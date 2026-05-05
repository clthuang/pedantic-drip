"""Tests for FR-7 enumerate JSON contract + FR-8 argparse tolerance (feature 104).

Companion to test_cli_integration.py, which auto-injects --include-descriptive
for FR-5 fixture compat. This module tests DEFAULT behavior (no flag) and
argparse-tolerance edge cases that test_cli_integration cannot exercise via
its _run_cli helper.

Per design TD-4: this module uses _run_direct (NO --include-descriptive
auto-injection) so default-filter tests can observe the pre-FR-5 default.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[5]
VENV_PY = REPO_ROOT / "plugins/pd/.venv/bin/python"
PLUGIN_LIB = REPO_ROOT / "plugins/pd/hooks/lib"
MAIN_PY = PLUGIN_LIB / "pattern_promotion/__main__.py"


def _run_direct(*args: str, cwd: Path | None = None) -> tuple[int, str, str]:
    """Subprocess invocation WITHOUT auto-injected --include-descriptive flag."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PLUGIN_LIB) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [str(VENV_PY), "-m", "pattern_promotion", *args],
        env=env,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _make_kb(tmp_path: Path, files: dict[str, str]) -> Path:
    """Build a synthetic KB dir with the given filename → content map."""
    kb = tmp_path / "kb"
    kb.mkdir()
    for name, content in files.items():
        (kb / name).write_text(content)
    return kb


def _entry_with_keywords(name: str, keywords: list[str], obs: int = 5) -> str:
    """Build a markdown entry block with the given heading and keyword text."""
    body = " ".join(keywords)
    return (
        f"### {name}\n"
        f"{body}.\n"
        f"- Observation count: {obs}\n"
        f"- Confidence: high\n"
        f"- Last observed: Feature #{obs:03d}\n\n"
    )


# Strong-marker keywords each contribute score 2; soft-marker each contribute 1
# (per plugins/pd/hooks/lib/pattern_promotion/enforceability.py).
ENFORCEABLE_2 = "must always"  # 2 strong markers → score 4
ENFORCEABLE_1 = "must"  # 1 strong marker → score 2
DESCRIPTIVE = "Heavy upfront investment reduces iterations"  # 0 markers → score 0


class TestEnumerateJSONContract:
    """FR-7: enumerate JSON contract — top-level entries key, default-filter,
    --include-descriptive opt-in, DESC sort.
    """

    def test_top_level_entries_key(self, tmp_path: Path):
        """AC-7.1: enumerate output has top-level `entries` key (not bare list)."""
        kb = _make_kb(tmp_path, {
            "anti-patterns.md": _entry_with_keywords("Enforceable rule", [ENFORCEABLE_1]) + _entry_with_keywords("Descriptive only", [DESCRIPTIVE]),
        })
        sandbox = tmp_path / "sb"
        rc, _, _ = _run_direct(
            "enumerate", "--sandbox", str(sandbox),
            "--kb-dir", str(kb), "--include-descriptive",
        )
        assert rc == 0
        data = json.loads((sandbox / "entries.json").read_text())
        assert isinstance(data, dict)
        assert "entries" in data
        assert isinstance(data["entries"], list)

    def test_default_excludes_descriptive(self, tmp_path: Path):
        """AC-7.2: default invocation (no --include-descriptive) excludes
        entries with descriptive=true.
        """
        kb = _make_kb(tmp_path, {
            "anti-patterns.md": _entry_with_keywords("Enforceable rule", [ENFORCEABLE_1]) + _entry_with_keywords("Descriptive only", [DESCRIPTIVE]),
        })
        sandbox = tmp_path / "sb"
        rc, _, _ = _run_direct(
            "enumerate", "--sandbox", str(sandbox), "--kb-dir", str(kb),
        )
        assert rc == 0
        data = json.loads((sandbox / "entries.json").read_text())
        assert all(not e.get("descriptive") for e in data["entries"])
        assert len(data["entries"]) == 1

    def test_include_descriptive_flag(self, tmp_path: Path):
        """AC-7.3: --include-descriptive includes entries with descriptive=true."""
        kb = _make_kb(tmp_path, {
            "anti-patterns.md": _entry_with_keywords("Enforceable rule", [ENFORCEABLE_1]) + _entry_with_keywords("Descriptive only", [DESCRIPTIVE]),
        })
        sandbox = tmp_path / "sb"
        rc, _, _ = _run_direct(
            "enumerate", "--sandbox", str(sandbox),
            "--kb-dir", str(kb), "--include-descriptive",
        )
        assert rc == 0
        data = json.loads((sandbox / "entries.json").read_text())
        assert len(data["entries"]) == 2
        assert any(e.get("descriptive") for e in data["entries"])

    def test_desc_sort_by_score(self, tmp_path: Path):
        """AC-7.4: 3-entry KB scored 4, 2, 0 → DESC by enforceability_score."""
        kb = _make_kb(tmp_path, {
            "anti-patterns.md": (
                _entry_with_keywords("High score", ["must always"])  # score 4
                + _entry_with_keywords("Medium score", ["must"])  # score 2
                + _entry_with_keywords("Zero score", [DESCRIPTIVE])  # score 0
            ),
        })
        sandbox = tmp_path / "sb"
        rc, _, _ = _run_direct(
            "enumerate", "--sandbox", str(sandbox),
            "--kb-dir", str(kb), "--include-descriptive",
        )
        assert rc == 0
        data = json.loads((sandbox / "entries.json").read_text())
        scores = [e["enforceability_score"] for e in data["entries"]]
        assert scores == sorted(scores, reverse=True)
        assert scores[0] >= scores[-1]


class TestArgparseTolerance:
    """FR-8: argparse tolerance — parse_known_args, unknown args exit 0,
    --entries triggers orchestrator suggestion, functional preservation.
    """

    def test_parse_known_args_present(self):
        """AC-8.1: __main__.py uses parse_known_args, NOT parser.parse_args(argv)."""
        src = MAIN_PY.read_text()
        assert "parse_known_args" in src, "parse_known_args missing from __main__.py"
        assert "parser.parse_args(argv)" not in src, (
            "Legacy parser.parse_args(argv) call still present"
        )

    def test_unknown_args_exit_zero(self, tmp_path: Path):
        """AC-8.2: unknown args produce stderr WARN and exit 0 (NOT SystemExit(2))."""
        kb = _make_kb(tmp_path, {
            "anti-patterns.md": _entry_with_keywords("Rule", [ENFORCEABLE_1]),
        })
        sandbox = tmp_path / "sb"
        rc, _, stderr = _run_direct(
            "enumerate", "--sandbox", str(sandbox),
            "--kb-dir", str(kb), "--bogus", "value",
        )
        assert rc == 0, f"expected exit 0, got {rc}; stderr={stderr}"
        assert "WARN: unknown args ignored" in stderr
        assert "--bogus" in stderr

    def test_entries_triggers_suggestion(self, tmp_path: Path):
        """AC-8.3: --entries flag triggers orchestrator-suggestion text."""
        kb = _make_kb(tmp_path, {
            "anti-patterns.md": _entry_with_keywords("Rule", [ENFORCEABLE_1]),
        })
        sandbox = tmp_path / "sb"
        rc, _, stderr = _run_direct(
            "enumerate", "--sandbox", str(sandbox),
            "--kb-dir", str(kb), "--entries", "foo",
        )
        assert rc == 0
        assert "did you mean to invoke /pd:promote-pattern" in stderr

    def test_functional_preservation(self, tmp_path: Path):
        """AC-8.4: with bogus args, functional output (entries.json) still produced
        and matches AC-7.1 contract.
        """
        kb = _make_kb(tmp_path, {
            "anti-patterns.md": _entry_with_keywords("Rule", [ENFORCEABLE_1]),
        })
        sandbox = tmp_path / "sb"
        rc, _, _ = _run_direct(
            "enumerate", "--sandbox", str(sandbox),
            "--kb-dir", str(kb), "--entries", "foo",
        )
        assert rc == 0
        data = json.loads((sandbox / "entries.json").read_text())
        assert "entries" in data
        assert isinstance(data["entries"], list)
