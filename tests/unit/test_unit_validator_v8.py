"""Unit tests for ORACLE v.8 in the L1 validator: bridges, emergent edges, rating-unit explanations.

§4 (v.8): a bridge is a new node whose owner set has >= 2 owners (host bridge: it also cites the host subbrain).
An emergent edge has >= 2 owners, does not touch the query node, and is not a self-anchor edge (new node N linked
to a source node S whose cited node is already in N's provenance). New–new edges count. Rating unit = bridge
nodes ∪ emergent edges. MUST-Q3 counts both, MUST-Q4 needs a 40-600 char summary on every bridge and a 40-400
char rationale on every emergent edge, MUST-Q7 pools bridge summaries with emergent edge rationales.
"""

from __future__ import annotations

import copy
from fractions import Fraction

import pytest

from opencanal.models import (
    CanalContext,
    DeltabrainSubmission,
    SubbrainDocument,
    SubbrainEdge,
    SubbrainNode,
    SubbrainVersion,
    ViolationCode,
    Visibility,
)
from opencanal.validator import (
    BRIDGE_SUMMARY_MAX_CHARS,
    BRIDGE_SUMMARY_MIN_CHARS,
    compute_stats,
    validate_deltabrain,
)

GENERIC = frozenset({"시너지", "혁신", "가치", "융합", "접근", "synergy", "innovation"})
JOSA = ["에서는", "으로", "에서", "의", "을", "를", "이", "가", "은", "는", "와", "과", "로"]


def _subbrain(subbrain_id, version, owner, nodes, edges=()):
    return SubbrainVersion(
        subbrain_id=subbrain_id,
        version=version,
        owner_id=owner,
        owner_display=owner.upper(),
        visibility=Visibility.PUBLIC,
        is_published_version=True,
        content_hash="0" * 64,
        created_at="2026-10-07T00:00:00Z",
        document=SubbrainDocument(
            title=f"{subbrain_id} title",
            domains=["test"],
            nodes=[SubbrainNode(id=nid, label=label) for nid, label in nodes],
            edges=[SubbrainEdge(source=s, target=t) for s, t in edges],
        ),
    )


def _ctx(c_nodes=(("c1", "형태 상보성"), ("c2", "오류 교정"))) -> CanalContext:
    subbrains = [
        _subbrain("sb_a", 1, "user_a", [("a1", "현장 조립 오류"), ("a2", "접합부 상세"), ("a3", "공차 관리")],
                  [("a1", "a2")]),
        _subbrain("sb_b", 2, "user_b", [("b1", "잘못 놓을 수 없는 블록 모양"), ("b2", "오조작 방지")]),
        _subbrain("sb_b2", 1, "user_b", [("x1", "레벨 디자인 튜토리얼")]),
        _subbrain("sb_c", 1, "user_c", list(c_nodes)),
    ]
    return CanalContext(
        canal_id="canal_v8",
        host_subbrain_id="sb_a",
        host_version=1,
        host_owner_id="user_a",
        subbrains={(s.subbrain_id, s.version): s for s in subbrains},
    )


CTX = _ctx()


def ref(subbrain_id, version, node_id):
    return {"subbrain_id": subbrain_id, "version": version, "node_id": node_id}


A1, A2, A3 = ref("sb_a", 1, "a1"), ref("sb_a", 1, "a2"), ref("sb_a", 1, "a3")
B1, B2, X1 = ref("sb_b", 2, "b1"), ref("sb_b", 2, "b2"), ref("sb_b2", 1, "x1")
C1, C2 = ref("sb_c", 1, "c1"), ref("sb_c", 1, "c2")

LABELS = {
    "a1": "현장 조립 오류", "a2": "접합부 상세", "a3": "공차 관리", "b1": "잘못 놓을 수 없는 블록 모양",
    "b2": "오조작 방지", "x1": "레벨 디자인 튜토리얼", "c1": "형태 상보성", "c2": "오류 교정",
}


def node(node_id, kind, label, *refs, summary=None, constraints=None):
    out = {"id": node_id, "kind": kind, "label": label, "provenance": list(refs)}
    if summary is not None:
        out["summary"] = summary
    if constraints is not None:
        out["constraints"] = constraints
    return out


def src(node_id, r):
    return node(node_id, "source", LABELS[r["node_id"]], r)


def edge(edge_id, source, target, rationale=None, relation="applies_to"):
    out = {"id": edge_id, "source": source, "target": target, "relation": relation}
    if rationale is not None:
        out["rationale"] = rationale
    return out


def summ(tag):
    """In-range (40-600 normalized chars) bridge summary, distinct per tag."""
    return f"{tag} 다리: 접합부마다 위치별로 다른 돌기와 홈을 두어 맞는 자리가 아니면 유닛이 안착하지 않게 하는 상세 {tag}"


def rat(tag):
    """In-range (40-400 normalized chars) edge rationale, distinct per tag."""
    return f"{tag} 연결: 단백질 오류 교정처럼 조립 단계마다 형상 검사를 넣으면 현장 오류가 다음 층으로 넘어가지 않는다 {tag}"


def query():
    return node("q", "query", "모듈러 건축의 현장 조립 오류를 줄일 아이디어")


def run(payload, ctx=CTX):
    return validate_deltabrain(payload, ctx, generic_terms=GENERIC, josa_suffixes=JOSA, josa_min_stem_length=2)


def codes(result):
    return [v.code for v in result.violations]


def by_code(result, code):
    return [v for v in result.violations if v.code == code]


# ---------------------------------------------------------------------------
# §4 emergent edges: query edges and self-anchor edges are excluded, new–new edges count
# ---------------------------------------------------------------------------


def test_a_lone_host_bridge_satisfies_q3_and_its_query_edge_is_not_emergent():
    # v.7 counted q–n as emergent (n cites two owners). v.8: query edges never are; the bridge itself is the unit.
    payload = {"nodes": [query(), node("n", "new", "형상 키 접합", A2, C1, summary=summ("n"))],
               "edges": [edge("e0", "q", "n", rat("e0"))]}
    result = run(payload)
    assert result.ok, result.violations
    stats = result.stats
    assert stats.emergent_edge_ids == [] and stats.host_touching_emergent_edge_ids == []
    assert stats.bridge_node_ids == ["n"] and stats.host_bridge_node_ids == ["n"]


@pytest.mark.parametrize("anchor_edge", [("n", "sc1"), ("sc1", "n")], ids=["new->source", "source->new"])
def test_self_anchor_edges_are_not_emergent_in_either_direction(anchor_edge):
    payload = {
        "nodes": [query(), src("sa1", A1), src("sc1", C1), node("n", "new", "형상 키 접합", A2, C1, summary=summ("n"))],
        "edges": [
            edge("e0", "q", "sa1"),
            edge("e1", "sa1", "n", rat("e1")),  # n does not cite A1: emergent, touches the host
            edge("e2", *anchor_edge),  # sc1 anchors C1, which n already cites: self-anchor, no rationale needed
        ],
    }
    result = run(payload)
    assert result.ok, result.violations
    assert result.stats.emergent_edge_ids == ["e1"]
    assert result.stats.host_touching_emergent_edge_ids == ["e1"]


def test_self_anchor_on_the_host_side_is_not_emergent_either():
    # n cites A2; sa2 anchors A2. The edge touches the host but adds nothing beyond n's own provenance.
    payload = {
        "nodes": [query(), src("sa2", A2), node("n", "new", "형상 키 접합", A2, C1, summary=summ("n"))],
        "edges": [edge("e0", "q", "sa2"), edge("e1", "n", "sa2")],
    }
    result = run(payload)
    assert result.ok, result.violations  # the host bridge alone satisfies MUST-Q3
    assert result.stats.emergent_edge_ids == []


def test_bridge_linked_to_another_node_of_a_subbrain_it_cites_is_emergent():
    # Self-anchor is about the cited node, not the subbrain or owner: n cites A2, sa3 anchors A3.
    payload = {
        "nodes": [query(), src("sa3", A3), node("n", "new", "형상 키 접합", A2, C1, summary=summ("n"))],
        "edges": [edge("e0", "q", "sa3"), edge("e1", "n", "sa3", rat("e1"), "requires")],
    }
    result = run(payload)
    assert result.ok, result.violations
    assert result.stats.emergent_edge_ids == ["e1"]


def test_self_anchor_compares_the_whole_ref_not_the_node_id():
    # sb_c also has a node "a2": n cites (sb_a, a2); the source anchors (sb_c, a2). Different nodes, so emergent.
    ctx = _ctx(c_nodes=(("c1", "형태 상보성"), ("a2", "형태 맞물림")))
    payload = {
        "nodes": [query(), src("sa1", A1), node("sca2", "source", "형태 맞물림", ref("sb_c", 1, "a2")),
                  node("n", "new", "형상 키 접합", A2, C1, summary=summ("n"))],
        "edges": [edge("e0", "q", "sa1"), edge("e1", "q", "n"), edge("e2", "n", "sca2", rat("e2"))],
    }
    result = run(payload, ctx)
    assert result.ok, result.violations
    assert result.stats.emergent_edge_ids == ["e2"]


def test_new_new_edge_between_bridges_is_emergent_even_when_they_share_a_ref():
    payload = {
        "nodes": [
            query(),
            node("n1", "new", "형상 키 접합", A2, C1, summary=summ("n1")),
            node("n2", "new", "블록식 오류 교정 루프", B1, C1, summary=summ("n2")),  # shares C1 with n1
        ],
        "edges": [edge("e0", "q", "n1"), edge("e1", "n1", "n2", rat("e1"), "extends")],
    }
    result = run(payload)
    assert result.ok, result.violations
    assert result.stats.emergent_edge_ids == ["e1"]
    assert result.stats.host_touching_emergent_edge_ids == ["e1"]
    assert result.stats.bridge_node_ids == ["n1", "n2"]
    assert result.stats.host_bridge_node_ids == ["n1"]


def test_new_new_edge_between_single_owner_new_nodes_is_emergent_but_they_are_not_bridges():
    payload = {
        "nodes": [
            query(),
            node("nb", "new", "튜토리얼식 블록 배치 학습", B1, X1),  # user_b only: not a bridge, no summary needed
            node("nc", "new", "형태 기반 오류 교정 순환", C1, C2),  # user_c only
        ],
        "edges": [edge("e0", "q", "nb"), edge("e1", "nb", "nc", rat("e1"), "analogous_to")],
    }
    result = run(payload)
    assert codes(result) == [ViolationCode.HOST_NOT_TOUCHED]
    assert result.stats.emergent_edge_ids == ["e1"]
    assert result.stats.bridge_node_ids == []


# ---------------------------------------------------------------------------
# MUST-Q3 over bridges ∪ emergent edges
# ---------------------------------------------------------------------------


def test_member_only_bridge_without_host_touching_edge_is_host_not_touched():
    payload = {"nodes": [query(), node("n", "new", "블록식 오류 교정", B1, C1, summary=summ("n"))],
               "edges": [edge("e0", "q", "n")]}
    result = run(payload)
    assert codes(result) == [ViolationCode.HOST_NOT_TOUCHED]
    assert result.stats.bridge_node_ids == ["n"] and result.stats.host_bridge_node_ids == []


def test_member_only_bridge_plus_a_host_touching_emergent_edge_passes():
    payload = {
        "nodes": [query(), src("sa1", A1), node("n", "new", "블록식 오류 교정", B1, C1, summary=summ("n"))],
        "edges": [edge("e0", "q", "sa1"), edge("e1", "sa1", "n", rat("e1"))],
    }
    result = run(payload)
    assert result.ok, result.violations
    assert result.stats.host_bridge_node_ids == []
    assert result.stats.host_touching_emergent_edge_ids == ["e1"]


def test_query_and_self_anchor_edges_alone_are_no_emergence_without_a_bridge():
    # n cites one owner twice: not a bridge. Its edges are a query edge and a self-anchor edge.
    payload = {
        "nodes": [query(), src("sa1", A1), node("n", "new", "현장 오류 공차 연동", A1, A3)],
        "edges": [edge("e0", "q", "n"), edge("e1", "n", "sa1", rat("e1"))],
    }
    result = run(payload)
    assert codes(result) == [ViolationCode.NO_EMERGENCE]
    assert result.stats.emergent_edge_ids == [] and result.stats.bridge_node_ids == []


def test_bridges_ignore_refs_that_do_not_resolve():
    # n's second ref is outside the canal / missing: one valid owner, so not a bridge (and Q1 reports the ref).
    for bad in (ref("sb_d", 1, "d1"), ref("sb_c", 1, "c99"), ref("sb_a", 2, "a2")):
        payload = {"nodes": [query(), node("n", "new", "형상 키 접합", A2, bad, summary=summ("n"))],
                   "edges": [edge("e0", "q", "n")]}
        result = run(payload)
        assert result.stats.bridge_node_ids == [], bad
        assert ViolationCode.NO_EMERGENCE in codes(result)


# ---------------------------------------------------------------------------
# MUST-Q4: every rating unit carries an explanation
# ---------------------------------------------------------------------------


def _bridge_payload(summary):
    return {"nodes": [query(), node("n", "new", "형상 키 접합", A2, C1, summary=summary)],
            "edges": [edge("e0", "q", "n")]}


@pytest.mark.parametrize(
    "summary,problem",
    [
        (None, "has no summary"),
        ("", "has no summary"),
        ("!!! ... ", "has no summary"),
        ("가" * (BRIDGE_SUMMARY_MIN_CHARS - 1), "too short (39 chars)"),
        ("짧은 요약" + "ㅤ" * 60, "too short"),  # Hangul fillers count as spaces, not content
        ("㍿" * 151, "too long (604 chars)"),  # 151 raw chars pass pydantic; NFKC expands each to 4
    ],
)
def test_bridge_summary_out_of_range_is_rationale_missing_on_the_node(summary, problem):
    (violation,) = run(_bridge_payload(summary)).violations
    assert violation.code == ViolationCode.RATIONALE_MISSING
    assert violation.node_id == "n" and violation.edge_id is None
    ko, en = violation.message.split(" / ", 1)
    assert problem in en
    assert "다리" in ko and "summary" in ko and f"{BRIDGE_SUMMARY_MIN_CHARS}~{BRIDGE_SUMMARY_MAX_CHARS}자" in ko
    assert "bridge" in en.lower() and f"{BRIDGE_SUMMARY_MIN_CHARS}-{BRIDGE_SUMMARY_MAX_CHARS}" in en
    assert "invisible characters" in en


@pytest.mark.parametrize("summary", ["가" * BRIDGE_SUMMARY_MIN_CHARS, "가" * BRIDGE_SUMMARY_MAX_CHARS, "㍿" * 150])
def test_bridge_summary_bounds_are_inclusive(summary):
    assert run(_bridge_payload(summary)).ok


def test_only_bridges_and_emergent_edges_need_explanations():
    payload = {
        "nodes": [
            query(), src("sa1", A1), src("sc1", C1),
            node("n", "new", "형상 키 접합", A2, C1),  # bridge, no summary
            node("m", "new", "현장 오류 공차 연동", A1, A3),  # one owner: no summary needed
        ],
        "edges": [
            edge("e0", "q", "sa1"),  # query edge
            edge("e1", "n", "sc1"),  # self-anchor
            edge("e2", "m", "sa1"),  # one owner (m cites A1, A3; sa1 anchors A1)
            edge("e3", "sa1", "n"),  # emergent, no rationale
            edge("e4", "sc1", "sa1", "짧다"),  # emergent, too short
        ],
    }
    result = run(payload)
    missing = by_code(result, ViolationCode.RATIONALE_MISSING)
    # Nodes first, then edges, each in submission order.
    assert [(v.node_id, v.edge_id) for v in missing] == [("n", None), (None, "e3"), (None, "e4")]
    assert codes(result) == [ViolationCode.RATIONALE_MISSING] * 3


# ---------------------------------------------------------------------------
# MUST-Q7: bridge summaries and emergent edge rationales in one pool
# ---------------------------------------------------------------------------


def _units(summaries, rationales):
    """q - sa1 - b_k (host bridges with the given summaries) and sa1 - sc_k emergent edges with the given rationales."""
    nodes = [query(), src("sa1", A1)]
    edges = [edge("e0", "q", "sa1")]
    for k, text in enumerate(summaries):
        nodes.append(node(f"b{k}", "new", f"형상 키 접합 변형 {k}", A2, C1, summary=text))
        edges.append(edge(f"eb{k}", "q", f"b{k}"))  # query edge: not a unit
    for k, text in enumerate(rationales):
        nodes.append(src(f"sc{k}", C1 if k % 2 == 0 else C2))
        edges.append(edge(f"e{k + 1}", "sa1", f"sc{k}", text))
    return {"nodes": nodes, "edges": edges}


def test_repeated_bridge_summaries_are_templated():
    same = summ("공통")
    result = run(_units([same, same], [rat(k) for k in range(3)]))  # 2 of 5 units = 40%
    (violation,) = by_code(result, ViolationCode.TEMPLATED_RATIONALE)
    assert codes(result) == [ViolationCode.TEMPLATED_RATIONALE]
    ko, en = violation.message.split(" / ", 1)
    assert "'b0'" in ko and "'b1'" in ko and "다리 노드" in ko
    assert "bridge nodes 'b0', 'b1'" in en and "emergent edges" not in en
    assert "40%" in en and "2 of 5" in en


def test_a_summary_equal_to_a_rationale_counts_for_both_units():
    shared = rat("공유")
    result = run(_units([shared], [shared, rat(1), rat(2), rat(3)]))  # 2 of 5
    (violation,) = by_code(result, ViolationCode.TEMPLATED_RATIONALE)
    assert "bridge nodes 'b0'" in violation.message and "emergent edges 'e1'" in violation.message


def test_templated_share_over_units_at_twenty_percent_passes():
    shared = rat("공유")
    payload = _units([summ(k) for k in range(4)] + [shared], [shared] + [rat(k) for k in range(4)])  # 2 of 10
    result = run(payload)
    assert result.ok, result.violations
    assert len(result.stats.bridge_node_ids) + len(result.stats.emergent_edge_ids) == 10


def test_templated_share_is_exact_at_three_of_fifteen():
    shared = rat("공유")
    rationales = [shared] * 3 + [rat(k) for k in range(7)]
    assert run(_units([summ(k) for k in range(5)], rationales)).ok  # 3 of 15 = exactly 20%
    rationales = [shared] * 4 + [rat(k) for k in range(6)]
    assert codes(run(_units([summ(k) for k in range(5)], rationales))) == [ViolationCode.TEMPLATED_RATIONALE]


def test_bridge_summaries_are_compared_with_their_own_label_substituted():
    # Oracle v.9 MUST-Q7: a summary that differs from another only by its own bridge label is the same template.
    summaries = [f"형상 키 접합 변형 {k}는 위치마다 다른 돌기와 홈으로 틀린 자리를 막는 접합 상세다" for k in range(2)]
    assert codes(run(_units(summaries, [rat(k) for k in range(3)]))) == [ViolationCode.TEMPLATED_RATIONALE]
    # A summary that mentions another bridge's label is not rewritten: only its own label is substituted.
    distinct = [f"형상 키 접합 변형 {k}는 위치마다 다른 돌기와 홈으로 틀린 자리를 막는다" + (" 공장 쪽 공수가 든다" if k else " 현장 쪽 확인이 든다") for k in range(2)]
    assert run(_units(distinct, [rat(k) for k in range(3)])).ok
    copies = [summ("공통"), "  " + summ("공통").upper() + "!!"]
    assert codes(run(_units(copies, [rat(k) for k in range(3)]))) == [ViolationCode.TEMPLATED_RATIONALE]


def test_self_anchor_and_query_edge_rationales_are_not_units():
    # bad-templated's v.8 situation: the same rationale on edges that are not rating units does not count.
    shared = rat("공유")
    payload = {
        "nodes": [query(), src("sa1", A1), src("sa2", A2), src("sc1", C1),
                  node("n", "new", "형상 키 접합", A2, C1, summary=summ("n"))],
        "edges": [
            edge("e0", "q", "sa1", shared),
            edge("e1", "q", "n", shared),
            edge("e2", "n", "sa2", shared),  # self-anchor
            edge("e3", "sc1", "n", shared),  # self-anchor
            edge("e4", "sa1", "n", rat("e4")),
            edge("e5", "sc1", "sa1", rat("e5")),
        ],
    }
    result = run(payload)
    assert result.ok, result.violations
    assert result.stats.emergent_edge_ids == ["e4", "e5"]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def test_bridge_stats_and_constraints_count():
    payload = {
        "nodes": [
            query(), src("sa1", A1),
            node("n1", "new", "형상 키 접합", A2, C1, summary=summ("n1"), constraints="위치마다 다른 철물이라 제작비가 오른다"),
            node("n2", "new", "블록식 오류 교정", B1, C1, summary=summ("n2"), constraints=" ... ㅤ "),  # not filled
            node("n3", "new", "현장 오류 공차 연동", A1, A3, constraints="공차 측정 장비가 필요하다"),  # not a bridge
            node("n4", "new", "튜토리얼식 접합 교육", A3, X1, summary=summ("n4")),  # bridge, no constraints
        ],
        "edges": [
            edge("e0", "q", "sa1"), edge("e1", "q", "n1"), edge("e2", "q", "n2"), edge("e3", "q", "n3"),
            edge("e4", "q", "n4"),
        ],
    }
    result = run(payload)
    assert result.ok, result.violations  # constraints are reported, never enforced
    stats = result.stats
    assert stats.bridge_node_ids == ["n1", "n2", "n4"]
    assert stats.host_bridge_node_ids == ["n1", "n4"]
    assert stats.bridges_with_constraints == 1
    assert stats.new_node_count == 4
    assert compute_stats(DeltabrainSubmission.model_validate(payload), CTX) == stats


def test_results_are_deterministic():
    payload = _units([summ(k) for k in range(3)], [rat(k) for k in range(4)])
    first = run(copy.deepcopy(payload))
    again = run(copy.deepcopy(payload), copy.deepcopy(CTX))
    assert first == again
    assert first.model_dump_json() == again.model_dump_json()


def test_templated_limit_is_the_exact_fraction():
    from opencanal.validator import _TEMPLATED_MAX

    assert _TEMPLATED_MAX == Fraction(1, 5)


# ---------------------------------------------------------------------------
# Messages describe the v.8 rules
# ---------------------------------------------------------------------------

V2_EDGE_REF_PHRASES = (
    "엣지의 출처", "∪", "plus the edge", "edge's own refs", "edge's refs", "in its provenance", "effective provenance",
)


def _no_emergence():
    return {"nodes": [query(), src("sa1", A1), src("sa3", A3)],
            "edges": [edge("e0", "q", "sa1"), edge("e1", "sa1", "sa3", rat("e1"))]}


def _host_not_touched():
    return {"nodes": [query(), node("n", "new", "블록식 오류 교정", B1, C1, summary=summ("n"))],
            "edges": [edge("e0", "q", "n")]}


@pytest.mark.parametrize("make,code", [(_no_emergence, ViolationCode.NO_EMERGENCE),
                                       (_host_not_touched, ViolationCode.HOST_NOT_TOUCHED)])
def test_q3_messages_explain_bridges_and_which_edges_are_emergent(make, code):
    (violation,) = by_code(run(make()), code)
    ko, en = violation.message.split(" / ", 1)
    for phrase in V2_EDGE_REF_PHRASES:
        assert phrase not in violation.message, phrase
    # What a bridge is
    assert "다리" in ko and "주인 2명 이상" in ko and "new 노드" in ko
    assert "bridge" in en and "2 or more different owners" in en and "new node" in en
    # Which edges are emergent
    assert "query 노드에 닿는 엣지" in ko and "자기 앵커" in ko and "new 노드끼리" in ko
    assert "touching the query node" in en and "self-anchor" in en and "between two new nodes" in en
    assert "양 끝 노드" in ko and "엣지에 직접 적은" in ko and "on the edge itself" in en
    # How to fix, including the bridge summary bounds
    assert f"{BRIDGE_SUMMARY_MIN_CHARS}~{BRIDGE_SUMMARY_MAX_CHARS}자 summary" in ko
    assert f"summary of {BRIDGE_SUMMARY_MIN_CHARS}-{BRIDGE_SUMMARY_MAX_CHARS} normalized chars" in en
    if code == ViolationCode.HOST_NOT_TOUCHED:
        assert "호스트 다리" in ko and "host bridge" in en


def test_emergent_edge_rationale_message_says_why_the_edge_is_a_unit():
    payload = _host_not_touched()
    payload["nodes"].append(src("sa1", A1))
    payload["edges"].append(edge("e1", "sa1", "n", "짧다"))
    (violation,) = run(payload).violations
    assert violation.edge_id == "e1"
    ko, en = violation.message.split(" / ", 1)
    assert "창발 엣지" in ko and "자기 앵커" in ko and "40~400자" in ko
    assert "self-anchor" in en and "query node" in en and "40-400" in en


def test_messages_do_not_echo_canal_text():
    payload = _units([summ("공통"), summ("공통")], [rat(k) for k in range(3)])
    payload["nodes"].append(node("bare", "new", "형상 키 접합 무요약", A3, B1))
    payload["edges"].append(edge("eb_bare", "q", "bare"))
    result = run(payload)
    assert set(codes(result)) == {ViolationCode.TEMPLATED_RATIONALE, ViolationCode.RATIONALE_MISSING}
    for violation in result.violations:
        assert "접합부마다" not in violation.message  # summary text written into the deltabrain
        assert "현장 조립 오류" not in violation.message and "형태 상보성" not in violation.message
