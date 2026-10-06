"""MUST-E3 (Oracle v.5, owner decision "지금 0600 적용") — DB files 0600, data directory 0700.

ORACLE §5.8 MUST-E3: a DB file opencanal creates or opens, and its sidecars (-wal, -shm, -journal), have mode 0600;
an existing file with wider permissions is narrowed to 0600 when opened; a data directory opencanal creates is 0700.

Every test runs under umask 022 (the usual default), so a file created without an explicit mode would be 0644 and
a directory 0755: passing requires opencanal to set the modes itself. Directories the test creates on purpose are
not "created by opencanal" and are not checked.
"""

from __future__ import annotations

import os
import sqlite3
import stat
import subprocess
from pathlib import Path
from typing import Iterator

import pytest

from opencanal.models import Tier

from .conftest import World, assert_ok
from ._v4 import cli_env, opencanal_bin

pytestmark = pytest.mark.timeout(180)

CLI_TIMEOUT = 120.0
SIDECARS = ("-wal", "-shm", "-journal")


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


def _mode(p: Path) -> int:
    return stat.S_IMODE(os.stat(p).st_mode)


def _db_files(db: Path) -> list[Path]:
    return [db, *(Path(str(db) + s) for s in SIDECARS if Path(str(db) + s).exists())]


def _assert_db_files_0600(db: Path, when: str) -> None:
    assert db.exists(), f"{when}: {db} does not exist"
    bad = {f.name: oct(_mode(f)) for f in _db_files(db) if _mode(f) != 0o600}
    assert not bad, f"{when}: DB files must be 0600 (MUST-E3): {bad}"


def _key(tmp_path: Path) -> bytes:
    from opencanal import crypto

    return crypto.load_or_create_master_key(tmp_path / "master.key")


def _run(args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(opencanal_bin()), *args], env=env, cwd=str(cwd), capture_output=True, text=True, timeout=CLI_TIMEOUT
    )


# ---------------------------------------------------------------------------
# Store: create and open
# ---------------------------------------------------------------------------


def test_must_e3_store_creates_db_and_sidecars_0600(tmp_path: Path):
    from opencanal.store import Store

    d = tmp_path / "db"
    d.mkdir()
    db = d / "opencanal.db"
    store = Store(db, master_key=_key(tmp_path))
    try:
        store.create_user("Haram Kim", Tier.FREE, user_id="user_a")  # a write: journal / WAL files appear now
        _assert_db_files_0600(db, "new DB while open")
    finally:
        store.close()
    _assert_db_files_0600(db, "new DB after close")


def test_must_e3_existing_wider_db_is_tightened_on_open(tmp_path: Path):
    from opencanal.store import Store

    key = _key(tmp_path)
    d = tmp_path / "db"
    d.mkdir()
    db = d / "opencanal.db"
    store = Store(db, master_key=key)
    store.create_user("Haram Kim", Tier.FREE, user_id="user_a")
    store.close()
    for f in _db_files(db):
        os.chmod(f, 0o644)
    assert _mode(db) == 0o644, "self-check"

    store = Store(db, master_key=key)
    try:
        _assert_db_files_0600(db, "right after opening a 0644 DB")
        store.create_user("Bora Lee", Tier.FREE, user_id="user_b")
        _assert_db_files_0600(db, "after a write to the reopened DB (sidecars created after open)")
        assert store.get_user("user_a") is not None, "the existing data is kept"
    finally:
        store.close()
    _assert_db_files_0600(db, "after close")


def test_must_e3_existing_wider_sidecars_are_tightened_on_open(tmp_path: Path):
    """Sidecars that already exist when opencanal opens the DB (another connection keeps them alive) are narrowed too.

    The sidecars are real SQLite files of a live connection, never fabricated (a stale fake WAL would be replayed).
    In rollback-journal mode no sidecar survives between transactions, and only the DB file is checked.
    """
    from opencanal.store import Store

    key = _key(tmp_path)
    d = tmp_path / "db"
    d.mkdir()
    db = d / "opencanal.db"
    store = Store(db, master_key=key)
    store.create_user("Haram Kim", Tier.FREE, user_id="user_a")
    store.close()

    raw = sqlite3.connect(str(db))
    try:
        raw.execute("SELECT count(*) FROM sqlite_master").fetchall()  # in WAL mode this opens -wal and -shm
        files = _db_files(db)
        for f in files:
            os.chmod(f, 0o644)
        store = Store(db, master_key=key)
        try:
            _assert_db_files_0600(db, f"right after opening with existing {[f.name for f in files]}")
            store.create_user("Bora Lee", Tier.FREE, user_id="user_b")
            _assert_db_files_0600(db, "after a write")
        finally:
            store.close()
    finally:
        raw.close()


def test_must_e3_store_restore_bytes_writes_0600(seeded: World, tmp_path: Path):
    from opencanal.store import Store

    snapshot = seeded.store.snapshot_bytes()
    d = tmp_path / "restored"
    d.mkdir()
    target = d / "opencanal.db"
    Store.restore_bytes(target, snapshot)
    _assert_db_files_0600(target, "restore_bytes target")
    store = Store(target, master_key=seeded.master_key)
    try:
        assert store.get_user("user_a") is not None
        _assert_db_files_0600(target, "restored DB opened")
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Data directories opencanal creates are 0700
# ---------------------------------------------------------------------------


def test_must_e3_master_key_creates_its_data_directory_0700(tmp_path: Path):
    from opencanal import crypto

    data = tmp_path / "data"  # does not exist: opencanal creates it
    key = crypto.load_or_create_master_key(data / "master.key")
    assert len(key) == 32
    assert _mode(data) == 0o700, f"data directory created by opencanal is {oct(_mode(data))}"
    assert _mode(data / "master.key") == 0o600


def test_must_e3_store_created_data_directory_is_0700(tmp_path: Path):
    """If the Store creates the DB's missing parent directory, that directory is 0700 (the contract does not say
    whether Store creates directories; init-db below must)."""
    from opencanal.store import Store

    data = tmp_path / "data"
    db = data / "opencanal.db"
    try:
        store = Store(db, master_key=_key(tmp_path))
    except Exception:
        assert not db.exists()
        return
    try:
        store.create_user("Haram Kim", Tier.FREE, user_id="user_a")
        assert _mode(data) == 0o700, f"data directory created by the Store is {oct(_mode(data))}"
        _assert_db_files_0600(db, "DB in a Store-created directory")
    finally:
        store.close()


# ---------------------------------------------------------------------------
# CLI: init-db and restore
# ---------------------------------------------------------------------------


def test_must_e3_cli_init_db_creates_0700_data_dir_and_0600_db(tmp_path: Path):
    data = tmp_path / "data"  # does not exist
    db, key = data / "opencanal.db", data / "master.key"
    proc = _run(["init-db", "--db", str(db), "--key-file", str(key)], cli_env(db, key), tmp_path)
    assert proc.returncode == 0, f"init-db failed: {proc.stdout}\n{proc.stderr}"
    assert _mode(data) == 0o700, f"data directory created by init-db is {oct(_mode(data))}"
    _assert_db_files_0600(db, "init-db")
    assert _mode(key) == 0o600


@pytest.fixture
def backup_file(tmp_path: Path) -> dict:
    src = tmp_path / "src"
    src.mkdir()
    db = src / "opencanal.db"
    w = World(src, db_path=db)  # master key at src/master.key
    w.ensure_fixture_users()
    w.seed(("A", "B", "C"))
    tokens = dict(w.tokens)
    w.store.close()
    key = src / "master.key"
    out_dir = tmp_path / "backups"
    proc = _run(["backup", "--out", str(out_dir)], cli_env(db, key), tmp_path)
    assert proc.returncode == 0, f"backup failed: {proc.stdout}\n{proc.stderr}"
    files = sorted(p for p in out_dir.rglob("*") if p.is_file())
    assert len(files) == 1, files
    return {"tmp": tmp_path, "backup": files[0], "key": key, "tokens": tokens}


def _restore(bf: dict, target: Path) -> subprocess.CompletedProcess:
    return _run(
        ["restore", "--db", str(target), "--key-file", str(bf["key"]), "--in", str(bf["backup"])],
        cli_env(target, bf["key"]),
        bf["tmp"],
    )


def test_must_e3_cli_restore_writes_0600_db(backup_file: dict):
    from opencanal import crypto
    from opencanal.store import Store

    d = backup_file["tmp"] / "restored"
    d.mkdir()
    target = d / "opencanal.db"
    proc = _restore(backup_file, target)
    assert proc.returncode == 0, f"restore failed: {proc.stdout}\n{proc.stderr}"
    _assert_db_files_0600(target, "restored DB")
    store = Store(target, master_key=crypto.load_or_create_master_key(backup_file["key"]))
    try:
        user = store.user_by_token(backup_file["tokens"]["user_a"])
        assert user is not None and user.id == "user_a"
        _assert_db_files_0600(target, "restored DB opened")
    finally:
        store.close()


def test_must_e3_cli_restore_created_data_directory_is_0700(backup_file: dict):
    """If restore creates the target's missing directory, it is 0700 and the DB 0600."""
    data = backup_file["tmp"] / "new_data"  # does not exist
    target = data / "opencanal.db"
    proc = _restore(backup_file, target)
    if proc.returncode != 0:
        assert not target.exists(), "a failed restore leaves no DB behind"
        return
    assert _mode(data) == 0o700, f"data directory created by restore is {oct(_mode(data))}"
    _assert_db_files_0600(target, "restored DB in a restore-created directory")
