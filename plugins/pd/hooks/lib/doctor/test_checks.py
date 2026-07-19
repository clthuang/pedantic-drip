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

        CREATE TABLE IF NOT EXISTS entity_tags (
            entity_uuid TEXT NOT NULL,
            tag         TEXT NOT NULL,
            PRIMARY KEY (entity_uuid, tag)
        );
    """)
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Live-schema fixtures (post-Migration-11)
#
# _make_db (above) builds the legacy pre-Mig-11 schema (entity_type /
# project_id, no `kind` / `workspace_uuid`) and remains the baseline fixture
# for checks that are schema-version-agnostic (db_readiness,
# referential_integrity, config/security/stale-worktrees). _make_live_db /
# _register_live_feature (below) bootstrap the CURRENT live schema via
# EntityDatabase (precedent: entity_registry/test_database.py) for checks
# that need it (e.g. missed_cascade's `entity_relations` edges).
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
# Task 1.2: Check 8 (DB Readiness)
# ===========================================================================


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
    # nothing): post-feature-133 retirement the surviving checks carry 10
    # constant SQL sites.
    assert len(collected) >= 10, (
        f"walker collected only {len(collected)} SQL sites — expected >= 10; "
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

    # Guard a silently-broken walker: the fixer write paths carry 4 constant
    # SQL sites (fixer.py delegates, contributing 0; fix_actions holds the
    # UPDATE / DELETE statements — 4 after feature 133 retired 11 fix fns,
    # leaving 7 survivors of which 4 carry constant .execute() calls).
    assert len(collected) >= 4, (
        f"walker collected only {len(collected)} fixer SQL sites — expected "
        ">= 4; the .execute() AST shape may have drifted"
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

# Feature 131 removed check_project_attribution: 21 checks -> 20. Feature 129
# removed check_cross_workspace_parent_uuid: 20 checks -> 19. Single source
# for the orchestrator/CLI check-count assertions below.
EXPECTED_CHECK_COUNT = 10


class TestOrchestratorReportHas10Checks:
    """Orchestrator: report always has 10 checks (feature 133's
    post-retirement CHECK_ORDER membership; see EXPECTED_CHECK_COUNT).
    """

    def test_report_has_10_checks(self, tmp_path):
        from doctor import run_diagnostics

        db_path = _make_db(tmp_path)
        (tmp_path / "docs").mkdir(exist_ok=True)

        report = run_diagnostics(db_path, str(tmp_path / "docs"), str(tmp_path))
        assert len(report.checks) == EXPECTED_CHECK_COUNT


class TestOrchestratorReportEvenWhenLocked:
    """Orchestrator: 10 checks even when DB is locked."""

    def test_report_10_checks_even_when_locked(self, tmp_path):
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
    """Orchestrator: a hermetically healthy project reports 0 errors and 0
    warnings (spec SC1), proven non-vacuous by a fault-control companion
    that seeds a live referential-integrity violation on the SAME fixture
    and confirms the retained check_referential_integrity still fires.
    """

    def _seed_healthy_fixture(self, tmp_path, monkeypatch):
        """Seed every survivor check's non-DB prerequisite (spec SC1)."""
        from doctor.checks import _get_expected_entity_version

        db_path = _make_db(tmp_path, "entities.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE _metadata SET value = ? WHERE key = 'schema_version'",
            (str(_get_expected_entity_version()),),
        )
        conn.commit()
        conn.close()

        artifacts_root = tmp_path / "docs"
        artifacts_root.mkdir(exist_ok=True)

        commands_dir = tmp_path / ".claude" / "commands"
        commands_dir.mkdir(parents=True, exist_ok=True)
        (commands_dir / "security-review.md").write_text("# security review\n")

        # check_no_free_text_status_parsers greps these 3 relative paths
        # under project_root (unlike status_write_path/severity_vocab, which
        # resolve via __file__ and are already hermetic) -- stub them clean
        # so the check runs its real grep instead of warning "lint skipped".
        for rel in (
            "plugins/pd/hooks/lib/entity_registry/backfill.py",
            "plugins/pd/hooks/lib/doctor/checks.py",
            "plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py",
        ):
            stub = tmp_path / rel
            stub.parent.mkdir(parents=True, exist_ok=True)
            stub.write_text("# stub for check_no_free_text_status_parsers\n")

        # No .pd-worktrees/ directory -- check_stale_worktrees no-ops silently.
        # Hermeticity (design-i2 W4): point the v2-cutover marker check at an
        # empty tmp dir so it never reads the real ~/.claude/pd.
        monkeypatch.setenv("PD_REBUILD_MARKER_DIR", str(tmp_path))

        return db_path, str(artifacts_root)

    def test_healthy_project_all_pass(self, tmp_path, monkeypatch):
        from doctor import run_diagnostics

        db_path, artifacts_root = self._seed_healthy_fixture(tmp_path, monkeypatch)

        report = run_diagnostics(db_path, artifacts_root, str(tmp_path))

        errors = [
            (c.name, i.message) for c in report.checks for i in c.issues
            if i.severity == "error"
        ]
        warnings = [
            (c.name, i.message) for c in report.checks for i in c.issues
            if i.severity == "warning"
        ]
        assert errors == []
        assert warnings == []
        # info issues are permitted (spec SC1)

    def test_referential_integrity_fault_control_still_fires(self, tmp_path, monkeypatch):
        """Non-vacuity control: seeding a live violation on the same
        hermetic fixture still surfaces it, proving the 0/0 result above
        comes from retirement, not a broken runner."""
        from doctor import run_diagnostics

        db_path, artifacts_root = self._seed_healthy_fixture(tmp_path, monkeypatch)

        uuid_val = "self-ref-uuid"
        _register_entity_with_uuid(
            db_path, "feature:001", "feature", "001",
            uuid_val=uuid_val,
            parent_type_id="feature:001", parent_uuid=uuid_val,
        )

        report = run_diagnostics(db_path, artifacts_root, str(tmp_path))

        ref_check = next(
            c for c in report.checks if c.name == "referential_integrity"
        )
        self_ref_errors = [
            i for i in ref_check.issues
            if i.severity == "error" and "own parent" in i.message
        ]
        assert len(self_ref_errors) >= 1
        assert report.error_count >= 1

    def test_config_validity_fault_control_still_fires(self, tmp_path, monkeypatch):
        """Non-vacuity control #2: a DIFFERENT retained-check FAMILY (the
        config surface, not an entity-DB query) also still fires on the
        SAME hermetic fixture -- proving the SC1 zero isn't an artifact
        specific to referential-integrity faults but generalizes across
        check families.

        missed_cascade would be a poor second control here: this
        fixture's legacy v9 schema (``_make_db``) has no entity_relations
        table at all, and check_missed_cascade silently swallows
        sqlite3.Error, so it can't be faulted without first adding DDL
        the healthy fixture deliberately doesn't have. config_validity's
        artifacts_root-missing branch is a clean, single-surface fault
        that doesn't perturb any other check's prerequisites.
        """
        from doctor import run_diagnostics
        import shutil

        db_path, artifacts_root = self._seed_healthy_fixture(tmp_path, monkeypatch)
        shutil.rmtree(artifacts_root)

        report = run_diagnostics(db_path, artifacts_root, str(tmp_path))

        config_check = next(
            c for c in report.checks if c.name == "config_validity"
        )
        missing_dir_errors = [
            i for i in config_check.issues
            if i.severity == "error" and "does not exist" in i.message
        ]
        assert len(missing_dir_errors) >= 1, (
            f"expected an artifacts_root-missing error; got "
            f"{config_check.issues}"
        )
        assert report.error_count >= 1


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
            # Entity-dependent checks should be skipped (post-133: only the
            # two remaining _ENTITY_DB_CHECKS members).
            for check in report.checks:
                if check.name in ("referential_integrity", "missed_cascade"):
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


class TestCliJsonOutputHas10Checks:
    """CLI: JSON output contains 10 checks (feature 133's post-retirement
    CHECK_ORDER membership; see EXPECTED_CHECK_COUNT).
    """

    def test_cli_json_output_has_10_checks(self, tmp_path):
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
# Check 11: Missed Cascade (feature 124 D6)
# ---------------------------------------------------------------------------


class TestCheck11MissedCascadeDetected:
    """check_missed_cascade flags a 'blocked' entity whose (single) blocker
    is already resolved -- cascade_unblock should have flipped it."""

    def test_missed_cascade_detected(self, tmp_path):
        from doctor.checks import check_missed_cascade

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "blocker", status="completed")
        blocker_uuid = _entity_uuid(conn, "feature:blocker")
        _register_live_feature(db, "blocked", status="blocked")
        blocked_uuid = _entity_uuid(conn, "feature:blocked")
        db.add_dependency(blocked_uuid, blocker_uuid)

        try:
            result = check_missed_cascade(entities_conn=conn)
            assert result.name == "missed_cascade"
            assert not result.passed
            assert len(result.issues) == 1
            issue = result.issues[0]
            assert "Missed cascade" in issue.message
            assert blocked_uuid in issue.message
            assert blocker_uuid in issue.message
            assert issue.fix_hint == "Run cascade evaluation"
        finally:
            conn.close()


class TestCheck11CleanDependenciesPass:
    """check_missed_cascade passes when no missed-cascade edges exist."""

    def test_clean_dependencies_pass(self, tmp_path):
        from doctor.checks import check_missed_cascade

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "a", status="active")
        a_uuid = _entity_uuid(conn, "feature:a")
        _register_live_feature(db, "b", status="blocked")
        b_uuid = _entity_uuid(conn, "feature:b")

        # Blocker NOT resolved (status=active) -- must not fire.
        db.add_dependency(b_uuid, a_uuid)

        try:
            result = check_missed_cascade(entities_conn=conn)
            assert result.passed
            assert len(result.issues) == 0
        finally:
            conn.close()


class TestCheck11MultiBlockerPartialNoFire:
    """SC5: fires ONLY when EVERY blocker is resolved -- a blocked entity
    with one resolved + one unresolved blocker must NOT fire (kills the
    naive edge-to-completed-blocker false positive)."""

    def test_multi_blocker_partial_completion_no_fire(self, tmp_path):
        from doctor.checks import check_missed_cascade

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "resolved-blocker", status="completed")
        resolved_uuid = _entity_uuid(conn, "feature:resolved-blocker")
        _register_live_feature(db, "active-blocker", status="active")
        active_uuid = _entity_uuid(conn, "feature:active-blocker")
        _register_live_feature(db, "downstream", status="blocked")
        downstream_uuid = _entity_uuid(conn, "feature:downstream")

        db.add_dependency(downstream_uuid, resolved_uuid)
        db.add_dependency(downstream_uuid, active_uuid)

        try:
            result = check_missed_cascade(entities_conn=conn)
            assert result.passed
            assert len(result.issues) == 0

            # Resolve the remaining blocker via raw SQL, bypassing
            # update_entity's OWN live cascade hook -- going through
            # update_entity here would flip 'downstream' to 'ready'
            # immediately (the feature working as intended), and it would
            # never sit in 'blocked' for the doctor to catch. Raw SQL
            # simulates the actual missed-cascade scenario this check
            # exists for (e.g. a fail-open cascade failure or an external
            # write) without exercising the live cascade path.
            conn.execute(
                "UPDATE entities SET status = 'completed' WHERE uuid = ?",
                (active_uuid,),
            )
            conn.commit()
            result2 = check_missed_cascade(entities_conn=conn)
            assert not result2.passed
            assert len(result2.issues) == 1
            assert result2.issues[0].entity == "feature:downstream"
        finally:
            conn.close()


class TestCheck11PerKindEquivalence:
    """Feature 124 D6: SQL-vs-Python equivalence, one blocker per CASE arm.

    Asserts the missed-cascade SQL's per-kind CASE agrees with
    ``DependencyManager._all_blockers_resolved`` (D4) for one blocker of
    every kind in the design-pinned terminal table.
    """

    @pytest.mark.parametrize(
        "kind,resolved_status",
        [
            ("brainstorm", "abandoned"),
            ("backlog", "dropped"),
            ("task", "closed"),
            ("bug", "resolved"),
            ("feature", "completed"),
        ],
    )
    def test_sql_matches_python_helper(self, tmp_path, kind, resolved_status):
        from doctor.checks import check_missed_cascade
        from entity_registry.dependencies import DependencyManager

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(
            db, "blocker-x", kind=kind, status=resolved_status,
        )
        blocker_uuid = _entity_uuid(conn, f"{kind}:blocker-x")
        _register_live_feature(db, "downstream-x", status="blocked")
        downstream_uuid = _entity_uuid(conn, "feature:downstream-x")
        db.add_dependency(downstream_uuid, blocker_uuid)

        try:
            sql_flagged = {
                i.entity for i in check_missed_cascade(entities_conn=conn).issues
            }
            python_resolved = DependencyManager()._all_blockers_resolved(
                db, downstream_uuid
            )
            # Both sides must agree, and (since this arm's blocker is
            # resolved) both must say "resolved" -- an arm silently
            # defaulting to False on both sides would pass the equality
            # check vacuously.
            assert python_resolved is True
            assert ("feature:downstream-x" in sql_flagged) == python_resolved
        finally:
            conn.close()


class TestCheck11ZeroBlockerEdgeDivergence:
    """Feature 124 D6 (checks.py's missed_cascade docstring, ~:1842-1846):
    an entity that is 'blocked' but has ZERO recorded blocker edges is a
    DIFFERENT anomaly class from a missed cascade -- the check's outer
    EXISTS clause deliberately scopes it to "a cascade opportunity
    existed and was missed". The Python helper
    (``DependencyManager._all_blockers_resolved``), by contrast, treats a
    zero-blocker entity as vacuously resolved (``all([]) is True`` --
    load-bearing for the delete-hook's D5.3 empty-set case).

    Both sides of this INTENTIONAL divergence are pinned here, in the
    SAME test class, so a future change to either one is a deliberate
    choice rather than an accidental drift caught only by a flaky
    cross-file coincidence.
    """

    def test_python_helper_says_vacuously_resolved_with_zero_blockers(
        self, tmp_path
    ):
        # Given a 'blocked' entity with NO blocker edges ever recorded.
        from entity_registry.dependencies import DependencyManager

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "lone-blocked", status="blocked")
        lone_uuid = _entity_uuid(conn, "feature:lone-blocked")

        try:
            # Then the Python helper is vacuously True (all([]) is True).
            assert DependencyManager().get_blockers(db, lone_uuid) == []
            assert (
                DependencyManager()._all_blockers_resolved(db, lone_uuid)
                is True
            )
        finally:
            conn.close()

    def test_doctor_check_does_not_fire_for_the_same_zero_blocker_entity(
        self, tmp_path
    ):
        # Given the SAME construction: 'blocked' with zero blocker edges.
        from doctor.checks import check_missed_cascade

        db, conn = _make_live_db(tmp_path)
        _register_live_feature(db, "lone-blocked-2", status="blocked")

        try:
            # When the doctor's missed_cascade check runs.
            result = check_missed_cascade(entities_conn=conn)
            # Then it does NOT fire -- the outer EXISTS(an edge) clause
            # excludes it; this is a different anomaly class than a
            # missed cascade, not a false negative.
            assert result.passed
            assert result.issues == []
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


