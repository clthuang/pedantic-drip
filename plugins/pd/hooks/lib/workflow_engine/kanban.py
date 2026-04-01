"""Kanban column derivation from entity status and workflow phase.

Single source of truth for kanban_column values. Replaces the former
STATUS_TO_KANBAN and FEATURE_PHASE_TO_KANBAN scattered mappings.
"""
from __future__ import annotations

PHASE_TO_KANBAN: dict[str, str] = {
    # L3 feature phases (7-phase workflow)
    "brainstorm": "backlog",
    "specify": "backlog",
    "design": "prioritised",
    "create-plan": "prioritised",
    "implement": "wip",
    "finish": "documenting",
    # 5D phases (L1/L2/L4)
    "discover": "backlog",
    "define": "backlog",
    "deliver": "wip",
    "debrief": "documenting",
    # "design" is shared between both — already mapped above
}


def derive_kanban(status: str, workflow_phase: str | None) -> str:
    """Derive kanban column from entity status and current workflow phase.

    Priority order:
    1. Terminal statuses (completed, abandoned) -> "completed"
    2. Blocked status -> "blocked"
    3. Planned status -> "backlog"
    4. Phase-based lookup with "backlog" fallback
    """
    if status in ("completed", "abandoned"):
        return "completed"
    if status == "blocked":
        return "blocked"
    if status == "planned":
        return "backlog"
    return PHASE_TO_KANBAN.get(workflow_phase, "backlog")  # type: ignore[arg-type]
