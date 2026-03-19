"""Tests for semantic_memory.writer CLI module."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from semantic_memory import content_hash
from semantic_memory.database import MemoryDatabase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry_json(
    name: str = "Test pattern",
    description: str = "A useful pattern for testing",
    category: str = "patterns",
    **extra,
) -> str:
    """Build a JSON string for a valid entry."""
    entry = {"name": name, "description": description, "category": category}
    entry.update(extra)
    return json.dumps(entry)


def _make_mock_provider(dimensions: int = 768):
    """Create a mock embedding provider that returns deterministic vectors."""
    provider = MagicMock()
    provider.dimensions = dimensions
    provider.provider_name = "mock"
    provider.model_name = "mock-model"

    def embed_side_effect(text, task_type="document"):
        return np.ones(dimensions, dtype=np.float32) * 0.5

    provider.embed.side_effect = embed_side_effect
    return provider


def _run_main(args: list[str]) -> tuple[int, str, str]:
    """Run writer.main() with the given args and capture exit code + output.

    Returns (exit_code, stdout, stderr).
    """
    from semantic_memory.writer import main

    captured_code = [0]

    def fake_exit(code=0):
        captured_code[0] = code
        raise SystemExit(code)

    with patch("sys.argv", ["writer.py"] + args), \
         patch("sys.exit", fake_exit):
        import io
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            main()
        except SystemExit:
            pass
        stdout_val = sys.stdout.getvalue()
        stderr_val = sys.stderr.getvalue()
        sys.stdout, sys.stderr = old_stdout, old_stderr

    return captured_code[0], stdout_val, stderr_val


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def global_store(tmp_path):
    """Provide a temp directory as the global store."""
    store = tmp_path / "global-store"
    store.mkdir()
    return str(store)


# ---------------------------------------------------------------------------
# Test: Valid entry JSON -> DB entry with correct content hash
# ---------------------------------------------------------------------------


class TestValidEntry:
    def test_valid_entry_stored_with_content_hash(self, global_store, tmp_path):
        """A valid entry JSON produces a DB entry with the correct content hash as ID."""
        entry_json = _make_entry_json()
        entry_data = json.loads(entry_json)
        expected_hash = content_hash(entry_data["description"])

        with patch("semantic_memory.writer.create_provider", return_value=None), \
             patch("semantic_memory.writer.read_config", return_value={}):
            exit_code, stdout, stderr = _run_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", entry_json,
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 0
        assert f"id: {expected_hash}" in stdout

        # Verify in DB
        db = MemoryDatabase(os.path.join(global_store, "memory.db"))
        entry = db.get_entry(expected_hash)
        assert entry is not None
        assert entry["name"] == "Test pattern"
        assert entry["description"] == "A useful pattern for testing"
        assert entry["category"] == "patterns"
        db.close()


# ---------------------------------------------------------------------------
# Test: Entry with all optional fields
# ---------------------------------------------------------------------------


class TestAllOptionalFields:
    def test_all_optional_fields_stored(self, global_store, tmp_path):
        """All optional fields (reasoning, keywords, references, confidence,
        source, source_project) are stored correctly."""
        entry_json = _make_entry_json(
            reasoning="This matters because testing is fundamental",
            keywords=["testing", "tdd"],
            references=["path/to/file.py", "feature/024"],
            confidence="high",
            source="retro",
            source_project="/path/to/project",
        )
        entry_data = json.loads(entry_json)
        expected_hash = content_hash(entry_data["description"])

        with patch("semantic_memory.writer.create_provider", return_value=None), \
             patch("semantic_memory.writer.read_config", return_value={}):
            exit_code, stdout, stderr = _run_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", entry_json,
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 0

        db = MemoryDatabase(os.path.join(global_store, "memory.db"))
        entry = db.get_entry(expected_hash)
        assert entry is not None
        assert entry["reasoning"] == "This matters because testing is fundamental"
        assert json.loads(entry["keywords"]) == ["testing", "tdd"]
        assert json.loads(entry["references"]) == ["path/to/file.py", "feature/024"]
        assert entry["confidence"] == "high"
        assert entry["source"] == "retro"
        assert entry["source_project"] == "/path/to/project"
        db.close()


# ---------------------------------------------------------------------------
# Test: Invalid category -> exit code 1
# ---------------------------------------------------------------------------


class TestInvalidCategory:
    def test_invalid_category_exits_1(self, global_store, tmp_path):
        """An invalid category produces exit code 1."""
        entry_json = _make_entry_json(category="invalid-category")

        with patch("semantic_memory.writer.create_provider", return_value=None), \
             patch("semantic_memory.writer.read_config", return_value={}):
            exit_code, stdout, stderr = _run_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", entry_json,
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 1
        assert "category" in stderr.lower()


# ---------------------------------------------------------------------------
# Test: Missing name -> exit code 1
# ---------------------------------------------------------------------------


class TestMissingName:
    def test_missing_name_exits_1(self, global_store, tmp_path):
        """A missing name field produces exit code 1."""
        entry_json = json.dumps({
            "description": "A description",
            "category": "patterns",
        })

        with patch("semantic_memory.writer.create_provider", return_value=None), \
             patch("semantic_memory.writer.read_config", return_value={}):
            exit_code, stdout, stderr = _run_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", entry_json,
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 1
        assert "name" in stderr.lower()

    def test_empty_name_exits_1(self, global_store, tmp_path):
        """An empty name field produces exit code 1."""
        entry_json = _make_entry_json(name="")

        with patch("semantic_memory.writer.create_provider", return_value=None), \
             patch("semantic_memory.writer.read_config", return_value={}):
            exit_code, stdout, stderr = _run_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", entry_json,
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 1
        assert "name" in stderr.lower()


# ---------------------------------------------------------------------------
# Test: Missing description -> exit code 1
# ---------------------------------------------------------------------------


class TestMissingDescription:
    def test_missing_description_exits_1(self, global_store, tmp_path):
        """A missing description field produces exit code 1."""
        entry_json = json.dumps({
            "name": "Test",
            "category": "patterns",
        })

        with patch("semantic_memory.writer.create_provider", return_value=None), \
             patch("semantic_memory.writer.read_config", return_value={}):
            exit_code, stdout, stderr = _run_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", entry_json,
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 1
        assert "description" in stderr.lower()

    def test_empty_description_exits_1(self, global_store, tmp_path):
        """An empty description field produces exit code 1."""
        entry_json = _make_entry_json(description="")

        with patch("semantic_memory.writer.create_provider", return_value=None), \
             patch("semantic_memory.writer.read_config", return_value={}):
            exit_code, stdout, stderr = _run_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", entry_json,
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 1
        assert "description" in stderr.lower()


# ---------------------------------------------------------------------------
# Test: Provider unavailable -> stored without embedding
# ---------------------------------------------------------------------------


class TestProviderUnavailable:
    def test_stored_without_embedding_when_no_provider(self, global_store, tmp_path):
        """When no embedding provider is available, entry is stored with embedding=None."""
        entry_json = _make_entry_json()
        entry_data = json.loads(entry_json)
        expected_hash = content_hash(entry_data["description"])

        with patch("semantic_memory.writer.create_provider", return_value=None), \
             patch("semantic_memory.writer.read_config", return_value={}):
            exit_code, stdout, stderr = _run_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", entry_json,
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 0

        db = MemoryDatabase(os.path.join(global_store, "memory.db"))
        entry = db.get_entry(expected_hash)
        assert entry is not None
        assert entry["embedding"] is None
        db.close()


# ---------------------------------------------------------------------------
# Test: Pending batch processing
# ---------------------------------------------------------------------------


class TestPendingBatch:
    def test_pending_entries_get_embeddings(self, global_store, tmp_path):
        """Insert 3 entries without embeddings, then writer processes them."""
        # Pre-populate DB with 3 entries that have no embedding
        db_path = os.path.join(global_store, "memory.db")
        db = MemoryDatabase(db_path)
        for i in range(3):
            db.upsert_entry({
                "id": f"pre_entry_{i}",
                "name": f"Pre-existing {i}",
                "description": f"Description {i}",
                "category": "patterns",
                "source": "manual",
                "source_project": str(tmp_path),
                "source_hash": f"hash{i:014d}",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            })
        # Verify they have no embedding
        pending = db.get_entries_without_embedding()
        assert len(pending) == 3
        db.close()

        mock_provider = _make_mock_provider()

        entry_json = _make_entry_json(
            name="New entry",
            description="A brand new entry",
        )

        with patch("semantic_memory.writer.create_provider", return_value=mock_provider), \
             patch("semantic_memory.writer.read_config", return_value={
                 "memory_embedding_provider": "mock",
                 "memory_embedding_model": "mock-model",
             }):
            exit_code, stdout, stderr = _run_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", entry_json,
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 0

        # Verify pending entries now have embeddings
        db = MemoryDatabase(db_path)
        pending = db.get_entries_without_embedding()
        assert len(pending) == 0, f"Expected 0 pending entries, got {len(pending)}"
        db.close()


# ---------------------------------------------------------------------------
# Test: Provider migration (TD9)
# ---------------------------------------------------------------------------


class TestProviderMigration:
    def test_provider_change_clears_embeddings(self, global_store, tmp_path):
        """When embedding provider changes, all existing embeddings are cleared."""
        db_path = os.path.join(global_store, "memory.db")
        db = MemoryDatabase(db_path)
        # Insert entry with embedding and set old provider metadata
        emb = np.ones(768, dtype=np.float32).tobytes()
        db.upsert_entry({
            "id": "existing_entry",
            "name": "Existing",
            "description": "Old entry with embedding",
            "category": "patterns",
            "source": "manual",
            "source_project": str(tmp_path),
            "source_hash": "existinghash1234",
            "embedding": emb,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        })
        db.set_metadata("embedding_provider", "old-provider")
        db.set_metadata("embedding_model", "old-model")
        # Verify embedding exists
        entry = db.get_entry("existing_entry")
        assert entry["embedding"] is not None
        db.close()

        mock_provider = _make_mock_provider()
        entry_json = _make_entry_json()

        with patch("semantic_memory.writer.create_provider", return_value=mock_provider), \
             patch("semantic_memory.writer.read_config", return_value={
                 "memory_embedding_provider": "new-provider",
                 "memory_embedding_model": "new-model",
             }):
            exit_code, stdout, stderr = _run_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", entry_json,
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 0
        assert "embedding provider changed" in stderr.lower()

        # Verify old embedding was cleared (then re-embedded via pending batch)
        db = MemoryDatabase(db_path)
        # The metadata should reflect the new provider
        assert db.get_metadata("embedding_provider") == "new-provider"
        assert db.get_metadata("embedding_model") == "new-model"
        db.close()


# ---------------------------------------------------------------------------
# Test: Duplicate entry -> observation_count incremented
# ---------------------------------------------------------------------------


class TestDuplicateEntry:
    def test_duplicate_increments_observation_count(self, global_store, tmp_path):
        """Upserting the same entry twice increments observation_count."""
        entry_json = _make_entry_json()
        entry_data = json.loads(entry_json)
        expected_hash = content_hash(entry_data["description"])

        with patch("semantic_memory.writer.create_provider", return_value=None), \
             patch("semantic_memory.writer.read_config", return_value={}):
            _run_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", entry_json,
                "--project-root", str(tmp_path),
            ])
            _run_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-json", entry_json,
                "--project-root", str(tmp_path),
            ])

        db = MemoryDatabase(os.path.join(global_store, "memory.db"))
        entry = db.get_entry(expected_hash)
        assert entry is not None
        assert entry["observation_count"] == 2
        db.close()


# ---------------------------------------------------------------------------
# Test: --entry-file reads from file
# ---------------------------------------------------------------------------


class TestEntryFile:
    def test_entry_file_reads_from_file(self, global_store, tmp_path):
        """--entry-file reads entry JSON from a file."""
        entry_json = _make_entry_json()
        entry_file = tmp_path / "entry.json"
        entry_file.write_text(entry_json)

        entry_data = json.loads(entry_json)
        expected_hash = content_hash(entry_data["description"])

        with patch("semantic_memory.writer.create_provider", return_value=None), \
             patch("semantic_memory.writer.read_config", return_value={}):
            exit_code, stdout, stderr = _run_main([
                "--action", "upsert",
                "--global-store", global_store,
                "--entry-file", str(entry_file),
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 0
        assert f"id: {expected_hash}" in stdout

        db = MemoryDatabase(os.path.join(global_store, "memory.db"))
        entry = db.get_entry(expected_hash)
        assert entry is not None
        assert entry["name"] == "Test pattern"
        db.close()


# ---------------------------------------------------------------------------
# Test: _build_db_entry
# ---------------------------------------------------------------------------

from semantic_memory.writer import _build_db_entry  # noqa: E402
from semantic_memory import source_hash as sh_fn  # noqa: E402


class TestBuildDbEntry:
    def test_defaults_keywords_to_empty_json(self):
        """When keywords are not provided, should default to '[]'."""
        entry = {"name": "Test", "description": "Desc", "category": "patterns",
                 "source": "manual"}
        result = _build_db_entry(entry, "test_id", "2026-01-01T00:00:00Z",
                                 project_root="/proj")
        assert result["keywords"] == "[]"

    def test_sets_source_hash(self):
        """source_hash should be computed from description."""
        desc = "A description for hash test"
        entry = {"name": "Test", "description": desc, "category": "patterns",
                 "source": "manual"}
        result = _build_db_entry(entry, "test_id", "2026-01-01T00:00:00Z",
                                 project_root="/proj")
        assert result["source_hash"] == sh_fn(desc)

    def test_falls_back_to_project_root(self):
        """When source_project is not in entry, should fall back to project_root."""
        entry = {"name": "Test", "description": "Desc", "category": "patterns",
                 "source": "manual"}
        result = _build_db_entry(entry, "test_id", "2026-01-01T00:00:00Z",
                                 project_root="/my/project")
        assert result["source_project"] == "/my/project"

    def test_preserves_explicit_source_project(self):
        """When source_project is in entry, it should be used."""
        entry = {"name": "Test", "description": "Desc", "category": "patterns",
                 "source": "manual", "source_project": "/explicit/project"}
        result = _build_db_entry(entry, "test_id", "2026-01-01T00:00:00Z",
                                 project_root="/fallback")
        assert result["source_project"] == "/explicit/project"


# ---------------------------------------------------------------------------
# Test: CLI delete action (feature 047)
# ---------------------------------------------------------------------------


class TestCLIDelete:
    def test_cli_delete_success(self, global_store, tmp_path):
        """AC-8: --action delete --entry-id deletes and prints confirmation."""
        # First create an entry to delete
        db = MemoryDatabase(os.path.join(global_store, "memory.db"))
        entry = {
            "id": "del-me",
            "name": "Delete Test",
            "description": "To be deleted",
            "category": "patterns",
            "source": "manual",
            "keywords": "[]",
            "source_project": "/tmp",
            "source_hash": "0000",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        db.upsert_entry(entry)
        assert db.get_entry("del-me") is not None
        db.close()

        with patch("semantic_memory.writer.create_provider", return_value=None), \
             patch("semantic_memory.writer.read_config", return_value={}):
            exit_code, stdout, stderr = _run_main([
                "--action", "delete",
                "--entry-id", "del-me",
                "--global-store", global_store,
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 0
        assert "Deleted memory entry: del-me" in stdout

        # Verify entry is gone from DB
        db = MemoryDatabase(os.path.join(global_store, "memory.db"))
        assert db.get_entry("del-me") is None
        db.close()

    def test_cli_delete_missing_entry_id(self):
        """AC-9: --action delete without --entry-id exits code 2."""
        exit_code, stdout, stderr = _run_main([
            "--action", "delete",
            "--global-store", "/tmp/fake",
        ])
        assert exit_code == 2
        assert "entry-id" in stderr.lower() or "required" in stderr.lower()

    def test_cli_delete_not_found_exits_1(self, global_store, tmp_path):
        """Delete of nonexistent entry exits with code 1."""
        with patch("semantic_memory.writer.create_provider", return_value=None), \
             patch("semantic_memory.writer.read_config", return_value={}):
            exit_code, stdout, stderr = _run_main([
                "--action", "delete",
                "--entry-id", "nonexistent-id",
                "--global-store", global_store,
                "--project-root", str(tmp_path),
            ])

        assert exit_code == 1
        assert "not found" in stderr.lower()
