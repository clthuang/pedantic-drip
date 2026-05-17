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
