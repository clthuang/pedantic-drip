"""Tests for entity_registry.frontmatter_sync module."""
from __future__ import annotations

import os
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
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature")
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
        db.register_entity("feature", "001-test", "Test Feature")

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
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature")

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
        db.register_entity("feature", "001-test", "Test Feature")

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
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature")
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
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature")

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
        db.register_entity("feature", "001-test", "Test Feature")

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
        db.register_entity("feature", "001-test", "Test Feature")

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
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature")

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
        db.register_entity("feature", "001-test", "Test Feature")

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
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature")

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
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature")

        filepath = tmp_path / "spec.md"
        _write_file(filepath, _make_frontmatter(entity_uuid, "feature:001-test"))

        # Mock update_entity to simulate a race condition (entity deleted between read and write)
        original_update = db.update_entity
        db.update_entity = MagicMock(side_effect=ValueError("Entity not found"))

        result = ingest_header(db, str(filepath))
        assert result.action == "error"
        assert "disappeared" in result.message.lower() or "entity" in result.message.lower()
