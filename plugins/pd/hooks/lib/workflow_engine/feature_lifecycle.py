"""Feature and project state initialization and activation.

Extracted from workflow_state_server.py MCP handlers into pure business logic
functions. Each function returns a dict; MCP wrappers call json.dumps() and
handle _project_meta_json as a post-step.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone

from entity_registry.database import _UNKNOWN_WORKSPACE_UUID, EntityDatabase, EntityExistsError
from entity_registry.id_generator import registration_identity
from workflow_engine.engine import WorkflowStateEngine


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Local replica of the former workflow_engine.kanban module (deleted at
# feature 132, Scope model D6.1-.3 — post-cutover call sites carry their
# own copy instead of importing the shared kanban.py helper). Byte-identical to
# its siblings in backfill.py / engine.py / reconciliation.py /
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


def _iso_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _atomic_json_write(path: str, data: dict) -> None:
    """Atomic JSON write: NamedTemporaryFile + os.replace()."""
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=os.path.dirname(path),
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as fd:
            tmp_name = fd.name
            json.dump(data, fd, indent=2)
            fd.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
        raise


def _validate_feature_type_id(feature_type_id: str, artifacts_root: str) -> str:
    """Validate feature_type_id and extract slug with realpath defense.

    Raises ValueError on invalid input.
    """
    if ":" not in feature_type_id:
        raise ValueError("invalid_input: missing colon in feature_type_id")

    slug = feature_type_id.split(":", 1)[1]

    if not slug:
        raise ValueError("feature_not_found: empty slug")

    if "\0" in slug:
        raise ValueError(f"feature_not_found: {slug} not found or path traversal blocked")

    candidate = os.path.join(artifacts_root, "features", slug)
    resolved = os.path.realpath(candidate)
    root = os.path.realpath(artifacts_root)

    if not resolved.startswith(root + os.sep) or not os.path.isdir(resolved):
        raise ValueError(f"feature_not_found: {slug} not found or path traversal blocked")

    return slug


def _promote_brainstorm(db: EntityDatabase, brainstorm_source: str) -> None:
    """Best-effort promotion of brainstorm entity when feature is created.

    Extracts the brainstorm stem from the source path and updates the entity
    status to 'promoted'. Also updates the workflow_phases row if it exists.
    Silently ignores all errors — feature creation must not be blocked.
    """
    stem = os.path.basename(brainstorm_source)
    if stem.endswith(".prd.md"):
        stem = stem[: -len(".prd.md")]
    type_id = f"brainstorm:{stem}"
    try:
        entity = db.get_entity(type_id)
        if entity and entity.get("status") != "promoted":
            db.update_entity(type_id, status="promoted")
            wf = db.get_workflow_phase(type_id)
            if wf:
                db.update_workflow_phase(
                    type_id,
                    workflow_phase="promoted",
                    kanban_column="completed",
                )
    except Exception:
        pass  # Best-effort — don't block feature creation


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _allocated_identity(kind: str, text_id: str, slug: str) -> dict:
    """seq/slug for an id the allocator issued, refusing one it would not render.

    The caller names the entity ``{text_id}-{slug}``; registering anything
    else would leave its type_id and its display row disagreeing.
    """
    identity = registration_identity(kind, f"{text_id}-{slug}")
    if identity is None:
        raise ValueError(
            f"invalid_input: {kind} id {text_id!r} with slug {slug!r} is not an "
            "allocated id (allocate_entity_id issues them)")
    return identity


def init_feature_state(
    db: EntityDatabase,
    engine: WorkflowStateEngine | None,
    artifacts_root: str,
    feature_dir: str,
    feature_id: str,
    slug: str,
    mode: str,
    branch: str,
    brainstorm_source: str | None = None,
    backlog_source: str | None = None,
    status: str = "active",
    *,
    workspace_uuid: str | None = None,
) -> dict:
    """Create feature entity + workflow state. Idempotent.

    Returns dict with keys: created, feature_type_id, status, meta_json_path.
    Optionally includes projection_warning (not set here — added by MCP wrapper).

    Raises:
        ValueError: if feature_id, slug, or branch is None, empty, or whitespace-only,
            or if feature_id with slug is not an id the allocator issues
            (``invalid_input: … is not an allocated id``); nothing is written.
    """
    # Field validation — reject None, empty string, whitespace-only
    for field_name, field_value in [
        ("feature_id", feature_id),
        ("slug", slug),
        ("branch", branch),
    ]:
        if field_value is None or not isinstance(field_value, str) or not field_value.strip():
            raise ValueError(f"invalid_input: {field_name} must be a non-empty string")

    feature_type_id = f"feature:{feature_id}-{slug}"
    identity = _allocated_identity("feature", feature_id, slug)

    # Validate feature_type_id for path traversal defense
    _validate_feature_type_id(feature_type_id, artifacts_root)

    # Build metadata dict
    metadata: dict = {
        "id": feature_id,
        "slug": slug,
        "mode": mode,
        "branch": branch,
        "phase_timing": {"brainstorm": {"started": _iso_now()}} if status == "active" else {},
    }
    if brainstorm_source:
        metadata["brainstorm_source"] = brainstorm_source
        _promote_brainstorm(db, brainstorm_source)
    if backlog_source:
        metadata["backlog_source"] = backlog_source

    # Register or update entity. Use ``project_id="__unknown__"`` so the
    # canonical workspaces row is auto-bootstrapped on fresh in-memory DBs.
    # Production callers running against the persistent entities.db will
    # be migrated via the existing __unknown__-bucket backfill paths.
    existing = db.get_entity(feature_type_id)
    if existing is None:
        # F12 audit: conflict-is-error → register_entity, EntityExistsError handled
        try:
            db.register_entity(
                entity_type="feature",
                **identity,
                name=slug.replace("-", " ").title(),
                artifact_path=feature_dir,
                status=status,
                metadata=metadata,
                workspace_uuid=workspace_uuid,
                project_id="__unknown__" if workspace_uuid is None else None,
            )
        except EntityExistsError as e:
            raise RuntimeError(
                f"Feature registration conflict for {feature_type_id}"
            ) from e
    else:
        # Retry path: preserve existing phase_timing, last_completed_phase,
        # skipped_phases to avoid clobbering progress data.
        existing_meta_raw = existing.get("metadata")
        if existing_meta_raw:
            existing_meta = (
                json.loads(existing_meta_raw)
                if isinstance(existing_meta_raw, str)
                else existing_meta_raw
            )
        else:
            existing_meta = {}
        metadata["phase_timing"] = existing_meta.get("phase_timing", metadata["phase_timing"])
        if existing_meta.get("last_completed_phase"):
            metadata["last_completed_phase"] = existing_meta["last_completed_phase"]
        if existing_meta.get("skipped_phases"):
            metadata["skipped_phases"] = existing_meta["skipped_phases"]
        db.update_entity(feature_type_id, status=status, metadata=metadata, workspace_uuid=workspace_uuid)

    # Fix kanban_column via _kanban_column_for (phase-aware single source of truth).
    wf_row = db.get_workflow_phase(feature_type_id)
    wf_phase = wf_row["workflow_phase"] if wf_row else None
    init_kanban = _kanban_column_for(status, wf_phase)
    try:
        db.update_workflow_phase(feature_type_id, kanban_column=init_kanban)
    except ValueError:
        # Row may not exist if engine initialization failed — create it.
        try:
            db.create_workflow_phase(feature_type_id, kanban_column=init_kanban)
        except ValueError:
            pass  # Entity itself may be missing; workflow row cannot be created

    return {
        "created": True,
        "feature_type_id": feature_type_id,
        "status": status,
        "meta_json_path": os.path.join(feature_dir, ".meta.json"),
    }


def _validate_project_dir(project_dir: str, artifacts_root: str) -> str:
    """Resolve ``project_dir``, refusing any path that is not a directory
    directly under ``{artifacts_root}/projects``.

    The directory need not exist: ``init_project_state`` creates it only
    after registration succeeds. So existence proves nothing here, and the
    checks look at where the path RESOLVES:

    - **NUL bytes** are refused outright.
    - **Containment** — the realpath (``..`` and symlinks resolved) must be
      a direct child of the realpath of ``{artifacts_root}/projects``, the
      one place reconciliation and backfill look for projects.
    - **Not a non-directory** — an existing file at the path is refused.

    Returns the resolved path. Raises ValueError (``invalid_input: …``).
    """
    if "\0" in project_dir:
        raise ValueError("invalid_input: project_dir path traversal blocked")
    projects_root = os.path.realpath(os.path.join(artifacts_root, "projects"))
    resolved = os.path.realpath(project_dir)
    if os.path.dirname(resolved) != projects_root:
        raise ValueError(
            f"invalid_input: project_dir must be a directory directly under "
            f"{projects_root} (path traversal blocked): {project_dir}"
        )
    if os.path.exists(resolved) and not os.path.isdir(resolved):
        raise ValueError(
            f"invalid_input: project_dir exists and is not a directory: {project_dir}"
        )
    return resolved


def _resumable_registration(
    db: EntityDatabase,
    conflict: EntityExistsError,
    project_dir: str,
    parent_uuid: str | None,
) -> str:
    """The uuid of the row a project registration conflicted with, when that
    row is what this same call registers: its own earlier attempt, typically
    one that registered and then stopped before its directory or
    ``.meta.json`` (a completed one re-runs, rewriting ``.meta.json``). The
    row must be:

    - **Live** — deletion is soft, so a deleted project still holds its id.
      The allocator never re-issues a spent number (C1/C2), so a conflict
      with a deleted row means the call reused an earlier id; resuming it
      would hand the new project a deleted row.
    - **Same directory** — its ``artifact_path`` is this ``project_dir``.
      Another registrar records none (the MCP ``register_entity`` tool,
      unless given one) or its own.
    - **Same parent** — another brainstorm means another project.

    Any other row raises ``RuntimeError`` (``Project registration conflict
    …``) before a directory exists. The conflict is scoped to this
    workspace, and so is the lookup: a same-id project in another workspace
    is never the row.
    """
    existing_uuid = db.resolve_ref(
        conflict.type_id, workspace_uuid=conflict.workspace_uuid
    )
    existing = db.get_entity_by_uuid(existing_uuid, include_deleted=True)
    if existing.get("is_deleted"):
        reason = "the registered project is deleted"
    elif existing.get("artifact_path") != project_dir:
        reason = (
            f"the registered project's directory is "
            f"{existing.get('artifact_path')!r}, not {project_dir!r}"
        )
    elif existing.get("parent_uuid") != parent_uuid:
        reason = (
            f"the registered project's parent is "
            f"{existing.get('parent_uuid')!r}, not {parent_uuid!r}"
        )
    else:
        return existing_uuid
    raise RuntimeError(
        f"Project registration conflict for {conflict.type_id}: {reason}"
    ) from conflict


# F4-AUDIT: project-type schema differs; ported to feature 111
def init_project_state(
    db: EntityDatabase,
    artifacts_root: str,
    project_dir: str,
    project_id: str,
    slug: str,
    branch: str,
    features: str,
    milestones: str,
    brainstorm_source: str | None = None,
    status: str = "active",
    *,
    workspace_uuid: str | None = None,
    parent_uuid: str | None = None,
) -> dict:
    """Register a project, then create its directory and write its .meta.json.

    The one owner of project registration: ``/pd:create-project`` calls this
    and never ``register_entity`` for a project. Registration precedes
    directory creation, so a registration failure leaves no directory:

    1. **Validate** ``project_dir`` (``_validate_project_dir``; it need not
       exist yet), the id (the allocator must have issued it), and the
       ``features``/``milestones`` JSON.
    2. **Register** the project, under ``parent_uuid`` when given. That
       parent must be live and in the project's workspace
       (``refuse_deleted_or_cross_workspace_parent``, in the registration's
       transaction).
    3. **Create** the directory.
    4. **Write** ``.meta.json``.

    A registration conflict resumes only a row this same call registered
    (``_resumable_registration``), typically an attempt that stopped after
    registering: the same call again continues with that row. Any other
    holder of the id — a deleted project, or a row with another directory
    or parent — is a conflict, raised before the directory exists.

    Directory and ``.meta.json`` are written at the resolved path, the one
    validated; ``artifact_path`` records ``project_dir`` as given.

    Returns dict with keys: created, project_type_id, project_uuid, resumed
    (True when an earlier attempt's registration was resumed), and
    meta_json_path.

    Raises:
        ValueError: if project_id with slug is not an id the allocator issues
            (``invalid_input: … is not an allocated id``), project_dir is
            invalid, or parent_uuid names a soft-deleted entity or one in
            another workspace; nothing is written.
        RuntimeError: ``Project registration conflict …`` when a row that is
            not this call's earlier attempt holds the id; nothing is written.
        A registration error propagates before the directory exists. An
        OSError creating the directory leaves the project registered; the
        same call again finishes it.
    """
    resolved_dir = _validate_project_dir(project_dir, artifacts_root)

    project_type_id = f"project:{project_id}-{slug}"
    identity = _allocated_identity("project", project_id, slug)

    # Parse JSON params (raises ValueError/JSONDecodeError on malformed input)
    features_list = json.loads(features)
    milestones_list = json.loads(milestones)

    metadata = {
        "id": project_id,
        "slug": slug,
        "features": features_list,
        "milestones": milestones_list,
    }
    if brainstorm_source:
        metadata["brainstorm_source"] = brainstorm_source

    # The parent must be live and in the workspace the project registers in
    # (the parent rules reparent_entity enforces, C22a). The check shares the
    # registration's transaction, so the parent cannot change between the
    # two. Without a workspace_uuid, the project registers in the default
    # __unknown__ workspace (the project_id argument below).
    #
    # Use ``project_id="__unknown__"`` so the canonical workspaces row is
    # auto-bootstrapped on fresh in-memory DBs (matches feature 108 pattern).
    # C4 dropped the project "P" prefix: projects render "{NNN}-{slug}"
    # like every other sequence-numbered kind, so the allocated id splits
    # into seq and slug and the display row is written.
    project_workspace_uuid = (
        workspace_uuid if workspace_uuid is not None else _UNKNOWN_WORKSPACE_UUID
    )
    try:
        with db.transaction():
            if parent_uuid is not None:
                db.refuse_deleted_or_cross_workspace_parent(
                    parent_uuid,
                    workspace_uuid=project_workspace_uuid,
                    child_ref=project_type_id,
                    caller="init_project_state",
                )
            # F12 audit: conflict-is-error → register_entity, EntityExistsError
            # handled below: resumed only when the row is this call's own
            # earlier attempt.
            project_uuid = db.register_entity(
                entity_type="project",
                **identity,
                name=slug.replace("-", " ").title(),
                artifact_path=project_dir,
                status=status,
                parent_uuid=parent_uuid,
                metadata=metadata,
                workspace_uuid=workspace_uuid,
                project_id="__unknown__" if workspace_uuid is None else None,
            )
        resumed = False
    except EntityExistsError as conflict:
        # The conflict is scoped to this workspace. The row is resumed only
        # if it is this call's own earlier attempt; any other holder of the
        # id raises here, before the directory. (An unscoped get_entity
        # pre-check let a same-id project in another workspace skip this
        # one's registration.)
        project_uuid = _resumable_registration(db, conflict, project_dir, parent_uuid)
        resumed = True

    # The directory exists only once the registry holds the project. Both
    # writes use the resolved path: the one validated, and one the kernel
    # can walk (``missing/../`` in the path as given is not).
    os.makedirs(resolved_dir, exist_ok=True)

    # Build project .meta.json
    meta = {
        "id": project_id,
        "slug": slug,
        "status": status,
        "created": _iso_now(),
        "features": features_list,
        "milestones": milestones_list,
    }
    if brainstorm_source:
        meta["brainstorm_source"] = brainstorm_source

    # Atomic write
    meta_path = os.path.join(resolved_dir, ".meta.json")
    _atomic_json_write(meta_path, meta)

    return {
        "created": True,
        "project_type_id": project_type_id,
        "project_uuid": project_uuid,
        "resumed": resumed,
        "meta_json_path": meta_path,
    }


def activate_feature(
    db: EntityDatabase,
    engine: WorkflowStateEngine,
    artifacts_root: str,
    feature_type_id: str,
    *,
    workspace_uuid: str | None = None,
) -> dict:
    """Transition a planned feature to active status.

    Pre-condition: entity status must be 'planned'.
    Post-condition: entity status becomes 'active'.

    Returns dict with keys: activated, feature_type_id, previous_status, new_status.
    Optionally includes projection_warning (not set here — added by MCP wrapper).
    """
    _validate_feature_type_id(feature_type_id, artifacts_root)

    entity = db.get_entity(feature_type_id)
    if entity is None:
        raise ValueError(f"feature_not_found: {feature_type_id}")

    current_status = entity.get("status")
    if current_status != "planned":
        raise ValueError(
            f"invalid_transition: feature status is '{current_status}', "
            f"expected 'planned' for activation"
        )

    db.update_entity(feature_type_id, status="active", workspace_uuid=workspace_uuid)

    return {
        "activated": True,
        "feature_type_id": feature_type_id,
        "previous_status": "planned",
        "new_status": "active",
    }
