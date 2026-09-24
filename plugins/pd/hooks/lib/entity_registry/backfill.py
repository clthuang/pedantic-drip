"""Backfill scanner for migrating existing pd artifacts into the entity registry.

Scans features, projects, brainstorms, and backlog items from the artifact
directory and registers them in the EntityDatabase with correct parent-child
relationships.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import re
import sys

from entity_registry.database import EntityDatabase, EntityExistsError
from entity_registry.id_generator import registration_identity, render_display_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENTITY_SCAN_ORDER = ["backlog", "brainstorm", "project", "feature"]

# Regex patterns for backlog marker extraction from brainstorm PRDs
# B7 (2026-09-22): widened from \d{5}. These markers are hand-copied out of
# backlog.md into PRDs, so after B7 people write "#063-watch-…" while every
# document already on disk says "#00063". BOTH must keep resolving or the
# backlog->feature link is silently lost for one generation of documents.
BACKLOG_MARKER_PATTERN_1 = r"\*Source:\s*Backlog\s*#([0-9][^\s*]*)\*"
BACKLOG_MARKER_PATTERN_2 = r"\*\*Backlog Item:\*\*\s*([0-9][^\s*]*)"

# Statuses after which an entity's work is over; the NULL-phase cleanup
# marks only these finished.
_DONE_STATUSES = frozenset({"completed", "abandoned"})

PHASE_SEQUENCE: tuple[str, ...] = (
    "brainstorm", "specify", "design", "create-plan",
    "implement", "finish",
)

# Valid statuses for kanban derivation (used for validation only)
_VALID_STATUSES: frozenset[str] = frozenset({"planned", "active", "completed", "abandoned"})

VALID_MODES: frozenset[str] = frozenset({"standard", "full", "light"})

BACKFILL_BATCH_SIZE = 20

# Local replica of the former workflow_engine.kanban module (deleted at
# feature 132, Scope model D6.1-.3 — post-cutover call sites carry their
# own copy instead of importing the shared kanban.py helper). Byte-identical to
# its siblings in engine.py / feature_lifecycle.py / reconciliation.py /
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


def _chunked(iterable, size: int):
    """Yield successive chunks of *size* from *iterable*."""
    batch: list = []
    for item in iterable:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


# ---------------------------------------------------------------------------
# Workflow phase helpers (private)
# ---------------------------------------------------------------------------


def _derive_next_phase(last_completed: str | None) -> str | None:
    """Return the phase after last_completed, or None if finish/unrecognized.

    - None input -> None
    - "finish" -> "finish" (terminal state per D-5)
    - Recognized phase -> next phase in PHASE_SEQUENCE
    - Unrecognized -> None
    """
    if last_completed is None:
        return None
    if last_completed == "finish":
        return "finish"
    try:
        idx = PHASE_SEQUENCE.index(last_completed)
    except ValueError:
        return None
    if idx + 1 < len(PHASE_SEQUENCE):
        return PHASE_SEQUENCE[idx + 1]
    return None


def _resolve_meta_path(
    entity: dict, artifacts_root: str
) -> str | None:
    """Resolve .meta.json path from artifact_path or convention fallback.

    Returns None for entities without artifact_path and no matching
    convention directory (expected for brainstorms/backlogs without
    artifact directories).
    """
    # Priority 1: artifact_path based lookup
    artifact_path = entity.get("artifact_path")
    if artifact_path is not None:
        candidate = os.path.join(artifact_path, ".meta.json")
        if os.path.isfile(candidate):
            return candidate

    # Priority 2: convention fallback
    entity_type = entity["entity_type"]
    entity_id = entity["entity_id"]
    convention = os.path.join(
        artifacts_root, f"{entity_type}s", entity_id, ".meta.json"
    )
    if os.path.isfile(convention):
        return convention

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_backfill(
    db: EntityDatabase, artifacts_root: str, header_aware: bool = False,
    project_id: str = "__unknown__",
) -> None:
    """Scan artifact directories and register entities in topological order.

    Parameters
    ----------
    db:
        An open EntityDatabase to register entities into.
    artifacts_root:
        Root directory containing features/, brainstorms/, projects/, backlog.md.
    header_aware:
        If True, stamp frontmatter headers on all discovered artifact files
        BEFORE the backfill_complete guard check.  This ensures headers are
        stamped even on already-backfilled databases (spec R26).
        Defaults to False for backward compatibility (spec R25).
    """
    # Step 1: Header stamping (independent of backfill_complete) — spec R26
    if header_aware:
        from entity_registry.frontmatter_sync import backfill_headers

        backfill_headers(db, artifacts_root)

    # Guard: skip entity registration if backfill already completed
    # Backfill version tracks schema changes that require re-scanning
    # (e.g., name enrichment logic). Bump _BACKFILL_VERSION when scan
    # logic changes to trigger a one-time re-scan on existing DBs.
    _BACKFILL_VERSION = "4"  # v4: backlog status sync from annotations

    current_version = db.get_metadata("backfill_version") or "0"
    if db.get_metadata("backfill_complete") == "1" and current_version >= _BACKFILL_VERSION:
        return

    scanners = {
        "backlog": _scan_backlog,
        "brainstorm": _scan_brainstorms,
        "project": _scan_projects,
        "feature": _scan_features,
    }

    # Resolved before any write: an unknown workspace fails here, not halfway.
    workspace_uuid = _workspace(db, project_id)
    for entity_type in ENTITY_SCAN_ORDER:
        scanners[entity_type](db, artifacts_root, project_id=project_id)

    # A NULL workflow_phase on an entity already done (e.g. abandoned) means
    # it finished. Only this workspace's rows, and only done entities: a
    # planned feature has no phase yet, and another workspace's rows are not
    # this backfill's to change.
    done = {e["type_id"] for e in db.list_entities(workspace_uuid=workspace_uuid)
            if e["status"] in _DONE_STATUSES}
    with db.transaction():
        for row in db.list_workflow_phases(workspace_uuid=workspace_uuid):
            if row["workflow_phase"] is None and row["type_id"] in done:
                try:
                    db.update_workflow_phase(row["type_id"], workflow_phase="finish",
                                             workspace_uuid=workspace_uuid)
                except ValueError:
                    pass  # TOCTOU: row deleted between list and update

    # Mark backfill as complete with current version
    db.set_metadata("backfill_complete", "1")
    db.set_metadata("backfill_version", _BACKFILL_VERSION)


def backfill_workflow_phases(
    db: EntityDatabase,
    artifacts_root: str,
    project_id: str = "__unknown__",
) -> dict:
    """Backfill workflow_phases rows for all eligible entities.

    Reads entity data from DB + .meta.json files. Creates rows
    using INSERT OR IGNORE for idempotency.

    Parameters
    ----------
    db:
        Open EntityDatabase instance.
    artifacts_root:
        Root directory containing feature/brainstorm/backlog artifacts.

    Returns
    -------
    dict
        {"created": int, "updated": int, "skipped": int, "errors": list[str]}
    """
    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []

    # Query all entities via public API, exclude projects in Python
    all_entities = db.list_entities()
    entities = [e for e in all_entities if e["entity_type"] != "project"]

    for batch in _chunked(entities, BACKFILL_BATCH_SIZE):
        with db.transaction():
            for entity in batch:
                try:
                    type_id = entity["type_id"]
                    entity_type = entity["entity_type"]

                    # Resolve .meta.json
                    meta_path = _resolve_meta_path(entity, artifacts_root)
                    meta = None
                    if meta_path is not None:
                        meta = _read_json(meta_path)
                        # Distinguish "malformed JSON" from "file not found" (D-9, AC-18)
                        if meta is None and os.path.isfile(meta_path):
                            logger.warning(
                                "Malformed JSON in %s for entity %s, using defaults",
                                meta_path, type_id,
                            )

                    # Early handling for brainstorm/backlog — skip kanban derivation
                    if entity_type in ("brainstorm", "backlog"):
                        # Child-completion override (D3: prefer parent_uuid, fall back
                        # to parent_type_id for legacy entities without parent_uuid)
                        entity_uuid = entity.get("uuid")
                        children = [
                            e for e in all_entities
                            if e["entity_type"] == "feature"
                            and (
                                (entity_uuid and e.get("parent_uuid") == entity_uuid)
                                or (
                                    not e.get("parent_uuid")
                                    and e.get("parent_type_id") == type_id
                                )
                            )
                        ]
                        all_children_completed = children and all(
                            c.get("status") == "completed" for c in children
                        )

                        # Check existing workflow_phases row
                        existing_row = db.get_workflow_phase(type_id)

                        if existing_row and existing_row["workflow_phase"] is not None:
                            skipped += 1
                            continue

                        # Derive defaults
                        if entity_type == "brainstorm":
                            workflow_phase = "draft"
                            kanban_column = "wip"
                        else:  # backlog
                            workflow_phase = "open"
                            kanban_column = "backlog"

                        # Apply child-completion override
                        if all_children_completed:
                            kanban_column = "completed"

                        # Case 3: existing row with NULL phase -> UPDATE
                        if existing_row and existing_row["workflow_phase"] is None:
                            db.update_workflow_phase(
                                type_id,
                                workflow_phase=workflow_phase,
                                kanban_column=kanban_column,
                            )
                            updated += 1
                            continue

                        # Case 1: no row -> INSERT (upsert for idempotency)
                        db.upsert_workflow_phase(
                            type_id,
                            project_id=project_id,
                            workflow_phase=workflow_phase,
                            kanban_column=kanban_column,
                        )
                        created += 1
                        continue

                    # 3-tier status resolution
                    status = None
                    if meta is not None and "status" in meta:
                        status = meta["status"]
                    if status is None and entity["status"] is not None:
                        status = entity["status"]
                    if status is None:
                        status = "planned"

                    # Validate status
                    if status not in _VALID_STATUSES:
                        logger.warning(
                            "Unmapped status %r for entity %s, defaulting to 'planned'",
                            status, type_id,
                        )
                        status = "planned"

                    # Feature-specific: derive workflow_phase, last_completed_phase, mode
                    workflow_phase = None
                    last_completed_phase = None
                    mode = None

                    if entity_type == "feature":
                        # last_completed_phase from .meta.json
                        if meta is not None:
                            last_completed_phase = meta.get("lastCompletedPhase")
                        # Validate last_completed_phase
                        if last_completed_phase is not None and last_completed_phase not in PHASE_SEQUENCE:
                            logger.warning(
                                "Unrecognized lastCompletedPhase %r for entity %s, setting to None",
                                last_completed_phase, type_id,
                            )
                            last_completed_phase = None

                        # Derive workflow_phase
                        workflow_phase = _derive_next_phase(last_completed_phase)

                        # Special case: completed status -> workflow_phase = finish
                        if status == "completed":
                            workflow_phase = "finish"

                        # mode from .meta.json
                        if meta is not None:
                            mode = meta.get("mode")
                        # Validate mode
                        if mode is not None and mode not in VALID_MODES:
                            logger.warning(
                                "Invalid mode %r for entity %s, setting to None",
                                mode, type_id,
                            )
                            mode = None

                    kanban_column = _kanban_column_for(status, workflow_phase)

                    # Skip if row already exists (idempotent — don't overwrite)
                    if db.get_workflow_phase(type_id) is not None:
                        skipped += 1
                        continue

                    # Upsert for idempotency (INSERT OR IGNORE + UPDATE)
                    db.upsert_workflow_phase(
                        type_id,
                        project_id=project_id,
                        workflow_phase=workflow_phase,
                        kanban_column=kanban_column,
                        last_completed_phase=last_completed_phase,
                        mode=mode,
                    )
                    created += 1

                except Exception as exc:
                    errors.append(f"Error processing {entity.get('type_id', '?')}: {exc}")

    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Scanner functions
# ---------------------------------------------------------------------------


def _scan_backlog(db: EntityDatabase, artifacts_root: str, project_id: str = "__unknown__") -> None:
    """Parse backlog.md and register each row as a backlog entity."""
    backlog_path = os.path.join(artifacts_root, "backlog.md")
    if not os.path.isfile(backlog_path):
        return

    with open(backlog_path) as f:
        content = f.read()

    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        # Skip header and separator rows
        cells = [c.strip() for c in line.split("|")]
        # Split produces ['', cell1, cell2, ..., ''] for | delimited rows
        cells = [c for c in cells if c]
        if len(cells) < 3:
            # Skip separator rows silently (all dashes), log others
            raw_cells = [c.strip() for c in line.split("|") if c.strip()]
            if raw_cells and not all(c.startswith("-") for c in raw_cells):
                print(
                    f"entity-server: backfill: skipping malformed backlog row: {line!r}",
                    file=sys.stderr,
                )
            continue
        item_id = cells[0]
        # Skip header row and separator row
        if item_id == "ID" or item_id.startswith("-"):
            continue
        identity = registration_identity("backlog", item_id)
        if identity is None:
            _log_skipped("backlog", item_id)
            continue

        description = cells[2]
        if len(description) <= 80:
            title = description
        else:
            truncated = description[:80].rsplit(" ", 1)[0]
            title = (truncated if truncated != description[:80] else description[:80]) + "\u2026"

        # F12 audit: idempotent backfill → upsert_entity
        db.upsert_entity(
            entity_type="backlog",
            **identity,
            name=title,
            artifact_path=backlog_path,
            metadata={"description": description},
            project_id=project_id,
        )
        db.update_entity(
            type_id=f"backlog:{item_id}",
            project_id=project_id,
            name=title,
            metadata={"description": description},
        )

        # Feature 111 / FR-CL.1: free-text suffix parsers removed.
        # entities.status is authoritative (set via complete_phase closes= or
        # explicit update_entity). Backfill no longer derives status from
        # historical prose markers in the description text.


def _scan_brainstorms(db: EntityDatabase, artifacts_root: str, project_id: str = "__unknown__") -> None:
    """Glob brainstorm files and register each as a brainstorm entity.

    .prd.md files are scanned first; .md files only for unregistered stems.
    """
    bs_dir = os.path.join(artifacts_root, "brainstorms")
    if not os.path.isdir(bs_dir):
        return

    registered_stems: set[str] = set()

    # Phase 1: .prd.md files (higher priority)
    prd_files = sorted(glob.glob(os.path.join(bs_dir, "*.prd.md")))
    for path in prd_files:
        stem = _brainstorm_stem(path)
        _register_brainstorm(db, path, stem, project_id=project_id)
        registered_stems.add(stem)

    # Phase 2: .md files (only unregistered stems)
    md_files = sorted(glob.glob(os.path.join(bs_dir, "*.md")))
    for path in md_files:
        # Skip .prd.md files (already processed)
        if path.endswith(".prd.md"):
            continue
        stem = _brainstorm_stem(path)
        if stem in registered_stems:
            continue

        _register_brainstorm(db, path, stem, project_id=project_id)
        registered_stems.add(stem)


def _read_entity_display_for_project(
    db: EntityDatabase, meta: dict, workspace_uuid: str
) -> dict | None:
    """Look up the ``entity_display`` row for a project whose ``.meta.json``
    has been read off disk (feature 110 FR-8.3c port).

    Returns the ``(seq, slug)`` row if both (a) the project entity is
    already registered in the DB (re-run scenario) AND (b) ``entity_display``
    has a corresponding row. Returns ``None`` for first-pass backfill where
    the entity does not yet exist, OR if ``entity_display`` is absent
    (pre-migration-13).

    The caller falls back to ``meta.get("id", "")`` when this returns
    ``None`` — see the ``if row is None`` branch in ``_scan_projects``.
    """
    # fallback: read id from .meta.json (no entity_display row exists yet).
    proj_id_from_meta = meta.get("id", "")
    if not proj_id_from_meta:
        return None
    slug = meta.get("slug", "")
    composite = f"{proj_id_from_meta}-{slug}" if slug else proj_id_from_meta
    existing = _in_workspace(db, f"project:{composite}", workspace_uuid)
    if existing is None:
        return None
    return db.get_entity_display(existing.get("uuid"))


def _read_entity_display_for_feature(
    db: EntityDatabase, meta: dict, workspace_uuid: str
) -> dict | None:
    """Look up the ``entity_display`` row for a feature whose ``.meta.json``
    has been read off disk (feature 110 FR-8.3c port).

    The feature's composite entity_id is ``f"{meta.id}-{meta.slug}"``. We
    use that to locate the entity row; if absent (first-pass backfill), or
    if entity_display has no row, returns ``None`` so the caller falls back
    to ``meta.get("id", "")`` / ``meta.get("slug", "")`` reads.
    """
    # fallback: read id/slug from .meta.json (no entity_display row yet).
    feat_id = meta.get("id", "")
    slug = meta.get("slug", "")
    if not feat_id:
        return None
    composite = f"{feat_id}-{slug}" if slug else feat_id
    existing = _in_workspace(db, f"feature:{composite}", workspace_uuid)
    if existing is None:
        return None
    return db.get_entity_display(existing.get("uuid"))


def _scan_projects(db: EntityDatabase, artifacts_root: str, project_id: str = "__unknown__") -> None:
    """Glob project .meta.json files and register each as a project entity."""
    proj_dir = os.path.join(artifacts_root, "projects")
    if not os.path.isdir(proj_dir):
        return

    meta_files = sorted(glob.glob(os.path.join(proj_dir, "*", ".meta.json")))
    workspace_uuid = _workspace(db, project_id)
    by_display = _registered_by_display(db, "project", workspace_uuid)
    for path in meta_files:
        meta = _read_json(path)
        if meta is None:
            continue

        # F4-AUDIT: read seq from entity_display when an entity row already
        # exists (FR-8.3c). Backfill is typically a first-pass populator,
        # but for re-runs (idempotent backfill) the entity_display table is
        # already populated and is the canonical source of seq/slug. The
        # ``meta.get("id", "")`` read remains as a defense-in-depth
        # fallback for first-pass invocations.
        row = _read_entity_display_for_project(db, meta, workspace_uuid)
        if row is None:
            proj_entity_id = f"{meta.get('id', '')}-{meta.get('slug', '')}"
            identity = registration_identity("project", proj_entity_id)
            if identity is None:
                _log_skipped("project", proj_entity_id)
                continue
        else:
            identity = {"seq": row["seq"], "slug": row["slug"]}
            proj_entity_id = render_display_id("project", row["seq"], row["slug"])
        name = meta.get("name", proj_entity_id)

        # F12 audit: idempotent backfill → upsert_entity
        type_id = by_display.get((identity["seq"], identity["slug"]))
        if type_id is None or type_id == f"project:{proj_entity_id}":
            type_id = db.upsert_entity(
                entity_type="project",
                **identity,
                name=name,
                artifact_path=os.path.dirname(path),
                project_id=project_id,
            )

        parent_type_id = _derive_parent("project", meta, None, artifacts_root=artifacts_root)
        if parent_type_id:
            _safe_set_parent(db, type_id, parent_type_id, workspace_uuid)


def _scan_features(db: EntityDatabase, artifacts_root: str, project_id: str = "__unknown__") -> None:
    """Glob feature .meta.json files and register each as a feature entity."""
    feat_dir = os.path.join(artifacts_root, "features")
    if not os.path.isdir(feat_dir):
        return

    meta_files = sorted(glob.glob(os.path.join(feat_dir, "*", ".meta.json")))
    workspace_uuid = _workspace(db, project_id)
    by_display = _registered_by_display(db, "feature", workspace_uuid)
    for path in meta_files:
        meta = _read_json(path)
        if meta is None:
            continue

        # F4-AUDIT: prefer entity_display as source-of-truth for seq + slug
        # (FR-8.3c). For re-run backfill the entity already exists in DB and
        # entity_display is canonical. First-pass backfill (entity not yet
        # in DB) falls back to the ``.meta.json`` reads below.
        row = _read_entity_display_for_feature(db, meta, workspace_uuid)
        if row is None:
            feat_id = meta.get("id", "")
            slug = meta.get("slug", "")
            entity_id = f"{feat_id}-{slug}" if slug else feat_id
            identity = registration_identity("feature", entity_id)
            if identity is None:
                _log_skipped("feature", entity_id)
                continue
        else:
            slug = row["slug"]
            identity = {"seq": row["seq"], "slug": slug}
            entity_id = render_display_id("feature", row["seq"], slug)
        name = meta.get("name", "")
        if not name:
            name = _humanize_slug(slug or entity_id)

        # Build entity metadata from optional fields
        entity_meta: dict | None = None
        if "depends_on_features" in meta:
            entity_meta = {"depends_on_features": meta["depends_on_features"]}

        # F12 audit: idempotent backfill → upsert_entity
        type_id = by_display.get((identity["seq"], identity["slug"]))
        if type_id is None or type_id == f"feature:{entity_id}":
            type_id = db.upsert_entity(
                entity_type="feature",
                **identity,
                name=name,
                artifact_path=os.path.dirname(path),
                metadata=entity_meta,
                project_id=project_id,
            )

        # Update name if existing entity has a slug-style name (no spaces)
        existing = _in_workspace(db, type_id, workspace_uuid)
        if existing and " " not in existing["name"]:
            db.update_entity(type_id=type_id, name=name, workspace_uuid=workspace_uuid)

        # Derive and set parent
        parent_type_id = _derive_parent("feature", meta, None, artifacts_root=artifacts_root)
        if parent_type_id:
            # Ensure parent exists in this workspace (register synthetic if needed)
            if _in_workspace(db, parent_type_id, workspace_uuid) is None:
                _register_synthetic_for_missing_parent(
                    db, parent_type_id, meta, project_id=project_id,
                    artifacts_root=artifacts_root,
                )
            _safe_set_parent(db, type_id, parent_type_id, workspace_uuid)

        # Handle backlog_source for direct backlog link (if no other parent set)
        if not parent_type_id and meta.get("backlog_source"):
            bl_id = meta["backlog_source"]
            bl_type_id = f"backlog:{bl_id}"
            if _in_workspace(db, bl_type_id, workspace_uuid) is None:
                _register_synthetic(
                    db, "backlog", bl_id,
                    f"Backlog #{bl_id} (orphaned)", "orphaned",
                    project_id=project_id,
                )
            _safe_set_parent(db, type_id, bl_type_id, workspace_uuid)


# ---------------------------------------------------------------------------
# Parent derivation
# ---------------------------------------------------------------------------


def _derive_parent(
    entity_type: str, meta: dict, brainstorm_content: str | None,
    *, artifacts_root: str | None = None,
) -> str | None:
    """Derive the parent type_id for an entity.

    Parameters
    ----------
    entity_type:
        One of: backlog, brainstorm, project, feature.
    meta:
        Parsed .meta.json dict (or empty dict for brainstorms).
    brainstorm_content:
        File content of the brainstorm .md file (for brainstorm entities).
    artifacts_root:
        The repository's artifacts directory; an absolute ``brainstorm_source``
        under it is in-repo, not external.

    Returns
    -------
    str | None
        The parent type_id string, or None if no parent can be derived.
    """
    if entity_type == "backlog":
        return None

    if entity_type == "brainstorm":
        if brainstorm_content:
            match = re.search(BACKLOG_MARKER_PATTERN_1, brainstorm_content)
            if match:
                return f"backlog:{match.group(1)}"
            match = re.search(BACKLOG_MARKER_PATTERN_2, brainstorm_content)
            if match:
                return f"backlog:{match.group(1)}"
        return None

    if entity_type == "project":
        return _brainstorm_parent(meta.get("brainstorm_source"), artifacts_root)

    if entity_type == "feature":
        # Priority 1: project_id
        project_id = meta.get("project_id")
        if project_id:
            return f"project:{project_id}"

        # Priority 2: brainstorm_source
        parent = _brainstorm_parent(meta.get("brainstorm_source"), artifacts_root)
        if parent:
            return parent

        # Priority 3: backlog_source (handled separately in _scan_features)
        return None

    return None


# ---------------------------------------------------------------------------
# Synthetic entity helpers
# ---------------------------------------------------------------------------


def _register_synthetic(
    db: EntityDatabase,
    entity_type: str,
    entity_id: str,
    name: str,
    status: str,
    project_id: str = "__unknown__",
) -> str | None:
    """Register a synthetic entity (orphaned/external).

    Returns the constructed type_id, or None when ``entity_id`` has no
    seq/slug form and is skipped.
    """
    identity = registration_identity(entity_type, entity_id)
    if identity is None:
        _log_skipped(entity_type, entity_id)
        return None
    # F12 audit: conflict-is-error → register_entity, EntityExistsError handled.
    # Only when absent: the caller's get_entity(type_id) sees nothing when the
    # id exists in two workspaces, and an upsert would then rewrite this
    # workspace's real row (its status became 'orphaned').
    try:
        db.register_entity(
            entity_type=entity_type,
            **identity,
            name=name,
            status=status,
            project_id=project_id,
        )
    except EntityExistsError:
        pass
    return f"{entity_type}:{entity_id}"


def _register_synthetic_for_missing_parent(
    db: EntityDatabase,
    parent_type_id: str,
    meta: dict,
    project_id: str = "__unknown__",
    artifacts_root: str | None = None,
) -> None:
    """Register a synthetic entity for a missing parent reference.

    Handles two cases:
    - Brainstorm parent with external path -> status="external"
    - Backlog parent not found -> status="orphaned"
    """
    parts = parent_type_id.split(":", 1)
    if len(parts) != 2:
        return
    p_type, p_id = parts

    if p_type == "brainstorm":
        bs_source = meta.get("brainstorm_source", "")
        if _is_external_path(bs_source, artifacts_root):
            _register_synthetic(
                db, "brainstorm", p_id,
                f"External: {bs_source}", "external",
                project_id=project_id,
            )
        else:
            _register_synthetic(
                db, "brainstorm", p_id,
                f"Brainstorm {p_id} (orphaned)", "orphaned",
                project_id=project_id,
            )
    elif p_type == "backlog":
        _register_synthetic(
            db, "backlog", p_id,
            f"Backlog #{p_id} (orphaned)", "orphaned",
            project_id=project_id,
        )
    elif p_type == "project":
        _register_synthetic(
            db, "project", p_id,
            f"Project {p_id} (orphaned)", "orphaned",
            project_id=project_id,
        )


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _humanize_slug(slug: str) -> str:
    """Strip date prefix and convert slug to human-readable title.

    '20260205-002937-rca-agent' -> 'Rca Agent'
    '20260205-agent' -> 'Agent'
    'vast-mixing' -> 'Vast Mixing'
    '20260227' -> '20260227' (preserved if only a date)
    """
    import re

    name = re.sub(r"^\d{8}(-\d{6})?-", "", slug)
    if not name:  # slug was only a date
        return slug
    return name.replace("-", " ").title()


def _extract_prd_title(content: str | None, stem: str) -> str:
    """Extract human-readable title from PRD content, falling back to slug.

    Tries: '# PRD: <title>' heading, then first '# <title>' heading,
    then humanizes the slug.
    """
    import re

    if content:
        # Try '# PRD: <title>' (use [^\S\n]* to avoid matching across newlines)
        m = re.search(r"^#\s+PRD:[^\S\n]*(.+)", content, re.MULTILINE)
        if m and m.group(1).strip():
            return m.group(1).strip()
        # Try first '# <title>'
        m = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return _humanize_slug(stem)


def _register_brainstorm(db: EntityDatabase, path: str, stem: str, project_id: str = "__unknown__") -> None:
    """Read a brainstorm file, register it, and set its parent if derivable."""
    content = _read_file(path)
    title = _extract_prd_title(content, stem)
    parent_type_id = _derive_parent("brainstorm", {}, content)

    # F12 audit: idempotent backfill → upsert_entity
    db.upsert_entity(
        entity_type="brainstorm",
        display_id=stem,
        name=title,
        artifact_path=path,
        project_id=project_id,
    )
    db.update_entity(type_id=f"brainstorm:{stem}", name=title, project_id=project_id)
    if parent_type_id:
        _safe_set_parent(db, f"brainstorm:{stem}", parent_type_id, _workspace(db, project_id))


def _brainstorm_parent(bs_source: str | None, artifacts_root: str | None = None) -> str | None:
    """The brainstorm type_id a ``brainstorm_source`` names, or None.

    Newer ``.meta.json`` files write the type_id itself
    (``brainstorm:20260710-…``), used as-is. A path inside the repository —
    relative, or absolute under ``artifacts_root`` — names a brainstorm only
    if it is in a ``brainstorms`` directory; any other file (a project's
    ``prd.md``) is not one, and inventing a brainstorm for it mints a phantom
    entity. External paths keep their placeholder.
    """
    if not bs_source:
        return None
    if bs_source.startswith("brainstorm:"):
        return bs_source
    if not _is_external_path(bs_source, artifacts_root) and \
            os.path.basename(os.path.dirname(bs_source)) != "brainstorms":
        return None
    return f"brainstorm:{_brainstorm_stem(bs_source)}"


def _brainstorm_stem(path: str) -> str:
    """Extract the stem from a brainstorm file path.

    '...some/path/20260227-lineage.prd.md' -> '20260227-lineage'
    '...some/path/20260130-slug.md' -> '20260130-slug'
    """
    basename = os.path.basename(path)
    if basename.endswith(".prd.md"):
        return basename[: -len(".prd.md")]
    if basename.endswith(".md"):
        return basename[: -len(".md")]
    return basename


def _is_external_path(path: str, artifacts_root: str | None = None) -> bool:
    """Whether a path points outside the repository: home-relative, or
    absolute and not under ``artifacts_root``. Some ``.meta.json`` files name
    an in-repo file by its absolute path; without ``artifacts_root`` every
    absolute path counts as external.
    """
    if not path:
        return False
    if path.startswith("~"):
        return True
    if not os.path.isabs(path):
        return False
    if artifacts_root is None:
        return True
    root = os.path.realpath(artifacts_root)
    return os.path.commonpath([os.path.realpath(path), root]) != root


def _read_file(path: str) -> str | None:
    """Read a file, returning None if it doesn't exist."""
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def _read_json(path: str) -> dict | None:
    """Read and parse a JSON file, returning None on failure."""
    content = _read_file(path)
    if content is None:
        return None
    try:
        return json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return None


def _workspace(db: EntityDatabase, project_id: str) -> str:
    """The workspace being backfilled. Raises ValueError for an unknown one."""
    return db._resolve_optional_workspace_filter(None, project_id, _caller="backfill")


def _in_workspace(db: EntityDatabase, type_id: str, workspace_uuid: str) -> dict | None:
    """This workspace's entity ``type_id``, or None.

    Backfill reads one repository, so an entity another workspace registered
    under the same type_id is not its parent. The unscoped ``get_entity`` finds
    such a row when it is the only one, and returns None when a type_id is in
    two workspaces; both lose the right answer.
    """
    try:
        entity_uuid, _ = db._resolve_identifier(type_id, workspace_uuid=workspace_uuid)
    except ValueError:
        return None
    return db.get_entity_by_uuid(entity_uuid)


def _registered_by_display(db: EntityDatabase, kind: str, workspace_uuid: str) -> dict:
    """(seq, slug) -> type_id for this workspace's registered ``kind`` entities.

    A registry older than zero-padding holds ``feature:66-x`` where
    ``.meta.json`` says ``066``; a type_id lookup misses that row and
    would register the feature a second time.
    """
    found: dict = {}
    for entity in db.list_entities(entity_type=kind, workspace_uuid=workspace_uuid):
        display = db.get_entity_display(entity["uuid"])
        if display is not None:
            found.setdefault((display["seq"], display["slug"]), entity["type_id"])
    return found


def _log_skipped(kind: str, text_id: str) -> None:
    """An id with no seq/slug form (``00019``, ``P001``) is skipped, never guessed at."""
    print(f"entity-server: backfill: skipping {kind} {text_id!r}: no seq/slug form",
          file=sys.stderr)


def _safe_set_parent(
    db: EntityDatabase, type_id: str, parent_type_id: str, workspace_uuid: str
) -> None:
    """Fill a missing parent, logging a warning if the operation fails.

    A parent already set is left alone: backfill derives parents from files
    on disk, which are older than what the registry has since recorded. Both
    ends are looked up in this workspace only.
    """
    child = _in_workspace(db, type_id, workspace_uuid)
    if child is None or child["parent_uuid"] is not None:
        return
    if _in_workspace(db, parent_type_id, workspace_uuid) is not None:
        try:
            db.set_parent(type_id, parent_type_id, workspace_uuid=workspace_uuid)
        except ValueError as exc:
            print(
                f"entity-server: backfill: set_parent {type_id}->{parent_type_id} "
                f"skipped: {exc}",
                file=sys.stderr,
            )
