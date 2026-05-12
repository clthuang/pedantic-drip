"""Migration safety tests for feature 109 (migration 12).

Scope:
  - ``test_v12_stub_has_fk_check`` (Task 0.2 DoD): asserts the migration-12
    function contains an in-transaction ``PRAGMA foreign_key_check`` between
    ``BEGIN IMMEDIATE`` and the schema_version stamp. This gates the FK-check
    safety property from commit 0.2 onwards — any future Group filling in
    migration body cannot accidentally remove the in-tx check without
    failing this test.
  - ``test_collision_audit_detects_backlog_feature_collisions`` (Task 1.1 DoD,
    AC-1.10): asserts the migration emits a one-line INFO log per pre-flight
    backlog/feature numeric-suffix collision but does not abort the migration.
  - ``test_migration_12_cleans_malformed_feature_row`` (Task 1.3 DoD, AC-5.3):
    asserts the migration removes the known malformed ``workflow_phases`` row
    with ``type_id='feature:'`` and emits an INFO log entry to stderr.

Group 16 additions:
  - ``test_migration_12_end_to_end`` (Task 16.4): exercises the full forward
    migration against a v11 baseline and verifies all expected schema state
    plus FK cleanliness.
  - ``test_migration_12_idempotent`` (Task 16.4a, AC-5.2): re-running
    migration 12 on a v12 database is a no-op with zero schema drift.
  - ``test_migration_12_lock_failure`` (Task 16.4b, AC-5.4 + AC-2.5): when
    another connection holds an exclusive lock, the migration raises
    OperationalError rather than silently swallowing it.
  - ``test_migration_12_down`` (Task 16.5b, AC-5.1): the down migration
    restores runtime v11 schema state (entity_type column, immutable
    triggers, narrowed phase_events CHECK, NULL-able phase removed).
"""
from __future__ import annotations

import inspect
import sqlite3
import tempfile
import threading
import time
import uuid as _uuid
from pathlib import Path

import pytest

from entity_registry.database import (
    MIGRATIONS,
    MIGRATIONS_DOWN,
    _migration_12_polymorphic_taxonomy_and_events,
)
from entity_registry.test_helpers import make_v11_db, make_v12_db


def test_v12_stub_has_fk_check() -> None:
    """Migration 12 must contain in-transaction ``PRAGMA foreign_key_check``
    between ``BEGIN IMMEDIATE`` and the ``schema_version`` stamp.

    This is the binary safety assertion required by Task 0.2 DoD. Source-based
    (``inspect.getsource``) rather than runtime-based so it remains robust
    against future Groups adding body steps — as long as the FK-check stays
    between the transaction begin and the version stamp, the test passes.
    """
    source = inspect.getsource(_migration_12_polymorphic_taxonomy_and_events)

    begin_idx = source.find('BEGIN IMMEDIATE')
    stamp_idx = source.find("'schema_version', '12'")
    fk_idx = source.find('PRAGMA foreign_key_check')

    assert begin_idx >= 0, (
        "Migration 12 source must contain 'BEGIN IMMEDIATE'"
    )
    assert stamp_idx >= 0, (
        "Migration 12 source must contain the schema_version=12 stamp"
    )
    assert fk_idx >= 0, (
        "Migration 12 source must contain 'PRAGMA foreign_key_check'"
    )

    # There may be multiple PRAGMA foreign_key_check occurrences (pre-tx and
    # in-tx); we need to find at least one between BEGIN IMMEDIATE and the
    # schema_version stamp.
    cursor = begin_idx
    in_tx_fk_idx = -1
    while True:
        nxt = source.find('PRAGMA foreign_key_check', cursor + 1)
        if nxt == -1 or nxt > stamp_idx:
            break
        if nxt > begin_idx and nxt < stamp_idx:
            in_tx_fk_idx = nxt
        cursor = nxt

    assert in_tx_fk_idx > begin_idx and in_tx_fk_idx < stamp_idx, (
        "Migration 12 must contain an in-transaction "
        "'PRAGMA foreign_key_check' between BEGIN IMMEDIATE and the "
        "schema_version=12 stamp (critical safety from day 1)."
    )


# ---------------------------------------------------------------------------
# Group 1 helpers
# ---------------------------------------------------------------------------


def _bootstrap_workspace(conn: sqlite3.Connection, legacy_id: str = "__test__") -> str:
    """Insert a synthetic ``workspaces`` row and return its uuid.

    Used by Group 1 tests that build their own v11 connection directly via
    :func:`make_v11_db` (no EntityDatabase wrapper). Mirrors the
    test_helpers ``bootstrap_test_workspace`` flow but operates on a raw
    sqlite3.Connection.
    """
    ws_uuid = str(_uuid.uuid4())
    now = "2026-05-12T00:00:00Z"
    conn.execute(
        "INSERT OR IGNORE INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws_uuid, legacy_id, None, now, now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT uuid FROM workspaces WHERE project_id_legacy = ?",
        (legacy_id,),
    ).fetchone()
    return row["uuid"]


def _insert_v11_entity(
    conn: sqlite3.Connection,
    *,
    ws_uuid: str,
    entity_type: str,
    entity_id: str,
    name: str = "synthetic",
) -> str:
    """Insert a synthetic v11 ``entities`` row directly (bypass register_entity).

    Returns the new uuid. Used to set up collision fixtures / unmapped-type
    rows without going through the validating API surface.
    """
    type_id = f"{entity_type}:{entity_id}"
    entity_uuid = str(_uuid.uuid4())
    now = "2026-05-12T00:00:00Z"
    conn.execute(
        "INSERT INTO entities "
        "(uuid, workspace_uuid, type_id, entity_type, entity_id, name, "
        "status, parent_uuid, artifact_path, created_at, updated_at, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (entity_uuid, ws_uuid, type_id, entity_type, entity_id, name,
         None, None, None, now, now, None),
    )
    conn.commit()
    return entity_uuid


# ---------------------------------------------------------------------------
# Group 1: Pre-flight collision audit (Task 1.1) + AC-5.3 cleanup (Task 1.3)
# ---------------------------------------------------------------------------


def test_collision_audit_detects_backlog_feature_collisions(capsys) -> None:
    """AC-1.10: migration 12 logs an INFO line per backlog/feature numeric-
    suffix collision but does NOT abort.

    Setup:
      - Build v11 DB.
      - Bootstrap a workspace.
      - Insert ``backlog:42`` and ``feature:42`` rows sharing that workspace.

    Run migration 12.

    Assert:
      - Migration completes (no exception, schema_version stamped to 12).
      - stderr contains exactly one INFO collision line referencing the shared
        workspace_uuid and suffix ``42``.
    """
    conn = make_v11_db()
    ws_uuid = _bootstrap_workspace(conn)
    _insert_v11_entity(
        conn, ws_uuid=ws_uuid, entity_type="backlog", entity_id="42"
    )
    _insert_v11_entity(
        conn, ws_uuid=ws_uuid, entity_type="feature", entity_id="42"
    )

    # Sanity: confirm both rows exist pre-migration.
    pre_count = conn.execute(
        "SELECT COUNT(*) FROM entities WHERE type_id IN ('backlog:42','feature:42')"
    ).fetchone()[0]
    assert pre_count == 2

    # Run migration 12 directly against the v11 connection.
    _migration_12_polymorphic_taxonomy_and_events(conn)

    err = capsys.readouterr().err
    info_lines = [
        line for line in err.splitlines()
        if line.startswith("INFO: Migration 12 pre-flight collision")
    ]
    assert len(info_lines) == 1, (
        f"Expected exactly one collision INFO line in stderr, got {info_lines!r}"
    )
    # The audit log must reference the shared workspace and the suffix '42'.
    assert ws_uuid in info_lines[0]
    assert "42" in info_lines[0]

    # Schema version must have advanced to 12 (non-blocking audit).
    v = conn.execute(
        "SELECT value FROM _metadata WHERE key='schema_version'"
    ).fetchone()
    assert v is not None and v[0] == "12"


def test_migration_12_cleans_malformed_feature_row(capsys) -> None:
    """AC-5.3 (Task 1.3): migration 12 removes the malformed
    ``workflow_phases`` row with ``type_id='feature:'`` and emits a one-line
    INFO log entry to stderr.

    Setup:
      - Build v11 DB.
      - Insert synthetic ``workflow_phases`` row with ``type_id='feature:'``.

    Run migration 12.

    Assert:
      - ``SELECT COUNT(*) FROM workflow_phases WHERE type_id='feature:'`` == 0.
      - stderr contains the AC-5.3 INFO line.
    """
    conn = make_v11_db()
    # The malformed row in the live DB has type_id='feature:' (empty after
    # colon). At v11, workflow_phases has a ``wp_reject_orphaned_insert``
    # BEFORE-INSERT trigger that raises if no matching entity exists AND
    # workspace_uuid is NULL. We bypass the trigger by supplying a synthetic
    # workspace_uuid (matches a real workspaces row to keep the FK valid).
    ws_uuid = _bootstrap_workspace(conn)
    now = "2026-05-12T00:00:00Z"
    conn.execute(
        "INSERT INTO workflow_phases (type_id, updated_at, workspace_uuid) "
        "VALUES (?, ?, ?)",
        ("feature:", now, ws_uuid),
    )
    conn.commit()
    pre = conn.execute(
        "SELECT COUNT(*) FROM workflow_phases WHERE type_id = 'feature:'"
    ).fetchone()[0]
    assert pre == 1

    _migration_12_polymorphic_taxonomy_and_events(conn)

    post = conn.execute(
        "SELECT COUNT(*) FROM workflow_phases WHERE type_id = 'feature:'"
    ).fetchone()[0]
    assert post == 0, (
        "Migration 12 must remove the malformed workflow_phases row "
        "(type_id='feature:') per AC-5.3"
    )

    err = capsys.readouterr().err
    matching = [
        line for line in err.splitlines()
        if line.startswith(
            "INFO: Migration 12 removed malformed workflow_phases row: feature:"
        )
    ]
    assert len(matching) == 1, (
        f"Expected exactly one AC-5.3 cleanup INFO line, got {matching!r}"
    )


# ---------------------------------------------------------------------------
# Group 16: end-to-end migration verification
# ---------------------------------------------------------------------------


def test_migration_12_end_to_end() -> None:
    """Task 16.4: full forward migration verification on a v11 baseline.

    Assert:
      - schema_version stamped to '12'
      - 3 new columns (type, kind, lifecycle_class) present on entities
      - legacy entity_type column ABSENT
      - phase_events.event_type CHECK accepts all 7 values
      - phase_events.phase is nullable (NOT NULL relaxed)
      - phase_events has metadata column
      - Both immutable triggers absent from sqlite_master
      - entities_fts has `kind` (not `entity_type`) in column list
      - idx_entities_type_kind index exists
      - FK check clean (no violations)
    """
    conn = make_v11_db()
    _migration_12_polymorphic_taxonomy_and_events(conn)

    # schema_version stamped
    v = conn.execute(
        "SELECT value FROM _metadata WHERE key='schema_version'"
    ).fetchone()
    assert v is not None and v[0] == "12"

    # 3 new columns present on entities
    cols = {r[1] for r in conn.execute("PRAGMA table_info(entities)").fetchall()}
    assert "type" in cols
    assert "kind" in cols
    assert "lifecycle_class" in cols

    # entity_type column absent
    assert "entity_type" not in cols, (
        "Migration 12 must DROP entities.entity_type (AC-1.4); still present"
    )

    # phase_events.event_type CHECK accepts 7 values — synthetic insert per
    # event_type proves the constraint is permissive enough.
    pe_create_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='phase_events'"
    ).fetchone()[0]
    for ev in (
        "started", "completed", "skipped", "backward",
        "entity_created", "entity_status_changed", "entity_promoted",
    ):
        assert f"'{ev}'" in pe_create_sql, (
            f"phase_events CHECK missing event_type {ev!r}: {pe_create_sql}"
        )

    # phase column is now NULL-able (was NOT NULL pre-migration).
    pe_cols = conn.execute("PRAGMA table_info(phase_events)").fetchall()
    phase_col = next(c for c in pe_cols if c[1] == "phase")
    # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
    assert phase_col[3] == 0, (
        f"phase column notnull flag should be 0 (NULL-able), got {phase_col[3]}"
    )

    # phase_events has metadata column
    pe_col_names = {c[1] for c in pe_cols}
    assert "metadata" in pe_col_names

    # Both immutable triggers absent from sqlite_master
    trig_rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND name IN ("
        "'enforce_immutable_entity_type', 'enforce_immutable_type_id')"
    ).fetchall()
    assert trig_rows == [], (
        f"Immutable triggers must be dropped (AC-3.1); still present: {trig_rows}"
    )

    # entities_fts uses 'kind' instead of 'entity_type'
    fts_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='entities_fts'"
    ).fetchone()[0]
    assert "kind" in fts_sql, f"entities_fts schema missing kind: {fts_sql}"
    assert "entity_type" not in fts_sql, (
        f"entities_fts must not reference entity_type post-migration: {fts_sql}"
    )

    # idx_entities_type_kind index exists
    idx_row = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='index' AND name='idx_entities_type_kind'"
    ).fetchone()
    assert idx_row is not None, (
        "idx_entities_type_kind index must exist post-migration (AC-1.6)"
    )

    # FK check clean
    fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert fk_violations == [], (
        f"Post-migration FK violations: {fk_violations}"
    )


def test_migration_12_idempotent() -> None:
    """Task 16.4a / AC-5.2: running migration 12 twice produces no error and
    no schema drift.
    """
    conn = make_v12_db()
    schema_before = conn.execute(
        "SELECT name, sql FROM sqlite_master ORDER BY name"
    ).fetchall()
    schema_before_norm = [(r[0], r[1]) for r in schema_before]

    MIGRATIONS[12](conn)

    schema_after = conn.execute(
        "SELECT name, sql FROM sqlite_master ORDER BY name"
    ).fetchall()
    schema_after_norm = [(r[0], r[1]) for r in schema_after]
    assert schema_before_norm == schema_after_norm, (
        "Migration 12 must be idempotent — schema_after != schema_before"
    )


def test_migration_12_lock_failure(tmp_path: Path) -> None:
    """Task 16.4b / AC-5.4 + AC-2.5: when another connection holds an
    exclusive lock, migration 12 raises OperationalError rather than
    silently swallowing it.
    """
    db_path = tmp_path / "lock_test.db"
    # Build a v11 DB at the file path so the migration has something to
    # operate against.
    setup_conn = make_v11_db(db_path)
    setup_conn.close()

    # Hold an exclusive lock from a separate connection.
    holder = sqlite3.connect(str(db_path), timeout=0.0)
    holder.execute("PRAGMA busy_timeout = 0")
    holder.execute("BEGIN EXCLUSIVE")
    try:
        # Open a second connection with a short busy_timeout and attempt
        # migration 12.
        attacker = sqlite3.connect(str(db_path), timeout=0.0)
        attacker.row_factory = sqlite3.Row
        attacker.execute("PRAGMA busy_timeout = 100")
        with pytest.raises(sqlite3.OperationalError) as excinfo:
            _migration_12_polymorphic_taxonomy_and_events(attacker)
        # Loud failure surface: the error message mentions the lock.
        assert "lock" in str(excinfo.value).lower() or "busy" in str(
            excinfo.value
        ).lower(), (
            f"Expected lock/busy in error message, got: {excinfo.value!r}"
        )
        attacker.close()
    finally:
        try:
            holder.rollback()
        except sqlite3.Error:
            pass
        holder.close()


# ---------------------------------------------------------------------------
# Group 16.5b: down-migration verification
# ---------------------------------------------------------------------------


def test_migration_12_down() -> None:
    """Task 16.5b / AC-5.1: down migration restores runtime v11 schema state.

    Assert after running down on a v12 DB:
      - schema_version = '11'
      - entity_type column restored on entities
      - new columns (type, kind, lifecycle_class) absent
      - Both immutable triggers present in sqlite_master
      - phase_events.event_type CHECK narrowed back to 4 values
      - phase_events.phase NOT NULL again
      - phase_events.metadata column absent
      - idx_entities_type_kind index absent
      - entities_fts references entity_type (not kind)
    """
    conn = make_v12_db()
    # Sanity: confirm v12 state before applying down.
    cols_v12 = {r[1] for r in conn.execute("PRAGMA table_info(entities)").fetchall()}
    assert "kind" in cols_v12 and "entity_type" not in cols_v12

    MIGRATIONS_DOWN[12](conn)

    # schema_version stamped back to 11
    v = conn.execute(
        "SELECT value FROM _metadata WHERE key='schema_version'"
    ).fetchone()
    assert v is not None and v[0] == "11"

    # entity_type column restored; new columns absent.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(entities)").fetchall()}
    assert "entity_type" in cols
    assert "type" not in cols
    assert "kind" not in cols
    assert "lifecycle_class" not in cols

    # Both immutable triggers present.
    trig_rows = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name IN ("
            "'enforce_immutable_entity_type', 'enforce_immutable_type_id')"
        ).fetchall()
    }
    assert trig_rows == {
        "enforce_immutable_entity_type",
        "enforce_immutable_type_id",
    }, f"Immutable triggers must be re-created; got {trig_rows!r}"

    # phase_events.event_type CHECK narrowed.
    pe_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='phase_events'"
    ).fetchone()[0]
    for ev in ("started", "completed", "skipped", "backward"):
        assert f"'{ev}'" in pe_sql
    for ev in ("entity_created", "entity_status_changed", "entity_promoted"):
        assert f"'{ev}'" not in pe_sql, (
            f"phase_events CHECK must narrow back; still allows {ev!r}: {pe_sql}"
        )

    # phase column NOT NULL again.
    pe_cols = conn.execute("PRAGMA table_info(phase_events)").fetchall()
    phase_col = next(c for c in pe_cols if c[1] == "phase")
    assert phase_col[3] == 1, (
        f"phase column notnull flag should be 1 after down, got {phase_col[3]}"
    )

    # metadata column absent.
    pe_col_names = {c[1] for c in pe_cols}
    assert "metadata" not in pe_col_names

    # idx_entities_type_kind absent.
    idx_row = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='index' AND name='idx_entities_type_kind'"
    ).fetchone()
    assert idx_row is None, (
        "idx_entities_type_kind must be dropped on down"
    )

    # entities_fts references entity_type (not kind).
    fts_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='entities_fts'"
    ).fetchone()[0]
    assert "entity_type" in fts_sql, (
        f"entities_fts must reference entity_type after down: {fts_sql}"
    )
    assert "kind" not in fts_sql, (
        f"entities_fts must not reference kind after down: {fts_sql}"
    )
