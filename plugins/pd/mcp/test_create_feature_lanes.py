"""W2 lane tests: ``/pd:create-feature`` works from allocation through its
first phase transition, on the deep, express and decomposed paths.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W2 (changes
1, 5 and 7, and its Tests). Before W2:

- ``activate_feature`` seeded no ``workflow_phases`` row, so the first
  ``transition_phase`` answered "Feature not found" (N1);
- the workflow-state skill's activation steps made no directory, so a
  decomposed feature could not be activated (N2).

**How each lane runs.** Both MCP servers start through their real lifespans,
against a temp registry (``ENTITY_DB_PATH``), a temp HOME and a temp git
repo. The lane then calls the MCP tools, which call the real ``_process_*``
functions, in the order of ``commands/create-feature.md`` steps 2-6.

**What every lane checks first.** The seeded row, with its ``workspace_uuid``
and ``uuid``, right after ``activate_feature`` and before any engine read.
Hydration from ``.meta.json`` still exists until W1.5, and could otherwise
supply a row the activation never seeded.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys

import pytest

_MCP_DIR = os.path.dirname(os.path.abspath(__file__))
_HOOKS_LIB = os.path.normpath(os.path.join(_MCP_DIR, "..", "hooks", "lib"))
for _path in (_HOOKS_LIB, _MCP_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import entity_server  # noqa: E402
import server_lifecycle  # noqa: E402
import workflow_state_server as wss  # noqa: E402

_SKILL_PATH = os.path.normpath(
    os.path.join(_MCP_DIR, "..", "skills", "workflow-state", "SKILL.md")
)
_SKILL_MKDIR_STEP = "mkdir -p {pd_artifacts_root}/features/{id}-{slug}/"
_EXPRESS_SKIPPED_PHASES = ["brainstorm", "specify", "design", "create-plan"]

# Each lifespan assigns these module globals; the fixture restores them so
# a lane leaves no server state behind for the rest of the suite.
_ENTITY_SERVER_GLOBALS = (
    "_db", "_db_unavailable", "_recovery_thread", "_config", "_project_root",
    "_artifacts_root", "_project_id", "_git_info", "_workspace_uuid",
)
_WORKFLOW_SERVER_GLOBALS = (
    "_db", "_db_unavailable", "_recovery_thread", "_engine", "_entity_engine",
    "_artifacts_root", "_project_root", "_project_id", "_workspace_uuid",
    "_notification_queue",
)


def run_git(*args: str) -> None:
    """git with a fixed identity, so commits need no user config."""
    subprocess.run(
        ["git", "-c", "user.name=lane", "-c", "user.email=lane@example.invalid",
         *args],
        check=True, capture_output=True,
    )


def make_pd_repo(path) -> None:
    """A git repo with a root commit and a ``.claude/`` directory (a
    pd-enabled project: workspace resolution requires it)."""
    run_git("init", "-q", "-b", "main", str(path))
    run_git("-C", str(path), "commit", "-q", "--allow-empty", "-m", "root")
    (path / ".claude").mkdir()


def isolate_servers(monkeypatch, *, home, db_path, project_root) -> None:
    """Point both servers' lifespans at a temp HOME, a temp registry and
    *project_root*, and restore their module globals afterwards.

    Process-level side effects of the lifespans stay inside the temp HOME:
    the PID files go there, and the parent-PID watchdog is not started (it
    would outlive the test and ``os._exit`` the whole run if pytest were
    re-parented).
    """
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ENTITY_DB_PATH", str(db_path))
    monkeypatch.setenv("PROJECT_ROOT", str(project_root))
    monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
    monkeypatch.delenv("WORKSPACE_UUID", raising=False)
    monkeypatch.setattr(
        server_lifecycle, "PID_DIR", home / ".claude" / "pd" / "run"
    )
    for module, names in (
        (entity_server, _ENTITY_SERVER_GLOBALS),
        (wss, _WORKFLOW_SERVER_GLOBALS),
    ):
        monkeypatch.setattr(module, "start_parent_watchdog", lambda: None)
        for name in names:
            monkeypatch.setattr(module, name, getattr(module, name))


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A temp pd repo, a temp HOME and a temp registry for both servers."""
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    make_pd_repo(repo)
    (repo / "docs" / "features").mkdir(parents=True)
    db_path = tmp_path / "registry" / "entities.db"
    isolate_servers(monkeypatch, home=home, db_path=db_path, project_root=repo)
    return {
        "artifacts_root": str(repo / "docs"),
        "db_path": str(db_path),
    }


def _run_with_servers(scenario):
    """Start both servers through their lifespans, run *scenario*, stop them."""
    async def main():
        async with entity_server.lifespan(None), wss.lifespan(None):
            assert wss._workspace_uuid, "the workflow server resolved no workspace"
            assert wss._workspace_uuid == entity_server._workspace_uuid
            await scenario()

    asyncio.run(main())


async def _allocate_and_register(checkout, description, *, make_directory):
    """create-feature.md steps 2-4: allocate, mkdir, register (no artifact_path).

    Returns ``(type_id, feature_directory)``.
    """
    allocation = json.loads(await entity_server.allocate_entity_id(
        entity_type="feature", name=description,
    ))
    assert "entity_id" in allocation, allocation
    feature_directory = os.path.join(
        checkout["artifacts_root"], "features", allocation["entity_id"]
    )
    if make_directory:
        os.makedirs(feature_directory, exist_ok=True)
    reply = await entity_server.register_entity(
        entity_type="feature", seq=allocation["seq"], slug=allocation["slug"],
        name=description, status="planned",
    )
    type_id = "feature:" + allocation["entity_id"]
    entity = wss._db.get_entity(type_id)
    assert entity is not None, reply
    assert entity["artifact_path"] is None
    return type_id, feature_directory


async def _activate(type_id):
    activation = json.loads(await wss.activate_feature(feature_type_id=type_id))
    assert activation.get("activated") is True, activation
    return activation


def _committed_row_count(checkout, type_id):
    """The type_id's workflow_phases rows another connection sees: committed
    rows only."""
    other = sqlite3.connect(checkout["db_path"])
    try:
        return other.execute(
            "SELECT COUNT(*) FROM workflow_phases WHERE type_id = ?", (type_id,),
        ).fetchone()[0]
    finally:
        other.close()


def _assert_seeded_row(type_id):
    """The row activation seeded: this server's workspace, the entity's uuid,
    no phase yet, and the planned-to-active kanban column. A plain registry
    read: no engine call, so no hydration can have written it."""
    row = wss._db.get_workflow_phase(type_id)
    assert row is not None, f"activate_feature seeded no workflow_phases row for {type_id}"
    entity = wss._db.get_entity(type_id)
    assert row["workspace_uuid"] == wss._workspace_uuid
    assert row["uuid"] == entity["uuid"]
    assert row["workflow_phase"] is None
    assert row["kanban_column"] == "backlog"


def test_deep_lane_reaches_specify(checkout):
    async def scenario():
        type_id, _ = await _allocate_and_register(
            checkout, "deep lane thing", make_directory=True,
        )
        await _activate(type_id)
        _assert_seeded_row(type_id)

        transition = json.loads(await wss.transition_phase(
            feature_type_id=type_id, target_phase="specify",
        ))
        assert transition.get("transitioned") is True, transition
        assert wss._db.get_workflow_phase(type_id)["workflow_phase"] == "specify"

    _run_with_servers(scenario)


def test_express_lane_reaches_implement(checkout):
    async def scenario():
        type_id, _ = await _allocate_and_register(
            checkout, "express lane thing", make_directory=True,
        )
        await _activate(type_id)
        _assert_seeded_row(type_id)

        recorded = json.loads(await wss.record_mini_spec(
            feature_type_id=type_id, text="do x; verify y",
        ))
        assert recorded.get("recorded") is True, recorded
        transition = json.loads(await wss.transition_phase(
            feature_type_id=type_id, target_phase="implement",
            skipped_phases=_EXPRESS_SKIPPED_PHASES,
        ))
        assert transition.get("transitioned") is True, transition
        assert wss._db.get_workflow_phase(type_id)["workflow_phase"] == "implement"

    _run_with_servers(scenario)


def test_decomposed_skill_makes_the_directory_before_activating():
    """W2.7: the workflow-state skill's activation steps run the create-feature
    mkdir before ``activate_feature``, portably (no plugin path)."""
    with open(_SKILL_PATH, encoding="utf-8") as handle:
        skill = handle.read()
    section = skill.split("## Activating a planned feature", 1)[1]
    section = section.split("\n## ", 1)[0]
    lines = section.splitlines()

    mkdir_lines = [i for i, line in enumerate(lines) if _SKILL_MKDIR_STEP in line]
    activate_lines = [i for i, line in enumerate(lines) if "activate_feature(" in line]
    assert mkdir_lines, f"no {_SKILL_MKDIR_STEP!r} step in the activation section"
    assert activate_lines, "no activate_feature step in the activation section"
    assert mkdir_lines[0] < activate_lines[0]
    assert "plugins/pd" not in section


def test_decomposed_lane_activates_after_the_skills_mkdir(checkout):
    """A decomposed feature is registered with no directory. Activation still
    refuses loudly without one and makes none (W2.5); after the skill's mkdir
    it activates, seeds the row, and the first transition succeeds."""
    async def scenario():
        type_id, feature_directory = await _allocate_and_register(
            checkout, "decomposed thing", make_directory=False,
        )
        refused = json.loads(await wss.activate_feature(feature_type_id=type_id))
        assert refused.get("error_type") == "feature_not_found", refused
        assert not os.path.exists(feature_directory)
        assert wss._db.get_entity(type_id)["status"] == "planned"
        assert wss._db.get_workflow_phase(type_id) is None

        os.makedirs(feature_directory)  # the skill's mkdir step
        await _activate(type_id)
        _assert_seeded_row(type_id)

        transition = json.loads(await wss.transition_phase(
            feature_type_id=type_id, target_phase="specify",
        ))
        assert transition.get("transitioned") is True, transition

    _run_with_servers(scenario)


def test_activation_retried_after_a_lock_seeds_exactly_one_row(checkout, monkeypatch):
    """W2.5: the seed and the status write are one transaction, so a lock on
    the status write rolls the seed back and ``@_with_retry``'s re-run of the
    whole call seeds it once. The injected lock also checks, at the moment of
    the status write, that the seed is written but not yet committed."""
    lock_probe: dict = {}

    async def scenario():
        type_id, _ = await _allocate_and_register(
            checkout, "retried activation", make_directory=True,
        )
        real_update_entity = wss._db.update_entity

        def update_entity_locked_once(target, *args, **kwargs):
            if kwargs.get("status") == "active" and not lock_probe:
                lock_probe["seen_by_the_writer"] = (
                    wss._db.get_workflow_phase(type_id) is not None
                )
                lock_probe["committed"] = _committed_row_count(checkout, type_id)
                raise sqlite3.OperationalError("database is locked")
            return real_update_entity(target, *args, **kwargs)

        monkeypatch.setattr(wss._db, "update_entity", update_entity_locked_once)
        await _activate(type_id)

        assert _committed_row_count(checkout, type_id) == 1
        _assert_seeded_row(type_id)
        assert wss._db.get_entity(type_id)["status"] == "active"
        assert lock_probe == {"seen_by_the_writer": True, "committed": 0}

    _run_with_servers(scenario)
