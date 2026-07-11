"""Dark-shipped v2 display-id allocator + rename-event helper.

Owns display-identity mutation for v2 (design 121, D5/D6):
``next_display_seq`` (an atomic per-(workspace_uuid, kind) sequence bump
over 118's ``sequences`` table) and ``rename_entity`` (a display-field
UPDATE plus a "renamed"/"lifecycle" event, both in one transaction, via
119's ``append_event``). No DDL of its own — both functions operate on
tables schema_v2.py (``sequences``, ``entities``) and events.py
(``events``) already register; importing this module transitively
registers "events" into ``entity_registry.schema_v2.DDL_REGISTRY`` as a
side effect of its ``entity_registry.events`` import below (the same
mechanism events.py itself uses for "events").

Ships dark: no live v17 code path imports this module, only its own
tests do (mirrors schema_v2.py/events.py, design D1) — feature 132's
cutover decides when a v2 database (and this allocator) comes online.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from entity_registry.events import append_event
from entity_registry.uuid7 import generate_uuid7
from sqlite_retry import with_retry


def next_display_seq(conn: sqlite3.Connection, *, workspace_uuid: str, kind: str) -> int:
    """Return the next display sequence number for (workspace_uuid, kind).

    A bare ``int`` — no ``{seq:03d}-{slug}`` composition here (design
    D7); that continuity is the live ``allocate_entity_id`` MCP tool's
    job (feature 121 D1). Feature 132 seeds ``sequences.current_value``
    per (workspace, kind) from the v1 census before this becomes the
    live path.

    Composes on ``conn.in_transaction`` (design D5), same discipline as
    ``entity_registry.events.append_event``:

    - **True** (caller already opened a transaction, e.g. its own
      ``BEGIN IMMEDIATE``): a bare ``_bump()`` call — no COMMIT or
      ROLLBACK. The caller MUST hold BEGIN IMMEDIATE before calling in
      this mode and owns both atomicity and retry; retrying here
      mid-transaction would replay only a fragment of the caller's
      work. This is a documented precondition, not an enforced one:
      ``conn.in_transaction`` is already True immediately after a bare
      ``BEGIN DEFERRED`` too (before any read), so it cannot
      distinguish a DEFERRED composer from an IMMEDIATE one, and
      sqlite3 exposes no lock-TYPE flag to check instead.
    - **False** (standalone call): BEGIN IMMEDIATE, bump, COMMIT, with
      a guarded ROLLBACK on failure, inside a nested function decorated
      ``@with_retry("sequences")`` and invoked immediately.

    Raw ``COMMIT``/``ROLLBACK`` SQL via ``conn.execute()``, not the
    ``sqlite3.Connection.commit()``/``.rollback()`` convenience methods
    — same autocommit=True / raw-SQL rationale as append_event (those
    convenience methods are no-ops against a transaction opened via raw
    "BEGIN IMMEDIATE" text on an autocommit=True connection).
    """
    if conn.in_transaction:
        return _bump(conn, workspace_uuid, kind)

    @with_retry("sequences")
    def _standalone() -> int:
        conn.execute("BEGIN IMMEDIATE")
        try:
            value = _bump(conn, workspace_uuid, kind)
            conn.execute("COMMIT")
            return value
        except Exception:
            # A transient "locked" failure AT "BEGIN IMMEDIATE" itself
            # never opens a transaction on *conn* — an unguarded
            # "ROLLBACK" here would raise "cannot rollback - no
            # transaction is active", masking the retryable error and
            # defeating with_retry (design D5, mirrors append_event).
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    return _standalone()


def _bump(conn: sqlite3.Connection, workspace_uuid: str, kind: str) -> int:
    """Read-modify-write the (workspace_uuid, kind) row(s) in ``sequences``.

    ``MAX(current_value)`` read + update-ALL-matching-rows write (design
    D5): under BEGIN IMMEDIATE only one writer exists, so at most one
    row per (workspace_uuid, kind) is inserted in practice; if duplicate
    rows exist anyway (FR-4 permits it — no UNIQUE(workspace_uuid, kind)
    index), MAX() keeps issuance monotonic and the UPDATE converges
    every matching row to the new value, self-healing rather than
    forking. No repair machinery.
    """
    row = conn.execute(
        "SELECT MAX(current_value) FROM sequences WHERE workspace_uuid = ? AND kind = ?",
        (workspace_uuid, kind),
    ).fetchone()
    current = row[0] if row and row[0] is not None else None
    if current is None:
        conn.execute(
            "INSERT INTO sequences(uuid, workspace_uuid, kind, current_value) VALUES(?,?,?,1)",
            (generate_uuid7(), workspace_uuid, kind),
        )
        return 1
    next_value = current + 1
    conn.execute(
        "UPDATE sequences SET current_value = ? WHERE workspace_uuid = ? AND kind = ?",
        (next_value, workspace_uuid, kind),
    )
    return next_value


def rename_entity(
    conn: sqlite3.Connection,
    *,
    entity_uuid: str,
    actor: str,
    new_type_id: str | None = None,
    new_name: str | None = None,
) -> str:
    """Rename an entity's type_id and/or display name; return the new event's uuid.

    At least one of *new_type_id*/*new_name* is required — a call
    supplying neither raises ``ValueError`` (nothing to rename). An
    *entity_uuid* not present in ``entities`` also raises ``ValueError``.

    Composes on ``conn.in_transaction``, same lock rules as
    ``next_display_seq`` (design D5/D6): the caller MUST hold BEGIN
    IMMEDIATE to call this in compose mode; a standalone call opens its
    own BEGIN IMMEDIATE, commits, and retries transient failures via
    ``@with_retry("entities")``.

    Inside the transaction: read the current ``type_id``/``name``,
    UPDATE only the supplied field(s) plus ``updated_at``, then append a
    "renamed"/"lifecycle" event via
    ``entity_registry.events.append_event`` — compose mode, since this
    function's own transaction (standalone, or the caller's) is already
    open by the time append_event runs, so append_event never opens or
    closes one of its own here. ``from_value``/``to_value`` carry the
    type_id pair and are both ``None`` when only the name changes;
    ``payload`` carries the ``nameFrom``/``nameTo`` pair and is ``None``
    (SQL NULL) when only the type_id changes — both conditionals are
    explicit so neither branch accidentally inherits the other's shape.

    uuid/FKs/relations stay structurally untouched: the UPDATE lists
    only ``type_id``, ``name``, ``updated_at``.
    """
    if new_type_id is None and new_name is None:
        raise ValueError("rename_entity requires at least one of new_type_id/new_name")
    # A rename may never BLANK a display field (feature 121 FR-5 — the
    # same corruption vector the v1 register/upsert/update guards close;
    # this is the v2 rename path's equivalent, live at the 132 cutover).
    if new_type_id is not None and not new_type_id.strip():
        raise ValueError("rename must not blank display fields (feature 121 FR-5)")
    if new_name is not None and not new_name.strip():
        raise ValueError("rename must not blank display fields (feature 121 FR-5)")

    if conn.in_transaction:
        return _rename(conn, entity_uuid, actor, new_type_id, new_name)

    @with_retry("entities")
    def _standalone() -> str:
        conn.execute("BEGIN IMMEDIATE")
        try:
            event_uuid = _rename(conn, entity_uuid, actor, new_type_id, new_name)
            conn.execute("COMMIT")
            return event_uuid
        except Exception:
            # Same guarded-ROLLBACK rationale as next_display_seq/
            # append_event: an unguarded ROLLBACK when BEGIN IMMEDIATE
            # itself never opened a transaction would mask the real
            # error and defeat with_retry.
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    return _standalone()


def _rename(
    conn: sqlite3.Connection,
    entity_uuid: str,
    actor: str,
    new_type_id: str | None,
    new_name: str | None,
) -> str:
    row = conn.execute(
        "SELECT type_id, name FROM entities WHERE uuid = ?", (entity_uuid,)
    ).fetchone()
    if row is None:
        raise ValueError(f"no entity with uuid {entity_uuid!r}")
    old_type_id, old_name = row

    set_parts: list[str] = []
    params: list[str] = []
    if new_type_id is not None:
        set_parts.append("type_id = ?")
        params.append(new_type_id)
    if new_name is not None:
        set_parts.append("name = ?")
        params.append(new_name)
    set_parts.append("updated_at = ?")
    params.append(datetime.now(timezone.utc).isoformat())
    params.append(entity_uuid)

    conn.execute(
        f"UPDATE entities SET {', '.join(set_parts)} WHERE uuid = ?", params,
    )

    return append_event(
        conn,
        entity_uuid=entity_uuid,
        event_type="renamed",
        axis="lifecycle",
        from_value=(old_type_id if new_type_id is not None else None),
        to_value=new_type_id,
        actor=actor,
        payload=(
            {"nameFrom": old_name, "nameTo": new_name}
            if new_name is not None
            else None
        ),
    )
