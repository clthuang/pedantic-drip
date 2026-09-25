"""W2.6: the startup backfill reads no files, and stays in its workspace.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W2 change 6
and its "Backfill scope" and "Backfill source" tests.

- **Scope:** the backfill iterates only the server's workspace and passes
  that workspace to every write, so another workspace's rows are never
  rewritten, and a type_id two workspaces hold is seeded for the caller.
- **Source:** status comes from the registry. A feature's phase is
  ``finish`` when it is completed, otherwise None; ``last_completed_phase``
  and ``mode`` stay None. No ``.meta.json`` is read.

Workspace B's uuid sorts first and B registers each shared type_id first,
so the ``wp_autofill_workspace_uuid`` trigger's guess is always B.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

_MCP_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp"))
if _MCP_DIR not in sys.path:
    sys.path.insert(0, _MCP_DIR)

import entity_server  # noqa: E402
import server_lifecycle  # noqa: E402
from entity_registry.backfill import backfill_workflow_phases  # noqa: E402
from entity_registry.database import EntityDatabase  # noqa: E402

WORKSPACE_B = "00000000-0000-4000-8000-0000000000bb"  # sorts first
WORKSPACE_A = "ffffffff-0000-4000-8000-0000000000aa"


def _add_workspace(db: EntityDatabase, workspace_uuid: str, legacy_id: str) -> None:
    now = db._now_iso()
    db._conn.execute(
        "INSERT INTO workspaces (uuid, project_id_legacy, project_root, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (workspace_uuid, legacy_id, None, now, now),
    )
    db._conn.commit()


@pytest.fixture
def db(tmp_path):
    database = EntityDatabase(str(tmp_path / "entities.db"))
    _add_workspace(database, WORKSPACE_B, "backfill-scope-b")
    _add_workspace(database, WORKSPACE_A, "backfill-scope-a")
    yield database
    database.close()


@pytest.fixture
def artifacts_root(tmp_path) -> str:
    """The checkout's artifacts root: the backfill must not read it."""
    root = tmp_path / "docs"
    (root / "features").mkdir(parents=True)
    return str(root)


def _backfill_as_the_server_of(db, workspace_uuid):
    """The entity server's startup call, for a server whose workspace is
    *workspace_uuid*."""
    return backfill_workflow_phases(db, workspace_uuid)


def _brainstorm(db, workspace_uuid, stem):
    uuid = db.register_entity(
        "brainstorm", name=stem, display_id=stem, workspace_uuid=workspace_uuid,
    )
    return db.get_entity_by_uuid(uuid)


def test_another_workspaces_null_phase_brainstorm_row_is_left_alone(db):
    """B's row with a NULL phase is not A's to fill in (before W2.6 it was
    rewritten through the NULL-phase update). A's own brainstorm is seeded
    in the same run, so the run did work."""
    brainstorm_b = _brainstorm(db, WORKSPACE_B, "20260925-000000-b-idea")
    db.create_workflow_phase(
        brainstorm_b["type_id"], workflow_phase=None, kanban_column="backlog",
    )
    row_b_before = dict(db.get_workflow_phase(brainstorm_b["type_id"]))
    brainstorm_a = _brainstorm(db, WORKSPACE_A, "20260925-000001-a-idea")

    _backfill_as_the_server_of(db, WORKSPACE_A)

    assert dict(db.get_workflow_phase(brainstorm_b["type_id"])) == row_b_before
    row_a = db.get_workflow_phase(brainstorm_a["type_id"])
    assert row_a is not None
    assert (row_a["workspace_uuid"], row_a["uuid"]) == (WORKSPACE_A, brainstorm_a["uuid"])
    assert (row_a["workflow_phase"], row_a["kanban_column"]) == ("draft", "wip")


def test_a_shared_type_ids_row_owned_by_another_workspace_is_left_alone(db):
    """A holds the type_id too, so A's run reaches the row; the row is B's,
    and the NULL-phase update, given A's workspace, refuses it."""
    stem = "20260925-000002-shared-idea"
    shared_b = _brainstorm(db, WORKSPACE_B, stem)
    db.create_workflow_phase(
        shared_b["type_id"], workflow_phase=None, kanban_column="backlog",
    )
    _brainstorm(db, WORKSPACE_A, stem)
    row_before = dict(db.get_workflow_phase(shared_b["type_id"]))

    result = _backfill_as_the_server_of(db, WORKSPACE_A)

    assert dict(db.get_workflow_phase(shared_b["type_id"])) == row_before
    assert any(shared_b["type_id"] in error for error in result["errors"]), result


def test_a_shared_type_ids_missing_row_is_seeded_for_the_calling_workspace(db):
    """``feature:035``'s shape: both workspaces hold the type_id, no row
    exists, and only A's server runs. The row is A's, with A's entity uuid
    (the trigger's guess would be B)."""
    db.register_entity(
        "feature", name="Shared", seq=35, slug="shared", status="active",
        workspace_uuid=WORKSPACE_B,
    )
    uuid_a = db.register_entity(
        "feature", name="Shared", seq=35, slug="shared", status="active",
        workspace_uuid=WORKSPACE_A,
    )

    _backfill_as_the_server_of(db, WORKSPACE_A)

    row = db.get_workflow_phase("feature:035-shared")
    assert row is not None
    assert (row["workspace_uuid"], row["uuid"]) == (WORKSPACE_A, uuid_a)


def test_a_completed_features_row_comes_from_the_registry_not_its_meta_json(db, artifacts_root):
    """The registry says completed; the checkout's ``.meta.json``, both at
    the stored ``artifact_path`` and at the convention path, says active.
    The row is seeded ``finish`` / ``completed`` with no phase or mode read
    from the file."""
    feature_dir = os.path.join(artifacts_root, "features", "007-done")
    os.makedirs(feature_dir)
    with open(os.path.join(feature_dir, ".meta.json"), "w", encoding="utf-8") as handle:
        json.dump({"status": "active", "lastCompletedPhase": "design",
                   "mode": "full"}, handle)
    uuid_a = db.register_entity(
        "feature", name="Done", seq=7, slug="done", status="completed",
        artifact_path=feature_dir, workspace_uuid=WORKSPACE_A,
    )

    _backfill_as_the_server_of(db, WORKSPACE_A)

    row = db.get_workflow_phase("feature:007-done")
    assert row is not None
    assert (row["workflow_phase"], row["kanban_column"]) == ("finish", "completed")
    assert (row["last_completed_phase"], row["mode"]) == (None, None)
    assert (row["workspace_uuid"], row["uuid"]) == (WORKSPACE_A, uuid_a)


def test_an_unresolved_workspace_backfills_nothing(db):
    """An empty workspace never widens to every workspace's entities."""
    brainstorm_b = _brainstorm(db, WORKSPACE_B, "20260925-000003-b-unscoped")

    with pytest.raises(ValueError, match="requires a workspace_uuid"):
        backfill_workflow_phases(db, "")

    assert db.get_workflow_phase(brainstorm_b["type_id"]) is None


# Module globals the entity server's lifespan assigns; restored after the test.
_ENTITY_SERVER_GLOBALS = (
    "_db", "_db_unavailable", "_recovery_thread", "_config", "_project_root",
    "_artifacts_root", "_project_id", "_git_info", "_workspace_uuid",
)


def test_the_entity_servers_startup_seeds_only_its_own_workspace(db, tmp_path, monkeypatch):
    """The lifespan passes its resolved workspace (A) to the backfill: A's
    brainstorm is seeded; B's brainstorm and feature get no row. The PID
    files go under a temp HOME and the parent-PID watchdog is not started."""
    brainstorm_a = _brainstorm(db, WORKSPACE_A, "20260925-000004-a-startup")
    brainstorm_b = _brainstorm(db, WORKSPACE_B, "20260925-000005-b-startup")
    db.register_entity(
        "feature", name="B only", seq=8, slug="b-only", status="active",
        workspace_uuid=WORKSPACE_B,
    )
    home = tmp_path / "home"
    project_root = tmp_path / "project"
    (project_root / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ENTITY_DB_PATH", str(tmp_path / "entities.db"))
    monkeypatch.setenv("PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("ENTITY_WORKSPACE_UUID", WORKSPACE_A)
    monkeypatch.delenv("WORKSPACE_UUID", raising=False)
    monkeypatch.setattr(server_lifecycle, "PID_DIR", home / ".claude" / "pd" / "run")
    monkeypatch.setattr(entity_server, "start_parent_watchdog", lambda: None)
    for name in _ENTITY_SERVER_GLOBALS:
        monkeypatch.setattr(entity_server, name, getattr(entity_server, name))

    async def start_and_stop():
        async with entity_server.lifespan(None):
            assert entity_server._workspace_uuid == WORKSPACE_A

    asyncio.run(start_and_stop())

    row_a = db.get_workflow_phase(brainstorm_a["type_id"])
    assert row_a is not None
    assert (row_a["workspace_uuid"], row_a["uuid"]) == (WORKSPACE_A, brainstorm_a["uuid"])
    assert db.get_workflow_phase(brainstorm_b["type_id"]) is None
    assert db.get_workflow_phase("feature:008-b-only") is None
