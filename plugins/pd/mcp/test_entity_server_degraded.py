"""Tests for entity_server degraded mode (DB lock resilience).

Task 3.1: RED tests for degraded mode behavior.
Task 3.2: GREEN — these should pass after implementation.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import threading
import time
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
        """Set _db_unavailable = True, verify _check_db_available returns error dict."""
        old_val = entity_server._db_unavailable
        try:
            entity_server._db_unavailable = True
            err = entity_server._check_db_available()
            assert err == {"error": "database temporarily unavailable"}
        finally:
            entity_server._db_unavailable = old_val


class TestRecoveryThreadRecovers:
    """Test that recovery thread restores DB after transient failure."""

    def test_recovery_thread_recovers(self, tmp_path):
        """Mock EntityDatabase to fail once then succeed, verify recovery."""
        db_path = str(tmp_path / "test.db")

        call_count = 0
        mock_db = mock.MagicMock()

        def fake_entity_db(path):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise sqlite3.OperationalError("database is locked")
            return mock_db

        old_db = entity_server._db
        old_unavailable = entity_server._db_unavailable
        entity_server._db_unavailable = True
        try:
            with mock.patch("entity_server.EntityDatabase", side_effect=fake_entity_db):
                thread = entity_server._start_recovery_thread(
                    db_path, poll_interval=0.05
                )
                # Wait for recovery (should happen within ~0.2s)
                deadline = time.time() + 2.0
                while entity_server._db_unavailable and time.time() < deadline:
                    time.sleep(0.05)

                assert entity_server._db_unavailable is False
                assert entity_server._db is mock_db
        finally:
            entity_server._db = old_db
            entity_server._db_unavailable = old_unavailable


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


class TestRecoveryLogsBackfillSkipped:
    """Test that recovery thread logs backfill skipped message."""

    def test_recovery_logs_backfill_skipped(self, tmp_path, caplog):
        """Verify recovery thread logs 'backfill skipped' message."""
        db_path = str(tmp_path / "test.db")
        mock_db = mock.MagicMock()

        old_db = entity_server._db
        old_unavailable = entity_server._db_unavailable
        entity_server._db_unavailable = True
        try:
            with mock.patch(
                "entity_server.EntityDatabase", return_value=mock_db
            ), caplog.at_level(logging.INFO, logger="entity_server"):
                thread = entity_server._start_recovery_thread(
                    db_path, poll_interval=0.05
                )
                # Wait for recovery
                deadline = time.time() + 2.0
                while entity_server._db_unavailable and time.time() < deadline:
                    time.sleep(0.05)

                assert any(
                    "backfill skipped" in record.message for record in caplog.records
                ), f"Expected 'backfill skipped' in logs, got: {[r.message for r in caplog.records]}"
        finally:
            entity_server._db = old_db
            entity_server._db_unavailable = old_unavailable
