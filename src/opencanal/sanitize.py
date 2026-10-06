"""Import + sanitize a brain export into a canonical SubbrainDocument (ORACLE NEVER-04).

Owner: Builder S (tasks/TASK-001.md §4).

Pipeline (same for both formats): keep only allowed fields -> mask sensitive text ->
truncate -> drop dangling edges -> validate as SubbrainDocument. Masking runs before
truncation so a cut can never leave a fragment the patterns no longer recognize.
Every Redaction.location points into the *input* (raw indices and raw key names), and
no Redaction ever carries the removed value itself.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from .models import (
    MAX_TAGS_PER_NODE,
    SUMMARY_MAX_CHARS,
    ErrorCode,
    ImportResult,
    OpenCanalError,
    Redaction,
    SubbrainDocument,
)

TITLE_MAX_CHARS = 200
LABEL_MAX_CHARS = 200
ID_MAX_CHARS = 200
TYPE_MAX_CHARS = 50
RELATION_MAX_CHARS = 50
TAG_MAX_CHARS = 50
DOMAIN_MAX_CHARS = 50
MAX_DOMAINS = 10
MAX_NODES = 2000
MAX_EDGES = 5000

_TOP_KEYS = frozenset({"title", "domains", "nodes", "edges"})
_CANONICAL_NODE_KEYS = frozenset({"id", "label", "type", "summary", "tags"})
_CANONICAL_EDGE_KEYS = frozenset({"id", "source", "target", "relation", "summary"})
_OPENCRAB_NODE_KEYS = frozenset({"id", "label", "node_type", "properties"})
_OPENCRAB_EDGE_KEYS = frozenset({"id", "from_id", "to_id", "relation", "properties"})

# ---------------------------------------------------------------------------
# Sensitive-text patterns. Order matters: URL first (a URL contains paths and
# sometimes emails), then paths (a path may contain an email-like segment), then
# emails, then phones. Mask tokens contain no pattern trigger, so masking is a fixpoint.
# ---------------------------------------------------------------------------

# Scheme length is bounded so a long letter run is not rescanned from every position.
_URL_RE = re.compile(
    r"(?:[A-Za-z][A-Za-z0-9+.\-]{0,31}://|www\.)"
    r"[^\s<>\"'`()\[\]{}]*[^\s<>\"'`()\[\]{}.,;:!?]"
)

# A path segment may contain one inner space if another separator follows it
# ("C:\Users\Hong Gildong\x.txt"). Only one, so a later "3/4" in the same sentence does
# not swallow the prose between. The last segment stops at whitespace and does not end
# in sentence punctuation.
_WIN_SEG = r"[^\s\\/:*?\"<>|]+"
_WIN_LAST = r"(?:[^\s\\/:*?\"<>|]*[^\s\\/:*?\"<>|.,;!)\]'])?"
_WIN_TAIL = rf"(?:{_WIN_SEG}(?: {_WIN_SEG})?[\\/]+)*{_WIN_LAST}"
_UNIX_SEG = r"[^\s/]+"
_UNIX_LAST = r"(?:[^\s/]*[^\s/.,;:!?)\]'\"])?"
_UNIX_TAIL = rf"(?:{_UNIX_SEG}(?: {_UNIX_SEG})?/+)*{_UNIX_LAST}"
_UNIX_ROOTS = "Users|home|root|private|tmp|var|Volumes|mnt|media|opt|srv|etc|usr"
# ASCII-only lookbehinds: Hangul right before a path ("경로/Users/...") must not block it.
_PATH_RE = re.compile(
    rf"(?<![A-Za-z0-9])[A-Za-z]:[\\/]+{_WIN_TAIL}"  # C:\..., C:/...
    rf"|(?<!\\)\\\\(?=[^\s\\/]){_WIN_TAIL}"  # \\server\share\...
    rf"|(?<![A-Za-z0-9._~/\\-])/(?:{_UNIX_ROOTS})(?![A-Za-z0-9_\-])(?:/+{_UNIX_TAIL})?"
    rf"|(?<![A-Za-z0-9._~/\\-])~[A-Za-z0-9_.\-]*/+{_UNIX_TAIL}"  # ~/..., ~user/...
)

# The lookbehind starts a match only at the beginning of a local-part run (linear time).
_EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")

# (?<!\d)/(?!\d) instead of \b: Hangul and digits are both \w, so "010-...입니다" has no \b.
_PHONE_RE = re.compile(
    r"(?<![A-Za-z0-9+])\+\d{1,3}[-. ]?(?:\(0\)[-. ]?)?\(?\d{1,4}\)?(?:[-. ]?\d{2,4}){2,3}(?!\d)"  # +82 10-1234-5678
    r"|(?<!\d)01[016789][-. ]?\d{3,4}[-. ]?\d{4}(?!\d)"  # 010-1234-5678, 01012345678
    r"|(?<!\d)(?:\(0\d{1,2}\)[-. ]?|0\d{1,2}[-. ])\d{3,4}[-. ]\d{4}(?!\d)"  # 02-123-4567, (031) 123-4567
)

_MASKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("url", _URL_RE),
    ("path", _PATH_RE),
    ("email", _EMAIL_RE),
    ("phone", _PHONE_RE),
)

# Invisible characters that could split a pattern and slip past masking
# (zero-width space, word joiner, BOM, bidi controls, C0 controls except \t \n \r).
_INVISIBLE_RE = re.compile(r"[\u200b\u2060-\u2064\ufeff\u202a-\u202e\u2066-\u2069\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def mask_sensitive(text: str) -> tuple[str, list[str]]:
    """Mask URLs, paths, emails and phone numbers. Returns (masked_text, kinds in hit order)."""
    hits: list[str] = []
    for kind, pattern in _MASKERS:
        token = f"[REDACTED:{kind.upper()}]"

        def _replace(_match: re.Match[str], kind: str = kind, token: str = token) -> str:
            hits.append(kind)
            return token

        text = pattern.sub(_replace, text)
    return text, hits


def content_hash(document_json: dict[str, Any]) -> str:
    """sha256 hex of canonical JSON (sort_keys=True, ensure_ascii=False, separators=(",", ":"))."""
    if isinstance(document_json, BaseModel):  # tolerate a SubbrainDocument
        document_json = document_json.model_dump(mode="json")
    payload = json.dumps(document_json, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invalid(message: str) -> OpenCanalError:
    return OpenCanalError(ErrorCode.IMPORT_INVALID, message)


class _Report:
    def __init__(self) -> None:
        self.items: list[Redaction] = []

    def add(self, location: str, kind: str, detail: str = "") -> None:
        self.items.append(Redaction(location=location, kind=kind, detail=detail))


def _join(base: str, key: Any) -> str:
    # Key names are input too: mask them before they appear in a location string.
    name, _ = mask_sensitive(_INVISIBLE_RE.sub("", str(key)))
    name = name[:64]
    return f"{base}.{name}" if base else name


def _unknown_keys(obj: dict[str, Any], allowed: frozenset[str], base: str) -> list[str]:
    return [_join(base, key) for key in sorted(obj, key=str) if key not in allowed]


def _clean_text(value: str, location: str, report: _Report, max_chars: int) -> str:
    text, hits = mask_sensitive(_INVISIBLE_RE.sub("", value).strip())
    for kind in hits:
        report.add(location, kind)
    if len(text) > max_chars:
        report.add(location, "truncated", f"{len(text)} -> {max_chars} chars")
        text = text[:max_chars].rstrip()
    return text


def _optional_text(value: Any, location: str, report: _Report, max_chars: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        report.add(location, "dropped_field", "expected a string")
        return None
    return _clean_text(value, location, report, max_chars) or None


def _clean_tags(value: Any, location: str, report: _Report) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        report.add(location, "dropped_field", "expected a list of strings")
        return []
    tags: list[str] = []
    for k, tag in enumerate(value):
        if len(tags) == MAX_TAGS_PER_NODE:
            report.add(location, "truncated", f"kept the first {MAX_TAGS_PER_NODE} of {len(value)} tags")
            break
        tag_location = f"{location}[{k}]"
        if not isinstance(tag, str):
            report.add(tag_location, "dropped_field", "expected a string")
            continue
        text = _clean_text(tag, tag_location, report, TAG_MAX_CHARS)
        if text:
            tags.append(text)
    return tags


def _id_text(value: Any) -> str | None:
    """Ids may be strings or integers (stringified). Anything else is not an id."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value)
    if not text.strip() or len(text) > ID_MAX_CHARS:
        return None
    return text


def _pseudonym(prefix: str, index: int, taken: set[str]) -> str:
    candidate = f"redacted-{prefix}-{index}"
    n = 2
    while candidate in taken:
        candidate = f"redacted-{prefix}-{index}-{n}"
        n += 1
    taken.add(candidate)
    return candidate


def _plan_ids(raw_ids: list[str], prefix: str) -> list[str]:
    """Final ids: an id that contains a URL/path/email/phone is replaced as a whole by a
    position-based pseudonym (partial masking would collide). Other ids stay as they are
    so node ids remain stable across versions."""
    taken = set(raw_ids)
    return [
        _pseudonym(prefix, i, taken) if mask_sensitive(raw)[1] else raw
        for i, raw in enumerate(raw_ids)
    ]


def _report_id(raw: str, final: str, location: str, report: _Report) -> None:
    if raw != final:
        for kind in mask_sensitive(raw)[1]:
            report.add(location, kind, "id replaced")


def _properties(
    props: Any, base: str, *, with_tags: bool
) -> tuple[dict[str, tuple[Any, str]], list[str]]:
    """Map OpenCrab `properties` -> summary (+ tags). Every other sub-key is dropped."""
    if props is None:
        return {}, []
    if not isinstance(props, dict):
        return {}, [base]
    fields: dict[str, tuple[Any, str]] = {}
    summary_key = next(
        (k for k in ("summary", "description") if isinstance(props.get(k), str) and props[k].strip()),
        None,
    )
    if summary_key is not None:
        fields["summary"] = (props[summary_key], f"{base}.{summary_key}")
    if with_tags and isinstance(props.get("tags"), list):
        fields["tags"] = (props["tags"], f"{base}.tags")
    used = {summary_key, "tags" if "tags" in fields else None}
    dropped = [_join(base, key) for key in sorted(props, key=str) if key not in used]
    return fields, dropped


def _node_fields(node: dict[str, Any], i: int, fmt: str) -> tuple[dict[str, tuple[Any, str]], list[str]]:
    """{canonical field: (raw value, input location)} plus the input locations dropped."""
    base = f"nodes[{i}]"
    if fmt == "canonical":
        fields = {k: (node[k], f"{base}.{k}") for k in ("label", "type", "summary", "tags") if k in node}
        return fields, _unknown_keys(node, _CANONICAL_NODE_KEYS, base)
    fields = {}
    if "label" in node:
        fields["label"] = (node["label"], f"{base}.label")
    if "node_type" in node:
        fields["type"] = (node["node_type"], f"{base}.node_type")
    prop_fields, prop_dropped = _properties(node.get("properties"), f"{base}.properties", with_tags=True)
    fields.update(prop_fields)
    return fields, _unknown_keys(node, _OPENCRAB_NODE_KEYS, base) + prop_dropped


def _edge_fields(edge: dict[str, Any], j: int, fmt: str) -> tuple[dict[str, tuple[Any, str]], list[str]]:
    base = f"edges[{j}]"
    if fmt == "canonical":
        fields = {k: (edge[k], f"{base}.{k}") for k in ("source", "target", "relation", "summary") if k in edge}
        return fields, _unknown_keys(edge, _CANONICAL_EDGE_KEYS, base)
    fields = {}
    for src, dst in (("from_id", "source"), ("to_id", "target"), ("relation", "relation")):
        if src in edge:
            fields[dst] = (edge[src], f"{base}.{src}")
    prop_fields, prop_dropped = _properties(edge.get("properties"), f"{base}.properties", with_tags=False)
    fields.update(prop_fields)
    return fields, _unknown_keys(edge, _OPENCRAB_EDGE_KEYS, base) + prop_dropped


# ---------------------------------------------------------------------------
# Document parts
# ---------------------------------------------------------------------------


def _clean_title(raw: dict[str, Any], title: str | None, report: _Report) -> str:
    value = title if title is not None else raw.get("title")
    if not isinstance(value, str) or not value.strip():
        raise _invalid("title is required (a non-empty string)")
    return _clean_text(value, "title", report, TITLE_MAX_CHARS)


def _clean_domains(raw: dict[str, Any], domains: list[str] | None, report: _Report) -> list[str]:
    value: Any = domains if domains is not None else raw.get("domains")
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value:
        raise _invalid("domains is required (a non-empty list of strings)")
    out: list[str] = []
    for k, domain in enumerate(value):
        if len(out) == MAX_DOMAINS:
            report.add("domains", "truncated", f"kept the first {MAX_DOMAINS} of {len(value)} domains")
            break
        if not isinstance(domain, str):
            report.add(f"domains[{k}]", "dropped_field", "expected a string")
            continue
        text = _clean_text(domain, f"domains[{k}]", report, DOMAIN_MAX_CHARS)
        if text:
            out.append(text)
    if not out:
        raise _invalid("domains must contain at least one non-empty string")
    return out


def _clean_nodes(raw_nodes: list[Any], fmt: str, report: _Report) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Returns the cleaned nodes and a map raw id -> final id (for edge endpoints)."""
    raw_ids: list[str] = []
    first_seen: dict[str, int] = {}
    for i, node in enumerate(raw_nodes):
        if not isinstance(node, dict):
            raise _invalid(f"nodes[{i}] must be an object")
        node_id = _id_text(node.get("id"))
        if node_id is None:
            raise _invalid(f"nodes[{i}].id must be a non-empty string of at most {ID_MAX_CHARS} chars")
        if node_id in first_seen:
            raise _invalid(f"duplicate node id: nodes[{i}] repeats nodes[{first_seen[node_id]}]")
        first_seen[node_id] = i
        raw_ids.append(node_id)
    final_ids = _plan_ids(raw_ids, "node")

    nodes: list[dict[str, Any]] = []
    for i, node in enumerate(raw_nodes):
        fields, dropped = _node_fields(node, i, fmt)
        for location in dropped:
            report.add(location, "dropped_field")
        _report_id(raw_ids[i], final_ids[i], f"nodes[{i}].id", report)
        label, label_location = fields.get("label", (None, f"nodes[{i}].label"))
        if not isinstance(label, str) or not label.strip():
            raise _invalid(f"{label_location} must be a non-empty string")
        cleaned: dict[str, Any] = {
            "id": final_ids[i],
            "label": _clean_text(label, label_location, report, LABEL_MAX_CHARS),
            "type": None,
            "summary": None,
            "tags": [],
        }
        if "type" in fields:
            cleaned["type"] = _optional_text(*fields["type"], report, TYPE_MAX_CHARS)
        if "summary" in fields:
            cleaned["summary"] = _optional_text(*fields["summary"], report, SUMMARY_MAX_CHARS)
        if "tags" in fields:
            cleaned["tags"] = _clean_tags(*fields["tags"], report)
        nodes.append(cleaned)
    return nodes, dict(zip(raw_ids, final_ids))


def _clean_edges(
    raw_edges: list[Any], fmt: str, id_map: dict[str, str], report: _Report
) -> list[dict[str, Any]]:
    for j, edge in enumerate(raw_edges):
        if not isinstance(edge, dict):
            raise _invalid(f"edges[{j}] must be an object")
    raw_edge_ids = [_id_text(edge.get("id")) for edge in raw_edges]
    taken = {eid for eid in raw_edge_ids if eid is not None}

    edges: list[dict[str, Any]] = []
    first_seen: dict[str, int] = {}
    for j, edge in enumerate(raw_edges):
        fields, dropped = _edge_fields(edge, j, fmt)
        endpoints = {}
        for end in ("source", "target"):
            raw_end = _id_text(fields.get(end, (None, ""))[0])
            endpoints[end] = id_map.get(raw_end) if raw_end is not None else None
        if endpoints["source"] is None or endpoints["target"] is None:
            missing = "source" if endpoints["source"] is None else "target"
            report.add(f"edges[{j}]", "dangling_edge", f"{missing} node not found")
            continue
        if endpoints["source"] == endpoints["target"]:
            report.add(f"edges[{j}]", "dangling_edge", "self-loop")
            continue

        for location in dropped:
            report.add(location, "dropped_field")
        edge_id: str | None = None
        if edge.get("id") is not None:
            raw_id = raw_edge_ids[j]
            if raw_id is None:
                report.add(f"edges[{j}].id", "dropped_field", f"expected a string of at most {ID_MAX_CHARS} chars")
            elif mask_sensitive(raw_id)[1]:
                edge_id = _pseudonym("edge", j, taken)
                _report_id(raw_id, edge_id, f"edges[{j}].id", report)
            else:
                edge_id = raw_id
        if edge_id is not None:
            if edge_id in first_seen:
                raise _invalid(f"duplicate edge id: edges[{j}] repeats edges[{first_seen[edge_id]}]")
            first_seen[edge_id] = j
        cleaned: dict[str, Any] = {
            "id": edge_id,
            "source": endpoints["source"],
            "target": endpoints["target"],
            "relation": None,
            "summary": None,
        }
        if "relation" in fields:
            cleaned["relation"] = _optional_text(*fields["relation"], report, RELATION_MAX_CHARS)
        if "summary" in fields:
            cleaned["summary"] = _optional_text(*fields["summary"], report, SUMMARY_MAX_CHARS)
        edges.append(cleaned)
    return edges


def _describe(exc: ValidationError) -> str:
    # include_input=False: never echo raw values back in an error message.
    parts = [
        f"{'.'.join(str(p) for p in err['loc']) or 'document'}: {err['msg']}"
        for err in exc.errors(include_url=False, include_context=False, include_input=False)[:5]
    ]
    return "document is not a valid subbrain: " + "; ".join(parts)


def import_document(
    raw: dict[str, Any],
    *,
    source_format: Literal["canonical", "opencrab"] = "canonical",
    title: str | None = None,
    domains: list[str] | None = None,
) -> ImportResult:
    """Sanitize `raw` into an ImportResult.

    canonical: {"title", "domains", "nodes": [{id,label,type?,summary?,tags?}], "edges": [{id?,source,target,relation?,summary?}]}
    opencrab:  {"nodes": [{id,label,node_type,properties{...}}], "edges": [{id,from_id,to_id,relation,properties{...}}]}
               `title` and `domains` must be given as arguments (or present at top level).

    Must: keep only allowed fields (report every dropped field as Redaction kind="dropped_field");
    mask Windows/Unix/home paths, emails, phone numbers, URLs inside title/label/summary/tags/domains
    (Redaction kinds path/email/phone/url, masked as "[REDACTED:PATH]" etc.); truncate summaries to
    SUMMARY_MAX_CHARS ("truncated"); drop edges whose endpoints do not exist ("dangling_edge").
    Raises OpenCanalError(IMPORT_INVALID) when the result would not be a valid SubbrainDocument.
    """
    if source_format not in ("canonical", "opencrab"):
        raise _invalid("format must be 'canonical' or 'opencrab'")
    if not isinstance(raw, dict):
        raise _invalid("document must be a JSON object")
    raw_nodes = raw.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise _invalid("nodes is required (a non-empty list)")
    if len(raw_nodes) > MAX_NODES:
        raise _invalid(f"too many nodes ({len(raw_nodes)} > {MAX_NODES})")
    raw_edges = raw.get("edges")
    if raw_edges is None:
        raw_edges = []
    if not isinstance(raw_edges, list):
        raise _invalid("edges must be a list")

    report = _Report()
    for location in _unknown_keys(raw, _TOP_KEYS, ""):
        report.add(location, "dropped_field")
    doc_title = _clean_title(raw, title, report)
    doc_domains = _clean_domains(raw, domains, report)
    nodes, id_map = _clean_nodes(raw_nodes, source_format, report)
    edges = _clean_edges(raw_edges, source_format, id_map, report)
    if len(edges) > MAX_EDGES:
        raise _invalid(f"too many edges ({len(edges)} > {MAX_EDGES})")

    try:
        document = SubbrainDocument.model_validate(
            {"title": doc_title, "domains": doc_domains, "nodes": nodes, "edges": edges}
        )
    except ValidationError as exc:
        raise _invalid(_describe(exc)) from None
    return ImportResult(
        document=document,
        content_hash=content_hash(document.model_dump(mode="json")),
        redactions=report.items,
    )
