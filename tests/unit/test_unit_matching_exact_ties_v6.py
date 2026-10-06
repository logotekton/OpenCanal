"""MUST-M2 tie rules on the MUST-M5 content distance (adversarial review M2-FLOAT-TIE-1, M2-V6-FLOATTIE-1/2).

MUST-M2 (v.6): rank by score = relevance + distance_bonus × distance, "같으면 관련도, 그다음 subbrain_id 오름차순",
comparing unrounded values. MUST-M5 (v.7): distance = 1 − min(1, (|H ∩ C| / |H|) / distance_saturation), computed
exactly. Float arithmetic broke exact ties by last-bit rounding error: 0.2 + 0.3 · (1 − 0.175 / 0.25) is
0.29000000000000004, so a score of exactly 29/100 would rank above another exact 29/100 with higher relevance, and
1 − 0.14 / 0.2 is 0.29999999999999993, so a distance of exactly far_distance 0.3 would not count as far.

The candidates below are built so their exact values are known by hand; each test self-checks them. The fuzz test at
the end compares match_with_ranking with an exact Fraction reference written from the manifest.
"""

from __future__ import annotations

import json
import random
from fractions import Fraction
from pathlib import Path
from typing import Optional

import pytest

from opencanal import matching
from opencanal.config import MatchingConfig, load_config
from opencanal.matching import content_distance, match, match_with_ranking
from opencanal.models import SubbrainDocument, SubbrainNode, SubbrainVersion, Visibility

REPO = Path(__file__).resolve().parents[2]
BRAINS = REPO / "fixtures" / "brains"
Q01 = "모듈러 건축의 현장 조립 오류를 줄일 아이디어"
BONUS = "relevance_with_distance_bonus"
DIVERSITY = "relevance_plus_diversity"


@pytest.fixture(scope="module")
def cfg() -> MatchingConfig:
    return load_config().matching


def _exact(x) -> Fraction:
    return Fraction(str(x))


def _node(node_id: str, label: str, tags=(), summary: Optional[str] = None) -> dict:
    return {"id": node_id, "label": label, "tags": list(tags), "summary": summary}


def _labels(words: list[str], prefix: str) -> list[dict]:
    return [_node(f"{prefix}{i}", " ".join(words[i : i + 16])) for i in range(0, len(words), 16)]


def _sv(subbrain_id: str, nodes: list[dict], owner_id: Optional[str] = None) -> SubbrainVersion:
    return SubbrainVersion(
        subbrain_id=subbrain_id,
        version=1,
        owner_id=owner_id or f"user_{subbrain_id}",
        owner_display="x",
        visibility=Visibility.PUBLIC,
        is_published_version=True,
        content_hash="0" * 64,
        created_at="2026-10-06T00:00:00Z",
        document=SubbrainDocument(title="t", domains=["z"], nodes=[SubbrainNode.model_validate(n) for n in nodes]),
    )


def _fixture_doc(fid: str) -> dict:
    return json.loads((BRAINS / f"{fid}.json").read_text("utf-8"))["document"]


def _doc_sv(subbrain_id: str, doc: dict, owner_id: str) -> SubbrainVersion:
    return SubbrainVersion(
        subbrain_id=subbrain_id,
        version=1,
        owner_id=owner_id,
        owner_display="x",
        visibility=Visibility.PUBLIC,
        is_published_version=True,
        content_hash="0" * 64,
        created_at="2026-10-06T00:00:00Z",
        document=SubbrainDocument.model_validate(doc),
    )


def _overlap(host: SubbrainVersion, cand: SubbrainVersion, cfg: MatchingConfig) -> tuple[int, int]:
    """(|H ∩ C|, |H|)"""
    h, c = matching._content_words(host, cfg), matching._content_words(cand, cfg)
    return len(h & c), len(h)


def _distance(host: SubbrainVersion, cand: SubbrainVersion, cfg: MatchingConfig) -> Fraction:
    return matching._distance_between(matching._content_words(host, cfg), matching._content_words(cand, cfg), cfg)


def _relevance(query: str, sv: SubbrainVersion, cfg: MatchingConfig) -> Fraction:
    return matching._score_terms(matching._clean_terms(matching.query_terms(query, cfg)), sv, cfg)[0]


def _ids(ranked) -> list[str]:
    return [c.subbrain_id for c in ranked.ranking]


def _selected(result) -> list[str]:
    return [c.subbrain_id for c in result.candidates if c.selected]


# ---------------------------------------------------------------------------
# The distance is an exact fraction
# ---------------------------------------------------------------------------


def test_the_distance_is_an_exact_fraction(cfg):
    host = _sv("H", [_node("n", "s h1 h2 h3 h4 h5")])  # |H| = 6
    cand = _sv("C", [_node("n", "s f1 f2 f3 f4 f5 f6 f7 f8")])  # shares s: similarity 1/6
    assert _overlap(host, cand, cfg) == (1, 6), "self-check"
    exact = _distance(host, cand, cfg)
    assert type(exact) is Fraction and exact == Fraction(1, 3)  # 1 - (1/6) / (1/4)
    # the public value is the float nearest to 1/3, not 0.33333333333333337
    assert content_distance(host, cand, cfg) == 1 / 3


# ---------------------------------------------------------------------------
# Equal score -> higher relevance first (M2-V6-FLOATTIE-1, M2-FLOAT-TIE-1)
# ---------------------------------------------------------------------------


def test_exact_score_tie_goes_to_higher_relevance_one_sixth(cfg):
    """X: relevance 1, distance 0 -> score 1. Y: relevance 9/10, similarity 1/6 -> distance exactly 1/3 -> score
    9/10 + 3/10 · 1/3 = 1. Equal: X (higher relevance) ranks first and takes the only slot. The ids are chosen so the
    subbrain_id tie-break would favour Y: only relevance can put X first."""
    host = _sv("sb_H", [_node("n", "s h1 h2 h3 h4 h5")])
    x = _sv("sb_z_X", [_node("n", "s h1 h2 h3 h4 h5", ("kw", "ab"))])
    y = _sv("sb_a_Y", [_node("n", "ab s f1 f2 f3 f4 f5 f6", ("kw",))])
    assert (_relevance("kw ab", x, cfg), _relevance("kw ab", y, cfg)) == (1, Fraction(9, 10)), "self-check"
    assert _overlap(host, y, cfg) == (1, 6), "self-check: similarity(H, Y) = 1/6"
    assert _distance(host, x, cfg) == 0 and _distance(host, y, cfg) == Fraction(1, 3)
    for pool in ([x, y], [y, x]):
        ranked = match_with_ranking("kw ab", host, pool, max_members=1, cfg=cfg)
        assert _ids(ranked) == ["sb_z_X", "sb_a_Y"]
        assert _selected(ranked.result) == ["sb_z_X"]
        assert {c.subbrain_id: c.reason for c in ranked.result.candidates}["sb_a_Y"] == matching.REASON_TRUNCATED
        assert [c.score for c in ranked.ranking] == [1.0, 1.0]  # displayed as the tie it is


def test_exact_score_tie_goes_to_higher_relevance_seven_fortieths(cfg):
    """P: relevance 1/5, similarity 7/40 (7 of 40 host words) -> distance 3/10 -> score 1/5 + 9/100 = 29/100.
    Q: relevance 29/100, contains the host -> distance 0 -> score 29/100. Equal: Q (higher relevance) first, although
    sb_P < sb_Q. In floats P's score is 0.29000000000000004, a hair above 29/100."""
    host_words = [f"w{i}" for i in range(40)]
    host_nodes = _labels(host_words, "h")
    host = _sv("sb_H", host_nodes)
    p = _sv("sb_P", [_node("p1", " ".join(host_words[:7] + [f"p{i}" for i in range(8)]), ("kw",))])
    q = _sv("sb_Q", host_nodes + [_node("q1", "lab partx", summary="summx")])
    query = "kw lab part summ none"
    assert _overlap(host, p, cfg) == (7, 40), "self-check: similarity 7/40"
    assert _relevance(query, p, cfg) == Fraction(1, 5) and _relevance(query, q, cfg) == Fraction(29, 100)
    assert _distance(host, p, cfg) == Fraction(3, 10) and _distance(host, q, cfg) == 0
    assert 0.2 + 0.3 * (1 - (7 / 40) / 0.25) > 0.29  # self-check: what float arithmetic would give
    for pool in ([p, q], [q, p]):
        ranked = match_with_ranking(query, host, pool, max_members=1, cfg=cfg)
        assert _ids(ranked) == ["sb_Q", "sb_P"]
        assert _selected(ranked.result) == ["sb_Q"]


# ---------------------------------------------------------------------------
# Equal score and relevance -> subbrain_id ascending (M2-V6-FLOATTIE-2, M2-FLOAT-TIE-1 exp2)
# ---------------------------------------------------------------------------


def test_a_repeated_document_ties_by_subbrain_id(cfg):
    """sb_b repeats sb_a's node three times: the same word set, so the same distance and relevance. A full tie that
    sb_a wins."""
    words = "모듈러 가나 다라 마바 사아 자차 카타 파하 거너"
    host = _sv("sb_host", [_node("h", "모듈러 건축 공차 양중 인양 h1 h2 h3 h4 h5")])
    a = _sv("sb_a", [_node("n1", words)])
    b = _sv("sb_b", [_node(f"n{i}", words) for i in range(3)])
    assert matching._content_words(a, cfg) == matching._content_words(b, cfg), "self-check"
    assert _distance(host, a, cfg) == _distance(host, b, cfg) == Fraction(3, 5)  # 1 - (1/10) / (1/4)
    for pool in ([a, b], [b, a]):
        ranked = match_with_ranking("모듈러", host, pool, max_members=1, cfg=cfg)
        assert _ids(ranked) == ["sb_a", "sb_b"]
        assert _selected(ranked.result) == ["sb_a"]


@pytest.mark.parametrize("k", [7, 13])
def test_fixture_c_repeated_ties_by_subbrain_id(cfg, k):
    """Fixture C and C repeated k times share 오류·조립 with host A (similarity 1/18, distance 7/9) and have relevance
    2/5 on Q-01: a full tie. C itself is sb_AAA, so the tie-break puts it first."""
    host = _doc_sv("sb_A", _fixture_doc("A"), "user_a")
    base = _fixture_doc("C")
    many = dict(base, edges=[], nodes=[dict(n, id=f"{n['id']}-r{r}") for r in range(k) for n in base["nodes"]])
    once, repeated = _doc_sv("sb_AAA", base, "user_p"), _doc_sv("sb_ZZZ", many, "user_q")
    assert _overlap(host, once, cfg) == _overlap(host, repeated, cfg) == (2, 36), "self-check"
    assert _distance(host, once, cfg) == _distance(host, repeated, cfg) == Fraction(7, 9)
    assert _relevance(Q01, once, cfg) == _relevance(Q01, repeated, cfg) == Fraction(2, 5), "self-check"
    for pool in ([once, repeated], [repeated, once]):
        ranked = match_with_ranking(Q01, host, pool, max_members=1, cfg=cfg)
        assert _ids(ranked) == ["sb_AAA", "sb_ZZZ"]
        assert _selected(ranked.result) == ["sb_AAA"]


def test_different_documents_sharing_as_many_host_words_tie_by_subbrain_id(cfg):
    """Both have 현장 as a tag (relevance 1/5 on Q-01). P also has 공차 (a tag); Q has 운송 (in a label) and 50 words
    host A lacks. Each shares 2 of A's 36 words, different ones, so both distances are exactly 1 - (1/18) / (1/4) =
    7/9: a full tie that sb_AAA wins, whichever words were shared and however much Q is padded."""
    host = _doc_sv("sb_A", _fixture_doc("A"), "user_a")
    p = _sv("sb_AAA", [_node("p0", "pz0x pz1x", ("현장", "공차"))])
    q = _sv("sb_ZZZ", [_node("q0", "운송 qn0w", ("현장",))] + _labels([f"qz{i}y" for i in range(50)], "qf"))
    assert _overlap(host, p, cfg) == (2, 36) and _overlap(host, q, cfg) == (2, 36), "self-check: 현장 + one more"
    assert matching._content_words(host, cfg) & matching._content_words(p, cfg) != (
        matching._content_words(host, cfg) & matching._content_words(q, cfg)
    ), "self-check: different shared words"
    assert _distance(host, p, cfg) == _distance(host, q, cfg) == Fraction(7, 9)
    assert _relevance(Q01, p, cfg) == _relevance(Q01, q, cfg) == Fraction(1, 5)
    for pool in ([p, q], [q, p]):
        ranked = match_with_ranking(Q01, host, pool, max_members=1, cfg=cfg)
        assert _ids(ranked) == ["sb_AAA", "sb_ZZZ"]
        assert _selected(ranked.result) == ["sb_AAA"]


# ---------------------------------------------------------------------------
# far_distance boundary: a distance of exactly far_distance is far
# ---------------------------------------------------------------------------


def _boundary_pool(n_host: int, n_shared: int):
    """Host: n_host words. N: the host's words plus tags kw, ab (relevance 1, distance 0, score 1). F: the first
    n_shared host words, tag kw and fillers (relevance 1/2)."""
    words = [f"s{i}" for i in range(n_host)]
    host = _sv("sb_H", _labels(words, "h"))
    near = _sv("sb_N", _labels(words, "n") + [_node("t", "nt", ("kw", "ab"))])
    far = _sv("sb_F", _labels(words[:n_shared] + [f"f{i}" for i in range(30)], "f") + [_node("t", "ft", ("kw",))])
    return host, near, far


@pytest.mark.parametrize("strategy", [BONUS, DIVERSITY])
def test_a_distance_of_exactly_far_distance_is_far_with_a_non_dyadic_saturation(cfg, strategy):
    """saturation 0.2, far_distance 0.3: similarity 7/50 -> distance 1 - 7/10 = 3/10 exactly. The float path gives
    0.29999999999999993, not far, so the diversity guarantee would not swap F in."""
    c = cfg.model_copy(update={"distance_saturation": 0.2, "far_distance": 0.3})
    host, near, far = _boundary_pool(n_host=50, n_shared=7)
    assert _overlap(host, far, c) == (7, 50), "self-check"
    assert _distance(host, far, c) == Fraction(3, 10)
    assert 1 - (7 / 50) / 0.2 < 0.3  # self-check: what float arithmetic would give
    result = match("kw ab", host, [near, far], max_members=1, cfg=c, strategy=strategy)
    reasons = {x.subbrain_id: x.reason for x in result.candidates}
    assert reasons == {"sb_F": matching.REASON_DIVERSITY, "sb_N": matching.REASON_DISPLACED}


@pytest.mark.parametrize("strategy", [BONUS, DIVERSITY])
def test_far_distance_is_compared_as_the_decimal_it_is_written_as(cfg, strategy):
    """far_distance 0.4 as a binary float is 0.40000000000000002220, above 2/5. Similarity 3/20 -> distance
    1 - 3/5 = 2/5 exactly, which is far."""
    c = cfg.model_copy(update={"far_distance": 0.4})
    host, near, far = _boundary_pool(n_host=20, n_shared=3)
    assert _overlap(host, far, c) == (3, 20), "self-check"
    assert _distance(host, far, c) == Fraction(2, 5) < 0.4  # the float 0.4 is a hair above 2/5
    result = match("kw ab", host, [near, far], max_members=1, cfg=c, strategy=strategy)
    reasons = {x.subbrain_id: x.reason for x in result.candidates}
    assert reasons == {"sb_F": matching.REASON_DIVERSITY, "sb_N": matching.REASON_DISPLACED}


# ---------------------------------------------------------------------------
# Differential fuzz against an exact reference
# ---------------------------------------------------------------------------


def _ref_words(sv: SubbrainVersion, cfg: MatchingConfig) -> set[str]:
    from opencanal.textnorm import tokenize

    words: set[str] = set()
    for node in sv.document.nodes:
        for text in (node.label, *node.tags):
            words.update(tokenize(text, josa_suffixes=cfg.josa_suffixes, min_stem=cfg.josa_min_stem_length,
                                  stopwords=cfg.stopwords))
    return words


def _ref_distance(h: set[str], c: set[str], cfg: MatchingConfig) -> Fraction:
    """MUST-M5 (v.7), from the manifest text."""
    if not h:
        return Fraction(1)
    s = _exact(cfg.distance_saturation)
    return 1 - min(Fraction(1), Fraction(len(h & c), len(h)) / s)


VOCAB = ["kw", "ab", "cd", "ef", "gh", "ij", "kl", "mn", "op", "qr"]
FUZZ_QUERY = "kw ab"


def _ref_relevance(sv: SubbrainVersion, cfg: MatchingConfig) -> Fraction:
    """The vocabulary has no word inside another, so only exact matches count: max field weight per query term."""
    weights = {name: _exact(w) for name, w in cfg.field_weights.items()}
    total = Fraction(0)
    for term in ("kw", "ab"):
        best = Fraction(0)
        for node in sv.document.nodes:
            if term in node.label.split():
                best = max(best, weights["label"])
            if term in node.tags:
                best = max(best, weights["tags"])
            if node.summary and term in node.summary.split():
                best = max(best, weights["summary"])
        total += best
    return min(Fraction(1), total / 2)


def _rand_nodes(rng: random.Random) -> list[dict]:
    return [
        _node(
            f"n{i}",
            " ".join(rng.choices(VOCAB, k=rng.randint(1, 3))),
            rng.sample(VOCAB, rng.randint(0, 2)),
            summary=" ".join(rng.choices(VOCAB, k=rng.randint(0, 3))) or None,
        )
        for i in range(rng.randint(1, 5))
    ]


def _reference(host: SubbrainVersion, pool: list[SubbrainVersion], k: int, cfg: MatchingConfig):
    """MUST-M2 selection, exactly: eligible order and the selected set (with the far_distance guarantee)."""
    tau, bonus, far = _exact(cfg.tau), _exact(cfg.distance_bonus), _exact(cfg.far_distance)
    hw = _ref_words(host, cfg)
    rows = []
    for sv in pool:
        r = _ref_relevance(sv, cfg)
        if r < tau or r <= 0:
            continue
        d = _ref_distance(hw, _ref_words(sv, cfg), cfg)
        rows.append((sv.subbrain_id, r, r + bonus * d, d >= far))
    order = sorted(rows, key=lambda row: (-row[2], -row[1], row[0]))
    selected = [row[0] for row in order[:k]]
    if selected and not any(row[3] for row in order[:k]):
        swap = next((row[0] for row in order[k:] if row[3]), None)
        if swap is not None:
            selected = selected[:-1] + [swap]
    ties = sum(1 for x, y in zip(order, order[1:]) if x[2] == y[2])
    return [row[0] for row in order], sorted(selected), ties


@pytest.mark.parametrize(
    ("seed", "saturation", "far_distance"), [(1, 0.25, 0.5), (2, 0.2, 0.3), (3, 0.3, 0.4), (4, 0.25, 0.4)]
)
def test_ranking_and_selection_match_an_exact_reference(cfg, seed, saturation, far_distance):
    c = cfg.model_copy(update={"distance_saturation": saturation, "far_distance": far_distance})
    rng = random.Random(seed)
    trials, tie_cases = 300, 0
    for _ in range(trials):
        host = _sv("sb_host", _rand_nodes(rng), owner_id="user_host")
        docs = [_rand_nodes(rng) for _ in range(rng.randint(2, 4))]
        # a repeated or padded copy ties fully with its original (same relevance, same distance): the subbrain_id
        # must decide
        for nodes in rng.sample(docs, rng.randint(1, len(docs))):
            m = rng.randint(2, 4)
            copy = [dict(n, id=f"{n['id']}-{r}") for r in range(m) for n in nodes]
            if rng.random() < 0.5:
                copy += _labels([f"pad{i}" for i in range(rng.randint(1, 40))], "pad")
            docs.append(copy)
        ids = [f"sb_{i:02d}" for i in range(len(docs))]
        rng.shuffle(ids)
        pool = [_sv(sid, nodes) for sid, nodes in zip(ids, docs)]
        k = rng.randint(1, 3)
        exp_order, exp_selected, ties = _reference(host, pool, k, c)
        tie_cases += ties
        ranked = match_with_ranking(FUZZ_QUERY, host, pool, max_members=k, cfg=c)
        eligible = set(exp_order)
        assert [x.subbrain_id for x in ranked.ranking if x.subbrain_id in eligible] == exp_order
        assert sorted(_selected(ranked.result)) == exp_selected
        hw = _ref_words(host, c)
        for sv in pool:
            assert _distance(host, sv, c) == _ref_distance(hw, _ref_words(sv, c), c)
    assert tie_cases >= trials, f"self-check: the pools must exercise exact score ties ({tie_cases})"
