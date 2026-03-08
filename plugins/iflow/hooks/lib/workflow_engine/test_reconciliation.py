"""Tests for workflow_engine.reconciliation -- Tasks 1.1, 1.2, 2.1-2.3, 3.1-3.2, 7.1."""
from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from entity_registry.database import EntityDatabase
from workflow_engine.engine import WorkflowStateEngine
from workflow_engine.reconciliation import (
    ReconcileAction,
    ReconciliationResult,
    WorkflowDriftReport,
    WorkflowDriftResult,
    WorkflowMismatch,
    _check_single_feature,
    _compare_phases,
    _derive_expected_kanban,
    _phase_index,
    _read_single_meta_json,
    _reconcile_single_feature,
    apply_workflow_reconciliation,
    check_workflow_drift,
)


# ---------------------------------------------------------------------------
# Helpers (matching test_engine.py patterns)
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
# Task 1.1: Dataclass definitions
# ===========================================================================


class TestWorkflowMismatch:
    """WorkflowMismatch frozen dataclass tests."""

    def test_construction(self) -> None:
        m = WorkflowMismatch(field="mode", meta_json_value="standard", db_value="full")
        assert m.field == "mode"
        assert m.meta_json_value == "standard"
        assert m.db_value == "full"

    def test_frozen(self) -> None:
        m = WorkflowMismatch(field="mode", meta_json_value="standard", db_value="full")
        with pytest.raises(FrozenInstanceError):
            m.field = "other"  # type: ignore[misc]

    def test_none_values(self) -> None:
        m = WorkflowMismatch(field="last_completed_phase", meta_json_value=None, db_value="design")
        assert m.meta_json_value is None
        assert m.db_value == "design"


class TestWorkflowDriftReport:
    """WorkflowDriftReport frozen dataclass tests."""

    def test_construction(self) -> None:
        r = WorkflowDriftReport(
            feature_type_id="feature:010-test",
            status="in_sync",
            meta_json={"workflow_phase": "design"},
            db={"workflow_phase": "design"},
            mismatches=(),
        )
        assert r.feature_type_id == "feature:010-test"
        assert r.status == "in_sync"
        assert r.meta_json == {"workflow_phase": "design"}
        assert r.db == {"workflow_phase": "design"}
        assert r.mismatches == ()
        assert r.message == ""

    def test_frozen(self) -> None:
        r = WorkflowDriftReport(
            feature_type_id="feature:010-test",
            status="in_sync",
            meta_json=None,
            db=None,
            mismatches=(),
        )
        with pytest.raises(FrozenInstanceError):
            r.status = "error"  # type: ignore[misc]

    def test_mismatches_tuple_default(self) -> None:
        r = WorkflowDriftReport(
            feature_type_id="feature:010-test",
            status="in_sync",
            meta_json=None,
            db=None,
            mismatches=(),
        )
        assert isinstance(r.mismatches, tuple)

    def test_message_field(self) -> None:
        r = WorkflowDriftReport(
            feature_type_id="feature:010-test",
            status="error",
            meta_json=None,
            db=None,
            mismatches=(),
            message="Something went wrong",
        )
        assert r.message == "Something went wrong"


class TestWorkflowDriftResult:
    """WorkflowDriftResult frozen dataclass tests."""

    def test_construction(self) -> None:
        report = WorkflowDriftReport(
            feature_type_id="feature:010-test",
            status="in_sync",
            meta_json=None,
            db=None,
            mismatches=(),
        )
        result = WorkflowDriftResult(
            features=(report,),
            summary={"in_sync": 1},
        )
        assert len(result.features) == 1
        assert result.summary["in_sync"] == 1

    def test_frozen(self) -> None:
        result = WorkflowDriftResult(features=(), summary={})
        with pytest.raises(FrozenInstanceError):
            result.features = ()  # type: ignore[misc]

    def test_features_tuple(self) -> None:
        result = WorkflowDriftResult(features=(), summary={})
        assert isinstance(result.features, tuple)


class TestReconcileAction:
    """ReconcileAction frozen dataclass tests."""

    def test_construction(self) -> None:
        a = ReconcileAction(
            feature_type_id="feature:010-test",
            action="reconciled",
            direction="meta_json_to_db",
            changes=(),
            message="Updated DB",
        )
        assert a.feature_type_id == "feature:010-test"
        assert a.action == "reconciled"
        assert a.direction == "meta_json_to_db"
        assert a.changes == ()
        assert a.message == "Updated DB"

    def test_frozen(self) -> None:
        a = ReconcileAction(
            feature_type_id="feature:010-test",
            action="reconciled",
            direction="meta_json_to_db",
            changes=(),
            message="",
        )
        with pytest.raises(FrozenInstanceError):
            a.action = "error"  # type: ignore[misc]

    def test_changes_with_mismatches(self) -> None:
        m = WorkflowMismatch(field="workflow_phase", meta_json_value="finish", db_value="implement")
        a = ReconcileAction(
            feature_type_id="feature:010-test",
            action="reconciled",
            direction="meta_json_to_db",
            changes=(m,),
            message="",
        )
        assert len(a.changes) == 1
        assert a.changes[0].field == "workflow_phase"


class TestReconciliationResult:
    """ReconciliationResult frozen dataclass tests."""

    def test_construction(self) -> None:
        r = ReconciliationResult(
            actions=(),
            summary={"reconciled": 0, "created": 0, "skipped": 0, "error": 0, "dry_run": 0},
        )
        assert r.actions == ()
        assert r.summary["reconciled"] == 0

    def test_frozen(self) -> None:
        r = ReconciliationResult(actions=(), summary={})
        with pytest.raises(FrozenInstanceError):
            r.actions = ()  # type: ignore[misc]


# ===========================================================================
# Task 1.2: Phase comparison helpers
# ===========================================================================


class TestPhaseIndex:
    """_phase_index() tests."""

    def test_known_phases(self) -> None:
        """All PHASE_SEQUENCE phases map to correct indices."""
        expected = {
            "brainstorm": 0,
            "specify": 1,
            "design": 2,
            "create-plan": 3,
            "create-tasks": 4,
            "implement": 5,
            "finish": 6,
        }
        for phase, idx in expected.items():
            assert _phase_index(phase) == idx, f"_phase_index({phase!r}) != {idx}"

    def test_none_returns_minus_one(self) -> None:
        assert _phase_index(None) == -1

    def test_unknown_returns_minus_one(self) -> None:
        assert _phase_index("nonexistent-phase") == -1

    def test_empty_string_returns_minus_one(self) -> None:
        assert _phase_index("") == -1


class TestComparePhases:
    """_compare_phases() covering all 8 spec R8 comparison steps."""

    def test_in_sync_both_match(self) -> None:
        """Step 6: both last_completed and workflow_phase match."""
        assert _compare_phases("design", "create-plan", "design", "create-plan") == "in_sync"

    def test_meta_json_ahead_last_completed(self) -> None:
        """Steps 1-3: meta last_completed > db last_completed."""
        assert _compare_phases("implement", "finish", "design", "create-plan") == "meta_json_ahead"

    def test_db_ahead_last_completed(self) -> None:
        """Steps 1-4: db last_completed > meta last_completed."""
        assert _compare_phases("design", "create-plan", "implement", "finish") == "db_ahead"

    def test_equal_last_completed_meta_workflow_ahead(self) -> None:
        """Step 5: equal last_completed, meta workflow_phase ahead."""
        assert _compare_phases("design", "implement", "design", "create-plan") == "meta_json_ahead"

    def test_equal_last_completed_db_workflow_ahead(self) -> None:
        """Step 5: equal last_completed, db workflow_phase ahead."""
        assert _compare_phases("design", "create-plan", "design", "implement") == "db_ahead"

    def test_none_vs_non_none_last_completed_meta_ahead(self) -> None:
        """Step 7: meta has value, db has None."""
        assert _compare_phases("design", "create-plan", None, "brainstorm") == "meta_json_ahead"

    def test_none_vs_non_none_last_completed_db_ahead(self) -> None:
        """Step 7: db has value, meta has None."""
        assert _compare_phases(None, "brainstorm", "design", "create-plan") == "db_ahead"

    def test_both_none_last_completed_fallthrough_to_workflow(self) -> None:
        """Step 8: both None last_completed, compare workflow_phase."""
        # meta workflow_phase ahead
        assert _compare_phases(None, "design", None, "brainstorm") == "meta_json_ahead"

    def test_both_none_last_completed_db_workflow_ahead(self) -> None:
        """Step 8: both None last_completed, db workflow_phase ahead."""
        assert _compare_phases(None, "brainstorm", None, "design") == "db_ahead"

    def test_both_none_everything(self) -> None:
        """Step 8: all four values are None -> in_sync."""
        assert _compare_phases(None, None, None, None) == "in_sync"

    def test_terminal_phase(self) -> None:
        """Edge case: finish is terminal phase."""
        assert _compare_phases("finish", "finish", "implement", "finish") == "meta_json_ahead"

    def test_both_at_terminal(self) -> None:
        """Both at finish -> in_sync."""
        assert _compare_phases("finish", "finish", "finish", "finish") == "in_sync"

    def test_unknown_phase_treated_as_minus_one(self) -> None:
        """Unknown phases get index -1, same as None."""
        assert _compare_phases("unknown", None, None, None) == "in_sync"


# ===========================================================================
# Task 2.1: Single-feature meta reader
# ===========================================================================


class TestReadSingleMetaJson:
    """_read_single_meta_json() tests."""

    def test_valid_file(self, tmp_path) -> None:
        """Valid .meta.json returns parsed dict."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "010-test-feature"
        _create_meta_json(tmp_path, slug, status="active", last_completed_phase="design")

        result = _read_single_meta_json(engine, str(tmp_path), f"feature:{slug}")

        assert result is not None
        assert result["status"] == "active"
        assert result["lastCompletedPhase"] == "design"

    def test_missing_file(self, tmp_path) -> None:
        """Missing file returns None."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        # Create directory but no .meta.json
        (tmp_path / "features" / "010-test-feature").mkdir(parents=True)

        result = _read_single_meta_json(engine, str(tmp_path), "feature:010-test-feature")
        assert result is None

    def test_corrupt_json(self, tmp_path) -> None:
        """Corrupt JSON returns None."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        slug = "010-test-feature"
        feature_dir = tmp_path / "features" / slug
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text("{broken json")

        result = _read_single_meta_json(engine, str(tmp_path), f"feature:{slug}")
        assert result is None


# ===========================================================================
# Task 2.2: Single-feature drift check
# ===========================================================================


class TestCheckSingleFeature:
    """_check_single_feature() tests."""

    def test_in_sync(self, tmp_path) -> None:
        """All fields match -> in_sync with empty mismatches."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        meta = {
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": "design",
            "phases": {},
        }

        report = _check_single_feature(engine, db, type_id, meta)

        assert report.status == "in_sync"
        assert report.mismatches == ()
        assert report.meta_json is not None
        assert report.db is not None
        # Verify field name mapping: output uses "workflow_phase" not "current_phase"
        assert "workflow_phase" in report.meta_json
        assert "workflow_phase" in report.db

    def test_meta_json_ahead(self, tmp_path) -> None:
        """meta.json has later phase -> meta_json_ahead."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        meta = {
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": "implement",
            "phases": {},
        }

        report = _check_single_feature(engine, db, type_id, meta)

        assert report.status == "meta_json_ahead"
        # Should have mismatches for last_completed_phase and workflow_phase
        mismatch_fields = {m.field for m in report.mismatches}
        assert "last_completed_phase" in mismatch_fields
        assert "workflow_phase" in mismatch_fields

    def test_db_ahead(self, tmp_path) -> None:
        """DB has later phase -> db_ahead."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="finish",
            last_completed_phase="implement",
            mode="standard",
        )
        meta = {
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": "design",
            "phases": {},
        }

        report = _check_single_feature(engine, db, type_id, meta)

        assert report.status == "db_ahead"

    def test_no_db_row(self, tmp_path) -> None:
        """No workflow_phases row -> meta_json_only."""
        db = _make_db()
        _register_feature(db, "010-test")
        engine = WorkflowStateEngine(db, str(tmp_path))
        meta = {
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": "design",
            "phases": {},
        }

        report = _check_single_feature(engine, db, "feature:010-test", meta)

        assert report.status == "meta_json_only"
        assert report.db is None

    def test_mode_mismatch_with_phase_sync(self, tmp_path) -> None:
        """Phases match but mode differs -> in_sync but mismatch present."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="full",
        )
        meta = {
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": "design",
            "phases": {},
        }

        report = _check_single_feature(engine, db, type_id, meta)

        assert report.status == "in_sync"
        mode_mismatches = [m for m in report.mismatches if m.field == "mode"]
        assert len(mode_mismatches) == 1
        assert mode_mismatches[0].meta_json_value == "standard"
        assert mode_mismatches[0].db_value == "full"

    def test_derive_state_returns_none(self, tmp_path) -> None:
        """_derive_state_from_meta returns None -> status='error'."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="design",
            last_completed_phase="specify",
            mode="standard",
        )
        # Meta with an unknown lastCompletedPhase causes _derive_state_from_meta to return None
        meta = {
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": "unknown-phase",
            "phases": {},
        }

        report = _check_single_feature(engine, db, type_id, meta)

        assert report.status == "error"
        assert "Failed to derive state" in report.message

    def test_field_name_mapping(self, tmp_path) -> None:
        """Output dict uses workflow_phase (DB column name), not current_phase."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        meta = {
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": "design",
            "phases": {},
        }

        report = _check_single_feature(engine, db, type_id, meta)

        assert "workflow_phase" in report.meta_json
        assert "current_phase" not in report.meta_json
        assert "workflow_phase" in report.db
        assert "current_phase" not in report.db


# ===========================================================================
# Task 2.3: Public drift detection
# ===========================================================================


class TestCheckWorkflowDrift:
    """check_workflow_drift() tests."""

    def test_single_feature_in_sync(self, tmp_path) -> None:
        """AC-1: in_sync status for matching feature."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        _create_meta_json(tmp_path, "010-test", status="active", last_completed_phase="design")

        result = check_workflow_drift(engine, db, str(tmp_path), feature_type_id=type_id)

        assert len(result.features) == 1
        assert result.features[0].status == "in_sync"
        assert result.summary["in_sync"] == 1

    def test_single_feature_meta_json_ahead(self, tmp_path) -> None:
        """AC-2: meta_json_ahead when .meta.json has later phase."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        _create_meta_json(tmp_path, "010-test", status="active", last_completed_phase="implement")

        result = check_workflow_drift(engine, db, str(tmp_path), feature_type_id=type_id)

        assert len(result.features) == 1
        assert result.features[0].status == "meta_json_ahead"
        assert result.summary["meta_json_ahead"] == 1

    def test_single_feature_meta_json_only(self, tmp_path) -> None:
        """AC-3: meta_json_only when no workflow_phases row."""
        db = _make_db()
        _register_feature(db, "010-test")
        engine = WorkflowStateEngine(db, str(tmp_path))
        _create_meta_json(tmp_path, "010-test", status="active", last_completed_phase="design")

        result = check_workflow_drift(engine, db, str(tmp_path), feature_type_id="feature:010-test")

        assert len(result.features) == 1
        assert result.features[0].status == "meta_json_only"
        assert result.summary["meta_json_only"] == 1

    def test_single_feature_db_only(self, tmp_path) -> None:
        """AC-4: db_only when no .meta.json but DB row exists."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        # Do NOT create .meta.json

        result = check_workflow_drift(engine, db, str(tmp_path), feature_type_id=type_id)

        assert len(result.features) == 1
        assert result.features[0].status == "db_only"
        assert result.summary["db_only"] == 1

    def test_single_feature_not_found(self, tmp_path) -> None:
        """Feature not found in either source -> error."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        # Create the features directory so path validation passes
        (tmp_path / "features" / "999-nonexistent").mkdir(parents=True)

        result = check_workflow_drift(
            engine, db, str(tmp_path), feature_type_id="feature:999-nonexistent"
        )

        assert len(result.features) == 1
        assert result.features[0].status == "error"
        assert "not found" in result.features[0].message.lower()

    def test_bulk_scan(self, tmp_path) -> None:
        """AC-5: bulk scan with multiple features."""
        db = _make_db()
        # Feature 1: in_sync
        type_id1 = _register_feature(db, "001-feat-a")
        db.create_workflow_phase(
            type_id1, workflow_phase="create-plan", last_completed_phase="design", mode="standard"
        )
        _create_meta_json(tmp_path, "001-feat-a", status="active", last_completed_phase="design")

        # Feature 2: meta_json_ahead
        type_id2 = _register_feature(db, "002-feat-b")
        db.create_workflow_phase(
            type_id2, workflow_phase="specify", last_completed_phase="brainstorm", mode="standard"
        )
        _create_meta_json(tmp_path, "002-feat-b", status="active", last_completed_phase="design")

        engine = WorkflowStateEngine(db, str(tmp_path))

        result = check_workflow_drift(engine, db, str(tmp_path))

        assert len(result.features) == 2
        statuses = {r.feature_type_id: r.status for r in result.features}
        assert statuses["feature:001-feat-a"] == "in_sync"
        assert statuses["feature:002-feat-b"] == "meta_json_ahead"
        assert result.summary["in_sync"] == 1
        assert result.summary["meta_json_ahead"] == 1

    def test_bulk_scan_db_only_detection(self, tmp_path) -> None:
        """db_only detection via list_workflow_phases set difference."""
        db = _make_db()
        # Feature with .meta.json
        type_id1 = _register_feature(db, "001-feat-a")
        db.create_workflow_phase(
            type_id1, workflow_phase="design", last_completed_phase="specify", mode="standard"
        )
        _create_meta_json(tmp_path, "001-feat-a", status="active", last_completed_phase="specify")

        # Feature with DB row but NO .meta.json
        type_id2 = _register_feature(db, "002-feat-b")
        db.create_workflow_phase(
            type_id2, workflow_phase="design", last_completed_phase="specify", mode="standard"
        )

        engine = WorkflowStateEngine(db, str(tmp_path))

        result = check_workflow_drift(engine, db, str(tmp_path))

        statuses = {r.feature_type_id: r.status for r in result.features}
        assert statuses["feature:002-feat-b"] == "db_only"
        assert result.summary["db_only"] == 1

    def test_bulk_scan_non_feature_excluded(self, tmp_path) -> None:
        """Non-feature type_ids in DB excluded from db_only detection."""
        db = _make_db()
        # Feature in both sources
        type_id1 = _register_feature(db, "001-feat-a")
        db.create_workflow_phase(
            type_id1, workflow_phase="design", last_completed_phase="specify", mode="standard"
        )
        _create_meta_json(tmp_path, "001-feat-a", status="active", last_completed_phase="specify")

        # Non-feature entity with workflow_phases row
        db.register_entity(
            entity_type="brainstorm",
            entity_id="some-brainstorm",
            name="Some Brainstorm",
        )
        # Brainstorms normally don't have workflow_phases, but if one exists
        # it should be excluded from db_only detection
        db.create_workflow_phase(
            "brainstorm:some-brainstorm", workflow_phase="brainstorm", mode="standard"
        )

        engine = WorkflowStateEngine(db, str(tmp_path))

        result = check_workflow_drift(engine, db, str(tmp_path))

        # Only feature:001-feat-a should be in the results
        type_ids = {r.feature_type_id for r in result.features}
        assert "brainstorm:some-brainstorm" not in type_ids
        assert result.summary.get("db_only", 0) == 0

    def test_summary_counts(self, tmp_path) -> None:
        """Summary has all expected keys with correct counts."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = check_workflow_drift(engine, db, str(tmp_path))

        expected_keys = {"in_sync", "meta_json_ahead", "db_ahead", "meta_json_only", "db_only", "error"}
        assert set(result.summary.keys()) == expected_keys
        # Empty scan -> all zeros
        for key in expected_keys:
            assert result.summary[key] == 0

    def test_never_raises(self, tmp_path) -> None:
        """check_workflow_drift never raises for per-feature errors."""
        db = _make_db()
        # Feature with corrupt meta
        _register_feature(db, "001-corrupt")
        db.create_workflow_phase(
            "feature:001-corrupt", workflow_phase="design", mode="standard"
        )
        feature_dir = tmp_path / "features" / "001-corrupt"
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text("{broken")

        engine = WorkflowStateEngine(db, str(tmp_path))

        # Should not raise -- corrupt meta handled gracefully
        result = check_workflow_drift(engine, db, str(tmp_path))
        # The corrupt meta feature should show up as db_only (meta unreadable)
        # since _iter_meta_jsons skips unparseable files
        assert isinstance(result, WorkflowDriftResult)


# ===========================================================================
# Task 3.1: Single-feature reconcile
# ===========================================================================


class TestReconcileSingleFeature:
    """_reconcile_single_feature() tests."""

    def test_meta_json_ahead_update(self, tmp_path) -> None:
        """AC-6: meta_json_ahead -> update DB row, action='reconciled'."""
        _, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        report = WorkflowDriftReport(
            feature_type_id=type_id,
            status="meta_json_ahead",
            meta_json={
                "workflow_phase": "finish",
                "last_completed_phase": "implement",
                "mode": "standard",
                "status": "active",
            },
            db={
                "workflow_phase": "create-plan",
                "last_completed_phase": "design",
                "mode": "standard",
                "kanban_column": "backlog",
            },
            mismatches=(
                WorkflowMismatch(field="last_completed_phase", meta_json_value="implement", db_value="design"),
                WorkflowMismatch(field="workflow_phase", meta_json_value="finish", db_value="create-plan"),
            ),
        )

        action = _reconcile_single_feature(db, report, dry_run=False)

        assert action.action == "reconciled"
        assert action.direction == "meta_json_to_db"
        assert len(action.changes) > 0

        # Verify DB was actually updated
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["last_completed_phase"] == "implement"
        assert row["workflow_phase"] == "finish"

    def test_in_sync_skip(self, tmp_path) -> None:
        """AC-7: in_sync -> skip."""
        _, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        report = WorkflowDriftReport(
            feature_type_id=type_id,
            status="in_sync",
            meta_json={"workflow_phase": "create-plan", "last_completed_phase": "design", "mode": "standard", "status": "active"},
            db={"workflow_phase": "create-plan", "last_completed_phase": "design", "mode": "standard", "kanban_column": "backlog"},
            mismatches=(),
        )

        action = _reconcile_single_feature(db, report, dry_run=False)

        assert action.action == "skipped"
        assert "in sync" in action.message.lower()

    def test_meta_json_only_entity_exists_create(self, tmp_path) -> None:
        """AC-8: meta_json_only + entity exists -> create row, action='created'."""
        db = _make_db()
        _register_feature(db, "010-test")

        report = WorkflowDriftReport(
            feature_type_id="feature:010-test",
            status="meta_json_only",
            meta_json={
                "workflow_phase": "create-plan",
                "last_completed_phase": "design",
                "mode": "standard",
                "status": "active",
            },
            db=None,
            mismatches=(),
        )

        action = _reconcile_single_feature(db, report, dry_run=False)

        assert action.action == "created"
        assert action.direction == "meta_json_to_db"

        # Verify row was created
        row = db.get_workflow_phase("feature:010-test")
        assert row is not None
        assert row["workflow_phase"] == "create-plan"
        assert row["last_completed_phase"] == "design"
        assert row["mode"] == "standard"

    def test_meta_json_only_no_entity_error(self, tmp_path) -> None:
        """meta_json_only + entity not found -> action='error'."""
        db = _make_db()

        report = WorkflowDriftReport(
            feature_type_id="feature:010-nonexistent",
            status="meta_json_only",
            meta_json={
                "workflow_phase": "create-plan",
                "last_completed_phase": "design",
                "mode": "standard",
                "status": "active",
            },
            db=None,
            mismatches=(),
        )

        action = _reconcile_single_feature(db, report, dry_run=False)

        assert action.action == "error"
        assert "entity not found" in action.message.lower() or "Entity not found" in action.message

    def test_meta_json_only_meta_json_none_error(self, tmp_path) -> None:
        """meta_json_only + meta_json is None -> error (defensive guard)."""
        db = _make_db()

        report = WorkflowDriftReport(
            feature_type_id="feature:010-test",
            status="meta_json_only",
            meta_json=None,
            db=None,
            mismatches=(),
        )

        action = _reconcile_single_feature(db, report, dry_run=False)

        assert action.action == "error"
        assert "no meta_json data" in action.message.lower()

    def test_db_ahead_skip(self, tmp_path) -> None:
        """db_ahead -> skip."""
        _, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="finish",
            last_completed_phase="implement",
            mode="standard",
        )
        report = WorkflowDriftReport(
            feature_type_id=type_id,
            status="db_ahead",
            meta_json={"workflow_phase": "create-plan", "last_completed_phase": "design", "mode": "standard", "status": "active"},
            db={"workflow_phase": "finish", "last_completed_phase": "implement", "mode": "standard", "kanban_column": "backlog"},
            mismatches=(),
        )

        action = _reconcile_single_feature(db, report, dry_run=False)

        assert action.action == "skipped"
        assert "db is ahead" in action.message.lower()

    def test_db_only_skip(self, tmp_path) -> None:
        """db_only -> skip."""
        _, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="design",
            last_completed_phase="specify",
            mode="standard",
        )
        report = WorkflowDriftReport(
            feature_type_id=type_id,
            status="db_only",
            meta_json=None,
            db={"workflow_phase": "design", "last_completed_phase": "specify", "mode": "standard", "kanban_column": "backlog"},
            mismatches=(),
        )

        action = _reconcile_single_feature(db, report, dry_run=False)

        assert action.action == "skipped"
        assert "no .meta.json" in action.message.lower()

    def test_error_propagate(self, tmp_path) -> None:
        """error status -> action='error', message propagated."""
        db = _make_db()

        report = WorkflowDriftReport(
            feature_type_id="feature:010-test",
            status="error",
            meta_json=None,
            db=None,
            mismatches=(),
            message="Original error message",
        )

        action = _reconcile_single_feature(db, report, dry_run=False)

        assert action.action == "error"
        assert "Original error message" in action.message

    def test_dry_run_no_db_writes(self, tmp_path) -> None:
        """AC-9: dry_run=True -> no DB writes."""
        _, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        report = WorkflowDriftReport(
            feature_type_id=type_id,
            status="meta_json_ahead",
            meta_json={
                "workflow_phase": "finish",
                "last_completed_phase": "implement",
                "mode": "standard",
                "status": "active",
            },
            db={
                "workflow_phase": "create-plan",
                "last_completed_phase": "design",
                "mode": "standard",
                "kanban_column": "backlog",
            },
            mismatches=(
                WorkflowMismatch(field="last_completed_phase", meta_json_value="implement", db_value="design"),
                WorkflowMismatch(field="workflow_phase", meta_json_value="finish", db_value="create-plan"),
            ),
        )

        action = _reconcile_single_feature(db, report, dry_run=True)

        assert action.action == "reconciled"
        assert len(action.changes) > 0

        # DB should NOT have been updated
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["last_completed_phase"] == "design"
        assert row["workflow_phase"] == "create-plan"

    def test_idempotency(self, tmp_path) -> None:
        """AC-10: second reconcile after first should skip."""
        _, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        report = WorkflowDriftReport(
            feature_type_id=type_id,
            status="meta_json_ahead",
            meta_json={
                "workflow_phase": "finish",
                "last_completed_phase": "implement",
                "mode": "standard",
                "status": "active",
            },
            db={
                "workflow_phase": "create-plan",
                "last_completed_phase": "design",
                "mode": "standard",
                "kanban_column": "backlog",
            },
            mismatches=(
                WorkflowMismatch(field="last_completed_phase", meta_json_value="implement", db_value="design"),
            ),
        )

        # First reconcile
        action1 = _reconcile_single_feature(db, report, dry_run=False)
        assert action1.action == "reconciled"

        # Now DB matches meta_json -> build in_sync report
        report2 = WorkflowDriftReport(
            feature_type_id=type_id,
            status="in_sync",
            meta_json=report.meta_json,
            db={
                "workflow_phase": "finish",
                "last_completed_phase": "implement",
                "mode": "standard",
                "kanban_column": "backlog",
            },
            mismatches=(),
        )

        # Second reconcile should skip
        action2 = _reconcile_single_feature(db, report2, dry_run=False)
        assert action2.action == "skipped"

    def test_value_error_from_update(self, tmp_path) -> None:
        """ValueError from update_workflow_phase -> action='error'."""
        _, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        report = WorkflowDriftReport(
            feature_type_id=type_id,
            status="meta_json_ahead",
            meta_json={
                "workflow_phase": "finish",
                "last_completed_phase": "implement",
                "mode": "standard",
                "status": "active",
            },
            db={
                "workflow_phase": "create-plan",
                "last_completed_phase": "design",
                "mode": "standard",
                "kanban_column": "backlog",
            },
            mismatches=(
                WorkflowMismatch(field="last_completed_phase", meta_json_value="implement", db_value="design"),
            ),
        )

        # Delete the workflow phase row to cause ValueError on update
        db._conn.execute("DELETE FROM workflow_phases WHERE type_id = ?", (type_id,))
        db._conn.commit()

        action = _reconcile_single_feature(db, report, dry_run=False)

        assert action.action == "error"

    def test_value_error_from_create(self, tmp_path) -> None:
        """ValueError from create_workflow_phase -> action='error'."""
        _, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        # Report says meta_json_only, but a row already exists -> create will fail
        report = WorkflowDriftReport(
            feature_type_id=type_id,
            status="meta_json_only",
            meta_json={
                "workflow_phase": "create-plan",
                "last_completed_phase": "design",
                "mode": "standard",
                "status": "active",
            },
            db=None,
            mismatches=(),
        )

        action = _reconcile_single_feature(db, report, dry_run=False)

        assert action.action == "error"


# ===========================================================================
# Task 3.2: Public reconciliation
# ===========================================================================


class TestApplyWorkflowReconciliation:
    """apply_workflow_reconciliation() tests."""

    def test_bulk_reconcile(self, tmp_path) -> None:
        """Bulk reconcile multiple features."""
        db = _make_db()
        # Feature 1: meta_json_ahead (will be reconciled)
        type_id1 = _register_feature(db, "001-feat-a")
        db.create_workflow_phase(
            type_id1, workflow_phase="specify", last_completed_phase="brainstorm", mode="standard"
        )
        _create_meta_json(tmp_path, "001-feat-a", status="active", last_completed_phase="design")

        # Feature 2: in_sync (will be skipped)
        type_id2 = _register_feature(db, "002-feat-b")
        db.create_workflow_phase(
            type_id2, workflow_phase="create-plan", last_completed_phase="design", mode="standard"
        )
        _create_meta_json(tmp_path, "002-feat-b", status="active", last_completed_phase="design")

        engine = WorkflowStateEngine(db, str(tmp_path))

        result = apply_workflow_reconciliation(engine, db, str(tmp_path))

        assert isinstance(result, ReconciliationResult)
        action_map = {a.feature_type_id: a.action for a in result.actions}
        assert action_map["feature:001-feat-a"] == "reconciled"
        assert action_map["feature:002-feat-b"] == "skipped"
        assert result.summary["reconciled"] == 1
        assert result.summary["skipped"] == 1

    def test_dry_run_preview(self, tmp_path) -> None:
        """AC-9: dry_run preview returns changes without modifying DB."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        _create_meta_json(tmp_path, "010-test", status="active", last_completed_phase="implement")

        result = apply_workflow_reconciliation(
            engine, db, str(tmp_path), feature_type_id=type_id, dry_run=True
        )

        assert result.summary.get("dry_run", 0) >= 1
        # DB should not be changed
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["last_completed_phase"] == "design"

    def test_idempotency(self, tmp_path) -> None:
        """AC-10: second run produces all-skipped."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        _create_meta_json(tmp_path, "010-test", status="active", last_completed_phase="implement")

        # First run
        result1 = apply_workflow_reconciliation(engine, db, str(tmp_path), feature_type_id=type_id)
        assert result1.summary["reconciled"] == 1

        # Second run - should all be skipped now
        result2 = apply_workflow_reconciliation(engine, db, str(tmp_path), feature_type_id=type_id)
        assert result2.summary["skipped"] == 1
        assert result2.summary["reconciled"] == 0

    def test_summary_keys(self, tmp_path) -> None:
        """Summary dict has all 5 expected keys."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        result = apply_workflow_reconciliation(engine, db, str(tmp_path))

        expected_keys = {"reconciled", "created", "skipped", "error", "dry_run"}
        assert set(result.summary.keys()) == expected_keys

    def test_never_raises(self, tmp_path) -> None:
        """apply_workflow_reconciliation never raises for per-feature errors."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        # Should not raise even with empty data
        result = apply_workflow_reconciliation(engine, db, str(tmp_path))
        assert isinstance(result, ReconciliationResult)

    def test_single_feature_reconcile(self, tmp_path) -> None:
        """Single feature reconciliation via feature_type_id."""
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        _create_meta_json(tmp_path, "010-test", status="active", last_completed_phase="implement")

        result = apply_workflow_reconciliation(
            engine, db, str(tmp_path), feature_type_id=type_id
        )

        assert len(result.actions) == 1
        assert result.actions[0].action == "reconciled"
        assert result.summary["reconciled"] == 1

        # Verify DB updated
        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["last_completed_phase"] == "implement"


# ===========================================================================
# Task 7.1: Full-cycle integration tests
# ===========================================================================


class TestIntegrationFullCycle:
    """Multi-feature drift -> reconcile -> verify in_sync cycle."""

    def test_bulk_drift_reconcile_verify(self, tmp_path) -> None:
        """3+ features in different drift states -> reconcile -> all in_sync."""
        db = _make_db()

        # Feature 1: meta_json_ahead
        type_id1 = _register_feature(db, "001-ahead")
        db.create_workflow_phase(
            type_id1, workflow_phase="specify", last_completed_phase="brainstorm", mode="standard"
        )
        _create_meta_json(tmp_path, "001-ahead", status="active", last_completed_phase="implement")

        # Feature 2: in_sync
        type_id2 = _register_feature(db, "002-synced")
        db.create_workflow_phase(
            type_id2, workflow_phase="create-plan", last_completed_phase="design", mode="standard"
        )
        _create_meta_json(tmp_path, "002-synced", status="active", last_completed_phase="design")

        # Feature 3: meta_json_ahead (different phase)
        type_id3 = _register_feature(db, "003-another-ahead")
        db.create_workflow_phase(
            type_id3, workflow_phase="design", last_completed_phase="specify", mode="full"
        )
        _create_meta_json(
            tmp_path, "003-another-ahead", status="active",
            last_completed_phase="create-tasks", mode="full"
        )

        engine = WorkflowStateEngine(db, str(tmp_path))

        # Step 1: Detect drift
        drift = check_workflow_drift(engine, db, str(tmp_path))
        assert drift.summary["meta_json_ahead"] == 2
        assert drift.summary["in_sync"] == 1

        # Step 2: Reconcile
        result = apply_workflow_reconciliation(engine, db, str(tmp_path))
        assert result.summary["reconciled"] == 2
        assert result.summary["skipped"] == 1

        # Step 3: Verify all in_sync
        drift2 = check_workflow_drift(engine, db, str(tmp_path))
        assert drift2.summary["in_sync"] == 3
        assert drift2.summary["meta_json_ahead"] == 0

    def test_idempotency_full_cycle(self, tmp_path) -> None:
        """Second reconcile after first produces all-skipped."""
        db = _make_db()
        type_id = _register_feature(db, "010-test")
        db.create_workflow_phase(
            type_id, workflow_phase="specify", last_completed_phase="brainstorm", mode="standard"
        )
        _create_meta_json(tmp_path, "010-test", status="active", last_completed_phase="design")

        engine = WorkflowStateEngine(db, str(tmp_path))

        # First reconcile
        result1 = apply_workflow_reconciliation(engine, db, str(tmp_path))
        assert result1.summary["reconciled"] == 1

        # Second reconcile - idempotent
        result2 = apply_workflow_reconciliation(engine, db, str(tmp_path))
        assert result2.summary["reconciled"] == 0
        assert result2.summary["skipped"] == 1

    def test_both_none_phases(self, tmp_path) -> None:
        """Edge case: both-None phases in both sources -> in_sync."""
        db = _make_db()
        type_id = _register_feature(db, "010-test", status="planned")
        db.create_workflow_phase(
            type_id, workflow_phase=None, last_completed_phase=None, mode="standard"
        )
        # "planned" status with no lastCompletedPhase -> _derive_state returns
        # workflow_phase=None, last_completed_phase=None
        _create_meta_json(tmp_path, "010-test", status="planned")

        engine = WorkflowStateEngine(db, str(tmp_path))

        drift = check_workflow_drift(engine, db, str(tmp_path), feature_type_id=type_id)

        assert drift.features[0].status == "in_sync"

    def test_terminal_phases(self, tmp_path) -> None:
        """Edge case: terminal phase (finish) in both sources."""
        db = _make_db()
        type_id = _register_feature(db, "010-test", status="completed")
        db.create_workflow_phase(
            type_id, workflow_phase="finish", last_completed_phase="finish", mode="standard"
        )
        _create_meta_json(
            tmp_path, "010-test", status="completed", last_completed_phase="finish"
        )

        engine = WorkflowStateEngine(db, str(tmp_path))

        drift = check_workflow_drift(engine, db, str(tmp_path), feature_type_id=type_id)

        assert drift.features[0].status == "in_sync"

    def test_empty_feature_set(self, tmp_path) -> None:
        """Edge case: no features at all."""
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        drift = check_workflow_drift(engine, db, str(tmp_path))
        assert len(drift.features) == 0
        assert drift.summary["in_sync"] == 0

        result = apply_workflow_reconciliation(engine, db, str(tmp_path))
        assert len(result.actions) == 0

    def test_meta_json_only_create_then_verify(self, tmp_path) -> None:
        """AC-8 integration: meta_json_only -> create -> verify in_sync."""
        db = _make_db()
        _register_feature(db, "010-test")
        _create_meta_json(tmp_path, "010-test", status="active", last_completed_phase="design")

        engine = WorkflowStateEngine(db, str(tmp_path))

        # Step 1: Detect - should be meta_json_only
        drift1 = check_workflow_drift(
            engine, db, str(tmp_path), feature_type_id="feature:010-test"
        )
        assert drift1.features[0].status == "meta_json_only"

        # Step 2: Reconcile - should create
        result = apply_workflow_reconciliation(
            engine, db, str(tmp_path), feature_type_id="feature:010-test"
        )
        assert result.summary["created"] == 1

        # Step 3: Verify in_sync
        drift2 = check_workflow_drift(
            engine, db, str(tmp_path), feature_type_id="feature:010-test"
        )
        assert drift2.features[0].status == "in_sync"

    def test_mixed_statuses_bulk(self, tmp_path) -> None:
        """Bulk with meta_json_ahead, in_sync, meta_json_only, db_only."""
        db = _make_db()

        # meta_json_ahead
        type_id1 = _register_feature(db, "001-ahead")
        db.create_workflow_phase(
            type_id1, workflow_phase="specify", last_completed_phase="brainstorm", mode="standard"
        )
        _create_meta_json(tmp_path, "001-ahead", status="active", last_completed_phase="design")

        # in_sync
        type_id2 = _register_feature(db, "002-synced")
        db.create_workflow_phase(
            type_id2, workflow_phase="create-plan", last_completed_phase="design", mode="standard"
        )
        _create_meta_json(tmp_path, "002-synced", status="active", last_completed_phase="design")

        # meta_json_only (entity exists, no workflow_phases row)
        _register_feature(db, "003-meta-only")
        _create_meta_json(tmp_path, "003-meta-only", status="active", last_completed_phase="specify")

        # db_only (workflow_phases row, no .meta.json)
        type_id4 = _register_feature(db, "004-db-only")
        db.create_workflow_phase(
            type_id4, workflow_phase="implement", last_completed_phase="create-tasks", mode="standard"
        )

        engine = WorkflowStateEngine(db, str(tmp_path))

        # Drift check
        drift = check_workflow_drift(engine, db, str(tmp_path))
        status_map = {r.feature_type_id: r.status for r in drift.features}
        assert status_map["feature:001-ahead"] == "meta_json_ahead"
        assert status_map["feature:002-synced"] == "in_sync"
        assert status_map["feature:003-meta-only"] == "meta_json_only"
        assert status_map["feature:004-db-only"] == "db_only"

        # Reconcile
        result = apply_workflow_reconciliation(engine, db, str(tmp_path))
        assert result.summary["reconciled"] == 1  # 001-ahead
        assert result.summary["created"] == 1    # 003-meta-only
        assert result.summary["skipped"] == 2    # 002-synced + 004-db-only

        # Verify post-reconcile drift
        drift2 = check_workflow_drift(engine, db, str(tmp_path))
        status_map2 = {r.feature_type_id: r.status for r in drift2.features}
        assert status_map2["feature:001-ahead"] == "in_sync"
        assert status_map2["feature:002-synced"] == "in_sync"
        assert status_map2["feature:003-meta-only"] == "in_sync"
        assert status_map2["feature:004-db-only"] == "db_only"  # Still db_only (no meta.json)


# ===========================================================================
# Test-deepener: Phase B -- Boundary Value tests
# derived_from: dimension:boundary_values
# ===========================================================================


class TestPhaseIndexBoundary:
    """Boundary value tests for _phase_index().
    derived_from: dimension:boundary_values (numeric range BVA)
    """

    def test_first_phase_returns_zero(self) -> None:
        """First phase in PHASE_SEQUENCE returns index 0.
        derived_from: spec:R8 (phase comparison algorithm)

        Anticipate: Off-by-one if _PHASE_VALUES is built incorrectly
        or index() uses 1-based indexing.
        """
        # Given the first phase in PHASE_SEQUENCE is "brainstorm"
        # When querying its index
        result = _phase_index("brainstorm")
        # Then it returns exactly 0 (not 1, not -1)
        assert result == 0

    def test_last_phase_returns_max_index(self) -> None:
        """Last phase in PHASE_SEQUENCE returns index 6.
        derived_from: spec:R8 (phase comparison algorithm)

        Anticipate: If _PHASE_VALUES tuple is truncated or reordered,
        finish would not be at the expected max index.
        """
        # Given the last phase is "finish"
        # When querying its index
        result = _phase_index("finish")
        # Then it returns exactly 6 (7 phases, 0-indexed)
        assert result == 6

    def test_second_phase_returns_one(self) -> None:
        """Second phase returns min+1 = 1.
        derived_from: dimension:boundary_values (min+1)

        Anticipate: Adjacent phases could be swapped in _PHASE_VALUES
        without detection if only min and max are tested.
        """
        # Given the second phase is "specify"
        # When querying its index
        result = _phase_index("specify")
        # Then it returns 1
        assert result == 1

    def test_penultimate_phase_returns_max_minus_one(self) -> None:
        """Penultimate phase returns max-1 = 5.
        derived_from: dimension:boundary_values (max-1)

        Anticipate: "implement" at index 5 is critical for boundary
        comparisons against "finish" at index 6.
        """
        # Given the penultimate phase is "implement"
        # When querying its index
        result = _phase_index("implement")
        # Then it returns 5
        assert result == 5

    def test_empty_string_returns_minus_one(self) -> None:
        """Empty string is treated as unknown -> -1.
        derived_from: dimension:boundary_values (empty string input)

        Anticipate: str.index("") returns 0 for any string, which would
        incorrectly map empty string to "brainstorm" index.
        Verify: The implementation uses _PHASE_VALUES.index(phase) which
        would return 0 for "" if any phase value starts with "". Since
        tuple.index("") raises ValueError (no exact match), this is safe.
        """
        assert _phase_index("") == -1


class TestComparePhasesAdjacentBoundary:
    """Adjacent-phase boundary tests for _compare_phases().
    derived_from: dimension:boundary_values (off-by-one detection)
    """

    def test_adjacent_phases_meta_one_step_ahead(self) -> None:
        """Meta one step ahead in last_completed (index 0 vs 1).
        derived_from: spec:R8 (comparison steps 1-3)

        Anticipate: >= instead of > in the comparison would cause
        equal indices to report "ahead" instead of falling through
        to workflow_phase comparison.
        """
        # Given meta last_completed="specify" (1), db last_completed="brainstorm" (0)
        # When comparing
        result = _compare_phases("specify", "design", "brainstorm", "specify")
        # Then meta is ahead by exactly one step
        assert result == "meta_json_ahead"

    def test_adjacent_phases_db_one_step_ahead(self) -> None:
        """DB one step ahead in last_completed (index 1 vs 0).
        derived_from: spec:R8 (comparison steps 1-4)

        Anticipate: Swapping > and < in the comparison would invert
        the "ahead" direction.
        """
        # Given db last_completed="specify" (1), meta last_completed="brainstorm" (0)
        result = _compare_phases("brainstorm", "specify", "specify", "design")
        # Then db is ahead
        assert result == "db_ahead"

    def test_workflow_phase_tiebreaker_adjacent(self) -> None:
        """Equal last_completed, meta workflow_phase one step ahead (step 5).
        derived_from: spec:R8 (comparison step 5)

        Anticipate: If step 5 comparison is deleted or skipped,
        equal last_completed always returns "in_sync" even with
        different workflow_phases.
        """
        # Given both last_completed="design" (2), meta wp="create-tasks" (4), db wp="create-plan" (3)
        result = _compare_phases("design", "create-tasks", "design", "create-plan")
        assert result == "meta_json_ahead"


class TestCheckSingleFeatureBoundary:
    """Boundary value tests for _check_single_feature().
    derived_from: dimension:boundary_values (field comparison edge cases)
    """

    def test_status_field_excluded_from_mismatches(self, tmp_path) -> None:
        """status field is never compared -- it appears in meta_json output
        but never generates a mismatch entry.
        derived_from: spec:R1 (status is informational only)

        Anticipate: If someone adds a status comparison alongside mode,
        last_completed_phase, and workflow_phase, it would generate
        spurious mismatches. This test pins that status is excluded
        from the compared fields by checking that "status" never appears
        as a mismatch field, even when phases differ.
        """
        # Given a feature where meta is ahead (so we get mismatches)
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            status="active",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        meta = {
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": "implement",  # Ahead of DB
            "phases": {},
        }

        # When checking drift
        report = _check_single_feature(engine, db, type_id, meta)

        # Then mismatches exist for phase fields but NOT for "status"
        assert report.status == "meta_json_ahead"
        assert len(report.mismatches) > 0
        mismatch_fields = {m.field for m in report.mismatches}
        assert "status" not in mismatch_fields
        # Only these three fields can appear as mismatches
        assert mismatch_fields.issubset({"last_completed_phase", "workflow_phase", "mode"})

    def test_meta_json_dict_includes_status_field(self, tmp_path) -> None:
        """report.meta_json includes status for informational purposes.
        derived_from: spec:R1 (field source mapping table)

        Anticipate: Removing status from meta_dict would break callers
        who display it for context.
        """
        # Given a feature with status="active"
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        meta = {
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": "design",
            "phases": {},
        }

        report = _check_single_feature(engine, db, type_id, meta)

        # Then meta_json dict includes "status" key
        assert "status" in report.meta_json
        assert report.meta_json["status"] == "active"

    def test_db_dict_includes_kanban_column(self, tmp_path) -> None:
        """report.db includes kanban_column for informational context.
        derived_from: spec:R1 (field source mapping: kanban_column informational)

        Anticipate: If kanban_column is removed from db_dict, callers
        lose context about kanban state during drift review.
        """
        # Given a feature with a DB row
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="create-plan",
            last_completed_phase="design",
            mode="standard",
        )
        meta = {
            "status": "active",
            "mode": "standard",
            "lastCompletedPhase": "design",
            "phases": {},
        }

        report = _check_single_feature(engine, db, type_id, meta)

        # Then db dict includes "kanban_column" key
        assert "kanban_column" in report.db


class TestReadSingleMetaJsonBoundary:
    """Boundary tests for _read_single_meta_json().
    derived_from: dimension:boundary_values (filesystem edge cases)
    """

    def test_invalid_type_id_format_returns_none(self, tmp_path) -> None:
        """feature_type_id without colon causes ValueError in _extract_slug -> returns None.
        derived_from: dimension:boundary_values (malformed input)

        Anticipate: If ValueError from _extract_slug is not caught,
        the function would raise instead of returning None.
        """
        # Given an engine
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))

        # When reading with a malformed type_id (no colon)
        result = _read_single_meta_json(engine, str(tmp_path), "nocolon")

        # Then returns None (not raises)
        assert result is None

    def test_nonexistent_features_directory(self, tmp_path) -> None:
        """artifacts_root exists but features/ subdirectory doesn't -> returns None.
        derived_from: dimension:boundary_values (non-existent directory)

        Anticipate: os.path.join() would construct a valid path string
        but open() would raise OSError, which should be caught.
        """
        # Given artifacts_root with no "features" subdirectory
        db = _make_db()
        engine = WorkflowStateEngine(db, str(tmp_path))
        # tmp_path exists but tmp_path/features/010-test does not

        result = _read_single_meta_json(engine, str(tmp_path), "feature:010-test")

        assert result is None


# ===========================================================================
# Test-deepener: Phase B -- Adversarial tests
# derived_from: dimension:adversarial
# ===========================================================================


class TestAdversarialReconciliation:
    """Adversarial and invariant-violation tests for reconciliation module.
    derived_from: dimension:adversarial
    """

    def test_case_sensitive_phase_names(self) -> None:
        """Phase names are case-sensitive: 'Design' != 'design'.
        derived_from: dimension:adversarial (case sensitivity heuristic)

        Anticipate: If phase comparison is case-insensitive, "Design"
        would match "design" in PHASE_SEQUENCE, hiding real drift.
        Challenge: This test asserts that wrong-case phases get -1 index,
        meaning they're treated as unknown.
        """
        # Given an uppercase variant of a known phase
        # When querying its index
        result = _phase_index("Design")
        # Then it's treated as unknown (not matched to "design")
        assert result == -1

    def test_frozen_dataclass_immutability_after_creation(self) -> None:
        """Attempting to mutate WorkflowDriftReport fields after creation raises.
        derived_from: dimension:adversarial (Never/Always: frozen invariant)

        Anticipate: If @dataclass(frozen=True) is accidentally removed,
        reports could be mutated after creation, corrupting shared state.
        """
        from dataclasses import FrozenInstanceError

        report = WorkflowDriftReport(
            feature_type_id="feature:010-test",
            status="in_sync",
            meta_json=None,
            db=None,
            mismatches=(),
        )

        with pytest.raises(FrozenInstanceError):
            report.status = "meta_json_ahead"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            report.mismatches = ()  # type: ignore[misc]

    def test_reconcile_single_feature_all_three_fields_changed(self, tmp_path) -> None:
        """Reconciling with mode+phase+last_completed all different updates all three.
        derived_from: dimension:adversarial (Follow the Data heuristic)

        Anticipate: If update_workflow_phase only passes some fields,
        the others would be silently left stale. This test verifies
        all three fields are updated atomically.
        """
        # Given a feature where all three compared fields differ
        _, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="specify",
            last_completed_phase="brainstorm",
            mode="full",
        )
        report = WorkflowDriftReport(
            feature_type_id=type_id,
            status="meta_json_ahead",
            meta_json={
                "workflow_phase": "finish",
                "last_completed_phase": "implement",
                "mode": "standard",
                "status": "active",
            },
            db={
                "workflow_phase": "specify",
                "last_completed_phase": "brainstorm",
                "mode": "full",
                "kanban_column": "backlog",
            },
            mismatches=(
                WorkflowMismatch(field="last_completed_phase", meta_json_value="implement", db_value="brainstorm"),
                WorkflowMismatch(field="workflow_phase", meta_json_value="finish", db_value="specify"),
                WorkflowMismatch(field="mode", meta_json_value="standard", db_value="full"),
            ),
        )

        # When reconciling
        action = _reconcile_single_feature(db, report, dry_run=False)

        # Then all three fields are updated
        assert action.action == "reconciled"
        row = db.get_workflow_phase(type_id)
        assert row["workflow_phase"] == "finish"
        assert row["last_completed_phase"] == "implement"
        assert row["mode"] == "standard"

    def test_meta_json_only_creates_three_change_entries(self, tmp_path) -> None:
        """meta_json_only reconciliation creates exactly 3 change entries.
        derived_from: dimension:adversarial (Zero/One/Many: exact count)

        Anticipate: If a field is omitted from the changes tuple,
        the dry_run preview would be incomplete, misleading callers.
        """
        # Given a meta_json_only report
        db = _make_db()
        _register_feature(db, "010-test")

        report = WorkflowDriftReport(
            feature_type_id="feature:010-test",
            status="meta_json_only",
            meta_json={
                "workflow_phase": "design",
                "last_completed_phase": "specify",
                "mode": "standard",
                "status": "active",
            },
            db=None,
            mismatches=(),
        )

        # When reconciling (dry_run to inspect changes without side effects)
        action = _reconcile_single_feature(db, report, dry_run=True)

        # Then exactly 3 changes are reported
        assert action.action == "created"
        assert len(action.changes) == 3
        change_fields = {c.field for c in action.changes}
        assert change_fields == {"workflow_phase", "last_completed_phase", "mode"}
        # All old values are None (no DB row existed)
        for c in action.changes:
            assert c.db_value is None


# ===========================================================================
# Test-deepener: Phase B -- Error Propagation tests
# derived_from: dimension:error_propagation
# ===========================================================================


class TestErrorPropagationReconciliation:
    """Error propagation and failure mode tests.
    derived_from: dimension:error_propagation
    """

    def test_build_drift_result_unknown_status_counted_as_error(self) -> None:
        """Unknown status string in report is counted under 'error' in summary.
        derived_from: dimension:error_propagation (unknown status handling)

        Anticipate: If _build_drift_result doesn't handle unknown status
        strings, summary counts would silently miss features, making
        sum(summary.values()) != len(features).
        """
        from workflow_engine.reconciliation import _build_drift_result

        # Given a report with an unexpected status value
        report = WorkflowDriftReport(
            feature_type_id="feature:010-test",
            status="unknown_status_value",
            meta_json=None,
            db=None,
            mismatches=(),
        )

        # When building the drift result
        result = _build_drift_result([report])

        # Then the unknown status is counted as "error"
        assert result.summary["error"] == 1
        # And the total count equals the number of features
        total = sum(result.summary.values())
        assert total == 1

    def test_apply_reconciliation_catches_exception_from_reconcile_single(
        self, tmp_path, monkeypatch
    ) -> None:
        """Exception in _reconcile_single_feature is caught, not propagated.
        derived_from: dimension:error_propagation (never-raises contract)

        Anticipate: If the try/except in apply_workflow_reconciliation
        doesn't catch RuntimeError from _reconcile_single_feature,
        the entire bulk operation would abort on one bad feature.
        """
        # Given a feature with meta_json_ahead
        db = _make_db()
        type_id = _register_feature(db, "010-test")
        db.create_workflow_phase(
            type_id, workflow_phase="specify", last_completed_phase="brainstorm", mode="standard"
        )
        _create_meta_json(tmp_path, "010-test", status="active", last_completed_phase="design")

        engine = WorkflowStateEngine(db, str(tmp_path))

        # Monkeypatch _reconcile_single_feature to raise
        import workflow_engine.reconciliation as recon_mod
        original = recon_mod._reconcile_single_feature

        def exploding_reconcile(*args, **kwargs):
            raise RuntimeError("unexpected boom")

        monkeypatch.setattr(recon_mod, "_reconcile_single_feature", exploding_reconcile)

        # When applying reconciliation
        result = apply_workflow_reconciliation(engine, db, str(tmp_path))

        # Then it does NOT raise, and the error is captured
        assert isinstance(result, ReconciliationResult)
        assert result.summary["error"] >= 1
        error_actions = [a for a in result.actions if a.action == "error"]
        assert len(error_actions) >= 1
        assert "unexpected boom" in error_actions[0].message

        monkeypatch.setattr(recon_mod, "_reconcile_single_feature", original)

    def test_check_workflow_drift_catches_exception_from_check_single(
        self, tmp_path, monkeypatch
    ) -> None:
        """Exception in _check_single_feature is caught in bulk scan.
        derived_from: dimension:error_propagation (never-raises contract)

        Anticipate: If the try/except in check_workflow_drift's bulk
        loop doesn't catch exceptions, one bad feature would abort
        the entire drift check.
        """
        # Given two features, one of which will cause an exception
        db = _make_db()
        type_id1 = _register_feature(db, "001-good")
        db.create_workflow_phase(
            type_id1, workflow_phase="create-plan", last_completed_phase="design", mode="standard"
        )
        _create_meta_json(tmp_path, "001-good", status="active", last_completed_phase="design")

        type_id2 = _register_feature(db, "002-bad")
        db.create_workflow_phase(
            type_id2, workflow_phase="specify", last_completed_phase="brainstorm", mode="standard"
        )
        _create_meta_json(tmp_path, "002-bad", status="active", last_completed_phase="design")

        engine = WorkflowStateEngine(db, str(tmp_path))

        # Monkeypatch _check_single_feature to explode on "002-bad"
        import workflow_engine.reconciliation as recon_mod
        original = recon_mod._check_single_feature

        def selective_check(eng, database, ftype_id, meta):
            if "002-bad" in ftype_id:
                raise RuntimeError("check exploded")
            return original(eng, database, ftype_id, meta)

        monkeypatch.setattr(recon_mod, "_check_single_feature", selective_check)

        # When checking drift in bulk
        result = check_workflow_drift(engine, db, str(tmp_path))

        # Then it does NOT raise
        assert isinstance(result, WorkflowDriftResult)
        # And 001-good is processed normally
        status_map = {r.feature_type_id: r.status for r in result.features}
        assert status_map.get("feature:001-good") == "in_sync"
        # And 002-bad shows as error
        assert status_map.get("feature:002-bad") == "error"

        monkeypatch.setattr(recon_mod, "_check_single_feature", original)


# ===========================================================================
# Test-deepener: Phase B -- Mutation Mindset tests
# derived_from: dimension:mutation_mindset
# ===========================================================================


class TestMutationMindsetReconciliation:
    """Tests designed to catch specific mutations in reconciliation.py.
    derived_from: dimension:mutation_mindset
    """

    def test_compare_phases_direction_matters(self) -> None:
        """Swapping meta and db args must reverse the result.
        derived_from: dimension:mutation_mindset (arithmetic swap)

        Anticipate: If the comparison operators are accidentally
        inverted (> to <), meta_json_ahead and db_ahead would swap.
        This test calls _compare_phases with swapped arguments and
        verifies the result is the opposite.
        """
        # Given: meta ahead scenario
        result_meta_ahead = _compare_phases("implement", "finish", "design", "create-plan")
        # When: swap meta and db arguments
        result_swapped = _compare_phases("design", "create-plan", "implement", "finish")
        # Then: results are opposite
        assert result_meta_ahead == "meta_json_ahead"
        assert result_swapped == "db_ahead"

    def test_dry_run_true_prevents_db_write_for_created(self, tmp_path) -> None:
        """dry_run=True on meta_json_only prevents create_workflow_phase call.
        derived_from: dimension:mutation_mindset (line deletion: dry_run guard)

        Anticipate: If the `if not dry_run:` guard is deleted from the
        meta_json_only branch, dry_run would actually create rows.
        """
        # Given a meta_json_only feature with registered entity
        db = _make_db()
        _register_feature(db, "010-test")

        report = WorkflowDriftReport(
            feature_type_id="feature:010-test",
            status="meta_json_only",
            meta_json={
                "workflow_phase": "design",
                "last_completed_phase": "specify",
                "mode": "standard",
                "status": "active",
            },
            db=None,
            mismatches=(),
        )

        # When reconciling with dry_run=True
        action = _reconcile_single_feature(db, report, dry_run=True)

        # Then action is "created" but NO row exists in DB
        assert action.action == "created"
        row = db.get_workflow_phase("feature:010-test")
        assert row is None, "dry_run=True should not create DB rows"

    def test_reconciliation_result_dry_run_count_logic(self, tmp_path) -> None:
        """dry_run count = reconciled + created (not skipped or error).
        derived_from: dimension:mutation_mindset (return value mutation)

        Anticipate: If dry_run count includes skipped or error actions,
        the preview would overcount. If it excludes created, it would
        undercount for meta_json_only features.
        """
        from workflow_engine.reconciliation import _build_reconciliation_result

        # Given a mix of actions
        actions = [
            ReconcileAction(
                feature_type_id="feature:001-test",
                action="reconciled",
                direction="meta_json_to_db",
                changes=(),
                message="Reconciled",
            ),
            ReconcileAction(
                feature_type_id="feature:002-test",
                action="created",
                direction="meta_json_to_db",
                changes=(),
                message="Created",
            ),
            ReconcileAction(
                feature_type_id="feature:003-test",
                action="skipped",
                direction="meta_json_to_db",
                changes=(),
                message="Skipped",
            ),
            ReconcileAction(
                feature_type_id="feature:004-test",
                action="error",
                direction="meta_json_to_db",
                changes=(),
                message="Error",
            ),
        ]

        # When building result with dry_run=True
        result = _build_reconciliation_result(actions, dry_run=True)

        # Then dry_run count = reconciled (1) + created (1) = 2
        assert result.summary["dry_run"] == 2
        assert result.summary["reconciled"] == 1
        assert result.summary["created"] == 1
        assert result.summary["skipped"] == 1
        assert result.summary["error"] == 1

    def test_reconciliation_result_dry_run_false_count_zero(self) -> None:
        """dry_run=False produces dry_run count = 0 in summary.
        derived_from: dimension:mutation_mindset (return value mutation)

        Anticipate: If the dry_run branch condition is inverted,
        dry_run count would be non-zero when dry_run is False.
        """
        from workflow_engine.reconciliation import _build_reconciliation_result

        actions = [
            ReconcileAction(
                feature_type_id="feature:001-test",
                action="reconciled",
                direction="meta_json_to_db",
                changes=(),
                message="Reconciled",
            ),
        ]

        # When building result with dry_run=False
        result = _build_reconciliation_result(actions, dry_run=False)

        # Then dry_run count is 0
        assert result.summary["dry_run"] == 0

    def test_reconcile_direction_always_meta_json_to_db(self, tmp_path) -> None:
        """All ReconcileAction.direction values are 'meta_json_to_db'.
        derived_from: dimension:mutation_mindset (return value mutation)

        Anticipate: If direction is accidentally set to "db_to_meta_json"
        or some other string, the MCP serialization would report the
        wrong direction to callers.
        """
        # Given multiple features in different states
        db = _make_db()
        type_id1 = _register_feature(db, "001-ahead")
        db.create_workflow_phase(
            type_id1, workflow_phase="specify", last_completed_phase="brainstorm", mode="standard"
        )
        _create_meta_json(tmp_path, "001-ahead", status="active", last_completed_phase="design")

        type_id2 = _register_feature(db, "002-synced")
        db.create_workflow_phase(
            type_id2, workflow_phase="create-plan", last_completed_phase="design", mode="standard"
        )
        _create_meta_json(tmp_path, "002-synced", status="active", last_completed_phase="design")

        engine = WorkflowStateEngine(db, str(tmp_path))

        # When reconciling all
        result = apply_workflow_reconciliation(engine, db, str(tmp_path))

        # Then every action has direction="meta_json_to_db"
        for action in result.actions:
            assert action.direction == "meta_json_to_db", (
                f"Expected direction 'meta_json_to_db' for {action.feature_type_id}, "
                f"got '{action.direction}'"
            )

    def test_healthy_flag_requires_both_dimensions_clean(self, tmp_path) -> None:
        """Healthy means ALL non-in_sync counts are zero in summary.
        derived_from: dimension:mutation_mindset (logic inversion: && to ||)

        Anticipate: If the healthy check uses OR instead of AND,
        having one clean dimension would report healthy=True even
        when the other has drift.
        Verify: This tests _build_drift_result summary at module level.
        """
        from workflow_engine.reconciliation import _build_drift_result

        # Given: one in_sync + one meta_json_ahead report
        reports = [
            WorkflowDriftReport(
                feature_type_id="feature:001-test",
                status="in_sync",
                meta_json=None,
                db=None,
                mismatches=(),
            ),
            WorkflowDriftReport(
                feature_type_id="feature:002-test",
                status="meta_json_ahead",
                meta_json=None,
                db=None,
                mismatches=(),
            ),
        ]

        result = _build_drift_result(reports)

        # Then summary shows both counts
        assert result.summary["in_sync"] == 1
        assert result.summary["meta_json_ahead"] == 1
        # And a healthy check (as done in MCP server) would fail
        non_sync = {k: v for k, v in result.summary.items() if k != "in_sync"}
        assert any(v > 0 for v in non_sync.values()), (
            "Expected non-zero counts outside 'in_sync'"
        )


# ---------------------------------------------------------------------------
# Task 4a: _derive_expected_kanban helper
# ---------------------------------------------------------------------------


class TestDeriveExpectedKanban:
    """Tests for _derive_expected_kanban — maps phase to expected kanban column."""

    def test_derive_expected_kanban_none_phase(self):
        """None phase and None last_completed returns None."""
        assert _derive_expected_kanban(None, None) is None

    def test_derive_expected_kanban_finish_completed(self):
        """finish phase with finish as last_completed returns 'completed'."""
        assert _derive_expected_kanban("finish", "finish") == "completed"

    def test_derive_expected_kanban_finish_in_progress(self):
        """finish phase with last_completed before finish returns 'documenting'."""
        assert _derive_expected_kanban("finish", "specify") == "documenting"

    def test_derive_expected_kanban_implement(self):
        """implement phase returns 'wip'."""
        assert _derive_expected_kanban("implement", "specify") == "wip"

    def test_derive_expected_kanban_unknown_phase(self):
        """Unknown phase returns None."""
        assert _derive_expected_kanban("nonexistent", None) is None


# ===========================================================================
# Task 5: Kanban drift detection and reconciliation tests (TDD RED)
# ===========================================================================


class TestKanbanDriftDetection:
    """Kanban column drift detection in _check_single_feature (AC-4)."""

    def test_check_single_feature_detects_kanban_drift(self, tmp_path) -> None:
        """AC-4: kanban_column mismatch detected when DB kanban != expected.

        Setup: implement phase (expected kanban='wip') but DB has kanban='backlog'.
        Expect: mismatch with field='kanban_column', meta_json_value='wip', db_value='backlog'.
        """
        engine, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="implement",
            last_completed_phase="create-tasks",
            mode="standard",
        )
        # DB has kanban_column="backlog" (default from create_workflow_phase),
        # but implement phase expects "wip"
        meta = {
            "status": "active",
            "mode": "standard",
            "phases": {
                "brainstorm": {"started": "2026-01-01T00:00:00"},
                "specify": {"completed": "2026-01-02T00:00:00"},
                "design": {"completed": "2026-01-03T00:00:00"},
                "create-plan": {"completed": "2026-01-04T00:00:00"},
                "create-tasks": {"completed": "2026-01-05T00:00:00"},
            },
            "lastCompletedPhase": "create-tasks",
        }

        report = _check_single_feature(engine, db, type_id, meta)

        # Should detect kanban_column drift
        kanban_mismatches = [m for m in report.mismatches if m.field == "kanban_column"]
        assert len(kanban_mismatches) == 1, (
            f"Expected 1 kanban_column mismatch, got {len(kanban_mismatches)}. "
            f"All mismatches: {report.mismatches}"
        )
        km = kanban_mismatches[0]
        assert km.meta_json_value == "wip"
        assert km.db_value == "backlog"

    def test_check_single_feature_no_false_positive_kanban(self, tmp_path) -> None:
        """No false-positive kanban mismatch when DB kanban matches expected.

        Setup: implement phase with kanban_column='wip' in DB (correct).
        Expect: no kanban_column mismatch in report.
        """
        db = _make_db()
        type_id = _register_feature(db, "010-test")
        db.create_workflow_phase(
            type_id,
            workflow_phase="implement",
            last_completed_phase="create-tasks",
            mode="standard",
        )
        # Fix kanban to match expected value
        db.update_workflow_phase(type_id, kanban_column="wip")
        engine = WorkflowStateEngine(db, str(tmp_path))

        meta = {
            "status": "active",
            "mode": "standard",
            "phases": {
                "brainstorm": {"started": "2026-01-01T00:00:00"},
                "specify": {"completed": "2026-01-02T00:00:00"},
                "design": {"completed": "2026-01-03T00:00:00"},
                "create-plan": {"completed": "2026-01-04T00:00:00"},
                "create-tasks": {"completed": "2026-01-05T00:00:00"},
            },
            "lastCompletedPhase": "create-tasks",
        }

        report = _check_single_feature(engine, db, type_id, meta)

        kanban_mismatches = [m for m in report.mismatches if m.field == "kanban_column"]
        assert len(kanban_mismatches) == 0, (
            f"Expected no kanban_column mismatch, got: {kanban_mismatches}"
        )


class TestKanbanReconciliation:
    """Kanban column reconciliation in _reconcile_single_feature (AC-5)."""

    def test_reconcile_single_feature_corrects_kanban(self, tmp_path) -> None:
        """AC-5: reconciliation updates kanban_column when drifted.

        Setup: meta_json_ahead report with kanban_column mismatch (backlog->wip).
        Expect: after reconcile, DB kanban_column == 'wip'.
        """
        _, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="implement",
            last_completed_phase="create-tasks",
            mode="standard",
        )
        # DB has kanban_column="backlog" (default)

        report = WorkflowDriftReport(
            feature_type_id=type_id,
            status="meta_json_ahead",
            meta_json={
                "workflow_phase": "implement",
                "last_completed_phase": "create-tasks",
                "mode": "standard",
                "status": "active",
            },
            db={
                "workflow_phase": "implement",
                "last_completed_phase": "create-tasks",
                "mode": "standard",
                "kanban_column": "backlog",
            },
            mismatches=(
                WorkflowMismatch(
                    field="kanban_column",
                    meta_json_value="wip",
                    db_value="backlog",
                ),
            ),
        )

        _reconcile_single_feature(db, report, dry_run=False)

        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["kanban_column"] == "wip", (
            f"Expected kanban_column='wip' after reconcile, got '{row['kanban_column']}'"
        )

    def test_reconcile_single_feature_skips_kanban_when_none(self, tmp_path) -> None:
        """Reconciliation leaves kanban_column unchanged when derived kanban is None.

        Setup: meta has workflow_phase='nonexistent' (unknown phase -> kanban=None).
        Expect: kanban_column remains 'backlog' (unchanged).
        """
        _, db, type_id = _setup_engine(
            tmp_path,
            slug="010-test",
            workflow_phase="implement",
            last_completed_phase="create-tasks",
            mode="standard",
        )
        # DB has kanban_column="backlog" (default)

        report = WorkflowDriftReport(
            feature_type_id=type_id,
            status="meta_json_ahead",
            meta_json={
                "workflow_phase": "nonexistent",
                "last_completed_phase": "create-tasks",
                "mode": "standard",
                "status": "active",
            },
            db={
                "workflow_phase": "implement",
                "last_completed_phase": "create-tasks",
                "mode": "standard",
                "kanban_column": "backlog",
            },
            mismatches=(
                WorkflowMismatch(
                    field="kanban_column",
                    meta_json_value=None,
                    db_value="backlog",
                ),
            ),
        )

        _reconcile_single_feature(db, report, dry_run=False)

        row = db.get_workflow_phase(type_id)
        assert row is not None
        assert row["kanban_column"] == "backlog", (
            f"Expected kanban_column='backlog' (unchanged), got '{row['kanban_column']}'"
        )
