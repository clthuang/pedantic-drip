"""Projection determinism tests (feature 110 Group 5).

Scope:
  - ``_project_meta_json`` reads id/slug from ``entity_display`` table
    (Task 5.2 / AC-8.5).
  - ``_project_meta_json`` is byte-deterministic (Task 5.3 / AC-4.1).
  - Regenerating ``.meta.json`` after deletion produces byte-identical
    output (Task 5.4 / AC-4.3).
  - Manual edits to ``.meta.json`` do NOT mutate the DB (Task 5.5 / AC-4.5).

These tests live in ``hooks/lib/entity_registry/`` (per design §2.1) rather
than ``plugins/pd/mcp/`` so they pick up the local ``conftest.py`` that
disables strict entity_id-format enforcement for legacy fixtures. The tests
explicitly populate ``entity_display`` via raw SQL when they need to
exercise the entity_display read path, sidestepping the strict-mode toggle
entirely.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import uuid as _uuid
from pathlib import Path

import pytest

# Make the MCP module importable when this test file runs under the
# entity_registry test collection (it normally sits alongside other
# hooks/lib tests but imports from plugins/pd/mcp/).
_REPO_ROOT = Path(__file__).resolve().parents[5]
_MCP = str(_REPO_ROOT / "plugins" / "pd" / "mcp")
if _MCP not in sys.path:
    sys.path.insert(0, _MCP)

from entity_registry.database import EntityDatabase  # noqa: E402
from workflow_state_server import (  # noqa: E402
    _project_backlog_md,
    _project_meta_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_feature(
    db: EntityDatabase,
    *,
    feature_dir: str,
    entity_id: str = "043-projection-test",
    name: str = "Projection Test",
    branch: str = "feature/043-projection-test",
) -> tuple[str, dict]:
    """Insert a feature entity AND its entity_display row, returning
    ``(type_id, metadata_dict)``. Uses raw SQL for the entity_display row
    so the test does not depend on the strict-format env-var toggle.
    """
    metadata = {
        "id": entity_id.split("-", 1)[0],
        "slug": entity_id.split("-", 1)[1],
        "mode": "standard",
        "branch": branch,
        "phase_timing": {
            "brainstorm": {
                "started": "2026-03-01T00:00:00Z",
                "completed": "2026-03-02T00:00:00Z",
            },
            "specify": {"started": "2026-03-02T00:00:00Z"},
        },
    }
    os.makedirs(feature_dir, exist_ok=True)
    db.register_entity(
        "feature",
        entity_id,
        name,
        artifact_path=feature_dir,
        status="active",
        metadata=metadata,
        project_id="__unknown__",
    )
    type_id = f"feature:{entity_id}"

    # Ensure entity_display has a row even when strict-format check is
    # disabled (the conftest sets the env var to "0" for the hooks/lib
    # suite, which means register_entity skips the entity_display INSERT).
    entity = db.get_entity(type_id)
    assert entity is not None
    seq_str, slug = entity_id.split("-", 1)
    db._conn.execute(
        "INSERT OR REPLACE INTO entity_display (uuid, seq, slug) "
        "VALUES (?, ?, ?)",
        (entity["uuid"], int(seq_str), slug),
    )
    db._conn.commit()

    return type_id, metadata


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Task 5.2 / AC-8.5 — entity_display is the source of id+slug
# ---------------------------------------------------------------------------


def test_meta_json_reads_entity_display(tmp_path: Path) -> None:
    """Deleting ``id``/``slug`` from ``entities.metadata`` JSON post-migration
    does NOT affect ``.meta.json`` output. The projection reads identity
    from ``entity_display`` (FR-8.3b)."""
    db = EntityDatabase(":memory:")
    feature_dir = str(tmp_path / "features" / "043-projection-test")
    type_id, _md = _seed_feature(db, feature_dir=feature_dir)

    # First projection (baseline).
    warn = _project_meta_json(db, None, type_id, feature_dir)
    assert warn is None, f"projection emitted warning: {warn}"
    meta_path = os.path.join(feature_dir, ".meta.json")
    pre_bytes = _read_bytes(meta_path)

    # Surgically strip id + slug from entities.metadata JSON. The projection
    # MUST still emit the same bytes because entity_display is the source.
    entity = db.get_entity(type_id)
    md = json.loads(entity["metadata"])
    md.pop("id", None)
    md.pop("slug", None)
    db._conn.execute(
        "UPDATE entities SET metadata = ? WHERE type_id = ?",
        (json.dumps(md), type_id),
    )
    db._conn.commit()

    warn2 = _project_meta_json(db, None, type_id, feature_dir)
    assert warn2 is None
    post_bytes = _read_bytes(meta_path)

    assert post_bytes == pre_bytes, (
        f"projection output drifted after metadata id/slug removal "
        f"(pre={pre_bytes!r}, post={post_bytes!r}). "
        f"entity_display read path is broken."
    )


# ---------------------------------------------------------------------------
# Task 5.3 / AC-4.1 — byte-deterministic projection
# ---------------------------------------------------------------------------


def test_meta_json_byte_deterministic(tmp_path: Path) -> None:
    """Two consecutive projection invocations produce SHA256-equal bytes.

    Also asserts (static-grep) that the ``_project_meta_json`` body contains
    no ``datetime.utcnow()`` / ``datetime.now()`` calls. AC-4.1 enforces
    these together.
    """
    db = EntityDatabase(":memory:")
    feature_dir = str(tmp_path / "features" / "044-determinism")
    type_id, _ = _seed_feature(
        db,
        feature_dir=feature_dir,
        entity_id="044-determinism",
        name="Deterministic",
        branch="feature/044-determinism",
    )

    warn1 = _project_meta_json(db, None, type_id, feature_dir)
    assert warn1 is None
    meta_path = os.path.join(feature_dir, ".meta.json")
    bytes_1 = _read_bytes(meta_path)
    hash_1 = hashlib.sha256(bytes_1).hexdigest()

    warn2 = _project_meta_json(db, None, type_id, feature_dir)
    assert warn2 is None
    bytes_2 = _read_bytes(meta_path)
    hash_2 = hashlib.sha256(bytes_2).hexdigest()

    assert hash_1 == hash_2, (
        f"_project_meta_json is NOT byte-deterministic: hash drifted "
        f"({hash_1} -> {hash_2})"
    )
    assert bytes_1 == bytes_2

    # Static-check (AC-4.1 second part): the projection function body
    # references no datetime.utcnow / datetime.now calls. We parse the
    # source file and scan the function range.
    import ast
    import inspect
    import workflow_state_server as wss

    source_file = inspect.getsourcefile(wss._project_meta_json)
    assert source_file is not None
    tree = ast.parse(Path(source_file).read_text())
    target = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.FunctionDef)
                and node.name == "_project_meta_json"):
            target = node
            break
    assert target is not None, "_project_meta_json not found in AST"

    forbidden = {"utcnow", "now"}
    offending: list[str] = []
    for node in ast.walk(target):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (node.func.attr in forbidden
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "datetime"):
                offending.append(ast.unparse(node))
    assert not offending, (
        f"_project_meta_json must not call datetime.utcnow/now "
        f"(volatile state); found: {offending}"
    )


# ---------------------------------------------------------------------------
# Task 5.4 / AC-4.3 — regenerate after delete matches pre-delete bytes
# ---------------------------------------------------------------------------


def test_meta_json_regenerate_after_delete_matches(tmp_path: Path) -> None:
    """AC-4.3: deleting ``.meta.json`` does not touch DB state; re-running
    the projection rebuilds byte-identical content."""
    db = EntityDatabase(":memory:")
    feature_dir = str(tmp_path / "features" / "045-regenerate")
    type_id, _ = _seed_feature(
        db,
        feature_dir=feature_dir,
        entity_id="045-regenerate",
        name="Regenerate Test",
        branch="feature/045-regenerate",
    )

    warn = _project_meta_json(db, None, type_id, feature_dir)
    assert warn is None
    meta_path = os.path.join(feature_dir, ".meta.json")
    pre_bytes = _read_bytes(meta_path)
    pre_status = db.get_entity(type_id)["status"]

    # Delete the file. Confirm DB row unchanged.
    os.remove(meta_path)
    assert not os.path.exists(meta_path)
    mid_status = db.get_entity(type_id)["status"]
    assert mid_status == pre_status, (
        "DB entity status drifted after .meta.json deletion (R5/FR-4.7)"
    )

    # Re-project. Bytes match.
    warn2 = _project_meta_json(db, None, type_id, feature_dir)
    assert warn2 is None
    post_bytes = _read_bytes(meta_path)
    assert post_bytes == pre_bytes, (
        f"Re-projected .meta.json bytes diverge:\n"
        f"  pre:  {pre_bytes!r}\n"
        f"  post: {post_bytes!r}"
    )


# ---------------------------------------------------------------------------
# Task 5.5 / AC-4.5 — tamper safety
# ---------------------------------------------------------------------------


def test_meta_json_tamper_safety(tmp_path: Path) -> None:
    """AC-4.5: manually editing ``.meta.json`` (appending ``"tampered":
    true``) does NOT change ``entities.status``; re-projecting overwrites
    the tampered file with canonical content."""
    db = EntityDatabase(":memory:")
    feature_dir = str(tmp_path / "features" / "046-tamper")
    type_id, _ = _seed_feature(
        db,
        feature_dir=feature_dir,
        entity_id="046-tamper",
        name="Tamper Test",
        branch="feature/046-tamper",
    )

    warn = _project_meta_json(db, None, type_id, feature_dir)
    assert warn is None
    meta_path = os.path.join(feature_dir, ".meta.json")
    pre_bytes = _read_bytes(meta_path)
    pre_status = db.get_entity(type_id)["status"]

    # Tamper with the file on disk.
    with open(meta_path, "r") as f:
        meta = json.load(f)
    meta["tampered"] = True
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    # DB unaffected.
    post_tamper_status = db.get_entity(type_id)["status"]
    assert post_tamper_status == pre_status, (
        "Tampering with .meta.json must not mutate DB state"
    )

    # Re-project — canonical content restored.
    warn2 = _project_meta_json(db, None, type_id, feature_dir)
    assert warn2 is None
    regenerated_bytes = _read_bytes(meta_path)
    regenerated = json.loads(regenerated_bytes)
    assert "tampered" not in regenerated, (
        f"Projection failed to overwrite tampered field; got {regenerated!r}"
    )
    assert regenerated_bytes == pre_bytes, (
        "Re-projection after tamper did not restore canonical bytes"
    )


# ---------------------------------------------------------------------------
# Group 8 backlog projection tests — feature 110 FR-4.2 / TD-10
# ---------------------------------------------------------------------------


def _seed_backlog_entity(
    db: EntityDatabase,
    *,
    entity_id: str,
    name: str,
    created_at: str,
    metadata: dict | None = None,
    status: str = "open",
    workspace_uuid: str | None = None,
) -> str:
    """Seed a backlog entity directly via raw SQL.

    Raw SQL is used (rather than ``register_entity``) so the test does
    not depend on the strict-format env-var toggle AND so the
    deterministic ``created_at`` value is honored exactly (the
    ``register_entity`` path stamps an ``_iso_now()`` value).
    """
    # Reuse the conftest-installed __unknown__ workspace seed so the
    # FK on entities.workspace_uuid resolves. The bootstrap workspace
    # row is created lazily; force-create it here.
    if workspace_uuid is None:
        db._ensure_unknown_workspace_row()
        row = db._conn.execute(
            "SELECT uuid FROM workspaces "
            "WHERE project_id_legacy = '__unknown__' LIMIT 1"
        ).fetchone()
        assert row is not None, (
            "Bootstrap workspace row missing — test environment broken"
        )
        workspace_uuid = row["uuid"]

    entity_uuid = str(_uuid.uuid4())
    type_id = f"backlog:{entity_id}"
    md_json = json.dumps(metadata or {})
    db._conn.execute(
        "INSERT INTO entities ("
        "uuid, workspace_uuid, type_id, entity_id, name, status, "
        "metadata, created_at, updated_at, "
        "type, kind, lifecycle_class"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entity_uuid,
            workspace_uuid,
            type_id,
            entity_id,
            name,
            status,
            md_json,
            created_at,
            created_at,
            "work",
            "backlog",
            "work_flow",
        ),
    )

    # Populate entity_display for the row. Backlog ids may be pure
    # 5-digit ("00008") or "00400-slug" form — handle both.
    if "-" in entity_id:
        head, _, tail = entity_id.partition("-")
        try:
            seq = int(head)
        except ValueError:
            seq = 0
        slug = tail
    else:
        try:
            seq = int(entity_id)
        except ValueError:
            seq = 0
        slug = ""
    db._conn.execute(
        "INSERT OR REPLACE INTO entity_display (uuid, seq, slug) "
        "VALUES (?, ?, ?)",
        (entity_uuid, seq, slug),
    )
    db._conn.commit()
    return entity_uuid


def test_project_backlog_md_callable() -> None:
    """Task 5.6 / AC-1.3: ``_project_backlog_md`` is importable + callable.

    The deferred Task 5.6 belongs to Group 5 but is tested here alongside
    the Group 8 backlog suite to keep all backlog-projection asserts in
    one file.
    """
    import workflow_state_server as wss
    assert callable(wss._project_backlog_md)


def test_backlog_md_byte_deterministic(tmp_path: Path) -> None:
    """Task 8.3 / AC-4.2: two consecutive ``_project_backlog_md(db)``
    calls produce SHA256-identical output."""
    db = EntityDatabase(":memory:")

    # Mix formats so the section-grouping branch is exercised in
    # determinism testing.
    _seed_backlog_entity(
        db,
        entity_id="00008",
        name="add product manager agent",
        created_at="2026-01-31T12:05:00Z",
        metadata={"format": "table_row"},
    )
    _seed_backlog_entity(
        db,
        entity_id="00012",
        name="fix the secretary AskUserQuestion formatting.",
        created_at="2026-02-17T12:00:00Z",
        metadata={"format": "table_row"},
    )
    _seed_backlog_entity(
        db,
        entity_id="00367",
        name="[MED-security] dummy",
        created_at="2026-05-11T00:00:00Z",
        metadata={
            "format": "bullet_item",
            "section": "From Feature 108 Pre-Release QA Findings (2026-05-11)",
            "subsection": "MED findings (auto-filed from QA gate)",
        },
    )
    _seed_backlog_entity(
        db,
        entity_id="00360",
        name="[HIGH-deferred] FR-3 violated",
        created_at="2026-05-11T00:00:01Z",
        metadata={
            "format": "bullet_item",
            "section": "From Feature 108 Pre-Release QA Findings (2026-05-11)",
            "section_intro": (
                "Feature 108 Pre-Release Adversarial QA Gate surfaced "
                "blockers."
            ),
            "subsection": "HIGH-cluster deferrals (rationale in qa-override.md)",
        },
    )

    result_1 = _project_backlog_md(db)
    result_2 = _project_backlog_md(db)

    hash_1 = hashlib.sha256(result_1.encode("utf-8")).hexdigest()
    hash_2 = hashlib.sha256(result_2.encode("utf-8")).hexdigest()
    assert hash_1 == hash_2, (
        f"_project_backlog_md is NOT byte-deterministic "
        f"({hash_1} vs {hash_2})"
    )
    assert result_1 == result_2


def test_backlog_md_no_datetime_now_calls() -> None:
    """Task 8.4 / AC-4.2 static check: ``_project_backlog_md`` body
    contains no ``datetime.utcnow()`` / ``datetime.now()`` calls."""
    import ast
    import inspect
    import workflow_state_server as wss

    source_file = inspect.getsourcefile(wss._project_backlog_md)
    assert source_file is not None
    tree = ast.parse(Path(source_file).read_text())
    target = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.FunctionDef)
                and node.name == "_project_backlog_md"):
            target = node
            break
    assert target is not None, "_project_backlog_md not found in AST"

    forbidden = {"utcnow", "now"}
    offending: list[str] = []
    for node in ast.walk(target):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr in forbidden:
                # Match datetime.utcnow() / datetime.now().
                if (isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "datetime"):
                    offending.append(ast.unparse(node))
    assert not offending, (
        f"_project_backlog_md must not call datetime.utcnow/now "
        f"(volatile state); found: {offending}"
    )


def test_backlog_md_regenerate_after_delete(tmp_path: Path) -> None:
    """Task 8.5 / AC-4.4: deleting the projected file and re-running
    ``_project_backlog_md`` yields byte-identical content."""
    db = EntityDatabase(":memory:")
    _seed_backlog_entity(
        db,
        entity_id="00001",
        name="first item",
        created_at="2026-01-01T00:00:00Z",
        metadata={"format": "table_row"},
    )
    _seed_backlog_entity(
        db,
        entity_id="00002",
        name="second item with | pipe",
        created_at="2026-01-02T00:00:00Z",
        metadata={"format": "table_row"},
    )

    backlog_path = tmp_path / "backlog.md"
    pre_text = _project_backlog_md(db)
    backlog_path.write_text(pre_text, encoding="utf-8")
    pre_bytes = backlog_path.read_bytes()

    # Delete the file. Re-project. Bytes must match.
    backlog_path.unlink()
    assert not backlog_path.exists()
    post_text = _project_backlog_md(db)
    backlog_path.write_text(post_text, encoding="utf-8")
    post_bytes = backlog_path.read_bytes()

    assert post_bytes == pre_bytes, (
        f"Re-projected backlog bytes diverge:\n"
        f"  pre:  {pre_bytes!r}\n"
        f"  post: {post_bytes!r}"
    )


def test_compare_backlog_projection_script_no_drift(tmp_path: Path) -> None:
    """Task 8.6 / AC-4.2a: the ``compare_backlog_projection.py`` script
    exits 0 when fed identical fixture content.

    Verifies the script exists, is importable, and that its whitespace-
    normalized comparison succeeds on a fixture DB whose projection
    equals the fixture file (by construction).
    """
    import subprocess

    script_path = (
        _REPO_ROOT / "plugins" / "pd" / "scripts"
        / "compare_backlog_projection.py"
    )
    assert script_path.exists(), (
        f"compare_backlog_projection.py missing at {script_path}"
    )

    # Seed a fixture DB with two table-row entries.
    db_path = tmp_path / "entities.db"
    db = EntityDatabase(str(db_path))
    _seed_backlog_entity(
        db,
        entity_id="00001",
        name="alpha",
        created_at="2026-01-01T00:00:00Z",
        metadata={"format": "table_row"},
    )
    _seed_backlog_entity(
        db,
        entity_id="00002",
        name="beta",
        created_at="2026-01-02T00:00:00Z",
        metadata={"format": "table_row"},
    )

    # Render projection into a fixture file. The script's comparison
    # MUST then report zero drift against this file.
    fixture_backlog = tmp_path / "backlog.md"
    fixture_backlog.write_text(_project_backlog_md(db), encoding="utf-8")
    db.close()

    proc = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--backlog-path",
            str(fixture_backlog),
            "--db-path",
            str(db_path),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"compare_backlog_projection.py reported drift on byte-identical "
        f"fixture:\n  stdout={proc.stdout!r}\n  stderr={proc.stderr!r}"
    )
