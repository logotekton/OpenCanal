"""Oracle v.3/v.4 boundaries of the L1 validator: MUST-Q3, MUST-Q4, MUST-Q5, MUST-Q7 (ORACLE §4, §5.1, §9).

Pure tests against the fixture canal (host sb_A v1, members sb_B v1, sb_C v1) unless a test builds its own
CanalContext. Every boundary is computed with the contract normalizer (textnorm.normalize) and asserted as a
self-check before the validator is called, so the expected verdict follows from the Oracle text alone.
"""

from __future__ import annotations

import pytest

from opencanal.models import CanalContext, Visibility
from opencanal.textnorm import normalize

from ._v8 import analyse
from .conftest import Q01, dumps, fixture_canal_context, fixture_version, load_delta, run_validator, violation_codes

# ORACLE v.8 §4: e1/e2 (query edges) and e5-e8 (self-anchor edges) are not emergent. Was (v.7): e3-e10.
GOOD_EMERGENT = {"e3", "e4", "e9", "e10"}


def _ref(sb: str, node: str, version: int = 1) -> dict:
    return {"subbrain_id": sb, "version": version, "node_id": node}


def _node(g: dict, nid: str) -> dict:
    return next(n for n in g["nodes"] if n["id"] == nid)


def _edge(g: dict, eid: str) -> dict:
    return next(e for e in g["edges"] if e["id"] == eid)


def _check(payload, ctx, cfg, expected: set[str], tolerated: set[str] = frozenset()):
    result = run_validator(payload, ctx, cfg)
    codes = violation_codes(result)
    assert result.ok is False, f"expected rejection with {expected}, got ok"
    assert expected <= codes, f"missing {expected - codes}; got {codes}: {dumps([v.model_dump(mode='json') for v in result.violations])}"
    extra = codes - expected - set(tolerated)
    assert not extra, f"unexpected extra violations {extra} (target {expected})"
    return result


def _accept(payload, ctx, cfg):
    result = run_validator(payload, ctx, cfg)
    assert result.ok is True, f"expected acceptance, got {[(v.code, v.message) for v in result.violations]}"
    return result


# ---------------------------------------------------------------------------
# MUST-Q3 (v.3) — an edge-level host ref does not make a member-only bridge host-touching
# ---------------------------------------------------------------------------


def host_ref_on_member_bridges() -> dict:
    """bad-host-untouched with a valid (sb_A, a-n2) ref written on every B–C bridge edge itself."""
    g = load_delta("bad-host-untouched")
    for eid in ("e3", "e4", "e5"):
        _edge(g, eid)["provenance"] = [_ref("sb_A", "a-n2")]
    return g


def test_must_q3_v3_edge_level_host_ref_does_not_touch_host(ctx, cfg):
    # ORACLE v.8: n-bc's 27-char summary also trips MUST-Q4 (bridge summary 40..600) -> RATIONALE_MISSING co-fires;
    # e4 (n-bc -> s-b1) and e5 (s-c2 -> n-bc) are self-anchor edges, so only e3 is emergent (was v.7: e3, e4, e5).
    result = _check(host_ref_on_member_bridges(), ctx, cfg, {"HOST_NOT_TOUCHED"}, tolerated={"RATIONALE_MISSING"})
    assert result.stats is not None
    assert set(result.stats.emergent_edge_ids) == {"e3"}, "the B–C source–source edge is still emergent"
    assert result.stats.bridge_node_ids == ["n-bc"] and result.stats.host_bridge_node_ids == [], "an edge ref is evidence"
    assert result.stats.host_touching_emergent_edge_ids == [], "an edge-level ref is evidence, not an endpoint"


# ---------------------------------------------------------------------------
# MUST-Q3 (§4) — emergence counts owners, not subbrains: two subbrains of one owner do not make a bridge
# ---------------------------------------------------------------------------


def two_subbrains_one_owner_ctx() -> CanalContext:
    """Host sb_A (user_a); members sb_B and sb_P, both owned by user_b (fixture P's owner is user_b)."""
    subbrains = {
        ("sb_A", 1): fixture_version("A"),
        ("sb_B", 1): fixture_version("B"),
        ("sb_P", 1): fixture_version("P", visibility=Visibility.PUBLIC),
    }
    assert subbrains[("sb_B", 1)].owner_id == subbrains[("sb_P", 1)].owner_id == "user_b"
    return CanalContext(
        canal_id="canal_v4_same_owner",
        host_subbrain_id="sb_A",
        host_version=1,
        host_owner_id="user_a",
        subbrains=subbrains,
    )


def same_owner_bridges(*, with_host_bridge: bool) -> dict:
    g = {
        "nodes": [
            {"id": "q", "kind": "query", "label": Q01},
            {"id": "s-a1", "kind": "source", "label": "현장 조립 오류", "provenance": [_ref("sb_A", "a-n2")]},
            {"id": "s-b1", "kind": "source", "label": "잘못 놓을 수 없는 블록 모양", "provenance": [_ref("sb_B", "b-n2")]},
            {"id": "s-p1", "kind": "source", "label": "성채 블록 조립 오류 로그", "provenance": [_ref("sb_P", "p-n2")]},
            {
                "id": "n-bp",
                "kind": "new",
                "label": "오조작 기록 기반 블록 형상 보정",
                "summary": "테스터가 잘못 붙인 기록을 모아 그 자리에 들어가지 않도록 블록 요철을 고친다.",
                "provenance": [_ref("sb_B", "b-n3"), _ref("sb_P", "p-n2")],
            },
        ],
        "edges": [
            {"id": "e1", "source": "q", "target": "s-a1", "relation": "requires"},
            {"id": "e2", "source": "q", "target": "s-b1", "relation": "requires"},
            {
                "id": "e3",
                "source": "s-p1",
                "target": "s-b1",
                "relation": "explains",
                "rationale": "테스터가 어느 조각을 어디에 잘못 붙였는지 모은 기록이, 맞지 않는 자리에 아예 들어가지 않는 모양이 왜 필요한지 보여 준다.",
            },
            {
                "id": "e4",
                "source": "n-bp",
                "target": "s-b1",
                "relation": "extends",
                "rationale": "잘못 놓을 수 없는 모양 원칙을 실제 오조작 기록으로 보정해, 자주 틀리는 자리부터 요철을 더 뚜렷하게 만드는 방향으로 넓힌다.",
            },
            {
                "id": "e5",
                "source": "n-bp",
                "target": "s-p1",
                "relation": "requires",
                "rationale": "요철을 어디부터 고칠지 정하려면 조각별로 잘못 붙인 횟수가 쌓인 조립 오류 기록이 먼저 있어야 한다.",
            },
        ],
    }
    if with_host_bridge:
        g["edges"].append(
            {
                "id": "e6",
                "source": "s-b1",
                "target": "s-a1",
                "relation": "applies_to",
                "rationale": "맞지 않는 자리에는 물리적으로 들어가지 않는 요철을 유닛 접합면에 주면, 크레인으로 올린 유닛이 틀린 위치에서는 안착하지 않아 실수가 바로 드러난다.",
            }
        )
    return g


def test_must_q3_v4_two_subbrains_of_one_owner_are_not_emergent(cfg):
    ctx = two_subbrains_one_owner_ctx()
    result = _check(same_owner_bridges(with_host_bridge=False), ctx, cfg, {"NO_EMERGENCE"}, tolerated={"HOST_NOT_TOUCHED"})
    assert result.stats is not None and result.stats.emergent_edge_ids == []


def test_must_q3_v4_owner_count_not_subbrain_count(cfg):
    ctx = two_subbrains_one_owner_ctx()
    result = _accept(same_owner_bridges(with_host_bridge=True), ctx, cfg)
    assert result.stats.emergent_edge_ids == ["e6"], "only the user_b–user_a edge is emergent"
    assert result.stats.host_touching_emergent_edge_ids == ["e6"]
    assert result.stats.owners_involved == 2, "sb_B and sb_P belong to one owner"


# ---------------------------------------------------------------------------
# MUST-Q5 — NOT_NOVEL under every normalization variant (v.4 adds invisible characters)
# ---------------------------------------------------------------------------

# (new node id, variant label, the input label it must collide with)
LABEL_VARIANTS = [
    ("n1", "ｂｉｍ 간섭·조정", "BIM 간섭 조정"),  # full-width + case + middle dot
    ("n1", "Bim_간섭_조정", "BIM 간섭 조정"),  # underscore is punctuation-like
    ("n2", "오류 교정, 기제!!", "오류 교정 기제"),  # punctuation
    ("n2", "오류​교정 기제", "오류 교정 기제"),  # zero-width space as the separator
    ("n2", "﻿오류 교정 기제‍", "오류 교정 기제"),  # BOM / ZWJ around
    ("n2", "오류ㅤ교정ㅤ기제", "오류 교정 기제"),  # Hangul filler as separator
    ("n2", "오류ﾠ교정 기제", "오류 교정 기제"),  # halfwidth Hangul filler
    ("n2", "오류 교정 기제ㅤㅤ", "오류 교정 기제"),  # trailing filler padding
    ("n2", "오류 교정⁠ 기제️", "오류 교정 기제"),  # word joiner + variation selector
    ("n2", "오류­교정 기제", "오류 교정 기제"),  # soft hyphen (Cf)
]


@pytest.mark.parametrize("nid,variant,target", LABEL_VARIANTS, ids=[repr(v[1]) for v in LABEL_VARIANTS])
def test_must_q5_v4_new_label_equal_after_normalization_is_not_novel(ctx, cfg, nid, variant, target):
    assert normalize(variant) == normalize(target), "self-check: the contract normalizer equates them"
    g = load_delta("good-01")
    _node(g, nid)["label"] = variant
    _check(g, ctx, cfg, {"NOT_NOVEL"})


# ---------------------------------------------------------------------------
# MUST-Q5 (v.3) — any source–source edge that re-states an input edge, in either direction
# ---------------------------------------------------------------------------


def copy_b_e1_reversed() -> dict:
    """Input b-e1 is b-n2 -> b-n3. Re-stated backwards with another relation, no edge-level ref (same owner)."""
    g = load_delta("good-01")
    g["nodes"].append({"id": "s-b2", "kind": "source", "label": "오조작 방지 설계", "provenance": [_ref("sb_B", "b-n3")]})
    g["edges"].append({"id": "e11", "source": "s-b2", "target": "s-b1", "relation": "requires"})
    return g


def copy_a_e4(direction: str) -> dict:
    """Input a-e4 is a-n3 (접합부 상세) -> a-n2 (현장 조립 오류), both already anchored as s-a2 / s-a1."""
    g = load_delta("good-01")
    src, tgt = ("s-a2", "s-a1") if direction == "forward" else ("s-a1", "s-a2")
    g["edges"].append({"id": "e11", "source": src, "target": tgt, "relation": "risk_for"})
    return g


def copy_c_e4_reversed() -> dict:
    """Input c-e4 is c-n6 (열쇠와 자물쇠 모델) -> c-n2 (형태 상보성); re-stated backwards inside sb_C."""
    g = load_delta("good-01")
    g["nodes"].append({"id": "s-c3", "kind": "source", "label": "열쇠와 자물쇠 모델", "provenance": [_ref("sb_C", "c-n6")]})
    g["edges"].append({"id": "e11", "source": "s-c1", "target": "s-c3", "relation": "extends"})
    return g


@pytest.mark.parametrize(
    "build",
    [copy_b_e1_reversed, lambda: copy_a_e4("forward"), lambda: copy_a_e4("reverse"), copy_c_e4_reversed],
    ids=["member_b_reversed", "host_a_forward", "host_a_reversed", "member_c_reversed"],
)
def test_must_q5_v3_copied_input_edge_any_direction_is_not_novel(ctx, cfg, build):
    _check(build(), ctx, cfg, {"NOT_NOVEL"})


def test_must_q5_source_source_edge_that_is_not_an_input_edge_is_allowed(ctx, cfg):
    """Control: a same-subbrain edge is fine when the input has no edge between those two nodes (a-n4, a-n2)."""
    g = load_delta("good-01")
    g["edges"].append({"id": "e11", "source": "s-a3", "target": "s-a1", "relation": "risk_for"})
    _accept(g, ctx, cfg)


# ---------------------------------------------------------------------------
# MUST-Q7 — 20% boundary and the v.4 endpoint-label substitution
# ---------------------------------------------------------------------------

R11 = "결합 에너지가 낮은 잘못된 결합이 저절로 풀리는 교정 기제는, 틀린 위치에 놓인 유닛을 고정 전에 빼내는 현장 절차의 근거가 된다."
R12 = "블록의 요철처럼 위치마다 다른 맞물림을 주면 크레인 기사가 유닛 번호를 확인하지 않아도 엉뚱한 자리에 내려놓는 실수가 줄어든다."
SHARED = "형상이 맞지 않으면 아예 결합하지 않도록 만드는 원리를 설치 절차에 옮겨, 틀린 조합이 볼트를 조이기 전에 바로 드러나게 한다."


R13 = "약하게 붙은 틀린 짝이 저절로 떨어져 나가는 세포의 방식은, 게임에서 틀린 조합이 화면에 남지 않도록 막는 규칙이 왜 실수를 줄이는지 보여 준다."
R14 = "맞물리는 표면끼리만 붙게 하려면 돌기와 홈의 치수가 제작 오차보다 넉넉해야 한다. 허용 오차를 단계별로 나눠 주지 않으면 맞는 유닛도 들어가지 않는다."


def ten_units() -> dict:
    """Exactly 10 rating units under ORACLE v.8 (MUST-Q7 counts bridge summaries + emergent edge rationales):
    good-01's 2 bridges + 4 emergent edges, plus four cross-subbrain emergent edges e11..e14.

    Was (v.7) `ten_emergent`: good-01's 8 emergent edges + e11, e12. Under v.8 that graph has only 8 units, which
    turned the "2 of 10 = 20% allowed" cases into 2 of 8 = 25%.
    """
    g = load_delta("good-01")
    g["edges"].append({"id": "e11", "source": "s-c2", "target": "s-a1", "relation": "explains", "rationale": R11})
    g["edges"].append({"id": "e12", "source": "s-b1", "target": "s-a1", "relation": "applies_to", "rationale": R12})
    g["edges"].append({"id": "e13", "source": "s-c2", "target": "s-b1", "relation": "explains", "rationale": R13})
    g["edges"].append({"id": "e14", "source": "s-c1", "target": "s-a3", "relation": "requires", "rationale": R14})
    ref = analyse(g, fixture_canal_context())
    assert len(ref.units) == 10 and ref.templated_share == 0, "self-check (v.8 reference)"
    return g


def _labels(g: dict) -> dict[str, str]:
    return {n["id"]: n["label"] for n in g["nodes"]}


def label_template(g: dict, eid: str, when: str = "고정 전에") -> str:
    labels = _labels(g)
    e = _edge(g, eid)
    return f"\"{labels[e['source']]}\"의 맞물림 원리를 \"{labels[e['target']]}\"에 옮기면 틀린 조합이 {when} 바로 드러나 재작업 범위가 크게 줄어든다."


def _rationale_ok(text: str) -> None:
    n = len(normalize(text))
    assert 40 <= n <= 400, f"self-check: rationale length {n} must be valid so only MUST-Q7 is under test"


def test_must_q7_three_of_ten_identical_rationales_is_templated(ctx, cfg):
    g = ten_units()
    _rationale_ok(SHARED)
    for eid in ("e10", "e11", "e12"):
        _edge(g, eid)["rationale"] = SHARED
    _check(g, ctx, cfg, {"TEMPLATED_RATIONALE"})  # 3/10 = 30% > 20%


def test_must_q7_two_of_ten_identical_rationales_is_allowed(ctx, cfg):
    g = ten_units()
    for eid in ("e11", "e12"):
        _edge(g, eid)["rationale"] = SHARED
    result = _accept(g, ctx, cfg)  # 2/10 = 20% (이하)
    assert len(result.stats.emergent_edge_ids) + len(result.stats.bridge_node_ids) == 10  # v.8 units (was 10 edges)


def test_must_q7_v4_rationales_differing_only_by_endpoint_labels_are_identical(ctx, cfg):
    g = ten_units()
    for eid in ("e3", "e4", "e10"):  # v.8: e10 replaces e7, which is a self-anchor edge (not a unit) now
        _edge(g, eid)["rationale"] = label_template(g, eid)
        _rationale_ok(_edge(g, eid)["rationale"])
    texts = {_edge(g, eid)["rationale"] for eid in ("e3", "e4", "e10")}
    assert len(texts) == 3, "self-check: the raw rationales all differ (only by their endpoint labels)"
    _check(g, ctx, cfg, {"TEMPLATED_RATIONALE"})  # 3/10 after label substitution


def test_must_q7_v4_two_label_templates_of_ten_is_allowed(ctx, cfg):
    g = ten_units()
    for eid in ("e3", "e4"):
        _edge(g, eid)["rationale"] = label_template(g, eid)
    _accept(g, ctx, cfg)  # 2/10


def test_must_q7_v4_rationales_differing_by_a_non_label_word_are_not_templated(ctx, cfg):
    """§10: near-duplicate detection is a v.5 candidate, not v.4 — only label substitution is in scope."""
    g = ten_units()
    for eid, when in (("e3", "고정 전에"), ("e4", "인양 직후에"), ("e10", "볼트 체결 단계에서")):
        _edge(g, eid)["rationale"] = label_template(g, eid, when)
    _accept(g, ctx, cfg)


# ---------------------------------------------------------------------------
# MUST-Q4 — rationale length 40..400 after normalization; v.4 invisible padding does not count
# ---------------------------------------------------------------------------

_HANGUL_RUN = (
    "형태가맞물리는표면끼리만결합한다는원리가블록모양이실수를막는이유를설명하고규칙을외우지않아도올바른조합만남게한다"
    "단백질표면의요철과전하분포가서로맞아야안정적으로붙듯이블록의돌기와홈도맞는짝에서만딸깍들어간다"
)


def hangul(n: int) -> str:
    text = (_HANGUL_RUN * (n // len(_HANGUL_RUN) + 1))[:n]
    assert len(normalize(text)) == n, "self-check: pure Hangul without spaces normalizes to itself"
    return text


def _with_e9_rationale(text: str) -> dict:
    g = load_delta("good-01")
    _edge(g, "e9")["rationale"] = text
    return g


@pytest.mark.parametrize("length,ok", [(39, False), (40, True), (400, True), (401, False)])
def test_must_q4_rationale_length_boundaries(ctx, cfg, length, ok):
    g = _with_e9_rationale(hangul(length))
    if ok:
        _accept(g, ctx, cfg)
    else:
        _check(g, ctx, cfg, {"RATIONALE_MISSING"})


@pytest.mark.parametrize(
    "text,ok",
    [
        (hangul(30) + "ㅤ" * 20, False),  # trailing Hangul filler padding
        ("ㅤ" * 15 + hangul(30) + "ﾠ" * 15, False),  # halfwidth filler too
        (hangul(30) + "​" * 20, False),  # zero-width space padding
        (hangul(30) + "️" * 10 + "⁠" * 10, False),  # variation selectors / word joiners
        (hangul(19) + "ㅤ" * 30 + hangul(19), False),  # a filler run collapses to one space: 19+1+19 = 39
        (hangul(400) + "ㅤ" * 10, True),  # padding does not count toward the maximum either
    ],
    ids=["filler_tail", "halfwidth_filler", "zwsp_tail", "vs_wj_tail", "filler_middle_run_39", "max_plus_filler"],
)
def test_must_q4_v4_invisible_padding_does_not_count(ctx, cfg, text, ok):
    assert len(text) >= 40, "self-check: raw length would pass a naive check"
    n = len(normalize(text))
    assert (40 <= n <= 400) is ok, f"self-check: normalized length {n}"
    g = _with_e9_rationale(text)
    if ok:
        _accept(g, ctx, cfg)
    else:
        _check(g, ctx, cfg, {"RATIONALE_MISSING"})
