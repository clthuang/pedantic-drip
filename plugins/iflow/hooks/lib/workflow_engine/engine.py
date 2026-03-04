"""WorkflowStateEngine -- stateless orchestrator for workflow phase transitions."""
from __future__ import annotations

import json
import os
from typing import ClassVar

from entity_registry.database import EntityDatabase
from transition_gate import (
    PHASE_SEQUENCE,
    TransitionResult,
    check_backward_transition,
    check_hard_prerequisites,
    check_soft_prerequisites,
    check_yolo_override,
    validate_transition,
)
from transition_gate.constants import HARD_PREREQUISITES

from .models import FeatureWorkflowState


class WorkflowStateEngine:
    """Stateless orchestrator -- no mutable instance state beyond constructor refs."""

    _GATE_GUARD_IDS: ClassVar[dict[str, str]] = {
        "check_backward_transition": "G-18",
        "check_hard_prerequisites": "G-08",
        "check_soft_prerequisites": "G-23",
        "validate_transition": "G-22",
    }

    def __init__(self, db: EntityDatabase, artifacts_root: str) -> None:
        """Store references only. No DB calls, no I/O."""
        self.db = db
        self.artifacts_root = artifacts_root

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_state(self, feature_type_id: str) -> FeatureWorkflowState | None:
        """Read feature workflow state from DB, falling back to .meta.json hydration."""
        row = self.db.get_workflow_phase(feature_type_id)
        if row is not None:
            return FeatureWorkflowState(
                feature_type_id=row["type_id"],
                current_phase=row["workflow_phase"],
                last_completed_phase=row["last_completed_phase"],
                completed_phases=self._derive_completed_phases(
                    row["last_completed_phase"]
                ),
                mode=row["mode"],
                source="db",
            )
        return self._hydrate_from_meta_json(feature_type_id)

    def transition_phase(
        self,
        feature_type_id: str,
        target_phase: str,
        yolo_active: bool = False,
    ) -> list[TransitionResult]:
        """Validate and enter a target phase."""
        state = self.get_state(feature_type_id)
        if state is None:
            raise ValueError(f"Feature not found: {feature_type_id}")

        slug = self._extract_slug(feature_type_id)
        existing_artifacts = self._get_existing_artifacts(slug)
        results = self._evaluate_gates(state, target_phase, existing_artifacts, yolo_active)

        if all(r.allowed for r in results):
            self.db.update_workflow_phase(
                feature_type_id, workflow_phase=target_phase
            )

        return results

    def complete_phase(
        self, feature_type_id: str, phase: str
    ) -> FeatureWorkflowState:
        """Record a phase as completed and advance workflow_phase."""
        state = self.get_state(feature_type_id)
        if state is None:
            raise ValueError(f"Feature not found: {feature_type_id}")

        if state.current_phase is None:
            raise ValueError(
                f"Cannot complete phase '{phase}': no active phase for "
                f"{feature_type_id}"
            )

        phase_values = [p.value for p in PHASE_SEQUENCE]

        if phase not in phase_values:
            raise ValueError(f"Unknown phase: {phase}")

        phase_idx = phase_values.index(phase)

        if phase != state.current_phase:
            # Check if this is a backward re-run
            if state.last_completed_phase is None:
                raise ValueError(
                    f"Phase mismatch: cannot complete '{phase}' when current "
                    f"phase is '{state.current_phase}' and no phases completed yet"
                )
            last_idx = phase_values.index(state.last_completed_phase)
            if phase_idx > last_idx:
                raise ValueError(
                    f"Phase mismatch: cannot complete '{phase}' when current "
                    f"phase is '{state.current_phase}'"
                )
            # Backward re-run is valid -- continue

        next_phase = self._next_phase_value(phase)
        if next_phase is None:
            next_phase = phase  # Terminal phase (finish) stays as-is

        self.db.update_workflow_phase(
            feature_type_id,
            last_completed_phase=phase,
            workflow_phase=next_phase,
        )

        return self.get_state(feature_type_id)  # type: ignore[return-value]

    def validate_prerequisites(
        self, feature_type_id: str, target_phase: str
    ) -> list[TransitionResult]:
        """Dry-run gate evaluation without executing the transition."""
        state = self.get_state(feature_type_id)
        if state is None:
            raise ValueError(f"Feature not found: {feature_type_id}")

        slug = self._extract_slug(feature_type_id)
        existing_artifacts = self._get_existing_artifacts(slug)
        return self._evaluate_gates(
            state, target_phase, existing_artifacts, yolo_active=False
        )

    def list_by_phase(self, phase: str) -> list[FeatureWorkflowState]:
        """All features currently in the given phase."""
        rows = self.db.list_workflow_phases(workflow_phase=phase)
        return [
            FeatureWorkflowState(
                feature_type_id=row["type_id"],
                current_phase=row["workflow_phase"],
                last_completed_phase=row["last_completed_phase"],
                completed_phases=self._derive_completed_phases(
                    row["last_completed_phase"]
                ),
                mode=row["mode"],
                source="db",
            )
            for row in rows
        ]

    def list_by_status(self, status: str) -> list[FeatureWorkflowState]:
        """All features with the given entity status."""
        entities = self.db.list_entities(entity_type="feature")
        matching = [e for e in entities if e.get("status") == status]

        results: list[FeatureWorkflowState] = []
        for entity in matching:
            type_id = entity["type_id"]
            wp_row = self.db.get_workflow_phase(type_id)
            if wp_row is not None:
                results.append(
                    FeatureWorkflowState(
                        feature_type_id=type_id,
                        current_phase=wp_row["workflow_phase"],
                        last_completed_phase=wp_row["last_completed_phase"],
                        completed_phases=self._derive_completed_phases(
                            wp_row["last_completed_phase"]
                        ),
                        mode=wp_row["mode"],
                        source="db",
                    )
                )
            else:
                results.append(
                    FeatureWorkflowState(
                        feature_type_id=type_id,
                        current_phase=None,
                        last_completed_phase=None,
                        completed_phases=(),
                        mode=None,
                        source="db",
                    )
                )
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_slug(self, feature_type_id: str) -> str:
        """Extract slug from type_id. 'feature:008-foo' -> '008-foo'."""
        if ":" not in feature_type_id:
            raise ValueError(
                f"Invalid feature_type_id (missing ':'): {feature_type_id}"
            )
        parts = feature_type_id.split(":", 1)
        if not parts[1]:
            raise ValueError(
                f"Invalid feature_type_id (empty slug): {feature_type_id}"
            )
        return parts[1]

    def _derive_completed_phases(
        self, last_completed: str | None
    ) -> tuple[str, ...]:
        """Derive completed phases tuple from last_completed_phase."""
        if not last_completed:
            return ()
        phase_values = [p.value for p in PHASE_SEQUENCE]
        if last_completed not in phase_values:
            raise ValueError(f"Unknown phase: {last_completed}")
        idx = phase_values.index(last_completed)
        return tuple(phase_values[: idx + 1])

    def _next_phase_value(self, current_phase: str) -> str | None:
        """Return the next phase value, or None if at end of sequence."""
        phase_values = [p.value for p in PHASE_SEQUENCE]
        if current_phase not in phase_values:
            raise ValueError(f"Unknown phase: {current_phase}")
        idx = phase_values.index(current_phase)
        if idx >= len(phase_values) - 1:
            return None
        return phase_values[idx + 1]

    def _get_existing_artifacts(self, feature_slug: str) -> list[str]:
        """Return list of artifact filenames that exist for this feature."""
        feature_dir = os.path.join(
            self.artifacts_root, "features", feature_slug
        )
        all_artifacts: set[str] = set()
        for artifacts_list in HARD_PREREQUISITES.values():
            all_artifacts.update(artifacts_list)
        return [
            name
            for name in sorted(all_artifacts)
            if os.path.exists(os.path.join(feature_dir, name))
        ]

    def _hydrate_from_meta_json(
        self, feature_type_id: str
    ) -> FeatureWorkflowState | None:
        """Lazy hydration: parse .meta.json, derive state, backfill DB row."""
        # Precondition: entity must exist
        entity = self.db.get_entity(feature_type_id)
        if entity is None:
            return None

        slug = self._extract_slug(feature_type_id)
        meta_path = os.path.join(
            self.artifacts_root, "features", slug, ".meta.json"
        )
        if not os.path.exists(meta_path):
            return None

        with open(meta_path) as f:
            meta = json.load(f)

        status = meta.get("status")
        mode = meta.get("mode")
        last_completed = meta.get("lastCompletedPhase")

        # Derive workflow_phase based on status
        if status == "active":
            if last_completed:
                try:
                    next_phase = self._next_phase_value(last_completed)
                except ValueError:
                    return None
                workflow_phase = next_phase if next_phase is not None else last_completed
            else:
                workflow_phase = PHASE_SEQUENCE[0].value
            try:
                completed_phases = self._derive_completed_phases(last_completed)
            except ValueError:
                return None
        elif status == "completed":
            workflow_phase = "finish"
            last_completed = last_completed or "finish"
            try:
                completed_phases = self._derive_completed_phases(last_completed)
            except ValueError:
                return None
        else:
            # "planned", "abandoned", or any other status
            workflow_phase = None
            last_completed = None
            completed_phases = ()

        # Backfill DB row
        try:
            self.db.create_workflow_phase(
                feature_type_id,
                workflow_phase=workflow_phase,
                last_completed_phase=last_completed,
                mode=mode,
            )
        except ValueError as e:
            if "already exists" in str(e):
                # Race condition: another caller created the row first
                row = self.db.get_workflow_phase(feature_type_id)
                if row is not None:
                    return FeatureWorkflowState(
                        feature_type_id=row["type_id"],
                        current_phase=row["workflow_phase"],
                        last_completed_phase=row["last_completed_phase"],
                        completed_phases=self._derive_completed_phases(
                            row["last_completed_phase"]
                        ),
                        mode=row["mode"],
                        source="meta_json",
                    )
            raise

        return FeatureWorkflowState(
            feature_type_id=feature_type_id,
            current_phase=workflow_phase,
            last_completed_phase=last_completed,
            completed_phases=completed_phases,
            mode=mode,
            source="meta_json",
        )

    def _evaluate_gates(
        self,
        state: FeatureWorkflowState,
        target_phase: str,
        existing_artifacts: list[str],
        yolo_active: bool,
    ) -> list[TransitionResult]:
        """Run ordered gate evaluation with skip conditions and YOLO overrides."""
        results: list[TransitionResult] = []

        # Gate 1: check_backward_transition (skip if last_completed_phase is None)
        if state.last_completed_phase is not None:
            guard_id = self._GATE_GUARD_IDS["check_backward_transition"]
            if yolo_active:
                override = check_yolo_override(guard_id, True)
                if override is not None:
                    results.append(override)
                else:
                    results.append(
                        check_backward_transition(
                            target_phase, state.last_completed_phase
                        )
                    )
            else:
                results.append(
                    check_backward_transition(
                        target_phase, state.last_completed_phase
                    )
                )

        # Gate 2: check_hard_prerequisites (never skipped)
        guard_id = self._GATE_GUARD_IDS["check_hard_prerequisites"]
        if yolo_active:
            override = check_yolo_override(guard_id, True)
            if override is not None:
                results.append(override)
            else:
                results.append(
                    check_hard_prerequisites(target_phase, existing_artifacts)
                )
        else:
            results.append(
                check_hard_prerequisites(target_phase, existing_artifacts)
            )

        # Gate 3: check_soft_prerequisites (never skipped)
        guard_id = self._GATE_GUARD_IDS["check_soft_prerequisites"]
        if yolo_active:
            override = check_yolo_override(guard_id, True)
            if override is not None:
                results.append(override)
            else:
                results.append(
                    check_soft_prerequisites(
                        target_phase, list(state.completed_phases)
                    )
                )
        else:
            results.append(
                check_soft_prerequisites(
                    target_phase, list(state.completed_phases)
                )
            )

        # Gate 4: validate_transition (skip if current_phase is None)
        if state.current_phase is not None:
            guard_id = self._GATE_GUARD_IDS["validate_transition"]
            if yolo_active:
                override = check_yolo_override(guard_id, True)
                if override is not None:
                    results.append(override)
                else:
                    results.append(
                        validate_transition(
                            state.current_phase,
                            target_phase,
                            list(state.completed_phases),
                        )
                    )
            else:
                results.append(
                    validate_transition(
                        state.current_phase,
                        target_phase,
                        list(state.completed_phases),
                    )
                )

        return results
