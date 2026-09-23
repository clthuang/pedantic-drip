"""Entity identity: allocation, rendering and the one sanctioned parse.

``generate_entity_id`` allocates ``(seq, slug)`` from the per-type counters in
the ``sequences`` table; ``render_display_id`` renders them as ``{seq:03d}-{slug}``;
``registration_identity`` turns display text read from a file back into
them, or refuses.
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


# Kinds whose identity is NOT a sequence number, so ``render_display_id``
# cannot produce a valid id for them. Brainstorm identity is a timestamp
# (``{YYYYMMDD-HHMMSS}-{slug}``, commands/brainstorm.md) and no brainstorm
# path calls the allocator — measured on the live registry: 96 of 100
# brainstorms are date-shaped, 1 is seq-shaped, 3 predate the convention.
#
# Canonical home for this fact. ``entity_registry.clean_break`` imports it
# rather than keeping a second copy; two homes for one fact is the defect
# this effort exists to remove.
NON_SEQUENCE_KINDS = frozenset({"brainstorm"})


def render_display_id(kind: str, seq: int, slug: str) -> str:
    r"""Compose the one canonical display id: ``{seq:03d}-{slug}``.

    THE single place that turns structured identity into display text. The
    allocator (``entity_server.allocate_entity_id``) and the registrar
    (``generate_entity_id``) previously each hardcoded this f-string and
    could therefore disagree.

    **No project branch.** Projects render exactly like every other
    sequence-numbered kind. The ``P`` prefix was never produced here or at
    either call site — it came from the caller, ``create-project.md``, which
    built ``P{NNN}`` from the returned ``seq`` and discarded the returned
    ``entity_id``. Dropping it removes the special case behind the original
    incident: ``_PROJECT_DISPLAY_RE = ^P(\d+)$`` existed only to parse the
    prefix back off, and its end anchor silently returned nothing for every
    slug-suffixed project id.

    *kind* is not decorative: it refuses kinds that do not use sequence
    identity at all, rather than minting a plausible-looking wrong id for
    them.

    Raises
    ------
    ValueError
        If *kind* has no sequence identity, if *seq* is not a positive
        integer, or if *slug* is empty.
    """
    if kind in NON_SEQUENCE_KINDS:
        raise ValueError(
            f"{kind!r} identity is not a sequence; render_display_id cannot "
            f"compose an id for it"
        )
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        raise ValueError(f"seq must be a positive int, got {seq!r}")
    if not slug:
        raise ValueError("slug must be non-empty")
    return f"{seq:03d}-{slug}"


def registration_identity(kind: str, entity_id: str) -> dict | None:
    """``register_entity``'s identity keywords for ``entity_id``, an id as it
    displays, or ``None`` when that text has no structured form.

    The one sanctioned text-to-identity parse (declared in the inference
    inventory): ids read from files and tool arguments arrive as text.
    A non-sequence kind passes through as ``display_id``. A sequence kind
    splits into ``seq`` and ``slug`` only when ``render_display_id`` gives the
    same text back, so a legacy id (``00019``, ``P001``, ``00019-slug``) has
    none: callers skip it rather than guess.
    """
    if kind in NON_SEQUENCE_KINDS:
        return {"display_id": entity_id}
    seq_text, _, slug = entity_id.partition("-")
    # isascii: str.isdigit accepts "²", which int() then refuses.
    if not (seq_text.isascii() and seq_text.isdigit()) or int(seq_text) < 1 or not slug:
        return None
    if render_display_id(kind, int(seq_text), slug) != entity_id:
        return None
    return {"seq": int(seq_text), "slug": slug}


def generate_entity_id(
    db: "EntityDatabase", entity_type: str, name: str, project_id: str
) -> tuple[int, str]:
    """Allocate the next sequence value and derive the slug for a new entity.

    Parameters
    ----------
    db:
        EntityDatabase instance (used for sequence counter persistence).
    entity_type:
        The entity type (e.g. ``"feature"``, ``"task"``).
    name:
        Human-readable name from which the slug is derived.
    project_id:
        The project scope for the sequence counter.

    Returns
    -------
    tuple[int, str]
        ``(seq, slug)``, which ``register_entity`` takes as they are;
        ``render_display_id`` gives the display text.
    """
    seq = db.next_sequence_value(project_id, entity_type)
    slug = _slugify(name)

    if not slug:
        slug = "unnamed"

    return seq, slug
