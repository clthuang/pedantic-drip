"""Top-level conftest for plugins/pd/hooks/lib/ tests.

Registration is strict here, as in production. Wave 2 step 2 removed the
session-wide opt-out; step 4 removed the last per-test one, once backfill
skipped legacy ids instead of registering them.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolate_entity_db_path(tmp_path_factory) -> None:
    """Session-wide default: point ENTITY_DB_PATH at a throwaway DB.

    Any test (or subprocess it spawns) that lets the resolver fall back to
    the real ``~/.claude/pd/entities/entities.db`` registers temp
    workspaces there (2,305-row leak purged in the 2026-09-17 hygiene
    sweep). ``os.environ.setdefault`` so explicit per-test
    ``monkeypatch.setenv("ENTITY_DB_PATH", ...)`` still wins.
    """
    os.environ.setdefault(
        "ENTITY_DB_PATH", str(tmp_path_factory.mktemp("entity-db") / "entities.db")
    )
    yield
