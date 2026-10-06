"""MUST-E3 (Oracle v.6): plaintext temporary DB files made during backup and restore are 0600 and are removed.

ORACLE §5.8 MUST-E3 (v.6): "백업·복원 중 잠깐 만드는 평문 임시 파일도 0600이고 작업이 끝나면 지운다". §9 (v.6): the backup
briefly made a plaintext DB copy with mode 0644 (adversarial review E3-3). The rest of MUST-E3 (the DB and its sidecars
0600, data directories 0700) is pinned in test_oracle_v5_file_modes.py and not repeated here.

How it is observed (tests/oracle/_tmpspy.py): an audit hook stats every plaintext SQLite file (SQLite header, or a
-journal/-wal/-shm next to one) right before each Python-level file step — open, chmod, unlink, rename/replace, rmtree,
sqlite3.connect, mkstemp ... — plus a polling thread. A temporary copy that is read back, chmod-ed, renamed into
place or deleted is therefore seen with the mode it had at that moment. For the `opencanal` CLI the same observer is
loaded into the subprocess through a generated sitecustomize. An implementation that makes no temporary file at all
(for example sqlite3 `serialize()`) passes: nothing plaintext is seen besides the live DB.

Every test runs under umask 022 (a file created without an explicit mode would be 0644) and with a fresh, empty
temporary directory (tempfile.tempdir and TMPDIR), which must be empty again afterwards. The live DB, and for restore
the restored DB, stay; anything else plaintext that appeared must be gone, and every plaintext file seen — the
restored DB included (MUST-E3: a DB file opencanal creates is 0600) — must have been 0600 at every observation.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator

import pytest

from .conftest import World
from ._tmpspy import DIRS_ENV, LOG_ENV, SIDECARS, SQLITE_HEADER, Spy, prepare_site_dir, read_log
from ._v4 import cli_env, opencanal_bin

pytestmark = pytest.mark.timeout(180)

CLI_TIMEOUT = 120.0


@pytest.fixture(autouse=True)
def _no_env_master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCANAL_MASTER_KEY", raising=False)


@pytest.fixture(autouse=True)
def umask_022() -> Iterator[None]:
    old = os.umask(0o022)  # inherited by CLI subprocesses
    try:
        yield
    finally:
        os.umask(old)


@pytest.fixture
def fresh_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "tmpdir"
    d.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(d))
    monkeypatch.setenv("TMPDIR", str(d))
    return d


def _files(d: Path) -> list[str]:
    return sorted(str(p) for p in d.rglob("*") if p.is_file()) if d.exists() else []


def _non_sidecar_files(d: Path, db: Path) -> set[str]:
    side = {str(db) + s for s in SIDECARS}
    return {p for p in _files(d) if p not in side}


def _rp(p: Path | str) -> str:
    return os.path.realpath(os.fspath(p))


def _without(observations: dict[str, set[int]], *dbs: Path) -> dict[str, set[int]]:
    """Observations keyed by real path, minus the given live DBs and their sidecars (pinned by the v.5 tests)."""
    skip = {_rp(db) + s for db in dbs for s in ("", *SIDECARS)}
    out: dict[str, set[int]] = {}
    for p, modes in observations.items():
        rp = _rp(p)
        if rp not in skip:
            out.setdefault(rp, set()).update(modes)
    return out


def _assert_clean(
    observations: dict[str, set[int]],
    *,
    keep: list[Path],
    tmpdir: Path,
    what: str,
) -> None:
    """MUST-E3 v.6: every plaintext file seen was 0600 every time; only `keep` (and their sidecars) remain."""
    observations = _without(observations)
    keep_set = {_rp(p) for p in keep}
    keep_all = keep_set | {k + s for k in keep_set for s in SIDECARS}
    wide = {p: sorted(oct(m) for m in modes) for p, modes in sorted(observations.items()) if any(m != 0o600 for m in modes)}
    assert not wide, f"{what}: plaintext DB file(s) seen with a mode other than 0600 (MUST-E3 v.6): {wide}"
    left = [p for p in sorted(observations) if p not in keep_all and os.path.exists(p)]
    assert not left, f"{what}: plaintext temporary file(s) still exist afterwards (MUST-E3 v.6 '지운다'): {left}"
    assert _files(tmpdir) == [], f"{what}: files left in the temporary directory: {_files(tmpdir)}"


def _plaintext(path: Path) -> bool:
    with open(path, "rb") as fh:
        return fh.read(len(SQLITE_HEADER)) == SQLITE_HEADER


# ---------------------------------------------------------------------------
# The observer itself (controls: it must see a 0644 copy, and must not flag a 0600 one)
# ---------------------------------------------------------------------------


def _copy_via_sqlite(src: sqlite3.Connection, path: str) -> bytes:
    dst = sqlite3.connect(path)
    src.backup(dst)
    dst.close()
    data = Path(path).read_bytes()
    os.unlink(path)
    return data


def test_must_e3_v6_spy_control_sees_a_0644_copy_and_accepts_a_0600_one(tmp_path: Path, fresh_tmp: Path):
    src = sqlite3.connect(":memory:")
    src.execute("CREATE TABLE t (x TEXT)")
    src.execute("INSERT INTO t VALUES ('현장 조립 오류')")
    src.commit()
    with Spy([tmp_path]) as bad:
        _copy_via_sqlite(src, str(fresh_tmp / "copy.db"))  # created by SQLite under umask 022 -> 0644
    assert bad.wide(), "control: the observer must see a short-lived 0644 plaintext copy"
    assert _files(fresh_tmp) == []

    with Spy([tmp_path]) as good:
        fd, path = tempfile.mkstemp()  # 0600
        os.close(fd)
        data = _copy_via_sqlite(src, path)
    assert data.startswith(SQLITE_HEADER)
    assert good.observations and not good.wide(), f"control: a 0600 copy is fine: {good.observations}"

    with Spy([tmp_path]) as chmodded:
        path = str(fresh_tmp / "late.db")
        dst = sqlite3.connect(path)
        src.backup(dst)
        dst.close()
        os.chmod(path, 0o600)  # narrowed only after the plaintext was already on disk
        os.unlink(path)
    assert chmodded.wide(), "control: a copy narrowed to 0600 after being written 0644 was still exposed"
    src.close()


def test_must_e3_v6_spy_control_works_inside_a_subprocess(tmp_path: Path, fresh_tmp: Path):
    site = prepare_site_dir(tmp_path / "spy_site")
    log = tmp_path / "spy.log"
    code = (
        "import os, sqlite3, tempfile\n"
        "p = os.path.join(tempfile.gettempdir(), 'copy.db')\n"
        "c = sqlite3.connect(p); c.execute('CREATE TABLE t (x)'); c.commit(); c.close()\n"
        "open(p, 'rb').read(); os.unlink(p)\n"
    )
    env = dict(os.environ, PYTHONPATH=str(site), TMPDIR=str(fresh_tmp), **{LOG_ENV: str(log), DIRS_ENV: str(tmp_path)})
    proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=CLI_TIMEOUT)
    assert proc.returncode == 0, proc.stderr
    rec = read_log(log)
    assert rec["loaded"] and rec["done"], rec
    assert any(m != 0o600 for modes in rec["observations"].values() for m in modes), rec


# ---------------------------------------------------------------------------
# Store.snapshot_bytes() and Store.restore_bytes()
# ---------------------------------------------------------------------------


def _file_world(tmp_path: Path) -> tuple[World, Path]:
    data = tmp_path / "data"
    data.mkdir()
    db = data / "opencanal.db"
    w = World(data, db_path=db)  # master key at data/master.key
    w.ensure_fixture_users()
    w.seed(("A", "B", "C"))
    return w, db


def test_must_e3_v6_snapshot_bytes_of_a_file_db(tmp_path: Path, fresh_tmp: Path):
    w, db = _file_world(tmp_path)
    try:
        before = _non_sidecar_files(db.parent, db)
        with Spy([tmp_path]) as spy:
            snapshot = w.store.snapshot_bytes()
        assert snapshot.startswith(SQLITE_HEADER), "self-check: the snapshot is the DB"
        _assert_clean(_without(spy.observations, db), keep=[], tmpdir=fresh_tmp, what="Store.snapshot_bytes() of a file DB")
        assert _non_sidecar_files(db.parent, db) == before, "snapshot_bytes left files next to the DB"
    finally:
        w.store.close()


def test_must_e3_v6_snapshot_bytes_of_an_in_memory_db(world: World, tmp_path: Path, fresh_tmp: Path):
    world.seed(("A", "B"))
    with Spy([tmp_path]) as spy:
        snapshot = world.store.snapshot_bytes()
    assert snapshot.startswith(SQLITE_HEADER)
    _assert_clean(spy.observations, keep=[], tmpdir=fresh_tmp, what="Store.snapshot_bytes() of an in-memory DB")


def test_must_e3_v6_restore_bytes(world: World, tmp_path: Path, fresh_tmp: Path):
    from opencanal.store import Store

    world.seed(("A", "B"))
    snapshot = world.store.snapshot_bytes()
    target_dir = tmp_path / "restored"
    target_dir.mkdir()
    target = target_dir / "opencanal.db"
    with Spy([tmp_path]) as spy:
        Store.restore_bytes(target, snapshot)
    assert target.exists() and _plaintext(target), "self-check: restored"
    _assert_clean(spy.observations, keep=[target], tmpdir=fresh_tmp, what="Store.restore_bytes()")
    assert _non_sidecar_files(target_dir, target) == {str(target)}, f"extra files: {_files(target_dir)}"


# ---------------------------------------------------------------------------
# CLI: `opencanal backup` / `opencanal restore` with the observer loaded into the subprocess
# ---------------------------------------------------------------------------


def _spy_env(base: dict[str, str], tmp_path: Path, fresh_tmp: Path, log: Path) -> dict[str, str]:
    site = prepare_site_dir(tmp_path / "spy_site")
    env = dict(base)
    env["PYTHONPATH"] = os.pathsep.join([str(site), *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])])
    env["TMPDIR"] = str(fresh_tmp)
    env[LOG_ENV] = str(log)
    env[DIRS_ENV] = str(tmp_path)
    return env


def _run(args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(opencanal_bin()), *args], env=env, cwd=str(cwd), capture_output=True, text=True, timeout=CLI_TIMEOUT
    )


@pytest.fixture
def cli_src(tmp_path: Path) -> dict[str, Any]:
    src = tmp_path / "src"
    src.mkdir()
    db = src / "opencanal.db"
    w = World(src, db_path=db)  # master key at src/master.key
    w.ensure_fixture_users()
    w.seed(("A", "B", "C"))
    w.store.close()
    return {"db": db, "key": src / "master.key", "src": src}


def _observations(log: Path, what: str) -> dict[str, set[int]]:
    rec = read_log(log)
    assert rec["loaded"], f"{what}: the observer did not load in the subprocess (harness problem)"
    assert rec["done"], f"{what}: the subprocess exited without the observer's final report"
    return rec["observations"]


def test_must_e3_v6_cli_backup_temp_files_are_0600_and_removed(cli_src: dict, tmp_path: Path, fresh_tmp: Path):
    db, key, src = cli_src["db"], cli_src["key"], cli_src["src"]
    out_dir = tmp_path / "backups"
    log = tmp_path / "backup.spy.log"
    before = _non_sidecar_files(src, db)
    proc = _run(["backup", "--out", str(out_dir)], _spy_env(cli_env(db, key), tmp_path, fresh_tmp, log), tmp_path)
    assert proc.returncode == 0, f"backup failed: {proc.stdout}\n{proc.stderr}"
    observed = _without(_observations(log, "backup"), db)
    _assert_clean(observed, keep=[], tmpdir=fresh_tmp, what="opencanal backup")
    assert _non_sidecar_files(src, db) == before, f"backup left files next to the DB: {_files(src)}"
    outs = _files(out_dir)
    assert len(outs) == 1, f"expected exactly the backup file in {out_dir}, got {outs}"
    assert not _plaintext(Path(outs[0])), "the backup file is a plaintext DB"


def test_must_e3_v6_cli_restore_temp_files_are_0600_and_removed(cli_src: dict, tmp_path: Path, fresh_tmp: Path):
    db, key = cli_src["db"], cli_src["key"]
    out_dir = tmp_path / "backups"
    proc = _run(["backup", "--out", str(out_dir)], cli_env(db, key), tmp_path)  # made without the observer
    assert proc.returncode == 0, f"backup failed: {proc.stdout}\n{proc.stderr}"
    (backup,) = [Path(p) for p in _files(out_dir)]
    assert _files(fresh_tmp) == [], "self-check"

    target_dir = tmp_path / "restored"
    target_dir.mkdir()
    target = target_dir / "opencanal.db"
    log = tmp_path / "restore.spy.log"
    env = _spy_env(cli_env(target, key), tmp_path, fresh_tmp, log)
    proc = _run(["restore", "--db", str(target), "--key-file", str(key), "--in", str(backup)], env, tmp_path)
    assert proc.returncode == 0, f"restore failed: {proc.stdout}\n{proc.stderr}"
    assert target.exists() and _plaintext(target)
    observed = _without(_observations(log, "restore"), db)
    _assert_clean(observed, keep=[target], tmpdir=fresh_tmp, what="opencanal restore")
    assert _non_sidecar_files(target_dir, target) == {str(target)}, f"extra files: {_files(target_dir)}"
    assert _files(out_dir) == [str(backup)], "restore must not write next to the backup file"
