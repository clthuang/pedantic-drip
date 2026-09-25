"""Workflow drift detection between the DB and its .meta.json projections, and
missed-cascade recovery.

Pure logic module. No MCP awareness -- accepts explicit parameters, returns
dataclasses.

- **Drift is reported, never applied** (design W1.3): a ``.meta.json`` is a
  projection of the DB, so nothing here writes a projection's state back
  into it. ``check_workflow_drift`` only reads.
- **Cascade recovery** (``_recover_pending_cascades``) re-runs completion
  cascades that never ran, in one workspace, writing by uuid (W1.7). The
  session-start orchestrator runs it as its own task.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass

from entity_registry.database import EntityDatabase
from entity_registry.metadata import parse_metadata
from transition_gate.constants import PHASE_SEQUENCE

from .engine import WorkflowStateEngine
from .rollup import compute_objective_score, compute_progress, rollup_parent

# Precomputed phase values from immutable PHASE_SEQUENCE (same pattern as engine.py)
_PHASE_VALUES: tuple[str, ...] = tuple(p.value for p in PHASE_SEQUENCE)

# Local replica of the former workflow_engine.kanban module (deleted at
# feature 132, Scope model D6.1-.3 — post-cutover call sites carry their
# own copy instead of importing the shared kanban.py helper). Byte-identical to
# its siblings in backfill.py / engine.py / feature_lifecycle.py /
# workflow_state_server.py — kept in sync via test_constants.py's parity
# pin.
_PHASE_TO_KANBAN: dict[str, str] = {
    "brainstorm": "backlog",
    "specify": "backlog",
    "design": "prioritised",
    "create-plan": "prioritised",
    "implement": "wip",
    "finish": "documenting",
    "discover": "backlog",
    "define": "backlog",
    "deliver": "wip",
    "debrief": "documenting",
}


def _kanban_column_for(status: str, workflow_phase: str | None) -> str:
    """Kanban column for (status, workflow_phase).

    Priority order (unchanged from the retired kanban.py logic):
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
    return _PHASE_TO_KANBAN.get(workflow_phase, "backlog")


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
    """Drift assessment for a single feature's workflow state.

    A ``db_only`` report can also carry an ORPHAN workflow_phases row (no
    entities row, so no kind), whatever its type_id prefix: since C8 the
    db_only filter in ``check_workflow_drift`` reads the joined kind column
    and keeps orphans visible.
    """

    feature_type_id: str
    status: str  # "in_sync"|"meta_json_ahead"|"db_ahead"|"meta_json_only"|"db_only"|"error"
    meta_json: dict | None  # {workflow_phase, last_completed_phase, mode, status}
    db: dict | None  # {workflow_phase, last_completed_phase, mode, kanban_column}
    mismatches: tuple[WorkflowMismatch, ...]
    message: str = ""  # human-readable context for error/edge cases
    artifact_missing: bool = False  # R3: artifact dir does not exist on disk
    depth: int | None = None  # R4: entity tree depth (None for root/unknown)
    parent_type_id: str | None = None  # R4: immediate parent type_id


@dataclass(frozen=True)
class WorkflowDriftResult:
    """Aggregate result from check_workflow_drift()."""

    features: tuple[WorkflowDriftReport, ...]
    summary: dict  # {in_sync, meta_json_ahead, db_ahead, meta_json_only, db_only, error}


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


def _single_feature_dir_name(
    engine: WorkflowStateEngine, feature_type_id: str
) -> str | None:
    """The directory name for one feature: ``engine._feature_dir_name``.

    A failed registry read falls back to the features/ listing
    (``use_db=False``), so the single-feature check never raises for it.
    Refusals (ValueError) propagate to the caller.
    """
    try:
        return engine._feature_dir_name(feature_type_id)
    except sqlite3.Error:
        return engine._feature_dir_name(feature_type_id, use_db=False)


def _read_single_meta_json(
    engine: WorkflowStateEngine,
    artifacts_root: str,
    feature_type_id: str,
) -> dict | None:
    """Read .meta.json for a single feature without bulk scan.

    Names the directory via ``_single_feature_dir_name`` (the row's
    entity_id column, or with no row the listed directory; never the
    type_id text), then reads and parses
    ``{artifacts_root}/features/{dir_name}/.meta.json``.

    Returns parsed dict or None if no directory is named, the name is
    refused, or the file is missing/unparseable.
    """
    try:
        dir_name = _single_feature_dir_name(engine, feature_type_id)
    except ValueError:
        return None
    if dir_name is None:
        return None

    meta_path = os.path.join(artifacts_root, "features", dir_name, ".meta.json")
    try:
        with open(meta_path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


_TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "abandoned"})


def _derive_expected_kanban(
    workflow_phase: str | None,
    last_completed_phase: str | None,
    status: str | None = None,
) -> str | None:
    """Derive the expected kanban column from workflow phase.

    Delegates to _kanban_column_for() for consistent kanban derivation.
    Special case: finish phase with finish as last_completed means the
    feature completed all phases -> 'completed' column.
    Returns None for unknown or None phases (when status is also None).
    """
    if status in _TERMINAL_STATUSES:
        return "completed"
    if not workflow_phase:  # None or empty string
        return None
    if workflow_phase == "finish" and last_completed_phase == "finish":
        return "completed"
    result = _kanban_column_for(status or "active", workflow_phase)
    return result


def _check_single_feature(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    feature_type_id: str,
    meta: dict,
    artifact_dir: str | None = None,
) -> WorkflowDriftReport:
    """Build drift report for one feature given its .meta.json dict and DB state.

    Field name mapping:
    - state.current_phase -> workflow_phase (DB column name)
    - state.last_completed_phase -> last_completed_phase
    - state.mode -> mode
    """
    # R3: Check artifact directory existence
    artifact_missing = artifact_dir is not None and not os.path.exists(artifact_dir)

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
            artifact_missing=artifact_missing,
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
        state.current_phase, state.last_completed_phase,
        status=meta.get("status"),
    )
    if expected_kanban is not None and expected_kanban != row["kanban_column"]:
        mismatches.append(WorkflowMismatch(
            field="kanban_column",
            meta_json_value=expected_kanban,
            db_value=row["kanban_column"],
        ))

    # R4: Depth context
    # Performance: +1 get_entity + conditional get_lineage per feature. OK for <100 features.
    depth = None
    parent_tid = None
    msg = ""
    entity = db.get_entity(feature_type_id)
    if entity is not None:
        parent_tid = entity.get("parent_type_id")
        if parent_tid is not None:
            ancestors = db.get_lineage(feature_type_id, direction="up")
            # len - 1: get_lineage includes self (depth 0), so subtract 1 for tree depth
            depth = (len(ancestors) - 1) if ancestors else None
    if depth is not None:
        msg = f"depth: {depth}, parent: {parent_tid}"

    return WorkflowDriftReport(
        feature_type_id=feature_type_id,
        status=status,
        meta_json=meta_dict,
        db=db_dict,
        mismatches=tuple(mismatches),
        message=msg,
        artifact_missing=artifact_missing,
        depth=depth,
        parent_type_id=parent_tid,
    )


# ---------------------------------------------------------------------------
# Cascade recovery (Task 3.3a)
# ---------------------------------------------------------------------------


def _recover_pending_cascades(db: EntityDatabase, workspace_uuid: str) -> int:
    """Detect and recover missed cascades from two-phase commit failures.

    When Phase A (completion) commits but Phase B (cascade) fails (e.g., crash),
    completed children will have stale parent progress.  This function detects
    such mismatches and re-runs rollup_parent + cascade_unblock.

    Detection: For each entity with status=completed and a parent_uuid, compute
    expected parent progress from children.  Compare with stored progress in
    parent metadata.  Mismatch = missed cascade.

    Scoped to one workspace (design W1.7), so a session never rewrites
    another workspace's rows, even where the two share a type_id:

    - **Scans:** both list only *workspace_uuid*'s entities.
    - **Rollups:** a parent outside the workspace is not recovered here, and
      a rollup stops at the first ancestor outside it.
    - **Writes:** every write names its entity by uuid.

    Parameters
    ----------
    db:
        Open EntityDatabase instance.
    workspace_uuid:
        The session's workspace. Required: an unscoped recovery would
        rewrite every workspace's parents.

    Returns
    -------
    int
        Number of cascades recovered.

    Raises
    ------
    ValueError
        If *workspace_uuid* is empty.
    """
    if not workspace_uuid:
        raise ValueError(
            "cascade recovery needs the session's workspace_uuid; "
            "an unscoped recovery would rewrite every workspace's parents"
        )

    from entity_registry.dependencies import DependencyManager

    # Find this workspace's completed entities that have a parent
    completed = db.list_entities(workspace_uuid=workspace_uuid)
    completed_with_parent = [
        e for e in completed
        if e.get("status") == "completed" and e.get("parent_uuid")
    ]

    recovered = 0
    dep_mgr = DependencyManager()

    # Group by parent to avoid recomputing the same parent multiple times
    parents_checked: set[str] = set()

    for entity in completed_with_parent:
        parent_uuid = entity["parent_uuid"]

        if parent_uuid in parents_checked:
            continue
        parents_checked.add(parent_uuid)

        parent = db.get_entity_by_uuid(parent_uuid)
        if parent is None:
            continue
        # A parent in another workspace is that workspace's to recover.
        if parent.get("workspace_uuid") != workspace_uuid:
            continue

        # Compute expected progress
        expected_progress = compute_progress(db, parent_uuid)

        # Read stored progress from parent metadata
        raw_metadata = parent.get("metadata")
        metadata = parse_metadata(raw_metadata)

        stored_progress = metadata.get("progress")

        # Compare: mismatch if no stored progress or different value
        if stored_progress is not None and abs(stored_progress - expected_progress) < 1e-9:
            continue  # already correct

        # Mismatch detected — re-run cascade
        # Re-run rollup for all completed children under this parent
        for child in completed_with_parent:
            if child.get("parent_uuid") == parent_uuid:
                rollup_parent(db, child["uuid"], workspace_uuid=workspace_uuid)
                dep_mgr.cascade_unblock(db, child["uuid"])

        recovered += 1

    # Phase 2: OKR score reconciliation for objective entities
    # Objectives may have stale scores when KR children change status
    # without triggering parent phase completion.
    all_entities = db.list_entities(workspace_uuid=workspace_uuid)
    objectives = [
        e for e in all_entities
        if e.get("entity_type") == "objective"
    ]
    for obj in objectives:
        obj_uuid = obj["uuid"]
        children = db.get_children_by_uuid(obj_uuid)
        if not children:
            continue

        expected_score = compute_objective_score(db, obj_uuid)
        raw_meta = obj.get("metadata")
        meta = parse_metadata(raw_meta)
        stored_score = meta.get("score")

        if stored_score is not None:
            try:
                if abs(float(stored_score) - expected_score) < 1e-9:
                    continue  # already correct
            except (ValueError, TypeError):
                pass  # invalid stored score — recompute

        # Mismatch or missing score — update via metadata merge
        db.update_entity(obj_uuid, metadata={"score": expected_score})
        recovered += 1

    if recovered > 0:
        print(
            f"reconciliation: Recovered {recovered} missed cascades",
            file=__import__("sys").stderr,
        )

    return recovered


# ---------------------------------------------------------------------------
# Public API (Design I2)
# ---------------------------------------------------------------------------


def check_workflow_drift(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None = None,
    *,
    workspace_uuid: str | None = None,
) -> WorkflowDriftResult:
    """Detect workflow state drift between .meta.json and DB.

    Parameters
    ----------
    engine : WorkflowStateEngine
        Engine instance (for _derive_state_from_meta, _iter_meta_jsons,
        _feature_dir_name, _contained_feature_dir_name).
    db : EntityDatabase
        Database instance (for get_workflow_phase).
    artifacts_root : str
        Root directory for artifact files.
    feature_type_id : str | None
        If provided, check single feature. If None, scan all.
    workspace_uuid : str | None
        Feature 133 FR133-2.ii: forwarded to the bulk path's
        ``db.list_workflow_phases`` call so db_only detection is
        workspace-scoped. ``None`` preserves today's unscoped behavior
        exactly (orphan workflow_phases rows are always retained --
        see ``list_workflow_phases`` docstring). The per-feature
        comparison is not scoped: it reads the row by type_id alone
        (``workflow_phases`` is keyed by type_id), so a ``.meta.json`` of
        a feature only another workspace holds is compared against that
        workspace's row.

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
                dir_name = _single_feature_dir_name(engine, feature_type_id)
                artifact_dir = os.path.join(artifacts_root, "features", dir_name)
                report = _check_single_feature(engine, db, feature_type_id, meta, artifact_dir=artifact_dir)
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
        # Bulk path: scan all .meta.json files. Each report pairs the LISTED
        # directory with the type_id its name composes; the directory is
        # that listed name, containment-checked, never read back out of
        # the type_id and never looked up in the registry (C11).
        meta_type_ids: set[str] = set()
        for ftype_id, dirname, meta in engine._iter_meta_jsons():
            meta_type_ids.add(ftype_id)
            try:
                dir_name = engine._contained_feature_dir_name(ftype_id, dirname)
                artifact_dir = os.path.join(artifacts_root, "features", dir_name)
                report = _check_single_feature(engine, db, ftype_id, meta, artifact_dir=artifact_dir)
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

        # Detect db_only features via set difference. The kind is the joined
        # entities row's kind column (list_workflow_phases' ``e.kind AS
        # entity_type``), never the type_id text (C8):
        #   * a feature-kind row is a candidate; any other kind is excluded.
        #   * an ORPHAN row (no entities row, so entity_type is None; the
        #     query keeps orphans for anomaly visibility) has no kind, so it
        #     stays a candidate whatever its type_id spells. Feature-prefixed
        #     orphans keep their pre-C8 db_only status; orphans with any
        #     other prefix are now reported too.
        all_wp_rows = db.list_workflow_phases(workspace_uuid=workspace_uuid)
        db_rows_by_id = {
            row["type_id"]: row for row in all_wp_rows
            if row["entity_type"] == "feature" or row["entity_type"] is None
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

    summary["artifact_missing_count"] = sum(1 for r in reports if r.artifact_missing)

    return WorkflowDriftResult(features=tuple(reports), summary=summary)
