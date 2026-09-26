"""Tests for entity_server degraded mode (DB lock resilience).

Task 3.1: RED tests for degraded mode behavior.
Task 3.2: GREEN — these should pass after implementation.

A degraded server stays degraded until it is restarted: the recovery thread
and its tests were deleted (W4.2); test_require_workspace.py pins that no
thread starts.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from unittest import mock

import pytest

# Make entity_registry importable
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in sys.path:
    sys.path.insert(0, _hooks_lib)

# Make sibling mcp modules importable
_mcp_dir = os.path.dirname(__file__)
if _mcp_dir not in sys.path:
    sys.path.insert(0, _mcp_dir)

import entity_server


class TestDegradedModeOnDbLock:
    """Test that DB lock triggers degraded mode."""

    def test_degraded_mode_on_db_lock(self, tmp_path):
        """Mock EntityDatabase to raise OperationalError, verify _db_unavailable."""
        db_path = str(tmp_path / "test.db")
        with mock.patch(
            "entity_server.EntityDatabase",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            result = entity_server._init_db_with_retry(
                db_path, max_retries=2, backoff_seconds=0.01
            )
        assert result is None


class TestDegradedToolReturnsError:
    """Test that tool handlers return structured error in degraded mode."""

    def test_degraded_tool_returns_error(self):
        """Set _db_unavailable = True, verify _check_db_available returns error
        dict. A degraded server stays degraded until restarted (W4.2)."""
        old_val = entity_server._db_unavailable
        try:
            entity_server._db_unavailable = True
            err = entity_server._check_db_available()
            assert err == {
                "error": "database unavailable (degraded start); restart the MCP server"
            }
        finally:
            entity_server._db_unavailable = old_val


class TestRetryBackoffIsFlat:
    """Test that retry backoff is flat (not exponential)."""

    def test_retry_backoff_is_flat(self, tmp_path):
        """Mock time.sleep, verify sleep called with 2.0 each time."""
        db_path = str(tmp_path / "test.db")
        with mock.patch(
            "entity_server.EntityDatabase",
            side_effect=sqlite3.OperationalError("database is locked"),
        ), mock.patch("entity_server.time.sleep") as mock_sleep:
            result = entity_server._init_db_with_retry(
                db_path, max_retries=3, backoff_seconds=2.0
            )

        assert result is None
        # sleep is called between retries (max_retries - 1 times)
        assert mock_sleep.call_count == 2
        for call in mock_sleep.call_args_list:
            assert call == mock.call(2.0)
