"""MUST-M1 τ boundary, NEVER-08, and MUST-M3 v.4 topicless variants Q-02a..d (ORACLE §5.4, §6.2).

Weak candidates are built so that their relevance under the frozen formula (matching stub docstring +
config/matching.json) is strictly between 0 and τ. The expected value is computed twice: by hand in the table
below and by an independent reference implementation of the formula (_v4.reference_relevance).
"""

from __future__ import annotations

import pytest

from opencanal.models import QueryMode, Tier

from .conftest import (
    Q01,
    Q01_TERMS,
    Q02,
    World,
    assert_err,
    assert_ok,
    current_month,
    dumps,
    find_dicts,
    fixture_sid,
    fixture_version,
    member_ids,
)
from ._v4 import reference_relevance, version_from_doc

# ---------------------------------------------------------------------------
# Weak candidates (Q-01 terms: 모듈러, 건축, 현장, 조립, 오류 -> denominator 5)
# ---------------------------------------------------------------------------

WEAK_DOCS: dict[str, dict] = {
    # one exact label hit "현장": 0.8 / 5
    "W_LABEL": {
        "title": "하천 측량 일지",
        "domains": ["도시 계획"],
        "nodes": [
            {"id": "w-n1", "label": "현장 측량 일지", "tags": ["하천", "측량"], "summary": "하천 둑 높이를 재는 기록."},
            {"id": "w-n2", "label": "수위 표척", "tags": ["수위"], "summary": "눈금 막대로 물 높이를 읽는다."},
        ],
        "edges": [{"id": "w-e1", "source": "w-n2", "target": "w-n1", "relation": "feeds"}],
    },
    # substring-only hit: "조립" inside the tag token "조립식": 1.0 * 0.5 / 5
    "W_SUB": {
        "title": "가설 창고 배치 메모",
        "domains": ["물류"],
        "nodes": [
            {"id": "w-n1", "label": "가설 창고 배치", "tags": ["조립식", "창고"], "summary": "자재를 쌓아 둘 창고 위치를 정한다."},
            {"id": "w-n2", "label": "지게차 동선", "tags": ["지게차"], "summary": "통로 폭을 넉넉히 잡는다."},
        ],
        "edges": [{"id": "w-e1", "source": "w-n2", "target": "w-n1", "relation": "serves"}],
    },
    # two substring-only hits: tag "조립식" (0.5) + label token "오류율" (0.8 * 0.5): 0.9 / 5
    "W_TWO": {
        "title": "인쇄 공정 점검표",
        "domains": ["인쇄"],
        "nodes": [
            {"id": "w-n1", "label": "오류율 표", "tags": ["조립식", "인쇄"], "summary": "잉크 번짐 건수를 주마다 센다."},
            {"id": "w-n2", "label": "용지 보관", "tags": ["용지"], "summary": "습기를 피해 선반 위에 둔다."},
        ],
        "edges": [{"id": "w-e1", "source": "w-n2", "target": "w-n1", "relation": "affects"}],
    },
    # one exact summary hit "건축": 0.5 / 5
    "W_SUM": {
        "title": "서류 보관 규칙",
        "domains": ["사무 행정"],
        "nodes": [
            {"id": "w-n1", "label": "허가 서류철", "tags": ["서류", "보관"], "summary": "건축 허가 서류를 한곳에 모은다."},
            {"id": "w-n2", "label": "문서 번호", "tags": ["번호"], "summary": "접수 순서대로 번호를 붙인다."},
        ],
        "edges": [{"id": "w-e1", "source": "w-n2", "target": "w-n1", "relation": "indexes"}],
    },
}
WEAK_EXPECTED = {"W_LABEL": 0.16, "W_SUB": 0.10, "W_TWO": 0.18, "W_SUM": 0.10}

# exactly τ: one exact tag hit "현장": 1.0 / 5 = 0.2 (MUST-M1 "τ 이상")
AT_TAU_DOC = {
    "title": "하천 정비 메모",
    "domains": ["도시 계획"],
    "nodes": [
        {"id": "t-n1", "label": "제방 보강 순서", "tags": ["현장", "제방"], "summary": "흙을 다지고 돌망태를 쌓는다."},
        {"id": "t-n2", "label": "배수 펌프", "tags": ["배수"], "summary": "비 오기 전에 미리 돌려 본다."},
    ],
    "edges": [{"id": "t-e1", "source": "t-n2", "target": "t-n1", "relation": "protects"}],
}


def _weak_version(name: str):
    return version_from_doc(WEAK_DOCS[name], subbrain_id=f"sb_{name}", owner_id=f"user_{name.lower()}")


def _match(query, candidates, cfg, *, max_members=3, strategy=None, query_mode=QueryMode.AUTO):
    from opencanal import matching

    return matching.match(
        query,
        fixture_version("A"),
        candidates,
        max_members=max_members,
        cfg=cfg.matching,
        query_mode=query_mode,
        strategy=strategy,
    )


# ---------------------------------------------------------------------------
# MUST-M1 — the formula gives 0 < relevance < τ for the weak candidates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(WEAK_DOCS))
def test_must_m1_v4_weak_candidate_relevance_is_between_zero_and_tau(cfg, name):
    from opencanal import matching

    tau = cfg.matching.tau
    ref, ref_terms = reference_relevance(Q01_TERMS, WEAK_DOCS[name], cfg.matching)
    assert ref == pytest.approx(WEAK_EXPECTED[name]), "self-check: hand value == reference formula"
    assert 0 < ref < tau, "self-check: the candidate is weak but not zero"

    rel, terms = matching.score_relevance(Q01_TERMS, _weak_version(name), cfg.matching)
    assert rel == pytest.approx(WEAK_EXPECTED[name])
    assert set(terms) <= set(Q01_TERMS)


def test_must_m1_v4_at_tau_candidate_relevance(cfg):
    from opencanal import matching

    ref, _ = reference_relevance(Q01_TERMS, AT_TAU_DOC, cfg.matching)
    assert ref == pytest.approx(cfg.matching.tau)
    rel, terms = matching.score_relevance(
        Q01_TERMS, version_from_doc(AT_TAU_DOC, subbrain_id="sb_T", owner_id="user_t"), cfg.matching
    )
    assert rel == pytest.approx(cfg.matching.tau)
    assert set(terms) == {"현장"}


# ---------------------------------------------------------------------------
# MUST-M1 — a candidate with 0 < relevance < τ is never selected (pure match)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("strategy", ["relevance_only", "relevance_plus_diversity"])
@pytest.mark.parametrize("max_members", [1, 3, 10])
def test_must_m1_v4_below_tau_never_selected_by_match(cfg, strategy, max_members):
    weak = [_weak_version(n) for n in sorted(WEAK_DOCS)]
    result = _match(Q01, [fixture_version("A2"), *weak], cfg, max_members=max_members, strategy=strategy)
    selected = {c.subbrain_id for c in result.candidates if c.selected}
    assert selected == {fixture_sid("A2")}, f"only A2 (0.56) reaches τ; selected {selected}"
    for c in result.candidates:
        if c.subbrain_id.startswith("sb_W_"):
            assert c.selected is False
            assert 0 < c.relevance < cfg.matching.tau


def test_must_m1_v4_diversity_swap_never_brings_in_a_below_tau_candidate(cfg):
    """A2 is domain-close (distance 0); every weak candidate is domain-distant (distance 1.0) but below τ.

    relevance_plus_diversity may swap in a distance-1.0 candidate only if its relevance >= τ (stub docstring).
    """
    weak = [_weak_version(n) for n in sorted(WEAK_DOCS)]
    for max_members in (1, 2):
        result = _match(Q01, [fixture_version("A2"), *weak], cfg, max_members=max_members, strategy="relevance_plus_diversity")
        by_id = {c.subbrain_id: c for c in result.candidates}
        assert by_id[fixture_sid("A2")].distance == pytest.approx(0.0)
        for name in WEAK_DOCS:
            assert by_id[f"sb_{name}"].distance == pytest.approx(1.0), "self-check: weak candidates are domain-distant"
        assert {c.subbrain_id for c in result.candidates if c.selected} == {fixture_sid("A2")}


def test_must_m1_v4_at_tau_candidate_is_selectable(cfg):
    at_tau = version_from_doc(AT_TAU_DOC, subbrain_id="sb_T", owner_id="user_t")
    result = _match(Q01, [at_tau, *[_weak_version(n) for n in sorted(WEAK_DOCS)]], cfg, max_members=10, strategy="relevance_only")
    assert {c.subbrain_id for c in result.candidates if c.selected} == {"sb_T"}, "relevance == τ is 'τ 이상'"


# ---------------------------------------------------------------------------
# MUST-M1 / NEVER-08 — through Service.dispatch
# ---------------------------------------------------------------------------


def _publish_doc(world: World, user_id: str, doc: dict) -> str:
    if user_id not in world.tokens:
        world.add_user(user_id)
    env = assert_ok(world.import_doc(user_id, doc))
    assert_ok(
        world.call(user_id, "subbrain_set_visibility", subbrain_id=env["subbrain_id"], visibility="public", confirm_hash=env["content_hash"])
    )
    return env["subbrain_id"]


def _publish_weak(world: World) -> dict[str, str]:
    return {name: _publish_doc(world, f"user_{name.lower()}", WEAK_DOCS[name]) for name in sorted(WEAK_DOCS)}


def test_must_m1_v4_canal_open_never_includes_below_tau_even_with_room(seeded: World):
    weak = _publish_weak(seeded)
    seeded.set_tier("user_a", Tier.EXPERT)  # 10 members: truncation cannot explain an absence
    env = assert_ok(seeded.open_canal(query=Q01))
    ids = set(member_ids(env))
    assert {seeded.sid("A2"), seeded.sid("B"), seeded.sid("C")} <= ids
    assert not ids & set(weak.values()), "a candidate with 0 < relevance < τ became a canal member"
    for m in env["members"]:
        assert m["relevance"] >= seeded.cfg.matching.tau

    search = assert_ok(seeded.call("user_a", "subbrain_search", query=Q01, limit=20))
    found = {r["subbrain_id"] for r in search["untrusted_data"]["results"]}
    assert not found & set(weak.values()), "subbrain_search returns relevance >= τ only"

    explain = assert_ok(seeded.call("user_a", "match_explain", query=Q01, host_subbrain_id=seeded.sid("A")))
    cands = {c["subbrain_id"]: c for c in find_dicts(explain, lambda d: "subbrain_id" in d and "selected" in d and "relevance" in d)}
    for name, sid in weak.items():
        assert sid in cands, "match_explain lists below-τ candidates"
        assert cands[sid]["selected"] is False
        assert cands[sid]["relevance"] == pytest.approx(WEAK_EXPECTED[name])


def test_must_m1_v4_canal_open_with_only_a_close_member_does_not_pad_with_weak_ones(world: World):
    """Free host (3 slots): A2 is the only candidate >= τ; the other slots must stay empty (NEVER-08)."""
    world.seed(("A", "A2"))
    weak = _publish_weak(world)
    env = assert_ok(world.open_canal(query=Q01))
    assert member_ids(env) == [world.sid("A2")], f"members {member_ids(env)}; weak {weak}"
    assert env["truncated"] is False


def test_never_08_v4_only_below_tau_candidates_is_no_relevant_subbrain(world: World):
    world.seed(("A",))
    _publish_weak(world)
    month = current_month()
    env = assert_err(world.open_canal(query=Q01), "NO_RELEVANT_SUBBRAIN")
    assert "canal_id" not in env
    assert world.store.count_canals_in_month("user_a", month) == 0


def test_must_m1_v4_canal_open_selects_a_candidate_exactly_at_tau(world: World):
    world.seed(("A",))
    _publish_weak(world)
    t_sid = _publish_doc(world, "user_t", AT_TAU_DOC)
    env = assert_ok(world.open_canal(query=Q01))
    assert member_ids(env) == [t_sid]
    assert env["members"][0]["relevance"] == pytest.approx(world.cfg.matching.tau)


# ---------------------------------------------------------------------------
# MUST-M3 (v.4) — Q-02a..d are topicless: whole_host, never NO_RELEVANT_SUBBRAIN for host A
# ---------------------------------------------------------------------------

Q02_VARIANTS = {
    "Q-02": Q02,
    "Q-02a": "내가 만든 두뇌를 평가해 주세요",
    "Q-02b": "저의 두뇌를 검토해줘",
    "Q-02c": "두뇌 전체적으로 평가 부탁드립니다",
    "Q-02d": "내 두뇌 어때?",
}
SENTENCE_WORDS = {"두뇌", "평가", "만든", "내가", "저의", "검토", "전체적", "전체적으로", "부탁드립니다", "어때", "주세요", "평가해"}


@pytest.mark.parametrize("qid", sorted(Q02_VARIANTS))
def test_must_m3_v4_topicless_variants_have_no_query_terms(cfg, qid):
    from opencanal import matching

    assert matching.query_terms(Q02_VARIANTS[qid], cfg.matching) == []


@pytest.mark.parametrize("qid", sorted(Q02_VARIANTS))
def test_must_m3_v4_topicless_variants_match_whole_host(cfg, qid):
    from opencanal import matching

    candidates = [fixture_version(f) for f in ("A2", "B", "C", "D", "X")]
    result = _match(Q02_VARIANTS[qid], candidates, cfg)
    assert result.query_mode_used == QueryMode.WHOLE_HOST
    assert set(result.query_terms) <= set(matching.host_terms(fixture_version("A"), cfg.matching))
    assert not set(result.query_terms) & SENTENCE_WORDS
    selected = {c.subbrain_id for c in result.candidates if c.selected}
    assert selected, "a topicless query of host A must not end with no members"
    assert fixture_sid("D") not in selected
    for c in result.candidates:
        if c.selected:
            assert c.relevance >= cfg.matching.tau
            assert not set(c.matched_terms) & SENTENCE_WORDS


@pytest.mark.parametrize("qid", sorted(Q02_VARIANTS))
def test_must_m3_v4_canal_open_topicless_variants(seeded: World, qid):
    env = seeded.open_canal(query=Q02_VARIANTS[qid])
    assert env["ok"] is True, f"{qid} must open a whole_host canal, got {dumps(env)[:500]}"
    assert env["query_mode_used"] == "whole_host"
    ids = member_ids(env)
    assert ids
    assert seeded.sid("D") not in ids
    assert {seeded.sid("B"), seeded.sid("C")} & set(ids), "B/C share host tags 조립·오류"
    for m in env["members"]:
        assert m["relevance"] >= seeded.cfg.matching.tau
        assert not set(m["matched_terms"]) & SENTENCE_WORDS


# ---------------------------------------------------------------------------
# MUST-M1 (v.4 정규화) — invisible characters used as separators do not change the query terms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "모듈러​건축의 현장ㅤ조립 오류를﻿줄일 아이디어",
        "ㅤ모듈러 건축의⁠ 현장 조립ﾠ오류를 줄일 아이디어‍",
        "모듈러 건축의 현장 조립 오류를 줄일 아이디어️",
    ],
    ids=["zwsp_filler_bom", "wj_halfwidth_zwj", "variation_selector"],
)
def test_must_m1_v4_invisible_separators_give_the_same_query_terms(cfg, query):
    from opencanal import matching

    assert matching.query_terms(query, cfg.matching) == Q01_TERMS
