"""Tests for WorkflowStateEngine -- Phases 1-8."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from entity_registry.database import EntityDatabase
from transition_gate import PHASE_SEQUENCE
from transition_gate.constants import COMMAND_PHASES, HARD_PREREQUISITES

from transition_gate.models import Severity, TransitionResult

from workflow_engine import FeatureWorkflowState, WorkflowStateEngine
from workflow_engine.models import TransitionResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> EntityDatabase:
    """Create an in-memory EntityDatabase."""
    return EntityDatabase(":memory:")


def _register_feature(
    db: EntityDatabase,
    slug: str = "008-test-feature",
    status: str | None = "active",
) -> str:
    """Register a feature entity and return the type_id."""
    type_id = f"feature:{slug}"
    db.register_entity(
        entity_type="feature",
        entity_id=slug,
        name=f"Test Feature {slug}",
        status=status,
        project_id="__unknown__",
    )
    return type_id


def _create_meta_json(
    tmp_path,
    slug: str = "008-test-feature",
    *,
    status: str = "active",
    mode: str | None = "standard",
    last_completed_phase: str | None = None,
) -> None:
    """Create a .meta.json file in the expected location."""
    feature_dir = tmp_path / "features" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": slug.split("-", 1)[0],
        "slug": slug,
        "status": status,
        "mode": mode,
        "lastCompletedPhase": last_completed_phase,
        "phases": {},
    }
    (feature_dir / ".meta.json").write_text(json.dumps(meta))


def _setup_engine(
    tmp_path,
    slug: str = "008-test-feature",
    *,
    status: str = "active",
    workflow_phase: str | None = None,
    last_completed_phase: str | None = None,
    mode: str | None = "standard",
    create_wp: bool = True,
) -> tuple[WorkflowStateEngine, EntityDatabase, str]:
    """Full setup: DB + entity + workflow_phase row + engine."""
    db = _make_db()
    type_id = _register_feature(db, slug, status=status)
    if create_wp:
        db.create_workflow_phase(
            type_id,
            workflow_phase=workflow_phase,
            last_completed_phase=last_completed_phase,
            mode=mode,
        )
    engine = WorkflowStateEngine(db, str(tmp_path))
    return engine, db, type_id


# ===========================================================================
# Phase 1: Models
# ===========================================================================


class TestModels:
    """Task 1.2/1.3: FeatureWorkflowState frozen dataclass tests."""

    def test_frozen_attribute_raises(self) -> None:
        state = FeatureWorkflowState(
            feature_type_id="feature:001-test",
            current_phase="specify",
            last_completed_phase="brainstorm",
            completed_phases=("brainstorm",),
            mode="standard",
            source="db",
        )
        with pytest.raises(FrozenInstanceError):
            state.current_phase = "design"  # type: ignore[misc]

    def test_completed_phases_tuple_immutable(self) -> None:
        state = FeatureWorkflowState(
            feature_type_id="feature:001-test",
            current_phase="specify",
            last_completed_phase="brainstorm",
            completed_phases=("brainstorm",),
            mode="standard",
            source="db",
        )
        # Tuple is immutable -- cannot append or modify
        assert isinstance(state.completed_phases, tuple)
        with pytest.raises(AttributeError):
            state.completed_phases.append("specify")  # type: ignore[attr-defined]


# ===========================================================================
# Phase 2: Private Helpers
# ===========================================================================


class TestHelpers:
    """Tasks 2.1-2.8: Private helper tests."""

    # -- _extract_slug (2.1/2.2) --

    def test_extract_slug_valid(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        assert engine._extract_slug("feature:008-foo") == "008-foo"

    def test_extract_slug_missing_colon(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        with pytest.raises(ValueError, match="missing ':'"):
            engine._extract_slug("feature-008-foo")

    def test_extract_slug_empty(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        with pytest.raises(ValueError, match="empty slug"):
            engine._extract_slug("feature:")

    # -- _derive_completed_phases (2.3/2.4) --

    def test_derive_completed_phases_none(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        assert engine._derive_completed_phases(None) == ()

    def test_derive_completed_phases_specify(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        result = engine._derive_completed_phases("specify")
        assert result == ("brainstorm", "specify")

    def test_derive_completed_phases_finish(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        result = engine._derive_completed_phases("finish")
        expected = tuple(p.value for p in PHASE_SEQUENCE)
        assert result == expected
        assert len(result) == 6

    def test_derive_completed_phases_unknown(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        with pytest.raises(ValueError, match="Unknown phase"):
            engine._derive_completed_phases("nonexistent")

    # -- _next_phase_value (2.5/2.6) --

    def test_next_phase_value_specify_to_design(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        assert engine._next_phase_value("specify") == "design"

    def test_next_phase_value_finish_returns_none(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        assert engine._next_phase_value("finish") is None

    def test_next_phase_value_unknown(self) -> None:
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        with pytest.raises(ValueError, match="Unknown phase"):
            engine._next_phase_value("nonexistent")

    # -- _get_existing_artifacts (2.7/2.8) --

    def test_hard_prerequisites_import(self) -> None:
        """Verify HARD_PREREQUISITES is importable and is a dict."""
        assert isinstance(HARD_PREREQUISITES, dict)

    def test_get_existing_artifacts_some_present(self, tmp_path) -> None:
        feature_dir = tmp_path / "features" / "008-foo"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# Spec")
        (feature_dir / "design.md").write_text("# Design")

        engine = WorkflowStateEngine(_make_db(), str(tmp_path))
        result = engine._get_existing_artifacts("008-foo")
        assert "spec.md" in result
        assert "design.md" in result
        assert "plan.md" not in result

    def test_get_existing_artifacts_none_present(self, tmp_path) -> None:
        feature_dir = tmp_path / "features" / "008-foo"
        feature_dir.mkdir(parents=True)

        engine = WorkflowStateEngine(_make_db(), str(tmp_path))
        result = engine._get_existing_artifacts("008-foo")
        assert result == []

    def test_get_existing_artifacts_all_present(self, tmp_path) -> None:
        feature_dir = tmp_path / "features" / "008-foo"
        feature_dir.mkdir(parents=True)

        # Create all artifacts from HARD_PREREQUISITES
        all_artifacts: set[str] = set()
        for artifacts_list in HARD_PREREQUISITES.values():
            all_artifacts.update(artifacts_list)

        for name in all_artifacts:
            (feature_dir / name).write_text(f"# {name}")

        engine = WorkflowStateEngine(_make_db(), str(tmp_path))
        result = engine._get_existing_artifacts("008-foo")
        assert set(result) == all_artifacts

    # -- Guard IDs in gate evaluation (2.9) --

    def test_guard_ids_in_gate_results(self, tmp_path) -> None:
        """Guard IDs G-18, G-08, G-23, G-22 appear in gate evaluation results."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        state = engine.get_state(type_id)
        assert state is not None
        results = engine._evaluate_gates(
            state, "design", [], yolo_active=False
        )
        guard_ids = {r.guard_id for r in results}
        assert "G-18" in guard_ids
        assert "G-08" in guard_ids
        assert "G-23" in guard_ids
        assert "G-22" in guard_ids


# ===========================================================================
# Phase 3: State Reading + Hydration
# ===========================================================================


class TestHydration:
    """Tasks 3.1/3.2: _hydrate_from_meta_json tests."""

    def test_hydrate_active_status(self, tmp_path) -> None:
        db = _make_db()
        type_id = _register_feature(db, "008-active")
        _create_meta_json(
            tmp_path,
            "008-active",
            status="active",
            last_completed_phase="design",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)

        assert state is not None
        assert state.source == "meta_json"
        assert state.current_phase == "create-plan"  # next after design
        assert state.last_completed_phase == "design"
        assert state.completed_phases == ("brainstorm", "specify", "design")

    def test_hydrate_completed_status(self, tmp_path) -> None:
        db = _make_db()
        type_id = _register_feature(db, "008-done")
        _create_meta_json(
            tmp_path,
            "008-done",
            status="completed",
            last_completed_phase="implement",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)

        assert state is not None
        assert state.current_phase == "finish"
        assert state.source == "meta_json"

    def test_hydrate_planned_status(self, tmp_path) -> None:
        db = _make_db()
        type_id = _register_feature(db, "008-planned")
        _create_meta_json(
            tmp_path,
            "008-planned",
            status="planned",
            last_completed_phase="specify",  # stale data
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)

        assert state is not None
        assert state.current_phase is None
        assert state.last_completed_phase is None
        assert state.completed_phases == ()

    def test_hydrate_unknown_status(self, tmp_path) -> None:
        db = _make_db()
        type_id = _register_feature(db, "008-abandoned")
        _create_meta_json(
            tmp_path,
            "008-abandoned",
            status="abandoned",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)

        assert state is not None
        assert state.current_phase is None
        assert state.last_completed_phase is None

    def test_hydrate_missing_entity(self, tmp_path) -> None:
        db = _make_db()
        _create_meta_json(tmp_path, "008-noentity")
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json("feature:008-noentity")
        assert state is None

    def test_hydrate_missing_meta_json(self, tmp_path) -> None:
        db = _make_db()
        type_id = _register_feature(db, "008-nometa")
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)
        assert state is None

    def test_hydrate_malformed_meta_json(self, tmp_path) -> None:
        db = _make_db()
        type_id = _register_feature(db, "008-bad")
        _create_meta_json(
            tmp_path,
            "008-bad",
            status="active",
            last_completed_phase="invalid-phase",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)
        assert state is None

    def test_hydrate_concurrent_race(self, tmp_path) -> None:
        """ValueError 'already exists' -> fallback to get_workflow_phase."""
        db = _make_db()
        type_id = _register_feature(db, "008-race")
        _create_meta_json(
            tmp_path,
            "008-race",
            status="active",
            last_completed_phase="specify",
        )

        # Pre-create the workflow phase to simulate a race
        db.create_workflow_phase(
            type_id,
            workflow_phase="design",
            last_completed_phase="specify",
            mode="standard",
        )

        engine = WorkflowStateEngine(db, str(tmp_path))
        state = engine._hydrate_from_meta_json(type_id)

        assert state is not None
        assert state.source == "meta_json"
        # Should fallback to get and get the existing row's data
        assert state.current_phase == "design"

    def test_hydrate_active_finished_edge(self, tmp_path) -> None:
        """Active + lastCompletedPhase='finish' -> workflow_phase='finish'."""
        db = _make_db()
        type_id = _register_feature(db, "008-edge")
        _create_meta_json(
            tmp_path,
            "008-edge",
            status="active",
            last_completed_phase="finish",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)

        assert state is not None
        assert state.current_phase == "finish"

    def test_hydrate_active_no_completed_phase(self, tmp_path) -> None:
        """Active + lastCompletedPhase=None -> workflow_phase=PHASE_SEQUENCE[0]."""
        db = _make_db()
        type_id = _register_feature(db, "008-new")
        _create_meta_json(
            tmp_path,
            "008-new",
            status="active",
            last_completed_phase=None,
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine._hydrate_from_meta_json(type_id)

        assert state is not None
        assert state.current_phase == PHASE_SEQUENCE[0].value  # "brainstorm"
        assert state.last_completed_phase is None
        assert state.completed_phases == ()


class TestGetState:
    """Tasks 3.3/3.4: get_state tests."""

    def test_get_state_db_row_exists(self, tmp_path) -> None:
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )

        state = engine.get_state(type_id)

        assert state is not None
        assert state.source == "db"
        assert state.current_phase == "design"
        assert state.last_completed_phase == "specify"
        assert state.completed_phases == ("brainstorm", "specify")

    def test_get_state_db_missing_meta_exists(self, tmp_path) -> None:
        """SC-4 + SC-9: fallback to .meta.json, source='meta_json'."""
        db = _make_db()
        type_id = _register_feature(db, "008-fallback")
        _create_meta_json(
            tmp_path,
            "008-fallback",
            status="active",
            last_completed_phase="design",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine.get_state(type_id)

        assert state is not None
        assert state.source == "meta_json"
        assert state.current_phase == "create-plan"

    def test_get_state_both_missing_returns_none(self, tmp_path) -> None:
        db = _make_db()
        type_id = _register_feature(db, "008-empty")
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine.get_state(type_id)
        assert state is None

    def test_get_state_missing_feature_returns_none(self, tmp_path) -> None:
        """Entity not registered, no .meta.json -> returns None."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        state = engine.get_state("feature:999-nonexistent")
        assert state is None


# ===========================================================================
# Phase 4: Gate Evaluation
# ===========================================================================


class TestGateEvaluation:
    """Tasks 4.1/4.2: _evaluate_gates tests."""

    def test_gate_order_all_applicable(self, tmp_path) -> None:
        """All 4 gates run when last_completed_phase and current_phase are set."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        state = engine.get_state(type_id)
        assert state is not None

        results = engine._evaluate_gates(
            state, "create-plan", ["spec.md", "design.md"], yolo_active=False
        )

        # Should have 4 results: backward, hard, soft, validate
        assert len(results) == 4
        guard_ids = [r.guard_id for r in results]
        assert guard_ids[0] == "G-18"  # backward
        assert guard_ids[1] == "G-08"  # hard prereq
        assert guard_ids[2] == "G-23"  # soft prereq
        assert guard_ids[3] == "G-22"  # validate

    def test_skip_backward_when_last_completed_none(self, tmp_path) -> None:
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="brainstorm",
            last_completed_phase=None,
        )
        state = engine.get_state(type_id)
        assert state is not None

        results = engine._evaluate_gates(
            state, "brainstorm", [], yolo_active=False
        )

        # backward gate skipped, validate gate NOT skipped (current_phase is set)
        guard_ids = [r.guard_id for r in results]
        assert "G-18" not in guard_ids
        assert "G-08" in guard_ids
        assert "G-23" in guard_ids
        assert "G-22" in guard_ids

    def test_skip_validate_when_current_phase_none(self, tmp_path) -> None:
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase=None,
            last_completed_phase="specify",
        )
        state = engine.get_state(type_id)
        assert state is not None

        results = engine._evaluate_gates(
            state, "design", ["spec.md"], yolo_active=False
        )

        guard_ids = [r.guard_id for r in results]
        assert "G-22" not in guard_ids  # validate skipped
        assert "G-18" in guard_ids  # backward runs
        assert "G-08" in guard_ids
        assert "G-23" in guard_ids

    def test_yolo_overrides_soft_gates(self, tmp_path) -> None:
        """G-18/G-22/G-23 have yolo_behavior=auto_select, should get overridden."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        state = engine.get_state(type_id)
        assert state is not None

        results = engine._evaluate_gates(
            state, "create-plan", ["spec.md", "design.md"], yolo_active=True
        )

        # G-18, G-23, G-22 should be overridden (auto_select -> warn override)
        # G-08 has yolo_behavior=unchanged -> runs normally
        for r in results:
            if r.guard_id in ("G-18", "G-23", "G-22"):
                assert "YOLO" in r.reason or r.allowed is True
            if r.guard_id == "G-08":
                assert "YOLO" not in r.reason

    def test_yolo_does_not_override_hard_gate(self, tmp_path) -> None:
        """G-08 has yolo_behavior=unchanged, should NOT be overridden."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        state = engine.get_state(type_id)
        assert state is not None

        # Missing design.md -- hard prereq should fail even with YOLO
        results = engine._evaluate_gates(
            state, "create-plan", ["spec.md"], yolo_active=True
        )

        hard_result = [r for r in results if r.guard_id == "G-08"][0]
        assert hard_result.allowed is False
        assert "YOLO" not in hard_result.reason


# ===========================================================================
# Phase 5: Transition + Complete
# ===========================================================================


class TestTransitionPhase:
    """Tasks 5.1/5.2: transition_phase tests."""

    def test_forward_transition_success(self, tmp_path) -> None:
        """SC-1 partial: forward transition updates DB."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # Create required artifacts for design
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        results = engine.transition_phase(type_id, "design").results

        assert all(r.allowed for r in results)
        # Verify DB was updated
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["workflow_phase"] == "design"

    def test_blocked_missing_prerequisites(self, tmp_path) -> None:
        """SC-2: missing hard prereqs blocks transition."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # No spec.md created -- design requires it

        results = engine.transition_phase(type_id, "design").results

        blocked = [r for r in results if not r.allowed]
        assert len(blocked) > 0
        assert any(r.guard_id == "G-08" for r in blocked)
        # DB should NOT be updated
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["workflow_phase"] == "specify"

    def test_backward_transition_warning(self, tmp_path) -> None:
        """SC-3: backward transition warns but allows."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="design",
        )

        results = engine.transition_phase(type_id, "specify").results

        # Should have a G-18 warning but all allowed
        g18 = [r for r in results if r.guard_id == "G-18"]
        assert len(g18) == 1
        assert g18[0].allowed is True
        assert g18[0].severity.value == "warn"

    def test_yolo_mode_passthrough(self, tmp_path) -> None:
        """SC-8: YOLO overrides soft gates."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        results = engine.transition_phase(type_id, "design", yolo_active=True).results

        # With YOLO, soft gates should be overridden
        yolo_results = [r for r in results if "YOLO" in r.reason]
        assert len(yolo_results) > 0

    def test_missing_feature_raises_valueerror(self, tmp_path) -> None:
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        with pytest.raises(ValueError, match="Feature not found"):
            engine.transition_phase("feature:999-nonexistent", "specify")


class TestCompletePhase:
    """Tasks 5.3/5.4: complete_phase tests."""

    def test_normal_completion_advances(self, tmp_path) -> None:
        """SC-5: completing specify -> workflow_phase becomes design."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )

        state = engine.complete_phase(type_id, "specify")

        assert state.current_phase == "design"
        assert state.last_completed_phase == "specify"
        assert "specify" in state.completed_phases

    def test_terminal_phase_finish(self, tmp_path) -> None:
        """TD-8: finishing 'finish' keeps workflow_phase='finish', not None."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="finish",
            last_completed_phase="implement",
        )

        state = engine.complete_phase(type_id, "finish")

        assert state.current_phase == "finish"
        assert state.last_completed_phase == "finish"

    def test_backward_rerun_resets(self, tmp_path) -> None:
        """TD-6: backward re-run resets progress."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="create-plan",
            last_completed_phase="design",
        )

        state = engine.complete_phase(type_id, "specify")

        assert state.last_completed_phase == "specify"
        assert state.current_phase == "design"
        assert state.completed_phases == ("brainstorm", "specify")

    def test_phase_mismatch_raises_valueerror(self, tmp_path) -> None:
        """Phase does not match current and is not backward."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )

        with pytest.raises(ValueError, match="Phase mismatch"):
            engine.complete_phase(type_id, "design")

    def test_missing_feature_raises_valueerror(self, tmp_path) -> None:
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        with pytest.raises(ValueError, match="Feature not found"):
            engine.complete_phase("feature:999-nonexistent", "specify")

    def test_no_active_phase_raises_valueerror(self, tmp_path) -> None:
        """current_phase=None -> cannot complete."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase=None,
            last_completed_phase=None,
        )

        with pytest.raises(ValueError, match="no active phase"):
            engine.complete_phase(type_id, "specify")

    def test_phase_mismatch_no_last_completed(self, tmp_path) -> None:
        """phase != current_phase AND last_completed_phase=None -> ValueError."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="brainstorm",
            last_completed_phase=None,
        )

        with pytest.raises(ValueError, match="no phases completed yet"):
            engine.complete_phase(type_id, "specify")


# ===========================================================================
# Phase 6: Query + Validate
# ===========================================================================


class TestValidatePrerequisites:
    """Tasks 6.1/6.2: validate_prerequisites tests."""

    def test_returns_same_results_as_transition(self, tmp_path) -> None:
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        validate_results = engine.validate_prerequisites(type_id, "design")
        response = engine.transition_phase(type_id, "design")
        transition_results = response.results

        # Same gate evaluation logic -- same results
        assert len(validate_results) == len(transition_results)
        for v, t in zip(validate_results, transition_results):
            assert v.guard_id == t.guard_id
            assert v.allowed == t.allowed

    def test_no_db_write(self, tmp_path) -> None:
        """SC-6: validate does not update workflow_phase."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        engine.validate_prerequisites(type_id, "design")

        # workflow_phase should still be "specify"
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["workflow_phase"] == "specify"

    def test_missing_feature_raises_valueerror(self, tmp_path) -> None:
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        with pytest.raises(ValueError, match="Feature not found"):
            engine.validate_prerequisites("feature:999-nonexistent", "design")


class TestBatchQueries:
    """Tasks 6.3-6.6: list_by_phase and list_by_status tests."""

    # -- list_by_phase (6.3/6.4) --

    def test_list_by_phase_matches(self, tmp_path) -> None:
        db = _make_db()
        # Create 3 features in different phases
        for i, phase in enumerate(["design", "design", "implement"]):
            slug = f"00{i}-feat"
            tid = _register_feature(db, slug)
            db.create_workflow_phase(tid, workflow_phase=phase)

        engine = WorkflowStateEngine(db, str(tmp_path))
        results = engine.list_by_phase("design")

        assert len(results) == 2
        assert all(r.current_phase == "design" for r in results)
        assert all(r.source == "db" for r in results)

    def test_list_by_phase_empty(self, tmp_path) -> None:
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        results = engine.list_by_phase("design")
        assert results == []

    # -- list_by_status (6.5/6.6) --

    def test_list_by_status_matches(self, tmp_path) -> None:
        db = _make_db()
        tid1 = _register_feature(db, "001-active", status="active")
        db.create_workflow_phase(tid1, workflow_phase="design")
        tid2 = _register_feature(db, "002-active", status="active")
        db.create_workflow_phase(tid2, workflow_phase="specify")
        _register_feature(db, "003-completed", status="completed")

        engine = WorkflowStateEngine(db, str(tmp_path))
        results = engine.list_by_status("active")

        assert len(results) == 2
        type_ids = {r.feature_type_id for r in results}
        assert tid1 in type_ids
        assert tid2 in type_ids

    def test_list_by_status_none_excluded(self, tmp_path) -> None:
        """Entities with status=None should not match any status query."""
        db = _make_db()
        _register_feature(db, "001-nostat", status=None)

        engine = WorkflowStateEngine(db, str(tmp_path))
        results = engine.list_by_status("active")

        assert results == []

    def test_list_by_status_no_workflow_row(self, tmp_path) -> None:
        """SC-7: features without workflow_phases row included with current_phase=None."""
        db = _make_db()
        tid = _register_feature(db, "001-nowp", status="active")
        # Deliberately NOT creating workflow_phase row

        engine = WorkflowStateEngine(db, str(tmp_path))
        results = engine.list_by_status("active")

        assert len(results) == 1
        assert results[0].feature_type_id == tid
        assert results[0].current_phase is None
        assert results[0].completed_phases == ()
        assert results[0].source == "db"


# ===========================================================================
# Phase 7: Integration Tests
# ===========================================================================

# Artifact produced by each phase (used for creating files after completion).
# Artifacts produced by each phase (used for creating files after completion).
# create-plan produces both plan.md and tasks.md (create-tasks merged in 073).
_PHASE_ARTIFACTS: dict[str, list[str]] = {
    "specify": ["spec.md"],
    "design": ["design.md"],
    "create-plan": ["plan.md", "tasks.md"],
}


class TestIntegration:
    """Tasks 7.1a/7.1b/7.2/7.3: Full lifecycle integration tests."""

    # -- Task 7.1a + 7.1b: Full lifecycle all 6 command phases (SC-1) --

    def test_full_lifecycle_all_6_phases(self, tmp_path) -> None:
        """SC-1: transition + complete through all 6 command phases.

        Setup (7.1a): EntityDatabase(:memory:), tmp_path for artifacts,
        register entity, create .meta.json, get_state -> source='meta_json'.

        Lifecycle (7.1b): For each command phase: transition_phase() +
        create required artifact + complete_phase().
        """
        # --- 7.1a: Setup ---
        db = EntityDatabase(":memory:")
        slug = "008-lifecycle-test"
        type_id = f"feature:{slug}"
        db.register_entity(
            entity_type="feature",
            entity_id=slug,
            name="Lifecycle Test Feature",
            status="active",
            project_id="__unknown__",
        )

        # Create .meta.json (active, no completed phases)
        feature_dir = tmp_path / "features" / slug
        feature_dir.mkdir(parents=True)
        meta = {
            "id": "008",
            "slug": slug,
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": None,
            "phases": {},
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))

        engine = WorkflowStateEngine(db, str(tmp_path))

        # get_state triggers hydration from .meta.json
        state = engine.get_state(type_id)
        assert state is not None
        assert state.source == "meta_json"
        assert state.current_phase == PHASE_SEQUENCE[0].value  # "brainstorm"
        assert state.last_completed_phase is None

        # --- 7.1b: Lifecycle through 6 command phases ---
        # First, complete brainstorm to move to specify
        # (brainstorm is not a command phase but needs to be completed)
        # The hydrated state has current_phase="brainstorm", so complete it
        state = engine.complete_phase(type_id, "brainstorm")
        assert state.current_phase == "specify"
        assert state.last_completed_phase == "brainstorm"

        # Now iterate through all 6 command phases
        command_phase_values = [p.value for p in COMMAND_PHASES]
        for phase_value in command_phase_values:
            # Transition into the phase
            results = engine.transition_phase(type_id, phase_value).results
            assert all(r.allowed for r in results), (
                f"Transition to {phase_value} blocked: "
                + str([r for r in results if not r.allowed])
            )

            # Verify DB reflects the transition
            row = db.get_workflow_phase(type_id)
            assert row is not None
            assert row["workflow_phase"] == phase_value

            # Complete the phase
            state = engine.complete_phase(type_id, phase_value)

            # Create artifact produced by this phase (if any)
            for artifact in _PHASE_ARTIFACTS.get(phase_value, []):
                (feature_dir / artifact).write_text(f"# {phase_value}")

        # Verify final state
        assert state.last_completed_phase == "finish"
        assert state.current_phase == "finish"  # TD-8: terminal stays "finish"
        assert state.completed_phases == tuple(p.value for p in PHASE_SEQUENCE)

    # -- Task 7.2: All 5 consumed gates exercised (SC-10) --

    def test_all_5_consumed_gates_exercised(self, tmp_path) -> None:
        """SC-10: Verify all 5 engine-consumed gates are invoked.

        Patches all 5 gate functions at engine module namespace with
        side_effect=original_fn so calls are tracked but execute normally.
        Runs a lifecycle with yolo_active=True on first transition to
        exercise check_yolo_override.
        """
        import workflow_engine.engine as engine_mod

        # Save originals
        orig_backward = engine_mod.check_backward_transition
        orig_hard = engine_mod.check_hard_prerequisites
        orig_soft = engine_mod.check_soft_prerequisites
        orig_validate = engine_mod.validate_transition
        orig_yolo = engine_mod.check_yolo_override

        db = EntityDatabase(":memory:")
        slug = "008-gate-coverage"
        type_id = f"feature:{slug}"
        db.register_entity(
            entity_type="feature",
            entity_id=slug,
            name="Gate Coverage Test",
            status="active",
            project_id="__unknown__",
        )

        feature_dir = tmp_path / "features" / slug
        feature_dir.mkdir(parents=True)

        with (
            patch.object(
                engine_mod,
                "check_backward_transition",
                side_effect=orig_backward,
            ) as mock_backward,
            patch.object(
                engine_mod,
                "check_hard_prerequisites",
                side_effect=orig_hard,
            ) as mock_hard,
            patch.object(
                engine_mod,
                "check_soft_prerequisites",
                side_effect=orig_soft,
            ) as mock_soft,
            patch.object(
                engine_mod,
                "validate_transition",
                side_effect=orig_validate,
            ) as mock_validate,
            patch.object(
                engine_mod,
                "check_yolo_override",
                side_effect=orig_yolo,
            ) as mock_yolo,
        ):
            engine = WorkflowStateEngine(db, str(tmp_path))

            # Set up initial state: brainstorm completed, in specify
            db.create_workflow_phase(
                type_id,
                workflow_phase="specify",
                last_completed_phase="brainstorm",
                mode="standard",
            )

            # First transition with yolo_active=True to exercise check_yolo_override
            results = engine.transition_phase(
                type_id, "specify", yolo_active=True
            ).results
            assert all(r.allowed for r in results)

            # Complete specify, create artifact
            engine.complete_phase(type_id, "specify")
            (feature_dir / "spec.md").write_text("# Spec")

            # Transition to design (normal, not YOLO) to exercise
            # backward + hard + soft + validate gates
            results = engine.transition_phase(type_id, "design").results
            assert all(r.allowed for r in results)

            # Assert all 5 gates were called at least once
            assert mock_backward.call_count >= 1, (
                "check_backward_transition not called"
            )
            assert mock_hard.call_count >= 1, (
                "check_hard_prerequisites not called"
            )
            assert mock_soft.call_count >= 1, (
                "check_soft_prerequisites not called"
            )
            assert mock_validate.call_count >= 1, (
                "validate_transition not called"
            )
            assert mock_yolo.call_count >= 1, (
                "check_yolo_override not called"
            )

    # -- Task 7.3: Hydration then transition (SC-4 + SC-9) --

    def test_hydration_then_transition(self, tmp_path) -> None:
        """SC-4 + SC-9: .meta.json hydration then successful transition.

        Feature has .meta.json with lastCompletedPhase='design' but no DB
        row. get_state hydrates (source='meta_json'). Then transition to
        implement succeeds using hydrated state.
        """
        db = EntityDatabase(":memory:")
        slug = "008-hydrate-transition"
        type_id = f"feature:{slug}"
        db.register_entity(
            entity_type="feature",
            entity_id=slug,
            name="Hydration Transition Test",
            status="active",
            project_id="__unknown__",
        )

        # Create .meta.json with design completed
        feature_dir = tmp_path / "features" / slug
        feature_dir.mkdir(parents=True)
        meta = {
            "id": "008",
            "slug": slug,
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": "design",
            "phases": {},
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))

        # Create required artifacts for create-plan (next phase after design)
        (feature_dir / "spec.md").write_text("# Spec")
        (feature_dir / "design.md").write_text("# Design")

        engine = WorkflowStateEngine(db, str(tmp_path))

        # get_state should hydrate from .meta.json
        state = engine.get_state(type_id)
        assert state is not None
        assert state.source == "meta_json"
        assert state.current_phase == "create-plan"
        assert state.last_completed_phase == "design"

        # Transition should succeed using the hydrated state
        results = engine.transition_phase(type_id, "create-plan").results
        assert all(r.allowed for r in results)

        # Verify the DB was updated
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["workflow_phase"] == "create-plan"

        # Now get_state should return source="db" (row exists)
        state = engine.get_state(type_id)
        assert state is not None
        assert state.source == "db"


# ===========================================================================
# Phase 8: Deepened Tests (test-deepener)
# ===========================================================================


class TestDeepenedBoundaryValues:
    """Boundary value and equivalence partitioning tests.

    Dimension 2: Tests boundary conditions not covered by existing TDD suite.
    """

    # -- _derive_completed_phases boundary: first phase (brainstorm) --

    def test_derive_completed_phases_first_phase_brainstorm(self) -> None:
        """BVA: first phase returns only that phase in completed tuple.

        Anticipate: Off-by-one in slicing could return empty or include next.
        derived_from: dimension:boundary_values (BVA min)
        """
        # Given the first phase in the sequence (brainstorm)
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        # When deriving completed phases for the first phase
        result = engine._derive_completed_phases("brainstorm")
        # Then only brainstorm is in the completed tuple
        assert result == ("brainstorm",)
        assert len(result) == 1

    # -- _extract_slug boundary: multiple colons --

    def test_extract_slug_multiple_colons_returns_full_slug(self) -> None:
        """BVA: slug with embedded colons preserves everything after first colon.

        Anticipate: Using split() without maxsplit=1 would drop parts after second colon.
        derived_from: dimension:boundary_values (string edge)
        """
        # Given a type_id with multiple colons
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        # When extracting the slug
        result = engine._extract_slug("feature:008-foo:bar:baz")
        # Then everything after first colon is returned
        assert result == "008-foo:bar:baz"

    # -- list_by_status empty results --

    def test_list_by_status_no_entities_returns_empty(self, tmp_path) -> None:
        """BVA: empty DB returns empty list for list_by_status.

        Anticipate: Missing guard on empty entity list could raise.
        derived_from: dimension:boundary_values (empty collection)
        """
        # Given an empty database
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        # When querying by status
        results = engine.list_by_status("active")
        # Then empty list is returned
        assert results == []

    # -- _get_existing_artifacts when feature dir doesn't exist --

    def test_get_existing_artifacts_missing_dir_returns_empty(self, tmp_path) -> None:
        """BVA: non-existent feature dir returns empty list (not error).

        Anticipate: os.path.exists on children of missing dir could raise or
        the sorted() comprehension could fail.
        derived_from: dimension:boundary_values (empty/missing)
        """
        # Given a feature slug whose directory does not exist
        engine = WorkflowStateEngine(_make_db(), str(tmp_path))
        # When checking artifacts
        result = engine._get_existing_artifacts("999-nonexistent")
        # Then empty list is returned (no error)
        assert result == []

    # -- _derive_completed_phases boundary: second phase (specify) --

    def test_derive_completed_phases_second_phase_includes_first(self) -> None:
        """BVA: second phase returns first two phases in order.

        Anticipate: Off-by-one in idx+1 slicing could miss first or include third.
        derived_from: dimension:boundary_values (BVA min+1)
        """
        # Given the second phase (specify)
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        # When deriving completed phases
        result = engine._derive_completed_phases("specify")
        # Then brainstorm and specify are included in order
        assert result == ("brainstorm", "specify")
        assert len(result) == 2

    # -- _next_phase_value boundary: second-to-last phase --

    def test_next_phase_value_second_to_last_returns_finish(self) -> None:
        """BVA: implement (second-to-last) returns finish (last).

        Anticipate: Off-by-one in idx >= len-1 check could wrongly return None.
        derived_from: dimension:boundary_values (BVA max-1)
        """
        # Given the second-to-last phase (implement)
        engine = WorkflowStateEngine(_make_db(), "/tmp")
        # When getting next phase
        result = engine._next_phase_value("implement")
        # Then finish is returned
        assert result == "finish"

    # -- list_by_phase with many features, only one matches --

    def test_list_by_phase_single_match_among_many(self, tmp_path) -> None:
        """BVA: one-of-many match returns exactly one result.

        Anticipate: Filtering bug could return all or none.
        derived_from: dimension:boundary_values (collection single element)
        """
        # Given 5 features in various phases, only 1 in "implement"
        db = _make_db()
        for i, phase in enumerate(
            ["design", "design", "specify", "implement", "finish"]
        ):
            slug = f"00{i}-feat"
            tid = _register_feature(db, slug)
            db.create_workflow_phase(tid, workflow_phase=phase)

        engine = WorkflowStateEngine(db, str(tmp_path))
        # When listing by phase "implement"
        results = engine.list_by_phase("implement")
        # Then exactly one result
        assert len(results) == 1
        assert results[0].current_phase == "implement"


class TestDeepenedAdversarial:
    """Adversarial and negative testing.

    Dimension 3: Edge cases that could reveal hidden bugs.
    """

    def test_transition_to_unknown_phase_gate_returns_invalid(self, tmp_path) -> None:
        """Adversarial: transitioning to a nonexistent phase name.

        Anticipate: _evaluate_gates passes unknown phase to gate functions which
        should return INVALID results, not crash.
        derived_from: dimension:adversarial (wrong data type/logically invalid)
        """
        # Given a feature at specify
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # When transitioning to an invalid phase
        response = engine.transition_phase(type_id, "nonexistent-phase")
        results = response.results
        # Then at least one gate blocks with INVALID guard_id
        blocked = [r for r in results if not r.allowed]
        assert len(blocked) > 0

    def test_complete_unknown_phase_raises_valueerror(self, tmp_path) -> None:
        """Adversarial: completing a nonexistent phase name raises ValueError.

        Anticipate: Missing validation on phase name could lead to index errors.
        derived_from: dimension:adversarial (wrong data)
        """
        # Given a feature at specify
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # When completing an unknown phase
        with pytest.raises(ValueError, match="Unknown phase"):
            engine.complete_phase(type_id, "nonexistent-phase")

    def test_hydrate_meta_json_with_corrupt_json(self, tmp_path) -> None:
        """Adversarial: .meta.json contains invalid JSON.

        Engine catches JSONDecodeError and returns None (graceful fallback).
        derived_from: dimension:adversarial (starve/corrupt input)
        """
        # Given corrupt .meta.json
        db = _make_db()
        type_id = _register_feature(db, "008-corrupt")
        feature_dir = tmp_path / "features" / "008-corrupt"
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text("{not valid json!!!")

        engine = WorkflowStateEngine(db, str(tmp_path))
        # When hydrating -- returns None for corrupt JSON
        state = engine._hydrate_from_meta_json(type_id)
        assert state is None

    def test_validate_prerequisites_unknown_phase_gates_handle(
        self, tmp_path
    ) -> None:
        """Adversarial: validate_prerequisites with unknown target phase.

        Anticipate: Gate functions should return blocking results, not crash.
        derived_from: dimension:adversarial (logically invalid but syntactically correct)
        """
        # Given a feature at design
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        # When validating unknown target
        results = engine.validate_prerequisites(type_id, "imaginary-phase")
        # Then should have blocking results (from G-08 at minimum)
        blocked = [r for r in results if not r.allowed]
        assert len(blocked) > 0

    def test_transition_to_same_phase_as_current(self, tmp_path) -> None:
        """Adversarial: transitioning to the same phase you're already in.

        Anticipate: Edge case -- this is technically backward (target_idx <= current_idx).
        G-22 should warn, G-18 should warn if last_completed covers it.
        derived_from: dimension:adversarial (zero/one/many -- zero distance)
        """
        # Given a feature at design with specify completed
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        # When transitioning to the same phase (design)
        response = engine.transition_phase(type_id, "design")
        results = response.results
        # Then G-22 should warn about target not ahead
        g22 = [r for r in results if r.guard_id == "G-22"]
        assert len(g22) == 1
        assert g22[0].severity.value == "warn"


class TestDeepenedErrorPropagation:
    """Error propagation and failure mode tests.

    Dimension 4: Verify error messages are informative and errors propagate correctly.
    """

    def test_valueerror_message_contains_feature_type_id(self, tmp_path) -> None:
        """Error messages include the feature_type_id for debuggability.

        Anticipate: Generic "not found" without context makes debugging hard.
        derived_from: dimension:error_propagation (informative error messages)
        """
        # Given a nonexistent feature
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        # When calling transition_phase
        with pytest.raises(ValueError, match="999-nonexistent"):
            engine.transition_phase("feature:999-nonexistent", "specify")

    def test_complete_phase_mismatch_message_includes_both_phases(
        self, tmp_path
    ) -> None:
        """Phase mismatch error includes both current and requested phase.

        Anticipate: Error message missing context makes it unclear what failed.
        derived_from: dimension:error_propagation (informative error messages)
        """
        # Given a feature at specify
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # When completing wrong phase (design, which is ahead)
        with pytest.raises(ValueError) as exc_info:
            engine.complete_phase(type_id, "design")
        # Then error mentions both phases
        msg = str(exc_info.value)
        assert "design" in msg
        assert "specify" in msg

    def test_yolo_override_replaces_gate_result_in_place(self, tmp_path) -> None:
        """YOLO override replaces the gate result entirely (not appended).

        Anticipate: If YOLO result is appended alongside original, result count doubles.
        derived_from: dimension:error_propagation (YOLO override contract)
        """
        # Given a feature at design with specify completed
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        # When evaluating gates with and without YOLO
        state = engine.get_state(type_id)
        assert state is not None

        results_normal = engine._evaluate_gates(
            state, "create-plan", ["spec.md", "design.md"], yolo_active=False
        )
        results_yolo = engine._evaluate_gates(
            state, "create-plan", ["spec.md", "design.md"], yolo_active=True
        )
        # Then both produce the same number of results (replacement, not addition)
        assert len(results_normal) == len(results_yolo)

    def test_transition_blocked_does_not_update_db(self, tmp_path) -> None:
        """When any gate blocks, DB must NOT be updated.

        Anticipate: If DB update happens before gate check, state corrupts.
        derived_from: dimension:error_propagation (partial failure consistency)
        """
        # Given a feature at specify, missing required artifacts for design
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # When transition is blocked (no spec.md for design)
        results = engine.transition_phase(type_id, "design").results
        assert any(not r.allowed for r in results)
        # Then DB still shows "specify"
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["workflow_phase"] == "specify"
        assert row["last_completed_phase"] == "brainstorm"


class TestDeepenedMutationMindset:
    """Mutation-targeted behavioral pinning tests.

    Dimension 5: Each test targets a specific mutation operator that could
    silently corrupt behavior if applied.
    """

    def test_complete_phase_updates_both_last_completed_and_workflow_phase(
        self, tmp_path
    ) -> None:
        """Pin: complete_phase must update BOTH last_completed AND workflow_phase.

        Mutation target: Deleting the last_completed_phase= kwarg in update call.
        derived_from: dimension:mutation_mindset (line deletion)
        """
        # Given a feature at specify with brainstorm completed
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # When completing specify
        state = engine.complete_phase(type_id, "specify")
        # Then BOTH fields updated
        assert state.last_completed_phase == "specify"  # last_completed updated
        assert state.current_phase == "design"  # workflow_phase advanced
        # Verify via raw DB too
        row = db.get_workflow_phase(type_id)
        assert row["last_completed_phase"] == "specify"
        assert row["workflow_phase"] == "design"

    def test_complete_finish_phase_syncs_entity_status_to_completed(
        self, tmp_path
    ) -> None:
        """Pin: complete_phase('finish') must update entities.status to 'completed'.

        Gap S1 fix: entities.status was never updated by workflow engine,
        causing drift between workflow_phases and entities tables.
        derived_from: dimension:mutation_mindset (line deletion)
        """
        # Given a feature at implement with create-plan completed
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="finish",
            last_completed_phase="implement",
        )
        # Verify entity starts as active
        entity = db.get_entity(type_id)
        assert entity["status"] == "active"
        # When completing finish phase
        state = engine.complete_phase(type_id, "finish")
        assert state.current_phase == "finish"
        assert state.last_completed_phase == "finish"
        # Then entities.status is synced to completed
        entity = db.get_entity(type_id)
        assert entity["status"] == "completed"

    def test_complete_non_finish_phase_does_not_change_entity_status(
        self, tmp_path
    ) -> None:
        """Pin: complete_phase for non-terminal phases must NOT touch entities.status.

        derived_from: dimension:mutation_mindset (guard condition removal)
        """
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        state = engine.complete_phase(type_id, "specify")
        assert state.current_phase == "design"
        # Entity status must still be active (not "completed")
        entity = db.get_entity(type_id)
        assert entity["status"] == "active"

    def test_transition_phase_only_updates_workflow_phase_not_last_completed(
        self, tmp_path
    ) -> None:
        """Pin: transition_phase must ONLY update workflow_phase.

        Mutation target: Adding last_completed_phase= to the transition update call.
        derived_from: dimension:mutation_mindset (line deletion / return value mutation)
        """
        # Given a feature at specify with brainstorm completed
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        # When transitioning to design
        results = engine.transition_phase(type_id, "design").results
        assert all(r.allowed for r in results)
        # Then workflow_phase changed but last_completed_phase did NOT change
        row = db.get_workflow_phase(type_id)
        assert row["workflow_phase"] == "design"
        assert row["last_completed_phase"] == "brainstorm"  # unchanged!

    def test_all_gates_must_pass_for_transition_not_any(self, tmp_path) -> None:
        """Pin: transition uses all() not any() for gate pass check.

        Mutation target: Swapping all(r.allowed ...) to any(r.allowed ...).
        If any() were used, transition would proceed even with one blocking gate.
        derived_from: dimension:mutation_mindset (logic inversion)
        """
        # Given a feature at specify, missing required artifact for design
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # No spec.md -> G-08 will block, but G-23 might pass
        response = engine.transition_phase(type_id, "design")
        results = response.results

        # Verify at least one gate blocks
        blocked = [r for r in results if not r.allowed]
        assert len(blocked) >= 1
        # Verify at least one gate passes (so any() would wrongly pass)
        passed = [r for r in results if r.allowed]
        assert len(passed) >= 1
        # And transition did NOT happen (all() correctly blocked)
        row = db.get_workflow_phase(type_id)
        assert row["workflow_phase"] == "specify"  # unchanged

    def test_backward_skip_uses_last_completed_not_current_phase(
        self, tmp_path
    ) -> None:
        """Pin: backward gate skip condition checks last_completed_phase, not current_phase.

        Mutation target: Changing `state.last_completed_phase is not None` to
        `state.current_phase is not None` in _evaluate_gates.
        derived_from: dimension:mutation_mindset (boundary shift)
        """
        # Given a feature with current_phase set but last_completed_phase=None
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="brainstorm",
            last_completed_phase=None,
        )
        state = engine.get_state(type_id)
        assert state is not None
        assert state.current_phase == "brainstorm"  # current_phase IS set
        assert state.last_completed_phase is None  # last_completed IS None

        # When evaluating gates
        results = engine._evaluate_gates(
            state, "brainstorm", [], yolo_active=False
        )
        # Then backward gate (G-18) is SKIPPED (because last_completed is None)
        guard_ids = [r.guard_id for r in results]
        assert "G-18" not in guard_ids
        # If the mutation were applied (checking current_phase instead),
        # G-18 would be included because current_phase is set.

    def test_backward_rerun_boundary_uses_strict_greater_not_gte(
        self, tmp_path
    ) -> None:
        """Pin: backward re-run check uses `phase_idx > last_idx` not `>=`.

        Mutation target: Changing > to >= in complete_phase would cause completing
        the same phase as last_completed to raise ValueError instead of allowing it.
        derived_from: dimension:mutation_mindset (boundary shift >= vs >)
        """
        # Given a feature at design with design as last_completed
        # (i.e., re-running the current phase)
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="design",
        )
        # When completing design (same as last_completed, so phase_idx == last_idx)
        # This is NOT a mismatch, it's the current phase = design
        state = engine.complete_phase(type_id, "design")
        # Then it should succeed (not raise ValueError)
        assert state.last_completed_phase == "design"
        assert state.current_phase == "create-plan"

    def test_hydration_completed_status_overrides_last_completed_to_finish(
        self, tmp_path
    ) -> None:
        """Pin: completed status sets last_completed = last_completed or 'finish'.

        Mutation target: Removing the `or "finish"` fallback would leave
        last_completed as None for completed features without lastCompletedPhase.
        derived_from: dimension:mutation_mindset (return value mutation)
        """
        # Given a completed feature with NO lastCompletedPhase in meta
        db = _make_db()
        type_id = _register_feature(db, "008-comp-null")
        _create_meta_json(
            tmp_path,
            "008-comp-null",
            status="completed",
            last_completed_phase=None,  # absent
        )
        engine = WorkflowStateEngine(db, str(tmp_path))
        # When hydrating
        state = engine._hydrate_from_meta_json(type_id)
        # Then last_completed defaults to "finish" (not None)
        assert state is not None
        assert state.last_completed_phase == "finish"
        assert state.current_phase == "finish"
        assert len(state.completed_phases) == 6  # all phases

    def test_terminal_phase_next_returns_none_triggers_fallback(
        self, tmp_path
    ) -> None:
        """Pin: _next_phase_value('finish') returns None, complete_phase uses fallback.

        Mutation target: Removing `if next_phase is None: next_phase = phase`
        would set workflow_phase to None after finishing.
        derived_from: dimension:mutation_mindset (return value mutation + line deletion)
        """
        # Given a feature at finish
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="finish",
            last_completed_phase="implement",
        )
        # When completing finish
        state = engine.complete_phase(type_id, "finish")
        # Then workflow_phase stays "finish" (not None)
        assert state.current_phase == "finish"
        row = db.get_workflow_phase(type_id)
        assert row["workflow_phase"] == "finish"
        assert row["workflow_phase"] is not None

    def test_hydration_planned_status_clears_non_null_last_completed(
        self, tmp_path
    ) -> None:
        """Pin: planned status nullifies lastCompletedPhase even if non-null in meta.

        Mutation target: Removing `last_completed = None` for non-active/completed
        statuses would preserve stale lastCompletedPhase data.
        derived_from: dimension:mutation_mindset (line deletion)
        """
        # Given a planned feature with stale lastCompletedPhase
        db = _make_db()
        type_id = _register_feature(db, "008-stale-planned")
        _create_meta_json(
            tmp_path,
            "008-stale-planned",
            status="planned",
            last_completed_phase="design",  # stale data
        )
        engine = WorkflowStateEngine(db, str(tmp_path))
        # When hydrating
        state = engine._hydrate_from_meta_json(type_id)
        # Then planned status overrides to null
        assert state is not None
        assert state.last_completed_phase is None
        assert state.current_phase is None
        assert state.completed_phases == ()


class TestDeepenedPerformance:
    """Performance contract tests.

    Dimension 6: Basic timing assertions for engine operations.
    """

    def test_single_transition_under_50ms(self, tmp_path) -> None:
        """Performance: single transition should complete within 50ms.

        derived_from: dimension:performance_contracts (SLA: single operation)
        """
        import time

        # Given a feature ready for transition
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        # When timing a transition
        times = []
        for _ in range(10):
            # Reset state for each iteration
            db.update_workflow_phase(type_id, workflow_phase="specify")
            start = time.perf_counter()
            engine.transition_phase(type_id, "design")
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        # Then median should be under 50ms
        times.sort()
        median = times[len(times) // 2]
        assert median < 50, f"Median transition time {median:.1f}ms exceeds 50ms SLA"

    def test_batch_query_100_features_under_200ms(self, tmp_path) -> None:
        """Performance: batch query of 100 features should complete within 200ms.

        derived_from: dimension:performance_contracts (SLA: batch operation)
        """
        import time

        # Given 100 registered features with workflow rows
        db = _make_db()
        for i in range(100):
            slug = f"{i:03d}-perf-feature"
            tid = _register_feature(db, slug, status="active")
            phase = ["specify", "design", "implement"][i % 3]
            db.create_workflow_phase(tid, workflow_phase=phase)

        engine = WorkflowStateEngine(db, str(tmp_path))

        # When timing list_by_status
        start = time.perf_counter()
        results = engine.list_by_status("active")
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Then under 200ms and correct count
        assert len(results) == 100
        assert elapsed_ms < 200, (
            f"Batch query time {elapsed_ms:.1f}ms exceeds 200ms SLA"
        )


# ---------------------------------------------------------------------------
# TransitionResponse dataclass (Task 1.1)
# ---------------------------------------------------------------------------


class TestTransitionResponse:
    """Tests for the TransitionResponse frozen dataclass."""

    def test_transition_response_construction(self) -> None:
        """TransitionResponse can be constructed with results tuple and degraded bool."""
        r1 = TransitionResult(
            allowed=True, reason="ok", severity=Severity.info, guard_id="g1"
        )
        r2 = TransitionResult(
            allowed=False, reason="blocked", severity=Severity.block, guard_id="g2"
        )
        response = TransitionResponse(results=(r1, r2), degraded=False)
        assert response is not None

    def test_transition_response_frozen(self) -> None:
        """TransitionResponse is frozen -- attributes cannot be reassigned."""
        r1 = TransitionResult(
            allowed=True, reason="ok", severity=Severity.info, guard_id="g1"
        )
        response = TransitionResponse(results=(r1,), degraded=False)
        with pytest.raises(FrozenInstanceError):
            response.degraded = True  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            response.results = ()  # type: ignore[misc]

    def test_transition_response_field_access(self) -> None:
        """TransitionResponse fields are accessible and correct."""
        r1 = TransitionResult(
            allowed=True, reason="ok", severity=Severity.info, guard_id="g1"
        )
        r2 = TransitionResult(
            allowed=False, reason="no", severity=Severity.block, guard_id="g2"
        )
        response = TransitionResponse(results=(r1, r2), degraded=True)
        assert response.results == (r1, r2)
        assert response.degraded is True

    def test_transition_response_results_is_tuple(self) -> None:
        """TransitionResponse.results is a tuple, not a list."""
        r1 = TransitionResult(
            allowed=True, reason="ok", severity=Severity.info, guard_id="g1"
        )
        response = TransitionResponse(results=(r1,), degraded=False)
        assert isinstance(response.results, tuple)

    def test_transition_response_degraded_is_bool(self) -> None:
        """TransitionResponse.degraded is a bool."""
        r1 = TransitionResult(
            allowed=True, reason="ok", severity=Severity.info, guard_id="g1"
        )
        response_normal = TransitionResponse(results=(r1,), degraded=False)
        response_degraded = TransitionResponse(results=(r1,), degraded=True)
        assert isinstance(response_normal.degraded, bool)
        assert isinstance(response_degraded.degraded, bool)
        assert response_normal.degraded is False
        assert response_degraded.degraded is True

    def test_transition_response_empty_results(self) -> None:
        """TransitionResponse can have empty results tuple."""
        response = TransitionResponse(results=(), degraded=False)
        assert response.results == ()
        assert len(response.results) == 0


class TestCheckDbHealth:
    """Tests for _check_db_health() -- DB availability probe."""

    def test_healthy_db_returns_true(self, tmp_path) -> None:
        """A healthy in-memory DB returns True from _check_db_health."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        assert engine._check_db_health() is True

    def test_conn_none_returns_false(self, tmp_path, monkeypatch) -> None:
        """When db._conn is None (defensive guard), returns False."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        monkeypatch.setattr(engine.db, "_conn", None)
        assert engine._check_db_health() is False

    def test_programming_error_returns_false(self, tmp_path, monkeypatch) -> None:
        """When execute raises sqlite3.ProgrammingError (closed DB), returns False."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        class MockConn:
            def execute(self, *a):
                raise sqlite3.ProgrammingError("closed")

        monkeypatch.setattr(engine.db, "_conn", MockConn())
        assert engine._check_db_health() is False

    def test_generic_sqlite_error_returns_false(self, tmp_path, monkeypatch) -> None:
        """When execute raises generic sqlite3.Error, returns False."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        class MockConn:
            def execute(self, *a):
                raise sqlite3.Error("generic error")

        monkeypatch.setattr(engine.db, "_conn", MockConn())
        assert engine._check_db_health() is False


class TestDeriveStateFromMeta:
    """Task 1.3: _derive_state_from_meta extraction tests."""

    def test_active_status_with_last_completed(self, tmp_path) -> None:
        """Active status with lastCompletedPhase derives next phase."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        meta = {"status": "active", "mode": "standard", "lastCompletedPhase": "design"}

        state = engine._derive_state_from_meta(meta, "feature:008-test")

        assert state is not None
        assert state.current_phase == "create-plan"  # next after design
        assert state.last_completed_phase == "design"
        assert state.completed_phases == ("brainstorm", "specify", "design")
        assert state.mode == "standard"
        assert state.feature_type_id == "feature:008-test"

    def test_active_status_no_completed_phase(self, tmp_path) -> None:
        """Active status with no lastCompletedPhase uses first phase."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        meta = {"status": "active", "mode": "full"}

        state = engine._derive_state_from_meta(meta, "feature:008-new")

        assert state is not None
        assert state.current_phase == PHASE_SEQUENCE[0].value  # brainstorm
        assert state.last_completed_phase is None
        assert state.completed_phases == ()

    def test_active_finished_edge(self, tmp_path) -> None:
        """Active + lastCompletedPhase='finish' -> workflow_phase='finish'."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        meta = {"status": "active", "lastCompletedPhase": "finish"}

        state = engine._derive_state_from_meta(meta, "feature:008-edge")

        assert state is not None
        # _next_phase_value("finish") returns None, so workflow_phase = last_completed
        assert state.current_phase == "finish"

    def test_completed_status(self, tmp_path) -> None:
        """Completed status derives workflow_phase='finish'."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        meta = {"status": "completed", "mode": "standard", "lastCompletedPhase": "implement"}

        state = engine._derive_state_from_meta(meta, "feature:008-done")

        assert state is not None
        assert state.current_phase == "finish"
        assert state.last_completed_phase == "implement"

    def test_completed_status_no_last_completed_defaults_to_finish(self, tmp_path) -> None:
        """Completed status with no lastCompletedPhase defaults to 'finish'."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        meta = {"status": "completed"}

        state = engine._derive_state_from_meta(meta, "feature:008-comp-null")

        assert state is not None
        assert state.last_completed_phase == "finish"
        assert state.current_phase == "finish"
        assert len(state.completed_phases) == 6  # all phases

    def test_unknown_status(self, tmp_path) -> None:
        """Unknown status (planned, abandoned, etc.) -> workflow_phase=None."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        meta = {"status": "planned", "lastCompletedPhase": "specify"}

        state = engine._derive_state_from_meta(meta, "feature:008-planned")

        assert state is not None
        assert state.current_phase is None
        assert state.last_completed_phase is None
        assert state.completed_phases == ()

    def test_default_source_is_meta_json(self, tmp_path) -> None:
        """Omitting source arg defaults to 'meta_json'."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        meta = {"status": "active", "mode": "standard"}

        state = engine._derive_state_from_meta(meta, "feature:008-default")

        assert state is not None
        assert state.source == "meta_json"

    def test_custom_source(self, tmp_path) -> None:
        """Explicit source parameter is passed through."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        meta = {"status": "active", "mode": "standard"}

        state = engine._derive_state_from_meta(
            meta, "feature:008-custom", source="meta_json_fallback"
        )

        assert state is not None
        assert state.source == "meta_json_fallback"

    def test_invalid_last_completed_returns_none(self, tmp_path) -> None:
        """ValueError from _next_phase_value (invalid phase) returns None."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        meta = {"status": "active", "lastCompletedPhase": "invalid-phase"}

        state = engine._derive_state_from_meta(meta, "feature:008-bad")

        assert state is None

    def test_completed_with_invalid_last_completed_returns_none(self, tmp_path) -> None:
        """Completed status with invalid lastCompletedPhase returns None."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        meta = {"status": "completed", "lastCompletedPhase": "invalid-phase"}

        state = engine._derive_state_from_meta(meta, "feature:008-bad-comp")

        assert state is None


class TestIsoNow:
    """Task 1.4: _iso_now() module-level helper tests."""

    def test_returns_string(self) -> None:
        """_iso_now() must return a string."""
        from workflow_engine.engine import _iso_now

        result = _iso_now()
        assert isinstance(result, str)

    def test_contains_timezone_offset(self) -> None:
        """Output must contain a timezone offset ('+HH:MM', '-HH:MM', or 'Z')."""
        import re

        from workflow_engine.engine import _iso_now

        result = _iso_now()
        # ISO 8601 timezone patterns: +HH:MM, -HH:MM, or Z
        tz_pattern = r"([+-]\d{2}:\d{2}|Z)$"
        assert re.search(tz_pattern, result), (
            f"Expected timezone offset in ISO 8601 output, got: {result}"
        )

    def test_parseable_as_iso_8601(self) -> None:
        """Output must be parseable back as a valid ISO 8601 datetime."""
        from datetime import datetime

        from workflow_engine.engine import _iso_now

        result = _iso_now()
        # datetime.fromisoformat handles ISO 8601 strings (Python 3.11+)
        parsed = datetime.fromisoformat(result)
        assert parsed is not None

    def test_matches_meta_json_convention(self) -> None:
        """Output format matches .meta.json convention: ISO 8601 with timezone.

        Example: '2026-03-06T18:30:00+08:00' or '2026-03-06T10:30:00+00:00'
        """
        import re

        from workflow_engine.engine import _iso_now

        result = _iso_now()
        # Full ISO 8601 with timezone: YYYY-MM-DDTHH:MM:SS[.ffffff]+HH:MM
        iso_with_tz = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?[+-]\d{2}:\d{2}$"
        assert re.match(iso_with_tz, result), (
            f"Expected ISO 8601 with timezone offset, got: {result}"
        )

    def test_timezone_aware(self) -> None:
        """Returned datetime must be timezone-aware (not naive)."""
        from datetime import datetime

        from workflow_engine.engine import _iso_now

        result = _iso_now()
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None, (
            f"Expected timezone-aware datetime, got naive: {result}"
        )


class TestReadStateFromMetaJson:
    """Task 2.1: _read_state_from_meta_json() pure-filesystem reader tests."""

    def test_valid_meta_json_returns_state(self, tmp_path) -> None:
        """Valid .meta.json returns FeatureWorkflowState with source='meta_json_fallback'."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-test-feature"
        _create_meta_json(tmp_path, slug, status="active", mode="standard", last_completed_phase="design")

        state = engine._read_state_from_meta_json(f"feature:{slug}")

        assert state is not None
        assert state.source == "meta_json_fallback"
        assert state.feature_type_id == f"feature:{slug}"
        assert state.current_phase == "create-plan"  # next after design
        assert state.last_completed_phase == "design"
        assert state.completed_phases == ("brainstorm", "specify", "design")
        assert state.mode == "standard"

    def test_missing_file_returns_none(self, tmp_path) -> None:
        """Missing .meta.json returns None (no exception raised)."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = engine._read_state_from_meta_json("feature:999-nonexistent")

        assert result is None

    def test_corrupt_json_returns_none(self, tmp_path) -> None:
        """Corrupt (unparseable) .meta.json returns None."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-corrupt"
        feature_dir = tmp_path / "features" / slug
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text("{invalid json!!!")

        result = engine._read_state_from_meta_json(f"feature:{slug}")

        assert result is None

    def test_oserror_returns_none(self, tmp_path) -> None:
        """OSError (e.g., permission denied) returns None."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-oserror"
        # Create a directory where .meta.json is expected -- trying to open
        # a directory as a file raises IsADirectoryError (subclass of OSError)
        feature_dir = tmp_path / "features" / slug
        feature_dir.mkdir(parents=True)
        meta_dir = feature_dir / ".meta.json"
        meta_dir.mkdir()  # .meta.json is a directory, not a file

        result = engine._read_state_from_meta_json(f"feature:{slug}")

        assert result is None

    def test_active_status_no_completed_phase(self, tmp_path) -> None:
        """Active status with no lastCompletedPhase returns first phase."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-active-new"
        _create_meta_json(tmp_path, slug, status="active", mode="full")

        state = engine._read_state_from_meta_json(f"feature:{slug}")

        assert state is not None
        assert state.current_phase == PHASE_SEQUENCE[0].value  # brainstorm
        assert state.last_completed_phase is None
        assert state.completed_phases == ()
        assert state.mode == "full"
        assert state.source == "meta_json_fallback"

    def test_completed_status(self, tmp_path) -> None:
        """Completed status returns workflow_phase='finish'."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-completed"
        _create_meta_json(tmp_path, slug, status="completed", last_completed_phase="implement")

        state = engine._read_state_from_meta_json(f"feature:{slug}")

        assert state is not None
        assert state.current_phase == "finish"
        assert state.last_completed_phase == "implement"
        assert state.source == "meta_json_fallback"

    def test_unknown_status(self, tmp_path) -> None:
        """Unknown status (planned, abandoned, etc.) returns workflow_phase=None."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-planned"
        _create_meta_json(tmp_path, slug, status="planned")

        state = engine._read_state_from_meta_json(f"feature:{slug}")

        assert state is not None
        assert state.current_phase is None
        assert state.last_completed_phase is None
        assert state.completed_phases == ()
        assert state.source == "meta_json_fallback"

    def test_does_not_require_db_entity(self, tmp_path) -> None:
        """_read_state_from_meta_json works without any entity in the DB.

        This is a key difference from _hydrate_from_meta_json which requires
        self.db.get_entity() to succeed first.
        """
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-no-entity"
        # Create .meta.json but do NOT register entity in DB
        _create_meta_json(tmp_path, slug, status="active", mode="standard", last_completed_phase="specify")

        state = engine._read_state_from_meta_json(f"feature:{slug}")

        assert state is not None
        assert state.feature_type_id == f"feature:{slug}"
        assert state.source == "meta_json_fallback"

    def test_invalid_last_completed_phase_returns_none(self, tmp_path) -> None:
        """Invalid lastCompletedPhase value causes _derive_state_from_meta to return None."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-bad-phase"
        _create_meta_json(tmp_path, slug, status="active", last_completed_phase="invalid-phase")

        result = engine._read_state_from_meta_json(f"feature:{slug}")

        assert result is None


# ---------------------------------------------------------------------------
# _write_meta_json_fallback (Task 2.2)
# ---------------------------------------------------------------------------


class TestWriteMetaJsonFallback:
    """Task 2.2: _write_meta_json_fallback() atomic .meta.json writer tests."""

    def test_normal_write_updates_last_completed_and_phase_timestamp(
        self, tmp_path
    ) -> None:
        """Normal write updates lastCompletedPhase and phases.{phase}.completed."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-write-test"
        _create_meta_json(
            tmp_path, slug, status="active", mode="standard",
            last_completed_phase="specify",
        )

        input_state = FeatureWorkflowState(
            feature_type_id=f"feature:{slug}",
            current_phase="design",
            last_completed_phase="specify",
            completed_phases=("brainstorm", "specify"),
            mode="standard",
            source="meta_json_fallback",
        )

        result = engine._write_meta_json_fallback(
            f"feature:{slug}", "design", input_state
        )

        # Verify returned FeatureWorkflowState
        assert result is not None
        assert result.source == "meta_json_fallback"
        assert result.last_completed_phase == "design"
        assert result.current_phase == "create-plan"  # next after design
        assert result.completed_phases == ("brainstorm", "specify", "design")
        assert result.mode == "standard"
        assert result.feature_type_id == f"feature:{slug}"

        # Verify .meta.json file was updated
        meta_path = tmp_path / "features" / slug / ".meta.json"
        with open(meta_path) as f:
            meta = json.load(f)

        assert meta["lastCompletedPhase"] == "design"
        assert "design" in meta["phases"]
        assert "completed" in meta["phases"]["design"]
        # Verify timestamp is ISO 8601 with timezone
        import re
        iso_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
        assert re.match(iso_pattern, meta["phases"]["design"]["completed"])

    def test_atomic_replacement_cleans_up_temp_file(self, tmp_path) -> None:
        """After successful write, no temp files remain in the feature dir."""
        import glob

        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-atomic-test"
        _create_meta_json(
            tmp_path, slug, status="active", mode="standard",
            last_completed_phase="brainstorm",
        )

        input_state = FeatureWorkflowState(
            feature_type_id=f"feature:{slug}",
            current_phase="specify",
            last_completed_phase="brainstorm",
            completed_phases=("brainstorm",),
            mode="standard",
            source="meta_json_fallback",
        )

        engine._write_meta_json_fallback(
            f"feature:{slug}", "specify", input_state
        )

        # No .tmp files should remain in the feature directory
        feature_dir = tmp_path / "features" / slug
        tmp_files = glob.glob(str(feature_dir / "*.tmp"))
        assert tmp_files == [], f"Temp files left behind: {tmp_files}"

    def test_missing_meta_json_raises_value_error(self, tmp_path) -> None:
        """Missing .meta.json raises ValueError."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-missing"
        # Do NOT create .meta.json

        input_state = FeatureWorkflowState(
            feature_type_id=f"feature:{slug}",
            current_phase="specify",
            last_completed_phase="brainstorm",
            completed_phases=("brainstorm",),
            mode="standard",
            source="meta_json_fallback",
        )

        with pytest.raises(ValueError, match="Cannot update .meta.json"):
            engine._write_meta_json_fallback(
                f"feature:{slug}", "specify", input_state
            )

    def test_corrupt_meta_json_raises_value_error(self, tmp_path) -> None:
        """Corrupt .meta.json raises ValueError."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-corrupt-write"
        feature_dir = tmp_path / "features" / slug
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text("{broken json!!!")

        input_state = FeatureWorkflowState(
            feature_type_id=f"feature:{slug}",
            current_phase="specify",
            last_completed_phase="brainstorm",
            completed_phases=("brainstorm",),
            mode="standard",
            source="meta_json_fallback",
        )

        with pytest.raises(ValueError, match="Cannot update .meta.json"):
            engine._write_meta_json_fallback(
                f"feature:{slug}", "specify", input_state
            )

    def test_terminal_phase_finish_sets_status_completed(
        self, tmp_path
    ) -> None:
        """Completing 'finish' phase sets status='completed' and completed timestamp."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-finish-test"
        _create_meta_json(
            tmp_path, slug, status="active", mode="standard",
            last_completed_phase="implement",
        )

        input_state = FeatureWorkflowState(
            feature_type_id=f"feature:{slug}",
            current_phase="finish",
            last_completed_phase="implement",
            completed_phases=(
                "brainstorm", "specify", "design",
                "create-plan", "implement",
            ),
            mode="standard",
            source="meta_json_fallback",
        )

        result = engine._write_meta_json_fallback(
            f"feature:{slug}", "finish", input_state
        )

        # Verify returned state
        assert result.current_phase == "finish"  # terminal: stays at finish
        assert result.last_completed_phase == "finish"
        assert result.source == "meta_json_fallback"
        assert "finish" in result.completed_phases

        # Verify .meta.json
        meta_path = tmp_path / "features" / slug / ".meta.json"
        with open(meta_path) as f:
            meta = json.load(f)

        assert meta["status"] == "completed"
        assert meta["lastCompletedPhase"] == "finish"
        assert "finish" in meta["phases"]
        assert "completed" in meta["phases"]["finish"]
        # completed timestamp at top level
        assert "completed" in meta

    def test_partial_write_cleanup_removes_temp_file(self, tmp_path) -> None:
        """When json.dump raises mid-write, temp file is cleaned up."""
        import glob

        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-partial-write"
        _create_meta_json(
            tmp_path, slug, status="active", mode="standard",
            last_completed_phase="brainstorm",
        )

        input_state = FeatureWorkflowState(
            feature_type_id=f"feature:{slug}",
            current_phase="specify",
            last_completed_phase="brainstorm",
            completed_phases=("brainstorm",),
            mode="standard",
            source="meta_json_fallback",
        )

        # Mock json.dump to raise mid-write
        with patch("workflow_engine.engine.json.dump", side_effect=IOError("disk full")):
            with pytest.raises(IOError, match="disk full"):
                engine._write_meta_json_fallback(
                    f"feature:{slug}", "specify", input_state
                )

        # Verify no temp files left behind
        feature_dir = tmp_path / "features" / slug
        tmp_files = glob.glob(str(feature_dir / "*.tmp"))
        assert tmp_files == [], f"Temp files left behind after failure: {tmp_files}"

        # Verify original .meta.json is unchanged (not corrupted)
        meta_path = feature_dir / ".meta.json"
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["lastCompletedPhase"] == "brainstorm"  # unchanged

    def test_state_mode_is_used_from_input_state(self, tmp_path) -> None:
        """Only state.mode is read from the input state parameter."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-mode-test"
        _create_meta_json(
            tmp_path, slug, status="active", mode="standard",
            last_completed_phase="brainstorm",
        )

        # Input state has mode="full" which differs from .meta.json mode="standard"
        input_state = FeatureWorkflowState(
            feature_type_id=f"feature:{slug}",
            current_phase="specify",
            last_completed_phase="brainstorm",
            completed_phases=("brainstorm",),
            mode="full",
            source="meta_json_fallback",
        )

        result = engine._write_meta_json_fallback(
            f"feature:{slug}", "specify", input_state
        )

        # Returned state uses input_state.mode, not .meta.json mode
        assert result.mode == "full"

    def test_phases_setdefault_creates_missing_phases_dict(
        self, tmp_path
    ) -> None:
        """When .meta.json has no 'phases' key, it is created."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "008-no-phases"
        # Create .meta.json without 'phases' key
        feature_dir = tmp_path / "features" / slug
        feature_dir.mkdir(parents=True)
        meta = {"id": "008", "slug": slug, "status": "active", "mode": "standard"}
        (feature_dir / ".meta.json").write_text(json.dumps(meta))

        input_state = FeatureWorkflowState(
            feature_type_id=f"feature:{slug}",
            current_phase="brainstorm",
            last_completed_phase=None,
            completed_phases=(),
            mode="standard",
            source="meta_json_fallback",
        )

        result = engine._write_meta_json_fallback(
            f"feature:{slug}", "brainstorm", input_state
        )

        assert result is not None
        # Verify the file now has phases dict
        meta_path = feature_dir / ".meta.json"
        with open(meta_path) as f:
            updated = json.load(f)
        assert "phases" in updated
        assert "brainstorm" in updated["phases"]
        assert "completed" in updated["phases"]["brainstorm"]


class TestScanFeaturesFilesystem:
    """Task 3.1: _scan_features_filesystem() directory scanner tests."""

    def test_multiple_features_returns_correct_list(self, tmp_path) -> None:
        """Scanning a dir with multiple valid .meta.json files returns all."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        # Create three features with valid .meta.json
        _create_meta_json(tmp_path, "001-alpha", status="active", mode="standard")
        _create_meta_json(
            tmp_path, "002-beta", status="active", mode="full",
            last_completed_phase="brainstorm",
        )
        _create_meta_json(tmp_path, "003-gamma", status="completed",
                          last_completed_phase="finish")

        results = engine._scan_features_filesystem()

        assert len(results) == 3
        type_ids = {r.feature_type_id for r in results}
        assert type_ids == {
            "feature:001-alpha",
            "feature:002-beta",
            "feature:003-gamma",
        }
        # All results have meta_json_fallback source
        for r in results:
            assert r.source == "meta_json_fallback"

    def test_empty_dir_returns_empty_list(self, tmp_path) -> None:
        """Empty features directory returns empty list."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        # Create features dir but no feature subdirectories
        (tmp_path / "features").mkdir(parents=True, exist_ok=True)

        results = engine._scan_features_filesystem()

        assert results == []

    def test_no_features_dir_returns_empty_list(self, tmp_path) -> None:
        """Missing features directory returns empty list (no crash)."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        # Do NOT create features dir at all
        results = engine._scan_features_filesystem()

        assert results == []

    def test_corrupt_meta_json_files_skipped(self, tmp_path) -> None:
        """Mix of valid and corrupt .meta.json files -- corrupt ones skipped."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        # Valid feature
        _create_meta_json(tmp_path, "001-valid", status="active", mode="standard")

        # Corrupt feature -- invalid JSON
        corrupt_dir = tmp_path / "features" / "002-corrupt"
        corrupt_dir.mkdir(parents=True)
        (corrupt_dir / ".meta.json").write_text("{broken json!!!")

        # Another valid feature
        _create_meta_json(
            tmp_path, "003-also-valid", status="completed",
            last_completed_phase="finish",
        )

        results = engine._scan_features_filesystem()

        assert len(results) == 2
        type_ids = {r.feature_type_id for r in results}
        assert "feature:001-valid" in type_ids
        assert "feature:003-also-valid" in type_ids
        assert "feature:002-corrupt" not in type_ids

    def test_feature_type_id_derived_from_dir_name(self, tmp_path) -> None:
        """feature_type_id is 'feature:{dirname}' from the .meta.json parent dir."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        _create_meta_json(tmp_path, "042-specific-slug", status="active")

        results = engine._scan_features_filesystem()

        assert len(results) == 1
        assert results[0].feature_type_id == "feature:042-specific-slug"

    def test_states_have_correct_phase_derivation(self, tmp_path) -> None:
        """States returned have correct phase derivation from .meta.json data."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        _create_meta_json(
            tmp_path, "010-phase-test", status="active", mode="full",
            last_completed_phase="specify",
        )

        results = engine._scan_features_filesystem()

        assert len(results) == 1
        state = results[0]
        assert state.current_phase == "design"  # next after specify
        assert state.last_completed_phase == "specify"
        assert state.completed_phases == ("brainstorm", "specify")
        assert state.mode == "full"


class TestScanFeaturesByStatus:
    """Task 3.2: _scan_features_by_status() filesystem scanner filtered by status."""

    def test_filter_active_returns_only_active(self, tmp_path) -> None:
        """Filtering by 'active' returns only features with status='active'."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        _create_meta_json(tmp_path, "001-active-a", status="active", mode="standard")
        _create_meta_json(
            tmp_path, "002-active-b", status="active", mode="full",
            last_completed_phase="brainstorm",
        )
        _create_meta_json(
            tmp_path, "003-completed", status="completed",
            last_completed_phase="finish",
        )
        _create_meta_json(tmp_path, "004-planned", status="planned")

        results = engine._scan_features_by_status("active")

        assert len(results) == 2
        type_ids = {r.feature_type_id for r in results}
        assert type_ids == {"feature:001-active-a", "feature:002-active-b"}
        for r in results:
            assert r.source == "meta_json_fallback"

    def test_filter_completed_returns_only_completed(self, tmp_path) -> None:
        """Filtering by 'completed' returns only features with status='completed'."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        _create_meta_json(tmp_path, "001-active", status="active", mode="standard")
        _create_meta_json(
            tmp_path, "002-done", status="completed",
            last_completed_phase="finish",
        )
        _create_meta_json(
            tmp_path, "003-also-done", status="completed",
            last_completed_phase="implement",
        )

        results = engine._scan_features_by_status("completed")

        assert len(results) == 2
        type_ids = {r.feature_type_id for r in results}
        assert type_ids == {"feature:002-done", "feature:003-also-done"}
        for r in results:
            assert r.source == "meta_json_fallback"
            assert r.current_phase == "finish"  # completed status -> finish

    def test_corrupt_files_skipped(self, tmp_path) -> None:
        """Corrupt .meta.json files are silently skipped, not raising errors."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        _create_meta_json(tmp_path, "001-valid", status="active", mode="standard")

        # Corrupt feature -- invalid JSON
        corrupt_dir = tmp_path / "features" / "002-corrupt"
        corrupt_dir.mkdir(parents=True)
        (corrupt_dir / ".meta.json").write_text("{broken json!!!")

        _create_meta_json(tmp_path, "003-also-valid", status="active", mode="full")

        results = engine._scan_features_by_status("active")

        assert len(results) == 2
        type_ids = {r.feature_type_id for r in results}
        assert "feature:001-valid" in type_ids
        assert "feature:003-also-valid" in type_ids
        assert "feature:002-corrupt" not in type_ids

    def test_empty_results_when_no_match(self, tmp_path) -> None:
        """When no features match the status, returns empty list."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        _create_meta_json(tmp_path, "001-active", status="active", mode="standard")
        _create_meta_json(
            tmp_path, "002-completed", status="completed",
            last_completed_phase="finish",
        )

        results = engine._scan_features_by_status("planned")

        assert results == []

    def test_empty_features_dir_returns_empty_list(self, tmp_path) -> None:
        """Empty features directory returns empty list."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        (tmp_path / "features").mkdir(parents=True, exist_ok=True)

        results = engine._scan_features_by_status("active")

        assert results == []

    def test_no_features_dir_returns_empty_list(self, tmp_path) -> None:
        """Missing features directory returns empty list (no crash)."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        results = engine._scan_features_by_status("active")

        assert results == []

    def test_filters_before_state_derivation(self, tmp_path) -> None:
        """Status filtering happens at raw JSON level, not on FeatureWorkflowState.

        This is important because FeatureWorkflowState has no status field.
        Verify by checking that only matching features get derived states.
        """
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        _create_meta_json(
            tmp_path, "001-active", status="active", mode="standard",
            last_completed_phase="design",
        )
        _create_meta_json(
            tmp_path, "002-completed", status="completed",
            last_completed_phase="finish",
        )

        active_results = engine._scan_features_by_status("active")
        assert len(active_results) == 1
        assert active_results[0].feature_type_id == "feature:001-active"
        assert active_results[0].current_phase == "create-plan"  # next after design

        completed_results = engine._scan_features_by_status("completed")
        assert len(completed_results) == 1
        assert completed_results[0].feature_type_id == "feature:002-completed"
        assert completed_results[0].current_phase == "finish"

    def test_derive_state_returns_none_skips_feature(self, tmp_path) -> None:
        """When _derive_state_from_meta returns None, that feature is skipped.

        This can happen when lastCompletedPhase is an invalid phase name.
        """
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        # Valid active feature
        _create_meta_json(tmp_path, "001-valid", status="active", mode="standard")

        # Active feature with invalid lastCompletedPhase -> _derive returns None
        bad_dir = tmp_path / "features" / "002-bad-phase"
        bad_dir.mkdir(parents=True)
        meta = {
            "id": "002",
            "slug": "002-bad-phase",
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": "invalid-phase-name",
        }
        (bad_dir / ".meta.json").write_text(json.dumps(meta))

        results = engine._scan_features_by_status("active")

        # Only the valid feature should be returned
        assert len(results) == 1
        assert results[0].feature_type_id == "feature:001-valid"


# ===========================================================================
# Task 4.1: get_state() fallback tests
# ===========================================================================


class TestGetStateFallback:
    """Task 4.1: get_state() degrades to .meta.json when DB is unhealthy."""

    def test_probe_fails_returns_meta_json_fallback(self, tmp_path) -> None:
        """When _check_db_health returns False, get_state returns from .meta.json
        with source='meta_json_fallback'."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        # Create .meta.json so the fallback has data to read
        _create_meta_json(
            tmp_path,
            "008-test-feature",
            status="active",
            last_completed_phase="design",
        )
        # Force health probe to fail
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        state = engine.get_state(type_id)

        assert state is not None
        assert state.source == "meta_json_fallback"
        assert state.feature_type_id == type_id
        # Phase derived from .meta.json: active + lastCompletedPhase=design -> next=create-plan
        assert state.current_phase == "create-plan"
        assert state.last_completed_phase == "design"

    def test_probe_fails_no_meta_json_returns_none(self, tmp_path) -> None:
        """When probe fails and no .meta.json exists, get_state returns None."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        state = engine.get_state(type_id)

        assert state is None

    def test_probe_passes_db_query_raises_secondary_defense(
        self, tmp_path, monkeypatch
    ) -> None:
        """When probe passes but db.get_workflow_phase raises sqlite3.Error,
        secondary defense catches it and falls back to .meta.json."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        _create_meta_json(
            tmp_path,
            "008-test-feature",
            status="active",
            last_completed_phase="specify",
        )
        # Probe passes (DB is actually healthy) but query raises
        monkeypatch.setattr(
            db,
            "get_workflow_phase",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.OperationalError("disk I/O error")
            ),
        )

        state = engine.get_state(type_id)

        assert state is not None
        assert state.source == "meta_json_fallback"
        assert state.current_phase == "design"
        assert state.last_completed_phase == "specify"

    def test_probe_passes_db_query_raises_no_meta_json(
        self, tmp_path, monkeypatch
    ) -> None:
        """When probe passes, DB query raises, and no .meta.json exists,
        secondary defense returns None."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        monkeypatch.setattr(
            db,
            "get_workflow_phase",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.DatabaseError("file is not a database")
            ),
        )

        state = engine.get_state(type_id)

        assert state is None

    def test_happy_path_unchanged(self, tmp_path) -> None:
        """When DB is healthy, get_state returns from DB as before."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )

        state = engine.get_state(type_id)

        assert state is not None
        assert state.source == "db"
        assert state.current_phase == "design"
        assert state.last_completed_phase == "specify"

    def test_probe_fails_logs_to_stderr(self, tmp_path, capsys) -> None:
        """When probe fails, a degradation message is logged to stderr."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        _create_meta_json(
            tmp_path,
            "008-test-feature",
            status="active",
            last_completed_phase="design",
        )
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        engine.get_state(type_id)

        captured = capsys.readouterr()
        assert "DB unhealthy" in captured.err
        assert type_id in captured.err

    def test_secondary_defense_logs_to_stderr(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        """When secondary defense catches sqlite3.Error, it logs to stderr."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        _create_meta_json(
            tmp_path,
            "008-test-feature",
            status="active",
            last_completed_phase="specify",
        )
        monkeypatch.setattr(
            db,
            "get_workflow_phase",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.OperationalError("database is locked")
            ),
        )

        engine.get_state(type_id)

        captured = capsys.readouterr()
        assert "DB error in get_state" in captured.err
        assert "database is locked" in captured.err
        assert type_id in captured.err


# ---------------------------------------------------------------------------
# TransitionPhase Fallback
# ---------------------------------------------------------------------------


class TestTransitionPhaseFallback:
    """transition_phase() degrades gracefully when DB is unavailable."""

    def test_probe_fail_returns_degraded_response(self, tmp_path) -> None:
        """When _check_db_health returns False, transition_phase returns
        TransitionResponse with degraded=True."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # Create .meta.json so the fallback get_state can read it
        _create_meta_json(
            tmp_path,
            "008-test-feature",
            status="active",
            last_completed_phase="brainstorm",
        )
        # Force health probe to fail -- get_state will use .meta.json fallback
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        response = engine.transition_phase(type_id, "specify")

        assert isinstance(response, TransitionResponse)
        assert response.degraded is True
        assert isinstance(response.results, tuple)
        assert len(response.results) > 0

    def test_db_write_fail_returns_degraded_response(
        self, tmp_path, monkeypatch
    ) -> None:
        """When probe passes but db.update_workflow_phase raises sqlite3.Error,
        transition_phase returns TransitionResponse with degraded=True."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # Create .meta.json (needed as secondary fallback data source)
        _create_meta_json(
            tmp_path,
            "008-test-feature",
            status="active",
            last_completed_phase="brainstorm",
        )
        # Create spec.md so the hard prerequisite for "design" is satisfied
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        # Probe passes (DB is healthy for reads) but write raises
        monkeypatch.setattr(
            db,
            "update_workflow_phase",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.OperationalError("database is locked")
            ),
        )

        response = engine.transition_phase(type_id, "design")

        assert isinstance(response, TransitionResponse)
        assert response.degraded is True
        assert isinstance(response.results, tuple)
        # The transition should still be "allowed" from gate evaluation
        assert all(r.allowed for r in response.results)


class TestCompletePhaseFallback:
    """complete_phase() degrades gracefully when DB is unavailable."""

    def test_db_write_fail_falls_back_to_meta_json(
        self, tmp_path, monkeypatch
    ) -> None:
        """When db.update_workflow_phase raises sqlite3.Error,
        complete_phase falls back to _write_meta_json_fallback and returns
        source='meta_json_fallback'."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # .meta.json must exist for the fallback writer
        _create_meta_json(
            tmp_path,
            "008-test-feature",
            status="active",
            last_completed_phase="brainstorm",
        )

        # Probe passes (DB healthy for reads) but write raises
        monkeypatch.setattr(
            db,
            "update_workflow_phase",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.OperationalError("database is locked")
            ),
        )

        state = engine.complete_phase(type_id, "specify")

        assert state.source == "meta_json_fallback"
        assert state.last_completed_phase == "specify"
        assert state.current_phase == "design"
        assert "specify" in state.completed_phases

    def test_probe_fail_uses_meta_json_fallback(self, tmp_path) -> None:
        """When _check_db_health returns False (probe fail), complete_phase
        skips DB write entirely and writes to .meta.json."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        _create_meta_json(
            tmp_path,
            "008-test-feature",
            status="active",
            last_completed_phase="brainstorm",
        )
        # Force health probe to fail -- get_state returns meta_json_fallback
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        state = engine.complete_phase(type_id, "specify")

        assert state.source == "meta_json_fallback"
        assert state.last_completed_phase == "specify"
        assert state.current_phase == "design"

    def test_db_write_succeeds_readback_fails_returns_source_db(
        self, tmp_path, monkeypatch
    ) -> None:
        """When DB write succeeds but get_workflow_phase would fail on a
        hypothetical read-back, complete_phase still returns source='db'
        because it derives state from params rather than reading back.

        Uses a call-counting wrapper: first call to get_workflow_phase
        (inside get_state) succeeds normally; subsequent calls raise
        sqlite3.Error -- simulating DB degrading after initial read."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )

        original_get_wp = db.get_workflow_phase
        call_count = 0

        def get_wp_after_first_fails(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise sqlite3.OperationalError("disk I/O error")
            return original_get_wp(*a, **kw)

        # Let update_workflow_phase succeed (no-op)
        monkeypatch.setattr(
            db,
            "update_workflow_phase",
            lambda *a, **kw: None,
        )
        # First get_workflow_phase call (in get_state) succeeds;
        # any subsequent call would raise
        monkeypatch.setattr(
            db,
            "get_workflow_phase",
            get_wp_after_first_fails,
        )

        state = engine.complete_phase(type_id, "specify")

        # Should still succeed with source="db" since complete_phase
        # derives state from params, not from a DB read-back
        assert state.source == "db"
        assert state.last_completed_phase == "specify"
        assert state.current_phase == "design"

    def test_happy_path_unchanged(self, tmp_path) -> None:
        """Normal complete_phase still returns source='db' when everything works."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )

        state = engine.complete_phase(type_id, "specify")

        assert state.source == "db"
        assert state.last_completed_phase == "specify"
        assert state.current_phase == "design"

    def test_fallback_sets_started_when_missing(self, tmp_path) -> None:
        """When fallback writes to .meta.json and phase has no 'started'
        timestamp, it adds one (spec R2, design I4)."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # Create .meta.json with no 'started' on the specify phase
        _create_meta_json(
            tmp_path,
            "008-test-feature",
            status="active",
            last_completed_phase="brainstorm",
        )
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        engine.complete_phase(type_id, "specify")

        meta_path = tmp_path / "features" / "008-test-feature" / ".meta.json"
        meta = json.loads(meta_path.read_text())
        phase_obj = meta["phases"]["specify"]
        assert "started" in phase_obj, "started timestamp must be set when missing"
        assert "completed" in phase_obj

    def test_fallback_preserves_existing_started(self, tmp_path) -> None:
        """When fallback writes to .meta.json and phase already has 'started',
        it preserves the original value."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        original_started = "2026-01-01T00:00:00+00:00"
        meta = {
            "id": "008",
            "slug": "test-feature",
            "status": "active",
            "lastCompletedPhase": "brainstorm",
            "phases": {"specify": {"started": original_started}},
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        engine.complete_phase(type_id, "specify")

        updated = json.loads((feature_dir / ".meta.json").read_text())
        assert updated["phases"]["specify"]["started"] == original_started


# ===========================================================================
# Task 4.4: list_by_phase() fallback
# ===========================================================================


class TestListByStatusFallback:
    """list_by_status() degrades gracefully when DB is unavailable."""

    def test_probe_fail_returns_filesystem_results(self, tmp_path) -> None:
        """When _check_db_health returns False, list_by_status scans .meta.json
        files filtered by status, returning source='meta_json_fallback'."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        # Create .meta.json files: two active, one planned
        _create_meta_json(
            tmp_path, "001-alpha", status="active", last_completed_phase="brainstorm"
        )
        _create_meta_json(
            tmp_path, "002-beta", status="active", last_completed_phase=None
        )
        _create_meta_json(
            tmp_path, "003-gamma", status="planned"
        )

        # Force probe failure
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        results = engine.list_by_status("active")

        assert len(results) == 2
        assert all(r.source == "meta_json_fallback" for r in results)
        type_ids = {r.feature_type_id for r in results}
        assert "feature:001-alpha" in type_ids
        assert "feature:002-beta" in type_ids
        assert "feature:003-gamma" not in type_ids

    def test_happy_path_unchanged(self, tmp_path) -> None:
        """Normal list_by_status still returns source='db' results."""
        db = _make_db()
        tid1 = _register_feature(db, "001-active", status="active")
        db.create_workflow_phase(tid1, workflow_phase="design")
        tid2 = _register_feature(db, "002-active", status="active")
        db.create_workflow_phase(tid2, workflow_phase="specify")
        _register_feature(db, "003-completed", status="completed")

        engine = WorkflowStateEngine(db, str(tmp_path))
        results = engine.list_by_status("active")

        assert len(results) == 2
        assert all(r.source == "db" for r in results)
        type_ids = {r.feature_type_id for r in results}
        assert tid1 in type_ids
        assert tid2 in type_ids


class TestListByPhaseFallback:
    """list_by_phase() degrades gracefully when DB is unavailable."""

    def test_probe_fail_returns_filesystem_results(self, tmp_path) -> None:
        """When _check_db_health returns False, list_by_phase scans .meta.json
        files and filters by current_phase == phase, returning
        source='meta_json_fallback'."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        # Create .meta.json files: two in "specify", one in "design"
        _create_meta_json(
            tmp_path, "001-alpha", status="active", last_completed_phase="brainstorm"
        )  # current_phase => "specify"
        _create_meta_json(
            tmp_path, "002-beta", status="active", last_completed_phase="brainstorm"
        )  # current_phase => "specify"
        _create_meta_json(
            tmp_path, "003-gamma", status="active", last_completed_phase="specify"
        )  # current_phase => "design"

        # Force probe failure
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        results = engine.list_by_phase("specify")

        assert len(results) == 2
        assert all(r.current_phase == "specify" for r in results)
        assert all(r.source == "meta_json_fallback" for r in results)
        type_ids = {r.feature_type_id for r in results}
        assert "feature:001-alpha" in type_ids
        assert "feature:002-beta" in type_ids

    def test_db_query_raises_returns_filesystem_results(
        self, tmp_path, monkeypatch
    ) -> None:
        """When list_workflow_phases raises sqlite3.Error, list_by_phase
        falls back to filesystem scan filtered by phase."""
        engine, db, _ = _setup_engine(
            tmp_path, "001-alpha", workflow_phase="specify", last_completed_phase="brainstorm"
        )
        _create_meta_json(
            tmp_path, "001-alpha", status="active", last_completed_phase="brainstorm"
        )  # current_phase => "specify"

        monkeypatch.setattr(
            db,
            "list_workflow_phases",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.OperationalError("disk I/O error")
            ),
        )

        results = engine.list_by_phase("specify")

        assert len(results) == 1
        assert results[0].feature_type_id == "feature:001-alpha"
        assert results[0].current_phase == "specify"
        assert results[0].source == "meta_json_fallback"

    def test_happy_path_unchanged(self, tmp_path) -> None:
        """Normal list_by_phase still returns source='db' results."""
        db = _make_db()
        for i, phase in enumerate(["specify", "specify", "design"]):
            slug = f"00{i}-feat"
            tid = _register_feature(db, slug)
            db.create_workflow_phase(tid, workflow_phase=phase)

        engine = WorkflowStateEngine(db, str(tmp_path))
        results = engine.list_by_phase("specify")

        assert len(results) == 2
        assert all(r.current_phase == "specify" for r in results)
        assert all(r.source == "db" for r in results)


# ===========================================================================
# Phase 6 (Task 6.1): Integration Tests — Degradation Path
# ===========================================================================


class TestIntegrationDegradation:
    """Task 6.1: End-to-end degradation path integration tests.

    Each test creates a fully seeded DB+entity+meta.json, then closes the DB
    connection to trigger the degraded-mode fallback path.
    """

    def test_get_state_fallback_after_db_close(self, tmp_path) -> None:
        """Full workflow: create feature in DB -> close DB -> get_state() returns meta_json_fallback.

        Covers: _check_db_health() returning False -> _read_state_from_meta_json path.
        """
        db = EntityDatabase(":memory:")
        slug = "009-integration-get-state"
        type_id = f"feature:{slug}"
        db.register_entity(
            entity_type="feature",
            entity_id=slug,
            name="Integration Get State Test",
            status="active",
            project_id="__unknown__",
        )
        db.create_workflow_phase(
            type_id,
            workflow_phase="design",
            last_completed_phase="specify",
            mode="standard",
        )

        # Create .meta.json so fallback can read it
        feature_dir = tmp_path / "features" / slug
        feature_dir.mkdir(parents=True)
        _create_meta_json(
            tmp_path,
            slug,
            status="active",
            mode="standard",
            last_completed_phase="specify",
        )

        engine = WorkflowStateEngine(db, str(tmp_path))

        # Verify DB path works before closing
        state_before = engine.get_state(type_id)
        assert state_before is not None
        assert state_before.source == "db"

        # Close the DB to force degradation
        db.close()

        # get_state should now fall back to .meta.json
        state_after = engine.get_state(type_id)
        assert state_after is not None
        assert state_after.source == "meta_json_fallback"
        # Fallback reads from .meta.json: lastCompletedPhase="specify" -> current="design"
        assert state_after.last_completed_phase == "specify"
        assert state_after.current_phase == "design"

    def test_complete_phase_fallback_writes_meta_json(self, tmp_path) -> None:
        """Full workflow: create feature in DB -> close DB -> complete_phase() writes .meta.json.

        Covers: complete_phase() detecting source='meta_json_fallback' and calling
        _write_meta_json_fallback() instead of updating the DB.
        """
        db = EntityDatabase(":memory:")
        slug = "009-integration-complete"
        type_id = f"feature:{slug}"
        db.register_entity(
            entity_type="feature",
            entity_id=slug,
            name="Integration Complete Phase Test",
            status="active",
            project_id="__unknown__",
        )
        db.create_workflow_phase(
            type_id,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
            mode="standard",
        )

        # Create .meta.json so degraded mode can operate
        feature_dir = tmp_path / "features" / slug
        feature_dir.mkdir(parents=True)
        _create_meta_json(
            tmp_path,
            slug,
            status="active",
            mode="standard",
            last_completed_phase="brainstorm",
        )

        engine = WorkflowStateEngine(db, str(tmp_path))

        # Close the DB to force degradation
        db.close()

        # complete_phase should fall back to writing .meta.json
        state = engine.complete_phase(type_id, "specify")

        # Verify returned state reflects the completion
        assert state.source == "meta_json_fallback"
        assert state.last_completed_phase == "specify"
        assert state.current_phase == "design"  # next after specify

        # Verify .meta.json was actually written with updated phase
        import json as _json

        meta_path = feature_dir / ".meta.json"
        with open(meta_path) as f:
            meta = _json.load(f)

        assert meta["lastCompletedPhase"] == "specify"
        assert "specify" in meta.get("phases", {})
        assert meta["phases"]["specify"]["completed"] is not None

    def test_list_by_phase_fallback_filesystem_scan(self, tmp_path) -> None:
        """Full workflow: create features in DB -> close DB -> list_by_phase() uses filesystem scan.

        Covers: list_by_phase() detecting unhealthy DB -> _scan_features_filesystem()
        filtering by current_phase.
        """
        db = EntityDatabase(":memory:")

        # Seed 3 features: 2 in "specify" (via meta), 1 in "design"
        # last_completed="brainstorm" -> next phase = "specify"
        # last_completed="specify"   -> next phase = "design"
        for slug, last_completed in [
            ("009-lbp-alpha", "brainstorm"),
            ("009-lbp-beta", "brainstorm"),
            ("009-lbp-gamma", "specify"),
        ]:
            type_id = f"feature:{slug}"
            db.register_entity(
                entity_type="feature",
                entity_id=slug,
                name=f"Test {slug}",
                status="active",
                project_id="__unknown__",
            )
            # Use the correct next-phase value matching what the meta.json will report
            next_phase = "specify" if last_completed == "brainstorm" else "design"
            db.create_workflow_phase(
                type_id,
                workflow_phase=next_phase,
                last_completed_phase=last_completed,
                mode="standard",
            )
            _create_meta_json(
                tmp_path,
                slug,
                status="active",
                mode="standard",
                last_completed_phase=last_completed,
            )

        engine = WorkflowStateEngine(db, str(tmp_path))

        # Close the DB to force degradation
        db.close()

        # list_by_phase should scan filesystem
        # last_completed="brainstorm" -> current_phase="specify" (next after brainstorm)
        results = engine.list_by_phase("specify")

        assert len(results) == 2
        assert all(r.current_phase == "specify" for r in results)
        assert all(r.source == "meta_json_fallback" for r in results)
        slugs = {r.feature_type_id for r in results}
        assert "feature:009-lbp-alpha" in slugs
        assert "feature:009-lbp-beta" in slugs

    def test_list_by_status_fallback_filesystem_scan(self, tmp_path) -> None:
        """Full workflow: create features in DB -> close DB -> list_by_status() uses filesystem scan.

        Covers: list_by_status() detecting unhealthy DB -> _scan_features_by_status()
        filtering by .meta.json status field.
        """
        db = EntityDatabase(":memory:")

        # Seed: 2 active, 1 completed
        for slug, status, last_completed in [
            ("009-lbs-active1", "active", "specify"),
            ("009-lbs-active2", "active", "brainstorm"),
            ("009-lbs-done", "completed", "finish"),
        ]:
            type_id = f"feature:{slug}"
            db.register_entity(
                entity_type="feature",
                entity_id=slug,
                name=f"Test {slug}",
                status=status,
                project_id="__unknown__",
            )
            _create_meta_json(
                tmp_path,
                slug,
                status=status,
                mode="standard",
                last_completed_phase=last_completed,
            )

        engine = WorkflowStateEngine(db, str(tmp_path))

        # Close the DB to force degradation
        db.close()

        # list_by_status("active") should return only the 2 active features
        results = engine.list_by_status("active")

        assert len(results) == 2
        assert all(r.source == "meta_json_fallback" for r in results)
        slugs = {r.feature_type_id for r in results}
        assert "feature:009-lbs-active1" in slugs
        assert "feature:009-lbs-active2" in slugs
        assert "feature:009-lbs-done" not in slugs

        # list_by_status("completed") should return only the completed feature
        results_done = engine.list_by_status("completed")
        assert len(results_done) == 1
        assert results_done[0].feature_type_id == "feature:009-lbs-done"
        assert results_done[0].current_phase == "finish"


# ===========================================================================
# Phase 6 (Task 6.1): Health Probe Performance
# ===========================================================================


class TestHealthProbePerformance:
    """Task 6.1: _check_db_health() performance contract.

    1000 iterations must complete with mean < 1ms using an in-memory SQLite DB.
    """

    def test_health_probe_1000_iterations_under_1ms_mean(self) -> None:
        """Performance: 1000 _check_db_health() calls must average < 1ms each.

        Uses an in-memory DB (:memory:) to isolate probe latency from disk I/O.
        Acceptable on any modern machine -- SELECT 1 on a healthy in-memory
        connection is typically sub-10us.
        """
        import time

        db = EntityDatabase(":memory:")
        engine = WorkflowStateEngine(db, "/tmp")

        # Warm-up: let SQLite and Python reach steady state
        for _ in range(10):
            engine._check_db_health()

        # Time 1000 iterations
        iterations = 1000
        start = time.perf_counter()
        for _ in range(iterations):
            result = engine._check_db_health()
        elapsed_s = time.perf_counter() - start

        assert result is True  # Verify the probe returns correct value
        mean_ms = (elapsed_s / iterations) * 1000
        assert mean_ms < 1.0, (
            f"_check_db_health() mean latency {mean_ms:.3f}ms exceeds 1ms threshold "
            f"over {iterations} iterations"
        )


# ===========================================================================
# Phase 8b: Test-Deepener Feature 010 (Graceful Degradation)
# ===========================================================================


class TestDegradedGetStateCatchesSqliteSubclasses:
    """Dimension 5 (mutation mindset): Verify get_state catches all sqlite3.Error
    subclasses, not just the base class.

    Anticipate: If the except clause used a specific subclass like
    sqlite3.OperationalError instead of sqlite3.Error, other subclasses
    (DatabaseError, InterfaceError, ProgrammingError) would propagate uncaught.
    derived_from: dimension:mutation_mindset (error type classification)
    """

    def test_catches_database_error(self, tmp_path, monkeypatch) -> None:
        """get_state catches sqlite3.DatabaseError (subclass of sqlite3.Error).
        derived_from: dimension:mutation_mindset (catches all sqlite3.Error subclasses)
        """
        # Given a healthy engine with meta.json fallback available
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        _create_meta_json(
            tmp_path, "008-test-feature", status="active",
            last_completed_phase="specify",
        )
        # When DB raises DatabaseError on query
        monkeypatch.setattr(
            db, "get_workflow_phase",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.DatabaseError("file is not a database")
            ),
        )
        # Then get_state catches it and falls back to meta_json
        state = engine.get_state(type_id)
        assert state is not None
        assert state.source == "meta_json_fallback"

    def test_catches_interface_error(self, tmp_path, monkeypatch) -> None:
        """get_state catches sqlite3.InterfaceError (subclass of sqlite3.Error).
        derived_from: dimension:mutation_mindset (catches all sqlite3.Error subclasses)
        """
        # Given a healthy engine with meta.json fallback available
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        _create_meta_json(
            tmp_path, "008-test-feature", status="active",
            last_completed_phase="specify",
        )
        # When DB raises InterfaceError on query
        monkeypatch.setattr(
            db, "get_workflow_phase",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.InterfaceError("binding mismatch")
            ),
        )
        # Then get_state catches it and falls back to meta_json
        state = engine.get_state(type_id)
        assert state is not None
        assert state.source == "meta_json_fallback"

    def test_does_not_re_raise_sqlite_error(self, tmp_path, monkeypatch) -> None:
        """get_state NEVER re-raises sqlite3.Error -- it always falls back gracefully.
        derived_from: dimension:adversarial (does not re-raise sqlite error)

        Anticipate: If the except clause accidentally had a `raise` or
        was missing entirely, sqlite errors would propagate to the caller.
        """
        # Given a healthy engine with meta.json fallback available
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        _create_meta_json(
            tmp_path, "008-test-feature", status="active",
            last_completed_phase="specify",
        )
        # When DB raises sqlite3.Error on query
        monkeypatch.setattr(
            db, "get_workflow_phase",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.Error("generic sqlite error")
            ),
        )
        # Then get_state does NOT raise -- it returns a state or None
        state = engine.get_state(type_id)
        # Should be meta_json_fallback (not raised, not None since meta.json exists)
        assert state is not None
        assert state.source == "meta_json_fallback"


class TestHealthProbePerCallNotCached:
    """Dimension 5 (mutation mindset): Verify _check_db_health is called per-call,
    not cached from a previous invocation.

    Anticipate: If health was cached at construction time or memoized, a DB that
    becomes unhealthy after the first call would not be detected.
    derived_from: dimension:mutation_mindset (per-call health probe)
    """

    def test_probe_called_fresh_each_time(self, tmp_path, monkeypatch) -> None:
        """Health probe must be invoked on each get_state call.

        First call: DB healthy -> returns source='db'.
        Second call: DB unhealthy -> returns source='meta_json_fallback'.
        """
        # Given a healthy engine
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        _create_meta_json(
            tmp_path, "008-test-feature", status="active",
            last_completed_phase="specify",
        )

        # When first call: DB healthy
        state1 = engine.get_state(type_id)
        assert state1 is not None
        assert state1.source == "db"

        # When DB becomes unhealthy between calls
        db.close()

        # Then second call detects the unhealthy DB
        state2 = engine.get_state(type_id)
        assert state2 is not None
        assert state2.source == "meta_json_fallback"

    def test_probe_recovery_after_unhealthy(self, tmp_path, monkeypatch) -> None:
        """Health probe detects recovery: unhealthy -> healthy.

        Uses monkeypatch to simulate probe failure then removal.
        """
        # Given a healthy engine
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        _create_meta_json(
            tmp_path, "008-test-feature", status="active",
            last_completed_phase="specify",
        )

        # When probe is temporarily unhealthy
        original_check = engine._check_db_health
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        state1 = engine.get_state(type_id)
        assert state1 is not None
        assert state1.source == "meta_json_fallback"

        # When probe recovers
        engine._check_db_health = original_check  # type: ignore[assignment]

        state2 = engine.get_state(type_id)
        assert state2 is not None
        assert state2.source == "db"


class TestTransitionPhaseDualConditionDegraded:
    """Dimension 5 (mutation mindset): transition_phase has TWO degradation paths:
    1. Primary: get_state returns source='meta_json_fallback' -> skip DB write
    2. Secondary: DB write fails with sqlite3.Error -> return degraded=True

    Both must set degraded=True. Deleting either path would miss degradation.
    derived_from: dimension:mutation_mindset (dual-condition degraded)
    """

    def test_primary_defense_source_check_sets_degraded(self, tmp_path) -> None:
        """When get_state returns meta_json_fallback, transition sets degraded=True
        WITHOUT attempting a DB write.
        derived_from: dimension:mutation_mindset (dual-condition degraded: primary)
        """
        # Given engine with probe failure -> get_state returns meta_json_fallback
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        _create_meta_json(
            tmp_path, "008-test-feature", status="active",
            last_completed_phase="brainstorm",
        )
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        # Track whether update_workflow_phase was called
        update_called = []
        original_update = db.update_workflow_phase

        def tracking_update(*a, **kw):
            update_called.append(True)
            return original_update(*a, **kw)

        db.update_workflow_phase = tracking_update  # type: ignore[assignment]

        # When transitioning
        response = engine.transition_phase(type_id, "specify")

        # Then degraded=True and DB write was NOT attempted
        assert response.degraded is True
        assert len(update_called) == 0, "DB write should not be attempted in primary defense"

    def test_secondary_defense_write_fail_sets_degraded(
        self, tmp_path, monkeypatch
    ) -> None:
        """When get_state returns source='db' but DB write fails,
        transition sets degraded=True.
        derived_from: dimension:mutation_mindset (dual-condition degraded: secondary)
        """
        # Given engine with healthy probe but write failure
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        monkeypatch.setattr(
            db, "update_workflow_phase",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.OperationalError("disk full")
            ),
        )

        # When transitioning (all gates pass because spec.md exists)
        response = engine.transition_phase(type_id, "design")

        # Then degraded=True from secondary defense
        assert response.degraded is True
        assert all(r.allowed for r in response.results)

    def test_normal_path_not_degraded(self, tmp_path) -> None:
        """When both probe and write succeed, degraded=False.
        derived_from: dimension:mutation_mindset (return value mutation)
        """
        # Given a fully healthy engine
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        # When transitioning successfully
        response = engine.transition_phase(type_id, "design")

        # Then degraded=False
        assert response.degraded is False
        assert all(r.allowed for r in response.results)


class TestCompletePhaseFallbackWriteVsRead:
    """Dimension 4 (error propagation): complete_phase distinguishes between
    read-failure (meta.json unreadable) and write-success-but-degraded.

    derived_from: dimension:error_propagation (error type classification)
    """

    def test_fallback_write_unreadable_meta_raises_value_error(
        self, tmp_path
    ) -> None:
        """When DB is degraded and meta.json is unreadable, complete_phase raises
        ValueError (not silently returning None or corrupt state).
        derived_from: dimension:adversarial (meta.json unreadable raises ValueError)
        """
        # Given engine with probe failure and corrupt meta.json
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        # Create corrupt .meta.json
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / ".meta.json").write_text("{corrupt json!!!")
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        # When completing phase -- get_state returns None (corrupt meta)
        # Then ValueError is raised (feature not found)
        with pytest.raises(ValueError, match="Feature not found"):
            engine.complete_phase(type_id, "specify")

    def test_fallback_write_success_returns_correct_state(
        self, tmp_path
    ) -> None:
        """When DB is degraded but meta.json is readable, complete_phase
        writes fallback and returns FeatureWorkflowState with source='meta_json_fallback'.
        derived_from: dimension:error_propagation (partial failure consistency)
        """
        # Given engine with probe failure and valid meta.json
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        _create_meta_json(
            tmp_path, "008-test-feature", status="active",
            last_completed_phase="brainstorm",
        )
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        # When completing phase
        state = engine.complete_phase(type_id, "specify")

        # Then state is correct with fallback source
        assert state.source == "meta_json_fallback"
        assert state.last_completed_phase == "specify"
        assert state.current_phase == "design"
        assert state.completed_phases == ("brainstorm", "specify")

        # And meta.json was actually updated
        meta_path = tmp_path / "features" / "008-test-feature" / ".meta.json"
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["lastCompletedPhase"] == "specify"


class TestListByStatusDbQueryRaisesFallback:
    """Dimension 4 (error propagation): list_by_status falls back to filesystem
    when DB query raises sqlite3.Error after probe passes.

    Anticipate: If secondary defense is missing in list_by_status,
    a late DB error after successful probe would propagate uncaught.
    derived_from: dimension:error_propagation (upstream dependency failure)
    """

    def test_list_entities_raises_falls_back_to_filesystem(
        self, tmp_path, monkeypatch
    ) -> None:
        """When db.list_entities raises sqlite3.Error, list_by_status
        falls back to _scan_features_by_status.
        """
        # Given engine with features in meta.json
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        _create_meta_json(
            tmp_path, "008-test-feature", status="active",
            last_completed_phase="specify",
        )

        # When list_entities raises on query
        monkeypatch.setattr(
            db, "list_entities",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.OperationalError("table locked")
            ),
        )

        # Then list_by_status falls back to filesystem scan
        results = engine.list_by_status("active")
        assert len(results) >= 1
        assert all(r.source == "meta_json_fallback" for r in results)

    def test_fallback_logs_to_stderr(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        """When list_by_status falls back, it logs the error to stderr.
        derived_from: dimension:adversarial (stderr-only logging)
        """
        # Given engine with features in meta.json
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="design",
            last_completed_phase="specify",
        )
        _create_meta_json(
            tmp_path, "008-test-feature", status="active",
            last_completed_phase="specify",
        )

        # When list_entities raises on query
        monkeypatch.setattr(
            db, "list_entities",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.OperationalError("database is locked")
            ),
        )

        engine.list_by_status("active")

        captured = capsys.readouterr()
        assert "DB error in list_by_status" in captured.err
        assert "database is locked" in captured.err


class TestTransitionPhaseNoDoubleWrite:
    """Dimension 5 (mutation mindset): When gates block the transition,
    update_workflow_phase must NOT be called.

    Anticipate: If update_workflow_phase is called before the gate check
    (or unconditionally), a blocked transition would still mutate DB state.
    derived_from: dimension:mutation_mindset (no double-write)
    """

    def test_blocked_transition_does_not_call_update(
        self, tmp_path, monkeypatch
    ) -> None:
        """When any gate blocks, update_workflow_phase is never called.
        """
        # Given a feature missing spec.md (G-08 blocks design transition)
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )

        update_calls = []
        original_update = db.update_workflow_phase

        def tracking_update(*a, **kw):
            update_calls.append((a, kw))
            return original_update(*a, **kw)

        monkeypatch.setattr(db, "update_workflow_phase", tracking_update)

        # When transitioning to design (blocked by G-08 -- no spec.md)
        response = engine.transition_phase(type_id, "design")

        # Then blocked and no update called
        blocked = [r for r in response.results if not r.allowed]
        assert len(blocked) > 0
        assert len(update_calls) == 0, (
            f"update_workflow_phase called {len(update_calls)} times "
            f"despite blocked transition"
        )

    def test_allowed_transition_calls_update_exactly_once(
        self, tmp_path, monkeypatch
    ) -> None:
        """When all gates pass, update_workflow_phase is called exactly once.
        derived_from: dimension:mutation_mindset (no double-write)
        """
        # Given a feature with spec.md present
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        update_calls = []
        original_update = db.update_workflow_phase

        def tracking_update(*a, **kw):
            update_calls.append((a, kw))
            return original_update(*a, **kw)

        monkeypatch.setattr(db, "update_workflow_phase", tracking_update)

        # When transitioning to design (allowed)
        response = engine.transition_phase(type_id, "design")

        # Then update called exactly once
        assert all(r.allowed for r in response.results)
        assert len(update_calls) == 1, (
            f"update_workflow_phase called {len(update_calls)} times, expected 1"
        )


class TestSchemaNotModifiedDuringDegradation:
    """Dimension 3 (adversarial): Degraded-mode operations must not accidentally
    modify the DB schema or create tables/indices.

    Anticipate: If a degraded-mode code path calls create_workflow_phase or
    other DDL-triggering methods, it could corrupt the schema.
    derived_from: dimension:adversarial (schema not modified)
    """

    def test_get_state_degraded_does_not_create_workflow_phase_row(
        self, tmp_path
    ) -> None:
        """When get_state falls back to meta_json, it does NOT backfill a DB row.
        This is the key difference between _hydrate_from_meta_json (which backfills)
        and _read_state_from_meta_json (which does NOT backfill).
        """
        # Given engine with probe failure
        db = _make_db()
        type_id = _register_feature(db, "008-no-backfill")
        _create_meta_json(
            tmp_path, "008-no-backfill", status="active",
            last_completed_phase="specify",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        # Count existing workflow phase rows
        rows_before = db.list_workflow_phases()
        count_before = len(rows_before)

        # Force probe failure
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        # When getting state in degraded mode
        state = engine.get_state(type_id)
        assert state is not None
        assert state.source == "meta_json_fallback"

        # Then no new workflow_phase row was created
        # Re-enable probe to read DB
        engine._check_db_health = lambda: True  # type: ignore[assignment]
        rows_after = db.list_workflow_phases()
        count_after = len(rows_after)
        assert count_after == count_before, (
            f"Degraded get_state created {count_after - count_before} "
            f"workflow_phase rows"
        )


class TestValidatePrerequisitesDegradedMode:
    """Dimension 1 (BDD): validate_prerequisites works correctly in degraded mode.

    Anticipate: validate_prerequisites calls get_state internally. If get_state
    returns source='meta_json_fallback', validate should still return gate results
    (not raise or return empty).
    derived_from: spec:AC-6 (validate_prerequisites dry-run in degraded mode)
    """

    def test_returns_gate_results_when_degraded(self, tmp_path) -> None:
        """validate_prerequisites returns gate results even when DB is unhealthy.
        """
        # Given engine with probe failure
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        _create_meta_json(
            tmp_path, "008-test-feature", status="active",
            last_completed_phase="brainstorm",
        )
        engine._check_db_health = lambda: False  # type: ignore[assignment]

        # When validating prerequisites
        results = engine.validate_prerequisites(type_id, "specify")

        # Then gate results are returned (not empty, not error)
        assert len(results) > 0
        # Should have at minimum G-08 and G-23
        guard_ids = {r.guard_id for r in results}
        assert "G-08" in guard_ids
        assert "G-23" in guard_ids


class TestTransitionPhaseLogsWriteFailure:
    """Dimension 3 (adversarial): transition_phase logs DB write failure to stderr.

    derived_from: dimension:adversarial (stderr-only logging)
    """

    def test_write_failure_logged_to_stderr(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        """When DB write fails in transition_phase, error is logged to stderr.
        """
        # Given engine with healthy probe but write failure
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        feature_dir = tmp_path / "features" / "008-test-feature"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text("# Spec")

        monkeypatch.setattr(
            db, "update_workflow_phase",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.OperationalError("disk I/O error")
            ),
        )

        # When transitioning
        engine.transition_phase(type_id, "design")

        # Then error is logged to stderr
        captured = capsys.readouterr()
        assert "DB write failed in transition_phase" in captured.err
        assert "disk I/O error" in captured.err
        assert type_id in captured.err


class TestCompletePhaseFallbackLogsToStderr:
    """Dimension 3 (adversarial): complete_phase logs DB write failure to stderr.

    derived_from: dimension:adversarial (stderr-only logging)
    """

    def test_write_failure_logged_to_stderr(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        """When DB write fails in complete_phase, error is logged to stderr.
        """
        # Given engine with healthy probe but write failure
        engine, db, type_id = _setup_engine(
            tmp_path,
            workflow_phase="specify",
            last_completed_phase="brainstorm",
        )
        _create_meta_json(
            tmp_path, "008-test-feature", status="active",
            last_completed_phase="brainstorm",
        )
        monkeypatch.setattr(
            db, "update_workflow_phase",
            lambda *a, **kw: (_ for _ in ()).throw(
                sqlite3.OperationalError("disk full")
            ),
        )

        # When completing phase
        engine.complete_phase(type_id, "specify")

        # Then error is logged to stderr
        captured = capsys.readouterr()
        assert "DB write failed in complete_phase" in captured.err
        assert "disk full" in captured.err
        assert type_id in captured.err


# ===========================================================================
# Feature 036: Kanban Column Lifecycle Fix
# ===========================================================================


class TestDegradedModeBackfillSetsKanbanFromPhase:
    """Backfill via _hydrate_from_meta_json should derive kanban_column from
    the current phase using derive_kanban, not default to 'backlog'.

    derived_from: feature:036, requirement:R8
    """

    def test_degraded_mode_backfill_sets_kanban_from_phase(
        self, tmp_path
    ) -> None:
        """When get_state triggers hydration from .meta.json with
        last_completed_phase='design', current_phase resolves to 'create-plan'
        and kanban_column should be 'prioritised' (not 'backlog').
        """
        # Given: DB with registered entity, no workflow_phases row,
        # and .meta.json with last_completed_phase="design"
        db = _make_db()
        slug = "036-kanban-fix"
        type_id = _register_feature(db, slug)
        _create_meta_json(
            tmp_path, slug, status="active",
            last_completed_phase="design",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        # When: get_state triggers degraded-mode backfill (no DB row exists)
        state = engine.get_state(type_id)

        # Then: state was hydrated successfully
        assert state is not None
        assert state.current_phase == "create-plan"

        # And: the backfilled DB row has kanban_column derived from the phase
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["kanban_column"] == "prioritised"


class TestDegradedModeBackfillSetsKanbanFromPhaseDeepened:
    """Deepened tests for degraded-mode backfill kanban column derivation.

    Tests additional phases beyond create-plan to ensure derive_kanban
    is consistently applied during hydration from .meta.json.

    derived_from: feature:036, dimension:bdd_scenarios, dimension:boundary_values
    """

    def test_degraded_backfill_implement_phase_sets_wip(self, tmp_path) -> None:
        """Backfill with last_completed_phase='create-plan' resolves to
        current_phase='implement' and kanban_column should be 'wip'.

        Anticipate: If derive_kanban is missing 'implement' mapping or
        the backfill defaults to 'backlog', this test catches it.
        derived_from: spec:R8 (degraded backfill kanban)
        """
        # Given: registered entity, no workflow_phases row,
        # .meta.json with last_completed_phase="create-plan"
        db = _make_db()
        slug = "036-backfill-impl"
        type_id = _register_feature(db, slug)
        _create_meta_json(
            tmp_path, slug, status="active",
            last_completed_phase="create-plan",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        # When: get_state triggers hydration
        state = engine.get_state(type_id)

        # Then: current_phase is 'implement', kanban is 'wip'
        assert state is not None
        assert state.current_phase == "implement"
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["kanban_column"] == "wip"

    def test_degraded_backfill_finish_phase_sets_documenting(self, tmp_path) -> None:
        """Backfill with last_completed_phase='implement' resolves to
        current_phase='finish' and kanban_column should be 'documenting'.

        Anticipate: If the code maps finish to 'completed' without checking
        last_completed_phase, this test catches it. Backfill should use
        derive_kanban which maps finish -> 'documenting'.
        derived_from: spec:R8 (degraded backfill kanban)
        """
        # Given: registered entity, no workflow_phases row,
        # .meta.json with last_completed_phase="implement"
        db = _make_db()
        slug = "036-backfill-finish"
        type_id = _register_feature(db, slug)
        _create_meta_json(
            tmp_path, slug, status="active",
            last_completed_phase="implement",
        )
        engine = WorkflowStateEngine(db, str(tmp_path))

        # When: get_state triggers hydration
        state = engine.get_state(type_id)

        # Then: current_phase is 'finish', kanban is 'documenting'
        assert state is not None
        assert state.current_phase == "finish"
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["kanban_column"] == "documenting"
