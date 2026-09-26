"""W5.6: the migration chain is safe under concurrent runners.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W5 change 6
("The race"). Two MCP servers can open one registry at the same moment, so
every runner of ``EntityDatabase._migrate`` may overlap another.
``test_database.py::TestMigration11ConcurrentRunners`` races two real
runners and failed about 1 run in 20. Its failures were never in migration
11: they were ``duplicate column name`` from the flag migrations (v1 22-24).

Each test here replays one losing interleaving deterministically: a trace
hook pauses runner A just before its next statement, a peer finishes the
work, then A resumes. The replays found three defects:

- **The flag migrations (22-24)** probed for their column, then ALTERed
  with no write lock held, so a peer's ALTER in between made A's ALTER
  raise ``duplicate column name``.
- **Migration 11's step 0** read the legacy ``project_id`` column before
  its ``BEGIN IMMEDIATE``, so a peer finishing migration 11 in between made
  A raise ``no such column: project_id``.
- **The loop's stamp** overwrote ``schema_version`` after each step, so a
  runner that started behind moved a peer's newer stamp back, and a third
  runner entering migration 13 then aborted on the stamp it read.
"""
from __future__ import annotations

import sqlite3
import threading
import uuid

import pytest

from entity_registry import database
from entity_registry.database import EntityDatabase
from entity_registry.test_helpers import make_v10_db

_WAIT_SECONDS = 30


class _PauseBeforeNextStatement:
    """A connection trace hook. Once the connection starts a statement
    beginning with *after_prefix*, the statement after it waits until
    ``release`` is set; ``paused`` says the runner got there.

    A trace hook runs as a statement starts, before it takes any lock, so
    a peer can do its work while the runner waits.
    """

    def __init__(self, after_prefix: str) -> None:
        self.after_prefix = after_prefix
        self.armed = False
        self.paused = threading.Event()
        self.release = threading.Event()

    def __call__(self, sql: str) -> None:
        if self.paused.is_set():
            return
        if self.armed:
            self.paused.set()
            self.release.wait(_WAIT_SECONDS)
            return
        if sql.lstrip().startswith(self.after_prefix):
            self.armed = True


def _run_paused_runner(path: str, migration, hook: _PauseBeforeNextStatement) -> tuple[threading.Thread, dict]:
    """Start runner A in a thread: its own connection, the hook installed,
    *migration* applied. The dict gets A's error (None when it returned)
    and whether A left a transaction open."""
    outcome: dict = {}

    def runner() -> None:
        connection = sqlite3.connect(path, timeout=15.0)
        connection.execute("PRAGMA busy_timeout = 15000")
        connection.set_trace_callback(hook)
        try:
            migration(connection)
            outcome["error"] = None
        except Exception as exc:  # the test asserts on it
            outcome["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            connection.set_trace_callback(None)
            outcome["left_transaction_open"] = connection.in_transaction
            outcome["foreign_keys"] = connection.execute("PRAGMA foreign_keys").fetchone()[0]
            connection.close()

    thread = threading.Thread(target=runner, name="runner-a")
    thread.start()
    return thread, outcome


def _v10_file_with_two_projects(tmp_path) -> str:
    """A registry at schema_version 10 with one entity in each of two
    legacy projects, as the two-runner race test builds it."""
    path = str(tmp_path / "v10.db")
    connection = make_v10_db(path)
    now = "2026-05-10T00:00:00+00:00"
    for project in ("wsA", "wsB"):
        connection.execute(
            "INSERT INTO entities (uuid, type_id, project_id, entity_type, "
            "entity_id, name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), f"feature:001-{project}", project,
             "feature", f"001-{project}", project, now, now),
        )
    connection.commit()
    connection.close()
    return path


def _file_before_the_flag_columns(tmp_path) -> str:
    """A registry built by the real chain up to version 21: no
    ``is_legacy``, ``is_archived`` or ``is_deleted`` column yet."""
    path = str(tmp_path / "v21.db")
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS _metadata "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    for version in range(1, 22):
        database.MIGRATIONS[version](connection)
        database._upsert_metadata(connection, "schema_version", str(version))
        connection.commit()
    connection.close()
    return path


def _entity_columns(path: str) -> list[str]:
    connection = sqlite3.connect(path)
    try:
        return [row[1] for row in connection.execute("PRAGMA table_info(entities)")]
    finally:
        connection.close()


def _stamp_on_disk(path: str) -> str:
    connection = sqlite3.connect(path)
    try:
        return connection.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()[0]
    finally:
        connection.close()


def test_migration_11_returns_cleanly_when_a_peer_finishes_it_before_its_step_0(tmp_path):
    """A passes the outer version check (the file is at 10), then pauses; a
    peer runs migration 11 to completion; A resumes. A finds the work done
    under its own lock and returns, leaving no transaction open and foreign
    keys back on."""
    path = _v10_file_with_two_projects(tmp_path)
    hook = _PauseBeforeNextStatement("SELECT value FROM _metadata")
    thread, outcome = _run_paused_runner(
        path, database._migration_11_workspace_identity, hook,
    )
    try:
        assert hook.paused.wait(_WAIT_SECONDS), "runner A never passed its version check"
        peer = sqlite3.connect(path, timeout=15.0)
        try:
            database._migration_11_workspace_identity(peer)
        finally:
            peer.close()
    finally:
        hook.release.set()
        thread.join(_WAIT_SECONDS)

    assert outcome["error"] is None, outcome["error"]
    assert outcome["left_transaction_open"] is False
    assert outcome["foreign_keys"] == 1
    columns = _entity_columns(path)
    assert "workspace_uuid" in columns and "project_id" not in columns


@pytest.mark.parametrize(
    ("version", "column"),
    [(22, "is_legacy"), (23, "is_archived"), (24, "is_deleted")],
)
def test_a_flag_migration_returns_cleanly_when_a_peer_adds_its_column_first(tmp_path, version, column):
    """A probes and finds no column, then pauses; a peer adds the column;
    A resumes. A re-probes under its write lock, finds the column, and
    returns: one column, no ``duplicate column name``, no open transaction."""
    path = _file_before_the_flag_columns(tmp_path)
    assert column not in _entity_columns(path)
    hook = _PauseBeforeNextStatement("PRAGMA table_info(entities)")
    thread, outcome = _run_paused_runner(path, database.MIGRATIONS[version], hook)
    try:
        assert hook.paused.wait(_WAIT_SECONDS), "runner A never probed for its column"
        peer = sqlite3.connect(path, timeout=15.0)
        try:
            peer.execute(
                f"ALTER TABLE entities ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
            )
            peer.commit()
        finally:
            peer.close()
    finally:
        hook.release.set()
        thread.join(_WAIT_SECONDS)

    assert outcome["error"] is None, outcome["error"]
    assert outcome["left_transaction_open"] is False
    assert _entity_columns(path).count(column) == 1


def _replay_a_runner_that_started_behind(tmp_path, monkeypatch, at_its_step_12) -> str:
    """Runner S opens a v10 file and reads current=10; before its step 11
    runs, a peer migrates the file to head. S then replays 11, 12, ...
    against the head file. *at_its_step_12* is called in S's thread as S
    enters step 12, before the real step 12 runs; the path is returned."""
    path = _v10_file_with_two_projects(tmp_path)
    real_step_11 = database.MIGRATIONS[11]
    real_step_12 = database.MIGRATIONS[12]
    stale_runner = {}
    entered_step_11 = threading.Event()
    peer_done = threading.Event()

    def step_11(connection):
        if threading.get_ident() == stale_runner.get("ident"):
            entered_step_11.set()
            peer_done.wait(_WAIT_SECONDS)
        real_step_11(connection)

    def step_12(connection):
        if threading.get_ident() == stale_runner.get("ident"):
            at_its_step_12(path)
        real_step_12(connection)

    monkeypatch.setitem(database.MIGRATIONS, 11, step_11)
    monkeypatch.setitem(database.MIGRATIONS, 12, step_12)
    errors = []

    def run_stale_runner():
        stale_runner["ident"] = threading.get_ident()
        try:
            EntityDatabase(path).close()
        except Exception as exc:  # the test asserts on it
            errors.append(f"{type(exc).__name__}: {exc}")

    thread = threading.Thread(target=run_stale_runner, name="stale-runner")
    thread.start()
    try:
        assert entered_step_11.wait(_WAIT_SECONDS), "runner S never reached step 11"
        EntityDatabase(path).close()  # the peer: the file goes to head
    finally:
        peer_done.set()
        thread.join(2 * _WAIT_SECONDS)
    assert errors == []
    return path


def test_a_runner_that_started_behind_does_not_stamp_the_file_back(tmp_path, monkeypatch):
    """S's step 11 is a no-op on the head file. The loop's stamp for it
    must not move the file's schema_version back: S enters step 12 with
    the file still at head, and the file ends at head."""
    head = str(max(database.MIGRATIONS))
    stamps_seen = []
    path = _replay_a_runner_that_started_behind(
        tmp_path, monkeypatch, lambda path: stamps_seen.append(_stamp_on_disk(path)),
    )
    assert stamps_seen == [head]
    assert _stamp_on_disk(path) == head


def test_a_runner_that_started_behind_cannot_make_a_third_runner_abort_migration_13(tmp_path, monkeypatch):
    """While S replays the chain, a third runner enters migration 13. It
    reads the file's stamp and returns, since the file is past 13; it does
    not abort with "Manual reconciliation required"."""
    step_13 = database.MIGRATIONS[13]
    third_runner = []

    def third_runner_enters_step_13(path):
        connection = sqlite3.connect(path, timeout=15.0)
        try:
            step_13(connection)
            third_runner.append(None)
        except Exception as exc:  # the test asserts on it
            third_runner.append(f"{type(exc).__name__}: {exc}")
        finally:
            connection.close()

    _replay_a_runner_that_started_behind(tmp_path, monkeypatch, third_runner_enters_step_13)
    assert third_runner == [None]
