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

from entity_registry.database import EntityDatabase
from workflow_engine.kanban import derive_kanban

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENTITY_SCAN_ORDER = ["backlog", "brainstorm", "project", "feature"]

# Regex patterns for backlog marker extraction from brainstorm PRDs
BACKLOG_MARKER_PATTERN_1 = r"\*Source:\s*Backlog\s*#(\d{5})\*"
BACKLOG_MARKER_PATTERN_2 = r"\*\*Backlog Item:\*\*\s*(\d{5})"

PHASE_SEQUENCE: tuple[str, ...] = (
    "brainstorm", "specify", "design", "create-plan",
    "create-tasks", "implement", "finish",
)

# Valid statuses for kanban derivation (used for validation only)
_VALID_STATUSES: frozenset[str] = frozenset({"planned", "active", "completed", "abandoned"})

VALID_MODES: frozenset[str] = frozenset({"standard", "full", "light"})


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
    db: EntityDatabase, artifacts_root: str, header_aware: bool = False
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
    _BACKFILL_VERSION = "2"  # v2: entity name enrichment (title extraction)

    current_version = db.get_metadata("backfill_version") or "0"
    if db.get_metadata("backfill_complete") == "1" and current_version >= _BACKFILL_VERSION:
        return

    scanners = {
        "backlog": _scan_backlog,
        "brainstorm": _scan_brainstorms,
        "project": _scan_projects,
        "feature": _scan_features,
    }

    for entity_type in ENTITY_SCAN_ORDER:
        scanners[entity_type](db, artifacts_root)

    # Fix orphaned NULL workflow_phase values (e.g. abandoned entities)
    db._conn.execute(
        "UPDATE workflow_phases SET workflow_phase = 'finish' "
        "WHERE workflow_phase IS NULL"
    )
    db._conn.commit()

    # Mark backfill as complete with current version
    db.set_metadata("backfill_complete", "1")
    db.set_metadata("backfill_version", _BACKFILL_VERSION)


def backfill_workflow_phases(
    db: EntityDatabase,
    artifacts_root: str,
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

    for entity in entities:
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
                # Child-completion override
                children = [
                    e for e in all_entities
                    if e.get("parent_type_id") == type_id
                    and e["entity_type"] == "feature"
                ]
                all_children_completed = children and all(
                    c.get("status") == "completed" for c in children
                )

                # Check existing workflow_phases row
                existing_row = db._conn.execute(
                    "SELECT workflow_phase FROM workflow_phases WHERE type_id = ?",
                    (type_id,),
                ).fetchone()

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
                    db._conn.execute(
                        "UPDATE workflow_phases SET workflow_phase = ?, kanban_column = ?, "
                        "updated_at = ? WHERE type_id = ?",
                        (workflow_phase, kanban_column, db._now_iso(), type_id),
                    )
                    updated += 1
                    continue

                # Case 1: no row -> INSERT
                cursor = db._conn.execute(
                    "INSERT OR IGNORE INTO workflow_phases "
                    "(type_id, kanban_column, workflow_phase, "
                    "last_completed_phase, mode, "
                    "backward_transition_reason, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (type_id, kanban_column, workflow_phase, None, None, None, db._now_iso()),
                )
                if cursor.rowcount > 0:
                    created += 1
                else:
                    skipped += 1  # concurrent insert won the race
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

            kanban_column = derive_kanban(status, workflow_phase)

            # INSERT OR IGNORE for idempotency (TD-10: bypasses CRUD)
            insert_sql = (
                "INSERT OR IGNORE INTO workflow_phases "
                "(type_id, kanban_column, workflow_phase, "
                "last_completed_phase, mode, "
                "backward_transition_reason, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)"
            )
            params = (
                type_id, kanban_column, workflow_phase,
                last_completed_phase, mode, None, db._now_iso(),
            )
            cursor = db._conn.execute(insert_sql, params)

            if cursor.rowcount > 0:
                created += 1
            else:
                skipped += 1

        except Exception as exc:
            errors.append(f"Error processing {entity.get('type_id', '?')}: {exc}")

    # Commit once at end (TD-10: direct connection access for bulk insert)
    db._conn.commit()

    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Scanner functions
# ---------------------------------------------------------------------------


def _scan_backlog(db: EntityDatabase, artifacts_root: str) -> None:
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

        description = cells[2]
        if len(description) <= 80:
            title = description
        else:
            truncated = description[:80].rsplit(" ", 1)[0]
            title = (truncated if truncated != description[:80] else description[:80]) + "\u2026"

        db.register_entity(
            entity_type="backlog",
            entity_id=item_id,
            name=title,
            artifact_path=backlog_path,
            metadata={"description": description},
        )
        db.update_entity(
            type_id=f"backlog:{item_id}",
            name=title,
            metadata={"description": description},
        )


def _scan_brainstorms(db: EntityDatabase, artifacts_root: str) -> None:
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
        _register_brainstorm(db, path, stem)
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

        _register_brainstorm(db, path, stem)
        registered_stems.add(stem)


def _scan_projects(db: EntityDatabase, artifacts_root: str) -> None:
    """Glob project .meta.json files and register each as a project entity."""
    proj_dir = os.path.join(artifacts_root, "projects")
    if not os.path.isdir(proj_dir):
        return

    meta_files = sorted(glob.glob(os.path.join(proj_dir, "*", ".meta.json")))
    for path in meta_files:
        meta = _read_json(path)
        if meta is None:
            continue

        project_id = meta.get("id", "")
        name = meta.get("name", project_id)

        db.register_entity(
            entity_type="project",
            entity_id=project_id,
            name=name,
            artifact_path=os.path.dirname(path),
        )

        parent_type_id = _derive_parent("project", meta, None)
        if parent_type_id:
            _safe_set_parent(db, f"project:{project_id}", parent_type_id)


def _scan_features(db: EntityDatabase, artifacts_root: str) -> None:
    """Glob feature .meta.json files and register each as a feature entity."""
    feat_dir = os.path.join(artifacts_root, "features")
    if not os.path.isdir(feat_dir):
        return

    meta_files = sorted(glob.glob(os.path.join(feat_dir, "*", ".meta.json")))
    for path in meta_files:
        meta = _read_json(path)
        if meta is None:
            continue

        feat_id = meta.get("id", "")
        slug = meta.get("slug", "")
        entity_id = f"{feat_id}-{slug}" if slug else feat_id
        name = meta.get("name", "")
        if not name:
            name = _humanize_slug(slug or entity_id)

        # Build entity metadata from optional fields
        entity_meta: dict | None = None
        if "depends_on_features" in meta:
            entity_meta = {"depends_on_features": meta["depends_on_features"]}

        type_id = db.register_entity(
            entity_type="feature",
            entity_id=entity_id,
            name=name,
            artifact_path=os.path.dirname(path),
            metadata=entity_meta,
        )

        # Update name if existing entity has a slug-style name (no spaces)
        existing = db.get_entity(f"feature:{entity_id}")
        if existing and " " not in existing["name"]:
            db.update_entity(type_id=f"feature:{entity_id}", name=name)

        # Derive and set parent
        parent_type_id = _derive_parent("feature", meta, None)
        if parent_type_id:
            # Ensure parent exists (register synthetic if needed)
            if db.get_entity(parent_type_id) is None:
                _register_synthetic_for_missing_parent(
                    db, parent_type_id, meta
                )
            if db.get_entity(parent_type_id) is not None:
                db.set_parent(type_id, parent_type_id)

        # Handle backlog_source for direct backlog link (if no other parent set)
        if not parent_type_id and meta.get("backlog_source"):
            bl_id = meta["backlog_source"]
            bl_type_id = f"backlog:{bl_id}"
            if db.get_entity(bl_type_id) is None:
                _register_synthetic(
                    db, "backlog", bl_id,
                    f"Backlog #{bl_id} (orphaned)", "orphaned",
                )
            db.set_parent(type_id, bl_type_id)


# ---------------------------------------------------------------------------
# Parent derivation
# ---------------------------------------------------------------------------


def _derive_parent(
    entity_type: str, meta: dict, brainstorm_content: str | None
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
        bs_source = meta.get("brainstorm_source")
        if bs_source:
            stem = _brainstorm_stem(bs_source)
            return f"brainstorm:{stem}"
        return None

    if entity_type == "feature":
        # Priority 1: project_id
        project_id = meta.get("project_id")
        if project_id:
            return f"project:{project_id}"

        # Priority 2: brainstorm_source
        bs_source = meta.get("brainstorm_source")
        if bs_source:
            stem = _brainstorm_stem(bs_source)
            return f"brainstorm:{stem}"

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
) -> str:
    """Register a synthetic entity (orphaned/external).

    Returns the constructed type_id.
    """
    return db.register_entity(
        entity_type=entity_type,
        entity_id=entity_id,
        name=name,
        status=status,
    )


def _register_synthetic_for_missing_parent(
    db: EntityDatabase,
    parent_type_id: str,
    meta: dict,
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
        if _is_external_path(bs_source):
            _register_synthetic(
                db, "brainstorm", p_id,
                f"External: {bs_source}", "external",
            )
        else:
            _register_synthetic(
                db, "brainstorm", p_id,
                f"Brainstorm {p_id} (orphaned)", "orphaned",
            )
    elif p_type == "backlog":
        _register_synthetic(
            db, "backlog", p_id,
            f"Backlog #{p_id} (orphaned)", "orphaned",
        )
    elif p_type == "project":
        _register_synthetic(
            db, "project", p_id,
            f"Project {p_id} (orphaned)", "orphaned",
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


def _register_brainstorm(db: EntityDatabase, path: str, stem: str) -> None:
    """Read a brainstorm file, register it, and set its parent if derivable."""
    content = _read_file(path)
    title = _extract_prd_title(content, stem)
    parent_type_id = _derive_parent("brainstorm", {}, content)

    db.register_entity(
        entity_type="brainstorm",
        entity_id=stem,
        name=title,
        artifact_path=path,
    )
    db.update_entity(type_id=f"brainstorm:{stem}", name=title)
    if parent_type_id:
        _safe_set_parent(db, f"brainstorm:{stem}", parent_type_id)


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


def _is_external_path(path: str) -> bool:
    """Check if a path is absolute or home-relative (external)."""
    return bool(path) and (os.path.isabs(path) or path.startswith("~"))


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


def _safe_set_parent(
    db: EntityDatabase, type_id: str, parent_type_id: str
) -> None:
    """Set parent, logging a warning if the operation fails."""
    if db.get_entity(parent_type_id) is not None:
        try:
            db.set_parent(type_id, parent_type_id)
        except ValueError as exc:
            print(
                f"entity-server: backfill: set_parent {type_id}->{parent_type_id} "
                f"skipped: {exc}",
                file=sys.stderr,
            )
