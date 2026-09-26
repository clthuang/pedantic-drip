"""W5.6: concurrent openers never run a migration step twice on one file.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W5 change 6
("The race"), as the 2026-09-26 amendment to task 4C rules: the race is in
the migration runner. Two MCP servers can open one registry at the same
moment. ``EntityDatabase._migrate`` and ``_migrate_v2`` read the file's
version once, with no lock, and ran every pending step, so two openers ran
the same steps side by side:

- **Replayed table rebuilds** against a later schema could leave the file
  unopenable, or with triggers on a dropped column that failed every
  entity insert.
- **Replayed stamps** moved the version back (once to 3 under the newest
  schema), and every later open failed.
- **The flag migrations (22-24)** raised ``duplicate column name``: the
  flake of ``test_database.py::TestMigration11ConcurrentRunners``.

The runner is now serialized: a pending run holds a cross-process lock and
decides again under it what is left to run, and no forward stamp lowers the
version. The tests here, by kind:

- **Process races:** runner processes open one file at the same moment,
  over several rounds, from each starting shape (fresh, v10, and v2 with
  test-only steps pending).
- **Deterministic interleavings,** in one process with threads: a runner
  is paused at a chosen point while a peer works, then resumed.
- **The version stamp:** a lower stamp is ignored, not refused.
- **The migrations' own guards,** kept from the first fix: migration 11's
  step 0 and the flag migrations re-check under their own write lock, for
  callers that run a step outside the runner.
"""
from __future__ import annotations

import fcntl
import json
import os
import select
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager, suppress
from pathlib import Path

import pytest

from entity_registry import database
from entity_registry.database import EntityDatabase
from entity_registry.test_helpers import make_v10_db

_WAIT_SECONDS = 30

# Process races: rounds per starting shape, and runner processes per round.
_RACE_ROUNDS = 6
_RACE_RUNNERS = 4


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


def _v10_file_with_two_projects(tmp_path, name: str = "v10.db") -> str:
    """A registry at schema_version 10 with one entity in each of two
    legacy projects, as the two-runner race test builds it."""
    path = str(tmp_path / name)
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


def _v2_file_at_its_newest_version(path: str) -> str:
    """A v2-generation registry at ``max(V2_MIGRATIONS)``.

    The v1 chain's newest shape is the v2 chain's newest shape (v2 steps
    2-7 are v1 steps 20-25), stamped here as the rebuild tool stamps a
    cutover file. Build it before registering test-only v2 steps.
    """
    EntityDatabase(path).close()
    connection = sqlite3.connect(path)
    try:
        database._upsert_metadata(connection, "schema_generation", "v2")
        database._upsert_metadata(
            connection, "schema_version", str(max(database.V2_MIGRATIONS))
        )
        connection.commit()
    finally:
        connection.close()
    return path


def _test_only_v2_versions() -> list[int]:
    """Two versions past this build's v2 chain, for test-only steps."""
    newest = max(database.V2_MIGRATIONS)
    return [newest + 1, newest + 2]


def _test_only_v2_step(version: int):
    """A pending v2 step for these tests. It adds a column with no probe
    first, so a second run of it on one file raises ``duplicate column
    name``, as the flag migrations did before W5.6."""
    def step(connection: sqlite3.Connection) -> None:
        connection.execute(
            f"ALTER TABLE entities ADD COLUMN test_only_v2_step_{version} INTEGER"
        )
    return step


def _register_test_only_v2_steps(monkeypatch, versions: list[int]) -> None:
    for version in versions:
        monkeypatch.setitem(database.V2_MIGRATIONS, version, _test_only_v2_step(version))


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


def _schema(path: str) -> list[tuple]:
    """Every table, index, view and trigger definition in the file."""
    connection = sqlite3.connect(path)
    try:
        return connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Process races
# ---------------------------------------------------------------------------

_RUNNER_PROCESS_ENTRY = (
    "import json, sys; sys.path.insert(0, sys.argv[1]); "
    "from entity_registry.test_migration_concurrent_runners import _serve_opens; "
    "_serve_opens(json.loads(sys.argv[2]))"
)


def _serve_opens(test_only_v2_versions: list[int]) -> None:
    """A runner process's main loop (see :func:`_runner_processes`).

    Registers the test-only v2 steps, logs every step it enters, prints
    ``ready``, then for each path read from stdin opens it once and prints
    one JSON line: the error (None when the open succeeded) and the steps
    that open ran.
    """
    for version in test_only_v2_versions:
        database.V2_MIGRATIONS[version] = _test_only_v2_step(version)
    steps_run: list[list] = []
    for chain, registry in (("v1", database.MIGRATIONS), ("v2", database.V2_MIGRATIONS)):
        for version, step in list(registry.items()):
            def logged(connection, chain=chain, version=version, step=step):
                steps_run.append([chain, version])
                step(connection)
            registry[version] = logged
    print("ready", flush=True)
    for line in sys.stdin:
        steps_run.clear()
        try:
            EntityDatabase(line.rstrip("\n")).close()
            error = None
        except Exception as exc:  # reported to the test, which asserts on it
            error = f"{type(exc).__name__}: {exc}"
        print(json.dumps({"error": error, "steps_run": steps_run}), flush=True)


def _reply_line(process: subprocess.Popen) -> str:
    ready, _, _ = select.select([process.stdout], [], [], 2 * _WAIT_SECONDS)
    assert ready, "a runner process did not answer"
    return process.stdout.readline().rstrip("\n")


@contextmanager
def _runner_processes(count: int, test_only_v2_versions: list[int]):
    """Start *count* runner processes; yield ``open_at_once(path)``.

    Each runner waits on its stdin, so writing the path to every runner
    back to back makes them open the file at the same moment. It returns
    each runner's reply, as :func:`_serve_opens` describes it.
    """
    hooks_lib = str(Path(database.__file__).resolve().parent.parent)
    processes: list[subprocess.Popen] = []
    try:
        for _ in range(count):
            processes.append(subprocess.Popen(
                [sys.executable, "-c", _RUNNER_PROCESS_ENTRY, hooks_lib,
                 json.dumps(test_only_v2_versions)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            ))
        for process in processes:
            assert _reply_line(process) == "ready"

        def open_at_once(path: str) -> list[dict]:
            for process in processes:
                process.stdin.write(path + "\n")
                process.stdin.flush()
            return [json.loads(_reply_line(process)) for process in processes]

        yield open_at_once
    finally:
        for process in processes:
            with suppress(OSError):
                process.stdin.close()
        for process in processes:
            try:
                process.wait(_WAIT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


@pytest.mark.parametrize("shape", ["fresh", "v10", "v2"])
def test_runner_processes_opening_one_file_at_once_run_each_step_once(tmp_path, monkeypatch, shape):
    """Four runner processes open one file at the same moment, in each of
    six rounds. Every runner succeeds, each pending step runs once across
    all of them, the file ends at the newest version, a further open
    succeeds, and the schema is the one a single process builds.

    Shapes: a file that does not exist yet (the v1 chain from nothing), a
    v10 file (the v1 chain from 11), and a v2 file with two test-only steps
    pending (the v2 chain).
    """
    test_only_v2_versions: list[int] = []
    if shape == "fresh":
        def prepare(label):
            return str(tmp_path / f"fresh-{label}.db")
        expected_steps = [("v1", v) for v in range(1, max(database.MIGRATIONS) + 1)]
        newest = max(database.MIGRATIONS)
    elif shape == "v10":
        def prepare(label):
            return _v10_file_with_two_projects(tmp_path, f"v10-{label}.db")
        expected_steps = [("v1", v) for v in range(11, max(database.MIGRATIONS) + 1)]
        newest = max(database.MIGRATIONS)
    else:
        template = _v2_file_at_its_newest_version(str(tmp_path / "v2-template.db"))
        test_only_v2_versions = _test_only_v2_versions()
        _register_test_only_v2_steps(monkeypatch, test_only_v2_versions)

        def prepare(label):
            path = str(tmp_path / f"v2-{label}.db")
            shutil.copyfile(template, path)
            return path
        expected_steps = [("v2", v) for v in test_only_v2_versions]
        newest = max(database.V2_MIGRATIONS)

    reference = prepare("reference")
    EntityDatabase(reference).close()
    reference_schema = _schema(reference)

    with _runner_processes(_RACE_RUNNERS, test_only_v2_versions) as open_at_once:
        for round_number in range(_RACE_ROUNDS):
            path = prepare(round_number)
            replies = open_at_once(path)
            errors = [reply["error"] for reply in replies if reply["error"]]
            steps_run = sorted(tuple(step) for reply in replies for step in reply["steps_run"])

            assert errors == [], f"round {round_number}"
            assert steps_run == expected_steps, f"round {round_number}"
            assert _stamp_on_disk(path) == str(newest), f"round {round_number}"
            EntityDatabase(path).close()
            assert _schema(path) == reference_schema, f"round {round_number}"


def test_a_lock_file_a_killed_runner_left_neither_blocks_nor_outlives_the_next_run(tmp_path):
    """A runner killed mid-run leaves its lock file behind, while the kernel
    frees the lock itself. The next opener takes the lock, brings the file
    to the newest version, and removes the lock file: nothing is left
    beside the registry."""
    path = _v10_file_with_two_projects(tmp_path)
    lock_file = Path(os.path.realpath(path) + ".migrate.lock")
    lock_file.touch()

    EntityDatabase(path).close()

    assert _stamp_on_disk(path) == str(max(database.MIGRATIONS))
    assert not lock_file.exists()


# ---------------------------------------------------------------------------
# Deterministic interleavings
# ---------------------------------------------------------------------------


class _StepLog:
    """Which thread entered which migration step, in order."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, int]] = []
        self._guard = threading.Lock()

    def record(self, version: int) -> None:
        with self._guard:
            self.entries.append((threading.current_thread().name, version))

    def versions_run_by(self, thread_name: str) -> list[int]:
        return [version for name, version in self.entries if name == thread_name]


def _log_steps(monkeypatch, registry: dict, versions: list[int], log: _StepLog, before_step) -> None:
    """Wrap each step in *versions*: entering it is logged, then
    ``before_step(version)`` runs in the entering thread, then the step."""
    for version in versions:
        real_step = registry[version]

        def step(connection, version=version, real_step=real_step):
            log.record(version)
            before_step(version)
            real_step(connection)
        monkeypatch.setitem(registry, version, step)


def _before_each_exclusive_flock(monkeypatch, hook) -> None:
    """Run ``hook()`` in any thread just before it asks for an exclusive
    ``fcntl.flock``, as the migration lock does, then ask for it."""
    real_flock = fcntl.flock

    def flock(fd, operation):
        if operation & fcntl.LOCK_EX:
            hook()
        return real_flock(fd, operation)
    monkeypatch.setattr(fcntl, "flock", flock)


def _open_in_thread(path: str, name: str, errors: list[str]) -> threading.Thread:
    def open_once() -> None:
        try:
            EntityDatabase(path).close()
        except Exception as exc:  # the test asserts on it
            errors.append(f"{name}: {type(exc).__name__}: {exc}")

    thread = threading.Thread(target=open_once, name=name)
    thread.start()
    return thread


@pytest.mark.parametrize("chain", ["v1", "v2"])
def test_a_runner_that_started_behind_runs_no_step_and_leaves_the_version_at_head(tmp_path, monkeypatch, chain):
    """Runner S reads the file's version, then stops before the migration
    lock (with no lock, before its first step). A peer brings the file to
    the newest version. S resumes and runs no step: under the lock it reads
    the newest version, and the file stays there. Before W5.6, S replayed
    every step from the version it had read, and its stamps moved the
    file's version back.

    v1: a v10 file. v2: a v2 file at its newest real version, with two
    test-only steps pending.
    """
    if chain == "v1":
        path = _v10_file_with_two_projects(tmp_path)
        registry = database.MIGRATIONS
        pending = list(range(11, max(registry) + 1))
    else:
        path = _v2_file_at_its_newest_version(str(tmp_path / "v2.db"))
        pending = _test_only_v2_versions()
        _register_test_only_v2_steps(monkeypatch, pending)
        registry = database.V2_MIGRATIONS
    newest = max(registry)
    behind = "runner-that-started-behind"
    behind_stopped = threading.Event()
    peer_done = threading.Event()

    def stop_the_runner_behind_once() -> None:
        if threading.current_thread().name == behind and not behind_stopped.is_set():
            behind_stopped.set()
            peer_done.wait(_WAIT_SECONDS)

    log = _StepLog()
    _log_steps(monkeypatch, registry, pending, log, lambda version: stop_the_runner_behind_once())
    _before_each_exclusive_flock(monkeypatch, stop_the_runner_behind_once)

    errors: list[str] = []
    runner_behind = _open_in_thread(path, behind, errors)
    try:
        assert behind_stopped.wait(_WAIT_SECONDS), "runner S reached neither the lock nor a step"
        EntityDatabase(path).close()  # the peer, in this thread
    finally:
        peer_done.set()
        runner_behind.join(2 * _WAIT_SECONDS)

    assert log.versions_run_by(behind) == []
    assert errors == []
    assert log.versions_run_by(threading.main_thread().name) == pending
    assert _stamp_on_disk(path) == str(newest)


def test_openers_that_arrive_mid_run_wait_for_it_then_run_no_step(tmp_path, monkeypatch):
    """Runner S holds the migration lock inside step 11 of a v10 file when
    two more openers arrive. They wait for S's run instead of running the
    steps beside it, then find the file at the newest version: every step
    runs once, all of them in S. Before W5.6 the late openers ran every
    step at the same time as S, and a third runner could abort migration 13
    on a version a replay had moved back."""
    path = _v10_file_with_two_projects(tmp_path)
    pending = list(range(11, max(database.MIGRATIONS) + 1))
    holder = "runner-holding-the-lock"
    late_openers = ("late-opener-1", "late-opener-2")
    holder_in_first_step = threading.Event()
    release_holder = threading.Event()
    at_the_lock = {name: threading.Event() for name in late_openers}

    def hold_the_holder_in_its_first_step(version: int) -> None:
        if threading.current_thread().name == holder and version == pending[0]:
            holder_in_first_step.set()
            release_holder.wait(_WAIT_SECONDS)

    def note_a_late_opener_at_the_lock() -> None:
        name = threading.current_thread().name
        if name in at_the_lock:
            at_the_lock[name].set()

    log = _StepLog()
    _log_steps(monkeypatch, database.MIGRATIONS, pending, log, hold_the_holder_in_its_first_step)
    _before_each_exclusive_flock(monkeypatch, note_a_late_opener_at_the_lock)

    errors: list[str] = []
    threads = [_open_in_thread(path, holder, errors)]
    try:
        assert holder_in_first_step.wait(_WAIT_SECONDS), "runner S never reached step 11"
        threads += [_open_in_thread(path, name, errors) for name in late_openers]
        # Each late opener either waits at the lock, or (no lock) has run
        # the steps beside S and finished.
        deadline = time.monotonic() + _WAIT_SECONDS
        while time.monotonic() < deadline and not all(
            at_the_lock[thread.name].is_set() or not thread.is_alive()
            for thread in threads[1:]
        ):
            time.sleep(0.01)
    finally:
        release_holder.set()
        for thread in threads:
            thread.join(2 * _WAIT_SECONDS)

    assert sorted(log.entries) == sorted((holder, version) for version in pending)
    assert errors == []
    assert _stamp_on_disk(path) == str(max(database.MIGRATIONS))


# ---------------------------------------------------------------------------
# The version stamp
# ---------------------------------------------------------------------------

# Forward steps that stamp their own number inside their transaction without
# first re-checking the version, and whose replay on a file at the newest
# version reached that stamp at c1bbfae0, writing the lower number over the
# file's version. (Steps 2, 4, 6 and 8 fail against the newest schema before
# their stamp; steps 10-14 and 18 re-check first.) Step 5 then fails its
# post-commit foreign key check against the newest schema.
_STEPS_WHOSE_REPLAY_REACHES_THEIR_STAMP = (3, 5, 9, 15, 17)

# Of those, the steps whose replay touches nothing a newer schema changed,
# so it completes.
_STEPS_WHOSE_REPLAY_COMPLETES = (15, 17)


@pytest.mark.parametrize("version", _STEPS_WHOSE_REPLAY_REACHES_THEIR_STAMP)
def test_a_forward_step_replayed_on_a_newer_file_leaves_its_version(tmp_path, version):
    """The step's own stamp is below the file's version: it is ignored, not
    refused. The version stays at the newest, and a step whose replay
    touches nothing newer completes without an error."""
    path = str(tmp_path / "newest.db")
    EntityDatabase(path).close()

    connection = sqlite3.connect(path, timeout=15.0)
    error = None
    try:
        database.MIGRATIONS[version](connection)
    except sqlite3.Error as exc:
        error = exc
    finally:
        connection.close()

    assert _stamp_on_disk(path) == str(max(database.MIGRATIONS))
    if version in _STEPS_WHOSE_REPLAY_COMPLETES:
        assert error is None, error


def _test_only_step_that_stamps(version: int):
    """A pending step that also stamps *version*, a later step's number."""
    def step(connection: sqlite3.Connection) -> None:
        database._upsert_metadata(connection, "schema_version", str(version))
    return step


def _test_only_step_that_notes_the_version(versions_seen: list[str]):
    """A pending step that notes the file's version as it starts."""
    def step(connection: sqlite3.Connection) -> None:
        versions_seen.append(connection.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()[0])
    return step


@pytest.mark.parametrize("chain", ["v1", "v2"])
def test_the_step_stamp_ignores_a_version_below_the_files(tmp_path, monkeypatch, chain):
    """Two test-only steps are pending, and the first also stamps the
    second's number itself. The loop's stamp for the first step then meets
    a higher stored version: it is ignored, not refused. The second step
    starts with the file still at the higher version, and the file ends at
    the newest version.

    v1: the v1 chain's newest file, steps registered past its end. v2: a v2
    file at its newest real version.
    """
    versions_seen: list[str] = []
    if chain == "v1":
        path = str(tmp_path / "newest.db")
        EntityDatabase(path).close()
        registry = database.MIGRATIONS
    else:
        path = _v2_file_at_its_newest_version(str(tmp_path / "v2.db"))
        registry = database.V2_MIGRATIONS
    first, second = max(registry) + 1, max(registry) + 2
    monkeypatch.setitem(registry, first, _test_only_step_that_stamps(second))
    monkeypatch.setitem(registry, second, _test_only_step_that_notes_the_version(versions_seen))

    EntityDatabase(path).close()

    assert versions_seen == [str(second)]
    assert _stamp_on_disk(path) == str(second)


# ---------------------------------------------------------------------------
# The migrations' own guards (for callers outside the runner)
# ---------------------------------------------------------------------------


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
