"""C17 / C5b step 1: the entity server's allocate+register tools use ONE workspace.

The tools that allocate a number and then register the entity — the
``register_entity`` tool with ``auto_id``, ``issue_spawn`` and
``create_key_result`` — resolve the workspace once and hand that one value to
``generate_entity_id`` (so to ``next_sequence_value``) and to
``register_entity``; neither call receives the ``project_id`` alias.

The fixture makes the two resolutions differ: the server's own workspace is B
while its legacy project id names workspace A. Before C5b the ``auto_id`` and
``issue_spawn`` paths took the number from A's counter and put the row in B.

Every expected ``entity_created`` label is what the pre-C5b build wrote for
the same input: the workspace's ``project_id_legacy`` when the tool had a
workspace, the legacy project id when it resolved the workspace from that id.
``create_key_result`` never read the server's workspace; it still resolves
from the legacy project id, so its workspace and label are the base's.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys

import pytest

_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _hooks_lib)
_mcp_dir = os.path.dirname(__file__)
if _mcp_dir not in sys.path:
    sys.path.insert(0, _mcp_dir)

import entity_server  # noqa: E402
from entity_registry.database import EntityDatabase  # noqa: E402
from entity_registry.test_helpers import bootstrap_test_workspace  # noqa: E402

LEGACY_A = "c5b-ws-a"
LEGACY_B = "c5b-ws-b"
_ALIASES = frozenset({"project_id", "parent_type_id"})


@pytest.fixture
def registry(monkeypatch):
    """Workspaces A and B; the server runs in B with A's legacy project id."""
    db = EntityDatabase(":memory:")
    ws_a = bootstrap_test_workspace(db, LEGACY_A)
    ws_b = bootstrap_test_workspace(db, LEGACY_B)
    monkeypatch.setattr(entity_server, "_db", db)
    monkeypatch.setattr(entity_server, "_db_unavailable", False)
    monkeypatch.setattr(entity_server, "_workspace_uuid", ws_b)
    monkeypatch.setattr(entity_server, "_project_id", LEGACY_A)
    yield db, ws_a, ws_b
    db.close()


def _run(coroutine):
    return asyncio.run(coroutine)


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


def _counter(db: EntityDatabase, workspace_uuid: str, kind: str) -> int | None:
    row = db._conn.execute(
        "SELECT next_val FROM sequences WHERE workspace_uuid = ? AND entity_type = ?",
        (workspace_uuid, kind),
    ).fetchone()
    return None if row is None else row[0]


def _assert_one_workspace(allocations: list[dict], registrations: list[dict],
                          workspace_uuid: str) -> None:
    """The one resolved value reaches the allocator and the registration, and
    neither carries an alias value."""
    assert len(allocations) == 1 and len(registrations) == 1, (allocations, registrations)
    for arguments in (allocations[0], registrations[0]):
        leaked = sorted(name for name in _ALIASES if arguments.get(name) is not None)
        assert not leaked, f"still passed {leaked}: {arguments}"
        assert arguments.get("workspace_uuid") == workspace_uuid, arguments


def _entity(db: EntityDatabase, entity_uuid: str) -> dict:
    return db.get_entity_by_uuid(entity_uuid)


# ---------------------------------------------------------------------------
# register_entity tool, auto_id
# ---------------------------------------------------------------------------


def test_auto_id_allocates_and_registers_in_the_servers_workspace(registry, monkeypatch):
    db, ws_a, ws_b = registry
    allocations = _record_calls(monkeypatch, db, "next_sequence_value")
    registrations = _record_calls(monkeypatch, db, "register_entity")

    reply = _run(entity_server.register_entity(entity_type="feature", name="Auto Numbered",
                                               auto_id=True))

    assert reply == "Registered: feature:001-auto-numbered"
    _assert_one_workspace(allocations, registrations, ws_b)
    assert _counter(db, ws_b, "feature") is not None
    assert _counter(db, ws_a, "feature") is None
    assert db.get_entity("feature:001-auto-numbered")["workspace_uuid"] == ws_b
    assert _created_label(db, "feature:001-auto-numbered") == LEGACY_B


def test_auto_id_without_a_server_workspace_resolves_the_legacy_id_once(registry, monkeypatch):
    db, ws_a, ws_b = registry
    monkeypatch.setattr(entity_server, "_workspace_uuid", "")
    allocations = _record_calls(monkeypatch, db, "next_sequence_value")
    registrations = _record_calls(monkeypatch, db, "register_entity")

    reply = _run(entity_server.register_entity(entity_type="feature", name="Legacy Numbered",
                                               auto_id=True))

    assert reply == "Registered: feature:001-legacy-numbered"
    _assert_one_workspace(allocations, registrations, ws_a)
    assert _counter(db, ws_b, "feature") is None
    assert db.get_entity("feature:001-legacy-numbered")["workspace_uuid"] == ws_a
    assert _created_label(db, "feature:001-legacy-numbered") == LEGACY_A


def test_auto_id_with_a_stale_server_workspace_returns_the_base_error_and_burns_no_number(
    registry, monkeypatch,
):
    """A server workspace with no workspaces row (the split-brain) is refused
    before allocating. The tool returns the string the pre-C17 build returned
    when its registration refused that workspace; that build had already
    taken a number from the legacy id's workspace (A), which now stays
    untouched."""
    db, ws_a, ws_b = registry
    stale_workspace_uuid = "01900000-0000-7000-8000-00000000dead"
    monkeypatch.setattr(entity_server, "_workspace_uuid", stale_workspace_uuid)
    allocations = _record_calls(monkeypatch, db, "next_sequence_value")

    reply = _run(entity_server.register_entity(entity_type="feature", name="Split Brain",
                                               auto_id=True))

    assert reply == (
        f"Error registering entity: register_entity(): workspace_uuid="
        f"{stale_workspace_uuid!r} not present in the workspaces table — "
        f"workspace.json/DB split-brain detected. Run pd:doctor --fix, then "
        f"restart the session (MCP servers cache the workspace UUID at startup)."
    )
    assert allocations == []
    assert _counter(db, ws_a, "feature") is None
    assert _counter(db, ws_b, "feature") is None
    assert db.get_entity("feature:001-split-brain") is None


# ---------------------------------------------------------------------------
# issue_spawn
# ---------------------------------------------------------------------------


def _parent_feature(db: EntityDatabase, workspace_uuid: str) -> str:
    return db.register_entity("feature", name="Parent", seq=40, slug="parent",
                              status="active", workspace_uuid=workspace_uuid)


def test_issue_spawn_allocates_and_registers_in_the_servers_workspace(registry, monkeypatch):
    db, ws_a, ws_b = registry
    parent_uuid = _parent_feature(db, ws_b)
    allocations = _record_calls(monkeypatch, db, "next_sequence_value")
    registrations = _record_calls(monkeypatch, db, "register_entity")

    reply = json.loads(_run(entity_server.issue_spawn(parent_uuid=parent_uuid, kind="bug",
                                                      summary="Spawned bug")))

    child = _entity(db, reply["uuid"])
    _assert_one_workspace(allocations, registrations, ws_b)
    assert _counter(db, ws_b, "bug") is not None
    assert _counter(db, ws_a, "bug") is None
    assert child["workspace_uuid"] == ws_b
    assert _created_label(db, child["type_id"]) == LEGACY_B


def test_issue_spawn_project_id_argument_resolves_the_workspace_once(registry, monkeypatch):
    """The tool's own deprecated project_id argument, with no workspace from
    the caller or the server: its workspace (A) allocates and holds the row."""
    db, ws_a, ws_b = registry
    monkeypatch.setattr(entity_server, "_workspace_uuid", "")
    monkeypatch.setattr(entity_server, "_project_id", LEGACY_B)
    parent_uuid = _parent_feature(db, ws_a)
    allocations = _record_calls(monkeypatch, db, "next_sequence_value")
    registrations = _record_calls(monkeypatch, db, "register_entity")

    reply = json.loads(_run(entity_server.issue_spawn(parent_uuid=parent_uuid, kind="task",
                                                      summary="Spawned task",
                                                      project_id=LEGACY_A)))

    child = _entity(db, reply["uuid"])
    _assert_one_workspace(allocations, registrations, ws_a)
    assert _counter(db, ws_b, "task") is None
    assert child["workspace_uuid"] == ws_a
    assert _created_label(db, child["type_id"]) == LEGACY_A


# ---------------------------------------------------------------------------
# create_key_result
# ---------------------------------------------------------------------------


def test_create_key_result_allocates_and_registers_in_the_legacy_ids_workspace(
    registry, monkeypatch,
):
    db, ws_a, ws_b = registry
    db.register_entity("objective", name="Objective", seq=1, slug="grow",
                       status="active", workspace_uuid=ws_a)
    allocations = _record_calls(monkeypatch, db, "next_sequence_value")
    registrations = _record_calls(monkeypatch, db, "register_entity")

    reply = json.loads(_run(entity_server.create_key_result(
        parent_ref="objective:001-grow", name="Measured Result", metric_type="binary")))

    assert reply["type_id"] == "key_result:001-measured-result", reply
    _assert_one_workspace(allocations, registrations, ws_a)
    assert _counter(db, ws_b, "key_result") is None
    assert db.get_entity_by_uuid(reply["uuid"])["workspace_uuid"] == ws_a
    assert _created_label(db, reply["type_id"]) == LEGACY_A
