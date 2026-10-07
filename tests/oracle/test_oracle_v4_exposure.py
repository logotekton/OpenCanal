"""NEVER-02 (v.4 host), NEVER-01/NEVER-04 (unconfirmed versions), NEVER-11 (v.4 statistics) — ORACLE §5.5, §9.

All behavior goes through Service.dispatch with real tokens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from opencanal.models import Tier

from .conftest import (
    PRIVATE_CONTRIBUTOR,
    Q01,
    World,
    assert_err,
    assert_ok,
    assert_same_not_found,
    dumps,
    fake_id_like,
    find_dicts,
    load_brain,
    load_delta,
    member_ids,
    pick,
    rewrite_provenance,
)
from ._v4 import canonical, find_strings, first_difference


def _doc(fid: str) -> dict:
    return load_brain(fid)["document"]


def _withheld_entries(env: dict, sid: str) -> list[dict]:
    return find_dicts(env, lambda d: "withheld" in d and sid in [v for v in d.values() if isinstance(v, str)])


# ---------------------------------------------------------------------------
# NEVER-02 (v.4) — the HOST switching to private is withheld from the other participants, too
# ---------------------------------------------------------------------------

# Host A strings that only A's subbrain content can supply (labels inside the Q-01 sentence excluded).
A_ONLY = [
    _doc("A")["title"],
    *(n["label"] for n in _doc("A")["nodes"] if n["label"] not in Q01),
    *(n["summary"] for n in _doc("A")["nodes"]),
    *(e["summary"] for e in _doc("A")["edges"] if e.get("summary")),
]


def test_never_02_v4_host_switched_private_is_withheld_in_canal_get(seeded: World):
    canal = assert_ok(seeded.open_canal(query=Q01))
    canal_id, aid = canal["canal_id"], seeded.sid("A")
    participants = ["user_a", *sorted({seeded.sb[f]["owner"] for f in seeded.sb if seeded.sid(f) in member_ids(canal)})]
    assert {"user_b", "user_c", "user_e"} <= set(participants)

    before = assert_ok(seeded.call("user_b", "canal_get", canal_id=canal_id))
    assert find_strings(before["untrusted_data"], "공차 관리"), "self-check: host content is served while public"

    assert_ok(seeded.make_private("A"))

    for viewer in ("user_b", "user_c", "user_e"):
        env = assert_ok(seeded.call(viewer, "canal_get", canal_id=canal_id))
        for s in A_ONLY:
            assert not find_strings(env, s), f"host content still served to {viewer} after the host went private: {s!r}"
        # Oracle v.5 NEVER-11 + §9: the withheld host is an opaque per-canal `withheld_ref`, never the real
        # subbrain_id (was: located by the real subbrain_id).
        marks = find_dicts(env, lambda d: d.get("withheld") is True)
        assert marks, f"host must be marked withheld:true for {viewer}"
        refs = {d.get("withheld_ref") for d in marks}
        assert len(refs) == 1 and all(isinstance(r, str) and r for r in refs), f"one withheld_ref for {viewer}: {marks}"
        assert not find_strings(env, aid), f"real host subbrain_id shown to {viewer} (NEVER-11 v.5)"
        assert find_strings(env["untrusted_data"], "형태 상보성"), "still-public members stay visible"

    own = assert_ok(seeded.call("user_a", "canal_get", canal_id=canal_id))
    for s in ("접합부 상세", "공차 관리", _doc("A")["nodes"][0]["summary"]):
        assert find_strings(own, s), f"the owner still sees the host content: {s!r}"
    assert all(d["withheld"] is False for d in _withheld_entries(own, aid)), "not withheld for its owner"


def test_never_02_v4_host_switched_private_leaves_search_new_canals_and_direct_get(seeded: World):
    aid = seeded.sid("A")
    # Before: A is a candidate for another host's canal.
    e_canal = assert_ok(seeded.call("user_e", "canal_open", query=Q01, host_subbrain_id=seeded.sid("A2")))
    assert aid in member_ids(e_canal), "self-check: A is relevant to Q-01"

    assert_ok(seeded.make_private("A"))

    for viewer in ("user_b", "user_e"):
        search = assert_ok(seeded.call(viewer, "subbrain_search", query=Q01, limit=20))
        assert aid not in {r["subbrain_id"] for r in search["untrusted_data"]["results"]}
    e_canal2 = assert_ok(seeded.call("user_e", "canal_open", query=Q01, host_subbrain_id=seeded.sid("A2")))
    assert aid not in member_ids(e_canal2)
    fake = fake_id_like(aid)
    assert_same_not_found(
        seeded.call("user_b", "subbrain_get", subbrain_id=aid), aid, seeded.call("user_b", "subbrain_get", subbrain_id=fake), fake
    )
    assert_err(seeded.open_canal(query=Q01), "HOST_NOT_PUBLIC")  # MUST-C1
    mine = pick(assert_ok(seeded.call("user_a", "subbrain_list_mine")), "subbrains")
    assert next(s for s in mine if s["subbrain_id"] == aid)["visibility"] == "private"


def test_never_02_v4_host_switched_private_keeps_existing_deltabrain(seeded: World):
    _, db_id, _ = seeded.canal_with_deltabrain()
    aid = seeded.sid("A")
    assert_ok(seeded.make_private("A"))
    for viewer in ("user_a", "user_b", "user_c", "user_e"):
        env = assert_ok(seeded.call(viewer, "deltabrain_get", deltabrain_id=db_id))
        graph = env["untrusted_data"]["deltabrain"]
        for label in ("현장 조립 오류", "접합부 상세", "공차 관리", "비대칭 접합 키 설계"):
            assert find_strings(graph, label), f"derived host node {label!r} vanished for {viewer}"
        listed = pick(assert_ok(seeded.call(viewer, "deltabrain_list")), "deltabrains")
        assert db_id in dumps(listed)
    # NEVER-11 applies to the host as a contributor: non-owners see the masked contributor, not user_a.
    for viewer in ("user_b", "user_c"):
        env = assert_ok(seeded.call(viewer, "deltabrain_get", deltabrain_id=db_id))
        assert PRIVATE_CONTRIBUTOR in dumps(env), f"host refs must be masked for {viewer}"
        for d in find_dicts(env, lambda d: d.get("subbrain_id") == aid):
            assert d.get("owner_id") in (None, ""), f"host owner id visible next to its ref: {d}"
            assert d.get("owner_display") != "Haram Kim", d


# ---------------------------------------------------------------------------
# NEVER-04 / NEVER-01 — an imported but unconfirmed version is never visible to others
# ---------------------------------------------------------------------------

V2_LABEL = "조립 순서 잠금 신규 규칙"


def _import_b_v2(world: World) -> dict[str, Any]:
    doc = load_brain("B")["document"]
    doc["nodes"].append({"id": "b-n11", "label": V2_LABEL, "tags": ["조립", "순서"], "summary": "앞 블록이 놓이기 전에는 다음 블록이 잠긴다."})
    env = assert_ok(world.import_doc("user_b", doc, subbrain_id=world.sid("B")))
    assert env["subbrain_id"] == world.sid("B") and env["version"] == 2
    return env


def _published_version(world: World, owner: str, sid: str) -> Any:
    mine = pick(assert_ok(world.call(owner, "subbrain_list_mine")), "subbrains")
    return next(s for s in mine if s["subbrain_id"] == sid)["published_version"]


def test_never_04_v4_unconfirmed_v2_is_invisible_to_others(seeded: World):
    bid = seeded.sid("B")
    _import_b_v2(seeded)
    assert _published_version(seeded, "user_b", bid) == 1

    default = assert_ok(seeded.call("user_a", "subbrain_get", subbrain_id=bid))
    assert V2_LABEL not in dumps(default)
    assert find_dicts(default, lambda d: d.get("version") == 1), "others get the published v1"
    assert not find_dicts(default, lambda d: d.get("version") == 2)

    # version=2 (exists, unconfirmed), version=99 (does not exist) and a fake id must be indistinguishable.
    v2 = seeded.call("user_a", "subbrain_get", subbrain_id=bid, version=2)
    v99 = seeded.call("user_a", "subbrain_get", subbrain_id=bid, version=99)
    assert V2_LABEL not in dumps(v2)
    assert dumps(v2) == dumps(v99), f"unconfirmed v2 is distinguishable from a missing version:\n{dumps(v2)}\n{dumps(v99)}"
    if v2["ok"] is False:
        fake = fake_id_like(bid)
        assert_same_not_found(v2, bid, seeded.call("user_a", "subbrain_get", subbrain_id=fake, version=2), fake)
    else:  # the reading "version=2 falls back to the published v1" is also leak-free
        assert find_dicts(v2, lambda d: d.get("version") == 1)

    for env in (
        assert_ok(seeded.call("user_a", "subbrain_search", query="조립 순서 잠금", limit=20)),
        assert_ok(seeded.call("user_a", "subbrain_search", query=Q01, limit=20)),
        assert_ok(seeded.open_canal(query=Q01)),
    ):
        assert V2_LABEL not in dumps(env)
        for d in find_dicts(env, lambda d: d.get("subbrain_id") == bid and "version" in d):
            assert d["version"] == 1, d
    canal = assert_ok(seeded.open_canal(query=Q01))
    got = assert_ok(seeded.call("user_c", "canal_get", canal_id=canal["canal_id"]))
    assert V2_LABEL not in dumps(got)

    # Positive control: the owner sees v2.
    assert V2_LABEL in dumps(assert_ok(seeded.call("user_b", "subbrain_get", subbrain_id=bid, version=2)))


@pytest.mark.parametrize("explicit_version", [True, False], ids=["version=2", "default_latest"])
def test_never_04_v4_publishing_v2_with_v1_hash_is_confirmation_mismatch(seeded: World, explicit_version: bool):
    bid = seeded.sid("B")
    v1_hash = seeded.sb["B"]["content_hash"]
    v2 = _import_b_v2(seeded)
    assert v2["content_hash"] != v1_hash, "self-check: v2 has its own preview hash"
    args: dict[str, Any] = {"subbrain_id": bid, "visibility": "public", "confirm_hash": v1_hash}
    if explicit_version:
        args["version"] = 2
    assert_err(seeded.call("user_b", "subbrain_set_visibility", **args), "CONFIRMATION_MISMATCH")
    assert _published_version(seeded, "user_b", bid) == 1, "a mismatch must not change the published version"
    assert V2_LABEL not in dumps(seeded.call("user_a", "subbrain_get", subbrain_id=bid))
    # Positive control: the v2 hash publishes v2.
    assert_ok(seeded.call("user_b", "subbrain_set_visibility", subbrain_id=bid, visibility="public", version=2, confirm_hash=v2["content_hash"]))
    assert _published_version(seeded, "user_b", bid) == 2
    assert V2_LABEL in dumps(assert_ok(seeded.call("user_a", "subbrain_get", subbrain_id=bid)))


# ---------------------------------------------------------------------------
# NEVER-11 (v.4) — statistics, ratings and errors do not tell who the private contributor is
#
# Two worlds that differ only in WHO owns subbrain C:
#   distinct: C is owned by user_c (a contributor nobody else in the deltabrain is)
#   same:     C is owned by user_b, who also owns the still-public B (one of the visible contributors)
# After C goes private, a participant who is not C's owner must get byte-identical responses in both worlds
# (modulo server-assigned ids, timestamps and the masked token itself).
# ---------------------------------------------------------------------------

EDGES = [f"e{i}" for i in range(1, 11)]
# Oracle v.8: rating targets are bridge nodes or emergent edges (`target_id`), so every node id is tried as well.
TARGETS = [*EDGES, "q", "s-a1", "s-a2", "s-a3", "s-b1", "s-c1", "s-c2", "n1", "n2"]
# ORACLE v.8 §4: e1/e2 query edges, e5-e8 self-anchor edges are not emergent (was v.7: e3-e10).
GOOD_EMERGENT = {"e3", "e4", "e9", "e10"}
VIEWERS = ("user_a", "user_e")


def _never11_world(base: Path, variant: str) -> dict[str, Any]:
    w = World(base / variant)
    w.ensure_fixture_users()
    w.set_tier("user_b", Tier.PRO)  # user_b may keep two public subbrains in the "same" world
    for fid in ("A", "A2", "B", "D", "X"):
        w.import_fixture(fid)
        assert_ok(w.publish(fid))
    c_key = "C" if variant == "distinct" else "C@user_b"
    w.import_fixture("C", as_user=None if variant == "distinct" else "user_b")
    assert_ok(w.publish(c_key))
    c_sid = w.sid(c_key)

    canal = assert_ok(w.open_canal(query=Q01))
    assert set(member_ids(canal)) == {w.sid("A2"), w.sid("B"), c_sid}, f"{variant}: canal members differ"
    mapping = {"sb_A": (w.sid("A"), 1), "sb_B": (w.sid("B"), 1), "sb_C": (c_sid, 1)}
    sub = assert_ok(w.submit(canal["canal_id"], rewrite_provenance(load_delta("good-01"), mapping)))
    db_id = sub["deltabrain_id"]
    # Self-check: the TRUE statistics differ between the worlds (e9 joins sb_C and sb_B, one owner in "same"),
    # so identical viewer responses below can only come from statistics computed on visible identities.
    true_emergent = GOOD_EMERGENT if variant == "distinct" else GOOD_EMERGENT - {"e9"}
    assert set(sub["stats"]["emergent_edge_ids"]) == true_emergent, f"{variant}: {sub['stats']}"
    assert sub["stats"]["owners_involved"] == (3 if variant == "distinct" else 2), f"{variant}: {sub['stats']}"
    assert_ok(w.make_private(c_key))

    replacements = {
        w.sid("A"): "<SB_A>",
        w.sid("A2"): "<SB_A2>",
        w.sid("B"): "<SB_B>",
        c_sid: "<SB_C>",
        w.sid("D"): "<SB_D>",
        w.sid("X"): "<SB_X>",
        canal["canal_id"]: "<CANAL>",
        db_id: "<DB>",
    }
    out: dict[str, Any] = {"world": w, "db_id": db_id, "reps": replacements, "raw": {}}
    for viewer in VIEWERS:
        got = assert_ok(w.call(viewer, "deltabrain_get", deltabrain_id=db_id))
        assert PRIVATE_CONTRIBUTOR in dumps(got), f"{variant}: C must be masked for {viewer}"
        out["raw"][(viewer, "get")] = got
        out["raw"][(viewer, "list")] = w.call(viewer, "deltabrain_list")
    for viewer in VIEWERS:
        for eid in TARGETS:
            out["raw"][(viewer, f"rate:{eid}")] = w.call(
                viewer, "deltabrain_rate", deltabrain_id=db_id, target_id=eid, novelty=1, validity=1, usefulness=0
            )
    for viewer in VIEWERS:
        out["raw"][(viewer, "get_after_rating")] = w.call(viewer, "deltabrain_get", deltabrain_id=db_id)
        out["raw"][(viewer, "list_after_rating")] = w.call(viewer, "deltabrain_list")
        w.set_tier(viewer, Tier.PRO)  # same change in both worlds, after the canal exists
        out["raw"][(viewer, "export")] = w.call(viewer, "deltabrain_export", deltabrain_id=db_id)
        out["raw"][(viewer, "rate_unknown_edge")] = w.call(
            viewer, "deltabrain_rate", deltabrain_id=db_id, target_id="e404", novelty=1, validity=1, usefulness=1
        )
    return out


@pytest.fixture
def never11_worlds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENCANAL_MASTER_KEY", raising=False)
    worlds = {v: _never11_world(tmp_path, v) for v in ("distinct", "same")}
    yield worlds
    for out in worlds.values():
        try:
            out["world"].store.close()
        except Exception:
            pass


def _canon(out: dict[str, Any], key: tuple[str, str]) -> Any:
    return canonical(out["raw"][key], out["reps"])


@pytest.mark.parametrize("viewer", VIEWERS)
def test_never_11_v8_viewer_stats_carry_v8_fields_and_ratings_succeed(never11_worlds, viewer):
    """Keeps the identity comparison below from being vacuous under v.8: the compared deltabrain_get carries the v.8
    stats fields, and the rating calls being compared actually rate (the units in the viewer's view are the same in
    both worlds: the masked contributor counts as its own visible identity, so e9 joins two owners in both)."""
    for variant, out in never11_worlds.items():
        text = dumps(out["raw"][(viewer, "get")])
        for key in ("bridge_node_ids", "host_bridge_node_ids", "bridges_with_constraints", "emergent_edge_ids"):
            assert key in text, f"{variant}/{viewer}: v.8 stats field {key} missing from deltabrain_get"
        for target in ("n1", "n2", *sorted(GOOD_EMERGENT)):
            assert_ok(out["raw"][(viewer, f"rate:{target}")])
        for target in ("e1", "e5", "s-a1"):
            assert_err(out["raw"][(viewer, f"rate:{target}")], "NOT_RATEABLE")


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("call", ["get", "list", "get_after_rating", "list_after_rating", "export", "rate_unknown_edge"])
def test_never_11_v4_views_identical_whether_private_contributor_is_visible_owner(never11_worlds, viewer, call):
    a = _canon(never11_worlds["distinct"], (viewer, call))
    b = _canon(never11_worlds["same"], (viewer, call))
    assert a == b, (
        f"{viewer} {call}: response depends on who the private contributor is — {first_difference(a, b)}"
    )


@pytest.mark.parametrize("viewer", VIEWERS)
def test_never_11_v4_rating_responses_identical_whether_private_contributor_is_visible_owner(never11_worlds, viewer):
    for eid in TARGETS:
        a = _canon(never11_worlds["distinct"], (viewer, f"rate:{eid}"))
        b = _canon(never11_worlds["same"], (viewer, f"rate:{eid}"))
        assert a == b, f"{viewer} rating {eid}: {first_difference(a, b)}\n distinct: {dumps(a)}\n same    : {dumps(b)}"


def test_never_11_v4_masked_contributor_owner_never_shown(never11_worlds):
    """Neither world shows C's real owner next to C's refs, to any non-owner viewer."""
    for variant, out in never11_worlds.items():
        c_sid = next(k for k, v in out["reps"].items() if v == "<SB_C>")
        for viewer in VIEWERS:
            env = out["raw"][(viewer, "get")]
            refs = find_dicts(env, lambda d: d.get("subbrain_id") == c_sid)
            for d in refs:
                assert d.get("owner_id") in (None, ""), f"{variant}/{viewer}: {d}"
                assert d.get("owner_display") in (None, PRIVATE_CONTRIBUTOR), f"{variant}/{viewer}: {d}"
            assert "Chaeyoung Yoon" not in dumps(env)
