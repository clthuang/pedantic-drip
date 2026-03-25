"""Tests for sqlite_retry module — TDD tests written before implementation.

Tests cover:
- is_transient() classification of SQLite errors
- with_retry() decorator: retry logic, backoff, logging
"""

import sqlite3
import time

import pytest

from sqlite_retry import is_transient, with_retry


# ---------------------------------------------------------------------------
# is_transient tests
# ---------------------------------------------------------------------------


class TestIsTransient:
    """Classify SQLite errors as transient (retryable) or permanent."""

    def test_database_is_locked_lowercase(self) -> None:
        """OperationalError with 'database is locked' is transient."""
        exc = sqlite3.OperationalError("database is locked")
        assert is_transient(exc) is True

    def test_database_is_locked_case_insensitive(self) -> None:
        """OperationalError with 'database IS LOCKED' is transient (case-insensitive)."""
        exc = sqlite3.OperationalError("database IS LOCKED")
        assert is_transient(exc) is True

    def test_no_such_table_not_transient(self) -> None:
        """OperationalError with 'no such table' is NOT transient."""
        exc = sqlite3.OperationalError("no such table: foo")
        assert is_transient(exc) is False

    def test_sql_logic_error_not_transient(self) -> None:
        """OperationalError with 'SQL logic error' is NOT transient.

        BEGIN IMMEDIATE prevents the stale-transaction root cause, so
        matching 'sql logic error' would false-positive on genuine
        schema/FTS/syntax errors.
        """
        exc = sqlite3.OperationalError("SQL logic error")
        assert is_transient(exc) is False

    def test_non_operational_error_not_transient(self) -> None:
        """Non-OperationalError (e.g., IntegrityError) is NOT transient."""
        exc = sqlite3.IntegrityError("UNIQUE constraint failed")
        assert is_transient(exc) is False

    def test_generic_exception_not_transient(self) -> None:
        """A plain Exception is NOT transient."""
        exc = Exception("something went wrong")
        assert is_transient(exc) is False


# ---------------------------------------------------------------------------
# with_retry tests
# ---------------------------------------------------------------------------


class TestWithRetry:
    """Decorator factory for retrying SQLite operations on transient errors."""

    def test_successful_call_no_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Successful call returns result without any retry."""
        sleep_calls: list[float] = []
        monkeypatch.setattr(time, "sleep", lambda d: sleep_calls.append(d))

        @with_retry(server_name="test-server")
        def succeed():
            return "ok"

        assert succeed() == "ok"
        assert sleep_calls == []

    def test_transient_error_retries_then_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Transient error retries up to max_attempts then re-raises."""
        monkeypatch.setattr(time, "sleep", lambda d: None)

        call_count = 0

        @with_retry(server_name="test-server", max_attempts=3)
        def always_locked():
            nonlocal call_count
            call_count += 1
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            always_locked()

        assert call_count == 3

    def test_transient_error_succeeds_on_second_attempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Transient error on first call, success on second."""
        monkeypatch.setattr(time, "sleep", lambda d: None)

        call_count = 0

        @with_retry(server_name="test-server", max_attempts=3)
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise sqlite3.OperationalError("database is locked")
            return "recovered"

        assert fail_then_succeed() == "recovered"
        assert call_count == 2

    def test_non_transient_error_raises_immediately(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-transient OperationalError raises immediately without retry."""
        sleep_calls: list[float] = []
        monkeypatch.setattr(time, "sleep", lambda d: sleep_calls.append(d))

        call_count = 0

        @with_retry(server_name="test-server", max_attempts=3)
        def schema_error():
            nonlocal call_count
            call_count += 1
            raise sqlite3.OperationalError("no such table: foo")

        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            schema_error()

        assert call_count == 1
        assert sleep_calls == []

    def test_backoff_sequence_with_jitter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Backoff delays match (0.1, 0.5, 2.0) + jitter (0 to 0.05)."""
        sleep_calls: list[float] = []
        monkeypatch.setattr(time, "sleep", lambda d: sleep_calls.append(d))

        @with_retry(
            server_name="test-server",
            max_attempts=4,
            backoff=(0.1, 0.5, 2.0),
        )
        def always_locked():
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(sqlite3.OperationalError):
            always_locked()

        # 4 attempts = 3 sleeps (between attempts 1-2, 2-3, 3-4)
        assert len(sleep_calls) == 3

        # Each sleep should be base + jitter where jitter is in [0, 0.05]
        expected_bases = [0.1, 0.5, 2.0]
        for actual, base in zip(sleep_calls, expected_bases):
            assert base <= actual <= base + 0.05, (
                f"Sleep {actual} not in [{base}, {base + 0.05}]"
            )

    def test_backoff_clamps_to_last_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When attempts exceed backoff tuple length, last value is reused."""
        sleep_calls: list[float] = []
        monkeypatch.setattr(time, "sleep", lambda d: sleep_calls.append(d))

        @with_retry(
            server_name="test-server",
            max_attempts=5,
            backoff=(0.1,),
        )
        def always_locked():
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(sqlite3.OperationalError):
            always_locked()

        # 5 attempts = 4 sleeps, all clamped to 0.1 + jitter
        assert len(sleep_calls) == 4
        for actual in sleep_calls:
            assert 0.1 <= actual <= 0.15

    def test_server_name_in_log_output(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """server_name appears in stderr log output on retry."""
        monkeypatch.setattr(time, "sleep", lambda d: None)

        @with_retry(server_name="entity-server", max_attempts=2)
        def locked():
            raise sqlite3.OperationalError("database is locked")

        with pytest.raises(sqlite3.OperationalError):
            locked()

        captured = capsys.readouterr()
        assert "entity-server" in captured.err
        assert "retry" in captured.err.lower()

    def test_preserves_function_metadata(self) -> None:
        """Decorated function preserves __name__ and __doc__."""

        @with_retry(server_name="test-server")
        def my_handler():
            """Handler docstring."""
            return True

        assert my_handler.__name__ == "my_handler"
        assert my_handler.__doc__ == "Handler docstring."

    def test_non_sqlite_exception_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-sqlite3 exceptions propagate immediately without retry."""
        sleep_calls: list[float] = []
        monkeypatch.setattr(time, "sleep", lambda d: sleep_calls.append(d))

        call_count = 0

        @with_retry(server_name="test-server", max_attempts=3)
        def value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            value_error()

        assert call_count == 1
        assert sleep_calls == []
