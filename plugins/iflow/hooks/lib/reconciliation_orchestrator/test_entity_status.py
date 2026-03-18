"""Unit tests for reconciliation_orchestrator.entity_status.sync_entity_statuses.

TDD: tests written before implementation. All tests should fail with ImportError
until entity_status.py is created.

Fixtures use temp directories and in-memory EntityDatabase for isolation.
"""
import json
import os
import tempfile

import pytest

from entity_registry.database import EntityDatabase
from reconciliation_orchestrator.entity_status import sync_entity_statuses


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_db() -> EntityDatabase:
    """Return a fresh in-memory EntityDatabase."""
    return EntityDatabase(":memory:")


def seed_feature(db: EntityDatabase, folder: str, status: str) -> None:
    """Register a feature entity with the given folder name and status."""
    db.register_entity(
        entity_type="feature",
        entity_id=folder,
        name=folder,
        status=status,
    )


def seed_project(db: EntityDatabase, folder: str, status: str) -> None:
    """Register a project entity with the given folder name and status."""
    db.register_entity(
        entity_type="project",
        entity_id=folder,
        name=folder,
        status=status,
    )


def write_meta_json(directory: str, status: str) -> None:
    """Write a minimal .meta.json with the given status into directory."""
    os.makedirs(directory, exist_ok=True)
    meta = {"status": status}
    with open(os.path.join(directory, ".meta.json"), "w") as f:
        json.dump(meta, f)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDriftedStatusUpdated:
    """test_drifted_status_updated: .meta.json status differs from entity status → updated."""

    def test_drifted_status_updated(self, tmp_path):
        db = make_db()
        folder = "042-some-feature"
        seed_feature(db, folder, status="active")

        features_dir = tmp_path / "features" / folder
        write_meta_json(str(features_dir), status="completed")

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["updated"] == 1
        assert result["skipped"] == 0
        assert result["archived"] == 0
        assert result["warnings"] == []

        # Verify the entity DB was actually updated
        entity = db.get_entity(f"feature:{folder}")
        assert entity["status"] == "completed"


class TestNoDriftSkipped:
    """test_no_drift_skipped: matching statuses → no update, counted as skipped."""

    def test_no_drift_skipped(self, tmp_path):
        db = make_db()
        folder = "042-some-feature"
        seed_feature(db, folder, status="active")

        features_dir = tmp_path / "features" / folder
        write_meta_json(str(features_dir), status="active")

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["updated"] == 0
        assert result["skipped"] == 1
        assert result["archived"] == 0
        assert result["warnings"] == []

        # Entity status unchanged
        entity = db.get_entity(f"feature:{folder}")
        assert entity["status"] == "active"


class TestMissingMetaJsonArchived:
    """test_missing_meta_json_archived: entity exists, .meta.json missing → archived."""

    def test_missing_meta_json_archived(self, tmp_path):
        db = make_db()
        folder = "042-some-feature"
        seed_feature(db, folder, status="active")

        # Create the folder but NOT .meta.json
        feature_dir = tmp_path / "features" / folder
        feature_dir.mkdir(parents=True)

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["archived"] == 1
        assert result["updated"] == 0
        assert result["warnings"] == []

        entity = db.get_entity(f"feature:{folder}")
        assert entity["status"] == "archived"


class TestMalformedJsonWarned:
    """test_malformed_json_warned: corrupt .meta.json → warning, entity skipped."""

    def test_malformed_json_warned(self, tmp_path):
        db = make_db()
        folder = "042-some-feature"
        seed_feature(db, folder, status="active")

        feature_dir = tmp_path / "features" / folder
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text("{ this is not valid json }")

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["updated"] == 0
        assert len(result["warnings"]) == 1
        assert ".meta.json" in result["warnings"][0]

        # Entity status must not have changed
        entity = db.get_entity(f"feature:{folder}")
        assert entity["status"] == "active"


class TestUnknownStatusSkipped:
    """test_unknown_status_skipped: .meta.json status="draft" → warning, entity skipped."""

    def test_unknown_status_skipped(self, tmp_path):
        db = make_db()
        folder = "042-some-feature"
        seed_feature(db, folder, status="active")

        features_dir = tmp_path / "features" / folder
        write_meta_json(str(features_dir), status="draft")

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["updated"] == 0
        assert len(result["warnings"]) == 1
        assert "draft" in result["warnings"][0]

        # Entity unchanged
        entity = db.get_entity(f"feature:{folder}")
        assert entity["status"] == "active"


class TestEntityNotInRegistrySkipped:
    """test_entity_not_in_registry_skipped: .meta.json exists, no entity in DB → skipped."""

    def test_entity_not_in_registry_skipped(self, tmp_path):
        db = make_db()
        # No entity registered
        folder = "042-some-feature"

        features_dir = tmp_path / "features" / folder
        write_meta_json(str(features_dir), status="active")

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["skipped"] == 1
        assert result["updated"] == 0
        assert result["archived"] == 0
        assert result["warnings"] == []


class TestMissingDirectoryHandled:
    """test_missing_directory_handled: features/ dir doesn't exist → empty results."""

    def test_missing_directory_handled(self, tmp_path):
        db = make_db()
        # tmp_path has no features/ or projects/ subdirs

        result = sync_entity_statuses(db, str(tmp_path))

        assert result == {"updated": 0, "skipped": 0, "archived": 0, "warnings": []}


class TestProjectsScanned:
    """test_projects_scanned: projects/ dir is scanned with the same sync logic."""

    def test_projects_scanned(self, tmp_path):
        db = make_db()
        folder = "my-project"
        seed_project(db, folder, status="active")

        projects_dir = tmp_path / "projects" / folder
        write_meta_json(str(projects_dir), status="completed")

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["updated"] == 1
        assert result["warnings"] == []

        entity = db.get_entity(f"project:{folder}")
        assert entity["status"] == "completed"

    def test_projects_missing_meta_json_archived(self, tmp_path):
        """Entity in registry, project folder exists but .meta.json deleted → archived."""
        db = make_db()
        folder = "my-project"
        seed_project(db, folder, status="active")

        # Folder exists, no .meta.json
        project_dir = tmp_path / "projects" / folder
        project_dir.mkdir(parents=True)

        result = sync_entity_statuses(db, str(tmp_path))

        assert result["archived"] == 1

        entity = db.get_entity(f"project:{folder}")
        assert entity["status"] == "archived"
