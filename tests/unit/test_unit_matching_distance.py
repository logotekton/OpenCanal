"""Unit tests for the content distance of ORACLE v.7 MUST-M5 (opencanal.matching, Builder M).

similarity = |H ∩ C| / |H|, H and C the sets of distinct words (textnorm.tokenize: josa stripped, stopwords removed)
of the host's and the candidate's node labels and tags; distance = 1 - min(1, similarity / distance_saturation).
Summaries, node types, edges, the title and declared domains never move it. Empty H -> 1.0. Exact (rational) and
deterministic. Words the candidate adds that the host lacks never change it (adversarial review M5-PAD-1).
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from opencanal import matching
from opencanal.config import MatchingConfig, load_config
from opencanal.matching import NO_CONTENT_DISTANCE, content_distance, display_value, match, match_with_ranking
from opencanal.models import QueryMode, SubbrainDocument, SubbrainEdge, SubbrainNode, SubbrainVersion, Visibility
from opencanal.textnorm import tokenize

REPO = Path(__file__).resolve().parents[2]
BRAINS = REPO / "fixtures" / "brains"
Q01 = "모듈러 건축의 현장 조립 오류를 줄일 아이디어"
Q02 = "내 두뇌를 평가해줘"


@pytest.fixture(scope="module")
def cfg() -> MatchingConfig:
    return load_config().matching


def _node(
    node_id: str, label: str, tags: tuple[str, ...] = (), summary: str | None = None, type: str | None = None
) -> SubbrainNode:
    return SubbrainNode(id=node_id, label=label, tags=list(tags), summary=summary, type=type)


def _sv(
    subbrain_id: str,
    nodes: list[SubbrainNode],
    *,
    owner_id: str | None = None,
    domains: tuple[str, ...] = ("z",),
    title: str = "untitled",
    edges: list[SubbrainEdge] | None = None,
    visibility: Visibility = Visibility.PUBLIC,
) -> SubbrainVersion:
    return SubbrainVersion(
        subbrain_id=subbrain_id,
        version=1,
        owner_id=owner_id or f"user_{subbrain_id}",
        owner_display="x",
        visibility=visibility,
        is_published_version=True,
        content_hash="0" * 64,
        created_at="2026-10-06T00:00:00Z",
        document=SubbrainDocument(title=title, domains=list(domains), nodes=nodes, edges=edges or []),
    )


def _fixture(fid: str) -> SubbrainVersion:
    brain = json.loads((BRAINS / f"{fid}.json").read_text("utf-8"))
    return SubbrainVersion(
        subbrain_id=f"sb_{fid}",
        version=1,
        owner_id=brain["owner"]["user_id"],
        owner_display=brain["owner"]["display_name"],
        visibility=Visibility(brain["visibility"]),
        is_published_version=True,
        content_hash="0" * 64,
        created_at="2026-10-06T00:00:00Z",
        document=SubbrainDocument.model_validate(brain["document"]),
    )


def _labels(words: list[str], prefix: str = "n") -> list[SubbrainNode]:
    """Nodes whose labels hold `words`, 16 per label."""
    return [_node(f"{prefix}{i}", " ".join(words[i : i + 16])) for i in range(0, len(words), 16)]


def _exact_distance(host: SubbrainVersion, cand: SubbrainVersion, cfg: MatchingConfig) -> Fraction:
    return matching._distance_between(matching._content_words(host, cfg), matching._content_words(cand, cfg), cfg)


# An independent reference for MUST-M5, written from the manifest text.
def _ref_words(sv: SubbrainVersion, cfg: MatchingConfig) -> set[str]:
    words: set[str] = set()
    for node in sv.document.nodes:
        for text in [node.label, *node.tags]:
            words.update(
                tokenize(text, josa_suffixes=cfg.josa_suffixes, min_stem=cfg.josa_min_stem_length, stopwords=cfg.stopwords)
            )
    return words


def _ref_similarity(host: SubbrainVersion, cand: SubbrainVersion, cfg: MatchingConfig) -> Fraction:
    h, c = _ref_words(host, cfg), _ref_words(cand, cfg)
    return Fraction(len(h & c), len(h)) if h else Fraction(0)


def _ref_distance(host: SubbrainVersion, cand: SubbrainVersion, cfg: MatchingConfig) -> Fraction:
    if not _ref_words(host, cfg):
        return Fraction(1)
    return 1 - min(Fraction(1), _ref_similarity(host, cand, cfg) / Fraction(str(cfg.distance_saturation)))


# ---------------------------------------------------------------------------
# The fixture brains: ORACLE §9 (v.7) numbers
# ---------------------------------------------------------------------------


def test_fixture_similarities_and_distances_match_the_manifest(cfg):
    a = _fixture("A")
    assert len(_ref_words(a, cfg)) == 36, "self-check: host A has 36 distinct label/tag words"
    # §9 (v.7): labels and tags only -> A2 0.278, B·C 0.056, D·X 0
    expected = {
        "A2": (Fraction(5, 18), Fraction(0)),  # 0.278 >= 0.25: saturated
        "B": (Fraction(1, 18), Fraction(7, 9)),  # 오류, 조립
        "C": (Fraction(1, 18), Fraction(7, 9)),
        "D": (Fraction(0), Fraction(1)),
        "X": (Fraction(0), Fraction(1)),
        "P": (Fraction(5, 36), Fraction(4, 9)),
    }
    for fid, (similarity, distance) in expected.items():
        assert _ref_similarity(a, _fixture(fid), cfg) == similarity, fid
        exact = _exact_distance(a, _fixture(fid), cfg)
        assert type(exact) is Fraction and exact == distance, fid
        assert content_distance(a, _fixture(fid), cfg) == float(distance), fid
    assert round(float(Fraction(5, 18)), 3) == 0.278 and round(float(Fraction(1, 18)), 3) == 0.056


@pytest.mark.parametrize("host_id", ["A", "A2", "B", "C", "D", "P", "X"])
def test_fixture_distances_match_the_reference(cfg, host_id):
    host = _fixture(host_id)
    for fid in ("A", "A2", "B", "C", "D", "P", "X"):
        assert _exact_distance(host, _fixture(fid), cfg) == _ref_distance(host, _fixture(fid), cfg), (host_id, fid)


def test_fixture_q01_ranks_b_and_c_above_a2(cfg):
    # §9: with the defaults, Q-01 ranks B·C (distance 7/9) above A2 (distance 0). B and C now tie on relevance,
    # distance and score (0.4 + 0.3 · 7/9 = 19/30), so subbrain_id puts B first.
    candidates = [_fixture(f) for f in ("A2", "B", "C", "D", "X")]
    for pool in (candidates, candidates[::-1]):
        ranked = match_with_ranking(Q01, _fixture("A"), pool, max_members=3, cfg=cfg)
        got = [(c.subbrain_id, c.relevance, c.distance, c.score, c.selected) for c in ranked.ranking]
        assert got == [
            ("sb_B", 0.4, 0.7778, 0.6333, True),
            ("sb_C", 0.4, 0.7778, 0.6333, True),
            ("sb_A2", 0.56, 0.0, 0.56, True),
            ("sb_D", 0.0, 1.0, 0.0, False),
            ("sb_X", 0.0, 1.0, 0.0, False),
        ]
    assert Fraction(2, 5) + Fraction(3, 10) * Fraction(7, 9) == Fraction(19, 30)


def test_fixture_q02_keeps_a2_on_top(cfg):
    candidates = [_fixture(f) for f in ("A2", "B", "C", "D", "X")]
    ranked = match_with_ranking(Q02, _fixture("A"), candidates, max_members=3, cfg=cfg)
    assert ranked.result.query_mode_used is QueryMode.WHOLE_HOST
    # B and C are equally far (7/9); C is more relevant to the host's terms, so it ranks above B
    assert [(c.subbrain_id, c.relevance, c.distance, c.score) for c in ranked.ranking[:3]] == [
        ("sb_A2", 1.0, 0.0, 1.0),
        ("sb_C", 0.45, 0.7778, 0.6833),
        ("sb_B", 0.4, 0.7778, 0.6333),
    ]
    assert {c.subbrain_id for c in ranked.result.selected} == {"sb_A2", "sb_B", "sb_C"}


def test_fixture_q01_one_slot_diversity_uses_far_distance(cfg):
    # relevance_plus_diversity, one slot: A2 (0.56, distance 0) is first by relevance; B (7/9 >= 0.5) is the best
    # far candidate in relevance order (ties C on relevance, wins on subbrain_id) and is swapped in.
    candidates = [_fixture(f) for f in ("A2", "B", "C", "D", "X")]
    result = match(Q01, _fixture("A"), candidates, max_members=1, cfg=cfg, strategy="relevance_plus_diversity")
    assert [c.subbrain_id for c in result.selected] == ["sb_B"]
    assert {c.subbrain_id: c.reason for c in result.candidates}["sb_A2"] == matching.REASON_DISPLACED


# ---------------------------------------------------------------------------
# Hand-computed values: a host of 24 distinct label words, so distance = 1 - min(1, shared / 6)
# ---------------------------------------------------------------------------

HOST_WORDS = ["공차", "접합부", "양중", "인양", *[f"h{i:02d}" for i in range(20)]]
HOST = _sv("H", _labels(HOST_WORDS), domains=("건축", "BIM"), title="모듈러 건축")


def _cand(shared: int, fillers: int = 0, **kw) -> SubbrainVersion:
    """The first `shared` HOST words and `fillers` words the host lacks, all as labels."""
    words = HOST_WORDS[:shared] + [f"f{i}" for i in range(fillers)]
    return _sv("C", _labels(words or ["f-only"]), **kw)


@pytest.mark.parametrize(
    ("shared", "fillers", "distance"),
    [
        (0, 3, Fraction(1)),  # nothing in common
        (1, 0, Fraction(5, 6)),  # similarity 1/24
        (2, 50, Fraction(2, 3)),  # 1/12
        (3, 7, Fraction(1, 2)),  # 1/8
        (4, 0, Fraction(1, 3)),  # 1/6
        (5, 100, Fraction(1, 6)),  # 5/24
        (6, 0, Fraction(0)),  # 1/4: exactly at saturation
        (7, 9, Fraction(0)),  # past saturation
        (24, 0, Fraction(0)),  # every host word
    ],
)
def test_distance_hand_computed(cfg, shared, fillers, distance):
    cand = _cand(shared, fillers)
    assert _exact_distance(HOST, cand, cfg) == distance
    assert content_distance(HOST, cand, cfg) == float(distance)


def test_distance_is_exact_and_unrounded(cfg):
    cand = _cand(4)  # similarity 1/6 -> 1 - 2/3
    exact = _exact_distance(HOST, cand, cfg)
    assert type(exact) is Fraction and exact == Fraction(1, 3)
    d = content_distance(HOST, cand, cfg)
    assert d == 1 / 3  # the float nearest to 1/3, not 1 - (1/6) / 0.25 = 0.33333333333333337
    assert 1 - (1 / 6) / 0.25 != 1 / 3  # self-check: what float arithmetic would give
    assert d != display_value(d)  # the function does not round; MatchCandidate shows 0.3333
    assert display_value(d) == 0.3333


def test_distance_saturation_is_read_from_config(cfg):
    quarter = _cand(6)  # similarity 1/4
    assert content_distance(HOST, quarter, cfg) == 0.0
    assert content_distance(HOST, quarter, cfg.model_copy(update={"distance_saturation": 0.5})) == 0.5
    assert content_distance(HOST, quarter, cfg.model_copy(update={"distance_saturation": 1.0})) == 0.75
    # a non-dyadic saturation is read as the decimal it is written as: 1 - (1/4) / (3/10) = 1/6 exactly
    assert _exact_distance(HOST, quarter, cfg.model_copy(update={"distance_saturation": 0.3})) == Fraction(1, 6)
    # a non-positive saturation saturates on any shared word, and still gives 1.0 when nothing is shared
    for sat in (0.0, -0.5):
        bad = cfg.model_copy(update={"distance_saturation": sat})
        assert content_distance(HOST, _cand(1), bad) == 0.0
        assert content_distance(HOST, _cand(0, 3), bad) == 1.0


def test_distance_is_relative_to_the_host(cfg):
    # H has 24 words; C is two of them. From H, C covers 1/12 of the host (2/3). From C, H covers all of C (0).
    small = _cand(2)
    assert content_distance(HOST, small, cfg) == float(Fraction(2, 3))
    assert content_distance(small, HOST, cfg) == 0.0


def test_distance_to_itself_is_zero(cfg):
    for sv in (HOST, _cand(4), _fixture("A"), _fixture("D")):
        assert content_distance(sv, sv, cfg) == 0.0


def test_more_shared_host_words_never_increase_the_distance(cfg):
    distances = [_exact_distance(HOST, _cand(k), cfg) for k in range(len(HOST_WORDS) + 1)]
    assert distances == sorted(distances, reverse=True)
    assert distances[0] == 1 and distances[-1] == 0


# ---------------------------------------------------------------------------
# Padding (adversarial review M5-PAD-1): words the host lacks never change the distance
# ---------------------------------------------------------------------------


def test_padding_with_words_the_host_lacks_never_changes_the_distance(cfg):
    base = _sv("C", [_node("n0", "공차 접합부", ("f-x",))])  # similarity 2/24 -> 2/3
    assert _exact_distance(HOST, base, cfg) == Fraction(2, 3)
    pad = [f"pad{i}" for i in range(300)]
    padded = [
        # many new words in labels and tags
        _sv("C", base.document.nodes + _labels(pad, "p") + [_node("t", "x9", tuple(pad[:20]))]),
        # one unrelated word repeated on many nodes (the v.6 cosine attack)
        _sv("C", base.document.nodes + [_node(f"r{i}", "filler", ("filler",)) for i in range(500)]),
        # the shared words themselves repeated
        _sv("C", base.document.nodes * 1 + [_node(f"s{i}", "공차 접합부") for i in range(200)]),
    ]
    for cand in padded:
        assert _exact_distance(HOST, cand, cfg) == Fraction(2, 3)


def test_padding_cannot_push_a_close_candidate_past_far_distance(cfg):
    """v.6 cosine: repeating one unrelated word drove a close candidate's distance toward 1, earning the bonus and
    the diversity slot. v.7: the padded copy keeps its distance, so it can neither outscore the honest copy nor be
    treated as far."""
    honest = _sv("sb_honest", [_node("n0", " ".join(HOST_WORDS[:6]), ("kw", "ab"))])  # distance 0, relevance 1
    stuffed = _sv("sb_stuffed", honest.document.nodes + [_node(f"r{i}", "filler", ("filler",)) for i in range(400)])
    far = _sv("sb_far", [_node("n0", "x1 x2", ("kw",))])  # distance 1, relevance 1/2: score 0.5 + 0.3 = 0.8
    assert _exact_distance(HOST, stuffed, cfg) == _exact_distance(HOST, honest, cfg) == 0
    for strategy in ("relevance_with_distance_bonus", "relevance_plus_diversity"):
        for close in (honest, stuffed):
            result = match("kw ab", HOST, [far, close], max_members=1, cfg=cfg, strategy=strategy)
            assert {c.subbrain_id: (c.distance, c.score) for c in result.candidates} == {
                close.subbrain_id: (0.0, 1.0),  # padding earns no bonus
                "sb_far": (1.0, 0.8),
            }
            # the close candidate is not far, so the honest far one takes the diversity slot either way
            assert {c.subbrain_id: c.reason for c in result.candidates} == {
                close.subbrain_id: matching.REASON_DISPLACED,
                "sb_far": matching.REASON_DIVERSITY,
            }


def test_padding_property_on_random_documents(cfg):
    rng = random.Random(7)
    vocab = [f"w{i}" for i in range(30)]
    for _ in range(200):
        host = _sv("H", [_node(f"h{i}", " ".join(rng.sample(vocab, rng.randint(1, 5))), tuple(rng.sample(vocab, 2)))
                         for i in range(rng.randint(1, 4))])
        host_words = matching._content_words(host, cfg)
        cand_nodes = [_node(f"c{i}", " ".join(rng.sample(vocab, rng.randint(1, 5)))) for i in range(rng.randint(1, 4))]
        cand = _sv("C", cand_nodes)
        before = _exact_distance(host, cand, cfg)
        lacking = [w for w in vocab if w not in host_words] + [f"x{i}" for i in range(10)]
        extra = rng.sample(lacking, rng.randint(1, len(lacking)))
        padded = _sv("C", cand_nodes + _labels(extra, "p") + [_node("t", "x0", tuple(extra[:20]))] * rng.randint(1, 5))
        assert _exact_distance(host, padded, cfg) == before
        assert before == _ref_distance(host, cand, cfg)


# ---------------------------------------------------------------------------
# What counts as content
# ---------------------------------------------------------------------------


def test_declared_domains_and_title_never_move_the_distance(cfg):
    base = _cand(3, 13)
    assert content_distance(HOST, base, cfg) == 0.5
    for domains, title in [
        (("건축", "BIM"), "모듈러 건축"),  # same declarations as the host
        (("건축물",), "x"),  # a differently written field name
        (("동네 빵집 마케팅",), " ".join(HOST_WORDS[:16])),  # title made of host words
    ]:
        assert content_distance(HOST, _cand(3, 13, domains=domains, title=title), cfg) == 0.5
    # forbidden result: declaring the host's fields does not make disjoint content close
    disjoint = _sv("C", _labels(["빵", "쿠폰", "단골"]), domains=("건축", "BIM"), title="모듈러 건축")
    assert content_distance(HOST, disjoint, cfg) == 1.0
    # forbidden result: a field name written differently does not push close content to distance 1
    same_words = _sv("C", _labels(HOST_WORDS), domains=("Architecture",))
    assert content_distance(HOST, same_words, cfg) == 0.0
    # the host's own title and domains do not count either
    renamed = _sv("H", _labels(HOST_WORDS), domains=("동네 빵집 마케팅",), title="빵 쿠폰 단골")
    assert content_distance(renamed, base, cfg) == 0.5
    assert content_distance(renamed, disjoint, cfg) == 1.0


def test_labels_and_tags_are_content(cfg):
    six = tuple(HOST_WORDS[:6])  # similarity 1/4
    assert content_distance(HOST, _sv("C", [_node("n", " ".join(six))]), cfg) == 0.0  # label
    assert content_distance(HOST, _sv("C", [_node("n", "x1", six)]), cfg) == 0.0  # tags
    assert content_distance(HOST, _sv("C", [_node("n", " ".join(six[:3]), six[3:])]), cfg) == 0.0  # both
    # the host side counts its tags too: a host whose words are all tags
    tag_host = _sv("T", [_node("n", "x1", six)])  # H = {x1} + six words: 7
    assert _exact_distance(tag_host, _sv("C", [_node("n", six[0])]), cfg) == 1 - Fraction(1, 7) / Fraction(1, 4)


def test_summaries_node_types_and_edges_are_not_content(cfg):
    words = " ".join(HOST_WORDS[:6])
    for node in (
        _node("n", "x1", summary=words),  # summary
        _node("n", "x1", type=HOST_WORDS[0]),  # node type
    ):
        assert content_distance(HOST, _sv("C", [node]), cfg) == 1.0
    edge = SubbrainEdge(source="a", target="b", summary=words, relation=HOST_WORDS[1])
    with_edge = _sv("C", [_node("a", "x1"), _node("b", "x2")], edges=[edge])
    assert content_distance(HOST, with_edge, cfg) == 1.0
    # the host's summaries, types and edges are not in H either: a host with only a summary of words has H = {x1}
    summary_host = _sv("S", [_node("a", "x1", summary=words, type=HOST_WORDS[0]), _node("b", "x2")], edges=[edge])
    assert matching._content_words(summary_host, cfg) == {"x1", "x2"}
    assert content_distance(summary_host, _sv("C", [_node("n", words)]), cfg) == 1.0


def test_no_host_words_is_distance_one(cfg):
    stop_only = _sv("S", [_node("n", "두뇌 생각", ("평가",), summary="공차 접합부")])  # stopwords only (+ a summary)
    punct_only = _sv("Q", [_node("n", "!!! ...", ("—",))])
    for empty in (stop_only, punct_only):
        assert matching._content_words(empty, cfg) == frozenset()
        assert content_distance(empty, HOST, cfg) == NO_CONTENT_DISTANCE == 1.0  # empty H
        assert content_distance(HOST, empty, cfg) == 1.0  # empty C shares nothing
    assert content_distance(stop_only, punct_only, cfg) == 1.0
    assert content_distance(stop_only, stop_only, cfg) == 1.0  # no words: not "identical content"
    assert _exact_distance(stop_only, HOST, cfg.model_copy(update={"distance_saturation": 0.0})) == 1


def test_stopwords_shared_do_not_make_close(cfg):
    a = _sv("A", _labels(["두뇌", "생각", "공차"]))
    b = _sv("B", _labels(["두뇌", "생각", "빵"]))
    assert content_distance(a, b, cfg) == 1.0


def test_josa_case_and_width_are_normalized(cfg):
    host = _sv("A", [_node("n", "BIM 공차를", ("Ｍｏｄｕｌｅ",))])
    cand = _sv("B", [_node("n", "bim 공차", ("module",))])
    assert content_distance(host, cand, cfg) == 0.0
    assert matching._content_words(host, cfg) == matching._content_words(cand, cfg) == {"bim", "공차", "module"}


def test_a_word_counts_once(cfg):
    # H and C are sets: repeating a word, in one text or across labels and tags, does not weigh it more.
    unsat = cfg.model_copy(update={"distance_saturation": 1.0})
    probe = _sv("P", [_node("n", "공차")])
    for host in (
        _sv("A", [_node("n", "공차 접합부")]),
        _sv("A", [_node("n", "공차 공차 접합부")]),
        _sv("A", [_node("n", "공차 접합부", ("공차", "공차를")), _node("m", "공차")]),
    ):
        assert _exact_distance(host, probe, unsat) == Fraction(1, 2)  # similarity 1/2
    assert matching._content_words(_sv("A", [_node("n", "공차 접합부", ("공차",))]), cfg) == {"공차", "접합부"}


def test_host_words_are_the_whole_host_terms(cfg):
    for fid in ("A", "A2", "B", "C", "D", "P", "X"):
        sv = _fixture(fid)
        assert matching._content_words(sv, cfg) == set(matching.host_terms(sv, cfg)), fid


# ---------------------------------------------------------------------------
# Inside match()
# ---------------------------------------------------------------------------


def test_match_reports_the_content_distance(cfg):
    pool = [_fixture(f) for f in ("A2", "B", "C", "D", "P", "X")]
    result = match(Q01, _fixture("A"), [sv.model_copy(update={"visibility": Visibility.PUBLIC}) for sv in pool],
                   max_members=3, cfg=cfg)
    assert len(result.candidates) == len(pool)
    for c in result.candidates:
        sv = next(s for s in pool if s.subbrain_id == c.subbrain_id)
        assert c.distance == display_value(content_distance(_fixture("A"), sv, cfg))


def test_match_builds_the_host_word_set_once(cfg, monkeypatch):
    calls: list[str] = []
    real = matching._content_words

    def counting(version, cfg_):
        calls.append(version.subbrain_id)
        return real(version, cfg_)

    monkeypatch.setattr(matching, "_content_words", counting)
    pool = [_fixture(f) for f in ("A2", "B", "C", "D", "X")]
    match(Q01, _fixture("A"), pool, max_members=3, cfg=cfg)
    assert calls.count("sb_A") == 1
    assert sorted(c for c in calls if c != "sb_A") == ["sb_A2", "sb_B", "sb_C", "sb_D", "sb_X"]


def test_distance_does_not_depend_on_the_hash_seed():
    # Set iteration order changes with PYTHONHASHSEED; the distance only counts set members.
    code = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from opencanal.config import load_config\n"
        "from opencanal.matching import content_distance, match\n"
        "from opencanal.models import SubbrainDocument, SubbrainVersion, Visibility\n"
        "cfg = load_config().matching\n"
        "def v(f):\n"
        "    b = json.loads((Path(sys.argv[1]) / f'{f}.json').read_text('utf-8'))\n"
        "    return SubbrainVersion(subbrain_id='sb_' + f, version=1, owner_id=b['owner']['user_id'],\n"
        "        owner_display='x', visibility=Visibility(b['visibility']), is_published_version=True,\n"
        "        content_hash='0' * 64, created_at='2026-10-06T00:00:00Z',\n"
        "        document=SubbrainDocument.model_validate(b['document']))\n"
        "fids = ['A', 'A2', 'B', 'C', 'D', 'P', 'X']\n"
        "print([repr(content_distance(v(a), v(b), cfg)) for a in fids for b in fids])\n"
        "r = match('모듈러 건축의 현장 조립 오류를 줄일 아이디어', v('A'), [v(f) for f in fids[1:]],\n"
        "          max_members=2, cfg=cfg)\n"
        "print(r.model_dump_json())\n"
    )
    outputs = set()
    for seed in ("0", "1", "4242"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO / "src")}
        done = subprocess.run(
            [sys.executable, "-c", code, str(BRAINS)], env=env, capture_output=True, text=True, timeout=60
        )
        assert done.returncode == 0, done.stderr
        outputs.add(done.stdout)
    assert len(outputs) == 1
