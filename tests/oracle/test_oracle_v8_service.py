"""Oracle v.8 pins through Service.dispatch — rating units, stats, quality, protocol, NEVER-11 viewer stats.

ORACLE_MANIFEST v2026-10-07.8 and TASK-001 §5:
- §9 (v.8) "평가 도구 deltabrain_rate의 대상 = 다리 노드 또는 창발 엣지 (target_id), 아니면 NOT_RATEABLE"
- TASK §5 deltabrain_rate: `deltabrain_id`, `target_id`(다리 노드 또는 창발 엣지, v.8), `novelty`, `validity`,
  `usefulness` (0/1) -> `ok`, `untrusted_data.target_id`; NOT_FOUND, NOT_RATEABLE(보는 사람의 뷰 기준), INVALID_ARGUMENT.
  An unknown target id is "neither a bridge node nor an emergent edge" (models.ErrorCode.NOT_RATEABLE) -> NOT_RATEABLE;
  NOT_FOUND stays the answer for a deltabrain the caller cannot see (NEVER-05), whatever the target.
- HUMAN-01 (v.8) "델타브레인 품질 = 세 축이 모두 1인 평가 단위 비율" — computed over the rated units.
- TASK §5 deltabrain_get: "최상위 stats는 숫자만, rating_summary(숫자) ... untrusted_data.stats(엣지 ID 목록)".
- §2 (2026-10-07) "합성 프로토콜에 현실 제약 검토 | 넣는다 | 다리 노드의 constraints 필드, 프로토콜 요구사항".
- NEVER-11 (v.4) "통계(창발 엣지 목록, 관여 주인 수), 평가 응답, 오류 코드로도 ... 계산할 수 없다. 그 참여자에게 보이는
  통계는 그에게 보이는 신원 기준으로 계산한다" — re-run with the v.8 stats (bridge ids, host bridge ids, constraints).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from opencanal.models import Tier

from ._v4 import canonical, first_difference
from ._v8 import analyse, quality
from .conftest import (
    PRIVATE_CONTRIBUTOR,
    Q01,
    World,
    assert_err,
    assert_ok,
    assert_same_not_found,
    dumps,
    fake_id_like,
    find_dicts,
    fixture_canal_context,
    load_delta,
    member_ids,
    rewrite_provenance,
)

GOOD_BRIDGES = {"n1", "n2"}
GOOD_EMERGENT = {"e3", "e4", "e9", "e10"}
GOOD_HOST_TOUCHING = {"e3", "e4", "e10"}
NOT_UNITS = ("e1", "e2", "e5", "e6", "e7", "e8", "q", "s-a1", "s-a2", "s-a3", "s-b1", "s-c1", "s-c2")
STAT_LISTS = ("emergent_edge_ids", "host_touching_emergent_edge_ids", "bridge_node_ids", "host_bridge_node_ids")


def _ref(sb: str, node: str, version: int = 1) -> dict:
    return {"subbrain_id": sb, "version": version, "node_id": node}


def _node(g: dict, nid: str) -> dict:
    return next(n for n in g["nodes"] if n["id"] == nid)


def rate(w: World, user: str, db_id: str, target: str, labels=(1, 1, 1)) -> dict[str, Any]:
    n, v, u = labels
    return w.call(user, "deltabrain_rate", deltabrain_id=db_id, target_id=target, novelty=n, validity=v, usefulness=u)


def viewer_stats(env: dict[str, Any]) -> dict[str, Any]:
    """deltabrain_get stats as a participant sees them.

    TASK §5: "최상위 stats는 숫자만 ... untrusted_data.stats(엣지 ID 목록)". The ID lists are host-authored ids, so they
    must sit under `untrusted_data` (NEVER-09 v.4); the exact nesting inside it is not pinned here (the implementation
    has kept them at untrusted_data.deltabrain.stats since v.3), only that exactly one stats dict carries them.
    """
    ud = env.get("untrusted_data") or {}
    found = find_dicts(ud, lambda d: "emergent_edge_ids" in d)
    assert found, f"deltabrain_get must carry the id-list stats under untrusted_data: {dumps(env)[:1500]}"
    assert all(d == found[0] for d in found), f"conflicting stats dicts under untrusted_data: {found}"
    lists = found[0]
    top = env.get("stats") or {}
    assert isinstance(top, dict)
    for k, v in top.items():
        assert isinstance(v, (int, float)) and not isinstance(v, bool), f"top-level stats are numbers only (TASK §5): {k}={v!r}"
    merged = {**top, **lists}
    for key in (*STAT_LISTS, "bridges_with_constraints"):
        assert key in merged, f"v.8 stats field {key!r} missing from the viewer's deltabrain_get: {dumps(env)[:1500]}"
    for key in STAT_LISTS:
        assert isinstance(lists.get(key), list), f"{key} must be an id list under untrusted_data"
    return merged


def _numbers(obj: Any) -> list[float]:
    if isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, dict):
        return [x for v in obj.values() for x in _numbers(v)]
    if isinstance(obj, (list, tuple)):
        return [x for v in obj for x in _numbers(v)]
    return []


@pytest.fixture
def flow(seeded: World) -> dict[str, Any]:
    """Q-01 canal hosted by A (members A2, B, C) with good-01 accepted."""
    canal = assert_ok(seeded.open_canal(query=Q01))
    sub = assert_ok(seeded.submit(canal["canal_id"], seeded.good01()))
    return {"world": seeded, "canal_id": canal["canal_id"], "db_id": sub["deltabrain_id"], "sub": sub}


# ---------------------------------------------------------------------------
# Stats on the product surface
# ---------------------------------------------------------------------------


def test_v8_submit_returns_v8_stats(flow):
    stats = flow["sub"]["stats"]
    assert set(stats["bridge_node_ids"]) == GOOD_BRIDGES
    assert set(stats["host_bridge_node_ids"]) == GOOD_BRIDGES
    assert set(stats["emergent_edge_ids"]) == GOOD_EMERGENT
    assert set(stats["host_touching_emergent_edge_ids"]) == GOOD_HOST_TOUCHING
    assert stats["bridges_with_constraints"] == 0


def test_v8_submit_counts_bridges_with_constraints(seeded: World):
    canal = assert_ok(seeded.open_canal(query=Q01))
    delta = seeded.good01()
    _node(delta, "n1")["constraints"] = "접합부 종류가 늘어 제작비와 도면 관리 공수가 커진다. 위치를 헷갈리기 쉬운 현장에만 쓴다."
    sub = assert_ok(seeded.submit(canal["canal_id"], delta))
    assert sub["stats"]["bridges_with_constraints"] == 1


@pytest.mark.parametrize("viewer", ["user_a", "user_b", "user_c", "user_e"])
def test_v8_every_participant_gets_v8_stats_in_deltabrain_get(flow, viewer):
    env = assert_ok(flow["world"].call(viewer, "deltabrain_get", deltabrain_id=flow["db_id"]))
    stats = viewer_stats(env)
    assert set(stats["bridge_node_ids"]) == GOOD_BRIDGES
    assert set(stats["host_bridge_node_ids"]) == GOOD_BRIDGES
    assert set(stats["emergent_edge_ids"]) == GOOD_EMERGENT
    assert set(stats["host_touching_emergent_edge_ids"]) == GOOD_HOST_TOUCHING
    assert stats["bridges_with_constraints"] == 0


def test_v8_validation_failed_names_the_bridge_without_summary(seeded: World):
    canal = assert_ok(seeded.open_canal(query=Q01))
    delta = seeded.good01()
    _node(delta, "n2").pop("summary")
    env = seeded.submit(canal["canal_id"], delta)
    assert_err(env, "VALIDATION_FAILED")
    found = [v for v in env["error"]["violations"] if v.get("code") == "RATIONALE_MISSING"]
    assert [v.get("node_id") for v in found] == ["n2"], f"MUST-Q4 v.8: RATIONALE_MISSING names node_id n2: {found}"


# ---------------------------------------------------------------------------
# deltabrain_rate (v.8): target_id = bridge node or emergent edge
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target", ["n1", "n2", "e3", "e4", "e9", "e10"])
def test_v8_rate_bridge_nodes_and_emergent_edges(flow, target):
    w, db_id = flow["world"], flow["db_id"]
    env = assert_ok(rate(w, "user_b", db_id, target))
    assert env["untrusted_data"]["target_id"] == target, f"TASK §5: untrusted_data.target_id: {dumps(env)}"
    rated = {(r.edge_id, r.rater_id, r.novelty, r.validity, r.usefulness) for r in w.store.ratings_for(db_id)}
    assert rated == {(target, "user_b", 1, 1, 1)}, "EdgeRating.edge_id holds the rating target id (models v.8)"


@pytest.mark.parametrize("target", NOT_UNITS)
def test_v8_rate_anything_else_is_not_rateable_without_side_effects(flow, target):
    """Query edges, self-anchor edges, the query node and source nodes are not rating units (§4 v.8)."""
    w, db_id = flow["world"], flow["db_id"]
    assert_err(rate(w, "user_a", db_id, target), "NOT_RATEABLE")
    assert w.store.ratings_for(db_id) == [], "a refused rating must not be stored"


def test_v8_rate_unknown_target_in_a_visible_deltabrain_is_not_rateable(flow):
    """§9 (v.8): "대상 = 다리 노드 또는 창발 엣지 (target_id), 아니면 NOT_RATEABLE"; models.ErrorCode.NOT_RATEABLE
    "target is neither a bridge node nor an emergent edge". TASK §5 keeps NOT_FOUND for the deltabrain itself.
    Every node and edge id of a deltabrain is visible to its participants (NEVER-02 keeps retained content), so an
    unknown id hides nothing and needs no NOT_FOUND masking; the deltabrain is visible, the target is not a unit."""
    w, db_id = flow["world"], flow["db_id"]
    assert_err(rate(w, "user_a", db_id, "zz-unknown-404"), "NOT_RATEABLE")
    assert w.store.ratings_for(db_id) == []


def test_v8_rate_single_owner_new_node_is_not_rateable(seeded: World):
    canal = assert_ok(seeded.open_canal(query=Q01))
    delta = seeded.good01()
    a = seeded.sid("A")
    delta["nodes"].append(
        {"id": "n-a", "kind": "new", "label": "공차 흡수형 볼트 슬롯", "provenance": [_ref(a, "a-n3"), _ref(a, "a-n4")]}
    )
    delta["edges"].append({"id": "e11", "source": "n-a", "target": "s-a2", "relation": "extends"})
    db_id = assert_ok(seeded.submit(canal["canal_id"], delta))["deltabrain_id"]
    assert_err(rate(seeded, "user_a", db_id, "n-a"), "NOT_RATEABLE")
    assert_err(rate(seeded, "user_a", db_id, "e11"), "NOT_RATEABLE")
    assert_ok(rate(seeded, "user_a", db_id, "n1"))


def test_v8_rate_argument_errors(flow):
    w, db_id = flow["world"], flow["db_id"]
    assert_err(rate(w, "user_a", db_id, "n1", (2, 1, 1)), "INVALID_ARGUMENT")
    assert_err(rate(w, "user_a", db_id, "e3", (1, -1, 1)), "INVALID_ARGUMENT")
    assert_err(w.call("user_a", "deltabrain_rate", deltabrain_id=db_id, novelty=1, validity=1, usefulness=1), "INVALID_ARGUMENT")
    assert w.store.ratings_for(db_id) == []


@pytest.mark.parametrize("target", ["n1", "e3", "e1", "zz-unknown-404"])
def test_v8_rate_by_a_non_participant_is_not_found_for_any_target(flow, target):
    w, db_id = flow["world"], flow["db_id"]
    fake = fake_id_like(db_id)
    for outsider in ("user_d", "user_x"):
        assert_same_not_found(rate(w, outsider, db_id, target), db_id, rate(w, outsider, fake, target), fake)
    assert w.store.ratings_for(db_id) == []


def test_v8_rate_is_an_upsert_per_rater_and_target(flow):
    w, db_id = flow["world"], flow["db_id"]
    assert_ok(rate(w, "user_a", db_id, "n1", (1, 1, 1)))
    assert_ok(rate(w, "user_a", db_id, "n1", (0, 1, 0)))
    assert_ok(rate(w, "user_c", db_id, "n1", (1, 0, 1)))
    rated = {(r.edge_id, r.rater_id, r.novelty, r.validity, r.usefulness) for r in w.store.ratings_for(db_id)}
    assert rated == {("n1", "user_a", 0, 1, 0), ("n1", "user_c", 1, 0, 1)}
    env = assert_ok(w.call("user_b", "deltabrain_get", deltabrain_id=db_id))
    assert "n1" in dumps(env["untrusted_data"]["ratings"])


def test_v8_quality_is_the_share_of_rated_units_with_all_three_labels(flow):
    """HUMAN-01 v.8 over the rated units, one rater. Five of the six units rated; three are 1/1/1 -> 3/5 = 0.6.

    The numbers are chosen so that no other reading gives 0.6: all six units 3/6, emergent edges only 1/3,
    bridges only 2/2, per-axis means 4/5, 4/5, 1.
    """
    w, db_id = flow["world"], flow["db_id"]
    labels = {"n1": (1, 1, 1), "n2": (1, 1, 1), "e3": (1, 1, 1), "e4": (0, 1, 1), "e9": (1, 0, 1)}
    for target, lab in labels.items():
        assert_ok(rate(w, "user_a", db_id, target, lab))
    want = float(quality(labels))
    assert want == pytest.approx(0.6)
    for other in (3 / 6, 1 / 3, 1.0, 4 / 5):
        assert abs(other - want) > 0.05, "self-check: the readings differ"
    env = assert_ok(w.call("user_a", "deltabrain_get", deltabrain_id=db_id))
    assert "rating_summary" in env, f"TASK §5: deltabrain_get carries rating_summary: {sorted(env)}"
    nums = _numbers(env["rating_summary"])
    assert any(abs(x - want) < 0.006 for x in nums), (
        f"HUMAN-01 v.8 quality {want} (3 of 5 rated units all 1) not in rating_summary: {dumps(env['rating_summary'])}"
    )


# ---------------------------------------------------------------------------
# Synthesis protocol (§2 v.8): constraints and the bridge summary are protocol requirements
# ---------------------------------------------------------------------------


def _protocol_prose(protocol: dict[str, Any]) -> str:
    """The protocol's human-readable text (everything but the generated submission schema)."""
    return dumps({k: v for k, v in protocol.items() if k != "submission_schema"})


def test_v8_protocol_asks_for_constraints_on_bridges(seeded: World):
    env = assert_ok(seeded.open_canal(query=Q01))
    prose = _protocol_prose(env["protocol"])
    assert "constraints" in prose, "§2 v.8: the protocol must ask for the bridge `constraints` (현실 제약 검토)"


def test_v8_protocol_states_the_bridge_summary_rule(seeded: World):
    env = assert_ok(seeded.open_canal(query=Q01))
    prose = _protocol_prose(env["protocol"])
    assert "summary" in prose and "600" in prose, "MUST-Q4 v.8: the L1 rules handed to the synthesizer name the bridge summary (40..600)"


# ---------------------------------------------------------------------------
# NEVER-11 (v.4 rule, v.8 stats): a non-owner's view must not depend on who the private contributor is
#
# Two worlds that differ only in WHO owns C: "distinct" (user_c) and "same" (user_b, who also owns the public B).
# The submission adds to good-01 a B–C bridge n3 (with constraints), a new–new edge e11 (n3 -> n1), a B-side edge
# e12 (n3 -> s-b1, not self-anchor) and a self-anchor edge e13 (s-c3 -> n3). In the "same" world the TRUE stats
# lose n3 as a bridge, e9 and e12 as emergent edges and one bridge with constraints. After C goes private, a viewer
# who does not own C must see the same stats, rating results and errors in both worlds.
# ---------------------------------------------------------------------------

VIEWERS = ("user_a", "user_e")
SUM_N3 = "모양으로 실수를 막는 장치에 에너지를 써서 한 번 더 확인하는 단계를 덧붙여, 맞는 것처럼 보이는 틀린 조합까지 걸러 내는 이중 장치."
R_E11 = "위치별 돌기 배치에 한 번 더 확인하는 단계를 붙이면, 키가 비슷해 잘못 들어간 유닛까지 볼트 체결 전에 걸러 낼 수 있어 형상만 쓸 때보다 오류가 덜 남는다."
R_E12 = "모양만으로 실수를 막는 방식은 비슷한 모양끼리 헷갈릴 때 약하다. 결합 뒤에 한 번 더 확인하는 단계를 더하면 겉보기로 맞는 틀린 조합까지 걸러 낸다."


def rich_delta() -> dict[str, Any]:
    g = load_delta("good-01")
    _node(g, "n1")["constraints"] = "접합부 종류가 늘어 제작비와 도면 관리 공수가 커진다. 위치를 헷갈리기 쉬운 현장에만 쓴다."
    g["nodes"].append(
        {
            "id": "n3",
            "kind": "new",
            "label": "형상 잠금과 재확인 이중 장치",
            "summary": SUM_N3,
            "constraints": "확인 단계를 하나 더 두면 설치 시간이 늘어나므로 오조작 비용이 큰 위치에만 쓴다.",
            "provenance": [_ref("sb_B", "b-n3"), _ref("sb_C", "c-n10")],
        }
    )
    g["nodes"].append({"id": "s-c3", "kind": "source", "label": "동역학적 교정", "provenance": [_ref("sb_C", "c-n10")]})
    g["edges"] += [
        {"id": "e11", "source": "n3", "target": "n1", "relation": "extends", "rationale": R_E11},
        {"id": "e12", "source": "n3", "target": "s-b1", "relation": "extends", "rationale": R_E12},
        {"id": "e13", "source": "s-c3", "target": "n3", "relation": "explains"},
        {"id": "e14", "source": "q", "target": "n3", "relation": "requires"},
    ]
    return g


# The viewer's view: the masked contributor is a separate visible identity, so n3, e9 and e12 cross owners in both worlds.
VIEW_BRIDGES = {"n1", "n2", "n3"}
VIEW_HOST_BRIDGES = {"n1", "n2"}
VIEW_EMERGENT = {"e3", "e4", "e9", "e10", "e11", "e12"}
VIEW_HOST_TOUCHING = {"e3", "e4", "e10", "e11"}
VIEW_CONSTRAINTS = 2
ALL_IDS = [f"e{i}" for i in range(1, 15)] + ["q", "s-a1", "s-a2", "s-a3", "s-b1", "s-c1", "s-c2", "s-c3", "n1", "n2", "n3"]


def test_v8_never11_rich_delta_reference():
    """Self-check of the two worlds' TRUE stats (reference, no implementation)."""
    ctx = fixture_canal_context()
    distinct = analyse(rich_delta(), ctx)
    assert set(distinct.bridges) == VIEW_BRIDGES and set(distinct.emergent) == VIEW_EMERGENT
    assert set(distinct.host_bridges) == VIEW_HOST_BRIDGES and set(distinct.host_touching) == VIEW_HOST_TOUCHING
    assert distinct.bridges_with_constraints == VIEW_CONSTRAINTS and distinct.codes() == set()
    same_ctx = ctx.model_copy(deep=True)
    same_ctx.subbrains[("sb_C", 1)].owner_id = "user_b"
    same = analyse(rich_delta(), same_ctx)
    assert set(same.bridges) == {"n1", "n2"} and set(same.emergent) == {"e3", "e4", "e10", "e11"}
    assert same.bridges_with_constraints == 1 and same.codes() == set()


def _world(base: Path, variant: str) -> dict[str, Any]:
    w = World(base / variant)
    w.ensure_fixture_users()
    w.set_tier("user_b", Tier.PRO)  # user_b may keep two public subbrains in the "same" world
    for fid in ("A", "A2", "B", "D", "X"):
        w.import_fixture(fid)
        assert_ok(w.publish(fid))
    c_key = "C" if variant == "distinct" else "C@user_b"
    w.import_fixture("C", as_user=None if variant == "distinct" else "user_b")
    assert_ok(w.publish(c_key))
    c_sid = w.sid(c_key)

    canal = assert_ok(w.open_canal(query=Q01))
    assert set(member_ids(canal)) == {w.sid("A2"), w.sid("B"), c_sid}, f"{variant}: canal members differ"
    mapping = {"sb_A": (w.sid("A"), 1), "sb_B": (w.sid("B"), 1), "sb_C": (c_sid, 1)}
    sub = assert_ok(w.submit(canal["canal_id"], rewrite_provenance(rich_delta(), mapping)))
    db_id = sub["deltabrain_id"]
    # Self-check: the TRUE stats differ between the worlds.
    true_bridges = VIEW_BRIDGES if variant == "distinct" else {"n1", "n2"}
    assert set(sub["stats"]["bridge_node_ids"]) == true_bridges, f"{variant}: {sub['stats']}"
    assert sub["stats"]["bridges_with_constraints"] == (2 if variant == "distinct" else 1), f"{variant}: {sub['stats']}"
    assert_ok(w.make_private(c_key))

    reps = {
        w.sid("A"): "<SB_A>",
        w.sid("A2"): "<SB_A2>",
        w.sid("B"): "<SB_B>",
        c_sid: "<SB_C>",
        w.sid("D"): "<SB_D>",
        w.sid("X"): "<SB_X>",
        canal["canal_id"]: "<CANAL>",
        db_id: "<DB>",
    }
    raw: dict[tuple[str, str], Any] = {}
    for viewer in VIEWERS:
        got = assert_ok(w.call(viewer, "deltabrain_get", deltabrain_id=db_id))
        assert PRIVATE_CONTRIBUTOR in dumps(got), f"{variant}: C must be masked for {viewer}"
        raw[(viewer, "get")] = got
    for viewer in VIEWERS:
        for target in ALL_IDS:
            raw[(viewer, f"rate:{target}")] = rate(w, viewer, db_id, target, (1, 1, 0))
        raw[(viewer, "rate:unknown")] = rate(w, viewer, db_id, "zz-unknown-404")
    for viewer in VIEWERS:
        raw[(viewer, "get_after_rating")] = w.call(viewer, "deltabrain_get", deltabrain_id=db_id)
        raw[(viewer, "list_after_rating")] = w.call(viewer, "deltabrain_list")
        w.set_tier(viewer, Tier.PRO)
        raw[(viewer, "export")] = w.call(viewer, "deltabrain_export", deltabrain_id=db_id)
    return {"world": w, "db_id": db_id, "reps": reps, "raw": raw}


@pytest.fixture
def two_worlds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENCANAL_MASTER_KEY", raising=False)
    worlds = {v: _world(tmp_path, v) for v in ("distinct", "same")}
    yield worlds
    for out in worlds.values():
        try:
            out["world"].store.close()
        except Exception:
            pass


@pytest.mark.parametrize("variant", ["distinct", "same"])
@pytest.mark.parametrize("viewer", VIEWERS)
def test_v8_never11_viewer_stats_use_visible_identities(two_worlds, variant, viewer):
    out = two_worlds[variant]
    for call in ("get", "get_after_rating"):
        stats = viewer_stats(out["raw"][(viewer, call)])
        assert set(stats["bridge_node_ids"]) == VIEW_BRIDGES, f"{variant}/{viewer}/{call}: {stats}"
        assert set(stats["host_bridge_node_ids"]) == VIEW_HOST_BRIDGES, f"{variant}/{viewer}/{call}: {stats}"
        assert set(stats["emergent_edge_ids"]) == VIEW_EMERGENT, f"{variant}/{viewer}/{call}: {stats}"
        assert set(stats["host_touching_emergent_edge_ids"]) == VIEW_HOST_TOUCHING, f"{variant}/{viewer}/{call}: {stats}"
        assert stats["bridges_with_constraints"] == VIEW_CONSTRAINTS, f"{variant}/{viewer}/{call}: {stats}"


@pytest.mark.parametrize("variant", ["distinct", "same"])
@pytest.mark.parametrize("viewer", VIEWERS)
def test_v8_never11_rateable_in_the_viewers_view(two_worlds, variant, viewer):
    raw = two_worlds[variant]["raw"]
    for target in ALL_IDS:
        env = raw[(viewer, f"rate:{target}")]
        if target in VIEW_BRIDGES | VIEW_EMERGENT:
            assert_ok(env)
        else:
            assert_err(env, "NOT_RATEABLE")
    # The unknown-target code itself is pinned in test_v8_rate_anything_else_is_not_rateable_without_side_effects;
    # here it only has to be identical in both worlds (test_v8_never11_views_identical_...).


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("call", ["get", "get_after_rating", "list_after_rating", "export", "rate:unknown", *(f"rate:{t}" for t in ALL_IDS)])
def test_v8_never11_views_identical_whether_private_contributor_is_visible_owner(two_worlds, viewer, call):
    a = canonical(two_worlds["distinct"]["raw"][(viewer, call)], two_worlds["distinct"]["reps"])
    b = canonical(two_worlds["same"]["raw"][(viewer, call)], two_worlds["same"]["reps"])
    assert a == b, f"{viewer} {call}: response depends on who the private contributor is — {first_difference(a, b)}"


def test_v8_never11_masked_contributor_owner_never_shown(two_worlds):
    for variant, out in two_worlds.items():
        c_sid = next(k for k, v in out["reps"].items() if v == "<SB_C>")
        for viewer in VIEWERS:
            env = out["raw"][(viewer, "get_after_rating")]
            for d in find_dicts(env, lambda d: d.get("subbrain_id") == c_sid):
                assert d.get("owner_id") in (None, ""), f"{variant}/{viewer}: {d}"
            assert "Chaeyoung Yoon" not in dumps(env)
