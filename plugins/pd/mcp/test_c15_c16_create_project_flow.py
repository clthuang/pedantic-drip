"""C15 + C16 across the ``/pd:create-project`` flow.

- **The command's instructions** (``commands/create-project.md``) — exactly
  one project-registration attempt, ``init_project_state``; no command,
  skill, agent or reference registers a project through
  ``register_entity``; and no step creates the project directory before
  ``init_project_state``.
- **The MCP entry point the command calls** (``init_project_state`` in
  ``workflow_state_server``) — the flow's calls replayed against a real
  in-memory registry count registration ATTEMPTS and ``entity_created``
  events (a duplicate registration followed by conflict handling also
  leaves one row, so rows prove nothing); a failure that reaches
  registration leaves no directory; an out-of-root path is refused before
  any registry write.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import pytest

# Ensure hooks/lib is on path for imports (mirrors test_workflow_state_server.py).
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in sys.path:
    sys.path.insert(0, _hooks_lib)

from entity_registry.database import EntityDatabase
from entity_registry.id_generator import generate_entity_id, render_display_id
from entity_registry.server_helpers import _process_register_entity

import workflow_state_server as wss

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent          # plugins/pd
_CREATE_PROJECT = _PLUGIN_ROOT / "commands" / "create-project.md"

_REGISTER_A_PROJECT = re.compile(r"register_entity\(\s*entity_type\s*=\s*[\"']project[\"']")
_INIT_PROJECT_STATE_CALL = re.compile(r"\binit_project_state\(")
_CREATE_THE_PROJECT_DIRECTORY = re.compile(
    r"(?i)\b(?:create|mkdir)\b[^\n]*?\{pd_artifacts_root\}/projects/"
)

PROJECT_TYPE_ID = "project:001-alpha"
BRAINSTORM_STEM = "20260924-alpha"
MISSING_PARENT_UUID = "01900000-0000-7000-8000-000000000000"


def _create_project_steps() -> str:
    text = _CREATE_PROJECT.read_text(encoding="utf-8")
    return text.split("**Steps:**", 1)[1].split("**Constraints:**", 1)[0]


def _instruction_files() -> list[Path]:
    files: list[Path] = []
    for pattern in ("commands/*.md", "skills/**/*.md", "agents/*.md", "references/*.md"):
        files.extend(sorted(_PLUGIN_ROOT.glob(pattern)))
    return files


# ---------------------------------------------------------------------------
# The command's instructions
# ---------------------------------------------------------------------------


def test_no_instruction_file_registers_a_project_through_register_entity():
    offenders = [
        f"{path.relative_to(_PLUGIN_ROOT)}:{number}"
        for path in _instruction_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _REGISTER_A_PROJECT.search(line)
    ]
    assert offenders == []


def test_create_project_attempts_project_registration_exactly_once():
    steps = _create_project_steps()
    init_calls = _INIT_PROJECT_STATE_CALL.findall(steps)
    register_calls = _REGISTER_A_PROJECT.findall(steps)

    assert (len(init_calls), len(register_calls)) == (1, 0)


def test_create_project_creates_no_directory_before_init_project_state():
    steps = _create_project_steps()
    before_registration = steps[: _INIT_PROJECT_STATE_CALL.search(steps).start()]

    assert _CREATE_THE_PROJECT_DIRECTORY.findall(before_registration) == []


# ---------------------------------------------------------------------------
# The MCP entry point
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_module_globals():
    saved = (wss._db, wss._db_unavailable, wss._workspace_uuid, wss._artifacts_root)
    try:
        yield
    finally:
        wss._db, wss._db_unavailable, wss._workspace_uuid, wss._artifacts_root = saved


@pytest.fixture()
def db():
    database = EntityDatabase(":memory:")
    yield database
    database.close()


@pytest.fixture()
def artifacts_root(tmp_path, db):
    """The server as a real session leaves it: a registry, no resolved
    workspace (so registration lands in ``__unknown__``), and an artifacts
    root."""
    root = tmp_path / "docs"
    root.mkdir()
    wss._db = db
    wss._db_unavailable = False
    wss._workspace_uuid = ""
    wss._artifacts_root = str(root)
    return str(root)


def _init_project_state_tool(**arguments) -> dict:
    defaults = dict(project_id="001", slug="alpha", features="[]", milestones="[]")
    defaults.update(arguments)
    return json.loads(asyncio.run(wss.init_project_state(**defaults)))


def _record_registration_attempts(db, monkeypatch, watched_dir: str) -> list[tuple[str, bool]]:
    """Every ``register_entity`` call as ``(kind, watched_dir existed)``."""
    attempts: list[tuple[str, bool]] = []
    real_register = db.register_entity

    def spy(*args, **kwargs):
        kind = kwargs.get("entity_type", args[0] if args else None)
        attempts.append((kind, os.path.exists(watched_dir)))
        return real_register(*args, **kwargs)

    monkeypatch.setattr(db, "register_entity", spy)
    return attempts


def test_the_create_project_flow_registers_the_project_exactly_once(db, artifacts_root, monkeypatch):
    """Steps 3, 5 and 6 of create-project.md, through the code they call."""
    project_dir = os.path.join(artifacts_root, "projects", "001-alpha")
    attempts = _record_registration_attempts(db, monkeypatch, project_dir)

    seq, slug = generate_entity_id(db, "project", "alpha", "__unknown__")
    assert render_display_id("project", seq, slug) == "001-alpha"
    registered = _process_register_entity(
        db, "brainstorm", {"display_id": BRAINSTORM_STEM}, BRAINSTORM_STEM,
        None, "active", None, None,
    )
    assert registered == f"Registered: brainstorm:{BRAINSTORM_STEM}"
    brainstorm_uuid = db.get_entity(f"brainstorm:{BRAINSTORM_STEM}")["uuid"]

    result = _init_project_state_tool(
        project_dir=project_dir,
        brainstorm_source=f"docs/brainstorms/{BRAINSTORM_STEM}.prd.md",
        parent_uuid=brainstorm_uuid,
    )

    assert attempts == [("brainstorm", False), ("project", False)]
    assert len(db.query_phase_events(type_id=PROJECT_TYPE_ID, event_type="entity_created")) == 1
    project = db.get_entity(PROJECT_TYPE_ID)
    assert project["parent_uuid"] == brainstorm_uuid
    assert result["project_uuid"] == project["uuid"]
    assert os.path.isfile(os.path.join(project_dir, ".meta.json"))


def test_a_failure_inside_registration_through_the_tool_leaves_no_directory(db, artifacts_root, monkeypatch):
    project_dir = os.path.join(artifacts_root, "projects", "001-alpha")
    reached_registration = []

    def failing_display_row(entity_uuid, seq, slug):
        reached_registration.append((seq, slug))
        raise RuntimeError("injected registration failure")

    monkeypatch.setattr(db, "_insert_display_row", failing_display_row)

    result = _init_project_state_tool(project_dir=project_dir)

    assert result["error"] is True
    assert "injected registration failure" in result["message"]
    assert reached_registration == [(1, "alpha")]
    assert db.get_entity(PROJECT_TYPE_ID) is None
    assert not os.path.exists(project_dir)


def test_a_missing_parent_fails_registration_through_the_tool_and_leaves_no_directory(db, artifacts_root):
    project_dir = os.path.join(artifacts_root, "projects", "001-alpha")

    result = _init_project_state_tool(project_dir=project_dir, parent_uuid=MISSING_PARENT_UUID)

    assert result["error_type"] == "db_unavailable"
    assert "FOREIGN KEY" in result["message"]
    assert db.get_entity(PROJECT_TYPE_ID) is None
    assert not os.path.exists(project_dir)


def test_an_out_of_root_directory_is_refused_by_the_tool_before_any_registry_write(
    db, artifacts_root, tmp_path, monkeypatch,
):
    outside = tmp_path / "elsewhere" / "001-alpha"
    outside.mkdir(parents=True)
    attempts = _record_registration_attempts(db, monkeypatch, str(outside))

    result = _init_project_state_tool(project_dir=str(outside))

    assert result["error"] is True
    assert "path traversal blocked" in result["message"]
    assert attempts == []
    assert db.list_entities(entity_type="project") == []
    assert not (outside / ".meta.json").exists()
