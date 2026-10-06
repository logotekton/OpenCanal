"""Unit tests for opencanal.matching (Builder M). Hand-built SubbrainVersions, no store."""

from __future__ import annotations

import random

import pytest

from opencanal.config import MatchingConfig, load_config
from opencanal.matching import (
    REASON_BELOW_TAU,
    REASON_DISPLACED,
    REASON_DIVERSITY,
    REASON_NO_MATCH,
    REASON_SELECTED,
    REASON_TRUNCATED,
    domain_distance,
    host_terms,
    match,
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
A2 = _sv(  # close to host (same domains), shares 모듈러 + 건축(domain) + 현장
    "A2",
    "user_e",
    domains=["건축", "BIM"],
    nodes=[_node("e1", "모듈러 유닛 운송", ("모듈러", "운송", "현장"))],
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


def _by_id(result, subbrain_id):
    return next(c for c in result.candidates if c.subbrain_id == subbrain_id)


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
    assert relevance == round((1.0 + 0.8 + 0.5) / 3, 4) == 0.7667
    assert matched == ["조립", "오류", "현장"]


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


def test_score_counts_domains_title_and_edge_summaries(cfg):
    cand = _sv(
        "X",
        "u",
        domains=["게임 디자인"],
        title="블록 노트",
        nodes=[_node("n1", "무관"), _node("n2", "무관2")],
        edges=[SubbrainEdge(source="n1", target="n2", summary="오조작 설명")],
    )
    evidence = {e.term: e for e in relevance_evidence(["게임", "블록", "오조작"], cand, cfg)}
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


def test_relevance_evidence_explains_each_term(cfg):
    evidence = relevance_evidence(["조립", "형태", "상보", "쿠폰"], C, cfg)
    assert [e.model_dump() for e in evidence] == [
        {"term": "조립", "weight": 1.0, "field": "tags", "match": "exact", "token": "조립"},
        {"term": "형태", "weight": 1.0, "field": "tags", "match": "exact", "token": "형태"},
        {"term": "상보", "weight": 0.4, "field": "label", "match": "substring", "token": "상보성"},
        {"term": "쿠폰", "weight": 0.0, "field": None, "match": None, "token": None},
    ]


# ---------------------------------------------------------------------------
# Domain distance
# ---------------------------------------------------------------------------


def test_domain_distance(cfg):
    assert domain_distance(HOST, A2) == 0.0
    assert domain_distance(HOST, B) == 1.0
    half = _sv("X", "u", domains=["건축"], nodes=[_node("n", "x")])
    assert domain_distance(HOST, half) == 0.5
    third = _sv("Y", "u", domains=["건축", "조경"], nodes=[_node("n", "x")])
    assert domain_distance(HOST, third) == 0.6667  # 1 - 1/3


def test_domain_distance_normalizes(cfg):
    upper = _sv("X", "u", domains=["  bim ", "건축!"], nodes=[_node("n", "x")])
    assert domain_distance(HOST, upper) == 0.0


def test_domain_distance_both_empty_after_normalize(cfg):
    a = _sv("X", "u", domains=["!!"], nodes=[_node("n", "x")])
    b = _sv("Y", "u", domains=[" "], nodes=[_node("n", "x")])
    assert domain_distance(a, b) == 1.0


# ---------------------------------------------------------------------------
# match()
# ---------------------------------------------------------------------------


def test_match_q01_topic_excludes_host_own_private_and_irrelevant(cfg):
    result = match(Q01, HOST, ALL, max_members=5, cfg=cfg)
    assert result.query_mode_used is QueryMode.TOPIC
    assert result.query_terms == ["모듈러", "건축", "현장", "조립", "오류"]
    assert result.strategy == "relevance_plus_diversity"
    assert result.tau == cfg.tau
    ids = [c.subbrain_id for c in result.candidates]
    assert ids == ["A2", "B", "C", "D"]  # host, own, private P never listed
    assert {c.subbrain_id for c in result.selected} == {"A2", "B", "C"}
    d = _by_id(result, "D")
    assert (d.selected, d.reason, d.relevance, d.matched_terms) == (False, REASON_BELOW_TAU, 0.0, [])
    b = _by_id(result, "B")
    assert (b.relevance, b.distance, b.matched_terms, b.reason) == (0.4, 1.0, ["조립", "오류"], REASON_SELECTED)
    assert _by_id(result, "A2").relevance == 0.6  # 모듈러 + 건축(domain) + 현장
    assert all(c.relevance >= cfg.tau and c.matched_terms for c in result.selected)
    assert result.truncated is False


def test_match_never_selects_below_tau_even_with_room(cfg):
    result = match(Q03, HOST, [B, C, D], max_members=10, cfg=cfg)
    assert result.selected == []
    assert all(c.reason == REASON_BELOW_TAU for c in result.candidates)


def test_match_tau_boundary_is_inclusive(cfg):
    one = _sv("E", "user_x", domains=["z"], nodes=[_node("n", "무관", ("공차",))])
    result = match("공차 모듈러 현장 조립 오류", HOST, [one], max_members=3, cfg=cfg)
    assert _by_id(result, "E").relevance == 0.2
    assert _by_id(result, "E").reason == REASON_SELECTED


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
    only = match(Q01, HOST, [A2, B, C, D], max_members=1, cfg=cfg, strategy="relevance_only")
    assert [c.subbrain_id for c in only.selected] == ["A2"]
    assert {c.subbrain_id: c.reason for c in only.candidates}["B"] == REASON_TRUNCATED

    div = match(Q01, HOST, [A2, B, C, D], max_members=1, cfg=cfg, strategy="relevance_plus_diversity")
    reasons = {c.subbrain_id: c.reason for c in div.candidates}
    assert reasons == {
        "A2": REASON_DISPLACED,
        "B": REASON_DIVERSITY,  # best distance-1.0 candidate (tie with C broken by subbrain_id)
        "C": REASON_TRUNCATED,
        "D": REASON_BELOW_TAU,
    }
    assert [c.subbrain_id for c in div.selected] == ["B"]
    assert div.truncated is True
    # candidates stay in relevance order after the swap
    assert [c.subbrain_id for c in div.candidates] == ["A2", "B", "C", "D"]


def test_match_default_strategy_comes_from_config(cfg):
    only_cfg = cfg.model_copy(update={"strategy": "relevance_only"})
    result = match(Q01, HOST, [A2, B, C], max_members=1, cfg=only_cfg)
    assert result.strategy == "relevance_only"
    assert [c.subbrain_id for c in result.selected] == ["A2"]


def test_match_no_swap_when_selected_already_diverse(cfg):
    result = match(Q01, HOST, [A2, B, C], max_members=2, cfg=cfg)
    assert {c.subbrain_id: c.reason for c in result.candidates} == {
        "A2": REASON_SELECTED,
        "B": REASON_SELECTED,
        "C": REASON_TRUNCATED,
    }


def test_match_no_swap_when_diverse_candidate_below_tau(cfg):
    near = _sv("A3", "user_f", domains=["건축"], nodes=[_node("n", "무관", ("모듈러", "현장"))])
    result = match(Q01, HOST, [A2, near, D], max_members=1, cfg=cfg)
    assert {c.subbrain_id: c.reason for c in result.candidates} == {
        "A2": REASON_SELECTED,
        "A3": REASON_TRUNCATED,
        "D": REASON_BELOW_TAU,  # distance 1.0 but never swapped in below tau
    }


def test_match_zero_members(cfg):
    result = match(Q01, HOST, [A2, B], max_members=0, cfg=cfg)
    assert result.selected == []
    assert all(c.reason == REASON_TRUNCATED for c in result.candidates)
    assert result.truncated is True


def test_match_zero_relevance_never_selected_even_if_tau_zero(cfg):
    zero_cfg = cfg.model_copy(update={"tau": 0.0})
    result = match(Q01, HOST, [B, D], max_members=5, cfg=zero_cfg)
    assert [c.subbrain_id for c in result.selected] == ["B"]
    assert _by_id(result, "D").reason == REASON_NO_MATCH


def test_match_unknown_strategy_raises(cfg):
    with pytest.raises(ValueError):
        match(Q01, HOST, [B], max_members=1, cfg=cfg, strategy="random")
    with pytest.raises(ValueError):
        match(Q01, HOST, [B], max_members=1, cfg=cfg.model_copy(update={"strategy": "nope"}))


def test_match_is_deterministic_and_order_independent(cfg):
    pool = [A2, B, C, D, P, OWN_OTHER, HOST]
    baseline = match(Q01, HOST, pool, max_members=2, cfg=cfg).model_dump()
    rng = random.Random(7)
    for _ in range(10):
        shuffled = pool[:]
        rng.shuffle(shuffled)
        assert match(Q01, HOST, shuffled, max_members=2, cfg=cfg).model_dump() == baseline
    assert match(Q01, HOST, pool, max_members=2, cfg=cfg).model_dump() == baseline


def test_match_does_not_mutate_inputs(cfg):
    before = [sv.model_dump() for sv in ALL]
    match(Q01, HOST, ALL, max_members=1, cfg=cfg)
    assert [sv.model_dump() for sv in ALL] == before
