"""Tests for entity_registry.entity_lifecycle module.

Unit tests for init_entity_workflow and transition_entity_phase extracted
from workflow_state_server.py.
"""
from __future__ import annotations

import pytest

from entity_registry.database import EntityDatabase
from entity_registry.entity_lifecycle import (
    ENTITY_MACHINES,
    init_entity_workflow,
    transition_entity_phase,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    """Provide a file-based EntityDatabase with workflow_phases table."""
    db_path = str(tmp_path / "entities.db")
    database = EntityDatabase(db_path)
    yield database
    database.close()


def _create_brainstorm(db: EntityDatabase, entity_id: str = "idea-1") -> str:
    """Helper: register a brainstorm entity and return its type_id."""
    type_id = f"brainstorm:{entity_id}"
    db.register_entity(
        entity_type="brainstorm",
        entity_id=entity_id,
        name=f"Test brainstorm {entity_id}",
        status="draft",
    )
    return type_id


def _create_backlog(db: EntityDatabase, entity_id: str = "item-1") -> str:
    """Helper: register a backlog entity and return its type_id."""
    type_id = f"backlog:{entity_id}"
    db.register_entity(
        entity_type="backlog",
        entity_id=entity_id,
        name=f"Test backlog {entity_id}",
        status="open",
    )
    return type_id


# ---------------------------------------------------------------------------
# ENTITY_MACHINES constant
# ---------------------------------------------------------------------------


class TestEntityMachines:
    """Verify ENTITY_MACHINES constant structure."""

    def test_brainstorm_machine_exists(self):
        assert "brainstorm" in ENTITY_MACHINES

    def test_backlog_machine_exists(self):
        assert "backlog" in ENTITY_MACHINES

    def test_each_machine_has_required_keys(self):
        for entity_type, machine in ENTITY_MACHINES.items():
            assert "transitions" in machine, f"{entity_type} missing transitions"
            assert "columns" in machine, f"{entity_type} missing columns"
            assert "forward" in machine, f"{entity_type} missing forward"


# ---------------------------------------------------------------------------
# init_entity_workflow
# ---------------------------------------------------------------------------


class TestInitEntityWorkflow:
    """Tests for init_entity_workflow()."""

    def test_init_brainstorm_creates_row(self, db):
        type_id = _create_brainstorm(db)
        result = init_entity_workflow(db, type_id, "draft", "wip")
        assert result["created"] is True
        assert result["type_id"] == type_id
        assert result["workflow_phase"] == "draft"
        assert result["kanban_column"] == "wip"

    def test_init_backlog_creates_row(self, db):
        type_id = _create_backlog(db)
        result = init_entity_workflow(db, type_id, "open", "backlog")
        assert result["created"] is True
        assert result["type_id"] == type_id
        assert result["workflow_phase"] == "open"
        assert result["kanban_column"] == "backlog"

    def test_init_idempotent_returns_existing(self, db):
        type_id = _create_brainstorm(db)
        first = init_entity_workflow(db, type_id, "draft", "wip")
        assert first["created"] is True
        second = init_entity_workflow(db, type_id, "draft", "wip")
        assert second["created"] is False
        assert second["reason"] == "already_exists"
        assert second["workflow_phase"] == "draft"
        assert second["kanban_column"] == "wip"

    def test_init_nonexistent_entity_raises(self, db):
        with pytest.raises(ValueError, match="entity_not_found"):
            init_entity_workflow(db, "brainstorm:nonexistent", "draft", "wip")

    def test_init_feature_type_rejected(self, db):
        db.register_entity(
            entity_type="feature",
            entity_id="feat-1",
            name="Test feature",
            status="active",
        )
        with pytest.raises(ValueError, match="invalid_entity_type.*feature"):
            init_entity_workflow(db, "feature:feat-1", "ideation", "backlog")

    def test_init_project_type_rejected(self, db):
        db.register_entity(
            entity_type="project",
            entity_id="proj-1",
            name="Test project",
            status="active",
        )
        with pytest.raises(ValueError, match="invalid_entity_type.*project"):
            init_entity_workflow(db, "project:proj-1", "active", "wip")

    def test_init_invalid_phase_for_brainstorm_raises(self, db):
        type_id = _create_brainstorm(db)
        with pytest.raises(ValueError, match="invalid_transition.*bogus"):
            init_entity_workflow(db, type_id, "bogus", "wip")

    def test_init_mismatched_column_raises(self, db):
        type_id = _create_brainstorm(db)
        with pytest.raises(ValueError, match="invalid_transition.*kanban_column"):
            init_entity_workflow(db, type_id, "draft", "wrong_column")

    def test_init_returns_dict_not_string(self, db):
        type_id = _create_brainstorm(db)
        result = init_entity_workflow(db, type_id, "draft", "wip")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# transition_entity_phase
# ---------------------------------------------------------------------------


class TestTransitionEntityPhase:
    """Tests for transition_entity_phase()."""

    def test_valid_forward_transition_brainstorm(self, db):
        type_id = _create_brainstorm(db)
        init_entity_workflow(db, type_id, "draft", "wip")
        result = transition_entity_phase(db, type_id, "reviewing")
        assert result["transitioned"] is True
        assert result["from_phase"] == "draft"
        assert result["to_phase"] == "reviewing"
        assert result["kanban_column"] == "agent_review"

    def test_valid_forward_transition_backlog(self, db):
        type_id = _create_backlog(db)
        init_entity_workflow(db, type_id, "open", "backlog")
        result = transition_entity_phase(db, type_id, "triaged")
        assert result["transitioned"] is True
        assert result["from_phase"] == "open"
        assert result["to_phase"] == "triaged"
        assert result["kanban_column"] == "prioritised"

    def test_invalid_transition_rejected(self, db):
        type_id = _create_brainstorm(db)
        init_entity_workflow(db, type_id, "draft", "wip")
        with pytest.raises(ValueError, match="invalid_transition.*cannot transition"):
            transition_entity_phase(db, type_id, "promoted")

    def test_forward_transition_updates_last_completed_phase(self, db):
        type_id = _create_brainstorm(db)
        init_entity_workflow(db, type_id, "draft", "wip")
        transition_entity_phase(db, type_id, "reviewing")
        row = db.get_workflow_phase(type_id)
        assert row["last_completed_phase"] == "draft"

    def test_backward_transition_preserves_last_completed_phase(self, db):
        type_id = _create_brainstorm(db)
        init_entity_workflow(db, type_id, "draft", "wip")
        transition_entity_phase(db, type_id, "reviewing")
        # reviewing -> draft is backward
        transition_entity_phase(db, type_id, "draft")
        row = db.get_workflow_phase(type_id)
        # last_completed_phase should still be "draft" from the forward transition
        assert row["last_completed_phase"] == "draft"

    def test_entities_status_updated(self, db):
        type_id = _create_brainstorm(db)
        init_entity_workflow(db, type_id, "draft", "wip")
        transition_entity_phase(db, type_id, "reviewing")
        entity = db.get_entity(type_id)
        assert entity["status"] == "reviewing"

    def test_malformed_type_id_raises(self, db):
        with pytest.raises(ValueError, match="invalid_entity_type.*malformed"):
            transition_entity_phase(db, "nocolon", "reviewing")

    def test_unsupported_entity_type_raises(self, db):
        with pytest.raises(ValueError, match="invalid_entity_type.*feature"):
            transition_entity_phase(db, "feature:feat-1", "reviewing")

    def test_nonexistent_entity_raises(self, db):
        with pytest.raises(ValueError, match="entity_not_found"):
            transition_entity_phase(db, "brainstorm:nonexistent", "reviewing")

    def test_no_workflow_row_raises(self, db):
        type_id = _create_brainstorm(db)
        with pytest.raises(ValueError, match="entity_not_found.*no workflow_phases"):
            transition_entity_phase(db, type_id, "reviewing")

    def test_returns_dict_not_string(self, db):
        type_id = _create_brainstorm(db)
        init_entity_workflow(db, type_id, "draft", "wip")
        result = transition_entity_phase(db, type_id, "reviewing")
        assert isinstance(result, dict)

    def test_full_lifecycle_brainstorm_draft_to_promoted(self, db):
        """Full forward path: draft -> reviewing -> promoted."""
        type_id = _create_brainstorm(db)
        init_entity_workflow(db, type_id, "draft", "wip")
        transition_entity_phase(db, type_id, "reviewing")
        result = transition_entity_phase(db, type_id, "promoted")
        assert result["transitioned"] is True
        assert result["to_phase"] == "promoted"
        assert result["kanban_column"] == "completed"
        # last_completed_phase should be "reviewing"
        row = db.get_workflow_phase(type_id)
        assert row["last_completed_phase"] == "reviewing"

    def test_full_lifecycle_backlog_open_to_promoted(self, db):
        """Full forward path: open -> triaged -> promoted."""
        type_id = _create_backlog(db)
        init_entity_workflow(db, type_id, "open", "backlog")
        transition_entity_phase(db, type_id, "triaged")
        result = transition_entity_phase(db, type_id, "promoted")
        assert result["transitioned"] is True
        assert result["to_phase"] == "promoted"
        row = db.get_workflow_phase(type_id)
        assert row["last_completed_phase"] == "triaged"
