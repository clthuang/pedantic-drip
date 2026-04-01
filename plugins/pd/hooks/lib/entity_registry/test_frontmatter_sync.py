"""Tests for entity_registry.frontmatter_sync module."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Phase 1: Dataclass and constant tests (task 1.2a)
# ---------------------------------------------------------------------------


class TestDataclasses:
    """Verify dataclass construction and field accessibility."""

    def test_field_mismatch_construction(self):
        """FieldMismatch stores field, file_value, db_value (spec R4)."""
        from entity_registry.frontmatter_sync import FieldMismatch

        m = FieldMismatch(field="entity_uuid", file_value="abc", db_value="xyz")
        assert m.field == "entity_uuid"
        assert m.file_value == "abc"
        assert m.db_value == "xyz"

    def test_drift_report_construction(self):
        """DriftReport stores all 6 fields."""
        from entity_registry.frontmatter_sync import DriftReport, FieldMismatch

        report = DriftReport(
            filepath="/tmp/test.md",
            type_id="feature:001-test",
            status="in_sync",
            file_fields={"entity_uuid": "abc"},
            db_fields={"uuid": "abc"},
            mismatches=[],
        )
        assert report.filepath == "/tmp/test.md"
        assert report.type_id == "feature:001-test"
        assert report.status == "in_sync"
        assert report.file_fields == {"entity_uuid": "abc"}
        assert report.db_fields == {"uuid": "abc"}
        assert report.mismatches == []

    def test_stamp_result_construction(self):
        """StampResult stores filepath, action, message."""
        from entity_registry.frontmatter_sync import StampResult

        result = StampResult(filepath="/tmp/test.md", action="created", message="OK")
        assert result.filepath == "/tmp/test.md"
        assert result.action == "created"
        assert result.message == "OK"

    def test_ingest_result_construction(self):
        """IngestResult stores filepath, action, message."""
        from entity_registry.frontmatter_sync import IngestResult

        result = IngestResult(filepath="/tmp/test.md", action="updated", message="OK")
        assert result.filepath == "/tmp/test.md"
        assert result.action == "updated"
        assert result.message == "OK"


class TestConstants:
    """Verify module-level constants."""

    def test_comparable_field_map_content(self):
        """COMPARABLE_FIELD_MAP has exactly 2 entries (spec R6)."""
        from entity_registry.frontmatter_sync import COMPARABLE_FIELD_MAP

        assert len(COMPARABLE_FIELD_MAP) == 2
        assert COMPARABLE_FIELD_MAP["entity_uuid"] == "uuid"
        assert COMPARABLE_FIELD_MAP["entity_type_id"] == "type_id"

    def test_module_imports_resolve(self):
        """Module re-exports ARTIFACT_BASENAME_MAP and ARTIFACT_PHASE_MAP."""
        from entity_registry import frontmatter_sync

        assert hasattr(frontmatter_sync, "COMPARABLE_FIELD_MAP")
        assert hasattr(frontmatter_sync, "ARTIFACT_BASENAME_MAP")
        assert hasattr(frontmatter_sync, "ARTIFACT_PHASE_MAP")


# ---------------------------------------------------------------------------
# Phase 2: Internal helper tests (tasks 2.1a, 2.2a)
# ---------------------------------------------------------------------------


class TestDeriveOptionalFields:
    """Tests for _derive_optional_fields() helper (task 2.1a)."""

    def test_derive_feature_entity(self):
        """Feature type_id with artifact_type='spec' yields feature_id, feature_slug, phase."""
        from entity_registry.frontmatter_sync import _derive_optional_fields

        entity = {
            "type_id": "feature:003-bidirectional-uuid-sync-betwee",
            "metadata": None,
            "parent_type_id": None,
        }
        result = _derive_optional_fields(entity, "spec")
        assert result["feature_id"] == "003"
        assert result["feature_slug"] == "bidirectional-uuid-sync-betwee"
        assert result["phase"] == "specify"

    def test_derive_project_id_from_metadata(self):
        """Entity with metadata JSON containing project_id extracts it."""
        from entity_registry.frontmatter_sync import _derive_optional_fields

        entity = {
            "type_id": "feature:001-test",
            "metadata": '{"project_id": "P001"}',
            "parent_type_id": None,
        }
        result = _derive_optional_fields(entity, "spec")
        assert result["project_id"] == "P001"

    def test_derive_project_id_from_parent(self):
        """Entity with parent_type_id='project:P001' extracts project_id."""
        from entity_registry.frontmatter_sync import _derive_optional_fields

        entity = {
            "type_id": "feature:001-test",
            "metadata": None,
            "parent_type_id": "project:P001",
        }
        result = _derive_optional_fields(entity, "spec")
        assert result["project_id"] == "P001"

    def test_derive_metadata_priority(self):
        """When both metadata JSON and parent_type_id have project_id, metadata wins."""
        from entity_registry.frontmatter_sync import _derive_optional_fields

        entity = {
            "type_id": "feature:001-test",
            "metadata": '{"project_id": "META-ID"}',
            "parent_type_id": "project:PARENT-ID",
        }
        result = _derive_optional_fields(entity, "spec")
        assert result["project_id"] == "META-ID"

    def test_derive_non_feature_entity(self):
        """Non-feature entity (project) has no feature_id or feature_slug."""
        from entity_registry.frontmatter_sync import _derive_optional_fields

        entity = {
            "type_id": "project:P001",
            "metadata": None,
            "parent_type_id": None,
        }
        result = _derive_optional_fields(entity, "spec")
        assert "feature_id" not in result
        assert "feature_slug" not in result

    def test_derive_malformed_metadata(self):
        """Invalid JSON metadata falls back to parent_type_id for project_id."""
        from entity_registry.frontmatter_sync import _derive_optional_fields

        entity = {
            "type_id": "feature:001-test",
            "metadata": "not-valid-json{{{",
            "parent_type_id": "project:FALLBACK",
        }
        result = _derive_optional_fields(entity, "spec")
        assert result["project_id"] == "FALLBACK"

    def test_derive_no_project_id(self):
        """Neither metadata nor parent provides project_id — key absent from result."""
        from entity_registry.frontmatter_sync import _derive_optional_fields

        entity = {
            "type_id": "feature:001-test",
            "metadata": None,
            "parent_type_id": None,
        }
        result = _derive_optional_fields(entity, "spec")
        assert "project_id" not in result


class TestDeriveFeatureDirectory:
    """Tests for _derive_feature_directory() helper (task 2.2a)."""

    def test_derive_dir_from_artifact_path_dir(self, tmp_path):
        """artifact_path that is a directory returns it directly."""
        from entity_registry.frontmatter_sync import _derive_feature_directory

        feature_dir = tmp_path / "features" / "003-my-feature"
        feature_dir.mkdir(parents=True)
        entity = {"artifact_path": str(feature_dir), "entity_id": "003-my-feature"}
        result = _derive_feature_directory(entity, str(tmp_path))
        assert result == str(feature_dir)

    def test_derive_dir_from_artifact_path_file(self, tmp_path):
        """artifact_path that is a file returns its dirname."""
        from entity_registry.frontmatter_sync import _derive_feature_directory

        feature_dir = tmp_path / "features" / "003-my-feature"
        feature_dir.mkdir(parents=True)
        spec_file = feature_dir / "spec.md"
        spec_file.write_text("# Spec")
        entity = {"artifact_path": str(spec_file), "entity_id": "003-my-feature"}
        result = _derive_feature_directory(entity, str(tmp_path))
        assert result == str(feature_dir)

    def test_derive_dir_from_entity_id(self, tmp_path):
        """No artifact_path, constructs from entity_id when directory exists."""
        from entity_registry.frontmatter_sync import _derive_feature_directory

        feature_dir = tmp_path / "features" / "003-my-feature"
        feature_dir.mkdir(parents=True)
        entity = {"artifact_path": None, "entity_id": "003-my-feature"}
        result = _derive_feature_directory(entity, str(tmp_path))
        assert result == str(feature_dir)

    def test_derive_dir_none(self, tmp_path):
        """No artifact_path and constructed path doesn't exist returns None."""
        from entity_registry.frontmatter_sync import _derive_feature_directory

        entity = {"artifact_path": None, "entity_id": "999-nonexistent"}
        result = _derive_feature_directory(entity, str(tmp_path))
        assert result is None


# ---------------------------------------------------------------------------
# Phase 3: Core function tests (tasks 3.1a, 3.2a, 3.3a)
# ---------------------------------------------------------------------------


def _write_file(path, content: str) -> None:
    """Helper: write content to a file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _make_frontmatter(
    uuid: str, type_id: str, artifact_type: str = "spec", created_at: str = "2025-01-01T00:00:00+00:00"
) -> str:
    """Helper: build a valid YAML frontmatter block."""
    return (
        "---\n"
        f"entity_uuid: {uuid}\n"
        f"entity_type_id: {type_id}\n"
        f"artifact_type: {artifact_type}\n"
        f"created_at: {created_at}\n"
        "---\n"
    )


class TestDetectDrift:
    """Tests for detect_drift() (task 3.1a)."""

    def test_drift_in_sync(self, tmp_path):
        """Matching header and DB returns status='in_sync' (AC-1)."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import detect_drift

        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")
        entity = db.get_entity("feature:001-test")

        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(entity_uuid, "feature:001-test"))

        report = detect_drift(db, str(filepath), "feature:001-test")
        assert report.status == "in_sync"
        assert report.mismatches == []
        assert report.file_fields is not None
        assert report.db_fields is not None

    def test_drift_file_only(self, tmp_path):
        """Header with UUID but no DB record returns status='file_only' (AC-2)."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import detect_drift

        db = EntityDatabase(":memory:")
        fake_uuid = "12345678-1234-4123-8123-123456789abc"
        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(fake_uuid, "feature:999-nonexistent"))

        report = detect_drift(db, str(filepath))
        assert report.status == "file_only"

    def test_drift_db_only(self, tmp_path):
        """No header, type_id provided, DB record exists returns status='db_only' (AC-3)."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import detect_drift

        db = EntityDatabase(":memory:")
        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        filepath = tmp_path / "spec.md"
        _write_file(filepath, "# Spec\n\nBody content, no frontmatter.\n")

        report = detect_drift(db, str(filepath), "feature:001-test")
        assert report.status == "db_only"
        assert report.type_id == "feature:001-test"

    def test_drift_diverged_type_id(self, tmp_path):
        """Header type_id differs from DB type_id returns status='diverged' (AC-4)."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import detect_drift

        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        # File header has wrong type_id
        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(entity_uuid, "feature:999-wrong"))

        report = detect_drift(db, str(filepath), "feature:001-test")
        assert report.status == "diverged"
        assert len(report.mismatches) >= 1
        type_id_mismatches = [m for m in report.mismatches if m.field == "entity_type_id"]
        assert len(type_id_mismatches) == 1
        assert type_id_mismatches[0].file_value == "feature:999-wrong"
        assert type_id_mismatches[0].db_value == "feature:001-test"

    def test_drift_no_header(self, tmp_path):
        """No header and no type_id returns status='no_header' (AC-5)."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import detect_drift

        db = EntityDatabase(":memory:")

        filepath = tmp_path / "spec.md"
        _write_file(filepath, "# Spec\n\nNo frontmatter here.\n")

        report = detect_drift(db, str(filepath))
        assert report.status == "no_header"

    def test_drift_header_no_uuid_no_type_id(self, tmp_path):
        """Header without entity_uuid and no type_id returns 'no_header'."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import detect_drift

        db = EntityDatabase(":memory:")

        # Header with no entity_uuid field
        filepath = tmp_path / "spec.md"
        _write_file(filepath, "---\nartifact_type: spec\n---\n# Content\n")

        report = detect_drift(db, str(filepath))
        assert report.status == "no_header"

    def test_drift_type_id_different_uuid(self, tmp_path):
        """type_id provided but file has different UUID returns 'diverged'."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import detect_drift

        db = EntityDatabase(":memory:")
        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        # File has a completely different UUID
        different_uuid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(different_uuid, "feature:001-test"))

        report = detect_drift(db, str(filepath), "feature:001-test")
        assert report.status == "diverged"
        uuid_mismatches = [m for m in report.mismatches if m.field == "entity_uuid"]
        assert len(uuid_mismatches) == 1

    def test_drift_db_error(self, tmp_path):
        """db.get_entity raising RuntimeError returns status='error' (TD-4)."""
        from entity_registry.frontmatter_sync import detect_drift

        db = MagicMock()
        db.get_entity.side_effect = RuntimeError("connection lost")

        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(
            "12345678-1234-4123-8123-123456789abc", "feature:001-test"
        ))

        report = detect_drift(db, str(filepath), "feature:001-test")
        assert report.status == "error"


class TestStampHeader:
    """Tests for stamp_header() (task 3.2a)."""

    def test_stamp_creates_header(self, tmp_path):
        """No existing frontmatter creates a new header, action='created' (AC-6).

        created_at must come from the DB record (DB-authoritative).
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter import read_frontmatter
        from entity_registry.frontmatter_sync import stamp_header

        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")
        db_entity = db.get_entity("feature:001-test")

        filepath = tmp_path / "spec.md"
        _write_file(filepath, "# Spec\n\nBody content.\n")

        result = stamp_header(db, str(filepath), "feature:001-test", "spec")
        assert result.action == "created"

        header = read_frontmatter(str(filepath))
        assert header is not None
        assert header["entity_uuid"] == entity_uuid
        assert header["entity_type_id"] == "feature:001-test"
        assert header["artifact_type"] == "spec"
        # DB-authoritative: created_at from DB, NOT datetime.now()
        assert header["created_at"] == db_entity["created_at"]

    def test_stamp_with_project_id_from_metadata(self, tmp_path):
        """Metadata project_id appears in the stamped header (AC-6a)."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter import read_frontmatter
        from entity_registry.frontmatter_sync import stamp_header

        db = EntityDatabase(":memory:")
        db.register_entity(
            "feature", "001-test", "Test Feature",
            metadata={"project_id": "P001"},
            project_id="__unknown__",
        )

        filepath = tmp_path / "spec.md"
        _write_file(filepath, "# Spec\n")

        result = stamp_header(db, str(filepath), "feature:001-test", "spec")
        assert result.action == "created"

        header = read_frontmatter(str(filepath))
        assert header is not None
        assert header.get("project_id") == "P001"

    def test_stamp_updates_header(self, tmp_path):
        """Existing matching header returns action='updated' (AC-7).

        created_at preserves the file's original value (write_frontmatter merge semantics).
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter import read_frontmatter
        from entity_registry.frontmatter_sync import stamp_header

        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        # Write initial frontmatter with an older created_at
        original_created = "2024-01-01T00:00:00+00:00"
        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(entity_uuid, "feature:001-test", "spec", original_created))

        result = stamp_header(db, str(filepath), "feature:001-test", "spec")
        assert result.action == "updated"

        header = read_frontmatter(str(filepath))
        assert header is not None
        assert header["entity_uuid"] == entity_uuid
        # created_at preserved from the file's original value
        assert header["created_at"] == original_created

    def test_stamp_mismatch_error(self, tmp_path):
        """Existing different UUID returns action='error' (AC-8)."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import stamp_header

        db = EntityDatabase(":memory:")
        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        # Write frontmatter with a different UUID
        different_uuid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(different_uuid, "feature:001-test"))

        result = stamp_header(db, str(filepath), "feature:001-test", "spec")
        assert result.action == "error"
        assert "mismatch" in result.message.lower() or "UUID" in result.message

    def test_stamp_entity_not_found(self, tmp_path):
        """Bad type_id returns action='error' (AC-9)."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import stamp_header

        db = EntityDatabase(":memory:")

        filepath = tmp_path / "spec.md"
        _write_file(filepath, "# Spec\n")

        result = stamp_header(db, str(filepath), "feature:999-nonexistent", "spec")
        assert result.action == "error"
        assert "not found" in result.message.lower()

    def test_stamp_preserves_body(self, tmp_path):
        """Body content is unchanged after stamp (AC-10)."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import stamp_header

        db = EntityDatabase(":memory:")
        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        body_content = "# Spec\n\nThis is the body.\n\n## Section 2\n\nMore content.\n"
        filepath = tmp_path / "spec.md"
        _write_file(filepath, body_content)

        stamp_header(db, str(filepath), "feature:001-test", "spec")

        # Read full file, strip frontmatter, verify body
        with open(str(filepath)) as f:
            content = f.read()
        # Body starts after closing ---
        parts = content.split("---\n", 2)  # opening, header, rest
        assert len(parts) == 3
        assert parts[2] == body_content

    def test_stamp_header_no_uuid_in_existing(self, tmp_path):
        """Existing header without entity_uuid is treated as 'created'."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter import read_frontmatter
        from entity_registry.frontmatter_sync import stamp_header

        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        # Header without entity_uuid
        filepath = tmp_path / "spec.md"
        _write_file(filepath, "---\nartifact_type: spec\n---\n# Content\n")

        result = stamp_header(db, str(filepath), "feature:001-test", "spec")
        # No entity_uuid in existing = treat as create (no mismatch possible)
        assert result.action == "created"

        header = read_frontmatter(str(filepath))
        assert header is not None
        assert header["entity_uuid"] == entity_uuid

    def test_stamp_build_header_error(self, tmp_path):
        """Invalid artifact_type causes ValueError, returns action='error'."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import stamp_header

        db = EntityDatabase(":memory:")
        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        filepath = tmp_path / "spec.md"
        _write_file(filepath, "# Spec\n")

        result = stamp_header(db, str(filepath), "feature:001-test", "INVALID_TYPE")
        assert result.action == "error"


class TestIngestHeader:
    """Tests for ingest_header() (task 3.3a)."""

    def test_ingest_updates_path(self, tmp_path):
        """Valid header updates DB artifact_path, action='updated' (AC-11).

        Verifies db.update_entity is called with the UUID string (not type_id),
        exercising the _resolve_identifier path (spec R17).
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import ingest_header

        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(entity_uuid, "feature:001-test"))

        result = ingest_header(db, str(filepath))
        assert result.action == "updated"

        # Verify DB was updated
        entity = db.get_entity("feature:001-test")
        assert entity is not None
        assert entity["artifact_path"] == os.path.abspath(str(filepath))

    def test_ingest_no_frontmatter(self, tmp_path):
        """No header returns action='skipped' (AC-12)."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import ingest_header

        db = EntityDatabase(":memory:")

        filepath = tmp_path / "spec.md"
        _write_file(filepath, "# Spec\n\nNo frontmatter.\n")

        result = ingest_header(db, str(filepath))
        assert result.action == "skipped"

    def test_ingest_entity_not_found(self, tmp_path):
        """UUID not in DB returns action='error' (AC-13)."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import ingest_header

        db = EntityDatabase(":memory:")
        fake_uuid = "12345678-1234-4123-8123-123456789abc"

        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(fake_uuid, "feature:999-nonexistent"))

        result = ingest_header(db, str(filepath))
        assert result.action == "error"
        assert "not found" in result.message.lower()

    def test_ingest_no_uuid_in_header(self, tmp_path):
        """Header without entity_uuid returns action='skipped'."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import ingest_header

        db = EntityDatabase(":memory:")

        filepath = tmp_path / "spec.md"
        _write_file(filepath, "---\nartifact_type: spec\n---\n# Content\n")

        result = ingest_header(db, str(filepath))
        assert result.action == "skipped"

    def test_ingest_race_condition(self, tmp_path):
        """db.update_entity raises ValueError after get_entity succeeds -> action='error'."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import ingest_header

        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(entity_uuid, "feature:001-test"))

        # Mock update_entity to simulate a race condition (entity deleted between read and write)
        original_update = db.update_entity
        db.update_entity = MagicMock(side_effect=ValueError("Entity not found"))

        result = ingest_header(db, str(filepath))
        assert result.action == "error"
        assert "disappeared" in result.message.lower() or "entity" in result.message.lower()


# ---------------------------------------------------------------------------
# Phase 4: Bulk function tests (tasks 4.1a, 4.2a)
# ---------------------------------------------------------------------------


class TestBackfillHeaders:
    """Tests for backfill_headers() (task 4.1a)."""

    def test_backfill_stamps_all(self, tmp_path):
        """3 features x 2 files each = 6 stamps (AC-14).

        Setup: register 3 feature entities, create directories with spec.md
        and design.md in each.
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter import read_frontmatter
        from entity_registry.frontmatter_sync import backfill_headers

        db = EntityDatabase(":memory:")
        artifacts_root = str(tmp_path)

        # Register 3 features and create directories with 2 files each
        for i in range(1, 4):
            entity_id = f"00{i}-feature-{i}"
            db.register_entity("feature", entity_id, f"Feature {i}", project_id="__unknown__")
            feature_dir = tmp_path / "features" / entity_id
            feature_dir.mkdir(parents=True)
            (feature_dir / "spec.md").write_text(f"# Spec for feature {i}\n")
            (feature_dir / "design.md").write_text(f"# Design for feature {i}\n")

        results = backfill_headers(db, artifacts_root)

        # Should stamp all 6 files
        assert len(results) == 6
        created_results = [r for r in results if r.action == "created"]
        assert len(created_results) == 6

        # Verify all files now have frontmatter
        for i in range(1, 4):
            entity_id = f"00{i}-feature-{i}"
            for basename in ("spec.md", "design.md"):
                filepath = tmp_path / "features" / entity_id / basename
                header = read_frontmatter(str(filepath))
                assert header is not None, f"No header in {filepath}"
                assert header.get("entity_uuid") is not None

    def test_backfill_idempotent(self, tmp_path):
        """Running backfill twice produces identical file content (AC-15).

        First run: action='created'. Second run: action='updated'.
        File content is byte-identical after both runs.
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import backfill_headers

        db = EntityDatabase(":memory:")
        artifacts_root = str(tmp_path)

        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")
        feature_dir = tmp_path / "features" / "001-test"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# Spec\n")

        # First run
        results1 = backfill_headers(db, artifacts_root)
        assert len(results1) == 1
        assert results1[0].action == "created"

        # Capture file content after first run
        content_after_first = (feature_dir / "spec.md").read_text()

        # Second run
        results2 = backfill_headers(db, artifacts_root)
        assert len(results2) == 1
        assert results2[0].action == "updated"

        # File content is byte-identical
        content_after_second = (feature_dir / "spec.md").read_text()
        assert content_after_first == content_after_second

    def test_backfill_skips_mismatch(self, tmp_path):
        """Mismatched UUID in a file results in error in results (AC-16)."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import backfill_headers

        db = EntityDatabase(":memory:")
        artifacts_root = str(tmp_path)

        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")
        feature_dir = tmp_path / "features" / "001-test"
        feature_dir.mkdir(parents=True)

        # Write a file with a different UUID already stamped
        different_uuid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        (feature_dir / "spec.md").write_text(
            _make_frontmatter(different_uuid, "feature:001-test") + "# Spec\n"
        )

        results = backfill_headers(db, artifacts_root)
        assert len(results) == 1
        assert results[0].action == "error"

    def test_backfill_skips_missing_dir(self, tmp_path):
        """Entity with no directory on disk results in 'skipped' result."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import backfill_headers

        db = EntityDatabase(":memory:")
        artifacts_root = str(tmp_path)

        # Register entity but do NOT create the directory
        db.register_entity("feature", "999-no-dir", "Missing Dir Feature", project_id="__unknown__")

        results = backfill_headers(db, artifacts_root)
        assert len(results) == 1
        assert results[0].action == "skipped"
        assert "directory" in results[0].message.lower() or "no directory" in results[0].message.lower()

    def test_backfill_empty_db(self, tmp_path):
        """No features in DB returns empty list."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import backfill_headers

        db = EntityDatabase(":memory:")
        artifacts_root = str(tmp_path)

        results = backfill_headers(db, artifacts_root)
        assert results == []


class TestScanAll:
    """Tests for scan_all() (task 4.2a)."""

    def test_scan_mixed_statuses(self, tmp_path):
        """Features with headers and without headers return mixed statuses (AC-17).

        Feature 1: has headers (spec.md stamped) -> in_sync for spec.md
        Feature 2: no headers (spec.md plain) -> db_only for spec.md
        Since scan_all always passes type_id, files without frontmatter
        return 'db_only' (not 'no_header').
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import scan_all, stamp_header

        db = EntityDatabase(":memory:")
        artifacts_root = str(tmp_path)

        # Feature 1: stamped
        uuid1 = db.register_entity("feature", "001-stamped", "Stamped Feature", project_id="__unknown__")
        dir1 = tmp_path / "features" / "001-stamped"
        dir1.mkdir(parents=True)
        (dir1 / "spec.md").write_text("# Spec\n")
        stamp_header(db, str(dir1 / "spec.md"), "feature:001-stamped", "spec")

        # Feature 2: not stamped
        db.register_entity("feature", "002-plain", "Plain Feature", project_id="__unknown__")
        dir2 = tmp_path / "features" / "002-plain"
        dir2.mkdir(parents=True)
        (dir2 / "spec.md").write_text("# Spec without frontmatter\n")

        reports = scan_all(db, artifacts_root)

        assert len(reports) == 2

        # Find reports by filepath
        report_map = {r.filepath: r for r in reports}

        stamped_report = report_map[str(dir1 / "spec.md")]
        assert stamped_report.status == "in_sync"

        plain_report = report_map[str(dir2 / "spec.md")]
        assert plain_report.status == "db_only"

    def test_scan_empty_db(self, tmp_path):
        """No features in DB returns empty list."""
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import scan_all

        db = EntityDatabase(":memory:")
        artifacts_root = str(tmp_path)

        reports = scan_all(db, artifacts_root)
        assert reports == []


# ---------------------------------------------------------------------------
# Phase 5: Integration tests (tasks 5.1a, 5.2a, 5.3)
# ---------------------------------------------------------------------------


class TestBackfillHeaderAware:
    """Tests for run_backfill header_aware parameter (task 5.1a)."""

    def test_backfill_header_aware_true(self, tmp_path):
        """header_aware=True stamps headers even after backfill_complete (AC-18).

        Verifies that header stamping runs BEFORE the backfill_complete guard,
        so headers are stamped even on already-backfilled databases.
        """
        from entity_registry.backfill import run_backfill
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter import read_frontmatter

        db = EntityDatabase(":memory:")
        artifacts_root = str(tmp_path)

        # Register a feature entity and create its artifact files
        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")
        feature_dir = tmp_path / "features" / "001-test"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# Spec\n")

        # Mark backfill as complete (simulates production DB)
        db.set_metadata("backfill_complete", "1")

        # Run with header_aware=True -- should still stamp headers
        run_backfill(db, artifacts_root, header_aware=True)

        # Verify header was stamped
        header = read_frontmatter(str(feature_dir / "spec.md"))
        assert header is not None
        assert header.get("entity_uuid") is not None

    def test_backfill_header_aware_false(self, tmp_path):
        """header_aware=False (default) does NOT stamp headers (AC-19).

        Backward compatibility: existing callers are not affected.
        """
        from entity_registry.backfill import run_backfill
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter import read_frontmatter

        db = EntityDatabase(":memory:")
        artifacts_root = str(tmp_path)

        # Register a feature entity and create its artifact files
        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")
        feature_dir = tmp_path / "features" / "001-test"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# Spec\n")

        # Mark backfill as complete
        db.set_metadata("backfill_complete", "1")

        # Run with default (header_aware=False) -- should NOT stamp headers
        run_backfill(db, artifacts_root)

        # Verify NO header was stamped
        header = read_frontmatter(str(feature_dir / "spec.md"))
        assert header is None


class TestCLI:
    """Tests for frontmatter_sync_cli.py CLI entry point (task 5.2a)."""

    # Path to the Python interpreter inside the plugin venv
    PYTHON = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", ".venv", "bin", "python"
    )
    # PYTHONPATH so entity_registry resolves as a package
    LIB_DIR = os.path.join(os.path.dirname(__file__), "..")
    CLI_MODULE = "entity_registry.frontmatter_sync_cli"

    def _run_cli(self, args: list[str], env_extra: dict | None = None) -> subprocess.CompletedProcess:
        """Helper: invoke the CLI module via subprocess."""
        env = {**os.environ, "PYTHONPATH": self.LIB_DIR}
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, "-m", self.CLI_MODULE, *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    def test_cli_drift(self, tmp_path):
        """CLI drift subcommand outputs valid JSON with status field (AC-20)."""
        from entity_registry.database import EntityDatabase

        # Set up a DB and a file with matching frontmatter
        db_path = str(tmp_path / "test.db")
        db = EntityDatabase(db_path)
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")
        db.close()

        filepath = tmp_path / "spec.md"
        filepath.write_text(
            _make_frontmatter(entity_uuid, "feature:001-test") + "# Spec\n"
        )

        result = self._run_cli(
            ["drift", str(filepath), "feature:001-test"],
            env_extra={"ENTITY_DB_PATH": db_path},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert "status" in data

    def test_cli_backfill(self, tmp_path):
        """CLI backfill subcommand stamps headers and outputs JSON summary (AC-21)."""
        from entity_registry.database import EntityDatabase

        db_path = str(tmp_path / "test.db")
        db = EntityDatabase(db_path)
        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")
        db.close()

        feature_dir = tmp_path / "features" / "001-test"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# Spec\n")

        result = self._run_cli(
            ["backfill", str(tmp_path)],
            env_extra={"ENTITY_DB_PATH": db_path},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_cli_scan(self, tmp_path):
        """CLI scan subcommand outputs JSON array of drift reports (AC-22)."""
        from entity_registry.database import EntityDatabase

        db_path = str(tmp_path / "test.db")
        db = EntityDatabase(db_path)
        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")
        db.close()

        feature_dir = tmp_path / "features" / "001-test"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# Spec\n")

        result = self._run_cli(
            ["scan", str(tmp_path)],
            env_extra={"ENTITY_DB_PATH": db_path},
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert isinstance(data, list)

    def test_cli_db_error(self, tmp_path):
        """Invalid DB path produces JSON error output and exit code 1."""
        # Point to a path that cannot be a valid DB (inside a non-existent dir)
        bad_db_path = str(tmp_path / "nonexistent_dir" / "bad.db")

        filepath = tmp_path / "spec.md"
        filepath.write_text("# Spec\n")

        result = self._run_cli(
            ["drift", str(filepath), "feature:001-test"],
            env_extra={"ENTITY_DB_PATH": bad_db_path},
        )

        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert "error" in data

    def test_cli_bad_args(self):
        """Missing arguments produces non-zero exit code."""
        result = self._run_cli([])
        assert result.returncode != 0


class TestErrorHandling:
    """Error handling verification tests (task 5.3).

    These verify the never-raise pattern (TD-4): all sync functions return
    error/skipped results instead of raising exceptions.
    """

    def test_detect_drift_db_unavailable(self, tmp_path):
        """DB connection error returns status='error' (AC-23)."""
        from entity_registry.frontmatter_sync import detect_drift

        db = MagicMock()
        db.get_entity.side_effect = RuntimeError("DB connection lost")

        filepath = tmp_path / "spec.md"
        filepath.write_text(
            _make_frontmatter(
                "12345678-1234-4123-8123-123456789abc", "feature:001-test"
            )
            + "# Spec\n"
        )

        report = detect_drift(db, str(filepath), "feature:001-test")
        assert report.status == "error"

    def test_stamp_header_db_unavailable(self, tmp_path):
        """DB connection error returns action='error' (AC-23)."""
        from entity_registry.frontmatter_sync import stamp_header

        db = MagicMock()
        db.get_entity.side_effect = RuntimeError("DB connection lost")

        filepath = tmp_path / "spec.md"
        filepath.write_text("# Spec\n")

        result = stamp_header(db, str(filepath), "feature:001-test", "spec")
        assert result.action == "error"

    def test_ingest_header_db_unavailable(self, tmp_path):
        """DB connection error returns action='error' (AC-23)."""
        from entity_registry.frontmatter_sync import ingest_header

        db = MagicMock()
        db.get_entity.side_effect = RuntimeError("DB connection lost")

        filepath = tmp_path / "spec.md"
        filepath.write_text(
            _make_frontmatter(
                "12345678-1234-4123-8123-123456789abc", "feature:001-test"
            )
            + "# Spec\n"
        )

        result = ingest_header(db, str(filepath))
        assert result.action == "error"

    def test_detect_drift_missing_file(self, tmp_path):
        """Non-existent file returns status='no_header' (AC-24).

        read_frontmatter on non-existent file returns None (feature 002 contract).
        detect_drift with None header + no type_id -> 'no_header'.
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import detect_drift

        db = EntityDatabase(":memory:")
        nonexistent = str(tmp_path / "does_not_exist.md")

        report = detect_drift(db, nonexistent)
        assert report.status == "no_header"

    def test_stamp_header_missing_file(self, tmp_path):
        """Non-existent file returns action='error' (AC-24).

        write_frontmatter raises ValueError('File not found: ...')
        which stamp_header catches and returns as action='error'.
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import stamp_header

        db = EntityDatabase(":memory:")
        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")
        nonexistent = str(tmp_path / "does_not_exist.md")

        result = stamp_header(db, nonexistent, "feature:001-test", "spec")
        assert result.action == "error"

    def test_ingest_header_missing_file(self, tmp_path):
        """Non-existent file returns action='skipped' (AC-24).

        read_frontmatter on non-existent file returns None ->
        ingest_header returns action='skipped' (no frontmatter found).
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import ingest_header

        db = EntityDatabase(":memory:")
        nonexistent = str(tmp_path / "does_not_exist.md")

        result = ingest_header(db, nonexistent)
        assert result.action == "skipped"


# ---------------------------------------------------------------------------
# Phase 6: Test Deepening — Boundary Values
# ---------------------------------------------------------------------------


class TestBoundaryValues:
    """Boundary value and equivalence partition tests.

    derived_from: dimension:boundary_values
    """

    def test_detect_drift_uuid_case_insensitive_comparison(self, tmp_path):
        """File UUID lowercase, DB UUID mixed-case -> in_sync.

        Anticipate: UUID comparison might be case-sensitive, causing false
        divergence on case-only differences. This pins the case-insensitive
        comparison path in detect_drift.

        derived_from: spec:R6 (UUID case-insensitive comparison)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import detect_drift

        # Given an entity in DB (uuid is lowercase by default)
        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        # When the file has the same UUID but in uppercase
        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(entity_uuid.upper(), "feature:001-test"))

        # Then drift detection reports in_sync (case-insensitive UUID match)
        report = detect_drift(db, str(filepath), "feature:001-test")
        assert report.status == "in_sync"
        assert report.mismatches == []

    def test_detect_drift_type_id_case_sensitive_comparison(self, tmp_path):
        """type_id 'Feature:001-test' vs 'feature:001-test' -> diverged.

        Anticipate: type_id comparison might accidentally be case-insensitive
        like UUID, masking actual type_id differences. This pins the
        case-sensitive comparison for entity_type_id field.

        derived_from: spec:R6 (type_id case-sensitive comparison)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import detect_drift

        # Given an entity in DB with lowercase type_id
        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        # When the file header has a differently-cased type_id
        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(entity_uuid, "Feature:001-test"))

        # Then drift detection reports diverged (case-sensitive type_id mismatch)
        report = detect_drift(db, str(filepath), "feature:001-test")
        assert report.status == "diverged"
        type_id_mismatches = [m for m in report.mismatches if m.field == "entity_type_id"]
        assert len(type_id_mismatches) == 1
        assert type_id_mismatches[0].file_value == "Feature:001-test"
        assert type_id_mismatches[0].db_value == "feature:001-test"

    def test_derive_optional_fields_feature_type_id_without_hyphen(self):
        """type_id='feature:003' -> feature_id='003', no feature_slug.

        Anticipate: _parse_feature_type_id might fail or produce wrong
        results when there's no hyphen-separated slug. This catches
        the edge case where partition('-') returns ('003', '', '').

        derived_from: spec:R10 (_parse_feature_type_id edge case)
        """
        from entity_registry.frontmatter_sync import _derive_optional_fields

        # Given an entity with a type_id that has no slug
        entity = {
            "type_id": "feature:003",
            "metadata": None,
            "parent_type_id": None,
        }

        # When we derive optional fields
        result = _derive_optional_fields(entity, "spec")

        # Then feature_id is extracted, feature_slug is absent
        assert result["feature_id"] == "003"
        assert "feature_slug" not in result

    def test_derive_optional_fields_all_artifact_type_phase_mappings(self):
        """All 6 artifact_type -> phase mappings produce correct phase values.

        Anticipate: A new artifact_type might be added to ARTIFACT_BASENAME_MAP
        but not ARTIFACT_PHASE_MAP, or a mapping might have the wrong phase.
        This pins all 6 known mappings.

        derived_from: spec:R10 (artifact_type to phase mapping completeness)
        """
        from entity_registry.frontmatter_sync import _derive_optional_fields

        # Given a minimal entity
        entity = {
            "type_id": "feature:001-test",
            "metadata": None,
            "parent_type_id": None,
        }

        # When/Then each artifact_type maps to its correct phase
        expected_mappings = {
            "spec": "specify",
            "design": "design",
            "plan": "create-plan",
            "tasks": "create-plan",
            "retro": "finish",
            "prd": "brainstorm",
        }
        for artifact_type, expected_phase in expected_mappings.items():
            result = _derive_optional_fields(entity, artifact_type)
            assert result.get("phase") == expected_phase, (
                f"artifact_type={artifact_type!r}: expected phase={expected_phase!r}, "
                f"got {result.get('phase')!r}"
            )

    def test_derive_optional_fields_unknown_artifact_type(self):
        """Unknown artifact_type -> no 'phase' key in result.

        Anticipate: Unknown artifact_type might raise KeyError or return
        a default phase instead of omitting the key. This catches both.

        derived_from: spec:R10 (unknown artifact_type handling)
        """
        from entity_registry.frontmatter_sync import _derive_optional_fields

        # Given a minimal entity
        entity = {
            "type_id": "feature:001-test",
            "metadata": None,
            "parent_type_id": None,
        }

        # When we pass an unknown artifact_type
        result = _derive_optional_fields(entity, "unknown_type")

        # Then no phase key is present
        assert "phase" not in result

    def test_derive_optional_fields_metadata_is_none(self):
        """None metadata -> no crash, falls through to parent_type_id.

        Anticipate: json.loads(None) raises TypeError; the code must handle
        the None metadata case before attempting JSON parse.

        derived_from: spec:R10 (metadata None safety)
        """
        from entity_registry.frontmatter_sync import _derive_optional_fields

        # Given an entity with no metadata and a project parent
        entity = {
            "type_id": "feature:001-test",
            "metadata": None,
            "parent_type_id": "project:P001",
        }

        # When we derive optional fields
        result = _derive_optional_fields(entity, "spec")

        # Then project_id is derived from parent (no crash from None metadata)
        assert result["project_id"] == "P001"

    def test_derive_optional_fields_metadata_has_empty_project_id(self):
        """metadata project_id='' -> falls back to parent_type_id.

        Anticipate: Empty string '' might pass the `or None` check and be
        treated as a valid project_id. This pins that empty string is
        treated as falsy and triggers the fallback.

        derived_from: spec:R10 (empty project_id fallback)
        """
        from entity_registry.frontmatter_sync import _derive_optional_fields

        # Given an entity with empty project_id in metadata but valid parent
        entity = {
            "type_id": "feature:001-test",
            "metadata": '{"project_id": ""}',
            "parent_type_id": "project:FALLBACK-PROJ",
        }

        # When we derive optional fields
        result = _derive_optional_fields(entity, "spec")

        # Then project_id comes from parent (empty string was treated as falsy)
        assert result["project_id"] == "FALLBACK-PROJ"

    def test_backfill_headers_known_artifact_basenames_only(self, tmp_path):
        """Only files in ARTIFACT_BASENAME_MAP are stamped; extra files ignored.

        Anticipate: backfill_headers might stamp all .md files in a feature
        directory, not just the known basenames. This verifies that notes.md
        (not in ARTIFACT_BASENAME_MAP) is untouched.

        derived_from: spec:R20 (only known artifact basenames)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter import read_frontmatter
        from entity_registry.frontmatter_sync import backfill_headers

        # Given a feature with spec.md and an extra notes.md
        db = EntityDatabase(":memory:")
        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")
        feature_dir = tmp_path / "features" / "001-test"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# Spec\n")
        (feature_dir / "notes.md").write_text("# Notes\n")

        # When we backfill headers
        results = backfill_headers(db, str(tmp_path))

        # Then only spec.md gets stamped (notes.md is not a known basename)
        assert len(results) == 1
        assert results[0].action == "created"
        header_notes = read_frontmatter(str(feature_dir / "notes.md"))
        assert header_notes is None

    def test_detect_drift_comparable_fields_only_uuid_and_type_id(self, tmp_path):
        """created_at difference between file and DB does NOT cause divergence.

        Anticipate: COMPARABLE_FIELD_MAP might accidentally include
        created_at or other fields, causing false divergence. This verifies
        that only entity_uuid and entity_type_id are compared.

        derived_from: spec:R6 (only COMPARABLE_FIELD_MAP fields compared)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import detect_drift

        # Given an entity in DB
        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")
        entity = db.get_entity("feature:001-test")

        # When the file has matching UUID and type_id but different created_at
        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(
            entity_uuid, "feature:001-test", "spec", "1999-01-01T00:00:00+00:00"
        ))

        # Then drift detection reports in_sync (created_at not compared)
        report = detect_drift(db, str(filepath), "feature:001-test")
        assert report.status == "in_sync"
        assert report.mismatches == []

    def test_ingest_header_stores_absolute_path(self, tmp_path):
        """Relative filepath -> absolute path stored in DB.

        Anticipate: ingest_header might store the filepath as-is without
        resolving to absolute, causing path comparison issues later.

        derived_from: spec:R17 (artifact_path stored as absolute)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import ingest_header

        # Given an entity in DB
        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        # When we create a file and ingest using a path (tmp_path is already absolute)
        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(entity_uuid, "feature:001-test"))

        result = ingest_header(db, str(filepath))
        assert result.action == "updated"

        # Then DB stores the absolute path
        entity = db.get_entity("feature:001-test")
        stored_path = entity["artifact_path"]
        assert os.path.isabs(stored_path)
        assert stored_path == os.path.abspath(str(filepath))


# ---------------------------------------------------------------------------
# Phase 6: Test Deepening — Adversarial / Negative Testing
# ---------------------------------------------------------------------------


class TestAdversarial:
    """Adversarial and negative tests.

    derived_from: dimension:adversarial
    """

    def test_stamp_header_with_non_feature_entity_type(self, tmp_path):
        """Stamping a project entity produces no feature_id/feature_slug.

        Anticipate: _derive_optional_fields might unconditionally call
        _parse_feature_type_id on non-feature entities, producing garbage
        feature_id values.

        derived_from: spec:R10 (non-feature entity stamp)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter import read_frontmatter
        from entity_registry.frontmatter_sync import stamp_header

        # Given a project entity in DB
        db = EntityDatabase(":memory:")
        db.register_entity("project", "P001", "My Project", project_id="__unknown__")

        filepath = tmp_path / "spec.md"
        _write_file(filepath, "# Spec\n")

        # When we stamp with the project entity
        result = stamp_header(db, str(filepath), "project:P001", "spec")
        assert result.action == "created"

        # Then the header has no feature_id or feature_slug
        header = read_frontmatter(str(filepath))
        assert header is not None
        assert header.get("feature_id") is None
        assert header.get("feature_slug") is None

    def test_ingest_header_does_not_overwrite_immutable_db_fields(self, tmp_path):
        """ingest_header only updates artifact_path, not name/status/etc.

        Anticipate: ingest_header might accidentally pass extra fields from
        the frontmatter to db.update_entity, modifying immutable entity
        fields like name or entity_type.

        derived_from: spec:R17 (only artifact_path written to DB)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import ingest_header

        # Given an entity with a known name and status
        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity(
            "feature", "001-test", "Original Name", status="active",
            project_id="__unknown__",
        )

        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(entity_uuid, "feature:001-test"))

        # When we ingest the header
        result = ingest_header(db, str(filepath))
        assert result.action == "updated"

        # Then only artifact_path changed; name and status are preserved
        entity = db.get_entity("feature:001-test")
        assert entity["name"] == "Original Name"
        assert entity["status"] == "active"
        assert entity["artifact_path"] == os.path.abspath(str(filepath))

    def test_backfill_headers_only_processes_feature_entities(self, tmp_path):
        """Project entities in DB are NOT processed by backfill_headers.

        Anticipate: backfill_headers might use list_entities() without
        the entity_type filter, processing projects/brainstorms too.

        derived_from: spec:R20 (backfill_headers scans feature entities only)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import backfill_headers

        # Given a project entity and a feature entity
        db = EntityDatabase(":memory:")
        db.register_entity("project", "P001", "My Project", project_id="__unknown__")
        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        feature_dir = tmp_path / "features" / "001-test"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# Spec\n")

        # Also create a project dir structure (if it were accidentally scanned)
        project_dir = tmp_path / "features" / "P001"
        project_dir.mkdir(parents=True)
        (project_dir / "spec.md").write_text("# Project Spec\n")

        # When we backfill
        results = backfill_headers(db, str(tmp_path))

        # Then only feature entity is processed (1 result, not 2)
        created = [r for r in results if r.action == "created"]
        assert len(created) == 1

    def test_detect_drift_with_type_id_pointing_to_different_entity_than_file_uuid(
        self, tmp_path
    ):
        """File UUID belongs to entity A, type_id arg belongs to entity B -> diverged.

        Anticipate: detect_drift might look up by type_id only, ignoring
        the file's UUID entirely, masking cross-entity contamination.

        derived_from: spec:R6 (cross-entity divergence detection)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import detect_drift

        # Given two distinct entities in DB
        db = EntityDatabase(":memory:")
        uuid_a = db.register_entity("feature", "001-entity-a", "Entity A", project_id="__unknown__")
        uuid_b = db.register_entity("feature", "002-entity-b", "Entity B", project_id="__unknown__")

        # When file has UUID of entity A but we pass type_id of entity B
        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(uuid_a, "feature:001-entity-a"))

        report = detect_drift(db, str(filepath), "feature:002-entity-b")

        # Then report shows diverged (UUID mismatch between file and DB)
        assert report.status == "diverged"
        uuid_mismatches = [m for m in report.mismatches if m.field == "entity_uuid"]
        assert len(uuid_mismatches) == 1
        assert uuid_mismatches[0].file_value == uuid_a
        assert uuid_mismatches[0].db_value == uuid_b


# ---------------------------------------------------------------------------
# Phase 6: Test Deepening — Error Propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    """Error propagation and failure mode tests.

    derived_from: dimension:error_propagation
    """

    def test_stamp_header_catches_value_error_from_build_header_bad_uuid(self, tmp_path):
        """build_header with empty UUID triggers catch -> action='error'.

        Anticipate: The exception path for build_header failures might be
        unreachable if entity always has a valid UUID. We mock to force the
        path.

        derived_from: design:error-contract (stamp_header never raises)
        """
        from entity_registry.frontmatter_sync import stamp_header

        # Given a mock DB that returns an entity with invalid data
        db = MagicMock()
        db.get_entity.return_value = {
            "uuid": "",  # empty UUID triggers build_header ValueError
            "type_id": "feature:001-test",
            "created_at": "2025-01-01T00:00:00+00:00",
            "metadata": None,
            "parent_type_id": None,
        }

        filepath = tmp_path / "spec.md"
        _write_file(filepath, "# Spec\n")

        # When we attempt to stamp
        result = stamp_header(db, str(filepath), "feature:001-test", "spec")

        # Then error is returned, not raised
        assert result.action == "error"
        assert result.message  # non-empty error message

    def test_backfill_headers_continues_after_individual_stamp_error(self, tmp_path):
        """One file's stamp error doesn't prevent other files from being stamped.

        Anticipate: backfill_headers might short-circuit on the first error
        instead of collecting results for all files. This verifies partial
        failure resilience.

        derived_from: spec:R20 (partial failure resilience)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import backfill_headers

        # Given two features, one with a conflicting UUID and one clean
        db = EntityDatabase(":memory:")
        db.register_entity("feature", "001-clean", "Clean Feature", project_id="__unknown__")
        db.register_entity("feature", "002-conflict", "Conflict Feature", project_id="__unknown__")

        # Create directories
        dir1 = tmp_path / "features" / "001-clean"
        dir1.mkdir(parents=True)
        (dir1 / "spec.md").write_text("# Spec\n")

        dir2 = tmp_path / "features" / "002-conflict"
        dir2.mkdir(parents=True)
        # Pre-stamp with a different UUID to cause mismatch error
        different_uuid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        (dir2 / "spec.md").write_text(
            _make_frontmatter(different_uuid, "feature:002-conflict") + "# Spec\n"
        )

        # When we backfill
        results = backfill_headers(db, str(tmp_path))

        # Then both files are attempted (not short-circuited)
        assert len(results) >= 2

        # One should succeed, one should error
        actions = {r.action for r in results}
        assert "created" in actions
        assert "error" in actions

    def test_cli_fatal_error_exits_with_code_1(self, tmp_path):
        """Fatal DB open error -> exit code 1 with JSON error on stdout.

        Anticipate: _run_handler might not catch DB construction errors,
        causing an unhandled traceback instead of clean JSON output.

        derived_from: spec:R30 (CLI exit codes)
        """
        # Given a DB path inside a non-existent directory
        bad_db_path = str(tmp_path / "nonexistent" / "subdir" / "bad.db")

        filepath = tmp_path / "spec.md"
        filepath.write_text("# Spec\n")

        PYTHON = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", ".venv", "bin", "python"
        )
        LIB_DIR = os.path.join(os.path.dirname(__file__), "..")

        env = {**os.environ, "PYTHONPATH": LIB_DIR, "ENTITY_DB_PATH": bad_db_path}
        result = subprocess.run(
            [sys.executable, "-m", "entity_registry.frontmatter_sync_cli",
             "stamp", str(filepath), "feature:001-test", "spec"],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

        # Then exit code is 1 and stdout contains valid JSON with "error" key
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert "error" in data

    def test_ingest_header_general_exception_returns_error(self, tmp_path):
        """Unexpected exception in ingest_header -> action='error'.

        Anticipate: The outer except clause might not catch all exception
        types, letting unexpected errors propagate.

        derived_from: design:error-contract (ingest_header never raises)
        """
        from entity_registry.frontmatter_sync import ingest_header

        # Given a mock DB where get_entity raises an unexpected error type
        db = MagicMock()
        db.get_entity.side_effect = OSError("Disk failure")

        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(
            "12345678-1234-4123-8123-123456789abc", "feature:001-test"
        ))

        # When we ingest
        result = ingest_header(db, str(filepath))

        # Then error is returned, not raised
        assert result.action == "error"
        assert "Disk failure" in result.message or "Ingest failed" in result.message


# ---------------------------------------------------------------------------
# Phase 6: Test Deepening — Mutation Mindset
# ---------------------------------------------------------------------------


class TestMutationMindset:
    """Mutation-mindset behavioral pinning tests.

    derived_from: dimension:mutation_mindset
    """

    def test_detect_drift_distinguishes_in_sync_from_diverged(self, tmp_path):
        """Pin: in_sync requires ALL comparable fields match, not just one.

        Mutation: if comparison logic uses OR instead of AND (checks only
        first field), both UUID match + type_id mismatch would still report
        in_sync. This test has matching UUID but mismatched type_id.

        derived_from: dimension:mutation (logic inversion && <-> ||)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import detect_drift

        # Given an entity in DB
        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        # When file has correct UUID but wrong type_id
        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(entity_uuid, "feature:WRONG-type"))

        # Then status is diverged (not in_sync)
        report = detect_drift(db, str(filepath), "feature:001-test")
        assert report.status == "diverged"
        assert len(report.mismatches) == 1
        assert report.mismatches[0].field == "entity_type_id"

    def test_stamp_header_created_vs_updated_action(self, tmp_path):
        """Pin: 'created' when no existing UUID, 'updated' when UUID matches.

        Mutation: swapping the condition (existing is None -> 'updated')
        would break the created/updated distinction. We verify both paths.

        derived_from: dimension:mutation (boundary shift on existing check)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import stamp_header

        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        # Path 1: No existing header -> 'created'
        filepath_new = tmp_path / "new_spec.md"
        _write_file(filepath_new, "# Spec\n")
        result_new = stamp_header(db, str(filepath_new), "feature:001-test", "spec")
        assert result_new.action == "created"

        # Path 2: Existing matching header -> 'updated'
        filepath_existing = tmp_path / "existing_spec.md"
        _write_file(filepath_existing, _make_frontmatter(entity_uuid, "feature:001-test"))
        result_existing = stamp_header(
            db, str(filepath_existing), "feature:001-test", "spec"
        )
        assert result_existing.action == "updated"

    def test_stamp_header_uuid_mismatch_check_is_not_skippable(self, tmp_path):
        """Pin: UUID mismatch guard blocks stamping even when type_id matches.

        Mutation: deleting the UUID mismatch guard would allow overwriting
        a file that already belongs to a different entity. This verifies
        the guard is active.

        derived_from: dimension:mutation (line deletion)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter import read_frontmatter
        from entity_registry.frontmatter_sync import stamp_header

        # Given two entities
        db = EntityDatabase(":memory:")
        uuid_a = db.register_entity("feature", "001-entity-a", "Entity A", project_id="__unknown__")
        uuid_b = db.register_entity("feature", "002-entity-b", "Entity B", project_id="__unknown__")

        # When file is stamped with entity A's UUID
        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(uuid_a, "feature:001-entity-a"))

        # And we try to stamp entity B onto the same file
        result = stamp_header(db, str(filepath), "feature:002-entity-b", "spec")

        # Then it's an error (guard prevents overwrite)
        assert result.action == "error"
        assert "mismatch" in result.message.lower()

        # And the original UUID is preserved
        header = read_frontmatter(str(filepath))
        assert header["entity_uuid"] == uuid_a

    def test_ingest_header_actually_calls_update_entity(self, tmp_path):
        """Pin: ingest_header calls db.update_entity with the entity UUID.

        Mutation: replacing db.update_entity with a no-op (line deletion)
        would make ingest silently succeed without updating the DB. This
        verifies the DB is actually modified.

        derived_from: dimension:mutation (line deletion)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import ingest_header

        # Given an entity with no artifact_path
        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")
        entity_before = db.get_entity("feature:001-test")
        assert entity_before["artifact_path"] is None

        # When we ingest a file with that entity's UUID
        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(entity_uuid, "feature:001-test"))
        result = ingest_header(db, str(filepath))
        assert result.action == "updated"

        # Then DB is actually updated (not just reported as updated)
        entity_after = db.get_entity("feature:001-test")
        assert entity_after["artifact_path"] is not None
        assert entity_after["artifact_path"] == os.path.abspath(str(filepath))

    def test_detect_drift_entity_uuid_compared_not_just_type_checked(self, tmp_path):
        """Pin: entity_uuid is compared by VALUE, not just presence check.

        Mutation: replacing `file_val.lower() != db_val.lower()` with
        `file_val is None` would make the test pass as long as both have
        *some* UUID. This verifies distinct UUIDs produce a mismatch.

        derived_from: dimension:mutation (return value mutation)
        """
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter_sync import detect_drift

        # Given an entity in DB
        db = EntityDatabase(":memory:")
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")

        # When file has a different (but valid) UUID
        different_uuid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(different_uuid, "feature:001-test"))

        # Then diverged with specific UUID mismatch
        report = detect_drift(db, str(filepath), "feature:001-test")
        assert report.status == "diverged"
        uuid_mismatches = [m for m in report.mismatches if m.field == "entity_uuid"]
        assert len(uuid_mismatches) == 1
        assert uuid_mismatches[0].file_value == different_uuid
        assert uuid_mismatches[0].db_value == entity_uuid

    def test_project_id_metadata_priority_over_parent_type_id(self):
        """Pin: metadata project_id takes priority over parent_type_id.

        Mutation: swapping the order of checks (parent first, metadata
        second) would produce the wrong project_id when both are present.
        This pins the priority order.

        derived_from: dimension:mutation (arithmetic swap on priority)
        """
        from entity_registry.frontmatter_sync import _derive_optional_fields

        # Given an entity with BOTH metadata project_id and parent project
        entity = {
            "type_id": "feature:001-test",
            "metadata": '{"project_id": "METADATA-WINS"}',
            "parent_type_id": "project:PARENT-LOSES",
        }

        # When we derive optional fields
        result = _derive_optional_fields(entity, "spec")

        # Then metadata project_id wins (not parent)
        assert result["project_id"] == "METADATA-WINS"

    def test_backfill_header_aware_ordering_before_guard(self, tmp_path):
        """Pin: header stamping runs BEFORE the backfill_complete guard.

        Mutation: moving the header_aware block AFTER the guard would
        prevent stamping on already-backfilled databases. This verifies
        the ordering.

        derived_from: dimension:mutation (line deletion / reorder)
        """
        from entity_registry.backfill import run_backfill
        from entity_registry.database import EntityDatabase
        from entity_registry.frontmatter import read_frontmatter

        # Given an already-backfilled DB with a registered feature
        db = EntityDatabase(":memory:")
        db.register_entity("feature", "001-test", "Test Feature", project_id="__unknown__")
        db.set_metadata("backfill_complete", "1")

        feature_dir = tmp_path / "features" / "001-test"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text("# Spec\n")

        # When we run with header_aware=True
        run_backfill(db, str(tmp_path), header_aware=True)

        # Then the header IS stamped (ordering ensures it runs before guard)
        header = read_frontmatter(str(feature_dir / "spec.md"))
        assert header is not None
        assert header.get("entity_uuid") is not None
