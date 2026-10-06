"""ASGI app: FastAPI with the MCP endpoint mounted at /mcp/{token} and GET /health.

Owner: Builder MCP.
"""

from __future__ import annotations

from typing import Any

from .service import Service


def create_app(service: Service) -> Any:
    raise NotImplementedError
