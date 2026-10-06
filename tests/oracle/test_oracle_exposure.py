"""NEVER-01..05, NEVER-09..11, MUST-C1, MUST-C2 — subbrain exposure and canal rules (ORACLE §5.5, §5.7).

All behavior goes through Service.dispatch with real tokens (World.call authenticates every call).
"""

from __future__ import annotations

import pytest

from opencanal.models import Tier

from .conftest import (
    INJECTION_FRAGMENT,
    INJECTION_FRAGMENT_EN,
    PRIVATE_CONTRIBUTOR,
    Q01,
    Q_SECURITY,
    World,
    assert_err,
    assert_ok,
    assert_same_not_found,
    current_month,
    dumps,
    fake_id_like,
    find_dicts,
    load_brain,
    member_ids,
    pick,
    string_paths,
    violation_codes,
)


def _labels(fid: str) -> list[str]:
    return [n["label"] for n in load_brain(fid)["document"]["nodes"]]


def _content_strings(fid: str) -> list[str]:
    """Distinctive content of a brain: title, node labels, node summaries, edge summaries."""
    doc = load_brain(fid)["document"]
    out = [doc["title"], *(n["label"] for n in doc["nodes"])]
    out += [n["summary"] for n in doc["nodes"] if n.get("summary")]
    out += [e["summary"] for e in doc["edges"] if e.get("summary")]
    return out


def _with_extra_edge_ref(delta: dict, ref: dict) -> dict:
    for e in delta["edges"]:
        if e["id"] == "e9":
            e["provenance"] = [ref]
    return delta


# ---------------------------------------------------------------------------
# NEVER-01 — another user's private subbrain is invisible, even by direct id
# ---------------------------------------------------------------------------


def test_never_01_private_subbrain_invisible_in_search_and_canal(seeded: World):
    search = assert_ok(seeded.call("user_a", "subbrain_search", query=Q01))
    canal = assert_ok(seeded.open_canal(query=Q01))
    for env in (search, canal):
        text = dumps(env)
        assert seeded.sid("P") not in text
        for s in _content_strings("P"):
            assert s not in text, f"private content leaked: {s}"
    assert seeded.sid("P") not in member_ids(canal)


def test_never_01_direct_get_of_private_subbrain_is_not_found(seeded: World):
    pid = seeded.sid("P")
    fake = fake_id_like(pid)
    assert_same_not_found(
        seeded.call("user_a", "subbrain_get", subbrain_id=pid),
        pid,
        seeded.call("user_a", "subbrain_get", subbrain_id=fake),
        fake,
    )
    assert_same_not_found(
        seeded.call("user_a", "subbrain_get", subbrain_id=pid, version=1),
        pid,
        seeded.call("user_a", "subbrain_get", subbrain_id=fake, version=1),
        fake,
    )
    # Positive control: the owner still sees it.
    own = assert_ok(seeded.call("user_b", "subbrain_get", subbrain_id=pid))
    assert "성채 블록 조립 오류 로그" in dumps(own)


def test_never_01_private_subbrain_as_canal_host_is_not_found(seeded: World):
    """Using someone else's private subbrain as host must not answer HOST_NOT_PUBLIC (that would leak it)."""
    pid = seeded.sid("P")
    fake = fake_id_like(pid)
    month = current_month()
    before = seeded.store.count_canals_in_month("user_a", month)
    assert_same_not_found(
        seeded.call("user_a", "canal_open", query=Q01, host_subbrain_id=pid),
        pid,
        seeded.call("user_a", "canal_open", query=Q01, host_subbrain_id=fake),
        fake,
    )
    assert seeded.store.count_canals_in_month("user_a", month) == before


def test_never_01_other_owner_actions_on_private_subbrain_are_not_found(seeded: World):
    pid = seeded.sid("P")
    fake = fake_id_like(pid)
    doc = load_brain("A")["document"]
    assert_same_not_found(
        seeded.call("user_a", "subbrain_set_visibility", subbrain_id=pid, visibility="public", confirm_hash="0" * 64),
        pid,
        seeded.call("user_a", "subbrain_set_visibility", subbrain_id=fake, visibility="public", confirm_hash="0" * 64),
        fake,
    )
    assert_same_not_found(
        seeded.call("user_a", "subbrain_import", document=doc, format="canonical", subbrain_id=pid),
        pid,
        seeded.call("user_a", "subbrain_import", document=doc, format="canonical", subbrain_id=fake),
        fake,
    )
    # P is untouched: still private, still one version, still only in its owner's list.
    mine = pick(assert_ok(seeded.call("user_b", "subbrain_list_mine")), "subbrains")
    p = next(s for s in mine if s["subbrain_id"] == pid)
    assert p["visibility"] == "private" and p["latest_version"] == 1


def test_never_01_match_explain_on_private_subbrain_is_not_found(seeded: World):
    seeded.set_tier("user_a", Tier.PRO)
    pid = seeded.sid("P")
    fake = fake_id_like(pid)
    assert_same_not_found(
        seeded.call("user_a", "match_explain", query=Q01, host_subbrain_id=pid),
        pid,
        seeded.call("user_a", "match_explain", query=Q01, host_subbrain_id=fake),
        fake,
    )


# ---------------------------------------------------------------------------
# NEVER-02 — switching to private
# ---------------------------------------------------------------------------


def test_never_02_private_switch_effects(seeded: World):
    canal_id, db_id, _ = seeded.canal_with_deltabrain()
    bid = seeded.sid("B")
    assert_ok(seeded.make_private("B"))

    # Search and new canals drop B immediately.
    search = assert_ok(seeded.call("user_a", "subbrain_search", query=Q01))
    assert bid not in {r["subbrain_id"] for r in search["untrusted_data"]["results"]}
    new_canal = assert_ok(seeded.open_canal(query=Q01))
    assert bid not in member_ids(new_canal)

    # Existing canal: B's content is withheld.
    canal = assert_ok(seeded.call("user_a", "canal_get", canal_id=canal_id))
    text = dumps(canal)
    for s in _content_strings("B"):
        if s != "잘못 놓을 수 없는 블록 모양":  # the one B label good-01 carried into the deltabrain
            assert s not in text, f"withheld member content still served: {s}"
    # Oracle v.5 NEVER-11 + §9: a withheld entry carries an opaque per-canal `withheld_ref`, never the real
    # subbrain_id (was: located by the real subbrain_id).
    withheld = find_dicts(canal, lambda d: d.get("withheld") is True)
    assert withheld, "withdrawn member must be marked withheld:true"
    refs = {d.get("withheld_ref") for d in withheld}
    assert len(refs) == 1 and all(isinstance(r, str) and r for r in refs), f"one withheld_ref for B: {withheld}"
    assert bid not in text, "real subbrain_id of the withheld member shown (NEVER-11 v.5)"

    # Existing deltabrain keeps the derived nodes for every participant.
    for viewer in ("user_a", "user_b", "user_c"):
        db = assert_ok(seeded.call(viewer, "deltabrain_get", deltabrain_id=db_id))
        assert "잘못 놓을 수 없는 블록 모양" in dumps(db["untrusted_data"]["deltabrain"])
        assert "비대칭 접합 키 설계" in dumps(db["untrusted_data"]["deltabrain"])

    # The owner keeps seeing it in their own list.
    mine = pick(assert_ok(seeded.call("user_b", "subbrain_list_mine")), "subbrains")
    b = next(s for s in mine if s["subbrain_id"] == bid)
    assert b["visibility"] == "private"

    # A new submission citing B is outside the canal context now (TASK-001 §5).
    env = assert_err(seeded.submit(canal_id, seeded.good01()), "VALIDATION_FAILED")
    assert "PROVENANCE_OUT_OF_CANAL" in violation_codes(env)


def test_never_02_other_users_cannot_get_switched_subbrain(seeded: World):
    bid = seeded.sid("B")
    assert_ok(seeded.call("user_a", "subbrain_get", subbrain_id=bid))
    assert_ok(seeded.make_private("B"))
    fake = fake_id_like(bid)
    assert_same_not_found(
        seeded.call("user_a", "subbrain_get", subbrain_id=bid),
        bid,
        seeded.call("user_a", "subbrain_get", subbrain_id=fake),
        fake,
    )


# ---------------------------------------------------------------------------
# NEVER-03 — no delete; the server keeps every version
# ---------------------------------------------------------------------------


def test_never_03_no_delete_tool_in_any_tier(world: World):
    for tier in Tier:
        uid = f"user_tier_{tier.value}"
        world.add_user(uid, tier=tier)
        specs = world.service.tools_for(world.user(uid))
        for spec in specs:
            name = spec.name.lower()
            for verb in ("delete", "remove", "purge", "erase", "destroy", "drop"):
                assert verb not in name, f"{spec.name} looks like a delete tool"
        # DECISIONS D-005: user-facing words are 공개/비공개 only — never 삭제/철회.
        text = dumps([s.model_dump(mode="json") for s in specs])
        assert "삭제" not in text and "철회" not in text
    for tool in ("subbrain_delete", "deltabrain_delete", "canal_delete"):
        assert_err(world.call("user_tier_expert", tool, subbrain_id="x"), "UNKNOWN_TOOL")


def test_never_03_private_switch_and_new_versions_keep_all_data(seeded: World):
    aid = seeded.sid("A")
    v2_doc = load_brain("A")["document"]
    v2_doc["nodes"].append({"id": "a-n13", "label": "접합 철물 재고 표", "tags": ["철물"], "summary": "현장 반입 전 철물 수량을 맞춘다."})
    assert_ok(seeded.import_doc("user_a", v2_doc, subbrain_id=aid))
    assert_ok(seeded.make_private("A"))
    mine = pick(assert_ok(seeded.call("user_a", "subbrain_list_mine")), "subbrains")
    a = next(s for s in mine if s["subbrain_id"] == aid)
    assert a["visibility"] == "private" and a["latest_version"] == 2
    v1 = assert_ok(seeded.call("user_a", "subbrain_get", subbrain_id=aid, version=1))
    v2 = assert_ok(seeded.call("user_a", "subbrain_get", subbrain_id=aid, version=2))
    assert "접합 철물 재고 표" not in dumps(v1)
    assert "접합 철물 재고 표" in dumps(v2)
    # Store level: both versions are still rows.
    assert seeded.store.get_subbrain_for_viewer("user_a", aid, 1).version == 1
    assert seeded.store.get_subbrain_for_viewer("user_a", aid, 2).version == 2


# ---------------------------------------------------------------------------
# NEVER-04 — import sanitizes, starts private, publishing needs the preview hash
# ---------------------------------------------------------------------------

SENSITIVE_DOC = {
    "title": "현장 실측 메모 /Users/kim/vault/실측.md",
    "domains": ["건축"],
    "source_url": "https://notes.example.com/vault/42",
    "nodes": [
        {
            "id": "r-n1",
            "label": "접합부 실측 C:\\Logotekton\\vault\\접합부.md",
            "summary": "담당 kim.builder@example.com, 010-1234-5678. 원본 https://example.com/raw/1 참고",
            "tags": ["실측"],
            "content": "원문 청크: 회의록 전체 텍스트가 여기에 그대로 들어 있다",
            "source_url": "https://example.com/raw/1",
        },
        {"id": "r-n2", "label": "현장 사진 /home/kim/photos/0001.jpg", "summary": "기초 앵커 위치", "tags": ["사진"]},
    ],
    "edges": [{"id": "r-e1", "source": "r-n1", "target": "r-n2", "relation": "documents"}],
}
SENSITIVE_STRINGS = (
    "/Users/kim",
    "C:\\Logotekton",
    "/home/kim",
    "kim.builder@example.com",
    "010-1234-5678",
    "https://",
    "원문 청크",
)


def test_never_04_import_is_sanitized_private_and_needs_confirm_hash(world: World):
    env = assert_ok(world.import_doc("user_a", SENSITIVE_DOC))
    sid, chash = env["subbrain_id"], env["content_hash"]
    assert env["visibility"] == "private"
    kinds = {r["kind"] for r in env["redactions"]}
    assert {"dropped_field", "path", "email", "phone", "url"} <= kinds
    assert env["preview"]["node_count"] == 2 and env["preview"]["edge_count"] == 1
    stored = assert_ok(world.call("user_a", "subbrain_get", subbrain_id=sid))
    for text in (dumps(env["preview"]), dumps(stored)):
        for s in SENSITIVE_STRINGS:
            assert s not in text, f"sensitive value kept: {s}"
        assert "source_url" not in text

    # Private right after import: nobody else can see it.
    fake = fake_id_like(sid)
    assert_same_not_found(
        world.call("user_b", "subbrain_get", subbrain_id=sid), sid, world.call("user_b", "subbrain_get", subbrain_id=fake), fake
    )

    # Publishing requires the preview hash.
    missing = world.call("user_a", "subbrain_set_visibility", subbrain_id=sid, visibility="public")
    assert missing["ok"] is False and missing["error"]["code"] in {"CONFIRMATION_MISMATCH", "INVALID_ARGUMENT"}
    wrong = "f" * 64 if chash != "f" * 64 else "e" * 64
    assert_err(
        world.call("user_a", "subbrain_set_visibility", subbrain_id=sid, visibility="public", confirm_hash=wrong),
        "CONFIRMATION_MISMATCH",
    )
    assert_err(world.call("user_b", "subbrain_get", subbrain_id=sid), "NOT_FOUND")
    assert_ok(world.call("user_a", "subbrain_set_visibility", subbrain_id=sid, visibility="public", confirm_hash=chash))
    other = assert_ok(world.call("user_b", "subbrain_get", subbrain_id=sid))
    assert "subbrain" in other["untrusted_data"]


# ---------------------------------------------------------------------------
# NEVER-05 — non-participants cannot reach a canal or deltabrain by id
# ---------------------------------------------------------------------------


def test_never_05_non_participant_gets_not_found_for_canal_and_deltabrain(seeded: World):
    canal_id, db_id, sub = seeded.canal_with_deltabrain()
    fake_canal, fake_db = fake_id_like(canal_id), fake_id_like(db_id)
    edge = sub["stats"]["emergent_edge_ids"][0]
    for outsider in ("user_d", "user_x"):
        assert_same_not_found(
            seeded.call(outsider, "canal_get", canal_id=canal_id),
            canal_id,
            seeded.call(outsider, "canal_get", canal_id=fake_canal),
            fake_canal,
        )
        assert_same_not_found(
            seeded.call(outsider, "deltabrain_get", deltabrain_id=db_id),
            db_id,
            seeded.call(outsider, "deltabrain_get", deltabrain_id=fake_db),
            fake_db,
        )
        rate = dict(edge_id=edge, novelty=1, validity=1, usefulness=1)
        assert_same_not_found(
            seeded.call(outsider, "deltabrain_rate", deltabrain_id=db_id, **rate),
            db_id,
            seeded.call(outsider, "deltabrain_rate", deltabrain_id=fake_db, **rate),
            fake_db,
        )
        assert_same_not_found(
            seeded.call(outsider, "canal_submit", canal_id=canal_id, deltabrain=seeded.good01()),
            canal_id,
            seeded.call(outsider, "canal_submit", canal_id=fake_canal, deltabrain=seeded.good01()),
            fake_canal,
        )
        listed = pick(assert_ok(seeded.call(outsider, "deltabrain_list")), "deltabrains")
        assert db_id not in dumps(listed)
    seeded.set_tier("user_d", Tier.PRO)
    assert_same_not_found(
        seeded.call("user_d", "deltabrain_export", deltabrain_id=db_id),
        db_id,
        seeded.call("user_d", "deltabrain_export", deltabrain_id=fake_db),
        fake_db,
    )
    # Positive control: a member participant can read both.
    assert_ok(seeded.call("user_b", "canal_get", canal_id=canal_id))
    assert_ok(seeded.call("user_b", "deltabrain_get", deltabrain_id=db_id))


# ---------------------------------------------------------------------------
# NEVER-09 — other users' content lives only under untrusted_data
# ---------------------------------------------------------------------------


def _assert_only_under_untrusted(env: dict, needles: list[str]) -> None:
    for needle in needles:
        for path in string_paths(env, needle):
            assert path and path[0] == "untrusted_data", f"{needle!r} outside untrusted_data at {path}"


def test_never_09_injection_stays_inside_untrusted_data(seeded: World):
    x_content = _content_strings("X")
    canal = assert_ok(seeded.open_canal(query=Q_SECURITY))
    assert member_ids(canal) == [seeded.sid("X")]
    assert string_paths(canal["untrusted_data"], INJECTION_FRAGMENT), "X's summary is served (as data)"
    _assert_only_under_untrusted(canal, [INJECTION_FRAGMENT, INJECTION_FRAGMENT_EN, *x_content])

    search = assert_ok(seeded.call("user_a", "subbrain_search", query=Q_SECURITY))
    get = assert_ok(seeded.call("user_a", "subbrain_get", subbrain_id=seeded.sid("X")))
    canal_get = assert_ok(seeded.call("user_a", "canal_get", canal_id=canal["canal_id"]))
    for env in (search, get, canal_get):
        _assert_only_under_untrusted(env, [INJECTION_FRAGMENT, INJECTION_FRAGMENT_EN, *x_content])

    # The server did not act on the text: nothing else was dumped, nothing changed.
    for env in (canal, search, get, canal_get):
        text = dumps(env)
        for fid in ("P", "D", "B", "C", "A2"):
            assert load_brain(fid)["document"]["title"] not in text
    after = assert_ok(seeded.call("user_a", "subbrain_search", query=Q01))
    assert seeded.sid("P") not in dumps(after)
    mine = pick(assert_ok(seeded.call("user_a", "subbrain_list_mine")), "subbrains")
    assert [s["subbrain_id"] for s in mine] == [seeded.sid("A")]


def test_never_09_member_content_in_q01_canal_is_untrusted(seeded: World):
    canal = assert_ok(seeded.open_canal(query=Q01))
    needles = [s for fid in ("B", "C", "A2") for s in _content_strings(fid)]
    assert string_paths(canal["untrusted_data"], "형태 상보성"), "member content is served (as data)"
    _assert_only_under_untrusted(canal, needles)
    canal_id, db_id, _ = seeded.canal_with_deltabrain()
    db = assert_ok(seeded.call("user_b", "deltabrain_get", deltabrain_id=db_id))
    assert string_paths(db["untrusted_data"], "비대칭 접합 키 설계")
    _assert_only_under_untrusted(db, ["비대칭 접합 키 설계", "형태 상보성", "잘못 놓을 수 없는 블록 모양"])


# ---------------------------------------------------------------------------
# NEVER-10 — provenance from another canal is rejected
# ---------------------------------------------------------------------------


def test_never_10_citing_subbrain_from_another_canal_is_out_of_canal(seeded: World):
    canal_q01 = assert_ok(seeded.open_canal(query=Q01))
    canal_x = assert_ok(seeded.open_canal(query=Q_SECURITY))
    assert seeded.sid("X") in member_ids(canal_x) and seeded.sid("X") not in member_ids(canal_q01)

    foreign = _with_extra_edge_ref(seeded.good01(), {"subbrain_id": seeded.sid("X"), "version": 1, "node_id": "x-n2"})
    env = assert_err(seeded.submit(canal_q01["canal_id"], foreign), "VALIDATION_FAILED")
    assert "PROVENANCE_OUT_OF_CANAL" in violation_codes(env)

    # A private subbrain and a non-existent one are rejected the same way (no existence leak).
    pid = seeded.sid("P")
    fake = fake_id_like(pid)
    via_p = assert_err(
        seeded.submit(canal_q01["canal_id"], _with_extra_edge_ref(seeded.good01(), {"subbrain_id": pid, "version": 1, "node_id": "p-n2"})),
        "VALIDATION_FAILED",
    )
    via_fake = assert_err(
        seeded.submit(canal_q01["canal_id"], _with_extra_edge_ref(seeded.good01(), {"subbrain_id": fake, "version": 1, "node_id": "p-n2"})),
        "VALIDATION_FAILED",
    )
    assert violation_codes(via_p) == violation_codes(via_fake) == {"PROVENANCE_OUT_OF_CANAL"}
    assert dumps(via_p).replace(pid, "<ID>") == dumps(via_fake).replace(fake, "<ID>")
    assert pick(assert_ok(seeded.call("user_a", "deltabrain_list")), "deltabrains") == []


# ---------------------------------------------------------------------------
# NEVER-11 — private contributors are shown only as an encrypted token
# ---------------------------------------------------------------------------


def _owner_tokens(db_env: dict) -> set[str]:
    masked = find_dicts(db_env, lambda d: PRIVATE_CONTRIBUTOR in [v for v in d.values() if isinstance(v, str)])
    assert masked, f"no {PRIVATE_CONTRIBUTOR} entries in {dumps(db_env)[:1500]}"
    tokens = set()
    for d in masked:
        assert d.get("owner_id") in (None, ""), d
        assert isinstance(d.get("owner_token"), str) and d["owner_token"], d
        tokens.add(d["owner_token"])
    return tokens


def test_never_11_private_contributor_is_encrypted_token(seeded: World):
    from opencanal import crypto

    _, db1, _ = seeded.canal_with_deltabrain()
    _, db2, _ = seeded.canal_with_deltabrain()
    assert db1 != db2
    assert_ok(seeded.make_private("C"))
    c_display = load_brain("C")["owner"]["display_name"]

    tokens: dict[str, set[str]] = {}
    for db_id in (db1, db2):
        for viewer in ("user_a", "user_b", "user_e"):
            env = assert_ok(seeded.call(viewer, "deltabrain_get", deltabrain_id=db_id))
            text = dumps(env)
            assert PRIVATE_CONTRIBUTOR in text
            assert "user_c" not in text, f"owner id of a private contributor visible to {viewer}"
            assert c_display not in text, f"owner name of a private contributor visible to {viewer}"
            assert "형태 상보성" in dumps(env["untrusted_data"]["deltabrain"]), "retained content stays (NEVER-02)"
            toks = _owner_tokens(env)
            assert len(toks) == 1, "same contributor -> same token within one deltabrain"
            tokens.setdefault(db_id, set()).update(toks)
        assert len(tokens[db_id]) == 1, "token does not depend on who is viewing"

    t1, t2 = next(iter(tokens[db1])), next(iter(tokens[db2]))
    assert t1 != t2, "tokens differ across deltabrains (no cross-linking)"
    assert crypto.decrypt_contributor_token(seeded.master_key, t1) == ("user_c", db1)
    assert crypto.decrypt_contributor_token(seeded.master_key, t2) == ("user_c", db2)
    assert "user_c" not in t1 and "user_c" not in t2

    # Public contributors are still shown normally (only the private one is masked).
    env_a = assert_ok(seeded.call("user_a", "deltabrain_get", deltabrain_id=db1))
    assert "user_b" in dumps(env_a) or load_brain("B")["owner"]["display_name"] in dumps(env_a)


def test_never_11_owner_of_private_subbrain_still_sees_own_identity(seeded: World):
    _, db_id, _ = seeded.canal_with_deltabrain()
    assert_ok(seeded.make_private("C"))
    env = assert_ok(seeded.call("user_c", "deltabrain_get", deltabrain_id=db_id))
    # Store contract (get_deltabrain_for_viewer): owner info is shown when the viewer is the owner.
    assert PRIVATE_CONTRIBUTOR not in dumps(env)


# ---------------------------------------------------------------------------
# MUST-C1 / MUST-C2 — canal rules
# ---------------------------------------------------------------------------


def test_must_c1_private_host_cannot_open_canal(world: World):
    world.seed(skip_publish=("A",))
    month = current_month()
    assert_err(world.open_canal(query=Q01), "HOST_NOT_PUBLIC")
    assert world.store.count_canals_in_month("user_a", month) == 0


def test_must_c1_host_turned_private_cannot_submit(seeded: World):
    canal = assert_ok(seeded.open_canal(query=Q01))
    assert_ok(seeded.make_private("A"))
    assert_err(seeded.submit(canal["canal_id"], seeded.good01()), "HOST_NOT_PUBLIC")
    assert pick(assert_ok(seeded.call("user_a", "deltabrain_list")), "deltabrains") == []


def test_must_c2_only_host_can_submit(seeded: World):
    canal = assert_ok(seeded.open_canal(query=Q01))
    assert_err(seeded.submit(canal["canal_id"], seeded.good01(), user_id="user_b"), "NOT_CANAL_HOST")
    assert_err(seeded.submit(canal["canal_id"], seeded.good01(), user_id="user_c"), "NOT_CANAL_HOST")
    assert_err(seeded.submit(canal["canal_id"], seeded.good01(), user_id="user_d"), "NOT_FOUND")
    for viewer in ("user_a", "user_b"):
        assert pick(assert_ok(seeded.call(viewer, "deltabrain_list")), "deltabrains") == []
    assert_ok(seeded.submit(canal["canal_id"], seeded.good01()))
