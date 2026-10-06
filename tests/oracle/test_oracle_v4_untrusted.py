"""NEVER-06 and NEVER-09 as response-wide invariants (ORACLE §5.6, §5.7, §9 v.4).

NEVER-06: no response a Free user can get from the 11 Free tools — success or error — names a hidden tool.
NEVER-09 (v.4 scope): every string another user authored — subbrain content, display names, the host's
deltabrain node/edge ids, matching terms, the query, X's injection text — appears only under the top-level
`untrusted_data` key. Checked by a generic walker over whole envelopes (tests/oracle/_v4.py).
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

import pytest

from opencanal.models import ALLOWED_RELATIONS, Tier

from .conftest import (
    HIGHER_TIER_TOOLS,
    INJECTION_FRAGMENT,
    INJECTION_FRAGMENT_EN,
    Q01,
    Q01_TERMS,
    Q02,
    Q03,
    Q_SECURITY,
    World,
    assert_ok,
    dumps,
    load_brain,
    load_delta,
    rewrite_provenance,
)
from ._v4 import all_text, find_strings, foreign_hits, iter_strings

# ---------------------------------------------------------------------------
# NEVER-06 — hidden tool names never appear in any Free response
# ---------------------------------------------------------------------------


def _free_responses(world: World) -> list[tuple[str, dict[str, Any]]]:
    """Exercise every Free tool on its success path and every reachable error path; return (label, envelope)."""
    out: list[tuple[str, dict[str, Any]]] = []

    def call(label: str, user: str | None, tool: str, **args: Any) -> dict[str, Any]:
        env = world.call(user, tool, **args) if user else world.service.dispatch(None, tool, args)
        out.append((label, env))
        return env

    world.seed()
    for uid in world.tokens:
        assert world.user(uid).tier == Tier.FREE

    # subbrain_import
    new = call("import ok", "user_d", "subbrain_import", document=load_brain("D")["document"], format="canonical")
    call("import IMPORT_INVALID", "user_d", "subbrain_import", document={"title": "빈", "domains": ["x"], "nodes": [], "edges": []})
    call("import INVALID_ARGUMENT", "user_d", "subbrain_import")
    call("import bad format", "user_d", "subbrain_import", document=load_brain("D")["document"], format="obsidian")
    call("import NOT_FOUND", "user_a", "subbrain_import", document=load_brain("A")["document"], subbrain_id=world.sid("P"))
    # subbrain_list_mine
    call("list_mine a", "user_a", "subbrain_list_mine")
    call("list_mine b", "user_b", "subbrain_list_mine")
    # subbrain_get
    call("get own", "user_a", "subbrain_get", subbrain_id=world.sid("A"))
    call("get other public", "user_a", "subbrain_get", subbrain_id=world.sid("B"))
    call("get NOT_FOUND private", "user_a", "subbrain_get", subbrain_id=world.sid("P"))
    call("get INVALID_ARGUMENT", "user_a", "subbrain_get")
    call("get bad version", "user_a", "subbrain_get", subbrain_id=world.sid("A"), version="latest")
    # subbrain_set_visibility
    call("visibility LIMIT_EXCEEDED", "user_b", "subbrain_set_visibility", subbrain_id=world.sid("P"), visibility="public", confirm_hash=world.sb["P"]["content_hash"])
    call("visibility NOT_FOUND", "user_a", "subbrain_set_visibility", subbrain_id=world.sid("P"), visibility="private")
    call("visibility INVALID_ARGUMENT", "user_x", "subbrain_set_visibility", subbrain_id=world.sid("X"), visibility="deleted")
    call("visibility private ok", "user_x", "subbrain_set_visibility", subbrain_id=world.sid("X"), visibility="private")
    call("visibility CONFIRMATION_MISMATCH", "user_x", "subbrain_set_visibility", subbrain_id=world.sid("X"), visibility="public", confirm_hash="0" * 64)
    call("visibility public ok", "user_x", "subbrain_set_visibility", subbrain_id=world.sid("X"), visibility="public", confirm_hash=world.sb["X"]["content_hash"])
    # subbrain_search
    call("search ok", "user_a", "subbrain_search", query=Q01)
    call("search empty", "user_a", "subbrain_search", query=Q03)
    call("search INVALID_ARGUMENT", "user_a", "subbrain_search")
    call("search big limit", "user_a", "subbrain_search", query=Q01, limit=999)
    # canal_open
    canal = call("canal_open ok", "user_a", "canal_open", query=Q01, host_subbrain_id=world.sid("A"))
    call("canal_open whole_host", "user_a", "canal_open", query=Q02, host_subbrain_id=world.sid("A"))
    call("canal_open NO_RELEVANT", "user_a", "canal_open", query=Q03, host_subbrain_id=world.sid("A"))
    call("canal_open NOT_FOUND", "user_a", "canal_open", query=Q01, host_subbrain_id=world.sid("P"))
    call("canal_open HOST_NOT_PUBLIC", "user_d", "canal_open", query=Q01, host_subbrain_id=new["subbrain_id"])
    call("canal_open INVALID_ARGUMENT", "user_a", "canal_open", query=Q01, host_subbrain_id=world.sid("A"), query_mode="psychic")
    for i in range(world.cfg.limits_for_tier(Tier.FREE).canals_per_month + 1):
        env = call(f"canal_open c#{i}", "user_c", "canal_open", query=Q01, host_subbrain_id=world.sid("C"))
    assert env["ok"] is False and env["error"]["code"] == "LIMIT_EXCEEDED", "self-check: the monthly limit was reached"
    # canal_get
    canal_id = canal["canal_id"]
    call("canal_get host", "user_a", "canal_get", canal_id=canal_id)
    call("canal_get member", "user_b", "canal_get", canal_id=canal_id)
    call("canal_get NOT_FOUND", "user_d", "canal_get", canal_id=canal_id)
    # canal_submit
    mapping = world.mapping()
    call("submit VALIDATION_FAILED", "user_a", "canal_submit", canal_id=canal_id, deltabrain=rewrite_provenance(load_delta("bad-generic"), mapping))
    call("submit SCHEMA", "user_a", "canal_submit", canal_id=canal_id, deltabrain={"nodes": "nope"})
    call("submit NOT_CANAL_HOST", "user_b", "canal_submit", canal_id=canal_id, deltabrain=world.good01())
    call("submit NOT_FOUND", "user_d", "canal_submit", canal_id=canal_id, deltabrain=world.good01())
    sub = call("submit ok", "user_a", "canal_submit", canal_id=canal_id, deltabrain=world.good01())
    db_id = sub["deltabrain_id"]
    # deltabrain_get / list / rate
    call("db_get host", "user_a", "deltabrain_get", deltabrain_id=db_id)
    call("db_get member", "user_b", "deltabrain_get", deltabrain_id=db_id)
    call("db_get NOT_FOUND", "user_d", "deltabrain_get", deltabrain_id=db_id)
    call("db_list", "user_b", "deltabrain_list")
    call("rate ok", "user_b", "deltabrain_rate", deltabrain_id=db_id, edge_id="e3", novelty=1, validity=1, usefulness=1)
    call("rate NOT_EMERGENT_EDGE", "user_b", "deltabrain_rate", deltabrain_id=db_id, edge_id="e1", novelty=1, validity=1, usefulness=1)
    call("rate INVALID_ARGUMENT", "user_b", "deltabrain_rate", deltabrain_id=db_id, edge_id="e3", novelty=2, validity=1, usefulness=1)
    call("rate unknown edge", "user_b", "deltabrain_rate", deltabrain_id=db_id, edge_id="e404", novelty=1, validity=1, usefulness=1)
    call("rate NOT_FOUND", "user_d", "deltabrain_rate", deltabrain_id=db_id, edge_id="e3", novelty=1, validity=1, usefulness=1)
    # host switched private -> HOST_NOT_PUBLIC on submit
    assert_ok(world.make_private("A"))
    call("submit HOST_NOT_PUBLIC", "user_a", "canal_submit", canal_id=canal_id, deltabrain=world.good01())
    # unknown tools and no token
    call("UNKNOWN_TOOL", "user_a", "no_such_tool")
    call("UNKNOWN_TOOL delete", "user_a", "subbrain_delete", subbrain_id=world.sid("A"))
    call("UNAUTHORIZED", None, "subbrain_list_mine")
    call("UNAUTHORIZED hidden", None, "match_explain", query=Q01)
    return out


def test_never_06_v4_no_free_response_names_a_hidden_tool(world: World):
    responses = _free_responses(world)
    assert len({label for label, _ in responses}) == len(responses)
    codes = {env["error"]["code"] for _, env in responses if env["ok"] is False}
    assert {
        "IMPORT_INVALID",
        "NOT_FOUND",
        "CONFIRMATION_MISMATCH",
        "LIMIT_EXCEEDED",
        "NO_RELEVANT_SUBBRAIN",
        "HOST_NOT_PUBLIC",
        "VALIDATION_FAILED",
        "NOT_CANAL_HOST",
        "NOT_EMERGENT_EDGE",
        "INVALID_ARGUMENT",
        "UNKNOWN_TOOL",
        "UNAUTHORIZED",
    } <= codes, f"self-check: error paths exercised: {codes}"
    for label, env in responses:
        for _, text in iter_strings(env):
            for hidden in HIGHER_TIER_TOOLS:
                assert hidden not in text, f"{label}: hidden tool {hidden!r} named in a Free response: {text[:300]!r}"


def test_never_06_v4_tier_forbidden_does_not_advertise_other_hidden_tools(seeded: World):
    for tool in HIGHER_TIER_TOOLS:
        env = seeded.call("user_a", tool)
        assert env["ok"] is False and env["error"]["code"] == "TIER_FORBIDDEN"
        text = " ".join(all_text(env))
        for other in HIGHER_TIER_TOOLS:
            if other != tool:
                assert other not in text, f"calling {tool} advertises {other}: {dumps(env)}"


# ---------------------------------------------------------------------------
# NEVER-09 (v.4) — a generic walker over member responses in the Q-01 flow
# ---------------------------------------------------------------------------

FIXTURE_OWNER_OF = {fid: load_brain(fid)["owner"]["user_id"] for fid in ("A", "A2", "B", "C", "D", "P", "X")}


def _brain_strings(fid: str) -> tuple[set[str], set[str]]:
    brain = load_brain(fid)
    doc = brain["document"]
    long = {doc["title"], brain["owner"]["display_name"]}
    long |= {n["label"] for n in doc["nodes"]}
    long |= {n["summary"] for n in doc["nodes"] if n.get("summary")}
    long |= {e["summary"] for e in doc["edges"] if e.get("summary")}
    exact = set(doc["domains"])
    exact |= {t for n in doc["nodes"] for t in n.get("tags", [])}
    exact |= {n["id"] for n in doc["nodes"]} | {e["id"] for e in doc["edges"]}
    exact |= {e["relation"] for e in doc["edges"] if e.get("relation") and e["relation"] not in ALLOWED_RELATIONS}
    return long, exact


def _host_deltabrain_strings() -> tuple[set[str], set[str]]:
    """What the host (user_a) authored into the canal and its deltabrain (good-01) besides copied labels."""
    g = load_delta("good-01")
    long = {Q01, g["synthesizer"]["model"]}
    long |= {n["label"] for n in g["nodes"] if n["kind"] == "new"}
    long |= {n["summary"] for n in g["nodes"] if n.get("summary")}
    long |= {e[k] for e in g["edges"] for k in ("rationale", "applies_when") if e.get(k)}
    exact = {n["id"] for n in g["nodes"]} | {e["id"] for e in g["edges"]} | set(Q01_TERMS)
    return long, exact


_ID_RE = re.compile(r"[a-z]+-[a-z]?\d+|[a-z]+\d*|[a-z]-[a-z]+\d*")


def _tokens(texts: Iterable[str]) -> set[str]:
    """Words and contract tokens of a text (whole_host query terms of a viewer's own subbrain are the viewer's own)."""
    from opencanal.config import load_config
    from opencanal.textnorm import normalize, tokenize

    m = load_config().matching
    out: set[str] = set()
    for t in texts:
        out |= set(normalize(t).split())
        out |= set(tokenize(t, josa_suffixes=m.josa_suffixes, min_stem=m.josa_min_stem_length))
    return out


def own_strings(user_id: str, extra: Iterable[str] = ()) -> set[str]:
    """The viewer's own text: what they authored, its words/tokens (not of ids: "b-e3" does not make "e3" theirs)."""
    long, exact = authored(user_id)
    words = long | {x for x in exact if not _ID_RE.fullmatch(x)}
    return long | exact | _tokens(words) | set(extra) | _tokens(extra)


def authored(user_id: str) -> tuple[set[str], set[str]]:
    long: set[str] = set()
    exact: set[str] = set()
    for fid, owner in FIXTURE_OWNER_OF.items():
        if owner == user_id:
            lo, ex = _brain_strings(fid)
            long |= lo
            exact |= ex
    if user_id == "user_a":
        lo, ex = _host_deltabrain_strings()
        long |= lo
        exact |= ex
    return long, exact


def _static_protocol() -> Any:
    from opencanal.protocol import synthesis_protocol

    return json.loads(json.dumps(synthesis_protocol(), ensure_ascii=False, default=str))


def assert_others_only_in_untrusted(env: dict[str, Any], viewer: str, *, own_extra: Iterable[str] = (), label: str = "") -> None:
    others_long: set[str] = set()
    others_exact: set[str] = set()
    for uid in set(FIXTURE_OWNER_OF.values()) - {viewer}:
        lo, ex = authored(uid)
        others_long |= lo
        others_exact |= ex
    own = own_strings(viewer, own_extra)
    if viewer != "user_x":
        others_long |= {INJECTION_FRAGMENT, INJECTION_FRAGMENT_EN}
    skip_top = ("protocol",) if env.get("protocol") == _static_protocol() else ()
    hits = foreign_hits(env, long_needles=others_long, exact_needles=others_exact, own=own, skip_top=skip_top)
    assert not hits, f"{label} ({viewer}): another user's string outside untrusted_data: " + "; ".join(
        f"{'/'.join(map(str, p))} has {n!r}" for p, n, _ in hits[:8]
    )


@pytest.fixture
def q01_flow(seeded: World) -> dict[str, Any]:
    """Q-01 canal hosted by A (members A2, B, C), good-01 accepted, one rating by the host."""
    canal = assert_ok(seeded.open_canal(query=Q01))
    sub = assert_ok(seeded.submit(canal["canal_id"], seeded.good01()))
    assert_ok(seeded.call("user_a", "deltabrain_rate", deltabrain_id=sub["deltabrain_id"], edge_id="e3", novelty=1, validity=1, usefulness=1))
    return {"world": seeded, "canal": canal, "canal_id": canal["canal_id"], "db_id": sub["deltabrain_id"]}


MEMBER_QUERY = "단백질 형태 조립 오류"
MEMBER_QUERY_TERMS = ["단백질", "형태", "조립", "오류"]


@pytest.mark.parametrize("viewer", ["user_b", "user_c", "user_e"])
def test_never_09_v4_member_responses_keep_others_strings_in_untrusted_data(q01_flow, viewer):
    w: World = q01_flow["world"]
    canal_id, db_id = q01_flow["canal_id"], q01_flow["db_id"]
    w.set_tier(viewer, Tier.PRO)  # to reach deltabrain_export and match_explain
    own_sid = next(w.sid(f) for f, o in FIXTURE_OWNER_OF.items() if o == viewer and f in w.sb and f != "P")
    own_extra = [MEMBER_QUERY, Q_SECURITY, Q02]

    responses = {
        "canal_get": w.call(viewer, "canal_get", canal_id=canal_id),
        "deltabrain_get": w.call(viewer, "deltabrain_get", deltabrain_id=db_id),
        "deltabrain_list": w.call(viewer, "deltabrain_list"),
        "deltabrain_export": w.call(viewer, "deltabrain_export", deltabrain_id=db_id),
        "subbrain_search": w.call(viewer, "subbrain_search", query=MEMBER_QUERY, limit=20),
        "subbrain_search_x": w.call(viewer, "subbrain_search", query=Q_SECURITY, limit=20),
        "subbrain_get_host": w.call(viewer, "subbrain_get", subbrain_id=w.sid("A")),
        "subbrain_get_c": w.call(viewer, "subbrain_get", subbrain_id=w.sid("C")),
        "subbrain_get_x": w.call(viewer, "subbrain_get", subbrain_id=w.sid("X")),
        "match_explain": w.call(viewer, "match_explain", query=MEMBER_QUERY, host_subbrain_id=own_sid),
        "match_explain_whole": w.call(viewer, "match_explain", query=Q02, host_subbrain_id=own_sid),
    }
    for name, env in responses.items():
        assert_ok(env)
        assert_others_only_in_untrusted(env, viewer, own_extra=own_extra, label=name)

    # The walker is not vacuous: the foreign strings are served — as data.
    ud = lambda name: responses[name]["untrusted_data"]  # noqa: E731
    assert find_strings(ud("canal_get"), "공차 관리"), "host content served in canal_get"
    assert find_strings(ud("deltabrain_get"), "비대칭 접합 키 설계")
    assert any(s == "e3" for s in all_text(ud("deltabrain_get"))), "host edge ids are served (as data)"
    assert find_strings(ud("deltabrain_export"), "비대칭 접합 키 설계")
    assert find_strings(ud("subbrain_search_x"), load_brain("X")["document"]["title"])
    assert find_strings(ud("subbrain_get_x"), INJECTION_FRAGMENT)
    assert find_strings(ud("subbrain_get_host"), "Haram Kim") or find_strings(ud("subbrain_get_host"), "공차 관리")


def test_never_09_v4_host_responses_keep_member_strings_in_untrusted_data(q01_flow):
    w: World = q01_flow["world"]
    w.set_tier("user_a", Tier.PRO)
    responses = {
        "canal_open": q01_flow["canal"],
        "canal_open_x": w.open_canal(query=Q_SECURITY),
        "canal_get": w.call("user_a", "canal_get", canal_id=q01_flow["canal_id"]),
        "deltabrain_get": w.call("user_a", "deltabrain_get", deltabrain_id=q01_flow["db_id"]),
        "deltabrain_list": w.call("user_a", "deltabrain_list"),
        "deltabrain_export": w.call("user_a", "deltabrain_export", deltabrain_id=q01_flow["db_id"]),
        "subbrain_search": w.call("user_a", "subbrain_search", query=Q01, limit=20),
        "match_explain": w.call("user_a", "match_explain", query=Q01, host_subbrain_id=w.sid("A")),
    }
    own_extra = [Q_SECURITY]
    for name, env in responses.items():
        assert_ok(env)
        assert_others_only_in_untrusted(env, "user_a", own_extra=own_extra, label=name)
    assert find_strings(responses["canal_open_x"]["untrusted_data"], INJECTION_FRAGMENT)
    assert find_strings(responses["canal_get"]["untrusted_data"], "Bora Lee") or find_strings(
        responses["canal_get"]["untrusted_data"], "형태 상보성"
    )


def test_never_09_v4_walker_is_not_vacuous(q01_flow):
    """Guard for the walker itself: moving another user's strings next to untrusted_data must be caught."""
    w: World = q01_flow["world"]
    env = assert_ok(w.call("user_c", "deltabrain_get", deltabrain_id=q01_flow["db_id"]))
    assert_others_only_in_untrusted(env, "user_c", label="baseline")
    for leak in (
        {"edge": "e3"},  # a host-chosen edge id (exact)
        {"query": Q01},  # the host's query sentence
        {"owners": ["Haram Kim"]},  # another user's display name
        {"terms": ["모듈러", "현장"]},  # matching terms from the host's query
        {"note": "요약: " + load_brain("B")["document"]["nodes"][1]["summary"]},  # member content inside a longer string
        {"ids": ["s-a1", "n1"]},  # host-chosen node ids
        {INJECTION_FRAGMENT: 1},  # as a key
    ):
        bad = {**env, **leak}
        with pytest.raises(AssertionError):
            assert_others_only_in_untrusted(bad, "user_c", label=f"sabotaged {leak}")
    # The viewer's own text next to the envelope is not a leak.
    own = {**env, "mine": "형태 상보성", "my_terms": ["조립", "단백질"], "my_ids": ["c-n2"]}
    assert_others_only_in_untrusted(own, "user_c", label="own")
