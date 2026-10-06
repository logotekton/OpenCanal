"""`opencanal restore` (CRY-1): refuse a target with leftover SQLite sidecars, never leave a partial DB.

SQLite reads <db>-wal / <db>-shm / <db>-journal as part of <db>. A WAL left behind by a killed server
would be replayed on top of the restored image (post-backup rows, or a corrupt DB), so restore must
refuse while any of them exists. A failed restore (wrong key, corrupt blob, write error) leaves no file.
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

import pytest

from opencanal import cli, crypto
from opencanal.models import Tier
from opencanal.store import Store

SIDECARS = ("-wal", "-shm", "-journal")


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    for name in ("OPENCANAL_MASTER_KEY", "OPENCANAL_DB", "OPENCANAL_KEY_FILE", "OPENCANAL_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    key_file = tmp_path / "keys" / "master.key"
    key = crypto.load_or_create_master_key(key_file)
    store = Store(tmp_path / "live.db", master_key=key)
    try:
        store.create_user("백업 시점 사용자", Tier.FREE, user_id="user_a")
        blob = crypto.encrypt_backup(key, store.snapshot_bytes())
    finally:
        store.close()
    backup = tmp_path / "backup.db.enc"
    backup.write_bytes(blob)
    out = tmp_path / "out"
    out.mkdir()
    return {"key_file": key_file, "backup": backup, "out": out, "target": out / "o.db"}


def _restore(world: dict[str, Path], *, backup: Path | None = None, key_file: Path | None = None) -> int:
    return cli.main(
        [
            "--key-file", str(key_file or world["key_file"]),
            "restore", "--in", str(backup or world["backup"]), "--db", str(world["target"]),
        ]
    )


def _listing(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


def _users(db: Path, key_file: Path) -> list[str]:
    store = Store(db, master_key=key_file.read_bytes())
    try:
        return [row[0] for row in store._conn.execute("SELECT id FROM users ORDER BY id")]
    finally:
        store.close()


def test_restore_writes_the_backup_exactly(world: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
    assert _restore(world) == 0
    assert "복원 완료" in capsys.readouterr().out
    target = world["target"]
    assert _listing(world["out"]) == ["o.db"]  # no temp file, no sidecar
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600
    assert _users(target, world["key_file"]) == ["user_a"]


@pytest.mark.parametrize("suffix", SIDECARS)
def test_restore_refuses_leftover_sidecar(
    world: dict[str, Path], capsys: pytest.CaptureFixture[str], suffix: str
) -> None:
    sidecar = Path(f"{world['target']}{suffix}")
    sidecar.write_bytes(b"left by a killed server")
    assert _restore(world) == 1
    err = capsys.readouterr().err
    assert str(sidecar) in err and "옮기" in err
    assert not world["target"].exists()
    assert sidecar.read_bytes() == b"left by a killed server"  # the operator's file is not touched
    assert _listing(world["out"]) == [sidecar.name]


def test_restore_refuses_dangling_sidecar_symlink(world: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
    sidecar = Path(f"{world['target']}-wal")
    sidecar.symlink_to(world["out"] / "gone")
    assert _restore(world) == 1
    assert str(sidecar) in capsys.readouterr().err
    assert not world["target"].exists()


def test_restore_refuses_existing_db(world: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
    world["target"].write_bytes(b"current db")
    assert _restore(world) == 1
    assert "덮어쓰지 않습니다" in capsys.readouterr().err
    assert world["target"].read_bytes() == b"current db"


def test_stale_wal_from_killed_writer_is_never_replayed(world: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
    """The judge's scenario: post-backup writes only in <db>-wal, DB moved away, restore to the same path."""
    target = world["target"]
    key = world["key_file"].read_bytes()
    Store.restore_bytes(target, crypto.decrypt_backup(key, world["backup"].read_bytes()))
    writer = Store(target, master_key=key)
    writer.create_user("Mallory", Tier.EXPERT, user_id="user_mallory")
    # Simulate kill -9: copy the files while the writer still holds the WAL, then drop the connection.
    files = {p.name: p.read_bytes() for p in world["out"].iterdir()}
    writer.close()
    for p in list(world["out"].iterdir()):
        p.unlink()
    for name, data in files.items():
        (world["out"] / name).write_bytes(data)
    assert Path(f"{target}-wal").stat().st_size > 0
    target.rename(world["out"] / "o.db.bad")

    assert _restore(world) == 1
    assert "-wal" in capsys.readouterr().err
    assert not target.exists()


def test_wrong_key_leaves_nothing(world: dict[str, Path], tmp_path: Path) -> None:
    other = tmp_path / "other.key"
    crypto.load_or_create_master_key(other)
    assert _restore(world, key_file=other) == 1
    assert _listing(world["out"]) == []


def test_tampered_blob_leaves_nothing(world: dict[str, Path], tmp_path: Path) -> None:
    blob = bytearray(world["backup"].read_bytes())
    blob[len(blob) // 2] ^= 0x01
    bad = tmp_path / "bad.db.enc"
    bad.write_bytes(bytes(blob))
    assert _restore(world, backup=bad) == 1
    assert _listing(world["out"]) == []


@pytest.mark.parametrize("image", ["not sqlite", "truncated", "garbage pages"])
def test_bad_image_inside_valid_backup_is_refused_cleanly(
    world: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str], image: str
) -> None:
    key = world["key_file"].read_bytes()
    good = crypto.decrypt_backup(key, world["backup"].read_bytes())
    data = {
        "not sqlite": b"plain text, decrypts fine",
        "truncated": good[: len(good) // 2],
        "garbage pages": good[:100] + os.urandom(len(good) - 100),
    }[image]
    bad = tmp_path / "bad.db.enc"
    bad.write_bytes(crypto.encrypt_backup(key, data))
    assert _restore(world, backup=bad) == 1  # a CliError, not a traceback
    assert "오류:" in capsys.readouterr().err
    assert _listing(world["out"]) == []


def test_write_failure_midway_leaves_no_partial_file(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def disk_full(db_path: Path | str, data: bytes) -> None:
        Path(db_path).write_bytes(data[:4096])
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(Store, "restore_bytes", staticmethod(disk_full))
    assert _restore(world) == 1
    assert "No space left" in capsys.readouterr().err
    assert _listing(world["out"]) == []


def test_file_appearing_during_restore_is_not_replaced(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real_check = cli._check_sqlite_image

    def racing_check(path: Path) -> None:
        real_check(path)
        world["target"].write_bytes(b"written by someone else meanwhile")

    monkeypatch.setattr(cli, "_check_sqlite_image", racing_check)
    assert _restore(world) == 1
    assert "덮어쓰지 않습니다" in capsys.readouterr().err
    assert world["target"].read_bytes() == b"written by someone else meanwhile"
    assert _listing(world["out"]) == ["o.db"]


def test_filesystem_without_hard_links_falls_back_to_exclusive_copy(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_links(src: object, dst: object) -> None:
        raise OSError(errno.EPERM, "Operation not permitted")

    monkeypatch.setattr(cli.os, "link", no_links)
    assert _restore(world) == 0
    assert _listing(world["out"]) == ["o.db"]
    assert stat.S_IMODE(os.stat(world["target"]).st_mode) == 0o600
    assert _users(world["target"], world["key_file"]) == ["user_a"]


def test_target_created_just_before_link_is_not_replaced(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real_link = os.link

    def racing_link(src: str | Path, dst: str | Path) -> None:
        if Path(dst) == world["target"]:  # Store.restore_bytes may link its own temp file first
            Path(dst).write_bytes(b"won the race")
        real_link(src, dst)

    monkeypatch.setattr(cli.os, "link", racing_link)
    assert _restore(world) == 1
    err = capsys.readouterr().err
    assert "덮어쓰지 않습니다" in err and str(world["target"]) in err and ".tmp" not in err
    assert world["target"].read_bytes() == b"won the race"
    assert _listing(world["out"]) == ["o.db"]
