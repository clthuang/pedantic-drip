"""C15 + C16: ``init_project_state`` owns project registration, and registers
before it creates the project directory.

- **C15** — one code path attempts project registration: ``init_project_state``.
  Counted as registration ATTEMPTS and ``entity_created`` events, never as
  resulting rows: a duplicate registration followed by conflict handling also
  leaves exactly one row.
- **C16** — registration precedes directory creation, so a registration
  failure leaves no directory. The failures injected here fire INSIDE
  ``register_entity``; a failure caused by a bad path never reaches
  registration and would prove nothing.
- **Conflicts** — a registration conflict resumes only the row this same
  call wrote (live, same directory, same parent); a deleted project or a
  row with another directory or parent is refused before the directory.
- **Path validation** — the directory no longer exists when the path is
  validated, so validation checks where the path RESOLVES: NUL bytes,
  realpath containment directly under ``{artifacts_root}/projects``, and no
  existing non-directory. Writes go to the resolved path.

Real ``EntityDatabase`` (in memory) throughout: the facts asserted are rows,
events and directories, which a mock cannot hold.
"""
from __future__ import annotations

import os
import sqlite3

import pytest

from entity_registry.database import EntityDatabase
from entity_registry.test_helpers import bootstrap_test_workspace
from workflow_engine import feature_lifecycle
from workflow_engine.feature_lifecycle import init_project_state

PROJECT_TYPE_ID = "project:001-alpha"
MISSING_PARENT_UUID = "01900000-0000-7000-8000-000000000000"


@pytest.fixture()
def db():
    database = EntityDatabase(":memory:")
    yield database
    database.close()


@pytest.fixture()
def artifacts_root(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    return str(root)


def _project_dir(artifacts_root: str, name: str = "001-alpha") -> str:
    return os.path.join(artifacts_root, "projects", name)


def _init(db, artifacts_root, project_dir, **overrides):
    kwargs = dict(
        db=db,
        artifacts_root=artifacts_root,
        project_dir=project_dir,
        project_id="001",
        slug="alpha",
        branch="",
        features="[]",
        milestones="[]",
    )
    kwargs.update(overrides)
    return init_project_state(**kwargs)


class RegistrationAttempts:
    """Every ``register_entity`` call on ``db``, as ``(kind, directory_existed)``.

    ``directory_existed`` is whether the watched project directory was on
    disk at the moment registration was attempted.
    """

    def __init__(self, db, monkeypatch, watched_dir: str):
        self.calls: list[tuple[str, bool]] = []
        real_register = db.register_entity

        def spy(*args, **kwargs):
            kind = kwargs.get("entity_type", args[0] if args else None)
            self.calls.append((kind, os.path.exists(watched_dir)))
            return real_register(*args, **kwargs)

        monkeypatch.setattr(db, "register_entity", spy)

    def of_kind(self, kind: str) -> list[tuple[str, bool]]:
        return [call for call in self.calls if call[0] == kind]


def _creation_events(db, type_id: str = PROJECT_TYPE_ID) -> list[dict]:
    return db.query_phase_events(type_id=type_id, event_type="entity_created")


def _register_brainstorm(db, stem: str) -> str:
    return db.register_entity(
        "brainstorm", name=f"{stem} brainstorm", display_id=stem,
        project_id="__unknown__",
    )


def _register_then_fail_the_directory(db, artifacts_root, project_dir, monkeypatch, **overrides) -> str:
    """Run the call with directory creation failing, so it stops after
    registering: the state a retry resumes. Returns the registered uuid."""
    real_makedirs = os.makedirs

    def makedirs_failing_for_the_project(path, *args, **kwargs):
        if os.path.realpath(path) == os.path.realpath(project_dir):
            raise PermissionError("injected mkdir failure")
        return real_makedirs(path, *args, **kwargs)

    with monkeypatch.context() as patched:
        patched.setattr(feature_lifecycle.os, "makedirs", makedirs_failing_for_the_project)
        with pytest.raises(PermissionError, match="injected mkdir failure"):
            _init(db, artifacts_root, project_dir, **overrides)
    assert not os.path.exists(project_dir)
    return db.get_entity(PROJECT_TYPE_ID)["uuid"]


# ---------------------------------------------------------------------------
# C16 — registration precedes directory creation
# ---------------------------------------------------------------------------


def test_a_failure_inside_register_entity_leaves_no_directory(db, artifacts_root, monkeypatch):
    """The injected failure is the display-row write, which runs inside
    register_entity's transaction after the entity INSERT. It must be
    reached (so the path was accepted and registration really began) and
    must leave neither a row nor a directory behind."""
    project_dir = _project_dir(artifacts_root)
    reached_registration = []

    def failing_display_row(entity_uuid, seq, slug):
        reached_registration.append((seq, slug))
        raise RuntimeError("injected registration failure")

    monkeypatch.setattr(db, "_insert_display_row", failing_display_row)

    with pytest.raises(RuntimeError, match="injected registration failure"):
        _init(db, artifacts_root, project_dir)

    assert reached_registration == [(1, "alpha")]
    assert db.get_entity(PROJECT_TYPE_ID) is None
    assert _creation_events(db) == []
    assert not os.path.exists(project_dir)


def test_a_parent_that_does_not_exist_fails_registration_and_leaves_no_directory(db, artifacts_root):
    """A real registration failure, no monkeypatching: parent_uuid is a
    foreign key, so an unknown parent fails the INSERT itself."""
    project_dir = _project_dir(artifacts_root)

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        _init(db, artifacts_root, project_dir, parent_uuid=MISSING_PARENT_UUID)

    assert db.get_entity(PROJECT_TYPE_ID) is None
    assert not os.path.exists(project_dir)


def test_the_directory_is_created_only_after_registration_succeeds(db, artifacts_root, monkeypatch):
    project_dir = _project_dir(artifacts_root)
    attempts = RegistrationAttempts(db, monkeypatch, project_dir)

    result = _init(db, artifacts_root, project_dir)

    assert attempts.calls == [("project", False)]
    assert os.path.isdir(project_dir)
    assert os.path.isfile(os.path.join(project_dir, ".meta.json"))
    assert result["project_uuid"] == db.get_entity(PROJECT_TYPE_ID)["uuid"]
    assert result["resumed"] is False


def test_the_project_registers_under_the_parent_it_is_given(db, artifacts_root):
    """The removed command-side registration carried the brainstorm as
    parent; the owner has to carry it now."""
    brainstorm_uuid = db.register_entity(
        "brainstorm", name="alpha brainstorm", display_id="20260924-alpha",
        project_id="__unknown__",
    )

    _init(db, artifacts_root, _project_dir(artifacts_root), parent_uuid=brainstorm_uuid)

    assert db.get_entity(PROJECT_TYPE_ID)["parent_uuid"] == brainstorm_uuid


def test_a_retry_after_a_failed_mkdir_finishes_without_a_second_creation(db, artifacts_root, monkeypatch):
    """A directory failure after registration leaves the row; running the
    same call again must finish the directory without registering twice.
    The second attempt conflicts; the workspace-scoped conflict finds the
    row, and its directory and parent match this call's, so it resumes."""
    project_dir = _project_dir(artifacts_root)
    first_uuid = _register_then_fail_the_directory(db, artifacts_root, project_dir, monkeypatch)

    result = _init(db, artifacts_root, project_dir)

    assert result["project_uuid"] == first_uuid
    assert result["resumed"] is True
    assert len(_creation_events(db)) == 1
    assert os.path.isfile(os.path.join(project_dir, ".meta.json"))


def test_a_same_id_project_in_another_workspace_does_not_stand_in_for_this_one(db, artifacts_root, monkeypatch):
    """Workspaces allocate independently, so two can hold project:001-alpha.
    An unscoped existence check found the other workspace's row, skipped
    registration, and still wrote the directory: a directory with no
    registration behind it. The directory here predates the call (an earlier
    run of the old command made it); that is allowed, and it keeps this
    test about the workspace, not the ordering."""
    workspace_a = bootstrap_test_workspace(db, "workspace-a")
    workspace_b = bootstrap_test_workspace(db, "workspace-b")
    other_uuid = db.register_entity(
        "project", name="Alpha", seq=1, slug="alpha", workspace_uuid=workspace_a,
    )
    project_dir = _project_dir(artifacts_root)
    os.makedirs(project_dir)

    result = _init(db, artifacts_root, project_dir, workspace_uuid=workspace_b)

    own_rows = db.list_entities(entity_type="project", workspace_uuid=workspace_b)
    assert [row["type_id"] for row in own_rows] == [PROJECT_TYPE_ID]
    assert result["project_uuid"] == own_rows[0]["uuid"] != other_uuid


# ---------------------------------------------------------------------------
# A registration conflict resumes only this call's own earlier attempt
# ---------------------------------------------------------------------------


def test_a_retry_under_the_same_parent_resumes(db, artifacts_root, monkeypatch):
    project_dir = _project_dir(artifacts_root)
    brainstorm_uuid = _register_brainstorm(db, "20260924-alpha")
    first_uuid = _register_then_fail_the_directory(
        db, artifacts_root, project_dir, monkeypatch, parent_uuid=brainstorm_uuid,
    )

    result = _init(db, artifacts_root, project_dir, parent_uuid=brainstorm_uuid)

    assert (result["project_uuid"], result["resumed"]) == (first_uuid, True)
    assert os.path.isfile(os.path.join(project_dir, ".meta.json"))


def test_a_deleted_project_holding_the_id_is_refused_before_the_directory(db, artifacts_root, monkeypatch):
    """Sequence drift can re-issue a deleted project's id once its directory
    is gone. Deletion is soft, so the row still holds the id and
    registration conflicts; resuming it would hand the new project a
    deleted row. The row is this very call's earlier attempt, so its
    deletion is the only thing that differs."""
    project_dir = _project_dir(artifacts_root)
    _register_then_fail_the_directory(db, artifacts_root, project_dir, monkeypatch)
    db.delete_entity(PROJECT_TYPE_ID)

    with pytest.raises(RuntimeError, match="registration conflict for project:001-alpha: .* is deleted"):
        _init(db, artifacts_root, project_dir)

    assert db.get_entity(PROJECT_TYPE_ID, include_deleted=True)["is_deleted"] == 1
    assert len(_creation_events(db)) == 1
    assert not os.path.exists(project_dir)


@pytest.mark.parametrize("recorded_dir", [None, "001-alpha-earlier"], ids=["no directory", "another directory"])
def test_a_row_registered_for_another_directory_is_refused_before_the_directory(recorded_dir, db, artifacts_root):
    """A row this call did not write is not resumed. The MCP
    ``register_entity`` tool, the duplicate registrar C15 removed, records
    no directory unless given one; a row recording another directory
    belongs to another project. Resuming either would hide the duplicate."""
    project_dir = _project_dir(artifacts_root)
    db.register_entity(
        "project", name="Alpha", seq=1, slug="alpha", project_id="__unknown__",
        artifact_path=None if recorded_dir is None else _project_dir(artifacts_root, recorded_dir),
    )

    with pytest.raises(RuntimeError, match="registration conflict for project:001-alpha: .* directory is"):
        _init(db, artifacts_root, project_dir)

    assert len(_creation_events(db)) == 1
    assert not os.path.exists(project_dir)


def test_a_row_registered_under_another_parent_is_refused_before_the_directory(db, artifacts_root, monkeypatch):
    """Same directory, another brainstorm: an earlier project that stopped
    after registering, whose id drift has re-issued, is not this call's."""
    project_dir = _project_dir(artifacts_root)
    earlier_brainstorm = _register_brainstorm(db, "20260901-alpha")
    this_brainstorm = _register_brainstorm(db, "20260924-alpha")
    _register_then_fail_the_directory(
        db, artifacts_root, project_dir, monkeypatch, parent_uuid=earlier_brainstorm,
    )

    with pytest.raises(RuntimeError, match="registration conflict for project:001-alpha: .* parent is"):
        _init(db, artifacts_root, project_dir, parent_uuid=this_brainstorm)

    assert db.get_entity(PROJECT_TYPE_ID)["parent_uuid"] == earlier_brainstorm
    assert len(_creation_events(db)) == 1
    assert not os.path.exists(project_dir)


# ---------------------------------------------------------------------------
# The parent must be live and in the project's workspace — the parent rules
# reparent_entity enforces (C22a) — checked before registration
# ---------------------------------------------------------------------------


def test_a_soft_deleted_parent_is_refused_before_registration(db, artifacts_root, monkeypatch):
    """Deleted rows stay childless: registering under one would give a row
    that reads no longer show a child."""
    project_dir = _project_dir(artifacts_root)
    deleted_brainstorm = _register_brainstorm(db, "20260901-gone")
    db.delete_entity(deleted_brainstorm)
    attempts = RegistrationAttempts(db, monkeypatch, project_dir)

    with pytest.raises(ValueError, match="parent .* is soft-deleted"):
        _init(db, artifacts_root, project_dir, parent_uuid=deleted_brainstorm)

    assert attempts.calls == []
    assert db.get_entity(PROJECT_TYPE_ID, include_deleted=True) is None
    assert _creation_events(db) == []
    assert not os.path.exists(project_dir)


@pytest.mark.parametrize(
    "project_workspace_name", [None, "home"],
    ids=["project in the default workspace", "project in a named workspace"],
)
def test_a_parent_in_another_workspace_is_refused_before_registration(
    project_workspace_name, db, artifacts_root, monkeypatch,
):
    """No new path may add a cross-workspace parent link. Without a
    workspace_uuid the project registers in the default ``__unknown__``
    workspace, so a parent in a named workspace is in another one too."""
    project_dir = _project_dir(artifacts_root)
    project_workspace = (
        None if project_workspace_name is None
        else bootstrap_test_workspace(db, project_workspace_name)
    )
    elsewhere = bootstrap_test_workspace(db, "elsewhere")
    foreign_brainstorm = db.register_entity(
        "brainstorm", name="alpha brainstorm", display_id="20260924-alpha",
        workspace_uuid=elsewhere,
    )
    attempts = RegistrationAttempts(db, monkeypatch, project_dir)

    with pytest.raises(ValueError, match="cross-workspace parent"):
        _init(
            db, artifacts_root, project_dir,
            workspace_uuid=project_workspace, parent_uuid=foreign_brainstorm,
        )

    assert attempts.calls == []
    assert db.list_entities(entity_type="project", include_deleted=True) == []
    assert not os.path.exists(project_dir)


def test_a_live_parent_in_the_projects_named_workspace_is_accepted(db, artifacts_root):
    """The positive side of the workspace rule, outside the default
    workspace: the check compares against the workspace the project
    registers in, not a fixed one."""
    home = bootstrap_test_workspace(db, "home")
    brainstorm_uuid = db.register_entity(
        "brainstorm", name="alpha brainstorm", display_id="20260924-alpha",
        workspace_uuid=home,
    )

    result = _init(
        db, artifacts_root, _project_dir(artifacts_root),
        workspace_uuid=home, parent_uuid=brainstorm_uuid,
    )

    project = db.get_entity_by_uuid(result["project_uuid"])
    assert (project["workspace_uuid"], project["parent_uuid"]) == (home, brainstorm_uuid)


# ---------------------------------------------------------------------------
# C15 — one attempt, one creation event
# ---------------------------------------------------------------------------


def test_one_call_makes_one_registration_attempt_and_one_creation_event(db, artifacts_root, monkeypatch):
    project_dir = _project_dir(artifacts_root)
    attempts = RegistrationAttempts(db, monkeypatch, project_dir)

    _init(db, artifacts_root, project_dir)

    assert attempts.of_kind("project") == [("project", False)]
    assert len(_creation_events(db)) == 1


# ---------------------------------------------------------------------------
# Path validation — before any registry write, without requiring existence
# ---------------------------------------------------------------------------


def _outside_existing(tmp_path, artifacts_root):
    outside = tmp_path / "elsewhere" / "001-alpha"
    outside.mkdir(parents=True)
    return str(outside), str(outside / ".meta.json")


def _outside_missing(tmp_path, artifacts_root):
    outside = str(tmp_path / "elsewhere" / "001-alpha")
    return outside, outside


def _dot_dot_escape(tmp_path, artifacts_root):
    escaped = os.path.join(artifacts_root, "projects", "..", "..", "001-alpha")
    return escaped, str(tmp_path / "001-alpha")


def _nested(tmp_path, artifacts_root):
    nested = os.path.join(artifacts_root, "projects", "group", "001-alpha")
    return nested, nested


def _projects_root_itself(tmp_path, artifacts_root):
    root = os.path.join(artifacts_root, "projects")
    return root, os.path.join(root, ".meta.json")


def _symlink_out_of_root(tmp_path, artifacts_root):
    target = tmp_path / "symlink-target"
    target.mkdir()
    projects = os.path.join(artifacts_root, "projects")
    os.makedirs(projects)
    link = os.path.join(projects, "001-alpha")
    os.symlink(str(target), link)
    return link, str(target / ".meta.json")


def _empty(tmp_path, artifacts_root):
    return "", str(tmp_path / ".meta.json")


_ESCAPES = {
    "outside the root, existing": _outside_existing,
    "outside the root, missing": _outside_missing,
    "dot-dot escape": _dot_dot_escape,
    "nested below projects": _nested,
    "the projects root itself": _projects_root_itself,
    "symlink out of the root": _symlink_out_of_root,
    "empty string": _empty,
}


@pytest.mark.parametrize("case", list(_ESCAPES))
def test_a_path_outside_the_projects_root_is_refused_before_any_registry_write(
    case, db, artifacts_root, tmp_path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)  # "" resolves to the working directory
    project_dir, must_not_exist = _ESCAPES[case](tmp_path, artifacts_root)
    attempts = RegistrationAttempts(db, monkeypatch, project_dir)

    with pytest.raises(ValueError, match="path traversal blocked"):
        _init(db, artifacts_root, project_dir)

    assert attempts.calls == []
    assert db.list_entities(entity_type="project") == []
    assert not os.path.exists(must_not_exist)


def test_a_nul_byte_is_refused_before_any_registry_write(db, artifacts_root, monkeypatch):
    project_dir = _project_dir(artifacts_root) + "\0evil"
    attempts = RegistrationAttempts(db, monkeypatch, _project_dir(artifacts_root))

    with pytest.raises(ValueError, match="path traversal blocked"):
        _init(db, artifacts_root, project_dir)

    assert attempts.calls == []
    assert not os.path.exists(_project_dir(artifacts_root))


def test_an_existing_file_at_the_path_is_refused_before_any_registry_write(db, artifacts_root, monkeypatch):
    project_dir = _project_dir(artifacts_root)
    os.makedirs(os.path.dirname(project_dir))
    with open(project_dir, "w") as f:
        f.write("not a directory")
    attempts = RegistrationAttempts(db, monkeypatch, project_dir)

    with pytest.raises(ValueError, match="is not a directory"):
        _init(db, artifacts_root, project_dir)

    assert attempts.calls == []
    assert db.list_entities(entity_type="project") == []


def test_a_path_through_a_missing_directory_is_written_where_it_resolves(db, artifacts_root):
    """``projects/missing/../001-alpha`` resolves directly under the root, so
    it is accepted. The kernel cannot walk through the missing component,
    so a write through the path as given fails after registering, on every
    retry; the checked, resolved path is the one to write."""
    project_dir = os.path.join(artifacts_root, "projects", "missing", "..", "001-alpha")
    resolved_meta = os.path.join(os.path.realpath(artifacts_root), "projects", "001-alpha", ".meta.json")

    result = _init(db, artifacts_root, project_dir)

    assert result["meta_json_path"] == resolved_meta
    assert os.path.isfile(resolved_meta)


@pytest.mark.parametrize("overrides, refusal", [
    ({"project_id": "P001"}, "not an allocated id"),
    ({"features": "not-json"}, "Expecting value"),
    ({"milestones": "{broken"}, "Expecting property name"),
], ids=["unallocated id", "malformed features", "malformed milestones"])
def test_invalid_input_is_refused_before_registration_and_before_the_directory(
    overrides, refusal, db, artifacts_root, monkeypatch,
):
    project_dir = _project_dir(artifacts_root)
    attempts = RegistrationAttempts(db, monkeypatch, project_dir)

    with pytest.raises(ValueError, match=refusal):
        _init(db, artifacts_root, project_dir, **overrides)

    assert attempts.calls == []
    assert not os.path.exists(project_dir)
