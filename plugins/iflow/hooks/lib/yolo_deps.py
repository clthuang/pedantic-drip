"""Dependency check for YOLO feature selection (Feature 038).

Checks whether a feature's declared dependencies (depends_on_features)
are all completed. Used by yolo-stop.sh to skip features with unmet deps.
"""
from __future__ import annotations

import json
import os


def check_feature_deps(meta_path: str, features_dir: str) -> tuple[bool, str | None]:
    """Check if a feature's dependencies are all completed.

    Args:
        meta_path: Absolute path to the feature's .meta.json
        features_dir: Absolute path to the features directory

    Returns:
        (True, None) -- all deps met or no deps declared
        (False, "dep_ref:status") -- first unmet dep found

    Status labels:
        - Actual status string (e.g., "blocked", "planned") for readable dep .meta.json
        - "missing" for FileNotFoundError
        - "unreadable" for JSONDecodeError or other parse failures
        - "missing" for non-string dep elements (coerced to str for ref)
    """
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return (True, None)

    deps = meta.get("depends_on_features") or []

    for dep in deps:
        if not isinstance(dep, str):
            return (False, f"{dep}:missing")

        dep_meta_path = os.path.join(features_dir, dep, ".meta.json")
        # Guard against path traversal (e.g., "../../etc" or absolute paths)
        resolved = os.path.realpath(dep_meta_path)
        if not resolved.startswith(os.path.realpath(features_dir) + os.sep):
            return (False, f"{dep}:missing")
        try:
            with open(dep_meta_path) as f:
                dep_data = json.load(f)
            status = dep_data.get("status", "unknown")
            if status != "completed":
                return (False, f"{dep}:{status}")
        except FileNotFoundError:
            return (False, f"{dep}:missing")
        except (json.JSONDecodeError, OSError, AttributeError):
            return (False, f"{dep}:unreadable")

    return (True, None)
