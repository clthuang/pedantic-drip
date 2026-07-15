"""Dark-shipped v2 event log: the ``events`` table + append/read API.

Owns everything event-log-shaped for v2 (design 119, D4/D7): DDL
registration for the ``events`` table (immutable via BEFORE UPDATE/DELETE
triggers, plus a BEFORE INSERT uuid-collision guard against
``INSERT OR REPLACE`` — feature 132 design D7b, FR132-7), ``connect_v2``
(a v2 connection factory carrying the full PRAGMA contract),
``append_event``, and ``read_events``. Ships dark: no live v17 code path
imports this module, only its own tests do (mirrors schema_v2.py, design
D1) — feature 132's cutover decides when a v2 database (and this event
log) comes online.

Importing this module registers "events" into
``entity_registry.schema_v2.DDL_REGISTRY`` as a side effect (module top,
below). A consumer that calls ``bootstrap_v2`` WITHOUT having imported
this module first gets a core-only database — acceptable in the dark
phase; feature 132 owns the canonical "import every DDL owner, then
bootstrap" entrypoint.

FR-11 payload key registry (prose contract only — design D2; the actual
validating consumer is ``entity_registry.meta_projection`` (feature 126),
not this module):
  - ``iterations``        camelCase — PRD FR-11 / .meta.json projection contract
  - ``reviewerNotes``     camelCase — PRD FR-11 / .meta.json projection contract
                          (NOT the same thing as the v1 DB column
                          ``reviewer_notes``)
  - ``skippedPhases``     camelCase — PRD FR-11 / .meta.json projection contract
  - ``mode``              camelCase — PRD FR-11 / .meta.json projection contract
  - ``branch``            camelCase — PRD FR-11 / .meta.json projection contract
  - ``brainstorm_source`` snake_case — matches live .meta.json
  - ``backlog_source``    snake_case — matches live .meta.json
  - ``nameFrom``          camelCase — feature 121 D6 rename event payload
                          (entity_registry.display.rename_entity; NOT an
                          FR-11/.meta.json key)
  - ``nameTo``            camelCase — feature 121 D6 rename event payload
                          (entity_registry.display.rename_entity; NOT an
                          FR-11/.meta.json key)
  - ``phaseSummaryEntry`` camelCase (payload side) — PRD FR-11 /
                          .meta.json projection contract (feature 126,
                          feature 075 origin); ONE dict per
                          `phase_completed` event, ACCUMULATED by
                          entity_registry.meta_projection into the
                          FILE-side key ``phase_summaries`` (snake_case,
                          PLURAL — not the same spelling as the payload
                          key)
  - ``backwardContext``   camelCase (payload side) — PRD FR-11 /
                          .meta.json projection contract (feature 126,
                          feature 073 origin); projected by
                          entity_registry.meta_projection to the
                          FILE-side key ``backward_context`` (snake_case
                          — not the same spelling as the payload key)
  - ``backwardReturnTarget`` camelCase (payload side) — PRD FR-11 /
                          .meta.json projection contract (feature 126,
                          feature 073 origin); projected by
                          entity_registry.meta_projection to the
                          FILE-side key ``backward_return_target``
                          (snake_case — not the same spelling as the
                          payload key)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from entity_registry import schema_v2
from entity_registry.uuid7 import generate_uuid7
from sqlite_retry import with_retry

# events DDL (design 119, D7 — verbatim, plus feature 132 D7b's
# events_no_replace trigger appended below). No `created_at` besides
# `timestamp` (one time column; v1 phase_events' separate created_at
# duplicated it). No `source` column (v1 had live/backfill — v2 encodes
# provenance in `actor`, e.g. "backfill:132"; one mechanism, not two).
_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS events (
  uuid        TEXT PRIMARY KEY,
  entity_uuid TEXT NOT NULL REFERENCES entities(uuid),
  event_type  TEXT NOT NULL CHECK(length(event_type) > 0),
  axis        TEXT NOT NULL CHECK(axis IN ('pipeline','execution','lifecycle')),
  from_value  TEXT,
  to_value    TEXT,
  actor       TEXT NOT NULL CHECK(length(actor) > 0),
  timestamp   TEXT NOT NULL,
  payload     TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_entity_axis ON events(entity_uuid, axis);
CREATE INDEX IF NOT EXISTS idx_events_timestamp   ON events(timestamp);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events rows are immutable (PRD NFR-4)'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events rows are immutable (PRD NFR-4)'); END;
CREATE TRIGGER IF NOT EXISTS events_no_replace BEFORE INSERT ON events
WHEN EXISTS(SELECT 1 FROM events WHERE uuid = NEW.uuid)
BEGIN SELECT RAISE(ABORT, 'events rows are immutable (PRD NFR-4)'); END;
"""

schema_v2.register_ddl("events", _EVENTS_DDL)


def connect_v2(db_path: str) -> sqlite3.Connection:
    """Open a v2 connection with the full PRAGMA contract re-issued.

    PRAGMAs are per-connection and never carry over from whatever
    connection ``bootstrap_v2`` used to build the schema — every v2
    connection, this one included, must set its own (design D5). Same
    order bootstrap_v2 uses (busy_timeout first, since journal_mode=WAL
    requires a write that a concurrent connection could block during
    init): busy_timeout (``schema_v2._BUSY_TIMEOUT_MS``, the same
    constant bootstrap_v2 uses) -> journal_mode=WAL -> foreign_keys=ON.
    """
    conn = sqlite3.connect(db_path, autocommit=True)
    conn.execute(f"PRAGMA busy_timeout = {schema_v2._BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


_INSERT_EVENT_SQL = (
    "INSERT INTO events "
    "(uuid, entity_uuid, event_type, axis, from_value, to_value, actor, timestamp, payload) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_SELECT_EVENTS_SQL = (
    "SELECT uuid, entity_uuid, event_type, axis, from_value, to_value, actor, timestamp, payload "
    "FROM events WHERE entity_uuid = ? ORDER BY uuid"
)

_SELECT_EVENTS_BY_AXIS_SQL = (
    "SELECT uuid, entity_uuid, event_type, axis, from_value, to_value, actor, timestamp, payload "
    "FROM events WHERE entity_uuid = ? AND axis = ? ORDER BY uuid"
)

# Column order for the two SELECT statements above, kept as one tuple so
# read_events' row->dict labeling can't silently drift out of sync with
# either SELECT's column list.
_EVENT_COLUMNS = (
    "uuid", "entity_uuid", "event_type", "axis",
    "from_value", "to_value", "actor", "timestamp", "payload",
)


def _row_to_event(row: tuple) -> dict:
    event = dict(zip(_EVENT_COLUMNS, row))
    event["payload"] = json.loads(event["payload"]) if event["payload"] is not None else None
    return event


def append_event(
    conn: sqlite3.Connection,
    *,
    entity_uuid: str,
    event_type: str,
    axis: str,
    from_value: str | None = None,
    to_value: str | None = None,
    actor: str,
    payload: dict | None = None,
    timestamp: str | None = None,
) -> str:
    """Append one immutable event row; return its newly minted uuid7.

    ``conn`` MUST come from ``connect_v2`` — FK enforcement
    (``foreign_keys=ON``) is per-connection; a bare ``sqlite3.connect``
    silently disables the entity_uuid FK check. Enforced at entry: a
    connection reporting ``foreign_keys`` off raises ``ValueError``
    before any write, on either transaction path (backlog #061). The
    guard trusts the connection's own PRAGMA self-report — it defends
    against ACCIDENTAL bare connections, not an adversarial proxy that
    lies about the pragma (raw INSERT is the equal-effort documented
    residual either way; see the preserved orphan pin in test_events).

    Composes on ``conn.in_transaction`` (design D5):

    - **True** (caller already opened a transaction, e.g. its own
      ``BEGIN IMMEDIATE``): a bare parameterized INSERT — no COMMIT or
      ROLLBACK. The caller owns both atomicity and retry; retrying here
      mid-transaction would replay only a fragment of the caller's work.
    - **False** (standalone call): the attempt — BEGIN IMMEDIATE, INSERT,
      COMMIT, with a guarded ROLLBACK on failure — runs inside a nested
      function decorated ``@with_retry("events")`` and is invoked
      immediately.

    ``json.dumps(payload)`` (None → SQL NULL, never TEXT 'null') runs
    before any WRITE on both paths — only the read-only #061 PRAGMA
    probe above precedes it: a non-serializable *payload* (e.g. a set)
    raises ``TypeError`` with no transaction ever opened, on either
    path (and the guard fires even earlier — pinned by test).

    The standalone path issues COMMIT/ROLLBACK as raw SQL via
    ``conn.execute()``, not the ``sqlite3.Connection.commit()`` /
    ``.rollback()`` convenience methods: on an ``autocommit=True``
    connection (connect_v2), those methods are no-ops against a
    transaction that was opened by executing "BEGIN IMMEDIATE" as raw SQL
    text — verified empirically (CPython 3.14's autocommit mode only
    wires ``.commit()``/``.rollback()`` to transactions it opened
    implicitly itself). Raw "COMMIT"/"ROLLBACK" text acts on the real
    SQLite-level transaction regardless of who opened it, and still
    raises "cannot rollback - no transaction is active" if issued with
    none open — so the ``if conn.in_transaction:`` guard below stays
    load-bearing.
    """
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    if row is None or row[0] != 1:
        raise ValueError(
            "append_event requires a connect_v2 connection "
            "(PRAGMA foreign_keys=ON is per-connection; a bare sqlite3.connect "
            "would write orphan-capable rows into the immutable events table — backlog #061)"
        )

    # None binds SQL NULL (not the 4-char TEXT 'null') so the immutable log
    # carries ONE representation of "no payload" — SQL-level consumers
    # (120 projections, 132 backfill) can trust IS NULL semantics.
    payload_json = json.dumps(payload) if payload is not None else None
    event_uuid = generate_uuid7()
    event_timestamp = (
        timestamp if timestamp is not None else datetime.now(timezone.utc).isoformat()
    )
    params = (
        event_uuid,
        entity_uuid,
        event_type,
        axis,
        from_value,
        to_value,
        actor,
        event_timestamp,
        payload_json,
    )

    if conn.in_transaction:
        conn.execute(_INSERT_EVENT_SQL, params)
        return event_uuid

    @with_retry("events")
    def _insert_standalone() -> None:
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(_INSERT_EVENT_SQL, params)
            conn.execute("COMMIT")
        except Exception:
            # A transient "locked" failure AT "BEGIN IMMEDIATE" itself
            # never opens a transaction on *conn* — an unguarded
            # "ROLLBACK" here would raise "cannot rollback - no
            # transaction is active", masking the retryable error and
            # defeating with_retry (design D5).
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    _insert_standalone()
    return event_uuid


def read_events(
    conn: sqlite3.Connection, entity_uuid: str, *, axis: str | None = None
) -> list[dict]:
    """Return every event row for *entity_uuid*, oldest first.

    ``conn`` MUST come from ``connect_v2`` — FK enforcement
    (``foreign_keys=ON``) is per-connection; a bare ``sqlite3.connect``
    silently disables the entity_uuid FK check.

    ORDER BY uuid: uuid7 is time-ordered (RFC 9562), so ascending uuid
    order already agrees with insertion order — no separate sequence
    column is needed. Both query shapes lead with ``entity_uuid = ?``,
    using ``idx_events_entity_axis``'s leading column; supplying *axis*
    additionally uses the index's second column.
    """
    if axis is None:
        rows = conn.execute(_SELECT_EVENTS_SQL, (entity_uuid,)).fetchall()
    else:
        rows = conn.execute(_SELECT_EVENTS_BY_AXIS_SQL, (entity_uuid, axis)).fetchall()
    return [_row_to_event(row) for row in rows]
