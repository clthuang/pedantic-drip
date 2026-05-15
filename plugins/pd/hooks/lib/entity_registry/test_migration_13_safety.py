"""Migration 13 safety tests (feature 110 Groups 1+2+3).

Scope:
  - Pre-flight gate (Task 1.3 / AC-5.6, AC-5.6b, AC-5.6c): three stale-shape
    fixtures + version-divergence fixture each abort migration 13 with a
    distinct error.
  - Pre-flight pass (Task 1.4): clean post-12 fixture proceeds past the gate.
  - Idempotency (Task 2.6 / AC-5.2): replaying migration 13 is a no-op.
  - schema_version stamp (Task 2.7 / AC-5.3): post-migration version is 13.
  - Single-tx + FK check (Task 2.8 / AC-5.1): source-level BEGIN IMMEDIATE +
    PRAGMA foreign_key_check assertions.
  - Runtime PRAGMA introspection (Task 2.9 / AC-5.7): missing-column fixture
    aborts before any DDL.
"""
from __future__ import annotations

import inspect
import sqlite3
import tempfile
import uuid as _uuid
from pathlib import Path

import pytest

from entity_registry.database import (
    MIGRATIONS,
    MIGRATIONS_DOWN,
    _migration_12_polymorphic_taxonomy_and_events,
    _migration_13_entity_display,
    _migration_13_entity_display_down,
)
from entity_registry.test_helpers import make_v11_db, make_v12_db


# ---------------------------------------------------------------------------
# Test helpers — synthetic stale-schema fixtures
# ---------------------------------------------------------------------------


def _make_stale_pre12_shape(path: Path | None = None) -> sqlite3.Connection:
    """v11-style DB: entity_type column present, type/kind/lifecycle_class
    absent. Mirrors a database that has never run migration 12.

    Returns a connection where _metadata.schema_version='11'.
    """
    return make_v11_db(path)


def _make_partial_v12_shape(path: Path | None = None) -> sqlite3.Connection:
    """v11+entity_type AND v12 columns both present, but entity_type NOT
    dropped — mirrors a migration-12 run that partially succeeded before the
    DROP COLUMN step. Schema_version is stamped as 12 (so pre-flight check 1
    passes), but the column layout check (#3) detects the stale entity_type.
    """
    conn = make_v11_db(path)
    # Add v12 columns alongside the legacy entity_type column.
    conn.execute("ALTER TABLE entities ADD COLUMN type TEXT NOT NULL DEFAULT 'work'")
    conn.execute("ALTER TABLE entities ADD COLUMN kind TEXT NOT NULL DEFAULT 'feature'")
    conn.execute(
        "ALTER TABLE entities ADD COLUMN lifecycle_class TEXT NOT NULL "
        "DEFAULT 'feature_flow'"
    )
    conn.execute(
        "INSERT OR REPLACE INTO _metadata (key, value) VALUES ('schema_version', '12')"
    )
    conn.commit()
    return conn


def _make_version_divergence_shape(path: Path | None = None) -> sqlite3.Connection:
    """Schema is at v12 (entity_type absent, type/kind/lifecycle_class present),
    BUT _metadata.schema_version says '11' — simulating a torn write between
    schema migration and version stamp.

    Migration 13 reads schema_version from _metadata; the divergence triggers
    the version-mismatch error path.
    """
    conn = make_v12_db(path)
    # Manually revert just the stamp — schema is fully migrated but version
    # is wrong. This is the dual of partial_v12_shape and exercises check #1.
    conn.execute(
        "INSERT OR REPLACE INTO _metadata (key, value) VALUES ('schema_version', '11')"
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Pre-flight gate tests (Task 1.3 / AC-5.6, AC-5.6b, AC-5.6c)
# ---------------------------------------------------------------------------


def test_pre_flight_aborts_on_stale_pre12_schema() -> None:
    """v11 baseline: entity_type column present, type/kind absent. Migration
    13 must ABORT with the schema-mismatch error pointing at feature-109."""
    conn = _make_stale_pre12_shape()

    with pytest.raises(RuntimeError) as excinfo:
        _migration_13_entity_display(conn)

    msg = str(excinfo.value)
    # Per Task 1.3 DoD: error must mention "feature 109" remediation guidance.
    assert "feature 109" in msg.lower() or "feature-109" in msg.lower(), (
        f"Stale-pre12 abort error should reference feature 109; got: {msg}"
    )
    # entity_display must NOT exist after the abort.
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='entity_display'"
    ).fetchall()
    assert rows == [], "entity_display table created despite pre-flight abort"


def test_pre_flight_aborts_on_partial_v12_schema() -> None:
    """partial-12 shape: entity_type AND type/kind both present. Migration
    13 must ABORT (AC-5.6b)."""
    conn = _make_partial_v12_shape()

    with pytest.raises(RuntimeError) as excinfo:
        _migration_13_entity_display(conn)

    msg = str(excinfo.value)
    assert "feature 109" in msg.lower() or "feature-109" in msg.lower(), (
        f"Partial-12 abort error should reference feature 109; got: {msg}"
    )
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='entity_display'"
    ).fetchall()
    assert rows == [], "entity_display table created despite pre-flight abort"


def test_pre_flight_aborts_on_version_divergence() -> None:
    """Version-divergence: schema is post-12 but _metadata.schema_version=11.
    Migration 13 must ABORT (AC-5.6c) with the user_version mismatch error."""
    conn = _make_version_divergence_shape()

    with pytest.raises(RuntimeError) as excinfo:
        _migration_13_entity_display(conn)

    msg = str(excinfo.value)
    # Per Task 1.3 / TD-6 check 1 error message.
    assert "expected 12" in msg.lower() or "user_version" in msg.lower(), (
        f"Version divergence error should mention version mismatch; got: {msg}"
    )


def test_pre_flight_passes_on_clean_post_12_db() -> None:
    """Fresh post-12 fixture: pre-flight gate passes; migration 13 proceeds
    to create entity_display (Task 1.4)."""
    conn = make_v12_db()
    # No entities, no mismatches. Migration should succeed end-to-end.
    _migration_13_entity_display(conn)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='entity_display'"
    ).fetchall()
    assert rows != [], "entity_display table missing after successful migration"


# ---------------------------------------------------------------------------
# Idempotency + version stamp tests (Tasks 2.6, 2.7 / AC-5.2, AC-5.3)
# ---------------------------------------------------------------------------


def test_migration_13_idempotent_replay() -> None:
    """Replaying migration 13 on a v13 DB is a no-op."""
    conn = make_v12_db()
    _migration_13_entity_display(conn)

    # Capture row count for entity_display after first run.
    first_count = conn.execute(
        "SELECT COUNT(*) FROM entity_display"
    ).fetchone()[0]

    # Second run — should be a no-op early-return.
    _migration_13_entity_display(conn)

    second_count = conn.execute(
        "SELECT COUNT(*) FROM entity_display"
    ).fetchone()[0]
    assert first_count == second_count, "entity_display row count changed on replay"

    # schema_version still 13.
    v = conn.execute(
        "SELECT value FROM _metadata WHERE key='schema_version'"
    ).fetchone()
    assert v is not None and v[0] == "13", f"schema_version drifted on replay: {v}"


def test_user_version_and_schema_version_table_set() -> None:
    """Post-migration: _metadata.schema_version=13 (codebase analogue of
    PRAGMA user_version; see implementation note)."""
    conn = make_v12_db()
    _migration_13_entity_display(conn)
    v = conn.execute(
        "SELECT value FROM _metadata WHERE key='schema_version'"
    ).fetchone()
    assert v is not None and v[0] == "13", f"Expected schema_version=13; got {v}"


# ---------------------------------------------------------------------------
# Static / runtime BEGIN IMMEDIATE + FK check (Task 2.8 / AC-5.1)
# ---------------------------------------------------------------------------


def test_migration_13_static_has_begin_immediate_and_fk_check() -> None:
    """Source-level assertion: migration 13 contains BEGIN IMMEDIATE and at
    least one PRAGMA foreign_key_check between BEGIN IMMEDIATE and the
    schema_version stamp."""
    source = inspect.getsource(_migration_13_entity_display)

    begin_idx = source.find("BEGIN IMMEDIATE")
    stamp_idx = source.find("'schema_version', '13'")
    fk_idx = source.find("PRAGMA foreign_key_check")

    assert begin_idx >= 0, "migration 13 must contain BEGIN IMMEDIATE"
    assert stamp_idx >= 0, "migration 13 must stamp schema_version=13"
    assert fk_idx >= 0, "migration 13 must contain PRAGMA foreign_key_check"

    # Find a foreign_key_check between BEGIN IMMEDIATE and the stamp.
    cursor = begin_idx
    found_in_tx = False
    while True:
        fk_idx = source.find("PRAGMA foreign_key_check", cursor)
        if fk_idx < 0 or fk_idx > stamp_idx:
            break
        if fk_idx > begin_idx:
            found_in_tx = True
            break
        cursor = fk_idx + 1
    assert found_in_tx, (
        "migration 13 must contain an in-transaction PRAGMA foreign_key_check "
        "between BEGIN IMMEDIATE and the schema_version stamp"
    )


def test_migration_13_fk_check_clean_on_healthy_fixture() -> None:
    """Runtime: PRAGMA foreign_key_check returns zero rows pre- AND post-DDL
    on a healthy v12 fixture."""
    conn = make_v12_db()
    pre = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert pre == []
    _migration_13_entity_display(conn)
    post = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert post == []


# ---------------------------------------------------------------------------
# Runtime PRAGMA introspection (Task 2.9 / AC-5.7)
# ---------------------------------------------------------------------------


def test_runtime_pragma_introspection_aborts_on_missing_column() -> None:
    """Synthetic v12 fixture with the ``metadata`` column dropped → migration
    13 ABORTS via runtime PRAGMA table_info introspection. entity_display
    must NOT be created."""
    conn = make_v12_db()

    # Drop metadata column from entities. SQLite < 3.35 lacks DROP COLUMN; we
    # use copy-rename. SQLite 3.35+ supports DROP COLUMN natively (Python
    # 3.12 ships with 3.45+ stdlib build). Use the native path.
    # First we must drop FTS5 + triggers that reference metadata.
    try:
        conn.execute("ALTER TABLE entities DROP COLUMN metadata")
    except sqlite3.OperationalError:
        # Fallback for older SQLite: copy-rename. Build a temporary table
        # without metadata then swap.
        # For test simplicity, skip if we can't drop the column.
        pytest.skip("SQLite DROP COLUMN unsupported on this build")

    conn.commit()

    with pytest.raises(RuntimeError) as excinfo:
        _migration_13_entity_display(conn)

    msg = str(excinfo.value).lower()
    assert "metadata" in msg or "column" in msg, (
        f"Missing-column abort error should mention the missing column; got: {msg}"
    )

    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='entity_display'"
    ).fetchall()
    assert rows == [], "entity_display created despite missing-column abort"
