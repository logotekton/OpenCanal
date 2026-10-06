"""NEVER-04 (v.4) — masking on import, extended (ORACLE §5.5 NEVER-04, §9 v.4).

v.4 scope: paths (C:\\, /Users/, /home/, UNC), emails, phone numbers (mobile, landline, 대표번호), URLs with and
without a scheme, 주민등록번호, secrets (oc_, ocm_, sk-, AKIA, ghp_, xox?-, private key blocks); in title, domains,
labels, summaries, tags, edge relations, edge summaries, node ids and edge ids; NFKC and invisible-character removal
happen *before* masking (full-width digits, ＠, zero-width characters); the redaction report never repeats the
original value.

A value counts as leaked if any of its probes occurs in an output string either verbatim or after folding
(NFKC + invisible-character removal) — a reader's screen does the folding for free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from opencanal.textnorm import strip_invisible

from .conftest import World, assert_ok, dumps
from ._v4 import all_text, folded

OC_TOKEN = "oc_" + "kKKzDenbEokG72VBakuQrBqv6hdm3ixIpX-DuTDe_aQ"
OCM_TOKEN = "ocm_ORpPn2gh7c8AF0X67kcBTYMYwRhHS0vLctsElKFj"
SK_KEY = "sk-proj-J5cihDcHgFPoEtj2I5ee6eVC4LLZ6hDlZ28nNqgN"
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
GH_TOKEN = "ghp_5GL7eATlbYzaDgxhENe7SBku0FoJYeAFLGID"
SLACK_TOKEN = "xoxb-504613719889-1649761727070-DjJCBwTOgSUktaA5cJBbrsIV"
PEM_BODY_1 = "MIIBVQIBADANBgkqhkiG9w0BAQEFAASCAT8wggE7AgEAAkEA"
PEM_BODY_2 = "6FosZiw3UdI+B0iSu2B28rDK+mH2Nj1HYduIssDv7HE8FC2W"
PEM_KEY = f"-----BEGIN PRIVATE KEY-----\n{PEM_BODY_1}\n{PEM_BODY_2}\n-----END PRIVATE KEY-----"
PEM_RSA = f"-----BEGIN RSA PRIVATE KEY-----\n{PEM_BODY_2}\n{PEM_BODY_1}\n-----END RSA PRIVATE KEY-----"

BEFORE, AFTER = "접합부점검메모", "확인완료"


@dataclass(frozen=True)
class Case:
    name: str
    raw: str
    kind: str  # models.Redaction.kind
    probes: tuple[str, ...]
    multiline: bool = False
    extra_locations: tuple[str, ...] = field(default=())

    @property
    def fits_relation(self) -> bool:
        return len(self.raw) <= 50 and not self.multiline


CASES = [
    Case("path_windows", "C:\\Logotekton\\vault\\접합부.md", "path", ("C:\\Logotekton", "Logotekton\\vault")),
    Case("path_users", "/Users/kim/vault/실측.md", "path", ("/Users/kim", "kim/vault")),
    Case("path_home", "/home/kim/photos/0001.jpg", "path", ("/home/kim", "kim/photos")),
    Case("path_unc", "\\\\fileserver\\share\\vault\\a.md", "path", ("\\\\fileserver", "fileserver\\share")),
    Case("email", "kim.builder@example.com", "email", ("kim.builder", "builder@example")),
    Case("email_fullwidth", "ｋｉｍ.builder＠example.com", "email", ("kim.builder", "builder@example")),
    Case("email_zero_width", "kim.\u200bbuilder@exam\u200bple.com", "email", ("kim.builder", "builder@example")),
    Case("phone_mobile", "010-1234-5678", "phone", ("1234-5678", "12345678")),
    Case("phone_fullwidth", "０１０－１２３４－５６７８", "phone", ("1234-5678", "12345678")),
    Case("phone_zero_width", "010\u200b-1234\u2060-5678", "phone", ("1234-5678", "12345678")),
    Case("phone_landline_seoul", "02-345-6789", "phone", ("345-6789", "3456789")),
    Case("phone_landline_regional", "031-987-6543", "phone", ("987-6543", "9876543")),
    Case("phone_representative", "1588-1234", "phone", ("1588-1234", "15881234")),
    Case("url_https", "https://notes.example.com/vault/42", "url", ("notes.example.com", "example.com/vault")),
    Case("url_schemeless_www", "www.example.com/vault/42", "url", ("www.example.com", "example.com/vault")),
    Case("url_schemeless_host", "notes.example.co.kr/raw/1", "url", ("notes.example.co.kr", "example.co.kr/raw")),
    Case("rrn", "900101-1234567", "rrn", ("900101-1234567", "9001011234567", "1234567")),
    Case("rrn_fullwidth", "９００１０１－１２３４５６７", "rrn", ("900101-1234567", "9001011234567", "1234567")),
    Case("secret_oc", OC_TOKEN, "secret", (OC_TOKEN[3:19], OC_TOKEN[-16:])),
    Case("secret_ocm", OCM_TOKEN, "secret", (OCM_TOKEN[4:20], OCM_TOKEN[-16:])),
    Case("secret_sk", SK_KEY, "secret", (SK_KEY[8:24], SK_KEY[-16:])),
    Case("secret_aws", AWS_KEY, "secret", ("IOSFODNN7EXAMPLE",)),
    Case("secret_github", GH_TOKEN, "secret", (GH_TOKEN[4:20], GH_TOKEN[-16:])),
    Case("secret_slack", SLACK_TOKEN, "secret", ("504613719889", SLACK_TOKEN[-16:])),
    Case("secret_pem", PEM_KEY, "secret", (PEM_BODY_1[:24], PEM_BODY_1[-16:], PEM_BODY_2[:24], PEM_BODY_2[-16:]), multiline=True),
    Case("secret_pem_rsa", PEM_RSA, "secret", (PEM_BODY_1[:24], PEM_BODY_2[:24]), multiline=True),
]
CASE_BY_NAME = {c.name: c for c in CASES}

TEXT_LOCATIONS = ("title", "label", "summary", "edge_summary")
ALL_LOCATIONS = ("title", "domain", "label", "summary", "tag", "edge_summary", "edge_relation", "node_id", "edge_id")


def base_doc() -> dict[str, Any]:
    return {
        "title": "접합부 점검 기록",
        "domains": ["건축"],
        "nodes": [
            {"id": "n1", "label": "볼트 체결 점검", "summary": "체결 상태를 눈으로 본다.", "tags": ["점검"]},
            {"id": "n2", "label": "공차 기록", "summary": "허용 오차를 적는다.", "tags": ["공차"]},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2", "relation": "requires", "summary": "기록이 있어야 점검한다."}],
    }


def place(doc: dict[str, Any], loc: str, value: str) -> dict[str, Any]:
    wrapped = f"{BEFORE} {value} {AFTER}"
    if loc == "title":
        doc["title"] = wrapped
    elif loc == "domain":
        doc["domains"] = ["건축", value]
    elif loc == "label":
        doc["nodes"][0]["label"] = wrapped
    elif loc == "summary":
        doc["nodes"][0]["summary"] = wrapped
    elif loc == "tag":
        doc["nodes"][0]["tags"] = ["점검", value]
    elif loc == "edge_summary":
        doc["edges"][0]["summary"] = wrapped
    elif loc == "edge_relation":
        doc["edges"][0]["relation"] = value
    elif loc == "node_id":  # a node no edge references (masking an id must not be blocked by edge remapping)
        doc["nodes"].append({"id": f"n-{value}", "label": "고립 노드 표식", "tags": ["표식"]})
    elif loc == "edge_id":
        doc["edges"][0]["id"] = f"e-{value}"
    else:
        raise AssertionError(loc)
    return doc


def applicable(case: Case, loc: str) -> bool:
    if case.multiline and loc not in ("summary", "edge_summary"):
        return False
    if loc == "edge_relation" and not case.fits_relation:
        return False
    return True


MATRIX = [(c.name, loc) for c in CASES for loc in ALL_LOCATIONS if applicable(c, loc)]


def leaks(obj: Any, case: Case) -> list[tuple[str, str]]:
    found = []
    for text in all_text(obj):
        view = folded(text)
        for probe in (*case.probes, case.raw, folded(case.raw)):
            if probe in text or probe in view:
                found.append((probe, text))
    return found


def _import(doc: dict[str, Any]):
    from opencanal.sanitize import import_document

    return import_document(doc, source_format="canonical")


# ---------------------------------------------------------------------------
# Pure: every class in every v.4 location
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_name,loc", MATRIX, ids=[f"{c}-{loc}" for c, loc in MATRIX])
def test_never_04_v4_value_is_masked_everywhere(case_name: str, loc: str):
    case = CASE_BY_NAME[case_name]
    result = _import(place(base_doc(), loc, case.raw))
    doc = result.document.model_dump(mode="json")
    assert not leaks(doc, case), f"{case.name} kept in {loc}: {leaks(doc, case)[:3]}"
    kinds = {r.kind for r in result.redactions}
    assert case.kind in kinds, f"redaction report must say a {case.kind} was masked; got {kinds}"
    report = [r.model_dump(mode="json") for r in result.redactions]
    assert not leaks(report, case), f"the redaction report repeats the original value: {leaks(report, case)[:3]}"


@pytest.mark.parametrize(
    "case_name,loc",
    [(c.name, loc) for c in CASES if not c.kind == "path" and not c.multiline for loc in TEXT_LOCATIONS],
)
def test_never_04_v4_masks_the_value_not_the_whole_text(case_name: str, loc: str):
    """"남은 텍스트 … 의 해당 값은 가린다": the surrounding clean words stay (paths/key blocks excluded — their extent is fuzzy)."""
    case = CASE_BY_NAME[case_name]
    doc = _import(place(base_doc(), loc, case.raw)).document.model_dump(mode="json")
    text = {
        "title": doc["title"],
        "label": doc["nodes"][0]["label"],
        "summary": doc["nodes"][0].get("summary") or "",
        "edge_summary": (doc["edges"][0].get("summary") or "") if doc["edges"] else "",
    }[loc]
    assert BEFORE in text and AFTER in text, f"{loc} lost its clean words: {text!r}"


def test_never_04_v4_invisible_characters_are_removed_on_import():
    """v.4: invisible characters are removed before masking, so none survive into the stored text."""
    doc = base_doc()
    doc["title"] = "접합부\u200b 점검\u3164기록\ufeff"
    doc["domains"] = ["건\u200d축"]
    doc["nodes"][0]["label"] = "볼트\u2060 체결\u00ad 점검\ufe0f"
    doc["nodes"][0]["summary"] = "체결\u3164\u3164상태를\u200b 눈으로\uffa0 본다."
    doc["nodes"][0]["tags"] = ["점\u200b검"]
    doc["edges"][0]["summary"] = "기록이\u200c 있어야\u200e 점검한다."
    result = _import(doc)
    for text in all_text(result.document.model_dump(mode="json")):
        assert strip_invisible(text) == text, f"invisible character kept in {text!r}"


def test_never_04_v4_fullwidth_and_zero_width_values_in_one_summary():
    """Several obfuscated values side by side; all are masked and none is echoed by the report."""
    doc = base_doc()
    doc["nodes"][0]["summary"] = (
        "담당 ｋｉｍ.builder＠example.com, ０１０－１２３４－５６７８, "
        "대표 1588-1234, 주민 ９００１０１－１２３４５６７, 메모 www.example.com/vault/42"
    )
    result = _import(doc)
    out = result.document.model_dump(mode="json")
    report = [r.model_dump(mode="json") for r in result.redactions]
    for name in ("email_fullwidth", "phone_fullwidth", "phone_representative", "rrn_fullwidth", "url_schemeless_www"):
        case = CASE_BY_NAME[name]
        assert not leaks(out, case), f"{name}: {leaks(out, case)[:2]}"
        assert not leaks(report, case), f"{name} echoed by the report"
    assert {"email", "phone", "rrn", "url"} <= {r.kind for r in result.redactions}


# ---------------------------------------------------------------------------
# Through Service.dispatch: import response (preview + report), stored copy, and what others see after publishing
# ---------------------------------------------------------------------------


def _service_doc(case: Case) -> dict[str, Any]:
    doc = base_doc()
    place(doc, "summary", case.raw)
    place(doc, "edge_summary", case.raw)
    place(doc, "node_id", case.raw)
    place(doc, "edge_id", case.raw)
    if not case.multiline:
        place(doc, "label", case.raw)
        place(doc, "tag", case.raw)
        place(doc, "title", case.raw)
    if case.fits_relation:
        place(doc, "edge_relation", case.raw)
    return doc


@pytest.mark.parametrize("case_name", [c.name for c in CASES])
def test_never_04_v4_service_import_preview_store_and_published_copy(world: World, case_name: str):
    case = CASE_BY_NAME[case_name]
    env = assert_ok(world.import_doc("user_a", _service_doc(case)))
    assert env["visibility"] == "private"
    assert not leaks(env, case), f"import response (preview/report) leaks {case.name}: {leaks(env, case)[:3]}"
    assert case.kind in {r["kind"] for r in env["redactions"]}

    sid = env["subbrain_id"]
    own = assert_ok(world.call("user_a", "subbrain_get", subbrain_id=sid))
    assert not leaks(own, case), f"stored copy leaks {case.name}"

    assert_ok(world.call("user_a", "subbrain_set_visibility", subbrain_id=sid, visibility="public", confirm_hash=env["content_hash"]))
    other = assert_ok(world.call("user_b", "subbrain_get", subbrain_id=sid))
    assert "subbrain" in other["untrusted_data"], dumps(other)[:500]
    assert not leaks(other, case), f"published copy leaks {case.name}"
