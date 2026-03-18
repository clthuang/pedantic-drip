"""Unit tests for brainstorm_registry.sync_brainstorm_entities (TDD — tests first).

Run with:
    plugins/iflow/.venv/bin/python -m pytest \
        plugins/iflow/hooks/lib/reconciliation_orchestrator/test_brainstorm_registry.py -v
"""
import os
import tempfile

import pytest

from entity_registry.database import EntityDatabase
from reconciliation_orchestrator.brainstorm_registry import sync_brainstorm_entities


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> EntityDatabase:
    """Return an in-memory EntityDatabase for test isolation."""
    return EntityDatabase(":memory:")


def _make_brainstorms_dir(base: str, filenames: list[str]) -> str:
    """Create base/brainstorms/ with the given files and return base path."""
    brainstorms = os.path.join(base, "brainstorms")
    os.makedirs(brainstorms, exist_ok=True)
    for name in filenames:
        open(os.path.join(brainstorms, name), "w").close()
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSyncBrainstormEntities:
    def test_unregistered_file_registered(self):
        """A .prd.md file with no entity in registry → entity registered."""
        db = _make_db()
        with tempfile.TemporaryDirectory() as base:
            _make_brainstorms_dir(base, ["20260318-my-idea.prd.md"])
            result = sync_brainstorm_entities(db, base, "docs")

        assert result["registered"] == 1
        assert result["skipped"] == 0

        entity = db.get_entity("brainstorm:20260318-my-idea")
        assert entity is not None
        assert entity["entity_type"] == "brainstorm"
        assert entity["entity_id"] == "20260318-my-idea"
        assert entity["status"] == "active"

    def test_already_registered_skipped(self):
        """An entity already in the registry → skipped (idempotent)."""
        db = _make_db()
        stem = "20260318-already-exists"
        db.register_entity(
            entity_type="brainstorm",
            entity_id=stem,
            name=stem,
            status="active",
        )

        with tempfile.TemporaryDirectory() as base:
            _make_brainstorms_dir(base, [f"{stem}.prd.md"])
            result = sync_brainstorm_entities(db, base, "docs")

        assert result["registered"] == 0
        assert result["skipped"] == 1
        # Confirm only one entity exists (no duplicate)
        entities = db.list_entities(entity_type="brainstorm")
        assert len(entities) == 1

    def test_gitkeep_ignored(self):
        """.gitkeep file → not registered."""
        db = _make_db()
        with tempfile.TemporaryDirectory() as base:
            _make_brainstorms_dir(base, [".gitkeep"])
            result = sync_brainstorm_entities(db, base, "docs")

        assert result["registered"] == 0
        assert result["skipped"] == 0
        assert db.list_entities(entity_type="brainstorm") == []

    def test_non_prd_md_ignored(self):
        """A .txt file (non-.prd.md) → not registered."""
        db = _make_db()
        with tempfile.TemporaryDirectory() as base:
            _make_brainstorms_dir(base, ["notes.txt", "README.md"])
            result = sync_brainstorm_entities(db, base, "docs")

        assert result["registered"] == 0
        assert result["skipped"] == 0
        assert db.list_entities(entity_type="brainstorm") == []

    def test_missing_directory_handled(self):
        """brainstorms/ directory doesn't exist → returns empty results without error."""
        db = _make_db()
        with tempfile.TemporaryDirectory() as base:
            # Do NOT create brainstorms/ subdirectory
            result = sync_brainstorm_entities(db, base, "docs")

        assert result == {"registered": 0, "skipped": 0}

    def test_artifact_path_relative(self):
        """Stored artifact_path uses relative artifacts_root path, not absolute."""
        db = _make_db()
        filename = "20260318-check-path.prd.md"
        artifacts_root = "docs"

        with tempfile.TemporaryDirectory() as base:
            _make_brainstorms_dir(base, [filename])
            sync_brainstorm_entities(db, base, artifacts_root)

        entity = db.get_entity("brainstorm:20260318-check-path")
        assert entity is not None
        expected_path = os.path.join(artifacts_root, "brainstorms", filename)
        assert entity["artifact_path"] == expected_path
        # Must NOT be an absolute path containing the temp dir
        assert not os.path.isabs(entity["artifact_path"])
