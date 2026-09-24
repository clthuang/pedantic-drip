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
from entity_registry.id_generator import read_display_identity
from entity_registry.metadata import parse_metadata

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
    "shape.md": "shape",
    "spec.md": "spec",
    "design.md": "design",
    "plan.md": "plan",
    "tasks.md": "tasks",
    "retro.md": "retro",
    "prd.md": "prd",
}

# I5 step 7: artifact_type -> workflow phase
ARTIFACT_PHASE_MAP: dict[str, str] = {
    "shape": "specify",
    "spec": "specify",
    "design": "design",
    "plan": "create-plan",
    "tasks": "create-plan",
    "retro": "finish",
    "prd": "brainstorm",
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _feature_identity_fields(db: EntityDatabase, entity: dict) -> dict[str, str]:
    """The ``feature_id`` / ``feature_slug`` header fields for *entity* (C9).

    Read from its display row by ``read_display_identity``, the reader the
    ``.meta.json`` projection uses, so the header and the projection show
    the same number at the same width. An entity with no usable display row
    (a legacy entity) falls back to the ``id``/``slug`` its metadata stored
    at registration, as the projection does. The stored ``entity_id`` is
    never taken apart (design D9). An absent value is omitted, as optional
    header fields always were.
    """
    identity = read_display_identity(db, entity["uuid"], entity["kind"], entity["entity_id"])
    if identity is not None:
        feature_id, feature_slug = identity
        return {"feature_id": feature_id, "feature_slug": feature_slug}
    metadata = parse_metadata(entity.get("metadata"))
    fields: dict[str, str] = {}
    if metadata.get("id"):
        fields["feature_id"] = str(metadata["id"])
    if metadata.get("slug"):
        fields["feature_slug"] = str(metadata["slug"])
    return fields


def _parent_project_id(db: EntityDatabase, entity: dict) -> str | None:
    """The ``project_id`` header field: the stored ``entity_id`` of *entity*'s
    parent when that parent is a project, else None (C10).

    The parent is found by ``parent_uuid`` and is a project when its ``kind``
    column says so. Its ``entity_id`` is read whole, a column read and not
    inference (design D9), so a parent with no display row still resolves:
    a live child of an archived legacy project keeps its ``project_id``. A
    soft-deleted parent resolves too, as the ``parent_type_id`` join this
    replaces did.
    """
    parent_uuid = entity.get("parent_uuid")
    if not parent_uuid:
        return None
    parent = db.get_entity_by_uuid(parent_uuid, include_deleted=True)
    if parent is None or parent["kind"] != "project":
        return None
    return parent["entity_id"]


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

        # 7. Build optional fields from the entity's structure: its display
        # row (C9) and its parent row (C10), never its type_id text.
        project_id = _parent_project_id(db, entity_record)
        phase = ARTIFACT_PHASE_MAP.get(artifact_type)

        optional_kwargs: dict[str, str] = _feature_identity_fields(db, entity_record)
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
