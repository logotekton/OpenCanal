"""Unit tests for opencanal.crypto (Builder K). NEVER-11 (v.5), MUST-E1/E2/E3, D-006."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import stat

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESSIV

from opencanal import crypto

ENV = "OPENCANAL_MASTER_KEY"
URLSAFE = re.compile(r"^[A-Za-z0-9_-]+$")


@pytest.fixture(autouse=True)
def _no_env_master_key(monkeypatch):
    # If the real environment had the key set, file-path tests would pass for the wrong reason.
    monkeypatch.delenv(ENV, raising=False)


@pytest.fixture
def key_a() -> bytes:
    return bytes(range(32))


@pytest.fixture
def key_b() -> bytes:
    return bytes(range(100, 132))


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def _b64_body(token: str) -> bytes:
    body = token[len("ct_"):]
    return base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))


# --- API tokens ---------------------------------------------------------------


def test_new_api_token_shape_and_uniqueness():
    t1 = crypto.new_api_token()
    t2 = crypto.new_api_token()
    assert t1.startswith("oc_")
    assert len(t1) >= 3 + 43  # 32 random bytes -> 43 urlsafe chars
    assert URLSAFE.match(t1[3:])
    assert t1 != t2


def test_hash_api_token_is_sha256_hex():
    token = crypto.new_api_token()
    h = crypto.hash_api_token(token)
    assert h == hashlib.sha256(token.encode()).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", h)
    assert crypto.hash_api_token(token) == h
    assert token not in h
    assert crypto.hash_api_token(crypto.new_api_token()) != h


# --- Master key file ----------------------------------------------------------


def test_master_key_created_with_parents_and_mode_0600(tmp_path):
    path = tmp_path / "nested" / "deeper" / "master.key"
    key = crypto.load_or_create_master_key(path)
    assert isinstance(key, bytes) and len(key) == 32
    assert path.read_bytes() == key
    assert _mode(path) == 0o600


def test_master_key_is_stable_across_loads(tmp_path):
    path = tmp_path / "master.key"
    first = crypto.load_or_create_master_key(path)
    second = crypto.load_or_create_master_key(str(path))
    assert first == second


def test_master_key_mode_0600_even_with_permissive_umask(tmp_path):
    old = os.umask(0o000)
    try:
        path = tmp_path / "k" / "master.key"
        crypto.load_or_create_master_key(path)
    finally:
        os.umask(old)
    assert _mode(path) == 0o600


def test_existing_world_readable_key_is_tightened(tmp_path):
    path = tmp_path / "master.key"
    raw = os.urandom(32)
    path.write_bytes(raw)
    os.chmod(path, 0o644)
    assert crypto.load_or_create_master_key(path) == raw
    assert _mode(path) == 0o600


@pytest.mark.parametrize("size", [0, 16, 31, 33, 64])
def test_existing_key_with_wrong_length_rejected(tmp_path, size):
    path = tmp_path / "master.key"
    path.write_bytes(b"\x01" * size)
    os.chmod(path, 0o600)
    with pytest.raises(ValueError):
        crypto.load_or_create_master_key(path)


def test_key_path_that_is_a_directory_rejected(tmp_path):
    path = tmp_path / "master.key"
    path.mkdir()
    with pytest.raises((ValueError, OSError)):
        crypto.load_or_create_master_key(path)


# --- Env override -------------------------------------------------------------


def test_env_override_wins_and_does_not_touch_filesystem(tmp_path, monkeypatch):
    raw = os.urandom(32)
    monkeypatch.setenv(ENV, base64.urlsafe_b64encode(raw).decode())
    path = tmp_path / "nested" / "master.key"
    assert crypto.load_or_create_master_key(path) == raw
    assert not path.exists()
    assert not path.parent.exists()


def test_env_override_beats_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "master.key"
    file_key = crypto.load_or_create_master_key(path)
    env_key = bytes(reversed(file_key))
    monkeypatch.setenv(ENV, base64.urlsafe_b64encode(env_key).decode())
    assert crypto.load_or_create_master_key(path) == env_key


def test_env_override_accepts_missing_padding(tmp_path, monkeypatch):
    raw = os.urandom(32)
    monkeypatch.setenv(ENV, base64.urlsafe_b64encode(raw).decode().rstrip("="))
    assert crypto.load_or_create_master_key(tmp_path / "m.key") == raw


@pytest.mark.parametrize(
    "value",
    [
        base64.urlsafe_b64encode(b"\x00" * 31).decode(),
        base64.urlsafe_b64encode(b"\x00" * 33).decode(),
        "not base64 at all!!",
        "a",
    ],
)
def test_env_override_invalid_raises(tmp_path, monkeypatch, value):
    monkeypatch.setenv(ENV, value)
    path = tmp_path / "m.key"
    with pytest.raises(ValueError):
        crypto.load_or_create_master_key(path)
    assert not path.exists()


# --- Master key validation ----------------------------------------------------


@pytest.mark.parametrize("bad", [b"", b"x" * 16, b"x" * 31, b"x" * 33, b"x" * 64])
def test_functions_reject_wrong_length_master_key(bad):
    with pytest.raises(ValueError):
        crypto.contributor_token(bad, "user_a", "db_1")
    with pytest.raises(ValueError):
        crypto.encrypt_backup(bad, b"data")


def test_functions_reject_non_bytes_master_key():
    with pytest.raises(TypeError):
        crypto.contributor_token("k" * 32, "user_a", "db_1")  # type: ignore[arg-type]


# --- Contributor tokens -------------------------------------------------------


def test_contributor_token_is_deterministic(key_a):
    assert crypto.contributor_token(key_a, "user_a", "db_1") == crypto.contributor_token(key_a, "user_a", "db_1")


def test_contributor_token_differs_across_deltabrains(key_a):
    assert crypto.contributor_token(key_a, "user_a", "db_1") != crypto.contributor_token(key_a, "user_a", "db_2")


def test_contributor_token_differs_across_owners(key_a):
    assert crypto.contributor_token(key_a, "user_a", "db_1") != crypto.contributor_token(key_a, "user_b", "db_1")


def test_contributor_token_differs_across_master_keys(key_a, key_b):
    assert crypto.contributor_token(key_a, "user_a", "db_1") != crypto.contributor_token(key_b, "user_a", "db_1")


def test_contributor_token_format(key_a):
    token = crypto.contributor_token(key_a, "user_a", "db_1")
    assert token.startswith("ct_")
    assert "=" not in token
    assert URLSAFE.match(token[3:])


@pytest.mark.parametrize(
    "owner_id,deltabrain_id",
    [("user_a", "db_1"), ("사용자_가", "델타_1"), ("u", "db|with|pipes"), ("", "db_1")],
)
def test_contributor_token_round_trip(key_a, owner_id, deltabrain_id):
    token = crypto.contributor_token(key_a, owner_id, deltabrain_id)
    assert crypto.decrypt_contributor_token(key_a, token) == (owner_id, deltabrain_id)


def test_contributor_token_hides_owner_plaintext(key_a):
    owner = "user_alice_owner"
    deltabrain = "db_0123456789"
    token = crypto.contributor_token(key_a, owner, deltabrain)
    raw = _b64_body(token)
    assert owner not in token
    assert deltabrain not in token
    assert owner.encode() not in raw
    assert base64.urlsafe_b64encode(owner.encode()).decode().rstrip("=") not in token


def test_contributor_token_owner_with_separator_round_trips(key_a):
    # Length-prefixed fields: "|" in the owner id is no longer ambiguous (and no longer a server crash).
    token = crypto.contributor_token(key_a, "user|a", "db_1")
    assert crypto.decrypt_contributor_token(key_a, token) == ("user|a", "db_1")
    assert token != crypto.contributor_token(key_a, "user", "a|db_1")


# --- NEVER-11 v.5: the token length says nothing about the owner id ---------------


LONGEST_OWNER_IDS = [
    "a" * crypto.MAX_OWNER_ID_CHARS,
    "가" * crypto.MAX_OWNER_ID_CHARS,  # 3 UTF-8 bytes each
    "\U0001F600" * crypto.MAX_OWNER_ID_CHARS,  # 4 UTF-8 bytes each: the byte maximum
]


def test_contributor_token_length_is_independent_of_owner_id(key_a):
    owners = ["", "u", "user_c", "user_with_a_much_longer_identifier_0123456789", "사용자_가", *LONGEST_OWNER_IDS]
    lengths = {len(crypto.contributor_token(key_a, owner, "db_0123456789abcdef")) for owner in owners}
    assert len(lengths) == 1, lengths
    # ... and of the deltabrain id.
    assert {len(crypto.contributor_token(key_a, "user_c", d)) for d in ("d", "db_0123456789abcdef", "x" * 64)} == lengths


@pytest.mark.parametrize("owner_id", LONGEST_OWNER_IDS)
def test_contributor_token_longest_owner_ids_round_trip(key_a, owner_id):
    token = crypto.contributor_token(key_a, owner_id, "db_" + "f" * 16)
    assert crypto.decrypt_contributor_token(key_a, token) == (owner_id, "db_" + "f" * 16)


@pytest.mark.parametrize(
    "owner_id,deltabrain_id",
    [
        ("a" * (crypto.MAX_OWNER_ID_BYTES + 1), "db_1"),
        ("\U0001F600" * crypto.MAX_OWNER_ID_CHARS + "a", "db_1"),
        ("user_c", "x" * (crypto.MAX_DELTABRAIN_ID_BYTES + 1)),
        ("user_\ud800", "db_1"),  # lone surrogate: not encodable
    ],
)
def test_contributor_token_rejects_ids_that_do_not_fit_the_frame(key_a, owner_id, deltabrain_id):
    with pytest.raises(ValueError):
        crypto.contributor_token(key_a, owner_id, deltabrain_id)


def _seal(key: bytes, plaintext: bytes) -> str:
    """A token over an arbitrary plaintext, as only someone holding the subkey could make it."""
    raw = AESSIV(crypto._contributor_token_key(key)).encrypt(plaintext, None)
    return "ct_" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _frame(owner: bytes, deltabrain: bytes, size: int = crypto._CONTRIBUTOR_TOKEN_FRAME_BYTES) -> bytes:
    body = len(owner).to_bytes(2, "big") + owner + len(deltabrain).to_bytes(2, "big") + deltabrain
    return body + bytes(size - len(body))


def test_contributor_token_plaintext_is_the_documented_frame(key_a):
    assert crypto.contributor_token(key_a, "user_c", "db_1") == _seal(key_a, _frame(b"user_c", b"db_1"))


@pytest.mark.parametrize(
    "plaintext",
    [
        b"user_c|db_1",  # the pre-v.5 unframed plaintext
        _frame(b"user_c", b"db_1")[:-1],  # frame too short
        _frame(b"user_c", b"db_1") + b"\x00",  # frame too long
        _frame(b"user_c", b"db_1")[:-1] + b"\x01",  # non-zero padding
        b"\x01\x01" + _frame(b"user_c", b"db_1")[2:],  # owner length beyond the cap
        _frame(b"\xff\xfe", b"db_1"),  # owner bytes not UTF-8
        _frame(b"user_c", b"\xc3"),  # deltabrain bytes not UTF-8
    ],
)
def test_contributor_token_malformed_frame_rejected(key_a, plaintext):
    with pytest.raises(ValueError):
        crypto.decrypt_contributor_token(key_a, _seal(key_a, plaintext))


def test_contributor_token_tamper_every_position_detected(key_a):
    token = crypto.contributor_token(key_a, "user_a", "db_1")
    body = token[3:]
    for i in range(len(body)):
        replacement = "A" if body[i] != "A" else "B"
        tampered = "ct_" + body[:i] + replacement + body[i + 1:]
        with pytest.raises(ValueError):
            crypto.decrypt_contributor_token(key_a, tampered)


def test_contributor_token_byte_flip_detected(key_a):
    token = crypto.contributor_token(key_a, "user_a", "db_1")
    raw = bytearray(_b64_body(token))
    for i in range(len(raw)):
        flipped = bytearray(raw)
        flipped[i] ^= 0x01
        tampered = "ct_" + base64.urlsafe_b64encode(bytes(flipped)).decode().rstrip("=")
        with pytest.raises(ValueError):
            crypto.decrypt_contributor_token(key_a, tampered)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t[:-1],  # truncated
        lambda t: t[:10],
        lambda t: "xx_" + t[3:],  # wrong prefix
        lambda t: t[3:],  # no prefix
        lambda t: t + "=",  # padding not allowed
        lambda t: t + "AAAA",  # extended
        lambda t: "ct_",
        lambda t: "ct_!!!!",
        lambda t: "",
    ],
)
def test_contributor_token_malformed_rejected(key_a, mutate):
    token = crypto.contributor_token(key_a, "user_a", "db_1")
    with pytest.raises(ValueError):
        crypto.decrypt_contributor_token(key_a, mutate(token))


def test_contributor_token_non_str_rejected(key_a):
    with pytest.raises(ValueError):
        crypto.decrypt_contributor_token(key_a, None)  # type: ignore[arg-type]


def test_contributor_token_wrong_master_key_rejected(key_a, key_b):
    token = crypto.contributor_token(key_a, "user_a", "db_1")
    with pytest.raises(ValueError):
        crypto.decrypt_contributor_token(key_b, token)


def test_contributor_token_not_encrypted_with_master_key_directly(key_a):
    token = crypto.contributor_token(key_a, "user_a", "db_1")
    # A 32-byte master key is a valid AES-128-SIV key, so this exercises "wrong key", not "bad size".
    with pytest.raises(InvalidTag):
        AESSIV(key_a).decrypt(_b64_body(token), None)


# --- Backups ------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"plain backup",
        "모듈러 조립 오류 — 서브브레인 라벨과 요약".encode("utf-8"),
        os.urandom(4096),
    ],
)
def test_backup_round_trip(key_a, data):
    blob = crypto.encrypt_backup(key_a, data)
    assert isinstance(blob, bytes)
    assert crypto.decrypt_backup(key_a, blob) == data


def test_backup_accepts_ascii_text_blob(key_a):
    blob = crypto.encrypt_backup(key_a, b"data")
    assert crypto.decrypt_backup(key_a, blob.decode("ascii")) == b"data"
    with pytest.raises(ValueError):
        crypto.decrypt_backup(key_a, "비밀 not ascii")


def test_backup_plaintext_absent_from_ciphertext(key_a):
    label = "모듈러 조립 오류".encode("utf-8")
    summary = b"BIM assumes a shared data standard"
    data = b'{"label": "' + label + b'", "summary": "' + summary + b'"}'
    blob = crypto.encrypt_backup(key_a, data)
    for needle in (label, summary, data):
        assert needle not in blob
        assert base64.urlsafe_b64encode(needle).rstrip(b"=") not in blob
        assert base64.b64encode(needle).rstrip(b"=") not in blob


def test_backup_tamper_detected(key_a):
    blob = bytearray(crypto.encrypt_backup(key_a, b"secret data"))
    blob[len(blob) // 2] = ord("A") if blob[len(blob) // 2] != ord("A") else ord("B")
    with pytest.raises(ValueError):
        crypto.decrypt_backup(key_a, bytes(blob))


def test_backup_garbage_rejected(key_a):
    with pytest.raises(ValueError):
        crypto.decrypt_backup(key_a, b"not a fernet token")


def test_backup_wrong_master_key_rejected(key_a, key_b):
    blob = crypto.encrypt_backup(key_a, b"secret data")
    with pytest.raises(ValueError):
        crypto.decrypt_backup(key_b, blob)


def test_backup_not_encrypted_with_master_key_directly(key_a):
    blob = crypto.encrypt_backup(key_a, b"secret data")
    with pytest.raises(InvalidToken):
        Fernet(base64.urlsafe_b64encode(key_a)).decrypt(blob)


def test_backup_and_contributor_subkeys_are_distinct(key_a):
    ct_key = crypto._contributor_token_key(key_a)
    bk_key = crypto._backup_key(key_a)
    assert len(ct_key) == 64 and len(bk_key) == 32
    assert bk_key != ct_key[:32] and bk_key != ct_key[32:]
    assert key_a not in (ct_key[:32], ct_key[32:], bk_key)


def test_withheld_ref_subkey_is_distinct(key_a):
    wr_key = crypto._withheld_ref_key(key_a)
    ct_key = crypto._contributor_token_key(key_a)
    assert len(wr_key) == 32
    assert wr_key not in (key_a, crypto._backup_key(key_a), ct_key[:32], ct_key[32:])


# --- Withheld refs (NEVER-11 v.5) ---------------------------------------------


def test_withheld_ref_is_stable_within_a_canal_and_unlinkable_across_canals(key_a, key_b):
    ref = crypto.withheld_ref(key_a, "cn_1", "sb_c")
    assert ref == crypto.withheld_ref(key_a, "cn_1", "sb_c")
    assert ref != crypto.withheld_ref(key_a, "cn_2", "sb_c")
    assert ref != crypto.withheld_ref(key_a, "cn_1", "sb_b")
    assert ref != crypto.withheld_ref(key_b, "cn_1", "sb_c")


def test_withheld_ref_format_and_construction(key_a):
    ref = crypto.withheld_ref(key_a, "cn_1", "sb_c")
    assert ref.startswith("wr_") and URLSAFE.match(ref[3:]) and "=" not in ref
    assert "sb_c" not in ref and "cn_1" not in ref
    mac = hmac.new(crypto._withheld_ref_key(key_a), b"cn_1|sb_c", hashlib.sha256).digest()[:16]
    assert ref == "wr_" + base64.urlsafe_b64encode(mac).decode().rstrip("=")
    assert len({len(crypto.withheld_ref(key_a, c, s)) for c, s in [("c", "s"), ("cn_" + "f" * 16, "sb_" + "0" * 40)]}) == 1


def test_withheld_ref_rejects_non_str(key_a):
    with pytest.raises(TypeError):
        crypto.withheld_ref(key_a, "cn_1", None)  # type: ignore[arg-type]


# --- Private directories (MUST-E3) ----------------------------------------------


def test_make_private_dirs_creates_every_missing_level_0700_even_with_permissive_umask(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    old = os.umask(0o000)
    try:
        crypto.make_private_dirs(target)
    finally:
        os.umask(old)
    for d in (tmp_path / "a", tmp_path / "a" / "b", target):
        assert _mode(d) == 0o700, d


def test_make_private_dirs_leaves_existing_directories_alone(tmp_path):
    existing = tmp_path / "shared"
    existing.mkdir()
    os.chmod(existing, 0o755)
    crypto.make_private_dirs(existing / "data")
    crypto.make_private_dirs(existing)
    assert _mode(existing) == 0o755
    assert _mode(existing / "data") == 0o700


def test_make_private_dirs_refuses_a_file(tmp_path):
    f = tmp_path / "file"
    f.write_text("x")
    with pytest.raises(OSError):
        crypto.make_private_dirs(f)
    with pytest.raises(OSError):
        crypto.make_private_dirs(f / "below")


def test_master_key_parent_dirs_created_0700(tmp_path):
    crypto.load_or_create_master_key(tmp_path / "data" / "keys" / "master.key")
    assert _mode(tmp_path / "data") == 0o700 and _mode(tmp_path / "data" / "keys") == 0o700
