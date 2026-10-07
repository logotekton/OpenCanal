"""Independent reference of the Oracle v.8 structure definitions and the L1 rules that read them.

Derived from docs/oracle/ORACLE_MANIFEST.md v2026-10-07.8 (§4, MUST-Q3, MUST-Q4, MUST-Q7, HUMAN-01, §9 "(v.8)" rows)
and the contract code only (models.py, textnorm.py). Nothing here reads or imports the implementation.

§4 (v.8), as computed here:
- node owners   = owners of the node's VALID provenance refs (ref -> a subbrain version of this canal that has the node)
- edge owners   = owners(source) ∪ owners(target); refs written on the edge itself are evidence only (v.3)
- bridge        = a `new` node with >= 2 owners; host bridge = a bridge citing the host subbrain
- emergent edge = edge owners >= 2, AND neither end is the `query` node, AND not a self-anchor edge
                  (a `new` node N joined to a `source` node S whose cited node is already in N's provenance);
                  new–new edges count when the first two conditions hold
- host-touching = either end node cites the host subbrain
- rating unit   = bridge nodes ∪ emergent edges

MUST-Q3 (v.8): units >= 1 else NO_EMERGENCE; at least one host bridge or host-touching emergent edge else
HOST_NOT_TOUCHED. MUST-Q4 (v.8): emergent edge rationale 40..400 normalized chars, bridge summary 40..600 normalized
chars, else RATIONALE_MISSING naming edge_id / node_id. MUST-Q7 (v.8): share of units whose normalized description
equals another unit's > 20% -> TEMPLATED_RATIONALE; rationales have their two endpoint labels (normalized) replaced by
one placeholder first (v.4). The Oracle names that substitution for rationales only, so the tests here never put a
bridge's own label inside its summary (the verdict is the same whether or not an implementation substitutes it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from opencanal.models import CanalContext
from opencanal.textnorm import normalize

PLACEHOLDER = "\u0000"
SUMMARY_MIN, SUMMARY_MAX = 40, 600  # MUST-Q4 v.8 (bridge summary)
RATIONALE_MIN, RATIONALE_MAX = 40, 400  # MUST-Q4 (emergent edge rationale)
TEMPLATED_MAX = Fraction(1, 5)  # MUST-Q7 "20% 이하"

RefKey = tuple[str, int, str]


def ref_key(ref: dict[str, Any]) -> RefKey:
    return (ref["subbrain_id"], int(ref["version"]), ref["node_id"])


@dataclass
class V8:
    """The §4 v.8 reading of one submission (a raw dict) in one canal."""

    bridges: list[str] = field(default_factory=list)
    host_bridges: list[str] = field(default_factory=list)
    emergent: list[str] = field(default_factory=list)
    host_touching: list[str] = field(default_factory=list)
    self_anchor: list[str] = field(default_factory=list)
    query_edges: list[str] = field(default_factory=list)
    bridges_with_constraints: int = 0
    owners: dict[str, frozenset[str]] = field(default_factory=dict)
    q4_nodes: list[str] = field(default_factory=list)  # bridges whose summary is outside 40..600
    q4_edges: list[str] = field(default_factory=list)  # emergent edges whose rationale is outside 40..400
    templated_share: Fraction = Fraction(0)

    @property
    def units(self) -> list[str]:
        return [*self.bridges, *self.emergent]

    def q3_codes(self) -> set[str]:
        if not self.units:
            return {"NO_EMERGENCE"}
        if not self.host_bridges and not self.host_touching:
            return {"HOST_NOT_TOUCHED"}
        return set()

    def codes(self) -> set[str]:
        """Codes the v.8 definitions alone produce (MUST-Q3, Q4 length, Q7). Other rules are not modelled."""
        out = self.q3_codes()
        if self.q4_nodes or self.q4_edges:
            out.add("RATIONALE_MISSING")
        if self.templated_share > TEMPLATED_MAX:
            out.add("TEMPLATED_RATIONALE")
        return out


def _valid(ref: dict[str, Any], ctx: CanalContext) -> bool:
    sv = ctx.subbrains.get((ref["subbrain_id"], int(ref["version"])))
    return sv is not None and any(n.id == ref["node_id"] for n in sv.document.nodes)


def _norm_len(text: Any) -> int:
    return len(normalize(text)) if isinstance(text, str) else 0


def rationale_key(rationale: str, labels: tuple[str, str]) -> str:
    """MUST-Q7 v.4: normalized rationale with both endpoint labels (normalized) replaced by one placeholder."""
    text = normalize(rationale)
    for label in sorted({normalize(x) for x in labels if normalize(x)}, key=len, reverse=True):
        text = text.replace(label, PLACEHOLDER)
    return text


def analyse(sub: dict[str, Any], ctx: CanalContext) -> V8:
    nodes = {n["id"]: n for n in sub["nodes"]}
    host = ctx.host_subbrain_id
    out = V8()
    cites_host: dict[str, bool] = {}
    keys: dict[str, set[RefKey]] = {}
    for nid, n in nodes.items():
        valid = [r for r in n.get("provenance", []) or [] if _valid(r, ctx)]
        out.owners[nid] = frozenset(ctx.subbrains[(r["subbrain_id"], int(r["version"]))].owner_id for r in valid)
        cites_host[nid] = any(r["subbrain_id"] == host for r in valid)
        keys[nid] = {ref_key(r) for r in n.get("provenance", []) or []}
        if n["kind"] == "new" and len(out.owners[nid]) >= 2:
            out.bridges.append(nid)
            if cites_host[nid]:
                out.host_bridges.append(nid)
            if isinstance(n.get("constraints"), str) and n["constraints"].strip():
                out.bridges_with_constraints += 1
            if not SUMMARY_MIN <= _norm_len(n.get("summary")) <= SUMMARY_MAX:
                out.q4_nodes.append(nid)

    descriptions: list[str] = [normalize(nodes[b].get("summary")) for b in out.bridges]
    for e in sub["edges"]:
        s, t = nodes[e["source"]], nodes[e["target"]]
        kinds = {s["kind"], t["kind"]}
        if "query" in kinds:
            out.query_edges.append(e["id"])
            continue
        if kinds == {"new", "source"}:
            new, src = (s, t) if s["kind"] == "new" else (t, s)
            if keys[src["id"]] & keys[new["id"]]:
                out.self_anchor.append(e["id"])
                continue
        if len(out.owners[s["id"]] | out.owners[t["id"]]) < 2:
            continue
        out.emergent.append(e["id"])
        if cites_host[s["id"]] or cites_host[t["id"]]:
            out.host_touching.append(e["id"])
        if not RATIONALE_MIN <= _norm_len(e.get("rationale")) <= RATIONALE_MAX:
            out.q4_edges.append(e["id"])
        descriptions.append(rationale_key(e.get("rationale") or "", (s["label"], t["label"])))

    if descriptions:
        dup = sum(1 for i, d in enumerate(descriptions) if any(d == o for j, o in enumerate(descriptions) if j != i))
        out.templated_share = Fraction(dup, len(descriptions))
    return out


def quality(labels: dict[str, tuple[int, int, int]]) -> Fraction:
    """HUMAN-01 (v.8): share of rated units whose novelty, validity and usefulness are all 1."""
    assert labels, "quality of an unrated deltabrain is undefined"
    return Fraction(sum(1 for v in labels.values() if v == (1, 1, 1)), len(labels))
