"""Entity status sync: reads .meta.json files, compares with entity registry, updates on drift."""
import json
import os


def sync_entity_statuses(db, full_artifacts_path):
    """Scan .meta.json files for features and projects and sync status to entity registry.

    Args:
        db: EntityDatabase instance
        full_artifacts_path: absolute path to the artifacts root (e.g., /project/docs)

    Returns:
        {"updated": int, "skipped": int, "archived": int, "warnings": list[str]}
    """
    STATUS_MAP = {"active", "completed", "abandoned", "planned", "promoted"}
    results = {"updated": 0, "skipped": 0, "archived": 0, "warnings": []}

    for entity_type, subdir in [("feature", "features"), ("project", "projects")]:
        scan_dir = os.path.join(full_artifacts_path, subdir)
        if not os.path.isdir(scan_dir):
            continue

        for folder in os.listdir(scan_dir):
            meta_path = os.path.join(scan_dir, folder, ".meta.json")
            type_id = f"{entity_type}:{folder}"

            if not os.path.isfile(meta_path):
                # .meta.json deleted — archive entity if it exists
                try:
                    db.update_entity(type_id, status="archived")
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
                db.update_entity(type_id, status=meta_status)
                results["updated"] += 1
            else:
                results["skipped"] += 1

    return results
