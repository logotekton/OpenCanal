"""Query relevance and canal member selection (ORACLE §5.4, DECISIONS D-003).

Owner: Builder M. Pure functions over already-visible candidates (the store filters visibility).

The owner has not fixed the member-selection criterion yet (D-003), so selection strategies are
pluggable (`STRATEGIES`) and every scoring decision can be explained term by term
(`relevance_evidence`) for `match_explain`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal, Optional, Protocol

from pydantic import BaseModel

from .config import MatchingConfig
from .models import MatchCandidate, MatchResult, QueryMode, SubbrainVersion, Visibility
from .textnorm import normalize, tokenize

# Candidate text fields, in tie-break order (first wins when two fields give the same weight).
FIELDS: tuple[str, ...] = ("tags", "label", "summary")

# Reason codes on MatchCandidate.reason (shown to the owner by match_explain).
REASON_SELECTED = "selected_relevance"
REASON_BELOW_TAU = "below_tau"
REASON_TRUNCATED = "truncated_by_limit"
REASON_DIVERSITY = "selected_diversity"
REASON_DISPLACED = "displaced_by_diversity"
REASON_NO_MATCH = "no_matched_terms"  # only reachable when tau <= 0: zero evidence is never selected

MAX_DISTANCE = 1.0  # domain distance of a candidate that shares no domain with the host


# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------


def _tokens(texts: Iterable[Optional[str]], cfg: MatchingConfig, stopwords: Iterable[str] = ()) -> list[str]:
    """Tokens of several texts, josa-stripped, deduplicated in first-seen order."""
    stop = tuple(stopwords)
    seen: set[str] = set()
    out: list[str] = []
    for text in texts:
        for token in tokenize(
            text,
            josa_suffixes=cfg.josa_suffixes,
            min_stem=cfg.josa_min_stem_length,
            stopwords=stop,
        ):
            if token not in seen:
                seen.add(token)
                out.append(token)
    return out


def query_terms(query: str, cfg: MatchingConfig) -> list[str]:
    """Content terms of a query: tokenize with josa stripping and stopword removal."""
    return _tokens([query], cfg, cfg.stopwords)


def host_terms(host: SubbrainVersion, cfg: MatchingConfig) -> list[str]:
    """Terms used in whole_host mode: tokens of the host's tags and node labels (stopwords removed)."""
    nodes = host.document.nodes
    texts = [tag for node in nodes for tag in node.tags] + [node.label for node in nodes]
    return _tokens(texts, cfg, cfg.stopwords)


def candidate_fields(candidate: SubbrainVersion, cfg: MatchingConfig) -> dict[str, list[str]]:
    """Token lists per field. No stopword removal on candidates (a stopword never reaches the terms).

    tags    = node tags + subbrain domains
    label   = node labels + document title
    summary = node summaries + edge summaries
    """
    doc = candidate.document
    return {
        "tags": _tokens([tag for node in doc.nodes for tag in node.tags] + list(doc.domains), cfg),
        "label": _tokens([node.label for node in doc.nodes] + [doc.title], cfg),
        "summary": _tokens([node.summary for node in doc.nodes] + [edge.summary for edge in doc.edges], cfg),
    }


# ---------------------------------------------------------------------------
# Relevance
# ---------------------------------------------------------------------------


class TermEvidence(BaseModel):
    """Why one term contributed what it did to a candidate's relevance."""

    term: str
    weight: float  # 0 when the term matched nothing
    field: Optional[str] = None  # field that gave the winning weight
    match: Optional[Literal["exact", "substring"]] = None
    token: Optional[str] = None  # candidate token that matched (first in field order)


def _clean_terms(terms: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            out.append(term)
    return out


def _evidence_for_fields(terms: list[str], fields: dict[str, list[str]], cfg: MatchingConfig) -> list[TermEvidence]:
    field_sets = {name: set(tokens) for name, tokens in fields.items()}
    out: list[TermEvidence] = []
    for term in terms:
        best = TermEvidence(term=term, weight=0.0)
        for name in FIELDS:
            w = cfg.field_weights.get(name, 0.0)
            if w <= 0:
                continue
            if term in field_sets.get(name, ()):
                weight, kind, token = w, "exact", term
            elif len(term) >= 2:
                token = next((tok for tok in fields.get(name, ()) if term in tok), None)
                if token is None:
                    continue
                weight, kind = w * cfg.substring_match_factor, "substring"
            else:
                continue
            if weight > best.weight:
                best = TermEvidence(term=term, weight=weight, field=name, match=kind, token=token)
        out.append(best)
    return out


def relevance_evidence(terms: list[str], candidate: SubbrainVersion, cfg: MatchingConfig) -> list[TermEvidence]:
    """Per-term breakdown behind score_relevance (same order as the deduplicated terms)."""
    return _evidence_for_fields(_clean_terms(terms), candidate_fields(candidate, cfg), cfg)


def _relevance_from_evidence(evidence: list[TermEvidence], cfg: MatchingConfig) -> tuple[float, list[str]]:
    if not evidence:
        return 0.0, []
    denominator = max(1, min(len(evidence), cfg.denominator_cap))
    total = sum(e.weight for e in evidence)
    relevance = round(min(1.0, total / denominator), 4)
    return relevance, [e.term for e in evidence if e.weight > 0]


def score_relevance(terms: list[str], candidate: SubbrainVersion, cfg: MatchingConfig) -> tuple[float, list[str]]:
    """relevance in [0,1] and the matched terms.

    per term t: weight = max over fields (tags, label, summary) of field_weights[field] if t equals a token
    of that field, else field_weights[field] * substring_match_factor if t (len>=2) is a substring of a token;
    relevance = sum(weights) / min(len(terms), denominator_cap). Empty terms -> 0.0.
    """
    return _relevance_from_evidence(relevance_evidence(terms, candidate, cfg), cfg)


def _domain_set(version: SubbrainVersion) -> set[str]:
    return {d for d in (normalize(raw) for raw in version.document.domains) if d}


def domain_distance(host: SubbrainVersion, candidate: SubbrainVersion) -> float:
    """1 - Jaccard(normalized host domains, normalized candidate domains)."""
    a, b = _domain_set(host), _domain_set(candidate)
    union = a | b
    if not union:
        return MAX_DISTANCE
    return round(1.0 - len(a & b) / len(union), 4)


# ---------------------------------------------------------------------------
# Selection strategies
# ---------------------------------------------------------------------------


class SelectionStrategy(Protocol):
    def __call__(self, ranked: list[MatchCandidate], *, max_members: int, tau: float) -> None:
        """Set `selected` and `reason` on every candidate of `ranked` (sorted best first). In place."""


def _eligible(candidate: MatchCandidate, tau: float) -> bool:
    # relevance > 0 keeps NEVER-08 even if tau were configured <= 0.
    return candidate.relevance >= tau and candidate.relevance > 0


def select_relevance_only(ranked: list[MatchCandidate], *, max_members: int, tau: float) -> None:
    """Top max_members candidates with relevance >= tau, in rank order."""
    limit = max(0, max_members)
    taken = 0
    for c in ranked:
        if not _eligible(c, tau):
            c.selected = False
            c.reason = REASON_BELOW_TAU if c.relevance < tau else REASON_NO_MATCH
        elif taken < limit:
            c.selected = True
            c.reason = REASON_SELECTED
            taken += 1
        else:
            c.selected = False
            c.reason = REASON_TRUNCATED


def select_relevance_plus_diversity(ranked: list[MatchCandidate], *, max_members: int, tau: float) -> None:
    """relevance_only, then guarantee one domain-disjoint member when one was cut by the limit (PROV-M2).

    If no selected member has distance == 1.0 and a truncated candidate (relevance >= tau) does,
    the best such candidate replaces the lowest-ranked selected member.
    """
    select_relevance_only(ranked, max_members=max_members, tau=tau)
    selected = [c for c in ranked if c.selected]
    if not selected or any(c.distance == MAX_DISTANCE for c in selected):
        return
    diverse = next((c for c in ranked if c.reason == REASON_TRUNCATED and c.distance == MAX_DISTANCE), None)
    if diverse is None:
        return
    displaced = selected[-1]
    displaced.selected = False
    displaced.reason = REASON_DISPLACED
    diverse.selected = True
    diverse.reason = REASON_DIVERSITY


STRATEGIES: dict[str, SelectionStrategy] = {
    "relevance_plus_diversity": select_relevance_plus_diversity,
    "relevance_only": select_relevance_only,
}


def resolve_strategy(strategy: Optional[str], cfg: MatchingConfig) -> str:
    """Strategy name to use; ValueError if unknown or not allowed by config."""
    name = strategy if strategy is not None else cfg.strategy
    if name not in STRATEGIES or name not in cfg.strategies_available:
        raise ValueError(f"unknown matching strategy: {name!r}")
    return name


# ---------------------------------------------------------------------------
# Match
# ---------------------------------------------------------------------------


def _is_candidate(candidate: SubbrainVersion, host: SubbrainVersion) -> bool:
    """MUST-M4: only other users' public subbrains. Excluded ones are not listed at all (no existence leak)."""
    return (
        candidate.subbrain_id != host.subbrain_id
        and candidate.owner_id != host.owner_id
        # Defensive: the store already passes only public versions; a private one must never surface.
        and candidate.visibility == Visibility.PUBLIC
    )


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
    strategy_name = resolve_strategy(strategy, cfg)
    select = STRATEGIES[strategy_name]

    mode = QueryMode(query_mode) if query_mode is not None else QueryMode.AUTO
    if mode is QueryMode.AUTO:
        mode = QueryMode.TOPIC if query_terms(query, cfg) else QueryMode.WHOLE_HOST
    terms = query_terms(query, cfg) if mode is QueryMode.TOPIC else host_terms(host, cfg)

    scored: list[MatchCandidate] = []
    for candidate in candidates:
        if not _is_candidate(candidate, host):
            continue
        relevance, matched = score_relevance(terms, candidate, cfg)
        scored.append(
            MatchCandidate(
                subbrain_id=candidate.subbrain_id,
                version=candidate.version,
                owner_id=candidate.owner_id,
                relevance=relevance,
                distance=domain_distance(host, candidate),
                matched_terms=matched,
                selected=False,
                reason="",
            )
        )
    scored.sort(key=lambda c: (-c.relevance, c.subbrain_id, c.version))

    select(scored, max_members=max_members, tau=cfg.tau)

    return MatchResult(
        query_mode_used=mode,
        query_terms=terms,
        strategy=strategy_name,
        tau=cfg.tau,
        candidates=scored,
        truncated=any(c.reason in (REASON_TRUNCATED, REASON_DISPLACED) for c in scored),
    )
