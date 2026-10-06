"""Observer for MUST-E3 (Oracle v.6): plaintext temporary DB files made during backup/restore are 0600 and removed.

Standalone on purpose (stdlib only, no package-relative imports): the CLI tests copy this file next to a generated
`sitecustomize.py` so the very same observer runs inside the `opencanal` subprocess.

What it records: every regular file that holds a plaintext SQLite database (it starts with the SQLite header) or that
is a -journal/-wal/-shm sidecar of such a file, with every permission mode it was seen with. Two read-only observers:

- an audit hook (sys.addaudithook). Python raises audit events *before* a file operation takes effect: open,
  os.chmod, os.remove (unlink), os.rename (rename/replace), shutil.rmtree, shutil.copyfile, sqlite3.connect,
  tempfile.mkstemp/mkdtemp, ... On each one the hook stats the paths named by the event and every file under the
  watched directories. A plaintext copy that is read back, chmod-ed, renamed, or deleted from Python is therefore
  seen with the mode it had right before that step — deterministically, however short-lived the file is.
- a polling thread that does the same scan continuously (extra coverage only; it can miss, never invent).

The hook never raises into the observed code and ignores its own file accesses.
"""

from __future__ import annotations

import atexit
import json
import os
import stat
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

SQLITE_HEADER = b"SQLite format 3\x00"
SIDECARS = ("-journal", "-wal", "-shm")

_EVENTS = frozenset(
    {
        "open",
        "os.chmod",
        "os.chown",
        "os.remove",
        "os.rename",
        "os.rmdir",
        "os.link",
        "os.symlink",
        "os.truncate",
        "os.utime",
        "shutil.rmtree",
        "shutil.copyfile",
        "shutil.copymode",
        "shutil.copystat",
        "shutil.copytree",
        "shutil.move",
        "sqlite3.connect",
        "tempfile.mkstemp",
        "tempfile.mkdtemp",
    }
)
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

_local = threading.local()
_active: Optional["Spy"] = None
_hook_installed = False


def _as_path(value: Any) -> Optional[str]:
    if isinstance(value, (str, bytes, os.PathLike)):
        try:
            p = os.fsdecode(os.fspath(value))
        except Exception:
            return None
        if p and p != ":memory:" and not p.startswith("file::memory:"):
            if p.startswith("file:"):
                p = p[5:].split("?", 1)[0]
            return os.path.abspath(p)
    return None


def _hook(event: str, args: tuple) -> None:
    spy = _active
    if spy is None or event not in _EVENTS or getattr(_local, "busy", False):
        return
    _local.busy = True
    try:
        spy._on_event(event, args)
    except Exception:  # never disturb the observed code
        pass
    finally:
        _local.busy = False


def _install_hook() -> None:
    global _hook_installed
    if not _hook_installed:
        sys.addaudithook(_hook)
        _hook_installed = True


class Spy:
    """Context manager. `observations` maps a plaintext-DB path to the set of modes it was seen with."""

    def __init__(self, watch_dirs: Iterable[Path | str], *, poll: bool = True, interval: float = 0.0005) -> None:
        self.watch_dirs = [os.path.abspath(os.fspath(d)) for d in watch_dirs]
        self.poll = poll
        self.interval = interval
        self.observations: dict[str, set[int]] = {}
        self.named_paths: set[str] = set()
        self.events: list[tuple[str, str]] = []
        self._plain: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.on_new: Optional[Callable[[str, int], None]] = None

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> "Spy":
        global _active
        _install_hook()
        self.scan()
        _active = self
        if self.poll:
            self._thread = threading.Thread(target=self._run, name="oracle-tmpspy", daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        global _active
        _active = None
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        _local.busy = True
        try:
            self.scan()
        finally:
            _local.busy = False

    def _run(self) -> None:
        _local.busy = True  # the poller's own file access must not re-enter the hook
        while not self._stop.is_set():
            try:
                self.scan()
            except Exception:
                pass
            self._stop.wait(self.interval)

    # -- observation ---------------------------------------------------------
    def _on_event(self, event: str, args: tuple) -> None:
        paths: list[str] = []
        if event == "open":
            path = _as_path(args[0]) if args else None
            flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
            if path is None:
                return
            if not (flags & _WRITE_FLAGS) and not self._interesting(path):
                return  # plain reads elsewhere (imports, config) are not our business
            paths.append(path)
        else:
            for a in args:
                p = _as_path(a)
                if p is not None:
                    paths.append(p)
        with self._lock:
            for p in paths:
                self.named_paths.add(p)
                self.events.append((event, p))
        self.scan(extra=paths)

    def _interesting(self, path: str) -> bool:
        if path in self.named_paths or path in self._plain:
            return True
        return any(path == d or path.startswith(d + os.sep) for d in self.watch_dirs)

    def _candidates(self, extra: Iterable[str]) -> set[str]:
        with self._lock:
            out = set(extra) | set(self.named_paths) | set(self._plain)
        for d in self.watch_dirs:
            for root, _dirs, files in os.walk(d):
                for f in files:
                    out.add(os.path.join(root, f))
        for p in list(out):
            for s in SIDECARS:
                out.add(p + s)
        return out

    def scan(self, extra: Iterable[str] = ()) -> None:
        for path in self._candidates(extra):
            try:
                st = os.lstat(path)
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            mode = stat.S_IMODE(st.st_mode)
            if self._is_plain(path):
                self._record(path, mode)

    def _is_plain(self, path: str) -> bool:
        if path in self._plain:
            return True
        for s in SIDECARS:
            if path.endswith(s) and path[: -len(s)] in self._plain:
                return True
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError:
            return False
        try:
            head = os.read(fd, len(SQLITE_HEADER))
        finally:
            os.close(fd)
        if head == SQLITE_HEADER:
            with self._lock:
                self._plain.add(path)
            return True
        return False

    def _record(self, path: str, mode: int) -> None:
        with self._lock:
            modes = self.observations.setdefault(path, set())
            new = mode not in modes
            modes.add(mode)
        if new and self.on_new is not None:
            try:
                self.on_new(path, mode)
            except Exception:
                pass

    # -- results ---------------------------------------------------------------
    def wide(self, *, exclude: Iterable[str] = ()) -> dict[str, list[str]]:
        """Plaintext-DB files seen with any mode other than 0600 (paths in `exclude` and their sidecars skipped)."""
        skip = _with_sidecars(exclude)
        return {
            p: sorted(oct(m) for m in modes)
            for p, modes in sorted(self.observations.items())
            if p not in skip and any(m != 0o600 for m in modes)
        }

    def plaintext_paths(self, *, exclude: Iterable[str] = ()) -> list[str]:
        skip = _with_sidecars(exclude)
        return sorted(p for p in self.observations if p not in skip)


def _with_sidecars(paths: Iterable[str | Path]) -> set[str]:
    out: set[str] = set()
    for p in paths:
        a = os.path.abspath(os.fspath(p))
        out.add(a)
        out.update(a + s for s in SIDECARS)
    return out


# ---------------------------------------------------------------------------
# Subprocess mode: sitecustomize calls install_from_env()
# ---------------------------------------------------------------------------

LOG_ENV = "ORACLE_TMPSPY_LOG"  # not OPENCANAL_*: the implementation's own settings stay untouched
DIRS_ENV = "ORACLE_TMPSPY_DIRS"


def install_from_env() -> None:
    log = os.environ.get(LOG_ENV)
    if not log:
        return
    dirs = [d for d in os.environ.get(DIRS_ENV, "").split(os.pathsep) if d]
    spy = Spy(dirs)
    lock = threading.Lock()

    def write(obj: dict[str, Any]) -> None:
        line = json.dumps(obj) + "\n"
        prev = getattr(_local, "busy", False)
        _local.busy = True
        try:
            with lock, open(log, "a", encoding="utf-8") as fh:
                fh.write(line)
        finally:
            _local.busy = prev

    write({"loaded": True, "pid": os.getpid()})
    spy.on_new = lambda path, mode: write({"path": path, "mode": mode})
    spy.__enter__()

    def finish() -> None:
        try:
            spy.__exit__(None, None, None)
            write({"done": True, "observations": {p: sorted(m) for p, m in spy.observations.items()}})
        except Exception:
            pass

    atexit.register(finish)


def read_log(path: Path) -> dict[str, Any]:
    """Merge a subprocess log: {"loaded": bool, "done": bool, "observations": {path: [modes]}}."""
    out: dict[str, Any] = {"loaded": False, "done": False, "observations": {}}
    if not path.exists():
        return out
    obs: dict[str, set[int]] = {}
    for line in path.read_text("utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("loaded"):
            out["loaded"] = True
        if "path" in rec:
            obs.setdefault(rec["path"], set()).add(int(rec["mode"]))
        if rec.get("done"):
            out["done"] = True
            for p, modes in rec.get("observations", {}).items():
                obs.setdefault(p, set()).update(int(m) for m in modes)
    out["observations"] = obs
    return out


SITECUSTOMIZE = "import _oc_tmpspy\n_oc_tmpspy.install_from_env()\n"


def prepare_site_dir(site_dir: Path) -> Path:
    """A directory to put first on PYTHONPATH: this module as `_oc_tmpspy` plus a sitecustomize that installs it."""
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "_oc_tmpspy.py").write_text(Path(__file__).read_text("utf-8"), "utf-8")
    (site_dir / "sitecustomize.py").write_text(SITECUSTOMIZE, "utf-8")
    return site_dir
