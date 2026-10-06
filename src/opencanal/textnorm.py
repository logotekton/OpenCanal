"""Text normalization and tokenization shared by the validator and matching.

Rules come from docs/oracle/ORACLE_MANIFEST.md §5.1 (정규화) and config/matching.json
(josa suffixes, stopwords).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
# Hangul fillers render as blank but are letters (Lo), so \w keeps them (ORACLE v.4 정규화).
_HANGUL_FILLERS = frozenset({"\u115f", "\u1160", "\u3164", "\uffa0"})
_WS_RE = re.compile(r"\s+")
_HANGUL_RE = re.compile(r"[가-힣]")


def _is_invisible(ch: str) -> bool:
    if ch in _HANGUL_FILLERS or ch == "\u034f":  # combining grapheme joiner
        return True
    code = ord(ch)
    if 0xFE00 <= code <= 0xFE0F or 0xE0100 <= code <= 0xE01EF:  # variation selectors
        return True
    return unicodedata.category(ch) == "Cf"  # ZWSP/ZWNJ/ZWJ, LRM/RLM, soft hyphen, BOM, tag chars, ...


def strip_invisible(text: str | None) -> str:
    """Remove characters that render as nothing (format chars, Hangul fillers, variation selectors)."""
    if not text:
        return ""
    return "".join(ch for ch in text if not _is_invisible(ch))


def normalize(text: str | None) -> str:
    """ORACLE 정규화: NFKC, invisible chars and punctuation become spaces, lowercase, collapse whitespace, trim.

    Invisible chars become a space (not nothing) so a filler used as a fake separator cannot glue or split
    words differently from what a visible separator would; sanitizing uses strip_invisible() instead.
    """
    if not text:
        return ""
    value = "".join(" " if _is_invisible(ch) else ch for ch in unicodedata.normalize("NFKC", text)).lower()
    value = _PUNCT_RE.sub(" ", value)
    value = value.replace("_", " ")
    return _WS_RE.sub(" ", value).strip()


def is_hangul(token: str) -> bool:
    return bool(_HANGUL_RE.search(token))


def strip_josa(token: str, suffixes: Sequence[str], min_stem: int = 2) -> str:
    """Strip one trailing Korean particle if the remaining stem keeps >= min_stem chars."""
    if not is_hangul(token):
        return token
    for suffix in sorted(suffixes, key=len, reverse=True):
        if token.endswith(suffix) and len(token) - len(suffix) >= min_stem:
            return token[: -len(suffix)]
    return token


def tokenize(
    text: str | None,
    *,
    josa_suffixes: Sequence[str] = (),
    min_stem: int = 2,
    stopwords: Iterable[str] = (),
) -> list[str]:
    """Normalize, split on whitespace, strip josa, drop stopwords. Keeps order, dedups."""
    stop = set(stopwords)
    seen: set[str] = set()
    out: list[str] = []
    for raw in normalize(text).split(" "):
        if not raw:
            continue
        token = strip_josa(raw, josa_suffixes, min_stem)
        if not token or token in stop or raw in stop:
            continue
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out
