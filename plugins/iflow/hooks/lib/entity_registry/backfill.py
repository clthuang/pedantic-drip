"""Backfill scanner for migrating existing iflow artifacts into the entity registry.

Scans features, projects, brainstorms, and backlog items from the artifact
directory and registers them in the EntityDatabase with correct parent-child
relationships.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

from entity_registry.database import EntityDatabase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENTITY_SCAN_ORDER = ["backlog", "brainstorm", "project", "feature"]

# Regex patterns for backlog marker extraction from brainstorm PRDs
BACKLOG_MARKER_PATTERN_1 = r"\*Source:\s*Backlog\s*#(\d{5})\*"
BACKLOG_MARKER_PATTERN_2 = r"\*\*Backlog Item:\*\*\s*(\d{5})"


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
    if db.get_metadata("backfill_complete") == "1":
        return

    scanners = {
        "backlog": _scan_backlog,
        "brainstorm": _scan_brainstorms,
        "project": _scan_projects,
        "feature": _scan_features,
    }

    for entity_type in ENTITY_SCAN_ORDER:
        scanners[entity_type](db, artifacts_root)

    # Mark backfill as complete
    db.set_metadata("backfill_complete", "1")


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
        db.register_entity(
            entity_type="backlog",
            entity_id=item_id,
            name=description,
            artifact_path=backlog_path,
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
        name = meta.get("name", entity_id)

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


def _register_brainstorm(db: EntityDatabase, path: str, stem: str) -> None:
    """Read a brainstorm file, register it, and set its parent if derivable."""
    content = _read_file(path)
    parent_type_id = _derive_parent("brainstorm", {}, content)

    db.register_entity(
        entity_type="brainstorm",
        entity_id=stem,
        name=stem,
        artifact_path=path,
    )
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
