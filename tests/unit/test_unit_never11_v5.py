"""NEVER-11 v.5 ("엮을 수도 없게"): no response lets a non-owner participant link a now-private contributor across
different canals or deltabrains. Real Store + crypto + validator + Service; canals are created with
store.create_canal directly so these tests do not depend on the matching strategy.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from opencanal import crypto
from opencanal.config import load_config
from opencanal.models import CanalMember, QueryMode, Tier, User
from opencanal.service import Service
from opencanal.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "brains"
DELTAS = Path(__file__).resolve().parents[2] / "fixtures" / "deltabrains"
Q01 = "모듈러 건축의 현장 조립 오류를 줄일 아이디어"


def _brain(fid: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{fid}.json").read_text("utf-8"))


def _text(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _ok(env: dict[str, Any]) -> dict[str, Any]:
    assert env.get("ok") is True, env
    return env


def _good01(sids: dict[str, str]) -> dict[str, Any]:
    delta = json.loads((DELTAS / "good-01.json").read_text("utf-8"))
    for item in [*delta["nodes"], *delta["edges"]]:
        for ref in item.get("provenance", []):
            ref["subbrain_id"], ref["version"] = sids[ref["subbrain_id"].removeprefix("sb_")], 1
    return delta


def _members(store: Store, sids: dict[str, str], fids: list[str]) -> list[CanalMember]:
    out = []
    for fid in fids:
        sv = store.get_subbrain_for_viewer(_brain(fid)["owner"]["user_id"], sids[fid])
        out.append(CanalMember(subbrain_id=sv.subbrain_id, version=sv.version, owner_id=sv.owner_id, relevance=0.5,
                               distance=1.0, matched_terms=["조립"]))
    return out


@pytest.fixture
def world():
    """Canal 1: host A (user_a) with B, C, one accepted deltabrain. Canal 2: host A2 (user_e) with A, B, C, one
    deltabrain citing C. user_b and user_c take part in both canals."""
    master_key = os.urandom(32)
    store = Store(":memory:", master_key=master_key)
    svc = Service(store, load_config())
    users: dict[str, User] = {}
    sids: dict[str, str] = {}
    for fid in ("A", "B", "C", "A2"):
        owner = _brain(fid)["owner"]
        users[owner["user_id"]], _ = store.create_user(owner["display_name"], Tier.PRO, user_id=owner["user_id"])
        imported = _ok(svc.dispatch(users[owner["user_id"]], "subbrain_import", {"document": _brain(fid)["document"]}))
        _ok(svc.dispatch(users[owner["user_id"]], "subbrain_set_visibility", {
            "subbrain_id": imported["subbrain_id"], "visibility": "public", "confirm_hash": imported["content_hash"],
        }))
        sids[fid] = imported["subbrain_id"]
    canal1 = store.create_canal("user_a", sids["A"], 1, Q01, QueryMode.TOPIC, _members(store, sids, ["B", "C"]))
    canal2 = store.create_canal("user_e", sids["A2"], 1, Q01, QueryMode.TOPIC, _members(store, sids, ["A", "B", "C"]))
    db1 = _ok(svc.dispatch(users["user_a"], "canal_submit", {"canal_id": canal1.id, "deltabrain": _good01(sids)}))
    delta2 = {
        "nodes": [
            {"id": "q", "kind": "query", "label": Q01},
            {"id": "s-e", "kind": "source", "label": _brain("A2")["document"]["nodes"][0]["label"],
             "provenance": [{"subbrain_id": sids["A2"], "version": 1, "node_id": "e-n1"}]},
            {"id": "s-c", "kind": "source", "label": _brain("C")["document"]["nodes"][0]["label"],
             "provenance": [{"subbrain_id": sids["C"], "version": 1, "node_id": "c-n1"}]},
        ],
        "edges": [
            {"id": "e-q", "source": "q", "target": "s-e", "relation": "requires"},
            {"id": "e-x", "source": "s-c", "target": "s-e", "relation": "applies_to",
             "rationale": "단백질이 형태가 맞을 때만 결합하는 원리를 목조 모듈 접합부에 옮기면 잘못 끼우는 조립을 형상으로 막을 수 있다."},
        ],
    }
    db2 = svc.dispatch(users["user_e"], "canal_submit", {"canal_id": canal2.id, "deltabrain": delta2})
    return {"store": store, "svc": svc, "users": users, "sids": sids, "key": master_key,
            "canal1": canal1.id, "canal2": canal2.id, "db1": db1["deltabrain_id"],
            "db2": db2["deltabrain_id"] if db2.get("ok") else None, "db2_env": db2}


def _call(w: dict[str, Any], uid: str, tool: str, **args: Any) -> dict[str, Any]:
    return w["svc"].dispatch(w["users"][uid], tool, args)


def _deltabrain_responses(w: dict[str, Any], uid: str, db: str) -> dict[str, Any]:
    got = _ok(_call(w, uid, "deltabrain_get", deltabrain_id=db))
    responses = {
        "get": got,
        "list": _ok(_call(w, uid, "deltabrain_list")),
        "export": _ok(_call(w, uid, "deltabrain_export", deltabrain_id=db)),
        "rate_unknown": _call(w, uid, "deltabrain_rate", deltabrain_id=db, target_id="no-such-edge", novelty=1,
                              validity=1, usefulness=1),
    }
    stats = got["untrusted_data"]["deltabrain"]["stats"]
    for target in [*stats["bridge_node_ids"], *stats["emergent_edge_ids"]]:  # v.8 rating units
        responses[f"rate:{target}"] = _ok(_call(w, uid, "deltabrain_rate", deltabrain_id=db, target_id=target,
                                                novelty=1, validity=0, usefulness=1))
    responses["get_after_rating"] = _ok(_call(w, uid, "deltabrain_get", deltabrain_id=db))
    return responses


def _withheld(env: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            if o.get("withheld") is True:
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(env)
    return found


def test_self_check_world(world):
    assert world["db2"] is not None, world["db2_env"]


def test_withheld_member_gets_a_ref_that_differs_per_canal(world):
    w, c_sid = world, world["sids"]["C"]
    _ok(_call(w, "user_c", "subbrain_set_visibility", subbrain_id=c_sid, visibility="private"))
    refs = {}
    for canal in ("canal1", "canal2"):
        got = _ok(_call(w, "user_b", "canal_get", canal_id=w[canal]))
        marks = _withheld(got)
        assert len(marks) == 2, marks  # canal.members row + untrusted_data.subbrains entry
        assert all(set(m) == {"withheld", "withheld_ref"} for m in marks), marks
        assert len({m["withheld_ref"] for m in marks}) == 1, "same subbrain, same canal -> same ref"
        refs[canal] = marks[0]["withheld_ref"]
        assert refs[canal] == crypto.withheld_ref(w["key"], w[canal], c_sid)
        text = _text(got)
        assert c_sid not in text and "user_c" not in text and _brain("C")["owner"]["display_name"] not in text
    assert refs["canal1"] != refs["canal2"], "a withheld subbrain must not be linkable across canals"
    # Stable across calls.
    assert _withheld(_ok(_call(w, "user_b", "canal_get", canal_id=w["canal1"])))[0]["withheld_ref"] == refs["canal1"]
    # The owner sees the real ids in both canals.
    for canal in ("canal1", "canal2"):
        own = _ok(_call(w, "user_c", "canal_get", canal_id=w[canal]))
        assert _withheld(own) == [] and c_sid in _text(own)


def test_withheld_host_ids_are_gone_from_canal_get(world):
    w, a_sid = world, world["sids"]["A"]
    _ok(_call(w, "user_a", "subbrain_set_visibility", subbrain_id=a_sid, visibility="private"))
    as_host = _ok(_call(w, "user_b", "canal_get", canal_id=w["canal1"]))
    as_member = _ok(_call(w, "user_b", "canal_get", canal_id=w["canal2"]))
    for got in (as_host, as_member):
        assert a_sid not in _text(got)
        assert _brain("A")["owner"]["display_name"] not in _text(got)
    host_ref = as_host["untrusted_data"]["host"]["withheld_ref"]
    assert as_host["canal"]["host_withheld_ref"] == host_ref
    member_ref = _withheld(as_member)[0]["withheld_ref"]
    assert host_ref != member_ref, "the private host of canal 1 and the private member of canal 2 must not link"
    own = _ok(_call(w, "user_a", "canal_get", canal_id=w["canal1"]))
    assert own["canal"]["host_subbrain_id"] == a_sid and own["untrusted_data"]["host"]["withheld"] is False


def test_private_member_leaves_no_real_id_in_any_deltabrain_response(world):
    w, c_sid = world, world["sids"]["C"]
    _ok(_call(w, "user_c", "subbrain_set_visibility", subbrain_id=c_sid, visibility="private"))
    tokens = set()
    for db in ("db1", "db2"):
        for viewer in ("user_b",) if db == "db1" else ("user_b", "user_a"):
            responses = _deltabrain_responses(w, viewer, w[db])
            for name, env in responses.items():
                text = _text(env)
                assert c_sid not in text, f"{viewer} {db} {name}"
                assert "user_c" not in text and _brain("C")["owner"]["display_name"] not in text, f"{viewer} {db} {name}"
            masked = [r for n in responses["get"]["untrusted_data"]["deltabrain"]["nodes"] for r in n["provenance"]
                      if r["owner_id"] is None]
            assert masked and all(r["subbrain_id"] is None and r["version"] is None and r["node_id"] is None
                                  for r in masked)
            tokens |= {r["owner_token"] for r in masked}
    assert len(tokens) == 2, "one token per deltabrain, unrelated across deltabrains"
    assert len({len(t) for t in tokens}) == 1


def test_private_host_leaves_no_real_id_in_any_deltabrain_response(world):
    w, a_sid = world, world["sids"]["A"]
    _ok(_call(w, "user_a", "subbrain_set_visibility", subbrain_id=a_sid, visibility="private"))
    for viewer in ("user_b", "user_c"):
        responses = _deltabrain_responses(w, viewer, w["db1"])
        assert responses["get"]["untrusted_data"]["deltabrain"]["host_subbrain_id"] is None
        for name, env in responses.items():
            text = _text(env)
            assert a_sid not in text and "user_a" not in text, f"{viewer} {name}"
            assert _brain("A")["owner"]["display_name"] not in text, f"{viewer} {name}"
    own = _ok(_call(w, "user_a", "deltabrain_get", deltabrain_id=w["db1"]))
    assert own["untrusted_data"]["deltabrain"]["host_subbrain_id"] == a_sid


def test_contributor_token_length_does_not_reveal_the_owner_id_length(world):
    """Two private contributors with very different id lengths get tokens of the same length."""
    w = world
    store, svc = w["store"], w["svc"]
    long_user, _ = store.create_user("긴 이름", Tier.PRO, user_id="u" * 64)
    doc = _brain("B")["document"]
    doc["title"] = "퍼즐 게임 블록 설계 원칙 (긴 ID)"
    imported = _ok(svc.dispatch(long_user, "subbrain_import", {"document": doc}))
    _ok(svc.dispatch(long_user, "subbrain_set_visibility", {"subbrain_id": imported["subbrain_id"], "visibility": "public",
                                                            "confirm_hash": imported["content_hash"]}))
    sids = dict(w["sids"], B=imported["subbrain_id"])
    canal = store.create_canal("user_a", sids["A"], 1, Q01, QueryMode.TOPIC,
                               [*_members(store, w["sids"], ["C"]),
                                CanalMember(subbrain_id=sids["B"], version=1, owner_id=long_user.id, relevance=0.5,
                                            distance=1.0, matched_terms=["조립"])])
    db = _ok(svc.dispatch(w["users"]["user_a"], "canal_submit", {"canal_id": canal.id, "deltabrain": _good01(sids)}))
    for uid, sid in ((long_user.id, sids["B"]), ("user_c", sids["C"])):
        user = long_user if uid == long_user.id else w["users"][uid]
        _ok(svc.dispatch(user, "subbrain_set_visibility", {"subbrain_id": sid, "visibility": "private"}))
    view = _ok(_call(w, "user_a", "deltabrain_get", deltabrain_id=db["deltabrain_id"]))["untrusted_data"]["deltabrain"]
    tokens = {r["owner_token"] for n in view["nodes"] for r in n["provenance"] if r["owner_id"] is None}
    assert len(tokens) == 2 and len({len(t) for t in tokens}) == 1
    assert {crypto.decrypt_contributor_token(w["key"], t)[0] for t in tokens} == {long_user.id, "user_c"}
