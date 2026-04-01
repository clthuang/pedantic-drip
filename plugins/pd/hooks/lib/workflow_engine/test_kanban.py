"""Tests for derive_kanban() — kanban column derivation from status + phase."""
from __future__ import annotations

import pytest

from .kanban import PHASE_TO_KANBAN, derive_kanban


class TestPhaseToKanbanMapping:
    """Verify the PHASE_TO_KANBAN dict covers all expected phases."""

    def test_six_phase_keys_present(self) -> None:
        expected = {
            "brainstorm", "specify", "design",
            "create-plan", "implement", "finish",
        }
        assert expected.issubset(PHASE_TO_KANBAN.keys())

    def test_five_d_phase_keys_present(self) -> None:
        expected = {"discover", "define", "deliver", "debrief"}
        assert expected.issubset(PHASE_TO_KANBAN.keys())

    def test_design_shared_between_both(self) -> None:
        """'design' appears in both 7-phase and 5D — single entry is correct."""
        assert PHASE_TO_KANBAN["design"] == "prioritised"


class TestDeriveKanban:
    """Test derive_kanban(status, workflow_phase) for all specified combos."""

    # --- Terminal statuses override phase ---

    def test_completed_status_returns_completed(self) -> None:
        assert derive_kanban("completed", "finish") == "completed"

    def test_completed_status_ignores_phase(self) -> None:
        assert derive_kanban("completed", "implement") == "completed"

    def test_completed_status_none_phase(self) -> None:
        assert derive_kanban("completed", None) == "completed"

    def test_abandoned_status_returns_completed(self) -> None:
        assert derive_kanban("abandoned", "implement") == "completed"

    def test_abandoned_any_phase(self) -> None:
        assert derive_kanban("abandoned", "brainstorm") == "completed"

    def test_abandoned_none_phase(self) -> None:
        assert derive_kanban("abandoned", None) == "completed"

    # --- Blocked status ---

    def test_blocked_status_returns_blocked(self) -> None:
        assert derive_kanban("blocked", "implement") == "blocked"

    def test_blocked_none_phase(self) -> None:
        assert derive_kanban("blocked", None) == "blocked"

    # --- Planned status ---

    def test_planned_status_returns_backlog(self) -> None:
        assert derive_kanban("planned", None) == "backlog"

    def test_planned_status_ignores_phase(self) -> None:
        assert derive_kanban("planned", "implement") == "backlog"

    # --- Active status, 7-phase ---

    def test_active_brainstorm(self) -> None:
        assert derive_kanban("active", "brainstorm") == "backlog"

    def test_active_specify(self) -> None:
        assert derive_kanban("active", "specify") == "backlog"

    def test_active_design(self) -> None:
        assert derive_kanban("active", "design") == "prioritised"

    def test_active_create_plan(self) -> None:
        assert derive_kanban("active", "create-plan") == "prioritised"

    def test_active_implement(self) -> None:
        assert derive_kanban("active", "implement") == "wip"

    def test_active_finish(self) -> None:
        assert derive_kanban("active", "finish") == "documenting"

    # --- Active status, 5D phases ---

    def test_active_discover(self) -> None:
        assert derive_kanban("active", "discover") == "backlog"

    def test_active_define(self) -> None:
        assert derive_kanban("active", "define") == "backlog"

    def test_active_deliver(self) -> None:
        assert derive_kanban("active", "deliver") == "wip"

    def test_active_debrief(self) -> None:
        assert derive_kanban("active", "debrief") == "documenting"

    # --- Fallback: active + None/unknown phase ---

    def test_active_none_phase_falls_back_to_backlog(self) -> None:
        assert derive_kanban("active", None) == "backlog"

    def test_active_unknown_phase_falls_back_to_backlog(self) -> None:
        assert derive_kanban("active", "nonexistent-phase") == "backlog"

    # --- Done-when scenarios from task spec ---

    def test_done_active_specify(self) -> None:
        """active+specify -> backlog per design PHASE_TO_KANBAN mapping.

        NOTE: Task done-when says active+specify->wip, but the design's
        PHASE_TO_KANBAN maps specify->backlog. Following the design (C2).
        """
        assert derive_kanban("active", "specify") == "backlog"

    def test_done_completed_finish(self) -> None:
        assert derive_kanban("completed", "finish") == "completed"

    def test_done_abandoned_any(self) -> None:
        assert derive_kanban("abandoned", "design") == "completed"

    def test_done_active_none_backlog(self) -> None:
        assert derive_kanban("active", None) == "backlog"

    def test_done_active_discover_backlog(self) -> None:
        assert derive_kanban("active", "discover") == "backlog"

    def test_done_active_deliver_wip(self) -> None:
        assert derive_kanban("active", "deliver") == "wip"

    def test_done_active_debrief_documenting(self) -> None:
        assert derive_kanban("active", "debrief") == "documenting"
