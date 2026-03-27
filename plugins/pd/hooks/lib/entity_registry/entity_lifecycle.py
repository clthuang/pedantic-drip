"""Entity lifecycle state machine for brainstorm/backlog workflow phases.

Extracted from workflow_state_server.py _process_init_entity_workflow and
_process_transition_entity_phase. Preserves exact behavior — library functions
return dicts, callers serialize to JSON.
"""
from __future__ import annotations

from entity_registry.database import EntityDatabase

# ---------------------------------------------------------------------------
# Entity lifecycle state machines — exact copy from workflow_state_server.py
# lines 50-87. Single registry keyed by entity_type.
# Each entry defines: valid transitions, phase-to-kanban-column mapping,
# and forward transition set (for last_completed_phase updates).
# ---------------------------------------------------------------------------

ENTITY_MACHINES: dict[str, dict] = {
    "brainstorm": {
        "transitions": {
            "draft": ["reviewing", "promoted", "abandoned"],
            "reviewing": ["promoted", "draft", "abandoned"],
        },
        "columns": {
            "draft": "wip",
            "reviewing": "agent_review",
            "promoted": "completed",
            "abandoned": "completed",
        },
        "forward": {
            ("draft", "reviewing"),
            ("draft", "promoted"),
            ("reviewing", "promoted"),
            ("reviewing", "abandoned"),
            ("draft", "abandoned"),
        },
    },
    "backlog": {
        "transitions": {
            "open": ["triaged", "dropped"],
            "triaged": ["promoted", "dropped"],
        },
        "columns": {
            "open": "backlog",
            "triaged": "prioritised",
            "promoted": "completed",
            "dropped": "completed",
        },
        "forward": {
            ("open", "triaged"),
            ("triaged", "promoted"),
            ("triaged", "dropped"),
            ("open", "dropped"),
        },
    },
}


def init_entity_workflow(
    db: EntityDatabase, type_id: str, workflow_phase: str, kanban_column: str
) -> dict:
    """Create workflow_phases row for an entity. Idempotent.

    Preserves all validation from _process_init_entity_workflow:
    - Entity must exist in registry
    - feature/project types rejected (they use WorkflowStateEngine)
    - Phase/column validated against ENTITY_MACHINES when applicable
    - Idempotent: existing row returns with created=False

    Returns dict (caller serializes to JSON).
    Raises ValueError for validation failures.
    """
    # 1. Validate entity exists
    entity = db.get_entity(type_id)
    if entity is None:
        raise ValueError(f"entity_not_found: {type_id}")

    # 1b. Reject entity types with their own workflow management
    if ":" in type_id:
        entity_type = type_id.split(":", 1)[0]
        if entity_type in ("feature", "project"):
            raise ValueError(
                f"invalid_entity_type: {entity_type} entities use the feature workflow engine"
            )
        if entity_type in ENTITY_MACHINES:
            machine = ENTITY_MACHINES[entity_type]
            if workflow_phase not in machine["columns"]:
                raise ValueError(
                    f"invalid_transition: {workflow_phase} is not a valid phase for {entity_type}"
                )
            expected_column = machine["columns"][workflow_phase]
            if kanban_column != expected_column:
                raise ValueError(
                    f"invalid_transition: kanban_column {kanban_column} does not match "
                    f"expected {expected_column} for phase {workflow_phase}"
                )

    # 2. Check idempotency — existing row means no-op
    existing = db.get_workflow_phase(type_id)
    if existing:
        return {
            "created": False,
            "type_id": type_id,
            "workflow_phase": existing["workflow_phase"],
            "kanban_column": existing["kanban_column"],
            "reason": "already_exists",
        }

    # 3. Insert workflow_phases row via public API
    db.upsert_workflow_phase(
        type_id, workflow_phase=workflow_phase, kanban_column=kanban_column
    )
    return {
        "created": True,
        "type_id": type_id,
        "workflow_phase": workflow_phase,
        "kanban_column": kanban_column,
    }


def transition_entity_phase(
    db: EntityDatabase, type_id: str, target_phase: str
) -> dict:
    """Transition a brainstorm/backlog entity to a new lifecycle phase.

    Preserves ALL behavior from _process_transition_entity_phase:
    - Transition graph validation against ENTITY_MACHINES
    - Forward/backward distinction via 'forward' set
    - entities.status update via db.update_entity()
    - workflow_phases update: forward sets last_completed_phase, backward preserves it

    Returns dict (caller serializes to JSON).
    Raises ValueError for validation failures.
    """
    # 1. Parse entity_type
    if ":" not in type_id:
        raise ValueError(f"invalid_entity_type: malformed type_id: {type_id}")
    entity_type = type_id.split(":", 1)[0]

    # 2. Validate entity_type has a state machine
    if entity_type not in ENTITY_MACHINES:
        raise ValueError(
            f"invalid_entity_type: {entity_type} — only brainstorm and backlog supported"
        )

    # 3. Validate entity exists
    entity = db.get_entity(type_id)
    if entity is None:
        raise ValueError(f"entity_not_found: {type_id}")

    # 4. Get current phase via public API
    current_row = db.get_workflow_phase(type_id)
    if current_row is None:
        raise ValueError(f"entity_not_found: no workflow_phases row for {type_id}")
    current_phase = current_row.get("workflow_phase")
    if current_phase is None:
        raise ValueError(
            f"invalid_transition: {type_id} has NULL current_phase — "
            "call init_entity_workflow first"
        )

    # 5. Validate transition against graph
    machine = ENTITY_MACHINES[entity_type]
    valid_targets = machine["transitions"].get(current_phase, [])
    if target_phase not in valid_targets:
        raise ValueError(
            f"invalid_transition: cannot transition {entity_type} from "
            f"{current_phase} to {target_phase}"
        )

    # 6. Look up target kanban column
    kanban_column = machine["columns"][target_phase]

    # 7. Determine if forward transition (for last_completed_phase)
    is_forward = (current_phase, target_phase) in machine["forward"]

    # 8. Update entities.status via public API
    db.update_entity(type_id, status=target_phase)

    # 9. Update workflow_phases via public API
    update_kwargs: dict = {
        "workflow_phase": target_phase,
        "kanban_column": kanban_column,
    }
    if is_forward:
        update_kwargs["last_completed_phase"] = current_phase

    db.update_workflow_phase(type_id, **update_kwargs)

    return {
        "transitioned": True,
        "type_id": type_id,
        "from_phase": current_phase,
        "to_phase": target_phase,
        "kanban_column": kanban_column,
    }
