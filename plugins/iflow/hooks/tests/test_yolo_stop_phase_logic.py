"""Test-deepener tests for yolo-stop.sh phase transition logic (Feature 014).

Tests the Python logic embedded in yolo-stop.sh for next-phase computation,
covering: PHASE_SEQUENCE-derived transitions, engine path vs fallback path,
boundary conditions, adversarial inputs, error propagation, and mutation
mindset.

The hook embeds Python inline via `python3 -c`. These tests exercise the
same logic by importing the same modules and replicating the algorithm.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Path setup -- make hooks/lib importable (same as other hook tests)
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import pytest

from transition_gate.constants import PHASE_SEQUENCE
from transition_gate.models import Phase
from workflow_engine.models import FeatureWorkflowState


# ---------------------------------------------------------------------------
# Helpers -- replicate the exact algorithm from yolo-stop.sh lines 172-209
# ---------------------------------------------------------------------------

_PHASE_VALUES = tuple(p.value for p in PHASE_SEQUENCE)


def compute_next_phase_engine_path(state: FeatureWorkflowState | None,
                                    shell_last_phase: str) -> str:
    """Replicate the engine path from yolo-stop.sh lines 172-201.

    This is the try-block logic: uses engine state if available,
    falls back to shell variable if state is None.
    """
    if state is not None:
        last = state.last_completed_phase or ""
    else:
        last = shell_last_phase

    if last in ("null", ""):
        return PHASE_SEQUENCE[1].value  # specify
    elif last in _PHASE_VALUES:
        idx = _PHASE_VALUES.index(last)
        return _PHASE_VALUES[idx + 1] if idx < len(_PHASE_VALUES) - 1 else ""
    else:
        return ""


def compute_next_phase_fallback(last_completed_phase: str) -> str:
    """Replicate the fallback path from yolo-stop.sh lines 202-208.

    This is the except-block logic: hardcoded phase_map dict.
    """
    phase_map = {
        "null": "specify",
        "brainstorm": "specify",
        "specify": "design",
        "design": "create-plan",
        "create-plan": "create-tasks",
        "create-tasks": "implement",
        "implement": "finish",
    }
    return phase_map.get(last_completed_phase, "")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_state(last_completed_phase: str | None = None,
                current_phase: str | None = None,
                source: str = "db") -> FeatureWorkflowState:
    """Build a FeatureWorkflowState for testing."""
    return FeatureWorkflowState(
        feature_type_id="feature:001-test",
        current_phase=current_phase,
        last_completed_phase=last_completed_phase,
        completed_phases=(),
        mode=None,
        source=source,
    )


# ===========================================================================
# Dimension 1: BDD Scenarios (spec-driven)
# ===========================================================================


class TestPhaseTransitionMappings:
    """AC-3, AC-4: Phase transition mappings via PHASE_SEQUENCE."""

    def test_null_string_maps_to_specify(self):
        """Given lastCompletedPhase="null", the next phase is "specify".
        derived_from: spec:AC-4"""
        # Given a feature with lastCompletedPhase="null"
        state = _make_state(last_completed_phase=None)
        # When computing next phase (state.last_completed_phase is None -> '' via 'or')
        result = compute_next_phase_engine_path(state, "null")
        # Then next phase is "specify"
        assert result == "specify"

    def test_empty_string_maps_to_specify(self):
        """Given lastCompletedPhase="" (empty), the next phase is "specify".
        derived_from: spec:AC-4"""
        # Given a feature with empty lastCompletedPhase
        state = _make_state(last_completed_phase="")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "")
        # Then next phase is "specify"
        assert result == "specify"

    def test_brainstorm_maps_to_specify(self):
        """Given lastCompletedPhase="brainstorm", next phase is "specify".
        derived_from: spec:FR-1"""
        # Given a feature that completed brainstorm
        state = _make_state(last_completed_phase="brainstorm")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "brainstorm")
        # Then next phase is specify (brainstorm is index 0, specify is index 1)
        assert result == "specify"

    def test_specify_maps_to_design(self):
        """Given lastCompletedPhase="specify", next phase is "design".
        derived_from: spec:AC-3"""
        # Given a feature that completed specify
        state = _make_state(last_completed_phase="specify")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "specify")
        # Then next phase is "design"
        assert result == "design"

    def test_design_maps_to_create_plan(self):
        """Given lastCompletedPhase="design", next phase is "create-plan".
        derived_from: spec:FR-1"""
        # Given a feature that completed design
        state = _make_state(last_completed_phase="design")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "design")
        # Then next phase is "create-plan"
        assert result == "create-plan"

    def test_create_plan_maps_to_create_tasks(self):
        """Given lastCompletedPhase="create-plan", next phase is "create-tasks".
        derived_from: spec:FR-1"""
        # Given a feature that completed create-plan
        state = _make_state(last_completed_phase="create-plan")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "create-plan")
        # Then next phase is "create-tasks"
        assert result == "create-tasks"

    def test_create_tasks_maps_to_implement(self):
        """Given lastCompletedPhase="create-tasks", next phase is "implement".
        derived_from: spec:FR-1"""
        # Given a feature that completed create-tasks
        state = _make_state(last_completed_phase="create-tasks")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "create-tasks")
        # Then next phase is "implement"
        assert result == "implement"

    def test_implement_maps_to_finish(self):
        """Given lastCompletedPhase="implement", next phase is "finish".
        derived_from: spec:FR-1"""
        # Given a feature that completed implement
        state = _make_state(last_completed_phase="implement")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "implement")
        # Then next phase is "finish"
        assert result == "finish"

    def test_finish_maps_to_empty_string(self):
        """Given lastCompletedPhase="finish", next phase is "" (terminal).
        derived_from: spec:AC-5"""
        # Given a feature that completed finish
        state = _make_state(last_completed_phase="finish")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "finish")
        # Then no next phase (empty string)
        assert result == ""


class TestEnginePathUsesState:
    """AC-8: Engine path uses get_state() result."""

    def test_engine_state_overrides_shell_variable(self):
        """When engine returns state, its last_completed_phase takes precedence
        over the shell variable.
        derived_from: spec:AC-8"""
        # Given engine state says "design" but shell says "brainstorm"
        state = _make_state(last_completed_phase="design")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "brainstorm")
        # Then the engine's value is used (next after design = create-plan)
        assert result == "create-plan"

    def test_none_state_falls_back_to_shell_variable(self):
        """When engine returns None, the shell variable is used.
        derived_from: spec:FR-2 step 4"""
        # Given engine returns None and shell has "specify"
        result = compute_next_phase_engine_path(None, "specify")
        # Then shell variable is used (next after specify = design)
        assert result == "design"

    def test_state_with_none_last_completed_phase_treated_as_empty(self):
        """When engine returns state with last_completed_phase=None,
        it's treated as '' (empty) via 'or' fallback, mapping to specify.
        derived_from: spec:FR-1 algorithm step 3"""
        # Given engine state with last_completed_phase=None
        state = _make_state(last_completed_phase=None)
        # When computing next phase
        result = compute_next_phase_engine_path(state, "irrelevant")
        # Then it's treated as empty -> specify
        assert result == "specify"


class TestBlockMessageContent:
    """AC-3: Block message includes the correct /iflow:phase command."""

    def test_block_reason_format_for_specify(self):
        """The block message references /iflow:specify for null phase.
        derived_from: spec:AC-4"""
        # Given next phase is "specify"
        next_phase = compute_next_phase_engine_path(None, "null")
        feature_ref = "099-test-feature"
        last_phase = "null"
        # When constructing the reason (replicating yolo-stop.sh line 217)
        reason = f"[YOLO_MODE] Feature {feature_ref} in progress. Last completed: {last_phase}. Invoke /iflow:{next_phase} --feature={feature_ref} with [YOLO_MODE]."
        # Then it includes the correct command
        assert "/iflow:specify" in reason
        assert "--feature=099-test-feature" in reason

    def test_block_reason_format_for_design(self):
        """The block message references /iflow:design for specify phase.
        derived_from: spec:AC-3"""
        # Given next phase is "design"
        next_phase = compute_next_phase_engine_path(
            _make_state(last_completed_phase="specify"), "specify"
        )
        feature_ref = "042-my-feature"
        # When constructing the reason
        reason = f"[YOLO_MODE] Feature {feature_ref} in progress. Last completed: specify. Invoke /iflow:{next_phase} --feature={feature_ref} with [YOLO_MODE]."
        # Then it includes the correct command
        assert "/iflow:design" in reason


# ===========================================================================
# Dimension 2: Boundary Values
# ===========================================================================


class TestBoundaryPhaseSequence:
    """Boundary conditions on PHASE_SEQUENCE indexing."""

    def test_phase_sequence_has_7_phases(self):
        """PHASE_SEQUENCE must have exactly 7 phases.
        derived_from: dimension:boundary"""
        # Given the canonical PHASE_SEQUENCE
        # Then it has exactly 7 phases
        assert len(PHASE_SEQUENCE) == 7

    def test_first_phase_is_brainstorm_index_0(self):
        """PHASE_SEQUENCE[0] is brainstorm.
        derived_from: spec:Technical Notes"""
        # Given the canonical PHASE_SEQUENCE
        # Then index 0 is brainstorm
        assert PHASE_SEQUENCE[0] == Phase.brainstorm
        assert PHASE_SEQUENCE[0].value == "brainstorm"

    def test_second_phase_is_specify_index_1(self):
        """PHASE_SEQUENCE[1] is specify -- the null case target.
        Mutation check: if someone changed [1] to [0], null would map to brainstorm.
        derived_from: spec:Technical Notes"""
        # Given the canonical PHASE_SEQUENCE
        # Then index 1 is specify
        assert PHASE_SEQUENCE[1] == Phase.specify
        assert PHASE_SEQUENCE[1].value == "specify"

    def test_last_phase_is_finish_index_6(self):
        """PHASE_SEQUENCE[-1] is finish -- the terminal phase.
        Boundary: idx < len - 1 check prevents going past finish.
        derived_from: dimension:boundary"""
        # Given the canonical PHASE_SEQUENCE
        # Then last element is finish
        assert PHASE_SEQUENCE[-1] == Phase.finish
        assert PHASE_SEQUENCE[-1].value == "finish"

    def test_penultimate_phase_is_implement(self):
        """PHASE_SEQUENCE[-2] is implement -- last phase with a successor.
        Boundary: implement at idx 5, len-1 = 6, so 5 < 6 is True (has next).
        derived_from: dimension:boundary"""
        # Given the canonical PHASE_SEQUENCE
        # Then second-to-last is implement
        assert PHASE_SEQUENCE[-2] == Phase.implement
        assert PHASE_SEQUENCE[-2].value == "implement"

    def test_null_uses_index_1_not_index_0(self):
        """Null/empty maps to PHASE_SEQUENCE[1] (specify), not [0] (brainstorm).
        Mutation: changing [1] to [0] would produce "brainstorm" instead of "specify".
        derived_from: spec:FR-1 algorithm step 3"""
        # Given lastCompletedPhase is empty (null representation)
        result = compute_next_phase_engine_path(None, "null")
        # Then result is specify (index 1), NOT brainstorm (index 0)
        assert result == "specify"
        assert result != "brainstorm"

    def test_finish_boundary_idx_equals_len_minus_1(self):
        """finish is at idx 6, len(_PHASE_VALUES)-1 = 6, so idx < len-1 is False.
        Mutation: changing < to <= would produce an IndexError for finish.
        derived_from: dimension:boundary"""
        # Given finish is the last phase
        idx = _PHASE_VALUES.index("finish")
        # Then idx equals len - 1 exactly (boundary condition)
        assert idx == len(_PHASE_VALUES) - 1
        # And the function returns "" (no next phase), not an error
        result = compute_next_phase_engine_path(
            _make_state(last_completed_phase="finish"), "finish"
        )
        assert result == ""


# ===========================================================================
# Dimension 3: Adversarial / Negative Testing
# ===========================================================================


class TestAdversarialInputs:
    """Adversarial inputs to the phase transition logic."""

    def test_unknown_phase_returns_empty_string(self):
        """An unknown phase name returns "" (no next phase, hook allows stop).
        derived_from: spec:FR-1 algorithm step 3"""
        # Given a completely unknown phase
        state = _make_state(last_completed_phase="nonexistent-phase")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "nonexistent-phase")
        # Then returns empty string
        assert result == ""

    def test_case_sensitive_phase_names(self):
        """Phase names are case-sensitive -- "Specify" != "specify".
        derived_from: dimension:adversarial"""
        # Given a phase name with wrong case
        state = _make_state(last_completed_phase="Specify")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "Specify")
        # Then returns empty (not found in PHASE_VALUES)
        assert result == ""

    def test_phase_name_with_underscore_instead_of_hyphen(self):
        """Phase enum member uses underscore (create_plan) but value uses hyphen (create-plan).
        An underscore variant is not recognized.
        derived_from: dimension:adversarial"""
        # Given a phase name using underscore instead of hyphen
        state = _make_state(last_completed_phase="create_plan")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "create_plan")
        # Then returns empty (underscore variant not in PHASE_VALUES)
        assert result == ""

    def test_whitespace_in_phase_name(self):
        """Phase names with leading/trailing whitespace are not recognized.
        derived_from: dimension:adversarial"""
        # Given a phase name with whitespace
        state = _make_state(last_completed_phase=" specify ")
        # When computing next phase
        result = compute_next_phase_engine_path(state, " specify ")
        # Then returns empty
        assert result == ""

    def test_phase_name_with_trailing_newline(self):
        """Phase name with trailing newline is not recognized.
        derived_from: dimension:adversarial"""
        # Given a phase name with trailing newline
        state = _make_state(last_completed_phase="specify\n")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "specify\n")
        # Then returns empty
        assert result == ""

    def test_empty_string_literal_null_both_map_to_specify(self):
        """Both the string "null" and actual empty string map to specify.
        This is the convergence point documented in the implementation comment.
        derived_from: spec:FR-1 algorithm step 3"""
        # Given both null representations
        result_null_str = compute_next_phase_engine_path(None, "null")
        result_empty = compute_next_phase_engine_path(
            _make_state(last_completed_phase=""), "irrelevant"
        )
        # Then both produce "specify"
        assert result_null_str == "specify"
        assert result_empty == "specify"

    def test_numeric_phase_name_returns_empty(self):
        """A numeric phase name returns empty string.
        derived_from: dimension:adversarial"""
        # Given a numeric string as phase name
        state = _make_state(last_completed_phase="42")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "42")
        # Then returns empty
        assert result == ""

    def test_sql_injection_in_phase_name_returns_empty(self):
        """SQL-like input in phase name returns empty (no injection risk since
        this is a dict lookup, but confirms robustness).
        derived_from: dimension:adversarial"""
        # Given a SQL-like phase name
        state = _make_state(last_completed_phase="'; DROP TABLE--")
        # When computing next phase
        result = compute_next_phase_engine_path(state, "'; DROP TABLE--")
        # Then returns empty
        assert result == ""


# ===========================================================================
# Dimension 4: Error Propagation & Fallback Parity
# ===========================================================================


class TestFallbackParity:
    """NFR-3, AC-7: Fallback phase_map must match PHASE_SEQUENCE transitions."""

    def test_fallback_null_matches_engine_path(self):
        """Fallback for "null" matches engine path output.
        derived_from: spec:NFR-3"""
        # Given "null" as last phase
        engine_result = compute_next_phase_engine_path(None, "null")
        fallback_result = compute_next_phase_fallback("null")
        # Then both produce "specify"
        assert engine_result == fallback_result == "specify"

    def test_fallback_all_known_phases_match_engine_path(self):
        """Every known phase in fallback phase_map produces the same result as
        the engine path.
        derived_from: spec:NFR-3 drift risk"""
        # Given all phases that appear in the fallback phase_map
        test_phases = [
            "null", "brainstorm", "specify", "design",
            "create-plan", "create-tasks", "implement",
        ]
        for phase in test_phases:
            # When computing via both paths
            if phase == "null":
                engine_result = compute_next_phase_engine_path(None, phase)
            else:
                state = _make_state(last_completed_phase=phase)
                engine_result = compute_next_phase_engine_path(state, phase)
            fallback_result = compute_next_phase_fallback(phase)
            # Then they match
            assert engine_result == fallback_result, (
                f"Drift detected for phase '{phase}': "
                f"engine={engine_result}, fallback={fallback_result}"
            )

    def test_fallback_finish_returns_empty_like_engine(self):
        """Fallback for "finish" returns "" (not in phase_map) -- same as engine.
        derived_from: spec:AC-5"""
        # Given "finish" as last phase
        engine_result = compute_next_phase_engine_path(
            _make_state(last_completed_phase="finish"), "finish"
        )
        fallback_result = compute_next_phase_fallback("finish")
        # Then both produce empty string
        assert engine_result == "" and fallback_result == ""

    def test_fallback_unknown_phase_returns_empty_like_engine(self):
        """Fallback for unknown phase returns "" -- same as engine.
        derived_from: spec:NFR-3"""
        # Given an unknown phase
        engine_result = compute_next_phase_engine_path(
            _make_state(last_completed_phase="invalid"), "invalid"
        )
        fallback_result = compute_next_phase_fallback("invalid")
        # Then both produce empty string
        assert engine_result == "" and fallback_result == ""

    def test_fallback_has_no_finish_key(self):
        """The fallback phase_map deliberately omits 'finish' because there
        is no next phase after finish. Verifies the map's structure.
        derived_from: dimension:error_propagation"""
        # Given the fallback phase_map
        phase_map = {
            "null": "specify",
            "brainstorm": "specify",
            "specify": "design",
            "design": "create-plan",
            "create-plan": "create-tasks",
            "create-tasks": "implement",
            "implement": "finish",
        }
        # Then 'finish' is not a key
        assert "finish" not in phase_map


# ===========================================================================
# Dimension 5: Mutation Mindset
# ===========================================================================


class TestMutationMindset:
    """Behavioral pinning tests designed to catch common mutations."""

    def test_index_1_not_0_for_null_case(self):
        """Mutation: PHASE_SEQUENCE[0] instead of [1] would give "brainstorm".
        derived_from: dimension:mutation (line deletion / value swap)"""
        # Given null/empty case
        result = compute_next_phase_engine_path(None, "null")
        # Then result is specifically "specify", not "brainstorm"
        assert result == "specify"
        assert result != PHASE_SEQUENCE[0].value  # NOT brainstorm

    def test_strict_less_than_not_less_equal_for_finish(self):
        """Mutation: changing < to <= would cause IndexError for finish.
        The boundary check is idx < len(_PHASE_VALUES) - 1.
        derived_from: dimension:mutation (boundary shift >= -> >)"""
        # Given finish is at the last index
        finish_idx = _PHASE_VALUES.index("finish")
        # Then idx < len - 1 is False (no next phase)
        assert not (finish_idx < len(_PHASE_VALUES) - 1)
        # And idx <= len - 1 would be True (which is the mutation we guard against)
        assert finish_idx <= len(_PHASE_VALUES) - 1

    def test_or_fallback_converts_none_to_empty(self):
        """Mutation: removing 'or ""' would leave last=None, which wouldn't
        match either 'null' or '' in the if check.
        derived_from: dimension:mutation (line deletion)"""
        # Given state with last_completed_phase=None
        state = _make_state(last_completed_phase=None)
        # When computing (the 'or ""' converts None to "")
        last = state.last_completed_phase or ""
        # Then last is "" not None
        assert last == ""
        assert last is not None

    def test_each_phase_has_unique_successor(self):
        """Mutation: if two phases accidentally mapped to the same successor,
        the workflow would skip a phase. Each phase's successor must be unique.
        derived_from: dimension:mutation (return value mutation)"""
        # Given all non-terminal phases
        successors = []
        for phase_val in _PHASE_VALUES[:-1]:  # exclude finish (no successor)
            state = _make_state(last_completed_phase=phase_val)
            successor = compute_next_phase_engine_path(state, phase_val)
            successors.append(successor)
        # Then all successors are unique
        assert len(successors) == len(set(successors)), (
            f"Duplicate successors found: {successors}"
        )

    def test_sequence_is_contiguous(self):
        """Walking the full sequence from brainstorm produces every phase exactly once.
        Mutation: deleting a phase from PHASE_SEQUENCE would break the chain.
        derived_from: dimension:mutation (line deletion)"""
        # Given we start at brainstorm
        visited = ["brainstorm"]
        current = "brainstorm"
        for _ in range(10):  # safety limit
            state = _make_state(last_completed_phase=current)
            next_phase = compute_next_phase_engine_path(state, current)
            if next_phase == "":
                break
            visited.append(next_phase)
            current = next_phase
        # Then we visit all 7 phases
        expected = ["brainstorm", "specify", "design", "create-plan",
                     "create-tasks", "implement", "finish"]
        assert visited == expected

    def test_implement_successor_is_finish_not_empty(self):
        """Mutation: if the boundary check was wrong, implement could return "".
        implement is at index 5, len-1 = 6, so 5 < 6 is True.
        derived_from: dimension:mutation (boundary shift)"""
        # Given implement at index 5
        implement_idx = _PHASE_VALUES.index("implement")
        # Then it has a successor (idx < len - 1)
        assert implement_idx < len(_PHASE_VALUES) - 1
        # And the successor is specifically "finish"
        result = compute_next_phase_engine_path(
            _make_state(last_completed_phase="implement"), "implement"
        )
        assert result == "finish"
        assert result != ""
