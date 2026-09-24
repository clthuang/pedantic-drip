"""Entity identity: allocation, rendering, reading, the one sanctioned parse, the invariant.

``generate_entity_id`` allocates ``(seq, slug)`` from the per-type counters in
the ``sequences`` table; ``render_display_id`` renders them as ``{seq:03d}-{slug}``,
its number part by ``render_display_seq``; ``read_display_identity`` reads a
registered entity's displayed number and slug from its display row;
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


def render_display_seq(kind: str, seq: int) -> str:
    """Render the number part of a display id: *seq* zero-padded to three digits.

    The padding is a MINIMUM width, not a field size: ``1000`` stays
    ``1000``. ``render_display_id`` composes every display id from this, so
    the width is stated once. A reader that shows the number on its own — a
    ``.meta.json`` ``id``, a frontmatter ``feature_id`` — gets it through
    ``read_display_identity``, which uses this except for ids registered
    unpadded (see there), and never from the width of stored text (design
    D5).

    Raises
    ------
    ValueError
        If *kind* has no sequence identity, or if *seq* is not a positive
        integer.
    """
    if kind in NON_SEQUENCE_KINDS:
        raise ValueError(
            f"{kind!r} identity is not a sequence; no display id can be "
            f"rendered for it"
        )
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        raise ValueError(f"seq must be a positive int, got {seq!r}")
    return f"{seq:03d}"


def render_display_id(kind: str, seq: int, slug: str) -> str:
    r"""Compose the one canonical display id: ``{seq:03d}-{slug}``.

    THE single place that turns structured identity into display text; its
    number part is ``render_display_seq``'s. The
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
    seq_text = render_display_seq(kind, seq)
    if not slug:
        raise ValueError("slug must be non-empty")
    return f"{seq_text}-{slug}"


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


def read_display_identity(
    db: "EntityDatabase", entity_uuid: str | None, kind: str, entity_id: str | None,
) -> tuple[str, str] | None:
    """Read a registered entity's displayed ``(number, slug)`` from its
    ``entity_display`` row.

    THE reader behind every surface that shows an entity's number and slug
    separately: the ``.meta.json`` projection's ``id``/``slug`` and the
    frontmatter header's ``feature_id``/``feature_slug``. Returns ``None``
    when there is no row the renderer accepts: a legacy entity, whose number
    exists only inside its id text, or a row with a non-positive ``seq`` or
    an empty ``slug``. Each caller keeps its own fallback for that case, and
    none of them may take the stored id apart instead (design D9).

    **The number is rendered, not recovered.** ``render_display_seq`` decides
    its width, with one exception that keeps live output stable: when
    *entity_id* (the stored ``entities.entity_id``) is exactly the UNPADDED
    form of these same ``(seq, slug)``, ``74-sse-event-stream`` for seq 74,
    the number is shown unpadded. Live features were registered that way
    before registration took structured identity. Their directories,
    branches and ``.meta.json`` files carry the unpadded number, and readers
    rebuild ``{id}-{slug}`` into the type_id and the directory path, so
    ``074`` would send them to an entity and a directory that do not exist.

    *entity_id* is compared WHOLE with compositions of the display row's own
    fields. It is never split, sliced or matched: its text only chooses
    between two renderings of the row's ``seq`` and supplies no digit, width
    or slug. From seq 100 up the two renderings coincide. The unpadded
    composition only recognises an existing id; nothing is registered or
    allocated through it, so ``render_display_id`` stays the one composer
    of new ids.
    """
    row = db.get_entity_display(entity_uuid) if entity_uuid else None
    if row is None:
        return None
    seq, slug = row["seq"], row["slug"]
    try:
        rendered_id = render_display_id(kind, seq, slug)
    except ValueError:
        return None
    if entity_id != rendered_id and entity_id == f"{seq}-{slug}":
        return str(seq), slug
    return render_display_seq(kind, seq), slug


def generate_entity_id(
    db: "EntityDatabase", entity_type: str, name: str, *, workspace_uuid: str,
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
    workspace_uuid:
        The workspace whose counter issues the number. Required. A caller
        that registers the entity next passes this same value to
        ``register_entity`` (C17), so the number and the row share one
        workspace.

    Returns
    -------
    tuple[int, str]
        ``(seq, slug)``, which ``register_entity`` takes as they are;
        ``render_display_id`` gives the display text.

    Raises
    ------
    TypeError
        ``workspace_uuid`` is missing or None: a counter has no scope
        without one.
    IncompleteBucketError
        From ``next_sequence_value`` (C3): the bucket holds an entity that
        breaks the display-row invariant. Nothing was allocated; callers
        report it rather than retry.
    """
    if workspace_uuid is None:
        raise TypeError("generate_entity_id() requires workspace_uuid")
    seq = db.next_sequence_value(entity_type=entity_type, workspace_uuid=workspace_uuid)
    slug = _slugify(name)

    if not slug:
        slug = "unnamed"

    return seq, slug


# ---------------------------------------------------------------------------
# The display-row invariant
# ---------------------------------------------------------------------------

# The flag columns that exempt an entity from the display-row invariant:
# is_legacy alone (migration 22). is_deleted is deliberately absent; see
# display_row_violations_sql.
DISPLAY_ROW_EXEMPTION_FLAGS = ("is_legacy",)

# Where an entity's kind lives: kind since migration 12, entity_type before.
_KIND_COLUMNS = ("kind", "entity_type")


def display_row_violations_sql(
    entity_columns: set[str],
) -> tuple[str, tuple[str, ...]]:
    """``FROM ... WHERE ...`` selecting every entity that breaks the
    display-row invariant. THE one statement of that invariant.

    **The invariant.** Every entity has an ``entity_display`` row unless it
    is exempt. An entity is exempt when either of these holds:

    - ``is_legacy = 1``: it predates the structural model. The ``sequences``
      counter reserves its number (B4's high-water sweep), not a display
      row. The column is immutable (v2 migration 7), so it cannot mute a
      violation.
    - its kind is in ``NON_SEQUENCE_KINDS``: its identity is not a sequence
      number (a brainstorm's is its file stem), so it has no display row by
      design (Wave 2 D3). The ``entities`` CHECK pairs ``type`` with
      ``kind``, so no single-column write moves a row into such a kind.

    **Soft-deleted rows are not exempt.** ``is_deleted`` is mutable:
    ``delete_entity`` sets it and ``set_deleted`` clears it. As an exemption
    it would be a mute button: soft-deleting a violating row would unblock
    its bucket, the allocator could then issue the number that row still
    holds, and restoring the row would leave two entities with it. A deleted
    entity's number is spent all the same. B8's contract exempted
    ``is_legacy`` alone; its first implementation added ``is_deleted``
    without a stated reason.

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
