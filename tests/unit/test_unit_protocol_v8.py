"""Unit tests for the v.8 synthesis protocol (ORACLE v2026-10-07.8: §4 bridges and emergent edges, MUST-Q3,
MUST-Q4, MUST-Q7, HUMAN-01, and the owner decision on real-world constraints).

The synthesizing LLM reads the rules and instructions as its acceptance criteria, so they must state the v.8
definitions and none of the v.7 ones.
"""

from __future__ import annotations

import pydantic
import pytest

from opencanal.models import DeltabrainSubmission, DeltaNode, NodeKind, ViolationCode
from opencanal.protocol import synthesis_protocol

# Wording of the v.7 protocol that is wrong under v.8: emergence counted every cross-owner edge (query edges and
# self-anchor edges included), the host rule needed an emergent edge, and only edges needed explanations.
V7_PHRASES = (
    "창발 엣지를 1개 이상 만든다",
    "Create at least one emergent edge",
    "창발 엣지 중 1개 이상은",
    "At least one emergent edge must have",
    "At least one emergent edge has an end node",
    "[NO_EMERGENCE] 창발 엣지가 1개 이상 있다",
    "At least one emergent edge:",
    "rationale이 다른 엣지와 같은 창발 엣지의 비율",
    "of emergent edges share the same rationale",
    "new 노드를 다른 노드와 잇거나",
    "Connect a new node that cites nodes of different owners",
    "[RATIONALE_MISSING] 창발 엣지마다",
    "Every emergent edge has a rationale",
    "Give every emergent edge a specific rationale",
)


def _text() -> str:
    p = synthesis_protocol()
    return "\n".join([p["instructions"], *p["rules"]])


def _rule(code: ViolationCode) -> tuple[str, str]:
    (rule,) = [r for r in synthesis_protocol()["rules"] if r.startswith(f"[{code.value}]")]
    ko, en = rule.split(" / ", 1)
    return ko, en


def _instruction(number: int) -> tuple[str, str]:
    lines = [line for line in synthesis_protocol()["instructions"].splitlines() if line.startswith(f"{number}. ")]
    assert len(lines) == 2, lines
    return lines[0], lines[1]


@pytest.mark.parametrize("phrase", V7_PHRASES)
def test_no_v7_wording_remains(phrase):
    assert phrase not in _text()


def test_instruction_numbering_is_parallel():
    numbers = [
        [int(line.split(".", 1)[0]) for line in block.splitlines() if line[:1].isdigit()]
        for block in synthesis_protocol()["instructions"].split("\n\n")
    ]
    assert len(numbers) == 2 and numbers[0] == numbers[1] == list(range(1, len(numbers[0]) + 1))


# ---------------------------------------------------------------------------
# §4 bridges and emergent edges, MUST-Q3
# ---------------------------------------------------------------------------


def test_bridge_is_defined_as_a_new_node_with_two_owners():
    ko, en = _instruction(6)
    assert "다리" in ko and "2명 이상" in ko and "호스트 다리" in ko
    assert "bridge" in en and "two or more owners" in en and "host bridge" in en
    ko, en = _rule(ViolationCode.NO_EMERGENCE)
    assert "다리 = " in ko and "2명 이상인 new 노드" in ko
    assert "A bridge is a new node" in en


@pytest.mark.parametrize("source", ["rule", "instruction"])
def test_emergent_edges_exclude_query_and_self_anchor_edges(source):
    ko, en = _rule(ViolationCode.NO_EMERGENCE) if source == "rule" else _instruction(8)
    assert "질의 노드가 아니" in ko and "query node" in en
    assert "자기 앵커 엣지" in ko and "self-anchor edge" in en
    # The self-anchor definition: new N and source S where S's cited node is already in N's provenance.
    assert "S가 인용한 노드가 이미 N의 출처" in ko and "already in N's provenance" in en
    assert "new-new 엣지는 이 조건을 만족하면 창발" in ko and "new-new edge is emergent" in en
    assert "맥락" in ko and "context" in en


def test_no_emergence_rule_counts_bridges_and_emergent_edges_together():
    ko, en = _rule(ViolationCode.NO_EMERGENCE)
    assert ko.startswith("[NO_EMERGENCE] 다리와 창발 엣지를 합쳐 1개 이상")
    assert "At least one bridge or emergent edge in total" in en


def test_host_rule_accepts_a_host_bridge_or_a_host_touching_emergent_edge():
    ko, en = _rule(ViolationCode.HOST_NOT_TOUCHED)
    assert "다리와 창발 엣지" in ko and "호스트 다리" in ko and "창발 엣지" in ko
    assert "bridge or emergent edge" in en and "host bridge" in en
    ko8, en8 = _instruction(8)
    assert "호스트 다리" in ko8 and "host bridge" in en8


def test_context_edges_are_not_rating_units():
    ko, en = _instruction(8)
    assert "평가 단위도 아니다" in ko and "not rating units" in en


# ---------------------------------------------------------------------------
# MUST-Q4, MUST-Q7: every rating unit is explained
# ---------------------------------------------------------------------------


def test_bridge_summary_length_is_stated():
    ko, en = _rule(ViolationCode.RATIONALE_MISSING)
    assert "다리 노드마다 정규화 후 40~600자 summary" in ko
    assert "창발 엣지마다 정규화 후 40~400자 rationale" in ko
    assert "summary of 40-600 characters" in en and "rationale of 40-400 characters" in en
    assert "node_id" in ko and "edge_id" in ko and "node_id" in en and "edge_id" in en
    ko10, en10 = _instruction(10)
    assert "summary를 정규화 기준 40~600자" in ko10 and "rationale을 정규화 기준 40~400자" in ko10
    assert "summary of 40-600 normalized characters" in en10 and "rationale of 40-400 normalized characters" in en10


def test_summary_upper_bound_matches_the_model():
    DeltaNode(id="n", kind=NodeKind.NEW, label="x", summary="a" * 600, constraints="b" * 600)
    with pytest.raises(pydantic.ValidationError):
        DeltaNode(id="n", kind=NodeKind.NEW, label="x", summary="a" * 601)
    with pytest.raises(pydantic.ValidationError):
        DeltaNode(id="n", kind=NodeKind.NEW, label="x", constraints="b" * 601)
    assert "600자 이하" in _instruction(13)[0] and "at most 600 characters" in _instruction(13)[1]


def test_templated_rule_covers_bridge_summaries_and_emergent_rationales():
    ko, en = _rule(ViolationCode.TEMPLATED_RATIONALE)
    assert "다리 노드의 summary와 창발 엣지의 rationale" in ko and "20% 이하" in ko
    assert "bridge summaries and emergent-edge rationales" in en and "20%" in en
    ko10, en10 = _instruction(10)
    assert "다리 summary와 창발 엣지 rationale을 함께 비교" in ko10
    assert "Bridge summaries and emergent-edge rationales are compared together" in en10


# ---------------------------------------------------------------------------
# Owner decision 2026-10-07: real-world constraint review on every bridge
# ---------------------------------------------------------------------------


def test_rules_mention_constraints_as_required_but_not_rejected():
    ko, en = _rule(ViolationCode.RATIONALE_MISSING)
    assert "constraints" in ko and "현실 제약" in ko and "거부 사유도 아니다" in ko
    assert "constraints" in en and "required by the protocol" in en and "never causes a rejection" in en


def test_constraints_instruction_covers_cost_effort_process_tradeoff_and_conditions():
    ko, en = _instruction(13)
    for needle in ("constraints", "현실 제약", "비용", "공수", "공정", "일정", "운영", "트레이드오프", "가치가 있는 조건"):
        assert needle in ko, needle
    for needle in ("constraints", "cost", "effort", "process", "schedule", "operations", "trade-off", "worth it"):
        assert needle in en, needle
    assert "L1 거부 사유는 아니지만 이 프로토콜의 요구사항" in ko
    assert "not an L1 rejection, but this protocol requires it" in en
    assert "bridges_with_constraints" in ko and "bridges_with_constraints" in en
    assert "현실에서 실행할 수 있는 다리" in ko and "practical feasibility" in en


def test_bridge_instruction_points_to_summary_and_constraints():
    ko, en = _instruction(6)
    assert "summary" in ko and "constraints" in ko
    assert "summary" in en and "constraints" in en


def test_rating_unit_and_obvious_links_score_zero_for_novelty():
    ko, en = _instruction(14)
    assert "다리 노드와 창발 엣지" in ko and "뻔한 연결은 새로움 0점" in ko
    assert "bridge nodes and emergent edges" in en and "obvious connection scores 0 for novelty" in en


# ---------------------------------------------------------------------------
# submission_example follows the v.8 shape
# ---------------------------------------------------------------------------


def _example_units() -> tuple[set[str], set[str], dict[str, int]]:
    """Bridges and emergent edges of the example by the §4 v.8 definitions (owner = subbrain placeholder),
    plus each node's undirected hop distance from the query node."""
    example = synthesis_protocol()["submission_example"]
    nodes = {n["id"]: n for n in example["nodes"]}
    refs = {nid: {(r["subbrain_id"], r["node_id"]) for r in n.get("provenance", [])} for nid, n in nodes.items()}
    owners = {nid: {sb for sb, _ in r} for nid, r in refs.items()}
    bridges = {nid for nid, n in nodes.items() if n["kind"] == "new" and len(owners[nid]) >= 2}

    def self_anchor(a: str, b: str) -> bool:
        kinds = {nodes[a]["kind"]: a, nodes[b]["kind"]: b}
        if set(kinds) != {"new", "source"}:
            return False
        return refs[kinds["source"]] <= refs[kinds["new"]]

    emergent = {
        e["id"]
        for e in example["edges"]
        if len(owners[e["source"]] | owners[e["target"]]) >= 2
        and "query" not in (nodes[e["source"]]["kind"], nodes[e["target"]]["kind"])
        and not self_anchor(e["source"], e["target"])
    }
    (query,) = [nid for nid, n in nodes.items() if n["kind"] == "query"]
    dist, frontier = {query: 0}, [query]
    while frontier:
        nxt = []
        for e in example["edges"]:
            for a, b in ((e["source"], e["target"]), (e["target"], e["source"])):
                if a in frontier and b not in dist:
                    dist[b] = dist[a] + 1
                    nxt.append(b)
        frontier = nxt
    return bridges, emergent, dist


def test_example_parses_and_has_a_bridge_and_an_emergent_edge():
    example = synthesis_protocol()["submission_example"]
    DeltabrainSubmission.model_validate(example)
    bridges, emergent, dist = _example_units()
    assert bridges == {"n1"}
    # e1 touches the query node and e2 is a self-anchor edge: context only. e3 is the emergent edge.
    assert emergent == {"e3"}
    assert set(dist) == {n["id"] for n in example["nodes"]} and max(dist.values()) <= 3


def test_example_bridge_carries_summary_and_constraints():
    (n1,) = [n for n in synthesis_protocol()["submission_example"]["nodes"] if n["id"] == "n1"]
    assert n1["summary"] and n1["constraints"]
    assert "40~600" in n1["summary"] and "40-600" in n1["summary"]
    for needle in ("비용", "공수", "공정", "cost", "effort", "trade-off"):
        assert needle in n1["constraints"], needle
