"""Task 1C: brainstorm registration looks up, and inserts, in one workspace only.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W1 change 1,
which keeps Part 1 of the brainstorm helper: the registration of new
``.prd.md`` files. Task 1C's execution note makes it exact:

1. **Existence is scoped:** a ``.prd.md`` file is skipped when the
   registration workspace holds a row for its type_id, whatever that row's
   status, archived or soft-deleted too. Rows other workspaces hold for the
   type_id are neither read nor written.
2. **Registration only inserts** (``register_entity``): no existing row's
   status, name, artifact_path or flags change.
3. **The counts are exact:** ``registered`` is rows inserted; ``skipped`` is
   files whose type_id the registration workspace already holds.
4. **No workspace, no row:** when no workspace resolves, nothing is
   registered anywhere.

**The defect** (Phase 1 live-copy check F1, run 2): existence was read with
the unscoped ``db.get_entity(type_id)``, which answers None for a type_id two
workspaces hold. The session's own ``promoted`` row was then upserted back to
``active``, with an ``entity_status_changed`` event, at every session start,
and reported as registered. A type_id only another workspace held was found
and skipped, so this workspace never registered its own file.

**How a session starts here:** as in ``test_session_start_reads_no_files``,
the orchestrator runs the way ``session-start.sh`` runs it, against a temp
registry, a temp HOME and temp git repos. The per-row matrix calls
``sync_entity_statuses`` in-process, with the arguments the orchestrator
passes it.

**The registry is v2-generation**, the generation the live one is, so every
status write also lands in the ``events`` ledger: "no event written" is
checked in both ``phase_events`` and ``events``.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys

import pytest

from entity_registry import schema_v2
from entity_registry.database import EntityDatabase
from entity_registry.project_identity import (
    _compute_legacy_project_id,
    _insert_workspace_row_if_absent,
    resolve_workspace_uuid,
)
from reconciliation_orchestrator.entity_status import sync_entity_statuses

# Imported at collection time, not inside the fixture: the first import of
# rebuild_tool registers the events/views/axes DDL owners into
# schema_v2.DDL_REGISTRY, once per process, and the registry snapshot below
# must include them from its first run (test_database.py documents how a
# lazy import breaks every later v2 registry with "no such table: events").
from entity_registry import rebuild_tool

_HOOKS_LIB = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_ORCHESTRATOR = "reconciliation_orchestrator"

# The tables a registration, or a status rewrite, writes.
_WRITTEN_TABLES = ("entities", "phase_events", "events")

# A brainstorm the F1 live copy re-statused: pedantic-drip held it as
# 'promoted', another workspace as 'active', and pedantic-drip tracks its file.
_SHARED_STEM = "20260318-025248-three-claws-v2-protocol"

# Every status a brainstorm row can hold: its lifecycle machine's four
# (workflow_engine/router.py), registration's 'active', and two values rows
# of other kinds carry.
_ROW_STATUSES = (
    "draft", "reviewing", "promoted", "abandoned", "active", "planned",
    "completed",
)

_NO_WORKSPACE_ERRORS_AFTER_THE_FIRST = [
    "cascade_recovery: skipped: workspace unresolved",
    "dependency_freshness: skipped: workspace unresolved",
]


@pytest.fixture(autouse=True)
def _reset_ddl_registry_for_v2_fixtures():
    """Snapshot/restore ``schema_v2.DDL_REGISTRY`` around every test.

    Building a v2 registry registers the axis vocabulary triggers as
    production behaviour; without the restore they leak into whatever test
    runs next in this process (test_database.py's identically-named
    fixture).
    """
    original_registry = list(schema_v2.DDL_REGISTRY)
    yield
    schema_v2.DDL_REGISTRY[:] = original_registry


def _git(*args: str) -> None:
    """git with a fixed identity, so commits need no user config."""
    subprocess.run(
        ["git", "-c", "user.name=1c", "-c", "user.email=1c@example.invalid",
         *args],
        check=True, capture_output=True,
    )


def _make_pd_repo(path, root_message: str) -> str:
    """A git repo with its own root commit and a ``.claude/`` directory.

    The root commit is the repo's legacy project id, so each repo gets its
    own message. ``.claude/`` marks pd as enabled: workspace resolution
    requires it. It stays untracked, so a clone of the repo lacks it.
    """
    _git("init", "-q", "-b", "main", str(path))
    _git("-C", str(path), "commit", "-q", "--allow-empty", "-m", root_message)
    (path / ".claude").mkdir()
    return os.path.realpath(str(path))


def _register_workspace(repo: str, db_path: str) -> str:
    """Resolve *repo*'s workspace with the production resolver, and record
    its ``workspaces`` row.

    On a v2-generation registry the resolver writes
    ``.claude/pd/workspace.json`` but not the row: ``_ensure_workspace_row``
    skips a ``schema_version`` below 11, and the v2 lineage's reads 7. The
    live registry holds its rows from before its cutover, so the fixture
    writes the row with the row writer the resolver uses on v1 files.
    """
    workspace = resolve_workspace_uuid(repo, db_path=db_path)
    conn = sqlite3.connect(db_path)
    try:
        _insert_workspace_row_if_absent(
            conn, workspace, repo, _compute_legacy_project_id(repo),
        )
        conn.commit()
    finally:
        conn.close()
    return workspace


@pytest.fixture
def checkouts(tmp_path, monkeypatch):
    """Workspace A's checkout and workspace B's repo, sharing one v2 registry.

    Each repo's ``workspace.json`` names its workspace, so the orchestrator
    resolves A from A's checkout alone.
    """
    monkeypatch.delenv("ENTITY_WORKSPACE_UUID", raising=False)
    monkeypatch.delenv("WORKSPACE_UUID", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    registry = tmp_path / "registry"
    registry.mkdir()
    db_path = str(registry / "entities.db")
    rebuild_tool.build_staging_database(db_path)
    db = EntityDatabase(db_path)
    assert db._is_v2_generation, "fixture precondition: a v2 registry"
    repo = _make_pd_repo(tmp_path / "repo-a", "root of workspace A")
    other_repo = _make_pd_repo(tmp_path / "repo-b", "root of workspace B")
    os.makedirs(os.path.join(repo, "docs", "brainstorms"))
    ws_a = _register_workspace(repo, db_path)
    ws_b = _register_workspace(other_repo, db_path)
    assert ws_a != ws_b
    yield {
        "db": db, "db_path": db_path, "home": str(home), "repo": repo,
        "A": ws_a, "B": ws_b,
    }
    db.close()


def _brainstorm(db, workspace: str, stem: str, status: str) -> str:
    """Register brainstorm *stem* in *workspace*; return its uuid."""
    return db.register_entity(
        "brainstorm", name=stem, display_id=stem, status=status,
        artifact_path=f"docs/brainstorms/{stem}.prd.md",
        workspace_uuid=workspace,
    )


def _write_prd(checkout: str, stem: str) -> str:
    """Write ``docs/brainstorms/<stem>.prd.md`` in *checkout*; return its
    path relative to the checkout."""
    relative = os.path.join("docs", "brainstorms", f"{stem}.prd.md")
    with open(os.path.join(checkout, relative), "w") as f:
        f.write(f"# {stem}\n")
    return relative


def _track_prd(checkout: str, stem: str) -> None:
    """Commit brainstorm *stem*'s ``.prd.md`` in *checkout*, as a tracked
    brainstorm file is committed."""
    _git("-C", checkout, "add", _write_prd(checkout, stem))
    _git("-C", checkout, "commit", "-q", "-m", f"brainstorm {stem}")


def _session_start(c, project_root: str | None = None) -> dict:
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


def _sync_as_orchestrator(c) -> dict:
    """Task 1 in-process, with the arguments the orchestrator passes for
    A's checkout (``reconciliation_orchestrator/__main__.py``)."""
    return sync_entity_statuses(
        c["db"], os.path.join(c["repo"], "docs"),
        project_id=_compute_legacy_project_id(c["repo"]),
        artifacts_root="docs", project_root=c["repo"],
        workspace_uuid=c["A"],
    )


def _snapshot(db_path: str) -> dict[str, list[dict]]:
    """Every row, every column, of the tables a registration writes."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return {
            table: [dict(row) for row in conn.execute(
                f"SELECT * FROM {table} ORDER BY rowid"
            )]
            for table in _WRITTEN_TABLES
        }
    finally:
        conn.close()


def _row(c, entity_uuid: str) -> dict:
    """Every column of one entity row, soft-deleted or not."""
    return c["db"].get_entity_by_uuid(entity_uuid, include_deleted=True)


def _brainstorm_rows(c, workspace: str) -> list[dict]:
    """The brainstorm rows *workspace* holds, soft-deleted ones included."""
    return c["db"].list_entities(
        entity_type="brainstorm", workspace_uuid=workspace,
        include_deleted=True,
    )


# ---------------------------------------------------------------------------
# 1C contract 1-3: a session start in A, with the type_id held by A, B or both
# ---------------------------------------------------------------------------


def test_a_type_id_both_workspaces_hold_is_skipped_and_left_byte_identical(
    checkouts,
):
    """The F1 live-copy shape: A holds the type_id as 'promoted', B as
    'active', and A's checkout tracks its file. A session start in A leaves
    both rows byte-identical, writes no event, and counts the file skipped.

    Before task 1C, A's row became 'active', with an
    ``entity_status_changed`` phase event and ``events`` row, and the run
    reported it registered.
    """
    c, db = checkouts, checkouts["db"]
    a_uuid = _brainstorm(db, c["A"], _SHARED_STEM, "promoted")
    b_uuid = _brainstorm(db, c["B"], _SHARED_STEM, "active")
    _track_prd(c["repo"], _SHARED_STEM)
    a_before, b_before = _row(c, a_uuid), _row(c, b_uuid)
    before = _snapshot(c["db_path"])

    result = _session_start(c)

    assert _row(c, a_uuid) == a_before
    assert _row(c, b_uuid) == b_before
    assert _snapshot(c["db_path"]) == before
    assert result["entity_sync"] == {
        "registered": 0, "skipped": 1, "warnings": [],
    }
    assert result["errors"] == []


def test_a_type_id_only_another_workspace_holds_is_registered_in_this_one(
    checkouts,
):
    """B alone holds the type_id, and A's checkout tracks its file. A
    session start in A inserts A's own row, as a new ``.prd.md`` is
    registered (kind brainstorm, status 'active', the artifact path under
    the artifacts root), with the insert path's creation events, and leaves
    B's row and events alone.

    Before task 1C, B's row hid A's file: skipped, nothing registered in A.
    """
    c, db = checkouts, checkouts["db"]
    b_uuid = _brainstorm(db, c["B"], _SHARED_STEM, "active")
    _track_prd(c["repo"], _SHARED_STEM)
    b_before = _row(c, b_uuid)
    before = _snapshot(c["db_path"])

    result = _session_start(c)

    assert result["entity_sync"] == {
        "registered": 1, "skipped": 0, "warnings": [],
    }
    [a_row] = _brainstorm_rows(c, c["A"])
    assert {
        key: a_row[key] for key in (
            "type_id", "kind", "name", "status", "artifact_path",
            "is_archived", "is_deleted",
        )
    } == {
        "type_id": f"brainstorm:{_SHARED_STEM}", "kind": "brainstorm",
        "name": _SHARED_STEM, "status": "active",
        "artifact_path": f"docs/brainstorms/{_SHARED_STEM}.prd.md",
        "is_archived": 0, "is_deleted": 0,
    }
    assert _row(c, b_uuid) == b_before
    after = _snapshot(c["db_path"])
    for table in _WRITTEN_TABLES:
        assert after[table][:len(before[table])] == before[table], (
            f"{table}: an existing row changed"
        )
    new_phase_events = after["phase_events"][len(before["phase_events"]):]
    assert [
        (event["type_id"], event["event_type"], event["project_id"])
        for event in new_phase_events
    ] == [(f"brainstorm:{_SHARED_STEM}", "entity_created",
           _compute_legacy_project_id(c["repo"]))]
    new_events = after["events"][len(before["events"]):]
    assert [
        (event["entity_uuid"], event["event_type"]) for event in new_events
    ] == [(a_row["uuid"], "entity_created")]
    assert result["errors"] == []


def test_a_second_session_start_after_the_skip_changes_nothing(checkouts):
    """A session start right after the both-workspaces skip writes nothing
    and counts the file skipped again; A's row is still 'promoted'.

    Before task 1C, the first run re-statused A's row and every later run
    upserted it again, a no-op reported as registered.
    """
    c, db = checkouts, checkouts["db"]
    a_uuid = _brainstorm(db, c["A"], _SHARED_STEM, "promoted")
    _brainstorm(db, c["B"], _SHARED_STEM, "active")
    _track_prd(c["repo"], _SHARED_STEM)
    _session_start(c)
    after_first = _snapshot(c["db_path"])

    result = _session_start(c)

    assert _snapshot(c["db_path"]) == after_first
    assert result["entity_sync"] == {
        "registered": 0, "skipped": 1, "warnings": [],
    }
    assert _row(c, a_uuid)["status"] == "promoted"


def test_a_second_session_start_after_the_registration_changes_nothing(
    checkouts,
):
    """A session start right after A registered its own row (B holds the
    type_id too) writes nothing and counts the file skipped: A holds exactly
    the one row the first run inserted.

    Before task 1C, neither run registered A's row.
    """
    c, db = checkouts, checkouts["db"]
    _brainstorm(db, c["B"], _SHARED_STEM, "active")
    _track_prd(c["repo"], _SHARED_STEM)
    _session_start(c)
    after_first = _snapshot(c["db_path"])

    result = _session_start(c)

    assert _snapshot(c["db_path"]) == after_first
    assert result["entity_sync"] == {
        "registered": 0, "skipped": 1, "warnings": [],
    }
    assert len(_brainstorm_rows(c, c["A"])) == 1


# ---------------------------------------------------------------------------
# 1C contract 1: any row the workspace holds counts, whatever it holds
# ---------------------------------------------------------------------------


def test_an_archived_brainstorm_this_workspace_holds_stays_archived_and_unchanged(
    checkouts,
):
    """Regression pin: an archived brainstorm only A holds, with its file
    back in A's checkout (a branch cut before the cleanup), is skipped: it
    stays archived and byte-identical, and no event is written.
    Registration never un-archives."""
    c, db = checkouts, checkouts["db"]
    stem = "20260901-000000-shelved"
    a_uuid = _brainstorm(db, c["A"], stem, "promoted")
    db.set_archived(a_uuid)
    _track_prd(c["repo"], stem)
    a_before = _row(c, a_uuid)
    assert a_before["is_archived"] == 1, "fixture precondition: archived"
    before = _snapshot(c["db_path"])

    result = _session_start(c)

    assert _row(c, a_uuid) == a_before
    assert _snapshot(c["db_path"]) == before
    assert result["entity_sync"] == {
        "registered": 0, "skipped": 1, "warnings": [],
    }


def test_a_soft_deleted_brainstorm_this_workspace_holds_is_not_resurrected(
    checkouts,
):
    """Regression pin: a soft-deleted brainstorm only A holds, with its file
    in A's checkout, stays deleted and byte-identical, no event is written,
    and the file counts as skipped: registration never resurrects.

    Before task 1C, ``get_entity`` answered None for the deleted row, so the
    run upserted it (a no-op for an 'active' row) and reported it
    registered.
    """
    c, db = checkouts, checkouts["db"]
    stem = "20260902-000000-withdrawn"
    a_uuid = _brainstorm(db, c["A"], stem, "active")
    db.set_deleted(f"brainstorm:{stem}", workspace_uuid=c["A"])
    _track_prd(c["repo"], stem)
    a_before = _row(c, a_uuid)
    assert a_before["is_deleted"] == 1, "fixture precondition: soft-deleted"
    before = _snapshot(c["db_path"])

    result = _session_start(c)

    assert _row(c, a_uuid) == a_before
    assert _snapshot(c["db_path"]) == before
    assert result["entity_sync"] == {
        "registered": 0, "skipped": 1, "warnings": [],
    }


@pytest.mark.parametrize("flag", ["none", "archived", "soft_deleted"])
@pytest.mark.parametrize("status", _ROW_STATUSES)
def test_no_row_this_workspace_holds_is_rewritten(checkouts, status, flag):
    """Whatever A's row holds (any status, archived or soft-deleted), with
    B holding the type_id too and A's checkout tracking its file,
    registration leaves every row byte-identical, writes no event, and
    counts the file skipped.

    Before task 1C, each case wrote: A's row re-statused to 'active', or,
    already 'active', a no-op upsert reported as registered.
    """
    c, db = checkouts, checkouts["db"]
    a_uuid = _brainstorm(db, c["A"], _SHARED_STEM, status)
    if flag == "archived":
        db.set_archived(a_uuid)
    elif flag == "soft_deleted":
        db.set_deleted(f"brainstorm:{_SHARED_STEM}", workspace_uuid=c["A"])
    _brainstorm(db, c["B"], _SHARED_STEM, "active")
    _write_prd(c["repo"], _SHARED_STEM)
    before = _snapshot(c["db_path"])

    result = _sync_as_orchestrator(c)

    assert _snapshot(c["db_path"]) == before
    assert result == {"registered": 0, "skipped": 1, "warnings": []}


# ---------------------------------------------------------------------------
# 1C contract 4: with no workspace resolved, nothing is registered anywhere
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stems", [
    [_SHARED_STEM],
    [_SHARED_STEM, "20260903-000000-fresh"],
], ids=["held-by-B", "held-by-B-and-new"])
def test_a_checkout_whose_workspace_does_not_resolve_registers_nothing(
    checkouts, tmp_path, stems,
):
    """A directory where pd is not enabled (no ``.claude/``, no git) resolves
    no workspace, and its legacy project id, a hash of its path, names none.
    Its brainstorm files register nothing anywhere, and the orchestrator
    records what it recorded before task 1C when a registration was due:
    the workspace error, the Task 2 and 3 skips, and Task 1's warning.

    With the new file (held-by-B-and-new) that record is unchanged. With
    only a file B holds, B's row is no longer read: before task 1C it made
    the file count as skipped, with no warning.
    """
    c, db = checkouts, checkouts["db"]
    _brainstorm(db, c["B"], _SHARED_STEM, "active")
    not_pd = tmp_path / "not-pd"
    (not_pd / "docs" / "brainstorms").mkdir(parents=True)
    project_root = os.path.realpath(str(not_pd))
    for stem in stems:
        _write_prd(project_root, stem)
    before = _snapshot(c["db_path"])

    result = _session_start(c, project_root=project_root)

    assert _snapshot(c["db_path"]) == before
    legacy_id = _compute_legacy_project_id(project_root)
    assert result["entity_sync"] == {
        "registered": 0, "skipped": 0,
        "warnings": [
            f"brainstorms: register_entity(): project_id={legacy_id!r} has no "
            f"matching workspaces.project_id_legacy row. Either pass "
            f"workspace_uuid directly or pre-register the workspace."
        ],
    }
    assert result["errors"][0].startswith("workspace_uuid: ")
    assert result["errors"][1:] == _NO_WORKSPACE_ERRORS_AFTER_THE_FIRST


def test_a_checkout_resolved_by_its_legacy_id_looks_up_that_workspace_only(
    checkouts, tmp_path,
):
    """A second clone of A's repository, without ``.claude/``, resolves no
    workspace of its own (the orchestrator records why, and skips Tasks 2
    and 3), so Task 1 takes the workspace its legacy project id names: A's,
    since a clone shares the root commit (C5b; design W4.1 resolves a
    writer's workspace the same way). Existence is checked in A alone: A's
    'promoted' row and B's namesake stay byte-identical, and the file counts
    as skipped.

    Before task 1C the unscoped check answered None for the shared type_id,
    and the run re-statused A's row from the clone.
    """
    c, db = checkouts, checkouts["db"]
    a_uuid = _brainstorm(db, c["A"], _SHARED_STEM, "promoted")
    _brainstorm(db, c["B"], _SHARED_STEM, "active")
    _track_prd(c["repo"], _SHARED_STEM)
    clone = tmp_path / "clone"
    _git("clone", "-q", c["repo"], str(clone))
    clone_root = os.path.realpath(str(clone))
    assert not os.path.exists(os.path.join(clone_root, ".claude")), (
        "fixture precondition: pd is not enabled in the clone"
    )
    a_before = _row(c, a_uuid)
    before = _snapshot(c["db_path"])

    result = _session_start(c, project_root=clone_root)

    assert _row(c, a_uuid) == a_before
    assert _snapshot(c["db_path"]) == before
    assert result["entity_sync"] == {
        "registered": 0, "skipped": 1, "warnings": [],
    }
    assert result["errors"][0].startswith("workspace_uuid: ")
    assert result["errors"][1:] == _NO_WORKSPACE_ERRORS_AFTER_THE_FIRST
