"""MUST-M5 and MUST-M2 (Oracle v.6, owner decision "거리는 내용으로 계산 (신고 분야 대신)").

ORACLE §5.4 MUST-M5: distance between host and candidate = 1 − min(1, similarity ÷ distance_saturation (config)).
similarity = cosine of the word-frequency vectors of the two subbrains' node labels, tags and summaries (host: the
version the canal uses; candidate: its public version). Words come from textnorm.tokenize (josa and stopwords removed).
Declared domains and the title are not used. No words -> distance 1. Deterministic. Forbidden: changing the declared
domains changes the distance; a differently spelled domain name makes the distance 1.

ORACLE §5.4 MUST-M2 (v.6): score = relevance + distance_bonus × distance (MUST-M5 distance); order by score, then
relevance, then subbrain_id; ranking and the τ comparison use UNROUNDED values, rounding is for display only; then the
diversity guarantee: if an eligible candidate with distance >= far_distance (config) exists and none is selected, the
best one is put in. Q-01 ranks B·C above A2; Q-02 keeps A2 first.

§9 (v.6): distance_saturation 0.25, far_distance 0.5; fixture cosine A–A2 0.34; Q-01 B·C distances ≈ 0.75·0.81;
rounding twice flipped the score order and the relevance tie-break (adversarial review M2-ROUND-1).

Expected values come from the independent reference in _v7.py (v.6: _v6.py; never from the implementation). Reported
relevance, distance and score may be rounded for display, so reported values are compared with DISPLAY_TOL; rankings are
observed through selection under max_members and — for canal_open, where nothing is truncated — the order of
`members`. A distance is observed through MatchCandidate.distance (models.py: "content distance from host (v.6
MUST-M5)") and through match_explain / canal_open; no helper function name is assumed.

Updated for Oracle v.7 (2026-10-06.7). MUST-M5 now reads: "유사도 = 호스트 낱말 중 후보도 가진 낱말의 비율 = |H ∩ C| ÷
|H|. H와 C는 ... 노드 라벨과 태그에서 textnorm.tokenize(조사 제거, 불용어 제거)로 만든 서로 다른 낱말의 집합이다. 요약,
노드 유형, 엣지, 제목, 신고한 분야(domains)는 쓰지 않는다 ... H가 비면 거리 1. 계산은 정확해야 하고(유리수)". The cosine
reference (_v6.py) is replaced by _v7.py, and only what v.7 contradicts changed here: summaries no longer count
(test_must_m5_other_fields_do_not_count), word frequency no longer counts (test_must_m5_word_repetition_does_not_count),
removing summaries no longer moves the distance, B and C now tie at 7/9 (§9 v.7 "B·C 0.056") so the Q-01 order is
B, C (subbrain_id ascending), A2, and the constructed candidates were rebuilt so that their stated near/far roles hold
under v.7. The §9 v.6 numbers (cosine A–A2 0.34, B ≈ 0.75, C ≈ 0.81) are withdrawn; the v.7 numbers and the new v.7
properties (padding, repetition, exactness, other fields) are pinned in test_oracle_v7_matching.py.
"""

from __future__ import annotations

import copy

import pytest

from opencanal.models import QueryMode, Tier
from opencanal.textnorm import tokenize

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
    FAR_020,
    FAR_060,
    NEAR_060,
    NO_WORDS,
    add_tags,
    m2_order_key,
    nodes_doc,
    reference_distance,
    reference_score,
    reference_word_set,
    with_meta,
)
from .test_oracle_v4_matching import AT_TAU_DOC, WEAK_DOCS
from .test_oracle_v5_matching import CLOSE_050, CLOSE_060, QK

DEFAULT = "relevance_with_distance_bonus"
DISPLAY_TOL = 1e-3  # reported values may be rounded for display (MUST-M2 v.6); same tolerance as the v.5 tests
FIXTURES = ("A2", "B", "C", "D", "X")


def _doc(fid: str) -> dict:
    return load_brain(fid)["document"]


def _host() -> dict:
    return _doc("A")


def _v(doc: dict, sid: str, owner: str | None = None):
    return version_from_doc(doc, subbrain_id=sid, owner_id=owner or f"user_{sid.lower()}")


def _match(query, candidates, cfg, *, host=None, max_members=3, strategy=None, query_mode=QueryMode.AUTO, mcfg=None):
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


def _fixtures():
    return [fixture_version(f) for f in FIXTURES]


def _by_id(result):
    return {c.subbrain_id: c for c in result.candidates}


def _selected(result) -> set[str]:
    return {c.subbrain_id for c in result.candidates if c.selected}


def _dist(cand_doc: dict, cfg, host_doc: dict | None = None) -> float:
    return reference_distance(host_doc if host_doc is not None else _host(), cand_doc, cfg.matching)


def _terms(query: str, cfg) -> list[str]:
    m = cfg.matching
    return tokenize(query, josa_suffixes=m.josa_suffixes, min_stem=m.josa_min_stem_length, stopwords=m.stopwords)


# ===========================================================================
# MUST-M5 — the reference and the config values
# ===========================================================================


def test_must_m5_config_values_from_section9(cfg):
    m = cfg.matching
    assert m.distance_saturation == pytest.approx(0.25), "§9 (v.6) planner proposal"
    assert m.far_distance == pytest.approx(0.5), "§9 (v.6) planner proposal"
    assert m.distance_bonus == pytest.approx(0.3), "§9 (v.5)"
    assert m.strategy == DEFAULT


# The v.6 self-check against the §9 (v.6) numbers (cosine A–A2 0.34, B ≈ 0.75, C ≈ 0.81, D just below 1) is withdrawn by
# v.7; its successor against the §9 (v.7) numbers (A2 0.278, B·C 0.056, D·X 0) is
# test_oracle_v7_matching.py::test_must_m5_v7_reference_reproduces_the_oracle_section9_numbers.


# ===========================================================================
# MUST-M5 — pure (matching.match -> MatchCandidate.distance)
# ===========================================================================


@pytest.mark.parametrize("query", [Q01, Q02, Q03], ids=["Q-01", "Q-02", "Q-03"])
def test_must_m5_fixture_distances_from_host_a(cfg, query):
    """The distance does not depend on the query, on relevance, or on τ (D and X are below τ and still get one)."""
    result = _match(query, _fixtures(), cfg)
    by_id = _by_id(result)
    for fid in FIXTURES:
        assert by_id[fixture_sid(fid)].distance == pytest.approx(_dist(_doc(fid), cfg), abs=DISPLAY_TOL), fid
        assert 0.0 <= by_id[fixture_sid(fid)].distance <= 1.0
    assert by_id[fixture_sid("A2")].distance == pytest.approx(0.0, abs=1e-9), "A2: 10/36 >= 0.25 (§9 v.7 0.278)"
    assert by_id[fixture_sid("X")].distance == pytest.approx(1.0, abs=1e-9), "X: no word in common"
    # v.7 (§9 v.7 "B·C 0.056", "D·X 0"): B and C share the same two words with A -> exactly the same distance (v.6
    # cosine had B < C); D shares no label/tag word -> 1.
    assert by_id[fixture_sid("B")].distance == by_id[fixture_sid("C")].distance < by_id[fixture_sid("D")].distance
    assert by_id[fixture_sid("D")].distance == pytest.approx(1.0, abs=1e-9)


def test_must_m5_candidate_declared_domains_and_title_do_not_change_the_distance(cfg):
    """Forbidden (MUST-M5): changing the declared domains changes the distance. B claims the host's field and title."""
    b = _doc("B")
    variants = {
        "sb_B1": with_meta(b, domains=_host()["domains"]),
        "sb_B2": with_meta(b, title=_host()["title"]),
        "sb_B3": with_meta(b, title=_host()["title"], domains=_host()["domains"]),
        "sb_B4": with_meta(b, domains=["세포생물학", "동네 빵집 마케팅"]),
    }
    cands = [fixture_version("B"), *(_v(doc, sid) for sid, doc in variants.items())]
    by_id = _by_id(_match(Q01, cands, cfg, max_members=10))
    base = by_id[fixture_sid("B")]
    assert base.distance == pytest.approx(_dist(b, cfg), abs=DISPLAY_TOL)
    for sid in variants:
        assert by_id[sid].distance == pytest.approx(base.distance, abs=1e-12), f"{sid}: declared metadata moved it"


def test_must_m5_host_declared_domains_and_title_do_not_change_the_distance(cfg):
    host_doc = with_meta(_host(), title=_doc("B")["title"], domains=["게임 디자인"])  # claims B's field
    host = version_from_doc(host_doc, subbrain_id=fixture_sid("A"), owner_id="user_a")
    moved = _by_id(_match(Q01, _fixtures(), cfg, host=host))
    plain = _by_id(_match(Q01, _fixtures(), cfg))
    for fid in FIXTURES:
        sid = fixture_sid(fid)
        assert moved[sid].distance == pytest.approx(plain[sid].distance, abs=1e-12), fid
        assert moved[sid].distance == pytest.approx(_dist(_doc(fid), cfg, host_doc), abs=DISPLAY_TOL), fid
    assert moved[fixture_sid("B")].distance > cfg.matching.far_distance, "B is still far by content"


@pytest.mark.parametrize(
    "domains",
    [["건축학", "BIM 설계"], ["architecture"], ["건 축", "B.I.M."], ["목조 주택"]],
    ids=["건축학", "english", "spaced", "unrelated_name"],
)
def test_must_m5_differently_spelled_domain_names_do_not_make_the_distance_one(cfg, domains):
    """Forbidden (MUST-M5): "표기만 다른 분야명 때문에 거리 1". A2 is content-close to A whatever it calls its field."""
    a2 = _v(with_meta(_doc("A2"), domains=domains), "sb_A2x", "user_e")
    c = _by_id(_match(Q01, [a2], cfg))["sb_A2x"]
    assert c.distance == pytest.approx(0.0, abs=1e-9), f"domains {domains} moved A2 to {c.distance}"


def test_must_m5_identical_content_is_distance_zero(cfg):
    """A copy of the host's nodes under another user's title and domains (and with the nodes in another order)."""
    same = with_meta(_host(), title="퍼즐 게임 블록 설계 원칙", domains=["게임 디자인"])
    shuffled = copy.deepcopy(same)
    shuffled["nodes"] = list(reversed(shuffled["nodes"]))
    assert reference_word_set(shuffled, cfg.matching) == reference_word_set(_host(), cfg.matching)
    by_id = _by_id(_match(Q01, [_v(same, "sb_same"), _v(shuffled, "sb_shuf")], cfg))
    assert by_id["sb_same"].distance == pytest.approx(0.0, abs=1e-9)
    assert by_id["sb_shuf"].distance == pytest.approx(0.0, abs=1e-9)


def test_must_m5_disjoint_content_is_distance_one_even_with_the_hosts_title_and_domains(cfg):
    assert DISJOINT["title"] == _host()["title"] and DISJOINT["domains"] == _host()["domains"]
    assert _dist(DISJOINT, cfg) == 1.0 and _dist(_doc("X"), cfg) == 1.0
    by_id = _by_id(_match(Q01, [_v(DISJOINT, "sb_J"), fixture_version("X")], cfg))
    assert by_id["sb_J"].distance == pytest.approx(1.0, abs=1e-9), "same title and domains, no common word"
    assert by_id[fixture_sid("X")].distance == pytest.approx(1.0, abs=1e-9)


def test_must_m5_no_words_is_distance_one(cfg):
    """MUST-M5 "H가 비면 거리 1" (v.7; v.6 "낱말이 없으면 거리 1"): labels and tags that tokenize to nothing (title,
    domains and an edge summary carry the host's words, and must not count)."""
    assert reference_word_set(NO_WORDS, cfg.matching) == frozenset()
    cand = _by_id(_match(Q01, [_v(NO_WORDS, "sb_O")], cfg))["sb_O"]
    assert cand.distance == pytest.approx(1.0, abs=1e-9)
    # a host without words: every candidate is at distance 1, even a copy of A
    host = version_from_doc(NO_WORDS, subbrain_id="sb_A", owner_id="user_a")
    copy_a = _v(with_meta(_host(), title="복사본"), "sb_Acopy", "user_h")
    by_id = _by_id(_match(Q01, [*_fixtures(), copy_a], cfg, host=host))
    for sid, c in by_id.items():
        assert c.distance == pytest.approx(1.0, abs=1e-9), f"{sid}: {c.distance} from a host without words"


# Base for the field tests: no word in common with A. One host word (유닛) is then placed in exactly one place.
_FIELD_BASE = nodes_doc(
    "하천 정비 메모",
    ["토목"],
    [
        {"label": "하천 둑 보강", "type": "공정", "tags": ["제방", "하천"], "summary": "흙을 다지고 돌망태를 올린다."},
        {"label": "물막이 판", "type": "자재", "tags": ["둑"], "summary": "비가 오기 전에 세워 둔다."},
    ],
    "q",
)


def _field_variant(where: str) -> dict:
    doc = copy.deepcopy(_FIELD_BASE)
    n = doc["nodes"][0]
    if where == "label":
        n["label"] = "유닛 하천 둑 보강"
    elif where == "tag":
        n["tags"] = [*n["tags"], "유닛"]
    elif where == "summary":
        n["summary"] = "유닛 흙을 다지고 돌망태를 올린다."
    elif where == "type":
        n["type"] = "유닛"
    elif where == "edge_summary":
        doc["edges"][0]["summary"] = "유닛 설치 순서"
    elif where == "title":
        doc["title"] = "유닛 설치 순서"
    elif where == "domains":
        doc["domains"] = ["유닛", "설치"]
    return doc


@pytest.mark.parametrize("where", ["label", "tag"])
def test_must_m5_node_labels_and_tags_count(cfg, where):
    """v.7 (MUST-M5 "노드 라벨과 태그"): labels and tags count; the v.6 "summary" case moved to the next test."""
    doc = _field_variant(where)
    ref = _dist(doc, cfg)
    assert ref < 1.0 and _dist(_FIELD_BASE, cfg) == 1.0, "self-check"
    c = _by_id(_match(Q01, [_v(doc, "sb_F")], cfg))["sb_F"]
    assert c.distance == pytest.approx(ref, abs=DISPLAY_TOL), f"a host word in the node {where} must count"
    assert c.distance < 1.0


@pytest.mark.parametrize("where", ["summary", "type", "edge_summary", "title", "domains"])
def test_must_m5_other_fields_do_not_count(cfg, where):
    """MUST-M5 (v.7) lists node labels and tags only; "요약, 노드 유형, 엣지, 제목, 신고한 분야(domains)는 쓰지 않는다".
    (v.6 counted summaries; v.7 moved "summary" here.)"""
    doc = _field_variant(where)
    assert _dist(doc, cfg) == 1.0, "self-check"
    c = _by_id(_match(Q01, [_v(doc, "sb_F")], cfg))["sb_F"]
    assert c.distance == pytest.approx(1.0, abs=1e-9), f"a host word only in the {where} moved the distance"


def test_must_m5_words_come_from_textnorm_tokenize(cfg):
    """Josa are stripped and stopwords dropped (textnorm.tokenize with the config lists): particles do not change the
    distance, and stopwords shared with the host do not make two subbrains similar."""
    bare = nodes_doc("메모", ["토목"], [{"label": "유닛 순서", "tags": ["현장"], "summary": "공장 위치 하천 둑"}], "p")
    josa = nodes_doc("메모", ["토목"], [{"label": "유닛을 순서는", "tags": ["현장에서"], "summary": "공장의 위치를 하천과 둑"}], "p")
    assert reference_word_set(bare, cfg.matching) == reference_word_set(josa, cfg.matching)
    # v.7: the non-stopwords moved from the summaries to the tags, so the host's word set is not empty (summaries no
    # longer count, and an empty H would give distance 1 for a different reason).
    stop_host = nodes_doc("메모", ["x"], [{"label": "아이디어 방법", "tags": ["평가", "제빵", "반죽"], "summary": "제빵 반죽"}], "h")
    stop_cand = nodes_doc("메모", ["y"], [{"label": "아이디어 방법", "tags": ["평가", "하천", "둑"], "summary": "하천 둑"}], "s")
    assert reference_word_set(stop_host, cfg.matching) == {"제빵", "반죽"}
    assert reference_distance(stop_host, stop_cand, cfg.matching) == 1.0
    by_id = _by_id(_match(Q01, [_v(bare, "sb_bare"), _v(josa, "sb_josa")], cfg))
    assert by_id["sb_bare"].distance == pytest.approx(_dist(bare, cfg), abs=DISPLAY_TOL)
    assert by_id["sb_josa"].distance == pytest.approx(by_id["sb_bare"].distance, abs=1e-12)
    host = version_from_doc(stop_host, subbrain_id="sb_A", owner_id="user_a")
    c = _by_id(_match(Q01, [_v(stop_cand, "sb_S")], cfg, host=host))["sb_S"]
    assert c.distance == pytest.approx(1.0, abs=1e-9), "shared stopwords only -> nothing in common"


def test_must_m5_word_repetition_does_not_count(cfg):
    """v.7 (MUST-M5 "서로 다른 낱말의 집합"): the same set of words with different counts gives the SAME distance.
    (v.6, a frequency vector, pinned the opposite: test_must_m5_word_frequency_counts_not_just_presence.)"""
    once = nodes_doc("메모", ["토목"], [{"label": "유닛 하천", "tags": ["둑"], "summary": "제방 보강"}], "w")
    many = nodes_doc(
        "메모",
        ["토목"],
        [
            {"label": "유닛 하천", "tags": ["둑"], "summary": "제방 보강"},
            {"label": "유닛 둑", "tags": ["유닛"], "summary": "유닛 제방"},
        ],
        "w",
    )
    assert reference_word_set(once, cfg.matching) == reference_word_set(many, cfg.matching)
    d_once, d_many = _dist(once, cfg), _dist(many, cfg)
    assert d_once == d_many == 8 / 9, "self-check: one of A's words (유닛), counts do not matter"
    by_id = _by_id(_match(Q01, [_v(once, "sb_once"), _v(many, "sb_many")], cfg))
    assert by_id["sb_once"].distance == pytest.approx(d_once, abs=DISPLAY_TOL)
    assert by_id["sb_many"].distance == by_id["sb_once"].distance, "repeating a word moved the distance"


def test_must_m5_content_change_changes_the_distance(cfg):
    b = _doc("B")
    closer = copy.deepcopy(b)
    closer["nodes"].append(
        {"id": "b-n11", "label": "유닛 설치 순서", "tags": ["유닛", "공장", "운송"], "summary": "현장 설치 위치를 정한다."}
    )
    no_summaries = copy.deepcopy(b)
    for n in no_summaries["nodes"]:
        n.pop("summary", None)
    refs = {"sb_B": _dist(b, cfg), "sb_Bc": _dist(closer, cfg), "sb_Bn": _dist(no_summaries, cfg)}
    # v.7 (MUST-M5 "요약 ... 쓰지 않는다"): removing the summaries no longer moves the distance (v.6: it did).
    assert refs["sb_Bc"] < refs["sb_B"] - 0.1 and refs["sb_Bn"] == refs["sb_B"], "self-check"
    cands = [_v(b, "sb_B", "user_b"), _v(closer, "sb_Bc", "user_b2"), _v(no_summaries, "sb_Bn", "user_b3")]
    by_id = _by_id(_match(Q01, cands, cfg, max_members=10))
    for sid, ref in refs.items():
        assert by_id[sid].distance == pytest.approx(ref, abs=DISPLAY_TOL), sid
    assert by_id["sb_Bc"].distance < by_id["sb_B"].distance
    assert by_id["sb_Bn"].distance == by_id["sb_B"].distance, "summaries do not count (v.7)"


def test_must_m5_distance_is_deterministic(cfg):
    cands = [*_fixtures(), _v(NEAR_060, "sb_N"), _v(FAR_060, "sb_M"), _v(_doc("B"), "sb_Bdup", "user_bdup")]
    first = _match(Q01, cands, cfg, max_members=3)
    again = _match(Q01, cands, cfg, max_members=3)
    rev = _match(Q01, list(reversed(cands)), cfg, max_members=3)
    assert first.model_dump(mode="json") == again.model_dump(mode="json") == rev.model_dump(mode="json")
    by_id = _by_id(first)
    assert by_id["sb_Bdup"].distance == by_id[fixture_sid("B")].distance, "same content, other id/owner"


# ===========================================================================
# MUST-M5 — through Service.dispatch
# ===========================================================================


def _explain(world: World, query: str = Q01) -> dict[str, dict]:
    env = assert_ok(world.call("user_a", "match_explain", query=query, host_subbrain_id=world.sid("A")))
    return {
        c["subbrain_id"]: c
        for c in find_dicts(env, lambda d: "subbrain_id" in d and "relevance" in d and "selected" in d)
    }


def test_must_m5_match_explain_distance_equals_the_reference(seeded: World):
    seeded.set_tier("user_a", Tier.PRO)
    cands = _explain(seeded)
    for fid in FIXTURES:
        c = cands[seeded.sid(fid)]
        ref = _dist(_doc(fid), seeded.cfg)
        assert c["distance"] == pytest.approx(ref, abs=DISPLAY_TOL), f"{fid}: {c['distance']} vs reference {ref:.6f}"
    assert cands[seeded.sid("A2")]["distance"] == pytest.approx(0.0, abs=1e-9)
    assert cands[seeded.sid("X")]["distance"] == pytest.approx(1.0, abs=1e-9)


def test_must_m5_canal_open_members_carry_the_content_distance(seeded: World):
    env = assert_ok(seeded.open_canal(query=Q01))
    by_sid = {seeded.sid(f): f for f in FIXTURES}
    assert env["members"]
    for m in env["members"]:
        fid = by_sid[m["subbrain_id"]]
        assert m["distance"] == pytest.approx(_dist(_doc(fid), seeded.cfg), abs=DISPLAY_TOL), fid


def test_must_m5_candidate_distance_uses_its_public_version(world: World):
    """MUST-M5 "후보는 공개 버전": B's unpublished v2 (a copy of A's content, distance 0) does not count until published."""
    world.seed(("A", "A2", "B", "C"))
    world.set_tier("user_a", Tier.PRO)
    v2_doc = with_meta(_host(), title=_doc("B")["title"], domains=_doc("B")["domains"])
    v2 = assert_ok(world.import_doc("user_b", v2_doc, subbrain_id=world.sid("B")))
    assert v2["version"] == 2
    before = _explain(world)[world.sid("B")]
    assert before["version"] == 1
    assert before["distance"] == pytest.approx(_dist(_doc("B"), world.cfg), abs=DISPLAY_TOL)
    assert_ok(
        world.call(
            "user_b",
            "subbrain_set_visibility",
            subbrain_id=world.sid("B"),
            visibility="public",
            version=2,
            confirm_hash=v2["content_hash"],
        )
    )
    after = _explain(world)[world.sid("B")]
    assert after["version"] == 2
    assert after["distance"] == pytest.approx(0.0, abs=1e-9), "published v2 has the host's content"


def test_must_m5_distance_is_measured_from_the_host_version_the_canal_uses(world: World):
    """MUST-M5 "호스트는 커널에 쓰는 버전": A has a published v1 and a newer, unpublished v2 holding B's content. The test
    does not decide which version a canal uses; whichever the canal records, member distances follow its content."""
    world.seed(("A", "A2", "B", "C"))
    world.set_tier("user_a", Tier.EXPERT)
    v2_doc = with_meta(_doc("B"), title=_host()["title"], domains=_host()["domains"])
    assert_ok(world.import_doc("user_a", v2_doc, subbrain_id=world.sid("A")))
    env = assert_ok(world.open_canal(query=Q01))
    canal = assert_ok(world.call("user_a", "canal_get", canal_id=env["canal_id"]))
    versions = {d["host_version"] for d in find_dicts([env, canal], lambda d: isinstance(d.get("host_version"), int))}
    assert len(versions) == 1, f"the canal must record one host version (Canal.host_version): {versions}"
    host_version = versions.pop()
    assert host_version in (1, 2)
    host_doc = _host() if host_version == 1 else v2_doc
    by_sid = {world.sid(f): f for f in ("A2", "B", "C")}
    assert env["members"]
    for m in env["members"]:
        fid = by_sid[m["subbrain_id"]]
        ref = reference_distance(host_doc, _doc(fid), world.cfg.matching)
        assert m["distance"] == pytest.approx(ref, abs=DISPLAY_TOL), f"{fid} vs host v{host_version}: {m['distance']}"


# ===========================================================================
# MUST-M2 (v.6) — scores use the MUST-M5 distance
# ===========================================================================


def test_must_m2_v6_q01_scores_and_order_follow_the_content_distance(cfg):
    m = cfg.matching
    ref = {}
    for fid in FIXTURES:
        rel = min(1.0, reference_relevance(Q01_TERMS, _doc(fid), m)[0])
        ref[fid] = (rel, _dist(_doc(fid), cfg))
    order = sorted((f for f in FIXTURES if ref[f][0] >= m.tau), key=lambda f: m2_order_key(fixture_sid(f), *ref[f], m))
    # v.7: B and C tie (7/9, 0.40) -> subbrain_id ascending (v.6 cosine: C, B, A2)
    assert order == ["B", "C", "A2"], f"self-check of the reference order: {order}"
    by_id = _by_id(_match(Q01, _fixtures(), cfg))
    for fid in FIXTURES:
        assert by_id[fixture_sid(fid)].score == pytest.approx(reference_score(*ref[fid], m), abs=DISPLAY_TOL), fid
    for k in (1, 2, 3):
        got = _selected(_match(Q01, _fixtures(), cfg, max_members=k))
        assert got == {fixture_sid(f) for f in order[:k]}, f"max_members={k}: {got}"


# ---------------------------------------------------------------------------
# Unrounded comparisons (§9 v.6 "반올림 전 값으로 비교", M2-ROUND-1)
#
# Rounding is monotone, so on its own it cannot reverse a strict order; what it does is create a false tie that a
# tie-break then settles the wrong way. Each case below puts two candidates within 5e-5 of each other in score, so that
# both "round the score to 4 decimals" and "round relevance/distance to 4 decimals, then the score again" turn them
# into a tie, and the true (unrounded) order says the opposite of the tie-break. The bonus is set through a copy of
# the matching config (as the v.5 bonus test does); config/ is not touched.
# ---------------------------------------------------------------------------


def _r4(x: float) -> float:
    return round(x, 4)


def _double_rounded(rel: float, dist: float, bonus: float) -> float:
    return _r4(_r4(rel) + bonus * _r4(dist))


def test_must_m2_v6_rounding_must_not_create_a_tie_that_relevance_breaks_the_wrong_way(cfg):
    """P (0.40, far) truly outscores Q (0.50, close) by 3e-5; rounded they tie and Q's higher relevance would win.

    F (0.60, far) is always selected first, so the diversity guarantee is met either way and cannot hide the error.
    """
    m = cfg.matching
    host = _host()
    p_doc, q_doc, f_doc = _doc("B"), CLOSE_050, FAR_060
    rel = {k: reference_relevance(_terms(QK, cfg), d, m)[0] for k, d in (("P", p_doc), ("Q", q_doc), ("F", f_doc))}
    dist = {k: reference_distance(host, d, m) for k, d in (("P", p_doc), ("Q", q_doc), ("F", f_doc))}
    assert (rel["P"], rel["Q"], rel["F"]) == (pytest.approx(0.40), pytest.approx(0.50), pytest.approx(0.60))
    assert dist["Q"] == 0.0 and dist["P"] >= m.far_distance and dist["F"] >= m.far_distance
    eps = 3e-5
    bonus = (rel["Q"] - rel["P"] + eps) / dist["P"]  # score P = score Q + eps
    s = {k: rel[k] + bonus * dist[k] for k in rel}
    assert s["F"] > s["P"] > s["Q"] and s["P"] - s["Q"] == pytest.approx(eps, abs=1e-9)
    assert _r4(s["P"]) == _r4(s["Q"]), "self-check: rounded scores tie"
    assert _double_rounded(rel["P"], dist["P"], bonus) <= _double_rounded(rel["Q"], dist["Q"], bonus), "self-check"
    mcfg = m.model_copy(update={"distance_bonus": bonus})
    cands = [_v(q_doc, "sb_0Q"), _v(p_doc, "sb_P"), _v(f_doc, "sb_F")]
    result = _match(QK, cands, cfg, max_members=2, mcfg=mcfg)
    assert _selected(result) == {"sb_F", "sb_P"}, (
        f"P outscores Q by {eps} before rounding; selected {_selected(result)} "
        f"(scores {[(c.subbrain_id, c.score) for c in result.candidates]})"
    )
    assert result.truncated is True


# v.7: B and C are at the same distance (7/9), so the closer candidate is B plus one of A's words (유닛) as a tag:
# relevance under Q-01 unchanged (0.40), 3 shared words -> distance 2/3. It keeps the id sb_B, which sorts first.
B_PLUS1 = add_tags(load_brain("B")["document"], 0, ["유닛"])


def _fixtures_b_plus1():
    return [
        fixture_version("A2"),
        _v(B_PLUS1, fixture_sid("B"), "user_b"),
        *(fixture_version(f) for f in ("C", "D", "X")),
    ]


def test_must_m2_v6_rounding_must_not_hide_a_small_distance_difference_at_equal_relevance(cfg):
    """Q-01: B' (B plus one host word) and C have equal relevance; with a tiny bonus their scores differ by 3e-5 (C
    farther). Rounded, the full tie would fall to subbrain_id (sb_B first); unrounded, C ranks above B' ("관련도가 같으면
    먼 분야가 위다"). v.7 (MUST-M5): B itself now ties C exactly (both 7/9), so B' replaces B here."""
    m = cfg.matching
    d_b, d_c = _dist(B_PLUS1, cfg), _dist(_doc("C"), cfg)
    assert (d_b, d_c) == (2 / 3, 7 / 9) and d_b >= m.far_distance, "self-check (v.7: 3 and 2 of A's 36 words)"
    rel_b, rel_c = reference_relevance(Q01_TERMS, B_PLUS1, m)[0], reference_relevance(Q01_TERMS, _doc("C"), m)[0]
    assert rel_b == rel_c == pytest.approx(0.40), "self-check: the added tag is no Q-01 term"
    bonus = 3e-5 / (d_c - d_b)
    s_b, s_c = 0.40 + bonus * d_b, 0.40 + bonus * d_c
    assert s_c - s_b == pytest.approx(3e-5, abs=1e-9)
    assert _r4(s_b) == _r4(s_c) and _double_rounded(0.40, d_b, bonus) == _double_rounded(0.40, d_c, bonus), "self-check"
    assert fixture_sid("B") < fixture_sid("C")
    mcfg = m.model_copy(update={"distance_bonus": bonus})
    two = _match(Q01, _fixtures_b_plus1(), cfg, max_members=2, mcfg=mcfg)
    assert _selected(two) == {fixture_sid("A2"), fixture_sid("C")}, f"selected {_selected(two)}"
    # one slot: A2 (0.56) is close, so the guarantee swaps in the BEST far candidate — C, not B'
    one = _match(Q01, _fixtures_b_plus1(), cfg, max_members=1, mcfg=mcfg)
    assert _selected(one) == {fixture_sid("C")}, f"selected {_selected(one)}"
    only_bc = _match(Q01, [_v(B_PLUS1, fixture_sid("B"), "user_b"), fixture_version("C")], cfg, max_members=1, mcfg=mcfg)
    assert _selected(only_bc) == {fixture_sid("C")}


# Three-term query: relevance = sum / 3, so 0.8 / 3 = 0.26666… and 1.0 / 3 = 0.33333… are not 4-decimal numbers.
Q3 = "조립 오류 공차"
L_DOC = nodes_doc("치수 기록", ["토목"], [{"label": "공차 기록", "tags": ["기록"], "summary": "값을 적는다."}], "l")
T_DOC = nodes_doc("치수 표", ["토목"], [{"label": "치수 표", "tags": ["공차"], "summary": "허용 범위를 적는다."}], "s")


@pytest.mark.parametrize(
    "tau, expect",
    [(0.26667, {"sb_T3"}), (0.33333, {"sb_T3"}), (0.2666, {"sb_L3", "sb_T3"}), (0.33334, set())],
    ids=["L_just_below", "T_just_above", "both_above", "both_below"],
)
def test_must_m2_v6_tau_gate_uses_unrounded_relevance(cfg, tau, expect):
    """τ is compared with the unrounded relevance (v.6). With τ = 0.26667, L (0.26666…) is not eligible although it
    displays as 0.2667; with τ = 0.33333, T (0.33333…) is eligible although it displays as 0.3333. τ is set through a
    copy of the matching config to probe the comparison; config/ is not touched."""
    m = cfg.matching
    terms = _terms(Q3, cfg)
    assert terms == ["조립", "오류", "공차"]
    rel_l, rel_t = reference_relevance(terms, L_DOC, m)[0], reference_relevance(terms, T_DOC, m)[0]
    assert rel_l == pytest.approx(0.8 / 3) and rel_t == pytest.approx(1.0 / 3)
    assert rel_l < 0.26667 <= _r4(rel_l) and _r4(rel_t) < 0.33333 <= rel_t, "self-check"
    mcfg = m.model_copy(update={"tau": tau})
    result = _match(Q3, [_v(L_DOC, "sb_L3"), _v(T_DOC, "sb_T3")], cfg, max_members=10, mcfg=mcfg)
    assert _selected(result) == expect, f"τ={tau}: selected {_selected(result)}"
    for c in result.candidates:
        if c.subbrain_id not in expect:
            assert c.selected is False and c.score == 0.0, f"below-τ candidate {c.subbrain_id} must score 0: {c}"


# ---------------------------------------------------------------------------
# Diversity guarantee with far_distance (v.6)
# ---------------------------------------------------------------------------


def _h():
    return fixture_version("A", subbrain_id="sb_H", owner_id="user_h")  # the host's content, another user


def test_must_m2_v6_a_selected_member_at_far_distance_satisfies_the_guarantee(cfg):
    """M (0.60, content distance 2/3 >= far_distance) is selected next to H: nothing is swapped, although M declares
    the host's own domains and T (0.20, 7/9) is also far. (v.7 values; v.6 cosine: ≈ 0.56 both.)"""
    host = _host()
    assert cfg.matching.far_distance <= _dist(FAR_060, cfg) < 1.0 and FAR_060["domains"] == host["domains"]
    assert _dist(AT_TAU_DOC, cfg) >= cfg.matching.far_distance
    cands = [_h(), _v(FAR_060, "sb_M"), _v(AT_TAU_DOC, "sb_T")]
    assert _selected(_match(QK, cands, cfg, max_members=2)) == {"sb_H", "sb_M"}


def test_must_m2_v6_a_member_just_below_far_distance_does_not_satisfy_the_guarantee(cfg):
    """N (0.60, 4/9 < far_distance) is selected by score next to H; the best eligible far candidate T (0.20, 7/9)
    replaces N (the lowest-ranked member). far_distance is read from config. (v.7 values; NEAR_060 rebuilt with its host
    words in tags, since v.7 no longer reads summaries; v.6 cosine: N ≈ 0.40, T ≈ 0.56.)"""
    m = cfg.matching
    d_n, d_t = _dist(NEAR_060, cfg), _dist(AT_TAU_DOC, cfg)
    assert 0.0 < d_n < m.far_distance <= d_t < 1.0, "self-check"
    cands = [_h(), _v(NEAR_060, "sb_N"), _v(AT_TAU_DOC, "sb_T")]
    assert _selected(_match(QK, cands, cfg, max_members=2)) == {"sb_H", "sb_T"}
    assert _selected(_match(QK, cands, cfg, max_members=1)) == {"sb_T"}
    assert _selected(_match(QK, cands, cfg, max_members=3)) == {"sb_H", "sb_N", "sb_T"}
    lower = m.model_copy(update={"far_distance": 0.35})  # N (4/9) now counts as far
    assert _selected(_match(QK, cands, cfg, max_members=2, mcfg=lower)) == {"sb_H", "sb_N"}
    assert d_t < 0.8, "self-check: T (7/9) is below the raised threshold"
    higher = m.model_copy(update={"far_distance": 0.8})  # no eligible candidate is far any more (v.7: T is 7/9 > 0.6)
    assert _selected(_match(QK, cands, cfg, max_members=2, mcfg=higher)) == {"sb_H", "sb_N"}


def test_must_m2_v6_the_best_far_candidate_is_swapped_in_never_a_below_tau_one(cfg):
    """H (1.00, d0) and Z (0.60, d0) win on score. Far eligible: T1 (0.20, 7/9 -> ≈0.433) and T2 (0.20, 8/9 ->
    ≈0.467); far below τ: W_TWO (0.18, d1 -> would-be 0.48). T2 is the best by MUST-M2 order (its id sorts after T1).
    (v.7 values; v.6 cosine: T1 ≈ 0.56, T2 ≈ 0.63.)"""
    m = cfg.matching
    s1 = reference_score(0.20, _dist(AT_TAU_DOC, cfg), m)
    s2 = reference_score(0.20, _dist(FAR_020, cfg), m)
    assert s2 > s1 and _dist(CLOSE_060, cfg) == 0.0, "self-check"
    assert reference_relevance(_terms(QK, cfg), WEAK_DOCS["W_TWO"], m)[0] < m.tau and _dist(WEAK_DOCS["W_TWO"], cfg) == 1.0
    cands = [_h(), _v(CLOSE_060, "sb_Z"), _v(AT_TAU_DOC, "sb_T1"), _v(FAR_020, "sb_T2"), _v(WEAK_DOCS["W_TWO"], "sb_W")]
    assert _selected(_match(QK, cands, cfg, max_members=2)) == {"sb_H", "sb_T2"}
    assert _selected(_match(QK, cands, cfg, max_members=1)) == {"sb_T2"}
    assert _selected(_match(QK, cands, cfg, max_members=4)) == {"sb_H", "sb_Z", "sb_T1", "sb_T2"}


def test_must_m2_v6_a_declared_far_field_does_not_make_a_close_member_far(cfg):
    """A2's content declared as another field is still close (distance 0); with one slot, only below-τ far candidates
    besides it, nothing is swapped in."""
    a2_game = _v(with_meta(_doc("A2"), domains=["게임 디자인"]), "sb_A2g", "user_e")
    weak = [_v(WEAK_DOCS[n], f"sb_{n}") for n in sorted(WEAK_DOCS)]
    result = _match(Q01, [a2_game, *weak], cfg, max_members=1)
    assert _selected(result) == {"sb_A2g"}
    assert _by_id(result)["sb_A2g"].distance == pytest.approx(0.0, abs=1e-9)


# ===========================================================================
# MUST-M2 (v.6) — through Service.dispatch
# ===========================================================================


def _reference_q01_order(cfg, sid=fixture_sid) -> list[str]:
    """MUST-M2 order of the Q-01 eligible fixtures; `sid` maps a fixture to the subbrain_id the tie-break sees."""
    m = cfg.matching
    ref = {f: (min(1.0, reference_relevance(Q01_TERMS, _doc(f), m)[0]), _dist(_doc(f), cfg)) for f in FIXTURES}
    return sorted((f for f in FIXTURES if ref[f][0] >= m.tau), key=lambda f: m2_order_key(sid(f), *ref[f], m))


def test_must_m2_v6_canal_open_q01_expert_host_orders_members_by_score(seeded: World):
    seeded.set_tier("user_a", Tier.EXPERT)  # 10 slots: nothing is truncated, so only the order can rank
    env = assert_ok(seeded.open_canal(query=Q01))
    order = _reference_q01_order(seeded.cfg, seeded.sid)
    # v.7 (MUST-M5): B and C tie (0.40 + 0.3 × 7/9 ≈ 0.633), so their order is the server ids' ascending order
    # (MUST-M2 "그다음 subbrain_id 오름차순"); A2 (0.56) is last. (v.6 cosine: C ≈ 0.644 > B ≈ 0.626.)
    assert set(order[:2]) == {"B", "C"} and order[2] == "A2" and len(order) == 3
    assert member_ids(env) == [seeded.sid(f) for f in order], "MUST-M2: B = C (≈0.633, subbrain_id asc) > A2 (0.56)"
    assert env["truncated"] is False
    for mbr in env["members"]:
        if "score" in mbr:
            assert mbr["score"] == pytest.approx(
                mbr["relevance"] + seeded.cfg.matching.distance_bonus * mbr["distance"], abs=DISPLAY_TOL
            )


def test_must_m2_v6_canal_open_q02_expert_host_keeps_a2_first(seeded: World):
    seeded.set_tier("user_a", Tier.EXPERT)
    env = assert_ok(seeded.open_canal(query=Q02))
    assert env["query_mode_used"] == "whole_host"
    ids = member_ids(env)
    assert ids and ids[0] == seeded.sid("A2"), f"A2 stays on top for Q-02: {ids}"
    assert seeded.sid("D") not in ids and seeded.sid("X") not in ids


def test_must_m2_v6_match_explain_scores_use_the_content_distance(seeded: World):
    seeded.set_tier("user_a", Tier.PRO)
    cands = _explain(seeded)
    m = seeded.cfg.matching
    for fid in FIXTURES:
        rel = min(1.0, reference_relevance(Q01_TERMS, _doc(fid), m)[0])
        expected = reference_score(rel, _dist(_doc(fid), seeded.cfg), m)
        assert cands[seeded.sid(fid)]["score"] == pytest.approx(expected, abs=DISPLAY_TOL), fid
