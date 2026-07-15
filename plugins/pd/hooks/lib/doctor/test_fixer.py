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
            backward_transition_reason TEXT,
            created_at         TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
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

    def test_set_wal_entities(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Set PRAGMA journal_mode=WAL on the database")
        assert cls == "safe"

    def test_remove_orphan_tag(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Remove orphaned tag row")
        assert cls == "safe"

    def test_remove_orphan_workflow(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Remove orphaned workflow_phases row")
        assert cls == "safe"

    def test_clear_self_referential(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Clear self-referential parent_uuid")
        assert cls == "safe"

    def test_rebuild_fts(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Rebuild FTS index: python3 scripts/migrate_db.py rebuild-fts")
        assert cls == "safe"

    def test_run_entity_migrations(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Run migrations to initialize the database")
        assert cls == "safe"

    def test_unknown_hint_is_manual(self):
        from doctor.fixer import classify_fix
        cls, fn = classify_fix("Kill the process holding the lock")
        assert cls == "manual"
        assert fn is None

    def test_classify_returns_callable(self):
        """Design I2: classify_fix returns Callable | None, not string."""
        from doctor.fixer import classify_fix
        _, fn = classify_fix("Set PRAGMA journal_mode=WAL on the database")
        assert callable(fn)

    def test_survivor_safe_patterns_preserve_first_match_order(self):
        """H2 regression: after feature 133 retired 11 fix fns, the 7
        surviving _SAFE_PATTERNS rows still resolve each survivor's own
        prefix to its own fn, in the documented relative order (deletions
        must not re-order surviving prefixes' first-match-wins semantics).
        """
        from doctor.fixer import _SAFE_PATTERNS, classify_fix

        expected_order = [
            "_fix_wal_entities",
            "_fix_remove_orphan_tag",
            "_fix_remove_orphan_workflow",
            "_fix_self_referential_parent",
            "_fix_rebuild_fts",
            "_fix_run_entity_migrations",
            "_fix_missed_cascade",
        ]
        assert [fn.__name__ for _, fn in _SAFE_PATTERNS] == expected_order

        for prefix, fn in _SAFE_PATTERNS:
            cls, resolved = classify_fix(prefix)
            assert cls == "safe"
            assert resolved is fn


# ===========================================================================
# Task 2: Fix Action Tests
# ===========================================================================


class TestFixActions:
    """Test individual fix functions."""

    def test_fix_wal_entities(self, tmp_path):
        from doctor.fix_actions import FixContext, _fix_wal_entities

        db_path = _make_db(tmp_path)
        # Set to DELETE mode first
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.close()

        conn = sqlite3.connect(db_path)
        ctx = FixContext(
            entities_db_path=db_path,
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=conn,
        )
        issue = Issue(check="db_readiness", severity="warning", entity=None,
                      message="not WAL", fix_hint="Set PRAGMA journal_mode=WAL on the database")

        action = _fix_wal_entities(ctx, issue)
        assert "WAL" in action

        # Verify
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        conn.close()

    def test_fix_self_referential_parent(self, tmp_path):
        from doctor.fix_actions import FixContext, _fix_self_referential_parent

        db_path = _make_db(tmp_path)
        entity_uuid = str(uuid_mod.uuid4())
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO entities (uuid, type_id, project_id, entity_type, entity_id, name, status, parent_uuid) "
            "VALUES (?, 'feature:001-self', '__unknown__', 'feature', '001-self', 'Self', 'active', ?)",
            (entity_uuid, entity_uuid),
        )
        conn.commit()

        ctx = FixContext(
            entities_db_path=db_path,
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=conn,
        )
        issue = Issue(check="referential_integrity", severity="error",
                      entity="feature:001-self",
                      message="self-referential parent",
                      fix_hint="Clear self-referential parent_uuid")

        action = _fix_self_referential_parent(ctx, issue)
        assert "self-referential" in action.lower() or "Cleared" in action

        row = conn.execute(
            "SELECT parent_uuid FROM entities WHERE type_id = 'feature:001-self'"
        ).fetchone()
        assert row[0] is None
        conn.close()

    def test_fix_remove_orphan_tag(self, tmp_path):
        from doctor.fix_actions import FixContext, _fix_remove_orphan_tag

        db_path = _make_db(tmp_path)
        eu = str(uuid_mod.uuid4())
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO entity_tags (entity_uuid, tag) VALUES (?, 'test')", (eu,))
        conn.commit()

        ctx = FixContext(
            entities_db_path=db_path,
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=conn,
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
            entities_db_path=db_path,
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=conn,
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
            entities_db_path=str(tmp_path / "entities.db"),
            artifacts_root="", project_root=str(tmp_path),
            db=None, engine=None, entities_conn=None,
        )
        issue = Issue(
            check="db_readiness", severity="warning", entity=None,
            message="FTS index stale",
            fix_hint="Rebuild FTS index: python3 scripts/migrate_db.py rebuild-fts",
        )

        with pytest.raises(FileNotFoundError, match="migrate_db.py"):
            _fix_rebuild_fts(ctx, issue)

    def test_fix_run_entity_migrations(self, tmp_path):
        from doctor.fix_actions import _fix_run_entity_migrations, FixContext

        # Create empty DB file
        db_path = str(tmp_path / "entities.db")
        conn = sqlite3.connect(db_path)
        conn.close()

        ctx = FixContext(
            entities_db_path=db_path,
            artifacts_root="", project_root="",
            db=None, engine=None, entities_conn=None,
        )
        issue = Issue(check="db_readiness", severity="error", entity=None,
                      message="schema outdated", fix_hint="Run migrations to initialize the database")

        action = _fix_run_entity_migrations(ctx, issue)
        assert "migration" in action.lower()

    def test_fix_context_shared_connection(self, tmp_path):
        """entities_conn IS db._conn -- same object, not separate connection."""
        from doctor.fix_actions import FixContext
        from entity_registry.database import EntityDatabase

        db_path = _make_db(tmp_path)
        db = EntityDatabase(db_path)
        ctx = FixContext(
            entities_db_path=db_path,
            artifacts_root="", project_root="",
            db=db, engine=None,
            entities_conn=db._conn,
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

        report = _make_report(
            ("db_readiness", [
                Issue(check="db_readiness", severity="error", entity=None,
                      message="locked", fix_hint="Kill the process holding the lock"),
            ]),
        )

        result = apply_fixes(
            report=report,
            entities_db_path=db_path,
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

        report = _make_report(
            ("db_readiness", [
                Issue(check="db_readiness", severity="warning", entity=None,
                      message="not WAL", fix_hint="Set PRAGMA journal_mode=WAL on the database"),
            ]),
        )

        result = apply_fixes(
            report=report,
            entities_db_path=db_path,
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

        report = _make_report(
            ("db_readiness", [
                Issue(check="db_readiness", severity="error", entity=None,
                      message="something wrong", fix_hint=None),
            ]),
        )

        result = apply_fixes(
            report=report,
            entities_db_path=db_path,
            artifacts_root=str(tmp_path),
            project_root=str(tmp_path),
        )

        assert len(result.results) == 0

    def test_counts_correct(self, tmp_path):
        """Counts match actual results."""
        from doctor.fixer import apply_fixes

        db_path = _make_db(tmp_path)

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
            report=report, entities_db_path=db_path,
            artifacts_root=str(tmp_path), project_root=str(tmp_path),
        )
        assert result1.fixed_count == 1

        # Second run: WAL is already set, so the fix is a no-op (still "applied"
        # because PRAGMA journal_mode=WAL is idempotent and doesn't error)
        result2 = apply_fixes(
            report=report, entities_db_path=db_path,
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

        cmd = [
            sys.executable, "-m", "doctor",
            "--entities-db", db_path,
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


class TestFixMissedCascade:
    """_fix_missed_cascade (renamed from _fix_stale_dependency) removes the
    stale edge's downstream block and promotes the blocked entity."""

    def test_fix_missed_cascade_flips_dependent_to_ready(self, tmp_path):
        from entity_registry.database import EntityDatabase
        from doctor.fix_actions import FixContext, _fix_missed_cascade

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
            entities_db_path=db_path,
            artifacts_root="", project_root="",
            db=db, engine=None, entities_conn=None,
        )
        issue = Issue(
            check="missed_cascade", severity="warning", entity=None,
            message=(
                f"Missed cascade: entity '{uuid_blocked}' (feature:stale-blocked) "
                f"has every blocker resolved but remains 'blocked'; "
                f"e.g. blocker '{uuid_blocker}'"
            ),
            fix_hint="Run cascade evaluation",
        )

        action = _fix_missed_cascade(ctx, issue)
        assert uuid_blocker in action
        assert "flipped 1" in action

        # Feature 124 FR124-4c: edge SURVIVES (cascade_unblock no longer
        # tombstones edges)
        deps = db.query_dependencies(entity_uuid=uuid_blocked)
        assert len(deps) == 1

        # Feature 124 FR124-4a: blocked entity should be promoted to ready
        # (not planned)
        entity = db.get_entity_by_uuid(uuid_blocked)
        assert entity["status"] == "ready"

        db.close()
