"""Tests for semantic_memory.database module."""
from __future__ import annotations

import hashlib
import json
import struct
import sqlite3

import numpy as np
import pytest

from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query


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
        assert db.get_schema_version() == 4

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
        still result in schema_version == 4 (migrations are idempotent)."""
        db1 = MemoryDatabase(":memory:")
        assert db1.get_schema_version() == 4
        db1.close()

    def test_schema_version_persists(self, tmp_path):
        """Schema version survives close and reopen."""
        db_path = str(tmp_path / "test.db")
        db1 = MemoryDatabase(db_path)
        assert db1.get_schema_version() == 4
        db1.close()

        db2 = MemoryDatabase(db_path)
        assert db2.get_schema_version() == 4
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
        assert db.get_schema_version() == 4

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
            ("e-createtasks", "Task creation with create-tasks",
             "Use create-tasks workflow for structured task generation",
             "heuristics", '["create-tasks", "workflow"]'),
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
        results = db.fts5_search("create-tasks git-flow")
        ids = [r[0] for r in results]
        assert "e-createtasks" in ids
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
        assert db.get_schema_version() == 4

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
        assert db1.get_schema_version() == 4
        db1.close()

        db2 = MemoryDatabase(db_path)
        assert db2.get_schema_version() == 4
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
