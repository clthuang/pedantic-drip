"""Shared dataclasses for the pattern_promotion package.

Per design I-6 / I-7 and the Subprocess Serialization Contract (TD-3):
these dataclasses are the single source of truth for subprocess payloads.
`Path` fields are coerced to `str(path)` before serialization by callers
using `json.dumps(..., default=str)`.

KBEntry lives in `kb_parser.py` per design C-3, not here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

TargetType = Literal["hook", "skill", "agent", "command"]
Action = Literal["create", "modify"]


@dataclass
class FileEdit:
    """A single file mutation within a DiffPlan.

    `write_order` is ascending (lower = earlier). Hook target convention:
    .sh=0, test-.sh=1, hooks.json=2 (must be last because it references paths).
    Rollback per edit: modify -> restore `before`; create -> unlink.
    """

    path: Path
    action: Action
    before: Optional[str]
    after: str
    write_order: int


@dataclass
class DiffPlan:
    """Output of a generator; sorted by write_order ascending.

    `target_path` is the primary file used for the KB marker. For hook target
    it is the .sh script; for skill/agent/command it is the modified file.
    """

    edits: list[FileEdit]
    target_type: TargetType
    target_path: Path


@dataclass
class Result:
    """Outcome of apply.apply().

    `stage_completed` is 0-5 (diagnostics). `target_path` is repo-relative
    when set so the KB marker is portable across clones.
    """

    success: bool
    target_path: Optional[Path]
    reason: Optional[str]
    rolled_back: bool
    stage_completed: int
