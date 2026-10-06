"""SQLite persistence with viewer-scoped accessors (ORACLE §5.5).

Owner: Builder ST. Every read that a tool can reach goes through a *_for_viewer / *_for_owner
method that enforces visibility. "Missing" and "not visible to you" both raise
OpenCanalError(NOT_FOUND) with the same message (no existence leak).

There are no delete methods for user data (NEVER-03, D-005): subbrains only switch between
public and private, and every version / canal / deltabrain row is kept.

Every write runs in one BEGIN IMMEDIATE transaction (`_write_txn`), so a count-then-write such as the
monthly canal limit or the public subbrain limit is atomic across processes sharing the DB file (TIER-1).

MUST-E3 (v.5): the DB file and its -wal/-shm/-journal sidecars are 0600, the directory created for them 0700.
MUST-E3 (v.6): snapshot_bytes writes no plaintext copy to disk; restore_bytes stages the image in a 0600 temp file
that is removed on success and on failure.
"""

from __future__ import annotations

import errno
import hmac
import json
import os
import re
import secrets
import sqlite3
import stat
import tempfile
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import crypto
from .models import (
    Canal,
    CanalContext,
    CanalMember,
    DeltabrainRecord,
    DeltabrainStats,
    DeltabrainSubmission,
    EdgeRating,
    ErrorCode,
    NodeKind,
    OpenCanalError,
    QueryMode,
    SubbrainDocument,
    SubbrainSummary,
    SubbrainVersion,
    Tier,
    User,
    Visibility,
)

MASKED_DISPLAY = "비공개 기여자"
MONTHLY_CANAL_LIMIT_MESSAGE = "이번 달 커널 수 한도를 넘습니다 / monthly canal limit reached"
PUBLIC_SUBBRAIN_LIMIT_MESSAGE = "공개 서브브레인 수 한도를 넘습니다 / public subbrain limit reached"
# Contributor tokens hold the owner id in a fixed-size frame (NEVER-11 v.5), so user ids have a hard cap.
MAX_USER_ID_CHARS = crypto.MAX_OWNER_ID_CHARS
USER_ID_TOO_LONG_MESSAGE = (
    f"사용자 ID는 {MAX_USER_ID_CHARS}자 이하여야 합니다 / user id must be at most {MAX_USER_ID_CHARS} characters"
)
_SQLITE_MAGIC = b"SQLite format 3\x00"
# Files SQLite treats as part of the database at <db>: a stale one is replayed into a restored image (CRY-1).
_SQLITE_SIDECARS = ("-wal", "-shm", "-journal")
# Header bytes 18/19 of a DB image: file format write/read version, 1 = rollback journal, 2 = WAL.
_WAL_HEADER_VERSION = b"\x02\x02"
_ROLLBACK_HEADER_VERSION = b"\x01\x01"
# Connection.serialize() exists only when Python's SQLite has the serialize API (built in by default since 3.36).
_CAN_SERIALIZE = hasattr(sqlite3.Connection, "serialize")
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

# How one owner is counted for one viewer: ("plain", owner_id) or ("masked", owner_token) (NEVER-11).
_IdentityKey = tuple[str, str]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    tier TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_api_tokens_user ON api_tokens(user_id);
CREATE TABLE IF NOT EXISTS subbrains (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES users(id),
    visibility TEXT NOT NULL,
    published_version INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_subbrains_owner ON subbrains(owner_id);
CREATE TABLE IF NOT EXISTS subbrain_versions (
    subbrain_id TEXT NOT NULL REFERENCES subbrains(id),
    version INTEGER NOT NULL,
    document_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    domains_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (subbrain_id, version)
);
CREATE TABLE IF NOT EXISTS canals (
    id TEXT PRIMARY KEY,
    host_user_id TEXT NOT NULL REFERENCES users(id),
    host_subbrain_id TEXT NOT NULL,
    host_version INTEGER NOT NULL,
    query TEXT NOT NULL,
    query_mode_used TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (host_subbrain_id, host_version) REFERENCES subbrain_versions(subbrain_id, version)
);
CREATE INDEX IF NOT EXISTS ix_canals_host ON canals(host_user_id);
CREATE TABLE IF NOT EXISTS canal_members (
    canal_id TEXT NOT NULL REFERENCES canals(id),
    subbrain_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    owner_id TEXT NOT NULL,
    relevance REAL NOT NULL,
    distance REAL NOT NULL,
    matched_terms_json TEXT NOT NULL,
    PRIMARY KEY (canal_id, subbrain_id),
    FOREIGN KEY (subbrain_id, version) REFERENCES subbrain_versions(subbrain_id, version)
);
CREATE INDEX IF NOT EXISTS ix_canal_members_owner ON canal_members(owner_id);
CREATE TABLE IF NOT EXISTS deltabrains (
    id TEXT PRIMARY KEY,
    canal_id TEXT NOT NULL REFERENCES canals(id),
    submitted_by TEXT NOT NULL,
    submission_json TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_deltabrains_canal ON deltabrains(canal_id);
CREATE TABLE IF NOT EXISTS edge_ratings (
    deltabrain_id TEXT NOT NULL REFERENCES deltabrains(id),
    edge_id TEXT NOT NULL,
    rater_id TEXT NOT NULL,
    novelty INTEGER NOT NULL,
    validity INTEGER NOT NULL,
    usefulness INTEGER NOT NULL,
    rated_at TEXT NOT NULL,
    PRIMARY KEY (deltabrain_id, edge_id, rater_id)
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    detail_json TEXT NOT NULL
);
-- TASK-001 §6 calls the audit log the `audit` table; keep both names readable.
CREATE VIEW IF NOT EXISTS audit AS SELECT * FROM audit_log;
"""


def _not_found() -> OpenCanalError:
    # One message for "missing" and "not yours / not visible" (NEVER-01, NEVER-05). No detail.
    return OpenCanalError(ErrorCode.NOT_FOUND, "not found")


def _new_id(prefix: str) -> str:
    return prefix + secrets.token_hex(8)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _viewer_stats(
    submission: DeltabrainSubmission,
    stored: DeltabrainStats,
    host: tuple[str, int],
    keys: Mapping[str, Optional[_IdentityKey]],
) -> DeltabrainStats:
    """Deltabrain stats over the identities one viewer is shown (ORACLE v.4 NEVER-11).

    `keys` maps each cited subbrain_id to the key its owner is shown under (None: no such subbrain). A masked
    owner is never merged with a plainly shown one, so the result is the same whether the masked contributor is
    or is not one of the visible owners. Same rules as validator._stats (§4): owners of the endpoint nodes'
    refs decide emergence (query nodes exempt), owners_involved also counts edge refs. A ref to the host counts
    as host-touching only when the viewer sees it plainly: a masked ref must not reveal that it is the host.
    The stored (true) stats are returned unchanged when nothing is masked for this viewer.
    """
    if all(key is not None and key[0] == "plain" for key in keys.values()):
        return stored
    node_refs = {
        node.id: [] if node.kind == NodeKind.QUERY else [r for r in node.provenance if keys.get(r.subbrain_id)]
        for node in submission.nodes
    }
    owners = {keys[r.subbrain_id] for refs in node_refs.values() for r in refs}
    owners |= {keys[r.subbrain_id] for e in submission.edges for r in e.provenance if keys.get(r.subbrain_id)}
    emergent: list[str] = []
    host_touching: list[str] = []
    for edge in submission.edges:
        refs = [*node_refs.get(edge.source, ()), *node_refs.get(edge.target, ())]
        if len({keys[r.subbrain_id] for r in refs}) < 2:
            continue
        emergent.append(edge.id)
        if any((r.subbrain_id, r.version) == host and keys[r.subbrain_id][0] == "plain" for r in refs):
            host_touching.append(edge.id)
    return stored.model_copy(
        update={
            "emergent_edge_ids": emergent,
            "host_touching_emergent_edge_ids": host_touching,
            "owners_involved": len(owners),
        }
    )


def _fsync_dir(directory: Path) -> None:
    """Persist a directory entry (best effort: not every platform can fsync a directory)."""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _exists_error(path: Path) -> FileExistsError:
    return FileExistsError(errno.EEXIST, "refusing to restore over an existing database file", str(path))


def _sidecars(path: Path) -> list[Path]:
    return [path.with_name(path.name + suffix) for suffix in _SQLITE_SIDECARS]


def _tighten(fd: int) -> None:
    """chmod 0600 when the open file is a regular file with any permission bit beyond 0600 (MUST-E3)."""
    st = os.fstat(fd)
    if stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode) & ~crypto.PRIVATE_FILE_MODE:
        os.fchmod(fd, crypto.PRIVATE_FILE_MODE)


def _tighten_existing(path: Path) -> None:
    try:
        # O_NONBLOCK: never hang on a FIFO planted at a sidecar path.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | _O_CLOEXEC)
    except FileNotFoundError:
        return
    try:
        _tighten(fd)
    finally:
        os.close(fd)


def _resolved_db_path(path: Path) -> Path:
    """The file SQLite actually uses for `path`: symlinks resolved, also a dangling one (its target).

    O_CREAT|O_EXCL on a symlink fails with EEXIST even when its target is missing, and SQLite places -wal/-shm/
    -journal next to the resolved target, not next to the link. Checking modes on the link path would therefore
    miss the very files SQLite creates (MUST-E3), so everything is done on, and SQLite opens, this path."""
    return Path(os.path.realpath(path))


def _prepare_db_file(db_path: Path) -> Path:
    """Before SQLite opens the DB (MUST-E3): create the directory (0700, only what is missing) and a missing DB file
    with mode 0600, and narrow an existing DB file and existing sidecars to 0600. All of it on the resolved path
    (`_resolved_db_path`), which is returned: the caller must open that path, not `db_path`.

    SQLite creates -wal/-shm/-journal with the main file's mode (unix VFS, verified), so a 0600 DB file keeps every
    sidecar it creates later at 0600; existing sidecars may predate that and are narrowed here.
    """
    path = _resolved_db_path(db_path)
    crypto.make_private_dirs(path.parent)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_CLOEXEC, crypto.PRIVATE_FILE_MODE)
    except FileExistsError:
        _tighten_existing(path)
    else:
        try:
            os.fchmod(fd, crypto.PRIVATE_FILE_MODE)  # umask can only remove bits; pin the mode exactly
        finally:
            os.close(fd)
    for sidecar in _sidecars(path):
        _tighten_existing(sidecar)
    return path


def _backup_in_memory(conn: sqlite3.Connection) -> bytes:
    """Copy `conn`'s DB into a private in-memory DB and serialize it: no file is written (MUST-E3 v.6)."""
    dest = sqlite3.connect(":memory:")
    try:
        conn.backup(dest)
        return dest.serialize()
    finally:
        dest.close()


def _backup_via_private_file(conn: sqlite3.Connection) -> bytes:
    """Fallback for an SQLite without the serialize API (MUST-E3 v.6): the copy goes to a 0600 file in a fresh 0700
    directory (mkdtemp), and the directory is removed with everything in it on success and on failure."""
    with tempfile.TemporaryDirectory(prefix="opencanal-snap-") as tmp:
        dest_path = os.path.join(tmp, "snapshot.db")
        # Create the file before SQLite does: SQLite would create it 0644 under umask 022. Its -journal, made while
        # the backup writes, takes the main file's mode.
        fd = os.open(dest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_CLOEXEC, crypto.PRIVATE_FILE_MODE)
        try:
            os.fchmod(fd, crypto.PRIVATE_FILE_MODE)  # umask can only remove bits; pin the mode exactly
        finally:
            os.close(fd)
        dest = sqlite3.connect(dest_path)  # an existing empty file is an empty DB; SQLite keeps its mode
        try:
            conn.backup(dest)
        finally:
            dest.close()
        return Path(dest_path).read_bytes()


def _self_contained_image(image: bytes) -> bytes:
    """`image` with the rollback-journal version in its header instead of WAL.

    The backup API copies page 1 as is, so the copy of a WAL-mode DB still says WAL: opening a file restored from it
    would put SQLite in WAL mode and create -wal/-shm next to it. The copy already holds every committed page (the
    backup reads through the WAL), so only these two bytes differ from a rollback-mode file; they are what
    `PRAGMA journal_mode=DELETE` writes, and that pragma cannot be used on a memory DB."""
    if image[18:20] == _WAL_HEADER_VERSION:
        return image[:18] + _ROLLBACK_HEADER_VERSION + image[20:]
    return image


class Store:
    def __init__(self, db_path: Path | str, *, master_key: bytes) -> None:
        """Open/create the SQLite DB (":memory:" allowed) and create tables if missing."""
        self._master_key = master_key
        self._lock = threading.RLock()
        # Time source for every stored timestamp. Service may point this at its own clock so that
        # count_canals_in_month() and the service agree on "this month".
        self.clock: Callable[[], datetime] = _utc_now
        path = str(db_path)
        self._is_memory = path == ":memory:" or path.startswith("file::memory:")
        if not self._is_memory:
            # Open the resolved path, so the files whose modes were just checked are the ones SQLite uses (MUST-E3).
            path = str(_prepare_db_file(Path(path)))
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys=ON")
            if not self._is_memory:
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
            if not self._is_memory:
                # The first write created -wal/-shm with the DB file's mode; re-check in case a sidecar was created
                # by another opener between our check and SQLite's open (MUST-E3).
                for sidecar in _sidecars(Path(path)):
                    _tighten_existing(sidecar)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- helpers ----------------------------------------------------------
    def _now(self) -> str:
        now = self.clock()
        now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
        return now.isoformat(timespec="seconds")

    def _one(self, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        return self._conn.execute(sql, tuple(params)).fetchone()

    def _all(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return self._conn.execute(sql, tuple(params)).fetchall()

    @contextmanager
    def _write_txn(self) -> Iterator[None]:
        """One write transaction that holds SQLite's write lock from its first statement.

        Store._lock only serializes this process. BEGIN IMMEDIATE makes every other connection to the same
        file wait (sqlite3 busy timeout) until we commit, so the reads inside (limit counts, next version)
        still hold when the write lands. An explicit BEGIN is required: legacy-mode sqlite3 would only open
        its implicit transaction at the first INSERT/UPDATE, after the count.
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._conn.rollback()
                raise
            self._conn.commit()

    def _audit_row(self, actor: str, action: str, target: str, detail: Optional[dict[str, Any]]) -> None:
        self._conn.execute(
            "INSERT INTO audit_log (ts, actor, action, target, detail_json) VALUES (?, ?, ?, ?, ?)",
            (self._now(), actor, action, target, _dumps(detail or {})),
        )

    @staticmethod
    def _user(row: sqlite3.Row) -> User:
        return User(id=row["id"], display_name=row["display_name"], tier=Tier(row["tier"]))

    def _subbrain_row(self, subbrain_id: str) -> Optional[sqlite3.Row]:
        return self._one(
            "SELECT s.*, u.display_name AS owner_display FROM subbrains s JOIN users u ON u.id = s.owner_id "
            "WHERE s.id = ?",
            (subbrain_id,),
        )

    def _latest_version(self, subbrain_id: str) -> int:
        row = self._one("SELECT MAX(version) AS v FROM subbrain_versions WHERE subbrain_id = ?", (subbrain_id,))
        return int(row["v"]) if row and row["v"] is not None else 0

    def _version(self, sb: sqlite3.Row, version: int) -> Optional[SubbrainVersion]:
        row = self._one(
            "SELECT * FROM subbrain_versions WHERE subbrain_id = ? AND version = ?", (sb["id"], version)
        )
        if row is None:
            return None
        visibility = Visibility(sb["visibility"])
        return SubbrainVersion(
            subbrain_id=sb["id"],
            version=row["version"],
            owner_id=sb["owner_id"],
            owner_display=sb["owner_display"],
            visibility=visibility,
            is_published_version=(visibility == Visibility.PUBLIC and row["version"] == sb["published_version"]),
            content_hash=row["content_hash"],
            created_at=row["created_at"],
            document=SubbrainDocument.model_validate_json(row["document_json"]),
        )

    def _summary(self, sb: sqlite3.Row) -> SubbrainSummary:
        latest = self._one(
            "SELECT version, title, domains_json FROM subbrain_versions WHERE subbrain_id = ? "
            "ORDER BY version DESC LIMIT 1",
            (sb["id"],),
        )
        return SubbrainSummary(
            subbrain_id=sb["id"],
            owner_id=sb["owner_id"],
            title=latest["title"],
            domains=json.loads(latest["domains_json"]),
            visibility=Visibility(sb["visibility"]),
            latest_version=latest["version"],
            published_version=sb["published_version"],
            updated_at=sb["updated_at"],
        )

    def _canal(self, canal_id: str) -> Optional[Canal]:
        row = self._one("SELECT * FROM canals WHERE id = ?", (canal_id,))
        if row is None:
            return None
        members = [
            CanalMember(
                subbrain_id=m["subbrain_id"],
                version=m["version"],
                owner_id=m["owner_id"],
                relevance=m["relevance"],
                distance=m["distance"],
                matched_terms=json.loads(m["matched_terms_json"]),
            )
            for m in self._all("SELECT * FROM canal_members WHERE canal_id = ? ORDER BY rowid", (canal_id,))
        ]
        return Canal(
            id=row["id"],
            host_user_id=row["host_user_id"],
            host_subbrain_id=row["host_subbrain_id"],
            host_version=row["host_version"],
            query=row["query"],
            query_mode_used=QueryMode(row["query_mode_used"]),
            members=members,
            created_at=row["created_at"],
        )

    @staticmethod
    def _record(row: sqlite3.Row) -> DeltabrainRecord:
        return DeltabrainRecord(
            id=row["id"],
            canal_id=row["canal_id"],
            submitted_by=row["submitted_by"],
            submission=DeltabrainSubmission.model_validate_json(row["submission_json"]),
            stats=DeltabrainStats.model_validate_json(row["stats_json"]),
            created_at=row["created_at"],
        )

    def _insert_token(self, user_id: str) -> str:
        token = crypto.new_api_token()
        self._conn.execute(
            "INSERT INTO api_tokens (token_hash, user_id, created_at, revoked_at) VALUES (?, ?, ?, NULL)",
            (crypto.hash_api_token(token), user_id, self._now()),
        )
        return token

    # -- users / tokens ---------------------------------------------------
    def create_user(self, display_name: str, tier: Tier, *, user_id: Optional[str] = None) -> tuple[User, str]:
        """Create a user and return (user, plaintext_token). Only the token hash is stored.

        INVALID_ARGUMENT for a user id over MAX_USER_ID_CHARS characters (or not encodable as UTF-8): the id must
        fit the fixed-size contributor-token frame (NEVER-11 v.5)."""
        uid = user_id or _new_id("u_")
        if not isinstance(uid, str) or len(uid) > MAX_USER_ID_CHARS:
            raise OpenCanalError(ErrorCode.INVALID_ARGUMENT, USER_ID_TOO_LONG_MESSAGE)
        try:
            uid.encode("utf-8")
        except UnicodeEncodeError:
            raise OpenCanalError(ErrorCode.INVALID_ARGUMENT, "user id is not valid text") from None
        tier = Tier(tier)
        with self._write_txn():
            if self._one("SELECT 1 FROM users WHERE id = ?", (uid,)) is not None:
                raise OpenCanalError(ErrorCode.INVALID_ARGUMENT, "user already exists")
            self._conn.execute(
                "INSERT INTO users (id, display_name, tier, created_at) VALUES (?, ?, ?, ?)",
                (uid, display_name, tier.value, self._now()),
            )
            token = self._insert_token(uid)
            self._audit_row(uid, "user.create", uid, {"tier": tier.value})
        return User(id=uid, display_name=display_name, tier=tier), token

    def user_by_token(self, token: str) -> Optional[User]:
        """Hash lookup; None for unknown or revoked tokens."""
        if not isinstance(token, str) or not token:
            return None
        token_hash = crypto.hash_api_token(token)
        with self._lock:
            row = self._one(
                "SELECT u.* FROM api_tokens t JOIN users u ON u.id = t.user_id "
                "WHERE t.token_hash = ? AND t.revoked_at IS NULL",
                (token_hash,),
            )
        return self._user(row) if row is not None else None

    def rotate_token(self, user_id: str) -> str:
        """Revoke all existing tokens of the user and return a new plaintext token."""
        with self._write_txn():
            if self._one("SELECT 1 FROM users WHERE id = ?", (user_id,)) is None:
                raise _not_found()
            self._conn.execute(
                "UPDATE api_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (self._now(), user_id),
            )
            token = self._insert_token(user_id)
            self._audit_row(user_id, "token.rotate", user_id, None)
        return token

    def set_tier(self, user_id: str, tier: Tier) -> User:
        tier = Tier(tier)
        with self._write_txn():
            row = self._one("SELECT * FROM users WHERE id = ?", (user_id,))
            if row is None:
                raise _not_found()
            self._conn.execute("UPDATE users SET tier = ? WHERE id = ?", (tier.value, user_id))
            self._audit_row(user_id, "user.tier", user_id, {"from": row["tier"], "to": tier.value})
        return User(id=user_id, display_name=row["display_name"], tier=tier)

    def get_user(self, user_id: str) -> Optional[User]:
        with self._lock:
            row = self._one("SELECT * FROM users WHERE id = ?", (user_id,))
        return self._user(row) if row is not None else None

    # -- subbrains --------------------------------------------------------
    def add_subbrain_version(
        self, owner_id: str, document: SubbrainDocument, content_hash: str, *, subbrain_id: Optional[str] = None
    ) -> SubbrainVersion:
        """New subbrain (private) when subbrain_id is None; else a new version of the owner's subbrain
        (visibility and published_version unchanged). NOT_FOUND if subbrain_id is not the owner's."""
        now = self._now()
        with self._write_txn():
            if self._one("SELECT 1 FROM users WHERE id = ?", (owner_id,)) is None:
                raise _not_found()
            if subbrain_id is None:
                sid, version = _new_id("sb_"), 1
                self._conn.execute(
                    "INSERT INTO subbrains (id, owner_id, visibility, published_version, created_at, updated_at) "
                    "VALUES (?, ?, ?, NULL, ?, ?)",
                    (sid, owner_id, Visibility.PRIVATE.value, now, now),
                )
            else:
                sb = self._one("SELECT owner_id FROM subbrains WHERE id = ?", (subbrain_id,))
                if sb is None or sb["owner_id"] != owner_id:
                    raise _not_found()
                sid, version = subbrain_id, self._latest_version(subbrain_id) + 1
                self._conn.execute("UPDATE subbrains SET updated_at = ? WHERE id = ?", (now, sid))
            self._conn.execute(
                "INSERT INTO subbrain_versions (subbrain_id, version, document_json, content_hash, title, "
                "domains_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    version,
                    document.model_dump_json(),
                    content_hash,
                    document.title,
                    _dumps(list(document.domains)),
                    now,
                ),
            )
            self._audit_row(owner_id, "subbrain.import", sid, {"version": version, "content_hash": content_hash})
            result = self._version(self._subbrain_row(sid), version)
        assert result is not None
        return result

    def set_visibility(
        self,
        owner_id: str,
        subbrain_id: str,
        visibility: Visibility,
        *,
        version: Optional[int] = None,
        confirm_hash: Optional[str] = None,
        max_public: Optional[int] = None,
    ) -> SubbrainSummary:
        """PUBLIC requires confirm_hash == content_hash of `version` (default latest) else CONFIRMATION_MISMATCH;
        sets published_version = version. PRIVATE keeps published_version (data retained). Audit-logged.

        max_public (MUST-T1): when a private subbrain goes public and the owner already has max_public public
        subbrains, LIMIT_EXCEEDED. Counted in the same write transaction as the update (atomic across processes);
        re-publishing an already public subbrain is not counted."""
        visibility = Visibility(visibility)
        with self._write_txn():
            sb = self._subbrain_row(subbrain_id)
            if sb is None or sb["owner_id"] != owner_id:
                raise _not_found()
            now = self._now()
            if visibility == Visibility.PUBLIC:
                if max_public is not None and sb["visibility"] != Visibility.PUBLIC.value:
                    current = self._count_public(owner_id)
                    if current >= max_public:
                        raise OpenCanalError(
                            ErrorCode.LIMIT_EXCEEDED, PUBLIC_SUBBRAIN_LIMIT_MESSAGE, limit=max_public, current=current
                        )
                target = version if version is not None else self._latest_version(subbrain_id)
                row = self._one(
                    "SELECT content_hash FROM subbrain_versions WHERE subbrain_id = ? AND version = ?",
                    (subbrain_id, target),
                )
                if row is None:
                    raise _not_found()
                if not isinstance(confirm_hash, str) or not hmac.compare_digest(
                    confirm_hash.encode("utf-8"), row["content_hash"].encode("utf-8")
                ):
                    # Never echo the stored hash: the caller must have seen the preview.
                    raise OpenCanalError(
                        ErrorCode.CONFIRMATION_MISMATCH,
                        "confirm_hash does not match the previewed content_hash of this version",
                    )
                self._conn.execute(
                    "UPDATE subbrains SET visibility = ?, published_version = ?, updated_at = ? WHERE id = ?",
                    (Visibility.PUBLIC.value, target, now, subbrain_id),
                )
                detail: dict[str, Any] = {"from": sb["visibility"], "to": "public", "version": target}
            else:
                self._conn.execute(
                    "UPDATE subbrains SET visibility = ?, updated_at = ? WHERE id = ?",
                    (Visibility.PRIVATE.value, now, subbrain_id),
                )
                detail = {"from": sb["visibility"], "to": "private"}
            self._audit_row(owner_id, "subbrain.visibility", subbrain_id, detail)
            return self._summary(self._subbrain_row(subbrain_id))

    def _count_public(self, owner_id: str) -> int:
        row = self._one(
            "SELECT COUNT(*) AS n FROM subbrains WHERE owner_id = ? AND visibility = ?",
            (owner_id, Visibility.PUBLIC.value),
        )
        return int(row["n"])

    def count_public_subbrains(self, owner_id: str) -> int:
        with self._lock:
            return self._count_public(owner_id)

    def list_subbrains_for_owner(self, owner_id: str) -> list[SubbrainSummary]:
        """Owner sees all of their subbrains, public and private."""
        with self._lock:
            rows = self._all(
                "SELECT s.*, u.display_name AS owner_display FROM subbrains s JOIN users u ON u.id = s.owner_id "
                "WHERE s.owner_id = ? ORDER BY s.rowid",
                (owner_id,),
            )
            return [self._summary(r) for r in rows]

    def get_subbrain_for_viewer(self, viewer_id: str, subbrain_id: str, version: Optional[int] = None) -> SubbrainVersion:
        """Owner: any version (default latest). Others: only public subbrains, only published_version."""
        with self._lock:
            sb = self._subbrain_row(subbrain_id)
            if sb is None:
                raise _not_found()
            if sb["owner_id"] == viewer_id:
                target = version if version is not None else self._latest_version(subbrain_id)
            else:
                published = sb["published_version"]
                if sb["visibility"] != Visibility.PUBLIC.value or published is None:
                    raise _not_found()
                if version is not None and version != published:
                    raise _not_found()
                target = published
            result = self._version(sb, target)
        if result is None:
            raise _not_found()
        return result

    def list_public_versions(self, *, exclude_owner_id: Optional[str] = None) -> list[SubbrainVersion]:
        """Published version of every public subbrain, optionally excluding one owner."""
        with self._lock:
            rows = self._all(
                "SELECT s.*, u.display_name AS owner_display FROM subbrains s JOIN users u ON u.id = s.owner_id "
                "WHERE s.visibility = ? AND s.published_version IS NOT NULL ORDER BY s.id",
                (Visibility.PUBLIC.value,),
            )
            out: list[SubbrainVersion] = []
            for sb in rows:
                if exclude_owner_id is not None and sb["owner_id"] == exclude_owner_id:
                    continue
                v = self._version(sb, sb["published_version"])
                if v is not None:
                    out.append(v)
        return out

    # -- canals -----------------------------------------------------------
    def create_canal(
        self,
        host_user_id: str,
        host_subbrain_id: str,
        host_version: int,
        query: str,
        query_mode_used: QueryMode,
        members: list[CanalMember],
        *,
        canals_per_month: Optional[int] = None,
    ) -> Canal:
        """canals_per_month (MUST-T1): LIMIT_EXCEEDED when the host already created that many canals in the
        UTC month of this canal's created_at. Counted in the same write transaction as the insert, so processes
        sharing the DB cannot both pass the check (TIER-1)."""
        canal_id = _new_id("cn_")
        mode = QueryMode(query_mode_used)
        with self._write_txn():
            host = self._one("SELECT owner_id FROM subbrains WHERE id = ?", (host_subbrain_id,))
            if host is None or host["owner_id"] != host_user_id:
                raise _not_found()
            pinned = [(host_subbrain_id, host_version)] + [(m.subbrain_id, m.version) for m in members]
            for sid, ver in pinned:
                if self._one(
                    "SELECT 1 FROM subbrain_versions WHERE subbrain_id = ? AND version = ?", (sid, ver)
                ) is None:
                    raise _not_found()
            now = self._now()
            if canals_per_month is not None:
                month = now[:7]
                used = self._count_canals(host_user_id, month)
                if used >= canals_per_month:
                    raise OpenCanalError(
                        ErrorCode.LIMIT_EXCEEDED,
                        MONTHLY_CANAL_LIMIT_MESSAGE,
                        limit=canals_per_month,
                        current=used,
                        month=month,
                    )
            self._conn.execute(
                "INSERT INTO canals (id, host_user_id, host_subbrain_id, host_version, query, query_mode_used, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (canal_id, host_user_id, host_subbrain_id, host_version, query, mode.value, now),
            )
            for m in members:
                # owner_id is stored as of canal creation: the participant set never shrinks (NEVER-02).
                owner = self._one("SELECT owner_id FROM subbrains WHERE id = ?", (m.subbrain_id,))
                self._conn.execute(
                    "INSERT INTO canal_members (canal_id, subbrain_id, version, owner_id, relevance, distance, "
                    "matched_terms_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        canal_id,
                        m.subbrain_id,
                        m.version,
                        owner["owner_id"],
                        float(m.relevance),
                        float(m.distance),
                        _dumps(list(m.matched_terms)),
                    ),
                )
            self._audit_row(
                host_user_id,
                "canal.open",
                canal_id,
                {
                    "host_subbrain_id": host_subbrain_id,
                    "host_version": host_version,
                    "query_mode_used": mode.value,
                    "members": [m.subbrain_id for m in members],
                },
            )
            canal = self._canal(canal_id)
        assert canal is not None
        return canal

    def withheld_ref(self, canal_id: str, subbrain_id: str) -> str:
        """Opaque per-canal handle shown instead of the ids of a subbrain withheld from a viewer (NEVER-11 v.5).
        Same subbrain in the same canal -> same ref; another canal -> an unrelated ref."""
        return crypto.withheld_ref(self._master_key, canal_id, subbrain_id)

    def get_canal_for_viewer(self, viewer_id: str, canal_id: str) -> Canal:
        """Participants only (host + member owners). NOT_FOUND otherwise."""
        with self._lock:
            canal = self._canal(canal_id)
        if canal is None or viewer_id not in canal.participant_ids:
            raise _not_found()
        return canal

    def canal_context(self, canal_id: str) -> CanalContext:
        """Internal (validator). Includes host + members whose subbrain is currently PUBLIC."""
        with self._lock:
            canal = self._canal(canal_id)
            if canal is None:
                raise _not_found()
            subbrains: dict[tuple[str, int], SubbrainVersion] = {}
            host_sb = self._subbrain_row(canal.host_subbrain_id)
            host_v = self._version(host_sb, canal.host_version) if host_sb is not None else None
            if host_v is None:
                raise _not_found()
            subbrains[(host_v.subbrain_id, host_v.version)] = host_v
            for m in canal.members:
                sb = self._subbrain_row(m.subbrain_id)
                if sb is None or sb["visibility"] != Visibility.PUBLIC.value:
                    continue
                v = self._version(sb, m.version)  # pinned version, never latest
                if v is not None:
                    subbrains[(v.subbrain_id, v.version)] = v
        return CanalContext(
            canal_id=canal.id,
            host_subbrain_id=canal.host_subbrain_id,
            host_version=canal.host_version,
            host_owner_id=canal.host_user_id,
            subbrains=subbrains,
        )

    def count_canals_in_month(self, user_id: str, month: str) -> int:
        """month = "YYYY-MM" (UTC) of created_at."""
        if not _MONTH_RE.match(month or ""):
            raise ValueError("month must be YYYY-MM")
        with self._lock:
            return self._count_canals(user_id, month)

    def _count_canals(self, user_id: str, month: str) -> int:
        row = self._one(
            "SELECT COUNT(*) AS n FROM canals WHERE host_user_id = ? AND substr(created_at, 1, 7) = ?",
            (user_id, month),
        )
        return int(row["n"])

    # -- deltabrains ------------------------------------------------------
    def save_deltabrain(
        self, canal_id: str, submitted_by: str, submission: DeltabrainSubmission, stats: DeltabrainStats
    ) -> DeltabrainRecord:
        deltabrain_id = _new_id("db_")
        with self._write_txn():
            if self._one("SELECT 1 FROM canals WHERE id = ?", (canal_id,)) is None:
                raise _not_found()
            self._conn.execute(
                "INSERT INTO deltabrains (id, canal_id, submitted_by, submission_json, stats_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (deltabrain_id, canal_id, submitted_by, submission.model_dump_json(), stats.model_dump_json(),
                 self._now()),
            )
            self._audit_row(
                submitted_by,
                "deltabrain.submit",
                deltabrain_id,
                {"canal_id": canal_id, "node_count": stats.node_count, "edge_count": stats.edge_count,
                 "emergent_edge_count": len(stats.emergent_edge_ids)},
            )
            row = self._one("SELECT * FROM deltabrains WHERE id = ?", (deltabrain_id,))
        return self._record(row)

    def _viewer_identities(
        self, viewer_id: str, deltabrain_id: str, submission: DeltabrainSubmission
    ) -> dict[str, tuple[dict[str, Any], Optional[_IdentityKey]]]:
        """Owner of every subbrain the submission cites, as shown to viewer_id (NEVER-11), with the key that
        owner is counted under for this viewer (None: no such subbrain). Plain when the subbrain is public or the
        viewer owns it; else "비공개 기여자" + the per-deltabrain contributor token. Caller holds self._lock."""
        cited = {ref.subbrain_id for item in (*submission.nodes, *submission.edges) for ref in item.provenance}
        tokens: dict[str, str] = {}
        out: dict[str, tuple[dict[str, Any], Optional[_IdentityKey]]] = {}
        for sid in sorted(cited):
            sb = self._subbrain_row(sid)
            if sb is not None and (sb["visibility"] == Visibility.PUBLIC.value or sb["owner_id"] == viewer_id):
                ident: dict[str, Any] = {"owner_id": sb["owner_id"], "owner_display": sb["owner_display"]}
                out[sid] = (ident, ("plain", sb["owner_id"]))
                continue
            token = None
            if sb is not None:
                owner_id = sb["owner_id"]
                if owner_id not in tokens:
                    tokens[owner_id] = crypto.contributor_token(self._master_key, owner_id, deltabrain_id)
                token = tokens[owner_id]
            ident = {"owner_id": None, "owner_display": MASKED_DISPLAY, "owner_token": token}
            out[sid] = (ident, ("masked", token) if token is not None else None)
        return out

    @staticmethod
    def _keys(idents: Mapping[str, tuple[dict[str, Any], Optional[_IdentityKey]]]) -> dict[str, Optional[_IdentityKey]]:
        return {sid: key for sid, (_, key) in idents.items()}

    def get_deltabrain_for_viewer(self, viewer_id: str, deltabrain_id: str) -> dict[str, Any]:
        """Participants only. Returns a JSON-ready view in which every provenance ref carries
        owner info: {"owner_id", "owner_display"} when the cited subbrain is public or the viewer is
        its owner, else {"owner_id": None, "owner_display": "비공개 기여자",
        "owner_token": crypto.contributor_token(master_key, owner_id, deltabrain_id)} (NEVER-11).
        Retained content (labels/summaries) stays visible to participants (NEVER-02).

        "stats" is computed over the identities shown to this viewer (ORACLE v.4 NEVER-11, `_viewer_stats`):
        emergent edges, host-touching edges and owners_involved never reveal whether a masked contributor is
        one of the plainly shown owners. The stored record keeps the true stats.

        No real id of a masked subbrain appears anywhere (NEVER-11 v.5): masked refs carry null
        subbrain_id/version/node_id, and "host_subbrain_id" is null when the host is masked for this viewer."""
        with self._lock:
            row = self._one("SELECT * FROM deltabrains WHERE id = ?", (deltabrain_id,))
            canal = self._canal(row["canal_id"]) if row is not None else None
            if row is None or canal is None or viewer_id not in canal.participant_ids:
                raise _not_found()
            record = self._record(row)
            idents = self._viewer_identities(viewer_id, deltabrain_id, record.submission)
            host_sb = self._subbrain_row(canal.host_subbrain_id)
        # NEVER-11 v.5: a host now private is masked like any other contributor, top-level id included.
        host_shown = host_sb is not None and (
            host_sb["visibility"] == Visibility.PUBLIC.value or host_sb["owner_id"] == viewer_id
        )
        stats = _viewer_stats(
            record.submission, record.stats, (canal.host_subbrain_id, canal.host_version), self._keys(idents)
        )
        contributors: dict[_IdentityKey | tuple[str, None], dict[str, Any]] = {}

        def annotate(refs: list[Any]) -> list[dict[str, Any]]:
            out = []
            for ref in refs:
                ident, key = idents[ref.subbrain_id]
                # One contributor entry per displayed identity, so a masked owner never collapses into a
                # plainly listed one (that would let viewers infer who the masked contributor is).
                contributors.setdefault(key or ("masked", None), dict(ident))
                if ident["owner_id"] is None:
                    out.append({"subbrain_id": None, "version": None, "node_id": None, **ident})
                else:
                    out.append({"subbrain_id": ref.subbrain_id, "version": ref.version, "node_id": ref.node_id,
                                **ident})
            return out

        nodes = []
        for node in record.submission.nodes:
            item = node.model_dump(mode="json")
            item["provenance"] = annotate(node.provenance)
            nodes.append(item)
        edges = []
        for edge in record.submission.edges:
            item = edge.model_dump(mode="json")
            item["provenance"] = annotate(edge.provenance)
            edges.append(item)

        return {
            "id": record.id,
            "canal_id": record.canal_id,
            "query": canal.query,
            "host_subbrain_id": canal.host_subbrain_id if host_shown else None,
            "created_at": record.created_at,
            "synthesizer": record.submission.synthesizer.model_dump(mode="json"),
            "stats": stats.model_dump(mode="json"),
            "nodes": nodes,
            "edges": edges,
            "contributors": list(contributors.values()),
        }

    def list_deltabrains_for_viewer(self, viewer_id: str) -> list[dict[str, Any]]:
        """Summaries of deltabrains of canals the viewer participates in. Counts are the viewer's own
        (same `_viewer_stats` as get_deltabrain_for_viewer, NEVER-11)."""
        out = []
        with self._lock:
            rows = self._all(
                "SELECT d.id, d.canal_id, d.submission_json, d.stats_json, d.created_at, c.query, c.host_user_id, "
                "c.host_subbrain_id, c.host_version "
                "FROM deltabrains d JOIN canals c ON c.id = d.canal_id "
                "WHERE c.host_user_id = ? OR EXISTS "
                "(SELECT 1 FROM canal_members m WHERE m.canal_id = c.id AND m.owner_id = ?) "
                "ORDER BY d.rowid",
                (viewer_id, viewer_id),
            )
            for r in rows:
                submission = DeltabrainSubmission.model_validate_json(r["submission_json"])
                idents = self._viewer_identities(viewer_id, r["id"], submission)
                stats = _viewer_stats(
                    submission,
                    DeltabrainStats.model_validate_json(r["stats_json"]),
                    (r["host_subbrain_id"], r["host_version"]),
                    self._keys(idents),
                )
                out.append(
                    {
                        "id": r["id"],
                        "canal_id": r["canal_id"],
                        "query": r["query"],
                        "created_at": r["created_at"],
                        "is_host": r["host_user_id"] == viewer_id,
                        "stats": {
                            "node_count": stats.node_count,
                            "edge_count": stats.edge_count,
                            "emergent_edge_count": len(stats.emergent_edge_ids),
                        },
                    }
                )
        return out

    def get_deltabrain_record(self, deltabrain_id: str) -> DeltabrainRecord:
        """Internal only (no visibility check). Never call from a tool handler without a participant check."""
        with self._lock:
            row = self._one("SELECT * FROM deltabrains WHERE id = ?", (deltabrain_id,))
        if row is None:
            raise _not_found()
        return self._record(row)

    def rate_edge(self, rating: EdgeRating, deltabrain_id: str) -> None:
        """Upsert one rater's labels for one edge. Caller (service) checks participant + emergent edge."""
        with self._write_txn():
            if self._one("SELECT 1 FROM deltabrains WHERE id = ?", (deltabrain_id,)) is None:
                raise _not_found()
            self._conn.execute(
                "INSERT INTO edge_ratings (deltabrain_id, edge_id, rater_id, novelty, validity, usefulness, rated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (deltabrain_id, edge_id, rater_id) DO UPDATE SET "
                "novelty = excluded.novelty, validity = excluded.validity, usefulness = excluded.usefulness, "
                "rated_at = excluded.rated_at",
                (deltabrain_id, rating.edge_id, rating.rater_id, rating.novelty, rating.validity, rating.usefulness,
                 self._now()),
            )

    def ratings_for(self, deltabrain_id: str) -> list[EdgeRating]:
        with self._lock:
            rows = self._all("SELECT * FROM edge_ratings WHERE deltabrain_id = ? ORDER BY rowid", (deltabrain_id,))
        return [
            EdgeRating(
                edge_id=r["edge_id"],
                rater_id=r["rater_id"],
                novelty=r["novelty"],
                validity=r["validity"],
                usefulness=r["usefulness"],
            )
            for r in rows
        ]

    # -- audit / backup ---------------------------------------------------
    def audit(self, actor: str, action: str, target: str, detail: Optional[dict[str, Any]] = None) -> None:
        with self._write_txn():
            self._audit_row(actor, action, target, detail)

    def snapshot_bytes(self) -> bytes:
        """Consistent, self-contained copy of the whole DB as bytes (sqlite backup API).

        MUST-E3 (v.6): the copy is made in memory, so no plaintext copy of the DB is written to disk. Only an SQLite
        without the serialize API goes through a temp file, 0600 in a 0700 directory, removed whatever happens."""
        with self._lock:
            image = _backup_in_memory(self._conn) if _CAN_SERIALIZE else _backup_via_private_file(self._conn)
        return _self_contained_image(image)

    @staticmethod
    def restore_bytes(db_path: Path | str, data: bytes) -> None:
        """Write `data` as a new DB file (mode 0600) at db_path.

        Refuses with FileExistsError naming the file when db_path or any SQLite sidecar of it (<db>-wal, <db>-shm,
        <db>-journal) exists: SQLite would replay a stale sidecar on top of the restored image and silently
        bring back post-backup writes or corrupt it (CRY-1). The image goes to a temp file in the same directory,
        is fsynced, then hard-linked into place (never replaces an existing file), so a crash cannot leave a
        partial DB at db_path. The temp file is 0600 from creation (mkstemp, whatever the umask) and is removed on
        success and on failure (MUST-E3 v.6)."""
        path = Path(db_path)
        for candidate in (path, *(path.with_name(path.name + suffix) for suffix in _SQLITE_SIDECARS)):
            if os.path.lexists(candidate):
                raise _exists_error(candidate)
        if not data.startswith(_SQLITE_MAGIC):
            raise ValueError("not a SQLite database image")
        crypto.make_private_dirs(path.parent)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".restoring")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, 0o600)
            try:
                os.link(tmp, path)
            except FileExistsError:
                raise _exists_error(path) from None
            except OSError:
                # No hard links on this filesystem. rename() is atomic too but replaces, so check again first.
                if os.path.lexists(path):
                    raise _exists_error(path) from None
                os.rename(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
        _fsync_dir(path.parent)
