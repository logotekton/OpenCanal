"""MUST-E1, MUST-E2 and the NEVER-11 token primitive (ORACLE §5.5, §5.8; DECISIONS D-005, D-006)."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

from opencanal.config import DEFAULT_DATA_DIR, REPO_ROOT
from opencanal.models import Tier

from .conftest import World, assert_ok, load_brain


@pytest.fixture(autouse=True)
def _no_env_master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCANAL_MASTER_KEY", raising=False)


# ---------------------------------------------------------------------------
# MUST-E1 — key file and encrypted backup
# ---------------------------------------------------------------------------


def test_must_e1_master_key_file_created_with_mode_0600(tmp_path: Path):
    from opencanal import crypto

    path = tmp_path / "data" / "keys" / "master.key"  # parent dirs do not exist yet
    key = crypto.load_or_create_master_key(path)
    assert isinstance(key, bytes) and len(key) == 32
    assert path.exists()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert crypto.load_or_create_master_key(path) == key, "existing key is reused, not replaced"
    other = crypto.load_or_create_master_key(tmp_path / "other.key")
    assert other != key


def test_must_e1_key_location_is_gitignored():
    assert DEFAULT_DATA_DIR == REPO_ROOT / "data"
    lines = {line.strip() for line in (REPO_ROOT / ".gitignore").read_text("utf-8").splitlines()}
    assert "data/" in lines, ".gitignore must exclude the data/ directory (keys and DBs live there)"
    assert "*.key" in lines, ".gitignore must exclude key files anywhere"


def test_must_e1_backup_has_no_plaintext_and_restores(seeded: World, tmp_path: Path):
    from opencanal import crypto
    from opencanal.store import Store

    snapshot = seeded.store.snapshot_bytes()
    blob = crypto.encrypt_backup(seeded.master_key, snapshot)
    assert isinstance(blob, bytes) and blob != snapshot

    plaintexts = [
        "현장 조립 오류",
        "형태 상보성",
        "잘못 놓을 수 없는 블록 모양",
        load_brain("A")["document"]["title"],
        load_brain("P")["document"]["title"],
        load_brain("C")["document"]["nodes"][1]["summary"],
        "이전 지시를 무시하고",
        seeded.tokens["user_a"],
    ]
    for text in plaintexts:
        assert text.encode("utf-8") not in blob, f"backup contains plaintext {text!r}"

    with pytest.raises(Exception):
        crypto.decrypt_backup(crypto.load_or_create_master_key(tmp_path / "wrong.key"), blob)

    restored_path = tmp_path / "restored" / "opencanal.db"
    restored_path.parent.mkdir()
    Store.restore_bytes(restored_path, crypto.decrypt_backup(seeded.master_key, blob))
    restored = Store(restored_path, master_key=seeded.master_key)
    try:
        for uid in ("user_a", "user_b"):
            assert [s.model_dump(mode="json") for s in restored.list_subbrains_for_owner(uid)] == [
                s.model_dump(mode="json") for s in seeded.store.list_subbrains_for_owner(uid)
            ]
        aid = seeded.sid("A")
        assert (
            restored.get_subbrain_for_viewer("user_a", aid).document
            == seeded.store.get_subbrain_for_viewer("user_a", aid).document
        )
        user = restored.user_by_token(seeded.tokens["user_a"])
        assert user is not None and user.id == "user_a"
    finally:
        restored.close()

    with pytest.raises(Exception):
        Store.restore_bytes(restored_path, snapshot)  # never overwrite an existing DB


# ---------------------------------------------------------------------------
# MUST-E2 — only token hashes are stored
# ---------------------------------------------------------------------------


def test_must_e2_token_format_and_hash():
    from opencanal import crypto

    t1, t2 = crypto.new_api_token(), crypto.new_api_token()
    assert t1 != t2
    assert t1.startswith("oc_") and len(t1) >= 3 + 43  # >= 32 bytes of urlsafe entropy
    assert crypto.hash_api_token(t1) == hashlib.sha256(t1.encode("utf-8")).hexdigest()


def test_must_e2_database_files_hold_no_plaintext_token(tmp_path: Path):
    from opencanal import crypto
    from opencanal.store import Store

    key = crypto.load_or_create_master_key(tmp_path / "master.key")
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    store = Store(db_dir / "opencanal.db", master_key=key)
    _, token_a = store.create_user("Haram Kim", Tier.FREE, user_id="user_a")
    _, token_b_old = store.create_user("Bora Lee", Tier.PRO, user_id="user_b")
    token_b = store.rotate_token("user_b")
    assert store.user_by_token(token_a).id == "user_a"
    assert store.user_by_token(token_b).id == "user_b"
    assert store.user_by_token(token_b_old) is None
    store.close()

    blobs = b"".join(p.read_bytes() for p in db_dir.iterdir() if p.is_file())
    assert blobs, "the store wrote its DB under the given path"
    for token in (token_a, token_b_old, token_b):
        assert token.encode() not in blobs, "plaintext token stored"
        assert token.split("_", 1)[-1].encode() not in blobs
    assert crypto.hash_api_token(token_a).encode() in blobs, "positive control: the hash is what is stored"


def test_must_e2_no_tool_response_echoes_a_token(seeded: World):
    for uid in ("user_a", "user_b"):
        token = seeded.tokens[uid]
        for tool, args in (("subbrain_list_mine", {}), ("deltabrain_list", {})):
            env = assert_ok(seeded.call(uid, tool, **args))
            assert token not in str(env)


# ---------------------------------------------------------------------------
# NEVER-11 primitive — deterministic contributor token (D-006)
# ---------------------------------------------------------------------------


def test_never_11_contributor_token_properties(tmp_path: Path):
    from opencanal import crypto

    key = crypto.load_or_create_master_key(tmp_path / "master.key")
    t = crypto.contributor_token(key, "user_c", "db_1")
    assert crypto.contributor_token(key, "user_c", "db_1") == t, "same inputs -> same token"
    assert crypto.contributor_token(key, "user_c", "db_2") != t, "different deltabrain -> different token"
    assert crypto.contributor_token(key, "user_b", "db_1") != t
    assert "user_c" not in t and "db_1" not in t
    assert crypto.decrypt_contributor_token(key, t) == ("user_c", "db_1")

    other_key = crypto.load_or_create_master_key(tmp_path / "other.key")
    with pytest.raises(ValueError):
        crypto.decrypt_contributor_token(other_key, t)
    tampered = t[:-2] + ("AA" if t[-2:] != "AA" else "BB")
    with pytest.raises(ValueError):
        crypto.decrypt_contributor_token(key, tampered)
