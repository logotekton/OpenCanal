"""Helpers for the Oracle v.7 tests: an independent reference of the MUST-M5 distance and constructed subbrains.

Derived from docs/oracle/ORACLE_MANIFEST.md v2026-10-06.7 (MUST-M5, MUST-M2, §9 "(v.7)" row, §10) and the contract
code only (models.py, textnorm.py, config.py, public stub signatures). Nothing here reads or imports the
implementation. Replaces the v.6 cosine reference (_v6.py), which v.7 withdrew.

MUST-M5 (v.7): similarity = |H ∩ C| / |H|, where H and C are the SETS of distinct words of the host's and the
candidate's node LABELS and TAGS (textnorm.tokenize with the config josa_suffixes, josa_min_stem_length and stopwords).
Summaries, node types, edges, the title and the declared domains are not used. distance = 1 − min(1, similarity ÷
distance_saturation). Empty H -> distance 1. The computation is exact (rational) and deterministic; words the host
lacks never change the distance.

The reference computes with fractions.Fraction. distance_saturation is read as the decimal the config states
(Fraction(str(x)), 0.25 -> 1/4), so the exact value is the one a reader of config/matching.json computes by hand.
§9 (v.7) quotes the fixture numbers this reproduces: "라벨·태그만 쓰면 A2 0.278, B·C 0.056, D·X 0" — 10/36, 2/36, 0
(test_oracle_v7_matching.py::test_must_m5_v7_reference_reproduces_the_oracle_section9_numbers pins that).
"""

from __future__ import annotations

import copy
from fractions import Fraction
from typing import Any, Iterable, Iterator

from opencanal.textnorm import tokenize

# ---------------------------------------------------------------------------
# MUST-M5 reference (v.7)
# ---------------------------------------------------------------------------


def distance_texts(doc: dict[str, Any]) -> Iterator[str]:
    """The texts MUST-M5 v.7 reads: every node label and every tag (no summary, type, edge, title, domains)."""
    for node in doc["nodes"]:
        yield node["label"]
        yield from node.get("tags", []) or []


def reference_words(text: str, mcfg) -> list[str]:
    return tokenize(
        text, josa_suffixes=mcfg.josa_suffixes, min_stem=mcfg.josa_min_stem_length, stopwords=mcfg.stopwords
    )


def reference_word_set(doc: dict[str, Any], mcfg) -> frozenset[str]:
    """H or C: the set of distinct words of the node labels and tags."""
    out: set[str] = set()
    for text in distance_texts(doc):
        out.update(reference_words(text, mcfg))
    return frozenset(out)


def saturation(mcfg) -> Fraction:
    return Fraction(str(mcfg.distance_saturation))


def reference_similarity(host_doc: dict[str, Any], cand_doc: dict[str, Any], mcfg) -> Fraction:
    """|H ∩ C| / |H| exactly; 0 when H is empty (the distance is then 1 by the empty-host rule anyway)."""
    h = reference_word_set(host_doc, mcfg)
    if not h:
        return Fraction(0)
    return Fraction(len(h & reference_word_set(cand_doc, mcfg)), len(h))


def reference_distance_exact(host_doc: dict[str, Any], cand_doc: dict[str, Any], mcfg) -> Fraction:
    """MUST-M5 v.7, exact. Empty H -> 1."""
    if not reference_word_set(host_doc, mcfg):
        return Fraction(1)
    return 1 - min(Fraction(1), reference_similarity(host_doc, cand_doc, mcfg) / saturation(mcfg))


def reference_distance(host_doc: dict[str, Any], cand_doc: dict[str, Any], mcfg) -> float:
    """The exact distance as the nearest float (for pytest.approx and comparisons with reported values)."""
    return float(reference_distance_exact(host_doc, cand_doc, mcfg))


def distance_for_shared(k: int, n: int, mcfg) -> Fraction:
    """The distance of a candidate sharing k of the host's n words (n > 0)."""
    return 1 - min(Fraction(1), Fraction(k, n) / saturation(mcfg))


def reference_score(relevance: float, distance: float, mcfg, *, bonus: float | None = None) -> float:
    """MUST-M2: relevance + distance_bonus × distance for relevance >= τ, else 0 (models.py MatchCandidate.score)."""
    if relevance < mcfg.tau:
        return 0.0
    return relevance + (mcfg.distance_bonus if bonus is None else bonus) * distance


def m2_order_key(sid: str, relevance: float, distance: float, mcfg, *, bonus: float | None = None) -> tuple:
    """MUST-M2 ranking: score desc, then relevance desc, then subbrain_id asc — on unrounded values (v.6)."""
    return (-reference_score(relevance, distance, mcfg, bonus=bonus), -relevance, sid)


# ---------------------------------------------------------------------------
# Document builders
# ---------------------------------------------------------------------------


def with_meta(doc: dict[str, Any], *, title: str | None = None, domains: list[str] | None = None) -> dict[str, Any]:
    """Copy of `doc` with another title and/or declared domains (content untouched)."""
    out = copy.deepcopy(doc)
    if title is not None:
        out["title"] = title
    if domains is not None:
        out["domains"] = list(domains)
    return out


def nodes_doc(title: str, domains: list[str], nodes: Iterable[dict[str, Any]], prefix: str = "v") -> dict[str, Any]:
    nodes = [dict(n) for n in nodes]
    for i, n in enumerate(nodes, 1):
        n.setdefault("id", f"{prefix}-n{i}")
    edges = [
        {"id": f"{prefix}-e{i}", "source": nodes[i]["id"], "target": nodes[i - 1]["id"], "relation": "supports"}
        for i in range(1, len(nodes))
    ]
    return {"title": title, "domains": list(domains), "nodes": nodes, "edges": edges}


def add_tags(doc: dict[str, Any], node_index: int, words: Iterable[str]) -> dict[str, Any]:
    """Copy of `doc` with `words` appended to one node's tags."""
    out = copy.deepcopy(doc)
    node = out["nodes"][node_index]
    node["tags"] = [*(node.get("tags") or []), *words]
    return out


# Filler words for the padding tests (M5-PAD-1): none is a word of fixture A, none is or contains a term of any query
# the tests use, none ends in a particle. The tests self-check this against the reference before relying on it.
FILLER_REPEATED = "바나나"
_FIRST = ("고래", "자두", "망토", "연필", "우산", "등대", "거울", "단풍", "소금", "모래")
_SECOND = ("빛", "결", "꽃", "잎", "숲", "길", "샘", "솔")
FILLERS: tuple[str, ...] = tuple(a + b for a in _FIRST for b in _SECOND)  # 80 distinct words


def pad_doc(
    doc: dict[str, Any], n: int, *, mode: str, place: str, prefix: str = "pad", tags_per_node: int = 1
) -> dict[str, Any]:
    """Copy of `doc` plus `n` nodes made of filler words only.

    mode "repeated": the one word FILLER_REPEATED everywhere (the M5-PAD-1 attack: "관계없는 낱말 하나를 반복해 채우면");
    mode "distinct": a different filler word per slot (FILLERS, cycled when n × tags_per_node exceeds 80).
    place "labels": the filler is the node label (no tags); place "tags": the label is a stopword ("방법", tokenizes to
    nothing) and the fillers are the tags; place "both": label and tags.
    """
    assert mode in ("repeated", "distinct") and place in ("labels", "tags", "both")
    out = copy.deepcopy(doc)
    slot = 0

    def word() -> str:
        nonlocal slot
        w = FILLER_REPEATED if mode == "repeated" else FILLERS[slot % len(FILLERS)]
        slot += 1
        return w

    for i in range(1, n + 1):
        node: dict[str, Any] = {"id": f"{prefix}-n{i}", "type": "채움"}
        if place == "labels":
            w = word()
            node["label"] = f"{w} {w}" if mode == "repeated" else w
            node["tags"] = []
        elif place == "tags":
            node["label"] = "방법"
            node["tags"] = [word() for _ in range(tags_per_node)]
        else:
            node["label"] = word()
            node["tags"] = [word() for _ in range(tags_per_node)]
        out["nodes"].append(node)
    return out


# Words of fixture A that are no term of Q-01, QK, QT or Q3 and contain none (so adding them to a candidate leaves its
# relevance under those queries unchanged while lowering its MUST-M5 distance). Self-checked in the v.7 tests.
SAFE_HOST_WORDS: tuple[str, ...] = (
    "유닛",
    "설치",
    "순서",
    "공장",
    "운송",
    "제작",
    "치수",
    "품질",
    "간섭",
    "조정",
    "상세",
    "배관",
    "설비",
    "식별",
    "표기",
)

# ---------------------------------------------------------------------------
# Constructed subbrains (values are recomputed with the reference in the self-check tests; never trusted blindly).
# Host A has 36 distinct label/tag words, so a candidate sharing k of them is at distance 1 − min(1, k/9):
# k >= 9 -> 0; k = 5 -> 4/9 (< far_distance 0.5); k = 4 -> 5/9 (>= far_distance); k = 0 -> 1.
# ---------------------------------------------------------------------------

# A topic query whose last two terms occur nowhere in fixture A, so a candidate can match them and still share no
# word with the host (distance exactly 1.0).
QT = "현장 조립 오류 제방 배수"
QT_TERMS = ["현장", "조립", "오류", "제방", "배수"]

# relevance 0.20 under QT (tag 제방: 1.0 / 5), 0 under Q-01 and QK; no label/tag word in common with A -> distance
# exactly 1.0. It declares the host's own domains (v.5 domain distance would have called it 0).
T_FAR = nodes_doc(
    "하천 정비 메모",
    ["건축", "BIM"],
    [
        {"label": "하천 둑 보강", "tags": ["제방", "하천"], "summary": "흙을 다지고 돌망태를 올린다."},
        {"label": "물막이 판", "tags": ["둑", "장마"], "summary": "비가 오기 전에 세워 둔다."},
    ],
    "t",
)

# relevance 0.60 under QK (tags 조립, 현장, 오류); shares 3 words with A (조립, 현장, 오류) -> distance 2/3
# (>= far_distance 0.5, < 1); declares the host's own domains.
FAR_060 = nodes_doc(
    "유닛 정렬 점검 메모",
    ["건축", "BIM"],
    [
        {"label": "정렬 점검표", "tags": ["조립", "현장"], "summary": "놓을 때마다 기준선을 본다."},
        {"label": "불일치 기록", "tags": ["오류", "기록"], "summary": "틀어진 값을 바로 적는다."},
    ],
    "f",
)

# FAR_060 plus the host words 설치 and 유닛 as tags (v.7: v.6 put 설치 in a summary, which no longer counts): relevance
# 0.60 under QK, shares 5 words with A -> distance 4/9 (< far_distance). It declares a field the host does not have.
NEAR_060 = nodes_doc(
    "유닛 정렬 점검 메모",
    ["게임 디자인"],
    [
        {"label": "정렬 점검표", "tags": ["조립", "현장", "설치"], "summary": "놓을 때마다 설치 기준선을 본다."},
        {"label": "불일치 기록", "tags": ["오류", "기록", "유닛"], "summary": "틀어진 값을 바로 적는다."},
    ],
    "n",
)

# relevance 0.20 under QK (tag 현장); shares 1 word with A (현장) -> distance 8/9 (far); declares the host's own domains.
FAR_020 = nodes_doc(
    "기초 레벨 측정",
    ["건축", "BIM"],
    [
        {"label": "레벨 측량 기록", "tags": ["현장", "측량"], "summary": "기초 높이를 매일 잰다."},
        {"label": "앵커 위치 확인", "tags": ["앵커"], "summary": "철판 구멍과 앵커를 맞춘다."},
    ],
    "g",
)

# The host's title and domains, but not one label/tag word in common with A -> distance exactly 1.0.
DISJOINT = nodes_doc(
    "모듈러 건축 현장 조립 품질 노트",
    ["건축", "BIM"],
    [
        {"label": "반죽 숙성 시간", "tags": ["반죽", "숙성"], "summary": "밀가루와 물을 섞어 냉장고에 하룻밤 둔다."},
        {"label": "오븐 예열", "tags": ["오븐", "예열"], "summary": "굽기 삼십 분 전에 켠다."},
    ],
    "j",
)

# Labels and tags tokenize to nothing (stopwords and punctuation only); title, domains and an edge summary carry the
# host's words. MUST-M5 "H가 비면 거리 1" (as a host) and nothing in common (as a candidate).
NO_WORDS = {
    "title": "모듈러 건축 현장 조립 오류",
    "domains": ["건축", "BIM"],
    "nodes": [
        {"id": "o-n1", "label": "평가", "tags": ["방법", "아이디어"], "summary": "…!"},
        {"id": "o-n2", "label": "—", "tags": [], "summary": "내 두뇌를 평가해줘"},
    ],
    "edges": [{"id": "o-e1", "source": "o-n1", "target": "o-n2", "relation": "supports", "summary": "모듈러 유닛 현장 설치"}],
}
