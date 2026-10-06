"""MUST-Q0..Q9 — L1 deterministic validation of deltabrains (ORACLE §4, §5.1, §6.4).

Pure tests: validator.validate_deltabrain against the fixture canal (host sb_A v1, members sb_B v1, sb_C v1).
Each golden file pins its target code. `tolerated` lists codes that may legitimately co-fire under the
Oracle text; anything else is a false positive and fails the test.
"""

from __future__ import annotations

import copy

import pytest

from opencanal.models import ALLOWED_RELATIONS, DeltabrainSubmission

from .conftest import dumps, load_delta, run_validator, violation_codes

GOOD_EMERGENT = {"e3", "e4", "e5", "e6", "e7", "e8", "e9", "e10"}
GOOD_HOST_TOUCHING = GOOD_EMERGENT - {"e9"}


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
    assert not extra, f"unexpected extra violations {extra} (target {expected})"
    return result


def _accept(payload, ctx, cfg):
    result = run_validator(payload, ctx, cfg)
    assert result.ok is True, f"expected acceptance, got {[ (v.code, v.message) for v in result.violations ]}"
    assert result.violations == []
    return result


# ---------------------------------------------------------------------------
# Mutations of good-01 (module-level so they can be reviewed and re-checked by hand)
# ---------------------------------------------------------------------------


def mut_wrong_version() -> dict:
    g = load_delta("good-01")
    _edge(g, "e9")["provenance"] = [_ref("sb_B", "b-n2", version=2)]
    return g


def mut_new_node_one_ref() -> dict:
    g = load_delta("good-01")
    _node(g, "n2")["provenance"] = [_ref("sb_C", "c-n3")]
    return g


def mut_no_query() -> dict:
    g = load_delta("good-01")
    g["nodes"] = [n for n in g["nodes"] if n["id"] != "q"]
    g["edges"] = [e for e in g["edges"] if e["id"] not in ("e1", "e2")]
    return g


def mut_four_hops() -> dict:
    g = load_delta("good-01")
    g["nodes"].append({"id": "s-c3", "kind": "source", "label": "샤페론 단백질", "provenance": [_ref("sb_C", "c-n4")]})
    g["edges"].append({"id": "e11", "source": "s-c3", "target": "s-c2", "relation": "explains"})
    return g


def mut_short_rationale() -> dict:
    g = load_delta("good-01")
    # Raw length > 40, but only ~15 characters survive normalization (punctuation stripped, spaces collapsed).
    _edge(g, "e9")["rationale"] = "형태가 맞물려 실수를 막는다." + " !?…·~,;:" * 12
    return g


def mut_long_rationale() -> dict:
    g = load_delta("good-01")
    _edge(g, "e9")["rationale"] = " ".join([_edge(g, "e9")["rationale"]] * 6)
    return g


def mut_relation(relation: str) -> dict:
    g = load_delta("good-01")
    _edge(g, "e1")["relation"] = relation
    return g


def mut_label_normalized_copy() -> dict:
    g = load_delta("good-01")
    _node(g, "n2")["label"] = "오류  교정, 기제!"  # normalizes to sb_C c-n3 "오류 교정 기제"
    _node(g, "n1")["label"] = "bim 간섭-조정"  # normalizes to sb_A a-n5 "BIM 간섭 조정"
    return g


def mut_copied_input_edge() -> dict:
    """A source-source edge that re-states sb_B's own edge b-n2 -applies_to-> b-n3.

    Oracle v.3: the edge-level C ref no longer makes it emergent; MUST-Q5 now covers every source-source edge.
    """
    g = load_delta("good-01")
    g["nodes"].append({"id": "s-b2", "kind": "source", "label": "오조작 방지 설계", "provenance": [_ref("sb_B", "b-n3")]})
    g["edges"].append(
        {
            "id": "e11",
            "source": "s-b1",
            "target": "s-b2",
            "relation": "applies_to",
            "rationale": "잘못 놓을 수 없는 모양은 오조작 방지 설계의 대표 수단이며, 세포의 형태 상보성도 같은 방식으로 잘못된 결합을 걸러 낸다.",
            "provenance": [_ref("sb_C", "c-n2")],
        }
    )
    return g


def mut_mixed_generic_label() -> dict:
    g = load_delta("good-01")
    _node(g, "n1")["label"] = "혁신적 비대칭 접합 키"
    return g


def mut_templated_at_limit() -> dict:
    """10 emergent edges, exactly one pair shares a rationale -> 2/10 = 20% (allowed: '20% 이하')."""
    g = load_delta("good-01")
    g["edges"].append(
        {
            "id": "e11",
            "source": "s-c2",
            "target": "s-a1",
            "relation": "explains",
            "rationale": "결합 에너지가 낮은 잘못된 결합이 저절로 풀리는 교정 기제는, 틀린 위치에 놓인 유닛을 고정 전에 빼내는 현장 절차의 근거가 된다.",
        }
    )
    g["edges"].append(
        {"id": "e12", "source": "s-b1", "target": "s-a1", "relation": "applies_to", "rationale": _edge(g, "e10")["rationale"]}
    )
    return g


def mut_source_two_refs() -> dict:
    g = load_delta("good-01")
    _node(g, "s-c1")["provenance"] = [_ref("sb_C", "c-n2"), _ref("sb_C", "c-n6")]
    return g


def mut_source_label_normalized() -> dict:
    g = load_delta("good-01")
    _node(g, "s-c1")["label"] = "  형태   상보성. "
    return g


def mut_all_at_once() -> dict:
    g = load_delta("bad-two-queries")
    del _edge(g, "e9")["rationale"]
    _node(g, "n2")["label"] = "혁신적 시너지 융합"
    return g


def padded(total_nodes: int, total_edges: int) -> dict:
    """good-01 grown with valid, non-emergent source nodes hung off the query node (only size changes).

    Padding edges attach to the query node (not source-source), so Oracle v.3 MUST-Q5 cannot fire on filler.
    """
    g = load_delta("good-01")
    extra = total_nodes - len(g["nodes"])
    assert extra >= 0
    for i in range(extra):
        g["nodes"].append({"id": f"x{i}", "kind": "source", "label": "모듈러 건축", "provenance": [_ref("sb_A", "a-n1")]})
        g["edges"].append({"id": f"ex{i}", "source": "q", "target": f"x{i}", "relation": "requires"})
    k = 0
    while len(g["edges"]) < total_edges:
        i = k % extra
        g["edges"].append({"id": f"ey{k}", "source": f"x{i}", "target": "q", "relation": "explains"})
        k += 1
    assert len(g["nodes"]) == total_nodes and len(g["edges"]) == total_edges
    return g


# ---------------------------------------------------------------------------
# good-01
# ---------------------------------------------------------------------------


def test_must_q_good01_accepted_with_g1_g2_and_exact_stats(ctx, cfg):
    result = _accept(load_delta("good-01"), ctx, cfg)
    stats = result.stats
    assert stats is not None
    assert stats.node_count == 9
    assert stats.edge_count == 10
    assert stats.new_node_count == 2
    assert set(stats.emergent_edge_ids) == GOOD_EMERGENT
    assert set(stats.host_touching_emergent_edge_ids) == GOOD_HOST_TOUCHING
    assert stats.owners_involved == 3


def test_must_q_compute_stats_matches_oracle_definitions(ctx):
    from opencanal.validator import compute_stats

    stats = compute_stats(DeltabrainSubmission.model_validate(load_delta("good-01")), ctx)
    assert set(stats.emergent_edge_ids) == GOOD_EMERGENT
    assert set(stats.host_touching_emergent_edge_ids) == GOOD_HOST_TOUCHING


def test_must_q_validator_is_pure_and_accepts_parsed_model(ctx, cfg):
    payload = load_delta("bad-generic")
    before = dumps(payload)
    r1 = run_validator(payload, ctx, cfg)
    r2 = run_validator(payload, ctx, cfg)
    r3 = run_validator(DeltabrainSubmission.model_validate(load_delta("bad-generic")), ctx, cfg)
    assert dumps(payload) == before, "validator must not mutate its input"
    assert r1.model_dump(mode="json") == r2.model_dump(mode="json")
    assert violation_codes(r1) == violation_codes(r3)


def test_must_q_all_violations_returned_at_once(ctx, cfg):
    _check(mut_all_at_once(), ctx, cfg, {"QUERY_NODE_COUNT", "RATIONALE_MISSING", "GENERIC_LABEL"})


# ---------------------------------------------------------------------------
# MUST-Q0 schema
# ---------------------------------------------------------------------------


def test_must_q0_duplicate_node_id_is_schema_invalid(ctx, cfg):
    _check(load_delta("bad-schema-duplicate-id"), ctx, cfg, {"SCHEMA_INVALID"})


def test_must_q0_dangling_edge_is_schema_invalid(ctx, cfg):
    _check(load_delta("bad-schema-dangling-edge"), ctx, cfg, {"SCHEMA_INVALID"})


@pytest.mark.parametrize(
    "breakage",
    ["missing_label", "unknown_kind", "unknown_top_level_field", "nodes_not_list", "edge_without_relation"],
)
def test_must_q0_unparseable_payload_is_schema_invalid(ctx, cfg, breakage):
    from opencanal.validator import parse_submission

    g = load_delta("good-01")
    if breakage == "missing_label":
        del _node(g, "s-a1")["label"]
    elif breakage == "unknown_kind":
        _node(g, "n1")["kind"] = "bridge"
    elif breakage == "unknown_top_level_field":
        g["comment"] = "extra fields are forbidden"
    elif breakage == "nodes_not_list":
        g["nodes"] = "q,s-a1"
    elif breakage == "edge_without_relation":
        del _edge(g, "e3")["relation"]
    sub, failure = parse_submission(g)
    assert sub is None
    assert failure is not None and failure.ok is False
    assert violation_codes(failure) == {"SCHEMA_INVALID"}
    _check(g, ctx, cfg, {"SCHEMA_INVALID"})


def test_must_q0_parse_submission_accepts_good01():
    from opencanal.validator import parse_submission

    sub, failure = parse_submission(load_delta("good-01"))
    assert failure is None
    assert isinstance(sub, DeltabrainSubmission) and len(sub.nodes) == 9


# ---------------------------------------------------------------------------
# MUST-Q1 provenance
# ---------------------------------------------------------------------------


def test_must_q1_missing_provenance_is_provenance_missing(ctx, cfg):
    # A source node with zero refs; a validator may also say the source cites != 1 node.
    _check(load_delta("bad-no-provenance"), ctx, cfg, {"PROVENANCE_MISSING"}, tolerated={"SOURCE_MISMATCH"})


def test_must_q1_foreign_subbrain_is_provenance_out_of_canal(ctx, cfg):
    _check(load_delta("bad-foreign-provenance"), ctx, cfg, {"PROVENANCE_OUT_OF_CANAL"})


def test_must_q1_version_not_in_canal_is_provenance_out_of_canal(ctx, cfg):
    # The canal holds sb_B *version 1*; a ref to sb_B v2 points at a version that is not in this canal.
    _check(mut_wrong_version(), ctx, cfg, {"PROVENANCE_OUT_OF_CANAL"})


def test_must_q1_unknown_node_is_provenance_invalid(ctx, cfg):
    _check(load_delta("bad-invalid-node"), ctx, cfg, {"PROVENANCE_INVALID"})


def test_must_q1_new_node_needs_two_refs(ctx, cfg):
    # Oracle: "new 노드는 참조가 2개 이상" under MUST-Q1, without naming which of the Q1 codes applies.
    result = run_validator(mut_new_node_one_ref(), ctx, cfg)
    codes = violation_codes(result)
    assert result.ok is False
    assert codes & {"PROVENANCE_MISSING", "PROVENANCE_INVALID"}, codes
    assert codes <= {"PROVENANCE_MISSING", "PROVENANCE_INVALID"}, codes


# ---------------------------------------------------------------------------
# MUST-Q2 query node and hops
# ---------------------------------------------------------------------------


def test_must_q2_two_query_nodes_is_query_node_count(ctx, cfg):
    _check(load_delta("bad-two-queries"), ctx, cfg, {"QUERY_NODE_COUNT"})


def test_must_q2_zero_query_nodes_is_query_node_count(ctx, cfg):
    # Without a query node, hop distance is undefined; OFF_QUERY_NODE may co-fire.
    _check(mut_no_query(), ctx, cfg, {"QUERY_NODE_COUNT"}, tolerated={"OFF_QUERY_NODE"})


def test_must_q2_unconnected_node_is_off_query(ctx, cfg):
    _check(load_delta("bad-off-query"), ctx, cfg, {"OFF_QUERY_NODE"})


def test_must_q2_node_four_hops_away_is_off_query(ctx, cfg):
    _check(mut_four_hops(), ctx, cfg, {"OFF_QUERY_NODE"})


# ---------------------------------------------------------------------------
# MUST-Q3 emergence
# ---------------------------------------------------------------------------


def test_must_q3_single_owner_graph_is_no_emergence(ctx, cfg):
    # With zero emergent edges, "one of them touches the host" also fails; HOST_NOT_TOUCHED may co-fire.
    _check(load_delta("bad-same-owner"), ctx, cfg, {"NO_EMERGENCE"}, tolerated={"HOST_NOT_TOUCHED"})


def test_must_q3_member_only_bridges_are_host_not_touched(ctx, cfg):
    _check(load_delta("bad-host-untouched"), ctx, cfg, {"HOST_NOT_TOUCHED"})


# ---------------------------------------------------------------------------
# MUST-Q4 relation vocabulary and rationale
# ---------------------------------------------------------------------------


def test_must_q4_q6_generic_label_and_contentless_relation(ctx, cfg):
    _check(load_delta("bad-generic"), ctx, cfg, {"GENERIC_LABEL", "RELATION_NOT_ALLOWED"})


@pytest.mark.parametrize("relation", ["관련있다", "연결된다", "시너지", "related_to"])
def test_must_q4_relation_outside_vocabulary_rejected(ctx, cfg, relation):
    _check(mut_relation(relation), ctx, cfg, {"RELATION_NOT_ALLOWED"})


@pytest.mark.parametrize("relation", ALLOWED_RELATIONS)
def test_must_q4_every_vocabulary_relation_accepted(ctx, cfg, relation):
    _accept(mut_relation(relation), ctx, cfg)


def test_must_q4_emergent_edge_without_rationale_is_rationale_missing(ctx, cfg):
    _check(load_delta("bad-no-rationale"), ctx, cfg, {"RATIONALE_MISSING"})


def test_must_q4_rationale_length_counted_after_normalization(ctx, cfg):
    _check(mut_short_rationale(), ctx, cfg, {"RATIONALE_MISSING"})


def test_must_q4_rationale_over_400_chars_rejected(ctx, cfg):
    _check(mut_long_rationale(), ctx, cfg, {"RATIONALE_MISSING"})


# ---------------------------------------------------------------------------
# MUST-Q5 novelty
# ---------------------------------------------------------------------------


def test_must_q5_new_node_reusing_input_label_is_not_novel(ctx, cfg):
    _check(load_delta("bad-copy"), ctx, cfg, {"NOT_NOVEL"})


def test_must_q5_label_comparison_is_normalized(ctx, cfg):
    _check(mut_label_normalized_copy(), ctx, cfg, {"NOT_NOVEL"})


def test_must_q5_copied_input_edge_is_not_novel(ctx, cfg):
    _check(mut_copied_input_edge(), ctx, cfg, {"NOT_NOVEL"})


# ---------------------------------------------------------------------------
# MUST-Q6 generic labels
# ---------------------------------------------------------------------------


def test_must_q6_generic_word_mixed_with_specific_words_is_allowed(ctx, cfg):
    _accept(mut_mixed_generic_label(), ctx, cfg)


# ---------------------------------------------------------------------------
# MUST-Q7 templated rationale
# ---------------------------------------------------------------------------


def test_must_q7_templated_rationale(ctx, cfg):
    _check(load_delta("bad-templated"), ctx, cfg, {"TEMPLATED_RATIONALE"})


def test_must_q7_duplicate_share_at_twenty_percent_is_allowed(ctx, cfg):
    result = _accept(mut_templated_at_limit(), ctx, cfg)
    assert len(result.stats.emergent_edge_ids) == 10


# ---------------------------------------------------------------------------
# MUST-Q8 size
# ---------------------------------------------------------------------------


def test_must_q8_61_nodes_is_too_large(ctx, cfg):
    _check(padded(61, 62), ctx, cfg, {"TOO_LARGE"})


def test_must_q8_121_edges_is_too_large(ctx, cfg):
    _check(padded(60, 121), ctx, cfg, {"TOO_LARGE"})


def test_must_q8_60_nodes_120_edges_is_within_limit(ctx, cfg):
    _accept(padded(60, 120), ctx, cfg)


# ---------------------------------------------------------------------------
# MUST-Q9 source labels
# ---------------------------------------------------------------------------


def test_must_q9_source_label_differs_from_cited_label(ctx, cfg):
    _check(load_delta("bad-source-mismatch"), ctx, cfg, {"SOURCE_MISMATCH"})


def test_must_q9_source_label_compared_after_normalization(ctx, cfg):
    _accept(mut_source_label_normalized(), ctx, cfg)


def test_must_q9_source_node_must_cite_exactly_one_node(ctx, cfg):
    # §4 "source: 출처 정확히 1개"; the Oracle does not name the code for 2 refs.
    result = run_validator(mut_source_two_refs(), ctx, cfg)
    codes = violation_codes(result)
    allowed = {"SOURCE_MISMATCH", "PROVENANCE_INVALID", "SCHEMA_INVALID"}
    assert result.ok is False
    assert codes and codes <= allowed, codes


def test_must_q_golden_files_do_not_share_state(ctx, cfg):
    """Validating a bad file must not change how good-01 is judged afterwards (pure function)."""
    run_validator(load_delta("bad-templated"), ctx, cfg)
    ctx_copy = copy.deepcopy(ctx)
    _accept(load_delta("good-01"), ctx_copy, cfg)
    _accept(load_delta("good-01"), ctx, cfg)


# ---------------------------------------------------------------------------
# Oracle v.3 (§4): emergence and host-touching come from endpoint provenance only.
# An edge-level ref is evidence, not an owner. Added by the Oracle owner proxy (planner), not the Builder.
# ---------------------------------------------------------------------------


def edge_ref_only_bridge() -> dict:
    """Two A anchors joined by an edge that cites a C node only on the edge itself."""
    return {
        "nodes": [
            {"id": "q", "kind": "query", "label": "모듈러 건축의 현장 조립 오류를 줄일 아이디어"},
            {"id": "s1", "kind": "source", "label": "현장 조립 오류", "provenance": [_ref("sb_A", "a-n2")]},
            {"id": "s2", "kind": "source", "label": "공차 관리", "provenance": [_ref("sb_A", "a-n4")]},
        ],
        "edges": [
            {"id": "e1", "source": "s1", "target": "q", "relation": "explains"},
            {
                "id": "e2",
                "source": "s2",
                "target": "s1",
                "relation": "risk_for",
                "rationale": "공차 관리가 느슨하면 현장 조립 오류가 늘어나며, 세포의 형태 상보성처럼 맞물림이 어긋나면 결합이 실패한다.",
                "provenance": [_ref("sb_C", "c-n2")],
            },
        ],
    }


def test_must_q3_v3_edge_level_ref_does_not_create_emergence(ctx, cfg):
    result = _check(edge_ref_only_bridge(), ctx, cfg, {"NO_EMERGENCE"})
    assert result.stats is not None and result.stats.emergent_edge_ids == []


def test_must_q1_v3_edge_level_ref_is_still_validated(ctx, cfg):
    g = edge_ref_only_bridge()
    _edge(g, "e2")["provenance"] = [_ref("sb_D", "d-n1")]
    _check(g, ctx, cfg, {"NO_EMERGENCE", "PROVENANCE_OUT_OF_CANAL"})


def test_must_q3_v3_good01_unchanged(ctx, cfg):
    result = _accept(load_delta("good-01"), ctx, cfg)
    assert set(result.stats.emergent_edge_ids) == GOOD_EMERGENT
    assert set(result.stats.host_touching_emergent_edge_ids) == GOOD_HOST_TOUCHING
