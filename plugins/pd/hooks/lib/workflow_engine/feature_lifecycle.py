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

from entity_registry.database import EntityDatabase
from workflow_engine.engine import WorkflowStateEngine


# ---------------------------------------------------------------------------
# Status-to-kanban mapping (single source of truth — also imported by workflow_state_server)
# ---------------------------------------------------------------------------

STATUS_TO_KANBAN: dict[str, str] = {
    "active": "wip",
    "planned": "backlog",
    "completed": "completed",
    "abandoned": "completed",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


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
) -> dict:
    """Create feature entity + workflow state. Idempotent.

    Returns dict with keys: created, feature_type_id, status, meta_json_path.
    Optionally includes projection_warning (not set here — added by MCP wrapper).

    Raises:
        ValueError: if feature_id, slug, or branch is None, empty, or whitespace-only.
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
    if backlog_source:
        metadata["backlog_source"] = backlog_source

    # Register or update entity
    existing = db.get_entity(feature_type_id)
    if existing is None:
        db.register_entity(
            entity_type="feature",
            entity_id=f"{feature_id}-{slug}",
            name=slug.replace("-", " ").title(),
            artifact_path=feature_dir,
            status=status,
            metadata=metadata,
        )
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
        db.update_entity(feature_type_id, status=status, metadata=metadata)

    # Fix kanban_column based on status (init-time uses STATUS_TO_KANBAN).
    init_kanban = STATUS_TO_KANBAN.get(status)
    if init_kanban:
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
) -> dict:
    """Create initial project state in DB + .meta.json.

    Returns dict with keys: created, project_type_id, meta_json_path.
    """
    # Path traversal validation
    if "\0" in project_dir:
        raise ValueError("invalid_input: project_dir path traversal blocked")
    resolved = os.path.realpath(project_dir)
    if not os.path.isdir(resolved):
        raise ValueError(f"invalid_input: project_dir does not exist: {project_dir}")

    project_type_id = f"project:{project_id}-{slug}"

    # Parse JSON params (raises ValueError/JSONDecodeError on malformed input)
    features_list = json.loads(features)
    milestones_list = json.loads(milestones)

    # Register entity (idempotent — skip if already exists)
    existing = db.get_entity(project_type_id)
    metadata = {
        "id": project_id,
        "slug": slug,
        "features": features_list,
        "milestones": milestones_list,
    }
    if brainstorm_source:
        metadata["brainstorm_source"] = brainstorm_source

    if existing is None:
        db.register_entity(
            entity_type="project",
            entity_id=f"{project_id}-{slug}",
            name=slug.replace("-", " ").title(),
            artifact_path=project_dir,
            status=status,
            metadata=metadata,
        )

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
    meta_path = os.path.join(project_dir, ".meta.json")
    _atomic_json_write(meta_path, meta)

    return {
        "created": True,
        "project_type_id": project_type_id,
        "meta_json_path": meta_path,
    }


def activate_feature(
    db: EntityDatabase,
    engine: WorkflowStateEngine,
    artifacts_root: str,
    feature_type_id: str,
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

    db.update_entity(feature_type_id, status="active")

    return {
        "activated": True,
        "feature_type_id": feature_type_id,
        "previous_status": "planned",
        "new_status": "active",
    }
