"""Oracle v.5 pins for the two confirmed v.5 judge findings that tests/oracle did not see (CHANGE-004 §10).

- NEVER-11 v.5: withheld canal_get entries sit after visible entries, ordered by withheld_ref,
  so their position does not reveal the original rank/score (N11-V5-ORDER-1).
- MUST-E3 v.5: a symlinked DB path still yields a 0600 DB file and sidecars at the real location (E3-1).

Written from the Oracle text by the Oracle-owner proxy (planner), not by a Builder.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from opencanal import crypto
from opencanal.models import Tier

from .test_oracle_v5_unlinkability import _build, _close


@pytest.fixture(autouse=True)
def _no_env_master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCANAL_MASTER_KEY", raising=False)


@pytest.mark.parametrize("viewer", ["user_a", "user_e"])
def test_never_11_v5_withheld_entries_do_not_keep_their_rank_position(tmp_path: Path, viewer: str):
    info = _build(tmp_path, ("B", "C"))
    try:
        w = info["world"]
        for canal_id in info["canals"]:
            env = w.call(viewer, "canal_get", canal_id=canal_id)
            assert env["ok"] is True, env
            for listing in (env["canal"]["members"], env["untrusted_data"]["subbrains"]):
                flags = [bool(m.get("withheld")) for m in listing]
                assert any(flags), f"expected withheld entries for {viewer}: {listing}"
                first_withheld = flags.index(True)
                assert all(flags[first_withheld:]), f"withheld entry before a visible one: {flags}"
                refs = [m["withheld_ref"] for m in listing if m.get("withheld")]
                assert refs == sorted(refs), f"withheld entries not in handle order: {refs}"
    finally:
        _close(info)


def test_must_e3_v5_symlinked_db_path_yields_0600_real_files(tmp_path: Path):
    from opencanal.store import Store

    old = os.umask(0o022)
    try:
        real_dir = tmp_path / "real"
        real_dir.mkdir()
        link_dir = tmp_path / "link"
        link_dir.mkdir()
        link = link_dir / "opencanal.db"
        target = real_dir / "opencanal.db"
        link.symlink_to(target)  # dangling until the Store creates the DB
        key = crypto.load_or_create_master_key(tmp_path / "keys" / "master.key")
        store = Store(link, master_key=key)
        try:
            store.create_user("Haram Kim", Tier.FREE, user_id="user_a")
            files = [p for p in (target, Path(f"{target}-wal"), Path(f"{target}-shm"), Path(f"{target}-journal")) if p.exists()]
            assert target in files, "DB was not created at the symlink target"
            for p in files:
                assert stat.S_IMODE(p.stat().st_mode) == 0o600, f"{p.name} is {oct(stat.S_IMODE(p.stat().st_mode))}"
        finally:
            store.close()
    finally:
        os.umask(old)
