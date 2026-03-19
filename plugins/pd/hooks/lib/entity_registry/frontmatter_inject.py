"""CLI script for frontmatter injection during workflow commit.

Invoked by commitAndComplete in workflow-transitions SKILL.md to embed
entity identity headers into markdown artifact files before git add.

Usage: python frontmatter_inject.py <artifact_path> <feature_type_id>

Exit codes:
    0 - success or graceful skip (unsupported basename, DB unavailable, entity missing)
    1 - UUID mismatch or bad arguments
"""
from __future__ import annotations

import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone

from entity_registry.database import EntityDatabase
from entity_registry.frontmatter import (
    FrontmatterUUIDMismatch,
    build_header,
    write_frontmatter,
)

# ---------------------------------------------------------------------------
# Logging (TD-7): stderr handler, minimal format
# ---------------------------------------------------------------------------

logger = logging.getLogger("entity_registry.frontmatter_inject")
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
logger.addHandler(_handler)
logger.setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# TD-6: basename -> artifact_type mapping
ARTIFACT_BASENAME_MAP: dict[str, str] = {
    "spec.md": "spec",
    "design.md": "design",
    "plan.md": "plan",
    "tasks.md": "tasks",
    "retro.md": "retro",
    "prd.md": "prd",
}

# I5 step 7: artifact_type -> workflow phase
ARTIFACT_PHASE_MAP: dict[str, str] = {
    "spec": "specify",
    "design": "design",
    "plan": "create-plan",
    "tasks": "create-tasks",
    "retro": "finish",
    "prd": "brainstorm",
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _parse_feature_type_id(type_id: str) -> tuple[str, str | None]:
    """Parse a feature type_id into (feature_id, feature_slug | None).

    The type_id format is 'feature:{id}-{slug}'. The 'feature:' prefix is
    stripped first. Then the entity part is split on the first '-' to get
    (id, slug). If no '-', slug is None.

    Examples:
        'feature:002-some-slug' -> ('002', 'some-slug')
        'feature:noseparator'   -> ('noseparator', None)
        'feature:'              -> ('', None)
    """
    # Strip "feature:" prefix (split on first ':')
    _, _, entity_part = type_id.partition(":")
    # Split entity part on first '-' to get (id, slug)
    if "-" in entity_part:
        feature_id, _, slug = entity_part.partition("-")
        return (feature_id, slug)
    return (entity_part, None)


def _extract_project_id(parent_type_id: str | None) -> str | None:
    """Extract project_id from a parent_type_id string.

    If parent_type_id is None or the entity_type is not 'project',
    returns None. Otherwise returns the entity_id portion.

    Examples:
        'project:P001'   -> 'P001'
        'brainstorm:abc' -> None
        None             -> None
    """
    if parent_type_id is None:
        return None
    entity_type, _, entity_id = parent_type_id.partition(":")
    if entity_type == "project":
        return entity_id
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for frontmatter injection."""
    # 1. Parse args
    if len(sys.argv) != 3:
        print(
            "Usage: python frontmatter_inject.py <artifact_path> <feature_type_id>",
            file=sys.stderr,
        )
        sys.exit(1)

    artifact_path = sys.argv[1]
    feature_type_id = sys.argv[2]

    # 2. Derive artifact_type from basename (R15, TD-6)
    basename = os.path.basename(artifact_path)
    artifact_type = ARTIFACT_BASENAME_MAP.get(basename)
    if artifact_type is None:
        logger.warning("Unsupported artifact basename: %s", basename)
        sys.exit(0)

    # 3. Resolve DB path (TD-5)
    db_path = os.environ.get(
        "ENTITY_DB_PATH",
        os.path.expanduser("~/.claude/pd/entities/entities.db"),
    )

    # 4. Instantiate EntityDatabase and look up entity
    # Note: sys.exit(0) below raises SystemExit, so the finally block at the
    # end of main() handles db.close() only for the success/error paths that
    # reach the inner try block. The DB-open failure path exits the process
    # immediately — no cleanup needed since no connection was established.
    db = None
    try:
        db = EntityDatabase(db_path)
    except (sqlite3.Error, OSError) as exc:
        logger.warning("Cannot open entity DB at %s: %s", db_path, exc)
        sys.exit(0)

    try:
        # 5. Look up entity
        entity_record = db.get_entity(feature_type_id)
        if entity_record is None:
            logger.warning("Entity not found: %s", feature_type_id)
            sys.exit(0)

        # 6. Extract UUID
        entity_uuid = entity_record["uuid"]

        # 7. Build optional fields
        feature_id, feature_slug = _parse_feature_type_id(feature_type_id)
        project_id = _extract_project_id(entity_record.get("parent_type_id"))
        phase = ARTIFACT_PHASE_MAP.get(artifact_type)

        optional_kwargs: dict[str, str] = {}
        if feature_id:
            optional_kwargs["feature_id"] = feature_id
        if feature_slug is not None:
            optional_kwargs["feature_slug"] = feature_slug
        if project_id is not None:
            optional_kwargs["project_id"] = project_id
        if phase is not None:
            optional_kwargs["phase"] = phase

        # 8. Build header
        created_at = datetime.now(timezone.utc).isoformat()
        header = build_header(
            entity_uuid=entity_uuid,
            entity_type_id=feature_type_id,
            artifact_type=artifact_type,
            created_at=created_at,
            **optional_kwargs,
        )

        # 9. Write frontmatter
        write_frontmatter(artifact_path, header)

    except FrontmatterUUIDMismatch as exc:
        logger.error("Frontmatter injection failed: %s", exc)
        sys.exit(1)
    except ValueError as exc:
        logger.warning("Frontmatter injection skipped: %s", exc)
        sys.exit(0)
    except OSError as exc:
        logger.warning("Frontmatter injection I/O error: %s", exc)
        sys.exit(0)
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    main()
