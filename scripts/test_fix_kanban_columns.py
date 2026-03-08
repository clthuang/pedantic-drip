"""Tests for the kanban column remediation script.

Verifies that fix_kanban_columns(conn) corrects kanban_column values
based on entity status: planned->backlog, active->wip,
completed/abandoned->completed. Orphaned workflow_phases rows
(no matching entity) are preserved as-is.
"""
from __future__ import annotations

import sqlite3

import pytest

from fix_kanban_columns import fix_kanban_columns

# ---------------------------------------------------------------------------
# Schema helpers — mirror production tables (migration 5 shape) without
# triggers or FTS to keep tests fast and focused.
# ---------------------------------------------------------------------------

_ENTITIES_DDL = """\
CREATE TABLE entities (
    uuid           TEXT NOT NULL PRIMARY KEY,
    type_id        TEXT NOT NULL UNIQUE,
    entity_type    TEXT NOT NULL CHECK(entity_type IN (
                       'backlog','brainstorm','project','feature')),
    entity_id      TEXT NOT NULL,
    name           TEXT NOT NULL,
    status         TEXT,
    parent_type_id TEXT,
    parent_uuid    TEXT,
    artifact_path  TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    metadata       TEXT
);
"""

_WORKFLOW_PHASES_DDL = """\
CREATE TABLE workflow_phases (
    type_id                    TEXT PRIMARY KEY
                               REFERENCES entities(type_id),
    workflow_phase             TEXT CHECK(workflow_phase IN (
                                   'brainstorm','specify','design',
                                   'create-plan','create-tasks',
                                   'implement','finish',
                                   'draft','reviewing','promoted','abandoned',
                                   'open','triaged','dropped'
                               ) OR workflow_phase IS NULL),
    kanban_column              TEXT NOT NULL DEFAULT 'backlog'
                               CHECK(kanban_column IN (
                                   'backlog','prioritised','wip',
                                   'agent_review','human_review',
                                   'blocked','documenting','completed'
                               )),
    last_completed_phase       TEXT CHECK(last_completed_phase IN (
                                   'brainstorm','specify','design',
                                   'create-plan','create-tasks',
                                   'implement','finish',
                                   'draft','reviewing','promoted','abandoned',
                                   'open','triaged','dropped'
                               ) OR last_completed_phase IS NULL),
    mode                       TEXT CHECK(mode IN ('standard', 'full')
                                   OR mode IS NULL),
    backward_transition_reason TEXT,
    updated_at                 TEXT NOT NULL
);
"""

NOW = "2026-03-09T00:00:00+00:00"


def _make_db() -> sqlite3.Connection:
    """Create an in-memory DB with production-shaped tables and test data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_ENTITIES_DDL)
    conn.executescript(_WORKFLOW_PHASES_DDL)

    # -- Entities --------------------------------------------------------
    entities = [
        ("uuid-001", "feature:001-planned", "feature", "001-planned",
         "Planned Feature", "planned", None, None, None, NOW, NOW, None),
        ("uuid-002", "feature:002-active", "feature", "002-active",
         "Active Feature", "active", None, None, None, NOW, NOW, None),
        ("uuid-003", "feature:003-completed", "feature", "003-completed",
         "Completed Feature", "completed", None, None, None, NOW, NOW, None),
        ("uuid-004", "feature:004-abandoned", "feature", "004-abandoned",
         "Abandoned Feature", "abandoned", None, None, None, NOW, NOW, None),
    ]
    conn.executemany(
        "INSERT INTO entities "
        "(uuid, type_id, entity_type, entity_id, name, status, "
        "parent_type_id, parent_uuid, artifact_path, created_at, "
        "updated_at, metadata) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        entities,
    )

    # -- Workflow phases (all start with kanban_column='backlog') ---------
    phases = [
        ("feature:001-planned", None, "backlog", None, None, None, NOW),
        ("feature:002-active", "implement", "backlog", None, "standard", None, NOW),
        ("feature:003-completed", "finish", "backlog", "finish", "standard", None, NOW),
        ("feature:004-abandoned", None, "backlog", None, None, None, NOW),
        # Orphaned: exists in workflow_phases but NOT in entities
        ("feature:005-orphaned", None, "backlog", None, None, None, NOW),
    ]
    # Commit pending transaction so PRAGMA change takes effect
    conn.commit()
    # Temporarily disable FK checks to insert the orphaned row
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executemany(
        "INSERT INTO workflow_phases "
        "(type_id, workflow_phase, kanban_column, last_completed_phase, "
        "mode, backward_transition_reason, updated_at) "
        "VALUES (?,?,?,?,?,?,?)",
        phases,
    )
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFixKanbanColumns:
    """Verify remediation corrects kanban_column based on entity status."""

    def _get_kanban(self, conn: sqlite3.Connection, type_id: str) -> str:
        row = conn.execute(
            "SELECT kanban_column FROM workflow_phases WHERE type_id = ?",
            (type_id,),
        ).fetchone()
        assert row is not None, f"No workflow_phases row for {type_id}"
        return row["kanban_column"]

    def test_planned_stays_backlog(self, db: sqlite3.Connection) -> None:
        assert self._get_kanban(db, "feature:001-planned") == "backlog"

    def test_active_becomes_wip(self, db: sqlite3.Connection) -> None:
        assert self._get_kanban(db, "feature:002-active") == "wip"

    def test_completed_becomes_completed(self, db: sqlite3.Connection) -> None:
        assert self._get_kanban(db, "feature:003-completed") == "completed"

    def test_abandoned_becomes_completed(self, db: sqlite3.Connection) -> None:
        assert self._get_kanban(db, "feature:004-abandoned") == "completed"

    def test_orphaned_preserved_backlog(self, db: sqlite3.Connection) -> None:
        assert self._get_kanban(db, "feature:005-orphaned") == "backlog"


@pytest.fixture
def db() -> sqlite3.Connection:
    """Provide a populated test DB after running the remediation."""
    conn = _make_db()
    fix_kanban_columns(conn)
    return conn


# ---------------------------------------------------------------------------
# Deepened tests
# ---------------------------------------------------------------------------


class TestFixKanbanColumnsDeepened:
    """Adversarial and mutation mindset tests for kanban remediation.

    derived_from: feature:036, dimension:adversarial, dimension:mutation_mindset
    """

    def _get_kanban(self, conn: sqlite3.Connection, type_id: str) -> str:
        row = conn.execute(
            "SELECT kanban_column FROM workflow_phases WHERE type_id = ?",
            (type_id,),
        ).fetchone()
        assert row is not None, f"No workflow_phases row for {type_id}"
        return row["kanban_column"]

    def test_remediation_idempotent_run_twice(self) -> None:
        """Running fix_kanban_columns twice produces the same result.

        Anticipate: If the SQL UPDATE has side effects beyond kanban_column
        (e.g., corrupting other fields on re-run), the second run would
        produce different results or errors.
        derived_from: dimension:adversarial (idempotency)
        """
        # Given a fresh DB
        conn = _make_db()

        # When we run remediation twice
        first_result = fix_kanban_columns(conn)
        second_result = fix_kanban_columns(conn)

        # Then the second run changes nothing (idempotent)
        # Note: rowcount may still report rows "updated" even if values
        # didn't change (SQLite behavior), so we verify actual values instead.
        assert self._get_kanban(conn, "feature:001-planned") == "backlog"
        assert self._get_kanban(conn, "feature:002-active") == "wip"
        assert self._get_kanban(conn, "feature:003-completed") == "completed"
        assert self._get_kanban(conn, "feature:004-abandoned") == "completed"
        assert self._get_kanban(conn, "feature:005-orphaned") == "backlog"

        conn.close()

    def test_remediation_only_updates_feature_entities(self) -> None:
        """Remediation SQL only targets 'feature:%' type_ids.

        Anticipate: If the WHERE clause is missing or too broad
        (e.g., just 'WHERE type_id LIKE "%"'), non-feature entities
        would be incorrectly updated.
        derived_from: dimension:adversarial (scope isolation)
        """
        # Given a DB with both feature and brainstorm workflow_phases rows
        conn = _make_db()

        # Add a brainstorm entity with a workflow_phases row
        conn.execute(
            "INSERT INTO entities "
            "(uuid, type_id, entity_type, entity_id, name, status, "
            "parent_type_id, parent_uuid, artifact_path, created_at, "
            "updated_at, metadata) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("uuid-bs-1", "brainstorm:idea-1", "brainstorm", "idea-1",
             "Test Idea", "draft", None, None, None, NOW, NOW, None),
        )
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            "INSERT INTO workflow_phases "
            "(type_id, workflow_phase, kanban_column, last_completed_phase, "
            "mode, backward_transition_reason, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            ("brainstorm:idea-1", "draft", "wip", None, None, None, NOW),
        )
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()

        # When remediation runs
        fix_kanban_columns(conn)

        # Then brainstorm entity kanban is unchanged ('wip' stays 'wip')
        assert self._get_kanban(conn, "brainstorm:idea-1") == "wip"

        # And feature entities are still correctly remediated
        assert self._get_kanban(conn, "feature:002-active") == "wip"
        assert self._get_kanban(conn, "feature:003-completed") == "completed"

        conn.close()
