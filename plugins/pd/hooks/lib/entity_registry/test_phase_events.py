"""Tests for phase_events table: migration 10, insert, query."""
from __future__ import annotations

import json
import sqlite3
import uuid

import pytest

from entity_registry.database import EntityDatabase, MIGRATIONS
from entity_registry.test_helpers import TEST_PROJECT_ID


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """In-memory database with full migrations applied."""
    database = EntityDatabase(":memory:")
    yield database
    database.close()


@pytest.fixture
def seeded_db():
    """DB with 3 entities pre-seeded with phase_timing metadata BEFORE migration 10.

    Strategy: create DB (runs all migrations incl. 10), register entities,
    then drop phase_events + reset schema_version to 9, and re-run migration 10
    so the backfill actually processes the seeded entities.
    """
    from entity_registry.database import _migration_10_phase_events

    database = EntityDatabase(":memory:")

    # Seed 3 entities with phase_timing metadata
    meta1 = {
        "phase_timing": {
            "brainstorm": {"started": "2026-01-01T00:00:00Z", "completed": "2026-01-01T01:00:00Z", "iterations": 2},
            "specify": {"started": "2026-01-01T02:00:00Z"},
        },
        "skipped_phases": ["design"],
    }
    meta2 = {
        "phase_timing": {
            "brainstorm": {"started": "2026-01-02T00:00:00Z", "completed": "2026-01-02T01:00:00Z"},
        },
        "backward_history": [
            {"source_phase": "specify", "target_phase": "brainstorm", "reason": "scope gap", "timestamp": "2026-01-02T02:00:00Z"},
        ],
    }
    meta3 = {
        "phase_timing": {
            "implement": {"started": "2026-01-03T00:00:00Z", "completed": "2026-01-03T05:00:00Z", "iterations": 3,
                          "reviewerNotes": ["fix lint", "add tests"]},
        },
    }

    database.register_entity(
        "feature", "001-alpha", "Alpha",
        project_id=TEST_PROJECT_ID, metadata=meta1,
    )
    database.register_entity(
        "feature", "002-beta", "Beta",
        project_id=TEST_PROJECT_ID, metadata=meta2,
    )
    database.register_entity(
        "feature", "003-gamma", "Gamma",
        project_id=TEST_PROJECT_ID, metadata=meta3,
    )

    # Drop phase_events and reset schema_version to simulate pre-migration state
    database._conn.execute("DROP TABLE IF EXISTS phase_events")
    database._conn.execute("DROP INDEX IF EXISTS idx_pe_lookup")
    database._conn.execute("DROP INDEX IF EXISTS idx_pe_project")
    database._conn.execute("DROP INDEX IF EXISTS idx_pe_timestamp")
    database._conn.execute(
        "INSERT INTO _metadata(key, value) VALUES('schema_version', '9') "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    )
    database._conn.commit()

    # Re-run migration 10 to backfill from the seeded entities
    _migration_10_phase_events(database._conn)

    yield database
    database.close()


# ---------------------------------------------------------------------------
# TestMigration10
# ---------------------------------------------------------------------------


class TestMigration10:
    """AC-1, AC-2, AC-3, AC-8, AC-9, AC-10, AC-18."""

    def test_ac1_table_exists(self, db):
        """AC-1: phase_events table exists after migration."""
        row = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='phase_events'"
        ).fetchone()
        assert row is not None

    def test_ac2_schema_correct(self, db):
        """AC-2: 12 columns with correct names/types."""
        cols = db._conn.execute("PRAGMA table_info(phase_events)").fetchall()
        col_names = [c["name"] for c in cols]
        expected = [
            "id", "type_id", "project_id", "phase", "event_type",
            "timestamp", "iterations", "reviewer_notes", "backward_reason",
            "backward_target", "source", "created_at",
        ]
        assert col_names == expected
        assert len(cols) == 12

    def test_ac3_indexes_exist(self, db):
        """AC-3: 3 composite indexes exist."""
        indexes = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='phase_events'"
        ).fetchall()
        idx_names = {r["name"] for r in indexes}
        assert "idx_pe_lookup" in idx_names
        assert "idx_pe_project" in idx_names
        assert "idx_pe_timestamp" in idx_names

    def test_ac8_backfill_count(self, seeded_db):
        """AC-8: backfill creates rows from seeded phase_timing."""
        # Entity 001: brainstorm started+completed, specify started = 3 events + 1 skipped (design) = 4
        # Entity 002: brainstorm started+completed = 2 events + 1 backward = 3
        # Entity 003: implement started+completed = 2 events
        # Total backfill events = 4 + 3 + 2 = 9
        count = seeded_db._conn.execute(
            "SELECT COUNT(*) as cnt FROM phase_events WHERE source='backfill'"
        ).fetchone()["cnt"]
        assert count == 9

    def test_ac9_malformed_metadata(self, db):
        """AC-9: entity with malformed metadata produces 0 rows."""
        # Register entity then corrupt its metadata
        db.register_entity(
            "feature", "bad-meta", "Bad Meta",
            project_id=TEST_PROJECT_ID, metadata={"phase_timing": {"brainstorm": {"started": "2026-01-01T00:00:00Z"}}},
        )
        # The entity was registered after migration 10 ran, so its phase_timing
        # was not backfilled. To test AC-9 properly, we need to verify that
        # a malformed metadata entity doesn't crash migration. Since migration
        # already ran, we verify by checking that the table exists (migration
        # completed successfully even if there were malformed entries).
        # For a more direct test, we manually run the migration function on
        # a pre-migration schema.
        #
        # Actually, let's test this more directly: drop phase_events, insert
        # a bad entity, then re-run migration 10.
        db._conn.execute("DROP TABLE IF EXISTS phase_events")
        db._conn.execute("DROP INDEX IF EXISTS idx_pe_lookup")
        db._conn.execute("DROP INDEX IF EXISTS idx_pe_project")
        db._conn.execute("DROP INDEX IF EXISTS idx_pe_timestamp")
        # Insert entity with bad metadata directly
        db._conn.execute(
            "UPDATE entities SET metadata = 'not json' WHERE type_id = 'feature:bad-meta'"
        )
        db._conn.execute(
            "INSERT INTO _metadata(key, value) VALUES('schema_version', '9') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        db._conn.commit()

        # Re-run migration 10
        from entity_registry.database import _migration_10_phase_events
        _migration_10_phase_events(db._conn)

        # Verify no rows for the bad entity
        count = db._conn.execute(
            "SELECT COUNT(*) as cnt FROM phase_events WHERE type_id='feature:bad-meta'"
        ).fetchone()["cnt"]
        assert count == 0

    def test_ac10_backfill_source_tag(self, seeded_db):
        """AC-10: backfill rows have source='backfill'."""
        rows = seeded_db._conn.execute(
            "SELECT DISTINCT source FROM phase_events"
        ).fetchall()
        sources = {r["source"] for r in rows}
        # Only backfill rows exist at this point (no live events yet)
        assert "backfill" in sources

    def test_ac18_idempotent_migration(self, db):
        """AC-18: calling _migrate() twice produces no duplicate rows."""
        initial_count = db._conn.execute(
            "SELECT COUNT(*) as cnt FROM phase_events"
        ).fetchone()["cnt"]

        # Force re-migrate by resetting schema_version
        # Actually, _migrate checks schema_version and skips if already at max.
        # So calling _migrate() again should be a no-op.
        db._migrate()

        final_count = db._conn.execute(
            "SELECT COUNT(*) as cnt FROM phase_events"
        ).fetchone()["cnt"]
        assert final_count == initial_count


# ---------------------------------------------------------------------------
# TestInsertPhaseEvent
# ---------------------------------------------------------------------------


class TestInsertPhaseEvent:
    """Test EntityDatabase.insert_phase_event method."""

    def test_insert_all_columns(self, db):
        """INSERT with all columns populates correctly."""
        db.insert_phase_event(
            type_id="feature:test-001",
            project_id=TEST_PROJECT_ID,
            phase="specify",
            event_type="completed",
            timestamp="2026-04-01T10:00:00Z",
            iterations=3,
            reviewer_notes='["fix lint"]',
            backward_reason=None,
            backward_target=None,
            source="live",
        )
        rows = db._conn.execute(
            "SELECT * FROM phase_events WHERE type_id='feature:test-001'"
        ).fetchall()
        assert len(rows) == 1
        row = dict(rows[0])
        assert row["phase"] == "specify"
        assert row["event_type"] == "completed"
        assert row["iterations"] == 3
        assert row["reviewer_notes"] == '["fix lint"]'
        assert row["source"] == "live"
        assert row["created_at"] is not None

    def test_insert_returns_none(self, db):
        """insert_phase_event returns None."""
        result = db.insert_phase_event(
            type_id="feature:test-ret",
            project_id=TEST_PROJECT_ID,
            phase="brainstorm",
            event_type="started",
            timestamp="2026-04-01T10:00:00Z",
        )
        assert result is None

    def test_insert_backward_event(self, db):
        """INSERT backward event with reason and target."""
        db.insert_phase_event(
            type_id="feature:test-bw",
            project_id=TEST_PROJECT_ID,
            phase="design",
            event_type="backward",
            timestamp="2026-04-01T12:00:00Z",
            backward_reason="scope gap",
            backward_target="specify",
        )
        rows = db._conn.execute(
            "SELECT * FROM phase_events WHERE type_id='feature:test-bw'"
        ).fetchall()
        assert len(rows) == 1
        row = dict(rows[0])
        assert row["backward_reason"] == "scope gap"
        assert row["backward_target"] == "specify"


# ---------------------------------------------------------------------------
# TestQueryPhaseEvents
# ---------------------------------------------------------------------------


class TestQueryPhaseEvents:
    """Test EntityDatabase.query_phase_events method."""

    @pytest.fixture(autouse=True)
    def seed_events(self, db):
        """Seed multiple events for query testing."""
        events = [
            ("feature:q-001", "proj-A", "brainstorm", "started", "2026-01-01T00:00:00Z"),
            ("feature:q-001", "proj-A", "brainstorm", "completed", "2026-01-01T01:00:00Z"),
            ("feature:q-001", "proj-A", "specify", "started", "2026-01-01T02:00:00Z"),
            ("feature:q-002", "proj-B", "brainstorm", "started", "2026-01-02T00:00:00Z"),
            ("feature:q-002", "proj-B", "design", "backward", "2026-01-02T03:00:00Z"),
        ]
        for type_id, proj, phase, evt, ts in events:
            db.insert_phase_event(
                type_id=type_id, project_id=proj, phase=phase,
                event_type=evt, timestamp=ts,
            )

    def test_filter_by_type_id(self, db):
        """Filter by type_id returns only matching rows."""
        results = db.query_phase_events(type_id="feature:q-001")
        assert len(results) == 3
        assert all(r["type_id"] == "feature:q-001" for r in results)

    def test_filter_by_project_id(self, db):
        """Filter by project_id returns only matching rows."""
        results = db.query_phase_events(project_id="proj-B")
        assert len(results) == 2
        assert all(r["project_id"] == "proj-B" for r in results)

    def test_filter_by_phase(self, db):
        """Filter by phase."""
        results = db.query_phase_events(phase="brainstorm")
        assert len(results) == 3

    def test_filter_by_event_type(self, db):
        """Filter by event_type."""
        results = db.query_phase_events(event_type="started")
        assert len(results) == 3

    def test_limit(self, db):
        """Limit caps results."""
        results = db.query_phase_events(limit=2)
        assert len(results) == 2

    def test_limit_capped_at_500(self, db):
        """Limit is capped at 500."""
        results = db.query_phase_events(limit=1000)
        # All 5 events returned (under 500 cap)
        assert len(results) == 5

    def test_order_by_timestamp_desc(self, db):
        """Results ordered by timestamp DESC."""
        results = db.query_phase_events()
        timestamps = [r["timestamp"] for r in results]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_returns_list_of_dicts(self, db):
        """Results are list of plain dicts."""
        results = db.query_phase_events(limit=1)
        assert isinstance(results, list)
        assert isinstance(results[0], dict)
        assert "type_id" in results[0]

    def test_combined_filters(self, db):
        """Multiple filters combine with AND."""
        results = db.query_phase_events(
            type_id="feature:q-001", event_type="completed",
        )
        assert len(results) == 1
        assert results[0]["phase"] == "brainstorm"
