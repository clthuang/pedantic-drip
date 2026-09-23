"""Feature 134 NFR-4 trust-gate tests — #056 native-list params at the tool layer.

The transport JSON-parses string args shaped like JSON back into lists, so the
async tool boundary must accept native lists (backlog #056). These tests call
the ASYNC tools (not the _process helpers) because the normalization lives at
that boundary.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "hooks", "lib"
    ),
)

import workflow_state_server as wss  # noqa: E402
from entity_registry.database import EntityDatabase  # noqa: E402
from workflow_engine.engine import WorkflowStateEngine  # noqa: E402
from test_workflow_state_server import _bootstrap_test_workspace  # noqa: E402


@pytest.fixture()
def tool_env(tmp_path, monkeypatch):
    """Point the module globals at a temp DB the way server startup does."""
    db = EntityDatabase(str(tmp_path / "entities.db"))
    ws_uuid = _bootstrap_test_workspace(db, "P-134")
    db.register_entity(
        "feature", name="T", seq=134, slug="t", status="active", project_id="P-134",
        workspace_uuid=ws_uuid,
    )
    db.create_workflow_phase(
        "feature:134-t", workflow_phase="brainstorm",
        last_completed_phase=None, mode="standard",
    )
    engine = WorkflowStateEngine(db, str(tmp_path))
    monkeypatch.setattr(wss, "_db", db)
    monkeypatch.setattr(wss, "_engine", engine)
    monkeypatch.setattr(wss, "_entity_engine", None)
    monkeypatch.setattr(wss, "_workspace_uuid", ws_uuid)
    yield db
    db.close()


def test_transition_tool_accepts_native_list_skipped_phases(tool_env):
    """#056: a native list produces one skipped row PER PHASE NAME (the
    double-encoded string form produced one row per CHARACTER — QA132-A)."""
    db = tool_env
    result = json.loads(asyncio.run(wss.transition_phase(
        feature_type_id="feature:134-t",
        target_phase="implement",
        yolo_active=True,
        skipped_phases=["specify", "design", "create-plan"],
    )))
    assert result.get("transitioned") is True, result
    rows = [
        r for r in db.query_phase_events(type_id="feature:134-t")
        if r["event_type"] == "skipped"
    ]
    assert sorted(r["phase"] for r in rows) == [
        "create-plan", "design", "specify",
    ], rows
    # Feature 134 QA blocker pin: the phase actually ADVANCES to the target —
    # transitioned=true + skipped rows alone were vacuously green while
    # last-skipped-wins projection left workflow_phase at 'create-plan'.
    row = db.get_workflow_phase("feature:134-t")
    assert row["workflow_phase"] == "implement", row


def test_complete_tool_accepts_native_list_reviewer_notes(tool_env):
    """#056: a native reviewer_notes list round-trips into the completed
    event's reviewer_notes column."""
    db = tool_env
    notes = ["blocker: none", "warning: naming"]
    result = json.loads(asyncio.run(wss.complete_phase(
        feature_type_id="feature:134-t",
        phase="brainstorm",
        iterations=1,
        reviewer_notes=notes,
    )))
    assert "error" not in result, result
    rows = [
        r for r in db.query_phase_events(
            type_id="feature:134-t", phase="brainstorm", event_type="completed",
        )
    ]
    assert len(rows) == 1, rows
    assert json.loads(rows[0]["reviewer_notes"]) == notes


def test_entity_vanish_after_completion_rolls_back(tool_env, monkeypatch):
    """qa-server H1 pin: if the post-completion entity read comes back None,
    the whole completion ROLLS BACK (raise, not return — a return would exit
    the transaction CM normally and COMMIT engine state with no event)."""
    db = tool_env
    real_get = db.get_entity
    calls = {"n": 0}

    def vanishing_get(type_id, *a, **k):
        calls["n"] += 1
        # Vanish on every read: the in-transaction post-completion timing
        # read (the H1 site) then gets None and must raise/roll back.
        if calls["n"] >= 1:
            return None
        return real_get(type_id, *a, **k)

    monkeypatch.setattr(db, "get_entity", vanishing_get)
    result = json.loads(asyncio.run(wss.complete_phase(
        feature_type_id="feature:134-t", phase="brainstorm", iterations=1,
    )))
    monkeypatch.undo()

    assert result.get("error"), result
    # Rollback proof (true only on the raise path): no completed event,
    # and last_completed_phase did not advance.
    rows = db.query_phase_events(
        type_id="feature:134-t", phase="brainstorm", event_type="completed",
    )
    assert rows == [], rows
    wp = db.get_workflow_phase("feature:134-t")
    assert wp.get("last_completed_phase") in (None, ""), wp


def test_mini_spec_record_and_get_round_trip(tool_env):
    """qa-prose B2: the express audit minimum is reachable over MCP."""
    db = tool_env
    rec = json.loads(asyncio.run(wss.record_mini_spec(
        feature_type_id="feature:134-t", text="fix the thing; verify with pytest -k thing",
    )))
    assert rec.get("recorded") is True, rec
    got = json.loads(asyncio.run(wss.get_mini_spec(feature_type_id="feature:134-t")))
    assert got.get("text") == "fix the thing; verify with pytest -k thing", got


def test_get_mini_spec_not_found(tool_env):
    got = json.loads(asyncio.run(wss.get_mini_spec(feature_type_id="feature:134-t")))
    assert got.get("error_type") == "mini_spec_not_found", got


def test_record_mini_spec_rejects_blank(tool_env):
    rec = json.loads(asyncio.run(wss.record_mini_spec(
        feature_type_id="feature:134-t", text="   ",
    )))
    assert rec.get("error_type") == "invalid_input", rec


def test_express_completeness_expects_only_retro(tool_env, tmp_path):
    """qa-prose B5: a recorded mini_spec means shape/plan are not expected —
    only retro.md — so express finish is not drowned in artifact warnings."""
    db = tool_env
    feat_dir = tmp_path / "features" / "134-t"
    feat_dir.mkdir(parents=True)
    db.update_entity("feature:134-t", artifact_path=str(feat_dir))
    asyncio.run(wss.record_mini_spec(feature_type_id="feature:134-t", text="t"))
    warnings = wss._check_artifact_completeness(db, "feature:134-t")
    assert warnings and all("retro.md" in w for w in warnings), warnings
    assert not any("shape.md" in w or "plan.md" in w for w in warnings), warnings
