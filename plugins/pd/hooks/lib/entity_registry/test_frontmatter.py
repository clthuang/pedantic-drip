"""Tests for entity_registry.frontmatter module."""
from __future__ import annotations

import logging
import os
import tempfile

import pytest

from entity_registry.frontmatter import (
    ALLOWED_ARTIFACT_TYPES,
    ALLOWED_FIELDS,
    FIELD_ORDER,
    FrontmatterUUIDMismatch,
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    build_header,
    read_frontmatter,
    validate_header,
    write_frontmatter,
)

# Internal symbols — tested directly to verify low-level contracts
from entity_registry.frontmatter import (
    _UUID_V4_RE,
    _parse_block,
    _serialize_header,
)

# Valid UUID v4 for reuse across tests
VALID_UUID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
VALID_TYPE_ID = "feature:002-markdown-entity-file-header-sc"
VALID_ARTIFACT_TYPE = "spec"
VALID_CREATED_AT = "2026-03-01T12:00:00+00:00"


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _write_file(path: str, content: str) -> None:
    """Helper: write text content to a file with UTF-8 encoding."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _write_binary(path: str, data: bytes) -> None:
    """Helper: write binary content to a file."""
    with open(path, "wb") as f:
        f.write(data)


def _full_header(**overrides) -> dict:
    """Helper: return a full valid header dict with optional overrides."""
    header = {
        "entity_uuid": VALID_UUID,
        "entity_type_id": VALID_TYPE_ID,
        "artifact_type": VALID_ARTIFACT_TYPE,
        "created_at": VALID_CREATED_AT,
    }
    header.update(overrides)
    return header


# ---------------------------------------------------------------------------
# Phase 1: Core Infrastructure
# ---------------------------------------------------------------------------


class TestParseBlock:
    """Tests for _parse_block (Task 1.2.1)."""

    def test_empty_lines_returns_empty_dict(self):
        result = _parse_block([])
        assert result == {}

    def test_single_key_value_line(self):
        result = _parse_block(["entity_uuid: abc-123"])
        assert result == {"entity_uuid": "abc-123"}

    def test_colon_in_value(self):
        """Values may contain ': ' sequences (e.g., entity_type_id: feature:002-foo)."""
        result = _parse_block(["entity_type_id: feature:002-foo"])
        assert result == {"entity_type_id": "feature:002-foo"}

    def test_no_separator_ignored(self):
        """Lines without ': ' separator are silently ignored."""
        result = _parse_block(["no-separator-here"])
        assert result == {}

    def test_invalid_key_chars_ignored(self):
        """Keys with uppercase, digits, or hyphens are ignored."""
        result = _parse_block([
            "Invalid: uppercase",
            "key-with-hyphens: bad",
            "key123: digits",
        ])
        assert result == {}

    def test_blank_and_comment_lines_ignored(self):
        result = _parse_block(["", "# comment line", "   "])
        assert result == {}

    def test_multiple_valid_lines(self):
        result = _parse_block([
            "entity_uuid: abc-123",
            "artifact_type: spec",
            "created_at: 2026-01-01",
        ])
        assert result == {
            "entity_uuid": "abc-123",
            "artifact_type": "spec",
            "created_at": "2026-01-01",
        }


class TestSerializeHeader:
    """Tests for _serialize_header (Task 1.3.1)."""

    def test_required_fields_ordered(self):
        """Required fields appear in FIELD_ORDER with --- delimiters."""
        header = {
            "entity_uuid": VALID_UUID,
            "entity_type_id": VALID_TYPE_ID,
            "artifact_type": VALID_ARTIFACT_TYPE,
            "created_at": VALID_CREATED_AT,
        }
        result = _serialize_header(header)
        lines = result.split("\n")
        # First line is ---, last non-empty line before trailing \n is ---
        assert lines[0] == "---"
        assert lines[1].startswith("entity_uuid: ")
        assert lines[2].startswith("entity_type_id: ")
        assert lines[3].startswith("artifact_type: ")
        assert lines[4].startswith("created_at: ")
        assert lines[5] == "---"

    def test_optional_fields_after_required(self):
        """Optional fields follow required, in FIELD_ORDER order."""
        header = {
            "entity_uuid": VALID_UUID,
            "entity_type_id": VALID_TYPE_ID,
            "artifact_type": VALID_ARTIFACT_TYPE,
            "created_at": VALID_CREATED_AT,
            "feature_id": "002",
            "phase": "specify",
        }
        result = _serialize_header(header)
        lines = result.split("\n")
        # feature_id at index 5, phase at index 6 (after 4 required fields)
        assert lines[5].startswith("feature_id: ")
        assert lines[6].startswith("phase: ")

    def test_unknown_field_appended_after_field_order(self):
        """Unknown fields (not in FIELD_ORDER) appear at the end."""
        header = {
            "entity_uuid": VALID_UUID,
            "entity_type_id": VALID_TYPE_ID,
            "artifact_type": VALID_ARTIFACT_TYPE,
            "created_at": VALID_CREATED_AT,
            "custom_field": "custom_value",
        }
        result = _serialize_header(header)
        lines = result.split("\n")
        # custom_field should be after the 4 known fields, before closing ---
        assert "custom_field: custom_value" in lines

    def test_round_trip_non_empty(self):
        """Serialize then parse back equals original dict."""
        header = {
            "entity_uuid": VALID_UUID,
            "entity_type_id": VALID_TYPE_ID,
            "artifact_type": VALID_ARTIFACT_TYPE,
            "created_at": VALID_CREATED_AT,
        }
        serialized = _serialize_header(header)
        # Extract lines between --- delimiters
        content_lines = serialized.split("\n")
        inner_lines = content_lines[1:-2]  # skip first --- and last ---\n
        parsed = _parse_block(inner_lines)
        assert parsed == header

    def test_round_trip_single_field(self):
        """Single-field dict round-trips correctly."""
        header = {"entity_uuid": VALID_UUID}
        serialized = _serialize_header(header)
        content_lines = serialized.split("\n")
        inner_lines = content_lines[1:-2]
        parsed = _parse_block(inner_lines)
        assert parsed == header

    def test_empty_dict_serializes_to_delimiters_only(self):
        """Empty dict {} serializes as '---\\n---\\n', parses back to {}."""
        header = {}
        serialized = _serialize_header(header)
        assert serialized == "---\n---\n"
        content_lines = serialized.split("\n")
        inner_lines = content_lines[1:-2]
        parsed = _parse_block(inner_lines)
        assert parsed == {}


# ---------------------------------------------------------------------------
# Phase 2: Validation & Build Functions
# ---------------------------------------------------------------------------


class TestValidateHeader:
    """Tests for validate_header (Task 2.1.1)."""

    def test_ac5_valid_header_returns_empty_list(self):
        """AC-5: all required fields with valid values returns empty list."""
        errors = validate_header(_full_header())
        assert errors == []

    def test_ac6_missing_required_field(self):
        """AC-6: missing each required field individually returns error with field name."""
        for field in REQUIRED_FIELDS:
            header = _full_header()
            del header[field]
            errors = validate_header(header)
            assert len(errors) >= 1, f"Expected error for missing {field}"
            assert any(field in e for e in errors), (
                f"Error for missing {field} should mention the field name"
            )

    def test_ac7_invalid_uuid_format(self):
        """AC-7: invalid UUID format returns validation error."""
        header = _full_header()
        header["entity_uuid"] = "not-a-uuid"
        errors = validate_header(header)
        assert len(errors) >= 1
        assert any("entity_uuid" in e or "UUID" in e for e in errors)

    def test_valid_uuid_no_error(self):
        """Valid lowercase UUID returns no error."""
        errors = validate_header(_full_header())
        assert errors == []

    def test_uppercase_uuid_accepted(self):
        """Uppercase hex UUID accepted -- lowercased before regex match."""
        header = _full_header()
        header["entity_uuid"] = "A1B2C3D4-E5F6-4A7B-8C9D-0E1F2A3B4C5D"
        errors = validate_header(header)
        assert errors == []

    def test_invalid_artifact_type(self):
        """Invalid artifact_type returns validation error."""
        header = _full_header()
        header["artifact_type"] = "unknown_type"
        errors = validate_header(header)
        assert len(errors) >= 1
        assert any("artifact_type" in e for e in errors)

    def test_each_valid_artifact_type(self):
        """Each valid artifact_type returns no error."""
        for at in ALLOWED_ARTIFACT_TYPES:
            header = _full_header()
            header["artifact_type"] = at
            errors = validate_header(header)
            assert errors == [], f"Unexpected error for artifact_type={at}: {errors}"

    def test_invalid_created_at(self):
        """Invalid created_at (not ISO 8601) returns validation error."""
        header = _full_header()
        header["created_at"] = "not-a-date"
        errors = validate_header(header)
        assert len(errors) >= 1
        assert any("created_at" in e for e in errors)

    def test_valid_created_at_with_timezone(self):
        """Valid created_at with timezone returns no error."""
        header = _full_header()
        header["created_at"] = "2026-03-01T12:00:00+05:30"
        errors = validate_header(header)
        assert errors == []

    def test_unknown_field_returns_error(self):
        """Unknown field present returns validation error."""
        header = _full_header()
        header["bogus_field"] = "some_value"
        errors = validate_header(header)
        assert len(errors) >= 1
        assert any("bogus_field" in e for e in errors)

    def test_multiple_errors_no_short_circuit(self):
        """Multiple errors all returned (no short-circuit)."""
        header = {
            # missing entity_uuid entirely
            "entity_type_id": VALID_TYPE_ID,
            "artifact_type": "invalid_type",  # bad artifact_type
            "created_at": "not-a-date",  # bad date
            "bogus": "x",  # unknown field
        }
        errors = validate_header(header)
        # Should have at least 4 errors: missing uuid, bad artifact_type,
        # bad created_at, unknown field
        assert len(errors) >= 4


class TestBuildHeader:
    """Tests for build_header (Task 2.2.1)."""

    def test_ac10_valid_args_returns_valid_dict(self):
        """AC-10: valid required args returns dict passing validate_header."""
        header = build_header(
            VALID_UUID, VALID_TYPE_ID, VALID_ARTIFACT_TYPE, VALID_CREATED_AT,
        )
        assert header["entity_uuid"] == VALID_UUID
        assert header["entity_type_id"] == VALID_TYPE_ID
        assert header["artifact_type"] == VALID_ARTIFACT_TYPE
        assert header["created_at"] == VALID_CREATED_AT
        assert validate_header(header) == []

    def test_ac11_invalid_artifact_type_raises(self):
        """AC-11: invalid artifact_type raises ValueError."""
        with pytest.raises(ValueError):
            build_header(VALID_UUID, VALID_TYPE_ID, "invalid", VALID_CREATED_AT)

    def test_invalid_uuid_raises(self):
        """Invalid UUID raises ValueError."""
        with pytest.raises(ValueError):
            build_header("not-a-uuid", VALID_TYPE_ID, VALID_ARTIFACT_TYPE, VALID_CREATED_AT)

    def test_invalid_created_at_raises(self):
        """Invalid created_at raises ValueError."""
        with pytest.raises(ValueError):
            build_header(VALID_UUID, VALID_TYPE_ID, VALID_ARTIFACT_TYPE, "bad-date")

    def test_valid_with_optional_kwargs(self):
        """Valid required + valid optional kwargs all present in output."""
        header = build_header(
            VALID_UUID, VALID_TYPE_ID, VALID_ARTIFACT_TYPE, VALID_CREATED_AT,
            feature_id="002",
            feature_slug="markdown-entity-file-header-sc",
            phase="specify",
        )
        assert header["feature_id"] == "002"
        assert header["feature_slug"] == "markdown-entity-file-header-sc"
        assert header["phase"] == "specify"
        assert validate_header(header) == []

    def test_unknown_kwarg_raises(self):
        """Unknown optional kwarg raises ValueError."""
        with pytest.raises(ValueError):
            build_header(
                VALID_UUID, VALID_TYPE_ID, VALID_ARTIFACT_TYPE, VALID_CREATED_AT,
                bogus_field="value",
            )


# ---------------------------------------------------------------------------
# Phase 3: Read Function
# ---------------------------------------------------------------------------


class TestReadFrontmatter:
    """Tests for read_frontmatter (Task 3.1.1)."""

    def test_ac2_valid_frontmatter(self, tmp_path):
        """AC-2: file with valid frontmatter returns dict with all fields."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, (
            "---\n"
            f"entity_uuid: {VALID_UUID}\n"
            f"entity_type_id: {VALID_TYPE_ID}\n"
            f"artifact_type: {VALID_ARTIFACT_TYPE}\n"
            f"created_at: {VALID_CREATED_AT}\n"
            "---\n"
            "# Spec Content\n"
        ))
        result = read_frontmatter(fpath)
        assert result is not None
        assert result["entity_uuid"] == VALID_UUID
        assert result["entity_type_id"] == VALID_TYPE_ID
        assert result["artifact_type"] == VALID_ARTIFACT_TYPE
        assert result["created_at"] == VALID_CREATED_AT

    def test_ac3_legacy_file_no_frontmatter(self, tmp_path):
        """AC-3: legacy file (no --- on line 1) returns None."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, "# Just a markdown file\nNo frontmatter here.\n")
        result = read_frontmatter(fpath)
        assert result is None

    def test_ac4_malformed_no_closing(self, tmp_path, caplog):
        """AC-4: malformed frontmatter (opening --- but no closing ---) returns None + warning."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, (
            "---\n"
            f"entity_uuid: {VALID_UUID}\n"
            "some content without closing delimiter\n"
        ))
        with caplog.at_level(logging.WARNING, logger="entity_registry.frontmatter"):
            result = read_frontmatter(fpath)
        assert result is None
        assert any("malformed" in r.message.lower() for r in caplog.records)

    def test_empty_file(self, tmp_path):
        """Empty file returns None."""
        fpath = str(tmp_path / "empty.md")
        _write_file(fpath, "")
        result = read_frontmatter(fpath)
        assert result is None

    def test_empty_block_returns_empty_dict(self, tmp_path):
        """--- on line 1 and --- on line 2 (empty block) returns {} (empty dict, NOT None)."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, "---\n---\nBody content\n")
        result = read_frontmatter(fpath)
        assert result is not None
        assert result == {}

    def test_values_with_colons(self, tmp_path):
        """Frontmatter with values containing ': ' parses correctly."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, (
            "---\n"
            f"entity_type_id: {VALID_TYPE_ID}\n"
            "---\n"
            "Body\n"
        ))
        result = read_frontmatter(fpath)
        assert result is not None
        assert result["entity_type_id"] == VALID_TYPE_ID

    def test_binary_content_returns_none(self, tmp_path, caplog):
        """Binary content (null bytes in first 8192 bytes) returns None + warning."""
        fpath = str(tmp_path / "binary.md")
        _write_binary(fpath, b"---\n\x00binary data\n---\n")
        with caplog.at_level(logging.WARNING, logger="entity_registry.frontmatter"):
            result = read_frontmatter(fpath)
        assert result is None
        assert any("binary" in r.message.lower() for r in caplog.records)

    def test_file_not_found_returns_none(self, tmp_path, caplog):
        """File does not exist returns None + warning."""
        fpath = str(tmp_path / "nonexistent.md")
        with caplog.at_level(logging.WARNING, logger="entity_registry.frontmatter"):
            result = read_frontmatter(fpath)
        assert result is None
        assert any("not found" in r.message.lower() or "file not found" in r.message.lower()
                    for r in caplog.records)

    def test_body_preserved_only_header_parsed(self, tmp_path):
        """Body content after frontmatter is not included in parsed dict."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, (
            "---\n"
            f"entity_uuid: {VALID_UUID}\n"
            "---\n"
            "body_key: this should not appear\n"
            "# Heading\n"
        ))
        result = read_frontmatter(fpath)
        assert result is not None
        assert "body_key" not in result
        assert result == {"entity_uuid": VALID_UUID}

    def test_large_file_only_header_parsed(self, tmp_path):
        """Large file with frontmatter -- only header portion parsed."""
        fpath = str(tmp_path / "large.md")
        body = "x" * 100_000 + "\n"
        _write_file(fpath, (
            "---\n"
            f"entity_uuid: {VALID_UUID}\n"
            "---\n"
            + body
        ))
        result = read_frontmatter(fpath)
        assert result is not None
        assert result == {"entity_uuid": VALID_UUID}


# ---------------------------------------------------------------------------
# Phase 4: Write Function
# ---------------------------------------------------------------------------


class TestWriteFrontmatter:
    """Tests for write_frontmatter -- core behavior (Task 4.1.1)."""

    def test_ac1_new_file_prepends_header_preserves_body(self, tmp_path):
        """AC-1: new file (no frontmatter) gets header prepended, body preserved."""
        fpath = str(tmp_path / "spec.md")
        body = "# Spec Content\n\nSome body text.\n"
        _write_file(fpath, body)

        header = _full_header()
        write_frontmatter(fpath, header)

        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        assert content.startswith("---\n")
        assert f"entity_uuid: {VALID_UUID}\n" in content
        assert content.endswith(body)

    def test_ac8_existing_frontmatter_replaced_body_preserved(self, tmp_path):
        """AC-8: file with existing frontmatter gets header replaced, body preserved."""
        fpath = str(tmp_path / "spec.md")
        body = "# Body\n"
        _write_file(fpath, (
            "---\n"
            f"entity_uuid: {VALID_UUID}\n"
            f"entity_type_id: {VALID_TYPE_ID}\n"
            f"artifact_type: {VALID_ARTIFACT_TYPE}\n"
            f"created_at: {VALID_CREATED_AT}\n"
            "---\n"
            + body
        ))

        new_header = _full_header(phase="specify")
        write_frontmatter(fpath, new_header)

        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        assert "phase: specify" in content
        assert content.endswith(body)

    def test_ac15_idempotent(self, tmp_path):
        """AC-15: write twice with same header produces identical content."""
        fpath = str(tmp_path / "spec.md")
        body = "# Body\n"
        _write_file(fpath, body)

        header = _full_header()
        write_frontmatter(fpath, header)
        with open(fpath, "r", encoding="utf-8") as f:
            content_after_first = f.read()

        write_frontmatter(fpath, header)
        with open(fpath, "r", encoding="utf-8") as f:
            content_after_second = f.read()

        assert content_after_first == content_after_second

    def test_ac16_uuid_mismatch_raises(self, tmp_path):
        """AC-16: UUID mismatch raises FrontmatterUUIDMismatch (a ValueError subclass)."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, (
            "---\n"
            f"entity_uuid: {VALID_UUID}\n"
            f"entity_type_id: {VALID_TYPE_ID}\n"
            f"artifact_type: {VALID_ARTIFACT_TYPE}\n"
            f"created_at: {VALID_CREATED_AT}\n"
            "---\n"
            "# Body\n"
        ))

        different_uuid = "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e"
        with pytest.raises(FrontmatterUUIDMismatch):
            write_frontmatter(fpath, _full_header(entity_uuid=different_uuid))

    def test_ac16_uuid_case_mismatch_does_not_raise(self, tmp_path):
        """AC-16 variant: UUID case mismatch (same UUID different case) does NOT raise."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, (
            "---\n"
            f"entity_uuid: {VALID_UUID}\n"
            f"entity_type_id: {VALID_TYPE_ID}\n"
            f"artifact_type: {VALID_ARTIFACT_TYPE}\n"
            f"created_at: {VALID_CREATED_AT}\n"
            "---\n"
            "# Body\n"
        ))

        upper_uuid = VALID_UUID.upper()
        # Should not raise -- same UUID, different case
        write_frontmatter(fpath, _full_header(entity_uuid=upper_uuid))

    def test_ac17_none_removes_optional_field(self, tmp_path):
        """AC-17: existing optional field + None in new headers removes field."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, (
            "---\n"
            f"entity_uuid: {VALID_UUID}\n"
            f"entity_type_id: {VALID_TYPE_ID}\n"
            f"artifact_type: {VALID_ARTIFACT_TYPE}\n"
            f"created_at: {VALID_CREATED_AT}\n"
            "feature_id: 002\n"
            "---\n"
            "# Body\n"
        ))

        write_frontmatter(fpath, _full_header(feature_id=None))

        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        assert "feature_id" not in content

    def test_ac18_empty_string_removes_optional_field(self, tmp_path):
        """AC-18: existing optional field + '' in new headers removes field."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, (
            "---\n"
            f"entity_uuid: {VALID_UUID}\n"
            f"entity_type_id: {VALID_TYPE_ID}\n"
            f"artifact_type: {VALID_ARTIFACT_TYPE}\n"
            f"created_at: {VALID_CREATED_AT}\n"
            "phase: specify\n"
            "---\n"
            "# Body\n"
        ))

        write_frontmatter(fpath, _full_header(phase=""))

        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        assert "phase" not in content

    def test_td9_created_at_preserved(self, tmp_path):
        """TD-9: existing created_at preserved when new headers differ."""
        fpath = str(tmp_path / "spec.md")
        original_ts = "2026-01-01T00:00:00+00:00"
        _write_file(fpath, (
            "---\n"
            f"entity_uuid: {VALID_UUID}\n"
            f"entity_type_id: {VALID_TYPE_ID}\n"
            f"artifact_type: {VALID_ARTIFACT_TYPE}\n"
            f"created_at: {original_ts}\n"
            "---\n"
            "# Body\n"
        ))

        new_ts = "2026-06-15T12:00:00+00:00"
        write_frontmatter(fpath, _full_header(created_at=new_ts))

        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        assert f"created_at: {original_ts}" in content
        assert new_ts not in content

    def test_file_not_found_raises_valueerror(self, tmp_path):
        """File does not exist raises ValueError."""
        fpath = str(tmp_path / "nonexistent.md")
        with pytest.raises(ValueError, match="File not found"):
            write_frontmatter(fpath, _full_header())

    def test_merge_preserve_existing_optional(self, tmp_path):
        """Merge-preserve: partial write preserves existing optional fields."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, "# Body\n")

        # First write: full header with feature_id
        full = _full_header(feature_id="002")
        write_frontmatter(fpath, full)

        # Second write: partial dict (entity_uuid + artifact_type only)
        # Omits required fields -- relies on merge to preserve from existing
        partial = {"entity_uuid": VALID_UUID, "artifact_type": VALID_ARTIFACT_TYPE}
        write_frontmatter(fpath, partial)

        result = read_frontmatter(fpath)
        assert result is not None
        assert result["feature_id"] == "002"
        # Also verify required fields preserved via merge
        assert result["entity_type_id"] == VALID_TYPE_ID
        assert result["created_at"] == VALID_CREATED_AT

    def test_merge_add_new_optional(self, tmp_path):
        """Merge-add: writing with new optional field adds it."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, "# Body\n")

        # First write: full header without feature_id
        write_frontmatter(fpath, _full_header())

        # Second write: add feature_id
        write_frontmatter(fpath, {
            "entity_uuid": VALID_UUID,
            "artifact_type": VALID_ARTIFACT_TYPE,
            "feature_id": "002",
        })

        result = read_frontmatter(fpath)
        assert result is not None
        assert result["feature_id"] == "002"

    def test_validation_failure_after_merge_raises_file_unchanged(self, tmp_path):
        """Validation failure after merge raises ValueError, file unchanged."""
        fpath = str(tmp_path / "spec.md")
        original_content = (
            "---\n"
            f"entity_uuid: {VALID_UUID}\n"
            f"entity_type_id: {VALID_TYPE_ID}\n"
            f"artifact_type: {VALID_ARTIFACT_TYPE}\n"
            f"created_at: {VALID_CREATED_AT}\n"
            "---\n"
            "# Body\n"
        )
        _write_file(fpath, original_content)

        # Try to merge in an unknown field -- should fail validation
        with pytest.raises(ValueError):
            write_frontmatter(fpath, {
                "entity_uuid": VALID_UUID,
                "bogus_field": "bad_value",
            })

        # File should be unchanged
        with open(fpath, "r", encoding="utf-8") as f:
            assert f.read() == original_content


class TestWriteFrontmatterAtomicAndGuards:
    """Tests for write_frontmatter -- atomic write and guards (Task 4.1.2)."""

    def test_ac9_atomic_write_uses_rename(self, tmp_path, monkeypatch):
        """AC-9: atomic write -- mock os.rename to verify temp file in same dir."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, "# Body\n")

        rename_calls = []
        original_rename = os.rename

        def mock_rename(src, dst):
            rename_calls.append((src, dst))
            original_rename(src, dst)

        monkeypatch.setattr(os, "rename", mock_rename)
        write_frontmatter(fpath, _full_header())

        assert len(rename_calls) == 1
        src, dst = rename_calls[0]
        # Temp file must be in the same directory as target
        assert os.path.dirname(src) == os.path.dirname(dst)
        assert dst == fpath
        assert src.endswith(".tmp")

    def test_temp_file_cleanup_on_error(self, tmp_path, monkeypatch):
        """Temp file is cleaned up if write fails before rename."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, "# Body\n")

        # Force os.rename to raise an error
        def failing_rename(src, dst):
            raise OSError("simulated rename failure")

        monkeypatch.setattr(os, "rename", failing_rename)

        with pytest.raises(OSError):
            write_frontmatter(fpath, _full_header())

        # No leftover .tmp files in the directory
        tmp_files = [f for f in os.listdir(str(tmp_path)) if f.endswith(".tmp")]
        assert tmp_files == [], f"Leftover temp files: {tmp_files}"

    def test_binary_content_guard(self, tmp_path):
        """Binary content (null bytes) raises ValueError, file unchanged."""
        fpath = str(tmp_path / "binary.md")
        binary_content = b"---\n\x00binary data\n---\n# Body\n"
        _write_binary(fpath, binary_content)

        with pytest.raises(ValueError, match="[Bb]inary"):
            write_frontmatter(fpath, _full_header())

        # File unchanged
        with open(fpath, "rb") as f:
            assert f.read() == binary_content

    def test_divergence_guard_read_consistent(self, tmp_path):
        """Divergence guard: read_frontmatter returns same header as write's internal read."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, "# Body\n")

        header = _full_header(feature_id="002", phase="specify")
        write_frontmatter(fpath, header)

        # read_frontmatter should return exactly what write stored
        result = read_frontmatter(fpath)
        assert result == header

    def test_body_starting_with_triple_dash(self, tmp_path):
        """Body starting with --- (markdown horizontal rule) -- read logic stops at correct delimiter."""
        fpath = str(tmp_path / "spec.md")
        body = "---\n\nThis is after a horizontal rule.\n"
        _write_file(fpath, (
            "---\n"
            f"entity_uuid: {VALID_UUID}\n"
            f"entity_type_id: {VALID_TYPE_ID}\n"
            f"artifact_type: {VALID_ARTIFACT_TYPE}\n"
            f"created_at: {VALID_CREATED_AT}\n"
            "---\n"
            + body
        ))

        # Write with updated header
        write_frontmatter(fpath, _full_header(phase="specify"))

        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        assert "phase: specify" in content
        # Body with --- should be preserved intact
        assert content.endswith(body)

    def test_structural_independence_from_read_frontmatter(self, tmp_path, monkeypatch):
        """Structural independence: write_frontmatter does NOT call read_frontmatter internally."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, "# Body\n")

        # Patch read_frontmatter at the module level to raise AssertionError
        import entity_registry.frontmatter as fm_module

        def bomb_read(filepath):
            raise AssertionError("read_frontmatter should not be called by write_frontmatter")

        monkeypatch.setattr(fm_module, "read_frontmatter", bomb_read)

        # Should NOT raise AssertionError -- write_frontmatter uses its own read logic
        write_frontmatter(fpath, _full_header())


class TestRoundTrip:
    """Round-trip tests: write then read returns equal dict (Task 4.2.1)."""

    def test_ac14_round_trip_basic(self, tmp_path):
        """AC-14: read_frontmatter(path) after write_frontmatter(path, h) returns dict equal to h."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, "# Body\n")

        header = _full_header(feature_id="002", phase="specify")
        write_frontmatter(fpath, header)

        result = read_frontmatter(fpath)
        assert result == header

    def test_round_trip_required_fields_only(self, tmp_path):
        """Round-trip with all required fields only."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, "# Body\n")

        header = _full_header()
        write_frontmatter(fpath, header)

        result = read_frontmatter(fpath)
        assert result == header

    def test_round_trip_all_optional_fields(self, tmp_path):
        """Round-trip with required + all optional fields."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, "# Body\n")

        header = _full_header(
            feature_id="002",
            feature_slug="markdown-entity-file-header-sc",
            project_id="P001",
            phase="specify",
            updated_at="2026-03-02T10:00:00+00:00",
        )
        write_frontmatter(fpath, header)

        result = read_frontmatter(fpath)
        assert result == header

    def test_round_trip_values_with_colons(self, tmp_path):
        """Round-trip with values containing ': ' characters."""
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, "# Body\n")

        header = _full_header(
            entity_type_id="feature:002-markdown-entity-file-header-sc",
        )
        # entity_type_id already contains ':' -- verify round-trip fidelity
        write_frontmatter(fpath, header)

        result = read_frontmatter(fpath)
        assert result == header
        assert result["entity_type_id"] == "feature:002-markdown-entity-file-header-sc"


# ---------------------------------------------------------------------------
# Phase 5: CLI Script Helpers
# ---------------------------------------------------------------------------

from entity_registry.frontmatter_inject import (
    ARTIFACT_BASENAME_MAP,
    ARTIFACT_PHASE_MAP,
    _extract_project_id,
    _parse_feature_type_id,
)


class TestCLIHelpers:
    """Tests for frontmatter_inject helper functions and constants (Task 5.2.1)."""

    def test_artifact_basename_map_contains_all_basenames(self):
        """ARTIFACT_BASENAME_MAP contains all 6 supported basenames."""
        expected = {"spec.md", "design.md", "plan.md", "tasks.md", "retro.md", "prd.md"}
        assert set(ARTIFACT_BASENAME_MAP.keys()) == expected

    def test_artifact_phase_map_contains_all_types(self):
        """ARTIFACT_PHASE_MAP contains all 6 artifact types."""
        expected = {"spec", "design", "plan", "tasks", "retro", "prd"}
        assert set(ARTIFACT_PHASE_MAP.keys()) == expected

    def test_parse_feature_type_id_with_slug(self):
        """_parse_feature_type_id('feature:002-some-slug') returns ('002', 'some-slug')."""
        result = _parse_feature_type_id("feature:002-some-slug")
        assert result == ("002", "some-slug")

    def test_parse_feature_type_id_no_separator(self):
        """_parse_feature_type_id('feature:noseparator') returns ('noseparator', None)."""
        result = _parse_feature_type_id("feature:noseparator")
        assert result == ("noseparator", None)

    def test_parse_feature_type_id_empty_entity(self):
        """_parse_feature_type_id('feature:') returns ('', None)."""
        result = _parse_feature_type_id("feature:")
        assert result == ("", None)

    def test_extract_project_id_from_project(self):
        """_extract_project_id('project:P001') returns 'P001'."""
        result = _extract_project_id("project:P001")
        assert result == "P001"

    def test_extract_project_id_non_project(self):
        """_extract_project_id('brainstorm:abc') returns None."""
        result = _extract_project_id("brainstorm:abc")
        assert result is None

    def test_extract_project_id_none(self):
        """_extract_project_id(None) returns None."""
        result = _extract_project_id(None)
        assert result is None


# DB teardown: EntityDatabase.close() confirmed available (database.py:265)


# ---------------------------------------------------------------------------
# Phase 7: Integration Tests
# ---------------------------------------------------------------------------

import subprocess
import sys
from pathlib import Path

from entity_registry.database import EntityDatabase


class TestFrontmatterInjectCLI:
    """Integration tests for frontmatter_inject.py CLI (Tasks 7.1-7.4)."""

    # Path to the CLI script
    SCRIPT_PATH = str(
        Path(__file__).parent / "frontmatter_inject.py"
    )

    # PYTHONPATH must resolve to hooks/lib/ so entity_registry is importable
    PYTHONPATH = str(Path(__file__).parent.parent)

    def _run_cli(self, artifact_path, type_id, db_path, extra_env=None):
        """Helper: invoke frontmatter_inject.py via subprocess."""
        env = {
            "PYTHONPATH": self.PYTHONPATH,
            "ENTITY_DB_PATH": str(db_path),
        }
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, self.SCRIPT_PATH, str(artifact_path), type_id],
            capture_output=True,
            text=True,
            env=env,
        )

    def _setup_db(self, tmp_path):
        """Helper: create a test DB and register a feature entity.

        Returns (db, entity_uuid, db_path).
        """
        db_path = str(tmp_path / "test.db")
        db = EntityDatabase(db_path)
        entity_uuid = db.register_entity(
            entity_type="feature",
            entity_id="002-test-feature",
            name="Test Feature",
        )
        return db, entity_uuid, db_path

    # ------------------------------------------------------------------
    # AC-12: End-to-end header injection
    # ------------------------------------------------------------------

    def test_ac12_end_to_end_header_injection(self, tmp_path):
        """AC-12: CLI injects valid frontmatter into a plain markdown file."""
        db, entity_uuid, db_path = self._setup_db(tmp_path)

        # Create artifact file
        artifact = tmp_path / "spec.md"
        artifact.write_text("# Spec Content\n\nBody text.\n", encoding="utf-8")

        type_id = "feature:002-test-feature"
        result = self._run_cli(str(artifact), type_id, db_path)
        db.close()

        assert result.returncode == 0

        # Read and verify frontmatter
        header = read_frontmatter(str(artifact))
        assert header is not None
        assert header["entity_uuid"] == entity_uuid
        assert header["entity_type_id"] == type_id
        assert header["artifact_type"] == "spec"
        # created_at must be valid ISO 8601
        from datetime import datetime as _dt
        _dt.fromisoformat(header["created_at"])
        # Optional fields should be present
        assert header.get("feature_id") == "002"
        assert header.get("feature_slug") == "test-feature"
        assert header.get("phase") == "specify"

    # ------------------------------------------------------------------
    # AC-13: Graceful degradation with unavailable DB
    # ------------------------------------------------------------------

    def test_ac13_nonexistent_db_path(self, tmp_path):
        """AC-13: nonexistent DB directory causes exit 0 with warning, file unchanged."""
        artifact = tmp_path / "spec.md"
        original_content = "# Spec Content\n"
        artifact.write_text(original_content, encoding="utf-8")

        # Use a path where the parent directory does not exist
        bad_db_path = str(tmp_path / "nonexistent_dir" / "test.db")

        result = self._run_cli(
            str(artifact), "feature:002-test", bad_db_path,
        )

        assert result.returncode == 0
        assert "WARNING" in result.stderr
        # File unchanged
        assert artifact.read_text(encoding="utf-8") == original_content

    # ------------------------------------------------------------------
    # Edge cases (Task 7.4.1)
    # ------------------------------------------------------------------

    def test_unsupported_basename_exit_0_no_header(self, tmp_path):
        """Unsupported basename (notes.md) exits 0, no header injected."""
        db, _, db_path = self._setup_db(tmp_path)

        artifact = tmp_path / "notes.md"
        original_content = "# Notes\n"
        artifact.write_text(original_content, encoding="utf-8")

        result = self._run_cli(
            str(artifact), "feature:002-test-feature", db_path,
        )
        db.close()

        assert result.returncode == 0
        assert artifact.read_text(encoding="utf-8") == original_content

    def test_entity_not_found_exit_0_no_header(self, tmp_path):
        """Entity not found in DB exits 0, no header injected."""
        db, _, db_path = self._setup_db(tmp_path)

        artifact = tmp_path / "spec.md"
        original_content = "# Spec\n"
        artifact.write_text(original_content, encoding="utf-8")

        # Use a type_id not in the DB
        result = self._run_cli(
            str(artifact), "feature:999-nonexistent", db_path,
        )
        db.close()

        assert result.returncode == 0
        assert "WARNING" in result.stderr
        assert artifact.read_text(encoding="utf-8") == original_content

    def test_idempotent_cli_twice(self, tmp_path):
        """Running CLI twice produces identical file content (idempotent)."""
        db, _, db_path = self._setup_db(tmp_path)

        artifact = tmp_path / "spec.md"
        artifact.write_text("# Spec\n", encoding="utf-8")

        type_id = "feature:002-test-feature"

        # First run
        result1 = self._run_cli(str(artifact), type_id, db_path)
        assert result1.returncode == 0
        content_after_first = artifact.read_text(encoding="utf-8")

        # Second run
        result2 = self._run_cli(str(artifact), type_id, db_path)
        assert result2.returncode == 0
        content_after_second = artifact.read_text(encoding="utf-8")

        db.close()

        assert content_after_first == content_after_second

    def test_uuid_mismatch_exit_1(self, tmp_path):
        """File with different UUID in frontmatter causes exit 1."""
        db, _, db_path = self._setup_db(tmp_path)

        artifact = tmp_path / "spec.md"
        # Write frontmatter with a different UUID
        different_uuid = "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e"
        artifact.write_text(
            "---\n"
            f"entity_uuid: {different_uuid}\n"
            f"entity_type_id: feature:002-test-feature\n"
            f"artifact_type: spec\n"
            f"created_at: 2026-01-01T00:00:00+00:00\n"
            "---\n"
            "# Spec\n",
            encoding="utf-8",
        )

        result = self._run_cli(
            str(artifact), "feature:002-test-feature", db_path,
        )
        db.close()

        assert result.returncode == 1


# ---------------------------------------------------------------------------
# Phase B: Test Deepening — Boundary Value, Adversarial, Error Propagation,
# Mutation Mindset
# ---------------------------------------------------------------------------


class TestValidateHeaderUUIDBoundary:
    """BVA tests for UUID v4 validation boundaries (dimension: boundary_values)."""

    def test_validate_header_uuid_v4_minimum_valid(self):
        """Minimum valid UUID v4: all-zeros with version=4, variant=8.
        derived_from: spec:R11 (UUID v4 regex), dimension:boundary_values
        """
        # Given a header with the lowest possible valid UUID v4
        # 00000000-0000-4000-8000-000000000000
        # version digit = 4, variant digit = 8
        header = _full_header(entity_uuid="00000000-0000-4000-8000-000000000000")
        # When validated
        errors = validate_header(header)
        # Then no errors — this is a valid UUID v4
        assert errors == [], f"Minimum valid UUID v4 should pass, got: {errors}"

    def test_validate_header_uuid_v4_maximum_valid(self):
        """Maximum valid UUID v4: all-f's with version=4, variant=b.
        derived_from: spec:R11 (UUID v4 regex), dimension:boundary_values
        """
        # Given a header with the highest possible valid UUID v4
        # ffffffff-ffff-4fff-bfff-ffffffffffff
        # version digit = 4, variant digit = b
        header = _full_header(entity_uuid="ffffffff-ffff-4fff-bfff-ffffffffffff")
        # When validated
        errors = validate_header(header)
        # Then no errors — this is a valid UUID v4
        assert errors == [], f"Maximum valid UUID v4 should pass, got: {errors}"

    def test_validate_header_uuid_wrong_version_digit_3(self):
        """UUID with version=3 (not v4) must be rejected.
        derived_from: spec:R11 (UUID v4 regex), dimension:boundary_values
        """
        # Given a UUID that differs only in the version digit (3 instead of 4)
        header = _full_header(entity_uuid="a1b2c3d4-e5f6-3a7b-8c9d-0e1f2a3b4c5d")
        # When validated
        errors = validate_header(header)
        # Then it must be rejected — version digit must be exactly 4
        assert len(errors) >= 1
        assert any("entity_uuid" in e or "UUID" in e for e in errors), (
            f"Expected UUID rejection for version=3, got: {errors}"
        )

    def test_validate_header_uuid_wrong_variant_digit_7(self):
        """UUID with variant=7 (outside [89ab]) must be rejected.
        derived_from: spec:R11 (UUID v4 regex), dimension:boundary_values
        """
        # Given a UUID with variant digit 7 (valid range is [89ab])
        header = _full_header(entity_uuid="a1b2c3d4-e5f6-4a7b-7c9d-0e1f2a3b4c5d")
        # When validated
        errors = validate_header(header)
        # Then it must be rejected — variant digit must be 8, 9, a, or b
        assert len(errors) >= 1
        assert any("entity_uuid" in e or "UUID" in e for e in errors), (
            f"Expected UUID rejection for variant=7, got: {errors}"
        )

    def test_validate_header_uuid_version_digit_exactly_4_not_5(self):
        """UUID with version=5 must be rejected — only version=4 is allowed.
        derived_from: spec:R11 (UUID v4 only), dimension:mutation_mindset
        Mutation: would swapping '4' check to '>= 4' pass version 5? This catches it.
        """
        # Given a UUID with version digit 5
        header = _full_header(entity_uuid="a1b2c3d4-e5f6-5a7b-8c9d-0e1f2a3b4c5d")
        # When validated
        errors = validate_header(header)
        # Then rejected — only version 4 is valid
        assert len(errors) >= 1
        assert any("entity_uuid" in e or "UUID" in e for e in errors), (
            f"Expected UUID rejection for version=5, got: {errors}"
        )

    def test_validate_header_uuid_variant_boundary_8_accepted(self):
        """UUID with variant digit=8 (lower boundary of valid range) accepted.
        derived_from: spec:R11 (variant [89ab]), dimension:boundary_values
        """
        # Given variant digit exactly at lower boundary (8)
        header = _full_header(entity_uuid="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d")
        # When validated
        errors = validate_header(header)
        # Then accepted
        assert errors == []

    def test_validate_header_uuid_variant_boundary_b_accepted(self):
        """UUID with variant digit=b (upper boundary of valid range) accepted.
        derived_from: spec:R11 (variant [89ab]), dimension:boundary_values
        """
        # Given variant digit exactly at upper boundary (b)
        header = _full_header(entity_uuid="a1b2c3d4-e5f6-4a7b-bc9d-0e1f2a3b4c5d")
        # When validated
        errors = validate_header(header)
        # Then accepted
        assert errors == []

    def test_validate_header_uuid_variant_c_rejected(self):
        """UUID with variant digit=c (just above valid range) rejected.
        derived_from: spec:R11 (variant [89ab]), dimension:boundary_values
        Mutation: would changing [89ab] to [89abc] pass this? This catches that.
        """
        # Given variant digit c (one above upper boundary)
        header = _full_header(entity_uuid="a1b2c3d4-e5f6-4a7b-cc9d-0e1f2a3b4c5d")
        # When validated
        errors = validate_header(header)
        # Then rejected
        assert len(errors) >= 1
        assert any("entity_uuid" in e or "UUID" in e for e in errors)


class TestValidateHeaderCreatedAtBoundary:
    """BVA tests for created_at timestamp validation (dimension: boundary_values)."""

    def test_validate_header_created_at_without_timezone(self):
        """created_at without timezone offset (naive ISO) should be accepted.
        Python's datetime.fromisoformat accepts naive timestamps.
        derived_from: spec:R3 (created_at ISO 8601), dimension:boundary_values
        """
        # Given a header with a naive ISO timestamp (no timezone)
        header = _full_header(created_at="2026-03-01T12:00:00")
        # When validated
        errors = validate_header(header)
        # Then accepted — fromisoformat accepts naive timestamps
        assert errors == [], f"Naive ISO timestamp should be accepted, got: {errors}"

    def test_validate_header_created_at_date_only(self):
        """created_at with date-only string should be accepted by fromisoformat.
        derived_from: spec:R3 (created_at ISO 8601), dimension:boundary_values
        """
        # Given a header with date-only string
        header = _full_header(created_at="2026-03-01")
        # When validated
        errors = validate_header(header)
        # Then accepted — fromisoformat accepts date-only strings
        assert errors == [], f"Date-only ISO string should be accepted, got: {errors}"


class TestCLIBasenameMapping:
    """BVA tests for CLI basename-to-artifact_type mapping (dimension: boundary_values)."""

    def test_cli_artifact_basename_mapping_all_six(self):
        """Each of the 6 supported basenames maps to the correct artifact_type.
        derived_from: spec:TD-6 (basename mapping), dimension:boundary_values
        """
        # Given the expected mapping of basenames to artifact types
        expected = {
            "spec.md": "spec",
            "design.md": "design",
            "plan.md": "plan",
            "tasks.md": "tasks",
            "retro.md": "retro",
            "prd.md": "prd",
        }
        # When we check each basename in ARTIFACT_BASENAME_MAP
        for basename, expected_type in expected.items():
            actual = ARTIFACT_BASENAME_MAP.get(basename)
            # Then the mapping matches exactly
            assert actual == expected_type, (
                f"Basename {basename!r} should map to {expected_type!r}, got {actual!r}"
            )

    def test_cli_artifact_phase_mapping_all_six(self):
        """Each of the 6 artifact types maps to the correct phase.
        derived_from: spec:I5-step7 (phase mapping), dimension:boundary_values
        """
        # Given the expected mapping of artifact types to phases
        expected = {
            "spec": "specify",
            "design": "design",
            "plan": "create-plan",
            "tasks": "create-tasks",
            "retro": "finish",
            "prd": "brainstorm",
        }
        # When we check each artifact type in ARTIFACT_PHASE_MAP
        for artifact_type, expected_phase in expected.items():
            actual = ARTIFACT_PHASE_MAP.get(artifact_type)
            # Then the mapping matches exactly
            assert actual == expected_phase, (
                f"Artifact type {artifact_type!r} should map to phase {expected_phase!r}, "
                f"got {actual!r}"
            )


class TestCLIAdversarial:
    """Adversarial tests for CLI arg handling (dimension: adversarial)."""

    SCRIPT_PATH = str(Path(__file__).parent / "frontmatter_inject.py")
    PYTHONPATH = str(Path(__file__).parent.parent)

    def test_cli_wrong_arg_count_zero_args_exits_with_usage(self):
        """CLI with 0 args (no artifact_path, no type_id) exits 1 with usage message.
        derived_from: spec:CLI-exit-codes (exit 1 for bad arguments), dimension:adversarial
        """
        # Given the CLI invoked with no arguments
        result = subprocess.run(
            [sys.executable, self.SCRIPT_PATH],
            capture_output=True,
            text=True,
            env={"PYTHONPATH": self.PYTHONPATH},
        )
        # Then exit code is 1 and stderr contains usage guidance
        assert result.returncode == 1
        assert "Usage" in result.stderr

    def test_cli_wrong_arg_count_four_args_exits_with_usage(self):
        """CLI with too many args (4 instead of 2) exits 1 with usage message.
        derived_from: spec:CLI-exit-codes (exit 1 for bad arguments), dimension:adversarial
        """
        # Given the CLI invoked with 4 arguments
        result = subprocess.run(
            [sys.executable, self.SCRIPT_PATH, "a", "b", "c", "d"],
            capture_output=True,
            text=True,
            env={"PYTHONPATH": self.PYTHONPATH},
        )
        # Then exit code is 1 and stderr contains usage guidance
        assert result.returncode == 1
        assert "Usage" in result.stderr


class TestReadFrontmatterAdversarial:
    """Adversarial tests for read_frontmatter (dimension: adversarial)."""

    def test_read_frontmatter_leading_whitespace_before_opening_delimiter(self, tmp_path):
        """File with leading whitespace before --- should NOT parse as frontmatter.
        The opening delimiter must be exactly '---' on line 1 with no leading whitespace.
        derived_from: spec:R1 (line 1 must be ---), dimension:adversarial
        """
        # Given a file with a space before the opening ---
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, " ---\nentity_uuid: abc\n---\n# Body\n")
        # When read_frontmatter is called
        result = read_frontmatter(fpath)
        # Then it returns None (no valid frontmatter detected)
        assert result is None

    def test_read_frontmatter_stops_at_first_closing_delimiter(self, tmp_path):
        """read_frontmatter must stop at the FIRST closing --- delimiter.
        If body contains ---, those should NOT be consumed as part of the header.
        derived_from: spec:R1 (first closing ---), dimension:mutation_mindset
        Mutation: would reading past the first --- break this? This catches that.
        """
        # Given a file with frontmatter followed by body containing ---
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, (
            "---\n"
            f"entity_uuid: {VALID_UUID}\n"
            "---\n"
            "---\n"
            "extra_key: should_not_appear\n"
            "---\n"
        ))
        # When read_frontmatter is called
        result = read_frontmatter(fpath)
        # Then only the first block is parsed
        assert result is not None
        assert result == {"entity_uuid": VALID_UUID}
        assert "extra_key" not in result


class TestWriteFrontmatterMutationMindset:
    """Mutation mindset tests for write_frontmatter (dimension: mutation_mindset)."""

    def test_write_frontmatter_none_deletion_vs_missing_key(self, tmp_path):
        """Absent key in new headers preserves existing field; None deletes it.
        This verifies the distinction between 'not providing a key' (merge-preserve)
        and 'providing key=None' (explicit deletion per R9).
        derived_from: spec:AC-17 (None deletion), spec:R8 (merge-preserve), dimension:mutation_mindset
        Mutation: if merge treated absent-key same as None, existing fields would vanish.
        """
        # Given a file with frontmatter containing feature_id and phase
        fpath = str(tmp_path / "spec.md")
        _write_file(fpath, "# Body\n")
        initial_header = _full_header(feature_id="002", phase="specify")
        write_frontmatter(fpath, initial_header)

        # When we write with only entity_uuid (no feature_id key, no phase key)
        partial = {"entity_uuid": VALID_UUID}
        write_frontmatter(fpath, partial)

        # Then feature_id and phase are PRESERVED (absent key != deletion)
        result = read_frontmatter(fpath)
        assert result is not None
        assert result.get("feature_id") == "002", (
            "Absent key should preserve existing field, not delete it"
        )
        assert result.get("phase") == "specify", (
            "Absent key should preserve existing field, not delete it"
        )

        # Now explicitly delete feature_id with None
        write_frontmatter(fpath, {"entity_uuid": VALID_UUID, "feature_id": None})

        # Then feature_id is REMOVED but phase is still preserved
        result2 = read_frontmatter(fpath)
        assert result2 is not None
        assert "feature_id" not in result2, (
            "None value should explicitly delete the field"
        )
        assert result2.get("phase") == "specify", (
            "Phase should still be preserved when only feature_id is deleted"
        )

    def test_serialize_header_field_ordering_matches_spec(self):
        """Serialized header must follow FIELD_ORDER exactly:
        entity_uuid, entity_type_id, artifact_type, created_at,
        feature_id, feature_slug, project_id, phase, updated_at.
        derived_from: spec:R5/TD-2 (field ordering), dimension:mutation_mindset
        Mutation: swapping two fields in FIELD_ORDER would break this test.
        """
        # Given a header with all known fields
        header = {
            "entity_uuid": VALID_UUID,
            "entity_type_id": VALID_TYPE_ID,
            "artifact_type": VALID_ARTIFACT_TYPE,
            "created_at": VALID_CREATED_AT,
            "feature_id": "002",
            "feature_slug": "test-slug",
            "project_id": "P001",
            "phase": "specify",
            "updated_at": "2026-03-02T10:00:00+00:00",
        }
        # When serialized
        result = _serialize_header(header)
        lines = result.split("\n")
        # Then field order within the block (between --- delimiters) matches FIELD_ORDER
        # lines[0] = "---", lines[1..9] = fields, lines[10] = "---"
        expected_order = [
            "entity_uuid",
            "entity_type_id",
            "artifact_type",
            "created_at",
            "feature_id",
            "feature_slug",
            "project_id",
            "phase",
            "updated_at",
        ]
        assert lines[0] == "---"
        for i, field_name in enumerate(expected_order):
            assert lines[i + 1].startswith(f"{field_name}: "), (
                f"Position {i + 1}: expected {field_name!r}, got line {lines[i + 1]!r}"
            )
        assert lines[len(expected_order) + 1] == "---"


class TestWriteFrontmatterErrorPropagation:
    """Error propagation tests for write_frontmatter (dimension: error_propagation)."""

    def test_write_frontmatter_validation_failure_aborts_without_modifying_file(self, tmp_path):
        """When a merge produces an invalid header (e.g., bad artifact_type via merge),
        the file must remain unchanged. No partial writes.
        derived_from: spec:AC-9 (atomic write), design:error-contract, dimension:error_propagation
        """
        # Given a file with valid frontmatter
        fpath = str(tmp_path / "spec.md")
        original_content = (
            "---\n"
            f"entity_uuid: {VALID_UUID}\n"
            f"entity_type_id: {VALID_TYPE_ID}\n"
            f"artifact_type: {VALID_ARTIFACT_TYPE}\n"
            f"created_at: {VALID_CREATED_AT}\n"
            "---\n"
            "# Body\n"
        )
        _write_file(fpath, original_content)

        # When we try to merge in an invalid artifact_type
        with pytest.raises(ValueError):
            write_frontmatter(fpath, {
                "entity_uuid": VALID_UUID,
                "artifact_type": "invalid_type_xyzzy",
            })

        # Then file is completely unchanged
        with open(fpath, "r", encoding="utf-8") as f:
            assert f.read() == original_content

    def test_build_header_propagates_all_validation_errors(self):
        """build_header raises ValueError whose message contains all failing fields.
        derived_from: design:error-contract (no short-circuit), dimension:error_propagation
        """
        # Given multiple invalid inputs
        with pytest.raises(ValueError) as exc_info:
            build_header(
                entity_uuid="not-a-uuid",
                entity_type_id=VALID_TYPE_ID,
                artifact_type="invalid_type",
                created_at="not-a-date",
            )
        # Then the error message mentions all three failures
        msg = str(exc_info.value)
        assert "entity_uuid" in msg or "UUID" in msg
        assert "artifact_type" in msg
        assert "created_at" in msg
