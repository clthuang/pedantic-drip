"""Task 1C: brainstorm registration checks existence in the session's workspace
and only inserts, and only a type_id no workspace holds.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W1 change 1,
which keeps Part 1 of the brainstorm helper: the registration of new
``.prd.md`` files. Task 1C's execution note, as amended after the Phase R
premortem, makes it exact:

1. **Existence is scoped:** a ``.prd.md`` file is skipped when the
   registration workspace holds a row for its type_id, whatever that row's
   status, archived or soft-deleted too.
2. **Registration only inserts** (``register_entity``): no existing row's
   status, name, artifact_path or flags change.
3. **Another workspace's type_id is skipped too** (the amendment): a file
   whose type_id only another workspace holds, in any row, is not
   registered, and the warnings name it. A row here would be that
   workspace's namesake, and the unscoped ``get_entity`` answers None for a
   type_id two workspaces hold, so the other workspace's brainstorm would
   stop resolving by type_id. A row is inserted only when no workspace
   holds the type_id, until workflow rows are keyed per entity (Phase R).
4. **The counts are exact:** ``registered`` is rows inserted; ``skipped`` is
   files whose type_id a workspace already holds, this one or another.
5. **No workspace, no row:** when no workspace resolves, nothing is
   registered anywhere.

**The defect** (Phase 1 live-copy check F1, run 2): existence was read with
the unscoped ``db.get_entity(type_id)``, which answers None for a type_id two
workspaces hold. The session's own ``promoted`` row was then upserted back to
``active``, with an ``entity_status_changed`` event, at every session start,
and reported as registered. A type_id only another workspace held was found
and skipped silently; the amendment keeps that skip and names it.

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
from entity_registry.database import EntityDatabase, _UNKNOWN_WORKSPACE_UUID
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


def _held_elsewhere(stem: str) -> str:
    """Task 1's warning for a skipped file whose type_id only another
    workspace holds (the task 1C amendment)."""
    return (
        f"brainstorms: brainstorm:{stem} is held by another workspace, so it "
        f"is not registered here until workflow rows are keyed per entity "
        f"(Phase R)"
    )


def _record_registrations(monkeypatch, db) -> list[dict]:
    """Record the keyword arguments of every ``db.register_entity`` call,
    each still made."""
    calls: list[dict] = []
    original = db.register_entity

    def recording_register_entity(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(db, "register_entity", recording_register_entity)
    return calls


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


@pytest.mark.parametrize("b_flag", ["none", "archived", "soft_deleted"])
def test_a_type_id_only_another_workspace_holds_is_skipped_and_named(
    checkouts, b_flag,
):
    """B alone holds the type_id, in a plain, archived or soft-deleted row,
    and A's checkout tracks its file. A session start in A registers
    nothing: every row and event stays byte-identical, the file counts as
    skipped, and the warnings name it. The unscoped ``get_entity`` still
    answers B's row afterwards, which it could not had A registered a
    namesake (an ambiguous type_id resolves to None).

    Task 1C before its amendment registered A's namesake here. The base
    skipped the plain and archived rows silently, and registered a namesake
    beside the soft-deleted one, which ``get_entity`` hides.
    """
    c, db = checkouts, checkouts["db"]
    type_id = f"brainstorm:{_SHARED_STEM}"
    b_uuid = _brainstorm(db, c["B"], _SHARED_STEM, "active")
    if b_flag == "archived":
        db.set_archived(b_uuid)
    elif b_flag == "soft_deleted":
        db.set_deleted(type_id, workspace_uuid=c["B"])
    _track_prd(c["repo"], _SHARED_STEM)
    b_before = _row(c, b_uuid)
    before = _snapshot(c["db_path"])

    result = _session_start(c)

    assert _snapshot(c["db_path"]) == before
    assert _row(c, b_uuid) == b_before
    assert _brainstorm_rows(c, c["A"]) == []
    assert result["entity_sync"] == {
        "registered": 0, "skipped": 1,
        "warnings": [_held_elsewhere(_SHARED_STEM)],
    }
    assert db.get_entity(type_id, include_deleted=True)["uuid"] == b_uuid
    assert result["errors"] == []


def test_a_type_id_no_workspace_holds_is_registered_in_this_one(checkouts):
    """No workspace holds the type_id, and A's checkout tracks its file. A
    session start in A inserts A's row, as a new ``.prd.md`` is registered
    (kind brainstorm, status 'active', the artifact path under the
    artifacts root), with the insert path's creation events, and changes
    no existing row. B holds a brainstorm whose type_id extends this one's,
    which the other-workspace check's prefix search finds: only an exact
    type_id counts as held elsewhere.

    Keep-green: the base registers it too.
    """
    c, db = checkouts, checkouts["db"]
    stem = "20260905-000000-fresh-idea"
    b_uuid = _brainstorm(db, c["B"], f"{stem}-v2", "active")
    _track_prd(c["repo"], stem)
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
        "type_id": f"brainstorm:{stem}", "kind": "brainstorm",
        "name": stem, "status": "active",
        "artifact_path": f"docs/brainstorms/{stem}.prd.md",
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
    ] == [(f"brainstorm:{stem}", "entity_created",
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


@pytest.mark.parametrize("first_run", ["skipped-held-by-B", "registered-new"])
def test_a_second_session_start_after_the_first_changes_nothing(
    checkouts, first_run,
):
    """A session start right after the first one writes nothing:
    - **skipped-held-by-B:** the file B alone holds is skipped and named
      again, and A still holds no row;
    - **registered-new:** the file the first run registered is skipped, A
      holding exactly that one row.

    Task 1C before its amendment registered A's namesake of B's row in the
    first run. The base skipped the file B holds silently (red here through
    the warnings only); a file it registered it skipped next time too
    (keep-green).
    """
    c, db = checkouts, checkouts["db"]
    if first_run == "skipped-held-by-B":
        stem = _SHARED_STEM
        _brainstorm(db, c["B"], stem, "active")
        expected_rows_in_a, expected_warnings = 0, [_held_elsewhere(stem)]
    else:
        stem = "20260905-000000-fresh-idea"
        expected_rows_in_a, expected_warnings = 1, []
    _track_prd(c["repo"], stem)
    _session_start(c)
    after_first = _snapshot(c["db_path"])

    result = _session_start(c)

    assert _snapshot(c["db_path"]) == after_first
    assert len(_brainstorm_rows(c, c["A"])) == expected_rows_in_a
    assert result["entity_sync"] == {
        "registered": 0, "skipped": 1, "warnings": expected_warnings,
    }


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


@pytest.mark.parametrize("holders", ["A-and-B", "A-alone"])
@pytest.mark.parametrize("flag", ["none", "archived", "soft_deleted"])
@pytest.mark.parametrize("status", _ROW_STATUSES)
def test_no_row_this_workspace_holds_is_rewritten(
    checkouts, monkeypatch, status, flag, holders,
):
    """Whatever A's row holds (any status, archived or soft-deleted), with
    B holding the type_id too or A alone, and A's checkout tracking its
    file: the scoped existence check skips the file. No ``register_entity``
    call is made, every row stays byte-identical, no event is written, and
    the file counts as skipped with no warning, since A holds the type_id.

    These pin the scoped check itself. Without it, an A-alone file reaches
    ``register_entity`` (its ``EntityExistsError`` would hide that in the
    counts), and an A-and-B file is reported as held elsewhere.

    Before task 1C, each A-and-B case wrote: A's row re-statused to
    'active', or, already 'active', a no-op upsert reported as registered.
    The A-alone soft-deleted cases, which ``get_entity`` hides, did the
    same; the other A-alone cases are keep-green.
    """
    c, db = checkouts, checkouts["db"]
    a_uuid = _brainstorm(db, c["A"], _SHARED_STEM, status)
    if flag == "archived":
        db.set_archived(a_uuid)
    elif flag == "soft_deleted":
        db.set_deleted(f"brainstorm:{_SHARED_STEM}", workspace_uuid=c["A"])
    if holders == "A-and-B":
        _brainstorm(db, c["B"], _SHARED_STEM, "active")
    _write_prd(c["repo"], _SHARED_STEM)
    before = _snapshot(c["db_path"])
    registrations = _record_registrations(monkeypatch, db)

    result = _sync_as_orchestrator(c)

    assert _snapshot(c["db_path"]) == before
    assert result == {"registered": 0, "skipped": 1, "warnings": []}
    assert registrations == []


def test_a_row_registered_after_the_check_is_counted_skipped_and_left_alone(
    checkouts, monkeypatch,
):
    """1C contract 2's backstop: a row another writer inserts between the
    existence check and the insert (a concurrent session start) makes
    ``register_entity`` refuse with ``EntityExistsError``. The file counts
    as skipped, and the row stays byte-identical. The other-workspace check
    between the two sees that row as this workspace's own, so no warning
    names it.

    The race is simulated by an existence lookup that finds nothing. Before
    task 1C the upsert's conflict branch rewrote that row's status.
    """
    c, db = checkouts, checkouts["db"]
    _brainstorm(db, c["A"], _SHARED_STEM, "promoted")
    _write_prd(c["repo"], _SHARED_STEM)
    before = _snapshot(c["db_path"])

    def lookup_that_finds_nothing(identifier, *args, **kwargs):
        raise ValueError(f"Entity not found: {identifier!r}")

    monkeypatch.setattr(db, "_resolve_identifier", lookup_that_finds_nothing)
    result = _sync_as_orchestrator(c)

    assert _snapshot(c["db_path"]) == before
    assert result == {"registered": 0, "skipped": 1, "warnings": []}


# ---------------------------------------------------------------------------
# 1C contract 4: with no workspace resolved, nothing is registered anywhere
# ---------------------------------------------------------------------------


def _workspace_rows(db_path: str) -> list[dict]:
    """Every ``workspaces`` row."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM workspaces ORDER BY rowid"
        )]
    finally:
        conn.close()


def test_the_unknown_project_id_registers_nothing_in_the_unknown_workspace(
    checkouts,
):
    """``sync_entity_statuses`` called with its defaults, no workspace uuid
    and the ``"__unknown__"`` project id placeholder, resolves no
    workspace: it registers nothing, creates no unknown-workspace row, and
    returns ``register_entity``'s refusal as the warning.

    Before task 1C the placeholder resolved to the unknown workspace, which
    registration bootstrapped and registered the file into.
    """
    c = checkouts
    _write_prd(c["repo"], "20260904-000000-orphan")
    before = _snapshot(c["db_path"])
    workspaces_before = _workspace_rows(c["db_path"])

    result = sync_entity_statuses(c["db"], os.path.join(c["repo"], "docs"))

    assert _workspace_rows(c["db_path"]) == workspaces_before
    assert _snapshot(c["db_path"]) == before
    assert result == {
        "registered": 0, "skipped": 0,
        "warnings": ["brainstorms: register_entity() requires workspace_uuid"],
    }


def test_the_unknown_workspace_given_by_its_uuid_registers_nothing(checkouts):
    """A session workspace that is the unknown workspace itself (an
    ``ENTITY_WORKSPACE_UUID``, ``--workspace-uuid`` or ``workspace.json``
    naming its uuid) is refused like the ``"__unknown__"`` placeholder: it
    registers nothing, creates no unknown-workspace row, and returns the
    refusal as the warning.

    Before this fix, registration bootstrapped the unknown workspace and
    registered the file into it.
    """
    c = checkouts
    _write_prd(c["repo"], "20260904-000000-orphan")
    before = _snapshot(c["db_path"])
    workspaces_before = _workspace_rows(c["db_path"])

    result = sync_entity_statuses(
        c["db"], os.path.join(c["repo"], "docs"),
        project_id=_compute_legacy_project_id(c["repo"]),
        artifacts_root="docs", project_root=c["repo"],
        workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
    )

    assert _workspace_rows(c["db_path"]) == workspaces_before
    assert _snapshot(c["db_path"]) == before
    assert result == {
        "registered": 0, "skipped": 0,
        "warnings": [
            f"brainstorms: register_entity(): "
            f"workspace_uuid={_UNKNOWN_WORKSPACE_UUID!r} is the unknown "
            f"workspace; brainstorms are never registered there"
        ],
    }


@pytest.mark.parametrize("stems", [
    [_SHARED_STEM],
    [_SHARED_STEM, "20260903-000000-fresh"],
], ids=["held-by-B", "held-by-B-and-new"])
def test_a_checkout_whose_workspace_does_not_resolve_registers_nothing(
    checkouts, tmp_path, stems,
):
    """A directory where pd is not enabled (no ``.claude/``, no git) resolves
    no workspace, and its legacy project id, a hash of its path, names none.
    Its brainstorm files register nothing anywhere. The orchestrator records
    the workspace error and the Task 2 and 3 skips, as before task 1C, and
    Task 1's result keeps the base's counts:
    - **held-by-B:** the file B holds is skipped, as the base skipped it,
      and the warnings now name it (the task 1C amendment). No file needs
      registering, so the unresolved workspace goes unreported there, as
      the base left it.
    - **held-by-B-and-new:** the new file needs a registration workspace,
      so Task 1 fails with the resolution error as its one warning and both
      counts 0: the base's record, unchanged (keep-green).
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
    if len(stems) == 1:
        expected_entity_sync = {
            "registered": 0, "skipped": 1,
            "warnings": [_held_elsewhere(_SHARED_STEM)],
        }
    else:
        expected_entity_sync = {
            "registered": 0, "skipped": 0,
            "warnings": [
                f"brainstorms: register_entity(): project_id={legacy_id!r} "
                f"has no matching workspaces.project_id_legacy row. Either "
                f"pass workspace_uuid directly or pre-register the workspace."
            ],
        }
    assert result["entity_sync"] == expected_entity_sync
    assert result["errors"][0].startswith("workspace_uuid: ")
    assert result["errors"][1:] == _NO_WORKSPACE_ERRORS_AFTER_THE_FIRST


def test_a_checkout_resolved_by_its_legacy_id_looks_up_that_workspace_only(
    checkouts, tmp_path,
):
    """A second clone of A's repository, without ``.claude/``, resolves no
    workspace of its own (the orchestrator records why, and skips Tasks 2
    and 3), so Task 1 takes the workspace its legacy project id names: A's,
    since a clone shares the root commit (C5b; design W4.1 resolves a
    writer's workspace the same way). Existence is checked in A first, and A
    holds the type_id: A's 'promoted' row and B's namesake stay
    byte-identical, and the file counts as skipped, with no warning.

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
