"""Query relevance and canal member selection (ORACLE §5.4, DECISIONS D-003).

Owner: Builder M. Pure functions over already-visible candidates (the store filters visibility).
"""

from __future__ import annotations

from .config import MatchingConfig
from .models import MatchResult, QueryMode, SubbrainVersion


def query_terms(query: str, cfg: MatchingConfig) -> list[str]:
    """Content terms of a query: tokenize with josa stripping and stopword removal."""
    raise NotImplementedError


def host_terms(host: SubbrainVersion, cfg: MatchingConfig) -> list[str]:
    """Terms used in whole_host mode: tokens of the host's tags and node labels (stopwords removed)."""
    raise NotImplementedError


def score_relevance(terms: list[str], candidate: SubbrainVersion, cfg: MatchingConfig) -> tuple[float, list[str]]:
    """relevance in [0,1] and the matched terms.

    per term t: weight = max over fields (tags, label, summary) of field_weights[field] if t equals a token
    of that field, else field_weights[field] * substring_match_factor if t (len>=2) is a substring of a token;
    relevance = sum(weights) / min(len(terms), denominator_cap). Empty terms -> 0.0.
    """
    raise NotImplementedError


def domain_distance(host: SubbrainVersion, candidate: SubbrainVersion) -> float:
    """1 - Jaccard(normalized host domains, normalized candidate domains)."""
    raise NotImplementedError


def match(
    query: str,
    host: SubbrainVersion,
    candidates: list[SubbrainVersion],
    *,
    max_members: int,
    cfg: MatchingConfig,
    query_mode: QueryMode = QueryMode.AUTO,
    strategy: str | None = None,
) -> MatchResult:
    """Score all candidates, select members.

    AUTO -> TOPIC if query_terms() is non-empty else WHOLE_HOST.
    Never select relevance < tau (MUST-M1). Never select candidates owned by host.owner_id (MUST-M4).
    relevance_only: top max_members by relevance (tie-break subbrain_id).
    relevance_plus_diversity: same, then if no selected member has distance == 1.0 and an unselected
    candidate with distance == 1.0 and relevance >= tau exists, swap it in for the lowest selected.
    Deterministic for identical input.
    """
    raise NotImplementedError
