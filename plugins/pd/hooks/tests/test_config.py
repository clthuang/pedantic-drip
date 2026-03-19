"""Tests for semantic_memory.config module.

TDD: written before implementation. Tests cover:
- Default values when config file is missing
- Parsing of key: value lines from a real-format config file
- Type coercion: bool, int, float, str
- Space stripping (tr -d ' ' equivalent)
- Only first match per key is used (head -1 equivalent)
- Keys not in defaults are included in output
- Null/empty values fall back to defaults
"""
from __future__ import annotations

import os
import sys

# Allow imports from hooks/lib/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from semantic_memory.config import read_config


class TestReadConfigDefaults:
    """When config file is missing, return all defaults."""

    def test_missing_file_returns_defaults(self, tmp_path):
        result = read_config(str(tmp_path))
        assert result["activation_mode"] == "manual"
        assert result["memory_semantic_enabled"] is True
        assert result["memory_vector_weight"] == 0.5
        assert result["memory_keyword_weight"] == 0.2
        assert result["memory_prominence_weight"] == 0.3
        assert result["memory_embedding_provider"] == "gemini"
        assert result["memory_embedding_model"] == "gemini-embedding-001"
        assert result["memory_keyword_provider"] == "auto"
        assert result["memory_injection_limit"] == 20
        assert result["memory_model_capture_mode"] == "ask-first"
        assert result["memory_silent_capture_budget"] == 5

    def test_new_project_config_defaults(self, tmp_path):
        """Project-awareness fields have correct defaults."""
        result = read_config(str(tmp_path))
        assert result["artifacts_root"] == "docs"
        assert result["base_branch"] == "auto"
        assert result["release_script"] == ""
        assert result["backfill_scan_dirs"] == ""

    def test_default_types(self, tmp_path):
        result = read_config(str(tmp_path))
        assert isinstance(result["memory_semantic_enabled"], bool)
        assert isinstance(result["memory_vector_weight"], float)
        assert isinstance(result["memory_keyword_weight"], float)
        assert isinstance(result["memory_prominence_weight"], float)
        assert isinstance(result["memory_embedding_provider"], str)
        assert isinstance(result["memory_embedding_model"], str)
        assert isinstance(result["memory_keyword_provider"], str)
        assert isinstance(result["memory_injection_limit"], int)


class TestReadConfigParsing:
    """Parsing key: value lines from config files."""

    def _write_config(self, tmp_path, content: str):
        """Write a config file at the expected path."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        config_file = claude_dir / "pd.local.md"
        config_file.write_text(content)

    def test_bool_true(self, tmp_path):
        self._write_config(tmp_path, "memory_semantic_enabled: true\n")
        result = read_config(str(tmp_path))
        assert result["memory_semantic_enabled"] is True

    def test_bool_false(self, tmp_path):
        self._write_config(tmp_path, "memory_semantic_enabled: false\n")
        result = read_config(str(tmp_path))
        assert result["memory_semantic_enabled"] is False

    def test_int_value(self, tmp_path):
        self._write_config(tmp_path, "memory_injection_limit: 30\n")
        result = read_config(str(tmp_path))
        assert result["memory_injection_limit"] == 30
        assert isinstance(result["memory_injection_limit"], int)

    def test_float_value(self, tmp_path):
        self._write_config(tmp_path, "memory_vector_weight: 0.7\n")
        result = read_config(str(tmp_path))
        assert result["memory_vector_weight"] == 0.7
        assert isinstance(result["memory_vector_weight"], float)

    def test_string_value(self, tmp_path):
        self._write_config(tmp_path, "memory_embedding_provider: voyage\n")
        result = read_config(str(tmp_path))
        assert result["memory_embedding_provider"] == "voyage"

    def test_negative_int(self, tmp_path):
        self._write_config(tmp_path, "memory_injection_limit: -5\n")
        result = read_config(str(tmp_path))
        assert result["memory_injection_limit"] == -5
        assert isinstance(result["memory_injection_limit"], int)

    def test_negative_float(self, tmp_path):
        self._write_config(tmp_path, "memory_vector_weight: -0.3\n")
        result = read_config(str(tmp_path))
        assert result["memory_vector_weight"] == -0.3
        assert isinstance(result["memory_vector_weight"], float)


class TestReadConfigSpaceStripping:
    """Matches bash tr -d ' ' -- strip ALL spaces from values."""

    def _write_config(self, tmp_path, content: str):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "pd.local.md").write_text(content)

    def test_spaces_stripped_from_string(self, tmp_path):
        self._write_config(tmp_path, "memory_embedding_model: gemini embedding 001\n")
        result = read_config(str(tmp_path))
        # tr -d ' ' strips ALL spaces
        assert result["memory_embedding_model"] == "geminiembedding001"

    def test_spaces_stripped_from_bool(self, tmp_path):
        self._write_config(tmp_path, "memory_semantic_enabled:  true  \n")
        result = read_config(str(tmp_path))
        assert result["memory_semantic_enabled"] is True

    def test_spaces_stripped_from_float(self, tmp_path):
        self._write_config(tmp_path, "memory_vector_weight:  0.5  \n")
        result = read_config(str(tmp_path))
        assert result["memory_vector_weight"] == 0.5


class TestReadConfigEdgeCases:
    """Edge cases: YAML frontmatter, duplicate keys, unknown keys, empty values."""

    def _write_config(self, tmp_path, content: str):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "pd.local.md").write_text(content)

    def test_yaml_frontmatter_parsed(self, tmp_path):
        """Fields inside --- delimiters are still parsed (no delimiter awareness)."""
        self._write_config(tmp_path, "---\nmemory_injection_limit: 42\n---\n")
        result = read_config(str(tmp_path))
        assert result["memory_injection_limit"] == 42

    def test_first_match_wins(self, tmp_path):
        """Matches bash head -1: only first occurrence of a key is used."""
        self._write_config(
            tmp_path,
            "memory_injection_limit: 10\nmemory_injection_limit: 99\n",
        )
        result = read_config(str(tmp_path))
        assert result["memory_injection_limit"] == 10

    def test_unknown_keys_included(self, tmp_path):
        """Keys not in defaults are still returned (for forward compatibility)."""
        self._write_config(tmp_path, "some_new_config: hello\n")
        result = read_config(str(tmp_path))
        assert result["some_new_config"] == "hello"

    def test_empty_value_uses_default(self, tmp_path):
        """Empty value (just 'key:' with nothing after) uses default."""
        self._write_config(tmp_path, "memory_injection_limit:\n")
        result = read_config(str(tmp_path))
        assert result["memory_injection_limit"] == 20  # default

    def test_null_value_uses_default(self, tmp_path):
        """Value 'null' is treated as missing, uses default (matches bash behavior)."""
        self._write_config(tmp_path, "memory_injection_limit: null\n")
        result = read_config(str(tmp_path))
        assert result["memory_injection_limit"] == 20  # default

    def test_non_field_lines_ignored(self, tmp_path):
        """Lines that don't match ^field: pattern are ignored."""
        self._write_config(
            tmp_path,
            "# This is a comment\n"
            "Some markdown text\n"
            "  indented_key: value\n"  # indented, should NOT match ^field:
            "memory_injection_limit: 15\n",
        )
        result = read_config(str(tmp_path))
        assert result["memory_injection_limit"] == 15
        assert "indented_key" not in result

    def test_real_world_config(self, tmp_path):
        """Matches real pd.local.md format with YAML frontmatter."""
        self._write_config(
            tmp_path,
            "---\n"
            "yolo_mode: true\n"
            "yolo_max_stop_blocks: 50\n"
            "activation_mode: aware\n"
            "memory_semantic_enabled: true\n"
            "memory_vector_weight: 0.6\n"
            "---\n",
        )
        result = read_config(str(tmp_path))
        assert result["activation_mode"] == "aware"
        assert result["memory_semantic_enabled"] is True
        assert result["memory_vector_weight"] == 0.6
        assert result["yolo_mode"] is True
        assert result["yolo_max_stop_blocks"] == 50

    def test_colon_in_value(self, tmp_path):
        """Values containing colons should be handled (take everything after first colon)."""
        self._write_config(tmp_path, "memory_embedding_model: model:v2:latest\n")
        result = read_config(str(tmp_path))
        # After tr -d ' ': "model:v2:latest"
        assert result["memory_embedding_model"] == "model:v2:latest"


class TestReadConfigMatchesBash:
    """Verify Python config reader matches bash read_local_md_field exactly.

    Bash implementation:
        value=$(grep "^${field}:" "$file" 2>/dev/null | head -1 | sed 's/^[^:]*: *//' | tr -d ' ' || echo "")
    """

    def _write_config(self, tmp_path, content: str):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "pd.local.md").write_text(content)

    def test_sed_extracts_after_first_colon_space(self, tmp_path):
        """sed 's/^[^:]*: *//' removes everything up to and including first ': '."""
        self._write_config(tmp_path, "memory_embedding_model: gemini-embedding-001\n")
        result = read_config(str(tmp_path))
        assert result["memory_embedding_model"] == "gemini-embedding-001"

    def test_sed_no_space_after_colon(self, tmp_path):
        """sed 's/^[^:]*: *//' also handles no space after colon."""
        self._write_config(tmp_path, "memory_embedding_model:gemini-embedding-001\n")
        result = read_config(str(tmp_path))
        assert result["memory_embedding_model"] == "gemini-embedding-001"

    def test_sed_multiple_spaces_after_colon(self, tmp_path):
        """sed 's/^[^:]*: *//' handles multiple spaces after colon."""
        self._write_config(tmp_path, "memory_embedding_model:   gemini-embedding-001\n")
        result = read_config(str(tmp_path))
        # sed strips leading spaces after colon, tr -d ' ' strips all remaining
        assert result["memory_embedding_model"] == "gemini-embedding-001"

    def test_float_without_leading_zero(self, tmp_path):
        """Regex ^-?[0-9]*\\.[0-9]+$ should match .5 (no leading zero)."""
        self._write_config(tmp_path, "memory_vector_weight: .5\n")
        result = read_config(str(tmp_path))
        assert result["memory_vector_weight"] == 0.5
        assert isinstance(result["memory_vector_weight"], float)
