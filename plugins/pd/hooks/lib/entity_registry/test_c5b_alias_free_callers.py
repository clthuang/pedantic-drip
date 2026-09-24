"""C5b step 1: production callers stop passing the deprecated registration aliases.

``project_id`` (alias for ``workspace_uuid``) and ``parent_type_id`` (alias
for ``parent_uuid``) stay accepted by ``register_entity``, ``upsert_entity``
and ``register_entities_batch`` until a later step deletes them. Here every
production caller resolves ONE workspace at its boundary and passes
``workspace_uuid`` instead, and the allocator ``generate_entity_id`` takes
``workspace_uuid`` too.

Two facts are pinned per converted site:

* **The alias no longer reaches registration** — a spy on the registration
  call sees ``workspace_uuid`` and no alias keyword. True only on the
  converted path.
* **The ``entity_created`` label is byte-identical to the base.** With an
  explicit ``project_id`` the label WAS that string; without it, the label is
  the resolved workspace's ``project_id_legacy``. A workspace found through
  ``project_id_legacy`` carries the same string, so every expected label
  below is what the pre-C5b build wrote for the same input.
"""
from __future__ import annotations

import ast
import inspect
import json
import os
import warnings
from pathlib import Path

import pytest

from entity_registry.backfill import run_backfill
from entity_registry.database import _UNKNOWN_WORKSPACE_UUID, EntityDatabase
from entity_registry.id_generator import generate_entity_id
from entity_registry.server_helpers import _process_register_entity
from entity_registry.test_helpers import bootstrap_test_workspace

LEGACY_A = "c5b-ws-a"
LEGACY_B = "c5b-ws-b"
UNKNOWN_LABEL = "__unknown__"
_PLUGIN_ROOT = Path(__file__).resolve().parents[3]
_REGISTRATION_CALLS = frozenset({"register_entity", "upsert_entity", "register_entities_batch"})
_REGISTRATION_ALIASES = frozenset({"project_id", "parent_type_id"})
_SKIPPED_DIRECTORIES = frozenset({".venv", "tests", "__pycache__", "node_modules"})


@pytest.fixture
def two_workspaces():
    """A registry with workspaces A and B, each found by its legacy id."""
    db = EntityDatabase(":memory:")
    ws_a = bootstrap_test_workspace(db, LEGACY_A)
    ws_b = bootstrap_test_workspace(db, LEGACY_B)
    yield db, ws_a, ws_b
    db.close()


def _record_calls(monkeypatch, target, method_name: str) -> list[dict]:
    """Wrap ``target.method_name``; return every call's arguments by parameter
    name, positional ones included (``next_sequence_value`` takes its
    ``project_id`` alias first)."""
    calls: list[dict] = []
    original = getattr(target, method_name)
    signature = inspect.signature(original)

    def recording(*args, **kwargs):
        calls.append(dict(signature.bind(*args, **kwargs).arguments))
        return original(*args, **kwargs)

    monkeypatch.setattr(target, method_name, recording)
    return calls


def _created_label(db: EntityDatabase, type_id: str) -> str:
    """The project_id label of the one entity_created event for *type_id*."""
    rows = db._conn.execute(
        "SELECT project_id FROM phase_events "
        "WHERE type_id = ? AND event_type = 'entity_created'",
        (type_id,),
    ).fetchall()
    assert len(rows) == 1, f"{type_id}: expected one entity_created event, got {len(rows)}"
    return rows[0][0]


def _row_workspace(db: EntityDatabase, type_id: str) -> str:
    return db._conn.execute(
        "SELECT workspace_uuid FROM entities WHERE type_id = ?", (type_id,)
    ).fetchone()[0]


def _counter(db: EntityDatabase, workspace_uuid: str, kind: str) -> int | None:
    row = db._conn.execute(
        "SELECT next_val FROM sequences WHERE workspace_uuid = ? AND entity_type = ?",
        (workspace_uuid, kind),
    ).fetchone()
    return None if row is None else row[0]


def _assert_no_alias(calls: list[dict], expected_workspace_uuid: str) -> None:
    """Every recorded call carried *expected_workspace_uuid* and no alias value."""
    assert calls, "the registration call was never made"
    for arguments in calls:
        leaked = sorted(name for name in _REGISTRATION_ALIASES
                        if arguments.get(name) is not None)
        assert not leaked, f"still passed {leaked}: {arguments}"
        assert arguments.get("workspace_uuid") == expected_workspace_uuid, arguments


# ---------------------------------------------------------------------------
# Exit check: no production call passes an alias
# ---------------------------------------------------------------------------


def _production_sources():
    for directory, subdirectories, files in os.walk(_PLUGIN_ROOT):
        subdirectories[:] = [d for d in subdirectories if d not in _SKIPPED_DIRECTORIES]
        for file_name in files:
            if not file_name.endswith(".py"):
                continue
            if file_name.startswith("test_") or file_name == "conftest.py":
                continue
            yield Path(directory, file_name)


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _alias_passing_calls(path: Path) -> list[str]:
    with warnings.catch_warnings():
        # Parsing is all this needs; a module's own invalid-escape
        # SyntaxWarning is not this test's finding.
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    where = path.relative_to(_PLUGIN_ROOT)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = _called_name(node)
        if called in _REGISTRATION_CALLS:
            found += [f"{where}:{node.lineno} {called}({keyword.arg}=...)"
                      for keyword in node.keywords if keyword.arg in _REGISTRATION_ALIASES]
        elif called == "generate_entity_id":
            if len(node.args) >= 4:
                found.append(f"{where}:{node.lineno} generate_entity_id(<4th positional project_id>)")
            found += [f"{where}:{node.lineno} generate_entity_id(project_id=...)"
                      for keyword in node.keywords if keyword.arg == "project_id"]
    return found


def test_no_production_call_passes_a_registration_alias():
    """C5b step 1's exit check: no production call hands registration the
    ``project_id`` or ``parent_type_id`` alias, or the allocator ``project_id``
    (keyword or 4th positional). (A ``**splat`` argument is not inspected;
    production splats carry identity keywords only.)"""
    offending = [site for path in _production_sources() for site in _alias_passing_calls(path)]
    assert offending == []


# ---------------------------------------------------------------------------
# The allocator takes workspace_uuid
# ---------------------------------------------------------------------------


def test_generate_entity_id_allocates_from_the_workspace_uuid_it_is_given(two_workspaces):
    db, ws_a, ws_b = two_workspaces

    seq, slug = generate_entity_id(db, "feature", "Some Feature", workspace_uuid=ws_b)

    assert (seq, slug) == (1, "some-feature")
    assert _counter(db, ws_b, "feature") is not None
    assert _counter(db, ws_a, "feature") is None


# ---------------------------------------------------------------------------
# database.py: upsert_entity resolves its own aliases before delegating
# ---------------------------------------------------------------------------


def test_upsert_resolves_its_aliases_before_delegating_to_register(two_workspaces, monkeypatch):
    db, ws_a, _ws_b = two_workspaces
    parent_uuid = db.register_entity("project", name="Parent", seq=1, slug="parent",
                                     workspace_uuid=ws_a)
    delegated = _record_calls(monkeypatch, db, "register_entity")

    db.upsert_entity("feature", name="Child", seq=7, slug="child",
                     project_id=LEGACY_A, parent_type_id="project:001-parent")

    _assert_no_alias(delegated, ws_a)
    assert delegated[0]["parent_uuid"] == parent_uuid
    child = db.get_entity("feature:007-child")
    assert child["workspace_uuid"] == ws_a
    assert child["parent_uuid"] == parent_uuid
    assert _created_label(db, "feature:007-child") == LEGACY_A


def test_upsert_with_the_unknown_alias_registers_in_the_unknown_workspace(monkeypatch):
    db = EntityDatabase(":memory:")
    delegated = _record_calls(monkeypatch, db, "register_entity")

    db.upsert_entity("feature", name="Orphan", seq=3, slug="orphan", project_id=UNKNOWN_LABEL)

    _assert_no_alias(delegated, _UNKNOWN_WORKSPACE_UUID)
    assert _row_workspace(db, "feature:003-orphan") == _UNKNOWN_WORKSPACE_UUID
    assert _created_label(db, "feature:003-orphan") == UNKNOWN_LABEL


def test_upsert_parent_alias_naming_no_entity_still_leaves_the_parent_unset(two_workspaces):
    """register_entity's tolerant alias resolution, preserved: an unresolvable
    parent_type_id registers the entity with no parent rather than raising."""
    db, ws_a, _ws_b = two_workspaces

    db.upsert_entity("feature", name="Loose", seq=4, slug="loose",
                     project_id=LEGACY_A, parent_type_id="project:099-missing")

    loose = db.get_entity("feature:004-loose")
    assert loose["workspace_uuid"] == ws_a
    assert loose["parent_uuid"] is None


# ---------------------------------------------------------------------------
# server_helpers: the MCP registration wrapper
# ---------------------------------------------------------------------------


def test_process_register_entity_resolves_project_id_to_one_workspace(two_workspaces, monkeypatch):
    db, ws_a, _ws_b = two_workspaces
    registered = _record_calls(monkeypatch, db, "register_entity")

    reply = _process_register_entity(db, "feature", {"seq": 5, "slug": "wrapped"}, "Wrapped",
                                     None, None, None, None, project_id=LEGACY_A)

    assert reply == "Registered: feature:005-wrapped"
    _assert_no_alias(registered, ws_a)
    assert _row_workspace(db, "feature:005-wrapped") == ws_a
    assert _created_label(db, "feature:005-wrapped") == LEGACY_A


def test_process_register_entity_prefers_the_workspace_it_is_given(two_workspaces, monkeypatch):
    db, _ws_a, ws_b = two_workspaces
    registered = _record_calls(monkeypatch, db, "register_entity")

    _process_register_entity(db, "feature", {"seq": 6, "slug": "given"}, "Given",
                             None, None, None, None, project_id=LEGACY_A, workspace_uuid=ws_b)

    _assert_no_alias(registered, ws_b)
    assert _created_label(db, "feature:006-given") == LEGACY_B


def test_process_register_entity_reports_an_unknown_project_id_as_before(two_workspaces):
    """The error string is the base build's, byte for byte."""
    db, _ws_a, _ws_b = two_workspaces

    reply = _process_register_entity(db, "feature", {"seq": 8, "slug": "stray"}, "Stray",
                                     None, None, None, None, project_id="no-such-legacy-id")

    assert reply == (
        "Error registering entity: register_entity(): project_id='no-such-legacy-id' has no "
        "matching workspaces.project_id_legacy row. Either pass workspace_uuid directly or "
        "pre-register the workspace."
    )
    assert db.get_entity("feature:008-stray") is None


# ---------------------------------------------------------------------------
# backfill: every scanner registers in the one resolved workspace
# ---------------------------------------------------------------------------


def _artifact_tree(root: Path) -> dict[str, str]:
    """One entity per scanner. Returns kind -> the type_id it registers."""
    (root / "backlog.md").write_text(
        "| ID | Timestamp | Description |\n|----|-----------|-------------|\n"
        "| 012-backlogged | 2026-01-01T00:00:00Z | A backlog item |\n")
    (root / "brainstorms").mkdir()
    (root / "brainstorms" / "20260101-000000-idea.prd.md").write_text("# Idea\n")
    for folder, name, meta in (
        ("projects", "003-proj", {"id": "003", "slug": "proj", "name": "Proj"}),
        ("features", "021-feat", {"id": "021", "slug": "feat", "name": "Feat"}),
    ):
        directory = root / folder / name
        directory.mkdir(parents=True)
        (directory / ".meta.json").write_text(json.dumps(meta))
    return {
        "backlog": "backlog:012-backlogged",
        "brainstorm": "brainstorm:20260101-000000-idea",
        "project": "project:003-proj",
        "feature": "feature:021-feat",
    }


@pytest.mark.parametrize("backfill_project_id, expected_label", [
    (LEGACY_A, LEGACY_A),
    (UNKNOWN_LABEL, UNKNOWN_LABEL),
])
def test_run_backfill_registers_every_kind_in_the_resolved_workspace(
    tmp_path, monkeypatch, backfill_project_id, expected_label,
):
    db = EntityDatabase(":memory:")
    ws_a = bootstrap_test_workspace(db, LEGACY_A)
    bootstrap_test_workspace(db, LEGACY_B)
    expected_workspace = ws_a if backfill_project_id == LEGACY_A else _UNKNOWN_WORKSPACE_UUID
    registered = _artifact_tree(tmp_path)
    upserts = _record_calls(monkeypatch, db, "upsert_entity")

    run_backfill(db, str(tmp_path), project_id=backfill_project_id)

    _assert_no_alias(upserts, expected_workspace)
    assert len(upserts) == len(registered)
    for kind, type_id in registered.items():
        assert _row_workspace(db, type_id) == expected_workspace, kind
        assert _created_label(db, type_id) == expected_label, kind
