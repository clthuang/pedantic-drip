"""Concurrent-write integration tests for sqlite_retry module.

Tests multi-process SQLite write contention using real file-backed databases
with the shared `with_retry` decorator.

Uses `multiprocessing` (not threading) because SQLite contention is process-level.
Worker functions are top-level module functions (pickle requirement for multiprocessing).
"""

import multiprocessing
import os
import sqlite3
import tempfile
import time

import pytest

from sqlite_retry import with_retry


# ---------------------------------------------------------------------------
# Top-level worker functions (must be picklable for multiprocessing)
# ---------------------------------------------------------------------------


def _worker_write(db_path, event, worker_id, num_writes):
    """Worker process: wait for barrier, then write N rows with retry."""
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA journal_mode = WAL")

    @with_retry("test-worker")
    def do_write(seq):
        conn.execute(
            "INSERT INTO test_data (worker_id, seq) VALUES (?, ?)",
            (worker_id, seq),
        )
        conn.commit()

    event.wait()  # barrier — all workers start simultaneously

    for i in range(num_writes):
        do_write(i)

    conn.close()


def _worker_write_memory_pattern(db_path, event, worker_id, num_writes):
    """Worker mimicking memory DB write patterns (larger payloads)."""
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA journal_mode = WAL")

    @with_retry("test-memory-worker")
    def do_write(seq):
        payload = f"memory-content-{worker_id}-{seq}" * 10
        conn.execute(
            "INSERT INTO memory_data (worker_id, seq, content) VALUES (?, ?, ?)",
            (worker_id, seq, payload),
        )
        conn.commit()

    event.wait()

    for i in range(num_writes):
        do_write(i)

    conn.close()


def _exclusive_lock_holder(db_path, lock_acquired_event, release_event):
    """Hold an exclusive lock on the database until told to release."""
    conn = sqlite3.connect(db_path, timeout=1.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("BEGIN EXCLUSIVE")
    conn.execute(
        "INSERT INTO test_data (worker_id, seq) VALUES (?, ?)", (-1, -1)
    )
    # Signal that lock is acquired
    lock_acquired_event.set()
    # Hold lock until release event or timeout
    release_event.wait(timeout=10.0)
    conn.rollback()
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def entity_db_path():
    """Create a temporary SQLite DB with entity-style schema."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(
        "CREATE TABLE test_data ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  worker_id INTEGER NOT NULL,"
        "  seq INTEGER NOT NULL"
        ")"
    )
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)
    # Clean up WAL/SHM files if they exist
    for suffix in ("-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


@pytest.fixture
def memory_db_path():
    """Create a temporary SQLite DB with memory-style schema."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(
        "CREATE TABLE memory_data ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  worker_id INTEGER NOT NULL,"
        "  seq INTEGER NOT NULL,"
        "  content TEXT NOT NULL"
        ")"
    )
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)
    for suffix in ("-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConcurrentEntityWrites:
    """3+ processes writing to entity-style DB simultaneously."""

    def test_concurrent_writes_all_succeed(self, entity_db_path):
        """N workers x M writes each = N*M rows, no missing or duplicates."""
        num_workers = 4
        num_writes = 15
        expected_rows = num_workers * num_writes

        barrier = multiprocessing.Event()
        processes = []

        for wid in range(num_workers):
            p = multiprocessing.Process(
                target=_worker_write,
                args=(entity_db_path, barrier, wid, num_writes),
            )
            processes.append(p)
            p.start()

        # Release all workers simultaneously
        barrier.set()

        for p in processes:
            p.join(timeout=30)
            assert p.exitcode == 0, f"Worker exited with code {p.exitcode}"

        # Verify row count
        conn = sqlite3.connect(entity_db_path)
        (count,) = conn.execute("SELECT COUNT(*) FROM test_data").fetchone()
        conn.close()

        assert count == expected_rows, (
            f"Expected {expected_rows} rows, got {count}"
        )

    def test_no_duplicate_writes(self, entity_db_path):
        """Each (worker_id, seq) pair appears exactly once."""
        num_workers = 3
        num_writes = 10

        barrier = multiprocessing.Event()
        processes = []

        for wid in range(num_workers):
            p = multiprocessing.Process(
                target=_worker_write,
                args=(entity_db_path, barrier, wid, num_writes),
            )
            processes.append(p)
            p.start()

        barrier.set()

        for p in processes:
            p.join(timeout=30)
            assert p.exitcode == 0

        conn = sqlite3.connect(entity_db_path)
        rows = conn.execute(
            "SELECT worker_id, seq, COUNT(*) as cnt "
            "FROM test_data GROUP BY worker_id, seq HAVING cnt > 1"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM test_data").fetchone()[0]
        conn.close()

        assert rows == [], f"Duplicate rows found: {rows}"
        assert total == num_workers * num_writes


class TestConcurrentMemoryWrites:
    """3+ processes writing to memory-style DB simultaneously."""

    def test_concurrent_memory_writes_all_succeed(self, memory_db_path):
        """N workers x M writes with larger payloads — all succeed."""
        num_workers = 4
        num_writes = 12
        expected_rows = num_workers * num_writes

        barrier = multiprocessing.Event()
        processes = []

        for wid in range(num_workers):
            p = multiprocessing.Process(
                target=_worker_write_memory_pattern,
                args=(memory_db_path, barrier, wid, num_writes),
            )
            processes.append(p)
            p.start()

        barrier.set()

        for p in processes:
            p.join(timeout=30)
            assert p.exitcode == 0, f"Worker exited with code {p.exitcode}"

        conn = sqlite3.connect(memory_db_path)
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM memory_data"
        ).fetchone()
        conn.close()

        assert count == expected_rows, (
            f"Expected {expected_rows} rows, got {count}"
        )

    def test_no_duplicate_memory_writes(self, memory_db_path):
        """Each (worker_id, seq) pair appears exactly once in memory DB."""
        num_workers = 3
        num_writes = 10

        barrier = multiprocessing.Event()
        processes = []

        for wid in range(num_workers):
            p = multiprocessing.Process(
                target=_worker_write_memory_pattern,
                args=(memory_db_path, barrier, wid, num_writes),
            )
            processes.append(p)
            p.start()

        barrier.set()

        for p in processes:
            p.join(timeout=30)
            assert p.exitcode == 0

        conn = sqlite3.connect(memory_db_path)
        rows = conn.execute(
            "SELECT worker_id, seq, COUNT(*) as cnt "
            "FROM memory_data GROUP BY worker_id, seq HAVING cnt > 1"
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM memory_data"
        ).fetchone()[0]
        conn.close()

        assert rows == [], f"Duplicate rows found: {rows}"
        assert total == num_workers * num_writes


class TestExhaustedRetryRaises:
    """Verify zero-retry path raises OperationalError immediately."""

    def test_exhausted_retry_raises_locked_error(self, entity_db_path):
        """With max_attempts=1 and an exclusive lock held, write fails immediately."""
        lock_acquired = multiprocessing.Event()
        release_lock = multiprocessing.Event()

        # Start lock holder
        holder = multiprocessing.Process(
            target=_exclusive_lock_holder,
            args=(entity_db_path, lock_acquired, release_lock),
        )
        holder.start()

        try:
            # Wait for lock to be acquired
            assert lock_acquired.wait(timeout=5.0), "Lock holder did not acquire lock"

            # Attempt a write with max_attempts=1 (no retries)
            conn = sqlite3.connect(entity_db_path, timeout=0.1)
            conn.execute("PRAGMA busy_timeout = 100")  # Short timeout
            conn.execute("PRAGMA journal_mode = WAL")

            @with_retry("test-no-retry", max_attempts=1, backoff=(0.1,))
            def do_write():
                conn.execute(
                    "INSERT INTO test_data (worker_id, seq) VALUES (?, ?)",
                    (99, 99),
                )
                conn.commit()

            with pytest.raises(sqlite3.OperationalError, match="(?i)locked"):
                do_write()

            conn.close()
        finally:
            release_lock.set()
            holder.join(timeout=10)
