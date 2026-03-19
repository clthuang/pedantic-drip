"""Tests for workflow_engine.constants — ensures FEATURE_PHASE_TO_KANBAN
covers every workflow phase and maps only to valid kanban columns."""

from transition_gate import PHASE_SEQUENCE
from workflow_engine.constants import FEATURE_PHASE_TO_KANBAN

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


class TestFeaturePhaseToKanban:
    """FEATURE_PHASE_TO_KANBAN completeness and validity."""

    def test_all_phases_mapped(self) -> None:
        """Every phase in PHASE_SEQUENCE has a corresponding key in the map."""
        for phase in PHASE_SEQUENCE:
            assert phase.value in FEATURE_PHASE_TO_KANBAN, (
                f"Phase '{phase.value}' from PHASE_SEQUENCE is missing "
                f"from FEATURE_PHASE_TO_KANBAN"
            )

    def test_all_values_valid_kanban_columns(self) -> None:
        """Every value in the map is a recognised kanban column name."""
        for phase, column in FEATURE_PHASE_TO_KANBAN.items():
            assert column in VALID_KANBAN_COLUMNS, (
                f"Phase '{phase}' maps to '{column}' which is not a "
                f"valid kanban column. Valid: {sorted(VALID_KANBAN_COLUMNS)}"
            )
