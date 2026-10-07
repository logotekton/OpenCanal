"""L1 deterministic validation of a deltabrain submission (ORACLE §4, §5.1, v.8).

Owner: Builder V. Pure functions: no DB, no I/O besides the passed config.

Rating units (v.8 §4) are bridge nodes (new nodes whose provenance owners number >= 2) and emergent
edges (owners >= 2, not touching the query node, not a self-anchor edge). Q3, Q4 and Q7 work on them.

Violation messages are read by the synthesizing LLM, so each one says what to fix.
They never quote text from canal subbrains (labels, summaries): only ids and refs the
submitter wrote themselves. Other users' content must stay under `untrusted_data`.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from pydantic import ValidationError

from .models import (
    ALLOWED_RELATIONS,
    MAX_DELTA_EDGES,
    MAX_DELTA_NODES,
    MAX_QUERY_HOPS,
    NEW_NODE_MIN_REFS,
    RATIONALE_MAX_CHARS,
    RATIONALE_MIN_CHARS,
    TEMPLATED_RATIONALE_MAX_RATIO,
    CanalContext,
    DeltabrainStats,
    DeltabrainSubmission,
    DeltaEdge,
    DeltaNode,
    NodeKind,
    ProvRef,
    ValidationResult,
    Violation,
    ViolationCode,
)
from .textnorm import normalize, tokenize

_SubbrainKey = tuple[str, int]
_RefKey = tuple[str, int, str]

# ORACLE v.8 MUST-Q4: a bridge node's summary, normalized. models.py has no constant for it (DeltaNode.summary
# caps the raw text at 600, but NFKC can lengthen it, so the normalized upper bound is still checked here).
BRIDGE_SUMMARY_MIN_CHARS = 40
BRIDGE_SUMMARY_MAX_CHARS = 600

# Exact decimal value of the Oracle's 20%, so the ratio test is rational arithmetic, not float rounding.
_TEMPLATED_MAX = Fraction(repr(TEMPLATED_RATIONALE_MAX_RATIO))

_MAX_ECHO_CHARS = 80
_MAX_LISTED_IDS = 30


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _q(value: Any) -> str:
    """Quote a submitter-written id for a message, truncated so messages stay short."""
    text = str(value)
    if len(text) > _MAX_ECHO_CHARS:
        text = text[:_MAX_ECHO_CHARS] + "…"
    return repr(text)


def _ref_str(ref: ProvRef) -> str:
    return f"({_q(ref.subbrain_id)}, v{ref.version}, {_q(ref.node_id)})"


def _id_list(ids: Sequence[str]) -> str:
    shown = ", ".join(_q(i) for i in ids[:_MAX_LISTED_IDS])
    rest = len(ids) - _MAX_LISTED_IDS
    return f"{shown} (+{rest})" if rest > 0 else shown


def _ref_key(ref: ProvRef) -> _RefKey:
    return (ref.subbrain_id, ref.version, ref.node_id)


def _distinct(refs: Iterable[ProvRef]) -> list[ProvRef]:
    """Refs without exact repeats: citing the same node twice is still one source."""
    seen: set[_RefKey] = set()
    out: list[ProvRef] = []
    for ref in refs:
        key = _ref_key(ref)
        if key not in seen:
            seen.add(key)
            out.append(ref)
    return out


def _v(code: ViolationCode, message: str, *, node_id: str | None = None, edge_id: str | None = None) -> Violation:
    return Violation(code=code, message=message, node_id=node_id, edge_id=edge_id)


# ---------------------------------------------------------------------------
# Canal index (built once per call from the server-side CanalContext)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CanalIndex:
    host: _SubbrainKey
    owners: dict[_SubbrainKey, str]
    labels: dict[_SubbrainKey, dict[str, str]]  # subbrain version -> node_id -> normalized label
    edge_pairs: dict[_SubbrainKey, frozenset[frozenset[str]]]  # undirected input edges
    all_labels: frozenset[str]  # normalized label of every node in every canal subbrain

    def key(self, ref: ProvRef) -> _SubbrainKey:
        return (ref.subbrain_id, ref.version)

    def in_canal(self, ref: ProvRef) -> bool:
        return self.key(ref) in self.owners

    def is_valid(self, ref: ProvRef) -> bool:
        nodes = self.labels.get(self.key(ref))
        return nodes is not None and ref.node_id in nodes

    def owner(self, ref: ProvRef) -> str:
        return self.owners[self.key(ref)]


def _index(ctx: CanalContext) -> _CanalIndex:
    owners: dict[_SubbrainKey, str] = {}
    labels: dict[_SubbrainKey, dict[str, str]] = {}
    edge_pairs: dict[_SubbrainKey, frozenset[frozenset[str]]] = {}
    all_labels: set[str] = set()
    for (subbrain_id, version), sv in ctx.subbrains.items():
        key = (subbrain_id, version)
        owners[key] = sv.owner_id
        node_labels = {node.id: normalize(node.label) for node in sv.document.nodes}
        labels[key] = node_labels
        all_labels.update(node_labels.values())
        edge_pairs[key] = frozenset(frozenset((edge.source, edge.target)) for edge in sv.document.edges)
    return _CanalIndex(
        host=(ctx.host_subbrain_id, ctx.host_version),
        owners=owners,
        labels=labels,
        edge_pairs=edge_pairs,
        all_labels=frozenset(all_labels),
    )


# ---------------------------------------------------------------------------
# Bridges and emergent edges (ORACLE v.8 §4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _NodeInfo:
    node: DeltaNode
    owners: frozenset[str]
    cites_host: bool

    @property
    def bridge(self) -> bool:
        """v.8 §4: a new node whose owner set (owners of its valid refs) has 2 or more owners."""
        return self.node.kind == NodeKind.NEW and len(self.owners) >= 2

    @property
    def host_bridge(self) -> bool:
        return self.bridge and self.cites_host


@dataclass(frozen=True)
class _EdgeInfo:
    edge: DeltaEdge
    owners: frozenset[str]
    host_touching: bool
    emergent: bool


@dataclass(frozen=True)
class _Analysis:
    nodes: list[_NodeInfo]  # submission order
    edges: list[_EdgeInfo]  # submission order

    @property
    def bridges(self) -> list[_NodeInfo]:
        return [info for info in self.nodes if info.bridge]

    @property
    def emergent(self) -> list[_EdgeInfo]:
        return [info for info in self.edges if info.emergent]


def _node_valid_refs(node: DeltaNode, idx: _CanalIndex) -> list[ProvRef]:
    if node.kind == NodeKind.QUERY:  # exempt from provenance rules; its refs are ignored
        return []
    return [ref for ref in _distinct(node.provenance) if idx.is_valid(ref)]


def _is_self_anchor(
    source: str, target: str, kinds: dict[str, NodeKind], ref_keys: dict[str, frozenset[_RefKey]]
) -> bool:
    """v.8 §4: a new node N linked (either direction) to a source node S whose cited node N already cites.

    Refs are compared as (subbrain_id, version, node_id), because node ids are unique only within one version.
    Only valid refs count, as everywhere in §4: a ref that does not resolve is ignored.
    """
    for new_id, source_id in ((source, target), (target, source)):
        if kinds.get(new_id) == NodeKind.NEW and kinds.get(source_id) == NodeKind.SOURCE:
            if ref_keys.get(source_id, frozenset()) & ref_keys.get(new_id, frozenset()):
                return True
    return False


def _analyze(submission: DeltabrainSubmission, idx: _CanalIndex) -> _Analysis:
    """Bridges and emergent edges (ORACLE v.8 §4). Tolerates dangling edges and duplicate ids (last node wins)."""
    nodes: list[_NodeInfo] = []
    node_refs: dict[str, list[ProvRef]] = {}
    for node in submission.nodes:
        refs = _node_valid_refs(node, idx)
        node_refs[node.id] = refs
        nodes.append(_NodeInfo(
            node=node,
            owners=frozenset(idx.owner(ref) for ref in refs),
            cites_host=any(idx.key(ref) == idx.host for ref in refs),
        ))
    ref_keys = {node_id: frozenset(_ref_key(ref) for ref in refs) for node_id, refs in node_refs.items()}
    kinds = {node.id: node.kind for node in submission.nodes}
    edges: list[_EdgeInfo] = []
    for edge in submission.edges:
        # Oracle v.3 §4: only endpoint provenance decides owners; edge-level refs are evidence (checked by Q1).
        refs = [*node_refs.get(edge.source, ()), *node_refs.get(edge.target, ())]
        owners = frozenset(idx.owner(ref) for ref in refs)
        touches_query = NodeKind.QUERY in (kinds.get(edge.source), kinds.get(edge.target))
        edges.append(
            _EdgeInfo(
                edge=edge,
                owners=owners,
                host_touching=any(idx.key(ref) == idx.host for ref in refs),
                emergent=(
                    len(owners) >= 2
                    and not touches_query
                    and not _is_self_anchor(edge.source, edge.target, kinds, ref_keys)
                ),
            )
        )
    return _Analysis(nodes=nodes, edges=edges)


def _stats(submission: DeltabrainSubmission, idx: _CanalIndex, analysis: _Analysis) -> DeltabrainStats:
    owners: set[str] = set()
    for info in analysis.nodes:
        owners.update(info.owners)
    for edge in submission.edges:
        owners.update(idx.owner(ref) for ref in edge.provenance if idx.is_valid(ref))
    bridges = analysis.bridges
    emergent = analysis.emergent
    return DeltabrainStats(
        node_count=len(submission.nodes),
        edge_count=len(submission.edges),
        new_node_count=sum(1 for node in submission.nodes if node.kind == NodeKind.NEW),
        emergent_edge_ids=[info.edge.id for info in emergent],
        host_touching_emergent_edge_ids=[info.edge.id for info in emergent if info.host_touching],
        owners_involved=len(owners),
        bridge_node_ids=[info.node.id for info in bridges],
        host_bridge_node_ids=[info.node.id for info in bridges if info.host_bridge],
        # Reported, never enforced (owner decision 2026-10-07). Whitespace, punctuation or invisible filler is not
        # a constraint, so the same normalization as every other text rule decides "filled".
        bridges_with_constraints=sum(1 for info in bridges if normalize(info.node.constraints)),
    )


# ---------------------------------------------------------------------------
# Checks — each returns its violations in submission order
# ---------------------------------------------------------------------------


def _check_graph_schema(sub: DeltabrainSubmission) -> list[Violation]:
    """MUST-Q0 beyond pydantic: unique ids, edge endpoints exist, no self-loops."""
    out: list[Violation] = []
    node_counts = Counter(node.id for node in sub.nodes)
    for node_id, count in node_counts.items():
        if count > 1:
            out.append(_v(
                ViolationCode.SCHEMA_INVALID,
                f"노드 ID {_q(node_id)}가 {count}번 쓰였습니다. 노드마다 고유한 ID를 쓰세요. "
                f"/ Node id {_q(node_id)} is used {count} times; give every node a unique id.",
                node_id=node_id,
            ))
    edge_counts = Counter(edge.id for edge in sub.edges)
    for edge_id, count in edge_counts.items():
        if count > 1:
            out.append(_v(
                ViolationCode.SCHEMA_INVALID,
                f"엣지 ID {_q(edge_id)}가 {count}번 쓰였습니다. 엣지마다 고유한 ID를 쓰세요. "
                f"/ Edge id {_q(edge_id)} is used {count} times; give every edge a unique id.",
                edge_id=edge_id,
            ))
    for shared_id in sorted(set(node_counts) & set(edge_counts)):
        # v.9 MUST-Q0: rating targets (bridge nodes, emergent edges) share one id namespace.
        out.append(_v(
            ViolationCode.SCHEMA_INVALID,
            f"ID {_q(shared_id)}가 노드와 엣지에 함께 쓰였습니다. 노드와 엣지 ID는 서로 겹치지 않게 쓰세요. "
            f"/ Id {_q(shared_id)} names both a node and an edge; node and edge ids must not overlap.",
            node_id=shared_id,
        ))
    for edge in sub.edges:
        for end, node_id in (("source", edge.source), ("target", edge.target)):
            if node_id not in node_counts:
                out.append(_v(
                    ViolationCode.SCHEMA_INVALID,
                    f"엣지 {_q(edge.id)}의 {end} {_q(node_id)}가 노드 목록에 없습니다. 있는 노드 ID를 쓰거나 노드를 추가하세요. "
                    f"/ Edge {_q(edge.id)} {end} {_q(node_id)} is not a node id; point it at an existing node.",
                    edge_id=edge.id,
                ))
        if edge.source == edge.target:
            out.append(_v(
                ViolationCode.SCHEMA_INVALID,
                f"엣지 {_q(edge.id)}가 노드 {_q(edge.source)} 자신을 잇습니다. 서로 다른 두 노드를 이으세요. "
                f"/ Edge {_q(edge.id)} is a self-loop on {_q(edge.source)}; connect two different nodes.",
                edge_id=edge.id,
            ))
    return out


def _check_size(sub: DeltabrainSubmission) -> list[Violation]:
    """MUST-Q8."""
    n, m = len(sub.nodes), len(sub.edges)
    if n <= MAX_DELTA_NODES and m <= MAX_DELTA_EDGES:
        return []
    return [_v(
        ViolationCode.TOO_LARGE,
        f"델타브레인이 너무 큽니다: 노드 {n}개(최대 {MAX_DELTA_NODES}), 엣지 {m}개(최대 {MAX_DELTA_EDGES}). "
        f"질의에 가장 도움이 되는 노드와 엣지만 남기세요. "
        f"/ Too large: {n} nodes (max {MAX_DELTA_NODES}), {m} edges (max {MAX_DELTA_EDGES}); "
        f"keep only what serves the query.",
    )]


def _check_query_count(sub: DeltabrainSubmission) -> list[Violation]:
    """MUST-Q2, first half."""
    count = sum(1 for node in sub.nodes if node.kind == NodeKind.QUERY)
    if count == 1:
        return []
    return [_v(
        ViolationCode.QUERY_NODE_COUNT,
        f"query 노드가 {count}개입니다. 질의를 나타내는 query 노드를 정확히 1개 두세요. "
        f"/ Found {count} query nodes; exactly one query node is required.",
    )]


def _check_ref(ref: ProvRef, idx: _CanalIndex, where_ko: str, where_en: str, **ids: str) -> Violation | None:
    if not idx.in_canal(ref):
        return _v(
            ViolationCode.PROVENANCE_OUT_OF_CANAL,
            f"{where_ko}의 출처 {_ref_str(ref)}는 이번 커널에 들어간 서브브레인 버전이 아닙니다. "
            f"canal_get에 나온 subbrain_id와 version만 인용하세요. "
            f"/ {where_en} cites {_ref_str(ref)}, which is not a subbrain version in this canal; "
            f"cite only the canal's inputs (subbrain_id and version from canal_get).",
            **ids,
        )
    if not idx.is_valid(ref):
        return _v(
            ViolationCode.PROVENANCE_INVALID,
            f"{where_ko}의 출처 {_ref_str(ref)}가 가리키는 노드가 그 서브브레인 버전에 없습니다. 실제 node_id를 쓰세요. "
            f"/ {where_en} cites {_ref_str(ref)}, but that node does not exist in that subbrain version; "
            f"use a real node_id.",
            **ids,
        )
    return None


def _check_provenance(sub: DeltabrainSubmission, idx: _CanalIndex) -> list[Violation]:
    """MUST-Q1 (+ the source-node part of MUST-Q9: exactly one ref)."""
    out: list[Violation] = []
    for node in sub.nodes:
        if node.kind == NodeKind.QUERY:
            continue
        refs = _distinct(node.provenance)
        if node.kind == NodeKind.SOURCE:
            if not refs:
                out.append(_v(
                    ViolationCode.PROVENANCE_MISSING,
                    f"source 노드 {_q(node.id)}에 출처가 없습니다. 가져온 서브브레인 노드 1개를 provenance에 적으세요. "
                    f"/ Source node {_q(node.id)} has no provenance; cite the one canal subbrain node it anchors.",
                    node_id=node.id,
                ))
            elif len(refs) > 1:
                out.append(_v(
                    ViolationCode.SOURCE_MISMATCH,
                    f"source 노드 {_q(node.id)}가 노드 {len(refs)}개를 인용합니다. source는 노드 1개만 인용해야 합니다. "
                    f"여러 노드를 합친 개념이면 kind를 new로 바꾸세요. "
                    f"/ Source node {_q(node.id)} cites {len(refs)} nodes; a source must cite exactly one node "
                    f"(use kind \"new\" for a concept combining several).",
                    node_id=node.id,
                ))
        elif len(refs) < NEW_NODE_MIN_REFS:
            out.append(_v(
                ViolationCode.PROVENANCE_MISSING,
                f"new 노드 {_q(node.id)}의 출처가 {len(refs)}개입니다. 이 노드가 나온 서브브레인 노드를 "
                f"{NEW_NODE_MIN_REFS}개 이상 provenance에 적으세요. "
                f"/ New node {_q(node.id)} has {len(refs)} distinct provenance ref(s); "
                f"cite at least {NEW_NODE_MIN_REFS} canal subbrain nodes it was derived from.",
                node_id=node.id,
            ))
        for ref in refs:
            bad = _check_ref(ref, idx, f"노드 {_q(node.id)}", f"Node {_q(node.id)}", node_id=node.id)
            if bad:
                out.append(bad)
    for edge in sub.edges:
        for ref in _distinct(edge.provenance):
            bad = _check_ref(ref, idx, f"엣지 {_q(edge.id)}", f"Edge {_q(edge.id)}", edge_id=edge.id)
            if bad:
                out.append(bad)
    return out


def _check_source_labels(sub: DeltabrainSubmission, idx: _CanalIndex) -> list[Violation]:
    """MUST-Q9: a source node's label equals (normalized) the label of the node it cites."""
    out: list[Violation] = []
    for node in sub.nodes:
        if node.kind != NodeKind.SOURCE:
            continue
        refs = _distinct(node.provenance)
        if len(refs) != 1 or not idx.is_valid(refs[0]):
            continue  # already reported as PROVENANCE_* / SOURCE_MISMATCH(count)
        ref = refs[0]
        if normalize(node.label) != idx.labels[idx.key(ref)][ref.node_id]:
            # The cited label is another user's text: do not quote it here.
            out.append(_v(
                ViolationCode.SOURCE_MISMATCH,
                f"source 노드 {_q(node.id)}의 라벨이 인용한 노드 {_ref_str(ref)}의 라벨과 다릅니다. "
                f"인용한 노드의 라벨을 그대로 쓰세요. 바꿔 쓴 개념이면 kind를 new로 하세요. "
                f"/ Source node {_q(node.id)} label differs from the label of {_ref_str(ref)}; "
                f"copy the cited label exactly (use kind \"new\" for a reworded concept).",
                node_id=node.id,
            ))
    return out


def _check_hops(sub: DeltabrainSubmission) -> list[Violation]:
    """MUST-Q2, second half: every node within MAX_QUERY_HOPS undirected hops of the query node."""
    query_ids = [node.id for node in sub.nodes if node.kind == NodeKind.QUERY]
    if len(query_ids) != 1:
        return []  # QUERY_NODE_COUNT already reported; distance is undefined
    adjacency: dict[str, set[str]] = {node.id: set() for node in sub.nodes}
    for edge in sub.edges:
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)
    dist = {query_ids[0]: 0}
    queue = deque(query_ids)
    while queue:
        current = queue.popleft()
        for nxt in adjacency[current]:
            if nxt not in dist:
                dist[nxt] = dist[current] + 1
                queue.append(nxt)
    out: list[Violation] = []
    for node in sub.nodes:
        d = dist.get(node.id)
        if d is None:
            out.append(_v(
                ViolationCode.OFF_QUERY_NODE,
                f"노드 {_q(node.id)}가 query 노드와 이어져 있지 않습니다. 질의에서 {MAX_QUERY_HOPS}홉 안에 오도록 "
                f"엣지로 잇거나, 질의와 무관하면 빼세요. "
                f"/ Node {_q(node.id)} is not connected to the query node; link it within {MAX_QUERY_HOPS} hops "
                f"or remove it if it does not serve the query.",
                node_id=node.id,
            ))
        elif d > MAX_QUERY_HOPS:
            out.append(_v(
                ViolationCode.OFF_QUERY_NODE,
                f"노드 {_q(node.id)}가 query 노드에서 {d}홉 떨어져 있습니다(최대 {MAX_QUERY_HOPS}홉). "
                f"질의에 더 가깝게 잇거나 빼세요. "
                f"/ Node {_q(node.id)} is {d} hops from the query node (max {MAX_QUERY_HOPS}); "
                f"link it closer to the query or remove it.",
                node_id=node.id,
            ))
    return out


def _check_relations(sub: DeltabrainSubmission) -> list[Violation]:
    """MUST-Q4, controlled vocabulary (ORACLE §5.2)."""
    allowed = ", ".join(ALLOWED_RELATIONS)
    return [
        _v(
            ViolationCode.RELATION_NOT_ALLOWED,
            f"엣지 {_q(edge.id)}의 관계 {_q(edge.relation)}는 통제 어휘에 없습니다. 다음 중 하나를 쓰세요: {allowed}. "
            f"/ Edge {_q(edge.id)} relation {_q(edge.relation)} is not allowed; use one of: {allowed}.",
            edge_id=edge.id,
        )
        for edge in sub.edges
        if edge.relation.strip().lower() not in ALLOWED_RELATIONS
    ]


_SUMMARY_BOUNDS_KO = f"정규화 기준 {BRIDGE_SUMMARY_MIN_CHARS}~{BRIDGE_SUMMARY_MAX_CHARS}자"
_SUMMARY_BOUNDS_EN = f"{BRIDGE_SUMMARY_MIN_CHARS}-{BRIDGE_SUMMARY_MAX_CHARS} normalized chars"
_RATIONALE_BOUNDS_KO = f"정규화 기준 {RATIONALE_MIN_CHARS}~{RATIONALE_MAX_CHARS}자"
_RATIONALE_BOUNDS_EN = f"{RATIONALE_MIN_CHARS}-{RATIONALE_MAX_CHARS} normalized chars"

# v.8 §4 definitions, shared by the MUST-Q3 messages so the synthesizer sees the same rule each time.
_UNITS_RULE_KO = (
    "다리는 서로 다른 주인 2명 이상의 서브브레인 노드를 함께 인용하는 new 노드이고, 호스트 다리는 그중 호스트 "
    "서브브레인 노드를 인용하는 다리입니다. 창발 엣지는 양 끝 노드가 인용한 출처의 주인을 합쳐 2명 이상인 엣지인데, "
    "query 노드에 닿는 엣지와 자기 앵커 엣지(new 노드와, 그 new 노드가 이미 인용한 노드를 앵커한 source 노드를 잇는 "
    "엣지)는 세지 않습니다. new 노드끼리 잇는 엣지는 이 조건을 만족하면 창발입니다. 엣지에 직접 적은 출처는 근거일 뿐 "
    "창발이나 호스트 판정에 쓰지 않습니다."
)
_UNITS_RULE_EN = (
    "A bridge is a new node whose provenance cites subbrain nodes of 2 or more different owners; a host bridge is a "
    "bridge that cites a host subbrain node. An emergent edge is an edge whose two END NODES together cite 2 or more "
    "owners, except edges touching the query node and self-anchor edges (a new node linked to a source node that "
    "anchors a node the new node already cites). An edge between two new nodes is emergent when it meets these "
    "conditions. Refs written on the edge itself are evidence and never count for emergence or the host."
)


def _check_emergence(analysis: _Analysis) -> list[Violation]:
    """MUST-Q3 (v.8): bridges + emergent edges >= 1, and one of them touches the host."""
    bridges, emergent = analysis.bridges, analysis.emergent
    if not bridges and not emergent:
        return [_v(
            ViolationCode.NO_EMERGENCE,
            f"다리도 창발 엣지도 없습니다. {_UNITS_RULE_KO} 고치려면 서로 다른 주인의 노드를 함께 인용하는 new 노드(다리)를 "
            f"만들고 {_SUMMARY_BOUNDS_KO} summary를 쓰거나, 서로 다른 주인의 서브브레인을 앵커한 source 노드 둘을 "
            f"{_RATIONALE_BOUNDS_KO} rationale과 함께 이으세요. "
            f"/ No bridge and no emergent edge. {_UNITS_RULE_EN} To fix it, add a new node (a bridge) that cites nodes "
            f"of different owners and give it a summary of {_SUMMARY_BOUNDS_EN}, or link two source nodes anchored in "
            f"different owners' subbrains with a rationale of {_RATIONALE_BOUNDS_EN}.",
        )]
    if not any(info.host_bridge for info in bridges) and not any(info.host_touching for info in emergent):
        return [_v(
            ViolationCode.HOST_NOT_TOUCHED,
            f"호스트에 닿는 다리도 창발 엣지도 없습니다. {_UNITS_RULE_KO} 창발 엣지가 호스트에 닿는지는 양 끝 노드 중 "
            f"하나가 호스트 서브브레인 노드를 인용하는지로만 정합니다. 고치려면 호스트 노드와 다른 주인의 노드를 함께 "
            f"인용하는 new 노드(호스트 다리)를 만들고 {_SUMMARY_BOUNDS_KO} summary를 쓰거나, 호스트 노드를 앵커한 source "
            f"노드를 다른 주인의 서브브레인을 앵커한 source 노드와 {_RATIONALE_BOUNDS_KO} rationale과 함께 이으세요. "
            f"/ No bridge or emergent edge touches the host subbrain. {_UNITS_RULE_EN} An emergent edge touches the "
            f"host only when one of its end nodes cites a host subbrain node. To fix it, add a new node (a host bridge) "
            f"that cites both a host node and another owner's node and give it a summary of {_SUMMARY_BOUNDS_EN}, or "
            f"link a source node anchored in the host subbrain to a source node anchored in another owner's subbrain "
            f"with a rationale of {_RATIONALE_BOUNDS_EN}.",
        )]
    return []


def _length_problem(length: int, low: int, high: int, field: str, subject_ko: str) -> tuple[str, str] | None:
    """(Korean, English) phrase for a length outside [low, high]; `subject_ko` is the field with its particle."""
    if low <= length <= high:
        return None
    if length == 0:
        return f"{subject_ko} 없습니다", f"has no {field}"
    if length < low:
        return f"{subject_ko} {length}자로 너무 짧습니다", f"{field} is too short ({length} chars)"
    return f"{subject_ko} {length}자로 너무 깁니다", f"{field} is too long ({length} chars)"


def _check_rationales(analysis: _Analysis) -> list[Violation]:
    """MUST-Q4 (v.8): every rating unit carries an explanation (normalized characters).

    Bridge nodes need a summary, emergent edges a rationale. Other nodes and edges are not rating units.
    """
    out: list[Violation] = []
    for info in analysis.bridges:
        node = info.node
        problem = _length_problem(
            len(normalize(node.summary)), BRIDGE_SUMMARY_MIN_CHARS, BRIDGE_SUMMARY_MAX_CHARS, "summary", "summary가"
        )
        if problem is None:
            continue
        ko, en = problem
        out.append(_v(
            ViolationCode.RATIONALE_MISSING,
            f"다리 노드 {_q(node.id)}의 {ko}. 다리(서로 다른 주인 2명 이상의 노드를 인용한 new 노드)는 사람이 평가하는 "
            f"단위라서 설명이 있어야 합니다. 이 개념이 무엇이고 어떻게 작동하는지 {_SUMMARY_BOUNDS_KO}로 summary에 쓰세요. "
            f"정규화는 보이지 않는 문자와 구두점을 공백으로 바꾸고 연속 공백을 하나로 줄인 뒤 셉니다. "
            f"/ Bridge node {_q(node.id)} {en}. A bridge (a new node citing nodes of 2 or more different owners) is a "
            f"rating unit and needs an explanation: say what the concept is and how it works in its summary, in "
            f"{_SUMMARY_BOUNDS_EN} (invisible characters and punctuation count as spaces, and runs of spaces count "
            f"as one).",
            node_id=node.id,
        ))
    for info in analysis.emergent:
        edge = info.edge
        problem = _length_problem(
            len(normalize(edge.rationale)), RATIONALE_MIN_CHARS, RATIONALE_MAX_CHARS, "rationale", "rationale이"
        )
        if problem is None:
            continue
        ko, en = problem
        out.append(_v(
            ViolationCode.RATIONALE_MISSING,
            f"창발 엣지 {_q(edge.id)}의 {ko}. 창발 엣지(양 끝 노드의 출처 주인이 2명 이상이고, query 노드에 닿지 않고, "
            f"자기 앵커 엣지가 아닌 엣지)는 사람이 평가하는 단위입니다. 이 연결이 왜 성립하는지 {_RATIONALE_BOUNDS_KO}로 "
            f"쓰세요. 정규화는 보이지 않는 문자와 구두점을 공백으로 바꾸고 연속 공백을 하나로 줄인 뒤 셉니다. "
            f"/ Emergent edge {_q(edge.id)} {en}. An emergent edge (end nodes citing 2 or more owners, not touching the "
            f"query node, not a self-anchor edge) is a rating unit: explain why the link holds in {_RATIONALE_BOUNDS_EN} "
            f"(invisible characters and punctuation count as spaces, and runs of spaces count as one).",
            edge_id=edge.id,
        ))
    return out


def _check_novelty(sub: DeltabrainSubmission, idx: _CanalIndex, infos: list[_EdgeInfo]) -> list[Violation]:
    """MUST-Q5."""
    out: list[Violation] = []
    for node in sub.nodes:
        if node.kind != NodeKind.NEW:
            continue
        label = normalize(node.label)
        if label and label in idx.all_labels:
            out.append(_v(
                ViolationCode.NOT_NOVEL,
                f"new 노드 {_q(node.id)}의 라벨이 정규화하면 커널 입력 서브브레인에 이미 있는 라벨과 같습니다"
                f"(대소문자, 구두점, 보이지 않는 문자, 연속 공백의 차이는 무시됩니다). "
                f"기존 개념이면 source 노드로 인용하고, 새 개념이면 그 차이가 드러나는 라벨을 쓰세요. "
                f"/ New node {_q(node.id)} label equals, after normalization (case, punctuation, invisible characters "
                f"and extra spaces are ignored), a label in a canal input subbrain; "
                f"anchor it as a source node, or name what is actually new.",
                node_id=node.id,
            ))
    sources = {node.id: node for node in sub.nodes if node.kind == NodeKind.SOURCE}
    for info in infos:
        edge = info.edge
        # Oracle v.3: applies to every source-source edge, emergent or not (a deltabrain carries only the delta).
        if edge.source not in sources or edge.target not in sources:
            continue
        copied = _copied_input_edge(sources[edge.source], sources[edge.target], idx)
        if copied is not None:
            subbrain_id, version = copied
            out.append(_v(
                ViolationCode.NOT_NOVEL,
                f"엣지 {_q(edge.id)}는 입력 서브브레인 ({_q(subbrain_id)}, v{version})에 이미 있는 엣지(같은 두 노드, "
                f"방향 무관)를 옮긴 것입니다. 양 끝이 source인 엣지는 창발 여부와 무관하게 이 검사를 받고, 엣지에 붙인 "
                f"출처나 relation을 바꿔도 같은 엣지입니다. 이 엣지를 빼거나 입력에 없는 새 연결로 바꾸세요. "
                f"/ Edge {_q(edge.id)} copies an edge that already exists in input subbrain "
                f"({_q(subbrain_id)}, v{version}) (same two nodes, either direction). Every source-to-source edge is "
                f"checked, emergent or not, and changing its relation or edge refs does not make it new; remove it or "
                f"replace it with a connection the inputs do not already contain.",
                edge_id=edge.id,
            ))
    return out


def _copied_input_edge(a: DeltaNode, b: DeltaNode, idx: _CanalIndex) -> _SubbrainKey | None:
    """The subbrain version that already links the nodes cited by `a` and `b`, if any.

    Node ids are only unique within one subbrain version, so both cited nodes must come
    from the same version for an input edge to exist between them.
    """
    for ra in (ref for ref in _distinct(a.provenance) if idx.is_valid(ref)):
        for rb in (ref for ref in _distinct(b.provenance) if idx.is_valid(ref)):
            key = idx.key(ra)
            if key == idx.key(rb) and frozenset((ra.node_id, rb.node_id)) in idx.edge_pairs[key]:
                return key
    return None


def _generic_vocabulary(generic_terms: Iterable[str], josa_suffixes: Sequence[str], min_stem: int) -> frozenset[str]:
    """Generic terms in the same form label tokens take (normalized, josa stripped)."""
    vocab: set[str] = set()
    for term in generic_terms:
        norm = normalize(term)
        if norm:
            vocab.add(norm)
        tokens = tokenize(term, josa_suffixes=josa_suffixes, min_stem=min_stem)
        if len(tokens) == 1:
            vocab.add(tokens[0])
    return frozenset(vocab)


def _check_generic(
    sub: DeltabrainSubmission,
    generic_terms: Iterable[str],
    josa_suffixes: Sequence[str],
    min_stem: int,
) -> list[Violation]:
    """MUST-Q6."""
    vocab = _generic_vocabulary(generic_terms, josa_suffixes, min_stem)
    out: list[Violation] = []
    for node in sub.nodes:
        if node.kind != NodeKind.NEW:
            continue
        tokens = tokenize(node.label, josa_suffixes=josa_suffixes, min_stem=min_stem, stopwords=())
        if not tokens:
            # Punctuation-only label: no content word at all, which is the generic case at its limit.
            out.append(_v(
                ViolationCode.GENERIC_LABEL,
                f"new 노드 {_q(node.id)}의 라벨에 내용 단어가 없습니다. 무엇이 무엇에 어떻게 작용하는지 구체적으로 이름 붙이세요. "
                f"/ New node {_q(node.id)} label has no content words; name the specific concept or mechanism.",
                node_id=node.id,
            ))
        elif all(token in vocab for token in tokens):
            words = ", ".join(tokens)
            out.append(_v(
                ViolationCode.GENERIC_LABEL,
                f"new 노드 {_q(node.id)}의 라벨이 금지 일반어({words})로만 이뤄져 있습니다. "
                f"무엇이 무엇에 어떻게 작용하는지 구체적으로 이름 붙이세요. "
                f"/ New node {_q(node.id)} label uses only generic terms ({words}); "
                f"name the specific concept or mechanism.",
                node_id=node.id,
            ))
    return out


# Normalized text keeps only word characters and single spaces, so a punctuation-only placeholder can never
# collide with rationale text or be matched by a (normalized) label during later replacements.
_LABEL_PLACEHOLDER = "<>"


def _label_skeleton(text: str, labels: Iterable[str]) -> str:
    """ORACLE v.4 MUST-Q7: every occurrence of an endpoint label in a normalized rationale becomes one placeholder.

    Longest label first, so a label that is part of the other endpoint's label does not split it.
    Empty labels are skipped: replacing "" would insert the placeholder between every character.
    """
    for label in sorted({label for label in labels if label}, key=len, reverse=True):
        text = text.replace(label, _LABEL_PLACEHOLDER)
    return text


@dataclass(frozen=True)
class _Explanation:
    """One rating unit's normalized explanation for MUST-Q7."""

    unit_id: str
    is_node: bool
    text: str
    skeleton: str | None  # emergent edges only: endpoint labels replaced (v.4); summaries compare as text


def _explanations(sub: DeltabrainSubmission, analysis: _Analysis) -> list[_Explanation]:
    """Bridge summaries, then emergent edge rationales, in submission order. Empty ones are RATIONALE_MISSING."""
    out: list[_Explanation] = []
    for info in analysis.bridges:
        text = normalize(info.node.summary)
        if text:
            # v.9 MUST-Q7: a summary is compared with its own bridge label replaced, like a rationale (v.4).
            skeleton = _label_skeleton(text, (normalize(info.node.label),))
            out.append(_Explanation(unit_id=info.node.id, is_node=True, text=text, skeleton=skeleton))
    labels = {node.id: normalize(node.label) for node in sub.nodes}
    for info in analysis.emergent:
        text = normalize(info.edge.rationale)
        if text:
            ends = (labels.get(info.edge.source, ""), labels.get(info.edge.target, ""))
            out.append(_Explanation(
                unit_id=info.edge.id, is_node=False, text=text, skeleton=_label_skeleton(text, ends)
            ))
    return out


def _check_templated(sub: DeltabrainSubmission, analysis: _Analysis) -> list[Violation]:
    """MUST-Q7 (v.8): share of rating units whose normalized explanation repeats another unit's <= 20%.

    The units are bridge summaries and emergent edge rationales, compared in one pool: a summary that equals a
    rationale counts for both. Two rationales are also the same when, after each edge's two endpoint labels are
    replaced by one placeholder (v.4), their skeletons are equal: a template with only the labels swapped is the
    same sentence, and an exact copy stays a copy. v.9: a bridge summary gets the same treatment with its own label.
    """
    units = _explanations(sub, analysis)
    if not units:
        return []
    text_counts = Counter(unit.text for unit in units)
    skeleton_counts = Counter(unit.skeleton for unit in units if unit.skeleton is not None)
    repeated = [
        unit
        for unit in units
        if text_counts[unit.text] > 1 or (unit.skeleton is not None and skeleton_counts[unit.skeleton] > 1)
    ]
    total = len(units)
    share = Fraction(len(repeated), total)
    if share <= _TEMPLATED_MAX:
        return []
    pct = round(100 * share)
    limit = round(100 * _TEMPLATED_MAX)
    node_ids = [unit.unit_id for unit in repeated if unit.is_node]
    edge_ids = [unit.unit_id for unit in repeated if not unit.is_node]
    listed_ko = "; ".join(
        part for part in (
            f"다리 노드 {_id_list(node_ids)}" if node_ids else "",
            f"창발 엣지 {_id_list(edge_ids)}" if edge_ids else "",
        ) if part
    )
    listed_en = "; ".join(
        part for part in (
            f"bridge nodes {_id_list(node_ids)}" if node_ids else "",
            f"emergent edges {_id_list(edge_ids)}" if edge_ids else "",
        ) if part
    )
    return [_v(
        ViolationCode.TEMPLATED_RATIONALE,
        f"평가 단위(다리 노드의 summary와 창발 엣지의 rationale) {total}개 중 {len(repeated)}개({pct}%)의 설명이 다른 "
        f"단위와 같은 문장입니다(허용 {limit}% 이하): {listed_ko}. 비교 전에 정규화하고, 엣지 rationale은 그 엣지의 양 끝 "
        f"노드 라벨을 같은 자리표시자로 바꾸므로 노드 이름만 갈아 끼운 틀 문장도 같은 문장입니다. 다리 summary와 엣지 "
        f"rationale도 서로 비교합니다. 다리마다 그 개념이 무엇이고 어떻게 작동하는지, 엣지마다 무엇이 무엇에 대응하고 "
        f"왜 그 연결이 성립하는지를 그 단위에만 해당하는 내용으로 다시 쓰세요. "
        f"/ {len(repeated)} of {total} rating units ({pct}%; bridge node summaries and emergent edge rationales) "
        f"share the same explanation (max {limit}%): {listed_en}. Explanations are compared after normalization, and "
        f"each edge rationale has both of its end-node labels replaced by one placeholder, so a template with only "
        f"the node names swapped is the same sentence; summaries and rationales are compared with each other too. "
        f"Rewrite each one with content specific to that unit: what the bridge concept is and how it works, or what "
        f"maps to what and why this particular link holds.",
    )]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _format_loc(loc: tuple[Any, ...]) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out or "(root)"


def _id_at(payload: Any, loc: tuple[Any, ...], collection: str) -> str | None:
    """Best-effort id of the node/edge an error points at (payload shape is untrusted)."""
    if len(loc) < 2 or loc[0] != collection or not isinstance(loc[1], int):
        return None
    try:
        item_id = payload[collection][loc[1]]["id"]
    except (KeyError, IndexError, TypeError):
        return None
    return item_id if isinstance(item_id, str) else None


def parse_submission(payload: dict[str, Any]) -> tuple[DeltabrainSubmission | None, ValidationResult | None]:
    """Parse raw JSON. On pydantic failure return (None, ValidationResult(ok=False, SCHEMA_INVALID ...))."""
    try:
        return DeltabrainSubmission.model_validate(payload), None
    except ValidationError as exc:
        violations = []
        for error in exc.errors(include_url=False, include_input=False):
            loc = tuple(error.get("loc", ()))
            where = _format_loc(loc)
            msg = error.get("msg", "invalid")
            violations.append(_v(
                ViolationCode.SCHEMA_INVALID,
                f"스키마 오류 {where}: {msg}. 이 필드를 제출 형식(nodes[{{id,kind,label,provenance}}], "
                f"edges[{{id,source,target,relation,rationale}}])에 맞게 고치세요. "
                f"/ Schema error at {where}: {msg}; fix this field to match the submission format.",
                node_id=_id_at(payload, loc, "nodes"),
                edge_id=_id_at(payload, loc, "edges"),
            ))
        return None, ValidationResult(ok=False, violations=violations, stats=None)


def compute_stats(submission: DeltabrainSubmission, ctx: CanalContext) -> DeltabrainStats:
    """Stats under ORACLE v.8 §4 (same as validate_deltabrain's), tolerating graphs that fail the schema checks.

    Bridges = new nodes citing >= 2 owners (host bridge: also cites the host subbrain). Emergent edges = endpoint
    provenance owners >= 2, not touching a query node, not a self-anchor edge; host-touching = an endpoint cites
    the host subbrain. Edge-level refs count only toward owners_involved.
    """
    idx = _index(ctx)
    return _stats(submission, idx, _analyze(submission, idx))


def validate_deltabrain(
    payload: dict[str, Any] | DeltabrainSubmission,
    ctx: CanalContext,
    *,
    generic_terms: frozenset[str],
    josa_suffixes: list[str] | tuple[str, ...] = (),
    josa_min_stem_length: int = 2,
) -> ValidationResult:
    """Run every L1 check and return ALL violations (not just the first). ok == (no violations)."""
    if isinstance(payload, DeltabrainSubmission):
        submission = payload
    else:
        parsed, failure = parse_submission(payload)
        if failure is not None:
            return failure
        assert parsed is not None
        submission = parsed

    schema = _check_graph_schema(submission)
    if schema:  # ids/endpoints are unreliable, so graph checks would mislead
        return ValidationResult(ok=False, violations=schema, stats=None)

    idx = _index(ctx)
    analysis = _analyze(submission, idx)
    violations = [
        *_check_size(submission),
        *_check_query_count(submission),
        *_check_provenance(submission, idx),
        *_check_source_labels(submission, idx),
        *_check_hops(submission),
        *_check_relations(submission),
        *_check_emergence(analysis),
        *_check_rationales(analysis),
        *_check_novelty(submission, idx, analysis.edges),
        *_check_generic(submission, generic_terms, josa_suffixes, josa_min_stem_length),
        *_check_templated(submission, analysis),
    ]
    return ValidationResult(ok=not violations, violations=violations, stats=_stats(submission, idx, analysis))
