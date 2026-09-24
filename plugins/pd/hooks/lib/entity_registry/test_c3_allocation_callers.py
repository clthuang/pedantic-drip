"""C3 — the completeness guard's refusal reaches every allocation caller.

``next_sequence_value`` raises ``IncompleteBucketError`` for a bucket holding
an entity that breaks the display-row invariant. Each MCP tool that
allocates must hand that back as a clear error: not swallowed into a
success-shaped result, not relabelled as the caller's own bad input, and not
retried — the refusal is a registry state, so a retry can only repeat it.

Every test counts ``next_sequence_value`` calls and reads the ``sequences``
counter afterwards, so "returned an error" alone cannot pass.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_mcp_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp"))
if _mcp_dir not in sys.path:
    sys.path.insert(0, _mcp_dir)

import entity_server  # noqa: E402
import workflow_state_server  # noqa: E402
from entity_registry.database import EntityDatabase  # noqa: E402
from entity_registry.test_helpers import bootstrap_test_workspace  # noqa: E402

_WORKSPACE_LEGACY_ID = "c3-callers"
_OFFENDING_SEQ = 6
_COUNTER_BEFORE = 7

_PLAN_MD = """# Tasks

## Phase 1

#### Task 1.1: Add structured log fields
- **Do:** Add fields.
"""


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """A temp registry wired into both MCP servers' module globals."""
    database = EntityDatabase(str(tmp_path / "callers.db"))
    workspace_uuid = bootstrap_test_workspace(database, _WORKSPACE_LEGACY_ID)
    for server in (entity_server, workflow_state_server):
        monkeypatch.setattr(server, "_db", database)
        monkeypatch.setattr(server, "_db_unavailable", False)
        monkeypatch.setattr(server, "_workspace_uuid", workspace_uuid)
    # create_key_result resolves its bucket's workspace from the legacy
    # project id; the auto_id and issue_spawn paths use _workspace_uuid (C17).
    monkeypatch.setattr(entity_server, "_project_id", _WORKSPACE_LEGACY_ID)
    yield database, workspace_uuid
    database.close()


def _break_bucket(database: EntityDatabase, workspace_uuid: str, kind: str) -> str:
    """Leave one display-less, non-exempt entity in (kind, workspace) and a
    counter a successful allocation would advance. Returns its type_id."""
    slug = "lost"
    entity_uuid = database.register_entity(
        kind, seq=_OFFENDING_SEQ, slug=slug, name=slug, workspace_uuid=workspace_uuid)
    database._conn.execute("DELETE FROM entity_display WHERE uuid = ?", (entity_uuid,))
    database._conn.execute(
        "INSERT OR REPLACE INTO sequences(workspace_uuid, entity_type, next_val) "
        "VALUES(?,?,?)", (workspace_uuid, kind, _COUNTER_BEFORE))
    database._conn.commit()
    return f"{kind}:{_OFFENDING_SEQ:03d}-{slug}"


def _count_allocations(monkeypatch, database: EntityDatabase) -> list[tuple]:
    calls: list[tuple] = []
    allocate = database.next_sequence_value

    def counting_next_sequence_value(*args, **kwargs):
        calls.append((args, kwargs))
        return allocate(*args, **kwargs)

    monkeypatch.setattr(database, "next_sequence_value", counting_next_sequence_value)
    return calls


def _counter(database: EntityDatabase, workspace_uuid: str, kind: str) -> int | None:
    row = database._conn.execute(
        "SELECT next_val FROM sequences WHERE workspace_uuid = ? AND entity_type = ?",
        (workspace_uuid, kind)).fetchone()
    return None if row is None else row[0]


def _type_ids(database: EntityDatabase, kind: str) -> list[str]:
    return sorted(row[0] for row in database._conn.execute(
        "SELECT type_id FROM entities WHERE kind = ?", (kind,)))


@pytest.mark.asyncio
async def test_allocate_entity_id_returns_an_incomplete_bucket_envelope(registry, monkeypatch):
    database, workspace_uuid = registry
    offending = _break_bucket(database, workspace_uuid, "feature")
    allocations = _count_allocations(monkeypatch, database)

    envelope = json.loads(await entity_server.allocate_entity_id(
        entity_type="feature", name="Next Feature"))

    assert envelope["error"] is True
    assert envelope["error_type"] == "incomplete_bucket"
    assert offending in envelope["message"]
    assert "entity_display" in envelope["recovery_hint"]
    assert len(allocations) == 1
    assert _counter(database, workspace_uuid, "feature") == _COUNTER_BEFORE


@pytest.mark.asyncio
async def test_register_entity_auto_id_returns_the_envelope_and_registers_nothing(
    registry, monkeypatch
):
    database, workspace_uuid = registry
    offending = _break_bucket(database, workspace_uuid, "feature")
    allocations = _count_allocations(monkeypatch, database)

    envelope = json.loads(await entity_server.register_entity(
        entity_type="feature", name="Next Feature", auto_id=True))

    assert envelope["error"] is True
    assert envelope["error_type"] == "incomplete_bucket"
    assert offending in envelope["message"]
    assert _type_ids(database, "feature") == [offending]
    assert len(allocations) == 1
    assert _counter(database, workspace_uuid, "feature") == _COUNTER_BEFORE


@pytest.mark.asyncio
async def test_issue_spawn_returns_an_error_envelope_and_spawns_nothing(registry, monkeypatch):
    database, workspace_uuid = registry
    parent_uuid = database.register_entity(
        "feature", seq=1, slug="parent", name="parent", workspace_uuid=workspace_uuid)
    offending = _break_bucket(database, workspace_uuid, "task")
    allocations = _count_allocations(monkeypatch, database)

    envelope = json.loads(await entity_server.issue_spawn(
        parent_uuid=parent_uuid, kind="task", summary="Next task"))

    assert envelope["error"] is True
    assert envelope["error_type"] == "incompletebucketerror"
    assert offending in envelope["message"]
    assert _type_ids(database, "task") == [offending]
    assert len(allocations) == 1
    assert _counter(database, workspace_uuid, "task") == _COUNTER_BEFORE


@pytest.mark.asyncio
async def test_create_key_result_returns_the_refusal_as_its_error(registry, monkeypatch):
    database, workspace_uuid = registry
    database.register_entity(
        "objective", seq=1, slug="grow", name="Grow", workspace_uuid=workspace_uuid)
    offending = _break_bucket(database, workspace_uuid, "key_result")
    allocations = _count_allocations(monkeypatch, database)

    result = json.loads(await entity_server.create_key_result(
        parent_ref="objective:001-grow", name="Double revenue", metric_type="binary"))

    assert offending in result["error"]
    assert _type_ids(database, "key_result") == [offending]
    assert len(allocations) == 1
    assert _counter(database, workspace_uuid, "key_result") == _COUNTER_BEFORE


@pytest.mark.asyncio
async def test_promote_task_reports_the_refusal_not_invalid_input(registry, monkeypatch, tmp_path):
    """promote_task's wrapper maps ValueError to ``invalid_input`` with a hint
    about feature_ref and plan.md; neither is what went wrong here."""
    import workflow_engine.task_promotion as task_promotion

    database, workspace_uuid = registry
    feature_dir = tmp_path / "features" / "052-reactive"
    feature_dir.mkdir(parents=True)
    (feature_dir / "plan.md").write_text(_PLAN_MD)
    database.register_entity(
        "feature", seq=52, slug="reactive", name="Reactive", status="active",
        workspace_uuid=workspace_uuid, artifact_path=str(feature_dir))
    database.create_workflow_phase("feature:052-reactive", mode="standard",
                                   workflow_phase="implement")
    offending = _break_bucket(database, workspace_uuid, "task")
    monkeypatch.setattr(task_promotion, "_compute_legacy_project_id",
                        lambda *args, **kwargs: _WORKSPACE_LEGACY_ID)
    allocations = _count_allocations(monkeypatch, database)

    envelope = json.loads(await workflow_state_server.promote_task(
        feature_ref="feature:052-reactive", task_heading="Task 1.1: Add structured log fields"))

    assert envelope["error"] is True
    assert envelope["error_type"] == "incomplete_bucket"
    assert offending in envelope["message"]
    assert "entity_display" in envelope["recovery_hint"]
    assert _type_ids(database, "task") == [offending]
    assert len(allocations) == 1
    assert _counter(database, workspace_uuid, "task") == _COUNTER_BEFORE
