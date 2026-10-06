"""Confirmed v.5 judge findings, pinned at unit level.

N11-V5-ORDER-1 (NEVER-11 v.5): canal_get used to list members in their stored rank order (score, relevance, real
subbrain_id) with withheld entries left at their rank position. The position bounded a withheld member's hidden
score, on a tie showed how its real id compares to others, and, since that comparison is the same in every canal,
paired withheld_refs across canals. With a private host, the score order of visible members also encoded the hidden
host-derived distance. Canals are created with store.create_canal directly, so the stored order is chosen here.

E3-1 (MUST-E3 v.5): with the DB path a symlink, the DB and its sidecars were created or left at SQLite's 0644.
"""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from opencanal import cli
from opencanal import store as store_mod
from opencanal.config import load_config
from opencanal.models import CanalMember, QueryMode, Tier, User
from opencanal.service import Service
from opencanal.store import Store

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "brains"
Q01 = "모듈러 건축의 현장 조립 오류를 줄일 아이디어"
OWNERS = {"A": "user_a", "B": "user_b", "C": "user_c", "A2": "user_e"}


def _brain(fid: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{fid}.json").read_text("utf-8"))


def _ok(env: dict[str, Any]) -> dict[str, Any]:
    assert env.get("ok") is True, env
    return env


# -- N11-V5-ORDER-1 ------------------------------------------------------------------------------------------------


class _World:
    def __init__(self) -> None:
        self.store = Store(":memory:", master_key=os.urandom(32))
        self.svc = Service(self.store, load_config())
        self.users: dict[str, User] = {}
        self.sids: dict[str, str] = {}
        self.hashes: dict[str, str] = {}
        for fid in ("A", "B", "C", "A2"):
            owner = _brain(fid)["owner"]
            assert owner["user_id"] == OWNERS[fid]
            self.users[owner["user_id"]], _ = self.store.create_user(
                owner["display_name"], Tier.PRO, user_id=owner["user_id"]
            )
            imported = _ok(self.call(owner["user_id"], "subbrain_import", document=_brain(fid)["document"]))
            self.sids[fid], self.hashes[fid] = imported["subbrain_id"], imported["content_hash"]
            self.set_visibility(fid, "public")

    def call(self, uid: str, tool: str, **args: Any) -> dict[str, Any]:
        return self.svc.dispatch(self.users[uid], tool, args)

    def set_visibility(self, fid: str, visibility: str) -> None:
        _ok(self.call(OWNERS[fid], "subbrain_set_visibility", subbrain_id=self.sids[fid], visibility=visibility,
                      confirm_hash=self.hashes[fid]))

    def open(self, host: str, members: list[tuple[str, float, float]], mode: QueryMode = QueryMode.TOPIC) -> str:
        """A canal whose members are stored in exactly this order: (fixture, relevance, distance)."""
        stored = [
            CanalMember(subbrain_id=self.sids[fid], version=1, owner_id=OWNERS[fid], relevance=rel, distance=dist,
                        matched_terms=["조립"])
            for fid, rel, dist in members
        ]
        return self.store.create_canal(OWNERS[host], self.sids[host], 1, Q01, mode, stored).id

    def get(self, uid: str, canal_id: str) -> dict[str, Any]:
        return _ok(self.call(uid, "canal_get", canal_id=canal_id))

    def ref(self, canal_id: str, fid: str) -> str:
        return self.store.withheld_ref(canal_id, self.sids[fid])

    def layout(self, env: dict[str, Any]) -> list[str]:
        """canal.members as fixture names, withheld entries as their ref; asserts untrusted_data.subbrains agrees."""
        by_sid = {sid: fid for fid, sid in self.sids.items()}

        def name(item: dict[str, Any]) -> str:
            return item["withheld_ref"] if item.get("withheld") else by_sid[item["subbrain_id"]]

        members = [name(m) for m in env["canal"]["members"]]
        assert [name(e) for e in env["untrusted_data"]["subbrains"]] == members
        return members


@pytest.fixture
def world() -> Iterator[_World]:
    w = _World()
    yield w
    w.store.close()


# Q-01 with host A: B and C tie on score 0.70 (0.40 + 0.3 * 1.0); A2 scores 0.56. Stored rank order breaks the B-C
# tie on the real subbrain_id, so both stored orders below are rank orders for some pair of random ids.
B, C, A2 = ("B", 0.40, 1.0), ("C", 0.40, 1.0), ("A2", 0.56, 0.0)


@pytest.mark.parametrize("stored", [[C, B, A2], [B, C, A2]], ids=["C-first", "B-first"])
def test_a_withheld_member_is_listed_after_the_visible_ones_whatever_its_rank(world: _World, stored) -> None:
    canal = world.open("A", stored)
    world.set_visibility("C", "private")
    for viewer in ("user_e", "user_a", "user_b"):  # A2's owner, the host, B's owner: none owns C
        assert world.layout(world.get(viewer, canal)) == ["B", "A2", world.ref(canal, "C")], viewer
        assert world.sids["C"] not in json.dumps(world.get(viewer, canal))


def test_withheld_members_are_listed_by_their_per_canal_ref(world: _World) -> None:
    canals = [world.open("A", [B, C, A2]), world.open("A2", [("A", 1.0, 0.0), B, C])]
    world.set_visibility("B", "private")
    world.set_visibility("C", "private")
    for canal in canals:
        refs = sorted([world.ref(canal, "B"), world.ref(canal, "C")])
        for viewer in ("user_a", "user_e"):  # both take part in both canals and own neither B nor C
            assert world.layout(world.get(viewer, canal))[-2:] == refs, (canal, viewer)


def test_withheld_positions_do_not_pair_refs_across_canals(world: _World) -> None:
    """Every canal stores B before C. If positions followed the stored rank, B's ref would come first in every canal
    and a participant could pair the refs of any two canals by position. Ordered by the per-canal ref instead, B
    comes first in about half of them (all 32 the same: probability 2**-31)."""
    canals = [world.open("A", [B, C, A2]) for _ in range(32)]
    world.set_visibility("B", "private")
    world.set_visibility("C", "private")
    b_first = []
    for canal in canals:
        layout = world.layout(world.get("user_e", canal))
        assert layout[0] == "A2" and set(layout[1:]) == {world.ref(canal, "B"), world.ref(canal, "C")}
        b_first.append(layout[1] == world.ref(canal, "B"))
    assert any(b_first) and not all(b_first), b_first


def test_private_host_topic_mode_lists_visible_members_by_shown_relevance(world: _World) -> None:
    """Stored score order is B, C, A2 (0.70, 0.70, 0.56). With host A private, distance is hidden; keeping that order
    would tell the viewer A2's distance to the hidden host is lower. Relevance (shown) puts A2 first."""
    canal = world.open("A", [B, C, A2])
    world.set_visibility("A", "private")
    tied = sorted(["B", "C"], key=lambda fid: world.sids[fid])
    for viewer in ("user_e", "user_b", "user_c"):
        env = world.get(viewer, canal)
        assert "host_withheld_ref" in env["canal"] and "host_subbrain_id" not in env["canal"]
        assert world.layout(env) == ["A2", *tied], viewer
        assert all("distance" not in m and "relevance" in m for m in env["canal"]["members"])


def test_private_host_whole_host_mode_lists_visible_members_by_id(world: _World) -> None:
    """In whole_host mode relevance is host-derived too, so neither score nor relevance may order the list."""
    canal = world.open("A", [("A2", 1.0, 0.0), ("C", 0.45, 1.0), ("B", 0.40, 1.0)], mode=QueryMode.WHOLE_HOST)
    world.set_visibility("A", "private")
    by_id = sorted(["A2", "B", "C"], key=lambda fid: world.sids[fid])
    for viewer in ("user_e", "user_b"):
        env = world.get(viewer, canal)
        assert world.layout(env) == by_id, viewer
        assert all("distance" not in m and "relevance" not in m for m in env["canal"]["members"])


def test_private_host_and_private_member_together(world: _World) -> None:
    canal = world.open("A", [B, C, A2])
    world.set_visibility("A", "private")
    world.set_visibility("B", "private")
    env = world.get("user_e", canal)
    assert world.layout(env) == ["A2", "C", world.ref(canal, "B")]
    assert env["canal"]["host_withheld_ref"] == world.ref(canal, "A")


def test_nothing_withheld_keeps_the_stored_rank_order(world: _World) -> None:
    canal = world.open("A", [C, B, A2])
    assert world.layout(world.get("user_e", canal)) == ["C", "B", "A2"]
    # An owner sees their own private subbrain: nothing is withheld from them, so the stored order stays.
    world.set_visibility("C", "private")
    assert world.layout(world.get("user_c", canal)) == ["C", "B", "A2"]


def test_with_the_host_shown_visible_members_keep_their_stored_relative_order(world: _World) -> None:
    """Relevance alone would put A2 first; the stored score order (computable from the shown relevance and distance)
    stays for visible members."""
    canal = world.open("A", [B, A2, C])
    world.set_visibility("C", "private")
    assert world.layout(world.get("user_e", canal)) == ["B", "A2", world.ref(canal, "C")]


# -- E3-1: DB path through a symlink -------------------------------------------------------------------------------


def _mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def _sidecar(path: Path, suffix: str) -> Path:
    return path.with_name(path.name + suffix)


@contextmanager
def _umask(value: int) -> Iterator[None]:
    old = os.umask(value)
    try:
        yield
    finally:
        os.umask(old)


@pytest.mark.parametrize("relative", [False, True], ids=["absolute-target", "relative-target"])
def test_db_created_through_a_dangling_symlink_is_0600_with_its_sidecars(tmp_path: Path, relative: bool) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "ext").mkdir()
    link, target = tmp_path / "data" / "opencanal.db", tmp_path / "ext" / "opencanal.db"
    os.symlink(Path("..") / "ext" / "opencanal.db" if relative else target, link)
    with _umask(0o000):
        s = Store(link, master_key=os.urandom(32))
        try:
            s.create_user("u", Tier.FREE, user_id="user_x")  # a write after open: -wal/-shm exist now
            assert link.is_symlink()
            for p in (target, _sidecar(target, "-wal"), _sidecar(target, "-shm")):
                assert p.exists() and _mode(p) == 0o600, p
        finally:
            s.close()
    assert _mode(target) == 0o600 and link.is_symlink()
    assert not any(_sidecar(link, suffix).exists() for suffix in ("-wal", "-shm", "-journal"))


def test_dangling_symlink_target_directory_is_created_0700(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    link, target = tmp_path / "data" / "opencanal.db", tmp_path / "ext" / "sub" / "opencanal.db"
    os.symlink(target, link)
    with _umask(0o000):
        Store(link, master_key=os.urandom(32)).close()
    assert _mode(tmp_path / "ext") == 0o700 and _mode(tmp_path / "ext" / "sub") == 0o700 and _mode(target) == 0o600


def test_existing_db_opened_through_a_symlink_has_wide_sidecars_narrowed(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "data").mkdir()
    real, link = tmp_path / "real" / "opencanal.db", tmp_path / "data" / "opencanal.db"
    Store(real, master_key=os.urandom(32)).close()
    other = sqlite3.connect(real)  # keeps -wal/-shm alive
    try:
        other.execute("PRAGMA journal_mode=WAL")
        other.execute("INSERT INTO audit_log (ts, actor, action, target, detail_json) VALUES ('t','a','x','t','{}')")
        other.commit()
        for p in (real, _sidecar(real, "-wal"), _sidecar(real, "-shm")):
            os.chmod(p, 0o644)
        os.symlink(real, link)
        s = Store(link, master_key=os.urandom(32))
        try:
            for p in (real, _sidecar(real, "-wal"), _sidecar(real, "-shm")):
                assert _mode(p) == 0o600, p
        finally:
            s.close()
    finally:
        other.close()


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_prepare_narrows_sidecars_next_to_the_symlink_target(tmp_path: Path, suffix: str) -> None:
    (tmp_path / "real").mkdir()
    real, link = tmp_path / "real" / "x.db", tmp_path / "x.db"
    Store(real, master_key=os.urandom(32)).close()
    os.chmod(real, 0o644)
    _sidecar(real, suffix).write_bytes(b"")
    os.chmod(_sidecar(real, suffix), 0o666)
    os.symlink(real, link)
    assert store_mod._prepare_db_file(link) == Path(os.path.realpath(real))
    assert _mode(real) == 0o600 and _mode(_sidecar(real, suffix)) == 0o600


@pytest.fixture
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENCANAL_MASTER_KEY", "OPENCANAL_DB", "OPENCANAL_KEY_FILE", "OPENCANAL_TOKEN"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.usefixtures("_clean_env")
@pytest.mark.parametrize("umask", [0o022, 0o002], ids=["umask022", "umask002"])
def test_cli_init_db_through_a_dangling_symlink_creates_the_target_0600(tmp_path: Path, umask: int) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "ext").mkdir()
    link, target = tmp_path / "data" / "opencanal.db", tmp_path / "ext" / "opencanal.db"
    os.symlink(target, link)
    with _umask(umask):
        assert cli.main(["--db", str(link), "--key-file", str(tmp_path / "keys" / "master.key"), "init-db"]) == 0
    assert link.is_symlink() and _mode(target) == 0o600
