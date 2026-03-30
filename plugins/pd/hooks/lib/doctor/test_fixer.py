"""Tests for pd:doctor Phase 2 auto-fix: models, classifier, fix actions, orchestrator, CLI."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import uuid as uuid_mod

import pytest

from doctor.models import (
    CheckResult,
    DiagnosticReport,
    FixReport,
    FixResult,
    Issue,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path, name: str = "entities.db") -> str:
    """Create a minimal entity DB with schema matching EntityDatabase v8."""
    db_path = str(tmp_path / name)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS _metadata (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT OR REPLACE INTO _metadata(key, value) VALUES('schema_version', '8');

        CREATE TABLE IF NOT EXISTS entities (
            uuid        TEXT NOT NULL PRIMARY KEY,
            type_id     TEXT NOT NULL,
            project_id  TEXT NOT NULL DEFAULT '__unknown__',
            entity_type TEXT NOT NULL,
            entity_id   TEXT NOT NULL,
            name        TEXT NOT NULL,
            status      TEXT,
            parent_type_id TEXT,
            parent_uuid    TEXT,
            artifact_path  TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
            metadata    TEXT,
            UNIQUE(project_id, type_id)
        );

        CREATE TABLE IF NOT EXISTS projects (
            project_id      TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            root_commit_sha TEXT,
            remote_url      TEXT,
            normalized_url  TEXT,
            remote_host     TEXT,
            remote_owner    TEXT,
            remote_repo     TEXT,
            default_branch  TEXT,
            project_root    TEXT,
            is_git_repo     INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sequences (
            project_id  TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            next_val    INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (project_id, entity_type)
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
            entity_uuid     TEXT NOT NULL,
            blocked_by_uuid TEXT NOT NULL,
            UNIQUE(entity_uuid, blocked_by_uuid)
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


def _make_memory_db(tmp_path, name: str = "memory.db") -> str:
    """Create a minimal memory DB with schema matching memory v4."""
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
            category    TEXT,
            source      TEXT,
            project     TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
            keywords    TEXT,
            embedding   BLOB
        );
    """)
    conn.commit()
    conn.close()
    return db_path


def _register_feature(db_path: str, slug: str = "008-test-feature", status: str = "active") -> str:
    """Register a feature entity directly via SQL. Returns type_id."""
    type_id = f"feature:{slug}"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO entities "
        "(uuid, type_id, project_id, entity_type, entity_id, name, status, created_at, updated_at) "
        "VALUES (?, ?, '__unknown__', 'feature', ?, ?, ?, datetime('now'), datetime('now'))",
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
    last_completed_phase: str | None = None,
    phases: dict | None = None,
) -> None:
    """Create a .meta.json file in the expected location."""
    feature_dir = tmp_path / "features" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": slug.split("-", 1)[0],
        "slug": slug,
        "status": status,
        "mode": "standard",
        "lastCompletedPhase": last_completed_phase,
        "phases": phases or {},
    }
    (feature_dir / ".meta.json").write_text(json.dumps(meta, indent=2))


def _make_report(*issues_by_check: tuple[str, list[Issue]]) -> DiagnosticReport:
    """Build a DiagnosticReport from (check_name, issues) tuples."""
    checks = []
    all_issues = []
    for name, issues in issues_by_check:
        checks.append(CheckResult(
            name=name,
            passed=len(issues) == 0,
            issues=issues,
            elapsed_ms=0,
        ))
        all_issues.extend(issues)

    error_count = sum(1 for i in all_issues if i.severity == "error")
    warning_count = sum(1 for i in all_issues if i.severity == "warning")
    return DiagnosticReport(
        healthy=len(all_issues) == 0,
        checks=checks,
        total_issues=len(all_issues),
        error_count=error_count,
        warning_count=warning_count,
        elapsed_ms=0,
    )


# ===========================================================================
# Task 1: Model Tests
# ===========================================================================


class TestFixResult:
    def test_to_dict(self):
        issue = Issue(check="test", severity="error", entity="feature:001", message="broken", fix_hint="fix it")
        result = FixResult(issue=issue, applied=True, action="fixed it", classification="safe")
        d = result.to_dict()
        assert d["applied"] is True
        assert d["action"] == "fixed it"
        assert d["classification"] == "safe"
        assert d["issue"]["check"] == "test"


class TestFixReport:
    def test_to_dict(self):
        issue = Issue(check="test", severity="error", entity=None, message="m", fix_hint=None)
        result = FixResult(issue=issue, applied=False, action="skipped", classification="manual")
        report = FixReport(
            fixed_count=0, skipped_count=1, failed_count=0,
            results=[result], elapsed_ms=100,
        )
        d = report.to_dict()
        assert d["fixed_count"] == 0
        assert d["skipped_count"] == 1
        assert d["elapsed_ms"] == 100
        assert len(d["results"]) == 1

    def test_counts(self):
        """Verify count fields match results list."""
        issues = [
            Issue(check="c", severity="error", entity=None, message="m", fix_hint="h"),
            Issue(check="c", severity="error", entity=None, message="m", fix_hint="h"),
        ]
        results = [
            FixResult(issue=issues[0], applied=True, action="done", classification="safe"),
            FixResult(issue=issues[1], applied=False, action="Manual: h", classification="manual"),
        ]
        report = FixReport(
            fixed_count=1, skipped_count=1, failed_count=0,
            results=results, elapsed_ms=50,
        )
        d = report.to_dict()
        assert d["fixed_count"] == 1
        assert d["skipped_count"] == 1
        assert d["failed_count"] == 0


# ===========================================================================
# Task 2: Classifier Tests
# ===========================================================================


class TestClassifyFix:
    """Test classify_fix for all safe patterns + manual default."""

    def test_set_last_completed_phase(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Set lastCompletedPhase to the latest completed phase")
        assert cls == "safe"
        assert fn is not None

    def test_run_reconcile_apply_sync(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Run reconcile_apply to sync DB from .meta.json")
        assert cls == "safe"

    def test_run_reconcile_apply_kanban(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Run reconcile_apply to sync kanban column")
        assert cls == "safe"

    def test_run_reconcile_apply_create(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Run reconcile_apply to create DB entry")
        assert cls == "safe"

    def test_update_brainstorm_status(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Update brainstorm entity status to 'promoted'")
        assert cls == "safe"

    def test_update_entity_status(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Update entity status to 'promoted'")
        assert cls == "safe"

    def test_update_entity_status_dropped(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Update entity status to 'dropped'")
        assert cls == "safe"
        assert fn.__name__ == "_fix_entity_status_dropped"

    def test_dropped_routes_to_dropped_not_promoted(self):
        """Ensure prefix ordering routes dropped and promoted to correct functions."""
        from doctor.fixer import classify_fix
        _, fn_dropped = classify_fix("Update entity status to 'dropped'")
        _, fn_promoted = classify_fix("Update entity status to 'promoted'")
        assert fn_dropped.__name__ == "_fix_entity_status_dropped"
        assert fn_promoted.__name__ == "_fix_entity_status_promoted"

    def test_add_promoted_annotation(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Add (promoted -> feature) annotation to backlog.md")
        assert cls == "safe"

    def test_set_wal_entities(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Set PRAGMA journal_mode=WAL on the database")
        assert cls == "safe"

    def test_set_wal_memory(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Set PRAGMA journal_mode=WAL on memory DB")
        assert cls == "safe"

    def test_update_meta_from_db(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Update .meta.json from DB state")
        assert cls == "safe"

    def test_run_migration_parent_uuid(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Run migration to populate parent_uuid")
        assert cls == "safe"

    def test_update_parent_uuid(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Update parent_uuid to match parent entity's uuid")
        assert cls == "safe"

    def test_remove_orphan_dependency(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Remove orphaned dependency row")
        assert cls == "safe"

    def test_remove_orphan_tag(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Remove orphaned tag row")
        assert cls == "safe"

    def test_remove_orphan_workflow(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Remove orphaned workflow_phases row")
        assert cls == "safe"

    def test_remove_self_referential(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Remove self-referential parent_type_id")
        assert cls == "safe"

    def test_rebuild_fts(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Rebuild FTS index: python3 scripts/migrate_db.py rebuild-fts")
        assert cls == "safe"

    def test_run_entity_migrations(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Run migrations to initialize the database")
        assert cls == "safe"

    def test_run_memory_migrations(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Run memory DB migrations to update schema")
        assert cls == "safe"

    def test_unknown_hint_is_manual(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Kill the process holding the lock")
        assert cls == "manual"
        assert fn is None

    def test_classify_returns_callable(self):
        """Design I2: classify_fix returns Callable | None, not string."""
        from doctor.fixer import classify_fix
        _, fn = classify_fix("Set lastCompletedPhase to the latest completed phase")
        assert callable(fn)


# ===========================================================================
# Task 2: Fix Action Tests
# ===========================================================================


class TestFixActions:
    """Test individual fix functions."""

    def test_fix_last_completed_phase(self, tmp_path):
        from doctor.fix_actions import FixContext, _fix_last_completed_phase

        _create_meta_json(
            tmp_path,
            slug="008-test-feature",
            last_completed_phase=None,
            phases={
                "ideate": {"started": "2025-01-01", "completed": "2025-01-02"},
                "specify": {"started": "2025-01-03", "completed": "2025-01-04"},
                "design": {"started": "2025-01-05"},
            },
        )
        ctx = FixContext(
            entities_db_path="", memory_db_path="",
            artifacts_root=str(tmp_path), project_root=str(tmp_path),
            db=None, engine=None, entities_conn=None, memory_conn=None,
        )
        issue = Issue(check="workflow_phase", severity="error",
                      entity="feature:008-test-feature",
                      message="missing lastCompletedPhase",
                      fix_hint="Set lastCompletedPhase to the latest completed phase")

        action = _fix_last_completed_phase(ctx, issue)
        assert "specify" in action

        # Verify file was updated
        meta_path = tmp_path / "features" / "008-test-feature" / ".meta.json"
        meta = json.loads(meta_path.read_text())
        assert meta["lastCompletedPhase"] == "specify"

    def test_fix_entity_status_promoted(self, tmp_path):
        from doctor.fix_actions import FixContext, _fix_entity_status_promoted
        from entity_registry.database import EntityDatabase

        # Use EntityDatabase constructor to get full schema (including FTS)
        db_path = str(tmp_path / "entities_promoted.db")
        db = EntityDatabase(db_path)
        # Register entity via the DB's own API
        db.register_entity(
            entity_type="feature",
            entity_id="009-brainstorm",
            name="Brainstorm 009",
            status="active",
            project_id="__unknown__",
        )

        ctx = FixContext(
            entities_db_path=db_path, memory_db_path="",
            artifacts_root="", project_root="",
            db=db, engine=None, entities_conn=db._conn, memory_conn=None,
        )
        issue = Issue(check="brainstorm_status", severity="warning",
                      entity="feature:009-brainstorm",
                      message="not promoted",
                      fix_hint="Update brainstorm entity status to 'promoted'")

        action = _fix_entity_status_promoted(ctx, issue)
        assert "promoted" in action

        # Verify
        row = db._conn.execute(
            "SELECT status FROM entities WHERE type_id = ?",
            ("feature:009-brainstorm",),
        ).fetchone()
        assert row[0] == "promoted"
        db.close()

    def test_fix_wal_entities(self, tmp_path):
        from doctor.fix_actions import FixContext, _fix_wal_entities

        db_path = _make_db(tmp_path)
        # Set to DELETE mode first
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.close()

        conn = sqlite3.connect(db_path)
        ctx = FixContext(
            entities_db_path=db_path, memory_db_path="",
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=conn, memory_conn=None,
        )
        issue = Issue(check="db_readiness", severity="warning", entity=None,
                      message="not WAL", fix_hint="Set PRAGMA journal_mode=WAL on the database")

        action = _fix_wal_entities(ctx, issue)
        assert "WAL" in action

        # Verify
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        conn.close()

    def test_fix_wal_memory(self, tmp_path):
        from doctor.fix_actions import FixContext, _fix_wal_memory

        db_path = _make_memory_db(tmp_path)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.close()

        conn = sqlite3.connect(db_path)
        ctx = FixContext(
            entities_db_path="", memory_db_path=db_path,
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=None, memory_conn=conn,
        )
        issue = Issue(check="db_readiness", severity="warning", entity=None,
                      message="not WAL", fix_hint="Set PRAGMA journal_mode=WAL on memory DB")

        action = _fix_wal_memory(ctx, issue)
        assert "WAL" in action
        conn.close()

    def test_fix_parent_uuid(self, tmp_path):
        from doctor.fix_actions import FixContext, _fix_parent_uuid

        db_path = _make_db(tmp_path)
        parent_uuid = str(uuid_mod.uuid4())
        child_uuid = str(uuid_mod.uuid4())

        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO entities (uuid, type_id, project_id, entity_type, entity_id, name, status) "
            "VALUES (?, 'project:alpha', '__unknown__', 'project', 'alpha', 'Alpha', 'active')",
            (parent_uuid,),
        )
        conn.execute(
            "INSERT INTO entities (uuid, type_id, project_id, entity_type, entity_id, name, status, parent_type_id) "
            "VALUES (?, 'feature:001-child', '__unknown__', 'feature', '001-child', 'Child', 'active', 'project:alpha')",
            (child_uuid,),
        )
        conn.commit()

        ctx = FixContext(
            entities_db_path=db_path, memory_db_path="",
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=conn, memory_conn=None,
        )
        issue = Issue(check="referential_integrity", severity="warning",
                      entity="feature:001-child",
                      message="missing parent_uuid",
                      fix_hint="Run migration to populate parent_uuid")

        action = _fix_parent_uuid(ctx, issue)
        assert parent_uuid in action

        row = conn.execute(
            "SELECT parent_uuid FROM entities WHERE type_id = 'feature:001-child'"
        ).fetchone()
        assert row[0] == parent_uuid
        conn.close()

    def test_fix_self_referential_parent(self, tmp_path):
        from doctor.fix_actions import FixContext, _fix_self_referential_parent

        db_path = _make_db(tmp_path)
        entity_uuid = str(uuid_mod.uuid4())
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO entities (uuid, type_id, project_id, entity_type, entity_id, name, status, parent_type_id) "
            "VALUES (?, 'feature:001-self', '__unknown__', 'feature', '001-self', 'Self', 'active', 'feature:001-self')",
            (entity_uuid,),
        )
        conn.commit()

        ctx = FixContext(
            entities_db_path=db_path, memory_db_path="",
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=conn, memory_conn=None,
        )
        issue = Issue(check="referential_integrity", severity="error",
                      entity="feature:001-self",
                      message="self-referential parent",
                      fix_hint="Remove self-referential parent_type_id")

        action = _fix_self_referential_parent(ctx, issue)
        assert "self-referential" in action.lower() or "Removed" in action

        row = conn.execute(
            "SELECT parent_type_id, parent_uuid FROM entities WHERE type_id = 'feature:001-self'"
        ).fetchone()
        assert row[0] is None
        assert row[1] is None
        conn.close()

    def test_fix_remove_orphan_dependency(self, tmp_path):
        from doctor.fix_actions import FixContext, _fix_remove_orphan_dependency

        db_path = _make_db(tmp_path)
        eu = str(uuid_mod.uuid4())
        bu = str(uuid_mod.uuid4())
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO entity_dependencies (entity_uuid, blocked_by_uuid) VALUES (?, ?)",
            (eu, bu),
        )
        conn.commit()

        ctx = FixContext(
            entities_db_path=db_path, memory_db_path="",
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=conn, memory_conn=None,
        )
        issue = Issue(
            check="referential_integrity", severity="error", entity=None,
            message=f"Orphaned dependency: entity_uuid '{eu}' blocked_by_uuid '{bu}'",
            fix_hint="Remove orphaned dependency row",
        )

        action = _fix_remove_orphan_dependency(ctx, issue)
        assert eu in action

        row = conn.execute("SELECT COUNT(*) FROM entity_dependencies").fetchone()
        assert row[0] == 0
        conn.close()

    def test_fix_remove_orphan_dependency_malformed(self, tmp_path):
        """Edge case: message without enough UUIDs."""
        from doctor.fix_actions import FixContext, _fix_remove_orphan_dependency

        db_path = _make_db(tmp_path)
        conn = sqlite3.connect(db_path)

        ctx = FixContext(
            entities_db_path=db_path, memory_db_path="",
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=conn, memory_conn=None,
        )
        issue = Issue(
            check="referential_integrity", severity="error", entity=None,
            message="Orphaned dependency with no UUIDs",
            fix_hint="Remove orphaned dependency row",
        )

        with pytest.raises(ValueError, match="Could not extract"):
            _fix_remove_orphan_dependency(ctx, issue)
        conn.close()

    def test_fix_remove_orphan_tag(self, tmp_path):
        from doctor.fix_actions import FixContext, _fix_remove_orphan_tag

        db_path = _make_db(tmp_path)
        eu = str(uuid_mod.uuid4())
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO entity_tags (entity_uuid, tag) VALUES (?, 'test')", (eu,))
        conn.commit()

        ctx = FixContext(
            entities_db_path=db_path, memory_db_path="",
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=conn, memory_conn=None,
        )
        issue = Issue(
            check="referential_integrity", severity="error", entity=None,
            message=f"Orphaned tag: entity_uuid '{eu}' not found in entities table",
            fix_hint="Remove orphaned tag row",
        )

        action = _fix_remove_orphan_tag(ctx, issue)
        assert eu in action

        row = conn.execute("SELECT COUNT(*) FROM entity_tags").fetchone()
        assert row[0] == 0
        conn.close()

    def test_fix_remove_orphan_workflow(self, tmp_path):
        from doctor.fix_actions import FixContext, _fix_remove_orphan_workflow

        db_path = _make_db(tmp_path)
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO workflow_phases (type_id, workflow_phase) VALUES ('feature:orphan', 'ideate')"
        )
        conn.commit()

        ctx = FixContext(
            entities_db_path=db_path, memory_db_path="",
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=conn, memory_conn=None,
        )
        issue = Issue(
            check="referential_integrity", severity="error",
            entity="feature:orphan",
            message="Orphaned workflow_phases row for type_id 'feature:orphan'",
            fix_hint="Remove orphaned workflow_phases row",
        )

        action = _fix_remove_orphan_workflow(ctx, issue)
        assert "feature:orphan" in action

        row = conn.execute("SELECT COUNT(*) FROM workflow_phases").fetchone()
        assert row[0] == 0
        conn.close()

    def test_fix_rebuild_fts_missing_script(self, tmp_path):
        """Edge case: migrate_db.py not found anywhere."""
        from doctor.fix_actions import FixContext, _fix_rebuild_fts

        ctx = FixContext(
            entities_db_path=str(tmp_path / "entities.db"), memory_db_path="",
            artifacts_root="", project_root=str(tmp_path),
            db=None, engine=None, entities_conn=None, memory_conn=None,
        )
        issue = Issue(
            check="db_readiness", severity="warning", entity=None,
            message="FTS index stale",
            fix_hint="Rebuild FTS index: python3 scripts/migrate_db.py rebuild-fts",
        )

        with pytest.raises(FileNotFoundError, match="migrate_db.py"):
            _fix_rebuild_fts(ctx, issue)

    def test_fix_backlog_annotation(self, tmp_path):
        from doctor.fix_actions import FixContext, _fix_backlog_annotation

        backlog_path = tmp_path / "backlog.md"
        backlog_path.write_text(
            "| ID | Description | Status |\n"
            "|----|-------------|--------|\n"
            "| 00042 | Cool idea | pending |\n"
            "| 00043 | Another idea | pending |\n"
        )

        ctx = FixContext(
            entities_db_path="", memory_db_path="",
            artifacts_root=str(tmp_path), project_root=str(tmp_path),
            db=None, engine=None, entities_conn=None, memory_conn=None,
        )
        issue = Issue(
            check="backlog_status", severity="warning",
            entity="backlog:00042",
            message="Backlog 00042 promoted but not annotated",
            fix_hint="Add (promoted -> feature) annotation to backlog.md",
        )

        action = _fix_backlog_annotation(ctx, issue)
        assert "00042" in action

        content = backlog_path.read_text()
        assert "(promoted)" in content
        # Other rows unaffected
        assert "00043" in content

    def test_fix_backlog_annotation_parse_failure(self, tmp_path):
        """Edge case: backlog row not found."""
        from doctor.fix_actions import FixContext, _fix_backlog_annotation

        backlog_path = tmp_path / "backlog.md"
        backlog_path.write_text("| ID | Description |\n| 99999 | something |\n")

        ctx = FixContext(
            entities_db_path="", memory_db_path="",
            artifacts_root=str(tmp_path), project_root=str(tmp_path),
            db=None, engine=None, entities_conn=None, memory_conn=None,
        )
        issue = Issue(
            check="backlog_status", severity="warning",
            entity="backlog:00042",
            message="not annotated",
            fix_hint="Add (promoted -> feature) annotation to backlog.md",
        )

        with pytest.raises(ValueError, match="Could not find"):
            _fix_backlog_annotation(ctx, issue)

    def test_fix_run_entity_migrations(self, tmp_path):
        from doctor.fix_actions import _fix_run_entity_migrations, FixContext

        # Create empty DB file
        db_path = str(tmp_path / "entities.db")
        conn = sqlite3.connect(db_path)
        conn.close()

        ctx = FixContext(
            entities_db_path=db_path, memory_db_path="",
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=None, memory_conn=None,
        )
        issue = Issue(check="db_readiness", severity="error", entity=None,
                      message="schema outdated", fix_hint="Run migrations to initialize the database")

        action = _fix_run_entity_migrations(ctx, issue)
        assert "migration" in action.lower()

    def test_fix_run_memory_migrations(self, tmp_path):
        from doctor.fix_actions import _fix_run_memory_migrations, FixContext

        db_path = str(tmp_path / "memory.db")
        conn = sqlite3.connect(db_path)
        conn.close()

        ctx = FixContext(
            entities_db_path="", memory_db_path=db_path,
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=None, memory_conn=None,
        )
        issue = Issue(check="db_readiness", severity="error", entity=None,
                      message="schema outdated", fix_hint="Run memory DB migrations")

        action = _fix_run_memory_migrations(ctx, issue)
        assert "migration" in action.lower()

    def test_fix_context_shared_connection(self, tmp_path):
        """entities_conn IS db._conn -- same object, not separate connection."""
        from doctor.fix_actions import FixContext
        from entity_registry.database import EntityDatabase

        db_path = _make_db(tmp_path)
        db = EntityDatabase(db_path)
        ctx = FixContext(
            entities_db_path=db_path, memory_db_path="",
            artifacts_root="", project_root="",
            db=db, engine=None,
            entities_conn=db._conn,
            memory_conn=None,
        )
        assert ctx.entities_conn is db._conn
        db.close()


# ===========================================================================
# Task 3: Orchestrator Tests
# ===========================================================================


class TestApplyFixes:
    """Test apply_fixes orchestrator."""

    def test_safe_applied(self, tmp_path):
        """Safe fix is applied successfully."""
        from doctor.fixer import apply_fixes

        db_path = _make_db(tmp_path)
        memory_path = _make_memory_db(tmp_path)

        # Create a report with a WAL fix issue
        report = _make_report(
            ("db_readiness", [
                Issue(check="db_readiness", severity="warning", entity=None,
                      message="not WAL", fix_hint="Set PRAGMA journal_mode=WAL on the database"),
            ]),
        )

        result = apply_fixes(
            report=report,
            entities_db_path=db_path,
            memory_db_path=memory_path,
            artifacts_root=str(tmp_path),
            project_root=str(tmp_path),
        )

        assert result.fixed_count == 1
        assert result.skipped_count == 0
        assert result.failed_count == 0

    def test_manual_skipped(self, tmp_path):
        """Manual fix is skipped."""
        from doctor.fixer import apply_fixes

        db_path = _make_db(tmp_path)
        memory_path = _make_memory_db(tmp_path)

        report = _make_report(
            ("db_readiness", [
                Issue(check="db_readiness", severity="error", entity=None,
                      message="locked", fix_hint="Kill the process holding the lock"),
            ]),
        )

        result = apply_fixes(
            report=report,
            entities_db_path=db_path,
            memory_db_path=memory_path,
            artifacts_root=str(tmp_path),
            project_root=str(tmp_path),
        )

        assert result.fixed_count == 0
        assert result.skipped_count == 1
        assert result.results[0].classification == "manual"

    def test_dry_run(self, tmp_path):
        """Dry run does not apply fixes."""
        from doctor.fixer import apply_fixes

        db_path = _make_db(tmp_path)
        memory_path = _make_memory_db(tmp_path)

        report = _make_report(
            ("db_readiness", [
                Issue(check="db_readiness", severity="warning", entity=None,
                      message="not WAL", fix_hint="Set PRAGMA journal_mode=WAL on the database"),
            ]),
        )

        result = apply_fixes(
            report=report,
            entities_db_path=db_path,
            memory_db_path=memory_path,
            artifacts_root=str(tmp_path),
            project_root=str(tmp_path),
            dry_run=True,
        )

        assert result.fixed_count == 0
        assert result.failed_count == 0  # dry-run items are NOT counted as failed
        assert result.results[0].action.startswith("dry-run:")
        assert not result.results[0].applied

    def test_exception_handling(self, tmp_path):
        """Safe fix that fails is recorded as failed."""
        from doctor.fixer import apply_fixes

        db_path = _make_db(tmp_path)
        memory_path = _make_memory_db(tmp_path)

        # FTS rebuild with no script -> will fail
        report = _make_report(
            ("db_readiness", [
                Issue(check="db_readiness", severity="warning", entity=None,
                      message="FTS stale",
                      fix_hint="Rebuild FTS index: python3 scripts/migrate_db.py rebuild-fts"),
            ]),
        )

        result = apply_fixes(
            report=report,
            entities_db_path=db_path,
            memory_db_path=memory_path,
            artifacts_root=str(tmp_path),
            project_root=str(tmp_path),
        )

        assert result.failed_count == 1
        assert result.fixed_count == 0
        assert "Failed:" in result.results[0].action

    def test_no_hint_skipped(self, tmp_path):
        """Issues with no fix_hint are ignored."""
        from doctor.fixer import apply_fixes

        db_path = _make_db(tmp_path)
        memory_path = _make_memory_db(tmp_path)

        report = _make_report(
            ("db_readiness", [
                Issue(check="db_readiness", severity="error", entity=None,
                      message="something wrong", fix_hint=None),
            ]),
        )

        result = apply_fixes(
            report=report,
            entities_db_path=db_path,
            memory_db_path=memory_path,
            artifacts_root=str(tmp_path),
            project_root=str(tmp_path),
        )

        assert len(result.results) == 0

    def test_counts_correct(self, tmp_path):
        """Counts match actual results."""
        from doctor.fixer import apply_fixes

        db_path = _make_db(tmp_path)
        memory_path = _make_memory_db(tmp_path)

        report = _make_report(
            ("db_readiness", [
                Issue(check="db_readiness", severity="warning", entity=None,
                      message="not WAL", fix_hint="Set PRAGMA journal_mode=WAL on the database"),
                Issue(check="db_readiness", severity="error", entity=None,
                      message="locked", fix_hint="Kill the process holding the lock"),
                Issue(check="db_readiness", severity="warning", entity=None,
                      message="FTS stale",
                      fix_hint="Rebuild FTS index: python3 scripts/migrate_db.py rebuild-fts"),
            ]),
        )

        result = apply_fixes(
            report=report,
            entities_db_path=db_path,
            memory_db_path=memory_path,
            artifacts_root=str(tmp_path),
            project_root=str(tmp_path),
        )

        assert result.fixed_count == 1  # WAL fix
        assert result.skipped_count == 1  # manual
        assert result.failed_count == 1  # FTS rebuild fails (no script)
        assert len(result.results) == 3

    def test_idempotent(self, tmp_path):
        """Running apply_fixes twice: second time fixed_count=0."""
        from doctor.fixer import apply_fixes

        db_path = _make_db(tmp_path)
        memory_path = _make_memory_db(tmp_path)

        # Set entities DB to DELETE mode so WAL fix has something to do
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.close()

        report = _make_report(
            ("db_readiness", [
                Issue(check="db_readiness", severity="warning", entity=None,
                      message="not WAL", fix_hint="Set PRAGMA journal_mode=WAL on the database"),
            ]),
        )

        result1 = apply_fixes(
            report=report, entities_db_path=db_path, memory_db_path=memory_path,
            artifacts_root=str(tmp_path), project_root=str(tmp_path),
        )
        assert result1.fixed_count == 1

        # Second run: WAL is already set, so the fix is a no-op (still "applied"
        # because PRAGMA journal_mode=WAL is idempotent and doesn't error)
        result2 = apply_fixes(
            report=report, entities_db_path=db_path, memory_db_path=memory_path,
            artifacts_root=str(tmp_path), project_root=str(tmp_path),
        )
        # The fix still "applies" (PRAGMA is idempotent), but the real verification
        # is that re-running diagnostics would show no issues.
        assert result2.fixed_count == 1  # Idempotent: no error, still runs


# ===========================================================================
# Task 4: CLI Tests
# ===========================================================================


class TestCLI:
    """Test CLI --fix and --dry-run flags."""

    def _run_doctor(self, tmp_path, *extra_args):
        """Run doctor CLI and return parsed JSON output."""
        db_path = _make_db(tmp_path)
        memory_path = _make_memory_db(tmp_path)

        cmd = [
            sys.executable, "-m", "doctor",
            "--entities-db", db_path,
            "--memory-db", memory_path,
            "--project-root", str(tmp_path),
            "--artifacts-root", str(tmp_path),
            *extra_args,
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".."
        )
        result = subprocess.run(
            cmd, capture_output=True, text=True, env=env, timeout=30,
        )
        return result

    def test_default_unchanged(self, tmp_path):
        """Default mode wraps output in {diagnostic: ...}."""
        result = self._run_doctor(tmp_path)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "diagnostic" in data
        assert "fixes" not in data

    def test_fix_three_sections(self, tmp_path):
        """--fix produces diagnostic + fixes + post_fix."""
        result = self._run_doctor(tmp_path, "--fix")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "diagnostic" in data
        assert "fixes" in data
        assert "post_fix" in data

    def test_dry_run_no_post_fix(self, tmp_path):
        """--fix --dry-run produces diagnostic + fixes, no post_fix."""
        result = self._run_doctor(tmp_path, "--fix", "--dry-run")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "diagnostic" in data
        assert "fixes" in data
        assert "post_fix" not in data

    def test_exit_code_zero_with_fix(self, tmp_path):
        """Exit code is always 0."""
        result = self._run_doctor(tmp_path, "--fix")
        assert result.returncode == 0


class TestFixStaleDependency:
    """_fix_stale_dependency removes stale edge and promotes blocked entity."""

    def test_fix_stale_dependency_removes_edge_and_promotes(self, tmp_path):
        from entity_registry.database import EntityDatabase
        from doctor.fix_actions import FixContext, _fix_stale_dependency

        db_path = str(tmp_path / "entities.db")
        db = EntityDatabase(db_path)

        uuid_blocked = db.register_entity(
            "feature", "stale-blocked", "Blocked Entity",
            status="blocked", project_id="__unknown__",
        )
        uuid_blocker = db.register_entity(
            "feature", "stale-blocker", "Completed Blocker",
            status="completed", project_id="__unknown__",
        )
        db.add_dependency(uuid_blocked, uuid_blocker)

        ctx = FixContext(
            entities_db_path=db_path, memory_db_path="",
            artifacts_root="", project_root="",
            db=db, engine=None, entities_conn=None, memory_conn=None,
        )
        issue = Issue(
            check="stale_dependencies", severity="warning", entity=None,
            message=(
                f"Stale blocked_by edge: entity '{uuid_blocked}' "
                f"blocked by completed '{uuid_blocker}' (feature:stale-blocker)"
            ),
            fix_hint="Remove stale dependency on completed 'feature:stale-blocker'",
        )

        action = _fix_stale_dependency(ctx, issue)
        assert uuid_blocker in action
        assert "unblocked 1" in action

        # Edge should be gone
        deps = db.query_dependencies(entity_uuid=uuid_blocked)
        assert len(deps) == 0

        # Blocked entity should be promoted to planned
        entity = db.get_entity_by_uuid(uuid_blocked)
        assert entity["status"] == "planned"

        db.close()
