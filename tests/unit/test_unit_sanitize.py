"""Unit tests for opencanal.sanitize (Builder S) — ORACLE NEVER-04."""

from __future__ import annotations

import copy
import json
import re

import pytest

from opencanal.models import MAX_TAGS_PER_NODE, SUMMARY_MAX_CHARS, ErrorCode, OpenCanalError
from opencanal.sanitize import content_hash, import_document, mask_sensitive


def _doc(**node_extra):
    return {
        "title": "모듈러 건축",
        "domains": ["건축", "BIM"],
        "nodes": [
            {"id": "a1", "label": "현장 조립 오류", "type": "problem", "summary": "요약", "tags": ["조립"], **node_extra},
            {"id": "a2", "label": "공차 관리", "tags": ["공차"]},
        ],
        "edges": [{"id": "e1", "source": "a1", "target": "a2", "relation": "requires"}],
    }


def _blob(result) -> str:
    return json.dumps(result.document.model_dump(mode="json"), ensure_ascii=False)


def _kinds(result, location: str) -> list[str]:
    return [r.kind for r in result.redactions if r.location == location]


OPENCRAB_SAMPLE = {
    "workspace_id": "ws-logotekton",
    "nodes": [
        {
            "id": "c1",
            "label": "형태 상보성",
            "node_type": "concept",
            "space": "cell-biology",
            "source_type": "pdf",
            "created_at": "2026-09-01T00:00:00Z",
            "properties": {
                "description": "단백질은 모양이 맞물려야만 결합한다. 문의: hong@example.com",
                "tags": ["조립", "오류", "자기조립"],
                "source_url": "C:\\Logotekton\\opencrab\\packs\\cell\\raw\\protein.pdf",
                "source_locator": "C:\\Logotekton\\opencrab\\packs\\cell\\raw\\protein.pdf#page=3",
                "evidence": "원문 청크: 단백질 접힘 실험에서 연구실 전화 010-1234-5678 로 문의하라는 주석이 있었다.",
                "external_id": "doc-77",
            },
        },
        {
            "id": "c2",
            "label": "오류 교정",
            "node_type": "mechanism",
            "properties": {"summary": "샤페론이 잘못 접힌 단백질을 고친다.", "collected_at": "2026-09-01"},
        },
        {"id": "c3", "label": "자기조립", "node_type": "concept"},
    ],
    "edges": [
        {
            "id": "ce1",
            "from_id": "c1",
            "to_id": "c2",
            "relation": "explains",
            "workspace_id": "ws-logotekton",
            "properties": {"source_url": "https://example.org/paper", "weight": 0.7},
        },
        {"id": "ce2", "from_id": "c3", "to_id": "c-missing", "relation": "extends", "workspace_id": "ws-logotekton"},
    ],
}


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "C:\\Logotekton\\opencrab\\data\\source.pdf",
        "C:/Users/홍길동/문서/메모.md",
        "C:\\Users\\Hong Gildong\\My Documents\\plan.txt",
        "C:\\\\Logotekton\\\\packs\\\\a.md",
        "\\\\fileserver\\share\\team\\plan.docx",
        "/Users/hong/notes/bim.md",
        "/home/kim/brain/x.json",
        "/root/.ssh/id_rsa",
        "/private/var/folders/xy/T/tmp.txt",
        "/tmp/export.json",
        "/var/lib/opencrab/db.sqlite",
        "~/Documents/brain.md",
        "/Users/hong/Library/Mobile Documents/com~apple/x.md",
    ],
)
def test_paths_are_masked_whole(text):
    masked, hits = mask_sensitive(f"원본은 {text} 에 있다")
    assert masked == "원본은 [REDACTED:PATH] 에 있다"
    assert hits == ["path"]


def test_path_glued_to_hangul_is_masked():
    masked, hits = mask_sensitive("경로/Users/hong/x.md 참고")
    assert masked == "경로[REDACTED:PATH] 참고"
    assert hits == ["path"]


def test_two_paths_in_one_sentence_keep_prose_between():
    masked, hits = mask_sensitive("/home/kim/x 그리고 ~/Documents/a.txt, /Users/hong/a 와 3/4 비율")
    assert masked == "[REDACTED:PATH] 그리고 [REDACTED:PATH], [REDACTED:PATH] 와 3/4 비율"
    assert hits == ["path", "path", "path"]


@pytest.mark.parametrize(
    "text",
    ["hong@example.com", "hong.gildong+brain@mail.example.co.kr", "a_b-c@sub.domain.io"],
)
def test_emails_are_masked(text):
    masked, hits = mask_sensitive(f"문의 {text} 로")
    assert masked == "문의 [REDACTED:EMAIL] 로"
    assert hits == ["email"]


@pytest.mark.parametrize(
    "text",
    [
        "010-1234-5678",
        "010.1234.5678",
        "010 1234 5678",
        "01012345678",
        "011-123-4567",
        "+82 10-1234-5678",
        "+82-10-1234-5678",
        "+82 10 1234 5678",
        "+821012345678",
        "+82-2-123-4567",
        "+82 (0)10 1234 5678",
        "+44 20 7946 0958",
        "02-123-4567",
        "02-1234-5678",
        "031-123-4567",
        "(02) 123-4567",
        "1588-1234",  # 대표번호 (ORACLE v.4 NEVER-04)
    ],
)
def test_phones_are_masked(text):
    masked, hits = mask_sensitive(f"전화 {text} 로")
    assert masked == "전화 [REDACTED:PHONE] 로"
    assert hits == ["phone"]


def test_phone_glued_to_hangul_is_masked():
    masked, hits = mask_sensitive("연락처:010-1234-5678입니다, Tel.02-123-4567")
    assert masked == "연락처:[REDACTED:PHONE]입니다, Tel.[REDACTED:PHONE]"
    assert hits == ["phone", "phone"]


@pytest.mark.parametrize(
    "text",
    [
        "https://example.com/a?b=1",
        "http://localhost:8765/mcp/abc",
        "www.example.co.kr/page",
        "file:///Users/hong/x.md",
        "obsidian://open?vault=brain",
    ],
)
def test_urls_are_masked(text):
    masked, hits = mask_sensitive(f"참고 {text} 끝")
    assert masked == "참고 [REDACTED:URL] 끝"
    assert hits == ["url"]


def test_url_runs_first_and_keeps_trailing_punctuation():
    masked, hits = mask_sensitive("링크https://x.com/home/hong?mail=a@b.com. 그리고 www.test.kr, 끝")
    assert masked == "링크[REDACTED:URL]. 그리고 [REDACTED:URL], 끝"
    assert hits == ["url", "url"]


def test_email_inside_windows_path_is_one_path():
    masked, hits = mask_sensitive("C:\\Users\\hong@x.com\\notes 참고")
    assert masked == "[REDACTED:PATH] 참고"
    assert hits == ["path"]


@pytest.mark.parametrize(
    "text",
    [
        "2026-10-06",
        "2024.10.06",
        "v1.2.3",
        "3/4 비율",
        "and/or",
        "A/B/etc",
        "공차 ±2mm",
        "ISO 19650",
        "10:30",
        "12,000원",
        "0.05 mm",
        "BIM/CDE",
        "[REDACTED:URL] [REDACTED:PATH] [REDACTED:EMAIL] [REDACTED:PHONE]",
        "[REDACTED:SECRET] [REDACTED:RRN] password=[REDACTED:SECRET]",
        "redacted-node-3 redacted-edge-0",
    ],
)
def test_ordinary_text_is_not_masked(text):
    assert mask_sensitive(text) == (text, [])


def test_masking_is_linear_on_long_runs():
    import time

    start = time.perf_counter()
    for text in ("a" * 200_000 + "@", "a." * 100_000, "0" * 200_000, "/Users/" + "a b/" * 50_000):
        mask_sensitive(text)
    assert time.perf_counter() - start < 2.0


# ---------------------------------------------------------------------------
# Canonical import
# ---------------------------------------------------------------------------


def test_canonical_clean_document_has_no_redactions():
    result = import_document(_doc())
    assert result.redactions == []
    assert result.document.title == "모듈러 건축"
    assert [n.id for n in result.document.nodes] == ["a1", "a2"]
    assert result.document.edges[0].relation == "requires"


def test_canonical_drops_unknown_fields_with_locations():
    raw = _doc(properties={"source_url": "C:\\x"}, content="원문 전체")
    raw["source_url"] = "https://example.com"
    raw["nodes"][1]["text"] = "chunk"
    raw["edges"][0]["weight"] = 0.3
    result = import_document(raw)
    dropped = sorted(r.location for r in result.redactions if r.kind == "dropped_field")
    assert dropped == [
        "edges[0].weight",
        "nodes[0].content",
        "nodes[0].properties",
        "nodes[1].text",
        "source_url",
    ]
    blob = _blob(result)
    for leaked in ("원문 전체", "chunk", "example.com", "0.3", "C:"):
        assert leaked not in blob


def test_canonical_masks_every_text_field_with_location():
    raw = {
        "title": "홍길동 hong@example.com 의 두뇌",
        "domains": ["건축 /Users/hong/x", "BIM"],
        "nodes": [
            {
                "id": "n1",
                "label": "현장 https://example.com/a 조립",
                "type": "C:\\types\\t",
                "summary": "전화 010-1234-5678 그리고 /home/kim/x",
                "tags": ["조립", "kim@example.com"],
            },
            {"id": "n2", "label": "공차"},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2", "relation": "applies_to", "summary": "+82 10 1234 5678"}
        ],
    }
    result = import_document(raw)
    assert _kinds(result, "title") == ["email"]
    assert _kinds(result, "domains[0]") == ["path"]
    assert _kinds(result, "nodes[0].label") == ["url"]
    assert _kinds(result, "nodes[0].type") == ["path"]
    assert _kinds(result, "nodes[0].summary") == ["path", "phone"]
    assert _kinds(result, "nodes[0].tags[1]") == ["email"]
    assert _kinds(result, "edges[0].summary") == ["phone"]
    assert result.document.nodes[0].tags == ["조립", "[REDACTED:EMAIL]"]
    assert result.document.nodes[0].summary == "전화 [REDACTED:PHONE] 그리고 [REDACTED:PATH]"
    blob = _blob(result)
    for leaked in ("@", "example.com", "/Users/", "/home/", "C:", "010-1234", "1234 5678"):
        assert leaked not in blob


def test_redaction_detail_never_carries_the_removed_value():
    raw = copy.deepcopy(OPENCRAB_SAMPLE)
    result = import_document(raw, source_format="opencrab", title="세포", domains=["세포생물학"])
    report = json.dumps([r.model_dump() for r in result.redactions], ensure_ascii=False)
    for leaked in ("Logotekton", "hong@", "010-1234", "example.org", "원문 청크", "doc-77"):
        assert leaked not in report


# ---------------------------------------------------------------------------
# OpenCrab import
# ---------------------------------------------------------------------------


def test_opencrab_mapping_and_dropped_properties():
    result = import_document(
        copy.deepcopy(OPENCRAB_SAMPLE), source_format="opencrab", title="세포생물학 두뇌", domains=["세포생물학"]
    )
    doc = result.document
    assert doc.title == "세포생물학 두뇌"
    assert doc.domains == ["세포생물학"]
    c1, c2, c3 = doc.nodes
    assert (c1.id, c1.label, c1.type) == ("c1", "형태 상보성", "concept")
    assert c1.summary == "단백질은 모양이 맞물려야만 결합한다. 문의: [REDACTED:EMAIL]"
    assert c1.tags == ["조립", "오류", "자기조립"]
    assert (c2.type, c2.summary) == ("mechanism", "샤페론이 잘못 접힌 단백질을 고친다.")
    assert (c3.type, c3.summary, c3.tags) == ("concept", None, [])
    assert len(doc.edges) == 1
    edge = doc.edges[0]
    assert (edge.id, edge.source, edge.target, edge.relation, edge.summary) == ("ce1", "c1", "c2", "explains", None)

    dropped = {r.location for r in result.redactions if r.kind == "dropped_field"}
    assert dropped == {
        "workspace_id",
        "nodes[0].space",
        "nodes[0].source_type",
        "nodes[0].created_at",
        "nodes[0].properties.source_url",
        "nodes[0].properties.source_locator",
        "nodes[0].properties.evidence",
        "nodes[0].properties.external_id",
        "nodes[1].properties.collected_at",
        "edges[0].workspace_id",
        "edges[0].properties.source_url",
        "edges[0].properties.weight",
    }
    assert _kinds(result, "nodes[0].properties.description") == ["email"]
    assert _kinds(result, "edges[1]") == ["dangling_edge"]

    blob = _blob(result)
    for leaked in ("Logotekton", "C:", "\\", "protein.pdf", "원문 청크", "010-1234-5678", "hong@", "example.org", "ws-logotekton"):
        assert leaked not in blob


def test_opencrab_summary_wins_over_description_and_edge_summary_maps():
    raw = {
        "title": "t",
        "domains": ["d"],
        "nodes": [
            {"id": "x", "label": "X", "properties": {"summary": "짧은 요약", "description": "긴 원문"}},
            {"id": "y", "label": "Y", "properties": {"summary": "", "description": "설명"}},
        ],
        "edges": [{"from_id": "x", "to_id": "y", "relation": "extends", "properties": {"description": "엣지 설명"}}],
    }
    result = import_document(raw, source_format="opencrab")
    assert result.document.nodes[0].summary == "짧은 요약"
    assert result.document.nodes[1].summary == "설명"
    assert result.document.edges[0].summary == "엣지 설명"
    assert result.document.edges[0].id is None
    dropped = {r.location for r in result.redactions if r.kind == "dropped_field"}
    assert dropped == {"nodes[0].properties.description", "nodes[1].properties.summary"}


def test_opencrab_bad_properties_and_tags_are_dropped():
    raw = {
        "nodes": [
            {"id": "x", "label": "X", "properties": "not-an-object"},
            {"id": "y", "label": "Y", "properties": {"tags": "조립, 오류"}},
            {"id": "z", "label": "Z", "properties": {"tags": ["조립", 3, None]}},
        ],
    }
    result = import_document(raw, source_format="opencrab", title="t", domains=["d"])
    assert _kinds(result, "nodes[0].properties") == ["dropped_field"]
    assert _kinds(result, "nodes[1].properties.tags") == ["dropped_field"]
    assert _kinds(result, "nodes[2].properties.tags[1]") == ["dropped_field"]
    assert _kinds(result, "nodes[2].properties.tags[2]") == ["dropped_field"]
    assert result.document.nodes[2].tags == ["조립"]


def test_opencrab_title_and_domains_from_top_level():
    raw = copy.deepcopy(OPENCRAB_SAMPLE)
    raw["title"] = "팩 제목"
    raw["domains"] = ["세포생물학"]
    result = import_document(raw, source_format="opencrab")
    assert result.document.title == "팩 제목"
    assert result.document.domains == ["세포생물학"]


def test_arguments_override_top_level_title_and_domains():
    result = import_document(_doc(), title="새 제목", domains=["게임 디자인"])
    assert result.document.title == "새 제목"
    assert result.document.domains == ["게임 디자인"]


# ---------------------------------------------------------------------------
# Sensitive ids
# ---------------------------------------------------------------------------


def test_sensitive_node_and_edge_ids_are_pseudonymized_and_edges_remapped():
    raw = {
        "title": "t",
        "domains": ["d"],
        "nodes": [
            {"id": "C:\\Logotekton\\x.md#3", "label": "A"},
            {"id": "hong@example.com", "label": "B"},
            {"id": "redacted-node-0", "label": "C"},  # collides with the first pseudonym
        ],
        "edges": [
            {"id": "/Users/hong/e", "source": "C:\\Logotekton\\x.md#3", "target": "hong@example.com"},
            {"source": "redacted-node-0", "target": "C:\\Logotekton\\x.md#3"},
        ],
    }
    result = import_document(raw)
    ids = [n.id for n in result.document.nodes]
    assert ids == ["redacted-node-0-2", "redacted-node-1", "redacted-node-0"]
    e0, e1 = result.document.edges
    assert (e0.id, e0.source, e0.target) == ("redacted-edge-0", "redacted-node-0-2", "redacted-node-1")
    assert (e1.source, e1.target) == ("redacted-node-0", "redacted-node-0-2")
    assert _kinds(result, "nodes[0].id") == ["path"]
    assert _kinds(result, "nodes[1].id") == ["email"]
    assert _kinds(result, "edges[0].id") == ["path"]
    blob = _blob(result)
    assert "Logotekton" not in blob and "@" not in blob and "/Users/" not in blob


def test_integer_ids_are_stringified():
    raw = {"title": "t", "domains": ["d"], "nodes": [{"id": 1, "label": "A"}, {"id": 2, "label": "B"}],
           "edges": [{"id": 7, "source": 1, "target": 2}]}
    result = import_document(raw)
    assert [n.id for n in result.document.nodes] == ["1", "2"]
    assert (result.document.edges[0].id, result.document.edges[0].source) == ("7", "1")


# ---------------------------------------------------------------------------
# Truncation and limits
# ---------------------------------------------------------------------------


def test_truncation_of_summary_label_tags_and_type():
    raw = _doc()
    node = raw["nodes"][0]
    node["summary"] = "가" * (SUMMARY_MAX_CHARS + 20)
    node["label"] = "나" * 250
    node["type"] = "t" * 60
    node["tags"] = ["태그" * 30] + [f"t{k}" for k in range(MAX_TAGS_PER_NODE + 5)]
    raw["edges"][0]["relation"] = "r" * 70
    result = import_document(raw)
    out = result.document.nodes[0]
    assert len(out.summary) == SUMMARY_MAX_CHARS
    assert len(out.label) == 200
    assert len(out.type) == 50
    assert len(out.tags) == MAX_TAGS_PER_NODE
    assert len(out.tags[0]) == 50
    assert len(result.document.edges[0].relation) == 50
    for location in ("nodes[0].summary", "nodes[0].label", "nodes[0].type", "nodes[0].tags", "nodes[0].tags[0]", "edges[0].relation"):
        assert "truncated" in _kinds(result, location), location


def test_mask_happens_before_truncation():
    raw = _doc(summary="가" * 270 + " C:\\Logotekton\\very\\long\\path\\file.pdf")
    result = import_document(raw)
    summary = result.document.nodes[0].summary
    assert "Logotekton" not in summary and "C:" not in summary
    assert _kinds(result, "nodes[0].summary") == ["path", "truncated"]


def test_too_many_domains_are_truncated():
    result = import_document(_doc(), domains=[f"d{k}" for k in range(12)])
    assert result.document.domains == [f"d{k}" for k in range(10)]
    assert _kinds(result, "domains") == ["truncated"]


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


def test_dangling_edges_and_self_loops_are_dropped():
    raw = _doc()
    raw["edges"] = [
        {"id": "ok", "source": "a1", "target": "a2"},
        {"id": "gone-target", "source": "a1", "target": "nope", "weight": 1},
        {"id": "gone-source", "source": "nope", "target": "a2"},
        {"id": "loop", "source": "a1", "target": "a1"},
        {"id": "no-target", "source": "a1"},
    ]
    result = import_document(raw)
    assert [e.id for e in result.document.edges] == ["ok"]
    dangling = [(r.location, r.detail) for r in result.redactions if r.kind == "dangling_edge"]
    assert dangling == [
        ("edges[1]", "target node not found"),
        ("edges[2]", "source node not found"),
        ("edges[3]", "self-loop"),
        ("edges[4]", "target node not found"),
    ]
    # a dropped edge is reported once, not field by field
    assert "edges[1].weight" not in {r.location for r in result.redactions}


def test_edges_may_be_missing():
    raw = _doc()
    del raw["edges"]
    assert import_document(raw).document.edges == []


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------


def _assert_invalid(raw, **kwargs):
    with pytest.raises(OpenCanalError) as info:
        import_document(raw, **kwargs)
    assert info.value.code == ErrorCode.IMPORT_INVALID
    return info.value


@pytest.mark.parametrize("raw", [None, [], "doc", 3])
def test_non_dict_input_is_invalid(raw):
    _assert_invalid(raw)


def test_missing_title_or_domains_is_invalid():
    raw = _doc()
    del raw["title"]
    _assert_invalid(raw)
    raw = _doc()
    del raw["domains"]
    _assert_invalid(raw)
    _assert_invalid(_doc(), domains=[])
    _assert_invalid(_doc(), title="   ")
    _assert_invalid(_doc(), domains=["", 3])
    # opencrab without arguments or top-level keys
    _assert_invalid(copy.deepcopy(OPENCRAB_SAMPLE), source_format="opencrab")


def test_empty_or_bad_nodes_are_invalid():
    for nodes in ([], None, "nodes", [["a"]], [{"label": "no id"}], [{"id": "x"}], [{"id": "x", "label": "  "}],
                  [{"id": True, "label": "bool id"}], [{"id": "x" * 201, "label": "long id"}]):
        raw = _doc()
        raw["nodes"] = nodes
        _assert_invalid(raw)


def test_duplicate_ids_are_invalid_and_message_does_not_echo_values():
    raw = _doc()
    raw["nodes"][1]["id"] = "a1"
    error = _assert_invalid(raw)
    assert "nodes[1]" in error.message
    raw = _doc()
    raw["edges"].append({"id": "e1", "source": "a2", "target": "a1"})
    _assert_invalid(raw)
    raw = _doc()
    raw["nodes"] = [{"id": "C:\\secret\\a", "label": "A"}, {"id": "C:\\secret\\a", "label": "B"}]
    error = _assert_invalid(raw)
    assert "secret" not in error.message


def test_bad_edges_or_format_are_invalid():
    raw = _doc()
    raw["edges"] = {"e1": {}}
    _assert_invalid(raw)
    raw = _doc()
    raw["edges"] = ["edge"]
    _assert_invalid(raw)
    _assert_invalid(_doc(), source_format="obsidian")


def test_too_many_nodes_is_invalid():
    raw = _doc()
    raw["nodes"] = [{"id": f"n{k}", "label": f"L{k}"} for k in range(2001)]
    _assert_invalid(raw)


# ---------------------------------------------------------------------------
# Hash and determinism
# ---------------------------------------------------------------------------


def test_content_hash_recipe():
    result = import_document(_doc())
    dumped = result.document.model_dump(mode="json")
    expected = json.dumps(dumped, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    import hashlib

    assert result.content_hash == hashlib.sha256(expected.encode("utf-8")).hexdigest()
    assert content_hash(dumped) == result.content_hash
    assert re.fullmatch(r"[0-9a-f]{64}", result.content_hash)


def test_hash_is_stable_and_key_order_independent():
    first = import_document(_doc())
    second = import_document(_doc())
    assert first == second
    shuffled = {k: v for k, v in reversed(list(_doc().items()))}
    shuffled["nodes"] = [dict(reversed(list(n.items()))) for n in shuffled["nodes"]]
    assert import_document(shuffled).content_hash == first.content_hash
    reordered = dict(reversed(list(first.document.model_dump(mode="json").items())))
    assert content_hash(reordered) == first.content_hash


def test_hash_changes_with_content():
    base = import_document(_doc()).content_hash
    assert import_document(_doc(summary="다른 요약")).content_hash != base
    assert import_document(_doc(), title="다른 제목").content_hash != base


def test_redactions_are_deterministic_regardless_of_key_order():
    raw = copy.deepcopy(OPENCRAB_SAMPLE)
    reordered = copy.deepcopy(OPENCRAB_SAMPLE)
    for node in reordered["nodes"]:
        if "properties" in node:
            node["properties"] = dict(reversed(list(node["properties"].items())))
    a = import_document(raw, source_format="opencrab", title="t", domains=["d"])
    b = import_document(reordered, source_format="opencrab", title="t", domains=["d"])
    assert a.redactions == b.redactions
    assert a.content_hash == b.content_hash


def test_sanitized_output_is_a_fixpoint():
    raw = copy.deepcopy(OPENCRAB_SAMPLE)
    raw["nodes"].append({"id": "C:\\Logotekton\\n.md", "label": "경로 노드 /Users/hong/x", "node_type": "x" * 60})
    first = import_document(raw, source_format="opencrab", title="세포 hong@example.com", domains=["세포생물학"])
    again = import_document(first.document.model_dump(mode="json"))
    assert again.redactions == []
    assert again.content_hash == first.content_hash


def test_input_is_not_mutated():
    raw = copy.deepcopy(OPENCRAB_SAMPLE)
    before = copy.deepcopy(raw)
    import_document(raw, source_format="opencrab", title="t", domains=["d"])
    assert raw == before


def test_pydantic_fallback_is_import_invalid_without_echoing_input():
    # passes the pre-check (strip() keeps zero-width chars) but is empty after cleaning
    raw = _doc()
    raw["nodes"][0]["label"] = "​⁠"
    error = _assert_invalid(raw)
    assert "nodes.0.label" in error.message
    assert "​" not in error.message
