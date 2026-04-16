"""Command-target DiffPlan generator.

Per FR-3-command: candidate pool is `plugins/pd/commands/*.md`. Target
specification is `step_id` (e.g. `"5a"`, `"2b"`) which maps to a
`### Step {step_id}:` heading inside the command file — the established
convention across the pd command suite.

The generator reuses the shared `_md_insert` helper. The only command-specific
logic is resolving step_id → exact heading string by scanning heading lines
and matching the `### Step {step_id}:` prefix.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from pattern_promotion.inventory import list_commands
from pattern_promotion.types import DiffPlan, FileEdit

from ._md_insert import (
    InsertionMode,
    insert_block,
)


_VALID_MODES = {"append-to-list", "new-paragraph-after-heading"}
_REQUIRED_KEYS = ("command_name", "step_id", "insertion_mode")


def _command_path(plugin_root: Path, command_name: str) -> Path:
    return plugin_root / "commands" / f"{command_name}.md"


def _resolve_step_heading(text: str, step_id: str) -> Optional[str]:
    """Find a `### Step {step_id}:` heading in `text` and return it verbatim.

    Matches the step_id prefix case-sensitively and tolerates any suffix
    (step title). Returns the full heading line as it appears in the file,
    or None if no match.
    """
    pattern = re.compile(
        rf"^###\s+Step\s+{re.escape(step_id)}(?:\b|:).*$",
    )
    for ln in text.splitlines():
        if pattern.match(ln):
            return ln
    return None


def validate_target_meta(
    target_meta: dict, *, plugin_root: Optional[Path] = None
) -> tuple[bool, Optional[str]]:
    """Schema + existence check for command target_meta."""
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

    command_name = target_meta["command_name"]
    path = _command_path(plugin_root, command_name)
    if not path.is_file():
        return False, f"command {command_name!r} not found at {path}"
    try:
        known = set(list_commands(plugin_root=plugin_root))
    except FileNotFoundError:
        known = set()
    if known and command_name not in known:
        return False, f"command {command_name!r} not in inventory"

    text = path.read_text(encoding="utf-8")
    step_id = target_meta["step_id"]
    if _resolve_step_heading(text, step_id) is None:
        return (
            False,
            f"step {step_id!r} (### Step {step_id}:) not found in {path}",
        )

    return True, None


def generate(
    entry,
    target_meta: dict,
    *,
    plugin_root: Optional[Path] = None,
) -> DiffPlan:
    """Produce a 1-FileEdit DiffPlan modifying the target command .md file."""
    if plugin_root is None:
        plugin_root = Path("plugins/pd")

    ok, reason = validate_target_meta(target_meta, plugin_root=plugin_root)
    if not ok:
        raise ValueError(f"target_meta validation failed: {reason}")

    command_name = target_meta["command_name"]
    step_id = target_meta["step_id"]
    mode: InsertionMode = target_meta["insertion_mode"]

    path = _command_path(plugin_root, command_name)
    before = path.read_text(encoding="utf-8")
    heading = _resolve_step_heading(before, step_id)
    assert heading is not None  # validated above

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
        target_type="command",
        target_path=path,
    )
