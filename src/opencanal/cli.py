"""`opencanal` command line (TASK-001 §4).

Owner: Builder MCP.
Commands: init-db, create-user, rotate-token, set-tier, seed-fixtures, serve, mcp-stdio,
match-explain, backup, restore.

Paths: --db (env OPENCANAL_DB, default data/opencanal.db), --key-file (env OPENCANAL_KEY_FILE,
default data/keys/master.key), --config-dir (env OPENCANAL_CONFIG_DIR, default config/). Relative
defaults resolve against the repository root, so the same DB is used from any working directory.
Plaintext MCP tokens are printed once, when created; only their hashes are stored.
Directories created for data, keys and backups are 0700; DB, key and backup files are 0600 (MUST-E1, MUST-E3).
backup writes no plaintext copy of the DB to disk; restore's plaintext temp file is 0600 and is removed on success
and on failure (MUST-E3 v.6).
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import secrets
import signal
import sqlite3
import sys
import threading
import unicodedata
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from . import crypto, matching
from .config import DEFAULT_DATA_DIR, REPO_ROOT, load_config
from .models import MatchCandidate, OpenCanalError, QueryMode, Tier, User, Visibility
from .service import Service
from .store import Store

DEFAULT_DB = DEFAULT_DATA_DIR / "opencanal.db"
DEFAULT_KEY_FILE = DEFAULT_DATA_DIR / "keys" / "master.key"
DEFAULT_FIXTURES_DIR = REPO_ROOT / "fixtures" / "brains"
DEFAULT_BACKUP_DIR = REPO_ROOT / "backups"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
# SQLite treats these files next to a DB as part of it (WAL mode is the Store default).
SQLITE_SIDECARS = ("-wal", "-shm", "-journal")


class CliError(Exception):
    """User-facing failure: printed as one line on stderr, exit code 1."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def mcp_url(token: str, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    shown_host = f"[{host}]" if ":" in host else host
    return f"http://{shown_host}:{port}/mcp/{token}"


def _db_path(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "db", None) or os.environ.get("OPENCANAL_DB") or DEFAULT_DB)


def _key_path(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "key_file", None) or os.environ.get("OPENCANAL_KEY_FILE") or DEFAULT_KEY_FILE)


def _load_key(args: argparse.Namespace, *, create: bool = True) -> bytes:
    path = _key_path(args)
    if not create and not os.environ.get("OPENCANAL_MASTER_KEY") and not path.exists():
        raise CliError(f"마스터 키 파일이 없습니다: {path} (백업을 만든 키가 필요합니다)")
    return crypto.load_or_create_master_key(path)


@contextmanager
def _open_store(args: argparse.Namespace, *, must_exist: bool = False) -> Iterator[tuple[Store, bytes]]:
    db = _db_path(args)
    if str(db) != ":memory:":
        if must_exist and not db.exists():
            raise CliError(f"DB가 없습니다: {db} (먼저 `opencanal init-db`)")
        crypto.make_private_dirs(db.parent)  # 0700 for what we create (MUST-E3); Store pins the DB files to 0600
    key = _load_key(args)
    store = Store(db, master_key=key)
    try:
        yield store, key
    finally:
        store.close()


def _service(args: argparse.Namespace, store: Store) -> Service:
    return Service(store, load_config(getattr(args, "config_dir", None)))


def _require_user(store: Store, user_id: str) -> User:
    user = store.get_user(user_id)
    if user is None:
        raise CliError(f"사용자가 없습니다: {user_id}")
    return user


def _pick(envelope: dict[str, Any], key: str) -> Any:
    """Value of `key` at the top level of an envelope, else in a directly nested object."""
    if key in envelope:
        return envelope[key]
    for value in envelope.values():
        if isinstance(value, dict) and key in value:
            return value[key]
    return None


def _error_text(envelope: dict[str, Any]) -> str:
    error = envelope.get("error") or {}
    return f"{error.get('code', 'ERROR')}: {error.get('message', '')}".strip()


def _clean_cell(value: Any) -> str:
    """Printable one-line cell. Strips control/format chars: cells may hold other users' text."""
    if value is None:
        return ""
    if isinstance(value, float):
        text = f"{value:.3f}"
    elif isinstance(value, (list, tuple)):
        text = ", ".join(str(v) for v in value)
    else:
        text = str(value)
    return "".join(" " if unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") else ch for ch in text)


def _width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * (width - _width(text))


def format_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    cells = [[_clean_cell(c) for c in row] for row in rows]
    widths = [_width(h) for h in headers]
    for row in cells:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _width(cell))
    lines = ["  ".join(_pad(h, widths[i]) for i, h in enumerate(headers)).rstrip()]
    lines.append("  ".join("-" * w for w in widths))
    lines.extend("  ".join(_pad(c, widths[i]) for i, c in enumerate(row)).rstrip() for row in cells)
    return "\n".join(lines)


def _print_token(user: User, token: str) -> None:
    print(f"user_id: {user.id}")
    print(f"name:    {user.display_name}")
    print(f"tier:    {user.tier.value}")
    print(f"token:   {token}")
    print(f"MCP URL: {mcp_url(token)}")
    print("토큰은 지금 한 번만 표시됩니다. 서버에는 해시만 남습니다.")


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_init_db(args: argparse.Namespace) -> int:
    with _open_store(args):
        pass
    print(f"DB 준비됨: {_db_path(args)} (권한 0600)")
    if os.environ.get("OPENCANAL_MASTER_KEY"):
        print("마스터 키: 환경변수 OPENCANAL_MASTER_KEY")
    else:
        print(f"마스터 키: {_key_path(args)} (권한 0600, git에 넣지 않는다)")
    return 0


def cmd_create_user(args: argparse.Namespace) -> int:
    with _open_store(args) as (store, _):
        if args.user_id and store.get_user(args.user_id) is not None:
            raise CliError(f"이미 있는 사용자 ID입니다: {args.user_id}")
        user, token = store.create_user(args.name, Tier(args.tier), user_id=args.user_id)
    _print_token(user, token)
    return 0


def cmd_rotate_token(args: argparse.Namespace) -> int:
    with _open_store(args) as (store, _):
        user = _require_user(store, args.user_id)
        token = store.rotate_token(user.id)
    print("이전 토큰은 모두 폐기했습니다.")
    _print_token(user, token)
    return 0


def cmd_set_tier(args: argparse.Namespace) -> int:
    with _open_store(args) as (store, _):
        _require_user(store, args.user_id)
        user = store.set_tier(args.user_id, Tier(args.tier))
    print(f"{user.id}: tier = {user.tier.value}")
    return 0


def _load_fixture(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text("utf-8"))
        owner = data["owner"]
        return {
            "fixture_id": str(data.get("fixture_id") or path.stem),
            "user_id": str(owner["user_id"]),
            "display_name": str(owner.get("display_name") or owner["user_id"]),
            "tier": Tier(owner.get("tier", Tier.FREE.value)),
            "visibility": Visibility(data.get("visibility", Visibility.PRIVATE.value)),
            "document": data["document"],
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise CliError(f"fixture 형식 오류: {path.name}: {exc}") from exc


def _seed_one(service: Service, user: User, fx: dict[str, Any]) -> dict[str, Any]:
    """Import one fixture through Service.dispatch (tier rules apply) and publish if asked."""
    row: dict[str, Any] = {"subbrain_id": "", "version": "", "visibility": "", "redactions": "", "status": ""}
    title = fx["document"].get("title") if isinstance(fx["document"], dict) else None
    mine = service.dispatch(user, "subbrain_list_mine", {})
    for summary in (mine.get("subbrains") or []) if mine.get("ok") else []:
        if title and summary.get("title") == title:
            # Re-running seed-fixtures must not pile up duplicate subbrains.
            row.update(
                subbrain_id=summary.get("subbrain_id", ""),
                version=summary.get("latest_version", ""),
                visibility=summary.get("visibility", ""),
                status="exists (skipped)",
            )
            return row

    imported = service.dispatch(user, "subbrain_import", {"document": fx["document"]})
    if not imported.get("ok"):
        row["status"] = f"import failed — {_error_text(imported)}"
        return row
    row.update(
        subbrain_id=imported.get("subbrain_id", ""),
        version=imported.get("version", ""),
        visibility=imported.get("visibility", Visibility.PRIVATE.value),
        redactions=len(imported.get("redactions") or []),
        status="imported",
    )
    if fx["visibility"] is Visibility.PUBLIC:
        published = service.dispatch(
            user,
            "subbrain_set_visibility",
            {
                "subbrain_id": imported.get("subbrain_id"),
                "visibility": Visibility.PUBLIC.value,
                "version": imported.get("version"),
                "confirm_hash": imported.get("content_hash"),
            },
        )
        if published.get("ok"):
            row["visibility"] = _pick(published, "visibility") or Visibility.PUBLIC.value
            row["status"] = "imported + published"
        else:
            row["status"] = f"publish failed — {_error_text(published)}"
    return row


def cmd_seed_fixtures(args: argparse.Namespace) -> int:
    directory = Path(args.fixtures or DEFAULT_FIXTURES_DIR)
    files = sorted(directory.glob("*.json"))
    if not files:
        raise CliError(f"fixture가 없습니다: {directory}/*.json")
    fixtures = [_load_fixture(path) for path in files]

    rows: list[list[Any]] = []
    new_tokens: list[tuple[str, str]] = []
    failed = False
    with _open_store(args) as (store, _):
        service = _service(args, store)
        for fx in fixtures:
            user = store.get_user(fx["user_id"])
            new_user = user is None
            if user is None:
                user, token = store.create_user(fx["display_name"], fx["tier"], user_id=fx["user_id"])
                new_tokens.append((user.id, token))
            row = _seed_one(service, user, fx)
            failed = failed or "failed" in row["status"]
            rows.append(
                [
                    fx["fixture_id"],
                    user.id,
                    user.tier.value,
                    "new" if new_user else "existing",
                    row["subbrain_id"],
                    row["version"],
                    row["visibility"],
                    row["redactions"],
                    row["status"],
                ]
            )

    headers = ["fixture", "user_id", "tier", "user", "subbrain_id", "ver", "visibility", "redactions", "status"]
    print(format_table(headers, rows))
    if new_tokens:
        print()
        print("새 사용자 토큰 — 지금 한 번만 표시됩니다 (서버에는 해시만 남습니다):")
        print(format_table(["user_id", "token", "MCP URL"], [[uid, tok, mcp_url(tok)] for uid, tok in new_tokens]))
    return 1 if failed else 0


@contextmanager
def _sigterm_closes_store() -> Iterator[None]:
    """Turn SIGTERM into SystemExit(143) so the enclosing `_open_store` closes the DB.

    uvicorn handles SIGTERM itself, then restores the previous handler and raises the signal again.
    With the default handler that kills the process before Store.close(), leaving <db>-wal/-shm
    behind (and post-checkpoint writes only in the -wal file). Closing checkpoints and removes them.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def terminate(signum: int, _frame: Any) -> None:
        raise SystemExit(128 + signum)

    previous = signal.signal(signal.SIGTERM, terminate)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous if previous is not None else signal.SIG_DFL)


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .app import create_app
    from .mcp_server import install_token_log_filter

    if args.host not in LOOPBACK_HOSTS:
        print(
            f"경고: {args.host}에 바인딩합니다. v0(R0)는 로컬 전용이며, MCP 엔드포인트는 "
            "localhost Host 헤더만 받습니다.",
            file=sys.stderr,
        )
    with _open_store(args) as (store, _), _sigterm_closes_store():
        app = create_app(_service(args, store))
        config = uvicorn.Config(app, host=args.host, port=args.port, log_level=args.log_level)
        install_token_log_filter()  # after uvicorn configured its handlers
        print(f"opencanal MCP: {mcp_url('<token>', args.host, args.port)}", file=sys.stderr)
        uvicorn.Server(config).run()
    return 0


def cmd_mcp_stdio(args: argparse.Namespace) -> int:
    from .mcp_server import build_mcp, install_token_log_filter

    token = (os.environ.get("OPENCANAL_TOKEN") or "").strip() or None
    if token is None:
        # Still serve: fail closed means tools/list [] and UNAUTHORIZED, never a default user.
        print("경고: OPENCANAL_TOKEN이 없습니다. 모든 도구 호출은 UNAUTHORIZED입니다.", file=sys.stderr)
    with _open_store(args) as (store, _):
        server = build_mcp(_service(args, store), stdio_token=token)
        install_token_log_filter()  # stderr log lines get the same token mask as `serve`
        server.run("stdio")
    return 0


def _find_candidates(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    found = _pick(envelope, "candidates")
    if found is None and isinstance(envelope.get("untrusted_data"), dict):
        found = _pick(envelope["untrusted_data"], "candidates")
    return [c for c in found if isinstance(c, dict)] if isinstance(found, list) else []


def _in_rank_order(candidates: list[dict[str, Any]], strategy: Any, ranking: Any = None) -> list[dict[str, Any]]:
    """Candidate rows in the strategy's ranking (MUST-M2: by score). The envelope lists them in relevance order.

    The server's `ranking` is the exact order (v.6: unrounded values) and wins when it lists exactly these
    candidates. Without it, the rows are sorted by their rounded fields, which can tie where the exact values do not.
    """
    if isinstance(ranking, list):
        position = {}
        for i, entry in enumerate(ranking):
            if isinstance(entry, dict):
                position.setdefault((entry.get("subbrain_id"), entry.get("version")), i)
        keys = [(c.get("subbrain_id"), c.get("version")) for c in candidates]
        if len(position) == len(ranking) == len(candidates) and set(keys) == set(position):
            return sorted(candidates, key=lambda c: position[(c.get("subbrain_id"), c.get("version"))])
    try:
        parsed = [MatchCandidate.model_validate(c) for c in candidates]
    except ValidationError:
        return candidates  # unexpected shape: keep the server's order
    rows = {id(m): c for m, c in zip(parsed, candidates)}
    return [rows[id(m)] for m in matching.in_rank_order(parsed, str(strategy or ""))]


def _shown_number(value: Any) -> Any:
    """A relevance/distance/score cell at the precision the server rounds to for display (v.6)."""
    return f"{value:.{matching.DISPLAY_DECIMALS}f}" if isinstance(value, float) else value


def cmd_match_explain(args: argparse.Namespace) -> int:
    token = (args.token or os.environ.get("OPENCANAL_TOKEN") or "").strip()
    if not token:
        raise CliError("--token 또는 환경변수 OPENCANAL_TOKEN이 필요합니다")
    tool_args: dict[str, Any] = {"query": args.query, "host_subbrain_id": args.host_subbrain_id}
    if args.mode:
        tool_args["query_mode"] = args.mode
    with _open_store(args) as (store, _):
        service = _service(args, store)
        envelope = service.dispatch(service.authenticate(token), "match_explain", tool_args)
    if not envelope.get("ok"):
        print(f"오류: {_error_text(envelope)}", file=sys.stderr)
        return 1

    for key in ("host_subbrain_id", "host_version", "query_mode_used", "strategy", "tau", "max_members", "query_terms", "truncated"):
        value = _pick(envelope, key)
        if value is not None:
            print(f"{key}: {_clean_cell(_shown_number(value))}")
    candidates = _find_candidates(envelope)
    # Titles and owner names are other users' text: they arrive under untrusted_data and are only displayed.
    untrusted = envelope.get("untrusted_data") if isinstance(envelope.get("untrusted_data"), dict) else {}
    about: dict[tuple[Any, Any], dict[str, Any]] = {}
    for entry in untrusted.get("subbrains") or []:
        if isinstance(entry, dict):
            about[(entry.get("subbrain_id"), entry.get("version"))] = entry
            about.setdefault((entry.get("subbrain_id"), None), entry)
    rows = []
    ranked = _in_rank_order(candidates, _pick(envelope, "strategy"), envelope.get("ranking"))
    for rank, c in enumerate(ranked, start=1):
        info = about.get((c.get("subbrain_id"), c.get("version"))) or about.get((c.get("subbrain_id"), None)) or {}
        display = c.get("owner_display") or info.get("owner_display")
        owner_id = c.get("owner_id", "")
        rows.append(
            [
                rank,
                f"{c.get('subbrain_id', '')}@v{c.get('version', '')}",
                c.get("title") or info.get("title", ""),
                f"{display} ({owner_id})" if display else owner_id,
                _shown_number(c.get("relevance")),
                _shown_number(c.get("distance")),
                _shown_number(c.get("score")),
                c.get("matched_terms", []),
                "yes" if c.get("selected") else "no",
                c.get("reason", ""),
            ]
        )
    print()
    headers = ["rank", "subbrain", "title", "owner", "relevance", "distance", "score", "matched_terms", "selected", "reason"]
    print(format_table(headers, rows))
    if not candidates:
        print("(후보 없음)")
    return 0


def _write_private_file(directory: Path, stem: str, suffix: str, data: bytes) -> Path:
    for attempt in range(1000):
        path = directory / (f"{stem}{suffix}" if attempt == 0 else f"{stem}-{attempt}{suffix}")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(path, 0o600)
        return path
    raise CliError(f"백업 파일 이름을 만들 수 없습니다: {directory}/{stem}*{suffix}")


def cmd_backup(args: argparse.Namespace) -> int:
    out_dir = Path(args.out or DEFAULT_BACKUP_DIR)
    with _open_store(args, must_exist=True) as (store, key):
        snapshot = store.snapshot_bytes()
    blob = crypto.encrypt_backup(key, snapshot)
    crypto.make_private_dirs(out_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _write_private_file(out_dir, f"opencanal-{stamp}", ".db.enc", blob)
    print(f"백업 완료: {path} ({len(blob)} bytes, 권한 0600, 마스터 키로 암호화)")
    return 0


def _sqlite_files(db: Path) -> list[Path]:
    """The DB path and the sidecars SQLite reads as part of that database."""
    return [db, *(Path(f"{db}{suffix}") for suffix in SQLITE_SIDECARS)]


def _refuse_existing_db_files(target: Path) -> None:
    found = [path for path in _sqlite_files(target) if os.path.lexists(path)]
    if not found:
        return
    if found == [target]:
        raise CliError(f"이미 있는 파일은 덮어쓰지 않습니다: {target} (새 파일 경로를 주세요)")
    raise CliError(
        "복원하지 않습니다. 대상 경로에 이전 DB의 파일이 남아 있습니다: "
        + ", ".join(str(path) for path in found)
        + ". SQLite는 -wal/-shm/-journal 파일을 DB의 일부로 읽기 때문에, 남겨 두면 백업 위에 "
        "백업 이후의 기록이 다시 적용되거나 DB가 손상됩니다. 서버를 멈춘 뒤 이 파일들을 DB 파일과 "
        "함께 다른 곳으로 옮기거나, 다른 새 경로로 복원하세요."
    )


def _check_sqlite_image(path: Path) -> None:
    # immutable=1: read without locks or sidecar files, so checking leaves nothing behind.
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            row = conn.execute("PRAGMA quick_check").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise CliError("백업 안의 DB 이미지가 손상되었습니다 (복원하지 않음)") from exc
    if not row or row[0] != "ok":
        raise CliError("백업 안의 DB 이미지가 손상되었습니다 (복원하지 않음)")


def _fsync_path(path: Path, *, directory: bool = False) -> None:
    fd = os.open(path, os.O_RDONLY | (getattr(os, "O_DIRECTORY", 0) if directory else 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _copy_exclusive(source: Path, target: Path) -> None:
    """Fallback when the filesystem has no hard links: O_EXCL copy, removing only what this call created."""
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(source.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def _restore_db_file(target: Path, data: bytes) -> None:
    """Write the restored DB so that `target` either holds the whole checked image or does not exist.

    The image goes to a private temp file next to the target first; it is linked into place only after
    it is complete, flushed and passes SQLite's quick_check. Only that temp file is ever removed.
    MUST-E3 (v.6): the temp file is 0600 from creation (Store.restore_bytes stages it with mkstemp, so the umask
    cannot widen it), the read-only immutable check creates no sidecar, and `finally` removes it on every path.
    """
    temp = target.parent / f".{target.name}.restore-{secrets.token_hex(8)}.tmp"
    try:
        try:
            Store.restore_bytes(temp, data)  # O_EXCL, 0600; refuses data that is not a SQLite image
        except ValueError as exc:
            raise CliError("백업 안의 데이터가 SQLite DB가 아닙니다 (복원하지 않음)") from exc
        os.chmod(temp, 0o600)
        _fsync_path(temp)
        _check_sqlite_image(temp)
        _refuse_existing_db_files(target)  # again: something may have appeared since the first check
        try:
            os.link(temp, target)  # atomic, and never replaces an existing file
        except OSError as exc:  # FileExistsError (EEXIST) is re-raised here and reported below
            if exc.errno not in (errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EXDEV, errno.EMLINK):
                raise
            _copy_exclusive(temp, target)
        os.chmod(target, 0o600)
        with suppress(OSError):
            _fsync_path(target.parent, directory=True)
    except FileExistsError as exc:  # the target appeared after the checks; os.link refused to replace it
        raise CliError(f"이미 있는 파일은 덮어쓰지 않습니다: {target}") from exc
    except OSError as exc:
        raise CliError(f"복원 파일을 쓰지 못했습니다: {target} ({exc.strerror or exc})") from exc
    finally:
        for leftover in _sqlite_files(temp):
            leftover.unlink(missing_ok=True)


def cmd_restore(args: argparse.Namespace) -> int:
    if not getattr(args, "db", None):
        raise CliError("restore에는 --db PATH가 필요합니다 (새 파일 경로)")
    target = Path(args.db)
    _refuse_existing_db_files(target)
    source = Path(args.in_file)
    if not source.is_file():
        raise CliError(f"백업 파일이 없습니다: {source}")
    key = _load_key(args, create=False)
    try:
        data = crypto.decrypt_backup(key, source.read_bytes())
    except Exception as exc:  # Fernet InvalidToken is not a ValueError
        raise CliError("백업을 복호화할 수 없습니다 (다른 키이거나 손상된 파일)") from exc
    try:
        crypto.make_private_dirs(target.parent)
    except OSError as exc:
        raise CliError(f"복원 경로를 만들 수 없습니다: {target.parent} ({exc.strerror or exc})") from exc
    _restore_db_file(target, data)
    print(f"복원 완료: {target}")
    print(
        "이 파일을 다른 경로로 옮겨 쓸 때는 그 경로의 -wal/-shm/-journal 파일을 먼저 치우세요 "
        "(남아 있으면 SQLite가 복원본 위에 다시 적용합니다)."
    )
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def _common_options() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=argparse.SUPPRESS, help="SQLite DB (env OPENCANAL_DB, 기본 data/opencanal.db)")
    common.add_argument(
        "--key-file",
        dest="key_file",
        default=argparse.SUPPRESS,
        help="마스터 키 파일 (env OPENCANAL_KEY_FILE, 기본 data/keys/master.key)",
    )
    common.add_argument(
        "--config-dir",
        dest="config_dir",
        default=argparse.SUPPRESS,
        help="config 디렉터리 (env OPENCANAL_CONFIG_DIR, 기본 config/)",
    )
    return common


def build_parser() -> argparse.ArgumentParser:
    common = _common_options()
    parser = argparse.ArgumentParser(
        prog="opencanal", description="opencanal (오픈커널) v0 — 로컬 MCP 서버와 운영 명령", parents=[common]
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    tiers = [t.value for t in Tier]

    def add(name: str, handler: Any, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, parents=[common], help=help_text, description=help_text)
        p.set_defaults(handler=handler)
        return p

    add("init-db", cmd_init_db, "DB와 마스터 키(0600)를 만든다")

    p = add("create-user", cmd_create_user, "사용자를 만들고 토큰과 MCP URL을 한 번 보여준다")
    p.add_argument("--name", required=True, help="표시 이름")
    p.add_argument("--tier", required=True, choices=tiers)
    p.add_argument("--user-id", dest="user_id", default=None)

    p = add("rotate-token", cmd_rotate_token, "기존 토큰을 모두 폐기하고 새 토큰을 발급한다")
    p.add_argument("--user-id", dest="user_id", required=True)

    p = add("set-tier", cmd_set_tier, "사용자 티어를 바꾼다")
    p.add_argument("--user-id", dest="user_id", required=True)
    p.add_argument("--tier", required=True, choices=tiers)

    p = add("seed-fixtures", cmd_seed_fixtures, "합성 두뇌 fixture를 가져오고 공개 설정을 적용한다")
    p.add_argument("--fixtures", default=None, help="fixture 디렉터리 (기본 fixtures/brains)")

    p = add("serve", cmd_serve, "HTTP MCP 서버 (http://127.0.0.1:8765/mcp/<token>)")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--log-level", dest="log_level", default="info", choices=["critical", "error", "warning", "info", "debug"])

    add("mcp-stdio", cmd_mcp_stdio, "stdio MCP 서버 (토큰은 환경변수 OPENCANAL_TOKEN)")

    p = add("match-explain", cmd_match_explain, "매칭 후보와 점수를 표로 본다 (Pro 이상, 커널 생성·차감 없음)")
    p.add_argument("--token", default=None, help="MCP 토큰 (기본: 환경변수 OPENCANAL_TOKEN)")
    p.add_argument("--query", required=True)
    p.add_argument("--host-subbrain-id", dest="host_subbrain_id", required=True)
    p.add_argument("--mode", default=None, choices=[m.value for m in QueryMode])

    p = add("backup", cmd_backup, "DB를 마스터 키로 암호화해 백업한다 (0600)")
    p.add_argument("--out", default=None, help="백업 디렉터리 (기본 backups/)")

    p = add("restore", cmd_restore, "암호화 백업을 새 DB 파일로 복원한다 (기존 파일은 거부)")
    p.add_argument("--in", dest="in_file", required=True, help="백업 파일 (.db.enc)")
    return parser


def _exit_code(exc: SystemExit) -> int:
    if exc.code is None:
        return 0
    return exc.code if isinstance(exc.code, int) else 2


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # --help or usage error: return the code instead of exiting
        return _exit_code(exc)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        return int(handler(args) or 0)
    except CliError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    except OpenCanalError as exc:
        print(f"오류: {exc.code.value}: {exc.message}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
