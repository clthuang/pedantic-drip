"""Agent-target DiffPlan generator.

Mirror of `skill.py` but the candidate pool is `plugins/pd/agents/*.md`
(flat layout: one .md per agent, not a directory).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pattern_promotion.inventory import list_agents
from pattern_promotion.types import DiffPlan, FileEdit

from ._md_insert import (
    InsertionMode,
    find_heading_line,
    insert_block,
)


_VALID_MODES = {"append-to-list", "new-paragraph-after-heading"}
_REQUIRED_KEYS = ("agent_name", "section_heading", "insertion_mode")


def _agent_path(plugin_root: Path, agent_name: str) -> Path:
    return plugin_root / "agents" / f"{agent_name}.md"


def validate_target_meta(
    target_meta: dict, *, plugin_root: Optional[Path] = None
) -> tuple[bool, Optional[str]]:
    """Schema + existence check for agent target_meta."""
    if plugin_root is None:
        plugin_root = Path("plugins/pd")

    for key in _REQUIRED_KEYS:
        if key not in target_meta:
            return False, f"missing required key: {key!r}"

    mode = target_meta["insertion_mode"]
    if mode not in _VALID_MODES:
        return (
            False,
            f"insertion_mode {mode!r} must be one of {sorted(_VALID_MODES)}",
        )

    agent_name = target_meta["agent_name"]
    path = _agent_path(plugin_root, agent_name)
    if not path.is_file():
        return False, f"agent {agent_name!r} not found at {path}"
    try:
        known = set(list_agents(plugin_root=plugin_root))
    except FileNotFoundError:
        known = set()
    if known and agent_name not in known:
        return False, f"agent {agent_name!r} not in inventory"

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
    """Produce a 1-FileEdit DiffPlan modifying the target agent .md file."""
    if plugin_root is None:
        plugin_root = Path("plugins/pd")

    ok, reason = validate_target_meta(target_meta, plugin_root=plugin_root)
    if not ok:
        raise ValueError(f"target_meta validation failed: {reason}")

    agent_name = target_meta["agent_name"]
    heading = target_meta["section_heading"]
    mode: InsertionMode = target_meta["insertion_mode"]

    path = _agent_path(plugin_root, agent_name)
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
        target_type="agent",
        target_path=path,
    )
