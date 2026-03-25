"""Shared MCP server lifecycle utilities.

Provides PID file management and watchdog threads for all pd MCP servers.
"""

import os
import threading
import time
from pathlib import Path

PID_DIR = Path(os.path.expanduser("~/.claude/pd/run"))


def write_pid(server_name: str) -> Path:
    """Write current process PID to PID_DIR/{server_name}.pid.

    Creates PID_DIR if needed. Overwrites any existing PID file
    (previous instance may be stale).

    Args:
        server_name: One of "entity_server", "memory_server",
                     "workflow_state_server", "ui_server"

    Returns:
        Path to the written PID file
    """
    PID_DIR.mkdir(parents=True, exist_ok=True)
    pid_file = PID_DIR / f"{server_name}.pid"
    pid_file.write_text(str(os.getpid()))
    return pid_file


def remove_pid(server_name: str) -> None:
    """Remove PID file for the given server. No-op if file missing."""
    pid_file = PID_DIR / f"{server_name}.pid"
    pid_file.unlink(missing_ok=True)


def read_pid(server_name: str) -> int | None:
    """Read PID from file. Returns None if file missing or content invalid."""
    pid_file = PID_DIR / f"{server_name}.pid"
    try:
        content = pid_file.read_text().strip()
        return int(content)
    except (FileNotFoundError, ValueError):
        return None


def start_parent_watchdog(
    poll_interval: float = 10.0,
    _exit_fn: callable = os._exit,
) -> threading.Thread:
    """Start daemon thread that monitors parent PID.

    Records os.getppid() at call time. Polls every poll_interval seconds.
    When parent PID changes (orphaned), calls _exit_fn(0).

    Args:
        poll_interval: Seconds between checks (default 10.0)
        _exit_fn: Exit function, injectable for testing (default os._exit)

    Returns:
        The started daemon thread
    """
    initial_ppid = os.getppid()

    def _watch():
        while True:
            time.sleep(poll_interval)
            if os.getppid() != initial_ppid:
                _exit_fn(0)
                return

    thread = threading.Thread(target=_watch, name="parent-watchdog", daemon=True)
    thread.start()
    return thread


def start_lifetime_watchdog(
    max_seconds: int = 86400,
    _exit_fn: callable = os._exit,
) -> threading.Thread:
    """Start daemon thread that exits after max_seconds.

    Args:
        max_seconds: Maximum lifetime in seconds (default 86400 = 24h)
        _exit_fn: Exit function, injectable for testing (default os._exit)

    Returns:
        The started daemon thread
    """

    def _watch():
        time.sleep(max_seconds)
        _exit_fn(0)

    thread = threading.Thread(target=_watch, name="lifetime-watchdog", daemon=True)
    thread.start()
    return thread
