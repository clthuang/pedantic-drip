"""Adversarial tests for phase_events: migration 10, insert, query edge cases.

Goal: BREAK feature 084. Find bugs, not fix them.
"""
from __future__ import annotations

import json
import sqlite3
import uuid

import pytest

from entity_registry.database import EntityDatabase, _migration_10_phase_events
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


def _reset_to_pre_migration_10(db_instance):
    """Drop phase_events and reset schema_version to 9."""
    db_instance._conn.execute("DROP TABLE IF EXISTS phase_events")
    db_instance._conn.execute("DROP INDEX IF EXISTS idx_pe_lookup")
    db_instance._conn.execute("DROP INDEX IF EXISTS idx_pe_project")
    db_instance._conn.execute("DROP INDEX IF EXISTS idx_pe_timestamp")
    db_instance._conn.execute(
        "INSERT INTO _metadata(key, value) VALUES('schema_version', '9') "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    )
    db_instance._conn.commit()


# ===========================================================================
# 1. BACKFILL EDGE CASES
# ===========================================================================

class TestBackfillEdgeCases:
    """Attack vector 1: malformed/unusual metadata during backfill."""

    def test_empty_phase_timing_dict(self, db):
        """Entity with phase_timing={} should produce 0 backfill rows, no crash."""
        db.register_entity(
            "feature", "empty-timing", "Empty Timing",
            project_id=TEST_PROJECT_ID,
            metadata={"phase_timing": {}},
        )
        _reset_to_pre_migration_10(db)
        _migration_10_phase_events(db._conn)

        count = db._conn.execute(
            "SELECT COUNT(*) as cnt FROM phase_events WHERE type_id='feature:empty-timing'"
        ).fetchone()["cnt"]
        assert count == 0, "Empty phase_timing should produce 0 events"

    def test_phase_started_but_no_completed(self, db):
        """Mid-phase entity: started exists but completed missing.
        Should produce only a 'started' event, not crash."""
        db.register_entity(
            "feature", "mid-phase", "Mid Phase",
            project_id=TEST_PROJECT_ID,
            metadata={"phase_timing": {"design": {"started": "2026-03-01T00:00:00Z"}}},
        )
        _reset_to_pre_migration_10(db)
        _migration_10_phase_events(db._conn)

        rows = db._conn.execute(
            "SELECT * FROM phase_events WHERE type_id='feature:mid-phase'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["event_type"] == "started"

    def test_backward_history_missing_required_fields(self, db):
        """backward_history entry missing source_phase, target_phase, reason.
        Migration should handle gracefully (defaults or skip)."""
        db.register_entity(
            "feature", "bad-bh", "Bad Backward History",
            project_id=TEST_PROJECT_ID,
            metadata={
                "phase_timing": {},
                "backward_history": [
                    {},  # completely empty entry
                    {"source_phase": "design"},  # missing target_phase, reason, timestamp
                ],
            },
        )
        _reset_to_pre_migration_10(db)

        # Should not crash
        _migration_10_phase_events(db._conn)

        rows = db._conn.execute(
            "SELECT * FROM phase_events WHERE type_id='feature:bad-bh'"
        ).fetchall()
        # Both entries should be backfilled (with defaults), verify they exist
        assert len(rows) == 2, f"Expected 2 backward events (with defaults), got {len(rows)}"
        # Check that the empty entry got 'unknown' as phase
        phases = [r["phase"] for r in rows]
        assert "unknown" in phases, "Empty backward_history entry should get 'unknown' phase"

    def test_skipped_phases_as_string_not_list(self, db):
        """skipped_phases is a string instead of a list — malformed data.
        The migration iterates over it; iterating a string yields characters.
        BUG CANDIDATE: 'for skipped in "design"' yields 'd', 'e', 's', 'i', 'g', 'n'."""
        db.register_entity(
            "feature", "str-skip", "String Skip",
            project_id=TEST_PROJECT_ID,
            metadata={
                "phase_timing": {},
                "skipped_phases": "design",  # string, not list!
            },
        )
        _reset_to_pre_migration_10(db)
        _migration_10_phase_events(db._conn)

        rows = db._conn.execute(
            "SELECT * FROM phase_events WHERE type_id='feature:str-skip' AND event_type='skipped'"
        ).fetchall()
        # If string iteration happens, we'd get 6 char-events instead of 1 phase-event
        if len(rows) > 1:
            phases = [r["phase"] for r in rows]
            pytest.fail(
                f"BUG: skipped_phases string iterated char-by-char! "
                f"Got {len(rows)} events with phases: {phases}. "
                f"Expected either 1 event for 'design' or 0 (skipped gracefully)."
            )

    def test_large_metadata_json(self, db):
        """Entity with very large metadata (>100KB). Should not crash."""
        big_notes = ["note " * 200] * 50  # ~50KB of notes
        meta = {
            "phase_timing": {
                "brainstorm": {
                    "started": "2026-01-01T00:00:00Z",
                    "completed": "2026-01-01T01:00:00Z",
                    "reviewerNotes": big_notes,
                },
            },
        }
        assert len(json.dumps(meta)) > 50000, "Metadata should be >50KB"

        db.register_entity(
            "feature", "big-meta", "Big Metadata",
            project_id=TEST_PROJECT_ID,
            metadata=meta,
        )
        _reset_to_pre_migration_10(db)
        _migration_10_phase_events(db._conn)

        rows = db._conn.execute(
            "SELECT * FROM phase_events WHERE type_id='feature:big-meta'"
        ).fetchall()
        assert len(rows) == 2  # started + completed

    def test_extra_unknown_fields_in_metadata(self, db):
        """Metadata with unknown fields alongside phase_timing. Should not crash."""
        db.register_entity(
            "feature", "extra-fields", "Extra Fields",
            project_id=TEST_PROJECT_ID,
            metadata={
                "phase_timing": {"brainstorm": {"started": "2026-01-01T00:00:00Z"}},
                "some_unknown_field": {"nested": True},
                "another_field": 42,
            },
        )
        _reset_to_pre_migration_10(db)
        _migration_10_phase_events(db._conn)

        rows = db._conn.execute(
            "SELECT * FROM phase_events WHERE type_id='feature:extra-fields'"
        ).fetchall()
        assert len(rows) == 1

    def test_phase_timing_value_is_not_dict(self, db):
        """phase_timing where a phase value is a string instead of dict.
        BUG CANDIDATE: timing.get("started") on a string will crash."""
        db.register_entity(
            "feature", "bad-timing-val", "Bad Timing Value",
            project_id=TEST_PROJECT_ID,
            metadata={
                "phase_timing": {
                    "brainstorm": "2026-01-01T00:00:00Z",  # string, not dict!
                },
            },
        )
        _reset_to_pre_migration_10(db)

        # This should either skip the malformed entry gracefully or crash
        try:
            _migration_10_phase_events(db._conn)
        except AttributeError as e:
            pytest.fail(
                f"BUG: Migration crashes on non-dict phase_timing value: {e}. "
                f"Should handle gracefully."
            )


# ===========================================================================
# 2. MIGRATION SAFETY
# ===========================================================================

class TestMigrationSafety:
    """Attack vector 2: migration edge cases."""

    def test_migration_on_existing_phase_events_table(self, db):
        """If phase_events table already exists (partial previous run),
        migration should either skip or fail gracefully, not crash with
        'table already exists'."""
        # phase_events already exists from the initial migration
        # Reset schema_version but DON'T drop the table
        db._conn.execute(
            "INSERT INTO _metadata(key, value) VALUES('schema_version', '9') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        db._conn.commit()

        # Running migration 10 again should handle the existing table
        try:
            _migration_10_phase_events(db._conn)
        except sqlite3.OperationalError as e:
            if "already exists" in str(e):
                pytest.fail(
                    f"BUG: Migration 10 crashes if phase_events table already exists: {e}. "
                    f"Should use CREATE TABLE IF NOT EXISTS or handle gracefully."
                )
            raise

    def test_null_project_id_entity_not_possible(self, db):
        """Entity with NULL project_id cannot be created — entities table has NOT NULL.
        This is NOT a migration 10 bug; the schema prevents the precondition."""
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO entities (uuid, entity_type, entity_id, type_id, name, "
                "project_id, metadata, status, created_at, updated_at) "
                "VALUES (?, 'feature', 'null-proj', 'feature:null-proj', 'Null Project', "
                "NULL, ?, 'active', datetime('now'), datetime('now'))",
                (
                    str(uuid.uuid4()),
                    json.dumps({"phase_timing": {"brainstorm": {"started": "2026-01-01T00:00:00Z"}}}),
                ),
            )

    def test_backfill_timestamp_format_consistency(self, db):
        """Verify backfill timestamps use consistent format.
        Spec says ISO-8601 UTC. Check for Z suffix vs +00:00 mixing."""
        db.register_entity(
            "feature", "ts-check", "Timestamp Check",
            project_id=TEST_PROJECT_ID,
            metadata={"phase_timing": {"brainstorm": {
                "started": "2026-01-01T00:00:00+00:00",  # +00:00 format
                "completed": "2026-01-01T01:00:00Z",     # Z format
            }}},
        )
        _reset_to_pre_migration_10(db)
        _migration_10_phase_events(db._conn)

        rows = db._conn.execute(
            "SELECT timestamp FROM phase_events WHERE type_id='feature:ts-check' ORDER BY timestamp"
        ).fetchall()
        timestamps = [r["timestamp"] for r in rows]
        # The migration preserves original timestamps, which may mix formats
        # This is informational — check if they're both present
        formats = set()
        for ts in timestamps:
            if ts.endswith("Z"):
                formats.add("Z")
            elif "+00:00" in ts:
                formats.add("+00:00")
        if len(formats) > 1:
            # Not necessarily a bug, but worth reporting as a data quality concern
            print(f"INFO: Mixed timestamp formats in backfill: {timestamps}")


# ===========================================================================
# 3. INSERT_PHASE_EVENT EDGE CASES
# ===========================================================================

class TestInsertPhaseEventEdgeCases:
    """Attack vector 3: insert_phase_event boundary conditions."""

    def test_invalid_event_type_rejected(self, db):
        """Invalid event_type should be rejected by CHECK constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_phase_event(
                type_id="feature:bad-type",
                project_id=TEST_PROJECT_ID,
                phase="brainstorm",
                event_type="INVALID_TYPE",
                timestamp="2026-04-01T10:00:00Z",
            )

    def test_invalid_source_rejected(self, db):
        """Invalid source should be rejected by CHECK constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_phase_event(
                type_id="feature:bad-source",
                project_id=TEST_PROJECT_ID,
                phase="brainstorm",
                event_type="started",
                timestamp="2026-04-01T10:00:00Z",
                source="INVALID_SOURCE",
            )

    def test_null_type_id_rejected(self, db):
        """NULL type_id should be rejected by NOT NULL constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO phase_events "
                "(type_id, project_id, phase, event_type, timestamp, source, created_at) "
                "VALUES (NULL, ?, ?, 'started', '2026-01-01T00:00:00Z', 'live', '2026-01-01T00:00:00Z')",
                (TEST_PROJECT_ID, "brainstorm"),
            )

    def test_null_project_id_rejected(self, db):
        """NULL project_id should be rejected by NOT NULL constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO phase_events "
                "(type_id, project_id, phase, event_type, timestamp, source, created_at) "
                "VALUES ('feature:x', NULL, 'brainstorm', 'started', '2026-01-01T00:00:00Z', 'live', '2026-01-01T00:00:00Z')",
            )

    def test_null_timestamp_rejected(self, db):
        """NULL timestamp should be rejected by NOT NULL constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO phase_events "
                "(type_id, project_id, phase, event_type, timestamp, source, created_at) "
                "VALUES ('feature:x', ?, 'brainstorm', 'started', NULL, 'live', '2026-01-01T00:00:00Z')",
                (TEST_PROJECT_ID,),
            )

    def test_very_long_strings(self, db):
        """Very long type_id, phase, backward_reason strings. Should not crash."""
        long_str = "x" * 10000
        db.insert_phase_event(
            type_id=f"feature:{long_str}",
            project_id=TEST_PROJECT_ID,
            phase=long_str,
            event_type="backward",
            timestamp="2026-04-01T10:00:00Z",
            backward_reason=long_str,
            backward_target=long_str,
        )
        rows = db._conn.execute(
            f"SELECT * FROM phase_events WHERE type_id='feature:{long_str}'"
        ).fetchall()
        assert len(rows) == 1

    def test_empty_string_event_type(self, db):
        """Empty string event_type — should be rejected by CHECK constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_phase_event(
                type_id="feature:empty-evt",
                project_id=TEST_PROJECT_ID,
                phase="brainstorm",
                event_type="",
                timestamp="2026-04-01T10:00:00Z",
            )


# ===========================================================================
# 4. QUERY_PHASE_EVENTS EDGE CASES
# ===========================================================================

class TestQueryPhaseEventsEdgeCases:
    """Attack vector 4: query_phase_events boundary conditions."""

    def test_empty_table_returns_empty_list(self, db):
        """Empty table should return [], not None or error."""
        results = db.query_phase_events()
        assert results == [], f"Expected empty list, got {results!r}"

    def test_all_filters_none_returns_all(self, db):
        """All filters None should return all rows (up to limit)."""
        db.insert_phase_event(
            type_id="feature:all-none",
            project_id=TEST_PROJECT_ID,
            phase="brainstorm",
            event_type="started",
            timestamp="2026-04-01T10:00:00Z",
        )
        results = db.query_phase_events()
        assert len(results) >= 1

    def test_limit_zero(self, db):
        """limit=0 — should return 0 rows or behave reasonably."""
        db.insert_phase_event(
            type_id="feature:lim-zero",
            project_id=TEST_PROJECT_ID,
            phase="brainstorm",
            event_type="started",
            timestamp="2026-04-01T10:00:00Z",
        )
        results = db.query_phase_events(limit=0)
        # SQLite LIMIT 0 returns 0 rows — this is correct behavior
        assert len(results) == 0, f"limit=0 should return 0 rows, got {len(results)}"

    def test_limit_negative(self, db):
        """limit=-1 — SQLite treats LIMIT -1 as unlimited.
        BUG CANDIDATE: min(-1, 500) = -1, so LIMIT -1 returns ALL rows."""
        for i in range(10):
            db.insert_phase_event(
                type_id=f"feature:neg-{i}",
                project_id=TEST_PROJECT_ID,
                phase="brainstorm",
                event_type="started",
                timestamp=f"2026-04-01T{i:02d}:00:00Z",
            )
        results = db.query_phase_events(limit=-1)
        # min(-1, 500) = -1, and SQLite LIMIT -1 means NO LIMIT
        # This bypasses the 500 cap!
        if len(results) > 500:
            pytest.fail(
                f"BUG: limit=-1 bypasses the 500 cap! Got {len(results)} rows."
            )
        # Even returning all 10 when capped at 500 isn't a bug per se,
        # but limit=-1 bypassing the cap IS a bug
        if len(results) == 10:
            # min(-1, 500) == -1, LIMIT -1 == unlimited in SQLite
            pytest.fail(
                f"BUG: limit=-1 bypasses cap via min(-1, 500)=-1. "
                f"SQLite LIMIT -1 means unlimited. Got all {len(results)} rows."
            )

    def test_sql_injection_via_type_id(self, db):
        """SQL injection attempt via type_id filter — should be parameterized."""
        db.insert_phase_event(
            type_id="feature:safe",
            project_id=TEST_PROJECT_ID,
            phase="brainstorm",
            event_type="started",
            timestamp="2026-04-01T10:00:00Z",
        )
        # Attempt injection
        results = db.query_phase_events(
            type_id="feature:safe' OR '1'='1"
        )
        # If parameterized, this returns 0 rows (no match)
        # If vulnerable, returns all rows
        assert len(results) == 0, (
            f"CRITICAL BUG: SQL injection succeeded! Got {len(results)} rows. "
            f"Filters are not parameterized."
        )

    def test_sql_injection_via_phase(self, db):
        """SQL injection attempt via phase filter."""
        db.insert_phase_event(
            type_id="feature:inj-phase",
            project_id=TEST_PROJECT_ID,
            phase="brainstorm",
            event_type="started",
            timestamp="2026-04-01T10:00:00Z",
        )
        results = db.query_phase_events(
            phase="brainstorm' OR '1'='1"
        )
        assert len(results) == 0, "SQL injection via phase filter succeeded!"

    def test_empty_string_filter_treated_as_falsy(self, db):
        """Empty string filter — truthy in most langs but '' is falsy in Python.
        BUG CANDIDATE: 'if type_id:' skips empty string, treating it as 'no filter'."""
        db.insert_phase_event(
            type_id="feature:empty-filter",
            project_id=TEST_PROJECT_ID,
            phase="brainstorm",
            event_type="started",
            timestamp="2026-04-01T10:00:00Z",
        )
        # If we filter by type_id="" and it's treated as "no filter", we get results
        results = db.query_phase_events(type_id="")
        if len(results) > 0:
            # This might be intentional (empty string = no filter),
            # but it's inconsistent — the caller explicitly passed a filter value
            print(
                f"INFO: Empty string type_id='\"\"' treated as no filter, "
                f"returned {len(results)} rows instead of 0."
            )


# ===========================================================================
# 5. COMBINATION ATTACKS
# ===========================================================================

class TestCombinationAttacks:
    """Edge cases combining multiple vectors."""

    def test_backfill_entity_with_all_edge_cases(self, db):
        """Entity with all edge cases combined: empty phase_timing,
        string skipped_phases, empty backward_history entry."""
        db.register_entity(
            "feature", "combo", "Combo Edge Case",
            project_id=TEST_PROJECT_ID,
            metadata={
                "phase_timing": {},
                "skipped_phases": "design",  # string, not list
                "backward_history": [{}],     # empty entry
            },
        )
        _reset_to_pre_migration_10(db)

        try:
            _migration_10_phase_events(db._conn)
        except Exception as e:
            pytest.fail(f"BUG: Migration crashes on combined edge cases: {e}")

        rows = db._conn.execute(
            "SELECT * FROM phase_events WHERE type_id='feature:combo'"
        ).fetchall()
        # Report what we got
        event_types = [(r["phase"], r["event_type"]) for r in rows]
        print(f"Combo entity produced: {event_types}")

    def test_insert_then_query_roundtrip_preserves_data(self, db):
        """Insert with all fields, query back, verify all fields preserved."""
        db.insert_phase_event(
            type_id="feature:roundtrip",
            project_id="proj-RT",
            phase="design",
            event_type="completed",
            timestamp="2026-04-01T10:30:00Z",
            iterations=5,
            reviewer_notes='["note1", "note2"]',
            source="live",
        )
        results = db.query_phase_events(type_id="feature:roundtrip")
        assert len(results) == 1
        r = results[0]
        assert r["type_id"] == "feature:roundtrip"
        assert r["project_id"] == "proj-RT"
        assert r["phase"] == "design"
        assert r["event_type"] == "completed"
        assert r["timestamp"] == "2026-04-01T10:30:00Z"
        assert r["iterations"] == 5
        assert r["reviewer_notes"] == '["note1", "note2"]'
        assert r["source"] == "live"
        assert r["created_at"] is not None
        assert r["id"] is not None
