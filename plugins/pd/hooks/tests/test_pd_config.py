"""Tests for the standalone pd_config.config reader.

Replaces the config-reader coverage that previously lived in the (now
removed) semantic_memory.config test suite. Verifies the core, memory-
independent config parsing used by the entity registry, workflow engine,
and doctor.
"""
from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.normpath(os.path.join(_HERE, "..", "lib"))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from pd_config.config import DEFAULTS, read_config  # noqa: E402


def _write_config(tmp_path, body: str) -> str:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "pd.local.md").write_text(body)
    return str(tmp_path)


def test_defaults_are_memory_independent():
    # The extracted reader must NOT carry any memory_* defaults.
    assert set(DEFAULTS) == {"artifacts_root", "base_branch", "release_script"}
    assert not any(k.startswith("memory_") for k in DEFAULTS)


def test_missing_file_returns_defaults():
    result = read_config("/nonexistent/project/root/xyz")
    assert result == DEFAULTS
    assert result["artifacts_root"] == "docs"
    assert result["base_branch"] == "auto"


def test_reads_overrides(tmp_path):
    root = _write_config(tmp_path, "artifacts_root: artifacts\nbase_branch: develop\n")
    cfg = read_config(root)
    assert cfg["artifacts_root"] == "artifacts"
    assert cfg["base_branch"] == "develop"


def test_first_occurrence_wins(tmp_path):
    root = _write_config(tmp_path, "base_branch: develop\nbase_branch: main\n")
    assert read_config(root)["base_branch"] == "develop"


def test_empty_and_null_fall_back_to_default(tmp_path):
    root = _write_config(tmp_path, "artifacts_root:\nbase_branch: null\n")
    cfg = read_config(root)
    assert cfg["artifacts_root"] == "docs"
    assert cfg["base_branch"] == "auto"


def test_comment_and_indented_lines_ignored(tmp_path):
    root = _write_config(tmp_path, "# artifacts_root: ignored\n   base_branch: indented\n")
    cfg = read_config(root)
    assert cfg["artifacts_root"] == "docs"
    assert cfg["base_branch"] == "auto"


def test_type_coercion_for_unknown_keys(tmp_path):
    # Unknown (non-pd_) keys are still parsed and coerced, tolerated for
    # forward-compat (e.g. yolo_mode, max_concurrent_agents).
    root = _write_config(tmp_path, "max_concurrent_agents: 7\nyolo_mode: true\n")
    cfg = read_config(root)
    assert cfg["max_concurrent_agents"] == 7
    assert cfg["yolo_mode"] is True


def test_spaces_stripped(tmp_path):
    root = _write_config(tmp_path, "base_branch:   main  \n")
    assert read_config(root)["base_branch"] == "main"
