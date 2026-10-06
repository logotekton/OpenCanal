"""MUST-E3 (v.6) through `opencanal backup` / `opencanal restore`: no plaintext DB copy wider than 0600, and no
temporary left behind on success or on failure.

backup must not write a plaintext copy at all (the only file it creates is the encrypted, 0600 backup). restore
has to put a plaintext DB at --db, so it stages the image in a temp file next to it: that file must be 0600 the
whole time, the integrity check must not add sidecars to it, and it must be gone afterwards.

Each case runs under umask 022 (the usual default, where SQLite creates files 0644) and umask 000.
"""

from __future__ import annotations

import os
import sqlite3
import stat
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from opencanal import cli, crypto

UMASKS = pytest.mark.parametrize("umask", [0o022, 0o000], ids=["umask022", "umask000"])
SQLITE_MAGIC = b"SQLite format 3\x00"


def _mode(path: Path | str) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def _modes(directory: Path) -> dict[str, int]:
    return {p.name: stat.S_IMODE(p.lstat().st_mode) for p in sorted(directory.iterdir())}


@contextmanager
def _umask(value: int) -> Iterator[None]:
    old = os.umask(value)
    try:
        yield
    finally:
        os.umask(old)


class _ConnectSpy:
    """Stands in for sqlite3.connect: records every on-disk DB opened (SQLite creates files in C, past os.open)."""

    def __init__(self, real: Callable[..., sqlite3.Connection]) -> None:
        self.real = real
        self.files: list[tuple[str, int]] = []

    def __call__(self, database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = self.real(database, *args, **kwargs)
        if str(database) != ":memory:":
            self.files.append((str(database), _mode(database)))
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


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENCANAL_MASTER_KEY", "OPENCANAL_DB", "OPENCANAL_KEY_FILE", "OPENCANAL_TOKEN"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def private_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The process temp dir, pointed at an empty directory so a left-behind temp file is visible."""
    directory = tmp_path / "tmp"
    directory.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(directory))
    return directory


@pytest.fixture
def live(tmp_path: Path) -> dict[str, Path]:
    data = tmp_path / "data"
    paths = {"db": data / "opencanal.db", "key": data / "keys" / "master.key", "data": data}
    for user_id in ("user_a", "user_b"):
        argv = ["--db", str(paths["db"]), "--key-file", str(paths["key"]), "create-user"]
        assert cli.main([*argv, "--name", user_id, "--tier", "free", "--user-id", user_id]) == 0
    return paths


def _backup(live: dict[str, Path], out_dir: Path) -> Path:
    assert cli.main(["--db", str(live["db"]), "--key-file", str(live["key"]), "backup", "--out", str(out_dir)]) == 0
    [backup] = list(out_dir.iterdir())
    return backup


def _restore(live: dict[str, Path], backup: Path, target: Path) -> int:
    return cli.main(["--key-file", str(live["key"]), "restore", "--in", str(backup), "--db", str(target)])


@UMASKS
def test_backup_writes_no_plaintext_copy(
    live: dict[str, Path], private_tmp: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, umask: int
) -> None:
    before = _modes(live["data"])
    out_dir = tmp_path / "backups"
    connects = _ConnectSpy(sqlite3.connect)
    creates = _CreateSpy(os.open)
    monkeypatch.setattr(sqlite3, "connect", connects)
    monkeypatch.setattr(os, "open", creates)
    with _umask(umask):
        backup = _backup(live, out_dir)
    monkeypatch.setattr(os, "open", creates.real)
    monkeypatch.setattr(sqlite3, "connect", connects.real)
    assert connects.files == [(os.path.realpath(live["db"]), 0o600)], "only the live DB is opened as a file"
    assert creates.created == [(str(backup), 0o600)], "the encrypted backup is the only file backup creates"
    assert _modes(private_tmp) == {}
    assert _modes(live["data"]) == before
    assert _modes(out_dir) == {backup.name: 0o600}
    blob = backup.read_bytes()
    assert SQLITE_MAGIC not in blob
    image = crypto.decrypt_backup(live["key"].read_bytes(), blob)
    assert image.startswith(SQLITE_MAGIC) and image[18:20] == b"\x01\x01"  # self-contained, not WAL


@UMASKS
def test_restore_stages_a_0600_temp_file_and_removes_it(
    live: dict[str, Path], private_tmp: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, umask: int
) -> None:
    backup = _backup(live, tmp_path / "backups")
    out = tmp_path / "out"
    out.mkdir()
    target = out / "o.db"
    real_check = cli._check_sqlite_image
    seen: list[dict[str, int]] = []

    def spy_check(path: Path) -> None:
        seen.append(_modes(out))
        real_check(path)
        seen.append(_modes(out))

    monkeypatch.setattr(cli, "_check_sqlite_image", spy_check)
    with _umask(umask):
        assert _restore(live, backup, target) == 0
    before_check, after_check = seen
    [(temp_name, temp_mode)] = before_check.items()
    assert temp_name.startswith(".o.db.restore-") and temp_name.endswith(".tmp")
    assert temp_mode == 0o600
    assert after_check == before_check, "the integrity check must not add -journal/-wal/-shm next to the image"
    assert _modes(out) == {"o.db": 0o600}
    assert _modes(private_tmp) == {}
    raw = sqlite3.connect(target)
    try:
        assert [row[0] for row in raw.execute("SELECT id FROM users ORDER BY id")] == ["user_a", "user_b"]
    finally:
        raw.close()


@UMASKS
def test_failed_restore_leaves_no_plaintext_temp_file(
    live: dict[str, Path],
    private_tmp: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    umask: int,
) -> None:
    key = live["key"].read_bytes()
    good = crypto.decrypt_backup(key, _backup(live, tmp_path / "backups").read_bytes())
    corrupt = tmp_path / "corrupt.db.enc"
    corrupt.write_bytes(crypto.encrypt_backup(key, good[:100] + os.urandom(len(good) - 100)))
    out = tmp_path / "out"
    out.mkdir()
    real_check = cli._check_sqlite_image
    seen: list[dict[str, int]] = []

    def spy_check(path: Path) -> None:
        seen.append(_modes(out))
        real_check(path)

    monkeypatch.setattr(cli, "_check_sqlite_image", spy_check)
    with _umask(umask):
        assert _restore(live, corrupt, out / "o.db") == 1
    assert "손상" in capsys.readouterr().err
    [staged] = seen
    assert list(staged.values()) == [0o600]
    assert _modes(out) == {}
    assert _modes(private_tmp) == {}
