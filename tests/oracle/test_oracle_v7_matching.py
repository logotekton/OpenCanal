"""MUST-M5 v.7 (Oracle 2026-10-06.7): distance = share of the host's distinct label/tag words the candidate has.

ORACLE §5.4 MUST-M5 (v.7): "유사도 = 호스트 낱말 중 후보도 가진 낱말의 비율 = |H ∩ C| ÷ |H|. H와 C는 각 서브브레인(호스트는
커널에 쓰는 버전, 후보는 공개 버전)의 노드 라벨과 태그에서 textnorm.tokenize(조사 제거, 불용어 제거)로 만든 서로 다른
낱말의 집합이다. 요약, 노드 유형, 엣지, 제목, 신고한 분야(domains)는 쓰지 않는다. 거리 = 1 − min(1, 유사도 ÷
distance_saturation). H가 비면 거리 1. 계산은 정확해야 하고(유리수), 결과는 결정적이다. 후보가 호스트와 겹치지 않는 낱말을
아무리 덧붙여도 거리는 변하지 않는다." Forbidden: "낱말 채우기·반복으로 거리를 키울 수 있음, 신고한 분야나 제목으로 거리가
바뀜".

§9 (v.7): v.6's cosine let a candidate raise its own distance by padding with one repeated unrelated word and so take
the bonus and the far slot (adversarial review M5-PAD-1); summaries were dropped; "fixture: 라벨·태그만 쓰면 A2 0.278,
B·C 0.056, D·X 0". MUST-M2: score = relevance + distance_bonus × distance, ties by relevance, then subbrain_id
ascending, compared unrounded. §10: relevance keyword stuffing (MUST-M1) is still open, so nothing here pins it —
every filler word below is chosen so that relevance cannot move, and the tests self-check that.

Expected values come from the independent exact reference in _v7.py (never from the implementation). A distance is
observed through MatchCandidate.distance (pure matching.match), match_explain and canal_open. Reported values may be
rounded for display (MUST-M2 v.6), so a reported value is compared with the exact reference within DISPLAY_TOL, and
two reported values that must be equal are compared with == (the same exact value displays the same way).
"""

from __future__ import annotations

import copy
from fractions import Fraction

import pytest

from opencanal.models import QueryMode, Tier

from .conftest import (
    Q01,
    Q01_TERMS,
    Q02,
    Q03,
    World,
    assert_ok,
    find_dicts,
    fixture_sid,
    fixture_version,
    load_brain,
    member_ids,
)
from ._v4 import reference_relevance, version_from_doc
from ._v7 import (
    DISJOINT,
    FILLER_REPEATED,
    FILLERS,
    QT_TERMS,
    SAFE_HOST_WORDS,
    add_tags,
    distance_for_shared,
    nodes_doc,
    pad_doc,
    reference_distance,
    reference_distance_exact,
    reference_similarity,
    reference_word_set,
    saturation,
)
from .test_oracle_v5_matching import QK_TERMS

DISPLAY_TOL = 1e-3  # reported values may be rounded for display (MUST-M2 v.6); same tolerance as the v.5/v.6 tests
FIXTURES = ("A2", "B", "C", "D", "X")
ALL_QUERY_TERMS = frozenset([*Q01_TERMS, *QK_TERMS, *QT_TERMS])


def _doc(fid: str) -> dict:
    return load_brain(fid)["document"]


def _host() -> dict:
    return _doc("A")


def _v(doc: dict, sid: str, owner: str | None = None):
    return version_from_doc(doc, subbrain_id=sid, owner_id=owner or f"user_{sid.lower()}")


def _match(query, candidates, cfg, *, host=None, max_members=50, strategy=None, query_mode=QueryMode.AUTO, mcfg=None):
    from opencanal import matching

    return matching.match(
        query,
        host if host is not None else fixture_version("A"),
        candidates,
        max_members=max_members,
        cfg=mcfg or cfg.matching,
        query_mode=query_mode,
        strategy=strategy,
    )


def _by_id(result):
    return {c.subbrain_id: c for c in result.candidates}


def _selected(result) -> set[str]:
    return {c.subbrain_id for c in result.candidates if c.selected}


def _exact(cand_doc: dict, cfg, host_doc: dict | None = None) -> Fraction:
    return reference_distance_exact(host_doc if host_doc is not None else _host(), cand_doc, cfg.matching)


def _rel(doc: dict, cfg, terms=Q01_TERMS) -> float:
    return min(1.0, reference_relevance(list(terms), doc, cfg.matching)[0])


def _explain(world: World, query: str = Q01) -> dict[str, dict]:
    env = assert_ok(world.call("user_a", "match_explain", query=query, host_subbrain_id=world.sid("A")))
    return {
        c["subbrain_id"]: c
        for c in find_dicts(env, lambda d: "subbrain_id" in d and "relevance" in d and "selected" in d)
    }


def _publish_doc(world: World, user_id: str, doc: dict) -> str:
    if user_id not in world.tokens:
        world.add_user(user_id)
    env = assert_ok(world.import_doc(user_id, doc))
    assert_ok(
        world.call(
            user_id, "subbrain_set_visibility", subbrain_id=env["subbrain_id"], visibility="public",
            confirm_hash=env["content_hash"],
        )
    )
    return env["subbrain_id"]


# ===========================================================================
# The reference against the Oracle's own numbers (§9 v.7) and the fixture design (§6.1)
# ===========================================================================


def test_must_m5_v7_reference_reproduces_the_oracle_section9_numbers(cfg):
    """Self-check of the reference against §9 (v.7) "라벨·태그만 쓰면 A2 0.278, B·C 0.056, D·X 0", not the implementation."""
    m = cfg.matching
    h = reference_word_set(_host(), m)
    assert len(h) == 36
    assert saturation(m) == Fraction(1, 4), "§9 (v.6) distance_saturation 0.25"
    sims = {fid: reference_similarity(_host(), _doc(fid), m) for fid in FIXTURES}
    assert sims == {"A2": Fraction(10, 36), "B": Fraction(2, 36), "C": Fraction(2, 36), "D": 0, "X": 0}
    assert {fid: round(float(s), 3) for fid, s in sims.items()} == {"A2": 0.278, "B": 0.056, "C": 0.056, "D": 0.0, "X": 0.0}
    # §6.1: B and C carry 조립 and 오류 "그대로" as tags; that is all they share with A
    assert h & reference_word_set(_doc("B"), m) == h & reference_word_set(_doc("C"), m) == {"조립", "오류"}
    dist = {fid: _exact(_doc(fid), cfg) for fid in FIXTURES}
    assert dist == {"A2": 0, "B": Fraction(7, 9), "C": Fraction(7, 9), "D": 1, "X": 1}
    # MUST-M2 with these: B = C = 0.40 + 0.3 × 7/9 ≈ 0.633 > A2 0.56 (Q-01); far_distance 0.5 <= 7/9
    assert _rel(_doc("B"), cfg) == _rel(_doc("C"), cfg) == pytest.approx(0.40)
    assert 0.40 + m.distance_bonus * 7 / 9 > _rel(_doc("A2"), cfg) == pytest.approx(0.56)


def test_must_m5_v7_match_explain_reports_the_section9_distances(seeded: World):
    seeded.set_tier("user_a", Tier.PRO)
    cands = _explain(seeded)
    expect = {"A2": 0.0, "B": 7 / 9, "C": 7 / 9, "D": 1.0, "X": 1.0}
    for fid, d in expect.items():
        assert cands[seeded.sid(fid)]["distance"] == pytest.approx(d, abs=DISPLAY_TOL), fid
    assert cands[seeded.sid("B")]["distance"] == cands[seeded.sid("C")]["distance"], "2/36 and 2/36: one exact value"
    assert cands[seeded.sid("B")]["score"] == cands[seeded.sid("C")]["score"]
    assert cands[seeded.sid("B")]["score"] == pytest.approx(0.40 + 0.3 * 7 / 9, abs=DISPLAY_TOL)


# ===========================================================================
# Q-01 / Q-02 through canal_open (MUST-M2 with the v.7 distance)
# ===========================================================================


def test_must_m2_v7_canal_open_q01_expert_host_b_and_c_tie_above_a2(seeded: World):
    """Q-01: B and C tie on score (0.40 + 0.3 × 7/9) and on relevance (0.40) -> subbrain_id ascending decides; both
    rank above A2 (0.56 + 0)."""
    seeded.set_tier("user_a", Tier.EXPERT)  # 10 slots: nothing is truncated, so only the order can rank
    env = assert_ok(seeded.open_canal(query=Q01))
    b, c, a2 = seeded.sid("B"), seeded.sid("C"), seeded.sid("A2")
    assert member_ids(env) == [*sorted([b, c]), a2], f"MUST-M2: B = C (subbrain_id asc) > A2: {member_ids(env)}"
    assert env["truncated"] is False
    mb = {m["subbrain_id"]: m for m in env["members"]}
    assert mb[b]["distance"] == mb[c]["distance"] == pytest.approx(7 / 9, abs=DISPLAY_TOL)
    assert mb[b]["relevance"] == mb[c]["relevance"] == pytest.approx(0.40, abs=DISPLAY_TOL)
    assert mb[a2]["distance"] == pytest.approx(0.0, abs=1e-9)
    if "score" in mb[b]:
        assert mb[b]["score"] == mb[c]["score"] == pytest.approx(0.40 + 0.3 * 7 / 9, abs=DISPLAY_TOL)


def test_must_m2_v7_canal_open_q02_expert_host_keeps_a2_first(seeded: World):
    seeded.set_tier("user_a", Tier.EXPERT)
    env = assert_ok(seeded.open_canal(query=Q02))
    assert env["query_mode_used"] == "whole_host"
    ids = member_ids(env)
    assert ids and ids[0] == seeded.sid("A2"), f"A2 (relevance 1.00, distance 0) stays on top for Q-02: {ids}"
    assert {seeded.sid("B"), seeded.sid("C")} <= set(ids)
    assert seeded.sid("D") not in ids and seeded.sid("X") not in ids


# ===========================================================================
# Padding immunity (MUST-M5 "후보가 호스트와 겹치지 않는 낱말을 아무리 덧붙여도 거리는 변하지 않는다"; §9 M5-PAD-1)
# ===========================================================================


def test_must_m5_v7_filler_and_safe_words_are_what_the_tests_assume(cfg):
    """Self-check: filler words are not host words and touch no query term (so relevance cannot move); the safe host
    words are host words that touch no query term."""
    m = cfg.matching
    h = reference_word_set(_host(), m)
    tokenize_one = lambda w: reference_word_set(nodes_doc("t", ["d"], [{"label": w, "tags": []}]), m)  # noqa: E731
    for w in (FILLER_REPEATED, *FILLERS):
        assert tokenize_one(w) == {w}, w
        assert w not in h, w
        assert not [t for t in ALL_QUERY_TERMS if t in w or w in t], w
    assert len(set(FILLERS)) == len(FILLERS) >= 60
    for w in SAFE_HOST_WORDS:
        assert tokenize_one(w) == {w} and w in h, w
        assert not [t for t in ALL_QUERY_TERMS if t in w or w in t], w


# B plus three host words as tags: shares 5 of A's words -> 4/9 (a "near but not close" candidate)
B_NEAR = add_tags(load_brain("B")["document"], 0, list(SAFE_HOST_WORDS[:3]))
PAD_BASES = {"A2": load_brain("A2")["document"], "B": load_brain("B")["document"], "BN": B_NEAR, "J": DISJOINT}
PAD_SIZES = (1, 7, 40)


def _inline_pad(doc: dict, mode: str) -> dict:
    """Filler words appended to every existing node's label and tags (no new nodes)."""
    out = copy.deepcopy(doc)
    for i, n in enumerate(out["nodes"]):
        w = FILLER_REPEATED if mode == "repeated" else FILLERS[i % len(FILLERS)]
        n["label"] = f"{n['label']} {w} {w}"
        n["tags"] = [*(n.get("tags") or []), w]
    return out


@pytest.mark.parametrize("place", ["labels", "tags", "both", "inline"])
@pytest.mark.parametrize("mode", ["repeated", "distinct"])
def test_must_m5_v7_padding_with_foreign_words_never_changes_the_distance(cfg, mode, place):
    m = cfg.matching
    cands, expect = [], {}
    for name, base in PAD_BASES.items():
        cands.append(_v(base, f"sb_{name}"))
        variants = (
            {"i": _inline_pad(base, mode)}
            if place == "inline"
            else {str(n): pad_doc(base, n, mode=mode, place=place, tags_per_node=3) for n in PAD_SIZES}
        )
        for tag, doc in variants.items():
            sid = f"sb_{name}_pad{tag}"
            # self-check: the padding adds only foreign words, and neither the distance nor the relevance moves
            assert reference_word_set(doc, m) >= reference_word_set(base, m)
            assert not (reference_word_set(doc, m) - reference_word_set(base, m)) & reference_word_set(_host(), m)
            assert _exact(doc, cfg) == _exact(base, cfg), (name, tag)
            assert _rel(doc, cfg) == _rel(base, cfg), (name, tag)
            cands.append(_v(doc, sid))
            expect[sid] = f"sb_{name}"
    by_id = _by_id(_match(Q01, cands, cfg))
    for sid, base_sid in expect.items():
        got, base = by_id[sid], by_id[base_sid]
        assert got.distance == base.distance, f"{sid}: padding moved the distance {base.distance} -> {got.distance}"
        assert got.score == base.score, f"{sid}: padding moved the score {base.score} -> {got.score}"
    for name, base in PAD_BASES.items():
        assert by_id[f"sb_{name}"].distance == pytest.approx(float(_exact(base, cfg)), abs=DISPLAY_TOL), name


def _clones(mode_place: tuple[tuple[str, str], ...], n: int = 40) -> list[dict]:
    return [pad_doc(_doc("A2"), n, mode=mode, place=place, tags_per_node=3) for mode, place in mode_place]


CLONE_KINDS = (("repeated", "labels"), ("distinct", "tags"), ("repeated", "both"))


def test_must_m2_v7_padded_near_host_clones_cannot_buy_the_bonus_or_the_far_slot(cfg):
    """M5-PAD-1, pure: copies of A2 (relevance 0.56, distance 0) padded with 40 nodes of foreign words. Their ids sort
    before every fixture, so any tie goes their way — they must still lose to B and C on score (0.56 < 0.633)."""
    m = cfg.matching
    clones = _clones(CLONE_KINDS)
    for doc in clones:
        assert _exact(doc, cfg) == 0 and _rel(doc, cfg) == _rel(_doc("A2"), cfg), "self-check"
    clone_ids = [f"sb_0pad{i}" for i in range(1, len(clones) + 1)]
    cands = [*(fixture_version(f) for f in FIXTURES), *(_v(d, sid) for d, sid in zip(clones, clone_ids))]
    by_id = _by_id(_match(Q01, cands, cfg))
    for sid in clone_ids:
        assert by_id[sid].distance == by_id[fixture_sid("A2")].distance == pytest.approx(0.0, abs=1e-9), sid
        assert by_id[sid].score == by_id[fixture_sid("A2")].score, sid
    assert _selected(_match(Q01, cands, cfg, max_members=1)) == {fixture_sid("B")}, "B = C tie -> sb_B"
    assert _selected(_match(Q01, cands, cfg, max_members=2)) == {fixture_sid("B"), fixture_sid("C")}
    # third slot: A2 and the clones tie exactly (0.56, distance 0) -> subbrain_id ascending -> the first clone id
    assert _selected(_match(Q01, cands, cfg, max_members=3)) == {fixture_sid("B"), fixture_sid("C"), clone_ids[0]}
    assert 0.0 < m.far_distance, "the clones are at distance 0 (not far): the diversity guarantee cannot pull them in"


def test_must_m2_v7_canal_open_padded_near_host_clones_do_not_crowd_out_b_and_c(world: World):
    """M5-PAD-1 through the product: three users publish A2 clones padded with 40 nodes of foreign words (one repeated
    word in the labels, distinct words in the tags, one repeated word in both). A Free host (3 slots) still gets B and
    C; the clones stay at A2's distance (0) and tie with A2 for the third slot (subbrain_id ascending)."""
    world.seed()
    clones = {f"user_pad{i}": doc for i, doc in enumerate(_clones(CLONE_KINDS), 1)}
    clone_sids = {uid: _publish_doc(world, uid, doc) for uid, doc in clones.items()}
    b, c, a2 = world.sid("B"), world.sid("C"), world.sid("A2")
    near = sorted([a2, *clone_sids.values()])

    env = assert_ok(world.open_canal(query=Q01))
    ids = member_ids(env)
    assert {b, c} <= set(ids), f"padded clones crowded out B/C: {ids} (clones {sorted(clone_sids.values())})"
    assert set(ids) == {b, c, near[0]}, f"third slot: A2 and the clones tie -> lowest subbrain_id {near[0]}: {ids}"
    assert env["truncated"] is True

    world.set_tier("user_a", Tier.EXPERT)
    env = assert_ok(world.open_canal(query=Q01))
    assert member_ids(env) == [*sorted([b, c]), *near], member_ids(env)
    mb = {m["subbrain_id"]: m for m in env["members"]}
    assert mb[a2]["distance"] == pytest.approx(0.0, abs=1e-9)
    for uid, sid in clone_sids.items():
        assert mb[sid]["distance"] == mb[a2]["distance"], f"{uid}: padding moved the distance"
        if "score" in mb[sid]:
            assert mb[sid]["score"] == mb[a2]["score"], uid

    explain = _explain(world)
    for uid, sid in clone_sids.items():
        assert explain[sid]["distance"] == explain[a2]["distance"] == pytest.approx(0.0, abs=1e-9), uid
        assert explain[sid]["score"] == explain[a2]["score"], uid


# ===========================================================================
# Only node labels and tags count — on the candidate side and on the host side
# ===========================================================================


def _host_words_list(cfg) -> list[str]:
    return sorted(reference_word_set(_host(), cfg.matching))


def _chunks(words: list[str], size: int) -> list[str]:
    return [" ".join(words[i : i + size]) for i in range(0, len(words), size)]


def _stuff(doc: dict, words: list[str], where: str) -> dict:
    """Copy of `doc` with `words` placed only in `where` (within the model's field limits)."""
    out = copy.deepcopy(doc)
    nodes, edges = out["nodes"], out["edges"]
    if where in ("summary", "all"):
        for n, chunk in zip(nodes, _chunks(words, -(-len(words) // len(nodes)))):
            n["summary"] = f"{n.get('summary') or ''} {chunk}".strip()
    if where in ("type", "all"):
        chunks = _chunks(words, 3)
        while len(nodes) < len(chunks):
            nodes.append({"id": f"st-n{len(nodes)}", "label": "방법", "tags": []})  # stopword label: no word
        for n, chunk in zip(nodes, chunks):
            n["type"] = chunk
    if where in ("edge_summary", "edge_relation", "all"):
        chunks = _chunks(words, 3)
        for i, chunk in enumerate(chunks):
            e = {"id": f"st-e{i}", "source": nodes[i % len(nodes)]["id"], "target": nodes[(i + 1) % len(nodes)]["id"]}
            e["relation"] = chunk if where in ("edge_relation", "all") else "supports"
            if where in ("edge_summary", "all"):
                e["summary"] = chunk
            edges.append(e)
    if where in ("title", "all"):
        out["title"] = " ".join(words)
    if where in ("domains", "all"):
        out["domains"] = _chunks(words, -(-len(words) // 10))
    return out


OTHER_FIELDS = ["summary", "type", "edge_summary", "edge_relation", "title", "domains", "all"]


@pytest.mark.parametrize("where", OTHER_FIELDS)
def test_must_m5_v7_host_words_outside_labels_and_tags_never_count_for_the_candidate(cfg, where):
    """Every one of the host's 36 words, placed only in `where` of a candidate with no shared label/tag word: still
    distance exactly 1 ("요약, 노드 유형, 엣지, 제목, 신고한 분야(domains)는 쓰지 않는다")."""
    doc = _stuff(DISJOINT, _host_words_list(cfg), where)
    assert reference_word_set(doc, cfg.matching) == reference_word_set(DISJOINT, cfg.matching), "self-check"
    assert _exact(doc, cfg) == 1
    c = _by_id(_match(Q01, [_v(doc, "sb_F")], cfg))["sb_F"]
    assert c.distance == pytest.approx(1.0, abs=1e-9), f"host words only in the {where} moved the distance"


def _bare(doc: dict) -> dict:
    """Only node ids, labels and tags left: no summaries, no types, no edges, a neutral title and domain."""
    return {
        "title": "메모",
        "domains": ["기타"],
        "nodes": [{"id": n["id"], "label": n["label"], "tags": list(n.get("tags") or [])} for n in doc["nodes"]],
        "edges": [],
    }


def test_must_m5_v7_removing_summaries_types_edges_title_and_domains_keeps_the_candidate_distance(cfg):
    cands = [*(fixture_version(f) for f in FIXTURES), *(_v(_bare(_doc(f)), f"sb_{f}_bare") for f in FIXTURES)]
    by_id = _by_id(_match(Q01, cands, cfg))
    for fid in FIXTURES:
        assert _exact(_bare(_doc(fid)), cfg) == _exact(_doc(fid), cfg), "self-check"
        assert by_id[f"sb_{fid}_bare"].distance == by_id[fixture_sid(fid)].distance, fid
        assert by_id[fixture_sid(fid)].distance == pytest.approx(float(_exact(_doc(fid), cfg)), abs=DISPLAY_TOL), fid


def _host_variants(cfg) -> dict[str, dict]:
    """Host A with its non-label/tag fields emptied, or stuffed with the candidates' label/tag words."""
    m = cfg.matching
    stuffed = copy.deepcopy(_host())
    b_words = sorted(reference_word_set(_doc("B"), m))
    c_words = sorted(reference_word_set(_doc("C"), m))
    d_words = sorted(reference_word_set(_doc("D"), m))
    x_words = sorted(reference_word_set(_doc("X"), m))
    stuffed = _stuff(stuffed, b_words, "summary")
    stuffed = _stuff(stuffed, c_words, "edge_summary")
    stuffed = _stuff(stuffed, d_words, "title")
    stuffed = _stuff(stuffed, x_words, "domains")
    stuffed = _stuff(stuffed, sorted(reference_word_set(_doc("A2"), m) - reference_word_set(_host(), m)), "type")
    return {"bare": _bare(_host()), "stuffed": stuffed}


@pytest.mark.parametrize("variant", ["bare", "stuffed"])
def test_must_m5_v7_host_summaries_types_edges_title_and_domains_do_not_count(cfg, variant):
    """The host side reads labels and tags only, too: emptying the host's other fields, or filling them with every
    candidate's words, leaves every distance exactly where it was."""
    host_doc = _host_variants(cfg)[variant]
    assert reference_word_set(host_doc, cfg.matching) == reference_word_set(_host(), cfg.matching), "self-check"
    host = version_from_doc(host_doc, subbrain_id=fixture_sid("A"), owner_id="user_a")
    moved = _by_id(_match(Q01, [fixture_version(f) for f in FIXTURES], cfg, host=host))
    plain = _by_id(_match(Q01, [fixture_version(f) for f in FIXTURES], cfg))
    for fid in FIXTURES:
        sid = fixture_sid(fid)
        assert moved[sid].distance == plain[sid].distance, f"{fid}: host {variant} moved {plain[sid].distance}"
        assert moved[sid].distance == pytest.approx(float(_exact(_doc(fid), cfg, host_doc)), abs=DISPLAY_TOL), fid


# ===========================================================================
# Sets, not counts
# ===========================================================================


def test_must_m5_v7_repeating_shared_words_does_not_change_the_distance(cfg):
    """B repeats the two words it shares with A (조립, 오류) in 30 more nodes: still 2 of 36 -> 7/9."""
    rep = copy.deepcopy(_doc("B"))
    rep["nodes"] += [{"id": f"r-n{i}", "label": "조립 오류 조립", "tags": ["조립", "오류"]} for i in range(30)]
    assert _exact(rep, cfg) == _exact(_doc("B"), cfg) == Fraction(7, 9) and _rel(rep, cfg) == _rel(_doc("B"), cfg)
    by_id = _by_id(_match(Q01, [fixture_version("B"), _v(rep, "sb_B_rep")], cfg))
    assert by_id["sb_B_rep"].distance == by_id[fixture_sid("B")].distance
    assert by_id["sb_B_rep"].score == by_id[fixture_sid("B")].score


def test_must_m5_v7_repetition_in_the_host_does_not_change_the_distance(cfg):
    """Host A with every node three times (new ids): the same 36 words, the same distances."""
    tripled = copy.deepcopy(_host())
    tripled["nodes"] = [dict(n, id=f"{n['id']}-{k}") for k in range(3) for n in _host()["nodes"]]
    tripled["edges"] = []
    host = version_from_doc(tripled, subbrain_id=fixture_sid("A"), owner_id="user_a")
    moved = _by_id(_match(Q01, [fixture_version(f) for f in FIXTURES], cfg, host=host))
    plain = _by_id(_match(Q01, [fixture_version(f) for f in FIXTURES], cfg))
    for fid in FIXTURES:
        assert moved[fixture_sid(fid)].distance == plain[fixture_sid(fid)].distance, fid


# ===========================================================================
# Adding host words lowers the distance (and only host words do)
# ===========================================================================


@pytest.mark.parametrize("place", ["tag", "label"])
def test_must_m5_v7_each_added_host_word_lowers_the_distance_until_saturation(cfg, place):
    """B shares 2 of A's 36 words; adding k more gives 1 − min(1, (2 + k)/9): 7/9, 6/9, ..., 0 at k = 7, then 0."""
    docs = {}
    for k in range(0, 10):
        words = list(SAFE_HOST_WORDS[:k])
        if place == "tag":
            doc = add_tags(_doc("B"), 0, words)
        else:
            doc = copy.deepcopy(_doc("B"))
            doc["nodes"] += [{"id": f"h-n{i}", "label": w, "tags": []} for i, w in enumerate(words)]
        assert _exact(doc, cfg) == distance_for_shared(2 + k, 36, cfg.matching), k
        assert _rel(doc, cfg) == _rel(_doc("B"), cfg), "self-check: safe words are no Q-01 term"
        docs[k] = doc
    by_id = _by_id(_match(Q01, [_v(doc, f"sb_k{k}") for k, doc in docs.items()], cfg))
    got = [by_id[f"sb_k{k}"].distance for k in range(10)]
    for k in range(10):
        assert got[k] == pytest.approx(float(distance_for_shared(2 + k, 36, cfg.matching)), abs=DISPLAY_TOL), (k, got)
    assert all(got[k] > got[k + 1] for k in range(7)), f"each host word must lower the distance: {got}"
    assert got[7] == got[8] == got[9] == pytest.approx(0.0, abs=1e-9), f"saturated at 9 of 36: {got}"


# ===========================================================================
# Empty host word set -> distance 1
# ===========================================================================


def _empty_host_with_all_words_elsewhere(cfg) -> dict:
    """Host labels and tags are stopwords/punctuation only; all of A's words sit in its summaries, types, edges,
    title and domains."""
    words = _host_words_list(cfg)
    base = {
        "title": "메모",
        "domains": ["기타"],
        "nodes": [
            {"id": f"e-n{i}", "label": label, "tags": tags}
            for i, (label, tags) in enumerate([("평가", ["방법"]), ("—", []), ("아이디어 방법", ["두뇌", "…"]), ("검토", [])])
        ],
        "edges": [],
    }
    return _stuff(base, words, "all")


def test_must_m5_v7_empty_host_word_set_gives_distance_one(cfg):
    """MUST-M5 "H가 비면 거리 1": even a copy of A and A2 (which share every one of those words in their labels and
    tags) are at distance exactly 1 from such a host."""
    host_doc = _empty_host_with_all_words_elsewhere(cfg)
    assert reference_word_set(host_doc, cfg.matching) == frozenset(), "self-check"
    host = version_from_doc(host_doc, subbrain_id="sb_A", owner_id="user_a")
    cands = [*(fixture_version(f) for f in FIXTURES), _v(_host(), "sb_Acopy", "user_h")]
    by_id = _by_id(_match(Q01, cands, cfg, host=host))
    for sid, c in by_id.items():
        assert c.distance == pytest.approx(1.0, abs=1e-9), f"{sid}: {c.distance} from a host without label/tag words"
    assert _exact(_host(), cfg, host_doc) == 1


# ===========================================================================
# Exact (rational) arithmetic
# ===========================================================================

_HOST_POOL = tuple(a + b for a in ("가람", "나래", "다솜", "라온", "마루", "바다", "아라", "하늘") for b in ("터", "뫼", "골", "재", "벌", "섬"))


def _words_doc(words: list[str], prefix: str) -> dict:
    """One word per label, every second word as a tag of the node before."""
    nodes = [{"label": words[i], "tags": list(words[i + 1 : i + 2])} for i in range(0, len(words), 2)]
    return nodes_doc("메모", ["기타"], nodes, prefix)


def _coverage_case(n: int, k: int, cfg) -> tuple[dict, dict]:
    """(host, candidate) with |H| = n and |H ∩ C| = k; n = 36 means fixture A."""
    if n == 36:
        host = _host()
        shared = list(SAFE_HOST_WORDS[:k])
    else:
        host = _words_doc(list(_HOST_POOL[:n]), "h")
        shared = list(_HOST_POOL[:k])
    cand = _words_doc([*shared, *FILLERS[:3]], "c")
    m = cfg.matching
    assert len(reference_word_set(host, m)) == n and len(reference_word_set(host, m) & reference_word_set(cand, m)) == k
    return host, cand


EQUAL_RATIO_GROUPS = {
    "1/3 = 2/6 (saturated, 0)": [(3, 1), (6, 2)],
    "1/9 = 2/18 = 4/36 (5/9)": [(9, 1), (18, 2), (36, 4)],
    "1/6 = 2/12 = 6/36 (1/3)": [(6, 1), (12, 2), (36, 6)],
    "1/7 = 2/14 = 3/21 (3/7)": [(7, 1), (14, 2), (21, 3)],
    "1/10 = 2/20 = 3/30 (3/5)": [(10, 1), (20, 2), (30, 3)],
}


@pytest.mark.parametrize("group", sorted(EQUAL_RATIO_GROUPS))
def test_must_m5_v7_rationally_equal_coverages_give_exactly_equal_distances(cfg, group):
    """MUST-M5 "계산은 정확해야 하고(유리수)": coverages that are the same rational number give the same distance —
    the same reported value, not merely close ones — whatever |H| is."""
    m = cfg.matching
    got, exact = [], set()
    for n, k in EQUAL_RATIO_GROUPS[group]:
        host_doc, cand_doc = _coverage_case(n, k, cfg)
        exact.add(reference_distance_exact(host_doc, cand_doc, m))
        host = version_from_doc(host_doc, subbrain_id=f"sb_H{n}", owner_id=f"user_h{n}")
        got.append(_by_id(_match(Q01, [_v(cand_doc, "sb_c")], cfg, host=host))["sb_c"].distance)
    assert len(exact) == 1, f"self-check: {exact}"
    (value,) = exact
    assert all(g == pytest.approx(float(value), abs=DISPLAY_TOL) for g in got), (group, got, value)
    assert len(set(got)) == 1, f"{group}: rationally equal coverages reported different distances {got}"


def test_must_m5_v7_same_number_of_shared_words_is_a_full_tie_broken_by_subbrain_id(cfg):
    """Two candidates share different host words but the same number (2 + 4 of 36 -> 1/3) and have the same relevance
    (조립, 오류 tags: 0.40): exactly the same distance and score, so MUST-M2 falls through to subbrain_id ascending."""
    base = nodes_doc("메모", ["기타"], [{"label": "자두빛 규칙", "tags": ["조립", "오류"]}], "p")
    p_doc = add_tags(base, 0, list(SAFE_HOST_WORDS[0:4]))
    q_doc = add_tags(base, 0, list(SAFE_HOST_WORDS[4:8]))
    assert _exact(p_doc, cfg) == _exact(q_doc, cfg) == Fraction(1, 3)
    assert _rel(p_doc, cfg) == _rel(q_doc, cfg) == pytest.approx(0.40)
    for first, second in (("sb_P", "sb_Q"), ("sb_Q", "sb_P")):
        docs = {"sb_P": p_doc, "sb_Q": q_doc}
        cands = [_v(docs[first], "sb_0" + first[-1]), _v(docs[second], "sb_1" + second[-1])]
        result = _match(Q01, cands, cfg, max_members=1)
        by_id = _by_id(result)
        a, b = by_id["sb_0" + first[-1]], by_id["sb_1" + second[-1]]
        assert a.distance == b.distance and a.score == b.score, (a, b)
        assert _selected(result) == {a.subbrain_id}, f"full tie -> subbrain_id ascending: {_selected(result)}"


def test_must_m5_v7_distance_does_not_depend_on_the_query_or_relevance(cfg):
    """The distance is a property of host and candidate content (D and X are below τ and still carry one)."""
    cands = [fixture_version(f) for f in FIXTURES]
    seen = {q: {c.subbrain_id: c.distance for c in _match(q, cands, cfg).candidates} for q in (Q01, Q02, Q03)}
    assert seen[Q01] == seen[Q02] == seen[Q03]
    for fid in FIXTURES:
        assert seen[Q01][fixture_sid(fid)] == pytest.approx(reference_distance(_host(), _doc(fid), cfg.matching), abs=DISPLAY_TOL)
