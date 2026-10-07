"""Oracle v.4 pins for the three sabotages the fix round's integrator found still unpinned (CHANGE-003 §6).

- T06 NEVER-06: the MCP `initialize` result (server instructions) must not name a hidden tool.
- T25 NEVER-09: a VALIDATION_FAILED envelope keeps other users' strings inside untrusted_data.
- T81 MUST-Q7: the templated share is computed over EMERGENT edges only; rationales on
  non-emergent edges must not dilute it. (Oracle v.8: over rating units = bridge summaries + emergent edge
  rationales; query and self-anchor edges are not units and still must not dilute it.)

Written from the Oracle text by the Oracle-owner proxy (planner), not by a Builder.
"""

from __future__ import annotations

import asyncio
import json

from ._v4 import all_text, foreign_hits
from .conftest import World, load_brain, load_delta, run_validator, violation_codes
from .test_oracle_mcp_http import CLIENT_TIMEOUT, _url, mcp_server  # noqa: F401  (fixture re-export)

HIDDEN_FROM_FREE = ("match_explain", "deltabrain_export", "canal_synthesize")


def _initialize_result(url: str):
    from mcp import ClientSession

    try:
        from mcp.client.streamable_http import streamable_http_client as _client
    except ImportError:  # older SDK name
        from mcp.client.streamable_http import streamablehttp_client as _client

    async def go():
        async with _client(url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                return await session.initialize()

    return asyncio.run(asyncio.wait_for(go(), CLIENT_TIMEOUT))


def test_never_06_v4_initialize_result_names_no_hidden_tool(mcp_server):  # noqa: F811
    init = _initialize_result(_url(mcp_server, mcp_server["free"]))
    text = json.dumps(init.model_dump(mode="json"), ensure_ascii=False)
    for name in HIDDEN_FROM_FREE:
        assert name not in text, f"initialize result names hidden tool {name!r}"


def test_never_09_v4_validation_failed_keeps_foreign_strings_in_untrusted_data(tmp_path):
    world = World(tmp_path).seed()
    canal_id = world.open_canal()["canal_id"]
    bad = world.good01()
    # Trip several rules at once, including ones that point at member (B, C) nodes.
    for node in bad["nodes"]:
        if node["kind"] == "source" and node["provenance"][0]["subbrain_id"] == world.sid("C"):
            node["label"] = node["label"] + " 변형"  # SOURCE_MISMATCH on C's anchor
        if node["kind"] == "new":
            node["label"] = "시너지 혁신"  # GENERIC_LABEL
    bad["edges"][-1]["relation"] = "related_to"  # RELATION_NOT_ALLOWED
    env = world.submit(canal_id, bad)
    assert env["ok"] is False and env["error"]["code"] == "VALIDATION_FAILED", env
    assert len(env["error"]["violations"]) >= 2, env

    own = set(all_text(bad))  # the host's own submitted strings, echoed back verbatim, are not foreign
    foreign_long: set[str] = set()
    for fid in ("B", "C"):
        brain = load_brain(fid)
        doc = brain["document"]
        foreign_long.update([brain["owner"]["display_name"], doc["title"]])
        foreign_long.update(n["label"] for n in doc["nodes"])
        foreign_long.update(n["summary"] for n in doc["nodes"] if n.get("summary"))
        foreign_long.update(e["summary"] for e in doc.get("edges", []) if e.get("summary"))
    hits = foreign_hits(env, long_needles=foreign_long, exact_needles=(), own=own)
    assert not hits, f"other users' strings outside untrusted_data: {hits}"


def test_must_q7_v4_templated_share_counts_emergent_edges_only(ctx, cfg):
    g = load_delta("good-01")
    edges = {e["id"]: e for e in g["edges"]}
    # ORACLE v.8 §4: units = bridges n1, n2 + emergent e3, e4, e9, e10. e1/e2 are query edges, e5-e8 self-anchor
    # edges (was v.7: emergent e3-e10, non-emergent e1/e2 only).
    emergent = ["e3", "e4", "e9", "e10"]
    non_emergent = [eid for eid in edges if eid not in emergent]
    assert set(non_emergent) == {"e1", "e2", "e5", "e6", "e7", "e8"}, "query + self-anchor edges"
    shared = "같은 틀 문장을 두 창발 엣지에 그대로 붙였다. 결합 방식이 다른데도 이유를 구분하지 않아 무엇이 새로운지 알 수 없다."
    edges["e3"]["rationale"] = shared
    edges["e4"]["rationale"] = shared  # 2 of 6 units = 33% > 20% (v.7: 2 of 8 emergent) -> TEMPLATED_RATIONALE
    for i, eid in enumerate(non_emergent):  # distinct rationales on non-unit edges must not dilute it (2/12 would be ok)
        edges[eid]["rationale"] = f"질의와 앵커를 잇는 맥락 엣지 {i}번이며 서로 다른 설명을 달아 비율을 낮추려는 시도다. 고유 번호 {i * 7 + 3}."
    result = run_validator(g, ctx, cfg)
    assert "TEMPLATED_RATIONALE" in violation_codes(result), [v.code for v in result.violations]
