"""Unit tests for opencanal.store (Builder ST). Crypto is faked so these do not depend on Builder K."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import stat
import threading
from datetime import datetime, timezone

import pytest

from opencanal import crypto
from opencanal.models import (
    CanalMember,
    DeltabrainStats,
    DeltabrainSubmission,
    EdgeRating,
    ErrorCode,
    OpenCanalError,
    QueryMode,
    SubbrainDocument,
    Tier,
    Visibility,
)
from opencanal.store import MASKED_DISPLAY, Store

MASTER_KEY = b"k" * 32


@pytest.fixture(autouse=True)
def fake_crypto(monkeypatch):
    counter = iter(range(10_000))
    monkeypatch.setattr(crypto, "new_api_token", lambda: f"oc_plaintext_token_{next(counter):04d}_xyz")
    monkeypatch.setattr(crypto, "hash_api_token", lambda t: hashlib.sha256(t.encode()).hexdigest())
    monkeypatch.setattr(
        crypto,
        "contributor_token",
        lambda key, owner_id, db_id: "ct_" + hmac.new(key, f"{owner_id}|{db_id}".encode(), "sha256").hexdigest()[:24],
    )


@pytest.fixture
def store():
    s = Store(":memory:", master_key=MASTER_KEY)
    yield s
    s.close()


def doc(title: str, prefix: str, labels: list[str]) -> SubbrainDocument:
    return SubbrainDocument(
        title=title,
        domains=[title],
        nodes=[{"id": f"{prefix}{i}", "label": label, "tags": [label]} for i, label in enumerate(labels, 1)],
        edges=[{"source": f"{prefix}1", "target": f"{prefix}2", "relation": "requires"}] if len(labels) > 1 else [],
    )


def publish(store: Store, owner: str, sid: str) -> None:
    v = store.get_subbrain_for_viewer(owner, sid)
    store.set_visibility(owner, sid, Visibility.PUBLIC, confirm_hash=v.content_hash)


def assert_not_found(fn, *args, **kwargs) -> OpenCanalError:
    with pytest.raises(OpenCanalError) as info:
        fn(*args, **kwargs)
    assert info.value.code == ErrorCode.NOT_FOUND
    return info.value


def same_error(a: OpenCanalError, b: OpenCanalError) -> bool:
    return (a.code, a.message, a.detail, str(a)) == (b.code, b.message, b.detail, str(b))


@pytest.fixture
def world(store):
    """Users A (host), B, C, D (outsider); public subbrains SA, SB, SC; canal A<-B,C; one deltabrain."""
    users = {}
    for uid, name in [("user_a", "앨리스"), ("user_b", "밥빌더"), ("user_c", "캐럴셀"), ("user_d", "데이브")]:
        users[uid], _ = store.create_user(name, Tier.FREE, user_id=uid)
    sa = store.add_subbrain_version("user_a", doc("건축", "a", ["현장 조립 오류", "접합부 상세"]), "hash_a1")
    sb = store.add_subbrain_version("user_b", doc("게임", "b", ["블록 조립 규칙", "오조작 방지"]), "hash_b1")
    sc = store.add_subbrain_version("user_c", doc("세포", "c", ["형태 상보성", "오류 교정"]), "hash_c1")
    for owner, v in [("user_a", sa), ("user_b", sb), ("user_c", sc)]:
        publish(store, owner, v.subbrain_id)
    members = [
        CanalMember(subbrain_id=v.subbrain_id, version=1, owner_id=v.owner_id, relevance=0.5, distance=1.0,
                    matched_terms=["조립"])
        for v in (sb, sc)
    ]
    canal = store.create_canal("user_a", sa.subbrain_id, 1, "모듈러 조립 오류", QueryMode.TOPIC, members)
    sub = make_submission(sa.subbrain_id, sb.subbrain_id, sc.subbrain_id)
    stats = DeltabrainStats(node_count=4, edge_count=3, new_node_count=0, emergent_edge_ids=["e1", "e2"],
                            host_touching_emergent_edge_ids=["e1", "e2"], owners_involved=3)
    rec = store.save_deltabrain(canal.id, "user_a", sub, stats)
    return {"users": users, "sa": sa.subbrain_id, "sb": sb.subbrain_id, "sc": sc.subbrain_id,
            "canal": canal, "sub": sub, "stats": stats, "db": rec.id}


def make_submission(sa: str, sb: str, sc: str) -> DeltabrainSubmission:
    rationale = "형태가 맞아야만 결합되는 원리를 현장 접합부 설계에 옮기면 잘못된 조립을 물리적으로 막을 수 있다."
    return DeltabrainSubmission.model_validate({
        "nodes": [
            {"id": "q", "kind": "query", "label": "모듈러 조립 오류"},
            {"id": "na", "kind": "source", "label": "현장 조립 오류",
             "provenance": [{"subbrain_id": sa, "version": 1, "node_id": "a1"}]},
            {"id": "nb", "kind": "source", "label": "블록 조립 규칙",
             "provenance": [{"subbrain_id": sb, "version": 1, "node_id": "b1"}]},
            {"id": "nc", "kind": "source", "label": "형태 상보성",
             "provenance": [{"subbrain_id": sc, "version": 1, "node_id": "c1"}]},
        ],
        "edges": [
            {"id": "e0", "source": "q", "target": "na", "relation": "requires"},
            {"id": "e1", "source": "nc", "target": "na", "relation": "applies_to", "rationale": rationale,
             "provenance": [{"subbrain_id": sb, "version": 1, "node_id": "b2"}]},
            {"id": "e2", "source": "nb", "target": "na", "relation": "analogous_to", "rationale": rationale + " 2"},
        ],
        "synthesizer": {"kind": "client_llm", "model": "test"},
    })


# -- users / tokens -----------------------------------------------------------


def test_only_token_hash_is_stored(store):
    user, token = store.create_user("앨리스", Tier.PRO)
    assert user.id.startswith("u_") and user.tier == Tier.PRO
    rows = store._conn.execute("SELECT token_hash FROM api_tokens").fetchall()
    assert [r[0] for r in rows] == [hashlib.sha256(token.encode()).hexdigest()]
    assert token.encode() not in store.snapshot_bytes()
    assert store.user_by_token(token) == user


def test_user_by_token_fails_closed(store):
    store.create_user("앨리스", Tier.FREE, user_id="user_a")
    for bad in [None, "", "oc_unknown", 123]:
        assert store.user_by_token(bad) is None


def test_rotate_token_revokes_all_old_tokens(store):
    _, t1 = store.create_user("앨리스", Tier.FREE, user_id="user_a")
    t2 = store.rotate_token("user_a")
    t3 = store.rotate_token("user_a")
    assert store.user_by_token(t1) is None and store.user_by_token(t2) is None
    assert store.user_by_token(t3).id == "user_a"
    assert_not_found(store.rotate_token, "nobody")


def test_create_user_explicit_id_and_duplicate(store):
    user, _ = store.create_user("밥", Tier.EXPERT, user_id="user_b")
    assert user.id == "user_b" and store.get_user("user_b") == user
    with pytest.raises(OpenCanalError) as info:
        store.create_user("밥2", Tier.FREE, user_id="user_b")
    assert info.value.code == ErrorCode.INVALID_ARGUMENT
    assert store.set_tier("user_b", Tier.PRO).tier == Tier.PRO
    assert store.get_user("user_b").tier == Tier.PRO
    assert store.get_user("nobody") is None


# -- subbrains / visibility ------------------------------------------------------


def test_import_is_private_and_versions_kept(store):
    store.create_user("앨리스", Tier.FREE, user_id="user_a")
    v1 = store.add_subbrain_version("user_a", doc("건축", "a", ["x1", "x2"]), "h1")
    assert v1.subbrain_id.startswith("sb_") and v1.version == 1
    assert v1.visibility == Visibility.PRIVATE and not v1.is_published_version
    assert v1.owner_display == "앨리스"
    v2 = store.add_subbrain_version("user_a", doc("건축2", "a", ["y1"]), "h2", subbrain_id=v1.subbrain_id)
    assert v2.version == 2 and v2.visibility == Visibility.PRIVATE
    [summary] = store.list_subbrains_for_owner("user_a")
    assert (summary.latest_version, summary.published_version, summary.title) == (2, None, "건축2")
    assert store.get_subbrain_for_viewer("user_a", v1.subbrain_id).version == 2
    assert store.get_subbrain_for_viewer("user_a", v1.subbrain_id, 1).document.title == "건축"


def test_add_version_to_someone_elses_subbrain_is_not_found(store):
    store.create_user("A", Tier.FREE, user_id="user_a")
    store.create_user("B", Tier.FREE, user_id="user_b")
    v = store.add_subbrain_version("user_a", doc("t", "a", ["x"]), "h")
    e1 = assert_not_found(store.add_subbrain_version, "user_b", doc("t", "b", ["y"]), "h", subbrain_id=v.subbrain_id)
    e2 = assert_not_found(store.add_subbrain_version, "user_b", doc("t", "b", ["y"]), "h", subbrain_id="sb_missing")
    assert same_error(e1, e2)


def test_confirm_hash_required_to_publish(store):
    store.create_user("A", Tier.FREE, user_id="user_a")
    v = store.add_subbrain_version("user_a", doc("t", "a", ["x"]), "secret_hash_value")
    for bad in [None, "", "wrong"]:
        with pytest.raises(OpenCanalError) as info:
            store.set_visibility("user_a", v.subbrain_id, Visibility.PUBLIC, confirm_hash=bad)
        assert info.value.code == ErrorCode.CONFIRMATION_MISMATCH
        assert "secret_hash_value" not in info.value.message
        assert "secret_hash_value" not in json.dumps(info.value.detail)
    assert store.count_public_subbrains("user_a") == 0
    s = store.set_visibility("user_a", v.subbrain_id, Visibility.PUBLIC, confirm_hash="secret_hash_value")
    assert s.visibility == Visibility.PUBLIC and s.published_version == 1
    assert store.count_public_subbrains("user_a") == 1


def test_publish_specific_version_and_private_keeps_published_version(store):
    store.create_user("A", Tier.FREE, user_id="user_a")
    store.create_user("B", Tier.FREE, user_id="user_b")
    v1 = store.add_subbrain_version("user_a", doc("t1", "a", ["x"]), "h1")
    sid = v1.subbrain_id
    store.add_subbrain_version("user_a", doc("t2", "a", ["y"]), "h2", subbrain_id=sid)
    with pytest.raises(OpenCanalError) as info:  # default target is latest (v2) -> h1 mismatches
        store.set_visibility("user_a", sid, Visibility.PUBLIC, confirm_hash="h1")
    assert info.value.code == ErrorCode.CONFIRMATION_MISMATCH
    store.set_visibility("user_a", sid, Visibility.PUBLIC, version=1, confirm_hash="h1")
    seen = store.get_subbrain_for_viewer("user_b", sid)
    assert seen.version == 1 and seen.is_published_version and seen.visibility == Visibility.PUBLIC
    assert_not_found(store.get_subbrain_for_viewer, "user_b", sid, 2)
    s = store.set_visibility("user_a", sid, Visibility.PRIVATE)
    assert s.visibility == Visibility.PRIVATE and s.published_version == 1
    assert store.get_subbrain_for_viewer("user_a", sid, 1).is_published_version is False
    actions = [r[0] for r in store._conn.execute("SELECT action FROM audit WHERE action = 'subbrain.visibility'")]
    assert len(actions) == 2


def test_not_found_is_identical_for_missing_and_private(store):
    store.create_user("A", Tier.FREE, user_id="user_a")
    store.create_user("B", Tier.FREE, user_id="user_b")
    p = store.add_subbrain_version("user_b", doc("비공개", "p", ["조립 오류"]), "hp")
    e_private = assert_not_found(store.get_subbrain_for_viewer, "user_a", p.subbrain_id)
    e_missing = assert_not_found(store.get_subbrain_for_viewer, "user_a", "sb_0000000000000000")
    assert same_error(e_private, e_missing)
    e_vis = assert_not_found(store.set_visibility, "user_a", p.subbrain_id, Visibility.PUBLIC, confirm_hash="hp")
    e_vis_missing = assert_not_found(store.set_visibility, "user_a", "sb_x", Visibility.PUBLIC, confirm_hash="hp")
    assert same_error(e_vis, e_vis_missing) and same_error(e_vis, e_missing)
    assert store.list_public_versions() == []
    assert store.list_subbrains_for_owner("user_a") == []


def test_list_public_versions(store):
    for uid in ["user_a", "user_b", "user_c"]:
        store.create_user(uid, Tier.FREE, user_id=uid)
    ids = {}
    for uid in ["user_a", "user_b", "user_c"]:
        ids[uid] = store.add_subbrain_version(uid, doc("t", uid, ["x"]), "h").subbrain_id
    publish(store, "user_a", ids["user_a"])
    publish(store, "user_b", ids["user_b"])
    store.add_subbrain_version("user_b", doc("t", "b", ["new"]), "h2", subbrain_id=ids["user_b"])
    got = store.list_public_versions()
    assert [v.subbrain_id for v in got] == sorted([ids["user_a"], ids["user_b"]])
    assert all(v.version == 1 and v.is_published_version for v in got)
    assert [v.owner_id for v in store.list_public_versions(exclude_owner_id="user_a")] == ["user_b"]


# -- canals ---------------------------------------------------------------------


def test_canal_participants_and_context(store, world):
    canal = world["canal"]
    assert canal.id.startswith("cn_") and canal.participant_ids == {"user_a", "user_b", "user_c"}
    for uid in ["user_a", "user_b", "user_c"]:
        assert store.get_canal_for_viewer(uid, canal.id).id == canal.id
    e1 = assert_not_found(store.get_canal_for_viewer, "user_d", canal.id)
    e2 = assert_not_found(store.get_canal_for_viewer, "user_d", "cn_missing")
    assert same_error(e1, e2)

    ctx = store.canal_context(canal.id)
    assert set(ctx.subbrains) == {(world["sa"], 1), (world["sb"], 1), (world["sc"], 1)}
    assert ctx.host_owner_id == "user_a" and ctx.host_subbrain_id == world["sa"]

    # B adds v2 and goes private: B leaves the context but stays a participant (NEVER-02).
    store.add_subbrain_version("user_b", doc("게임2", "b", ["z"]), "hb2", subbrain_id=world["sb"])
    store.set_visibility("user_b", world["sb"], Visibility.PRIVATE)
    ctx = store.canal_context(canal.id)
    assert set(ctx.subbrains) == {(world["sa"], 1), (world["sc"], 1)}
    assert store.get_canal_for_viewer("user_b", canal.id).members[0].subbrain_id == world["sb"]
    # Republishing v2 brings B back at the pinned version 1, not latest.
    store.set_visibility("user_b", world["sb"], Visibility.PUBLIC, confirm_hash="hb2")
    assert (world["sb"], 1) in store.canal_context(canal.id).subbrains


def test_create_canal_rejects_foreign_host(store, world):
    assert_not_found(store.create_canal, "user_d", world["sa"], 1, "q", QueryMode.TOPIC, [])
    assert_not_found(store.create_canal, "user_a", world["sa"], 9, "q", QueryMode.TOPIC, [])
    assert_not_found(store.canal_context, "cn_missing")


def test_count_canals_in_month_uses_clock(store, world):
    month = world["canal"].created_at[:7]
    assert store.count_canals_in_month("user_a", month) == 1
    assert store.count_canals_in_month("user_b", month) == 0
    store.clock = lambda: datetime(2031, 1, 31, 23, 59, tzinfo=timezone.utc)
    store.create_canal("user_a", world["sa"], 1, "q2", QueryMode.WHOLE_HOST, [])
    assert store.count_canals_in_month("user_a", "2031-01") == 1
    assert store.count_canals_in_month("user_a", month) == 1
    with pytest.raises(ValueError):
        store.count_canals_in_month("user_a", "2031-1")


# -- deltabrains ----------------------------------------------------------------


def test_deltabrain_view_for_participants(store, world):
    view = store.get_deltabrain_for_viewer("user_b", world["db"])
    assert set(view) == {"id", "canal_id", "query", "host_subbrain_id", "created_at", "synthesizer", "stats",
                         "nodes", "edges", "contributors"}
    assert view["query"] == "모듈러 조립 오류" and view["synthesizer"]["model"] == "test"
    json.dumps(view)  # JSON-ready
    ref = view["nodes"][1]["provenance"][0]
    assert ref == {"subbrain_id": world["sa"], "version": 1, "node_id": "a1", "owner_id": "user_a",
                   "owner_display": "앨리스"}
    assert {c["owner_id"] for c in view["contributors"]} == {"user_a", "user_b", "user_c"}
    e1 = assert_not_found(store.get_deltabrain_for_viewer, "user_d", world["db"])
    e2 = assert_not_found(store.get_deltabrain_for_viewer, "user_d", "db_missing")
    assert same_error(e1, e2)
    assert store.get_deltabrain_record(world["db"]).submission == world["sub"]


def test_private_contributor_is_masked(store, world):
    store.set_visibility("user_b", world["sb"], Visibility.PRIVATE)
    sub2 = make_submission(world["sa"], world["sb"], world["sc"])
    # Second deltabrain on a second canal while B was public again, then private again.
    store.set_visibility("user_b", world["sb"], Visibility.PUBLIC, confirm_hash="hash_b1")
    db2 = store.save_deltabrain(world["canal"].id, "user_a", sub2, world["stats"]).id
    store.set_visibility("user_b", world["sb"], Visibility.PRIVATE)

    for viewer in ["user_a", "user_c"]:
        view = store.get_deltabrain_for_viewer(viewer, world["db"])
        text = json.dumps(view, ensure_ascii=False)
        assert "user_b" not in text and "밥빌더" not in text and world["sb"] not in text
        masked = [r for n in view["nodes"] + view["edges"] for r in n["provenance"] if r["owner_id"] is None]
        assert len(masked) == 2  # node nb + edge e1
        for r in masked:
            assert r["owner_display"] == MASKED_DISPLAY
            assert r["subbrain_id"] is None and r["version"] is None and r["node_id"] is None
        assert len({r["owner_token"] for r in masked}) == 1
        # Retained content stays visible (NEVER-02).
        assert any(n["label"] == "블록 조립 규칙" for n in view["nodes"])
        assert any(c.get("owner_token") == masked[0]["owner_token"] for c in view["contributors"])
        assert len(view["contributors"]) == 3

    tok1 = next(r["owner_token"] for r in store.get_deltabrain_for_viewer("user_a", world["db"])["nodes"][2]["provenance"])
    tok2 = next(r["owner_token"] for r in store.get_deltabrain_for_viewer("user_a", db2)["nodes"][2]["provenance"])
    assert tok1 != tok2
    assert tok1 == crypto.contributor_token(MASTER_KEY, "user_b", world["db"])

    # The owner still sees themself.
    own = store.get_deltabrain_for_viewer("user_b", world["db"])
    ref = own["nodes"][2]["provenance"][0]
    assert ref["owner_id"] == "user_b" and ref["owner_display"] == "밥빌더" and "owner_token" not in ref
    # B is still a participant and still lists the deltabrain.
    assert [d["id"] for d in store.list_deltabrains_for_viewer("user_b")] == [world["db"], db2]


def test_list_deltabrains_for_viewer(store, world):
    [item] = store.list_deltabrains_for_viewer("user_a")
    assert item == {"id": world["db"], "canal_id": world["canal"].id, "query": "모듈러 조립 오류",
                    "created_at": item["created_at"], "is_host": True,
                    "stats": {"node_count": 4, "edge_count": 3, "emergent_edge_count": 2}}
    assert store.list_deltabrains_for_viewer("user_c")[0]["is_host"] is False
    assert store.list_deltabrains_for_viewer("user_d") == []


def test_rate_edge_upsert(store, world):
    db = world["db"]
    store.rate_edge(EdgeRating(edge_id="e1", rater_id="user_a", novelty=1, validity=1, usefulness=0), db)
    store.rate_edge(EdgeRating(edge_id="e1", rater_id="user_a", novelty=0, validity=1, usefulness=1), db)
    store.rate_edge(EdgeRating(edge_id="e2", rater_id="user_b", novelty=1, validity=0, usefulness=1), db)
    got = store.ratings_for(db)
    assert [(r.edge_id, r.rater_id, r.novelty, r.usefulness) for r in got] == [("e1", "user_a", 0, 1),
                                                                              ("e2", "user_b", 1, 1)]
    assert_not_found(store.rate_edge, EdgeRating(edge_id="e1", rater_id="user_a", novelty=1, validity=1,
                                                  usefulness=1), "db_missing")


def test_audit_log_records_key_actions(store, world):
    actions = {r[0] for r in store._conn.execute("SELECT action FROM audit_log")}
    assert {"subbrain.visibility", "canal.open", "deltabrain.submit"} <= actions
    store.audit("user_a", "deltabrain.reject", world["canal"].id, {"codes": ["NO_EMERGENCE"]})
    row = store._conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 1").fetchone()
    assert row["action"] == "deltabrain.reject" and json.loads(row["detail_json"]) == {"codes": ["NO_EMERGENCE"]}


def test_no_delete_methods():
    assert not [name for name in dir(Store) if "delete" in name.lower() or "remove" in name.lower()]


# -- backup / file DB -------------------------------------------------------------


def test_snapshot_and_restore_roundtrip(tmp_path, store, world):
    data = store.snapshot_bytes()
    target = tmp_path / "restored" / "opencanal.db"
    Store.restore_bytes(target, data)
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600
    with pytest.raises(FileExistsError):
        Store.restore_bytes(target, data)
    with pytest.raises(ValueError):
        Store.restore_bytes(tmp_path / "junk.db", b"not sqlite")
    restored = Store(target, master_key=MASTER_KEY)
    try:
        assert restored.get_deltabrain_record(world["db"]).submission == world["sub"]
        assert restored.get_subbrain_for_viewer("user_d", world["sc"]).document.title == "세포"
    finally:
        restored.close()


def test_file_db_wal_and_threads(tmp_path):
    path = tmp_path / "data" / "x.db"
    s = Store(path, master_key=MASTER_KEY)
    try:
        assert s._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert s._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        errors: list[BaseException] = []

        def worker(i: int) -> None:
            try:
                s.create_user(f"u{i}", Tier.FREE, user_id=f"user_{i}")
            except BaseException as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert s._conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 20
        snap = s.snapshot_bytes()
        assert snap.startswith(b"SQLite format 3\x00")
    finally:
        s.close()
    restored_path = tmp_path / "r.db"
    Store.restore_bytes(restored_path, snap)
    raw = sqlite3.connect(restored_path)
    assert raw.execute("PRAGMA journal_mode").fetchone()[0] != "wal"  # self-contained image
    assert raw.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 20
    raw.close()
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 20
    conn.close()
