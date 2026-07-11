"""Tests for entity_registry.events (dark-shipped v2 event log).

Covers design 119 Testing Strategy #1-6: events table/index/trigger shape
(PRAGMA introspection), DB-resident immutability enforcement (asserted on
a bare connection, so no events.py code is in the write path),
append_event's mint shape (uuid7 version/variant nibbles, UTC timestamp)
and sequential ordering, transaction composition (caller-owned vs.
standalone with_retry, both the happy and the failure path), the
with_retry retry-path pin, the connect_v2 FK-enforcement pair, and the
payload registry round-trip.

Imports `events` at module top like its siblings — that import's side
effect (`schema_v2.register_ddl("events", ...)`) is how the events DDL
gets registered into DDL_REGISTRY at all; every bootstrap_v2 call in this
file picks it up as a result.
"""
from __future__ import annotations

import sqlite3
import threading
import time

import pytest

from entity_registry import events
from entity_registry import schema_v2

_NOW = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def bootstrapped_db_path(tmp_path):
    """Fresh v2 DB path with core + events DDL applied. The module-top
    `events` import above already registered "events" into
    schema_v2.DDL_REGISTRY, so bootstrap_v2 applies both."""
    db_path = str(tmp_path / "v2.db")
    conn = schema_v2.bootstrap_v2(db_path)
    conn.close()
    return db_path


@pytest.fixture
def seeded_entity_uuid(bootstrapped_db_path):
    """Insert one workspace + one entity row directly; return the
    entity's uuid — the FK target append_event's tests write against."""
    workspace_uuid = "workspace-uuid-events-test"
    entity_uuid = "entity-uuid-events-test"
    conn = sqlite3.connect(bootstrapped_db_path)
    try:
        conn.execute(
            "INSERT INTO workspaces (uuid, project_root, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (workspace_uuid, "/tmp/project", _NOW, _NOW),
        )
        conn.execute(
            "INSERT INTO entities (uuid, workspace_uuid, type, kind, lifecycle_class, "
            "type_id, name, artifact_path, parent_uuid, created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entity_uuid, workspace_uuid, "feature", "feature", "artifact",
                "119-append-only-event-log", "Test Entity", None, None,
                _NOW, _NOW, None,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return entity_uuid


@pytest.fixture
def v2_conn(bootstrapped_db_path):
    """A connect_v2 connection on the bootstrapped path, closed after
    the test."""
    conn = events.connect_v2(bootstrapped_db_path)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Design test #1: events table/index/trigger introspection (SC1)
# ---------------------------------------------------------------------------
class TestEventsTableIntrospection:
    def test_table_info_exact_column_set(self, bootstrapped_db_path):
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            columns = [
                row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()
            ]
        finally:
            conn.close()
        assert columns == [
            "uuid", "entity_uuid", "event_type", "axis",
            "from_value", "to_value", "actor", "timestamp", "payload",
        ]

    def test_ddl_text_has_exactly_three_check_constraints(self, bootstrapped_db_path):
        """event_type length, axis 3-value, and actor length are CHECKs.
        entity_uuid and timestamp are also NOT NULL, but NOT NULL is a
        distinct constraint type — it must not be counted as a CHECK."""
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            ddl_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'events'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert "CHECK(length(event_type) > 0)" in ddl_sql
        assert "CHECK(axis IN ('pipeline','execution','lifecycle'))" in ddl_sql
        assert "CHECK(length(actor) > 0)" in ddl_sql
        assert ddl_sql.count("CHECK(") == 3

    def test_two_indexes_present(self, bootstrapped_db_path):
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            index_names = {
                row[1] for row in conn.execute("PRAGMA index_list(events)").fetchall()
            }
        finally:
            conn.close()
        assert "idx_events_entity_axis" in index_names
        assert "idx_events_timestamp" in index_names

    def test_two_immutability_triggers_present(self, bootstrapped_db_path):
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            trigger_names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                    "AND tbl_name = 'events'"
                ).fetchall()
            }
        finally:
            conn.close()
        assert trigger_names == {"events_no_update", "events_no_delete"}


# ---------------------------------------------------------------------------
# Design test #2: raw-connection immutability (SC2)
# ---------------------------------------------------------------------------
class TestEventsImmutability:
    """The bare-connection assertion below proves enforcement is
    DB-resident (the triggers), not anything in this module's Python — no
    events.py code is in the write path for these UPDATE/DELETE calls
    (only the module-top `events` import above, which is how the DDL
    registers in the first place)."""

    def test_bare_connection_blocks_update_and_delete_but_allows_insert(
        self, bootstrapped_db_path
    ):
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            conn.execute(
                "INSERT INTO events "
                "(uuid, entity_uuid, event_type, axis, actor, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "event-uuid-immutability-1", "entity-uuid-immutability-1",
                    "phase_completed", "pipeline", "test-actor", _NOW,
                ),
            )
            conn.commit()
            row_count = conn.execute(
                "SELECT COUNT(*) FROM events WHERE uuid = ?",
                ("event-uuid-immutability-1",),
            ).fetchone()[0]
            assert row_count == 1

            with pytest.raises(sqlite3.IntegrityError, match="events rows are immutable"):
                conn.execute(
                    "UPDATE events SET actor = ? WHERE uuid = ?",
                    ("someone-else", "event-uuid-immutability-1"),
                )

            with pytest.raises(sqlite3.IntegrityError, match="events rows are immutable"):
                conn.execute(
                    "DELETE FROM events WHERE uuid = ?",
                    ("event-uuid-immutability-1",),
                )
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Design test #3: round-trip + version/variant nibbles + UTC stamp +
# sequential order (SC3)
# ---------------------------------------------------------------------------
class TestAppendEventRoundTrip:
    def test_mint_is_version_7_with_rfc9562_variant_nibble(self, v2_conn, seeded_entity_uuid):
        event_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", actor="test-actor",
        )
        assert event_uuid[14] == "7"
        assert event_uuid[19] in "89ab"

    def test_default_timestamp_is_utc_iso8601_with_timezone_marker(
        self, v2_conn, seeded_entity_uuid
    ):
        event_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", actor="test-actor",
        )
        rows = events.read_events(v2_conn, seeded_entity_uuid)
        (matching_row,) = [row for row in rows if row["uuid"] == event_uuid]
        assert matching_row["timestamp"].endswith("+00:00")

    def test_sequential_appends_land_in_ascending_uuid_order(self, v2_conn, seeded_entity_uuid):
        first_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="event-a",
            axis="pipeline", actor="test-actor",
        )
        second_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="event-b",
            axis="pipeline", actor="test-actor",
        )
        rows = events.read_events(v2_conn, seeded_entity_uuid)
        assert [row["uuid"] for row in rows] == [first_uuid, second_uuid]
        assert first_uuid < second_uuid


# ---------------------------------------------------------------------------
# Design test #4 (a-c): transaction composition — caller-owned rollback,
# standalone failure atomicity, two-thread distinct-uuid append (SC4a-c)
# ---------------------------------------------------------------------------
class TestAppendEventTransactionComposition:
    def test_caller_transaction_rollback_discards_the_event(self, v2_conn, seeded_entity_uuid):
        """The caller manages its own transaction with raw SQL, not the
        sqlite3.Connection.commit()/.rollback() convenience methods:
        on an autocommit=True connection (connect_v2), those methods are
        no-ops against a transaction opened via raw "BEGIN IMMEDIATE"
        text (verified empirically — see append_event's docstring)."""
        v2_conn.execute("BEGIN IMMEDIATE")
        event_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", actor="test-actor",
        )
        v2_conn.execute("ROLLBACK")

        assert v2_conn.in_transaction is False
        row_count = v2_conn.execute(
            "SELECT COUNT(*) FROM events WHERE uuid = ?", (event_uuid,)
        ).fetchone()[0]
        assert row_count == 0

    def test_standalone_unknown_entity_uuid_raises_with_no_partial_row(self, v2_conn):
        with pytest.raises(sqlite3.IntegrityError):
            events.append_event(
                v2_conn, entity_uuid="entity-uuid-does-not-exist",
                event_type="phase_completed", axis="pipeline", actor="test-actor",
            )

        assert v2_conn.in_transaction is False
        row_count = v2_conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert row_count == 0
        # Connection remains usable after the failure.
        assert v2_conn.execute("SELECT 1").fetchone() == (1,)

    def test_two_threads_own_connections_append_two_distinct_uuids(
        self, bootstrapped_db_path, seeded_entity_uuid
    ):
        minted_uuids: dict[str, str] = {}

        def append_from_thread(thread_label):
            thread_conn = events.connect_v2(bootstrapped_db_path)
            try:
                minted_uuids[thread_label] = events.append_event(
                    thread_conn, entity_uuid=seeded_entity_uuid,
                    event_type="phase_completed", axis="pipeline",
                    actor=thread_label,
                )
            finally:
                thread_conn.close()

        thread_a = threading.Thread(target=append_from_thread, args=("thread-a",))
        thread_b = threading.Thread(target=append_from_thread, args=("thread-b",))
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=10)
        thread_b.join(timeout=10)

        assert minted_uuids["thread-a"] != minted_uuids["thread-b"]
        verify_conn = sqlite3.connect(bootstrapped_db_path)
        try:
            row_count = verify_conn.execute(
                "SELECT COUNT(*) FROM events WHERE uuid IN (?, ?)",
                (minted_uuids["thread-a"], minted_uuids["thread-b"]),
            ).fetchone()[0]
        finally:
            verify_conn.close()
        assert row_count == 2


# ---------------------------------------------------------------------------
# Design test #4 (d): retry-path pin (SC4d)
# ---------------------------------------------------------------------------
class _FirstBeginImmediateLockedConnection:
    """Wraps a real sqlite3.Connection: the FIRST execute() of "BEGIN
    IMMEDIATE" raises a transient OperationalError; every other call
    (including later BEGIN IMMEDIATE attempts) delegates straight
    through.

    Exercises with_retry's retry path deterministically — and, because
    the injected failure happens BEFORE any transaction opens, pins the
    guarded `if conn.in_transaction: conn.execute("ROLLBACK")` in
    append_event's except clause (design D5): an unguarded "ROLLBACK"
    there would itself raise "cannot rollback - no transaction is
    active", masking the retryable error and defeating with_retry.
    """

    def __init__(self, real_conn: sqlite3.Connection):
        self._real_conn = real_conn
        self.begin_immediate_attempts = 0

    def execute(self, sql, *args, **kwargs):
        if sql == "BEGIN IMMEDIATE":
            self.begin_immediate_attempts += 1
            if self.begin_immediate_attempts == 1:
                raise sqlite3.OperationalError("database is locked")
        return self._real_conn.execute(sql, *args, **kwargs)

    @property
    def in_transaction(self):
        return self._real_conn.in_transaction


class TestAppendEventRetryPath:
    def test_first_begin_immediate_locked_then_retry_succeeds(
        self, monkeypatch, bootstrapped_db_path, seeded_entity_uuid
    ):
        monkeypatch.setattr(time, "sleep", lambda seconds: None)

        real_conn = events.connect_v2(bootstrapped_db_path)
        wrapper_conn = _FirstBeginImmediateLockedConnection(real_conn)
        try:
            event_uuid = events.append_event(
                wrapper_conn, entity_uuid=seeded_entity_uuid,
                event_type="phase_completed", axis="pipeline", actor="test-actor",
            )
        finally:
            real_conn.close()

        assert wrapper_conn.begin_immediate_attempts == 2

        verify_conn = sqlite3.connect(bootstrapped_db_path)
        try:
            row_count = verify_conn.execute(
                "SELECT COUNT(*) FROM events WHERE uuid = ?", (event_uuid,)
            ).fetchone()[0]
        finally:
            verify_conn.close()
        assert row_count == 1


# ---------------------------------------------------------------------------
# Design test #5: FK-enforcement positive/negative pair
# ---------------------------------------------------------------------------
class TestForeignKeyEnforcementPair:
    """entity_uuid FK enforcement is a property of connect_v2's PRAGMA
    contract (foreign_keys=ON), not the schema itself — a bare
    sqlite3.connect bypasses it entirely. This documents the factory is
    load-bearing (design D1/D5)."""

    def test_connect_v2_rejects_unknown_entity_uuid(self, v2_conn):
        with pytest.raises(sqlite3.IntegrityError):
            events.append_event(
                v2_conn, entity_uuid="entity-uuid-does-not-exist",
                event_type="phase_completed", axis="pipeline", actor="test-actor",
            )

    def test_bare_connection_inserts_the_same_orphan_successfully(self, tmp_path):
        """Runs on its OWN fresh tmp_path (not the shared
        bootstrapped_db_path fixture): the orphan row this test inserts
        can never be cleaned up afterward — events are immutable even on
        a bare connection (SC2), so DELETE is trigger-blocked here too.
        A dedicated throwaway DB keeps that permanent row from polluting
        a database any other test depends on."""
        throwaway_db_path = str(tmp_path / "throwaway.db")
        setup_conn = schema_v2.bootstrap_v2(throwaway_db_path)
        setup_conn.close()

        bare_conn = sqlite3.connect(throwaway_db_path)
        try:
            bare_conn.execute(
                "INSERT INTO events "
                "(uuid, entity_uuid, event_type, axis, actor, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    "orphan-event-uuid", "entity-uuid-does-not-exist",
                    "phase_completed", "pipeline", "test-actor", _NOW,
                ),
            )
            bare_conn.commit()
            row_count = bare_conn.execute(
                "SELECT COUNT(*) FROM events WHERE uuid = ?", ("orphan-event-uuid",)
            ).fetchone()[0]
        finally:
            bare_conn.close()
        assert row_count == 1


# ---------------------------------------------------------------------------
# Design test #6: payload registry round-trip + non-serializable TypeError
# ---------------------------------------------------------------------------
class TestPayloadRegistry:
    def test_payload_dict_round_trips_via_read_events(self, v2_conn, seeded_entity_uuid):
        payload = {
            "iterations": 2,
            "reviewerNotes": "looks good",
            "skippedPhases": ["design"],
            "mode": "standard",
            "branch": "feature/119-append-only-event-log",
            "brainstorm_source": "docs/brainstorms/example.md",
            "backlog_source": "docs/backlog.md",
        }
        event_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", actor="test-actor", payload=payload,
        )
        rows = events.read_events(v2_conn, seeded_entity_uuid)
        (matching_row,) = [row for row in rows if row["uuid"] == event_uuid]
        assert matching_row["payload"] == payload

    def test_non_serializable_payload_raises_type_error_before_any_sql(
        self, v2_conn, seeded_entity_uuid
    ):
        non_serializable_payload = {"bad_value": {1, 2, 3}}  # a set is not JSON serializable

        with pytest.raises(TypeError):
            events.append_event(
                v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
                axis="pipeline", actor="test-actor", payload=non_serializable_payload,
            )

        assert v2_conn.in_transaction is False
        row_count = v2_conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert row_count == 0
