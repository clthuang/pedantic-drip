"""W5.6: the UI server's process bookkeeping (its PID file, the lifetime
watchdog and the at-exit removal) belongs to the server process.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W5 change 6
("Server lifecycle"). Tests call ``ui.__main__.main()`` in-process with
uvicorn mocked. Before this change ``main()`` itself wrote
``~/.claude/pd/run/ui_server.pid`` for the test process, started a 24-hour
``os._exit`` watchdog in it, and removed the PID file at exit: under the
real HOME, a live UI server's PID file was overwritten, then deleted.

Only the module's entry point asks for the bookkeeping now
(``main(server_process=True)``):

- **in-process:** ``main()`` writes no PID file and starts no watchdog;
- **the real server** (keep-green, the behaviour it had before): writes
  its PID file under its HOME's ``run/`` and removes it when it stops.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
import unittest.mock
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent.parent.parent
_START_SECONDS = 60


def _lifetime_watchdogs() -> set[int]:
    return {
        thread.ident for thread in threading.enumerate()
        if thread.name == "lifetime-watchdog"
    }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait_for(condition, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def test_main_called_in_process_writes_no_pid_file_and_starts_no_watchdog(capsys):
    """``main()`` parses, checks the port and serves (uvicorn mocked). The
    process HOME's ``ui_server.pid`` does not name this process afterwards,
    and no lifetime watchdog has started."""
    from ui.__main__ import main
    import server_lifecycle

    pid_file = server_lifecycle.PID_DIR / "ui_server.pid"
    watchdogs_before = _lifetime_watchdogs()
    with unittest.mock.patch("ui.__main__.uvicorn") as mock_uvicorn:
        mock_uvicorn.run = unittest.mock.MagicMock()
        main(["--port", str(_free_port())])

    mock_uvicorn.run.assert_called_once()
    assert {
        "pid_file_names_this_process": (
            pid_file.exists() and pid_file.read_text().strip() == str(os.getpid())
        ),
        "new_lifetime_watchdogs": len(_lifetime_watchdogs() - watchdogs_before),
    } == {"pid_file_names_this_process": False, "new_lifetime_watchdogs": 0}


def test_the_real_ui_server_writes_its_pid_file_under_its_home_and_removes_it_on_exit(tmp_path):
    """Started as ``run-ui-server.sh`` starts it, the server writes its PID
    into ``$HOME/.claude/pd/run``. On Ctrl+C (SIGINT) uvicorn shuts down and
    re-raises the signal, the process exits through ``KeyboardInterrupt``,
    and the at-exit hook removes the file.

    (SIGTERM is re-raised the same way, but its default action ends the
    process without at-exit hooks, so the file stays for session-start's
    stale-PID sweep. That was so before this change too.)"""
    home = tmp_path / "home"
    home.mkdir()
    env = {
        key: value for key, value in os.environ.items()
        if key not in ("ENTITY_WORKSPACE_UUID", "WORKSPACE_UUID")
    }
    env.update({
        "HOME": str(home),
        "ENTITY_DB_PATH": str(tmp_path / "registry" / "entities.db"),
        "PYTHONPATH": f"{_PLUGIN_DIR / 'hooks' / 'lib'}:{_PLUGIN_DIR}",
        "PYTHONUNBUFFERED": "1",
    })
    pid_file = home / ".claude" / "pd" / "run" / "ui_server.pid"
    stderr_path = tmp_path / "ui_server.stderr"
    with open(stderr_path, "wb") as stderr:
        server = subprocess.Popen(
            [sys.executable, str(_PLUGIN_DIR / "ui" / "__main__.py"),
             "--port", str(_free_port())],
            stdout=subprocess.DEVNULL, stderr=stderr, env=env, cwd=str(tmp_path),
        )
    try:
        assert _wait_for(
            lambda: pid_file.exists() and pid_file.read_text().strip() == str(server.pid),
            _START_SECONDS,
        ), stderr_path.read_text()
        server.send_signal(signal.SIGINT)
        server.wait(timeout=_START_SECONDS)
        assert not pid_file.exists(), stderr_path.read_text()
    finally:
        if server.poll() is None:
            server.kill()
            server.wait()
