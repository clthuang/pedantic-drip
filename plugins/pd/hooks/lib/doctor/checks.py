"""Diagnostic check functions for pd:doctor."""
from __future__ import annotations

import glob
import os
import sqlite3
import time

from doctor.models import CheckResult, Issue

# Expected schema versions
ENTITY_SCHEMA_VERSION = 7
MEMORY_SCHEMA_VERSION = 4


def _build_local_entity_set(artifacts_root: str) -> set[str]:
    """Scan {artifacts_root}/features/*/ directories and return directory names.

    Returns a set of entity_ids (directory basenames like '001-alpha').
    Only includes actual directories, not files.
    """
    features_dir = os.path.join(artifacts_root, "features")
    if not os.path.isdir(features_dir):
        return set()
    return {
        entry
        for entry in os.listdir(features_dir)
        if os.path.isdir(os.path.join(features_dir, entry))
    }


def _test_db_lock(db_path: str, label: str) -> Issue | None:
    """Try BEGIN IMMEDIATE on a dedicated short-lived connection.

    Returns an Issue if the DB is locked, None otherwise.
    Connection is always closed before returning.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=2.0)
        conn.execute("PRAGMA busy_timeout = 2000")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
        return None
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            return Issue(
                check="db_readiness",
                severity="error",
                entity=None,
                message=f"{label} is locked: {exc}",
                fix_hint="Kill the process holding the lock or wait for it to release",
            )
        return Issue(
            check="db_readiness",
            severity="error",
            entity=None,
            message=f"{label} lock test failed: {exc}",
            fix_hint=None,
        )
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _check_schema_version(
    db_path: str, label: str, expected: int
) -> Issue | None:
    """Check schema_version on a separate read-only connection.

    Returns an Issue if version doesn't match, None otherwise.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=2.0)
        conn.execute("PRAGMA busy_timeout = 2000")
        row = conn.execute(
            "SELECT value FROM _metadata WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            return Issue(
                check="db_readiness",
                severity="error",
                entity=None,
                message=f"{label} has no schema_version in _metadata",
                fix_hint="Run migrations to initialize the database",
            )
        actual = int(row[0])
        if actual != expected:
            return Issue(
                check="db_readiness",
                severity="error",
                entity=None,
                message=(
                    f"{label} schema_version is {actual}, expected {expected}"
                ),
                fix_hint="Run migrations to update the database schema",
            )
        return None
    except sqlite3.OperationalError as exc:
        return Issue(
            check="db_readiness",
            severity="error",
            entity=None,
            message=f"{label} schema version check failed: {exc}",
            fix_hint=None,
        )
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _check_wal_mode(db_path: str, label: str) -> Issue | None:
    """Check journal_mode is WAL on a separate read-only connection.

    Returns an Issue (warning) if not WAL, None otherwise.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=2.0)
        conn.execute("PRAGMA busy_timeout = 2000")
        row = conn.execute("PRAGMA journal_mode").fetchone()
        if row is None or row[0].lower() != "wal":
            mode = row[0] if row else "unknown"
            return Issue(
                check="db_readiness",
                severity="warning",
                entity=None,
                message=f"{label} journal_mode is '{mode}', expected 'wal'",
                fix_hint="Set PRAGMA journal_mode=WAL on the database",
            )
        return None
    except sqlite3.OperationalError as exc:
        return Issue(
            check="db_readiness",
            severity="warning",
            entity=None,
            message=f"{label} WAL check failed: {exc}",
            fix_hint=None,
        )
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def check_db_readiness(
    entities_db_path: str, memory_db_path: str, **_
) -> CheckResult:
    """Check 8: DB Readiness.

    Tests lock acquisition, schema version, and WAL mode on both databases.
    Each sub-check uses a dedicated short-lived connection.

    Returns extras={"entity_db_ok": bool, "memory_db_ok": bool}.
    """
    start = time.monotonic()
    issues: list[Issue] = []

    entity_db_ok = True
    memory_db_ok = True

    # Lock tests
    entity_lock_issue = _test_db_lock(entities_db_path, "Entity DB")
    if entity_lock_issue is not None:
        issues.append(entity_lock_issue)
        entity_db_ok = False

    memory_lock_issue = _test_db_lock(memory_db_path, "Memory DB")
    if memory_lock_issue is not None:
        issues.append(memory_lock_issue)
        memory_db_ok = False

    # Schema version checks (only if not locked)
    if entity_db_ok:
        schema_issue = _check_schema_version(
            entities_db_path, "Entity DB", ENTITY_SCHEMA_VERSION
        )
        if schema_issue is not None:
            issues.append(schema_issue)

    if memory_db_ok:
        schema_issue = _check_schema_version(
            memory_db_path, "Memory DB", MEMORY_SCHEMA_VERSION
        )
        if schema_issue is not None:
            issues.append(schema_issue)

    # WAL mode checks (only if not locked)
    if entity_db_ok:
        wal_issue = _check_wal_mode(entities_db_path, "Entity DB")
        if wal_issue is not None:
            issues.append(wal_issue)

    if memory_db_ok:
        wal_issue = _check_wal_mode(memory_db_path, "Memory DB")
        if wal_issue is not None:
            issues.append(wal_issue)

    elapsed = int((time.monotonic() - start) * 1000)
    passed = not any(i.severity in ("error", "warning") for i in issues)

    return CheckResult(
        name="db_readiness",
        passed=passed,
        issues=issues,
        elapsed_ms=elapsed,
        extras={"entity_db_ok": entity_db_ok, "memory_db_ok": memory_db_ok},
    )
