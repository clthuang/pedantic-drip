"""Consolidated Phase 1 foundation tests for the semantic memory system.

Covers all Phase 1 modules in a single file:
  - content_hash (semantic_memory.__init__)
  - config reader (semantic_memory.config)
  - database CRUD (semantic_memory.database)
  - FTS5 full-text search
  - embedding BLOB round-trips
  - schema migration (version 0 -> 1)
"""
from __future__ import annotations

import json
import os
import struct
import sys

# Allow imports from hooks/lib/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import numpy as np
import pytest

from semantic_memory import content_hash
from semantic_memory.config import read_config
from semantic_memory.database import MemoryDatabase


# =========================================================================
# Helpers
# =========================================================================


def _make_entry(**overrides) -> dict:
    """Build a minimal valid entry dict, with optional overrides."""
    base = {
        "id": "abc123",
        "name": "Test pattern",
        "description": "A test description",
        "category": "patterns",
        "source": "manual",
        "keywords": json.dumps(["test", "example"]),
        "source_project": "/tmp/project",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def _make_embedding(dims: int = 768) -> bytes:
    """Create a dummy float32 embedding blob."""
    return np.array([0.1] * dims, dtype=np.float32).tobytes()


# =========================================================================
# 1. content_hash tests
# =========================================================================


class TestContentHash:
    """Tests for content_hash: SHA-256 of normalised text, first 16 hex chars."""

    def test_known_input_produces_16_char_hex(self):
        result = content_hash("hello world")
        assert result == "b94d27b9934d3e08"
        assert len(result) == 16

    def test_output_is_hex(self):
        result = content_hash("abc")
        assert all(c in "0123456789abcdef" for c in result)
        assert result == "ba7816bf8f01cfea"

    def test_normalises_whitespace(self):
        """Multiple spaces, tabs, newlines all collapse to single space."""
        assert content_hash("hello   world") == "b94d27b9934d3e08"
        assert content_hash("hello\t\n world") == "b94d27b9934d3e08"
        assert content_hash("hello\n\nworld") == "b94d27b9934d3e08"

    def test_normalises_case(self):
        """Input is lowercased before hashing."""
        assert content_hash("Hello World") == "b94d27b9934d3e08"
        assert content_hash("HELLO WORLD") == "b94d27b9934d3e08"

    def test_strips_leading_trailing_whitespace(self):
        assert content_hash("  Hello  World  ") == "b94d27b9934d3e08"

    def test_empty_string(self):
        result = content_hash("")
        assert result == "e3b0c44298fc1c14"
        assert len(result) == 16

    def test_whitespace_only_is_same_as_empty(self):
        assert content_hash("   ") == content_hash("")

    def test_deterministic(self):
        """Same input always produces same hash."""
        assert content_hash("stable") == content_hash("stable")


# =========================================================================
# 2. config reader tests
# =========================================================================


class TestConfigReaderDefaults:
    """When config file is missing, return all defaults."""

    def test_missing_file_returns_defaults(self, tmp_path):
        result = read_config(str(tmp_path))
        assert result["memory_semantic_enabled"] is True
        assert result["memory_vector_weight"] == 0.5
        assert result["memory_keyword_weight"] == 0.2
        assert result["memory_prominence_weight"] == 0.3
        assert result["memory_embedding_provider"] == "gemini"
        assert result["memory_embedding_model"] == "gemini-embedding-001"
        assert result["memory_keyword_provider"] == "auto"
        assert result["memory_injection_limit"] == 20


class TestConfigReaderTypes:
    """Type coercion for parsed values."""

    def _write_config(self, tmp_path, content: str):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "pd.local.md").write_text(content)

    def test_bool_true(self, tmp_path):
        self._write_config(tmp_path, "memory_semantic_enabled: true\n")
        result = read_config(str(tmp_path))
        assert result["memory_semantic_enabled"] is True

    def test_bool_false(self, tmp_path):
        self._write_config(tmp_path, "memory_semantic_enabled: false\n")
        result = read_config(str(tmp_path))
        assert result["memory_semantic_enabled"] is False

    def test_int_value(self, tmp_path):
        self._write_config(tmp_path, "memory_injection_limit: 30\n")
        result = read_config(str(tmp_path))
        assert result["memory_injection_limit"] == 30
        assert isinstance(result["memory_injection_limit"], int)

    def test_float_value(self, tmp_path):
        self._write_config(tmp_path, "memory_vector_weight: 0.7\n")
        result = read_config(str(tmp_path))
        assert result["memory_vector_weight"] == 0.7
        assert isinstance(result["memory_vector_weight"], float)

    def test_string_value(self, tmp_path):
        self._write_config(tmp_path, "memory_embedding_provider: voyage\n")
        result = read_config(str(tmp_path))
        assert result["memory_embedding_provider"] == "voyage"


class TestConfigReaderSpaceStripping:
    """tr -d ' ' semantics: all spaces stripped from values."""

    def _write_config(self, tmp_path, content: str):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "pd.local.md").write_text(content)

    def test_spaces_stripped_from_string(self, tmp_path):
        self._write_config(tmp_path, "memory_embedding_model: gemini embedding 001\n")
        result = read_config(str(tmp_path))
        assert result["memory_embedding_model"] == "geminiembedding001"

    def test_leading_trailing_spaces_on_bool(self, tmp_path):
        self._write_config(tmp_path, "memory_semantic_enabled:  true  \n")
        result = read_config(str(tmp_path))
        assert result["memory_semantic_enabled"] is True


class TestConfigReaderEdgeCases:
    """Edge cases: missing file, empty values, null, first-match-wins."""

    def _write_config(self, tmp_path, content: str):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "pd.local.md").write_text(content)

    def test_empty_value_falls_back_to_default(self, tmp_path):
        self._write_config(tmp_path, "memory_injection_limit:\n")
        result = read_config(str(tmp_path))
        assert result["memory_injection_limit"] == 20  # default

    def test_null_value_falls_back_to_default(self, tmp_path):
        self._write_config(tmp_path, "memory_injection_limit: null\n")
        result = read_config(str(tmp_path))
        assert result["memory_injection_limit"] == 20  # default

    def test_first_match_wins(self, tmp_path):
        self._write_config(
            tmp_path,
            "memory_injection_limit: 10\nmemory_injection_limit: 99\n",
        )
        result = read_config(str(tmp_path))
        assert result["memory_injection_limit"] == 10


# =========================================================================
# 3. database CRUD tests
# =========================================================================


@pytest.fixture
def db():
    """Provide an in-memory MemoryDatabase, closed after test."""
    database = MemoryDatabase(":memory:")
    yield database
    database.close()


class TestDatabaseCRUD:
    """Insert, get, count, upsert round-trips on in-memory DB."""

    def test_insert_and_get(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        result = db.get_entry("abc123")
        assert result is not None
        assert result["id"] == "abc123"
        assert result["name"] == "Test pattern"
        assert result["category"] == "patterns"
        assert result["source"] == "manual"

    def test_count_entries(self, db: MemoryDatabase):
        assert db.count_entries() == 0
        db.upsert_entry(_make_entry(id="a"))
        assert db.count_entries() == 1
        db.upsert_entry(_make_entry(id="b"))
        assert db.count_entries() == 2

    def test_get_missing_returns_none(self, db: MemoryDatabase):
        assert db.get_entry("nonexistent") is None

    def test_upsert_increments_observation_count(self, db: MemoryDatabase):
        entry = _make_entry()
        db.upsert_entry(entry)
        db.upsert_entry(entry)
        db.upsert_entry(entry)
        result = db.get_entry("abc123")
        assert result["observation_count"] == 3

    def test_upsert_does_not_create_duplicates(self, db: MemoryDatabase):
        entry = _make_entry()
        db.upsert_entry(entry)
        db.upsert_entry(entry)
        assert db.count_entries() == 1

    def test_upsert_updates_updated_at(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(updated_at="2026-01-01T00:00:00Z"))
        db.upsert_entry(_make_entry(updated_at="2026-06-15T12:00:00Z"))
        result = db.get_entry("abc123")
        assert result["updated_at"] == "2026-06-15T12:00:00Z"

    def test_upsert_preserves_created_at(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(created_at="2026-01-01T00:00:00Z"))
        db.upsert_entry(_make_entry(created_at="2026-12-31T00:00:00Z"))
        result = db.get_entry("abc123")
        assert result["created_at"] == "2026-01-01T00:00:00Z"

    def test_get_all_entries(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(id="a", name="first"))
        db.upsert_entry(_make_entry(id="b", name="second"))
        entries = db.get_all_entries()
        assert len(entries) == 2
        assert all(isinstance(e, dict) for e in entries)


class TestDatabaseMetadata:
    """Metadata key-value storage round-trips."""

    def test_get_missing_returns_none(self, db: MemoryDatabase):
        assert db.get_metadata("nonexistent") is None

    def test_set_and_get(self, db: MemoryDatabase):
        db.set_metadata("foo", "bar")
        assert db.get_metadata("foo") == "bar"

    def test_set_overwrites(self, db: MemoryDatabase):
        db.set_metadata("foo", "bar")
        db.set_metadata("foo", "baz")
        assert db.get_metadata("foo") == "baz"


# =========================================================================
# 4. FTS5 search tests
# =========================================================================


class TestFTS5Search:
    """Insert entries with keywords, verify FTS5 search finds them."""

    def test_fts5_search_by_keyword(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(keywords=json.dumps(["resilience", "retry"])))
        results = db.fts5_search("resilience")
        assert len(results) >= 1
        ids = [r[0] for r in results]
        assert "abc123" in ids

    def test_fts5_search_by_name(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(name="Error handling pattern"))
        results = db.fts5_search("error")
        assert len(results) >= 1

    def test_fts5_search_by_description(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(description="Retry with exponential backoff"))
        results = db.fts5_search("exponential")
        assert len(results) >= 1

    def test_fts5_search_returns_id_and_positive_score(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        results = db.fts5_search("test")
        assert len(results) >= 1
        entry_id, score = results[0]
        assert isinstance(entry_id, str)
        assert isinstance(score, float)
        assert score > 0

    def test_fts5_search_no_match_returns_empty(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        results = db.fts5_search("xyznonsensequery")
        assert results == []

    def test_fts5_search_respects_limit(self, db: MemoryDatabase):
        for i in range(10):
            db.upsert_entry(
                _make_entry(id=f"id_{i}", name=f"Pattern {i}", description="common")
            )
        results = db.fts5_search("pattern", limit=3)
        assert len(results) == 3

    def test_fts5_table_populated_by_trigger(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        cur = db._conn.execute("SELECT COUNT(*) FROM entries_fts")
        assert cur.fetchone()[0] == 1


# =========================================================================
# 5. Embedding BLOB round-trip tests
# =========================================================================


class TestEmbeddingBlob:
    """Store float32 tobytes, read back, verify array equality."""

    def test_store_and_retrieve_embedding(self, db: MemoryDatabase):
        vec = np.array([0.1, 0.2, 0.3, 0.4, 0.5], dtype=np.float32)
        emb_bytes = vec.tobytes()
        db.upsert_entry(_make_entry(embedding=emb_bytes))
        result = db.get_entry("abc123")
        recovered = np.frombuffer(result["embedding"], dtype=np.float32)
        np.testing.assert_array_equal(recovered, vec)

    def test_full_768_dim_round_trip(self, db: MemoryDatabase):
        vec = np.random.rand(768).astype(np.float32)
        emb_bytes = vec.tobytes()
        db.upsert_entry(_make_entry(embedding=emb_bytes))
        result = db.get_entry("abc123")
        recovered = np.frombuffer(result["embedding"], dtype=np.float32)
        np.testing.assert_array_almost_equal(recovered, vec)

    def test_update_embedding_method(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        vec = np.array([0.5] * 768, dtype=np.float32)
        db.update_embedding("abc123", vec.tobytes())
        result = db.get_entry("abc123")
        recovered = np.frombuffer(result["embedding"], dtype=np.float32)
        np.testing.assert_array_equal(recovered, vec)

    def test_get_all_embeddings_matrix(self, db: MemoryDatabase):
        for i in range(3):
            vec = np.array([float(i)] * 768, dtype=np.float32)
            db.upsert_entry(_make_entry(id=f"id_{i}", embedding=vec.tobytes()))
        result = db.get_all_embeddings()
        assert result is not None
        ids, matrix = result
        assert len(ids) == 3
        assert matrix.shape == (3, 768)
        assert matrix.dtype == np.float32

    def test_null_embedding_excluded_from_get_all(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(id="no_emb"))
        emb = _make_embedding()
        db.upsert_entry(_make_entry(id="has_emb", embedding=emb))
        result = db.get_all_embeddings()
        assert result is not None
        ids, matrix = result
        assert ids == ["has_emb"]
        assert matrix.shape == (1, 768)

    def test_corrupted_blob_skipped(self, db: MemoryDatabase):
        good = _make_embedding()
        db.upsert_entry(_make_entry(id="good", embedding=good))
        db.upsert_entry(_make_entry(id="bad", embedding=b"\x00" * 10))
        result = db.get_all_embeddings()
        assert result is not None
        ids, matrix = result
        assert ids == ["good"]


# =========================================================================
# 6. Migration tests
# =========================================================================


class TestMigration:
    """Version 0 -> 1 creates all expected tables."""

    def test_schema_version_is_1_after_init(self, db: MemoryDatabase):
        assert db.get_schema_version() == 1

    def test_entries_table_exists(self, db: MemoryDatabase):
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entries'"
        )
        assert cur.fetchone() is not None

    def test_metadata_table_exists(self, db: MemoryDatabase):
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_metadata'"
        )
        assert cur.fetchone() is not None

    def test_fts5_table_exists(self, db: MemoryDatabase):
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entries_fts'"
        )
        assert cur.fetchone() is not None

    def test_entries_has_16_columns(self, db: MemoryDatabase):
        cur = db._conn.execute("PRAGMA table_info(entries)")
        columns = cur.fetchall()
        assert len(columns) == 16

    def test_entries_column_names(self, db: MemoryDatabase):
        cur = db._conn.execute("PRAGMA table_info(entries)")
        col_names = [row[1] for row in cur.fetchall()]
        expected = [
            "id", "name", "description", "reasoning", "category",
            "keywords", "source", "source_project", "references",
            "observation_count", "confidence", "recall_count",
            "last_recalled_at", "embedding", "created_at", "updated_at",
        ]
        assert col_names == expected

    def test_fts5_triggers_created(self, db: MemoryDatabase):
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
        )
        trigger_names = [row[0] for row in cur.fetchall()]
        assert "entries_ai" in trigger_names
        assert "entries_ad" in trigger_names
        assert "entries_au" in trigger_names

    def test_reopen_is_idempotent(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        db1 = MemoryDatabase(db_path)
        assert db1.get_schema_version() == 1
        db1.close()
        db2 = MemoryDatabase(db_path)
        assert db2.get_schema_version() == 1
        db2.close()
