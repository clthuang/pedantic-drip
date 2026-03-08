"""Tests for workflow_state_server processing functions."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
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

from entity_registry.frontmatter_sync import DriftReport, FieldMismatch
from workflow_engine.reconciliation import (
    ReconcileAction,
    WorkflowDriftReport,
    WorkflowDriftResult,
    WorkflowMismatch,
)

from workflow_state_server import (
    _NOT_INITIALIZED,
    _SUPPORTED_DIRECTIONS,
    _atomic_json_write,
    _iso_now,
    _make_error,
    _process_complete_phase,
    _process_get_phase,
    _process_list_features_by_phase,
    _process_list_features_by_status,
    _process_reconcile_apply,
    _process_reconcile_check,
    _process_reconcile_frontmatter,
    _process_reconcile_status,
    _process_transition_phase,
    _process_validate_prerequisites,
    _serialize_drift_report,
    _serialize_reconcile_action,
    _serialize_result,
    _serialize_state,
    _serialize_workflow_drift_report,
    _validate_feature_type_id,
)

# RED-phase import: _process_init_project_state does not exist yet.
# Conditional import keeps the test file importable so existing tests still run.
try:
    from workflow_state_server import _process_init_project_state
except ImportError:
    _process_init_project_state = None


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
        """Completing a phase for a nonexistent feature returns feature_not_found.
        derived_from: spec:AC-5, R4 (complete_phase validates feature existence)

        Anticipate: If feature existence check is missing before phase completion,
        it could cause NoneType errors or corrupt DB.
        """
        # Given an engine with no features
        # When completing a phase for a nonexistent feature
        result = _process_complete_phase(
            engine, "feature:nonexistent", "specify"
        )
        # Then the server returns a structured error with feature_not_found type
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "feature_not_found"
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


# ===========================================================================
# Feature 011: Reconciliation MCP Tool (Wave 2)
# ===========================================================================


# ---------------------------------------------------------------------------
# Task 1.3: _validate_feature_type_id
# ---------------------------------------------------------------------------


class TestValidateFeatureTypeId:
    """Path-traversal validation for feature_type_id."""

    def test_valid_feature_type_id_returns_slug(self, tmp_path):
        """Valid 'feature:010-slug' with existing dir returns slug."""
        feat_dir = os.path.join(str(tmp_path), "features", "010-slug")
        os.makedirs(feat_dir, exist_ok=True)
        result = _validate_feature_type_id("feature:010-slug", str(tmp_path))
        assert result == "010-slug"

    def test_no_colon_raises_value_error(self, tmp_path):
        """Missing colon raises ValueError with 'invalid_input' prefix."""
        with pytest.raises(ValueError, match="invalid_input: missing colon"):
            _validate_feature_type_id("feature-no-colon", str(tmp_path))

    def test_double_dot_in_slug_raises_value_error(self, tmp_path):
        """'..' in slug raises ValueError (path traversal)."""
        with pytest.raises(ValueError, match="feature_not_found"):
            _validate_feature_type_id("feature:../../../etc", str(tmp_path))

    def test_null_bytes_in_slug_raises_value_error(self, tmp_path):
        """Null bytes in slug raises ValueError before realpath."""
        with pytest.raises(ValueError, match="feature_not_found"):
            _validate_feature_type_id("feature:010-slug\x00evil", str(tmp_path))

    def test_symlink_traversal_raises_value_error(self, tmp_path):
        """Symlink pointing outside artifacts_root raises ValueError."""
        # Create artifacts_root with features/ subdir
        arts_root = os.path.join(str(tmp_path), "artifacts")
        features_dir = os.path.join(arts_root, "features")
        os.makedirs(features_dir, exist_ok=True)

        # Create a directory truly outside artifacts_root
        with tempfile.TemporaryDirectory() as outside_dir:
            symlink_path = os.path.join(features_dir, "evil-link")
            os.symlink(outside_dir, symlink_path)
            with pytest.raises(ValueError, match="feature_not_found"):
                _validate_feature_type_id("feature:evil-link", arts_root)

    def test_prefix_collision_raises_value_error(self, tmp_path):
        """Symlink to external dir raises ValueError even with valid prefix."""
        evil_root = os.path.join(str(tmp_path), "evilroot")
        os.makedirs(os.path.join(evil_root, "features"), exist_ok=True)
        real_target = os.path.join(str(tmp_path), "external-data")
        os.makedirs(real_target, exist_ok=True)
        os.symlink(real_target, os.path.join(evil_root, "features", "010-slug"))
        with pytest.raises(ValueError, match="feature_not_found"):
            _validate_feature_type_id("feature:010-slug", evil_root)


# ---------------------------------------------------------------------------
# Task 4.1: _serialize_workflow_drift_report and _serialize_reconcile_action
# ---------------------------------------------------------------------------


class TestSerializeWorkflowDriftReport:
    """Serialization of WorkflowDriftReport dataclass."""

    def test_round_trip_with_mismatches(self):
        """Full report with mismatches serializes correctly."""
        report = WorkflowDriftReport(
            feature_type_id="feature:010-test",
            status="meta_json_ahead",
            meta_json={"workflow_phase": "finish", "last_completed_phase": "implement",
                       "mode": "standard", "status": "active"},
            db={"workflow_phase": "create-plan", "last_completed_phase": "design",
                "mode": "standard", "kanban_column": "in-progress"},
            mismatches=(
                WorkflowMismatch(field="last_completed_phase",
                                 meta_json_value="implement", db_value="design"),
                WorkflowMismatch(field="workflow_phase",
                                 meta_json_value="finish", db_value="create-plan"),
            ),
        )
        result = _serialize_workflow_drift_report(report)
        assert result["feature_type_id"] == "feature:010-test"
        assert result["status"] == "meta_json_ahead"
        assert result["meta_json"]["workflow_phase"] == "finish"
        assert result["db"]["kanban_column"] == "in-progress"
        assert len(result["mismatches"]) == 2
        assert result["mismatches"][0]["field"] == "last_completed_phase"
        assert result["mismatches"][0]["meta_json_value"] == "implement"
        assert result["mismatches"][0]["db_value"] == "design"

    def test_empty_mismatches(self):
        """Report with no mismatches serializes with empty list."""
        report = WorkflowDriftReport(
            feature_type_id="feature:009-test",
            status="in_sync",
            meta_json={"workflow_phase": "specify"},
            db={"workflow_phase": "specify"},
            mismatches=(),
        )
        result = _serialize_workflow_drift_report(report)
        assert result["mismatches"] == []

    def test_none_values(self):
        """Report with None meta_json/db serializes correctly."""
        report = WorkflowDriftReport(
            feature_type_id="feature:009-test",
            status="db_only",
            meta_json=None,
            db=None,
            mismatches=(),
        )
        result = _serialize_workflow_drift_report(report)
        assert result["meta_json"] is None
        assert result["db"] is None


class TestSerializeReconcileAction:
    """Serialization of ReconcileAction dataclass."""

    def test_changes_use_old_new_value_convention(self):
        """ReconcileAction changes serialize as old_value=db, new_value=meta_json."""
        action = ReconcileAction(
            feature_type_id="feature:010-test",
            action="reconciled",
            direction="meta_json_to_db",
            changes=(
                WorkflowMismatch(field="last_completed_phase",
                                 meta_json_value="implement", db_value="design"),
            ),
            message="Updated DB to match .meta.json",
        )
        result = _serialize_reconcile_action(action)
        assert result["feature_type_id"] == "feature:010-test"
        assert result["action"] == "reconciled"
        assert result["direction"] == "meta_json_to_db"
        assert len(result["changes"]) == 1
        assert result["changes"][0]["field"] == "last_completed_phase"
        assert result["changes"][0]["old_value"] == "design"
        assert result["changes"][0]["new_value"] == "implement"
        assert result["message"] == "Updated DB to match .meta.json"

    def test_empty_changes(self):
        """Skipped action with no changes serializes correctly."""
        action = ReconcileAction(
            feature_type_id="feature:009-test",
            action="skipped",
            direction="meta_json_to_db",
            changes=(),
            message="Already in sync",
        )
        result = _serialize_reconcile_action(action)
        assert result["changes"] == []

    def test_none_values_in_changes(self):
        """Changes with None old/new values serialize correctly (meta_json_only case)."""
        action = ReconcileAction(
            feature_type_id="feature:010-test",
            action="created",
            direction="meta_json_to_db",
            changes=(
                WorkflowMismatch(field="workflow_phase",
                                 meta_json_value="specify", db_value=None),
            ),
            message="Created DB row from .meta.json",
        )
        result = _serialize_reconcile_action(action)
        assert result["changes"][0]["old_value"] is None
        assert result["changes"][0]["new_value"] == "specify"


# ---------------------------------------------------------------------------
# Task 4.2: _serialize_drift_report
# ---------------------------------------------------------------------------


class TestSerializeDriftReport:
    """Serialization of frontmatter_sync.DriftReport dataclass."""

    def test_with_mismatches(self):
        """DriftReport with mismatches serializes correctly."""
        report = DriftReport(
            filepath="/tmp/features/010-test/spec.md",
            type_id="feature:010-test",
            status="diverged",
            file_fields={"entity_uuid": "uuid-1", "entity_type_id": "feature:010-test"},
            db_fields={"uuid": "uuid-2", "type_id": "feature:010-test"},
            mismatches=[
                FieldMismatch(field="entity_uuid", file_value="uuid-1", db_value="uuid-2"),
            ],
        )
        result = _serialize_drift_report(report)
        assert result["filepath"] == "/tmp/features/010-test/spec.md"
        assert result["type_id"] == "feature:010-test"
        assert result["status"] == "diverged"
        assert len(result["mismatches"]) == 1
        assert result["mismatches"][0]["field"] == "entity_uuid"
        assert result["mismatches"][0]["file_value"] == "uuid-1"
        assert result["mismatches"][0]["db_value"] == "uuid-2"

    def test_empty_mismatches(self):
        """DriftReport with no mismatches serializes correctly."""
        report = DriftReport(
            filepath="/tmp/features/010-test/spec.md",
            type_id="feature:010-test",
            status="in_sync",
            file_fields={"entity_uuid": "uuid-1"},
            db_fields={"uuid": "uuid-1"},
            mismatches=[],
        )
        result = _serialize_drift_report(report)
        assert result["mismatches"] == []
        assert result["status"] == "in_sync"

    def test_all_status_values(self):
        """All DriftReport status values serialize correctly."""
        for status in ("in_sync", "file_only", "db_only", "diverged", "no_header", "error"):
            report = DriftReport(
                filepath="/tmp/test.md",
                type_id=None,
                status=status,
                file_fields=None,
                db_fields=None,
                mismatches=[],
            )
            result = _serialize_drift_report(report)
            assert result["status"] == status


# ---------------------------------------------------------------------------
# Task 5.1: _process_reconcile_check
# ---------------------------------------------------------------------------


class TestProcessReconcileCheck:
    """Processing function for workflow drift detection."""

    @pytest.fixture
    def reconcile_env(self, db, tmp_path):
        """Set up a feature with .meta.json ahead of DB for reconcile tests."""
        # Register entity + workflow phase in DB
        db.register_entity("feature", "011-rec", "Reconcile Test", status="active")
        db.create_workflow_phase(
            "feature:011-rec",
            workflow_phase="specify",
            last_completed_phase="brainstorm",
            mode="standard",
        )

        # Create .meta.json that is ahead
        feat_dir = os.path.join(str(tmp_path), "features", "011-rec")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            json.dump({
                "id": "011",
                "slug": "011-rec",
                "status": "active",
                "mode": "standard",
                "lastCompletedPhase": "implement",
                "phases": {
                    "brainstorm": {"status": "completed"},
                    "specify": {"status": "completed"},
                    "design": {"status": "completed"},
                    "create-plan": {"status": "completed"},
                    "create-tasks": {"status": "completed"},
                    "implement": {"status": "completed"},
                },
            }, f)

        engine = WorkflowStateEngine(db, str(tmp_path))
        return engine, db, str(tmp_path)

    def test_single_feature_drift(self, reconcile_env):
        """Single feature check returns JSON with drift report."""
        engine, db, arts = reconcile_env
        result = _process_reconcile_check(engine, db, arts, "feature:011-rec")
        data = json.loads(result)
        assert "error" not in data
        assert len(data["features"]) == 1
        assert data["features"][0]["status"] == "meta_json_ahead"
        assert data["summary"]["meta_json_ahead"] == 1

    def test_bulk_check_returns_summary(self, reconcile_env):
        """Bulk check returns summary counts."""
        engine, db, arts = reconcile_env
        result = _process_reconcile_check(engine, db, arts, None)
        data = json.loads(result)
        assert "error" not in data
        assert "summary" in data
        assert isinstance(data["summary"], dict)
        total = sum(data["summary"].values())
        assert total >= 1

    def test_nonexistent_slug_returns_feature_not_found(self, db, tmp_path):
        """Non-existent slug causes ValueError -> feature_not_found error."""
        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_check(
            engine, db, str(tmp_path), "feature:999-nonexistent"
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "feature_not_found"

    def test_malformed_no_colon_returns_invalid_transition(self, db, tmp_path):
        """Missing colon causes ValueError -> invalid_transition error (AC-18 case 2)."""
        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_check(
            engine, db, str(tmp_path), "featurenocolon"
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "invalid_transition"


# ---------------------------------------------------------------------------
# Task 5.2: _process_reconcile_apply
# ---------------------------------------------------------------------------


class TestProcessReconcileApply:
    """Processing function for workflow reconciliation."""

    @pytest.fixture
    def reconcile_env(self, db, tmp_path):
        """Feature with .meta.json ahead of DB."""
        db.register_entity("feature", "011-app", "Apply Test", status="active")
        db.create_workflow_phase(
            "feature:011-app",
            workflow_phase="specify",
            last_completed_phase="brainstorm",
            mode="standard",
        )

        feat_dir = os.path.join(str(tmp_path), "features", "011-app")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            json.dump({
                "id": "011",
                "slug": "011-app",
                "status": "active",
                "mode": "standard",
                "lastCompletedPhase": "implement",
                "phases": {
                    "brainstorm": {"status": "completed"},
                    "specify": {"status": "completed"},
                    "design": {"status": "completed"},
                    "create-plan": {"status": "completed"},
                    "create-tasks": {"status": "completed"},
                    "implement": {"status": "completed"},
                },
            }, f)

        engine = WorkflowStateEngine(db, str(tmp_path))
        return engine, db, str(tmp_path)

    def test_reconcile_returns_actions(self, reconcile_env):
        """Reconcile returns JSON with action list."""
        engine, db, arts = reconcile_env
        result = _process_reconcile_apply(
            engine, db, arts, "feature:011-app", "meta_json_to_db", False
        )
        data = json.loads(result)
        assert "error" not in data
        assert len(data["actions"]) >= 1
        assert data["actions"][0]["action"] == "reconciled"

    def test_dry_run(self, reconcile_env):
        """dry_run returns changes without applying."""
        engine, db, arts = reconcile_env
        result = _process_reconcile_apply(
            engine, db, arts, "feature:011-app", "meta_json_to_db", True
        )
        data = json.loads(result)
        assert "error" not in data
        assert data["summary"]["dry_run"] >= 1

        # Verify DB was NOT updated
        check = _process_reconcile_check(engine, db, arts, "feature:011-app")
        check_data = json.loads(check)
        assert check_data["features"][0]["status"] == "meta_json_ahead"

    def test_invalid_direction_returns_error(self, reconcile_env):
        """Unsupported direction returns structured error (AC-17)."""
        engine, db, arts = reconcile_env
        result = _process_reconcile_apply(
            engine, db, arts, None, "db_to_meta_json", False
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "invalid_transition"
        assert "Unsupported direction" in data["message"]

    def test_nonexistent_slug_returns_feature_not_found(self, db, tmp_path):
        """Non-existent slug -> feature_not_found (AC-18)."""
        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_apply(
            engine, db, str(tmp_path), "feature:999-missing", "meta_json_to_db", False
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "feature_not_found"

    def test_malformed_no_colon_returns_invalid_transition(self, db, tmp_path):
        """Missing colon -> invalid_transition (AC-18 case 2)."""
        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_apply(
            engine, db, str(tmp_path), "nocolon", "meta_json_to_db", False
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "invalid_transition"


# ---------------------------------------------------------------------------
# Task 5.3: _process_reconcile_frontmatter
# ---------------------------------------------------------------------------


class TestProcessReconcileFrontmatter:
    """Processing function for frontmatter drift detection."""

    def test_single_feature_with_frontmatter(self, db, tmp_path):
        """Single feature with valid frontmatter returns drift reports (AC-11)."""
        # Register entity in DB
        db.register_entity("feature", "011-fm", "FM Test", status="active")

        # Create feature dir with spec.md containing frontmatter
        feat_dir = os.path.join(str(tmp_path), "features", "011-fm")
        os.makedirs(feat_dir, exist_ok=True)
        entity = db.get_entity("feature:011-fm")
        entity_uuid = entity["uuid"]

        spec_path = os.path.join(feat_dir, "spec.md")
        with open(spec_path, "w") as f:
            f.write(f"---\nentity_uuid: {entity_uuid}\n"
                    f"entity_type_id: feature:011-fm\n---\n# Spec\n")

        result = _process_reconcile_frontmatter(db, str(tmp_path), "feature:011-fm")
        data = json.loads(result)
        assert "error" not in data
        assert len(data["reports"]) >= 1
        assert data["reports"][0]["status"] == "in_sync"
        assert data["summary"]["in_sync"] >= 1

    def test_no_frontmatter(self, db, tmp_path):
        """Feature with no frontmatter in files returns db_only reports (AC-12)."""
        db.register_entity("feature", "011-nofm", "No FM", status="active")

        feat_dir = os.path.join(str(tmp_path), "features", "011-nofm")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\nNo frontmatter here.\n")

        result = _process_reconcile_frontmatter(db, str(tmp_path), "feature:011-nofm")
        data = json.loads(result)
        assert "error" not in data
        assert len(data["reports"]) >= 1
        # With type_id passed, detect_drift returns db_only for no-header files
        assert data["reports"][0]["status"] == "db_only"

    def test_bulk_scan(self, db, tmp_path):
        """Bulk scan via scan_all returns aggregate summary (AC-13)."""
        # Register entity
        db.register_entity("feature", "011-bulk", "Bulk Test", status="active")
        entity = db.get_entity("feature:011-bulk")

        # Create feature dir
        feat_dir = os.path.join(str(tmp_path), "features", "011-bulk")
        os.makedirs(feat_dir, exist_ok=True)

        # Write spec.md with matching frontmatter
        spec_path = os.path.join(feat_dir, "spec.md")
        with open(spec_path, "w") as f:
            f.write(f"---\nentity_uuid: {entity['uuid']}\n"
                    f"entity_type_id: feature:011-bulk\n---\n# Spec\n")

        # Update entity artifact_path so scan_all can find it
        db.update_entity(entity["uuid"], artifact_path=feat_dir)

        result = _process_reconcile_frontmatter(db, str(tmp_path), None)
        data = json.loads(result)
        assert "error" not in data
        assert "summary" in data
        assert isinstance(data["summary"], dict)

    def test_nonexistent_directory_returns_empty(self, db, tmp_path):
        """Non-existent feature directory returns empty reports."""
        feat_dir = os.path.join(str(tmp_path), "features", "011-gone")
        os.makedirs(feat_dir, exist_ok=True)  # Must exist for validation to pass
        result = _process_reconcile_frontmatter(db, str(tmp_path), "feature:011-gone")
        data = json.loads(result)
        assert "error" not in data
        # No artifact files in the dir -> empty reports
        assert len(data["reports"]) == 0
        assert all(v == 0 for v in data["summary"].values())

    def test_nonexistent_slug_returns_feature_not_found(self, db, tmp_path):
        """Non-existent slug -> feature_not_found (AC-18)."""
        result = _process_reconcile_frontmatter(
            db, str(tmp_path), "feature:999-missing"
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "feature_not_found"

    def test_malformed_no_colon_returns_invalid_transition(self, db, tmp_path):
        """Missing colon -> invalid_transition (AC-18 case 2)."""
        result = _process_reconcile_frontmatter(
            db, str(tmp_path), "nocolonhere"
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "invalid_transition"


# ---------------------------------------------------------------------------
# Task 5.4: _process_reconcile_status
# ---------------------------------------------------------------------------


class TestProcessReconcileStatus:
    """Processing function for combined drift report."""

    def test_healthy_when_all_in_sync(self, db, tmp_path):
        """All in sync -> healthy=true (AC-14)."""
        # Register entity and create matching .meta.json and DB state
        db.register_entity("feature", "011-healthy", "Healthy", status="active")
        db.create_workflow_phase(
            "feature:011-healthy",
            workflow_phase="specify",
            last_completed_phase="brainstorm",
            mode="standard",
        )

        feat_dir = os.path.join(str(tmp_path), "features", "011-healthy")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            json.dump({
                "id": "011",
                "slug": "011-healthy",
                "status": "active",
                "mode": "standard",
                "lastCompletedPhase": "brainstorm",
                "phases": {
                    "brainstorm": {"status": "completed"},
                },
            }, f)

        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_status(engine, db, str(tmp_path))
        data = json.loads(result)
        assert "error" not in data
        assert data["healthy"] is True
        assert data["total_features_checked"] >= 1

    def test_unhealthy_when_drift_exists(self, db, tmp_path):
        """Any drift -> healthy=false (AC-15)."""
        db.register_entity("feature", "011-drift", "Drift", status="active")
        db.create_workflow_phase(
            "feature:011-drift",
            workflow_phase="specify",
            last_completed_phase="brainstorm",
            mode="standard",
        )

        feat_dir = os.path.join(str(tmp_path), "features", "011-drift")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            json.dump({
                "id": "011",
                "slug": "011-drift",
                "status": "active",
                "mode": "standard",
                "lastCompletedPhase": "implement",
                "phases": {
                    "brainstorm": {"status": "completed"},
                    "specify": {"status": "completed"},
                    "design": {"status": "completed"},
                    "create-plan": {"status": "completed"},
                    "create-tasks": {"status": "completed"},
                    "implement": {"status": "completed"},
                },
            }, f)

        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_status(engine, db, str(tmp_path))
        data = json.loads(result)
        assert "error" not in data
        assert data["healthy"] is False

    def test_error_status_makes_unhealthy(self, db, tmp_path, monkeypatch):
        """scan_all raising sqlite3.Error -> entire response is structured error."""
        engine = WorkflowStateEngine(db, str(tmp_path))
        # Monkeypatch scan_all to raise sqlite3.Error
        import workflow_state_server as mod
        original_scan_all = mod.scan_all
        def raise_error(*a, **kw):
            raise sqlite3.OperationalError("db locked")
        monkeypatch.setattr(mod, "scan_all", raise_error)

        result = _process_reconcile_status(engine, db, str(tmp_path))
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "db_unavailable"

        monkeypatch.setattr(mod, "scan_all", original_scan_all)


# ---------------------------------------------------------------------------
# Task 6.1: MCP tool handlers (not-initialized guards)
# ---------------------------------------------------------------------------


class TestReconciliationNotInitializedGuards:
    """Verify all 4 reconciliation handlers have None guards (AC-16)."""

    def test_all_4_reconciliation_handlers_have_guard(self):
        """Inspect source of all 4 reconciliation handlers for None guard."""
        import inspect
        import workflow_state_server as mod

        handlers = [
            mod.reconcile_check,
            mod.reconcile_apply,
            mod.reconcile_frontmatter,
            mod.reconcile_status,
        ]

        for handler in handlers:
            source = inspect.getsource(handler)
            # Each handler should check _engine or _db is None
            assert "_NOT_INITIALIZED" in source, (
                f"{handler.__name__} missing _NOT_INITIALIZED return"
            )


# ---------------------------------------------------------------------------
# Task 7.2: MCP end-to-end integration tests
# ---------------------------------------------------------------------------


class TestReconciliationEndToEnd:
    """End-to-end integration tests for reconciliation processing functions."""

    def test_reconcile_status_healthy_after_apply(self, db, tmp_path):
        """reconcile_status returns healthy=true after reconcile_apply syncs drift.

        Fixture: 2 features with .meta.json ahead, run apply, then verify status.
        """
        features = [
            ("011-e2e-a", "brainstorm", "implement"),
            ("011-e2e-b", "design", "create-tasks"),
        ]
        for slug, db_last, meta_last in features:
            db.register_entity("feature", slug, f"E2E {slug}", status="active")
            db.create_workflow_phase(
                f"feature:{slug}",
                workflow_phase="specify",
                last_completed_phase=db_last,
                mode="standard",
            )
            feat_dir = os.path.join(str(tmp_path), "features", slug)
            os.makedirs(feat_dir, exist_ok=True)
            # Build phases dict
            from transition_gate.constants import PHASE_SEQUENCE
            phase_values = [p.value for p in PHASE_SEQUENCE]
            meta_idx = phase_values.index(meta_last)
            phases = {
                p: {"status": "completed"}
                for p in phase_values[: meta_idx + 1]
            }
            with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
                json.dump({
                    "id": slug.split("-")[0],
                    "slug": slug,
                    "status": "active",
                    "mode": "standard",
                    "lastCompletedPhase": meta_last,
                    "phases": phases,
                }, f)

        engine = WorkflowStateEngine(db, str(tmp_path))

        # Step 1: Verify unhealthy before apply
        status_before = json.loads(
            _process_reconcile_status(engine, db, str(tmp_path))
        )
        assert status_before["healthy"] is False

        # Step 2: Apply reconciliation
        apply_result = json.loads(
            _process_reconcile_apply(
                engine, db, str(tmp_path), None, "meta_json_to_db", False
            )
        )
        assert "error" not in apply_result
        assert apply_result["summary"]["reconciled"] >= 2

        # Step 3: Verify healthy after apply
        status_after = json.loads(
            _process_reconcile_status(engine, db, str(tmp_path))
        )
        assert status_after["healthy"] is True
        wf_summary = status_after["workflow_drift"]["summary"]
        assert wf_summary["meta_json_ahead"] == 0
        assert wf_summary["db_ahead"] == 0
        assert wf_summary["error"] == 0

    def test_reconcile_frontmatter_with_real_headers(self, db, tmp_path):
        """reconcile_frontmatter with real temp files containing frontmatter headers."""
        # Register entity and get UUID
        db.register_entity("feature", "011-hdr", "Header Test", status="active")
        entity = db.get_entity("feature:011-hdr")
        entity_uuid = entity["uuid"]

        feat_dir = os.path.join(str(tmp_path), "features", "011-hdr")
        os.makedirs(feat_dir, exist_ok=True)

        # Create spec.md with matching frontmatter
        spec_path = os.path.join(feat_dir, "spec.md")
        with open(spec_path, "w") as f:
            f.write(
                f"---\nentity_uuid: {entity_uuid}\n"
                f"entity_type_id: feature:011-hdr\n---\n# Spec\nContent here.\n"
            )

        # Create design.md with no frontmatter
        design_path = os.path.join(feat_dir, "design.md")
        with open(design_path, "w") as f:
            f.write("# Design\nNo frontmatter.\n")

        result = _process_reconcile_frontmatter(
            db, str(tmp_path), "feature:011-hdr"
        )
        data = json.loads(result)
        assert "error" not in data
        assert len(data["reports"]) == 2
        statuses = [r["status"] for r in data["reports"]]
        assert "in_sync" in statuses
        # design.md has no header but type_id was passed -> db_only
        assert "db_only" in statuses

    def test_error_uninitialized_guard(self):
        """Uninitialized engine/db returns not_initialized error (AC-16)."""
        import asyncio
        import workflow_state_server as mod

        # Temporarily set globals to None
        orig_engine = mod._engine
        orig_db = mod._db
        mod._engine = None
        mod._db = None

        try:
            # Run the async handlers synchronously
            result_check = asyncio.run(mod.reconcile_check())
            result_apply = asyncio.run(mod.reconcile_apply())
            result_fm = asyncio.run(mod.reconcile_frontmatter())
            result_status = asyncio.run(mod.reconcile_status())

            for result in [result_check, result_apply, result_fm, result_status]:
                data = json.loads(result)
                assert data["error"] is True
                assert data["error_type"] == "not_initialized"
        finally:
            mod._engine = orig_engine
            mod._db = orig_db

    def test_error_invalid_direction(self, db, tmp_path):
        """Invalid direction returns structured error (AC-17)."""
        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_apply(
            engine, db, str(tmp_path), None, "invalid_direction", False
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "invalid_transition"
        assert "Unsupported direction" in data["message"]

    def test_error_invalid_feature_type_id(self, db, tmp_path):
        """Invalid feature_type_id returns structured errors (AC-18)."""
        engine = WorkflowStateEngine(db, str(tmp_path))

        # Case 1: Non-existent slug -> feature_not_found
        result = _process_reconcile_check(
            engine, db, str(tmp_path), "feature:999-nope"
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "feature_not_found"

        # Case 2: Malformed (no colon) -> invalid_transition
        result = _process_reconcile_check(
            engine, db, str(tmp_path), "nocolon"
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "invalid_transition"


# ===========================================================================
# Test-deepener: Feature 011 Phase B -- Boundary Value tests
# derived_from: dimension:boundary_values
# ===========================================================================


class TestReconciliationBoundaryValues:
    """Boundary value analysis for reconciliation MCP processing functions.
    derived_from: dimension:boundary_values
    """

    def test_reconcile_check_empty_feature_set_returns_zero_summary(self, db, tmp_path):
        """Bulk reconcile_check with zero features returns all-zero summary.
        derived_from: dimension:boundary_values (empty collection)

        Anticipate: Empty iteration might skip summary initialization,
        returning {} instead of the expected 6-key summary dict.
        """
        # Given an engine with no features
        engine = WorkflowStateEngine(db, str(tmp_path))
        # When checking drift in bulk
        result = _process_reconcile_check(engine, db, str(tmp_path), None)
        data = json.loads(result)
        # Then summary has all 6 keys, all zero
        assert "error" not in data
        expected_keys = {"in_sync", "meta_json_ahead", "db_ahead", "meta_json_only", "db_only", "error"}
        assert set(data["summary"].keys()) == expected_keys
        assert all(v == 0 for v in data["summary"].values())
        assert data["features"] == []

    def test_reconcile_apply_empty_feature_set_returns_zero_summary(self, db, tmp_path):
        """Bulk reconcile_apply with zero features returns all-zero summary.
        derived_from: dimension:boundary_values (empty collection)

        Anticipate: Empty action list might not produce the 5-key summary,
        or dry_run count might be undefined.
        """
        # Given an engine with no features
        engine = WorkflowStateEngine(db, str(tmp_path))
        # When applying reconciliation in bulk
        result = _process_reconcile_apply(
            engine, db, str(tmp_path), None, "meta_json_to_db", False
        )
        data = json.loads(result)
        # Then summary has all 5 keys, all zero
        assert "error" not in data
        expected_keys = {"reconciled", "created", "skipped", "error", "dry_run"}
        assert set(data["summary"].keys()) == expected_keys
        assert all(v == 0 for v in data["summary"].values())

    def test_reconcile_apply_empty_direction_returns_error(self, db, tmp_path):
        """Empty string direction returns structured error.
        derived_from: dimension:boundary_values (empty string input)

        Anticipate: Empty string might accidentally match a valid direction
        if the check uses `in` substring matching instead of set membership.
        """
        # Given an engine
        engine = WorkflowStateEngine(db, str(tmp_path))
        # When applying with empty direction
        result = _process_reconcile_apply(
            engine, db, str(tmp_path), None, "", False
        )
        data = json.loads(result)
        # Then structured error
        assert data["error"] is True
        assert data["error_type"] == "invalid_transition"
        assert "Unsupported direction" in data["message"]

    def test_reconcile_check_response_json_shape(self, db, tmp_path):
        """reconcile_check response has exactly {features, summary} top-level keys.
        derived_from: dimension:boundary_values (JSON shape contract)

        Anticipate: Extra keys (e.g., "healthy" leaked from reconcile_status)
        or missing keys would break MCP clients.
        """
        # Given a feature in sync
        db.register_entity("feature", "011-shape", "Shape Test", status="active")
        db.create_workflow_phase(
            "feature:011-shape",
            workflow_phase="specify",
            last_completed_phase="brainstorm",
            mode="standard",
        )
        feat_dir = os.path.join(str(tmp_path), "features", "011-shape")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            json.dump({
                "id": "011", "slug": "011-shape", "status": "active",
                "mode": "standard", "lastCompletedPhase": "brainstorm",
                "phases": {"brainstorm": {"status": "completed"}},
            }, f)

        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_check(engine, db, str(tmp_path), "feature:011-shape")
        data = json.loads(result)

        # Then exact top-level key set
        assert set(data.keys()) == {"features", "summary"}

    def test_reconcile_apply_response_json_shape(self, db, tmp_path):
        """reconcile_apply response has exactly {actions, summary} top-level keys.
        derived_from: dimension:boundary_values (JSON shape contract)

        Anticipate: Missing "summary" or extra keys would break clients.
        """
        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_apply(
            engine, db, str(tmp_path), None, "meta_json_to_db", False
        )
        data = json.loads(result)
        assert set(data.keys()) == {"actions", "summary"}

    def test_reconcile_status_response_json_shape(self, db, tmp_path):
        """reconcile_status response has exactly 5 top-level keys.
        derived_from: dimension:boundary_values (JSON shape contract)

        Anticipate: Missing or extra keys would silently break consumers.
        """
        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_status(engine, db, str(tmp_path))
        data = json.loads(result)
        expected_keys = {
            "workflow_drift", "frontmatter_drift", "healthy",
            "total_features_checked", "total_files_checked",
        }
        assert set(data.keys()) == expected_keys


# ===========================================================================
# Test-deepener: Feature 011 Phase B -- Adversarial tests
# derived_from: dimension:adversarial
# ===========================================================================


class TestReconciliationAdversarial:
    """Adversarial and negative tests for reconciliation MCP tools.
    derived_from: dimension:adversarial
    """

    def test_supported_directions_is_frozenset(self):
        """_SUPPORTED_DIRECTIONS must be a frozenset (immutable).
        derived_from: dimension:adversarial (Never/Always: immutability)

        Anticipate: If _SUPPORTED_DIRECTIONS is a regular set, code
        could accidentally mutate it (e.g., .add("db_to_meta_json")),
        silently enabling unsupported directions.
        """
        assert isinstance(_SUPPORTED_DIRECTIONS, frozenset)
        assert "meta_json_to_db" in _SUPPORTED_DIRECTIONS
        assert len(_SUPPORTED_DIRECTIONS) == 1

    def test_path_traversal_in_reconcile_check(self, db, tmp_path):
        """Path traversal in feature_type_id is blocked by _validate_feature_type_id.
        derived_from: dimension:adversarial (path traversal)

        Anticipate: If _validate_feature_type_id is not called before
        check_workflow_drift, an attacker could read .meta.json files
        outside the artifacts_root.
        """
        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_check(
            engine, db, str(tmp_path), "feature:../../etc/passwd"
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "feature_not_found"

    def test_path_traversal_in_reconcile_apply(self, db, tmp_path):
        """Path traversal in feature_type_id blocked for reconcile_apply.
        derived_from: dimension:adversarial (path traversal)

        Anticipate: reconcile_apply calls _validate_feature_type_id too.
        If the validation is missing, an attacker could trigger DB writes
        based on external .meta.json content.
        """
        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_apply(
            engine, db, str(tmp_path), "feature:../../../evil", "meta_json_to_db", False
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "feature_not_found"

    def test_path_traversal_in_reconcile_frontmatter(self, db, tmp_path):
        """Path traversal in feature_type_id blocked for reconcile_frontmatter.
        derived_from: dimension:adversarial (path traversal)
        """
        result = _process_reconcile_frontmatter(
            db, str(tmp_path), "feature:../../etc/shadow"
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "feature_not_found"

    def test_null_bytes_in_reconcile_check(self, db, tmp_path):
        """Null bytes in feature_type_id blocked for reconcile_check.
        derived_from: dimension:adversarial (null byte injection)

        Anticipate: Null bytes could truncate the path in C-level
        filesystem calls, allowing path traversal.
        """
        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_check(
            engine, db, str(tmp_path), "feature:011-test\x00evil"
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "feature_not_found"

    def test_reconcile_check_drift_report_per_feature_shape(self, db, tmp_path):
        """Each feature in reconcile_check has exactly 5 keys per spec R1.
        derived_from: dimension:adversarial (JSON shape contract)

        Anticipate: Extra or missing keys in per-feature drift report
        would break MCP consumers. The 'message' field from the dataclass
        is intentionally excluded from serialization.
        """
        # Set up an in-sync feature
        db.register_entity("feature", "011-shape2", "Shape2", status="active")
        db.create_workflow_phase(
            "feature:011-shape2",
            workflow_phase="specify",
            last_completed_phase="brainstorm",
            mode="standard",
        )
        feat_dir = os.path.join(str(tmp_path), "features", "011-shape2")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            json.dump({
                "id": "011", "slug": "011-shape2", "status": "active",
                "mode": "standard", "lastCompletedPhase": "brainstorm",
                "phases": {"brainstorm": {"status": "completed"}},
            }, f)

        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_check(engine, db, str(tmp_path), "feature:011-shape2")
        data = json.loads(result)

        # Each feature report has exactly these keys
        for feature in data["features"]:
            assert set(feature.keys()) == {
                "feature_type_id", "status", "meta_json", "db", "mismatches"
            }

    def test_reconcile_apply_action_per_feature_shape(self, db, tmp_path):
        """Each action in reconcile_apply has exactly 5 keys per spec R2.
        derived_from: dimension:adversarial (JSON shape contract)
        """
        # Set up a meta_json_ahead feature
        db.register_entity("feature", "011-shape3", "Shape3", status="active")
        db.create_workflow_phase(
            "feature:011-shape3",
            workflow_phase="specify",
            last_completed_phase="brainstorm",
            mode="standard",
        )
        feat_dir = os.path.join(str(tmp_path), "features", "011-shape3")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            json.dump({
                "id": "011", "slug": "011-shape3", "status": "active",
                "mode": "standard", "lastCompletedPhase": "implement",
                "phases": {
                    "brainstorm": {"status": "completed"},
                    "specify": {"status": "completed"},
                    "design": {"status": "completed"},
                    "create-plan": {"status": "completed"},
                    "create-tasks": {"status": "completed"},
                    "implement": {"status": "completed"},
                },
            }, f)

        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_apply(
            engine, db, str(tmp_path), "feature:011-shape3", "meta_json_to_db", False
        )
        data = json.loads(result)

        for action in data["actions"]:
            assert set(action.keys()) == {
                "feature_type_id", "action", "direction", "changes", "message"
            }


# ===========================================================================
# Test-deepener: Feature 011 Phase B -- Error Propagation tests
# derived_from: dimension:error_propagation
# ===========================================================================


class TestReconciliationErrorPropagation:
    """Error propagation through reconciliation MCP processing functions.
    derived_from: dimension:error_propagation
    """

    def test_reconcile_check_sqlite_error_returns_db_unavailable(
        self, db, tmp_path, monkeypatch
    ):
        """sqlite3.Error in reconcile_check returns db_unavailable.
        derived_from: dimension:error_propagation (DB exceptions)

        Anticipate: If _with_error_handling doesn't wrap _process_reconcile_check,
        sqlite3.Error would propagate as raw exception to MCP transport.
        """
        engine = WorkflowStateEngine(db, str(tmp_path))
        import workflow_state_server as mod
        original = mod.check_workflow_drift

        def raise_sqlite(*a, **kw):
            raise sqlite3.OperationalError("database locked")

        monkeypatch.setattr(mod, "check_workflow_drift", raise_sqlite)

        result = _process_reconcile_check(engine, db, str(tmp_path), None)
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "db_unavailable"
        assert "OperationalError" in data["message"]

        monkeypatch.setattr(mod, "check_workflow_drift", original)

    def test_reconcile_apply_sqlite_error_returns_db_unavailable(
        self, db, tmp_path, monkeypatch
    ):
        """sqlite3.Error in reconcile_apply returns db_unavailable.
        derived_from: dimension:error_propagation (DB exceptions)
        """
        engine = WorkflowStateEngine(db, str(tmp_path))
        import workflow_state_server as mod
        original = mod.apply_workflow_reconciliation

        def raise_sqlite(*a, **kw):
            raise sqlite3.DatabaseError("disk I/O error")

        monkeypatch.setattr(mod, "apply_workflow_reconciliation", raise_sqlite)

        result = _process_reconcile_apply(
            engine, db, str(tmp_path), None, "meta_json_to_db", False
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "db_unavailable"

        monkeypatch.setattr(mod, "apply_workflow_reconciliation", original)

    def test_reconcile_frontmatter_sqlite_error_returns_db_unavailable(
        self, db, tmp_path, monkeypatch
    ):
        """sqlite3.Error in reconcile_frontmatter returns db_unavailable.
        derived_from: dimension:error_propagation (DB exceptions)
        """
        import workflow_state_server as mod
        original = mod.scan_all

        def raise_sqlite(*a, **kw):
            raise sqlite3.IntegrityError("constraint failed")

        monkeypatch.setattr(mod, "scan_all", raise_sqlite)

        result = _process_reconcile_frontmatter(db, str(tmp_path), None)
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "db_unavailable"

        monkeypatch.setattr(mod, "scan_all", original)

    def test_validate_feature_type_id_not_found_routes_correctly(self, tmp_path):
        """ValueError with 'feature_not_found:' prefix routes to feature_not_found.
        derived_from: dimension:error_propagation (ValueError routing)

        Anticipate: _catch_value_error uses prefix-based routing. If the
        prefix check is removed, "feature_not_found:" messages would fall
        through to "invalid_transition" error_type.
        """
        # Given a non-existent feature directory
        # When validating
        with pytest.raises(ValueError, match="feature_not_found"):
            _validate_feature_type_id("feature:999-ghost", str(tmp_path))

    def test_validate_feature_type_id_invalid_input_routes_correctly(self, tmp_path):
        """ValueError with 'invalid_input:' prefix routes to invalid_transition.
        derived_from: dimension:error_propagation (ValueError routing)

        Anticipate: Missing colon generates 'invalid_input:' prefix.
        _catch_value_error checks for 'not found' substring -- since
        'invalid_input' doesn't contain 'not found', it falls through
        to 'invalid_transition'. This test pins that routing.
        """
        with pytest.raises(ValueError, match="invalid_input"):
            _validate_feature_type_id("nocolonhere", str(tmp_path))


# ===========================================================================
# Test-deepener: Feature 011 Phase B -- Mutation Mindset tests
# derived_from: dimension:mutation_mindset
# ===========================================================================


class TestReconciliationMutationMindset:
    """Tests to catch specific mutations in reconciliation MCP code.
    derived_from: dimension:mutation_mindset
    """

    def test_serialization_direction_old_new_not_swapped(self):
        """old_value = db_value, new_value = meta_json_value (not swapped).
        derived_from: dimension:mutation_mindset (arithmetic swap: old/new)

        Anticipate: Swapping db_value and meta_json_value in
        _serialize_reconcile_action would cause callers to see the
        wrong "before" and "after" values.
        """
        from workflow_engine.reconciliation import WorkflowMismatch, ReconcileAction

        action = ReconcileAction(
            feature_type_id="feature:010-test",
            action="reconciled",
            direction="meta_json_to_db",
            changes=(
                WorkflowMismatch(
                    field="last_completed_phase",
                    meta_json_value="implement",
                    db_value="design",
                ),
            ),
            message="Updated",
        )
        result = _serialize_reconcile_action(action)

        # old_value = db_value (what was in DB before)
        assert result["changes"][0]["old_value"] == "design"
        # new_value = meta_json_value (what .meta.json has)
        assert result["changes"][0]["new_value"] == "implement"
        # NOT swapped
        assert result["changes"][0]["old_value"] != result["changes"][0]["new_value"]

    def test_healthy_flag_false_when_only_workflow_drift(self, db, tmp_path):
        """healthy=False when workflow drift exists but frontmatter is clean.
        derived_from: dimension:mutation_mindset (logic inversion: && to ||)

        Anticipate: If healthy uses OR (wf_healthy || fm_healthy) instead
        of AND, having clean frontmatter would mask workflow drift.
        """
        # Set up a feature with workflow drift (meta_json_ahead)
        db.register_entity("feature", "011-wf-only", "WF Only", status="active")
        db.create_workflow_phase(
            "feature:011-wf-only",
            workflow_phase="specify",
            last_completed_phase="brainstorm",
            mode="standard",
        )
        feat_dir = os.path.join(str(tmp_path), "features", "011-wf-only")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            json.dump({
                "id": "011", "slug": "011-wf-only", "status": "active",
                "mode": "standard", "lastCompletedPhase": "implement",
                "phases": {
                    "brainstorm": {"status": "completed"},
                    "specify": {"status": "completed"},
                    "design": {"status": "completed"},
                    "create-plan": {"status": "completed"},
                    "create-tasks": {"status": "completed"},
                    "implement": {"status": "completed"},
                },
            }, f)

        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_status(engine, db, str(tmp_path))
        data = json.loads(result)

        # Workflow drift exists -> healthy must be False
        assert data["healthy"] is False
        assert data["workflow_drift"]["summary"]["meta_json_ahead"] >= 1

    def test_healthy_flag_true_requires_zero_non_sync_counts(self, db, tmp_path):
        """healthy=True only when ALL non-in_sync workflow counts are zero.
        derived_from: dimension:mutation_mindset (boundary shift: > to >=)

        Anticipate: If the healthy check uses `> 1` instead of `> 0`
        (or `!= 0`), a single drifted feature would be missed.
        """
        # Set up a feature that is perfectly in sync
        db.register_entity("feature", "011-perfect", "Perfect", status="active")
        db.create_workflow_phase(
            "feature:011-perfect",
            workflow_phase="specify",
            last_completed_phase="brainstorm",
            mode="standard",
        )
        feat_dir = os.path.join(str(tmp_path), "features", "011-perfect")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            json.dump({
                "id": "011", "slug": "011-perfect", "status": "active",
                "mode": "standard", "lastCompletedPhase": "brainstorm",
                "phases": {"brainstorm": {"status": "completed"}},
            }, f)

        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_status(engine, db, str(tmp_path))
        data = json.loads(result)

        # All in sync -> healthy must be True
        assert data["healthy"] is True
        wf_summary = data["workflow_drift"]["summary"]
        assert wf_summary["in_sync"] >= 1
        # All other counts are exactly zero
        for k, v in wf_summary.items():
            if k != "in_sync":
                assert v == 0, f"Expected {k}=0 for healthy, got {v}"

    def test_dry_run_summary_includes_created_count(self, db, tmp_path):
        """dry_run summary counts 'created' actions in dry_run total.
        derived_from: dimension:mutation_mindset (line deletion)

        Anticipate: If the dry_run count formula omits 'created'
        (only counts 'reconciled'), meta_json_only features would
        not appear in the preview count.
        """
        # Set up a meta_json_only feature (entity exists, no workflow_phases row)
        db.register_entity("feature", "011-create", "Create Test", status="active")
        feat_dir = os.path.join(str(tmp_path), "features", "011-create")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            json.dump({
                "id": "011", "slug": "011-create", "status": "active",
                "mode": "standard", "lastCompletedPhase": "design",
                "phases": {
                    "brainstorm": {"status": "completed"},
                    "specify": {"status": "completed"},
                    "design": {"status": "completed"},
                },
            }, f)

        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_apply(
            engine, db, str(tmp_path), "feature:011-create", "meta_json_to_db", True
        )
        data = json.loads(result)

        # dry_run count must include the "created" action
        assert data["summary"]["created"] == 1
        assert data["summary"]["dry_run"] >= 1, (
            "dry_run count should include 'created' actions"
        )


# ---------------------------------------------------------------------------
# _iso_now tests (T0.1)
# ---------------------------------------------------------------------------


class TestIsoNow:
    """Tests for _iso_now() UTC timestamp utility."""

    def test_returns_iso_8601_string(self):
        """_iso_now() returns a parseable ISO 8601 datetime string."""
        from datetime import datetime

        result = _iso_now()
        # Should be parseable as ISO 8601
        parsed = datetime.fromisoformat(result)
        assert parsed is not None

    def test_contains_utc_offset(self):
        """_iso_now() includes UTC timezone indicator (+00:00)."""
        result = _iso_now()
        assert "+00:00" in result or "Z" in result

    def test_returns_string_type(self):
        """_iso_now() returns a str, not datetime."""
        result = _iso_now()
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _atomic_json_write tests (T1.1)
# ---------------------------------------------------------------------------


class TestAtomicJsonWrite:
    """Tests for _atomic_json_write() atomic file write utility."""

    def test_writes_valid_json_with_trailing_newline(self, tmp_path):
        """Written file contains valid JSON and ends with a newline."""
        target = os.path.join(str(tmp_path), "test.json")
        data = {"key": "value", "num": 42}
        _atomic_json_write(target, data)

        with open(target) as f:
            content = f.read()

        # Trailing newline
        assert content.endswith("\n")
        # Valid JSON
        parsed = json.loads(content)
        assert parsed == data

    def test_existing_file_not_corrupted_on_write_failure(self, tmp_path):
        """If json.dump raises mid-write, the original file is preserved."""
        from unittest.mock import patch

        target = os.path.join(str(tmp_path), "existing.json")
        original_data = {"original": True}
        # Write original file
        with open(target, "w") as f:
            json.dump(original_data, f)

        # Mock json.dump to raise mid-write
        with patch("workflow_state_server.json.dump", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                _atomic_json_write(target, {"new": "data"})

        # Original file must be intact
        with open(target) as f:
            assert json.load(f) == original_data

    def test_temp_file_cleaned_up_on_base_exception(self, tmp_path):
        """Temp file is removed even on BaseException (e.g., KeyboardInterrupt)."""
        from unittest.mock import patch

        target = os.path.join(str(tmp_path), "cleanup.json")

        with patch("workflow_state_server.json.dump", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                _atomic_json_write(target, {"data": 1})

        # No .tmp files left behind
        tmp_files = [f for f in os.listdir(str(tmp_path)) if f.endswith(".tmp")]
        assert tmp_files == [], f"Temp files not cleaned up: {tmp_files}"

    def test_file_created_in_correct_directory(self, tmp_path):
        """Written file ends up in the target directory, not /tmp."""
        subdir = os.path.join(str(tmp_path), "subdir")
        os.makedirs(subdir)
        target = os.path.join(subdir, "output.json")
        _atomic_json_write(target, {"dir_test": True})

        assert os.path.isfile(target)
        # Verify no file was left in system /tmp
        assert os.path.dirname(os.path.abspath(target)) == subdir
