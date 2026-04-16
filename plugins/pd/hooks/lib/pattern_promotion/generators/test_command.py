"""Tests for pattern_promotion.generators.command.

Per FR-3-command:
- target pool is `plugins/pd/commands/*.md`
- target_meta uses `step_id` instead of `section_heading`; the generator
  matches against `### Step {step_id}:` headings (convention in pd commands).
- TD-8 marker block inserted inside the step body.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from pattern_promotion.generators import command
from pattern_promotion.kb_parser import KBEntry
from pattern_promotion.types import DiffPlan, FileEdit


SAMPLE_COMMAND_MD = textwrap.dedent("""\
    ---
    description: Sample command for tests
    ---

    # /pd:sample Command

    Sample intro.

    ## Step 1: Overview

    ### Step 1a: Commit and Push

    1. Check for uncommitted changes via `git status`.
    2. Commit and push.

    Rules:

    - Never force-push
    - Always verify clean tree

    ### Step 1b: Validate

    1. Run `./validate.sh`.

    ## Step 2: Completion

    ### Step 2a: Final Output

    Output a summary.
    """)


def _entry(name: str = "Verify clean tree before commit") -> KBEntry:
    return KBEntry(
        name=name,
        description="Always check `git status` and avoid committing unrelated files.",
        confidence="high",
        effective_observation_count=3,
        category="patterns",
        file_path=Path("/tmp/patterns.md"),
        line_range=(1, 5),
    )


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    root = tmp_path / "pd"
    # inventory requires a skills/ dir with at least one SKILL.md for the
    # plugin-root resolver to identify this as a pd plugin root.
    (root / "skills" / "dummy").mkdir(parents=True)
    (root / "skills" / "dummy" / "SKILL.md").write_text("# Dummy\n")
    cmds = root / "commands"
    cmds.mkdir()
    (cmds / "sample.md").write_text(SAMPLE_COMMAND_MD)
    (cmds / "other.md").write_text("# Other\n")
    return root


# ---------------------------------------------------------------------------
# validate_target_meta
# ---------------------------------------------------------------------------


class TestValidate:
    def test_accepts_valid_meta(self, plugin_root: Path):
        meta = {
            "command_name": "sample",
            "step_id": "1a",
            "insertion_mode": "append-to-list",
        }
        ok, reason = command.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is True, reason
        assert reason is None

    def test_rejects_unknown_command(self, plugin_root: Path):
        meta = {
            "command_name": "nonesuch",
            "step_id": "1a",
            "insertion_mode": "append-to-list",
        }
        ok, reason = command.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is False

    def test_rejects_unknown_step_id(self, plugin_root: Path):
        meta = {
            "command_name": "sample",
            "step_id": "99z",
            "insertion_mode": "append-to-list",
        }
        ok, reason = command.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is False
        assert reason is not None
        assert "step" in reason.lower() or "99z" in reason

    def test_rejects_invalid_insertion_mode(self, plugin_root: Path):
        meta = {
            "command_name": "sample",
            "step_id": "1a",
            "insertion_mode": "sprinkle",
        }
        ok, reason = command.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is False

    def test_rejects_missing_keys(self, plugin_root: Path):
        meta = {"command_name": "sample"}
        ok, reason = command.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is False


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_single_modify_edit(self, plugin_root: Path):
        entry = _entry()
        plan = command.generate(
            entry,
            {
                "command_name": "sample",
                "step_id": "1a",
                "insertion_mode": "append-to-list",
            },
            plugin_root=plugin_root,
        )
        assert isinstance(plan, DiffPlan)
        assert plan.target_type == "command"
        assert len(plan.edits) == 1
        e = plan.edits[0]
        assert isinstance(e, FileEdit)
        assert e.action == "modify"
        assert e.write_order == 0

    def test_target_path_points_at_command_md(self, plugin_root: Path):
        entry = _entry()
        plan = command.generate(
            entry,
            {
                "command_name": "sample",
                "step_id": "1a",
                "insertion_mode": "append-to-list",
            },
            plugin_root=plugin_root,
        )
        assert plan.target_path.name == "sample.md"

    def test_td8_marker_present(self, plugin_root: Path):
        entry = _entry("Verify clean tree before commit")
        plan = command.generate(
            entry,
            {
                "command_name": "sample",
                "step_id": "1a",
                "insertion_mode": "append-to-list",
            },
            plugin_root=plugin_root,
        )
        after = plan.edits[0].after
        assert "<!-- Promoted: Verify clean tree before commit -->" in after

    def test_append_to_list_inserts_inside_step_body(self, plugin_root: Path):
        entry = _entry("Verify clean tree before commit")
        plan = command.generate(
            entry,
            {
                "command_name": "sample",
                "step_id": "1a",
                "insertion_mode": "append-to-list",
            },
            plugin_root=plugin_root,
        )
        after = plan.edits[0].after
        # Existing content preserved
        assert "- Never force-push" in after
        assert "- Always verify clean tree" in after
        # Next step untouched
        assert "### Step 1b: Validate" in after
        assert "### Step 2a: Final Output" in after
        # Marker must appear between Step 1a heading and Step 1b heading
        lines = after.splitlines()
        step1a_idx = next(
            i for i, ln in enumerate(lines) if ln.startswith("### Step 1a")
        )
        step1b_idx = next(
            i for i, ln in enumerate(lines) if ln.startswith("### Step 1b")
        )
        marker_idx = next(
            i for i, ln in enumerate(lines) if "<!-- Promoted:" in ln
        )
        assert step1a_idx < marker_idx < step1b_idx

    def test_new_paragraph_mode(self, plugin_root: Path):
        entry = _entry("Paragraph-style command guidance")
        plan = command.generate(
            entry,
            {
                "command_name": "sample",
                "step_id": "2a",
                "insertion_mode": "new-paragraph-after-heading",
            },
            plugin_root=plugin_root,
        )
        after = plan.edits[0].after
        assert "<!-- Promoted: Paragraph-style command guidance -->" in after

    def test_generate_rejects_invalid_meta(self, plugin_root: Path):
        entry = _entry()
        with pytest.raises(ValueError):
            command.generate(
                entry,
                {
                    "command_name": "nonesuch",
                    "step_id": "1a",
                    "insertion_mode": "append-to-list",
                },
                plugin_root=plugin_root,
            )
