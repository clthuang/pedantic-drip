"""Regression tests surviving Feature 129's cross-workspace-allowlist deletion.

Feature 129 deleted ``_fix_triage_cross_workspace_link`` (the grandfather /
re-attribute-parent / re-attribute-child / delete-relation fixer for
cross-workspace ``parent_uuid`` links) along with its FR-9 adversarial
fix_hint validator (``_normalize_and_validate_fix_hint`` /
``_parse_triage_choice``) and this module's 4-decision triage coverage — the
fixer was orphaned (never registered in ``fixer.py``'s ``_SAFE_PATTERNS``)
and the cross-workspace allowlist mechanism it triaged no longer exists.

This module was never dedicated to that fixer; two independent coverage
areas remain:

- ``test_canonical_trigger_sql_matches_production_source``: F117 TA.4 / R-1
  drift guard pinning ``_CANONICAL_TRIGGER_SQL`` against the
  ``enforce_immutable_workspace_uuid`` trigger body in
  ``entity_registry/database.py``.
- Task #7 workspace split-brain fix-action tests (``_fix_adopt_workspace_uuid``
  / ``_fix_insert_workspace_row`` / ``_fix_claim_unknown_entities``).
"""
from __future__ import annotations

import pytest

from doctor.fix_actions import FixContext


# F117 TA.1: canonical CREATE TRIGGER SQL for enforce_immutable_workspace_uuid.
# MUST be byte-identical to plugins/pd/hooks/lib/entity_registry/database.py
# lines 2042-2046 inside _migration_11_workspace_identity. The em-dash below
# is U+2014 (HORIZONTAL EM-DASH) — load-bearing per F117 design R-1.
# Drift detector: see test_canonical_trigger_sql_matches_production_source.
_CANONICAL_TRIGGER_SQL = """
            CREATE TRIGGER enforce_immutable_workspace_uuid
            BEFORE UPDATE OF workspace_uuid ON entities
            BEGIN SELECT RAISE(ABORT, 'workspace_uuid is immutable — use re-attribution API'); END
        """


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def entities_db_session(tmp_path):
    """Build a schema-correct entities.db connection via EntityDatabase.

    Bypasses MCP entity-server (which may be unavailable in test env);
    yields the underlying _conn for direct SQL fixtures (test-only access
    per CLAUDE.md gotcha — EntityDatabase has no public setter for the
    workspaces table rows these tests seed directly).
    """
    from entity_registry.database import EntityDatabase

    db = EntityDatabase(str(tmp_path / "entities.db"))
    try:
        yield db._conn  # test-only direct conn access; production fix functions consume this connection
    finally:
        db.close()


def test_canonical_trigger_sql_matches_production_source():
    """F117 TA.4 / R-1 mitigation: detect drift between _CANONICAL_TRIGGER_SQL
    in this test module and the source-of-truth in entity_registry/database.py
    (_migration_11_workspace_identity, lines ~2042-2046). Substring scan +
    whitespace normalization tolerates indentation drift but catches body changes.
    """
    import re
    from pathlib import Path

    db_source_path = (
        Path(__file__).parent.parent / "entity_registry" / "database.py"
    )
    db_source = db_source_path.read_text(encoding="utf-8")

    pattern = re.compile(
        r"CREATE TRIGGER enforce_immutable_workspace_uuid\s+"
        r"BEFORE UPDATE OF workspace_uuid ON entities\s+"
        r"BEGIN SELECT RAISE\(ABORT,\s*"
        r"'workspace_uuid is immutable — use re-attribution API'\s*"
        r"\); END",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(db_source)
    assert match is not None, (
        "Migration-11 CREATE TRIGGER enforce_immutable_workspace_uuid not "
        f"found in {db_source_path} — has the canonical source moved?"
    )

    def _normalize(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    assert _normalize(match.group(0)) == _normalize(_CANONICAL_TRIGGER_SQL), (
        "Canonical trigger SQL in test_fix_actions.py drifted from production "
        "source at database.py. Re-sync _CANONICAL_TRIGGER_SQL to match the "
        "CREATE TRIGGER block in _migration_11_workspace_identity."
    )


# ---------------------------------------------------------------------------
# Workspace split-brain fix actions (Task #7)
# ---------------------------------------------------------------------------

import json as _json
import os as _os

from doctor.fix_actions import (
    _fix_adopt_workspace_uuid,
    _fix_insert_workspace_row,
)

_WS_A = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
_WS_B = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb"


def _write_orphan_ws(proj_dir, ws_uuid):
    d = _os.path.join(proj_dir, ".claude", "pd")
    _os.makedirs(d, exist_ok=True)
    path = _os.path.join(d, "workspace.json")
    with open(path, "w", encoding="utf-8") as fh:
        _json.dump({"workspace_uuid": ws_uuid, "schema_version": 1}, fh)
    return path


def _ws_ctx(conn, project_root):
    return FixContext(
        entities_db_path="", artifacts_root="",
        project_root=project_root, db=None, engine=None,
        entities_conn=conn,
    )


def _file_uuid(path):
    with open(path, encoding="utf-8") as fh:
        return _json.load(fh)["workspace_uuid"]


def _seed_ws_row(conn, ws_uuid, legacy, root):
    conn.execute(
        "INSERT INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, 'n', 'n')",
        (ws_uuid, legacy, root),
    )
    conn.commit()


class TestFixAdoptWorkspaceUuid:
    def test_adopt_rewrites_file_and_check_then_passes(
        self, entities_db_session, tmp_path
    ):
        conn = entities_db_session
        proj = tmp_path / "proj"
        proj.mkdir()
        root = _os.path.abspath(str(proj))
        path = _write_orphan_ws(str(proj), _WS_A)  # orphan A
        _seed_ws_row(conn, _WS_B, "leg", root)      # canonical row B

        result = _fix_adopt_workspace_uuid(_ws_ctx(conn, str(proj)), None)
        assert "Adopted" in result
        assert _file_uuid(path) == _WS_B
        # Re-running the check against the same DB now passes.
        from doctor.checks import check_workspace_uuid_consistency
        re_check = check_workspace_uuid_consistency(
            entities_db_path=str(tmp_path / "entities.db"),
            project_root=str(proj),
        )
        assert re_check.passed

    def test_already_member_is_noop(self, entities_db_session, tmp_path):
        conn = entities_db_session
        proj = tmp_path / "proj"
        proj.mkdir()
        root = _os.path.abspath(str(proj))
        _write_orphan_ws(str(proj), _WS_A)
        _seed_ws_row(conn, _WS_A, "leg", root)  # A is already a member
        result = _fix_adopt_workspace_uuid(_ws_ctx(conn, str(proj)), None)
        assert "already consistent" in result

    def test_file_absent_is_noop(self, entities_db_session, tmp_path):
        conn = entities_db_session
        proj = tmp_path / "proj"
        proj.mkdir()  # no workspace.json
        result = _fix_adopt_workspace_uuid(_ws_ctx(conn, str(proj)), None)
        assert "absent" in result

    def test_missing_project_root_raises(self, entities_db_session):
        with pytest.raises(ValueError, match="project_root required"):
            _fix_adopt_workspace_uuid(_ws_ctx(entities_db_session, ""), None)


class TestFixInsertWorkspaceRow:
    def test_insert_creates_row(self, entities_db_session, tmp_path):
        conn = entities_db_session
        proj = tmp_path / "proj"
        proj.mkdir()
        _write_orphan_ws(str(proj), _WS_A)  # orphan A, empty workspaces
        result = _fix_insert_workspace_row(_ws_ctx(conn, str(proj)), None)
        assert "Inserted" in result
        present = conn.execute(
            "SELECT 1 FROM workspaces WHERE uuid = ?", (_WS_A,)
        ).fetchone()
        assert present is not None

    def test_already_member_is_noop(self, entities_db_session, tmp_path):
        conn = entities_db_session
        proj = tmp_path / "proj"
        proj.mkdir()
        root = _os.path.abspath(str(proj))
        _write_orphan_ws(str(proj), _WS_A)
        _seed_ws_row(conn, _WS_A, "leg", root)
        result = _fix_insert_workspace_row(_ws_ctx(conn, str(proj)), None)
        assert "already consistent" in result

    def test_malformed_uuid_refused(self, entities_db_session, tmp_path):
        """Defense in depth (codex warning): never insert a malformed uuid."""
        conn = entities_db_session
        proj = tmp_path / "proj"
        proj.mkdir()
        _write_orphan_ws(str(proj), "not-a-uuid")
        with pytest.raises(ValueError, match="malformed"):
            _fix_insert_workspace_row(_ws_ctx(conn, str(proj)), None)


class TestDoctorWorkspaceHealEndToEnd:
    """run_diagnostics → apply_fixes → re-run converges (the pd:doctor --fix
    path operators actually invoke)."""

    def test_detect_fix_reconverge(self, tmp_path):
        from doctor import run_diagnostics
        from doctor.fixer import apply_fixes
        from entity_registry.database import EntityDatabase

        db_path = str(tmp_path / "entities.db")
        proj = tmp_path / "proj"
        proj.mkdir()
        root = _os.path.abspath(str(proj))

        db = EntityDatabase(db_path)
        try:
            _seed_ws_row(db._conn, _WS_B, "leg", root)  # canonical row
        finally:
            db.close()
        _write_orphan_ws(str(proj), _WS_A)  # orphaned file

        before = run_diagnostics(db_path, str(proj), str(proj))
        ws_before = [
            c for c in before.checks
            if c.name == "workspace_uuid_consistency"
        ][0]
        assert not ws_before.passed

        apply_fixes(before, db_path, str(proj), str(proj))

        after = run_diagnostics(db_path, str(proj), str(proj))
        ws_after = [
            c for c in after.checks
            if c.name == "workspace_uuid_consistency"
        ][0]
        assert ws_after.passed
        assert _file_uuid(
            _os.path.join(str(proj), ".claude", "pd", "workspace.json")
        ) == _WS_B


class TestWorkspaceFixDryRun:
    """dry_run must not invoke the fix function — file + DB stay untouched."""

    def test_dry_run_leaves_file_and_db_untouched(self, tmp_path):
        from doctor.fixer import apply_fixes
        from doctor.models import DiagnosticReport, CheckResult, Issue
        from entity_registry.database import EntityDatabase

        db_path = str(tmp_path / "entities.db")
        EntityDatabase(db_path).close()  # real schema, empty workspaces
        proj = tmp_path / "proj"
        proj.mkdir()
        path = _write_orphan_ws(str(proj), _WS_A)

        issue = Issue(
            check="workspace_uuid_consistency", severity="error", entity=None,
            message="workspace.json UUID ... not present in workspaces table",
            fix_hint=f"Insert missing workspaces row for file UUID {_WS_A}",
        )
        report = DiagnosticReport(
            healthy=False,
            checks=[CheckResult(
                name="workspace_uuid_consistency", passed=False,
                issues=[issue], elapsed_ms=0,
            )],
            total_issues=1, error_count=1, warning_count=0,
            severity_summary={"error": 1},
        )
        fix_report = apply_fixes(
            report, db_path,
            str(proj), str(proj), dry_run=True,
        )
        # File unchanged; no row inserted.
        assert _file_uuid(path) == _WS_A
        conn = __import__("sqlite3").connect(db_path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM workspaces WHERE uuid = ?", (_WS_A,)
            ).fetchone()[0]
        finally:
            conn.close()
        assert n == 0
        # And it was reported as a would-be safe fix, not applied.
        assert any(
            r.classification == "safe" and not r.applied
            for r in fix_report.results
        )


class TestFixClaimUnknownEntities:
    """The claim fix re-attributes unknown-workspace orphans into the project's
    workspace, resolved at fix time from project_root."""

    _TARGET = "eeeeeeee-5555-4555-8555-eeeeeeeeeeee"

    def _db_with_orphans(self, tmp_path, n):
        from entity_registry.database import EntityDatabase

        db = EntityDatabase(str(tmp_path / "entities.db"))
        for i in range(n):
            db.register_entity(
                "feature", f"f{i}", f"F{i}", project_id="__unknown__"
            )
        return db

    def _ctx(self, db, project_root):
        return FixContext(
            entities_db_path="", artifacts_root="",
            project_root=project_root, db=db, engine=None,
            entities_conn=db._conn if db else None,
        )

    def test_claims_orphans_into_resolved_workspace(self, tmp_path):
        from doctor.fix_actions import _fix_claim_unknown_entities
        from entity_registry.database import _UNKNOWN_WORKSPACE_UUID

        proj = tmp_path / "proj"
        proj.mkdir()
        root = _os.path.abspath(str(proj))
        db = self._db_with_orphans(tmp_path, 3)
        _seed_ws_row(db._conn, self._TARGET, "leg", root)  # the claim target
        try:
            result = _fix_claim_unknown_entities(self._ctx(db, str(proj)), None)
            assert "Claimed 3" in result
            assert self._TARGET in result
            remaining = db._conn.execute(
                "SELECT COUNT(*) FROM entities WHERE workspace_uuid = ?",
                (_UNKNOWN_WORKSPACE_UUID,),
            ).fetchone()[0]
            assert remaining == 0
        finally:
            db.close()

    def test_no_workspace_row_is_noop(self, tmp_path):
        from doctor.fix_actions import _fix_claim_unknown_entities

        proj = tmp_path / "proj"
        proj.mkdir()
        db = self._db_with_orphans(tmp_path, 2)  # no workspaces row for root
        try:
            result = _fix_claim_unknown_entities(self._ctx(db, str(proj)), None)
            assert "no-op" in result
        finally:
            db.close()

    def test_missing_project_root_raises(self, tmp_path):
        from doctor.fix_actions import _fix_claim_unknown_entities

        db = self._db_with_orphans(tmp_path, 0)
        try:
            with pytest.raises(ValueError, match="project_root required"):
                _fix_claim_unknown_entities(self._ctx(db, ""), None)
        finally:
            db.close()

    def test_missing_db_raises(self, tmp_path):
        from doctor.fix_actions import _fix_claim_unknown_entities

        proj = tmp_path / "proj"
        proj.mkdir()
        with pytest.raises(ValueError, match="No entities DB"):
            _fix_claim_unknown_entities(self._ctx(None, str(proj)), None)
