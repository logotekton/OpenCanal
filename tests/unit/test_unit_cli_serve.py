"""The real `python -m opencanal serve` process (TIER-2, CRY-1 root cause).

- Every line it writes (uvicorn access/error logs, mcp and opencanal loggers) masks MCP tokens, also
  when a client puts the token in a mistyped URL that only gets a 404.
- SIGTERM shuts it down through Store.close(), so no <db>-wal/-shm is left for a later restore to replay.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from opencanal import crypto
from opencanal.models import Tier
from opencanal.store import Store

SRC_DIR = Path(__file__).resolve().parents[2] / "src"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_health(base: str, proc: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"serve exited early with {proc.returncode}")
        try:
            if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    raise RuntimeError("serve did not become healthy")


@pytest.mark.skipif(not hasattr(signal, "SIGTERM") or os.name != "posix", reason="POSIX signals")
def test_serve_masks_tokens_in_all_log_lines_and_closes_db_on_sigterm(tmp_path: Path) -> None:
    key_file = tmp_path / "keys" / "master.key"
    key = crypto.load_or_create_master_key(key_file)
    db = tmp_path / "oc.db"
    store = Store(db, master_key=key)
    try:
        _, token = store.create_user("A", Tier.PRO, user_id="user_a")
    finally:
        store.close()

    env = {k: v for k, v in os.environ.items() if not k.startswith("OPENCANAL_")}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(SRC_DIR), env.get("PYTHONPATH")]))
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    log_path = tmp_path / "serve.log"
    argv = [sys.executable, "-m", "opencanal", "serve", "--db", str(db), "--key-file", str(key_file),
            "--port", str(port), "--log-level", "debug"]
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    headers = {"Accept": "application/json, text/event-stream"}
    mistyped = [f"/mcp//{token}", f"/x/{token}", f"/{token}", f"/MCP/{token}", f"/mcp/{token}/extra",
                f"/x?t={token}", f"/mcp{token}"]

    with log_path.open("wb") as out:
        proc = subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT, env=env, cwd=tmp_path)
        try:
            _wait_for_health(base, proc)
            ok = httpx.post(f"{base}/mcp/{token}", json=body, headers=headers, timeout=10)
            assert ok.status_code == 200 and ok.json()["result"]["tools"]  # the token is live
            for path in mistyped:
                assert httpx.post(base + path, json=body, headers=headers, timeout=10).status_code == 404
            evil = httpx.post(f"{base}/mcp/{token}", json=body, headers={**headers, "Host": "evil.example"}, timeout=10)
            assert evil.status_code in (400, 421)
            with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:  # malformed request line
                raw.sendall(f"POST /x/{token} HTTP/1.1 junk\r\nHost: 127.0.0.1\r\n\r\n".encode())
                raw.recv(1024)
            proc.send_signal(signal.SIGTERM)
            returncode = proc.wait(timeout=20)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    log = log_path.read_text("utf-8", errors="replace")
    assert token not in log and token[3:] not in log
    assert log.count(token[:6] + "…") >= len(mistyped) + 1  # the requests were logged, masked
    assert returncode == 128 + signal.SIGTERM
    assert not Path(f"{db}-wal").exists() and not Path(f"{db}-shm").exists()
