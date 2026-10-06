"""MUST-M2 tie rules on the MUST-M5 content distance (adversarial review M2-FLOAT-TIE-1, M2-V6-FLOATTIE-1/2).

MUST-M2 (v.6): rank by score = relevance + distance_bonus × distance, "같으면 관련도, 그다음 subbrain_id 오름차순",
comparing unrounded values. MUST-M5 defines the distance mathematically: 1 − min(1, cosine / distance_saturation).
A binary-float cosine broke exact score ties by last-bit rounding error: 7/40 became 0.17499999999999998890, so a
score of exactly 29/100 ranked above another exact 29/100 with higher relevance, and a candidate whose term vector is
a multiple of another's got a different float distance, so the larger subbrain_id won a full tie.

The candidates below are built so their exact values are known by hand; each test self-checks them. The fuzz test at
the end compares match_with_ranking with an exact reference that compares a + b·√u forms by sign, without floats.
"""

from __future__ import annotations

import functools
import json
import random
from collections import Counter
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


def _norm2(v: Counter) -> int:
    return sum(c * c for c in v.values())


def _dot(u: Counter, v: Counter) -> int:
    return sum(u[t] * v[t] for t in u)


def _relevance(query: str, sv: SubbrainVersion, cfg: MatchingConfig) -> Fraction:
    return matching._score_terms(matching._clean_terms(matching.query_terms(query, cfg)), sv, cfg)[0]


def _ids(ranked) -> list[str]:
    return [c.subbrain_id for c in ranked.ranking]


def _selected(result) -> list[str]:
    return [c.subbrain_id for c in result.candidates if c.selected]


# ---------------------------------------------------------------------------
# Rational cosine: the distance is exact
# ---------------------------------------------------------------------------


def test_a_rational_cosine_gives_an_exact_distance(cfg):
    host = _sv("H", [_node("n", "s h1 h2 h3")])  # |H|² = 4
    cand = _sv("C", [_node("n", "s f1 f2 f3 f4 f5 f6 f7 f8")])  # |C|² = 9, dot 1: cos 1/6
    hv, cv = matching._term_vector(host, cfg), matching._term_vector(cand, cfg)
    assert (_norm2(hv), _norm2(cv), _dot(hv, cv)) == (4, 9, 1), "self-check"
    exact = matching._distance_between(hv, cv, cfg)
    assert isinstance(exact, Fraction) and exact == Fraction(1, 3)  # 1 - (1/6) / (1/4)
    # the public value is the float nearest to 1/3, not 0.33333333333333337
    assert content_distance(host, cand, cfg) == 1 / 3


# ---------------------------------------------------------------------------
# Equal score -> higher relevance first (M2-V6-FLOATTIE-1, M2-FLOAT-TIE-1)
# ---------------------------------------------------------------------------


def test_exact_score_tie_goes_to_higher_relevance_cosine_one_sixth(cfg):
    """X: relevance 1, distance 0 -> score 1. Y: relevance 9/10, cos 1/6 -> distance exactly 1/3 -> score
    9/10 + 3/10 · 1/3 = 1. Equal: X (higher relevance) ranks first and takes the only slot. The ids are chosen so the
    subbrain_id tie-break would favour Y: only relevance can put X first."""
    host = _sv("sb_H", [_node("n", "s h1 h2 h3")])
    x = _sv("sb_z_X", [_node("n", "s h1 h2 h3", ("kw", "ab"))])
    y = _sv("sb_a_Y", [_node("n", "ab s f1 f2 f3 f4 f5 f6", ("kw",))])
    assert (_relevance("kw ab", x, cfg), _relevance("kw ab", y, cfg)) == (1, Fraction(9, 10)), "self-check"
    hv = matching._term_vector(host, cfg)
    yv = matching._term_vector(y, cfg)
    assert (_norm2(hv), _norm2(yv), _dot(hv, yv)) == (4, 9, 1), "self-check: cos(H, Y) = 1/6"
    assert content_distance(host, x, cfg) == 0.0
    for pool in ([x, y], [y, x]):
        ranked = match_with_ranking("kw ab", host, pool, max_members=1, cfg=cfg)
        assert _ids(ranked) == ["sb_z_X", "sb_a_Y"]
        assert _selected(ranked.result) == ["sb_z_X"]
        assert {c.subbrain_id: c.reason for c in ranked.result.candidates}["sb_a_Y"] == matching.REASON_TRUNCATED
        assert [c.score for c in ranked.ranking] == [1.0, 1.0]  # displayed as the tie it is


def test_exact_score_tie_goes_to_higher_relevance_cosine_seven_fortieths(cfg):
    """P: relevance 1/5, cos(H, P) = 7/40 (|H|² 100, |P|² 16, dot 7) -> distance 3/10 -> score 1/5 + 9/100 = 29/100.
    Q: relevance 29/100, contains the host -> distance 0 -> score 29/100. Equal: Q (higher relevance) first, although
    sb_P < sb_Q. The float 7/40 is 0.17499999999999998890, which used to put P a hair above 29/100."""
    shared = [f"w{i}" for i in range(7)]
    host_nodes = [
        _node("h1", " ".join(shared)),
        _node("h2", "xx", ["xx"] * 8),  # xx counted 9 times (each tag is a text)
        _node("h3", "yy", ["yy"] * 2),  # yy 3 times
        _node("h4", "z1 z2 z3"),
    ]
    host = _sv("sb_H", host_nodes)
    p = _sv("sb_P", [_node("p1", " ".join(shared + [f"p{i}" for i in range(8)]), ("kw",))])
    q = _sv("sb_Q", host_nodes + [_node("q1", "lab partx", summary="summx")])
    query = "kw lab part summ none"
    hv, pv = matching._term_vector(host, cfg), matching._term_vector(p, cfg)
    assert (_norm2(hv), _norm2(pv), _dot(hv, pv)) == (100, 16, 7), "self-check: cos 7/40"
    assert _relevance(query, p, cfg) == Fraction(1, 5) and _relevance(query, q, cfg) == Fraction(29, 100)
    assert matching._distance_between(hv, pv, cfg) == Fraction(3, 10)
    assert content_distance(host, q, cfg) == 0.0
    for pool in ([p, q], [q, p]):
        ranked = match_with_ranking(query, host, pool, max_members=1, cfg=cfg)
        assert _ids(ranked) == ["sb_Q", "sb_P"]
        assert _selected(ranked.result) == ["sb_Q"]


# ---------------------------------------------------------------------------
# Equal score and relevance -> subbrain_id ascending (M2-V6-FLOATTIE-2, M2-FLOAT-TIE-1 exp2)
# ---------------------------------------------------------------------------


def test_a_scaled_term_vector_ties_by_subbrain_id(cfg):
    """sb_b repeats sb_a's node three times: its term vector is exactly 3x, the cosine (1/sqrt 18, irrational) and the
    relevance are equal, so the score ties fully and sb_a comes first. The floats used to differ in the last bit."""
    words = "모듈러 가나 다라 마바 사아 자차 카타 파하 거너"
    host = _sv("sb_host", [_node("h", "모듈러 건축")])
    a = _sv("sb_a", [_node("n1", words)])
    b = _sv("sb_b", [_node(f"n{i}", words) for i in range(3)])
    va, vb = matching._term_vector(a, cfg), matching._term_vector(b, cfg)
    assert vb == Counter({t: 3 * c for t, c in va.items()}), "self-check"
    assert content_distance(host, a, cfg) == content_distance(host, b, cfg)
    assert 0 < content_distance(host, a, cfg) < 1
    for pool in ([a, b], [b, a]):
        ranked = match_with_ranking("모듈러", host, pool, max_members=1, cfg=cfg)
        assert _ids(ranked) == ["sb_a", "sb_b"]
        assert _selected(ranked.result) == ["sb_a"]


@pytest.mark.parametrize("k", [7, 13])
def test_fixture_c_repeated_ties_by_subbrain_id(cfg, k):
    """Fixture C and C repeated k times have cos² 289/132418 from host A, relevance 2/5 on Q-01: a full tie. C itself
    is sb_AAA, so the tie-break puts it first (the repeated copy's float distance used to be a bit larger)."""
    host = _doc_sv("sb_A", _fixture_doc("A"), "user_a")
    base = _fixture_doc("C")
    many = dict(base, edges=[], nodes=[dict(n, id=f"{n['id']}-r{r}") for r in range(k) for n in base["nodes"]])
    once, repeated = _doc_sv("sb_AAA", base, "user_p"), _doc_sv("sb_ZZZ", many, "user_q")
    hv = matching._term_vector(host, cfg)
    cos2 = {
        sv.subbrain_id: Fraction(_dot(hv, v) ** 2, _norm2(hv) * _norm2(v))
        for sv in (once, repeated)
        for v in [matching._term_vector(sv, cfg)]
    }
    assert cos2 == {"sb_AAA": Fraction(289, 132418), "sb_ZZZ": Fraction(289, 132418)}, "self-check"
    assert content_distance(host, once, cfg) == content_distance(host, repeated, cfg)
    assert _relevance(Q01, once, cfg) == _relevance(Q01, repeated, cfg) == Fraction(2, 5), "self-check"
    for pool in ([once, repeated], [repeated, once]):
        ranked = match_with_ranking(Q01, host, pool, max_members=1, cfg=cfg)
        assert _ids(ranked) == ["sb_AAA", "sb_ZZZ"]
        assert _selected(ranked.result) == ["sb_AAA"]


def test_different_vectors_with_equal_cosine_tie_by_subbrain_id(cfg):
    """No repeated node or label: P has 현장 as one tag and 2 filler words; Q has 현장 as a tag of 5 nodes plus 50
    filler words. dot² · |Q|² = dot_Q² · |P|² in integers, so the cosines are equal (irrational) and both relevances
    are 1/5: a full tie that sb_AAA wins."""
    host = _doc_sv("sb_A", _fixture_doc("A"), "user_a")
    p = _sv("sb_AAA", [_node("p0", "pz0x pz1x", ("현장",))])
    q_nodes = [_node(f"q{j}", f"qn{j}w", ("현장",)) for j in range(5)]
    rest = [f"qz{i}y" for i in range(45)]
    q_nodes += [_node(f"qf{i}", " ".join(rest[i : i + 20])) for i in range(0, len(rest), 20)]
    q = _sv("sb_ZZZ", q_nodes)
    hv = matching._term_vector(host, cfg)
    pv, qv = matching._term_vector(p, cfg), matching._term_vector(q, cfg)
    assert _dot(hv, pv) ** 2 * _norm2(qv) == _dot(hv, qv) ** 2 * _norm2(pv), "self-check: equal cos²"
    assert pv != qv and _relevance(Q01, p, cfg) == _relevance(Q01, q, cfg) == Fraction(1, 5)
    assert content_distance(host, p, cfg) == content_distance(host, q, cfg)
    for pool in ([p, q], [q, p]):
        ranked = match_with_ranking(Q01, host, pool, max_members=1, cfg=cfg)
        assert _ids(ranked) == ["sb_AAA", "sb_ZZZ"]
        assert _selected(ranked.result) == ["sb_AAA"]


# ---------------------------------------------------------------------------
# far_distance boundary: a distance of exactly far_distance is far
# ---------------------------------------------------------------------------


def _boundary_pool(n_host_own: int, n_shared: int, n_cand_words: int):
    """Host: n_shared shared words + n_host_own own words. N: the host's words plus tags kw, ab (relevance 1, distance
    0, score 1). F: the shared words, tag kw and fillers, n_cand_words words in all (relevance 1/2)."""
    shared = [f"s{i}" for i in range(n_shared)]
    host = _sv("sb_H", [_node("h", " ".join(shared + [f"h{i}" for i in range(n_host_own)]))])
    near = _sv("sb_N", [_node("n", " ".join(shared + [f"h{i}" for i in range(n_host_own)]), ("kw", "ab"))])
    words = shared + [f"f{i}" for i in range(n_cand_words - n_shared - 1)]
    far_nodes = [_node(f"f{i}", " ".join(words[i : i + 20])) for i in range(0, len(words), 20)]
    far_nodes[0]["tags"] = ["kw"]
    return host, near, _sv("sb_F", far_nodes)


@pytest.mark.parametrize("strategy", [BONUS, DIVERSITY])
def test_a_distance_of_exactly_far_distance_is_far_with_a_non_dyadic_saturation(cfg, strategy):
    """saturation 0.2, far_distance 0.3: cos(H, F) = 7/50 (|H|² 10, |F|² 250, dot 7) -> distance 1 - 7/10 = 3/10
    exactly. The float path gave 0.29999999999999993, not far, so the diversity guarantee did not swap F in."""
    c = cfg.model_copy(update={"distance_saturation": 0.2, "far_distance": 0.3})
    host, near, far = _boundary_pool(n_host_own=3, n_shared=7, n_cand_words=250)
    hv, fv = matching._term_vector(host, c), matching._term_vector(far, c)
    assert (_norm2(hv), _norm2(fv), _dot(hv, fv)) == (10, 250, 7), "self-check"
    assert matching._distance_between(hv, fv, c) == Fraction(3, 10)
    result = match("kw ab", host, [near, far], max_members=1, cfg=c, strategy=strategy)
    reasons = {x.subbrain_id: x.reason for x in result.candidates}
    assert reasons == {"sb_F": matching.REASON_DIVERSITY, "sb_N": matching.REASON_DISPLACED}


@pytest.mark.parametrize("strategy", [BONUS, DIVERSITY])
def test_far_distance_is_compared_as_the_decimal_it_is_written_as(cfg, strategy):
    """far_distance 0.4 as a binary float is 0.40000000000000002220, above 2/5. cos(H, F) = 3/20 (|H|² 16, |F|² 25,
    dot 3) -> distance 1 - 3/5 = 2/5 exactly, which is far."""
    c = cfg.model_copy(update={"far_distance": 0.4})
    host, near, far = _boundary_pool(n_host_own=13, n_shared=3, n_cand_words=25)
    hv, fv = matching._term_vector(host, c), matching._term_vector(far, c)
    assert (_norm2(hv), _norm2(fv), _dot(hv, fv)) == (16, 25, 3), "self-check"
    assert matching._distance_between(hv, fv, c) == Fraction(2, 5) < 0.4  # the float 0.4 is a hair above 2/5
    result = match("kw ab", host, [near, far], max_members=1, cfg=c, strategy=strategy)
    reasons = {x.subbrain_id: x.reason for x in result.candidates}
    assert reasons == {"sb_F": matching.REASON_DIVERSITY, "sb_N": matching.REASON_DISPLACED}


# ---------------------------------------------------------------------------
# Differential fuzz against an exact reference
# ---------------------------------------------------------------------------


def _sign(x: Fraction) -> int:
    return (x > 0) - (x < 0)


def _sign_surd(a: Fraction, b: Fraction, u: Fraction) -> int:
    """sign(a + b·√u), u >= 0, exactly."""
    sa, sb = _sign(a), (_sign(b) if u > 0 else 0)
    if sb == 0 or sa == sb:
        return sa
    if sa == 0:
        return sb
    d = a * a - b * b * u
    return sa if d > 0 else sb if d < 0 else 0


def _sign_diff(x: tuple, y: tuple) -> int:
    """sign(x - y) for x = a1 + b1·√u1, y = a2 + b2·√u2, exactly."""
    (a1, b1, u1), (a2, b2, u2) = x, y
    a = a1 - a2
    sx = _sign_surd(a, b1, u1)
    sy = _sign(b2) if u2 > 0 else 0
    if sx != sy:
        return 1 if sx > sy else -1
    if sx == 0:
        return 0
    # X = a + b1√u1 and Y = b2√u2 share the sign σ: sign(X - Y) = σ · sign(X² - Y²)
    return sx * _sign_surd(a * a + b1 * b1 * u1 - b2 * b2 * u2, 2 * a * b1, u1)


def _ref_vector(sv: SubbrainVersion, cfg: MatchingConfig) -> Counter:
    from opencanal.textnorm import tokenize

    v: Counter = Counter()
    for node in sv.document.nodes:
        for text in (node.label, *node.tags, node.summary):
            v.update(tokenize(text, josa_suffixes=cfg.josa_suffixes, min_stem=cfg.josa_min_stem_length,
                              stopwords=cfg.stopwords))
    return v


def _ref_distance(h: Counter, c: Counter, cfg: MatchingConfig) -> tuple:
    """MUST-M5 distance as (a, b, u) meaning a + b·√u."""
    s = _exact(cfg.distance_saturation)
    dot = sum(h[t] * c[t] for t in h)
    if not h or not c or dot == 0:
        return (Fraction(1), Fraction(0), Fraction(0))
    cos2 = Fraction(dot * dot, _norm2(h) * _norm2(c))
    if cos2 >= s * s:
        return (Fraction(0), Fraction(0), Fraction(0))
    return (Fraction(1), -1 / s, cos2)


VOCAB = ["kw", "ab", "cd", "ef", "gh", "ij"]
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
        _node(f"n{i}", " ".join(rng.choices(VOCAB, k=rng.randint(1, 2))), rng.sample(VOCAB, rng.randint(0, 2)))
        for i in range(rng.randint(1, 5))
    ]


def _reference(host: SubbrainVersion, pool: list[SubbrainVersion], k: int, cfg: MatchingConfig):
    """MUST-M2 selection, exactly: eligible order and the selected set (with the far_distance guarantee)."""
    tau, bonus, far = _exact(cfg.tau), _exact(cfg.distance_bonus), _exact(cfg.far_distance)
    hv = _ref_vector(host, cfg)
    rows = []
    for sv in pool:
        r = _ref_relevance(sv, cfg)
        if r < tau or r <= 0:
            continue
        da, db, du = _ref_distance(hv, _ref_vector(sv, cfg), cfg)
        rows.append((sv.subbrain_id, r, (r + bonus * da, bonus * db, du), (da - far, db, du)))

    def cmp(x, y) -> int:
        s = _sign_diff(x[2], y[2])
        if s:
            return -s
        if x[1] != y[1]:
            return -1 if x[1] > y[1] else 1
        return -1 if x[0] < y[0] else (1 if x[0] > y[0] else 0)

    order = sorted(rows, key=functools.cmp_to_key(cmp))
    is_far = {row[0]: _sign_surd(*row[3]) >= 0 for row in order}
    selected = [row[0] for row in order[:k]]
    if selected and not any(is_far[s] for s in selected):
        swap = next((row[0] for row in order[k:] if is_far[row[0]]), None)
        if swap is not None:
            selected = selected[:-1] + [swap]
    ties = sum(1 for x, y in zip(order, order[1:]) if _sign_diff(x[2], y[2]) == 0)
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
        # a scaled copy ties fully with its original (same relevance, same cos²): the subbrain_id must decide
        for nodes in rng.sample(docs, rng.randint(1, len(docs))):
            m = rng.randint(2, 4)
            docs.append([dict(n, id=f"{n['id']}-{r}") for r in range(m) for n in nodes])
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
    assert tie_cases >= trials, f"self-check: the pools must exercise exact score ties ({tie_cases})"
