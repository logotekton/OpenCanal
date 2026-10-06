"""Unit tests for the L1 deltabrain validator (ORACLE §4, §5.1).

The canal context is built by hand: host A (user_a) plus members B (user_b, two
subbrains) and C (user_c). Fixture files are not used here; tests/oracle/ covers them.
"""

from __future__ import annotations

import copy

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
from opencanal.validator import compute_stats, parse_submission, validate_deltabrain

GENERIC = frozenset({"시너지", "혁신", "가치", "융합", "접근", "synergy", "innovation"})
JOSA = ["에서는", "으로", "에서", "의", "을", "를", "이", "가", "은", "는", "와", "과", "로"]

R1 = "단백질이 모양이 맞을 때만 결합하듯, 접합부를 비대칭 형상으로 만들면 잘못된 방향의 조립이 물리적으로 불가능해진다"
R2 = "게임에서 블록 모양이 놓일 자리를 하나로 정하듯 접합부 상세도 맞는 부재 하나만 받아들이도록 형상을 정할 수 있다"
R3 = "블록 모양 규칙과 접합부 상세를 합치면 현장 작업자가 도면 없이도 맞는 위치를 알 수 있는 키잉 방식이 나온다"


def _subbrain(subbrain_id, version, owner, nodes, edges=()):
    return SubbrainVersion(
        subbrain_id=subbrain_id,
        version=version,
        owner_id=owner,
        owner_display=owner.upper(),
        visibility=Visibility.PUBLIC,
        is_published_version=True,
        content_hash="0" * 64,
        created_at="2026-10-06T00:00:00Z",
        document=SubbrainDocument(
            title=f"{subbrain_id} title",
            domains=["test"],
            nodes=[SubbrainNode(id=nid, label=label) for nid, label in nodes],
            edges=[SubbrainEdge(source=s, target=t) for s, t in edges],
        ),
    )


def _ctx(*extra: SubbrainVersion, override_c: SubbrainVersion | None = None) -> CanalContext:
    subbrains = [
        _subbrain("sb_a", 1, "user_a",
                  [("a1", "현장 조립 오류"), ("a2", "접합부 상세"), ("a3", "공차 관리")],
                  [("a1", "a2"), ("a2", "a3")]),
        _subbrain("sb_b", 2, "user_b",
                  [("b1", "잘못 놓을 수 없는 블록 모양"), ("b2", "오조작 방지")],
                  [("b1", "b2")]),
        _subbrain("sb_b2", 1, "user_b",
                  [("x1", "레벨 디자인 튜토리얼"), ("x2", "플레이 테스트")]),
        override_c or _subbrain("sb_c", 1, "user_c",
                                [("c1", "형태 상보성"), ("c2", "오류 교정")],
                                [("c1", "c2")]),
        *extra,
    ]
    return CanalContext(
        canal_id="canal_1",
        host_subbrain_id="sb_a",
        host_version=1,
        host_owner_id="user_a",
        subbrains={(s.subbrain_id, s.version): s for s in subbrains},
    )


CTX = _ctx()


def ref(subbrain_id, version, node_id):
    return {"subbrain_id": subbrain_id, "version": version, "node_id": node_id}


A1, A2, A3 = ref("sb_a", 1, "a1"), ref("sb_a", 1, "a2"), ref("sb_a", 1, "a3")
B1, X1 = ref("sb_b", 2, "b1"), ref("sb_b2", 1, "x1")
C1, C2 = ref("sb_c", 1, "c1"), ref("sb_c", 1, "c2")


def node(node_id, kind, label, *refs):
    return {"id": node_id, "kind": kind, "label": label, "provenance": list(refs)}


def edge(edge_id, source, target, relation="requires", rationale=None, *refs):
    out = {"id": edge_id, "source": source, "target": target, "relation": relation, "provenance": list(refs)}
    if rationale is not None:
        out["rationale"] = rationale
    return out


VALID = {
    "nodes": [
        node("q", "query", "모듈러 건축의 현장 조립 오류를 줄일 아이디어"),
        node("sa1", "source", "현장 조립 오류", A1),
        node("sa2", "source", "접합부 상세", A2),
        node("sc1", "source", "형태 상보성", C1),
        node("sb1", "source", "잘못 놓을 수 없는 블록 모양", B1),
        node("n1", "new", "모양으로 강제되는 접합부 키잉", B1, A2),
    ],
    "edges": [
        edge("e0", "q", "sa1", "requires"),
        edge("e_ctx", "q", "sa2", "requires"),  # non-emergent context edge (Oracle v.3: copying an input edge would be NOT_NOVEL)
        edge("e1", "sc1", "sa1", "applies_to", R1),
        edge("e2", "sb1", "sa2", "analogous_to", R2),
        edge("e3", "n1", "sa2", "extends", R3),
    ],
}


def run(payload, ctx=CTX):
    return validate_deltabrain(payload, ctx, generic_terms=GENERIC, josa_suffixes=JOSA, josa_min_stem_length=2)


def fresh():
    return copy.deepcopy(VALID)


def codes(result):
    return [v.code for v in result.violations]


def by_code(result, code):
    return [v for v in result.violations if v.code == code]


def find(payload, collection, item_id):
    return next(item for item in payload[collection] if item["id"] == item_id)


# ---------------------------------------------------------------------------
# Valid case and stats
# ---------------------------------------------------------------------------


def test_valid_submission_is_accepted_with_stats():
    result = run(fresh())
    assert result.ok, result.violations
    assert result.violations == []
    stats = result.stats
    assert stats is not None
    assert (stats.node_count, stats.edge_count, stats.new_node_count) == (6, 5, 1)
    assert stats.emergent_edge_ids == ["e1", "e2", "e3"]
    assert stats.host_touching_emergent_edge_ids == ["e1", "e2", "e3"]
    assert stats.owners_involved == 3


def test_model_and_dict_payloads_give_the_same_result():
    from_dict = run(fresh())
    from_model = run(DeltabrainSubmission.model_validate(fresh()))
    assert from_dict == from_model


def test_compute_stats_matches_validator_stats():
    submission = DeltabrainSubmission.model_validate(fresh())
    assert compute_stats(submission, CTX) == run(fresh()).stats


def test_compute_stats_tolerates_dangling_edges():
    payload = fresh()
    payload["edges"].append(edge("e_bad", "sa1", "ghost", "requires"))
    stats = compute_stats(DeltabrainSubmission.model_validate(payload), CTX)
    assert stats.edge_count == 6
    assert "e_bad" not in stats.emergent_edge_ids


def test_new_node_citing_two_nodes_of_the_same_owner_is_allowed():
    # Q1 needs >= 2 refs, not 2 owners; emergence is decided per edge.
    payload = fresh()
    payload["nodes"].append(node("n2", "new", "튜토리얼식 블록 배치 학습", B1, X1))
    payload["edges"].append(edge("e4", "q", "n2", "requires"))
    result = run(payload)
    assert result.ok, result.violations
    assert "e4" not in result.stats.emergent_edge_ids


def test_edge_own_provenance_does_not_make_it_emergent():
    # Oracle v.3 §4: owners come from endpoint provenance only; the edge-level C1 ref is evidence.
    payload = {
        "nodes": [
            node("q", "query", "현장 조립 오류"),
            node("sa1", "source", "현장 조립 오류", A1),
            node("sa3", "source", "공차 관리", A3),
        ],
        "edges": [
            edge("e0", "q", "sa1"),
            edge("e1", "sa1", "sa3", "applies_to", R1, C1),
        ],
    }
    result = run(payload)
    assert codes(result) == [ViolationCode.NO_EMERGENCE]
    assert result.stats.emergent_edge_ids == []
    assert result.stats.host_touching_emergent_edge_ids == []


# ---------------------------------------------------------------------------
# SCHEMA_INVALID
# ---------------------------------------------------------------------------


def test_parse_submission_accepts_valid_payload():
    submission, failure = parse_submission(fresh())
    assert failure is None
    assert isinstance(submission, DeltabrainSubmission)


def test_parse_submission_reports_location_and_ids():
    payload = fresh()
    payload["nodes"][0]["kind"] = "bogus"
    payload["edges"][1]["weight"] = 3
    submission, failure = parse_submission(payload)
    assert submission is None
    assert failure is not None and not failure.ok and failure.stats is None
    assert set(codes(failure)) == {ViolationCode.SCHEMA_INVALID}
    messages = " | ".join(v.message for v in failure.violations)
    assert "nodes[0].kind" in messages
    assert "edges[1].weight" in messages
    assert {v.node_id for v in failure.violations} >= {"q"}
    assert {v.edge_id for v in failure.violations} >= {"e_ctx"}


@pytest.mark.parametrize("payload", [None, [], "nodes", {"edges": []}, {"nodes": [{"id": "q"}]}])
def test_unparseable_payloads_are_schema_invalid(payload):
    result = run(payload)
    assert not result.ok
    assert result.stats is None
    assert result.violations
    assert set(codes(result)) == {ViolationCode.SCHEMA_INVALID}


def test_graph_schema_errors_are_all_reported_and_stop_further_checks():
    payload = fresh()
    payload["nodes"].append(node("sa1", "source", "현장 조립 오류", A1))  # duplicate node id
    payload["edges"].append(edge("e1", "q", "sa2", "related_to"))  # duplicate edge id, bad relation
    payload["edges"].append(edge("e5", "sa1", "ghost", "requires"))  # dangling endpoint
    payload["edges"].append(edge("e6", "sa2", "sa2", "requires"))  # self-loop
    result = run(payload)
    assert not result.ok
    assert result.stats is None
    assert codes(result) == [ViolationCode.SCHEMA_INVALID] * 4
    assert {v.node_id for v in result.violations} == {"sa1", None}
    assert {v.edge_id for v in result.violations} == {"e1", "e5", "e6", None}


# ---------------------------------------------------------------------------
# TOO_LARGE
# ---------------------------------------------------------------------------


def test_too_many_nodes():
    payload = fresh()
    for i in range(56):
        payload["nodes"].append(node(f"s{i}", "source", "공차 관리", A3))
        payload["edges"].append(edge(f"x{i}", "q", f"s{i}"))
    result = run(payload)
    assert codes(result) == [ViolationCode.TOO_LARGE]
    assert result.stats is not None and result.stats.node_count == 62


def test_too_many_nodes_and_edges_is_one_violation():
    payload = fresh()
    for i in range(56):
        payload["nodes"].append(node(f"s{i}", "source", "공차 관리", A3))
    for i in range(120):
        payload["edges"].append(edge(f"x{i}", "q", f"s{i % 56}"))
    result = run(payload)
    assert codes(result) == [ViolationCode.TOO_LARGE]


def test_size_at_limit_is_fine():
    payload = fresh()
    for i in range(54):
        payload["nodes"].append(node(f"s{i}", "source", "공차 관리", A3))
    for i in range(115):
        payload["edges"].append(edge(f"x{i}", "q", f"s{i % 54}"))
    assert (len(payload["nodes"]), len(payload["edges"])) == (60, 120)
    assert run(payload).ok


# ---------------------------------------------------------------------------
# QUERY_NODE_COUNT / OFF_QUERY_NODE
# ---------------------------------------------------------------------------


def test_no_query_node_skips_hop_check():
    payload = fresh()
    payload["nodes"] = [n for n in payload["nodes"] if n["id"] != "q"]
    payload["edges"] = [e for e in payload["edges"] if "q" not in (e["source"], e["target"])]
    payload["nodes"].append(node("lonely", "source", "공차 관리", A3))
    result = run(payload)
    assert codes(result) == [ViolationCode.QUERY_NODE_COUNT]
    assert "0" in result.violations[0].message


def test_two_query_nodes():
    payload = fresh()
    payload["nodes"].append(node("q2", "query", "두 번째 질의"))
    payload["edges"].append(edge("eq", "q", "q2"))
    result = run(payload)
    assert codes(result) == [ViolationCode.QUERY_NODE_COUNT]


def test_query_node_refs_are_ignored():
    payload = fresh()
    payload["nodes"][0]["provenance"] = [ref("sb_d", 1, "d1"), ref("sb_c", 1, "nope"), C1]
    result = run(payload)
    assert result.ok, result.violations
    assert result.stats == run(fresh()).stats


def test_query_node_refs_do_not_create_emergence():
    payload = {
        "nodes": [node("q", "query", "현장 조립 오류", C1, B1), node("sa1", "source", "현장 조립 오류", A1)],
        "edges": [edge("e0", "q", "sa1", "applies_to", R1)],
    }
    result = run(payload)
    assert codes(result) == [ViolationCode.NO_EMERGENCE]
    assert result.stats.owners_involved == 1


def test_off_query_nodes_far_and_disconnected():
    payload = fresh()
    # sb1 sits 2 hops from q (q -> sa2 -> sb1), so n_mid is at 3 hops and n_far at 4.
    payload["nodes"].append(node("n_mid", "new", "형상 키 기반 조립 순서 검증", C2, A3))
    payload["nodes"].append(node("n_far", "new", "오류 교정 루프 기반 공차 흡수", C2, A3))
    payload["nodes"].append(node("n_iso", "new", "자기 교정 접합 순서", C2, A3))
    payload["edges"].append(edge("e4", "sb1", "n_mid", "extends", R3 + " 그리고 순서 검증을 더한다"))
    payload["edges"].append(edge("e5", "n_mid", "n_far", "extends", R1 + " 여기에 교정 루프를 붙인다"))
    result = run(payload)
    off = by_code(result, ViolationCode.OFF_QUERY_NODE)
    assert [v.node_id for v in off] == ["n_far", "n_iso"]
    assert "4" in off[0].message
    assert codes(result) == [ViolationCode.OFF_QUERY_NODE] * 2  # n_mid at exactly 3 hops is fine


# ---------------------------------------------------------------------------
# Provenance: PROVENANCE_MISSING / OUT_OF_CANAL / INVALID, SOURCE_MISMATCH
# ---------------------------------------------------------------------------


def test_source_without_provenance():
    payload = fresh()
    find(payload, "nodes", "sc1")["provenance"] = []
    result = run(payload)
    missing = by_code(result, ViolationCode.PROVENANCE_MISSING)
    assert [v.node_id for v in missing] == ["sc1"]


def test_new_node_needs_two_distinct_refs():
    payload = fresh()
    find(payload, "nodes", "n1")["provenance"] = [B1]
    payload["nodes"].append(node("n2", "new", "튜토리얼식 블록 배치 학습", B1, B1))  # same ref twice
    payload["edges"].append(edge("e4", "q", "n2"))
    result = run(payload)
    missing = by_code(result, ViolationCode.PROVENANCE_MISSING)
    assert [v.node_id for v in missing] == ["n1", "n2"]


def test_source_citing_two_nodes_is_source_mismatch():
    payload = fresh()
    find(payload, "nodes", "sa1")["provenance"] = [A1, C1]
    result = run(payload)
    mismatch = by_code(result, ViolationCode.SOURCE_MISMATCH)
    assert [v.node_id for v in mismatch] == ["sa1"]
    assert "exactly one" in mismatch[0].message


def test_refs_outside_the_canal():
    payload = fresh()
    find(payload, "nodes", "sb1")["provenance"] = [ref("sb_d", 1, "d1")]  # subbrain not in canal
    find(payload, "nodes", "n1")["provenance"] = [B1, ref("sb_a", 2, "a2")]  # unknown version
    find(payload, "edges", "e1")["provenance"] = [ref("sb_p", 1, "p1")]
    result = run(payload)
    out = by_code(result, ViolationCode.PROVENANCE_OUT_OF_CANAL)
    assert [(v.node_id, v.edge_id) for v in out] == [("sb1", None), ("n1", None), (None, "e1")]
    assert not by_code(result, ViolationCode.PROVENANCE_INVALID)


def test_ref_to_missing_node_in_canal_subbrain():
    payload = fresh()
    find(payload, "nodes", "sc1")["provenance"] = [ref("sb_c", 1, "c99")]
    find(payload, "edges", "e2")["provenance"] = [ref("sb_b", 2, "b99")]
    result = run(payload)
    invalid = by_code(result, ViolationCode.PROVENANCE_INVALID)
    assert [(v.node_id, v.edge_id) for v in invalid] == [("sc1", None), (None, "e2")]
    assert not by_code(result, ViolationCode.SOURCE_MISMATCH)


def test_source_label_must_match_cited_label():
    payload = fresh()
    find(payload, "nodes", "sb1")["label"] = "블록 모양"
    result = run(payload)
    mismatch = by_code(result, ViolationCode.SOURCE_MISMATCH)
    assert [v.node_id for v in mismatch] == ["sb1"]
    # The cited label is another user's text and must not be echoed outside untrusted_data.
    assert "잘못 놓을 수 없는" not in mismatch[0].message


def test_source_label_comparison_is_normalized():
    payload = fresh()
    find(payload, "nodes", "sa1")["label"] = "  현장-조립   오류! "
    assert run(payload).ok


# ---------------------------------------------------------------------------
# RELATION_NOT_ALLOWED
# ---------------------------------------------------------------------------


def test_relations_outside_vocabulary():
    payload = fresh()
    find(payload, "edges", "e1")["relation"] = "related_to"
    find(payload, "edges", "e2")["relation"] = " Analogous_To "
    find(payload, "edges", "e3")["relation"] = "시너지"
    result = run(payload)
    assert [v.edge_id for v in by_code(result, ViolationCode.RELATION_NOT_ALLOWED)] == ["e1", "e3"]
    assert codes(result) == [ViolationCode.RELATION_NOT_ALLOWED] * 2


# ---------------------------------------------------------------------------
# NO_EMERGENCE / HOST_NOT_TOUCHED
# ---------------------------------------------------------------------------


def test_single_owner_has_no_emergence():
    payload = {
        "nodes": [
            node("q", "query", "현장 조립 오류"),
            node("sa1", "source", "현장 조립 오류", A1),
            node("sa3", "source", "공차 관리", A3),
        ],
        "edges": [edge("e0", "q", "sa1"), edge("e1", "sa1", "sa3", "applies_to", R1)],
    }
    result = run(payload)
    assert codes(result) == [ViolationCode.NO_EMERGENCE]


def test_two_subbrains_of_one_owner_are_not_emergent():
    payload = {
        "nodes": [
            node("q", "query", "블록 조립"),
            node("sb1", "source", "잘못 놓을 수 없는 블록 모양", B1),
            node("sx1", "source", "레벨 디자인 튜토리얼", X1),
        ],
        "edges": [edge("e0", "q", "sb1"), edge("e1", "sb1", "sx1", "applies_to", R2)],
    }
    assert codes(run(payload)) == [ViolationCode.NO_EMERGENCE]


def test_emergence_that_skips_the_host():
    payload = {
        "nodes": [
            node("q", "query", "현장 조립 오류"),
            node("sb1", "source", "잘못 놓을 수 없는 블록 모양", B1),
            node("sc1", "source", "형태 상보성", C1),
        ],
        "edges": [edge("e0", "q", "sb1"), edge("e1", "sb1", "sc1", "analogous_to", R2)],
    }
    result = run(payload)
    assert codes(result) == [ViolationCode.HOST_NOT_TOUCHED]
    assert result.stats.emergent_edge_ids == ["e1"]
    assert result.stats.host_touching_emergent_edge_ids == []


# Phrasings of the v.2 definition, where refs written on the edge counted toward emergence / host-touching.
V2_EDGE_REF_PHRASES = (
    "엣지의 출처", "∪", "plus the edge", "edge's own refs", "edge's refs", "in its provenance", "effective provenance",
)


def _single_owner_payload():
    return {
        "nodes": [
            node("q", "query", "현장 조립 오류"),
            node("sa1", "source", "현장 조립 오류", A1),
            node("sa3", "source", "공차 관리", A3),
        ],
        "edges": [edge("e0", "q", "sa1"), edge("e1", "sa1", "sa3", "applies_to", R1)],
    }


def _host_skipping_payload():
    return {
        "nodes": [
            node("q", "query", "현장 조립 오류"),
            node("sb1", "source", "잘못 놓을 수 없는 블록 모양", B1),
            node("sc1", "source", "형태 상보성", C1),
        ],
        "edges": [edge("e0", "q", "sb1"), edge("e1", "sb1", "sc1", "analogous_to", R2)],
    }


@pytest.mark.parametrize(
    "payload,code",
    [(_single_owner_payload(), ViolationCode.NO_EMERGENCE), (_host_skipping_payload(), ViolationCode.HOST_NOT_TOUCHED)],
)
def test_emergence_messages_never_claim_edge_refs_count(payload, code):
    # Oracle v.3 §4: only the two end nodes' refs decide emergence and host-touching; edge refs are evidence.
    (violation,) = by_code(run(payload), code)
    ko, en = violation.message.split(" / ", 1)
    for phrase in V2_EDGE_REF_PHRASES:
        assert phrase not in violation.message, phrase
    assert "양 끝 노드" in ko and "end node" in en.lower()
    assert "엣지에 직접 적은" in ko and "on the edge itself" in en
    assert "new 노드" in ko and "new node" in en  # names an action that can actually fix it


def test_edge_refs_suggested_by_v2_wording_do_not_clear_the_violation():
    # What the old message told the synthesizer to do: cite other owners on the edge itself. Still rejected.
    no_emergence = _single_owner_payload()
    find(no_emergence, "edges", "e1")["provenance"] = [B1, C1]
    assert codes(run(no_emergence)) == [ViolationCode.NO_EMERGENCE]
    host_skipping = _host_skipping_payload()
    find(host_skipping, "edges", "e1")["provenance"] = [A1]
    assert codes(run(host_skipping)) == [ViolationCode.HOST_NOT_TOUCHED]


def test_following_the_emergence_message_clears_it():
    # "connect a new node that cites nodes of both owners (host + member)" fixes both violations.
    for payload in (_single_owner_payload(), _host_skipping_payload()):
        payload["nodes"].append(node("n_fix", "new", "모양으로 강제되는 접합부 키잉", A2, B1))
        payload["edges"].append(edge("e_fix", "n_fix", payload["edges"][0]["target"], "applies_to", R3))
        result = run(payload)
        assert result.ok, result.violations
        assert "e_fix" in result.stats.host_touching_emergent_edge_ids


def test_copied_input_edge_message_covers_non_emergent_edges():
    payload = {
        "nodes": [
            node("q", "query", "현장 조립 오류"),
            node("sa1", "source", "현장 조립 오류", A1),
            node("sa2", "source", "접합부 상세", A2),
        ],
        "edges": [edge("e0", "q", "sa1"), edge("e1", "sa2", "sa1", "applies_to", R1)],
    }
    (violation,) = by_code(run(payload), ViolationCode.NOT_NOVEL)
    ko, en = violation.message.split(" / ", 1)
    assert "창발 여부와 무관" in ko and "emergent or not" in en
    assert "방향 무관" in ko and "either direction" in en


def test_rationale_message_states_invisible_characters_count_as_spaces():
    payload = fresh()
    find(payload, "edges", "e1")["rationale"] = "짧다" + "ㅤ" * 60  # Hangul fillers are not content
    (violation,) = by_code(run(payload), ViolationCode.RATIONALE_MISSING)
    ko, en = violation.message.split(" / ", 1)
    assert "보이지 않는 문자" in ko and "invisible characters" in en


# ---------------------------------------------------------------------------
# RATIONALE_MISSING
# ---------------------------------------------------------------------------


def test_rationale_missing_short_and_long():
    payload = fresh()
    find(payload, "edges", "e1").pop("rationale")
    find(payload, "edges", "e2")["rationale"] = "모양이 맞는다"
    find(payload, "edges", "e3")["rationale"] = "가" * 401
    result = run(payload)
    missing = by_code(result, ViolationCode.RATIONALE_MISSING)
    assert [v.edge_id for v in missing] == ["e1", "e2", "e3"]
    assert codes(result) == [ViolationCode.RATIONALE_MISSING] * 3  # e0/e_ctx are not emergent


def test_rationale_length_is_measured_after_normalization():
    payload = fresh()
    find(payload, "edges", "e1")["rationale"] = "가" * 40
    find(payload, "edges", "e2")["rationale"] = "나" * 39 + "!!!!  ...  "
    find(payload, "edges", "e3")["rationale"] = "다" * 400
    result = run(payload)
    assert [v.edge_id for v in by_code(result, ViolationCode.RATIONALE_MISSING)] == ["e2"]


# ---------------------------------------------------------------------------
# NOT_NOVEL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", ["형태  상보성!", "접합부 상세", "공차-관리"])
def test_new_node_label_already_in_canal(label):
    payload = fresh()
    find(payload, "nodes", "n1")["label"] = label
    result = run(payload)
    assert [v.node_id for v in by_code(result, ViolationCode.NOT_NOVEL)] == ["n1"]


@pytest.mark.parametrize("source,target", [("sa1", "sa2"), ("sa2", "sa1")])
def test_emergent_edge_copying_an_input_edge(source, target):
    payload = {
        "nodes": [
            node("q", "query", "현장 조립 오류"),
            node("sa1", "source", "현장 조립 오류", A1),
            node("sa2", "source", "접합부 상세", A2),
        ],
        "edges": [edge("e0", "q", "sa1"), edge("e1", source, target, "applies_to", R1, C1)],
    }
    result = run(payload)
    # Oracle v.3: same-subbrain edge is not emergent, but copying an input edge is still NOT_NOVEL.
    assert [v.edge_id for v in by_code(result, ViolationCode.NOT_NOVEL)] == ["e1"]
    assert sorted(codes(result)) == sorted([ViolationCode.NO_EMERGENCE, ViolationCode.NOT_NOVEL])


def test_node_id_collision_across_subbrains_is_not_a_copy():
    # sb_c also has a node "a2"; A's edge a1-a2 says nothing about (sb_a a1)-(sb_c a2).
    ctx = _ctx(override_c=_subbrain("sb_c", 1, "user_c", [("a2", "형태 맞물림"), ("c1", "형태 상보성")]))
    payload = {
        "nodes": [
            node("q", "query", "현장 조립 오류"),
            node("sa1", "source", "현장 조립 오류", A1),
            node("sca2", "source", "형태 맞물림", ref("sb_c", 1, "a2")),
        ],
        "edges": [edge("e0", "q", "sa1"), edge("e1", "sa1", "sca2", "applies_to", R1)],
    }
    result = run(payload, ctx)
    assert result.ok, result.violations


# ---------------------------------------------------------------------------
# GENERIC_LABEL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", ["시너지 혁신", "혁신과 가치를", "Synergy & Innovation", "융합", "!!!"])
def test_generic_new_node_labels(label):
    payload = fresh()
    find(payload, "nodes", "n1")["label"] = label
    result = run(payload)
    assert [v.node_id for v in by_code(result, ViolationCode.GENERIC_LABEL)] == ["n1"]


def test_specific_label_with_one_generic_word_is_fine():
    payload = fresh()
    find(payload, "nodes", "n1")["label"] = "형태 키잉 혁신"
    assert run(payload).ok


def test_generic_rule_applies_to_new_nodes_only():
    payload = fresh()
    payload["nodes"].append(node("sg", "source", "시너지", ref("sb_x", 1, "g1")))
    payload["edges"].append(edge("e4", "q", "sg"))
    ctx = _ctx(_subbrain("sb_x", 1, "user_x", [("g1", "시너지")]))
    result = run(payload, ctx)
    assert result.ok, result.violations


# ---------------------------------------------------------------------------
# TEMPLATED_RATIONALE
# ---------------------------------------------------------------------------


def _fan(rationales):
    """q - sa1 - n_k, one emergent edge per rationale (sa1 is host, n_k cites C)."""
    nodes = [node("q", "query", "현장 조립 오류"), node("sa1", "source", "현장 조립 오류", A1)]
    edges = [edge("e0", "q", "sa1")]
    for k, text in enumerate(rationales):
        nodes.append(node(f"n{k}", "new", f"교정 기제 변형 {k}", C1, C2))
        edges.append(edge(f"e{k + 1}", "sa1", f"n{k}", "applies_to", text))
    return {"nodes": nodes, "edges": edges}


def _unique(k):
    return f"{k}번째 연결: 단백질 오류 교정처럼 조립 단계마다 형상 검사를 넣으면 현장 오류가 줄어든다 {k}"


def test_templated_rationales_over_limit():
    same = [R1, R1.upper() + "!", "  " + R1 + " ..."]
    result = run(_fan(same))
    templ = by_code(result, ViolationCode.TEMPLATED_RATIONALE)
    assert len(templ) == 1
    for edge_id in ("e1", "e2", "e3"):
        assert repr(edge_id) in templ[0].message


def test_templated_ratio_exactly_at_limit_passes():
    rationales = [_unique(k) for k in range(8)] + [R2, R2]  # 2 of 10 = 20%
    result = run(_fan(rationales))
    assert result.ok, result.violations


def test_templated_ratio_above_limit_fails():
    rationales = [_unique(k) for k in range(7)] + [R2, R2, R2]  # 3 of 10 = 30%
    result = run(_fan(rationales))
    assert codes(result) == [ViolationCode.TEMPLATED_RATIONALE]
    assert "e8" in result.violations[0].message and "e1'" not in result.violations[0].message


def _mad_libs(k):
    """One template with the edge's own endpoint labels filled in (sa1 = "현장 조립 오류", n_k = "교정 기제 변형 k")."""
    return (
        f"{_fan_label(k)}의 원리를 현장 조립 오류에 적용하면 현장 조립 오류 문제를 줄이는 데 도움이 되므로 "
        f"두 개념은 서로 밀접하게 연결된다고 볼 수 있다."
    )


def _fan_label(k):
    return f"교정 기제 변형 {k}"


def test_templated_label_swapped_template_is_the_same_sentence():
    # ORACLE v.4 MUST-Q7: endpoint labels are replaced by one placeholder before the exact comparison.
    rationales = [_mad_libs(k) for k in range(5)]
    assert len({r for r in rationales}) == 5  # all different before substitution
    result = run(_fan(rationales))
    templ = by_code(result, ViolationCode.TEMPLATED_RATIONALE)
    assert codes(result) == [ViolationCode.TEMPLATED_RATIONALE]
    for edge_id in ("e1", "e2", "e3", "e4", "e5"):
        assert repr(edge_id) in templ[0].message
    # Labels are other users' text and must not be echoed (only ids the submitter wrote).
    assert "교정 기제" not in templ[0].message and "현장 조립" not in templ[0].message


def test_templated_label_swap_respects_the_twenty_percent_limit():
    at_limit = [_unique(k) for k in range(8)] + [_mad_libs(8), _mad_libs(9)]  # 2 of 10 = 20%
    assert run(_fan(at_limit)).ok
    over = [_unique(k) for k in range(7)] + [_mad_libs(7), _mad_libs(8), _mad_libs(9)]  # 3 of 10
    result = run(_fan(over))
    assert codes(result) == [ViolationCode.TEMPLATED_RATIONALE]
    assert "e8" in result.violations[0].message and "e10" in result.violations[0].message


def test_templated_rationales_that_differ_beyond_the_labels_are_distinct():
    rationales = [
        f"{_fan_label(k)}의 원리를 현장 조립 오류에 적용하면 {tail}"
        for k, tail in enumerate([
            "조립 단계마다 형상 검사를 넣어 잘못 놓인 유닛을 바로 빼낼 수 있다.",
            "결합 에너지가 낮은 접합만 풀리게 해 틀린 위치를 고정 전에 드러낸다.",
            "운송 중 생긴 치수 오차를 키의 여유 안에서 흡수하는 방법이 보인다.",
        ])
    ]
    assert run(_fan(rationales)).ok


def test_templated_longest_endpoint_label_is_replaced_first():
    # n_k's label contains sa1's label: replacing the shorter one first would leave "방지 장치 k" behind.
    payload = _fan([f"현장 조립 오류 방지 장치 {k}는 현장 조립 오류를 설치 순간에 드러내는 장치로 쓰일 수 있다고 본다." for k in "가나다"])
    for k, suffix in enumerate("가나다"):
        find(payload, "nodes", f"n{k}")["label"] = f"현장 조립 오류 방지 장치 {suffix}"
    result = run(payload)
    assert codes(result) == [ViolationCode.TEMPLATED_RATIONALE]


def test_templated_exact_copy_still_counts_when_only_one_edge_names_its_endpoint():
    # The same text names n7's label, so n7's skeleton differs from n8/n9's; it is still the same rationale.
    shared = f"{_fan_label(7)}처럼 결합 에너지가 낮은 접합을 먼저 풀어 틀린 위치의 유닛을 고정 전에 빼내는 절차가 필요하다."
    result = run(_fan([_unique(k) for k in range(7)] + [shared] * 3))  # 3 of 10 = 30%
    assert codes(result) == [ViolationCode.TEMPLATED_RATIONALE]
    for edge_id in ("e8", "e9", "e10"):
        assert repr(edge_id) in result.violations[0].message


def test_label_skeleton_skips_empty_labels_and_uses_a_placeholder_normalization_cannot_produce():
    from opencanal.textnorm import normalize
    from opencanal.validator import _LABEL_PLACEHOLDER, _label_skeleton

    assert normalize(_LABEL_PLACEHOLDER) == ""  # never collides with normalized text or labels
    assert _label_skeleton("형태 상보성의 원리", ["", "형태 상보성"]) == f"{_LABEL_PLACEHOLDER}의 원리"
    assert _label_skeleton("abc", ["", ""]) == "abc"
    # Same placeholder for both endpoints, and a shorter label never splits a longer one.
    assert _label_skeleton("ab abc", ["ab", "abc"]) == f"{_LABEL_PLACEHOLDER} {_LABEL_PLACEHOLDER}"


def test_templated_punctuation_only_endpoint_label_does_not_break_the_check():
    payload = _fan([_unique(k) for k in range(3)])
    find(payload, "nodes", "n0")["label"] = "!!!"
    result = run(payload)
    assert codes(result) == [ViolationCode.GENERIC_LABEL]


# ---------------------------------------------------------------------------
# All violations at once, message shape
# ---------------------------------------------------------------------------


def test_all_violations_are_returned_together():
    payload = fresh()
    find(payload, "nodes", "n1")["label"] = "시너지"
    find(payload, "nodes", "sb1")["label"] = "블록"
    find(payload, "nodes", "sc1")["provenance"] = [ref("sb_d", 1, "d1")]
    find(payload, "edges", "e1")["relation"] = "related_to"
    find(payload, "edges", "e2").pop("rationale")
    payload["nodes"].append(node("n_iso", "new", "자기 교정 접합 순서", C2))
    result = run(payload)
    assert not result.ok
    assert set(codes(result)) == {
        ViolationCode.GENERIC_LABEL,
        ViolationCode.SOURCE_MISMATCH,
        ViolationCode.PROVENANCE_OUT_OF_CANAL,
        ViolationCode.PROVENANCE_MISSING,
        ViolationCode.OFF_QUERY_NODE,
        ViolationCode.RELATION_NOT_ALLOWED,
        ViolationCode.RATIONALE_MISSING,
    }
    assert result.stats is not None


def test_every_message_is_bilingual_and_actionable():
    payloads = [
        {"nodes": [{"id": "q"}]},
        {"nodes": [], "edges": [edge("e1", "a", "a")]},
        _fan([R1, R1]),
    ]
    payload = fresh()
    find(payload, "nodes", "n1")["label"] = "시너지"
    find(payload, "nodes", "sc1")["provenance"] = [ref("sb_d", 1, "d1")]
    find(payload, "edges", "e1")["relation"] = "related_to"
    payloads.append(payload)
    seen = set()
    for p in payloads:
        for v in run(p).violations:
            seen.add(v.code)
            assert " / " in v.message
            ko, en = v.message.split(" / ", 1)
            assert any("가" <= ch <= "힣" for ch in ko)
            assert any("a" <= ch.lower() <= "z" for ch in en)
    assert len(seen) >= 5


# ---------------------------------------------------------------------------
# Real Oracle config (config/generic_terms.txt, matching.json josa list)
# ---------------------------------------------------------------------------


def _run_with_real_config(payload):
    from opencanal.config import load_config

    cfg = load_config()
    return validate_deltabrain(
        payload,
        CTX,
        generic_terms=cfg.generic_terms,
        josa_suffixes=cfg.matching.josa_suffixes,
        josa_min_stem_length=cfg.matching.josa_min_stem_length,
    )


def test_valid_submission_passes_with_real_config():
    assert _run_with_real_config(fresh()).ok


@pytest.mark.parametrize("label", ["혁신적 융합 플랫폼", "시너지의 극대화", "새로운 접근법", "Innovative Synergy"])
def test_generic_labels_with_real_config(label):
    payload = fresh()
    find(payload, "nodes", "n1")["label"] = label
    result = _run_with_real_config(payload)
    assert codes(result) == [ViolationCode.GENERIC_LABEL]
