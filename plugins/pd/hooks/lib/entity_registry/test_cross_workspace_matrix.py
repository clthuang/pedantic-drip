"""Feature 129: cross-workspace links are ordinary, permitted operations.

Historically (Feature 115/116) `EntityDatabase` gated cross-workspace links
via `_assert_same_workspace_pairwise`, raising `CrossWorkspaceError` for a
mismatched-workspace pair unless it was allowlisted. Feature 129 deleted
that gate entirely: the THREE previously-gated EntityDatabase public
handlers (`set_parent`, `add_dependency`, `add_okr_alignment`) now treat a
cross-workspace pair the same as a same-workspace pair — the link is
written, no exception, no allowlist required.

This module pins the resulting round-trip matrix: for each handler, a
cross-workspace pair and a same-workspace pair both succeed (3 handlers x
2 cases = 6 parametrized cases), and the cross-workspace case additionally
reads the created link back through the same public API a caller would
use. The former "allowlisted" case is gone — with no gate to bypass, an
allowlist row no longer changes the outcome, so that case would have been
a vacuous duplicate of the re-scoped cross-workspace case.

Tests invoke `EntityDatabase` instance methods (NOT the MCP server entry
points) — this isolates handler behavior from MCP runtime availability and
matches the F115 design rev 2 contract's test placement.

See spec:
  /Users/terry/projects/pedantic-drip/docs/features/129-workspace-scoped-queries/spec.md
"""
from __future__ import annotations

import contextlib
import uuid as uuid_mod

import pytest

from entity_registry.database import EntityDatabase


# ---------------------------------------------------------------------------
# Workspace seeding (session-scoped, reused across all 9 parametrized cases)
# ---------------------------------------------------------------------------


_WS_LEGACY_IDS = ("ws-A", "ws-B", "ws-C")


def _seed_workspace(db: EntityDatabase, legacy_id: str) -> str:
    """Insert a workspaces row and return the assigned workspace_uuid.

    Mirrors `_bootstrap_test_workspace` from test_database.py (the established
    fixture-seeding pattern) but with a deterministic legacy_id per workspace.
    """
    ws_uuid = str(uuid_mod.uuid4())
    now = db._now_iso()
    db._conn.execute(
        "INSERT OR IGNORE INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws_uuid, legacy_id, None, now, now),
    )
    db._conn.commit()
    row = db._conn.execute(
        "SELECT uuid FROM workspaces WHERE project_id_legacy = ?",
        (legacy_id,),
    ).fetchone()
    return row["uuid"]


def _seed_feature_and_backlog(
    db: EntityDatabase, workspace_uuid: str, suffix: str
) -> dict:
    """Register one feature + one backlog in the given workspace.

    Returns a dict keyed by kind ('feature', 'backlog') → dict with type_id +
    uuid strings, suitable for the pair-fixture dict shape required by FR-6.

    `suffix` makes the entity_id unique per workspace so the
    (workspace_uuid, type_id) UNIQUE constraint never fires across seeded
    workspaces. The strict `^\\d+-.+` entity_id format check is opted-out
    session-wide by `hooks/lib/conftest.py` — see that file for context.
    """
    feature_id = f"001-feat-{suffix}"
    backlog_id = f"002-bl-{suffix}"
    feature_uuid = db.register_entity(
        "feature", feature_id, f"Feature {suffix}",
        workspace_uuid=workspace_uuid,
    )
    backlog_uuid = db.register_entity(
        "backlog", backlog_id, f"Backlog {suffix}",
        workspace_uuid=workspace_uuid,
    )
    return {
        "feature": {
            "type_id": f"feature:{feature_id}",
            "uuid": feature_uuid,
        },
        "backlog": {
            "type_id": f"backlog:{backlog_id}",
            "uuid": backlog_uuid,
        },
    }


@pytest.fixture(scope="session")
def entity_db(tmp_path_factory):
    """Session-scoped EntityDatabase with 3 workspaces and seeded entities.

    Schema is built once for the whole module; per-case mutations are rolled
    back by the autouse `_reset_per_case` fixture via SAVEPOINT.

    Fixture name `entity_db` (not `entities_db_session`) avoids collision
    with FR-7/FR-9's `entities_db_session` fixture (raw sqlite3.Connection)
    in `doctor/test_fix_actions.py` — per spec FR-6 naming note.
    """
    tmp_path = tmp_path_factory.mktemp("f116_tc3")
    db_path = str(tmp_path / "entities.db")
    db = EntityDatabase(db_path)

    # Bootstrap 3 workspaces with one feature + one backlog each.
    ws_uuids: dict[str, str] = {}
    seeded: dict[str, dict] = {}
    for legacy_id in _WS_LEGACY_IDS:
        ws_uuid = _seed_workspace(db, legacy_id)
        ws_uuids[legacy_id] = ws_uuid
        suffix = legacy_id.split("-")[-1]  # 'A', 'B', 'C'
        seeded[legacy_id] = _seed_feature_and_backlog(db, ws_uuid, suffix)

    # Attach the maps so per-case fixtures can resolve workspaces + entities.
    db._test_ws_uuids = ws_uuids        # type: ignore[attr-defined]
    db._test_seeded = seeded            # type: ignore[attr-defined]

    # Smoke-check isolation mode before defining the reset fixture.
    # EntityDatabase uses sqlite3 default isolation_level='' (implicit-tx
    # mode), NOT autocommit (None). Per-case SAVEPOINT/ROLLBACK relies on
    # being inside a transaction — autocommit would render SAVEPOINT a no-op.
    assert db._conn.isolation_level is not None, (
        "EntityDatabase._conn must NOT be in autocommit mode for SAVEPOINT "
        "rollback to work between parametrized cases"
    )

    yield db
    db.close()


@pytest.fixture(autouse=True)
def _reset_per_case(entity_db):
    """SAVEPOINT-based reset between parametrized cases.

    Direct `_conn` + `_in_transaction` access: test-only — EntityDatabase has
    no public SAVEPOINT API. Per spec FR-6 contract.

    Implementation note: a bare `SAVEPOINT` would be destroyed by the first
    handler's internal `_commit()` (which calls `_conn.commit()` and ends the
    surrounding transaction in Python's default-isolation sqlite3). To keep
    the savepoint alive across handler invocations we wrap it in an explicit
    `BEGIN IMMEDIATE` AND flip `db._in_transaction = True` so the production
    `_commit()` method becomes a no-op (matching the `transaction()` context
    manager's suppression contract at database.py:6395).

    Each case's mutations (set_parent UPDATE, INSERT into entity_dependencies
    / entity_okr_alignment / cross_workspace_allowlist) are confined to the
    savepoint scope; ROLLBACK TO SAVEPOINT discards them so subsequent cases
    see the same pristine seeded state. The outer transaction is then
    rolled back as well so no committed state escapes the test boundary.
    """
    # Suppress production `_commit()` calls so the savepoint stays alive
    # across handler invocations. Match `transaction()` semantics at
    # database.py:6395.
    entity_db._conn.execute("BEGIN IMMEDIATE")
    entity_db._in_transaction = True
    entity_db._conn.execute("SAVEPOINT tc3_case")
    try:
        yield
    finally:
        # Discard case-local mutations: rollback to savepoint, then ROLLBACK
        # the outer transaction to ensure no committed state escapes.
        try:
            entity_db._conn.execute("ROLLBACK TO SAVEPOINT tc3_case")
            entity_db._conn.execute("RELEASE SAVEPOINT tc3_case")
            entity_db._conn.execute("ROLLBACK")
        finally:
            entity_db._in_transaction = False


# ---------------------------------------------------------------------------
# Pair-fixture helpers (return dict shape {parent: {type_id, uuid}, child: {...}})
# ---------------------------------------------------------------------------


def _cross_ws_pair_fixture(db: EntityDatabase) -> dict:
    """Cross-workspace pair: feature in ws-A as parent, backlog in ws-B as child."""
    return {
        "parent": db._test_seeded["ws-A"]["feature"],
        "child": db._test_seeded["ws-B"]["backlog"],
    }


def _same_ws_pair_fixture(db: EntityDatabase) -> dict:
    """Same-workspace pair: feature + backlog both in ws-A."""
    return {
        "parent": db._test_seeded["ws-A"]["feature"],
        "child": db._test_seeded["ws-A"]["backlog"],
    }


def _link_persisted(db: EntityDatabase, handler_name: str, pair: dict) -> bool:
    """Read back the link `handler_name` should have created for `pair`.

    Uses the same public read APIs a caller would use — no direct `_conn`
    access. One branch per `HANDLERS` entry.
    """
    if handler_name == "set_parent":
        child = db.get_entity(pair["child"]["uuid"])
        return child is not None and child["parent_uuid"] == pair["parent"]["uuid"]
    if handler_name == "add_dependency":
        rows = db.query_dependencies(
            entity_uuid=pair["child"]["uuid"],
            blocked_by_uuid=pair["parent"]["uuid"],
        )
        return len(rows) == 1
    if handler_name == "add_okr_alignment":
        aligned = db.get_okr_alignments(pair["parent"]["uuid"])
        return any(kr["uuid"] == pair["child"]["uuid"] for kr in aligned)
    raise AssertionError(f"no read-back check defined for handler {handler_name!r}")


# ---------------------------------------------------------------------------
# 3 handlers x 2 ACs = 6 parametrized cases
# ---------------------------------------------------------------------------


HANDLERS = [
    (
        "set_parent",
        lambda db, pair: db.set_parent(
            pair["child"]["type_id"], pair["parent"]["type_id"]
        ),
    ),
    (
        "add_dependency",
        lambda db, pair: db.add_dependency(
            pair["child"]["uuid"], pair["parent"]["uuid"]
        ),
    ),
    (
        "add_okr_alignment",
        lambda db, pair: db.add_okr_alignment(
            pair["parent"]["uuid"], pair["child"]["uuid"]
        ),
    ),
]


@pytest.mark.parametrize("handler_name,handler_fn", HANDLERS)
@pytest.mark.parametrize(
    "ac,pair_fixture,expected",
    [
        (
            "AC-E.1_cross_ws_permitted",
            _cross_ws_pair_fixture,
            contextlib.nullcontext(),
        ),
        (
            "AC-E.2_same_ws_succeeds",
            _same_ws_pair_fixture,
            contextlib.nullcontext(),
        ),
    ],
)
def test_t2b_5_cross_workspace_gate_matrix(
    entity_db, handler_name, handler_fn, ac, pair_fixture, expected
):
    """F129: 3 handlers x 2 cases = 6 cross-workspace/same-workspace cases.

    Both cases succeed now that the cross-workspace gate is gone; the
    cross-workspace case is additionally verified non-vacuous by reading
    the created link back (see `_link_persisted`).
    """
    pair = pair_fixture(entity_db)
    with expected:
        handler_fn(entity_db, pair)
    if ac == "AC-E.1_cross_ws_permitted":
        assert _link_persisted(entity_db, handler_name, pair), (
            f"{handler_name} did not persist a readable link for {ac}"
        )


# ---------------------------------------------------------------------------
# Dedicated positive cross-workspace round-trip tests (spec SC2 / design
# Testing Strategy #1). Non-vacuous: each of these raised CrossWorkspaceError
# on develop before Feature 129 deleted the gate.
# ---------------------------------------------------------------------------


def test_add_dependency_cross_workspace_round_trip(entity_db):
    """add_dependency across two workspaces succeeds and reads back."""
    pair = _cross_ws_pair_fixture(entity_db)
    entity_db.add_dependency(pair["child"]["uuid"], pair["parent"]["uuid"])
    rows = entity_db.query_dependencies(
        entity_uuid=pair["child"]["uuid"],
        blocked_by_uuid=pair["parent"]["uuid"],
    )
    assert len(rows) == 1


def test_set_parent_cross_workspace_round_trip(entity_db):
    """set_parent across two workspaces succeeds and reads back."""
    pair = _cross_ws_pair_fixture(entity_db)
    entity_db.set_parent(pair["child"]["type_id"], pair["parent"]["type_id"])
    child = entity_db.get_entity(pair["child"]["uuid"])
    assert child is not None
    assert child["parent_uuid"] == pair["parent"]["uuid"]


def test_add_okr_alignment_cross_workspace_round_trip(entity_db):
    """add_okr_alignment across two workspaces succeeds and reads back."""
    pair = _cross_ws_pair_fixture(entity_db)
    entity_db.add_okr_alignment(pair["parent"]["uuid"], pair["child"]["uuid"])
    aligned = entity_db.get_okr_alignments(pair["parent"]["uuid"])
    assert any(kr["uuid"] == pair["child"]["uuid"] for kr in aligned)
