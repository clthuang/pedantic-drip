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

    def test_phase_summaries_list_no_warnings(self):
        """phase_summaries: list should produce no warnings for feature type (AC-11)."""
        meta = {
            "phase_summaries": [
                {
                    "phase": "specify",
                    "timestamp": "2026-04-02T08:00:00Z",
                    "outcome": "Done",
                    "artifacts_produced": ["spec.md"],
                    "key_decisions": "Chose X",
                    "reviewer_feedback_summary": "LGTM",
                    "rework_trigger": None,
                }
            ]
        }
        assert validate_metadata("feature", meta) == []

    def test_backward_context_dict_no_warnings(self):
        """backward_context: dict should produce no warnings for feature type."""
        meta = {"backward_context": {"source_phase": "design", "findings": []}}
        assert validate_metadata("feature", meta) == []

    def test_backward_return_target_str_no_warnings(self):
        """backward_return_target: str should produce no warnings."""
        assert validate_metadata("feature", {"backward_return_target": "specify"}) == []

    def test_backward_history_list_no_warnings(self):
        """backward_history: list should produce no warnings."""
        assert validate_metadata("feature", {"backward_history": []}) == []

    # -- Feature 075: deepened tests --

    def test_phase_summaries_wrong_type_string_warns(self):
        """dimension:adversarial — phase_summaries as string triggers type warning.
        derived_from: AC-11 (schema validation)"""
        # Given validate_metadata expects phase_summaries to be a list
        # When called with a string value instead
        warnings = validate_metadata("feature", {"phase_summaries": "not a list"})
        # Then a type-mismatch warning is produced
        assert len(warnings) == 1
        assert "expected list" in warnings[0]
        assert "got str" in warnings[0]

    def test_phase_summaries_wrong_type_dict_warns(self):
        """dimension:adversarial — phase_summaries as dict triggers type warning.
        derived_from: AC-11 (schema validation)"""
        # Given validate_metadata expects phase_summaries to be a list
        # When called with a dict value instead
        warnings = validate_metadata("feature", {"phase_summaries": {"phase": "specify"}})
        # Then a type-mismatch warning is produced
        assert len(warnings) == 1
        assert "expected list" in warnings[0]
        assert "got dict" in warnings[0]

    def test_phase_summaries_wrong_type_int_warns(self):
        """dimension:adversarial — phase_summaries as int triggers type warning.
        derived_from: AC-11 (schema validation)"""
        warnings = validate_metadata("feature", {"phase_summaries": 42})
        assert len(warnings) == 1
        assert "expected list" in warnings[0]
        assert "got int" in warnings[0]
