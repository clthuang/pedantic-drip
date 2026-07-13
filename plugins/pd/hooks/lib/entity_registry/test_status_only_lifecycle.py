"""Status-only lifecycle tests for bug/task entities (feature 111 Group B).

Verifies AC-BL.1 through AC-BL.7:
  - AC-BL.1: ENTITY_MACHINES does NOT contain 'bug' or 'task' keys.
  - AC-BL.2: _KIND_TO_TYPE_LIFECYCLE['bug'] == ('work', 'bug_flow');
             _KIND_TO_TYPE_LIFECYCLE['task'] == ('work', 'task_flow').
  - AC-BL.3: _CLOSES_TERMINAL contents (3 keys + non-keys).
  - AC-BL.4: register_entity(entity_type='bug') → entities row has correct
             (type, kind, lifecycle_class, status); NO workflow_phases row.
  - AC-BL.5: Direct update_entity(bug_uuid, status='resolved') succeeds.
  - AC-BL.6: Closes path bypasses ENTITY_MACHINES (verified via design IF-7).
  - AC-BL.7: transition_entity_phase(type_id='bug:X', ...) raises ValueError
             with substring 'invalid_entity_type' AND 'bug'.

Also verifies AC-EX.1 — exception classes importable + subclass of ValueError.
AC-EX.2 (MCP envelope) lives in Group D's test_complete_phase_closes.py.
"""
from __future__ import annotations

import pytest

from entity_registry.database import EntityDatabase
from workflow_engine.router import (
    ENTITY_MACHINES,
    transition_entity_phase,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "entities.db")
    database = EntityDatabase(db_path)
    yield database
    database.close()


# ---------------------------------------------------------------------------
# AC-BL.1 — ENTITY_MACHINES does NOT contain 'bug' or 'task'
# ---------------------------------------------------------------------------


def test_ac_bl_1_entity_machines_does_not_contain_bug_or_task():
    """Per FR-BL.1 — bug and task are not lifecycle-GRAPH kinds: neither
    has an ENTITY_MACHINES entry (feature 123 — task IS machine-bearing via
    MACHINE_REGISTRY's FiveDMachine, but ENTITY_MACHINES itself stays
    scoped to brainstorm/backlog only; bug remains the sole machine-less
    kind, spec FR123-5)."""
    assert "bug" not in ENTITY_MACHINES
    assert "task" not in ENTITY_MACHINES


# ---------------------------------------------------------------------------
# AC-BL.2 — _KIND_TO_TYPE_LIFECYCLE rows for bug + task
# ---------------------------------------------------------------------------


def test_ac_bl_2_kind_to_type_lifecycle_for_bug_and_task():
    from entity_registry.database import _KIND_TO_TYPE_LIFECYCLE

    assert _KIND_TO_TYPE_LIFECYCLE["bug"] == ("work", "bug_flow")
    assert _KIND_TO_TYPE_LIFECYCLE["task"] == ("work", "task_flow")


# ---------------------------------------------------------------------------
# AC-BL.3 — _CLOSES_TERMINAL contents
# ---------------------------------------------------------------------------


def test_ac_bl_3_closes_terminal_contents():
    from entity_registry.database import _CLOSES_TERMINAL

    assert _CLOSES_TERMINAL["bug_flow"] == "closed"
    assert _CLOSES_TERMINAL["task_flow"] == "closed"
    assert _CLOSES_TERMINAL["work_flow"] == "dropped"

    # Negative: features and other flows are NOT in the dict (raise on closure).
    assert "feature_flow" not in _CLOSES_TERMINAL
    assert "brainstorm_flow" not in _CLOSES_TERMINAL
    assert "container_flow" not in _CLOSES_TERMINAL


# ---------------------------------------------------------------------------
# AC-BL.4 — register_entity(entity_type='bug') → entities row triple + no
#           workflow_phases row.
# ---------------------------------------------------------------------------


def test_ac_bl_4_register_bug_no_workflow_phases(db):
    """register_entity(entity_type='bug', status='open') creates entities
    row with (work, bug, bug_flow, 'open'); NO workflow_phases row.
    """
    db.register_entity(
        entity_type="bug",
        entity_id="1-foo",
        name="A bug",
        status="open",
        project_id="__unknown__",
    )

    row = db._conn.execute(
        "SELECT type, kind, lifecycle_class, status FROM entities "
        "WHERE type_id='bug:1-foo'"
    ).fetchone()
    assert row is not None
    assert row["type"] == "work"
    assert row["kind"] == "bug"
    assert row["lifecycle_class"] == "bug_flow"
    assert row["status"] == "open"

    # No workflow_phases row should exist (status-only model).
    wp_rows = db._conn.execute(
        "SELECT type_id FROM workflow_phases WHERE type_id='bug:1-foo'"
    ).fetchall()
    assert wp_rows == []


# ---------------------------------------------------------------------------
# AC-BL.5 — Direct update_entity(bug, status='resolved') succeeds.
# ---------------------------------------------------------------------------


def test_ac_bl_5_direct_update_entity_status(db):
    """entities.status has no CHECK; direct update accepts any string."""
    db.register_entity(
        entity_type="bug",
        entity_id="2-bar",
        name="Another bug",
        status="open",
        project_id="__unknown__",
    )

    db.update_entity("bug:2-bar", status="resolved", project_id="__unknown__")

    row = db._conn.execute(
        "SELECT status FROM entities WHERE type_id='bug:2-bar'"
    ).fetchone()
    assert row["status"] == "resolved"

    # No workflow_phases write triggered.
    wp_rows = db._conn.execute(
        "SELECT type_id FROM workflow_phases WHERE type_id='bug:2-bar'"
    ).fetchall()
    assert wp_rows == []


# ---------------------------------------------------------------------------
# AC-BL.6 — Direct status='closed' write on a bug succeeds; no workflow_phases
#           row gained. (closes= path verified end-to-end in Group D tests;
#           here we exercise the status-only update path that closes= relies on.)
# ---------------------------------------------------------------------------


def test_ac_bl_6_status_only_close_does_not_create_workflow_phases(db):
    db.register_entity(
        entity_type="bug",
        entity_id="3-baz",
        name="Close-me bug",
        status="open",
        project_id="__unknown__",
    )

    db.update_entity("bug:3-baz", status="closed", project_id="__unknown__")

    row = db._conn.execute(
        "SELECT status FROM entities WHERE type_id='bug:3-baz'"
    ).fetchone()
    assert row["status"] == "closed"

    wp_rows = db._conn.execute(
        "SELECT type_id FROM workflow_phases WHERE type_id='bug:3-baz'"
    ).fetchall()
    assert wp_rows == []


# ---------------------------------------------------------------------------
# AC-BL.7 — transition_entity_phase(type_id='bug:X', ...) raises ValueError
#           with substring 'invalid_entity_type' AND 'bug'.
# ---------------------------------------------------------------------------


def test_ac_bl_7_transition_entity_phase_rejects_bug(db):
    # Register the bug first (CHECK widening from Migration 14 must be in
    # place so the INSERT succeeds; Group A established this).
    db.register_entity(
        entity_type="bug",
        entity_id="4-defensive",
        name="Defensive raise check",
        status="open",
        project_id="__unknown__",
    )

    with pytest.raises(ValueError) as excinfo:
        transition_entity_phase(db, "bug:4-defensive", "resolved")
    msg = str(excinfo.value)
    assert "invalid_entity_type" in msg
    assert "bug" in msg


# ---------------------------------------------------------------------------
# AC-EX.1 — Exception classes importable + subclass of ValueError
# ---------------------------------------------------------------------------


def test_ac_ex_1_exception_classes_importable_and_subclass_value_error():
    from entity_registry.database import (
        EntityNotFoundError,
        InvalidCloseTargetError,
    )

    assert issubclass(EntityNotFoundError, ValueError)
    assert issubclass(InvalidCloseTargetError, ValueError)

    # Smoke: instantiation works with a message arg.
    err1 = EntityNotFoundError("not found")
    err2 = InvalidCloseTargetError("bad target")
    assert isinstance(err1, ValueError)
    assert isinstance(err2, ValueError)
    assert "not found" in str(err1)
    assert "bad target" in str(err2)
