"""Keys, token hashing, contributor-token encryption, backup encryption (ORACLE NEVER-11, MUST-E1/E2, D-006).

Owner: Builder K.

The master key is never used directly. Each purpose gets its own HKDF-SHA256 subkey
(D-006): one for contributor tokens (AES-SIV), one for backups (Fernet).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import secrets
import stat
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MASTER_KEY_ENV = "OPENCANAL_MASTER_KEY"
MASTER_KEY_BYTES = 32

API_TOKEN_PREFIX = "oc_"
CONTRIBUTOR_TOKEN_PREFIX = "ct_"

_CONTRIBUTOR_TOKEN_INFO = b"opencanal/contributor-token/v1"
_CONTRIBUTOR_TOKEN_KEY_BYTES = 64  # AES-256-SIV
_BACKUP_INFO = b"opencanal/backup/v1"
_BACKUP_KEY_BYTES = 32  # Fernet signing + encryption halves


# --- MCP API tokens (MUST-E2) -------------------------------------------------


def new_api_token() -> str:
    """Return a fresh MCP token: "oc_" + urlsafe random (>= 32 bytes entropy)."""
    return API_TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_api_token(token: str) -> str:
    """sha256 hex of the token. Only this is stored."""
    if not isinstance(token, str):
        raise TypeError("token must be str")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- Master key (MUST-E1) -----------------------------------------------------


def _b64url_decode_strict(value: str) -> bytes:
    """Strict urlsafe base64 decode; padding optional. Raises ValueError on any malformed input."""
    padded = value + "=" * (-len(value) % 4)
    try:
        return base64.b64decode(padded, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid urlsafe base64") from exc


def _b64url_encode_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _master_key_from_env(value: str) -> bytes:
    try:
        key = _b64url_decode_strict(value)
    except ValueError as exc:
        raise ValueError(f"{MASTER_KEY_ENV} is not valid urlsafe base64") from exc
    if len(key) != MASTER_KEY_BYTES:
        raise ValueError(f"{MASTER_KEY_ENV} must decode to {MASTER_KEY_BYTES} bytes")
    return key


def _read_master_key_file(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError(f"master key path is not a regular file: {path}")
        # fd-based chmod: tighten the very file we are about to read.
        if st.st_mode & 0o077:
            os.fchmod(fd, 0o600)
        data = b""
        while len(data) <= MASTER_KEY_BYTES:
            chunk = os.read(fd, MASTER_KEY_BYTES + 1 - len(data))
            if not chunk:
                break
            data += chunk
    finally:
        os.close(fd)
    if len(data) != MASTER_KEY_BYTES:
        raise ValueError(f"master key file must be exactly {MASTER_KEY_BYTES} bytes: {path}")
    return data


def _create_master_key_file(path: Path) -> bytes | None:
    """Create the key file exclusively with mode 0600. Returns None if it already exists."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return None
    try:
        os.fchmod(fd, 0o600)  # umask can only remove bits; pin the mode exactly anyway
        key = os.urandom(MASTER_KEY_BYTES)
        view = memoryview(key)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return key


def load_or_create_master_key(path: Path | str) -> bytes:
    """Read a 32-byte master key; if missing create it (parent dirs too) with file mode 0600.

    Env OPENCANAL_MASTER_KEY (urlsafe base64 of 32 bytes) overrides the file when set.
    """
    env_value = os.environ.get(MASTER_KEY_ENV, "").strip()
    if env_value:
        # Env wins: do not touch the filesystem at all.
        return _master_key_from_env(env_value)

    key_path = Path(path)
    if not key_path.exists():
        key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        created = _create_master_key_file(key_path)
        if created is not None:
            return created
        # Another process created it between exists() and open(); read theirs.
    return _read_master_key_file(key_path)


# --- Subkeys (D-006) ----------------------------------------------------------


def _check_master_key(master_key: bytes) -> bytes:
    if not isinstance(master_key, (bytes, bytearray)):
        raise TypeError("master_key must be bytes")
    if len(master_key) != MASTER_KEY_BYTES:
        raise ValueError(f"master_key must be {MASTER_KEY_BYTES} bytes")
    return bytes(master_key)


def _derive(master_key: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info).derive(
        _check_master_key(master_key)
    )


def _contributor_token_key(master_key: bytes) -> bytes:
    return _derive(master_key, _CONTRIBUTOR_TOKEN_INFO, _CONTRIBUTOR_TOKEN_KEY_BYTES)


def _backup_key(master_key: bytes) -> bytes:
    return _derive(master_key, _BACKUP_INFO, _BACKUP_KEY_BYTES)


# --- Contributor tokens (NEVER-11, D-006) -------------------------------------


def contributor_token(master_key: bytes, owner_id: str, deltabrain_id: str) -> str:
    """Deterministic AES-SIV encryption of f"{owner_id}|{deltabrain_id}" with an HKDF subkey; urlsafe b64 string.

    Same inputs -> same token; different deltabrain_id -> different token.
    """
    if not isinstance(owner_id, str) or not isinstance(deltabrain_id, str):
        raise TypeError("owner_id and deltabrain_id must be str")
    if "|" in owner_id:
        # The separator must be unambiguous so decryption splits on the first "|".
        raise ValueError("owner_id must not contain '|'")
    plaintext = f"{owner_id}|{deltabrain_id}".encode("utf-8")
    ciphertext = AESSIV(_contributor_token_key(master_key)).encrypt(plaintext, None)
    return CONTRIBUTOR_TOKEN_PREFIX + _b64url_encode_nopad(ciphertext)


def decrypt_contributor_token(master_key: bytes, token: str) -> tuple[str, str]:
    """Inverse of contributor_token -> (owner_id, deltabrain_id). Raises ValueError on tamper."""
    key = _contributor_token_key(master_key)
    if not isinstance(token, str) or not token.startswith(CONTRIBUTOR_TOKEN_PREFIX):
        raise ValueError("invalid contributor token")
    body = token[len(CONTRIBUTOR_TOKEN_PREFIX):]
    if not body or "=" in body:
        raise ValueError("invalid contributor token")
    try:
        ciphertext = _b64url_decode_strict(body)
    except ValueError as exc:
        raise ValueError("invalid contributor token") from exc
    # Reject non-canonical encodings (e.g. stray low bits) so one ciphertext has one token.
    if _b64url_encode_nopad(ciphertext) != body:
        raise ValueError("invalid contributor token")
    try:
        plaintext = AESSIV(key).decrypt(ciphertext, None)
    except (InvalidTag, ValueError) as exc:
        raise ValueError("invalid contributor token") from exc
    try:
        text = plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid contributor token") from exc
    owner_id, sep, deltabrain_id = text.partition("|")
    if not sep:
        raise ValueError("invalid contributor token")
    return owner_id, deltabrain_id


# --- Backups (MUST-E1) --------------------------------------------------------


def _backup_fernet(master_key: bytes) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(_backup_key(master_key)))


def encrypt_backup(master_key: bytes, data: bytes) -> bytes:
    """Fernet-encrypt with an HKDF subkey distinct from the contributor-token subkey."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("data must be bytes")
    return _backup_fernet(master_key).encrypt(bytes(data))


def decrypt_backup(master_key: bytes, blob: bytes) -> bytes:
    fernet = _backup_fernet(master_key)
    if isinstance(blob, str):
        blob = blob.encode("ascii", errors="replace")  # Fernet tokens are ASCII; tolerate text reads
    if not isinstance(blob, (bytes, bytearray)):
        raise TypeError("blob must be bytes")
    try:
        return fernet.decrypt(bytes(blob))
    except InvalidToken as exc:
        raise ValueError("backup blob is invalid or was encrypted with a different key") from exc
