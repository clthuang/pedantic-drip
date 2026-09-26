"""Both MCP servers start degraded behind a migration run that outlasts the wait.

The migration lock's wait ends after ``database._MIGRATION_LOCK_WAIT_SECONDS``
with ``sqlite3.OperationalError`` (``test_migration_lock_wait.py`` pins the
error). Each server's ``_init_db_with_retry`` catches that error and, once
its retries are spent, returns None; the lifespan then marks the database
unavailable, and the server stays degraded until it is restarted (W4.2).
With no bound on the wait, a stopped holder kept the server's start
waiting for as long as it stayed stopped.
"""
from __future__ import annotations

import fcntl
import os
import sys
import threading

import pytest

_MCP_DIR = os.path.dirname(os.path.abspath(__file__))
_HOOKS_LIB = os.path.normpath(os.path.join(_MCP_DIR, "..", "hooks", "lib"))
for _path in (_HOOKS_LIB, _MCP_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import entity_server  # noqa: E402
import workflow_state_server  # noqa: E402
from entity_registry import database  # noqa: E402
from entity_registry.test_helpers import make_v10_db  # noqa: E402

# The wait the test sets, and how long it lets the start run before it
# calls the start stuck: far above two waits, far below a test timeout.
_TEST_WAIT_SECONDS = 0.5
_STUCK_AFTER_SECONDS = 10.0


@pytest.mark.parametrize(
    "server", [entity_server, workflow_state_server],
    ids=["entity_server", "workflow_state_server"],
)
def test_the_servers_open_retry_gives_up_behind_a_held_migration_lock(
    tmp_path, monkeypatch, server,
):
    path = str(tmp_path / "v10.db")
    make_v10_db(path).close()
    lock_path = os.path.realpath(path) + ".migrate.lock"
    # raising=False: the red-first run sets it on a build without the wait.
    monkeypatch.setattr(
        database, "_MIGRATION_LOCK_WAIT_SECONDS", _TEST_WAIT_SECONDS, raising=False,
    )
    started: dict = {}

    def start_the_database() -> None:
        db = server._init_db_with_retry(path, max_retries=2, backoff_seconds=0.0)
        started["opened"] = db is not None
        if db is not None:
            db.close()  # in the thread that opened it

    holder_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(holder_fd, fcntl.LOCK_EX)
    start = threading.Thread(target=start_the_database, daemon=True)
    try:
        start.start()
        start.join(_STUCK_AFTER_SECONDS)
        assert not start.is_alive(), (
            f"the server's open still waits for {lock_path} after {_STUCK_AFTER_SECONDS}s"
        )
    finally:
        fcntl.flock(holder_fd, fcntl.LOCK_UN)
        os.close(holder_fd)
        start.join(_STUCK_AFTER_SECONDS)

    assert started == {"opened": False}
