"""MUST-E3 (v.6) in the Store: snapshot_bytes writes no plaintext copy of the DB to disk, and the temp file that
restore_bytes stages the image in is 0600 from creation and gone afterwards, on success and on failure.

Each case runs under umask 022 (the usual default, where SQLite creates files 0644) and umask 000 (where any file
created without an explicit mode shows up 0666, so nothing can pass by accident).
"""

from __future__ import annotations

import errno
import os
import sqlite3
import stat
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from opencanal import store as store_mod
from opencanal.models import Tier
from opencanal.store import Store

MASTER_KEY = b"k" * 32
UMASKS = pytest.mark.parametrize("umask", [0o022, 0o000], ids=["umask022", "umask000"])
USERS = [f"user_{i:02d}" for i in range(30)]


def _mode(path: Path | str) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def _listing(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


@contextmanager
def _umask(value: int) -> Iterator[None]:
    old = os.umask(value)
    try:
        yield
    finally:
        os.umask(old)


class _ConnectSpy:
    """Stands in for sqlite3.connect: records every on-disk DB opened, with its mode and its directory's mode."""

    def __init__(self, real: Callable[..., sqlite3.Connection], *, close_before_return: bool = False) -> None:
        self.real = real
        self.close_before_return = close_before_return
        self.files: list[tuple[str, int, int]] = []

    def __call__(self, database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = self.real(database, *args, **kwargs)
        name = str(database)
        if name != ":memory:":
            self.files.append((name, _mode(name), _mode(os.path.dirname(name))))
        if self.close_before_return:
            conn.close()  # the next use (the backup) fails after the temp file exists
        return conn


class _CreateSpy:
    """Stands in for os.open: records every file an O_CREAT open succeeded on, with its mode right then."""

    def __init__(self, real: Callable[..., int]) -> None:
        self.real = real
        self.created: list[tuple[str, int]] = []

    def __call__(self, path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        fd = self.real(path, flags, *args, **kwargs)
        if flags & os.O_CREAT:
            self.created.append((os.fspath(path), stat.S_IMODE(os.fstat(fd).st_mode)))
        return fd


@pytest.fixture
def wal_store(tmp_path: Path) -> Iterator[Store]:
    """A file DB in WAL mode whose rows are still only in the -wal (no checkpoint yet)."""
    s = Store(tmp_path / "db" / "live.db", master_key=MASTER_KEY)
    s._conn.execute("PRAGMA wal_autocheckpoint=0")
    for user_id in USERS:
        s.create_user(user_id, Tier.FREE, user_id=user_id)
    assert (tmp_path / "db" / "live.db-wal").stat().st_size > 0
    yield s
    s.close()


@pytest.fixture
def private_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The process temp dir, pointed at an empty directory so a left-behind temp file is visible."""
    directory = tmp_path / "tmp"
    directory.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(directory))
    return directory


def _users_in(image: bytes) -> list[str]:
    conn = sqlite3.connect(":memory:")
    try:
        conn.deserialize(image)  # refuses an image whose header still says WAL
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        return [row[0] for row in conn.execute("SELECT id FROM users ORDER BY id")]
    finally:
        conn.close()


@UMASKS
def test_snapshot_creates_no_file_at_all(
    wal_store: Store, private_tmp: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, umask: int
) -> None:
    db_dir = tmp_path / "db"
    before = _listing(db_dir)
    connects = _ConnectSpy(sqlite3.connect)
    creates = _CreateSpy(os.open)
    monkeypatch.setattr(sqlite3, "connect", connects)
    monkeypatch.setattr(os, "open", creates)
    with _umask(umask):
        image = wal_store.snapshot_bytes()
    monkeypatch.undo()
    assert connects.files == [], "the copy must be made in memory, not in a DB file"
    assert creates.created == []
    assert _listing(private_tmp) == []
    assert _listing(db_dir) == before
    assert image.startswith(b"SQLite format 3\x00")
    assert _users_in(image) == USERS  # rows that were only in the -wal are in the copy


def test_snapshot_of_a_wal_db_is_a_self_contained_rollback_image(wal_store: Store, tmp_path: Path) -> None:
    image = wal_store.snapshot_bytes()
    assert image[18:20] == b"\x01\x01", "header must not say WAL"
    out = tmp_path / "out"
    Store.restore_bytes(out / "o.db", image)
    raw = sqlite3.connect(out / "o.db")
    try:
        assert raw.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert raw.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert [row[0] for row in raw.execute("SELECT id FROM users ORDER BY id")] == USERS
    finally:
        raw.close()
    assert _listing(out) == ["o.db"]  # reading it made no -wal/-shm


def test_snapshot_of_a_memory_store_is_left_as_sqlite_wrote_it() -> None:
    s = Store(":memory:", master_key=MASTER_KEY)
    try:
        s.create_user("A", Tier.FREE, user_id="user_a")
        image = s.snapshot_bytes()
    finally:
        s.close()
    assert image[18:20] == b"\x01\x01"
    assert _users_in(image) == ["user_a"]


def test_self_contained_image_changes_only_the_wal_version_bytes() -> None:
    wal = b"SQLite format 3\x00" + b"\x10\x00" + b"\x02\x02" + b"x" * 80
    patched = store_mod._self_contained_image(wal)
    assert patched[18:20] == b"\x01\x01"
    assert patched[:18] == wal[:18] and patched[20:] == wal[20:]
    rollback = wal[:18] + b"\x01\x01" + wal[20:]
    assert store_mod._self_contained_image(rollback) is rollback


@UMASKS
def test_fallback_without_serialize_uses_a_0600_file_in_a_0700_dir_and_removes_it(
    wal_store: Store, private_tmp: Path, monkeypatch: pytest.MonkeyPatch, umask: int
) -> None:
    monkeypatch.setattr(store_mod, "_CAN_SERIALIZE", False)
    connects = _ConnectSpy(sqlite3.connect)
    monkeypatch.setattr(sqlite3, "connect", connects)
    with _umask(umask):
        image = wal_store.snapshot_bytes()
    [(path, file_mode, dir_mode)] = connects.files
    assert Path(path).parent.parent == private_tmp
    assert file_mode == 0o600 and dir_mode == 0o700
    assert _listing(private_tmp) == [], "the temp directory is removed with the copy in it"
    assert image[18:20] == b"\x01\x01"
    assert _users_in(image) == USERS


@UMASKS
def test_fallback_removes_its_temp_file_when_the_backup_fails(
    wal_store: Store, private_tmp: Path, monkeypatch: pytest.MonkeyPatch, umask: int
) -> None:
    monkeypatch.setattr(store_mod, "_CAN_SERIALIZE", False)
    connects = _ConnectSpy(sqlite3.connect, close_before_return=True)
    monkeypatch.setattr(sqlite3, "connect", connects)
    with _umask(umask), pytest.raises(sqlite3.ProgrammingError):
        wal_store.snapshot_bytes()
    [(_, file_mode, dir_mode)] = connects.files
    assert file_mode == 0o600 and dir_mode == 0o700
    assert _listing(private_tmp) == []


@UMASKS
@pytest.mark.parametrize("fail", [False, True], ids=["success", "failure"])
def test_restore_bytes_temp_file_is_0600_while_written_and_removed(
    wal_store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, umask: int, fail: bool
) -> None:
    data = wal_store.snapshot_bytes()
    out = tmp_path / "out"
    out.mkdir()
    real_fsync = os.fsync
    seen: list[tuple[list[str], int]] = []

    def spy_fsync(fd: int) -> None:
        st = os.fstat(fd)
        if stat.S_ISREG(st.st_mode):  # the staged image (the directory is fsynced too)
            seen.append((_listing(out), stat.S_IMODE(st.st_mode)))
            if fail:
                raise OSError(errno.EIO, "I/O error")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", spy_fsync)
    with _umask(umask):
        if fail:
            with pytest.raises(OSError):
                Store.restore_bytes(out / "o.db", data)
        else:
            Store.restore_bytes(out / "o.db", data)
    [(names, mode)] = seen
    assert mode == 0o600
    assert len(names) == 1 and names[0].startswith(".o.db.") and names[0].endswith(".restoring")
    assert _listing(out) == ([] if fail else ["o.db"])
    if not fail:
        assert _mode(out / "o.db") == 0o600 and (out / "o.db").read_bytes() == data
