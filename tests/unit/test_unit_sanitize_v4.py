"""Unit tests for opencanal.sanitize — ORACLE v.4 NEVER-04 (adversarial review SAN-1..6, GAP-1).

Normalize first (NFKC, invisible characters removed -> "invisible"), then mask secrets, URLs with
or without scheme, local paths, emails, 주민등록번호 and phone numbers in every text field and id.
"""

from __future__ import annotations

import json
import time

import pytest

from opencanal.models import SUMMARY_MAX_CHARS, ErrorCode, OpenCanalError
from opencanal.sanitize import import_document, mask_sensitive, normalize_text


def _doc(summary: str = "요약", **node_extra):
    return {
        "title": "모듈러 건축",
        "domains": ["건축"],
        "nodes": [
            {"id": "a1", "label": "현장 조립 오류", "summary": summary, **node_extra},
            {"id": "a2", "label": "공차 관리"},
        ],
        "edges": [{"id": "e1", "source": "a1", "target": "a2", "relation": "requires"}],
    }


def _blob(result) -> str:
    return json.dumps(result.document.model_dump(mode="json"), ensure_ascii=False)


def _report(result) -> str:
    return json.dumps([r.model_dump() for r in result.redactions], ensure_ascii=False)


def _kinds(result, location: str) -> list[str]:
    return [r.kind for r in result.redactions if r.location == location]


def _masked_whole(text: str, kind: str) -> None:
    masked, hits = mask_sensitive(f"메모 {text} 끝")
    assert masked == f"메모 [REDACTED:{kind.upper()}] 끝", (text, masked)
    assert hits == [kind]


# ---------------------------------------------------------------------------
# SAN-1: paths are masked whole; "/Users/<name>" never survives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "C:\\Users\\kim\\OneDrive - Logotekton Inc\\vault\\a.md",
        "C:\\Users\\Hong Gil Dong\\vault\\secret.md",
        "C:\\Users\\Hong Gildong",
        "c:\\users\\kim\\a.md",
        "C:/Users/kim/a.md",
        "D:\\내 문서\\두뇌 볼트\\비밀.md",
        "C:\\Users\\kim\\Documents\\계약서 최종.docx",
        "\\\\fileserver\\share\\kim\\a.docx",
        "\\\\?\\C:\\Users\\kim\\a.md",
        "\\\\wsl$\\Ubuntu\\home\\kim\\a.md",
        "//fileserver/share/kim/a.docx",
        "%USERPROFILE%\\Documents\\a.md",
        "%APPDATA%/Obsidian/obsidian.json",
        "$HOME/Documents/brain.md",
        "${HOME}/brain.md",
        "$env:USERPROFILE\\Documents\\a.md",
        "~\\Documents\\a.md",
        "/System/Volumes/Data/Users/kim/vault/secret.md",
        "/users/kim/vault/secret.md",
        "/USERS/kim/vault/secret.md",
        "/HOME/kim/vault/secret.md",
        "/Users/kim/My Brain Vault/secret.md",
        "/Users/kim/Library/Mobile Documents/iCloud~md~obsidian/Documents/My Second Brain/a.md",
        "/Users/kim/계약서 최종.hwp",
        "/Volumes/Macintosh HD/Users/kim/a.md",
        "/mnt/c/Users/kim/a.md",
        "/etc/opencanal/keys.json",
        "/opt/opencrab/data/db.sqlite",
        "/Library/Application Support/x/y.db",
    ],
)
def test_paths_are_masked_whole_v4(text):
    _masked_whole(text, "path")


@pytest.mark.parametrize(
    "text",
    ["Macintosh HD/Users/kim/vault/secret.md", "./Users/kim/vault/secret.md", "data/Users/kim/a.md", "Data\\Users\\kim\\a.md"],
)
def test_home_folder_inside_a_longer_path_never_survives(text):
    masked, hits = mask_sensitive(f"메모 {text} 끝")
    assert hits == ["path"]
    for leaked in ("Users", "kim", "secret.md", "a.md"):
        assert leaked not in masked, (text, masked)


@pytest.mark.parametrize(
    "text",
    ["Public /Private 설정", "/system 설정", "/library 책", "work/home/life 균형", "power/users/admin", "README.md/설명"],
)
def test_path_like_prose_is_not_masked(text):
    assert mask_sensitive(text) == (text, [])


# ---------------------------------------------------------------------------
# SAN-2: masking runs on NFKC text (full-width digits, ＠, ／, ：) and Unicode dashes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("０１０-１２３４-５６７８", "phone"),
        ("０１０－１２３４－５６７８", "phone"),
        ("010–1234–5678", "phone"),  # U+2013
        ("010‐1234‐5678", "phone"),  # U+2010
        ("010−1234−5678", "phone"),  # U+2212
        ("010﹘1234﹘5678", "phone"),  # U+FE58
        ("kim.lee＠example.com", "email"),
        ("ｋｉｍ＠ｅｘａｍｐｌｅ．ｃｏｍ", "email"),
        ("／Users／kim／vault", "path"),
        ("C：\\Users\\kim", "path"),
        ("C:＼Users＼kim", "path"),
        ("ｈｔｔｐｓ://example.com/x", "url"),
        ("９００１０１－１２３４５６７", "rrn"),
    ],
)
def test_full_width_and_unicode_dash_variants_are_masked(text, kind):
    _masked_whole(text, kind)


def test_stored_text_is_nfkc_and_hash_follows_it():
    result = import_document(_doc(summary="전화 ０１０-１２３４-５６７８, ＢＩＭ 모델"))
    assert result.document.nodes[0].summary == "전화 [REDACTED:PHONE], BIM 모델"
    assert _kinds(result, "nodes[0].summary") == ["phone"]
    assert "０" not in _blob(result) and "Ｂ" not in _blob(result)


# ---------------------------------------------------------------------------
# SAN-3: Korean landline, virtual and representative numbers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "02)123-4567",
        "031)123-4567",
        "(031)123-4567",
        "(010) 1234-5678",
        "0311234567",
        "0212345678",
        "021234567",
        "07012345678",
        "070-1234-5678",
        "0505-123-4567",
        "0507-1234-5678",
        "080-123-4567",
        "0082-10-1234-5678",
        "+82 010-1234-5678",
        "010 - 1234 - 5678",
        "02 - 123 - 4567",
        "010-1234 5678",
        "02.123.4567",
        "1588-1234",
        "1577 1234",
        "1644.1234",
        "1600-1234",
        "1800-1234",
    ],
)
def test_more_phone_formats_are_masked(text):
    _masked_whole(text, "phone")


@pytest.mark.parametrize(
    "text",
    [
        "1592-1598",  # 임진왜란: not a 대표번호 prefix
        "1600-1700년",  # a span of years, even with a 대표번호 prefix
        "1800-1900년대",
        "1800-1900 년",
        "2026-10-06",
        "2026.10.06",
        "06-10-2026",
        "02-10-2026",
        "v2.0",
        "2.0",
        "10.0.19045",
        "031",
        "1,234,567",
        "12345678",
        "No. 12345",
        "ISO 9001:2015",
        "EN 1993-1-8",
        "10:30~11:00",
    ],
)
def test_numbers_that_are_not_phones_stay(text):
    assert mask_sensitive(text) == (text, [])


@pytest.mark.parametrize(
    "text",
    [
        "1588-2000",  # tail between the prefix and 2100: still a 대표번호 (NEVER-04 v.4)
        "1644-2000",
        "1577-1600",
        "1661-2024",
        "1588 2000",
        "1800-1900",  # a bare year span in a 대표번호 shape is masked too (fail closed)
    ],
)
def test_representative_number_that_looks_like_a_year_span_is_masked(text):
    _masked_whole(text, "phone")


def test_year_span_exemption_needs_a_year_marker():
    assert mask_sensitive("대표번호 1588-2000번") == ("대표번호 [REDACTED:PHONE]번", ["phone"])
    assert mask_sensitive("1600-1700년대 건축") == ("1600-1700년대 건축", [])


# ---------------------------------------------------------------------------
# SAN-4: every invisible character is removed before masking and reported
# ---------------------------------------------------------------------------

INVISIBLE = [
    "\u200b",  # ZWSP
    "\u200c",  # ZWNJ
    "\u200d",  # ZWJ
    "\u200e",  # LRM
    "\u200f",  # RLM
    "\u061c",  # ALM
    "\u00ad",  # soft hyphen
    "\u034f",  # combining grapheme joiner
    "\u180e",  # Mongolian vowel separator
    "\u2060",  # word joiner
    "\u2061",  # function application
    "\u202e",  # RLO
    "\u2066",  # LRI
    "\ufeff",  # BOM
    "\ufe0f",  # variation selector 16
    "\U000e0020",  # tag space
    "\U000e0100",  # variation selector 17
    "\u3164",  # Hangul filler
    "\uffa0",  # half-width Hangul filler
    "\u115f",  # Hangul choseong filler
    "\u1160",  # Hangul jungseong filler
    "\x00",
    "\x1b",
    "\x7f",
    "\x85",
]


@pytest.mark.parametrize("z", INVISIBLE, ids=[f"U+{ord(z):04X}" for z in INVISIBLE])
def test_invisible_characters_cannot_split_a_pattern(z):
    summary = f"전화 010-1234{z}-5678 메일 kim.lee{z}@example.com 경로 /Us{z}ers/kim/secret.md 키 sk-proj-{z}abcdEFGH12345678"
    result = import_document(_doc(summary=summary))
    stored = result.document.nodes[0].summary
    assert stored == "전화 [REDACTED:PHONE] 메일 [REDACTED:EMAIL] 경로 [REDACTED:PATH] 키 [REDACTED:SECRET]"
    assert _kinds(result, "nodes[0].summary") == ["invisible", "secret", "path", "email", "phone"]
    invisible = [r for r in result.redactions if r.kind == "invisible"]
    assert invisible[0].detail == "removed 4 invisible character(s)"


def test_invisible_removal_is_reported_in_every_text_field():
    z = "\u200b"
    raw = {
        "title": f"두{z}뇌",
        "domains": [f"건{z}축"],
        "nodes": [
            {"id": "n1", "label": f"라{z}벨", "type": f"개{z}념", "summary": f"요{z}약", "tags": [f"태{z}그"]},
            {"id": "n2", "label": "공차"},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2", "relation": f"requires{z}", "summary": f"엣{z}지"}],
    }
    result = import_document(raw)
    doc = result.document
    assert (doc.title, doc.domains, doc.nodes[0].label, doc.nodes[0].type) == ("두뇌", ["건축"], "라벨", "개념")
    assert (doc.nodes[0].summary, doc.nodes[0].tags, doc.edges[0].relation, doc.edges[0].summary) == (
        "요약", ["태그"], "requires", "엣지",
    )
    locations = {r.location for r in result.redactions if r.kind == "invisible"}
    assert locations == {
        "title", "domains[0]", "nodes[0].label", "nodes[0].type", "nodes[0].summary", "nodes[0].tags[0]",
        "edges[0].relation", "edges[0].summary",
    }
    assert z not in _blob(result)


def test_mask_sensitive_reports_invisible_first():
    assert mask_sensitive("a\u200bb") == ("ab", ["invisible"])
    assert mask_sensitive("kim\u200b@example.com") == ("[REDACTED:EMAIL]", ["invisible", "email"])


def test_normalize_text_reaches_a_fixpoint():
    for raw in ("e\u200b\u0301", "ㅤ０１\u00ad", "가\u3164나", "plain"):
        text, _ = normalize_text(raw)
        assert normalize_text(text) == (text, 0)
    assert normalize_text("e\u200b\u0301") == ("é", 1)


# ---------------------------------------------------------------------------
# SAN-5: ids go through the same normalization; sensitive ids become pseudonyms
# ---------------------------------------------------------------------------


def test_ids_with_split_sensitive_values_are_pseudonymized_and_edges_follow():
    z = "\u200b"
    raw = {
        "title": "t",
        "domains": ["d"],
        "nodes": [
            {"id": f"kim.lee{z}@example.com", "label": "A"},
            {"id": f"010-1234{z}-5678", "label": "B"},
            {"id": "/Us\u200cers/kim/notes.md", "label": "C"},
            {"id": "９００１０１-１２３４５６７", "label": "D"},
        ],
        "edges": [
            {"id": f"C:{z}\\Users\\kim\\e.md", "source": f"kim.lee{z}@example.com", "target": f"010-1234{z}-5678"},
            # endpoints are matched after normalization too
            {"id": "e2", "source": "kim.lee＠example.com", "target": "/Users/kim/notes.md"},
            {"id": "sk-proj-abcdEFGH12345678", "source": "900101-1234567", "target": f"010-1234{z}-5678"},
        ],
    }
    result = import_document(raw)
    doc = result.document
    assert [n.id for n in doc.nodes] == ["redacted-node-0", "redacted-node-1", "redacted-node-2", "redacted-node-3"]
    assert [(e.id, e.source, e.target) for e in doc.edges] == [
        ("redacted-edge-0", "redacted-node-0", "redacted-node-1"),
        ("e2", "redacted-node-0", "redacted-node-2"),
        ("redacted-edge-2", "redacted-node-3", "redacted-node-1"),
    ]
    assert _kinds(result, "nodes[0].id") == ["invisible", "email"]
    assert _kinds(result, "nodes[1].id") == ["invisible", "phone"]
    assert _kinds(result, "nodes[2].id") == ["invisible", "path"]
    assert _kinds(result, "nodes[3].id") == ["rrn"]
    assert _kinds(result, "edges[0].id") == ["invisible", "path"]
    assert _kinds(result, "edges[2].id") == ["secret"]
    blob, report = _blob(result), _report(result)
    for leaked in ("kim", "example", "1234", "5678", "900101", "Users", "abcdEFGH", "sk-proj"):
        assert leaked not in blob and leaked not in report, leaked


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("/home/kim/photos/0001.jpg", "path"),
        ("~/Documents/a.md", "path"),
        ("oc_kKKzDenbEokG72VBakuQrBqv6hdm3ixIpX-DuTDe_aQ", "secret"),
        ("ocm_ORpPn2gh7c8AF0X67kcBTYMYwRhHS0vLctsElKFj", "secret"),
        ("sk-proj-J5cihDcHgFPoEtj2I5ee6eVC4LLZ6hDlZ28nNqgN", "secret"),
        ("xoxb-504613719889-1649761727070-DjJCBwTOgSUktaA5cJBbrsIV", "secret"),
        ("www.example.com", "url"),
        ("notes.example.co.kr/raw/1", "url"),
        ("192.168.0.10:8080/admin", "url"),
        ("localhost:8765/mcp", "url"),
        ("900101-1234567", "rrn"),
    ],
)
@pytest.mark.parametrize("glue", ["n-", "n_"])
def test_values_glued_into_ids_with_hyphen_or_underscore_are_pseudonymized(value, kind, glue):
    raw = _doc()
    raw["nodes"].append({"id": f"{glue}{value}", "label": "고립 노드"})
    raw["edges"][0]["id"] = f"e{glue[1:]}{value}"
    result = import_document(raw)
    assert result.document.nodes[2].id == "redacted-node-2"
    assert result.document.edges[0].id == "redacted-edge-0"
    assert _kinds(result, "nodes[2].id") == [kind]
    assert _kinds(result, "edges[0].id") == [kind]
    assert value not in _blob(result) and value not in _report(result)


def test_harmless_ids_are_normalized_not_replaced():
    raw = {
        "title": "t",
        "domains": ["d"],
        "nodes": [{"id": "ｎ\u200b1", "label": "A"}, {"id": 2, "label": "B"}],
        "edges": [{"id": "ｅ1", "source": "n1", "target": "２"}],
    }
    result = import_document(raw)
    assert [n.id for n in result.document.nodes] == ["n1", "2"]
    assert [(e.id, e.source, e.target) for e in result.document.edges] == [("e1", "n1", "2")]
    assert _kinds(result, "nodes[0].id") == ["invisible"]
    assert _kinds(result, "edges[0].id") == []


@pytest.mark.parametrize(
    "ids",
    [["a1", "a\u200b1"], ["n1", "ｎ1"], ["\uac00", "\u1100\u1161"]],  # invisible split, full width, decomposed Hangul
)
def test_ids_that_collide_after_normalization_are_invalid_without_echo(ids):
    raw = {"title": "t", "domains": ["d"], "nodes": [{"id": ids[0], "label": "A"}, {"id": ids[1], "label": "B"}]}
    with pytest.raises(OpenCanalError) as info:
        import_document(raw)
    assert info.value.code == ErrorCode.IMPORT_INVALID
    assert "nodes[1] repeats nodes[0]" in info.value.message
    assert ids[0] not in info.value.message


def test_edge_ids_that_collide_after_normalization_are_invalid():
    raw = _doc()
    raw["edges"].append({"id": "ｅ1", "source": "a2", "target": "a1"})
    with pytest.raises(OpenCanalError) as info:
        import_document(raw)
    assert info.value.code == ErrorCode.IMPORT_INVALID


def test_id_made_only_of_invisible_characters_is_invalid_or_dropped():
    raw = _doc()
    raw["nodes"][0]["id"] = "\u200b\u2060"
    raw["edges"] = []
    with pytest.raises(OpenCanalError):
        import_document(raw)
    raw = _doc()
    raw["edges"][0]["id"] = "\u200b"
    result = import_document(raw)
    assert result.document.edges[0].id is None
    assert _kinds(result, "edges[0].id") == ["dropped_field"]


def test_huge_integer_id_is_invalid_not_a_crash():
    raw = _doc()
    raw["nodes"][0]["id"] = 10**5000
    with pytest.raises(OpenCanalError) as info:
        import_document(raw)
    assert info.value.code == ErrorCode.IMPORT_INVALID


# ---------------------------------------------------------------------------
# SAN-6: URLs without a scheme
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "notes.example.co.kr/vault/42",
        "github.com/kim/private-repo",
        "docs.google.com/document/d/1AbCdEfG/edit",
        "example.com/raw/1",
        "GitHub.com/kim",
        "WWW.EXAMPLE.COM/x",
        "www.example.com",
        "192.168.0.10:8080/admin",
        "192.168.0.10:8080",
        "10.0.0.1/admin",
        "localhost:8765/mcp",
        "example.com:8080/x",
        "naver.com/",
    ],
)
def test_urls_without_scheme_are_masked(text):
    _masked_whole(text, "url")


def test_url_without_scheme_glued_to_hangul_keeps_the_particle_out_of_the_prefix():
    masked, hits = mask_sensitive("출처:github.com/kim/repo 참고")
    assert masked == "출처:[REDACTED:URL] 참고"
    assert hits == ["url"]


@pytest.mark.parametrize(
    "text",
    [
        "Node.js/React",
        "B.Arch/M.Arch",
        "ASP.NET/C#",
        "Vue.js/Next.js",
        "e.g./i.e.",
        "Ph.D/M.S",
        "main.py/x",
        "U.S./U.K.",
        "IP 192.168.0.1",
        "example.com",
        "버전 1.2.3.4",
    ],
)
def test_dotted_prose_is_not_a_url(text):
    assert mask_sensitive(text) == (text, [])


# ---------------------------------------------------------------------------
# GAP-1: 주민등록번호 and secrets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["900101-1234567", "9001011234567", "900101 1234567", "900101 - 1234567", "010101-3234567", "900101–2234567", "900101-5234567"],
)
def test_resident_registration_numbers_are_masked(text):
    _masked_whole(text, "rrn")


@pytest.mark.parametrize(
    "text",
    ["901301-1234567", "900132-1234567", "9001015234567", "900101-123456", "1900101-1234567", "20261006"],
)
def test_rrn_lookalikes_stay(text):
    assert mask_sensitive(text) == (text, [])


@pytest.mark.parametrize(
    "text",
    [
        "oc_" + "Ab1-_" * 8 + "xyz",  # this project's MCP token shape
        "ocm_1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d",
        "sk-proj-abcdEFGH1234567890abcdEFGH1234567890",
        "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789",
        "AKIAIOSFODNN7EXAMPLE",
        "ASIAIOSFODNN7EXAMPLE",
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "gho_abcdefghijklmnopqrstuvwxyz0123456789",
        "github_pat_11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz",
        "xoxb-123456789012-123456789012-abcdefghijklmnopqrstuvwx",
        "xoxp-1234567890-abcdef",
        "AIzaSyA1234567890abcdefghijklmnopqrstu",
        "sk_live_abcdefghijklmnop1234",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJraW0ifQ.abc123",
        "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\nBKcwggSjAgEAAoIBAQC7\n-----END PRIVATE KEY-----",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n-----END RSA PRIVATE KEY-----",
        "-----BEGIN OPENSSH PRIVATE KEY-----MIIEvQIBADANBgkqhkiG9w0BAQ",  # cut off: body is masked too
    ],
)
def test_secrets_are_masked(text):
    _masked_whole(text, "secret")


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        ("password=hunter2!", "password=[REDACTED:SECRET]"),
        ('"api_key": "abcd1234efgh"', '"api_key": "[REDACTED:SECRET]"'),
        ("비밀번호: qwer1234!!", "비밀번호: [REDACTED:SECRET]"),
        ("Authorization: Bearer abcdefghijklmnop1234", "Authorization: Bearer [REDACTED:SECRET]"),
        ("CLIENT_SECRET=s3cr3t-value", "CLIENT_SECRET=[REDACTED:SECRET]"),
    ],
)
def test_secret_values_after_a_key_are_masked_and_the_key_stays(text, masked):
    assert mask_sensitive(text) == (masked, ["secret"])


@pytest.mark.parametrize(
    "text",
    [
        "sk-hynix",
        "SK-Hynix 반도체",
        "task-force-team-members-list",
        "oc_import_document_function_helper",
        "doc_" + "A1" * 20,
        "password: 8자 이상",
        "Secret: The Book",
        "secret 정보",
        "api 키 관리",
        "token=abcdefgh",
    ],
)
def test_secret_lookalikes_stay(text):
    assert mask_sensitive(text) == (text, [])


def test_secret_inside_a_url_is_reported_and_gone():
    masked, hits = mask_sensitive("접속 http://127.0.0.1:8765/mcp/oc_" + "Ab1" * 14 + "x 끝")
    assert "oc_" not in masked and "Ab1" not in masked
    assert hits == ["secret", "url"]


def test_rrn_and_secrets_are_masked_in_every_field_and_never_reported_back():
    rrn, key = "900101-1234567", "sk-proj-abcdEFGH1234567890"
    raw = {
        "title": f"두뇌 {rrn}",
        "domains": [f"건축 {key}"],
        "nodes": [
            {"id": "n1", "label": f"라벨 {rrn}", "type": key[:30], "summary": f"요약 {key}", "tags": [rrn]},
            {"id": "n2", "label": "공차"},
        ],
        "edges": [{"source": "n1", "target": "n2", "relation": rrn, "summary": f"요약 {rrn} {key}"}],
    }
    result = import_document(raw)
    assert _kinds(result, "title") == ["rrn"]
    assert _kinds(result, "domains[0]") == ["secret"]
    assert _kinds(result, "nodes[0].label") == ["rrn"]
    assert _kinds(result, "nodes[0].type") == ["secret"]
    assert _kinds(result, "nodes[0].tags[0]") == ["rrn"]
    assert _kinds(result, "edges[0].relation") == ["rrn"]
    assert _kinds(result, "edges[0].summary") == ["secret", "rrn"]
    blob, report = _blob(result), _report(result)
    for leaked in ("900101", "1234567", "abcdEFGH", "sk-proj"):
        assert leaked not in blob and leaked not in report, leaked


# ---------------------------------------------------------------------------
# Truncation, fixpoint, linear time
# ---------------------------------------------------------------------------


def test_a_cut_that_completes_a_phone_number_is_masked_again():
    summary = "가" * 268 + " 010123456789"  # 12 digits: not a phone until the cut drops the last one
    assert mask_sensitive(summary)[1] == []
    result = import_document(_doc(summary=summary))
    stored = result.document.nodes[0].summary
    assert len(stored) <= SUMMARY_MAX_CHARS
    assert "0101234" not in stored
    assert _kinds(result, "nodes[0].summary") == ["truncated", "phone"]
    again = import_document(result.document.model_dump(mode="json"))
    assert again.redactions == [] and again.content_hash == result.content_hash


def test_v4_output_is_a_fixpoint():
    z = "\u200b"
    raw = {
        "title": f"두뇌 900101-1234567 ｋｉｍ＠ｅｘａｍｐｌｅ．ｃｏｍ",
        "domains": ["건축 github.com/kim/repo"],
        "nodes": [
            {"id": f"010-1234{z}-5678", "label": "AKIAIOSFODNN7EXAMPLE 키", "summary": "password=hunter22 02)123-4567 C:\\Users\\Hong Gil Dong\\a.md"},
            {"id": "n2", "label": "공차 1588-1234", "tags": ["/users/kim/x", "-----BEGIN PRIVATE KEY-----MIIE"]},
        ],
        "edges": [{"id": "sk-proj-abcdEFGH12345678", "source": f"010-1234{z}-5678", "target": "n2"}],
    }
    first = import_document(raw)
    again = import_document(first.document.model_dump(mode="json"))
    assert again.redactions == []
    assert again.content_hash == first.content_hash


def test_new_patterns_are_linear_on_long_runs():
    n = 40_000
    runs = [
        "-----BEGIN PRIVATE KEY-----" + "AB CD " * n + "끝",
        "password=" * (n // 9),
        "sk-" + "a" * n,
        "a." * n + "/",
        "a-" * n + ".com/x",
        "/Users/a" + " Bb" * n,
        "C:\\" + "a b c d " * (n // 8),
        "/tmp/" + "a Bb Cc Dd " * (n // 11),
        "%a%" * (n // 3),
        "//" * n,
        "a@" + "가." * n,
        "900101 " * (n // 7),
        "010 - " * (n // 6),
        "+82 " + "12 " * n,
    ]
    start = time.perf_counter()
    for text in runs:
        mask_sensitive(text)
    assert time.perf_counter() - start < 2.0
