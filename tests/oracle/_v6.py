"""Helpers for the Oracle v.6 tests: an independent reference of the MUST-M5 content distance and constructed subbrains.

Derived from docs/oracle/ORACLE_MANIFEST.md v2026-10-06.6 (MUST-M5, MUST-M2, §9 v.6 rows) and the contract code only
(models.py, textnorm.py, config.py, public stub signatures). Nothing here reads or imports the implementation.

MUST-M5: distance = 1 - min(1, similarity / distance_saturation). similarity is the cosine of the word-frequency
vectors of the two subbrains' node labels, tags and summaries; words come from textnorm.tokenize (josa stripping,
stopword removal). Declared domains and the title are not used. No words -> distance 1.

Granularity: tokenize() dedups inside one text, so the reference tokenizes each node label, each tag and each node
summary on its own and counts in how many of those texts a word occurs. This is the reading that reproduces the
numbers the Oracle itself quotes in §9 (v.6): fixture cosine A–A2 0.34, distance A–B ≈ 0.75, A–C ≈ 0.81
(test_must_m5_reference_reproduces_the_oracle_section9_numbers pins that). Node `type` and edges are not in the
Oracle's list (노드 라벨·태그·요약) and are not used.
"""

from __future__ import annotations

import copy
import math
from collections import Counter
from typing import Any, Iterable, Iterator

from opencanal.textnorm import tokenize

# ---------------------------------------------------------------------------
# MUST-M5 reference
# ---------------------------------------------------------------------------


def content_texts(doc: dict[str, Any]) -> Iterator[str]:
    """The texts MUST-M5 reads: every node label, every tag, every node summary (not title, domains, type, edges)."""
    for node in doc["nodes"]:
        yield node["label"]
        yield from node.get("tags", []) or []
        if node.get("summary"):
            yield node["summary"]


def reference_words(text: str, mcfg) -> list[str]:
    return tokenize(
        text, josa_suffixes=mcfg.josa_suffixes, min_stem=mcfg.josa_min_stem_length, stopwords=mcfg.stopwords
    )


def reference_term_vector(doc: dict[str, Any], mcfg) -> Counter:
    vec: Counter = Counter()
    for text in content_texts(doc):
        vec.update(reference_words(text, mcfg))
    return vec


def reference_cosine(u: Counter, v: Counter) -> float:
    if not u or not v:
        return 0.0
    dot = sum(u[w] * v[w] for w in u if w in v)
    nu = math.sqrt(sum(c * c for c in u.values()))
    nv = math.sqrt(sum(c * c for c in v.values()))
    return dot / (nu * nv)


def reference_similarity(host_doc: dict[str, Any], cand_doc: dict[str, Any], mcfg) -> float:
    return reference_cosine(reference_term_vector(host_doc, mcfg), reference_term_vector(cand_doc, mcfg))


def reference_distance(host_doc: dict[str, Any], cand_doc: dict[str, Any], mcfg) -> float:
    """MUST-M5. No words on either side -> 1.0 (cosine undefined, nothing in common)."""
    hv, cv = reference_term_vector(host_doc, mcfg), reference_term_vector(cand_doc, mcfg)
    if not hv or not cv:
        return 1.0
    return 1.0 - min(1.0, reference_cosine(hv, cv) / mcfg.distance_saturation)


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


# ---------------------------------------------------------------------------
# Constructed subbrains (values are recomputed with the reference in the self-check tests; never trusted blindly)
# ---------------------------------------------------------------------------

# A topic query whose last two terms occur nowhere in fixture A, so a candidate can match them and still share no
# word with the host (content distance exactly 1.0).
QT = "현장 조립 오류 제방 배수"
QT_TERMS = ["현장", "조립", "오류", "제방", "배수"]

# relevance 0.20 under QT (tag 제방: 1.0 / 5), 0 under Q-01 and QK; no word in common with A -> distance exactly 1.0.
# It declares the host's own domains (v.5 domain distance would have called it 0).
T_FAR = nodes_doc(
    "하천 정비 메모",
    ["건축", "BIM"],
    [
        {"label": "하천 둑 보강", "tags": ["제방", "하천"], "summary": "흙을 다지고 돌망태를 올린다."},
        {"label": "물막이 판", "tags": ["둑", "장마"], "summary": "비가 오기 전에 세워 둔다."},
    ],
    "t",
)

# relevance 0.60 under QK (tags 조립, 현장, 오류); content distance from A ≈ 0.5618 (>= far_distance 0.5, < 1);
# declares the host's own domains.
FAR_060 = nodes_doc(
    "유닛 정렬 점검 메모",
    ["건축", "BIM"],
    [
        {"label": "정렬 점검표", "tags": ["조립", "현장"], "summary": "놓을 때마다 기준선을 본다."},
        {"label": "불일치 기록", "tags": ["오류", "기록"], "summary": "틀어진 값을 바로 적는다."},
    ],
    "f",
)

# Same as FAR_060 plus the host word 설치 in one summary: relevance 0.60 under QK, distance ≈ 0.4029 (< far_distance).
# It declares a field the host does not have.
NEAR_060 = nodes_doc(
    "유닛 정렬 점검 메모",
    ["게임 디자인"],
    [
        {"label": "정렬 점검표", "tags": ["조립", "현장"], "summary": "놓을 때마다 설치 기준선을 본다."},
        {"label": "불일치 기록", "tags": ["오류", "기록"], "summary": "틀어진 값을 바로 적는다."},
    ],
    "n",
)

# relevance 0.20 under QK (tag 현장); distance ≈ 0.6282 (far); declares the host's own domains.
FAR_020 = nodes_doc(
    "기초 레벨 측정",
    ["건축", "BIM"],
    [
        {"label": "레벨 측량 기록", "tags": ["현장", "측량"], "summary": "기초 높이를 매일 잰다."},
        {"label": "앵커 위치 확인", "tags": ["앵커"], "summary": "철판 구멍과 앵커를 맞춘다."},
    ],
    "g",
)

# The host's title and domains, but not one content word in common with A -> distance exactly 1.0.
DISJOINT = nodes_doc(
    "모듈러 건축 현장 조립 품질 노트",
    ["건축", "BIM"],
    [
        {"label": "반죽 숙성 시간", "tags": ["반죽", "숙성"], "summary": "밀가루와 물을 섞어 냉장고에 하룻밤 둔다."},
        {"label": "오븐 예열", "tags": ["오븐", "예열"], "summary": "굽기 삼십 분 전에 켠다."},
    ],
    "j",
)

# Labels, tags and summaries tokenize to nothing (stopwords and punctuation only); title and domains carry the host's
# words. MUST-M5 "낱말이 없으면 거리 1".
NO_WORDS = {
    "title": "모듈러 건축 현장 조립 오류",
    "domains": ["건축", "BIM"],
    "nodes": [
        {"id": "o-n1", "label": "평가", "tags": ["방법", "아이디어"], "summary": "…!"},
        {"id": "o-n2", "label": "—", "tags": [], "summary": "내 두뇌를 평가해줘"},
    ],
    "edges": [{"id": "o-e1", "source": "o-n1", "target": "o-n2", "relation": "supports", "summary": "모듈러 유닛 현장 설치"}],
}
