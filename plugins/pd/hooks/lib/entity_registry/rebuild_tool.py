"""Feature 132 — the v1->v2 entity-registry rebuild tool (Scope model, D1).

Owns the NEW committed rebuild tool the spec names (not the pre-existing
v1 ``entity_registry/backfill.py`` — a different artifact). Builds the
new database file via three ordered steps design D1 pins, so the union
DDL is derived BY CONSTRUCTION rather than hand-copied:

1. **Chain replay** (:func:`_replay_v1_chain`) — construct an
   ``EntityDatabase`` against the (nonexistent) staging path, which
   unconditionally runs the full v1 migration chain, then close it. No
   hand-rolled replay loop — this IS the sanctioned initial use of
   ``_migrate()`` that the FR132-1 generation guard carves out (it runs
   BEFORE step 3's stamp, so the guard is a no-op here).
2. **Selective v2 seed** (:func:`_seed_v2_schema`) — one raw
   ``sqlite3.connect`` on the SAME file. Importing events/views/axes
   registers their DDL into ``schema_v2.DDL_REGISTRY`` (module-import
   side effect); ``axes.register_vocab_ddl()`` is called explicitly
   (register-on-demand, never at import). The four registry entries for
   owners ``events``/``views``/``axes``/``axes_vocab_triggers`` are then
   applied in ONE transaction — NOT the ``core`` owner (step 1 already
   built those chain-shaped tables, ``_metadata`` included) and NOT
   ``bootstrap_v2()`` wholesale (its ``IF NOT EXISTS`` replay would
   silently skip chain-shaped tables). D7b's ``events_no_replace`` guard
   trigger ships inside the ``events`` owner's own DDL (events.py) — no
   standalone register call exists for it.
3. **Generation stamp** (:func:`_stamp_v2_generation`) — same
   connection, upserts ``schema_generation='v2'`` + ``schema_version``
   via the shared ``database._upsert_metadata`` helper (#062: ON
   CONFLICT DO UPDATE, not INSERT OR IGNORE).

Task 1 slice: build steps only. ``--staging-only`` is the ONLY supported
CLI mode until feature 132 task 2 adds the backfill/report/cutover
machinery — :func:`main` without it reports "not yet implemented" and
exits non-zero. H5 (spec Hazards): this module runs only when invoked —
nothing here executes at import time.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Side-effect imports: importing each registers its DDL into
# schema_v2.DDL_REGISTRY (module-top code in each sibling). Listed
# explicitly for clarity even though axes.py's own chain
# (events -> views -> axes) would register all three via `axes` alone.
from entity_registry import events  # noqa: F401
from entity_registry import views  # noqa: F401
from entity_registry import axes
from entity_registry import database
from entity_registry import schema_v2

# D1 step 2: the four registry owners this tool seeds onto the v1
# chain-shaped file. "core" is deliberately excluded — step 1's chain
# replay already built those tables (including _metadata).
_V2_SEED_OWNERS = frozenset({"events", "views", "axes", "axes_vocab_triggers"})

# Same default remediate_m12.py uses for the live entities.db.
_DEFAULT_LIVE_DB_PATH = str(Path.home() / ".claude" / "pd" / "entities" / "entities.db")


def _replay_v1_chain(staging_path: str) -> None:
    """D1 step 1: the sanctioned initial ``_migrate()`` use.

    Constructing ``EntityDatabase`` against a fresh path unconditionally
    runs the full v1 migration chain (``__init__`` -> ``_migrate()``);
    this closes it immediately after. No hand-rolled replay loop.
    """
    db = database.EntityDatabase(staging_path)
    db.close()


def _seed_v2_schema(conn: sqlite3.Connection) -> None:
    """D1 step 2: selectively seed the v2 event core, in one transaction.

    *conn* must already have ``PRAGMA foreign_keys = ON`` set (a raw
    connection defaults OFF). Guards ``register_vocab_ddl()`` with
    ``is_vocab_registered()`` first (axes.py's own re-entry guidance for
    "callers that may re-enter") so building more than one staging
    database in the same process is safe.
    """
    if not axes.is_vocab_registered():
        axes.register_vocab_ddl()

    # Raw "BEGIN IMMEDIATE"/"COMMIT"/"ROLLBACK" SQL text, not
    # conn.commit()/.rollback(): on an autocommit=True connection those
    # convenience methods are no-ops against a transaction opened via raw
    # "BEGIN IMMEDIATE" text — verified empirically (mirrors
    # events.append_event's _insert_standalone, same finding documented
    # in its docstring).
    conn.execute("BEGIN IMMEDIATE")
    try:
        for owner, sql_script in schema_v2.DDL_REGISTRY:
            if owner in _V2_SEED_OWNERS:
                conn.executescript(sql_script)
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def _stamp_v2_generation(conn: sqlite3.Connection) -> None:
    """D1 step 3: stamp the generation marker + version (#062 upsert)."""
    database._upsert_metadata(conn, "schema_generation", "v2")
    database._upsert_metadata(
        conn, "schema_version", str(schema_v2.V2_SCHEMA_VERSION)
    )


def build_staging_database(staging_path: str) -> None:
    """Run D1's three build steps against *staging_path*.

    *staging_path* should not already exist — :func:`main`'s
    ``--staging-only`` path enforces that; this function does not
    special-case re-entry (it happens to be idempotent-safe regardless:
    a v2-stamped file re-run through this is a no-op, per the FR132-1
    guard plus this function's own IF-NOT-EXISTS/upsert DDL).
    """
    _replay_v1_chain(staging_path)

    conn = sqlite3.connect(staging_path, autocommit=True)
    try:
        # PRAGMA discipline (mirrors schema_v2.bootstrap_v2/events.connect_v2):
        # busy_timeout and foreign_keys are per-connection and non-persistent
        # — every fresh connection re-issues them BEFORE any transaction
        # opens (foreign_keys is a silent no-op if set mid-transaction).
        conn.execute(f"PRAGMA busy_timeout = {schema_v2._BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA foreign_keys = ON")
        _seed_v2_schema(conn)
        _stamp_v2_generation(conn)
    finally:
        conn.close()


def default_staging_path(live_db_path: str) -> str:
    """D1: ``<dir>/entities.db.rebuild-<yyyymmdd>`` beside *live_db_path*."""
    live = Path(live_db_path)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return str(live.parent / f"{live.name}.rebuild-{today}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the v2-generation entities.db (feature 132).",
    )
    parser.add_argument(
        "--db",
        default=_DEFAULT_LIVE_DB_PATH,
        help="Path to the LIVE v1 entities.db the staging path is derived "
        "beside (default: ~/.claude/pd/entities/entities.db). This tool "
        "never opens it directly.",
    )
    parser.add_argument(
        "--staging-path",
        default=None,
        help="Override the computed staging path (primarily for tests).",
    )
    parser.add_argument(
        "--staging-only",
        action="store_true",
        help="Run build steps 1-3 only (chain replay + v2 seed + "
        "generation stamp) — no backfill/cutover. The only supported "
        "mode until feature 132 task 2 lands.",
    )
    args = parser.parse_args(argv)

    staging_path = args.staging_path or default_staging_path(args.db)
    if Path(staging_path).exists():
        print(f"Staging file already exists: {staging_path}", file=sys.stderr)
        return 1

    if not args.staging_only:
        print(
            "Full backfill+cutover is not implemented yet (feature 132 "
            "task 2+). Re-run with --staging-only.",
            file=sys.stderr,
        )
        return 2

    build_staging_database(staging_path)
    print(f"Staging database built: {staging_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
