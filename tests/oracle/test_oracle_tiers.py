"""NEVER-06, NEVER-07, NEVER-12, MUST-T1 — tier gate, limits, fail closed (ORACLE §5.6), at the Service layer.

The same properties are checked over real MCP HTTP in test_oracle_mcp_http.py.
"""

from __future__ import annotations

from opencanal.models import Tier

from .conftest import (
    HIGHER_TIER_TOOLS,
    Q01,
    Q03,
    World,
    assert_err,
    assert_ok,
    current_month,
    dumps,
    member_ids,
    pick,
)


def _tool_names(world: World, user_id: str | None) -> list[str]:
    user = world.user(user_id) if user_id else None
    return [t.name for t in world.service.tools_for(user)]


# ---------------------------------------------------------------------------
# NEVER-06 — tools/list shows exactly the tier's tools
# ---------------------------------------------------------------------------


def test_never_06_tools_for_each_tier_match_config(world: World):
    for tier in Tier:
        uid = f"user_tier_{tier.value}"
        world.add_user(uid, tier=tier)
        names = _tool_names(world, uid)
        assert sorted(names) == sorted(world.cfg.tools_for_tier(tier)), tier
        assert len(names) == len(set(names))


def test_never_06_free_tool_list_never_mentions_hidden_tools(world: World):
    specs = world.service.tools_for(world.user("user_a"))
    text = dumps([s.model_dump(mode="json") for s in specs])
    for hidden in HIGHER_TIER_TOOLS:
        assert hidden not in text, f"{hidden} leaks into the Free tool list (name, description or schema)"
    world.add_user("user_pro_06", tier=Tier.PRO)
    pro_text = dumps([s.model_dump(mode="json") for s in world.service.tools_for(world.user("user_pro_06"))])
    assert "canal_synthesize" not in pro_text


# ---------------------------------------------------------------------------
# NEVER-07 — calling a higher-tier tool directly
# ---------------------------------------------------------------------------


def test_never_07_free_direct_call_of_higher_tier_tools_is_forbidden(seeded: World):
    month = current_month()
    before = seeded.store.count_canals_in_month("user_a", month)
    args = {
        "match_explain": {"query": Q01, "host_subbrain_id": seeded.sid("A")},
        "deltabrain_export": {"deltabrain_id": "db_anything"},
        "canal_synthesize": {},
    }
    for tool in HIGHER_TIER_TOOLS:
        env = assert_err(seeded.call("user_a", tool, **args[tool]), "TIER_FORBIDDEN")
        assert "untrusted_data" not in env
        # Tier is checked before argument validation (TASK-001 §5 dispatch order).
        assert_err(seeded.call("user_a", tool), "TIER_FORBIDDEN")
    assert seeded.store.count_canals_in_month("user_a", month) == before


def test_never_07_canal_synthesize_is_expert_only_and_not_available(world: World):
    world.add_user("user_pro_07", tier=Tier.PRO)
    world.add_user("user_expert_07", tier=Tier.EXPERT)
    assert_err(world.call("user_pro_07", "canal_synthesize"), "TIER_FORBIDDEN")
    assert_err(world.call("user_expert_07", "canal_synthesize"), "NOT_AVAILABLE")


def test_never_07_tier_is_rechecked_on_every_call(seeded: World):
    seeded.set_tier("user_a", Tier.PRO)
    assert_ok(seeded.call("user_a", "match_explain", query=Q01, host_subbrain_id=seeded.sid("A")))
    seeded.set_tier("user_a", Tier.FREE)
    assert_err(seeded.call("user_a", "match_explain", query=Q01, host_subbrain_id=seeded.sid("A")), "TIER_FORBIDDEN")
    assert "match_explain" not in _tool_names(seeded, "user_a")


# ---------------------------------------------------------------------------
# NEVER-12 — fail closed
# ---------------------------------------------------------------------------


def test_never_12_missing_unknown_and_revoked_tokens_fail_closed(world: World):
    svc = world.service
    old_token = world.tokens["user_a"]
    new_token = world.store.rotate_token("user_a")
    assert new_token != old_token
    for token in (None, "", "oc_" + "A" * 43, "not-a-token", old_token):
        assert svc.authenticate(token) is None, f"token {token!r} must not authenticate"
    assert svc.authenticate(new_token).id == "user_a"
    world.tokens["user_a"] = new_token

    assert svc.tools_for(None) == []
    for tool, args in (
        ("subbrain_list_mine", {}),
        ("subbrain_search", {"query": Q01}),
        ("canal_synthesize", {}),
        ("no_such_tool", {}),
    ):
        env = assert_err(svc.dispatch(None, tool, args), "UNAUTHORIZED")
        assert "untrusted_data" not in env


def test_never_12_no_default_user_side_effects(world: World):
    """An unauthenticated import must not land on any account."""
    from .conftest import load_brain

    assert_err(world.service.dispatch(None, "subbrain_import", {"document": load_brain("A")["document"]}), "UNAUTHORIZED")
    for uid in world.tokens:
        assert pick(assert_ok(world.call(uid, "subbrain_list_mine")), "subbrains") == []


# ---------------------------------------------------------------------------
# MUST-T1 — tier limits
# ---------------------------------------------------------------------------

F_DOC = {
    "title": "건설 현장 안전 교육 메모",
    "domains": ["건설 안전"],
    "nodes": [
        {"id": "f-n1", "label": "건축 안전 교육", "tags": ["현장", "안전"], "summary": "신규 작업자 첫날 두 시간 교육."},
        {"id": "f-n2", "label": "추락 방지 난간", "tags": ["추락", "난간"], "summary": "개구부 둘레에 임시 난간을 세운다."},
        {"id": "f-n3", "label": "안전모 착용 점호", "tags": ["안전모"], "summary": "아침 체조 뒤에 착용 상태를 서로 본다."},
    ],
    "edges": [{"id": "f-e1", "source": "f-n1", "target": "f-n2", "relation": "covers"}],
}  # Q-01 relevance by the config formula: 현장(tag 1.0) + 건축(label 0.8) = 1.8 / 5 = 0.36 < A2, B, C
# Oracle MUST-M2 score = relevance + 0.3 * distance (MUST-M5 content distance). v.7 (label/tag word sets): F shares
# 건축, 현장 with A -> distance 7/9, score 0.36 + 0.3 * 7/9 ≈ 0.593 > A2 0.56 + 0.3 * 0 = 0.56; B = C ≈ 0.633.
# (v.6 cosine: F ≈ 0.60, B ≈ 0.63, C ≈ 0.64; v.5 declared-domain distance: F 0.66, B and C 0.70.)


def test_must_t1_members_truncated_by_relevance_and_flagged(seeded: World):
    seeded.add_user("user_f", "Farah Lim")
    f = assert_ok(seeded.import_doc("user_f", F_DOC))
    assert_ok(
        seeded.call("user_f", "subbrain_set_visibility", subbrain_id=f["subbrain_id"], visibility="public", confirm_hash=f["content_hash"])
    )
    limit = seeded.cfg.limits_for_tier(Tier.FREE).max_members_per_canal
    env = assert_ok(seeded.open_canal(query=Q01))
    ids = member_ids(env)
    assert len(ids) == limit
    assert env["truncated"] is True
    # Oracle v.5 MUST-M2 (default strategy): eligible candidates are chosen by score, so the lowest-SCORE
    # candidate is the one cut — A2 (0.56), not F (≈0.593 with the v.7 content distance). MUST-T1's "상위 관련도 순"
    # predates v.5.
    assert seeded.sid("A2") not in ids, "the lowest-score candidate (MUST-M2) is the one cut"
    assert {f["subbrain_id"], seeded.sid("B"), seeded.sid("C")} == set(ids)
    for m in env["members"]:
        assert m["relevance"] >= seeded.cfg.matching.tau

    # A Pro host has room for all four relevant candidates.
    seeded.set_tier("user_a", Tier.PRO)
    env_pro = assert_ok(seeded.open_canal(query=Q01))
    assert f["subbrain_id"] in member_ids(env_pro)
    assert env_pro["truncated"] is False


def test_must_t1_monthly_canal_limit_counts_only_created_canals(seeded: World):
    limit = seeded.cfg.limits_for_tier(Tier.FREE).canals_per_month
    month = current_month()
    for _ in range(limit - 1):
        assert_ok(seeded.open_canal(query=Q01))
    assert_err(seeded.open_canal(query=Q03), "NO_RELEVANT_SUBBRAIN")  # NEVER-08: not counted
    assert seeded.store.count_canals_in_month("user_a", month) == limit - 1
    assert_ok(seeded.open_canal(query=Q01))
    assert seeded.store.count_canals_in_month("user_a", month) == limit
    assert_err(seeded.open_canal(query=Q01), "LIMIT_EXCEEDED")
    assert seeded.store.count_canals_in_month("user_a", month) == limit
    # Another user's quota is independent.
    assert_ok(seeded.call("user_c", "canal_open", query=Q01, host_subbrain_id=seeded.sid("C")))


def test_must_t1_public_subbrain_limit(seeded: World):
    assert seeded.cfg.limits_for_tier(Tier.FREE).max_public_subbrains == 1
    pid = seeded.sid("P")
    assert_err(seeded.publish("P"), "LIMIT_EXCEEDED")
    mine = pick(assert_ok(seeded.call("user_b", "subbrain_list_mine")), "subbrains")
    assert next(s for s in mine if s["subbrain_id"] == pid)["visibility"] == "private"
    assert_err(seeded.call("user_a", "subbrain_get", subbrain_id=pid), "NOT_FOUND")
    # Re-publishing the already-public subbrain is not counted again.
    assert_ok(seeded.publish("B"))
    # Switching B to private frees the slot.
    assert_ok(seeded.make_private("B"))
    assert_ok(seeded.publish("P"))
