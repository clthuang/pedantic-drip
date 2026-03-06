"""Tests for workflow_state_server processing functions."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time

import pytest

# Ensure hooks/lib is on path for imports
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in sys.path:
    sys.path.insert(0, _hooks_lib)

from entity_registry.database import EntityDatabase
from transition_gate.models import Severity, TransitionResult
from workflow_engine.engine import WorkflowStateEngine
from workflow_engine.models import FeatureWorkflowState, TransitionResponse

from workflow_state_server import (
    _make_error,
    _process_complete_phase,
    _process_get_phase,
    _process_list_features_by_phase,
    _process_list_features_by_status,
    _process_transition_phase,
    _process_validate_prerequisites,
    _serialize_result,
    _serialize_state,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """In-memory database with schema."""
    return EntityDatabase(":memory:")


@pytest.fixture
def engine(db, tmp_path):
    """Engine backed by in-memory DB."""
    return WorkflowStateEngine(db, str(tmp_path))


@pytest.fixture
def seeded_engine(engine, db, tmp_path):
    """Engine with a test feature seeded in DB.

    Feature 'feature:009-test' is at workflow_phase='specify'.
    A feature directory with .meta.json is created so the engine
    can resolve artifact paths.
    """
    db.register_entity("feature", "009-test", "Test Feature", status="active")
    db.create_workflow_phase("feature:009-test", workflow_phase="specify")

    # Create feature directory with minimal .meta.json for artifact resolution
    feat_dir = os.path.join(str(tmp_path), "features", "009-test")
    os.makedirs(feat_dir, exist_ok=True)
    with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
        f.write('{"id": "009", "slug": "test", "status": "active", "mode": "standard"}')

    return engine


# ---------------------------------------------------------------------------
# Serialization tests (Task 2.2)
# ---------------------------------------------------------------------------


class TestSerializeState:
    def test_returns_dict_with_correct_keys(self):
        state = FeatureWorkflowState(
            feature_type_id="feature:009-test",
            current_phase="specify",
            last_completed_phase=None,
            completed_phases=("brainstorm",),
            mode="standard",
            source="entity_db",
        )
        result = _serialize_state(state)
        assert isinstance(result, dict)
        assert set(result.keys()) == {
            "feature_type_id", "current_phase", "last_completed_phase",
            "completed_phases", "mode", "source", "degraded",
        }

    def test_completed_phases_tuple_to_list(self):
        state = FeatureWorkflowState(
            feature_type_id="feature:009-test",
            current_phase="design",
            last_completed_phase="specify",
            completed_phases=("brainstorm", "specify"),
            mode="standard",
            source="entity_db",
        )
        result = _serialize_state(state)
        assert isinstance(result["completed_phases"], list)
        assert result["completed_phases"] == ["brainstorm", "specify"]

    def test_degraded_false_for_db_source(self):
        state = FeatureWorkflowState(
            feature_type_id="feature:009-test",
            current_phase="specify",
            last_completed_phase=None,
            completed_phases=(),
            mode="standard",
            source="db",
        )
        result = _serialize_state(state)
        assert result["degraded"] is False

    def test_degraded_true_for_meta_json_fallback(self):
        state = FeatureWorkflowState(
            feature_type_id="feature:009-test",
            current_phase="specify",
            last_completed_phase=None,
            completed_phases=(),
            mode="standard",
            source="meta_json_fallback",
        )
        result = _serialize_state(state)
        assert result["degraded"] is True

    def test_degraded_false_for_meta_json_source(self):
        state = FeatureWorkflowState(
            feature_type_id="feature:009-test",
            current_phase="specify",
            last_completed_phase=None,
            completed_phases=(),
            mode="standard",
            source="meta_json",
        )
        result = _serialize_state(state)
        assert result["degraded"] is False


class TestSerializeResult:
    def test_severity_is_string(self):
        tr = TransitionResult(
            allowed=True,
            reason="All OK",
            severity=Severity.info,
            guard_id="G-22",
        )
        result = _serialize_result(tr)
        assert isinstance(result["severity"], str)
        assert result["severity"] == "info"

    def test_returns_dict_with_correct_keys(self):
        tr = TransitionResult(
            allowed=False,
            reason="Blocked",
            severity=Severity.block,
            guard_id="G-08",
        )
        result = _serialize_result(tr)
        assert set(result.keys()) == {"allowed", "reason", "severity", "guard_id"}
        assert result["allowed"] is False
        assert result["guard_id"] == "G-08"


# ---------------------------------------------------------------------------
# _make_error tests (Task 1.5)
# ---------------------------------------------------------------------------


class TestMakeError:
    """Tests for the _make_error structured error helper."""

    def test_returns_valid_json_string(self):
        """_make_error returns a parseable JSON string."""
        result = _make_error("internal", "Something broke", "Report this error")
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_json_has_required_keys(self):
        """JSON structure has exactly error, error_type, message, recovery_hint."""
        result = _make_error("internal", "Something broke", "Report this error")
        data = json.loads(result)
        assert set(data.keys()) == {"error", "error_type", "message", "recovery_hint"}

    def test_error_field_is_true(self):
        """The error field is always boolean True."""
        result = _make_error("internal", "Something broke", "Report this error")
        data = json.loads(result)
        assert data["error"] is True

    def test_fields_match_arguments(self):
        """error_type, message, recovery_hint match the arguments passed."""
        result = _make_error("db_unavailable", "DB is down", "Check DB file")
        data = json.loads(result)
        assert data["error_type"] == "db_unavailable"
        assert data["message"] == "DB is down"
        assert data["recovery_hint"] == "Check DB file"

    def test_error_type_db_unavailable(self):
        """db_unavailable error_type produces valid JSON."""
        result = _make_error("db_unavailable", "DB locked", "Check DB file at /path")
        data = json.loads(result)
        assert data["error_type"] == "db_unavailable"
        assert data["error"] is True

    def test_error_type_feature_not_found(self):
        """feature_not_found error_type produces valid JSON."""
        result = _make_error(
            "feature_not_found",
            "Feature not found: feature:099-missing",
            "Verify feature_type_id format: 'feature:{id}-{slug}'",
        )
        data = json.loads(result)
        assert data["error_type"] == "feature_not_found"
        assert data["error"] is True

    def test_error_type_invalid_transition(self):
        """invalid_transition error_type produces valid JSON."""
        result = _make_error(
            "invalid_transition",
            "Cannot transition to design",
            "Check phase name and current state",
        )
        data = json.loads(result)
        assert data["error_type"] == "invalid_transition"
        assert data["error"] is True

    def test_error_type_internal(self):
        """internal error_type produces valid JSON."""
        result = _make_error("internal", "Unexpected error", "Report this error")
        data = json.loads(result)
        assert data["error_type"] == "internal"
        assert data["error"] is True

    def test_error_type_not_initialized(self):
        """not_initialized error_type produces valid JSON."""
        result = _make_error(
            "not_initialized", "Engine not initialized", "Restart MCP server"
        )
        data = json.loads(result)
        assert data["error_type"] == "not_initialized"
        assert data["error"] is True

    def test_all_error_types_produce_valid_json(self):
        """All documented error_type values produce parseable JSON with correct structure."""
        error_types = [
            "db_unavailable",
            "feature_not_found",
            "invalid_transition",
            "internal",
            "not_initialized",
        ]
        for error_type in error_types:
            result = _make_error(error_type, f"msg for {error_type}", "hint")
            data = json.loads(result)
            assert data["error"] is True, f"error field wrong for {error_type}"
            assert data["error_type"] == error_type
            assert data["message"] == f"msg for {error_type}"
            assert data["recovery_hint"] == "hint"


# ---------------------------------------------------------------------------
# _process_get_phase tests (Task 2.3)
# ---------------------------------------------------------------------------


class TestProcessGetPhase:
    def test_success(self, seeded_engine):
        result = _process_get_phase(seeded_engine, "feature:009-test")
        data = json.loads(result)
        assert data["feature_type_id"] == "feature:009-test"
        assert data["current_phase"] == "specify"

    def test_not_found(self, engine):
        result = _process_get_phase(engine, "feature:nonexistent")
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "feature_not_found"
        assert "feature:nonexistent" in data["message"]

    def test_unexpected_exception(self, seeded_engine, monkeypatch):
        monkeypatch.setattr(seeded_engine, "get_state", lambda *a: 1 / 0)
        result = _process_get_phase(seeded_engine, "feature:009-test")
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "internal"
        assert "ZeroDivisionError" in data["message"]


# ---------------------------------------------------------------------------
# _process_transition_phase tests (Task 2.4)
# ---------------------------------------------------------------------------


class TestProcessTransitionPhase:
    def test_success(self, seeded_engine, tmp_path):
        # Create spec.md so G-08 hard prereq passes for design
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")

        result = _process_transition_phase(
            seeded_engine, "feature:009-test", "design", False
        )
        data = json.loads(result)
        assert data["transitioned"] is True
        assert data["degraded"] is False

    def test_blocked_g08(self, seeded_engine):
        # No spec.md in tmp_path → G-08 blocks transition to design
        result = _process_transition_phase(
            seeded_engine, "feature:009-test", "design", False
        )
        data = json.loads(result)
        assert data["transitioned"] is False

        # Verify G-08 fired
        guard_ids = [r["guard_id"] for r in data["results"]]
        assert "G-08" in guard_ids
        g08_result = next(r for r in data["results"] if r["guard_id"] == "G-08")
        assert g08_result["allowed"] is False

    def test_yolo_active_changes_behavior(self, seeded_engine, tmp_path):
        """Verify YOLO changes G-23 reason text.

        Note: G-23 is soft_warn — it returns allowed=True regardless of YOLO.
        YOLO changes the reason text to 'Auto-selected default in YOLO mode'.
        Both calls return transitioned=True when spec.md exists.
        """
        # Create spec.md so G-08 passes
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")

        # Without YOLO
        result_no_yolo = _process_transition_phase(
            seeded_engine, "feature:009-test", "design", False
        )
        data_no_yolo = json.loads(result_no_yolo)

        # Re-seed the feature (transition moved it to design)
        seeded_engine.db.update_workflow_phase("feature:009-test", workflow_phase="specify")

        # With YOLO
        result_yolo = _process_transition_phase(
            seeded_engine, "feature:009-test", "design", True
        )
        data_yolo = json.loads(result_yolo)

        assert data_yolo["transitioned"] is True

        # Verify G-23 reason text differs between YOLO and non-YOLO
        g23_no_yolo = next(
            (r for r in data_no_yolo["results"] if r["guard_id"] == "G-23"), None
        )
        g23_yolo = next(
            (r for r in data_yolo["results"] if r["guard_id"] == "G-23"), None
        )
        assert g23_no_yolo is not None, "G-23 should appear in non-YOLO results"
        assert g23_yolo is not None, "G-23 should appear in YOLO results"
        assert "Auto-selected" in g23_yolo["reason"]

    def test_value_error(self, seeded_engine, monkeypatch):
        monkeypatch.setattr(
            seeded_engine, "transition_phase",
            lambda *a, **kw: (_ for _ in ()).throw(ValueError("bad phase")),
        )
        result = _process_transition_phase(
            seeded_engine, "feature:009-test", "nonexistent", False
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "invalid_transition"
        assert "bad phase" in data["message"]

    def test_unexpected_exception(self, seeded_engine, monkeypatch):
        monkeypatch.setattr(
            seeded_engine, "transition_phase",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        result = _process_transition_phase(
            seeded_engine, "feature:009-test", "design", False
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "internal"
        assert "RuntimeError" in data["message"]


# ---------------------------------------------------------------------------
# _process_complete_phase tests (Task 2.5)
# ---------------------------------------------------------------------------


class TestProcessCompletePhase:
    def test_success(self, seeded_engine):
        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "specify"
        )
        data = json.loads(result)
        assert "specify" in data["completed_phases"]

    def test_value_error(self, seeded_engine, monkeypatch):
        monkeypatch.setattr(
            seeded_engine, "complete_phase",
            lambda *a: (_ for _ in ()).throw(ValueError("phase mismatch")),
        )
        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "design"
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "invalid_transition"
        assert "phase mismatch" in data["message"]

    def test_unexpected_exception(self, seeded_engine, monkeypatch):
        monkeypatch.setattr(
            seeded_engine, "complete_phase",
            lambda *a: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "specify"
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "internal"
        assert "RuntimeError" in data["message"]


# ---------------------------------------------------------------------------
# _process_validate_prerequisites tests (Task 2.6)
# ---------------------------------------------------------------------------


class TestProcessValidatePrerequisites:
    def test_pass(self, seeded_engine, tmp_path):
        # Create spec.md so G-08 passes for design
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")

        result = _process_validate_prerequisites(
            seeded_engine, "feature:009-test", "design"
        )
        data = json.loads(result)
        assert data["all_passed"] is True

    def test_fail(self, seeded_engine):
        # No spec.md → G-08 blocks
        result = _process_validate_prerequisites(
            seeded_engine, "feature:009-test", "design"
        )
        data = json.loads(result)
        assert data["all_passed"] is False
        assert len(data["results"]) > 0

    def test_value_error(self, seeded_engine, monkeypatch):
        monkeypatch.setattr(
            seeded_engine, "validate_prerequisites",
            lambda *a: (_ for _ in ()).throw(ValueError("unknown feature")),
        )
        result = _process_validate_prerequisites(
            seeded_engine, "feature:009-test", "design"
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "invalid_transition"
        assert "unknown feature" in data["message"]

    def test_unexpected_exception(self, seeded_engine, monkeypatch):
        monkeypatch.setattr(
            seeded_engine, "validate_prerequisites",
            lambda *a: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        result = _process_validate_prerequisites(
            seeded_engine, "feature:009-test", "design"
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "internal"
        assert "RuntimeError" in data["message"]

    def test_no_mutation(self, seeded_engine, tmp_path):
        """validate_prerequisites should not change DB state."""
        # Create spec.md
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")

        state_before = _process_get_phase(seeded_engine, "feature:009-test")
        _process_validate_prerequisites(seeded_engine, "feature:009-test", "design")
        state_after = _process_get_phase(seeded_engine, "feature:009-test")
        assert state_before == state_after


# ---------------------------------------------------------------------------
# _process_list_features_by_phase tests (Task 2.7)
# ---------------------------------------------------------------------------


class TestProcessListFeaturesByPhase:
    def test_populated(self, seeded_engine):
        result = _process_list_features_by_phase(seeded_engine, "specify")
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["current_phase"] == "specify"

    def test_empty(self, engine):
        result = _process_list_features_by_phase(engine, "nonexistent_phase")
        data = json.loads(result)
        assert data == []

    def test_unexpected_exception(self, seeded_engine, monkeypatch):
        monkeypatch.setattr(
            seeded_engine, "list_by_phase",
            lambda *a: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        result = _process_list_features_by_phase(seeded_engine, "specify")
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "internal"
        assert "RuntimeError" in data["message"]


# ---------------------------------------------------------------------------
# _process_list_features_by_status tests (Task 2.8)
# ---------------------------------------------------------------------------


class TestProcessListFeaturesByStatus:
    def test_populated(self, seeded_engine):
        result = _process_list_features_by_status(seeded_engine, "active")
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_empty(self, engine):
        result = _process_list_features_by_status(engine, "nonexistent_status")
        data = json.loads(result)
        assert data == []

    def test_unexpected_exception(self, seeded_engine, monkeypatch):
        monkeypatch.setattr(
            seeded_engine, "list_by_status",
            lambda *a: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        result = _process_list_features_by_status(seeded_engine, "active")
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "internal"
        assert "RuntimeError" in data["message"]


# ---------------------------------------------------------------------------
# Performance tests (Task 5.4)
# ---------------------------------------------------------------------------


@pytest.fixture
def perf_engine(tmp_path):
    """Engine with 50 seeded features for performance testing."""
    db = EntityDatabase(":memory:")
    for i in range(50):
        db.register_entity("feature", f"perf-{i:03d}", f"Perf Test {i}", status="active")
        db.create_workflow_phase(f"feature:perf-{i:03d}", workflow_phase="specify")

        # Create feature directory with .meta.json
        feat_dir = os.path.join(str(tmp_path), "features", f"perf-{i:03d}")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            f.write(f'{{"id": "perf-{i:03d}", "slug": "perf-{i:03d}", "status": "active", "mode": "standard"}}')

    return WorkflowStateEngine(db, str(tmp_path))


class TestPerformance:
    def test_get_phase(self, perf_engine):
        start = time.perf_counter()
        _process_get_phase(perf_engine, "feature:perf-025")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1, f"get_phase took {elapsed:.3f}s (>100ms)"

    def test_list_by_phase(self, perf_engine):
        start = time.perf_counter()
        _process_list_features_by_phase(perf_engine, "specify")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1, f"list_by_phase took {elapsed:.3f}s (>100ms)"

    def test_list_by_status(self, perf_engine):
        start = time.perf_counter()
        _process_list_features_by_status(perf_engine, "active")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1, f"list_by_status took {elapsed:.3f}s (>100ms)"

    def test_validate_prerequisites(self, perf_engine):
        start = time.perf_counter()
        _process_validate_prerequisites(perf_engine, "feature:perf-025", "design")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1, f"validate_prerequisites took {elapsed:.3f}s (>100ms)"


# ---------------------------------------------------------------------------
# Test-deepener: Boundary Value tests
# derived_from: dimension:boundary_values
# ---------------------------------------------------------------------------


class TestBoundaryValues:
    """Boundary value analysis for edge-case inputs."""

    def test_get_phase_empty_string_feature_id(self, engine):
        """Empty feature_type_id returns 'Feature not found' not a crash.
        derived_from: dimension:boundary_values (empty-string input)

        Anticipate: Implementation might not handle empty-string feature_type_id,
        causing KeyError or unhandled exception instead of clean 'not found'.
        """
        # Given an engine with no features registered
        # When _process_get_phase is called with an empty feature_type_id
        result = _process_get_phase(engine, "")
        # Then it returns a structured error JSON
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "feature_not_found"

    def test_list_features_by_phase_empty_string_phase(self, engine):
        """Empty string phase returns empty JSON array, not error.
        derived_from: dimension:boundary_values (empty-string input)

        Anticipate: DB query with empty phase could misbehave or throw.
        """
        # Given an engine with no features
        # When listing by empty-string phase
        result = _process_list_features_by_phase(engine, "")
        # Then we get a valid empty JSON array
        data = json.loads(result)
        assert data == []

    def test_list_features_by_status_empty_string_status(self, engine):
        """Empty string status returns empty JSON array, not error.
        derived_from: dimension:boundary_values (empty-string input)

        Anticipate: Status filtering with empty string could match entities
        with None status or crash.
        """
        # Given an engine with no features
        # When listing by empty-string status
        result = _process_list_features_by_status(engine, "")
        # Then we get a valid empty JSON array
        data = json.loads(result)
        assert data == []

    def test_transition_phase_empty_target_phase_returns_json(self, seeded_engine):
        """Transition to empty-string target returns gate results JSON, not crash.
        derived_from: dimension:boundary_values (empty-string input)

        Anticipate: Empty target_phase could cause IndexError or KeyError
        in gate evaluation rather than returning structured JSON.
        """
        # Given a seeded feature at phase 'specify'
        # When transitioning to empty-string target phase
        result = _process_transition_phase(
            seeded_engine, "feature:009-test", "", False
        )
        # Then we get parseable JSON (gate results or error), not a crash
        # The gates should evaluate and return results
        assert isinstance(result, str)
        # Must be valid JSON — either gate results or structured error
        data = json.loads(result)
        # Either gate results (transitioned/results) or structured error (error/error_type)
        assert ("results" in data or "transitioned" in data) or data.get("error") is True

    def test_list_features_by_phase_50_features_returns_all(self, perf_engine):
        """List-by-phase with 50 features returns all 50 without truncation.
        derived_from: dimension:boundary_values (large collection)

        Anticipate: Implementation might silently truncate results due to
        pagination, LIMIT clause, or serialization cap.
        """
        # Given 50 features all at phase 'specify'
        # When listing features by that phase
        result = _process_list_features_by_phase(perf_engine, "specify")
        data = json.loads(result)
        # Then all 50 features are returned
        assert len(data) == 50

    def test_serialize_state_empty_completed_phases(self):
        """Empty completed_phases tuple serializes to empty list.
        derived_from: dimension:boundary_values (empty collection)

        Anticipate: list(()) is [] but a mutation swapping to str() or
        leaving as tuple would break JSON consumers expecting array type.
        """
        # Given a state with no completed phases
        state = FeatureWorkflowState(
            feature_type_id="feature:010-test",
            current_phase="brainstorm",
            last_completed_phase=None,
            completed_phases=(),
            mode="standard",
            source="db",
        )
        # When serialized
        result = _serialize_state(state)
        # Then completed_phases is an empty list (not tuple, not None)
        assert result["completed_phases"] == []
        assert isinstance(result["completed_phases"], list)

    def test_serialize_state_multiple_completed_phases_preserves_order(self):
        """Multiple completed phases maintain insertion order after serialization.
        derived_from: dimension:boundary_values (multi-element collection)

        Anticipate: Serialization might sort or reverse the phase list,
        breaking downstream consumers that rely on chronological order.
        """
        # Given a state with 3 completed phases in chronological order
        state = FeatureWorkflowState(
            feature_type_id="feature:010-test",
            current_phase="create-plan",
            last_completed_phase="design",
            completed_phases=("brainstorm", "specify", "design"),
            mode="standard",
            source="db",
        )
        # When serialized
        result = _serialize_state(state)
        # Then the order is preserved exactly
        assert result["completed_phases"] == ["brainstorm", "specify", "design"]


# ---------------------------------------------------------------------------
# Test-deepener: Adversarial / Negative tests
# derived_from: dimension:adversarial
# ---------------------------------------------------------------------------


class TestAdversarial:
    """Adversarial inputs and invariant-violation tests."""

    def test_yolo_does_not_bypass_hard_block_g08(self, seeded_engine):
        """YOLO=True must NOT override G-08 (hard_block, yolo_behavior=unchanged).
        derived_from: spec:AC-4 (YOLO only overrides soft gates)

        Anticipate: If YOLO override logic checks yolo_active before checking
        enforcement level, G-08 could be silently skipped.
        Challenge: This test directly asserts G-08 still blocks even with yolo=True.
        """
        # Given a seeded feature at 'specify' with NO spec.md (G-08 requires it)
        # When transitioning to 'design' with yolo=True
        result = _process_transition_phase(
            seeded_engine, "feature:009-test", "design", True
        )
        data = json.loads(result)
        # Then transition is still blocked
        assert data["transitioned"] is False
        # And G-08 specifically blocked it
        g08 = next(r for r in data["results"] if r["guard_id"] == "G-08")
        assert g08["allowed"] is False
        assert g08["severity"] == "block"

    def test_complete_phase_wrong_phase_returns_error(self, seeded_engine):
        """Completing a phase that doesn't match current_phase returns ValueError.
        derived_from: spec:AC-5 (complete_phase validates current phase)

        Anticipate: If phase mismatch check is missing, a feature at 'specify'
        could mark 'design' as completed, corrupting the workflow state.
        """
        # Given a feature at current_phase='specify'
        # When trying to complete 'design' (not the current phase)
        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "design"
        )
        # Then the server returns a structured error
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "invalid_transition"
        assert "mismatch" in data["message"].lower() or "cannot complete" in data["message"].lower()

    def test_complete_phase_nonexistent_feature_returns_error(self, engine):
        """Completing a phase for a nonexistent feature returns ValueError error.
        derived_from: spec:AC-5 (complete_phase validates feature existence)

        Anticipate: If feature existence check is missing before phase completion,
        it could cause NoneType errors or corrupt DB.
        """
        # Given an engine with no features
        # When completing a phase for a nonexistent feature
        result = _process_complete_phase(
            engine, "feature:nonexistent", "specify"
        )
        # Then the server returns a structured error
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "invalid_transition"
        assert "not found" in data["message"].lower()

    def test_transition_result_json_has_exact_key_set(self, seeded_engine):
        """Transition response JSON has exactly {transitioned, results, degraded}.
        derived_from: dimension:adversarial (JSON shape contract)

        Anticipate: Extra or missing keys would break MCP clients parsing the
        response. A mutation adding or removing a key goes undetected without
        an exact-set assertion.
        """
        # Given a seeded feature
        # When transitioning (will be blocked by G-08, but that's fine)
        result = _process_transition_phase(
            seeded_engine, "feature:009-test", "design", False
        )
        data = json.loads(result)
        # Then the top-level keys are exactly {transitioned, results, degraded}
        assert set(data.keys()) == {"transitioned", "results", "degraded"}

    def test_validate_result_json_has_exact_key_set(self, seeded_engine):
        """Validate response JSON has exactly {all_passed, results}.
        derived_from: dimension:adversarial (JSON shape contract)

        Anticipate: If validate_prerequisites response shape diverges from
        transition_phase shape, clients must handle both. Pinning the exact
        keys prevents silent contract drift.
        """
        # Given a seeded feature
        # When validating prerequisites for 'design'
        result = _process_validate_prerequisites(
            seeded_engine, "feature:009-test", "design"
        )
        data = json.loads(result)
        # Then the top-level keys are exactly {all_passed, results}
        assert set(data.keys()) == {"all_passed", "results"}

    def test_get_phase_result_json_has_all_six_fields(self, seeded_engine):
        """get_phase JSON response contains all 6 state fields.
        derived_from: dimension:adversarial (JSON shape contract)

        Anticipate: A field could be accidentally omitted from _serialize_state,
        causing downstream consumers to fail on missing key access.
        """
        # Given a seeded feature
        # When reading its phase
        result = _process_get_phase(seeded_engine, "feature:009-test")
        data = json.loads(result)
        # Then all 6 fields are present
        expected_keys = {
            "feature_type_id", "current_phase", "last_completed_phase",
            "completed_phases", "mode", "source", "degraded",
        }
        assert set(data.keys()) == expected_keys

    def test_transition_result_item_json_has_exact_key_set(self, seeded_engine):
        """Each item in transition results[] has {allowed, reason, severity, guard_id}.
        derived_from: dimension:adversarial (JSON shape contract)

        Anticipate: _serialize_result could silently drop a field or add extras.
        """
        # Given a seeded feature
        # When transitioning (blocked by G-08)
        result = _process_transition_phase(
            seeded_engine, "feature:009-test", "design", False
        )
        data = json.loads(result)
        # Then each result item has exactly 4 keys
        for item in data["results"]:
            assert set(item.keys()) == {"allowed", "reason", "severity", "guard_id"}


# ---------------------------------------------------------------------------
# Test-deepener: Mutation Mindset tests
# derived_from: dimension:mutation_mindset
# ---------------------------------------------------------------------------


class TestMutationMindset:
    """Tests designed to catch specific mutations in the implementation."""

    def test_transitioned_uses_all_not_any(self, seeded_engine, monkeypatch):
        """transitioned must be True only when ALL results are allowed, not just any.
        derived_from: dimension:mutation_mindset (logic inversion: all -> any)

        Anticipate: Swapping all() to any() in _process_transition_phase would
        let a transition succeed when some gates block. This test provides one
        allowed and one blocked result to catch that mutation.
        """
        # Given: monkeypatch engine.transition_phase to return mixed results
        mixed_results = [
            TransitionResult(allowed=True, reason="OK", severity=Severity.info, guard_id="G-23"),
            TransitionResult(allowed=False, reason="Blocked", severity=Severity.block, guard_id="G-08"),
        ]
        monkeypatch.setattr(
            seeded_engine, "transition_phase",
            lambda *a, **kw: TransitionResponse(results=tuple(mixed_results), degraded=False),
        )
        # When transitioning
        result = _process_transition_phase(
            seeded_engine, "feature:009-test", "design", False
        )
        data = json.loads(result)
        # Then transitioned must be False (all() would be False, any() would be True)
        assert data["transitioned"] is False
        assert data["degraded"] is False

    def test_all_passed_uses_all_not_any(self, seeded_engine, monkeypatch):
        """all_passed must be True only when ALL results are allowed, not just any.
        derived_from: dimension:mutation_mindset (logic inversion: all -> any)

        Anticipate: Same mutation as above but in _process_validate_prerequisites.
        """
        # Given: monkeypatch engine.validate_prerequisites to return mixed results
        mixed_results = [
            TransitionResult(allowed=True, reason="OK", severity=Severity.info, guard_id="G-23"),
            TransitionResult(allowed=False, reason="Blocked", severity=Severity.block, guard_id="G-08"),
        ]
        monkeypatch.setattr(
            seeded_engine, "validate_prerequisites",
            lambda *a: mixed_results,
        )
        # When validating prerequisites
        result = _process_validate_prerequisites(
            seeded_engine, "feature:009-test", "design"
        )
        data = json.loads(result)
        # Then all_passed must be False (all() would be False, any() would be True)
        assert data["all_passed"] is False

    def test_get_phase_none_state_returns_not_found(self, seeded_engine, monkeypatch):
        """When get_state returns None, result must be 'Feature not found', not crash.
        derived_from: dimension:mutation_mindset (line deletion: None guard)

        Anticipate: Deleting the 'if state is None' check would cause
        AttributeError when trying to serialize None.
        """
        # Given: monkeypatch engine.get_state to return None
        monkeypatch.setattr(seeded_engine, "get_state", lambda *a: None)
        # When getting phase for a (nominally existing) feature
        result = _process_get_phase(seeded_engine, "feature:009-test")
        # Then we get the not-found structured error, not an exception
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "feature_not_found"
        assert "feature:009-test" in data["message"]
        # Verify it is NOT an internal error (would mean None slipped through)
        assert data["error_type"] != "internal"


# ---------------------------------------------------------------------------
# Test-deepener: Error Propagation tests
# derived_from: dimension:error_propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    """Verify error classification matches the documented contract."""

    def test_list_by_phase_valueerror_caught_as_internal(self, seeded_engine, monkeypatch):
        """ValueError in list_by_phase is classified as 'Internal error:', not 'Error:'.
        derived_from: dimension:error_propagation (error classification contract)

        Anticipate: list_by_phase has no explicit ValueError handler -- only
        'except Exception'. A ValueError (e.g., corrupt DB row) must be
        'Internal error:' since it's not a user-input validation error.
        Challenge: If someone adds 'except ValueError' before 'except Exception',
        it could incorrectly classify as 'Error:'.
        """
        # Given: monkeypatch to raise ValueError (simulating corrupt DB row)
        monkeypatch.setattr(
            seeded_engine, "list_by_phase",
            lambda *a: (_ for _ in ()).throw(ValueError("corrupt row")),
        )
        # When listing by phase
        result = _process_list_features_by_phase(seeded_engine, "specify")
        # Then the error is classified as "internal", not "invalid_transition"
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "internal"
        assert "ValueError" in data["message"]

    def test_list_by_status_valueerror_caught_as_internal(self, seeded_engine, monkeypatch):
        """ValueError in list_by_status is classified as 'internal', not 'invalid_transition'.
        derived_from: dimension:error_propagation (error classification contract)

        Anticipate: Same pattern as list_by_phase -- no explicit ValueError handler.
        """
        # Given: monkeypatch to raise ValueError
        monkeypatch.setattr(
            seeded_engine, "list_by_status",
            lambda *a: (_ for _ in ()).throw(ValueError("corrupt data")),
        )
        # When listing by status
        result = _process_list_features_by_status(seeded_engine, "active")
        # Then the error is classified as "internal", not "invalid_transition"
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "internal"
        assert "ValueError" in data["message"]

    def test_get_phase_valueerror_caught_as_internal(self, seeded_engine, monkeypatch):
        """ValueError in get_state is classified as 'internal', not 'invalid_transition'.
        derived_from: dimension:error_propagation (error classification contract)

        Anticipate: _process_get_phase has no explicit ValueError handler --
        only 'except Exception'. Any ValueError from engine internals must
        surface as 'internal' error_type.
        """
        # Given: monkeypatch to raise ValueError
        monkeypatch.setattr(
            seeded_engine, "get_state",
            lambda *a: (_ for _ in ()).throw(ValueError("bad type_id")),
        )
        # When getting phase
        result = _process_get_phase(seeded_engine, "feature:009-test")
        # Then the error is classified as "internal", not "invalid_transition"
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "internal"
        assert "ValueError" in data["message"]


# ---------------------------------------------------------------------------
# Integration: Degradation signal propagation (Task 6.2)
# ---------------------------------------------------------------------------


class TestIntegrationDegradation:
    """Verify degraded=True propagates correctly when DB is closed.

    Each test closes the DB connection to trigger the engine's fallback path.
    A .meta.json file is created so the fallback has data to return.
    """

    @pytest.fixture
    def degraded_engine(self, db, tmp_path):
        """Engine with a seeded feature whose DB is then closed.

        The .meta.json is created before close so fallback reads succeed.
        Returns (engine, tmp_path) so tests can inspect the artifacts root.
        """
        db.register_entity("feature", "009-test", "Test Feature", status="active")
        db.create_workflow_phase("feature:009-test", workflow_phase="specify")

        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            f.write(
                '{"id": "009", "slug": "test", "status": "active",'
                ' "mode": "standard", "lastCompletedPhase": null}'
            )

        engine = WorkflowStateEngine(db, str(tmp_path))
        db.close()  # Trigger degraded mode
        return engine

    def test_get_phase_db_closed_returns_degraded(self, degraded_engine):
        """_process_get_phase with closed DB returns state with degraded=True."""
        result = _process_get_phase(degraded_engine, "feature:009-test")
        data = json.loads(result)
        # Must be a state dict (not an error), with degraded=True
        assert "error" not in data
        assert data["degraded"] is True
        assert data["feature_type_id"] == "feature:009-test"

    def test_transition_phase_db_closed_returns_degraded(self, degraded_engine):
        """_process_transition_phase with closed DB returns response with degraded=True."""
        result = _process_transition_phase(
            degraded_engine, "feature:009-test", "design", False
        )
        data = json.loads(result)
        # Must be a transition response dict (not an error), with degraded=True
        assert "error" not in data
        assert data["degraded"] is True
        assert "results" in data
        assert "transitioned" in data

    def test_complete_phase_db_closed_returns_degraded(self, degraded_engine):
        """_process_complete_phase with closed DB writes to .meta.json and returns degraded=True.

        The .meta.json has lastCompletedPhase=null and status=active, so the
        fallback engine resolves current_phase='brainstorm' (first phase).
        Completing 'brainstorm' matches that current phase and succeeds.
        """
        result = _process_complete_phase(
            degraded_engine, "feature:009-test", "brainstorm"
        )
        data = json.loads(result)
        # Must be a state dict (not an error), with degraded=True
        assert "error" not in data
        assert data["degraded"] is True
        assert "brainstorm" in data["completed_phases"]

    def test_list_features_by_phase_db_closed_returns_degraded_states(
        self, degraded_engine
    ):
        """_process_list_features_by_phase with closed DB returns states with degraded=True."""
        result = _process_list_features_by_phase(degraded_engine, "brainstorm")
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) >= 1
        for state in data:
            assert state["degraded"] is True

    def test_list_features_by_status_db_closed_returns_degraded_states(
        self, degraded_engine
    ):
        """_process_list_features_by_status with closed DB returns states with degraded=True."""
        result = _process_list_features_by_status(degraded_engine, "active")
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) >= 1
        for state in data:
            assert state["degraded"] is True


# ---------------------------------------------------------------------------
# Structured error format verification (Task 6.2)
# ---------------------------------------------------------------------------


class TestStructuredErrorFormat:
    """Verify JSON error structure for all 5 documented error types.

    Each test calls _make_error with a specific error_type and asserts the
    exact JSON structure: {error: true, error_type, message, recovery_hint}.
    """

    _REQUIRED_KEYS = {"error", "error_type", "message", "recovery_hint"}

    def _parse_and_check(self, error_type: str, message: str, hint: str) -> dict:
        """Helper: call _make_error and return parsed dict after structure checks."""
        raw = _make_error(error_type, message, hint)
        data = json.loads(raw)
        assert set(data.keys()) == self._REQUIRED_KEYS, (
            f"Expected keys {self._REQUIRED_KEYS}, got {set(data.keys())}"
        )
        assert data["error"] is True
        assert data["error_type"] == error_type
        assert data["message"] == message
        assert data["recovery_hint"] == hint
        return data

    def test_db_unavailable_structure(self):
        """db_unavailable error has exact required JSON structure."""
        data = self._parse_and_check(
            "db_unavailable",
            "Database error: ProgrammingError: Cannot operate on a closed database.",
            "Check database file permissions and disk space",
        )
        assert data["error_type"] == "db_unavailable"

    def test_feature_not_found_structure(self):
        """feature_not_found error has exact required JSON structure."""
        data = self._parse_and_check(
            "feature_not_found",
            "Feature not found: feature:099-missing",
            "Verify feature_type_id format: 'feature:{id}-{slug}'",
        )
        assert data["error_type"] == "feature_not_found"

    def test_invalid_transition_structure(self):
        """invalid_transition error has exact required JSON structure."""
        data = self._parse_and_check(
            "invalid_transition",
            "Error: Cannot transition to design",
            "Check current phase with get_phase before transitioning",
        )
        assert data["error_type"] == "invalid_transition"

    def test_internal_structure(self):
        """internal error has exact required JSON structure."""
        data = self._parse_and_check(
            "internal",
            "Internal error: RuntimeError: unexpected failure",
            "Report this error — it may indicate a bug",
        )
        assert data["error_type"] == "internal"

    def test_not_initialized_structure(self):
        """not_initialized error has exact required JSON structure."""
        data = self._parse_and_check(
            "not_initialized",
            "Engine not initialized (server not started)",
            "Wait for server startup or restart the MCP server",
        )
        assert data["error_type"] == "not_initialized"

    def test_all_five_error_types_have_identical_structure(self):
        """All 5 error types produce the same top-level JSON structure."""
        error_types = [
            "db_unavailable",
            "feature_not_found",
            "invalid_transition",
            "internal",
            "not_initialized",
        ]
        for error_type in error_types:
            raw = _make_error(error_type, f"msg {error_type}", f"hint {error_type}")
            data = json.loads(raw)
            assert set(data.keys()) == self._REQUIRED_KEYS, (
                f"{error_type}: expected keys {self._REQUIRED_KEYS}, "
                f"got {set(data.keys())}"
            )
            assert data["error"] is True, f"{error_type}: error field must be True"
            assert isinstance(data["error_type"], str), (
                f"{error_type}: error_type must be a string"
            )
            assert isinstance(data["message"], str), (
                f"{error_type}: message must be a string"
            )
            assert isinstance(data["recovery_hint"], str), (
                f"{error_type}: recovery_hint must be a string"
            )


# ---------------------------------------------------------------------------
# Test-deepener: Feature 010 Graceful Degradation (Phase B)
# ---------------------------------------------------------------------------


class TestSqlite3ErrorThroughMcpTools:
    """Dimension 4 (error propagation): sqlite3.Error propagates as structured
    'db_unavailable' error through all MCP processing functions.

    Anticipate: If _with_error_handling does not catch sqlite3.Error for a
    specific tool, the raw exception would propagate to the MCP transport,
    breaking the JSON-RPC protocol.
    derived_from: dimension:error_propagation (all 5 error types through MCP)
    """

    def test_get_phase_sqlite_error_returns_db_unavailable(
        self, seeded_engine, monkeypatch
    ):
        """sqlite3.Error in get_state produces db_unavailable error JSON."""
        # Given: monkeypatch to raise sqlite3.Error
        monkeypatch.setattr(
            seeded_engine, "get_state",
            lambda *a: (_ for _ in ()).throw(
                sqlite3.OperationalError("database is locked")
            ),
        )
        # When getting phase
        result = _process_get_phase(seeded_engine, "feature:009-test")
        # Then structured db_unavailable error
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "db_unavailable"
        assert "OperationalError" in data["message"]

    def test_transition_phase_sqlite_error_returns_db_unavailable(
        self, seeded_engine, monkeypatch
    ):
        """sqlite3.Error in transition_phase produces db_unavailable error JSON."""
        # Given: monkeypatch to raise sqlite3.Error
        monkeypatch.setattr(
            seeded_engine, "transition_phase",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.DatabaseError("disk I/O error")
            ),
        )
        # When transitioning
        result = _process_transition_phase(
            seeded_engine, "feature:009-test", "design", False
        )
        # Then structured db_unavailable error
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "db_unavailable"
        assert "DatabaseError" in data["message"]

    def test_complete_phase_sqlite_error_returns_db_unavailable(
        self, seeded_engine, monkeypatch
    ):
        """sqlite3.Error in complete_phase produces db_unavailable error JSON."""
        # Given: monkeypatch to raise sqlite3.Error
        monkeypatch.setattr(
            seeded_engine, "complete_phase",
            lambda *a: (_ for _ in ()).throw(
                sqlite3.InterfaceError("cannot bind")
            ),
        )
        # When completing phase
        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "specify"
        )
        # Then structured db_unavailable error
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "db_unavailable"
        assert "InterfaceError" in data["message"]

    def test_validate_prerequisites_sqlite_error_returns_db_unavailable(
        self, seeded_engine, monkeypatch
    ):
        """sqlite3.Error in validate_prerequisites produces db_unavailable error JSON."""
        # Given: monkeypatch to raise sqlite3.Error
        monkeypatch.setattr(
            seeded_engine, "validate_prerequisites",
            lambda *a: (_ for _ in ()).throw(
                sqlite3.ProgrammingError("closed database")
            ),
        )
        # When validating
        result = _process_validate_prerequisites(
            seeded_engine, "feature:009-test", "design"
        )
        # Then structured db_unavailable error
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "db_unavailable"
        assert "ProgrammingError" in data["message"]

    def test_list_by_phase_sqlite_error_returns_db_unavailable(
        self, seeded_engine, monkeypatch
    ):
        """sqlite3.Error in list_by_phase produces db_unavailable error JSON."""
        # Given: monkeypatch to raise sqlite3.Error
        monkeypatch.setattr(
            seeded_engine, "list_by_phase",
            lambda *a: (_ for _ in ()).throw(
                sqlite3.OperationalError("table locked")
            ),
        )
        # When listing by phase
        result = _process_list_features_by_phase(seeded_engine, "specify")
        # Then structured db_unavailable error
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "db_unavailable"
        assert "OperationalError" in data["message"]

    def test_list_by_status_sqlite_error_returns_db_unavailable(
        self, seeded_engine, monkeypatch
    ):
        """sqlite3.Error in list_by_status produces db_unavailable error JSON."""
        # Given: monkeypatch to raise sqlite3.Error
        monkeypatch.setattr(
            seeded_engine, "list_by_status",
            lambda *a: (_ for _ in ()).throw(
                sqlite3.OperationalError("disk space")
            ),
        )
        # When listing by status
        result = _process_list_features_by_status(seeded_engine, "active")
        # Then structured db_unavailable error
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "db_unavailable"
        assert "OperationalError" in data["message"]


class TestNotInitializedGuards:
    """Dimension 4 (error propagation): All 6 MCP tool handlers check for
    _engine is None and return 'not_initialized' error.

    Anticipate: If a tool handler is missing the None guard, calling it before
    server startup would cause AttributeError on None.get_state().
    derived_from: dimension:error_propagation (all-6 not-initialized guards)
    """

    def test_all_6_tool_handlers_have_not_initialized_guard(self):
        """Verify by inspecting the source that all 6 async tool handlers
        contain the _engine is None check. Since we cannot call async handlers
        directly without an event loop, we verify structurally.

        Note: This is a code-level verification, not a runtime test.
        """
        import inspect
        import workflow_state_server as mod

        # All 6 tool handler functions
        handlers = [
            mod.get_phase,
            mod.transition_phase,
            mod.complete_phase,
            mod.validate_prerequisites,
            mod.list_features_by_phase,
            mod.list_features_by_status,
        ]

        for handler in handlers:
            source = inspect.getsource(handler)
            assert "_engine is None" in source, (
                f"{handler.__name__} is missing '_engine is None' guard"
            )
            assert "_NOT_INITIALIZED" in source, (
                f"{handler.__name__} is missing '_NOT_INITIALIZED' error return"
            )


class TestCompletePhaseDegradedSourceValue:
    """Dimension 5 (mutation mindset): When complete_phase returns via degraded
    fallback, the serialized source field must be 'meta_json_fallback' and
    degraded must be True.

    Anticipate: If source is set to 'db' or 'meta_json' instead of
    'meta_json_fallback', the degraded derivation in _serialize_state would
    incorrectly return False.
    derived_from: dimension:mutation_mindset (source field exact value)
    """

    def test_degraded_complete_phase_source_and_degraded_field(
        self, db, tmp_path
    ):
        """complete_phase via MCP with closed DB returns source='meta_json_fallback'
        and degraded=True in serialized output.
        """
        # Given: set up feature and close DB
        db.register_entity("feature", "010-test", "Test Feature", status="active")
        db.create_workflow_phase("feature:010-test", workflow_phase="specify")

        feat_dir = os.path.join(str(tmp_path), "features", "010-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            f.write(
                '{"id": "010", "slug": "010-test", "status": "active",'
                ' "mode": "standard", "lastCompletedPhase": null, "phases": {}}'
            )

        engine = WorkflowStateEngine(db, str(tmp_path))
        db.close()

        # When completing brainstorm (first phase in degraded mode)
        result = _process_complete_phase(engine, "feature:010-test", "brainstorm")
        data = json.loads(result)

        # Then source is exactly 'meta_json_fallback' and degraded is True
        assert "error" not in data, f"Unexpected error: {data}"
        assert data["source"] == "meta_json_fallback"
        assert data["degraded"] is True
        assert "brainstorm" in data["completed_phases"]

    def test_normal_complete_phase_source_is_db(self, seeded_engine):
        """Normal complete_phase returns source='db' and degraded=False.
        derived_from: dimension:mutation_mindset (return value mutation)
        """
        # When completing specify normally
        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "specify"
        )
        data = json.loads(result)

        # Then source is 'db' and degraded is False
        assert data["source"] == "db"
        assert data["degraded"] is False


class TestValidatePrerequisitesDegradedMode:
    """Dimension 1 (BDD): validate_prerequisites via MCP still returns results
    (not error) when DB is degraded.

    Anticipate: If validate_prerequisites doesn't handle degraded state from
    get_state, it could return a feature_not_found error instead of gate results.
    derived_from: spec:AC-6 (validate_prerequisites in degraded mode)
    """

    def test_returns_results_not_error_when_degraded(self, db, tmp_path):
        """validate_prerequisites via MCP returns gate results with degraded DB.
        """
        # Given: set up feature and close DB
        db.register_entity("feature", "010-val", "Test", status="active")
        db.create_workflow_phase("feature:010-val", workflow_phase="specify")

        feat_dir = os.path.join(str(tmp_path), "features", "010-val")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            f.write(
                '{"id": "010", "slug": "010-val", "status": "active",'
                ' "mode": "standard", "lastCompletedPhase": null, "phases": {}}'
            )

        engine = WorkflowStateEngine(db, str(tmp_path))
        db.close()

        # When validating prerequisites in degraded mode
        result = _process_validate_prerequisites(
            engine, "feature:010-val", "brainstorm"
        )
        data = json.loads(result)

        # Then results are returned (not an error)
        assert "error" not in data
        assert "all_passed" in data
        assert "results" in data
        assert isinstance(data["results"], list)
        assert len(data["results"]) > 0


class TestTransitionDegradedResponseShape:
    """Dimension 3 (adversarial): transition_phase in degraded mode still returns
    the exact same JSON shape as non-degraded: {transitioned, results, degraded}.

    Anticipate: A degraded code path might return a different shape (e.g., missing
    'results' key or adding an 'error' key), breaking MCP clients.
    derived_from: dimension:adversarial (JSON shape contract in degraded mode)
    """

    def test_degraded_transition_has_exact_key_set(self, db, tmp_path):
        """Degraded transition response has {transitioned, results, degraded}.
        """
        # Given: set up feature and close DB
        db.register_entity("feature", "010-shape", "Test", status="active")
        db.create_workflow_phase("feature:010-shape", workflow_phase="specify")

        feat_dir = os.path.join(str(tmp_path), "features", "010-shape")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            f.write(
                '{"id": "010", "slug": "010-shape", "status": "active",'
                ' "mode": "standard", "lastCompletedPhase": null, "phases": {}}'
            )

        engine = WorkflowStateEngine(db, str(tmp_path))
        db.close()

        # When transitioning in degraded mode
        result = _process_transition_phase(
            engine, "feature:010-shape", "brainstorm", False
        )
        data = json.loads(result)

        # Then exact same key set as non-degraded
        assert set(data.keys()) == {"transitioned", "results", "degraded"}
        assert data["degraded"] is True
        assert isinstance(data["results"], list)
        # Each result item has the correct shape
        for item in data["results"]:
            assert set(item.keys()) == {"allowed", "reason", "severity", "guard_id"}
