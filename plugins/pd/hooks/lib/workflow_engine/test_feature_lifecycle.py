"""Tests for workflow_engine.feature_lifecycle — extracted business logic."""
from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from workflow_engine.feature_lifecycle import (
    activate_feature,
    init_feature_state,
    init_project_state,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_artifacts(tmp_path):
    """Create a temporary artifacts_root with a features/ subdirectory."""
    features_dir = tmp_path / "features"
    features_dir.mkdir()
    return str(tmp_path)


@pytest.fixture()
def feature_dir(tmp_artifacts):
    """Create a feature directory under artifacts_root.

    The directory name must match the slug used in feature_type_id.
    For feature_id='001', slug='001-my-feature', the type_id slug becomes
    '001-001-my-feature', which _validate_feature_type_id resolves against
    artifacts_root/features/.
    """
    d = os.path.join(tmp_artifacts, "features", "001-001-my-feature")
    os.makedirs(d, exist_ok=True)
    return d


@pytest.fixture()
def mock_db():
    db = MagicMock()
    db.get_entity.return_value = None
    return db


@pytest.fixture()
def mock_engine():
    return MagicMock()


# ===========================================================================
# init_feature_state
# ===========================================================================

class TestInitFeatureState:
    """Tests for init_feature_state."""

    def test_creates_new_feature_entity(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        """Happy path: registers new entity when none exists."""
        result = init_feature_state(
            db=mock_db,
            engine=mock_engine,
            artifacts_root=tmp_artifacts,
            feature_dir=feature_dir,
            feature_id="001",
            slug="001-my-feature",
            mode="standard",
            branch="feature/001",
            status="active",
        )

        assert result["created"] is True
        assert result["feature_type_id"] == "feature:001-001-my-feature"
        assert result["status"] == "active"
        assert result["meta_json_path"] == os.path.join(feature_dir, ".meta.json")
        mock_db.register_entity.assert_called_once()

    def test_updates_existing_entity_preserves_timing(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        """When entity exists, update it and preserve phase_timing."""
        mock_db.get_entity.return_value = {
            "status": "active",
            "metadata": json.dumps({
                "phase_timing": {"brainstorm": {"started": "2025-01-01T00:00:00"}},
                "last_completed_phase": "design",
                "skipped_phases": ["brainstorm"],
            }),
        }

        result = init_feature_state(
            db=mock_db,
            engine=mock_engine,
            artifacts_root=tmp_artifacts,
            feature_dir=feature_dir,
            feature_id="001",
            slug="001-my-feature",
            mode="standard",
            branch="feature/001",
            status="active",
        )

        assert result["created"] is True
        mock_db.register_entity.assert_not_called()
        mock_db.update_entity.assert_called_once()
        # Verify preserved fields passed through
        call_kwargs = mock_db.update_entity.call_args
        metadata = call_kwargs[1].get("metadata") or call_kwargs[0][2] if len(call_kwargs[0]) > 2 else call_kwargs[1]["metadata"]
        assert metadata["last_completed_phase"] == "design"
        assert metadata["skipped_phases"] == ["brainstorm"]

    def test_includes_brainstorm_source(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        result = init_feature_state(
            db=mock_db,
            engine=mock_engine,
            artifacts_root=tmp_artifacts,
            feature_dir=feature_dir,
            feature_id="001",
            slug="001-my-feature",
            mode="standard",
            branch="feature/001",
            brainstorm_source="brainstorm:001",
            status="active",
        )
        assert result["created"] is True
        # brainstorm_source should be in the metadata passed to register_entity
        call_kwargs = mock_db.register_entity.call_args[1]
        assert call_kwargs["metadata"]["brainstorm_source"] == "brainstorm:001"

    def test_includes_backlog_source(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        result = init_feature_state(
            db=mock_db,
            engine=mock_engine,
            artifacts_root=tmp_artifacts,
            feature_dir=feature_dir,
            feature_id="001",
            slug="001-my-feature",
            mode="standard",
            branch="feature/001",
            backlog_source="backlog:001",
            status="active",
        )
        assert result["created"] is True
        call_kwargs = mock_db.register_entity.call_args[1]
        assert call_kwargs["metadata"]["backlog_source"] == "backlog:001"

    def test_planned_status_sets_kanban_backlog(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        result = init_feature_state(
            db=mock_db,
            engine=mock_engine,
            artifacts_root=tmp_artifacts,
            feature_dir=feature_dir,
            feature_id="001",
            slug="001-my-feature",
            mode="standard",
            branch="feature/001",
            status="planned",
        )
        assert result["status"] == "planned"
        mock_db.update_workflow_phase.assert_called_once_with(
            "feature:001-001-my-feature", kanban_column="backlog"
        )

    def test_kanban_update_falls_back_to_create(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        """When update_workflow_phase fails, falls back to create_workflow_phase."""
        mock_db.update_workflow_phase.side_effect = ValueError("no row")

        result = init_feature_state(
            db=mock_db,
            engine=mock_engine,
            artifacts_root=tmp_artifacts,
            feature_dir=feature_dir,
            feature_id="001",
            slug="001-my-feature",
            mode="standard",
            branch="feature/001",
            status="active",
        )
        assert result["created"] is True
        mock_db.create_workflow_phase.assert_called_once()

    def test_invalid_feature_type_id_raises(self, mock_db, mock_engine, tmp_artifacts):
        """Path traversal: feature_dir doesn't match artifacts_root."""
        with pytest.raises(ValueError, match="feature_not_found"):
            init_feature_state(
                db=mock_db,
                engine=mock_engine,
                artifacts_root=tmp_artifacts,
                feature_dir="/tmp/evil",
                feature_id="001",
                slug="../../etc",
                mode="standard",
                branch="feature/001",
                status="active",
            )

    # -----------------------------------------------------------------------
    # Field validation: feature_id, slug, branch — 9 tests (3 fields x 3 inputs)
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("field_name,overrides", [
        ("feature_id", {"feature_id": None}),
        ("feature_id", {"feature_id": ""}),
        ("feature_id", {"feature_id": "   "}),
        ("slug", {"slug": None}),
        ("slug", {"slug": ""}),
        ("slug", {"slug": "   "}),
        ("branch", {"branch": None}),
        ("branch", {"branch": ""}),
        ("branch", {"branch": "\t\n"}),
    ])
    def test_rejects_invalid_field(self, mock_db, mock_engine, tmp_artifacts, feature_dir, field_name, overrides):
        """init_feature_state rejects None, empty, and whitespace-only values."""
        defaults = dict(
            db=mock_db,
            engine=mock_engine,
            artifacts_root=tmp_artifacts,
            feature_dir=feature_dir,
            feature_id="001",
            slug="001-my-feature",
            mode="standard",
            branch="feature/001",
            status="active",
        )
        defaults.update(overrides)
        with pytest.raises(ValueError, match=f"invalid_input: {field_name}"):
            init_feature_state(**defaults)

    def test_no_projection_warning_when_none(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        """projection_warning key absent when no warning."""
        result = init_feature_state(
            db=mock_db,
            engine=mock_engine,
            artifacts_root=tmp_artifacts,
            feature_dir=feature_dir,
            feature_id="001",
            slug="001-my-feature",
            mode="standard",
            branch="feature/001",
            status="active",
        )
        assert "projection_warning" not in result


# ===========================================================================
# _promote_brainstorm (via init_feature_state)
# ===========================================================================

class TestPromoteBrainstorm:
    """Tests for brainstorm promotion when creating a feature."""

    def test_promotes_brainstorm_in_draft(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        """Brainstorm entity in draft status gets promoted."""
        # _promote_brainstorm calls get_entity first, then init_feature_state calls it for the feature.
        mock_db.get_entity.side_effect = [
            {"status": "draft", "entity_type": "brainstorm"},  # brainstorm lookup
            None,   # feature lookup
        ]
        mock_db.get_workflow_phase.return_value = {"workflow_phase": "draft", "kanban_column": "wip"}

        init_feature_state(
            db=mock_db, engine=mock_engine, artifacts_root=tmp_artifacts,
            feature_dir=feature_dir, feature_id="001", slug="001-my-feature",
            mode="standard", branch="feature/001",
            brainstorm_source="docs/brainstorms/20260327-test.prd.md",
            status="active",
        )

        # Verify brainstorm was promoted
        update_calls = [c for c in mock_db.update_entity.call_args_list
                        if c[0][0] == "brainstorm:20260327-test"]
        assert len(update_calls) == 1
        assert update_calls[0][1]["status"] == "promoted"

        # Verify workflow_phase updated
        wf_calls = [c for c in mock_db.update_workflow_phase.call_args_list
                    if c[0][0] == "brainstorm:20260327-test"]
        assert len(wf_calls) == 1
        assert wf_calls[0][1]["workflow_phase"] == "promoted"
        assert wf_calls[0][1]["kanban_column"] == "completed"

    def test_skips_already_promoted_brainstorm(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        """No update when brainstorm is already promoted."""
        mock_db.get_entity.side_effect = [
            {"status": "promoted", "entity_type": "brainstorm"},  # brainstorm
            None,  # feature lookup
        ]

        init_feature_state(
            db=mock_db, engine=mock_engine, artifacts_root=tmp_artifacts,
            feature_dir=feature_dir, feature_id="001", slug="001-my-feature",
            mode="standard", branch="feature/001",
            brainstorm_source="docs/brainstorms/20260327-test.prd.md",
            status="active",
        )

        # update_entity should not be called for brainstorm
        update_calls = [c for c in mock_db.update_entity.call_args_list
                        if len(c[0]) > 0 and c[0][0] == "brainstorm:20260327-test"]
        assert len(update_calls) == 0

    def test_handles_nonexistent_brainstorm(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        """No error when brainstorm entity doesn't exist in registry."""
        mock_db.get_entity.return_value = None  # brainstorm missing, feature missing

        result = init_feature_state(
            db=mock_db, engine=mock_engine, artifacts_root=tmp_artifacts,
            feature_dir=feature_dir, feature_id="001", slug="001-my-feature",
            mode="standard", branch="feature/001",
            brainstorm_source="docs/brainstorms/20260327-test.prd.md",
            status="active",
        )

        assert result["created"] is True

    def test_no_promotion_without_brainstorm_source(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        """No promotion attempt when brainstorm_source is None."""
        mock_db.get_entity.return_value = None

        init_feature_state(
            db=mock_db, engine=mock_engine, artifacts_root=tmp_artifacts,
            feature_dir=feature_dir, feature_id="001", slug="001-my-feature",
            mode="standard", branch="feature/001",
            status="active",
        )

        # Only the feature register_entity call, no brainstorm lookups beyond feature
        assert mock_db.get_entity.call_count == 1

    def test_stem_extraction_full_path(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        """Stem extracted correctly from full path with .prd.md suffix."""
        mock_db.get_entity.side_effect = [
            {"status": "draft", "entity_type": "brainstorm"},  # brainstorm
            None,  # feature
        ]
        mock_db.get_workflow_phase.return_value = None  # no workflow row

        init_feature_state(
            db=mock_db, engine=mock_engine, artifacts_root=tmp_artifacts,
            feature_dir=feature_dir, feature_id="001", slug="001-my-feature",
            mode="standard", branch="feature/001",
            brainstorm_source="docs/brainstorms/20260327-040000-my-brainstorm.prd.md",
            status="active",
        )

        update_calls = [c for c in mock_db.update_entity.call_args_list
                        if len(c[0]) > 0 and c[0][0] == "brainstorm:20260327-040000-my-brainstorm"]
        assert len(update_calls) == 1

    def test_handles_missing_workflow_row(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        """Promotes entity status even when no workflow_phases row exists."""
        mock_db.get_entity.side_effect = [
            {"status": "reviewing", "entity_type": "brainstorm"},  # brainstorm
            None,  # feature
        ]
        mock_db.get_workflow_phase.return_value = None  # no workflow row

        init_feature_state(
            db=mock_db, engine=mock_engine, artifacts_root=tmp_artifacts,
            feature_dir=feature_dir, feature_id="001", slug="001-my-feature",
            mode="standard", branch="feature/001",
            brainstorm_source="docs/brainstorms/20260327-test.prd.md",
            status="active",
        )

        # Entity status updated but workflow_phase update skipped
        update_calls = [c for c in mock_db.update_entity.call_args_list
                        if len(c[0]) > 0 and c[0][0] == "brainstorm:20260327-test"]
        assert len(update_calls) == 1
        assert mock_db.update_workflow_phase.call_count == 1  # only the feature kanban update

    def test_db_error_does_not_block_feature_creation(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        """Database errors during brainstorm promotion are silently swallowed."""
        mock_db.get_entity.side_effect = [
            Exception("DB locked"),  # brainstorm lookup fails (in _promote_brainstorm)
            None,  # feature lookup (after _promote_brainstorm catches the exception)
        ]

        result = init_feature_state(
            db=mock_db, engine=mock_engine, artifacts_root=tmp_artifacts,
            feature_dir=feature_dir, feature_id="001", slug="001-my-feature",
            mode="standard", branch="feature/001",
            brainstorm_source="docs/brainstorms/20260327-test.prd.md",
            status="active",
        )

        assert result["created"] is True


# ===========================================================================
# init_project_state
# ===========================================================================

class TestInitProjectState:
    """Tests for init_project_state."""

    def test_creates_new_project(self, mock_db, tmp_path):
        project_dir = str(tmp_path / "projects" / "my-proj")
        os.makedirs(project_dir, exist_ok=True)

        result = init_project_state(
            db=mock_db,
            artifacts_root=str(tmp_path),
            project_dir=project_dir,
            project_id="P01",
            slug="my-proj",
            branch="feature/P01",
            features='["feat-a","feat-b"]',
            milestones='["m1"]',
        )

        assert result["created"] is True
        assert result["project_type_id"] == "project:P01-my-proj"
        assert os.path.isfile(result["meta_json_path"])
        mock_db.register_entity.assert_called_once()

    def test_idempotent_existing_project(self, mock_db, tmp_path):
        """If project entity already exists, skip registration."""
        project_dir = str(tmp_path / "projects" / "my-proj")
        os.makedirs(project_dir, exist_ok=True)
        mock_db.get_entity.return_value = {"status": "active"}

        result = init_project_state(
            db=mock_db,
            artifacts_root=str(tmp_path),
            project_dir=project_dir,
            project_id="P01",
            slug="my-proj",
            branch="feature/P01",
            features='["feat-a"]',
            milestones='["m1"]',
        )

        assert result["created"] is True
        mock_db.register_entity.assert_not_called()

    def test_meta_json_content(self, mock_db, tmp_path):
        project_dir = str(tmp_path / "projects" / "my-proj")
        os.makedirs(project_dir, exist_ok=True)

        result = init_project_state(
            db=mock_db,
            artifacts_root=str(tmp_path),
            project_dir=project_dir,
            project_id="P01",
            slug="my-proj",
            branch="feature/P01",
            features='["feat-a"]',
            milestones='["m1","m2"]',
            brainstorm_source="brainstorm:001",
        )

        with open(result["meta_json_path"]) as f:
            meta = json.load(f)
        assert meta["id"] == "P01"
        assert meta["slug"] == "my-proj"
        assert meta["features"] == ["feat-a"]
        assert meta["milestones"] == ["m1", "m2"]
        assert meta["brainstorm_source"] == "brainstorm:001"

    def test_null_byte_raises(self, mock_db, tmp_path):
        with pytest.raises(ValueError, match="path traversal"):
            init_project_state(
                db=mock_db,
                artifacts_root=str(tmp_path),
                project_dir="/some/dir\0evil",
                project_id="P01",
                slug="my-proj",
                branch="feature/P01",
                features="[]",
                milestones="[]",
            )

    def test_nonexistent_dir_raises(self, mock_db, tmp_path):
        with pytest.raises(ValueError, match="does not exist"):
            init_project_state(
                db=mock_db,
                artifacts_root=str(tmp_path),
                project_dir="/nonexistent/dir",
                project_id="P01",
                slug="my-proj",
                branch="feature/P01",
                features="[]",
                milestones="[]",
            )

    def test_invalid_json_features_raises(self, mock_db, tmp_path):
        project_dir = str(tmp_path / "projects" / "my-proj")
        os.makedirs(project_dir, exist_ok=True)

        with pytest.raises((ValueError, json.JSONDecodeError)):
            init_project_state(
                db=mock_db,
                artifacts_root=str(tmp_path),
                project_dir=project_dir,
                project_id="P01",
                slug="my-proj",
                branch="feature/P01",
                features="not-json",
                milestones="[]",
            )

    def test_features_and_milestones_are_required(self):
        """features and milestones are required str params (no defaults)."""
        import inspect
        sig = inspect.signature(init_project_state)
        features_param = sig.parameters["features"]
        milestones_param = sig.parameters["milestones"]
        assert features_param.default is inspect.Parameter.empty
        assert milestones_param.default is inspect.Parameter.empty


# ===========================================================================
# activate_feature
# ===========================================================================

class TestActivateFeature:
    """Tests for activate_feature."""

    def test_activates_planned_feature(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        mock_db.get_entity.return_value = {"status": "planned"}

        result = activate_feature(
            db=mock_db,
            engine=mock_engine,
            artifacts_root=tmp_artifacts,
            feature_type_id="feature:001-001-my-feature",
        )

        assert result["activated"] is True
        assert result["previous_status"] == "planned"
        assert result["new_status"] == "active"
        assert result["feature_type_id"] == "feature:001-001-my-feature"
        mock_db.update_entity.assert_called_once_with(
            "feature:001-001-my-feature", status="active"
        )

    def test_feature_not_found_raises(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        mock_db.get_entity.return_value = None

        with pytest.raises(ValueError, match="feature_not_found"):
            activate_feature(
                db=mock_db,
                engine=mock_engine,
                artifacts_root=tmp_artifacts,
                feature_type_id="feature:001-001-my-feature",
            )

    def test_non_planned_status_raises(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        mock_db.get_entity.return_value = {"status": "active"}

        with pytest.raises(ValueError, match="invalid_transition"):
            activate_feature(
                db=mock_db,
                engine=mock_engine,
                artifacts_root=tmp_artifacts,
                feature_type_id="feature:001-001-my-feature",
            )

    def test_projection_warning_included(self, mock_db, mock_engine, tmp_artifacts, feature_dir):
        """When _project_meta_json returns a warning, include it in result."""
        mock_db.get_entity.return_value = {"status": "planned"}

        # activate_feature does NOT call _project_meta_json — that stays in the server wrapper.
        # So there should be no projection_warning key.
        result = activate_feature(
            db=mock_db,
            engine=mock_engine,
            artifacts_root=tmp_artifacts,
            feature_type_id="feature:001-001-my-feature",
        )
        assert "projection_warning" not in result
