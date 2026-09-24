"""C5b step 1 / C17: workflow_engine callers register with one resolved workspace.

* ``init_feature_state`` and ``init_project_state`` register in the canonical
  ``__unknown__`` workspace when given none — by passing its uuid, no longer
  the ``project_id="__unknown__"`` alias. The ``entity_created`` label stays
  ``"__unknown__"`` (that workspace's ``project_id_legacy``).
* ``promote_task`` allocates the task's number and registers the task in ONE
  workspace (C17): the caller's ``workspace_uuid``, else the workspace the
  project root's legacy id names. Before C5b the number always came from the
  legacy-id workspace while the row went to the caller's, so on a fixture
  where the two differ the counter and the row parted ways.
"""
from __future__ import annotations

import inspect
import textwrap

import pytest

import workflow_engine.task_promotion as task_promotion
from entity_registry.database import _UNKNOWN_WORKSPACE_UUID, EntityDatabase
from entity_registry.test_helpers import bootstrap_test_workspace
from workflow_engine.feature_lifecycle import init_feature_state, init_project_state

LEGACY_A = "c5b-ws-a"
LEGACY_B = "c5b-ws-b"
UNKNOWN_LABEL = "__unknown__"
_ALIASES = frozenset({"project_id", "parent_type_id"})
_PLAN_MD = textwrap.dedent("""\
    # Tasks

    ## Phase 1

    #### Task 1.1: Add structured log fields
    - **Do:** Add fields.
""")
_TASK_HEADING = "Task 1.1: Add structured log fields"


@pytest.fixture
def two_workspaces():
    db = EntityDatabase(":memory:")
    ws_a = bootstrap_test_workspace(db, LEGACY_A)
    ws_b = bootstrap_test_workspace(db, LEGACY_B)
    yield db, ws_a, ws_b
    db.close()


def _record_calls(monkeypatch, target, method_name: str) -> list[dict]:
    """Wrap ``target.method_name``; return every call's arguments by parameter
    name, positional ones included."""
    calls: list[dict] = []
    original = getattr(target, method_name)
    signature = inspect.signature(original)

    def recording(*args, **kwargs):
        calls.append(dict(signature.bind(*args, **kwargs).arguments))
        return original(*args, **kwargs)

    monkeypatch.setattr(target, method_name, recording)
    return calls


def _created_label(db: EntityDatabase, type_id: str) -> str:
    rows = db._conn.execute(
        "SELECT project_id FROM phase_events "
        "WHERE type_id = ? AND event_type = 'entity_created'",
        (type_id,),
    ).fetchall()
    assert len(rows) == 1, f"{type_id}: expected one entity_created event, got {len(rows)}"
    return rows[0][0]


def _row_workspace(db: EntityDatabase, type_id: str) -> str:
    return db._conn.execute(
        "SELECT workspace_uuid FROM entities WHERE type_id = ?", (type_id,)
    ).fetchone()[0]


def _counter(db: EntityDatabase, workspace_uuid: str, kind: str) -> int | None:
    row = db._conn.execute(
        "SELECT next_val FROM sequences WHERE workspace_uuid = ? AND entity_type = ?",
        (workspace_uuid, kind),
    ).fetchone()
    return None if row is None else row[0]


def _assert_no_alias(calls: list[dict], expected_workspace_uuid: str) -> None:
    """Every recorded call carried *expected_workspace_uuid* and no alias value."""
    assert calls, "the call was never made"
    for arguments in calls:
        leaked = sorted(name for name in _ALIASES
                        if arguments.get(name) is not None)
        assert not leaked, f"still passed {leaked}: {arguments}"
        assert arguments.get("workspace_uuid") == expected_workspace_uuid, arguments


# ---------------------------------------------------------------------------
# feature_lifecycle: the __unknown__ default is a workspace uuid, not an alias
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("given_workspace, expected_label", [
    (None, UNKNOWN_LABEL),
    ("ws_b", LEGACY_B),
])
def test_init_feature_state_registers_in_one_workspace(
    tmp_path, monkeypatch, two_workspaces, given_workspace, expected_label,
):
    db, _ws_a, ws_b = two_workspaces
    workspace_uuid = ws_b if given_workspace == "ws_b" else None
    expected_workspace = ws_b if given_workspace == "ws_b" else _UNKNOWN_WORKSPACE_UUID
    feature_dir = tmp_path / "features" / "009-lifecycle"
    feature_dir.mkdir(parents=True)
    registered = _record_calls(monkeypatch, db, "register_entity")

    init_feature_state(db, None, str(tmp_path), str(feature_dir), "009", "lifecycle",
                       "standard", "feature/009-lifecycle", workspace_uuid=workspace_uuid)

    _assert_no_alias(registered, expected_workspace)
    assert _row_workspace(db, "feature:009-lifecycle") == expected_workspace
    assert _created_label(db, "feature:009-lifecycle") == expected_label


@pytest.mark.parametrize("given_workspace, expected_label", [
    (None, UNKNOWN_LABEL),
    ("ws_b", LEGACY_B),
])
def test_init_project_state_registers_in_one_workspace(
    tmp_path, monkeypatch, two_workspaces, given_workspace, expected_label,
):
    db, _ws_a, ws_b = two_workspaces
    workspace_uuid = ws_b if given_workspace == "ws_b" else None
    expected_workspace = ws_b if given_workspace == "ws_b" else _UNKNOWN_WORKSPACE_UUID
    registered = _record_calls(monkeypatch, db, "register_entity")

    init_project_state(db, str(tmp_path), str(tmp_path / "projects" / "004-plan"),
                       "004", "plan", "feature/004-plan", "[]", "[]",
                       workspace_uuid=workspace_uuid)

    _assert_no_alias(registered, expected_workspace)
    assert _row_workspace(db, "project:004-plan") == expected_workspace
    assert _created_label(db, "project:004-plan") == expected_label


# ---------------------------------------------------------------------------
# task_promotion (C17): one workspace allocates the number and holds the row
# ---------------------------------------------------------------------------


def _feature_with_plan(db: EntityDatabase, tmp_path, workspace_uuid: str) -> str:
    plan_dir = tmp_path / "features" / "052-promoting"
    plan_dir.mkdir(parents=True)
    (plan_dir / "plan.md").write_text(_PLAN_MD)
    db.register_entity("feature", name="Promoting", seq=52, slug="promoting",
                       status="active", artifact_path=str(plan_dir),
                       workspace_uuid=workspace_uuid)
    return "feature:052-promoting"


def test_promote_task_allocates_and_registers_in_the_callers_workspace(
    tmp_path, monkeypatch, two_workspaces,
):
    """The project root's legacy id names workspace A; the caller says B.
    Both the counter and the row are B's."""
    db, ws_a, ws_b = two_workspaces
    monkeypatch.setattr(task_promotion, "_compute_legacy_project_id", lambda *_a, **_k: LEGACY_A)
    feature_type_id = _feature_with_plan(db, tmp_path, ws_b)

    result = task_promotion.promote_task(db, feature_type_id, _TASK_HEADING, workspace_uuid=ws_b)

    task_type_id = result["task_type_id"]
    assert _counter(db, ws_b, "task") is not None
    assert _counter(db, ws_a, "task") is None
    assert _row_workspace(db, task_type_id) == ws_b
    assert _created_label(db, task_type_id) == LEGACY_B


def test_promote_task_without_a_workspace_resolves_the_legacy_id_once(
    tmp_path, monkeypatch, two_workspaces,
):
    """No caller workspace: the legacy id's workspace (A) is resolved once and
    that one value reaches the allocator and the registration."""
    db, ws_a, ws_b = two_workspaces
    monkeypatch.setattr(task_promotion, "_compute_legacy_project_id", lambda *_a, **_k: LEGACY_A)
    feature_type_id = _feature_with_plan(db, tmp_path, ws_a)
    allocations = _record_calls(monkeypatch, db, "next_sequence_value")
    registrations = _record_calls(monkeypatch, db, "register_entity")

    result = task_promotion.promote_task(db, feature_type_id, _TASK_HEADING)

    task_type_id = result["task_type_id"]
    _assert_no_alias(allocations, ws_a)
    _assert_no_alias(registrations, ws_a)
    assert _counter(db, ws_a, "task") is not None
    assert _counter(db, ws_b, "task") is None
    assert _row_workspace(db, task_type_id) == ws_a
    assert _created_label(db, task_type_id) == LEGACY_A


def test_promote_task_with_a_workspace_does_not_need_the_legacy_id(
    tmp_path, monkeypatch, two_workspaces,
):
    """A caller workspace is the whole answer: an unregistered legacy id no
    longer fails the allocation (before C5b the allocator resolved it and
    raised)."""
    db, _ws_a, ws_b = two_workspaces
    monkeypatch.setattr(task_promotion, "_compute_legacy_project_id",
                        lambda *_a, **_k: "no-such-legacy-id")
    feature_type_id = _feature_with_plan(db, tmp_path, ws_b)

    result = task_promotion.promote_task(db, feature_type_id, _TASK_HEADING, workspace_uuid=ws_b)

    assert result["promoted"] is True
    assert _row_workspace(db, result["task_type_id"]) == ws_b


def test_promote_task_names_the_workspace_it_could_not_resolve(
    tmp_path, monkeypatch, two_workspaces,
):
    db, ws_a, _ws_b = two_workspaces
    monkeypatch.setattr(task_promotion, "_compute_legacy_project_id",
                        lambda *_a, **_k: "no-such-legacy-id")
    feature_type_id = _feature_with_plan(db, tmp_path, ws_a)

    with pytest.raises(ValueError, match="project_id='no-such-legacy-id' has no matching"):
        task_promotion.promote_task(db, feature_type_id, _TASK_HEADING)
    assert _counter(db, ws_a, "task") is None
