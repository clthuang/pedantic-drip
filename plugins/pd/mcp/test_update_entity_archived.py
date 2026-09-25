"""W1.2: ``update_entity(archived=...)`` archives explicitly.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W1 change 2
and its Tests ("Explicit brainstorm archive"). Session start no longer
archives a brainstorm whose ``.prd.md`` is missing; ``/pd:cleanup-brainstorms``
archives it through this parameter instead, which sets the archive flag of
the entity the tool resolved, by its uuid:

- ``archived=True`` sets ``is_archived``;
- ``archived=False`` clears it;
- omitted, the flag is left as it is.

The tool runs with the server's globals set the way its lifespan sets them
for workspace A; workspace B shares the registry.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

_MCP_DIR = os.path.dirname(os.path.abspath(__file__))
_HOOKS_LIB = os.path.normpath(os.path.join(_MCP_DIR, "..", "hooks", "lib"))
for _path in (_HOOKS_LIB, _MCP_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import entity_server  # noqa: E402
from entity_registry.database import EntityDatabase  # noqa: E402
from entity_registry.test_helpers import bootstrap_test_workspace  # noqa: E402

_LEGACY_A, _LEGACY_B = "w1-2-workspace-a", "w1-2-workspace-b"
_BRAINSTORM_ID = "20260925-120000-scratch"
_TYPE_ID = f"brainstorm:{_BRAINSTORM_ID}"


@pytest.fixture
def server(tmp_path, monkeypatch):
    """The entity server's globals for workspace A, and the brainstorm
    ``brainstorm:20260925-120000-scratch`` registered in both workspaces."""
    db = EntityDatabase(str(tmp_path / "entities.db"))
    ws_a = bootstrap_test_workspace(db, _LEGACY_A)
    ws_b = bootstrap_test_workspace(db, _LEGACY_B)
    uuids = {}
    for workspace in (ws_a, ws_b):
        uuids[workspace] = db.register_entity(
            "brainstorm", name="scratch", display_id=_BRAINSTORM_ID,
            artifact_path=f"docs/brainstorms/{_BRAINSTORM_ID}.prd.md",
            status="active", workspace_uuid=workspace,
        )
    for name, value in {
        "_db": db, "_db_unavailable": False, "_project_id": _LEGACY_A,
        "_workspace_uuid": ws_a,
    }.items():
        monkeypatch.setattr(entity_server, name, value)
    yield {"db": db, "A": uuids[ws_a], "B": uuids[ws_b]}
    db.close()


def _update(**kwargs) -> str:
    return asyncio.run(entity_server.update_entity(type_id=_TYPE_ID, **kwargs))


def _flag(c, which) -> int:
    return c["db"].get_entity_by_uuid(c[which])["is_archived"]


def test_archived_true_sets_the_flag_of_the_sessions_entity(server):
    c = server

    answer = _update(archived=True)

    assert answer == f"Updated: {_TYPE_ID}", answer
    assert _flag(c, "A") == 1
    assert _flag(c, "B") == 0
    assert c["db"].get_entity_by_uuid(c["A"])["status"] == "active"


def test_archived_false_clears_the_flag(server):
    c = server
    _update(archived=True)

    answer = _update(archived=False)

    assert answer == f"Updated: {_TYPE_ID}", answer
    assert _flag(c, "A") == 0


def test_omitted_archived_leaves_the_flag(server):
    """An update of another field, with no ``archived``, keeps the flag."""
    c = server
    _update(archived=True)

    answer = _update(name="renamed scratch")

    assert answer == f"Updated: {_TYPE_ID}", answer
    assert c["db"].get_entity_by_uuid(c["A"])["name"] == "renamed scratch"
    assert _flag(c, "A") == 1
