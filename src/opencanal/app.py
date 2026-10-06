"""ASGI app: FastAPI with the MCP endpoint mounted at /mcp/{token} and GET /health.

Owner: Builder MCP.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from .mcp_server import build_mcp, install_token_log_filter
from .service import Service

MCP_MOUNT_PATH = "/mcp"


def create_app(service: Service) -> Any:
    """FastAPI app. MCP endpoint: http://host:port/mcp/<token> (stateless streamable HTTP).

    Builds a fresh FastMCP per app: the SDK's session manager can be run only once per instance,
    and it must run inside this app's lifespan because Starlette does not run a mounted app's lifespan.
    """
    install_token_log_filter()  # logger-level filters survive uvicorn's later dictConfig
    mcp = build_mcp(service)
    mcp_app = mcp.streamable_http_app()  # creates mcp.session_manager

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = FastAPI(
        title="opencanal",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    app.mount(MCP_MOUNT_PATH, mcp_app, name="mcp")
    app.state.mcp = mcp
    app.state.service = service
    return app
