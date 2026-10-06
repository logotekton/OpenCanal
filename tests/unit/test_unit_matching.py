"""Unit tests for opencanal.matching (Builder M). Hand-built SubbrainVersions, no store.

Terms, relevance, query modes and visibility use HOST and friends (shaped after ORACLE §6.1). Strategy tests
use HS, a host of 48 distinct label words, and candidates built by `_shaped` that carry the first `shared` of them,
so every content distance (ORACLE v.7 MUST-M5) is exact by hand: similarity = shared / 48,
distance = 1 - min(1, similarity / 0.25) = 1 - min(1, shared / 12). The content-distance function itself is pinned
in test_unit_matching_distance.py.
"""

from __future__ import annotations

import random
from fractions import Fraction

import pytest

from opencanal.config import MatchingConfig, load_config
from opencanal.matching import (
    DISPLAY_DECIMALS,
    REASON_BELOW_TAU,
    REASON_DISPLACED,
    REASON_DIVERSITY,
    REASON_NO_MATCH,
    REASON_SELECTED,
    REASON_SELECTED_SCORE,
    REASON_TRUNCATED,
    STRATEGIES,
    content_distance,
    display_value,
    host_terms,
    in_rank_order,
    match,
    match_with_ranking,
    query_terms,
    relevance_evidence,
    score_relevance,
)
from opencanal.models import (
    QueryMode,
    SubbrainDocument,
    SubbrainEdge,
    SubbrainNode,
    SubbrainVersion,
    Visibility,
)

Q01 = "모듈러 건축의 현장 조립 오류를 줄일 아이디어"
Q02 = "내 두뇌를 평가해줘"
Q03 = "제빵 반죽 발효 온도"

BONUS = "relevance_with_distance_bonus"
ALL_STRATEGIES = (BONUS, "relevance_plus_diversity", "relevance_only")
SELECTED_REASON = {
    BONUS: REASON_SELECTED_SCORE,
    "relevance_plus_diversity": REASON_SELECTED,
    "relevance_only": REASON_SELECTED,
}


@pytest.fixture(scope="module")
def cfg() -> MatchingConfig:
    return load_config().matching


def _node(node_id: str, label: str, tags: tuple[str, ...] = (), summary: str | None = None) -> SubbrainNode:
    return SubbrainNode(id=node_id, label=label, tags=list(tags), summary=summary)


def _sv(
    subbrain_id: str,
    owner_id: str,
    *,
    domains: list[str],
    nodes: list[SubbrainNode],
    title: str = "untitled",
    edges: list[SubbrainEdge] | None = None,
    visibility: Visibility = Visibility.PUBLIC,
    version: int = 1,
) -> SubbrainVersion:
    return SubbrainVersion(
        subbrain_id=subbrain_id,
        version=version,
        owner_id=owner_id,
        owner_display=owner_id,
        visibility=visibility,
        is_published_version=True,
        content_hash="0" * 64,
        created_at="2026-10-06T00:00:00Z",
        document=SubbrainDocument(title=title, domains=domains, nodes=nodes, edges=edges or []),
    )


# Brains shaped after ORACLE §6.1 (hand-built here, not the fixture files).
HOST = _sv(
    "A",
    "user_a",
    domains=["건축", "BIM"],
    title="모듈러 건축 노트",
    nodes=[
        _node("a1", "모듈러 건축", ("모듈러", "건축")),
        _node("a2", "현장 조립 오류", ("조립", "오류", "현장")),
        _node("a3", "공차 관리", ("공차",)),
        _node("a4", "접합부 상세", ("bim",)),
    ],
)
OWN_OTHER = _sv(  # host owner's second subbrain: never a candidate
    "A-own", "user_a", domains=["건축"], nodes=[_node("o1", "조립 오류 사례", ("조립", "오류", "모듈러", "현장"))]
)
A2 = _sv(  # shares the tags 모듈러 + 건축 + 현장 (+ bim for whole_host)
    "A2",
    "user_e",
    domains=["건축", "BIM"],
    nodes=[_node("e1", "모듈러 유닛 운송", ("모듈러", "운송", "현장", "건축", "bim"))],
)
B = _sv(
    "B",
    "user_b",
    domains=["게임 디자인"],
    nodes=[
        _node("b1", "블록 조립 규칙", ("조립", "오류", "오조작 방지")),
        _node("b2", "잘못 놓을 수 없는 블록 모양", ("모양",)),
    ],
)
C = _sv(
    "C",
    "user_c",
    domains=["세포생물학"],
    nodes=[
        _node("c1", "단백질 자기조립", ("조립", "오류", "자기조립")),
        _node("c2", "형태 상보성", ("형태",)),
    ],
)
D = _sv(
    "D",
    "user_d",
    domains=["동네 빵집 마케팅"],
    nodes=[_node("d1", "단골 적립 쿠폰", ("쿠폰", "단골"), summary="아침 빵 할인 행사")],
)
P = _sv(  # private, shares Q-01 terms: must never surface
    "P",
    "user_b",
    domains=["게임 디자인"],
    visibility=Visibility.PRIVATE,
    nodes=[_node("p1", "모듈러 조립 오류", ("모듈러", "조립", "오류", "현장", "건축"))],
)
ALL = [HOST, OWN_OTHER, A2, B, C, D, P]


# ---------------------------------------------------------------------------
# Strategy pool: a host of 48 words and candidates of known content distance
# ---------------------------------------------------------------------------

# 48 words: no Q-01 term, no substring of one. distance from HS = 1 - min(1, shared / 12).
HS_TOKENS = ("공차", "접합부", "양중", "인양", *(f"hs{i:02d}" for i in range(44)))


def _label_nodes(words, prefix: str) -> list[SubbrainNode]:
    return [_node(f"{prefix}{i // 16}", " ".join(words[i : i + 16])) for i in range(0, len(words), 16)]


HS = _sv("H", "user_host", domains=["건축", "BIM"], title="모듈러 건축 노트", nodes=_label_nodes(HS_TOKENS, "h"))


def _shaped(
    subbrain_id: str,
    owner_id: str,
    *,
    tags: tuple[str, ...] = (),
    label: tuple[str, ...] = (),
    summary: tuple[str, ...] = (),
    shared: int = 0,
    fillers: int = 0,
    domains: tuple[str, ...] = ("z",),
    visibility: Visibility = Visibility.PUBLIC,
) -> SubbrainVersion:
    """A candidate with its tags, label and summary words on one node (label "f0" if none), the first `shared` HS
    tokens and `fillers` words the host lacks as labels of further nodes. Fillers match no query term.

    Against HS: distance = 1 - min(1, shared / 12); fillers never change it (MUST-M5 v.7).
    """
    content = [*tags, *label, *summary]
    assert len(set(content)) == len(content) and not set(content) & set(HS_TOKENS)
    nodes = [_node("n0", " ".join(label) or "f0", tags, summary=" ".join(summary) or None)]
    nodes += _label_nodes(HS_TOKENS[:shared], "s") + _label_nodes([f"f{i + 1}" for i in range(fillers)], "f")
    return _sv(subbrain_id, owner_id, domains=list(domains), nodes=nodes, visibility=visibility)


# Relevance is for Q01's 5 terms (denominator 5); distance is from HS; score = relevance + 0.3 * distance.
SA2 = _shaped("A2", "user_e", tags=("모듈러", "현장", "건축"), shared=12)  # 0.6, d 0 (similarity 1/4) -> 0.6
SB = _shaped("B", "user_b", tags=("조립", "오류"))  # 0.4, d 1 -> 0.7
SC = _shaped("C", "user_c", tags=("조립", "오류"), label=("형태",), fillers=30)  # 0.4, d 1 -> 0.7
SD = _shaped("D", "user_d", tags=("쿠폰",), summary=("빵",))  # 0.0, d 1 -> 0
NEAR = _shaped("N", "user_n", tags=("모듈러", "현장", "조립", "오류", "건축"), shared=20)  # 1.0, d 0 -> 1.0
A3 = _shaped("A3", "user_f", tags=("모듈러", "현장", "건축"), shared=6, fillers=9)  # 0.6, d 1/2 (1/8) -> 0.75
A4 = _shaped("A4", "user_i", tags=("모듈러", "현장", "건축"), shared=8)  # 0.6, d 1/3 (1/6) -> 0.7
T3 = _shaped("T3", "user_t", tags=("조립", "오류"), shared=8, fillers=40)  # 0.4, d 1/3 -> 0.5
M75 = _shaped("M75", "user_m", tags=("조립", "오류"), shared=3)  # 0.4, d 3/4 (1/16) -> 0.625
A5 = _shaped("A5", "user_j", tags=("모듈러", "현장", "건축", "조립"), shared=48)  # 0.8, d 0 -> 0.8
FAR_LOW = _shaped("A-far", "user_g", tags=("조립",), summary=("오류",))  # 1.0 + 0.5 = 0.3, d 1 -> 0.6
NEAR_HIGH = _shaped("Z-near", "user_z", tags=("모듈러", "현장", "건축"), shared=12)  # 0.6, d 0 -> 0.6 (= FAR_LOW)
WEAK_FAR = _shaped("W", "user_w", summary=("오류",))  # 0.1 < tau, d 1 (the bonus would lift it to 0.4)
HS_OWN = _shaped("H-own", "user_host", tags=("모듈러", "현장", "조립", "오류", "건축"))  # host's own: never listed
HS_PRIVATE = _shaped("P", "user_b", tags=("모듈러", "현장", "조립", "오류", "건축"), visibility=Visibility.PRIVATE)
POOL = [SA2, SB, SC, SD, NEAR, A3, A4, A5, T3, M75, FAR_LOW, NEAR_HIGH, WEAK_FAR]
EXPECTED = {  # subbrain_id: (relevance, distance, score) — hand-computed from the comments above
    "A2": (0.6, 0.0, 0.6),
    "B": (0.4, 1.0, 0.7),
    "C": (0.4, 1.0, 0.7),
    "D": (0.0, 1.0, 0.0),
    "N": (1.0, 0.0, 1.0),
    "A3": (0.6, 0.5, 0.75),
    "A4": (0.6, 0.3333, 0.7),
    "A5": (0.8, 0.0, 0.8),
    "T3": (0.4, 0.3333, 0.5),
    "M75": (0.4, 0.75, 0.625),
    "A-far": (0.3, 1.0, 0.6),
    "Z-near": (0.6, 0.0, 0.6),
    "W": (0.1, 1.0, 0.0),
}


def _by_id(result, subbrain_id):
    return next(c for c in result.candidates if c.subbrain_id == subbrain_id)


def _ranked(result):
    """Candidates in the strategy's own ranking, by displayed values (result.candidates is in relevance order)."""
    return in_rank_order(result.candidates, result.strategy)


def _ranking(query, host, pool, **kw):
    """The exact ranking match() used (unrounded values)."""
    return match_with_ranking(query, host, pool, **kw).ranking


# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------


def test_query_terms_strip_josa_and_stopwords(cfg):
    assert query_terms(Q01, cfg) == ["모듈러", "건축", "현장", "조립", "오류"]
    assert query_terms(Q03, cfg) == ["제빵", "반죽", "발효", "온도"]


@pytest.mark.parametrize("query", [Q02, "내 두뇌 평가해줘", "Evaluate my brain, please!", "  ", ""])
def test_query_terms_topicless_queries_are_empty(cfg, query):
    assert query_terms(query, cfg) == []


def test_query_terms_josa_min_stem_keeps_short_words(cfg):
    # "결과" ends with josa "과" but the stem would be 1 char, so it is kept whole.
    assert query_terms("결과를 현장에서는", cfg) == ["결과", "현장"]


def test_host_terms_are_tags_then_labels_without_stopwords(cfg):
    host = _sv(
        "H",
        "user_h",
        domains=["도메인전용"],
        title="제목전용 두뇌",
        nodes=[
            _node("h1", "현장 조립 오류", ("조립", "오류")),
            _node("h2", "내 두뇌 생각", ("공차를",)),
        ],
    )
    # tags first (node order), then labels; josa stripped; stopwords (내, 두뇌, 생각) dropped; dedup.
    assert host_terms(host, cfg) == ["조립", "오류", "공차", "현장"]


def test_host_terms_exclude_domains_and_title(cfg):
    terms = host_terms(HOST, cfg)
    assert "노트" not in terms  # title only
    assert terms == ["모듈러", "건축", "조립", "오류", "현장", "공차", "bim", "관리", "접합부", "상세"]


# ---------------------------------------------------------------------------
# Relevance
# ---------------------------------------------------------------------------


def test_score_exact_match_uses_field_weights(cfg):
    cand = _sv("X", "u", domains=["z"], nodes=[_node("n", "오류", ("조립",), summary="현장 이야기")])
    relevance, matched = score_relevance(["조립", "오류", "현장"], cand, cfg)
    assert relevance == float(Fraction(23, 30))  # (1.0 + 0.8 + 0.5) / 3, unrounded (v.6)
    assert display_value(relevance) == 0.7667
    assert matched == ["조립", "오류", "현장"]


def test_score_relevance_is_exact_for_decimal_weights(cfg):
    # tags 모듈러 + 건축 (1.0 each) + label 현장 (0.8) = 2.8 / 5. As binary floats that is 0.5599999999999999;
    # read as the decimals config writes, it is 14/25 and equal to the literal 0.56.
    cand = _sv("X", "u", domains=["z"], nodes=[_node("n", "현장", ("모듈러", "건축"))])
    assert 2.8 / 5 != 0.56  # self-check: what a float sum would give
    relevance, _ = score_relevance(["모듈러", "건축", "현장", "조립", "오류"], cand, cfg)
    assert relevance == 0.56


def test_score_takes_max_over_fields(cfg):
    cand = _sv("X", "u", domains=["z"], nodes=[_node("n", "조립", ("조립",), summary="조립")])
    assert score_relevance(["조립"], cand, cfg) == (1.0, ["조립"])


def test_score_candidate_side_josa_is_stripped(cfg):
    cand = _sv("X", "u", domains=["z"], nodes=[_node("n", "현장에서 생기는 오류를")])
    relevance, matched = score_relevance(["현장", "오류"], cand, cfg)
    assert relevance == 0.8
    assert matched == ["현장", "오류"]


def test_score_query_side_josa_matches_candidate_tag(cfg):
    cand = _sv("X", "u", domains=["z"], nodes=[_node("n", "무관", ("오류",))])
    assert score_relevance(query_terms("오류를", cfg), cand, cfg) == (1.0, ["오류"])


def test_score_substring_rule(cfg):
    tag_only = _sv("X", "u", domains=["z"], nodes=[_node("n", "무관", ("자기조립",))])
    label_only = _sv("Y", "u", domains=["z"], nodes=[_node("n", "자기조립 실험")])
    assert score_relevance(["조립"], tag_only, cfg) == (0.5, ["조립"])  # 1.0 * 0.5
    assert score_relevance(["조립"], label_only, cfg) == (0.4, ["조립"])  # 0.8 * 0.5


def test_score_single_char_term_never_substring_matches(cfg):
    cand = _sv("X", "u", domains=["z"], nodes=[_node("n", "무관", ("빵집",))])
    assert score_relevance(["빵"], cand, cfg) == (0.0, [])
    exact = _sv("Y", "u", domains=["z"], nodes=[_node("n", "무관", ("빵",))])
    assert score_relevance(["빵"], exact, cfg) == (1.0, ["빵"])


def test_score_exact_beats_substring_in_lower_field(cfg):
    # label exact (0.8) beats tags substring (1.0 * 0.5)
    cand = _sv("X", "u", domains=["z"], nodes=[_node("n", "조립", ("자기조립",))])
    assert score_relevance(["조립"], cand, cfg) == (0.8, ["조립"])


def test_score_ignores_domains_title_and_edge_summaries(cfg):
    # Relevance fields are the nodes' tags, labels and summaries only (stub docstring, D-003, ORACLE v.5 tests).
    cand = _sv(
        "X",
        "u",
        domains=["게임 디자인"],
        title="블록 노트",
        nodes=[_node("n1", "무관"), _node("n2", "무관2")],
        edges=[SubbrainEdge(source="n1", target="n2", summary="오조작 설명")],
    )
    evidence = {e.term: e for e in relevance_evidence(["게임", "블록", "오조작"], cand, cfg)}
    assert all((e.field, e.weight) == (None, 0.0) for e in evidence.values()), evidence
    assert score_relevance(["게임", "블록", "오조작"], cand, cfg) == (0.0, [])
    same_words_on_a_node = _sv(
        "Y", "u", domains=["z"], nodes=[_node("n1", "블록", ("게임",), summary="오조작"), _node("n2", "무관2")]
    )
    evidence = {e.term: e for e in relevance_evidence(["게임", "블록", "오조작"], same_words_on_a_node, cfg)}
    assert (evidence["게임"].field, evidence["게임"].weight) == ("tags", 1.0)
    assert (evidence["블록"].field, evidence["블록"].weight) == ("label", 0.8)
    assert (evidence["오조작"].field, evidence["오조작"].weight) == ("summary", 0.5)


def test_score_no_stopword_removal_on_candidates(cfg):
    cand = _sv("X", "u", domains=["z"], nodes=[_node("n", "무관", ("아이디어",))])
    assert score_relevance(["아이디어"], cand, cfg) == (1.0, ["아이디어"])


def test_score_denominator_cap_and_clamp(cfg):
    tags = ("t1", "t2", "t3", "t4", "t5", "t6")
    all_tags = _sv("X", "u", domains=["z"], nodes=[_node("n", "무관", tags)])
    one_tag = _sv("Y", "u", domains=["z"], nodes=[_node("n", "무관", ("t1",))])
    assert score_relevance(list(tags), all_tags, cfg)[0] == 1.0  # 6/5 clamped
    assert score_relevance(list(tags), one_tag, cfg) == (0.2, ["t1"])  # 1/min(6,5)
    assert score_relevance(["t1", "t9"], one_tag, cfg) == (0.5, ["t1"])  # 1/2


def test_score_empty_terms(cfg):
    assert score_relevance([], B, cfg) == (0.0, [])


def test_score_matched_terms_keep_term_order(cfg):
    _, matched = score_relevance(["오류", "없음", "조립"], B, cfg)
    assert matched == ["오류", "조립"]


def test_score_relevance_returns_plain_floats(cfg):
    relevance, _ = score_relevance(["조립", "형태", "상보"], C, cfg)
    assert type(relevance) is float  # JSON-serializable: service puts it straight into responses


def test_relevance_evidence_explains_each_term(cfg):
    evidence = relevance_evidence(["조립", "형태", "상보", "쿠폰"], C, cfg)
    assert [e.model_dump() for e in evidence] == [
        {"term": "조립", "weight": 1.0, "field": "tags", "match": "exact", "token": "조립"},
        {"term": "형태", "weight": 1.0, "field": "tags", "match": "exact", "token": "형태"},
        {"term": "상보", "weight": 0.4, "field": "label", "match": "substring", "token": "상보성"},
        {"term": "쿠폰", "weight": 0.0, "field": None, "match": None, "token": None},
    ]


# ---------------------------------------------------------------------------
# The strategy pool itself (self-checks)
# ---------------------------------------------------------------------------


def test_shaped_pool_values_are_what_the_comments_say(cfg):
    result = match(Q01, HS, POOL, max_members=0, cfg=cfg)
    got = {c.subbrain_id: (c.relevance, c.distance, c.score) for c in result.candidates}
    assert got == EXPECTED
    for sv in POOL:
        assert display_value(content_distance(HS, sv, cfg)) == EXPECTED[sv.subbrain_id][1]


# ---------------------------------------------------------------------------
# match()
# ---------------------------------------------------------------------------


def test_match_q01_topic_excludes_host_own_private_and_irrelevant(cfg):
    result = match(Q01, HOST, ALL, max_members=5, cfg=cfg)
    assert result.query_mode_used is QueryMode.TOPIC
    assert result.query_terms == ["모듈러", "건축", "현장", "조립", "오류"]
    assert result.strategy == BONUS  # v.5 default (config)
    assert result.tau == cfg.tau
    # host, own, private P never listed; candidates are listed in relevance order (models.py)
    assert [c.subbrain_id for c in result.candidates] == ["A2", "B", "C", "D"]
    assert {c.subbrain_id for c in result.selected} == {"A2", "B", "C"}
    d = _by_id(result, "D")
    assert (d.selected, d.reason, d.relevance, d.matched_terms, d.score) == (False, REASON_BELOW_TAU, 0.0, [], 0.0)
    b = _by_id(result, "B")
    assert (b.relevance, b.matched_terms, b.reason) == (0.4, ["조립", "오류"], REASON_SELECTED_SCORE)
    assert _by_id(result, "A2").relevance == 0.6  # 모듈러 + 건축 + 현장 tags
    assert all(c.relevance >= cfg.tau and c.matched_terms for c in result.selected)
    assert result.truncated is False
    # D shares no content with the host; it is far, and still never selected below tau
    assert d.distance == 1.0


def test_match_q01_distant_candidates_rank_above_close_one(cfg):
    result = match(Q01, HS, [SA2, SB, SC, SD], max_members=5, cfg=cfg)
    assert [c.subbrain_id for c in result.candidates] == ["A2", "B", "C", "D"]  # relevance order
    # distant B·C (0.4 + 0.3) rank above close A2 (0.6) (MUST-M2)
    assert [(c.subbrain_id, c.score) for c in _ranked(result)] == [("B", 0.7), ("C", 0.7), ("A2", 0.6), ("D", 0.0)]
    assert {c.subbrain_id for c in result.selected} == {"A2", "B", "C"}


def test_match_never_selects_below_tau_even_with_room(cfg):
    result = match(Q03, HOST, [B, C, D], max_members=10, cfg=cfg)
    assert result.selected == []
    assert all(c.reason == REASON_BELOW_TAU for c in result.candidates)


@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_match_tau_boundary_is_inclusive(cfg, strategy):
    one = _shaped("E", "user_x", tags=("조립",))
    result = match(Q01, HS, [one], max_members=3, cfg=cfg, strategy=strategy)
    assert _by_id(result, "E").relevance == 0.2
    assert _by_id(result, "E").reason == SELECTED_REASON[strategy]
    assert _by_id(result, "E").score == 0.5  # 0.2 + 0.3 * 1.0


def test_match_q02_auto_whole_host(cfg):
    result = match(Q02, HOST, ALL, max_members=5, cfg=cfg)
    assert result.query_mode_used is QueryMode.WHOLE_HOST
    assert result.query_terms == host_terms(HOST, cfg)
    assert "두뇌" not in result.query_terms and "평가" not in result.query_terms
    assert {c.subbrain_id for c in result.selected} == {"A2", "B", "C"}
    assert _by_id(result, "D").reason == REASON_BELOW_TAU


def test_match_explicit_whole_host_ignores_query_words(cfg):
    result = match("제빵 반죽", HOST, [B, D], max_members=5, cfg=cfg, query_mode=QueryMode.WHOLE_HOST)
    assert result.query_mode_used is QueryMode.WHOLE_HOST
    assert result.query_terms == host_terms(HOST, cfg)
    assert [c.subbrain_id for c in result.selected] == ["B"]


def test_match_explicit_topic_with_topicless_query_selects_nothing(cfg):
    result = match(Q02, HOST, [B, C], max_members=5, cfg=cfg, query_mode=QueryMode.TOPIC)
    assert result.query_mode_used is QueryMode.TOPIC
    assert result.query_terms == []
    assert result.selected == []


def test_match_accepts_string_or_none_query_mode(cfg):
    assert match(Q02, HOST, [B], max_members=1, cfg=cfg, query_mode="auto").query_mode_used is QueryMode.WHOLE_HOST
    assert match(Q01, HOST, [B], max_members=1, cfg=cfg, query_mode=None).query_mode_used is QueryMode.TOPIC
    with pytest.raises(ValueError):
        match(Q01, HOST, [B], max_members=1, cfg=cfg, query_mode="sideways")


def test_match_private_candidate_never_listed(cfg):
    result = match(Q01, HOST, [P], max_members=5, cfg=cfg)
    assert result.candidates == []
    assert result.selected == []


def test_match_truncation_relevance_only(cfg):
    result = match(Q01, HOST, [A2, B, C, D], max_members=2, cfg=cfg, strategy="relevance_only")
    assert result.strategy == "relevance_only"
    reasons = {c.subbrain_id: c.reason for c in result.candidates}
    assert reasons == {"A2": REASON_SELECTED, "B": REASON_SELECTED, "C": REASON_TRUNCATED, "D": REASON_BELOW_TAU}
    assert result.truncated is True


def test_match_diversity_swap_vs_relevance_only(cfg):
    pool = [SA2, SB, SC, SD]
    only = match(Q01, HS, pool, max_members=1, cfg=cfg, strategy="relevance_only")
    assert [c.subbrain_id for c in only.selected] == ["A2"]
    assert {c.subbrain_id: c.reason for c in only.candidates}["B"] == REASON_TRUNCATED
    # score is filled for explanation, but does not change this strategy's order
    assert [(c.subbrain_id, c.score) for c in only.candidates] == [("A2", 0.6), ("B", 0.7), ("C", 0.7), ("D", 0.0)]

    div = match(Q01, HS, pool, max_members=1, cfg=cfg, strategy="relevance_plus_diversity")
    reasons = {c.subbrain_id: c.reason for c in div.candidates}
    assert reasons == {
        "A2": REASON_DISPLACED,
        "B": REASON_DIVERSITY,  # best far candidate (tie with C broken by subbrain_id)
        "C": REASON_TRUNCATED,
        "D": REASON_BELOW_TAU,
    }
    assert [c.subbrain_id for c in div.selected] == ["B"]
    assert div.truncated is True
    # candidates stay in relevance order after the swap
    assert [c.subbrain_id for c in div.candidates] == ["A2", "B", "C", "D"]
    assert [c.score for c in div.candidates] == [0.6, 0.7, 0.7, 0.0]


def test_match_default_strategy_comes_from_config(cfg):
    only_cfg = cfg.model_copy(update={"strategy": "relevance_only"})
    result = match(Q01, HOST, [A2, B, C], max_members=1, cfg=only_cfg)
    assert result.strategy == "relevance_only"
    assert [c.subbrain_id for c in result.selected] == ["A2"]


def test_match_no_swap_when_selected_already_diverse(cfg):
    result = match(Q01, HS, [SA2, SB, SC], max_members=2, cfg=cfg, strategy="relevance_plus_diversity")
    assert {c.subbrain_id: c.reason for c in result.candidates} == {
        "A2": REASON_SELECTED,
        "B": REASON_SELECTED,
        "C": REASON_TRUNCATED,
    }
    bonus = match(Q01, HS, [SA2, SB, SC], max_members=2, cfg=cfg)
    assert [(c.subbrain_id, c.reason) for c in _ranked(bonus)] == [
        ("B", REASON_SELECTED_SCORE),
        ("C", REASON_SELECTED_SCORE),
        ("A2", REASON_TRUNCATED),
    ]


def test_match_no_swap_when_the_only_far_candidate_is_below_tau(cfg):
    # T3 is eligible but not far (1/3 < 0.5); D is far but below tau.
    result = match(Q01, HS, [SA2, T3, SD], max_members=1, cfg=cfg, strategy="relevance_plus_diversity")
    assert {c.subbrain_id: c.reason for c in result.candidates} == {
        "A2": REASON_SELECTED,
        "T3": REASON_TRUNCATED,
        "D": REASON_BELOW_TAU,  # distance 1.0 but never swapped in below tau
    }
    bonus = match(Q01, HS, [SA2, T3, SD], max_members=1, cfg=cfg)
    assert [(c.subbrain_id, c.score, c.reason) for c in _ranked(bonus)] == [
        ("A2", 0.6, REASON_SELECTED_SCORE),
        ("T3", 0.5, REASON_TRUNCATED),  # 0.4 + 0.3 * 1/3: partial distance, partial bonus
        ("D", 0.0, REASON_BELOW_TAU),
    ]


@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_match_zero_members(cfg, strategy):
    result = match(Q01, HOST, [A2, B], max_members=0, cfg=cfg, strategy=strategy)
    assert result.selected == []
    assert all(c.reason == REASON_TRUNCATED for c in result.candidates)
    assert result.truncated is True


@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_match_zero_relevance_never_selected_even_if_tau_zero(cfg, strategy):
    zero_cfg = cfg.model_copy(update={"tau": 0.0})
    result = match(Q01, HS, [SB, SD], max_members=5, cfg=zero_cfg, strategy=strategy)
    assert [c.subbrain_id for c in result.selected] == ["B"]
    assert _by_id(result, "D").reason == REASON_NO_MATCH
    assert _by_id(result, "D").score == 0.0  # distance 1.0, but zero evidence earns no bonus


def test_match_unknown_strategy_raises(cfg):
    with pytest.raises(ValueError):
        match(Q01, HOST, [B], max_members=1, cfg=cfg, strategy="random")
    with pytest.raises(ValueError):
        match(Q01, HOST, [B], max_members=1, cfg=cfg.model_copy(update={"strategy": "nope"}))


@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_match_is_deterministic_and_order_independent(cfg, strategy):
    pool = [*POOL, HS_PRIVATE, HS_OWN, HS]
    baseline = match(Q01, HS, pool, max_members=2, cfg=cfg, strategy=strategy).model_dump()
    rng = random.Random(7)
    for _ in range(10):
        shuffled = pool[:]
        rng.shuffle(shuffled)
        assert match(Q01, HS, shuffled, max_members=2, cfg=cfg, strategy=strategy).model_dump() == baseline
    assert match(Q01, HS, pool, max_members=2, cfg=cfg, strategy=strategy).model_dump() == baseline


def test_match_does_not_mutate_inputs(cfg):
    before = [sv.model_dump() for sv in [*ALL, *POOL]]
    match(Q01, HOST, ALL, max_members=1, cfg=cfg)
    match(Q01, HS, POOL, max_members=1, cfg=cfg)
    assert [sv.model_dump() for sv in [*ALL, *POOL]] == before


def test_match_with_ranking_is_match_plus_the_exact_order(cfg):
    for strategy in ALL_STRATEGIES:
        ranked = match_with_ranking(Q01, HS, POOL, max_members=3, cfg=cfg, strategy=strategy)
        assert ranked.result == match(Q01, HS, POOL, max_members=3, cfg=cfg, strategy=strategy)
        # the same objects as result.candidates, each once
        assert sorted(map(id, ranked.ranking)) == sorted(map(id, ranked.result.candidates))
        # no near ties in this pool, so the displayed values give the same order
        assert ranked.ranking == in_rank_order(ranked.result.candidates, strategy)


# ---------------------------------------------------------------------------
# relevance_with_distance_bonus (ORACLE v.5/v.6 MUST-M2)
# ---------------------------------------------------------------------------


def _order(result):
    return [c.subbrain_id for c in _ranked(result)]


def _reasons(result):
    return [(c.subbrain_id, c.reason) for c in _ranked(result)]


@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_candidates_are_listed_in_relevance_order_for_every_strategy(cfg, strategy):
    # models.py: MatchResult.candidates is "sorted by relevance desc"; the ranking is in_rank_order's job.
    for max_members in (0, 1, 2, 10):
        result = match(Q01, HS, POOL, max_members=max_members, cfg=cfg, strategy=strategy)
        keys = [(-c.relevance, c.subbrain_id, c.version) for c in result.candidates]
        assert keys == sorted(keys)


def test_in_rank_order_follows_the_strategy(cfg):
    result = match(Q01, HS, [SA2, SB, SC, SD], max_members=10, cfg=cfg)
    assert [c.subbrain_id for c in in_rank_order(result.candidates, BONUS)] == ["B", "C", "A2", "D"]
    for name in ("relevance_plus_diversity", "relevance_only", "unknown"):
        assert [c.subbrain_id for c in in_rank_order(result.candidates, name)] == ["A2", "B", "C", "D"]
    assert [c.subbrain_id for c in result.candidates] == ["A2", "B", "C", "D"]  # not reordered in place


def test_bonus_is_the_configured_default_and_registered(cfg):
    assert cfg.strategy == BONUS
    assert cfg.distance_bonus == 0.3
    assert (cfg.distance_saturation, cfg.far_distance) == (0.25, 0.5)  # v.6 config, unchanged in v.7
    assert set(ALL_STRATEGIES) == set(STRATEGIES) == set(cfg.strategies_available)


def test_score_formula_and_gate(cfg):
    result = match(Q01, HS, [M75, SA2, WEAK_FAR, SD], max_members=5, cfg=cfg)
    m75 = _by_id(result, "M75")
    assert (m75.relevance, m75.distance, m75.score) == (0.4, 0.75, 0.625)  # 0.4 + 0.3 * 0.75
    assert _by_id(result, "A2").score == 0.6  # distance 0: no bonus
    assert _by_id(result, "W").score == 0.0  # below tau: no bonus
    zero = match(Q01, HS, [SD], max_members=5, cfg=cfg.model_copy(update={"tau": 0.0}))
    assert _by_id(zero, "D").score == 0.0  # zero evidence: no bonus


def test_bonus_same_relevance_distant_is_above(cfg):
    # 건축 (tag 1.0) + 오류 (summary 0.5) = 0.3 at distance 0; 조립 (tag) + 오류 (summary) = 0.3 at distance 1
    close = _shaped("A-close", "user_y", tags=("건축",), summary=("오류",), shared=12)
    far = _shaped("Z-far", "user_z", tags=("조립",), summary=("오류",))
    result = match(Q01, HS, [close, far], max_members=1, cfg=cfg)
    # Same relevance 0.3; subbrain_id alone would put A-close first, the distance bonus puts Z-far first.
    assert [(c.subbrain_id, c.relevance, c.distance, c.score) for c in _ranked(result)] == [
        ("Z-far", 0.3, 1.0, 0.6),
        ("A-close", 0.3, 0.0, 0.3),
    ]
    assert _reasons(result) == [("Z-far", REASON_SELECTED_SCORE), ("A-close", REASON_TRUNCATED)]


def test_bonus_same_score_higher_relevance_is_above(cfg):
    # FAR_LOW 0.3 + 0.3 == NEAR_HIGH 0.6 + 0; subbrain_id alone would put A-far first.
    result = match(Q01, HS, [FAR_LOW, NEAR_HIGH], max_members=1, cfg=cfg)
    assert [(c.subbrain_id, c.relevance, c.score) for c in _ranked(result)] == [
        ("Z-near", 0.6, 0.6),
        ("A-far", 0.3, 0.6),
    ]
    # Z-near is selected but not far, so the diversity guarantee swaps A-far in.
    assert _reasons(result) == [("Z-near", REASON_DISPLACED), ("A-far", REASON_DIVERSITY)]


def test_bonus_same_score_and_relevance_by_subbrain_id(cfg):
    for pool in ([SC, SB], [SB, SC]):
        result = match(Q01, HS, pool, max_members=1, cfg=cfg)
        assert _reasons(result) == [("B", REASON_SELECTED_SCORE), ("C", REASON_TRUNCATED)]


def test_bonus_diversity_swap_replaces_lowest_ranked_selected(cfg):
    one = match(Q01, HS, [SA2, SC, SB, NEAR], max_members=1, cfg=cfg)
    assert [(c.subbrain_id, c.score) for c in _ranked(one)] == [("N", 1.0), ("B", 0.7), ("C", 0.7), ("A2", 0.6)]
    assert _reasons(one) == [
        ("N", REASON_DISPLACED),
        ("B", REASON_DIVERSITY),  # best far eligible candidate
        ("C", REASON_TRUNCATED),
        ("A2", REASON_TRUNCATED),
    ]
    assert one.truncated is True

    two = match(Q01, HS, [SA2, SC, SB, A4, NEAR], max_members=2, cfg=cfg)
    assert [(c.subbrain_id, c.score) for c in _ranked(two)] == [
        ("N", 1.0),
        ("A4", 0.7),  # ties B·C on score, wins on relevance (0.6)
        ("B", 0.7),
        ("C", 0.7),
        ("A2", 0.6),
    ]
    assert _reasons(two) == [
        ("N", REASON_SELECTED_SCORE),
        ("A4", REASON_DISPLACED),  # lowest-ranked selected (distance 1/3 is not far)
        ("B", REASON_DIVERSITY),
        ("C", REASON_TRUNCATED),
        ("A2", REASON_TRUNCATED),
    ]


@pytest.mark.parametrize("max_members", [1, 2, 10])
def test_bonus_never_lifts_a_below_tau_candidate(cfg, max_members):
    result = match(Q01, HS, [SA2, WEAK_FAR], max_members=max_members, cfg=cfg)
    w = _by_id(result, "W")
    assert (w.relevance, w.distance) == (0.1, 1.0)  # self-check: 0.1 + 0.3 would clear tau
    assert (w.score, w.selected, w.reason) == (0.0, False, REASON_BELOW_TAU)
    assert _reasons(result)[0] == ("A2", REASON_SELECTED_SCORE)  # no diversity swap with a below-tau candidate


def test_bonus_whole_host_close_candidate_still_on_top(cfg):
    # whole_host terms come from the host, so the candidate closest in content is also the most relevant
    result = match(Q02, HOST, ALL, max_members=5, cfg=cfg)
    assert result.query_mode_used is QueryMode.WHOLE_HOST
    ranked = _ranked(result)
    assert ranked[0].subbrain_id == "A2"
    assert ranked[0].distance == 0.0 and ranked[0].relevance == max(c.relevance for c in result.candidates)
    assert {c.subbrain_id for c in result.selected} == {"A2", "B", "C"}


def test_bonus_score_is_filled_for_every_strategy(cfg):
    for strategy in ALL_STRATEGIES:
        result = match(Q01, HS, [SA2, A3, SB, SD, WEAK_FAR], max_members=5, cfg=cfg, strategy=strategy)
        assert {c.subbrain_id: c.score for c in result.candidates} == {
            "A2": 0.6,
            "A3": 0.75,
            "B": 0.7,
            "D": 0.0,
            "W": 0.0,
        }, strategy


@pytest.mark.parametrize("max_members", [0, 1, 2, 3, 10])
def test_bonus_with_zero_bonus_behaves_like_relevance_plus_diversity(cfg, max_members):
    zero = cfg.model_copy(update={"distance_bonus": 0.0})
    bonus = match(Q01, HS, POOL, max_members=max_members, cfg=zero, strategy=BONUS)
    div = match(Q01, HS, POOL, max_members=max_members, cfg=zero, strategy="relevance_plus_diversity")
    assert _order(bonus) == _order(div)
    relabel = {REASON_SELECTED_SCORE: REASON_SELECTED}
    assert [(i, relabel.get(r, r)) for i, r in _reasons(bonus)] == _reasons(div)
    assert all(c.score == (c.relevance if c.relevance >= cfg.tau else 0.0) for c in bonus.candidates)


def test_bonus_invariants_on_random_pools(cfg):
    pool = [*POOL, HS_PRIVATE, HS_OWN]
    rng = random.Random(2026)
    for _ in range(200):
        sample = rng.sample(pool, rng.randint(0, len(pool)))
        max_members = rng.randint(0, 5)
        ranked = match_with_ranking(Q01, HS, sample, max_members=max_members, cfg=cfg)
        result, cands = ranked.result, ranked.ranking
        listed = [(-c.relevance, c.subbrain_id) for c in result.candidates]
        assert listed == sorted(listed)  # models.py: listed in relevance order
        keys = [(-c.score, -c.relevance, c.subbrain_id) for c in cands]
        assert keys == sorted(keys)
        eligible = [c for c in cands if c.relevance >= cfg.tau and c.relevance > 0]
        for c in cands:
            assert c.subbrain_id not in ("H-own", "P")
            expected = c.relevance + cfg.distance_bonus * c.distance if c in eligible else 0.0
            assert c.score == pytest.approx(expected, abs=2e-4)
            if c.selected:
                assert c in eligible and c.matched_terms
        selected = [c for c in cands if c.selected]  # in rank order
        assert len(selected) == min(max_members, len(eligible))
        top = eligible[:max_members]
        if any(c.reason == REASON_DIVERSITY for c in cands):
            assert not any(c.distance >= cfg.far_distance for c in top)
            assert [c.reason for c in cands].count(REASON_DISPLACED) == 1
            assert next(c for c in cands if c.reason == REASON_DISPLACED) is top[-1]
            swapped = next(c for c in cands if c.reason == REASON_DIVERSITY)
            assert swapped.distance >= cfg.far_distance
            assert swapped is next(c for c in eligible[max_members:] if c.distance >= cfg.far_distance)
        else:
            assert selected == top
        assert result.truncated is (len(eligible) > max_members)


# ---------------------------------------------------------------------------
# v.6: "far" is distance >= far_distance (config), not distance == 1.0
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("strategy", [BONUS, "relevance_plus_diversity"])
def test_far_boundary_is_inclusive_for_a_selected_member(cfg, strategy):
    # A3 (0.6, distance exactly 0.5) and N (1.0, distance 0) fill both slots: A3 already counts as far.
    result = match(Q01, HS, [NEAR, A3, SB], max_members=2, cfg=cfg, strategy=strategy)
    assert {c.subbrain_id: c.reason for c in result.candidates} == {
        "N": SELECTED_REASON[strategy],
        "A3": SELECTED_REASON[strategy],
        "B": REASON_TRUNCATED,  # distance 1.0 but not needed
    }


@pytest.mark.parametrize("strategy", [BONUS, "relevance_plus_diversity"])
def test_far_boundary_is_inclusive_for_a_swapped_in_candidate(cfg, strategy):
    # N is close; A3 at exactly 0.5 is the only far candidate and gets swapped in.
    result = match(Q01, HS, [NEAR, A3], max_members=1, cfg=cfg, strategy=strategy)
    assert {c.subbrain_id: c.reason for c in result.candidates} == {"N": REASON_DISPLACED, "A3": REASON_DIVERSITY}


@pytest.mark.parametrize("strategy", [BONUS, "relevance_plus_diversity"])
def test_far_candidate_below_one_is_swapped_in(cfg, strategy):
    # M75 (distance 0.75) shares content with the host, so it is not "nothing in common"; since v.6 it is far.
    # N (1.0) and A5 (0.8) are close and outrank it in both strategies.
    result = match(Q01, HS, [NEAR, A5, M75], max_members=2, cfg=cfg, strategy=strategy)
    assert {c.subbrain_id: c.reason for c in result.candidates} == {
        "N": SELECTED_REASON[strategy],
        "A5": REASON_DISPLACED,
        "M75": REASON_DIVERSITY,
    }


@pytest.mark.parametrize("strategy", [BONUS, "relevance_plus_diversity"])
def test_far_distance_is_read_from_config(cfg, strategy):
    strict = cfg.model_copy(update={"far_distance": 0.8})  # M75 (0.75) is no longer far
    result = match(Q01, HS, [NEAR, A5, M75], max_members=2, cfg=strict, strategy=strategy)
    assert {c.subbrain_id: c.reason for c in result.candidates} == {
        "N": SELECTED_REASON[strategy],
        "A5": SELECTED_REASON[strategy],
        "M75": REASON_TRUNCATED,
    }
    lenient = cfg.model_copy(update={"far_distance": 0.3})  # A4 (1/3) now counts as far: nothing to swap
    result = match(Q01, HS, [NEAR, A4, SB], max_members=2, cfg=lenient, strategy=strategy)
    assert {c.subbrain_id: c.reason for c in result.candidates} == {
        "N": SELECTED_REASON[strategy],
        "A4": SELECTED_REASON[strategy],
        "B": REASON_TRUNCATED,
    }


# ---------------------------------------------------------------------------
# v.6: ranking and τ compare unrounded (exact) values; rounding is for display only
# ---------------------------------------------------------------------------


def test_display_rounding_is_four_decimals(cfg):
    assert DISPLAY_DECIMALS == 4
    cand = _shaped("S", "user_s", label=("자기조립",), shared=8)
    result = match("조립 모듈러 건축", HS, [cand], max_members=1, cfg=cfg.model_copy(update={"tau": 0.1}))
    s = _by_id(result, "S")
    # relevance 0.4 / 3 = 2/15, distance 1 - (8/48) / 0.25 = 1/3, score 2/15 + 0.1 = 7/30
    assert (s.relevance, s.distance, s.score) == (0.1333, 0.3333, 0.2333)


@pytest.mark.parametrize(("tau", "eligible"), [(0.13333, True), (0.13334, False)])
def test_tau_compares_unrounded_relevance(cfg, tau, eligible):
    # relevance 2/15 = 0.133333...: shown as 0.1333, which is below 0.13333 — the exact value is not.
    cand = _shaped("S", "user_s", label=("자기조립",))
    result = match("조립 모듈러 건축", HS, [cand], max_members=1, cfg=cfg.model_copy(update={"tau": tau}))
    s = _by_id(result, "S")
    assert s.relevance == 0.1333
    assert s.selected is eligible
    assert s.reason == (SELECTED_REASON[BONUS] if eligible else REASON_BELOW_TAU)
    assert (s.score > 0) is eligible


def test_tau_equal_to_an_exact_decimal_relevance_is_inclusive(cfg):
    # 2.8 / 5 is 0.5599999999999999 as floats; exactly 0.56 is "τ 이상" when τ is 0.56.
    cand = _shaped("X", "user_x", tags=("모듈러", "건축"), label=("현장",))
    result = match(Q01, HS, [cand], max_members=1, cfg=cfg.model_copy(update={"tau": 0.56}))
    assert _by_id(result, "X").selected is True
    assert _by_id(result, "X").relevance == 0.56


@pytest.mark.parametrize(("bonus", "first"), [(0.20004, "Y"), (0.19996, "X")])
def test_ranking_uses_unrounded_scores(cfg, bonus, first):
    # X: 0.6 at distance 0 -> 0.6. Y: 0.4 at distance 1 -> 0.4 + bonus = 0.60004 or 0.59996.
    # Both show score 0.6; the exact values decide.
    x = _shaped("X", "user_x", tags=("모듈러", "현장", "건축"), shared=12)
    y = _shaped("Y", "user_y", tags=("조립", "오류"))
    custom = cfg.model_copy(update={"distance_bonus": bonus})
    ranked = match_with_ranking(Q01, HS, [x, y], max_members=1, cfg=custom)
    assert [c.score for c in ranked.result.candidates] == [0.6, 0.6]
    assert ranked.ranking[0].subbrain_id == first
    reasons = {c.subbrain_id: c.reason for c in ranked.result.candidates}
    if first == "Y":
        # Y wins on score and is far: no swap needed
        assert reasons == {"Y": REASON_SELECTED_SCORE, "X": REASON_TRUNCATED}
        # in_rank_order only sees the displayed tie and falls back to relevance
        assert [c.subbrain_id for c in in_rank_order(ranked.result.candidates, BONUS)] == ["X", "Y"]
    else:
        # X wins on score, is close, so Y is swapped in by the diversity guarantee
        assert reasons == {"X": REASON_DISPLACED, "Y": REASON_DIVERSITY}


def test_mathematical_score_tie_is_exact_and_broken_by_relevance(cfg):
    # X: 2.8/5 = 0.56 at distance 0 -> 0.56. Y: (0.8 + 0.5)/5 = 0.26 at distance 1 -> 0.26 + 0.3 = 0.56.
    # As floats X would be 0.5599999999999999 and Y 0.56, putting Y first; exactly they tie and X wins on relevance.
    x = _shaped("X", "user_x", tags=("모듈러", "건축"), label=("현장",), shared=12)
    y = _shaped("Y", "user_y", label=("조립",), summary=("오류",))
    assert (2.8 / 5, (0.8 + 0.5) / 5 + 0.3) == (0.5599999999999999, 0.56)  # self-check: float noise
    ranked = match_with_ranking(Q01, HS, [y, x, SB], max_members=2, cfg=cfg)
    assert [(c.subbrain_id, c.relevance, c.distance, c.score) for c in ranked.ranking] == [
        ("B", 0.4, 1.0, 0.7),
        ("X", 0.56, 0.0, 0.56),
        ("Y", 0.26, 1.0, 0.56),
    ]
    assert {c.subbrain_id: c.reason for c in ranked.result.candidates} == {
        "B": REASON_SELECTED_SCORE,
        "X": REASON_SELECTED_SCORE,
        "Y": REASON_TRUNCATED,
    }


def test_same_relevance_from_terms_in_a_different_order_ties_exactly(cfg):
    # Same weights (1.0, 0.8, 0.5) on different terms, so summed in a different order; exactly they are equal and
    # the tie goes to subbrain_id.
    first = _shaped("K1", "user_k1", tags=("오류",), label=("모듈러",), summary=("건축",))
    second = _shaped("K2", "user_k2", tags=("모듈러",), label=("오류",), summary=("건축",))
    result = match(Q01, HS, [second, first], max_members=1, cfg=cfg, strategy="relevance_only")
    assert [c.relevance for c in result.candidates] == [0.46, 0.46]
    assert [(c.subbrain_id, c.reason) for c in result.candidates] == [("K1", REASON_SELECTED), ("K2", REASON_TRUNCATED)]
