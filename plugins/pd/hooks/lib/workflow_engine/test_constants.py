"""Tests for the workflow_engine package's per-file kanban-column
producers — ensures each replica covers every workflow phase, maps only
to valid kanban columns, and (critically) stays byte-identical to its
siblings.

Feature 132 (D6.1-.3) retired the shared workflow_engine.kanban module:
backfill.py, engine.py, feature_lifecycle.py, reconciliation.py, and
mcp/workflow_state_server.py each now carry a private
(_PHASE_TO_KANBAN, _kanban_column_for) replica instead of importing a
shared derive() function. This file is the parity backstop: it directly
compares the four same-tree replicas (the fifth, in mcp/, lives in a
separate import root and is exercised by mcp/test_workflow_state_server.py
instead) so a copy/paste divergence in any one of them fails LOUDLY here
rather than surfacing as a silent behavioral drift downstream. The
completeness/validity checks below also absorb the deleted
test_kanban.py's phase-coverage pins (its own home is gone with the
module).
"""
from __future__ import annotations

from entity_registry import backfill as _backfill_producer
from transition_gate import PHASE_SEQUENCE
from workflow_engine import engine as _engine_producer
from workflow_engine import feature_lifecycle as _feature_lifecycle_producer
from workflow_engine import reconciliation as _reconciliation_producer

# Representative producer for the completeness/validity/behavior pins
# below — TestKanbanProducerParity proves the other three match it
# value-for-value and branch-for-branch, so pinning against just one
# is not vacuous.
_REPRESENTATIVE = _engine_producer

PRODUCERS: dict[str, object] = {
    "engine": _engine_producer,
    "feature_lifecycle": _feature_lifecycle_producer,
    "reconciliation": _reconciliation_producer,
    "backfill": _backfill_producer,
}

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

FIVE_D_PHASES = {"discover", "define", "deliver", "debrief"}


class TestKanbanProducerParity:
    """All same-tree replicas must stay byte-identical — the DRY-violation
    risk feature 132's decentralization intentionally accepted, guarded
    here rather than left to silent drift."""

    def test_all_phase_to_kanban_dicts_are_identical(self) -> None:
        reference_name, reference_mod = next(iter(PRODUCERS.items()))
        reference = reference_mod._PHASE_TO_KANBAN
        for name, mod in PRODUCERS.items():
            assert mod._PHASE_TO_KANBAN == reference, (
                f"{name}._PHASE_TO_KANBAN diverges from "
                f"{reference_name}._PHASE_TO_KANBAN"
            )

    def test_all_kanban_column_for_functions_agree_on_every_branch(self) -> None:
        """Drives every producer's _kanban_column_for over the full
        (status, phase) input space and asserts they all return the same
        thing — catches priority-ladder logic drift a dict-equality
        check alone would miss."""
        statuses = (
            "planned", "active", "completed", "abandoned",
            "blocked", "unmapped-status",
        )
        phases = list(_REPRESENTATIVE._PHASE_TO_KANBAN) + [None, "nonexistent-phase"]

        for status in statuses:
            for phase in phases:
                results = {
                    name: mod._kanban_column_for(status, phase)
                    for name, mod in PRODUCERS.items()
                }
                assert len(set(results.values())) == 1, (
                    f"_kanban_column_for({status!r}, {phase!r}) diverges "
                    f"across producers: {results}"
                )


class TestKanbanProducerCompleteness:
    """PHASE_TO_KANBAN completeness/validity and _kanban_column_for
    behavior, checked against the representative producer (parity above
    proves the others match)."""

    def test_all_feature_phases_mapped(self) -> None:
        """Every phase in PHASE_SEQUENCE has a corresponding key in _PHASE_TO_KANBAN."""
        for phase in PHASE_SEQUENCE:
            assert phase.value in _REPRESENTATIVE._PHASE_TO_KANBAN, (
                f"Phase '{phase.value}' from PHASE_SEQUENCE is missing "
                f"from _PHASE_TO_KANBAN"
            )

    def test_five_d_phase_keys_present(self) -> None:
        assert FIVE_D_PHASES.issubset(_REPRESENTATIVE._PHASE_TO_KANBAN.keys())

    def test_design_shared_between_both(self) -> None:
        """'design' appears in both 7-phase and 5D — single entry is correct."""
        assert _REPRESENTATIVE._PHASE_TO_KANBAN["design"] == "prioritised"

    def test_all_values_valid_kanban_columns(self) -> None:
        """Every value in the map is a recognised kanban column name."""
        for phase, column in _REPRESENTATIVE._PHASE_TO_KANBAN.items():
            assert column in VALID_KANBAN_COLUMNS, (
                f"Phase '{phase}' maps to '{column}' which is not a "
                f"valid kanban column. Valid: {sorted(VALID_KANBAN_COLUMNS)}"
            )

    def test_specific_phase_to_kanban_mappings(self) -> None:
        """Pins the exact expected mapping per phase — the regression pin
        the deleted test_kanban.py's per-phase tests provided."""
        expected = {
            "brainstorm": "backlog",
            "specify": "backlog",
            "design": "prioritised",
            "create-plan": "prioritised",
            "implement": "wip",
            "finish": "documenting",
            "discover": "backlog",
            "define": "backlog",
            "deliver": "wip",
            "debrief": "documenting",
        }
        assert _REPRESENTATIVE._PHASE_TO_KANBAN == expected

    def test_active_with_phase_delegates_to_phase_to_kanban(self) -> None:
        """_kanban_column_for for active status delegates to _PHASE_TO_KANBAN."""
        for phase in PHASE_SEQUENCE:
            result = _REPRESENTATIVE._kanban_column_for("active", phase.value)
            assert result == _REPRESENTATIVE._PHASE_TO_KANBAN[phase.value]

    def test_terminal_statuses(self) -> None:
        """Terminal statuses always map to 'completed'."""
        assert _REPRESENTATIVE._kanban_column_for("completed", "brainstorm") == "completed"
        assert _REPRESENTATIVE._kanban_column_for("abandoned", "implement") == "completed"

    def test_blocked_status(self) -> None:
        """Blocked status always maps to 'blocked'."""
        assert _REPRESENTATIVE._kanban_column_for("blocked", "design") == "blocked"

    def test_planned_status(self) -> None:
        """Planned status always maps to 'backlog'."""
        assert _REPRESENTATIVE._kanban_column_for("planned", "implement") == "backlog"

    def test_no_phase_fallback(self) -> None:
        """Active status with no phase falls back to 'backlog'."""
        assert _REPRESENTATIVE._kanban_column_for("active", None) == "backlog"
