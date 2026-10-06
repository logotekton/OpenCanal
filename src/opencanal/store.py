"""SQLite persistence with viewer-scoped accessors (ORACLE §5.5).

Owner: Builder ST. Every read that a tool can reach goes through a *_for_viewer / *_for_owner
method that enforces visibility. "Missing" and "not visible to you" both raise
OpenCanalError(NOT_FOUND) with the same message (no existence leak).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .models import (
    Canal,
    CanalContext,
    CanalMember,
    DeltabrainRecord,
    DeltabrainStats,
    DeltabrainSubmission,
    EdgeRating,
    QueryMode,
    SubbrainDocument,
    SubbrainSummary,
    SubbrainVersion,
    Tier,
    User,
    Visibility,
)


class Store:
    def __init__(self, db_path: Path | str, *, master_key: bytes) -> None:
        """Open/create the SQLite DB (":memory:" allowed) and create tables if missing."""
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    # -- users / tokens ---------------------------------------------------
    def create_user(self, display_name: str, tier: Tier, *, user_id: Optional[str] = None) -> tuple[User, str]:
        """Create a user and return (user, plaintext_token). Only the token hash is stored."""
        raise NotImplementedError

    def user_by_token(self, token: str) -> Optional[User]:
        """Hash lookup; None for unknown or revoked tokens."""
        raise NotImplementedError

    def rotate_token(self, user_id: str) -> str:
        """Revoke all existing tokens of the user and return a new plaintext token."""
        raise NotImplementedError

    def set_tier(self, user_id: str, tier: Tier) -> User:
        raise NotImplementedError

    def get_user(self, user_id: str) -> Optional[User]:
        raise NotImplementedError

    # -- subbrains --------------------------------------------------------
    def add_subbrain_version(
        self, owner_id: str, document: SubbrainDocument, content_hash: str, *, subbrain_id: Optional[str] = None
    ) -> SubbrainVersion:
        """New subbrain (private) when subbrain_id is None; else a new version of the owner's subbrain
        (visibility and published_version unchanged). NOT_FOUND if subbrain_id is not the owner's."""
        raise NotImplementedError

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
        raise NotImplementedError

    def count_public_subbrains(self, owner_id: str) -> int:
        raise NotImplementedError

    def list_subbrains_for_owner(self, owner_id: str) -> list[SubbrainSummary]:
        """Owner sees all of their subbrains, public and private."""
        raise NotImplementedError

    def get_subbrain_for_viewer(self, viewer_id: str, subbrain_id: str, version: Optional[int] = None) -> SubbrainVersion:
        """Owner: any version (default latest). Others: only public subbrains, only published_version."""
        raise NotImplementedError

    def list_public_versions(self, *, exclude_owner_id: Optional[str] = None) -> list[SubbrainVersion]:
        """Published version of every public subbrain, optionally excluding one owner."""
        raise NotImplementedError

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
        raise NotImplementedError

    def get_canal_for_viewer(self, viewer_id: str, canal_id: str) -> Canal:
        """Participants only (host + member owners). NOT_FOUND otherwise."""
        raise NotImplementedError

    def canal_context(self, canal_id: str) -> CanalContext:
        """Internal (validator). Includes host + members whose subbrain is currently PUBLIC."""
        raise NotImplementedError

    def count_canals_in_month(self, user_id: str, month: str) -> int:
        """month = "YYYY-MM" (UTC) of created_at."""
        raise NotImplementedError

    # -- deltabrains ------------------------------------------------------
    def save_deltabrain(
        self, canal_id: str, submitted_by: str, submission: DeltabrainSubmission, stats: DeltabrainStats
    ) -> DeltabrainRecord:
        raise NotImplementedError

    def get_deltabrain_for_viewer(self, viewer_id: str, deltabrain_id: str) -> dict[str, Any]:
        """Participants only. Returns a JSON-ready view in which every provenance ref carries
        owner info: {"owner_id", "owner_display"} when the cited subbrain is public or the viewer is
        its owner, else {"owner_id": None, "owner_display": "비공개 기여자",
        "owner_token": crypto.contributor_token(master_key, owner_id, deltabrain_id)} (NEVER-11).
        Retained content (labels/summaries) stays visible to participants (NEVER-02)."""
        raise NotImplementedError

    def list_deltabrains_for_viewer(self, viewer_id: str) -> list[dict[str, Any]]:
        """Summaries of deltabrains of canals the viewer participates in."""
        raise NotImplementedError

    def get_deltabrain_record(self, deltabrain_id: str) -> DeltabrainRecord:
        """Internal only (no visibility check). Never call from a tool handler without a participant check."""
        raise NotImplementedError

    def rate_edge(self, rating: EdgeRating, deltabrain_id: str) -> None:
        """Upsert one rater's labels for one edge. Caller (service) checks participant + emergent edge."""
        raise NotImplementedError

    def ratings_for(self, deltabrain_id: str) -> list[EdgeRating]:
        raise NotImplementedError

    # -- audit / backup ---------------------------------------------------
    def audit(self, actor: str, action: str, target: str, detail: Optional[dict[str, Any]] = None) -> None:
        raise NotImplementedError

    def snapshot_bytes(self) -> bytes:
        """Consistent copy of the whole DB as bytes (sqlite backup API)."""
        raise NotImplementedError

    @staticmethod
    def restore_bytes(db_path: Path | str, data: bytes) -> None:
        """Write `data` as the DB file at db_path (refuse to overwrite an existing file)."""
        raise NotImplementedError
