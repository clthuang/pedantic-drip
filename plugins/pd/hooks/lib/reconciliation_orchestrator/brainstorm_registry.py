"""Brainstorm Registry Sync — C3.

Scans brainstorms/ directory for .prd.md files and registers any unregistered
files as brainstorm entities in the entity registry.
"""
import os

from entity_registry.database import EntityDatabase


def sync_brainstorm_entities(
    db: EntityDatabase,
    full_artifacts_path: str,
    artifacts_root: str,
) -> dict:
    """Scan brainstorms/ for .prd.md files; register unregistered ones.

    Args:
        db: EntityDatabase instance (open connection).
        full_artifacts_path: Absolute path to the artifacts root directory
            (e.g., /Users/terry/projects/pedantic-drip/docs).
        artifacts_root: Relative sub-path used to build the stored artifact_path
            (e.g., "docs").

    Returns:
        {"registered": int, "skipped": int}
    """
    results = {"registered": 0, "skipped": 0}
    brainstorms_dir = os.path.join(full_artifacts_path, "brainstorms")

    if not os.path.isdir(brainstorms_dir):
        return results

    for filename in os.listdir(brainstorms_dir):
        if filename == ".gitkeep" or not filename.endswith(".prd.md"):
            continue

        stem = filename[: -len(".prd.md")]
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
        )
        results["registered"] += 1

    return results
