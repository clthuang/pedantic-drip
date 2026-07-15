"""Unified per-kind transition registry (feature 123, design D1/D2/D6).

Single home for every machine-bearing kind's transition RULES: the router
composes the frozen engine's territory (feature), the 5D ordering rules
(initiative/objective/key_result/project/task), and the lifecycle graphs
(brainstorm/backlog) behind one registry. Dispatch stays the existing two
MCP surfaces, each consuming this registry (no new dispatch function):
transition_phase/complete_phase route feature kind to the frozen engine
unchanged and 5D kinds to ``get_machine(kind).validate(...)``; the moved
init_entity_workflow/transition_entity_phase below are the lifecycle-kind
entry points, and (feature 132 #075) transition_entity_phase ALSO routes
its transition check through ``get_machine(kind).validate(...)`` — one
enforcement route per kind, matching the 5D dispatch above.

Two roles a machine can implement (D1, B1 resolution):
  - ``GraphDescriptor`` (ALL machines): phases/is_forward/column_for — the
    role the SC1 diff harness enumerates.
  - ``validate(current, target, *, weight="standard") -> TransitionDecision``
    (FiveDMachine + LifecycleMachine ONLY — their validation is
    stateless-per-call). FeatureMachine is descriptor-ONLY: runtime
    feature validation remains the frozen engine's 4-gate chain, which
    needs per-feature state/artifacts/yolo the descriptor role can't
    carry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from entity_registry.database import EntityDatabase
from transition_gate import PHASE_SEQUENCE

from .templates import get_template

# Canonical feature phase sequence, string values (mirrors engine.py's own
# _PHASE_VALUES derivation — the ONLY enforced feature graph, D2.1;
# templates.py's feature rows are runtime-dead and excluded).
_PHASE_VALUES: tuple[str, ...] = tuple(p.value for p in PHASE_SEQUENCE)


@dataclass(frozen=True)
class TransitionDecision:
    """Frozen result of a machine's validate() call.

    Mirrors the existing gate-result shape (engine.py's ``_run_gate``
    results) so MCP serialization is unchanged when a caller adapts this
    into its own response shape.
    """

    allowed: bool
    reason: str
    severity: Literal["info", "warn", "error"]
    guard_id: str | None


@runtime_checkable
class GraphDescriptor(Protocol):
    """Role implemented by every machine (D1) — phase/forward/column
    introspection. This is what the SC1 diff harness enumerates."""

    def phases(self, weight: str = "standard") -> tuple[str, ...]:
        """Ordered phase names valid for this machine at ``weight``."""
        ...

    def is_forward(self, current: str | None, target: str) -> bool:
        """True when ``target`` is a forward move relative to ``current``."""
        ...

    def column_for(self, phase: str) -> str | None:
        """Kanban column for ``phase``, or None. Lifecycle kinds return
        their column; feature/5D return None (kanban derivation for
        those kinds is a separate, per-call-site stored-value producer
        since feature 132 D6.1-.3 retired the shared kanban.py module —
        not routed through this Protocol)."""
        ...


class FeatureMachine:
    """Feature-kind graph descriptor (D2.1). Weight-AGNOSTIC — wraps
    ``transition_gate.PHASE_SEQUENCE``, the only enforced feature graph;
    ``phases()`` returns the same 6-tuple regardless of ``weight`` (express
    variance is the skipped-events overlay, spec FR123-6, never a
    transition-graph variant). It does NOT consume templates.py (runtime-
    dead for features).

    Descriptor-ONLY: contributes no ``validate()``. Runtime feature
    validation remains the frozen engine's 4-gate chain (G-18/G-08/G-23/
    G-22), which needs last_completed_phase, completed_phases, the
    existing_artifacts filesystem scan, and yolo_active — state this
    descriptor role can't carry.
    """

    def phases(self, weight: str = "standard") -> tuple[str, ...]:
        return _PHASE_VALUES

    def is_forward(self, current: str | None, target: str) -> bool:
        if current is None:
            return True
        if current not in _PHASE_VALUES or target not in _PHASE_VALUES:
            return True
        return _PHASE_VALUES.index(target) > _PHASE_VALUES.index(current)

    def column_for(self, phase: str) -> str | None:
        return None


class FiveDMachine:
    """5D phase-sequence machine — one instance per kind (initiative/
    objective/key_result/project/task, D2.2). ``phases(weight)`` delegates
    to ``templates.get_template`` verbatim.

    ``validate()`` implements the former entity_engine.py hand-rolled
    ordering rules EXTRACTED (moved, not rewritten): unknown template ->
    blocked (guard TEMPLATE); target not in the phase list -> blocked
    (guard PHASE_SEQ); same-phase or +1 -> allowed; earlier -> allowed
    with a warning (guard G-18, matching the frozen engine's backward-warn
    shape); more than +1 -> blocked (guard PHASE_SEQ, skip).
    """

    def __init__(self, kind: str) -> None:
        self._kind = kind

    def phases(self, weight: str = "standard") -> tuple[str, ...]:
        return tuple(get_template(self._kind, weight))

    def is_forward(self, current: str | None, target: str) -> bool:
        if current is None:
            return True
        phases = self.phases()
        if current not in phases or target not in phases:
            return True
        return phases.index(target) > phases.index(current)

    def column_for(self, phase: str) -> str | None:
        return None

    def validate(
        self, current: str | None, target: str, *, weight: str = "standard",
    ) -> TransitionDecision:
        try:
            phases = self.phases(weight)
        except KeyError:
            return TransitionDecision(
                allowed=False,
                reason=f"No template for ({self._kind}, {weight})",
                severity="error",
                guard_id="TEMPLATE",
            )

        if target not in phases:
            return TransitionDecision(
                allowed=False,
                reason=f"Phase '{target}' not in sequence: {list(phases)}",
                severity="error",
                guard_id="PHASE_SEQ",
            )

        if current is not None and current in phases:
            current_idx = phases.index(current)
            target_idx = phases.index(target)
            if target_idx < current_idx:
                return TransitionDecision(
                    allowed=True,
                    reason=(
                        f"Backward transition from '{current}' to "
                        f"'{target}' (rework)"
                    ),
                    severity="warn",
                    guard_id="G-18",
                )
            if target_idx > current_idx + 1:
                return TransitionDecision(
                    allowed=False,
                    reason=f"Cannot skip from '{current}' to '{target}'",
                    severity="error",
                    guard_id="PHASE_SEQ",
                )

        return TransitionDecision(
            allowed=True,
            reason=f"Transitioned to {target}",
            severity="info",
            guard_id="PHASE_SEQ",
        )


# ---------------------------------------------------------------------------
# Entity lifecycle state machines — moved from entity_registry's former
# lifecycle module (feature 123 D6). Single registry keyed by entity_type.
# Each entry defines:
# valid transitions, phase-to-kanban-column mapping, and forward transition
# set (for last_completed_phase updates).
#
# FR123-4 (the one deliberate graph delta): brainstorm's reviewing phase
# maps to "wip" — the last live producer of the legacy column value
# retires (was CHECK-legal but off the v2 EXECUTION_STATUSES vocabulary;
# wip is both).
# ---------------------------------------------------------------------------

ENTITY_MACHINES: dict[str, dict] = {
    "brainstorm": {
        "transitions": {
            "draft": ["reviewing", "promoted", "abandoned"],
            "reviewing": ["promoted", "draft", "abandoned"],
        },
        "columns": {
            "draft": "wip",
            "reviewing": "wip",  # FR123-4: reviewing -> wip (retires the last legacy producer)
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


class LifecycleMachine:
    """Brainstorm/backlog lifecycle graph machine (D2.3) — one instance per
    kind. Carries the graph data in ``ENTITY_MACHINES`` above: transitions,
    forward set, and columns.

    ``validate()`` is plain graph membership (current in transitions,
    target in transitions[current]) — no gate IDs, matching the
    plain-ValueError posture of ``transition_entity_phase`` below; its
    failure ``reason`` text matches that function's error string.
    """

    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._machine = ENTITY_MACHINES[kind]

    def phases(self, weight: str = "standard") -> tuple[str, ...]:
        return tuple(self._machine["columns"])

    def is_forward(self, current: str | None, target: str) -> bool:
        if current is None:
            return True
        return (current, target) in self._machine["forward"]

    def column_for(self, phase: str) -> str | None:
        return self._machine["columns"].get(phase)

    def validate(
        self, current: str | None, target: str, *, weight: str = "standard",
    ) -> TransitionDecision:
        valid_targets = self._machine["transitions"].get(current, [])
        if target not in valid_targets:
            return TransitionDecision(
                allowed=False,
                reason=(
                    f"invalid_transition: cannot transition {self._kind} "
                    f"from {current} to {target}"
                ),
                severity="error",
                guard_id=None,
            )
        return TransitionDecision(
            allowed=True,
            reason=f"Transitioned to {target}",
            severity="info",
            guard_id=None,
        )


# Union of the three strategy classes — MACHINE_REGISTRY's value type (D1).
Machine = FeatureMachine | FiveDMachine | LifecycleMachine

# Kind -> machine instance. Keys are exactly the 8 machine-bearing kinds
# (spec FR123-1 table). ``bug`` is deliberately absent (status-only).
MACHINE_REGISTRY: dict[str, Machine] = {
    "feature": FeatureMachine(),
    "initiative": FiveDMachine("initiative"),
    "objective": FiveDMachine("objective"),
    "key_result": FiveDMachine("key_result"),
    "task": FiveDMachine("task"),
    "project": FiveDMachine("project"),
    "brainstorm": LifecycleMachine("brainstorm"),
    "backlog": LifecycleMachine("backlog"),
}


def get_machine(kind: str) -> Machine:
    """Return the transition machine for ``kind``.

    Raises ``ValueError`` for machine-less kinds (bug — status-only, spec
    FR123-5) and for any kind outside FR123-1's table (workspace, unknown
    values). Callers that special-case bug today keep doing so BEFORE
    routing — this function never silently no-ops.

        Role note: this method backs the Machine protocol and the SC1
        graph-diff harness, AND (feature 132 #075) is now the PRODUCTION
        enforcement route for lifecycle kinds too — the moved
        transition_entity_phase below calls ``get_machine(kind).validate()``
        instead of re-walking ENTITY_MACHINES inline, retiring the
        redundant duplicate the design D6 move originally left in place.
        """
    machine = MACHINE_REGISTRY.get(kind)
    if machine is None:
        raise ValueError(f"no transition machine for kind: {kind}")
    return machine


# ---------------------------------------------------------------------------
# Lifecycle entry points — moved from entity_registry's former lifecycle
# module (feature 123 D6). Bodies unchanged: ValueError strings, dict returns, and
# workspace_uuid kwargs are preserved exactly; ENTITY_MACHINES validation
# now reads the local dict above instead of an imported one.
# ---------------------------------------------------------------------------


def init_entity_workflow(
    db: EntityDatabase, type_id: str, workflow_phase: str, kanban_column: str,
    *,
    workspace_uuid: str | None = None,
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
        type_id, workflow_phase=workflow_phase, kanban_column=kanban_column,
        workspace_uuid=workspace_uuid,
    )
    return {
        "created": True,
        "type_id": type_id,
        "workflow_phase": workflow_phase,
        "kanban_column": kanban_column,
    }


def transition_entity_phase(
    db: EntityDatabase, type_id: str, target_phase: str,
    *,
    workspace_uuid: str | None = None,
) -> dict:
    """Transition a brainstorm/backlog entity to a new lifecycle phase.

    Preserves ALL behavior from _process_transition_entity_phase:
    - Transition graph validation via get_machine(kind).validate() (feature
      132 #075 — the former inline ENTITY_MACHINES re-walk is retired;
      LifecycleMachine.validate/column_for/is_forward read the SAME dict)
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

    # 2. Validate entity_type has a state machine (this endpoint is
    # lifecycle-kind-only — brainstorm/backlog; unlike get_machine(), which
    # would also resolve feature/5D kinds, ENTITY_MACHINES membership is
    # the correct gate here).
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

    # 5. Validate transition via the machine's own validate() (feature 132
    # #075: one enforcement route per kind, matching 123's 5D rewire —
    # the former inline ENTITY_MACHINES[entity_type]["transitions"] walk
    # duplicated exactly what LifecycleMachine.validate() already does).
    machine = get_machine(entity_type)
    decision = machine.validate(current_phase, target_phase)
    if not decision.allowed:
        raise ValueError(decision.reason)

    # 6. Look up target kanban column via the machine (not the raw dict).
    kanban_column = machine.column_for(target_phase)

    # 7. Determine if forward transition (for last_completed_phase), via
    # the machine (current_phase is validated non-None above, so this
    # matches the former inline tuple-membership check exactly).
    is_forward = machine.is_forward(current_phase, target_phase)

    # 8. Update entities.status via public API
    db.update_entity(type_id, status=target_phase, workspace_uuid=workspace_uuid)

    # 9. Update workflow_phases via public API.
    # workspace_uuid is unconditional; None is a no-op in update_workflow_phase.
    update_kwargs: dict = {
        "workflow_phase": target_phase,
        "kanban_column": kanban_column,
        "workspace_uuid": workspace_uuid,
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
