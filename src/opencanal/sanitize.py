"""Import + sanitize a brain export into a canonical SubbrainDocument (ORACLE NEVER-04).

Owner: Builder S (tasks/TASK-001.md §4).
"""

from __future__ import annotations

from typing import Any, Literal

from .models import ImportResult


def content_hash(document_json: dict[str, Any]) -> str:
    """sha256 hex of canonical JSON (sort_keys=True, ensure_ascii=False, separators=(",", ":"))."""
    raise NotImplementedError


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
    raise NotImplementedError
