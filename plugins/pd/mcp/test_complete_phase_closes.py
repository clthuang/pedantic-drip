"""Tests for feature 111 F10 — ``complete_phase(closes=[uuid...])`` atomic closure.

Verifies all AC-10.1 through AC-10.11 plus AC-EX.2 (MCP error envelope).

Setup pattern: each test uses an in-memory ``EntityDatabase``, sets the
module-level ``_workspace_uuid`` to the canonical unknown-workspace UUID
(matching ``project_id='__unknown__'`` registrations), and drives
``_process_complete_phase`` directly via the existing seeded-engine fixture
pattern from ``test_workflow_state_server.py``.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

# Ensure hooks/lib is on path for imports (mirrors test_workflow_state_server.py).
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in sys.path:
    sys.path.insert(0, _hooks_lib)

from entity_registry.database import (
    EntityDatabase,
    _UNKNOWN_WORKSPACE_UUID,
)
from workflow_engine.engine import WorkflowStateEngine
from workflow_engine.entity_engine import EntityWorkflowEngine

import workflow_state_server as wss
from workflow_state_server import _process_complete_phase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_module_globals():
    """Save and restore workflow_state_server module globals per test."""
    saved_db = wss._db
    saved_unavailable = wss._db_unavailable
    saved_project_id = wss._project_id
    saved_workspace_uuid = wss._workspace_uuid
    try:
        yield
    finally:
        wss._db = saved_db
        wss._db_unavailable = saved_unavailable
        wss._project_id = saved_project_id
        wss._workspace_uuid = saved_workspace_uuid


@pytest.fixture
def db():
    """In-memory database with all migrations applied (incl. Migration 14)."""
    return EntityDatabase(":memory:")


@pytest.fixture
def engine(db, tmp_path):
    return WorkflowStateEngine(db, str(tmp_path))


@pytest.fixture
def entity_engine(db, tmp_path):
    """Entity workflow engine for cascade routing."""
    from workflow_engine.notifications import NotificationQueue
    return EntityWorkflowEngine(
        db, str(tmp_path), NotificationQueue(), project_root=str(tmp_path)
    )


@pytest.fixture
def seeded(db, engine, entity_engine, tmp_path):
    """Seed a feature at workflow_phase='finish' so complete_phase('finish')
    succeeds (re-invocations stay at finish — terminal phase). Sets
    workflow_state_server._workspace_uuid to _UNKNOWN_WORKSPACE_UUID so F10's
    caller resolution matches features registered with project_id='__unknown__'.
    """
    db.register_entity(
        "feature", "111-closer", "Feature 111 closer test",
        status="active", project_id="__unknown__",
    )
    db.create_workflow_phase("feature:111-closer", workflow_phase="finish")

    # Build the on-disk .meta.json the engine expects for projection.
    feat_dir = os.path.join(str(tmp_path), "features", "111-closer")
    os.makedirs(feat_dir, exist_ok=True)
    with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
        f.write('{"id": "111", "slug": "closer", "status": "active", "mode": "standard"}')

    # Wire module globals so _process_complete_phase sees the right workspace.
    wss._db = db
    wss._db_unavailable = False
    wss._workspace_uuid = _UNKNOWN_WORKSPACE_UUID
    wss._project_id = "__unknown__"

    return {"db": db, "engine": engine, "entity_engine": entity_engine,
            "feature_type_id": "feature:111-closer"}


def _register_bug(db, entity_id: str, name: str = "A bug",
                  project_id: str = "__unknown__", status: str = "open") -> str:
    """Register a bug entity; returns its uuid."""
    return db.register_entity(
        entity_type="bug",
        entity_id=entity_id,
        name=name,
        status=status,
        project_id=project_id,
    )


def _register_task(db, entity_id: str, name: str = "A task",
                   project_id: str = "__unknown__", status: str = "open") -> str:
    return db.register_entity(
        entity_type="task",
        entity_id=entity_id,
        name=name,
        status=status,
        project_id=project_id,
    )


def _register_backlog(db, entity_id: str, name: str = "A backlog item",
                      project_id: str = "__unknown__", status: str = "open") -> str:
    return db.register_entity(
        entity_type="backlog",
        entity_id=entity_id,
        name=name,
        status=status,
        project_id=project_id,
    )


def _get_uuid(db, type_id: str) -> str:
    """Resolve type_id to uuid via the entities table."""
    row = db._conn.execute(
        "SELECT uuid FROM entities WHERE type_id = ?", (type_id,),
    ).fetchone()
    assert row is not None, f"Entity not found: {type_id}"
    return row["uuid"]


# ---------------------------------------------------------------------------
# AC-EX.2 — MCP error envelope for nonexistent caller (relocated from B.3)
# ---------------------------------------------------------------------------


class TestAcEx2EnvelopeNonexistentCaller:
    def test_returns_entitynotfounderror_envelope(self, seeded):
        u = _register_bug(seeded["db"], "1-foo")
        result = _process_complete_phase(
            seeded["engine"], "feature:nonexistent", "finish",
            db=seeded["db"], entity_engine=seeded["entity_engine"],
            closes=[u],
        )
        data = json.loads(result)
        assert data.get("error") is True, f"expected error envelope; got {data}"
        assert data["error_type"] == "entitynotfounderror", (
            f"expected error_type=entitynotfounderror; got {data['error_type']}"
        )
        assert "caller not registered" in data["message"] or "not found" in data["message"].lower()


# ---------------------------------------------------------------------------
# AC-10.1 — closes=[u_bug, u_task] transitions feature + closes both + 2 rows
# ---------------------------------------------------------------------------


class TestAc10_1AtomicClosureTwoUuids:
    def test_feature_finishes_and_two_relations_persisted(self, seeded):
        db = seeded["db"]
        u_bug = _register_bug(db, "1-bug-a")
        u_task = _register_task(db, "2-task-a")

        result = _process_complete_phase(
            seeded["engine"], seeded["feature_type_id"], "finish",
            db=db, entity_engine=seeded["entity_engine"],
            closes=[u_bug, u_task],
        )
        data = json.loads(result)
        assert "error" not in data, f"expected success; got {data}"
        assert set(data.get("closes_applied", [])) == {u_bug, u_task}

        # Bug + task both transitioned to 'closed'
        bug_row = db._conn.execute(
            "SELECT status FROM entities WHERE uuid = ?", (u_bug,)
        ).fetchone()
        task_row = db._conn.execute(
            "SELECT status FROM entities WHERE uuid = ?", (u_task,)
        ).fetchone()
        assert bug_row["status"] == "closed"
        assert task_row["status"] == "closed"

        # 2 entity_relations rows from the feature
        feature_uuid = _get_uuid(db, seeded["feature_type_id"])
        rel_count = db._conn.execute(
            "SELECT COUNT(*) FROM entity_relations "
            "WHERE from_uuid=? AND kind='fixes'", (feature_uuid,)
        ).fetchone()[0]
        assert rel_count == 2


# ---------------------------------------------------------------------------
# AC-10.2 — no closes → closes_applied=[]
# ---------------------------------------------------------------------------


class TestAc10_2EmptyClosesAppliedWithoutCloses:
    def test_closes_none_returns_empty_list(self, seeded):
        result = _process_complete_phase(
            seeded["engine"], seeded["feature_type_id"], "finish",
            db=seeded["db"], entity_engine=seeded["entity_engine"],
        )
        data = json.loads(result)
        assert "error" not in data
        assert data.get("closes_applied") == []

    def test_closes_empty_list_returns_empty_list(self, seeded):
        result = _process_complete_phase(
            seeded["engine"], seeded["feature_type_id"], "finish",
            db=seeded["db"], entity_engine=seeded["entity_engine"],
            closes=[],
        )
        data = json.loads(result)
        assert "error" not in data
        assert data.get("closes_applied") == []


# ---------------------------------------------------------------------------
# AC-10.3 — atomic rollback when one closes-uuid fails lifecycle check
# ---------------------------------------------------------------------------


class TestAc10_3AtomicRollbackOnInvalidTarget:
    def test_feature_in_closes_rolls_back_everything(self, seeded):
        db = seeded["db"]
        u_bug = _register_bug(db, "3-keep-open")

        # Register a sibling feature; lifecycle_class='feature_flow' → not closable.
        u_other_feature = db.register_entity(
            "feature", "111-sibling", "Sibling feature",
            status="active", project_id="__unknown__",
        )

        # Capture state before invocation.
        bug_before = db._conn.execute(
            "SELECT status FROM entities WHERE uuid = ?", (u_bug,)
        ).fetchone()["status"]

        feature_uuid = _get_uuid(db, seeded["feature_type_id"])
        phase_before = db._conn.execute(
            "SELECT workflow_phase FROM workflow_phases WHERE type_id = ?",
            (seeded["feature_type_id"],),
        ).fetchone()["workflow_phase"]

        result = _process_complete_phase(
            seeded["engine"], seeded["feature_type_id"], "finish",
            db=db, entity_engine=seeded["entity_engine"],
            closes=[u_bug, u_other_feature],
        )
        data = json.loads(result)
        assert data.get("error") is True, f"expected failure; got {data}"
        assert data["error_type"] == "invalidclosetargeterror"

        # Bug status unchanged
        bug_after = db._conn.execute(
            "SELECT status FROM entities WHERE uuid = ?", (u_bug,)
        ).fetchone()["status"]
        assert bug_after == bug_before == "open"

        # No entity_relations rows persisted
        rel_count = db._conn.execute(
            "SELECT COUNT(*) FROM entity_relations WHERE from_uuid = ?",
            (feature_uuid,),
        ).fetchone()[0]
        assert rel_count == 0

        # Feature's workflow_phase unchanged (rollback covered metadata write)
        phase_after = db._conn.execute(
            "SELECT workflow_phase FROM workflow_phases WHERE type_id = ?",
            (seeded["feature_type_id"],),
        ).fetchone()["workflow_phase"]
        assert phase_after == phase_before


# ---------------------------------------------------------------------------
# AC-10.4 — idempotent replay; exactly 1 row + 1 phase_event per uuid
# ---------------------------------------------------------------------------


class TestAc10_4IdempotentReplay:
    def test_three_replays_produce_exactly_one_row_and_one_event(self, seeded):
        db = seeded["db"]
        u_bug = _register_bug(db, "4-replay")
        feature_uuid = _get_uuid(db, seeded["feature_type_id"])

        for call in range(3):
            result = _process_complete_phase(
                seeded["engine"], seeded["feature_type_id"], "finish",
                db=db, entity_engine=seeded["entity_engine"],
                closes=[u_bug],
            )
            data = json.loads(result)
            assert "error" not in data, f"call {call} errored: {data}"
            assert data["closes_applied"] == [u_bug]

        # Exactly 1 entity_relations row
        rel_count = db._conn.execute(
            "SELECT COUNT(*) FROM entity_relations "
            "WHERE from_uuid=? AND to_uuid=? AND kind='fixes'",
            (feature_uuid, u_bug),
        ).fetchone()[0]
        assert rel_count == 1

        # Exactly 1 entity_status_changed phase_event for the bug
        bug_type_id = db._conn.execute(
            "SELECT type_id FROM entities WHERE uuid = ?", (u_bug,)
        ).fetchone()["type_id"]
        event_count = db._conn.execute(
            "SELECT COUNT(*) FROM phase_events "
            "WHERE type_id=? AND event_type='entity_status_changed'",
            (bug_type_id,),
        ).fetchone()[0]
        assert event_count == 1


# ---------------------------------------------------------------------------
# AC-10.5 — cross-closer conflict
# ---------------------------------------------------------------------------


class TestAc10_5CrossCloserConflict:
    def test_different_closer_raises_invalidclose(self, seeded):
        db = seeded["db"]
        u_bug = _register_bug(db, "5-conflict")

        # First closer (the seeded feature) closes it cleanly.
        first = _process_complete_phase(
            seeded["engine"], seeded["feature_type_id"], "finish",
            db=db, entity_engine=seeded["entity_engine"],
            closes=[u_bug],
        )
        assert "error" not in json.loads(first)

        # Register a DIFFERENT closer feature.
        db.register_entity(
            "feature", "112-other", "Other feature",
            status="active", project_id="__unknown__",
        )
        db.create_workflow_phase("feature:112-other", workflow_phase="implement")

        # Construct artifact dir so projection doesn't fail.
        feat_dir = os.path.join(
            seeded["engine"].artifacts_root, "features", "112-other"
        )
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            f.write('{"id": "112", "slug": "other", "status": "active", "mode": "standard"}')

        # Set the other feature to 'finish' phase so engine.complete_phase('finish')
        # succeeds; otherwise the engine raises ValueError BEFORE closure block runs.
        db.update_workflow_phase("feature:112-other", workflow_phase="finish")

        result = _process_complete_phase(
            seeded["engine"], "feature:112-other", "finish",
            db=db, entity_engine=seeded["entity_engine"],
            closes=[u_bug],
        )
        data = json.loads(result)
        assert data.get("error") is True
        assert data["error_type"] == "invalidclosetargeterror"
        assert "already closed by different closer" in data["message"]


# ---------------------------------------------------------------------------
# AC-10.6 — cross-workspace closure permitted
# ---------------------------------------------------------------------------


class TestAc10_6CrossWorkspacePermitted:
    """Feature 129 Task 2: the FR-10.3 cross-workspace closure gate is
    deleted — closing an entity that lives in a different workspace than
    the caller is now an ordinary permitted operation.
    """

    def test_cross_workspace_close_succeeds(self, seeded, tmp_path):
        db = seeded["db"]

        # Create a second workspace + a bug inside it.
        import uuid as _uuid
        ws2_uuid = str(_uuid.uuid4())
        now = db._now_iso()
        db._conn.execute(
            "INSERT INTO workspaces "
            "(uuid, project_id_legacy, project_root, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (ws2_uuid, "p2-legacy", str(tmp_path / "ws2"), now, now),
        )
        u_bug_ws2 = db.register_entity(
            entity_type="bug",
            entity_id="6-foreign",
            name="Foreign bug",
            status="open",
            workspace_uuid=ws2_uuid,
        )

        # Caller is in __unknown__ workspace (wss._workspace_uuid set via
        # fixture); the workspace mismatch no longer blocks the closure.
        result = _process_complete_phase(
            seeded["engine"], seeded["feature_type_id"], "finish",
            db=db, entity_engine=seeded["entity_engine"],
            closes=[u_bug_ws2],
        )
        data = json.loads(result)
        assert "error" not in data, f"expected success; got {data}"
        assert data.get("closes_applied") == [u_bug_ws2]

        # Bug transitioned to 'closed'
        st = db._conn.execute(
            "SELECT status FROM entities WHERE uuid = ?", (u_bug_ws2,)
        ).fetchone()["status"]
        assert st == "closed"

        # `fixes` relation created from the feature to the foreign-workspace bug
        feature_uuid = _get_uuid(db, seeded["feature_type_id"])
        rel_count = db._conn.execute(
            "SELECT COUNT(*) FROM entity_relations "
            "WHERE from_uuid=? AND to_uuid=? AND kind='fixes'",
            (feature_uuid, u_bug_ws2),
        ).fetchone()[0]
        assert rel_count == 1


# ---------------------------------------------------------------------------
# AC-10.7 — terminal-without-closer-record raises
# ---------------------------------------------------------------------------


class TestAc10_7TerminalWithoutCloserRecord:
    def test_manually_closed_bug_blocks_subsequent_closure(self, seeded):
        db = seeded["db"]
        u_bug = _register_bug(db, "7-manual")
        # Manually flip to closed WITHOUT going through closes= path.
        db.update_entity(u_bug, status="closed", project_id="__unknown__")

        result = _process_complete_phase(
            seeded["engine"], seeded["feature_type_id"], "finish",
            db=db, entity_engine=seeded["entity_engine"],
            closes=[u_bug],
        )
        data = json.loads(result)
        assert data.get("error") is True
        assert data["error_type"] == "invalidclosetargeterror"
        assert "already terminal but no closer record" in data["message"]


# ---------------------------------------------------------------------------
# AC-10.8 — entity_status_changed phase_event metadata shape
# ---------------------------------------------------------------------------


class TestAc10_8EntityStatusChangedEvent:
    def test_metadata_records_old_new_status_and_closed_by_uuid(self, seeded):
        db = seeded["db"]
        u_bug = _register_bug(db, "8-event")
        feature_uuid = _get_uuid(db, seeded["feature_type_id"])

        result = _process_complete_phase(
            seeded["engine"], seeded["feature_type_id"], "finish",
            db=db, entity_engine=seeded["entity_engine"],
            closes=[u_bug],
        )
        assert "error" not in json.loads(result)

        bug_type_id = db._conn.execute(
            "SELECT type_id FROM entities WHERE uuid = ?", (u_bug,)
        ).fetchone()["type_id"]
        ev_row = db._conn.execute(
            "SELECT metadata FROM phase_events "
            "WHERE type_id=? AND event_type='entity_status_changed' "
            "ORDER BY id DESC LIMIT 1",
            (bug_type_id,),
        ).fetchone()
        assert ev_row is not None
        meta = json.loads(ev_row["metadata"])
        assert meta["old_status"] == "open"
        assert meta["new_status"] == "closed"
        # Feature 115 FR-C-115.1: F111 manual emit removed; new emit lives inside
        # db.update_entity which has no access to the closer's uuid. closed_by_uuid
        # metadata is permanently lost per accepted trade-off (115 spec AC-C-115.3
        # + 114 spec Pin F.1 entry #3). Operators correlate via entity_relations
        # (the closure relation is INSERTed separately in _process_complete_phase
        # step 7). Asserting absence here documents the contract.
        assert "closed_by_uuid" not in meta


# ---------------------------------------------------------------------------
# AC-10.9 — caller not registered raises before any writes
# ---------------------------------------------------------------------------


class TestAc10_9CallerNotRegistered:
    def test_unknown_caller_raises_entitynotfound(self, seeded):
        db = seeded["db"]
        u_bug = _register_bug(db, "9-orphan")

        rel_before = db._conn.execute(
            "SELECT COUNT(*) FROM entity_relations"
        ).fetchone()[0]
        bug_before = db._conn.execute(
            "SELECT status FROM entities WHERE uuid = ?", (u_bug,)
        ).fetchone()["status"]

        result = _process_complete_phase(
            seeded["engine"], "feature:doesnotexist-x", "finish",
            db=db, entity_engine=seeded["entity_engine"],
            closes=[u_bug],
        )
        data = json.loads(result)
        assert data.get("error") is True
        assert data["error_type"] == "entitynotfounderror"

        # No phase transition, no closure rows.
        rel_after = db._conn.execute(
            "SELECT COUNT(*) FROM entity_relations"
        ).fetchone()[0]
        bug_after = db._conn.execute(
            "SELECT status FROM entities WHERE uuid = ?", (u_bug,)
        ).fetchone()["status"]
        assert rel_after == rel_before == 0
        assert bug_after == bug_before == "open"


# ---------------------------------------------------------------------------
# AC-10.10 — feature in closes raises InvalidCloseTargetError with specific msg
# ---------------------------------------------------------------------------


class TestAc10_10FeatureNotClosableViaCloses:
    def test_feature_lifecycle_class_rejected(self, seeded):
        db = seeded["db"]
        # Register another feature; its lifecycle_class is feature_flow.
        db.register_entity(
            "feature", "111-target-feat", "Target feature",
            status="active", project_id="__unknown__",
        )
        u_feature = _get_uuid(db, "feature:111-target-feat")

        result = _process_complete_phase(
            seeded["engine"], seeded["feature_type_id"], "finish",
            db=db, entity_engine=seeded["entity_engine"],
            closes=[u_feature],
        )
        data = json.loads(result)
        assert data.get("error") is True
        assert data["error_type"] == "invalidclosetargeterror"
        assert "feature entities cannot be closed via closes=" in data["message"]


# ---------------------------------------------------------------------------
# AC-10.11 — state-machine bypass: backlog 'open' → 'dropped' (skip 'triaged')
# ---------------------------------------------------------------------------


class TestAc10_11BacklogStateMachineBypass:
    def test_open_backlog_drops_directly_via_closes(self, seeded):
        db = seeded["db"]
        u_bk = _register_backlog(db, "11-bypass", status="open")

        result = _process_complete_phase(
            seeded["engine"], seeded["feature_type_id"], "finish",
            db=db, entity_engine=seeded["entity_engine"],
            closes=[u_bk],
        )
        data = json.loads(result)
        assert "error" not in data, f"expected success; got {data}"

        # Status should be 'dropped' (work_flow terminal), not 'triaged'.
        st = db._conn.execute(
            "SELECT status FROM entities WHERE uuid = ?", (u_bk,)
        ).fetchone()["status"]
        assert st == "dropped"

        # Phase event records the bypass.
        bk_type_id = db._conn.execute(
            "SELECT type_id FROM entities WHERE uuid = ?", (u_bk,)
        ).fetchone()["type_id"]
        ev = db._conn.execute(
            "SELECT metadata FROM phase_events "
            "WHERE type_id=? AND event_type='entity_status_changed' "
            "ORDER BY id DESC LIMIT 1",
            (bk_type_id,),
        ).fetchone()
        assert ev is not None
        meta = json.loads(ev["metadata"])
        assert meta["old_status"] == "open"
        assert meta["new_status"] == "dropped"
