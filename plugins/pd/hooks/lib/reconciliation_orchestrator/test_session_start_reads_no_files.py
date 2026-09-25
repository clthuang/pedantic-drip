"""W1 session-start tests: the checkout's files never write the registry.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W1 (changes
1, 3, 7 and 8, and its Tests).

**How a session starts here.** Each test runs the reconciliation
orchestrator the way ``plugins/pd/hooks/session-start.sh`` runs it:
``python -m reconciliation_orchestrator --project-root <repo>
--artifacts-root docs --entity-db <db>``, with ``PYTHONPATH`` at
``hooks/lib`` and no workspace flag, so the orchestrator resolves the
checkout's workspace itself. It runs against a temp registry, a temp HOME
and a temp git repo.

**The two workspaces.** The checkout under test is workspace A. Workspace B
is another pd repo registered in the same registry, the way every pd project
on a machine shares one ``entities.db``. One test adds a third: a second
clone of A's repository, whose workspace has no legacy project id.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from entity_registry.database import EntityDatabase
from entity_registry.metadata import parse_metadata
from entity_registry.project_identity import resolve_workspace_uuid
from entity_registry.test_helpers import seed_legacy_entity
from workflow_engine.rollup import compute_progress

_HOOKS_LIB = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_ORCHESTRATOR = "reconciliation_orchestrator"


def _git(*args: str) -> None:
    """git with a fixed identity, so commits need no user config."""
    subprocess.run(
        ["git", "-c", "user.name=w1", "-c", "user.email=w1@example.invalid",
         *args],
        check=True, capture_output=True,
    )


def _make_pd_repo(path, root_message: str) -> str:
    """A git repo with a root commit and a ``.claude/`` directory (a
    pd-enabled project: workspace resolution requires it).

    Each repo gets its own root commit message: the legacy project id is the
    root commit, and two identical root commits would collide on it.
    """
    _git("init", "-q", "-b", "main", str(path))
    _git("-C", str(path), "commit", "-q", "--allow-empty", "-m", root_message)
    (path / ".claude").mkdir()
    return os.path.realpath(str(path))


def _clone_pd_repo(source: str, path) -> str:
    """A second clone of *source*, pd-enabled, with an empty ``docs/``.

    The clone shares its source's root commit, so its workspace row gets no
    legacy project id: that id is already the source workspace's, and the
    column is unique (``project_identity._insert_workspace_row_if_absent``).
    """
    _git("clone", "-q", source, str(path))
    (path / ".claude").mkdir()
    (path / "docs").mkdir()
    return os.path.realpath(str(path))


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """Workspace A's checkout, workspace B's repo, and their shared registry.

    Both workspaces are created by the production resolver, which also
    writes each repo's ``.claude/pd/workspace.json``; the orchestrator's own
    resolution then finds A from the checkout alone.
    """
    monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
    monkeypatch.delenv("WORKSPACE_UUID", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    registry = tmp_path / "registry"
    registry.mkdir()
    db_path = str(registry / "entities.db")
    db = EntityDatabase(db_path)
    repo = _make_pd_repo(tmp_path / "repo", "root of workspace A")
    other_repo = _make_pd_repo(tmp_path / "other", "root of workspace B")
    artifacts = os.path.join(repo, "docs")
    for subdir in ("features", "projects", "brainstorms"):
        os.makedirs(os.path.join(artifacts, subdir))
    ws_a = resolve_workspace_uuid(repo, db_path=db_path)
    ws_b = resolve_workspace_uuid(other_repo, db_path=db_path)
    assert ws_a != ws_b
    yield {
        "db": db, "db_path": db_path, "home": str(home), "repo": repo,
        "artifacts": artifacts, "A": ws_a, "B": ws_b,
    }
    db.close()


def _session_start(c, project_root=None) -> dict:
    """Run the orchestrator as session-start.sh does; return its JSON line.

    *project_root* defaults to workspace A's checkout.
    """
    project_root = project_root or c["repo"]
    env = {
        key: value for key, value in os.environ.items()
        if key not in ("ENTITY_WORKSPACE_UUID", "WORKSPACE_UUID")
    }
    env.update(HOME=c["home"], ENTITY_DB_PATH=c["db_path"],
               PYTHONPATH=_HOOKS_LIB)
    proc = subprocess.run(
        [sys.executable, "-m", _ORCHESTRATOR,
         "--project-root", project_root,
         "--artifacts-root", "docs",
         "--entity-db", c["db_path"]],
        capture_output=True, text=True, env=env, cwd=project_root, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _register(db, kind, workspace, *, seq, slug, status="active", **kw):
    """Register one entity and return its row."""
    entity_uuid = db.register_entity(
        kind, name=slug.replace("-", " "), seq=seq, slug=slug, status=status,
        workspace_uuid=workspace, **kw,
    )
    return db.get_entity_by_uuid(entity_uuid)


def _write_meta(c, entity_id, **meta) -> None:
    """A feature projection in A's checkout."""
    feature_dir = os.path.join(c["artifacts"], "features", entity_id)
    os.makedirs(feature_dir, exist_ok=True)
    with open(os.path.join(feature_dir, ".meta.json"), "w") as f:
        json.dump(meta, f)


def _archive_state(db) -> dict:
    """Every entity row's ``is_archived`` and ``updated_at``, by uuid."""
    return {
        row["uuid"]: (row["is_archived"], row["updated_at"])
        for row in db.list_entities(include_deleted=True)
    }


def _workflow_rows(db) -> list[dict]:
    """Every workflow_phases row, in a stable order."""
    return sorted(db.list_workflow_phases(), key=lambda row: row["type_id"])


def _cascade_ready_events(db, type_id) -> list[dict]:
    return db.query_phase_events(type_id=type_id, event_type="cascade_ready")


# ---------------------------------------------------------------------------
# W1.1: Task 1 no longer archives or re-statuses from the checkout's files
# ---------------------------------------------------------------------------


def test_no_archive_when_the_checkout_holds_no_meta_json(checkout):
    """Registered features and projects whose directories hold no
    ``.meta.json`` (a fresh clone: the file is gitignored) keep every row's
    ``is_archived`` and ``updated_at``."""
    c, db = checkout, checkout["db"]
    features = [
        _register(db, "feature", c["A"], seq=1, slug="alpha"),
        _register(db, "feature", c["A"], seq=2, slug="beta",
                  status="completed"),
    ]
    project = _register(db, "project", c["A"], seq=3, slug="roadmap")
    for feature in features:
        feature_dir = os.path.join(c["artifacts"], "features",
                                   feature["entity_id"])
        os.makedirs(feature_dir)
        with open(os.path.join(feature_dir, "spec.md"), "w") as f:
            f.write("# spec\n")
    os.makedirs(os.path.join(c["artifacts"], "projects", project["entity_id"]))
    before = _archive_state(db)

    result = _session_start(c)

    assert _archive_state(db) == before
    assert result["errors"] == []


def test_no_brainstorm_archive_when_its_prd_is_missing(checkout):
    """A registered brainstorm whose ``.prd.md`` this checkout lacks (a branch
    or worktree cut before the file landed) stays unarchived. The same
    session still registers the ``.prd.md`` files the checkout does hold."""
    c, db = checkout, checkout["db"]
    missing_uuid = db.register_entity(
        "brainstorm", name="elsewhere", display_id="20260901-000000-elsewhere",
        artifact_path="docs/brainstorms/20260901-000000-elsewhere.prd.md",
        status="active", workspace_uuid=c["A"],
    )
    with open(os.path.join(c["artifacts"], "brainstorms",
                           "20260902-000000-here.prd.md"), "w") as f:
        f.write("# here\n")

    result = _session_start(c)

    missing = db.get_entity_by_uuid(missing_uuid)
    assert missing["is_archived"] == 0, missing
    registered = db.get_entity("brainstorm:20260902-000000-here")
    assert registered is not None
    assert registered["workspace_uuid"] == c["A"]
    assert result["entity_sync"]["registered"] == 1
    assert result["errors"] == []


def test_no_status_regression_from_a_stale_meta_json(checkout):
    """A stale projection saying ``active`` for a feature the registry has
    completed leaves the registry's status ``completed``."""
    c, db = checkout, checkout["db"]
    feature = _register(db, "feature", c["A"], seq=4, slug="gamma",
                        status="completed")
    _write_meta(c, feature["entity_id"], id="004", slug="gamma",
                status="active", mode="standard",
                lastCompletedPhase="specify")

    result = _session_start(c)

    assert db.get_entity_by_uuid(feature["uuid"])["status"] == "completed"
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# W1.3: Task 2's .meta.json -> workflow_phases writer is gone
# ---------------------------------------------------------------------------


def test_no_workflow_row_from_a_namesake_meta_json(checkout):
    """A's checkout holds namesake projections of two features only B holds:
    one with no workflow row, one whose row is behind the projection. The
    session creates no row and changes none."""
    c, db = checkout, checkout["db"]
    rowless = _register(db, "feature", c["B"], seq=5, slug="delta")
    with_row = _register(db, "feature", c["B"], seq=6, slug="epsilon")
    db.create_workflow_phase(
        with_row["type_id"], workspace_uuid=c["B"], workflow_phase="specify",
        kanban_column="backlog", mode="standard",
    )
    for feature in (rowless, with_row):
        _write_meta(c, feature["entity_id"], status="active", mode="standard",
                    lastCompletedPhase="design")
    rows_before = _workflow_rows(db)

    result = _session_start(c)

    assert db.get_workflow_phase(rowless["type_id"]) is None
    assert _workflow_rows(db) == rows_before
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# W1.7: cascade recovery is its own task, scoped to A, writing by uuid
# ---------------------------------------------------------------------------


def test_cascade_recovery_rolls_up_the_sessions_parent_by_uuid(checkout):
    """``project:P001`` is held by A and B, each with a completed child and no
    stored progress. A's session start rolls A's parent up, by uuid, and
    leaves B's parent untouched."""
    c, db = checkout, checkout["db"]
    parents = {}
    for workspace, seq, slug in ((c["A"], 7, "kid-a"), (c["B"], 8, "kid-b")):
        parent_uuid = seed_legacy_entity(
            db, "project", "P001", "shared project",
            workspace_uuid=workspace, status="active",
        )
        _register(db, "feature", workspace, seq=seq, slug=slug,
                  status="completed", parent_uuid=parent_uuid)
        parents[workspace] = parent_uuid
    b_parent_before = dict(db.get_entity_by_uuid(parents[c["B"]]))

    result = _session_start(c)

    a_parent = db.get_entity_by_uuid(parents[c["A"]])
    a_progress = parse_metadata(a_parent["metadata"]).get("progress")
    assert a_progress == compute_progress(db, parents[c["A"]]) == 1.0
    assert dict(db.get_entity_by_uuid(parents[c["B"]])) == b_parent_before
    assert result["cascade_recovery"] == 1
    assert result["errors"] == []


def test_cascade_recovery_rescores_only_the_sessions_objective(checkout):
    """An objective type_id held by A and B, each with a met key result and
    a stale stored score of 0.0. A's session start rescores A's objective,
    by uuid, and leaves B's objective and key result untouched: the
    objective scan lists only A's entities."""
    c, db = checkout, checkout["db"]
    objectives, key_results = {}, {}
    for workspace in (c["A"], c["B"]):
        objective = _register(db, "objective", workspace, seq=60,
                              slug="shared-goal", metadata={"score": 0.0})
        key_result = _register(
            db, "key_result", workspace, seq=61, slug="goal-met",
            parent_uuid=objective["uuid"],
            metadata={"metric_type": "baseline_target", "score": 1.0},
        )
        objectives[workspace] = objective["uuid"]
        key_results[workspace] = key_result["uuid"]
    assert (db.get_entity_by_uuid(objectives[c["A"]])["type_id"]
            == db.get_entity_by_uuid(objectives[c["B"]])["type_id"])
    b_objective_before = dict(db.get_entity_by_uuid(objectives[c["B"]]))
    b_key_result_before = dict(db.get_entity_by_uuid(key_results[c["B"]]))

    result = _session_start(c)

    a_meta = parse_metadata(db.get_entity_by_uuid(objectives[c["A"]])["metadata"])
    assert a_meta["score"] == 1.0
    assert (dict(db.get_entity_by_uuid(objectives[c["B"]]))
            == b_objective_before)
    assert (dict(db.get_entity_by_uuid(key_results[c["B"]]))
            == b_key_result_before)
    assert result["cascade_recovery"] == 1
    assert result["errors"] == []


def test_a_rollup_stops_at_the_first_ancestor_outside_the_workspace(checkout):
    """A's completed feature, under A's project, under B's programme. A's
    session start rolls A's project up and stops there: B's programme is
    B's to recover."""
    c, db = checkout, checkout["db"]
    b_programme = seed_legacy_entity(
        db, "project", "P009", "B's programme", workspace_uuid=c["B"],
        status="active",
    )
    a_project = _register(db, "project", c["A"], seq=40, slug="a-project",
                          parent_uuid=b_programme)
    _register(db, "feature", c["A"], seq=41, slug="finished",
              status="completed", parent_uuid=a_project["uuid"])
    b_programme_before = dict(db.get_entity_by_uuid(b_programme))

    result = _session_start(c)

    a_progress = parse_metadata(
        db.get_entity_by_uuid(a_project["uuid"])["metadata"]
    ).get("progress")
    assert a_progress == 1.0
    assert dict(db.get_entity_by_uuid(b_programme)) == b_programme_before
    assert result["cascade_recovery"] == 1
    assert result["errors"] == []


def test_dependency_flip_by_uuid_for_a_shared_type_id(checkout):
    """A blocked dependent in A whose type_id B also holds flips to
    ``ready`` once its blocker is resolved; B's namesake is untouched, and
    the ``cascade_ready`` event carries A's project id."""
    c, db = checkout, checkout["db"]
    blocker = _register(db, "feature", c["A"], seq=9, slug="blocker",
                        status="completed")
    dependent = _register(db, "feature", c["A"], seq=10, slug="dependent",
                          status="blocked")
    namesake = _register(db, "feature", c["B"], seq=10, slug="dependent")
    assert namesake["type_id"] == dependent["type_id"]
    db.add_dependency(dependent["uuid"], blocker["uuid"])
    namesake_before = dict(db.get_entity_by_uuid(namesake["uuid"]))

    result = _session_start(c)

    assert db.get_entity_by_uuid(dependent["uuid"])["status"] == "ready"
    assert dict(db.get_entity_by_uuid(namesake["uuid"])) == namesake_before
    events = _cascade_ready_events(db, dependent["type_id"])
    assert [event["project_id"] for event in events] == [
        dependent["project_id"]
    ]
    assert result["dependency_cleanup"] == 1
    assert result["errors"] == []


def test_a_flip_in_a_workspace_without_a_legacy_id_records_its_uuid(
    checkout, tmp_path,
):
    """A second clone of A's repository resolves to its own workspace, which
    has no legacy project id. A dependent flipped there records that
    workspace's uuid as the ``cascade_ready`` event's project id, never
    ``__unknown__``."""
    c, db = checkout, checkout["db"]
    clone = _clone_pd_repo(c["repo"], tmp_path / "second-clone")
    ws_clone = resolve_workspace_uuid(clone, db_path=c["db_path"])
    assert ws_clone not in (c["A"], c["B"])
    blocker = _register(db, "feature", ws_clone, seq=51, slug="landed",
                        status="completed")
    dependent = _register(db, "feature", ws_clone, seq=52, slug="waiting",
                          status="blocked")
    assert dependent["project_id"] is None
    db.add_dependency(dependent["uuid"], blocker["uuid"])

    result = _session_start(c, project_root=clone)

    assert db.get_entity_by_uuid(dependent["uuid"])["status"] == "ready"
    events = _cascade_ready_events(db, dependent["type_id"])
    assert [event["project_id"] for event in events] == [ws_clone]
    assert result["dependency_cleanup"] == 1
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# W1.8: Task 3 lists and flips only the session's workspace
# ---------------------------------------------------------------------------


def test_task3_never_flips_another_workspaces_blocked_entity(checkout):
    """B's blocked entity, whose blocker is resolved, stays blocked through
    A's session start; A's own such entity flips."""
    c, db = checkout, checkout["db"]
    flipped = {}
    for workspace, seq in ((c["A"], 11), (c["B"], 12)):
        blocker = _register(db, "feature", workspace, seq=seq,
                            slug=f"done-{seq}", status="completed")
        dependent = _register(db, "feature", workspace, seq=seq + 10,
                              slug=f"waiting-{seq}", status="blocked")
        db.add_dependency(dependent["uuid"], blocker["uuid"])
        flipped[workspace] = dependent
    b_dependent_before = dict(db.get_entity_by_uuid(flipped[c["B"]]["uuid"]))

    result = _session_start(c)

    b_dependent = db.get_entity_by_uuid(flipped[c["B"]]["uuid"])
    assert b_dependent["status"] == "blocked"
    assert dict(b_dependent) == b_dependent_before
    assert _cascade_ready_events(db, flipped[c["B"]]["type_id"]) == []
    assert db.get_entity_by_uuid(flipped[c["A"]]["uuid"])["status"] == "ready"
    assert result["dependency_cleanup"] == 1
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# W1.7 / W1.8: with no workspace, Tasks 2 and 3 are skipped, and say so
# ---------------------------------------------------------------------------


def test_an_unresolved_workspace_skips_tasks_2_and_3(checkout, tmp_path):
    """A session start in a directory whose workspace cannot be resolved
    (no ``.claude/``: pd is not enabled there) runs neither cascade recovery
    nor the dependency cleanup, since unscoped both would write every
    workspace's rows, and records each skip under ``errors``. B's missed
    cascade and B's stale blocked entity are left for B's own session."""
    c, db = checkout, checkout["db"]
    parent_uuid = seed_legacy_entity(
        db, "project", "P002", "B's project", workspace_uuid=c["B"],
        status="active",
    )
    _register(db, "feature", c["B"], seq=31, slug="finished-kid",
              status="completed", parent_uuid=parent_uuid)
    blocker = _register(db, "feature", c["B"], seq=32, slug="done",
                        status="completed")
    dependent = _register(db, "feature", c["B"], seq=33, slug="stuck",
                          status="blocked")
    db.add_dependency(dependent["uuid"], blocker["uuid"])
    not_pd = tmp_path / "not-pd"
    (not_pd / "docs").mkdir(parents=True)
    before = _archive_state(db)

    result = _session_start(c, project_root=os.path.realpath(str(not_pd)))

    assert db.get_entity_by_uuid(dependent["uuid"])["status"] == "blocked"
    assert "progress" not in parse_metadata(
        db.get_entity_by_uuid(parent_uuid)["metadata"]
    )
    assert _archive_state(db) == before
    assert result["cascade_recovery"] is None
    assert result["dependency_cleanup"] is None
    assert result["errors"][0].startswith("workspace_uuid: ")
    assert result["errors"][1:] == [
        "cascade_recovery: skipped: workspace unresolved",
        "dependency_freshness: skipped: workspace unresolved",
    ]
