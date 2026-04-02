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
# Deepened tests — boundary values, adversarial, error propagation, mutation
# ---------------------------------------------------------------------------


class TestBacklogBoundaryValues:
    """Boundary value tests for backlog ID validation and name handling."""

    def test_backlog_id_exactly_5_digits_accepted(self, tmp_path):
        """BVA: 5-digit IDs at boundaries (00001 and 99999) are valid, not junk.
        derived_from: spec:AC-6 (junk entity deletion — ^[0-9]{5}$ regex)
        """
        # Given backlog entities with boundary 5-digit IDs
        db = make_db()
        seed_backlog(db, "00001", status="open")
        seed_backlog(db, "99999", status="open")
        write_backlog_md(tmp_path, [
            ("00001", "2026-01-01T00:00:00Z", "First item"),
            ("99999", "2026-01-01T00:00:00Z", "Last item"),
        ])

        # When backlog sync runs
        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        # Then both entities survive (not deleted as junk)
        assert db.get_entity("backlog:00001") is not None
        assert db.get_entity("backlog:99999") is not None
        assert result["deleted"] == 0

    def test_backlog_id_4_digits_is_junk(self, tmp_path):
        """BVA: 4-digit ID '0001' fails ^[0-9]{5}$ — deleted as junk.
        derived_from: spec:AC-6 (junk entity deletion)
        """
        # Given a backlog entity with a 4-digit ID (boundary: min-1 digits)
        db = make_db()
        seed_backlog(db, "0001", status="open")
        write_backlog_md(tmp_path, [
            ("00001", "2026-01-01T00:00:00Z", "Valid item"),
        ])

        # When backlog sync runs
        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        # Then the 4-digit entity is deleted
        assert db.get_entity("backlog:0001") is None
        assert result["deleted"] == 1

    def test_backlog_id_6_digits_is_junk(self, tmp_path):
        """BVA: 6-digit ID '000001' fails ^[0-9]{5}$ — deleted as junk.
        derived_from: spec:AC-6 (junk entity deletion)
        """
        # Given a backlog entity with a 6-digit ID (boundary: max+1 digits)
        db = make_db()
        seed_backlog(db, "000001", status="open")
        write_backlog_md(tmp_path, [
            ("00001", "2026-01-01T00:00:00Z", "Valid item"),
        ])

        # When backlog sync runs
        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        # Then the 6-digit entity is deleted
        assert db.get_entity("backlog:000001") is None
        assert result["deleted"] == 1

    def test_empty_backlog_md_produces_zero_counts(self, tmp_path):
        """BVA: backlog.md with header only, no data rows → zero registered/updated.
        derived_from: dimension:boundary_values (empty collection)
        """
        # Given a backlog.md with only the header row
        db = make_db()
        (tmp_path / "backlog.md").write_text(
            "| ID | Added | Description |\n"
            "|------|-------|-------------|\n"
        )

        # When backlog sync runs
        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        # Then all counts are zero
        assert result["registered"] == 0
        assert result["updated"] == 0
        assert result["skipped"] == 0

    def test_backlog_name_truncated_at_200_chars(self, tmp_path):
        """BVA: Description longer than 200 chars → name truncated to 200.
        derived_from: dimension:boundary_values (string length max)
        """
        # Given a backlog row with a 250-char description
        db = make_db()
        long_desc = "A" * 250
        write_backlog_md(tmp_path, [
            ("00001", "2026-01-01T00:00:00Z", long_desc),
        ])

        # When backlog sync runs
        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        # Then the registered entity name is at most 200 chars
        entity = db.get_entity("backlog:00001")
        assert entity is not None
        assert len(entity["name"]) <= 200
        assert result["registered"] == 1


class TestBacklogAdversarial:
    """Adversarial tests for backlog status marker edge cases."""

    def test_standalone_already_implemented_mapped_to_dropped(self, tmp_path):
        """Adversarial: '(already implemented' WITHOUT '(closed:' prefix maps to dropped.
        derived_from: spec:AC-2 (backlog status mapping — standalone variant)
        """
        # Given a backlog row with standalone "(already implemented" marker
        db = make_db()
        seed_backlog(db, "00046", status="open")
        write_backlog_md(tmp_path, [
            ("00046", "2026-01-01T00:00:00Z",
             "Add review cycle (already implemented in Stage 4)"),
        ])

        # When backlog sync runs
        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        # Then entity status maps to dropped (spec says standalone variant)
        entity = db.get_entity("backlog:00046")
        assert entity["status"] == "dropped"

    def test_promoted_with_unicode_arrow_mapped(self, tmp_path):
        """Adversarial: both → (unicode) and -> (ascii) arrows detected as promoted.
        derived_from: spec:AC-3 (promotion detection)
        """
        # Given backlog rows with both arrow variants
        db = make_db()
        seed_backlog(db, "00020", status="open")
        seed_backlog(db, "00021", status="open")
        write_backlog_md(tmp_path, [
            ("00020", "2026-01-01T00:00:00Z", "Item A (promoted → feature:048)"),
            ("00021", "2026-01-01T00:00:00Z", "Item B (promoted -> feature:049)"),
        ])

        # When backlog sync runs
        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        # Then both are promoted
        assert db.get_entity("backlog:00020")["status"] == "promoted"
        assert db.get_entity("backlog:00021")["status"] == "promoted"

    def test_cross_project_duplicates_not_touched(self, tmp_path):
        """Adversarial: duplicates with DIFFERENT project_ids are NOT deduped.
        derived_from: spec:AC-7 (out of scope: cross-project dedup)
        """
        # Given two entities with the same entity_id but different project_ids
        db = make_db()
        db.register_entity(
            entity_type="backlog", entity_id="00020", name="Item",
            artifact_path="docs/backlog.md", status="open",
            project_id="project-A",
        )
        db.register_entity(
            entity_type="backlog", entity_id="00020", name="Item",
            artifact_path="docs/backlog.md", status="open",
            project_id="project-B",
        )
        write_backlog_md(tmp_path, [
            ("00020", "2026-01-01T00:00:00Z", "Some item"),
        ])

        # When backlog sync runs for project-A
        result = entity_status._sync_backlog_entities(
            db, str(tmp_path), "docs", "project-A"
        )

        # Then both entities still exist (cross-project dups not touched)
        rows = db._conn.execute(
            "SELECT * FROM entities WHERE entity_type='backlog' AND entity_id='00020'"
        ).fetchall()
        assert len(rows) == 2

    def test_backlog_row_with_multiple_status_markers(self, tmp_path):
        """Adversarial: row with multiple markers → first match wins (regex priority).
        derived_from: dimension:adversarial (marker ambiguity)
        """
        # Given a backlog row with both closed AND promoted markers
        db = make_db()
        seed_backlog(db, "00030", status="open")
        write_backlog_md(tmp_path, [
            ("00030", "2026-01-01T00:00:00Z",
             "Item (closed: not needed) (promoted -> feature:050)"),
        ])

        # When backlog sync runs
        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        # Then closed wins (checked first in the if/elif chain)
        entity = db.get_entity("backlog:00030")
        assert entity["status"] == "dropped"

    def test_backlog_row_with_parenthetical_not_a_status_marker(self, tmp_path):
        """Adversarial: '(needs review)' is NOT a recognized status marker → open.
        derived_from: dimension:adversarial (false positive parenthetical)
        """
        # Given a backlog row with non-marker parenthetical text
        db = make_db()
        write_backlog_md(tmp_path, [
            ("00031", "2026-01-01T00:00:00Z",
             "Add caching layer (needs review)"),
        ])

        # When backlog sync runs
        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        # Then entity is registered as open (parenthetical is not a status marker)
        entity = db.get_entity("backlog:00031")
        assert entity is not None
        assert entity["status"] == "open"
        assert result["registered"] == 1

    def test_name_stripping_removes_status_marker_not_entire_description(self, tmp_path):
        """Adversarial: NAME_STRIP_RE removes only the status marker parenthetical.
        derived_from: dimension:adversarial (name corruption)
        """
        # Given a backlog row with description and a closed marker
        db = make_db()
        write_backlog_md(tmp_path, [
            ("00032", "2026-01-01T00:00:00Z",
             "Security Scanning (closed: not needed)"),
        ])

        # When backlog sync runs
        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        # Then the name contains the description but NOT the status marker
        entity = db.get_entity("backlog:00032")
        assert entity is not None
        assert "Security Scanning" in entity["name"]
        assert "(closed" not in entity["name"]


class TestDedupEdgeCases:
    """Adversarial/boundary tests for dedup logic."""

    def test_dedup_both_entities_have_null_status(self, tmp_path):
        """Adversarial: both duplicates have null status → tie-break by uuid, one survives.
        derived_from: spec:AC-7 (dedup — null-status tie-break)
        """
        # Given two entities with the same ID and project_id, both with null status
        db = make_db()
        import uuid as uuid_mod

        # Rebuild table without UNIQUE constraint (same pattern as existing test)
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

        # Insert two entities with null status
        for _ in range(2):
            db._conn.execute(
                "INSERT INTO entities (uuid, entity_type, entity_id, type_id, name, "
                "artifact_path, status, project_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
                (str(uuid_mod.uuid4()), "backlog", "00050", "backlog:00050",
                 "Test item", "docs/backlog.md", None, "test-project"),
            )
        db._conn.commit()

        write_backlog_md(tmp_path, [
            ("00050", "2026-01-01T00:00:00Z", "Test item"),
        ])

        # When backlog sync runs
        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        # Then exactly one entity remains
        rows = db._conn.execute(
            "SELECT * FROM entities WHERE entity_type='backlog' AND entity_id='00050' "
            "AND project_id='test-project'"
        ).fetchall()
        assert len(rows) == 1
        assert result["deleted"] >= 1


class TestBrainstormAdversarial:
    """Adversarial tests for brainstorm sync edge cases."""

    def test_brainstorm_with_empty_artifact_path_not_archived(self, tmp_path):
        """Adversarial: brainstorm entity with empty artifact_path → NOT archived.
        The archival logic requires artifact_path to be non-empty to proceed.
        derived_from: dimension:adversarial (empty artifact_path guard)
        """
        # Given a brainstorm entity with empty artifact_path (no file to check)
        db = make_db()
        seed_brainstorm(db, "bar", status="active", artifact_path="")
        brainstorms_dir = tmp_path / "brainstorms"
        brainstorms_dir.mkdir()
        # No bar.prd.md on disk

        # When brainstorm sync runs
        result = entity_status._sync_brainstorm_entities(
            db, str(tmp_path), "docs", str(tmp_path), "test-project"
        )

        # Then entity is NOT archived (empty artifact_path guard)
        entity = db.get_entity("brainstorm:bar")
        assert entity["status"] == "active"
        assert result["archived"] == 0

    def test_gitkeep_not_registered_as_brainstorm(self, tmp_path):
        """Adversarial: .gitkeep file in brainstorms/ dir is not registered.
        derived_from: dimension:adversarial (false positive file)
        """
        # Given a brainstorms dir with only .gitkeep
        db = make_db()
        brainstorms_dir = tmp_path / "brainstorms"
        brainstorms_dir.mkdir()
        (brainstorms_dir / ".gitkeep").touch()

        # When brainstorm sync runs
        result = entity_status._sync_brainstorm_entities(
            db, str(tmp_path), "docs", str(tmp_path), "test-project"
        )

        # Then no entity registered
        assert result["registered"] == 0
        assert db.list_entities(entity_type="brainstorm") == []


class TestMutationMindset:
    """Mutation-mindset tests: would swapping operators break things?"""

    def test_junk_regex_anchored_both_ends(self, tmp_path):
        """Mutation: if JUNK_ID_RE lost $ anchor, '12345x' would pass. Verify it doesn't.
        derived_from: dimension:mutation_mindset (regex anchoring)
        """
        # Given a backlog entity with ID that has valid prefix but trailing char
        db = make_db()
        seed_backlog(db, "12345x", status="open")
        write_backlog_md(tmp_path, [
            ("00001", "2026-01-01T00:00:00Z", "Valid item"),
        ])

        # When backlog sync runs
        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        # Then '12345x' is deleted as junk ($ anchor prevents partial match)
        assert db.get_entity("backlog:12345x") is None
        assert result["deleted"] == 1

    def test_execution_order_junk_before_dedup_before_sync(self, tmp_path):
        """Mutation: if junk cleanup ran AFTER sync, junk entities could get updated
        instead of deleted. Verify junk deletion happens first.
        derived_from: dimension:mutation_mindset (execution order)
        """
        # Given both junk and valid entities exist
        db = make_db()
        seed_backlog(db, "JUNK", status="open")  # junk ID
        seed_backlog(db, "00001", status="open")  # valid ID
        write_backlog_md(tmp_path, [
            ("00001", "2026-01-01T00:00:00Z", "Valid item (closed: done)"),
        ])

        # When backlog sync runs
        result = entity_status._sync_backlog_entities(db, str(tmp_path), "docs", "test-project")

        # Then junk is deleted AND valid item is updated (both happen correctly)
        assert db.get_entity("backlog:JUNK") is None
        assert result["deleted"] >= 1
        entity = db.get_entity("backlog:00001")
        assert entity["status"] == "dropped"  # updated from open to dropped
        assert result["updated"] == 1

    def test_project_root_derivation_when_empty(self, tmp_path):
        """Mutation: if project_root derivation logic was removed, assertion would fire.
        derived_from: dimension:mutation_mindset (conditional branch — empty project_root)
        """
        # Given full_artifacts_path ends with artifacts_root and project_root is empty
        db = make_db()
        full_path = str(tmp_path / "docs")
        os.makedirs(full_path, exist_ok=True)

        # When sync_entity_statuses is called with empty project_root
        result = sync_entity_statuses(
            db, full_path, project_id="test-project",
            artifacts_root="docs", project_root="",
        )

        # Then it derives project_root successfully (no assertion error)
        # and returns valid results
        assert isinstance(result, dict)
        assert "updated" in result


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
