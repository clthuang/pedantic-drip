"""Read, write, validate, and build YAML frontmatter headers for markdown files."""
from __future__ import annotations

import logging
import os
import re
import tempfile
from datetime import datetime

logger = logging.getLogger("entity_registry.frontmatter")


class FrontmatterUUIDMismatch(ValueError):
    """Raised when a write would change the immutable entity_uuid field."""


# Field ordering for serialization (R5, TD-2)
FIELD_ORDER = (
    "entity_uuid",
    "entity_type_id",
    "artifact_type",
    "created_at",
    "feature_id",
    "feature_slug",
    "project_id",
    "phase",
    "updated_at",
)

# Required fields (R3)
REQUIRED_FIELDS = frozenset({
    "entity_uuid",
    "entity_type_id",
    "artifact_type",
    "created_at",
})

# Optional fields (R4)
OPTIONAL_FIELDS = frozenset({
    "feature_id",
    "feature_slug",
    "project_id",
    "phase",
    "updated_at",
})

# All allowed fields
ALLOWED_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS

# Pre-computed set for _serialize_header unknown-field loop
_FIELD_ORDER_SET = frozenset(FIELD_ORDER)

# Allowed artifact types (R3)
ALLOWED_ARTIFACT_TYPES = frozenset({"spec", "design", "plan", "tasks", "retro", "prd"})

# UUID v4 regex (lowercase; callers must .lower() before matching per R11)
_UUID_V4_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_block(lines: list[str]) -> dict:
    """Parse lines between frontmatter delimiters into a key-value dict.

    Each line is split on the first ': ' (colon-space). The portion before
    must match ``[a-z_]+`` to be accepted as a key. Lines that don't match
    are silently ignored.
    """
    result: dict[str, str] = {}
    for line in lines:
        key, sep, value = line.partition(": ")
        if sep and re.fullmatch(r"[a-z_]+", key):
            result[key] = value
    return result


def _serialize_header(header: dict) -> str:
    """Serialize a header dict to a YAML frontmatter string with --- delimiters.

    Fields in FIELD_ORDER come first (in that order), then any remaining keys.
    """
    parts = ["---\n"]
    for field in FIELD_ORDER:
        if field in header:
            parts.append(f"{field}: {header[field]}\n")
    for key in header:
        if key not in _FIELD_ORDER_SET:
            parts.append(f"{key}: {header[key]}\n")
    parts.append("---\n")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_header(header: dict) -> list[str]:
    """Validate a header dict against the schema.

    Returns a list of validation error strings (empty list = valid).
    Does not short-circuit -- all errors are collected.
    """
    errors: list[str] = []

    # 1. Required fields present
    for field in REQUIRED_FIELDS:
        if field not in header:
            errors.append(f"Missing required field: {field}")

    # 2. UUID format (case-insensitive per R11: .lower() before matching)
    if "entity_uuid" in header:
        if not _UUID_V4_RE.fullmatch(header["entity_uuid"].lower()):
            errors.append(
                f"Invalid entity_uuid format: {header['entity_uuid']!r}"
            )

    # 3. Artifact type set membership
    if "artifact_type" in header:
        if header["artifact_type"] not in ALLOWED_ARTIFACT_TYPES:
            errors.append(
                f"Invalid artifact_type: {header['artifact_type']!r} "
                f"(allowed: {sorted(ALLOWED_ARTIFACT_TYPES)})"
            )

    # 4. created_at ISO 8601
    if "created_at" in header:
        try:
            datetime.fromisoformat(header["created_at"])
        except (ValueError, TypeError):
            errors.append(
                f"Invalid created_at (not ISO 8601): {header['created_at']!r}"
            )

    # 5. Unknown fields
    for key in header:
        if key not in ALLOWED_FIELDS:
            errors.append(f"Unknown field: {key!r}")

    return errors


def build_header(
    entity_uuid: str,
    entity_type_id: str,
    artifact_type: str,
    created_at: str,
    **optional_fields,
) -> dict:
    """Construct a validated header dict from required and optional fields.

    Raises ``ValueError`` if any input is invalid (including unknown kwargs).
    """
    header = {
        "entity_uuid": entity_uuid,
        "entity_type_id": entity_type_id,
        "artifact_type": artifact_type,
        "created_at": created_at,
    }
    header.update(optional_fields)

    errors = validate_header(header)
    if errors:
        raise ValueError(
            f"Invalid header: {'; '.join(errors)}"
        )

    return header


def read_frontmatter(filepath: str) -> dict | None:
    """Parse YAML frontmatter from a markdown file.

    Returns a dict of header fields, or ``None`` if no valid frontmatter
    block is found. Never raises exceptions -- errors are logged as warnings.
    """
    # Single read: binary guard + text parsing from one open call
    try:
        with open(filepath, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        logger.warning("File not found: %s", filepath)
        return None

    if b"\x00" in raw[:8192]:
        logger.warning("Binary content detected, skipping: %s", filepath)
        return None

    lines = raw.decode("utf-8").splitlines(keepends=True)

    if not lines:
        # Empty file
        return None

    if lines[0].rstrip("\n") != "---":
        return None

    # Accumulate lines between opening and closing ---
    block_lines: list[str] = []
    for line in lines[1:]:
        stripped = line.rstrip("\n")
        if stripped == "---":
            # Found closing delimiter -- parse what we have
            return _parse_block(block_lines)
        block_lines.append(stripped)

    # EOF without closing delimiter -- malformed
    logger.warning("Malformed frontmatter (no closing ---): %s", filepath)
    return None


def write_frontmatter(filepath: str, headers: dict) -> None:
    """Prepend or update YAML frontmatter in a markdown file.

    Merges *headers* into any existing frontmatter (preserving ``created_at``
    per TD-9). Writes atomically via temp-file + ``os.rename`` (C2).

    Raises ``ValueError`` on UUID mismatch, validation failure, file not found,
    or binary content.
    """
    # --- 1. Single read: file-exists guard + binary guard + content ----------
    try:
        with open(filepath, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        raise ValueError(f"File not found: {filepath}")

    # --- 2. Binary content guard ---------------------------------------------
    if b"\x00" in raw[:8192]:
        raise ValueError(f"Binary content detected: {filepath}")

    # --- 3. Decode and split into lines (own logic, NOT read_frontmatter) ----
    all_lines = raw.decode("utf-8").splitlines(keepends=True)

    existing_header: dict[str, str] = {}
    body_lines: list[str] = []
    has_frontmatter = False

    if all_lines and all_lines[0].rstrip("\n") == "---":
        # Frontmatter detected -- accumulate until closing ---
        idx = 1
        block_lines: list[str] = []
        while idx < len(all_lines):
            stripped = all_lines[idx].rstrip("\n")
            if stripped == "---":
                # Found closing delimiter
                has_frontmatter = True
                existing_header = _parse_block(block_lines)
                body_lines = all_lines[idx + 1:]
                break
            block_lines.append(stripped)
            idx += 1
        else:
            # EOF without closing --- : treat entire file as body (no frontmatter)
            body_lines = all_lines
    else:
        body_lines = all_lines

    # --- 4. UUID match check -------------------------------------------------
    if has_frontmatter and "entity_uuid" in existing_header and "entity_uuid" in headers:
        if existing_header["entity_uuid"].lower() != headers["entity_uuid"].lower():
            raise FrontmatterUUIDMismatch(
                f"UUID mismatch: file has {existing_header['entity_uuid']!r}, "
                f"got {headers['entity_uuid']!r}"
            )

    # --- 5. Merge: existing <- new -------------------------------------------
    merged = dict(existing_header)  # start with existing

    for key, value in headers.items():
        if value is None or value == "":
            # Explicit deletion (R9)
            merged.pop(key, None)
        else:
            merged[key] = value

    # TD-9: created_at is preserved from existing (immutable after first write)
    if "created_at" in existing_header:
        merged["created_at"] = existing_header["created_at"]

    # --- 6. Validate merged header -------------------------------------------
    errors = validate_header(merged)
    if errors:
        raise ValueError(
            f"Validation failed after merge: {'; '.join(errors)}"
        )

    # --- 7. Serialize --------------------------------------------------------
    new_content = _serialize_header(merged) + "".join(body_lines)

    # --- 8. Atomic write: temp file + os.rename (C2, TD-3) -------------------
    target_dir = os.path.dirname(os.path.abspath(filepath))
    tmp_fd = None
    tmp_path = None
    try:
        tmp_fd = tempfile.NamedTemporaryFile(
            mode="w",
            dir=target_dir,
            delete=False,
            suffix=".tmp",
            encoding="utf-8",
        )
        tmp_path = tmp_fd.name
        tmp_fd.write(new_content)
        tmp_fd.close()
        tmp_fd = None  # closed successfully
        os.rename(tmp_path, filepath)
        tmp_path = None  # rename succeeded -- no cleanup needed
    finally:
        if tmp_fd is not None:
            tmp_fd.close()
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
