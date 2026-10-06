"""MUST-M1, MUST-M3, MUST-M4, NEVER-08, PROV-M2 — matching does not ignore keywords (ORACLE §5.4, §6.2).

Pure tests call matching.* with fixture subbrains; behavior tests go through Service.dispatch (canal_open,
subbrain_search, match_explain). tau is read from config and never tuned here.
"""

from __future__ import annotations

import pytest

from opencanal.models import QueryMode, Tier

from .conftest import (
    Q01,
    Q01_TERMS,
    Q02,
    Q03,
    World,
    assert_err,
    assert_ok,
    current_month,
    dumps,
    find_dicts,
    fixture_sid,
    fixture_version,
    load_brain,
    member_ids,
    pick,
)


def _candidates():
    """Other users' public fixture subbrains (the store's job is to pass only these; ORACLE MUST-M4)."""
    return [fixture_version(f) for f in ("A2", "B", "C", "D", "X")]


def _match(query, *, max_members=3, strategy=None, query_mode=QueryMode.AUTO, candidates=None, cfg=None):
    from opencanal import matching

    return matching.match(
        query,
        fixture_version("A"),
        candidates if candidates is not None else _candidates(),
        max_members=max_members,
        cfg=cfg.matching,
        query_mode=query_mode,
        strategy=strategy,
    )


def _by_id(result):
    return {c.subbrain_id: c for c in result.candidates}


def _selected_ids(result):
    return {c.subbrain_id for c in result.candidates if c.selected}


# ---------------------------------------------------------------------------
# MUST-M1 — pure
# ---------------------------------------------------------------------------


def test_must_m1_query_terms_of_q01(cfg):
    from opencanal import matching

    assert matching.query_terms(Q01, cfg.matching) == Q01_TERMS


def test_must_m1_relevance_formula_on_fixtures(cfg):
    """Formula of the matching stub docstring + config/matching.json, on hand-computed fixture values."""
    from opencanal import matching

    def score(fid):
        rel, terms = matching.score_relevance(Q01_TERMS, fixture_version(fid), cfg.matching)
        return rel, set(terms)

    assert score("B") == (pytest.approx(0.4), {"조립", "오류"})  # two exact tag hits / 5
    assert score("C") == (pytest.approx(0.4), {"조립", "오류"})
    assert score("A2") == (pytest.approx(0.56), {"모듈러", "건축", "현장"})  # tag + tag + label 0.8
    assert score("D") == (0.0, set())
    assert score("X") == (0.0, set())
    assert matching.score_relevance([], fixture_version("B"), cfg.matching)[0] == 0.0


def test_must_m1_q01_selects_only_relevant_members_with_evidence(cfg):
    result = _match(Q01, cfg=cfg)
    tau = cfg.matching.tau
    assert result.query_mode_used == QueryMode.TOPIC
    assert result.query_terms == Q01_TERMS
    assert result.tau == tau
    by_id = _by_id(result)
    selected = [c for c in result.candidates if c.selected]
    assert selected, "Q-01 must find relevant members"
    for c in selected:
        assert c.relevance >= tau
        assert c.matched_terms, f"{c.subbrain_id} selected without evidence"
        assert set(c.matched_terms) <= set(Q01_TERMS)
    assert {fixture_sid("B"), fixture_sid("C")} <= _selected_ids(result)
    assert by_id[fixture_sid("D")].selected is False
    assert by_id[fixture_sid("D")].relevance < tau
    assert by_id[fixture_sid("X")].selected is False
    rels = [c.relevance for c in result.candidates]
    assert rels == sorted(rels, reverse=True), "candidates are sorted by relevance desc"


def test_must_m1_match_is_deterministic(cfg):
    a = _match(Q01, cfg=cfg).model_dump(mode="json")
    b = _match(Q01, cfg=cfg).model_dump(mode="json")
    c = _match(Q01, cfg=cfg, candidates=list(reversed(_candidates()))).model_dump(mode="json")
    assert a == b
    assert a == c, "candidate input order must not change the result"


def test_must_m1_domain_distance(cfg):
    from opencanal import matching

    a = fixture_version("A")
    assert matching.domain_distance(a, fixture_version("A2")) == pytest.approx(0.0)
    assert matching.domain_distance(a, fixture_version("B")) == pytest.approx(1.0)
    assert matching.domain_distance(a, fixture_version("D")) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# MUST-M3 — topicless query uses the whole host subbrain
# ---------------------------------------------------------------------------


def test_must_m3_q02_has_no_query_terms(cfg):
    from opencanal import matching

    assert matching.query_terms(Q02, cfg.matching) == []


def test_must_m3_host_terms_come_from_host_tags_and_labels(cfg):
    from opencanal import matching

    terms = matching.host_terms(fixture_version("A"), cfg.matching)
    assert {"모듈러", "조립", "오류", "공차", "접합부", "양중"} <= set(terms)
    stop = set(cfg.matching.stopwords)
    assert not stop & set(terms)


def test_must_m3_q02_matches_whole_host_and_excludes_d(cfg):
    from opencanal import matching

    result = _match(Q02, cfg=cfg)
    assert result.query_mode_used == QueryMode.WHOLE_HOST
    assert "두뇌" not in result.query_terms and "평가" not in result.query_terms
    assert set(result.query_terms) <= set(matching.host_terms(fixture_version("A"), cfg.matching))
    assert {"조립", "오류"} <= set(result.query_terms)
    selected = [c for c in result.candidates if c.selected]
    assert selected
    for c in selected:
        assert c.relevance >= cfg.matching.tau
        assert "두뇌" not in c.matched_terms and "평가" not in c.matched_terms
    assert _by_id(result)[fixture_sid("D")].selected is False
    assert _by_id(result)[fixture_sid("D")].relevance < cfg.matching.tau


def test_must_m3_explicit_whole_host_mode_overrides_topic_terms(cfg):
    result = _match(Q01, cfg=cfg, query_mode=QueryMode.WHOLE_HOST)
    assert result.query_mode_used == QueryMode.WHOLE_HOST
    assert "공차" in result.query_terms  # a host term that is not in the Q-01 sentence
    assert _by_id(result)[fixture_sid("D")].selected is False


# ---------------------------------------------------------------------------
# MUST-M4 / NEVER-08 / PROV-M2 — pure
# ---------------------------------------------------------------------------


def test_must_m4_host_owner_candidates_never_selected(cfg):
    own = fixture_version("P", subbrain_id="sb_A_other", owner_id="user_a")  # relevance 1.0 for Q-01
    result = _match(Q01, cfg=cfg, candidates=[*_candidates(), own], max_members=10)
    assert "sb_A_other" not in _selected_ids(result)


def test_never_08_q03_selects_nothing(cfg):
    result = _match(Q03, cfg=cfg)
    assert result.query_mode_used == QueryMode.TOPIC
    assert _selected_ids(result) == set()
    assert all(c.relevance < cfg.matching.tau for c in result.candidates)


def test_prov_m2_relevance_only_takes_top_relevance(cfg):
    result = _match(Q01, cfg=cfg, max_members=1, strategy="relevance_only")
    assert result.strategy == "relevance_only"
    assert _selected_ids(result) == {fixture_sid("A2")}  # 0.56 > 0.4 (B, C)
    assert result.truncated is True


def test_prov_m2_diversity_includes_a_distant_relevant_candidate(cfg):
    result = _match(Q01, cfg=cfg, max_members=1, strategy="relevance_plus_diversity")
    assert result.strategy == "relevance_plus_diversity"
    selected = [c for c in result.candidates if c.selected]
    assert len(selected) == 1
    assert selected[0].distance == pytest.approx(1.0)
    assert selected[0].relevance >= cfg.matching.tau
    assert selected[0].subbrain_id in {fixture_sid("B"), fixture_sid("C")}  # never D/X (below tau)


@pytest.mark.parametrize("strategy", ["relevance_only", "relevance_plus_diversity"])
def test_prov_m2_no_strategy_selects_below_tau(cfg, strategy):
    for query in (Q01, Q02, Q03):
        for max_members in (1, 3, 10):
            result = _match(query, cfg=cfg, max_members=max_members, strategy=strategy)
            assert len(_selected_ids(result)) <= max_members
            for c in result.candidates:
                if c.selected:
                    assert c.relevance >= cfg.matching.tau
            assert fixture_sid("D") not in _selected_ids(result)
            assert fixture_sid("X") not in _selected_ids(result)


def test_prov_m2_default_strategy_comes_from_config(cfg):
    result = _match(Q01, cfg=cfg)
    assert result.strategy == cfg.matching.strategy == "relevance_plus_diversity"
    assert _selected_ids(result) == {fixture_sid("A2"), fixture_sid("B"), fixture_sid("C")}
    assert result.truncated is False


# ---------------------------------------------------------------------------
# Behavior through Service.dispatch
# ---------------------------------------------------------------------------


def test_must_m1_canal_open_q01_members_relevant_with_evidence(seeded: World):
    env = assert_ok(seeded.open_canal(query=Q01))
    tau = seeded.cfg.matching.tau
    ids = member_ids(env)
    assert env["query_mode_used"] == "topic"
    assert seeded.sid("B") in ids and seeded.sid("C") in ids
    for fid in ("D", "P", "A", "X"):
        assert seeded.sid(fid) not in ids, f"{fid} must not be a member of the Q-01 canal"
    for m in env["members"]:
        assert m["relevance"] >= tau
        assert m["matched_terms"], m
        assert set(m["matched_terms"]) <= set(Q01_TERMS)
    assert env["truncated"] is False
    assert isinstance(env["canal_id"], str) and env["canal_id"]


def test_must_m1_search_q01_returns_only_relevant_public_subbrains(seeded: World):
    env = assert_ok(seeded.call("user_a", "subbrain_search", query=Q01))
    results = env["untrusted_data"]["results"]
    ids = {r["subbrain_id"] for r in results}
    assert seeded.sid("B") in ids and seeded.sid("C") in ids
    assert seeded.sid("D") not in ids
    assert seeded.sid("P") not in ids
    for r in results:
        assert r["relevance"] >= seeded.cfg.matching.tau
        assert r["matched_terms"]


def test_must_m1_search_limit_is_respected(seeded: World):
    env = assert_ok(seeded.call("user_a", "subbrain_search", query=Q01, limit=1))
    assert len(env["untrusted_data"]["results"]) <= 1


def test_must_m1_match_explain_lists_below_tau_candidates_without_side_effects(seeded: World):
    seeded.set_tier("user_a", Tier.PRO)
    before = seeded.store.count_canals_in_month("user_a", current_month())
    env = assert_ok(seeded.call("user_a", "match_explain", query=Q01, host_subbrain_id=seeded.sid("A")))
    after = seeded.store.count_canals_in_month("user_a", current_month())
    assert before == after, "match_explain must not create a canal or use quota"
    cands = find_dicts(env, lambda d: "subbrain_id" in d and "relevance" in d and "selected" in d)
    ids = {c["subbrain_id"] for c in cands}
    assert seeded.sid("D") in ids, "MatchResult must include below-tau candidates"
    d = next(c for c in cands if c["subbrain_id"] == seeded.sid("D"))
    assert d["selected"] is False and d["relevance"] < seeded.cfg.matching.tau
    assert seeded.sid("P") not in dumps(env), "private subbrains are never candidates"


def test_must_m3_canal_open_q02_uses_whole_host_and_excludes_d(seeded: World):
    env = assert_ok(seeded.open_canal(query=Q02))
    assert env["query_mode_used"] == "whole_host"
    ids = member_ids(env)
    assert ids, "whole_host matching of host A finds members"
    assert seeded.sid("D") not in ids
    for m in env["members"]:
        assert m["relevance"] >= seeded.cfg.matching.tau
        assert "두뇌" not in m["matched_terms"] and "평가" not in m["matched_terms"]


def test_must_m3_canal_open_explicit_whole_host_mode(seeded: World):
    env = assert_ok(seeded.open_canal(query=Q01, query_mode="whole_host"))
    assert env["query_mode_used"] == "whole_host"
    assert seeded.sid("D") not in member_ids(env)


def test_must_m4_candidates_are_other_users_public_latest_versions(world: World):
    world.set_tier("user_a", Tier.PRO)  # Pro may keep several public subbrains
    world.seed()
    # A second public subbrain owned by the host user, highly relevant to Q-01.
    own = world.import_fixture("P", as_user="user_a")
    assert_ok(world.publish("P@user_a"))
    # B's owner publishes a new version of B.
    b2 = load_brain("B")["document"]
    b2["nodes"].append(
        {"id": "b-n11", "label": "조립 순서 잠금", "tags": ["조립", "순서"], "summary": "앞 블록을 놓기 전에는 다음 블록이 잠겨 있다."}
    )
    env_b2 = assert_ok(world.import_doc("user_b", b2, subbrain_id=world.sid("B")))
    assert env_b2["subbrain_id"] == world.sid("B") and env_b2["version"] == 2

    # Until v2 is confirmed with its content_hash, other users still get the published v1 (NEVER-04).
    env_v1 = assert_ok(world.open_canal(query=Q01))
    b_v1 = next(m for m in env_v1["members"] if m["subbrain_id"] == world.sid("B"))
    assert b_v1["version"] == 1
    assert "조립 순서 잠금" not in dumps(env_v1)

    assert_ok(
        world.call(
            "user_b",
            "subbrain_set_visibility",
            subbrain_id=world.sid("B"),
            visibility="public",
            version=2,
            confirm_hash=env_b2["content_hash"],
        )
    )

    env = assert_ok(world.open_canal(query=Q01))
    ids = member_ids(env)
    assert own["subbrain_id"] not in ids, "host's own subbrain is never a candidate"
    assert world.sid("P") not in ids, "private subbrain is never a candidate"
    assert not set(ids) & {world.sid("A"), own["subbrain_id"]}, "nothing owned by the host user"
    b = next(m for m in env["members"] if m["subbrain_id"] == world.sid("B"))
    assert b["version"] == 2


def test_never_08_q03_no_relevant_subbrain_creates_no_canal(seeded: World):
    month = current_month()
    before = seeded.store.count_canals_in_month("user_a", month)
    env = assert_err(seeded.open_canal(query=Q03), "NO_RELEVANT_SUBBRAIN")
    assert "canal_id" not in env
    assert seeded.store.count_canals_in_month("user_a", month) == before
    assert pick(assert_ok(seeded.call("user_a", "deltabrain_list")), "deltabrains") == []


def test_prov_m2_canal_open_default_strategy_includes_distant_member(seeded: World):
    env = assert_ok(seeded.open_canal(query=Q01))
    assert any(m["distance"] == pytest.approx(1.0) for m in env["members"])
