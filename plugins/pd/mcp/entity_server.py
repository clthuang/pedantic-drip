"""MCP entity server for unified lineage tracking of pd entities.

Runs as a subprocess via stdio transport.  Never print to stdout
(corrupts JSON-RPC protocol) -- all logging goes to stderr.
"""
from __future__ import annotations

import functools
import json
import logging
import os
import sqlite3
import sys
import threading
import time
from contextlib import asynccontextmanager

# Make entity_registry and semantic_memory importable from hooks/lib/.
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _hooks_lib)

from entity_registry.backfill import run_backfill
from entity_registry.database import (
    CrossWorkspaceError,
    EntityDatabase,
    EntityExistsError,
    EntityNotFoundError,
    PromotionConflictError,
)
from entity_registry.id_generator import generate_entity_id
from entity_registry.project_identity import (
    GitProjectInfo,
    _compute_legacy_project_id,
    collect_git_info,
    resolve_workspace_uuid,
)
from entity_registry.server_helpers import (
    _process_export_entities,
    _process_export_lineage_markdown,
    _process_get_lineage,
    _process_register_entity,
    _process_set_parent,
    parse_metadata,
)
from semantic_memory.config import read_config
from sqlite_retry import with_retry

from mcp.server.fastmcp import FastMCP
from server_lifecycle import write_pid, remove_pid, start_parent_watchdog

# ---------------------------------------------------------------------------
# Module-level globals (set during lifespan)
# ---------------------------------------------------------------------------

_db: EntityDatabase | None = None
_db_unavailable: bool = False
_recovery_thread: threading.Thread | None = None
_config: dict = {}
_project_root: str = ""
_artifacts_root: str = ""
_project_id: str = ""
_git_info: GitProjectInfo | None = None
# Phase D Task 4.8: lazy workspace_uuid global. Populated during lifespan
# from resolve_workspace_uuid(_project_root). Phase E will swap callers
# (e.g., _upsert_project) over to using this. Empty string until set.
_workspace_uuid: str = ""

_logger = logging.getLogger("entity_server")


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

    On success: sets global _db, clears _db_unavailable.
    Thread exits after successful recovery.
    """
    global _db, _db_unavailable

    def _recover():
        global _db, _db_unavailable
        while True:
            time.sleep(poll_interval)
            try:
                new_db = EntityDatabase(db_path)
                _db = new_db
                _db_unavailable = False
                _logger.info(
                    "DB recovered — backfill skipped, will run on next restart"
                )
                return
            except sqlite3.OperationalError:
                continue

    thread = threading.Thread(target=_recover, name="db-recovery", daemon=True)
    thread.start()
    return thread


def _check_db_available():
    """Return error dict if DB is unavailable, else None."""
    if _db_unavailable:
        return {"error": "database temporarily unavailable"}
    return None


# ---------------------------------------------------------------------------
# Project identity helpers
# ---------------------------------------------------------------------------


def _upsert_project(db: EntityDatabase, info: GitProjectInfo) -> None:
    """Insert or update a project row via db.upsert_project().

    Feature 108 design §6.10: forward the lazy workspace_uuid global so the
    eventual ``projects.workspace_uuid`` write path has the value
    pre-resolved. ``_workspace_uuid`` is set by lifespan() before this
    helper is called.
    """
    db.upsert_project(
        project_id=info.project_id,
        name=info.name,
        root_commit_sha=info.root_commit_sha,
        remote_url=info.remote_url,
        normalized_url=info.normalized_url,
        remote_host=info.remote_host,
        remote_owner=info.remote_owner,
        remote_repo=info.remote_repo,
        default_branch=info.default_branch,
        project_root=info.project_root,
        is_git_repo=info.is_git_repo,
        workspace_uuid=_workspace_uuid or None,
    )


def _effective_project_id(explicit: str | None = None) -> str | None:
    """Resolve the effective project_id for DB queries.

    Returns None (meaning 'all projects') when no project context is
    available. This happens in tests where _project_id is not set.
    """
    pid = explicit or _project_id
    return pid if pid else None


def _backfill_project_ids(
    db: EntityDatabase,
    project_root: str,
    project_id: str,
    workspace_uuid: str | None = None,
) -> int:
    """Claim __unknown__ entities whose artifact_path is under project_root.

    Delegates to EntityDatabase.backfill_project_ids() which handles the
    trigger-drop + UPDATE + trigger-recreate pattern internally. When
    *workspace_uuid* is supplied (the lifespan-resolved identity) it is the
    authoritative claim target, so entities are never cross-attributed into a
    stale legacy-keyed workspace row.

    Returns count of claimed entities.
    """
    count = db.backfill_project_ids(
        project_root, project_id, workspace_uuid=workspace_uuid
    )
    if count > 0:
        _logger.info("backfill: claimed %d entities for project %s", count, project_id)
    return count


# ---------------------------------------------------------------------------
# Lifespan handler
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(server):
    """Manage DB connection and backfill lifecycle."""
    global _db, _db_unavailable, _recovery_thread, _config, _project_root, _artifacts_root, _project_id, _git_info, _workspace_uuid

    # Determine DB path (env override for testing, else global store).
    db_path = os.environ.get(
        "ENTITY_DB_PATH",
        os.path.expanduser("~/.claude/pd/entities/entities.db"),
    )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    write_pid("entity_server")
    start_parent_watchdog()

    _db = _init_db_with_retry(db_path)
    if _db is None:
        _db_unavailable = True
        _recovery_thread = _start_recovery_thread(db_path)
        print(
            "entity-server: started in DEGRADED mode (DB locked)",
            file=sys.stderr,
        )
    else:
        # Read config from the project root.
        project_root = os.environ.get("PROJECT_ROOT", os.getcwd())
        _project_root = project_root
        config = read_config(project_root)
        _config = config
        _artifacts_root = os.path.join(project_root, str(config.get("artifacts_root", "docs")))

        # Detect project identity and register in DB.
        _project_id = _compute_legacy_project_id(_project_root)
        # Phase E Task 5.5: populate the workspace_uuid lazy global with
        # FR-3 / Decision 11 precedence:
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
                f"entity-server: workspace_uuid resolution failed: {exc}",
                file=sys.stderr,
            )
            _workspace_uuid = ""
        try:
            _git_info = collect_git_info(_project_root)
            _upsert_project(_db, _git_info)
        except Exception as exc:
            print(f"entity-server: project upsert failed: {exc}", file=sys.stderr)

        # Claim __unknown__ entities matching this project root. Pass the
        # resolved workspace identity so entities are claimed into it directly
        # (never cross-attributed into a stale legacy-keyed row).
        try:
            claimed = _backfill_project_ids(
                _db, _project_root, _project_id,
                workspace_uuid=_workspace_uuid or None,
            )
            if claimed > 0:
                print(
                    f"entity-server: claimed {claimed} entities for project {_project_id}",
                    file=sys.stderr,
                )
        except Exception as exc:
            print(f"entity-server: project backfill failed: {exc}", file=sys.stderr)

        # Backfill existing artifacts (idempotency guard inside run_backfill).
        try:
            run_backfill(_db, _artifacts_root, project_id=_project_id)
        except Exception as exc:
            print(f"entity-server: backfill failed: {exc}", file=sys.stderr)

        # Always run workflow_phases backfill (has its own INSERT OR IGNORE idempotency).
        # Called OUTSIDE the backfill_complete guard so newly registered entities
        # get workflow_phases rows on every startup.
        try:
            from entity_registry.backfill import backfill_workflow_phases

            result = backfill_workflow_phases(_db, _artifacts_root, project_id=_project_id)
            if result["created"] > 0:
                print(
                    f"entity-server: workflow_phases backfill created {result['created']} rows",
                    file=sys.stderr,
                )
        except Exception as exc:
            print(f"entity-server: workflow_phases backfill failed: {exc}", file=sys.stderr)

        print(
            f"entity-server: started (db={db_path}, artifacts={_artifacts_root})",
            file=sys.stderr,
        )

    try:
        yield {}
    finally:
        remove_pid("entity_server")
        if _db is not None:
            _db.close()
            _db = None
        _config = {}


# ---------------------------------------------------------------------------
# Ref resolution helper (Task 1b.5)
# ---------------------------------------------------------------------------


def _resolve_ref_param(
    db: EntityDatabase,
    type_id: str | None,
    ref: str | None,
    *,
    is_mutation: bool = False,
    project_id: str | None = None,
) -> str:
    """Resolve a type_id or ref parameter to a concrete type_id.

    Parameters
    ----------
    db:
        Open EntityDatabase.
    type_id:
        Explicit type_id (takes precedence if provided).
    ref:
        Flexible reference: UUID, full type_id, or type_id prefix.
    is_mutation:
        If True, ambiguous prefix matches always error (never guess).
    project_id:
        Optional project scope for resolution. Passed through to
        db.resolve_ref().

    Returns
    -------
    str
        The resolved type_id.

    Raises
    ------
    ValueError
        If neither param provided, ref not found, or ambiguous.
    """
    if type_id is not None:
        return type_id
    if ref is None:
        raise ValueError("Either type_id or ref must be provided")

    # resolve_ref returns a UUID — look up the entity to get type_id
    entity_uuid = db.resolve_ref(ref, project_id=project_id)
    entity = db.get_entity_by_uuid(entity_uuid)
    if entity is None:
        raise ValueError(f"No entity found matching ref: {ref!r}")
    return entity["type_id"]


# ---------------------------------------------------------------------------
# Sync DB-logic helpers (Type B handlers — extracted for @with_retry)
# ---------------------------------------------------------------------------


@with_retry("entity")
def _process_update_entity(
    db: EntityDatabase,
    resolved_type_id: str,
    name: str | None,
    description: str | None,
    status: str | None,
    metadata: dict | None,
    project_id: str | None = None,
    new_project_id: str | None = None,
) -> str:
    """Update mutable fields of an existing entity (retryable)."""
    db.update_entity(
        resolved_type_id, name=name, status=status,
        artifact_path=description, metadata=metadata,
        project_id=project_id, new_project_id=new_project_id,
    )
    return f"Updated: {resolved_type_id}"


@with_retry("entity")
def _process_delete_entity(
    db: EntityDatabase, resolved_type_id: str, project_id: str | None = None,
) -> str:
    """Delete an entity and all associated data (retryable)."""
    db.delete_entity(resolved_type_id, project_id=project_id)
    return json.dumps({"result": f"Deleted: {resolved_type_id}"})


@with_retry("entity")
def _process_add_entity_tag(db: EntityDatabase, resolved_type_id: str, tag: str) -> str:
    """Add a tag to an entity (retryable)."""
    entity = db.get_entity(resolved_type_id)
    if entity is None:
        return f"Error: entity not found: {resolved_type_id}"
    db.add_tag(entity["uuid"], tag)
    return json.dumps({"result": f"Tagged {resolved_type_id} with '{tag}'"})


@with_retry("entity")
def _process_add_dependency(
    db: EntityDatabase,
    dep_mgr,
    blocker_uuid: str,
    blocked_uuid: str,
    entity_ref: str,
    blocked_by_ref: str,
) -> str:
    """Add a dependency between two entities (retryable)."""
    dep_mgr.add_dependency(db, blocker_uuid, blocked_uuid)
    return json.dumps({
        "result": f"Dependency added: {entity_ref} blocked by {blocked_by_ref}"
    })


@with_retry("entity")
def _process_remove_dependency(
    db: EntityDatabase,
    dep_mgr,
    entity_uuid: str,
    blocked_by_uuid: str,
    entity_ref: str,
    blocked_by_ref: str,
) -> str:
    """Remove a dependency between two entities (retryable)."""
    dep_mgr.remove_dependency(db, entity_uuid, blocked_by_uuid)
    return json.dumps({
        "result": f"Dependency removed: {entity_ref} no longer blocked by {blocked_by_ref}"
    })


@with_retry("entity")
def _process_add_okr_alignment(
    db: EntityDatabase, entity_uuid: str, kr_uuid: str,
    entity_ref: str, kr_ref: str,
) -> str:
    """Link an entity to a key result (retryable)."""
    db.add_okr_alignment(entity_uuid, kr_uuid)
    return json.dumps({"result": f"Aligned {entity_ref} to {kr_ref}"})


@with_retry("entity")
def _process_create_key_result(
    db: EntityDatabase,
    parent_type_id: str,
    eid: str,
    name: str,
    status: str | None,
    metadata_json: str,
    weight: float,
    project_id: str = "__unknown__",
) -> str:
    """Register a key_result entity with parent linkage (retryable).

    Feature 112 / FR-4: parent_type_id is resolved to parent_uuid at this
    call site; ``db.register_entity`` is invoked with the canonical
    parent_uuid kwarg.
    """
    parent_entity = db.get_entity(parent_type_id)
    if parent_entity is None:
        # FR-9: explicit missing-parent surfacing (was: silent orphan).
        # Caught by the MCP create_key_result wrapper's except Exception
        # at entity_server.py:1136-1137 → returns JSON error to caller.
        raise ValueError(f"Parent entity not found: {parent_type_id!r}")
    parent_uuid = parent_entity["uuid"]
    # F12 audit: conflict-is-error → register_entity, EntityExistsError translated to MCP JSON
    try:
        uuid = db.register_entity(
            entity_type="key_result",
            entity_id=eid,
            name=name,
            status=status,
            parent_uuid=parent_uuid,
            metadata=metadata_json,
            project_id=project_id,
        )
    except EntityExistsError as e:
        return json.dumps({
            "error": True,
            "error_type": "entity_exists",
            "message": str(e),
            "workspace_uuid": e.workspace_uuid,
            "type_id": e.type_id,
            "recovery_hint": (
                "Use upsert_entity for idempotent registration, or check "
                "workspace context."
            ),
        })
    return json.dumps({"uuid": uuid, "type_id": f"key_result:{eid}", "weight": weight})


@with_retry("entity")
def _process_update_kr_score(
    db: EntityDatabase, resolved_type_id: str, score: float,
) -> str:
    """Update score for a key_result entity (retryable)."""
    db.update_entity(resolved_type_id, metadata={"score": float(score)})
    return json.dumps({"result": f"Score updated to {score}", "type_id": resolved_type_id})


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("entity-registry", lifespan=lifespan)


@mcp.tool()
async def register_entity(
    entity_type: str,
    entity_id: str | None = None,
    name: str = "",
    artifact_path: str | None = None,
    status: str | None = None,
    parent_uuid: str | None = None,
    metadata: str | dict | None = None,
    workspace_uuid: str | None = None,
    project_id: str | None = None,
    auto_id: bool = False,
) -> str:
    """Register a new entity in the lineage registry.

    Parameters
    ----------
    entity_type:
        One of: backlog, brainstorm, project, feature.
    entity_id:
        Unique identifier within the entity_type namespace
        (e.g. '029-entity-lineage-tracking'). Required unless auto_id=True.
    name:
        Human-readable name (e.g. 'Entity Lineage Tracking').
    artifact_path:
        Optional filesystem path to the entity's artifact.
    status:
        Optional status string.
    parent_uuid:
        Optional UUID of the parent entity. Replaces the legacy
        ``parent_type_id`` parameter dropped by feature 108 / FR-13.
    metadata:
        Optional metadata — pass a dict (preferred) or a JSON string;
        dicts are auto-coerced to JSON.
    workspace_uuid:
        Workspace identity (feature 108). When ``None``, the MCP server
        resolves it via the lazy ``_workspace_uuid`` global populated at
        server startup from ``.claude/pd/workspace.json``.
    project_id:
        Legacy project scope (pre-Migration-11). Retained for the duration
        of the Migration 11 transition: when ``UNIQUE(workspace_uuid,
        type_id)`` semantics are fully wired through database.py the kwarg
        is dropped.
    auto_id:
        If True, auto-generate entity_id from name. Cannot be used
        together with an explicit entity_id.

    Returns confirmation message or error.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    # Feature 108 FR-13: resolve workspace_uuid via lazy global if caller
    # did not supply it. Default to the empty string when no workspace
    # context is set (legacy fixture path).
    # NOTE: Feature 114 FR-D.2 originally proposed defaulting to
    # _UNKNOWN_WORKSPACE_UUID here, but that broke test fixtures that pass
    # project_id="__unknown__" without seeding the workspaces table.
    # _resolve_workspace_uuid_kwargs downstream maps "__unknown__" project_id
    # to _UNKNOWN_WORKSPACE_UUID correctly when workspace_uuid is "".
    resolved_workspace_uuid = workspace_uuid or _workspace_uuid or ""
    resolved_project_id = project_id or _project_id or "__unknown__"

    if auto_id and entity_id:
        return "Error: cannot specify both auto_id=True and entity_id"
    if auto_id:
        if not name:
            return "Error: name is required when auto_id=True"
        entity_id = generate_entity_id(_db, entity_type, name, resolved_project_id)
    elif not entity_id:
        return "Error: entity_id is required (or use auto_id=True)"

    if isinstance(metadata, dict):
        metadata = json.dumps(metadata)

    # database.py register_entity still keys on project_id; the
    # workspace_uuid surface is captured in metadata until the DB-layer
    # signature flip lands (out of scope for this dispatch).
    # F12 audit: conflict-is-error → register_entity, EntityExistsError translated to MCP JSON
    # (translation happens inside _process_register_entity which returns the
    # legacy "Already existed: ..." concise format on EntityExistsError per
    # server_helpers.py — see design §3.5 for the structured JSON shape used
    # by other MCP tool sites.)
    return _process_register_entity(
        _db, entity_type, entity_id, name,
        artifact_path, status, None,  # parent_type_id removed (FR-13 AC).
        parse_metadata(metadata),
        project_id=resolved_project_id,
        parent_uuid=parent_uuid,
        workspace_uuid=resolved_workspace_uuid,
    )


# ---------------------------------------------------------------------------
# Feature 111 F9 — issue_spawn MCP tool
# ---------------------------------------------------------------------------


_ISSUE_SPAWN_VALID_KINDS = ("bug", "task")
_ISSUE_SPAWN_VALID_PARENT_KINDS = ("feature", "backlog", "project")


def _catch_issue_spawn_errors(func):
    """Translate ValueError-family exceptions raised by ``issue_spawn`` into
    structured JSON error envelopes at the MCP boundary.

    Per spec FR-EX.3 / design IF-9: ``issue_spawn`` raises ``ValueError`` (and
    the ``EntityNotFoundError`` ValueError subclass) for ``invalid_kind``,
    ``parent_not_found``, ``invalid_parent_kind``, and ``cross-workspace
    parent forbidden``. The envelope shape matches the F10 ``complete_phase``
    pattern at ``workflow_state_server.py:_catch_close_errors`` so MCP
    consumers see a uniform contract:

      ``{"error": true, "error_type": "<class_name_lowercased>",
         "message": "<exception_str>"}``

    The wrapper is async-aware — ``issue_spawn`` is an async MCP tool.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValueError as exc:
            return json.dumps({
                "error": True,
                "error_type": exc.__class__.__name__.lower(),
                "message": str(exc),
            })
    return wrapper


@mcp.tool()
@_catch_issue_spawn_errors
async def issue_spawn(
    parent_uuid: str,
    kind: str,
    summary: str,
    workspace_uuid: str | None = None,
    project_id: str | None = None,
    metadata: str | dict | None = None,
) -> str:
    """Spawn a new issue entity (kind='bug' or 'task') linked to a parent.

    Per FR-9.1 to FR-9.9 of feature 111. Parent (feature/backlog/project) is
    NOT state-mutated — only a ``spawned_child`` phase_event is appended on
    the parent. The new entity's lifecycle is status-only (FR-BL) — no
    ``workflow_phases`` row is created.

    Parameters
    ----------
    parent_uuid:
        UUID of the parent entity. Parent's resolved ``kind`` must be in
        ``{feature, backlog, project}``.
    kind:
        Issue kind — ``'bug'`` or ``'task'``.
    summary:
        Human-readable summary; becomes ``entities.name`` AND seeds the
        slug portion of the auto-generated ``entity_id``.
    workspace_uuid:
        Workspace identity. Resolves via the lazy ``_workspace_uuid`` global
        when not supplied.
    project_id:
        Legacy project scope alias (deprecated). Falls back to the
        ``_project_id`` global, then ``"__unknown__"``.
    metadata:
        Optional dict (or JSON string) merged into ``entities.metadata``.
        System-supplied keys win — caller-supplied ``parent_uuid`` (and
        similar reserved keys owned by ``register_entity``) are dropped
        before persistence per FR-9.9.

    Returns
    -------
    str
        JSON string ``'{"uuid": "<new_entity_uuid>"}'`` on success. On
        failure, returns a JSON error envelope
        ``{"error": true, "error_type": "<exc_cls_lower>",
           "message": "<exc_str>"}`` produced by the
        ``_catch_issue_spawn_errors`` decorator (FR-EX.3).

    Raises
    ------
    ValueError
        On ``invalid_kind`` (FR-9.5), ``parent_not_found`` (FR-9.6),
        ``invalid_parent_kind`` (FR-9.6), or ``cross-workspace parent
        forbidden`` (FR-9.6 design IF-1 step 5b). All four conditions are
        caught at the MCP boundary by ``_catch_issue_spawn_errors`` and
        translated to a JSON error envelope (FR-EX.3).
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    # FR-9.5: validate kind BEFORE any DB work (no partial state on bad kind).
    if kind not in _ISSUE_SPAWN_VALID_KINDS:
        raise ValueError(
            f"invalid_kind: {kind!r}; expected bug|task"
        )

    # Two-layer fallback per design IF-1 step 3-4 (mirrors register_entity MCP
    # at entity_server.py:560-561). See FR-D.2 note above re: empty-string vs
    # _UNKNOWN_WORKSPACE_UUID default.
    resolved_workspace_uuid = workspace_uuid or _workspace_uuid or ""
    resolved_project_id = project_id or _project_id or "__unknown__"

    # FR-9.6: resolve parent. Existing helper reused per design C11 /
    # plan-reviewer iter 2 B2 (database.py:5839 — get_entity_by_uuid).
    parent_row = _db.get_entity_by_uuid(parent_uuid)
    if parent_row is None:
        # EntityNotFoundError is a ValueError subclass per IF-9, so the
        # caller's `except ValueError` (and AC-9.5's pytest.raises(ValueError))
        # still matches. The substring "parent_not_found" is pinned by AC-9.5.
        raise EntityNotFoundError(f"parent_not_found: {parent_uuid}")
    parent_kind = parent_row.get("kind")
    if parent_kind not in _ISSUE_SPAWN_VALID_PARENT_KINDS:
        raise ValueError(
            f"invalid_parent_kind: {parent_kind!r}; "
            f"expected feature|backlog|project"
        )

    # FR-9.6 cross-workspace gate (design IF-1 step 5b, security-reviewer iter
    # 2 BLOCKER 1): parent_uuid MUST resolve to a row in the SAME workspace as
    # the caller. Resolve the caller's effective workspace_uuid via the same
    # path register_entity uses (database.py:5635 _resolve_workspace_uuid_kwargs)
    # so the comparison is canonical (e.g., project_id='__unknown__' resolves
    # to _UNKNOWN_WORKSPACE_UUID). Run this BEFORE any state-mutating call so
    # no partial state can be created.
    resolved_caller_ws = _db._resolve_workspace_uuid_kwargs(
        resolved_workspace_uuid or None,
        resolved_project_id if not resolved_workspace_uuid else None,
        _caller="issue_spawn",
    )
    parent_ws = parent_row.get("workspace_uuid")
    if parent_ws != resolved_caller_ws:
        raise ValueError(
            f"cross-workspace parent forbidden: "
            f"parent in {parent_ws!r}, caller in {resolved_caller_ws!r}"
        )

    # Normalize caller metadata to a dict; drop reserved keys that live in
    # entity columns. FR-9.9: system-supplied keys win — caller's
    # parent_uuid (and other column-owned keys) are removed before merge.
    if isinstance(metadata, str):
        caller_meta: dict = json.loads(metadata) if metadata else {}
    elif isinstance(metadata, dict):
        # Shallow copy so we don't mutate the caller's dict.
        caller_meta = dict(metadata)
    else:
        caller_meta = {}
    # parent_uuid lives in the entities.parent_uuid column, NOT in metadata
    # (per AC-9.9 synthetic test). Strip the key defensively so caller-supplied
    # values cannot leak into entities.metadata.
    caller_meta.pop("parent_uuid", None)

    # FR-9.2: auto_id path via generate_entity_id produces conformant
    # `{seq:03d}-{slug}` ids, so EntityIdFormatError cannot fire (AC-9.6).
    entity_id = generate_entity_id(
        _db, kind, summary, resolved_project_id
    )

    # FR-9.2: direct db.register_entity call (mirrors entity_server.py:502+
    # pattern). The internal _derive_type_and_lifecycle mapping (Group B)
    # converts entity_type=kind → (type='work', kind=<bug|task>,
    # lifecycle_class=<kind>_flow). NO init_entity_workflow call —
    # bug/task use the status-only model per FR-BL.
    ws_uuid_kwarg = resolved_workspace_uuid or None
    # F12 audit: conflict-is-error → register_entity, EntityExistsError
    # bubbles to MCP boundary translator. auto_id guarantees fresh entity_id
    # so conflict is operationally impossible; raise-on-conflict semantics
    # preferred over INSERT OR IGNORE per feature 109 FR-4.
    new_uuid = _db.register_entity(
        entity_type=kind,
        entity_id=entity_id,
        name=summary,
        workspace_uuid=ws_uuid_kwarg,
        project_id=resolved_project_id if ws_uuid_kwarg is None else None,
        status="open",
        parent_uuid=parent_uuid,
        metadata=caller_meta,
    )

    # FR-9.3: append spawned_child phase_event on the parent. workspace_uuid
    # is passed defensively (informational for spawned_child today; the
    # required-kwarg gate at database.py:6964-6970 enforces it only for
    # entity_status_changed / entity_promoted, so passing here is harmless
    # and future-proofs against the check being widened). Source the
    # workspace_uuid from the parent row (the canonical context for the
    # event we're appending on the parent's type_id).
    _db.append_phase_event(
        type_id=parent_row["type_id"],
        project_id=resolved_project_id,
        workspace_uuid=parent_row.get("workspace_uuid") or resolved_workspace_uuid or None,
        event_type="spawned_child",
        phase=None,
        metadata={
            "child_uuid": new_uuid,
            "child_kind": kind,
            "child_name": summary,
        },
    )

    return json.dumps({"uuid": new_uuid})


@mcp.tool()
async def set_parent(
    type_id: str | None = None,
    parent_type_id: str | None = None,
    ref: str | None = None,
    parent_ref: str | None = None,
) -> str:
    """Set or change the parent of an entity.

    Parameters
    ----------
    type_id:
        The entity to update (e.g. 'feature:029-entity-lineage-tracking').
    parent_type_id:
        The new parent entity (e.g. 'project:my-project').
    ref:
        Alternative flexible reference for the child entity.
    parent_ref:
        Alternative flexible reference for the parent entity.

    Returns confirmation message or error.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    try:
        resolved_type_id = _resolve_ref_param(_db, type_id, ref, is_mutation=True, project_id=_effective_project_id())
        resolved_parent = _resolve_ref_param(
            _db, parent_type_id, parent_ref, is_mutation=True
        )
    except ValueError as exc:
        return f"Error: {exc}"

    return _process_set_parent(_db, resolved_type_id, resolved_parent)


@mcp.tool()
async def get_entity(type_id: str | None = None, ref: str | None = None) -> str:
    """Retrieve a single entity by type_id or ref.

    Parameters
    ----------
    type_id:
        Entity identifier (e.g. 'feature:029-entity-lineage-tracking').
    ref:
        Alternative flexible reference: UUID, full type_id, or type_id prefix.
        Resolved via db.resolve_ref(). Provide type_id OR ref (not both required).

    Returns JSON representation of the entity or not-found message.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    try:
        resolved_type_id = _resolve_ref_param(_db, type_id, ref, project_id=_effective_project_id())
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    entity = _db.get_entity(resolved_type_id)
    if entity is None:
        return f"Entity not found: {resolved_type_id}"
    for key in ("uuid", "entity_id", "parent_uuid"):
        entity.pop(key, None)
    return json.dumps(entity, separators=(",", ":"))


@mcp.tool()
async def get_lineage(
    type_id: str | None = None,
    direction: str = "up",
    max_depth: int = 10,
    ref: str | None = None,
) -> str:
    """Traverse the entity hierarchy and display as a tree.

    Parameters
    ----------
    type_id:
        Starting entity (e.g. 'feature:029-entity-lineage-tracking').
    direction:
        'up' walks toward root (ancestry), 'down' walks toward leaves
        (descendants). Default: 'up'.
    max_depth:
        Maximum levels to traverse (default: 10, AC-14 depth guard).
    ref:
        Alternative flexible reference for the starting entity.

    Returns formatted tree string or error message.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    try:
        resolved_type_id = _resolve_ref_param(_db, type_id, ref, project_id=_effective_project_id())
    except ValueError as exc:
        return f"Error: {exc}"

    return _process_get_lineage(_db, resolved_type_id, direction, max_depth)


@mcp.tool()
async def update_entity(
    type_id: str | None = None,
    name: str | None = None,
    status: str | None = None,
    artifact_path: str | None = None,
    metadata: str | dict | None = None,
    ref: str | None = None,
    project_id: str | None = None,
    new_project_id: str | None = None,
) -> str:
    """Update mutable fields of an existing entity.

    Parameters
    ----------
    type_id:
        Entity to update (e.g. 'feature:029-entity-lineage-tracking').
    name:
        New name (if provided).
    status:
        New status (if provided).
    artifact_path:
        New artifact_path (if provided).
    metadata:
        Metadata to shallow-merge — pass a dict (preferred) or a JSON
        string; dicts are auto-coerced. Empty dict '{}' clears.
    ref:
        Alternative flexible reference. Mutations require exact or unique match.
    project_id:
        Project scope for entity resolution. Defaults to current project.
    new_project_id:
        If provided, re-attribute the entity to a different project.

    Returns confirmation message or error.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    resolved_project_id = _effective_project_id(project_id)

    try:
        resolved_type_id = _resolve_ref_param(
            _db, type_id, ref, is_mutation=True, project_id=resolved_project_id,
        )
    except ValueError as exc:
        return f"Error: {exc}"

    if isinstance(metadata, dict):
        metadata = json.dumps(metadata)

    try:
        return _process_update_entity(
            _db, resolved_type_id, name=name, description=artifact_path,
            status=status, metadata=parse_metadata(metadata),
            project_id=resolved_project_id,
            new_project_id=new_project_id,
        )
    except Exception as exc:
        return f"Error updating entity: {exc}"


@mcp.tool()
async def export_lineage_markdown(
    type_id: str | None = None,
    output_path: str | None = None,
    project_id: str | None = None,
) -> str:
    """Export entity lineage as a markdown tree.

    Parameters
    ----------
    type_id:
        If provided, export only the tree rooted at this entity.
        If omitted, export all trees.
    output_path:
        If provided, write markdown to this file path (relative paths
        resolved against artifacts_root). Returns confirmation.
        If omitted, returns the markdown string directly.
    project_id:
        Project scope. Defaults to current project. Pass '*' for all projects.

    Returns markdown string or file-write confirmation.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    resolved_project_id = None if project_id == "*" else _effective_project_id(project_id)

    return _process_export_lineage_markdown(
        _db, type_id, output_path, _artifacts_root,
        project_id=resolved_project_id,
    )


@mcp.tool()
async def export_entities(
    entity_type: str | None = None,
    status: str | None = None,
    output_path: str | None = None,
    include_lineage: bool = True,
    fields: str | None = None,
    project_id: str | None = None,
) -> str:
    """Export all entities (or a filtered subset) as structured JSON.

    Parameters
    ----------
    entity_type:
        Filter by type (backlog, brainstorm, project, feature).
    status:
        Filter by status string.
    output_path:
        Write to file; if None, return as string.
    include_lineage:
        Include parent/child relationships (default True).
    fields:
        Comma-separated field names to include per entity (e.g.
        'type_id,name,status'). If omitted, all fields returned.
    project_id:
        Project scope. Defaults to current project. Pass '*' for all projects.

    Returns JSON string or file-write confirmation.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    resolved_project_id = None if project_id == "*" else _effective_project_id(project_id)

    return _process_export_entities(
        _db, entity_type, status, output_path, include_lineage, _artifacts_root,
        fields=fields,
        project_id=resolved_project_id,
    )


@mcp.tool()
async def delete_entity(type_id: str | None = None, ref: str | None = None) -> str:
    """Delete an entity and all associated data (FTS, workflow_phases).

    Parameters
    ----------
    type_id:
        Entity to delete (e.g. 'feature:001-test').
    ref:
        Alternative flexible reference. Mutations require exact or unique match.

    Returns confirmation JSON or error JSON.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        resolved_type_id = _resolve_ref_param(_db, type_id, ref, is_mutation=True, project_id=_effective_project_id())
        return _process_delete_entity(_db, resolved_type_id, project_id=_effective_project_id())
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def add_entity_tag(
    type_id: str | None = None, tag: str = "", ref: str | None = None
) -> str:
    """Add a tag to an entity.

    Parameters
    ----------
    type_id:
        Entity identifier (type_id).
    tag:
        Tag string (lowercase, hyphens, max 50 chars).
    ref:
        Alternative flexible reference for the entity.

    Returns confirmation or error.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        resolved_type_id = _resolve_ref_param(_db, type_id, ref, is_mutation=True, project_id=_effective_project_id())
        return _process_add_entity_tag(_db, resolved_type_id, tag)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        return json.dumps({"error": f"Unexpected error: {exc}"})


@mcp.tool()
async def get_entity_tags(type_id: str | None = None, ref: str | None = None) -> str:
    """Get all tags for an entity.

    Parameters
    ----------
    type_id:
        Entity identifier (type_id).
    ref:
        Alternative flexible reference for the entity.

    Returns JSON list of tags or error.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        resolved_type_id = _resolve_ref_param(_db, type_id, ref, project_id=_effective_project_id())
        entity = _db.get_entity(resolved_type_id)
        if entity is None:
            return f"Error: entity not found: {resolved_type_id}"
        tags = _db.get_tags(entity["uuid"])
        return json.dumps({"type_id": resolved_type_id, "tags": tags})
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        return json.dumps({"error": f"Unexpected error: {exc}"})


@mcp.tool()
async def add_dependency(
    entity_ref: str,
    blocked_by_ref: str,
) -> str:
    """Add a dependency: entity is blocked by another entity.

    Parameters
    ----------
    entity_ref:
        The entity that is blocked (type_id, UUID, or prefix).
    blocked_by_ref:
        The entity that blocks it (type_id, UUID, or prefix).

    Returns confirmation JSON or error JSON.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        from entity_registry.dependencies import CycleError, DependencyManager

        entity_uuid = _db.resolve_ref(entity_ref, project_id=_effective_project_id())
        blocked_by_uuid = _db.resolve_ref(blocked_by_ref, project_id=_effective_project_id())
        mgr = DependencyManager()
        return _process_add_dependency(
            _db, mgr, entity_uuid, blocked_by_uuid, entity_ref, blocked_by_ref,
        )
    except CycleError as exc:
        return json.dumps({"error": f"Cycle detected: {exc}"})
    except CrossWorkspaceError as exc:
        # Feature 115 FR-E.3: structured envelope for cross-workspace rejection.
        return json.dumps({
            "error": True,
            "error_type": "cross_workspace_forbidden",
            "message": str(exc),
            "recovery_hint": (
                "Re-attribute one endpoint or grandfather via "
                "cross_workspace_allowlist"
            ),
            "op_name": exc.op_name,
            "pairs": exc.pairs,
        })
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        return json.dumps({"error": f"Unexpected error: {exc}"})


@mcp.tool()
async def remove_dependency(
    entity_ref: str,
    blocked_by_ref: str,
) -> str:
    """Remove a dependency between two entities.

    Parameters
    ----------
    entity_ref:
        The entity that was blocked (type_id, UUID, or prefix).
    blocked_by_ref:
        The entity that was blocking it (type_id, UUID, or prefix).

    Returns confirmation JSON or error JSON.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        from entity_registry.dependencies import DependencyManager

        entity_uuid = _db.resolve_ref(entity_ref, project_id=_effective_project_id())
        blocked_by_uuid = _db.resolve_ref(blocked_by_ref, project_id=_effective_project_id())
        mgr = DependencyManager()
        return _process_remove_dependency(
            _db, mgr, entity_uuid, blocked_by_uuid, entity_ref, blocked_by_ref,
        )
    except ValueError as exc:
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        return json.dumps({"error": f"Unexpected error: {exc}"})


@mcp.tool()
async def search_entities(
    query: str,
    entity_type: str | None = None,
    limit: int = 20,
    project_id: str | None = None,
) -> str:
    """Full-text search across all entities.

    Parameters
    ----------
    query:
        Search string (prefix-matched, sanitized).
    entity_type:
        Optional filter by entity_type.
    limit:
        Max results (default 20, max 100).
    project_id:
        Project scope. Defaults to current project. Pass '*' for all projects.

    Returns formatted search results or error message.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    resolved_project_id = None if project_id == "*" else _effective_project_id(project_id)

    try:
        results = _db.search_entities(
            query, entity_type=entity_type, limit=limit,
            project_id=resolved_project_id,
        )
    except ValueError as exc:
        return f"Search error: {exc}"

    if not results:
        return f'No entities found matching "{query}".'

    n = len(results)
    lines = [f'Found {n} entities matching "{query}":\n']
    for i, r in enumerate(results, 1):
        # Intentional UX deviation from spec: use "no status" fallback instead
        # of empty parens when status is None/empty. Spec shows bare "()" but
        # "no status" is clearer for human readers.
        status = r.get("status") or "no status"
        lines.append(f'{i}. {r["type_id"]} — "{r["name"]}" ({status})')
    lines.append(f"\n{n} results shown (limit: {limit}).")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# OKR alignment tools (Task 6.5, AC-37 — lateral cross-linkage)
# ---------------------------------------------------------------------------


@mcp.tool()
async def add_okr_alignment(entity_ref: str, kr_ref: str) -> str:
    """Link an entity to a key result for lateral OKR alignment.

    Parameters
    ----------
    entity_ref:
        The entity to align (type_id, UUID, or prefix).
    kr_ref:
        The key_result to align with (type_id, UUID, or prefix).
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        entity_uuid = _db.resolve_ref(entity_ref, project_id=_effective_project_id())
        kr_uuid = _db.resolve_ref(kr_ref, project_id=_effective_project_id())
        return _process_add_okr_alignment(_db, entity_uuid, kr_uuid, entity_ref, kr_ref)
    except CrossWorkspaceError as exc:
        # Feature 115 FR-E.3: structured envelope for cross-workspace rejection.
        return json.dumps({
            "error": True,
            "error_type": "cross_workspace_forbidden",
            "message": str(exc),
            "recovery_hint": (
                "Re-attribute one endpoint or grandfather via "
                "cross_workspace_allowlist"
            ),
            "op_name": exc.op_name,
            "pairs": exc.pairs,
        })
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def get_okr_alignments(entity_ref: str) -> str:
    """Get all key results aligned to an entity.

    Parameters
    ----------
    entity_ref:
        The entity to query (type_id, UUID, or prefix).
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        entity_uuid = _db.resolve_ref(entity_ref, project_id=_effective_project_id())
        alignments = _db.get_okr_alignments(entity_uuid)
        results = [{"type_id": a["type_id"], "name": a["name"], "status": a.get("status")} for a in alignments]
        return json.dumps({"entity_ref": entity_ref, "alignments": results, "count": len(results)})
    except ValueError as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# OKR helpers — thin wrappers over rollup.py (Step 5.2, AC-32)
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_key_result(
    parent_ref: str,
    name: str,
    metric_type: str,
    weight: float = 1.0,
    entity_id: str | None = None,
    status: str | None = None,
) -> str:
    """Register a key_result entity with parent linkage, metric_type, and weight.

    Parameters
    ----------
    parent_ref:
        Reference (type_id, UUID, or prefix) to the parent objective.
    name:
        Human-readable KR name.
    metric_type:
        One of: milestone, binary, baseline_target.
    weight:
        Relative weight for weighted scoring (default 1.0).
    entity_id:
        Optional explicit ID; auto-generated if omitted.
    status:
        Optional initial status.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    _VALID_METRIC_TYPES = ("milestone", "binary", "baseline_target", "target", "baseline")
    if metric_type not in _VALID_METRIC_TYPES:
        return json.dumps({"error": f"Invalid metric_type: {metric_type}. Must be one of: {', '.join(_VALID_METRIC_TYPES)}"})
    try:
        parent_type_id = _resolve_ref_param(
            _db, None, parent_ref, is_mutation=True,
            project_id=_effective_project_id(),
        )
        eid = entity_id or name.lower().replace(" ", "-")[:30]
        metadata_json = json.dumps({"metric_type": metric_type, "weight": weight})
        return _process_create_key_result(
            _db, parent_type_id, eid, name, status, metadata_json, weight,
            project_id=_project_id or "__unknown__",
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def update_kr_score(
    kr_ref: str,
    score: float,
) -> str:
    """Manually update score for a baseline_target (or binary-no-children) KR.

    Parameters
    ----------
    kr_ref:
        Reference to the key_result entity.
    score:
        New score value (0.0-1.0).
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    if not (0.0 <= score <= 1.0):
        return json.dumps({"error": f"Score must be between 0.0 and 1.0, got {score}"})
    try:
        resolved = _resolve_ref_param(
            _db, None, kr_ref, is_mutation=True,
            project_id=_effective_project_id(),
        )
        return _process_update_kr_score(_db, resolved, score)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Project listing tool
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_projects() -> str:
    """List all known projects in the entity registry.

    Returns JSON array of project records ordered by created_at.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    projects = _db.list_projects()
    return json.dumps(projects)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
