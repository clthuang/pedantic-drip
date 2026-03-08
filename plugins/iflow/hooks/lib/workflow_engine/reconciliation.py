"""Reconciliation module -- drift detection and reconciliation between .meta.json and DB.

Pure logic module for workflow state drift detection and reconciliation.
No MCP awareness -- accepts explicit parameters, returns dataclasses.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from entity_registry.database import EntityDatabase
from transition_gate.constants import PHASE_SEQUENCE

from .constants import FEATURE_PHASE_TO_KANBAN
from .engine import WorkflowStateEngine

# Precomputed phase values from immutable PHASE_SEQUENCE (same pattern as engine.py)
_PHASE_VALUES: tuple[str, ...] = tuple(p.value for p in PHASE_SEQUENCE)


# ---------------------------------------------------------------------------
# Dataclasses (Design I1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkflowMismatch:
    """Single-field comparison between .meta.json and DB."""

    field: str
    meta_json_value: str | None
    db_value: str | None


@dataclass(frozen=True)
class WorkflowDriftReport:
    """Drift assessment for a single feature's workflow state."""

    feature_type_id: str
    status: str  # "in_sync"|"meta_json_ahead"|"db_ahead"|"meta_json_only"|"db_only"|"error"
    meta_json: dict | None  # {workflow_phase, last_completed_phase, mode, status}
    db: dict | None  # {workflow_phase, last_completed_phase, mode, kanban_column}
    mismatches: tuple[WorkflowMismatch, ...]
    message: str = ""  # human-readable context for error/edge cases


@dataclass(frozen=True)
class WorkflowDriftResult:
    """Aggregate result from check_workflow_drift()."""

    features: tuple[WorkflowDriftReport, ...]
    summary: dict  # {in_sync, meta_json_ahead, db_ahead, meta_json_only, db_only, error}


@dataclass(frozen=True)
class ReconcileAction:
    """Outcome of reconciling a single feature.

    Design extends spec R2 action enum with "created" to differentiate
    update (existing DB row) vs create (new row for meta_json_only).

    AC-8 mapping: "reconcile_apply on meta_json_only creates a new row"
    -> test assertions should use action="created" for this case.
    AC-6 mapping: "reconcile_apply on meta_json_ahead updates existing row"
    -> test assertions should use action="reconciled" for this case.
    """

    feature_type_id: str
    action: str  # "reconciled"|"skipped"|"created"|"error"
    direction: str  # "meta_json_to_db"
    changes: tuple[WorkflowMismatch, ...]
    # Serialization note: when serialized via _serialize_reconcile_action,
    # db_value -> "old_value" and meta_json_value -> "new_value".
    message: str


@dataclass(frozen=True)
class ReconciliationResult:
    """Aggregate result from apply_workflow_reconciliation().

    Summary extends spec R2 with "created" count (design enhancement).
    """

    actions: tuple[ReconcileAction, ...]
    summary: dict  # {reconciled, created, skipped, error, dry_run}


# ---------------------------------------------------------------------------
# Phase comparison helpers (Design I3)
# ---------------------------------------------------------------------------


def _phase_index(phase: str | None) -> int:
    """Return ordinal index of a phase in PHASE_SEQUENCE, or -1 for None/unknown."""
    if phase is None:
        return -1
    try:
        return _PHASE_VALUES.index(phase)
    except ValueError:
        return -1


def _compare_phases(
    meta_last: str | None,
    meta_current: str | None,
    db_last: str | None,
    db_current: str | None,
) -> str:
    """Compare phase positions and return drift status string.

    Implements the 8-step comparison algorithm from spec R8:
    1. Compare last_completed_phase indices
    2. Higher index = more advanced
    3. meta_json > db -> "meta_json_ahead"
    4. db > meta -> "db_ahead"
    5. If equal, compare workflow_phase (current phase)
    6. If both equal -> "in_sync"
    7. None vs non-None -> non-None is ahead
    8. Both None -> equal at -1, proceed to workflow_phase comparison

    Returns: "in_sync"|"meta_json_ahead"|"db_ahead"
    """
    meta_last_idx = _phase_index(meta_last)
    db_last_idx = _phase_index(db_last)

    # Steps 1-4, 7-8: Compare last_completed_phase
    if meta_last_idx > db_last_idx:
        return "meta_json_ahead"
    if db_last_idx > meta_last_idx:
        return "db_ahead"

    # Steps 5-6: Equal last_completed, compare workflow_phase
    meta_current_idx = _phase_index(meta_current)
    db_current_idx = _phase_index(db_current)

    if meta_current_idx > db_current_idx:
        return "meta_json_ahead"
    if db_current_idx > meta_current_idx:
        return "db_ahead"

    return "in_sync"


# ---------------------------------------------------------------------------
# Internal helpers (Design I3)
# ---------------------------------------------------------------------------


def _read_single_meta_json(
    engine: WorkflowStateEngine,
    artifacts_root: str,
    feature_type_id: str,
) -> dict | None:
    """Read .meta.json for a single feature without bulk scan.

    Extracts slug via engine._extract_slug(feature_type_id), constructs
    path as {artifacts_root}/features/{slug}/.meta.json, reads and parses.

    Returns parsed dict or None if file missing/unparseable.
    """
    try:
        slug = engine._extract_slug(feature_type_id)
    except ValueError:
        return None

    meta_path = os.path.join(artifacts_root, "features", slug, ".meta.json")
    try:
        with open(meta_path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _derive_expected_kanban(
    workflow_phase: str | None,
    last_completed_phase: str | None,
) -> str | None:
    """Derive the expected kanban column from workflow phase.

    Special case: finish phase with finish as last_completed means the
    feature completed all phases -> 'completed' column.
    Otherwise, look up the phase in FEATURE_PHASE_TO_KANBAN.
    Returns None for unknown or None phases.
    """
    if workflow_phase is None:
        return None
    if workflow_phase == "finish" and last_completed_phase == "finish":
        return "completed"
    return FEATURE_PHASE_TO_KANBAN.get(workflow_phase)


def _check_single_feature(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    feature_type_id: str,
    meta: dict,
) -> WorkflowDriftReport:
    """Build drift report for one feature given its .meta.json dict and DB state.

    Field name mapping:
    - state.current_phase -> workflow_phase (DB column name)
    - state.last_completed_phase -> last_completed_phase
    - state.mode -> mode
    """
    # Derive state from meta
    state = engine._derive_state_from_meta(meta, feature_type_id)
    if state is None:
        return WorkflowDriftReport(
            feature_type_id=feature_type_id,
            status="error",
            meta_json=None,
            db=None,
            mismatches=(),
            message="Failed to derive state from .meta.json",
        )

    # Build meta_json output dict (using DB column names)
    meta_dict = {
        "workflow_phase": state.current_phase,
        "last_completed_phase": state.last_completed_phase,
        "mode": state.mode,
        "status": meta.get("status"),
    }

    # Read DB row
    row = db.get_workflow_phase(feature_type_id)

    if row is None:
        return WorkflowDriftReport(
            feature_type_id=feature_type_id,
            status="meta_json_only",
            meta_json=meta_dict,
            db=None,
            mismatches=(),
        )

    # Build DB output dict
    db_dict = {
        "workflow_phase": row["workflow_phase"],
        "last_completed_phase": row["last_completed_phase"],
        "mode": row["mode"],
        "kanban_column": row["kanban_column"],
    }

    # Compare phases (determines status)
    status = _compare_phases(
        state.last_completed_phase,
        state.current_phase,
        row["last_completed_phase"],
        row["workflow_phase"],
    )

    # Detect all mismatches (including mode)
    mismatches: list[WorkflowMismatch] = []

    if state.last_completed_phase != row["last_completed_phase"]:
        mismatches.append(WorkflowMismatch(
            field="last_completed_phase",
            meta_json_value=state.last_completed_phase,
            db_value=row["last_completed_phase"],
        ))

    if state.current_phase != row["workflow_phase"]:
        mismatches.append(WorkflowMismatch(
            field="workflow_phase",
            meta_json_value=state.current_phase,
            db_value=row["workflow_phase"],
        ))

    if state.mode != row["mode"]:
        mismatches.append(WorkflowMismatch(
            field="mode",
            meta_json_value=state.mode,
            db_value=row["mode"],
        ))

    # Kanban column drift detection
    expected_kanban = _derive_expected_kanban(
        state.current_phase, state.last_completed_phase
    )
    if expected_kanban is not None and expected_kanban != row["kanban_column"]:
        mismatches.append(WorkflowMismatch(
            field="kanban_column",
            meta_json_value=expected_kanban,
            db_value=row["kanban_column"],
        ))

    return WorkflowDriftReport(
        feature_type_id=feature_type_id,
        status=status,
        meta_json=meta_dict,
        db=db_dict,
        mismatches=tuple(mismatches),
    )


def _reconcile_single_feature(
    db: EntityDatabase,
    report: WorkflowDriftReport,
    dry_run: bool,
) -> ReconcileAction:
    """Execute reconciliation for one feature based on its drift report.

    report.meta_json contains all needed .meta.json data -- separate meta
    parameter unnecessary since drift detection already derived the state.
    """
    direction = "meta_json_to_db"
    feature_type_id = report.feature_type_id

    if report.status == "meta_json_ahead":
        # Build changes from mismatches in the report
        changes = report.mismatches

        if not dry_run:
            meta = report.meta_json
            if meta is None:
                return ReconcileAction(
                    feature_type_id=feature_type_id,
                    action="error",
                    direction=direction,
                    changes=(),
                    message="meta_json_ahead status but no meta_json data",
                )
            try:
                expected_kanban = _derive_expected_kanban(
                    meta["workflow_phase"], meta["last_completed_phase"]
                )
                kwargs = dict(
                    workflow_phase=meta["workflow_phase"],
                    last_completed_phase=meta["last_completed_phase"],
                    mode=meta["mode"],
                )
                if expected_kanban is not None:
                    kwargs["kanban_column"] = expected_kanban
                db.update_workflow_phase(feature_type_id, **kwargs)
            except ValueError as exc:
                return ReconcileAction(
                    feature_type_id=feature_type_id,
                    action="error",
                    direction=direction,
                    changes=(),
                    message=f"Update failed: {exc}",
                )

        return ReconcileAction(
            feature_type_id=feature_type_id,
            action="reconciled",
            direction=direction,
            changes=changes,
            message="Updated DB to match .meta.json",
        )

    if report.status == "meta_json_only":
        # Defensive guard: meta_json must be present
        if report.meta_json is None:
            return ReconcileAction(
                feature_type_id=feature_type_id,
                action="error",
                direction=direction,
                changes=(),
                message="meta_json_only status but no meta_json data available",
            )

        # Build changes showing what will be created
        changes = (
            WorkflowMismatch(
                field="workflow_phase",
                meta_json_value=report.meta_json["workflow_phase"],
                db_value=None,
            ),
            WorkflowMismatch(
                field="last_completed_phase",
                meta_json_value=report.meta_json["last_completed_phase"],
                db_value=None,
            ),
            WorkflowMismatch(
                field="mode",
                meta_json_value=report.meta_json["mode"],
                db_value=None,
            ),
        )

        if not dry_run:
            try:
                db.create_workflow_phase(
                    feature_type_id,
                    workflow_phase=report.meta_json["workflow_phase"],
                    last_completed_phase=report.meta_json["last_completed_phase"],
                    mode=report.meta_json["mode"],
                )
            except ValueError as exc:
                return ReconcileAction(
                    feature_type_id=feature_type_id,
                    action="error",
                    direction=direction,
                    changes=(),
                    message=f"Create failed: {exc}",
                )

        return ReconcileAction(
            feature_type_id=feature_type_id,
            action="created",
            direction=direction,
            changes=changes,
            message="Created DB row from .meta.json",
        )

    if report.status == "in_sync":
        return ReconcileAction(
            feature_type_id=feature_type_id,
            action="skipped",
            direction=direction,
            changes=(),
            message="Already in sync",
        )

    if report.status == "db_ahead":
        return ReconcileAction(
            feature_type_id=feature_type_id,
            action="skipped",
            direction=direction,
            changes=(),
            message="DB is ahead -- manual resolution required",
        )

    if report.status == "db_only":
        return ReconcileAction(
            feature_type_id=feature_type_id,
            action="skipped",
            direction=direction,
            changes=(),
            message="No .meta.json to reconcile from",
        )

    # status == "error" -- propagate original error
    return ReconcileAction(
        feature_type_id=feature_type_id,
        action="error",
        direction=direction,
        changes=(),
        message=report.message,
    )


# ---------------------------------------------------------------------------
# Public API (Design I2)
# ---------------------------------------------------------------------------


def check_workflow_drift(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None = None,
) -> WorkflowDriftResult:
    """Detect workflow state drift between .meta.json and DB.

    Parameters
    ----------
    engine : WorkflowStateEngine
        Engine instance (for _derive_state_from_meta, _iter_meta_jsons,
        _extract_slug).
    db : EntityDatabase
        Database instance (for get_workflow_phase).
    artifacts_root : str
        Root directory for artifact files.
    feature_type_id : str | None
        If provided, check single feature. If None, scan all.

    Returns
    -------
    WorkflowDriftResult
        Per-feature drift reports and aggregate summary.

    Never raises -- all per-feature exceptions caught and returned as
    status="error".
    """
    reports: list[WorkflowDriftReport] = []

    if feature_type_id is not None:
        # Single-feature path
        meta = _read_single_meta_json(engine, artifacts_root, feature_type_id)
        if meta is not None:
            try:
                report = _check_single_feature(engine, db, feature_type_id, meta)
                reports.append(report)
            except Exception as exc:
                reports.append(WorkflowDriftReport(
                    feature_type_id=feature_type_id,
                    status="error",
                    meta_json=None,
                    db=None,
                    mismatches=(),
                    message=str(exc),
                ))
        else:
            # No .meta.json -- check if DB row exists
            row = db.get_workflow_phase(feature_type_id)
            if row is not None:
                db_dict = {
                    "workflow_phase": row["workflow_phase"],
                    "last_completed_phase": row["last_completed_phase"],
                    "mode": row["mode"],
                    "kanban_column": row["kanban_column"],
                }
                reports.append(WorkflowDriftReport(
                    feature_type_id=feature_type_id,
                    status="db_only",
                    meta_json=None,
                    db=db_dict,
                    mismatches=(),
                ))
            else:
                reports.append(WorkflowDriftReport(
                    feature_type_id=feature_type_id,
                    status="error",
                    meta_json=None,
                    db=None,
                    mismatches=(),
                    message=f"Feature not found: {feature_type_id}",
                ))
    else:
        # Bulk path: scan all .meta.json files
        meta_type_ids: set[str] = set()
        for ftype_id, meta in engine._iter_meta_jsons():
            meta_type_ids.add(ftype_id)
            try:
                report = _check_single_feature(engine, db, ftype_id, meta)
                reports.append(report)
            except Exception as exc:
                reports.append(WorkflowDriftReport(
                    feature_type_id=ftype_id,
                    status="error",
                    meta_json=None,
                    db=None,
                    mismatches=(),
                    message=str(exc),
                ))

        # Detect db_only features via set difference
        # Only include feature: type_ids (exclude non-feature entities)
        all_wp_rows = db.list_workflow_phases()
        db_rows_by_id = {
            row["type_id"]: row for row in all_wp_rows
            if row["type_id"].startswith("feature:")
        }
        db_only_ids = db_rows_by_id.keys() - meta_type_ids

        for ftype_id in sorted(db_only_ids):
            row = db_rows_by_id[ftype_id]
            db_dict = {
                "workflow_phase": row["workflow_phase"],
                "last_completed_phase": row["last_completed_phase"],
                "mode": row["mode"],
                "kanban_column": row["kanban_column"],
            }
            reports.append(WorkflowDriftReport(
                feature_type_id=ftype_id,
                status="db_only",
                meta_json=None,
                db=db_dict,
                mismatches=(),
            ))

    return _build_drift_result(reports)


def apply_workflow_reconciliation(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None = None,
    dry_run: bool = False,
) -> ReconciliationResult:
    """Sync .meta.json workflow state to DB for drifted features.

    Only reconciles features where .meta.json is ahead (post-degradation).
    Calls check_workflow_drift() internally to detect drift first.

    Parameters
    ----------
    engine : WorkflowStateEngine
        Engine instance.
    db : EntityDatabase
        Database instance (for create/update_workflow_phase).
    artifacts_root : str
        Root directory for artifact files.
    feature_type_id : str | None
        If provided, reconcile single feature. If None, reconcile all.
    dry_run : bool
        If True, compute changes without applying.

    Returns
    -------
    ReconciliationResult
        Per-feature actions and aggregate summary.

    Never raises -- all per-feature exceptions caught and returned as
    action="error".
    """
    drift_result = check_workflow_drift(engine, db, artifacts_root, feature_type_id)

    actions: list[ReconcileAction] = []
    for report in drift_result.features:
        try:
            action = _reconcile_single_feature(db, report, dry_run)
            actions.append(action)
        except Exception as exc:
            actions.append(ReconcileAction(
                feature_type_id=report.feature_type_id,
                action="error",
                direction="meta_json_to_db",
                changes=(),
                message=str(exc),
            ))

    return _build_reconciliation_result(actions, dry_run)


# ---------------------------------------------------------------------------
# Result builders
# ---------------------------------------------------------------------------


def _build_drift_result(reports: list[WorkflowDriftReport]) -> WorkflowDriftResult:
    """Build WorkflowDriftResult with summary counts from reports."""
    summary = {
        "in_sync": 0,
        "meta_json_ahead": 0,
        "db_ahead": 0,
        "meta_json_only": 0,
        "db_only": 0,
        "error": 0,
    }
    for report in reports:
        if report.status in summary:
            summary[report.status] += 1
        else:
            summary["error"] += 1

    return WorkflowDriftResult(features=tuple(reports), summary=summary)


def _build_reconciliation_result(
    actions: list[ReconcileAction],
    dry_run: bool,
) -> ReconciliationResult:
    """Build ReconciliationResult with summary counts from actions."""
    summary = {
        "reconciled": 0,
        "created": 0,
        "skipped": 0,
        "error": 0,
        "dry_run": 0,
    }
    for action in actions:
        if action.action in summary:
            summary[action.action] += 1

    if dry_run:
        # dry_run count = total non-error, non-skipped actions
        summary["dry_run"] = summary["reconciled"] + summary["created"]

    return ReconciliationResult(actions=tuple(actions), summary=summary)
