"""Task promotion: promote tasks.md headings to tracked task entities.

Core logic for the promote_task MCP tool. This module is standalone
and testable without MCP infrastructure.

Architecture: MCP thin wrapper calls promote_task() and returns JSON.
"""
from __future__ import annotations

import difflib
import json
import os
import re
from typing import TYPE_CHECKING

from entity_registry.dependencies import DependencyManager
from entity_registry.id_generator import generate_entity_id
from workflow_engine.templates import get_template

if TYPE_CHECKING:
    from entity_registry.database import EntityDatabase


# ---------------------------------------------------------------------------
# Task 3.5: Agent-executable task query
# ---------------------------------------------------------------------------


def query_ready_tasks(db: "EntityDatabase") -> list[dict]:
    """Return task entities that are ready for execution.

    Ready = type=task, status=planned, no blocked_by entries,
    and parent entity currently in 'implement' phase.

    Returns list of dicts with task info + parent context.

    Parameters
    ----------
    db:
        Open EntityDatabase instance.

    Returns
    -------
    list[dict]
        Each dict: {uuid, type_id, name, status, parent_type_id, parent_phase}.
    """
    tasks = db.list_entities(entity_type="task")
    if not tasks:
        return []

    ready: list[dict] = []

    for task in tasks:
        if task.get("status") != "planned":
            continue

        task_uuid = task["uuid"]

        # Check no blockers
        blockers = db._conn.execute(
            "SELECT 1 FROM entity_dependencies WHERE entity_uuid = ? LIMIT 1",
            (task_uuid,),
        ).fetchone()
        if blockers is not None:
            continue

        # Check parent is in implement phase
        parent_type_id = task.get("parent_type_id")
        if not parent_type_id:
            continue

        parent_wp = db.get_workflow_phase(parent_type_id)
        if parent_wp is None:
            continue

        parent_phase = parent_wp.get("workflow_phase")
        if parent_phase != "implement":
            continue

        ready.append({
            "uuid": task_uuid,
            "type_id": task["type_id"],
            "name": task.get("name", ""),
            "status": task["status"],
            "parent_type_id": parent_type_id,
            "parent_phase": parent_phase,
        })

    return ready


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TaskNotFoundError(ValueError):
    """No matching task heading found in tasks.md."""
    pass


class TaskAlreadyPromotedError(ValueError):
    """Task has already been promoted to an entity."""
    pass


# ---------------------------------------------------------------------------
# Heading parser
# ---------------------------------------------------------------------------

# Matches #### Task X.Y: Description  (level-4 markdown heading with Task prefix)
_TASK_HEADING_RE = re.compile(r"^####\s+(Task\s+\S+:?\s*.+?)\s*$")

# Matches **Depends on:** content
_DEPENDS_RE = re.compile(r"\*\*Depends\s+on:\*\*\s*(.+)", re.IGNORECASE)

def _extract_task_refs(deps_text: str) -> list[str]:
    """Extract task reference IDs from a depends-on string.

    Handles formats like:
    - "Task 3.1"
    - "Tasks 3.1, 3.2"
    - "Task 3.1, Task 3.2"
    - "Tasks 1b.3a, 1b.6"

    Returns list of reference IDs like ["3.1", "3.2"].
    """
    # Strip "Task" or "Tasks" prefix, then split on commas
    # Handle multiple "Task X" occurrences and "Tasks X, Y" patterns
    refs: list[str] = []
    # Split on "Task" or "Tasks" boundaries
    parts = re.split(r"Tasks?\s+", deps_text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Part may be "3.1" or "3.1, 3.2" or "3.1, 3.2 (some note)"
        for item in part.split(","):
            item = item.strip().rstrip(")")
            # Take only the ID portion (before any space/parenthesis)
            match = re.match(r"(\S+)", item)
            if match:
                refs.append(match.group(1))
    return refs


def parse_task_headings(tasks_md_path: str) -> list[dict]:
    """Parse tasks.md and extract task headings with dependency info.

    Parameters
    ----------
    tasks_md_path:
        Absolute path to tasks.md file.

    Returns
    -------
    list[dict]
        Each dict has:
        - heading: str — the full heading text (without #### prefix)
        - depends_on: list[str] — full heading text of depended-upon tasks

    Raises
    ------
    FileNotFoundError
        If tasks_md_path does not exist.
    """
    if not os.path.isfile(tasks_md_path):
        raise FileNotFoundError(f"tasks.md not found: {tasks_md_path}")

    with open(tasks_md_path, "r") as f:
        lines = f.readlines()

    tasks: list[dict] = []
    current_task: dict | None = None

    for line in lines:
        heading_match = _TASK_HEADING_RE.match(line)
        if heading_match:
            current_task = {
                "heading": heading_match.group(1).strip(),
                "depends_on": [],
            }
            tasks.append(current_task)
            continue

        if current_task is not None:
            depends_match = _DEPENDS_RE.search(line)
            if depends_match:
                deps_text = depends_match.group(1)
                ref_ids = _extract_task_refs(deps_text)
                for ref_id in ref_ids:
                    # Find matching heading by prefix "Task {ref_id}"
                    for t in tasks:
                        if t["heading"].startswith(f"Task {ref_id}"):
                            current_task["depends_on"].append(t["heading"])
                            break
                    else:
                        # Store raw ref for unresolved deps
                        current_task["depends_on"].append(f"Task {ref_id}")

    return tasks


# ---------------------------------------------------------------------------
# Fuzzy match
# ---------------------------------------------------------------------------


def _fuzzy_match_heading(
    query: str, headings: list[str], *, cutoff: float = 0.4
) -> list[str]:
    """Find task headings that match the query.

    Resolution order:
    1. Exact match (case-insensitive) → single result
    2. Substring match (query appears in heading, case-insensitive) → all matches
    3. difflib fuzzy match → all matches above cutoff

    Returns list of matching heading strings.
    """
    query_lower = query.lower()

    # 1. Exact match
    for h in headings:
        if h.lower() == query_lower:
            return [h]

    # 2. Substring match
    substring_matches = [h for h in headings if query_lower in h.lower()]
    if substring_matches:
        return substring_matches

    # 3. Fuzzy match via difflib
    close = difflib.get_close_matches(
        query_lower, [h.lower() for h in headings], n=5, cutoff=cutoff
    )
    if close:
        # Map back to original-case headings
        lower_to_orig = {h.lower(): h for h in headings}
        return [lower_to_orig[c] for c in close]

    return []


# ---------------------------------------------------------------------------
# Core promote function
# ---------------------------------------------------------------------------


def promote_task(
    db: "EntityDatabase",
    feature_ref: str,
    task_heading: str,
) -> dict:
    """Promote a task from tasks.md to a tracked entity.

    Parameters
    ----------
    db:
        Open EntityDatabase instance.
    feature_ref:
        Feature type_id, UUID, or partial ref to resolve.
    task_heading:
        Full or partial task heading to match against tasks.md.

    Returns
    -------
    dict
        On success: {promoted: True, task_uuid, task_type_id, entity_type, parent_uuid, status, heading, dependencies_created}
        On ambiguous: {promoted: False, candidates: [...]}

    Raises
    ------
    ValueError
        If feature_ref cannot be resolved or feature lacks artifact_path.
    TaskNotFoundError
        If no heading matches the query.
    TaskAlreadyPromotedError
        If the matched task has already been promoted.
    FileNotFoundError
        If tasks.md does not exist at the expected path.
    """
    # 1. Resolve feature
    feature = db.get_entity(feature_ref)
    if feature is None:
        raise ValueError(f"No entity found matching ref: {feature_ref!r}")

    feature_uuid = feature["uuid"]
    feature_type_id = feature["type_id"]

    # 2. Find tasks.md
    artifact_path = feature.get("artifact_path")
    if not artifact_path:
        raise ValueError(
            f"Feature {feature_type_id} has no artifact_path set"
        )
    tasks_md_path = os.path.join(artifact_path, "tasks.md")
    if not os.path.isfile(tasks_md_path):
        raise FileNotFoundError(f"tasks.md not found: {tasks_md_path}")

    # 3. Parse headings
    all_tasks = parse_task_headings(tasks_md_path)
    heading_texts = [t["heading"] for t in all_tasks]

    # 4. Fuzzy match
    matches = _fuzzy_match_heading(task_heading, heading_texts)

    if not matches:
        raise TaskNotFoundError(
            f"No matching task heading found for: {task_heading!r}"
        )

    if len(matches) > 1:
        return {"promoted": False, "candidates": matches}

    matched_heading = matches[0]
    matched_task = next(t for t in all_tasks if t["heading"] == matched_heading)

    # 5. Check already promoted
    # Search for existing task entities under this feature with matching heading in metadata
    existing_tasks = db.list_entities(entity_type="task")
    for et in existing_tasks:
        if et.get("parent_uuid") == feature_uuid:
            meta = et.get("metadata")
            if meta:
                if isinstance(meta, str):
                    meta = json.loads(meta)
                if meta.get("source_heading") == matched_heading:
                    raise TaskAlreadyPromotedError(
                        f"Task already promoted: {matched_heading!r}"
                    )

    # 6. Determine weight/mode from feature's workflow_phase
    wp = db.get_workflow_phase(feature_type_id)
    mode = wp["mode"] if wp and wp.get("mode") else "standard"

    # 7. Generate task entity ID
    task_entity_id = generate_entity_id(db, "task", matched_heading)
    task_type_id = f"task:{task_entity_id}"

    # 8. Register task entity
    task_metadata = {"source_heading": matched_heading}
    task_uuid = db.register_entity(
        entity_type="task",
        entity_id=task_entity_id,
        name=matched_heading,
        status="planned",
        parent_type_id=feature_type_id,
        metadata=task_metadata,
    )

    # 9. Create workflow_phase row for the task
    db.create_workflow_phase(task_type_id, mode=mode)

    # 10. Create dependencies (only for already-promoted sibling tasks)
    dep_mgr = DependencyManager()
    deps_created: list[str] = []

    for dep_heading in matched_task["depends_on"]:
        # Find if this dependency has been promoted
        for et in db.list_entities(entity_type="task"):
            if et.get("parent_uuid") == feature_uuid:
                meta = et.get("metadata")
                if meta:
                    if isinstance(meta, str):
                        meta = json.loads(meta)
                    if meta.get("source_heading") == dep_heading:
                        try:
                            dep_mgr.add_dependency(db, task_uuid, et["uuid"])
                            deps_created.append(dep_heading)
                        except Exception:
                            pass  # Skip if cycle or other issue
                        break

    return {
        "promoted": True,
        "task_uuid": task_uuid,
        "task_type_id": task_type_id,
        "entity_type": "task",
        "parent_uuid": feature_uuid,
        "status": "planned",
        "heading": matched_heading,
        "dependencies_created": deps_created,
    }
