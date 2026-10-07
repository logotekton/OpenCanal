"""NEVER-11 (Oracle v.5, owner decision "엮을 수도 없게") — private contributors cannot be linked across canals.

ORACLE §5.5 NEVER-11 (v.5): no value lets a participant tie a private contributor seen in one canal (and its
deltabrain) to the same contributor in another canal. Concretely: the real subbrain_id · version · node_id are not
shown; when the HOST is private the deltabrain's top-level host subbrain_id is not shown either; `canal_get` shows a
withheld entry through an opaque handle `withheld_ref` valid only inside that canal (§9 v.5: "커널 안에서만 같은 값");
the token length does not depend on the owner id length. Tokens: same value inside one deltabrain, different across
deltabrains, decryptable only with the server key. The owner keeps seeing the real ids.

Worlds: host A opens two canals on different queries (Q-01 topic, Q-02 whole_host); both contain members A2, B and C.
good-01 is submitted to both. C is published at version 2 (everyone else is version 1), so a leaked version is
recognisable. Every response a non-owner participant can get (canal_get, deltabrain_get, deltabrain_list,
deltabrain_export, deltabrain_rate) is collected for both canals and searched for anything that ties the two.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Iterator

import pytest

from opencanal.models import Tier

from .conftest import (
    PRIVATE_CONTRIBUTOR,
    Q01,
    Q02,
    World,
    assert_ok,
    dumps,
    find_dicts,
    load_brain,
    load_delta,
    member_ids,
    rewrite_provenance,
)
from ._v4 import all_text, iter_strings

TOKEN_KEYS = ("owner_token", "withheld_ref")
C_VERSION = 2
C_V2_EXTRA_NODE = {"id": "c-n11", "label": "막 수송 단백질", "tags": ["수송", "막"], "summary": "세포막을 가로질러 물질을 옮긴다."}
NODE_IDS = {
    "A": ("a-n2", "a-n3", "a-n4"),  # the host nodes good-01 cites
    "B": ("b-n2",),
    "C": ("c-n2", "c-n3"),
}
DISPLAY = {fid: load_brain(fid)["owner"]["display_name"] for fid in ("A", "B", "C")}
OWNER = {fid: load_brain(fid)["owner"]["user_id"] for fid in ("A", "B", "C")}


@pytest.fixture(autouse=True)
def _no_env_master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCANAL_MASTER_KEY", raising=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strings_except_tokens(obj: Any) -> Iterator[str]:
    """Every key and string value, except the values of the opaque token keys (random text may contain anything)."""
    for path, s in iter_strings(obj):
        if path and path[-1] in TOKEN_KEYS and s != path[-1]:
            continue
        yield s


def _values(obj: Any) -> set[str]:
    """String VALUES (not keys) anywhere inside obj."""
    out: set[str] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            out |= _values(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= _values(v)
    elif isinstance(obj, str):
        out.add(obj)
    return out


def _masked_refs(env: dict) -> list[dict]:
    return find_dicts(env, lambda d: isinstance(d.get("owner_token"), str) and bool(d.get("owner_token")))


def _withheld(env: dict) -> list[dict]:
    return find_dicts(env, lambda d: d.get("withheld") is True)


def _version_values(obj: Any) -> list[tuple[str, Any]]:
    """(key, value) of every key that names a version."""
    out: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and "version" in k.lower() and isinstance(v, int) and not isinstance(v, bool):
                out.append((k, v))
            out.extend(_version_values(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_version_values(v))
    return out


def _assert_no_identity(env: dict, fid: str, sid: str, where: str, *, version: int | None = None) -> None:
    """None of the private contributor's real identifiers appear anywhere in a non-owner's response."""
    text = dumps(env)
    assert sid not in text, f"{where}: real subbrain_id of private {fid} shown"
    assert OWNER[fid] not in text, f"{where}: owner id of private {fid} shown"
    assert DISPLAY[fid] not in text, f"{where}: owner name of private {fid} shown"
    strings = list(_strings_except_tokens(env))
    for nid in NODE_IDS[fid]:
        hits = [s for s in strings if nid in s]
        assert not hits, f"{where}: real node_id {nid!r} of private {fid} shown: {hits[:3]}"
    if version is not None:
        bad = [kv for kv in _version_values(env) if kv[1] == version]
        assert not bad, f"{where}: real version {version} of private {fid} shown: {bad}"


def _submission(world: World, query: str, c_version: int) -> dict:
    delta = rewrite_provenance(
        load_delta("good-01"),
        {"sb_A": (world.sid("A"), 1), "sb_B": (world.sid("B"), 1), "sb_C": (world.sid("C"), c_version)},
    )
    delta["nodes"][0]["label"] = query  # the query node carries the canal's own query
    assert delta["nodes"][0]["kind"] == "query"
    return delta


def _retained_strings(*deltas: dict) -> set[str]:
    """Host-authored deltabrain text without provenance: retained for participants (NEVER-02), not an identity."""
    out: set[str] = set()
    for d in deltas:
        bare = copy.deepcopy(d)
        for item in [*bare["nodes"], *bare["edges"]]:
            item.pop("provenance", None)
        out |= set(all_text(bare))
    return out


def _build(tmp_path: Path, private: tuple[str, ...]) -> dict[str, Any]:
    """Seeded world, C at version 2, two canals hosted by A (Q-01, Q-02) with good-01 each; then `private` go private."""
    w = World(tmp_path)
    w.ensure_fixture_users()
    for fid in ("A", "A2", "B", "D", "P", "X"):
        w.import_fixture(fid)
        if load_brain(fid)["visibility"] == "public":
            assert_ok(w.publish(fid))
    w.import_fixture("C")
    c_doc = load_brain("C")["document"]
    c_doc["nodes"].append(dict(C_V2_EXTRA_NODE))
    v2 = assert_ok(w.import_doc("user_c", c_doc, subbrain_id=w.sid("C")))
    assert v2["version"] == C_VERSION
    w.sb["C"]["content_hash"] = v2["content_hash"]
    assert_ok(w.publish("C", version=C_VERSION))

    canals, dbs, deltas = [], [], []
    for query in (Q01, Q02):
        canal = assert_ok(w.open_canal(query=query))
        assert set(member_ids(canal)) == {w.sid("A2"), w.sid("B"), w.sid("C")}, f"{query}: {member_ids(canal)}"
        c_member = next(m for m in canal["members"] if m["subbrain_id"] == w.sid("C"))
        assert c_member["version"] == C_VERSION
        delta = _submission(w, query, C_VERSION)
        sub = assert_ok(w.submit(canal["canal_id"], delta))
        canals.append(canal["canal_id"])
        dbs.append(sub["deltabrain_id"])
        deltas.append(delta)
    for fid in private:
        assert_ok(w.make_private(fid))
    return {"world": w, "canals": canals, "dbs": dbs, "deltas": deltas, "private": private}


def _collect(info: dict[str, Any], viewer: str) -> dict[str, Any]:
    """Every response `viewer` can get about each canal: {"worlds": [dict, dict], "shared": {...}}."""
    w: World = info["world"]
    w.set_tier(viewer, Tier.PRO)  # deltabrain_export (after the canals exist)
    worlds = []
    for canal_id, db_id in zip(info["canals"], info["dbs"]):
        worlds.append(
            {
                "canal_get": w.call(viewer, "canal_get", canal_id=canal_id),
                "canal_get_again": w.call(viewer, "canal_get", canal_id=canal_id),
                "deltabrain_get": w.call(viewer, "deltabrain_get", deltabrain_id=db_id),
                "deltabrain_export": w.call(viewer, "deltabrain_export", deltabrain_id=db_id),
                # Oracle v.8 / TASK §5: `target_id` (bridge node or emergent edge); was `edge_id`.
                "rate_e3": w.call(viewer, "deltabrain_rate", deltabrain_id=db_id, target_id="e3", novelty=1, validity=1, usefulness=1),
                "rate_e9": w.call(viewer, "deltabrain_rate", deltabrain_id=db_id, target_id="e9", novelty=1, validity=0, usefulness=1),
                "rate_n2": w.call(viewer, "deltabrain_rate", deltabrain_id=db_id, target_id="n2", novelty=0, validity=1, usefulness=1),
                "rate_e5": w.call(viewer, "deltabrain_rate", deltabrain_id=db_id, target_id="e5", novelty=1, validity=1, usefulness=1),
                "rate_e404": w.call(viewer, "deltabrain_rate", deltabrain_id=db_id, target_id="e404", novelty=1, validity=1, usefulness=1),
                "deltabrain_get_after_rating": w.call(viewer, "deltabrain_get", deltabrain_id=db_id),
            }
        )
    for resp in worlds:
        for name in ("canal_get", "deltabrain_get", "deltabrain_export", "rate_e3", "rate_e9", "rate_n2"):
            assert_ok(resp[name])
    shared = {"deltabrain_list": assert_ok(w.call(viewer, "deltabrain_list"))}
    return {"worlds": worlds, "shared": shared}


def _close(info: dict[str, Any]) -> None:
    try:
        info["world"].store.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Members B and C private: two private contributors in each canal
# ---------------------------------------------------------------------------

MEMBER_VIEWERS = ("user_a", "user_e")  # host and the A2 owner: participants of both canals, owners of neither


@pytest.fixture
def members_private(tmp_path: Path) -> Iterator[dict[str, Any]]:
    info = _build(tmp_path, ("B", "C"))
    info["views"] = {v: _collect(info, v) for v in MEMBER_VIEWERS}
    yield info
    _close(info)


@pytest.mark.parametrize("viewer", MEMBER_VIEWERS)
def test_never_11_v5_no_real_ids_of_private_members_anywhere(members_private, viewer):
    w: World = members_private["world"]
    view = members_private["views"][viewer]
    for i, resp in enumerate(view["worlds"]):
        for name, env in resp.items():
            _assert_no_identity(env, "C", w.sid("C"), f"{viewer} canal#{i + 1} {name}", version=C_VERSION)
            _assert_no_identity(env, "B", w.sid("B"), f"{viewer} canal#{i + 1} {name}")
    for name, env in view["shared"].items():
        _assert_no_identity(env, "C", w.sid("C"), f"{viewer} {name}", version=C_VERSION)
        _assert_no_identity(env, "B", w.sid("B"), f"{viewer} {name}")
    # The checks are not vacuous: the retained content and the masked contributor are served.
    for resp in view["worlds"]:
        graph = dumps(resp["deltabrain_get"]["untrusted_data"]["deltabrain"])
        assert "형태 상보성" in graph and "잘못 놓을 수 없는 블록 모양" in graph, "retained content (NEVER-02)"
        assert PRIVATE_CONTRIBUTOR in dumps(resp["deltabrain_get"])


@pytest.mark.parametrize("viewer", MEMBER_VIEWERS)
def test_never_11_v5_withheld_ref_is_per_canal_and_stable_inside_a_canal(members_private, viewer):
    view = members_private["views"][viewer]
    refs = []
    for i, resp in enumerate(view["worlds"]):
        marks = _withheld(resp["canal_get"])
        assert marks, f"canal#{i + 1}: private members must be marked withheld:true"
        got = {d.get("withheld_ref") for d in marks}
        assert all(isinstance(r, str) and r for r in got), f"canal#{i + 1}: withheld entry without withheld_ref: {marks}"
        assert len(got) == 2, f"canal#{i + 1}: two private members -> two handles, got {got}"
        again = {d.get("withheld_ref") for d in _withheld(resp["canal_get_again"])}
        assert again == got, "the handle is stable inside one canal"
        refs.append(got)
    assert not refs[0] & refs[1], "the same private member must get a different handle in another canal"
    for i, j in ((0, 1), (1, 0)):
        other = dumps(view["worlds"][j]) + dumps(view["shared"])
        for r in refs[i]:
            assert r not in other, f"withheld_ref of canal#{i + 1} reappears outside it"


def test_never_11_v5_withheld_ref_is_the_same_for_every_participant_of_a_canal(members_private):
    for i in range(2):
        per_viewer = [
            {d.get("withheld_ref") for d in _withheld(members_private["views"][v]["worlds"][i]["canal_get"])} for v in MEMBER_VIEWERS
        ]
        assert per_viewer[0] and None not in per_viewer[0], f"canal#{i + 1}: withheld entries carry withheld_ref"
        assert per_viewer[0] == per_viewer[1], f"canal#{i + 1}: §9 v.5 withheld_ref is one value inside the canal"


@pytest.mark.parametrize("viewer", MEMBER_VIEWERS)
def test_never_11_v5_tokens_are_per_deltabrain_and_decrypt_to_the_contributor(members_private, viewer):
    from opencanal import crypto

    w: World = members_private["world"]
    view = members_private["views"][viewer]
    tokens = []
    for i, (resp, db_id) in enumerate(zip(view["worlds"], members_private["dbs"])):
        by_owner: dict[str, set[str]] = {}
        for name in ("deltabrain_get", "deltabrain_export", "deltabrain_get_after_rating"):
            for d in _masked_refs(resp[name]):
                owner, db = crypto.decrypt_contributor_token(w.master_key, d["owner_token"])
                assert db == db_id
                by_owner.setdefault(owner, set()).add(d["owner_token"])
        assert set(by_owner) == {"user_b", "user_c"}, f"canal#{i + 1}: masked owners {set(by_owner)}"
        for owner, toks in by_owner.items():
            assert len(toks) == 1, f"{owner}: one token inside one deltabrain, got {toks}"
        tokens.append({next(iter(t)) for t in by_owner.values()})
    assert not tokens[0] & tokens[1], "tokens differ across deltabrains"
    for i, j in ((0, 1), (1, 0)):
        other = dumps(view["worlds"][j]) + dumps(view["shared"])
        for t in tokens[i]:
            assert t not in other, f"token of deltabrain#{i + 1} reappears outside it"


@pytest.mark.parametrize("viewer", MEMBER_VIEWERS)
def test_never_11_v5_no_contributor_specific_value_is_shared_between_the_canals(members_private, viewer):
    """Generic cross-canal check, independent of key names.

    In each canal two private contributors (B, C) are masked. Masked dicts are grouped per contributor — withheld
    entries of canal_get by their withheld_ref, masked provenance refs by their owner_token. A value found in the
    masked dicts of both contributors is a constant ("비공개 기여자", a placeholder, a notice) and identifies
    nobody. A value found for only one contributor — minus the host's own retained deltabrain text and the
    queries — is contributor-specific and must not occur anywhere in the other canal's responses.
    """
    view = members_private["views"][viewer]
    allowed = _retained_strings(*members_private["deltas"]) | {Q01, Q02, PRIVATE_CONTRIBUTOR}
    specific: list[set[str]] = []
    everything: list[set[str]] = []
    for i, resp in enumerate(view["worlds"]):
        groups = {
            "withheld_ref": [d for name in ("canal_get", "canal_get_again") for d in _withheld(resp[name])],
            "owner_token": [
                d for name in ("deltabrain_get", "deltabrain_export", "deltabrain_get_after_rating") for d in _masked_refs(resp[name])
            ],
        }
        spec: set[str] = set()
        for key, dicts in groups.items():
            per_contributor: dict[Any, set[str]] = {}
            for d in dicts:
                per_contributor.setdefault(d.get(key), set()).update(_values(d))
            assert len(per_contributor) == 2, f"canal#{i + 1}: expected 2 masked contributors by {key}, got {list(per_contributor)}"
            a, b = per_contributor.values()
            spec |= (a ^ b) - allowed
        specific.append(spec)
        everything.append(_values(resp))
    for i, j in ((0, 1), (1, 0)):
        shared = specific[i] & everything[j]
        assert not shared, f"{viewer}: contributor-specific values of canal#{i + 1} reappear in canal#{j + 1}: {sorted(shared)[:5]}"


def test_never_11_v5_owners_still_see_their_real_ids(members_private):
    w: World = members_private["world"]
    canal_1, db_1 = members_private["canals"][0], members_private["dbs"][0]
    for owner, fid, version in (("user_c", "C", C_VERSION), ("user_b", "B", 1)):
        sid = w.sid(fid)
        env = assert_ok(w.call(owner, "deltabrain_get", deltabrain_id=db_1))
        refs = find_dicts(env, lambda d: d.get("subbrain_id") == sid and "node_id" in d)
        assert refs, f"{owner} must see the real subbrain_id of their own {fid}"
        assert {d.get("node_id") for d in refs} == set(NODE_IDS[fid])
        assert {d.get("version") for d in refs} == {version}
        canal = assert_ok(w.call(owner, "canal_get", canal_id=canal_1))
        assert sid in dumps(canal), f"{owner} must see the real id of their own {fid} in canal_get"
    env_c = assert_ok(w.call("user_c", "deltabrain_get", deltabrain_id=db_1))
    for d in find_dicts(env_c, lambda d: d.get("subbrain_id") == w.sid("C")):
        assert d.get("owner_display") != PRIVATE_CONTRIBUTOR, d


# ---------------------------------------------------------------------------
# The HOST private: the top-level host subbrain_id disappears too
# ---------------------------------------------------------------------------

HOST_VIEWERS = ("user_b", "user_c", "user_e")


@pytest.fixture
def host_private(tmp_path: Path) -> Iterator[dict[str, Any]]:
    info = _build(tmp_path, ("A",))
    info["views"] = {v: _collect(info, v) for v in HOST_VIEWERS}
    yield info
    _close(info)


@pytest.mark.parametrize("viewer", HOST_VIEWERS)
def test_never_11_v5_private_host_id_absent_from_every_response(host_private, viewer):
    w: World = host_private["world"]
    aid = w.sid("A")
    view = host_private["views"][viewer]
    for i, resp in enumerate(view["worlds"]):
        for name, env in resp.items():
            _assert_no_identity(env, "A", aid, f"{viewer} canal#{i + 1} {name}")
        db_env = resp["deltabrain_get"]
        assert PRIVATE_CONTRIBUTOR in dumps(db_env), "host refs are masked (NEVER-11 applies to the host)"
        assert not find_dicts(db_env, lambda d: d.get("host_subbrain_id") == aid)
        graph = dumps(db_env["untrusted_data"]["deltabrain"])
        for label in ("현장 조립 오류", "접합부 상세", "공차 관리"):
            assert label in graph, f"retained host-derived node {label!r} (NEVER-02)"
    for name, env in view["shared"].items():
        _assert_no_identity(env, "A", aid, f"{viewer} {name}")


@pytest.mark.parametrize("viewer", HOST_VIEWERS)
def test_never_11_v5_private_host_handles_differ_between_canals(host_private, viewer):
    from opencanal import crypto

    w: World = host_private["world"]
    view = host_private["views"][viewer]
    refs, tokens = [], []
    for i, (resp, db_id) in enumerate(zip(view["worlds"], host_private["dbs"])):
        marks = _withheld(resp["canal_get"])
        got = {d.get("withheld_ref") for d in marks}
        assert marks and len(got) == 1 and all(isinstance(r, str) and r for r in got), f"canal#{i + 1}: {marks}"
        refs.append(got)
        toks = {d["owner_token"] for d in _masked_refs(resp["deltabrain_get"])}
        assert len(toks) == 1, f"canal#{i + 1}: one token for the host inside one deltabrain, got {toks}"
        tok = next(iter(toks))
        assert crypto.decrypt_contributor_token(w.master_key, tok) == ("user_a", db_id)
        tokens.append(tok)
    assert not refs[0] & refs[1]
    assert tokens[0] != tokens[1]
    for i, j in ((0, 1), (1, 0)):
        other = dumps(view["worlds"][j]) + dumps(view["shared"])
        assert tokens[i] not in other
        for r in refs[i]:
            assert r not in other


def test_never_11_v5_private_host_owner_still_sees_real_ids(host_private):
    w: World = host_private["world"]
    aid = w.sid("A")
    for canal_id, db_id in zip(host_private["canals"], host_private["dbs"]):
        env = assert_ok(w.call("user_a", "deltabrain_get", deltabrain_id=db_id))
        refs = find_dicts(env, lambda d: d.get("subbrain_id") == aid and "node_id" in d)
        assert {d.get("node_id") for d in refs} == set(NODE_IDS["A"])
        assert PRIVATE_CONTRIBUTOR not in dumps(env)
        assert aid in dumps(assert_ok(w.call("user_a", "canal_get", canal_id=canal_id)))


# ---------------------------------------------------------------------------
# Token length does not depend on the owner id length
# ---------------------------------------------------------------------------

SHORT_ID = "q"
LONG_ID = "long_contributor_" + "x" * 47  # 64 characters, the longest id the store accepts


def test_never_11_v5_token_length_is_independent_of_owner_id_length_primitive(tmp_path: Path):
    from opencanal import crypto

    key = crypto.load_or_create_master_key(tmp_path / "master.key")
    db_id = "db_" + "0123456789abcdef" * 2
    owners = ["q", "user_c", "u" * 20, "v" * 40, LONG_ID]
    tokens = {o: crypto.contributor_token(key, o, db_id) for o in owners}
    lengths = {o: len(t) for o, t in tokens.items()}
    assert len(set(lengths.values())) == 1, f"token length leaks the owner id length: {lengths}"
    for o, t in tokens.items():
        assert crypto.decrypt_contributor_token(key, t) == (o, db_id)
        if len(o) >= 6:  # a 1-letter id occurs in random base64 by chance
            assert o not in t


def test_never_11_v5_token_length_is_independent_of_owner_id_length_in_a_deltabrain(world: World):
    """One deltabrain cites two private contributors whose user ids are 1 and 64 characters long."""
    from opencanal import crypto

    assert len(LONG_ID) == 64
    for uid in (SHORT_ID, LONG_ID):
        world.add_user(uid, "Contributor")
    world.seed(("A", "B"))
    for uid in (SHORT_ID, LONG_ID):
        world.import_fixture("C", as_user=uid)
        assert_ok(world.publish(f"C@{uid}"))
    canal = assert_ok(world.open_canal(query=Q01))
    short_sid, long_sid = world.sid(f"C@{SHORT_ID}"), world.sid(f"C@{LONG_ID}")
    assert set(member_ids(canal)) == {world.sid("B"), short_sid, long_sid}

    delta = rewrite_provenance(load_delta("good-01"), {"sb_A": (world.sid("A"), 1), "sb_B": (world.sid("B"), 1)})
    for node in delta["nodes"]:
        for ref in node.get("provenance", []):
            if ref["subbrain_id"] == "sb_C":  # s-c1 -> the short-id copy, s-c2 and n2 -> the long-id copy
                ref["subbrain_id"], ref["version"] = (short_sid if node["id"] == "s-c1" else long_sid), 1
    db_id = assert_ok(world.submit(canal["canal_id"], delta))["deltabrain_id"]
    for uid in (SHORT_ID, LONG_ID):
        assert_ok(world.make_private(f"C@{uid}"))

    for viewer in ("user_a", "user_b"):
        env = assert_ok(world.call(viewer, "deltabrain_get", deltabrain_id=db_id))
        by_owner: dict[str, set[str]] = {}
        for d in _masked_refs(env):
            owner, db = crypto.decrypt_contributor_token(world.master_key, d["owner_token"])
            assert db == db_id
            by_owner.setdefault(owner, set()).add(d["owner_token"])
        assert set(by_owner) == {SHORT_ID, LONG_ID}, f"{viewer}: {set(by_owner)}"
        short_tok, long_tok = next(iter(by_owner[SHORT_ID])), next(iter(by_owner[LONG_ID]))
        assert len(short_tok) == len(long_tok), (
            f"{viewer}: token length {len(short_tok)} vs {len(long_tok)} reveals owner id length 1 vs 64"
        )
        assert LONG_ID not in dumps(env) and short_sid not in dumps(env) and long_sid not in dumps(env)
