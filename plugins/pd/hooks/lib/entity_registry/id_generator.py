"""Central entity ID generator.

Generates standardised ``{seq}-{slug}`` entity IDs with per-type sequential
counters stored in the ``_metadata`` table.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entity_registry.database import EntityDatabase


def _slugify(name: str, *, max_length: int = 30) -> str:
    """Convert *name* to a lowercase, hyphen-separated slug.

    Rules:
      - Lowercase the entire string
      - Replace non-alphanumeric characters with hyphens
      - Collapse consecutive hyphens
      - Strip leading/trailing hyphens
      - Truncate to *max_length* characters (on a hyphen boundary when possible)
    """
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")

    if len(slug) <= max_length:
        return slug

    # Truncate on a hyphen boundary to avoid cutting mid-word
    truncated = slug[:max_length]
    last_hyphen = truncated.rfind("-")
    if last_hyphen > 0:
        truncated = truncated[:last_hyphen]
    return truncated.rstrip("-")


def _scan_existing_max_seq(db: "EntityDatabase", entity_type: str) -> int:
    """Scan existing entities to find the max sequence number for *entity_type*.

    Looks at ``entity_id`` values matching ``^\\d{3,}-`` pattern and returns
    the highest numeric prefix found.  Returns 0 if no matching entities exist.
    """
    entity_ids = db.scan_entity_ids(entity_type)
    max_seq = 0
    for entity_id in entity_ids:
        match = re.match(r"^(\d+)-", entity_id)
        if match:
            max_seq = max(max_seq, int(match.group(1)))
    return max_seq


def generate_entity_id(db: "EntityDatabase", entity_type: str, name: str) -> str:
    """Generate a standardised ``{seq}-{slug}`` entity ID.

    Parameters
    ----------
    db:
        EntityDatabase instance (used for metadata counter persistence).
    entity_type:
        The entity type (e.g. ``"feature"``, ``"task"``).
    name:
        Human-readable name from which the slug is derived.

    Returns
    -------
    str
        Entity ID in ``{seq:03d}-{slug}`` format.
    """
    key = f"next_seq_{entity_type}"
    raw = db.get_metadata(key)

    if raw is None:
        # Bootstrap: scan existing entities for this type
        current_max = _scan_existing_max_seq(db, entity_type)
        seq = current_max + 1
    else:
        seq = int(raw) + 1

    db.set_metadata(key, str(seq))
    slug = _slugify(name)

    if not slug:
        slug = "unnamed"

    return f"{seq:03d}-{slug}"
