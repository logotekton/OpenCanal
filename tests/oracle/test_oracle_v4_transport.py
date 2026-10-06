"""NEVER-12 over stdio and MUST-E1 through the CLI (ORACLE §5.6, §5.8; TASK-001 §4 MCP/CLI).

stdio: the official MCP stdio client launches `opencanal mcp-stdio` (token from OPENCANAL_TOKEN) against a DB and
key file in tmp. A missing, empty, whitespace-only, unknown or revoked token must give an empty tools/list and
UNAUTHORIZED for every call — never a default user.

CLI: `opencanal backup` writes an encrypted file (mode 0600) without plaintext labels, summaries or tokens;
`opencanal restore` brings the same data back into a new DB file and refuses a target that already exists — and
a target whose SQLite sidecars (-wal, -shm) already exist, since SQLite would replay a stale WAL into the
restored DB and it would no longer be "the same data".
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import pytest

from opencanal.config import load_config
from opencanal.models import Tier

from .conftest import (
    HIGHER_TIER_TOOLS,
    INJECTION_FRAGMENT,
    Q01,
    REPO_ROOT,
    World,
    assert_ok,
    dumps,
    load_brain,
)
from ._v4 import cli_env, opencanal_bin

pytestmark = pytest.mark.timeout(180)

CLIENT_TIMEOUT = 60.0
CLI_TIMEOUT = 120.0


@pytest.fixture(autouse=True)
def _no_env_master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCANAL_MASTER_KEY", raising=False)


# ---------------------------------------------------------------------------
# NEVER-12 over stdio
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def stdio_db(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    saved = os.environ.pop("OPENCANAL_MASTER_KEY", None)
    try:
        base: Path = tmp_path_factory.mktemp("stdio")
        db = base / "opencanal.db"
        w = World(base, db_path=db)  # master key at base/master.key
        w.ensure_fixture_users()
        w.seed(("A", "B"))
        old_token = w.tokens["user_b"]
        new_token = w.store.rotate_token("user_b")
        w.store.close()
        return {
            "base": base,
            "db": db,
            "key": base / "master.key",
            "valid": w.tokens["user_a"],
            "revoked": old_token,
            "rotated": new_token,
            "a_sid": w.sid("A"),
        }
    finally:
        if saved is not None:
            os.environ["OPENCANAL_MASTER_KEY"] = saved


def _stdio(info: dict[str, Any], token: Optional[str], body: Callable[[Any], Awaitable[Any]]) -> Any:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    env = {
        "OPENCANAL_DB": str(info["db"]),
        "OPENCANAL_KEY_FILE": str(info["key"]),
        "OPENCANAL_CONFIG_DIR": str(REPO_ROOT / "config"),
    }
    if token is not None:
        env["OPENCANAL_TOKEN"] = token
    params = StdioServerParameters(command=str(opencanal_bin()), args=["mcp-stdio"], env=env, cwd=str(info["base"]))

    async def go() -> Any:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await body(session)

    return asyncio.run(asyncio.wait_for(go(), CLIENT_TIMEOUT))


def _envelope(result: Any) -> dict[str, Any]:
    assert len(result.content) == 1, result
    item = result.content[0]
    assert item.type == "text", result
    env = json.loads(item.text)
    assert isinstance(env, dict) and isinstance(env.get("ok"), bool), env
    return env


CALLS = [
    ("subbrain_list_mine", {}),
    ("subbrain_search", {"query": Q01}),
    ("subbrain_get", {"subbrain_id": "<A>"}),
    ("canal_open", {"query": Q01, "host_subbrain_id": "<A>"}),
    ("subbrain_import", {"document": load_brain("D")["document"]}),
    ("match_explain", {"query": Q01, "host_subbrain_id": "<A>"}),
    ("canal_synthesize", {}),
]


def _calls(info: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for name, args in CALLS:
        out.append((name, {k: (info["a_sid"] if v == "<A>" else v) for k, v in args.items()}))
    return out


@pytest.mark.parametrize("which", ["unset", "empty", "whitespace", "bogus", "revoked"])
def test_never_12_v4_stdio_bad_token_lists_nothing_and_every_call_is_unauthorized(stdio_db, which):
    token = {
        "unset": None,
        "empty": "",
        "whitespace": "   \t ",
        "bogus": "oc_" + "Z" * 43,
        "revoked": stdio_db["revoked"],
    }[which]
    calls = _calls(stdio_db)

    async def body(session):
        listed = await session.list_tools()
        results = [(name, await session.call_tool(name, args)) for name, args in calls]
        return listed, results

    listed, results = _stdio(stdio_db, token, body)
    assert listed.tools == [], f"{which}: tools/list must be empty, got {[t.name for t in listed.tools]}"
    for name, result in results:
        env = _envelope(result)
        assert env["ok"] is False and env["error"]["code"] == "UNAUTHORIZED", (which, name, env)
        assert "untrusted_data" not in env

    # No default user: the unauthenticated import landed on no account.
    from opencanal import crypto
    from opencanal.store import Store

    store = Store(stdio_db["db"], master_key=crypto.load_or_create_master_key(stdio_db["key"]))
    try:
        for uid in ("user_a", "user_b", "user_c", "user_d", "user_e", "user_x"):
            titles = [s.title for s in store.list_subbrains_for_owner(uid)]
            assert load_brain("D")["document"]["title"] not in titles, f"{which}: import landed on {uid}"
    finally:
        store.close()


def test_never_12_v4_stdio_valid_token_positive_control(stdio_db):
    async def body(session):
        listed = await session.list_tools()
        mine = await session.call_tool("subbrain_list_mine", {})
        hidden = await session.call_tool("match_explain", {"query": Q01, "host_subbrain_id": stdio_db["a_sid"]})
        return listed, mine, hidden

    listed, mine, hidden = _stdio(stdio_db, stdio_db["valid"], body)
    assert sorted(t.name for t in listed.tools) == sorted(load_config().tools_for_tier(Tier.FREE))
    for name in HIGHER_TIER_TOOLS:
        assert name not in listed.model_dump_json()
    env = _envelope(mine)
    assert env["ok"] is True and stdio_db["a_sid"] in dumps(env)
    assert _envelope(hidden)["error"]["code"] == "TIER_FORBIDDEN"


def test_never_12_v4_stdio_rotated_token_works(stdio_db):
    async def body(session):
        return await session.call_tool("subbrain_list_mine", {})

    assert _envelope(_stdio(stdio_db, stdio_db["rotated"], body))["ok"] is True


@pytest.mark.parametrize("token", ["", "   ", "\t\n", None])
def test_never_12_v4_service_rejects_blank_tokens(world: World, token):
    assert world.service.authenticate(token) is None
    assert world.service.tools_for(None) == []


# ---------------------------------------------------------------------------
# MUST-E1 through the CLI: backup / restore
# ---------------------------------------------------------------------------


def _run(args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(opencanal_bin()), *args], env=env, cwd=str(cwd), capture_output=True, text=True, timeout=CLI_TIMEOUT
    )


def _views(world_like: World) -> dict[str, Any]:
    """What each user sees through the product surface (compared before backup and after restore)."""
    out: dict[str, Any] = {}
    for uid in ("user_a", "user_b", "user_c"):
        out[f"{uid}:mine"] = world_like.call(uid, "subbrain_list_mine")
        out[f"{uid}:deltabrains"] = world_like.call(uid, "deltabrain_list")
    out["a:get_A"] = world_like.call("user_a", "subbrain_get", subbrain_id=world_like.sid("A"))
    out["b:get_P"] = world_like.call("user_b", "subbrain_get", subbrain_id=world_like.sid("P"))
    out["c:get_db"] = world_like.call("user_c", "deltabrain_get", deltabrain_id=world_like.db_id)
    return out


@pytest.fixture
def cli_world(tmp_path: Path) -> dict[str, Any]:
    data = tmp_path / "data"
    db = data / "opencanal.db"
    data.mkdir()
    w = World(data, db_path=db)  # master key at data/master.key
    w.ensure_fixture_users()
    w.seed()
    _, db_id, _ = w.canal_with_deltabrain()
    w.db_id = db_id
    assert_ok(w.make_private("C"))  # include a masked contributor in the data set
    views = _views(w)
    tokens = dict(w.tokens)
    sb = dict(w.sb)
    w.store.close()
    key = data / "master.key"
    return {"tmp": tmp_path, "db": db, "key": key, "env": cli_env(db, key), "views": views, "tokens": tokens, "sb": sb, "db_id": db_id}


def _restore(cw: dict[str, Any], backup: Path, target: Path) -> subprocess.CompletedProcess:
    """`opencanal restore --db TARGET --in BACKUP` (the target is named explicitly, never taken from the default)."""
    return _run(
        ["restore", "--db", str(target), "--key-file", str(cw["key"]), "--in", str(backup)],
        cli_env(target, cw["key"]),
        cw["tmp"],
    )


def _assert_clean_restore_works(cw: dict[str, Any], backup: Path) -> None:
    """Control for the refusal tests: the very same command succeeds on a clean target."""
    clean = cw["tmp"] / "control" / "opencanal.db"
    clean.parent.mkdir(exist_ok=True)
    proc = _restore(cw, backup, clean)
    assert proc.returncode == 0 and clean.exists(), f"control restore failed: {proc.stdout}\n{proc.stderr}"


def _backup(cw: dict[str, Any]) -> Path:
    out_dir = cw["tmp"] / "backups"
    proc = _run(["backup", "--out", str(out_dir)], cw["env"], cw["tmp"])
    assert proc.returncode == 0, f"backup failed: {proc.stdout}\n{proc.stderr}"
    files = sorted(p for p in out_dir.rglob("*") if p.is_file())
    assert len(files) == 1, f"expected one backup file in {out_dir}, got {files}"
    for text in (proc.stdout, proc.stderr):
        for token in cw["tokens"].values():
            assert token not in text, "the backup command printed a token"
    return files[0]


PLAINTEXTS = [
    load_brain("A")["document"]["title"],
    load_brain("P")["document"]["title"],
    "현장 조립 오류",
    "형태 상보성",
    "잘못 놓을 수 없는 블록 모양",
    load_brain("C")["document"]["nodes"][1]["summary"],
    INJECTION_FRAGMENT,
    "비대칭 접합 키 설계",
]


def test_must_e1_v4_cli_backup_is_encrypted_and_0600(cli_world):
    backup = _backup(cli_world)
    assert stat.S_IMODE(os.stat(backup).st_mode) == 0o600, oct(os.stat(backup).st_mode)
    blob = backup.read_bytes()
    assert blob and not blob.startswith(b"SQLite format 3"), "the backup is a raw SQLite file"
    assert b"SQLite format 3" not in blob
    for text in PLAINTEXTS:
        assert text.encode("utf-8") not in blob, f"backup contains plaintext {text!r}"
    for uid, token in cli_world["tokens"].items():
        assert token.encode() not in blob, f"backup contains the plaintext token of {uid}"
        assert token.split("_", 1)[-1].encode() not in blob
    assert stat.S_IMODE(os.stat(cli_world["key"]).st_mode) == 0o600, "key file stays 0600"


def test_must_e1_v4_cli_restore_round_trip(cli_world):
    from opencanal import crypto
    from opencanal.service import Service
    from opencanal.store import Store

    backup = _backup(cli_world)
    target = cli_world["tmp"] / "restored" / "opencanal.db"
    target.parent.mkdir()
    proc = _restore(cli_world, backup, target)
    assert proc.returncode == 0, f"restore failed: {proc.stdout}\n{proc.stderr}"
    assert target.exists()

    key = crypto.load_or_create_master_key(cli_world["key"])
    store = Store(target, master_key=key)
    try:
        w = World.__new__(World)  # same call helpers, restored store
        w.cfg = load_config()
        w.store = store
        w.service = Service(store, w.cfg)
        w.tokens = cli_world["tokens"]
        w.sb = cli_world["sb"]
        w.db_id = cli_world["db_id"]
        w.master_key = key
        restored = _views(w)
    finally:
        store.close()
    for name, before in cli_world["views"].items():
        assert dumps(restored[name]) == dumps(before), f"{name} differs after restore:\n{dumps(before)[:800]}\n{dumps(restored[name])[:800]}"


def test_must_e1_v4_cli_restore_refuses_existing_target(cli_world):
    backup = _backup(cli_world)
    target = cli_world["tmp"] / "exists.db"
    target.write_bytes(b"keep me")
    _assert_clean_restore_works(cli_world, backup)
    proc = _restore(cli_world, backup, target)
    assert proc.returncode != 0, "restore onto an existing file must fail"
    assert target.read_bytes() == b"keep me"


@pytest.mark.parametrize("sidecar", ["-wal", "-shm"])
def test_must_e1_v4_cli_restore_refuses_existing_sqlite_sidecar(cli_world, sidecar):
    backup = _backup(cli_world)
    target = cli_world["tmp"] / "fresh" / "opencanal.db"
    target.parent.mkdir()
    side = Path(str(target) + sidecar)
    side.write_bytes(b"stale sidecar from an older database")
    _assert_clean_restore_works(cli_world, backup)
    proc = _restore(cli_world, backup, target)
    assert proc.returncode != 0, f"restore next to an existing {sidecar} file must fail"
    assert not target.exists(), "no DB file may be written next to a stale sidecar"
    assert side.read_bytes() == b"stale sidecar from an older database", "the sidecar is not touched (no delete)"


def test_must_e1_v4_cli_init_db_creates_key_file_0600(tmp_path: Path):
    data = tmp_path / "data"
    db, key = data / "opencanal.db", data / "keys" / "master.key"
    proc = _run(["init-db", "--db", str(db), "--key-file", str(key)], cli_env(db, key), tmp_path)
    assert proc.returncode == 0, f"init-db failed: {proc.stdout}\n{proc.stderr}"
    assert key.exists() and db.exists()
    assert stat.S_IMODE(os.stat(key).st_mode) == 0o600, oct(os.stat(key).st_mode)
    assert len(key.read_bytes()) >= 32
