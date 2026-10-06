"""Helpers for the Oracle v.4 tests (response walkers, canonicalizers, synthetic subbrains).

Derived from docs/oracle/ORACLE_MANIFEST.md v2026-10-06.4 and the contract code only (models.py, textnorm.py,
config.py, public stub signatures). Kept out of conftest.py so the earlier Oracle tests are untouched.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional

from opencanal.models import SubbrainDocument, SubbrainVersion, Visibility
from opencanal.textnorm import strip_invisible, tokenize

from .conftest import FIXTURE_CONTENT_HASH, FIXTURE_CREATED_AT, REPO_ROOT, dumps

# ---------------------------------------------------------------------------
# Walking envelopes
# ---------------------------------------------------------------------------

Path_ = tuple


def iter_strings(obj: Any, path: Path_ = ()) -> Iterator[tuple[Path_, str]]:
    """(path, text) for every dict key and every string value, depth first."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                yield path + (k,), k
            yield from iter_strings(v, path + (k,))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from iter_strings(v, path + (i,))
    elif isinstance(obj, str):
        yield path, obj


def strings_outside_untrusted(env: dict[str, Any], *, skip_top: Iterable[str] = ()) -> Iterator[tuple[Path_, str]]:
    """Every key/string of an envelope except what lives under the top-level `untrusted_data` key (NEVER-09)."""
    skip = {"untrusted_data", *skip_top}
    for k, v in env.items():
        if k in skip:
            continue
        yield (k,), k
        yield from iter_strings(v, (k,))


def folded(text: str) -> str:
    """What a reader effectively sees: NFKC with invisible characters removed (ORACLE v.4 NEVER-04)."""
    return unicodedata.normalize("NFKC", strip_invisible(text))


def foreign_hits(
    env: dict[str, Any],
    *,
    long_needles: Iterable[str],
    exact_needles: Iterable[str],
    own: Iterable[str] = (),
    skip_top: Iterable[str] = (),
) -> list[tuple[Path_, str, str]]:
    """Places outside `untrusted_data` where another user's string shows up.

    long needles match as substrings (distinctive text: labels, summaries, rationales, names);
    exact needles match only a whole key or string value (short ids such as "e3", single terms such as "건축"),
    so a random id that happens to contain "e3" is not a hit. Strings in `own` (the viewer's own text, echoed
    back) are never hits.
    """
    own_set = set(own)
    longs = sorted({n for n in long_needles if n and n not in own_set}, key=len, reverse=True)
    exact = {n for n in exact_needles if n and n not in own_set}
    hits: list[tuple[Path_, str, str]] = []
    for path, text in strings_outside_untrusted(env, skip_top=skip_top):
        if text in own_set:
            continue
        if text in exact:
            hits.append((path, text, text))
            continue
        for needle in longs:
            if needle in text or needle in folded(text):
                hits.append((path, needle, text))
                break
    return hits


def find_strings(obj: Any, needle: str) -> list[Path_]:
    return [p for p, s in iter_strings(obj) if needle in s]


# ---------------------------------------------------------------------------
# Canonical comparison (NEVER-11: identical responses modulo ids, timestamps and the masked token)
# ---------------------------------------------------------------------------

_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")


def _sorted_lists(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _sorted_lists(v) for k, v in obj.items()}
    if isinstance(obj, list):
        items = [_sorted_lists(v) for v in obj]
        return sorted(items, key=lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True))
    return obj


def canonical(obj: Any, replacements: dict[str, str], *, token_keys: Iterable[str] = ("owner_token",)) -> Any:
    """JSON-equal form with world-specific values replaced by placeholders.

    replacements: server-assigned ids of this world -> stable placeholder. Every value under a `token_keys`
    key becomes "<TOKEN>" wherever it occurs. ISO timestamps become "<TS>". Lists are compared as multisets
    (an order that follows random ids is not an identity leak).
    """
    reps = dict(replacements)
    keys = set(token_keys)

    def collect(o: Any) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k in keys and isinstance(v, str) and v:
                    reps[v] = "<TOKEN>"
                collect(v)
        elif isinstance(o, list):
            for v in o:
                collect(v)

    collect(obj)
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    for old in sorted(reps, key=len, reverse=True):
        text = text.replace(old, reps[old])
    text = _TS_RE.sub("<TS>", text)
    return _sorted_lists(json.loads(text))


def first_difference(a: Any, b: Any, path: Path_ = ()) -> Optional[str]:
    if type(a) is not type(b):
        return f"{path}: {dumps(a)[:300]} != {dumps(b)[:300]}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path + (k,)}: only in {'first' if k in a else 'second'}: {dumps(a.get(k, b.get(k)))[:300]}"
            d = first_difference(a[k], b[k], path + (k,))
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: list length {len(a)} != {len(b)}: {dumps(a)[:300]} vs {dumps(b)[:300]}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_difference(x, y, path + (i,))
            if d:
                return d
        return None
    return None if a == b else f"{path}: {a!r} != {b!r}"


# ---------------------------------------------------------------------------
# Synthetic subbrains for pure matching tests
# ---------------------------------------------------------------------------


def version_from_doc(doc: dict[str, Any], *, subbrain_id: str, owner_id: str, display: str = "") -> SubbrainVersion:
    return SubbrainVersion(
        subbrain_id=subbrain_id,
        version=1,
        owner_id=owner_id,
        owner_display=display or owner_id,
        visibility=Visibility.PUBLIC,
        is_published_version=True,
        content_hash=FIXTURE_CONTENT_HASH,
        created_at=FIXTURE_CREATED_AT,
        document=SubbrainDocument.model_validate(doc),
    )


def reference_relevance(terms: list[str], doc: dict[str, Any], mcfg) -> tuple[float, set[str]]:
    """The frozen relevance formula of the matching stub docstring, computed independently with the contract tokenizer.

    per term t: weight = max over fields (tags, label, summary) of field_weights[field] if t equals a token of that
    field, else field_weights[field] * substring_match_factor if t (len>=2) is a substring of a token;
    relevance = sum(weights) / min(len(terms), denominator_cap).
    """
    if not terms:
        return 0.0, set()

    def toks(texts: Iterable[str]) -> set[str]:
        out: set[str] = set()
        for t in texts:
            out.update(tokenize(t, josa_suffixes=mcfg.josa_suffixes, min_stem=mcfg.josa_min_stem_length))
        return out

    fields = {
        "tags": toks(tag for n in doc["nodes"] for tag in n.get("tags", [])),
        "label": toks(n["label"] for n in doc["nodes"]),
        "summary": toks(n.get("summary") or "" for n in doc["nodes"]),
    }
    total = 0.0
    matched: set[str] = set()
    for t in terms:
        best = 0.0
        for field, tokens in fields.items():
            w = mcfg.field_weights[field]
            if t in tokens:
                best = max(best, w)
            elif len(t) >= 2 and any(t in tok for tok in tokens):
                best = max(best, w * mcfg.substring_match_factor)
        if best > 0:
            matched.add(t)
        total += best
    return total / min(len(terms), mcfg.denominator_cap), matched


# ---------------------------------------------------------------------------
# Subprocess / CLI
# ---------------------------------------------------------------------------


def opencanal_bin() -> Path:
    for cand in (Path(sys.executable).with_name("opencanal"), REPO_ROOT / ".venv" / "bin" / "opencanal"):
        if cand.exists():
            return cand
    raise AssertionError("the `opencanal` console script is not installed in the venv")


def cli_env(db: Path, key_file: Path, **extra: str) -> dict[str, str]:
    """Environment for a CLI subprocess: inherited env minus any OPENCANAL_* (no master-key override), plus ours."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("OPENCANAL_")}
    env.update(
        OPENCANAL_DB=str(db),
        OPENCANAL_KEY_FILE=str(key_file),
        OPENCANAL_CONFIG_DIR=str(REPO_ROOT / "config"),
        **extra,
    )
    return env


def all_text(obj: Any) -> list[str]:
    return [s for _, s in iter_strings(obj)]


def walk_pred(obj: Any, pred: Callable[[str], bool]) -> list[Path_]:
    return [p for p, s in iter_strings(obj) if pred(s)]
