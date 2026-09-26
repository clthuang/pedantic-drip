"""An opener waits a bounded time for a peer's migration run.

``_migration_lock`` serializes migration runs on one file across processes
(W5.6). Its wait was a blocking ``flock`` with no bound, so a holder that
stopped mid-run (SIGSTOP, a debugger) stalled every opener with a step
pending, for as long as it stayed stopped. The database's own lock waits
end after ``busy_timeout``. The migration lock's wait now ends after
``database._MIGRATION_LOCK_WAIT_SECONDS``: the open fails with
``sqlite3.OperationalError`` naming the lock file, and runs no step.
"""
from __future__ import annotations

import fcntl
import os
import sqlite3
import threading
import time

from entity_registry import database
from entity_registry.database import EntityDatabase
from entity_registry.test_helpers import make_v10_db

# The wait the test sets, and how long it lets the opener run before it
# calls the opener stuck: far above the wait, far below a test timeout.
_TEST_WAIT_SECONDS = 0.5
_STUCK_AFTER_SECONDS = 10.0


def _stamp_on_disk(path: str) -> str:
    connection = sqlite3.connect(path)
    try:
        return connection.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()[0]
    finally:
        connection.close()


def test_an_opener_behind_a_held_migration_lock_fails_after_the_wait_naming_the_lock_file(
    tmp_path, monkeypatch,
):
    """A peer holds the migration lock of a v10 file and never releases it,
    as a stopped holder does. An opener with steps 11 onward pending waits
    the set time, then fails with the error the MCP servers' open retry
    catches, naming the lock file. The file stays at version 10."""
    path = str(tmp_path / "v10.db")
    make_v10_db(path).close()
    lock_path = os.path.realpath(path) + ".migrate.lock"
    # raising=False: the red-first run sets it on a build without the wait.
    monkeypatch.setattr(
        database, "_MIGRATION_LOCK_WAIT_SECONDS", _TEST_WAIT_SECONDS, raising=False,
    )
    outcome: dict = {}

    def open_behind_the_holder() -> None:
        started = time.monotonic()
        try:
            EntityDatabase(path).close()
            outcome["opened"] = True
        except sqlite3.OperationalError as exc:
            outcome["error"] = exc
        outcome["waited"] = time.monotonic() - started

    holder_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(holder_fd, fcntl.LOCK_EX)
    opener = threading.Thread(target=open_behind_the_holder, daemon=True)
    try:
        opener.start()
        opener.join(_STUCK_AFTER_SECONDS)
        assert not opener.is_alive(), (
            f"the opener still waits for {lock_path} after {_STUCK_AFTER_SECONDS}s"
        )
    finally:
        fcntl.flock(holder_fd, fcntl.LOCK_UN)
        os.close(holder_fd)
        opener.join(_STUCK_AFTER_SECONDS)

    error = outcome.get("error")
    assert isinstance(error, sqlite3.OperationalError), outcome
    assert lock_path in str(error)
    assert outcome["waited"] >= _TEST_WAIT_SECONDS
    assert _stamp_on_disk(path) == "10"
