"""MUST-M2 (Oracle v.5, owner decision "먼 분야에 가산점") — default strategy relevance_with_distance_bonus.

ORACLE §5.4 MUST-M2: only candidates with relevance >= τ are eligible; eligible candidates are chosen by
score = relevance + distance_bonus(config) × distance (ties: relevance, then subbrain_id); then the diversity
guarantee. At equal relevance the farther field ranks higher. With the defaults, Q-01 ranks B·C above A2. Every
candidate carries `score`. Forbidden: a below-τ candidate selected because of the bonus; the closer field above the
farther at equal relevance. §9 (v.5): distance_bonus = 0.3; Q-02 keeps A2 (1.00) on top. models.py:
MatchCandidate.score is 0 for below-τ.

Updated for Oracle v.6 (2026-10-06.6): "거리" is the MUST-M5 content distance (1 − min(1, cosine of the label/tag/summary
word-frequency vectors ÷ distance_saturation)); declared domains no longer set it. The diversity guarantee includes
the best eligible candidate with distance >= far_distance (config) when none is selected. Expected distances come from
the independent reference in _v6.py; the constructed candidates below were rebuilt so that "close" means content close
to host A (distance 0) — they deliberately declare a field the host does not have — and "far" means content far.
New v.6 cases (rounding, far_distance threshold, MUST-M5 itself) live in test_oracle_v6_matching.py.

The list order of MatchResult.candidates is NOT used to observe ranking (models.py still documents it as
"sorted by relevance desc"); ranking is observed through which candidates are selected under max_members, through
the score values, and — for canal_open, where nothing is truncated — through the order of `members`.
Expected values are computed independently with the frozen formula (_v4.reference_relevance) and by hand.

The frozen relevance formula scores node tags/labels/summaries only (stub docstring, config field_weights, DECISIONS
D-003), so the constructed-candidate tests use QK, a query none of whose terms occurs in any candidate's title or
domains: they pin MUST-M2 and nothing else. Whether title/domains are scored is pinned once, in
test_must_m1_relevance_fields_*.
"""

from __future__ import annotations

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
from ._v6 import QT, T_FAR, reference_distance
from .test_oracle_v4_matching import AT_TAU_DOC, WEAK_DOCS

DEFAULT = "relevance_with_distance_bonus"
BONUS = 0.3  # ORACLE §9 (v.5) planner proposal; read from config/matching.json in every test

# A topic query whose terms appear in no candidate's title or domains (see module docstring).
QK = "현장 조립 오류 공차 양중"
QK_TERMS = ["현장", "조립", "오류", "공차", "양중"]
# under QK. v.6: content distances from A by the MUST-M5 reference (≈0.82, ≈0.78, 1.0), not 1.0 by domain.
WEAK_QK = {"W_LABEL": 0.16, "W_SUB": 0.10, "W_TWO": 0.18}

# ---------------------------------------------------------------------------
# Constructed candidates (QK terms: 현장, 조립, 오류, 공차, 양중 -> denominator 5)
#
# v.6 (MUST-M5): "close" now means content close to host A — the nodes reuse A's frequent words (유닛, 설치, 순서,
# 위치, 공장 ...) so the cosine with A reaches distance_saturation and the distance is exactly 0. They declare a field
# A does not have (게임 디자인): under the v.5 domain distance they would have been the far ones.
# ---------------------------------------------------------------------------

# relevance 0.40 (조립, 오류 exact tags: 2.0 / 5); content distance 0 -> score 0.40
CLOSE_040 = {
    "title": "유닛 반입 검수 메모",
    "domains": ["게임 디자인"],
    "nodes": [
        {"id": "k-n1", "label": "유닛 설치 순서표", "tags": ["조립", "유닛", "순서"], "summary": "공장에서 온 유닛을 설치 순서대로 세운다."},
        {"id": "k-n2", "label": "유닛 위치 대조", "tags": ["오류", "위치", "설치"], "summary": "운송 뒤 유닛 위치를 설비 도면과 맞춘다."},
    ],
    "edges": [{"id": "k-e1", "source": "k-n2", "target": "k-n1", "relation": "precedes"}],
}
# relevance 0.40; content distance ≈ 0.21 (between CLOSE_040 and B ≈ 0.75); declares A's own domains
MID_040 = {
    "title": "블록 끼움 규칙 메모",
    "domains": ["건축", "BIM"],
    "nodes": [
        {"id": "m-n1", "label": "블록 끼움 규칙", "tags": ["조립", "규칙", "블록"], "summary": "블록은 정해진 홈에만 끼운다."},
        {"id": "m-n2", "label": "말 위치 확인", "tags": ["오류", "유닛"], "summary": "놓기 전에 순서를 확인한다."},
    ],
    "edges": [{"id": "m-e1", "source": "m-n2", "target": "m-n1", "relation": "checks"}],
}
# relevance 0.50 (조립, 오류 exact tags + 현장 exact summary token: 2.5 / 5); content distance 0 -> score 0.50
CLOSE_050 = {
    "title": "유닛 반입 순서 메모",
    "domains": ["게임 디자인"],
    "nodes": [
        {"id": "r-n1", "label": "유닛 반입 순서표", "tags": ["조립", "유닛", "순서"], "summary": "현장 반입 순서를 공장과 맞춘다."},
        {"id": "r-n2", "label": "유닛 번호 대조", "tags": ["오류", "설치", "위치"], "summary": "유닛 번호와 설치 위치를 도면과 맞춘다."},
    ],
    "edges": [{"id": "r-e1", "source": "r-n2", "target": "r-n1", "relation": "checks"}],
}
# relevance exactly τ = 0.20 (현장 exact tag: 1.0 / 5); content distance 0 -> score 0.20
CLOSE_AT_TAU = {
    "title": "기초 레벨 측정",
    "domains": ["게임 디자인"],
    "nodes": [
        {"id": "u-n1", "label": "기초 레벨 측량", "tags": ["현장", "유닛", "설치"], "summary": "유닛 설치 위치의 기초 높이를 잰다."},
        {"id": "u-n2", "label": "앵커 위치 확인", "tags": ["위치", "순서"], "summary": "공장 도면과 앵커 위치를 맞춘다."},
    ],
    "edges": [{"id": "u-e1", "source": "u-n2", "target": "u-n1", "relation": "precedes"}],
}
# relevance 0.60 under QK (조립, 현장, 오류 exact tags: 3.0 / 5); content distance 0 -> score 0.60
CLOSE_060 = {
    "title": "유닛 정렬 점검 메모",
    "domains": ["게임 디자인"],
    "nodes": [
        {"id": "z-n1", "label": "유닛 정렬 점검표", "tags": ["조립", "현장", "유닛"], "summary": "유닛을 놓을 때마다 설치 기준선을 본다."},
        {"id": "z-n2", "label": "위치 불일치 기록", "tags": ["오류", "위치"], "summary": "틀어진 위치와 순서를 바로 적는다."},
    ],
    "edges": [{"id": "z-e1", "source": "z-n2", "target": "z-n1", "relation": "feeds"}],
}


def _v(doc: dict, sid: str, owner: str | None = None):
    return version_from_doc(doc, subbrain_id=sid, owner_id=owner or f"user_{sid.lower()}")


def _ref_distance(host_doc: dict, cand_doc: dict, cfg) -> float:
    """v.6 MUST-M5 content distance by the independent reference (_v6.reference_distance)."""
    return reference_distance(host_doc, cand_doc, cfg.matching)


def _ref(terms: list[str], doc: dict, cfg) -> tuple[float, float, float]:
    """(relevance, distance, score) by the frozen formulas; relevance capped at 1 (stub: relevance in [0,1])."""
    rel = min(1.0, reference_relevance(terms, doc, cfg.matching)[0])
    dist = _ref_distance(load_brain("A")["document"], doc, cfg)
    score = rel + cfg.matching.distance_bonus * dist if rel >= cfg.matching.tau else 0.0
    return rel, dist, score


def _match(query, candidates, cfg, *, max_members=3, strategy=None, query_mode=QueryMode.AUTO, mcfg=None):
    from opencanal import matching

    return matching.match(
        query,
        fixture_version("A"),
        candidates,
        max_members=max_members,
        cfg=mcfg or cfg.matching,
        query_mode=query_mode,
        strategy=strategy,
    )


def _fixtures():
    return [fixture_version(f) for f in ("A2", "B", "C", "D", "X")]


def _selected(result) -> set[str]:
    return {c.subbrain_id for c in result.candidates if c.selected}


def _by_id(result):
    return {c.subbrain_id: c for c in result.candidates}


# Reported relevance/distance may be rounded for display (e.g. 2/3 -> 0.6667); the score is checked against the
# reported fields with this tolerance, and against the exact reference values elsewhere.
DISPLAY_TOL = 1e-3


def _assert_scores(result, cfg, *, bonus=None) -> None:
    """models.py: score = relevance + distance_bonus * distance for eligible candidates, 0 for below-τ ones."""
    b = cfg.matching.distance_bonus if bonus is None else bonus
    for c in result.candidates:
        if c.relevance >= cfg.matching.tau:
            assert c.score == pytest.approx(c.relevance + b * c.distance, abs=DISPLAY_TOL), f"{c.subbrain_id}: {c}"
        else:
            assert c.score == 0.0, f"below-τ candidate {c.subbrain_id} must have score 0 (models.py): {c}"


# ---------------------------------------------------------------------------
# Self-checks of the constructed candidates (independent of the implementation)
# ---------------------------------------------------------------------------


def test_must_m2_v5_constructed_candidates_have_the_intended_values(cfg):
    m = cfg.matching
    assert tokenize(QK, josa_suffixes=m.josa_suffixes, min_stem=m.josa_min_stem_length, stopwords=m.stopwords) == QK_TERMS
    host = load_brain("A")["document"]
    # v.6: distances are MUST-M5 content distances (reference in _v6.py); ranges where the exact value is incidental.
    expect = {  # name: (doc, relevance under QK, distance from A as (low, high))
        "CLOSE_040": (CLOSE_040, 0.40, (0.0, 0.0)),
        "MID_040": (MID_040, 0.40, (0.15, 0.30)),
        "CLOSE_050": (CLOSE_050, 0.50, (0.0, 0.0)),
        "CLOSE_060": (CLOSE_060, 0.60, (0.0, 0.0)),
        "CLOSE_AT_TAU": (CLOSE_AT_TAU, 0.20, (0.0, 0.0)),
        "AT_TAU_FAR": (AT_TAU_DOC, 0.20, (0.5, 0.6)),  # >= far_distance
        "B": (load_brain("B")["document"], 0.40, (0.75, 0.76)),
        "H": (host, 1.00, (0.0, 0.0)),
        "W_LABEL": (WEAK_DOCS["W_LABEL"], WEAK_QK["W_LABEL"], (0.8, 0.85)),
        "W_SUB": (WEAK_DOCS["W_SUB"], WEAK_QK["W_SUB"], (0.75, 0.8)),
        "W_TWO": (WEAK_DOCS["W_TWO"], WEAK_QK["W_TWO"], (1.0, 1.0)),
    }
    for name, (doc, rel, (lo, hi)) in expect.items():
        assert reference_relevance(QK_TERMS, doc, m)[0] == pytest.approx(rel), name
        assert lo - 1e-12 <= _ref_distance(host, doc, cfg) <= hi + 1e-12, (name, _ref_distance(host, doc, cfg))
        if name not in ("B", "H"):  # B, H: any title hit is also a tag hit (weight 1.0 already)
            words = {t for text in (doc["title"], *doc["domains"]) for t in tokenize(text)}
            assert not [t for t in QK_TERMS if any(t in w for w in words)], f"{name}: a QK term in title/domains"
    # The content-close candidates declare a field the host does not have (v.5 domain distance would call them far).
    for doc in (CLOSE_040, CLOSE_050, CLOSE_060, CLOSE_AT_TAU):
        assert not set(doc["domains"]) & set(host["domains"])
    # Exact float tie used below (QT): 0.50 + 0.3 * 0 == 0.20 + 0.3 * 1.0
    assert 2.5 / 5 + BONUS * 0.0 == 1.0 / 5 + BONUS * 1.0
    qt = tokenize(QT, josa_suffixes=m.josa_suffixes, min_stem=m.josa_min_stem_length, stopwords=m.stopwords)
    assert reference_relevance(qt, CLOSE_050, m)[0] == pytest.approx(0.50)
    assert reference_relevance(qt, T_FAR, m)[0] == pytest.approx(0.20)
    assert _ref_distance(host, CLOSE_050, cfg) == 0.0 and _ref_distance(host, T_FAR, cfg) == 1.0


def test_must_m1_relevance_fields_are_node_tags_labels_and_summaries_only(cfg):
    """Frozen formula (matching stub docstring; config field_weights tags/label/summary; DECISIONS D-003 "태그·라벨·요약의
    어휘 겹침"): the document title and domains are not relevance fields. Not new in v.5, but under MUST-M2 scoring them
    lifts exactly the close-field candidates (they share the host's domain words, e.g. 건축) the bonus is meant to
    outrank."""
    from opencanal import matching

    doc = {
        "title": "모듈러 건축 현장 조립 오류",
        "domains": ["건축", "모듈러"],
        "nodes": [{"id": "y-n1", "label": "볼트 체결", "tags": ["검수"], "summary": "체결 토크를 표로 남긴다."}],
        "edges": [],
    }
    assert reference_relevance(Q01_TERMS, doc, cfg.matching) == (0.0, set())
    rel, terms = matching.score_relevance(Q01_TERMS, _v(doc, "sb_Y"), cfg.matching)
    assert (rel, list(terms)) == (0.0, []), f"title/domains were scored: {rel} {terms}"


# ---------------------------------------------------------------------------
# Config and the score field
# ---------------------------------------------------------------------------


def test_must_m2_v5_config_default_strategy_and_bonus(cfg):
    m = cfg.matching
    assert m.strategy == DEFAULT
    assert m.distance_bonus == pytest.approx(BONUS)
    assert set(m.strategies_available) == {DEFAULT, "relevance_plus_diversity", "relevance_only"}


def test_must_m2_v5_default_strategy_is_used_when_none_is_passed(cfg):
    result = _match(Q01, _fixtures(), cfg)
    assert result.strategy == DEFAULT


def test_must_m2_v5_score_field_on_q01_matches_the_formula(cfg):
    result = _match(Q01, _fixtures(), cfg)
    _assert_scores(result, cfg)
    by_id = _by_id(result)
    for fid in ("A2", "B", "C", "D", "X"):
        rel, dist, score = _ref(Q01_TERMS, load_brain(fid)["document"], cfg)
        c = by_id[fixture_sid(fid)]
        assert c.relevance == pytest.approx(rel, abs=DISPLAY_TOL), fid
        assert c.distance == pytest.approx(dist, abs=DISPLAY_TOL), fid
        assert c.score == pytest.approx(score, abs=DISPLAY_TOL), fid
    # v.6 (MUST-M5): B 0.40 + 0.3 × 0.7532, C 0.40 + 0.3 × 0.8131 (§9: "B·C(거리 약 0.75·0.81)"), A2 0.56 + 0.3 × 0
    assert by_id[fixture_sid("B")].score == pytest.approx(0.6260, abs=DISPLAY_TOL)
    assert by_id[fixture_sid("C")].score == pytest.approx(0.6439, abs=DISPLAY_TOL)
    assert by_id[fixture_sid("A2")].score == pytest.approx(0.56, abs=DISPLAY_TOL)
    assert by_id[fixture_sid("D")].score == 0.0 and by_id[fixture_sid("X")].score == 0.0


# ---------------------------------------------------------------------------
# Ranking by score (observed through selection under max_members)
# ---------------------------------------------------------------------------


def test_must_m2_v5_q01_ranks_b_and_c_above_a2(cfg):
    one = _match(Q01, _fixtures(), cfg, max_members=1)
    two = _match(Q01, _fixtures(), cfg, max_members=2)
    three = _match(Q01, _fixtures(), cfg, max_members=3)
    assert _selected(two) == {fixture_sid("B"), fixture_sid("C")}, "B (0.626)·C (0.644) rank above A2 (0.56)"
    assert two.truncated is True
    # v.6: C's content is farther from A than B's (§9: 0.81 vs 0.75) and the relevance is equal -> C first.
    assert _selected(one) == {fixture_sid("C")}, "equal relevance, C farther by content -> C ranks first"
    assert one.truncated is True
    assert _selected(three) == {fixture_sid("A2"), fixture_sid("B"), fixture_sid("C")}
    assert three.truncated is False


def test_must_m2_v5_full_tie_is_broken_by_subbrain_id_ascending(cfg):
    # v.6: B and C no longer tie (content distances differ), so the full tie uses two copies of C's content owned by
    # different users: same relevance, same content distance, same score -> subbrain_id ascending.
    c_first = fixture_version("C", subbrain_id="sb_0C", owner_id="user_c0")  # sorts before sb_C
    cands = [fixture_version("A2"), fixture_version("B"), fixture_version("C"), c_first]
    assert _selected(_match(Q01, cands, cfg, max_members=1)) == {"sb_0C"}
    assert _selected(_match(Q01, list(reversed(cands)), cfg, max_members=1)) == {"sb_0C"}
    assert _selected(_match(Q01, cands, cfg, max_members=2)) == {"sb_0C", fixture_sid("C")}


def test_must_m2_v5_equal_relevance_farther_field_ranks_higher(cfg):
    # The closer candidates get ids that sort FIRST, so an id tie-break cannot explain the outcome.
    close = _v(CLOSE_040, "sb_0close")
    mid = _v(MID_040, "sb_1mid")
    far = fixture_version("B")
    for c in (close, mid, far):
        assert reference_relevance(QK_TERMS, c.document.model_dump(), cfg.matching)[0] == pytest.approx(0.40)

    # v.6 (MUST-M5) content distances from A: close 0, mid ≈ 0.21, B ≈ 0.75 (self-checked against the reference).
    host = load_brain("A")["document"]
    d_close, d_mid, d_far = (_ref_distance(host, c.document.model_dump(), cfg) for c in (close, mid, far))
    assert d_close == 0.0 < d_mid < cfg.matching.far_distance <= d_far < 1.0

    r1 = _match(QK, [close, mid, far], cfg, max_members=1)
    assert all(c.relevance == pytest.approx(0.40) for c in r1.candidates)
    assert _selected(r1) == {fixture_sid("B")}, "the farthest content (B) beats mid and close at equal relevance"
    r2 = _match(QK, [close, mid, far], cfg, max_members=2)
    assert _selected(r2) == {fixture_sid("B"), "sb_1mid"}
    r3 = _match(QK, [close, mid], cfg, max_members=1)
    assert _selected(r3) == {"sb_1mid"}, "mid beats close at equal relevance (forbidden: closer field above)"
    by_id = _by_id(r2)
    assert by_id["sb_1mid"].score == pytest.approx(0.40 + BONUS * d_mid, abs=DISPLAY_TOL)
    assert by_id[fixture_sid("B")].score > by_id["sb_1mid"].score > by_id["sb_0close"].score
    _assert_scores(r2, cfg)


def test_must_m2_v5_equal_score_is_broken_by_relevance_before_subbrain_id(cfg):
    """R (0.50, d0) and T (0.20, d1) both score exactly 0.50; T's id sorts first, R must still win (relevance).

    B (0.40 + 0.3 × 0.75 ≈ 0.63, far) is present so the diversity guarantee is already met and cannot swap T in.
    v.6: under QK every matching word is also a word of A, so no candidate can be at content distance exactly 1.0;
    the query is QT (two terms A does not have) and T is T_FAR, which shares no word with A (distance exactly 1.0)
    while declaring A's own domains.
    """
    r = _v(CLOSE_050, "sb_R")
    t = _v(T_FAR, "sb_0T")
    result = _match(QT, [t, r, fixture_version("B")], cfg, max_members=2)
    by_id = _by_id(result)
    assert by_id["sb_R"].distance == 0.0 and by_id["sb_0T"].distance == 1.0
    assert by_id["sb_R"].score == pytest.approx(0.50) and by_id["sb_0T"].score == pytest.approx(0.50)
    assert _selected(result) == {fixture_sid("B"), "sb_R"}


# ---------------------------------------------------------------------------
# Forbidden: a below-τ candidate selected because of the bonus
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("max_members", [1, 3, 10])
def test_must_m2_v5_below_tau_distant_candidate_never_selected_even_if_its_score_would_win(cfg, max_members):
    eligible = _v(CLOSE_AT_TAU, "sb_U")  # 0.20, content distance 0 -> score 0.20
    weak = [_v(WEAK_DOCS[n], f"sb_{n}") for n in sorted(WEAK_QK)]  # 0.10..0.18 under QK, content-far from A
    # self-check: with the bonus, every weak candidate's would-be score beats the eligible one (v.6 content distances)
    host = load_brain("A")["document"]
    assert _ref_distance(host, CLOSE_AT_TAU, cfg) == 0.0
    for n, rel in WEAK_QK.items():
        assert rel + BONUS * _ref_distance(host, WEAK_DOCS[n], cfg) > 0.20, n
    result = _match(QK, [*weak, eligible], cfg, max_members=max_members)
    assert result.strategy == DEFAULT
    assert _selected(result) == {"sb_U"}, f"selected {_selected(result)}"
    for c in result.candidates:
        if c.subbrain_id.startswith("sb_W_"):
            assert c.selected is False
            assert 0 < c.relevance < cfg.matching.tau
            assert c.score == 0.0, "models.py: score is 0 for below-τ candidates"
    assert _by_id(result)["sb_U"].score == pytest.approx(0.20)
    assert result.truncated is False, "below-τ candidates are not 'relevant candidates dropped by max_members'"


def test_must_m2_v5_only_below_tau_candidates_selects_nothing(cfg):
    weak = [_v(WEAK_DOCS[n], f"sb_{n}") for n in sorted(WEAK_DOCS)]
    for max_members in (1, 10):
        result = _match(Q01, weak, cfg, max_members=max_members)
        assert _selected(result) == set()
        assert all(c.score == 0.0 for c in result.candidates)


@pytest.mark.parametrize("strategy", [None, DEFAULT])
@pytest.mark.parametrize("query", [Q01, QK, Q02, Q03], ids=["Q-01", "QK", "Q-02", "Q-03"])
@pytest.mark.parametrize("max_members", [1, 3, 10])
def test_must_m2_v5_never_selects_below_tau(cfg, strategy, query, max_members):
    weak = [_v(WEAK_DOCS[n], f"sb_{n}") for n in sorted(WEAK_DOCS)]
    cands = [*_fixtures(), *weak, _v(CLOSE_AT_TAU, "sb_U"), _v(AT_TAU_DOC, "sb_T")]
    result = _match(query, cands, cfg, max_members=max_members, strategy=strategy)
    selected = [c for c in result.candidates if c.selected]
    assert len(selected) <= max_members
    for c in selected:
        assert c.relevance >= cfg.matching.tau, c
    # Independent eligibility: the reference formula over the terms the matcher reports it used.
    docs = {c.subbrain_id: c.document.model_dump() for c in cands}
    for c in result.candidates:
        ref = reference_relevance(result.query_terms, docs[c.subbrain_id], cfg.matching)[0]
        if ref < cfg.matching.tau:
            assert c.selected is False, f"{c.subbrain_id} (reference relevance {ref:.3f} < τ) was selected"
    assert not _selected(result) & {fixture_sid("D"), fixture_sid("X")}
    if query == Q01:
        assert not _selected(result) & {f"sb_{n}" for n in WEAK_DOCS}
    _assert_scores(result, cfg)


# ---------------------------------------------------------------------------
# The diversity guarantee still applies after score ranking
# ---------------------------------------------------------------------------


def test_must_m2_v5_diversity_guarantee_still_applies(cfg):
    """H (1.00, d0), Z (0.60, d0), T (0.20, d≈0.56 -> ≈0.37) under QK: score order alone picks only close candidates.

    v.6: "far" is content distance >= far_distance (config, 0.5); T's content distance from A is ≈ 0.56.
    """
    h = fixture_version("A", subbrain_id="sb_H", owner_id="user_h")  # host-like doc of another user
    z = _v(CLOSE_060, "sb_Z")
    t = _v(AT_TAU_DOC, "sb_T")
    host = load_brain("A")["document"]
    assert _ref_distance(host, CLOSE_060, cfg) < cfg.matching.far_distance <= _ref_distance(host, AT_TAU_DOC, cfg)
    cands = [h, z, t]
    two = _match(QK, cands, cfg, max_members=2)
    assert "sb_T" in _selected(two), "an eligible candidate at distance >= far_distance must be included"
    assert "sb_H" in _selected(two), "the swap replaces the lowest-ranked selected member, not the top one"
    assert len(_selected(two)) == 2
    one = _match(QK, cands, cfg, max_members=1)
    assert _selected(one) == {"sb_T"}
    three = _match(QK, cands, cfg, max_members=3)
    assert _selected(three) == {"sb_H", "sb_Z", "sb_T"}


def test_must_m2_v5_diversity_never_swaps_in_a_below_tau_candidate(cfg):
    weak = [_v(WEAK_DOCS[n], f"sb_{n}") for n in sorted(WEAK_DOCS)]
    for max_members in (1, 2):
        result = _match(Q01, [fixture_version("A2"), *weak], cfg, max_members=max_members)
        assert _selected(result) == {fixture_sid("A2")}


# ---------------------------------------------------------------------------
# Q-02 (topicless, whole_host) keeps A2 first (§9 v.5)
# ---------------------------------------------------------------------------


def test_must_m2_v5_q02_keeps_a2_first(cfg):
    result = _match(Q02, _fixtures(), cfg, max_members=2)
    assert result.query_mode_used == QueryMode.WHOLE_HOST
    assert result.strategy == DEFAULT
    by_id = _by_id(result)
    assert by_id[fixture_sid("A2")].relevance == pytest.approx(1.0), "ORACLE §9 (v.5): A2(1.00) for Q-02"
    _assert_scores(result, cfg)
    top = by_id[fixture_sid("A2")].score
    assert all(c.score < top for c in result.candidates if c.subbrain_id != fixture_sid("A2"))
    # independent recomputation from the terms the matcher reports it used (host terms, MUST-M3)
    ref = {fid: _ref(result.query_terms, load_brain(fid)["document"], cfg) for fid in ("B", "C")}
    for fid, (_, _, score) in ref.items():
        assert by_id[fixture_sid(fid)].score == pytest.approx(score, abs=DISPLAY_TOL), fid  # v.6: display rounding
        assert score < 1.0
    best_far = sorted(("B", "C"), key=lambda f: (-ref[f][2], -ref[f][0], fixture_sid(f)))[0]  # MUST-M2 order
    assert _selected(result) == {fixture_sid("A2"), fixture_sid(best_far)}, "A2 first, then the best far candidate"
    # One slot: the diversity guarantee swaps the only member for the best eligible far candidate.
    one = _match(Q02, _fixtures(), cfg, max_members=1)
    assert _selected(one) == {fixture_sid(best_far)}
    three = _match(Q02, _fixtures(), cfg, max_members=3)
    assert _selected(three) == {fixture_sid("A2"), fixture_sid("B"), fixture_sid("C")}


# ---------------------------------------------------------------------------
# distance_bonus is read from config; the other two strategies ignore it
# ---------------------------------------------------------------------------


def test_must_m2_v5_distance_bonus_is_read_from_config(cfg):
    small = cfg.matching.model_copy(update={"distance_bonus": 0.1})
    r_small = _match(Q01, _fixtures(), cfg, max_members=2, mcfg=small)
    assert r_small.strategy == DEFAULT
    # v.6: 0.56 > 0.40 + 0.1 × d; C (d ≈ 0.81) beats B (d ≈ 0.75) at equal relevance
    assert _selected(r_small) == {fixture_sid("A2"), fixture_sid("C")}, "0.56 > 0.40 + 0.1 × d; C is farther than B"
    d_c = _ref_distance(load_brain("A")["document"], load_brain("C")["document"], cfg)
    assert _by_id(r_small)[fixture_sid("C")].score == pytest.approx(0.40 + 0.1 * d_c, abs=DISPLAY_TOL)
    _assert_scores(r_small, cfg, bonus=0.1)
    r_default = _match(Q01, _fixtures(), cfg, max_members=2)
    assert _selected(r_default) == {fixture_sid("B"), fixture_sid("C")}


@pytest.mark.parametrize("strategy", ["relevance_only", "relevance_plus_diversity"])
def test_must_m2_v5_other_strategies_still_rank_by_relevance(cfg, strategy):
    result = _match(Q01, _fixtures(), cfg, max_members=2, strategy=strategy)
    assert result.strategy == strategy
    assert _selected(result) == {fixture_sid("A2"), fixture_sid("B")}, "A2 (0.56) first, then B (id tie-break)"
    weak = [_v(WEAK_DOCS[n], f"sb_{n}") for n in sorted(WEAK_QK)]
    r = _match(QK, [_v(CLOSE_AT_TAU, "sb_U"), *weak], cfg, max_members=10, strategy=strategy)
    assert _selected(r) == {"sb_U"}


def test_must_m2_v5_default_match_is_deterministic(cfg):
    cands = [*_fixtures(), _v(MID_040, "sb_1mid"), _v(CLOSE_040, "sb_0close")]
    a = _match(Q01, cands, cfg, max_members=2).model_dump(mode="json")
    b = _match(Q01, list(reversed(cands)), cfg, max_members=2).model_dump(mode="json")
    assert a == b


# ---------------------------------------------------------------------------
# Through Service.dispatch
# ---------------------------------------------------------------------------


def test_must_m2_v5_canal_open_q01_expert_host_lists_b_and_c_above_a2(seeded: World):
    seeded.set_tier("user_a", Tier.EXPERT)  # 10 slots: nothing is truncated, so only the order can rank
    env = assert_ok(seeded.open_canal(query=Q01))
    ids = member_ids(env)
    a2, b, c = seeded.sid("A2"), seeded.sid("B"), seeded.sid("C")
    assert {a2, b, c} == set(ids), ids
    assert env["truncated"] is False
    assert ids.index(b) < ids.index(a2) and ids.index(c) < ids.index(a2), f"B·C must rank above A2: {ids}"
    for m in env["members"]:
        assert m["relevance"] >= seeded.cfg.matching.tau
        if "score" in m:
            assert m["score"] == pytest.approx(
                m["relevance"] + seeded.cfg.matching.distance_bonus * m["distance"], abs=DISPLAY_TOL
            )


def test_must_m2_v5_canal_open_q02_expert_host_keeps_a2_first(seeded: World):
    seeded.set_tier("user_a", Tier.EXPERT)
    env = assert_ok(seeded.open_canal(query=Q02))
    assert env["query_mode_used"] == "whole_host"
    ids = member_ids(env)
    assert ids and ids[0] == seeded.sid("A2"), f"A2 (1.00) stays on top for Q-02: {ids}"


def test_must_m2_v5_match_explain_exposes_score(seeded: World):
    seeded.set_tier("user_a", Tier.PRO)
    env = assert_ok(seeded.call("user_a", "match_explain", query=Q01, host_subbrain_id=seeded.sid("A")))
    cands = {
        c["subbrain_id"]: c
        for c in find_dicts(env, lambda d: "subbrain_id" in d and "relevance" in d and "selected" in d)
    }
    assert {seeded.sid(f) for f in ("A2", "B", "C", "D", "X")} <= set(cands)
    tau, bonus = seeded.cfg.matching.tau, seeded.cfg.matching.distance_bonus
    for sid, c in cands.items():
        assert "score" in c and "distance" in c, f"match_explain candidate without score: {c}"
        if c["relevance"] >= tau:
            assert c["score"] == pytest.approx(c["relevance"] + bonus * c["distance"], abs=DISPLAY_TOL), c
        else:
            assert c["score"] == 0.0, c
    # v.6 (MUST-M5): B = 0.40 + 0.3 × 0.7532 ≈ 0.6260 (content distance), no longer 0.70 (domain distance 1.0)
    assert cands[seeded.sid("B")]["score"] == pytest.approx(0.6260, abs=DISPLAY_TOL)
    assert cands[seeded.sid("A2")]["score"] == pytest.approx(0.56, abs=DISPLAY_TOL)
    assert find_dicts(env, lambda d: d.get("strategy") == DEFAULT), "match_explain reports the strategy used"


def _publish_doc(world: World, user_id: str, doc: dict) -> str:
    if user_id not in world.tokens:
        world.add_user(user_id)
    env = assert_ok(world.import_doc(user_id, doc))
    assert_ok(
        world.call(user_id, "subbrain_set_visibility", subbrain_id=env["subbrain_id"], visibility="public", confirm_hash=env["content_hash"])
    )
    return env["subbrain_id"]


def test_must_m2_v5_canal_open_never_lets_the_bonus_pull_in_a_below_tau_candidate(world: World):
    world.seed(("A",))
    weak = {n: _publish_doc(world, f"user_{n.lower()}", WEAK_DOCS[n]) for n in sorted(WEAK_QK)}
    u = _publish_doc(world, "user_u", CLOSE_AT_TAU)
    world.set_tier("user_a", Tier.EXPERT)
    env = assert_ok(world.open_canal(query=QK))
    assert member_ids(env) == [u], f"only the τ-eligible close candidate may join; weak: {weak}"
    assert env["truncated"] is False
