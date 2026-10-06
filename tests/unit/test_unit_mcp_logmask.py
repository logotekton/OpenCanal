"""TokenMaskFilter on every kind of log record (TIER-2): message, args, tracebacks, coloured variants.

The access-log path is covered end to end in test_unit_mcp.py and test_unit_cli_serve.py; these tests
pin the record-level behaviour that those rely on.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from opencanal.mcp_server import (
    TokenMaskFilter,
    install_token_log_filter,
    mask_request_target,
    mask_tokens_in_text,
)

TOKEN = "oc_" + "Zq9-_xY" * 6  # shape of crypto.generate_api_token(): "oc_" + urlsafe
MASKED = TOKEN[:6] + "…"


def _record(name: str, msg: object, args: object = None, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(name, logging.WARNING, __file__, 1, msg, args, None)
    record.__dict__.update(extra)
    return record


def _render(record: logging.LogRecord) -> str:
    assert TokenMaskFilter().filter(record) is True
    return logging.Formatter("%(message)s").format(record)


@pytest.mark.parametrize(
    "target",
    [
        f"/mcp/{TOKEN}", f"/mcp//{TOKEN}", f"/MCP/{TOKEN}", f"/x/{TOKEN}", f"/{TOKEN}", f"/a/b/{TOKEN}/c",
        f"/mcp/%20{TOKEN}%20", f"/x?t={TOKEN}", f"/x?{TOKEN}", f"/x?a=1&token={TOKEN}",
        f"http://127.0.0.1:8765/x/{TOKEN}", f"/mcp{TOKEN}", f"/x/{TOKEN[3:]}",
    ],
)
def test_request_targets_never_keep_a_full_token(target: str) -> None:
    masked = mask_tokens_in_text(mask_request_target(target))
    assert TOKEN not in masked and TOKEN[3:] not in masked
    assert mask_tokens_in_text(mask_request_target(masked)) == masked


def test_harmless_paths_are_kept() -> None:
    assert mask_request_target("/health") == "/health"
    assert mask_request_target("/mcp") == "/mcp"
    assert mask_request_target("*") == "*"
    assert mask_tokens_in_text("Invalid Host header: evil.example:8765") == "Invalid Host header: evil.example:8765"


def test_token_in_free_text_and_tracebacks() -> None:
    try:
        raise RuntimeError(f"illegal request line: bytearray(b'POST /x/{TOKEN} HTTP/1.1')")
    except RuntimeError:
        record = logging.LogRecord("uvicorn.error", logging.WARNING, __file__, 1, "Invalid HTTP request", None, None)
        import sys

        record.exc_info = sys.exc_info()
    line = _render(record)
    assert "Traceback" in line and "RuntimeError" in line
    assert TOKEN not in line and TOKEN[3:] not in line
    assert record.exc_info is None  # formatters (rich included) cannot re-render the raw exception


@pytest.mark.parametrize(
    ("msg", "args"),
    [
        ("bad line %r", (f"POST /x/{TOKEN} HTTP/1.1".encode(),)),
        ("scope %s", ({"path": f"/x/{TOKEN}", "raw_path": f"/x/{TOKEN}".encode()},)),
        ("%(path)s", ({"path": f"/x/{TOKEN}"},)),  # as logger.info("%(path)s", {...}) passes it
        (f"f-string with {TOKEN}", None),
        (RuntimeError(f"token {TOKEN}"), None),
    ],
)
def test_non_access_records_are_rendered_then_masked(msg: object, args: object) -> None:
    line = _render(_record("mcp.server.streamable_http", msg, args))
    assert TOKEN not in line and MASKED in line


def test_uvicorn_colour_message_is_masked_too() -> None:
    from uvicorn.logging import DefaultFormatter

    record = _record(
        "uvicorn.error", "Running on %s", (f"http://h/x/{TOKEN}",), color_message="Running on \x1b[1m%s\x1b[0m"
    )
    assert TokenMaskFilter().filter(record) is True
    line = DefaultFormatter("%(levelprefix)s %(message)s", use_colors=True).format(record)
    assert TOKEN not in line and MASKED in line


def test_access_record_keeps_its_five_tuple() -> None:
    from uvicorn.logging import AccessFormatter

    record = _record("uvicorn.access", '%s - "%s %s HTTP/%s" %d', ("127.0.0.1:1", "POST", f"/x/{TOKEN}?t={TOKEN}", "1.1", 404))
    assert TokenMaskFilter().filter(record) is True
    assert TokenMaskFilter().filter(record) is True  # logger filter + handler filter: second pass is a no-op
    assert isinstance(record.args, tuple) and len(record.args) == 5 and record.args[4] == 404
    line = AccessFormatter(use_colors=True).format(record)
    assert TOKEN not in line and f"/x/{MASKED}?t={MASKED}" in line


def test_unformattable_record_fails_closed_without_raising() -> None:
    record = _record("mcp", f"%d {TOKEN}", ("not a number",))
    line = _render(record)
    assert TOKEN not in line and "dropped" in line


@pytest.fixture
def root_capture() -> Iterator[list[str]]:
    lines: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(self.format(record))

    handler = Capture(level=logging.DEBUG)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        yield lines
    finally:
        root.removeHandler(handler)


def test_install_covers_records_propagated_from_any_logger(root_capture: list[str]) -> None:
    install_token_log_filter()  # as cmd_serve does once uvicorn has configured its handlers
    third_party = logging.getLogger("mcp.server.transport_security.test_only")
    third_party.warning("Invalid Host header for %s", f"/mcp//{TOKEN}")
    third_party.warning(f"rejected {TOKEN}")
    assert len(root_capture) == 2
    assert all(TOKEN not in line and MASKED in line for line in root_capture)
    assert any(isinstance(f, TokenMaskFilter) for f in logging.lastResort.filters)


def test_clean_records_are_left_untouched() -> None:
    """The filter also sits on shared root handlers: records without a token keep msg, args and exc_info."""
    import sys

    try:
        raise ValueError("no secret here")
    except ValueError:
        exc_info = sys.exc_info()
    record = _record("opencanal.service", "dispatch %s took %d ms", ("subbrain_list_mine", 3))
    record.exc_info = exc_info
    assert TokenMaskFilter().filter(record) is True
    assert record.msg == "dispatch %s took %d ms" and record.args == ("subbrain_list_mine", 3)
    assert record.exc_info is exc_info
