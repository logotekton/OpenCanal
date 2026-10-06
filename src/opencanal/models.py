"""Shared data contract for opencanal v0.

This module is the contract every other module codes against
(tasks/TASK-001.md). Field names and error codes here are referenced by
docs/oracle/ORACLE_MANIFEST.md; change them only through a TASK + Oracle update.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums and codes
# ---------------------------------------------------------------------------


class Tier(str, Enum):
    FREE = "free"
    PRO = "pro"
    EXPERT = "expert"


class Visibility(str, Enum):
    PRIVATE = "private"  # 비공개 — default right after import
    PUBLIC = "public"  # 공개


class QueryMode(str, Enum):
    AUTO = "auto"  # topic if the query has content terms, else whole_host
    TOPIC = "topic"
    WHOLE_HOST = "whole_host"


class NodeKind(str, Enum):
    QUERY = "query"
    SOURCE = "source"
    NEW = "new"


class ErrorCode(str, Enum):
    """Tool-level error codes (returned as {"ok": false, "error": {"code": ...}})."""

    UNAUTHORIZED = "UNAUTHORIZED"
    TIER_FORBIDDEN = "TIER_FORBIDDEN"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    IMPORT_INVALID = "IMPORT_INVALID"
    NOT_FOUND = "NOT_FOUND"  # also used for "exists but not visible to you" (no existence leak)
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    CONFIRMATION_MISMATCH = "CONFIRMATION_MISMATCH"
    HOST_NOT_PUBLIC = "HOST_NOT_PUBLIC"
    NOT_CANAL_HOST = "NOT_CANAL_HOST"
    NO_RELEVANT_SUBBRAIN = "NO_RELEVANT_SUBBRAIN"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    NOT_EMERGENT_EDGE = "NOT_EMERGENT_EDGE"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    INTERNAL = "INTERNAL"  # unexpected server error; never carries internals (ORACLE §9, v.3)


class ViolationCode(str, Enum):
    """Deltabrain L1 validation codes (ORACLE §5.1)."""

    SCHEMA_INVALID = "SCHEMA_INVALID"
    PROVENANCE_MISSING = "PROVENANCE_MISSING"
    PROVENANCE_OUT_OF_CANAL = "PROVENANCE_OUT_OF_CANAL"
    PROVENANCE_INVALID = "PROVENANCE_INVALID"
    QUERY_NODE_COUNT = "QUERY_NODE_COUNT"
    OFF_QUERY_NODE = "OFF_QUERY_NODE"
    NO_EMERGENCE = "NO_EMERGENCE"
    HOST_NOT_TOUCHED = "HOST_NOT_TOUCHED"
    RELATION_NOT_ALLOWED = "RELATION_NOT_ALLOWED"
    RATIONALE_MISSING = "RATIONALE_MISSING"
    NOT_NOVEL = "NOT_NOVEL"
    GENERIC_LABEL = "GENERIC_LABEL"
    TEMPLATED_RATIONALE = "TEMPLATED_RATIONALE"
    TOO_LARGE = "TOO_LARGE"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"


ALLOWED_RELATIONS: tuple[str, ...] = (
    "applies_to",
    "analogous_to",
    "contradicts",
    "extends",
    "requires",
    "alternative_to",
    "explains",
    "risk_for",
)

# ORACLE §5.1 numeric limits
MAX_DELTA_NODES = 60
MAX_DELTA_EDGES = 120
MAX_QUERY_HOPS = 3
RATIONALE_MIN_CHARS = 40
RATIONALE_MAX_CHARS = 400
TEMPLATED_RATIONALE_MAX_RATIO = 0.2
NEW_NODE_MIN_REFS = 2

# Subbrain limits (DECISIONS D-002, Q2)
SUMMARY_MAX_CHARS = 280
MAX_TAGS_PER_NODE = 20

PROTOCOL_VERSION = "opencanal-synthesis/0.1"


class OpenCanalError(Exception):
    """Raised by store/service code; the service converts it to an error envelope."""

    def __init__(self, code: ErrorCode, message: str = "", **detail: Any) -> None:
        super().__init__(message or code.value)
        self.code = code
        self.message = message or code.value
        self.detail = detail


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class User(BaseModel):
    id: str
    display_name: str
    tier: Tier


# ---------------------------------------------------------------------------
# Subbrains (what users publish)
# ---------------------------------------------------------------------------


class SubbrainNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)
    type: Optional[str] = Field(default=None, max_length=50)
    summary: Optional[str] = Field(default=None, max_length=SUMMARY_MAX_CHARS)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS_PER_NODE)


class SubbrainEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Optional[str] = Field(default=None, max_length=200)
    source: str
    target: str
    relation: Optional[str] = Field(default=None, max_length=50)
    summary: Optional[str] = Field(default=None, max_length=SUMMARY_MAX_CHARS)


class SubbrainDocument(BaseModel):
    """Canonical, sanitized subbrain content (no raw text, no URLs, no paths)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    domains: list[str] = Field(min_length=1, max_length=10)
    nodes: list[SubbrainNode] = Field(min_length=1, max_length=2000)
    edges: list[SubbrainEdge] = Field(default_factory=list, max_length=5000)


class Redaction(BaseModel):
    """One thing the sanitizer removed or masked (reported back on import)."""

    location: str  # e.g. "nodes[3].summary", "nodes[0].properties.source_url"
    kind: Literal[
        "dropped_field", "path", "email", "phone", "url", "rrn", "secret", "invisible", "truncated", "dangling_edge"
    ]
    detail: str = ""


class ImportResult(BaseModel):
    document: SubbrainDocument
    content_hash: str  # sha256 hex of canonical JSON of `document`
    redactions: list[Redaction] = Field(default_factory=list)


class SubbrainVersion(BaseModel):
    """One immutable version of a subbrain as stored."""

    subbrain_id: str
    version: int
    owner_id: str
    owner_display: str
    visibility: Visibility  # current visibility of the subbrain (not of this version)
    is_published_version: bool  # True if this is the version currently shown when public
    content_hash: str
    created_at: str
    document: SubbrainDocument


class SubbrainSummary(BaseModel):
    subbrain_id: str
    owner_id: str
    title: str
    domains: list[str]
    visibility: Visibility
    latest_version: int
    published_version: Optional[int]
    updated_at: str


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


class MatchCandidate(BaseModel):
    subbrain_id: str
    version: int
    owner_id: str
    relevance: float  # 0..1, ORACLE MUST-M1
    distance: float  # 0..1 domain distance from host (1 = no shared domain)
    score: float = 0.0  # v.5 MUST-M2 ranking score (relevance + distance_bonus * distance); 0 for below-tau
    matched_terms: list[str]  # query terms that matched (evidence for MUST-M1)
    selected: bool  # chosen as canal member
    reason: str  # why selected / not selected (e.g. "below_tau", "truncated_by_limit")


class MatchResult(BaseModel):
    query_mode_used: QueryMode  # TOPIC or WHOLE_HOST (never AUTO)
    query_terms: list[str]
    strategy: str
    tau: float
    candidates: list[MatchCandidate]  # all scored candidates, sorted by relevance desc
    truncated: bool  # True if relevant candidates were dropped by max_members

    @property
    def selected(self) -> list[MatchCandidate]:
        return [c for c in self.candidates if c.selected]


# ---------------------------------------------------------------------------
# Canals
# ---------------------------------------------------------------------------


class CanalMember(BaseModel):
    subbrain_id: str
    version: int
    owner_id: str
    relevance: float
    distance: float
    matched_terms: list[str]


class Canal(BaseModel):
    id: str
    host_user_id: str
    host_subbrain_id: str
    host_version: int
    query: str
    query_mode_used: QueryMode
    members: list[CanalMember]  # does NOT include the host subbrain
    created_at: str

    @property
    def participant_ids(self) -> set[str]:
        return {self.host_user_id, *(m.owner_id for m in self.members)}


class CanalContext(BaseModel):
    """Everything the validator needs, assembled server-side (never from client input).

    `subbrains` maps (subbrain_id, version) -> SubbrainVersion for the host and every
    member whose subbrain is currently public (ORACLE NEVER-02).
    """

    canal_id: str
    host_subbrain_id: str
    host_version: int
    host_owner_id: str
    subbrains: dict[tuple[str, int], SubbrainVersion]


# ---------------------------------------------------------------------------
# Deltabrains (what the synthesizer submits)
# ---------------------------------------------------------------------------


class ProvRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subbrain_id: str
    version: int
    node_id: str


class DeltaNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    kind: NodeKind
    label: str = Field(min_length=1, max_length=200)
    summary: Optional[str] = Field(default=None, max_length=600)
    provenance: list[ProvRef] = Field(default_factory=list)


class DeltaEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    source: str
    target: str
    relation: str = Field(max_length=50)  # vocabulary checked by validator (RELATION_NOT_ALLOWED)
    rationale: Optional[str] = Field(default=None, max_length=2000)  # length rule checked by validator
    applies_when: Optional[str] = Field(default=None, max_length=400)  # ORACLE §9 (recommended)
    provenance: list[ProvRef] = Field(default_factory=list)


class SynthesizerInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["client_llm", "platform"] = "client_llm"
    model: Optional[str] = Field(default=None, max_length=100)
    protocol_version: str = PROTOCOL_VERSION


class DeltabrainSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[DeltaNode] = Field(max_length=1000)
    edges: list[DeltaEdge] = Field(default_factory=list, max_length=2000)
    synthesizer: SynthesizerInfo = Field(default_factory=SynthesizerInfo)


class Violation(BaseModel):
    code: ViolationCode
    message: str
    node_id: Optional[str] = None
    edge_id: Optional[str] = None


class DeltabrainStats(BaseModel):
    node_count: int
    edge_count: int
    new_node_count: int
    emergent_edge_ids: list[str]
    host_touching_emergent_edge_ids: list[str]
    owners_involved: int


class ValidationResult(BaseModel):
    ok: bool
    violations: list[Violation] = Field(default_factory=list)
    stats: Optional[DeltabrainStats] = None  # present when the payload parsed


class EdgeRating(BaseModel):
    edge_id: str
    rater_id: str
    novelty: int = Field(ge=0, le=1)
    validity: int = Field(ge=0, le=1)
    usefulness: int = Field(ge=0, le=1)


class DeltabrainRecord(BaseModel):
    """Raw stored deltabrain. Internal only — never returned to a tool caller as-is."""

    id: str
    canal_id: str
    submitted_by: str
    submission: DeltabrainSubmission
    stats: DeltabrainStats
    created_at: str


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
