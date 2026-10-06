"""Keys, token hashing, contributor-token encryption, backup encryption (ORACLE NEVER-11, MUST-E1/E2, D-006).

Owner: Builder K.
"""

from __future__ import annotations

from pathlib import Path


def new_api_token() -> str:
    """Return a fresh MCP token: "oc_" + urlsafe random (>= 32 bytes entropy)."""
    raise NotImplementedError


def hash_api_token(token: str) -> str:
    """sha256 hex of the token. Only this is stored."""
    raise NotImplementedError


def load_or_create_master_key(path: Path | str) -> bytes:
    """Read a 32-byte master key; if missing create it (parent dirs too) with file mode 0600.

    Env OPENCANAL_MASTER_KEY (urlsafe base64 of 32 bytes) overrides the file when set.
    """
    raise NotImplementedError


def contributor_token(master_key: bytes, owner_id: str, deltabrain_id: str) -> str:
    """Deterministic AES-SIV encryption of f"{owner_id}|{deltabrain_id}" with an HKDF subkey; urlsafe b64 string.

    Same inputs -> same token; different deltabrain_id -> different token.
    """
    raise NotImplementedError


def decrypt_contributor_token(master_key: bytes, token: str) -> tuple[str, str]:
    """Inverse of contributor_token -> (owner_id, deltabrain_id). Raises ValueError on tamper."""
    raise NotImplementedError


def encrypt_backup(master_key: bytes, data: bytes) -> bytes:
    """Fernet-encrypt with an HKDF subkey distinct from the contributor-token subkey."""
    raise NotImplementedError


def decrypt_backup(master_key: bytes, blob: bytes) -> bytes:
    raise NotImplementedError
