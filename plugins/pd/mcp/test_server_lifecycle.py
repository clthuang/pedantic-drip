"""Tests for server_lifecycle module — PID management and watchdog threads."""

import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from server_lifecycle import (
    PID_DIR,
    read_pid,
    remove_pid,
    start_lifetime_watchdog,
    start_parent_watchdog,
    write_pid,
)


@pytest.fixture
def pid_dir(tmp_path):
    """Override PID_DIR to use a temp directory."""
    with patch("server_lifecycle.PID_DIR", tmp_path):
        yield tmp_path


class TestWritePid:
    def test_write_pid_creates_file(self, pid_dir):
        path = write_pid("entity_server")
        assert path.exists()
        assert path.read_text().strip() == str(os.getpid())

    def test_write_pid_creates_directory(self, tmp_path):
        nested = tmp_path / "sub" / "dir"
        with patch("server_lifecycle.PID_DIR", nested):
            write_pid("memory_server")
        assert nested.exists()
        assert (nested / "memory_server.pid").exists()

    def test_write_pid_overwrites_stale(self, pid_dir):
        pid_file = pid_dir / "entity_server.pid"
        pid_file.write_text("99999")
        write_pid("entity_server")
        assert pid_file.read_text().strip() == str(os.getpid())


class TestRemovePid:
    def test_remove_pid_deletes_file(self, pid_dir):
        pid_file = pid_dir / "entity_server.pid"
        pid_file.write_text(str(os.getpid()))
        remove_pid("entity_server")
        assert not pid_file.exists()

    def test_remove_pid_noop_missing(self, pid_dir):
        # Should not raise any exception
        remove_pid("nonexistent_server")


class TestReadPid:
    def test_read_pid_returns_value(self, pid_dir):
        pid_file = pid_dir / "entity_server.pid"
        pid_file.write_text("12345")
        result = read_pid("entity_server")
        assert result == 12345

    def test_read_pid_returns_none_missing(self, pid_dir):
        result = read_pid("nonexistent_server")
        assert result is None

    def test_read_pid_returns_none_invalid(self, pid_dir):
        pid_file = pid_dir / "entity_server.pid"
        pid_file.write_text("abc")
        result = read_pid("entity_server")
        assert result is None


class TestParentWatchdog:
    def test_parent_watchdog_calls_exit_on_ppid_change(self):
        exit_called = threading.Event()
        call_count = 0
        original_ppid = os.getppid()

        def mock_getppid():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return original_ppid
            return 1  # Simulate orphaning

        def mock_exit(code):
            exit_called.set()

        with patch("server_lifecycle.os.getppid", side_effect=mock_getppid):
            start_parent_watchdog(poll_interval=0.05, _exit_fn=mock_exit)
            assert exit_called.wait(timeout=2.0), "_exit_fn was not called within 2s"

    def test_parent_watchdog_noop_same_ppid(self):
        exit_called = threading.Event()

        def mock_exit(code):
            exit_called.set()

        with patch("server_lifecycle.os.getppid", return_value=os.getppid()):
            start_parent_watchdog(poll_interval=0.05, _exit_fn=mock_exit)
            time.sleep(0.2)
            assert not exit_called.is_set(), "_exit_fn should NOT have been called"


class TestLifetimeWatchdog:
    def test_lifetime_watchdog_calls_exit_after_timeout(self):
        exit_called = threading.Event()

        def mock_exit(code):
            exit_called.set()

        start_lifetime_watchdog(max_seconds=0.1, _exit_fn=mock_exit)
        assert exit_called.wait(timeout=2.0), "_exit_fn was not called within 2s"


class TestWatchdogDaemon:
    def test_watchdog_threads_are_daemon(self):
        with patch("server_lifecycle.os.getppid", return_value=os.getppid()):
            parent_thread = start_parent_watchdog(
                poll_interval=100, _exit_fn=lambda c: None
            )
            lifetime_thread = start_lifetime_watchdog(
                max_seconds=100, _exit_fn=lambda c: None
            )
            assert parent_thread.daemon is True
            assert lifetime_thread.daemon is True
