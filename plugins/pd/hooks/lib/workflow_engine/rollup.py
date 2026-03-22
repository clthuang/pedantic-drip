"""Progress rollup engine for parent-child entity hierarchies.

Computes parent progress from children's completed phases and propagates
up the ancestor chain.  Called by ``EntityWorkflowEngine.complete_phase()``
after a child entity completes a phase.

Implements design C5 (Progress Rollup Engine) and plan Step 3.2.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entity_registry.database import EntityDatabase

# Progress weight per 7-phase name.
# Value represents how far along a child is when it is currently IN that phase.
# "brainstorm" = 0.0 (just started), "finish" = 0.9 (nearly done).
# A completed child contributes 1.0.
PHASE_WEIGHTS_7: dict[str, float] = {
    "brainstorm": 0.0,
    "specify": 0.1,
    "design": 0.3,
    "create-plan": 0.3,
    "create-tasks": 0.3,
    "implement": 0.7,
    "finish": 0.9,
}

# Progress weight per 5D phase name.
PHASE_WEIGHTS_5D: dict[str, float] = {
    "discover": 0.0,
    "define": 0.1,
    "design": 0.3,
    "deliver": 0.7,
    "debrief": 0.9,
}

# Maximum ancestor depth to prevent infinite loops on malformed data.
_MAX_DEPTH = 5


def _get_workflow_phase(db: "EntityDatabase", type_id: str) -> str | None:
    """Look up the current workflow_phase for an entity."""
    wp = db.get_workflow_phase(type_id)
    if wp is None:
        return None
    return wp.get("workflow_phase")


def compute_progress(db: "EntityDatabase", entity_uuid: str) -> float:
    """Compute progress (0.0-1.0) for an entity from its children.

    Each non-abandoned child contributes its phase-based progress weight
    (0.0 to 1.0).  Completed children contribute 1.0.  Abandoned children
    are excluded entirely (from both numerator and denominator).

    Parameters
    ----------
    db:
        EntityDatabase instance for data access.
    entity_uuid:
        UUID of the parent entity whose progress to compute.

    Returns
    -------
    float
        Progress value in [0.0, 1.0].  Returns 0.0 if no active children.
    """
    children = db.get_children_by_uuid(entity_uuid)
    if not children:
        return 0.0

    total = 0.0
    active_count = 0

    for child in children:
        status = child.get("status")
        if status == "abandoned":
            continue  # excluded from both numerator and denominator

        active_count += 1

        if status == "completed":
            total += 1.0
        else:
            # Determine weight table based on entity type
            entity_type = child.get("entity_type", "")
            if entity_type == "feature":
                weights = PHASE_WEIGHTS_7
            else:
                weights = PHASE_WEIGHTS_5D

            # Look up current workflow phase
            phase = _get_workflow_phase(db, child["type_id"])
            total += weights.get(phase, 0.0) if phase else 0.0

    return total / active_count if active_count > 0 else 0.0


def rollup_parent(db: "EntityDatabase", child_uuid: str) -> None:
    """Walk up the parent chain and recompute progress for each ancestor.

    Starting from the child's parent, recomputes progress at each level
    and stores it in the entity's metadata (shallow-merged via
    ``update_entity``).  Stops when there is no parent or max depth
    (5 levels) is reached.

    Parameters
    ----------
    db:
        EntityDatabase instance for data access.
    child_uuid:
        UUID of the child entity that triggered the rollup.

    Notes
    -----
    This is a no-op if the child has no parent.

    ``update_entity()`` with ``metadata`` kwarg performs a dict MERGE
    (not replace) -- existing metadata keys are preserved, only provided
    keys are updated.
    """
    entity = db.get_entity_by_uuid(child_uuid)
    if entity is None:
        return

    parent_uuid = entity.get("parent_uuid")
    depth = 0

    while parent_uuid and depth < _MAX_DEPTH:
        parent = db.get_entity_by_uuid(parent_uuid)
        if parent is None:
            break

        progress = compute_progress(db, parent_uuid)
        db.update_entity(parent["type_id"], metadata={"progress": progress})

        parent_uuid = parent.get("parent_uuid")
        depth += 1
