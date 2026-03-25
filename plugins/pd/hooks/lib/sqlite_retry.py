"""Shared retry module for SQLite concurrency defense.

Stub created for TDD — full implementation in task 1.2.
"""


def is_transient(exc: Exception) -> bool:
    """Classify whether a SQLite error is transient (retryable)."""
    raise NotImplementedError("TDD stub")


def with_retry(
    server_name: str,
    max_attempts: int = 3,
    backoff: tuple[float, ...] = (0.1, 0.5, 2.0),
):
    """Decorator factory for retrying SQLite operations on transient errors."""
    raise NotImplementedError("TDD stub")
