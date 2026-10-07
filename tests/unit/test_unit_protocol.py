"""Unit tests for the synthesis protocol text served by canal_open (ORACLE §4, §5.1; v.3/v.4 definitions that
still hold in v.8). The v.8 bridge, emergence, summary and constraints wording is in test_unit_protocol_v8.py.

The rules and instructions are read by the synthesizing LLM as the acceptance criteria, so they must state
the definitions the validator actually applies.
"""

from __future__ import annotations

import pytest

from opencanal.models import ViolationCode
from opencanal.protocol import synthesis_protocol

# Phrasings of the v.2 definition, where refs written on the edge itself counted toward emergence.
V2_EDGE_REF_PHRASES = (
    "엣지의 출처", "∪", "plus the edge", "edge's own refs", "edge's refs", "effective provenance", "유효 출처의 주인이 2명",
)


def _rule(code: ViolationCode) -> str:
    (rule,) = [r for r in synthesis_protocol()["rules"] if r.startswith(f"[{code.value}]")]
    return rule


def _instruction(number: int) -> tuple[str, str]:
    """The Korean and English text of instruction `number`."""
    lines = [line for line in synthesis_protocol()["instructions"].splitlines() if line.startswith(f"{number}. ")]
    assert len(lines) == 2, lines
    return lines[0], lines[1]


def test_every_violation_code_has_exactly_one_bilingual_rule():
    rules = synthesis_protocol()["rules"]
    for code in ViolationCode:
        matching = [r for r in rules if r.startswith(f"[{code.value}]")]
        assert len(matching) == 1, code
        ko, en = matching[0].split(" / ", 1)
        assert any("가" <= ch <= "힣" for ch in ko) and any("a" <= ch.lower() <= "z" for ch in en)


def test_no_rule_or_instruction_claims_edge_refs_create_emergence():
    p = synthesis_protocol()
    text = "\n".join([p["instructions"], *p["rules"]])
    for phrase in V2_EDGE_REF_PHRASES:
        assert phrase not in text, phrase


@pytest.mark.parametrize("code", [ViolationCode.NO_EMERGENCE, ViolationCode.HOST_NOT_TOUCHED])
def test_emergence_rules_use_end_node_provenance_only(code):
    ko, en = _rule(code).split(" / ", 1)
    assert "양 끝 노드" in ko and "end node" in en
    assert "엣지에 직접 적은" in ko and "on the edge itself" in en


def test_no_emergence_rule_calls_edge_refs_evidence():
    ko, en = _rule(ViolationCode.NO_EMERGENCE).split(" / ", 1)
    assert "근거" in ko and "evidence" in en
    assert "never create emergence" in en


def test_emergence_instruction_says_how_to_make_an_emergent_edge():
    ko, en = _instruction(8)
    assert "양 끝 노드" in ko and "end nodes" in en
    assert "근거" in ko and "evidence" in en
    assert "new 노드" in ko and "new node" in en
    assert "호스트" in ko and "host" in en


def test_not_novel_covers_every_source_source_edge():
    ko, en = _rule(ViolationCode.NOT_NOVEL).split(" / ", 1)
    assert "창발 여부와 무관" in ko and "emergent or not" in en
    assert "방향 무관" in ko and "either direction" in en
    assert "창발 엣지가" not in ko and "emergent edges do not" not in en
    ko11, en11 = _instruction(11)
    assert "창발 여부와 무관" in ko11 and "whether or not it is emergent" in en11


def test_templated_rule_states_label_substitution():
    ko, en = _rule(ViolationCode.TEMPLATED_RATIONALE).split(" / ", 1)
    assert "양 끝 노드 라벨" in ko and "자리표시자" in ko
    assert "end-node labels" in en and "placeholder" in en
    ko10, en10 = _instruction(10)
    assert "자리표시자" in ko10 and "placeholder" in en10


def test_normalization_is_defined_with_invisible_characters():
    ko, en = _rule(ViolationCode.RATIONALE_MISSING).split(" / ", 1)
    assert "보이지 않는 문자" in ko and "invisible characters" in en
    ko10, en10 = _instruction(10)
    assert "보이지 않는 문자" in ko10 and "한글 채움 문자" in ko10
    assert "invisible characters" in en10 and "Hangul fillers" in en10
