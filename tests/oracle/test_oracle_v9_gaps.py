"""Oracle v.9 (v.8 supplement) pins for the two definition gaps the v.8 adversarial review found.

- MUST-Q0 v.9: node ids and edge ids share one namespace (deltabrain_rate target_id), so they must not overlap.
- MUST-Q7 v.9: a bridge summary is compared after its own label is replaced by the placeholder, like an edge
  rationale with its endpoint labels (v.4); a template with only the bridge label swapped is the same sentence.

Written by the Oracle-owner proxy (planner) from the Oracle text, not by a Builder.
"""

from __future__ import annotations

from .conftest import load_delta, run_validator, violation_codes


def _node(g: dict, nid: str) -> dict:
    return next(n for n in g["nodes"] if n["id"] == nid)


def test_must_q0_v9_node_and_edge_ids_must_not_overlap(ctx, cfg):
    g = load_delta("good-01")
    edge = next(e for e in g["edges"] if e["id"] == "e3")
    edge["id"] = "n1"  # same id as bridge node n1
    result = run_validator(g, ctx, cfg)
    assert "SCHEMA_INVALID" in violation_codes(result), [v.code for v in result.violations]


def test_must_q7_v9_bridge_summaries_differing_only_by_own_label_are_templated(ctx, cfg):
    g = load_delta("good-01")
    template = "의 원리를 현장 조립 오류를 막는 데 그대로 옮겨 쓰는 다리이며 공장과 현장이 책임을 나눠 진다"
    for nid in ("n1", "n2"):
        node = _node(g, nid)
        node["summary"] = node["label"] + template
    result = run_validator(g, ctx, cfg)
    assert "TEMPLATED_RATIONALE" in violation_codes(result), [v.code for v in result.violations]


def test_must_q7_v9_distinct_bridge_summaries_still_pass(ctx, cfg):
    result = run_validator(load_delta("good-01"), ctx, cfg)
    assert result.ok, [v.code for v in result.violations]
