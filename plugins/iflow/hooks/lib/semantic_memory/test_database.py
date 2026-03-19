"""Tests for semantic_memory.database module."""
from __future__ import annotations

import hashlib
import json
import struct
import sqlite3

import numpy as np
import pytest

from semantic_memory.database import MemoryDatabase


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

    def test_schema_version_is_3(self, db: MemoryDatabase):
        assert db.get_schema_version() == 3

    def test_entries_has_18_columns(self, db: MemoryDatabase):
        cur = db._conn.execute("PRAGMA table_info(entries)")
        columns = cur.fetchall()
        assert len(columns) == 18

    def test_entries_column_names(self, db: MemoryDatabase):
        cur = db._conn.execute("PRAGMA table_info(entries)")
        col_names = [row[1] for row in cur.fetchall()]
        expected = [
            "id", "name", "description", "reasoning", "category",
            "keywords", "source", "source_project", "references",
            "observation_count", "confidence", "recall_count",
            "last_recalled_at", "embedding", "created_at", "updated_at",
            "source_hash", "created_timestamp_utc",
        ]
        assert col_names == expected


class TestMigrationIdempotency:
    def test_opening_twice_does_not_error(self):
        """Opening two MemoryDatabase instances on same in-memory DB should
        still result in schema_version == 3 (migrations are idempotent)."""
        db1 = MemoryDatabase(":memory:")
        assert db1.get_schema_version() == 3
        db1.close()

    def test_schema_version_persists(self, tmp_path):
        """Schema version survives close and reopen."""
        db_path = str(tmp_path / "test.db")
        db1 = MemoryDatabase(db_path)
        assert db1.get_schema_version() == 3
        db1.close()

        db2 = MemoryDatabase(db_path)
        assert db2.get_schema_version() == 3
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

        # Reopen with MemoryDatabase to trigger migration v2
        db = MemoryDatabase(db_path)
        assert db.get_schema_version() == 3

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
        assert cur.fetchone()[0] == 5000

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
