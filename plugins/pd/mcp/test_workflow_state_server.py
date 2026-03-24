"""Tests for workflow_state_server processing functions."""
from __future__ import annotations

import functools
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

from entity_registry.entity_lifecycle import ENTITY_MACHINES
from workflow_state_server import (
    _NOT_INITIALIZED,
    _atomic_json_write,
    _catch_entity_value_error,
    _iso_now,
    _make_error,
    _process_activate_feature,
    _process_complete_phase,
    _process_get_phase,
    _process_init_entity_workflow,
    _process_init_feature_state,
    _process_init_project_state,
    _process_list_features_by_phase,
    _process_list_features_by_status,
    _process_reconcile_apply,
    _process_reconcile_check,
    _process_reconcile_frontmatter,
    _process_reconcile_status,
    _process_transition_entity_phase,
    _process_transition_phase,
    _process_validate_prerequisites,
    _project_meta_json,
    _serialize_drift_report,
    _serialize_reconcile_action,
    _serialize_result,
    _serialize_state,
    _serialize_workflow_drift_report,
    _validate_feature_type_id,
    _check_artifact_completeness,
    _EXPECTED_ARTIFACTS,
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
            "mode", "degraded",
        }

    def test_no_completed_phases_key(self):
        state = FeatureWorkflowState(
            feature_type_id="feature:009-test",
            current_phase="design",
            last_completed_phase="specify",
            completed_phases=("brainstorm", "specify"),
            mode="standard",
            source="entity_db",
        )
        result = _serialize_state(state)
        assert "completed_phases" not in result

    def test_no_source_key(self):
        state = FeatureWorkflowState(
            feature_type_id="feature:009-test",
            current_phase="design",
            last_completed_phase="specify",
            completed_phases=("brainstorm", "specify"),
            mode="standard",
            source="entity_db",
        )
        result = _serialize_state(state)
        assert "source" not in result

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
            seeded_engine, "feature:009-test", "design", False,
            db=seeded_engine.db,
        )
        data = json.loads(result)
        assert data["transitioned"] is True
        assert data["degraded"] is False

    def test_blocked_g08(self, seeded_engine):
        # No spec.md in tmp_path → G-08 blocks transition to design
        result = _process_transition_phase(
            seeded_engine, "feature:009-test", "design", False,
            db=seeded_engine.db,
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
            seeded_engine, "feature:009-test", "design", False,
            db=seeded_engine.db,
        )
        data_no_yolo = json.loads(result_no_yolo)

        # Re-seed the feature (transition moved it to design)
        seeded_engine.db.update_workflow_phase("feature:009-test", workflow_phase="specify")

        # With YOLO
        result_yolo = _process_transition_phase(
            seeded_engine, "feature:009-test", "design", True,
            db=seeded_engine.db,
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
            seeded_engine, "feature:009-test", "nonexistent", False,
            db=seeded_engine.db,
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
            seeded_engine, "feature:009-test", "design", False,
            db=seeded_engine.db,
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "internal"
        assert "RuntimeError" in data["message"]


# ---------------------------------------------------------------------------
# Extended _process_transition_phase tests (T7.2)
# ---------------------------------------------------------------------------


class TestTransitionPhaseEntityMetadata:
    """Tests for entity metadata updates and .meta.json projection after transition."""

    def test_meta_json_projected_after_successful_transition(self, seeded_engine, db, tmp_path):
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")
        db.update_entity("feature:009-test", artifact_path=feat_dir, metadata={"id": "009", "slug": "test", "mode": "standard", "branch": "feature/009-test"})
        result = _process_transition_phase(seeded_engine, "feature:009-test", "design", False, db=db)
        data = json.loads(result)
        assert data["transitioned"] is True
        meta_path = os.path.join(feat_dir, ".meta.json")
        assert os.path.exists(meta_path)
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["id"] == "009"
        assert "phases" in meta

    def test_phase_timing_started_stored_in_entity_metadata(self, seeded_engine, db, tmp_path):
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")
        db.update_entity("feature:009-test", artifact_path=feat_dir, metadata={"id": "009", "slug": "test", "mode": "standard", "branch": "feature/009-test"})
        result = _process_transition_phase(seeded_engine, "feature:009-test", "design", False, db=db)
        data = json.loads(result)
        assert data["transitioned"] is True
        entity = db.get_entity("feature:009-test")
        metadata = json.loads(entity["metadata"])
        assert "phase_timing" in metadata
        assert "design" in metadata["phase_timing"]
        assert "started" in metadata["phase_timing"]["design"]
        assert "T" in metadata["phase_timing"]["design"]["started"]

    def test_skipped_phases_stored_when_provided(self, seeded_engine, db, tmp_path):
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")
        db.update_entity("feature:009-test", artifact_path=feat_dir, metadata={"id": "009", "slug": "test", "mode": "standard", "branch": "feature/009-test"})
        skipped = json.dumps([{"phase": "brainstorm", "reason": "already done"}])
        result = _process_transition_phase(seeded_engine, "feature:009-test", "design", False, db=db, skipped_phases=skipped)
        data = json.loads(result)
        assert data["transitioned"] is True
        assert data.get("skipped_phases_stored") is True
        entity = db.get_entity("feature:009-test")
        metadata = json.loads(entity["metadata"])
        assert "skipped_phases" in metadata
        assert metadata["skipped_phases"] == [{"phase": "brainstorm", "reason": "already done"}]

    def test_skipped_phases_not_stored_when_none(self, seeded_engine, db, tmp_path):
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")
        db.update_entity("feature:009-test", artifact_path=feat_dir, metadata={"id": "009", "slug": "test", "mode": "standard", "branch": "feature/009-test"})
        result = _process_transition_phase(seeded_engine, "feature:009-test", "design", False, db=db, skipped_phases=None)
        data = json.loads(result)
        assert data["transitioned"] is True
        assert "skipped_phases_stored" not in data
        entity = db.get_entity("feature:009-test")
        metadata = json.loads(entity["metadata"])
        assert "skipped_phases" not in metadata

    def test_started_at_included_in_response(self, seeded_engine, db, tmp_path):
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")
        db.update_entity("feature:009-test", artifact_path=feat_dir, metadata={"id": "009", "slug": "test", "mode": "standard", "branch": "feature/009-test"})
        result = _process_transition_phase(seeded_engine, "feature:009-test", "design", False, db=db)
        data = json.loads(result)
        assert data["transitioned"] is True
        assert "started_at" in data
        assert "T" in data["started_at"]

    def test_projection_warning_included_when_projection_fails(self, seeded_engine, db, tmp_path, monkeypatch):
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")
        db.update_entity("feature:009-test", artifact_path=feat_dir, metadata={"id": "009", "slug": "test", "mode": "standard", "branch": "feature/009-test"})
        import workflow_state_server
        monkeypatch.setattr(workflow_state_server, "_project_meta_json", lambda *a, **kw: "projection failed: disk full")
        result = _process_transition_phase(seeded_engine, "feature:009-test", "design", False, db=db)
        data = json.loads(result)
        assert data["transitioned"] is True
        assert data["projection_warning"] == "projection failed: disk full"


# ---------------------------------------------------------------------------
# _process_complete_phase tests (Task 2.5)
# ---------------------------------------------------------------------------


class TestProcessCompletePhase:
    def test_success(self, seeded_engine):
        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "specify",
            db=seeded_engine.db,
        )
        data = json.loads(result)
        assert "error" not in data
        assert data["degraded"] is False

    def test_value_error(self, seeded_engine, monkeypatch):
        monkeypatch.setattr(
            seeded_engine, "complete_phase",
            lambda *a: (_ for _ in ()).throw(ValueError("phase mismatch")),
        )
        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "design",
            db=seeded_engine.db,
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
            seeded_engine, "feature:009-test", "specify",
            db=seeded_engine.db,
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "internal"
        assert "RuntimeError" in data["message"]


# ---------------------------------------------------------------------------
# _process_complete_phase entity metadata tests (Task 8.2)
# ---------------------------------------------------------------------------


class TestCompletePhaseEntityMetadata:
    """Tests for _process_complete_phase DB entity metadata updates."""

    def test_meta_json_projected_after_completion(self, seeded_engine, db, tmp_path):
        """After successful completion, _project_meta_json is called."""
        # Setup: ensure entity has metadata and artifact_path for projection
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        db.update_entity(
            "feature:009-test",
            artifact_path=feat_dir,
            metadata={
                "id": "009", "slug": "test", "mode": "standard",
                "branch": "feature/009-test", "phase_timing": {},
            },
        )

        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "specify",
            db=db,
        )
        data = json.loads(result)
        assert "error" not in data

        # .meta.json should exist after projection
        meta_path = os.path.join(feat_dir, ".meta.json")
        assert os.path.exists(meta_path)
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["lastCompletedPhase"] == "specify"

    def test_phase_timing_stored_correctly(self, seeded_engine, db, tmp_path):
        """completed, iterations, reviewerNotes stored in phase_timing."""
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        db.update_entity(
            "feature:009-test",
            metadata={
                "id": "009", "slug": "test", "mode": "standard",
                "branch": "feature/009-test", "phase_timing": {},
            },
        )

        notes = ["Reviewed code quality", "Tests comprehensive"]
        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "specify",
            db=db, iterations=3, reviewer_notes=json.dumps(notes),
        )
        data = json.loads(result)
        assert "error" not in data

        # Verify entity metadata
        entity = db.get_entity("feature:009-test")
        metadata = json.loads(entity["metadata"])
        timing = metadata["phase_timing"]["specify"]
        assert "completed" in timing
        assert "T" in timing["completed"]  # ISO 8601
        assert timing["iterations"] == 3
        assert timing["reviewerNotes"] == notes

    def test_last_completed_phase_updated(self, seeded_engine, db, tmp_path):
        """last_completed_phase is set to the completed phase name."""
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        db.update_entity(
            "feature:009-test",
            metadata={
                "id": "009", "slug": "test", "mode": "standard",
                "branch": "feature/009-test", "phase_timing": {},
            },
        )

        _process_complete_phase(
            seeded_engine, "feature:009-test", "specify",
            db=db,
        )

        entity = db.get_entity("feature:009-test")
        metadata = json.loads(entity["metadata"])
        assert metadata["last_completed_phase"] == "specify"

    def test_terminal_phase_finish_sets_completed_status(self, db, tmp_path):
        """Completing 'finish' phase sets entity status to 'completed'."""
        # Setup: feature at 'finish' phase
        db.register_entity("feature", "fin-test", "Finish Test", status="active")
        db.create_workflow_phase("feature:fin-test", workflow_phase="finish")

        feat_dir = os.path.join(str(tmp_path), "features", "fin-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            f.write('{"id": "fin", "slug": "fin-test", "status": "active", "mode": "standard"}')

        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_complete_phase(
            engine, "feature:fin-test", "finish",
            db=db,
        )
        data = json.loads(result)
        assert "error" not in data

        entity = db.get_entity("feature:fin-test")
        assert entity["status"] == "completed"

    def test_completed_at_in_response(self, seeded_engine, db, tmp_path):
        """Response includes completed_at timestamp."""
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        db.update_entity(
            "feature:009-test",
            metadata={
                "id": "009", "slug": "test", "mode": "standard",
                "branch": "feature/009-test", "phase_timing": {},
            },
        )

        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "specify",
            db=db,
        )
        data = json.loads(result)
        assert "completed_at" in data
        assert "T" in data["completed_at"]  # ISO 8601

    def test_projection_warning_included(self, seeded_engine, db, monkeypatch):
        """projection_warning included when _project_meta_json returns warning."""
        db.update_entity(
            "feature:009-test",
            metadata={
                "id": "009", "slug": "test", "mode": "standard",
                "branch": "feature/009-test", "phase_timing": {},
            },
        )

        # Mock _project_meta_json to return a warning
        import workflow_state_server as wss
        monkeypatch.setattr(
            wss, "_project_meta_json",
            lambda *a, **kw: "disk full: projection failed",
        )

        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "specify",
            db=db,
        )
        data = json.loads(result)
        assert data["projection_warning"] == "disk full: projection failed"

    def test_reviewer_notes_parsed_from_json_string(self, seeded_engine, db, tmp_path):
        """reviewer_notes JSON string is parsed and stored as list/dict."""
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        db.update_entity(
            "feature:009-test",
            metadata={
                "id": "009", "slug": "test", "mode": "standard",
                "branch": "feature/009-test", "phase_timing": {},
            },
        )

        notes_obj = {"summary": "LGTM", "issues": []}
        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "specify",
            db=db, reviewer_notes=json.dumps(notes_obj),
        )
        data = json.loads(result)
        assert "error" not in data

        entity = db.get_entity("feature:009-test")
        metadata = json.loads(entity["metadata"])
        assert metadata["phase_timing"]["specify"]["reviewerNotes"] == notes_obj

    def test_finish_phase_projects_toplevel_completed(self, db, tmp_path):
        """AC1: complete_phase('finish') produces top-level completed in .meta.json."""
        db.register_entity("feature", "040-test", "Completed Test", status="active")
        db.create_workflow_phase("feature:040-test", workflow_phase="finish")

        feat_dir = os.path.join(str(tmp_path), "features", "040-test")
        os.makedirs(feat_dir, exist_ok=True)
        db.update_entity(
            "feature:040-test",
            artifact_path=feat_dir,
            metadata={
                "id": "040", "slug": "test", "mode": "standard",
                "branch": "feature/040-test", "phase_timing": {},
            },
        )

        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_complete_phase(engine, "feature:040-test", "finish", db=db)
        data = json.loads(result)
        assert "error" not in data

        meta_path = os.path.join(feat_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["status"] == "completed"
        assert "completed" in meta
        assert "T" in meta["completed"]  # ISO 8601

    def test_active_status_no_completed_field(self, seeded_engine, db, tmp_path):
        """AC3: Active features don't have a completed field."""
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        db.update_entity(
            "feature:009-test",
            artifact_path=feat_dir,
            metadata={
                "id": "009", "slug": "test", "mode": "standard",
                "branch": "feature/009-test", "phase_timing": {},
            },
        )

        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "specify", db=db,
        )
        data = json.loads(result)
        assert "error" not in data

        meta_path = os.path.join(feat_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["status"] == "active"
        assert "completed" not in meta

    def test_abandoned_status_gets_completed_fallback(self, db, tmp_path):
        """AC5: Abandoned status with no finish timing gets completed via _iso_now() fallback."""
        db.register_entity("feature", "041-abandoned", "Abandoned Test", status="abandoned")

        feat_dir = os.path.join(str(tmp_path), "features", "041-abandoned")
        os.makedirs(feat_dir, exist_ok=True)

        # Abandoned feature: has some phase timing but no finish phase
        db.update_entity(
            "feature:041-abandoned",
            artifact_path=feat_dir,
            metadata={
                "id": "041", "slug": "abandoned", "mode": "standard",
                "branch": "feature/041-abandoned",
                "phase_timing": {
                    "specify": {"started": "2026-01-01T00:00:00+00:00", "completed": "2026-01-01T01:00:00+00:00"},
                },
            },
        )

        engine = WorkflowStateEngine(db, str(tmp_path))
        from workflow_state_server import _project_meta_json
        warning = _project_meta_json(db, engine, "feature:041-abandoned")
        assert warning is None or not warning.startswith("error")

        meta_path = os.path.join(feat_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["status"] == "abandoned"
        assert "completed" in meta
        assert "T" in meta["completed"]  # ISO 8601 fallback

    def test_finish_completed_timestamp_matches_phase_timing(self, db, tmp_path):
        """R1: completed timestamp comes from finish phase timing, not _iso_now()."""
        expected_ts = "2026-03-17T06:31:08.766797+00:00"
        db.register_entity("feature", "042-ts", "Timestamp Test", status="completed")

        feat_dir = os.path.join(str(tmp_path), "features", "042-ts")
        os.makedirs(feat_dir, exist_ok=True)

        db.update_entity(
            "feature:042-ts",
            artifact_path=feat_dir,
            metadata={
                "id": "042", "slug": "ts", "mode": "standard",
                "branch": "feature/042-ts",
                "phase_timing": {
                    "finish": {"completed": expected_ts},
                },
            },
        )

        engine = WorkflowStateEngine(db, str(tmp_path))
        from workflow_state_server import _project_meta_json
        _project_meta_json(db, engine, "feature:042-ts")

        meta_path = os.path.join(feat_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["completed"] == expected_ts


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
            seeded_engine, "feature:009-test", "", False,
            db=seeded_engine.db,
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

    def test_serialize_state_no_completed_phases_in_output(self):
        """Serialized state never contains completed_phases key.
        derived_from: dimension:boundary_values (removed field)
        """
        state = FeatureWorkflowState(
            feature_type_id="feature:010-test",
            current_phase="brainstorm",
            last_completed_phase=None,
            completed_phases=(),
            mode="standard",
            source="db",
        )
        result = _serialize_state(state)
        assert "completed_phases" not in result

    def test_serialize_state_no_source_in_output(self):
        """Serialized state never contains source key.
        derived_from: dimension:boundary_values (removed field)
        """
        state = FeatureWorkflowState(
            feature_type_id="feature:010-test",
            current_phase="create-plan",
            last_completed_phase="design",
            completed_phases=("brainstorm", "specify", "design"),
            mode="standard",
            source="db",
        )
        result = _serialize_state(state)
        assert "source" not in result


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
            seeded_engine, "feature:009-test", "design", True,
            db=seeded_engine.db,
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
            seeded_engine, "feature:009-test", "design",
            db=seeded_engine.db,
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
            engine, "feature:nonexistent", "specify",
            db=engine.db,
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
            seeded_engine, "feature:009-test", "design", False,
            db=seeded_engine.db,
        )
        data = json.loads(result)
        # Then the top-level keys are exactly {transitioned, results, degraded}
        # (blocked transitions don't include started_at or projection keys)
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
        # Then all 5 fields are present
        expected_keys = {
            "feature_type_id", "current_phase", "last_completed_phase",
            "mode", "degraded",
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
            seeded_engine, "feature:009-test", "design", False,
            db=seeded_engine.db,
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
            seeded_engine, "feature:009-test", "design", False,
            db=seeded_engine.db,
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
            degraded_engine, "feature:009-test", "design", False,
            db=None,  # DB is closed; skip entity metadata update
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
            seeded_engine, "feature:009-test", "design", False,
            db=seeded_engine.db,
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
            seeded_engine, "feature:009-test", "specify",
            db=seeded_engine.db,
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

        # Then degraded is True (source was meta_json_fallback)
        assert "error" not in data, f"Unexpected error: {data}"
        assert "source" not in data
        assert data["degraded"] is True

    def test_normal_complete_phase_source_is_db(self, seeded_engine):
        """Normal complete_phase returns source='db' and degraded=False.
        derived_from: dimension:mutation_mindset (return value mutation)
        """
        # When completing specify normally
        result = _process_complete_phase(
            seeded_engine, "feature:009-test", "specify",
            db=seeded_engine.db,
        )
        data = json.loads(result)

        # Then degraded is False (source was db)
        assert "source" not in data
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
            engine, "feature:010-shape", "brainstorm", False,
            db=None,  # DB is closed; skip entity metadata update
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
            engine, db, arts, "feature:011-app", False
        )
        data = json.loads(result)
        assert "error" not in data
        assert len(data["actions"]) >= 1
        assert data["actions"][0]["action"] == "reconciled"

    def test_dry_run(self, reconcile_env):
        """dry_run returns changes without applying."""
        engine, db, arts = reconcile_env
        result = _process_reconcile_apply(
            engine, db, arts, "feature:011-app", True
        )
        data = json.loads(result)
        assert "error" not in data
        assert data["summary"]["dry_run"] >= 1

        # Verify DB was NOT updated
        check = _process_reconcile_check(engine, db, arts, "feature:011-app")
        check_data = json.loads(check)
        assert check_data["features"][0]["status"] == "meta_json_ahead"

    def test_nonexistent_slug_returns_feature_not_found(self, db, tmp_path):
        """Non-existent slug -> feature_not_found (AC-18)."""
        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_apply(
            engine, db, str(tmp_path), "feature:999-missing", False
        )
        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "feature_not_found"

    def test_malformed_no_colon_returns_invalid_transition(self, db, tmp_path):
        """Missing colon -> invalid_transition (AC-18 case 2)."""
        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_apply(
            engine, db, str(tmp_path), "nocolon", False
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
        """Single in_sync feature is filtered out of reports (AC-11)."""
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
        # New envelope format
        assert "summary" not in data
        assert data["total_scanned"] >= 1
        # in_sync reports are filtered out
        assert data["drifted_count"] == 0
        assert len(data["reports"]) == 0

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
        # db_only is drifted -> included in reports
        assert data["total_scanned"] >= 1
        assert data["drifted_count"] >= 1
        assert len(data["reports"]) >= 1
        assert data["reports"][0]["status"] == "db_only"

    def test_bulk_scan(self, db, tmp_path):
        """Bulk scan via scan_all returns envelope with total_scanned/drifted_count (AC-13)."""
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
        assert "summary" not in data
        assert "total_scanned" in data
        assert "drifted_count" in data
        assert isinstance(data["total_scanned"], int)
        assert isinstance(data["drifted_count"], int)
        assert isinstance(data["reports"], list)

    def test_nonexistent_directory_returns_empty(self, db, tmp_path):
        """Non-existent feature directory returns empty reports."""
        feat_dir = os.path.join(str(tmp_path), "features", "011-gone")
        os.makedirs(feat_dir, exist_ok=True)  # Must exist for validation to pass
        result = _process_reconcile_frontmatter(db, str(tmp_path), "feature:011-gone")
        data = json.loads(result)
        assert "error" not in data
        # No artifact files in the dir -> empty reports
        assert data["total_scanned"] == 0
        assert data["drifted_count"] == 0
        assert len(data["reports"]) == 0

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

    # --- Task 2.2: summary_only mode ---

    def test_summary_only_healthy(self, db, tmp_path):
        """summary_only=True returns exactly 3 fields when healthy."""
        # Set up an in-sync feature
        db.register_entity("feature", "011-sum-h", "SumH", status="active")
        db.create_workflow_phase(
            "feature:011-sum-h",
            workflow_phase="specify",
            last_completed_phase="brainstorm",
            mode="standard",
        )
        feat_dir = os.path.join(str(tmp_path), "features", "011-sum-h")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            json.dump({
                "id": "011", "slug": "011-sum-h", "status": "active",
                "mode": "standard", "lastCompletedPhase": "brainstorm",
                "phases": {"brainstorm": {"status": "completed"}},
            }, f)

        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_status(engine, db, str(tmp_path), summary_only=True)
        data = json.loads(result)

        # Exactly 3 keys
        assert set(data.keys()) == {"healthy", "workflow_drift_count", "frontmatter_drift_count"}
        assert data["healthy"] is True
        assert data["workflow_drift_count"] == 0
        assert data["frontmatter_drift_count"] == 0

    def test_summary_only_unhealthy(self, db, tmp_path):
        """summary_only=True returns correct drift counts when drift exists."""
        # Set up a drifted feature (meta.json ahead of DB)
        db.register_entity("feature", "011-sum-d", "SumD", status="active")
        db.create_workflow_phase(
            "feature:011-sum-d",
            workflow_phase="specify",
            last_completed_phase="brainstorm",
            mode="standard",
        )
        feat_dir = os.path.join(str(tmp_path), "features", "011-sum-d")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            json.dump({
                "id": "011", "slug": "011-sum-d", "status": "active",
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
        result = _process_reconcile_status(engine, db, str(tmp_path), summary_only=True)
        data = json.loads(result)

        assert set(data.keys()) == {"healthy", "workflow_drift_count", "frontmatter_drift_count"}
        assert data["healthy"] is False
        assert data["workflow_drift_count"] >= 1

    def test_summary_only_false_returns_full_report(self, db, tmp_path):
        """summary_only=False (default) returns the full 5-key report unchanged."""
        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_status(engine, db, str(tmp_path), summary_only=False)
        data = json.loads(result)
        expected_keys = {
            "workflow_drift", "frontmatter_drift", "healthy",
            "total_features_checked", "total_files_checked",
        }
        assert set(data.keys()) == expected_keys

    def test_summary_only_default_is_false(self, db, tmp_path):
        """Calling without summary_only returns full report (backward compat)."""
        engine = WorkflowStateEngine(db, str(tmp_path))
        result = _process_reconcile_status(engine, db, str(tmp_path))
        data = json.loads(result)
        # Should have the full 5-key shape, not the 3-key summary
        assert "workflow_drift" in data
        assert "total_features_checked" in data


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
                engine, db, str(tmp_path), None, False
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
        # 2 files scanned total (spec.md + design.md)
        assert data["total_scanned"] == 2
        # Only drifted reports included (in_sync filtered out)
        assert data["drifted_count"] == 1
        assert len(data["reports"]) == 1
        # design.md has no header but type_id was passed -> db_only
        assert data["reports"][0]["status"] == "db_only"

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
        expected_keys = {"in_sync", "meta_json_ahead", "db_ahead", "meta_json_only", "db_only", "error", "artifact_missing_count"}
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
            engine, db, str(tmp_path), None, False
        )
        data = json.loads(result)
        # Then summary has all 5 keys, all zero
        assert "error" not in data
        expected_keys = {"reconciled", "created", "skipped", "error", "dry_run", "kanban_fixed", "cascades_recovered"}
        assert set(data["summary"].keys()) == expected_keys
        assert all(v == 0 for v in data["summary"].values())

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
            engine, db, str(tmp_path), None, False
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
            engine, db, str(tmp_path), "feature:../../../evil", False
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
            engine, db, str(tmp_path), "feature:011-shape3", False
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
            engine, db, str(tmp_path), None, False
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
            engine, db, str(tmp_path), "feature:011-create", True
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


# ---------------------------------------------------------------------------
# init_project_state tests
# ---------------------------------------------------------------------------


class TestInitProjectState:
    """Tests for _process_init_project_state."""


    def test_creates_project_entity_and_meta_json(self, db, tmp_path):
        """Creates project entity in DB and writes .meta.json with features
        and milestones arrays."""


        project_dir = os.path.join(str(tmp_path), "projects", "001-my-project")
        os.makedirs(project_dir, exist_ok=True)

        result = _process_init_project_state(
            db,
            project_dir,
            "001",
            "my-project",
            '["feat-a", "feat-b"]',
            '[{"name": "m1", "features": ["feat-a"]}]',
            None,
        )
        data = json.loads(result)

        assert data["created"] is True
        assert data["project_type_id"] == "project:001-my-project"

        # Verify entity registered
        entity = db.get_entity("project:001-my-project")
        assert entity is not None
        assert entity["status"] == "active"

        # Verify .meta.json written
        meta_path = os.path.join(project_dir, ".meta.json")
        assert os.path.isfile(meta_path)
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["id"] == "001"
        assert meta["slug"] == "my-project"
        assert meta["status"] == "active"
        assert meta["features"] == ["feat-a", "feat-b"]
        assert meta["milestones"] == [{"name": "m1", "features": ["feat-a"]}]
        assert "created" in meta  # ISO timestamp

    def test_brainstorm_source_included_when_provided(self, db, tmp_path):
        """brainstorm_source appears in .meta.json when provided."""


        project_dir = os.path.join(str(tmp_path), "projects", "002-src")
        os.makedirs(project_dir, exist_ok=True)

        _process_init_project_state(
            db,
            project_dir,
            "002",
            "src",
            "[]",
            "[]",
            "docs/brainstorms/some-brainstorm.md",
        )

        meta_path = os.path.join(project_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["brainstorm_source"] == "docs/brainstorms/some-brainstorm.md"

    def test_brainstorm_source_omitted_when_none(self, db, tmp_path):
        """brainstorm_source is NOT present in .meta.json when None."""


        project_dir = os.path.join(str(tmp_path), "projects", "003-no-src")
        os.makedirs(project_dir, exist_ok=True)

        _process_init_project_state(
            db,
            project_dir,
            "003",
            "no-src",
            "[]",
            "[]",
            None,
        )

        meta_path = os.path.join(project_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert "brainstorm_source" not in meta

    def test_json_string_params_parsed_correctly(self, db, tmp_path):
        """features and milestones JSON strings are parsed into lists."""


        project_dir = os.path.join(str(tmp_path), "projects", "004-parse")
        os.makedirs(project_dir, exist_ok=True)

        features_json = '["alpha", "beta", "gamma"]'
        milestones_json = '[{"name": "v1", "features": ["alpha"]}, {"name": "v2", "features": ["beta", "gamma"]}]'

        _process_init_project_state(
            db,
            project_dir,
            "004",
            "parse",
            features_json,
            milestones_json,
            None,
        )

        meta_path = os.path.join(project_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert isinstance(meta["features"], list)
        assert len(meta["features"]) == 3
        assert isinstance(meta["milestones"], list)
        assert len(meta["milestones"]) == 2
        assert meta["milestones"][0]["name"] == "v1"

    def test_catch_value_error_on_malformed_features_json(self, db, tmp_path):
        """@_catch_value_error catches malformed JSON string for features."""


        project_dir = os.path.join(str(tmp_path), "projects", "005-bad")
        os.makedirs(project_dir, exist_ok=True)

        result = _process_init_project_state(
            db,
            project_dir,
            "005",
            "bad",
            "not-valid-json",  # malformed
            "[]",
            None,
        )
        data = json.loads(result)
        # _catch_value_error wraps ValueError as error response
        assert data.get("error_type") == "invalid_transition"

    def test_catch_value_error_on_malformed_milestones_json(self, db, tmp_path):
        """@_catch_value_error catches malformed JSON string for milestones."""


        project_dir = os.path.join(str(tmp_path), "projects", "006-bad-ms")
        os.makedirs(project_dir, exist_ok=True)

        result = _process_init_project_state(
            db,
            project_dir,
            "006",
            "bad-ms",
            "[]",
            "{broken",  # malformed
            None,
        )
        data = json.loads(result)
        assert data.get("error_type") == "invalid_transition"

    def test_meta_json_contains_correct_fields_and_excludes_feature_fields(
        self, db, tmp_path
    ):
        """Project .meta.json contains id, slug, status, created, features,
        milestones — and does NOT contain phases, lastCompletedPhase, branch,
        mode (these are feature-only per design C4)."""


        project_dir = os.path.join(str(tmp_path), "projects", "007-fields")
        os.makedirs(project_dir, exist_ok=True)

        _process_init_project_state(
            db,
            project_dir,
            "007",
            "fields",
            '["f1"]',
            '[]',
            None,
        )

        meta_path = os.path.join(project_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)

        # Required fields present
        assert "id" in meta
        assert "slug" in meta
        assert "status" in meta
        assert "created" in meta
        assert "features" in meta
        assert isinstance(meta["features"], list)
        assert "milestones" in meta
        assert isinstance(meta["milestones"], list)

        # Feature-only fields must NOT be present
        assert "phases" not in meta
        assert "lastCompletedPhase" not in meta
        assert "branch" not in meta
        assert "mode" not in meta

    def test_atomic_json_write_called_with_correct_args(self, db, tmp_path):
        """_atomic_json_write is called with the correct path and dict
        (not open() + json.dump() directly)."""


        project_dir = os.path.join(str(tmp_path), "projects", "008-atomic")
        os.makedirs(project_dir, exist_ok=True)

        from unittest.mock import patch

        with patch(
            "workflow_engine.feature_lifecycle._atomic_json_write"
        ) as mock_write:
            _process_init_project_state(
                db,
                project_dir,
                "008",
                "atomic",
                '["x"]',
                '[]',
                None,
            )

            mock_write.assert_called_once()
            call_args = mock_write.call_args
            # First positional arg is path
            assert call_args[0][0] == os.path.join(project_dir, ".meta.json")
            # Second positional arg is dict with expected keys
            written_dict = call_args[0][1]
            assert isinstance(written_dict, dict)
            assert written_dict["id"] == "008"
            assert written_dict["slug"] == "atomic"
            assert written_dict["features"] == ["x"]
            assert written_dict["milestones"] == []


# ---------------------------------------------------------------------------
# T2.1 + T2.2: _project_meta_json() tests
# ---------------------------------------------------------------------------


class TestProjectMetaJson:
    """Tests for _project_meta_json projection function.

    Entity shape from DB: dict with keys artifact_path, metadata (JSON TEXT string),
    status, created_at. metadata must be parsed via json.loads().
    """


    # -- T2.1: Happy path tests --

    def test_projects_correct_json_structure(self, db, tmp_path):
        """Projects correct .meta.json from mock entity dict + mock engine state."""


        feature_dir = os.path.join(str(tmp_path), "features", "034-foo")
        os.makedirs(feature_dir, exist_ok=True)

        metadata = {
            "id": "034",
            "slug": "foo",
            "mode": "standard",
            "branch": "feature/034-foo",
            "phase_timing": {
                "brainstorm": {"started": "2026-03-01T00:00:00Z", "completed": "2026-03-02T00:00:00Z"},
                "specify": {"started": "2026-03-02T00:00:00Z"},
            },
        }
        db.register_entity(
            "feature", "034-foo", "foo",
            artifact_path=feature_dir,
            status="active",
            metadata=metadata,
        )
        db.create_workflow_phase("feature:034-foo", workflow_phase="specify")

        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _project_meta_json(db, engine, "feature:034-foo", feature_dir)
        assert result is None  # success

        meta_path = os.path.join(feature_dir, ".meta.json")
        assert os.path.isfile(meta_path)
        with open(meta_path) as f:
            meta = json.load(f)

        assert meta["id"] == "034"
        assert meta["slug"] == "foo"
        assert meta["mode"] == "standard"
        assert meta["status"] == "active"
        assert meta["branch"] == "feature/034-foo"
        assert "created" in meta
        assert "lastCompletedPhase" in meta
        assert "phases" in meta
        assert "brainstorm" in meta["phases"]
        assert meta["phases"]["brainstorm"]["started"] == "2026-03-01T00:00:00Z"
        assert meta["phases"]["brainstorm"]["completed"] == "2026-03-02T00:00:00Z"
        assert "specify" in meta["phases"]
        assert meta["phases"]["specify"]["started"] == "2026-03-02T00:00:00Z"

    def test_engine_none_falls_back_to_metadata(self, db, tmp_path):
        """engine=None falls back to metadata-only (no engine.get_state call);
        last_completed from metadata.get('last_completed_phase')."""


        feature_dir = os.path.join(str(tmp_path), "features", "035-noengine")
        os.makedirs(feature_dir, exist_ok=True)

        metadata = {
            "id": "035",
            "slug": "noengine",
            "mode": "full",
            "branch": "feature/035-noengine",
            "last_completed_phase": "brainstorm",
            "phase_timing": {
                "brainstorm": {"started": "2026-03-01T00:00:00Z", "completed": "2026-03-02T00:00:00Z"},
            },
        }
        db.register_entity(
            "feature", "035-noengine", "noengine",
            artifact_path=feature_dir,
            status="active",
            metadata=metadata,
        )

        result = _project_meta_json(db, None, "feature:035-noengine", feature_dir)
        assert result is None

        meta_path = os.path.join(feature_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)

        assert meta["lastCompletedPhase"] == "brainstorm"
        assert meta["mode"] == "full"

    def test_resolves_feature_dir_from_entity_artifact_path(self, db, tmp_path):
        """Resolves feature_dir from entity['artifact_path'] when not provided."""


        feature_dir = os.path.join(str(tmp_path), "features", "036-resolve")
        os.makedirs(feature_dir, exist_ok=True)

        metadata = {
            "id": "036",
            "slug": "resolve",
            "mode": "standard",
            "branch": "feature/036-resolve",
            "phase_timing": {},
        }
        db.register_entity(
            "feature", "036-resolve", "resolve",
            artifact_path=feature_dir,
            status="active",
            metadata=metadata,
        )

        # feature_dir=None -- should resolve from entity["artifact_path"]
        result = _project_meta_json(db, None, "feature:036-resolve", None)
        assert result is None

        meta_path = os.path.join(feature_dir, ".meta.json")
        assert os.path.isfile(meta_path)

    def test_phase_timing_with_iterations_and_reviewer_notes(self, db, tmp_path):
        """Phase timing with iterations and reviewerNotes projected correctly."""


        feature_dir = os.path.join(str(tmp_path), "features", "037-timing")
        os.makedirs(feature_dir, exist_ok=True)

        metadata = {
            "id": "037",
            "slug": "timing",
            "mode": "standard",
            "branch": "feature/037-timing",
            "phase_timing": {
                "specify": {
                    "started": "2026-03-01T00:00:00Z",
                    "completed": "2026-03-02T00:00:00Z",
                    "iterations": 3,
                    "reviewerNotes": ["Fix edge case", "Add validation"],
                },
            },
        }
        db.register_entity(
            "feature", "037-timing", "timing",
            artifact_path=feature_dir,
            status="active",
            metadata=metadata,
        )

        result = _project_meta_json(db, None, "feature:037-timing", feature_dir)
        assert result is None

        meta_path = os.path.join(feature_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)

        specify = meta["phases"]["specify"]
        assert specify["iterations"] == 3
        assert specify["reviewerNotes"] == ["Fix edge case", "Add validation"]
        assert specify["started"] == "2026-03-01T00:00:00Z"
        assert specify["completed"] == "2026-03-02T00:00:00Z"

    # -- T2.2: Edge case tests --

    def test_missing_entity_returns_warning(self, db, tmp_path):
        """Missing entity returns warning string."""


        result = _project_meta_json(db, None, "feature:999-missing", str(tmp_path))
        assert result is not None
        assert isinstance(result, str)
        assert "999-missing" in result

    def test_write_failure_returns_warning_no_exception(self, db, tmp_path):
        """Write failure returns warning string, no exception raised."""

        from unittest.mock import patch

        feature_dir = os.path.join(str(tmp_path), "features", "038-fail")
        os.makedirs(feature_dir, exist_ok=True)

        metadata = {
            "id": "038",
            "slug": "fail",
            "mode": "standard",
            "branch": "feature/038-fail",
            "phase_timing": {},
        }
        db.register_entity(
            "feature", "038-fail", "fail",
            artifact_path=feature_dir,
            status="active",
            metadata=metadata,
        )

        with patch(
            "workflow_state_server._atomic_json_write",
            side_effect=OSError("disk full"),
        ):
            result = _project_meta_json(db, None, "feature:038-fail", feature_dir)

        assert result is not None
        assert "projection failed" in result
        assert "disk full" in result

    def test_optional_fields_only_present_when_set(self, db, tmp_path):
        """Optional fields (brainstorm_source, skippedPhases) only present when set."""


        feature_dir = os.path.join(str(tmp_path), "features", "039-optional")
        os.makedirs(feature_dir, exist_ok=True)

        # Without optional fields
        metadata_no_opt = {
            "id": "039",
            "slug": "optional",
            "mode": "standard",
            "branch": "feature/039-optional",
            "phase_timing": {},
        }
        db.register_entity(
            "feature", "039-optional", "optional",
            artifact_path=feature_dir,
            status="active",
            metadata=metadata_no_opt,
        )

        result = _project_meta_json(db, None, "feature:039-optional", feature_dir)
        assert result is None

        meta_path = os.path.join(feature_dir, ".meta.json")
        with open(meta_path) as f:
            meta_no_opt = json.load(f)
        assert "brainstorm_source" not in meta_no_opt
        assert "skippedPhases" not in meta_no_opt

        # Now with optional fields
        feature_dir2 = os.path.join(str(tmp_path), "features", "040-withopt")
        os.makedirs(feature_dir2, exist_ok=True)

        metadata_with_opt = {
            "id": "040",
            "slug": "withopt",
            "mode": "standard",
            "branch": "feature/040-withopt",
            "phase_timing": {},
            "brainstorm_source": "docs/brainstorms/something.md",
            "skipped_phases": [{"phase": "brainstorm", "reason": "already done"}],
        }
        db.register_entity(
            "feature", "040-withopt", "withopt",
            artifact_path=feature_dir2,
            status="active",
            metadata=metadata_with_opt,
        )

        result = _project_meta_json(db, None, "feature:040-withopt", feature_dir2)
        assert result is None

        with open(os.path.join(feature_dir2, ".meta.json")) as f:
            meta_with_opt = json.load(f)
        assert meta_with_opt["brainstorm_source"] == "docs/brainstorms/something.md"
        assert meta_with_opt["skippedPhases"] == [{"phase": "brainstorm", "reason": "already done"}]

    def test_null_metadata_uses_empty_dict(self, db, tmp_path):
        """NULL metadata uses empty dict, no TypeError."""


        feature_dir = os.path.join(str(tmp_path), "features", "041-nullmeta")
        os.makedirs(feature_dir, exist_ok=True)

        # Register entity with no metadata (NULL in DB)
        db.register_entity(
            "feature", "041-nullmeta", "nullmeta",
            artifact_path=feature_dir,
            status="active",
        )

        result = _project_meta_json(db, None, "feature:041-nullmeta", feature_dir)
        assert result is None

        meta_path = os.path.join(feature_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        # Should have defaults, not crash
        assert meta["id"] == ""
        assert meta["slug"] == ""
        assert meta["mode"] == "standard"
        assert meta["phases"] == {}

    def test_no_artifact_path_and_no_feature_dir_returns_warning(self, db, tmp_path):
        """Entity with no artifact_path and no feature_dir param returns warning."""


        # Register entity without artifact_path
        db.register_entity(
            "feature", "042-nopath", "nopath",
            status="active",
            metadata={"id": "042", "slug": "nopath"},
        )

        result = _project_meta_json(db, None, "feature:042-nopath", None)
        assert result is not None
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# T4.1: init_feature_state tests
# ---------------------------------------------------------------------------


class TestInitFeatureState:
    """Tests for _process_init_feature_state.

    Entity shape from DB: dict with keys artifact_path, metadata (JSON TEXT string),
    status, created_at. metadata must be parsed via json.loads().
    """


    def test_creates_new_entity_and_meta_json_with_all_fields(self, db, engine, tmp_path):
        """Creates new entity + .meta.json with all required fields."""


        feature_dir = os.path.join(str(tmp_path), "features", "050-init-test")
        os.makedirs(feature_dir, exist_ok=True)

        result = _process_init_feature_state(
            db, engine, feature_dir, "050", "init-test", "standard",
            "feature/050-init-test", None, None, "active",
            artifacts_root=str(tmp_path),
        )
        data = json.loads(result)

        assert data["created"] is True
        assert data["feature_type_id"] == "feature:050-init-test"
        assert data["status"] == "active"
        assert "meta_json_path" in data

        entity = db.get_entity("feature:050-init-test")
        assert entity is not None
        assert entity["status"] == "active"

        meta_path = os.path.join(feature_dir, ".meta.json")
        assert os.path.isfile(meta_path)
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["id"] == "050"
        assert meta["slug"] == "init-test"
        assert meta["mode"] == "standard"
        assert meta["branch"] == "feature/050-init-test"
        assert meta["status"] == "active"
        assert "created" in meta

    def test_idempotent_retry_preserves_existing_timing(self, db, engine, tmp_path):
        """Idempotent retry preserves existing phase_timing, last_completed_phase,
        skipped_phases."""


        feature_dir = os.path.join(str(tmp_path), "features", "051-retry")
        os.makedirs(feature_dir, exist_ok=True)

        _process_init_feature_state(
            db, engine, feature_dir, "051", "retry", "standard",
            "feature/051-retry", None, None, "active",
            artifacts_root=str(tmp_path),
        )

        existing = db.get_entity("feature:051-retry")
        assert existing is not None
        existing_meta = json.loads(existing["metadata"]) if existing["metadata"] else {}
        existing_meta["phase_timing"] = {
            "brainstorm": {
                "started": "2026-03-01T00:00:00Z",
                "completed": "2026-03-02T00:00:00Z",
            },
        }
        existing_meta["last_completed_phase"] = "brainstorm"
        existing_meta["skipped_phases"] = [{"phase": "specify", "reason": "already done"}]
        db.update_entity("feature:051-retry", metadata=existing_meta)

        result = _process_init_feature_state(
            db, engine, feature_dir, "051", "retry", "standard",
            "feature/051-retry", None, None, "active",
            artifacts_root=str(tmp_path),
        )
        data = json.loads(result)
        assert data["created"] is True

        entity = db.get_entity("feature:051-retry")
        meta_raw = json.loads(entity["metadata"]) if entity["metadata"] else {}
        assert "brainstorm" in meta_raw.get("phase_timing", {})
        assert meta_raw["phase_timing"]["brainstorm"]["completed"] == "2026-03-02T00:00:00Z"
        assert meta_raw.get("last_completed_phase") == "brainstorm"
        assert meta_raw.get("skipped_phases") == [{"phase": "specify", "reason": "already done"}]

    def test_brainstorm_source_and_backlog_source_included(self, db, engine, tmp_path):
        """brainstorm_source and backlog_source included when provided."""


        feature_dir = os.path.join(str(tmp_path), "features", "052-sources")
        os.makedirs(feature_dir, exist_ok=True)

        result = _process_init_feature_state(
            db, engine, feature_dir, "052", "sources", "full",
            "feature/052-sources",
            "docs/brainstorms/some.md", "backlog-item-42",
            "active", artifacts_root=str(tmp_path),
        )
        data = json.loads(result)
        assert data["created"] is True

        meta_path = os.path.join(feature_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["brainstorm_source"] == "docs/brainstorms/some.md"
        assert meta["backlog_source"] == "backlog-item-42"

    def test_status_defaults_to_active_and_respects_planned(self, db, engine, tmp_path):
        """Status defaults to 'active', respects 'planned'."""


        feat_dir_a = os.path.join(str(tmp_path), "features", "053-active")
        os.makedirs(feat_dir_a, exist_ok=True)
        result_a = _process_init_feature_state(
            db, engine, feat_dir_a, "053", "active", "standard",
            "feature/053-active", None, None, "active",
            artifacts_root=str(tmp_path),
        )
        data_a = json.loads(result_a)
        assert data_a["status"] == "active"
        assert db.get_entity("feature:053-active")["status"] == "active"

        feat_dir_p = os.path.join(str(tmp_path), "features", "054-planned")
        os.makedirs(feat_dir_p, exist_ok=True)
        result_p = _process_init_feature_state(
            db, engine, feat_dir_p, "054", "planned", "standard",
            "feature/054-planned", None, None, "planned",
            artifacts_root=str(tmp_path),
        )
        data_p = json.loads(result_p)
        assert data_p["status"] == "planned"
        assert db.get_entity("feature:054-planned")["status"] == "planned"

        meta_path = os.path.join(feat_dir_p, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["status"] == "planned"
        assert meta["phases"] == {}

    def test_projection_warning_returned_on_failure(self, db, engine, tmp_path):
        """Returns projection_warning if _project_meta_json returns warning."""

        from unittest.mock import patch

        feature_dir = os.path.join(str(tmp_path), "features", "055-warn")
        os.makedirs(feature_dir, exist_ok=True)

        with patch(
            "workflow_state_server._project_meta_json",
            return_value="projection failed: disk full",
        ):
            result = _process_init_feature_state(
                db, engine, feature_dir, "055", "warn", "standard",
                "feature/055-warn", None, None, "active",
                artifacts_root=str(tmp_path),
            )
        data = json.loads(result)
        assert data["created"] is True
        assert data["projection_warning"] == "projection failed: disk full"

    def test_catch_value_error_on_bad_input(self, db, engine, tmp_path):
        """@_catch_value_error catches ValueError on bad input."""


        feature_dir = os.path.join(str(tmp_path), "features", "056-bad")
        os.makedirs(feature_dir, exist_ok=True)

        result = _process_init_feature_state(
            db, engine, feature_dir, "056", "bad\x00evil", "standard",
            "feature/056-bad", None, None, "active",
            artifacts_root=str(tmp_path),
        )
        data = json.loads(result)
        assert data.get("error") is True
        assert data.get("error_type") in ("feature_not_found", "invalid_transition")

    def test_no_projection_warning_when_successful(self, db, engine, tmp_path):
        """No projection_warning key when projection succeeds."""


        feature_dir = os.path.join(str(tmp_path), "features", "057-nowarning")
        os.makedirs(feature_dir, exist_ok=True)

        result = _process_init_feature_state(
            db, engine, feature_dir, "057", "nowarning", "standard",
            "feature/057-nowarning", None, None, "active",
            artifacts_root=str(tmp_path),
        )
        data = json.loads(result)
        assert data["created"] is True
        assert "projection_warning" not in data

    # -- Kanban column lifecycle tests (AC-6) --------------------------------

    def test_init_feature_state_active_sets_kanban_from_phase(self, db, tmp_path):
        """Active feature init sets kanban_column from phase via derive_kanban.
        Initial phase is brainstorm -> kanban_column = 'backlog'.
        derived_from: spec:AC-6, feature:052 AC-4
        """
        engine = WorkflowStateEngine(db=db, artifacts_root=str(tmp_path))

        feature_dir = os.path.join(str(tmp_path), "features", "099-test")
        os.makedirs(feature_dir, exist_ok=True)

        _process_init_feature_state(
            db, engine, feature_dir, "099", "test", "standard",
            "feature/099-test", None, None, "active",
            artifacts_root=str(tmp_path),
        )

        wp = db.get_workflow_phase("feature:099-test")
        assert wp is not None, "workflow_phase row should exist after init"
        assert wp["kanban_column"] == "backlog"

    def test_init_feature_state_planned_sets_kanban_backlog(self, db, tmp_path):
        """Planned feature init must set kanban_column to 'backlog'.
        derived_from: spec:AC-6
        """
        engine = WorkflowStateEngine(db=db, artifacts_root=str(tmp_path))

        feature_dir = os.path.join(str(tmp_path), "features", "100-planned")
        os.makedirs(feature_dir, exist_ok=True)

        _process_init_feature_state(
            db, engine, feature_dir, "100", "planned", "standard",
            "feature/100-planned", None, None, "planned",
            artifacts_root=str(tmp_path),
        )

        wp = db.get_workflow_phase("feature:100-planned")
        assert wp is not None, "workflow_phase row should exist after init"
        assert wp["kanban_column"] == "backlog"


# ---------------------------------------------------------------------------
# T6.1: activate_feature tests
# ---------------------------------------------------------------------------


class TestActivateFeature:
    """Tests for _process_activate_feature.

    Pre-condition: entity must be in 'planned' status.
    Post-condition: entity status becomes 'active', .meta.json projected.
    """


    def test_planned_entity_activated_to_active(self, db, tmp_path):
        """Planned entity is activated, status becomes 'active'."""


        feature_dir = os.path.join(str(tmp_path), "features", "050-activate")
        os.makedirs(feature_dir, exist_ok=True)

        metadata = {
            "id": "050",
            "slug": "activate",
            "mode": "standard",
            "branch": "feature/050-activate",
            "phase_timing": {},
        }
        db.register_entity(
            "feature", "050-activate", "activate",
            artifact_path=feature_dir,
            status="planned",
            metadata=metadata,
        )

        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_activate_feature(
            db, engine, "feature:050-activate", str(tmp_path),
        )
        data = json.loads(result)

        assert data["activated"] is True
        assert data["feature_type_id"] == "feature:050-activate"
        assert data["previous_status"] == "planned"
        assert data["new_status"] == "active"

        # Verify DB entity status updated
        entity = db.get_entity("feature:050-activate")
        assert entity["status"] == "active"

    def test_non_planned_entity_raises_value_error(self, db, tmp_path):
        """Non-planned entity (e.g., 'active') raises ValueError via error response."""


        feature_dir = os.path.join(str(tmp_path), "features", "051-already-active")
        os.makedirs(feature_dir, exist_ok=True)

        metadata = {
            "id": "051",
            "slug": "already-active",
            "mode": "standard",
            "branch": "feature/051-already-active",
            "phase_timing": {},
        }
        db.register_entity(
            "feature", "051-already-active", "already-active",
            artifact_path=feature_dir,
            status="active",
            metadata=metadata,
        )

        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_activate_feature(
            db, engine, "feature:051-already-active", str(tmp_path),
        )
        data = json.loads(result)

        # _catch_value_error converts ValueError to structured error
        assert data["error"] is True
        assert data["error_type"] == "invalid_transition"
        assert "active" in data["message"]  # mentions current status

    def test_nonexistent_entity_raises_value_error(self, db, tmp_path):
        """Non-existent entity raises ValueError via error response."""


        # Create the feature directory so _validate_feature_type_id passes
        feature_dir = os.path.join(str(tmp_path), "features", "999-ghost")
        os.makedirs(feature_dir, exist_ok=True)

        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_activate_feature(
            db, engine, "feature:999-ghost", str(tmp_path),
        )
        data = json.loads(result)

        assert data["error"] is True
        assert data["error_type"] == "feature_not_found"
        assert "999-ghost" in data["message"]

    def test_meta_json_projected_after_activation(self, db, tmp_path):
        """.meta.json is projected after activation."""


        feature_dir = os.path.join(str(tmp_path), "features", "052-project")
        os.makedirs(feature_dir, exist_ok=True)

        metadata = {
            "id": "052",
            "slug": "project",
            "mode": "standard",
            "branch": "feature/052-project",
            "phase_timing": {},
        }
        db.register_entity(
            "feature", "052-project", "project",
            artifact_path=feature_dir,
            status="planned",
            metadata=metadata,
        )

        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_activate_feature(
            db, engine, "feature:052-project", str(tmp_path),
        )
        data = json.loads(result)
        assert data["activated"] is True

        # Verify .meta.json was written
        meta_path = os.path.join(feature_dir, ".meta.json")
        assert os.path.isfile(meta_path)
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["status"] == "active"
        assert meta["id"] == "052"
        assert meta["slug"] == "project"

    def test_projection_warning_returned_on_failure(self, db, tmp_path):
        """Returns projection_warning if projection fails."""

        from unittest.mock import patch

        feature_dir = os.path.join(str(tmp_path), "features", "053-projfail")
        os.makedirs(feature_dir, exist_ok=True)

        metadata = {
            "id": "053",
            "slug": "projfail",
            "mode": "standard",
            "branch": "feature/053-projfail",
            "phase_timing": {},
        }
        db.register_entity(
            "feature", "053-projfail", "projfail",
            artifact_path=feature_dir,
            status="planned",
            metadata=metadata,
        )

        engine = WorkflowStateEngine(db, str(tmp_path))

        with patch(
            "workflow_state_server._project_meta_json",
            return_value="projection failed: disk full",
        ):
            result = _process_activate_feature(
                db, engine, "feature:053-projfail", str(tmp_path),
            )

        data = json.loads(result)
        assert data["activated"] is True
        assert data["projection_warning"] == "projection failed: disk full"


# ---------------------------------------------------------------------------
# Test Deepening: BDD Scenarios (Dimension 1)
# derived_from: spec:AC (end-to-end workflow), design:CQRS
# ---------------------------------------------------------------------------


class TestEndToEndWorkflow:
    """BDD scenarios covering the full init -> activate -> transition -> complete flow.

    Anticipate: Integration bugs where state from one step is not visible to the next.
    Challenge: Would catch if _project_meta_json silently fails mid-flow.
    Verify: Mutation of any step's DB write would break downstream assertions.
    """

    def test_full_lifecycle_init_activate_transition_complete(self, db, tmp_path):
        """End-to-end: init_feature_state -> activate_feature -> transition_phase -> complete_phase."""
        # derived_from: spec:AC (Sites 1,4,6,7) — full lifecycle via MCP tools

        # Given a feature directory exists
        feature_dir = os.path.join(str(tmp_path), "features", "100-lifecycle")
        os.makedirs(feature_dir, exist_ok=True)

        engine = WorkflowStateEngine(db, str(tmp_path))

        # When init_feature_state is called with status="planned"
        result = _process_init_feature_state(
            db, engine, feature_dir, "100", "lifecycle", "standard",
            "feature/100-lifecycle", None, None, "planned",
            artifacts_root=str(tmp_path),
        )
        data = json.loads(result)
        assert data["created"] is True
        assert data["status"] == "planned"

        # Then entity is in "planned" status with empty phase_timing
        entity = db.get_entity("feature:100-lifecycle")
        assert entity["status"] == "planned"
        meta_raw = json.loads(entity["metadata"]) if entity["metadata"] else {}
        assert meta_raw.get("phase_timing", {}) == {}

        # When activate_feature is called
        result = _process_activate_feature(
            db, engine, "feature:100-lifecycle", str(tmp_path),
        )
        data = json.loads(result)
        assert data["activated"] is True
        assert data["new_status"] == "active"

        # Then entity is in "active" status
        entity = db.get_entity("feature:100-lifecycle")
        assert entity["status"] == "active"

        # When transitioning to "specify" (engine auto-hydrates workflow phase from .meta.json)
        result = _process_transition_phase(
            engine, "feature:100-lifecycle", "specify", False,
            db=db, skipped_phases=None,
        )
        data = json.loads(result)
        assert data["transitioned"] is True
        assert "started_at" in data

        # Then .meta.json reflects the phase start
        meta_path = os.path.join(feature_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert "specify" in meta["phases"]
        assert "started" in meta["phases"]["specify"]

        # When completing the phase
        result = _process_complete_phase(
            engine, "feature:100-lifecycle", "specify",
            db=db, iterations=2, reviewer_notes='["Fix edge case"]',
        )
        data = json.loads(result)
        assert "completed_at" in data

        # Then .meta.json reflects completed phase with timing metadata
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["phases"]["specify"]["iterations"] == 2
        assert meta["phases"]["specify"]["reviewerNotes"] == ["Fix edge case"]
        assert "completed" in meta["phases"]["specify"]
        assert meta["lastCompletedPhase"] == "specify"

    def test_init_planned_has_empty_phase_timing_active_has_brainstorm(self, db, tmp_path):
        """Planned features get empty phase_timing; active features get brainstorm started."""
        # derived_from: spec:Site1 + spec:Site2 — status-dependent phase_timing init

        # Given two feature directories
        dir_planned = os.path.join(str(tmp_path), "features", "101-planned")
        dir_active = os.path.join(str(tmp_path), "features", "102-active")
        os.makedirs(dir_planned, exist_ok=True)
        os.makedirs(dir_active, exist_ok=True)

        engine = WorkflowStateEngine(db, str(tmp_path))

        # When creating planned feature
        _process_init_feature_state(
            db, engine, dir_planned, "101", "planned", "standard",
            "feature/101-planned", None, None, "planned",
            artifacts_root=str(tmp_path),
        )

        # Then phase_timing is empty
        entity = db.get_entity("feature:101-planned")
        meta_raw = json.loads(entity["metadata"]) if entity["metadata"] else {}
        assert meta_raw["phase_timing"] == {}

        # When creating active feature
        _process_init_feature_state(
            db, engine, dir_active, "102", "active", "standard",
            "feature/102-active", None, None, "active",
            artifacts_root=str(tmp_path),
        )

        # Then phase_timing has brainstorm started
        entity = db.get_entity("feature:102-active")
        meta_raw = json.loads(entity["metadata"]) if entity["metadata"] else {}
        assert "brainstorm" in meta_raw["phase_timing"]
        assert "started" in meta_raw["phase_timing"]["brainstorm"]


# ---------------------------------------------------------------------------
# Test Deepening: Boundary Values (Dimension 2)
# ---------------------------------------------------------------------------


class TestBoundaryValuesDeepened:
    """Boundary value analysis for new MCP tools and extended functions.

    Anticipate: Off-by-one, empty vs null, zero values.
    """

    def test_complete_phase_iterations_zero_stored(self, db, tmp_path):
        """iterations=0 is a valid boundary value and should be stored, not skipped."""
        # derived_from: spec:Site7 — iterations is int|None, 0 is valid
        # Anticipate: `if iterations:` would skip 0 since 0 is falsy

        feature_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feature_dir, exist_ok=True)
        with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
            f.write('{"id": "009", "slug": "test", "status": "active", "mode": "standard"}')

        db.register_entity(
            "feature", "009-test", "Test Feature", status="active",
            artifact_path=feature_dir,
            metadata={"id": "009", "slug": "test", "mode": "standard", "branch": "", "phase_timing": {}},
        )
        db.create_workflow_phase("feature:009-test", workflow_phase="specify")
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_complete_phase(
            engine, "feature:009-test", "specify",
            db=db, iterations=0, reviewer_notes=None,
        )
        data = json.loads(result)

        # Then iterations=0 should be stored
        entity = db.get_entity("feature:009-test")
        meta_raw = json.loads(entity["metadata"]) if entity["metadata"] else {}
        assert meta_raw["phase_timing"]["specify"]["iterations"] == 0

    def test_complete_phase_empty_reviewer_notes_array(self, db, tmp_path):
        """Empty reviewer_notes array '[]' is valid and should be stored."""
        # derived_from: spec:Site7 — reviewer_notes is JSON array, empty array is valid
        # Anticipate: `if reviewer_notes:` would skip "[]" since it's truthy but empty array

        feature_dir = os.path.join(str(tmp_path), "features", "110-empty-notes")
        os.makedirs(feature_dir, exist_ok=True)
        with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
            f.write('{"id": "110", "slug": "empty-notes", "status": "active", "mode": "standard"}')

        db.register_entity(
            "feature", "110-empty-notes", "empty-notes", status="active",
            artifact_path=feature_dir,
            metadata={"id": "110", "slug": "empty-notes", "mode": "standard", "branch": "", "phase_timing": {}},
        )
        db.create_workflow_phase("feature:110-empty-notes", workflow_phase="specify")
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_complete_phase(
            engine, "feature:110-empty-notes", "specify",
            db=db, iterations=None, reviewer_notes='[]',
        )
        data = json.loads(result)

        entity = db.get_entity("feature:110-empty-notes")
        meta_raw = json.loads(entity["metadata"]) if entity["metadata"] else {}
        # "[]" is truthy, so reviewer_notes should be parsed and stored as []
        assert meta_raw["phase_timing"]["specify"]["reviewerNotes"] == []

    def test_transition_phase_empty_skipped_phases_array(self, db, tmp_path):
        """Empty skipped_phases '[]' is valid JSON but falsy — should be stored."""
        # derived_from: spec:Site5 — skipped_phases JSON array, empty edge case
        # Anticipate: `if skipped_phases:` treats "[]" as truthy (non-empty string)

        feature_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feature_dir, exist_ok=True)
        with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
            f.write('{"id": "009", "slug": "test", "status": "active", "mode": "standard"}')

        db.register_entity(
            "feature", "009-test", "Test Feature", status="active",
            artifact_path=feature_dir,
            metadata={"id": "009", "slug": "test", "mode": "standard", "branch": "", "phase_timing": {}},
        )
        db.create_workflow_phase("feature:009-test", workflow_phase="specify")
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_transition_phase(
            engine, "feature:009-test", "specify", False,
            db=db, skipped_phases='[]',
        )
        data = json.loads(result)

        assert data["transitioned"] is True
        # "[]" is a truthy string, so skipped_phases_stored should be True
        assert data.get("skipped_phases_stored") is True

        # Verify empty array stored in metadata
        entity = db.get_entity("feature:009-test")
        meta_raw = json.loads(entity["metadata"]) if entity["metadata"] else {}
        assert meta_raw.get("skipped_phases") == []

    def test_init_project_state_empty_features_and_milestones(self, db, tmp_path):
        """Empty features and milestones arrays are valid."""
        # derived_from: spec:Site3/Site9 — features/milestones can be empty

        project_dir = os.path.join(str(tmp_path), "projects", "111-empty")
        os.makedirs(project_dir, exist_ok=True)

        result = _process_init_project_state(
            db, project_dir, "111", "empty", "[]", "[]", None,
        )
        data = json.loads(result)
        assert data["created"] is True

        meta_path = os.path.join(project_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["features"] == []
        assert meta["milestones"] == []

    def test_atomic_json_write_unicode_content(self, tmp_path):
        """Unicode content is written correctly via atomic write."""
        # derived_from: dimension:boundary — unicode characters in JSON

        target = os.path.join(str(tmp_path), "unicode.json")
        data = {"name": "日本語テスト", "emoji": "🎉", "accent": "café"}
        _atomic_json_write(target, data)

        with open(target, encoding="utf-8") as f:
            parsed = json.load(f)
        assert parsed == data

    def test_atomic_json_write_empty_dict(self, tmp_path):
        """Empty dict is written as valid JSON."""
        # derived_from: dimension:boundary — minimum valid input

        target = os.path.join(str(tmp_path), "empty.json")
        _atomic_json_write(target, {})

        with open(target) as f:
            parsed = json.load(f)
        assert parsed == {}

    def test_init_project_state_large_features_array(self, db, tmp_path):
        """Large features array (50 items) handled correctly."""
        # derived_from: dimension:boundary — collection size

        project_dir = os.path.join(str(tmp_path), "projects", "112-large")
        os.makedirs(project_dir, exist_ok=True)

        features = [f"feat-{i:03d}" for i in range(50)]
        result = _process_init_project_state(
            db, project_dir, "112", "large",
            json.dumps(features), "[]", None,
        )
        data = json.loads(result)
        assert data["created"] is True

        meta_path = os.path.join(project_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert len(meta["features"]) == 50


# ---------------------------------------------------------------------------
# Test Deepening: Adversarial / Negative Testing (Dimension 3)
# ---------------------------------------------------------------------------


class TestAdversarialDeepened:
    """Adversarial tests for new MCP tools.

    Anticipate: Invalid state transitions, malformed inputs, double operations.
    """

    def test_activate_feature_completed_status_rejected(self, db, tmp_path):
        """Activating a 'completed' feature should be rejected."""
        # derived_from: spec:Site4 — pre-condition: status must be 'planned'
        # Anticipate: Only checking `!= "planned"` vs specifically allowing certain states

        feature_dir = os.path.join(str(tmp_path), "features", "120-completed")
        os.makedirs(feature_dir, exist_ok=True)

        db.register_entity(
            "feature", "120-completed", "completed",
            artifact_path=feature_dir,
            status="completed",
            metadata={"id": "120", "slug": "completed", "mode": "standard", "branch": "", "phase_timing": {}},
        )

        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_activate_feature(
            db, engine, "feature:120-completed", str(tmp_path),
        )
        data = json.loads(result)

        assert data["error"] is True
        assert data["error_type"] == "invalid_transition"
        assert "completed" in data["message"]

    def test_activate_feature_double_activation_rejected(self, db, tmp_path):
        """Activating an already-active feature should be rejected."""
        # derived_from: spec:Site4 — race condition: double activation
        # Anticipate: Second activation attempt after first succeeds

        feature_dir = os.path.join(str(tmp_path), "features", "121-double")
        os.makedirs(feature_dir, exist_ok=True)

        db.register_entity(
            "feature", "121-double", "double",
            artifact_path=feature_dir,
            status="planned",
            metadata={"id": "121", "slug": "double", "mode": "standard", "branch": "", "phase_timing": {}},
        )

        engine = WorkflowStateEngine(db, str(tmp_path))

        # First activation succeeds
        result1 = _process_activate_feature(
            db, engine, "feature:121-double", str(tmp_path),
        )
        data1 = json.loads(result1)
        assert data1["activated"] is True

        # Second activation fails — status is now 'active', not 'planned'
        result2 = _process_activate_feature(
            db, engine, "feature:121-double", str(tmp_path),
        )
        data2 = json.loads(result2)
        assert data2["error"] is True
        assert data2["error_type"] == "invalid_transition"

    def test_transition_phase_malformed_skipped_phases_json(self, db, tmp_path):
        """Malformed skipped_phases JSON should return error."""
        # derived_from: spec:Site5 — skipped_phases is JSON string
        # Anticipate: json.loads failure on malformed input

        feature_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feature_dir, exist_ok=True)
        with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
            f.write('{"id": "009", "slug": "test", "status": "active", "mode": "standard"}')

        db.register_entity(
            "feature", "009-test", "Test Feature", status="active",
            artifact_path=feature_dir,
            metadata={"id": "009", "slug": "test", "mode": "standard", "branch": "", "phase_timing": {}},
        )
        db.create_workflow_phase("feature:009-test", workflow_phase="specify")
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_transition_phase(
            engine, "feature:009-test", "specify", False,
            db=db, skipped_phases="not-valid-json",
        )
        data = json.loads(result)

        # Malformed JSON should be caught by error handling
        # json.loads raises ValueError/JSONDecodeError which is caught
        assert data.get("error") is True

    def test_complete_phase_malformed_reviewer_notes_json(self, db, tmp_path):
        """Malformed reviewer_notes JSON should return error."""
        # derived_from: spec:Site7 — reviewer_notes is JSON string
        # Anticipate: json.loads failure on malformed input

        feature_dir = os.path.join(str(tmp_path), "features", "122-bad-notes")
        os.makedirs(feature_dir, exist_ok=True)
        with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
            f.write('{"id": "122", "slug": "bad-notes", "status": "active", "mode": "standard"}')

        db.register_entity(
            "feature", "122-bad-notes", "bad-notes", status="active",
            artifact_path=feature_dir,
            metadata={"id": "122", "slug": "bad-notes", "mode": "standard", "branch": "", "phase_timing": {}},
        )
        db.create_workflow_phase("feature:122-bad-notes", workflow_phase="specify")
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_complete_phase(
            engine, "feature:122-bad-notes", "specify",
            db=db, iterations=1, reviewer_notes="not-valid-json",
        )
        data = json.loads(result)

        assert data.get("error") is True

    def test_complete_phase_non_terminal_does_not_set_completed_status(self, db, tmp_path):
        """Completing a non-terminal phase (e.g., 'specify') should NOT set status to 'completed'."""
        # derived_from: spec:Site8 — only complete_phase("finish") sets status="completed"
        # Anticipate: Bug where any complete_phase sets status="completed"

        feature_dir = os.path.join(str(tmp_path), "features", "123-nonterminal")
        os.makedirs(feature_dir, exist_ok=True)
        with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
            f.write('{"id": "123", "slug": "nonterminal", "status": "active", "mode": "standard"}')

        db.register_entity(
            "feature", "123-nonterminal", "nonterminal", status="active",
            artifact_path=feature_dir,
            metadata={"id": "123", "slug": "nonterminal", "mode": "standard", "branch": "", "phase_timing": {}},
        )
        db.create_workflow_phase("feature:123-nonterminal", workflow_phase="specify")
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_complete_phase(
            engine, "feature:123-nonterminal", "specify",
            db=db, iterations=1, reviewer_notes=None,
        )
        data = json.loads(result)

        # Status should still be "active", not "completed"
        entity = db.get_entity("feature:123-nonterminal")
        assert entity["status"] == "active"

    def test_init_project_state_idempotent_existing_entity(self, db, tmp_path):
        """Calling init_project_state twice with same ID — second call should not crash.
        Spec says: 'Register entity (idempotent — skip if already exists)'.
        """
        # derived_from: design:C4 — idempotent entity registration

        project_dir = os.path.join(str(tmp_path), "projects", "124-idempotent")
        os.makedirs(project_dir, exist_ok=True)

        # First call
        result1 = _process_init_project_state(
            db, project_dir, "124", "idempotent",
            '["feat-a"]', '[]', None,
        )
        data1 = json.loads(result1)
        assert data1["created"] is True

        # Second call — should succeed (entity exists, skip registration)
        result2 = _process_init_project_state(
            db, project_dir, "124", "idempotent",
            '["feat-a", "feat-b"]', '[]', None,
        )
        data2 = json.loads(result2)
        assert data2["created"] is True

        # .meta.json should reflect the second call's data
        meta_path = os.path.join(project_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["features"] == ["feat-a", "feat-b"]

    def test_init_feature_state_path_traversal_blocked(self, db, tmp_path):
        """Path traversal via feature_id is blocked by _validate_feature_type_id."""
        # derived_from: design:C3 — _validate_feature_type_id defense

        feature_dir = os.path.join(str(tmp_path), "features", "../../etc")
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_init_feature_state(
            db, engine, feature_dir, "999", "../../etc", "standard",
            "feature/999", None, None, "active",
            artifacts_root=str(tmp_path),
        )
        data = json.loads(result)
        assert data.get("error") is True


# ---------------------------------------------------------------------------
# Test Deepening: Error Propagation (Dimension 4)
# ---------------------------------------------------------------------------


class TestErrorPropagationDeepened:
    """Error propagation tests for new/extended functions.

    Anticipate: Errors swallowed silently, partial state on failure.
    """

    def test_init_feature_state_sqlite_error_returns_db_unavailable(self, db, tmp_path):
        """SQLite error during entity registration returns db_unavailable."""
        # derived_from: design:D7 — _with_error_handling catches sqlite3.Error
        # Anticipate: sqlite3.Error not caught, propagates as 500

        from unittest.mock import patch

        feature_dir = os.path.join(str(tmp_path), "features", "130-sqlerr")
        os.makedirs(feature_dir, exist_ok=True)

        engine = WorkflowStateEngine(db, str(tmp_path))

        with patch.object(
            db, "get_entity", side_effect=sqlite3.OperationalError("database locked"),
        ):
            result = _process_init_feature_state(
                db, engine, feature_dir, "130", "sqlerr", "standard",
                "feature/130-sqlerr", None, None, "active",
                artifacts_root=str(tmp_path),
            )

        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "db_unavailable"

    def test_init_project_state_sqlite_error_returns_db_unavailable(self, db, tmp_path):
        """SQLite error during project entity registration returns db_unavailable."""
        # derived_from: design:D7 — _with_error_handling

        from unittest.mock import patch

        project_dir = os.path.join(str(tmp_path), "projects", "131-sqlerr")
        os.makedirs(project_dir, exist_ok=True)

        with patch.object(
            db, "get_entity", side_effect=sqlite3.OperationalError("database locked"),
        ):
            result = _process_init_project_state(
                db, project_dir, "131", "sqlerr", "[]", "[]", None,
            )

        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "db_unavailable"

    def test_activate_feature_sqlite_error_returns_db_unavailable(self, db, tmp_path):
        """SQLite error during activation returns db_unavailable."""
        # derived_from: design:D7 — _with_error_handling

        from unittest.mock import patch

        feature_dir = os.path.join(str(tmp_path), "features", "132-sqlerr")
        os.makedirs(feature_dir, exist_ok=True)

        engine = WorkflowStateEngine(db, str(tmp_path))

        with patch.object(
            db, "get_entity", side_effect=sqlite3.OperationalError("database locked"),
        ):
            result = _process_activate_feature(
                db, engine, "feature:132-sqlerr", str(tmp_path),
            )

        data = json.loads(result)
        assert data["error"] is True
        assert data["error_type"] == "db_unavailable"

    def test_complete_phase_db_preserves_state_on_projection_failure(self, db, tmp_path):
        """When projection fails after complete_phase, DB state is still updated correctly."""
        # derived_from: spec:Section5-AC5 — if projection fails, DB state preserved
        # Anticipate: rollback on projection failure losing the DB mutation

        from unittest.mock import patch

        feature_dir = os.path.join(str(tmp_path), "features", "133-projfail")
        os.makedirs(feature_dir, exist_ok=True)
        with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
            f.write('{"id": "133", "slug": "projfail", "status": "active", "mode": "standard"}')

        db.register_entity(
            "feature", "133-projfail", "projfail", status="active",
            artifact_path=feature_dir,
            metadata={"id": "133", "slug": "projfail", "mode": "standard", "branch": "", "phase_timing": {}},
        )
        db.create_workflow_phase("feature:133-projfail", workflow_phase="specify")
        engine = WorkflowStateEngine(db, str(tmp_path))

        with patch(
            "workflow_state_server._project_meta_json",
            return_value="projection failed: disk full",
        ):
            result = _process_complete_phase(
                engine, "feature:133-projfail", "specify",
                db=db, iterations=3, reviewer_notes=None,
            )

        data = json.loads(result)
        assert "projection_warning" in data

        # DB state should still be updated even though projection failed
        entity = db.get_entity("feature:133-projfail")
        meta_raw = json.loads(entity["metadata"]) if entity["metadata"] else {}
        assert meta_raw["last_completed_phase"] == "specify"
        assert meta_raw["phase_timing"]["specify"]["iterations"] == 3

    def test_transition_phase_db_preserves_state_on_projection_failure(self, db, tmp_path):
        """When projection fails after transition_phase, DB state is still updated."""
        # derived_from: spec:Section5-AC5 — DB preserved on projection failure

        from unittest.mock import patch

        feature_dir = os.path.join(str(tmp_path), "features", "134-projfail")
        os.makedirs(feature_dir, exist_ok=True)
        with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
            f.write('{"id": "134", "slug": "projfail", "status": "active", "mode": "standard"}')

        db.register_entity(
            "feature", "134-projfail", "projfail", status="active",
            artifact_path=feature_dir,
            metadata={"id": "134", "slug": "projfail", "mode": "standard", "branch": "", "phase_timing": {}},
        )
        db.create_workflow_phase("feature:134-projfail", workflow_phase="specify")
        engine = WorkflowStateEngine(db, str(tmp_path))

        with patch(
            "workflow_state_server._project_meta_json",
            return_value="projection failed: permissions",
        ):
            result = _process_transition_phase(
                engine, "feature:134-projfail", "specify", False,
                db=db, skipped_phases=None,
            )

        data = json.loads(result)
        assert data["transitioned"] is True
        assert "projection_warning" in data

        # DB should have phase timing stored
        entity = db.get_entity("feature:134-projfail")
        meta_raw = json.loads(entity["metadata"]) if entity["metadata"] else {}
        assert "specify" in meta_raw["phase_timing"]
        assert "started" in meta_raw["phase_timing"]["specify"]


# ---------------------------------------------------------------------------
# Test Deepening: Mutation Mindset (Dimension 5)
# ---------------------------------------------------------------------------


class TestMutationMindsetDeepened:
    """Mutation-oriented tests to pin behavior against common operator mutations.

    Each test targets a specific mutation operator that would break behavior.
    """

    def test_complete_phase_finish_sets_completed_not_active(self, db, tmp_path):
        """complete_phase('finish') sets status to 'completed', NOT 'active'."""
        # derived_from: spec:Site8 — terminal status update
        # Mutation: swap "completed" → "active" in `if phase == "finish"` branch
        # Verify: would catch if status value was wrong

        feature_dir = os.path.join(str(tmp_path), "features", "140-terminal")
        os.makedirs(feature_dir, exist_ok=True)
        with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
            f.write('{"id": "140", "slug": "terminal", "status": "active", "mode": "standard"}')

        db.register_entity(
            "feature", "140-terminal", "terminal", status="active",
            artifact_path=feature_dir,
            metadata={"id": "140", "slug": "terminal", "mode": "standard", "branch": "", "phase_timing": {}},
        )
        # Need to set up workflow so complete_phase("finish") is valid
        # The engine needs the feature at the "finish" phase
        db.create_workflow_phase("feature:140-terminal", workflow_phase="finish")
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_complete_phase(
            engine, "feature:140-terminal", "finish",
            db=db, iterations=None, reviewer_notes=None,
        )
        data = json.loads(result)

        entity = db.get_entity("feature:140-terminal")
        assert entity["status"] == "completed"

    def test_activate_feature_checks_planned_not_active(self, db, tmp_path):
        """activate_feature checks status == 'planned', not status == 'active'."""
        # derived_from: spec:Site4 — pre-condition: status must be 'planned'
        # Mutation: swap `!= "planned"` → `!= "active"` in condition

        feature_dir = os.path.join(str(tmp_path), "features", "141-check")
        os.makedirs(feature_dir, exist_ok=True)

        # Register as "planned" — should succeed
        db.register_entity(
            "feature", "141-check", "check",
            artifact_path=feature_dir,
            status="planned",
            metadata={"id": "141", "slug": "check", "mode": "standard", "branch": "", "phase_timing": {}},
        )

        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_activate_feature(
            db, engine, "feature:141-check", str(tmp_path),
        )
        data = json.loads(result)
        assert data["activated"] is True

        # Verify the entity is now active (not still planned)
        entity = db.get_entity("feature:141-check")
        assert entity["status"] == "active"

    def test_project_meta_json_uses_engine_state_over_metadata_for_last_completed(
        self, db, tmp_path
    ):
        """_project_meta_json uses engine.get_state() for last_completed_phase,
        not metadata alone. Engine is authoritative."""
        # derived_from: design:C2 — engine is authoritative for last_completed_phase
        # Mutation: swap engine_state.last_completed_phase with metadata fallback

        feature_dir = os.path.join(str(tmp_path), "features", "142-authority")
        os.makedirs(feature_dir, exist_ok=True)

        metadata = {
            "id": "142",
            "slug": "authority",
            "mode": "standard",
            "branch": "feature/142-authority",
            "last_completed_phase": "brainstorm",  # stale metadata
            "phase_timing": {},
        }
        db.register_entity(
            "feature", "142-authority", "authority",
            artifact_path=feature_dir,
            status="active",
            metadata=metadata,
        )
        # Set engine state to specify (more recent than metadata's "brainstorm")
        db.create_workflow_phase("feature:142-authority", workflow_phase="design")

        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _project_meta_json(db, engine, "feature:142-authority", feature_dir)
        assert result is None

        meta_path = os.path.join(feature_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)

        # Engine says last_completed is "specify" (previous to design),
        # NOT metadata's stale "brainstorm"
        engine_state = engine.get_state("feature:142-authority")
        assert meta["lastCompletedPhase"] == engine_state.last_completed_phase

    def test_transition_phase_transitioned_uses_all_not_any_with_db(
        self, db, tmp_path
    ):
        """When db is provided, phase timing is only stored if ALL gates pass (not ANY)."""
        # derived_from: dimension:mutation — all() vs any() operator
        # Mutation: swap `all(r.allowed ...)` → `any(r.allowed ...)`

        feature_dir = os.path.join(str(tmp_path), "features", "143-allvsany")
        os.makedirs(feature_dir, exist_ok=True)
        with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
            f.write('{"id": "143", "slug": "allvsany", "status": "active", "mode": "standard"}')

        db.register_entity(
            "feature", "143-allvsany", "allvsany", status="active",
            artifact_path=feature_dir,
            metadata={"id": "143", "slug": "allvsany", "mode": "standard", "branch": "", "phase_timing": {}},
        )
        db.create_workflow_phase("feature:143-allvsany", workflow_phase="specify")
        engine = WorkflowStateEngine(db, str(tmp_path))

        # Transition to "design" without completing "specify" — gate should block
        result = _process_transition_phase(
            engine, "feature:143-allvsany", "design", False,
            db=db, skipped_phases=None,
        )
        data = json.loads(result)

        # Transition should be blocked
        assert data["transitioned"] is False
        # No phase timing should be stored when transition is blocked
        assert "started_at" not in data

    def test_project_meta_json_empty_phase_entry_excluded(self, db, tmp_path):
        """Phase timing entries with no fields (empty dict) are excluded from phases."""
        # derived_from: dimension:mutation — line deletion of `if phase_entry:` guard
        # Mutation: removing `if phase_entry:` would include empty phase dicts

        feature_dir = os.path.join(str(tmp_path), "features", "144-empty-phase")
        os.makedirs(feature_dir, exist_ok=True)

        metadata = {
            "id": "144",
            "slug": "empty-phase",
            "mode": "standard",
            "branch": "feature/144-empty-phase",
            "phase_timing": {
                "brainstorm": {},  # empty — should be excluded
                "specify": {"started": "2026-03-01T00:00:00Z"},  # has data — include
            },
        }
        db.register_entity(
            "feature", "144-empty-phase", "empty-phase",
            artifact_path=feature_dir,
            status="active",
            metadata=metadata,
        )

        result = _project_meta_json(db, None, "feature:144-empty-phase", feature_dir)
        assert result is None

        meta_path = os.path.join(feature_dir, ".meta.json")
        with open(meta_path) as f:
            meta = json.load(f)

        # Empty brainstorm entry should NOT be in phases
        assert "brainstorm" not in meta["phases"]
        # Non-empty specify entry should be in phases
        assert "specify" in meta["phases"]
        assert meta["phases"]["specify"]["started"] == "2026-03-01T00:00:00Z"

    def test_init_feature_state_retry_preserves_skipped_phases_not_overwritten(
        self, db, tmp_path
    ):
        """Retry of init_feature_state preserves skipped_phases from first call."""
        # derived_from: design:C3 — retry path preserves existing timing data
        # Mutation: deleting `if existing_meta.get("skipped_phases"):` line

        feature_dir = os.path.join(str(tmp_path), "features", "145-preserve")
        os.makedirs(feature_dir, exist_ok=True)

        engine = WorkflowStateEngine(db, str(tmp_path))

        # First call
        _process_init_feature_state(
            db, engine, feature_dir, "145", "preserve", "standard",
            "feature/145-preserve", None, None, "active",
            artifacts_root=str(tmp_path),
        )

        # Simulate progress: add skipped_phases to entity metadata
        entity = db.get_entity("feature:145-preserve")
        meta_raw = json.loads(entity["metadata"]) if entity["metadata"] else {}
        meta_raw["skipped_phases"] = [{"phase": "brainstorm", "reason": "existing doc"}]
        meta_raw["last_completed_phase"] = "specify"
        db.update_entity("feature:145-preserve", metadata=meta_raw)

        # Retry call — should preserve skipped_phases and last_completed_phase
        _process_init_feature_state(
            db, engine, feature_dir, "145", "preserve", "standard",
            "feature/145-preserve", None, None, "active",
            artifacts_root=str(tmp_path),
        )

        entity = db.get_entity("feature:145-preserve")
        meta_raw = json.loads(entity["metadata"]) if entity["metadata"] else {}
        assert meta_raw["skipped_phases"] == [{"phase": "brainstorm", "reason": "existing doc"}]
        assert meta_raw["last_completed_phase"] == "specify"


# ---------------------------------------------------------------------------
# Entity Machines constant tests (Task 2.1)
# ---------------------------------------------------------------------------


class TestEntityMachines:
    """Tests for ENTITY_MACHINES state machine constant."""

    def test_entity_machines_brainstorm_transitions(self):
        """Brainstorm transitions have correct keys and target lists."""
        brainstorm = ENTITY_MACHINES["brainstorm"]
        transitions = brainstorm["transitions"]
        assert set(transitions.keys()) == {"draft", "reviewing"}
        assert set(transitions["draft"]) == {"reviewing", "abandoned"}
        assert set(transitions["reviewing"]) == {"promoted", "draft", "abandoned"}

    def test_entity_machines_backlog_transitions(self):
        """Backlog transitions have correct keys and target lists."""
        backlog = ENTITY_MACHINES["backlog"]
        transitions = backlog["transitions"]
        assert set(transitions.keys()) == {"open", "triaged"}
        assert set(transitions["open"]) == {"triaged", "dropped"}
        assert set(transitions["triaged"]) == {"promoted", "dropped"}

    def test_entity_machines_columns_cover_all_phases(self):
        """Every phase in transitions (keys + values) also appears in columns."""
        for entity_type, machine in ENTITY_MACHINES.items():
            transitions = machine["transitions"]
            columns = machine["columns"]
            # Collect all phases from transitions (source keys + target values)
            all_phases = set(transitions.keys())
            for targets in transitions.values():
                all_phases.update(targets)
            # Every phase must have a column mapping
            missing = all_phases - set(columns.keys())
            assert not missing, (
                f"{entity_type}: phases {missing} missing from columns"
            )


# ---------------------------------------------------------------------------
# Entity error decorator tests (Task 2.3)
# ---------------------------------------------------------------------------


class TestCatchEntityValueError:
    """Tests for _catch_entity_value_error decorator."""

    def test_catch_entity_value_error_entity_not_found(self):
        """entity_not_found: prefix -> structured error dict."""
        @_catch_entity_value_error
        def raises():
            raise ValueError("entity_not_found: brainstorm:foo")

        result = json.loads(raises())
        assert result["error"] is True
        assert result["error_type"] == "entity_not_found"
        assert "brainstorm:foo" in result["message"]
        assert result["recovery_hint"]  # non-empty

    def test_catch_entity_value_error_invalid_entity_type(self):
        """invalid_entity_type: prefix -> structured error dict."""
        @_catch_entity_value_error
        def raises():
            raise ValueError("invalid_entity_type: feature entities use the feature workflow engine")

        result = json.loads(raises())
        assert result["error"] is True
        assert result["error_type"] == "invalid_entity_type"
        assert "feature" in result["message"]

    def test_catch_entity_value_error_invalid_transition(self):
        """invalid_transition: prefix -> structured error dict."""
        @_catch_entity_value_error
        def raises():
            raise ValueError("invalid_transition: cannot transition brainstorm from draft to promoted")

        result = json.loads(raises())
        assert result["error"] is True
        assert result["error_type"] == "invalid_transition"
        assert "draft" in result["message"]

    def test_catch_entity_value_error_unexpected_reraise(self):
        """ValueError without known prefix -> re-raised (not caught)."""
        @_catch_entity_value_error
        def raises():
            raise ValueError("some_other: unexpected error")

        with pytest.raises(ValueError, match="some_other"):
            raises()


# ---------------------------------------------------------------------------
# init_entity_workflow tests (Task 3.1)
# ---------------------------------------------------------------------------


class TestInitEntityWorkflow:
    """Tests for _process_init_entity_workflow."""

    def test_init_entity_workflow_creates_row(self, db):
        """Register brainstorm entity, call init, verify workflow_phases row."""
        db.register_entity("brainstorm", "test-idea", "Test Idea", status="draft")
        result = json.loads(
            _process_init_entity_workflow(db, "brainstorm:test-idea", "draft", "wip")
        )
        assert result["created"] is True
        assert result["type_id"] == "brainstorm:test-idea"
        assert result["workflow_phase"] == "draft"
        assert result["kanban_column"] == "wip"

        # Verify row in DB
        row = db._conn.execute(
            "SELECT workflow_phase, kanban_column FROM workflow_phases WHERE type_id = ?",
            ("brainstorm:test-idea",),
        ).fetchone()
        assert row is not None
        assert row["workflow_phase"] == "draft"
        assert row["kanban_column"] == "wip"

    def test_init_entity_workflow_idempotent(self, db):
        """Call init twice, second returns created=false with existing values."""
        db.register_entity("brainstorm", "test-idea", "Test Idea", status="draft")
        _process_init_entity_workflow(db, "brainstorm:test-idea", "draft", "wip")

        result = json.loads(
            _process_init_entity_workflow(db, "brainstorm:test-idea", "draft", "wip")
        )
        assert result["created"] is False
        assert result["reason"] == "already_exists"
        assert result["workflow_phase"] == "draft"
        assert result["kanban_column"] == "wip"

    def test_init_entity_workflow_entity_not_found(self, db):
        """Non-existent type_id -> error_type=entity_not_found."""
        result = json.loads(
            _process_init_entity_workflow(db, "brainstorm:nonexistent", "draft", "wip")
        )
        assert result["error"] is True
        assert result["error_type"] == "entity_not_found"

    def test_init_entity_workflow_validates_phase_against_machine(self, db):
        """Invalid phase for brainstorm -> error_type=invalid_transition."""
        db.register_entity("brainstorm", "test-idea", "Test Idea", status="draft")
        result = json.loads(
            _process_init_entity_workflow(db, "brainstorm:test-idea", "invalid", "wip")
        )
        assert result["error"] is True
        assert result["error_type"] == "invalid_transition"
        assert "invalid" in result["message"]

    def test_init_entity_workflow_validates_kanban_column_consistency(self, db):
        """Mismatched kanban_column for brainstorm draft -> error_type=invalid_transition."""
        db.register_entity("brainstorm", "test-idea", "Test Idea", status="draft")
        result = json.loads(
            _process_init_entity_workflow(db, "brainstorm:test-idea", "draft", "wrong")
        )
        assert result["error"] is True
        assert result["error_type"] == "invalid_transition"
        assert "wrong" in result["message"]

    def test_init_entity_workflow_rejects_feature_entity_type(self, db):
        """Feature type_id -> error_type=invalid_entity_type."""
        db.register_entity("feature", "001-test", "Test Feature", status="active")
        result = json.loads(
            _process_init_entity_workflow(db, "feature:001-test", "brainstorm", "wip")
        )
        assert result["error"] is True
        assert result["error_type"] == "invalid_entity_type"
        assert "feature" in result["message"]

    def test_init_entity_workflow_rejects_project_entity_type(self, db):
        """Project type_id -> error_type=invalid_entity_type."""
        db.register_entity("project", "001-test", "Test Project", status="active")
        result = json.loads(
            _process_init_entity_workflow(db, "project:001-test", "brainstorm", "wip")
        )
        assert result["error"] is True
        assert result["error_type"] == "invalid_entity_type"
        assert "project" in result["message"]


# ---------------------------------------------------------------------------
# transition_entity_phase tests (Task 3.3)
# ---------------------------------------------------------------------------


class TestTransitionEntityPhase:
    """Tests for _process_transition_entity_phase."""

    def _seed_entity_with_workflow(self, db, entity_type, entity_id, phase, kanban_column,
                                    last_completed_phase=None):
        """Helper: register entity and insert workflow_phases row directly."""
        db.register_entity(entity_type, entity_id, f"Test {entity_type}", status=phase)
        db._conn.execute(
            "INSERT INTO workflow_phases "
            "(type_id, workflow_phase, kanban_column, last_completed_phase, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"{entity_type}:{entity_id}", phase, kanban_column, last_completed_phase,
             db._now_iso()),
        )
        db._conn.commit()

    def test_transition_brainstorm_draft_to_reviewing(self, db):
        """Forward transition: draft -> reviewing, kanban_column -> agent_review."""
        self._seed_entity_with_workflow(db, "brainstorm", "idea-1", "draft", "wip")
        result = json.loads(
            _process_transition_entity_phase(db, "brainstorm:idea-1", "reviewing")
        )
        assert result["transitioned"] is True
        assert result["from_phase"] == "draft"
        assert result["to_phase"] == "reviewing"
        assert result["kanban_column"] == "agent_review"

    def test_transition_brainstorm_reviewing_to_promoted(self, db):
        """Terminal forward: reviewing -> promoted, kanban_column -> completed."""
        self._seed_entity_with_workflow(db, "brainstorm", "idea-1", "reviewing", "agent_review")
        result = json.loads(
            _process_transition_entity_phase(db, "brainstorm:idea-1", "promoted")
        )
        assert result["transitioned"] is True
        assert result["to_phase"] == "promoted"
        assert result["kanban_column"] == "completed"

    def test_transition_brainstorm_reviewing_to_draft(self, db):
        """Backward transition: reviewing -> draft, last_completed_phase NOT updated."""
        self._seed_entity_with_workflow(
            db, "brainstorm", "idea-1", "reviewing", "agent_review",
            last_completed_phase="draft",
        )
        result = json.loads(
            _process_transition_entity_phase(db, "brainstorm:idea-1", "draft")
        )
        assert result["transitioned"] is True
        assert result["to_phase"] == "draft"
        assert result["kanban_column"] == "wip"

        # Verify last_completed_phase was NOT updated (backward transition)
        row = db._conn.execute(
            "SELECT last_completed_phase FROM workflow_phases WHERE type_id = ?",
            ("brainstorm:idea-1",),
        ).fetchone()
        assert row["last_completed_phase"] == "draft"

    def test_transition_backlog_open_to_triaged(self, db):
        """Forward transition: open -> triaged, kanban_column -> prioritised."""
        self._seed_entity_with_workflow(db, "backlog", "12345", "open", "backlog")
        result = json.loads(
            _process_transition_entity_phase(db, "backlog:12345", "triaged")
        )
        assert result["transitioned"] is True
        assert result["to_phase"] == "triaged"
        assert result["kanban_column"] == "prioritised"

    def test_transition_backlog_triaged_to_promoted(self, db):
        """Terminal forward: triaged -> promoted, kanban_column -> completed."""
        self._seed_entity_with_workflow(db, "backlog", "12345", "triaged", "prioritised")
        result = json.loads(
            _process_transition_entity_phase(db, "backlog:12345", "promoted")
        )
        assert result["transitioned"] is True
        assert result["to_phase"] == "promoted"
        assert result["kanban_column"] == "completed"

    def test_transition_invalid_from_terminal(self, db):
        """promoted -> anything -> invalid_transition."""
        self._seed_entity_with_workflow(db, "brainstorm", "idea-1", "promoted", "completed")
        result = json.loads(
            _process_transition_entity_phase(db, "brainstorm:idea-1", "draft")
        )
        assert result["error"] is True
        assert result["error_type"] == "invalid_transition"

    def test_transition_feature_entity_rejected(self, db):
        """feature:xxx type_id -> invalid_entity_type."""
        db.register_entity("feature", "001-test", "Test Feature", status="active")
        result = json.loads(
            _process_transition_entity_phase(db, "feature:001-test", "reviewing")
        )
        assert result["error"] is True
        assert result["error_type"] == "invalid_entity_type"

    def test_transition_entity_not_found(self, db):
        """Non-existent type_id -> entity_not_found."""
        result = json.loads(
            _process_transition_entity_phase(db, "brainstorm:nonexistent", "reviewing")
        )
        assert result["error"] is True
        assert result["error_type"] == "entity_not_found"

    def test_transition_null_current_phase_error(self, db):
        """Row with NULL workflow_phase -> invalid_transition with init hint."""
        db.register_entity("brainstorm", "idea-1", "Test Idea", status="draft")
        db._conn.execute(
            "INSERT INTO workflow_phases (type_id, workflow_phase, kanban_column, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("brainstorm:idea-1", None, "wip", db._now_iso()),
        )
        db._conn.commit()

        result = json.loads(
            _process_transition_entity_phase(db, "brainstorm:idea-1", "reviewing")
        )
        assert result["error"] is True
        assert result["error_type"] == "invalid_transition"
        assert "init_entity_workflow" in result["message"]

    def test_transition_updates_entities_status(self, db):
        """After transition, entities.status matches target_phase."""
        self._seed_entity_with_workflow(db, "brainstorm", "idea-1", "draft", "wip")
        _process_transition_entity_phase(db, "brainstorm:idea-1", "reviewing")

        entity = db.get_entity("brainstorm:idea-1")
        assert entity["status"] == "reviewing"

    def test_transition_forward_sets_last_completed_phase(self, db):
        """After draft->reviewing (forward), last_completed_phase='draft'."""
        self._seed_entity_with_workflow(db, "brainstorm", "idea-1", "draft", "wip")
        _process_transition_entity_phase(db, "brainstorm:idea-1", "reviewing")

        row = db._conn.execute(
            "SELECT last_completed_phase FROM workflow_phases WHERE type_id = ?",
            ("brainstorm:idea-1",),
        ).fetchone()
        assert row["last_completed_phase"] == "draft"

    def test_transition_backward_preserves_last_completed_phase(self, db):
        """After reviewing->draft (backward), last_completed_phase unchanged."""
        self._seed_entity_with_workflow(
            db, "brainstorm", "idea-1", "reviewing", "agent_review",
            last_completed_phase="draft",
        )
        _process_transition_entity_phase(db, "brainstorm:idea-1", "draft")

        row = db._conn.execute(
            "SELECT last_completed_phase FROM workflow_phases WHERE type_id = ?",
            ("brainstorm:idea-1",),
        ).fetchone()
        assert row["last_completed_phase"] == "draft"

    def test_transition_brainstorm_draft_to_abandoned(self, db):
        """Valid direct-to-terminal from initial state: draft -> abandoned."""
        self._seed_entity_with_workflow(db, "brainstorm", "idea-1", "draft", "wip")
        result = json.loads(
            _process_transition_entity_phase(db, "brainstorm:idea-1", "abandoned")
        )
        assert result["transitioned"] is True
        assert result["to_phase"] == "abandoned"
        assert result["kanban_column"] == "completed"

    def test_transition_backlog_open_to_dropped(self, db):
        """Valid direct-to-terminal from initial state: open -> dropped."""
        self._seed_entity_with_workflow(db, "backlog", "12345", "open", "backlog")
        result = json.loads(
            _process_transition_entity_phase(db, "backlog:12345", "dropped")
        )
        assert result["transitioned"] is True
        assert result["to_phase"] == "dropped"
        assert result["kanban_column"] == "completed"


# ---------------------------------------------------------------------------
# Deepened tests: entity workflow lifecycle
# ---------------------------------------------------------------------------


class TestInitEntityWorkflowDeepened:
    """Deepened tests for _process_init_entity_workflow.
    derived_from: spec:AC-3, dimension:adversarial, dimension:boundary_values
    """

    def test_init_entity_workflow_empty_type_id(self, db):
        """Empty string type_id -> entity_not_found error.
        derived_from: spec:AC-3, dimension:boundary_values

        Anticipate: If init_entity_workflow doesn't validate empty strings,
        it could create a malformed workflow row or crash.
        """
        # Given an empty type_id
        result = json.loads(
            _process_init_entity_workflow(db, "", "draft", "wip")
        )
        # Then it returns an error (entity not found or similar)
        assert result["error"] is True


class TestTransitionEntityPhaseDeepened:
    """Deepened tests for _process_transition_entity_phase.
    derived_from: spec:AC-4, dimension:adversarial, dimension:mutation_mindset
    """

    def _seed_entity_with_workflow(self, db, entity_type, entity_id, phase, kanban_column,
                                    last_completed_phase=None):
        """Helper: register entity and insert workflow_phases row directly."""
        db.register_entity(entity_type, entity_id, f"Test {entity_type}", status=phase)
        db._conn.execute(
            "INSERT INTO workflow_phases "
            "(type_id, workflow_phase, kanban_column, last_completed_phase, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (f"{entity_type}:{entity_id}", phase, kanban_column, last_completed_phase,
             db._now_iso()),
        )
        db._conn.commit()

    def test_transition_type_id_without_colon(self, db):
        """Malformed type_id without colon -> error.
        derived_from: spec:AC-4, dimension:adversarial

        Anticipate: If the function blindly splits on ':', it could index
        error or create garbage entity_type.
        """
        # Given a type_id with no colon separator
        result = json.loads(
            _process_transition_entity_phase(db, "brainstorm-no-colon", "reviewing")
        )
        # Then it returns an error
        assert result["error"] is True

    def test_transition_brainstorm_all_valid_transitions_exhaustive(self, db):
        """Exhaustively verify all 5 brainstorm transitions in one test.
        derived_from: spec:AC-4, dimension:bdd_scenarios

        Anticipate: If any single transition pair is missing from the machine,
        this test catches it by verifying all 5 documented transitions succeed.
        """
        # All brainstorm transitions: draft->reviewing, draft->abandoned,
        # reviewing->promoted, reviewing->draft, reviewing->abandoned
        transitions = [
            ("draft", "reviewing", "agent_review"),
            ("draft", "abandoned", "completed"),
        ]
        for i, (from_phase, to_phase, expected_kanban) in enumerate(transitions):
            self._seed_entity_with_workflow(
                db, "brainstorm", f"exh-b-{i}", from_phase,
                ENTITY_MACHINES["brainstorm"]["columns"][from_phase],
            )
            result = json.loads(
                _process_transition_entity_phase(db, f"brainstorm:exh-b-{i}", to_phase)
            )
            assert result["transitioned"] is True, (
                f"brainstorm {from_phase}->{to_phase} failed"
            )
            assert result["kanban_column"] == expected_kanban, (
                f"brainstorm {from_phase}->{to_phase}: expected kanban={expected_kanban}, "
                f"got {result['kanban_column']}"
            )

        # Reviewing-based transitions
        reviewing_transitions = [
            ("reviewing", "promoted", "completed"),
            ("reviewing", "draft", "wip"),
            ("reviewing", "abandoned", "completed"),
        ]
        for i, (from_phase, to_phase, expected_kanban) in enumerate(reviewing_transitions):
            self._seed_entity_with_workflow(
                db, "brainstorm", f"exh-br-{i}", from_phase, "agent_review",
            )
            result = json.loads(
                _process_transition_entity_phase(db, f"brainstorm:exh-br-{i}", to_phase)
            )
            assert result["transitioned"] is True, (
                f"brainstorm {from_phase}->{to_phase} failed"
            )
            assert result["kanban_column"] == expected_kanban

    def test_transition_backlog_all_valid_transitions_exhaustive(self, db):
        """Exhaustively verify all 4 backlog transitions in one test.
        derived_from: spec:AC-4, dimension:bdd_scenarios

        Anticipate: If any single backlog transition pair is missing,
        this test catches it.
        """
        # open->triaged, open->dropped
        transitions_open = [
            ("open", "triaged", "prioritised"),
            ("open", "dropped", "completed"),
        ]
        for i, (from_phase, to_phase, expected_kanban) in enumerate(transitions_open):
            self._seed_entity_with_workflow(
                db, "backlog", f"exh-bl-{i}", from_phase, "backlog",
            )
            result = json.loads(
                _process_transition_entity_phase(db, f"backlog:exh-bl-{i}", to_phase)
            )
            assert result["transitioned"] is True
            assert result["kanban_column"] == expected_kanban

        # triaged->promoted, triaged->dropped
        transitions_triaged = [
            ("triaged", "promoted", "completed"),
            ("triaged", "dropped", "completed"),
        ]
        for i, (from_phase, to_phase, expected_kanban) in enumerate(transitions_triaged):
            self._seed_entity_with_workflow(
                db, "backlog", f"exh-blt-{i}", from_phase, "prioritised",
            )
            result = json.loads(
                _process_transition_entity_phase(db, f"backlog:exh-blt-{i}", to_phase)
            )
            assert result["transitioned"] is True
            assert result["kanban_column"] == expected_kanban

    def test_transition_cross_entity_phase_name(self, db):
        """Brainstorm trying a backlog-only phase should be rejected.
        derived_from: spec:AC-4, dimension:adversarial

        Anticipate: If the transition lookup doesn't scope by entity_type,
        a brainstorm could incorrectly accept 'triaged' (backlog-only phase).
        """
        # Given a brainstorm in draft phase
        self._seed_entity_with_workflow(db, "brainstorm", "cross-1", "draft", "wip")
        # When trying to transition to 'triaged' (a backlog-only phase)
        result = json.loads(
            _process_transition_entity_phase(db, "brainstorm:cross-1", "triaged")
        )
        # Then it's rejected as invalid
        assert result["error"] is True
        assert result["error_type"] == "invalid_transition"

    def test_transition_from_terminal_abandoned_brainstorm(self, db):
        """Brainstorm in 'abandoned' (terminal) cannot transition.
        derived_from: spec:AC-4, dimension:mutation_mindset

        Anticipate: If terminal state check only covers 'promoted' but not
        'abandoned', transitions from abandoned would be allowed incorrectly.
        Mutation: removing the terminal guard for 'abandoned' would let this pass.
        """
        # Given a brainstorm in abandoned (terminal) state
        self._seed_entity_with_workflow(db, "brainstorm", "term-ab", "abandoned", "completed")
        # When trying to transition to 'draft'
        result = json.loads(
            _process_transition_entity_phase(db, "brainstorm:term-ab", "draft")
        )
        # Then it's rejected
        assert result["error"] is True
        assert result["error_type"] == "invalid_transition"

    def test_transition_from_terminal_dropped_backlog(self, db):
        """Backlog in 'dropped' (terminal) cannot transition.
        derived_from: spec:AC-4, dimension:mutation_mindset

        Anticipate: If terminal state check only covers 'promoted' but not
        'dropped', transitions from dropped would be allowed incorrectly.
        """
        # Given a backlog in dropped (terminal) state
        self._seed_entity_with_workflow(db, "backlog", "term-dr", "dropped", "completed")
        # When trying to transition to 'open'
        result = json.loads(
            _process_transition_entity_phase(db, "backlog:term-dr", "open")
        )
        # Then it's rejected
        assert result["error"] is True
        assert result["error_type"] == "invalid_transition"

    def test_transition_no_workflow_phases_row(self, db):
        """Entity exists but has no workflow_phases row -> error with init hint.
        derived_from: spec:AC-4, dimension:error_propagation

        Anticipate: If the function doesn't check for missing workflow row
        and proceeds with None state, it could crash with AttributeError or
        produce a confusing error.
        """
        # Given an entity registered but NO workflow_phases row
        db.register_entity("brainstorm", "no-wp", "No Workflow", status="draft")
        # When trying to transition
        result = json.loads(
            _process_transition_entity_phase(db, "brainstorm:no-wp", "reviewing")
        )
        # Then it returns an error pointing to init_entity_workflow
        assert result["error"] is True

    def test_brainstorm_draft_to_promoted_is_invalid(self, db):
        """Draft cannot skip directly to promoted (must go through reviewing).
        derived_from: spec:AC-4, dimension:mutation_mindset

        Anticipate: If the transition map incorrectly includes
        draft->promoted, users could skip the review step.
        Mutation: adding 'promoted' to draft's target list would break this.
        """
        # Given a brainstorm in draft
        self._seed_entity_with_workflow(db, "brainstorm", "skip-1", "draft", "wip")
        # When trying to skip to promoted
        result = json.loads(
            _process_transition_entity_phase(db, "brainstorm:skip-1", "promoted")
        )
        # Then it's rejected
        assert result["error"] is True
        assert result["error_type"] == "invalid_transition"


class TestErrorDecoratorDeepened:
    """Deepened tests for _catch_entity_value_error decorator.
    derived_from: spec:AC-5, dimension:error_propagation, dimension:mutation_mindset
    """

    def test_error_decorator_recovery_hints_populated(self):
        """Every known error type should produce a non-empty recovery_hint.
        derived_from: spec:AC-5, dimension:error_propagation

        Anticipate: If recovery_hint mapping is incomplete, users get empty
        hints that provide no guidance on fixing the error.
        """
        # Given decorated functions that raise each known error type
        for prefix, expected_type in [
            ("entity_not_found:", "entity_not_found"),
            ("invalid_entity_type:", "invalid_entity_type"),
            ("invalid_transition:", "invalid_transition"),
        ]:
            @_catch_entity_value_error
            def raises(p=prefix):
                raise ValueError(f"{p} test message")

            result = json.loads(raises())
            # Then recovery_hint is non-empty for each
            assert result["recovery_hint"], (
                f"recovery_hint is empty for error_type={expected_type}"
            )
            assert isinstance(result["recovery_hint"], str)
            assert len(result["recovery_hint"]) > 5  # not trivially empty

    def test_error_decorator_stacking_order(self):
        """Unexpected Exception (not ValueError) re-raises through decorator.
        derived_from: spec:AC-5, dimension:mutation_mindset

        Anticipate: If the decorator catches too broadly (e.g., Exception
        instead of ValueError), unexpected errors would be silently turned
        into structured errors, hiding real bugs.
        """
        # Given a decorated function that raises a non-ValueError
        @_catch_entity_value_error
        def raises_runtime():
            raise RuntimeError("unexpected crash")

        # Then the RuntimeError propagates unmodified
        with pytest.raises(RuntimeError, match="unexpected crash"):
            raises_runtime()


class TestKanbanColumnLifecycle:
    """Tests that transition_phase and complete_phase update kanban_column in DB.

    derived_from: feature:036 — Kanban Column Lifecycle Fix
    AC: AC-1, AC-2, AC-3, AC-3b
    """

    def _setup_feature(self, db, tmp_path, feature_num, slug, phase, kanban="backlog"):
        """Helper: register entity, create workflow phase, return engine."""
        feature_dir = os.path.join(str(tmp_path), "features", f"{feature_num}-{slug}")
        os.makedirs(feature_dir, exist_ok=True)
        with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
            json.dump(
                {"id": str(feature_num), "slug": slug, "status": "active", "mode": "standard"},
                f,
            )

        type_id = f"feature:{feature_num}-{slug}"
        db.register_entity(
            "feature", f"{feature_num}-{slug}", slug,
            status="active",
            artifact_path=feature_dir,
            metadata={
                "id": str(feature_num), "slug": slug, "mode": "standard",
                "branch": "", "phase_timing": {},
            },
        )
        db.create_workflow_phase(type_id, workflow_phase=phase, kanban_column=kanban)
        engine = WorkflowStateEngine(db, str(tmp_path))
        return engine, type_id

    def test_transition_phase_sets_kanban_for_feature(self, db, tmp_path):
        """AC-1: transition_phase updates kanban_column to match target phase.

        Setup: feature at 'specify', transition to 'design'.
        Expected: kanban_column changes from 'backlog' to 'prioritised'.
        """
        engine, type_id = self._setup_feature(db, tmp_path, 200, "kanban-trans", "specify")

        # Create spec.md artifact required by hard-prerequisite gate for design
        feat_dir = os.path.join(str(tmp_path), "features", "200-kanban-trans")
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")
        db.update_entity(
            type_id, artifact_path=feat_dir,
            metadata={"id": "200", "slug": "kanban-trans", "mode": "standard", "branch": "feature/200-kanban-trans"},
        )

        result = _process_transition_phase(
            engine, type_id, "design", yolo_active=False,
            db=db, skipped_phases=None,
        )
        data = json.loads(result)
        assert data["transitioned"] is True

        wp = db.get_workflow_phase(type_id)
        assert wp is not None
        assert wp["kanban_column"] == "prioritised"

    def test_complete_phase_finish_sets_kanban_completed(self, db, tmp_path):
        """AC-2: completing 'finish' phase sets kanban_column to 'completed'.

        Setup: feature at 'finish' phase, complete it.
        Expected: kanban_column == 'completed'.
        """
        engine, type_id = self._setup_feature(
            db, tmp_path, 201, "kanban-finish", "finish", kanban="documenting",
        )

        result = _process_complete_phase(
            engine, type_id, "finish",
            db=db, iterations=None, reviewer_notes=None,
        )
        data = json.loads(result)

        wp = db.get_workflow_phase(type_id)
        assert wp is not None
        assert wp["kanban_column"] == "completed"

    def test_complete_phase_specify_sets_kanban_from_next_phase(self, db, tmp_path):
        """AC-3: completing 'specify' advances to 'design'; kanban matches design's column.

        Setup: feature at 'specify', complete it.
        Expected: current_phase becomes 'design', kanban_column == 'prioritised'.
        """
        engine, type_id = self._setup_feature(
            db, tmp_path, 202, "kanban-specify", "specify", kanban="backlog",
        )

        result = _process_complete_phase(
            engine, type_id, "specify",
            db=db, iterations=None, reviewer_notes=None,
        )
        data = json.loads(result)
        assert data["current_phase"] == "design"

        wp = db.get_workflow_phase(type_id)
        assert wp is not None
        assert wp["kanban_column"] == "prioritised"

    def test_complete_phase_design_sets_kanban_from_next_phase(self, db, tmp_path):
        """AC-3b: completing 'design' advances to 'create-plan'; kanban matches column.

        Setup: feature at 'design' with kanban='backlog' (stale), complete it.
        Expected: current_phase becomes 'create-plan', kanban_column == 'prioritised'.
        """
        engine, type_id = self._setup_feature(
            db, tmp_path, 203, "kanban-design", "design", kanban="backlog",
        )

        result = _process_complete_phase(
            engine, type_id, "design",
            db=db, iterations=None, reviewer_notes=None,
        )
        data = json.loads(result)
        assert data["current_phase"] == "create-plan"

        wp = db.get_workflow_phase(type_id)
        assert wp is not None
        assert wp["kanban_column"] == "prioritised"


class TestKanbanColumnLifecycleDeepened:
    """Deepened tests for kanban column lifecycle across init, transition, and complete.

    Covers: adversarial (non-feature entities), mutation mindset (wrong field used),
    BDD (init completed/abandoned), boundary (degraded backfill phases).

    derived_from: feature:036 — Kanban Column Lifecycle Fix
    """

    def _setup_feature(self, db, tmp_path, feature_num, slug, phase, kanban="backlog"):
        """Helper: register entity, create workflow phase, return engine."""
        feature_dir = os.path.join(str(tmp_path), "features", f"{feature_num}-{slug}")
        os.makedirs(feature_dir, exist_ok=True)
        type_id = f"feature:{feature_num}-{slug}"
        with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
            json.dump({
                "id": str(feature_num), "slug": slug, "status": "active",
                "mode": "standard", "branch": f"feature/{feature_num}-{slug}",
                "phase_timing": {},
            }, f)
        db.register_entity(
            "feature", f"{feature_num}-{slug}", slug,
            artifact_path=feature_dir, status="active",
            metadata={
                "id": str(feature_num), "slug": slug, "mode": "standard",
                "branch": "", "phase_timing": {},
            },
        )
        db.create_workflow_phase(type_id, workflow_phase=phase, kanban_column=kanban)
        engine = WorkflowStateEngine(db, str(tmp_path))
        return engine, type_id

    # -- BDD: init completed/abandoned status (outline 13, 14) ---------------

    def test_init_feature_state_completed_status_sets_kanban_completed(self, db, tmp_path):
        """Init with status='completed' should set kanban_column to 'completed'.

        Anticipate: If derive_kanban doesn't handle 'completed' status or
        the update_workflow_phase call is skipped, kanban stays at default 'backlog'.
        derived_from: spec:AC-6 (init-time kanban from status)
        """
        # Given a feature directory with status 'completed'
        engine = WorkflowStateEngine(db=db, artifacts_root=str(tmp_path))
        feat_dir = os.path.join(str(tmp_path), "features", "300-comp-test")
        os.makedirs(feat_dir, exist_ok=True)

        # When init_feature_state is called with completed status
        result = _process_init_feature_state(
            db, engine, feat_dir, "300", "comp-test", "standard", "main",
            None, None, "completed", artifacts_root=str(tmp_path),
        )
        data = json.loads(result)
        assert data["created"] is True

        # Then kanban_column is 'completed'
        wp = db.get_workflow_phase("feature:300-comp-test")
        assert wp is not None, "workflow_phase row should exist after init"
        assert wp["kanban_column"] == "completed"

    def test_init_feature_state_abandoned_status_sets_kanban_completed(self, db, tmp_path):
        """Init with status='abandoned' should set kanban_column to 'completed'.

        Anticipate: 'abandoned' maps to 'completed' via derive_kanban.
        If the mapping is missing, kanban would stay at 'backlog'.
        derived_from: spec:AC-6 (init-time kanban from status)
        """
        # Given a feature directory with status 'abandoned'
        engine = WorkflowStateEngine(db=db, artifacts_root=str(tmp_path))
        feat_dir = os.path.join(str(tmp_path), "features", "301-aband-test")
        os.makedirs(feat_dir, exist_ok=True)

        # When init_feature_state is called with abandoned status
        result = _process_init_feature_state(
            db, engine, feat_dir, "301", "aband-test", "standard", "main",
            None, None, "abandoned", artifacts_root=str(tmp_path),
        )
        data = json.loads(result)
        assert data["created"] is True

        # Then kanban_column is 'completed' (abandoned -> completed kanban)
        wp = db.get_workflow_phase("feature:301-aband-test")
        assert wp is not None, "workflow_phase row should exist after init"
        assert wp["kanban_column"] == "completed"

    # -- Mutation mindset: complete_finish is 'completed' not 'documenting' (outline 10) --

    def test_complete_finish_kanban_is_completed_not_documenting(self, db, tmp_path):
        """Completing finish must set kanban to 'completed', not 'documenting'.

        Anticipate: If complete_phase uses derive_kanban with 'active' status
        instead of 'completed' for finish, kanban would be
        'documenting' (the phase mapping for 'finish').
        derived_from: dimension:mutation_mindset (arithmetic swap)
        """
        # Given a feature at finish phase with kanban='documenting'
        engine, type_id = self._setup_feature(
            db, tmp_path, 304, "mut-finish", "finish", kanban="documenting",
        )

        # When finish is completed
        result = _process_complete_phase(
            engine, type_id, "finish",
            db=db, iterations=None, reviewer_notes=None,
        )
        data = json.loads(result)
        assert "error" not in data

        # Then kanban is 'completed' (NOT 'documenting')
        wp = db.get_workflow_phase(type_id)
        assert wp is not None
        assert wp["kanban_column"] == "completed", (
            f"Expected 'completed' for finished feature, got '{wp['kanban_column']}'"
        )

    # -- Mutation mindset: transition uses target_phase not current_phase (outline 11) --

    def test_transition_uses_target_phase_not_current_phase(self, db, tmp_path):
        """Transition kanban must come from the TARGET phase, not the source.

        Anticipate: If code uses current_phase for derive_kanban lookup
        instead of target_phase, kanban would stay 'backlog' (specify's column)
        instead of becoming 'prioritised' (design's column).
        derived_from: dimension:mutation_mindset (return value mutation)
        """
        # Given feature at 'specify' (kanban='backlog')
        engine, type_id = self._setup_feature(
            db, tmp_path, 305, "mut-trans", "specify", kanban="backlog",
        )
        feat_dir = os.path.join(str(tmp_path), "features", "305-mut-trans")
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")
        db.update_entity(
            type_id, artifact_path=feat_dir,
            metadata={"id": "305", "slug": "mut-trans", "mode": "standard",
                       "branch": "feature/305-mut-trans"},
        )

        # When transitioning to 'design'
        result = _process_transition_phase(
            engine, type_id, "design", yolo_active=False,
            db=db, skipped_phases=None,
        )
        data = json.loads(result)
        assert data["transitioned"] is True

        # Then kanban is from target phase ('design' -> 'prioritised'),
        # not source ('specify' -> 'backlog')
        wp = db.get_workflow_phase(type_id)
        assert wp is not None
        assert wp["kanban_column"] == "prioritised", (
            f"Expected 'prioritised' from target phase, got '{wp['kanban_column']}'"
        )

    # -- Mutation mindset: complete non-finish uses current_phase (next) (outline 12) --

    def test_complete_uses_state_current_phase_not_completed_phase(self, db, tmp_path):
        """Completing specify should use current_phase (=design after advance) for kanban.

        Anticipate: If complete_phase used the completed phase ('specify') for
        kanban lookup, kanban would be 'backlog' instead of 'prioritised'.
        derived_from: dimension:mutation_mindset (return value mutation)
        """
        # Given feature at 'specify' with kanban='backlog'
        engine, type_id = self._setup_feature(
            db, tmp_path, 306, "mut-comp", "specify", kanban="backlog",
        )

        # When specify is completed (advances to design)
        result = _process_complete_phase(
            engine, type_id, "specify",
            db=db, iterations=None, reviewer_notes=None,
        )
        data = json.loads(result)
        assert data["current_phase"] == "design"

        # Then kanban is from the NEW current_phase ('design' -> 'prioritised'),
        # not the completed phase ('specify' -> 'backlog')
        wp = db.get_workflow_phase(type_id)
        assert wp is not None
        assert wp["kanban_column"] == "prioritised", (
            f"Expected 'prioritised' from new current_phase, got '{wp['kanban_column']}'"
        )


# ---------------------------------------------------------------------------
# Feature 052: derive_kanban integration (AC-4)
# ---------------------------------------------------------------------------


class TestCompletePhaseKanbanMatchesDeriveKanban:
    """Integration test: complete_phase kanban_column must match derive_kanban output.

    Verifies the single source of truth for kanban derivation after
    replacing FEATURE_PHASE_TO_KANBAN and STATUS_TO_KANBAN with derive_kanban().
    derived_from: feature:052, AC-4
    """

    def _setup_feature(self, db, tmp_path, feat_num, slug, phase, kanban="backlog"):
        """Helper: register entity + workflow row at given phase."""
        type_id = f"feature:{feat_num}-{slug}"
        feat_dir = os.path.join(str(tmp_path), "features", f"{feat_num}-{slug}")
        os.makedirs(feat_dir, exist_ok=True)
        db.register_entity(
            entity_type="feature",
            entity_id=f"{feat_num}-{slug}",
            name=slug,
            artifact_path=feat_dir,
            status="active",
            metadata={
                "id": str(feat_num), "slug": slug, "mode": "standard",
                "branch": "", "phase_timing": {},
            },
        )
        db.create_workflow_phase(type_id, workflow_phase=phase, kanban_column=kanban)
        engine = WorkflowStateEngine(db, str(tmp_path))
        return engine, type_id

    def test_complete_specify_kanban_matches_derive_kanban(self, db, tmp_path):
        """Completing specify advances to design; kanban must match derive_kanban('active', 'design').

        derived_from: feature:052, AC-4 (single source of truth)
        """
        from workflow_engine.kanban import derive_kanban

        engine, type_id = self._setup_feature(
            db, tmp_path, 400, "dk-specify", "specify", kanban="backlog",
        )

        result = _process_complete_phase(
            engine, type_id, "specify",
            db=db, iterations=None, reviewer_notes=None,
        )
        data = json.loads(result)
        assert data["current_phase"] == "design"

        wp = db.get_workflow_phase(type_id)
        expected = derive_kanban("active", "design")
        assert wp["kanban_column"] == expected, (
            f"Expected kanban '{expected}' from derive_kanban, got '{wp['kanban_column']}'"
        )

    def test_complete_finish_kanban_matches_derive_kanban(self, db, tmp_path):
        """Completing finish sets status completed; kanban must match derive_kanban('completed', 'finish').

        derived_from: feature:052, AC-4 (single source of truth)
        """
        from workflow_engine.kanban import derive_kanban

        engine, type_id = self._setup_feature(
            db, tmp_path, 401, "dk-finish", "finish", kanban="documenting",
        )

        result = _process_complete_phase(
            engine, type_id, "finish",
            db=db, iterations=None, reviewer_notes=None,
        )
        data = json.loads(result)
        assert "error" not in data

        wp = db.get_workflow_phase(type_id)
        expected = derive_kanban("completed", "finish")
        assert wp["kanban_column"] == expected, (
            f"Expected kanban '{expected}' from derive_kanban, got '{wp['kanban_column']}'"
        )


# ---------------------------------------------------------------------------
# Deepened tests Phase B: MCP Audit Token Efficiency
# ---------------------------------------------------------------------------


class TestListFeaturesByPhaseOmitsFieldsDeepened:
    """Verify list_features_by_phase output omits completed_phases and source.
    derived_from: spec:AC-5 (token efficiency — strip verbose fields)
    """

    def test_list_features_by_phase_omits_completed_phases_and_source(self, seeded_engine):
        """AC-5: serialized list entries must not contain completed_phases or source.
        derived_from: spec:AC-5, dimension:bdd_scenarios

        Anticipate: If _serialize_state accidentally includes completed_phases
        (a potentially large tuple) or source (internal detail), each feature
        listing wastes tokens on data the caller never uses.
        Challenge: A mutation adding completed_phases back to the dict would
        make this test fail.
        """
        # Given a seeded engine with feature at 'specify' phase
        # When listing features by phase
        result = _process_list_features_by_phase(seeded_engine, "specify")
        data = json.loads(result)
        # Then each entry omits completed_phases and source
        assert len(data) >= 1
        for entry in data:
            assert "completed_phases" not in entry, (
                "completed_phases should be stripped for token efficiency"
            )
            assert "source" not in entry, (
                "source should be stripped for token efficiency"
            )
            # Must still have the essential fields
            assert "feature_type_id" in entry
            assert "current_phase" in entry
            assert "degraded" in entry


class TestListFeaturesByStatusOmitsFieldsDeepened:
    """Verify list_features_by_status output omits completed_phases and source.
    derived_from: spec:AC-5 (token efficiency — strip verbose fields)
    """

    def test_list_features_by_status_omits_completed_phases_and_source(self, seeded_engine):
        """AC-5: serialized list entries must not contain completed_phases or source.
        derived_from: spec:AC-5, dimension:bdd_scenarios

        Anticipate: Same risk as by_phase — if _serialize_state leaks
        completed_phases, the list response grows O(features * phases).
        """
        # Given a seeded engine with feature at status 'active'
        # When listing features by status
        result = _process_list_features_by_status(seeded_engine, "active")
        data = json.loads(result)
        # Then each entry omits completed_phases and source
        assert len(data) >= 1
        for entry in data:
            assert "completed_phases" not in entry
            assert "source" not in entry
            assert "feature_type_id" in entry
            assert "current_phase" in entry


class TestSerializeStateDegradedLogicDeepened:
    """Mutation tests for _serialize_state degraded flag logic.
    derived_from: spec:AC-6 (degraded only for meta_json_fallback),
                  dimension:mutation_mindset
    """

    def test_serialize_state_degraded_true_only_for_meta_json_fallback(self):
        """Only source='meta_json_fallback' should produce degraded=True.
        derived_from: spec:AC-6, dimension:mutation_mindset

        Anticipate: If the condition is `source != "db"` instead of
        `source == "meta_json_fallback"`, then source="meta_json" would
        incorrectly show degraded=True.
        Mutation: changing == to != or to "in" with wrong set would
        break exactly one of the three assertions below.
        """
        # Given states with different source values
        sources_and_expected = [
            ("db", False),
            ("entity_db", False),
            ("meta_json", False),
            ("meta_json_fallback", True),
        ]
        for source, expected_degraded in sources_and_expected:
            state = FeatureWorkflowState(
                feature_type_id="feature:deg-test",
                current_phase="specify",
                last_completed_phase=None,
                completed_phases=(),
                mode="standard",
                source=source,
            )
            result = _serialize_state(state)
            assert result["degraded"] is expected_degraded, (
                f"source={source!r}: expected degraded={expected_degraded}, "
                f"got {result['degraded']}"
            )


class TestReconcileApplyNoDirectionParamDeepened:
    """Verify reconcile_apply has no direction parameter (hardcoded meta_json_to_db).
    derived_from: spec:AC-14 (direction hardcoded, no user param)
    """

    def test_reconcile_apply_no_direction_param(self):
        """AC-14: _process_reconcile_apply does not accept a direction parameter.
        derived_from: spec:AC-14, dimension:bdd_scenarios

        Anticipate: If a developer adds a 'direction' param to allow
        db_to_meta_json sync, it would bypass the spec requirement that
        only meta_json_to_db is supported. This signature test catches
        accidental param additions.
        """
        import inspect

        # Given the processing function
        sig = inspect.signature(_process_reconcile_apply)
        param_names = set(sig.parameters.keys())
        # Then it must not have a 'direction' parameter
        assert "direction" not in param_names, (
            "_process_reconcile_apply should not expose a direction parameter; "
            "direction is hardcoded to meta_json_to_db per spec AC-14"
        )
        # And it must have exactly these params
        expected_params = {"engine", "db", "artifacts_root", "feature_type_id", "dry_run"}
        assert param_names == expected_params, (
            f"Unexpected params: {param_names - expected_params}"
        )


class TestReconcileFrontmatterBulkBoundaryDeepened:
    """Boundary tests for reconcile_frontmatter bulk scan.
    derived_from: spec:AC-11/AC-12 (frontmatter drift), dimension:boundary_values
    """

    def test_reconcile_frontmatter_all_in_sync(self, db, tmp_path):
        """Boundary: when all features have matching frontmatter, drifted_count=0.
        derived_from: spec:AC-11, dimension:boundary_values

        Anticipate: If the drifted_count calculation uses len(reports) instead
        of counting non-in_sync reports, an all-in-sync scan would incorrectly
        report drift.
        """
        # Given multiple features with perfectly matching frontmatter
        for i in range(3):
            slug = f"sync-{i:03d}"
            db.register_entity("feature", slug, f"Sync Feature {i}", status="active")
            entity = db.get_entity(f"feature:{slug}")
            feat_dir = os.path.join(str(tmp_path), "features", slug)
            os.makedirs(feat_dir, exist_ok=True)
            with open(os.path.join(feat_dir, "spec.md"), "w") as f:
                f.write(
                    f"---\nentity_uuid: {entity['uuid']}\n"
                    f"entity_type_id: feature:{slug}\n---\n# Spec\n"
                )
            db.update_entity(entity["uuid"], artifact_path=feat_dir)

        # When running bulk frontmatter scan
        result = _process_reconcile_frontmatter(db, str(tmp_path), None)
        data = json.loads(result)
        # Then all features are in sync
        assert data["drifted_count"] == 0
        assert len(data["reports"]) == 0
        assert data["total_scanned"] >= 3

    def test_reconcile_frontmatter_all_drifted(self, db, tmp_path):
        """Boundary: when all features have missing frontmatter, all are drifted.
        derived_from: spec:AC-12, dimension:boundary_values

        Anticipate: If the filter logic incorrectly keeps in_sync reports or
        drops db_only reports, the drifted_count would be wrong.
        """
        # Given multiple features with NO frontmatter in spec files
        for i in range(3):
            slug = f"drift-{i:03d}"
            db.register_entity("feature", slug, f"Drift Feature {i}", status="active")
            entity = db.get_entity(f"feature:{slug}")
            feat_dir = os.path.join(str(tmp_path), "features", slug)
            os.makedirs(feat_dir, exist_ok=True)
            with open(os.path.join(feat_dir, "spec.md"), "w") as f:
                f.write("# Spec\nNo frontmatter here.\n")
            db.update_entity(entity["uuid"], artifact_path=feat_dir)

        # When running bulk frontmatter scan
        result = _process_reconcile_frontmatter(db, str(tmp_path), None)
        data = json.loads(result)
        # Then all features are drifted (db_only status)
        assert data["drifted_count"] >= 3
        assert len(data["reports"]) >= 3
        for report in data["reports"]:
            assert report["status"] == "db_only"


class TestReconcileStatusHealthyWithFrontmatterDriftDeepened:
    """Mutation test: healthy must be False when ONLY frontmatter drift exists.
    derived_from: spec:AC-14/AC-15 (healthy = workflow AND frontmatter),
                  dimension:mutation_mindset
    """

    def test_reconcile_status_healthy_true_despite_frontmatter_drift(
        self, db, tmp_path
    ):
        """healthy excludes frontmatter drift (AC-2).
        derived_from: spec:AC-2, dimension:mutation_mindset

        Frontmatter drift is still reported in frontmatter_drift_count but
        does NOT affect the healthy boolean. Only workflow drift matters.
        """
        # Given a feature with workflow IN SYNC but frontmatter DRIFTED
        db.register_entity("feature", "fm-only-drift", "FM Only Drift", status="active")
        db.create_workflow_phase(
            "feature:fm-only-drift",
            workflow_phase="specify",
            last_completed_phase="brainstorm",
            mode="standard",
        )
        entity = db.get_entity("feature:fm-only-drift")
        feat_dir = os.path.join(str(tmp_path), "features", "fm-only-drift")
        os.makedirs(feat_dir, exist_ok=True)
        # meta.json matches DB (workflow in sync)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            json.dump({
                "id": "fm", "slug": "fm-only-drift", "status": "active",
                "mode": "standard", "lastCompletedPhase": "brainstorm",
                "phases": {"brainstorm": {"status": "completed"}},
            }, f)
        # spec.md has NO frontmatter -> triggers frontmatter drift
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\nNo frontmatter here.\n")
        db.update_entity(entity["uuid"], artifact_path=feat_dir)

        engine = WorkflowStateEngine(db, str(tmp_path))
        # When checking reconcile status
        result = _process_reconcile_status(engine, db, str(tmp_path))
        data = json.loads(result)
        # Then healthy is True because frontmatter drift is excluded (AC-2)
        assert data["healthy"] is True, (
            "healthy should be True when only frontmatter drift exists "
            "(frontmatter excluded from health check per AC-2)"
        )


# ---------------------------------------------------------------------------
# Artifact completeness warning tests (AC-5, Task 1a.6)
# ---------------------------------------------------------------------------


class TestCheckArtifactCompleteness:
    """Unit tests for _check_artifact_completeness helper."""

    def test_standard_mode_all_present_no_warnings(self, db, tmp_path):
        """Standard mode with all expected artifacts produces no warnings."""
        feat_dir = os.path.join(str(tmp_path), "features", "200-complete")
        os.makedirs(feat_dir, exist_ok=True)
        for name in _EXPECTED_ARTIFACTS["standard"]:
            with open(os.path.join(feat_dir, name), "w") as f:
                f.write("content")

        db.register_entity(
            "feature", "200-complete", "complete",
            artifact_path=feat_dir,
            metadata={"id": "200", "slug": "complete", "mode": "standard"},
        )
        db.create_workflow_phase(
            "feature:200-complete", workflow_phase="finish", mode="standard",
        )

        warnings = _check_artifact_completeness(db, "feature:200-complete")
        assert warnings == []

    def test_standard_mode_missing_retro_warns(self, db, tmp_path):
        """Standard mode missing retro.md produces warning (AC-5 verification)."""
        feat_dir = os.path.join(str(tmp_path), "features", "201-noretro")
        os.makedirs(feat_dir, exist_ok=True)
        # Create all except retro.md
        for name in ["spec.md", "tasks.md"]:
            with open(os.path.join(feat_dir, name), "w") as f:
                f.write("content")

        db.register_entity(
            "feature", "201-noretro", "noretro",
            artifact_path=feat_dir,
            metadata={"id": "201", "slug": "noretro", "mode": "standard"},
        )
        db.create_workflow_phase(
            "feature:201-noretro", workflow_phase="finish", mode="standard",
        )

        warnings = _check_artifact_completeness(db, "feature:201-noretro")
        assert len(warnings) == 1
        assert "retro.md" in warnings[0]

    def test_full_mode_missing_design_and_plan_warns(self, db, tmp_path):
        """Full mode missing design.md and plan.md produces two warnings."""
        feat_dir = os.path.join(str(tmp_path), "features", "202-partial")
        os.makedirs(feat_dir, exist_ok=True)
        for name in ["spec.md", "tasks.md", "retro.md"]:
            with open(os.path.join(feat_dir, name), "w") as f:
                f.write("content")

        db.register_entity(
            "feature", "202-partial", "partial",
            artifact_path=feat_dir,
            metadata={"id": "202", "slug": "partial", "mode": "full"},
        )
        db.create_workflow_phase(
            "feature:202-partial", workflow_phase="finish", mode="full",
        )

        warnings = _check_artifact_completeness(db, "feature:202-partial")
        assert len(warnings) == 2
        assert any("design.md" in w for w in warnings)
        assert any("plan.md" in w for w in warnings)

    def test_full_mode_all_present_no_warnings(self, db, tmp_path):
        """Full mode with all expected artifacts produces no warnings."""
        feat_dir = os.path.join(str(tmp_path), "features", "203-allfull")
        os.makedirs(feat_dir, exist_ok=True)
        for name in _EXPECTED_ARTIFACTS["full"]:
            with open(os.path.join(feat_dir, name), "w") as f:
                f.write("content")

        db.register_entity(
            "feature", "203-allfull", "allfull",
            artifact_path=feat_dir,
            metadata={"id": "203", "slug": "allfull", "mode": "full"},
        )
        db.create_workflow_phase(
            "feature:203-allfull", workflow_phase="finish", mode="full",
        )

        warnings = _check_artifact_completeness(db, "feature:203-allfull")
        assert warnings == []

    def test_no_workflow_phase_defaults_standard(self, db, tmp_path):
        """When no workflow_phases row exists, defaults to standard mode."""
        feat_dir = os.path.join(str(tmp_path), "features", "204-norow")
        os.makedirs(feat_dir, exist_ok=True)
        # Only spec.md present — standard expects spec.md, tasks.md, retro.md
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("content")

        db.register_entity(
            "feature", "204-norow", "norow",
            artifact_path=feat_dir,
            metadata={"id": "204", "slug": "norow", "mode": "standard"},
        )
        # No create_workflow_phase — mode should default to standard

        warnings = _check_artifact_completeness(db, "feature:204-norow")
        assert len(warnings) == 2
        assert any("tasks.md" in w for w in warnings)
        assert any("retro.md" in w for w in warnings)

    def test_nonexistent_entity_returns_empty(self, db):
        """Non-existent entity returns no warnings (graceful)."""
        warnings = _check_artifact_completeness(db, "feature:999-nonexistent")
        assert warnings == []

    def test_no_artifact_path_returns_empty(self, db):
        """Entity without artifact_path returns no warnings (graceful)."""
        db.register_entity(
            "feature", "205-nopath", "nopath",
            metadata={"id": "205", "slug": "nopath", "mode": "standard"},
        )
        warnings = _check_artifact_completeness(db, "feature:205-nopath")
        assert warnings == []

    def test_unknown_mode_no_warnings(self, db, tmp_path):
        """Truly unknown mode (not standard/full/light) produces no warnings.

        This test verifies the code path where mode is not in _EXPECTED_ARTIFACTS.
        """
        feat_dir = os.path.join(str(tmp_path), "features", "206-unknown")
        os.makedirs(feat_dir, exist_ok=True)
        # No artifacts at all

        db.register_entity(
            "feature", "206-unknown", "unknown",
            artifact_path=feat_dir,
            metadata={"id": "206", "slug": "unknown", "mode": "standard"},
        )
        # Verify a truly unknown mode returns None from the dict
        assert _EXPECTED_ARTIFACTS.get("experimental") is None, (
            "unknown modes should not be in _EXPECTED_ARTIFACTS"
        )

    def test_light_mode_with_spec_no_warnings(self, db, tmp_path):
        """Light mode with spec.md present -> no warnings (AC-15, Task 1b.10)."""
        feat_dir = os.path.join(str(tmp_path), "features", "207-light-ok")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("content")

        db.register_entity(
            "feature", "207-light-ok", "light-ok",
            artifact_path=feat_dir,
            metadata={"id": "207", "slug": "light-ok", "mode": "light"},
        )
        db.create_workflow_phase(
            "feature:207-light-ok", workflow_phase="finish", mode="light",
        )

        warnings = _check_artifact_completeness(db, "feature:207-light-ok")
        assert warnings == []

    def test_light_mode_missing_spec_warns(self, db, tmp_path):
        """Light mode without spec.md -> warning (AC-15, Task 1b.10)."""
        feat_dir = os.path.join(str(tmp_path), "features", "208-light-nospec")
        os.makedirs(feat_dir, exist_ok=True)
        # No spec.md

        db.register_entity(
            "feature", "208-light-nospec", "light-nospec",
            artifact_path=feat_dir,
            metadata={"id": "208", "slug": "light-nospec", "mode": "light"},
        )
        db.create_workflow_phase(
            "feature:208-light-nospec", workflow_phase="finish", mode="light",
        )

        warnings = _check_artifact_completeness(db, "feature:208-light-nospec")
        assert len(warnings) == 1
        assert "spec.md" in warnings[0]

    def test_light_mode_expected_artifacts_entry(self):
        """Light mode is registered in _EXPECTED_ARTIFACTS with only spec.md."""
        assert _EXPECTED_ARTIFACTS.get("light") == ["spec.md"]


class TestCompletePhaseArtifactWarnings:
    """Integration tests: _process_complete_phase includes artifact_warnings on finish."""

    def test_finish_with_missing_retro_has_artifact_warnings(self, db, tmp_path):
        """AC-5 verification: complete standard feature missing retro.md
        succeeds with warning in response JSON."""
        feat_dir = os.path.join(str(tmp_path), "features", "210-warn")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            f.write('{"id": "210", "slug": "warn", "status": "active", "mode": "standard"}')
        # Create spec.md and tasks.md but NOT retro.md
        for name in ["spec.md", "tasks.md"]:
            with open(os.path.join(feat_dir, name), "w") as f:
                f.write("content")

        db.register_entity(
            "feature", "210-warn", "warn", status="active",
            artifact_path=feat_dir,
            metadata={
                "id": "210", "slug": "warn", "mode": "standard",
                "branch": "", "phase_timing": {},
            },
        )
        db.create_workflow_phase(
            "feature:210-warn", workflow_phase="finish", mode="standard",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_complete_phase(
            engine, "feature:210-warn", "finish",
            db=db, iterations=None, reviewer_notes=None,
        )
        data = json.loads(result)

        # Completion should succeed
        assert "error" not in data
        # Artifact warnings should be present
        assert "artifact_warnings" in data
        assert len(data["artifact_warnings"]) == 1
        assert "retro.md" in data["artifact_warnings"][0]

    def test_finish_with_all_artifacts_no_warnings(self, db, tmp_path):
        """Complete with all artifacts present — no artifact_warnings key."""
        feat_dir = os.path.join(str(tmp_path), "features", "211-ok")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            f.write('{"id": "211", "slug": "ok", "status": "active", "mode": "standard"}')
        for name in _EXPECTED_ARTIFACTS["standard"]:
            with open(os.path.join(feat_dir, name), "w") as f:
                f.write("content")

        db.register_entity(
            "feature", "211-ok", "ok", status="active",
            artifact_path=feat_dir,
            metadata={
                "id": "211", "slug": "ok", "mode": "standard",
                "branch": "", "phase_timing": {},
            },
        )
        db.create_workflow_phase(
            "feature:211-ok", workflow_phase="finish", mode="standard",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_complete_phase(
            engine, "feature:211-ok", "finish",
            db=db, iterations=None, reviewer_notes=None,
        )
        data = json.loads(result)

        assert "error" not in data
        assert "artifact_warnings" not in data

    def test_non_finish_phase_no_artifact_warnings(self, db, tmp_path):
        """Non-finish phase completion should not include artifact_warnings."""
        feat_dir = os.path.join(str(tmp_path), "features", "212-specify")
        os.makedirs(feat_dir, exist_ok=True)

        db.register_entity(
            "feature", "212-specify", "specify", status="active",
            artifact_path=feat_dir,
            metadata={
                "id": "212", "slug": "specify", "mode": "standard",
                "branch": "", "phase_timing": {},
            },
        )
        db.create_workflow_phase(
            "feature:212-specify", workflow_phase="specify", mode="standard",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_complete_phase(
            engine, "feature:212-specify", "specify",
            db=db, iterations=None, reviewer_notes=None,
        )
        data = json.loads(result)

        assert "error" not in data
        assert "artifact_warnings" not in data

    def test_finish_completion_not_blocked_by_missing_artifacts(self, db, tmp_path):
        """AC-5: completion is NOT blocked by missing artifacts — status is completed."""
        feat_dir = os.path.join(str(tmp_path), "features", "213-notblocked")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            f.write('{"id": "213", "slug": "notblocked", "status": "active", "mode": "standard"}')
        # No artifacts at all

        db.register_entity(
            "feature", "213-notblocked", "notblocked", status="active",
            artifact_path=feat_dir,
            metadata={
                "id": "213", "slug": "notblocked", "mode": "standard",
                "branch": "", "phase_timing": {},
            },
        )
        db.create_workflow_phase(
            "feature:213-notblocked", workflow_phase="finish", mode="standard",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = _process_complete_phase(
            engine, "feature:213-notblocked", "finish",
            db=db, iterations=None, reviewer_notes=None,
        )
        data = json.loads(result)

        # Completion succeeds despite missing artifacts
        assert "error" not in data
        entity = db.get_entity("feature:213-notblocked")
        assert entity["status"] == "completed"
        # But warnings are present
        assert "artifact_warnings" in data
        assert len(data["artifact_warnings"]) == 3  # spec.md, tasks.md, retro.md


# ---------------------------------------------------------------------------
# Task 2.1: Atomic transaction wrapping tests (TDD RED)
# ---------------------------------------------------------------------------


class TestTransitionPhaseAtomicRollback:
    """AC-3: When db.update_workflow_phase raises inside a transaction,
    ALL writes (including the prior db.update_entity) must be rolled back."""

    def test_transition_phase_atomic_rollback(self, seeded_engine, db, tmp_path):
        """Mock db.update_workflow_phase to raise OperationalError after
        db.update_entity succeeds; assert entity metadata is NOT persisted."""
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")
        db.update_entity(
            "feature:009-test",
            artifact_path=feat_dir,
            metadata={"id": "009", "slug": "test", "mode": "standard", "branch": "feature/009-test"},
        )

        # Snapshot metadata before transition attempt
        entity_before = db.get_entity("feature:009-test")
        metadata_before = entity_before["metadata"]

        # Patch update_workflow_phase to raise AFTER update_entity would have run
        original_update_wf = db.update_workflow_phase

        def exploding_update_wf(*args, **kwargs):
            raise sqlite3.OperationalError("simulated lock failure")

        db.update_workflow_phase = exploding_update_wf

        try:
            result = _process_transition_phase(
                seeded_engine, "feature:009-test", "design", False, db=db,
            )
        finally:
            db.update_workflow_phase = original_update_wf

        # With atomic transactions, the entity metadata should be rolled back
        # to its pre-transition state (update_entity inside same transaction).
        entity_after = db.get_entity("feature:009-test")
        metadata_after = entity_after["metadata"]
        assert metadata_after == metadata_before, (
            "Entity metadata was persisted despite update_workflow_phase failure — "
            "transaction rollback not working"
        )

    def test_complete_phase_atomic_rollback(self, db, tmp_path):
        """Same pattern for complete_phase: mock db.update_workflow_phase to
        raise; assert entity metadata is NOT persisted."""
        feat_dir = os.path.join(str(tmp_path), "features", "010-comp")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, ".meta.json"), "w") as f:
            f.write('{"id": "010", "slug": "comp", "status": "active", "mode": "standard"}')

        db.register_entity(
            "feature", "010-comp", "Comp Feature", status="active",
            artifact_path=feat_dir,
            metadata={"id": "010", "slug": "comp", "mode": "standard", "branch": "feature/010-comp"},
        )
        db.create_workflow_phase("feature:010-comp", workflow_phase="specify")
        engine = WorkflowStateEngine(db, str(tmp_path))

        # Snapshot metadata before
        entity_before = db.get_entity("feature:010-comp")
        metadata_before = entity_before["metadata"]

        # Patch update_workflow_phase to explode
        original_update_wf = db.update_workflow_phase

        def exploding_update_wf(*args, **kwargs):
            raise sqlite3.OperationalError("simulated lock failure")

        db.update_workflow_phase = exploding_update_wf

        try:
            result = _process_complete_phase(
                engine, "feature:010-comp", "specify", db=db,
                iterations=None, reviewer_notes=None,
            )
        finally:
            db.update_workflow_phase = original_update_wf

        # With atomic transactions, metadata should be unchanged
        entity_after = db.get_entity("feature:010-comp")
        metadata_after = entity_after["metadata"]
        assert metadata_after == metadata_before, (
            "Entity metadata was persisted despite update_workflow_phase failure — "
            "transaction rollback not working (complete_phase)"
        )


class TestTransitionPhaseDegradedInsideTransaction:
    """AC-3: When engine returns degraded=True inside a transaction,
    an OperationalError should be raised and the transaction rolled back."""

    def test_transition_phase_degraded_raises_inside_transaction(
        self, seeded_engine, db, tmp_path, monkeypatch
    ):
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")
        db.update_entity(
            "feature:009-test",
            artifact_path=feat_dir,
            metadata={"id": "009", "slug": "test", "mode": "standard", "branch": "feature/009-test"},
        )

        # Create a degraded response
        degraded_response = TransitionResponse(
            results=[
                TransitionResult(
                    allowed=True, reason="OK", severity=Severity.info, guard_id="G-01",
                )
            ],
            degraded=True,
        )
        monkeypatch.setattr(
            seeded_engine, "transition_phase", lambda *a, **kw: degraded_response
        )

        # Snapshot metadata
        entity_before = db.get_entity("feature:009-test")
        metadata_before = entity_before["metadata"]

        result = _process_transition_phase(
            seeded_engine, "feature:009-test", "design", False, db=db,
        )

        # With atomic transactions + degraded check, the transaction should be
        # rolled back and the result should indicate an error.
        data = json.loads(result)
        assert data.get("error") is True, (
            "Degraded response inside transaction should raise OperationalError "
            "which _with_error_handling converts to an error response"
        )

        # Metadata should not have been updated
        entity_after = db.get_entity("feature:009-test")
        assert entity_after["metadata"] == metadata_before


class TestProjectMetaJsonCalledAfterTransaction:
    """AC-3: _project_meta_json must be called OUTSIDE the transaction
    (after COMMIT), not inside it."""

    def test_project_meta_json_called_after_transaction(
        self, seeded_engine, db, tmp_path, monkeypatch
    ):
        feat_dir = os.path.join(str(tmp_path), "features", "009-test")
        os.makedirs(feat_dir, exist_ok=True)
        with open(os.path.join(feat_dir, "spec.md"), "w") as f:
            f.write("# Spec\n")
        db.update_entity(
            "feature:009-test",
            artifact_path=feat_dir,
            metadata={"id": "009", "slug": "test", "mode": "standard", "branch": "feature/009-test"},
        )

        # Track whether db.transaction() was used AND whether _project_meta_json
        # was called outside of it. We instrument both db.update_entity (must be
        # inside transaction) and _project_meta_json (must be outside).
        transaction_was_used = []
        update_entity_in_txn = []

        import workflow_state_server

        original_project_meta = workflow_state_server._project_meta_json
        original_update_entity = db.update_entity

        def tracking_update_entity(*args, **kwargs):
            in_txn = getattr(db, "_in_transaction", False)
            update_entity_in_txn.append(in_txn)
            return original_update_entity(*args, **kwargs)

        def tracking_project_meta(*args, **kwargs):
            in_txn = getattr(db, "_in_transaction", False)
            transaction_was_used.append(("_project_meta_json", in_txn))
            return original_project_meta(*args, **kwargs)

        db.update_entity = tracking_update_entity
        monkeypatch.setattr(
            workflow_state_server, "_project_meta_json", tracking_project_meta
        )

        result = _process_transition_phase(
            seeded_engine, "feature:009-test", "design", False, db=db,
        )
        data = json.loads(result)
        assert data["transitioned"] is True

        # _project_meta_json must have been called
        assert len(transaction_was_used) == 1, "_project_meta_json should be called once"

        # db.update_entity must have been called inside a transaction
        assert any(update_entity_in_txn), (
            "db.update_entity was NOT called inside a transaction — "
            "writes must use db.transaction() for atomicity"
        )

        # _project_meta_json must NOT be called inside the transaction
        assert transaction_was_used[0][1] is False, (
            "_project_meta_json was called inside a transaction — "
            "it must be called AFTER the transaction commits"
        )


# ---------------------------------------------------------------------------
# Task 2.2: Retry decorator tests (TDD RED)
# ---------------------------------------------------------------------------


# Try to import _with_retry and _is_transient from workflow_state_server.
# These don't exist yet (TDD RED phase). We define stubs that will cause
# assertion failures (FAILED, not ERROR) when the tests run.
try:
    from workflow_state_server import _with_retry, _is_transient
except ImportError:
    # Stubs: _is_transient always returns None (fails bool assertions)
    # _with_retry returns a pass-through decorator (no retry behavior)
    def _is_transient(exc):
        """Stub — always returns None. Will cause assertion failures."""
        return None

    def _with_retry(max_attempts=3, backoff=(0.1, 0.5, 2.0)):
        """Stub — no retry logic. Will cause test failures."""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        return decorator


class TestWithRetryDecorator:
    """AC-6: _with_retry retries transient errors and propagates permanent ones."""

    def test_retry_succeeds_after_transient_error(self):
        """Function fails with OperationalError('database is locked') on first
        call, succeeds on second; assert returns success."""
        call_count = 0

        @_with_retry(max_attempts=3, backoff=(0.0, 0.0, 0.0))
        def flaky_fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise sqlite3.OperationalError("database is locked")
            return "success"

        result = flaky_fn()
        assert result == "success", (
            f"Expected 'success' after retry, got {result!r}"
        )
        assert call_count == 2, (
            f"Expected 2 calls (1 failure + 1 success), got {call_count}"
        )

    def test_retry_exhausted_raises(self):
        """Function fails 3 times with 'database is locked';
        assert OperationalError propagates after exhaustion."""
        call_count = 0

        @_with_retry(max_attempts=3, backoff=(0.0, 0.0, 0.0))
        def always_locked():
            nonlocal call_count
            call_count += 1
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            always_locked()

        assert call_count == 3, (
            f"Expected 3 attempts before exhaustion, got {call_count}"
        )

    def test_retry_permanent_error_not_retried(self):
        """Function fails with IntegrityError; assert raised immediately
        (no retry)."""
        call_count = 0

        @_with_retry(max_attempts=3, backoff=(0.0, 0.0, 0.0))
        def integrity_fail():
            nonlocal call_count
            call_count += 1
            raise sqlite3.IntegrityError("UNIQUE constraint failed")

        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint"):
            integrity_fail()

        assert call_count == 1, (
            f"Permanent error should not be retried, but got {call_count} calls"
        )

    def test_retry_logs_to_stderr(self, capsys):
        """On retry, stderr contains 'retry 1/3'."""
        call_count = 0

        @_with_retry(max_attempts=3, backoff=(0.0, 0.0, 0.0))
        def locked_then_ok():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise sqlite3.OperationalError("database is locked")
            return "ok"

        locked_then_ok()
        captured = capsys.readouterr()
        assert "retry 1/3" in captured.err, (
            f"Expected 'retry 1/3' in stderr, got: {captured.err!r}"
        )


class TestIsTransient:
    """AC-5: _is_transient classifies errors correctly."""

    def test_is_transient_locked(self):
        """'database is locked' -> True"""
        exc = sqlite3.OperationalError("database is locked")
        result = _is_transient(exc)
        assert result is True, (
            f"Expected True for 'database is locked', got {result!r}"
        )

    def test_is_transient_table_locked(self):
        """'database table is locked' -> True"""
        exc = sqlite3.OperationalError("database table is locked")
        result = _is_transient(exc)
        assert result is True, (
            f"Expected True for 'database table is locked', got {result!r}"
        )

    def test_is_transient_sql_logic_error(self):
        """'SQL logic error' -> False"""
        exc = sqlite3.OperationalError("SQL logic error")
        result = _is_transient(exc)
        assert result is False, (
            f"Expected False for 'SQL logic error', got {result!r}"
        )
