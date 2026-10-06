"""Unit tests for the content distance of ORACLE v.6 MUST-M5 (opencanal.matching, Builder M).

distance = 1 - min(1, cosine / distance_saturation), cosine over term-frequency vectors of node labels, tags and
summaries (textnorm.tokenize: josa stripped, stopwords removed). Declared domains and the title never move it.
No tokens -> 1.0. Deterministic.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from opencanal import matching
from opencanal.config import MatchingConfig, load_config
from opencanal.matching import NO_CONTENT_DISTANCE, content_distance, display_value, match, match_with_ranking
from opencanal.models import QueryMode, SubbrainDocument, SubbrainNode, SubbrainVersion, Visibility
from opencanal.textnorm import tokenize

REPO = Path(__file__).resolve().parents[2]
BRAINS = REPO / "fixtures" / "brains"
Q01 = "모듈러 건축의 현장 조립 오류를 줄일 아이디어"
Q02 = "내 두뇌를 평가해줘"


@pytest.fixture(scope="module")
def cfg() -> MatchingConfig:
    return load_config().matching


def _node(node_id: str, label: str, tags: tuple[str, ...] = (), summary: str | None = None) -> SubbrainNode:
    return SubbrainNode(id=node_id, label=label, tags=list(tags), summary=summary)


def _sv(
    subbrain_id: str,
    nodes: list[SubbrainNode],
    *,
    owner_id: str | None = None,
    domains: tuple[str, ...] = ("z",),
    title: str = "untitled",
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
        document=SubbrainDocument(title=title, domains=list(domains), nodes=nodes),
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


def _words(*words: str, node_id: str = "n") -> list[SubbrainNode]:
    """One node whose label holds `words`: each counted once."""
    return [_node(node_id, " ".join(words))]


# An independent reference for MUST-M5, written from the manifest text.
def _ref_vector(sv: SubbrainVersion, cfg: MatchingConfig) -> Counter:
    vector: Counter = Counter()
    for node in sv.document.nodes:
        for text in [node.label, *node.tags, node.summary]:
            vector.update(
                tokenize(text, josa_suffixes=cfg.josa_suffixes, min_stem=cfg.josa_min_stem_length, stopwords=cfg.stopwords)
            )
    return vector


def _ref_cosine(a: SubbrainVersion, b: SubbrainVersion, cfg: MatchingConfig) -> float:
    va, vb = _ref_vector(a, cfg), _ref_vector(b, cfg)
    dot = sum(va[t] * vb[t] for t in va)
    if not dot:
        return 0.0
    return dot / (math.sqrt(sum(x * x for x in va.values())) * math.sqrt(sum(x * x for x in vb.values())))


def _ref_distance(a: SubbrainVersion, b: SubbrainVersion, cfg: MatchingConfig) -> float:
    return 1 - min(1, _ref_cosine(a, b, cfg) / cfg.distance_saturation)


# ---------------------------------------------------------------------------
# The fixture brains: ORACLE §9 (v.6) numbers
# ---------------------------------------------------------------------------


def test_fixture_distances_match_the_manifest(cfg):
    a = _fixture("A")
    # §9: same-field word overlap is low (A–A2 cosine 0.34), which saturation 0.25 turns into distance 0
    assert _ref_cosine(a, _fixture("A2"), cfg) == pytest.approx(0.34, abs=0.005)
    assert content_distance(a, _fixture("A2"), cfg) == 0.0
    # §9: B·C about 0.75·0.81
    assert content_distance(a, _fixture("B"), cfg) == pytest.approx(0.7532, abs=1e-4)
    assert content_distance(a, _fixture("C"), cfg) == pytest.approx(0.8131, abs=1e-4)
    # D shares a word or two; X shares nothing
    assert content_distance(a, _fixture("D"), cfg) == pytest.approx(0.9755, abs=1e-4)
    assert content_distance(a, _fixture("X"), cfg) == 1.0


@pytest.mark.parametrize("fid", ["A2", "B", "C", "D", "P", "X"])
def test_fixture_distances_match_the_reference(cfg, fid):
    a = _fixture("A")
    assert content_distance(a, _fixture(fid), cfg) == pytest.approx(_ref_distance(a, _fixture(fid), cfg), abs=1e-12)


def test_fixture_q01_ranks_b_and_c_above_a2(cfg):
    # §9 (v.6): with the defaults, Q-01 ranks B·C (distance ~0.75·0.81) above A2 (distance 0).
    candidates = [_fixture(f) for f in ("A2", "B", "C", "D", "X")]
    ranked = match_with_ranking(Q01, _fixture("A"), candidates, max_members=3, cfg=cfg)
    got = [(c.subbrain_id, c.relevance, c.distance, c.score, c.selected) for c in ranked.ranking]
    assert got == [
        ("sb_C", 0.4, 0.8131, 0.6439, True),  # C is now farther than B: no subbrain_id tie-break any more
        ("sb_B", 0.4, 0.7532, 0.626, True),
        ("sb_A2", 0.56, 0.0, 0.56, True),
        ("sb_D", 0.0, 0.9755, 0.0, False),
        ("sb_X", 0.0, 1.0, 0.0, False),
    ]


def test_fixture_q02_keeps_a2_on_top(cfg):
    candidates = [_fixture(f) for f in ("A2", "B", "C", "D", "X")]
    ranked = match_with_ranking(Q02, _fixture("A"), candidates, max_members=3, cfg=cfg)
    assert ranked.result.query_mode_used is QueryMode.WHOLE_HOST
    assert [c.subbrain_id for c in ranked.ranking[:3]] == ["sb_A2", "sb_C", "sb_B"]
    assert ranked.ranking[0].score == 1.0
    assert {c.subbrain_id for c in ranked.result.selected} == {"sb_A2", "sb_B", "sb_C"}


def test_fixture_q01_one_slot_diversity_uses_far_distance(cfg):
    # relevance_plus_diversity, one slot: A2 (0.56, distance 0) is first by relevance; B (0.7532 >= 0.5) is the best
    # far candidate in relevance order (ties C on relevance, wins on subbrain_id) and is swapped in.
    candidates = [_fixture(f) for f in ("A2", "B", "C", "D", "X")]
    result = match(Q01, _fixture("A"), candidates, max_members=1, cfg=cfg, strategy="relevance_plus_diversity")
    assert [c.subbrain_id for c in result.selected] == ["sb_B"]
    assert {c.subbrain_id: c.reason for c in result.candidates}["sb_A2"] == matching.REASON_DISPLACED


# ---------------------------------------------------------------------------
# Hand-computed values (host of 4 words counted once: norm 2)
# ---------------------------------------------------------------------------

HOST = _sv("H", _words("공차", "접합부", "양중", "인양"), domains=("건축", "BIM"), title="모듈러 건축")


def _cand(shared: int, distinct: int, **kw) -> SubbrainVersion:
    """`distinct` words counted once, the first `shared` of them HOST words: cos = shared / (2 * sqrt(distinct))."""
    words = ["공차", "접합부", "양중", "인양"][:shared] + [f"f{i}" for i in range(distinct - shared)]
    nodes = [_node(f"n{i}", " ".join(words[i : i + 20])) for i in range(0, len(words), 20)]
    return _sv("C", nodes, **kw)


@pytest.mark.parametrize(
    ("shared", "distinct", "distance"),
    [
        (0, 3, 1.0),  # nothing in common
        (1, 4, 0.0),  # cos 1/4: exactly at saturation
        (2, 7, 0.0),  # cos 0.378: past saturation
        (1, 16, 0.5),  # cos 1/8
        (1, 64, 0.75),  # cos 1/16
        (1, 256, 0.875),  # cos 1/32
    ],
)
def test_distance_hand_computed(cfg, shared, distinct, distance):
    assert content_distance(HOST, _cand(shared, distinct), cfg) == distance


def test_distance_partial_saturation_is_unrounded(cfg):
    d = content_distance(HOST, _cand(1, 9), cfg)  # cos 1/6 -> 1 - 2/3
    assert d == pytest.approx(1 / 3, abs=1e-15)
    assert d != display_value(d)  # the function does not round; MatchCandidate shows 0.3333
    assert display_value(d) == 0.3333


def test_distance_saturation_is_read_from_config(cfg):
    quarter = _cand(1, 4)  # cos 0.25
    assert content_distance(HOST, quarter, cfg) == 0.0
    assert content_distance(HOST, quarter, cfg.model_copy(update={"distance_saturation": 0.5})) == 0.5
    assert content_distance(HOST, quarter, cfg.model_copy(update={"distance_saturation": 1.0})) == 0.75
    # a non-positive saturation saturates on any shared word, and still gives 1.0 when nothing is shared
    zero = cfg.model_copy(update={"distance_saturation": 0.0})
    assert content_distance(HOST, _cand(1, 256), zero) == 0.0
    assert content_distance(HOST, _cand(0, 3), zero) == 1.0


def test_distance_is_symmetric(cfg):
    pool = [HOST, _cand(1, 9), _cand(2, 7), _fixture("A"), _fixture("B"), _fixture("C")]
    for a in pool:
        for b in pool:
            assert content_distance(a, b, cfg) == pytest.approx(content_distance(b, a, cfg), abs=1e-12)


def test_distance_to_itself_is_zero(cfg):
    for sv in (HOST, _cand(1, 9), _fixture("A"), _fixture("D")):
        assert content_distance(sv, sv, cfg) == 0.0


# ---------------------------------------------------------------------------
# What counts as content
# ---------------------------------------------------------------------------


def test_declared_domains_and_title_never_move_the_distance(cfg):
    base = _cand(1, 16)
    assert content_distance(HOST, base, cfg) == 0.5
    for domains, title in [
        (("건축", "BIM"), "모듈러 건축"),  # same declarations as the host
        (("건축물",), "x"),  # a differently written field name
        (("동네 빵집 마케팅",), "공차 접합부 양중 인양"),  # title made of host words
    ]:
        assert content_distance(HOST, _cand(1, 16, domains=domains, title=title), cfg) == 0.5
    # forbidden result: declaring the host's fields does not make disjoint content close
    disjoint = _sv("C", _words("빵", "쿠폰", "단골"), domains=("건축", "BIM"), title="모듈러 건축")
    assert content_distance(HOST, disjoint, cfg) == 1.0
    # forbidden result: a field name written differently does not push close content to distance 1
    same_words = _sv("C", _words("공차", "접합부", "양중", "인양"), domains=("Architecture",))
    assert content_distance(HOST, same_words, cfg) == 0.0


def test_labels_tags_and_summaries_are_all_content(cfg):
    for node in (
        _node("n", "공차 x1 x2 x3"),  # label
        _node("n", "x1 x2 x3", ("공차",)),  # tag
        _node("n", "x1 x2", summary="공차 x3"),  # summary
    ):
        assert content_distance(HOST, _sv("C", [node]), cfg) == 0.0  # cos 1/4


def test_edge_summaries_are_not_content(cfg):
    from opencanal.models import SubbrainEdge

    doc = SubbrainDocument(
        title="t",
        domains=["z"],
        nodes=[_node("a", "x1"), _node("b", "x2")],
        edges=[SubbrainEdge(source="a", target="b", summary="공차 접합부 양중 인양")],
    )
    cand = _sv("C", doc.nodes).model_copy(update={"document": doc})
    assert content_distance(HOST, cand, cfg) == 1.0


def test_no_tokens_is_distance_one(cfg):
    stop_only = _sv("S", [_node("n", "두뇌 생각", ("평가",), summary="그리고 및")])  # stopwords only
    punct_only = _sv("Q", [_node("n", "!!! ...", ("—",))])
    for empty in (stop_only, punct_only):
        assert content_distance(HOST, empty, cfg) == NO_CONTENT_DISTANCE == 1.0
        assert content_distance(empty, HOST, cfg) == 1.0
    assert content_distance(stop_only, punct_only, cfg) == 1.0
    assert content_distance(stop_only, stop_only, cfg) == 1.0  # no tokens: not "identical content"


def test_stopwords_shared_do_not_make_close(cfg):
    a = _sv("A", _words("두뇌", "생각", "공차"))
    b = _sv("B", _words("두뇌", "생각", "빵"))
    assert content_distance(a, b, cfg) == 1.0


def test_josa_case_and_width_are_normalized(cfg):
    host = _sv("A", [_node("n", "BIM 공차를", ("Ｍｏｄｕｌｅ",))])
    cand = _sv("B", [_node("n", "bim 공차", ("module",))])
    assert content_distance(host, cand, cfg) == 0.0
    assert matching._term_vector(host, cfg) == matching._term_vector(cand, cfg) == Counter(
        {"bim": 1, "공차": 1, "module": 1}
    )


def test_a_word_counts_once_per_text(cfg):
    # tokenize() dedups inside one text, so "공차 공차 접합부" is {공차: 1, 접합부: 1}; the same word in another text
    # (a tag) counts again. This is the reading that reproduces the §9 numbers.
    one_text = _sv("A", [_node("n", "공차 공차 접합부")])
    two_texts = _sv("B", [_node("n", "공차 접합부", ("공차",))])
    probe = _sv("P", _words("공차"))
    unsat = cfg.model_copy(update={"distance_saturation": 1.0})
    assert content_distance(one_text, probe, unsat) == pytest.approx(1 - 1 / math.sqrt(2), abs=1e-15)
    assert content_distance(two_texts, probe, unsat) == pytest.approx(1 - 2 / math.sqrt(5), abs=1e-15)


# ---------------------------------------------------------------------------
# Inside match()
# ---------------------------------------------------------------------------


def test_match_reports_the_content_distance(cfg):
    pool = [_fixture(f) for f in ("A2", "B", "C", "D", "X")]
    result = match(Q01, _fixture("A"), pool, max_members=3, cfg=cfg)
    for c in result.candidates:
        sv = next(s for s in pool if s.subbrain_id == c.subbrain_id)
        assert c.distance == display_value(content_distance(_fixture("A"), sv, cfg))


def test_match_builds_the_host_vector_once(cfg, monkeypatch):
    calls: list[str] = []
    real = matching._term_vector

    def counting(version, cfg_):
        calls.append(version.subbrain_id)
        return real(version, cfg_)

    monkeypatch.setattr(matching, "_term_vector", counting)
    pool = [_fixture(f) for f in ("A2", "B", "C", "D", "X")]
    match(Q01, _fixture("A"), pool, max_members=3, cfg=cfg)
    assert calls.count("sb_A") == 1
    assert sorted(c for c in calls if c != "sb_A") == ["sb_A2", "sb_B", "sb_C", "sb_D", "sb_X"]


def test_distance_does_not_depend_on_the_hash_seed():
    # Set iteration order changes with PYTHONHASHSEED; the integer sums make the float result bit-identical.
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
