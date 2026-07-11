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

import subprocess
import sqlite3
import sys
import threading
import time
from pathlib import Path

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

    # -----------------------------------------------------------------
    # Gap pass (test-deepener, dimension:boundary_values): every existing
    # test in this class either omits *timestamp* (exercising the
    # default UTC-now stamp) or never inspects it — passing one
    # explicitly was unexercised.
    # -----------------------------------------------------------------
    def test_explicit_timestamp_is_stored_verbatim_not_restamped(
        self, v2_conn, seeded_entity_uuid
    ):
        """Anticipate: an implementation that always stamps
        datetime.now(timezone.utc) regardless of a caller-supplied
        *timestamp* (e.g. a branch that ignores the caller-supplied timestamp and stamps now() unconditionally)
        would silently overwrite this with something close to "now" —
        this test fails against that mutation because 2020 is asserted
        verbatim and would be wildly different from "now".
        derived_from: spec:In-Scope item 3 (append_event timestamp
        parameter), dimension:boundary_values
        """
        # Given a timestamp far from "now" passed explicitly
        explicit_timestamp = "2020-06-15T12:00:00+00:00"
        # When append_event is called with that timestamp
        event_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", actor="test-actor", timestamp=explicit_timestamp,
        )
        # Then the stored row carries it verbatim, not a re-stamped "now"
        rows = events.read_events(v2_conn, seeded_entity_uuid)
        (matching_row,) = [row for row in rows if row["uuid"] == event_uuid]
        assert matching_row["timestamp"] == explicit_timestamp


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

    # -----------------------------------------------------------------
    # Gap pass (test-deepener, dimension:adversarial): the mirror image of
    # the rollback test above — only the discard half of the composition
    # contract was pinned; the persist half never was.
    # -----------------------------------------------------------------
    def test_caller_transaction_commit_persists_the_event(self, v2_conn, seeded_entity_uuid):
        """The caller commits its own transaction with raw SQL (same
        autocommit=True / raw-SQL rationale as the rollback sibling
        above) — the event must actually be readable afterward, not just
        "append_event didn't raise".

        Anticipate: a mutation that had append_event issue its own
        COMMIT/ROLLBACK even when conn.in_transaction is True (breaking
        the compose-or-wrap contract, design D5) would make the caller's
        own COMMIT below either double-commit or hit "cannot commit - no
        transaction is active" — this test's positive persistence
        assertion is the half of the contract the rollback sibling
        structurally cannot exercise.
        derived_from: spec:SC4a (transaction composition), design:D5,
        dimension:adversarial
        """
        # Given a caller-owned transaction
        v2_conn.execute("BEGIN IMMEDIATE")
        # When append_event runs inside it and the CALLER commits
        event_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", actor="test-actor",
        )
        v2_conn.execute("COMMIT")

        # Then the event is actually persisted, not just exception-free
        assert v2_conn.in_transaction is False
        row_count = v2_conn.execute(
            "SELECT COUNT(*) FROM events WHERE uuid = ?", (event_uuid,)
        ).fetchone()[0]
        assert row_count == 1

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


# ---------------------------------------------------------------------------
# Gap pass (test-deepener, dimension:error_propagation): with_retry
# EXHAUSTION. _FirstBeginImmediateLockedConnection above only fails the
# first attempt then lets the retry succeed — the boundary where every
# attempt fails (max_attempts reached, sqlite_retry.py's default is 3) was
# unexercised, so nothing pinned that the error actually propagates
# instead of looping forever or being swallowed.
# ---------------------------------------------------------------------------
class _AlwaysBeginImmediateLockedConnection:
    """Wraps a real sqlite3.Connection: EVERY execute() of "BEGIN
    IMMEDIATE" raises a transient OperationalError, unconditionally —
    unlike _FirstBeginImmediateLockedConnection above, no attempt ever
    succeeds. Drives with_retry to its exhaustion path."""

    def __init__(self, real_conn: sqlite3.Connection):
        self._real_conn = real_conn
        self.begin_immediate_attempts = 0

    def execute(self, sql, *args, **kwargs):
        if sql == "BEGIN IMMEDIATE":
            self.begin_immediate_attempts += 1
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

    def test_always_locked_exhausts_retries_and_propagates(
        self, monkeypatch, bootstrapped_db_path, seeded_entity_uuid
    ):
        """Anticipate: a bug that swallows the exhausted OperationalError
        (e.g. returning a sentinel instead of `raise last_exc`) or one
        that retries indefinitely (hangs) would either return silently
        here or never complete — this test fails against both: it
        asserts the specific exception propagates AND that exactly
        max_attempts (3, sqlite_retry.py's current default) BEGIN
        IMMEDIATE attempts were made — not more (no infinite loop) and
        not fewer (retry actually happened).
        derived_from: spec:In-Scope item 3 (NFR-1 with_retry clause),
        dimension:error_propagation
        """
        monkeypatch.setattr(time, "sleep", lambda seconds: None)

        # Given a connection where BEGIN IMMEDIATE always reports "locked"
        real_conn = events.connect_v2(bootstrapped_db_path)
        wrapper_conn = _AlwaysBeginImmediateLockedConnection(real_conn)
        try:
            # When append_event is called standalone
            # Then the OperationalError propagates after exactly 3 attempts
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                events.append_event(
                    wrapper_conn, entity_uuid=seeded_entity_uuid,
                    event_type="phase_completed", axis="pipeline", actor="test-actor",
                )
        finally:
            real_conn.close()

        assert wrapper_conn.begin_immediate_attempts == 3


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
# Design test (SC4, design D3): #061 guard — append_event's first statement
# probes PRAGMA foreign_keys and rejects any non-connect_v2 connection
# before the conn.in_transaction branch runs, so both transaction-
# composition paths are covered by construction.
# ---------------------------------------------------------------------------
class TestAppendEventConnectionGuard:
    """TestForeignKeyEnforcementPair above documents that a bare
    connection silently disables FK enforcement; this class documents
    that append_event itself now refuses to write through one at all
    (backlog #061), independent of whether the write would otherwise
    have succeeded."""

    def test_bare_connection_standalone_raises_before_any_write(
        self, bootstrapped_db_path, seeded_entity_uuid
    ):
        bare_conn = sqlite3.connect(bootstrapped_db_path)
        try:
            with pytest.raises(ValueError, match="connect_v2"):
                events.append_event(
                    bare_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
                    axis="pipeline", actor="test-actor",
                )
            row_count = bare_conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            assert row_count == 0
        finally:
            bare_conn.close()

    def test_bare_connection_with_open_transaction_raises_before_any_write(
        self, bootstrapped_db_path, seeded_entity_uuid
    ):
        """The compose path (caller already opened a transaction): the
        probe runs before the `conn.in_transaction` branch, so this
        raises identically to the standalone case above."""
        bare_conn = sqlite3.connect(bootstrapped_db_path)
        try:
            bare_conn.execute("BEGIN IMMEDIATE")
            with pytest.raises(ValueError, match="connect_v2"):
                events.append_event(
                    bare_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
                    axis="pipeline", actor="test-actor",
                )
            row_count = bare_conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            assert row_count == 0
        finally:
            bare_conn.close()

    def test_connect_v2_connection_passes_the_guard_unchanged(
        self, v2_conn, seeded_entity_uuid
    ):
        """Smoke test: a connect_v2 connection (foreign_keys=ON) is
        unaffected by the guard — the broader regression net is the
        rest of this file's append_event suite, all of which already
        runs through connect_v2 or a proxy over one."""
        event_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", actor="test-actor",
        )
        row_count = v2_conn.execute(
            "SELECT COUNT(*) FROM events WHERE uuid = ?", (event_uuid,)
        ).fetchone()[0]
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

    # -----------------------------------------------------------------
    # Gap pass (test-deepener, dimension:boundary_values): the round-trip
    # test above always supplies a non-empty payload dict — the None
    # default and the falsy-but-non-null {} case were both unexercised.
    # -----------------------------------------------------------------
    def test_payload_omitted_round_trips_as_none(self, v2_conn, seeded_entity_uuid):
        # Given append_event called with no payload argument
        event_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", actor="test-actor",
        )
        # When the row is read back
        rows = events.read_events(v2_conn, seeded_entity_uuid)
        (matching_row,) = [row for row in rows if row["uuid"] == event_uuid]
        # Then payload is None, not the string "null" or an empty dict
        assert matching_row["payload"] is None
        # SQL-level pin (QA-gate C1): omitted payload is a REAL SQL NULL —
        # one representation of "no payload" in the immutable log, so 120's
        # projections / 132's backfill can trust IS NULL semantics.
        row_type = v2_conn.execute(
            "SELECT typeof(payload) FROM events WHERE uuid = ?", (event_uuid,)
        ).fetchone()[0]
        assert row_type == "null"

    def test_payload_empty_dict_round_trips_as_empty_dict_not_none(
        self, v2_conn, seeded_entity_uuid
    ):
        """Anticipate: a payload-serialization helper written as
        `json.dumps(payload) if payload else None` (a truthy guard
        instead of an `is not None` check) would silently collapse an
        explicitly-empty dict into SQL NULL, since `{}` is falsy in
        Python — this test fails against that mutation because it
        asserts the read-back value IS `{}`, distinct from the None the
        sibling test above pins for the omitted case.
        derived_from: spec:In-Scope item 1 (payload TEXT, nullable),
        dimension:boundary_values
        """
        # Given append_event called with an explicit empty dict payload
        event_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", actor="test-actor", payload={},
        )
        # When the row is read back
        rows = events.read_events(v2_conn, seeded_entity_uuid)
        (matching_row,) = [row for row in rows if row["uuid"] == event_uuid]
        # Then payload is {}, not coalesced into None
        assert matching_row["payload"] == {}
        assert matching_row["payload"] is not None


# ---------------------------------------------------------------------------
# Gap pass (test-deepener, dimension:boundary_values): axis CHECK boundary
# — every existing test in this file hardcodes axis="pipeline"; the other
# two valid values and the CHECK's case-sensitivity were unexercised.
# ---------------------------------------------------------------------------
class TestAxisBoundaryValues:
    @pytest.mark.parametrize("axis_value", ["pipeline", "execution", "lifecycle"])
    def test_each_valid_axis_value_round_trips(
        self, v2_conn, seeded_entity_uuid, axis_value
    ):
        """Anticipate: a CHECK constraint (or an equivalent Python-side
        allowlist) that only lists two of the three axis values — e.g. a
        typo'd 'exection', or a copy/paste that dropped 'lifecycle' —
        would still pass every OTHER test in this suite, all of which
        hardcode 'pipeline'. This parametrized sweep exercises each of
        the three values individually so a narrowed CHECK fails loudly
        on exactly the value it silently dropped.
        derived_from: spec:In-Scope item 1 (axis CHECK), design:D7,
        dimension:boundary_values
        """
        # Given one of the three spec-documented axis values
        # When an event is appended with it
        event_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis=axis_value, actor="test-actor",
        )
        # Then it round-trips through read_events unchanged
        rows = events.read_events(v2_conn, seeded_entity_uuid)
        (matching_row,) = [row for row in rows if row["uuid"] == event_uuid]
        assert matching_row["axis"] == axis_value

    def test_axis_case_variant_is_rejected_by_check_constraint(
        self, v2_conn, seeded_entity_uuid
    ):
        """'Pipeline' (capital P) is not one of the three literal CHECK
        values — SQLite's IN comparison is case-sensitive for TEXT by
        default (no COLLATE NOCASE in the DDL), so this must be rejected
        outright, not silently normalized.

        Anticipate: a Python-side pre-validation added later that
        lowercases *axis* before the INSERT (e.g. `axis.lower()`) would
        silently accept this and mask the CHECK's case-sensitivity
        contract — this test fails against that mutation both via the
        expected exception AND the follow-up zero-rows assertion (not
        just "no exception happened").
        derived_from: design:D7 (exact axis CHECK values),
        dimension:boundary_values
        """
        # Given a case-variant of a valid axis value
        # When append_event is called with it
        # Then the CHECK constraint rejects it, with no row inserted
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            events.append_event(
                v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
                axis="Pipeline", actor="test-actor",
            )
        row_count = v2_conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert row_count == 0


# ---------------------------------------------------------------------------
# Gap pass (test-deepener, dimension:boundary_values): from_value/to_value
# — spec's Error & Boundary Cases notes CHECKs only cover event_type/actor,
# leaving from_value/to_value nullable with no CHECK; no existing test ever
# passes either one.
# ---------------------------------------------------------------------------
class TestFromToValueBoundaries:
    def test_from_value_and_to_value_default_to_none_when_omitted(
        self, v2_conn, seeded_entity_uuid
    ):
        # Given append_event called without from_value/to_value
        event_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="entity_created",
            axis="pipeline", actor="test-actor",
        )
        # When the row is read back
        rows = events.read_events(v2_conn, seeded_entity_uuid)
        (matching_row,) = [row for row in rows if row["uuid"] == event_uuid]
        # Then both columns are None (creation events have no "from")
        assert matching_row["from_value"] is None
        assert matching_row["to_value"] is None

    def test_from_value_and_to_value_empty_string_round_trips_distinct_from_none(
        self, v2_conn, seeded_entity_uuid
    ):
        """Anticipate: a helper that coalesces falsy values (e.g.
        `from_value or None`) before the INSERT would silently turn an
        explicit empty string into SQL NULL, blurring "explicitly empty"
        with "never set" — this test fails against that mutation because
        it asserts the read-back value IS the empty string, distinct
        from the None the sibling test above pins for the omitted case.
        derived_from: spec:Error & Boundary Cases (from_value/to_value
        nullable, no CHECK), dimension:boundary_values
        """
        # Given append_event called with explicit empty-string from/to values
        event_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="transition",
            axis="pipeline", from_value="", to_value="", actor="test-actor",
        )
        # When the row is read back
        rows = events.read_events(v2_conn, seeded_entity_uuid)
        (matching_row,) = [row for row in rows if row["uuid"] == event_uuid]
        # Then both columns are "", not coalesced into None
        assert matching_row["from_value"] == ""
        assert matching_row["to_value"] == ""


# ---------------------------------------------------------------------------
# Gap pass (test-deepener, dimension:adversarial): read_events' filters —
# no existing test interleaves two entities' appends (every read_events
# call in this file operates against a single entity_uuid in isolation),
# and no existing test ever passes axis= at all.
# ---------------------------------------------------------------------------
class TestReadEventsFiltering:
    def test_interleaved_appends_across_two_entities_preserve_per_entity_order(
        self, v2_conn
    ):
        """Two entities' appends interleave in insertion order (A1, B1,
        A2, B2, i.e. NOT grouped by entity): read_events(entity) must
        return only THAT entity's rows, in their own insertion order —
        not the other entity's rows mixed in, and not merely "whatever
        order the table happens to be in".

        Anticipate: a read_events that dropped or mis-targeted its
        entity_uuid WHERE clause would still pass the existing
        single-entity sequential-order test (nothing else is in that
        table to leak in) but would return all 4 rows here — this test
        fails against that mutation because entity B's rows are
        interleaved and would surface in entity A's read.
        derived_from: dimension:adversarial (Follow the Data / interleaving)
        """
        # Given two entities under one workspace
        workspace_uuid = "workspace-uuid-interleave-test"
        entity_a = "entity-uuid-interleave-a"
        entity_b = "entity-uuid-interleave-b"
        v2_conn.execute(
            "INSERT INTO workspaces (uuid, project_root, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (workspace_uuid, "/tmp/project", _NOW, _NOW),
        )
        for entity_uuid in (entity_a, entity_b):
            v2_conn.execute(
                "INSERT INTO entities (uuid, workspace_uuid, type, kind, lifecycle_class, "
                "type_id, name, artifact_path, parent_uuid, created_at, updated_at, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entity_uuid, workspace_uuid, "feature", "feature", "artifact",
                    "119-interleave", "Test Entity", None, None, _NOW, _NOW, None,
                ),
            )

        # When appends interleave across the two entities: A1, B1, A2, B2
        first_a_uuid = events.append_event(
            v2_conn, entity_uuid=entity_a, event_type="event-a1",
            axis="pipeline", actor="test-actor",
        )
        first_b_uuid = events.append_event(
            v2_conn, entity_uuid=entity_b, event_type="event-b1",
            axis="pipeline", actor="test-actor",
        )
        second_a_uuid = events.append_event(
            v2_conn, entity_uuid=entity_a, event_type="event-a2",
            axis="pipeline", actor="test-actor",
        )
        second_b_uuid = events.append_event(
            v2_conn, entity_uuid=entity_b, event_type="event-b2",
            axis="pipeline", actor="test-actor",
        )

        # Then each entity's read_events returns only its own rows, in order
        assert [row["uuid"] for row in events.read_events(v2_conn, entity_a)] == [
            first_a_uuid, second_a_uuid,
        ]
        assert [row["uuid"] for row in events.read_events(v2_conn, entity_b)] == [
            first_b_uuid, second_b_uuid,
        ]

    def test_axis_filter_excludes_other_axis_rows_for_same_entity(
        self, v2_conn, seeded_entity_uuid
    ):
        """One entity, two events on different axes: axis= filters
        correctly both ways, and the no-filter call still returns both.

        Anticipate: a read_events whose axis branch targeted the wrong
        column (e.g. filtered on event_type instead of axis) or whose
        `if axis is None` check was inverted would either return the
        wrong subset or an empty list here — no existing test calls
        read_events with axis= at all.
        derived_from: spec:In-Scope item 4 (read_events axis filter),
        dimension:adversarial
        """
        # Given one entity with events on two different axes
        pipeline_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", actor="test-actor",
        )
        lifecycle_uuid = events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="entity_archived",
            axis="lifecycle", actor="test-actor",
        )

        # When read_events is called with axis="pipeline"
        # Then only the pipeline-axis row comes back
        pipeline_rows = events.read_events(v2_conn, seeded_entity_uuid, axis="pipeline")
        assert [row["uuid"] for row in pipeline_rows] == [pipeline_uuid]

        # When read_events is called with axis="lifecycle"
        # Then only the lifecycle-axis row comes back
        lifecycle_rows = events.read_events(v2_conn, seeded_entity_uuid, axis="lifecycle")
        assert [row["uuid"] for row in lifecycle_rows] == [lifecycle_uuid]

        # When read_events is called with no axis filter
        # Then both rows come back
        all_rows = events.read_events(v2_conn, seeded_entity_uuid)
        assert {row["uuid"] for row in all_rows} == {pipeline_uuid, lifecycle_uuid}


# ---------------------------------------------------------------------------
# Gap pass (test-deepener, dimension:error_propagation): append_event
# against a core-only bootstrap (events.py never imported before
# bootstrap_v2 ran) — design's Data Flow (dark-phase) section documents
# this hazard, but nothing pinned it. This requires a genuinely fresh
# subprocess: this module's own top-level `from entity_registry import
# events` import (module top of this file) has already registered the
# events DDL for THIS test process by the time any test here runs, so the
# "core-only" scenario cannot be reproduced in-process.
# ---------------------------------------------------------------------------
class TestCoreOnlyBootstrapMissingEventsTable:
    def test_append_event_on_core_only_bootstrap_raises_no_such_table(self, tmp_path):
        """Anticipate: if append_event (or connect_v2) silently created
        missing tables on demand, or if importing events retroactively
        applied its DDL to already-bootstrapped paths, this documented
        dark-phase hazard would go unnoticed until feature 132's cutover
        hit it live — this test fails against either "helpful" mutation
        because it asserts the SPECIFIC no-such-table failure the design
        docstring predicts, not just "some exception happens".
        derived_from: design:Data Flow (dark-phase) section,
        dimension:error_propagation
        """
        hooks_lib_root = Path(__file__).resolve().parent.parent
        db_path = str(tmp_path / "core-only.db")
        # Given a subprocess that bootstraps a path having imported ONLY
        # schema_v2 (never entity_registry.events) — a core-only DB —
        # and only imports events AFTER that bootstrap already ran
        script = (
            "import sqlite3\n"
            "from entity_registry import schema_v2\n"
            f"conn = schema_v2.bootstrap_v2({db_path!r})\n"
            "conn.close()\n"
            "from entity_registry import events\n"
            f"v2_conn = events.connect_v2({db_path!r})\n"
            "try:\n"
            "    events.append_event(\n"
            "        v2_conn, entity_uuid='entity-uuid-does-not-matter',\n"
            "        event_type='phase_completed', axis='pipeline', actor='test-actor',\n"
            "    )\n"
            "except sqlite3.OperationalError as exc:\n"
            "    print('CAUGHT:' + str(exc))\n"
            "else:\n"
            "    print('NO_ERROR_RAISED')\n"
        )
        # When append_event is called against that core-only DB
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(hooks_lib_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Then it raises OperationalError("no such table: events") — the
        # exact failure design's Data Flow section predicts
        assert result.returncode == 0, (
            f"subprocess crashed unexpectedly: stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        )
        assert "CAUGHT:no such table: events" in result.stdout, (
            f"expected the core-only path's append_event to fail with "
            f"'no such table: events', got stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# Gap pass (test-deepener, dimension:mutation_mindset): read_events' output
# shape — pins the exact 9-column dict-key contract so column drift (add/
# rename/reorder) between the DDL, _EVENT_COLUMNS, and either SELECT
# statement shows up here instead of silently leaking through to callers.
# ---------------------------------------------------------------------------
class TestReadEventsColumnContract:
    def test_read_events_dict_keys_match_exactly_nine_documented_columns(
        self, v2_conn, seeded_entity_uuid
    ):
        """Anticipate: a future column addition to the events table
        (schema drift — e.g. a 120/121/122 sibling ALTERing the table)
        that isn't mirrored into _EVENT_COLUMNS and both SELECT
        statements in lockstep would leave read_events silently missing
        the new column from its dict output, or leak a stray extra key
        — this test fails against either drift direction because it
        asserts set EQUALITY, not just membership of the known keys.
        derived_from: spec:SC1 (exact FR-2 column set), design:D7,
        dimension:mutation_mindset
        """
        events.append_event(
            v2_conn, entity_uuid=seeded_entity_uuid, event_type="phase_completed",
            axis="pipeline", actor="test-actor",
        )
        (row,) = events.read_events(v2_conn, seeded_entity_uuid)
        assert set(row.keys()) == {
            "uuid", "entity_uuid", "event_type", "axis",
            "from_value", "to_value", "actor", "timestamp", "payload",
        }
