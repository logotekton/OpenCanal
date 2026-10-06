"""NEVER-06, NEVER-07, NEVER-12 over real MCP streamable HTTP (/mcp/{token}).

A uvicorn server runs create_app(service) on a free 127.0.0.1 port in a background thread. The server's
Store/Service are built inside that thread against a file DB (as `opencanal serve` would); users are created
beforehand from the test thread. The official MCP client (streamable HTTP + ClientSession) talks to it.
pytest-timeout is not a dependency, so every wait below has its own timeout.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

import pytest

from opencanal.config import load_config
from opencanal.models import Tier

from .conftest import HIGHER_TIER_TOOLS, Q01

pytestmark = pytest.mark.timeout(120)

STARTUP_TIMEOUT = 30.0
CLIENT_TIMEOUT = 30.0
SHUTDOWN_TIMEOUT = 15.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def mcp_server(tmp_path_factory: pytest.TempPathFactory):
    import uvicorn

    from opencanal import crypto
    from opencanal.app import create_app
    from opencanal.service import Service
    from opencanal.store import Store

    saved_env = os.environ.pop("OPENCANAL_MASTER_KEY", None)
    base: Path = tmp_path_factory.mktemp("mcp_http")
    master_key = crypto.load_or_create_master_key(base / "master.key")
    db_path = base / "opencanal.db"

    setup_store = Store(db_path, master_key=master_key)
    _, free_token = setup_store.create_user("Haram Kim", Tier.FREE, user_id="user_a")
    _, pro_token = setup_store.create_user("Pro Kim", Tier.PRO, user_id="user_pro")
    _, revoked_token = setup_store.create_user("Old Kim", Tier.FREE, user_id="user_old")
    setup_store.rotate_token("user_old")
    setup_store.close()

    port = _free_port()
    holder: dict[str, Any] = {}
    ready = threading.Event()

    def run() -> None:
        store = None
        try:
            store = Store(db_path, master_key=master_key)
            service = Service(store, load_config())
            app = create_app(service)
            config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
            holder["server"] = uvicorn.Server(config)
        except BaseException as exc:  # surfaced to the test thread
            holder["error"] = exc
            ready.set()
            return
        ready.set()
        try:
            holder["server"].run()
        except BaseException as exc:
            holder["error"] = exc
        finally:
            try:
                store.close()
            except Exception:
                pass

    thread = threading.Thread(target=run, name="opencanal-mcp-http", daemon=True)
    thread.start()
    try:
        assert ready.wait(STARTUP_TIMEOUT), "server setup did not finish"
        if "error" in holder:
            raise holder["error"]
        server = holder["server"]
        deadline = time.monotonic() + STARTUP_TIMEOUT
        while not server.started:
            if "error" in holder:
                raise holder["error"]
            assert thread.is_alive(), "uvicorn thread exited before startup"
            assert time.monotonic() < deadline, "uvicorn did not start in time"
            time.sleep(0.05)

        yield {
            "base": f"http://127.0.0.1:{port}",
            "free": free_token,
            "pro": pro_token,
            "revoked": revoked_token,
        }
    finally:
        server = holder.get("server")
        if server is not None:
            server.should_exit = True
        thread.join(SHUTDOWN_TIMEOUT)
        if saved_env is not None:
            os.environ["OPENCANAL_MASTER_KEY"] = saved_env
    assert not thread.is_alive(), "uvicorn thread did not shut down"


def _mcp(url: str, body: Callable[[Any], Awaitable[Any]]) -> Any:
    """Open an MCP session against `url`, run `body(session)`, close cleanly — all under a timeout."""
    from mcp import ClientSession

    try:
        from mcp.client.streamable_http import streamable_http_client as _client
    except ImportError:  # older SDK name
        from mcp.client.streamable_http import streamablehttp_client as _client

    async def go() -> Any:
        async with _client(url) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await body(session)

    return asyncio.run(asyncio.wait_for(go(), CLIENT_TIMEOUT))


def _envelope(result: Any) -> dict[str, Any]:
    """tools/call result contract: exactly one TextContent carrying the JSON envelope."""
    assert len(result.content) == 1, result
    item = result.content[0]
    assert item.type == "text", result
    env = json.loads(item.text)
    assert isinstance(env, dict) and isinstance(env.get("ok"), bool), env
    return env


def _url(server: dict, token: str) -> str:
    return f"{server['base']}/mcp/{token}"


def test_never_06_http_free_token_lists_only_free_tools(mcp_server):
    async def body(session):
        return await session.list_tools()

    result = _mcp(_url(mcp_server, mcp_server["free"]), body)
    names = sorted(t.name for t in result.tools)
    assert names == sorted(load_config().tools_for_tier(Tier.FREE))
    serialized = result.model_dump_json()
    for hidden in HIGHER_TIER_TOOLS:
        assert hidden not in serialized, f"{hidden} visible to a Free token"


def test_never_06_http_pro_token_lists_pro_tools(mcp_server):
    async def body(session):
        return await session.list_tools()

    result = _mcp(_url(mcp_server, mcp_server["pro"]), body)
    assert sorted(t.name for t in result.tools) == sorted(load_config().tools_for_tier(Tier.PRO))
    assert "canal_synthesize" not in result.model_dump_json()


def test_never_07_http_free_direct_call_is_tier_forbidden(mcp_server):
    calls = {
        "match_explain": {"query": Q01, "host_subbrain_id": "sb_anything"},
        "deltabrain_export": {"deltabrain_id": "db_anything"},
        "canal_synthesize": {},
    }

    async def body(session):
        return {name: await session.call_tool(name, args) for name, args in calls.items()}

    results = _mcp(_url(mcp_server, mcp_server["free"]), body)
    for name, result in results.items():
        env = _envelope(result)
        assert env["ok"] is False and env["error"]["code"] == "TIER_FORBIDDEN", (name, env)


def test_mcp_http_tools_call_returns_single_text_envelope(mcp_server):
    async def body(session):
        return await session.call_tool("subbrain_list_mine", {})

    env = _envelope(_mcp(_url(mcp_server, mcp_server["free"]), body))
    assert env["ok"] is True


@pytest.mark.parametrize("which", ["bogus", "revoked"])
def test_never_12_http_bad_token_lists_nothing_and_calls_are_unauthorized(mcp_server, which):
    token = "oc_" + "Z" * 43 if which == "bogus" else mcp_server["revoked"]

    async def body(session):
        listed = await session.list_tools()
        calls = [
            await session.call_tool("subbrain_list_mine", {}),
            await session.call_tool("match_explain", {"query": Q01, "host_subbrain_id": "sb_x"}),
            await session.call_tool("subbrain_search", {"query": Q01}),
        ]
        return listed, calls

    listed, calls = _mcp(_url(mcp_server, token), body)
    assert listed.tools == []
    for result in calls:
        env = _envelope(result)
        assert env["ok"] is False and env["error"]["code"] == "UNAUTHORIZED", env
