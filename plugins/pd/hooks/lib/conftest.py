"""Top-level conftest for plugins/pd/hooks/lib/ tests.

Registration is strict here, as in production: every entity_id must match
``^\\d+-.+``. Wave 2 step 2 removed the session-wide opt-out once step 1 had
moved every test id to round-trip form.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def _strict_id_format_off_until_c7(monkeypatch) -> None:
    """Registration without the id check, for tests whose fixture files hold
    legacy ids that production backfill registers as read.

    ``backfill.py`` passes a backlog.md row's first cell (``00019``), a
    brainstorm stem and a ``.meta.json`` project id straight to registration,
    and strict mode refuses them, in production too. C7 (Wave 2 step 4) moves
    backfill to structured identity; until then these tests keep the legacy
    fixtures, which are the formats real repositories hold. The name carries
    the strict switch's so D5's exit grep stays red while any test uses it.
    """
    monkeypatch.setenv("PD_REGISTER_ENTITY_STRICT_ID_FORMAT", "0")


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
