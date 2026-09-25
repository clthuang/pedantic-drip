"""W2.2-W2.4: the projection, the finish check and task promotion name the
directory in the session's checkout, never from the stored ``artifact_path``.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W2 changes
2-4 and the "Worktree projection" test.

- **Features:** ``{artifacts_root}/features/<name>``, the name from
  ``feature_dir_name`` with the engine's containment check.
- **Projects:** ``{artifacts_root}/projects/<last component of
  artifact_path>``: a project's entity_id need not be its directory's name.
- **A refused name or a missing directory:** the projection returns a
  warning and writes nothing.

**The session.** A main checkout and a linked worktree of it. The workflow
server starts through its real lifespan rooted at the worktree, with a temp
HOME and a temp registry. Every stored ``artifact_path`` is absolute into
the main checkout, as registration from the main checkout left it.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import uuid as _uuid

import pytest

_MCP_DIR = os.path.dirname(os.path.abspath(__file__))
_HOOKS_LIB = os.path.normpath(os.path.join(_MCP_DIR, "..", "hooks", "lib"))
for _path in (_HOOKS_LIB, _MCP_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import workflow_state_server as wss  # noqa: E402
from entity_registry.database import _derive_type_and_lifecycle  # noqa: E402
from test_create_feature_lanes import (  # noqa: E402
    isolate_servers,
    make_pd_repo,
    run_git,
)

_STANDARD_ARTIFACTS = ("shape.md", "plan.md", "retro.md")


@pytest.fixture
def session(tmp_path, monkeypatch):
    """A main checkout, a linked worktree, and the server rooted at the
    worktree."""
    home = tmp_path / "home"
    home.mkdir()
    main = tmp_path / "main"
    make_pd_repo(main)
    worktree = tmp_path / "worktree"
    run_git("-C", str(main), "worktree", "add", "-q", "-b", "session", str(worktree))
    for checkout in (main, worktree):
        (checkout / "docs" / "features").mkdir(parents=True)
        (checkout / "docs" / "projects").mkdir(parents=True)
    db_path = tmp_path / "registry" / "entities.db"
    isolate_servers(monkeypatch, home=home, db_path=db_path, project_root=worktree)
    return {
        "main_docs": str(main / "docs"),
        "session_docs": str(worktree / "docs"),
        "db_path": str(db_path),
    }


def _run_in_workflow_server(session, scenario):
    async def main():
        async with wss.lifespan(None):
            assert wss._artifacts_root == session["session_docs"]
            assert wss._workspace_uuid
            await scenario()

    asyncio.run(main())


def _directory(docs, kind_dir, name, files=()):
    path = os.path.join(docs, kind_dir, name)
    os.makedirs(path)
    for file_name in files:
        with open(os.path.join(path, file_name), "w", encoding="utf-8") as handle:
            handle.write("content\n")
    return path


def _feature(seq, slug, artifact_path, **columns):
    """Register a feature in the session's workspace, stored path into main."""
    return wss._db.register_entity(
        "feature", name=slug.replace("-", " "), seq=seq, slug=slug,
        status="active", artifact_path=artifact_path,
        workspace_uuid=wss._workspace_uuid, **columns,
    )


def test_a_feature_projects_into_the_sessions_worktree(session):
    async def scenario():
        main_dir = _directory(session["main_docs"], "features", "011-omega")
        session_dir = _directory(session["session_docs"], "features", "011-omega")
        _feature(11, "omega", main_dir)
        wss._db.create_workflow_phase(
            "feature:011-omega", workflow_phase="specify",
            kanban_column="backlog", mode="standard",
        )

        reply = json.loads(await wss.reproject_meta_json(
            feature_type_id="feature:011-omega",
        ))

        assert os.path.isfile(os.path.join(session_dir, ".meta.json")), reply
        assert not os.path.exists(os.path.join(main_dir, ".meta.json"))
        assert reply["projected"] is True, reply

    _run_in_workflow_server(session, scenario)


def test_a_project_is_named_by_its_stored_paths_last_component(session):
    """The entity_id (``006-memory-flywheel``) is not the directory's name
    (``P002-memory-flywheel``); the stored path ends in ``/``."""
    async def scenario():
        main_dir = _directory(session["main_docs"], "projects", "P002-memory-flywheel")
        session_dir = _directory(
            session["session_docs"], "projects", "P002-memory-flywheel",
        )
        wss._db.register_entity(
            "project", name="Memory flywheel", seq=6, slug="memory-flywheel",
            status="active", artifact_path=main_dir + "/",
            workspace_uuid=wss._workspace_uuid,
        )

        reply = json.loads(await wss.reproject_meta_json(
            feature_type_id="project:006-memory-flywheel",
        ))

        assert os.path.isfile(os.path.join(session_dir, ".meta.json")), reply
        assert not os.path.exists(os.path.join(main_dir, ".meta.json"))
        assert not os.path.exists(
            os.path.join(session["session_docs"], "projects", "006-memory-flywheel")
        )
        assert reply["projected"] is True, reply

    _run_in_workflow_server(session, scenario)


def test_a_missing_directory_is_a_warning_and_writes_nothing(session):
    """The session's checkout has no directory for the feature; the stored
    path's directory, in the main checkout, is not a stand-in."""
    async def scenario():
        main_dir = _directory(session["main_docs"], "features", "012-absent")
        _feature(12, "absent", main_dir)

        reply = json.loads(await wss.reproject_meta_json(
            feature_type_id="feature:012-absent",
        ))

        assert not os.path.exists(os.path.join(main_dir, ".meta.json"))
        assert not os.path.exists(
            os.path.join(session["session_docs"], "features", "012-absent")
        )
        assert reply["projected"] is False, reply
        assert "does not exist" in reply["warning"]

    _run_in_workflow_server(session, scenario)


def test_a_refused_name_is_a_warning_and_writes_nothing(session):
    """A corrupt stored entity_id that is not one path component names no
    directory: a warning, no write, no raise."""
    async def scenario():
        main_dir = _directory(session["main_docs"], "features", "013-unsafe")
        entity_type, lifecycle_class = _derive_type_and_lifecycle("feature")
        raw = sqlite3.connect(session["db_path"])
        try:
            raw.execute(
                "INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, "
                "name, status, artifact_path, created_at, updated_at, type, kind, "
                "lifecycle_class) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(_uuid.uuid4()), wss._workspace_uuid, "feature:013-unsafe",
                 "013-a/b", "unsafe", "active", main_dir,
                 "2026-09-26T00:00:00Z", "2026-09-26T00:00:00Z",
                 entity_type, "feature", lifecycle_class),
            )
            raw.commit()
        finally:
            raw.close()

        reply = json.loads(await wss.reproject_meta_json(
            feature_type_id="feature:013-unsafe",
        ))

        assert not os.path.exists(os.path.join(main_dir, ".meta.json"))
        assert reply["projected"] is False, reply
        assert "path traversal blocked" in reply["warning"]

    _run_in_workflow_server(session, scenario)


def test_finish_checks_the_artifacts_of_the_named_directory(session):
    """The main checkout's directory is complete; the session's lacks
    plan.md, and that is what finish reports."""
    async def scenario():
        main_dir = _directory(
            session["main_docs"], "features", "014-finish", _STANDARD_ARTIFACTS,
        )
        _directory(
            session["session_docs"], "features", "014-finish",
            ("shape.md", "retro.md"),
        )
        _feature(14, "finish", main_dir, metadata={"mode": "standard"})
        wss._db.create_workflow_phase(
            "feature:014-finish", workflow_phase="finish",
            kanban_column="documenting", mode="standard",
        )

        reply = json.loads(await wss.complete_phase(
            feature_type_id="feature:014-finish", phase="finish",
        ))

        assert reply.get("artifact_warnings") == ["Missing artifact: plan.md"], reply

    _run_in_workflow_server(session, scenario)


def test_promote_task_reads_plan_md_from_the_named_directory(session):
    """Only the session's directory has plan.md. The promoted task's row
    carries the session's workspace and the task's uuid (W2.1)."""
    async def scenario():
        main_dir = _directory(session["main_docs"], "features", "015-promote")
        session_dir = _directory(session["session_docs"], "features", "015-promote")
        with open(os.path.join(session_dir, "plan.md"), "w", encoding="utf-8") as handle:
            handle.write("# Plan\n\n#### Task 1.1: Wire the lanes\n\nDo it.\n")
        _feature(15, "promote", main_dir)
        wss._db.create_workflow_phase(
            "feature:015-promote", workflow_phase="implement",
            kanban_column="wip", mode="standard",
        )

        reply = json.loads(await wss.promote_task(
            feature_ref="feature:015-promote", task_heading="Wire the lanes",
        ))

        assert reply.get("promoted") is True, reply
        row = wss._db.get_workflow_phase(reply["task_type_id"])
        assert (row["workspace_uuid"], row["uuid"]) == (
            wss._workspace_uuid, reply["task_uuid"],
        )

    _run_in_workflow_server(session, scenario)
