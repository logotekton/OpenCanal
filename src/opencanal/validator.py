"""L1 deterministic validation of a deltabrain submission (ORACLE §4, §5.1).

Owner: Builder V. Pure functions: no DB, no I/O besides the passed config.
"""

from __future__ import annotations

from typing import Any

from .models import CanalContext, DeltabrainStats, DeltabrainSubmission, ValidationResult


def parse_submission(payload: dict[str, Any]) -> tuple[DeltabrainSubmission | None, ValidationResult | None]:
    """Parse raw JSON. On pydantic failure return (None, ValidationResult(ok=False, SCHEMA_INVALID ...))."""
    raise NotImplementedError


def compute_stats(submission: DeltabrainSubmission, ctx: CanalContext) -> DeltabrainStats:
    """Emergent edges = effective provenance owners >= 2; host-touching = effective provenance cites host subbrain."""
    raise NotImplementedError


def validate_deltabrain(
    payload: dict[str, Any] | DeltabrainSubmission,
    ctx: CanalContext,
    *,
    generic_terms: frozenset[str],
    josa_suffixes: list[str] | tuple[str, ...] = (),
    josa_min_stem_length: int = 2,
) -> ValidationResult:
    """Run every L1 check and return ALL violations (not just the first). ok == (no violations)."""
    raise NotImplementedError
