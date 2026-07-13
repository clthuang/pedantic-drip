"""Tests for workflow_engine.router's lifecycle entry points (moved from
entity_registry's former lifecycle module, feature 123 D6).

Unit tests for init_entity_workflow and transition_entity_phase extracted
from workflow_state_server.py.
"""
from __future__ import annotations

import pytest

from entity_registry.database import EntityDatabase
from workflow_engine.router import (
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
        project_id="__unknown__",
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
        project_id="__unknown__",
    )
    return type_id


# ---------------------------------------------------------------------------
# ENTITY_MACHINES constant
# ---------------------------------------------------------------------------


class TestEntityMachines:
    """Verify ENTITY_MACHINES constant structure."""

    def test_each_machine_has_required_keys(self):
        assert {"brainstorm", "backlog"} <= set(ENTITY_MACHINES)
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
            project_id="__unknown__",
        )
        with pytest.raises(ValueError, match="invalid_entity_type.*feature"):
            init_entity_workflow(db, "feature:feat-1", "ideation", "backlog")

    def test_init_project_type_rejected(self, db):
        db.register_entity(
            entity_type="project",
            entity_id="proj-1",
            name="Test project",
            status="active",
            project_id="__unknown__",
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
        assert result["kanban_column"] == "wip"

    def test_valid_forward_transition_backlog(self, db):
        type_id = _create_backlog(db)
        init_entity_workflow(db, type_id, "open", "backlog")
        result = transition_entity_phase(db, type_id, "triaged")
        assert result["transitioned"] is True
        assert result["from_phase"] == "open"
        assert result["to_phase"] == "triaged"
        assert result["kanban_column"] == "prioritised"

    def test_invalid_transition_rejected(self, db):
        """promoted is a terminal state — cannot transition out of it."""
        type_id = _create_brainstorm(db)
        init_entity_workflow(db, type_id, "draft", "wip")
        transition_entity_phase(db, type_id, "promoted")
        with pytest.raises(ValueError, match="invalid_transition.*cannot transition"):
            transition_entity_phase(db, type_id, "draft")

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

    def test_draft_to_promoted_direct(self, db):
        """draft -> promoted is valid (skip reviewing for direct feature creation)."""
        type_id = _create_brainstorm(db)
        init_entity_workflow(db, type_id, "draft", "wip")
        result = transition_entity_phase(db, type_id, "promoted")
        assert result["transitioned"] is True
        assert result["from_phase"] == "draft"
        assert result["to_phase"] == "promoted"
        assert result["kanban_column"] == "completed"
        row = db.get_workflow_phase(type_id)
        assert row["last_completed_phase"] == "draft"
        entity = db.get_entity(type_id)
        assert entity["status"] == "promoted"

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

    # ------------------------------------------------------------------
    # Feature 113 / FR-5 / FR-5.2: symmetric workspace_uuid forwarding
    # ------------------------------------------------------------------

    def test_transition_entity_phase_workspace_uuid_consistent(self, db):
        """Pin: transition_entity_phase forwards workspace_uuid SYMMETRICALLY
        to BOTH db.update_entity AND db.update_workflow_phase (FR-5.1).

        Setup bootstraps two workspaces. The brainstorm entity 'foo' is
        registered in ws_a with a workflow_phases row scoped to ws_a. A
        parallel 'brainstorm:other' entity is registered in ws_b as a
        cross-workspace isolation witness.

        Test instruments db.update_workflow_phase via monkeypatch to capture
        the kwargs it receives — pins that workspace_uuid is forwarded into
        the call (NOT just into db.update_entity).

        Assertions:
          (1) Success with workspace_uuid=ws_a: ws_a's entity status →
              'promoted'; workflow_phase row → 'promoted' / 'completed'.
          (2) ws_b's parallel entity UNCHANGED (no cross-workspace leak).
          (3) db.update_workflow_phase received workspace_uuid=ws_a kwarg —
              direct pin on the FR-5.1 forwarding line (router.py
              update_kwargs dict).
          (4) Mismatch path with workspace_uuid=ws_b against a ws_a-scoped
              entity raises ValueError (FR-5.1 symmetric scope rejection).
        """
        from entity_registry.test_helpers import bootstrap_test_workspace

        ws_a_uuid = bootstrap_test_workspace(db, "ws-a-lifecycle")
        ws_b_uuid = bootstrap_test_workspace(db, "ws-b-lifecycle")

        # ws_a: 'brainstorm:foo' + workflow_phase row.
        db.register_entity(
            entity_type="brainstorm",
            entity_id="foo",
            name="Foo brainstorm in ws-a",
            status="draft",
            workspace_uuid=ws_a_uuid,
        )
        db.upsert_workflow_phase(
            "brainstorm:foo",
            workflow_phase="draft",
            kanban_column="wip",
            workspace_uuid=ws_a_uuid,
        )
        # Sanity: stored workflow_phases.workspace_uuid is ws_a.
        wp_row = db._conn.execute(
            "SELECT workspace_uuid FROM workflow_phases WHERE type_id = ?",
            ("brainstorm:foo",),
        ).fetchone()
        assert wp_row["workspace_uuid"] == ws_a_uuid

        # ws_b: an unrelated 'brainstorm:other' entity used as the
        # cross-workspace isolation witness.
        db.register_entity(
            entity_type="brainstorm",
            entity_id="other",
            name="Other brainstorm in ws-b",
            status="draft",
            workspace_uuid=ws_b_uuid,
        )

        # Instrument db.update_workflow_phase to capture kwargs. The pin is
        # specifically on the 'workspace_uuid' kwarg in update_kwargs dict
        # at router.py:452-460. We wrap the real method (not a
        # mock) so the actual DB writes still happen and assertions (1)/(2)
        # remain meaningful.
        captured_update_kwargs: list[dict] = []
        real_update_workflow_phase = db.update_workflow_phase

        def _spy_update_workflow_phase(type_id, **kwargs):
            captured_update_kwargs.append({"type_id": type_id, **kwargs})
            return real_update_workflow_phase(type_id, **kwargs)

        db.update_workflow_phase = _spy_update_workflow_phase  # type: ignore[method-assign]

        try:
            # (1) Success path: workspace_uuid=ws_a → both writes land.
            result = transition_entity_phase(
                db, "brainstorm:foo", "promoted", workspace_uuid=ws_a_uuid,
            )
        finally:
            db.update_workflow_phase = real_update_workflow_phase  # type: ignore[method-assign]

        assert result["transitioned"] is True
        assert result["to_phase"] == "promoted"

        # ws_a entity status updated to 'promoted'.
        ws_a_entity = db._conn.execute(
            "SELECT status FROM entities "
            "WHERE type_id = ? AND workspace_uuid = ?",
            ("brainstorm:foo", ws_a_uuid),
        ).fetchone()
        assert ws_a_entity["status"] == "promoted"

        # workflow_phase row updated (advanced + kanban changed).
        wp_after = db.get_workflow_phase("brainstorm:foo")
        assert wp_after["workflow_phase"] == "promoted"
        assert wp_after["kanban_column"] == "completed"

        # (2) ws_b's unrelated entity UNCHANGED — no cross-workspace leak.
        ws_b_entity = db._conn.execute(
            "SELECT status FROM entities "
            "WHERE type_id = ? AND workspace_uuid = ?",
            ("brainstorm:other", ws_b_uuid),
        ).fetchone()
        assert ws_b_entity["status"] == "draft", (
            "ws_b entity status should be UNCHANGED — "
            f"got {ws_b_entity['status']!r}"
        )

        # (3) FR-5.1 mutation pin: db.update_workflow_phase received
        # workspace_uuid=ws_a as a forwarded kwarg. Without the
        # `"workspace_uuid": workspace_uuid` entry in the update_kwargs dict
        # at router.py:452-460, this assertion fails (kwarg absent
        # from captured call).
        assert len(captured_update_kwargs) == 1, captured_update_kwargs
        call_kwargs = captured_update_kwargs[0]
        assert "workspace_uuid" in call_kwargs, (
            "transition_entity_phase must forward workspace_uuid to "
            f"db.update_workflow_phase; got kwargs: {call_kwargs!r}"
        )
        assert call_kwargs["workspace_uuid"] == ws_a_uuid, (
            f"Forwarded workspace_uuid should equal ws_a; got "
            f"{call_kwargs['workspace_uuid']!r}"
        )

        # (4) Mismatch path: register a SECOND brainstorm in ws_a, init its
        # workflow_phase, then attempt transition with workspace_uuid=ws_b
        # (wrong workspace). db.update_entity's workspace-scoped lookup
        # rejects the ws_a entity from a ws_b perspective — pins the
        # symmetric scope rejection contract.
        db.register_entity(
            entity_type="brainstorm",
            entity_id="bar",
            name="Bar brainstorm in ws-a",
            status="draft",
            workspace_uuid=ws_a_uuid,
        )
        db.upsert_workflow_phase(
            "brainstorm:bar",
            workflow_phase="draft",
            kanban_column="wip",
            workspace_uuid=ws_a_uuid,
        )

        with pytest.raises(ValueError):
            transition_entity_phase(
                db, "brainstorm:bar", "reviewing", workspace_uuid=ws_b_uuid,
            )


# ---------------------------------------------------------------------------
# Feature 111 AC-BL.7 — defensive raise on bug/task type_ids
# ---------------------------------------------------------------------------
#
# bug and task type_ids are not lifecycle-GRAPH kinds: they do NOT have
# ENTITY_MACHINES entries (feature 123 — task IS machine-bearing via
# MACHINE_REGISTRY's FiveDMachine, but ENTITY_MACHINES itself stays scoped
# to brainstorm/backlog only; bug remains the sole machine-less kind, spec
# FR123-5). The existing first-line validation in transition_entity_phase
# at router.py:413 (raises
# "invalid_entity_type: {entity_type} — only brainstorm and backlog supported")
# fires naturally for these type_ids. These tests pin that behavior so a
# future refactor of ENTITY_MACHINES does not accidentally widen routing.


class TestTransitionEntityPhaseStatusOnlyBugTask:
    def test_transition_entity_phase_rejects_bug_type_id(self, db):
        # Register the bug so the type_id resolves (we want the raise to
        # come from the entity_type-vs-ENTITY_MACHINES gate, not from a
        # missing-entity branch).
        db.register_entity(
            entity_type="bug",
            entity_id="1-defensive-bug",
            name="Defensive raise check",
            status="open",
            project_id="__unknown__",
        )

        with pytest.raises(ValueError) as excinfo:
            transition_entity_phase(
                db, "bug:1-defensive-bug", "resolved",
            )
        msg = str(excinfo.value)
        assert "invalid_entity_type" in msg
        assert "bug" in msg

    def test_transition_entity_phase_rejects_task_type_id(self, db):
        db.register_entity(
            entity_type="task",
            entity_id="2-defensive-task",
            name="Defensive raise check task",
            status="open",
            project_id="__unknown__",
        )

        with pytest.raises(ValueError) as excinfo:
            transition_entity_phase(
                db, "task:2-defensive-task", "closed",
            )
        msg = str(excinfo.value)
        assert "invalid_entity_type" in msg
        assert "task" in msg


# ---------------------------------------------------------------------------
# Feature 123 D2.3 (deepened): transitions FROM terminal phases (no
# outgoing edges) -- exact error message + pre/post state UNCHANGED.
# derived_from: design:D2.3 (LifecycleMachine graph membership),
# dimension:adversarial, dimension:error_propagation
# ---------------------------------------------------------------------------


class TestTransitionFromTerminalPhases:
    """LifecycleMachine's ``transitions`` dict has NO key for terminal
    phases (promoted/abandoned/dropped) -- ``.get(current, [])`` always
    returns ``[]``, so EVERY target is rejected from a terminal current
    phase. test_invalid_transition_rejected (above) exercises exactly ONE
    terminal phase (brainstorm.promoted) via a real forward transition
    into it and doesn't pin the exact message or leftover state -- this
    parametrizes over all FOUR terminal phases across both kinds (seeded
    directly via init_entity_workflow, the public API) and adds both
    checks.

    Anticipate: a bug that special-cased "no transitions dict entry" as
    "allow anything" (instead of "allow nothing") would let a terminal
    entity silently re-open -- undetectable without an exact-rejection +
    state-preserved pin.
    """

    @pytest.mark.parametrize(
        "kind,terminal_phase,terminal_column,any_target",
        [
            ("brainstorm", "promoted", "completed", "draft"),
            ("brainstorm", "abandoned", "completed", "reviewing"),
            ("backlog", "promoted", "completed", "open"),
            ("backlog", "dropped", "completed", "triaged"),
        ],
    )
    def test_transition_from_terminal_phase_rejected_with_unchanged_state(
        self, db, kind, terminal_phase, terminal_column, any_target,
    ):
        # Given an entity whose workflow_phases row is already AT a
        # terminal phase (no outgoing edges in ENTITY_MACHINES)
        create = _create_brainstorm if kind == "brainstorm" else _create_backlog
        type_id = create(db, "terminal-probe")
        init_entity_workflow(db, type_id, terminal_phase, terminal_column)
        row_before = db.get_workflow_phase(type_id)

        # When any transition is attempted out of it
        with pytest.raises(ValueError) as excinfo:
            transition_entity_phase(db, type_id, any_target)

        # Then it is rejected with the exact graph-membership error string
        assert str(excinfo.value) == (
            f"invalid_transition: cannot transition {kind} from "
            f"{terminal_phase} to {any_target}"
        )
        # And the row is left completely unchanged by the rejected call
        row_after = db.get_workflow_phase(type_id)
        assert row_after == row_before, (
            "a rejected transition FROM a terminal phase must not mutate "
            "the workflow_phases row"
        )


# ---------------------------------------------------------------------------
# Feature 123 D1 (deepened): init_entity_workflow's idempotency check runs
# AFTER validation (router.py step 1b validates phase/column against the
# machine BEFORE step 2's idempotent-row short-circuit) -- an existing row
# does NOT bypass validation on a re-call with bad args, and a re-call with
# DIFFERENT-but-individually-valid args returns the ORIGINALLY stored
# values rather than silently re-writing.
# derived_from: design:D1 (init_entity_workflow validation ordering),
# dimension:adversarial
# ---------------------------------------------------------------------------


class TestInitEntityWorkflowIdempotencyOrdering:
    """test_init_idempotent_returns_existing (above) only ever calls
    init_entity_workflow twice with IDENTICAL args -- it cannot distinguish
    'idempotency short-circuits before validation runs' from 'validation
    always runs, idempotency is just a data return'. These two tests
    separate that ordering with DIFFERING second-call args.
    """

    def test_idempotent_call_still_validates_new_args(self, db):
        # Given a brainstorm with an existing draft/wip workflow row
        type_id = _create_brainstorm(db, "idempotent-validate")
        first = init_entity_workflow(db, type_id, "draft", "wip")
        assert first["created"] is True

        # When init_entity_workflow is called AGAIN with an invalid phase
        # Then it still raises -- the pre-existing row does not short-
        # circuit validation.
        with pytest.raises(ValueError, match="invalid_transition.*bogus"):
            init_entity_workflow(db, type_id, "bogus", "wip")

        # And the stored row is untouched by the rejected call.
        row = db.get_workflow_phase(type_id)
        assert row["workflow_phase"] == "draft"
        assert row["kanban_column"] == "wip"

    def test_idempotent_call_with_different_valid_args_returns_stored_values(
        self, db,
    ):
        # Given a brainstorm initialized at draft/wip
        type_id = _create_brainstorm(db, "idempotent-stored")
        first = init_entity_workflow(db, type_id, "draft", "wip")
        assert first["created"] is True

        # When init_entity_workflow is called again with a DIFFERENT
        # phase/column pair that is INDIVIDUALLY valid for brainstorm
        # (reviewing/wip is a real pair, per FR123-4) but doesn't match
        # the row already on disk
        result = init_entity_workflow(db, type_id, "reviewing", "wip")

        # Then the idempotent branch returns the ORIGINALLY stored
        # draft/wip values, not the newly requested reviewing/wip --
        # init_entity_workflow never silently overwrites an existing row.
        assert result["created"] is False
        assert result["reason"] == "already_exists"
        assert result["workflow_phase"] == "draft"
        assert result["kanban_column"] == "wip"

        row = db.get_workflow_phase(type_id)
        assert row["workflow_phase"] == "draft", "existing row must not be overwritten"


# ---------------------------------------------------------------------------
# Feature 123 D2.3 (deepened): backlog open->dropped forward classification
# -- named explicitly in ENTITY_MACHINES['backlog']['forward'] but never
# asserted end-to-end for its last_completed_phase write (the exhaustive
# tests in test_workflow_state_server.py assert kanban_column only).
# derived_from: spec:SC1 (backlog forward set), dimension:bdd_scenarios
# ---------------------------------------------------------------------------


class TestBacklogSkipToTerminalForwardClassification:
    def test_open_to_dropped_is_forward_and_sets_last_completed_phase(self, db):
        # Given a backlog item at 'open' (its initial phase)
        type_id = _create_backlog(db, "skip-to-dropped")
        init_entity_workflow(db, type_id, "open", "backlog")

        # When it transitions directly to the terminal 'dropped' phase
        # (skipping 'triaged' -- a valid direct edge per ENTITY_MACHINES)
        result = transition_entity_phase(db, type_id, "dropped")

        # Then it is classified forward (('open', 'dropped') is in the
        # 'forward' set) -- so last_completed_phase advances to 'open',
        # exactly as a triaged-mediated path would leave the PRECEDING
        # phase, not None/unset.
        assert result["transitioned"] is True
        assert result["kanban_column"] == "completed"
        row = db.get_workflow_phase(type_id)
        assert row["last_completed_phase"] == "open", (
            "open->dropped is a FORWARD edge (ENTITY_MACHINES['backlog']"
            "['forward']) -- last_completed_phase must advance, not stay None"
        )
