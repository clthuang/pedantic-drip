"""Dark-shipped v2 entity schema: core DDL, extension registry, bootstrap.

Owns everything v2 (design 118, D1/D3/D4): the schema version constant, the
uuid7-keyed core DDL, an ordered registry siblings extend, and
``bootstrap_v2()`` to apply it. Ships dark: no live v17 code path imports
this module, only its own tests do. The v17 ``EntityDatabase`` in
``database.py`` is untouched — feature 132's cutover decides how and when
a v2 database comes online.
"""
from __future__ import annotations

import sqlite3

V2_SCHEMA_VERSION = 1

# Per-connection, non-persistent (SQLite resets it on every new connection).
# Matches the v17 EntityDatabase._set_pragmas() value (database.py) for
# consistency across the two schema generations.
_BUSY_TIMEOUT_MS = 15000

# v2 core DDL (design 118, D3). All statements are IF NOT EXISTS. No state
# columns on entities and no allowlist table — state is events (119)
# projected via views (120); FR-9 removes cross-workspace allowlisting.
_CORE_DDL = """
CREATE TABLE IF NOT EXISTS _metadata (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
-- schema_version is written exactly once, by bootstrap_v2 (idempotent
-- insert-or-ignore) — the sole version write site [FR-12: ONE version location].
-- Deliberately NOT spelled as SQL here: test #5's source scan counts
-- executable write statements and must not match comment text.

CREATE TABLE IF NOT EXISTS workspaces (
  uuid         TEXT PRIMARY KEY,      -- uuid7
  project_root TEXT,                  -- resolution input (FR-9); project_id_legacy does NOT survive (FR-12)
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
  uuid            TEXT PRIMARY KEY,   -- uuid7
  workspace_uuid  TEXT NOT NULL REFERENCES workspaces(uuid),
  type            TEXT NOT NULL,      -- feature-109 polymorphic taxonomy carries over
  kind            TEXT NOT NULL,
  lifecycle_class TEXT NOT NULL,
  type_id         TEXT,               -- human-readable; NOT unique (FR-4)
  name            TEXT,               -- display; NOT unique
  artifact_path   TEXT,
  parent_uuid     TEXT REFERENCES entities(uuid),
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  metadata        TEXT                -- JSON
);
-- NO status / workflow_phase / pipeline_phase / execution_status columns:
-- state is events (119) projected via views (120) on the two axes (122).

CREATE TABLE IF NOT EXISTS entity_relations (
  uuid       TEXT PRIMARY KEY,        -- uuid7 (v17 used INTEGER id — FR-4 violation, fixed)
  from_uuid  TEXT NOT NULL REFERENCES entities(uuid) ON DELETE CASCADE,
  to_uuid    TEXT NOT NULL REFERENCES entities(uuid) ON DELETE CASCADE,
  kind       TEXT NOT NULL,           -- vocabulary CHECK deferred to 124 (owns `blocks` semantics)
  created_at TEXT NOT NULL
);
-- Carried over from v17 (database.py:4964-4967, :4971): ON DELETE CASCADE (dangling
-- relation rows serve nothing) and the structural dedup guard below — uuid+uuid+enum
-- is NOT a human-readable business key, so FR-4's no-uniqueness rule does not apply.
CREATE UNIQUE INDEX IF NOT EXISTS idx_relations_dedup
  ON entity_relations(from_uuid, to_uuid, kind);

CREATE TABLE IF NOT EXISTS sequences (
  uuid           TEXT PRIMARY KEY,    -- uuid7 (v17 PK was composite (workspace_uuid, entity_type) — business key, dropped)
  workspace_uuid TEXT NOT NULL REFERENCES workspaces(uuid),
  kind           TEXT NOT NULL,
  current_value  INTEGER NOT NULL DEFAULT 0
);

-- Non-unique lookup indexes (UNIQUE forbidden on human-readable fields; plain INDEX is not):
CREATE INDEX IF NOT EXISTS idx_entities_workspace ON entities(workspace_uuid);
CREATE INDEX IF NOT EXISTS idx_entities_type_id   ON entities(type_id);
CREATE INDEX IF NOT EXISTS idx_relations_from     ON entity_relations(from_uuid);
CREATE INDEX IF NOT EXISTS idx_relations_to       ON entity_relations(to_uuid);
CREATE INDEX IF NOT EXISTS idx_sequences_ws_kind  ON sequences(workspace_uuid, kind);
"""

# (owner_name, sql_script) pairs, applied by bootstrap_v2 in order.
DDL_REGISTRY: list[tuple[str, str]] = [("core", _CORE_DDL)]


def register_ddl(owner: str, sql_script: str) -> None:
    """Append *sql_script* to DDL_REGISTRY under *owner*.

    The registry is INPUT to bootstrap_v2, not a migration log it
    maintains: siblings (119 events, 120 views, 122 CHECK rewrites) call
    this at import time, BEFORE bootstrap_v2 runs, so their DDL is present
    when bootstrap replays the registry in order.

    Raises ValueError if *owner* is already registered — a double
    registration is a wiring mistake (e.g. a module imported twice under
    different paths), and IF NOT EXISTS would otherwise mask it silently.
    """
    if any(registered_owner == owner for registered_owner, _ in DDL_REGISTRY):
        raise ValueError(f"DDL owner {owner!r} is already registered")
    DDL_REGISTRY.append((owner, sql_script))


def bootstrap_v2(db_path: str) -> sqlite3.Connection:
    """Apply every registered DDL entry to *db_path* and return the open connection.

    DDL_REGISTRY is INPUT to this function: bootstrap_v2 replays whatever
    is registered at call time, in registration order — it does not track
    "what's already applied" separately from the registry itself.

    *db_path* is REQUIRED — there is no production default, so a stray
    import or test cannot create the real v2 database ahead of feature
    132's cutover deciding where it lives.

    Idempotent by construction, not by state: every statement in the
    registered DDL is guarded by IF NOT EXISTS, and the one write this
    function makes against the version table uses the same guard, so
    re-running bootstrap_v2 is a safe no-op — there's no separate "already
    ran" flag that could fall out of sync with the schema it describes.

    Convergent, not atomic: each registry entry is applied via its own
    executescript() call, which commits as it goes. A failure partway
    through leaves the entries before it applied and the entries from it
    onward not applied. That partial state recovers safely under the
    idempotency contract above — calling bootstrap_v2 again converges,
    because the already-applied prefix is skipped rather than repeated.

    PRAGMA discipline: busy_timeout, journal_mode=WAL, and foreign_keys=ON
    are all issued on a FRESH autocommit=True connection before any
    statement opens a transaction — foreign_keys is a silent no-op if set
    mid-transaction. Both settings are per-connection and non-persistent:
    a future v2 connection factory (119+) MUST re-issue foreign_keys AND
    busy_timeout itself; neither carries over from this connection to a
    caller's own.

    Returns the open, PRAGMA-configured connection instead of closing it —
    the caller is responsible for closing it. This lets tests assert the
    actual PRAGMA state on the very connection that did the work (a fresh
    connection would only show SQLite's defaults, not what bootstrap set
    up) and gives future callers (119+) a connection that's already ready.
    """
    conn = sqlite3.connect(db_path, autocommit=True)

    # busy_timeout first — journal_mode=WAL requires a write that can be
    # blocked by a concurrent connection during init (matches v17's
    # EntityDatabase._set_pragmas ordering in database.py).
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    for _owner, sql_script in DDL_REGISTRY:
        conn.executescript(sql_script)

    conn.execute(
        "INSERT OR IGNORE INTO _metadata (key, value) VALUES (?, ?)",
        ("schema_version", str(V2_SCHEMA_VERSION)),
    )

    return conn
