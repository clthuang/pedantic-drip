"""Entity status sync: reads .meta.json files, compares with entity registry, updates on drift."""
import json
import os
import re

# Feature/project valid statuses
STATUS_MAP = {"active", "completed", "abandoned", "planned", "promoted"}

# Brainstorm statuses that should not be re-archived
TERMINAL_STATUSES = {"promoted", "abandoned", "archived"}

# Backlog row parsing constants
BACKLOG_ROW_RE = re.compile(r'^\|\s*(\d{5})\s*\|[^|]*\|(.+)\|')
CLOSED_RE = re.compile(r'\((?:closed|already implemented)[:\s\u2014]')
PROMOTED_RE = re.compile(r'\(promoted\s*(?:\u2192|->)')
FIXED_RE = re.compile(r'\(fixed:')
JUNK_ID_RE = re.compile(r'^[0-9]{5}$')
NAME_STRIP_RE = re.compile(r'\s*\((?:closed|promoted|fixed|already implemented)[^)]*\)\s*')


def _sync_meta_json_entities(db, full_artifacts_path, subdir, entity_type, project_id):
    """Scan .meta.json files for a single entity type and sync status to entity registry.

    Args:
        db: EntityDatabase instance
        full_artifacts_path: absolute path to the artifacts root (e.g., /project/docs)
        subdir: subdirectory name to scan (e.g., "features", "projects")
        entity_type: entity type string (e.g., "feature", "project")
        project_id: project identifier

    Returns:
        {"updated": int, "skipped": int, "archived": int, "warnings": list[str]}
    """
    results = {"updated": 0, "skipped": 0, "archived": 0, "warnings": []}

    scan_dir = os.path.join(full_artifacts_path, subdir)
    if not os.path.isdir(scan_dir):
        return results

    for folder in os.listdir(scan_dir):
        meta_path = os.path.join(scan_dir, folder, ".meta.json")
        type_id = f"{entity_type}:{folder}"

        if not os.path.isfile(meta_path):
            # .meta.json deleted — archive entity if it exists
            try:
                db.update_entity(type_id, status="archived", project_id=project_id)
                results["archived"] += 1
            except ValueError:
                pass  # entity not in registry, skip
            continue

        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            results["warnings"].append(f"Failed to read {meta_path}: {e}")
            continue

        meta_status = meta.get("status")

        if meta_status not in STATUS_MAP:
            results["warnings"].append(f"Unknown status '{meta_status}' for {type_id}")
            continue

        entity = db.get_entity(type_id)  # returns None if not found
        if entity is None:
            results["skipped"] += 1  # entity not in registry
            continue

        if entity["status"] != meta_status:
            db.update_entity(type_id, status=meta_status, project_id=project_id)
            results["updated"] += 1
        else:
            results["skipped"] += 1

    return results


def sync_entity_statuses(db, full_artifacts_path, project_id="__unknown__",
                         artifacts_root="docs", project_root=""):
    """Scan all entity types and sync statuses to entity registry.

    Args:
        db: EntityDatabase instance
        full_artifacts_path: absolute path to the artifacts root (e.g., /project/docs)
        project_id: project identifier
        artifacts_root: relative artifacts sub-path for stored artifact_path (e.g., "docs")
        project_root: absolute path to project root. If empty, derived from
                      full_artifacts_path by stripping artifacts_root suffix.

    Returns:
        {"updated": int, "skipped": int, "archived": int,
         "registered": int, "deleted": int, "warnings": list[str]}
    """
    if not project_root:
        project_root = full_artifacts_path.removesuffix(artifacts_root).rstrip(os.sep)
        if not project_root:
            raise ValueError(
                f"Cannot derive project_root from full_artifacts_path={full_artifacts_path!r} "
                f"and artifacts_root={artifacts_root!r}"
            )

    results = {
        "updated": 0, "skipped": 0, "archived": 0,
        "registered": 0, "deleted": 0, "warnings": [],
    }

    helpers = [
        ("features", lambda: _sync_meta_json_entities(db, full_artifacts_path, "features", "feature", project_id)),
        ("projects", lambda: _sync_meta_json_entities(db, full_artifacts_path, "projects", "project", project_id)),
        ("brainstorms", lambda: _sync_brainstorm_entities(db, full_artifacts_path, artifacts_root, project_root, project_id)),
        ("backlogs", lambda: _sync_backlog_entities(db, full_artifacts_path, artifacts_root, project_id)),
    ]

    for name, helper in helpers:
        try:
            hr = helper()
        except Exception as exc:
            results["warnings"].append(f"{name}: {exc}")
            continue
        for key in ("updated", "skipped", "archived", "registered", "deleted"):
            results[key] += hr.get(key, 0)
        results["warnings"].extend(hr.get("warnings", []))

    return results


def _sync_brainstorm_entities(
    db, full_artifacts_path, artifacts_root, project_root, project_id
):
    """Scan brainstorms/ for .prd.md files; register new ones; archive missing ones.

    Part 1: Register unregistered .prd.md files as brainstorm entities.
    Part 2: Archive non-terminal brainstorm entities whose artifact file no longer exists (AC-9).

    Returns:
        {"registered": int, "archived": int, "skipped": int}
    """
    results = {"registered": 0, "archived": 0, "skipped": 0}
    brainstorms_dir = os.path.join(full_artifacts_path, "brainstorms")

    if not os.path.isdir(brainstorms_dir):
        return results

    # Part 1: scan filesystem for .prd.md files, register new entities
    seen_on_disk = set()  # entity_ids with files present on disk
    for filename in os.listdir(brainstorms_dir):
        if filename == ".gitkeep" or not filename.endswith(".prd.md"):
            continue

        stem = filename[: -len(".prd.md")]
        seen_on_disk.add(stem)
        type_id = f"brainstorm:{stem}"

        existing = db.get_entity(type_id)
        if existing is not None:
            results["skipped"] += 1
            continue

        artifact_path = os.path.join(artifacts_root, "brainstorms", filename)
        db.register_entity(
            entity_type="brainstorm",
            entity_id=stem,
            name=stem,
            artifact_path=artifact_path,
            status="active",
            project_id=project_id,
        )
        results["registered"] += 1

    # Part 2: archive non-terminal brainstorm entities whose file is missing (AC-9)
    entities = db.list_entities(entity_type="brainstorm", project_id=project_id)
    for entity in entities:
        if entity["entity_id"] in seen_on_disk:
            continue
        if entity.get("status", "") in TERMINAL_STATUSES:
            continue
        if not entity.get("artifact_path"):
            continue
        try:
            db.update_entity(entity["type_id"], status="archived", project_id=project_id)
            results["archived"] += 1
        except ValueError:
            pass  # entity disappeared between list and update, skip

    return results


def _cleanup_junk_backlogs(db, entities):
    """Delete backlog entities whose entity_id is not a valid 5-digit ID.

    Returns:
        (deleted_count, warnings_list)
    """
    deleted = 0
    warnings = []
    for entity in entities:
        entity_id = entity["type_id"].split(":", 1)[1]
        if not JUNK_ID_RE.match(entity_id):
            try:
                db.delete_entity(entity["type_id"])
                deleted += 1
            except ValueError as e:
                warnings.append(f"Cannot delete backlog:{entity_id}: {e}")
    return deleted, warnings


def _dedup_backlogs(db, entities):
    """Remove duplicate backlog entities sharing the same (entity_id, project_id).

    For duplicates, keeps the entity with a non-null status and deletes the other.

    Returns:
        Count of entities deleted.
    """
    groups = {}
    for entity in entities:
        entity_id = entity["type_id"].split(":", 1)[1]
        groups.setdefault(entity_id, []).append(entity)

    deleted = 0
    for entity_id, group in groups.items():
        if len(group) <= 1:
            continue
        # Sort: entities with non-null status first (keep those)
        group.sort(key=lambda e: (e.get("status") is None, e["uuid"]))
        # Keep first, delete rest
        for dup in group[1:]:
            try:
                db.delete_entity(dup["uuid"])
                deleted += 1
            except ValueError:
                pass
    return deleted


def _sync_backlog_entities(db, full_artifacts_path, artifacts_root, project_id):
    """Parse backlog.md and sync backlog entities to the entity registry.

    Execution order: (1) cleanup junk IDs, (2) dedup, (3) parse and sync.

    Args:
        db: EntityDatabase instance
        full_artifacts_path: absolute path to the artifacts root directory
        artifacts_root: relative artifacts root (e.g., "docs")
        project_id: project identifier

    Returns:
        {"updated": int, "skipped": int, "registered": int, "deleted": int, "warnings": list[str]}
    """
    results = {"updated": 0, "skipped": 0, "registered": 0, "deleted": 0, "warnings": []}

    all_backlogs = db.list_entities(entity_type="backlog", project_id=project_id)

    junk_deleted, junk_warnings = _cleanup_junk_backlogs(db, all_backlogs)
    results["deleted"] += junk_deleted
    results["warnings"].extend(junk_warnings)

    # Re-fetch after junk cleanup since entities were deleted
    remaining = db.list_entities(entity_type="backlog", project_id=project_id)

    dedup_deleted = _dedup_backlogs(db, remaining)
    results["deleted"] += dedup_deleted

    backlog_path = os.path.join(full_artifacts_path, "backlog.md")
    if not os.path.isfile(backlog_path):
        return results

    # Pre-fetch existing backlogs for O(1) lookup during parse
    existing_map = {
        e["type_id"]: e
        for e in db.list_entities(entity_type="backlog", project_id=project_id)
    }

    with open(backlog_path) as f:
        lines = f.readlines()

    for line in lines:
        m = BACKLOG_ROW_RE.match(line)
        if not m:
            continue

        entity_id = m.group(1)
        description = m.group(2).strip()

        if CLOSED_RE.search(description):
            status = "dropped"
        elif PROMOTED_RE.search(description):
            status = "promoted"
        elif FIXED_RE.search(description):
            status = "dropped"
        else:
            status = "open"

        name = NAME_STRIP_RE.sub("", description).strip()[:200]

        type_id = f"backlog:{entity_id}"
        existing = existing_map.get(type_id)

        if existing is None:
            db.register_entity(
                entity_type="backlog",
                entity_id=entity_id,
                name=name,
                artifact_path=os.path.join(artifacts_root, "backlog.md"),
                status=status,
                project_id=project_id,
            )
            results["registered"] += 1
        elif existing["status"] != status:
            db.update_entity(type_id, status=status, project_id=project_id)
            results["updated"] += 1
        else:
            results["skipped"] += 1

    return results
