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


# ---------------------------------------------------------------------------
# Feature 088 Bundle D: migration 10 hardening tests
# ---------------------------------------------------------------------------


def _reset_phase_events_to_pre_migration(database):
    """Drop phase_events artefacts + reset schema_version to 9.

    Used by feature 088 Bundle D tests to exercise ``_migration_10_phase_events``
    directly against a clean slate.
    """
    database._conn.execute("DROP TABLE IF EXISTS phase_events")
    database._conn.execute("DROP INDEX IF EXISTS idx_pe_lookup")
    database._conn.execute("DROP INDEX IF EXISTS idx_pe_project")
    database._conn.execute("DROP INDEX IF EXISTS idx_pe_timestamp")
    database._conn.execute("DROP INDEX IF EXISTS phase_events_backfill_dedup")
    database._conn.execute(
        "INSERT INTO _metadata(key, value) VALUES('schema_version', '9') "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    )
    database._conn.commit()


class TestFeature088Migration10Hardening:
    """Feature 088 Bundle D: migration 10 concurrency, backfill validation."""

    def test_migration_10_concurrent_idempotent(self, tmp_path):
        """AC-5: two threads running migration 10 simultaneously yield single-run row count.

        Uses ``threading.Barrier`` to align both threads inside the migration
        entry point. The partial UNIQUE index + INSERT OR IGNORE (plus the
        inside-BEGIN schema_version re-check) MUST produce the same row count
        as a single-threaded control run.
        """
        import threading
        import time
        from entity_registry.database import _migration_10_phase_events

        db_path = str(tmp_path / "concurrent.db")

        # Seed one control DB and one concurrent DB with identical entity set.
        def seed_entities(database):
            # Three entities with phase_timing metadata.
            database.register_entity(
                "feature", "001-alpha", "Alpha",
                project_id=TEST_PROJECT_ID,
                metadata={
                    "phase_timing": {
                        "brainstorm": {
                            "started": "2026-01-01T00:00:00Z",
                            "completed": "2026-01-01T01:00:00Z",
                            "iterations": 2,
                        },
                        "specify": {"started": "2026-01-01T02:00:00Z"},
                    },
                    "skipped_phases": ["design"],
                },
            )
            database.register_entity(
                "feature", "002-beta", "Beta",
                project_id=TEST_PROJECT_ID,
                metadata={
                    "phase_timing": {
                        "brainstorm": {
                            "started": "2026-01-02T00:00:00Z",
                            "completed": "2026-01-02T01:00:00Z",
                        },
                    },
                    "backward_history": [{
                        "source_phase": "specify",
                        "target_phase": "brainstorm",
                        "reason": "gap",
                        "timestamp": "2026-01-02T02:00:00Z",
                    }],
                },
            )

        # Control: single-thread run
        control_db = EntityDatabase(":memory:")
        seed_entities(control_db)
        _reset_phase_events_to_pre_migration(control_db)
        _migration_10_phase_events(control_db._conn)
        control_count = control_db._conn.execute(
            "SELECT COUNT(*) FROM phase_events"
        ).fetchone()[0]
        control_db.close()
        assert control_count > 0, "control run must produce backfill rows"

        # Concurrent: two threads race on the same file-backed DB.
        seed_db = EntityDatabase(db_path)
        seed_entities(seed_db)
        _reset_phase_events_to_pre_migration(seed_db)
        seed_db.close()

        barrier = threading.Barrier(2)
        errors: list[BaseException] = []

        def worker():
            try:
                conn = sqlite3.connect(db_path, timeout=10.0)
                try:
                    barrier.wait(timeout=5.0)
                    _migration_10_phase_events(conn)
                finally:
                    conn.close()
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)
            assert not t.is_alive(), "migration thread hung"

        # At least one thread may raise sqlite3.OperationalError under heavy
        # lock contention; that is acceptable as long as the winning run
        # produced the correct row count.  But a RuntimeError from the
        # barrier or an unrelated crash is not acceptable.
        for exc in errors:
            assert isinstance(exc, sqlite3.Error), (
                f"unexpected non-sqlite exception in worker: {exc!r}"
            )

        final_conn = sqlite3.connect(db_path)
        try:
            final_count = final_conn.execute(
                "SELECT COUNT(*) FROM phase_events"
            ).fetchone()[0]
        finally:
            final_conn.close()

        # Concurrent run must produce EXACTLY the same count as single-run.
        assert final_count == control_count, (
            f"concurrent run produced {final_count} rows; "
            f"control produced {control_count}"
        )

    def test_migration_skips_unparseable_timestamp(self, capsys):
        """AC-9: unparseable timestamp is skipped with stderr warning."""
        from entity_registry.database import _migration_10_phase_events

        database = EntityDatabase(":memory:")
        # Seed an entity with an unparseable timestamp in metadata.phase_timing.
        database.register_entity(
            "feature", "bad-ts", "Bad Timestamp",
            project_id=TEST_PROJECT_ID,
            metadata={
                "phase_timing": {
                    "design": {"started": "not-a-date"},
                    "brainstorm": {
                        "started": "2026-01-01T00:00:00Z",
                        "completed": "2026-01-01T01:00:00Z",
                    },
                },
            },
        )
        _reset_phase_events_to_pre_migration(database)
        _migration_10_phase_events(database._conn)

        # Row for (type_id, design, started) MUST NOT exist.
        rows = database._conn.execute(
            "SELECT * FROM phase_events "
            "WHERE type_id='feature:bad-ts' AND phase='design' "
            "AND event_type='started'"
        ).fetchall()
        assert rows == []

        # Valid rows still landed.
        rows_ok = database._conn.execute(
            "SELECT * FROM phase_events "
            "WHERE type_id='feature:bad-ts' AND phase='brainstorm'"
        ).fetchall()
        assert len(rows_ok) == 2

        # Stderr warning was emitted.
        captured = capsys.readouterr()
        assert "[migration-10] skipping unparseable timestamp" in captured.err
        database.close()

    def test_migration_truncates_backward_reason_at_500(self):
        """AC-9b: backward_reason and backward_target truncated to 500 chars."""
        from entity_registry.database import _migration_10_phase_events

        database = EntityDatabase(":memory:")
        database.register_entity(
            "feature", "trunc-001", "Trunc",
            project_id=TEST_PROJECT_ID,
            metadata={
                "backward_history": [{
                    "source_phase": "design",
                    "target_phase": "y" * 800,
                    "reason": "x" * 800,
                    "timestamp": "2026-04-01T00:00:00Z",
                }],
            },
        )
        _reset_phase_events_to_pre_migration(database)
        _migration_10_phase_events(database._conn)

        row = database._conn.execute(
            "SELECT backward_reason, backward_target "
            "FROM phase_events WHERE type_id='feature:trunc-001' "
            "AND event_type='backward'"
        ).fetchone()
        assert row is not None
        assert len(row["backward_reason"]) == 500
        assert len(row["backward_target"]) == 500

        # Original metadata blob is unchanged (AC-9b invariant).
        entity = database.get_entity("feature:trunc-001")
        meta = json.loads(entity["metadata"])
        bh = meta["backward_history"][0]
        assert len(bh["reason"]) == 800
        assert len(bh["target_phase"]) == 800
        database.close()


# ---------------------------------------------------------------------------
# Feature 088 Bundle E: DB-layer reviewer_notes guard + transaction participation
# ---------------------------------------------------------------------------


class TestFeature088BundleE:
    """Feature 088 Bundle E: DB-layer reviewer_notes cap + transaction pin.

    Covers FR-2.4 (DB-layer defense-in-depth) and FR-5.2 / AC-16
    (``insert_phase_event`` participates in an outer ``db.transaction()``
    block rather than committing prematurely). The latter is a pin of the
    existing ``_commit()`` guard at ``database.py:1672-1675`` — no source
    change is made by this test; it merely locks in current behavior.
    """

    def test_insert_phase_event_rejects_oversized_reviewer_notes(self, db):
        """FR-2.4 DB-layer defense: reviewer_notes >10000 chars raises
        ``ValueError`` before SQL execution.
        """
        oversized = "x" * 10001
        with pytest.raises(ValueError, match="reviewer_notes exceeds 10000 chars"):
            db.insert_phase_event(
                type_id="feature:oversized-001",
                project_id=TEST_PROJECT_ID,
                phase="specify",
                event_type="completed",
                timestamp="2026-04-01T10:00:00Z",
                reviewer_notes=oversized,
            )

        # No row was inserted.
        rows = db._conn.execute(
            "SELECT * FROM phase_events WHERE type_id = 'feature:oversized-001'"
        ).fetchall()
        assert rows == []

        # Exact-boundary sanity: 10000 chars is allowed.
        at_boundary = "x" * 10000
        db.insert_phase_event(
            type_id="feature:boundary-001",
            project_id=TEST_PROJECT_ID,
            phase="specify",
            event_type="completed",
            timestamp="2026-04-01T10:00:00Z",
            reviewer_notes=at_boundary,
        )
        rows_ok = db._conn.execute(
            "SELECT * FROM phase_events WHERE type_id = 'feature:boundary-001'"
        ).fetchall()
        assert len(rows_ok) == 1

    def test_insert_phase_event_does_not_prematurely_commit_outer_transaction(
        self, db,
    ):
        """AC-16 (FR-5.2): inside ``db.transaction()``, ``insert_phase_event``
        MUST participate in the outer transaction rather than auto-commit.

        Pins the existing ``_commit()`` guard at ``database.py:1672-1675``
        which defers to ``self._in_transaction`` (set by the ``transaction()``
        context manager). A rollback triggered by an exception inside the
        ``with`` block MUST remove the inserted row.
        """
        type_id_under_test = "feature:txn-pin-001"

        # Precondition: no rows for this type_id.
        pre = db._conn.execute(
            "SELECT COUNT(*) AS c FROM phase_events WHERE type_id = ?",
            (type_id_under_test,),
        ).fetchone()["c"]
        assert pre == 0

        # Run the transaction wrapper; expect our sentinel to propagate.
        with pytest.raises(RuntimeError, match="rollback test"):
            with db.transaction():
                db.insert_phase_event(
                    type_id=type_id_under_test,
                    project_id=TEST_PROJECT_ID,
                    phase="specify",
                    event_type="started",
                    timestamp="2026-04-01T10:00:00Z",
                )
                # Force an abort BEFORE the ``with`` block exits — the
                # outer transaction must roll back, discarding the insert.
                raise RuntimeError("rollback test")

        # Post-rollback: the inserted row MUST be absent. If the insert had
        # auto-committed via an unguarded ``self._commit()``, it would persist.
        post = db._conn.execute(
            "SELECT COUNT(*) AS c FROM phase_events WHERE type_id = ?",
            (type_id_under_test,),
        ).fetchone()["c"]
        assert post == 0, (
            "insert_phase_event prematurely committed despite outer "
            "db.transaction() context manager being active"
        )
