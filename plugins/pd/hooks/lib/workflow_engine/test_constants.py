"""Tests for workflow_engine.kanban — ensures derive_kanban covers every
workflow phase and maps only to valid kanban columns."""

from transition_gate import PHASE_SEQUENCE
from workflow_engine.kanban import PHASE_TO_KANBAN, derive_kanban

VALID_KANBAN_COLUMNS = {
    "backlog",
    "prioritised",
    "wip",
    "agent_review",
    "human_review",
    "blocked",
    "documenting",
    "completed",
}


class TestPhaseToKanban:
    """PHASE_TO_KANBAN completeness and validity (via derive_kanban)."""

    def test_all_phases_mapped(self) -> None:
        """Every phase in PHASE_SEQUENCE has a corresponding key in PHASE_TO_KANBAN."""
        for phase in PHASE_SEQUENCE:
            assert phase.value in PHASE_TO_KANBAN, (
                f"Phase '{phase.value}' from PHASE_SEQUENCE is missing "
                f"from PHASE_TO_KANBAN"
            )

    def test_all_values_valid_kanban_columns(self) -> None:
        """Every value in the map is a recognised kanban column name."""
        for phase, column in PHASE_TO_KANBAN.items():
            assert column in VALID_KANBAN_COLUMNS, (
                f"Phase '{phase}' maps to '{column}' which is not a "
                f"valid kanban column. Valid: {sorted(VALID_KANBAN_COLUMNS)}"
            )

    def test_derive_kanban_active_with_phase(self) -> None:
        """derive_kanban for active status delegates to PHASE_TO_KANBAN."""
        for phase in PHASE_SEQUENCE:
            result = derive_kanban("active", phase.value)
            assert result == PHASE_TO_KANBAN[phase.value]

    def test_derive_kanban_terminal_statuses(self) -> None:
        """Terminal statuses always map to 'completed'."""
        assert derive_kanban("completed", "brainstorm") == "completed"
        assert derive_kanban("abandoned", "implement") == "completed"

    def test_derive_kanban_blocked_status(self) -> None:
        """Blocked status always maps to 'blocked'."""
        assert derive_kanban("blocked", "design") == "blocked"

    def test_derive_kanban_planned_status(self) -> None:
        """Planned status always maps to 'backlog'."""
        assert derive_kanban("planned", "implement") == "backlog"

    def test_derive_kanban_no_phase_fallback(self) -> None:
        """Active status with no phase falls back to 'backlog'."""
        assert derive_kanban("active", None) == "backlog"
