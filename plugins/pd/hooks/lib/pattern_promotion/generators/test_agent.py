"""Tests for pattern_promotion.generators.agent.

Parallels test_skill. Target pool is `plugins/pd/agents/` (flat .md files,
not directories). Common headings: "Checks", "Process", "Validation Criteria".
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from pattern_promotion.generators import agent
from pattern_promotion.kb_parser import KBEntry
from pattern_promotion.types import DiffPlan, FileEdit


SAMPLE_AGENT_MD = textwrap.dedent("""\
    ---
    name: code-quality-reviewer
    description: Reviews implementation quality
    model: sonnet
    ---

    # Code Quality Reviewer Agent

    You review implementation quality after spec compliance is confirmed.

    ## Review Areas

    ### Code Quality

    - Adherence to established patterns
    - Error handling at I/O boundaries

    ### Testing

    - Test coverage meets baseline
    - Tests verify behavior (not mocks)

    ## Validation Criteria

    - Code style matches project conventions
    - Public APIs have docstrings
    """)


def _entry(name: str = "Encapsulation in tests") -> KBEntry:
    return KBEntry(
        name=name,
        description="Test code should respect the same encapsulation boundaries as production code.",
        confidence="high",
        effective_observation_count=3,
        category="patterns",
        file_path=Path("/tmp/patterns.md"),
        line_range=(1, 5),
    )


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    root = tmp_path / "pd"
    # Minimal skills presence is required by inventory's plugin-root resolver
    (root / "skills" / "dummy").mkdir(parents=True)
    (root / "skills" / "dummy" / "SKILL.md").write_text("# Dummy\n")
    agents_dir = root / "agents"
    agents_dir.mkdir()
    (agents_dir / "code-quality-reviewer.md").write_text(SAMPLE_AGENT_MD)
    (agents_dir / "plan-reviewer.md").write_text("# Plan Reviewer\n")
    return root


# ---------------------------------------------------------------------------
# validate_target_meta
# ---------------------------------------------------------------------------


class TestValidate:
    def test_accepts_valid_meta(self, plugin_root: Path):
        meta = {
            "agent_name": "code-quality-reviewer",
            "section_heading": "## Validation Criteria",
            "insertion_mode": "append-to-list",
        }
        ok, reason = agent.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is True
        assert reason is None

    def test_rejects_unknown_agent_name(self, plugin_root: Path):
        meta = {
            "agent_name": "nonesuch",
            "section_heading": "## Validation Criteria",
            "insertion_mode": "append-to-list",
        }
        ok, reason = agent.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is False

    def test_rejects_missing_heading(self, plugin_root: Path):
        meta = {
            "agent_name": "code-quality-reviewer",
            "section_heading": "## Does Not Exist",
            "insertion_mode": "append-to-list",
        }
        ok, reason = agent.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is False

    def test_rejects_invalid_insertion_mode(self, plugin_root: Path):
        meta = {
            "agent_name": "code-quality-reviewer",
            "section_heading": "## Validation Criteria",
            "insertion_mode": "freeform",
        }
        ok, reason = agent.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is False

    def test_rejects_missing_keys(self, plugin_root: Path):
        meta = {"agent_name": "code-quality-reviewer"}
        ok, reason = agent.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is False


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_single_modify_edit(self, plugin_root: Path):
        entry = _entry()
        plan = agent.generate(
            entry,
            {
                "agent_name": "code-quality-reviewer",
                "section_heading": "## Validation Criteria",
                "insertion_mode": "append-to-list",
            },
            plugin_root=plugin_root,
        )
        assert isinstance(plan, DiffPlan)
        assert plan.target_type == "agent"
        assert len(plan.edits) == 1
        e = plan.edits[0]
        assert isinstance(e, FileEdit)
        assert e.action == "modify"
        assert e.write_order == 0

    def test_target_path_points_at_agent_md(self, plugin_root: Path):
        entry = _entry()
        plan = agent.generate(
            entry,
            {
                "agent_name": "code-quality-reviewer",
                "section_heading": "## Validation Criteria",
                "insertion_mode": "append-to-list",
            },
            plugin_root=plugin_root,
        )
        assert plan.target_path.name == "code-quality-reviewer.md"

    def test_td8_marker_present(self, plugin_root: Path):
        entry = _entry("Encapsulation in tests")
        plan = agent.generate(
            entry,
            {
                "agent_name": "code-quality-reviewer",
                "section_heading": "## Validation Criteria",
                "insertion_mode": "append-to-list",
            },
            plugin_root=plugin_root,
        )
        after = plan.edits[0].after
        assert "<!-- Promoted: Encapsulation in tests -->" in after

    def test_append_to_list_preserves_existing(self, plugin_root: Path):
        entry = _entry()
        plan = agent.generate(
            entry,
            {
                "agent_name": "code-quality-reviewer",
                "section_heading": "## Validation Criteria",
                "insertion_mode": "append-to-list",
            },
            plugin_root=plugin_root,
        )
        after = plan.edits[0].after
        assert "- Code style matches project conventions" in after
        assert "- Public APIs have docstrings" in after

    def test_new_paragraph_mode(self, plugin_root: Path):
        entry = _entry("Paragraph-style guidance")
        plan = agent.generate(
            entry,
            {
                "agent_name": "code-quality-reviewer",
                "section_heading": "### Testing",
                "insertion_mode": "new-paragraph-after-heading",
            },
            plugin_root=plugin_root,
        )
        after = plan.edits[0].after
        assert "<!-- Promoted: Paragraph-style guidance -->" in after

    def test_generate_rejects_invalid_meta(self, plugin_root: Path):
        entry = _entry()
        with pytest.raises(ValueError):
            agent.generate(
                entry,
                {
                    "agent_name": "nonesuch",
                    "section_heading": "## Whatever",
                    "insertion_mode": "append-to-list",
                },
                plugin_root=plugin_root,
            )
