"""Oracle v.8 L1 pins — bridges, the new emergent-edge definition, and the rules that read them (pure validator tests).

ORACLE_MANIFEST v2026-10-07.8:
- §4 "다리(bridge) = 주인 집합에 주인이 2명 이상인 new 노드. 호스트 다리 = 호스트 서브브레인을 인용하는 다리 (v.8)"
- §4 "창발 엣지 = ... 주인 2명 이상 / 양 끝 어느 쪽도 query 노드가 아니다 / 자기 앵커 엣지가 아니다 /
  (new–new 엣지는 위 조건을 만족하면 창발이다)"; "평가 단위(다리 단위) = 다리 노드 ∪ 창발 엣지 (v.8)"
- MUST-Q3 (v.8) "다리와 창발 엣지를 합쳐 1개 이상 있고, 그중 1개 이상은 호스트에 닿는다(호스트 다리, 또는 호스트에
  닿는 창발 엣지)"
- MUST-Q4 (v.8) "평가 단위마다 설명이 있다: 창발 엣지에는 rationale(정규화 후 40~400자), 다리 노드에는
  summary(정규화 후 40~600자) | RATIONALE_MISSING (node_id 또는 edge_id 표시)"
- MUST-Q7 (v.8) "평가 단위(다리 노드의 summary, 창발 엣지의 rationale) 중 정규화한 설명이 다른 단위와 똑같은 단위의
  비율이 20% 이하다"
- §2 / §9 (v.8) "다리 노드의 constraints ... L1 거부 사유는 아니고 채운 수를 통계로 보고한다 (bridges_with_constraints)"

Every constructed case is first checked against the independent reference in _v8.py, so the expected verdict follows
from the Oracle text alone. Canal: host sb_A v1 (user_a), members sb_B v1 (user_b), sb_C v1 (user_c).
"""

from __future__ import annotations

import copy

import pytest

from opencanal.models import DeltabrainSubmission
from opencanal.textnorm import normalize

from ._v8 import analyse
from .conftest import Q01, dumps, load_delta, run_validator, violation_codes

GOOD_BRIDGES = {"n1", "n2"}
GOOD_EMERGENT = {"e3", "e4", "e9", "e10"}  # e1, e2 query edges; e5–e8 self-anchor edges
GOOD_HOST_TOUCHING = {"e3", "e4", "e10"}


def _ref(sb: str, node: str, version: int = 1) -> dict:
    return {"subbrain_id": sb, "version": version, "node_id": node}


def _node(g: dict, nid: str) -> dict:
    return next(n for n in g["nodes"] if n["id"] == nid)


def _edge(g: dict, eid: str) -> dict:
    return next(e for e in g["edges"] if e["id"] == eid)


def _check(payload, ctx, cfg, expected: set[str], tolerated: set[str] = frozenset()):
    result = run_validator(payload, ctx, cfg)
    codes = violation_codes(result)
    assert result.ok is False, f"expected rejection with {expected}, got ok"
    assert expected <= codes, f"missing {expected - codes}; got {codes}: {dumps([v.model_dump(mode='json') for v in result.violations])}"
    extra = codes - expected - set(tolerated)
    assert not extra, f"unexpected extra violations {extra} (target {expected}): {dumps([v.model_dump(mode='json') for v in result.violations])}"
    return result


def _accept(payload, ctx, cfg):
    result = run_validator(payload, ctx, cfg)
    assert result.ok is True, f"expected acceptance, got {[(v.code.value, v.node_id, v.edge_id, v.message) for v in result.violations]}"
    assert result.violations == []
    return result


def _expect(g: dict, ctx, codes: set[str]):
    """Self-check: the v.8 reference gives exactly `codes` for the rules it models (Q3, Q4 lengths, Q7)."""
    ref = analyse(g, ctx)
    assert ref.codes() == codes, f"self-check: the v.8 reference gives {ref.codes()}, test expects {codes}"
    return ref


def _assert_stats(stats, ref, *, constraints: int | None = None) -> None:
    assert stats is not None
    assert set(stats.bridge_node_ids) == set(ref.bridges), f"bridge_node_ids {stats.bridge_node_ids} != {ref.bridges}"
    assert len(stats.bridge_node_ids) == len(set(stats.bridge_node_ids))
    assert set(stats.host_bridge_node_ids) == set(ref.host_bridges), (
        f"host_bridge_node_ids {stats.host_bridge_node_ids} != {ref.host_bridges}"
    )
    assert set(stats.emergent_edge_ids) == set(ref.emergent), f"emergent_edge_ids {stats.emergent_edge_ids} != {ref.emergent}"
    assert len(stats.emergent_edge_ids) == len(set(stats.emergent_edge_ids))
    assert set(stats.host_touching_emergent_edge_ids) == set(ref.host_touching), (
        f"host_touching_emergent_edge_ids {stats.host_touching_emergent_edge_ids} != {ref.host_touching}"
    )
    want = ref.bridges_with_constraints if constraints is None else constraints
    assert stats.bridges_with_constraints == want, f"bridges_with_constraints {stats.bridges_with_constraints} != {want}"


def _missing_targets(result) -> set[str]:
    """MUST-Q4 v.8: every RATIONALE_MISSING names exactly one target — a node_id (bridge) or an edge_id (edge)."""
    out: set[str] = set()
    for v in result.violations:
        if v.code.value != "RATIONALE_MISSING":
            continue
        named = [x for x in (v.node_id, v.edge_id) if x]
        assert len(named) == 1, f"RATIONALE_MISSING must name a node_id or an edge_id (one of them): {v.model_dump(mode='json')}"
        out.add(named[0])
    return out


_HANGUL_RUN = (
    "다리노드의요약은두두뇌의개념이어떻게만나는지구체적으로적어야평가할수있고같은개념도서술이구체적이어야쓸모가판단된다"
    "현장에서는비용과공수와공정이함께움직이므로설치순서와검사지점을같이적어두면연결이성립하는조건이드러난다"
)


def hangul(n: int) -> str:
    text = (_HANGUL_RUN * (n // len(_HANGUL_RUN) + 1))[:n]
    assert len(normalize(text)) == n, "self-check: pure Hangul without spaces normalizes to itself"
    return text


# Distinct descriptions (40..400 normalized). None of them contains a node label of the deltabrains below.
R_NEW_NEW = "위치마다 다른 돌기로 유닛 자리를 강제해도 설치 직후 맞물림을 확인하는 절차가 없으면 덜 들어간 상태를 놓친다. 두 장치를 함께 써야 서로의 빈틈이 메워진다."
R_SHARED_REF = "돌기와 홈의 배치를 단백질 표면의 요철 규칙에서 빌려 오면, 위치별 키를 설계할 때 몇 가지 형상만으로도 서로 바꿔 끼울 수 없는 조합을 많이 만들 수 있다."
R_SAME_SUBBRAIN = "정해진 면끼리만 붙는다는 게임 규칙을 유닛 철물에 옮기면, 위치별 키의 종류를 정하는 기준이 화면 규칙처럼 단순해지고 현장 작업자가 바로 읽을 수 있다."
R_SLOT_COLOR = "테두리 색과 요철을 겹쳐 쓰는 표시법을 슬롯 위치에 옮기면, 작업자가 볼트를 넣기 전에 어느 슬롯이 어느 유닛 것인지 한눈에 구분할 수 있다."
R_C2_A1 = "잘못 결합한 서브유닛이 결합 에너지가 낮아 저절로 떨어지듯, 틀린 위치에 내려놓은 유닛도 고정 전에 빠지도록 하면 실수가 다음 층으로 쌓이지 않는다."
SUM_N3 = "게임 블록의 요철 배치 규칙과 단백질 표면의 맞물림 원리를 묶어, 서로 바꿔 끼울 수 없는 형상 조합을 체계적으로 만드는 설계 규칙."
SUM_BC = "틀린 자리에 놓인 블록은 결합력이 약해 저절로 빠지고, 맞는 자리에서만 단단히 고정되도록 요철과 결합면을 함께 설계하는 방식이다."
SHARED = "위치마다 다른 맞물림을 주고 놓을 때마다 확인해서, 틀린 조합이 볼트를 조이기 전에 바로 드러나게 만드는 현장 장치에 대한 설명이다."
TEMPLATE = "두 개념은 서로 다른 분야에서 왔지만 구조가 비슷해서 함께 쓰면 질의에 답하는 데 도움이 될 수 있다."


# ---------------------------------------------------------------------------
# Constructed deltabrains (module-level so they can be reviewed by hand)
# ---------------------------------------------------------------------------


def with_new_new_edge() -> dict:
    """good-01 + e11 n1 -> n2: a new–new edge joining two bridges (owners {a,b} ∪ {c,a})."""
    g = load_delta("good-01")
    g["edges"].append({"id": "e11", "source": "n1", "target": "n2", "relation": "requires", "rationale": R_NEW_NEW})
    return g


def with_bridges_sharing_a_cited_node() -> dict:
    """good-01 + n3 (cites b-n2 like n1, and c-n2) + e11 n1 -> n3 (new–new: no self-anchor rule) + e12 n3 -> s-c1
    (s-c1 cites c-n2, which n3 cites: self-anchor) + e13 n1 -> s-b3 (s-b3 cites b-n1 of the same subbrain sb_B, a
    node n1 does NOT cite: not a self-anchor edge — the rule is about the cited node, not the subbrain)."""
    g = load_delta("good-01")
    g["nodes"].append(
        {
            "id": "n3",
            "kind": "new",
            "label": "요철 배치 형상 문법",
            "summary": SUM_N3,
            "provenance": [_ref("sb_B", "b-n2"), _ref("sb_C", "c-n2")],
        }
    )
    g["nodes"].append({"id": "s-b3", "kind": "source", "label": "블록 조립 규칙", "provenance": [_ref("sb_B", "b-n1")]})
    g["edges"].append({"id": "e11", "source": "n1", "target": "n3", "relation": "requires", "rationale": R_SHARED_REF})
    g["edges"].append({"id": "e12", "source": "n3", "target": "s-c1", "relation": "extends"})
    g["edges"].append({"id": "e13", "source": "n1", "target": "s-b3", "relation": "extends", "rationale": R_SAME_SUBBRAIN})
    return g


def with_query_edge_to_bridge() -> dict:
    """good-01 + e11 q -> n1: owners of the edge are n1's owners {a,b}, but a query edge is never emergent."""
    g = load_delta("good-01")
    g["edges"].append({"id": "e11", "source": "q", "target": "n1", "relation": "requires", "rationale": R_NEW_NEW})
    return g


def single_owner_parts(*, new_new_edge: bool) -> dict:
    """A and B both contribute, but no node and no edge crosses owners: n-a cites only A, n-b cites only B,
    the anchors hang off the query node and off their own new node (self-anchor). With new_new_edge, one
    n-b -> n-a edge joins the two owners."""
    g = {
        "nodes": [
            {"id": "q", "kind": "query", "label": Q01},
            {"id": "s-a2", "kind": "source", "label": "접합부 상세", "provenance": [_ref("sb_A", "a-n3")]},
            {"id": "s-b1", "kind": "source", "label": "잘못 놓을 수 없는 블록 모양", "provenance": [_ref("sb_B", "b-n2")]},
            {
                "id": "n-a",
                "kind": "new",
                "label": "공차 흡수형 볼트 슬롯",
                "provenance": [_ref("sb_A", "a-n3"), _ref("sb_A", "a-n4")],
            },
            {
                "id": "n-b",
                "kind": "new",
                "label": "요철 색상 이중 표시 블록",
                "provenance": [_ref("sb_B", "b-n2"), _ref("sb_B", "b-n7")],
            },
        ],
        "edges": [
            {"id": "e1", "source": "q", "target": "s-a2", "relation": "requires"},
            {"id": "e2", "source": "q", "target": "s-b1", "relation": "requires"},
            {"id": "e3", "source": "n-a", "target": "s-a2", "relation": "extends"},
            {"id": "e4", "source": "n-b", "target": "s-b1", "relation": "extends"},
            {"id": "e5", "source": "q", "target": "n-a", "relation": "requires"},
            {"id": "e6", "source": "q", "target": "n-b", "relation": "requires"},
        ],
    }
    if new_new_edge:
        g["edges"].append({"id": "e7", "source": "n-b", "target": "n-a", "relation": "applies_to", "rationale": R_SLOT_COLOR})
    return g


def member_bridge_only(*, host_edge: bool) -> dict:
    """The only bridge joins B and C (no host ref); its edges are a query edge and two self-anchor edges.
    The host anchor s-a1 hangs off the query node. With host_edge, one emergent s-c2 -> s-a1 edge touches the host."""
    g = {
        "nodes": [
            {"id": "q", "kind": "query", "label": Q01},
            {"id": "s-a1", "kind": "source", "label": "현장 조립 오류", "provenance": [_ref("sb_A", "a-n2")]},
            {"id": "s-b1", "kind": "source", "label": "잘못 놓을 수 없는 블록 모양", "provenance": [_ref("sb_B", "b-n2")]},
            {"id": "s-c2", "kind": "source", "label": "오류 교정 기제", "provenance": [_ref("sb_C", "c-n3")]},
            {
                "id": "n-bc",
                "kind": "new",
                "label": "맞물림 기반 자가 교정 블록",
                "summary": SUM_BC,
                "provenance": [_ref("sb_B", "b-n2"), _ref("sb_C", "c-n3")],
            },
        ],
        "edges": [
            {"id": "e1", "source": "q", "target": "s-a1", "relation": "requires"},
            {"id": "e2", "source": "q", "target": "s-b1", "relation": "requires"},
            {"id": "e3", "source": "q", "target": "n-bc", "relation": "requires"},
            {"id": "e4", "source": "n-bc", "target": "s-b1", "relation": "extends"},
            {"id": "e5", "source": "s-c2", "target": "n-bc", "relation": "explains"},
        ],
    }
    if host_edge:
        g["edges"].append({"id": "e6", "source": "s-c2", "target": "s-a1", "relation": "explains", "rationale": R_C2_A1})
    return g


def host_bridge_only() -> dict:
    """One host bridge n1 (B + A) and no emergent edge at all: its two edges are self-anchor edges."""
    g = load_delta("good-01")
    keep_nodes = {"q", "s-a2", "s-b1", "n1"}
    g["nodes"] = [n for n in g["nodes"] if n["id"] in keep_nodes]
    g["edges"] = [
        {"id": "e1", "source": "q", "target": "s-a2", "relation": "requires"},
        {"id": "e2", "source": "n1", "target": "s-a2", "relation": "applies_to"},
        {"id": "e3", "source": "n1", "target": "s-b1", "relation": "extends"},
    ]
    return g


def ten_units() -> dict:
    """good-01 (2 bridges + 4 emergent edges) + 4 cross-subbrain source–source emergent edges = exactly 10 units."""
    g = load_delta("good-01")
    extra = [
        ("e11", "s-c2", "s-a1", "explains", R_C2_A1),
        (
            "e12",
            "s-b1",
            "s-a1",
            "applies_to",
            "블록의 요철처럼 위치마다 다른 맞물림을 주면 크레인 기사가 유닛 번호를 확인하지 않아도 엉뚱한 자리에 내려놓는 실수가 줄어든다.",
        ),
        (
            "e13",
            "s-c2",
            "s-b1",
            "explains",
            "약하게 붙은 틀린 짝이 저절로 떨어져 나가는 세포의 방식은, 게임에서 틀린 조합이 화면에 남지 않도록 막는 규칙이 왜 실수를 줄이는지 보여 준다.",
        ),
        (
            "e14",
            "s-c1",
            "s-a3",
            "requires",
            "맞물리는 표면끼리만 붙게 하려면 돌기와 홈의 치수가 제작 오차보다 넉넉해야 한다. 허용 오차를 단계별로 나눠 주지 않으면 맞는 유닛도 들어가지 않는다.",
        ),
    ]
    for eid, s, t, rel, rat in extra:
        g["edges"].append({"id": eid, "source": s, "target": t, "relation": rel, "rationale": rat})
    return g


# ---------------------------------------------------------------------------
# §4 definitions -> stats (bridges, host bridges, emergent edges, constraints)
# ---------------------------------------------------------------------------


def test_v8_good01_still_accepted_with_v8_stats(ctx, cfg):
    """good-01 bridges n1/n2 have summaries of 57/62 normalized chars (MUST-Q4 v.8 40..600), so no good-02 is needed."""
    g = load_delta("good-01")
    ref = _expect(g, ctx, set())
    assert set(ref.bridges) == GOOD_BRIDGES and set(ref.emergent) == GOOD_EMERGENT
    assert set(ref.self_anchor) == {"e5", "e6", "e7", "e8"} and set(ref.query_edges) == {"e1", "e2"}
    for nid in GOOD_BRIDGES:
        assert 40 <= len(normalize(_node(g, nid)["summary"])) <= 600
    result = _accept(g, ctx, cfg)
    _assert_stats(result.stats, ref, constraints=0)
    assert set(result.stats.host_bridge_node_ids) == GOOD_BRIDGES
    assert set(result.stats.host_touching_emergent_edge_ids) == GOOD_HOST_TOUCHING
    assert result.stats.node_count == 9 and result.stats.edge_count == 10 and result.stats.new_node_count == 2


def test_v8_compute_stats_uses_v8_definitions(ctx):
    from opencanal.validator import compute_stats

    g = with_bridges_sharing_a_cited_node()
    ref = analyse(g, ctx)
    stats = compute_stats(DeltabrainSubmission.model_validate(g), ctx)
    _assert_stats(stats, ref)


def test_v8_self_anchor_and_query_edges_are_not_emergent(ctx, cfg):
    """e5/e6/e7 (new -> its own anchor) and e8 (anchor -> new) are self-anchor edges; e1/e2 and an added q -> n1
    (whose owner set is {a,b}) are query edges. None is emergent; e10 (n1 -> s-a3, a-n4 not cited by n1) is."""
    g = with_query_edge_to_bridge()
    ref = _expect(g, ctx, set())
    assert "e11" in ref.query_edges and "e11" not in ref.emergent
    result = _accept(g, ctx, cfg)
    _assert_stats(result.stats, ref)
    assert set(result.stats.emergent_edge_ids) == GOOD_EMERGENT


def test_v8_new_new_edge_is_emergent(ctx, cfg):
    g = with_new_new_edge()
    ref = _expect(g, ctx, set())
    assert set(ref.emergent) == GOOD_EMERGENT | {"e11"}
    result = _accept(g, ctx, cfg)
    _assert_stats(result.stats, ref)
    assert "e11" in result.stats.emergent_edge_ids and "e11" in result.stats.host_touching_emergent_edge_ids


def test_v8_self_anchor_is_decided_by_the_cited_node_and_never_applies_to_new_new(ctx, cfg):
    g = with_bridges_sharing_a_cited_node()
    ref = _expect(g, ctx, set())
    assert set(ref.bridges) == {"n1", "n2", "n3"} and set(ref.host_bridges) == {"n1", "n2"}
    assert "e11" in ref.emergent, "new–new edge between bridges that both cite b-n2"
    assert "e12" in ref.self_anchor, "n3 -> s-c1: c-n2 is in n3's provenance"
    assert "e13" in ref.emergent, "n1 -> s-b3: same subbrain sb_B, but b-n1 is not in n1's provenance"
    result = _accept(g, ctx, cfg)
    _assert_stats(result.stats, ref)


# ---------------------------------------------------------------------------
# MUST-Q3 (v.8) — over the union of bridges and emergent edges
# ---------------------------------------------------------------------------


def test_v8_q3_two_owners_but_no_cross_owner_node_or_edge_is_no_emergence(ctx, cfg):
    """A and B both appear, but every new node cites a single owner and every edge is a query or self-anchor edge."""
    g = single_owner_parts(new_new_edge=False)
    ref = analyse(g, ctx)
    assert ref.units == [] and ref.codes() == {"NO_EMERGENCE"}
    assert {o for owners in ref.owners.values() for o in owners} == {"user_a", "user_b"}, "self-check: two owners present"
    result = _check(g, ctx, cfg, {"NO_EMERGENCE"}, tolerated={"HOST_NOT_TOUCHED"})
    assert result.stats is not None
    assert result.stats.bridge_node_ids == [] and result.stats.emergent_edge_ids == []


def test_v8_q3_a_single_new_new_edge_is_enough(ctx, cfg):
    """Same graph + one n-b -> n-a edge: zero bridges, one emergent host-touching edge -> accepted."""
    g = single_owner_parts(new_new_edge=True)
    ref = _expect(g, ctx, set())
    assert ref.bridges == [] and ref.emergent == ["e7"] and ref.host_touching == ["e7"]
    result = _accept(g, ctx, cfg)
    _assert_stats(result.stats, ref)


def test_v8_q3_only_member_bridges_is_host_not_touched(ctx, cfg):
    """The only unit is the B–C bridge (its edges are a query edge and self-anchor edges): HOST_NOT_TOUCHED, nothing else.
    No rationale is needed on those edges (MUST-Q4 v.8 asks rationale of emergent edges only)."""
    g = member_bridge_only(host_edge=False)
    ref = analyse(g, ctx)
    assert ref.units == ["n-bc"] and ref.host_bridges == [] and ref.codes() == {"HOST_NOT_TOUCHED"}
    result = _check(g, ctx, cfg, {"HOST_NOT_TOUCHED"})
    _assert_stats(result.stats, ref)


def test_v8_q3_member_bridge_plus_host_touching_emergent_edge_is_accepted(ctx, cfg):
    g = member_bridge_only(host_edge=True)
    ref = _expect(g, ctx, set())
    assert ref.host_bridges == [] and ref.host_touching == ["e6"]
    result = _accept(g, ctx, cfg)
    _assert_stats(result.stats, ref)


def test_v8_q3_a_host_bridge_alone_is_enough(ctx, cfg):
    """No emergent edge at all; the host bridge n1 is the unit that touches the host. Its two self-anchor edges
    need no rationale (MUST-Q4 v.8)."""
    g = host_bridge_only()
    ref = _expect(g, ctx, set())
    assert ref.bridges == ["n1"] and ref.host_bridges == ["n1"] and ref.emergent == []
    result = _accept(g, ctx, cfg)
    _assert_stats(result.stats, ref, constraints=0)


def test_v8_q3_bad_same_owner_is_still_no_emergence(ctx, cfg):
    _expect(load_delta("bad-same-owner"), ctx, {"NO_EMERGENCE"})
    _check(load_delta("bad-same-owner"), ctx, cfg, {"NO_EMERGENCE"}, tolerated={"HOST_NOT_TOUCHED"})


# ---------------------------------------------------------------------------
# MUST-Q4 (v.8) — a summary on every bridge, a rationale on every emergent edge, and only there
# ---------------------------------------------------------------------------


def _with_summary(nid: str, text) -> dict:
    g = load_delta("good-01")
    if text is None:
        _node(g, nid).pop("summary", None)
    else:
        _node(g, nid)["summary"] = text
    return g


@pytest.mark.parametrize("length,ok", [(39, False), (40, True), (600, True)])
def test_v8_q4_bridge_summary_length_boundaries(ctx, cfg, length, ok):
    g = _with_summary("n1", hangul(length))
    if ok:
        _expect(g, ctx, set())
        _accept(g, ctx, cfg)
    else:
        _expect(g, ctx, {"RATIONALE_MISSING"})
        result = _check(g, ctx, cfg, {"RATIONALE_MISSING"})
        assert _missing_targets(result) == {"n1"}


def test_v8_q4_bridge_summary_of_601_normalized_chars_is_rationale_missing(ctx, cfg):
    """600 raw characters (the DeltaNode.summary field limit) that normalize to 601: NFKC turns U+FB00 into "ff"."""
    text = hangul(599) + "ﬀ"
    assert len(text) == 600 and len(normalize(text)) == 601, "self-check"
    g = _with_summary("n1", text)
    _expect(g, ctx, {"RATIONALE_MISSING"})
    result = _check(g, ctx, cfg, {"RATIONALE_MISSING"})
    assert _missing_targets(result) == {"n1"}


def test_v8_q4_bridge_summary_of_601_raw_chars_is_rejected(ctx, cfg):
    """Over the contract field limit (models.DeltaNode.summary max_length=600): rejected either as a schema error
    (MUST-Q0) or as MUST-Q4 — never accepted."""
    g = _with_summary("n1", hangul(601))
    result = run_validator(g, ctx, cfg)
    codes = violation_codes(result)
    assert result.ok is False
    assert codes in ({"SCHEMA_INVALID"}, {"RATIONALE_MISSING"}), codes


def test_v8_q4_bridge_without_summary_names_the_node(ctx, cfg):
    g = _with_summary("n2", None)
    _expect(g, ctx, {"RATIONALE_MISSING"})
    result = _check(g, ctx, cfg, {"RATIONALE_MISSING"})
    assert _missing_targets(result) == {"n2"}


@pytest.mark.parametrize(
    "text",
    [hangul(30) + "ㅤ" * 20, hangul(30) + "​" * 20, "   " + hangul(20) + " !?…·~ " * 10],
    ids=["hangul_filler_tail", "zwsp_tail", "punctuation_padding"],
)
def test_v8_q4_bridge_summary_padding_does_not_count(ctx, cfg, text):
    assert len(text) >= 40 and len(normalize(text)) < 40, "self-check: only the raw length passes"
    g = _with_summary("n1", text)
    _expect(g, ctx, {"RATIONALE_MISSING"})
    result = _check(g, ctx, cfg, {"RATIONALE_MISSING"})
    assert _missing_targets(result) == {"n1"}


def test_v8_q4_bridge_and_edge_violations_are_reported_together_with_their_ids(ctx, cfg):
    g = _with_summary("n1", "짧은 요약.")
    del _edge(g, "e9")["rationale"]
    _expect(g, ctx, {"RATIONALE_MISSING"})
    result = _check(g, ctx, cfg, {"RATIONALE_MISSING"})
    assert _missing_targets(result) == {"n1", "e9"}
    by_target = {(v.node_id, v.edge_id) for v in result.violations if v.code.value == "RATIONALE_MISSING"}
    assert ("n1", None) in by_target and (None, "e9") in by_target, by_target


def test_v8_q4_new_new_emergent_edge_needs_a_rationale(ctx, cfg):
    g = with_new_new_edge()
    del _edge(g, "e11")["rationale"]
    _expect(g, ctx, {"RATIONALE_MISSING"})
    result = _check(g, ctx, cfg, {"RATIONALE_MISSING"})
    assert _missing_targets(result) == {"e11"}


def test_v8_q4_self_anchor_and_query_edges_need_no_rationale(ctx, cfg):
    """v.7 asked rationale of e5–e8 (then emergent). v.8: only emergent edges; a query edge may carry a short one."""
    g = load_delta("good-01")
    for eid in ("e5", "e6", "e7", "e8"):
        del _edge(g, eid)["rationale"]
    _edge(g, "e1")["rationale"] = "질의 맥락."
    _expect(g, ctx, set())
    _accept(g, ctx, cfg)


def test_v8_q4_single_owner_new_node_needs_no_summary(ctx, cfg):
    """A `new` node citing one owner is not a bridge, so MUST-Q4 v.8 asks no summary of it."""
    g = load_delta("good-01")
    g["nodes"].append(
        {"id": "n-a", "kind": "new", "label": "공차 흡수형 볼트 슬롯", "provenance": [_ref("sb_A", "a-n3"), _ref("sb_A", "a-n4")]}
    )
    g["edges"].append({"id": "e11", "source": "n-a", "target": "s-a2", "relation": "extends"})
    ref = _expect(g, ctx, set())
    assert "n-a" not in ref.bridges
    result = _accept(g, ctx, cfg)
    _assert_stats(result.stats, ref)
    assert result.stats.new_node_count == 3


# ---------------------------------------------------------------------------
# MUST-Q7 (v.8) — the templated share is taken over the units (bridge summaries + emergent edge rationales)
# ---------------------------------------------------------------------------


def test_v8_q7_identical_bridge_summaries_are_templated(ctx, cfg):
    g = load_delta("good-01")
    for nid in ("n1", "n2"):
        _node(g, nid)["summary"] = SHARED
    ref = _expect(g, ctx, {"TEMPLATED_RATIONALE"})
    assert ref.templated_share == pytest.approx(2 / 6)
    _check(g, ctx, cfg, {"TEMPLATED_RATIONALE"})


def test_v8_q7_a_bridge_summary_equal_to_an_emergent_rationale_counts(ctx, cfg):
    g = load_delta("good-01")
    _node(g, "n1")["summary"] = SHARED
    _edge(g, "e3")["rationale"] = SHARED  # e3 ends: 형태 상보성 / 현장 조립 오류 — neither occurs in SHARED
    ref = _expect(g, ctx, {"TEMPLATED_RATIONALE"})
    assert ref.templated_share == pytest.approx(2 / 6)
    _check(g, ctx, cfg, {"TEMPLATED_RATIONALE"})


def test_v8_q7_identical_rationales_on_self_anchor_and_query_edges_do_not_count(ctx, cfg):
    """These edges are not units. Under v.7 (e5–e8 emergent) this was 4/8 templated; under v.8 it is 0/6."""
    g = load_delta("good-01")
    for eid in ("e1", "e2", "e5", "e6", "e7", "e8"):
        _edge(g, eid)["rationale"] = TEMPLATE
    ref = _expect(g, ctx, set())
    assert ref.templated_share == 0
    _accept(g, ctx, cfg)


def test_v8_q7_two_of_ten_units_identical_is_allowed(ctx, cfg):
    g = ten_units()
    _node(g, "n2")["summary"] = SHARED
    _edge(g, "e13")["rationale"] = SHARED
    ref = _expect(g, ctx, set())
    assert len(ref.units) == 10 and ref.templated_share == pytest.approx(0.2)
    _accept(g, ctx, cfg)


def test_v8_q7_three_of_ten_units_identical_is_templated(ctx, cfg):
    g = ten_units()
    _node(g, "n2")["summary"] = SHARED
    for eid in ("e13", "e14"):
        _edge(g, eid)["rationale"] = SHARED
    ref = _expect(g, ctx, {"TEMPLATED_RATIONALE"})
    assert len(ref.units) == 10 and ref.templated_share == pytest.approx(0.3)
    _check(g, ctx, cfg, {"TEMPLATED_RATIONALE"})


def test_v8_q7_bad_templated_02_is_templated(ctx, cfg):
    """fixtures/deltabrains/bad-templated-02.json: the v.8 replacement of bad-templated.json (see
    test_oracle_validator.py::test_must_q7_templated_rationale). The template sits on emergent e4, e9, e10."""
    g = load_delta("bad-templated-02")
    ref = _expect(g, ctx, {"TEMPLATED_RATIONALE"})
    assert ref.templated_share == pytest.approx(3 / 6)
    _check(g, ctx, cfg, {"TEMPLATED_RATIONALE"})


# ---------------------------------------------------------------------------
# constraints (§2 / §9 v.8) — reported in stats, never an L1 rejection
# ---------------------------------------------------------------------------


def test_v8_constraints_are_counted_on_bridges_only_and_never_rejected(ctx, cfg):
    g = load_delta("good-01")
    _node(g, "n1")["constraints"] = "접합부 종류가 늘어 제작비와 도면 관리 공수가 커진다. 위치를 헷갈리기 쉬운 현장에만 쓴다."
    _node(g, "n2")["constraints"] = "비용 증가"  # short: constraints have no length rule
    g["nodes"].append(
        {
            "id": "n-a",
            "kind": "new",
            "label": "공차 흡수형 볼트 슬롯",
            "constraints": "슬롯이 길면 접합 강성이 떨어진다.",
            "provenance": [_ref("sb_A", "a-n3"), _ref("sb_A", "a-n4")],
        }
    )
    g["edges"].append({"id": "e11", "source": "n-a", "target": "s-a2", "relation": "extends"})
    ref = _expect(g, ctx, set())
    assert ref.bridges_with_constraints == 2, "self-check: n-a is not a bridge"
    result = _accept(g, ctx, cfg)
    _assert_stats(result.stats, ref, constraints=2)


def test_v8_constraints_missing_on_every_bridge_is_accepted_and_reported_as_zero(ctx, cfg):
    g = load_delta("good-01")
    assert all("constraints" not in n for n in g["nodes"])
    result = _accept(g, ctx, cfg)
    assert result.stats.bridges_with_constraints == 0


def test_v8_constraints_on_one_bridge_counts_one(ctx, cfg):
    g = load_delta("good-01")
    _node(g, "n1")["constraints"] = "위치별 키를 미리 정하려면 유닛 배치가 설계 단계에서 확정되어야 하고, 접합부 종류만큼 금형이 늘어난다."
    result = _accept(g, ctx, cfg)
    assert result.stats.bridges_with_constraints == 1


# ---------------------------------------------------------------------------
# Golden files under v.8
# ---------------------------------------------------------------------------


def test_v8_bad_host_untouched_also_lacks_a_bridge_summary(ctx, cfg):
    """bad-host-untouched.json (§6.4: HOST_NOT_TOUCHED). Its only bridge n-bc has a 27-char summary, so MUST-Q4 v.8
    adds RATIONALE_MISSING naming n-bc. e4/e5 are self-anchor edges now; e3 (s-c1 -> s-b1) is the only emergent edge."""
    g = load_delta("bad-host-untouched")
    ref = _expect(g, ctx, {"HOST_NOT_TOUCHED", "RATIONALE_MISSING"})
    assert ref.q4_nodes == ["n-bc"] and ref.emergent == ["e3"]
    result = _check(g, ctx, cfg, {"HOST_NOT_TOUCHED", "RATIONALE_MISSING"})
    assert _missing_targets(result) == {"n-bc"}
    _assert_stats(result.stats, ref)


def test_v8_validator_does_not_mutate_v8_inputs(ctx, cfg):
    g = with_bridges_sharing_a_cited_node()
    _node(g, "n1")["constraints"] = "제작비가 늘어난다."
    before = copy.deepcopy(g)
    run_validator(g, ctx, cfg)
    assert g == before
