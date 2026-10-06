"""NEVER-04 (pure part) — import keeps only allowed fields and masks paths, emails, phones, URLs."""

from __future__ import annotations

import pytest

from opencanal.models import SUMMARY_MAX_CHARS, OpenCanalError

from .conftest import dumps

RAW_CANONICAL = {
    "title": "현장 실측 메모 /Users/kim/vault/실측.md",
    "domains": ["건축"],
    "source_url": "https://notes.example.com/vault/42",
    "nodes": [
        {
            "id": "r-n1",
            "label": "접합부 실측 C:\\Logotekton\\vault\\접합부.md",
            "summary": "담당 kim.builder@example.com, 010-1234-5678. 원본 https://example.com/raw/1 참고",
            "tags": ["실측"],
            "content": "원문 청크: 회의록 전체 텍스트가 여기에 그대로 들어 있다",
            "source_url": "https://example.com/raw/1",
        },
        {"id": "r-n2", "label": "현장 사진 /home/kim/photos/0001.jpg", "summary": "가" * 400, "tags": ["사진"]},
        {"id": "r-n3", "label": "앵커 볼트 위치", "tags": ["앵커"]},
    ],
    "edges": [
        {"id": "r-e1", "source": "r-n1", "target": "r-n2", "relation": "documents"},
        {"id": "r-e2", "source": "r-n1", "target": "r-n404", "relation": "documents"},
    ],
}

SENSITIVE = (
    "/Users/kim",
    "C:\\Logotekton",
    "Logotekton\\vault",
    "/home/kim",
    "kim.builder@example.com",
    "010-1234-5678",
    "https://",
    "example.com/raw",
    "원문 청크",
    "source_url",
)


def test_never_04_canonical_import_drops_and_masks():
    from opencanal.sanitize import import_document

    result = import_document(RAW_CANONICAL, source_format="canonical")
    doc_text = dumps(result.document.model_dump(mode="json"))
    for s in SENSITIVE:
        assert s not in doc_text, f"kept sensitive value {s!r}"
    kinds = {r.kind for r in result.redactions}
    assert {"dropped_field", "path", "email", "phone", "url", "truncated", "dangling_edge"} <= kinds
    dropped = [r for r in result.redactions if r.kind == "dropped_field"]
    assert any("source_url" in (r.location + r.detail) for r in dropped), "report says what was dropped"
    assert any("content" in (r.location + r.detail) for r in dropped)
    assert [n.id for n in result.document.nodes] == ["r-n1", "r-n2", "r-n3"]
    assert [e.id for e in result.document.edges] == ["r-e1"]
    assert all(len(n.summary or "") <= SUMMARY_MAX_CHARS for n in result.document.nodes)
    assert result.document.nodes[2].label == "앵커 볼트 위치", "clean text is left alone"
    assert len(result.content_hash) == 64 and int(result.content_hash, 16) >= 0


def test_never_04_content_hash_is_deterministic():
    from opencanal.sanitize import content_hash, import_document

    a = import_document(RAW_CANONICAL, source_format="canonical")
    b = import_document(RAW_CANONICAL, source_format="canonical")
    assert a.content_hash == b.content_hash
    doc = a.document.model_dump(mode="json")
    assert content_hash(doc) == content_hash(dict(reversed(list(doc.items())))), "key order does not matter"


def test_never_04_opencrab_import_drops_properties_and_masks_paths():
    from opencanal.sanitize import import_document

    raw = {
        "nodes": [
            {
                "id": "oc-1",
                "label": "접합부 상세 /Users/kim/brain/a.md",
                "node_type": "concept",
                "properties": {
                    "source_url": "https://x.example.com/a",
                    "local_path": "C:\\Logotekton\\pack\\a.md",
                    "raw_chunk": "원문 청크: 팩 원문",
                },
            },
            {"id": "oc-2", "label": "공차 관리", "node_type": "concept", "properties": {}},
        ],
        "edges": [
            {"id": "oc-e1", "from_id": "oc-1", "to_id": "oc-2", "relation": "requires", "properties": {"collected_at": "2026-01-01"}}
        ],
    }
    result = import_document(raw, source_format="opencrab", title="OpenCrab 가져오기", domains=["건축"])
    doc = result.document
    assert doc.title == "OpenCrab 가져오기" and doc.domains == ["건축"]
    assert [n.id for n in doc.nodes] == ["oc-1", "oc-2"]
    assert [(e.source, e.target) for e in doc.edges] == [("oc-1", "oc-2")]
    text = dumps(doc.model_dump(mode="json"))
    for s in ("/Users/kim", "C:\\Logotekton", "https://", "source_url", "원문 청크"):
        assert s not in text, s
    kinds = {r.kind for r in result.redactions}
    assert {"path", "dropped_field"} <= kinds


def test_never_04_unusable_import_is_import_invalid():
    from opencanal.sanitize import import_document

    with pytest.raises(OpenCanalError) as exc:
        import_document({"title": "빈 두뇌", "domains": ["건축"], "nodes": [], "edges": []}, source_format="canonical")
    assert exc.value.code.value == "IMPORT_INVALID"
