"""End-to-end Q-01 flow through Service.dispatch (TASK-001 §1 user result).

import -> publish with confirm_hash -> canal_open Q-01 -> canal_submit good-01 (ids rewritten to the real
subbrain ids/versions) -> every participant reads the deltabrain, a non-participant gets NOT_FOUND ->
deltabrain_rate on an emergent edge.
"""

from __future__ import annotations

from opencanal.models import PROTOCOL_VERSION

from .conftest import (
    Q01,
    World,
    assert_err,
    assert_ok,
    assert_same_not_found,
    dumps,
    fake_id_like,
    load_brain,
    load_delta,
    member_ids,
    pick,
    rewrite_provenance,
)

GOOD_EMERGENT = {"e3", "e4", "e5", "e6", "e7", "e8", "e9", "e10"}


def test_flow_q01_import_publish_open_submit_read_rate(world: World):
    # 1. import (private, sanitized preview) and publish with the preview hash
    for fid in ("A", "A2", "B", "C", "D", "P", "X"):
        brain = load_brain(fid)
        env = assert_ok(world.import_fixture(fid))
        assert env["version"] == 1
        assert env["preview"]["node_count"] == len(brain["document"]["nodes"])
        assert env["preview"]["edge_count"] == len(brain["document"]["edges"])
        assert env["preview"]["title"] == brain["document"]["title"]
        if brain["visibility"] == "public":
            summary = assert_ok(world.publish(fid))
            assert "public" in dumps(summary)

    # 2. canal_open Q-01
    canal = assert_ok(world.open_canal(query=Q01))
    assert canal["query_mode_used"] == "topic"
    assert canal["protocol"]["version"] == PROTOCOL_VERSION
    ids = member_ids(canal)
    assert {world.sid("B"), world.sid("C")} <= set(ids)
    assert world.sid("D") not in ids and world.sid("P") not in ids
    assert "untrusted_data" in canal and canal["untrusted_data"]["subbrains"]
    participants = {"user_a"} | {world.sb[f]["owner"] for f in world.sb if world.sid(f) in ids}
    assert {"user_a", "user_b", "user_c"} <= participants

    # every participant can see the canal
    for uid in participants:
        assert_ok(world.call(uid, "canal_get", canal_id=canal["canal_id"]))

    # 3. canal_submit good-01 with real ids
    delta = rewrite_provenance(load_delta("good-01"), world.mapping())
    sub = assert_ok(world.submit(canal["canal_id"], delta))
    db_id = sub["deltabrain_id"]
    assert set(sub["stats"]["emergent_edge_ids"]) == GOOD_EMERGENT
    assert set(sub["stats"]["host_touching_emergent_edge_ids"]) == GOOD_EMERGENT - {"e9"}

    # 4. every participant can read it; a non-participant cannot
    for uid in participants:
        env = assert_ok(world.call(uid, "deltabrain_get", deltabrain_id=db_id))
        graph = dumps(env["untrusted_data"]["deltabrain"])
        for label in ("형태 상보성", "현장 조립 오류", "잘못 놓을 수 없는 블록 모양", "접합부 상세", "비대칭 접합 키 설계"):
            assert label in graph
        listed = pick(assert_ok(world.call(uid, "deltabrain_list")), "deltabrains")
        assert db_id in dumps(listed)
    for outsider in ("user_d", "user_x"):
        assert outsider not in participants
        fake = fake_id_like(db_id)
        assert_same_not_found(
            world.call(outsider, "deltabrain_get", deltabrain_id=db_id),
            db_id,
            world.call(outsider, "deltabrain_get", deltabrain_id=fake),
            fake,
        )

    # 5. L2 label on an emergent edge (HUMAN-01 input)
    assert_ok(world.call("user_a", "deltabrain_rate", deltabrain_id=db_id, edge_id="e3", novelty=1, validity=1, usefulness=1))
    assert_ok(world.call("user_a", "deltabrain_rate", deltabrain_id=db_id, edge_id="e4", novelty=0, validity=1, usefulness=1))
    assert_err(
        world.call("user_a", "deltabrain_rate", deltabrain_id=db_id, edge_id="e1", novelty=1, validity=1, usefulness=1),
        "NOT_EMERGENT_EDGE",
    )
    assert_err(
        world.call("user_a", "deltabrain_rate", deltabrain_id=db_id, edge_id="e3", novelty=2, validity=1, usefulness=1),
        "INVALID_ARGUMENT",
    )
    env = assert_ok(world.call("user_a", "deltabrain_get", deltabrain_id=db_id))
    ratings = pick(env, "ratings")
    assert "e3" in dumps(ratings) and "e4" in dumps(ratings)
    rated = world.store.ratings_for(db_id)
    assert {(r.edge_id, r.rater_id, r.novelty, r.validity, r.usefulness) for r in rated} == {
        ("e3", "user_a", 1, 1, 1),
        ("e4", "user_a", 0, 1, 1),
    }
