"""Integrator tests for ORACLE v.6 MUST-M2 at the service seams: unrounded ranking and τ, rounding for display only.

matching.match() compares unrounded values (Builder M's unit tests and tests/oracle pin that). These tests pin what
the service does with the result: canal_open lists and keeps members in match()'s exact ranking, subbrain_search
rounds only what it shows, and match_explain hands the exact ranking to the CLI table. Real Store(":memory:"),
real config with τ / distance_bonus changed through model_copy (config/ is not touched).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from opencanal import cli, matching
from opencanal.config import AppConfig, load_config
from opencanal.models import MatchCandidate, Tier, User
from opencanal.service import Service
from opencanal.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "brains"
Q01 = "모듈러 건축의 현장 조립 오류를 줄일 아이디어"
Q3 = "조립 오류 공차"  # three terms: a tag hit alone gives exactly 1/3


def _cfg(**matching_update: Any) -> AppConfig:
    cfg = load_config()
    return cfg.model_copy(update={"matching": cfg.matching.model_copy(update=matching_update)})


def _user(store: Store, user_id: str, tier: Tier = Tier.FREE) -> User:
    user = store.get_user(user_id)
    if user is None:
        user, _ = store.create_user(user_id, tier, user_id=user_id)
    return store.set_tier(user_id, tier)


def _publish(svc: Service, user: User, document: dict[str, Any]) -> str:
    imported = svc.dispatch(user, "subbrain_import", {"document": document})
    assert imported["ok"], imported
    published = svc.dispatch(
        user,
        "subbrain_set_visibility",
        {"subbrain_id": imported["subbrain_id"], "visibility": "public", "confirm_hash": imported["content_hash"]},
    )
    assert published["ok"], published
    return imported["subbrain_id"]


def _fixture(fid: str) -> tuple[str, dict[str, Any]]:
    brain = json.loads((FIXTURES / f"{fid}.json").read_text("utf-8"))
    return brain["owner"]["user_id"], brain["document"]


def _one_node(title: str, label: str, tags: list[str], summary: str, prefix: str) -> dict[str, Any]:
    return {
        "title": title,
        "domains": ["토목"],
        "nodes": [{"id": f"{prefix}-n1", "label": label, "type": "개념", "tags": tags, "summary": summary}],
        "edges": [],
    }


# T: tag 공차 only -> relevance exactly 1/3 for Q3 (displays 0.3333). L: label 공차 only -> 0.8/3 (displays 0.2667).
T_DOC = _one_node("치수 표", "치수 표", ["공차"], "허용 범위를 적는다.", "t")
L_DOC = _one_node("치수 기록", "공차 기록", ["기록"], "값을 적는다.", "l")


def _tau_world(tau: float) -> tuple[Service, User, dict[str, str]]:
    store = Store(":memory:", master_key=os.urandom(32))
    svc = Service(store, _cfg(tau=tau))
    owner_a, doc_a = _fixture("A")
    host = _user(store, owner_a, Tier.PRO)
    sids = {"A": _publish(svc, host, doc_a)}
    sids["T"] = _publish(svc, _user(store, "user_t"), T_DOC)
    sids["L"] = _publish(svc, _user(store, "user_l"), L_DOC)
    return svc, host, sids


def test_canal_open_keeps_a_member_selected_at_exactly_tau_boundary_one_third() -> None:
    """τ = 0.33333: T (1/3) is eligible unrounded although it displays as 0.3333 (MUST-M2 v.6). canal_open must not
    re-check the rounded relevance against τ and drop it (or answer NO_RELEVANT_SUBBRAIN)."""
    svc, host, sids = _tau_world(0.33333)
    explain = svc.dispatch(host, "match_explain", {"query": Q3, "host_subbrain_id": sids["A"]})
    assert explain["ok"], explain
    by_id = {c["subbrain_id"]: c for c in explain["candidates"]}
    assert by_id[sids["T"]]["relevance"] == 0.3333 and by_id[sids["T"]]["selected"] is True, "self-check"
    assert by_id[sids["L"]]["selected"] is False

    env = svc.dispatch(host, "canal_open", {"query": Q3, "host_subbrain_id": sids["A"]})
    assert env["ok"], env
    assert [m["subbrain_id"] for m in env["members"]] == [sids["T"]]
    assert env["members"][0]["relevance"] == 0.3333

    found = {r["subbrain_id"] for r in svc.dispatch(host, "subbrain_search", {"query": Q3})["untrusted_data"]["results"]}
    assert sids["T"] in found and sids["L"] not in found


def test_canal_open_leaves_out_a_candidate_that_only_displays_at_tau() -> None:
    """τ = 0.26667: L (0.8/3 = 0.26666…) displays as 0.2667 but is below τ; only T is a member."""
    svc, host, sids = _tau_world(0.26667)
    env = svc.dispatch(host, "canal_open", {"query": Q3, "host_subbrain_id": sids["A"]})
    assert env["ok"], env
    assert [m["subbrain_id"] for m in env["members"]] == [sids["T"]]

    found = {r["subbrain_id"] for r in svc.dispatch(host, "subbrain_search", {"query": Q3})["untrusted_data"]["results"]}
    assert sids["T"] in found and sids["L"] not in found


def test_subbrain_search_rounds_relevance_only_for_display() -> None:
    svc, host, sids = _tau_world(0.2)
    env = svc.dispatch(host, "subbrain_search", {"query": Q3})
    assert env["ok"], env
    rows = {r["subbrain_id"]: r for r in env["untrusted_data"]["results"]}
    assert rows[sids["T"]]["relevance"] == 0.3333  # 1/3 shown at DISPLAY_DECIMALS, not 0.333333…
    assert rows[sids["L"]]["relevance"] == 0.2667
    order = [r["subbrain_id"] for r in env["untrusted_data"]["results"]]
    assert order.index(sids["T"]) < order.index(sids["L"])
    shown = [r["relevance"] for r in env["untrusted_data"]["results"]]
    assert shown == sorted(shown, reverse=True)


# MUST-M5 (v.7): from host A, fixtures B and C share 2 of A's 36 label/tag words (오류, 조립): distance 7/9 each.
# `_b_closer` is fixture B with one more of A's words as a tag (공차, not a Q-01 term): 3 of 36, distance 2/3, relevance
# still 0.4. With distance_bonus = 0.0001, Q-01 scores are A2 0.56, C 0.4 + 0.0001 × 7/9 ≈ 0.4000778 and B
# 0.4 + 0.0001 × 2/3 ≈ 0.4000667: both display 0.4001 with relevance 0.4, so sorting the displayed fields falls back
# to subbrain_id. Unrounded, C ranks above B (MUST-M2 v.6, "관련도가 같으면 먼 분야가 위다").
TINY_BONUS = 0.0001


def _b_closer(doc: dict[str, Any]) -> dict[str, Any]:
    first = dict(doc["nodes"][0], tags=[*doc["nodes"][0]["tags"], "공차"])
    return dict(doc, nodes=[first, *doc["nodes"][1:]])


def _q01_world_where_ids_would_mislead() -> tuple[Service, User, dict[str, str]]:
    """Fixtures A (host), A2, B (`_b_closer`), C. Subbrain ids are random; retry until B's id sorts before C's, so an
    id tie-break on the rounded scores would put B first while the exact ranking puts C first."""
    for _ in range(64):
        store = Store(":memory:", master_key=os.urandom(32))
        svc = Service(store, _cfg(distance_bonus=TINY_BONUS))
        sids: dict[str, str] = {}
        users: dict[str, User] = {}
        for fid in ("A", "A2", "B", "C"):
            owner, doc = _fixture(fid)
            users[fid] = _user(store, owner, Tier.EXPERT if fid == "A" else Tier.FREE)
            sids[fid] = _publish(svc, users[fid], _b_closer(doc) if fid == "B" else doc)
        if sids["B"] < sids["C"]:
            return svc, users["A"], sids
        store.close()
    raise AssertionError("could not draw ids with B < C")


def test_canal_open_members_follow_the_exact_ranking_when_scores_round_alike() -> None:
    svc, host, sids = _q01_world_where_ids_would_mislead()
    explain = svc.dispatch(host, "match_explain", {"query": Q01, "host_subbrain_id": sids["A"]})
    assert explain["ok"], explain
    by_id = {c["subbrain_id"]: c for c in explain["candidates"]}
    b, c = by_id[sids["B"]], by_id[sids["C"]]
    assert (b["relevance"], b["score"]) == (c["relevance"], c["score"]) == (0.4, 0.4001), "self-check: rounded tie"
    assert (c["distance"], b["distance"]) == (0.7778, 0.6667), "self-check: C is farther by content"
    rounded = [m.subbrain_id for m in matching.in_rank_order(
        [MatchCandidate.model_validate(x) for x in explain["candidates"]], explain["strategy"]
    )]
    assert rounded.index(sids["B"]) < rounded.index(sids["C"]), "self-check: the rounded sort would mislead"

    env = svc.dispatch(host, "canal_open", {"query": Q01, "host_subbrain_id": sids["A"]})
    assert env["ok"], env
    assert [m["subbrain_id"] for m in env["members"]] == [sids["A2"], sids["C"], sids["B"]]
    assert [s["subbrain_id"] for s in env["untrusted_data"]["subbrains"]] == [sids["A2"], sids["C"], sids["B"]]


def test_match_explain_gives_the_exact_ranking_and_the_cli_table_follows_it() -> None:
    svc, host, sids = _q01_world_where_ids_would_mislead()
    env = svc.dispatch(host, "match_explain", {"query": Q01, "host_subbrain_id": sids["A"]})
    assert env["ok"], env
    ranking = [r["subbrain_id"] for r in env["ranking"]]
    assert ranking[:3] == [sids["A2"], sids["C"], sids["B"]]
    assert sorted(ranking) == sorted(c["subbrain_id"] for c in env["candidates"])
    # candidates themselves stay in relevance order (models.py)
    rels = [c["relevance"] for c in env["candidates"]]
    assert rels == sorted(rels, reverse=True)

    rows = cli._in_rank_order(env["candidates"], env["strategy"], env["ranking"])
    assert [r["subbrain_id"] for r in rows] == ranking


def test_cli_rank_order_falls_back_when_the_ranking_does_not_fit() -> None:
    base = {"version": 1, "owner_id": "u", "relevance": 0.4, "distance": 0.5, "score": 0.55,
            "matched_terms": ["x"], "selected": True, "reason": "selected_score"}
    rows = [dict(base, subbrain_id="sb_b"), dict(base, subbrain_id="sb_a")]
    exact = [{"subbrain_id": "sb_b", "version": 1}, {"subbrain_id": "sb_a", "version": 1}]
    assert [r["subbrain_id"] for r in cli._in_rank_order(rows, "relevance_with_distance_bonus", exact)] == ["sb_b", "sb_a"]
    for bad in (None, "x", exact[:1], exact + [{"subbrain_id": "sb_c", "version": 1}], [exact[0], exact[0]]):
        got = [r["subbrain_id"] for r in cli._in_rank_order(rows, "relevance_with_distance_bonus", bad)]
        assert got == ["sb_a", "sb_b"], bad  # rounded fields tie -> subbrain_id


@pytest.mark.parametrize("value, shown", [(0.6439, "0.6439"), (0.4, "0.4000"), (1.0, "1.0000"), (None, None)])
def test_cli_shows_numbers_at_display_precision(value: Any, shown: Any) -> None:
    assert cli._shown_number(value) == shown
