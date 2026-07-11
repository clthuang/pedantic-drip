"""Tests for entity_registry.display (dark-shipped v2 display-id allocator
+ rename-event helper).

Covers design 121 Testing Strategy #4 (dark allocator, ``next_display_seq``)
and #5 (dark rename, ``rename_entity``): monotonic issuance, transaction
composition (caller-owned compose vs. standalone with_retry, both the
happy and rollback paths), genuine multi-process and multi-thread
contention (no lost update / no duplicate / no gap), seeded-duplicate-row
convergence, the compose-precondition docstring pin, and rename's
event-emission shape (from/to + camelCase payload, both explicit-NULL
branches, rollback atomicity, and structural no-touch of uuid/relations).

Imports ``display`` at module top like its siblings (test_events.py,
test_schema_v2.py) — display.py's own ``from entity_registry.events
import append_event`` transitively imports ``entity_registry.events``,
whose module-top side effect (``schema_v2.register_ddl("events", ...)``)
is how the events DDL gets registered into DDL_REGISTRY at all; every
bootstrap_v2 call in this file picks up both core + events DDL as a
result.
"""
from __future__ import annotations

import multiprocessing
import sqlite3
import threading
import time

import pytest

from entity_registry import display
from entity_registry import events
from entity_registry import schema_v2

_NOW = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_ddl_registry():
    """Snapshot/restore DDL_REGISTRY around every test (mirrors
    test_schema_v2.py's fixture of the same name/purpose — this package
    has no shared conftest.py, so each test module defines its own)."""
    original_registry = list(schema_v2.DDL_REGISTRY)
    yield
    schema_v2.DDL_REGISTRY[:] = original_registry


@pytest.fixture
def bootstrapped_db_path(tmp_path):
    """Fresh v2 DB path with core + events DDL applied (the module-top
    ``display`` import above transitively registers "events" — see the
    module docstring)."""
    db_path = str(tmp_path / "v2.db")
    conn = schema_v2.bootstrap_v2(db_path)
    conn.close()
    return db_path


def _seed_workspace(db_path: str, workspace_uuid: str) -> None:
    """Insert one workspaces row directly — the FK target
    ``sequences.workspace_uuid``/``entities.workspace_uuid`` reference."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO workspaces (uuid, project_root, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (workspace_uuid, "/tmp/project", _NOW, _NOW),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def seeded_entity_uuid(bootstrapped_db_path):
    """Insert one workspace + one entity row directly; return the
    entity's uuid — rename_entity's tests read/update this row."""
    workspace_uuid = "workspace-uuid-display-test"
    entity_uuid = "entity-uuid-display-test"
    _seed_workspace(bootstrapped_db_path, workspace_uuid)
    conn = sqlite3.connect(bootstrapped_db_path)
    try:
        conn.execute(
            "INSERT INTO entities (uuid, workspace_uuid, type, kind, lifecycle_class, "
            "type_id, name, artifact_path, parent_uuid, created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entity_uuid, workspace_uuid, "feature", "feature", "artifact",
                "121-original-type-id", "Original Name", None, None,
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
# Design D5 / Testing Strategy #4a: monotonic issuance
# ---------------------------------------------------------------------------
class TestNextDisplaySeqMonotonic:
    def test_three_standalone_calls_issue_one_two_three(self, bootstrapped_db_path):
        workspace_uuid = "workspace-uuid-monotonic"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        conn = sqlite3.connect(bootstrapped_db_path, autocommit=True)
        try:
            first = display.next_display_seq(conn, workspace_uuid=workspace_uuid, kind="feature")
            row_count_after_first = conn.execute(
                "SELECT COUNT(*) FROM sequences WHERE workspace_uuid = ? AND kind = ?",
                (workspace_uuid, "feature"),
            ).fetchone()[0]
            second = display.next_display_seq(conn, workspace_uuid=workspace_uuid, kind="feature")
            third = display.next_display_seq(conn, workspace_uuid=workspace_uuid, kind="feature")
        finally:
            conn.close()
        assert (first, second, third) == (1, 2, 3)
        # The insert-if-absent branch of _bump creates exactly one row —
        # the second/third calls above hit the update branch instead.
        assert row_count_after_first == 1

    def test_distinct_kind_within_same_workspace_starts_its_own_count(
        self, bootstrapped_db_path
    ):
        """A different `kind` under the SAME workspace gets its own
        independent count starting at 1 — the allocator scopes by
        (workspace_uuid, kind), not workspace_uuid alone."""
        workspace_uuid = "workspace-uuid-monotonic-kinds"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        conn = sqlite3.connect(bootstrapped_db_path, autocommit=True)
        try:
            feature_seq = display.next_display_seq(
                conn, workspace_uuid=workspace_uuid, kind="feature"
            )
            backlog_seq = display.next_display_seq(
                conn, workspace_uuid=workspace_uuid, kind="backlog"
            )
            feature_seq_2 = display.next_display_seq(
                conn, workspace_uuid=workspace_uuid, kind="feature"
            )
        finally:
            conn.close()
        assert feature_seq == 1
        assert backlog_seq == 1
        assert feature_seq_2 == 2


# ---------------------------------------------------------------------------
# Design D5: compose mode leaves transaction control with the caller
# (mirrors test_events.py's TestAppendEventTransactionComposition
# commit/rollback pair).
# ---------------------------------------------------------------------------
class TestNextDisplaySeqComposeMode:
    def test_compose_mode_leaves_transaction_open_caller_commits(self, bootstrapped_db_path):
        workspace_uuid = "workspace-uuid-compose-commit"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        conn = sqlite3.connect(bootstrapped_db_path, autocommit=True)
        try:
            conn.execute("BEGIN IMMEDIATE")
            issued = display.next_display_seq(conn, workspace_uuid=workspace_uuid, kind="feature")
            assert issued == 1
            # Compose mode does not commit on its own — the caller still
            # owns the transaction.
            assert conn.in_transaction is True
            conn.execute("COMMIT")

            row = conn.execute(
                "SELECT current_value FROM sequences WHERE workspace_uuid = ? AND kind = ?",
                (workspace_uuid, "feature"),
            ).fetchone()
            assert row[0] == 1
        finally:
            conn.close()

    def test_compose_mode_caller_rollback_discards_the_bump(self, bootstrapped_db_path):
        workspace_uuid = "workspace-uuid-compose-rollback"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        conn = sqlite3.connect(bootstrapped_db_path, autocommit=True)
        try:
            conn.execute("BEGIN IMMEDIATE")
            display.next_display_seq(conn, workspace_uuid=workspace_uuid, kind="feature")
            conn.execute("ROLLBACK")

            assert conn.in_transaction is False
            row_count = conn.execute(
                "SELECT COUNT(*) FROM sequences WHERE workspace_uuid = ? AND kind = ?",
                (workspace_uuid, "feature"),
            ).fetchone()[0]
            assert row_count == 0
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Module-level worker for the two-process standalone allocation race (design
# D5 Testing Strategy #4b). Must be a top-level function: the default
# multiprocessing start method on darwin (and this suite's CI) is "spawn",
# which pickles a module-qualified function reference to hand the target to
# the child process — a closure or nested function is not picklable under
# spawn (mirrors test_schema_v2.py's _bootstrap_v2_race_worker).
# ---------------------------------------------------------------------------
def _next_display_seq_worker(
    db_path: str, workspace_uuid: str, kind: str, call_count: int, result_queue
) -> None:
    """Worker process: issue *call_count* standalone next_display_seq
    calls against db_path, reporting each issued value on result_queue.

    Each call gets its own BEGIN IMMEDIATE/COMMIT cycle (this IS the
    standalone path under test) — a large busy_timeout absorbs ordinary
    contention from the sibling process at the SQLite level so the
    30-trial race stresses next_display_seq's correctness, not
    with_retry's exhaustion ceiling.
    """
    conn = sqlite3.connect(db_path, autocommit=True)
    conn.execute(f"PRAGMA busy_timeout = {schema_v2._BUSY_TIMEOUT_MS}")
    try:
        for _ in range(call_count):
            seq = display.next_display_seq(conn, workspace_uuid=workspace_uuid, kind=kind)
            result_queue.put(seq)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Design D5 / Testing Strategy #4b: standalone two-process race, 30 trials.
# ---------------------------------------------------------------------------
class TestNextDisplaySeqStandaloneProcessRace:
    def test_thirty_trials_two_process_standalone_no_lost_no_duplicate_no_gap(
        self, tmp_path
    ):
        """30 independent trials, each racing 2 fresh processes (5 calls
        each = 10 issuances per trial) against a fresh db path + a shared
        (workspace, kind). The test_schema_v2.py:708 pattern this mirrors
        (test_thirty_trials_two_process_bootstrap_race_both_succeed) only
        asserts exitcode==0, which is vacuous for a write race — duplicate
        issuance would not crash either worker. Here every issued value is
        REPORTED via a multiprocessing.Queue so the parent can assert the
        combined result is exactly the contiguous range 1..10 — no
        duplicates (an update-all bug would forge one) and no gaps (a lost
        update would leave one).
        """
        num_trials = 30
        call_count = 5
        worker_count = 2
        expected_total = call_count * worker_count

        for trial in range(num_trials):
            db_path = str(tmp_path / f"race-{trial}.db")
            workspace_uuid = f"workspace-uuid-race-{trial}"

            # Parent pre-bootstraps the DB and seeds the workspace row.
            conn = schema_v2.bootstrap_v2(db_path)
            conn.close()
            _seed_workspace(db_path, workspace_uuid)

            result_queue: multiprocessing.Queue = multiprocessing.Queue()
            processes = [
                multiprocessing.Process(
                    target=_next_display_seq_worker,
                    args=(db_path, workspace_uuid, "feature", call_count, result_queue),
                )
                for _ in range(worker_count)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=15)
            for process in processes:
                assert process.exitcode == 0, (
                    f"trial {trial}: worker exited with code {process.exitcode}"
                )

            issued = [result_queue.get(timeout=5) for _ in range(expected_total)]
            assert sorted(issued) == list(range(1, expected_total + 1)), (
                f"trial {trial}: expected contiguous 1..{expected_total}, got {sorted(issued)}"
            )


# ---------------------------------------------------------------------------
# Design D5 / Testing Strategy #4c: compose-under-contention. Barrier/event
# idiom mirrors test_phase_events.py's TestFeature088Migration10Hardening /
# the AC-24 sync-point test (threading.Event confirming the holder is
# inside its transaction before the hammerer attempts its own).
# ---------------------------------------------------------------------------
class TestNextDisplaySeqComposeUnderContention:
    def test_compose_holder_blocks_standalone_hammerer_no_lost_update(
        self, bootstrapped_db_path
    ):
        """Thread A opens its own connection, BEGIN IMMEDIATE, calls
        next_display_seq in COMPOSE mode (conn.in_transaction True), and
        holds the transaction open past a synchronization point. Thread B,
        on a SEPARATE connection with busy_timeout=0 (so contention raises
        "database is locked" immediately instead of silently blocking
        inside SQLite's own busy handler), calls next_display_seq
        STANDALONE once A confirms it holds the lock — B's OWN
        ``@with_retry("sequences")`` decorator, not SQLite's busy_timeout,
        is what absorbs the failure and retries until A releases. No lost
        update: the two returned values are {1, 2} and the final
        current_value is 2.
        """
        workspace_uuid = "workspace-uuid-contention"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)

        a_holds_lock = threading.Event()
        b_attempted = threading.Event()
        results: dict[str, int] = {}
        errors: list[BaseException] = []

        def run_holder():
            try:
                conn_a = sqlite3.connect(bootstrapped_db_path, autocommit=True)
                try:
                    conn_a.execute("BEGIN IMMEDIATE")
                    results["a"] = display.next_display_seq(
                        conn_a, workspace_uuid=workspace_uuid, kind="feature",
                    )
                    a_holds_lock.set()
                    assert b_attempted.wait(timeout=5.0), "B never attempted"
                    # Hold the write lock a beat longer so B's first
                    # standalone attempt genuinely collides with it.
                    time.sleep(0.2)
                    conn_a.execute("COMMIT")
                finally:
                    conn_a.close()
            except BaseException as exc:
                errors.append(exc)

        def run_hammerer():
            try:
                assert a_holds_lock.wait(timeout=5.0), "A never confirmed holding the lock"
                conn_b = sqlite3.connect(bootstrapped_db_path, autocommit=True)
                try:
                    conn_b.execute("PRAGMA busy_timeout = 0")
                    b_attempted.set()
                    results["b"] = display.next_display_seq(
                        conn_b, workspace_uuid=workspace_uuid, kind="feature",
                    )
                finally:
                    conn_b.close()
            except BaseException as exc:
                errors.append(exc)

        holder_thread = threading.Thread(target=run_holder)
        hammerer_thread = threading.Thread(target=run_hammerer)
        holder_thread.start()
        hammerer_thread.start()
        holder_thread.join(timeout=15.0)
        hammerer_thread.join(timeout=15.0)
        assert not holder_thread.is_alive(), "holder thread hung"
        assert not hammerer_thread.is_alive(), "hammerer thread hung"

        assert errors == [], f"unexpected errors: {errors!r}"
        assert set(results.values()) == {1, 2}

        verify_conn = sqlite3.connect(bootstrapped_db_path)
        try:
            final_value = verify_conn.execute(
                "SELECT current_value FROM sequences WHERE workspace_uuid = ? AND kind = ?",
                (workspace_uuid, "feature"),
            ).fetchone()[0]
        finally:
            verify_conn.close()
        assert final_value == 2


# ---------------------------------------------------------------------------
# Design D5 / Testing Strategy #4: seeded-duplicate-row MAX issuance +
# update-all convergence.
# ---------------------------------------------------------------------------
class TestNextDisplaySeqDuplicateRows:
    def test_seeded_duplicate_rows_max_issuance_and_update_all_convergence(
        self, bootstrapped_db_path
    ):
        """Two pre-existing `sequences` rows share (workspace_uuid, kind)
        with different current_value (5 and 9) — a state FR-4 makes
        constructible (no UNIQUE(workspace_uuid, kind) index). The MAX()
        read must issue 10 (max + 1, not "whichever row SQLite happens to
        return first"), and the update-ALL-matching write must converge
        BOTH rows to 10 rather than leaving them diverged.
        """
        workspace_uuid = "workspace-uuid-dup-rows"
        _seed_workspace(bootstrapped_db_path, workspace_uuid)
        conn = sqlite3.connect(bootstrapped_db_path)
        try:
            conn.execute(
                "INSERT INTO sequences (uuid, workspace_uuid, kind, current_value) "
                "VALUES (?, ?, ?, ?)",
                ("seq-uuid-dup-1", workspace_uuid, "feature", 5),
            )
            conn.execute(
                "INSERT INTO sequences (uuid, workspace_uuid, kind, current_value) "
                "VALUES (?, ?, ?, ?)",
                ("seq-uuid-dup-2", workspace_uuid, "feature", 9),
            )
            conn.commit()
        finally:
            conn.close()

        call_conn = sqlite3.connect(bootstrapped_db_path, autocommit=True)
        try:
            issued = display.next_display_seq(
                call_conn, workspace_uuid=workspace_uuid, kind="feature"
            )
            assert issued == 10

            rows = call_conn.execute(
                "SELECT current_value FROM sequences WHERE workspace_uuid = ? AND kind = ? "
                "ORDER BY uuid",
                (workspace_uuid, "feature"),
            ).fetchall()
        finally:
            call_conn.close()
        assert [row[0] for row in rows] == [10, 10]


# ---------------------------------------------------------------------------
# Design D5: compose-precondition docstring pin ("trust-the-docstring" —
# conn.in_transaction cannot distinguish DEFERRED from IMMEDIATE, so the
# docstring + this contention suite are the enforcement).
# ---------------------------------------------------------------------------
class TestNextDisplaySeqDocstringPin:
    def test_docstring_pins_compose_precondition(self):
        assert "caller MUST hold BEGIN IMMEDIATE" in display.next_display_seq.__doc__


# ---------------------------------------------------------------------------
# Design D6 / Testing Strategy #5: rename_entity — event emission shape,
# transaction composition, and structural no-touch guarantees.
# ---------------------------------------------------------------------------
class TestRenameEntity:
    def test_fresh_entity_zero_to_one_event_all_fields(self, v2_conn, seeded_entity_uuid):
        event_uuid = display.rename_entity(
            v2_conn, entity_uuid=seeded_entity_uuid, actor="tester",
            new_type_id="121-renamed-type-id", new_name="Renamed Name",
        )

        entity_row = v2_conn.execute(
            "SELECT type_id, name FROM entities WHERE uuid = ?", (seeded_entity_uuid,)
        ).fetchone()
        assert entity_row == ("121-renamed-type-id", "Renamed Name")

        events_rows = events.read_events(v2_conn, seeded_entity_uuid)
        assert len(events_rows) == 1
        (event,) = events_rows
        assert event["uuid"] == event_uuid
        assert event["event_type"] == "renamed"
        assert event["axis"] == "lifecycle"
        assert event["from_value"] == "121-original-type-id"
        assert event["to_value"] == "121-renamed-type-id"
        assert event["actor"] == "tester"
        assert event["payload"] == {"nameFrom": "Original Name", "nameTo": "Renamed Name"}

    def test_second_rename_one_to_two_events_chains_from_previous_type_id(
        self, v2_conn, seeded_entity_uuid
    ):
        display.rename_entity(
            v2_conn, entity_uuid=seeded_entity_uuid, actor="tester",
            new_type_id="121-first-rename", new_name="First Rename",
        )
        second_event_uuid = display.rename_entity(
            v2_conn, entity_uuid=seeded_entity_uuid, actor="tester",
            new_type_id="121-second-rename", new_name="Second Rename",
        )

        events_rows = events.read_events(v2_conn, seeded_entity_uuid)
        assert len(events_rows) == 2
        second_event = events_rows[1]
        assert second_event["uuid"] == second_event_uuid
        # Chains from the PREVIOUS rename's type_id, not the original one.
        assert second_event["from_value"] == "121-first-rename"
        assert second_event["to_value"] == "121-second-rename"
        assert second_event["payload"] == {
            "nameFrom": "First Rename", "nameTo": "Second Rename",
        }

    def test_name_only_rename_from_to_null_payload_carries_names(
        self, v2_conn, seeded_entity_uuid
    ):
        display.rename_entity(
            v2_conn, entity_uuid=seeded_entity_uuid, actor="tester",
            new_name="Only Name Changed",
        )

        entity_row = v2_conn.execute(
            "SELECT type_id, name FROM entities WHERE uuid = ?", (seeded_entity_uuid,)
        ).fetchone()
        assert entity_row == ("121-original-type-id", "Only Name Changed")

        (event,) = events.read_events(v2_conn, seeded_entity_uuid)
        assert event["from_value"] is None
        assert event["to_value"] is None
        assert event["payload"] == {"nameFrom": "Original Name", "nameTo": "Only Name Changed"}

    def test_type_id_only_rename_payload_is_sql_null_typeof_pin(
        self, v2_conn, seeded_entity_uuid
    ):
        """Mirrors test_events.py's 119 QA C1 pattern
        (test_payload_omitted_round_trips_as_none): a type_id-only rename
        must leave payload as a REAL SQL NULL, not the JSON string "null"
        or an empty dict — checked via typeof(), not just `is None`."""
        event_uuid = display.rename_entity(
            v2_conn, entity_uuid=seeded_entity_uuid, actor="tester",
            new_type_id="121-type-id-only",
        )

        entity_row = v2_conn.execute(
            "SELECT type_id, name FROM entities WHERE uuid = ?", (seeded_entity_uuid,)
        ).fetchone()
        assert entity_row == ("121-type-id-only", "Original Name")

        (event,) = events.read_events(v2_conn, seeded_entity_uuid)
        assert event["from_value"] == "121-original-type-id"
        assert event["to_value"] == "121-type-id-only"
        assert event["payload"] is None

        row_type = v2_conn.execute(
            "SELECT typeof(payload) FROM events WHERE uuid = ?", (event_uuid,)
        ).fetchone()[0]
        assert row_type == "null"

    def test_compose_mode_leaves_transaction_open_caller_commits(
        self, bootstrapped_db_path, seeded_entity_uuid
    ):
        conn = events.connect_v2(bootstrapped_db_path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            event_uuid = display.rename_entity(
                conn, entity_uuid=seeded_entity_uuid, actor="tester",
                new_name="Composed Rename",
            )
            assert conn.in_transaction is True
            conn.execute("COMMIT")

            (event,) = events.read_events(conn, seeded_entity_uuid)
            assert event["uuid"] == event_uuid
            name_row = conn.execute(
                "SELECT name FROM entities WHERE uuid = ?", (seeded_entity_uuid,)
            ).fetchone()
            assert name_row[0] == "Composed Rename"
        finally:
            conn.close()

    def test_rollback_injection_neither_update_nor_event_persists(
        self, monkeypatch, bootstrapped_db_path, seeded_entity_uuid
    ):
        """Monkeypatch display.append_event to raise AFTER the UPDATE has
        already executed (uncommitted, standalone mode) — the standalone
        wrapper's guarded ROLLBACK must discard BOTH the entities UPDATE
        and the would-be events INSERT together, not just the half that
        never ran."""
        conn = events.connect_v2(bootstrapped_db_path)
        mid_transaction_snapshot = {}

        def _raise_after_update(*args, **kwargs):
            # Confirm the UPDATE already applied (uncommitted, but
            # visible within this same connection/transaction) before
            # simulating the downstream failure — proves this genuinely
            # exercises "post-UPDATE" rollback rather than the UPDATE
            # having been skipped entirely.
            mid_row = conn.execute(
                "SELECT type_id, name FROM entities WHERE uuid = ?",
                (seeded_entity_uuid,),
            ).fetchone()
            mid_transaction_snapshot["type_id"], mid_transaction_snapshot["name"] = mid_row
            raise RuntimeError("boom: simulated failure after UPDATE")

        monkeypatch.setattr(display, "append_event", _raise_after_update)

        try:
            before_row = conn.execute(
                "SELECT type_id, name, updated_at FROM entities WHERE uuid = ?",
                (seeded_entity_uuid,),
            ).fetchone()

            with pytest.raises(RuntimeError, match="boom"):
                display.rename_entity(
                    conn, entity_uuid=seeded_entity_uuid, actor="tester",
                    new_type_id="121-should-not-persist", new_name="Should Not Persist",
                )

            # The UPDATE really did run, uncommitted, before the injected
            # failure — otherwise this test would vacuously pass even if
            # append_event were (incorrectly) called BEFORE the UPDATE.
            assert mid_transaction_snapshot == {
                "type_id": "121-should-not-persist", "name": "Should Not Persist",
            }

            assert conn.in_transaction is False

            after_row = conn.execute(
                "SELECT type_id, name, updated_at FROM entities WHERE uuid = ?",
                (seeded_entity_uuid,),
            ).fetchone()
            assert after_row == before_row

            event_count = conn.execute(
                "SELECT COUNT(*) FROM events WHERE entity_uuid = ?", (seeded_entity_uuid,)
            ).fetchone()[0]
            assert event_count == 0

            # Connection remains usable after the failure.
            assert conn.execute("SELECT 1").fetchone() == (1,)
        finally:
            conn.close()

    def test_uuid_and_relations_rows_byte_unchanged(self, v2_conn, seeded_entity_uuid):
        """Design D6: the UPDATE lists only type_id/name/updated_at — the
        entity's uuid/workspace_uuid/type/kind/lifecycle_class/
        artifact_path/parent_uuid/created_at/metadata AND any
        entity_relations rows referencing it stay structurally
        untouched."""
        other_entity_uuid = "entity-uuid-display-relation-target"
        v2_conn.execute(
            "INSERT INTO entities (uuid, workspace_uuid, type, kind, lifecycle_class, "
            "type_id, name, artifact_path, parent_uuid, created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                other_entity_uuid, "workspace-uuid-display-test", "feature", "feature",
                "artifact", "121-relation-target", "Relation Target", None, None,
                _NOW, _NOW, None,
            ),
        )
        relation_uuid = "relation-uuid-display-test"
        v2_conn.execute(
            "INSERT INTO entity_relations (uuid, from_uuid, to_uuid, kind, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (relation_uuid, seeded_entity_uuid, other_entity_uuid, "blocks", _NOW),
        )

        before_entity = v2_conn.execute(
            "SELECT uuid, workspace_uuid, type, kind, lifecycle_class, artifact_path, "
            "parent_uuid, created_at, metadata FROM entities WHERE uuid = ?",
            (seeded_entity_uuid,),
        ).fetchone()
        before_relation = v2_conn.execute(
            "SELECT uuid, from_uuid, to_uuid, kind, created_at FROM entity_relations "
            "WHERE uuid = ?", (relation_uuid,),
        ).fetchone()

        display.rename_entity(
            v2_conn, entity_uuid=seeded_entity_uuid, actor="tester",
            new_type_id="121-renamed-again", new_name="Renamed Again",
        )

        after_entity = v2_conn.execute(
            "SELECT uuid, workspace_uuid, type, kind, lifecycle_class, artifact_path, "
            "parent_uuid, created_at, metadata FROM entities WHERE uuid = ?",
            (seeded_entity_uuid,),
        ).fetchone()
        after_relation = v2_conn.execute(
            "SELECT uuid, from_uuid, to_uuid, kind, created_at FROM entity_relations "
            "WHERE uuid = ?", (relation_uuid,),
        ).fetchone()

        assert after_entity == before_entity
        assert after_relation == before_relation

    def test_missing_entity_uuid_raises_value_error(self, v2_conn):
        with pytest.raises(ValueError, match="no entity"):
            display.rename_entity(
                v2_conn, entity_uuid="entity-uuid-does-not-exist", actor="tester",
                new_name="Doesn't Matter",
            )
        assert v2_conn.in_transaction is False
        event_count = v2_conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert event_count == 0

    def test_no_field_supplied_raises_value_error_no_op(self, v2_conn, seeded_entity_uuid):
        before_row = v2_conn.execute(
            "SELECT type_id, name, updated_at FROM entities WHERE uuid = ?",
            (seeded_entity_uuid,),
        ).fetchone()

        with pytest.raises(ValueError, match="at least one"):
            display.rename_entity(v2_conn, entity_uuid=seeded_entity_uuid, actor="tester")

        after_row = v2_conn.execute(
            "SELECT type_id, name, updated_at FROM entities WHERE uuid = ?",
            (seeded_entity_uuid,),
        ).fetchone()
        assert after_row == before_row
        event_count = v2_conn.execute(
            "SELECT COUNT(*) FROM events WHERE entity_uuid = ?", (seeded_entity_uuid,)
        ).fetchone()[0]
        assert event_count == 0
