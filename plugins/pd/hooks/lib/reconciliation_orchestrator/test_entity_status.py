"""Unit tests for reconciliation_orchestrator.entity_status — sync functions."""
import json
import os
import tempfile
from unittest.mock import patch

import pytest

from entity_registry.database import EntityDatabase
from reconciliation_orchestrator import entity_status
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
        project_id="__unknown__",
    )


def seed_project(db: EntityDatabase, folder: str, status: str) -> None:
    """Register a project entity with the given folder name and status."""
    db.register_entity(
        entity_type="project",
        entity_id=folder,
        name=folder,
        status=status,
        project_id="__unknown__",
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

        assert result["updated"] == 0
        assert result["skipped"] == 0
        assert result["archived"] == 0
        assert result["warnings"] == []


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


# ---------------------------------------------------------------------------
# _sync_brainstorm_entities tests
# ---------------------------------------------------------------------------


def seed_brainstorm(db: EntityDatabase, entity_id: str, status: str = "active",
                    artifact_path: str = "", project_id: str = "test-project") -> None:
    """Register a brainstorm entity for testing."""
    db.register_entity(
        entity_type="brainstorm",
        entity_id=entity_id,
        name=entity_id,
        status=status,
        artifact_path=artifact_path,
        project_id=project_id,
    )


class TestSyncBrainstormEntities:
    """Tests for entity_status._sync_brainstorm_entities (AC-8, AC-9)."""

    def test_new_brainstorm_registered(self, tmp_path):
        """A .prd.md file with no entity in registry -> entity registered as active."""
        db = make_db()
        brainstorms_dir = tmp_path / "brainstorms"
        brainstorms_dir.mkdir()
        (brainstorms_dir / "foo.prd.md").touch()

        result = entity_status._sync_brainstorm_entities(
            db, str(tmp_path), "docs", str(tmp_path), "test-project"
        )

        assert result["registered"] == 1
        entity = db.get_entity("brainstorm:foo")
        assert entity is not None
        assert entity["status"] == "active"

    def test_existing_brainstorm_skipped(self, tmp_path):
        """Already-registered brainstorm -> skipped, no duplicate created."""
        db = make_db()
        seed_brainstorm(db, "foo")
        brainstorms_dir = tmp_path / "brainstorms"
        brainstorms_dir.mkdir()
        (brainstorms_dir / "foo.prd.md").touch()

        result = entity_status._sync_brainstorm_entities(
            db, str(tmp_path), "docs", str(tmp_path), "test-project"
        )

        assert result["skipped"] == 1
        # No duplicate entity created
        entities = db.list_entities(entity_type="brainstorm")
        assert len(entities) == 1

    def test_missing_prd_file_archived(self, tmp_path):
        """AC-9: brainstorm entity exists but .prd.md file deleted -> status archived."""
        db = make_db()
        seed_brainstorm(
            db, "foo", status="active",
            artifact_path="docs/brainstorms/foo.prd.md",
            project_id="test-project",
        )
        # Do NOT create the file — it should be detected as missing
        # brainstorms dir must exist for the scan to proceed
        brainstorms_dir = tmp_path / "brainstorms"
        brainstorms_dir.mkdir()

        result = entity_status._sync_brainstorm_entities(
            db, str(tmp_path), "docs", str(tmp_path), "test-project"
        )

        assert result["archived"] == 1
        entity = db.get_entity("brainstorm:foo")
        assert entity["status"] == "archived"

    def test_terminal_brainstorm_not_rearchived(self, tmp_path):
        """Brainstorm with terminal status (promoted) -> not re-archived even if file missing."""
        db = make_db()
        seed_brainstorm(
            db, "foo", status="promoted",
            artifact_path="docs/brainstorms/foo.prd.md",
            project_id="test-project",
        )
        # No file created — but promoted is terminal, should not be touched
        brainstorms_dir = tmp_path / "brainstorms"
        brainstorms_dir.mkdir()

        result = entity_status._sync_brainstorm_entities(
            db, str(tmp_path), "docs", str(tmp_path), "test-project"
        )

        assert result["archived"] == 0
        entity = db.get_entity("brainstorm:foo")
        assert entity["status"] == "promoted"


# ---------------------------------------------------------------------------
# Backlog sync helpers
# ---------------------------------------------------------------------------

def seed_backlog(db: EntityDatabase, entity_id: str, status: str | None = None) -> None:
    """Register a backlog entity with the given ID and status."""
    db.register_entity(
        entity_type="backlog",
        entity_id=entity_id,
        name=entity_id,
        artifact_path="docs/backlog.md",
        status=status or "open",
        project_id="test-project",
    )


def write_backlog_md(tmp_path, rows: list[tuple[str, str, str]]) -> None:
    """Write a pipe-delimited markdown table to tmp_path/backlog.md.

    Each row is (id, timestamp, description).
    """
    lines = [
        "| ID | Added | Description |",
        "|------|-------|-------------|",
    ]
    for row_id, ts, desc in rows:
        lines.append(f"| {row_id} | {ts} | {desc} |")
    (tmp_path / "backlog.md").write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Backlog sync tests
# ---------------------------------------------------------------------------

class TestSyncBacklogEntities:
    """Tests for _sync_backlog_entities()."""

    def test_closed_status_mapped_to_dropped(self, tmp_path):
        """Task 1.2: (closed: not needed) marker maps to dropped status."""
        db = make_db()
        seed_backlog(db, "00014", status="open")
        write_backlog_md(tmp_path, [
            ("00014", "2026-01-01T00:00:00Z", "Security Scanning (closed: not needed)"),
        ])

        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        entity = db.get_entity("backlog:00014")
        assert entity["status"] == "dropped"

    def test_promoted_status_mapped(self, tmp_path):
        """Task 1.3: (promoted -> feature:048) marker maps to promoted status."""
        db = make_db()
        seed_backlog(db, "00020", status="open")
        write_backlog_md(tmp_path, [
            ("00020", "2026-01-01T00:00:00Z", "Rename plugin (promoted \u2192 feature:048)"),
        ])

        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        entity = db.get_entity("backlog:00020")
        assert entity["status"] == "promoted"

    def test_fixed_status_mapped_to_dropped(self, tmp_path):
        """Task 1.4: (fixed: auto-increment) marker maps to dropped status."""
        db = make_db()
        seed_backlog(db, "00048", status="open")
        write_backlog_md(tmp_path, [
            ("00048", "2026-01-01T00:00:00Z", "Release tag check (fixed: auto-increment)"),
        ])

        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        entity = db.get_entity("backlog:00048")
        assert entity["status"] == "dropped"

    def test_already_implemented_mapped_to_dropped(self, tmp_path):
        """Task 1.5: (closed: already implemented -- Stage 4) maps to dropped."""
        db = make_db()
        seed_backlog(db, "00046", status="open")
        write_backlog_md(tmp_path, [
            ("00046", "2026-01-01T00:00:00Z",
             "Add review cycle (closed: already implemented \u2014 Stage 4)"),
        ])

        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        entity = db.get_entity("backlog:00046")
        assert entity["status"] == "dropped"

    def test_no_marker_registered_as_open(self, tmp_path):
        """Task 1.6: No status marker in description -> registered as open."""
        db = make_db()
        # No seed -- entity does not exist in DB yet
        write_backlog_md(tmp_path, [
            ("00016", "2026-01-01T00:00:00Z", "Multi-Model Orchestration"),
        ])

        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        entity = db.get_entity("backlog:00016")
        assert entity is not None
        assert entity["status"] == "open"
        assert result["registered"] == 1

    def test_junk_ids_deleted(self, tmp_path):
        """Task 1.7: Non-5-digit entity IDs are deleted from DB."""
        db = make_db()
        seed_backlog(db, "B2")
        seed_backlog(db, "#")
        seed_backlog(db, "~~B1~~")
        write_backlog_md(tmp_path, [
            ("00001", "2026-01-01T00:00:00Z", "Valid item"),
        ])

        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        assert db.get_entity("backlog:B2") is None
        assert db.get_entity("backlog:#") is None
        assert db.get_entity("backlog:~~B1~~") is None
        assert result["deleted"] == 3

    def test_junk_deletion_skips_entity_with_children(self, tmp_path):
        """Task 1.8: Junk deletion handles ValueError (entity with children) gracefully."""
        db = make_db()
        seed_backlog(db, "JUNK1")
        write_backlog_md(tmp_path, [
            ("00001", "2026-01-01T00:00:00Z", "Valid item"),
        ])

        with patch.object(db, "delete_entity", side_effect=ValueError("has children")):
            result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        assert len(result["warnings"]) >= 1
        assert any("JUNK1" in w for w in result["warnings"])

    def test_same_project_dedup(self, tmp_path):
        """Task 1.9: Duplicate backlog entities with same project_id are deduplicated.

        The DB schema has UNIQUE(project_id, type_id) which normally prevents
        duplicates. This test simulates legacy data by rebuilding the table
        without the constraint, then verifying dedup cleans up.
        """
        db = make_db()
        seed_backlog(db, "00020", status="open")

        # Rebuild entities table without UNIQUE constraint to allow duplicate
        import uuid as uuid_mod
        db._conn.execute("CREATE TABLE entities_bak AS SELECT * FROM entities")
        db._conn.execute("DROP TABLE entities")
        db._conn.execute("""
            CREATE TABLE entities (
                uuid TEXT NOT NULL PRIMARY KEY,
                type_id TEXT NOT NULL,
                project_id TEXT NOT NULL DEFAULT '__unknown__',
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT,
                parent_type_id TEXT,
                parent_uuid TEXT,
                artifact_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT
            )
        """)
        db._conn.execute("INSERT INTO entities SELECT * FROM entities_bak")
        db._conn.execute("DROP TABLE entities_bak")
        # Now insert the duplicate (same project_id + type_id, different uuid)
        db._conn.execute(
            "INSERT INTO entities (uuid, entity_type, entity_id, type_id, name, "
            "artifact_path, status, project_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (str(uuid_mod.uuid4()), "backlog", "00020", "backlog:00020",
             "00020", "docs/backlog.md", None, "test-project"),
        )
        db._conn.commit()

        write_backlog_md(tmp_path, [
            ("00020", "2026-01-01T00:00:00Z", "Rename plugin"),
        ])

        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        # One duplicate should have been removed
        rows = db._conn.execute(
            "SELECT * FROM entities WHERE entity_type='backlog' AND entity_id='00020' "
            "AND project_id='test-project'"
        ).fetchall()
        assert len(rows) == 1
        assert result["deleted"] >= 1

    def test_missing_backlog_md_returns_empty(self, tmp_path):
        """Task 1.10: No backlog.md file -> return empty results dict."""
        db = make_db()
        # No backlog.md written

        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        assert result == {
            "updated": 0,
            "skipped": 0,
            "registered": 0,
            "deleted": 0,
            "warnings": [],
        }


# ---------------------------------------------------------------------------
# Unified sync integration test (Task 4.3)
# ---------------------------------------------------------------------------


class TestUnifiedSync:
    """Integration test: sync_entity_statuses calls all 4 helpers."""

    def test_unified_sync_all_four_types(self, tmp_path):
        """All entity types synced in one call; return dict has all 6 keys."""
        db = make_db()

        # 1) Feature: seed as active, .meta.json says completed -> drift -> updated
        feature_folder = "042-test"
        db.register_entity(
            entity_type="feature", entity_id=feature_folder,
            name=feature_folder, status="active", project_id="test-project",
        )
        write_meta_json(str(tmp_path / "features" / feature_folder), status="completed")

        # 2) Project: .meta.json present, no entity in DB -> skipped
        project_folder = "test-proj"
        (tmp_path / "projects" / project_folder).mkdir(parents=True)
        write_meta_json(str(tmp_path / "projects" / project_folder), status="active")

        # 3) Brainstorm: .prd.md file, no entity in DB -> registered
        brainstorms_dir = tmp_path / "brainstorms"
        brainstorms_dir.mkdir()
        (brainstorms_dir / "bar.prd.md").touch()

        # 4) Backlog: one row -> registered
        write_backlog_md(tmp_path, [
            ("00099", "2026-01-01T00:00:00Z", "Test backlog item"),
        ])

        result = sync_entity_statuses(
            db, str(tmp_path),
            project_id="test-project",
            artifacts_root="docs",
            project_root=str(tmp_path),
        )

        # All 6 keys must be present
        assert set(result.keys()) == {
            "updated", "skipped", "archived", "registered", "deleted", "warnings",
        }

        # Drifted feature should have been updated
        assert result["updated"] >= 1
        entity = db.get_entity(f"feature:{feature_folder}")
        assert entity["status"] == "completed"

        # Brainstorm and backlog should have been registered
        assert result["registered"] >= 2
        assert db.get_entity("brainstorm:bar") is not None
        assert db.get_entity("backlog:00099") is not None
