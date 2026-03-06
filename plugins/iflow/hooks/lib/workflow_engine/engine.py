"""WorkflowStateEngine -- stateless orchestrator for workflow phase transitions."""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone

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

from .models import FeatureWorkflowState, TransitionResponse

# Precomputed constants from immutable sources
_PHASE_VALUES: tuple[str, ...] = tuple(p.value for p in PHASE_SEQUENCE)
_ALL_HARD_ARTIFACTS: frozenset[str] = frozenset(
    name for names in HARD_PREREQUISITES.values() for name in names
)


def _iso_now() -> str:
    """Return current time as ISO 8601 string with local timezone offset.

    Matches existing .meta.json convention (e.g., '2026-03-06T18:30:00+08:00').
    """
    return datetime.now(timezone.utc).astimezone().isoformat()


class WorkflowStateEngine:
    """Stateless orchestrator -- no mutable instance state beyond constructor refs."""

    def __init__(self, db: EntityDatabase, artifacts_root: str) -> None:
        """Store references only. No DB calls, no I/O."""
        self.db = db
        self.artifacts_root = artifacts_root

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_state(self, feature_type_id: str) -> FeatureWorkflowState | None:
        """Read feature workflow state, falling back to .meta.json if DB unavailable."""
        if not self._check_db_health():
            print(
                f"workflow-engine: DB unhealthy, falling back to .meta.json "
                f"for {feature_type_id}",
                file=sys.stderr,
            )
            return self._read_state_from_meta_json(feature_type_id)

        try:
            row = self.db.get_workflow_phase(feature_type_id)
            if row is not None:
                return self._row_to_state(row)
            return self._hydrate_from_meta_json(feature_type_id)
        except sqlite3.Error as exc:
            print(
                f"workflow-engine: DB error in get_state, falling back to "
                f".meta.json for {feature_type_id}: {exc}",
                file=sys.stderr,
            )
            return self._read_state_from_meta_json(feature_type_id)

    def transition_phase(
        self,
        feature_type_id: str,
        target_phase: str,
        yolo_active: bool = False,
    ) -> TransitionResponse:
        """Validate and enter a target phase."""
        state = self.get_state(feature_type_id)
        if state is None:
            raise ValueError(f"Feature not found: {feature_type_id}")

        slug = self._extract_slug(feature_type_id)
        existing_artifacts = self._get_existing_artifacts(slug)
        results = self._evaluate_gates(state, target_phase, existing_artifacts, yolo_active)

        # Primary defense: health probe already failed during get_state
        if state.source == "meta_json_fallback":
            return TransitionResponse(results=tuple(results), degraded=True)

        if all(r.allowed for r in results):
            # Secondary defense: catch DB write failures
            try:
                self.db.update_workflow_phase(
                    feature_type_id, workflow_phase=target_phase
                )
            except sqlite3.Error as exc:
                print(
                    f"workflow-engine: DB write failed in transition_phase "
                    f"for {feature_type_id}: {exc}",
                    file=sys.stderr,
                )
                return TransitionResponse(
                    results=tuple(results), degraded=True
                )

        return TransitionResponse(results=tuple(results), degraded=False)

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

        if phase not in _PHASE_VALUES:
            raise ValueError(f"Unknown phase: {phase}")

        phase_idx = _PHASE_VALUES.index(phase)

        if phase != state.current_phase:
            # Check if this is a backward re-run
            if state.last_completed_phase is None:
                raise ValueError(
                    f"Phase mismatch: cannot complete '{phase}' when current "
                    f"phase is '{state.current_phase}' and no phases completed yet"
                )
            last_idx = _PHASE_VALUES.index(state.last_completed_phase)
            if phase_idx > last_idx:
                raise ValueError(
                    f"Phase mismatch: cannot complete '{phase}' when current "
                    f"phase is '{state.current_phase}'"
                )
            # Backward re-run is valid -- continue

        next_phase = self._next_phase_value(phase)
        if next_phase is None:
            next_phase = phase  # Terminal phase (finish) stays as-is

        # Primary defense: DB was already unhealthy during get_state
        if state.source == "meta_json_fallback":
            print(
                f"workflow-engine: DB already degraded, writing "
                f"complete_phase to .meta.json for {feature_type_id}",
                file=sys.stderr,
            )
            return self._write_meta_json_fallback(
                feature_type_id, phase, state
            )

        # Secondary defense: catch DB write failures
        try:
            self.db.update_workflow_phase(
                feature_type_id,
                last_completed_phase=phase,
                workflow_phase=next_phase,
            )
        except sqlite3.Error as exc:
            print(
                f"workflow-engine: DB write failed in complete_phase "
                f"for {feature_type_id}: {exc}",
                file=sys.stderr,
            )
            return self._write_meta_json_fallback(
                feature_type_id, phase, state
            )

        return FeatureWorkflowState(
            feature_type_id=feature_type_id,
            current_phase=next_phase,
            last_completed_phase=phase,
            completed_phases=self._derive_completed_phases(phase),
            mode=state.mode,
            source="db",
        )

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
        return [self._row_to_state(row) for row in rows]

    def list_by_status(self, status: str) -> list[FeatureWorkflowState]:
        """All features with the given entity status."""
        entities = self.db.list_entities(entity_type="feature")
        matching = [e for e in entities if e.get("status") == status]

        # 2-query pattern: fetch all workflow rows once, join in Python
        wp_rows = self.db.list_workflow_phases()
        wp_map = {r["type_id"]: r for r in wp_rows}

        results: list[FeatureWorkflowState] = []
        for entity in matching:
            type_id = entity["type_id"]
            wp_row = wp_map.get(type_id)
            if wp_row is not None:
                results.append(self._row_to_state(wp_row))
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

    def _check_db_health(self) -> bool:
        """Fast health probe -- SELECT 1 on the existing connection.

        Returns True if DB is usable, False otherwise.
        """
        # NOTE: busy_timeout is inherited from EntityDatabase (5s).
        # Accepted product decision -- see design C1 NFR-1 interaction.
        if self.db._conn is None:
            return False
        try:
            self.db._conn.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False

    def _row_to_state(
        self, row: dict, source: str = "db"
    ) -> FeatureWorkflowState:
        """Build FeatureWorkflowState from a workflow_phases DB row."""
        return FeatureWorkflowState(
            feature_type_id=row["type_id"],
            current_phase=row["workflow_phase"],
            last_completed_phase=row["last_completed_phase"],
            completed_phases=self._derive_completed_phases(
                row["last_completed_phase"]
            ),
            mode=row["mode"],
            source=source,
        )

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
        if last_completed is None:
            return ()
        if last_completed not in _PHASE_VALUES:
            raise ValueError(f"Unknown phase: {last_completed}")
        idx = _PHASE_VALUES.index(last_completed)
        return tuple(_PHASE_VALUES[: idx + 1])

    def _next_phase_value(self, current_phase: str) -> str | None:
        """Return the next phase value, or None if at end of sequence."""
        if current_phase not in _PHASE_VALUES:
            raise ValueError(f"Unknown phase: {current_phase}")
        idx = _PHASE_VALUES.index(current_phase)
        if idx >= len(_PHASE_VALUES) - 1:
            return None
        return _PHASE_VALUES[idx + 1]

    def _get_existing_artifacts(self, feature_slug: str) -> list[str]:
        """Return list of artifact filenames that exist for this feature."""
        feature_dir = os.path.join(
            self.artifacts_root, "features", feature_slug
        )
        return sorted(
            name
            for name in _ALL_HARD_ARTIFACTS
            if os.path.exists(os.path.join(feature_dir, name))
        )

    def _derive_state_from_meta(
        self,
        meta: dict,
        feature_type_id: str,
        source: str = "meta_json",
    ) -> FeatureWorkflowState | None:
        """Shared phase derivation from .meta.json dict.

        Used by both _hydrate_from_meta_json (DB-backed hydration) and
        _read_state_from_meta_json (pure-filesystem fallback).
        """
        status = meta.get("status")
        mode = meta.get("mode")
        last_completed = meta.get("lastCompletedPhase")

        # Derive workflow_phase based on status
        if status == "active":
            if last_completed is not None:
                try:
                    next_phase = self._next_phase_value(last_completed)
                except ValueError:
                    return None
                workflow_phase = next_phase if next_phase is not None else last_completed
            else:
                workflow_phase = PHASE_SEQUENCE[0].value
            # _next_phase_value above already validated last_completed against
            # _PHASE_VALUES, so _derive_completed_phases cannot raise here.
            completed_phases = self._derive_completed_phases(last_completed)
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

        return FeatureWorkflowState(
            feature_type_id=feature_type_id,
            current_phase=workflow_phase,
            last_completed_phase=last_completed,
            completed_phases=completed_phases,
            mode=mode,
            source=source,
        )

    def _read_state_from_meta_json(
        self, feature_type_id: str
    ) -> FeatureWorkflowState | None:
        """Standalone .meta.json reader for degraded-mode fallback.

        Unlike _hydrate_from_meta_json, this method:
        - Does NOT check entity existence in the DB
        - Does NOT backfill the DB row
        - Catches OSError in addition to json.JSONDecodeError (must never raise)
        """
        slug = self._extract_slug(feature_type_id)
        meta_path = os.path.join(
            self.artifacts_root, "features", slug, ".meta.json"
        )
        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        return self._derive_state_from_meta(
            meta, feature_type_id, source="meta_json_fallback"
        )

    def _write_meta_json_fallback(
        self,
        feature_type_id: str,
        phase: str,
        state: FeatureWorkflowState,
    ) -> FeatureWorkflowState:
        """Atomic .meta.json update when DB is unavailable.

        Reads current .meta.json, updates lastCompletedPhase and phase
        timestamps, writes atomically via NamedTemporaryFile + os.replace().

        Only state.mode is read from the state parameter -- all other data
        comes from the .meta.json file and the phase argument.
        """
        slug = self._extract_slug(feature_type_id)
        meta_path = os.path.join(
            self.artifacts_root, "features", slug, ".meta.json"
        )

        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Cannot update .meta.json: {exc}") from exc

        now = _iso_now()
        meta["lastCompletedPhase"] = phase
        meta.setdefault("phases", {})
        meta["phases"].setdefault(phase, {})
        meta["phases"][phase]["completed"] = now

        if phase == "finish":
            meta["status"] = "completed"
            meta["completed"] = now

        next_phase = self._next_phase_value(phase)
        workflow_phase = next_phase if next_phase is not None else phase

        fd = None
        try:
            fd = tempfile.NamedTemporaryFile(
                mode="w",
                dir=os.path.dirname(meta_path),
                suffix=".tmp",
                delete=False,
            )
            json.dump(meta, fd, indent=2)
            fd.close()
            os.replace(fd.name, meta_path)
        except BaseException:
            if fd is not None and not fd.closed:
                fd.close()
            if fd is not None:
                try:
                    os.unlink(fd.name)
                except OSError:
                    pass
            raise

        return FeatureWorkflowState(
            feature_type_id=feature_type_id,
            current_phase=workflow_phase,
            last_completed_phase=phase,
            completed_phases=self._derive_completed_phases(phase),
            mode=state.mode,
            source="meta_json_fallback",
        )

    def _scan_features_filesystem(self) -> list[FeatureWorkflowState]:
        """Scan features directory for .meta.json files.

        Used when DB is unavailable for list operations. Delegates to
        _read_state_from_meta_json for each discovered file, which handles
        corrupt/unparseable files by returning None (silently skipped).
        """
        pattern = os.path.join(
            self.artifacts_root, "features", "*", ".meta.json"
        )
        results: list[FeatureWorkflowState] = []
        for meta_path in glob.glob(pattern):
            feature_dir = os.path.basename(os.path.dirname(meta_path))
            feature_type_id = f"feature:{feature_dir}"
            state = self._read_state_from_meta_json(feature_type_id)
            if state is not None:
                results.append(state)
        return results

    def _scan_features_by_status(
        self, status: str
    ) -> list[FeatureWorkflowState]:
        """Scan features directory, filtering by .meta.json status field.

        Reads raw JSON and filters by meta["status"] BEFORE building
        FeatureWorkflowState (which has no status field). Only matching
        features get state derivation, avoiding wasted computation.

        Used by list_by_status() fallback when DB is unavailable.
        """
        pattern = os.path.join(
            self.artifacts_root, "features", "*", ".meta.json"
        )
        results: list[FeatureWorkflowState] = []
        for meta_path in glob.glob(pattern):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if meta.get("status") != status:
                continue
            feature_dir = os.path.basename(os.path.dirname(meta_path))
            feature_type_id = f"feature:{feature_dir}"
            state = self._derive_state_from_meta(
                meta, feature_type_id, source="meta_json_fallback"
            )
            if state is not None:
                results.append(state)
        return results

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

        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except json.JSONDecodeError:
            return None

        # Delegate phase derivation to shared helper (was inline before)
        state = self._derive_state_from_meta(meta, feature_type_id, source="meta_json")
        if state is None:
            return None

        # Backfill DB row
        try:
            self.db.create_workflow_phase(
                feature_type_id,
                workflow_phase=state.current_phase,
                last_completed_phase=state.last_completed_phase,
                mode=state.mode,
            )
        except ValueError:
            # All inputs (workflow_phase, last_completed, mode) are pre-validated
            # by _next_phase_value / _derive_completed_phases above, so the only
            # ValueError from create_workflow_phase is a duplicate-row conflict.
            # Re-fetch handles the race condition; re-raise if no row found.
            row = self.db.get_workflow_phase(feature_type_id)
            if row is not None:
                return self._row_to_state(row, source="meta_json")
            raise

        return state

    @staticmethod
    def _run_gate(
        guard_id: str,
        gate_fn: Callable[..., TransitionResult],
        *args: object,
        yolo_active: bool,
    ) -> TransitionResult:
        """Run a single gate with optional YOLO override."""
        if yolo_active:
            override = check_yolo_override(guard_id, True)
            if override is not None:
                return override
        return gate_fn(*args)

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
            results.append(self._run_gate(
                "G-18", check_backward_transition,
                target_phase, state.last_completed_phase,
                yolo_active=yolo_active,
            ))

        # Gate 2: check_hard_prerequisites (never skipped)
        results.append(self._run_gate(
            "G-08", check_hard_prerequisites,
            target_phase, existing_artifacts,
            yolo_active=yolo_active,
        ))

        # Gate 3: check_soft_prerequisites (never skipped)
        results.append(self._run_gate(
            "G-23", check_soft_prerequisites,
            target_phase, list(state.completed_phases),
            yolo_active=yolo_active,
        ))

        # Gate 4: validate_transition (skip if current_phase is None)
        if state.current_phase is not None:
            results.append(self._run_gate(
                "G-22", validate_transition,
                state.current_phase, target_phase, list(state.completed_phases),
                yolo_active=yolo_active,
            ))

        return results
