"""MCP transport (FastMCP, streamable HTTP at /mcp/{token}, and stdio). Delegates to Service.

Owner: Builder MCP. tools/list must come from Service.tools_for(user); tools/call from Service.dispatch.
"""

from __future__ import annotations

from typing import Any

from .service import Service


def build_mcp(service: Service, *, stdio_token: str | None = None) -> Any:
    """Return a configured FastMCP (subclass) instance bound to `service`."""
    raise NotImplementedError
