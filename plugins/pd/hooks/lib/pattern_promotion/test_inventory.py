"""Tests for pattern_promotion.inventory.

Fixture-based unit tests exercise the two-location resolution logic.
A sanity test exercises the real repo to confirm non-empty results.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pattern_promotion.inventory import (
    list_agents,
    list_commands,
    list_skills,
)


@pytest.fixture
def fake_plugin_root(tmp_path: Path) -> Path:
    root = tmp_path / "pd"
    (root / "skills" / "implementing").mkdir(parents=True)
    (root / "skills" / "implementing" / "SKILL.md").write_text("# Implementing")
    (root / "skills" / "brainstorming").mkdir(parents=True)
    (root / "skills" / "brainstorming" / "SKILL.md").write_text("# Brainstorming")
    # A skills directory without SKILL.md should be skipped
    (root / "skills" / "incomplete").mkdir(parents=True)

    (root / "agents").mkdir()
    (root / "agents" / "code-reviewer.md").write_text("# Code Reviewer")
    (root / "agents" / "implementer.md").write_text("# Implementer")

    (root / "commands").mkdir()
    (root / "commands" / "wrap-up.md").write_text("# Wrap Up")
    (root / "commands" / "doctor.md").write_text("# Doctor")
    return root


class TestListSkills:
    def test_lists_only_subdirs_with_skill_md(self, fake_plugin_root: Path):
        result = list_skills(plugin_root=fake_plugin_root)
        assert result == ["brainstorming", "implementing"]

    def test_real_repo_non_empty(self):
        """Sanity check against actual plugins/pd/ in this repo."""
        project_root = Path(__file__).resolve().parents[5]
        skills = list_skills(project_root=project_root)
        assert len(skills) > 0


class TestListAgents:
    def test_agent_basenames_sorted(self, fake_plugin_root: Path):
        assert list_agents(plugin_root=fake_plugin_root) == [
            "code-reviewer",
            "implementer",
        ]

    def test_real_repo_non_empty(self):
        project_root = Path(__file__).resolve().parents[5]
        assert len(list_agents(project_root=project_root)) > 0


class TestListCommands:
    def test_command_basenames_sorted(self, fake_plugin_root: Path):
        assert list_commands(plugin_root=fake_plugin_root) == [
            "doctor",
            "wrap-up",
        ]

    def test_real_repo_non_empty(self):
        project_root = Path(__file__).resolve().parents[5]
        assert len(list_commands(project_root=project_root)) > 0


class TestFallbackResolution:
    def test_missing_plugin_root_raises(self, tmp_path: Path, monkeypatch):
        import pattern_promotion.inventory as inv

        # Neutralize the primary cache glob for this test only.
        monkeypatch.setattr(inv, "PRIMARY_GLOB", str(tmp_path / "never_matches" / "*"))
        with pytest.raises(FileNotFoundError):
            list_skills(project_root=tmp_path)
