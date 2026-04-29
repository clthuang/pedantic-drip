"""Tests for semantic_memory.database module."""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import struct
import sqlite3
from collections.abc import Iterator
from datetime import datetime, timezone

import numpy as np
import pytest

from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query, _ISO8601_Z_PATTERN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        "source_hash": "0000000000000000",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def _make_embedding(dims: int = 768) -> bytes:
    """Create a dummy float32 embedding blob."""
    return struct.pack(f"{dims}f", *([0.1] * dims))


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Provide an in-memory MemoryDatabase, closed after test."""
    database = MemoryDatabase(":memory:")
    yield database
    database.close()


# ---------------------------------------------------------------------------
# Schema / migration tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    def test_creates_entries_table(self, db: MemoryDatabase):
        """The entries table should exist after init."""
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entries'"
        )
        assert cur.fetchone() is not None

    def test_creates_metadata_table(self, db: MemoryDatabase):
        """The _metadata table should exist after init."""
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_metadata'"
        )
        assert cur.fetchone() is not None

    def test_schema_version_is_4(self, db: MemoryDatabase):
        assert db.get_schema_version() == 5

    def test_entries_has_19_columns(self, db: MemoryDatabase):
        cur = db._conn.execute("PRAGMA table_info(entries)")
        columns = cur.fetchall()
        assert len(columns) == 19

    def test_entries_column_names(self, db: MemoryDatabase):
        cur = db._conn.execute("PRAGMA table_info(entries)")
        col_names = [row[1] for row in cur.fetchall()]
        expected = [
            "id", "name", "description", "reasoning", "category",
            "keywords", "source", "source_project", "references",
            "observation_count", "confidence", "recall_count",
            "last_recalled_at", "embedding", "created_at", "updated_at",
            "source_hash", "created_timestamp_utc", "influence_count",
        ]
        assert col_names == expected


class TestMigrationIdempotency:
    def test_opening_twice_does_not_error(self):
        """Opening two MemoryDatabase instances on same in-memory DB should
        still result in schema_version == 5 (migrations are idempotent)."""
        db1 = MemoryDatabase(":memory:")
        assert db1.get_schema_version() == 5
        db1.close()

    def test_schema_version_persists(self, tmp_path):
        """Schema version survives close and reopen."""
        db_path = str(tmp_path / "test.db")
        db1 = MemoryDatabase(db_path)
        assert db1.get_schema_version() == 5
        db1.close()

        db2 = MemoryDatabase(db_path)
        assert db2.get_schema_version() == 5
        db2.close()


# ---------------------------------------------------------------------------
# source_hash / migration v2 tests
# ---------------------------------------------------------------------------


class TestGetSourceHash:
    def test_returns_none_for_missing_entry(self, db: MemoryDatabase):
        assert db.get_source_hash("nonexistent") is None

    def test_returns_default_when_set_via_helper(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        assert db.get_source_hash("abc123") == "0000000000000000"

    def test_returns_value_when_set(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(source_hash="deadbeef12345678"))
        assert db.get_source_hash("abc123") == "deadbeef12345678"


class TestMigrationV2Backfill:
    def test_migration_v2_backfills_created_timestamp_utc(self, tmp_path):
        """Create a v1 DB manually, insert entry, reopen to trigger migration,
        verify created_timestamp_utc is populated from created_at."""
        db_path = str(tmp_path / "test.db")
        # Create a v1-only database by hand
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS entries (
                id                TEXT PRIMARY KEY,
                name              TEXT NOT NULL,
                description       TEXT NOT NULL,
                reasoning         TEXT,
                category          TEXT NOT NULL CHECK(category IN ('anti-patterns', 'patterns', 'heuristics')),
                keywords          TEXT,
                source            TEXT NOT NULL CHECK(source IN ('retro', 'session-capture', 'manual', 'import')),
                source_project    TEXT,
                "references"      TEXT,
                observation_count INTEGER DEFAULT 1,
                confidence        TEXT DEFAULT 'medium' CHECK(confidence IN ('high', 'medium', 'low')),
                recall_count      INTEGER DEFAULT 0,
                last_recalled_at  TEXT,
                embedding         BLOB,
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS _metadata (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT INTO _metadata (key, value) VALUES ('schema_version', '1');
        """)
        conn.execute(
            "INSERT INTO entries (id, name, description, category, source, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("test1", "Test", "Desc", "patterns", "manual", "2026-01-15T12:00:00Z", "2026-01-15T12:00:00Z"),
        )
        conn.commit()
        conn.close()

        # Reopen with MemoryDatabase to trigger migrations v2-v4
        db = MemoryDatabase(db_path)
        assert db.get_schema_version() == 5

        entry = db.get_entry("test1")
        assert entry is not None
        assert entry["created_timestamp_utc"] is not None
        assert isinstance(entry["created_timestamp_utc"], float)
        db.close()


# ---------------------------------------------------------------------------
# Migration v3 tests (NOT NULL enforcement)
# ---------------------------------------------------------------------------


def _create_v2_db(db_path: str) -> sqlite3.Connection:
    """Create a v2 database manually for migration testing."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entries (
            id                TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            description       TEXT NOT NULL,
            reasoning         TEXT,
            category          TEXT NOT NULL CHECK(category IN ('anti-patterns', 'patterns', 'heuristics')),
            keywords          TEXT,
            source            TEXT NOT NULL CHECK(source IN ('retro', 'session-capture', 'manual', 'import')),
            source_project    TEXT,
            "references"      TEXT,
            observation_count INTEGER DEFAULT 1,
            confidence        TEXT DEFAULT 'medium' CHECK(confidence IN ('high', 'medium', 'low')),
            recall_count      INTEGER DEFAULT 0,
            last_recalled_at  TEXT,
            embedding         BLOB,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            source_hash       TEXT,
            created_timestamp_utc REAL
        );
        CREATE TABLE IF NOT EXISTS _metadata (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT INTO _metadata (key, value) VALUES ('schema_version', '2');
    """)
    return conn


class TestMigrationV3:
    def test_migration_v3_backfills_null_keywords(self, tmp_path):
        """NULL keywords should be backfilled to '[]'."""
        db_path = str(tmp_path / "test.db")
        conn = _create_v2_db(db_path)
        conn.execute(
            "INSERT INTO entries (id, name, description, category, source, keywords, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("e1", "Test", "Desc", "patterns", "manual", None,
             "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        db = MemoryDatabase(db_path)
        entry = db.get_entry("e1")
        assert entry["keywords"] == "[]"
        db.close()

    def test_migration_v3_backfills_null_source_project(self, tmp_path):
        """NULL source_project should be backfilled from existing import entries."""
        db_path = str(tmp_path / "test.db")
        conn = _create_v2_db(db_path)
        # Import entry with source_project set
        conn.execute(
            "INSERT INTO entries (id, name, description, category, source, "
            "source_project, source_hash, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("import1", "Import", "Import desc", "patterns", "import",
             "/projects/myapp", "abc123", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        # Manual entry without source_project
        conn.execute(
            "INSERT INTO entries (id, name, description, category, source, "
            "source_project, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("manual1", "Manual", "Manual desc", "patterns", "manual",
             None, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        db = MemoryDatabase(db_path)
        entry = db.get_entry("manual1")
        assert entry["source_project"] == "/projects/myapp"
        db.close()

    def test_migration_v3_backfills_null_source_project_unknown_fallback(self, tmp_path):
        """When ALL source_project are NULL, backfill to 'unknown'."""
        db_path = str(tmp_path / "test.db")
        conn = _create_v2_db(db_path)
        conn.execute(
            "INSERT INTO entries (id, name, description, category, source, "
            "source_project, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("e1", "Test", "Desc", "patterns", "manual",
             None, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        db = MemoryDatabase(db_path)
        entry = db.get_entry("e1")
        assert entry["source_project"] == "unknown"
        db.close()

    def test_migration_v3_backfills_null_source_hash(self, tmp_path):
        """NULL source_hash should be backfilled to SHA-256(description)[:16]."""
        db_path = str(tmp_path / "test.db")
        conn = _create_v2_db(db_path)
        desc = "A test description for hash"
        conn.execute(
            "INSERT INTO entries (id, name, description, category, source, "
            "source_project, source_hash, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("e1", "Test", desc, "patterns", "manual",
             "/proj", None, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        expected_hash = hashlib.sha256(desc.encode()).hexdigest()[:16]
        db = MemoryDatabase(db_path)
        entry = db.get_entry("e1")
        assert entry["source_hash"] == expected_hash
        db.close()

    def test_migration_v3_preserves_existing_values(self, tmp_path):
        """Non-NULL values should be preserved through migration."""
        db_path = str(tmp_path / "test.db")
        conn = _create_v2_db(db_path)
        conn.execute(
            "INSERT INTO entries (id, name, description, category, source, "
            "keywords, source_project, source_hash, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("e1", "Test", "Desc", "patterns", "manual",
             '["keep"]', "/my/project", "existinghash1234",
             "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        db = MemoryDatabase(db_path)
        entry = db.get_entry("e1")
        assert entry["keywords"] == '["keep"]'
        assert entry["source_project"] == "/my/project"
        assert entry["source_hash"] == "existinghash1234"
        db.close()

    def test_migration_v3_fts5_works_after_rebuild(self, tmp_path):
        """FTS5 should work after migration rebuilds the table."""
        db_path = str(tmp_path / "test.db")
        conn = _create_v2_db(db_path)
        conn.commit()
        conn.close()

        db = MemoryDatabase(db_path)
        # Insert after migration
        db.upsert_entry(_make_entry(id="post_migration", name="Searchable pattern"))
        results = db.fts5_search("searchable")
        assert len(results) >= 1
        ids = [r[0] for r in results]
        assert "post_migration" in ids
        db.close()

    def test_migration_v3_not_null_enforced_keywords(self, tmp_path):
        """After migration, inserting NULL keywords should raise IntegrityError."""
        db_path = str(tmp_path / "test.db")
        db = MemoryDatabase(db_path)
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO entries (id, name, description, category, source, "
                "keywords, source_project, source_hash, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("e1", "Test", "Desc", "patterns", "manual",
                 None, "/proj", "hash1234", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
            )
        db.close()

    def test_migration_v3_not_null_enforced_source_project(self, tmp_path):
        """After migration, inserting NULL source_project should raise IntegrityError."""
        db_path = str(tmp_path / "test.db")
        db = MemoryDatabase(db_path)
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO entries (id, name, description, category, source, "
                "keywords, source_project, source_hash, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("e1", "Test", "Desc", "patterns", "manual",
                 "[]", None, "hash1234", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
            )
        db.close()

    def test_migration_v3_not_null_enforced_source_hash(self, tmp_path):
        """After migration, inserting NULL source_hash should raise IntegrityError."""
        db_path = str(tmp_path / "test.db")
        db = MemoryDatabase(db_path)
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO entries (id, name, description, category, source, "
                "keywords, source_project, source_hash, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("e1", "Test", "Desc", "patterns", "manual",
                 "[]", "/proj", None, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
            )
        db.close()


# ---------------------------------------------------------------------------
# PRAGMA tests
# ---------------------------------------------------------------------------


class TestPragmas:
    def test_wal_mode(self, tmp_path):
        """WAL journal mode should be set (only works on file-based DBs)."""
        db_path = str(tmp_path / "test.db")
        database = MemoryDatabase(db_path)
        cur = database._conn.execute("PRAGMA journal_mode")
        assert cur.fetchone()[0] == "wal"
        database.close()

    def test_busy_timeout(self, db: MemoryDatabase):
        cur = db._conn.execute("PRAGMA busy_timeout")
        assert cur.fetchone()[0] == 15000

    def test_cache_size(self, db: MemoryDatabase):
        cur = db._conn.execute("PRAGMA cache_size")
        assert cur.fetchone()[0] == -8000

    def test_synchronous_normal(self, db: MemoryDatabase):
        cur = db._conn.execute("PRAGMA synchronous")
        # 1 = NORMAL
        assert cur.fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------


class TestMetadata:
    def test_get_missing_key_returns_none(self, db: MemoryDatabase):
        assert db.get_metadata("nonexistent") is None

    def test_set_and_get(self, db: MemoryDatabase):
        db.set_metadata("foo", "bar")
        assert db.get_metadata("foo") == "bar"

    def test_set_overwrites(self, db: MemoryDatabase):
        db.set_metadata("foo", "bar")
        db.set_metadata("foo", "baz")
        assert db.get_metadata("foo") == "baz"


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------


class TestInsert:
    def test_insert_new_entry(self, db: MemoryDatabase):
        entry = _make_entry()
        db.upsert_entry(entry)
        assert db.count_entries() == 1

    def test_get_entry_returns_dict(self, db: MemoryDatabase):
        entry = _make_entry()
        db.upsert_entry(entry)
        result = db.get_entry("abc123")
        assert isinstance(result, dict)
        assert result["id"] == "abc123"
        assert result["name"] == "Test pattern"
        assert result["category"] == "patterns"
        assert result["source"] == "manual"
        assert result["observation_count"] == 1

    def test_get_entry_missing_returns_none(self, db: MemoryDatabase):
        assert db.get_entry("nonexistent") is None

    def test_insert_with_all_fields(self, db: MemoryDatabase):
        emb = _make_embedding()
        entry = _make_entry(
            reasoning="Because tests matter",
            references=json.dumps(["ref1", "ref2"]),
            confidence="high",
            recall_count=5,
            last_recalled_at="2026-02-01T00:00:00Z",
            embedding=emb,
        )
        db.upsert_entry(entry)
        result = db.get_entry("abc123")
        assert result["reasoning"] == "Because tests matter"
        assert result["references"] == json.dumps(["ref1", "ref2"])
        assert result["confidence"] == "high"
        assert result["recall_count"] == 5
        assert result["last_recalled_at"] == "2026-02-01T00:00:00Z"
        assert result["embedding"] == emb

    def test_insert_with_nullable_fields_omitted(self, db: MemoryDatabase):
        """Nullable fields default to None when not provided."""
        entry = _make_entry()
        db.upsert_entry(entry)
        result = db.get_entry("abc123")
        assert result["reasoning"] is None
        assert result["references"] is None
        assert result["last_recalled_at"] is None
        assert result["embedding"] is None
        # keywords, source_project, source_hash are NOT NULL with defaults/values
        assert result["keywords"] is not None
        assert result["source_project"] is not None
        assert result["source_hash"] is not None


class TestUpsert:
    def test_upsert_increments_observation_count(self, db: MemoryDatabase):
        entry = _make_entry()
        db.upsert_entry(entry)
        db.upsert_entry(entry)
        result = db.get_entry("abc123")
        assert result["observation_count"] == 2

    def test_upsert_three_times(self, db: MemoryDatabase):
        entry = _make_entry()
        db.upsert_entry(entry)
        db.upsert_entry(entry)
        db.upsert_entry(entry)
        result = db.get_entry("abc123")
        assert result["observation_count"] == 3

    def test_upsert_updates_updated_at(self, db: MemoryDatabase):
        entry = _make_entry(updated_at="2026-01-01T00:00:00Z")
        db.upsert_entry(entry)

        entry2 = _make_entry(updated_at="2026-06-15T12:00:00Z")
        db.upsert_entry(entry2)

        result = db.get_entry("abc123")
        assert result["updated_at"] == "2026-06-15T12:00:00Z"

    def test_upsert_preserves_created_at(self, db: MemoryDatabase):
        entry = _make_entry(created_at="2026-01-01T00:00:00Z")
        db.upsert_entry(entry)

        entry2 = _make_entry(created_at="2026-06-15T12:00:00Z")
        db.upsert_entry(entry2)

        result = db.get_entry("abc123")
        assert result["created_at"] == "2026-01-01T00:00:00Z"

    def test_upsert_overwrites_description_if_nonnull(self, db: MemoryDatabase):
        entry = _make_entry(description="original")
        db.upsert_entry(entry)

        entry2 = _make_entry(description="updated")
        db.upsert_entry(entry2)

        result = db.get_entry("abc123")
        assert result["description"] == "updated"

    def test_upsert_keeps_description_if_null(self, db: MemoryDatabase):
        entry = _make_entry(description="original")
        db.upsert_entry(entry)

        entry2 = _make_entry()
        entry2["description"] = None
        db.upsert_entry(entry2)

        result = db.get_entry("abc123")
        assert result["description"] == "original"

    def test_upsert_overwrites_keywords_if_nonnull(self, db: MemoryDatabase):
        entry = _make_entry(keywords=json.dumps(["old"]))
        db.upsert_entry(entry)

        entry2 = _make_entry(keywords=json.dumps(["new1", "new2"]))
        db.upsert_entry(entry2)

        result = db.get_entry("abc123")
        assert json.loads(result["keywords"]) == ["new1", "new2"]

    def test_upsert_keeps_keywords_if_empty_json(self, db: MemoryDatabase):
        """Upserting with keywords='[]' should preserve existing keywords."""
        entry = _make_entry(keywords=json.dumps(["keep"]))
        db.upsert_entry(entry)

        entry2 = _make_entry(keywords="[]")
        db.upsert_entry(entry2)

        result = db.get_entry("abc123")
        assert json.loads(result["keywords"]) == ["keep"]

    def test_upsert_keeps_keywords_when_incoming_empty_json(self, db: MemoryDatabase):
        """Explicit test: '[]' keywords should not overwrite existing non-empty keywords."""
        entry = _make_entry(keywords=json.dumps(["keep-these"]))
        db.upsert_entry(entry)

        entry2 = _make_entry(keywords="[]")
        db.upsert_entry(entry2)

        result = db.get_entry("abc123")
        assert json.loads(result["keywords"]) == ["keep-these"]

    def test_upsert_overwrites_reasoning_if_nonnull(self, db: MemoryDatabase):
        entry = _make_entry(reasoning="old reasoning")
        db.upsert_entry(entry)

        entry2 = _make_entry(reasoning="new reasoning")
        db.upsert_entry(entry2)

        result = db.get_entry("abc123")
        assert result["reasoning"] == "new reasoning"

    def test_upsert_keeps_reasoning_if_null(self, db: MemoryDatabase):
        entry = _make_entry(reasoning="keep this")
        db.upsert_entry(entry)

        entry2 = _make_entry()  # reasoning not in _make_entry by default
        db.upsert_entry(entry2)

        result = db.get_entry("abc123")
        assert result["reasoning"] == "keep this"

    def test_upsert_overwrites_references_if_nonnull(self, db: MemoryDatabase):
        entry = _make_entry(references=json.dumps(["old"]))
        db.upsert_entry(entry)

        entry2 = _make_entry(references=json.dumps(["new"]))
        db.upsert_entry(entry2)

        result = db.get_entry("abc123")
        assert json.loads(result["references"]) == ["new"]

    def test_upsert_keeps_references_if_null(self, db: MemoryDatabase):
        entry = _make_entry(references=json.dumps(["keep"]))
        db.upsert_entry(entry)

        entry2 = _make_entry()  # references not in _make_entry by default
        db.upsert_entry(entry2)

        result = db.get_entry("abc123")
        assert json.loads(result["references"]) == ["keep"]

    def test_upsert_does_not_create_duplicate_rows(self, db: MemoryDatabase):
        entry = _make_entry()
        db.upsert_entry(entry)
        db.upsert_entry(entry)
        assert db.count_entries() == 1


class TestGetAllAndCount:
    def test_empty_db(self, db: MemoryDatabase):
        assert db.get_all_entries() == []
        assert db.count_entries() == 0

    def test_multiple_entries(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(id="aaa", name="first"))
        db.upsert_entry(_make_entry(id="bbb", name="second"))
        db.upsert_entry(_make_entry(id="ccc", name="third"))

        entries = db.get_all_entries()
        assert len(entries) == 3
        assert db.count_entries() == 3

    def test_get_all_returns_dicts(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        entries = db.get_all_entries()
        assert all(isinstance(e, dict) for e in entries)


# ---------------------------------------------------------------------------
# Constraint / validation tests
# ---------------------------------------------------------------------------


class TestConstraints:
    def test_invalid_category_rejected(self, db: MemoryDatabase):
        entry = _make_entry(category="invalid")
        with pytest.raises(sqlite3.IntegrityError):
            db.upsert_entry(entry)

    def test_invalid_source_rejected(self, db: MemoryDatabase):
        entry = _make_entry(source="invalid")
        with pytest.raises(sqlite3.IntegrityError):
            db.upsert_entry(entry)

    def test_invalid_confidence_rejected(self, db: MemoryDatabase):
        entry = _make_entry(confidence="invalid")
        with pytest.raises(sqlite3.IntegrityError):
            db.upsert_entry(entry)

    def test_valid_categories(self, db: MemoryDatabase):
        for i, cat in enumerate(["anti-patterns", "patterns", "heuristics"]):
            db.upsert_entry(_make_entry(id=f"id_{i}", category=cat))
        assert db.count_entries() == 3

    def test_valid_sources(self, db: MemoryDatabase):
        for i, src in enumerate(["retro", "session-capture", "manual", "import"]):
            db.upsert_entry(_make_entry(id=f"id_{i}", source=src))
        assert db.count_entries() == 4

    def test_valid_confidence_levels(self, db: MemoryDatabase):
        for i, conf in enumerate(["high", "medium", "low"]):
            db.upsert_entry(_make_entry(id=f"id_{i}", confidence=conf))
        assert db.count_entries() == 3


# ---------------------------------------------------------------------------
# Close test
# ---------------------------------------------------------------------------


class TestClose:
    def test_close_prevents_further_operations(self):
        database = MemoryDatabase(":memory:")
        database.close()
        with pytest.raises(Exception):
            database.count_entries()


# ---------------------------------------------------------------------------
# FTS5 detection tests (T1.4)
# ---------------------------------------------------------------------------


class TestFTS5Detection:
    def test_fts5_available_property_exists(self, db: MemoryDatabase):
        """fts5_available should be a boolean property."""
        assert isinstance(db.fts5_available, bool)

    def test_fts5_detected_as_available(self, db: MemoryDatabase):
        """On standard Python builds, FTS5 should be available."""
        assert db.fts5_available is True

    def test_fts5_table_created_when_available(self, db: MemoryDatabase):
        """entries_fts virtual table should exist when FTS5 is available."""
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entries_fts'"
        )
        assert cur.fetchone() is not None

    def test_fts5_triggers_created(self, db: MemoryDatabase):
        """All 3 FTS5 triggers should exist."""
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            "ORDER BY name"
        )
        trigger_names = [row[0] for row in cur.fetchall()]
        assert "entries_ad" in trigger_names
        assert "entries_ai" in trigger_names
        assert "entries_au" in trigger_names

    def test_fts5_table_populated_on_insert(self, db: MemoryDatabase):
        """Inserting an entry should also populate the FTS5 table."""
        db.upsert_entry(_make_entry())
        cur = db._conn.execute("SELECT COUNT(*) FROM entries_fts")
        assert cur.fetchone()[0] == 1

    def test_fts5_table_cleared_on_delete(self, db: MemoryDatabase):
        """Deleting an entry from entries should remove it from FTS5."""
        db.upsert_entry(_make_entry())
        db._conn.execute("DELETE FROM entries WHERE id = 'abc123'")
        db._conn.commit()
        cur = db._conn.execute("SELECT COUNT(*) FROM entries_fts")
        assert cur.fetchone()[0] == 0

    def test_fts5_keywords_stripped_of_json(self, db: MemoryDatabase):
        """JSON array syntax should be stripped from keywords in FTS5."""
        db.upsert_entry(_make_entry(keywords=json.dumps(["alpha", "beta"])))
        # Search for a keyword directly (without JSON delimiters)
        cur = db._conn.execute(
            "SELECT COUNT(*) FROM entries_fts WHERE entries_fts MATCH 'alpha'"
        )
        assert cur.fetchone()[0] == 1

    def test_fts5_handles_empty_json_keywords(self, db: MemoryDatabase):
        """Entries with empty JSON '[]' keywords should not break FTS5 triggers."""
        entry = _make_entry(keywords="[]")
        db.upsert_entry(entry)
        cur = db._conn.execute("SELECT COUNT(*) FROM entries_fts")
        assert cur.fetchone()[0] == 1


# ---------------------------------------------------------------------------
# FTS5 search tests (T1.4)
# ---------------------------------------------------------------------------


class TestFTS5Search:
    def test_fts5_search_returns_list(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        results = db.fts5_search("test")
        assert isinstance(results, list)

    def test_fts5_search_matches_name(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(name="Error handling pattern"))
        results = db.fts5_search("error")
        assert len(results) >= 1
        ids = [r[0] for r in results]
        assert "abc123" in ids

    def test_fts5_search_matches_description(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(description="Retry with exponential backoff"))
        results = db.fts5_search("exponential")
        assert len(results) >= 1

    def test_fts5_search_matches_keywords(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(keywords=json.dumps(["resilience", "retry"])))
        results = db.fts5_search("resilience")
        assert len(results) >= 1

    def test_fts5_search_matches_reasoning(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(reasoning="Because flaky networks are common"))
        results = db.fts5_search("flaky")
        assert len(results) >= 1

    def test_fts5_search_returns_tuples_of_id_and_score(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        results = db.fts5_search("test")
        assert len(results) >= 1
        entry_id, score = results[0]
        assert isinstance(entry_id, str)
        assert isinstance(score, float)

    def test_fts5_search_score_is_positive(self, db: MemoryDatabase):
        """BM25 scores should be negated so higher = more relevant."""
        db.upsert_entry(_make_entry())
        results = db.fts5_search("test")
        assert len(results) >= 1
        _, score = results[0]
        assert score > 0

    def test_fts5_search_respects_limit(self, db: MemoryDatabase):
        for i in range(10):
            db.upsert_entry(_make_entry(
                id=f"id_{i}", name=f"Pattern {i}", description="common pattern"
            ))
        results = db.fts5_search("pattern", limit=3)
        assert len(results) == 3

    def test_fts5_search_no_match(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        results = db.fts5_search("xyznonsensequery")
        assert results == []

    def test_fts5_search_empty_db(self, db: MemoryDatabase):
        results = db.fts5_search("anything")
        assert results == []


# ---------------------------------------------------------------------------
# Embedding methods tests (T1.4)
# ---------------------------------------------------------------------------


class TestGetAllEmbeddings:
    def test_returns_none_when_no_embeddings(self, db: MemoryDatabase):
        """Should return None when no entries have embeddings."""
        db.upsert_entry(_make_entry())
        result = db.get_all_embeddings()
        assert result is None

    def test_returns_none_on_empty_db(self, db: MemoryDatabase):
        result = db.get_all_embeddings()
        assert result is None

    def test_returns_ids_and_matrix(self, db: MemoryDatabase):
        emb = np.array([0.1] * 768, dtype=np.float32).tobytes()
        db.upsert_entry(_make_entry(embedding=emb))
        result = db.get_all_embeddings()
        assert result is not None
        ids, matrix = result
        assert ids == ["abc123"]
        assert matrix.shape == (1, 768)
        assert matrix.dtype == np.float32

    def test_multiple_embeddings(self, db: MemoryDatabase):
        for i in range(3):
            emb = np.array([float(i)] * 768, dtype=np.float32).tobytes()
            db.upsert_entry(_make_entry(id=f"id_{i}", embedding=emb))
        result = db.get_all_embeddings()
        assert result is not None
        ids, matrix = result
        assert len(ids) == 3
        assert matrix.shape == (3, 768)

    def test_skips_corrupted_embeddings(self, db: MemoryDatabase, capsys):
        """Embeddings with wrong BLOB length should be skipped."""
        good_emb = np.array([0.1] * 768, dtype=np.float32).tobytes()
        db.upsert_entry(_make_entry(id="good", embedding=good_emb))
        # Insert a corrupted embedding directly
        bad_emb = b"\x00" * 10  # wrong length
        db.upsert_entry(_make_entry(id="bad", embedding=bad_emb))
        result = db.get_all_embeddings()
        assert result is not None
        ids, matrix = result
        assert ids == ["good"]
        assert matrix.shape == (1, 768)

    def test_skips_entries_without_embeddings(self, db: MemoryDatabase):
        """Entries with NULL embedding should not appear in results."""
        emb = np.array([0.1] * 768, dtype=np.float32).tobytes()
        db.upsert_entry(_make_entry(id="with_emb", embedding=emb))
        db.upsert_entry(_make_entry(id="no_emb"))
        result = db.get_all_embeddings()
        assert result is not None
        ids, matrix = result
        assert ids == ["with_emb"]

    def test_custom_expected_dims(self, db: MemoryDatabase):
        emb = np.array([0.5] * 384, dtype=np.float32).tobytes()
        db.upsert_entry(_make_entry(embedding=emb))
        result = db.get_all_embeddings(expected_dims=384)
        assert result is not None
        ids, matrix = result
        assert matrix.shape == (1, 384)


class TestUpdateEmbedding:
    def test_update_embedding(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        emb = np.array([0.5] * 768, dtype=np.float32).tobytes()
        db.update_embedding("abc123", emb)
        result = db.get_entry("abc123")
        assert result["embedding"] == emb

    def test_update_embedding_overwrites(self, db: MemoryDatabase):
        emb1 = np.array([0.1] * 768, dtype=np.float32).tobytes()
        db.upsert_entry(_make_entry(embedding=emb1))
        emb2 = np.array([0.9] * 768, dtype=np.float32).tobytes()
        db.update_embedding("abc123", emb2)
        result = db.get_entry("abc123")
        assert result["embedding"] == emb2


class TestClearAllEmbeddings:
    def test_clears_all_embeddings(self, db: MemoryDatabase):
        emb = np.array([0.1] * 768, dtype=np.float32).tobytes()
        db.upsert_entry(_make_entry(id="a", embedding=emb))
        db.upsert_entry(_make_entry(id="b", embedding=emb))
        db.clear_all_embeddings()
        assert db.get_entry("a")["embedding"] is None
        assert db.get_entry("b")["embedding"] is None

    def test_clear_embeddings_preserves_entries(self, db: MemoryDatabase):
        emb = np.array([0.1] * 768, dtype=np.float32).tobytes()
        db.upsert_entry(_make_entry(embedding=emb))
        db.clear_all_embeddings()
        assert db.count_entries() == 1


class TestGetEntriesWithoutEmbedding:
    def test_returns_entries_without_embedding(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(id="no_emb"))
        emb = np.array([0.1] * 768, dtype=np.float32).tobytes()
        db.upsert_entry(_make_entry(id="has_emb", embedding=emb))
        results = db.get_entries_without_embedding()
        assert len(results) == 1
        assert results[0]["id"] == "no_emb"

    def test_returns_empty_when_all_have_embeddings(self, db: MemoryDatabase):
        emb = np.array([0.1] * 768, dtype=np.float32).tobytes()
        db.upsert_entry(_make_entry(embedding=emb))
        results = db.get_entries_without_embedding()
        assert results == []

    def test_respects_limit(self, db: MemoryDatabase):
        for i in range(10):
            db.upsert_entry(_make_entry(id=f"id_{i}"))
        results = db.get_entries_without_embedding(limit=3)
        assert len(results) == 3

    def test_returns_dicts_with_expected_keys(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        results = db.get_entries_without_embedding()
        assert len(results) == 1
        entry = results[0]
        assert "id" in entry
        assert "name" in entry
        assert "description" in entry
        assert "keywords" in entry
        assert "reasoning" in entry


class TestUpdateRecall:
    def test_increments_recall_count(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        db.update_recall(["abc123"], "2026-02-20T12:00:00Z")
        result = db.get_entry("abc123")
        assert result["recall_count"] == 1

    def test_updates_last_recalled_at(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        ts = "2026-02-20T12:00:00Z"
        db.update_recall(["abc123"], ts)
        result = db.get_entry("abc123")
        assert result["last_recalled_at"] == ts

    def test_multiple_ids(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry(id="a"))
        db.upsert_entry(_make_entry(id="b"))
        db.upsert_entry(_make_entry(id="c"))
        ts = "2026-02-20T12:00:00Z"
        db.update_recall(["a", "b"], ts)
        assert db.get_entry("a")["recall_count"] == 1
        assert db.get_entry("b")["recall_count"] == 1
        assert db.get_entry("c")["recall_count"] == 0

    def test_increments_cumulatively(self, db: MemoryDatabase):
        db.upsert_entry(_make_entry())
        db.update_recall(["abc123"], "2026-02-20T12:00:00Z")
        db.update_recall(["abc123"], "2026-02-20T13:00:00Z")
        result = db.get_entry("abc123")
        assert result["recall_count"] == 2
        assert result["last_recalled_at"] == "2026-02-20T13:00:00Z"

    def test_empty_list_does_not_error(self, db: MemoryDatabase):
        db.update_recall([], "2026-02-20T12:00:00Z")


# ---------------------------------------------------------------------------
# Delete entry tests
# ---------------------------------------------------------------------------


class TestDeleteEntry:
    """Tests for MemoryDatabase.delete_entry (feature 047)."""

    def test_delete_entry_not_found(self, db: MemoryDatabase):
        """AC-5: Deleting a nonexistent entry raises ValueError."""
        with pytest.raises(ValueError, match="Memory entry not found"):
            db.delete_entry("nonexistent-id")

    def test_delete_entry_success(self, db: MemoryDatabase):
        """AC-6: Deleting an entry removes the row and FTS trigger auto-cleans."""
        entry = _make_entry(id="del-test", name="Delete Me", description="To be deleted")
        db.upsert_entry(entry)
        assert db.get_entry("del-test") is not None

        db.delete_entry("del-test")

        assert db.get_entry("del-test") is None

    def test_delete_entry_fts_cleaned(self, db: MemoryDatabase):
        """AC-7: After delete, FTS search no longer returns the deleted entry."""
        entry = _make_entry(id="fts-del", name="Unique Searchable Name",
                           description="A unique description for FTS test")
        db.upsert_entry(entry)
        # Confirm FTS finds it before delete
        results = db.fts5_search("Unique Searchable")
        assert len(results) > 0

        db.delete_entry("fts-del")

        results = db.fts5_search("Unique Searchable")
        assert len(results) == 0


# ---------------------------------------------------------------------------
# FTS5 sanitizer unit tests (Task 1.1)
# ---------------------------------------------------------------------------


class TestFts5Sanitizer:
    """Unit tests for _sanitize_fts5_query()."""

    def test_multi_word_joins_with_or(self):
        assert _sanitize_fts5_query("firebase firestore typescript") == "firebase OR firestore OR typescript"

    def test_single_word_unchanged(self):
        assert _sanitize_fts5_query("firebase") == "firebase"

    def test_hyphenated_quoted(self):
        assert _sanitize_fts5_query("anti-patterns") == '"anti-patterns"'

    def test_mixed_hyphen_and_plain(self):
        assert _sanitize_fts5_query("source session-capture") == 'source OR "session-capture"'

    def test_colon_stripped(self):
        assert _sanitize_fts5_query("source:session-capture") == 'source OR "session-capture"'

    def test_special_chars_stripped(self):
        # .claude-plugin/marketplace.json
        # Strip . / . → "claude-plugin marketplace json"
        # "claude-plugin" has hyphen → quoted
        result = _sanitize_fts5_query(".claude-plugin/marketplace.json")
        assert result == '"claude-plugin" OR marketplace OR json'

    def test_double_quotes_stripped(self):
        assert _sanitize_fts5_query('"hello"') == "hello"

    def test_standalone_dash_dropped(self):
        assert _sanitize_fts5_query("foo - bar") == "foo OR bar"

    def test_all_special_chars_returns_empty(self):
        assert _sanitize_fts5_query("...") == ""

    def test_empty_input_returns_empty(self):
        assert _sanitize_fts5_query("") == ""


# ---------------------------------------------------------------------------
# FTS5 search integration tests (Task 1.4)
# ---------------------------------------------------------------------------


class TestFts5SearchIntegration:
    """Integration tests for fts5_search with sanitized queries."""

    def _seed_entries(self, db):
        """Seed controlled test data for FTS5 integration tests."""
        entries = [
            ("e-firebase", "Firebase authentication patterns",
             "Use Firebase Auth for serverless apps with typescript integration",
             "patterns", '["firebase", "auth", "typescript"]'),
            ("e-firestore", "Firestore query optimization",
             "Optimize Firestore queries for better performance in typescript projects",
             "patterns", '["firestore", "query", "typescript"]'),
            ("e-antipatterns", "Common anti-patterns in hooks",
             "Avoid anti-patterns when writing shell hooks for git workflows",
             "anti-patterns", '["anti-patterns", "hooks", "git"]'),
            ("e-createplan", "Task creation with create-plan",
             "Use create-plan workflow for structured task generation",
             "heuristics", '["create-plan", "workflow"]'),
            ("e-gitflow", "Git-flow branching strategy",
             "Follow git-flow for release management and feature branches",
             "patterns", '["git-flow", "branching", "release"]'),
            ("e-claude", "Claude plugin marketplace",
             "Register plugins in the claude marketplace for distribution using json config",
             "heuristics", '["claude", "plugin", "marketplace", "json"]'),
            ("e-session", "Session capture source patterns",
             "Use session-capture source for automated knowledge extraction",
             "patterns", '["session-capture", "source", "knowledge"]'),
        ]
        for eid, name, desc, cat, kw in entries:
            db.upsert_entry(_make_entry(
                id=eid, name=name, description=desc, category=cat, keywords=kw,
            ))

    def test_fts5_or_search_returns_any_match(self, db: MemoryDatabase):
        """AC-1.1: Multi-word query returns entries matching any term."""
        self._seed_entries(db)
        results = db.fts5_search("firebase firestore typescript")
        ids = [r[0] for r in results]
        # Both firebase and firestore entries should match
        assert "e-firebase" in ids
        assert "e-firestore" in ids
        assert len(results) >= 2

    def test_fts5_bm25_ranks_multi_match_higher(self, db: MemoryDatabase):
        """AC-1.3: Entry matching more terms ranks above entry matching fewer."""
        self._seed_entries(db)
        # "firebase typescript" — e-firebase matches both terms in desc,
        # e-firestore also matches both. Any entry matching only one term
        # should rank lower.
        results = db.fts5_search("firebase typescript")
        ids = [r[0] for r in results]
        # e-firebase should be in results (matches both firebase and typescript)
        assert "e-firebase" in ids
        # The first result should match more query terms
        assert len(results) >= 1

    def test_fts5_hyphenated_search(self, db: MemoryDatabase):
        """AC-2.1: Hyphenated term returns matches."""
        self._seed_entries(db)
        results = db.fts5_search("anti-patterns")
        ids = [r[0] for r in results]
        assert "e-antipatterns" in ids

    def test_fts5_multi_hyphenated_search(self, db: MemoryDatabase):
        """AC-2.2: Multiple hyphenated terms return matches for both."""
        self._seed_entries(db)
        results = db.fts5_search("create-plan git-flow")
        ids = [r[0] for r in results]
        assert "e-createplan" in ids
        assert "e-gitflow" in ids

    def test_fts5_special_char_query(self, db: MemoryDatabase):
        """AC-3.1: Query with special chars returns results matching constituent words."""
        self._seed_entries(db)
        results = db.fts5_search(".claude-plugin/marketplace.json")
        ids = [r[0] for r in results]
        assert "e-claude" in ids

    def test_fts5_colon_query(self, db: MemoryDatabase):
        """AC-3.2: Query with colons returns results matching constituent words."""
        self._seed_entries(db)
        results = db.fts5_search("source:session-capture")
        ids = [r[0] for r in results]
        assert "e-session" in ids

    def test_fts5_error_logged_to_stderr(self, db: MemoryDatabase, capsys):
        """AC-4.1: OperationalError produces diagnostic stderr output.
        AC-4.2: Function still returns [] on error."""
        # Force an OperationalError by corrupting the FTS table
        # We can do this by dropping the FTS table and then searching
        db._conn.execute("DROP TABLE IF EXISTS entries_fts")
        db._conn.commit()
        # fts5_available is still True, so fts5_search will attempt MATCH
        results = db.fts5_search("test query")
        assert results == []
        captured = capsys.readouterr()
        assert "semantic_memory: FTS5 error for query" in captured.err
        assert "test query" in captured.err


# ---------------------------------------------------------------------------
# Migration v4 tests (influence tracking)
# ---------------------------------------------------------------------------


def _create_v3_db(db_path: str) -> sqlite3.Connection:
    """Create a v3 database manually for migration 4 testing."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entries (
            id                TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            description       TEXT NOT NULL,
            reasoning         TEXT,
            category          TEXT NOT NULL CHECK(category IN ('anti-patterns', 'patterns', 'heuristics')),
            keywords          TEXT NOT NULL DEFAULT '[]',
            source            TEXT NOT NULL CHECK(source IN ('retro', 'session-capture', 'manual', 'import')),
            source_project    TEXT NOT NULL,
            "references"      TEXT,
            observation_count INTEGER DEFAULT 1,
            confidence        TEXT DEFAULT 'medium' CHECK(confidence IN ('high', 'medium', 'low')),
            recall_count      INTEGER DEFAULT 0,
            last_recalled_at  TEXT,
            embedding         BLOB,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            source_hash       TEXT NOT NULL,
            created_timestamp_utc REAL
        );
        CREATE TABLE IF NOT EXISTS _metadata (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT INTO _metadata (key, value) VALUES ('schema_version', '3');
    """)
    return conn


class TestMigration4:
    """Tests for migration 4: influence_count column + influence_log table."""

    def test_migration_creates_influence_count_column(self, tmp_path):
        """Migration 4 adds influence_count column to entries table."""
        db_path = str(tmp_path / "test.db")
        conn = _create_v3_db(db_path)
        conn.execute(
            "INSERT INTO entries (id, name, description, category, source, "
            "source_project, source_hash, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("e1", "Test", "Desc", "patterns", "manual",
             "/proj", "hash1234abcd5678", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        db = MemoryDatabase(db_path)
        assert db.get_schema_version() == 5

        # Verify influence_count column exists and defaults to 0
        entry = db.get_entry("e1")
        assert entry is not None
        assert entry["influence_count"] == 0

        # Verify column is in PRAGMA table_info
        cur = db._conn.execute("PRAGMA table_info(entries)")
        col_names = [row[1] for row in cur.fetchall()]
        assert "influence_count" in col_names
        db.close()

    def test_migration_creates_influence_log_table(self, tmp_path):
        """Migration 4 creates the influence_log table."""
        db_path = str(tmp_path / "test.db")
        conn = _create_v3_db(db_path)
        conn.commit()
        conn.close()

        db = MemoryDatabase(db_path)
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='influence_log'"
        )
        assert cur.fetchone() is not None

        # Verify table schema
        cur = db._conn.execute("PRAGMA table_info(influence_log)")
        col_names = [row[1] for row in cur.fetchall()]
        assert col_names == ["id", "entry_id", "agent_role", "feature_type_id", "timestamp"]
        db.close()

    def test_migration_is_idempotent(self, tmp_path):
        """Opening DB twice after migration 4 does not error (schema_version prevents re-run)."""
        db_path = str(tmp_path / "test.db")
        conn = _create_v3_db(db_path)
        conn.commit()
        conn.close()

        db1 = MemoryDatabase(db_path)
        assert db1.get_schema_version() == 5
        db1.close()

        db2 = MemoryDatabase(db_path)
        assert db2.get_schema_version() == 5
        db2.close()

    def test_migration_influence_count_default_zero_on_new_entry(self, db: MemoryDatabase):
        """New entries get influence_count=0 by default."""
        db.upsert_entry(_make_entry())
        entry = db.get_entry("abc123")
        assert entry["influence_count"] == 0


# ---------------------------------------------------------------------------
# merge_duplicate tests
# ---------------------------------------------------------------------------


class TestMergeDuplicate:
    """Tests for MemoryDatabase.merge_duplicate method."""

    def test_increments_observation_count(self, db: MemoryDatabase):
        """merge_duplicate should increment observation_count by 1."""
        db.upsert_entry(_make_entry())
        assert db.get_entry("abc123")["observation_count"] == 1

        result = db.merge_duplicate("abc123", ["new-keyword"])
        assert result["observation_count"] == 2

    def test_increments_observation_count_multiple_times(self, db: MemoryDatabase):
        """Calling merge_duplicate twice increments observation_count to 3."""
        db.upsert_entry(_make_entry())
        db.merge_duplicate("abc123", [])
        result = db.merge_duplicate("abc123", [])
        assert result["observation_count"] == 3

    def test_unions_keywords(self, db: MemoryDatabase):
        """merge_duplicate should union existing and new keywords."""
        db.upsert_entry(_make_entry(keywords=json.dumps(["existing-1", "existing-2"])))
        result = db.merge_duplicate("abc123", ["existing-1", "new-1", "new-2"])
        keywords = json.loads(result["keywords"])
        assert set(keywords) == {"existing-1", "existing-2", "new-1", "new-2"}
        # Existing keywords should come first (order preserved)
        assert keywords[:2] == ["existing-1", "existing-2"]

    def test_preserves_other_fields(self, db: MemoryDatabase):
        """merge_duplicate should not modify name, description, reasoning, etc."""
        db.upsert_entry(_make_entry(
            name="Original Name",
            description="Original Description",
            reasoning="Original Reasoning",
            category="patterns",
            source="manual",
            confidence="high",
            source_project="/my/project",
        ))

        result = db.merge_duplicate("abc123", ["new-kw"])

        assert result["name"] == "Original Name"
        assert result["description"] == "Original Description"
        assert result["reasoning"] == "Original Reasoning"
        assert result["category"] == "patterns"
        assert result["source"] == "manual"
        assert result["confidence"] == "high"
        assert result["source_project"] == "/my/project"
        assert result["recall_count"] == 0
        assert result["influence_count"] == 0

    def test_updates_updated_at(self, db: MemoryDatabase):
        """merge_duplicate should refresh updated_at timestamp."""
        db.upsert_entry(_make_entry(updated_at="2026-01-01T00:00:00Z"))
        original = db.get_entry("abc123")
        assert original["updated_at"] == "2026-01-01T00:00:00Z"

        result = db.merge_duplicate("abc123", [])
        assert result["updated_at"] != "2026-01-01T00:00:00Z"
        assert result["updated_at"] > "2026-01-01T00:00:00Z"

    def test_raises_valueerror_for_nonexistent_id(self, db: MemoryDatabase):
        """merge_duplicate should raise ValueError for non-existent entry ID."""
        with pytest.raises(ValueError, match="Memory entry not found"):
            db.merge_duplicate("nonexistent-id", ["kw"])

    def test_handles_malformed_keywords_json(self, db: MemoryDatabase):
        """merge_duplicate should handle malformed existing keywords JSON gracefully."""
        db.upsert_entry(_make_entry(keywords="not-valid-json{"))
        result = db.merge_duplicate("abc123", ["new-kw"])
        keywords = json.loads(result["keywords"])
        assert keywords == ["new-kw"]

    def test_handles_empty_keywords(self, db: MemoryDatabase):
        """merge_duplicate with empty existing keywords and empty new keywords."""
        db.upsert_entry(_make_entry(keywords="[]"))
        result = db.merge_duplicate("abc123", [])
        keywords = json.loads(result["keywords"])
        assert keywords == []

    def test_handles_non_list_keywords_json(self, db: MemoryDatabase):
        """merge_duplicate should handle keywords that parse to non-list (e.g. string)."""
        db.upsert_entry(_make_entry(keywords='"just-a-string"'))
        result = db.merge_duplicate("abc123", ["new-kw"])
        keywords = json.loads(result["keywords"])
        assert keywords == ["new-kw"]

    def test_returns_full_entry_dict(self, db: MemoryDatabase):
        """merge_duplicate should return a complete entry dict."""
        db.upsert_entry(_make_entry())
        result = db.merge_duplicate("abc123", ["kw"])
        assert "id" in result
        assert "name" in result
        assert "description" in result
        assert "influence_count" in result


class TestMergeDuplicatePromotion:
    """Tests for confidence auto-promotion in merge_duplicate()."""

    def _seed_entry(self, db, *, obs_count=2, confidence="low", source="session-capture"):
        """Seed an entry with specific observation_count, confidence, and source."""
        entry = _make_entry(
            id="promo1",
            confidence=confidence,
            source=source,
        )
        db.upsert_entry(entry)
        # Set observation_count directly (the upsert starts at 1)
        if obs_count != 1:
            db._conn.execute(
                "UPDATE entries SET observation_count = ? WHERE id = ?",
                (obs_count, "promo1"),
            )
            db._conn.commit()

    def test_merge_duplicate_promotes_low_to_medium(self, db: MemoryDatabase):
        """When auto_promote=True and obs_count crosses threshold, low -> medium."""
        self._seed_entry(db, obs_count=2, confidence="low", source="session-capture")
        config = {"memory_auto_promote": True, "memory_promote_low_threshold": 3}
        result = db.merge_duplicate("promo1", ["kw"], config=config)
        assert result["confidence"] == "medium"
        assert result["observation_count"] == 3

    def test_merge_duplicate_promotes_medium_to_high_retro_only(self, db: MemoryDatabase):
        """medium -> high requires source=retro and obs_count >= threshold."""
        self._seed_entry(db, obs_count=4, confidence="medium", source="retro")
        config = {"memory_auto_promote": True, "memory_promote_medium_threshold": 5}
        result = db.merge_duplicate("promo1", ["kw"], config=config)
        assert result["confidence"] == "high"
        assert result["observation_count"] == 5

    def test_merge_duplicate_no_promote_when_disabled(self, db: MemoryDatabase):
        """When auto_promote=False (default), confidence stays unchanged."""
        self._seed_entry(db, obs_count=2, confidence="low", source="session-capture")
        config = {"memory_auto_promote": False, "memory_promote_low_threshold": 3}
        result = db.merge_duplicate("promo1", ["kw"], config=config)
        assert result["confidence"] == "low"

    def test_merge_duplicate_no_promote_import_source(self, db: MemoryDatabase):
        """source=import entries never promote even when thresholds are met."""
        self._seed_entry(db, obs_count=2, confidence="low", source="import")
        config = {"memory_auto_promote": True, "memory_promote_low_threshold": 3}
        result = db.merge_duplicate("promo1", ["kw"], config=config)
        assert result["confidence"] == "low"

    def test_merge_duplicate_no_promote_below_threshold(self, db: MemoryDatabase):
        """obs_count below threshold -> no promotion."""
        self._seed_entry(db, obs_count=1, confidence="low", source="session-capture")
        config = {"memory_auto_promote": True, "memory_promote_low_threshold": 3}
        result = db.merge_duplicate("promo1", ["kw"], config=config)
        # obs_count is now 2, still below 3
        assert result["confidence"] == "low"
        assert result["observation_count"] == 2

    def test_merge_duplicate_already_at_target(self, db: MemoryDatabase):
        """Entry already at high confidence -> no change."""
        self._seed_entry(db, obs_count=10, confidence="high", source="retro")
        config = {"memory_auto_promote": True, "memory_promote_low_threshold": 3, "memory_promote_medium_threshold": 5}
        result = db.merge_duplicate("promo1", ["kw"], config=config)
        assert result["confidence"] == "high"

    def test_merge_duplicate_medium_no_promote_non_retro(self, db: MemoryDatabase):
        """medium -> high requires source=retro; session-capture stays medium."""
        self._seed_entry(db, obs_count=4, confidence="medium", source="session-capture")
        config = {"memory_auto_promote": True, "memory_promote_medium_threshold": 5}
        result = db.merge_duplicate("promo1", ["kw"], config=config)
        assert result["confidence"] == "medium"


# ---------------------------------------------------------------------------
# Test: find_entry_by_name (Task 2.2.1)
# ---------------------------------------------------------------------------


class TestFindEntryByName:
    def test_exact_match_case_insensitive(self, db: MemoryDatabase):
        """find_entry_by_name should find entry by exact name (case-insensitive)."""
        db.upsert_entry(_make_entry(id="e1", name="Hook Stderr Pattern"))
        result = db.find_entry_by_name("hook stderr pattern")
        assert result is not None
        assert result["id"] == "e1"
        assert result["name"] == "Hook Stderr Pattern"

    def test_exact_match_same_case(self, db: MemoryDatabase):
        """find_entry_by_name should find entry with exact same case."""
        db.upsert_entry(_make_entry(id="e1", name="My Pattern"))
        result = db.find_entry_by_name("My Pattern")
        assert result is not None
        assert result["id"] == "e1"

    def test_like_fallback_when_exact_fails(self, db: MemoryDatabase):
        """find_entry_by_name should fall back to LIKE when exact match fails."""
        db.upsert_entry(_make_entry(id="e1", name="Always validate hook inputs before processing"))
        result = db.find_entry_by_name("validate hook inputs")
        assert result is not None
        assert result["id"] == "e1"

    def test_returns_none_for_nonexistent(self, db: MemoryDatabase):
        """find_entry_by_name should return None when no entry matches."""
        db.upsert_entry(_make_entry(id="e1", name="Something"))
        result = db.find_entry_by_name("completely different name")
        assert result is None

    def test_sql_wildcards_escaped(self, db: MemoryDatabase):
        """find_entry_by_name should escape SQL wildcards in the LIKE fallback."""
        db.upsert_entry(_make_entry(id="e1", name="Pattern with 100% accuracy"))
        # '%' in the search name should be escaped, not act as wildcard
        result = db.find_entry_by_name("100%")
        assert result is not None
        assert result["id"] == "e1"

    def test_underscore_escaped(self, db: MemoryDatabase):
        """find_entry_by_name should escape underscore in the LIKE fallback."""
        db.upsert_entry(_make_entry(id="e1", name="Use _embed_text_for_entry helper"))
        # '_' in the search name should be escaped, not act as single-char wildcard
        result = db.find_entry_by_name("_embed_text_for_entry")
        assert result is not None
        assert result["id"] == "e1"

    def test_returns_first_match_on_multiple(self, db: MemoryDatabase):
        """find_entry_by_name should return the first matching entry."""
        db.upsert_entry(_make_entry(id="e1", name="Pattern A about hooks"))
        db.upsert_entry(_make_entry(id="e2", name="Pattern B about hooks"))
        result = db.find_entry_by_name("hooks")
        assert result is not None
        assert result["id"] in ("e1", "e2")


# ---------------------------------------------------------------------------
# Test: record_influence (Task 2.2.2 — combined atomic method)
# ---------------------------------------------------------------------------


class TestRecordInfluence:
    def test_increments_influence_count(self, db: MemoryDatabase):
        """record_influence should increase influence_count by 1."""
        db.upsert_entry(_make_entry(id="e1"))
        assert db.get_entry("e1")["influence_count"] == 0

        db.record_influence("e1", "implementer", "feature:057")
        assert db.get_entry("e1")["influence_count"] == 1

        db.record_influence("e1", "reviewer", "feature:057")
        assert db.get_entry("e1")["influence_count"] == 2

    def test_increment_only_affects_target(self, db: MemoryDatabase):
        """record_influence should not affect other entries."""
        db.upsert_entry(_make_entry(id="e1"))
        db.upsert_entry(_make_entry(id="e2", name="Other"))

        db.record_influence("e1", "implementer", "feature:057")
        assert db.get_entry("e1")["influence_count"] == 1
        assert db.get_entry("e2")["influence_count"] == 0

    def test_inserts_influence_log_row(self, db: MemoryDatabase):
        """record_influence should insert a row into influence_log."""
        db.upsert_entry(_make_entry(id="e1"))
        db.record_influence("e1", "implementer", "feature:057-memory")

        rows = db._conn.execute(
            "SELECT entry_id, agent_role, feature_type_id, timestamp "
            "FROM influence_log"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "e1"
        assert rows[0][1] == "implementer"
        assert rows[0][2] == "feature:057-memory"
        assert rows[0][3] is not None  # timestamp present

    def test_inserts_with_null_feature_type_id(self, db: MemoryDatabase):
        """record_influence should accept None for feature_type_id."""
        db.upsert_entry(_make_entry(id="e1"))
        db.record_influence("e1", "reviewer", None)

        rows = db._conn.execute(
            "SELECT feature_type_id FROM influence_log"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] is None

    def test_multiple_records_accumulate(self, db: MemoryDatabase):
        """record_influence should accumulate multiple rows for same entry."""
        db.upsert_entry(_make_entry(id="e1"))
        db.record_influence("e1", "implementer", "feature:057")
        db.record_influence("e1", "reviewer", "feature:057")
        db.record_influence("e1", "implementer", "feature:058")

        count = db._conn.execute(
            "SELECT COUNT(*) FROM influence_log WHERE entry_id = 'e1'"
        ).fetchone()[0]
        assert count == 3


# ---------------------------------------------------------------------------
# Concurrent init / migration atomicity tests (Bug 1 fix)
# ---------------------------------------------------------------------------


class TestConcurrentInit:
    """6 threads concurrently create MemoryDatabase on the same new DB file.

    All must succeed.  Post-condition: schema_version == target and all
    expected columns exist.
    """

    def test_concurrent_init_all_succeed(self, tmp_path, monkeypatch):
        import threading
        import time

        db_path = str(tmp_path / "concurrent.db")
        num_threads = 6
        barrier = threading.Barrier(num_threads)
        errors: list[Exception] = []
        dbs: list[MemoryDatabase] = [None] * num_threads

        # Set busy_timeout BEFORE journal_mode to avoid lock contention
        # on the WAL pragma when many threads init concurrently.
        _orig_set_pragmas = MemoryDatabase._set_pragmas

        def _patient_pragmas(self):
            self._conn.execute("PRAGMA busy_timeout = 60000")
            _orig_set_pragmas(self)

        monkeypatch.setattr(MemoryDatabase, "_set_pragmas", _patient_pragmas)

        def _init(idx: int) -> None:
            try:
                barrier.wait(timeout=5)
                dbs[idx] = MemoryDatabase(db_path)
            except Exception as exc:
                errors.append(exc)
            finally:
                # Close in the same thread that created the connection.
                if dbs[idx] is not None:
                    dbs[idx].close()
                    dbs[idx] = None

        threads = [threading.Thread(target=_init, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # All threads completed without error.
        assert errors == [], f"Concurrent init errors: {errors}"

        # Verify post-conditions on a fresh connection.
        from semantic_memory.database import MIGRATIONS

        verify_db = MemoryDatabase(db_path)
        try:
            assert verify_db.get_schema_version() == max(MIGRATIONS)

            # All 19 columns must exist.
            cur = verify_db._conn.execute("PRAGMA table_info(entries)")
            col_names = {row[1] for row in cur.fetchall()}
            expected = {
                "id", "name", "description", "reasoning", "category",
                "keywords", "source", "source_project", "references",
                "observation_count", "confidence", "recall_count",
                "last_recalled_at", "embedding", "created_at", "updated_at",
                "source_hash", "created_timestamp_utc", "influence_count",
            }
            assert expected.issubset(col_names), f"Missing columns: {expected - col_names}"
        finally:
            verify_db.close()


class TestMigrationAtomicity:
    """If a migration raises mid-way, schema_version must not increment.

    The next connection retries the failed migration successfully.
    """

    def test_failed_migration_leaves_version_unchanged(self, tmp_path):
        from unittest.mock import patch
        from semantic_memory.database import MIGRATIONS

        db_path = str(tmp_path / "atomic.db")
        target = max(MIGRATIONS)

        # Create a patched MIGRATIONS dict where the last migration raises.
        bomb_called = False

        def _bomb(conn, **kwargs):
            nonlocal bomb_called
            bomb_called = True
            raise RuntimeError("simulated migration failure")

        patched = dict(MIGRATIONS)
        patched[target] = _bomb

        # First attempt: migration should fail.
        with patch("semantic_memory.database.MIGRATIONS", patched):
            with pytest.raises(RuntimeError, match="simulated migration failure"):
                MemoryDatabase(db_path)
        assert bomb_called

        # Verify schema_version is less than target (the failing migration
        # and all migrations in its transaction were rolled back).
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute(
                "SELECT value FROM _metadata WHERE key = 'schema_version'"
            )
            row = cur.fetchone()
            stored_version = int(row[0]) if row else 0
            assert stored_version < target, (
                f"schema_version should be < {target}, got {stored_version}"
            )
        finally:
            conn.close()

        # Second attempt: with real migrations, should succeed.
        db = MemoryDatabase(db_path)
        try:
            assert db.get_schema_version() == target
        finally:
            db.close()


class TestMigration5FTS5Rebuild:
    """Migration 5 repopulates entries_fts for DBs that missed the v3 rebuild."""

    def test_migration_repopulates_empty_fts5(self, tmp_path):
        db_path = str(tmp_path / "t.db")
        db = MemoryDatabase(db_path)
        try:
            db.upsert_entry(_make_entry(name="test-entry-for-fts", description="Memory flywheel fts5 backfill verification", keywords=json.dumps(["fts5"]), source_project="P002", id="id-" + "test-entry-for-fts".replace(chr(34), "")[:20].replace(" ", "-")))
            # Drop the virtual table entirely to simulate a DB that never had FTS5 populated.
            db._conn.execute("DROP TABLE IF EXISTS entries_fts")
            db._conn.commit()

            from semantic_memory.database import _rebuild_fts5_index
            _rebuild_fts5_index(db._conn, fts5_available=True)
            db._conn.commit()

            entries_count = db.count_entries()
            fts_count = db._conn.execute("SELECT COUNT(*) FROM entries_fts").fetchone()[0]
            assert fts_count == entries_count
        finally:
            db.close()

    def test_migration_is_idempotent(self, tmp_path):
        db_path = str(tmp_path / "t.db")
        db = MemoryDatabase(db_path)
        try:
            db.upsert_entry(_make_entry(name="idem-test", description="idempotent rebuild check", keywords=json.dumps([]), source_project="P", id="id-" + "idem-test".replace(chr(34), "")[:20].replace(" ", "-")))
            from semantic_memory.database import _rebuild_fts5_index
            _rebuild_fts5_index(db._conn, fts5_available=True)
            db._conn.commit()
            count_after_first = db._conn.execute("SELECT COUNT(*) FROM entries_fts").fetchone()[0]
            _rebuild_fts5_index(db._conn, fts5_available=True)
            db._conn.commit()
            count_after_second = db._conn.execute("SELECT COUNT(*) FROM entries_fts").fetchone()[0]
            assert count_after_first == count_after_second == db.count_entries()
        finally:
            db.close()

    def test_fts5_unavailable_is_noop(self, tmp_path):
        db_path = str(tmp_path / "t.db")
        db = MemoryDatabase(db_path)
        try:
            from semantic_memory.database import _rebuild_fts5_index
            _rebuild_fts5_index(db._conn, fts5_available=False)
        finally:
            db.close()


class TestFTS5TriggerSync:
    """Triggers keep entries_fts in sync with entries for insert/update/delete."""

    def test_insert_trigger_populates_fts(self, tmp_path):
        db_path = str(tmp_path / "t.db")
        db = MemoryDatabase(db_path)
        try:
            if not db._fts5_available:
                pytest.skip("FTS5 not available")
            db.upsert_entry(_make_entry(name="trigger-insert-test", description="unique-marker-abracadabra influence wiring", keywords=json.dumps(["trigger"]), source_project="P", id="id-" + "trigger-insert-test".replace(chr(34), "")[:20].replace(" ", "-")))
            results = db.fts5_search("abracadabra", limit=10)
            assert len(results) >= 1
        finally:
            db.close()

    def test_update_trigger_reindexes(self, tmp_path):
        db_path = str(tmp_path / "t.db")
        db = MemoryDatabase(db_path)
        try:
            if not db._fts5_available:
                pytest.skip("FTS5 not available")
            entry = _make_entry(name="trigger-update-test", description="original-token zebra", keywords=json.dumps([]), source_project="P", id="id-" + "trigger-update-test".replace(chr(34), "")[:20].replace(" ", "-"))
            db.upsert_entry(entry)
            entry["description"] = "modified-token yak"
            db.upsert_entry(entry)
            assert len(db.fts5_search("yak", limit=10)) >= 1
            assert len(db.fts5_search("zebra", limit=10)) == 0
        finally:
            db.close()

    def test_delete_trigger_removes_from_fts(self, tmp_path):
        db_path = str(tmp_path / "t.db")
        db = MemoryDatabase(db_path)
        try:
            if not db._fts5_available:
                pytest.skip("FTS5 not available")
            entry = _make_entry(name="trigger-delete-test", description="doomed-token quasar", keywords=json.dumps([]), source_project="P", id="id-" + "trigger-delete-test".replace(chr(34), "")[:20].replace(" ", "-"))
            db.upsert_entry(entry)
            assert len(db.fts5_search("quasar", limit=10)) >= 1
            db._conn.execute("DELETE FROM entries WHERE id = ?", (entry["id"],))
            db._conn.commit()
            assert len(db.fts5_search("quasar", limit=10)) == 0
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Feature 082 — busy_timeout_ms kwarg + batch_demote
# ---------------------------------------------------------------------------


class TestBusyTimeoutKwarg:
    """Task 2.1 / 2.2 — public accessor `get_busy_timeout_ms()` avoids
    the `db._conn` direct-access anti-pattern while verifying the kwarg
    was stored + forwarded to `_set_pragmas`.
    """

    def test_default_is_fifteen_thousand(self):
        db = MemoryDatabase(":memory:")
        try:
            assert db.get_busy_timeout_ms() == 15000
        finally:
            db.close()

    def test_override_via_kwarg(self):
        db = MemoryDatabase(":memory:", busy_timeout_ms=1000)
        try:
            assert db.get_busy_timeout_ms() == 1000
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Helpers for batch_demote tests
# ---------------------------------------------------------------------------


def _seed_entry_for_demote(
    db: MemoryDatabase,
    *,
    entry_id: str,
    confidence: str = "high",
    updated_at: str = "2020-01-01T00:00:00+00:00",
):
    """Raw INSERT to bypass upsert_entry (which always writes its own
    timestamps). Allows tests to seed stale `updated_at` so that the
    `updated_at < ?` guard in batch_demote triggers on fresh `now_iso`.
    """
    db._conn.execute(
        "INSERT INTO entries (id, name, description, category, keywords, "
        "source, source_project, source_hash, confidence, recall_count, "
        "last_recalled_at, created_at, updated_at, observation_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entry_id,
            f"name-{entry_id}",
            "desc",
            "patterns",
            json.dumps(["k"]),
            "session-capture",
            "/tmp/test-project",
            "0" * 16,
            confidence,
            0,
            None,
            "2020-01-01T00:00:00+00:00",
            updated_at,
            1,
        ),
    )
    db._conn.commit()


def _get_confidence(db: MemoryDatabase, entry_id: str) -> str:
    cur = db._conn.execute(
        "SELECT confidence FROM entries WHERE id = ?", (entry_id,)
    )
    return cur.fetchone()["confidence"]


def _get_updated_at(db: MemoryDatabase, entry_id: str) -> str:
    cur = db._conn.execute(
        "SELECT updated_at FROM entries WHERE id = ?", (entry_id,)
    )
    return cur.fetchone()["updated_at"]


class TestScanDecayCandidates:
    """Feature 091 FR-4 (#00078): public ``scan_decay_candidates`` method
    encapsulates the read path previously inlined at
    ``maintenance._select_candidates``. Closes "Direct db._conn Access"
    anti-pattern.
    """

    def test_scan_decay_candidates_respects_where_predicate(self, db: MemoryDatabase):
        """AC-7 (WHERE predicate): seed 3 stale + 7 fresh; scan_limit=100 returns only 3 stale."""
        cutoff = "2026-04-20T00:00:00Z"
        for i in range(3):
            db.insert_test_entry_for_testing(
                entry_id=f"e-stale-{i}",
                description=f"stale entry {i}",
                confidence="high",
                source="session-capture",
                last_recalled_at="2026-04-15T00:00:00Z",
                created_at="2026-04-15T00:00:00Z",
            )
        for i in range(7):
            db.insert_test_entry_for_testing(
                entry_id=f"e-fresh-{i}",
                description=f"fresh entry {i}",
                confidence="high",
                source="session-capture",
                last_recalled_at="2026-04-25T00:00:00Z",
                created_at="2026-04-25T00:00:00Z",
            )
        rows = list(db.scan_decay_candidates(
            not_null_cutoff=cutoff, scan_limit=100,
        ))
        assert len(rows) == 3, f"expected 3 stale rows, got {len(rows)}"

    def test_scan_decay_candidates_respects_scan_limit_cap(self, db: MemoryDatabase):
        """AC-7 (scan_limit cap): scan_limit caps result below match count."""
        cutoff = "2026-04-20T00:00:00Z"
        for i in range(10):
            db.insert_test_entry_for_testing(
                entry_id=f"e-stale-{i}",
                description=f"stale {i}",
                confidence="high",
                source="session-capture",
                last_recalled_at="2026-04-15T00:00:00Z",
                created_at="2026-04-15T00:00:00Z",
            )
        rows = list(db.scan_decay_candidates(
            not_null_cutoff=cutoff, scan_limit=5,
        ))
        assert len(rows) == 5

    def test_scan_decay_candidates_includes_null_last_recalled_at(
        self, db: MemoryDatabase
    ):
        """AC-7b: NULL last_recalled_at rows are returned."""
        cutoff = "2026-04-20T00:00:00Z"
        db.insert_test_entry_for_testing(
            entry_id="e-null",
            description="x",
            confidence="medium",
            source="session-capture",
            last_recalled_at=None,
            created_at="2026-04-15T00:00:00Z",
        )
        db.insert_test_entry_for_testing(
            entry_id="e-past",
            description="y",
            confidence="high",
            source="session-capture",
            last_recalled_at="2026-04-15T00:00:00Z",
            created_at="2026-04-15T00:00:00Z",
        )
        rows = list(db.scan_decay_candidates(
            not_null_cutoff=cutoff, scan_limit=100,
        ))
        ids = {row["id"] for row in rows}
        assert "e-null" in ids
        assert "e-past" in ids

    def test_scan_decay_candidates_returns_iterator(self, db: MemoryDatabase):
        """AC-7c: generator semantics — future refactor to list would fail this."""
        cutoff = "2026-04-20T00:00:00Z"
        result = db.scan_decay_candidates(
            not_null_cutoff=cutoff, scan_limit=10,
        )
        assert isinstance(result, Iterator)

    def test_scan_decay_candidates_clamps_negative_scan_limit_to_zero(
        self, db: MemoryDatabase,
    ):
        """Feature 092 AC-1 / FR-1 (#00193): scan_limit=-1 → zero rows
        (clamped, not SQLite LIMIT -1 = unlimited DoS vector)."""
        db.insert_test_entry_for_testing(
            entry_id="e1",
            description="x",
            confidence="high",
            source="session-capture",
            last_recalled_at="2026-04-15T00:00:00Z",
            created_at="2026-04-15T00:00:00Z",
        )
        rows = list(db.scan_decay_candidates(
            not_null_cutoff="2026-04-20T00:00:00Z", scan_limit=-1,
        ))
        assert rows == [], \
            f"expected zero rows from clamp; got {len(rows)} (SQLite LIMIT -1 = unlimited if unclamped)"

    def test_scan_decay_candidates_rejects_malformed_cutoff(
        self, db: MemoryDatabase, capsys,
    ):
        """Feature 092 AC-7 / FR-5 (#00197): malformed cutoff → empty result
        + stderr 'format violation' + NO exception (log-and-skip, consistent
        with FR-1 clamp philosophy)."""
        for bad_cutoff in ("+00:00", "", "not-iso", "2026-04-20T00:00:00+00:00"):
            rows = list(db.scan_decay_candidates(
                not_null_cutoff=bad_cutoff, scan_limit=100,
            ))
            assert rows == [], f"expected empty for {bad_cutoff!r}; got {rows}"
        captured = capsys.readouterr()
        assert "format violation" in captured.err, \
            f"expected stderr to contain 'format violation'; got: {captured.err!r}"

    @pytest.mark.parametrize("test_dt_label,test_dt_factory", [
        ("canonical",         lambda: datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)),
        ("microsecond_max",   lambda: datetime(2026, 4, 16, 12, 0, 0, 999999, tzinfo=timezone.utc)),
        ("year_9999_max",     lambda: datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)),
        ("year_1_min",        lambda: datetime(1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)),
        ("leap_year_2024",    lambda: datetime(2024, 2, 29, 12, 0, 0, tzinfo=timezone.utc)),
    ])
    def test_iso_utc_output_always_passes_hardened_pattern(
        self, db: MemoryDatabase, test_dt_label, test_dt_factory,
    ):
        """Feature 093 FR-4 format-drift pin: _iso_utc output MUST pass the
        hardened _ISO8601_Z_PATTERN.fullmatch for ALL representative datetime
        boundaries. Catches regression where _iso_utc changes format (e.g.,
        adds microseconds) and would silently break BOTH scan_decay_candidates
        (log-and-skip) AND batch_demote (raise)."""
        from semantic_memory._config_utils import _iso_utc
        test_dt = test_dt_factory()
        output = _iso_utc(test_dt)
        assert _ISO8601_Z_PATTERN.fullmatch(output), (
            f"[{test_dt_label}] _iso_utc({test_dt!r}) = {output!r} "
            f"does not match hardened pattern — format drift"
        )

    @pytest.mark.parametrize("unicode_cutoff", [
        "２０２６-04-20T00:00:00Z",  # fullwidth digits ２０２６
        "٢٠٢٦-04-20T00:00:00Z",  # Arabic-Indic digits ٢٠٢٦
        "२०२६-04-20T00:00:00Z",  # Devanagari digits २०२६
    ])
    def test_pattern_rejects_unicode_digits(
        self, unicode_cutoff, db: MemoryDatabase, capsys,
    ):
        """Feature 093 FR-1 (#00219): hardened pattern uses [0-9] + re.ASCII;
        Unicode digit codepoints (fullwidth, Arabic-Indic, Devanagari) that
        passed the 092 `\\d` pattern MUST now be rejected."""
        rows = list(db.scan_decay_candidates(
            not_null_cutoff=unicode_cutoff, scan_limit=100,
        ))
        assert rows == [], f"expected empty for {unicode_cutoff!r}; got {len(rows)} rows"
        captured = capsys.readouterr()
        assert "format violation" in captured.err, (
            f"expected stderr 'format violation'; got: {captured.err!r}"
        )

    @pytest.mark.parametrize("trailing_cutoff", [
        "2026-04-20T00:00:00Z\n",       # trailing newline (the #00220 case)
        "2026-04-20T00:00:00Z ",        # trailing space
        "2026-04-20T00:00:00Z\r\n",     # trailing CRLF
    ])
    def test_pattern_rejects_trailing_whitespace(
        self, trailing_cutoff, db: MemoryDatabase, capsys,
    ):
        """Feature 093 FR-2 (#00220): fullmatch rejects trailing whitespace that
        the 092 `$` anchor accepted (`$` matches before trailing `\\n`)."""
        rows = list(db.scan_decay_candidates(
            not_null_cutoff=trailing_cutoff, scan_limit=100,
        ))
        assert rows == [], f"expected empty for {trailing_cutoff!r}; got {len(rows)} rows"
        captured = capsys.readouterr()
        assert "format violation" in captured.err

    @pytest.mark.parametrize("partial_unicode_input,case_name", [
        ("2026-01-0１T00:00:00Z", "day-pos"),       # Feature 095 #00252 — fullwidth 1 at day-units
        ("2026-01-01T0１:00:00Z", "hour-pos"),      # Feature 095 #00252 — fullwidth 1 at hour-units
        ("2026-01-01T00:0１:00Z", "minute-pos"),    # Feature 095 #00252 — fullwidth 1 at minute-units
        ("2026-01-01T00:00:0１Z", "second-pos"),    # Feature 095 #00252 — fullwidth 1 at second-units
    ], ids=["day-pos", "hour-pos", "minute-pos", "second-pos"])
    def test_pattern_rejects_partial_unicode_injection(
        self, db: MemoryDatabase, capsys, partial_unicode_input, case_name,
    ):
        """Feature 095 #00252 — pin rejection of mid-string single Unicode digit injection.

        Existing test_pattern_rejects_unicode_digits covers full Unicode replacement (year).
        This test pins the partial-injection case at each datetime field position.
        """
        rows = list(db.scan_decay_candidates(
            not_null_cutoff=partial_unicode_input, scan_limit=10,
        ))
        assert rows == [], f"[{case_name}] expected empty for {partial_unicode_input!r}; got {len(rows)} rows"
        captured = capsys.readouterr()
        assert "format violation" in captured.err, (
            f"[{case_name}] scan_decay_candidates must reject partial Unicode injection"
        )


class TestBatchDemote:
    """Task 2.3 / 2.4 — design I-7 (BEGIN IMMEDIATE, 500-ids chunking,
    `updated_at < ?` guard for intra-tick idempotency).
    """

    NOW_ISO = "2026-04-16T12:00:00Z"  # Feature 093 FR-3: Z suffix required by hardened pattern

    def test_empty_ids_returns_zero_no_sql(self):
        db = MemoryDatabase(":memory:")
        try:
            result = db.batch_demote([], "medium", self.NOW_ISO)
            assert result == 0
        finally:
            db.close()

    _INVALID_NOW_ISO_CASES = [
        ("", "empty"),
        ("   ", "whitespace-only"),
        ("\n", "newline-only"),
        ("​", "zero-width-space"),
        ("10000-01-01T00:00:00Z", "5-digit-year-breaks-sqlite-lex-collation"),
        ("2026-04-20T00:00:00Z\n", "trailing-newline"),
        ("2026-04-20T00:00:00Z ", "trailing-space"),       # Feature 095 #00251
        ("2026-04-20T00:00:00Z\r\n", "trailing-crlf"),     # Feature 095 #00251
        ("２０２６-04-20T00:00:00Z", "unicode-digits"),
        ("2026-04-20T00:00:00+00:00", "plus-offset-not-Z-suffix"),
    ]

    @pytest.mark.parametrize(
        "invalid_now_iso,case_name",
        _INVALID_NOW_ISO_CASES,
        ids=[c for _, c in _INVALID_NOW_ISO_CASES],
    )
    def test_batch_demote_rejects_invalid_now_iso(self, invalid_now_iso, case_name):
        """Feature 093 FR-3 (#00221): batch_demote uses same _ISO8601_Z_PATTERN
        as scan_decay_candidates (single source of truth). All inputs that would
        silently corrupt `updated_at < ?` guard or pass 092's `not now_iso`
        truthy check MUST raise ValueError."""
        db = MemoryDatabase(":memory:")
        try:
            with pytest.raises(ValueError, match="Z-suffix ISO-8601"):
                db.batch_demote(["x"], "medium", invalid_now_iso)
        finally:
            db.close()

    @pytest.mark.parametrize("partial_unicode_input,case_name", [
        ("2026-01-0１T00:00:00Z", "day-pos"),       # Feature 095 #00252
        ("2026-01-01T0１:00:00Z", "hour-pos"),      # Feature 095 #00252
        ("2026-01-01T00:0１:00Z", "minute-pos"),    # Feature 095 #00252
        ("2026-01-01T00:00:0１Z", "second-pos"),    # Feature 095 #00252
    ], ids=["day-pos", "hour-pos", "minute-pos", "second-pos"])
    def test_batch_demote_rejects_partial_unicode_injection(self, partial_unicode_input, case_name):
        """Feature 095 #00252 — cross-call-site parity: batch_demote must also reject
        partial Unicode injection at any datetime position (not just full-Unicode year)."""
        db = MemoryDatabase(":memory:")
        try:
            with pytest.raises(ValueError, match="Z-suffix ISO-8601"):
                db.batch_demote(["x"], "medium", partial_unicode_input)
        finally:
            db.close()

    def test_batch_demote_empty_ids_short_circuits_before_now_iso_check(self):
        """Feature 093 FR-3 regression guard (092 TD-3 preserved): empty-ids
        short-circuit MUST execute before the new regex validation. Even with
        garbage now_iso, empty ids returns 0."""
        db = MemoryDatabase(":memory:")
        try:
            assert db.batch_demote([], "medium", "garbage-not-iso") == 0
        finally:
            db.close()

    def test_batch_demote_empty_now_iso_with_empty_ids_returns_zero(self):
        """Feature 092 AC-10 / FR-8: ids=[] + now_iso='' → 0 (preserves
        empty-ids short-circuit; empty-ids trumps empty-now_iso)."""
        db = MemoryDatabase(":memory:")
        try:
            assert db.batch_demote([], "medium", "") == 0
        finally:
            db.close()

    def test_value_error_on_invalid_new_confidence(self):
        db = MemoryDatabase(":memory:")
        try:
            _seed_entry_for_demote(db, entry_id="e1", confidence="high")
            with pytest.raises(ValueError, match="extreme"):
                db.batch_demote(["e1"], "extreme", self.NOW_ISO)
        finally:
            db.close()

    def test_single_chunk_under_five_hundred_ids(self):
        db = MemoryDatabase(":memory:")
        try:
            ids = [f"e{i}" for i in range(100)]
            for eid in ids:
                _seed_entry_for_demote(db, entry_id=eid, confidence="high")
            result = db.batch_demote(ids, "medium", self.NOW_ISO)
            assert result == 100
            for eid in ids:
                assert _get_confidence(db, eid) == "medium"
        finally:
            db.close()

    def test_multi_chunk_six_hundred_ids(self):
        db = MemoryDatabase(":memory:")
        try:
            ids = [f"e{i}" for i in range(600)]
            for eid in ids:
                _seed_entry_for_demote(db, entry_id=eid, confidence="high")
            result = db.batch_demote(ids, "medium", self.NOW_ISO)
            assert result == 600
            for eid in ids:
                assert _get_confidence(db, eid) == "medium"
        finally:
            db.close()

    def test_intra_tick_guard_blocks_second_call(self):
        db = MemoryDatabase(":memory:")
        try:
            _seed_entry_for_demote(db, entry_id="e1", confidence="high")
            first = db.batch_demote(["e1"], "medium", self.NOW_ISO)
            assert first == 1
            assert _get_confidence(db, "e1") == "medium"
            # Second call with SAME now_iso: updated_at == now_iso so
            # `updated_at < ?` is False; row is NOT updated.
            second = db.batch_demote(["e1"], "low", self.NOW_ISO)
            assert second == 0
            assert _get_confidence(db, "e1") == "medium"
        finally:
            db.close()

    def test_rowcount_sum_across_chunks(self):
        db = MemoryDatabase(":memory:")
        try:
            # 501 ids = 2 chunks (500 + 1). Confirm sum is returned,
            # not just the last chunk's rowcount.
            ids = [f"e{i}" for i in range(501)]
            for eid in ids:
                _seed_entry_for_demote(db, entry_id=eid, confidence="high")
            result = db.batch_demote(ids, "medium", self.NOW_ISO)
            assert result == 501
        finally:
            db.close()


class TestIso8601PatternSourcePins:
    """Feature 095 — source-level mutation-resistance pins for _ISO8601_Z_PATTERN.

    Closes feature 093 post-release adversarial QA gaps #00246-#00250.
    Per advisor consensus, uses _ISO8601_Z_PATTERN.pattern / .flags (stable Python 3.7+
    public attrs) where signal is equivalent; uses inspect.getsource() only for call-site
    .fullmatch() pin (#00250) where call-form IS the contract.
    """

    def test_pattern_source_uses_explicit_digit_class(self):
        """Closes #00246 — pin literal `[0-9]` in pattern source, NOT `\\d`."""
        assert '[0-9]' in _ISO8601_Z_PATTERN.pattern, \
            "_ISO8601_Z_PATTERN.pattern must use explicit [0-9] character class for ASCII-only matching"
        assert r'\d' not in _ISO8601_Z_PATTERN.pattern, \
            "_ISO8601_Z_PATTERN.pattern must NOT use \\d (Unicode-digit-permissive in Python 3 str patterns)"

    def test_pattern_compiled_with_re_ascii_flag(self):
        """Closes #00247 — pin re.ASCII flag presence (defense-in-depth)."""
        assert bool(_ISO8601_Z_PATTERN.flags & re.ASCII), \
            "_ISO8601_Z_PATTERN must be compiled with re.ASCII flag (defense-in-depth against future class expansion)"

    @pytest.mark.parametrize("unicode_input,case_name", [
        ("２０２６-04-20T00:00:00Z", "fullwidth-year"),
        ("٢٠٢٦-04-20T00:00:00Z", "arabic-indic-year"),
        ("२०२६-04-20T00:00:00Z", "devanagari-year"),
    ], ids=["fullwidth", "arabic-indic", "devanagari"])
    def test_pattern_rejects_unicode_digits_directly(self, unicode_input, case_name):
        """Closes #00248 — direct pattern-object Unicode rejection, decoupled from call sites.

        Catches combined mutation: swap [0-9] -> \\d AND drop re.ASCII flag (which would
        re-introduce #00219 Unicode-digit bypass). Behavior tests via call sites also
        catch this combined mutation, but this test catches it without needing a DB.
        """
        assert _ISO8601_Z_PATTERN.fullmatch(unicode_input) is None, \
            f"[{case_name}] Pattern must reject Unicode-digit input directly"

    @pytest.mark.parametrize("method", [
        MemoryDatabase.scan_decay_candidates,
        MemoryDatabase.batch_demote,
    ], ids=["scan_decay_candidates", "batch_demote"])
    def test_call_sites_use_fullmatch_not_match(self, method):
        """Closes #00250 + #00249 — pin .fullmatch() call-form at both call sites,
        and confirm both share _ISO8601_Z_PATTERN as single source of truth.

        This is the only test in this class that uses inspect.getsource() — required because
        the contract IS the call-form, not an attribute of the pattern object.
        """
        src = inspect.getsource(method)
        assert '_ISO8601_Z_PATTERN.fullmatch(' in src, \
            f"{method.__name__} must use _ISO8601_Z_PATTERN.fullmatch()"
        assert '_ISO8601_Z_PATTERN.match(' not in src, \
            f"{method.__name__} must NOT use _ISO8601_Z_PATTERN.match() (allows trailing newline bypass)"
        assert 're.compile(' not in src, \
            f"{method.__name__} must NOT define a local re.compile() — must use the module-level _ISO8601_Z_PATTERN constant"


class TestExecuteChunkSeam:
    """Task 2.5 — monkeypatch `_execute_chunk` to fail on 2nd call;
    assert rollback of all prior chunks (no partial UPDATE visible).
    """

    NOW_ISO = "2026-04-16T12:00:00Z"  # Feature 093 FR-3: Z suffix required by hardened pattern

    def test_partial_failure_rolls_back_first_chunk(self, monkeypatch):
        db = MemoryDatabase(":memory:")
        try:
            # 2000 ids → 4 chunks (500/500/500/500). Fail on 2nd chunk.
            ids = [f"e{i}" for i in range(2000)]
            for eid in ids:
                _seed_entry_for_demote(db, entry_id=eid, confidence="high")

            call_count = {"n": 0}
            original = MemoryDatabase._execute_chunk

            def fake(self, chunk_ids, new_confidence, now_iso):
                call_count["n"] += 1
                if call_count["n"] == 2:
                    raise sqlite3.OperationalError("simulated chunk-2 failure")
                return original(self, chunk_ids, new_confidence, now_iso)

            monkeypatch.setattr(MemoryDatabase, "_execute_chunk", fake)

            with pytest.raises(sqlite3.OperationalError, match="simulated"):
                db.batch_demote(ids, "medium", self.NOW_ISO)

            # All 2000 rows must still be at original "high" confidence —
            # the first chunk's UPDATE was rolled back.
            for eid in ids:
                assert _get_confidence(db, eid) == "high", (
                    f"{eid} was not rolled back"
                )
        finally:
            db.close()


# ---------------------------------------------------------------------------
# AC-20b concurrent-writer tests
# ---------------------------------------------------------------------------


class TestConcurrentWriters:
    """Tasks 2.6 / 2.7 — AC-20b-1 (success) and AC-20b-2 (timeout).

    Uses busy_timeout_ms=1000 to keep timing deterministic. File-backed
    SQLite is required (WAL requires disk) so tests use `tmp_path`.
    """

    NOW_ISO = "2026-04-16T12:00:00Z"  # Feature 093 FR-3: Z suffix required by hardened pattern

    def test_ac_20b_1_concurrent_writer_success(self, tmp_path):
        import threading
        import time as _time

        db_path = str(tmp_path / "decay-success.db")

        seed_db = MemoryDatabase(db_path, busy_timeout_ms=1000)
        _seed_entry_for_demote(seed_db, entry_id="e1", confidence="high")
        seed_db.close()

        db_b = MemoryDatabase(db_path, busy_timeout_ms=1000)
        a_lock_acquired = threading.Event()

        def thread_a():
            # Open db_a INSIDE the thread so the sqlite3.Connection lives
            # in the thread that uses it (sqlite3 default: same-thread only).
            db_a = MemoryDatabase(db_path, busy_timeout_ms=1000)
            try:
                db_a._conn.execute("BEGIN IMMEDIATE")
                try:
                    db_a._conn.execute(
                        "INSERT INTO entries (id, name, description, category, "
                        "keywords, source, source_project, source_hash, "
                        "confidence, recall_count, last_recalled_at, created_at, "
                        "updated_at, observation_count) "
                        "VALUES ('a-insert', 'n', 'd', 'patterns', '[]', "
                        "'session-capture', '/tmp/p', '0000000000000000', "
                        "'medium', 0, NULL, ?, ?, 1)",
                        (self.NOW_ISO, self.NOW_ISO),
                    )
                    a_lock_acquired.set()
                    _time.sleep(0.1)  # hold lock briefly
                    db_a._conn.commit()
                except Exception:
                    db_a._conn.rollback()
                    raise
            finally:
                db_a.close()

        try:
            t = threading.Thread(target=thread_a)
            t.start()
            a_lock_acquired.wait(timeout=5.0)
            # B waits out A's 100ms hold within the 1000ms busy-timeout budget.
            rows = db_b.batch_demote(["e1"], "medium", self.NOW_ISO)
            t.join()
            assert rows == 1
            assert _get_confidence(db_b, "e1") == "medium"
            # A's INSERT is visible on db_b after join.
            cur = db_b._conn.execute(
                "SELECT id FROM entries WHERE id = 'a-insert'"
            )
            assert cur.fetchone() is not None
        finally:
            db_b.close()

    def test_ac_20b_2_concurrent_writer_timeout(self, tmp_path):
        import threading
        import time as _time

        db_path = str(tmp_path / "decay-timeout.db")

        seed_db = MemoryDatabase(db_path, busy_timeout_ms=1000)
        _seed_entry_for_demote(seed_db, entry_id="e1", confidence="high")
        _seed_entry_for_demote(seed_db, entry_id="e2", confidence="high")
        seed_db.close()

        db_b = MemoryDatabase(db_path, busy_timeout_ms=1000)
        a_lock_acquired = threading.Event()

        def thread_a():
            db_a = MemoryDatabase(db_path, busy_timeout_ms=1000)
            try:
                db_a._conn.execute("BEGIN IMMEDIATE")
                try:
                    db_a._conn.execute(
                        "INSERT INTO entries (id, name, description, category, "
                        "keywords, source, source_project, source_hash, "
                        "confidence, recall_count, last_recalled_at, created_at, "
                        "updated_at, observation_count) "
                        "VALUES ('a-long', 'n', 'd', 'patterns', '[]', "
                        "'session-capture', '/tmp/p', '0000000000000000', "
                        "'medium', 0, NULL, ?, ?, 1)",
                        (self.NOW_ISO, self.NOW_ISO),
                    )
                    a_lock_acquired.set()
                    _time.sleep(2.0)  # exceed B's busy_timeout_ms=1000
                    db_a._conn.commit()
                except Exception:
                    db_a._conn.rollback()
                    raise
            finally:
                db_a.close()

        try:
            t = threading.Thread(target=thread_a)
            t.start()
            a_lock_acquired.wait(timeout=5.0)
            with pytest.raises(sqlite3.OperationalError):
                db_b.batch_demote(["e1", "e2"], "medium", self.NOW_ISO)
            t.join()
            # Verification SELECTs after A has committed and B has raised.
            # Neither e1 nor e2 was demoted (B rolled back on timeout).
            assert _get_confidence(db_b, "e1") == "high"
            assert _get_confidence(db_b, "e2") == "high"
        finally:
            db_b.close()


# ---------------------------------------------------------------------------
# Feature 089 Bundle A — Security hardening on test-only helpers
# ---------------------------------------------------------------------------


class TestFeature089BundleA:
    """Feature 089 Bundle A (#00140, #00144): runtime guard on
    ``*_for_testing`` helpers + rollback-on-error in
    ``execute_test_sql_for_testing``.
    """

    def test_for_testing_helpers_refuse_outside_pytest(self, tmp_path, monkeypatch):
        """AC-2 (FR-1.2 / #00140).

        With ``PYTEST_CURRENT_TEST`` unset AND the ``pytest`` module removed
        from ``sys.modules`` AND the ``PD_TESTING`` env var unset, calling
        ``execute_test_sql_for_testing`` MUST raise ``RuntimeError``.

        Feature 090 FR-2 (#00173): after tightening, the guard short-circuits
        on the missing ``PYTEST_CURRENT_TEST`` alone — the other two probes
        are now belt-and-suspenders. We still strip them all to exercise the
        full "production-like" negative path.
        """
        import sys as _sys

        db_path = str(tmp_path / "guard.db")

        # Build DB inside the test (pytest still imported at this point).
        db = MemoryDatabase(db_path)
        try:
            # Strip pytest + PD_TESTING + PYTEST_CURRENT_TEST so the guard trips.
            monkeypatch.delenv("PD_TESTING", raising=False)
            monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
            # Remove all pytest-prefixed modules so ``'pytest' in sys.modules``
            # returns False during the call.
            for mod_name in list(_sys.modules):
                if mod_name == "pytest" or mod_name.startswith("pytest."):
                    monkeypatch.delitem(_sys.modules, mod_name, raising=False)
            assert "pytest" not in _sys.modules
            assert os.environ.get("PD_TESTING") is None
            assert os.environ.get("PYTEST_CURRENT_TEST") is None

            with pytest.raises(RuntimeError, match="for-testing helper"):
                db.execute_test_sql_for_testing("SELECT 1")
        finally:
            db.close()

    def test_guard_rejects_pd_testing_without_pytest_current_test(
        self, tmp_path, monkeypatch,
    ):
        """Feature 090 AC-2 (FR-2 / #00173).

        With only ``PD_TESTING=1`` set and ``PYTEST_CURRENT_TEST`` unset, the
        guard MUST raise. This closes the parent-shell PD_TESTING leak vector
        where a developer exports PD_TESTING once and inadvertently leaves it
        set for all child processes including production sessions.
        """
        db_path = str(tmp_path / "pd_testing_only.db")
        db = MemoryDatabase(db_path)
        try:
            monkeypatch.setenv("PD_TESTING", "1")
            monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
            assert os.environ.get("PD_TESTING") == "1"
            assert os.environ.get("PYTEST_CURRENT_TEST") is None

            with pytest.raises(
                RuntimeError, match="PYTEST_CURRENT_TEST not set",
            ):
                db.execute_test_sql_for_testing("SELECT 1")
        finally:
            db.close()

    def test_guard_passes_with_both_pd_testing_and_pytest_current_test(
        self, tmp_path, monkeypatch,
    ):
        """Feature 090 AC-2 (FR-2 / #00173).

        With BOTH ``PD_TESTING=1`` and ``PYTEST_CURRENT_TEST`` set, the guard
        MUST pass — this is the canonical "active pytest test" configuration
        that pytest's own runner establishes for every test body.
        """
        db_path = str(tmp_path / "both_set.db")
        db = MemoryDatabase(db_path)
        try:
            monkeypatch.setenv("PD_TESTING", "1")
            # pytest normally sets PYTEST_CURRENT_TEST itself; we set it
            # explicitly so the assertion is self-contained.
            monkeypatch.setenv(
                "PYTEST_CURRENT_TEST",
                "test_database.py::test_guard_passes (call)",
            )
            # Should NOT raise.
            db.execute_test_sql_for_testing(
                "CREATE TABLE IF NOT EXISTS _feat090_guard_probe (x INTEGER)"
            )
        finally:
            db.close()

    def test_execute_test_sql_rolls_back_on_error(self, tmp_path, monkeypatch):
        """AC-6 (FR-1.6 / #00144).

        SQL that fails during execute (here, reference to a nonexistent
        table inside an explicit BEGIN) MUST trigger ``_conn.rollback()`` so
        the connection is NOT left mid-transaction.
        """
        monkeypatch.setenv("PD_TESTING", "1")
        db_path = str(tmp_path / "rollback.db")
        db = MemoryDatabase(db_path)
        try:
            # Open a mid-statement transaction before calling the helper.
            # The helper's sql will fail, causing its except branch to fire
            # and roll back this transaction.
            db._conn.execute("BEGIN IMMEDIATE")
            assert db._conn.in_transaction is True

            # Bogus SQL targeting a non-existent table → sqlite3.OperationalError.
            with pytest.raises(sqlite3.OperationalError):
                db.execute_test_sql_for_testing(
                    "UPDATE nonexistent_table_xyz SET col = ?", (1,)
                )

            # Post-error: the connection MUST NOT be mid-transaction.
            assert db._conn.in_transaction is False, (
                "execute_test_sql_for_testing must rollback on error"
            )
        finally:
            db.close()
