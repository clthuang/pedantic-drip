"""Tests for metadata parsing and validation (Task 1A.1)."""
from __future__ import annotations

import json

import pytest

from entity_registry.metadata import (
    METADATA_SCHEMAS,
    parse_metadata,
    validate_metadata,
)


# ---------------------------------------------------------------------------
# parse_metadata
# ---------------------------------------------------------------------------
class TestParseMetadata:
    def test_none_returns_empty_dict(self):
        assert parse_metadata(None) == {}

    def test_empty_string_returns_empty_dict(self):
        assert parse_metadata("") == {}

    def test_empty_json_object_returns_empty_dict(self):
        assert parse_metadata("{}") == {}

    def test_dict_passthrough(self):
        d = {"k": "v"}
        assert parse_metadata(d) == {"k": "v"}

    def test_json_string_parsed(self):
        assert parse_metadata('{"a": 1}') == {"a": 1}

    def test_invalid_json_returns_empty_dict(self):
        assert parse_metadata("not json") == {}

    def test_json_array_returns_empty_dict(self):
        """Non-dict JSON values should return empty dict."""
        assert parse_metadata("[1,2,3]") == {}

    def test_json_number_returns_empty_dict(self):
        assert parse_metadata("42") == {}

    def test_complex_nested_dict(self):
        raw = json.dumps({"phase_timing": {"brainstorm": {"started": "2024-01-01"}}})
        result = parse_metadata(raw)
        assert result["phase_timing"]["brainstorm"]["started"] == "2024-01-01"

    def test_dict_with_none_values(self):
        assert parse_metadata({"key": None}) == {"key": None}

    def test_empty_dict_passthrough(self):
        assert parse_metadata({}) == {}


# ---------------------------------------------------------------------------
# validate_metadata
# ---------------------------------------------------------------------------
class TestValidateMetadata:
    def test_empty_metadata_no_warnings(self):
        assert validate_metadata("feature", {}) == []

    def test_valid_feature_metadata(self):
        meta = {"id": "001", "slug": "test", "mode": "standard", "progress": 0.5}
        assert validate_metadata("feature", meta) == []

    def test_invalid_type_warns(self):
        warnings = validate_metadata("key_result", {"metric_type": 123})
        assert len(warnings) == 1
        assert "expected str" in warnings[0]
        assert "got int" in warnings[0]

    def test_unknown_key_warns(self):
        warnings = validate_metadata("feature", {"unknown_key": "val"})
        assert len(warnings) == 1
        assert "Unknown metadata key" in warnings[0]

    def test_common_progress_valid_int(self):
        assert validate_metadata("feature", {"progress": 1}) == []

    def test_common_progress_valid_float(self):
        assert validate_metadata("feature", {"progress": 0.5}) == []

    def test_common_progress_invalid_string(self):
        warnings = validate_metadata("feature", {"progress": "50%"})
        assert len(warnings) == 1
        assert "progress" in warnings[0]

    def test_project_metadata_valid(self):
        meta = {"id": "P01", "slug": "proj", "features": ["f1"], "milestones": []}
        assert validate_metadata("project", meta) == []

    def test_task_metadata_valid(self):
        assert validate_metadata("task", {"source_heading": "## Task"}) == []

    def test_backlog_metadata_valid(self):
        assert validate_metadata("backlog", {"description": "A desc"}) == []

    def test_key_result_weight_float(self):
        assert validate_metadata("key_result", {"weight": 2.0}) == []

    def test_key_result_weight_int(self):
        assert validate_metadata("key_result", {"weight": 2}) == []

    def test_key_result_weight_string_warns(self):
        warnings = validate_metadata("key_result", {"weight": "heavy"})
        assert len(warnings) == 1

    def test_multiple_errors(self):
        warnings = validate_metadata(
            "feature", {"id": 42, "slug": 99, "unknown": True}
        )
        assert len(warnings) == 3

    def test_none_metadata_no_warnings(self):
        assert validate_metadata("feature", {}) == []

    def test_unknown_entity_type_warns(self):
        warnings = validate_metadata("nonexistent_type", {"key": "val"})
        assert len(warnings) == 1
        assert "No schema defined" in warnings[0]

    def test_all_types_have_schemas(self):
        """Every type in METADATA_SCHEMAS should be validatable."""
        for etype in METADATA_SCHEMAS:
            # Should not raise
            validate_metadata(etype, {})

    def test_common_schema_applied_to_all_types(self):
        """progress is valid for any entity type with a schema."""
        for etype in METADATA_SCHEMAS:
            assert validate_metadata(etype, {"progress": 0.5}) == []
