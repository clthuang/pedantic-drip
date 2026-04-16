"""Skill-target DiffPlan generator.

Per design C-6 / I-5 / FR-3-skill:

- `validate_target_meta(target_meta, *, plugin_root) -> (bool, Optional[str])`
  checks that the named skill exists (a `plugins/pd/skills/{name}/SKILL.md`
  file), the target heading exists in that file, and the insertion mode is
  one of the two supported modes.

- `generate(entry, target_meta, *, plugin_root) -> DiffPlan` produces a
  single `modify` FileEdit on the target SKILL.md, inserting a TD-8-marked
  block under the specified heading.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pattern_promotion.inventory import list_skills
from pattern_promotion.types import DiffPlan, FileEdit

from ._md_insert import (
    InsertionMode,
    find_heading_line,
    insert_block,
)


_VALID_MODES = {"append-to-list", "new-paragraph-after-heading"}
_REQUIRED_KEYS = ("skill_name", "section_heading", "insertion_mode")


def _skill_path(plugin_root: Path, skill_name: str) -> Path:
    return plugin_root / "skills" / skill_name / "SKILL.md"


def validate_target_meta(
    target_meta: dict, *, plugin_root: Optional[Path] = None
) -> tuple[bool, Optional[str]]:
    """Schema + existence check for skill target_meta."""
    if plugin_root is None:
        plugin_root = Path("plugins/pd")

    for key in _REQUIRED_KEYS:
        if key not in target_meta:
            return False, f"missing required key: {key!r}"

    insertion_mode = target_meta["insertion_mode"]
    if insertion_mode not in _VALID_MODES:
        return (
            False,
            f"insertion_mode {insertion_mode!r} must be one of {sorted(_VALID_MODES)}",
        )

    skill_name = target_meta["skill_name"]
    # Cheap existence check first (direct file), then confirm it's in the
    # discovered inventory (consistency with the rest of the pipeline).
    path = _skill_path(plugin_root, skill_name)
    if not path.is_file():
        return False, f"skill {skill_name!r} not found at {path}"
    try:
        known = set(list_skills(plugin_root=plugin_root))
    except FileNotFoundError:
        known = set()
    if known and skill_name not in known:
        return False, f"skill {skill_name!r} not in inventory"

    text = path.read_text(encoding="utf-8")
    if find_heading_line(text, target_meta["section_heading"]) is None:
        return (
            False,
            f"heading {target_meta['section_heading']!r} not found in {path}",
        )

    return True, None


def generate(
    entry,
    target_meta: dict,
    *,
    plugin_root: Optional[Path] = None,
) -> DiffPlan:
    """Produce a 1-FileEdit DiffPlan modifying the target SKILL.md."""
    if plugin_root is None:
        plugin_root = Path("plugins/pd")

    ok, reason = validate_target_meta(target_meta, plugin_root=plugin_root)
    if not ok:
        raise ValueError(f"target_meta validation failed: {reason}")

    skill_name = target_meta["skill_name"]
    heading = target_meta["section_heading"]
    mode: InsertionMode = target_meta["insertion_mode"]

    path = _skill_path(plugin_root, skill_name)
    before = path.read_text(encoding="utf-8")
    after = insert_block(
        before,
        heading=heading,
        mode=mode,
        entry_name=entry.name,
        description=entry.description,
    )

    edit = FileEdit(
        path=path,
        action="modify",
        before=before,
        after=after,
        write_order=0,
    )

    return DiffPlan(
        edits=[edit],
        target_type="skill",
        target_path=path,
    )
