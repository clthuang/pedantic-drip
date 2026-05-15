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
from workflow_state_server import _project_meta_json  # noqa: E402


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
