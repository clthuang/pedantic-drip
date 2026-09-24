"""Entity identity: allocation, rendering, the one sanctioned parse, the invariant.

``generate_entity_id`` allocates ``(seq, slug)`` from the per-type counters in
the ``sequences`` table; ``render_display_id`` renders them as ``{seq:03d}-{slug}``;
``registration_identity`` turns display text read from a file back into
them, or refuses; ``display_row_violations_sql`` states the display-row invariant.
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

    Raises
    ------
    IncompleteBucketError
        From ``next_sequence_value`` (C3): the bucket holds an entity that
        breaks the display-row invariant. Nothing was allocated; callers
        report it rather than retry.
    """
    seq = db.next_sequence_value(project_id, entity_type)
    slug = _slugify(name)

    if not slug:
        slug = "unnamed"

    return seq, slug


# ---------------------------------------------------------------------------
# The display-row invariant
# ---------------------------------------------------------------------------

# The flag columns that exempt an entity from the display-row invariant.
# is_legacy arrived in migration 22, is_deleted in 24.
DISPLAY_ROW_EXEMPTION_FLAGS = ("is_legacy", "is_deleted")

# Where an entity's kind lives: kind since migration 12, entity_type before.
_KIND_COLUMNS = ("kind", "entity_type")


def display_row_violations_sql(
    entity_columns: set[str],
) -> tuple[str, tuple[str, ...]]:
    """``FROM ... WHERE ...`` selecting every entity that breaks the
    display-row invariant. THE one statement of that invariant.

    **The invariant.** Every entity has an ``entity_display`` row unless it
    is exempt. An entity is exempt when any of these holds:

    - ``is_legacy = 1``: it predates the structural model. The ``sequences``
      counter reserves its number (B4's high-water sweep), not a display
      row. The column is immutable (v2 migration 7), so it cannot mute a
      violation.
    - ``is_deleted = 1``: it is soft-deleted (#081).
    - its kind is in ``NON_SEQUENCE_KINDS``: its identity is not a sequence
      number (a brainstorm's is its file stem), so it has no display row by
      design (Wave 2 D3).

    **Both enforcers build their SQL here, never from a copy:**

    - ``doctor.checks.check_display_row_invariant`` reports every violation
      in the registry.
    - ``EntityDatabase.next_sequence_value`` refuses to allocate for a
      bucket that holds one (C3): a violating entity's number exists only in
      its ``entity_id`` text, which the structural census cannot see.

    With a second copy of these clauses, doctor could report a registry
    green while allocation refuses it, or the reverse.

    **Interface.** Returns ``(sql, params)``. The SQL aliases ``entities`` as
    ``e`` and ``entity_display`` as ``d``. A caller prepends its own
    ``SELECT``, may append ``AND`` clauses to narrow the scope, and binds
    *params* before any parameters of its own.

    *entity_columns* is the ``entities`` table's column set, from
    ``PRAGMA table_info(entities)``. Each clause is added only when its
    column exists, and each absence has a deliberate reading:

    - **No exemption flag column:** that flag exempts nothing. A file
      predating ``is_legacy`` has no entity marked legacy.
    - **No ``kind`` column:** the kind clause reads ``entity_type``
      instead, never nothing. A file predating migration 12 still holds
      brainstorms.
    - **Neither kind column:** no kind is exempt, so every display-less row
      is reported. That is a false alarm, never a silent pass.

    The SQL never names a column the table lacks. Doing so makes the
    statement raise, and a caller that swallowed the error would report a
    registry it never evaluated.
    """
    where = ["d.uuid IS NULL"]
    for flag in DISPLAY_ROW_EXEMPTION_FLAGS:
        if flag in entity_columns:
            where.append(f"NOT COALESCE(e.{flag}, 0)")
    params: tuple[str, ...] = ()
    kind_column = next((c for c in _KIND_COLUMNS if c in entity_columns), None)
    if kind_column is not None:
        params = tuple(sorted(NON_SEQUENCE_KINDS))
        placeholders = ", ".join("?" for _ in params)
        where.append(f"COALESCE(e.{kind_column}, '') NOT IN ({placeholders})")
    return (
        "FROM entities e LEFT JOIN entity_display d ON d.uuid = e.uuid "
        "WHERE " + " AND ".join(where),
        params,
    )
