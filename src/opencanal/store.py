"""SQLite persistence with viewer-scoped accessors (ORACLE §5.5).

Owner: Builder ST. Every read that a tool can reach goes through a *_for_viewer / *_for_owner
method that enforces visibility. "Missing" and "not visible to you" both raise
OpenCanalError(NOT_FOUND) with the same message (no existence leak).

There are no delete methods for user data (NEVER-03, D-005): subbrains only switch between
public and private, and every version / canal / deltabrain row is kept.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import sqlite3
import tempfile
import threading
from collections.abc import Callable, Iterable
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
_SQLITE_MAGIC = b"SQLite format 3\x00"
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

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
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys=ON")
            if not self._is_memory:
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

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
        """Create a user and return (user, plaintext_token). Only the token hash is stored."""
        uid = user_id or _new_id("u_")
        tier = Tier(tier)
        with self._lock, self._conn:
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
        with self._lock, self._conn:
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
        with self._lock, self._conn:
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
        with self._lock, self._conn:
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
    ) -> SubbrainSummary:
        """PUBLIC requires confirm_hash == content_hash of `version` (default latest) else CONFIRMATION_MISMATCH;
        sets published_version = version. PRIVATE keeps published_version (data retained). Audit-logged."""
        visibility = Visibility(visibility)
        with self._lock, self._conn:
            sb = self._subbrain_row(subbrain_id)
            if sb is None or sb["owner_id"] != owner_id:
                raise _not_found()
            now = self._now()
            if visibility == Visibility.PUBLIC:
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

    def count_public_subbrains(self, owner_id: str) -> int:
        with self._lock:
            row = self._one(
                "SELECT COUNT(*) AS n FROM subbrains WHERE owner_id = ? AND visibility = ?",
                (owner_id, Visibility.PUBLIC.value),
            )
        return int(row["n"])

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
    ) -> Canal:
        canal_id = _new_id("cn_")
        mode = QueryMode(query_mode_used)
        with self._lock, self._conn:
            host = self._one("SELECT owner_id FROM subbrains WHERE id = ?", (host_subbrain_id,))
            if host is None or host["owner_id"] != host_user_id:
                raise _not_found()
            pinned = [(host_subbrain_id, host_version)] + [(m.subbrain_id, m.version) for m in members]
            for sid, ver in pinned:
                if self._one(
                    "SELECT 1 FROM subbrain_versions WHERE subbrain_id = ? AND version = ?", (sid, ver)
                ) is None:
                    raise _not_found()
            self._conn.execute(
                "INSERT INTO canals (id, host_user_id, host_subbrain_id, host_version, query, query_mode_used, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (canal_id, host_user_id, host_subbrain_id, host_version, query, mode.value, self._now()),
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
        with self._lock, self._conn:
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

    def get_deltabrain_for_viewer(self, viewer_id: str, deltabrain_id: str) -> dict[str, Any]:
        """Participants only. Returns a JSON-ready view in which every provenance ref carries
        owner info: {"owner_id", "owner_display"} when the cited subbrain is public or the viewer is
        its owner, else {"owner_id": None, "owner_display": "비공개 기여자",
        "owner_token": crypto.contributor_token(master_key, owner_id, deltabrain_id)} (NEVER-11).
        Retained content (labels/summaries) stays visible to participants (NEVER-02)."""
        with self._lock:
            row = self._one("SELECT * FROM deltabrains WHERE id = ?", (deltabrain_id,))
            canal = self._canal(row["canal_id"]) if row is not None else None
            if row is None or canal is None or viewer_id not in canal.participant_ids:
                raise _not_found()
            record = self._record(row)
            cited = {ref.subbrain_id for n in record.submission.nodes for ref in n.provenance}
            cited |= {ref.subbrain_id for e in record.submission.edges for ref in e.provenance}
            owners: dict[str, sqlite3.Row] = {}
            for sid in sorted(cited):
                sb = self._subbrain_row(sid)
                if sb is not None:
                    owners[sid] = sb

        tokens: dict[str, str] = {}
        contributors: dict[tuple[Any, ...], dict[str, Any]] = {}

        def identity(sid: str) -> dict[str, Any]:
            sb = owners.get(sid)
            if sb is not None and (sb["visibility"] == Visibility.PUBLIC.value or sb["owner_id"] == viewer_id):
                ident: dict[str, Any] = {"owner_id": sb["owner_id"], "owner_display": sb["owner_display"]}
                key: tuple[Any, ...] = ("plain", sb["owner_id"])
            else:
                token = None
                if sb is not None:
                    owner_id = sb["owner_id"]
                    if owner_id not in tokens:
                        tokens[owner_id] = crypto.contributor_token(self._master_key, owner_id, deltabrain_id)
                    token = tokens[owner_id]
                ident = {"owner_id": None, "owner_display": MASKED_DISPLAY, "owner_token": token}
                key = ("masked", token)
            # One contributor entry per displayed identity, so a masked owner never collapses into a
            # plainly listed one (that would let viewers infer who the masked contributor is).
            contributors.setdefault(key, dict(ident))
            return ident

        def annotate(refs: list[Any]) -> list[dict[str, Any]]:
            out = []
            for ref in refs:
                ident = identity(ref.subbrain_id)
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
            "host_subbrain_id": canal.host_subbrain_id,
            "created_at": record.created_at,
            "synthesizer": record.submission.synthesizer.model_dump(mode="json"),
            "stats": record.stats.model_dump(mode="json"),
            "nodes": nodes,
            "edges": edges,
            "contributors": list(contributors.values()),
        }

    def list_deltabrains_for_viewer(self, viewer_id: str) -> list[dict[str, Any]]:
        """Summaries of deltabrains of canals the viewer participates in."""
        with self._lock:
            rows = self._all(
                "SELECT d.id, d.canal_id, d.stats_json, d.created_at, c.query, c.host_user_id "
                "FROM deltabrains d JOIN canals c ON c.id = d.canal_id "
                "WHERE c.host_user_id = ? OR EXISTS "
                "(SELECT 1 FROM canal_members m WHERE m.canal_id = c.id AND m.owner_id = ?) "
                "ORDER BY d.rowid",
                (viewer_id, viewer_id),
            )
        out = []
        for r in rows:
            stats = DeltabrainStats.model_validate_json(r["stats_json"])
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
        with self._lock, self._conn:
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
        with self._lock, self._conn:
            self._audit_row(actor, action, target, detail)

    def snapshot_bytes(self) -> bytes:
        """Consistent copy of the whole DB as bytes (sqlite backup API)."""
        with self._lock, tempfile.TemporaryDirectory(prefix="opencanal-snap-") as tmp:
            dest_path = os.path.join(tmp, "snapshot.db")
            dest = sqlite3.connect(dest_path)
            try:
                self._conn.backup(dest)
                # Make the copy self-contained (no -wal sidecar) before reading it back.
                dest.execute("PRAGMA journal_mode=DELETE")
                dest.commit()
            finally:
                dest.close()
            return Path(dest_path).read_bytes()

    @staticmethod
    def restore_bytes(db_path: Path | str, data: bytes) -> None:
        """Write `data` as the DB file at db_path (refuse to overwrite an existing file)."""
        path = Path(db_path)
        if path.exists():
            raise FileExistsError(str(path))
        if not data.startswith(_SQLITE_MAGIC):
            raise ValueError("not a SQLite database image")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
