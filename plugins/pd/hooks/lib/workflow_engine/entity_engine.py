"""EntityWorkflowEngine -- strategy-pattern wrapper over frozen WorkflowStateEngine.

Adds cascade logic (unblock, rollup, notify) via two-phase commit:
  Phase A: Frozen engine auto-commits completion (or direct DB for tasks/5D)
  Phase B: Separate BEGIN IMMEDIATE for cascade operations

Backends:
  FeatureBackend — delegates to frozen WorkflowStateEngine (L3 features)
  FiveDBackend   — 5D phase-sequence transitions for L1/L2/L4 entities
                   (initiative, objective, key_result, project, task)

Implements design D1 (Strategy Pattern), D2 (Cascade in Engine), C3,
plan Steps 3.3/4.1/4.3/4.4/6.1, AC-25/AC-26/AC-28/AC-29/AC-30/AC-35.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from entity_registry.database import EntityDatabase
from entity_registry.dependencies import DependencyManager

from .engine import WorkflowStateEngine
from .models import FeatureWorkflowState, TransitionResponse
from .notifications import Notification, NotificationQueue
from .rollup import compute_progress, rollup_parent
from .templates import get_template



# 5D entity types use phase-sequence-only transitions (no artifact prereqs).
# Features use the frozen WorkflowStateEngine with full guard model.
FIVE_D_ENTITY_TYPES: frozenset[str] = frozenset(
    {"initiative", "objective", "key_result", "project", "task"}
)

# Deliver-phase mapping: the phase where blocked_by is enforced.
# Features use "implement", 5D entities use "deliver".
_DELIVER_PHASE: dict[str, str] = {
    "feature": "implement",
}
_FIVE_D_DELIVER_PHASE = "deliver"


@dataclass(frozen=True)
class CompletionResult:
    """Wraps phase completion state with cascade outcomes.

    Attributes
    ----------
    state:
        The FeatureWorkflowState after completion (features) or None (tasks).
    entity_type:
        The type of entity that was completed.
    entity_uuid:
        UUID of the completed entity.
    phase:
        The phase that was completed.
    unblocked_uuids:
        UUIDs of entities unblocked by cascade.
    parent_progress:
        Updated parent progress value (None if no parent or cascade skipped).
    cascade_error:
        Error message if cascade failed (completion still persists).
    """

    state: FeatureWorkflowState | None
    entity_type: str
    entity_uuid: str
    phase: str
    unblocked_uuids: list[str] = field(default_factory=list)
    parent_progress: float | None = None
    cascade_error: str | None = None


class EntityWorkflowEngine:
    """Strategy-pattern orchestrator wrapping frozen WorkflowStateEngine.

    Routes to FeatureBackend (frozen engine) or FiveDBackend (direct DB)
    based on entity_type. Both paths run cascade in a separate transaction
    (Phase B).

    FeatureBackend: L3 features — full guard model via frozen engine.
    FiveDBackend:   L1/L2/L4 — phase-sequence-only, blocked_by at deliver.
    """

    # Shared constant with frozen engine for degraded mode detection
    _SOURCE_DEGRADED = "meta_json_fallback"

    def __init__(
        self,
        db: EntityDatabase,
        artifacts_root: str,
        notification_queue: NotificationQueue | None = None,
        project_root: str = "",
    ) -> None:
        self._db = db
        self._artifacts_root = artifacts_root
        self._project_root = project_root
        self._frozen_engine = WorkflowStateEngine(db, artifacts_root)
        self._dep_manager = DependencyManager()
        self._notification_queue = notification_queue

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def complete_phase(
        self, entity_uuid: str, phase: str
    ) -> CompletionResult:
        """Complete a phase for any entity type.

        Two-phase commit:
          Phase A: Completion (frozen engine for features, direct DB for tasks)
          Phase B: Cascade (unblock + rollup + notify) in separate transaction

        Parameters
        ----------
        entity_uuid:
            UUID of the entity.
        phase:
            Phase name to mark as completed.

        Returns
        -------
        CompletionResult
            Completion state plus cascade outcomes.

        Raises
        ------
        ValueError
            If entity not found or phase invalid.
        """
        entity = self._db.get_entity_by_uuid(entity_uuid)
        if entity is None:
            raise ValueError(f"Entity not found: {entity_uuid}")

        entity_type = entity["entity_type"]
        type_id = entity["type_id"]

        # Phase A: completion — route by backend
        if entity_type == "feature":
            state = self._feature_complete(type_id, phase)
        elif entity_type in FIVE_D_ENTITY_TYPES:
            state = self._fived_complete(entity, phase)
        else:
            raise ValueError(f"Unsupported entity type: {entity_type}")

        # Phase B: cascade (separate transaction, idempotent)
        unblocked: list[str] = []
        parent_progress: float | None = None
        cascade_error: str | None = None

        # Skip cascade if DB is unhealthy (degraded mode)
        if state is not None and state.source == self._SOURCE_DEGRADED:
            cascade_error = "cascade skipped: degraded mode"
        else:
            try:
                unblocked, parent_progress = self._run_cascade(entity_uuid)
                # Anomaly propagation: on terminal phase, check for
                # systemic_finding and propagate to parent (AC-35 / Task 6.1)
                self._propagate_anomaly(entity_uuid, entity_type, phase)
            except Exception as exc:
                cascade_error = str(exc)
                print(
                    f"entity-engine: cascade failed for {entity_uuid}: {exc}",
                    file=sys.stderr,
                )

        return CompletionResult(
            state=state,
            entity_type=entity_type,
            entity_uuid=entity_uuid,
            phase=phase,
            unblocked_uuids=unblocked,
            parent_progress=parent_progress,
            cascade_error=cascade_error,
        )

    def transition_phase(
        self, entity_uuid: str, target_phase: str
    ) -> TransitionResponse:
        """Transition an entity to a target phase.

        For features: delegates to frozen engine after checking blocked_by.
        For tasks: direct phase update.

        Parameters
        ----------
        entity_uuid:
            UUID of the entity.
        target_phase:
            Target phase to transition to.

        Returns
        -------
        TransitionResponse

        Raises
        ------
        ValueError
            If entity not found, blocked, or transition invalid.
        """
        entity = self._db.get_entity_by_uuid(entity_uuid)
        if entity is None:
            raise ValueError(f"Entity not found: {entity_uuid}")

        entity_type = entity["entity_type"]
        type_id = entity["type_id"]

        # Check blocked_by at deliver phase (implement for features,
        # deliver for 5D entities). Per design C3/AC-28.
        deliver_phase = _DELIVER_PHASE.get(
            entity_type, _FIVE_D_DELIVER_PHASE
        )
        if target_phase == deliver_phase:
            blockers = self._dep_manager.get_blockers(
                self._db, entity_uuid
            )
            if blockers:
                blocker_names = []
                for b_uuid in blockers:
                    b_entity = self._db.get_entity_by_uuid(b_uuid)
                    if b_entity:
                        blocker_names.append(b_entity["type_id"])
                    else:
                        blocker_names.append(b_uuid)
                raise ValueError(
                    f"Entity {type_id} is blocked by: "
                    f"{', '.join(blocker_names)}"
                )

        if entity_type == "feature":
            return self._frozen_engine.transition_phase(
                type_id, target_phase
            )

        if entity_type in FIVE_D_ENTITY_TYPES:
            return self._fived_transition(entity, target_phase)

        raise ValueError(f"Unsupported entity type: {entity_type}")

    def get_state(
        self, entity_uuid: str
    ) -> FeatureWorkflowState | None:
        """Get workflow state for any entity.

        For features: delegates to frozen engine.
        For other types: builds state from DB row.
        """
        entity = self._db.get_entity_by_uuid(entity_uuid)
        if entity is None:
            return None

        entity_type = entity["entity_type"]
        type_id = entity["type_id"]

        if entity_type == "feature":
            return self._frozen_engine.get_state(type_id)

        # Non-feature: build from workflow_phases row
        row = self._db.get_workflow_phase(type_id)
        if row is None:
            return None

        # Derive completed_phases from template (same logic as frozen engine)
        last_completed = row.get("last_completed_phase")
        completed_phases: tuple[str, ...] = ()
        if last_completed:
            weight = row.get("mode") or "standard"
            try:
                template = get_template(entity_type, weight)
                if last_completed in template:
                    idx = template.index(last_completed)
                    completed_phases = tuple(template[: idx + 1])
            except KeyError:
                pass  # unknown template — leave empty

        return FeatureWorkflowState(
            feature_type_id=type_id,
            current_phase=row["workflow_phase"],
            last_completed_phase=last_completed,
            completed_phases=completed_phases,
            mode=row.get("mode"),
            source="db",
        )

    def abandon_entity(
        self, entity_uuid: str, *, cascade: bool = False
    ) -> list[str]:
        """Abandon an entity, with orphan guard.

        Checks for active children (status not completed/abandoned).
        If active children exist and cascade is False, raises ValueError
        listing the active children (orphan guard).

        Parameters
        ----------
        entity_uuid:
            UUID of the entity to abandon.
        cascade:
            If True, abandon all active descendants recursively.
            If False (default), reject if active children exist.

        Returns
        -------
        list[str]
            UUIDs of all entities abandoned (including the target).

        Raises
        ------
        ValueError
            If entity not found, or active children exist and cascade=False.
        """
        entity = self._db.get_entity_by_uuid(entity_uuid)
        if entity is None:
            raise ValueError(f"Entity not found: {entity_uuid}")

        active_children = self._get_active_children(entity_uuid)

        if active_children and not cascade:
            child_names = [
                c["type_id"] for c in active_children
            ]
            raise ValueError(
                f"Cannot abandon {entity['type_id']}: "
                f"{len(active_children)} active children: "
                f"{', '.join(child_names)}"
            )

        abandoned: list[str] = []

        if cascade and active_children:
            # Walk tree depth-first, abandon all active descendants
            abandoned = self._abandon_descendants(entity_uuid)

        # Abandon the entity itself
        self._db.update_entity(entity["type_id"], status="abandoned")
        abandoned.append(entity_uuid)

        return abandoned

    def _get_active_children(self, parent_uuid: str) -> list[dict]:
        """Return children that are not completed or abandoned."""
        children = self._db.get_children_by_uuid(parent_uuid)
        return [
            c for c in children
            if c.get("status") not in ("completed", "abandoned")
        ]

    def _abandon_descendants(self, parent_uuid: str) -> list[str]:
        """Recursively abandon all active descendants depth-first.

        Returns list of UUIDs abandoned (excluding the parent itself).
        """
        abandoned: list[str] = []
        children = self._db.get_children_by_uuid(parent_uuid)
        for child in children:
            if child.get("status") in ("completed", "abandoned"):
                continue
            # Recurse into grandchildren first
            abandoned.extend(
                self._abandon_descendants(child["uuid"])
            )
            self._db.update_entity(child["type_id"], status="abandoned")
            abandoned.append(child["uuid"])
        return abandoned

    # ------------------------------------------------------------------
    # Private: Feature backend (delegates to frozen engine)
    # ------------------------------------------------------------------

    def _feature_complete(
        self, type_id: str, phase: str
    ) -> FeatureWorkflowState:
        """Phase A for features: delegate to frozen engine (auto-commits)."""
        return self._frozen_engine.complete_phase(type_id, phase)

    # ------------------------------------------------------------------
    # Private: FiveDBackend (direct DB — tasks, projects, initiatives, etc.)
    # ------------------------------------------------------------------

    def _fived_complete(
        self, entity: dict, phase: str
    ) -> FeatureWorkflowState | None:
        """Phase A for 5D entities: direct DB update."""
        type_id = entity["type_id"]
        entity_type = entity["entity_type"]
        weight = self._get_weight(type_id)

        try:
            phases = get_template(entity_type, weight)
        except KeyError:
            raise ValueError(
                f"No template for ({entity_type}, {weight})"
            ) from None

        if phase not in phases:
            raise ValueError(
                f"Phase '{phase}' not in template for "
                f"({entity_type}, {weight}): {phases}"
            )

        phase_idx = phases.index(phase)

        # Validate phase: allow current phase OR backward re-run (rework),
        # reject forward skip. Matches frozen engine behavior (engine.py:134-147).
        wf_row = self._db.get_workflow_phase(type_id)
        current_phase = wf_row["workflow_phase"] if wf_row else None
        if current_phase and phase != current_phase:
            last_completed = wf_row.get("last_completed_phase") if wf_row else None
            if last_completed is None:
                raise ValueError(
                    f"Phase mismatch: cannot complete '{phase}' when current "
                    f"phase is '{current_phase}' and no phases completed yet "
                    f"for {type_id}"
                )
            last_idx = phases.index(last_completed) if last_completed in phases else -1
            if phase_idx > last_idx:
                raise ValueError(
                    f"Phase mismatch: cannot complete '{phase}' when current "
                    f"phase is '{current_phase}' for {type_id}"
                )
            # Backward re-run is valid (rework cycle) — continue
        is_terminal = phase_idx == len(phases) - 1
        next_phase = phase if is_terminal else phases[phase_idx + 1]

        try:
            self._db.update_workflow_phase(
                type_id,
                last_completed_phase=phase,
                workflow_phase=next_phase,
            )
            if is_terminal:
                self._db.update_entity(type_id, status="completed")
        except sqlite3.Error as exc:
            print(
                f"entity-engine: DB write failed for task {type_id}: {exc}",
                file=sys.stderr,
            )
            return None

        return FeatureWorkflowState(
            feature_type_id=type_id,
            current_phase=next_phase,
            last_completed_phase=phase,
            completed_phases=tuple(phases[: phase_idx + 1]),
            mode=weight,
            source="db",
        )

    def _fived_transition(
        self, entity: dict, target_phase: str
    ) -> TransitionResponse:
        """Transition for 5D entities: phase-sequence validation."""
        from transition_gate.models import Severity, TransitionResult

        type_id = entity["type_id"]
        entity_type = entity["entity_type"]
        weight = self._get_weight(type_id)

        try:
            phases = get_template(entity_type, weight)
        except KeyError:
            return TransitionResponse(
                results=(
                    TransitionResult(
                        guard_id="TEMPLATE",
                        allowed=False,
                        reason=f"No template for ({entity_type}, {weight})",
                        severity=Severity.block,
                    ),
                ),
                degraded=False,
            )

        if target_phase not in phases:
            return TransitionResponse(
                results=(
                    TransitionResult(
                        guard_id="PHASE_SEQ",
                        allowed=False,
                        reason=(
                            f"Phase '{target_phase}' not in sequence: {phases}"
                        ),
                        severity=Severity.block,
                    ),
                ),
                degraded=False,
            )

        # Validate ordering: target must be current or next
        row = self._db.get_workflow_phase(type_id)
        if row is not None:
            current = row["workflow_phase"]
            if current is not None and current in phases:
                current_idx = phases.index(current)
                target_idx = phases.index(target_phase)
                if target_idx < current_idx:
                    # Backward transition allowed (rework) — warn only,
                    # matching frozen engine's check_backward_transition (G-18)
                    return TransitionResponse(
                        results=(
                            TransitionResult(
                                guard_id="G-18",
                                allowed=True,
                                reason=(
                                    f"Backward transition from '{current}' to "
                                    f"'{target_phase}' (rework)"
                                ),
                                severity=Severity.warn,
                            ),
                        ),
                        degraded=False,
                    )
                if target_idx > current_idx + 1:
                    return TransitionResponse(
                        results=(
                            TransitionResult(
                                guard_id="PHASE_SEQ",
                                allowed=False,
                                reason=(
                                    f"Cannot skip from '{current}' to "
                                    f"'{target_phase}'"
                                ),
                                severity=Severity.block,
                            ),
                        ),
                        degraded=False,
                    )

        try:
            self._db.update_workflow_phase(
                type_id, workflow_phase=target_phase
            )
        except sqlite3.Error as exc:
            print(
                f"entity-engine: DB write failed for {type_id}: {exc}",
                file=sys.stderr,
            )
            return TransitionResponse(
                results=(
                    TransitionResult(
                        guard_id="DB_ERROR",
                        allowed=False,
                        reason=str(exc),
                        severity=Severity.block,
                    ),
                ),
                degraded=True,
            )

        return TransitionResponse(
            results=(
                TransitionResult(
                    guard_id="PHASE_SEQ",
                    allowed=True,
                    reason=f"Transitioned to {target_phase}",
                    severity=Severity.info,
                ),
            ),
            degraded=False,
        )

    # ------------------------------------------------------------------
    # Private: Cascade (Phase B)
    # ------------------------------------------------------------------

    def _run_cascade(
        self, entity_uuid: str
    ) -> tuple[list[str], float | None]:
        """Run cascade in a separate transaction.

        1. cascade_unblock — remove completed entity from blocked_by lists
        2. rollup_parent — recompute parent progress up ancestor chain
        3. notification push (if queue available)

        Returns (unblocked_uuids, parent_progress).
        """
        unblocked: list[str] = []
        parent_progress: float | None = None

        # cascade_unblock already commits internally, so we call it directly
        unblocked = self._dep_manager.cascade_unblock(
            self._db, entity_uuid
        )

        # rollup_parent also commits internally via update_entity
        rollup_parent(self._db, entity_uuid)

        # Compute parent progress for the result
        entity = self._db.get_entity_by_uuid(entity_uuid)
        if entity is not None:
            parent_uuid = entity.get("parent_uuid")
            if parent_uuid is not None:
                parent_progress = compute_progress(self._db, parent_uuid)

        # Notification push (optional, after DB commits)
        if self._notification_queue is not None:
            self._push_notifications(entity_uuid, unblocked)

        return unblocked, parent_progress

    def _push_notifications(
        self, entity_uuid: str, unblocked: list[str]
    ) -> None:
        """Push notifications for completion and unblock events."""
        from datetime import datetime, timezone

        entity = self._db.get_entity_by_uuid(entity_uuid)
        if entity is None:
            return

        now = datetime.now(timezone.utc).isoformat()

        self._notification_queue.push(
            Notification(
                message=f"Phase completed for {entity['type_id']}",
                entity_type_id=entity["type_id"],
                event="phase_completed",
                project_root=self._project_root,
                timestamp=now,
            )
        )

        for uid in unblocked:
            unblocked_entity = self._db.get_entity_by_uuid(uid)
            if unblocked_entity is not None:
                self._notification_queue.push(
                    Notification(
                        message=(
                            f"Entity {unblocked_entity['type_id']} unblocked"
                        ),
                        entity_type_id=unblocked_entity["type_id"],
                        event="unblocked",
                        project_root=self._project_root,
                        timestamp=now,
                    )
                )

    # ------------------------------------------------------------------
    # Private: Anomaly propagation (Task 6.1 / AC-35)
    # ------------------------------------------------------------------

    def _propagate_anomaly(
        self, entity_uuid: str, entity_type: str, phase: str
    ) -> None:
        """Propagate systemic_finding to parent metadata on terminal phase.

        On terminal phase completion (last phase in the entity's template),
        checks if entity metadata contains a truthy ``systemic_finding``.
        If so, appends an anomaly record to the parent entity's metadata
        ``anomalies`` list.

        No-op if: phase is not terminal, no systemic_finding, or no parent.
        """
        # Determine if this phase is terminal for the entity type
        entity = self._db.get_entity_by_uuid(entity_uuid)
        if entity is None:
            return

        weight = self._get_weight(entity["type_id"])
        try:
            phases = get_template(entity_type, weight)
        except KeyError:
            return  # unknown template — skip

        if phase != phases[-1]:
            return  # not terminal phase

        # Check for systemic_finding in entity metadata
        raw_meta = entity.get("metadata")
        if not raw_meta:
            return
        if isinstance(raw_meta, str):
            meta = json.loads(raw_meta)
        elif isinstance(raw_meta, dict):
            meta = raw_meta
        else:
            return

        finding = meta.get("systemic_finding")
        if not finding:
            return

        # Check for parent
        parent_uuid = entity.get("parent_uuid")
        if not parent_uuid:
            return

        parent = self._db.get_entity_by_uuid(parent_uuid)
        if parent is None:
            return

        # Build anomaly record
        anomaly = {
            "description": finding,
            "source_type_id": entity["type_id"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Read existing parent anomalies
        parent_raw_meta = parent.get("metadata")
        if parent_raw_meta and isinstance(parent_raw_meta, str):
            parent_meta = json.loads(parent_raw_meta)
        elif isinstance(parent_raw_meta, dict):
            parent_meta = parent_raw_meta
        else:
            parent_meta = {}

        existing_anomalies = parent_meta.get("anomalies", [])
        existing_anomalies.append(anomaly)

        # Write back via update_entity (shallow merge)
        self._db.update_entity(
            parent["type_id"],
            metadata={"anomalies": existing_anomalies},
        )

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _get_weight(self, type_id: str) -> str:
        """Get the weight/mode for an entity from its workflow_phases row."""
        row = self._db.get_workflow_phase(type_id)
        if row is not None and row.get("mode"):
            return row["mode"]
        return "standard"  # default weight
