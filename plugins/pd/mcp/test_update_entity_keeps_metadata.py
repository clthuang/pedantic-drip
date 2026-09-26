"""``update_entity`` leaves an entity's metadata alone when the call passes none.

The tool handed ``parse_metadata(None)``, which is ``{}``, to
``EntityDatabase.update_entity``, and that method reads ``{}`` as "clear".
So every call without ``metadata`` set the entity's metadata to NULL:

- the archive manifest's recipe, ``update_entity(type_id=..., archived=true)``
  and its ``archived=false`` restore (``docs/entity-archive-manifest.md``);
- ``/pd:cleanup-brainstorms``' archive, the same call;
- ``/pd:abandon-feature``'s ``update_entity(type_id=..., status="abandoned")``.

Omitted now means unchanged, as it does for the tool's other fields. An
explicit ``{}`` still clears.

The tool runs with the server's globals set the way its lifespan sets them.
"""
from __future__ import annotations

import asyncio
import json
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

_LEGACY_PROJECT_ID = "keeps-metadata-workspace"
_BRAINSTORM_ID = "20260926-120000-kept"
_TYPE_ID = f"brainstorm:{_BRAINSTORM_ID}"
_METADATA = {"description": "what the brainstorm is about", "source": "session"}


@pytest.fixture
def server(tmp_path, monkeypatch):
    """The entity server's globals for one workspace, and the brainstorm
    ``brainstorm:20260926-120000-kept`` registered there with metadata."""
    db = EntityDatabase(str(tmp_path / "entities.db"))
    workspace_uuid = bootstrap_test_workspace(db, _LEGACY_PROJECT_ID)
    entity_uuid = db.register_entity(
        "brainstorm", name="kept", display_id=_BRAINSTORM_ID,
        artifact_path=f"docs/brainstorms/{_BRAINSTORM_ID}.prd.md",
        status="active", workspace_uuid=workspace_uuid, metadata=_METADATA,
    )
    for name, value in {
        "_db": db, "_db_unavailable": False, "_project_id": _LEGACY_PROJECT_ID,
        "_workspace_uuid": workspace_uuid,
    }.items():
        monkeypatch.setattr(entity_server, name, value)
    yield {"db": db, "uuid": entity_uuid}
    db.close()


def _update(**kwargs) -> str:
    return asyncio.run(entity_server.update_entity(type_id=_TYPE_ID, **kwargs))


def _row(c) -> dict:
    row = c["db"].get_entity_by_uuid(c["uuid"])
    metadata = json.loads(row["metadata"]) if row["metadata"] else None
    return {"status": row["status"], "is_archived": row["is_archived"], "metadata": metadata}


def test_the_archive_recipe_and_its_restore_keep_the_metadata(server):
    assert _update(archived=True) == f"Updated: {_TYPE_ID}"
    assert _row(server) == {"status": "active", "is_archived": 1, "metadata": _METADATA}

    assert _update(archived=False) == f"Updated: {_TYPE_ID}"
    assert _row(server) == {"status": "active", "is_archived": 0, "metadata": _METADATA}


def test_a_status_update_keeps_the_metadata_and_an_explicit_empty_dict_clears_it(server):
    assert _update(status="abandoned") == f"Updated: {_TYPE_ID}"
    assert _row(server) == {"status": "abandoned", "is_archived": 0, "metadata": _METADATA}

    assert _update(metadata={}) == f"Updated: {_TYPE_ID}"
    assert _row(server)["metadata"] is None
