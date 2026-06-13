"""Feature 116 FR-7 (T2a.7): 4-decision triage tests for
``_fix_triage_cross_workspace_link``.

Exercises every branch of the triage decision tree plus the grandfather
fallback (no reason supplied) and the unknown-choice negative path.

All seeding bypasses ``EntityDatabase`` public APIs and writes directly to
the underlying sqlite3 connection — this is test-only scaffolding because
the production code paths that would create cross-workspace links go through
``set_parent`` (which is BLOCKED by ``_assert_same_workspace_pairwise``), so
there is no public API to create the very condition that this fix function
exists to triage. The ``enforce_immutable_workspace_uuid`` trigger likewise
blocks the ``re-attribute parent`` / ``re-attribute child`` branches at the
SQL layer, so the seed helper drops the trigger for the duration of the test.
"""
from __future__ import annotations

import sqlite3
import uuid

import pytest

from doctor.fix_actions import (
    FixContext,
    _fix_triage_cross_workspace_link,
)
from doctor.models import Issue


# Module-level UUID constants used by FR-9 adversarial tests.
_VALID_UUID_1 = "a1a1a1a1-a1a1-a1a1-a1a1-a1a1a1a1a1a1"
_VALID_UUID_2 = "b2b2b2b2-b2b2-b2b2-b2b2-b2b2b2b2b2b2"


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


def _recreate_workspace_uuid_trigger(conn: sqlite3.Connection) -> None:
    """F117 TA.1: re-arm the enforce_immutable_workspace_uuid trigger that
    _seed_cross_workspace_pair drops during cross-workspace seeding.

    Called AFTER _seed_cross_workspace_pair (which DROPs the trigger to
    allow seed INSERTs) and BEFORE invoking _fix_triage_cross_workspace_link
    in tests that exercise the F117 capture/replay path. Mirrors
    entity_registry/database.py:2042-2046 byte-identical; if that source
    changes, update _CANONICAL_TRIGGER_SQL to match.
    """
    conn.execute(_CANONICAL_TRIGGER_SQL)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def entities_db_session(tmp_path):
    """Build a schema-correct entities.db connection via EntityDatabase.

    Bypasses MCP entity-server (which may be unavailable in test env);
    yields the underlying _conn for direct SQL fixtures (test-only access
    per CLAUDE.md gotcha — EntityDatabase has no public allowlist setter,
    and no public API exists for creating cross-workspace parent links).
    """
    from entity_registry.database import EntityDatabase

    db = EntityDatabase(str(tmp_path / "entities.db"))
    try:
        yield db._conn  # test-only direct conn access; production fix functions consume this connection
    finally:
        db.close()


def _make_fix_ctx(entities_conn: sqlite3.Connection) -> FixContext:
    """Build a minimal FixContext for triage tests.

    Only entities_conn is load-bearing for cross-workspace fix paths; other
    fields are populated with no-op placeholders that satisfy the 8-field
    dataclass contract (entities_db_path, memory_db_path, artifacts_root,
    project_root, db, engine, entities_conn, memory_conn).
    """
    return FixContext(
        entities_db_path="",
        memory_db_path="",
        artifacts_root="",
        project_root="",
        db=None,
        engine=None,
        entities_conn=entities_conn,
        memory_conn=None,
    )


def _seed_cross_workspace_pair(conn: sqlite3.Connection) -> tuple[str, str]:
    """Seed two workspaces + parent in A + child in B with parent_uuid link.

    Returns (parent_uuid, child_uuid). Drops the
    ``enforce_immutable_workspace_uuid`` trigger so the fix function's
    ``UPDATE entities SET workspace_uuid = ...`` branches can execute (the
    trigger normally blocks all such UPDATEs — production re-attribution
    paths drop + recreate the trigger; we drop it for the test lifetime).
    """
    # Drop the workspace_uuid immutability trigger so the fix function's
    # re-attribute branches can execute the UPDATE statements directly.
    conn.execute("DROP TRIGGER IF EXISTS enforce_immutable_workspace_uuid")

    ws_a_uuid = str(uuid.uuid4())
    ws_b_uuid = str(uuid.uuid4())
    now = "2026-05-17T00:00:00"
    conn.execute(
        "INSERT INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws_a_uuid, "ws-a", None, now, now),
    )
    conn.execute(
        "INSERT INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws_b_uuid, "ws-b", None, now, now),
    )

    parent_uuid = str(uuid.uuid4())
    child_uuid = str(uuid.uuid4())
    # Required NOT NULL columns on entities (post-F109):
    # uuid, workspace_uuid, type_id, entity_id, name, created_at, updated_at,
    # type, kind, lifecycle_class.
    conn.execute(
        "INSERT INTO entities "
        "(uuid, workspace_uuid, type_id, entity_id, name, created_at, "
        " updated_at, type, kind, lifecycle_class) "
        "VALUES (?, ?, 'feature:p-tc4', 'p-tc4', 'parent-tc4', ?, ?, "
        " 'work', 'feature', 'feature_flow')",
        (parent_uuid, ws_a_uuid, now, now),
    )
    conn.execute(
        "INSERT INTO entities "
        "(uuid, workspace_uuid, type_id, entity_id, name, created_at, "
        " updated_at, type, kind, lifecycle_class) "
        "VALUES (?, ?, 'backlog:c-tc4', 'c-tc4', 'child-tc4', ?, ?, "
        " 'work', 'backlog', 'feature_flow')",
        (child_uuid, ws_b_uuid, now, now),
    )
    # Wire up the cross-workspace parent link.
    conn.execute(
        "UPDATE entities SET parent_uuid = ? WHERE uuid = ?",
        (parent_uuid, child_uuid),
    )
    conn.commit()
    return parent_uuid, child_uuid


# ---------------------------------------------------------------------------
# Branch assertion helpers (one per triage choice)
# ---------------------------------------------------------------------------


def _assert_parent_moved_to_child_ws(conn, parent_uuid, child_uuid, reason):
    child_ws = conn.execute(
        "SELECT workspace_uuid FROM entities WHERE uuid=?", (child_uuid,)
    ).fetchone()[0]
    parent_ws = conn.execute(
        "SELECT workspace_uuid FROM entities WHERE uuid=?", (parent_uuid,)
    ).fetchone()[0]
    assert parent_ws == child_ws, "Expected parent moved to child's workspace"


def _assert_child_moved_to_parent_ws(conn, parent_uuid, child_uuid, reason):
    child_ws = conn.execute(
        "SELECT workspace_uuid FROM entities WHERE uuid=?", (child_uuid,)
    ).fetchone()[0]
    parent_ws = conn.execute(
        "SELECT workspace_uuid FROM entities WHERE uuid=?", (parent_uuid,)
    ).fetchone()[0]
    assert child_ws == parent_ws, "Expected child moved to parent's workspace"


def _assert_parent_uuid_set_null(conn, parent_uuid, child_uuid, reason):
    pu = conn.execute(
        "SELECT parent_uuid FROM entities WHERE uuid=?", (child_uuid,)
    ).fetchone()[0]
    assert pu is None, f"Expected NULL parent_uuid; got {pu!r}"


def _assert_allowlist_row_inserted_with_reason(
    conn, parent_uuid, child_uuid, reason
):
    row = conn.execute(
        "SELECT reason FROM cross_workspace_allowlist "
        "WHERE parent_uuid=? AND child_uuid=?",
        (parent_uuid, child_uuid),
    ).fetchone()
    assert row is not None, "Expected allowlist row inserted"
    assert row[0] == reason, f"Expected reason={reason!r}; got {row[0]!r}"


TRIAGE_CASES = [
    ("re-attribute parent", _assert_parent_moved_to_child_ws),
    ("re-attribute child", _assert_child_moved_to_parent_ws),
    ("delete relation", _assert_parent_uuid_set_null),
    ("grandfather", _assert_allowlist_row_inserted_with_reason),
]


# ---------------------------------------------------------------------------
# Parametrized 4-branch coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("choice,assertion", TRIAGE_CASES)
def test_t2a_7_triage_branch(entities_db_session, choice, assertion):
    parent_uuid, child_uuid = _seed_cross_workspace_pair(entities_db_session)
    _recreate_workspace_uuid_trigger(entities_db_session)  # F117 TA.5
    reason = "operator approved cross-org link"
    fix_hint = (
        f"triage_cross_workspace_links:{parent_uuid}:{child_uuid}"
        f"|choice:{choice}"
        f"|reason:{reason}"
    )
    issue = Issue(
        check="check_cross_workspace_parent_uuid",
        severity="warning",
        entity=child_uuid,
        message="cross-workspace link",
        fix_hint=fix_hint,
    )
    ctx = _make_fix_ctx(entities_db_session)
    _fix_triage_cross_workspace_link(ctx, issue)
    assertion(entities_db_session, parent_uuid, child_uuid, reason)


def test_t2a_7_triage_grandfather_without_reason_uses_fallback(
    entities_db_session,
):
    parent_uuid, child_uuid = _seed_cross_workspace_pair(entities_db_session)
    _recreate_workspace_uuid_trigger(entities_db_session)  # F117 TA.5
    fix_hint = (
        f"triage_cross_workspace_links:{parent_uuid}:{child_uuid}"
        f"|choice:grandfather"
    )  # no reason: field
    issue = Issue(
        check="check_cross_workspace_parent_uuid",
        severity="warning",
        entity=child_uuid,
        message="x",
        fix_hint=fix_hint,
    )
    _fix_triage_cross_workspace_link(
        _make_fix_ctx(entities_db_session), issue
    )
    row = entities_db_session.execute(
        "SELECT reason FROM cross_workspace_allowlist "
        "WHERE parent_uuid=? AND child_uuid=?",
        (parent_uuid, child_uuid),
    ).fetchone()
    assert row is not None
    assert row[0] == "operator-grandfathered (no reason supplied)"


def test_t2a_7_triage_unknown_choice_raises_value_error(entities_db_session):
    parent_uuid, child_uuid = _seed_cross_workspace_pair(entities_db_session)
    _recreate_workspace_uuid_trigger(entities_db_session)  # F117 TA.5
    fix_hint = (
        f"triage_cross_workspace_links:{parent_uuid}:{child_uuid}"
        f"|choice:bogus"
    )
    issue = Issue(
        check="check_cross_workspace_parent_uuid",
        severity="warning",
        entity=child_uuid,
        message="x",
        fix_hint=fix_hint,
    )
    with pytest.raises(ValueError, match="Unknown triage choice"):
        _fix_triage_cross_workspace_link(
            _make_fix_ctx(entities_db_session), issue
        )


# ---------------------------------------------------------------------------
# Feature 116 FR-9 (TC.7a): adversarial fix_hint tests — TDD red phase.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_hint,error_fragment", [
    # case 1: nul byte injection
    (f"triage_cross_workspace_links:{_VALID_UUID_1}:{_VALID_UUID_2}\x00", "invalid character"),
    # case 2: cyrillic confusable in uuid field (а = U+0430)
    (f"triage_cross_workspace_links:аaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa:{_VALID_UUID_2}|choice:grandfather", "invalid character"),
    # case 3: shell metacharacter in uuid field
    (f"triage_cross_workspace_links:{_VALID_UUID_1};rm -rf /:{_VALID_UUID_2}|choice:grandfather", "invalid character"),
    # case 4: shell metacharacter in reason
    (f"triage_cross_workspace_links:{_VALID_UUID_1}:{_VALID_UUID_2}|choice:grandfather|reason:legit$(rm -rf /)", "invalid character in reason"),
    # case 5: backtick in reason
    (f"triage_cross_workspace_links:{_VALID_UUID_1}:{_VALID_UUID_2}|choice:grandfather|reason:abc`whoami`", "invalid character in reason"),
    # case 5b: semicolon + ampersand in reason
    (f"triage_cross_workspace_links:{_VALID_UUID_1}:{_VALID_UUID_2}|choice:grandfather|reason:foo; bar & baz", "invalid character in reason"),
    # case 5c: parentheses in reason
    (f"triage_cross_workspace_links:{_VALID_UUID_1}:{_VALID_UUID_2}|choice:grandfather|reason:foo(bar)", "invalid character in reason"),
    # case 6: over-length
    ("triage_cross_workspace_links:" + ("a"*2000), "too long"),
    # case 7: unknown segment
    (f"triage_cross_workspace_links:{_VALID_UUID_1}:{_VALID_UUID_2}|bogus:val", "unknown segment"),
])
def test_fr9_adversarial_fix_hint_rejected(bad_hint, error_fragment):
    """FR-9 / AC-9.1: _normalize_and_validate_fix_hint rejects adversarial inputs.

    TDD red phase: this test will fail with ImportError or AttributeError until
    TC.5 implements the helper.
    """
    from doctor.fix_actions import _normalize_and_validate_fix_hint
    with pytest.raises(ValueError, match=error_fragment):
        _normalize_and_validate_fix_hint(bad_hint)


def test_fr9_legitimate_grandfather_with_reason_preserves_behavior(entities_db_session):
    """FR-9 / AC-9.3: legitimate grandfather reason passes through normalizer."""
    parent_uuid, child_uuid = _seed_cross_workspace_pair(entities_db_session)
    _recreate_workspace_uuid_trigger(entities_db_session)  # F117 TA.5
    reason = "operator approved cross-org link"
    fix_hint = (
        f"triage_cross_workspace_links:{parent_uuid}:{child_uuid}"
        f"|choice:grandfather|reason:{reason}"
    )
    issue = Issue(
        check="check_cross_workspace_parent_uuid",
        severity="warning",
        entity=child_uuid,
        message="x",
        fix_hint=fix_hint,
    )
    _fix_triage_cross_workspace_link(_make_fix_ctx(entities_db_session), issue)
    row = entities_db_session.execute(
        "SELECT reason FROM cross_workspace_allowlist WHERE parent_uuid=? AND child_uuid=?",
        (parent_uuid, child_uuid),
    ).fetchone()
    assert row is not None, "Expected allowlist row inserted"
    assert row[0] == reason, f"Expected reason={reason!r}; got {row[0]!r}"


# ---------------------------------------------------------------------------
# Feature 117 TA.2 / TA.4: trigger-active re-attribute tests.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "choice",
    ["re-attribute parent", "re-attribute child"],
)
def test_re_attribute_against_trigger_active_db(entities_db_session, choice):
    """F117 TA.2 / FR-A.3: re-attribute survives the enforce_immutable_workspace_uuid
    trigger via sqlite_master capture/replay (TDD red against pre-F117 production
    code; green after TA.3 lands _execute_re_attribute_with_trigger_dance).

    Inverts F116 TC.4 fixture polarity: re-arms trigger BEFORE invoking the
    fix function (vs F116 fixture which left trigger dropped). Single re-arm
    suffices for both parametrized choices (pytest re-runs test body per param).
    """
    parent_uuid, child_uuid = _seed_cross_workspace_pair(entities_db_session)
    _recreate_workspace_uuid_trigger(entities_db_session)

    pre_trigger_sql = entities_db_session.execute(
        "SELECT sql FROM sqlite_master WHERE name='enforce_immutable_workspace_uuid'"
    ).fetchone()[0]
    assert pre_trigger_sql is not None, "Pre-call: trigger should exist"

    fix_hint = (
        f"triage_cross_workspace_links:{parent_uuid}:{child_uuid}"
        f"|choice:{choice}"
    )
    issue = Issue(
        check="check_cross_workspace_parent_uuid",
        severity="warning",
        entity=child_uuid,
        message="cross-workspace link",
        fix_hint=fix_hint,
    )

    _fix_triage_cross_workspace_link(_make_fix_ctx(entities_db_session), issue)

    post_trigger_sql = entities_db_session.execute(
        "SELECT sql FROM sqlite_master WHERE name='enforce_immutable_workspace_uuid'"
    ).fetchone()[0]
    assert post_trigger_sql == pre_trigger_sql, (
        f"Trigger SQL drift detected:\npre:  {pre_trigger_sql!r}\npost: {post_trigger_sql!r}"
    )

    # Post-call trigger still enforces immutability against any other row.
    # Use the child (re-attribute parent case) or parent (re-attribute child case)
    # — whichever entity was NOT mutated by the re-attribute call.
    untouched_uuid = child_uuid if choice == "re-attribute parent" else parent_uuid
    with pytest.raises(sqlite3.IntegrityError, match="workspace_uuid is immutable"):
        entities_db_session.execute(
            "UPDATE entities SET workspace_uuid = ? WHERE uuid = ?",
            ("00000000-0000-0000-0000-000000000000", untouched_uuid),
        )


def test_re_attribute_aborts_when_trigger_absent(entities_db_session):
    """F117 TA.4 / FR-A.6: aborts with RuntimeError if trigger missing from
    sqlite_master (do NOT degrade to bare UPDATE). Fixture leaves trigger
    dropped (no _recreate call); abort fires before any workspace_uuid mutation.
    """
    parent_uuid, child_uuid = _seed_cross_workspace_pair(entities_db_session)
    pre_ws = entities_db_session.execute(
        "SELECT workspace_uuid FROM entities WHERE uuid = ?", (parent_uuid,)
    ).fetchone()[0]

    fix_hint = (
        f"triage_cross_workspace_links:{parent_uuid}:{child_uuid}"
        f"|choice:re-attribute parent"
    )
    issue = Issue(
        check="check_cross_workspace_parent_uuid",
        severity="warning",
        entity=child_uuid,
        message="x",
        fix_hint=fix_hint,
    )
    with pytest.raises(RuntimeError, match="enforce_immutable_workspace_uuid trigger not found"):
        _fix_triage_cross_workspace_link(_make_fix_ctx(entities_db_session), issue)

    post_ws = entities_db_session.execute(
        "SELECT workspace_uuid FROM entities WHERE uuid = ?", (parent_uuid,)
    ).fetchone()[0]
    assert post_ws == pre_ws


class _FailingUpdateConn:
    """F117 TA.4 / FR-A.4: proxy raising on UPDATE entities SET workspace_uuid only.

    NOTE on Python data model: __enter__/__exit__ MUST be defined on the class
    (not delegated via __getattr__). Special-method lookup uses type(obj).__enter__,
    bypassing instance __getattr__ entirely (Python docs §3.3.10). Without explicit
    __enter__/__exit__, `with conn:` inside _execute_re_attribute_with_trigger_dance
    would AttributeError before UPDATE — defeating the test.
    """

    def __init__(self, real_conn):
        self._real = real_conn

    def execute(self, sql, params=()):
        stripped = sql.lstrip().upper()
        if stripped.startswith("UPDATE ENTITIES SET WORKSPACE_UUID"):
            raise sqlite3.OperationalError("simulated UPDATE failure (F117 FR-A.4)")
        return self._real.execute(sql, params)

    def commit(self):
        return self._real.commit()

    def __enter__(self):
        return self._real.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._real.__exit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_re_attribute_restores_trigger_on_update_failure(entities_db_session):
    """F117 TA.4 / FR-A.4: trigger restored + workspace_uuid unchanged when
    UPDATE raises mid-transaction. Uses _FailingUpdateConn proxy (FK injection
    rejected at design — fix function reads workspace_uuid from entities table).
    """
    parent_uuid, child_uuid = _seed_cross_workspace_pair(entities_db_session)
    _recreate_workspace_uuid_trigger(entities_db_session)

    pre_trigger_sql = entities_db_session.execute(
        "SELECT sql FROM sqlite_master WHERE name='enforce_immutable_workspace_uuid'"
    ).fetchone()[0]
    pre_parent_ws = entities_db_session.execute(
        "SELECT workspace_uuid FROM entities WHERE uuid = ?", (parent_uuid,)
    ).fetchone()[0]

    ctx = _make_fix_ctx(entities_db_session)
    ctx.entities_conn = _FailingUpdateConn(entities_db_session)

    fix_hint = (
        f"triage_cross_workspace_links:{parent_uuid}:{child_uuid}"
        f"|choice:re-attribute parent"
    )
    issue = Issue(
        check="check_cross_workspace_parent_uuid",
        severity="warning",
        entity=child_uuid,
        message="x",
        fix_hint=fix_hint,
    )
    with pytest.raises(sqlite3.OperationalError, match="simulated UPDATE failure"):
        _fix_triage_cross_workspace_link(ctx, issue)

    post_trigger_sql = entities_db_session.execute(
        "SELECT sql FROM sqlite_master WHERE name='enforce_immutable_workspace_uuid'"
    ).fetchone()[0]
    assert post_trigger_sql == pre_trigger_sql

    post_parent_ws = entities_db_session.execute(
        "SELECT workspace_uuid FROM entities WHERE uuid = ?", (parent_uuid,)
    ).fetchone()[0]
    assert post_parent_ws == pre_parent_ws


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
        entities_db_path="", memory_db_path="", artifacts_root="",
        project_root=project_root, db=None, engine=None,
        entities_conn=conn, memory_conn=None,
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
        mem_path = str(tmp_path / "memory.db")  # absent → memory checks skip
        proj = tmp_path / "proj"
        proj.mkdir()
        root = _os.path.abspath(str(proj))

        db = EntityDatabase(db_path)
        try:
            _seed_ws_row(db._conn, _WS_B, "leg", root)  # canonical row
        finally:
            db.close()
        _write_orphan_ws(str(proj), _WS_A)  # orphaned file

        before = run_diagnostics(db_path, mem_path, str(proj), str(proj))
        ws_before = [
            c for c in before.checks
            if c.name == "workspace_uuid_consistency"
        ][0]
        assert not ws_before.passed

        apply_fixes(before, db_path, mem_path, str(proj), str(proj))

        after = run_diagnostics(db_path, mem_path, str(proj), str(proj))
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
            report, db_path, str(tmp_path / "memory.db"),
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
