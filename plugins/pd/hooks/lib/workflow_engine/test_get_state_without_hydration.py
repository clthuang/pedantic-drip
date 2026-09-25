"""W1.5: reading a row-less feature answers not-found and writes nothing.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W1 change 5
and its Tests ("No hydration write"). The registry is the only source of a
feature's workflow row: activation seeds it, the startup backfill seeds the
rest. A ``.meta.json`` in the checkout is a projection of that row, so a
healthy registry with no row answers "not found" and never reads the
projection back in.

Every test holds a registered, active feature with no ``workflow_phases`` row
and a readable ``.meta.json`` in the checkout: exactly the case the removed
lazy hydration turned into a new row.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

from entity_registry.database import EntityDatabase
from entity_registry.test_helpers import bootstrap_test_workspace
from workflow_engine.engine import WorkflowStateEngine

_MCP_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp")
)
if _MCP_DIR not in sys.path:
    sys.path.insert(0, _MCP_DIR)

import workflow_state_server as wss  # noqa: E402

_LEGACY_ID = "w1-5-no-hydration"


@pytest.fixture
def rowless_feature(tmp_path):
    """A registered, active feature with a ``.meta.json`` and no row."""
    artifacts = tmp_path / "docs"
    db = EntityDatabase(str(tmp_path / "entities.db"))
    workspace = bootstrap_test_workspace(db, _LEGACY_ID)
    entity_uuid = db.register_entity(
        "feature", name="rowless", seq=1, slug="rowless", status="active",
        workspace_uuid=workspace,
    )
    entity = db.get_entity_by_uuid(entity_uuid)
    feature_dir = artifacts / "features" / entity["entity_id"]
    feature_dir.mkdir(parents=True)
    (feature_dir / ".meta.json").write_text(json.dumps({
        "id": "001", "slug": "rowless", "status": "active",
        "mode": "standard", "lastCompletedPhase": "specify",
    }))
    assert db.get_workflow_phase(entity["type_id"]) is None
    yield {
        "db": db, "artifacts": str(artifacts), "workspace": workspace,
        "type_id": entity["type_id"], "entity": entity,
    }
    db.close()


def _entity_row(feature) -> dict:
    return dict(feature["db"].get_entity(feature["type_id"]))


def test_get_state_answers_none_and_writes_no_row(rowless_feature):
    feature = rowless_feature
    engine = WorkflowStateEngine(feature["db"], feature["artifacts"])
    entity_before = _entity_row(feature)

    assert engine.get_state(feature["type_id"]) is None

    assert feature["db"].get_workflow_phase(feature["type_id"]) is None
    assert _entity_row(feature) == entity_before


def test_transition_phase_answers_feature_not_found_and_writes_no_row(
    rowless_feature,
):
    feature = rowless_feature
    engine = WorkflowStateEngine(feature["db"], feature["artifacts"])

    with pytest.raises(ValueError, match="Feature not found"):
        engine.transition_phase(
            feature["type_id"], "design", workspace_uuid=feature["workspace"],
        )

    assert feature["db"].get_workflow_phase(feature["type_id"]) is None


def test_get_phase_tool_answers_feature_not_found_and_writes_no_row(
    rowless_feature, monkeypatch,
):
    """The ``get_phase`` MCP tool, with the server's globals set the way its
    lifespan sets them for this checkout."""
    feature = rowless_feature
    db = feature["db"]
    engine = WorkflowStateEngine(db, feature["artifacts"])
    for name, value in {
        "_db": db, "_db_unavailable": False, "_engine": engine,
        "_artifacts_root": feature["artifacts"], "_project_id": _LEGACY_ID,
        "_workspace_uuid": feature["workspace"],
    }.items():
        monkeypatch.setattr(wss, name, value)

    answer = json.loads(asyncio.run(
        wss.get_phase(feature_type_id=feature["type_id"])
    ))

    assert answer["error"] is True, answer
    assert answer["error_type"] == "feature_not_found", answer
    assert db.get_workflow_phase(feature["type_id"]) is None
