"""Bidirectional sync between frontmatter headers and entity DB.

Provides drift detection, DB-to-file stamping, file-to-DB ingestion,
bulk backfill, and bulk scan operations.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from entity_registry.database import EntityDatabase
from entity_registry.frontmatter import (
    FrontmatterUUIDMismatch,
    build_header,
    read_frontmatter,
    validate_header,
    write_frontmatter,
)
from entity_registry.frontmatter_inject import (
    ARTIFACT_BASENAME_MAP,
    ARTIFACT_PHASE_MAP,
    _parse_feature_type_id,
)

logger = logging.getLogger("entity_registry.frontmatter_sync")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maps file frontmatter field names to DB column names for drift comparison.
# Only these fields are compared; all others are informational (spec R6).
COMPARABLE_FIELD_MAP: dict[str, str] = {
    "entity_uuid": "uuid",
    "entity_type_id": "type_id",
}

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FieldMismatch:
    """Single-field comparison result between file and DB."""

    field: str
    file_value: str | None
    db_value: str | None


@dataclass
class DriftReport:
    """Full drift assessment for a single file."""

    filepath: str
    type_id: str | None
    status: str  # "in_sync" | "file_only" | "db_only" | "diverged" | "no_header" | "error"
    file_fields: dict | None
    db_fields: dict | None
    mismatches: list[FieldMismatch]


@dataclass
class StampResult:
    """Outcome of a DB-to-file stamp operation."""

    filepath: str
    action: str  # "created" | "updated" | "skipped" | "error"
    message: str


@dataclass
class IngestResult:
    """Outcome of a file-to-DB ingest operation."""

    filepath: str
    action: str  # "updated" | "skipped" | "error"
    message: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _derive_optional_fields(entity: dict, artifact_type: str) -> dict:
    """Derive optional frontmatter fields from an entity record.

    Extracts feature_id/feature_slug (feature entities only), project_id
    (from metadata JSON or parent_type_id fallback), and phase (from
    artifact_type mapping).

    Parameters
    ----------
    entity:
        Entity dict as returned by ``EntityDatabase.get_entity()``.
    artifact_type:
        The artifact type string (e.g. "spec", "design").

    Returns
    -------
    dict
        Optional kwargs suitable for ``build_header(**kwargs)``.
    """
    kwargs: dict[str, str] = {}
    entity_type, _, _ = entity["type_id"].partition(":")

    # feature_id + feature_slug (feature entities only)
    if entity_type == "feature":
        feat_id, feat_slug = _parse_feature_type_id(entity["type_id"])
        if feat_id:
            kwargs["feature_id"] = feat_id
        if feat_slug is not None:
            kwargs["feature_slug"] = feat_slug

    # project_id: metadata JSON first, then parent_type_id fallback
    project_id = None
    if entity.get("metadata"):
        try:
            meta = json.loads(entity["metadata"])
            project_id = meta.get("project_id") or None
        except (json.JSONDecodeError, TypeError):
            pass
    if project_id is None and entity.get("parent_type_id"):
        p_type, _, p_id = entity["parent_type_id"].partition(":")
        if p_type == "project":
            project_id = p_id
    if project_id:
        kwargs["project_id"] = project_id

    # phase: from artifact_type mapping
    phase = ARTIFACT_PHASE_MAP.get(artifact_type)
    if phase:
        kwargs["phase"] = phase

    return kwargs


def _derive_feature_directory(entity: dict, artifacts_root: str) -> str | None:
    """Derive the feature directory for an entity using a 4-step fallback.

    Fallback chain (spec R20 step 2):
      (a) artifact_path is a directory -> return it
      (b) artifact_path is a file -> return dirname
      (c) construct from entity_id: {artifacts_root}/features/{entity_id}/
      (d) if constructed path doesn't exist -> return None (skip)

    Parameters
    ----------
    entity:
        Entity dict as returned by ``EntityDatabase.get_entity()``.
    artifacts_root:
        Root directory for artifact files (e.g. "docs").

    Returns
    -------
    str | None
        Resolved directory path, or None if no directory can be derived.
    """
    ap = entity.get("artifact_path")
    if ap:
        if os.path.isdir(ap):
            return ap
        if os.path.isfile(ap):
            return os.path.dirname(ap)
    # Construct from entity_id (fallback step c)
    candidate = os.path.join(artifacts_root, "features", entity["entity_id"])
    if os.path.isdir(candidate):
        return candidate
    return None


# ---------------------------------------------------------------------------
# Public API: Core sync functions
# ---------------------------------------------------------------------------


def detect_drift(
    db: EntityDatabase,
    filepath: str,
    type_id: str | None = None,
) -> DriftReport:
    """Compare frontmatter header in *filepath* against the DB record.

    Stateless comparison -- reads file and DB, returns a :class:`DriftReport`.
    Never raises: all exceptions are caught and returned as ``status="error"``.

    Parameters
    ----------
    db:
        Entity database instance.
    filepath:
        Path to the markdown file to inspect.
    type_id:
        Optional entity type_id for DB lookup. If omitted, the entity is
        looked up by ``entity_uuid`` from the file's frontmatter header.

    Returns
    -------
    DriftReport
    """
    try:
        # Step 1: Read frontmatter from file
        header = read_frontmatter(filepath)

        # Step 2: Determine lookup_key
        lookup_key: str | None = None
        if type_id is not None:
            lookup_key = type_id
        elif header is not None:
            uuid_key = header.get("entity_uuid")
            if uuid_key is None:
                # Header exists but has no entity_uuid -- untracked
                return DriftReport(
                    filepath=filepath,
                    type_id=None,
                    status="no_header",
                    file_fields=dict(header),
                    db_fields=None,
                    mismatches=[],
                )
            lookup_key = uuid_key
        else:
            # No header, no type_id -- can't look up anything
            return DriftReport(
                filepath=filepath,
                type_id=None,
                status="no_header",
                file_fields=None,
                db_fields=None,
                mismatches=[],
            )

        # Step 3: Look up entity in DB
        entity = db.get_entity(lookup_key)

        # Step 4-6: Branch on header/entity presence
        if header is not None and entity is None:
            return DriftReport(
                filepath=filepath,
                type_id=type_id,
                status="file_only",
                file_fields=dict(header),
                db_fields=None,
                mismatches=[],
            )

        if header is None and entity is not None:
            return DriftReport(
                filepath=filepath,
                type_id=entity["type_id"],
                status="db_only",
                file_fields=None,
                db_fields=dict(entity),
                mismatches=[],
            )

        if header is None and entity is None:
            # Defensive: should not happen after step 2, but guard anyway
            return DriftReport(
                filepath=filepath,
                type_id=type_id,
                status="no_header",
                file_fields=None,
                db_fields=None,
                mismatches=[],
            )

        # Step 7: Both exist -- compare COMPARABLE_FIELD_MAP fields
        mismatches: list[FieldMismatch] = []
        for file_field, db_column in COMPARABLE_FIELD_MAP.items():
            file_val = header.get(file_field)  # type: ignore[union-attr]
            db_val = entity.get(db_column)  # type: ignore[union-attr]

            if file_field == "entity_uuid":
                # UUID comparison is case-insensitive
                if (file_val or "").lower() != (db_val or "").lower():
                    mismatches.append(FieldMismatch(
                        field=file_field,
                        file_value=file_val,
                        db_value=db_val,
                    ))
            else:
                # type_id comparison is case-sensitive
                if file_val != db_val:
                    mismatches.append(FieldMismatch(
                        field=file_field,
                        file_value=file_val,
                        db_value=db_val,
                    ))

        # Step 8-9: Diverged or in_sync
        status = "diverged" if mismatches else "in_sync"
        return DriftReport(
            filepath=filepath,
            type_id=entity["type_id"],  # type: ignore[index]
            status=status,
            file_fields=dict(header),  # type: ignore[arg-type]
            db_fields=dict(entity),  # type: ignore[arg-type]
            mismatches=mismatches,
        )

    except Exception as exc:
        logger.warning("detect_drift error for %s: %s", filepath, exc)
        return DriftReport(
            filepath=filepath,
            type_id=type_id,
            status="error",
            file_fields=None,
            db_fields=None,
            mismatches=[],
        )


def stamp_header(
    db: EntityDatabase,
    filepath: str,
    type_id: str,
    artifact_type: str,
) -> StampResult:
    """Stamp a DB entity record onto a file as frontmatter (DB-authoritative).

    Reads the entity from the DB by *type_id*, constructs a frontmatter header,
    and writes it to *filepath* using :func:`write_frontmatter`.

    Never raises: all exceptions are caught and returned as ``action="error"``.

    Parameters
    ----------
    db:
        Entity database instance.
    filepath:
        Path to the markdown file to stamp.
    type_id:
        Entity type_id for DB lookup.
    artifact_type:
        Artifact type string (e.g. "spec", "design").

    Returns
    -------
    StampResult
    """
    # Step 1: Look up entity in DB
    try:
        entity = db.get_entity(type_id)
    except Exception as exc:
        return StampResult(
            filepath=filepath,
            action="error",
            message=f"DB error looking up {type_id!r}: {exc}",
        )

    if entity is None:
        return StampResult(
            filepath=filepath,
            action="error",
            message=f"Entity not found: {type_id!r}",
        )

    # Step 2: Extract required fields
    entity_uuid = entity["uuid"]
    entity_type_id = entity["type_id"]
    created_at = entity["created_at"]

    # Step 3: Derive optional fields
    optional = _derive_optional_fields(entity, artifact_type)

    # Steps 4-7: build_header -> read existing -> UUID mismatch check -> write
    try:
        header = build_header(
            entity_uuid, entity_type_id, artifact_type, created_at, **optional
        )

        existing = read_frontmatter(filepath)

        if (
            existing
            and existing.get("entity_uuid")
            and existing["entity_uuid"].lower() != entity_uuid.lower()
        ):
            return StampResult(
                filepath=filepath,
                action="error",
                message=(
                    f"UUID mismatch: file has {existing['entity_uuid']!r}, "
                    f"DB has {entity_uuid!r}"
                ),
            )

        write_frontmatter(filepath, header)

    except FrontmatterUUIDMismatch as exc:
        return StampResult(
            filepath=filepath,
            action="error",
            message=f"UUID mismatch: {exc}",
        )
    except (ValueError, Exception) as exc:
        return StampResult(
            filepath=filepath,
            action="error",
            message=f"Stamp failed: {exc}",
        )

    # Step 8: Determine action
    action = "created" if existing is None or not existing.get("entity_uuid") else "updated"
    return StampResult(
        filepath=filepath,
        action=action,
        message=f"Header {action} for {entity_type_id}",
    )


def ingest_header(
    db: EntityDatabase,
    filepath: str,
) -> IngestResult:
    """Ingest frontmatter from a file into the DB (file-authoritative).

    Reads frontmatter from *filepath*, looks up the entity by UUID, and
    updates the DB record's ``artifact_path``. Only ``artifact_path`` is
    written to the DB -- all other fields are immutable or informational.

    Never raises: all exceptions are caught and returned as appropriate
    action results.

    Parameters
    ----------
    db:
        Entity database instance.
    filepath:
        Path to the markdown file to ingest.

    Returns
    -------
    IngestResult
    """
    try:
        # Step 1: Read frontmatter
        header = read_frontmatter(filepath)
        if header is None:
            return IngestResult(
                filepath=filepath,
                action="skipped",
                message="No frontmatter found",
            )

        # Step 2: Extract entity_uuid
        entity_uuid = header.get("entity_uuid")
        if not entity_uuid:
            return IngestResult(
                filepath=filepath,
                action="skipped",
                message="No entity_uuid in header",
            )

        # Step 3: Look up entity in DB
        entity = db.get_entity(entity_uuid)
        if entity is None:
            return IngestResult(
                filepath=filepath,
                action="error",
                message=f"Entity not found in DB: {entity_uuid!r}",
            )

        # Step 4-5: Update artifact_path
        abs_path = os.path.abspath(filepath)
        try:
            db.update_entity(entity_uuid, artifact_path=abs_path)
        except ValueError as exc:
            return IngestResult(
                filepath=filepath,
                action="error",
                message=f"Entity disappeared between read and write: {entity_uuid!r}",
            )

        # Step 6: Success
        return IngestResult(
            filepath=filepath,
            action="updated",
            message=f"artifact_path set to {abs_path}",
        )

    except Exception as exc:
        logger.warning("ingest_header error for %s: %s", filepath, exc)
        return IngestResult(
            filepath=filepath,
            action="error",
            message=f"Ingest failed: {exc}",
        )
