"""Metadata parsing, validation, and schema definitions for entity types.

Centralizes the duplicated parse pattern (6+ files) and provides
optional schema-based validation on writes.

Contract difference from server_helpers.parse_metadata:
  - This parse_metadata returns {} for None input (never None).
  - server_helpers.parse_metadata returns None for None input.
  server_helpers now re-exports this version; callers that checked
  `if meta is None` must use `if not meta` instead.
"""
from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# Metadata schemas per entity type
# ---------------------------------------------------------------------------
# Each schema maps key -> expected type (or tuple of types).
# Keys present in _COMMON_SCHEMA apply to ALL entity types.
# Unknown keys produce warnings but never block writes.
#
# Inventory source: grep of all register_entity / update_entity / meta.get()
# calls across entity_registry/, workflow_engine/, mcp/ (Task 1A.0 audit).
# ---------------------------------------------------------------------------

_COMMON_SCHEMA: dict[str, type | tuple[type, ...]] = {
    "progress": (int, float),
}

METADATA_SCHEMAS: dict[str, dict[str, type | tuple[type, ...]]] = {
    "feature": {
        "id": str,
        "slug": str,
        "mode": str,
        "branch": str,
        "phase_timing": dict,
        "last_completed_phase": str,
        "skipped_phases": list,
        "brainstorm_source": str,
        "backlog_source": str,
        "depends_on_features": list,
        "project_id": str,
        "weight": str,
    },
    "project": {
        "id": str,
        "slug": str,
        "features": list,
        "milestones": list,
        "brainstorm_source": str,
    },
    "task": {
        "source_heading": str,
    },
    "backlog": {
        "description": str,
    },
    "objective": {
        "score": (int, float),
    },
    "key_result": {
        "metric_type": str,
        "weight": (int, float),
    },
    "initiative": {},
    "brainstorm": {},
}


def parse_metadata(raw: str | dict | None) -> dict:
    """Parse raw metadata into a dict.

    Parameters
    ----------
    raw:
        JSON string, dict, or None.

    Returns
    -------
    dict
        Parsed metadata. Returns {} for None input (never returns None).
        Returns {} for invalid JSON (logs no error — callers handle gracefully).
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        result = json.loads(raw)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}


def validate_metadata(entity_type: str, metadata: dict) -> list[str]:
    """Validate metadata keys/types against the schema for entity_type.

    Parameters
    ----------
    entity_type:
        The entity type to validate against.
    metadata:
        The metadata dict to check.

    Returns
    -------
    list[str]
        Warning strings. Empty list means all known keys have correct types.
        Unknown keys produce a warning but never block writes.
    """
    if not metadata:
        return []

    schema = METADATA_SCHEMAS.get(entity_type)
    if schema is None:
        return [f"No schema defined for entity_type '{entity_type}'"]

    # Merge common + type-specific schema
    full_schema = {**_COMMON_SCHEMA, **schema}
    warnings: list[str] = []

    for key, value in metadata.items():
        if key not in full_schema:
            warnings.append(f"Unknown metadata key '{key}' for {entity_type}")
            continue
        expected = full_schema[key]
        if not isinstance(value, expected):
            expected_names = (
                expected.__name__
                if isinstance(expected, type)
                else " | ".join(t.__name__ for t in expected)
            )
            warnings.append(
                f"Metadata key '{key}' for {entity_type}: "
                f"expected {expected_names}, got {type(value).__name__}"
            )

    return warnings
