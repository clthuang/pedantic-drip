"""W1.6: ``reconcile_status`` is scoped, and a missing projection isn't drift.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W1 change 6
and its Tests ("Scoped, healthy status").

- **Scoped:** the tool reports the server's workspace only; features that
  only another workspace holds are omitted.
- **Health:** only a feature whose DB state and projection disagree
  (``db_ahead``, ``meta_json_ahead``) makes it unhealthy. A row with no
  projection (``db_only``) or a projection with no row (``meta_json_only``)
  is listed but not counted.

The tool runs with the server's globals set the way its lifespan sets them
for workspace A's checkout; workspace B shares the registry.
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

import workflow_state_server as wss  # noqa: E402
from entity_registry.database import EntityDatabase  # noqa: E402
from entity_registry.test_helpers import bootstrap_test_workspace  # noqa: E402
from workflow_engine.engine import WorkflowStateEngine  # noqa: E402

_LEGACY_A, _LEGACY_B = "w1-6-workspace-a", "w1-6-workspace-b"


@pytest.fixture
def server(tmp_path, monkeypatch):
    """The workflow server's globals for workspace A's checkout."""
    artifacts = tmp_path / "docs"
    (artifacts / "features").mkdir(parents=True)
    db = EntityDatabase(str(tmp_path / "entities.db"))
    ws_a = bootstrap_test_workspace(db, _LEGACY_A)
    ws_b = bootstrap_test_workspace(db, _LEGACY_B)
    for name, value in {
        "_db": db, "_db_unavailable": False,
        "_engine": WorkflowStateEngine(db, str(artifacts)),
        "_artifacts_root": str(artifacts), "_project_id": _LEGACY_A,
        "_workspace_uuid": ws_a,
    }.items():
        monkeypatch.setattr(wss, name, value)
    yield {"db": db, "artifacts": str(artifacts), "A": ws_a, "B": ws_b}
    db.close()


def _feature_with_row(c, workspace, seq, slug, *, status="active", **row):
    """Register a feature and seed its workflow row; return its type_id."""
    db = c["db"]
    entity_uuid = db.register_entity(
        "feature", name=slug, seq=seq, slug=slug, status=status,
        workspace_uuid=workspace,
    )
    type_id = db.get_entity_by_uuid(entity_uuid)["type_id"]
    db.create_workflow_phase(type_id, workspace_uuid=workspace, **row)
    return type_id


def _project(c, type_id, **meta) -> None:
    """Write the feature's projection into A's checkout."""
    entity_id = c["db"].get_entity(type_id)["entity_id"]
    feature_dir = os.path.join(c["artifacts"], "features", entity_id)
    os.makedirs(feature_dir)
    with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
        json.dump(meta, f)


def _status(summary_only=False) -> dict:
    return json.loads(asyncio.run(wss.reconcile_status(summary_only=summary_only)))


def _reports(out) -> dict:
    return {
        report["feature_type_id"]: report["status"]
        for report in out["workflow_drift"]["features"]
    }


def test_reconcile_status_omits_features_only_another_workspace_holds(server):
    c = server
    mine = _feature_with_row(
        c, c["A"], 1, "mine", workflow_phase="specify",
        last_completed_phase="brainstorm", kanban_column="backlog",
        mode="standard",
    )
    _project(c, mine, status="active", mode="standard",
             lastCompletedPhase="brainstorm")
    theirs = _feature_with_row(
        c, c["B"], 2, "theirs", workflow_phase="design",
        last_completed_phase="specify", kanban_column="prioritised",
        mode="standard",
    )

    out = _status()

    reports = _reports(out)
    assert theirs not in reports, reports
    assert reports == {mine: "in_sync"}, reports
    assert out["healthy"] is True, out


def test_completed_row_without_a_projection_is_listed_and_healthy(server):
    """A completed feature's row with no ``.meta.json`` (a fresh clone: the
    file is gitignored) is ``db_only``: listed, but the status is healthy."""
    c = server
    done = _feature_with_row(
        c, c["A"], 3, "done", status="completed", workflow_phase="finish",
        last_completed_phase="finish", kanban_column="completed",
        mode="standard",
    )

    out = _status()
    summary = _status(summary_only=True)

    assert _reports(out) == {done: "db_only"}
    assert out["healthy"] is True, out
    assert summary["healthy"] is True, summary
    assert summary["workflow_drift_count"] == 0, summary


def test_only_a_disagreement_counts_toward_health(server):
    """A ``db_only`` row beside a projection that is ahead of its row: the
    status is unhealthy, and only the disagreement is counted."""
    c = server
    _feature_with_row(
        c, c["A"], 4, "unprojected", status="completed",
        workflow_phase="finish", last_completed_phase="finish",
        kanban_column="completed", mode="standard",
    )
    behind = _feature_with_row(
        c, c["A"], 5, "behind", workflow_phase="specify",
        last_completed_phase="brainstorm", kanban_column="backlog",
        mode="standard",
    )
    _project(c, behind, status="active", mode="standard",
             lastCompletedPhase="design")

    out = _status()
    summary = _status(summary_only=True)

    assert sorted(_reports(out).values()) == ["db_only", "meta_json_ahead"]
    assert out["healthy"] is False, out
    assert summary == {
        "healthy": False,
        "workflow_drift_count": 1,
        "frontmatter_drift_count": summary["frontmatter_drift_count"],
    }, summary
