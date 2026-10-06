"""MUST-E3 (v.5) through the CLI: DB files and sidecars 0600, directories opencanal creates 0700.

Also the user-id cap that NEVER-11 v.5 needs (fixed-size contributor-token frame) as the CLI reports it.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from opencanal import cli
from opencanal.models import Tier
from opencanal.store import Store


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


@contextmanager
def _umask(value: int) -> Iterator[None]:
    old = os.umask(value)
    try:
        yield
    finally:
        os.umask(old)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENCANAL_MASTER_KEY", "OPENCANAL_DB", "OPENCANAL_KEY_FILE", "OPENCANAL_TOKEN"):
        monkeypatch.delenv(name, raising=False)


def _paths(root: Path) -> list[str]:
    return ["--db", str(root / "data" / "opencanal.db"), "--key-file", str(root / "data" / "keys" / "master.key")]


def test_init_db_creates_private_dirs_and_db_even_with_permissive_umask(tmp_path: Path) -> None:
    root = tmp_path / "fresh"
    with _umask(0o000):
        assert cli.main([*_paths(root), "init-db"]) == 0
    assert _mode(root) == 0o700 and _mode(root / "data") == 0o700 and _mode(root / "data" / "keys") == 0o700
    assert _mode(root / "data" / "opencanal.db") == 0o600
    assert _mode(root / "data" / "keys" / "master.key") == 0o600


def test_init_db_narrows_an_existing_broader_db_and_sidecar_but_not_an_existing_dir(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    os.chmod(data, 0o755)
    db = data / "opencanal.db"
    assert cli.main([*_paths(tmp_path), "init-db"]) == 0
    os.chmod(db, 0o644)
    stale = Path(f"{db}-journal")
    stale.write_bytes(b"")
    os.chmod(stale, 0o644)
    assert cli.main([*_paths(tmp_path), "init-db"]) == 0
    assert _mode(db) == 0o600
    assert not stale.exists() or _mode(stale) == 0o600  # SQLite may also discard an empty journal
    assert _mode(data) == 0o755, "a directory opencanal did not create keeps its mode"


def test_db_sidecars_are_0600_while_the_store_is_open(tmp_path: Path) -> None:
    assert cli.main([*_paths(tmp_path), "create-user", "--name", "A", "--tier", "free", "--user-id", "user_a"]) == 0
    db = tmp_path / "data" / "opencanal.db"
    key = (tmp_path / "data" / "keys" / "master.key").read_bytes()
    with _umask(0o000):
        store = Store(db, master_key=key)
        try:
            store.create_user("B", Tier.FREE, user_id="user_b")
            for path in (db, Path(f"{db}-wal"), Path(f"{db}-shm")):
                assert _mode(path) == 0o600, path
        finally:
            store.close()


def test_create_user_refuses_an_overlong_user_id(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([*_paths(tmp_path), "create-user", "--name", "X", "--tier", "free", "--user-id", "u" * 65]) == 1
    err = capsys.readouterr().err
    assert "INVALID_ARGUMENT" in err and "64" in err
    assert cli.main([*_paths(tmp_path), "create-user", "--name", "X", "--tier", "free", "--user-id", "u" * 64]) == 0


def test_backup_and_restore_create_private_dirs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([*_paths(tmp_path), "init-db"]) == 0
    out_dir = tmp_path / "new-backups" / "nested"
    with _umask(0o000):
        assert cli.main([*_paths(tmp_path), "backup", "--out", str(out_dir)]) == 0
    assert _mode(tmp_path / "new-backups") == 0o700 and _mode(out_dir) == 0o700
    [backup] = list(out_dir.iterdir())
    assert _mode(backup) == 0o600

    target = tmp_path / "restored" / "deeper" / "o.db"
    key_file = str(tmp_path / "data" / "keys" / "master.key")
    with _umask(0o000):
        assert cli.main(["--key-file", key_file, "restore", "--in", str(backup), "--db", str(target)]) == 0
    assert _mode(tmp_path / "restored") == 0o700 and _mode(target.parent) == 0o700
    assert _mode(target) == 0o600
    assert sorted(p.name for p in target.parent.iterdir()) == ["o.db"]
