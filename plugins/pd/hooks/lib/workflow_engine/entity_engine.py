"""EntityWorkflowEngine -- strategy-pattern wrapper over frozen WorkflowStateEngine.

Adds cascade logic (unblock, rollup, notify) via two-phase commit:
  Phase A: Frozen engine auto-commits completion (or direct DB for tasks)
  Phase B: Separate BEGIN IMMEDIATE for cascade operations

Implements design D1 (Strategy Pattern), D2 (Cascade in Engine),
plan Step 3.3 [XC], AC-25.
"""
from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from entity_registry.database import EntityDatabase
from entity_registry.dependencies import DependencyManager

from .engine import WorkflowStateEngine
from .models import FeatureWorkflowState, TransitionResponse
from .notifications import Notification, NotificationQueue
from .rollup import compute_progress, rollup_parent
from .templates import get_template

if TYPE_CHECKING:
    pass


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

    Routes to FeatureBackend (frozen engine) or TaskBackend based on
    entity_type. Both paths run cascade in a separate transaction (Phase B).
    """

    def __init__(
        self,
        db: EntityDatabase,
        artifacts_root: str,
        notification_queue: NotificationQueue | None = None,
    ) -> None:
        self._db = db
        self._artifacts_root = artifacts_root
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

        # Phase A: completion
        if entity_type == "feature":
            state = self._feature_complete(type_id, phase)
        else:
            state = self._task_complete(entity, phase)

        # Phase B: cascade (separate transaction, idempotent)
        unblocked: list[str] = []
        parent_progress: float | None = None
        cascade_error: str | None = None

        # Skip cascade if DB is unhealthy (degraded mode)
        if state is not None and state.source == "meta_json_fallback":
            cascade_error = "cascade skipped: degraded mode"
        else:
            try:
                unblocked, parent_progress = self._run_cascade(entity_uuid)
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

        # Check blocked_by for all entity types
        blockers = self._dep_manager.get_blockers(self._db, entity_uuid)
        if blockers:
            raise ValueError(
                f"Entity {type_id} is blocked by {len(blockers)} "
                f"dependencies. Complete blockers first."
            )

        if entity_type == "feature":
            return self._frozen_engine.transition_phase(
                type_id, target_phase
            )

        # Task/5D entities: direct phase update
        return self._task_transition(entity, target_phase)

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
        return FeatureWorkflowState(
            feature_type_id=type_id,
            current_phase=row["workflow_phase"],
            last_completed_phase=row.get("last_completed_phase"),
            completed_phases=(),  # simplified for non-features
            mode=row.get("mode"),
            source="db",
        )

    # ------------------------------------------------------------------
    # Private: Feature backend (delegates to frozen engine)
    # ------------------------------------------------------------------

    def _feature_complete(
        self, type_id: str, phase: str
    ) -> FeatureWorkflowState:
        """Phase A for features: delegate to frozen engine (auto-commits)."""
        return self._frozen_engine.complete_phase(type_id, phase)

    # ------------------------------------------------------------------
    # Private: Task backend (direct DB)
    # ------------------------------------------------------------------

    def _task_complete(
        self, entity: dict, phase: str
    ) -> FeatureWorkflowState | None:
        """Phase A for tasks/5D entities: direct DB update."""
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

    def _task_transition(
        self, entity: dict, target_phase: str
    ) -> TransitionResponse:
        """Transition for task/5D entities: phase-sequence validation."""
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
                project_root="",  # filled by caller
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
                        project_root="",
                        timestamp=now,
                    )
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
