"""W3.4: the entity tools resolve type_id and ref parameters in the caller's
workspace.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W3 change 4
and its Tests, and D5 (feature 129's link rule). Nine tools name an existing
entity: ``set_parent``, ``add_dependency``, ``remove_dependency``,
``add_okr_alignment``, ``create_key_result``, ``update_entity``,
``delete_entity``, ``add_entity_tag`` and ``update_kr_score``. Each one:

- **resolves a type_id or ref only in the server's workspace**
  (``_require_workspace()``, W4.1): a type_id only another workspace holds is
  not found, and one that two workspaces hold names the server's entity;
- **passes an explicit uuid through unchanged:** a uuid names one entity in
  any workspace (D5), so a call that names its entities only by uuid needs no
  workspace;
- **writes by the uuid it resolved,** and names type_ids in its answer;
- **refuses a type_id when no workspace resolves,** with the
  ``workspace_unresolved`` envelope, and writes nothing.

The tools run with the entity server's module globals set the way its
lifespan sets them. The server writes in workspace A, and workspace B shares
the registry. The server's legacy project id is empty, or B's (a second
clone's server can hold a legacy id that another workspace owns). Before W3.4
the tools resolved by that id or, with none, across every workspace, so in
both cases they acted on B's entity.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass

import pytest

_MCP_DIR = os.path.dirname(os.path.abspath(__file__))
_HOOKS_LIB = os.path.normpath(os.path.join(_MCP_DIR, "..", "hooks", "lib"))
for _path in (_HOOKS_LIB, _MCP_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import entity_server  # noqa: E402
from entity_registry.database import EntityDatabase  # noqa: E402
from entity_registry.dependencies import DependencyManager  # noqa: E402
from entity_registry.metadata import parse_metadata  # noqa: E402
from entity_registry.test_helpers import bootstrap_test_workspace  # noqa: E402

_LEGACY_A, _LEGACY_B = "w3-4-workspace-a", "w3-4-workspace-b"

# Held by workspace A only: the server's own entities.
_OWN_FEATURE = "feature:001-own-feature"
_OWN_PROJECT = "project:002-own-project"
_OWN_KEY_RESULT = "key_result:003-own-key-result"
# Held by workspace B only.
_THEIR_FEATURE = "feature:011-their-feature"
_THEIR_PROJECT = "project:012-their-project"
_THEIR_OBJECTIVE = "objective:013-their-objective"
_THEIR_KEY_RESULT = "key_result:014-their-key-result"
# Held by both workspaces, each in a row of its own.
_SHARED_FEATURE = "feature:021-shared-feature"
_SHARED_BLOCKER = "feature:022-shared-blocker"
_SHARED_PROJECT = "project:023-shared-project"
_SHARED_OBJECTIVE = "objective:024-shared-objective"
_SHARED_KEY_RESULT = "key_result:025-shared-key-result"
_SHARED = (
    _SHARED_FEATURE, _SHARED_BLOCKER, _SHARED_PROJECT, _SHARED_OBJECTIVE,
    _SHARED_KEY_RESULT,
)
_HELD_BY = {
    "A": (_OWN_FEATURE, _OWN_PROJECT, _OWN_KEY_RESULT, *_SHARED),
    "B": (
        _THEIR_FEATURE, _THEIR_PROJECT, _THEIR_OBJECTIVE, _THEIR_KEY_RESULT,
        *_SHARED,
    ),
}

# The workspace_unresolved envelope's hint names the server to restart (W4.1).
_ENTITY_SERVER_HINT = (
    "restart the pd entity-registry MCP server from the repository root, "
    "or create .claude/ there"
)
_TAG = "w3-4"
_NEW_NAME = "renamed by W3.4"
_SCORE = 0.5


# ---------------------------------------------------------------------------
# The registry and the server
# ---------------------------------------------------------------------------


@dataclass
class Registry:
    """A temp registry holding workspaces A and B and their entities."""

    db: EntityDatabase
    path: str
    workspaces: dict[str, str]
    """``"A"`` / ``"B"`` -> workspace uuid."""
    uuids: dict[tuple[str, str], str]
    """(``"A"`` / ``"B"``, type_id) -> entity uuid."""

    def uuid(self, workspace: str, type_id: str) -> str:
        return self.uuids[(workspace, type_id)]

    def entity(self, workspace: str, type_id: str) -> dict:
        return self.db.get_entity_by_uuid(
            self.uuid(workspace, type_id), include_deleted=True,
        )

    def b_identifiers(self) -> set[str]:
        """B's workspace uuid and the uuid of every entity B holds."""
        return {self.workspaces["B"]} | {
            uuid for (workspace, _), uuid in self.uuids.items() if workspace == "B"
        }


def _build_registry(tmp_path) -> Registry:
    """B's rows are registered first. Before W3.4, a ref resolved with no
    workspace took the first row holding its type_id (``resolve_ref``'s exact
    match, deferred with the re-key), so a shared type_id named B's entity."""
    path = str(tmp_path / "entities.db")
    db = EntityDatabase(path)
    workspaces = {
        "B": bootstrap_test_workspace(db, _LEGACY_B),
        "A": bootstrap_test_workspace(db, _LEGACY_A),
    }
    uuids = {}
    for workspace in ("B", "A"):
        for type_id in _HELD_BY[workspace]:
            kind, entity_id = type_id.split(":")
            seq, slug = entity_id.split("-", 1)
            uuids[(workspace, type_id)] = db.register_entity(
                kind, name=slug, seq=int(seq), slug=slug,
                workspace_uuid=workspaces[workspace],
            )
    return Registry(db, path, workspaces, uuids)


def _set_server_globals(monkeypatch, db, *, workspace_uuid: str, project_id: str) -> None:
    """The entity server's module globals, as its lifespan sets them. No
    project root: ``_require_workspace()`` answers from ``_workspace_uuid``,
    or from nothing at all."""
    for name, value in {
        "_db": db, "_db_unavailable": False, "_project_root": "",
        "_project_id": project_id, "_workspace_uuid": workspace_uuid,
    }.items():
        monkeypatch.setattr(entity_server, name, value)


@pytest.fixture(
    params=["", _LEGACY_B], ids=["no legacy project id", "B's legacy project id"],
)
def server_in_a(request, tmp_path, monkeypatch):
    """The server writes in workspace A."""
    registry = _build_registry(tmp_path)
    _set_server_globals(
        monkeypatch, registry.db,
        workspace_uuid=registry.workspaces["A"], project_id=request.param,
    )
    yield registry
    registry.db.close()


@pytest.fixture(
    params=["", "__unknown__"],
    ids=["no legacy project id", "the __unknown__ legacy project id"],
)
def server_without_workspace(request, tmp_path, monkeypatch):
    """No workspace resolves: there is no project root to retry the startup
    resolution with, and the lookup skips the legacy id (W4.1)."""
    registry = _build_registry(tmp_path)
    _set_server_globals(
        monkeypatch, registry.db, workspace_uuid="", project_id=request.param,
    )
    yield registry
    registry.db.close()


def _run(coroutine) -> str:
    return asyncio.run(coroutine)


def _as_json(answer: str):
    """The answer parsed as JSON, or the answer itself when it is not JSON,
    so a check comparing it fails as an assertion that shows the answer."""
    try:
        return json.loads(answer)
    except json.JSONDecodeError:
        return answer


def _snapshot(path: str) -> dict[str, list[tuple]]:
    """Every row of every table, read through a connection of its own."""
    with contextlib.closing(sqlite3.connect(path)) as registry:
        tables = [row[0] for row in registry.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )]
        return {
            table: sorted(
                registry.execute(f'SELECT * FROM "{table}"').fetchall(), key=repr,
            )
            for table in tables
        }


def _rows_naming(snapshot: dict[str, list[tuple]], identifiers: set[str]) -> dict:
    """The rows holding any of ``identifiers`` in one of their columns."""
    return {
        table: [row for row in rows if any(value in identifiers for value in row)]
        for table, rows in snapshot.items()
    }


def _nothing(registry: Registry) -> None:
    """No arrangement beyond the registry itself."""


def _block(registry: Registry, blocked: tuple[str, str], blocker: tuple[str, str]) -> None:
    """``blocked`` is blocked by ``blocker``: each a (workspace, type_id)
    pair, linked by uuid the way feature 129 links across workspaces."""
    DependencyManager().add_dependency(
        registry.db, registry.uuid(*blocked), registry.uuid(*blocker),
    )


def _dependency_count(registry: Registry, blocked: tuple[str, str], blocker: tuple[str, str]) -> int:
    return len(registry.db.query_dependencies(
        entity_uuid=registry.uuid(*blocked),
        blocked_by_uuid=registry.uuid(*blocker),
    ))


# ---------------------------------------------------------------------------
# A type_id only another workspace holds
# ---------------------------------------------------------------------------

# Every entity parameter of every W3.4 tool in turn, given a type_id only B
# holds, the others naming A's own entities. Each value is (B's type_id,
# arrange, call): arrange prepares the registry, and call takes it and returns
# the tool's coroutine.
_CALLS_NAMING_THEIR_TYPE_ID = {
    "set_parent type_id": (_THEIR_FEATURE, _nothing, lambda r: entity_server.set_parent(
        type_id=_THEIR_FEATURE, parent_type_id=_OWN_PROJECT)),
    "set_parent parent_type_id": (_THEIR_PROJECT, _nothing, lambda r: entity_server.set_parent(
        type_id=_OWN_FEATURE, parent_type_id=_THEIR_PROJECT)),
    "set_parent ref": (_THEIR_FEATURE, _nothing, lambda r: entity_server.set_parent(
        ref=_THEIR_FEATURE, parent_type_id=_OWN_PROJECT)),
    "set_parent parent_ref": (_THEIR_PROJECT, _nothing, lambda r: entity_server.set_parent(
        type_id=_OWN_FEATURE, parent_ref=_THEIR_PROJECT)),
    "update_entity type_id": (_THEIR_FEATURE, _nothing, lambda r: entity_server.update_entity(
        type_id=_THEIR_FEATURE, name=_NEW_NAME)),
    "update_entity ref": (_THEIR_FEATURE, _nothing, lambda r: entity_server.update_entity(
        ref=_THEIR_FEATURE, name=_NEW_NAME)),
    "delete_entity type_id": (_THEIR_FEATURE, _nothing, lambda r: entity_server.delete_entity(
        type_id=_THEIR_FEATURE)),
    "delete_entity ref": (_THEIR_FEATURE, _nothing, lambda r: entity_server.delete_entity(
        ref=_THEIR_FEATURE)),
    "add_entity_tag type_id": (_THEIR_FEATURE, _nothing, lambda r: entity_server.add_entity_tag(
        type_id=_THEIR_FEATURE, tag=_TAG)),
    "add_entity_tag ref": (_THEIR_FEATURE, _nothing, lambda r: entity_server.add_entity_tag(
        ref=_THEIR_FEATURE, tag=_TAG)),
    "add_dependency entity_ref": (_THEIR_FEATURE, _nothing, lambda r: entity_server.add_dependency(
        entity_ref=_THEIR_FEATURE, blocked_by_ref=_OWN_FEATURE)),
    "add_dependency blocked_by_ref": (_THEIR_FEATURE, _nothing, lambda r: entity_server.add_dependency(
        entity_ref=_OWN_FEATURE, blocked_by_ref=_THEIR_FEATURE)),
    "remove_dependency entity_ref": (
        _THEIR_FEATURE,
        lambda r: _block(r, ("B", _THEIR_FEATURE), ("A", _OWN_FEATURE)),
        lambda r: entity_server.remove_dependency(
            entity_ref=_THEIR_FEATURE, blocked_by_ref=_OWN_FEATURE),
    ),
    "remove_dependency blocked_by_ref": (
        _THEIR_FEATURE,
        lambda r: _block(r, ("A", _OWN_FEATURE), ("B", _THEIR_FEATURE)),
        lambda r: entity_server.remove_dependency(
            entity_ref=_OWN_FEATURE, blocked_by_ref=_THEIR_FEATURE),
    ),
    "add_okr_alignment entity_ref": (_THEIR_FEATURE, _nothing, lambda r: entity_server.add_okr_alignment(
        entity_ref=_THEIR_FEATURE, kr_ref=_OWN_KEY_RESULT)),
    "add_okr_alignment kr_ref": (_THEIR_KEY_RESULT, _nothing, lambda r: entity_server.add_okr_alignment(
        entity_ref=_OWN_FEATURE, kr_ref=_THEIR_KEY_RESULT)),
    "create_key_result parent_ref": (_THEIR_OBJECTIVE, _nothing, lambda r: entity_server.create_key_result(
        parent_ref=_THEIR_OBJECTIVE, name="Measured result", metric_type="binary")),
    "update_kr_score kr_ref": (_THEIR_KEY_RESULT, _nothing, lambda r: entity_server.update_kr_score(
        kr_ref=_THEIR_KEY_RESULT, score=_SCORE)),
}


@pytest.mark.parametrize("case", sorted(_CALLS_NAMING_THEIR_TYPE_ID))
def test_a_type_id_only_another_workspace_holds_is_not_found(server_in_a, case):
    """Design, W3 Tests: from A, a type_id only B holds answers not-found,
    and nothing in the registry changes. Before W3.4 each call acted on B's
    entity: ``set_parent`` linked it, ``update_entity`` updated it, and so
    on for every tool."""
    their_type_id, arrange, call = _CALLS_NAMING_THEIR_TYPE_ID[case]
    registry = server_in_a
    arrange(registry)
    registry_before = _snapshot(registry.path)

    answer = _run(call(registry))

    assert re.search(r"not found|no entity found", answer, re.IGNORECASE), answer
    assert their_type_id in answer, answer
    assert _snapshot(registry.path) == registry_before


# ---------------------------------------------------------------------------
# A type_id both workspaces hold
# ---------------------------------------------------------------------------


def _check_set_parent(registry: Registry, answer: str) -> None:
    assert answer == f"Parent set: {_SHARED_FEATURE} → {_SHARED_PROJECT}", answer
    assert registry.entity("A", _SHARED_FEATURE)["parent_uuid"] == (
        registry.uuid("A", _SHARED_PROJECT)
    )


def _check_update_entity(registry: Registry, answer: str) -> None:
    assert answer == f"Updated: {_SHARED_FEATURE}", answer
    assert registry.entity("A", _SHARED_FEATURE)["name"] == _NEW_NAME


def _check_archived(registry: Registry, answer: str) -> None:
    """``/pd:cleanup-brainstorms`` archives a deleted brainstorm's entity
    this way (W1.2): the caller's namesake only."""
    assert answer == f"Updated: {_SHARED_FEATURE}", answer
    assert registry.entity("A", _SHARED_FEATURE)["is_archived"] == 1


def _check_delete_entity(registry: Registry, answer: str) -> None:
    assert _as_json(answer) == {"result": f"Deleted: {_SHARED_FEATURE}"}, answer
    assert registry.entity("A", _SHARED_FEATURE)["is_deleted"] == 1


def _check_add_entity_tag(registry: Registry, answer: str) -> None:
    assert _as_json(answer) == {"result": f"Tagged {_SHARED_FEATURE} with '{_TAG}'"}, answer
    assert registry.db.get_tags(registry.uuid("A", _SHARED_FEATURE)) == [_TAG]


def _check_add_dependency(registry: Registry, answer: str) -> None:
    assert _as_json(answer) == {
        "result": f"Dependency added: {_SHARED_FEATURE} blocked by {_SHARED_BLOCKER}"
    }, answer
    assert _dependency_count(registry, ("A", _SHARED_FEATURE), ("A", _SHARED_BLOCKER)) == 1


def _arrange_shared_dependencies(registry: Registry) -> None:
    for workspace in ("B", "A"):
        _block(registry, (workspace, _SHARED_FEATURE), (workspace, _SHARED_BLOCKER))


def _check_remove_dependency(registry: Registry, answer: str) -> None:
    assert _as_json(answer) == {
        "result": (
            f"Dependency removed: {_SHARED_FEATURE} no longer blocked by "
            f"{_SHARED_BLOCKER}"
        )
    }, answer
    assert _dependency_count(registry, ("A", _SHARED_FEATURE), ("A", _SHARED_BLOCKER)) == 0


def _check_add_okr_alignment(registry: Registry, answer: str) -> None:
    assert _as_json(answer) == {
        "result": f"Aligned {_SHARED_FEATURE} to {_SHARED_KEY_RESULT}"
    }, answer
    aligned = registry.db.get_okr_alignments(registry.uuid("A", _SHARED_FEATURE))
    assert [key_result["uuid"] for key_result in aligned] == [
        registry.uuid("A", _SHARED_KEY_RESULT)
    ]


def _check_create_key_result(registry: Registry, answer: str) -> None:
    reply = _as_json(answer)
    assert isinstance(reply, dict) and "error" not in reply, answer
    key_result = registry.db.get_entity_by_uuid(reply["uuid"])
    assert key_result["type_id"] == reply["type_id"]
    assert key_result["workspace_uuid"] == registry.workspaces["A"]
    assert key_result["parent_uuid"] == registry.uuid("A", _SHARED_OBJECTIVE)


def _check_update_kr_score(registry: Registry, answer: str) -> None:
    assert _as_json(answer) == {
        "result": f"Score updated to {_SCORE}", "type_id": _SHARED_KEY_RESULT,
    }, answer
    metadata = parse_metadata(registry.entity("A", _SHARED_KEY_RESULT)["metadata"])
    assert metadata["score"] == _SCORE


# Each W3.4 tool, given type_ids both workspaces hold. Each value is
# (arrange, call, check): check asserts the answer names type_ids and that the
# call acted on A's entity.
_CALLS_NAMING_SHARED_TYPE_IDS = {
    "set_parent": (_nothing, lambda r: entity_server.set_parent(
        type_id=_SHARED_FEATURE, parent_type_id=_SHARED_PROJECT), _check_set_parent),
    "update_entity": (_nothing, lambda r: entity_server.update_entity(
        type_id=_SHARED_FEATURE, name=_NEW_NAME), _check_update_entity),
    "update_entity archived": (_nothing, lambda r: entity_server.update_entity(
        type_id=_SHARED_FEATURE, archived=True), _check_archived),
    "delete_entity": (_nothing, lambda r: entity_server.delete_entity(
        type_id=_SHARED_FEATURE), _check_delete_entity),
    "add_entity_tag": (_nothing, lambda r: entity_server.add_entity_tag(
        type_id=_SHARED_FEATURE, tag=_TAG), _check_add_entity_tag),
    "add_dependency": (_nothing, lambda r: entity_server.add_dependency(
        entity_ref=_SHARED_FEATURE, blocked_by_ref=_SHARED_BLOCKER), _check_add_dependency),
    "remove_dependency": (_arrange_shared_dependencies, lambda r: entity_server.remove_dependency(
        entity_ref=_SHARED_FEATURE, blocked_by_ref=_SHARED_BLOCKER), _check_remove_dependency),
    "add_okr_alignment": (_nothing, lambda r: entity_server.add_okr_alignment(
        entity_ref=_SHARED_FEATURE, kr_ref=_SHARED_KEY_RESULT), _check_add_okr_alignment),
    "create_key_result": (_nothing, lambda r: entity_server.create_key_result(
        parent_ref=_SHARED_OBJECTIVE, name="Measured result", metric_type="binary"),
        _check_create_key_result),
    "update_kr_score": (_nothing, lambda r: entity_server.update_kr_score(
        kr_ref=_SHARED_KEY_RESULT, score=_SCORE), _check_update_kr_score),
}


@pytest.mark.parametrize("case", sorted(_CALLS_NAMING_SHARED_TYPE_IDS))
def test_a_type_id_both_workspaces_hold_names_the_servers_entity(server_in_a, case):
    """From A, a type_id A and B both hold acts on A's entity only: the
    answer names the type_ids, the change lands on A's uuid, and every row
    naming B's workspace or one of its entities stays byte-identical."""
    arrange, call, check = _CALLS_NAMING_SHARED_TYPE_IDS[case]
    registry = server_in_a
    arrange(registry)
    b_rows_before = _rows_naming(_snapshot(registry.path), registry.b_identifiers())

    answer = _run(call(registry))

    check(registry, answer)
    assert _rows_naming(_snapshot(registry.path), registry.b_identifiers()) == b_rows_before


def test_remove_dependency_clears_an_edge_to_a_deleted_blocker_by_its_type_id(server_in_a):
    """W3.4 changes only the workspace a ref resolves in. The dependency
    tools still match a ref the way ``resolve_ref`` does, so an exact type_id
    names a soft-deleted blocker, whose edge survives the soft delete. From
    A, with the blocker's type_id held by both workspaces and A's blocker
    deleted, the call clears A's edge only. Before W3.4 it resolved B's live
    blocker and cleared B's edge."""
    registry = server_in_a
    _arrange_shared_dependencies(registry)
    registry.db.delete_entity(registry.uuid("A", _SHARED_BLOCKER))
    b_rows_before = _rows_naming(_snapshot(registry.path), registry.b_identifiers())

    answer = _run(entity_server.remove_dependency(
        entity_ref=_SHARED_FEATURE, blocked_by_ref=_SHARED_BLOCKER,
    ))

    _check_remove_dependency(registry, answer)
    assert _rows_naming(_snapshot(registry.path), registry.b_identifiers()) == b_rows_before


# ---------------------------------------------------------------------------
# An explicit uuid
# ---------------------------------------------------------------------------


def test_set_parent_by_another_workspaces_uuid_still_links(server_in_a):
    """Keep-green (design, W3 Tests: passes on the base too). D5 keeps
    feature 129's rule: an explicit uuid may point to another workspace."""
    registry = server_in_a

    answer = _run(entity_server.set_parent(
        type_id=_OWN_FEATURE, parent_ref=registry.uuid("B", _THEIR_PROJECT),
    ))

    assert answer == f"Parent set: {_OWN_FEATURE} → {_THEIR_PROJECT}", answer
    assert registry.entity("A", _OWN_FEATURE)["parent_uuid"] == (
        registry.uuid("B", _THEIR_PROJECT)
    )


def _check_linked_by_uuid(registry: Registry, answer: str) -> None:
    assert answer == f"Parent set: {_OWN_FEATURE} → {_THEIR_PROJECT}", answer
    assert registry.entity("A", _OWN_FEATURE)["parent_uuid"] == (
        registry.uuid("B", _THEIR_PROJECT)
    )


def _check_updated_by_uuid(registry: Registry, answer: str) -> None:
    assert answer == f"Updated: {_THEIR_FEATURE}", answer
    assert registry.entity("B", _THEIR_FEATURE)["name"] == _NEW_NAME


def _check_deleted_by_uuid(registry: Registry, answer: str) -> None:
    assert _as_json(answer) == {"result": f"Deleted: {_OWN_FEATURE}"}, answer
    assert registry.entity("A", _OWN_FEATURE)["is_deleted"] == 1


def _check_tagged_by_uuid(registry: Registry, answer: str) -> None:
    assert _as_json(answer) == {"result": f"Tagged {_OWN_FEATURE} with '{_TAG}'"}, answer
    assert registry.db.get_tags(registry.uuid("A", _OWN_FEATURE)) == [_TAG]


def _check_dependency_added_by_uuid(registry: Registry, answer: str) -> None:
    assert _as_json(answer) == {
        "result": f"Dependency added: {_OWN_FEATURE} blocked by {_THEIR_FEATURE}"
    }, answer
    assert _dependency_count(registry, ("A", _OWN_FEATURE), ("B", _THEIR_FEATURE)) == 1


def _check_dependency_removed_by_uuid(registry: Registry, answer: str) -> None:
    assert _as_json(answer) == {
        "result": (
            f"Dependency removed: {_OWN_FEATURE} no longer blocked by "
            f"{_THEIR_FEATURE}"
        )
    }, answer
    assert _dependency_count(registry, ("A", _OWN_FEATURE), ("B", _THEIR_FEATURE)) == 0


def _check_aligned_by_uuid(registry: Registry, answer: str) -> None:
    assert _as_json(answer) == {
        "result": f"Aligned {_OWN_FEATURE} to {_THEIR_KEY_RESULT}"
    }, answer
    aligned = registry.db.get_okr_alignments(registry.uuid("A", _OWN_FEATURE))
    assert [key_result["uuid"] for key_result in aligned] == [
        registry.uuid("B", _THEIR_KEY_RESULT)
    ]


# Each W3.4 tool whose answer names its entities, called with uuids only,
# some of them B's. Each value is (arrange, call, check). create_key_result
# registers in the server's workspace, so it needs one whatever it is given;
# update_kr_score already answered with the type_id it resolved.
_CALLS_NAMING_UUIDS_ONLY = {
    "set_parent": (_nothing, lambda r: entity_server.set_parent(
        type_id=r.uuid("A", _OWN_FEATURE),
        parent_type_id=r.uuid("B", _THEIR_PROJECT)), _check_linked_by_uuid),
    "update_entity": (_nothing, lambda r: entity_server.update_entity(
        type_id=r.uuid("B", _THEIR_FEATURE), name=_NEW_NAME), _check_updated_by_uuid),
    "delete_entity": (_nothing, lambda r: entity_server.delete_entity(
        type_id=r.uuid("A", _OWN_FEATURE)), _check_deleted_by_uuid),
    "add_entity_tag": (_nothing, lambda r: entity_server.add_entity_tag(
        type_id=r.uuid("A", _OWN_FEATURE), tag=_TAG), _check_tagged_by_uuid),
    "add_dependency": (_nothing, lambda r: entity_server.add_dependency(
        entity_ref=r.uuid("A", _OWN_FEATURE),
        blocked_by_ref=r.uuid("B", _THEIR_FEATURE)), _check_dependency_added_by_uuid),
    "remove_dependency": (
        lambda r: _block(r, ("A", _OWN_FEATURE), ("B", _THEIR_FEATURE)),
        lambda r: entity_server.remove_dependency(
            entity_ref=r.uuid("A", _OWN_FEATURE),
            blocked_by_ref=r.uuid("B", _THEIR_FEATURE)),
        _check_dependency_removed_by_uuid,
    ),
    "add_okr_alignment": (_nothing, lambda r: entity_server.add_okr_alignment(
        entity_ref=r.uuid("A", _OWN_FEATURE),
        kr_ref=r.uuid("B", _THEIR_KEY_RESULT)), _check_aligned_by_uuid),
}


@pytest.mark.parametrize("case", sorted(_CALLS_NAMING_UUIDS_ONLY))
def test_a_call_naming_only_uuids_needs_no_workspace_and_answers_in_type_ids(
    server_without_workspace, case,
):
    """A uuid names one entity in any workspace (D5), so a call naming its
    entities only by uuid goes ahead with no workspace resolved: it writes
    by those uuids, and its answer names their type_ids. Before W3.4 these
    calls went ahead too, but echoed the uuids they were given."""
    arrange, call, check = _CALLS_NAMING_UUIDS_ONLY[case]
    registry = server_without_workspace
    arrange(registry)

    answer = _run(call(registry))

    check(registry, answer)
    assert entity_server._workspace_uuid == ""


# ---------------------------------------------------------------------------
# No workspace resolves
# ---------------------------------------------------------------------------

# Each W3.4 tool given type_ids, as a session calls it. Each value is
# (arrange, call). create_key_result is not here: task 2A wired it to refuse
# (test_require_workspace.py's write-tool refusal test), since it registers in
# the server's workspace whatever its parent reference is.
_CALLS_NAMING_TYPE_IDS = {
    "set_parent": (_nothing, lambda r: entity_server.set_parent(
        type_id=_OWN_FEATURE, parent_type_id=_OWN_PROJECT)),
    "set_parent, a uuid child and a type_id parent": (
        _nothing,
        lambda r: entity_server.set_parent(
            type_id=r.uuid("A", _OWN_FEATURE), parent_type_id=_OWN_PROJECT),
    ),
    "update_entity": (_nothing, lambda r: entity_server.update_entity(
        type_id=_OWN_FEATURE, name=_NEW_NAME)),
    "delete_entity": (_nothing, lambda r: entity_server.delete_entity(
        type_id=_OWN_FEATURE)),
    "add_entity_tag": (_nothing, lambda r: entity_server.add_entity_tag(
        type_id=_OWN_FEATURE, tag=_TAG)),
    "add_dependency": (_nothing, lambda r: entity_server.add_dependency(
        entity_ref=_OWN_FEATURE, blocked_by_ref=_OWN_PROJECT)),
    "remove_dependency": (
        lambda r: _block(r, ("A", _OWN_FEATURE), ("A", _OWN_PROJECT)),
        lambda r: entity_server.remove_dependency(
            entity_ref=_OWN_FEATURE, blocked_by_ref=_OWN_PROJECT),
    ),
    "add_okr_alignment": (_nothing, lambda r: entity_server.add_okr_alignment(
        entity_ref=_OWN_FEATURE, kr_ref=_OWN_KEY_RESULT)),
    "update_kr_score": (_nothing, lambda r: entity_server.update_kr_score(
        kr_ref=_OWN_KEY_RESULT, score=_SCORE)),
}


@pytest.mark.parametrize("case", sorted(_CALLS_NAMING_TYPE_IDS))
def test_a_type_id_without_a_workspace_is_refused_and_writes_nothing(
    server_without_workspace, case,
):
    """Design, W3 Tests (Unresolved): with no resolvable workspace, a tool
    given a type_id answers ``workspace_unresolved`` and writes nothing, even
    when its other parameter is a uuid. Before W3.4 these tools never asked
    for a workspace."""
    arrange, call = _CALLS_NAMING_TYPE_IDS[case]
    registry = server_without_workspace
    arrange(registry)
    registry_before = _snapshot(registry.path)

    raw_reply = _run(call(registry))

    assert raw_reply.startswith("{"), f"not an error envelope: {raw_reply}"
    reply = json.loads(raw_reply)
    assert reply.get("error_type") == "workspace_unresolved", reply
    assert reply["recovery_hint"] == _ENTITY_SERVER_HINT
    assert _snapshot(registry.path) == registry_before
    assert entity_server._workspace_uuid == ""
