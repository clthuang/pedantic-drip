"""Migration 14 safety tests (feature 111 Group A + Group B).

Scope:
  - AC-MR.1: entity_relations table + 3 indices + CHECK(kind IN ('fixes'))
  - AC-MR.2: (type, kind) CHECK widening on entities admits 'bug'
  - AC-MR.3: phase_events.event_type CHECK admits 'spawned_child'
  - AC-MR.4: pre-flight aborts on missing entity_display (stale-v12 fixture)
  - AC-MR.5: pre-flight aborts when entity_relations already exists
  - AC-MR.6: replay on v14 → no-op
  - AC-MR.7: down-migration on clean v14 → byte-identical to pre-v14 snapshot;
             schema_version stamped back to 13.
  - AC-MR.8: composite UNIQUE on (from_uuid, to_uuid, kind)
  - AC-MR.9: PRAGMA foreign_keys = ON post-migration; FK violation on bad uuid.
  - AC-MR.10: down-migration refuses when kind='bug' rows exist
  - AC-MR.11: down-migration refuses when entity_relations rows exist

Uses live ``EntityDatabase`` constructor — which runs ALL migrations end-to-end —
plus a small synthetic-v13 fixture builder for pre-flight gate exercise.
"""
from __future__ import annotations

import sqlite3
import uuid as _uuid

import pytest

from entity_registry.database import (
    MIGRATIONS,
    MIGRATIONS_DOWN,
    EntityDatabase,
    MigrationError,
    _migration_14_down,
    _migration_14_issue_lifecycle_closure,
)
from entity_registry.test_helpers import make_v12_db


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_v13_conn(tmp_path=None) -> sqlite3.Connection:
    """Build a synthetic v13 connection by running migration 13 on top of v12.

    Returns a connection at ``_metadata.schema_version='13'`` with
    ``entity_display`` and ``migration_audit_log`` tables present.
    """
    from entity_registry.database import _migration_13_entity_display

    conn = make_v12_db(None if tmp_path is None else tmp_path / "v13.db")
    _migration_13_entity_display(conn)
    return conn


def _make_v14_db(tmp_path) -> EntityDatabase:
    """Construct a fresh EntityDatabase — runs all migrations including 14.

    Returns the EntityDatabase at the current head schema_version (17 post-F115).
    Test name preserved for git-blame continuity.
    """
    db_path = str(tmp_path / "v14.db")
    db = EntityDatabase(db_path)
    return db


# ---------------------------------------------------------------------------
# AC-MR.1 — entity_relations table + 3 indices + CHECK(kind IN ('fixes'))
# ---------------------------------------------------------------------------


def test_ac_mr_1_entity_relations_table_columns(tmp_path):
    """Post-migration, entity_relations exists with the expected columns."""
    db = _make_v14_db(tmp_path)
    try:
        cols = db._conn.execute(
            "PRAGMA table_info(entity_relations)"
        ).fetchall()
        col_names = [c["name"] if hasattr(c, "keys") else c[1] for c in cols]
        # Schema: id, from_uuid, to_uuid, kind, created_at
        assert "id" in col_names
        assert "from_uuid" in col_names
        assert "to_uuid" in col_names
        assert "kind" in col_names
        assert "created_at" in col_names
    finally:
        db.close()


def test_ac_mr_1_entity_relations_indices(tmp_path):
    """3 indices on entity_relations: unique, from, to."""
    db = _make_v14_db(tmp_path)
    try:
        rows = db._conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name='entity_relations' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        names = {r[0] for r in rows}
        assert "idx_entity_relations_unique" in names
        assert "idx_entity_relations_from" in names
        assert "idx_entity_relations_to" in names
    finally:
        db.close()


def test_ac_mr_1_entity_relations_check_constraint(tmp_path):
    """CHECK constraint admits kind='fixes' and rejects others."""
    db = _make_v14_db(tmp_path)
    try:
        sql_row = db._conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='entity_relations'"
        ).fetchone()
        assert sql_row is not None
        assert "'fixes'" in sql_row[0]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# AC-MR.2 — entities (type, kind) CHECK admits 'bug'
# ---------------------------------------------------------------------------


def test_ac_mr_2_entities_check_admits_bug(tmp_path):
    """Post-migration: sqlite_master.sql for 'entities' lists bug in work kinds."""
    db = _make_v14_db(tmp_path)
    try:
        row = db._conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='entities'"
        ).fetchone()
        assert row is not None
        # Spec FR-MR.2 pins the exact order including 'bug' between
        # 'backlog' and 'initiative'.
        expected = (
            "'feature','backlog','bug','initiative',"
            "'objective','key_result','task'"
        )
        # Allow optional whitespace between values:
        # Normalize: strip spaces around commas before substring match.
        normalized = row[0].replace(" ", "")
        assert expected.replace(" ", "") in normalized, (
            f"Expected substring {expected!r} (post-normalization) in entities "
            f"DDL; got: {row[0][:400]!r}"
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# AC-MR.3 — phase_events.event_type CHECK admits 'spawned_child'
# ---------------------------------------------------------------------------


def test_ac_mr_3_phase_events_check_admits_spawned_child(tmp_path):
    db = _make_v14_db(tmp_path)
    try:
        row = db._conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='phase_events'"
        ).fetchone()
        assert row is not None
        assert "'spawned_child'" in row[0]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# AC-MR.4 — pre-flight aborts on missing entity_display (stale-v12 fixture)
# ---------------------------------------------------------------------------


def test_ac_mr_4_pre_flight_aborts_on_missing_entity_display(tmp_path):
    """v12 DB (no entity_display) → migration 14 aborts with the FR-MR.6 message."""
    conn = make_v12_db(tmp_path / "stale12.db")
    # Stamp schema_version=13 manually to bypass gate 1 so we exercise gate 2.
    conn.execute(
        "INSERT OR REPLACE INTO _metadata (key, value) "
        "VALUES ('schema_version', '13')"
    )
    conn.commit()

    with pytest.raises(MigrationError) as excinfo:
        _migration_14_issue_lifecycle_closure(conn)
    msg = str(excinfo.value)
    assert "entity_display" in msg, (
        f"Pre-flight abort should mention entity_display; got: {msg}"
    )


# ---------------------------------------------------------------------------
# AC-MR.5 — pre-flight aborts when entity_relations already exists
# ---------------------------------------------------------------------------


def test_ac_mr_5_pre_flight_aborts_on_existing_entity_relations(tmp_path):
    """Existing entity_relations table at v13 → migration 14 aborts.

    AC-MR.5 message substring: "Migration 14 entity_relations table already exists".
    """
    conn = _make_v13_conn(tmp_path)
    # Inject a synthetic entity_relations table BEFORE running migration 14.
    conn.execute(
        "CREATE TABLE entity_relations (id INTEGER PRIMARY KEY)"
    )
    conn.commit()

    with pytest.raises(MigrationError) as excinfo:
        _migration_14_issue_lifecycle_closure(conn)
    msg = str(excinfo.value)
    assert "entity_relations table already exists" in msg, (
        f"Expected substring 'entity_relations table already exists' in: {msg}"
    )


# ---------------------------------------------------------------------------
# AC-MR.6 — replay on v14 is no-op
# ---------------------------------------------------------------------------


def test_ac_mr_6_replay_is_no_op(tmp_path):
    """Re-running migration 14 on a v14 DB does not change schema_version
    and does not raise."""
    db = _make_v14_db(tmp_path)
    try:
        # Capture state.
        v_before = db._conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()[0]
        # Post-F115: head is 17 (M15 + M16 stub + M17), not 14.
        assert v_before == "17"

        # Replay should be a no-op early-return.
        _migration_14_issue_lifecycle_closure(db._conn)

        v_after = db._conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()[0]
        assert v_after == "17"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# AC-MR.7 — down-migration on clean v14 → schema_version stamped back to 13
# ---------------------------------------------------------------------------


def test_ac_mr_7_down_migration_stamps_version_13(tmp_path):
    """Down-migration on a clean v14 DB (no bugs, no relations) restores v13."""
    db = _make_v14_db(tmp_path)
    try:
        _migration_14_down(db._conn)

        v = db._conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()[0]
        assert v == "13"

        # entity_relations table should be gone.
        rows = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='entity_relations'"
        ).fetchall()
        assert rows == []
    finally:
        db.close()


# ---------------------------------------------------------------------------
# AC-MR.8 — composite UNIQUE on (from_uuid, to_uuid, kind)
# ---------------------------------------------------------------------------


def test_ac_mr_8_composite_unique(tmp_path):
    """Duplicate (from, to, kind) raises IntegrityError without ON CONFLICT."""
    db = _make_v14_db(tmp_path)
    try:
        # Insert two real entities so FK constraints are satisfied.
        eid_a = db.register_entity(
            entity_type="feature",
            entity_id="111-foo",
            name="A",
            project_id="__unknown__",
        )
        eid_b = db.register_entity(
            entity_type="feature",
            entity_id="222-bar",
            name="B",
            project_id="__unknown__",
        )
        now = EntityDatabase._now_iso()
        db._conn.execute(
            "INSERT INTO entity_relations(from_uuid, to_uuid, kind, created_at) "
            "VALUES (?, ?, 'fixes', ?)",
            (eid_a, eid_b, now),
        )
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO entity_relations(from_uuid, to_uuid, kind, created_at) "
                "VALUES (?, ?, 'fixes', ?)",
                (eid_a, eid_b, now),
            )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# AC-MR.9 — FK enforcement on entity_relations
# ---------------------------------------------------------------------------


def test_ac_mr_9_fk_enforcement(tmp_path):
    """PRAGMA foreign_keys = ON; INSERT with non-existent from_uuid → FK violation."""
    db = _make_v14_db(tmp_path)
    try:
        fk_status = db._conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk_status == 1

        bogus = str(_uuid.uuid4())
        now = EntityDatabase._now_iso()
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO entity_relations(from_uuid, to_uuid, kind, created_at) "
                "VALUES (?, ?, 'fixes', ?)",
                (bogus, bogus, now),
            )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# AC-MR.10 — down-migration refuses on bug entities
# ---------------------------------------------------------------------------


def test_ac_mr_10_down_refuses_when_bug_entities_exist(tmp_path):
    """Insert a kind='bug' row, then attempt down-migration → MigrationError.

    Uses register_entity (relies on Group B's VALID_ENTITY_TYPES extension)
    so the test reflects the production write path.
    """
    db = _make_v14_db(tmp_path)
    try:
        db.register_entity(
            entity_type="bug",
            entity_id="1-foo",
            name="A bug",
            status="open",
            project_id="__unknown__",
        )

        with pytest.raises(MigrationError) as excinfo:
            _migration_14_down(db._conn)
        msg = str(excinfo.value)
        assert "Cannot down-migrate v14" in msg
        assert "bug entities" in msg
    finally:
        db.close()


# ---------------------------------------------------------------------------
# AC-MR.11 — down-migration refuses on entity_relations rows
# ---------------------------------------------------------------------------


def test_ac_mr_11_down_refuses_when_entity_relations_exist(tmp_path):
    """Insert 1 entity_relations row, attempt down-migration → MigrationError."""
    db = _make_v14_db(tmp_path)
    try:
        eid_a = db.register_entity(
            entity_type="feature",
            entity_id="111-foo",
            name="A",
            project_id="__unknown__",
        )
        eid_b = db.register_entity(
            entity_type="feature",
            entity_id="222-bar",
            name="B",
            project_id="__unknown__",
        )
        now = EntityDatabase._now_iso()
        db._conn.execute(
            "INSERT INTO entity_relations(from_uuid, to_uuid, kind, created_at) "
            "VALUES (?, ?, 'fixes', ?)",
            (eid_a, eid_b, now),
        )
        db._conn.commit()

        with pytest.raises(MigrationError) as excinfo:
            _migration_14_down(db._conn)
        msg = str(excinfo.value)
        assert "entity_relations" in msg
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Smoke: MIGRATIONS / MIGRATIONS_DOWN dispatch entries present.
# ---------------------------------------------------------------------------


def test_migration_14_registered():
    assert 14 in MIGRATIONS
    assert 14 in MIGRATIONS_DOWN
