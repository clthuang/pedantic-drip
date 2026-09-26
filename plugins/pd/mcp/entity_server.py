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
import time
from contextlib import asynccontextmanager

# Make entity_registry and pd_config importable from hooks/lib/.
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _hooks_lib)

from entity_registry.backfill import run_backfill
from entity_registry.database import (
    _UUID_RE,
    EntityDatabase,
    EntityExistsError,
    EntityNotFoundError,
    IncompleteBucketError,
)
from entity_registry.id_generator import (
    _slugify,
    generate_entity_id,
    render_display_id,
)
from entity_registry.project_identity import (
    GitProjectInfo,
    _compute_legacy_project_id,
    _git_cannot_answer_for_git_file,
    _repository_root,
    collect_git_info,
    resolve_startup_workspace_uuid,
)
from entity_registry.server_helpers import (
    _process_export_entities,
    _process_export_lineage_markdown,
    _process_get_lineage,
    _process_register_entity,
    _process_set_parent,
    parse_metadata,
)
from pd_config.config import read_config
from sqlite_retry import with_retry

from mcp.server.fastmcp import FastMCP
from server_lifecycle import write_pid, remove_pid, start_parent_watchdog

# ---------------------------------------------------------------------------
# Module-level globals (set during lifespan)
# ---------------------------------------------------------------------------

_db: EntityDatabase | None = None
_db_unavailable: bool = False
_config: dict = {}
_project_root: str = ""
_artifacts_root: str = ""
_project_id: str = ""
_git_info: GitProjectInfo | None = None
# The workspace this server writes in. The lifespan resolves it from
# _project_root; when that fails (a first session in a repository with no
# .claude/), _require_workspace() resolves it on demand and caches it here
# (W4.1). Empty string until resolved.
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


def _check_db_available():
    """Return error dict if DB is unavailable, else None.

    A server that could not open the registry at startup stays degraded
    until it is restarted (W4.2): nothing retries the open in the background.
    """
    if _db_unavailable:
        return {"error": "database unavailable (degraded start); restart the MCP server"}
    return None


# ---------------------------------------------------------------------------
# Workspace resolution on demand (W4.1)
# ---------------------------------------------------------------------------

# Which server to restart, and how a repository pd has never been started in
# gets a workspace.
_WORKSPACE_UNRESOLVED_HINT = (
    "restart the pd entity-registry MCP server from the repository root, "
    "or create .claude/ there"
)


class WorkspaceUnresolvedError(Exception):
    """No workspace resolves for this server. ``envelope`` is the
    ``workspace_unresolved`` error a write tool answers with."""

    def __init__(self) -> None:
        self.envelope = json.dumps({
            "error": True,
            "error_type": "workspace_unresolved",
            "message": "workspace identity not resolved — write refused",
            "recovery_hint": _WORKSPACE_UNRESOLVED_HINT,
        })
        super().__init__(self.envelope)


def _require_workspace() -> str:
    """The workspace this server writes in, resolved on demand (W4.1).

    The first of these that answers:

    1. ``_workspace_uuid``, set by the lifespan or by an earlier call;
    2. ``resolve_startup_workspace_uuid(_project_root)``: the startup's own
       resolution, retried once per call. Skipped when ``_project_root`` is
       empty, where it would key on the process's working directory;
    3. the workspaces row whose ``project_id_legacy`` is ``_project_id``
       (``_resolve_optional_workspace_filter``; its ``ValueError`` means
       there is no such row). The legacy id comes from the root commit, so
       it is the same from a subdirectory, a linked worktree or a second
       clone. Skipped when ``_project_id`` is empty or ``"__unknown__"``,
       which that method maps to the unknown workspace. In an orphaned
       worktree (a ``.git`` file git cannot answer for) the legacy id is a
       hash of the path, and the lifespan mints no row for it.

    A success is cached in ``_workspace_uuid``. A failure is not, so the
    next call tries again. A successful step 2 may write
    ``.claude/pd/workspace.json``, the normal file of a pd project.

    Raises ``WorkspaceUnresolvedError`` when none answers.
    """
    global _workspace_uuid
    if _workspace_uuid:
        return _workspace_uuid
    resolved = ""
    retry_error: Exception | None = None
    if _project_root:
        try:
            resolved = resolve_startup_workspace_uuid(_project_root)
        except Exception as exc:  # best-effort, as at startup
            retry_error = exc
    if not resolved and _db is not None and _project_id not in ("", "__unknown__"):
        try:
            resolved = _db._resolve_optional_workspace_filter(
                None, _project_id, _caller="_require_workspace"
            ) or ""
        except ValueError:
            resolved = ""
    if not resolved:
        print(
            f"entity-server: workspace unresolved (project_root={_project_root!r}, "
            f"project_id={_project_id!r}; retry: {retry_error})",
            file=sys.stderr,
        )
        raise WorkspaceUnresolvedError()
    _workspace_uuid = resolved
    return resolved


# ---------------------------------------------------------------------------
# Project identity helpers
# ---------------------------------------------------------------------------


def _upsert_project(db: EntityDatabase, info: GitProjectInfo) -> None:
    """Insert or update a project row via db.upsert_project().

    Feature 108 design §6.10: forward the lazy workspace_uuid global so the
    eventual ``projects.workspace_uuid`` write path has the value
    pre-resolved. ``_workspace_uuid`` is set by lifespan() before this
    helper is called.

    The row is keyed at the repository's main checkout
    (``_repository_root``), as path-keyed workspace resolution is. A
    workspace this mints in a first session started from a linked worktree
    is then the one ``resolve_workspace_uuid`` finds from the worktree and
    from the main checkout, rather than one keyed at the worktree's path,
    which a later ``.claude/`` in the main checkout would leave behind for
    a second workspace.
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
        project_root=_repository_root(info.project_root),
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
    global _db, _db_unavailable, _config, _project_root, _artifacts_root, _project_id, _git_info, _workspace_uuid

    # Determine DB path (env override for testing, else global store).
    db_path = os.environ.get(
        "ENTITY_DB_PATH",
        os.path.expanduser("~/.claude/pd/entities/entities.db"),
    )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    _db = _init_db_with_retry(db_path)
    if _db is None:
        # Degraded until restarted (W4.2): every tool answers the
        # _check_db_available error.
        _db_unavailable = True
        print(
            "entity-server: started in DEGRADED mode (DB locked); restart the MCP server",
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
        # Phase E Task 5.5: populate the workspace_uuid lazy global. Precedence
        # (see resolve_startup_workspace_uuid):
        #   ENTITY_WORKSPACE_UUID env (absolute test/explicit override)
        #     > WORKSPACE_UUID env (inherited candidate, reconciled vs DB)
        #     > resolve_workspace_uuid(_project_root) (file → DB → fresh)
        # The WORKSPACE_UUID candidate is validate-or-adopted so a stale
        # inherited value cannot re-open the split-brain it would otherwise
        # bypass. All resolution failures are best-effort; never block startup.
        try:
            _workspace_uuid = resolve_startup_workspace_uuid(_project_root)
        except Exception as exc:
            print(
                f"entity-server: workspace_uuid resolution failed: {exc}",
                file=sys.stderr,
            )
            _workspace_uuid = ""
        # The next three steps register the project and backfill its
        # entities. With no workspace resolved, upsert_project finds the
        # workspaces row by the legacy id or the root, or else mints one,
        # keyed at the repository's main checkout. That mint is how a first
        # session in a repository with no .claude/ gets the workspace
        # _require_workspace() then finds (W4.1).
        #
        # All three are skipped when the root's .git is a FILE git cannot
        # answer for (an orphaned worktree, or a git older than 2.31). Such
        # a checkout resolves no workspace (resolve_workspace_uuid), and
        # these steps would mint one keyed on its own path, which step 3 of
        # _require_workspace() then finds by the legacy id (in an orphan, a
        # hash of that path). So the server mints nothing, and its write
        # tools answer workspace_unresolved. One case still resolves: a
        # healthy linked worktree under a git older than 2.31 keeps the root
        # commit's legacy id, so step 3 finds the repository's own
        # workspace when one exists, the one place a server resolves where
        # the session-start hook refuses.
        if _git_cannot_answer_for_git_file(_project_root):
            print(
                "entity-server: project registration and backfill skipped: "
                f"the .git at {_project_root!r} is a file git cannot answer for",
                file=sys.stderr,
            )
        else:
            try:
                _git_info = collect_git_info(_project_root)
                _upsert_project(_db, _git_info)
            except Exception as exc:
                print(f"entity-server: project upsert failed: {exc}", file=sys.stderr)

            # Claim __unknown__ entities matching this project root. Pass the
            # resolved workspace identity so entities are claimed into it
            # directly (never cross-attributed into a stale legacy-keyed row).
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

        # Seed missing workflow_phases rows on every startup, OUTSIDE the
        # backfill_complete guard, so newly registered entities get rows (an
        # existing row is kept; only a brainstorm's or backlog item's NULL
        # phase is filled in). W2.6: it reads the registry only, never a
        # .meta.json, and seeds this server's workspace only, so it is
        # skipped when no workspace resolved.
        if _workspace_uuid:
            try:
                from entity_registry.backfill import backfill_workflow_phases

                result = backfill_workflow_phases(_db, workspace_uuid=_workspace_uuid)
                if result["created"] > 0:
                    print(
                        f"entity-server: workflow_phases backfill created {result['created']} rows",
                        file=sys.stderr,
                    )
            except Exception as exc:
                print(f"entity-server: workflow_phases backfill failed: {exc}", file=sys.stderr)
        else:
            print(
                "entity-server: workflow_phases backfill skipped: workspace unresolved",
                file=sys.stderr,
            )

        print(
            f"entity-server: started (db={db_path}, artifacts={_artifacts_root})",
            file=sys.stderr,
        )

    try:
        yield {}
    finally:
        if _db is not None:
            _db.close()
            _db = None
        _config = {}


# ---------------------------------------------------------------------------
# Ref resolution: the write tools resolve in the server's workspace (W3.4)
# ---------------------------------------------------------------------------


def _resolve_ref_param(
    db: EntityDatabase,
    type_id: str | None,
    ref: str | None,
    *,
    ref_may_be_deleted: bool = False,
) -> tuple[str, str]:
    """Resolve a write tool's entity parameter to ``(uuid, type_id)`` (W3.4).

    The tool writes by the uuid, never re-resolving the type_id, and names
    the type_id in its answer.

    - **An explicit uuid,** in either parameter, passes through unchanged.
      A uuid names one entity in any workspace (D5), so the server resolves
      no workspace for it: a call naming its entities only by uuid needs
      none, unless it also registers an entity, which ``create_key_result``
      does in the server's workspace.
    - **A type_id** (an exact match) **or a ref** (an exact type_id, then a
      unique type_id prefix, as :meth:`EntityDatabase.resolve_ref` matches
      it) resolves only in the server's own workspace,
      ``_require_workspace()`` (W4.1). A type_id only another workspace holds
      is not found, and one that two workspaces hold names this workspace's
      entity.
    - **Precedence:** ``type_id`` wins when both are given.
    - **Soft-deleted entities** match as they did before W3.4, which changed
      only the workspace a type_id or ref resolves in:
      - a ``type_id`` matches one, as the registry's own writers match a
        type_id;
      - a ``ref`` does not, unless ``ref_may_be_deleted``. The dependency
        and alignment tools pass it: they resolved a ref with
        :meth:`EntityDatabase.resolve_ref` alone, whose exact type_id and
        prefix matches include a soft-deleted entity (its uuid match never
        does). So ``remove_dependency`` still clears an edge to a deleted
        blocker by its type_id.

    Raises ``ValueError`` when neither parameter is given or no entity
    matches, and ``WorkspaceUnresolvedError`` when a type_id or ref needs a
    workspace and none resolves.
    """
    if type_id is not None:
        if _UUID_RE.match(type_id.lower()):
            entity = db.get_entity_by_uuid(type_id.lower(), include_deleted=True)
            if entity is not None:
                return entity["uuid"], entity["type_id"]
        else:
            entity_uuid, _ = db.resolve_entity_uuid(_require_workspace(), type_id)
            if entity_uuid is not None:
                return entity_uuid, type_id
        raise ValueError(f"Entity not found: {type_id!r}")
    if ref is None:
        raise ValueError("Either type_id or ref must be provided")
    # resolve_ref matches a uuid in any workspace, so only a type_id or
    # prefix needs the server's.
    workspace_uuid = None if _UUID_RE.match(ref.lower()) else _require_workspace()
    entity_uuid = db.resolve_ref(ref, workspace_uuid=workspace_uuid)
    entity = db.get_entity_by_uuid(entity_uuid, include_deleted=ref_may_be_deleted)
    if entity is None:
        raise ValueError(f"No entity found matching ref: {ref!r}")
    return entity_uuid, entity["type_id"]


def _resolve_type_id_for_read(
    db: EntityDatabase,
    type_id: str | None,
    ref: str | None,
    *,
    project_id: str | None = None,
) -> str:
    """Resolve a read tool's type_id or ref parameter to a type_id.

    The read tools keep their resolution (W4.1 leaves them as they were;
    W3.4 scopes only the write tools):

    - **A type_id** passes through as given; the read resolves it.
    - **A ref** resolves through :meth:`EntityDatabase.resolve_ref` in the
      workspace ``project_id`` names by its legacy id, or in every workspace
      when ``project_id`` is None.

    Raises ``ValueError`` when neither parameter is given, or the ref matches
    no entity or several.
    """
    if type_id is not None:
        return type_id
    if ref is None:
        raise ValueError("Either type_id or ref must be provided")
    entity = db.get_entity_by_uuid(db.resolve_ref(ref, project_id=project_id))
    if entity is None:
        raise ValueError(f"No entity found matching ref: {ref!r}")
    return entity["type_id"]


# ---------------------------------------------------------------------------
# Sync DB-logic helpers (Type B handlers — extracted for @with_retry)
# ---------------------------------------------------------------------------


# Each helper below writes by the uuids its tool resolved (W3.4), never
# re-resolving a type_id, and names the entities by type_id in its answer.


@with_retry("entity")
def _process_update_entity(
    db: EntityDatabase,
    entity_uuid: str,
    type_id: str,
    name: str | None,
    description: str | None,
    status: str | None,
    metadata: dict | None,
    new_project_id: str | None = None,
    archived: bool | None = None,
) -> str:
    """Update mutable fields of an existing entity (retryable).

    ``archived`` (W1.2) then sets (True) or clears (False) the entity's
    archive flag by the same uuid, which names the updated entity even
    after a re-attribution; None leaves the flag as it is. Both writes are
    idempotent, so a retry repeats them safely.
    """
    db.update_entity(
        entity_uuid, name=name, status=status,
        artifact_path=description, metadata=metadata,
        new_project_id=new_project_id,
    )
    if archived is not None:
        db.set_archived(entity_uuid, archived)
    return f"Updated: {type_id}"


@with_retry("entity")
def _process_delete_entity(db: EntityDatabase, entity_uuid: str, type_id: str) -> str:
    """Delete an entity (retryable). ``db.delete_entity``'s has-children
    refusal names the entity by the uuid it was handed; the refusal raised
    here names it by type_id, as the confirmation does."""
    try:
        db.delete_entity(entity_uuid)
    except ValueError as exc:
        raise ValueError(str(exc).replace(entity_uuid, type_id)) from exc
    return json.dumps({"result": f"Deleted: {type_id}"})


@with_retry("entity")
def _process_add_entity_tag(
    db: EntityDatabase, entity_uuid: str, type_id: str, tag: str,
) -> str:
    """Add a tag to an entity (retryable). A soft-deleted entity is not
    tagged."""
    if db.get_entity_by_uuid(entity_uuid) is None:
        return f"Error: entity not found: {type_id}"
    db.add_tag(entity_uuid, tag)
    return json.dumps({"result": f"Tagged {type_id} with '{tag}'"})


@with_retry("entity")
def _process_add_dependency(
    db: EntityDatabase,
    dep_mgr,
    entity_uuid: str,
    blocked_by_uuid: str,
    entity_type_id: str,
    blocked_by_type_id: str,
) -> str:
    """Record that ``entity_uuid`` is blocked by ``blocked_by_uuid``
    (retryable)."""
    dep_mgr.add_dependency(db, entity_uuid, blocked_by_uuid)
    return json.dumps({
        "result": f"Dependency added: {entity_type_id} blocked by {blocked_by_type_id}"
    })


@with_retry("entity")
def _process_remove_dependency(
    db: EntityDatabase,
    dep_mgr,
    entity_uuid: str,
    blocked_by_uuid: str,
    entity_type_id: str,
    blocked_by_type_id: str,
) -> str:
    """Remove a dependency between two entities (retryable)."""
    dep_mgr.remove_dependency(db, entity_uuid, blocked_by_uuid)
    return json.dumps({
        "result": (
            f"Dependency removed: {entity_type_id} no longer blocked by "
            f"{blocked_by_type_id}"
        )
    })


@with_retry("entity")
def _process_add_okr_alignment(
    db: EntityDatabase, entity_uuid: str, kr_uuid: str,
    entity_type_id: str, kr_type_id: str,
) -> str:
    """Link an entity to a key result (retryable)."""
    db.add_okr_alignment(entity_uuid, kr_uuid)
    return json.dumps({"result": f"Aligned {entity_type_id} to {kr_type_id}"})


# A retry re-runs the allocation, so a locked write can leave a gap in the
# key_result sequence; allocate_entity_id accepts the same (its errors burn a
# number too). Gaps are harmless, a reused number is not.
@with_retry("entity")
def _process_create_key_result(
    db: EntityDatabase,
    parent_uuid: str,
    name: str,
    status: str | None,
    metadata_json: str,
    weight: float,
    *,
    workspace_uuid: str,
) -> str:
    """Register a key_result entity with parent linkage (retryable).

    Feature 112 / FR-4: ``db.register_entity`` is invoked with the canonical
    parent_uuid kwarg. ``parent_uuid`` is the uuid the tool resolved (W3.4),
    never re-resolved from a type_id. ``workspace_uuid`` (the calling
    server's, W4.1) is the one workspace that allocates the number and holds
    the row (C17).
    """
    if db.get_entity_by_uuid(parent_uuid) is None:
        # FR-9: explicit missing-parent surfacing (was: silent orphan).
        # Caught by the MCP create_key_result wrapper's except Exception,
        # which returns it to the caller as a JSON error.
        raise ValueError(f"Parent entity not found: {parent_uuid!r}")
    # Allocated after the parent check, so a missing parent burns no number.
    seq, slug = generate_entity_id(db, "key_result", name, workspace_uuid=workspace_uuid)
    type_id = f"key_result:{render_display_id('key_result', seq, slug)}"
    # F12 audit: conflict-is-error → register_entity, EntityExistsError translated to MCP JSON
    try:
        uuid = db.register_entity(
            entity_type="key_result",
            seq=seq,
            slug=slug,
            name=name,
            status=status,
            parent_uuid=parent_uuid,
            metadata=parse_metadata(metadata_json),
            workspace_uuid=workspace_uuid,
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
    return json.dumps({"uuid": uuid, "type_id": type_id, "weight": weight})


@with_retry("entity")
def _process_update_kr_score(
    db: EntityDatabase, entity_uuid: str, type_id: str, score: float,
) -> str:
    """Update score for a key_result entity (retryable)."""
    db.update_entity(entity_uuid, metadata={"score": float(score)})
    return json.dumps({"result": f"Score updated to {score}", "type_id": type_id})


def _incomplete_bucket_envelope(refusal: IncompleteBucketError) -> str:
    """C3's allocation refusal as a structured error envelope.

    Returned once, never retried: the refusal is a registry state that only
    a repair outside the allocator changes, so a retry could only repeat it.
    """
    return json.dumps({
        "error": True,
        "error_type": refusal.ERROR_TYPE,
        "message": str(refusal),
        "type_ids": refusal.type_ids,
        "recovery_hint": refusal.RECOVERY_HINT,
    })


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("entity-registry", lifespan=lifespan)


@mcp.tool()
async def register_entity(
    entity_type: str,
    seq: int | None = None,
    slug: str | None = None,
    display_id: str | None = None,
    name: str = "",
    artifact_path: str | None = None,
    status: str | None = None,
    parent_uuid: str | None = None,
    metadata: str | dict | None = None,
    workspace_uuid: str | None = None,
    auto_id: bool = False,
) -> str:
    """Register a new entity in the lineage registry.

    Parameters
    ----------
    entity_type:
        One of: backlog, brainstorm, project, feature.
    seq, slug:
        The identity of a sequence-numbered kind, as ``allocate_entity_id``
        returned them (e.g. ``29``, ``'entity-lineage-tracking'``); the
        registry renders ``029-entity-lineage-tracking``. Required unless
        auto_id=True or display_id is given.
    display_id:
        The identity of a kind with no sequence (a brainstorm's file stem),
        stored as given.
    name:
        Human-readable name (e.g. 'Entity Lineage Tracking'). Must be
        non-blank — a blank/whitespace-only name returns an
        ``invalid_input`` error envelope (feature 121 FR-5) instead of
        registering.
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
        Workspace identity (feature 108). When ``None``, the server's own
        workspace, resolved on demand (W4.1); a server with none answers a
        ``workspace_unresolved`` error envelope and registers nothing.
    auto_id:
        If True, allocate seq and derive slug from name. Cannot be used
        together with seq, slug or display_id. An allocation the registry
        refuses (C3) returns an ``incomplete_bucket`` error envelope and
        registers nothing.

    Returns confirmation message or error.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    # Feature 121 D2: blank/whitespace name corrupts the registry (FR-5) —
    # pre-check BEFORE any sequence consumption (the auto_id branch below
    # calls generate_entity_id, which burns a counter value). Fires for
    # BOTH auto_id and explicit-id calls: register_entity always persists
    # `name`, so both call shapes need the same guard. Replaces the old
    # auto_id-only truthy guard, which let a blank explicit-id name reach
    # the DB-layer raise unguarded (bare crash, no structured error).
    if not name or not name.strip():
        return json.dumps({
            "error": True,
            "error_type": "invalid_input",
            # Single-sourced from the DB layer's constant — a hand-typed
            # copy here would silently drift (author-restated-literal class).
            "message": EntityDatabase._BLANK_NAME_ERROR,
            "recovery_hint": "pass a non-blank name",
        })

    identity = {key: value for key, value in
                (("seq", seq), ("slug", slug), ("display_id", display_id))
                if value is not None}
    if auto_id and identity:
        return "Error: cannot specify both auto_id=True and seq/slug/display_id"
    if not auto_id and not identity:
        return "Error: seq and slug (display_id for a brainstorm) are required, or use auto_id=True"

    # C17 + W4.1: one workspace allocates the number and holds the row: the
    # one given, else this server's, resolved on demand. A server with none
    # refuses here, before a number is taken.
    try:
        resolved_workspace_uuid = workspace_uuid or _require_workspace()
    except WorkspaceUnresolvedError as unresolved:
        return unresolved.envelope
    if auto_id:
        # A workspace with no workspaces row (the split-brain) is refused
        # before a number is taken, with the string _process_register_entity
        # returns when register_entity refuses it.
        try:
            _db._validated_provided_workspace_uuid(
                resolved_workspace_uuid, "register_entity"
            )
        except ValueError as refusal:
            return f"Error registering entity: {refusal}"
        try:
            seq, slug = generate_entity_id(
                _db, entity_type, name, workspace_uuid=resolved_workspace_uuid
            )
        except IncompleteBucketError as refusal:
            return _incomplete_bucket_envelope(refusal)
        identity = {"seq": seq, "slug": slug}

    if isinstance(metadata, dict):
        metadata = json.dumps(metadata)

    # _process_register_entity registers in resolved_workspace_uuid, never
    # empty here, so it never falls back to a legacy project id.
    # F12 audit: conflict-is-error → register_entity, EntityExistsError translated to MCP JSON
    # (translation happens inside _process_register_entity which returns the
    # legacy "Already existed: ..." concise format on EntityExistsError per
    # server_helpers.py — see design §3.5 for the structured JSON shape used
    # by other MCP tool sites.)
    return _process_register_entity(
        _db, entity_type, identity, name,
        artifact_path, status, None,  # parent_type_id removed (FR-13 AC).
        parse_metadata(metadata),
        parent_uuid=parent_uuid,
        workspace_uuid=resolved_workspace_uuid,
    )


# ---------------------------------------------------------------------------
# Feature 121 D1 — allocate_entity_id MCP tool
# ---------------------------------------------------------------------------


@mcp.tool()
async def allocate_entity_id(entity_type: str = "", name: str = "") -> str:   # async: matches every sibling @mcp.tool def
    """Atomically allocate the next {seq:03d}-{slug} entity id for a type.

    Direct plumbing over ``next_sequence_value`` + ``_slugify`` (design
    D1) — the same atomic ``BEGIN IMMEDIATE`` counter every allocating
    path uses (``generate_entity_id`` included), exposed standalone so
    callers (create-feature, create-project, decomposing) can mint an id
    BEFORE any filesystem/DB write (feature 121 SC1). No sequence value
    is consumed when an error envelope is returned.

    The number comes from the registry alone, never the disk: it is
    above every display number registered for that kind in the workspace
    (C1/C2), but a directory the registry has no row for is invisible to
    it. That is why ``/pd:create-feature`` and ``/pd:create-project``
    still compare it with the directories on disk before creating
    anything.

    Parameters
    ----------
    entity_type:
        The entity type to allocate a sequence value for (e.g. 'feature').
        Required. ``'project'`` is accepted like any other kind; every
        kind's id is shaped ``{seq:03d}-{slug}``.
    name:
        Human-readable name; slugified into the id's suffix. Must slugify
        to a non-empty string.

    Returns
    -------
    str
        JSON ``{"seq": <int>, "slug": "<slug>", "entity_id": "<seq:03d>-<slug>"}``
        on success: register with ``seq`` and ``slug``; ``entity_id`` names the
        directory and branch. On failure, a structured error envelope
        (``workspace_unresolved`` when the server has no workspace and none
        resolves on demand (W4.1), ``invalid_input``, or ``incomplete_bucket``
        when the registry refuses the allocation (C3): the bucket holds an
        entity with no display row that the display-row invariant does not
        exempt; the envelope lists them in ``type_ids``).
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    try:
        workspace_uuid = _require_workspace()
    except WorkspaceUnresolvedError as unresolved:
        return unresolved.envelope
    if not entity_type:
        return json.dumps({
            "error": True,
            "error_type": "invalid_input",
            "message": "entity_type is required",
            "recovery_hint": "pass entity_type, e.g. 'feature'",
        })
    slug = _slugify(name or "")
    if not slug:
        return json.dumps({
            "error": True,
            "error_type": "invalid_input",
            "message": "name must be non-empty and slugify to a non-empty slug",
            "recovery_hint": "supply a descriptive name containing letters/digits",
        })
    # Only C3's refusal becomes an envelope; any other DB-layer error still
    # propagates to the server's own exception translation.
    try:
        seq = _db.next_sequence_value(entity_type=entity_type, workspace_uuid=workspace_uuid)
    except IncompleteBucketError as refusal:
        return _incomplete_bucket_envelope(refusal)
    return json.dumps(
        {"seq": seq, "slug": slug,
         "entity_id": render_display_id(entity_type, seq, slug)}
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
    ``parent_not_found``, and ``invalid_parent_kind``. The envelope shape
    matches the F10 ``complete_phase``
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
        Workspace identity. When it is not supplied, the first of these:
        the server's own workspace, if already resolved; the workspace
        ``project_id`` names; the server's workspace, resolved on demand
        (W4.1). A server with none answers a ``workspace_unresolved`` error
        envelope and writes nothing.
    project_id:
        Legacy project scope alias (deprecated). Names the workspace whose
        ``project_id_legacy`` it is only when neither ``workspace_uuid`` nor
        the server's own workspace is set; ``"__unknown__"`` names none. The
        parent's ``spawned_child`` event records it, else the server's own
        legacy id, else ``"__unknown__"``: the label is never empty.
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
        ``_catch_issue_spawn_errors`` decorator (FR-EX.3), or the
        ``workspace_unresolved`` envelope (W4.1).

    Raises
    ------
    ValueError
        On ``invalid_kind`` (FR-9.5), ``parent_not_found`` (FR-9.6), or
        ``invalid_parent_kind`` (FR-9.6). All three conditions are caught
        at the MCP boundary by ``_catch_issue_spawn_errors`` and
        translated to a JSON error envelope (FR-EX.3).
    IncompleteBucketError
        A ``ValueError`` subclass: the registry refused the allocation (C3)
        before anything was registered. The same decorator translates it;
        its envelope's ``error_type`` is ``incompletebucketerror``.
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

    # C17 + W4.1: one workspace allocates the number and holds the row, the
    # first of these that answers:
    # 1. the workspace_uuid given;
    # 2. this server's own workspace, if already resolved (_workspace_uuid);
    # 3. the workspace a given project_id names. "__unknown__" names none, so
    #    the unknown workspace is never written;
    # 4. this server's workspace, resolved on demand. A server with none
    #    refuses here, before anything is written.
    # 1-3 keep the order this tool had before W4.1; 4 replaces its fallback
    # to the server's legacy id and then to "__unknown__".
    spawn_workspace_uuid = workspace_uuid or _workspace_uuid
    if not spawn_workspace_uuid and project_id and project_id != "__unknown__":
        spawn_workspace_uuid = _db._resolve_optional_workspace_filter(
            None, project_id, _caller="issue_spawn"
        )
    if not spawn_workspace_uuid:
        try:
            spawn_workspace_uuid = _require_workspace()
        except WorkspaceUnresolvedError as unresolved:
            return unresolved.envelope
    # A label only (the event's workspace is the parent's). Never empty: the
    # workflow server labels its events "__unknown__" when it has no id, and
    # query_phase_events cannot filter by an empty label.
    event_project_id = project_id or _project_id or "__unknown__"

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

    # FR-9.2: generate_entity_id allocates the seq and derives the slug.
    seq, slug = generate_entity_id(_db, kind, summary, workspace_uuid=spawn_workspace_uuid)

    # FR-9.2: direct db.register_entity call (mirrors entity_server.py:502+
    # pattern). The internal _derive_type_and_lifecycle mapping (Group B)
    # converts entity_type=kind → (type='work', kind=<bug|task>,
    # lifecycle_class=<kind>_flow). NO init_entity_workflow call —
    # bug/task use the status-only model per FR-BL.
    # F12 audit: conflict-is-error → register_entity, EntityExistsError
    # bubbles to MCP boundary translator. auto_id guarantees fresh entity_id
    # so conflict is operationally impossible; raise-on-conflict semantics
    # preferred over INSERT OR IGNORE per feature 109 FR-4.
    new_uuid = _db.register_entity(
        entity_type=kind,
        seq=seq,
        slug=slug,
        name=summary,
        workspace_uuid=spawn_workspace_uuid,
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
        project_id=event_project_id,
        workspace_uuid=parent_row.get("workspace_uuid") or spawn_workspace_uuid,
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

    A type_id, or a ref that is not a uuid, names an entity in this
    server's workspace only; a uuid, in any of the four parameters, names
    one in any workspace, so another workspace's parent is named by its
    uuid (W3.4, D5). With no workspace resolved, a type_id or such a ref
    answers the ``workspace_unresolved`` error envelope.

    Returns a confirmation naming both type_ids, or an error.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    try:
        child_uuid, child_type_id = _resolve_ref_param(_db, type_id, ref)
        parent_uuid, resolved_parent_type_id = _resolve_ref_param(
            _db, parent_type_id, parent_ref,
        )
    except WorkspaceUnresolvedError as unresolved:
        return unresolved.envelope
    except ValueError as exc:
        return f"Error: {exc}"

    return _process_set_parent(
        _db, child_uuid, parent_uuid,
        child_type_id=child_type_id, parent_type_id=resolved_parent_type_id,
    )


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
        resolved_type_id = _resolve_type_id_for_read(_db, type_id, ref, project_id=_effective_project_id())
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
        resolved_type_id = _resolve_type_id_for_read(_db, type_id, ref, project_id=_effective_project_id())
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
    new_project_id: str | None = None,
    archived: bool | None = None,
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
        string; dicts are auto-coerced. Empty dict '{}' clears; omitted
        leaves it.
    ref:
        Alternative flexible reference. Mutations require exact or unique match.
    new_project_id:
        If provided, re-attribute the entity to a different project.
    archived:
        True archives the entity, False un-archives it; omitted leaves it.
        Archiving sets the ``is_archived`` flag and never touches the
        status (e.g. ``/pd:cleanup-brainstorms`` archives a deleted
        brainstorm's entity this way).

    A type_id, or a ref that is not a uuid, names an entity in this
    server's workspace only; a uuid, in either parameter, names one in any
    workspace (W3.4). With no workspace resolved, a type_id or such a ref
    answers the ``workspace_unresolved`` error envelope.

    Returns confirmation message or error.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"

    try:
        entity_uuid, resolved_type_id = _resolve_ref_param(_db, type_id, ref)
    except WorkspaceUnresolvedError as unresolved:
        return unresolved.envelope
    except ValueError as exc:
        return f"Error: {exc}"

    if isinstance(metadata, dict):
        metadata = json.dumps(metadata)

    try:
        return _process_update_entity(
            _db, entity_uuid, resolved_type_id, name=name,
            description=artifact_path, status=status,
            # Omitted stays None, "not updating": parse_metadata(None) is {},
            # which EntityDatabase.update_entity reads as "clear".
            metadata=None if metadata is None else parse_metadata(metadata),
            new_project_id=new_project_id,
            archived=archived,
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

    A type_id, or a ref that is not a uuid, names an entity in this
    server's workspace only; a uuid, in either parameter, names one in any
    workspace (W3.4). With no workspace resolved, a type_id or such a ref
    answers the ``workspace_unresolved`` error envelope.

    Returns confirmation JSON or error JSON.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        entity_uuid, resolved_type_id = _resolve_ref_param(_db, type_id, ref)
        return _process_delete_entity(_db, entity_uuid, resolved_type_id)
    except WorkspaceUnresolvedError as unresolved:
        return unresolved.envelope
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

    A type_id, or a ref that is not a uuid, names an entity in this
    server's workspace only; a uuid, in either parameter, names one in any
    workspace (W3.4). With no workspace resolved, a type_id or such a ref
    answers the ``workspace_unresolved`` error envelope.

    Returns confirmation or error.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        entity_uuid, resolved_type_id = _resolve_ref_param(_db, type_id, ref)
        return _process_add_entity_tag(_db, entity_uuid, resolved_type_id, tag)
    except WorkspaceUnresolvedError as unresolved:
        return unresolved.envelope
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
        resolved_type_id = _resolve_type_id_for_read(_db, type_id, ref, project_id=_effective_project_id())
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

    A type_id or prefix names an entity in this server's workspace only; a
    uuid names one in any workspace (W3.4, D5). A type_id or prefix with no
    workspace resolved answers the ``workspace_unresolved`` error envelope.

    Returns confirmation JSON or error JSON.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        from entity_registry.dependencies import CycleError, DependencyManager

        entity_uuid, entity_type_id = _resolve_ref_param(
            _db, None, entity_ref, ref_may_be_deleted=True,
        )
        blocked_by_uuid, blocked_by_type_id = _resolve_ref_param(
            _db, None, blocked_by_ref, ref_may_be_deleted=True,
        )
        mgr = DependencyManager()
        return _process_add_dependency(
            _db, mgr, entity_uuid, blocked_by_uuid,
            entity_type_id, blocked_by_type_id,
        )
    except WorkspaceUnresolvedError as unresolved:
        return unresolved.envelope
    except CycleError as exc:
        return json.dumps({"error": f"Cycle detected: {exc}"})
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

    A type_id or prefix names an entity in this server's workspace only; a
    uuid names one in any workspace (W3.4, D5). A type_id or prefix with no
    workspace resolved answers the ``workspace_unresolved`` error envelope.

    Returns confirmation JSON or error JSON.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        from entity_registry.dependencies import DependencyManager

        entity_uuid, entity_type_id = _resolve_ref_param(
            _db, None, entity_ref, ref_may_be_deleted=True,
        )
        blocked_by_uuid, blocked_by_type_id = _resolve_ref_param(
            _db, None, blocked_by_ref, ref_may_be_deleted=True,
        )
        mgr = DependencyManager()
        return _process_remove_dependency(
            _db, mgr, entity_uuid, blocked_by_uuid,
            entity_type_id, blocked_by_type_id,
        )
    except WorkspaceUnresolvedError as unresolved:
        return unresolved.envelope
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

    A type_id or prefix names an entity in this server's workspace only; a
    uuid names one in any workspace (W3.4, D5). A type_id or prefix with no
    workspace resolved answers the ``workspace_unresolved`` error envelope.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    try:
        entity_uuid, entity_type_id = _resolve_ref_param(
            _db, None, entity_ref, ref_may_be_deleted=True,
        )
        kr_uuid, kr_type_id = _resolve_ref_param(
            _db, None, kr_ref, ref_may_be_deleted=True,
        )
        return _process_add_okr_alignment(
            _db, entity_uuid, kr_uuid, entity_type_id, kr_type_id,
        )
    except WorkspaceUnresolvedError as unresolved:
        return unresolved.envelope
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
    status:
        Optional initial status.

    The key result registers in the server's workspace, resolved on demand
    (W4.1); a server with none answers a ``workspace_unresolved`` error
    envelope and registers nothing. A type_id or prefix names the parent in
    that workspace only; a uuid names one in any workspace (W3.4, D5).
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
        workspace_uuid = _require_workspace()
    except WorkspaceUnresolvedError as unresolved:
        return unresolved.envelope
    try:
        parent_uuid, _ = _resolve_ref_param(_db, None, parent_ref)
        metadata_json = json.dumps({"metric_type": metric_type, "weight": weight})
        return _process_create_key_result(
            _db, parent_uuid, name, status, metadata_json, weight,
            workspace_uuid=workspace_uuid,
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

    A type_id or prefix names the key result in this server's workspace
    only; a uuid names one in any workspace (W3.4). A type_id or prefix with
    no workspace resolved answers the ``workspace_unresolved`` error
    envelope.
    """
    err = _check_db_available()
    if err:
        return json.dumps(err)
    if _db is None:
        return "Error: database not initialized (server not started)"
    if not (0.0 <= score <= 1.0):
        return json.dumps({"error": f"Score must be between 0.0 and 1.0, got {score}"})
    try:
        kr_uuid, kr_type_id = _resolve_ref_param(_db, None, kr_ref)
        return _process_update_kr_score(_db, kr_uuid, kr_type_id, score)
    except WorkspaceUnresolvedError as unresolved:
        return unresolved.envelope
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
    # The server process's own bookkeeping lives here, not in the lifespan:
    # tests run the lifespan in-process, where the PID file would land in
    # the test process's HOME and the watchdog could end the test run. The
    # watchdog is armed first, so a PID file names a process it guards.
    start_parent_watchdog()
    write_pid("entity_server")
    try:
        mcp.run(transport="stdio")
    finally:
        remove_pid("entity_server")
