"""Fixture design constraints (ORACLE §6.1-§6.4), checked mechanically with the contract tokenizer.

These pin the fixtures themselves, so a later edit cannot silently weaken MUST-M1/M3, NEVER-08 or Q-tests.
They use only contract code (textnorm, config, models) and pass without any implementation.
"""

from __future__ import annotations

from collections import deque

import pytest

from opencanal.models import ALLOWED_RELATIONS, DeltabrainSubmission, NodeKind, SubbrainDocument
from opencanal.textnorm import normalize, tokenize

from .conftest import (
    BRAIN_IDS,
    INJECTION_FRAGMENT,
    INJECTION_FRAGMENT_EN,
    Q01,
    Q01_TERMS,
    Q02,
    Q03,
    Q03_TERMS,
    Q_SECURITY,
    all_brain_texts,
    fixture_sid,
    load_brain,
    load_delta,
)

EXPECTED_OWNERS = {
    "A": "user_a",
    "A2": "user_e",
    "B": "user_b",
    "C": "user_c",
    "D": "user_d",
    "P": "user_b",
    "X": "user_x",
}


def _tok(cfg, text):
    m = cfg.matching
    return tokenize(text, josa_suffixes=m.josa_suffixes, min_stem=m.josa_min_stem_length, stopwords=m.stopwords)


def _words(texts):
    out = set()
    for t in texts:
        out.update(w for w in normalize(t).split(" ") if w)
    return out


def _bigrams(words):
    return {w[i : i + 2] for w in words for i in range(len(w) - 1)}


def _host_label_tag_texts(doc):
    yield doc["title"]
    yield from doc["domains"]
    for n in doc["nodes"]:
        yield n["label"]
        yield from n.get("tags", [])


def _all_tags(doc):
    return {t for n in doc["nodes"] for t in n.get("tags", [])}


def _labels(doc):
    return {n["label"] for n in doc["nodes"]}


def test_fixture_golden_query_terms(cfg):
    assert _tok(cfg, Q01) == Q01_TERMS
    assert _tok(cfg, Q02) == []  # MUST-M3: no topic terms
    assert _tok(cfg, Q03) == Q03_TERMS
    assert _tok(cfg, Q_SECURITY) == ["보안", "체크리스트", "점검"]


@pytest.mark.parametrize("fid", BRAIN_IDS)
def test_fixture_brain_shared_format(fid):
    brain = load_brain(fid)
    assert brain["fixture_id"] == fid
    assert set(brain) == {"fixture_id", "owner", "visibility", "document"}
    assert brain["owner"]["user_id"] == EXPECTED_OWNERS[fid]
    assert brain["owner"]["tier"] == "free"
    assert brain["visibility"] == ("private" if fid == "P" else "public")
    doc = SubbrainDocument.model_validate(brain["document"])
    assert 8 <= len(doc.nodes) <= 15
    ids = [n.id for n in doc.nodes]
    assert len(ids) == len(set(ids))
    assert doc.edges, "each brain has edges among its own nodes"
    for e in doc.edges:
        assert e.source in ids and e.target in ids
    assert all(n.tags for n in doc.nodes)


def test_fixture_required_labels_and_tags():
    a, a2, b, c = (load_brain(f)["document"] for f in ("A", "A2", "B", "C"))
    assert {"현장 조립 오류", "접합부 상세"} <= _labels(a)
    assert a["domains"] == ["건축", "BIM"]
    assert {"조립", "오류"} <= _all_tags(b)
    assert {"조립", "오류"} <= _all_tags(c)
    assert "형태 상보성" in _labels(c)
    assert "잘못 놓을 수 없는 블록 모양" in _labels(b)
    assert {"모듈러", "건축"} <= _all_tags(a2)


@pytest.mark.parametrize("fid", BRAIN_IDS)
def test_fixture_no_brain_contains_q03_terms(fid):
    """NEVER-08: Q-03 must find nothing, so no fixture token may even contain a Q-03 term."""
    words = _words(all_brain_texts(load_brain(fid)["document"]))
    hits = _bigrams(words) & _bigrams(Q03_TERMS)
    assert not hits, (fid, hits)


@pytest.mark.parametrize("fid", ["D", "X"])
def test_fixture_unrelated_brains_share_nothing_with_queries_or_host(fid, cfg):
    """MUST-M1/M3: D (and X) must score 0 for Q-01, Q-03 and whole_host(A), whatever tau is.

    Strongest form: no 2-character substring of any word in the brain occurs in a Q-01/Q-03 term or
    in any word of A's title, domains, labels or tags.
    """
    words = _words(all_brain_texts(load_brain(fid)["document"]))
    host_words = _words(_host_label_tag_texts(load_brain("A")["document"]))
    assert all(len(w) >= 2 for w in host_words)
    for name, other in (("Q-01", Q01_TERMS), ("Q-03", Q03_TERMS), ("host A", host_words)):
        hits = _bigrams(words) & _bigrams(other)
        assert not hits, (fid, name, hits)


def test_fixture_security_query_matches_only_x():
    terms = ["보안", "체크리스트", "점검"]
    for fid in BRAIN_IDS:
        words = _words(all_brain_texts(load_brain(fid)["document"]))
        hit = any(t in w for t in terms for w in words)
        assert hit == (fid == "X"), fid


def test_fixture_q01_overlap_design():
    """B and C match Q-01 only through 조립/오류; A2 only through 모듈러/건축/현장; P through all five."""

    def matched(fid):
        words = _words(all_brain_texts(load_brain(fid)["document"]))
        return {t for t in Q01_TERMS if any(t in w for w in words)}

    assert matched("B") == {"조립", "오류"}
    assert matched("C") == {"조립", "오류"}
    assert matched("A2") == {"모듈러", "건축", "현장"}
    assert matched("P") == set(Q01_TERMS)
    assert matched("D") == set()
    assert matched("X") == set()


def test_fixture_x_carries_injection():
    x = load_brain("X")["document"]
    summaries = [n.get("summary") or "" for n in x["nodes"]]
    assert any(INJECTION_FRAGMENT in s and INJECTION_FRAGMENT_EN in s for s in summaries)
    assert {"보안", "체크리스트"} <= _all_tags(x)


def test_fixture_identities_do_not_occur_in_content():
    """NEVER-11 searches responses for owner ids/display names; they must not collide with content."""
    texts = " ".join(t for fid in BRAIN_IDS for t in all_brain_texts(load_brain(fid)["document"]))
    for fid in BRAIN_IDS:
        owner = load_brain(fid)["owner"]
        assert owner["user_id"] not in texts
        assert owner["display_name"] not in texts


# ---------------------------------------------------------------------------
# good-01 hand check (ORACLE §4, §5.1) — independent of the validator implementation
# ---------------------------------------------------------------------------


def _ctx_brains():
    return {(fixture_sid(f), 1): load_brain(f) for f in ("A", "B", "C")}


def _node_owners(node, ctx):
    return {ctx[(r.subbrain_id, r.version)]["owner"]["user_id"] for r in node.provenance}


def _cites_host(node):
    return any((r.subbrain_id, r.version) == ("sb_A", 1) for r in node.provenance)


def _v8_edge_kind(edge, by_id, ctx):
    """ORACLE v.8 §4 by hand: "query" / "self_anchor" / "emergent" / "plain". Edge-level refs are evidence only (v.3).

    Was (v.7 and earlier): every edge whose endpoint (+ edge) refs had >= 2 owners was emergent.
    """
    s, t = by_id[edge.source], by_id[edge.target]
    if NodeKind.QUERY in (s.kind, t.kind):
        return "query"
    if {s.kind, t.kind} == {NodeKind.NEW, NodeKind.SOURCE}:
        new, src = (s, t) if s.kind == NodeKind.NEW else (t, s)
        if {(r.subbrain_id, r.version, r.node_id) for r in src.provenance} & {
            (r.subbrain_id, r.version, r.node_id) for r in new.provenance
        }:
            return "self_anchor"
    return "emergent" if len(_node_owners(s, ctx) | _node_owners(t, ctx)) >= 2 else "plain"


def test_fixture_good01_satisfies_every_l1_rule_by_hand(cfg):
    sub = DeltabrainSubmission.model_validate(load_delta("good-01"))
    ctx = _ctx_brains()
    by_id = {n.id: n for n in sub.nodes}
    assert len(by_id) == len(sub.nodes)
    for e in sub.edges:
        assert e.source in by_id and e.target in by_id
    assert len(sub.nodes) <= 60 and len(sub.edges) <= 120

    queries = [n for n in sub.nodes if n.kind == NodeKind.QUERY]
    assert len(queries) == 1 and not queries[0].provenance

    input_labels = {normalize(n["label"]) for b in ctx.values() for n in b["document"]["nodes"]}

    def cited(ref):
        doc = ctx[(ref.subbrain_id, ref.version)]["document"]
        return next(n for n in doc["nodes"] if n["id"] == ref.node_id)

    for n in sub.nodes:
        if n.kind == NodeKind.SOURCE:
            assert len(n.provenance) == 1
            assert cited(n.provenance[0])["label"] == n.label
        if n.kind == NodeKind.NEW:
            assert len(n.provenance) >= 2
            owners = {ctx[(r.subbrain_id, r.version)]["owner"]["user_id"] for r in n.provenance}
            assert len(owners) >= 2
            for r in n.provenance:
                cited(r)
            assert normalize(n.label) not in input_labels
            toks = tokenize(n.label, josa_suffixes=cfg.matching.josa_suffixes)
            assert not all(t in cfg.generic_terms for t in toks)
            assert not set(normalize(n.label).split()) & cfg.generic_terms

    adj = {i: set() for i in by_id}
    for e in sub.edges:
        adj[e.source].add(e.target)
        adj[e.target].add(e.source)
    dist = {queries[0].id: 0}
    dq = deque([queries[0].id])
    while dq:
        cur = dq.popleft()
        for nb in adj[cur]:
            if nb not in dist:
                dist[nb] = dist[cur] + 1
                dq.append(nb)
    assert all(dist.get(i, 99) <= 3 for i in by_id), dist

    # ORACLE v.8 §4 / MUST-Q3 / MUST-Q4 / MUST-Q7: bridges need a 40..600 summary, emergent edges a 40..400 rationale,
    # and no two units share a description.
    bridges = [n.id for n in sub.nodes if n.kind == NodeKind.NEW and len(_node_owners(n, ctx)) >= 2]
    host_bridges = [b for b in bridges if _cites_host(by_id[b])]
    descriptions = []
    for b in bridges:
        s = normalize(by_id[b].summary)
        assert 40 <= len(s) <= 600, (b, len(s))
        descriptions.append(s)
    kinds = {}
    emergent, host_touching = [], []
    for e in sub.edges:
        assert e.relation in ALLOWED_RELATIONS
        kinds[e.id] = _v8_edge_kind(e, by_id, ctx)
        if kinds[e.id] == "emergent":
            emergent.append(e.id)
            if _cites_host(by_id[e.source]) or _cites_host(by_id[e.target]):
                host_touching.append(e.id)
            r = normalize(e.rationale)
            assert 60 <= len(r) <= 150, (e.id, len(r))  # well inside 40..400
            descriptions.append(r)
    assert len(set(descriptions)) == len(descriptions)
    assert set(bridges) == set(host_bridges) == {"n1", "n2"}
    assert set(emergent) == {"e3", "e4", "e9", "e10"}
    assert set(host_touching) == {"e3", "e4", "e10"}
    assert {k for k, v in kinds.items() if v == "self_anchor"} == {"e5", "e6", "e7", "e8"}
    assert {k for k, v in kinds.items() if v == "query"} == {"e1", "e2"}

    edges = {e.id: e for e in sub.edges}
    g1, g2 = edges["e3"], edges["e4"]
    assert (by_id[g1.source].label, g1.relation, by_id[g1.target].label) == ("형태 상보성", "applies_to", "현장 조립 오류")
    assert (by_id[g2.source].label, g2.relation, by_id[g2.target].label) == (
        "잘못 놓을 수 없는 블록 모양",
        "analogous_to",
        "접합부 상세",
    )
    assert g1.applies_when and g2.applies_when


@pytest.mark.parametrize(
    "name",
    [
        "bad-no-provenance",
        "bad-foreign-provenance",
        "bad-invalid-node",
        "bad-generic",
        "bad-copy",
        "bad-same-owner",
        "bad-host-untouched",
        "bad-off-query",
        "bad-two-queries",
        "bad-templated",
        "bad-templated-02",
        "bad-no-rationale",
        "bad-source-mismatch",
        "bad-schema-duplicate-id",
        "bad-schema-dangling-edge",
    ],
)
def test_fixture_bad_deltabrains_parse_as_submissions(name):
    """Every bad-* file is well-formed JSON for DeltabrainSubmission, so the validator sees its target rule."""
    DeltabrainSubmission.model_validate(load_delta(name))


# ---------------------------------------------------------------------------
# Oracle v.8 vs §6.4 golden files (by hand, no implementation)
# ---------------------------------------------------------------------------


def test_fixture_v8_bad_templated_template_sits_on_non_unit_edges():
    """CONFLICT for the Oracle owner: §6.4 says bad-templated.json -> TEMPLATED_RATIONALE, but under v.8 §4 the shared
    template sits on e5, e6, e7 (self-anchor edges, not units) and e10 (the only emergent edge carrying it), so MUST-Q7
    v.8 counts 0 of 6 units as duplicates. fixtures/deltabrains/bad-templated-02.json moves the template onto emergent
    edges (e4, e9, e10 -> 3 of 6). bad-templated.json itself is frozen and left unchanged."""
    sub = DeltabrainSubmission.model_validate(load_delta("bad-templated"))
    ctx = _ctx_brains()
    by_id = {n.id: n for n in sub.nodes}
    texts: dict[str, list[str]] = {}
    for e in sub.edges:
        if e.rationale:
            texts.setdefault(normalize(e.rationale), []).append(e.id)
    shared = [ids for ids in texts.values() if len(ids) > 1]
    assert shared == [["e5", "e6", "e7", "e10"]], shared
    kinds = {e.id: _v8_edge_kind(e, by_id, ctx) for e in sub.edges}
    assert [kinds[i] for i in shared[0]] == ["self_anchor", "self_anchor", "self_anchor", "emergent"]

    sub2 = DeltabrainSubmission.model_validate(load_delta("bad-templated-02"))
    by_id2 = {n.id: n for n in sub2.nodes}
    texts2: dict[str, list[str]] = {}
    for e in sub2.edges:
        if _v8_edge_kind(e, by_id2, ctx) == "emergent":
            texts2.setdefault(normalize(e.rationale), []).append(e.id)
    assert sorted(ids for ids in texts2.values() if len(ids) > 1) == [["e4", "e9", "e10"]]
    good = {n.id: n.model_dump() for n in DeltabrainSubmission.model_validate(load_delta("good-01")).nodes}
    assert {n.id: n.model_dump() for n in sub2.nodes} == good, "bad-templated-02 differs from good-01 only in rationales"
