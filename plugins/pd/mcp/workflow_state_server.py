"""MCP workflow-engine server for phase read/write operations.

Runs as a subprocess via stdio transport.  Never print to stdout
(corrupts JSON-RPC protocol) -- all logging goes to stderr.
"""
from __future__ import annotations

import functools
import json
import os
import sqlite3
import sys
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from itertools import zip_longest
from pathlib import Path

# Feature 088 FR-7.2: internal cap on phase_events rows fetched for analytics.
# query_phase_analytics fetches up to this many rows per internal call before
# applying the caller-supplied `limit` (filter-then-truncate ordering).
_ANALYTICS_EVENT_SCAN_LIMIT = 500

# Make workflow_engine, transition_gate, entity_registry, semantic_memory
# importable from hooks/lib/ — safety net for direct invocation and tests.
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _hooks_lib)

from server_lifecycle import write_pid, remove_pid, start_parent_watchdog
from sqlite_retry import with_retry, is_transient

from entity_registry.database import EntityDatabase
from entity_registry.project_identity import _compute_legacy_project_id, resolve_workspace_uuid
from entity_registry.entity_lifecycle import (
    init_entity_workflow as _lib_init_entity_workflow,
    transition_entity_phase as _lib_transition_entity_phase,
)
from entity_registry.frontmatter_sync import (
    ARTIFACT_BASENAME_MAP,
    DriftReport,
    detect_drift,
    scan_all,
)
from entity_registry.metadata import parse_metadata
from semantic_memory.config import read_config
from semantic_memory.database import MemoryDatabase
from semantic_memory.embedding import EmbeddingProvider, create_provider
from semantic_memory.refresh import (
    refresh_memory_digest,
    build_refresh_query,
    _resolve_int_config,
    _refresh_warned_fields,
)
from transition_gate.models import Severity, TransitionResult
from workflow_engine.engine import WorkflowStateEngine
from workflow_engine.entity_engine import EntityWorkflowEngine
from workflow_engine.feature_lifecycle import (
    _atomic_json_write,
    _iso_now,
    _validate_feature_type_id,
    activate_feature as _lib_activate_feature,
    init_feature_state as _lib_init_feature_state,
    init_project_state as _lib_init_project_state,
)
from workflow_engine.kanban import derive_kanban
from workflow_engine.task_promotion import (
    TaskAlreadyPromotedError,
    TaskNotFoundError,
    promote_task as _lib_promote_task,
    query_ready_tasks as _lib_query_ready_tasks,
)
from workflow_engine.models import FeatureWorkflowState, TransitionResponse
from workflow_engine.rollup import get_ancestor_progress as _lib_get_ancestor_progress
from workflow_engine.notifications import NotificationQueue
from workflow_engine.reconciliation import (
    ReconcileAction,
    WorkflowDriftReport,
    apply_workflow_reconciliation,
    check_workflow_drift,
)

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Module-level globals (set during lifespan)
# ---------------------------------------------------------------------------

_db: EntityDatabase | None = None
_db_unavailable: bool = False
_recovery_thread: threading.Thread | None = None
_engine: WorkflowStateEngine | None = None
_entity_engine: EntityWorkflowEngine | None = None
_artifacts_root: str = ""
_project_root: str = ""
_project_id: str = ""
# Feature 108 Phase E + feature 112 FR-2: lazy workspace_uuid global.
# Populated during lifespan from ENTITY_WORKSPACE_UUID/WORKSPACE_UUID env or
# resolve_workspace_uuid(). Mirrors ``mcp/entity_server.py``'s pattern.
# Empty string until set; forwarded to engine functions as
# ``workspace_uuid=_workspace_uuid or None`` per the post-FR-2 wiring.
_workspace_uuid: str = ""
_notification_queue: NotificationQueue | None = None

# Feature 081: memory refresh digest — separate MemoryDatabase
# (~/.claude/pd/memory/memory.db, distinct from entities.db above) plus
# embedding provider + config dict mirrored from memory_server.py's lifespan.
_config: dict = {}
_provider: EmbeddingProvider | None = None
_memory_db: MemoryDatabase | None = None

# ---------------------------------------------------------------------------
# Degraded mode helpers
# ---------------------------------------------------------------------------


def _init_db_with_retry(
    db_path: str,
    max_retries: int = 3,
    backoff_seconds: float = 2.0,
) -> EntityDatabase | None:
    """Attempt DB initialization with retries.

    Returns EntityDatabase instance, or None if all retries failed.
    """
    for attempt in range(max_retries):
        try:
            return EntityDatabase(db_path)
        except sqlite3.OperationalError:
            if attempt < max_retries - 1:
                time.sleep(backoff_seconds)
    return None


def _start_recovery_thread(
    db_path: str,
    poll_interval: float = 30.0,
) -> threading.Thread:
    """Start daemon thread that retries DB initialization.

    On success: sets _db to new instance, clears _db_unavailable.
    Thread exits after successful recovery.
    """
    global _db, _db_unavailable, _engine, _entity_engine, _notification_queue, _project_root, _artifacts_root

    def _recover():
        global _db, _db_unavailable, _engine, _entity_engine, _notification_queue, _project_root, _artifacts_root
        while True:
            time.sleep(poll_interval)
            try:
                new_db = EntityDatabase(db_path)
                # Initialize engine and related objects
                project_root = os.environ.get("PROJECT_ROOT", os.getcwd())
                _project_root = project_root
                config = read_config(project_root)
                _artifacts_root = os.path.join(project_root, str(config.get("artifacts_root", "docs")))
                _engine = WorkflowStateEngine(new_db, _artifacts_root)
                _notification_queue = NotificationQueue()
                _entity_engine = EntityWorkflowEngine(
                    new_db, _artifacts_root, _notification_queue, project_root=_project_root
                )
                _db = new_db
                _db_unavailable = False
                print("workflow-engine: DB recovered", file=sys.stderr)
                return
            except sqlite3.OperationalError:
                continue

    thread = threading.Thread(target=_recover, name="db-recovery", daemon=True)
    thread.start()
    return thread


def _check_db_available() -> str | None:
    """Return error JSON if DB is unavailable, else None."""
    if _db_unavailable:
        return json.dumps({"error": "database temporarily unavailable"})
    return None


@asynccontextmanager
async def lifespan(server):
    """Manage DB connection and engine lifecycle."""
    global _db, _db_unavailable, _recovery_thread
    global _engine, _entity_engine, _artifacts_root, _project_root, _project_id, _workspace_uuid, _notification_queue
    global _config, _provider, _memory_db

    write_pid("workflow_state_server")
    start_parent_watchdog()

    db_path = os.environ.get(
        "ENTITY_DB_PATH",
        os.path.expanduser("~/.claude/pd/entities/entities.db"),
    )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    _db = _init_db_with_retry(db_path)
    if _db is None:
        _db_unavailable = True
        _recovery_thread = _start_recovery_thread(db_path)
        print("workflow-engine: started in degraded mode (DB unavailable)", file=sys.stderr)
    else:
        project_root = os.environ.get("PROJECT_ROOT", os.getcwd())
        _project_root = project_root
        _project_id = _compute_legacy_project_id(project_root)
        # Feature 108 Phase E: populate workspace_uuid lazy global with the
        # same FR-3 / Decision 11 precedence as mcp/entity_server.py:
        #   ENTITY_WORKSPACE_UUID env (test override / explicit)
        #     > WORKSPACE_UUID env (subprocess inheritance from hooks)
        #     > resolve_workspace_uuid(_project_root) (file → DB → fresh)
        # All resolution failures are best-effort; we never block startup.
        try:
            env_uuid = (
                os.environ.get("ENTITY_WORKSPACE_UUID")
                or os.environ.get("WORKSPACE_UUID")
                or ""
            )
            if env_uuid:
                _workspace_uuid = env_uuid
            else:
                _workspace_uuid = resolve_workspace_uuid(_project_root)
        except Exception as exc:
            print(
                f"workflow-engine: workspace_uuid resolution failed: {exc}",
                file=sys.stderr,
            )
            _workspace_uuid = ""
        config = read_config(project_root)
        _artifacts_root = os.path.join(project_root, str(config.get("artifacts_root", "docs")))

        _engine = WorkflowStateEngine(_db, _artifacts_root)
        _notification_queue = NotificationQueue()
        _entity_engine = EntityWorkflowEngine(
            _db, _artifacts_root, _notification_queue, project_root=_project_root
        )

        # Feature 081: populate memory-refresh globals (provider + memory.db).
        # Failures are non-fatal — memory_refresh silently omits, but operator
        # sees one stderr signal per failure mode.
        _config = config
        try:
            _provider = create_provider(config)
        except Exception as e:
            print(
                f"[workflow-state] memory_refresh disabled for this process: provider init failed: {e}",
                file=sys.stderr,
            )
        try:
            _memory_db = MemoryDatabase(
                str(Path.home() / ".claude" / "pd" / "memory" / "memory.db")
            )
        except Exception as e:
            print(
                f"[workflow-state] memory_refresh disabled for this process: memory_db init failed: {e}",
                file=sys.stderr,
            )

        print(f"workflow-engine: started (db={db_path}, artifacts={_artifacts_root})", file=sys.stderr)

    try:
        yield {}
    finally:
        remove_pid("workflow_state_server")
        if _db is not None:
            _db.close()
            _db = None
        if _memory_db is not None:
            _memory_db.close()
            _memory_db = None
        _engine = None
        _entity_engine = None
        _notification_queue = None


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_state(state: FeatureWorkflowState) -> dict:
    """Convert FeatureWorkflowState to JSON-serializable dict."""
    return {
        "feature_type_id": state.feature_type_id,
        "current_phase": state.current_phase,
        "last_completed_phase": state.last_completed_phase,
        "mode": state.mode,
        "degraded": state.source == "meta_json_fallback",
    }


def _serialize_result(result: TransitionResult) -> dict:
    """Convert TransitionResult to JSON-serializable dict.

    guard_id is always a non-None string — the engine guarantees this
    for all gate evaluations.
    """
    return {
        "allowed": result.allowed,
        "reason": result.reason,
        "severity": result.severity.value,
        "guard_id": result.guard_id,
    }


def _serialize_workflow_drift_report(report: WorkflowDriftReport) -> dict:
    """Convert WorkflowDriftReport to JSON-serializable dict."""
    return {
        "feature_type_id": report.feature_type_id,
        "status": report.status,
        "meta_json": report.meta_json,
        "db": report.db,
        "mismatches": [
            {"field": m.field, "meta_json_value": m.meta_json_value, "db_value": m.db_value}
            for m in report.mismatches
        ],
    }


def _serialize_reconcile_action(action: ReconcileAction) -> dict:
    """Convert ReconcileAction to JSON-serializable dict.

    For meta_json_to_db direction: old_value = DB (being overwritten),
    new_value = .meta.json (source of truth).
    """
    return {
        "feature_type_id": action.feature_type_id,
        "action": action.action,
        "direction": action.direction,
        "changes": [
            {"field": c.field, "old_value": c.db_value, "new_value": c.meta_json_value}
            for c in action.changes
        ],
        "message": action.message,
    }


def _serialize_drift_report(report: DriftReport) -> dict:
    """Convert frontmatter_sync.DriftReport to JSON-serializable dict."""
    return {
        "filepath": report.filepath,
        "type_id": report.type_id,
        "status": report.status,
        "file_fields": report.file_fields,
        "db_fields": report.db_fields,
        "mismatches": [
            {"field": m.field, "file_value": m.file_value, "db_value": m.db_value}
            for m in report.mismatches
        ],
    }


def _build_frontmatter_summary(reports: list[DriftReport]) -> dict[str, int]:
    """Count frontmatter drift reports by status."""
    summary: dict[str, int] = {
        "in_sync": 0, "file_only": 0, "db_only": 0,
        "diverged": 0, "no_header": 0, "error": 0,
    }
    for r in reports:
        if r.status in summary:
            summary[r.status] += 1
        else:
            summary["error"] += 1
    return summary


# ---------------------------------------------------------------------------
# Projection function
# ---------------------------------------------------------------------------


def _read_entity_display(
    db: EntityDatabase,
    entity_uuid: str | None,
    feature_type_id: str,
    metadata: dict,
    *,
    entity_id_hint: str | None = None,
) -> tuple[str, str]:
    """Return ``(id, slug)`` for an entity, preferring the ``entity_display``
    side table over ``metadata`` JSON (feature 110 FR-8.3b).

    Defense-in-depth: if the entity_display row is missing (test fixtures
    using ``_register_entity_no_display``, or rows registered before
    migration 13 / pre-migration callers), emit a stderr WARN and fall back
    to ``metadata.id`` / ``metadata.slug``.

    The function intentionally returns ``str`` for both fields so the
    downstream ``.meta.json`` shape is stable. ``id`` is the integer ``seq``
    serialized via ``str(seq)``. Zero-padding width is recovered from
    (1) ``metadata.id`` if it's a digit string, else (2) ``entity_id_hint``'s
    leading numeric prefix (i.e., ``entities.entity_id``), else (3) no
    padding. AC-8.5 specifically requires that the projection output is
    byte-identical even when ``metadata.id`` has been removed — so the
    ``entity_id_hint`` fallback is load-bearing.
    """

    def _width_from(value: str | None) -> int:
        if not value:
            return 0
        head = value.split("-", 1)[0]
        return len(head) if head.isdigit() else 0

    if entity_uuid:
        # Use the public encapsulated helper instead of raw _conn access;
        # the helper returns None on pre-migration-13 DBs and on missing
        # rows.
        row = db.get_entity_display(entity_uuid)
        if row is not None:
            seq, slug = row["seq"], row["slug"]
            # Recover zero-pad width. Order: metadata.id → entity_id prefix.
            width = _width_from(metadata.get("id"))
            if width == 0:
                width = _width_from(entity_id_hint)
            return (str(seq).zfill(width) if width else str(seq)), slug
    # Fallback (WARN): entity_display row missing.
    sys.stderr.write(
        f"[workflow-state] _project_meta_json: no entity_display row for "
        f"{feature_type_id!r} (uuid={entity_uuid!r}); falling back to "
        f"metadata id/slug\n"
    )
    return metadata.get("id", ""), metadata.get("slug", "")


def _project_meta_json(
    db: EntityDatabase,
    engine: WorkflowStateEngine | None,
    feature_type_id: str,
    feature_dir: str | None = None,
) -> str | None:
    """Regenerate .meta.json from DB + engine state. Returns warning string or None.

    Uses engine.get_state() as authoritative source for last_completed_phase
    and current_phase. Falls back to entity metadata if engine is None or
    engine state unavailable. Phase timing details (iterations, reviewerNotes)
    come from entity metadata only (engine doesn't track these).
    """
    entity = db.get_entity(feature_type_id)
    if entity is None:
        return f"entity not found: {feature_type_id}"

    if feature_dir is None:
        feature_dir = entity.get("artifact_path")
        if not feature_dir:
            return f"artifact_path not set and no feature_dir provided: {feature_type_id}"

    meta_path = os.path.join(feature_dir, ".meta.json")

    # Parse metadata -- it's a JSON TEXT column, not a dict
    raw_metadata = entity.get("metadata")
    if raw_metadata:
        metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
    else:
        metadata = {}

    phase_timing = metadata.get("phase_timing", {})

    # Get authoritative state from engine when available
    if engine is not None:
        engine_state = engine.get_state(feature_type_id)
        last_completed = (
            engine_state.last_completed_phase if engine_state else None
        )
    else:
        last_completed = metadata.get("last_completed_phase")

    # Feature 110 Group 5 (FR-8.3b): read seq + slug from entity_display
    # table when available. Falls back to metadata JSON with a WARN log if
    # the row is missing (defense-in-depth: test fixtures using
    # _register_entity_no_display, or rows registered before migration 13).
    display_id, display_slug = _read_entity_display(
        db,
        entity.get("uuid"),
        feature_type_id,
        metadata,
        entity_id_hint=entity.get("entity_id"),
    )

    # Build .meta.json structure
    meta = {
        "id": display_id,
        "slug": display_slug,
        "mode": metadata.get("mode", "standard"),
        "status": entity.get("status") or "active",
        "created": entity.get("created_at") or _iso_now(),
        "branch": metadata.get("branch", ""),
    }

    # Top-level completed timestamp for terminal statuses (R1/R2/R4)
    # Also trigger on last_completed == "finish" as a defensive fallback
    # when entity status hasn't propagated yet (e.g., status=None in DB).
    if meta["status"] in ("completed", "abandoned") or last_completed == "finish":
        finish_completed = phase_timing.get("finish", {}).get("completed")
        meta["completed"] = finish_completed or _iso_now()

    # Optional fields -- only include when present
    if metadata.get("brainstorm_source"):
        meta["brainstorm_source"] = metadata["brainstorm_source"]
    if metadata.get("backlog_source"):
        meta["backlog_source"] = metadata["backlog_source"]

    # Workflow state (engine is authoritative when available)
    meta["lastCompletedPhase"] = last_completed

    # Phases from phase_timing metadata
    phases = {}
    for phase_name, timing in phase_timing.items():
        phase_entry = {}
        if timing.get("started"):
            phase_entry["started"] = timing["started"]
        if timing.get("completed"):
            phase_entry["completed"] = timing["completed"]
        if timing.get("iterations") is not None:
            phase_entry["iterations"] = timing["iterations"]
        if timing.get("reviewerNotes"):
            phase_entry["reviewerNotes"] = timing["reviewerNotes"]
        if phase_entry:
            phases[phase_name] = phase_entry
    meta["phases"] = phases

    # Skipped phases
    if metadata.get("skipped_phases"):
        meta["skippedPhases"] = metadata["skipped_phases"]

    # Backward travel fields (feature 073)
    if metadata.get("backward_context"):
        meta["backward_context"] = metadata["backward_context"]
    if metadata.get("backward_return_target"):
        meta["backward_return_target"] = metadata["backward_return_target"]
    # backward_history is audit-only — stays in DB, not projected to .meta.json

    # Phase summaries (feature 075)
    if metadata.get("phase_summaries"):
        meta["phase_summaries"] = metadata["phase_summaries"]

    # Atomic write (fail-open)
    try:
        _atomic_json_write(meta_path, meta)
        return None  # success
    except Exception as exc:
        return f"projection failed: {exc}"


# F4-AUDIT: backlog projection (feature 110 FR-4.2, TD-10).
def _project_backlog_md(db: EntityDatabase) -> str:
    """Build a deterministic markdown representation of ``docs/backlog.md``
    from the entity registry (feature 110 FR-4.2 / TD-10).

    All timestamp and identity fields source from DB columns
    (``entities.created_at``, ``entities.name``, ``entities.entity_id``,
    ``entities.metadata``). No ``datetime.utcnow()`` / ``datetime.now()``
    calls — AC-4.2 static-checks this contract.

    Two formats per TD-10:
      - ``metadata.format == "table_row"`` (default for general backlog
        items): emitted as a pipe-table row under the top-level table.
      - ``metadata.format == "bullet_item"``: emitted as a bullet
        (``- **#{seq:05d}** {name}``) under the appropriate
        ``## From Feature N ...`` section identified by
        ``metadata.section``.

    Section ordering: sections appear in the order of the FIRST entity
    created in them (``min(created_at)`` per section). Within a section,
    rows are sorted by ``seq`` ascending.

    Optional metadata keys:
      - ``section_intro``: prose paragraph emitted after the section
        header (sourced from the first entity in that section that
        carries the key — deterministic because sections are sorted by
        ``min(created_at)`` and rows within sections are sorted by seq).
      - ``subsection``: emitted as ``### {subsection}`` before the first
        entity bearing that subsection within a section. Only the first
        occurrence per ``(section, subsection)`` pair emits the header.

    Returns
    -------
    str
        Markdown string. Archived rows (``status='archived'``) are
        excluded from the main table per design TD-10.
    """
    # Collect every backlog entity across all workspaces (cross-project
    # backlog is a single file). ``list_entities`` returns dict rows with
    # ``entity_id``, ``name``, ``created_at``, ``metadata``, ``status``,
    # ``uuid``.
    rows = db.list_entities(entity_type="backlog")

    # Exclude archived rows from the main projection (per design TD-10).
    rows = [r for r in rows if (r.get("status") or "") != "archived"]

    # Decorate rows with parsed metadata + (seq, slug) from entity_display
    # (preferred) or entity_id fallback. NO datetime.now/utcnow call here.
    decorated: list[dict] = []
    for row in rows:
        raw_md = row.get("metadata")
        if raw_md:
            md = (
                json.loads(raw_md)
                if isinstance(raw_md, str)
                else raw_md
            )
        else:
            md = {}

        # Identity: prefer entity_display side table; fall back to
        # parsing entity_id (feature 110 FR-8.3b style).
        entity_id = row.get("entity_id") or ""
        display = db.get_entity_display(row.get("uuid")) if row.get("uuid") else None
        if display is not None:
            seq = display["seq"]
            slug = display["slug"]
        else:
            # Fallback: parse from entity_id. Backlog ids are typically
            # zero-padded 5-digit integers (e.g., "00008"); a dash-slug
            # form ("001-foo") is also supported per the strict format
            # contract. Empty/non-numeric IDs sort last with seq=0.
            if "-" in entity_id:
                head, _, tail = entity_id.partition("-")
                try:
                    seq = int(head)
                except ValueError:
                    seq = 0
                slug = tail
            else:
                try:
                    seq = int(entity_id)
                except ValueError:
                    seq = 0
                slug = ""

        decorated.append({
            "uuid": row.get("uuid") or "",
            "entity_id": entity_id,
            "seq": seq,
            "slug": slug,
            "name": row.get("name") or "",
            "created_at": row.get("created_at") or "",
            "metadata": md,
            "format": md.get("format") or "table_row",
            "section": md.get("section"),  # may be None
            "section_intro": md.get("section_intro"),
            "subsection": md.get("subsection"),
        })

    # Partition into top-level table rows vs section bullets.
    table_rows = [
        d for d in decorated
        if d["format"] == "table_row"
    ]
    bullet_rows = [d for d in decorated if d["format"] == "bullet_item"]

    # Sort table rows by seq ascending (stable on entity_id tiebreaker
    # so that deterministic ordering survives duplicate seq).
    table_rows.sort(key=lambda d: (d["seq"], d["entity_id"]))

    # Group bullet rows by section in order of FIRST creation per
    # section (deterministic groupby on min(created_at)).
    sections: dict[str, list[dict]] = {}
    for d in bullet_rows:
        sec = d["section"] or ""
        sections.setdefault(sec, []).append(d)
    # Sort each section's rows by seq + entity_id.
    for sec in sections:
        sections[sec].sort(key=lambda d: (d["seq"], d["entity_id"]))
    # Section header ordering = min(created_at) per section, then
    # section name to break ties when timestamps are equal.
    section_order = sorted(
        sections.keys(),
        key=lambda s: (
            min((d["created_at"] for d in sections[s]), default=""),
            s,
        ),
    )

    # Build output. Use \n line endings (deterministic; matches existing
    # docs/backlog.md). Always end with a single trailing newline.
    out: list[str] = ["# Backlog", ""]
    out.append("| ID | Timestamp | Description |")
    out.append("|----|-----------|-------------|")
    for d in table_rows:
        seq_str = f"{d['seq']:05d}"
        # Escape pipe characters in name (description) to avoid breaking
        # the markdown table layout (matches add-to-backlog convention).
        name_escaped = d["name"].replace("|", "\\|")
        out.append(f"| {seq_str} | {d['created_at']} | {name_escaped} |")

    # Per-section bullets.
    for sec in section_order:
        if not sec:
            # Defensive: section bullets without a section header are
            # rendered under an "Uncategorized" pseudo-section. In
            # practice this never fires because rendering requires
            # metadata.format=='bullet_item' which is only set when the
            # backfill parser identifies a section.
            section_header = "## Uncategorized"
        else:
            section_header = f"## {sec}"
        out.append("")
        out.append(section_header)

        # Emit section_intro from the first entity in the section that
        # carries one (deterministic — list already sorted by seq).
        intro_text: str | None = None
        for d in sections[sec]:
            if d["section_intro"]:
                intro_text = d["section_intro"]
                break
        if intro_text:
            out.append("")
            out.append(intro_text)

        # Emit bullets. Track which (section, subsection) pairs have
        # already emitted their `### Subsection` header so we only
        # render each once.
        emitted_subsections: set[str] = set()
        first_bullet_pending = True
        for d in sections[sec]:
            subsection = d["subsection"]
            if subsection and subsection not in emitted_subsections:
                emitted_subsections.add(subsection)
                out.append("")
                out.append(f"### {subsection}")
                first_bullet_pending = True
            if first_bullet_pending:
                out.append("")
                first_bullet_pending = False
            seq_str = f"{d['seq']:05d}"
            name_escaped = d["name"]
            out.append(f"- **#{seq_str}** {name_escaped}")

    out.append("")  # trailing newline
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Processing functions
# ---------------------------------------------------------------------------


def _make_error(error_type: str, message: str, recovery_hint: str) -> str:
    """Create structured JSON error response for MCP tools."""
    return json.dumps({
        "error": True,
        "error_type": error_type,
        "message": message,
        "recovery_hint": recovery_hint,
    })


def _resolve_project_id(entity: dict) -> str:
    """Resolve ``project_id`` from an entity record, distinguishing missing
    (legitimate legacy data) from empty-string (data-integrity bug).

    Feature 089 FR-2.3 / AC-10 / #00151. Replaces the ambiguous
    ``entity.get('project_id') or '__unknown__'`` idiom that silently
    conflated the two cases.

    - ``None``: legacy row predating project_id enforcement — silent
      fallback to ``'__unknown__'``.
    - Empty string: data-integrity issue — emit a stderr warning AND
      fall back to ``'__unknown__'`` so dual-writes still succeed.
    - Non-empty: return as-is.
    """
    pid = entity.get("project_id")
    if pid is None:
        return "__unknown__"
    if not pid:
        sys.stderr.write(
            f'[workflow-state] feature {entity.get("type_id", "?")} '
            f'has empty project_id (data integrity issue)\n'
        )
        return "__unknown__"
    return pid


def _with_error_handling(func):
    """Wrap _process_* functions with standard DB/internal error handling."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except sqlite3.Error as exc:
            return _make_error(
                "db_unavailable",
                f"Database error: {type(exc).__name__}: {exc}",
                "Check database file permissions and disk space",
            )
        except Exception as exc:
            return _make_error(
                "internal",
                f"Internal error: {type(exc).__name__}: {exc}",
                "Report this error — it may indicate a bug",
            )
    return wrapper


def _catch_value_error(func):
    """Wrap functions that raise ValueError for invalid user input.

    Prefix-based routing: checks for "feature_not_found:" prefix first
    (new convention from _validate_feature_type_id), then falls back to
    substring match for "not found" (existing engine.py convention).
    All other ValueErrors map to 'invalid_transition'.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as exc:
            msg = str(exc)
            if msg.startswith("feature_not_found:") or "not found" in msg.lower():
                return _make_error(
                    "feature_not_found",
                    msg,
                    "Verify feature_type_id format: 'feature:{id}-{slug}'",
                )
            return _make_error(
                "invalid_transition",
                msg,
                "Check current phase with get_phase before transitioning",
            )
    return wrapper


_ENTITY_RECOVERY_HINTS = {
    "entity_not_found": "Verify type_id exists via get_entity",
    "invalid_entity_type": "Only brainstorm and backlog entities support lifecycle transitions",
    "invalid_transition": "Check current phase — transition may not be valid from current state",
}


def _catch_entity_value_error(func):
    """Map entity-related ValueErrors to structured error dicts."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            msg = str(e)
            for prefix in ("entity_not_found:", "invalid_entity_type:", "invalid_transition:"):
                if msg.startswith(prefix):
                    error_type = prefix.rstrip(":")
                    return _make_error(error_type, msg, _ENTITY_RECOVERY_HINTS.get(error_type, ""))
            raise
    return wrapper


_is_transient = is_transient


def _with_retry(**kwargs):
    """Retry decorator for transient SQLite write errors.

    Delegates to shared sqlite_retry.with_retry with server_name="workflow-state".

    Applied INSIDE _with_error_handling so retries happen before
    the error is converted to a terminal MCP response.

    Decorator stacking order:
      @_with_error_handling    <- outer: catches final exception, returns JSON error
      _with_retry()            <- middle: retries transient errors before they reach outer
      @_catch_value_error      <- inner: converts ValueError to structured error
      def _process_foo(...)
    """
    return with_retry("workflow-state", **kwargs)


@_with_error_handling
def _process_get_phase(engine: WorkflowStateEngine, feature_type_id: str) -> str:
    state = engine.get_state(feature_type_id)
    if state is None:
        return _make_error(
            "feature_not_found",
            f"Feature not found: {feature_type_id}",
            "Verify feature_type_id format: 'feature:{id}-{slug}'",
        )
    return json.dumps(_serialize_state(state))


@_with_error_handling
@_with_retry()
@_catch_value_error
def _process_transition_phase(
    engine: WorkflowStateEngine,
    feature_type_id: str,
    target_phase: str,
    yolo_active: bool,
    db: EntityDatabase | None = None,
    skipped_phases: str | None = None,
    entity_engine: EntityWorkflowEngine | None = None,
) -> str:
    # Task 3.4: Check blocked_by via entity engine before transition.
    # For features, we still delegate to frozen engine for the actual transition
    # (entity_engine.transition_phase checks blockers then delegates).
    transitioned = False
    warning = None
    # Feature 088 FR-5.1: capture entity, ts, skipped_list OUTSIDE transaction
    # so the post-commit phase_events dual-write can reference them even if
    # the transaction aborted before these were populated.
    entity = None
    ts: str | None = None
    skipped_list: list[str] = []

    if db is not None:
        with db.transaction():
            if entity_engine is not None:
                entity = db.get_entity(feature_type_id)
                if entity is not None:
                    try:
                        # FR-6.2: Empty-string == unset == None at db.* kwarg boundary;
                        # downstream defaults to project_id="__unknown__" → _UNKNOWN_WORKSPACE_UUID.
                        response = entity_engine.transition_phase(
                            entity["uuid"], target_phase,
                            workspace_uuid=_workspace_uuid or None,
                        )
                    except ValueError as exc:
                        # Blocked or invalid — return as structured error
                        return _make_error(
                            "invalid_transition",
                            str(exc),
                            "Check blocked_by dependencies or current phase",
                        )
                else:
                    response = engine.transition_phase(
                    feature_type_id, target_phase, yolo_active,
                    workspace_uuid=_workspace_uuid or None,
                )
            else:
                response = engine.transition_phase(
                    feature_type_id, target_phase, yolo_active,
                    workspace_uuid=_workspace_uuid or None,
                )

            if response.degraded:
                raise sqlite3.OperationalError(
                    "engine returned degraded=True inside transaction"
                )

            transitioned = all(r.allowed for r in response.results)

            if transitioned:
                # Store phase timing in entity metadata
                entity = db.get_entity(feature_type_id)
                raw_metadata = entity.get("metadata") if entity else None
                if raw_metadata:
                    metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
                else:
                    metadata = {}

                phase_timing = metadata.get("phase_timing", {})
                phase_timing.setdefault(target_phase, {})
                ts = _iso_now()
                phase_timing[target_phase]["started"] = ts
                metadata["phase_timing"] = phase_timing

                # Store skipped phases if provided
                if skipped_phases:
                    skipped_list = json.loads(skipped_phases)
                    metadata["skipped_phases"] = skipped_list

                db.update_entity(
                    feature_type_id, metadata=metadata,
                    workspace_uuid=_workspace_uuid or None,
                )

                # Update kanban_column for features based on phase
                if feature_type_id.startswith("feature:"):
                    kanban = derive_kanban("active", target_phase)
                    db.update_workflow_phase(feature_type_id, kanban_column=kanban)
    else:
        response = engine.transition_phase(
            feature_type_id, target_phase, yolo_active,
            workspace_uuid=_workspace_uuid or None,
        )
        transitioned = all(r.allowed for r in response.results)

    # Feature 088 FR-5.1: Dual-write phase_events AFTER main transaction commits.
    # Failure here MUST NOT roll back the primary workflow write.
    phase_events_write_failed = False
    if db is not None and transitioned and entity is not None and ts is not None:
        # Feature 089 FR-2.3 (#00151): distinguish missing vs empty project_id.
        project_id = _resolve_project_id(entity)
        try:
            # Feature 109 Group 9.6: pass workspace_uuid for consistency
            # (optional for workflow event types per design §3.1; the helper
            # uses type_id-keyed UPDATE for workflow_phases).
            db.append_phase_event(
                type_id=feature_type_id,
                project_id=project_id,
                phase=target_phase,
                event_type="started",
                timestamp=ts,
                workspace_uuid=_workspace_uuid or None,
            )
            for skipped in skipped_list:
                db.append_phase_event(
                    type_id=feature_type_id,
                    project_id=project_id,
                    phase=skipped,
                    event_type="skipped",
                    timestamp=ts,
                    workspace_uuid=_workspace_uuid or None,
                )
        except Exception as exc:
            phase_events_write_failed = True
            sys.stderr.write(
                f"[workflow-state] phase_events dual-write failed for "
                f"{feature_type_id}:{target_phase}: "
                f"{type(exc).__name__}: {str(exc)[:200]}\n"
            )

    result: dict = {
        "transitioned": transitioned,
        "results": [_serialize_result(r) for r in response.results],
        "degraded": response.degraded,
    }
    if phase_events_write_failed:
        result["phase_events_write_failed"] = True

    # Filesystem write AFTER transaction committed
    if transitioned and db is not None:
        warning = _project_meta_json(db, engine, feature_type_id)

        # Retrieve started_at from committed data
        entity = db.get_entity(feature_type_id)
        raw_metadata = entity.get("metadata") if entity else None
        if raw_metadata:
            metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
        else:
            metadata = {}
        phase_timing = metadata.get("phase_timing", {})
        result["started_at"] = phase_timing.get(target_phase, {}).get("started")
        if skipped_phases:
            result["skipped_phases_stored"] = True
        if warning:
            result["projection_warning"] = warning

    return json.dumps(result)


# ---------------------------------------------------------------------------
# Artifact completeness check (AC-5)
# ---------------------------------------------------------------------------

# Expected artifacts per mode for finish-phase completeness warning.
# Light mode deferred to task 1b.10.
_EXPECTED_ARTIFACTS: dict[str, list[str]] = {
    "standard": ["spec.md", "tasks.md", "retro.md"],
    "full": ["spec.md", "design.md", "plan.md", "tasks.md", "retro.md"],
    "light": ["spec.md"],
}


def _check_artifact_completeness(
    db: EntityDatabase,
    feature_type_id: str,
) -> list[str]:
    """Check for missing expected artifacts on finish. Returns list of warnings."""
    entity = db.get_entity(feature_type_id)
    if entity is None:
        return []

    artifact_path = entity.get("artifact_path")
    if not artifact_path or not os.path.isdir(artifact_path):
        return []

    # Read mode from workflow_phases table
    wf = db.get_workflow_phase(feature_type_id)
    mode = (wf.get("mode") if wf else None) or "standard"

    expected = _EXPECTED_ARTIFACTS.get(mode)
    if expected is None:
        return []

    missing = [
        name for name in expected
        if not os.path.isfile(os.path.join(artifact_path, name))
    ]

    return [f"Missing artifact: {name}" for name in missing]


@_with_error_handling
@_with_retry()
@_catch_value_error
def _process_complete_phase(
    engine: WorkflowStateEngine,
    feature_type_id: str,
    phase: str,
    db: EntityDatabase | None = None,
    iterations: int | None = None,
    reviewer_notes: str | None = None,
    entity_engine: EntityWorkflowEngine | None = None,
) -> str:
    # Task 3.4: Route through EntityWorkflowEngine for cascade support.
    # If entity_engine is available, use it (handles frozen engine delegation
    # + cascade internally). Fall back to frozen engine if not wired yet.
    completion = None
    warning = None

    # Feature 088 FR-2.4: entry-point reviewer_notes size guard.
    if reviewer_notes and len(reviewer_notes) > 10000:
        return _make_error(
            "oversized_reviewer_notes",
            f"reviewer_notes size {len(reviewer_notes)} exceeds 10000",
            "Reduce reviewer_notes payload size",
        )
    # Parse JSON exactly once (the original code parsed twice — once for
    # phase_timing metadata, again for phase_events insert).
    try:
        parsed_notes = json.loads(reviewer_notes) if reviewer_notes else None
    except json.JSONDecodeError as exc:
        return _make_error(
            "invalid_reviewer_notes",
            f"reviewer_notes is not valid JSON: {exc.msg}",
            "Pass a JSON-serializable payload",
        )

    # Feature 088 FR-5.1: capture entity and timestamp OUTSIDE transaction
    # so the post-commit phase_events dual-write can reference them even if
    # the transaction aborted before these were populated.
    entity = None
    ts: str | None = None

    # First db.get_entity for UUID resolution stays OUTSIDE transaction
    if db is not None:
        with db.transaction():
            if entity_engine is not None:
                entity = db.get_entity(feature_type_id)
                if entity is not None:
                    completion = entity_engine.complete_phase(
                        entity["uuid"], phase,
                        workspace_uuid=_workspace_uuid or None,
                    )
                    state = completion.state
                    if state is None:
                        return _make_error(
                            "completion_failed",
                            f"Phase completion returned no state for {feature_type_id}",
                            "Check entity type and phase validity",
                        )
                else:
                    # Entity not in registry — fall back to frozen engine
                    state = engine.complete_phase(
                        feature_type_id, phase,
                        workspace_uuid=_workspace_uuid or None,
                    )
            else:
                state = engine.complete_phase(
                    feature_type_id, phase,
                    workspace_uuid=_workspace_uuid or None,
                )

            if getattr(completion, 'degraded', False) if completion is not None else getattr(state, '_degraded', False) if hasattr(state, '_degraded') else False:
                raise sqlite3.OperationalError(
                    "engine returned degraded inside transaction"
                )

            # Store timing metadata in entity (MCP-layer responsibility)
            entity = db.get_entity(feature_type_id)
            if entity is None:
                return _make_error(
                    "feature_not_found",
                    f"Feature not found after completion: {feature_type_id}",
                    "Verify feature_type_id format: 'feature:{id}-{slug}'",
                )

            raw_metadata = entity.get("metadata")
            if raw_metadata:
                metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
            else:
                metadata = {}

            phase_timing = metadata.get("phase_timing", {})
            phase_timing.setdefault(phase, {})
            ts = _iso_now()
            phase_timing[phase]["completed"] = ts
            if iterations is not None:
                phase_timing[phase]["iterations"] = iterations
            if parsed_notes is not None:
                phase_timing[phase]["reviewerNotes"] = parsed_notes
            metadata["phase_timing"] = phase_timing
            metadata["last_completed_phase"] = phase

            # Feature 088 FR-5.1 (ordering swap): update_entity(metadata) MUST
            # run INSIDE the transaction; append_phase_event is dispatched
            # AFTER the transaction commits (below). This prevents a phase_events
            # failure from silently rolling back the primary workflow write.
            db.update_entity(
                feature_type_id, metadata=metadata,
                workspace_uuid=_workspace_uuid or None,
            )

            # Update kanban_column for features based on completed phase
            if feature_type_id.startswith("feature:"):
                status = "completed" if phase == "finish" else "active"
                kanban = derive_kanban(status, state.current_phase)
                db.update_workflow_phase(feature_type_id, kanban_column=kanban)
    else:
        state = engine.complete_phase(feature_type_id, phase)

    # Feature 088 FR-5.1: Dual-write phase_events AFTER main transaction commits.
    # Failure here MUST NOT roll back the primary workflow write.
    phase_events_write_failed = False
    if db is not None and entity is not None and ts is not None:
        # Feature 089 FR-2.3 (#00151): distinguish missing vs empty project_id.
        project_id = _resolve_project_id(entity)
        try:
            # Feature 109 Group 9.6: pass workspace_uuid (optional for
            # workflow event types per design §3.1).
            db.append_phase_event(
                type_id=feature_type_id,
                project_id=project_id,
                phase=phase,
                event_type="completed",
                timestamp=ts,
                iterations=iterations,
                reviewer_notes=(
                    json.dumps(parsed_notes) if parsed_notes is not None else None
                ),
                workspace_uuid=_workspace_uuid or None,
            )
        except Exception as exc:
            phase_events_write_failed = True
            sys.stderr.write(
                f"[workflow-state] phase_events dual-write failed for "
                f"{feature_type_id}:{phase}: "
                f"{type(exc).__name__}: {str(exc)[:200]}\n"
            )

    result = _serialize_state(state)

    if phase_events_write_failed:
        result["phase_events_write_failed"] = True

    # Add cascade info when entity engine was used
    if completion is not None:
        if completion.unblocked_uuids:
            result["unblocked_count"] = len(completion.unblocked_uuids)
        if completion.parent_progress is not None:
            result["parent_progress"] = completion.parent_progress
        if completion.cascade_error:
            result["cascade_warning"] = completion.cascade_error

    # Filesystem write AFTER transaction committed
    if db is not None:
        warning = _project_meta_json(db, engine, feature_type_id)

        # Read committed timing data
        entity = db.get_entity(feature_type_id)
        if entity is not None:
            raw_metadata = entity.get("metadata")
            if raw_metadata:
                metadata = json.loads(raw_metadata) if isinstance(raw_metadata, str) else raw_metadata
            else:
                metadata = {}
            phase_timing = metadata.get("phase_timing", {})
            result["completed_at"] = phase_timing.get(phase, {}).get("completed")
        if warning:
            result["projection_warning"] = warning

        # Artifact completeness warning on finish (AC-5)
        if phase == "finish":
            artifact_warnings = _check_artifact_completeness(
                db, feature_type_id,
            )
            if artifact_warnings:
                result["artifact_warnings"] = artifact_warnings

    # Feature 081: memory refresh digest (additive).
    # Four-part gate: entity DB live, memory DB live, the phase transition
    # actually completed (result.last_completed_phase set), and config enables.
    # Failing any gate omits the field silently — callers tolerate absence.
    if (
        db is not None
        and _memory_db is not None
        and result.get("last_completed_phase")
        and _config.get("memory_refresh_enabled", True)
    ):
        query = build_refresh_query(feature_type_id, phase)
        if query:
            limit = _resolve_int_config(
                _config, "memory_refresh_limit", 5,
                clamp=(1, 20), warned=_refresh_warned_fields,
            )
            digest = refresh_memory_digest(
                _memory_db, _provider, query, limit,
                config=_config,
                feature_type_id=feature_type_id,
                completed_phase=phase,
            )
            if digest:
                result["memory_refresh"] = digest

    return json.dumps(result)


@_with_error_handling
@_catch_value_error
def _process_validate_prerequisites(
    engine: WorkflowStateEngine,
    feature_type_id: str,
    target_phase: str,
) -> str:
    results = engine.validate_prerequisites(feature_type_id, target_phase)
    all_passed = all(r.allowed for r in results)
    return json.dumps({
        "all_passed": all_passed,
        "results": [_serialize_result(r) for r in results],
    })


@_with_error_handling
def _process_list_features_by_phase(engine: WorkflowStateEngine, phase: str) -> str:
    states = engine.list_by_phase(phase)
    return json.dumps([_serialize_state(s) for s in states])


@_with_error_handling
def _process_list_features_by_status(engine: WorkflowStateEngine, status: str) -> str:
    states = engine.list_by_status(status)
    return json.dumps([_serialize_state(s) for s in states])


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Reconciliation processing functions
# ---------------------------------------------------------------------------


def _detect_phase_events_drift(
    db: EntityDatabase,
    feature_type_id: str | None,
) -> list[dict]:
    """Detect entities whose metadata.phase_timing or skipped_phases list
    lacks a matching ``phase_events`` row (Feature 088 FR-10.9 / AC-42,
    extended by Feature 089 FR-2.1 / AC-8 / #00146 to also cover
    ``started`` and ``skipped`` events).

    Dual-write drift between ``entities.metadata`` and the ``phase_events``
    append-only log can accumulate when the analytics write (which runs
    OUTSIDE the main transaction per FR-5.1) fails silently or when
    historical rows pre-date migration 10. This helper enumerates the
    drift — the apply path warns but does NOT auto-insert (additive-safe).

    Feature 089 FR-2.2 / AC-9 / #00150: uses ``query_phase_events_bulk``
    (single chunked IN query) instead of N+1 per-entity calls.

    Returns a list of drift entry dicts. Each entry has keys:
    ``kind``, ``type_id``, ``phase``, ``metadata_completed_at``.
    The ``kind`` is one of ``phase_events_missing_started``,
    ``phase_events_missing_completed``, ``phase_events_missing_skipped``.
    For ``started``/``skipped`` entries, ``metadata_completed_at`` carries
    the corresponding ``started`` timestamp (or ``""`` for ``skipped``,
    which has no timestamp in metadata).
    """
    drift: list[dict] = []
    if feature_type_id:
        entities = [db.get_entity(feature_type_id)]
    else:
        # ``list_entities`` accepts no ``status`` kwarg — filter Python-side.
        all_features = db.list_entities(entity_type="feature")
        entities = [e for e in all_features if e and e.get("status") == "active"]

    # Filter to real entities and build type_id list for the bulk query.
    entities = [e for e in entities if e]
    if not entities:
        return drift

    type_ids = [e["type_id"] for e in entities]

    # FR-2.2: single bulk query covering all three event_types, then
    # diff Python-side against phase_timing and skipped_phases.
    event_types = ["started", "completed", "skipped"]
    existing_rows = db.query_phase_events_bulk(type_ids, event_types=event_types)
    existing: set[tuple[str, str, str]] = {
        (r["type_id"], r["phase"], r["event_type"]) for r in existing_rows
    }

    for entity in entities:
        meta = parse_metadata(entity.get("metadata"))
        type_id = entity["type_id"]
        phase_timing = meta.get("phase_timing") or {}
        for phase_name, timing in phase_timing.items():
            if not isinstance(timing, dict):
                continue
            # FR-2.1 (#00146) — started check.
            started_ts = timing.get("started")
            if started_ts and (type_id, phase_name, "started") not in existing:
                drift.append({
                    "kind": "phase_events_missing_started",
                    "type_id": type_id,
                    "phase": phase_name,
                    "metadata_completed_at": started_ts,
                })
            # Existing completed check.
            completed_ts = timing.get("completed")
            if completed_ts and (type_id, phase_name, "completed") not in existing:
                drift.append({
                    "kind": "phase_events_missing_completed",
                    "type_id": type_id,
                    "phase": phase_name,
                    "metadata_completed_at": completed_ts,
                })
        # FR-2.1 (#00146) — skipped check. ``skipped_phases`` is a list of
        # phase names with no associated timestamp in metadata.
        skipped_phases = meta.get("skipped_phases") or []
        if isinstance(skipped_phases, list):
            for phase_name in skipped_phases:
                if not isinstance(phase_name, str):
                    continue
                if (type_id, phase_name, "skipped") not in existing:
                    drift.append({
                        "kind": "phase_events_missing_skipped",
                        "type_id": type_id,
                        "phase": phase_name,
                        "metadata_completed_at": "",
                    })
    return drift


@_with_error_handling
@_catch_value_error
def _process_reconcile_check(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None,
) -> str:
    """Workflow drift detection. Returns JSON string.

    Note: Single-feature db_only is unreachable via MCP — _validate_feature_type_id
    requires the directory to exist (spec I7), so a feature with a DB row but no
    filesystem directory returns feature_not_found. db_only is only observable
    through the bulk scan path (feature_type_id=None).
    """
    if feature_type_id is not None:
        _validate_feature_type_id(feature_type_id, artifacts_root)
    result = check_workflow_drift(engine, db, artifacts_root, feature_type_id)
    # Feature 088 FR-10.9 / AC-42: additive sibling key surfacing drift between
    # entities.metadata.phase_timing and phase_events rows. Does not affect the
    # existing WorkflowDriftResult (frozen dataclass) schema.
    phase_events_drift = _detect_phase_events_drift(db, feature_type_id)
    return json.dumps({
        "features": [_serialize_workflow_drift_report(r) for r in result.features],
        "summary": result.summary,
        "phase_events_drift": phase_events_drift,
    })


@_with_error_handling
@_with_retry()
@_catch_value_error
def _process_reconcile_apply(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None,
    dry_run: bool,
    *,
    workspace_uuid: str | None = None,
) -> str:
    """Workflow reconciliation. Hardcodes meta_json_to_db direction, returns JSON string.

    Feature 113 FR-11: forwards ``workspace_uuid`` to
    ``apply_workflow_reconciliation`` so the FR-4.1 read-side assertion runs.
    """
    if feature_type_id is not None:
        _validate_feature_type_id(feature_type_id, artifacts_root)
    result = apply_workflow_reconciliation(
        engine, db, artifacts_root, feature_type_id, dry_run,
        workspace_uuid=workspace_uuid,
    )
    # Feature 088 FR-10.9 / AC-42b: detect phase_events-vs-metadata drift and
    # emit stderr warnings. We do NOT auto-insert phase_events rows — drift of
    # this kind requires manual inspection (a live row backfill would falsify
    # the created_at audit trail).
    phase_events_drift = _detect_phase_events_drift(db, feature_type_id)
    for entry in phase_events_drift:
        sys.stderr.write(
            f"[reconcile] phase_events drift for {entry['type_id']}:{entry['phase']} "
            f"(metadata completed={entry['metadata_completed_at']}, phase_events missing) — "
            f"NOT auto-fixing (manual inspection recommended)\n"
        )
    return json.dumps({
        "actions": [_serialize_reconcile_action(a) for a in result.actions],
        "summary": result.summary,
        "phase_events_drift_count": len(phase_events_drift),
    })


@_with_error_handling
@_with_retry()
@_catch_value_error
def _process_reconcile_frontmatter(
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None,
    *,
    workspace_uuid: str | None = None,
) -> str:
    """Frontmatter drift detection. Returns JSON string.

    Feature 113 FR-11: forwards ``workspace_uuid`` to ``scan_all`` so the
    bulk scan is workspace-scoped.
    """
    if feature_type_id is None:
        reports: list[DriftReport] = scan_all(
            db, artifacts_root, workspace_uuid=workspace_uuid,
        )
    else:
        slug = _validate_feature_type_id(feature_type_id, artifacts_root)
        feat_dir = os.path.join(artifacts_root, "features", slug)
        reports = []
        if os.path.isdir(feat_dir):
            for basename in ARTIFACT_BASENAME_MAP:
                filepath = os.path.join(feat_dir, basename)
                if os.path.isfile(filepath):
                    report = detect_drift(db, filepath, type_id=feature_type_id)
                    reports.append(report)

    drifted = [r for r in reports if r.status != "in_sync"]
    return json.dumps({
        "total_scanned": len(reports),
        "drifted_count": len(drifted),
        "reports": [_serialize_drift_report(r) for r in drifted],
    })


@_with_error_handling
@_with_retry()
@_catch_value_error
def _process_init_feature_state(
    db: EntityDatabase,
    engine: WorkflowStateEngine | None,
    feature_dir: str,
    feature_id: str,
    slug: str,
    mode: str,
    branch: str,
    brainstorm_source: str | None,
    backlog_source: str | None,
    status: str,
    *,
    artifacts_root: str,
) -> str:
    """Thin wrapper — delegates to feature_lifecycle.init_feature_state."""
    result = _lib_init_feature_state(
        db=db,
        engine=engine,
        artifacts_root=artifacts_root,
        feature_dir=feature_dir,
        feature_id=feature_id,
        slug=slug,
        mode=mode,
        branch=branch,
        brainstorm_source=brainstorm_source,
        backlog_source=backlog_source,
        status=status,
        # FR-6.2: Empty-string == unset == None at db.* kwarg boundary;
        # downstream defaults to project_id="__unknown__" → _UNKNOWN_WORKSPACE_UUID.
        workspace_uuid=_workspace_uuid or None,
    )
    warning = _project_meta_json(db, engine, result["feature_type_id"], feature_dir)
    if warning:
        result["projection_warning"] = warning
    return json.dumps(result)


@_with_error_handling
@_with_retry()
@_catch_value_error
def _process_init_project_state(
    db: EntityDatabase,
    project_dir: str,
    project_id: str,
    slug: str,
    features: str,  # JSON string
    milestones: str,  # JSON string
    brainstorm_source: str | None,
) -> str:
    """Thin wrapper — delegates to feature_lifecycle.init_project_state."""
    result = _lib_init_project_state(
        db=db,
        artifacts_root=_artifacts_root,
        project_dir=project_dir,
        project_id=project_id,
        slug=slug,
        branch="",  # Not used in original project init path
        features=features,
        milestones=milestones,
        brainstorm_source=brainstorm_source,
        workspace_uuid=_workspace_uuid or None,
    )
    return json.dumps(result)


@_with_error_handling
@_with_retry()
@_catch_value_error
def _process_activate_feature(
    db: EntityDatabase,
    engine: WorkflowStateEngine,
    feature_type_id: str,
    artifacts_root: str,
) -> str:
    """Thin wrapper — delegates to feature_lifecycle.activate_feature."""
    result = _lib_activate_feature(
        db=db,
        engine=engine,
        artifacts_root=artifacts_root,
        feature_type_id=feature_type_id,
        workspace_uuid=_workspace_uuid or None,
    )
    warning = _project_meta_json(db, engine, result["feature_type_id"])
    if warning:
        result["projection_warning"] = warning
    return json.dumps(result)


@_with_error_handling
@_with_retry()
@_catch_entity_value_error
def _process_init_entity_workflow(
    db: EntityDatabase, type_id: str, workflow_phase: str, kanban_column: str
) -> str:
    """Thin wrapper — delegates to entity_lifecycle.init_entity_workflow."""
    return json.dumps(_lib_init_entity_workflow(
        db, type_id, workflow_phase, kanban_column,
        workspace_uuid=_workspace_uuid or None,
    ))


@_with_error_handling
@_with_retry()
@_catch_entity_value_error
def _process_transition_entity_phase(
    db: EntityDatabase, type_id: str, target_phase: str
) -> str:
    """Thin wrapper — delegates to entity_lifecycle.transition_entity_phase."""
    return json.dumps(_lib_transition_entity_phase(
        db, type_id, target_phase,
        workspace_uuid=_workspace_uuid or None,
    ))


@_with_error_handling
def _process_reconcile_status(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
    summary_only: bool = False,
    *,
    workspace_uuid: str | None = None,
) -> str:
    """Combined drift report. Returns JSON string.

    When summary_only=True, returns a compact 3-field response:
    {"healthy": bool, "workflow_drift_count": int, "frontmatter_drift_count": int}

    Feature 113 FR-11.3: forwards ``workspace_uuid`` to ``scan_all`` so the
    frontmatter scan is workspace-scoped.
    """
    # Workflow drift
    workflow_result = check_workflow_drift(engine, db, artifacts_root)

    # Frontmatter drift
    frontmatter_reports = scan_all(
        db, artifacts_root, workspace_uuid=workspace_uuid,
    )

    if summary_only:
        wf_drift = sum(
            1 for r in workflow_result.features if r.status != "in_sync"
        )
        fm_drift = sum(
            1 for r in frontmatter_reports if r.status != "in_sync"
        )
        return json.dumps({
            "healthy": wf_drift == 0,
            "workflow_drift_count": wf_drift,
            "frontmatter_drift_count": fm_drift,
        })

    fm_summary = _build_frontmatter_summary(frontmatter_reports)

    # Healthy: workflow drift only (frontmatter drift excluded per AC-2,
    # artifact_missing_count excluded — informational, not a health issue)
    _HEALTH_EXCLUDED = {"in_sync", "artifact_missing_count"}
    wf_healthy = all(
        v == 0 for k, v in workflow_result.summary.items() if k not in _HEALTH_EXCLUDED
    )
    healthy = wf_healthy

    return json.dumps({
        "workflow_drift": {
            "features": [
                _serialize_workflow_drift_report(r) for r in workflow_result.features
            ],
            "summary": workflow_result.summary,
        },
        "frontmatter_drift": {
            "reports": [_serialize_drift_report(r) for r in frontmatter_reports],
            "summary": fm_summary,
        },
        "healthy": healthy,
        "total_features_checked": len(workflow_result.features),
        "total_files_checked": len(frontmatter_reports),
    })


# ---------------------------------------------------------------------------
# Ref resolution helper (Task 1b.5)
# ---------------------------------------------------------------------------


def _resolve_ref_to_feature_type_id(
    db: EntityDatabase,
    feature_type_id: str | None,
    ref: str | None,
) -> str:
    """Resolve a feature_type_id or ref to a concrete feature_type_id.

    Parameters
    ----------
    db:
        Open EntityDatabase.
    feature_type_id:
        Explicit feature_type_id (takes precedence if provided).
    ref:
        Flexible reference: UUID, full type_id, or type_id prefix.

    Returns
    -------
    str
        The resolved feature_type_id.

    Raises
    ------
    ValueError
        If neither param provided, ref not found, or ambiguous.
    """
    if feature_type_id is not None:
        return feature_type_id
    if ref is None:
        raise ValueError("Either feature_type_id or ref must be provided")

    entity_uuid = db.resolve_ref(ref)
    entity = db.get_entity_by_uuid(entity_uuid)
    if entity is None:
        raise ValueError(f"No entity found matching ref: {ref!r}")
    return entity["type_id"]


# ---------------------------------------------------------------------------
# MCP tool handlers
# ---------------------------------------------------------------------------

_NOT_INITIALIZED = _make_error(
    "not_initialized",
    "Engine not initialized (server not started)",
    "Wait for server startup or restart the MCP server",
)

mcp = FastMCP("workflow-engine", lifespan=lifespan)


@mcp.tool()
async def get_phase(feature_type_id: str | None = None, ref: str | None = None) -> str:
    """Read the current workflow state for a feature."""
    err = _check_db_available()
    if err:
        return err
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    try:
        resolved = _resolve_ref_to_feature_type_id(_db, feature_type_id, ref)
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid feature_type_id or ref")
    return _process_get_phase(_engine, resolved)


@mcp.tool()
async def transition_phase(
    feature_type_id: str | None = None,
    target_phase: str = "",
    yolo_active: bool = False,
    skipped_phases: str | None = None,
    ref: str | None = None,
) -> str:
    """Validate and enter a target phase."""
    err = _check_db_available()
    if err:
        return err
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    try:
        resolved = _resolve_ref_to_feature_type_id(_db, feature_type_id, ref)
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid feature_type_id or ref")
    return _process_transition_phase(
        _engine, resolved, target_phase, yolo_active,
        db=_db, skipped_phases=skipped_phases,
        entity_engine=_entity_engine,
    )


@mcp.tool()
async def complete_phase(
    feature_type_id: str | None = None,
    phase: str = "",
    iterations: int | None = None,
    reviewer_notes: str | None = None,
    ref: str | None = None,
) -> str:
    """Record a phase as completed and advance to next phase."""
    err = _check_db_available()
    if err:
        return err
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    try:
        resolved = _resolve_ref_to_feature_type_id(_db, feature_type_id, ref)
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid feature_type_id or ref")
    return _process_complete_phase(
        _engine, resolved, phase,
        db=_db, iterations=iterations, reviewer_notes=reviewer_notes,
        entity_engine=_entity_engine,
    )


@mcp.tool()
async def validate_prerequisites(
    feature_type_id: str | None = None,
    target_phase: str = "",
    ref: str | None = None,
) -> str:
    """Dry-run gate evaluation without executing the transition."""
    err = _check_db_available()
    if err:
        return err
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    try:
        resolved = _resolve_ref_to_feature_type_id(_db, feature_type_id, ref)
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid feature_type_id or ref")
    return _process_validate_prerequisites(_engine, resolved, target_phase)


def _resolve_list_handler_workspace_filter(
    project_id: str | None,
) -> str | None:
    """Decide the workspace_uuid scope filter for a list_features_* handler.

    Feature 112 / FR-2 / NFR-5 #4: default behavior is single-workspace
    (returns ``_workspace_uuid`` if populated, else the canonical unknown UUID
    resolved from the legacy ``_project_id``). ``project_id == "*"`` opts into
    cross-workspace by returning ``None``. A specific legacy ``project_id``
    value preserves backward compat by JOIN-resolving through
    ``_resolve_optional_workspace_filter``.

    Returns
    -------
    str | None
        Workspace UUID to filter by, or ``None`` for cross-workspace.
    """
    # FR-3.0: empty string → None at entry (treated as default-workspace).
    # Without normalization, "" falls into the JOIN-resolve branch below,
    # fails to match any workspaces.project_id_legacy row, and silently
    # degrades to cross-workspace via ValueError → None. Forms one
    # defensive contract with FR-6's workspace_uuid empty-string handling.
    if project_id == "":
        project_id = None
    if project_id == "*":
        return None
    if project_id is not None:
        # Caller-supplied legacy project_id → JOIN-resolve to workspace_uuid.
        if _db is None:
            # Degraded-mode: no DB → cross-workspace fallback is intentional,
            # surfaced via _check_db_available upstream
            return None
        # FR-3.2: silent None → ValueError. Invalid legacy hex must surface
        # as an MCP error envelope at the caller wrappers, not silently
        # degrade to cross-workspace. Caller wrappers in list_features_by_phase
        # and list_features_by_status catch this and return _make_error JSON
        # with error_type="invalid_project_id".
        return _db._resolve_optional_workspace_filter(
            workspace_uuid=None, project_id=project_id,
            _caller="list_features_handler",
        )
    # Default: filter by current workspace.
    return _workspace_uuid or None


def _filter_states_by_workspace(
    results_json: str, target_ws_uuid: str | None,
) -> str:
    """Post-filter a list_features_* result JSON by workspace_uuid.

    ``target_ws_uuid is None`` means cross-workspace (no filter).
    """
    if target_ws_uuid is None or _db is None:
        return results_json
    try:
        states = json.loads(results_json)
        filtered = []
        for s in states:
            entity = _db.get_entity(s.get("feature_type_id", ""))
            if entity and entity.get("workspace_uuid") == target_ws_uuid:
                filtered.append(s)
        return json.dumps(filtered)
    except json.JSONDecodeError:
        return results_json  # malformed JSON from engine — return as-is
    except sqlite3.OperationalError as exc:
        return _make_error(
            "db_unavailable", str(exc),
            "Database temporarily unavailable; retry shortly",
        )
    # FR-7: other exceptions PROPAGATE (no except Exception clause).


@mcp.tool()
async def list_features_by_phase(phase: str, project_id: str | None = None) -> str:
    """All features currently in a given workflow phase.

    Parameters
    ----------
    phase:
        Workflow phase name to filter by.
    project_id:
        Project scope. **Default: single-workspace** (current
        ``_workspace_uuid``). Pass ``'*'`` to opt into cross-workspace
        results. A legacy 12-char project_id resolves via
        ``workspaces.project_id_legacy``.
    """
    err = _check_db_available()
    if err:
        return err
    if _engine is None:
        return _NOT_INITIALIZED
    try:
        ws_filter = _resolve_list_handler_workspace_filter(project_id)
    except ValueError as exc:
        # FR-3.2: invalid legacy project_id → surfaced as MCP error envelope.
        return _make_error(
            "invalid_project_id", str(exc),
            "Pass project_id='*' for cross-workspace OR omit for "
            "current-workspace default",
        )
    results = _process_list_features_by_phase(_engine, phase)
    return _filter_states_by_workspace(results, ws_filter)


@mcp.tool()
async def list_features_by_status(status: str, project_id: str | None = None) -> str:
    """All features with a given entity status.

    Parameters
    ----------
    status:
        Entity status to filter by.
    project_id:
        Project scope. **Default: single-workspace** (current
        ``_workspace_uuid``). Pass ``'*'`` to opt into cross-workspace
        results. A legacy 12-char project_id resolves via
        ``workspaces.project_id_legacy``.
    """
    err = _check_db_available()
    if err:
        return err
    if _engine is None:
        return _NOT_INITIALIZED
    try:
        ws_filter = _resolve_list_handler_workspace_filter(project_id)
    except ValueError as exc:
        # FR-3.2: invalid legacy project_id → surfaced as MCP error envelope.
        return _make_error(
            "invalid_project_id", str(exc),
            "Pass project_id='*' for cross-workspace OR omit for "
            "current-workspace default",
        )
    results = _process_list_features_by_status(_engine, status)
    return _filter_states_by_workspace(results, ws_filter)


@mcp.tool()
async def reconcile_check(feature_type_id: str | None = None) -> str:
    """Compare .meta.json workflow state against DB for drift detection."""
    err = _check_db_available()
    if err:
        return err
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_check(_engine, _db, _artifacts_root, feature_type_id)


@mcp.tool()
async def reconcile_apply(
    feature_type_id: str | None = None,
    dry_run: bool = False,
) -> str:
    """Sync .meta.json workflow state to DB for features where .meta.json is ahead."""
    err = _check_db_available()
    if err:
        return err
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_apply(
        _engine, _db, _artifacts_root, feature_type_id, dry_run,
        # FR-11.3: thread workspace_uuid; empty string == unset → None.
        workspace_uuid=_workspace_uuid or None,
    )


@mcp.tool()
async def reconcile_frontmatter(feature_type_id: str | None = None) -> str:
    """Check frontmatter headers against DB entity records for drift."""
    err = _check_db_available()
    if err:
        return err
    if _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_frontmatter(
        _db, _artifacts_root, feature_type_id,
        # FR-11.4: thread workspace_uuid; empty string == unset → None.
        workspace_uuid=_workspace_uuid or None,
    )


@mcp.tool()
async def reconcile_status(summary_only: bool = False) -> str:
    """Unified health report across workflow state and frontmatter drift."""
    err = _check_db_available()
    if err:
        return err
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_status(
        _engine, _db, _artifacts_root, summary_only=summary_only,
        # FR-11.5: thread workspace_uuid; empty string == unset → None.
        workspace_uuid=_workspace_uuid or None,
    )


@mcp.tool()
async def init_feature_state(
    feature_dir: str,
    feature_id: str,
    slug: str,
    mode: str,
    branch: str,
    brainstorm_source: str | None = None,
    backlog_source: str | None = None,
    status: str = "active",
) -> str:
    """Create initial feature state in DB and write feature .meta.json."""
    err = _check_db_available()
    if err:
        return err
    if _db is None:
        return _NOT_INITIALIZED
    return _process_init_feature_state(
        _db, _engine, feature_dir, feature_id, slug, mode, branch,
        brainstorm_source, backlog_source, status,
        artifacts_root=_artifacts_root,
    )


@mcp.tool()
async def init_project_state(
    project_dir: str,
    project_id: str,
    slug: str,
    features: str,
    milestones: str,
    brainstorm_source: str | None = None,
) -> str:
    """Create initial project state in DB and write project .meta.json."""
    err = _check_db_available()
    if err:
        return err
    if _db is None:
        return _NOT_INITIALIZED
    return _process_init_project_state(
        _db, project_dir, project_id, slug, features, milestones, brainstorm_source
    )


@mcp.tool()
async def activate_feature(feature_type_id: str | None = None, ref: str | None = None) -> str:
    """Transition a planned feature to active status."""
    err = _check_db_available()
    if err:
        return err
    if _db is None or _engine is None:
        return _NOT_INITIALIZED
    try:
        resolved = _resolve_ref_to_feature_type_id(_db, feature_type_id, ref)
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid feature_type_id or ref")
    return _process_activate_feature(_db, _engine, resolved, _artifacts_root)


@mcp.tool()
async def init_entity_workflow(
    type_id: str | None = None,
    workflow_phase: str = "",
    kanban_column: str = "",
    ref: str | None = None,
) -> str:
    """Create a workflow_phases row for any entity type."""
    err = _check_db_available()
    if err:
        return err
    if _db is None:
        return _NOT_INITIALIZED
    try:
        resolved = _resolve_ref_to_feature_type_id(_db, type_id, ref)
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid type_id or ref")
    return _process_init_entity_workflow(_db, resolved, workflow_phase, kanban_column)


@mcp.tool()
async def transition_entity_phase(
    type_id: str | None = None,
    target_phase: str = "",
    ref: str | None = None,
) -> str:
    """Transition a brainstorm or backlog entity to a new lifecycle phase."""
    err = _check_db_available()
    if err:
        return err
    if _db is None:
        return _NOT_INITIALIZED
    try:
        resolved = _resolve_ref_to_feature_type_id(_db, type_id, ref)
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid type_id or ref")
    return _process_transition_entity_phase(_db, resolved, target_phase)


@mcp.tool()
async def get_notifications(project_root: str | None = None) -> str:
    """Drain pending notifications for the current project.

    Returns notifications queued by entity state changes (phase completions,
    threshold crossings, etc.). Drained notifications are removed from the
    queue so each notification is delivered exactly once.
    """
    err = _check_db_available()
    if err:
        return err
    if _notification_queue is None:
        return _NOT_INITIALIZED
    root = project_root or _project_root
    if not root:
        return _make_error(
            "missing_project_root",
            "No project_root provided and PROJECT_ROOT not set",
            "Pass project_root or set PROJECT_ROOT env var",
        )
    notifications = _notification_queue.drain(project_root=root)
    return json.dumps({
        "project_root": root,
        "count": len(notifications),
        "notifications": [
            {
                "message": n.message,
                "entity_type_id": n.entity_type_id,
                "event": n.event,
                "timestamp": n.timestamp,
            }
            for n in notifications
        ],
    })


@mcp.tool()
async def promote_task(feature_ref: str, task_heading: str) -> str:
    """Promote a task from tasks.md to a tracked task entity.

    Fuzzy-matches task_heading against headings in tasks.md, creates a task
    entity with parent=feature, status=planned, and links dependencies.
    """
    err = _check_db_available()
    if err:
        return err
    if _db is None:
        return _NOT_INITIALIZED
    try:
        result = _lib_promote_task(
            _db, feature_ref, task_heading,
            workspace_uuid=_workspace_uuid or None,
        )
        return json.dumps(result)
    except (TaskNotFoundError, TaskAlreadyPromotedError) as exc:
        return _make_error(type(exc).__name__, str(exc), "Check heading text or use exact heading from tasks.md")
    except (ValueError, FileNotFoundError) as exc:
        return _make_error("invalid_input", str(exc), "Provide valid feature_ref and ensure tasks.md exists")


@mcp.tool()
async def query_ready_tasks() -> str:
    """List task entities ready for execution.

    Returns tasks that are: type=task, status=planned, no blocked_by
    dependencies, and parent entity in implement phase.
    """
    err = _check_db_available()
    if err:
        return err
    if _db is None:
        return _NOT_INITIALIZED
    try:
        tasks = _lib_query_ready_tasks(_db)
        return json.dumps({"count": len(tasks), "tasks": tasks})
    except Exception as exc:
        return _make_error("internal", str(exc), "Report this error")


@mcp.tool()
async def get_progress_view(entity_ref: str) -> str:
    """Get cross-level progress view for an entity's ancestor chain.

    Walks up the parent chain and returns pre-computed progress and
    traffic_light for each ancestor (no recursive recomputation).
    """
    err = _check_db_available()
    if err:
        return err
    if _db is None:
        return _NOT_INITIALIZED
    try:
        entity_uuid = _db.resolve_ref(entity_ref)
        ancestors = _lib_get_ancestor_progress(_db, entity_uuid)
        return json.dumps({"ancestors": ancestors, "count": len(ancestors)})
    except ValueError as exc:
        return _make_error("invalid_ref", str(exc), "Provide a valid entity ref")
    except Exception as exc:
        return _make_error("internal", str(exc), "Report this error")


# ---------------------------------------------------------------------------
# Feature 084: Phase event analytics
# ---------------------------------------------------------------------------


@mcp.tool()
async def record_backward_event(
    type_id: str,
    source_phase: str,
    target_phase: str,
    reason: str = "",
) -> str:
    """Record a backward phase transition event for analytics.

    Called by workflow-transitions skill AFTER transition_phase completes
    a backward transition. `project_id` is resolved server-side from the
    entity record (feature 088 FR-2.3) — callers MUST NOT pass it.

    FR-2.3 validation: rejects unknown `type_id`; caps `reason` and
    `target_phase` at 500 chars. FR-2.5: sqlite failures return the
    standard `_make_error` shape (never raw `str(e)`).
    """
    err = _check_db_available()
    if err:
        return err
    if _db is None:
        return _NOT_INITIALIZED

    # FR-2.3 (a): reject unknown type_id.
    entity = _db.get_entity(type_id)
    if not entity:
        return _make_error(
            "entity_not_found",
            f"Entity {type_id} not found",
            "Verify type_id matches an existing entity",
        )

    # FR-2.3 (b): resolve project_id server-side from entity record.
    # Feature 089 FR-2.3 (#00151): distinguish missing vs empty project_id.
    resolved_project_id = _resolve_project_id(entity)

    # FR-2.3 (c) + FR-2.6 harmonized: cap reason and target at 500 chars.
    reason_capped = (reason or "")[:500]
    target_capped = (target_phase or "")[:500]

    ts = _iso_now()
    try:
        # Feature 109 Group 9.6: pass workspace_uuid (optional for workflow
        # event types per design §3.1).
        _db.append_phase_event(
            type_id=type_id,
            project_id=resolved_project_id,
            phase=source_phase,
            event_type="backward",
            timestamp=ts,
            backward_reason=reason_capped,
            backward_target=target_capped,
            workspace_uuid=_workspace_uuid or None,
        )
    except sqlite3.Error as e:
        print(
            f"[workflow-state] backward event INSERT failed: "
            f"{type(e).__name__}: {str(e)[:200]}",
            file=sys.stderr,
        )
        return _make_error(
            "insert_failed",
            f"{type(e).__name__}: {str(e)[:200]}",
            "Check type_id validity",
        )

    return json.dumps({
        "recorded": True,
        "type_id": type_id,
        "source_phase": source_phase,
        "target_phase": target_capped,
    })


@mcp.tool()
async def query_phase_analytics(
    query_type: str,
    feature_type_id: str | None = None,
    project_id: str | None = None,
    phase: str | None = None,
    limit: int = 50,
) -> str:
    """Query structured phase execution data for analytics.

    query_type: 'phase_duration' | 'iteration_summary' | 'backward_frequency' | 'raw_events'

    Cross-project isolation (feature 088, FR-2.1): by default, results are
    scoped to the current project (`_project_id`). Pass `project_id="*"` to
    opt into a cross-project query; pass a literal `project_id` string to
    scope to a specific project other than the current one.
    """
    err = _check_db_available()
    if err:
        return err
    if _db is None:
        return _NOT_INITIALIZED

    # Feature 089 FR-1.5 / AC-5 (#00143): allowlist ``project_id`` to avoid
    # cross-project data disclosure via arbitrary scope strings. Accepted:
    #   - ``None`` → defaults to current project below
    #   - ``'*'``   → explicit cross-project opt-in
    #   - ``_project_id`` → explicit current project
    # Anything else is refused.
    if project_id is not None and project_id != "*" and project_id != _project_id:
        return _make_error(
            "forbidden",
            f'cross-project query requires project_id="*" or current '
            f'project ({_project_id!r}); got {project_id!r}',
            'Pass project_id=None for current, "*" for all projects',
        )

    # FR-2.1: default to current project; "*" means opt into cross-project.
    resolved_project_id = None if project_id == "*" else (project_id or _project_id)

    if query_type == "phase_duration":
        # Feature 088 FR-4.1/FR-4.2: fetch both event types, merge into a
        # single list, and let _compute_durations emit rows for unpaired
        # (type_id, phase) groups via zip_longest + key-union.
        started = _db.query_phase_events(
            type_id=feature_type_id, project_id=resolved_project_id,
            phase=phase, event_type="started",
            limit=_ANALYTICS_EVENT_SCAN_LIMIT,
        )
        completed = _db.query_phase_events(
            type_id=feature_type_id, project_id=resolved_project_id,
            phase=phase, event_type="completed",
            limit=_ANALYTICS_EVENT_SCAN_LIMIT,
        )
        events = list(started) + list(completed)
        results = _compute_durations(events)
        return json.dumps({
            "query_type": "phase_duration",
            "results": results[:limit],
            "total": len(results),
        })

    elif query_type == "iteration_summary":
        # Feature 088 FR-7.1: fetch with the internal scan limit, filter
        # `iterations is not None` in Python, sort, THEN apply caller's limit.
        # Prior ordering (fetch with caller's limit, filter after) could return
        # fewer rows than expected when None rows occupied the top slots.
        events = _db.query_phase_events(
            type_id=feature_type_id, project_id=resolved_project_id,
            phase=phase, event_type="completed",
            limit=_ANALYTICS_EVENT_SCAN_LIMIT,
        )
        results = [
            {
                "type_id": e["type_id"],
                "phase": e["phase"],
                "iterations": e["iterations"],
                "timestamp": e["timestamp"],
            }
            for e in events if e.get("iterations") is not None
        ]
        results.sort(key=lambda x: x["iterations"] or 0, reverse=True)
        results = results[:limit]
        return json.dumps({
            "query_type": "iteration_summary",
            "results": results,
            "total": len(results),
        })

    elif query_type == "backward_frequency":
        events = _db.query_phase_events(
            type_id=feature_type_id, project_id=resolved_project_id,
            event_type="backward", limit=_ANALYTICS_EVENT_SCAN_LIMIT,
        )
        freq: dict[str, int] = {}
        for e in events:
            freq[e["phase"]] = freq.get(e["phase"], 0) + 1
        results = sorted(
            [{"phase": p, "backward_count": c} for p, c in freq.items()],
            key=lambda x: x["backward_count"], reverse=True,
        )
        return json.dumps({
            "query_type": "backward_frequency",
            "results": results,
            "total": len(results),
        })

    elif query_type == "raw_events":
        events = _db.query_phase_events(
            type_id=feature_type_id, project_id=resolved_project_id,
            phase=phase, limit=limit,
        )
        return json.dumps({
            "query_type": "raw_events",
            "results": events,
            "total": len(events),
        })

    return json.dumps({"error": f"Unknown query_type: {query_type}"})


def _compute_durations(events: list[dict]) -> list[dict]:
    """Pair `started` / `completed` phase_events for each (type_id, phase).

    Feature 088 FR-4.1/FR-4.2/FR-6.3:
    - Accepts a SINGLE merged events list (caller concatenates two filtered
      query_phase_events calls). Signature change from the old
      ``(started, completed)`` form is intentional — this function now owns
      grouping by event_type, so the caller can't silently drop one side.
    - Iterates the UNION of ``groups_s.keys() | groups_c.keys()`` so
      (type_id, phase) pairs with a started-but-no-completed, or the reverse,
      still produce a result row (never silently dropped).
    - Uses ``itertools.zip_longest(fillvalue=None)`` within each group so
      imbalanced pairs (e.g., 3 started + 2 completed after a mid-transition
      crash) yield N rows, with unpaired entries flagged via
      ``missing_started`` / ``missing_completed`` and ``duration_seconds=None``.
    - Imports (``defaultdict``, ``datetime``, ``zip_longest``) live at
      module scope per FR-6.3 so importing this module has a fixed cost
      regardless of whether the function runs.

    Rows are sorted descending by ``duration_seconds``; rows with None duration
    sort last (they convey "pairing anomaly" diagnostic, not a measurement).
    """
    groups_s: dict[tuple, list] = defaultdict(list)
    groups_c: dict[tuple, list] = defaultdict(list)
    for e in events:
        key = (e["type_id"], e["phase"])
        if e.get("event_type") == "started":
            groups_s[key].append(e)
        elif e.get("event_type") == "completed":
            groups_c[key].append(e)
        # Other event_types (backward, skipped, ...) are ignored here —
        # duration is only meaningful for started/completed pairs.

    results: list[dict] = []
    for key in groups_s.keys() | groups_c.keys():
        s_list = sorted(groups_s.get(key, []), key=lambda x: x["timestamp"])
        c_list = sorted(groups_c.get(key, []), key=lambda x: x["timestamp"])
        for s, c in zip_longest(s_list, c_list, fillvalue=None):
            row: dict = {
                "type_id": key[0],
                "phase": key[1],
                "started_at": s["timestamp"] if s else None,
                "completed_at": c["timestamp"] if c else None,
                "duration_seconds": None,
                "missing_started": s is None,
                "missing_completed": c is None,
            }
            if s is not None and c is not None:
                try:
                    s_ts = s["timestamp"].replace("Z", "+00:00") if s["timestamp"] else ""
                    c_ts = c["timestamp"].replace("Z", "+00:00") if c["timestamp"] else ""
                    s_dt = datetime.fromisoformat(s_ts)
                    c_dt = datetime.fromisoformat(c_ts)
                    row["duration_seconds"] = (c_dt - s_dt).total_seconds()
                except (ValueError, TypeError):
                    # Mixed-tz / unparseable timestamps leave duration as None
                    # rather than dropping the row (pairing diagnostic still
                    # useful for operators).
                    pass
            results.append(row)

    # None sorts last: coerce to -inf so legitimate durations stay on top.
    results.sort(
        key=lambda x: (x["duration_seconds"] is None, -(x["duration_seconds"] or 0)),
    )
    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
