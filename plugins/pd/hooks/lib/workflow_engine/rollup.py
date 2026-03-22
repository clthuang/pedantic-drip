"""Progress rollup engine for parent-child entity hierarchies.

Computes parent progress from children's completed phases and propagates
up the ancestor chain.  Called by ``EntityWorkflowEngine.complete_phase()``
after a child entity completes a phase.

Also provides OKR-specific scoring for key_result entities (AC-32).

Implements design C5 (Progress Rollup Engine), plan Steps 3.2, 4.2, and 5.2.
"""
from __future__ import annotations

import json
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


def compute_traffic_light(progress: float) -> str:
    """Derive a traffic light colour from a progress value.

    Thresholds (per AC-27):
    - RED:    progress < 0.4
    - YELLOW: 0.4 <= progress < 0.7
    - GREEN:  progress >= 0.7

    Parameters
    ----------
    progress:
        Progress value in [0.0, 1.0].

    Returns
    -------
    str
        One of ``"RED"``, ``"YELLOW"``, or ``"GREEN"``.
    """
    if progress < 0.4:
        return "RED"
    if progress < 0.7:
        return "YELLOW"
    return "GREEN"


def compute_okr_score(db: "EntityDatabase", kr_uuid: str) -> float:
    """Compute and store the score for a key_result entity based on metric_type.

    Scoring rules (AC-32):
    - ``milestone``: completed_children / total_active_children
    - ``binary``: with children → 1.0 if ALL active children completed, else 0.0;
      without children → manual score from metadata (``score`` key)
    - ``baseline_target``: manual only, returns metadata ``score`` (default 0.0)
    - No metric_type or unrecognised → 0.0

    Stores the computed score in the KR entity's metadata (shallow merge).

    Parameters
    ----------
    db:
        EntityDatabase instance for data access.
    kr_uuid:
        UUID of the key_result entity to score.

    Returns
    -------
    float
        Score in [0.0, 1.0].
    """
    entity = db.get_entity_by_uuid(kr_uuid)
    if entity is None:
        return 0.0

    raw_meta = entity.get("metadata")
    if raw_meta and isinstance(raw_meta, str):
        meta = json.loads(raw_meta)
    elif isinstance(raw_meta, dict):
        meta = raw_meta
    else:
        meta = {}

    metric_type = meta.get("metric_type")
    if metric_type is None:
        return 0.0

    children = db.get_children_by_uuid(kr_uuid)

    if metric_type == "milestone":
        active = [c for c in children if c.get("status") != "abandoned"]
        if not active:
            return 0.0
        completed = sum(1 for c in active if c.get("status") == "completed")
        score = completed / len(active)

    elif metric_type == "binary":
        active = [c for c in children if c.get("status") != "abandoned"]
        if not active:
            # No children → manual score from metadata
            score = float(meta.get("score", 0.0))
        else:
            all_complete = all(c.get("status") == "completed" for c in active)
            score = 1.0 if all_complete else 0.0

    elif metric_type == "baseline_target":
        score = float(meta.get("score", 0.0))

    else:
        # Unrecognised metric_type → un-scored
        return 0.0

    # Store score in KR metadata
    db.update_entity(entity["type_id"], metadata={"score": score})
    return score


def compute_objective_score(db: "EntityDatabase", objective_uuid: str) -> float:
    """Compute and store the score for an objective entity from its child KR scores.

    The objective score is the weighted average of all non-abandoned child
    key_result scores (each computed via ``compute_okr_score``).  Non-KR
    children are ignored.

    Stores score + traffic_light in the objective's metadata.

    Implements AC-34 (OKR Progress Rollup).

    Parameters
    ----------
    db:
        EntityDatabase instance for data access.
    objective_uuid:
        UUID of the objective entity to score.

    Returns
    -------
    float
        Score in [0.0, 1.0].  Returns 0.0 if no active KR children.
    """
    entity = db.get_entity_by_uuid(objective_uuid)
    if entity is None:
        return 0.0

    children = db.get_children_by_uuid(objective_uuid)
    if not children:
        return 0.0

    # Filter to key_result children only, exclude abandoned
    kr_children = [
        c for c in children
        if c.get("entity_type") == "key_result"
        and c.get("status") != "abandoned"
    ]
    if not kr_children:
        return 0.0

    total = 0.0
    for kr in kr_children:
        total += compute_okr_score(db, kr["uuid"])

    score = total / len(kr_children)
    traffic_light = compute_traffic_light(score)

    db.update_entity(
        entity["type_id"],
        metadata={"score": score, "traffic_light": traffic_light},
    )
    return score


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
        traffic_light = compute_traffic_light(progress)
        db.update_entity(
            parent["type_id"],
            metadata={"progress": progress, "traffic_light": traffic_light},
        )

        parent_uuid = parent.get("parent_uuid")
        depth += 1
