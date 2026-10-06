"""Unit tests for the MCP transport, ASGI app and CLI (Builder MCP).

Service is faked where the real one may still be a stub; tests that need the real Service/Store/crypto
skip with a clear reason when a dependency still raises NotImplementedError.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import stat
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

import anyio
import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.memory import create_connected_server_and_client_session

from opencanal import cli
from opencanal.app import create_app
from opencanal.mcp_server import (
    INSTRUCTIONS,
    TokenMaskFilter,
    build_mcp,
    mask_token,
    mask_tokens_in_text,
)
from opencanal.models import Tier, ToolSpec, User

GOOD = "oc_goodtoken_0123456789abcdef"
PRO = "oc_protoken_0123456789abcdef"
HIGHER_TIER_TOOLS = ("match_explain", "deltabrain_export", "canal_synthesize")


# ---------------------------------------------------------------------------
# fakes and helpers
# ---------------------------------------------------------------------------


class FakeService:
    """Minimal stand-in exposing authenticate / tools_for / dispatch."""

    def __init__(self, *, raise_on_dispatch: bool = False) -> None:
        self.calls: list[tuple[Optional[str], str, dict[str, Any]]] = []
        self.raise_on_dispatch = raise_on_dispatch
        self.users = {
            GOOD: User(id="user_a", display_name="건축가 A", tier=Tier.FREE),
            PRO: User(id="user_p", display_name="프로", tier=Tier.PRO),
        }

    def authenticate(self, token: Optional[str]) -> Optional[User]:
        return self.users.get(token or "")

    def tools_for(self, user: Optional[User]) -> list[ToolSpec]:
        if user is None:
            return []
        names = ["subbrain_list_mine", "subbrain_import"]
        if user.tier is not Tier.FREE:
            names.append("match_explain")
        return [
            ToolSpec(name=n, description=f"{n} 설명", input_schema={"type": "object", "properties": {}}) for n in names
        ]

    def dispatch(self, user: Optional[User], tool: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((user.id if user else None, tool, dict(args)))
        if self.raise_on_dispatch:
            raise RuntimeError("secret other-user content in exception text")
        if user is None:
            return {"ok": False, "error": {"code": "UNAUTHORIZED", "message": "인증 실패"}}
        if tool == "match_explain" and user.tier is Tier.FREE:
            return {"ok": False, "error": {"code": "TIER_FORBIDDEN", "message": "tier"}}
        return {"ok": True, "tool": tool, "user": user.id, "untrusted_data": {"note": "다른 사용자 내용"}}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def serve_in_thread(app_factory: Callable[[], Any], *, log_level: str = "warning") -> Iterator[str]:
    """Run uvicorn on a free port in a thread; the app is built inside that thread. Yields base URL."""
    import uvicorn

    port = _free_port()
    holder: dict[str, Any] = {}

    def run() -> None:
        try:
            server = uvicorn.Server(uvicorn.Config(app_factory(), host="127.0.0.1", port=port, log_level=log_level))
            holder["server"] = server
            server.run()
        except BaseException as exc:  # surface startup errors to the test thread
            holder["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if "error" in holder:
            raise holder["error"]
        server = holder.get("server")
        if server is not None and server.started:
            break
        time.sleep(0.02)
    else:
        raise RuntimeError("uvicorn did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        holder["server"].should_exit = True
        thread.join(timeout=10)


async def _http_session_roundtrip(url: str, tool: str, args: dict[str, Any]) -> tuple[Any, Any, Any]:
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool(tool, args)
            return init, tools, result


def _envelope(result: Any) -> dict[str, Any]:
    assert len(result.content) == 1, "tools/call must return exactly one content block"
    block = result.content[0]
    assert block.type == "text"
    return json.loads(block.text)


def _require_real(*factories: Callable[[], Any]) -> None:
    for factory in factories:
        try:
            factory()
        except NotImplementedError as exc:
            pytest.skip(f"dependency module is still a stub: {exc!r} from {factory.__name__}")


# ---------------------------------------------------------------------------
# HTTP transport with a fake Service
# ---------------------------------------------------------------------------


def test_http_roundtrip_user_comes_from_url_token() -> None:
    fake = FakeService()
    with serve_in_thread(lambda: create_app(fake)) as base:
        assert httpx.get(f"{base}/health").json() == {"ok": True}
        init, tools, result = anyio.run(
            _http_session_roundtrip, f"{base}/mcp/{GOOD}", "subbrain_list_mine", {"user_id": "user_b"}
        )

    assert init.serverInfo.name == "opencanal"
    assert [t.name for t in tools.tools] == ["subbrain_list_mine", "subbrain_import"]
    assert tools.tools[0].inputSchema == {"type": "object", "properties": {}}
    envelope = _envelope(result)
    assert envelope == {"ok": True, "tool": "subbrain_list_mine", "user": "user_a", "untrusted_data": {"note": "다른 사용자 내용"}}
    assert "다른 사용자 내용" in result.content[0].text  # ensure_ascii=False
    # identity from the token only; the user_id argument is passed through untouched for Service to ignore
    assert fake.calls == [("user_a", "subbrain_list_mine", {"user_id": "user_b"})]


def test_http_bogus_token_fails_closed() -> None:
    fake = FakeService()
    with serve_in_thread(lambda: create_app(fake)) as base:
        _, tools, result = anyio.run(_http_session_roundtrip, f"{base}/mcp/oc_bogus_token", "subbrain_list_mine", {})
    assert tools.tools == []
    assert _envelope(result)["error"]["code"] == "UNAUTHORIZED"
    assert fake.calls and all(user is None for user, _, _ in fake.calls)


def test_http_free_tier_never_sees_higher_tier_tools_but_pro_does() -> None:
    fake = FakeService()
    with serve_in_thread(lambda: create_app(fake)) as base:
        init, free_tools, free_call = anyio.run(_http_session_roundtrip, f"{base}/mcp/{GOOD}", "match_explain", {})
        _, pro_tools, pro_call = anyio.run(_http_session_roundtrip, f"{base}/mcp/{PRO}", "match_explain", {})

    assert "match_explain" not in [t.name for t in free_tools.tools]
    assert _envelope(free_call)["error"]["code"] == "TIER_FORBIDDEN"  # direct call still reaches Service gating
    assert "match_explain" in [t.name for t in pro_tools.tools]
    assert _envelope(pro_call)["ok"] is True
    blob = init.model_dump_json()
    assert not any(name in blob for name in HIGHER_TIER_TOOLS)


def test_mcp_endpoint_requires_a_token_segment() -> None:
    fake = FakeService()
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    headers = {"Accept": "application/json, text/event-stream"}
    with serve_in_thread(lambda: create_app(fake)) as base:
        bare = httpx.post(f"{base}/mcp", json=body, headers=headers)
        slash = httpx.post(f"{base}/mcp/", json=body, headers=headers)
    assert bare.status_code != 200
    assert slash.status_code == 404
    assert fake.calls == []


def test_http_rejects_foreign_host_header() -> None:
    fake = FakeService()
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    headers = {"Accept": "application/json, text/event-stream", "Host": "evil.example:8765"}
    with serve_in_thread(lambda: create_app(fake)) as base:
        response = httpx.post(f"{base}/mcp/{GOOD}", json=body, headers=headers)
    assert response.status_code in (400, 421)
    assert fake.calls == []


def test_access_log_never_contains_full_token() -> None:
    fake = FakeService()
    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    capture = Capture()
    with serve_in_thread(lambda: create_app(fake), log_level="info") as base:
        logging.getLogger("uvicorn.access").addHandler(capture)
        try:
            anyio.run(_http_session_roundtrip, f"{base}/mcp/{GOOD}", "subbrain_list_mine", {})
        finally:
            logging.getLogger("uvicorn.access").removeHandler(capture)
    joined = "\n".join(records)
    assert "/mcp/" + GOOD[:6] in joined
    assert GOOD not in joined


# ---------------------------------------------------------------------------
# FastMCP subclass without HTTP (stdio path uses the same handlers)
# ---------------------------------------------------------------------------


def test_stdio_token_authenticates_in_memory() -> None:
    fake = FakeService()

    async def go() -> tuple[Any, Any]:
        async with create_connected_server_and_client_session(build_mcp(fake, stdio_token=GOOD)) as session:
            return await session.list_tools(), await session.call_tool("subbrain_import", {"document": {}})

    tools, result = anyio.run(go)
    assert [t.name for t in tools.tools] == ["subbrain_list_mine", "subbrain_import"]
    assert _envelope(result)["user"] == "user_a"
    assert fake.calls == [("user_a", "subbrain_import", {"document": {}})]


@pytest.mark.parametrize("stdio_token", [None, "", "   ", "oc_unknown"])
def test_missing_or_unknown_stdio_token_fails_closed(stdio_token: Optional[str]) -> None:
    fake = FakeService()

    async def go() -> tuple[Any, Any]:
        async with create_connected_server_and_client_session(build_mcp(fake, stdio_token=stdio_token)) as session:
            return await session.list_tools(), await session.call_tool("subbrain_list_mine", {})

    tools, result = anyio.run(go)
    assert tools.tools == []
    assert _envelope(result)["error"]["code"] == "UNAUTHORIZED"


def test_dispatch_exception_does_not_leak_exception_text() -> None:
    fake = FakeService(raise_on_dispatch=True)

    async def go() -> Any:
        async with create_connected_server_and_client_session(build_mcp(fake, stdio_token=GOOD)) as session:
            return await session.call_tool("subbrain_list_mine", {})

    result = anyio.run(go)
    envelope = _envelope(result)
    # Same fallback envelope as Service.dispatch's own internal-error path (one code across layers).
    assert envelope == {"ok": False, "error": {"code": "INTERNAL", "message": "internal error"}}
    assert "secret" not in result.content[0].text


def test_list_tools_fails_closed_when_service_raises() -> None:
    class Broken(FakeService):
        def tools_for(self, user: Optional[User]) -> list[ToolSpec]:
            raise RuntimeError("store down")

    async def go() -> Any:
        async with create_connected_server_and_client_session(build_mcp(Broken(), stdio_token=GOOD)) as session:
            return await session.list_tools()

    assert anyio.run(go).tools == []


def test_server_settings() -> None:
    server = build_mcp(FakeService())
    settings = server.settings
    assert settings.streamable_http_path == "/{mcp_token}"
    assert settings.stateless_http is True
    assert settings.json_response is True
    security = settings.transport_security
    assert security is not None and security.enable_dns_rebinding_protection
    assert security.allowed_hosts == ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    assert security.allowed_origins == ["http://127.0.0.1:*", "http://localhost:*"]
    assert server._tool_manager.list_tools() == []  # registry lives in Service, not in FastMCP
    assert not any(name in INSTRUCTIONS for name in HIGHER_TIER_TOOLS)


# ---------------------------------------------------------------------------
# token masking
# ---------------------------------------------------------------------------


def test_mask_helpers() -> None:
    assert mask_token(GOOD) == GOOD[:6] + "…"
    assert mask_token(None) == "<none>"
    text = f'"POST /mcp/{GOOD} HTTP/1.1" and /mcp/{PRO}?x=1'
    masked = mask_tokens_in_text(text)
    assert GOOD not in masked and PRO not in masked
    assert f"/mcp/{GOOD[:6]}…" in masked


def test_token_filter_keeps_uvicorn_access_args_shape() -> None:
    from uvicorn.logging import AccessFormatter

    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "POST", f"/mcp/{GOOD}", "1.1", 200), None,
    )
    assert TokenMaskFilter().filter(record) is True
    assert isinstance(record.args, tuple) and len(record.args) == 5
    line = AccessFormatter(use_colors=False).format(record)
    assert GOOD not in line and f"/mcp/{GOOD[:6]}…" in line


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["init-db"], {"command": "init-db"}),
        (["create-user", "--name", "가", "--tier", "pro"], {"name": "가", "tier": "pro", "user_id": None}),
        (["create-user", "--name", "b", "--tier", "free", "--user-id", "user_b"], {"user_id": "user_b"}),
        (["rotate-token", "--user-id", "u"], {"user_id": "u"}),
        (["set-tier", "--user-id", "u", "--tier", "expert"], {"tier": "expert"}),
        (["seed-fixtures"], {"fixtures": None}),
        (["seed-fixtures", "--fixtures", "fx"], {"fixtures": "fx"}),
        (["serve"], {"host": "127.0.0.1", "port": 8765}),
        (["serve", "--host", "localhost", "--port", "9000"], {"host": "localhost", "port": 9000}),
        (["mcp-stdio"], {"command": "mcp-stdio"}),
        (
            ["match-explain", "--token", "t", "--query", "q", "--host-subbrain-id", "s", "--mode", "whole_host"],
            {"token": "t", "query": "q", "host_subbrain_id": "s", "mode": "whole_host"},
        ),
        (["backup"], {"out": None}),
        (["backup", "--out", "b"], {"out": "b"}),
        (["restore", "--in", "f.enc", "--db", "new.db"], {"in_file": "f.enc", "db": "new.db"}),
        (["--db", "x.db", "--key-file", "k", "init-db"], {"db": "x.db", "key_file": "k"}),
        (["init-db", "--db", "y.db", "--config-dir", "cfg"], {"db": "y.db", "config_dir": "cfg"}),
    ],
)
def test_cli_parsing(argv: list[str], expected: dict[str, Any]) -> None:
    args = cli.build_parser().parse_args(argv)
    for key, value in expected.items():
        assert getattr(args, key) == value
    assert callable(args.handler)


@pytest.mark.parametrize(
    "argv",
    [
        ["create-user", "--name", "x", "--tier", "gold"],
        ["create-user", "--tier", "free"],
        ["set-tier", "--user-id", "u"],
        ["match-explain", "--query", "q"],
        ["match-explain", "--query", "q", "--host-subbrain-id", "s", "--mode", "bogus"],
        ["restore"],
        ["no-such-command"],
        [],
    ],
)
def test_cli_usage_errors_return_2(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(argv) == 2


def test_cli_help_returns_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--help"]) == 0
    assert "seed-fixtures" in capsys.readouterr().out


def test_restore_requires_explicit_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OPENCANAL_DB", str(tmp_path / "env.db"))  # env must not count for restore
    assert cli.main(["restore", "--in", str(tmp_path / "x.enc")]) == 1
    assert "--db" in capsys.readouterr().err


def test_mcp_url_format() -> None:
    assert cli.mcp_url("oc_x") == "http://127.0.0.1:8765/mcp/oc_x"
    assert cli.mcp_url("oc_x", "::1", 9) == "http://[::1]:9/mcp/oc_x"


def test_format_table_strips_control_chars_and_aligns_korean() -> None:
    table = cli.format_table(["a", "b"], [["가나", "\x1b[31mred\x1b[0m"], ["x", 0.25]])
    assert "\x1b" not in table
    lines = table.splitlines()
    assert lines[2].startswith("가나  ") and lines[3].startswith("x     ")
    assert "0.250" in lines[3]


# ---------------------------------------------------------------------------
# CLI commands with fakes (seed-fixtures, match-explain)
# ---------------------------------------------------------------------------


class FakeStore:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.closed = False

    def get_user(self, user_id: str) -> Optional[User]:
        return self.users.get(user_id)

    def create_user(self, display_name: str, tier: Tier, *, user_id: Optional[str] = None) -> tuple[User, str]:
        user = User(id=user_id or f"u{len(self.users)}", display_name=display_name, tier=tier)
        self.users[user.id] = user
        return user, f"oc_token_for_{user.id}"

    def close(self) -> None:
        self.closed = True


class SeedService:
    """Fake Service for seed-fixtures: remembers imports so a second run sees them in list_mine."""

    def __init__(self, *, fail_publish_for: str = "") -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.subbrains: dict[str, list[dict[str, Any]]] = {}
        self.fail_publish_for = fail_publish_for

    def dispatch(self, user: User, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((user.id, tool, args))
        mine = self.subbrains.setdefault(user.id, [])
        if tool == "subbrain_list_mine":
            return {"ok": True, "subbrains": list(mine)}
        if tool == "subbrain_import":
            sid = f"sb_{user.id}_{len(mine)}"
            mine.append({"subbrain_id": sid, "title": args["document"]["title"], "visibility": "private", "latest_version": 1})
            return {"ok": True, "subbrain_id": sid, "version": 1, "visibility": "private",
                    "content_hash": f"hash_{sid}", "redactions": [{"kind": "email"}], "preview": {}}
        if tool == "subbrain_set_visibility":
            if user.id == self.fail_publish_for:
                return {"ok": False, "error": {"code": "LIMIT_EXCEEDED", "message": "public limit"}}
            for summary in mine:
                if summary["subbrain_id"] == args["subbrain_id"]:
                    summary["visibility"] = args["visibility"]
            return {"ok": True, "subbrain_id": args["subbrain_id"], "visibility": args["visibility"]}
        raise AssertionError(f"unexpected tool {tool}")


def _write_fixture(directory: Path, fid: str, user_id: str, tier: str, visibility: str, title: str) -> None:
    doc = {"title": title, "domains": ["d"], "nodes": [{"id": "n1", "label": "L"}], "edges": []}
    payload = {
        "fixture_id": fid,
        "owner": {"user_id": user_id, "display_name": f"이름 {user_id}", "tier": tier},
        "visibility": visibility,
        "document": doc,
    }
    (directory / f"{fid}.json").write_text(json.dumps(payload, ensure_ascii=False), "utf-8")


@pytest.fixture
def fake_runtime(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeStore, dict[str, Any]]:
    store = FakeStore()
    holder: dict[str, Any] = {}

    @contextmanager
    def open_store(args: Any, *, must_exist: bool = False) -> Iterator[tuple[FakeStore, bytes]]:
        yield store, b"k" * 32

    monkeypatch.setattr(cli, "_open_store", open_store)
    monkeypatch.setattr(cli, "_service", lambda args, st: holder["service"])
    return store, holder


def test_seed_fixtures_imports_publishes_and_prints_tokens_once(
    tmp_path: Path, fake_runtime: tuple[FakeStore, dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    store, holder = fake_runtime
    service = holder["service"] = SeedService()
    _write_fixture(tmp_path, "A", "user_a", "pro", "public", "모듈러 건축")
    _write_fixture(tmp_path, "B", "user_b", "free", "public", "블록 게임")
    _write_fixture(tmp_path, "P", "user_b", "free", "private", "비공개 게임")

    assert cli.main(["seed-fixtures", "--fixtures", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert set(store.users) == {"user_a", "user_b"}
    assert store.users["user_a"].tier is Tier.PRO and store.users["user_b"].display_name == "이름 user_b"
    assert out.count("oc_token_for_user_b") == 2  # token + URL on one line, printed for the new user only
    assert "http://127.0.0.1:8765/mcp/oc_token_for_user_a" in out

    imports = [c for c in service.calls if c[1] == "subbrain_import"]
    assert [c[2]["document"]["title"] for c in imports] == ["모듈러 건축", "블록 게임", "비공개 게임"]
    publishes = [c for c in service.calls if c[1] == "subbrain_set_visibility"]
    assert publishes == [
        ("user_a", "subbrain_set_visibility",
         {"subbrain_id": "sb_user_a_0", "visibility": "public", "version": 1, "confirm_hash": "hash_sb_user_a_0"}),
        ("user_b", "subbrain_set_visibility",
         {"subbrain_id": "sb_user_b_0", "visibility": "public", "version": 1, "confirm_hash": "hash_sb_user_b_0"}),
    ]

    # second run: no new users, no duplicate imports, no tokens
    service.calls.clear()
    assert cli.main(["seed-fixtures", "--fixtures", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "oc_token_for" not in out and "exists (skipped)" in out
    assert not [c for c in service.calls if c[1] != "subbrain_list_mine"]


def test_seed_fixtures_reports_publish_failure(
    tmp_path: Path, fake_runtime: tuple[FakeStore, dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    _, holder = fake_runtime
    holder["service"] = SeedService(fail_publish_for="user_a")
    _write_fixture(tmp_path, "A", "user_a", "free", "public", "t")
    assert cli.main(["seed-fixtures", "--fixtures", str(tmp_path)]) == 1
    assert "LIMIT_EXCEEDED" in capsys.readouterr().out


def test_seed_fixtures_empty_dir_is_an_error(
    tmp_path: Path, fake_runtime: tuple[FakeStore, dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    holder = fake_runtime[1]
    holder["service"] = SeedService()
    assert cli.main(["seed-fixtures", "--fixtures", str(tmp_path)]) == 1


class ExplainService:
    def __init__(self, envelope: dict[str, Any]) -> None:
        self.envelope = envelope
        self.calls: list[tuple[Optional[User], str, dict[str, Any]]] = []

    def authenticate(self, token: Optional[str]) -> Optional[User]:
        return User(id="user_a", display_name="A", tier=Tier.PRO) if token == PRO else None

    def dispatch(self, user: Optional[User], tool: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((user, tool, args))
        if user is None:
            return {"ok": False, "error": {"code": "UNAUTHORIZED", "message": "no"}}
        return self.envelope


def test_match_explain_prints_candidates(
    fake_runtime: tuple[FakeStore, dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    candidate = {
        "subbrain_id": "sb_c", "version": 2, "owner_id": "user_c", "relevance": 0.6, "distance": 1.0,
        "matched_terms": ["조립", "오류"], "selected": True, "reason": "selected",
    }
    below = dict(candidate, subbrain_id="sb_d", relevance=0.0, matched_terms=[], selected=False, reason="below_tau")
    envelope = {"ok": True, "query_mode_used": "topic", "strategy": "relevance_plus_diversity", "tau": 0.2,
                "query_terms": ["모듈러"], "truncated": False, "candidates": [candidate, below],
                "untrusted_data": {"notice": "data", "subbrains": [
                    {"subbrain_id": "sb_c", "version": 2, "owner_display": "세포 C", "title": "단백질\x1b[2J 자기조립"}]}}
    service = fake_runtime[1]["service"] = ExplainService(envelope)

    argv = ["match-explain", "--token", PRO, "--query", "모듈러", "--host-subbrain-id", "sb_a", "--mode", "topic"]
    assert cli.main(argv) == 0
    out = capsys.readouterr().out
    assert "sb_c@v2" in out and "조립, 오류" in out and "below_tau" in out and "0.600" in out
    assert "세포 C (user_c)" in out and "단백질" in out and "\x1b" not in out
    assert service.calls[0][1:] == ("match_explain", {"query": "모듈러", "host_subbrain_id": "sb_a", "query_mode": "topic"})


def test_match_explain_bad_token_is_unauthorized(
    fake_runtime: tuple[FakeStore, dict[str, Any]], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENCANAL_TOKEN", raising=False)
    fake_runtime[1]["service"] = ExplainService({"ok": True})
    assert cli.main(["match-explain", "--token", "oc_bad", "--query", "q", "--host-subbrain-id", "s"]) == 1
    assert "UNAUTHORIZED" in capsys.readouterr().err
    assert cli.main(["match-explain", "--query", "q", "--host-subbrain-id", "s"]) == 1


# ---------------------------------------------------------------------------
# CLI against the real Store / crypto (skips while they are stubs)
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    paths = {"db": tmp_path / "data" / "oc.db", "key": tmp_path / "data" / "keys" / "master.key", "root": tmp_path}
    monkeypatch.setenv("OPENCANAL_DB", str(paths["db"]))
    monkeypatch.setenv("OPENCANAL_KEY_FILE", str(paths["key"]))
    monkeypatch.delenv("OPENCANAL_MASTER_KEY", raising=False)
    monkeypatch.delenv("OPENCANAL_TOKEN", raising=False)
    return paths


def _real_store_and_crypto(tmp: Path) -> None:
    from opencanal import crypto
    from opencanal.store import Store

    def crypto_ready() -> None:
        crypto.encrypt_backup(b"k" * 32, b"x")

    def store_ready() -> None:
        Store(":memory:", master_key=b"k" * 32).close()

    _require_real(crypto_ready, store_ready)


def test_cli_user_lifecycle_and_encrypted_backup(cli_env: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
    _real_store_and_crypto(cli_env["root"])
    from opencanal.store import Store

    assert cli.main(["init-db"]) == 0
    assert stat.S_IMODE(os.stat(cli_env["key"]).st_mode) == 0o600
    assert cli.main(["create-user", "--name", "고유한표시이름", "--tier", "free", "--user-id", "user_q"]) == 0
    out = capsys.readouterr().out
    token = next(line.split()[-1] for line in out.splitlines() if line.startswith("token:"))
    assert f"http://127.0.0.1:8765/mcp/{token}" in out
    assert cli.main(["create-user", "--name", "dup", "--tier", "free", "--user-id", "user_q"]) == 1

    assert cli.main(["rotate-token", "--user-id", "user_q"]) == 0
    new_token = next(line.split()[-1] for line in capsys.readouterr().out.splitlines() if line.startswith("token:"))
    assert cli.main(["set-tier", "--user-id", "user_q", "--tier", "pro"]) == 0
    assert cli.main(["rotate-token", "--user-id", "nobody"]) == 1

    key = cli_env["key"].read_bytes()
    store = Store(cli_env["db"], master_key=key)
    try:
        assert store.user_by_token(token) is None  # revoked
        assert store.user_by_token(new_token).tier is Tier.PRO
    finally:
        store.close()
    assert token.encode() not in cli_env["db"].read_bytes()  # only hashes stored

    out_dir = cli_env["root"] / "backups"
    assert cli.main(["backup", "--out", str(out_dir)]) == 0
    (backup,) = list(out_dir.glob("opencanal-*.db.enc"))
    assert stat.S_IMODE(os.stat(backup).st_mode) == 0o600
    assert "고유한표시이름".encode() not in backup.read_bytes()

    existing = cli_env["db"]
    assert cli.main(["restore", "--in", str(backup), "--db", str(existing)]) == 1
    restored = cli_env["root"] / "restored.db"
    assert cli.main(["restore", "--in", str(backup), "--db", str(restored)]) == 0
    store = Store(restored, master_key=key)
    try:
        user = store.get_user("user_q")
        assert user is not None and user.display_name == "고유한표시이름"
    finally:
        store.close()

    other_key = cli_env["root"] / "other.key"
    from opencanal import crypto

    crypto.load_or_create_master_key(other_key)
    target = cli_env["root"] / "r2.db"
    assert cli.main(["--key-file", str(other_key), "restore", "--in", str(backup), "--db", str(target)]) == 1
    assert not target.exists()


def test_backup_refuses_missing_db(cli_env: dict[str, Path], capsys: pytest.CaptureFixture[str]) -> None:
    _real_store_and_crypto(cli_env["root"])
    assert cli.main(["backup", "--out", str(cli_env["root"] / "b")]) == 1
    assert not cli_env["db"].exists()


# ---------------------------------------------------------------------------
# full stack (real Service) over HTTP and stdio — skips while Service is a stub
# ---------------------------------------------------------------------------


def _real_service_or_skip(db: Path, key_file: Path) -> tuple[str, str]:
    """Create a free and a pro user in a fresh DB; skip if Store/Service are not implemented yet."""
    from opencanal import crypto
    from opencanal.config import load_config
    from opencanal.service import Service
    from opencanal.store import Store

    db.parent.mkdir(parents=True, exist_ok=True)
    try:
        key = crypto.load_or_create_master_key(key_file)
        store = Store(db, master_key=key)
        try:
            Service(store, load_config())
            _, free_token = store.create_user("Free", Tier.FREE, user_id="user_free")
            _, pro_token = store.create_user("Pro", Tier.PRO, user_id="user_pro")
        finally:
            store.close()
    except NotImplementedError as exc:
        pytest.skip(f"Store/Service still a stub (NotImplementedError) — full-stack test waits for Builder ST/SV: {exc}")
    return free_token, pro_token


def test_full_stack_http_with_real_service(cli_env: dict[str, Path]) -> None:
    free_token, pro_token = _real_service_or_skip(cli_env["db"], cli_env["key"])
    from opencanal import crypto
    from opencanal.config import load_config
    from opencanal.service import Service
    from opencanal.store import Store

    def app_factory() -> Any:
        store = Store(cli_env["db"], master_key=crypto.load_or_create_master_key(cli_env["key"]))
        return create_app(Service(store, load_config()))

    with serve_in_thread(app_factory) as base:
        _, free_tools, mine = anyio.run(_http_session_roundtrip, f"{base}/mcp/{free_token}", "subbrain_list_mine", {})
        _, _, forbidden = anyio.run(
            _http_session_roundtrip, f"{base}/mcp/{free_token}", "match_explain", {"query": "q", "host_subbrain_id": "x"}
        )
        _, pro_tools, _ = anyio.run(_http_session_roundtrip, f"{base}/mcp/{pro_token}", "subbrain_list_mine", {})
        _, bogus_tools, bogus = anyio.run(_http_session_roundtrip, f"{base}/mcp/oc_bogus", "subbrain_list_mine", {})

    free_names = {t.name for t in free_tools.tools}
    assert "subbrain_list_mine" in free_names and not free_names & set(HIGHER_TIER_TOOLS)
    assert _envelope(mine)["ok"] is True
    assert _envelope(forbidden)["error"]["code"] == "TIER_FORBIDDEN"
    assert "match_explain" in {t.name for t in pro_tools.tools}
    assert bogus_tools.tools == [] and _envelope(bogus)["error"]["code"] == "UNAUTHORIZED"


def test_full_stack_stdio_subprocess(cli_env: dict[str, Path]) -> None:
    free_token, _ = _real_service_or_skip(cli_env["db"], cli_env["key"])
    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go(token: Optional[str]) -> tuple[Any, Any]:
        env = {k: v for k, v in os.environ.items() if k != "OPENCANAL_TOKEN"}
        if token is not None:
            env["OPENCANAL_TOKEN"] = token
        params = StdioServerParameters(command=sys.executable, args=["-m", "opencanal", "mcp-stdio"], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.list_tools(), await session.call_tool("subbrain_list_mine", {})

    tools, result = anyio.run(go, free_token)
    assert "subbrain_list_mine" in {t.name for t in tools.tools}
    assert _envelope(result)["ok"] is True
    no_tools, unauthorized = anyio.run(go, None)
    assert no_tools.tools == [] and _envelope(unauthorized)["error"]["code"] == "UNAUTHORIZED"
