"""Import + sanitize a brain export into a canonical SubbrainDocument (ORACLE NEVER-04, v.4).

Owner: Builder S (tasks/TASK-001.md §4).

Pipeline (same for both formats): keep only allowed fields -> normalize every text field
and id (NFKC, then drop invisible characters) -> mask sensitive text -> truncate -> drop
dangling edges -> validate as SubbrainDocument. Normalizing first means full-width digits,
"＠", "／" and zero-width splits cannot hide a value from the patterns. Masking runs before
truncation so a cut can never leave a fragment the patterns no longer recognize, and a cut
is masked again in case it completed a pattern. Every Redaction.location points into the
*input* (raw indices and raw key names), and no Redaction ever carries the removed value.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
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
from .textnorm import strip_invisible

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
# Sensitive-text patterns. They run on normalized text (NFKC, no invisible chars).
# Lookbehinds before secrets, roots and URLs do not block "-" or "_": those glue values
# into ids ("n-sk-...", "n_/home/...", "n_github.com/x").
# Order matters: secrets first (a token can contain a phone-like digit run), then URLs
# (a URL contains paths and sometimes emails), then paths (a path may contain an
# email-like segment), emails, resident registration numbers, phones (an RRN contains
# phone-like digit runs). Mask tokens contain no pattern trigger, so masking is a fixpoint.
# ---------------------------------------------------------------------------

# Dashes NFKC does not fold to "-" (U+2010-2015, U+2212, U+FE58); "－" and "﹣" fold already.
_DASHES = r"\-\u2010-\u2015\u2212\ufe58\ufe63\uff0d"

_PEM_HEAD = r"-----BEGIN[A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?-----"
_PEM_END = r"-----END[A-Z0-9 ]{0,40}PRIVATE KEY(?: BLOCK)?-----"
_SECRET_RE = re.compile(
    # Through the END line, or (no END line) through the base64 body; possessive, so linear.
    rf"{_PEM_HEAD}(?:[A-Za-z0-9+/=\s:,.\-]*?{_PEM_END}|(?:\s*+[A-Za-z0-9+/=:,.\-]++)*+)"
    # oc_/ocm_ (this project's tokens), sk-...: must contain an upper-case letter or a digit
    # somewhere, so snake_case identifiers such as oc_import_document_helper stay.
    r"|(?<![A-Za-z0-9])(?:ocm?_|sk-)(?=[A-Za-z0-9_\-]{0,63}[A-Z0-9])[A-Za-z0-9_\-]{16,}"
    r"|(?<![A-Za-z0-9])(?:AKIA|ASIA)[0-9A-Z]{16,}"
    r"|(?<![A-Za-z0-9])(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"
    r"|(?<![A-Za-z0-9])xox[abposr]-[A-Za-z0-9\-]{10,}"
    r"|(?<![A-Za-z0-9])AIza[0-9A-Za-z_\-]{30,}"
    r"|(?<![A-Za-z0-9])[rs]k_live_[A-Za-z0-9]{16,}"
    r"|(?<![A-Za-z0-9])eyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]*"  # JWT
)
# password=..., "api_key": "...", 비밀번호: ... -> only the value is masked (group "keep" stays).
_SECRET_KEYS = (
    r"(?<![A-Za-z0-9])(?i:pass(?:word|wd|phrase)|pwd|(?:client[_-]?)?secret(?:[_-]?key)?|api[_-]?key"
    r"|access[_-]?(?:key|token)|private[_-]?key|auth[_-]?token|refresh[_-]?token)|비밀번호|패스워드"
)
_SECRET_VALUE_RE = re.compile(
    rf"(?P<keep>(?:{_SECRET_KEYS})[\"']?[ \t]{{0,3}}[:=][ \t]{{0,3}}[\"']?)"
    r"(?!\[REDACTED:)(?=[^\s\"',;]{0,63}[A-Za-z0-9])[^\s\"',;]{6,}"
)
_BEARER_RE = re.compile(r"(?P<keep>(?<![A-Za-z0-9])[Bb]earer[ \t]+)[A-Za-z0-9._~+/\-]{16,}=*")

# Scheme length is bounded so a long letter run is not rescanned from every position.
_URL_CHAR = r"[^\s<>\"'`()\[\]{}]"
_URL_END = r"[^\s<>\"'`()\[\]{}.,;:!?]"
_URL_PATH = rf"/(?:{_URL_CHAR}*{_URL_END})?"
# Scheme-less URLs need a known TLD and a "/": "Node.js/React" and "B.Arch/M.Arch" are prose.
# Lower-case TLDs only, so "ASP.NET/C#" stays too.
_TLDS = (
    "com|net|org|edu|gov|mil|int|info|biz|io|ai|app|dev|co|me|tv|xyz|site|online|tech|cloud|page|blog"
    "|news|shop|store|wiki|link|live|gg|ly|kr|jp|cn|uk|de|fr|us|ca|au|in|ru|eu|nl|ch|se|fi|it|es|br|tw"
    "|hk|sg|vn|th|id|ph|nz|be|at|dk|pl|cz|il|tr|mx|ar|za|ie|pt|gr|hu|ro|ua|ae|한국"
)
_HOST = r"(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+"
_URL_RE = re.compile(
    rf"(?:[A-Za-z][A-Za-z0-9+.\-]{{0,31}}://|(?<![A-Za-z0-9.])(?i:www)\.){_URL_CHAR}*{_URL_END}"
    rf"|(?<![A-Za-z0-9@./\\])(?:"
    rf"{_HOST}(?:{_TLDS})(?![A-Za-z0-9\-])(?::\d{{1,5}})?{_URL_PATH}"  # github.com/kim/repo
    rf"|(?:(?:\d{{1,3}}\.){{3}}\d{{1,3}}|(?i:localhost))(?::\d{{1,5}}(?!\d)(?:{_URL_PATH})?|{_URL_PATH})"
    r")"
)

# A Windows segment may contain up to three inner spaces if another separator follows it
# ("OneDrive - Org Name\", "Hong Gil Dong\"). A Unix segment may contain one inner space,
# plus up to two more ASCII words ("My Second Brain/"); stricter, so a later "3/4" or
# "~/x" in the same sentence does not swallow the prose between. The last segment stops at
# whitespace and does not end in sentence punctuation, unless its words end in a file
# extension ("계약서 최종.docx", "Hong Gil Dong.txt").
_EXT_END = r"\.[A-Za-z][A-Za-z0-9]{0,4}"
_WIN_SEG = r"[^\s\\/:*?\"<>|]+"
_WIN_LAST = (
    rf"(?:(?:{_WIN_SEG} ){{1,3}}[^\s\\/:*?\"<>|]*{_EXT_END}(?![^\s.,;!)\]'])"
    r"|[^\s\\/:*?\"<>|]*[^\s\\/:*?\"<>|.,;!)\]'])?"
)
# A user folder at the very end keeps its capitalized words: "C:\Users\Hong Gildong".
_WIN_USER_END = (
    r"(?:(?<=[Uu][Ss][Ee][Rr][Ss][\\/])|(?<=[Uu][Ss][Ee][Rr][Ss][\\/][\\/]))"
    r"[A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*){1,2}(?![^\s.,;!)\]'])"
)
_WIN_TAIL = rf"(?:{_WIN_SEG}(?: {_WIN_SEG}){{0,3}}[\\/]+)*(?:{_WIN_USER_END}|{_WIN_LAST})"
_UNIX_SEG = r"[^\s/]+"
_UNIX_WORD = r"[A-Za-z][A-Za-z0-9._\-]+"
_UNIX_LAST = (
    rf"(?:(?:{_UNIX_SEG} ){{1,2}}[^\s/]*{_EXT_END}(?![^\s.,;:!?)\]'\"])"
    r"|[^\s/]*[^\s/.,;:!?)\]'\"])?"
)
_UNIX_TAIL = rf"(?:{_UNIX_SEG}(?: {_UNIX_SEG})?(?: {_UNIX_WORD}){{0,2}}/+)*{_UNIX_LAST}"
_UNIX_ROOTS = "Users|home|root|private|tmp|var|Volumes|mnt|media|opt|srv|etc|usr"
# Any case, but only with a sub-path ("Public /Private" is prose): macOS file systems are
# case-insensitive, so /users/kim is the same home folder.
_UNIX_ROOTS_CI = rf"(?i:{_UNIX_ROOTS}|System|Library|Applications|cygdrive)"
# ASCII-only lookbehinds: Hangul right before a path ("경로/Users/...") must not block it.
_PATH_RE = re.compile(
    rf"(?<![A-Za-z0-9])[A-Za-z]:[\\/]+{_WIN_TAIL}"  # C:\..., C:/...
    rf"|(?<!\\)\\\\(?:[?.]\\(?:[A-Za-z]:[\\/]*)?)?(?=[^\s\\/]){_WIN_TAIL}"  # \\server\share, \\?\C:\...
    rf"|(?<![A-Za-z0-9:/\\.])//(?=[A-Za-z0-9])[^\s/\\]+/(?=[^\s/]){_UNIX_TAIL}"  # //server/share/...
    rf"|(?<![A-Za-z0-9.~/\\])/(?:{_UNIX_ROOTS})(?![A-Za-z0-9_\-])(?:/+{_UNIX_TAIL})?"  # /Users/..., /tmp
    rf"|(?<![A-Za-z0-9.~/\\])/{_UNIX_ROOTS_CI}/+(?=[^\s/]){_UNIX_TAIL}"  # /users/kim, /System/Volumes/...
    # A home folder anywhere: "Macintosh HD/Users/kim", "./Users/kim", "Data\Users\kim".
    rf"|/(?:Users|USERS)/(?=[^\s/]){_UNIX_TAIL}"
    rf"|\\(?i:Users)\\(?=[^\s\\/]){_WIN_TAIL}"
    rf"|(?<![A-Za-z0-9.~/\\])~[A-Za-z0-9_.\-]*(?:/+{_UNIX_TAIL}|\\+{_WIN_TAIL})"  # ~/..., ~user/..., ~\...
    rf"|%[A-Za-z_][A-Za-z0-9_()]*%[\\/]+{_WIN_TAIL}"  # %USERPROFILE%\...
    rf"|\$(?:env:[A-Za-z_][A-Za-z0-9_]*|\{{[A-Za-z_][A-Za-z0-9_]*\}}|[A-Z_][A-Z0-9_]*)[\\/]+{_WIN_TAIL}"  # $HOME/...
)

# The lookbehind starts a match only at the beginning of a local-part run (linear time).
# Unicode letters are allowed ("김철수@example.com"); an ASCII TLD stops at the first
# non-ASCII letter so a particle stays ("kim@example.com으로").
_EMAIL_RE = re.compile(r"(?<![\w.%+\-])[\w.%+\-]+@[\w\-]+(?:\.[\w\-]+)*\.(?:[A-Za-z]{2,}|[^\W\d_]{2,})")

# 주민등록번호 / 외국인등록번호: YYMMDD-GNNNNNN with a valid month and day. Without a
# separator only G in 1-4 (fewer false positives on 13-digit codes).
_RRN_SEP = rf"[ \t]{{0,2}}[{_DASHES}][ \t]{{0,2}}|[ \t]{{1,2}}"
_RRN_RE = re.compile(
    rf"(?<!\d)\d{{2}}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?:(?:{_RRN_SEP})[1-8]|[1-4])\d{{6}}(?!\d)"
)

# (?<!\d)/(?!\d) instead of \b: Hangul and digits are both \w, so "010-...입니다" has no \b.
_SEP = rf"(?:[ \t]{{0,2}}[{_DASHES}.][ \t]{{0,2}}|[ \t]{{1,2}})"
# Mobile 01x, Seoul 02, area 031-065, 050x safe numbers, 060/070/080.
_KR_PREFIX = r"0(?:1[016789]|2|[3-6][1-5]|50\d|[678]0)"
_REP_PREFIX = r"1(?:5(?:22|33|44|55|66|77|88|99)|6(?:00|11|22|33|44|55|61|66|68|70|88|99)|8(?:00|11|33|55|66|77|99))"
_PHONE_RE = re.compile(
    # +82 10-1234-5678, 0082-10-1234-5678, +44 20 7946 0958
    rf"(?:(?<![A-Za-z0-9+])\+|(?<!\d)00(?=[1-9]))\d{{1,3}}{_SEP}?(?:\(0\){_SEP}?)?\(?\d{{1,4}}\)?(?:{_SEP}?\d{{2,4}}){{2,3}}(?!\d)"
    # 010-1234-5678, 01012345678, 0311234567, 02)123-4567, (031) 123-4567, 0505-123-4567
    rf"|(?<!\d)(?:\({_KR_PREFIX}\)[ \t]{{0,2}}|{_KR_PREFIX}\)[ \t]{{0,2}}|{_KR_PREFIX}{_SEP}?)\d{{3,4}}{_SEP}?\d{{4}}(?!\d)"
    # 1588-1234 (대표번호): a separator is required
    rf"|(?<!\d)(?<!\d\.)(?P<rep>{_REP_PREFIX}){_SEP}(?P<rep_tail>\d{{4}})(?!\d)"
)


_YEAR_MARK_RE = re.compile(r"[ \t]?[년年]")


def _is_year_range(match: re.Match[str]) -> bool:
    """A span of years such as 1600-1700년 (in a 대표번호 shape) is not a phone number.

    Only with a year marker right after it: a bare 1588-2000 is a real 대표번호 (NEVER-04 v.4), so without the
    marker we mask (fail closed) and accept that a bare "1800-1900" is masked too.
    """
    if match.group("rep") is None:
        return False
    first, second = int(match.group("rep")), int(match.group("rep_tail"))
    return first < second <= 2100 and _YEAR_MARK_RE.match(match.string, match.end()) is not None


_MASKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("secret", _SECRET_RE),
    ("secret", _SECRET_VALUE_RE),
    ("secret", _BEARER_RE),
    ("url", _URL_RE),
    ("path", _PATH_RE),
    ("email", _EMAIL_RE),
    ("rrn", _RRN_RE),
    ("phone", _PHONE_RE),
)

# textnorm.strip_invisible covers format characters (Cf), Hangul fillers and variation
# selectors; control characters (Cc) render as nothing too. \t \n \r stay.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _strip(text: str) -> str:
    if not text.isascii():
        text = strip_invisible(text)
    return _CONTROL_RE.sub("", text)


def normalize_text(value: str) -> tuple[str, int]:
    """NFKC, then drop invisible characters (ORACLE v.4 NEVER-04). Returns (text, chars removed)."""
    text = unicodedata.normalize("NFKC", value)
    stripped = _strip(text)
    removed = len(text) - len(stripped)
    # Removing a character can let its neighbours compose; one more pass reaches the fixpoint.
    if removed and not unicodedata.is_normalized("NFKC", stripped):
        text = unicodedata.normalize("NFKC", stripped)
        stripped = _strip(text)
        removed += len(text) - len(stripped)
    return stripped, removed


def _mask(text: str) -> tuple[str, list[str]]:
    """Mask already-normalized text. Returns (masked_text, kinds in hit order)."""
    hits: list[str] = []
    for kind, pattern in _MASKERS:
        token = f"[REDACTED:{kind.upper()}]"

        def _replace(match: re.Match[str], kind: str = kind, token: str = token) -> str:
            if kind == "phone" and _is_year_range(match):
                return match.group(0)
            hits.append(kind)
            keep = match.groupdict().get("keep") or ""
            return keep + token

        text = pattern.sub(_replace, text)
    return text, hits


def mask_sensitive(text: str) -> tuple[str, list[str]]:
    """Normalize (NFKC, drop invisible characters), then mask secrets, URLs, paths, emails,
    resident registration numbers and phone numbers. Returns (masked_text, kinds in hit
    order); "invisible" comes first when characters were removed."""
    normalized, removed = normalize_text(text)
    masked, hits = _mask(normalized)
    return masked, (["invisible"] if removed else []) + hits


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

    def invisible(self, location: str, removed: int) -> None:
        if removed:
            self.add(location, "invisible", f"removed {removed} invisible character(s)")


def _cut(text: str, max_chars: int) -> tuple[str, list[str]]:
    """Cut to max_chars. A cut can complete a pattern its next character used to break
    ("010-1234-56789" cut after the 8), so the cut text is masked again until it is stable."""
    hits: list[str] = []
    for _ in range(4):
        text, more = _mask(text[:max_chars].rstrip())
        hits += more
        if len(text) <= max_chars:
            return text, hits
    return text[:max_chars].rstrip(), hits


def _join(base: str, key: Any) -> str:
    # Key names are input too: mask them before they appear in a location string.
    name, _ = mask_sensitive(str(key))
    name, _ = _cut(name, 64)
    return f"{base}.{name}" if base else name


def _unknown_keys(obj: dict[str, Any], allowed: frozenset[str], base: str) -> list[str]:
    return [_join(base, key) for key in sorted(obj, key=str) if key not in allowed]


def _clean_text(value: str, location: str, report: _Report, max_chars: int) -> str:
    text, removed = normalize_text(value)
    report.invisible(location, removed)
    text, hits = _mask(text.strip())
    for kind in hits:
        report.add(location, kind)
    if len(text) > max_chars:
        report.add(location, "truncated", f"{len(text)} -> {max_chars} chars")
        text, hits = _cut(text, max_chars)
        for kind in hits:
            report.add(location, kind)
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


def _id_text(value: Any) -> tuple[str | None, int]:
    """Ids may be strings or integers (stringified) and are normalized like text.
    Returns (normalized id or None if unusable, invisible chars removed)."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None, 0
    if isinstance(value, int) and value.bit_length() > 700:  # > 200 digits; str() could raise
        return None, 0
    text, removed = normalize_text(str(value))
    if not text.strip() or len(text) > ID_MAX_CHARS:
        return None, removed
    return text, removed


def _is_sensitive(text: str) -> bool:
    return bool(_mask(text)[1])


def _pseudonym(prefix: str, index: int, taken: set[str]) -> str:
    candidate = f"redacted-{prefix}-{index}"
    n = 2
    while candidate in taken:
        candidate = f"redacted-{prefix}-{index}-{n}"
        n += 1
    taken.add(candidate)
    return candidate


def _plan_ids(ids: list[str], prefix: str) -> list[str]:
    """Final ids: an id that contains a secret/URL/path/email/RRN/phone is replaced as a whole
    by a position-based pseudonym (partial masking would collide). Other ids stay as they are
    (normalized) so node ids remain stable across versions."""
    taken = set(ids)
    return [_pseudonym(prefix, i, taken) if _is_sensitive(text) else text for i, text in enumerate(ids)]


def _report_id(normalized: str, removed: int, final: str, location: str, report: _Report) -> None:
    report.invisible(location, removed)
    if normalized != final:
        for kind in _mask(normalized)[1]:
            report.add(location, kind, "id replaced")


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(normalize_text(value)[0].strip())


def _properties(
    props: Any, base: str, *, with_tags: bool
) -> tuple[dict[str, tuple[Any, str]], list[str]]:
    """Map OpenCrab `properties` -> summary (+ tags). Every other sub-key is dropped."""
    if props is None:
        return {}, []
    if not isinstance(props, dict):
        return {}, [base]
    fields: dict[str, tuple[Any, str]] = {}
    summary_key = next((k for k in ("summary", "description") if _has_text(props.get(k))), None)
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


def _duplicate(kind: str, later: int, first: int, raw: list[Any]) -> OpenCanalError:
    # Index-only message: never echo the id itself.
    how = "" if str(raw[later]) == str(raw[first]) else " after NFKC and removing invisible characters"
    return _invalid(f"duplicate {kind} id: {kind}s[{later}] repeats {kind}s[{first}]{how}")


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
    """Returns the cleaned nodes and a map normalized id -> final id (for edge endpoints)."""
    ids: list[str] = []
    removed: list[int] = []
    first_seen: dict[str, int] = {}
    for i, node in enumerate(raw_nodes):
        if not isinstance(node, dict):
            raise _invalid(f"nodes[{i}] must be an object")
        node_id, n_removed = _id_text(node.get("id"))
        if node_id is None:
            raise _invalid(f"nodes[{i}].id must be a non-empty string of at most {ID_MAX_CHARS} chars")
        if node_id in first_seen:
            raise _duplicate("node", i, first_seen[node_id], [n.get("id") for n in raw_nodes])
        first_seen[node_id] = i
        ids.append(node_id)
        removed.append(n_removed)
    final_ids = _plan_ids(ids, "node")

    nodes: list[dict[str, Any]] = []
    for i, node in enumerate(raw_nodes):
        fields, dropped = _node_fields(node, i, fmt)
        for location in dropped:
            report.add(location, "dropped_field")
        _report_id(ids[i], removed[i], final_ids[i], f"nodes[{i}].id", report)
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
    return nodes, dict(zip(ids, final_ids))


def _clean_edges(
    raw_edges: list[Any], fmt: str, id_map: dict[str, str], report: _Report
) -> list[dict[str, Any]]:
    for j, edge in enumerate(raw_edges):
        if not isinstance(edge, dict):
            raise _invalid(f"edges[{j}] must be an object")
    edge_ids = [_id_text(edge.get("id")) for edge in raw_edges]
    taken = {eid for eid, _ in edge_ids if eid is not None}

    edges: list[dict[str, Any]] = []
    first_seen: dict[str, int] = {}
    for j, edge in enumerate(raw_edges):
        fields, dropped = _edge_fields(edge, j, fmt)
        endpoints = {}
        for end in ("source", "target"):
            end_id, _ = _id_text(fields.get(end, (None, ""))[0])
            endpoints[end] = id_map.get(end_id) if end_id is not None else None
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
            normalized, n_removed = edge_ids[j]
            if normalized is None:
                report.add(f"edges[{j}].id", "dropped_field", f"expected a string of at most {ID_MAX_CHARS} chars")
            else:
                if normalized in first_seen:
                    raise _duplicate("edge", j, first_seen[normalized], [e.get("id") for e in raw_edges])
                first_seen[normalized] = j
                edge_id = _pseudonym("edge", j, taken) if _is_sensitive(normalized) else normalized
                _report_id(normalized, n_removed, edge_id, f"edges[{j}].id", report)
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
    normalize title/domains/label/type/summary/tags/relation and node/edge ids (NFKC, invisible
    characters removed -> "invisible"); mask secrets, URLs (with or without scheme), local paths,
    emails, resident registration numbers and phone numbers in them (kinds secret/url/path/email/
    rrn/phone, masked as "[REDACTED:SECRET]" etc.; an id that holds one is replaced by a
    "redacted-node-<i>" / "redacted-edge-<j>" pseudonym and edges follow it); truncate summaries to
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
