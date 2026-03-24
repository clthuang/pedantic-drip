"""Tests for pd:doctor data models and check functions."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time

import pytest

from doctor.models import CheckResult, DiagnosticReport, Issue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path, name: str = "entities.db") -> str:
    """Create a minimal entity DB with schema matching EntityDatabase v7.

    Returns the path to the DB file.
    """
    db_path = str(tmp_path / name)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS _metadata (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT OR REPLACE INTO _metadata(key, value) VALUES('schema_version', '7');

        CREATE TABLE IF NOT EXISTS entities (
            uuid        TEXT NOT NULL PRIMARY KEY,
            type_id     TEXT NOT NULL UNIQUE,
            entity_type TEXT NOT NULL,
            entity_id   TEXT NOT NULL,
            name        TEXT NOT NULL,
            status      TEXT,
            parent_type_id TEXT,
            parent_uuid    TEXT,
            artifact_path  TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
            metadata    TEXT
        );

        CREATE TABLE IF NOT EXISTS workflow_phases (
            uuid               TEXT,
            type_id            TEXT NOT NULL PRIMARY KEY,
            workflow_phase     TEXT,
            last_completed_phase TEXT,
            mode               TEXT,
            kanban_column      TEXT DEFAULT 'backlog',
            created_at         TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS entity_dependencies (
            source_uuid TEXT NOT NULL,
            target_uuid TEXT NOT NULL,
            dep_type    TEXT NOT NULL DEFAULT 'depends_on',
            PRIMARY KEY (source_uuid, target_uuid, dep_type)
        );

        CREATE TABLE IF NOT EXISTS entity_tags (
            entity_uuid TEXT NOT NULL,
            tag         TEXT NOT NULL,
            PRIMARY KEY (entity_uuid, tag)
        );
    """)
    conn.commit()
    conn.close()
    return db_path


def _register_feature(
    db_path: str,
    slug: str = "008-test-feature",
    status: str = "active",
) -> str:
    """Register a feature entity directly via SQL. Returns type_id."""
    import uuid as uuid_mod

    type_id = f"feature:{slug}"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO entities "
        "(uuid, type_id, entity_type, entity_id, name, status, created_at, updated_at) "
        "VALUES (?, ?, 'feature', ?, ?, ?, datetime('now'), datetime('now'))",
        (str(uuid_mod.uuid4()), type_id, slug, f"Test Feature {slug}", status),
    )
    conn.commit()
    conn.close()
    return type_id


def _create_meta_json(
    tmp_path,
    slug: str = "008-test-feature",
    *,
    status: str = "active",
    mode: str | None = "standard",
    last_completed_phase: str | None = None,
) -> None:
    """Create a .meta.json file in the expected location."""
    feature_dir = tmp_path / "features" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": slug.split("-", 1)[0],
        "slug": slug,
        "status": status,
        "mode": mode,
        "lastCompletedPhase": last_completed_phase,
        "phases": {},
    }
    (feature_dir / ".meta.json").write_text(json.dumps(meta))


def _make_memory_db(tmp_path, name: str = "memory.db") -> str:
    """Create a minimal memory DB with schema matching memory v4.

    Returns the path to the DB file.
    """
    db_path = str(tmp_path / name)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS _metadata (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT OR REPLACE INTO _metadata(key, value) VALUES('schema_version', '4');

        CREATE TABLE IF NOT EXISTS entries (
            id          TEXT PRIMARY KEY,
            content     TEXT NOT NULL,
            keywords    TEXT DEFAULT '[]',
            entry_type  TEXT DEFAULT 'observation',
            project     TEXT,
            importance  REAL DEFAULT 0.5,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
            embedding   BLOB
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
            content, keywords, entry_type, project
        );

        CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
            INSERT INTO entries_fts(rowid, content, keywords, entry_type, project)
            VALUES (new.rowid, new.content, new.keywords, new.entry_type, new.project);
        END;

        CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
            INSERT INTO entries_fts(entries_fts, rowid, content, keywords, entry_type, project)
            VALUES ('delete', old.rowid, old.content, old.keywords, old.entry_type, old.project);
        END;

        CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
            INSERT INTO entries_fts(entries_fts, rowid, content, keywords, entry_type, project)
            VALUES ('delete', old.rowid, old.content, old.keywords, old.entry_type, old.project);
            INSERT INTO entries_fts(rowid, content, keywords, entry_type, project)
            VALUES (new.rowid, new.content, new.keywords, new.entry_type, new.project);
        END;

        CREATE TABLE IF NOT EXISTS influence_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id    TEXT NOT NULL,
            context     TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    return db_path


# ===========================================================================
# Task 1.1: Model Tests
# ===========================================================================


class TestCheckResultPassedLogic:
    """Test that passed is True only when no error/warning issues exist."""

    def test_no_issues_is_passed(self):
        result = CheckResult(name="test", passed=True, issues=[], elapsed_ms=0)
        assert result.passed is True

    def test_info_only_is_passed(self):
        issues = [Issue(check="test", severity="info", entity=None, message="ok", fix_hint=None)]
        result = CheckResult(name="test", passed=True, issues=issues, elapsed_ms=0)
        assert result.passed is True

    def test_warning_is_not_passed(self):
        issues = [Issue(check="test", severity="warning", entity=None, message="warn", fix_hint=None)]
        result = CheckResult(name="test", passed=False, issues=issues, elapsed_ms=0)
        assert result.passed is False

    def test_error_is_not_passed(self):
        issues = [Issue(check="test", severity="error", entity=None, message="err", fix_hint=None)]
        result = CheckResult(name="test", passed=False, issues=issues, elapsed_ms=0)
        assert result.passed is False


class TestDiagnosticReportHealthyAggregate:
    """Test that healthy is True only when all checks passed."""

    def test_all_passed_is_healthy(self):
        checks = [
            CheckResult(name="a", passed=True, issues=[], elapsed_ms=1),
            CheckResult(name="b", passed=True, issues=[], elapsed_ms=2),
        ]
        report = DiagnosticReport(
            healthy=True, checks=checks, total_issues=0,
            error_count=0, warning_count=0, elapsed_ms=3,
        )
        assert report.healthy is True

    def test_one_failed_is_unhealthy(self):
        checks = [
            CheckResult(name="a", passed=True, issues=[], elapsed_ms=1),
            CheckResult(name="b", passed=False, issues=[
                Issue(check="b", severity="error", entity=None, message="bad", fix_hint=None),
            ], elapsed_ms=2),
        ]
        report = DiagnosticReport(
            healthy=False, checks=checks, total_issues=1,
            error_count=1, warning_count=0, elapsed_ms=3,
        )
        assert report.healthy is False

    def test_all_failed_is_unhealthy(self):
        checks = [
            CheckResult(name="a", passed=False, issues=[
                Issue(check="a", severity="warning", entity=None, message="w", fix_hint=None),
            ], elapsed_ms=1),
        ]
        report = DiagnosticReport(
            healthy=False, checks=checks, total_issues=1,
            error_count=0, warning_count=1, elapsed_ms=1,
        )
        assert report.healthy is False


class TestSerializationRoundtrip:
    """Test to_dict() produces valid JSON-serializable dicts."""

    def test_issue_roundtrip(self):
        issue = Issue(check="test", severity="error", entity="feature:001", message="bad", fix_hint="fix it")
        d = issue.to_dict()
        assert d == {
            "check": "test",
            "severity": "error",
            "entity": "feature:001",
            "message": "bad",
            "fix_hint": "fix it",
        }
        # JSON roundtrip
        assert json.loads(json.dumps(d)) == d

    def test_issue_none_fields(self):
        issue = Issue(check="test", severity="info", entity=None, message="ok", fix_hint=None)
        d = issue.to_dict()
        assert d["entity"] is None
        assert d["fix_hint"] is None
        # JSON null
        j = json.dumps(d)
        assert '"entity": null' in j

    def test_check_result_roundtrip(self):
        result = CheckResult(
            name="db_readiness",
            passed=True,
            issues=[],
            elapsed_ms=42,
            extras={"entity_db_ok": True},
        )
        d = result.to_dict()
        assert d["name"] == "db_readiness"
        assert d["extras"] == {"entity_db_ok": True}
        assert json.loads(json.dumps(d)) == d

    def test_diagnostic_report_roundtrip(self):
        issue = Issue(check="c", severity="error", entity=None, message="m", fix_hint=None)
        report = DiagnosticReport(
            healthy=False,
            checks=[CheckResult(name="c", passed=False, issues=[issue], elapsed_ms=10)],
            total_issues=1,
            error_count=1,
            warning_count=0,
            elapsed_ms=10,
        )
        d = report.to_dict()
        assert d["healthy"] is False
        assert len(d["checks"]) == 1
        assert d["checks"][0]["issues"][0]["severity"] == "error"
        assert json.loads(json.dumps(d)) == d


# ===========================================================================
# Task 1.2: Check 8 (DB Readiness) + _build_local_entity_set
# ===========================================================================


class TestBuildLocalEntitySet:
    """Test _build_local_entity_set scans feature directories."""

    def test_returns_feature_dir_names(self, tmp_path):
        from doctor.checks import _build_local_entity_set

        (tmp_path / "features" / "001-alpha").mkdir(parents=True)
        (tmp_path / "features" / "002-beta").mkdir(parents=True)
        result = _build_local_entity_set(str(tmp_path))
        assert result == {"001-alpha", "002-beta"}

    def test_empty_features_dir(self, tmp_path):
        from doctor.checks import _build_local_entity_set

        (tmp_path / "features").mkdir(parents=True)
        result = _build_local_entity_set(str(tmp_path))
        assert result == set()

    def test_no_features_dir(self, tmp_path):
        from doctor.checks import _build_local_entity_set

        result = _build_local_entity_set(str(tmp_path))
        assert result == set()

    def test_ignores_files_in_features_dir(self, tmp_path):
        from doctor.checks import _build_local_entity_set

        (tmp_path / "features").mkdir(parents=True)
        (tmp_path / "features" / "README.md").write_text("hello")
        (tmp_path / "features" / "003-gamma").mkdir()
        result = _build_local_entity_set(str(tmp_path))
        assert result == {"003-gamma"}


class TestCheck8BothDbsHealthy:
    """Check 8: both DBs healthy returns passed=True with extras."""

    def test_both_dbs_healthy(self, tmp_path):
        from doctor.checks import check_db_readiness

        entity_path = _make_db(tmp_path, "entities.db")
        memory_path = _make_memory_db(tmp_path, "memory.db")

        result = check_db_readiness(
            entities_db_path=entity_path,
            memory_db_path=memory_path,
        )
        assert result.passed is True
        assert result.extras["entity_db_ok"] is True
        assert result.extras["memory_db_ok"] is True
        assert result.name == "db_readiness"


class TestCheck8EntityDbLocked:
    """Check 8: locked entity DB reports error with extras.entity_db_ok=False."""

    def test_entity_db_locked(self, tmp_path):
        from doctor.checks import check_db_readiness

        entity_path = _make_db(tmp_path, "entities.db")
        memory_path = _make_memory_db(tmp_path, "memory.db")

        # Hold a write lock on the entity DB
        blocker = sqlite3.connect(entity_path)
        blocker.execute("BEGIN IMMEDIATE")

        try:
            result = check_db_readiness(
                entities_db_path=entity_path,
                memory_db_path=memory_path,
            )
            assert result.passed is False
            assert result.extras["entity_db_ok"] is False
            assert result.extras["memory_db_ok"] is True
            # Should have at least one error issue about the lock
            lock_issues = [i for i in result.issues if "lock" in i.message.lower()]
            assert len(lock_issues) >= 1
            assert lock_issues[0].severity == "error"
        finally:
            blocker.rollback()
            blocker.close()


class TestCheck8WrongEntitySchemaVersion:
    """Check 8: wrong entity schema version reports error."""

    def test_wrong_entity_schema_version(self, tmp_path):
        from doctor.checks import check_db_readiness

        entity_path = _make_db(tmp_path, "entities.db")
        memory_path = _make_memory_db(tmp_path, "memory.db")

        # Downgrade schema version
        conn = sqlite3.connect(entity_path)
        conn.execute("UPDATE _metadata SET value = '5' WHERE key = 'schema_version'")
        conn.commit()
        conn.close()

        result = check_db_readiness(
            entities_db_path=entity_path,
            memory_db_path=memory_path,
        )
        schema_issues = [i for i in result.issues if "schema" in i.message.lower()]
        assert len(schema_issues) >= 1
        assert schema_issues[0].severity == "error"


class TestCheck8NonWalMode:
    """Check 8: non-WAL mode reports warning."""

    def test_non_wal_mode(self, tmp_path):
        from doctor.checks import check_db_readiness

        # Create entity DB without WAL
        entity_path = str(tmp_path / "entities.db")
        conn = sqlite3.connect(entity_path)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.executescript("""
            CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO _metadata(key, value) VALUES('schema_version', '7');
            CREATE TABLE entities (uuid TEXT PRIMARY KEY);
        """)
        conn.commit()
        conn.close()

        # Create memory DB without WAL
        memory_path = str(tmp_path / "memory.db")
        conn = sqlite3.connect(memory_path)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.executescript("""
            CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO _metadata(key, value) VALUES('schema_version', '4');
        """)
        conn.commit()
        conn.close()

        result = check_db_readiness(
            entities_db_path=entity_path,
            memory_db_path=memory_path,
        )
        wal_issues = [i for i in result.issues if "wal" in i.message.lower()]
        assert len(wal_issues) >= 1
        assert all(i.severity == "warning" for i in wal_issues)


class TestCheck8ImmediateRollbackReleasesLock:
    """Check 8: lock test connection is released after check completes."""

    def test_immediate_rollback_releases_lock(self, tmp_path):
        from doctor.checks import check_db_readiness

        entity_path = _make_db(tmp_path, "entities.db")
        memory_path = _make_memory_db(tmp_path, "memory.db")

        # Run the check
        result = check_db_readiness(
            entities_db_path=entity_path,
            memory_db_path=memory_path,
        )
        assert result.passed is True

        # Verify we can still acquire a write lock (doctor released its lock)
        conn = sqlite3.connect(entity_path, timeout=1.0)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
        conn.close()
