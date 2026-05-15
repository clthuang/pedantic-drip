"""Tests for the F9 ``issue_spawn`` MCP tool (feature 111 Group C).

Verifies AC-9.1 through AC-9.9 from
``docs/features/111-issue-lifecycle-closure/spec.md`` rev 3.5.

The MCP tool lives in ``entity_server.py``. It spawns a new ``kind='bug'`` or
``kind='task'`` work entity linked to a parent (feature/backlog/project) and
appends a ``spawned_child`` phase_event on the parent without mutating the
parent's ``workflow_phase`` or ``kanban_column`` (AC-9.2 — column-level
invariance).

The tests follow the existing patterns in ``test_workflow_state_server.py``
(in-memory ``EntityDatabase`` + module-global swap for ``entity_server._db``).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys

import pytest

# Make hooks/lib importable for the database + entity_registry imports the
# tests use directly.
_hooks_lib = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "hooks", "lib")
)
if _hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _hooks_lib)

# Make sibling mcp modules importable so ``import entity_server`` works.
_mcp_dir = os.path.dirname(__file__)
if _mcp_dir not in sys.path:
    sys.path.insert(0, _mcp_dir)

import entity_server  # noqa: E402

from entity_registry.database import EntityDatabase  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine synchronously (mirrors test_export_entities)."""
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _strict_id_format_for_entity_display(monkeypatch):
    """Force strict id-format mode so register_entity populates entity_display.

    The MCP conftest defaults ``PD_REGISTER_ENTITY_STRICT_ID_FORMAT=0`` for
    legacy fixture compatibility, but ``issue_spawn``'s auto_id path always
    produces conformant ``{seq:03d}-{slug}`` ids. Strict mode is the
    production code path AC-9.7 (entity_display 1:1) exercises.
    """
    monkeypatch.setenv("PD_REGISTER_ENTITY_STRICT_ID_FORMAT", "1")


@pytest.fixture(autouse=True)
def _reset_entity_server_globals():
    """Save / restore ``entity_server`` module globals per test."""
    saved_db = entity_server._db
    saved_unavailable = entity_server._db_unavailable
    saved_project_id = entity_server._project_id
    saved_workspace_uuid = entity_server._workspace_uuid
    try:
        yield
    finally:
        entity_server._db = saved_db
        entity_server._db_unavailable = saved_unavailable
        entity_server._project_id = saved_project_id
        entity_server._workspace_uuid = saved_workspace_uuid


@pytest.fixture
def db():
    """In-memory ``EntityDatabase`` with all migrations applied."""
    return EntityDatabase(":memory:")


@pytest.fixture
def parent_feature(db):
    """Register a feature parent with a workflow_phases row.

    Returns the parent's resolved (uuid, type_id) tuple. The workflow_phases
    row is at phase='implement', kanban_column='wip' — AC-9.2 asserts these
    are unchanged after ``issue_spawn``.
    """
    db.register_entity(
        "feature",
        "111-issue-lifecycle-closure",
        "Issue Lifecycle Closure",
        status="active",
        project_id="__unknown__",
    )
    db.create_workflow_phase(
        "feature:111-issue-lifecycle-closure",
        workflow_phase="implement",
    )
    row = db.get_entity("feature:111-issue-lifecycle-closure")
    return row["uuid"], row["type_id"]


@pytest.fixture
def server(db):
    """Install ``db`` as ``entity_server._db`` so MCP tools resolve it."""
    entity_server._db = db
    entity_server._db_unavailable = False
    entity_server._project_id = "__unknown__"
    entity_server._workspace_uuid = ""
    return entity_server


# ---------------------------------------------------------------------------
# AC-9.1 — happy path: kind='bug' creates entity, returns uuid
# ---------------------------------------------------------------------------


class TestAC91HappyPath:
    """AC-9.1: bug entity created with correct (type, kind, lifecycle_class)
    triple, status='open', parent_uuid set, entity_id matches ``^\\d+-foo$``.
    """

    def test_bug_entity_created_with_triple(self, server, db, parent_feature):
        parent_uuid, _ = parent_feature
        result_json = _run(server.issue_spawn(
            parent_uuid=parent_uuid,
            kind="bug",
            summary="Foo",
        ))
        result = json.loads(result_json)
        assert "uuid" in result, f"missing uuid in response: {result}"
        new_uuid = result["uuid"]

        row = db._conn.execute(
            "SELECT type, kind, lifecycle_class, status, parent_uuid, "
            "entity_id "
            "FROM entities WHERE uuid = ?",
            (new_uuid,),
        ).fetchone()
        assert row is not None
        assert row["type"] == "work"
        assert row["kind"] == "bug"
        assert row["lifecycle_class"] == "bug_flow"
        assert row["status"] == "open"
        assert row["parent_uuid"] == parent_uuid
        # AC-9.1 + AC-9.6: entity_id matches ^\d+-foo$ (slug from summary)
        assert re.match(r"^\d+-foo$", row["entity_id"]), (
            f"entity_id={row['entity_id']!r} does not match ^\\d+-foo$"
        )

    def test_task_entity_created_with_triple(self, server, db, parent_feature):
        parent_uuid, _ = parent_feature
        result_json = _run(server.issue_spawn(
            parent_uuid=parent_uuid,
            kind="task",
            summary="Wire up MCP",
        ))
        result = json.loads(result_json)
        new_uuid = result["uuid"]
        row = db._conn.execute(
            "SELECT type, kind, lifecycle_class, status FROM entities "
            "WHERE uuid = ?",
            (new_uuid,),
        ).fetchone()
        assert row["type"] == "work"
        assert row["kind"] == "task"
        assert row["lifecycle_class"] == "task_flow"
        assert row["status"] == "open"


# ---------------------------------------------------------------------------
# AC-9.2 — parent's workflow_phase / kanban_column column-level invariance
# ---------------------------------------------------------------------------


class TestAC92ColumnLevelInvariance:
    """AC-9.2: parent's (workflow_phase, kanban_column) tuple unchanged.

    NB: updated_at is NOT asserted (may tick via triggers).
    """

    def test_parent_workflow_columns_unchanged(self, server, db, parent_feature):
        parent_uuid, parent_type_id = parent_feature
        before = db._conn.execute(
            "SELECT workflow_phase, kanban_column FROM workflow_phases "
            "WHERE type_id = ?",
            (parent_type_id,),
        ).fetchone()
        before_tuple = (before["workflow_phase"], before["kanban_column"])

        _run(server.issue_spawn(
            parent_uuid=parent_uuid,
            kind="bug",
            summary="Foo",
        ))

        after = db._conn.execute(
            "SELECT workflow_phase, kanban_column FROM workflow_phases "
            "WHERE type_id = ?",
            (parent_type_id,),
        ).fetchone()
        after_tuple = (after["workflow_phase"], after["kanban_column"])
        assert before_tuple == after_tuple, (
            f"AC-9.2 violation: parent ({parent_type_id}) workflow columns "
            f"changed from {before_tuple} to {after_tuple}"
        )


# ---------------------------------------------------------------------------
# AC-9.3 — exactly one spawned_child phase_event on parent
# ---------------------------------------------------------------------------


class TestAC93SpawnedChildEvent:
    """AC-9.3: exactly 1 phase_event with event_type='spawned_child',
    phase IS NULL, metadata contains child_uuid / child_kind / child_name.
    """

    def test_exactly_one_spawned_child_event(self, server, db, parent_feature):
        parent_uuid, parent_type_id = parent_feature
        result = json.loads(_run(server.issue_spawn(
            parent_uuid=parent_uuid,
            kind="bug",
            summary="Foo",
        )))
        new_uuid = result["uuid"]

        rows = db._conn.execute(
            "SELECT phase, event_type, metadata FROM phase_events "
            "WHERE type_id = ? AND event_type = 'spawned_child'",
            (parent_type_id,),
        ).fetchall()
        assert len(rows) == 1, (
            f"expected exactly 1 spawned_child event, got {len(rows)}"
        )
        ev = rows[0]
        assert ev["phase"] is None, f"phase should be NULL, got {ev['phase']!r}"
        meta = json.loads(ev["metadata"])
        assert meta.get("child_uuid") == new_uuid
        assert meta.get("child_kind") == "bug"
        assert meta.get("child_name") == "Foo"


# ---------------------------------------------------------------------------
# AC-9.4 — invalid kind translated to JSON error envelope BEFORE any DB write
# ---------------------------------------------------------------------------


class TestAC94InvalidKind:
    """AC-9.4 + FR-EX.3: kind='nonsense' produces a JSON error envelope
    at the MCP boundary (via ``_catch_issue_spawn_errors``);
    entities + phase_events row counts are byte-identical pre/post.
    """

    def test_invalid_kind_returns_error_envelope_no_partial_state(
        self, server, db, parent_feature
    ):
        parent_uuid, _ = parent_feature
        entities_before = db._conn.execute(
            "SELECT COUNT(*) FROM entities"
        ).fetchone()[0]
        events_before = db._conn.execute(
            "SELECT COUNT(*) FROM phase_events"
        ).fetchone()[0]

        # FR-EX.3 envelope: {"error": true, "error_type":"valueerror",
        # "message": "invalid_kind: ..."}.
        result_raw = _run(server.issue_spawn(
            parent_uuid=parent_uuid,
            kind="nonsense",
            summary="Foo",
        ))
        data = json.loads(result_raw)
        assert data.get("error") is True, f"expected error envelope, got {data!r}"
        assert data.get("error_type") == "valueerror", (
            f"expected error_type='valueerror', got {data!r}"
        )
        assert "invalid_kind" in data.get("message", ""), (
            f"expected 'invalid_kind' in message, got {data!r}"
        )

        entities_after = db._conn.execute(
            "SELECT COUNT(*) FROM entities"
        ).fetchone()[0]
        events_after = db._conn.execute(
            "SELECT COUNT(*) FROM phase_events"
        ).fetchone()[0]
        assert entities_before == entities_after, (
            f"entities row count changed: {entities_before} → {entities_after}"
        )
        assert events_before == events_after, (
            f"phase_events row count changed: {events_before} → {events_after}"
        )


# ---------------------------------------------------------------------------
# AC-9.5 — invalid parent_uuid / disallowed parent kind / cross-workspace
# ---------------------------------------------------------------------------


class TestAC95ParentValidation:
    """AC-9.5 + FR-9.6 + FR-EX.3: non-existent parent →
    ``entitynotfounderror`` envelope with ``parent_not_found`` substring;
    disallowed parent kind → ``valueerror`` envelope with
    ``invalid_parent_kind`` substring; cross-workspace parent →
    ``valueerror`` envelope with ``cross-workspace parent forbidden``
    substring (design IF-1 step 5b).
    """

    def test_nonexistent_parent_returns_error_envelope(self, server, db):
        # The DB has no parent registered — any uuid is a miss.
        result_raw = _run(server.issue_spawn(
            parent_uuid="00000000-0000-0000-0000-000000000000",
            kind="bug",
            summary="Foo",
        ))
        data = json.loads(result_raw)
        assert data.get("error") is True, f"expected error envelope, got {data!r}"
        # EntityNotFoundError → 'entitynotfounderror' (FR-EX.3 lowercased class name).
        assert data.get("error_type") == "entitynotfounderror", (
            f"expected error_type='entitynotfounderror', got {data!r}"
        )
        assert "parent_not_found" in data.get("message", ""), (
            f"expected 'parent_not_found' in message, got {data!r}"
        )

    def test_disallowed_parent_kind_returns_error_envelope(self, server, db):
        # Register a brainstorm entity as the "parent" — disallowed kind.
        db.register_entity(
            "brainstorm",
            "001-bs-fixture",
            "Brainstorm Fixture",
            status="active",
            project_id="__unknown__",
        )
        bs = db.get_entity("brainstorm:001-bs-fixture")
        result_raw = _run(server.issue_spawn(
            parent_uuid=bs["uuid"],
            kind="bug",
            summary="Foo",
        ))
        data = json.loads(result_raw)
        assert data.get("error") is True
        assert data.get("error_type") == "valueerror"
        assert "invalid_parent_kind" in data.get("message", "")

    def test_cross_workspace_parent_returns_error_envelope(
        self, server, db, tmp_path, monkeypatch
    ):
        """AC-9.5 extension + FR-9.6 cross-workspace gate (design IF-1
        step 5b).

        Create the parent feature in workspace_B; the caller is in
        __unknown__ (default fixture). The call must (a) return a JSON
        error envelope and (b) leave entities + phase_events row counts
        byte-identical.
        """
        # Set up a SECOND workspace (mirrors test_complete_phase_closes.py
        # AC-10.6 pattern at :393).
        import uuid as _uuid
        ws_b_uuid = str(_uuid.uuid4())
        now = db._now_iso()
        db._conn.execute(
            "INSERT INTO workspaces "
            "(uuid, project_id_legacy, project_root, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (ws_b_uuid, "ws-b-legacy", str(tmp_path / "ws_b"), now, now),
        )

        # Register a feature parent inside workspace_B.
        parent_uuid_ws_b = db.register_entity(
            entity_type="feature",
            entity_id="222-foreign-feature",
            name="Foreign Feature",
            status="active",
            workspace_uuid=ws_b_uuid,
        )

        # Caller is in __unknown__ workspace (server fixture set
        # _workspace_uuid=""), so resolved caller workspace will be
        # _UNKNOWN_WORKSPACE_UUID — different from ws_b_uuid.
        entities_before = db._conn.execute(
            "SELECT COUNT(*) FROM entities WHERE kind = 'bug'"
        ).fetchone()[0]
        events_before = db._conn.execute(
            "SELECT COUNT(*) FROM phase_events "
            "WHERE event_type = 'spawned_child'"
        ).fetchone()[0]

        result_raw = _run(server.issue_spawn(
            parent_uuid=parent_uuid_ws_b,
            kind="bug",
            summary="Should not be created",
        ))
        data = json.loads(result_raw)
        assert data.get("error") is True, (
            f"expected error envelope, got {data!r}"
        )
        assert data.get("error_type") == "valueerror", (
            f"expected error_type='valueerror', got {data!r}"
        )
        assert "cross-workspace parent forbidden" in data.get("message", ""), (
            f"expected 'cross-workspace parent forbidden' in message, got "
            f"{data!r}"
        )

        # No partial state: bug count unchanged, no spawned_child event.
        entities_after = db._conn.execute(
            "SELECT COUNT(*) FROM entities WHERE kind = 'bug'"
        ).fetchone()[0]
        events_after = db._conn.execute(
            "SELECT COUNT(*) FROM phase_events "
            "WHERE event_type = 'spawned_child'"
        ).fetchone()[0]
        assert entities_before == entities_after, (
            f"bug entity count changed: {entities_before} → {entities_after}"
        )
        assert events_before == events_after, (
            f"spawned_child event count changed: "
            f"{events_before} → {events_after}"
        )

    def test_no_partial_state_on_parent_not_found(
        self, server, db, parent_feature
    ):
        # Even with a real workspace + a real feature already registered,
        # the failing call must not write anything.
        entities_before = db._conn.execute(
            "SELECT COUNT(*) FROM entities"
        ).fetchone()[0]
        events_before = db._conn.execute(
            "SELECT COUNT(*) FROM phase_events"
        ).fetchone()[0]
        result_raw = _run(server.issue_spawn(
            parent_uuid="00000000-0000-0000-0000-000000000000",
            kind="bug",
            summary="Bar",
        ))
        data = json.loads(result_raw)
        assert data.get("error") is True
        assert "parent_not_found" in data.get("message", "")
        entities_after = db._conn.execute(
            "SELECT COUNT(*) FROM entities"
        ).fetchone()[0]
        events_after = db._conn.execute(
            "SELECT COUNT(*) FROM phase_events"
        ).fetchone()[0]
        assert entities_before == entities_after
        assert events_before == events_after


# ---------------------------------------------------------------------------
# AC-9.6 — entity_id matches ^\d+-.+
# ---------------------------------------------------------------------------


class TestAC96EntityIdFormat:
    def test_entity_id_matches_strict_format(
        self, server, db, parent_feature
    ):
        parent_uuid, _ = parent_feature
        result = json.loads(_run(server.issue_spawn(
            parent_uuid=parent_uuid,
            kind="task",
            summary="Hello world Foo",
        )))
        row = db._conn.execute(
            "SELECT entity_id FROM entities WHERE uuid = ?",
            (result["uuid"],),
        ).fetchone()
        assert re.match(r"^\d+-.+", row["entity_id"]), (
            f"entity_id={row['entity_id']!r} does not match strict format"
        )


# ---------------------------------------------------------------------------
# AC-9.7 — entity_display 1:1 invariant
# ---------------------------------------------------------------------------


class TestAC97EntityDisplayInvariant:
    """AC-9.7: entity_display has exactly 1 row for the new uuid with
    non-null seq + slug.
    """

    def test_entity_display_row_exists(self, server, db, parent_feature):
        parent_uuid, _ = parent_feature
        result = json.loads(_run(server.issue_spawn(
            parent_uuid=parent_uuid,
            kind="bug",
            summary="Foo",
        )))
        new_uuid = result["uuid"]

        count = db._conn.execute(
            "SELECT COUNT(*) FROM entity_display WHERE uuid = ?",
            (new_uuid,),
        ).fetchone()[0]
        assert count == 1, (
            f"AC-9.7 violation: entity_display row count = {count} for "
            f"uuid={new_uuid!r}; expected 1"
        )
        # display_seq + display_slug must be non-null.
        row = db._conn.execute(
            "SELECT seq, slug FROM entity_display WHERE uuid = ?",
            (new_uuid,),
        ).fetchone()
        assert row["seq"] is not None
        assert isinstance(row["seq"], int)
        assert row["slug"] is not None
        assert isinstance(row["slug"], str)
        assert row["slug"] != ""


# ---------------------------------------------------------------------------
# AC-9.8 — doctor check_status_write_path passes on entity_server.py
# ---------------------------------------------------------------------------


class TestAC98DoctorCheckPasses:
    """AC-9.8: ``check_status_write_path`` doctor check passes on the
    ``entity_server.py`` source after ``issue_spawn`` lands. The check is
    AST-based and flags direct phase_events INSERT / direct entities.status
    UPDATE outside the sealed path.
    """

    def test_check_status_write_path_returns_no_violations(self):
        from doctor.check_status_write_path import check_status_write_path

        result = check_status_write_path()
        # CheckResult model: has .status (or similar). Issues list should be
        # empty for entity_server.py specifically (we tolerate pre-existing
        # warnings in other files but verify the new code doesn't add any).
        issues = getattr(result, "issues", []) or []
        entity_server_issues = [
            i for i in issues
            if "entity_server.py" in (
                getattr(i, "file", "") or getattr(i, "path", "") or str(i)
            )
        ]
        assert not entity_server_issues, (
            f"check_status_write_path violations in entity_server.py: "
            f"{entity_server_issues}"
        )


# ---------------------------------------------------------------------------
# AC-9.9 — metadata shallow merge with system keys winning
# ---------------------------------------------------------------------------


class TestAC99MetadataShallowMerge:
    """AC-9.9: caller-supplied metadata is shallow-merged; system-supplied
    keys win — caller's ``parent_uuid`` key is dropped because parent
    linkage lives in the entities.parent_uuid column, NOT in metadata.
    """

    def test_severity_preserved_parent_uuid_dropped(
        self, server, db, parent_feature
    ):
        parent_uuid, _ = parent_feature
        result = json.loads(_run(server.issue_spawn(
            parent_uuid=parent_uuid,
            kind="bug",
            summary="Foo",
            metadata={"severity": "high", "parent_uuid": "evil"},
        )))
        new_uuid = result["uuid"]
        row = db._conn.execute(
            "SELECT metadata, parent_uuid FROM entities WHERE uuid = ?",
            (new_uuid,),
        ).fetchone()
        # parent_uuid column has the real parent, NOT 'evil'.
        assert row["parent_uuid"] == parent_uuid
        # entities.metadata JSON has severity but NOT a parent_uuid key.
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        assert meta.get("severity") == "high", (
            f"caller-supplied severity not preserved: {meta!r}"
        )
        assert "parent_uuid" not in meta, (
            f"caller-supplied parent_uuid key leaked into entities.metadata: "
            f"{meta!r}"
        )
