"""Tests for pattern_promotion.generators.skill.

Per design C-6 and FR-3-skill:

- `validate_target_meta(target_meta, *, plugin_root)` returns `(bool, reason)`:
  rejects unknown skill names (no such directory under `plugins/pd/skills/`),
  rejects non-existent target headings, and accepts valid meta.
- `generate(entry, target_meta, *, plugin_root) -> DiffPlan` produces a single
  `modify` FileEdit on the target `SKILL.md`. Insertion preserves surrounding
  content and inserts a TD-8 marker block of the form
  `<!-- Promoted: <entry-name> -->`.
- Two insertion modes: `append-to-list` inserts a new bullet at the end of
  the first bullet-list under the heading. `new-paragraph-after-heading`
  inserts a blank line + new paragraph directly below the heading.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from pattern_promotion.generators import skill
from pattern_promotion.kb_parser import KBEntry
from pattern_promotion.types import DiffPlan, FileEdit


SAMPLE_SKILL_MD = textwrap.dedent("""\
    ---
    name: implementing
    description: Sample skill for tests
    ---

    # Implementation Phase

    ## Process

    ### Step 1: Read Task List

    1. Read `tasks.md`.
    2. Parse headings.

    ### Step 2: Per-Task Dispatch Loop

    Dispatches agents. Rules:

    - Keep batches small
    - Prefer worktree isolation

    ## Related Skills

    - implementing-with-tdd
    """)


def _entry(name: str = "Bundle same-file tasks") -> KBEntry:
    return KBEntry(
        name=name,
        description="When multiple tasks touch the same file, dispatch them together.",
        confidence="high",
        effective_observation_count=4,
        category="heuristics",
        file_path=Path("/tmp/heuristics.md"),
        line_range=(1, 5),
    )


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    root = tmp_path / "pd"
    skills_dir = root / "skills"
    (skills_dir / "implementing").mkdir(parents=True)
    (skills_dir / "implementing" / "SKILL.md").write_text(SAMPLE_SKILL_MD)
    (skills_dir / "planning").mkdir()
    (skills_dir / "planning" / "SKILL.md").write_text("# Planning\n")
    return root


# ---------------------------------------------------------------------------
# validate_target_meta
# ---------------------------------------------------------------------------


class TestValidate:
    def test_accepts_valid_meta(self, plugin_root: Path):
        meta = {
            "skill_name": "implementing",
            "section_heading": "### Step 2: Per-Task Dispatch Loop",
            "insertion_mode": "append-to-list",
        }
        ok, reason = skill.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is True
        assert reason is None

    def test_rejects_unknown_skill_name(self, plugin_root: Path):
        meta = {
            "skill_name": "nonesuch",
            "section_heading": "### Step 2: Per-Task Dispatch Loop",
            "insertion_mode": "append-to-list",
        }
        ok, reason = skill.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is False
        assert reason is not None
        assert "nonesuch" in reason.lower() or "not found" in reason.lower()

    def test_rejects_missing_heading(self, plugin_root: Path):
        meta = {
            "skill_name": "implementing",
            "section_heading": "### Step 999: Does Not Exist",
            "insertion_mode": "append-to-list",
        }
        ok, reason = skill.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is False
        assert reason is not None
        assert "heading" in reason.lower() or "not found" in reason.lower()

    def test_rejects_invalid_insertion_mode(self, plugin_root: Path):
        meta = {
            "skill_name": "implementing",
            "section_heading": "### Step 1: Read Task List",
            "insertion_mode": "sprinkle-randomly",
        }
        ok, reason = skill.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is False

    def test_rejects_missing_keys(self, plugin_root: Path):
        meta = {"skill_name": "implementing"}
        ok, reason = skill.validate_target_meta(meta, plugin_root=plugin_root)
        assert ok is False


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_single_modify_edit(self, plugin_root: Path):
        entry = _entry()
        plan = skill.generate(
            entry,
            {
                "skill_name": "implementing",
                "section_heading": "### Step 2: Per-Task Dispatch Loop",
                "insertion_mode": "append-to-list",
            },
            plugin_root=plugin_root,
        )
        assert isinstance(plan, DiffPlan)
        assert plan.target_type == "skill"
        assert len(plan.edits) == 1
        e = plan.edits[0]
        assert isinstance(e, FileEdit)
        assert e.action == "modify"
        assert e.before is not None
        assert e.write_order == 0

    def test_target_path_points_at_skill_md(self, plugin_root: Path):
        entry = _entry()
        plan = skill.generate(
            entry,
            {
                "skill_name": "implementing",
                "section_heading": "### Step 2: Per-Task Dispatch Loop",
                "insertion_mode": "append-to-list",
            },
            plugin_root=plugin_root,
        )
        assert plan.target_path.name == "SKILL.md"
        assert plan.target_path == plan.edits[0].path

    def test_td8_marker_present(self, plugin_root: Path):
        entry = _entry("Bundle same-file tasks")
        plan = skill.generate(
            entry,
            {
                "skill_name": "implementing",
                "section_heading": "### Step 2: Per-Task Dispatch Loop",
                "insertion_mode": "append-to-list",
            },
            plugin_root=plugin_root,
        )
        after = plan.edits[0].after
        # TD-8 marker format for markdown: HTML comment survives parsing
        assert "<!-- Promoted: Bundle same-file tasks -->" in after

    def test_append_to_list_inserts_bullet(self, plugin_root: Path):
        entry = _entry("Bundle same-file tasks")
        plan = skill.generate(
            entry,
            {
                "skill_name": "implementing",
                "section_heading": "### Step 2: Per-Task Dispatch Loop",
                "insertion_mode": "append-to-list",
            },
            plugin_root=plugin_root,
        )
        after = plan.edits[0].after
        # Existing bullets must still be present
        assert "- Keep batches small" in after
        assert "- Prefer worktree isolation" in after
        # New bullet (description) must appear
        assert "- Bundle same-file tasks" in after or (
            "same-file tasks" in after
        )

    def test_append_to_list_preserves_following_sections(
        self, plugin_root: Path
    ):
        entry = _entry()
        plan = skill.generate(
            entry,
            {
                "skill_name": "implementing",
                "section_heading": "### Step 2: Per-Task Dispatch Loop",
                "insertion_mode": "append-to-list",
            },
            plugin_root=plugin_root,
        )
        after = plan.edits[0].after
        # "## Related Skills" section after the target must be preserved
        assert "## Related Skills" in after
        assert "- implementing-with-tdd" in after

    def test_new_paragraph_mode_inserts_after_heading(
        self, plugin_root: Path
    ):
        entry = _entry("New guidance paragraph")
        plan = skill.generate(
            entry,
            {
                "skill_name": "implementing",
                "section_heading": "### Step 1: Read Task List",
                "insertion_mode": "new-paragraph-after-heading",
            },
            plugin_root=plugin_root,
        )
        after = plan.edits[0].after
        # Heading still present, paragraph inserted after
        lines = after.splitlines()
        heading_idx = next(
            i for i, ln in enumerate(lines) if ln == "### Step 1: Read Task List"
        )
        # Within a few lines of the heading we should see the marker
        window = "\n".join(lines[heading_idx : heading_idx + 10])
        assert "<!-- Promoted: New guidance paragraph -->" in window

    def test_generate_rejects_invalid_meta(self, plugin_root: Path):
        entry = _entry()
        with pytest.raises(ValueError):
            skill.generate(
                entry,
                {
                    "skill_name": "nonesuch",
                    "section_heading": "### Foo",
                    "insertion_mode": "append-to-list",
                },
                plugin_root=plugin_root,
            )

    def test_before_matches_on_disk(self, plugin_root: Path):
        entry = _entry()
        plan = skill.generate(
            entry,
            {
                "skill_name": "implementing",
                "section_heading": "### Step 2: Per-Task Dispatch Loop",
                "insertion_mode": "append-to-list",
            },
            plugin_root=plugin_root,
        )
        edit = plan.edits[0]
        original = edit.path.read_text()
        assert edit.before == original
        assert edit.after != edit.before  # must have changed
