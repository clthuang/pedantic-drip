"""C5b: callers register and allocate with one resolved ``workspace_uuid``.

Step 1 moved every production caller off the registration aliases:
``project_id`` (for ``workspace_uuid``) and ``parent_type_id`` (for
``parent_uuid``). Each caller now resolves ONE workspace at its boundary and
passes ``workspace_uuid``, and the allocator ``generate_entity_id`` takes
``workspace_uuid`` too. Step 2 deleted the aliases from ``register_entity``,
``upsert_entity`` and ``register_entities_batch``, and deleted ``project_id``
from ``generate_entity_id`` and ``next_sequence_value``. Its TypeError tests
are in ``test_c5b_step2_aliases_removed.py``.

The exit check below scans plugins/pd and the repository's scripts/ for any
call that still passes a removed parameter.

Two facts are pinned per converted site:

* **The alias no longer reaches registration** — a spy on the registration
  call sees ``workspace_uuid`` and no alias keyword.
* **The ``entity_created`` label is byte-identical to the base.** The label
  is the resolved workspace's ``project_id_legacy`` (``"__unknown__"`` when
  it has none). A workspace found through ``project_id_legacy`` carries the
  same string, so every expected label below is what the pre-C5b build wrote
  for the same input.
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
_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_SCANNED_ROOTS = (_PLUGIN_ROOT, _REPOSITORY_ROOT / "scripts")
_REGISTRATION_CALLS = frozenset({"register_entity", "upsert_entity", "register_entities_batch"})
_REGISTRATION_ALIASES = frozenset({"project_id", "parent_type_id"})
# The positional index each allocator's removed ``project_id`` occupied:
# generate_entity_id(db, entity_type, name, project_id) and
# next_sequence_value(project_id, entity_type).
_ALLOCATOR_PROJECT_ID_POSITION = {"generate_entity_id": 3, "next_sequence_value": 0}
_SKIPPED_DIRECTORIES = frozenset({".venv", "__pycache__", "node_modules"})


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
    name, positional ones included."""
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
# Exit check: no call passes a removed parameter
# ---------------------------------------------------------------------------


def _python_sources():
    """Every .py file under plugins/pd and the repository's scripts/: tests,
    conftest files and tools included."""
    for root in _SCANNED_ROOTS:
        assert root.is_dir(), f"scan root missing: {root}"
        for directory, subdirectories, files in os.walk(root):
            subdirectories[:] = [d for d in subdirectories if d not in _SKIPPED_DIRECTORIES]
            for file_name in files:
                if file_name.endswith(".py"):
                    yield Path(directory, file_name)


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _asserts_type_error(context: ast.expr) -> bool:
    """``pytest.raises(TypeError, ...)``."""
    return (isinstance(context, ast.Call) and _called_name(context) == "raises"
            and bool(context.args) and isinstance(context.args[0], ast.Name)
            and context.args[0].id == "TypeError")


def _calls_asserted_to_raise_type_error(tree: ast.AST) -> set[int]:
    """ids of the calls inside a ``with pytest.raises(TypeError)`` block: the
    TypeError tests that pass a removed parameter to prove it is refused."""
    asserted = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.With, ast.AsyncWith)) and any(
            _asserts_type_error(item.context_expr) for item in node.items
        ):
            asserted |= {id(inner) for statement in node.body
                         for inner in ast.walk(statement) if isinstance(inner, ast.Call)}
    return asserted


def _alias_keys_in_literals(expression: ast.expr) -> list[str]:
    """Alias names used as keys of a dict literal or ``dict(...)`` call within
    *expression*: a ``**`` splat's source, or a batch's entity list."""
    keys = []
    for node in ast.walk(expression):
        if isinstance(node, ast.Dict):
            keys += [key.value for key in node.keys
                     if isinstance(key, ast.Constant) and key.value in _REGISTRATION_ALIASES]
        elif isinstance(node, ast.Call) and _called_name(node) == "dict":
            keys += [keyword.arg for keyword in node.keywords if keyword.arg in _REGISTRATION_ALIASES]
    return keys


def _removed_parameters_passed(call: ast.Call, called: str) -> list[str]:
    if called in _REGISTRATION_CALLS:
        passed = [f"{keyword.arg}=" for keyword in call.keywords
                  if keyword.arg in _REGISTRATION_ALIASES]
        passed += [f"**{{{key!r}: ...}}" for keyword in call.keywords if keyword.arg is None
                   for key in _alias_keys_in_literals(keyword.value)]
        if called == "register_entities_batch" and call.args:
            passed += [f"entity[{key!r}]" for key in _alias_keys_in_literals(call.args[0])]
        return passed
    if called in _ALLOCATOR_PROJECT_ID_POSITION:
        passed = [f"{keyword.arg}=" for keyword in call.keywords if keyword.arg == "project_id"]
        position = _ALLOCATOR_PROJECT_ID_POSITION[called]
        if len(call.args) > position:
            passed.append(f"<positional argument {position + 1}: project_id>")
        return passed
    return []


def _removed_parameter_uses(path: Path) -> list[str]:
    with warnings.catch_warnings():
        # Parsing is all this needs; a module's own invalid-escape
        # SyntaxWarning is not this test's finding.
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    where = path.relative_to(_REPOSITORY_ROOT)
    asserted_refusals = _calls_asserted_to_raise_type_error(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or id(node) in asserted_refusals:
            continue
        called = _called_name(node)
        passed = _removed_parameters_passed(node, called)
        if passed:
            found.append(f"{where}:{node.lineno} {called}({', '.join(passed)})")
    return found


def test_no_call_passes_a_removed_alias():
    """C5b's exit check, over every Python file in plugins/pd and scripts/
    (tests included). No call passes ``project_id`` or ``parent_type_id`` to
    ``register_entity``, ``upsert_entity`` or ``register_entities_batch`` (as
    a keyword, a ``**`` dict literal, or a batch entity's key), and none passes
    ``project_id`` to ``generate_entity_id`` or ``next_sequence_value`` (as a
    keyword, or in the position it held). The only exceptions are calls
    inside ``with pytest.raises(TypeError)``: the tests that prove each
    parameter is refused. A ``**`` splat of a variable is not inspected; the
    suite's splats carry identity keywords only."""
    offending = [site for path in _python_sources() for site in _removed_parameter_uses(path)]
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
# database.py: upsert_entity's insert branch refuses in register_entity's name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("workspace, message", [
    ({}, "register_entity() requires workspace_uuid"),
    ({"workspace_uuid": "01900000-0000-7000-8000-00000000dead"},
     "register_entity(): workspace_uuid='01900000-0000-7000-8000-00000000dead' not "
     "present in the workspaces table — workspace.json/DB split-brain detected. Run "
     "pd:doctor --fix, then restart the session (MCP servers cache the workspace UUID "
     "at startup)."),
])
def test_upsert_insert_branch_refusals_are_the_base_messages(two_workspaces, workspace, message):
    """The insert branch validates its workspace inside register_entity, so a
    refusal names register_entity() as before C5b; the reconciler records
    these strings as its warnings. (The missing-workspace message lost its
    "or project_id" when C5b step 2 deleted that alias.)"""
    db, _ws_a, _ws_b = two_workspaces

    with pytest.raises(ValueError) as refusal:
        db.upsert_entity("feature", name="Refused", seq=10, slug="refused", **workspace)

    assert str(refusal.value) == message
    assert db.get_entity("feature:010-refused") is None


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
