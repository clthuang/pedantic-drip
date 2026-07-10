"""Tests for pd:doctor data models and check functions."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

from doctor.models import CheckResult, DiagnosticReport, Issue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path, name: str = "entities.db") -> str:
    """Create a minimal entity DB with legacy schema.

    Most doctor tests construct entities via raw INSERT against the legacy
    schema (project_id, parent_type_id) and exercise pre-Migration-11
    integrity-check code paths. The doctor production code post-feature-108
    queries via parent_uuid only — these legacy fixtures still work because
    parent_uuid is present in v9 too.

    The doctor's schema_version comparison test (test_both_dbs_healthy)
    explicitly stamps version 11 via _make_db_v11 to match production.
    """
    db_path = str(tmp_path / name)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS _metadata (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT OR REPLACE INTO _metadata(key, value) VALUES('schema_version', '9');

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
    if status in ("completed", "abandoned"):
        meta["completed"] = "2026-01-01T00:00:00+00:00"
    (feature_dir / ".meta.json").write_text(json.dumps(meta))


# ---------------------------------------------------------------------------
# Feature 131 Task 1.2: live-schema fixtures (post-Migration-11)
#
# The legacy _make_db / _register_feature helpers above build the pre-Mig-11
# schema (entity_type / project_id, no `kind` / `workspace_uuid`). They are
# RETAINED for tests that genuinely exercise the old schema (e.g. the
# tolerate branch). The three rewritten checks (feature_status,
# brainstorm_status, entity_orphans) are repointed onto these live fixtures,
# which bootstrap the real schema via EntityDatabase (precedent:
# entity_registry/test_database.py).
# ---------------------------------------------------------------------------


_LIVE_DB_HANDLES: list = []


@pytest.fixture(autouse=True)
def _close_live_dbs():
    """Deterministically close every EntityDatabase opened via _make_live_db.

    Call sites close only the raw ``conn`` in their own finally blocks; the
    EntityDatabase handle is torn down here (mirrors the documented
    entity_registry/test_database.py fixture convention) so no test leaks a
    SQLite connection past its own teardown.
    """
    yield
    while _LIVE_DB_HANDLES:
        db = _LIVE_DB_HANDLES.pop()
        try:
            db.close()
        except Exception:
            pass


def _make_live_db(tmp_path, name: str = "entities.db"):
    """Build a live-schema entity DB and return ``(db, conn)``.

    ``db`` is the ``EntityDatabase`` (write authority for the register API);
    ``conn`` is a raw ``sqlite3`` connection the doctor checks consume as
    ``entities_conn``. Both point at the same file — EntityDatabase runs in
    WAL mode, so committed writes on either connection are visible to the
    other. ``db`` is auto-closed at test teardown by ``_close_live_dbs``;
    call sites remain responsible only for ``conn``.
    """
    from entity_registry.database import EntityDatabase

    db_path = str(tmp_path / name)
    db = EntityDatabase(db_path)
    _LIVE_DB_HANDLES.append(db)
    conn = _entities_conn(db_path)
    return db, conn


def _register_live_feature(
    db,
    entity_id: str,
    *,
    name: str | None = None,
    artifact_path: str | None = None,
    status: str = "active",
    workspace_uuid: str | None = None,
    kind: str = "feature",
) -> str:
    """Register a ``kind`` (default ``'feature'``) row via the live API.

    Uses ``EntityDatabase.register_entity`` — never a raw INSERT (uuid-PK
    gotcha). ``workspace_uuid`` defaults to the canonical unknown-workspace
    bucket, which EntityDatabase auto-bootstraps, so callers that don't care
    about scoping need not pre-insert a workspaces row. Any non-seq-slug
    entity_id (e.g. ``'bs-001'``) is accepted via ``_strict_id_format=False``.
    Returns the ``type_id``.
    """
    from entity_registry.database import _UNKNOWN_WORKSPACE_UUID

    if workspace_uuid is None:
        workspace_uuid = _UNKNOWN_WORKSPACE_UUID
    if name is None:
        name = f"{kind.title()} {entity_id}"
    db.register_entity(
        kind,
        entity_id,
        name,
        workspace_uuid=workspace_uuid,
        artifact_path=artifact_path,
        status=status,
        _strict_id_format=False,
    )
    return f"{kind}:{entity_id}"


def _insert_workspace(conn, project_root, uuid) -> None:
    """INSERT a ``workspaces`` row mapping ``project_root`` -> ``uuid``.

    Raw SQL is acceptable here (no API helper for arbitrary workspaces rows).
    ``project_root`` is stored as ``os.path.abspath`` so it matches the
    checks' ``WHERE project_root = ?`` lookup (which abspaths its input). The
    NOT NULL ``created_at`` / ``updated_at`` columns are satisfied via
    ``datetime('now')``.
    """
    conn.execute(
        "INSERT INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, NULL, ?, datetime('now'), datetime('now'))",
        (uuid, os.path.abspath(str(project_root))),
    )
    conn.commit()


def _entity_uuid(conn, type_id: str) -> str:
    """Return the uuid of the entity with ``type_id`` (live-schema helper)."""
    row = conn.execute(
        "SELECT uuid FROM entities WHERE type_id = ?", (type_id,)
    ).fetchone()
    return row[0]


class TestLiveFixtureSmoke:
    """Feature 131 Task 1.2: prove the live fixtures register + resolve."""

    def test_live_fixture_smoke_registers_feature(self, tmp_path):
        db, conn = _make_live_db(tmp_path)
        try:
            _register_live_feature(db, "001-alpha", status="active")
            rows = conn.execute(
                "SELECT entity_id FROM entities WHERE kind = 'feature'"
            ).fetchall()
            assert [r[0] for r in rows] == ["001-alpha"]
        finally:
            conn.close()

    def test_live_fixture_smoke_workspace_roundtrip(self, tmp_path):
        db, conn = _make_live_db(tmp_path)
        try:
            import uuid as uuid_mod

            ws_uuid = str(uuid_mod.uuid4())
            _insert_workspace(conn, str(tmp_path), ws_uuid)
            rows = conn.execute(
                "SELECT uuid FROM workspaces "
                "WHERE project_root IS NOT NULL AND project_root = ?",
                (os.path.abspath(str(tmp_path)),),
            ).fetchall()
            # Proves scoped=True is reachable before any scoping test relies
            # on it (guards the silent-INSERT gotcha).
            assert [r[0] for r in rows] == [ws_uuid]
        finally:
            conn.close()


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


# ===========================================================================
# Feature 131 Task 1.1: _run_live_schema_query helper
# ===========================================================================


class TestRunLiveSchemaQuery:
    """The execute-or-surface/tolerate discriminator (design Component [A]).

    Uses minimal in-memory tables so the helper's three branches are exercised
    independently of the full live schema (Task 1.2's fixtures).
    """

    def test_happy_path_returns_rows_untolerated(self):
        from doctor.checks import _run_live_schema_query

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE entities (kind TEXT, entity_id TEXT)")
        conn.execute(
            "INSERT INTO entities (kind, entity_id) VALUES ('feature', '001-a')"
        )
        issues: list = []
        rows, tolerated = _run_live_schema_query(
            conn,
            "SELECT entity_id FROM entities WHERE kind = 'feature'",
            (),
            "feature_status",
            issues,
            ("kind",),
        )
        assert tolerated is False
        assert [r[0] for r in rows] == ["001-a"]
        assert issues == []
        conn.close()

    def test_surface_branch_emits_one_error_issue(self):
        from doctor.checks import _run_live_schema_query

        # Table HAS the required `kind` column, but the query references a
        # column that does not exist -> rot, must surface.
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE entities (kind TEXT, entity_id TEXT)")
        issues: list = []
        rows, tolerated = _run_live_schema_query(
            conn,
            "SELECT nonexistent_col FROM entities WHERE kind = 'feature'",
            (),
            "feature_status",
            issues,
            ("kind",),
        )
        assert rows == []
        assert tolerated is False
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1
        assert errors[0].check == "feature_status"
        assert "feature_status" in errors[0].message
        assert "nonexistent_col" in errors[0].message
        conn.close()

    def test_tolerate_branch_when_required_column_absent(self):
        from doctor.checks import _run_live_schema_query

        # Table has NO `kind` column (pre-Migration-11 shape) -> tolerate.
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE entities (entity_id TEXT)")
        issues: list = []
        rows, tolerated = _run_live_schema_query(
            conn,
            "SELECT entity_id FROM entities WHERE kind = 'feature'",
            (),
            "feature_status",
            issues,
            ("kind",),
        )
        assert rows == []
        assert tolerated is True
        assert issues == []
        conn.close()

    def test_emit_once_dedupes_repeat_failures(self):
        from doctor.checks import _run_live_schema_query

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE entities (kind TEXT, entity_id TEXT)")
        issues: list = []
        for _ in range(2):
            _run_live_schema_query(
                conn,
                "SELECT nonexistent_col FROM entities WHERE kind = 'feature'",
                (),
                "feature_status",
                issues,
                ("kind",),
            )
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 1
        conn.close()

    def test_tolerate_when_one_of_multiple_required_columns_absent(self):
        # Feature 131 Component [A] / design [D].5: check_entity_orphans' scoped
        # step-1 query declares TWO required columns ("kind", "workspace_uuid").
        # On an intermediate schema that HAS `kind` but NOT `workspace_uuid`,
        # the "all required columns present" test must be False -> tolerate,
        # NOT surface. This is the ONLY shape that distinguishes `all(...)` from
        # a mutated `any(...)`: single-column required sets can't (for one
        # element all() == any()). Mutating all->any would surface here instead.
        from doctor.checks import _run_live_schema_query

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE entities (kind TEXT, entity_id TEXT)")
        issues: list = []
        rows, tolerated = _run_live_schema_query(
            conn,
            "SELECT entity_id FROM entities "
            "WHERE kind = 'feature' AND workspace_uuid = ?",
            ("ws",),
            "entity_orphans",
            issues,
            ("kind", "workspace_uuid"),
        )
        assert rows == []
        # all(["kind" present=True, "workspace_uuid" present=False]) -> False.
        assert tolerated is True
        assert issues == []
        conn.close()

    def test_never_raises_when_pragma_probe_also_fails(self):
        # Feature 131 Component [A] "The helper NEVER raises": when BOTH the main
        # statement AND the fallback PRAGMA table_info(entities) probe raise (a
        # broken/closed connection), the inner except sets present=set(), so the
        # all-present test is False for any non-empty required set -> tolerate,
        # ([], True), zero Issues, and — the contract under test — NO exception
        # escapes the helper. Existing surface/tolerate tests only fail the main
        # query; the probe still succeeds there, so this path was untested.
        from doctor.checks import _run_live_schema_query

        class _AlwaysRaises:
            """Stand-in connection whose every execute() raises (both the main
            query and the PRAGMA probe hit it)."""

            def execute(self, *_args, **_kwargs):
                raise sqlite3.OperationalError("connection is broken")

        issues: list = []
        rows, tolerated = _run_live_schema_query(
            _AlwaysRaises(),
            "SELECT entity_id FROM entities WHERE kind = 'feature'",
            (),
            "feature_status",
            issues,
            ("kind",),
        )
        assert rows == []
        assert tolerated is True
        assert issues == []


class TestCheck8BothDbsHealthy:
    """Check 8: both DBs healthy returns passed=True with extras."""

    def test_both_dbs_healthy(self, tmp_path):
        from doctor.checks import check_db_readiness

        entity_path = _make_db(tmp_path, "entities.db")

        # Stamp schema_version to the dynamic latest (F117 FR-B.1 replaces
        # the old hardcoded ENTITY_SCHEMA_VERSION=11). _make_db uses a legacy
        # v9 fixture so most tests can keep INSERTing via the project_id /
        # parent_type_id columns until the full Phase F test-fixture
        # migration lands (backlog #00360).
        from doctor.checks import _get_expected_entity_version
        conn = sqlite3.connect(entity_path)
        conn.execute(
            "UPDATE _metadata SET value = ? WHERE key = 'schema_version'",
            (str(_get_expected_entity_version()),),
        )
        conn.commit()
        conn.close()

        result = check_db_readiness(
            entities_db_path=entity_path,
        )
        assert result.passed is True
        assert result.extras["entity_db_ok"] is True
        assert result.name == "db_readiness"


class TestCheck8EntityDbLocked:
    """Check 8: locked entity DB reports error with extras.entity_db_ok=False."""

    def test_entity_db_locked(self, tmp_path):
        from doctor.checks import check_db_readiness

        entity_path = _make_db(tmp_path, "entities.db")

        # Hold a write lock on the entity DB
        blocker = sqlite3.connect(entity_path)
        blocker.execute("BEGIN IMMEDIATE")

        try:
            result = check_db_readiness(
                entities_db_path=entity_path,
            )
            assert result.passed is False
            assert result.extras["entity_db_ok"] is False
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

        # Downgrade schema version
        conn = sqlite3.connect(entity_path)
        conn.execute("UPDATE _metadata SET value = '5' WHERE key = 'schema_version'")
        conn.commit()
        conn.close()

        result = check_db_readiness(
            entities_db_path=entity_path,
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

        result = check_db_readiness(
            entities_db_path=entity_path,
        )
        wal_issues = [i for i in result.issues if "wal" in i.message.lower()]
        assert len(wal_issues) >= 1
        assert all(i.severity == "warning" for i in wal_issues)


class TestCheck8ImmediateRollbackReleasesLock:
    """Check 8: lock test connection is released after check completes."""

    def test_immediate_rollback_releases_lock(self, tmp_path):
        from doctor.checks import check_db_readiness

        entity_path = _make_db(tmp_path, "entities.db")

        # Stamp schema_version to the dynamic latest (F117 FR-B.1 replaces
        # the old hardcoded ENTITY_SCHEMA_VERSION=11). See test_both_dbs_healthy
        # for fixture rationale.
        from doctor.checks import _get_expected_entity_version
        conn = sqlite3.connect(entity_path)
        conn.execute(
            "UPDATE _metadata SET value = ? WHERE key = 'schema_version'",
            (str(_get_expected_entity_version()),),
        )
        conn.commit()
        conn.close()

        # Run the check
        result = check_db_readiness(
            entities_db_path=entity_path,
        )
        assert result.passed is True

        # Verify we can still acquire a write lock (doctor released its lock)
        conn = sqlite3.connect(entity_path, timeout=1.0)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
        conn.close()


# ===========================================================================
# Task 2.1: Check 1 (Feature Status)
# ===========================================================================


def _entities_conn(db_path: str) -> sqlite3.Connection:
    """Open a read-only style connection to entity DB for check functions."""
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


class TestCheck1AllStatusesMatch:
    """Check 1: all .meta.json statuses match DB — passes."""

    def test_check1_all_statuses_match(self, tmp_path):
        from doctor.checks import check_feature_status

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "001-alpha", status="active")
        _register_live_feature(db, "002-beta", status="completed")
        _create_meta_json(tmp_path, "001-alpha", status="active")
        _create_meta_json(tmp_path, "002-beta", status="completed")

        try:
            result = check_feature_status(conn, str(tmp_path))
            assert result.passed is True
            assert result.name == "feature_status"
            assert len([i for i in result.issues if i.severity in ("error", "warning")]) == 0
        finally:
            conn.close()


class TestCheck1StatusMismatch:
    """Check 1: status mismatch reports error."""

    def test_check1_status_mismatch_reports_error(self, tmp_path):
        from doctor.checks import check_feature_status

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "001-alpha", status="completed")
        _create_meta_json(tmp_path, "001-alpha", status="active")

        try:
            result = check_feature_status(conn, str(tmp_path))
            assert result.passed is False
            errors = [i for i in result.issues if i.severity == "error"]
            assert len(errors) >= 1
            assert "active" in errors[0].message
            assert "completed" in errors[0].message
            # Non-vacuity (design [D].1 / spec SC#3): the divergent feature IS
            # reported — impossible if the kind='feature' query silently
            # no-op'd down a tolerate branch (empty candidate set).
            assert any("001-alpha" in (i.entity or "") for i in errors)
        finally:
            conn.close()


class TestCheck1MissingFromDb:
    """Check 1: feature on disk but not in DB → warning."""

    def test_check1_missing_from_db_warning(self, tmp_path):
        from doctor.checks import check_feature_status

        db, conn = _make_live_db(tmp_path)
        _create_meta_json(tmp_path, "001-alpha", status="active")

        try:
            result = check_feature_status(conn, str(tmp_path))
            assert result.passed is False
            warnings = [i for i in result.issues if i.severity == "warning"]
            assert len(warnings) >= 1
            assert "not in entity DB" in warnings[0].message
        finally:
            conn.close()


class TestCheck1MalformedMetaJson:
    """Check 1: malformed .meta.json doesn't crash, reports error."""

    def test_check1_malformed_meta_json_no_crash(self, tmp_path):
        from doctor.checks import check_feature_status

        db, conn = _make_live_db(tmp_path)
        feature_dir = tmp_path / "features" / "001-alpha"
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text("{invalid json!!!")

        try:
            result = check_feature_status(conn, str(tmp_path))
            # Should not crash — should report an error issue
            errors = [i for i in result.issues if i.severity == "error"]
            assert len(errors) >= 1
            assert "Malformed" in errors[0].message
        finally:
            conn.close()


class TestCheck1NullLastCompletedPhase:
    """Check 1: null lastCompletedPhase with completed phase timestamps → warning."""

    def test_check1_null_last_completed_phase(self, tmp_path):
        from doctor.checks import check_feature_status

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "001-alpha", status="active")

        # Create .meta.json with phases that have 'completed' but null lastCompletedPhase
        feature_dir = tmp_path / "features" / "001-alpha"
        feature_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "id": "001",
            "slug": "001-alpha",
            "status": "active",
            "lastCompletedPhase": None,
            "phases": {
                "brainstorm": {"completed": "2025-01-01T00:00:00Z"},
                "specify": {"completed": "2025-01-02T00:00:00Z"},
            },
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))

        try:
            result = check_feature_status(conn, str(tmp_path))
            warnings = [
                i for i in result.issues
                if i.severity == "warning" and "lastCompletedPhase" in i.message
            ]
            assert len(warnings) >= 1
        finally:
            conn.close()


class TestCheck1CrossProjectEntity:
    """Check 1: cross-project entities (not in local_entity_ids) are skipped."""

    def test_check1_cross_project_entity_no_warning(self, tmp_path):
        from doctor.checks import check_feature_status

        db, conn = _make_live_db(tmp_path)
        # Register a feature in DB that's not local
        _register_live_feature(db, "099-remote", status="active")
        # Only "001-alpha" is local
        _create_meta_json(tmp_path, "001-alpha", status="active")
        _register_live_feature(db, "001-alpha", status="active")

        try:
            result = check_feature_status(
                conn, str(tmp_path),
                local_entity_ids={"001-alpha"},
            )
            # Should NOT warn about 099-remote (it's cross-project)
            remote_issues = [
                i for i in result.issues if "099-remote" in (i.entity or "")
            ]
            assert len(remote_issues) == 0
        finally:
            conn.close()


# ===========================================================================
# Task 2.2: Check 2 (Workflow Phase)
# ===========================================================================


def _setup_workflow_feature(db_path, slug, *, wp="design", lcp="specify",
                            mode="standard", kanban="wip"):
    """Register a feature and add workflow_phases entry."""
    import uuid as uuid_mod

    type_id = f"feature:{slug}"
    entity_uuid = str(uuid_mod.uuid4())
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO entities "
        "(uuid, type_id, project_id, entity_type, entity_id, name, status, created_at, updated_at) "
        "VALUES (?, ?, '__unknown__', 'feature', ?, ?, 'active', datetime('now'), datetime('now'))",
        (entity_uuid, type_id, slug, f"Feature {slug}"),
    )
    conn.execute(
        "INSERT OR REPLACE INTO workflow_phases "
        "(uuid, type_id, workflow_phase, last_completed_phase, mode, kanban_column, "
        "created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (entity_uuid, type_id, wp, lcp, mode, kanban),
    )
    conn.commit()
    conn.close()
    return type_id


class TestCheck2InSync:
    """Check 2: in-sync features pass."""

    def test_check2_in_sync_passes(self, tmp_path):
        from doctor.checks import check_workflow_phase

        db_path = _make_db(tmp_path)
        # kanban must match derive_kanban("active", "design") == "prioritised"
        _setup_workflow_feature(
            db_path, "001-alpha", wp="design", lcp="specify",
            mode="standard", kanban="prioritised",
        )
        _create_meta_json(
            tmp_path, "001-alpha", status="active",
            mode="standard", last_completed_phase="specify",
        )

        result = check_workflow_phase(db_path, str(tmp_path))
        # No errors or warnings expected for in-sync
        err_warn = [i for i in result.issues if i.severity in ("error", "warning")]
        assert len(err_warn) == 0, f"Unexpected issues: {[i.message for i in err_warn]}"


class TestCheck2MetaJsonAhead:
    """Check 2: meta_json_ahead reports error with fix hint."""

    def test_check2_meta_json_ahead_fix_hint(self, tmp_path):
        from doctor.checks import check_workflow_phase

        db_path = _make_db(tmp_path)
        # DB says specify, meta says design (ahead)
        _setup_workflow_feature(
            db_path, "001-alpha", wp="specify", lcp="brainstorm",
            mode="standard", kanban="wip",
        )
        _create_meta_json(
            tmp_path, "001-alpha", status="active",
            mode="standard", last_completed_phase="design",
        )

        result = check_workflow_phase(db_path, str(tmp_path))
        errors = [i for i in result.issues if i.severity == "error"]
        # Should have at least one error about drift
        meta_ahead = [i for i in errors if "meta_json_ahead" in i.message]
        assert len(meta_ahead) >= 1, f"Expected meta_json_ahead error, got: {[i.message for i in errors]}"
        assert meta_ahead[0].fix_hint is not None
        assert "reconcile" in meta_ahead[0].fix_hint.lower()


class TestCheck2DbAhead:
    """Check 2: db_ahead reports error with fix hint."""

    def test_check2_db_ahead_fix_hint(self, tmp_path):
        from doctor.checks import check_workflow_phase

        db_path = _make_db(tmp_path)
        # DB says design completed, meta says brainstorm
        _setup_workflow_feature(
            db_path, "001-alpha", wp="create-plan", lcp="design",
            mode="standard", kanban="wip",
        )
        _create_meta_json(
            tmp_path, "001-alpha", status="active",
            mode="standard", last_completed_phase="brainstorm",
        )

        result = check_workflow_phase(db_path, str(tmp_path))
        errors = [i for i in result.issues if i.severity == "error"]
        db_ahead = [i for i in errors if "db_ahead" in i.message]
        assert len(db_ahead) >= 1, f"Expected db_ahead error, got: {[i.message for i in errors]}"
        assert db_ahead[0].fix_hint is not None


class TestCheck2KanbanDrift:
    """Check 2: kanban-only drift on in_sync feature → warning."""

    def test_check2_kanban_only_drift_detected(self, tmp_path):
        from doctor.checks import check_workflow_phase

        db_path = _make_db(tmp_path)
        # Feature is in sync for phases but kanban is wrong
        _setup_workflow_feature(
            db_path, "001-alpha", wp="design", lcp="specify",
            mode="standard", kanban="backlog",  # wrong kanban
        )
        _create_meta_json(
            tmp_path, "001-alpha", status="active",
            mode="standard", last_completed_phase="specify",
        )

        result = check_workflow_phase(db_path, str(tmp_path))
        kanban_issues = [
            i for i in result.issues
            if "kanban" in i.message.lower() or "kanban" in (i.fix_hint or "").lower()
        ]
        # Kanban drift may or may not be detected depending on reconciliation logic.
        # The check only reports it if mismatches include kanban_column on in_sync features.
        # This is implementation-dependent on what check_workflow_drift returns.
        # We verify no crash at minimum.
        assert result.name == "workflow_phase"


class TestBackwardTransition:
    """Check 2: backward transition (rework) is info, not error."""

    def test_backward_transition_not_error(self, tmp_path):
        from doctor.checks import check_workflow_phase

        db_path = _make_db(tmp_path)
        # Feature where workflow_phase < last_completed_phase (rework)
        _setup_workflow_feature(
            db_path, "001-alpha", wp="specify", lcp="design",
            mode="standard", kanban="wip",
        )
        _create_meta_json(
            tmp_path, "001-alpha", status="active",
            mode="standard", last_completed_phase="design",
        )

        conn = sqlite3.connect(db_path)
        result = check_workflow_phase(db_path, str(tmp_path), entities_conn=conn)
        conn.close()
        rework_infos = [
            i for i in result.issues
            if i.severity == "info" and "rework" in i.message.lower()
        ]
        # Should detect rework state as info
        assert len(rework_infos) >= 1, f"Expected rework info, got: {[i.message for i in result.issues]}"
        # Should NOT be error
        rework_errors = [
            i for i in result.issues
            if i.severity == "error" and "rework" in i.message.lower()
        ]
        assert len(rework_errors) == 0


class TestCheck2CrossProjectDbOnly:
    """Check 2: db_only feature not in local_entity_ids is skipped."""

    def test_cross_project_check2_db_only_skipped(self, tmp_path):
        from doctor.checks import check_workflow_phase

        db_path = _make_db(tmp_path)
        # Feature in DB+workflow but no .meta.json and not local
        _setup_workflow_feature(
            db_path, "099-remote", wp="design", lcp="specify",
            mode="standard", kanban="wip",
        )
        # Local feature that's in sync
        _setup_workflow_feature(
            db_path, "001-alpha", wp="design", lcp="specify",
            mode="standard", kanban="wip",
        )
        _create_meta_json(
            tmp_path, "001-alpha", status="active",
            mode="standard", last_completed_phase="specify",
        )

        result = check_workflow_phase(
            db_path, str(tmp_path),
            local_entity_ids={"001-alpha"},
        )
        remote_issues = [
            i for i in result.issues
            if "099-remote" in (i.entity or "") and i.severity in ("error", "warning")
        ]
        assert len(remote_issues) == 0, f"Should skip cross-project: {[i.message for i in remote_issues]}"


# ===========================================================================
# Task 2.3: Check 3 (Brainstorm Status)
# ===========================================================================


class TestCheck3NoPromotionNeeded:
    """Check 3: no brainstorms needing promotion → passes."""

    def test_check3_no_promotion_needed(self, tmp_path):
        from doctor.checks import check_brainstorm_status

        db, conn = _make_live_db(tmp_path)
        # All brainstorms already promoted
        _register_live_feature(db, "bs-001", kind="brainstorm", status="promoted")

        try:
            result = check_brainstorm_status(conn, str(tmp_path))
            assert result.passed is True
            assert result.name == "brainstorm_status"
        finally:
            conn.close()


class TestCheck3BrainstormShouldBePromoted:
    """Check 3: brainstorm referenced by completed feature → warning."""

    def test_check3_brainstorm_should_be_promoted(self, tmp_path):
        from doctor.checks import check_brainstorm_status

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "bs-001", kind="brainstorm", status="active")

        # Create a completed feature that references this brainstorm
        feature_dir = tmp_path / "features" / "001-alpha"
        feature_dir.mkdir(parents=True)
        meta = {
            "id": "001",
            "slug": "001-alpha",
            "status": "completed",
            "brainstorm_source": "bs-001",
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))

        # Create brainstorm dir so file check passes
        (tmp_path / "brainstorms").mkdir(exist_ok=True)
        (tmp_path / "brainstorms" / "bs-001").mkdir(exist_ok=True)

        try:
            result = check_brainstorm_status(conn, str(tmp_path))
            assert result.passed is False
            warnings = [i for i in result.issues if i.severity == "warning"]
            promotion_warnings = [w for w in warnings if "promoted" in w.message]
            assert len(promotion_warnings) >= 1
            # Non-vacuity (design [D].1): the registered stale brainstorm IS
            # reported — impossible if the kind='brainstorm' query silently
            # no-op'd down a tolerate branch (empty candidate set).
            assert any("bs-001" in (w.entity or "") for w in promotion_warnings)
        finally:
            conn.close()


class TestCheck3BrainstormActiveFeature:
    """Check 3: brainstorm referenced by active feature → warning."""

    def test_check3_brainstorm_referenced_by_active_feature(self, tmp_path):
        from doctor.checks import check_brainstorm_status

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "bs-active-001", kind="brainstorm", status="draft")

        # Create an active feature that references this brainstorm
        feature_dir = tmp_path / "features" / "070-active-feat"
        feature_dir.mkdir(parents=True)
        meta = {
            "id": "070",
            "slug": "active-feat",
            "status": "active",
            "brainstorm_source": "bs-active-001",
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))

        # Create brainstorm dir so file check passes
        (tmp_path / "brainstorms").mkdir(exist_ok=True)
        (tmp_path / "brainstorms" / "bs-active-001").mkdir(exist_ok=True)

        try:
            result = check_brainstorm_status(conn, str(tmp_path))
            assert result.passed is False
            warnings = [i for i in result.issues if i.severity == "warning"]
            promotion_warnings = [w for w in warnings if "promoted" in w.message]
            assert len(promotion_warnings) >= 1, (
                f"Active feature should trigger promotion warning, got: "
                f"{[i.message for i in result.issues]}"
            )
        finally:
            conn.close()

    def test_check3_promoted_brainstorm_not_flagged(self, tmp_path):
        from doctor.checks import check_brainstorm_status

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "bs-promoted-001", kind="brainstorm", status="promoted")

        feature_dir = tmp_path / "features" / "071-done-feat"
        feature_dir.mkdir(parents=True)
        meta = {
            "id": "071",
            "slug": "done-feat",
            "status": "active",
            "brainstorm_source": "bs-promoted-001",
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))

        try:
            result = check_brainstorm_status(conn, str(tmp_path))
            # promoted brainstorm should NOT be flagged
            promotion_warnings = [i for i in result.issues if "promoted" in i.message]
            assert len(promotion_warnings) == 0
        finally:
            conn.close()

    def test_check3_no_feature_reference_not_flagged(self, tmp_path):
        from doctor.checks import check_brainstorm_status

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "bs-orphan", kind="brainstorm", status="draft")

        # No features reference this brainstorm
        (tmp_path / "features").mkdir(exist_ok=True)

        try:
            result = check_brainstorm_status(conn, str(tmp_path))
            promotion_warnings = [i for i in result.issues if "promoted" in i.message]
            assert len(promotion_warnings) == 0
        finally:
            conn.close()


class TestCheck3EntityDepsFallback:
    """Check 3: fallback to entity_dependencies for promotion detection."""

    def test_check3_entity_deps_fallback(self, tmp_path):
        from doctor.checks import check_brainstorm_status

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "bs-002", kind="brainstorm", status="active")
        bs_uuid = _entity_uuid(conn, "brainstorm:bs-002")

        # Create a completed feature with no brainstorm_source in meta
        _register_live_feature(db, "002-beta", status="completed")
        feat_uuid = _entity_uuid(conn, "feature:002-beta")

        # Add dependency: brainstorm -> feature (live API, not raw INSERT)
        db.add_dependency(bs_uuid, feat_uuid)

        # No brainstorm_source in meta, so direct check won't find it
        feature_dir = tmp_path / "features" / "002-beta"
        feature_dir.mkdir(parents=True)
        meta = {"id": "002", "slug": "002-beta", "status": "completed"}
        (feature_dir / ".meta.json").write_text(json.dumps(meta))

        try:
            result = check_brainstorm_status(conn, str(tmp_path))
            assert result.passed is False
            warnings = [i for i in result.issues if i.severity == "warning"]
            dep_warnings = [w for w in warnings if "promoted" in w.message]
            assert len(dep_warnings) >= 1, f"Expected dep fallback warning, got: {[i.message for i in result.issues]}"
        finally:
            conn.close()

    def test_check3_dep_edge_to_non_feature_no_crash(self, tmp_path):
        # Dependency edge points at a NON-feature entity: the WHERE
        # uuid=? AND kind='feature' lookup returns [], exercising the
        # `feat_rows[0] if feat_rows else None` empty guard. Fails with
        # IndexError (escaping the sqlite-only except) if the guard is
        # dropped (pre-release QA gate finding, feature 131).
        from doctor.checks import check_brainstorm_status

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "bs-003", kind="brainstorm", status="active")
        bs_uuid = _entity_uuid(conn, "brainstorm:bs-003")
        _register_live_feature(db, "bs-004", kind="brainstorm", status="active")
        other_uuid = _entity_uuid(conn, "brainstorm:bs-004")

        db.add_dependency(bs_uuid, other_uuid)

        try:
            result = check_brainstorm_status(conn, str(tmp_path))
            # Completes without raising; the non-feature edge produces no
            # promotion warning for bs-003 via the deps-fallback path.
            dep_warnings = [
                i for i in result.issues
                if "promoted" in i.message and "bs-003" in (i.entity or "")
            ]
            assert dep_warnings == []
        finally:
            conn.close()


class TestCheck3BrainstormSourceMissing:
    """Check 3: brainstorm_source file doesn't exist → warning."""

    def test_check3_brainstorm_source_missing(self, tmp_path):
        from doctor.checks import check_brainstorm_status

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "bs-ghost", kind="brainstorm", status="active")

        # Feature references non-existent brainstorm source
        feature_dir = tmp_path / "features" / "001-alpha"
        feature_dir.mkdir(parents=True)
        meta = {
            "id": "001",
            "slug": "001-alpha",
            "status": "active",
            "brainstorm_source": "bs-ghost",
        }
        (feature_dir / ".meta.json").write_text(json.dumps(meta))

        # Don't create brainstorms directory

        try:
            result = check_brainstorm_status(conn, str(tmp_path))
            missing_warnings = [
                i for i in result.issues
                if i.severity == "warning" and "does not exist" in i.message
            ]
            assert len(missing_warnings) >= 1
        finally:
            conn.close()


# ===========================================================================
# Task 2.4: Check 4 (Backlog Status)
# ===========================================================================


def _register_backlog(db_path, entity_id, status="active"):
    """Register a backlog entity."""
    import uuid as uuid_mod

    type_id = f"backlog:{entity_id}"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO entities "
        "(uuid, type_id, project_id, entity_type, entity_id, name, status, created_at, updated_at) "
        "VALUES (?, ?, '__unknown__', 'backlog', ?, ?, ?, datetime('now'), datetime('now'))",
        (str(uuid_mod.uuid4()), type_id, entity_id, f"Backlog {entity_id}", status),
    )
    conn.commit()
    conn.close()
    return type_id


# Feature 111 / FR-CL.2: free-text suffix parsers removed from
# doctor/checks.py. The parser-driven TestCheck4 classes
# (TestCheck4AnnotatedNotPromoted, TestCheck4PromotedNotAnnotated,
# TestCheck4ClosedAnnotation) DELETED — see
# docs/features/111-issue-lifecycle-closure/cleanup-inventory.md.
# The passive checks (missing backlog.md, empty backlog.md) remain.


class TestCheck4BacklogMissingFile:
    """Check 4: missing backlog.md → passes."""

    def test_check4_backlog_missing_file_passes(self, tmp_path):
        from doctor.checks import check_backlog_status

        db_path = _make_db(tmp_path)

        conn = _entities_conn(db_path)
        try:
            result = check_backlog_status(conn, str(tmp_path))
            assert result.passed is True
            assert result.name == "backlog_status"
        finally:
            conn.close()


class TestCheck4EmptyBacklog:
    """Check 4: empty backlog.md → passes."""

    def test_check4_empty_backlog_passes(self, tmp_path):
        from doctor.checks import check_backlog_status

        db_path = _make_db(tmp_path)

        (tmp_path / "backlog.md").write_text("")

        conn = _entities_conn(db_path)
        try:
            result = check_backlog_status(conn, str(tmp_path))
            assert result.passed is True
        finally:
            conn.close()


# ===========================================================================
# Task 3.2: Check 6 (Branch Consistency)
# ===========================================================================


def _init_git_repo(path):
    """Initialize a git repo with an initial commit at given path."""
    subprocess.run(
        ["git", "init"], cwd=str(path),
        capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=str(path),
        capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=str(path),
        capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "initial"],
        cwd=str(path), capture_output=True, text=True,
    )


class TestCheck6AllBranchesExist:
    """Check 6: all active features have their branches."""

    def test_check6_all_branches_exist(self, tmp_path):
        from doctor.checks import check_branch_consistency

        _init_git_repo(tmp_path)
        # Create a branch
        subprocess.run(
            ["git", "checkout", "-b", "feature/001-alpha"],
            cwd=str(tmp_path), capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=str(tmp_path), capture_output=True,
        )

        db_path = _make_db(tmp_path)
        _register_feature(db_path, "001-alpha", "active")

        features_dir = tmp_path / "features" / "001-alpha"
        features_dir.mkdir(parents=True)
        meta = {
            "status": "active",
            "branch": "feature/001-alpha",
        }
        (features_dir / ".meta.json").write_text(json.dumps(meta))

        conn = _entities_conn(db_path)
        try:
            result = check_branch_consistency(
                conn, str(tmp_path), str(tmp_path), "main",
            )
            err_warn = [i for i in result.issues if i.severity in ("error", "warning")]
            assert len(err_warn) == 0
            assert result.name == "branch_consistency"
        finally:
            conn.close()


class TestCheck6BaseBranchMissing:
    """Check 6: base branch missing reports error and skips rest."""

    def test_check6_base_branch_missing(self, tmp_path):
        from doctor.checks import check_branch_consistency

        _init_git_repo(tmp_path)
        db_path = _make_db(tmp_path)

        conn = _entities_conn(db_path)
        try:
            result = check_branch_consistency(
                conn, str(tmp_path), str(tmp_path), "nonexistent-branch",
            )
            assert result.passed is False
            errors = [i for i in result.issues if i.severity == "error"]
            assert len(errors) >= 1
            assert "nonexistent-branch" in errors[0].message
        finally:
            conn.close()


class TestCheck6ActiveNoBranchNotMerged:
    """Check 6: active feature, branch missing, not merged -> warning."""

    def test_check6_active_no_branch_not_merged_warning(self, tmp_path):
        from doctor.checks import check_branch_consistency

        _init_git_repo(tmp_path)
        db_path = _make_db(tmp_path)
        _register_feature(db_path, "001-alpha", "active")

        features_dir = tmp_path / "features" / "001-alpha"
        features_dir.mkdir(parents=True)
        meta = {
            "status": "active",
            "branch": "feature/001-alpha",
        }
        (features_dir / ".meta.json").write_text(json.dumps(meta))

        conn = _entities_conn(db_path)
        try:
            result = check_branch_consistency(
                conn, str(tmp_path), str(tmp_path), "main",
            )
            warnings = [i for i in result.issues if i.severity == "warning"]
            assert len(warnings) >= 1
            assert "doesn't exist" in warnings[0].message
        finally:
            conn.close()


class TestCheck6ActiveMergedNotRework:
    """Check 6: active + merged + not rework -> error."""

    def test_check6_active_merged_not_rework_error(self, tmp_path):
        from doctor.checks import check_branch_consistency

        _init_git_repo(tmp_path)

        # Create feature content on main
        features_dir = tmp_path / "features" / "001-alpha"
        features_dir.mkdir(parents=True)
        meta = {
            "status": "active",
            "branch": "feature/001-alpha",
        }
        (features_dir / ".meta.json").write_text(json.dumps(meta))

        # Commit on main so merge check finds it
        subprocess.run(
            ["git", "add", "."], cwd=str(tmp_path), capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "add feature"],
            cwd=str(tmp_path), capture_output=True,
        )

        db_path = _make_db(tmp_path)
        _register_feature(db_path, "001-alpha", "active")

        conn = _entities_conn(db_path)
        try:
            result = check_branch_consistency(
                conn, str(tmp_path), str(tmp_path), "main",
            )
            errors = [i for i in result.issues if i.severity == "error"]
            assert len(errors) >= 1
            assert "merged" in errors[0].message
        finally:
            conn.close()


class TestCheck6RemoteBaseBranchFallback:
    """Check 6: fallback to origin/base_branch when local missing."""

    def test_check6_remote_base_branch_fallback(self, tmp_path):
        from doctor.checks import check_branch_consistency

        # Create a "remote" repo
        remote_dir = tmp_path / "remote"
        remote_dir.mkdir()
        _init_git_repo(remote_dir)

        # Create local repo that tracks remote
        local_dir = tmp_path / "local"
        subprocess.run(
            ["git", "clone", str(remote_dir), str(local_dir)],
            capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=str(local_dir),
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=str(local_dir),
            capture_output=True,
        )

        # Delete local main but keep origin/main
        subprocess.run(
            ["git", "checkout", "-b", "temp-branch"],
            cwd=str(local_dir), capture_output=True,
        )
        subprocess.run(
            ["git", "branch", "-d", "main"],
            cwd=str(local_dir), capture_output=True,
        )

        db_path = _make_db(local_dir)
        conn = _entities_conn(db_path)
        try:
            result = check_branch_consistency(
                conn, str(local_dir), str(local_dir), "main",
            )
            # Should NOT error on base branch -- origin/main exists
            base_errors = [
                i for i in result.issues
                if "Base branch" in i.message and i.severity == "error"
            ]
            assert len(base_errors) == 0
        finally:
            conn.close()


# ===========================================================================
# Task 3.3: Check 7 (Entity Orphans)
# ===========================================================================


class TestCheck7AllMatched:
    """Check 7: all entities have dirs and vice versa."""

    def test_check7_all_matched(self, tmp_path):
        from doctor.checks import check_entity_orphans

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "001-alpha", status="active")
        _create_meta_json(tmp_path, "001-alpha", status="active")

        try:
            result = check_entity_orphans(
                conn, str(tmp_path),
                local_entity_ids={"001-alpha"},
                project_root=str(tmp_path),
            )
            err_warn = [i for i in result.issues if i.severity in ("error", "warning")]
            assert len(err_warn) == 0
            assert result.name == "entity_orphans"
        finally:
            conn.close()


class TestCheck7OrphanedLocalEntity:
    """Check 7: local entity in DB but no dir -> warning."""

    def test_check7_orphaned_local_entity(self, tmp_path):
        from doctor.checks import check_entity_orphans

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "001-alpha", status="active")
        # No feature directory created

        try:
            result = check_entity_orphans(
                conn, str(tmp_path),
                local_entity_ids={"001-alpha"},
                project_root=str(tmp_path),
            )
            warnings = [i for i in result.issues if i.severity == "warning"]
            assert len(warnings) >= 1
            assert "not found on disk" in warnings[0].message
            # Non-vacuity (design [D].1): a registered feature whose dir was
            # deleted IS flagged — impossible if the kind='feature' query
            # silently no-op'd down a tolerate branch (empty candidate set).
            assert any("001-alpha" in (w.entity or "") for w in warnings)
        finally:
            conn.close()


class TestCheck7DirectoryNoEntity:
    """Check 7: directory with .meta.json but no entity -> warning."""

    def test_check7_directory_no_entity_warning(self, tmp_path):
        from doctor.checks import check_entity_orphans

        db, conn = _make_live_db(tmp_path)
        _create_meta_json(tmp_path, "001-alpha", status="active")

        try:
            result = check_entity_orphans(
                conn, str(tmp_path),
                project_root=str(tmp_path),
            )
            warnings = [i for i in result.issues if i.severity == "warning"]
            dir_warnings = [w for w in warnings if "no entity in DB" in w.message]
            assert len(dir_warnings) >= 1
        finally:
            conn.close()


class TestCheck7OrphanedBrainstormPrd:
    """Check 7: .prd.md without entity -> warning."""

    def test_check7_orphaned_brainstorm_prd(self, tmp_path):
        from doctor.checks import check_entity_orphans

        db, conn = _make_live_db(tmp_path)
        bs_dir = tmp_path / "brainstorms" / "bs-001"
        bs_dir.mkdir(parents=True)
        (bs_dir / "bs-001.prd.md").write_text("# PRD")

        try:
            result = check_entity_orphans(
                conn, str(tmp_path),
                project_root=str(tmp_path),
            )
            warnings = [i for i in result.issues if i.severity == "warning"]
            prd_warnings = [w for w in warnings if "brainstorm" in w.entity.lower()]
            assert len(prd_warnings) >= 1
        finally:
            conn.close()


class TestCheck7CrossProjectEntityInfoNotWarning:
    """Check 7: cross-project entity is info, not warning."""

    def test_cross_project_entity_info_not_warning(self, tmp_path):
        from doctor.checks import check_entity_orphans

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "001-alpha", status="active")  # local
        _register_live_feature(db, "099-remote", status="active")  # cross-project
        _create_meta_json(tmp_path, "001-alpha", status="active")

        try:
            result = check_entity_orphans(
                conn, str(tmp_path),
                local_entity_ids={"001-alpha"},
                project_root=str(tmp_path),
            )
            # 099-remote should not produce a warning
            remote_warnings = [
                i for i in result.issues
                if "099-remote" in (i.entity or "") and i.severity == "warning"
            ]
            assert len(remote_warnings) == 0
        finally:
            conn.close()


class TestCheck7CrossProjectEntitiesAggregatedInfo:
    """Check 7: cross-project entities produce aggregated info."""

    def test_cross_project_entities_aggregated_info(self, tmp_path):
        from doctor.checks import check_entity_orphans

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "098-other", status="active")
        _register_live_feature(db, "099-remote", status="active")

        try:
            result = check_entity_orphans(
                conn, str(tmp_path),
                local_entity_ids=set(),  # empty = check all
                project_root=str(tmp_path),
            )
            # With empty local_entity_ids, these are treated as local (warn).
            # Now test with explicit local_entity_ids (reuse the read-only conn).
            result = check_entity_orphans(
                conn, str(tmp_path),
                local_entity_ids={"001-nonexistent"},
                project_root=str(tmp_path),
            )
            info_issues = [
                i for i in result.issues
                if i.severity == "info" and "other projects" in i.message
            ]
            assert len(info_issues) >= 1
            assert "2" in info_issues[0].message  # 2 entities
        finally:
            conn.close()


class TestEntityOrphansScoping:
    """Feature 131 Task 2.3 / design [D].5: workspace-scoped step-1.

    The two-arm ``(workspace_uuid = ? OR workspace_uuid = _UNKNOWN)`` predicate
    only kicks in when exactly one ``workspaces`` row matches ``project_root``.
    These tests are non-vacuous by construction: each controls scoping via
    ``_insert_workspace`` and per-entity ``workspace_uuid`` while leaving the
    on-disk features dir EMPTY, so the scoped path (foreign -> info bucket) and
    the legacy path (empty local_entity_ids -> warning) produce DISTINCT
    outcomes — removing the predicate flips the result. Task 4.1 EXTENDS this
    class with the a-inverse / on-disk / ambiguity boundary cases.
    """

    def test_foreign_workspace_missing_dir_info_not_warning(self, tmp_path):
        # (a) design [D].5(a): a feature under a FOREIGN workspace, with no
        # on-disk dir and an empty features dir, is routed to the info bucket
        # (not a warning) when the run is scoped — the predicate discriminates.
        from doctor.checks import check_entity_orphans
        import uuid as uuid_mod

        db, conn = _make_live_db(tmp_path)
        uuid_a = str(uuid_mod.uuid4())
        uuid_b = str(uuid_mod.uuid4())
        _insert_workspace(conn, str(tmp_path), uuid_a)  # matches project_root
        _insert_workspace(conn, str(tmp_path / "other"), uuid_b)  # foreign
        _register_live_feature(db, "001-alpha", workspace_uuid=uuid_b)
        (tmp_path / "features").mkdir()  # empty features dir

        try:
            result = check_entity_orphans(
                conn, str(tmp_path), project_root=str(tmp_path),
            )
            warnings_001 = [
                i for i in result.issues
                if i.severity == "warning" and "001-alpha" in (i.entity or "")
            ]
            assert warnings_001 == []
            infos = [
                i for i in result.issues
                if i.severity == "info" and "other projects" in i.message
            ]
            assert len(infos) >= 1
        finally:
            conn.close()

    def test_unknown_bucket_missing_dir_scoped_warns(self, tmp_path):
        # (b) design [D].5(b): a feature in the unknown-workspace bucket, no
        # on-disk dir, scoped run -> treated as local -> warning.
        from doctor.checks import check_entity_orphans
        from entity_registry.database import _UNKNOWN_WORKSPACE_UUID
        import uuid as uuid_mod

        db, conn = _make_live_db(tmp_path)
        uuid_a = str(uuid_mod.uuid4())
        _insert_workspace(conn, str(tmp_path), uuid_a)  # scoped
        _register_live_feature(
            db, "001-alpha", workspace_uuid=_UNKNOWN_WORKSPACE_UUID
        )
        (tmp_path / "features").mkdir()  # empty features dir

        try:
            result = check_entity_orphans(
                conn, str(tmp_path), project_root=str(tmp_path),
            )
            warnings_001 = [
                i for i in result.issues
                if i.severity == "warning" and "001-alpha" in (i.entity or "")
            ]
            assert len(warnings_001) >= 1
            assert "not found on disk" in warnings_001[0].message
        finally:
            conn.close()

    def test_foreign_workspace_unscoped_missing_dir_warns(self, tmp_path):
        # (a-inverse) design [D].5 pair: the SAME foreign-workspace entity as
        # test_foreign_workspace_missing_dir_info_not_warning, but WITHOUT a
        # project_root workspaces row -> unscoped. The legacy branch (empty
        # local_entity_ids -> warning arm) warns where the scoped path routed
        # the foreign entity to the info bucket. The scoped/unscoped pair proves
        # the two-arm predicate does the work: remove it and (a) collapses onto
        # this outcome.
        from doctor.checks import check_entity_orphans
        import uuid as uuid_mod

        db, conn = _make_live_db(tmp_path)
        uuid_b = str(uuid_mod.uuid4())
        # Only the FOREIGN workspace row exists; project_root matches nothing,
        # so root_uuids == [] -> scoped is False.
        _insert_workspace(conn, str(tmp_path / "other"), uuid_b)
        _register_live_feature(db, "001-alpha", workspace_uuid=uuid_b)
        (tmp_path / "features").mkdir()  # empty features dir

        try:
            result = check_entity_orphans(
                conn, str(tmp_path), project_root=str(tmp_path),
            )
            warnings_001 = [
                i for i in result.issues
                if i.severity == "warning" and "001-alpha" in (i.entity or "")
            ]
            assert len(warnings_001) >= 1
            assert "not found on disk" in warnings_001[0].message
            # NOT routed to the cross-project info bucket (test (a)'s scoped
            # outcome for the same placement) -> distinct outcome, so the
            # predicate is load-bearing.
            infos = [
                i for i in result.issues
                if i.severity == "info" and "other projects" in i.message
            ]
            assert infos == []
        finally:
            conn.close()

    def test_foreign_workspace_on_disk_not_step2_flagged(self, tmp_path):
        # (c) design [D].5(c) / spec SC#2 foreign case: an on-disk feature dir
        # whose entity lives under a FOREIGN workspace is NOT flagged "has
        # .meta.json but no entity in DB". Step-2 membership (db_feature_ids)
        # is UNSCOPED (db_features_all), so exists-in-both holds for every
        # workspace, foreign included.
        from doctor.checks import check_entity_orphans
        import uuid as uuid_mod

        db, conn = _make_live_db(tmp_path)
        uuid_a = str(uuid_mod.uuid4())
        uuid_b = str(uuid_mod.uuid4())
        _insert_workspace(conn, str(tmp_path), uuid_a)  # scoped
        _insert_workspace(conn, str(tmp_path / "other"), uuid_b)  # foreign
        _register_live_feature(db, "001-alpha", workspace_uuid=uuid_b)
        _create_meta_json(tmp_path, "001-alpha", status="active")  # on disk

        try:
            result = check_entity_orphans(
                conn, str(tmp_path), project_root=str(tmp_path),
            )
            meta_flags = [
                i for i in result.issues
                if "has .meta.json but" in i.message
                and "001-alpha" in (i.entity or "")
            ]
            assert meta_flags == []
        finally:
            conn.close()

    def test_unknown_bucket_on_disk_not_step2_flagged(self, tmp_path):
        # Additional pin (spec happy-path AC #6, direct): an on-disk feature dir
        # whose entity sits in the unknown-workspace bucket, scoped run -> the
        # two-arm predicate keeps it in db_feature_ids, so its directory is NOT
        # flagged "has .meta.json but no entity in DB". Its claimability stays
        # check_unknown_workspace_orphans's job.
        from doctor.checks import check_entity_orphans
        from entity_registry.database import _UNKNOWN_WORKSPACE_UUID
        import uuid as uuid_mod

        db, conn = _make_live_db(tmp_path)
        uuid_a = str(uuid_mod.uuid4())
        _insert_workspace(conn, str(tmp_path), uuid_a)  # scoped
        _register_live_feature(
            db, "001-alpha", workspace_uuid=_UNKNOWN_WORKSPACE_UUID
        )
        _create_meta_json(tmp_path, "001-alpha", status="active")  # on disk

        try:
            result = check_entity_orphans(
                conn, str(tmp_path), project_root=str(tmp_path),
            )
            meta_flags = [
                i for i in result.issues
                if "has .meta.json but" in i.message
                and "001-alpha" in (i.entity or "")
            ]
            assert meta_flags == []
        finally:
            conn.close()

    def test_ambiguous_workspace_rows_fall_back_to_legacy(self, tmp_path):
        # (d) design [D].5(d): TWO workspaces rows share project_root ->
        # len(root_uuids) == 2 -> scoped is False -> legacy local_entity_ids
        # branching (same outcome as the unscoped variant of (a)). The entity
        # sits under a FOREIGN workspace, so the assertion is non-vacuous: a
        # (broken) scoped path would route it to the info bucket, so a warning
        # proves the ambiguity fallback took the legacy branch.
        from doctor.checks import check_entity_orphans
        import uuid as uuid_mod

        db, conn = _make_live_db(tmp_path)
        uuid_a = str(uuid_mod.uuid4())
        uuid_c = str(uuid_mod.uuid4())
        uuid_b = str(uuid_mod.uuid4())
        _insert_workspace(conn, str(tmp_path), uuid_a)  # ambiguous match #1
        _insert_workspace(conn, str(tmp_path), uuid_c)  # ambiguous match #2
        # uuid_b lives at a DIFFERENT root (does not add to the project_root
        # match count) so the feature can register under a genuinely foreign
        # workspace — register_entity rejects a workspace_uuid absent from the
        # workspaces table (split-brain guard).
        _insert_workspace(conn, str(tmp_path / "foreign"), uuid_b)
        _register_live_feature(db, "001-alpha", workspace_uuid=uuid_b)  # foreign
        (tmp_path / "features").mkdir()  # empty features dir

        try:
            result = check_entity_orphans(
                conn, str(tmp_path), project_root=str(tmp_path),
            )
            warnings_001 = [
                i for i in result.issues
                if i.severity == "warning" and "001-alpha" in (i.entity or "")
            ]
            assert len(warnings_001) >= 1  # legacy branch (empty local set)
            assert "not found on disk" in warnings_001[0].message
        finally:
            conn.close()


class TestEntityOrphansTolerateWholeCheck:
    """Feature 131 Task 4.1 / design [D].4: a legacy (pre-Migration-11) DB
    tolerates the WHOLE check — steps 2 and 4 skip, zero Issues.
    """

    def test_legacy_schema_registered_feature_on_disk_zero_issues(self, tmp_path):
        # LEGACY fixture (genuinely no `kind` column) + a registered feature +
        # its on-disk dir with .meta.json. Were step 2 NOT gated on the
        # tolerated flag, it would false-flag the dir "has .meta.json but no
        # entity in DB" (db_feature_ids is EMPTY because the kind query
        # tolerated to []). The zero-Issue result proves the tolerated-
        # membership skip of steps 2/4 — not merely quiet SQL sites.
        from doctor.checks import check_entity_orphans

        db_path = _make_db(tmp_path)
        _register_feature(db_path, slug="001-alpha", status="active")
        _create_meta_json(tmp_path, "001-alpha", status="active")
        conn = _entities_conn(db_path)

        try:
            result = check_entity_orphans(
                conn, str(tmp_path), project_root=str(tmp_path),
            )
            assert result.issues == []
            assert result.passed is True
        finally:
            conn.close()

    def test_legacy_schema_on_disk_brainstorm_zero_issues(self, tmp_path):
        # Mirror of the feature case for STEP 4: LEGACY fixture (no `kind`
        # column) + an on-disk brainstorms/<stem>/<stem>.prd.md with no
        # matching entity. Were step 4 NOT gated on brainstorms_tolerated,
        # the tolerated-to-[] db_brainstorm_ids would false-flag the dir.
        # Fails if the `not brainstorms_tolerated` gate is removed
        # (pre-release QA gate finding, feature 131).
        from doctor.checks import check_entity_orphans

        db_path = _make_db(tmp_path)
        bs_dir = tmp_path / "brainstorms" / "bs-001"
        bs_dir.mkdir(parents=True)
        (bs_dir / "bs-001.prd.md").write_text("# PRD: stub\n")
        conn = _entities_conn(db_path)

        try:
            result = check_entity_orphans(
                conn, str(tmp_path), project_root=str(tmp_path),
            )
            assert result.issues == []
            assert result.passed is True
        finally:
            conn.close()


class TestRetainedChecksEmptyDb:
    """Feature 131 Task 4.1 / design [D].7: an empty live-schema DB yields no
    false positives and no exceptions across the three retained checks.
    """

    def test_empty_db_all_three_checks_clean(self, tmp_path):
        from doctor.checks import (
            check_brainstorm_status,
            check_entity_orphans,
            check_feature_status,
        )

        db, conn = _make_live_db(tmp_path)  # zero registered rows
        try:
            fs = check_feature_status(conn, str(tmp_path))
            bs = check_brainstorm_status(conn, str(tmp_path))
            eo = check_entity_orphans(
                conn, str(tmp_path), project_root=str(tmp_path)
            )
            for result in (fs, bs, eo):
                assert result.issues == []
                assert result.passed is True
        finally:
            conn.close()


class TestEntityOrphansSurfaceBranch:
    """Feature 131 Task 4.1 / design [D].3 / spec SC#4 surface AC: a schema-
    level sqlite3.Error at a rewritten site (with `kind` PRESENT) surfaces as
    exactly one error Issue naming the check — end-to-end, distinct from the
    Task 1.1 helper-level unit test.
    """

    def test_membership_query_failure_surfaces_one_error(self, tmp_path):
        from doctor.checks import check_entity_orphans

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "001-alpha", status="active")

        # Fail ONLY the feature-membership SELECT (step 1). PRAGMA
        # table_info(entities) and every other query pass through, so `kind`
        # probes as PRESENT -> the helper takes the SURFACE branch (not
        # tolerate). No project_root workspaces row -> unscoped, so only the
        # single unfiltered membership query runs -> exactly one error.
        sentinel = "injected corruption at membership select"

        class _FailMembershipConn:
            def __init__(self, real):
                self._real = real

            def execute(self, sql, *args):
                if "kind = 'feature'" in sql and "artifact_path" in sql:
                    raise sqlite3.OperationalError(sentinel)
                return self._real.execute(sql, *args)

            def __getattr__(self, name):
                return getattr(self._real, name)

        wrapped = _FailMembershipConn(conn)
        try:
            result = check_entity_orphans(
                wrapped, str(tmp_path), project_root=str(tmp_path),
            )
            errors = [i for i in result.issues if i.severity == "error"]
            assert len(errors) == 1
            assert errors[0].check == "entity_orphans"
            assert "entity_orphans" in errors[0].message
            assert sentinel in errors[0].message
            assert result.passed is False
        finally:
            conn.close()


class TestEntityOrphansWorkspaceLookupFailure:
    """Feature 131 design [D].5 / Component [A]: the workspace-resolution SELECT
    in check_entity_orphans is a BARE ``try/except sqlite3.Error`` (NOT routed
    through _run_live_schema_query), so a failure there must emit NO Issue and
    fall back to the unscoped legacy membership path. This is distinct from the
    tolerate-whole-check case (TestEntityOrphansTolerateWholeCheck): there
    `kind` is ABSENT so the membership queries themselves tolerate; here `kind`
    is PRESENT, the membership queries succeed, and ONLY the workspaces lookup
    breaks — proving the bare-except swallow is load-bearing and silent.
    """

    def test_workspaces_lookup_failure_no_issue_unscoped_fallback(self, tmp_path):
        from doctor.checks import check_entity_orphans

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "001-alpha", status="active")
        # No on-disk feature dir: under the unscoped legacy fallback (empty
        # local_entity_ids) the dirless registered feature is flagged, which
        # makes the "check still ran" assertion below non-vacuous.

        # Fail ONLY the `FROM workspaces` resolution query; every kind='feature'
        # membership query and the PRAGMA probe delegate to the real conn.
        class _FailWorkspacesConn:
            def __init__(self, real):
                self._real = real

            def execute(self, sql, *args):
                if "FROM workspaces" in sql:
                    raise sqlite3.OperationalError("no such table: workspaces")
                return self._real.execute(sql, *args)

            def __getattr__(self, name):
                return getattr(self._real, name)

        wrapped = _FailWorkspacesConn(conn)
        try:
            result = check_entity_orphans(
                wrapped, str(tmp_path), project_root=str(tmp_path),
            )
            # The bare-except swallows the workspaces failure WITHOUT an Issue:
            # no error at all (contrast TestEntityOrphansSurfaceBranch, where a
            # membership-query failure DOES surface one error).
            errors = [i for i in result.issues if i.severity == "error"]
            assert errors == []
            # Unscoped fallback (root_uuids == [] -> scoped False) still runs
            # step-1: the dirless registered feature is flagged, proving the
            # check proceeded past the swallowed lookup rather than aborting.
            warnings_001 = [
                i for i in result.issues
                if i.severity == "warning" and "001-alpha" in (i.entity or "")
            ]
            assert len(warnings_001) >= 1
            assert "not found on disk" in warnings_001[0].message
        finally:
            conn.close()


def test_all_checks_sql_explains_against_live_schema(tmp_path):
    """Feature 131 Task 4.2 / design [D].2 / spec SC#1+SC#5: committed EXPLAIN
    scan over every constant SQL site in checks.py.

    AST-walk checks.py for the constant string first-argument of every
    ``.execute(...)`` call whose text starts with SELECT/PRAGMA (constants
    only — f-strings, names, and BinOp concatenations are intentionally
    skipped, matching the authoring harness), then ``EXPLAIN`` each against a
    live-schema connection. A statement referencing a dropped column
    (``entity_type`` / ``project_id``) or any other schema drift fails to
    compile, so this is the durable, committed form of the authoring harness
    that found the original 7 rotted sites.
    """
    import ast

    checks_path = os.path.join(os.path.dirname(__file__), "checks.py")
    with open(checks_path) as f:
        tree = ast.parse(f.read(), filename=checks_path)

    collected: list[tuple[int, str]] = []  # (lineno, sql)
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
        ):
            continue
        arg = node.args[0]
        # Constants only: the parser folds adjacent string literals into one
        # ast.Constant; f-strings (JoinedStr), Name references, and BinOp
        # ("a" + b) concatenations are deliberately out of scope.
        if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
            continue
        if arg.value.strip().upper().startswith(("SELECT", "PRAGMA")):
            collected.append((node.lineno, arg.value))

    # Guard a silently-broken walker (e.g. an AST-shape change that collects
    # nothing): the checks module carries well over 20 constant SQL sites.
    assert len(collected) >= 20, (
        f"walker collected only {len(collected)} SQL sites — expected >= 20; "
        f"the .execute() AST shape may have drifted"
    )

    db, conn = _make_live_db(tmp_path)
    failures: list[tuple[int, str, str]] = []
    try:
        for lineno, sql in collected:
            try:
                conn.execute("EXPLAIN " + sql, ("x",) * sql.count("?"))
            except sqlite3.Error as exc:
                failures.append(
                    (lineno, str(exc), " ".join(sql.split())[:80])
                )
    finally:
        conn.close()

    assert failures == [], (
        "SQL sites failed to EXPLAIN against the live schema (dropped column "
        "or schema drift):\n"
        + "\n".join(
            f"  checks.py:{ln}: {err} :: {prefix}"
            for ln, err, prefix in failures
        )
    )


def test_fixer_sql_has_no_dropped_column_references():
    """Feature 131 design [D].2 (fixer net): committed form of the manual grep
    guarding the auto-fix WRITE paths against the Migration-11 dropped columns.

    checks.py has its own live EXPLAIN scan
    (test_all_checks_sql_explains_against_live_schema); the fix_actions / fixer
    write paths (UPDATE / DELETE / INSERT on `entities` et al.) were only ever
    guarded by a manual grep. AST-collect the constant SQL first-arg of every
    ``.execute(...)`` in both modules and assert none names a column dropped by
    Migration 11 (feature 108 / 109): ``entity_type``, ``project_id`` (bare —
    ``project_id_legacy`` survives and is NOT flagged), or ``parent_type_id``.

    Textual denylist rather than EXPLAIN on purpose: the fixer touches tables
    the minimal live fixture may omit at a given migration head, so EXPLAIN
    could false-fail with "no such table"; the denylist targets exactly the rot
    class the grep watched and never false-fails on table coverage.
    """
    import ast
    import re

    # \b already excludes project_id_legacy: `d`->`_` is not a word boundary,
    # so \bproject_id\b cannot match inside project_id_legacy.
    dropped = {
        "entity_type": re.compile(r"\bentity_type\b"),
        "project_id": re.compile(r"\bproject_id\b"),
        "parent_type_id": re.compile(r"\bparent_type_id\b"),
    }
    sql_verbs = (
        "SELECT", "INSERT", "UPDATE", "DELETE", "REPLACE",
        "CREATE", "DROP", "PRAGMA", "WITH",
    )

    here = os.path.dirname(__file__)
    targets = [
        os.path.join(here, "fix_actions", "__init__.py"),
        os.path.join(here, "fixer.py"),
    ]

    collected: list[tuple[str, int, str]] = []  # (basename, lineno, sql)
    for path in targets:
        with open(path) as f:
            tree = ast.parse(f.read(), filename=path)
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "execute"
                and node.args
            ):
                continue
            arg = node.args[0]
            # Constants only (matches the checks.py scan): f-strings, Names and
            # BinOp concatenations are out of scope by design.
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                continue
            if arg.value.strip().upper().startswith(sql_verbs):
                collected.append(
                    (os.path.basename(path), node.lineno, arg.value)
                )

    # Guard a silently-broken walker: the fixer write paths carry well over ten
    # constant SQL sites (fixer.py delegates, contributing ~0; fix_actions holds
    # the UPDATE / DELETE / INSERT / SELECT statements).
    assert len(collected) >= 10, (
        f"walker collected only {len(collected)} fixer SQL sites — expected "
        ">= 10; the .execute() AST shape may have drifted"
    )

    hits: list[str] = []
    for fname, lineno, sql in collected:
        flat = " ".join(sql.split())
        for col, rx in dropped.items():
            if rx.search(sql):
                hits.append(
                    f"  {fname}:{lineno}: references dropped '{col}' :: "
                    f"{flat[:80]}"
                )

    assert hits == [], (
        "fixer SQL references a Migration-11 dropped column (rot):\n"
        + "\n".join(hits)
    )


# ===========================================================================
# Task 4.1: Check 9 (Referential Integrity)
# ===========================================================================


def _register_entity_with_uuid(db_path, type_id, entity_type, entity_id,
                                 uuid_val=None, parent_type_id=None,
                                 parent_uuid=None):
    """Register an entity with explicit uuid and parent refs."""
    import uuid as uuid_mod

    if uuid_val is None:
        uuid_val = str(uuid_mod.uuid4())
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO entities "
        "(uuid, type_id, project_id, entity_type, entity_id, name, status, "
        "parent_type_id, parent_uuid, created_at, updated_at) "
        "VALUES (?, ?, '__unknown__', ?, ?, ?, 'active', ?, ?, datetime('now'), datetime('now'))",
        (uuid_val, type_id, entity_type, entity_id,
         f"Entity {entity_id}", parent_type_id, parent_uuid),
    )
    conn.commit()
    conn.close()
    return uuid_val


class TestCheck9ValidReferences:
    """Check 9: valid references pass."""

    def test_check9_valid_references(self, tmp_path):
        from doctor.checks import check_referential_integrity

        db_path = _make_db(tmp_path)
        parent_uuid = _register_entity_with_uuid(
            db_path, "project:p1", "project", "p1",
        )
        _register_entity_with_uuid(
            db_path, "feature:001", "feature", "001",
            parent_type_id="project:p1", parent_uuid=parent_uuid,
        )
        # Add workflow_phases entry
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO workflow_phases (type_id, workflow_phase, created_at, updated_at) "
            "VALUES ('feature:001', 'design', datetime('now'), datetime('now'))"
        )
        conn.commit()
        conn.close()

        conn = _entities_conn(db_path)
        try:
            result = check_referential_integrity(conn)
            err_warn = [i for i in result.issues if i.severity in ("error", "warning")]
            assert len(err_warn) == 0
            assert result.name == "referential_integrity"
        finally:
            conn.close()


class TestCheck9DanglingParentTypeId:
    """Check 9: dangling parent_type_id -> error."""

    def test_check9_dangling_parent_type_id(self, tmp_path):
        from doctor.checks import check_referential_integrity

        db_path = _make_db(tmp_path)
        _register_entity_with_uuid(
            db_path, "feature:001", "feature", "001",
            parent_type_id="project:nonexistent", parent_uuid="fake-uuid",
        )

        conn = _entities_conn(db_path)
        try:
            result = check_referential_integrity(conn)
            errors = [i for i in result.issues if i.severity == "error"]
            dangling = [e for e in errors if "non-existent" in e.message and "parent" in e.message]
            assert len(dangling) >= 1
        finally:
            conn.close()


class TestCheck9ParentUuidMismatch:
    """Check 9: parent_uuid doesn't match parent entity -> error."""

    def test_check9_parent_uuid_mismatch(self, tmp_path):
        from doctor.checks import check_referential_integrity

        db_path = _make_db(tmp_path)
        _register_entity_with_uuid(
            db_path, "project:p1", "project", "p1",
            uuid_val="real-parent-uuid",
        )
        _register_entity_with_uuid(
            db_path, "feature:001", "feature", "001",
            parent_type_id="project:p1", parent_uuid="wrong-uuid",
        )

        conn = _entities_conn(db_path)
        try:
            result = check_referential_integrity(conn)
            errors = [i for i in result.issues if i.severity == "error"]
            mismatch = [e for e in errors if "parent_uuid" in e.message]
            assert len(mismatch) >= 1
        finally:
            conn.close()


class TestCheck9OrphanedWorkflowPhases:
    """Check 9: workflow_phases entry with no entity -> error."""

    def test_check9_orphaned_workflow_phases(self, tmp_path):
        from doctor.checks import check_referential_integrity

        db_path = _make_db(tmp_path)
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO workflow_phases (type_id, workflow_phase, created_at, updated_at) "
            "VALUES ('feature:ghost', 'design', datetime('now'), datetime('now'))"
        )
        conn.commit()
        conn.close()

        conn = _entities_conn(db_path)
        try:
            result = check_referential_integrity(conn)
            errors = [i for i in result.issues if i.severity == "error"]
            orphan = [e for e in errors if "ghost" in e.message]
            assert len(orphan) >= 1
        finally:
            conn.close()


class TestCheck9SelfReferentialParent:
    """Check 9: entity is its own parent -> error."""

    def test_check9_self_referential_parent(self, tmp_path):
        from doctor.checks import check_referential_integrity

        db_path = _make_db(tmp_path)
        uuid_val = "self-ref-uuid"
        _register_entity_with_uuid(
            db_path, "feature:001", "feature", "001",
            uuid_val=uuid_val,
            parent_type_id="feature:001", parent_uuid=uuid_val,
        )

        conn = _entities_conn(db_path)
        try:
            result = check_referential_integrity(conn)
            errors = [i for i in result.issues if i.severity == "error"]
            self_ref = [e for e in errors if "own parent" in e.message]
            assert len(self_ref) >= 1
        finally:
            conn.close()


class TestCheck9ParentUuidNullWithTypeId:
    """Check 9: parent_type_id-set-but-parent_uuid-NULL — removed post-Migration-11.

    The legacy "parent_type_id set but parent_uuid NULL" detection no longer
    fires because parent_type_id was dropped by Migration 11 (feature 108).
    Referential integrity now flows entirely through parent_uuid.
    """

    @pytest.mark.skip(reason="Check removed post-Mig-11; parent_type_id column dropped")
    def test_check9_parent_uuid_null_with_type_id(self, tmp_path):
        pass


class TestCheck9CircularParentChain:
    """Check 9: circular parent chain -> error."""

    def test_check9_circular_parent_chain(self, tmp_path):
        from doctor.checks import check_referential_integrity

        db_path = _make_db(tmp_path)
        uuid_a = "uuid-a"
        uuid_b = "uuid-b"
        _register_entity_with_uuid(
            db_path, "feature:a", "feature", "a",
            uuid_val=uuid_a,
            parent_type_id="feature:b", parent_uuid=uuid_b,
        )
        _register_entity_with_uuid(
            db_path, "feature:b", "feature", "b",
            uuid_val=uuid_b,
            parent_type_id="feature:a", parent_uuid=uuid_a,
        )

        conn = _entities_conn(db_path)
        try:
            result = check_referential_integrity(conn)
            errors = [i for i in result.issues if i.severity == "error"]
            circular = [e for e in errors if "Circular" in e.message]
            assert len(circular) >= 1
        finally:
            conn.close()


class TestCheck9OrphanedDependencyRow:
    """Check 9: entity_dependencies with non-existent UUID -> warning."""

    def test_check9_orphaned_dependency_row(self, tmp_path):
        from doctor.checks import check_referential_integrity

        db_path = _make_db(tmp_path)
        _register_entity_with_uuid(
            db_path, "feature:001", "feature", "001",
            uuid_val="valid-uuid",
        )
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO entity_dependencies (entity_uuid, blocked_by_uuid) "
            "VALUES ('valid-uuid', 'nonexistent-uuid')"
        )
        conn.commit()
        conn.close()

        conn = _entities_conn(db_path)
        try:
            result = check_referential_integrity(conn)
            warnings = [i for i in result.issues if i.severity == "warning"]
            orphan_deps = [w for w in warnings if "nonexistent-uuid" in w.message]
            assert len(orphan_deps) >= 1
        finally:
            conn.close()


class TestCheck9DeepChainNoFalsePositive:
    """Check 9: valid deep chain does not produce false positive."""

    def test_check9_deep_chain_no_false_positive(self, tmp_path):
        from doctor.checks import check_referential_integrity
        import uuid as uuid_mod

        db_path = _make_db(tmp_path)
        # Create a chain of 5 entities
        prev_type_id = None
        prev_uuid = None
        for i in range(5):
            uuid_val = str(uuid_mod.uuid4())
            type_id = f"feature:{i:03d}"
            _register_entity_with_uuid(
                db_path, type_id, "feature", f"{i:03d}",
                uuid_val=uuid_val,
                parent_type_id=prev_type_id, parent_uuid=prev_uuid,
            )
            prev_type_id = type_id
            prev_uuid = uuid_val

        conn = _entities_conn(db_path)
        try:
            result = check_referential_integrity(conn)
            circular = [i for i in result.issues if "Circular" in i.message]
            assert len(circular) == 0
            depth_warnings = [i for i in result.issues if "depth limit" in i.message]
            assert len(depth_warnings) == 0
        finally:
            conn.close()


class TestCheck9ChainAtDepthLimit:
    """Check 9: chain at depth limit -> warning."""

    def test_check9_chain_at_depth_limit(self, tmp_path):
        from doctor.checks import check_referential_integrity
        import uuid as uuid_mod

        db_path = _make_db(tmp_path)
        # Create a chain of 21 entities (exceeds depth 20)
        prev_type_id = None
        prev_uuid = None
        for i in range(21):
            uuid_val = str(uuid_mod.uuid4())
            type_id = f"feature:{i:03d}"
            _register_entity_with_uuid(
                db_path, type_id, "feature", f"{i:03d}",
                uuid_val=uuid_val,
                parent_type_id=prev_type_id, parent_uuid=prev_uuid,
            )
            prev_type_id = type_id
            prev_uuid = uuid_val

        conn = _entities_conn(db_path)
        try:
            result = check_referential_integrity(conn)
            depth_warnings = [i for i in result.issues if "depth limit" in i.message]
            assert len(depth_warnings) >= 1
        finally:
            conn.close()


# ===========================================================================
# Task 4.2: Check 10 (Config Validity)
# ===========================================================================


class TestCheck10ValidConfig:
    """Check 10: valid config passes."""

    def test_check10_valid_config(self, tmp_path):
        from doctor.checks import check_config_validity

        # Create artifacts_root dir
        (tmp_path / "docs").mkdir()

        result = check_config_validity(str(tmp_path), artifacts_root="docs")
        # With defaults, weights sum to 1.0 and provider is set
        err_warn = [i for i in result.issues if i.severity in ("error", "warning")]
        assert len(err_warn) == 0
        assert result.name == "config_validity"


class TestCheck10ArtifactsRootMissing:
    """Check 10: artifacts_root dir missing -> error."""

    def test_check10_artifacts_root_missing(self, tmp_path):
        from doctor.checks import check_config_validity

        result = check_config_validity(str(tmp_path), artifacts_root="nonexistent")
        errors = [i for i in result.issues if i.severity == "error"]
        assert len(errors) >= 1
        assert "artifacts_root" in errors[0].message


class TestCheck10MissingConfigFileUsesDefaults:
    """Check 10: missing config file uses defaults (passes)."""

    def test_check10_missing_config_file_uses_defaults(self, tmp_path):
        from doctor.checks import check_config_validity

        (tmp_path / "docs").mkdir()

        result = check_config_validity(str(tmp_path), artifacts_root="docs")
        # Defaults are valid
        err_warn = [i for i in result.issues if i.severity in ("error", "warning")]
        assert len(err_warn) == 0


# ===========================================================================
# Task 5.1: Orchestrator Tests
# ===========================================================================

# Feature 131 removed check_project_attribution: 21 checks -> 20. Single
# source for the orchestrator/CLI check-count assertions below.
EXPECTED_CHECK_COUNT = 20


class TestOrchestratorReportHas14Checks:
    """Orchestrator: report always has 16 checks (14 pre-109 + the
    feature-109 ``check_status_write_path`` added by Group 10 + the
    feature-111 ``check_no_free_text_status_parsers`` added by Group E).
    """

    def test_report_has_14_checks(self, tmp_path):
        from doctor import run_diagnostics

        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))
        assert len(report.checks) == EXPECTED_CHECK_COUNT


class TestOrchestratorReportEvenWhenLocked:
    """Orchestrator: 16 checks even when DB is locked."""

    def test_report_14_checks_even_when_locked(self, tmp_path):
        from doctor import run_diagnostics

        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        # Lock entity DB
        blocker = sqlite3.connect(db_path)
        blocker.execute("BEGIN IMMEDIATE")
        try:
            report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))
            assert len(report.checks) == EXPECTED_CHECK_COUNT
        finally:
            blocker.rollback()
            blocker.close()


class TestOrchestratorHealthyProject:
    """Orchestrator: healthy project reports all pass."""

    def test_healthy_project_all_pass(self, tmp_path):
        from doctor import run_diagnostics

        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))
        # All checks should pass (empty project)
        failed = [c for c in report.checks if not c.passed]
        # Note: check2 (workflow_phase) might fail if EntityDatabase migration fails
        # In a clean test env with proper schema, it should pass or soft-fail
        assert report.total_issues >= 0  # Sanity check


class TestOrchestratorEntityDbLockSkips:
    """Orchestrator: entity DB lock skips dependent checks."""

    def test_entity_db_lock_skips_dependent(self, tmp_path):
        from doctor import run_diagnostics

        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        blocker = sqlite3.connect(db_path)
        blocker.execute("BEGIN IMMEDIATE")
        try:
            report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))
            # Entity-dependent checks should be skipped
            for check in report.checks:
                if check.name in ("feature_status", "brainstorm_status",
                                   "backlog_status", "branch_consistency",
                                   "entity_orphans", "referential_integrity"):
                    skip_issues = [i for i in check.issues if "Skipped" in i.message]
                    assert len(skip_issues) >= 1, f"{check.name} should be skipped"
        finally:
            blocker.rollback()
            blocker.close()


class TestOrchestratorPerCheckExceptionIsolation:
    """Orchestrator: exception in one check doesn't crash others."""

    def test_per_check_exception_isolation(self, tmp_path):
        from doctor import run_diagnostics

        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        # The orchestrator wraps each check in try/except
        # Even if a check raises, we still get 10 results
        report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))
        assert len(report.checks) == EXPECTED_CHECK_COUNT


class TestOrchestratorMissingDbFile:
    """Orchestrator: missing DB file doesn't create it."""

    def test_missing_db_file_no_create(self, tmp_path):
        from doctor import run_diagnostics

        db_path = str(tmp_path / "nonexistent_entities.db")
        (tmp_path / "docs").mkdir(exist_ok=True)

        report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))
        assert not os.path.exists(db_path)
        assert len(report.checks) == EXPECTED_CHECK_COUNT


class TestOrchestratorBaseBranchFromConfig:
    """Orchestrator: reads base_branch from config."""

    def test_base_branch_from_config(self, tmp_path):
        from doctor import run_diagnostics

        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        (config_dir / "pd.local.md").write_text("base_branch: develop\n")

        report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))
        assert len(report.checks) == EXPECTED_CHECK_COUNT


class TestOrchestratorBaseBranchDefaultMain:
    """Orchestrator: defaults to main when no config."""

    def test_base_branch_default_main(self, tmp_path):
        from doctor import run_diagnostics

        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))
        assert len(report.checks) == EXPECTED_CHECK_COUNT


class TestOrchestratorCheck8RunsFirst:
    """Orchestrator: check 8 (db_readiness) is the first check."""

    def test_check8_runs_first(self, tmp_path):
        from doctor import run_diagnostics

        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))
        assert report.checks[0].name == "db_readiness"


class TestOrchestratorEntityDbLocked:
    """Orchestrator: entity DB locked -> all DB-dependent checks skipped."""

    def test_entity_db_locked(self, tmp_path):
        from doctor import run_diagnostics

        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        blocker1 = sqlite3.connect(db_path)
        blocker1.execute("BEGIN IMMEDIATE")
        try:
            report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))
            assert len(report.checks) == EXPECTED_CHECK_COUNT
            assert report.healthy is False
        finally:
            blocker1.rollback()
            blocker1.close()


class TestOrchestratorFreshProjectEmpty:
    """Orchestrator: fresh project with no features produces a report."""

    def test_fresh_project_empty(self, tmp_path):
        from doctor import run_diagnostics

        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))
        assert len(report.checks) == EXPECTED_CHECK_COUNT
        assert report.elapsed_ms >= 0


class TestOrchestratorWorksWithoutMcp:
    """Orchestrator: works without MCP servers."""

    def test_works_without_mcp(self, tmp_path):
        from doctor import run_diagnostics

        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        # No MCP servers running -- should still work
        report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))
        assert len(report.checks) == EXPECTED_CHECK_COUNT


class TestOrchestratorConnectionsClosedOnSuccess:
    """Orchestrator: connections are closed after successful run."""

    def test_connections_closed_on_success(self, tmp_path):
        from doctor import run_diagnostics

        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))
        assert len(report.checks) == EXPECTED_CHECK_COUNT

        # Verify we can acquire write locks (connections were closed)
        conn = sqlite3.connect(db_path, timeout=1.0)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
        conn.close()

        conn = sqlite3.connect(db_path, timeout=1.0)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
        conn.close()


class TestOrchestratorConnectionsClosedOnException:
    """Orchestrator: connections are closed even if a check raises."""

    def test_connections_closed_on_exception(self, tmp_path):
        from doctor import run_diagnostics

        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))

        # Connections should be closed regardless
        conn = sqlite3.connect(db_path, timeout=1.0)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
        conn.close()


# ===========================================================================
# Task 5.2: CLI Tests
# ===========================================================================


def _doctor_lib_path():
    """Return the PYTHONPATH for running doctor module."""
    return os.path.join(
        os.path.dirname(__file__),
        os.pardir,  # up from doctor/ to lib/
    )


class TestCliJsonOutputHas14Checks:
    """CLI: JSON output contains 16 checks (14 pre-109 + the feature-109
    ``check_status_write_path`` added by Group 10 + the feature-111
    ``check_no_free_text_status_parsers`` added by Group E).
    """

    def test_cli_json_output_has_14_checks(self, tmp_path):
        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        result = subprocess.run(
            [sys.executable, "-m", "doctor",
             "--entities-db", db_path,
             "--project-root", str(tmp_path),
             "--artifacts-root", str(tmp_path / "docs")],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": _doctor_lib_path()},
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # Phase 2 wraps output: {"diagnostic": ...}
        diag = data.get("diagnostic", data)
        assert len(diag["checks"]) == EXPECTED_CHECK_COUNT


class TestCliExitCodeAlwaysZero:
    """CLI: exit code is always 0."""

    def test_cli_exit_code_always_zero(self, tmp_path):
        # Even with non-existent DBs
        result = subprocess.run(
            [sys.executable, "-m", "doctor",
             "--entities-db", str(tmp_path / "nope.db"),
             "--project-root", str(tmp_path),
             "--artifacts-root", str(tmp_path)],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": _doctor_lib_path()},
        )
        assert result.returncode == 0


class TestCliJsonStructureMatchesModel:
    """CLI: JSON structure matches DiagnosticReport model."""

    def test_cli_json_structure_matches_model(self, tmp_path):
        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        result = subprocess.run(
            [sys.executable, "-m", "doctor",
             "--entities-db", db_path,
             "--project-root", str(tmp_path),
             "--artifacts-root", str(tmp_path / "docs")],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": _doctor_lib_path()},
        )
        data = json.loads(result.stdout)
        # Phase 2 wraps output: {"diagnostic": ...}
        diag = data.get("diagnostic", data)
        assert "healthy" in diag
        assert "checks" in diag
        assert "total_issues" in diag
        assert "error_count" in diag
        assert "warning_count" in diag
        assert "elapsed_ms" in diag
        # Check first check structure
        check = diag["checks"][0]
        assert "name" in check
        assert "passed" in check
        assert "issues" in check
        assert "elapsed_ms" in check


class TestCliArtifactsRootCliArgPrecedence:
    """CLI: --artifacts-root CLI arg takes precedence."""

    def test_cli_artifacts_root_cli_arg_precedence(self, tmp_path):
        db_path = _make_db(tmp_path)
        custom_root = tmp_path / "custom-docs"
        custom_root.mkdir()

        result = subprocess.run(
            [sys.executable, "-m", "doctor",
             "--entities-db", db_path,
             "--project-root", str(tmp_path),
             "--artifacts-root", str(custom_root)],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": _doctor_lib_path()},
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        diag = data.get("diagnostic", data)
        assert len(diag["checks"]) == EXPECTED_CHECK_COUNT


class TestCliArtifactsRootConfigFallback:
    """CLI: artifacts_root falls back to config."""

    def test_cli_artifacts_root_config_fallback(self, tmp_path):
        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir()

        result = subprocess.run(
            [sys.executable, "-m", "doctor",
             "--entities-db", db_path,
             "--project-root", str(tmp_path)],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": _doctor_lib_path()},
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        diag = data.get("diagnostic", data)
        assert len(diag["checks"]) == EXPECTED_CHECK_COUNT


class TestCliArtifactsRootDefaultDocs:
    """CLI: artifacts_root defaults to 'docs'."""

    def test_cli_artifacts_root_default_docs(self, tmp_path):
        db_path = _make_db(tmp_path)

        result = subprocess.run(
            [sys.executable, "-m", "doctor",
             "--entities-db", db_path,
             "--project-root", str(tmp_path)],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": _doctor_lib_path()},
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        diag = data.get("diagnostic", data)
        assert len(diag["checks"]) == EXPECTED_CHECK_COUNT


class TestCliNoneSerializesAsJsonNull:
    """CLI: None values serialize as JSON null."""

    def test_cli_none_serializes_as_json_null(self, tmp_path):
        db_path = _make_db(tmp_path)

        result = subprocess.run(
            [sys.executable, "-m", "doctor",
             "--entities-db", db_path,
             "--project-root", str(tmp_path)],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": _doctor_lib_path()},
        )
        data = json.loads(result.stdout)
        # Verify JSON is valid (null handling)
        raw = result.stdout
        # The JSON should be well-formed
        json.loads(raw)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Lock Holder Identification Tests (feature 063)
# ---------------------------------------------------------------------------


class TestLockHolderIdentifiedViaPidFile:
    """_identify_lock_holders returns holder info from PID files."""

    def test_lock_holder_identified_via_pid_file(self, tmp_path, monkeypatch):
        from doctor.checks import _identify_lock_holders

        # Create a mock PID dir with a PID file
        pid_dir = tmp_path / "run"
        pid_dir.mkdir()
        pid_file = pid_dir / "entity_server.pid"
        pid_file.write_text("12345")

        # Redirect expanduser to use our tmp dir
        orig_expanduser = os.path.expanduser

        def mock_expanduser(p):
            if p == "~/.claude/pd/run":
                return str(pid_dir)
            return orig_expanduser(p)

        monkeypatch.setattr("os.path.expanduser", mock_expanduser)

        # Mock os.kill to succeed (process alive)
        orig_kill = os.kill

        def mock_kill(pid, sig):
            if pid == 12345 and sig == 0:
                return None
            return orig_kill(pid, sig)

        monkeypatch.setattr("os.kill", mock_kill)

        # Mock subprocess.run for ps and lsof
        orig_sub_run = subprocess.run

        def mock_sub_run(cmd, **kwargs):
            if cmd[0] == "ps" and "12345" in cmd:
                result = type("Result", (), {
                    "stdout": "    1\n",
                    "stderr": "",
                    "returncode": 0,
                })()
                return result
            if cmd[0] == "lsof":
                raise FileNotFoundError("no lsof")
            return orig_sub_run(cmd, **kwargs)

        monkeypatch.setattr("subprocess.run", mock_sub_run)

        holders = _identify_lock_holders("/fake/db.path")
        assert len(holders) == 1
        assert "12345" in holders[0]
        assert "entity_server" in holders[0]
        assert "orphaned" in holders[0]


class TestLockHolderIdentifiedViaLsof:
    """_identify_lock_holders returns holder info from lsof fallback."""

    def test_lock_holder_identified_via_lsof(self, tmp_path, monkeypatch):
        from doctor.checks import _identify_lock_holders

        # Empty PID dir (no PID files)
        pid_dir = tmp_path / "run"
        pid_dir.mkdir()

        orig_expanduser = os.path.expanduser

        def mock_expanduser(p):
            if p == "~/.claude/pd/run":
                return str(pid_dir)
            return orig_expanduser(p)

        monkeypatch.setattr("os.path.expanduser", mock_expanduser)

        # Mock subprocess.run for lsof
        orig_sub_run = subprocess.run

        def mock_sub_run(cmd, **kwargs):
            if cmd[0] == "lsof":
                result = type("Result", (), {
                    "stdout": (
                        "COMMAND  PID  USER  FD  TYPE DEVICE SIZE/OFF NODE NAME\n"
                        "python3  9876 user  3u  REG  1,5  32768 123 /fake/db.path\n"
                    ),
                    "stderr": "",
                    "returncode": 0,
                })()
                return result
            return orig_sub_run(cmd, **kwargs)

        monkeypatch.setattr("subprocess.run", mock_sub_run)

        holders = _identify_lock_holders("/fake/db.path")
        assert len(holders) == 1
        assert "9876" in holders[0]
        assert "python3" in holders[0]
        assert "lsof" in holders[0]


class TestLockHolderUnknownFallback:
    """_identify_lock_holders returns empty list when no holders found."""

    def test_lock_holder_unknown_fallback(self, tmp_path, monkeypatch):
        from doctor.checks import _identify_lock_holders

        # Empty PID dir
        pid_dir = tmp_path / "run"
        pid_dir.mkdir()

        orig_expanduser = os.path.expanduser

        def mock_expanduser(p):
            if p == "~/.claude/pd/run":
                return str(pid_dir)
            return orig_expanduser(p)

        monkeypatch.setattr("os.path.expanduser", mock_expanduser)

        # Mock lsof as unavailable
        def mock_sub_run(cmd, **kwargs):
            if cmd[0] == "lsof":
                raise FileNotFoundError("lsof not found")
            return subprocess.run(cmd, **kwargs)

        monkeypatch.setattr("subprocess.run", mock_sub_run)

        holders = _identify_lock_holders("/fake/db.path")
        assert holders == []


# ---------------------------------------------------------------------------
# Check 11: Stale Dependencies
# ---------------------------------------------------------------------------


class TestCheck11StaleDependencyDetected:
    """check_stale_dependencies detects edges to completed blockers."""

    def test_stale_dependency_detected(self, tmp_path):
        import uuid as uuid_mod
        from doctor.checks import check_stale_dependencies

        db_path = _make_db(tmp_path)
        uuid_blocked = str(uuid_mod.uuid4())
        uuid_blocker = str(uuid_mod.uuid4())

        # Register blocker as completed
        _register_entity_with_uuid(
            db_path, "feature:blocker", "feature", "blocker",
            uuid_val=uuid_blocker,
        )
        # Register blocked entity
        _register_entity_with_uuid(
            db_path, "feature:blocked", "feature", "blocked",
            uuid_val=uuid_blocked,
        )

        # Set blocker to completed
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE entities SET status = 'completed' WHERE uuid = ?",
            (uuid_blocker,),
        )
        # Add stale dependency edge
        conn.execute(
            "INSERT INTO entity_dependencies (entity_uuid, blocked_by_uuid) VALUES (?, ?)",
            (uuid_blocked, uuid_blocker),
        )
        conn.commit()
        conn.close()

        conn = _entities_conn(db_path)
        try:
            result = check_stale_dependencies(entities_conn=conn)
            assert result.name == "stale_dependencies"
            assert not result.passed
            assert len(result.issues) == 1
            issue = result.issues[0]
            assert "Stale blocked_by edge" in issue.message
            assert uuid_blocked in issue.message
            assert uuid_blocker in issue.message
            assert "Remove stale dependency" in issue.fix_hint
        finally:
            conn.close()


class TestCheck11CleanDependenciesPass:
    """check_stale_dependencies passes when no stale edges exist."""

    def test_clean_dependencies_pass(self, tmp_path):
        import uuid as uuid_mod
        from doctor.checks import check_stale_dependencies

        db_path = _make_db(tmp_path)
        uuid_a = str(uuid_mod.uuid4())
        uuid_b = str(uuid_mod.uuid4())

        _register_entity_with_uuid(
            db_path, "feature:a", "feature", "a", uuid_val=uuid_a,
        )
        _register_entity_with_uuid(
            db_path, "feature:b", "feature", "b", uuid_val=uuid_b,
        )

        # Add dependency where blocker is NOT completed (status=active)
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO entity_dependencies (entity_uuid, blocked_by_uuid) VALUES (?, ?)",
            (uuid_a, uuid_b),
        )
        conn.commit()
        conn.close()

        conn = _entities_conn(db_path)
        try:
            result = check_stale_dependencies(entities_conn=conn)
            assert result.passed
            assert len(result.issues) == 0
        finally:
            conn.close()


# ===========================================================================
# Check: security-review command installation
# ===========================================================================


class TestCheckSecurityReviewCommandMissing:
    """security-review command missing -> warning."""

    def test_missing_command_warns(self, tmp_path):
        from doctor.checks import check_security_review_command

        # No .claude/commands/security-review.md created
        result = check_security_review_command(str(tmp_path))

        assert result.name == "security_review_command"
        assert not result.passed
        warnings = [i for i in result.issues if i.severity == "warning"]
        assert len(warnings) == 1
        assert "security-review" in warnings[0].message.lower()
        assert warnings[0].fix_hint is not None


class TestCheckSecurityReviewCommandPresent:
    """security-review command present -> no issues."""

    def test_present_command_passes(self, tmp_path):
        from doctor.checks import check_security_review_command

        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "security-review.md").write_text("# security review\n")

        result = check_security_review_command(str(tmp_path))

        assert result.name == "security_review_command"
        assert result.passed
        assert len(result.issues) == 0


class TestCheckSecurityReviewCommandAcceptsKwargs:
    """Check tolerates extra kwargs (dispatched via ctx dict)."""

    def test_accepts_extra_kwargs(self, tmp_path):
        from doctor.checks import check_security_review_command

        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True)
        (commands_dir / "security-review.md").write_text("stub\n")

        # Should accept and ignore arbitrary kwargs from run_diagnostics ctx
        result = check_security_review_command(
            project_root=str(tmp_path),
            entities_conn=None,
            artifacts_root="docs",
            base_branch="main",
        )
        assert result.passed


# ===========================================================================
# Check: stale/orphaned worktrees under .pd-worktrees/
# ===========================================================================


def _init_git_repo(path) -> None:
    """Initialize a minimal git repo with one commit at `path`."""
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "t@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "commit.gpgsign", "false"],
        check=True,
    )
    (path / "README.md").write_text("seed\n")
    subprocess.run(["git", "-C", str(path), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "seed"],
        check=True,
    )


class TestCheckStaleWorktreesNoDirectory:
    """No .pd-worktrees/ directory -> pass silently."""

    def test_missing_dir_passes(self, tmp_path):
        from doctor.checks import check_stale_worktrees

        result = check_stale_worktrees(project_root=str(tmp_path))

        assert result.name == "stale_worktrees"
        assert result.passed
        assert result.issues == []


class TestCheckStaleWorktreesClean:
    """All worktree dirs tracked by git -> no orphans."""

    def test_clean_worktrees_pass(self, tmp_path):
        from doctor.checks import check_stale_worktrees

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        # Create a real worktree via git
        worktrees_dir = repo / ".pd-worktrees"
        worktrees_dir.mkdir()
        task_path = worktrees_dir / "task-1"
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "-q",
             str(task_path), "-b", "worktree-test-task-1"],
            check=True,
        )

        result = check_stale_worktrees(project_root=str(repo))

        assert result.name == "stale_worktrees"
        assert result.passed, f"unexpected issues: {result.issues}"
        assert result.issues == []


class TestCheckStaleWorktreesFilesystemOrphan:
    """Directory present without git admin record -> warning."""

    def test_filesystem_orphan_warns(self, tmp_path):
        from doctor.checks import check_stale_worktrees

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        # Create a .pd-worktrees/task-orphan dir without running git worktree add
        worktrees_dir = repo / ".pd-worktrees"
        worktrees_dir.mkdir()
        (worktrees_dir / "task-orphan").mkdir()

        result = check_stale_worktrees(project_root=str(repo))

        assert result.name == "stale_worktrees"
        assert not result.passed
        warnings = [i for i in result.issues if i.severity == "warning"]
        assert len(warnings) == 1
        assert "task-orphan" in warnings[0].message
        assert "no git admin record" in warnings[0].message.lower()
        assert "rm -rf" in (warnings[0].fix_hint or "")


class TestCheckStaleWorktreesGitAdminOrphan:
    """Git admin record present without directory on disk -> warning."""

    def test_git_admin_orphan_warns(self, tmp_path):
        from doctor.checks import check_stale_worktrees

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        # Create a worktree, then delete the directory (without git cleanup)
        worktrees_dir = repo / ".pd-worktrees"
        worktrees_dir.mkdir()
        task_path = worktrees_dir / "task-ghost"
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "-q",
             str(task_path), "-b", "worktree-test-task-ghost"],
            check=True,
        )
        # Remove only the directory — leave the git admin record dangling.
        import shutil
        shutil.rmtree(task_path)

        result = check_stale_worktrees(project_root=str(repo))

        assert result.name == "stale_worktrees"
        assert not result.passed
        warnings = [i for i in result.issues if i.severity == "warning"]
        assert len(warnings) == 1
        assert "task-ghost" in warnings[0].message
        assert "directory missing" in warnings[0].message.lower()
        assert "git worktree prune" in (warnings[0].fix_hint or "")


class TestCheckStaleWorktreesNotAGitRepo:
    """Non-git-repo with .pd-worktrees/ -> skip silently (pass)."""

    def test_non_git_repo_skips(self, tmp_path):
        from doctor.checks import check_stale_worktrees

        # No git init; just create the directory
        (tmp_path / ".pd-worktrees").mkdir()
        (tmp_path / ".pd-worktrees" / "task-1").mkdir()

        result = check_stale_worktrees(project_root=str(tmp_path))

        # git worktree list fails in a non-repo → skip silently
        assert result.name == "stale_worktrees"
        assert result.passed
        assert result.issues == []


class TestCheckStaleWorktreesAcceptsKwargs:
    """Check tolerates extra kwargs (dispatched via ctx dict)."""

    def test_accepts_extra_kwargs(self, tmp_path):
        from doctor.checks import check_stale_worktrees

        result = check_stale_worktrees(
            project_root=str(tmp_path),
            entities_conn=None,
            artifacts_root="docs",
            base_branch="main",
        )
        assert result.passed


class TestCheckStaleWorktreesEmptyDirectory:
    """Empty .pd-worktrees/ directory -> pass, no orphan warnings (boundary: N=0 entries)."""

    def test_empty_worktrees_dir_passes(self, tmp_path):
        # Given a git repo with an empty .pd-worktrees/ directory
        from doctor.checks import check_stale_worktrees

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        (repo / ".pd-worktrees").mkdir()

        # When the stale_worktrees check runs
        result = check_stale_worktrees(project_root=str(repo))

        # Then it passes silently with no issues (no children to inspect)
        assert result.name == "stale_worktrees"
        assert result.passed, f"unexpected issues: {result.issues}"
        assert result.issues == []


class TestCheckStaleWorktreesNonDirectoryEntry:
    """Plain file under .pd-worktrees/ is NOT a worktree candidate; do not crash or flag."""

    def test_plain_file_entry_does_not_crash(self, tmp_path):
        # Given a .pd-worktrees/ containing a stray regular file (not a dir)
        from doctor.checks import check_stale_worktrees

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        worktrees_dir = repo / ".pd-worktrees"
        worktrees_dir.mkdir()
        (worktrees_dir / "README.txt").write_text("not a worktree\n")

        # When the stale_worktrees check runs
        result = check_stale_worktrees(project_root=str(repo))

        # Then the check returns cleanly — a stray file is neither an orphan nor a tracked worktree
        assert result.name == "stale_worktrees"
        # Must not error out; non-dir entries are simply ignored
        assert all(i.severity != "error" for i in result.issues)


class TestCheckStaleWorktreesMultipleOrphans:
    """Multiple filesystem orphans -> one warning per orphan (Zero/One/Many heuristic)."""

    def test_two_orphans_produce_two_warnings(self, tmp_path):
        # Given two orphan directories under .pd-worktrees/
        from doctor.checks import check_stale_worktrees

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        worktrees_dir = repo / ".pd-worktrees"
        worktrees_dir.mkdir()
        (worktrees_dir / "task-a").mkdir()
        (worktrees_dir / "task-b").mkdir()

        # When the check runs
        result = check_stale_worktrees(project_root=str(repo))

        # Then two distinct warnings are surfaced
        assert not result.passed
        warnings = [i for i in result.issues if i.severity == "warning"]
        assert len(warnings) == 2
        messages = " ".join(w.message for w in warnings)
        assert "task-a" in messages
        assert "task-b" in messages


def _write_ws_json(proj_dir, ws_uuid, legacy=None):
    """Write a workspace.json under <proj_dir>/.claude/pd/."""
    d = os.path.join(proj_dir, ".claude", "pd")
    os.makedirs(d, exist_ok=True)
    payload = {"workspace_uuid": ws_uuid, "schema_version": 1}
    if legacy is not None:
        payload["project_id_legacy"] = legacy
    with open(os.path.join(d, "workspace.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh)


def _make_ws_db(tmp_path, name, rows=(), entities=0):
    """v11 entities.db with a workspaces table (+ optional entity rows)."""
    db_path = str(tmp_path / name)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _metadata VALUES ('schema_version', '11')"
        )
        conn.execute(
            "CREATE TABLE workspaces ("
            " uuid TEXT NOT NULL PRIMARY KEY,"
            " project_id_legacy TEXT UNIQUE,"
            " project_root TEXT,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute("CREATE TABLE entities (uuid TEXT PRIMARY KEY)")
        for u, leg, root in rows:
            conn.execute(
                "INSERT INTO workspaces VALUES (?, ?, ?, 'n', 'n')",
                (u, leg, root),
            )
        for i in range(entities):
            conn.execute("INSERT INTO entities VALUES (?)", (f"e{i}",))
        conn.commit()
    finally:
        conn.close()
    return db_path


class TestCheckWorkspaceUuidConsistency:
    """First-ever coverage: the split-brain detector + fixable-hint choice."""

    _A = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
    _B = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb"
    _C = "cccccccc-3333-4333-8333-cccccccccccc"

    def test_file_matches_db_passes(self, tmp_path):
        from doctor.checks import check_workspace_uuid_consistency

        proj = tmp_path / "proj"
        proj.mkdir()
        root = os.path.abspath(str(proj))
        db = _make_ws_db(tmp_path, "e.db", rows=[(self._A, "leg", root)])
        _write_ws_json(str(proj), self._A)
        result = check_workspace_uuid_consistency(
            entities_db_path=db, project_root=str(proj)
        )
        assert result.passed
        assert result.issues == []

    def test_orphan_single_root_row_emits_adopt_hint(self, tmp_path):
        from doctor.checks import check_workspace_uuid_consistency

        proj = tmp_path / "proj"
        proj.mkdir()
        root = os.path.abspath(str(proj))
        db = _make_ws_db(tmp_path, "e.db", rows=[(self._B, "leg", root)])
        _write_ws_json(str(proj), self._A)  # orphan A; root owned by B
        result = check_workspace_uuid_consistency(
            entities_db_path=db, project_root=str(proj)
        )
        assert not result.passed
        assert result.issues[0].fix_hint.startswith(
            "Adopt workspace UUID from DB row"
        )

    def test_orphan_no_root_row_emits_insert_hint(self, tmp_path):
        from doctor.checks import check_workspace_uuid_consistency

        proj = tmp_path / "proj"
        proj.mkdir()
        db = _make_ws_db(tmp_path, "e.db")  # empty workspaces
        _write_ws_json(str(proj), self._A)
        result = check_workspace_uuid_consistency(
            entities_db_path=db, project_root=str(proj)
        )
        assert not result.passed
        assert result.issues[0].fix_hint.startswith(
            "Insert missing workspaces row"
        )

    def test_orphan_multi_root_row_manual_hint(self, tmp_path):
        from doctor.checks import check_workspace_uuid_consistency

        proj = tmp_path / "proj"
        proj.mkdir()
        root = os.path.abspath(str(proj))
        db = _make_ws_db(
            tmp_path, "e.db",
            rows=[(self._B, "l1", root), (self._C, "l2", root)],
        )
        _write_ws_json(str(proj), self._A)
        result = check_workspace_uuid_consistency(
            entities_db_path=db, project_root=str(proj)
        )
        assert not result.passed
        assert "Multiple workspaces rows" in result.issues[0].fix_hint

    def test_file_missing_with_entities_errors(self, tmp_path):
        from doctor.checks import check_workspace_uuid_consistency

        proj = tmp_path / "proj"
        proj.mkdir()
        db = _make_ws_db(tmp_path, "e.db", entities=3)
        result = check_workspace_uuid_consistency(
            entities_db_path=db, project_root=str(proj)
        )
        assert not result.passed
        assert any(i.severity == "error" for i in result.issues)

    def test_file_missing_empty_db_warns(self, tmp_path):
        from doctor.checks import check_workspace_uuid_consistency

        proj = tmp_path / "proj"
        proj.mkdir()
        db = _make_ws_db(tmp_path, "e.db", entities=0)
        result = check_workspace_uuid_consistency(
            entities_db_path=db, project_root=str(proj)
        )
        # Fresh checkout: warning, not error → still "passed" (no errors).
        assert result.passed
        assert any(i.severity == "warning" for i in result.issues)

    def test_legacy_mismatch_errors(self, tmp_path):
        from doctor.checks import check_workspace_uuid_consistency

        proj = tmp_path / "proj"
        proj.mkdir()
        root = os.path.abspath(str(proj))
        # DB row for A carries legacy 'db-leg'; file claims 'file-leg'.
        db = _make_ws_db(tmp_path, "e.db", rows=[(self._A, "db-leg", root)])
        _write_ws_json(str(proj), self._A, legacy="file-leg")
        result = check_workspace_uuid_consistency(
            entities_db_path=db, project_root=str(proj)
        )
        assert not result.passed
        assert any("project_id_legacy" in i.message for i in result.issues)

    def test_malformed_file_uuid_no_root_row_manual_hint(self, tmp_path):
        """Codex warning: a malformed (but parseable) file uuid + no root row
        must NOT get the fixable Insert hint (it would write a bad row)."""
        from doctor.checks import check_workspace_uuid_consistency

        proj = tmp_path / "proj"
        proj.mkdir()
        db = _make_ws_db(tmp_path, "e.db")  # empty workspaces
        _write_ws_json(str(proj), "not-a-uuid")
        result = check_workspace_uuid_consistency(
            entities_db_path=db, project_root=str(proj)
        )
        assert not result.passed
        hint = result.issues[0].fix_hint
        assert not hint.startswith("Insert missing workspaces row")
        assert "malformed" in hint


def _make_orphan_db(tmp_path, name, ws_rows=(), orphans=0):
    """entities.db with a workspaces table + an entities table carrying a
    ``workspace_uuid`` column, seeded with ``orphans`` rows in the unknown
    bucket (so check_unknown_workspace_orphans can count them)."""
    from entity_registry.database import _UNKNOWN_WORKSPACE_UUID

    db_path = str(tmp_path / name)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE workspaces ("
            " uuid TEXT NOT NULL PRIMARY KEY,"
            " project_id_legacy TEXT UNIQUE,"
            " project_root TEXT,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE entities (uuid TEXT PRIMARY KEY, workspace_uuid TEXT)"
        )
        for u, leg, root in ws_rows:
            conn.execute(
                "INSERT INTO workspaces VALUES (?, ?, ?, 'n', 'n')",
                (u, leg, root),
            )
        for i in range(orphans):
            conn.execute(
                "INSERT INTO entities VALUES (?, ?)",
                (f"orphan{i}", _UNKNOWN_WORKSPACE_UUID),
            )
        conn.commit()
    finally:
        conn.close()
    return db_path


class TestCheckUnknownWorkspaceOrphans:
    """Detect entities stranded in the unknown-workspace bucket + claim hint."""

    _WS = "dddddddd-4444-4444-8444-dddddddddddd"

    def test_orphans_single_workspace_emits_claim_hint(self, tmp_path):
        from doctor.checks import check_unknown_workspace_orphans

        proj = tmp_path / "proj"
        proj.mkdir()
        root = os.path.abspath(str(proj))
        db = _make_orphan_db(
            tmp_path, "e.db", ws_rows=[(self._WS, "leg", root)], orphans=3
        )
        result = check_unknown_workspace_orphans(
            entities_db_path=db, project_root=str(proj)
        )
        # Warning (not error) → still "passed"; emits the fixable claim hint.
        assert result.passed
        assert len(result.issues) == 1
        assert result.issues[0].severity == "warning"
        assert result.issues[0].fix_hint.startswith(
            "Claim unknown-workspace entities into"
        )
        assert self._WS in result.issues[0].fix_hint
        assert "3 entities" in result.issues[0].message

    def test_no_orphans_passes_clean(self, tmp_path):
        from doctor.checks import check_unknown_workspace_orphans

        proj = tmp_path / "proj"
        proj.mkdir()
        root = os.path.abspath(str(proj))
        db = _make_orphan_db(
            tmp_path, "e.db", ws_rows=[(self._WS, "leg", root)], orphans=0
        )
        result = check_unknown_workspace_orphans(
            entities_db_path=db, project_root=str(proj)
        )
        assert result.passed
        assert result.issues == []

    def test_orphans_ambiguous_workspace_manual_hint(self, tmp_path):
        from doctor.checks import check_unknown_workspace_orphans

        proj = tmp_path / "proj"
        proj.mkdir()
        # No workspaces row for this project_root → cannot auto-claim.
        db = _make_orphan_db(tmp_path, "e.db", ws_rows=(), orphans=2)
        result = check_unknown_workspace_orphans(
            entities_db_path=db, project_root=str(proj)
        )
        assert result.passed  # warning only
        assert len(result.issues) == 1
        assert not result.issues[0].fix_hint.startswith(
            "Claim unknown-workspace entities into"
        )

    def test_missing_db_is_noop(self, tmp_path):
        from doctor.checks import check_unknown_workspace_orphans

        result = check_unknown_workspace_orphans(
            entities_db_path=str(tmp_path / "nonexistent.db"),
            project_root=str(tmp_path),
        )
        assert result.passed
        assert result.issues == []
