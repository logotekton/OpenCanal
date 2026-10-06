"""Integrator tests: seams between modules that each builder's own unit tests fake out.

Real Store(":memory:") + real crypto/sanitize/matching/validator + real config, driven through Service.dispatch.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from opencanal.config import load_config
from opencanal.models import Tier
from opencanal.service import Service
from opencanal.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "brains"
Q01 = "모듈러 건축의 현장 조립 오류를 줄일 아이디어"


def _brain(fid: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{fid}.json").read_text("utf-8"))


def _seed_public(svc: Service, store: Store, fid: str):
    brain = _brain(fid)
    owner = brain["owner"]
    user = store.get_user(owner["user_id"])
    if user is None:
        user, _ = store.create_user(owner["display_name"], Tier(owner["tier"]), user_id=owner["user_id"])
    imported = svc.dispatch(user, "subbrain_import", {"document": brain["document"]})
    assert imported["ok"], imported
    published = svc.dispatch(
        user,
        "subbrain_set_visibility",
        {"subbrain_id": imported["subbrain_id"], "visibility": "public", "confirm_hash": imported["content_hash"]},
    )
    assert published["ok"], published
    return user, imported["subbrain_id"]


def test_injected_service_clock_drives_store_month_for_monthly_canal_limit() -> None:
    """TASK-001 §5: the monthly canal count uses the UTC month of created canals.

    Service derives "this month" from its clock and Store counts canals by the created_at it stamps, so an
    injected clock must reach the store too; otherwise LIMIT_EXCEEDED never fires for a non-current month.
    """
    store = Store(":memory:", master_key=os.urandom(32))
    cfg = load_config()
    fake_now = datetime(2031, 1, 15, 12, 0, tzinfo=timezone.utc)
    svc = Service(store, cfg, clock=lambda: fake_now)

    host_user, host_id = _seed_public(svc, store, "A")
    for fid in ("B", "C"):
        _seed_public(svc, store, fid)

    limit = cfg.limits_for_tier(Tier.FREE).canals_per_month
    for _ in range(limit):
        opened = svc.dispatch(host_user, "canal_open", {"query": Q01, "host_subbrain_id": host_id})
        assert opened["ok"], opened
    got = svc.dispatch(host_user, "canal_get", {"canal_id": opened["canal_id"]})
    assert got["canal"]["created_at"].startswith("2031-01"), got["canal"]["created_at"]
    assert store.count_canals_in_month(host_user.id, "2031-01") == limit

    over = svc.dispatch(host_user, "canal_open", {"query": Q01, "host_subbrain_id": host_id})
    assert over["ok"] is False and over["error"]["code"] == "LIMIT_EXCEEDED", over
    assert store.count_canals_in_month(host_user.id, "2031-01") == limit


def test_service_without_clock_leaves_store_clock_alone() -> None:
    store = Store(":memory:", master_key=os.urandom(32))
    original = store.clock
    Service(store, load_config())
    assert store.clock is original
