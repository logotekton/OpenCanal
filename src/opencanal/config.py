"""Load Oracle-owned runtime configuration from config/.

The files in config/ are frozen for Builders (CLAUDE.md). This loader only reads them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel

from .models import Tier

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = REPO_ROOT / "config"
DEFAULT_DATA_DIR = REPO_ROOT / "data"


class MatchingConfig(BaseModel):
    tau: float
    strategy: str
    strategies_available: list[str]
    field_weights: dict[str, float]
    substring_match_factor: float
    distance_bonus: float = 0.0  # v.5 MUST-M2: score = relevance + distance_bonus * distance
    distance_saturation: float = 0.25  # MUST-M5 v.7: distance = 1 - min(1, (|H∩C|/|H|) / distance_saturation)
    far_distance: float = 0.5  # v.6 MUST-M2: diversity guarantee threshold
    denominator_cap: int
    josa_suffixes: list[str]
    josa_min_stem_length: int
    stopwords: list[str]


class TierLimits(BaseModel):
    max_members_per_canal: int
    canals_per_month: int
    max_public_subbrains: int


class TierConfig(BaseModel):
    tools: list[str]
    limits: TierLimits


class AppConfig(BaseModel):
    matching: MatchingConfig
    tiers: dict[Tier, TierConfig]
    generic_terms: frozenset[str]

    def tools_for_tier(self, tier: Tier) -> list[str]:
        return list(self.tiers[tier].tools)

    def limits_for_tier(self, tier: Tier) -> TierLimits:
        return self.tiers[tier].limits


def _strip_comment_keys(data: dict) -> dict:
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_config(config_dir: Path | str | None = None) -> AppConfig:
    base = Path(config_dir or os.environ.get("OPENCANAL_CONFIG_DIR") or DEFAULT_CONFIG_DIR)
    matching = MatchingConfig(**_strip_comment_keys(json.loads((base / "matching.json").read_text("utf-8"))))
    tiers_raw = json.loads((base / "tiers.json").read_text("utf-8"))["tiers"]
    tiers = {Tier(name): TierConfig(**value) for name, value in tiers_raw.items()}
    generic_terms = frozenset(
        line.strip().lower()
        for line in (base / "generic_terms.txt").read_text("utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    return AppConfig(matching=matching, tiers=tiers, generic_terms=generic_terms)
