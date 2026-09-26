"""W4 changes 1-3: each server resolves its workspace on demand and refuses
without one; a degraded start stays degraded; the create-project refusal of
a parent in another workspace has its own error type.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W4 (changes
1-3, and its Tests). Before W4:

- **First session:** in a repository with no ``.claude/``, the entity server
  refused every allocation (``workspace_unresolved``) until a restart, and the
  workflow server registered features into the ``__unknown__`` workspace
  (problem 3, N12);
- **Degraded start:** a recovery thread was started that never recovered the
  server (N3);
- **create-project** under another workspace's parent answered
  ``invalid_transition``, and did not say its allocated number is now unused
  (N11).

**How the lifespan tests run.** Both MCP servers start through their real
lifespans the way their launchers start them: ``PROJECT_ROOT`` unset, so each
server roots at its working directory. The registry, HOME and the git
repository are temp paths, and the repository has no ``.claude/``.
``isolate_lifespans`` sets that state up. The lifespans run unpatched: the
PID file and the parent watchdog belong to each server's ``__main__`` block
(W5.6), which no test here runs.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading

import pytest

_MCP_DIR = os.path.dirname(os.path.abspath(__file__))
_HOOKS_LIB = os.path.normpath(os.path.join(_MCP_DIR, "..", "hooks", "lib"))
for _path in (_HOOKS_LIB, _MCP_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import entity_server  # noqa: E402
import workflow_state_server as wss  # noqa: E402
from entity_registry.database import EntityDatabase, _UNKNOWN_WORKSPACE_UUID  # noqa: E402
from entity_registry.test_helpers import bootstrap_test_workspace  # noqa: E402
from workflow_engine.engine import WorkflowStateEngine  # noqa: E402
from workflow_engine.entity_engine import EntityWorkflowEngine  # noqa: E402
from workflow_engine.notifications import NotificationQueue  # noqa: E402

# The workspace_unresolved envelope's hint names the server to restart (W4.1).
_ENTITY_SERVER_HINT = (
    "restart the pd entity-registry MCP server from the repository root, "
    "or create .claude/ there"
)
_WORKFLOW_SERVER_HINT = (
    "restart the pd workflow-engine MCP server from the repository root, "
    "or create .claude/ there"
)
# What a degraded server answers every tool call with (W4.2).
_DEGRADED_ANSWER = "database unavailable (degraded start); restart the MCP server"

# The module globals each lifespan reads or assigns, at their values in a
# fresh server process. isolate_lifespans starts every test from these (a
# lifespan never resets _db_unavailable, and a degraded one assigns no
# project or workspace), and restores the suite's values afterwards.
_ENTITY_SERVER_FRESH_GLOBALS = {
    "_db": None, "_db_unavailable": False, "_config": {}, "_project_root": "",
    "_artifacts_root": "", "_project_id": "", "_git_info": None,
    "_workspace_uuid": "",
}
_WORKFLOW_SERVER_FRESH_GLOBALS = {
    "_db": None, "_db_unavailable": False, "_engine": None,
    "_entity_engine": None, "_artifacts_root": "", "_project_root": "",
    "_project_id": "", "_workspace_uuid": "", "_notification_queue": None,
}


def isolate_lifespans(monkeypatch, *, home, db_path) -> None:
    """Let both servers' lifespans run as their launchers start them, inside
    temp state, and restore the servers' module globals afterwards.

    - **Root:** ``PROJECT_ROOT`` is unset, so each server roots at the
      working directory the test chooses; no workspace env var is set.
    - **State:** HOME and the registry (``ENTITY_DB_PATH``) are temp paths,
      and both modules start from a fresh process's globals.
    """
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ENTITY_DB_PATH", str(db_path))
    for name in ("PROJECT_ROOT", "ENTITY_WORKSPACE_UUID", "WORKSPACE_UUID"):
        monkeypatch.delenv(name, raising=False)
    for module, fresh_globals in (
        (entity_server, _ENTITY_SERVER_FRESH_GLOBALS),
        (wss, _WORKFLOW_SERVER_FRESH_GLOBALS),
    ):
        for name, value in fresh_globals.items():
            monkeypatch.setattr(module, name, value)


def run_git(*args: str) -> str:
    """git with a fixed identity, so commits need no user config."""
    completed = subprocess.run(
        ["git", "-c", "user.name=w4", "-c", "user.email=w4@example.invalid",
         *args],
        check=True, capture_output=True, text=True,
    )
    return completed.stdout


def make_repository(path) -> None:
    """A git repository with a root commit and no ``.claude/``: a
    repository pd has never been started in."""
    run_git("init", "-q", "-b", "main", str(path))
    run_git("-C", str(path), "commit", "-q", "--allow-empty", "-m", "root")


def root_commit_id(repository) -> str:
    """The repository's legacy project id: its root commit, 12 characters."""
    return run_git(
        "-C", str(repository), "rev-list", "--max-parents=0", "HEAD"
    ).split()[0][:12]


def root_commit_workspace(db_path, repository) -> str:
    """The one workspaces row whose ``project_id_legacy`` is the
    repository's root commit id."""
    with contextlib.closing(sqlite3.connect(db_path)) as registry:
        rows = registry.execute(
            "SELECT uuid FROM workspaces WHERE project_id_legacy = ?",
            (root_commit_id(repository),),
        ).fetchall()
    assert len(rows) == 1, f"workspaces rows for the root commit: {rows}"
    return rows[0][0]


def committed_rows(db_path, sql, parameters=()):
    """Rows another connection sees: committed writes only."""
    with contextlib.closing(sqlite3.connect(db_path)) as registry:
        return registry.execute(sql, parameters).fetchall()


async def create_a_feature(description):
    """``/pd:create-feature`` steps 2-5: allocate, mkdir, register, activate.

    Returns the feature's type_id.
    """
    allocation = json.loads(await entity_server.allocate_entity_id(
        entity_type="feature", name=description,
    ))
    assert "entity_id" in allocation, allocation
    os.makedirs(os.path.join(
        wss._artifacts_root, "features", allocation["entity_id"]
    ))
    type_id = "feature:" + allocation["entity_id"]
    reply = await entity_server.register_entity(
        entity_type="feature", seq=allocation["seq"], slug=allocation["slug"],
        name=description, status="planned",
    )
    assert reply == f"Registered: {type_id}", reply
    activation = json.loads(await wss.activate_feature(feature_type_id=type_id))
    assert activation.get("activated") is True, activation
    return type_id


@pytest.fixture
def first_session(tmp_path, monkeypatch):
    """A temp HOME, an empty temp registry and a repository with no
    ``.claude/``, with both lifespans isolated."""
    home = tmp_path / "home"
    home.mkdir()
    repository = tmp_path / "repository"
    make_repository(repository)
    db_path = tmp_path / "registry" / "entities.db"
    isolate_lifespans(monkeypatch, home=home, db_path=db_path)
    return {"repository": repository, "db_path": str(db_path)}


# ---------------------------------------------------------------------------
# W4.1: a first session resolves on demand, from wherever it starts
# ---------------------------------------------------------------------------

_LAUNCH_PLACES = (
    "repository root", "subdirectory", "second clone", "linked worktree",
)
_START_ORDERS = ("entity server first", "workflow server first")


def _launch_directory(launch_place, first_session, tmp_path, monkeypatch):
    """The directory the session's servers start in (their root).

    The second clone's repository was opened once before, from its first
    clone: that entity server's startup bound the root commit to a workspace
    keyed by the first clone's path. The second clone has no ``.claude/``
    and no workspaces row of its own.
    """
    repository = first_session["repository"]
    if launch_place == "repository root":
        return repository
    if launch_place == "subdirectory":
        subdirectory = repository / "docs"
        subdirectory.mkdir()
        return subdirectory
    if launch_place == "linked worktree":
        worktree = tmp_path / "worktree"
        run_git("-C", str(repository), "worktree", "add", "-q", "-b",
                "session", str(worktree))
        return worktree
    monkeypatch.chdir(repository)

    async def open_the_first_clone():
        async with entity_server.lifespan(None):
            pass

    asyncio.run(open_the_first_clone())
    second_clone = tmp_path / "second-clone"
    run_git("clone", "-q", str(repository), str(second_clone))
    return second_clone


@pytest.mark.parametrize("start_order", _START_ORDERS)
@pytest.mark.parametrize("launch_place", _LAUNCH_PLACES)
def test_a_first_session_registers_through_both_servers(
    launch_place, start_order, first_session, tmp_path, monkeypatch,
):
    """Neither server needs a restart: the first write resolves the
    workspace whose legacy id is the repository's root commit, both servers
    cache it, and nothing lands in the ``__unknown__`` workspace."""
    launch_directory = _launch_directory(
        launch_place, first_session, tmp_path, monkeypatch,
    )
    monkeypatch.chdir(launch_directory)
    order = (
        (entity_server, wss) if start_order == "entity server first"
        else (wss, entity_server)
    )

    async def session():
        async with contextlib.AsyncExitStack() as servers:
            for module in order:
                await servers.enter_async_context(module.lifespan(None))
            assert entity_server._workspace_uuid == "", (
                "the entity server resolved a workspace at startup: "
                "not a first session"
            )
            return await create_a_feature("First idea")

    type_id = asyncio.run(session())

    db_path = first_session["db_path"]
    workspace = root_commit_workspace(db_path, first_session["repository"])
    assert (entity_server._workspace_uuid, wss._workspace_uuid) == (
        workspace, workspace,
    )
    assert committed_rows(
        db_path, "SELECT workspace_uuid FROM entities WHERE type_id = ?",
        (type_id,),
    ) == [(workspace,)]
    assert committed_rows(
        db_path, "SELECT workspace_uuid FROM workflow_phases WHERE type_id = ?",
        (type_id,),
    ) == [(workspace,)]
    assert committed_rows(
        db_path, "SELECT type_id FROM entities WHERE workspace_uuid = ?",
        (_UNKNOWN_WORKSPACE_UUID,),
    ) == []


def test_add_to_backlog_in_a_first_session_initializes_the_items_workflow(
    first_session, monkeypatch,
):
    """``/pd:add-to-backlog`` steps 3-4, first session, started from a
    subdirectory (neither server resolves a workspace at startup there).

    ``init_entity_workflow`` succeeds, and it succeeds through the workflow
    server's own workspace, resolved on demand and cached: the item's
    workflow row is in the repository's workspace, and so is the server.
    """
    subdirectory = first_session["repository"] / "docs"
    subdirectory.mkdir()
    monkeypatch.chdir(subdirectory)

    async def session():
        async with entity_server.lifespan(None), wss.lifespan(None):
            assert (entity_server._workspace_uuid, wss._workspace_uuid) == ("", "")
            reply = await entity_server.register_entity(
                entity_type="backlog", auto_id=True, name="first idea",
                status="open", metadata={"description": "first idea"},
            )
            assert reply == "Registered: backlog:001-first-idea", reply
            return json.loads(await wss.init_entity_workflow(
                type_id="backlog:001-first-idea", workflow_phase="open",
                kanban_column="backlog",
            ))

    initialized = asyncio.run(session())

    assert initialized.get("created") is True, initialized
    db_path = first_session["db_path"]
    workspace = root_commit_workspace(db_path, first_session["repository"])
    assert committed_rows(
        db_path, "SELECT workspace_uuid FROM workflow_phases WHERE type_id = ?",
        ("backlog:001-first-idea",),
    ) == [(workspace,)]
    assert wss._workspace_uuid == workspace


def test_a_workflow_server_with_no_workspace_refuses_until_one_resolves(
    first_session, monkeypatch,
):
    """Only the workflow server has started, from the repository root: no
    ``.claude/`` exists and no workspaces row carries the root commit.

    ``init_feature_state`` answers ``workspace_unresolved``, naming the
    workflow-engine server, and writes nothing: no row, no ``.meta.json``,
    no ``.claude/``. The refusal is not cached: once the entity server's
    startup binds the root commit to a workspace, the same call succeeds
    there, with no restart. That retry writes the repository's
    ``.claude/pd/workspace.json``, the normal file of a pd project.
    """
    repository = first_session["repository"]
    monkeypatch.chdir(repository)
    db_path = first_session["db_path"]
    call = dict(feature_id="001", slug="demo", mode="standard",
                branch="feature/001-demo")

    async def session():
        async with wss.lifespan(None):
            feature_directory = os.path.join(
                wss._artifacts_root, "features", "001-demo"
            )
            os.makedirs(feature_directory)
            refused = json.loads(await wss.init_feature_state(
                feature_dir=feature_directory, **call,
            ))
            after_refusal = {
                "rows": {
                    table: committed_rows(db_path, f"SELECT COUNT(*) FROM {table}")[0][0]
                    for table in ("entities", "workflow_phases", "workspaces")
                },
                "cached workspace": wss._workspace_uuid,
                "feature directory": sorted(os.listdir(feature_directory)),
                ".claude exists": (repository / ".claude").exists(),
            }
            async with entity_server.lifespan(None):
                accepted = json.loads(await wss.init_feature_state(
                    feature_dir=feature_directory, **call,
                ))
            return refused, after_refusal, accepted

    refused, after_refusal, accepted = asyncio.run(session())

    assert refused.get("error_type") == "workspace_unresolved", refused
    assert refused["recovery_hint"] == _WORKFLOW_SERVER_HINT
    assert after_refusal == {
        "rows": {"entities": 0, "workflow_phases": 0, "workspaces": 0},
        "cached workspace": "",
        "feature directory": [],
        ".claude exists": False,
    }
    assert accepted.get("created") is True, accepted
    assert (repository / ".claude" / "pd" / "workspace.json").is_file()
    workspace = root_commit_workspace(db_path, repository)
    assert committed_rows(
        db_path, "SELECT workspace_uuid FROM entities WHERE type_id = ?",
        ("feature:001-demo",),
    ) == [(workspace,)]


# ---------------------------------------------------------------------------
# W4.1 with Phase 3: the servers agree with the session-start hook. A checkout
# git cannot answer for gets no workspace; a linked worktree's first session
# gets the repository's.
# ---------------------------------------------------------------------------

_HOOKS_DIR = os.path.dirname(_HOOKS_LIB)


def ensure_workspace_uuid(directory, tmp_path) -> str:
    """The session-start hook's ``ensure_workspace_uuid "$PROJECT_ROOT"``
    (``hooks/lib/session-start-helpers.sh``) for a session rooted at
    *directory*. It runs ``$PLUGIN_ROOT/.venv/bin/python`` on
    ``$PLUGIN_ROOT/hooks/lib``, so the plugin root here pairs this test's
    interpreter with this checkout's hooks."""
    plugin_root = tmp_path / "plugin-root"
    if not plugin_root.exists():
        plugin_root.mkdir()
        os.symlink(sys.prefix, plugin_root / ".venv")
        os.symlink(_HOOKS_DIR, plugin_root / "hooks")
    completed = subprocess.run(
        ["bash", "-c",
         'source "$1/hooks/lib/common.sh" && '
         'source "$1/hooks/lib/session-start-helpers.sh" && '
         'PLUGIN_ROOT="$1" && '
         'PD_WORKSPACE_PROJECT_ROOT="$2" ensure_workspace_uuid "$2"',
         "ensure_workspace_uuid", str(plugin_root), str(directory)],
        cwd=str(directory), capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def _error_type(reply: str):
    """A tool reply's ``error_type``; the reply itself when it is not an
    error envelope (a success)."""
    try:
        return json.loads(reply).get("error_type", reply)
    except (ValueError, AttributeError):
        return reply


def test_a_server_in_an_orphaned_worktree_mints_no_workspace_and_refuses(
    first_session, monkeypatch, capsys,
):
    """Both servers start in a linked worktree whose directory under
    ``<main>/.git/worktrees`` is gone, so git cannot answer there. Phase 3
    decided such a checkout resolves no workspace, and the hook refuses it.
    The worktree holds pd's ``.claude/`` and a brainstorm, which the entity
    server's startup backfill would register.

    That startup registers no project and backfills nothing, so no
    workspace keyed on the orphan's path appears for step 3 of
    ``_require_workspace()`` to find by the path-hash legacy id. Each
    server's write tools answer ``workspace_unresolved``, and no registry
    table gains a row.
    """
    repository = first_session["repository"]
    (repository / ".claude").mkdir()
    (repository / ".claude" / "settings.json").write_text("{}\n")
    run_git("-C", str(repository), "add", ".claude")
    run_git("-C", str(repository), "commit", "-q", "-m", "enable pd")
    orphan = repository / ".pd-worktrees" / "task"
    run_git("-C", str(repository), "worktree", "add", "-q", "-b", "task",
            str(orphan))
    shutil.rmtree(
        (orphan / ".git").read_text().strip().removeprefix("gitdir: ")
    )
    brainstorms = orphan / "docs" / "brainstorms"
    brainstorms.mkdir(parents=True)
    (brainstorms / "20260927-orphan-idea.prd.md").write_text("# Orphan idea\n")
    feature_directory = orphan / "docs" / "features" / "001-demo"
    feature_directory.mkdir(parents=True)
    db_path = first_session["db_path"]
    os.makedirs(os.path.dirname(db_path))
    EntityDatabase(db_path).close()
    registry_before = _registry_snapshot(db_path)
    monkeypatch.chdir(orphan)

    async def session():
        async with entity_server.lifespan(None), wss.lifespan(None):
            after_startup = _registry_snapshot(db_path)
            replies = {
                "allocate_entity_id": await entity_server.allocate_entity_id(
                    entity_type="feature", name="orphan idea",
                ),
                "register_entity": await entity_server.register_entity(
                    entity_type="feature", auto_id=True, name="orphan idea",
                    status="planned",
                ),
                "init_feature_state": await wss.init_feature_state(
                    feature_dir=str(feature_directory), feature_id="001",
                    slug="demo", mode="standard", branch="feature/001-demo",
                ),
            }
            return after_startup, replies

    after_startup, replies = asyncio.run(session())

    assert after_startup == registry_before
    assert {tool: _error_type(reply) for tool, reply in replies.items()} == (
        dict.fromkeys(replies, "workspace_unresolved")
    )
    assert _registry_snapshot(db_path) == registry_before
    assert os.listdir(feature_directory) == []
    assert "project registration and backfill skipped" in capsys.readouterr().err


@pytest.mark.parametrize("start_order", _START_ORDERS)
def test_a_linked_worktrees_first_session_keeps_its_workspace_once_pd_is_enabled(
    start_order, first_session, tmp_path, monkeypatch,
):
    """A first session started from a linked worktree of a repository with
    no ``.claude/`` registers a feature, in the workspace the entity
    server's startup minted. That workspace is keyed at the main checkout,
    so once ``<main>/.claude`` exists (the refusal's hint asks for it), the
    session-start hook resolves the same workspace from the worktree and
    from the main checkout. Keyed at the worktree, the hook would mint a
    second workspace for the repository and strand the feature in the
    first."""
    repository = first_session["repository"]
    worktree = tmp_path / "worktree"
    run_git("-C", str(repository), "worktree", "add", "-q", "-b", "session",
            str(worktree))
    monkeypatch.chdir(worktree)
    order = (
        (entity_server, wss) if start_order == "entity server first"
        else (wss, entity_server)
    )

    async def session():
        async with contextlib.AsyncExitStack() as servers:
            for module in order:
                await servers.enter_async_context(module.lifespan(None))
            return await create_a_feature("First idea")

    type_id = asyncio.run(session())
    db_path = first_session["db_path"]
    [(first_sessions_workspace,)] = committed_rows(
        db_path, "SELECT workspace_uuid FROM entities WHERE type_id = ?",
        (type_id,),
    )
    (repository / ".claude").mkdir(exist_ok=True)

    assert {
        "from the worktree": ensure_workspace_uuid(worktree, tmp_path),
        "from the main checkout": ensure_workspace_uuid(repository, tmp_path),
    } == dict.fromkeys(
        ("from the worktree", "from the main checkout"), first_sessions_workspace,
    )
    assert committed_rows(
        db_path, "SELECT uuid, project_root FROM workspaces WHERE uuid != ?",
        (_UNKNOWN_WORKSPACE_UUID,),
    ) == [(first_sessions_workspace, os.path.realpath(repository))]


# ---------------------------------------------------------------------------
# W4.1: every write tool it lists refuses without a workspace
# ---------------------------------------------------------------------------

_FEATURE = "feature:001-alpha"
_BACKLOG_ITEM = "backlog:001-idea"
_BACKLOG_ITEM_WITHOUT_WORKFLOW = "backlog:002-other-idea"
_OBJECTIVE = "objective:001-grow"

# W4.1's write tools, each called with arguments a session would pass. Each
# value is (server, call); a call takes the setup dict and returns the
# tool's coroutine.
_WRITE_CALLS = {
    "allocate_entity_id": ("entity", lambda setup: entity_server.allocate_entity_id(
        entity_type="feature", name="gamma")),
    "register_entity": ("entity", lambda setup: entity_server.register_entity(
        entity_type="backlog", auto_id=True, name="another idea", status="open")),
    "issue_spawn": ("entity", lambda setup: entity_server.issue_spawn(
        parent_uuid=setup["feature_uuid"], kind="bug", summary="a bug")),
    "create_key_result": ("entity", lambda setup: entity_server.create_key_result(
        parent_ref=_OBJECTIVE, name="double revenue", metric_type="binary")),
    "activate_feature": ("workflow", lambda setup: wss.activate_feature(
        feature_type_id=_FEATURE)),
    "transition_phase": ("workflow", lambda setup: wss.transition_phase(
        feature_type_id=_FEATURE, target_phase="specify")),
    "complete_phase": ("workflow", lambda setup: wss.complete_phase(
        feature_type_id=_FEATURE, phase="brainstorm")),
    "init_feature_state": ("workflow", lambda setup: wss.init_feature_state(
        feature_dir=setup["new_feature_directory"], feature_id="002",
        slug="beta", mode="standard", branch="feature/002-beta")),
    "init_project_state": ("workflow", lambda setup: wss.init_project_state(
        project_dir=setup["new_project_directory"], project_id="001",
        slug="plan", features="[]", milestones="[]")),
    "init_entity_workflow": ("workflow", lambda setup: wss.init_entity_workflow(
        type_id=_BACKLOG_ITEM_WITHOUT_WORKFLOW, workflow_phase="open",
        kanban_column="backlog")),
    "transition_entity_phase": ("workflow", lambda setup: wss.transition_entity_phase(
        type_id=_BACKLOG_ITEM, target_phase="triaged")),
    "record_backward_event": ("workflow", lambda setup: wss.record_backward_event(
        type_id=_FEATURE, source_phase="design", target_phase="specify",
        reason="rework")),
    "record_mini_spec": ("workflow", lambda setup: wss.record_mini_spec(
        feature_type_id=_FEATURE, text="the mini-spec")),
    "promote_task": ("workflow", lambda setup: wss.promote_task(
        feature_ref=_FEATURE, task_heading="Task 1: build it")),
}


def _registry_snapshot(db_path):
    """Every table's row count: any write changes one."""
    with contextlib.closing(sqlite3.connect(db_path)) as registry:
        tables = [row[0] for row in registry.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )]
        return {
            table: registry.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in tables
        }


def _artifact_files(artifacts_root):
    return sorted(
        os.path.relpath(os.path.join(directory, name), artifacts_root)
        for directory, subdirectories, files in os.walk(artifacts_root)
        for name in files + subdirectories
    )


@pytest.fixture
def unresolved_servers(tmp_path, monkeypatch, request):
    """Both servers running with a registry but no workspace, and nothing to
    resolve one from: no project root to retry the startup resolution with,
    and a legacy project id (``request.param``) the lookup must skip.

    The registry holds a workspace with the entities the calls name, so a
    call that went ahead would write.
    """
    server_project_id = request.param
    db_path = str(tmp_path / "entities.db")
    db = EntityDatabase(db_path)
    workspace = bootstrap_test_workspace(db, "w4-refusal")
    artifacts_root = tmp_path / "docs"
    feature_directory = artifacts_root / "features" / "001-alpha"
    feature_directory.mkdir(parents=True)
    (feature_directory / "plan.md").write_text(
        "# Plan\n\n#### Task 1: build it\n\nBuild it.\n", encoding="utf-8",
    )
    new_feature_directory = artifacts_root / "features" / "002-beta"
    new_feature_directory.mkdir()
    feature_uuid = db.register_entity(
        "feature", name="Alpha", seq=1, slug="alpha", status="planned",
        artifact_path=str(feature_directory), workspace_uuid=workspace,
    )
    db.create_workflow_phase(
        _FEATURE, workspace_uuid=workspace, workflow_phase="brainstorm",
    )
    db.register_entity(
        "backlog", name="Idea", seq=1, slug="idea", status="open",
        workspace_uuid=workspace,
    )
    db.create_workflow_phase(
        _BACKLOG_ITEM, workspace_uuid=workspace, workflow_phase="open",
    )
    db.register_entity(
        "backlog", name="Other idea", seq=2, slug="other-idea", status="open",
        workspace_uuid=workspace,
    )
    db.register_entity(
        "objective", name="Grow", seq=1, slug="grow", status="active",
        workspace_uuid=workspace,
    )
    queue = NotificationQueue(str(tmp_path / "notifications.jsonl"))
    for module, values in (
        (entity_server, {}),
        (wss, {
            "_engine": WorkflowStateEngine(db, str(artifacts_root)),
            "_entity_engine": EntityWorkflowEngine(db, str(artifacts_root), queue),
            "_notification_queue": queue,
            "_artifacts_root": str(artifacts_root),
        }),
    ):
        values.update({
            "_db": db, "_db_unavailable": False, "_project_root": "",
            "_project_id": server_project_id, "_workspace_uuid": "",
        })
        for name, value in values.items():
            monkeypatch.setattr(module, name, value)
    yield {
        "db_path": db_path,
        "artifacts_root": str(artifacts_root),
        "feature_uuid": feature_uuid,
        "new_feature_directory": str(new_feature_directory),
        "new_project_directory": str(artifacts_root / "projects" / "001-plan"),
    }
    db.close()


@pytest.mark.parametrize(
    "unresolved_servers", ["", "__unknown__"],
    ids=["no legacy project id", "the __unknown__ legacy project id"],
    indirect=True,
)
@pytest.mark.parametrize("tool", sorted(_WRITE_CALLS))
def test_every_write_tool_refuses_without_a_workspace_and_writes_nothing(
    tool, unresolved_servers,
):
    """The ``__unknown__`` legacy id maps to the unknown workspace, so the
    lookup skips it rather than write there. Read tools still answer."""
    server, call = _WRITE_CALLS[tool]
    setup = unresolved_servers
    registry_before = _registry_snapshot(setup["db_path"])
    artifacts_before = _artifact_files(setup["artifacts_root"])

    raw_reply = asyncio.run(call(setup))

    assert raw_reply.startswith("{"), f"not an error envelope: {raw_reply}"
    reply = json.loads(raw_reply)
    assert reply.get("error_type") == "workspace_unresolved", reply
    assert reply["recovery_hint"] == (
        _ENTITY_SERVER_HINT if server == "entity" else _WORKFLOW_SERVER_HINT
    )
    assert _registry_snapshot(setup["db_path"]) == registry_before
    assert _artifact_files(setup["artifacts_root"]) == artifacts_before
    assert (entity_server._workspace_uuid, wss._workspace_uuid) == ("", "")
    if server == "entity":
        read = asyncio.run(entity_server.get_entity(type_id=_FEATURE))
        assert _FEATURE in read, read
    else:
        read = json.loads(asyncio.run(wss.get_phase(feature_type_id=_FEATURE)))
        assert read.get("current_phase") == "brainstorm", read


# ---------------------------------------------------------------------------
# W4.1: issue_spawn's deprecated project_id never outranks the server's own
# workspace, and "__unknown__" names no workspace
# ---------------------------------------------------------------------------

_SPAWN_SERVER_LEGACY_ID = "w4-spawn-server"
_SPAWN_OTHER_LEGACY_ID = "w4-spawn-other"


@pytest.fixture
def spawning_server(tmp_path, monkeypatch):
    """The entity server over a registry with two workspaces, the server's
    and another, and a parent feature in the server's.

    Nothing resolves a workspace on demand (no project root, no legacy
    project id): a test that gives the server one sets ``_workspace_uuid``.
    """
    db_path = str(tmp_path / "entities.db")
    db = EntityDatabase(db_path)
    server_workspace = bootstrap_test_workspace(db, _SPAWN_SERVER_LEGACY_ID)
    bootstrap_test_workspace(db, _SPAWN_OTHER_LEGACY_ID)
    parent_uuid = db.register_entity(
        "feature", name="Alpha", seq=1, slug="alpha", status="active",
        workspace_uuid=server_workspace,
    )
    for name, value in {
        "_db": db, "_db_unavailable": False, "_project_root": "",
        "_project_id": "", "_workspace_uuid": "",
    }.items():
        monkeypatch.setattr(entity_server, name, value)
    yield {
        "db_path": db_path,
        "server_workspace": server_workspace,
        "parent_uuid": parent_uuid,
    }
    db.close()


def _spawn_a_bug(spawning_server, project_id):
    return json.loads(asyncio.run(entity_server.issue_spawn(
        parent_uuid=spawning_server["parent_uuid"], kind="bug",
        summary="a bug", project_id=project_id,
    )))


@pytest.mark.parametrize(
    "project_id", [_SPAWN_OTHER_LEGACY_ID, "__unknown__"],
    ids=["another workspace's legacy id", "the __unknown__ legacy id"],
)
def test_issue_spawn_spawns_in_the_servers_workspace_whatever_project_id_names(
    project_id, spawning_server, monkeypatch,
):
    """A server with a workspace spawns there, as before W4.1: the deprecated
    project_id names a workspace only for a server with none of its own."""
    monkeypatch.setattr(
        entity_server, "_workspace_uuid", spawning_server["server_workspace"],
    )

    reply = _spawn_a_bug(spawning_server, project_id)

    assert "uuid" in reply, reply
    assert committed_rows(
        spawning_server["db_path"],
        "SELECT workspace_uuid FROM entities WHERE uuid = ?", (reply["uuid"],),
    ) == [(spawning_server["server_workspace"],)]


def test_issue_spawn_refuses_the_unknown_legacy_id_on_a_server_with_no_workspace(
    spawning_server,
):
    """``"__unknown__"`` names no workspace, just as no project_id does: a
    server with none of its own refuses (workspace_unresolved) and writes
    nothing, rather than spawn into the unknown workspace."""
    registry_before = _registry_snapshot(spawning_server["db_path"])

    reply = _spawn_a_bug(spawning_server, "__unknown__")

    assert reply.get("error_type") == "workspace_unresolved", reply
    assert reply["recovery_hint"] == _ENTITY_SERVER_HINT
    assert _registry_snapshot(spawning_server["db_path"]) == registry_before
    assert entity_server._workspace_uuid == ""


def test_issue_spawn_labels_the_parents_event_unknown_when_no_project_id_is_known(
    spawning_server, monkeypatch,
):
    """A direct call with no project_id, to a server with a workspace but
    no legacy id (a lifespan always sets one): the parent's
    ``spawned_child`` event is labelled ``"__unknown__"``, as the workflow
    server labels its events, never ``""``, which ``query_phase_events``
    cannot filter by."""
    monkeypatch.setattr(
        entity_server, "_workspace_uuid", spawning_server["server_workspace"],
    )

    reply = _spawn_a_bug(spawning_server, None)

    assert "uuid" in reply, reply
    assert committed_rows(
        spawning_server["db_path"],
        "SELECT project_id FROM phase_events WHERE event_type = 'spawned_child'",
    ) == [("__unknown__",)]


# ---------------------------------------------------------------------------
# W4.2: a degraded start stays degraded, with no recovery thread
# ---------------------------------------------------------------------------

async def _allocate_while_degraded():
    return json.loads(await entity_server.allocate_entity_id(
        entity_type="feature", name="gamma",
    ))


async def _init_feature_state_while_degraded():
    return json.loads(await wss.init_feature_state(
        feature_dir="docs/features/001-demo", feature_id="001", slug="demo",
        mode="standard", branch="feature/001-demo",
    ))


@pytest.mark.parametrize("server", ["entity server", "workflow server"])
def test_a_degraded_start_stays_degraded_with_no_recovery_thread(
    server, first_session, monkeypatch,
):
    """The registry cannot be opened at startup. The server starts no
    recovery thread (none ever recovered one, N3), and it answers every call
    with the degraded message, which asks for a restart."""
    module, write = {
        "entity server": (entity_server, _allocate_while_degraded),
        "workflow server": (wss, _init_feature_state_while_degraded),
    }[server]
    monkeypatch.chdir(first_session["repository"])
    monkeypatch.setattr(module, "_init_db_with_retry", lambda db_path: None)

    async def degraded_session():
        async with module.lifespan(None):
            return (
                module._db_unavailable,
                [thread.name for thread in threading.enumerate()],
                module._check_db_available(),
                await write(),
            )

    unavailable, threads, availability, reply = asyncio.run(degraded_session())

    assert unavailable is True
    assert "db-recovery" not in threads
    assert not hasattr(module, "_start_recovery_thread")
    if module is wss:
        availability = json.loads(availability)
    assert availability == {"error": _DEGRADED_ANSWER}
    assert reply == {"error": _DEGRADED_ANSWER}


# ---------------------------------------------------------------------------
# W4.3: create-project under another workspace's parent
# ---------------------------------------------------------------------------

def test_a_parent_in_another_workspace_answers_cross_workspace_parent(
    tmp_path, monkeypatch,
):
    """``/pd:create-project`` steps 3 and 6 with a brainstorm parent from
    another workspace: the refusal has its own error type, it names the
    allocated number that is now unused, and the next allocation does not
    reuse that number. Nothing is registered and no directory is made."""
    db = EntityDatabase(str(tmp_path / "entities.db"))
    home_workspace = bootstrap_test_workspace(db, "w4-home")
    other_workspace = bootstrap_test_workspace(db, "w4-other")
    foreign_brainstorm = db.register_entity(
        "brainstorm", name="alpha brainstorm", display_id="20260926-alpha",
        workspace_uuid=other_workspace,
    )
    artifacts_root = tmp_path / "docs"
    artifacts_root.mkdir()
    for module, values in (
        (entity_server, {}),
        (wss, {"_artifacts_root": str(artifacts_root)}),
    ):
        values.update({
            "_db": db, "_db_unavailable": False,
            "_workspace_uuid": home_workspace,
        })
        for name, value in values.items():
            monkeypatch.setattr(module, name, value)

    async def create_project():
        allocation = json.loads(await entity_server.allocate_entity_id(
            entity_type="project", name="alpha",
        ))
        project_directory = os.path.join(
            str(artifacts_root), "projects", allocation["entity_id"]
        )
        reply = json.loads(await wss.init_project_state(
            project_dir=project_directory,
            project_id=f"{allocation['seq']:03d}", slug=allocation["slug"],
            features="[]", milestones="[]", parent_uuid=foreign_brainstorm,
        ))
        next_allocation = json.loads(await entity_server.allocate_entity_id(
            entity_type="project", name="alpha",
        ))
        return allocation, project_directory, reply, next_allocation

    try:
        allocation, project_directory, reply, next_allocation = asyncio.run(
            create_project()
        )

        assert reply.get("error_type") == "cross_workspace_parent", reply
        unused_number = f"{allocation['seq']:03d}"
        assert f"project number {unused_number} is now unused" in reply["message"]
        assert "numbers are never reused" in reply["message"]
        assert db.list_entities(entity_type="project", include_deleted=True) == []
        assert not os.path.exists(project_directory)
        assert next_allocation["seq"] == allocation["seq"] + 1
    finally:
        db.close()
