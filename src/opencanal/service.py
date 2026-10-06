"""Transport-independent tool layer: tier gating + dispatch (ORACLE §5.6). MCP and tests both call this.

Owner: Builder SV.

Envelope: success -> {"ok": True, ...}; failure -> {"ok": False, "error": {"code": ErrorCode, "message": str, ...}}.
Other users' content in any response must live under the key "untrusted_data" (NEVER-09).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Optional

from .config import AppConfig
from .models import ToolSpec, User
from .store import Store


class Service:
    def __init__(self, store: Store, config: AppConfig, *, clock: Optional[Callable[[], datetime]] = None) -> None:
        raise NotImplementedError

    def authenticate(self, token: Optional[str]) -> Optional[User]:
        """None for missing/unknown/revoked tokens (fail closed, NEVER-12)."""
        raise NotImplementedError

    def tools_for(self, user: Optional[User]) -> list[ToolSpec]:
        """Exactly the tools allowed for the user's tier (config/tiers.json). [] when user is None."""
        raise NotImplementedError

    def dispatch(self, user: Optional[User], tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Check auth (UNAUTHORIZED), tool known (UNKNOWN_TOOL), tier (TIER_FORBIDDEN) BEFORE any side effect,
        validate args (INVALID_ARGUMENT), then run the handler. Never raises; always returns an envelope."""
        raise NotImplementedError
