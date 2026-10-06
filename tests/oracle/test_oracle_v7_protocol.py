"""The synthesis protocol tells the host's LLM to label the query node with the query sentence, so canal_open
must hand that sentence back to the host (it is the host's own text, so it sits outside untrusted_data).

Found in the first real LLM synthesis run (2026-10-07): all six synthesizers had to reconstruct the sentence
from query_terms. Written by the Oracle-owner proxy (planner) from TASK-001 §5 + protocol rule 4.
"""

from __future__ import annotations

from .conftest import Q01, World


def test_canal_open_returns_the_hosts_query_sentence(tmp_path):
    world = World(tmp_path).seed()
    env = world.open_canal()
    assert env["ok"] is True, env
    assert env.get("query") == Q01, f"canal_open must return the host's own query sentence: {sorted(env)}"
