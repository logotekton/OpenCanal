"""Query relevance and canal member selection (ORACLE §5.4, DECISIONS D-003).

Owner: Builder M. Pure functions over already-visible candidates (the store filters visibility).

The default strategy is `relevance_with_distance_bonus` (ORACLE v.5 MUST-M2, owner decision "먼 분야에
가산점"). The distance it rewards is the content distance of MUST-M5 (v.6 owner decision "내용으로 계산", v.7
definition): the share of the host's distinct label/tag words that the candidate also has. Summaries, node types,
edges, the title and declared domains never move it, and words the host lacks cannot move it either (M5-PAD-1).
The criterion may still change with the owner's research (D-003), so selection strategies stay pluggable
(`STRATEGIES`) and every scoring decision can be explained term by term (`relevance_evidence`) and by its
`score` for `match_explain`.

Exactness (v.6 MUST-M2, v.7 MUST-M5): ranking, τ and far_distance comparisons use unrounded values; MatchCandidate
fields are rounded to DISPLAY_DECIMALS only for the response. Relevance, distance and score are exact fractions, with
config numbers read as the decimals they are written as, so mathematically equal values compare equal (2.8 / 5 is
0.56, not 0.5599999999999999) and the manifest's tie rules ("같으면 관련도, 그다음 subbrain_id") are decided by the
rules, never by float rounding.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal, NamedTuple, Optional, Protocol, Union

from pydantic import BaseModel

from .config import MatchingConfig
from .models import MatchCandidate, MatchResult, QueryMode, SubbrainVersion, Visibility
from .textnorm import tokenize

# Candidate text fields, in tie-break order (first wins when two fields give the same weight).
FIELDS: tuple[str, ...] = ("tags", "label", "summary")

# Reason codes on MatchCandidate.reason (shown to the owner by match_explain).
REASON_SELECTED = "selected_relevance"
REASON_SELECTED_SCORE = "selected_score"  # relevance_with_distance_bonus
REASON_BELOW_TAU = "below_tau"
REASON_TRUNCATED = "truncated_by_limit"
REASON_DIVERSITY = "selected_diversity"
REASON_DISPLACED = "displaced_by_diversity"
REASON_NO_MATCH = "no_matched_terms"  # only reachable when tau <= 0: zero evidence is never selected

DISPLAY_DECIMALS = 4  # MatchCandidate relevance/distance/score are rounded to this for display only
NO_CONTENT_DISTANCE = 1.0  # MUST-M5: distance when the host has no words, or the candidate shares none

Number = Union[int, float, Fraction]


def display_value(value: Number) -> float:
    """A relevance/distance/score as shown in responses (v.6: round only for display)."""
    return round(float(value), DISPLAY_DECIMALS)


def _exact(value: Number) -> Fraction:
    """A config number as the decimal it is written as: 0.8 -> 4/5, not the nearest binary float."""
    return Fraction(str(value))


# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------


def _tokenize(text: Optional[str], cfg: MatchingConfig, stopwords: Iterable[str] = ()) -> list[str]:
    return tokenize(
        text,
        josa_suffixes=cfg.josa_suffixes,
        min_stem=cfg.josa_min_stem_length,
        stopwords=stopwords,
    )


def _tokens(texts: Iterable[Optional[str]], cfg: MatchingConfig, stopwords: Iterable[str] = ()) -> list[str]:
    """Tokens of several texts, josa-stripped, deduplicated in first-seen order."""
    stop = tuple(stopwords)
    seen: set[str] = set()
    out: list[str] = []
    for text in texts:
        for token in _tokenize(text, cfg, stop):
            if token not in seen:
                seen.add(token)
                out.append(token)
    return out


def query_terms(query: str, cfg: MatchingConfig) -> list[str]:
    """Content terms of a query: tokenize with josa stripping and stopword removal."""
    return _tokens([query], cfg, cfg.stopwords)


def _label_tag_texts(version: SubbrainVersion) -> list[str]:
    nodes = version.document.nodes
    return [tag for node in nodes for tag in node.tags] + [node.label for node in nodes]


def host_terms(host: SubbrainVersion, cfg: MatchingConfig) -> list[str]:
    """Terms used in whole_host mode: tokens of the host's tags and node labels (stopwords removed)."""
    return _tokens(_label_tag_texts(host), cfg, cfg.stopwords)


def candidate_fields(candidate: SubbrainVersion, cfg: MatchingConfig) -> dict[str, list[str]]:
    """Token lists per field. No stopword removal on candidates (a stopword never reaches the terms).

    tags    = node tags
    label   = node labels
    summary = node summaries

    Only the nodes' tags, labels and summaries are relevance fields (stub docstring, config field_weights,
    DECISIONS D-003 "태그·라벨·요약"). The document title and domains are not, and they do not move the
    content distance either (MUST-M5): a declared field never changes how a candidate ranks.
    """
    nodes = candidate.document.nodes
    return {
        "tags": _tokens([tag for node in nodes for tag in node.tags], cfg),
        "label": _tokens([node.label for node in nodes], cfg),
        "summary": _tokens([node.summary for node in nodes], cfg),
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


def _evidence_exact(
    terms: list[str], fields: dict[str, list[str]], cfg: MatchingConfig
) -> list[tuple[TermEvidence, Fraction]]:
    """Per term: the winning evidence and its exact weight (max over fields, first field wins a tie)."""
    field_sets = {name: set(tokens) for name, tokens in fields.items()}
    factor = _exact(cfg.substring_match_factor)
    out: list[tuple[TermEvidence, Fraction]] = []
    for term in terms:
        best, best_weight = TermEvidence(term=term, weight=0.0), Fraction(0)
        for name in FIELDS:
            w = _exact(cfg.field_weights.get(name, 0.0))
            if w <= 0:
                continue
            if term in field_sets.get(name, ()):
                weight, kind, token = w, "exact", term
            elif len(term) >= 2:
                token = next((tok for tok in fields.get(name, ()) if term in tok), None)
                if token is None:
                    continue
                weight, kind = w * factor, "substring"
            else:
                continue
            if weight > best_weight:
                best_weight = weight
                best = TermEvidence(term=term, weight=float(weight), field=name, match=kind, token=token)
        out.append((best, best_weight))
    return out


def _relevance_exact(weights: list[Fraction], cfg: MatchingConfig) -> Fraction:
    if not weights:
        return Fraction(0)
    denominator = max(1, min(len(weights), cfg.denominator_cap))
    return min(Fraction(1), sum(weights, Fraction(0)) / denominator)


def _score_terms(terms: list[str], candidate: SubbrainVersion, cfg: MatchingConfig) -> tuple[Fraction, list[str]]:
    evidence = _evidence_exact(terms, candidate_fields(candidate, cfg), cfg)
    relevance = _relevance_exact([weight for _, weight in evidence], cfg)
    return relevance, [e.term for e, weight in evidence if weight > 0]


def relevance_evidence(terms: list[str], candidate: SubbrainVersion, cfg: MatchingConfig) -> list[TermEvidence]:
    """Per-term breakdown behind score_relevance (same order as the deduplicated terms)."""
    return [e for e, _ in _evidence_exact(_clean_terms(terms), candidate_fields(candidate, cfg), cfg)]


def score_relevance(terms: list[str], candidate: SubbrainVersion, cfg: MatchingConfig) -> tuple[float, list[str]]:
    """relevance in [0,1] (unrounded; round with display_value to show it) and the matched terms.

    per term t: weight = max over fields (tags, label, summary) of field_weights[field] if t equals a token
    of that field, else field_weights[field] * substring_match_factor if t (len>=2) is a substring of a token;
    relevance = sum(weights) / min(len(terms), denominator_cap). Empty terms -> 0.0.
    """
    relevance, matched = _score_terms(_clean_terms(terms), candidate, cfg)
    return float(relevance), matched


# ---------------------------------------------------------------------------
# Content distance (ORACLE v.7 MUST-M5)
# ---------------------------------------------------------------------------


def _content_words(version: SubbrainVersion, cfg: MatchingConfig) -> frozenset[str]:
    """The distinct words of a version's node labels and tags (josa stripped, stopwords removed).

    Summaries, node types, edges, the title and declared domains are not content for the distance. A word counts
    once however often it is repeated, so the set of the host is the same token set as `host_terms`.
    """
    return frozenset(_tokens(_label_tag_texts(version), cfg, cfg.stopwords))


def _distance_between(host_words: frozenset[str], candidate_words: frozenset[str], cfg: MatchingConfig) -> Fraction:
    """1 - min(1, similarity / distance_saturation) with similarity = |H ∩ C| / |H|, exactly.

    The similarity is relative to the host: words the candidate adds that the host lacks change neither |H ∩ C|
    nor |H|, so padding a candidate never makes it look farther (M5-PAD-1). An empty H gives 1. A non-positive
    saturation makes any shared word saturate (distance 0) and keeps 1 when nothing is shared.
    """
    if not host_words:
        return _exact(NO_CONTENT_DISTANCE)
    shared = len(host_words & candidate_words)
    if shared == 0:
        return _exact(NO_CONTENT_DISTANCE)
    saturation = _exact(cfg.distance_saturation)
    if saturation <= 0:
        return Fraction(0)
    similarity = Fraction(shared, len(host_words))
    return 1 - min(Fraction(1), similarity / saturation)


def content_distance(host: SubbrainVersion, candidate: SubbrainVersion, cfg: MatchingConfig) -> float:
    """MUST-M5 distance in [0, 1], unrounded: 1 - min(1, |H ∩ C| / |H| / distance_saturation).

    H and C are the sets of distinct words of the host's and the candidate's node labels and tags. Host-relative,
    so not symmetric. No host words -> 1.0. Deterministic. The exact value is a rational; this is the float nearest
    to it (1/3, not 0.33333333333333337). match() ranks on the exact value (`_distance_between`).
    """
    return float(_distance_between(_content_words(host, cfg), _content_words(candidate, cfg), cfg))


# ---------------------------------------------------------------------------
# Selection strategies
# ---------------------------------------------------------------------------


@dataclass(eq=False)
class _Scored:
    """One candidate during selection: the exact values every comparison uses, and its display record."""

    out: MatchCandidate  # rounded fields; selection writes `selected` and `reason` here
    relevance: Fraction
    distance: Fraction
    score: Fraction  # relevance + distance_bonus * distance if eligible, else 0
    eligible: bool  # relevance >= tau and relevance > 0
    below_tau: bool  # relevance < tau


class SelectionStrategy(Protocol):
    def __call__(self, scored: list[_Scored], *, max_members: int, far_distance: float) -> list[_Scored]:
        """Set `selected` and `reason` on every candidate's `out`; return the candidates in this strategy's
        ranking (a new list: `scored` itself stays in relevance order, MatchResult.candidates in models.py).
        """


def _relevance_key(s: _Scored) -> tuple:
    return (-s.relevance, s.out.subbrain_id, s.out.version)


def _score_key(s: _Scored) -> tuple:
    # MUST-M2: score, then relevance, then subbrain_id (version only makes the order total).
    return (-s.score, -s.relevance, s.out.subbrain_id, s.out.version)


def _select_top(order: list[_Scored], *, max_members: int, reason: str) -> None:
    """Top max_members eligible candidates in `order` get `reason`; the other eligible ones are truncated."""
    limit = max(0, max_members)
    taken = 0
    for s in order:
        c = s.out
        if not s.eligible:
            c.selected = False
            c.reason = REASON_BELOW_TAU if s.below_tau else REASON_NO_MATCH
        elif taken < limit:
            c.selected = True
            c.reason = reason
            taken += 1
        else:
            c.selected = False
            c.reason = REASON_TRUNCATED


def _guarantee_diversity(order: list[_Scored], *, far_distance: float) -> None:
    """If no selected member is far (distance >= far_distance) and a truncated (eligible) candidate is, the
    first such candidate in `order` replaces the last selected member in `order`.

    far_distance is read as the decimal it is written as and compared exactly with the exact distance, so a
    distance of exactly far_distance is far.
    """
    threshold = _exact(far_distance)
    selected = [s for s in order if s.out.selected]
    if not selected or any(s.distance >= threshold for s in selected):
        return
    far = next((s for s in order if s.out.reason == REASON_TRUNCATED and s.distance >= threshold), None)
    if far is None:
        return
    displaced = selected[-1].out
    displaced.selected = False
    displaced.reason = REASON_DISPLACED
    far.out.selected = True
    far.out.reason = REASON_DIVERSITY


def select_relevance_only(scored: list[_Scored], *, max_members: int, far_distance: float) -> list[_Scored]:
    """Top max_members candidates with relevance >= tau, in relevance order (far_distance unused)."""
    order = sorted(scored, key=_relevance_key)
    _select_top(order, max_members=max_members, reason=REASON_SELECTED)
    return order


def select_relevance_plus_diversity(
    scored: list[_Scored], *, max_members: int, far_distance: float
) -> list[_Scored]:
    """relevance_only, then guarantee one far member when one was cut by the limit (PROV-M2, v.6 far_distance).

    If no selected member has distance >= far_distance and a truncated candidate (relevance >= tau) does,
    the best such candidate replaces the lowest-ranked selected member.
    """
    order = select_relevance_only(scored, max_members=max_members, far_distance=far_distance)
    _guarantee_diversity(order, far_distance=far_distance)
    return order


def select_relevance_with_distance_bonus(
    scored: list[_Scored], *, max_members: int, far_distance: float
) -> list[_Scored]:
    """MUST-M2: eligible = relevance >= tau; rank by score, then relevance, then subbrain_id.

    Selects the top max_members eligible candidates in score order ("selected_score"), then applies the same
    diversity guarantee as relevance_plus_diversity over that order. Below-tau candidates have score 0 and are
    never selected, whatever their distance.
    """
    order = sorted(scored, key=_score_key)
    _select_top(order, max_members=max_members, reason=REASON_SELECTED_SCORE)
    _guarantee_diversity(order, far_distance=far_distance)
    return order


STRATEGIES: dict[str, SelectionStrategy] = {
    "relevance_with_distance_bonus": select_relevance_with_distance_bonus,
    "relevance_plus_diversity": select_relevance_plus_diversity,
    "relevance_only": select_relevance_only,
}


def _display_relevance_rank(c: MatchCandidate) -> tuple:
    return (-c.relevance, c.subbrain_id, c.version)


def _display_score_rank(c: MatchCandidate) -> tuple:
    return (-c.score, -c.relevance, c.subbrain_id, c.version)


# The order each strategy ranks candidates in, over the rounded MatchCandidate fields. MatchResult.candidates is
# always in relevance order (models.py), so callers that present a ranking sort with this key. Rounded values can
# tie where the unrounded ones do not; RankedMatch.ranking (match_with_ranking) is the exact order match() used.
RANK_KEYS: dict[str, Callable[[MatchCandidate], tuple]] = {
    "relevance_with_distance_bonus": _display_score_rank,
    "relevance_plus_diversity": _display_relevance_rank,
    "relevance_only": _display_relevance_rank,
}


def in_rank_order(candidates: Iterable[MatchCandidate], strategy: str) -> list[MatchCandidate]:
    """`candidates` sorted the way `strategy` ranks them, by their displayed (rounded) values.

    Relevance order for an unknown name. For the exact order of a match() call, use match_with_ranking.
    """
    return sorted(candidates, key=RANK_KEYS.get(strategy, _display_relevance_rank))


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


class RankedMatch(NamedTuple):
    result: MatchResult
    ranking: list[MatchCandidate]  # the same objects as result.candidates, in the strategy's exact ranking


def match_with_ranking(
    query: str,
    host: SubbrainVersion,
    candidates: list[SubbrainVersion],
    *,
    max_members: int,
    cfg: MatchingConfig,
    query_mode: QueryMode = QueryMode.AUTO,
    strategy: str | None = None,
) -> RankedMatch:
    """match(), plus the candidates in the order the strategy ranked them by unrounded values."""
    strategy_name = resolve_strategy(strategy, cfg)
    select = STRATEGIES[strategy_name]

    mode = QueryMode(query_mode) if query_mode is not None else QueryMode.AUTO
    if mode is QueryMode.AUTO:
        mode = QueryMode.TOPIC if query_terms(query, cfg) else QueryMode.WHOLE_HOST
    terms = query_terms(query, cfg) if mode is QueryMode.TOPIC else host_terms(host, cfg)
    clean = _clean_terms(terms)

    tau = _exact(cfg.tau)
    bonus = _exact(cfg.distance_bonus)
    host_words = _content_words(host, cfg)  # once per call

    scored: list[_Scored] = []
    for candidate in candidates:
        if not _is_candidate(candidate, host):
            continue
        relevance, matched = _score_terms(clean, candidate, cfg)
        distance = _distance_between(host_words, _content_words(candidate, cfg), cfg)
        # relevance > 0 keeps NEVER-08 even if tau were configured <= 0; the bonus never lifts a below-tau
        # or zero-evidence candidate (MUST-M2 forbidden result).
        eligible = relevance >= tau and relevance > 0
        score = relevance + bonus * distance if eligible else Fraction(0)
        out = MatchCandidate(
            subbrain_id=candidate.subbrain_id,
            version=candidate.version,
            owner_id=candidate.owner_id,
            relevance=display_value(relevance),
            distance=display_value(distance),
            score=display_value(score),
            matched_terms=matched,
            selected=False,
            reason="",
        )
        scored.append(_Scored(out, relevance, distance, score, eligible, relevance < tau))
    scored.sort(key=_relevance_key)

    order = select(scored, max_members=max_members, far_distance=cfg.far_distance)

    result = MatchResult(
        query_mode_used=mode,
        query_terms=terms,
        strategy=strategy_name,
        tau=cfg.tau,
        candidates=[s.out for s in scored],
        truncated=any(s.out.reason in (REASON_TRUNCATED, REASON_DISPLACED) for s in scored),
    )
    return RankedMatch(result, [s.out for s in order])


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
    distance = content_distance(host, candidate) (MUST-M5); the host's word set is built once per call.
    Every eligible candidate gets score = relevance + cfg.distance_bonus * distance, others 0.0.
    relevance_with_distance_bonus (default, MUST-M2): top max_members by (score, relevance, subbrain_id),
    then the diversity swap below over that order.
    relevance_only: top max_members by relevance (tie-break subbrain_id).
    relevance_plus_diversity: same, then if no selected member is far (distance >= cfg.far_distance) and an
    unselected far candidate with relevance >= tau exists, swap the best one in for the lowest selected.
    All ranking and τ comparisons use unrounded values; relevance, distance and score on MatchCandidate are
    rounded to DISPLAY_DECIMALS for display. Every strategy lists candidates in relevance order (models.py);
    match_with_ranking gives the strategy's own ranking. Deterministic for identical input.
    """
    return match_with_ranking(
        query, host, candidates, max_members=max_members, cfg=cfg, query_mode=query_mode, strategy=strategy
    ).result
