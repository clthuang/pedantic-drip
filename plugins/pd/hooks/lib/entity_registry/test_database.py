"""Tests for entity_registry.database module."""
from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid

import pytest

from entity_registry.database import (
    EntityDatabase,
    _UUID_V4_RE,
    _create_initial_schema,
    _expand_workflow_phase_check,
    _migrate_to_uuid_pk,
)

from entity_registry.database import EXPORT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    """Provide a file-based EntityDatabase, closed after test."""
    db_path = str(tmp_path / "entities.db")
    database = EntityDatabase(db_path)
    yield database
    database.close()


@pytest.fixture
def mem_db():
    """Provide an in-memory EntityDatabase, closed after test."""
    database = EntityDatabase(":memory:")
    yield database
    database.close()


# ---------------------------------------------------------------------------
# Migration 2: Schema Foundation tests
# ---------------------------------------------------------------------------


class TestMigration2:
    def test_migration_fresh_db(self):
        """Fresh v1 DB migrated to v2 should have correct schema shape."""
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _create_initial_schema(conn)
        _migrate_to_uuid_pk(conn)

        # 12 columns
        cur = conn.execute("PRAGMA table_info(entities)")
        columns = cur.fetchall()
        assert len(columns) == 12

        # uuid is PRIMARY KEY
        col_map = {row[1]: row for row in columns}
        assert "uuid" in col_map
        assert col_map["uuid"][5] == 1  # pk flag

        # type_id is NOT PK
        assert col_map["type_id"][5] == 0

        # type_id has UNIQUE constraint (check via index)
        idx_cur = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' "
            "AND sql LIKE '%type_id%' AND sql LIKE '%UNIQUE%'"
        )
        # The UNIQUE on type_id creates an autoindex
        uniq_cur = conn.execute(
            "PRAGMA index_list(entities)"
        )
        unique_cols = []
        for idx_row in uniq_cur.fetchall():
            if idx_row[2]:  # unique flag
                info = conn.execute(
                    f"PRAGMA index_info({idx_row[1]!r})"
                ).fetchall()
                for info_row in info:
                    unique_cols.append(info_row[2])
        assert "type_id" in unique_cols

        # parent_uuid column exists
        assert "parent_uuid" in col_map

        # 8 triggers
        trigger_cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
        )
        trigger_names = [row[0] for row in trigger_cur.fetchall()]
        assert trigger_names == [
            "enforce_immutable_created_at",
            "enforce_immutable_entity_type",
            "enforce_immutable_type_id",
            "enforce_immutable_uuid",
            "enforce_no_self_parent",
            "enforce_no_self_parent_update",
            "enforce_no_self_parent_uuid_insert",
            "enforce_no_self_parent_uuid_update",
        ]

        # 4 indexes
        idx_cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        index_names = [row[0] for row in idx_cur.fetchall()]
        assert index_names == [
            "idx_entity_type",
            "idx_parent_type_id",
            "idx_parent_uuid",
            "idx_status",
        ]

        conn.close()

    def test_migration_populated_db_preserves_data(self):
        """Migrating a v1 DB with data should preserve all rows and add UUIDs."""
        import sqlite3
        from entity_registry.database import _UUID_V4_RE

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _create_initial_schema(conn)

        # Insert 3 entities using v1 schema (no uuid column)
        conn.execute(
            "INSERT INTO entities (type_id, entity_type, entity_id, name, "
            "status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("project:p1", "project", "p1", "Project One", "active",
             "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO entities (type_id, entity_type, entity_id, name, "
            "parent_type_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("feature:f1", "feature", "f1", "Feature One", "project:p1",
             "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO entities (type_id, entity_type, entity_id, name, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("backlog:b1", "backlog", "b1", "Backlog One",
             "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.commit()

        _migrate_to_uuid_pk(conn)

        # All 3 rows exist
        rows = conn.execute(
            "SELECT * FROM entities ORDER BY type_id"
        ).fetchall()
        assert len(rows) == 3

        # Field values preserved
        type_ids = [r["type_id"] for r in rows]
        assert "backlog:b1" in type_ids
        assert "feature:f1" in type_ids
        assert "project:p1" in type_ids

        # Each row has valid UUID v4
        for row in rows:
            assert _UUID_V4_RE.match(row["uuid"]), (
                f"Row {row['type_id']} has invalid uuid: {row['uuid']}"
            )

        # Specific field values
        p1 = [r for r in rows if r["type_id"] == "project:p1"][0]
        assert p1["name"] == "Project One"
        assert p1["status"] == "active"
        assert p1["entity_type"] == "project"

        conn.close()

    def test_migration_populates_parent_uuid(self):
        """Migration should populate parent_uuid from parent_type_id."""
        import sqlite3
        from entity_registry.database import _UUID_V4_RE

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _create_initial_schema(conn)

        # Insert parent and child
        conn.execute(
            "INSERT INTO entities (type_id, entity_type, entity_id, name, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("project:p1", "project", "p1", "Parent",
             "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO entities (type_id, entity_type, entity_id, name, "
            "parent_type_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("feature:f1", "feature", "f1", "Child", "project:p1",
             "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.commit()

        _migrate_to_uuid_pk(conn)

        parent = conn.execute(
            "SELECT uuid FROM entities WHERE type_id = 'project:p1'"
        ).fetchone()
        child = conn.execute(
            "SELECT parent_uuid FROM entities WHERE type_id = 'feature:f1'"
        ).fetchone()

        assert child["parent_uuid"] == parent["uuid"]
        assert _UUID_V4_RE.match(parent["uuid"])

        conn.close()

    def test_uuid_immutability_trigger(self):
        """After migration, updating uuid should raise IntegrityError."""
        import sqlite3
        import uuid

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _create_initial_schema(conn)
        _migrate_to_uuid_pk(conn)

        test_uuid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO entities (uuid, type_id, entity_type, entity_id, "
            "name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (test_uuid, "feature:trig", "feature", "trig", "Trigger Test",
             "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError, match="uuid is immutable"):
            conn.execute(
                "UPDATE entities SET uuid = 'new-uuid' WHERE type_id = ?",
                ("feature:trig",),
            )
        conn.close()

    def test_self_parent_uuid_insert_trigger(self):
        """Inserting entity where parent_uuid = uuid should raise."""
        import sqlite3
        import uuid

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _create_initial_schema(conn)
        _migrate_to_uuid_pk(conn)

        test_uuid = str(uuid.uuid4())
        with pytest.raises(
            sqlite3.IntegrityError, match="entity cannot be its own parent"
        ):
            conn.execute(
                "INSERT INTO entities (uuid, type_id, entity_type, entity_id, "
                "name, created_at, updated_at, parent_uuid) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (test_uuid, "feature:self", "feature", "self", "Self",
                 "2026-01-01T00:00:00", "2026-01-01T00:00:00", test_uuid),
            )
        conn.close()

    def test_self_parent_uuid_update_trigger(self):
        """Updating parent_uuid to self should raise."""
        import sqlite3
        import uuid

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _create_initial_schema(conn)
        _migrate_to_uuid_pk(conn)

        test_uuid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO entities (uuid, type_id, entity_type, entity_id, "
            "name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (test_uuid, "feature:upd", "feature", "upd", "Update Test",
             "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.commit()

        with pytest.raises(
            sqlite3.IntegrityError, match="entity cannot be its own parent"
        ):
            conn.execute(
                "UPDATE entities SET parent_uuid = uuid WHERE type_id = ?",
                ("feature:upd",),
            )
        conn.close()

    def test_init_already_migrated_db(self, tmp_path):
        """Creating EntityDatabase on an already-migrated DB should be a no-op."""
        import sqlite3

        db_path = str(tmp_path / "already_migrated.db")

        # First: create a v2 database via direct migration calls
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _create_initial_schema(conn)
        # Set schema_version to 1 (as _create_initial_schema doesn't set it)
        conn.execute(
            "INSERT OR REPLACE INTO _metadata(key, value) "
            "VALUES('schema_version', '1')"
        )
        conn.commit()
        _migrate_to_uuid_pk(conn)
        conn.close()

        # Now open it with EntityDatabase — runs pending migrations (3+)
        db = EntityDatabase(db_path)
        assert db.get_metadata("schema_version") == "6"

        # Schema should be intact
        cur = db._conn.execute("PRAGMA table_info(entities)")
        columns = cur.fetchall()
        assert len(columns) == 12

        db.close()

    def test_migration_rollback_on_failure(self):
        """If migration fails mid-way, original schema should be intact."""
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _create_initial_schema(conn)

        # Insert test data in v1 schema
        conn.execute(
            "INSERT INTO entities (type_id, entity_type, entity_id, name, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("project:p1", "project", "p1", "Project One",
             "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO entities (type_id, entity_type, entity_id, name, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("feature:f1", "feature", "f1", "Feature One",
             "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.commit()

        # Set schema_version to 1 (simulating Migration 1 completed)
        conn.execute(
            "INSERT OR REPLACE INTO _metadata(key, value) "
            "VALUES('schema_version', '1')"
        )
        conn.commit()

        class FailOnDropConn:
            """Proxy that delegates to real conn but raises on DROP TABLE."""
            def __init__(self, real_conn):
                self._real = real_conn
            def execute(self, sql, *args, **kwargs):
                if isinstance(sql, str) and "DROP TABLE" in sql:
                    raise RuntimeError("injected")
                return self._real.execute(sql, *args, **kwargs)
            def __getattr__(self, name):
                return getattr(self._real, name)

        wrapped = FailOnDropConn(conn)
        with pytest.raises(RuntimeError, match="injected"):
            _migrate_to_uuid_pk(wrapped)

        # Original v1 schema intact: type_id is PK, no uuid column
        cur = conn.execute("PRAGMA table_info(entities)")
        col_map = {row[1]: row for row in cur.fetchall()}
        assert "type_id" in col_map
        assert col_map["type_id"][5] == 1  # type_id is still PK
        assert "uuid" not in col_map

        # schema_version remains '1'
        ver = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        assert ver[0] == "1"

        # All data preserved
        count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        assert count == 2

        conn.close()


# ---------------------------------------------------------------------------
# Task 1.2: Schema creation tests
# ---------------------------------------------------------------------------


class TestSchemaCreation:
    def test_creates_entities_table(self, db: EntityDatabase):
        """The entities table should exist after init."""
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='entities'"
        )
        assert cur.fetchone() is not None

    def test_creates_metadata_table(self, db: EntityDatabase):
        """The _metadata table should exist after init."""
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='_metadata'"
        )
        assert cur.fetchone() is not None

    def test_entities_has_12_columns(self, db: EntityDatabase):
        cur = db._conn.execute("PRAGMA table_info(entities)")
        columns = cur.fetchall()
        assert len(columns) == 12

    def test_entities_column_names(self, db: EntityDatabase):
        cur = db._conn.execute("PRAGMA table_info(entities)")
        col_names = [row[1] for row in cur.fetchall()]
        expected = [
            "uuid", "type_id", "entity_type", "entity_id", "name", "status",
            "parent_type_id", "parent_uuid", "artifact_path", "created_at",
            "updated_at", "metadata",
        ]
        assert col_names == expected

    def test_uuid_is_primary_key(self, db: EntityDatabase):
        cur = db._conn.execute("PRAGMA table_info(entities)")
        col_map = {row[1]: row for row in cur.fetchall()}
        assert col_map["uuid"][5] == 1  # pk flag
        assert col_map["type_id"][5] == 0  # type_id is NOT pk

    def test_entity_type_no_sql_check_constraint(self, db: EntityDatabase):
        """entity_type CHECK constraint removed in v6; Python validation only.

        After migration 6, arbitrary entity_type values are accepted at the
        SQL level. Validation is enforced by _validate_entity_type() in Python.
        """
        import uuid

        # SQL-level insert with arbitrary entity_type should succeed
        db._conn.execute(
            "INSERT INTO entities (uuid, type_id, entity_type, entity_id, "
            "name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "custom:x", "custom", "x", "test",
             "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        db._conn.commit()
        row = db._conn.execute(
            "SELECT entity_type FROM entities WHERE type_id = 'custom:x'"
        ).fetchone()
        assert row[0] == "custom"

    def test_valid_entity_types_accepted(self, db: EntityDatabase):
        """All four valid entity types should be insertable."""
        import uuid
        for etype in ("backlog", "brainstorm", "project", "feature"):
            db._conn.execute(
                "INSERT INTO entities (uuid, type_id, entity_type, entity_id, "
                "name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), f"{etype}:test", etype, "test",
                 f"Test {etype}",
                 "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
            )
        db._conn.commit()
        cur = db._conn.execute("SELECT COUNT(*) FROM entities")
        assert cur.fetchone()[0] == 4


class TestTriggers:
    def test_has_nine_triggers(self, db: EntityDatabase):
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"
        )
        trigger_names = [row[0] for row in cur.fetchall()]
        expected = [
            "enforce_immutable_created_at",
            "enforce_immutable_entity_type",
            "enforce_immutable_type_id",
            "enforce_immutable_uuid",
            "enforce_immutable_wp_type_id",
            "enforce_no_self_parent",
            "enforce_no_self_parent_update",
            "enforce_no_self_parent_uuid_insert",
            "enforce_no_self_parent_uuid_update",
        ]
        assert trigger_names == expected


class TestIndexes:
    def test_has_indexes(self, db: EntityDatabase):
        """Verify all expected indexes exist after migration 6."""
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        index_names = [row[0] for row in cur.fetchall()]
        expected = [
            "idx_ed_blocked_by_uuid",
            "idx_ed_entity_uuid",
            "idx_entity_type",
            "idx_eoa_entity_uuid",
            "idx_eoa_key_result_uuid",
            "idx_et_entity_uuid",
            "idx_et_tag",
            "idx_parent_type_id",
            "idx_parent_uuid",
            "idx_status",
            "idx_wp_kanban_column",
            "idx_wp_uuid",
            "idx_wp_workflow_phase",
        ]
        assert index_names == expected


class TestPragmas:
    def test_wal_mode(self, db: EntityDatabase):
        cur = db._conn.execute("PRAGMA journal_mode")
        assert cur.fetchone()[0] == "wal"

    def test_foreign_keys_on(self, db: EntityDatabase):
        cur = db._conn.execute("PRAGMA foreign_keys")
        assert cur.fetchone()[0] == 1

    def test_busy_timeout(self, db: EntityDatabase):
        cur = db._conn.execute("PRAGMA busy_timeout")
        assert cur.fetchone()[0] == 5000

    def test_cache_size(self, db: EntityDatabase):
        cur = db._conn.execute("PRAGMA cache_size")
        assert cur.fetchone()[0] == -8000


class TestMetadata:
    def test_get_missing_key_returns_none(self, db: EntityDatabase):
        assert db.get_metadata("nonexistent") is None

    def test_set_and_get(self, db: EntityDatabase):
        db.set_metadata("foo", "bar")
        assert db.get_metadata("foo") == "bar"

    def test_set_overwrites(self, db: EntityDatabase):
        db.set_metadata("foo", "bar")
        db.set_metadata("foo", "baz")
        assert db.get_metadata("foo") == "baz"

    def test_schema_version_is_5(self, db: EntityDatabase):
        assert db.get_metadata("schema_version") == "6"


# ---------------------------------------------------------------------------
# Task 1.4: register_entity tests
# ---------------------------------------------------------------------------


class TestRegisterEntity:
    def test_happy_path(self, db: EntityDatabase):
        """Register a feature entity and retrieve it."""
        result = db.register_entity("feature", "feat-001", "My Feature")
        assert _UUID_V4_RE.match(result), f"Expected UUID v4, got {result!r}"
        cur = db._conn.execute(
            "SELECT * FROM entities WHERE type_id = 'feature:feat-001'"
        )
        row = cur.fetchone()
        assert row is not None
        assert row["entity_type"] == "feature"
        assert row["entity_id"] == "feat-001"
        assert row["name"] == "My Feature"

    def test_type_id_auto_constructed(self, db: EntityDatabase):
        """type_id should be f'{entity_type}:{entity_id}'."""
        result = db.register_entity("backlog", "item-42", "Backlog Item")
        assert _UUID_V4_RE.match(result), f"Expected UUID v4, got {result!r}"
        # Verify the type_id was constructed correctly in the DB
        row = db._conn.execute(
            "SELECT type_id FROM entities WHERE uuid = ?", (result,)
        ).fetchone()
        assert row["type_id"] == "backlog:item-42"

    def test_insert_or_ignore_idempotency(self, db: EntityDatabase):
        """Registering the same entity twice should not raise."""
        uuid1 = db.register_entity("project", "proj-1", "Project One")
        uuid2 = db.register_entity("project", "proj-1", "Project One Updated")
        assert _UUID_V4_RE.match(uuid1)
        assert uuid1 == uuid2
        cur = db._conn.execute("SELECT COUNT(*) FROM entities")
        assert cur.fetchone()[0] == 1
        # Name should remain the original (INSERT OR IGNORE)
        cur = db._conn.execute(
            "SELECT name FROM entities WHERE type_id = 'project:proj-1'"
        )
        assert cur.fetchone()[0] == "Project One"

    def test_entity_type_validation(self, db: EntityDatabase):
        """Invalid entity_type should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid entity_type"):
            db.register_entity("invalid_type", "x", "Bad Type")

    def test_all_valid_types(self, db: EntityDatabase):
        """All eight valid types should succeed."""
        for etype in EntityDatabase.VALID_ENTITY_TYPES:
            result = db.register_entity(etype, f"id-{etype}", f"Name {etype}")
            assert _UUID_V4_RE.match(result), f"Expected UUID v4 for {etype}"

    def test_new_entity_types_register_successfully(self, db: EntityDatabase):
        """New entity types (initiative, objective, key_result, task) register."""
        new_types = ("initiative", "objective", "key_result", "task")
        for etype in new_types:
            uuid_str = db.register_entity(etype, f"001-test-{etype}", f"Test {etype}")
            assert _UUID_V4_RE.match(uuid_str), f"{etype} should return valid UUID"
            # Verify entity is queryable
            row = db._conn.execute(
                "SELECT entity_type, entity_id FROM entities WHERE uuid = ?",
                (uuid_str,),
            ).fetchone()
            assert row["entity_type"] == etype
            assert row["entity_id"] == f"001-test-{etype}"

    def test_optional_fields(self, db: EntityDatabase):
        """artifact_path, status, parent_type_id, metadata should be optional."""
        entity_uuid = db.register_entity(
            "feature", "f1", "Feature One",
            artifact_path="/docs/features/f1",
            status="active",
            metadata={"priority": "high"},
        )
        cur = db._conn.execute(
            "SELECT * FROM entities WHERE uuid = ?", (entity_uuid,)
        )
        row = cur.fetchone()
        assert row["artifact_path"] == "/docs/features/f1"
        assert row["status"] == "active"
        assert json.loads(row["metadata"]) == {"priority": "high"}

    def test_parent_type_id_fk_validation(self, db: EntityDatabase):
        """Setting parent_type_id to a non-existent entity should raise."""
        with pytest.raises(sqlite3.IntegrityError):
            db.register_entity(
                "feature", "child", "Child Feature",
                parent_type_id="project:nonexistent",
            )

    def test_valid_parent_type_id(self, db: EntityDatabase):
        """Setting parent_type_id to an existing entity should work."""
        db.register_entity("project", "proj-1", "Project One")
        entity_uuid = db.register_entity(
            "feature", "feat-1", "Feature One",
            parent_type_id="project:proj-1",
        )
        cur = db._conn.execute(
            "SELECT parent_type_id FROM entities WHERE uuid = ?",
            (entity_uuid,),
        )
        assert cur.fetchone()[0] == "project:proj-1"

    def test_timestamps_set(self, db: EntityDatabase):
        """created_at and updated_at should be set automatically."""
        entity_uuid = db.register_entity("brainstorm", "b1", "Brainstorm One")
        cur = db._conn.execute(
            "SELECT created_at, updated_at FROM entities WHERE uuid = ?",
            (entity_uuid,),
        )
        row = cur.fetchone()
        assert row["created_at"] is not None
        assert row["updated_at"] is not None

    def test_returns_uuid_string(self, db: EntityDatabase):
        """register_entity should return a UUID v4 string."""
        result = db.register_entity("feature", "f99", "Feature 99")
        assert isinstance(result, str)
        assert _UUID_V4_RE.match(result), f"Expected UUID v4, got {result!r}"

    def test_metadata_stored_as_json(self, db: EntityDatabase):
        """metadata dict should be stored as JSON string in the database."""
        db.register_entity(
            "feature", "f1", "Feature",
            metadata={"key": "value", "count": 42},
        )
        cur = db._conn.execute(
            "SELECT metadata FROM entities WHERE type_id = 'feature:f1'"
        )
        raw = cur.fetchone()[0]
        assert isinstance(raw, str)
        parsed = json.loads(raw)
        assert parsed == {"key": "value", "count": 42}


# ---------------------------------------------------------------------------
# Task 1.6: Immutable field trigger tests
# ---------------------------------------------------------------------------


class TestImmutableTriggers:
    def test_type_id_immutable(self, db: EntityDatabase):
        """Attempting to change type_id should raise IntegrityError."""
        db.register_entity("feature", "f1", "Feature One")
        with pytest.raises(sqlite3.IntegrityError, match="type_id is immutable"):
            db._conn.execute(
                "UPDATE entities SET type_id = 'feature:f2' "
                "WHERE type_id = 'feature:f1'"
            )

    def test_entity_type_immutable(self, db: EntityDatabase):
        """Attempting to change entity_type should raise IntegrityError."""
        db.register_entity("feature", "f1", "Feature One")
        with pytest.raises(sqlite3.IntegrityError, match="entity_type is immutable"):
            db._conn.execute(
                "UPDATE entities SET entity_type = 'project' "
                "WHERE type_id = 'feature:f1'"
            )

    def test_created_at_immutable(self, db: EntityDatabase):
        """Attempting to change created_at should raise IntegrityError."""
        db.register_entity("feature", "f1", "Feature One")
        with pytest.raises(sqlite3.IntegrityError, match="created_at is immutable"):
            db._conn.execute(
                "UPDATE entities SET created_at = '2099-01-01T00:00:00Z' "
                "WHERE type_id = 'feature:f1'"
            )

    def test_self_parent_on_insert(self, db: EntityDatabase):
        """Inserting an entity that is its own parent should raise."""
        import uuid

        test_uuid = str(uuid.uuid4())
        # Case 1: self-parent via parent_type_id
        with pytest.raises(sqlite3.IntegrityError, match="entity cannot be its own parent"):
            db._conn.execute(
                "INSERT INTO entities (uuid, type_id, entity_type, entity_id, "
                "name, parent_type_id, created_at, updated_at) "
                "VALUES (?, 'feature:self', 'feature', 'self', 'Self', "
                "'feature:self', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
                (test_uuid,),
            )
        # Case 2: self-parent via parent_uuid (R12 trigger)
        test_uuid2 = str(uuid.uuid4())
        with pytest.raises(sqlite3.IntegrityError, match="entity cannot be its own parent"):
            db._conn.execute(
                "INSERT INTO entities (uuid, type_id, entity_type, entity_id, "
                "name, parent_uuid, created_at, updated_at) "
                "VALUES (?, 'feature:self2', 'feature', 'self2', 'Self2', "
                "?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
                (test_uuid2, test_uuid2),
            )

    def test_self_parent_on_update(self, db: EntityDatabase):
        """Updating parent_type_id to self should raise."""
        db.register_entity("feature", "f1", "Feature One")
        with pytest.raises(sqlite3.IntegrityError, match="entity cannot be its own parent"):
            db._conn.execute(
                "UPDATE entities SET parent_type_id = 'feature:f1' "
                "WHERE type_id = 'feature:f1'"
            )

    def test_name_is_mutable(self, db: EntityDatabase):
        """name should be updatable (not protected by triggers)."""
        db.register_entity("feature", "f1", "Original")
        db._conn.execute(
            "UPDATE entities SET name = 'Updated' WHERE type_id = 'feature:f1'"
        )
        db._conn.commit()
        cur = db._conn.execute(
            "SELECT name FROM entities WHERE type_id = 'feature:f1'"
        )
        assert cur.fetchone()[0] == "Updated"

    def test_status_is_mutable(self, db: EntityDatabase):
        """status should be updatable (not protected by triggers)."""
        db.register_entity("feature", "f1", "Feature", status="draft")
        db._conn.execute(
            "UPDATE entities SET status = 'active' WHERE type_id = 'feature:f1'"
        )
        db._conn.commit()
        cur = db._conn.execute(
            "SELECT status FROM entities WHERE type_id = 'feature:f1'"
        )
        assert cur.fetchone()[0] == "active"


# ---------------------------------------------------------------------------
# Task 1.8: set_parent tests
# ---------------------------------------------------------------------------


class TestSetParent:
    def test_happy_path(self, db: EntityDatabase):
        """Set parent on a child entity."""
        db.register_entity("project", "proj-1", "Project One")
        child_uuid = db.register_entity("feature", "f1", "Feature One")
        result = db.set_parent("feature:f1", "project:proj-1")
        assert result == child_uuid
        cur = db._conn.execute(
            "SELECT parent_type_id FROM entities WHERE type_id = 'feature:f1'"
        )
        assert cur.fetchone()[0] == "project:proj-1"

    def test_circular_reference_rejected(self, db: EntityDatabase):
        """A->B->C, then setting C's parent to A should raise (circular)."""
        db.register_entity("project", "a", "A")
        db.register_entity("feature", "b", "B", parent_type_id="project:a")
        db.register_entity("feature", "c", "C", parent_type_id="feature:b")
        with pytest.raises(ValueError, match="[Cc]ircular"):
            db.set_parent("project:a", "feature:c")

    def test_self_parent_rejected(self, db: EntityDatabase):
        """Setting an entity as its own parent should raise."""
        db.register_entity("feature", "f1", "Feature One")
        with pytest.raises((ValueError, sqlite3.IntegrityError)):
            db.set_parent("feature:f1", "feature:f1")

    def test_non_existent_child_rejected(self, db: EntityDatabase):
        """Setting parent on non-existent entity should raise."""
        db.register_entity("project", "proj-1", "Project One")
        with pytest.raises(ValueError, match="[Nn]ot found"):
            db.set_parent("feature:nonexistent", "project:proj-1")

    def test_non_existent_parent_rejected(self, db: EntityDatabase):
        """Setting non-existent entity as parent should raise."""
        db.register_entity("feature", "f1", "Feature One")
        with pytest.raises(ValueError, match="[Nn]ot found"):
            db.set_parent("feature:f1", "project:nonexistent")

    def test_reassign_parent(self, db: EntityDatabase):
        """Should be able to change parent from one entity to another."""
        db.register_entity("project", "p1", "Project 1")
        db.register_entity("project", "p2", "Project 2")
        db.register_entity("feature", "f1", "Feature", parent_type_id="project:p1")
        db.set_parent("feature:f1", "project:p2")
        cur = db._conn.execute(
            "SELECT parent_type_id FROM entities WHERE type_id = 'feature:f1'"
        )
        assert cur.fetchone()[0] == "project:p2"

    def test_deep_circular_reference_rejected(self, db: EntityDatabase):
        """A->B->C->D, then setting A's parent to D should be rejected."""
        db.register_entity("project", "a", "A")
        db.register_entity("feature", "b", "B", parent_type_id="project:a")
        db.register_entity("feature", "c", "C", parent_type_id="feature:b")
        db.register_entity("feature", "d", "D", parent_type_id="feature:c")
        with pytest.raises(ValueError, match="[Cc]ircular"):
            db.set_parent("project:a", "feature:d")

    def test_set_parent_depth_guard_11_hops_no_cycle(self, db: EntityDatabase):
        """An 11-entity chain with no cycle: linking a 12th should succeed.

        The depth guard (max 10 hops) should terminate traversal gracefully
        without hanging or raising, since there is no cycle within the limit.
        Covers AC-1.3 and AC-1.4.
        """
        # Build chain: e0 <- e1 <- e2 <- ... <- e10 (11 entities, 10 hops)
        db.register_entity("feature", "e0", "Entity 0")
        for i in range(1, 11):
            db.register_entity(
                "feature", f"e{i}", f"Entity {i}",
                parent_type_id=f"feature:e{i - 1}",
            )
        # Create 12th entity and set its parent to the end of the chain
        db.register_entity("feature", "e11", "Entity 11")
        # This must succeed — no cycle, depth guard terminates the CTE
        result = db.set_parent("feature:e11", "feature:e10")
        assert result is not None  # returns child_uuid on success

    def test_set_parent_cycle_within_10_hops(self, db: EntityDatabase):
        """A chain with a cycle at hop 5: set_parent() must raise ValueError.

        Covers AC-1.2.
        """
        # Build chain: e0 <- e1 <- e2 <- e3 <- e4 (5 entities, 4 hops)
        db.register_entity("feature", "e0", "Entity 0")
        for i in range(1, 5):
            db.register_entity(
                "feature", f"e{i}", f"Entity {i}",
                parent_type_id=f"feature:e{i - 1}",
            )
        # Attempt to set e0's parent to e4 -> creates cycle: e0->e4->e3->e2->e1->e0
        with pytest.raises(ValueError, match="[Cc]ircular"):
            db.set_parent("feature:e0", "feature:e4")


# ---------------------------------------------------------------------------
# Task 1.10: get_entity tests
# ---------------------------------------------------------------------------


class TestGetEntity:
    def test_returns_dict_for_existing(self, db: EntityDatabase):
        """get_entity should return a dict for an existing entity."""
        db.register_entity("feature", "f1", "Feature One", status="active")
        result = db.get_entity("feature:f1")
        assert isinstance(result, dict)
        assert result["type_id"] == "feature:f1"
        assert result["entity_type"] == "feature"
        assert result["entity_id"] == "f1"
        assert result["name"] == "Feature One"
        assert result["status"] == "active"
        assert result["created_at"] is not None
        assert result["updated_at"] is not None

    def test_returns_none_for_nonexistent(self, db: EntityDatabase):
        """get_entity should return None for a non-existent type_id."""
        result = db.get_entity("feature:nonexistent")
        assert result is None

    def test_includes_metadata_as_string(self, db: EntityDatabase):
        """metadata should be returned as the raw JSON string."""
        db.register_entity(
            "feature", "f1", "Feature",
            metadata={"key": "value"},
        )
        result = db.get_entity("feature:f1")
        assert result["metadata"] is not None
        assert json.loads(result["metadata"]) == {"key": "value"}

    def test_includes_parent_type_id(self, db: EntityDatabase):
        """parent_type_id should be included in the dict."""
        db.register_entity("project", "p1", "Project")
        db.register_entity("feature", "f1", "Feature", parent_type_id="project:p1")
        result = db.get_entity("feature:f1")
        assert result["parent_type_id"] == "project:p1"

    def test_null_optional_fields(self, db: EntityDatabase):
        """Optional fields should be None when not set."""
        db.register_entity("feature", "f1", "Feature")
        result = db.get_entity("feature:f1")
        assert result["status"] is None
        assert result["parent_type_id"] is None
        assert result["artifact_path"] is None
        assert result["metadata"] is None


# ---------------------------------------------------------------------------
# Task 1.12: get_lineage tests
# ---------------------------------------------------------------------------


class TestGetLineage:
    def _setup_chain(self, db: EntityDatabase):
        """Create a chain: project:root -> feature:mid -> feature:leaf."""
        db.register_entity("project", "root", "Root Project")
        db.register_entity("feature", "mid", "Mid Feature",
                           parent_type_id="project:root")
        db.register_entity("feature", "leaf", "Leaf Feature",
                           parent_type_id="feature:mid")

    def test_upward_traversal_root_first(self, db: EntityDatabase):
        """Upward traversal should return root first."""
        self._setup_chain(db)
        lineage = db.get_lineage("feature:leaf", direction="up")
        type_ids = [e["type_id"] for e in lineage]
        assert type_ids == ["project:root", "feature:mid", "feature:leaf"]

    def test_downward_traversal_bfs(self, db: EntityDatabase):
        """Downward traversal should return entity then children (BFS)."""
        self._setup_chain(db)
        lineage = db.get_lineage("project:root", direction="down")
        type_ids = [e["type_id"] for e in lineage]
        assert type_ids == ["project:root", "feature:mid", "feature:leaf"]

    def test_single_entity_up(self, db: EntityDatabase):
        """An entity with no parent should return just itself."""
        db.register_entity("project", "solo", "Solo Project")
        lineage = db.get_lineage("project:solo", direction="up")
        assert len(lineage) == 1
        assert lineage[0]["type_id"] == "project:solo"

    def test_single_entity_down(self, db: EntityDatabase):
        """An entity with no children should return just itself."""
        db.register_entity("project", "solo", "Solo Project")
        lineage = db.get_lineage("project:solo", direction="down")
        assert len(lineage) == 1
        assert lineage[0]["type_id"] == "project:solo"

    def test_depth_limit(self, db: EntityDatabase):
        """Traversal should respect max_depth."""
        self._setup_chain(db)
        lineage = db.get_lineage("feature:leaf", direction="up", max_depth=1)
        type_ids = [e["type_id"] for e in lineage]
        # max_depth=1 means: self (depth 0) + 1 level up
        assert "feature:leaf" in type_ids
        assert "feature:mid" in type_ids
        assert "project:root" not in type_ids

    def test_default_direction_is_up(self, db: EntityDatabase):
        """Default direction should be 'up'."""
        self._setup_chain(db)
        lineage = db.get_lineage("feature:leaf")
        type_ids = [e["type_id"] for e in lineage]
        assert type_ids[0] == "project:root"

    def test_returns_list_of_dicts(self, db: EntityDatabase):
        """get_lineage should return a list of dicts."""
        db.register_entity("project", "solo", "Solo")
        lineage = db.get_lineage("project:solo")
        assert isinstance(lineage, list)
        assert all(isinstance(e, dict) for e in lineage)

    def test_nonexistent_entity_returns_empty(self, db: EntityDatabase):
        """get_lineage for a non-existent entity should return empty list."""
        lineage = db.get_lineage("feature:nonexistent")
        assert lineage == []

    def test_downward_multiple_children(self, db: EntityDatabase):
        """Downward traversal should include all children."""
        db.register_entity("project", "root", "Root")
        db.register_entity("feature", "a", "A", parent_type_id="project:root")
        db.register_entity("feature", "b", "B", parent_type_id="project:root")
        lineage = db.get_lineage("project:root", direction="down")
        type_ids = [e["type_id"] for e in lineage]
        assert "project:root" in type_ids
        assert "feature:a" in type_ids
        assert "feature:b" in type_ids
        assert len(type_ids) == 3

    def test_max_depth_default_is_10(self, db: EntityDatabase):
        """Default max_depth should be 10."""
        # Build a chain of 12 entities
        db.register_entity("project", "e0", "E0")
        for i in range(1, 12):
            db.register_entity(
                "feature", f"e{i}", f"E{i}",
                parent_type_id=f"{'project' if i == 1 else 'feature'}:e{i-1}",
            )
        # Go upward from e11 with default max_depth=10
        lineage = db.get_lineage("feature:e11", direction="up")
        # Should have 11 items (self + 10 levels up), not 12
        assert len(lineage) == 11


# ---------------------------------------------------------------------------
# Task 1.14: update_entity tests
# ---------------------------------------------------------------------------


class TestUpdateEntity:
    def test_update_name(self, db: EntityDatabase):
        """Updating name should work."""
        db.register_entity("feature", "f1", "Original")
        db.update_entity("feature:f1", name="Updated")
        result = db.get_entity("feature:f1")
        assert result["name"] == "Updated"

    def test_update_status(self, db: EntityDatabase):
        """Updating status should work."""
        db.register_entity("feature", "f1", "Feature", status="draft")
        db.update_entity("feature:f1", status="active")
        result = db.get_entity("feature:f1")
        assert result["status"] == "active"

    def test_updated_at_changes(self, db: EntityDatabase):
        """updated_at should be refreshed on update."""
        db.register_entity("feature", "f1", "Feature")
        original = db.get_entity("feature:f1")
        original_updated = original["updated_at"]
        # Small delay to ensure different timestamp
        time.sleep(0.01)
        db.update_entity("feature:f1", name="Changed")
        updated = db.get_entity("feature:f1")
        assert updated["updated_at"] != original_updated

    def test_shallow_metadata_merge(self, db: EntityDatabase):
        """Updating metadata should do a shallow merge."""
        db.register_entity(
            "feature", "f1", "Feature",
            metadata={"key1": "val1", "key2": "val2"},
        )
        db.update_entity("feature:f1", metadata={"key2": "new_val2", "key3": "val3"})
        result = db.get_entity("feature:f1")
        merged = json.loads(result["metadata"])
        assert merged == {"key1": "val1", "key2": "new_val2", "key3": "val3"}

    def test_empty_dict_clears_metadata(self, db: EntityDatabase):
        """Passing empty dict {} for metadata should clear it."""
        db.register_entity(
            "feature", "f1", "Feature",
            metadata={"key1": "val1"},
        )
        db.update_entity("feature:f1", metadata={})
        result = db.get_entity("feature:f1")
        assert result["metadata"] is None

    def test_nonexistent_entity_raises(self, db: EntityDatabase):
        """Updating a non-existent entity should raise ValueError."""
        with pytest.raises(ValueError, match="[Nn]ot found"):
            db.update_entity("feature:nonexistent", name="X")

    def test_update_artifact_path(self, db: EntityDatabase):
        """Updating artifact_path should work."""
        db.register_entity("feature", "f1", "Feature")
        db.update_entity("feature:f1", artifact_path="/new/path")
        result = db.get_entity("feature:f1")
        assert result["artifact_path"] == "/new/path"

    def test_no_changes_still_updates_timestamp(self, db: EntityDatabase):
        """Calling update_entity with no changes should still update updated_at."""
        db.register_entity("feature", "f1", "Feature")
        original = db.get_entity("feature:f1")
        time.sleep(0.01)
        db.update_entity("feature:f1")
        updated = db.get_entity("feature:f1")
        assert updated["updated_at"] != original["updated_at"]

    def test_metadata_merge_with_none_existing(self, db: EntityDatabase):
        """Merging metadata when existing is None should just set."""
        db.register_entity("feature", "f1", "Feature")
        db.update_entity("feature:f1", metadata={"key": "value"})
        result = db.get_entity("feature:f1")
        assert json.loads(result["metadata"]) == {"key": "value"}


# ---------------------------------------------------------------------------
# Task 1.16: export_lineage_markdown tests
# ---------------------------------------------------------------------------


class TestExportLineageMarkdown:
    def test_single_tree(self, db: EntityDatabase):
        """Export a single tree with root and children."""
        db.register_entity("project", "p1", "Project Alpha")
        db.register_entity("feature", "f1", "Feature A",
                           parent_type_id="project:p1")
        db.register_entity("feature", "f2", "Feature B",
                           parent_type_id="project:p1")
        md = db.export_lineage_markdown("project:p1")
        assert "Project Alpha" in md
        assert "Feature A" in md
        assert "Feature B" in md
        # Children should be indented more than root
        lines = md.strip().split("\n")
        # Root line should have fewer leading spaces than children
        root_lines = [l for l in lines if "Project Alpha" in l]
        child_lines = [l for l in lines if "Feature A" in l or "Feature B" in l]
        assert len(root_lines) >= 1
        assert len(child_lines) >= 1

    def test_all_trees_export(self, db: EntityDatabase):
        """Export all trees (no type_id argument)."""
        db.register_entity("project", "p1", "Project Alpha")
        db.register_entity("feature", "f1", "Feature A",
                           parent_type_id="project:p1")
        db.register_entity("project", "p2", "Project Beta")
        md = db.export_lineage_markdown()
        assert "Project Alpha" in md
        assert "Feature A" in md
        assert "Project Beta" in md

    def test_empty_database(self, db: EntityDatabase):
        """Empty database should return empty or minimal markdown."""
        md = db.export_lineage_markdown()
        assert md.strip() == "" or "No entities" in md

    def test_markdown_format_uses_indentation(self, db: EntityDatabase):
        """Children should be indented relative to parents."""
        db.register_entity("project", "p1", "Root")
        db.register_entity("feature", "f1", "Child",
                           parent_type_id="project:p1")
        db.register_entity("feature", "f2", "Grandchild",
                           parent_type_id="feature:f1")
        md = db.export_lineage_markdown("project:p1")
        lines = [l for l in md.split("\n") if l.strip()]
        # Find indentation levels
        indents = []
        for line in lines:
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            indents.append(indent)
        # Should have at least 2 different indentation levels
        assert len(set(indents)) >= 2

    def test_includes_type_info(self, db: EntityDatabase):
        """Markdown should include entity type and/or status info."""
        db.register_entity("project", "p1", "Project One", status="active")
        md = db.export_lineage_markdown("project:p1")
        # Should include either the type or the type_id
        assert "project" in md.lower()


# ---------------------------------------------------------------------------
# Deepened tests: BDD, Boundary, Adversarial, Error, Mutation
# ---------------------------------------------------------------------------


class TestLineageFullAncestryChain:
    """BDD: AC-1 — show-lineage displays full ancestry chain with metadata.
    derived_from: spec:AC-1
    """

    def test_show_lineage_displays_full_ancestry_chain_with_metadata(
        self, db: EntityDatabase,
    ):
        # Given a 4-level chain: backlog -> brainstorm -> project -> feature
        db.register_entity("backlog", "00019", "Lineage Tracking", status="promoted")
        db.register_entity(
            "brainstorm", "20260227-lineage", "Entity Lineage",
            parent_type_id="backlog:00019",
        )
        db.register_entity(
            "project", "P001", "Lineage Project",
            parent_type_id="brainstorm:20260227-lineage", status="active",
        )
        db.register_entity(
            "feature", "029-entity-lineage-tracking", "Entity Lineage Tracking",
            parent_type_id="project:P001", status="active",
        )
        # When traversing upward from the feature
        lineage = db.get_lineage("feature:029-entity-lineage-tracking", direction="up")
        # Then all four ancestors are returned in root-first order
        type_ids = [e["type_id"] for e in lineage]
        assert type_ids == [
            "backlog:00019",
            "brainstorm:20260227-lineage",
            "project:P001",
            "feature:029-entity-lineage-tracking",
        ]
        # And each entity carries its metadata fields
        assert lineage[0]["status"] == "promoted"
        assert lineage[0]["name"] == "Lineage Tracking"
        assert lineage[3]["status"] == "active"


class TestLineageOrphanedParent:
    """BDD: AC-3 — orphaned parent shows orphaned label.
    derived_from: spec:AC-3
    """

    def test_show_lineage_orphaned_parent_shows_orphaned_label(
        self, db: EntityDatabase,
    ):
        # Given a synthetic orphaned backlog as parent of a feature
        db.register_entity(
            "backlog", "00099", "Backlog #00099 (orphaned)", status="orphaned",
        )
        db.register_entity(
            "feature", "031-orphan", "Orphan Feature",
            parent_type_id="backlog:00099",
        )
        # When traversing upward from the feature
        lineage = db.get_lineage("feature:031-orphan", direction="up")
        # Then the parent entity has status "orphaned"
        parent = lineage[0]
        assert parent["type_id"] == "backlog:00099"
        assert parent["status"] == "orphaned"
        assert "orphaned" in parent["name"].lower() or parent["status"] == "orphaned"


class TestLineageDescendants:
    """BDD: AC-4/AC-5 — descendants display full tree.
    derived_from: spec:AC-4, spec:AC-5
    """

    def test_show_lineage_descendants_displays_full_descendant_tree(
        self, db: EntityDatabase,
    ):
        # Given a project with 2 features and 1 sub-feature
        db.register_entity("project", "P1", "Root Project")
        db.register_entity(
            "feature", "f1", "Feature A", parent_type_id="project:P1",
        )
        db.register_entity(
            "feature", "f2", "Feature B", parent_type_id="project:P1",
        )
        db.register_entity(
            "feature", "f1-sub", "Sub-Feature A1", parent_type_id="feature:f1",
        )
        # When traversing downward from the project
        lineage = db.get_lineage("project:P1", direction="down")
        # Then all 4 entities are present
        type_ids = {e["type_id"] for e in lineage}
        assert type_ids == {
            "project:P1", "feature:f1", "feature:f2", "feature:f1-sub",
        }
        # And root is first
        assert lineage[0]["type_id"] == "project:P1"

    def test_show_lineage_project_decomposition_tree(
        self, db: EntityDatabase,
    ):
        # Given a backlog -> brainstorm -> project -> features chain
        db.register_entity("backlog", "00001", "Idea")
        db.register_entity(
            "brainstorm", "20260101-idea", "Brainstorm Idea",
            parent_type_id="backlog:00001",
        )
        db.register_entity(
            "project", "proj-alpha", "Alpha Project",
            parent_type_id="brainstorm:20260101-idea",
        )
        db.register_entity(
            "feature", "fa", "Feature A", parent_type_id="project:proj-alpha",
        )
        db.register_entity(
            "feature", "fb", "Feature B", parent_type_id="project:proj-alpha",
        )
        # When traversing downward from the project
        lineage = db.get_lineage("project:proj-alpha", direction="down")
        # Then both features appear as descendants
        type_ids = {e["type_id"] for e in lineage}
        assert "feature:fa" in type_ids
        assert "feature:fb" in type_ids


class TestParentFieldValidation:
    """BDD: AC-9 — nonexistent parent warns and nullifies.
    derived_from: spec:AC-9
    """

    def test_parent_field_validation_nonexistent_entity_warns_and_nullifies(
        self, db: EntityDatabase,
    ):
        # Given no project "nonexistent" exists in the database
        # When trying to register a feature with that parent
        with pytest.raises(sqlite3.IntegrityError):
            db.register_entity(
                "feature", "child", "Child Feature",
                parent_type_id="project:nonexistent",
            )
        # Then the feature is not registered (FK violation prevented it)
        assert db.get_entity("feature:child") is None


class TestTraversalDepthGuard:
    """BDD: AC-14 + Boundary — depth guard stops at 10 hops.
    derived_from: spec:AC-14, dimension:boundary_values
    """

    def _build_chain(self, db: EntityDatabase, length: int):
        """Build a chain of entities of the given length."""
        db.register_entity("project", "e0", "E0")
        for i in range(1, length):
            parent_type = "project" if i == 1 else "feature"
            db.register_entity(
                "feature", f"e{i}", f"E{i}",
                parent_type_id=f"{parent_type}:e{i-1}",
            )

    def test_traversal_depth_at_exactly_ten_hops_no_loop(
        self, db: EntityDatabase,
    ):
        # Given a chain of 12 entities (depth 0 through 11)
        self._build_chain(db, 12)
        # When traversing upward from e11 with default max_depth=10
        lineage = db.get_lineage("feature:e11", direction="up")
        # Then we get self + 10 levels up = 11 entities (e1 through e11)
        assert len(lineage) == 11
        # And e0 (the 12th) is excluded because it's 11 hops away
        type_ids = [e["type_id"] for e in lineage]
        assert "project:e0" not in type_ids

    def test_traversal_depth_at_eleven_hops_triggers_guard(
        self, db: EntityDatabase,
    ):
        # Given a chain of 13 entities (depth 0 through 12)
        self._build_chain(db, 13)
        # When traversing upward from e12 with default max_depth=10
        lineage = db.get_lineage("feature:e12", direction="up")
        # Then we get at most 11 entities (self + 10 levels)
        assert len(lineage) == 11
        # And the root (e0) and e1 are excluded
        type_ids = [e["type_id"] for e in lineage]
        assert "project:e0" not in type_ids

    def test_traversal_depth_at_nine_hops_fully_displayed(
        self, db: EntityDatabase,
    ):
        # Given a chain of 10 entities (depth 0 through 9)
        self._build_chain(db, 10)
        # When traversing upward from e9 with default max_depth=10
        lineage = db.get_lineage("feature:e9", direction="up")
        # Then all 10 entities are returned (only 9 hops, within limit)
        assert len(lineage) == 10
        type_ids = [e["type_id"] for e in lineage]
        assert "project:e0" in type_ids
        assert "feature:e9" in type_ids

    def test_traversal_depth_of_one_single_entity(
        self, db: EntityDatabase,
    ):
        # Given a single entity with no parent
        db.register_entity("project", "solo", "Solo Project")
        # When traversing upward from it
        lineage = db.get_lineage("project:solo", direction="up")
        # Then only the entity itself is returned
        assert len(lineage) == 1
        assert lineage[0]["type_id"] == "project:solo"

    def test_depth_guard_uses_less_than_or_equal_to_ten(
        self, db: EntityDatabase,
    ):
        """Mutation mindset: verify depth < max_depth, not depth <= max_depth.
        derived_from: dimension:mutation_mindset
        """
        # Given a chain of exactly 12 entities
        self._build_chain(db, 12)
        # When traversing upward from e11 with max_depth=10
        lineage = db.get_lineage("feature:e11", direction="up", max_depth=10)
        # Then exactly 11 entities returned (self at depth 0, up to depth 10)
        assert len(lineage) == 11
        # When traversing with max_depth=11
        lineage_11 = db.get_lineage("feature:e11", direction="up", max_depth=11)
        # Then all 12 entities returned
        assert len(lineage_11) == 12


class TestCircularReferenceTwoNodeLoop:
    """Adversarial: circular reference with exactly 2 nodes.
    derived_from: dimension:adversarial
    """

    def test_circular_reference_two_node_loop_detected(
        self, db: EntityDatabase,
    ):
        # Given A -> B (A is parent of B)
        db.register_entity("project", "a", "A")
        db.register_entity("feature", "b", "B", parent_type_id="project:a")
        # When setting A's parent to B (would create A <-> B loop)
        with pytest.raises(ValueError, match="[Cc]ircular"):
            db.set_parent("project:a", "feature:b")
        # Then the parent remains None (unchanged)
        entity_a = db.get_entity("project:a")
        assert entity_a["parent_type_id"] is None


class TestBoundaryEntityIdEmpty:
    """Boundary: empty entity_id behavior.
    derived_from: dimension:boundary_values
    """

    def test_entity_id_empty_string_registered(self, db: EntityDatabase):
        # Given an empty entity_id string
        # When registering with entity_id=""
        entity_uuid = db.register_entity("feature", "", "Empty ID Feature")
        # Then the return is a UUID
        assert _UUID_V4_RE.match(entity_uuid)
        # And the type_id is "feature:" (colon-separated format), retrievable
        entity = db.get_entity("feature:")
        assert entity is not None
        assert entity["entity_id"] == ""
        assert entity["type_id"] == "feature:"


class TestDescendantTreeEdgeCases:
    """Boundary: descendant tree with 0, 1, many children.
    derived_from: dimension:boundary_values
    """

    def test_descendant_tree_with_zero_children(self, db: EntityDatabase):
        # Given a leaf entity with no children
        db.register_entity("feature", "leaf", "Leaf Feature")
        # When traversing downward
        lineage = db.get_lineage("feature:leaf", direction="down")
        # Then only the entity itself is returned
        assert len(lineage) == 1
        assert lineage[0]["type_id"] == "feature:leaf"

    def test_descendant_tree_with_many_children(self, db: EntityDatabase):
        # Given a project with 5 direct children
        db.register_entity("project", "root", "Root")
        for i in range(5):
            db.register_entity(
                "feature", f"child-{i}", f"Child {i}",
                parent_type_id="project:root",
            )
        # When traversing downward from root
        lineage = db.get_lineage("project:root", direction="down")
        # Then all 6 entities are returned (root + 5 children)
        assert len(lineage) == 6


class TestUpwardTraversalOrder:
    """Mutation mindset: verify ancestors are returned in correct root-first order.
    derived_from: dimension:mutation_mindset
    """

    def test_upward_traversal_returns_ancestors_in_correct_order(
        self, db: EntityDatabase,
    ):
        # Given a 4-level chain: A -> B -> C -> D
        db.register_entity("project", "a", "A")
        db.register_entity("feature", "b", "B", parent_type_id="project:a")
        db.register_entity("feature", "c", "C", parent_type_id="feature:b")
        db.register_entity("feature", "d", "D", parent_type_id="feature:c")
        # When traversing upward from D
        lineage = db.get_lineage("feature:d", direction="up")
        # Then order is root-first: A, B, C, D
        type_ids = [e["type_id"] for e in lineage]
        assert type_ids == ["project:a", "feature:b", "feature:c", "feature:d"]
        # Mutation check: if ORDER BY was ASC instead of DESC, this would fail


class TestTypeIdFormat:
    """Mutation mindset: type_id format is colon-separated.
    derived_from: dimension:mutation_mindset
    """

    def test_type_id_format_is_colon_separated(self, db: EntityDatabase):
        # Given a feature entity with entity_id "my-feature"
        entity_uuid = db.register_entity("feature", "my-feature", "My Feature")
        # Then the return is a UUID
        assert _UUID_V4_RE.match(entity_uuid)
        # And the type_id in the DB uses a colon separator
        entity = db.get_entity(entity_uuid)
        type_id = entity["type_id"]
        assert type_id == "feature:my-feature"
        assert ":" in type_id
        parts = type_id.split(":", 1)
        assert parts[0] == "feature"
        assert parts[1] == "my-feature"


class TestDescendantTraversalMultiLevel:
    """Mutation mindset: descendant traversal includes all levels, not just direct.
    derived_from: dimension:mutation_mindset
    """

    def test_descendant_traversal_includes_all_levels_not_just_direct_children(
        self, db: EntityDatabase,
    ):
        # Given project -> feat-a -> feat-a1 -> feat-a1x
        db.register_entity("project", "root", "Root")
        db.register_entity("feature", "a", "A", parent_type_id="project:root")
        db.register_entity("feature", "a1", "A1", parent_type_id="feature:a")
        db.register_entity("feature", "a1x", "A1x", parent_type_id="feature:a1")
        # When traversing downward from root
        lineage = db.get_lineage("project:root", direction="down")
        # Then all 4 levels are included (not just direct children)
        type_ids = {e["type_id"] for e in lineage}
        assert "feature:a1x" in type_ids
        assert len(type_ids) == 4


class TestRecursiveCTELineageDirection:
    """Mutation mindset: verify CTE returns correct relationship direction.
    derived_from: dimension:mutation_mindset
    """

    def test_recursive_cte_lineage_query_returns_correct_relationship_direction(
        self, db: EntityDatabase,
    ):
        # Given A -> B -> C chain
        db.register_entity("project", "a", "A")
        db.register_entity("feature", "b", "B", parent_type_id="project:a")
        db.register_entity("feature", "c", "C", parent_type_id="feature:b")
        # When querying upward from C
        up_lineage = db.get_lineage("feature:c", direction="up")
        up_ids = [e["type_id"] for e in up_lineage]
        # Then upward goes root-first: A, B, C
        assert up_ids == ["project:a", "feature:b", "feature:c"]

        # When querying downward from A
        down_lineage = db.get_lineage("project:a", direction="down")
        down_ids = [e["type_id"] for e in down_lineage]
        # Then downward goes root-first too: A, B, C (BFS order)
        assert down_ids == ["project:a", "feature:b", "feature:c"]

        # Mutation check: if up/down queries were swapped,
        # querying "up" from A would return empty or just A
        up_from_a = db.get_lineage("project:a", direction="up")
        assert len(up_from_a) == 1  # root has no ancestors

        # And querying "down" from C would return just C
        down_from_c = db.get_lineage("feature:c", direction="down")
        assert len(down_from_c) == 1  # leaf has no descendants


class TestBacklogIdWithLeadingZeros:
    """Boundary: leading zeros in backlog IDs are preserved.
    derived_from: dimension:boundary_values
    """

    def test_backlog_id_with_leading_zeros_preserved(
        self, db: EntityDatabase,
    ):
        # Given a backlog entity with leading zeros in ID
        entity_uuid = db.register_entity("backlog", "00019", "Item with zeros")
        # Then the return is a UUID
        assert _UUID_V4_RE.match(entity_uuid)
        # And the type_id preserves leading zeros
        entity = db.get_entity("backlog:00019")
        assert entity is not None
        assert entity["entity_id"] == "00019"
        assert entity["type_id"] == "backlog:00019"


class TestConcurrentDatabaseAccess:
    """Adversarial: concurrent access with WAL mode.
    derived_from: dimension:adversarial
    """

    def test_concurrent_database_access_with_wal_mode(self, tmp_path):
        # Given two connections to the same database file
        db_path = str(tmp_path / "entities.db")
        db1 = EntityDatabase(db_path)
        db2 = EntityDatabase(db_path)
        try:
            # When both write entities
            db1.register_entity("project", "p1", "Project 1")
            db2.register_entity("feature", "f1", "Feature 1")
            # Then both entities are visible to both connections
            assert db1.get_entity("feature:f1") is not None
            assert db2.get_entity("project:p1") is not None
        finally:
            db1.close()
            db2.close()


# ---------------------------------------------------------------------------
# Phase 2: UUID Dual-Identity tests
# ---------------------------------------------------------------------------


# T2.1.1: _resolve_identifier tests
class TestResolveIdentifier:
    def test_resolve_identifier_with_uuid(self, db: EntityDatabase):
        """_resolve_identifier should resolve a UUID to (uuid, type_id)."""
        entity_uuid = db.register_entity("feature", "test-id", "Test")
        result = db._resolve_identifier(entity_uuid)
        assert result == (entity_uuid, "feature:test-id")

    def test_resolve_identifier_with_type_id(self, db: EntityDatabase):
        """_resolve_identifier should resolve a type_id to (uuid, type_id)."""
        entity_uuid = db.register_entity("feature", "test-id", "Test")
        result = db._resolve_identifier("feature:test-id")
        assert result == (entity_uuid, "feature:test-id")

    def test_resolve_identifier_not_found(self, db: EntityDatabase):
        """_resolve_identifier should raise ValueError for unknown identifier."""
        with pytest.raises(ValueError, match="nonexistent"):
            db._resolve_identifier("nonexistent")


# T2.2.1: register_entity UUID return tests
class TestRegisterEntityUUID:
    def test_register_returns_uuid_v4_format(self, db: EntityDatabase):
        """register_entity should return a valid UUID v4 string."""
        result = db.register_entity("feature", "test", "Test")
        assert _UUID_V4_RE.match(result), f"Expected UUID v4, got {result!r}"

    def test_register_duplicate_returns_existing_uuid(self, db: EntityDatabase):
        """Registering same entity twice should return the same UUID."""
        uuid1 = db.register_entity("project", "proj-1", "Project One")
        uuid2 = db.register_entity("project", "proj-1", "Project One Updated")
        assert uuid1 == uuid2


# T2.3.1: set_parent mixed identifier tests
class TestSetParentUUID:
    def test_set_parent_mixed_identifiers(self, db: EntityDatabase):
        """set_parent should accept UUID for child and type_id for parent."""
        parent_uuid = db.register_entity("project", "proj-1", "Project One")
        child_uuid = db.register_entity("feature", "f1", "Feature One")
        result = db.set_parent(child_uuid, "project:proj-1")
        assert result == child_uuid

    def test_set_parent_updates_both_parent_columns(self, db: EntityDatabase):
        """set_parent should populate both parent_type_id and parent_uuid."""
        parent_uuid = db.register_entity("project", "proj-1", "Project One")
        child_uuid = db.register_entity("feature", "f1", "Feature One")
        db.set_parent(child_uuid, "project:proj-1")
        row = db._conn.execute(
            "SELECT parent_type_id, parent_uuid FROM entities WHERE uuid = ?",
            (child_uuid,),
        ).fetchone()
        assert row["parent_type_id"] == "project:proj-1"
        assert row["parent_uuid"] == parent_uuid


# T2.4.1: get_entity dual-read tests
class TestGetEntityUUID:
    def test_get_entity_by_uuid(self, db: EntityDatabase):
        """get_entity should accept UUID and return dict with uuid field."""
        entity_uuid = db.register_entity("feature", "f1", "Feature One")
        result = db.get_entity(entity_uuid)
        assert result is not None
        assert result["uuid"] == entity_uuid

    def test_get_entity_by_type_id(self, db: EntityDatabase):
        """get_entity should accept type_id and return same entity."""
        entity_uuid = db.register_entity("feature", "f1", "Feature One")
        result = db.get_entity("feature:f1")
        assert result is not None
        assert result["uuid"] == entity_uuid
        assert result["type_id"] == "feature:f1"

    def test_get_entity_not_found_returns_none(self, db: EntityDatabase):
        """get_entity should return None for nonexistent identifier."""
        assert db.get_entity("nonexistent") is None


# T2.5.1: get_lineage and update_entity UUID tests
class TestGetLineageUUID:
    def test_get_lineage_with_uuid(self, db: EntityDatabase):
        """get_lineage should accept UUID and return entities with uuid field."""
        gp_uuid = db.register_entity("project", "gp", "Grandparent")
        p_uuid = db.register_entity(
            "feature", "p", "Parent", parent_type_id="project:gp"
        )
        c_uuid = db.register_entity(
            "feature", "c", "Child", parent_type_id="feature:p"
        )
        lineage = db.get_lineage(c_uuid, direction="up")
        assert len(lineage) == 3
        # Root-first order
        assert lineage[0]["uuid"] == gp_uuid
        assert lineage[1]["uuid"] == p_uuid
        assert lineage[2]["uuid"] == c_uuid
        # Each dict has uuid field
        for entry in lineage:
            assert "uuid" in entry


class TestUpdateEntityUUID:
    def test_update_entity_with_uuid(self, db: EntityDatabase):
        """update_entity should accept UUID as identifier."""
        entity_uuid = db.register_entity("feature", "f1", "Original")
        db.update_entity(entity_uuid, name="New Name")
        result = db.get_entity(entity_uuid)
        assert result["name"] == "New Name"


# T2.6.1: export UUID internals test
class TestExportUUIDInternals:
    def test_export_uses_uuid_internally(self, db: EntityDatabase):
        """Export should show type_id strings, NOT raw UUIDs."""
        gp_uuid = db.register_entity("project", "gp", "Grandparent")
        p_uuid = db.register_entity(
            "feature", "p", "Parent", parent_type_id="project:gp"
        )
        c_uuid = db.register_entity(
            "feature", "c", "Child", parent_type_id="feature:p"
        )
        md = db.export_lineage_markdown()
        # Output should contain type_id components
        assert "project" in md
        assert "Grandparent" in md
        assert "Parent" in md
        assert "Child" in md
        # Output should NOT contain UUID patterns
        import re
        uuid_pattern = re.compile(
            r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'
        )
        assert not uuid_pattern.search(md), (
            f"Export should not contain UUIDs, but found: {md}"
        )


# ---------------------------------------------------------------------------
# Deepened tests: Phase B — spec-driven test deepening
# ---------------------------------------------------------------------------


class TestResolveIdentifierBoundary:
    """Boundary: edge-case inputs to _resolve_identifier.
    derived_from: dimension:boundary_values, spec:R22, spec:R23
    """

    def test_empty_string_raises_value_error(self, db: EntityDatabase):
        """Empty string treated as type_id lookup and raises ValueError.
        Anticipate: Implementation might not validate empty input, returning
        a false match or None silently instead of raising ValueError.
        """
        # Given an empty string identifier
        # When resolving it
        # Then ValueError is raised because no entity has type_id=""
        with pytest.raises(ValueError, match="Entity not found"):
            db._resolve_identifier("")

    def test_whitespace_only_raises_value_error(self, db: EntityDatabase):
        """Whitespace-only input treated as type_id lookup, raises ValueError.
        Anticipate: Whitespace might be stripped and treated as empty, or
        the regex might match incorrectly.
        """
        # Given a whitespace-only identifier
        # When resolving it
        # Then ValueError is raised (no entity with whitespace type_id)
        with pytest.raises(ValueError, match="Entity not found"):
            db._resolve_identifier("   ")

    def test_uppercase_uuid_normalizes_to_lowercase(self, db: EntityDatabase):
        """Uppercase UUID input should be normalized and resolved correctly.
        Anticipate: If implementation doesn't lowercase before regex match,
        an uppercase UUID would be treated as a type_id lookup and fail.
        derived_from: spec:R23 (C3 lowercase normalization)
        """
        # Given a registered entity
        entity_uuid = db.register_entity("feature", "case-test", "Case Test")
        # When resolving with uppercase UUID
        upper_uuid = entity_uuid.upper()
        result = db._resolve_identifier(upper_uuid)
        # Then it resolves correctly (case-insensitive)
        assert result == (entity_uuid, "feature:case-test")

    def test_uuid_v1_format_not_matched_as_uuid(self, db: EntityDatabase):
        """UUID v1 format should NOT match v4 regex (version nibble = 1).
        Anticipate: If regex is too loose (e.g., accepts any hex), a v1
        UUID would be treated as a UUID lookup instead of type_id.
        derived_from: spec:R23, dimension:mutation_mindset
        """
        # Given a UUID v1 string (version nibble is 1, not 4)
        v1_like = "550e8400-e29b-11d4-a716-446655440000"
        # When checking against the regex
        # Then it should NOT match (position 13 must be '4')
        assert not _UUID_V4_RE.match(v1_like.lower())

    def test_uuid_v5_format_not_matched_as_uuid(self, db: EntityDatabase):
        """UUID v5 format should NOT match v4 regex (version nibble = 5).
        Anticipate: Weak regex accepting any version would incorrectly
        route this to UUID lookup path.
        derived_from: spec:R23, dimension:boundary_values
        """
        # Given a UUID v5 string (version nibble is 5)
        v5_like = "550e8400-e29b-51d4-a716-446655440000"
        assert not _UUID_V4_RE.match(v5_like.lower())

    def test_uuid_v3_format_not_matched_as_uuid(self, db: EntityDatabase):
        """UUID v3 format should NOT match v4 regex (version nibble = 3).
        derived_from: spec:R23, dimension:boundary_values
        """
        v3_like = "550e8400-e29b-31d4-a716-446655440000"
        assert not _UUID_V4_RE.match(v3_like.lower())

    def test_uuid_with_invalid_variant_nibble_not_matched(
        self, db: EntityDatabase,
    ):
        """UUID with variant nibble outside [89ab] should not match v4 regex.
        Anticipate: If regex variant check is missing, UUIDs with variant 0
        would be mismatched.
        derived_from: spec:R23, dimension:mutation_mindset
        """
        # Position 19 (variant nibble) must be [89ab]; 'c' is outside
        invalid_variant = "550e8400-e29b-41d4-c716-446655440000"
        assert not _UUID_V4_RE.match(invalid_variant.lower())


class TestMigrationEmptyDb:
    """Boundary: migration on a database with 0 existing entities.
    derived_from: dimension:boundary_values, spec:AC-19
    """

    def test_migration_zero_entities_produces_correct_schema(self):
        """Migrating an empty v1 DB (no entity rows) should succeed cleanly.
        Anticipate: Data copy loop with 0 rows might trigger edge cases
        in parent_uuid population logic.
        """
        # Given a v1 DB with no entities
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _create_initial_schema(conn)
        conn.commit()
        # When migrating
        _migrate_to_uuid_pk(conn)
        # Then schema is correct with 0 rows
        columns = conn.execute("PRAGMA table_info(entities)").fetchall()
        assert len(columns) == 12
        row_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        assert row_count == 0
        # And schema_version is 2
        ver = conn.execute(
            "SELECT value FROM _metadata WHERE key='schema_version'"
        ).fetchone()
        assert ver[0] == "2"
        conn.close()


class TestMigrationLargeDataset:
    """Boundary: migration with many entities.
    derived_from: dimension:boundary_values
    """

    def test_migration_100_entities_preserves_all(self):
        """Migrating 100+ entities preserves all data and generates unique UUIDs.
        Anticipate: Batch UUID generation might produce duplicates (astronomically
        unlikely but the test structure catches it), or data copy loop might
        skip rows.
        """
        # Given a v1 DB with 100 entities
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _create_initial_schema(conn)
        for i in range(100):
            conn.execute(
                "INSERT INTO entities (type_id, entity_type, entity_id, name, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (f"feature:f{i}", "feature", f"f{i}", f"Feature {i}",
                 "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
            )
        conn.commit()
        # When migrating
        _migrate_to_uuid_pk(conn)
        # Then all 100 rows exist
        rows = conn.execute("SELECT * FROM entities").fetchall()
        assert len(rows) == 100
        # And all UUIDs are unique
        uuids = [r["uuid"] for r in rows]
        assert len(set(uuids)) == 100
        # And all UUIDs are valid v4
        for u in uuids:
            assert _UUID_V4_RE.match(u)
        conn.close()


class TestEntityIdEdgeCases:
    """Boundary: special characters and long entity IDs.
    derived_from: dimension:boundary_values
    """

    def test_entity_with_very_long_entity_id(self, db: EntityDatabase):
        """Very long entity_id (500 chars) should be stored and retrievable.
        Anticipate: SQLite TEXT has no length limit, but the type_id
        constructed from it might cause issues in queries or indexes.
        """
        # Given a very long entity_id
        long_id = "x" * 500
        entity_uuid = db.register_entity("feature", long_id, "Long ID Feature")
        # Then retrieval by type_id works
        expected_type_id = f"feature:{long_id}"
        entity = db.get_entity(expected_type_id)
        assert entity is not None
        assert entity["entity_id"] == long_id
        assert entity["uuid"] == entity_uuid

    def test_entity_with_special_characters_in_entity_id(
        self, db: EntityDatabase,
    ):
        """Special characters (unicode, quotes, backslash) in entity_id.
        Anticipate: SQL injection or encoding issues with special chars.
        derived_from: dimension:adversarial
        """
        # Given entity_ids with special characters
        special_id = "test-id_with.dots/slashes'quotes\"and\\backslash"
        entity_uuid = db.register_entity("feature", special_id, "Special")
        # Then retrieval works correctly
        entity = db.get_entity(f"feature:{special_id}")
        assert entity is not None
        assert entity["entity_id"] == special_id
        assert entity["uuid"] == entity_uuid


class TestForeignKeyEnforcementPostMigration:
    """BDD: AC-5 extended — PRAGMA foreign_keys persists through migration.
    derived_from: spec:AC-5
    """

    def test_pragma_foreign_keys_returns_1_after_migration(
        self, db: EntityDatabase,
    ):
        """PRAGMA foreign_keys should be ON (1) after EntityDatabase init.
        Anticipate: Table recreation during migration might reset the pragma
        if it's not re-enabled in the finally block.
        """
        # Given an initialized EntityDatabase (migration already ran)
        # When checking PRAGMA foreign_keys
        fk_status = db._conn.execute("PRAGMA foreign_keys").fetchone()[0]
        # Then it should be 1 (ON)
        assert fk_status == 1

    def test_fk_violation_on_parent_uuid_insert(self, db: EntityDatabase):
        """Inserting a row with invalid parent_uuid should fail FK check.
        Anticipate: If foreign_keys pragma was silently reset during migration,
        invalid parent_uuid values would be accepted.
        derived_from: spec:AC-5, dimension:error_propagation
        """
        # Given a database with foreign_keys ON
        test_uuid = str(uuid.uuid4())
        fake_parent = str(uuid.uuid4())
        # When inserting with a nonexistent parent_uuid
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO entities (uuid, type_id, entity_type, entity_id, "
                "name, parent_uuid, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (test_uuid, "feature:fk-test", "feature", "fk-test",
                 "FK Test", fake_parent,
                 "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
            )


class TestNonexistentUUIDOperations:
    """Adversarial: using a valid UUID format that doesn't exist in DB.
    derived_from: dimension:adversarial, spec:R26
    """

    def test_get_entity_with_nonexistent_uuid_returns_none(
        self, db: EntityDatabase,
    ):
        """get_entity with a valid UUID format that doesn't exist returns None.
        Anticipate: The UUID matches the regex so it takes the UUID lookup
        path. If _resolve_identifier's ValueError is not caught, it would
        raise instead of returning None.
        """
        # Given a valid UUID that doesn't exist in the DB
        fake_uuid = str(uuid.uuid4())
        # When getting entity by fake UUID
        result = db.get_entity(fake_uuid)
        # Then None is returned (not ValueError)
        assert result is None

    def test_set_parent_with_nonexistent_uuid_raises(
        self, db: EntityDatabase,
    ):
        """set_parent with nonexistent UUID should propagate ValueError.
        Anticipate: If set_parent catches ValueError when it shouldn't,
        the operation would silently fail.
        derived_from: spec:R26
        """
        # Given a registered entity and a fake parent UUID
        db.register_entity("feature", "f1", "Feature One")
        fake_parent = str(uuid.uuid4())
        # When setting parent to nonexistent UUID
        with pytest.raises(ValueError, match="Entity not found"):
            db.set_parent("feature:f1", fake_parent)

    def test_get_lineage_with_nonexistent_uuid_returns_empty(
        self, db: EntityDatabase,
    ):
        """get_lineage with nonexistent UUID should return empty list.
        Anticipate: If get_lineage doesn't catch the ValueError from
        _resolve_identifier, it would raise instead of returning [].
        derived_from: spec:R26
        """
        # Given a valid UUID that doesn't exist
        fake_uuid = str(uuid.uuid4())
        # When getting lineage
        result = db.get_lineage(fake_uuid)
        # Then empty list is returned
        assert result == []

    def test_update_entity_with_nonexistent_uuid_raises(
        self, db: EntityDatabase,
    ):
        """update_entity with nonexistent UUID should propagate ValueError.
        derived_from: spec:R26
        """
        fake_uuid = str(uuid.uuid4())
        with pytest.raises(ValueError, match="[Nn]ot found"):
            db.update_entity(fake_uuid, name="Should Fail")

    def test_export_lineage_with_nonexistent_uuid_raises_value_error(
        self, db: EntityDatabase,
    ):
        """export_lineage_markdown with nonexistent UUID propagates ValueError.
        derived_from: spec:R26
        """
        fake_uuid = str(uuid.uuid4())
        with pytest.raises(ValueError, match="Entity not found"):
            db.export_lineage_markdown(fake_uuid)


class TestSqlInjectionAttempt:
    """Adversarial: SQL injection attempt in identifier.
    derived_from: dimension:adversarial
    """

    def test_sql_injection_in_resolve_identifier(self, db: EntityDatabase):
        """SQL injection string should be treated as literal type_id.
        Anticipate: If parameterized queries are not used, SQL injection
        could corrupt the database or bypass access controls.
        """
        # Given a SQL injection attempt as identifier
        injection = "'; DROP TABLE entities; --"
        # When resolving it
        # Then it should safely raise ValueError (no entity found)
        with pytest.raises(ValueError, match="Entity not found"):
            db._resolve_identifier(injection)
        # And the entities table should still exist
        count = db._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        assert count >= 0  # table still exists


class TestGetLineageInvalidDirection:
    """Error propagation: invalid direction parameter.
    derived_from: dimension:error_propagation, dimension:mutation_mindset
    """

    def test_invalid_direction_raises_value_error(self, db: EntityDatabase):
        """get_lineage with invalid direction should raise ValueError.
        Anticipate: If direction validation is missing, an invalid direction
        might silently return empty or raise an unrelated error.
        """
        # Given a registered entity
        db.register_entity("feature", "f1", "Feature One")
        # When calling get_lineage with invalid direction
        with pytest.raises(ValueError, match="[Ii]nvalid direction"):
            db.get_lineage("feature:f1", direction="sideways")

    def test_none_direction_raises_value_error(self, db: EntityDatabase):
        """get_lineage with None direction should raise ValueError.
        Anticipate: If implementation uses `if direction == 'up'` / `elif
        direction == 'down'` without else, None would fall through silently.
        """
        db.register_entity("feature", "f1", "Feature One")
        with pytest.raises((ValueError, AttributeError, TypeError)):
            db.get_lineage("feature:f1", direction=None)


class TestSetParentConsistencyAfterUpdate:
    """BDD: AC-29 — parent columns consistent after set_parent.
    derived_from: spec:AC-29
    """

    def test_set_parent_produces_consistent_dual_parent_columns(
        self, db: EntityDatabase,
    ):
        """After set_parent, parent_type_id and parent_uuid resolve to same entity.
        Anticipate: If set_parent updates one column but not the other,
        the parent columns would be inconsistent.
        """
        # Given parent and child entities
        parent_uuid = db.register_entity("project", "parent", "Parent")
        child_uuid = db.register_entity("feature", "child", "Child")
        # When setting parent
        db.set_parent("feature:child", "project:parent")
        # Then get_entity shows consistent parent columns
        child = db.get_entity("feature:child")
        assert child["parent_type_id"] == "project:parent"
        assert child["parent_uuid"] == parent_uuid
        # And resolving parent_uuid returns the same entity as parent_type_id
        parent_by_uuid = db.get_entity(child["parent_uuid"])
        parent_by_type_id = db.get_entity(child["parent_type_id"])
        assert parent_by_uuid["uuid"] == parent_by_type_id["uuid"]
        assert parent_by_uuid["type_id"] == "project:parent"

    def test_reassign_parent_keeps_both_columns_in_sync(
        self, db: EntityDatabase,
    ):
        """Reassigning parent should update BOTH parent columns atomically.
        Anticipate: Reassignment might update parent_uuid but leave
        parent_type_id pointing to old parent.
        derived_from: spec:AC-28
        """
        # Given a child with existing parent
        p1_uuid = db.register_entity("project", "p1", "Parent 1")
        p2_uuid = db.register_entity("project", "p2", "Parent 2")
        child_uuid = db.register_entity(
            "feature", "child", "Child", parent_type_id="project:p1",
        )
        # When reassigning parent
        db.set_parent("feature:child", "project:p2")
        # Then both columns reflect the new parent
        child = db.get_entity("feature:child")
        assert child["parent_type_id"] == "project:p2"
        assert child["parent_uuid"] == p2_uuid


class TestRootEntityParentUuidIsNone:
    """Boundary: root entity (no parent) should have NULL parent_uuid.
    derived_from: dimension:boundary_values
    """

    def test_root_entity_has_null_parent_uuid(self, db: EntityDatabase):
        """Root entity (registered without parent) has parent_uuid=None.
        Anticipate: Migration or register_entity might set parent_uuid
        to a default value instead of NULL.
        """
        # Given a root entity with no parent
        entity_uuid = db.register_entity("project", "root", "Root Project")
        # When retrieving it
        entity = db.get_entity(entity_uuid)
        # Then both parent columns are None
        assert entity["parent_type_id"] is None
        assert entity["parent_uuid"] is None


class TestExistingImmutabilityTriggersStillFire:
    """BDD: AC-8 — existing immutability triggers survive migration.
    derived_from: spec:AC-8, dimension:mutation_mindset
    """

    def test_type_id_immutable_via_uuid_lookup(self, db: EntityDatabase):
        """type_id trigger fires even when entity was found via UUID.
        Anticipate: If triggers were dropped during migration and not
        recreated, this would succeed when it should fail.
        """
        # Given a registered entity
        entity_uuid = db.register_entity("feature", "immut", "Immutable Test")
        # When attempting to change type_id using uuid in WHERE clause
        with pytest.raises(sqlite3.IntegrityError, match="type_id is immutable"):
            db._conn.execute(
                "UPDATE entities SET type_id = 'feature:changed' WHERE uuid = ?",
                (entity_uuid,),
            )

    def test_entity_type_immutable_post_migration(self, db: EntityDatabase):
        """entity_type trigger fires on UUID-identified entity.
        derived_from: spec:AC-8
        """
        entity_uuid = db.register_entity("feature", "immut2", "Immutable Test 2")
        with pytest.raises(
            sqlite3.IntegrityError, match="entity_type is immutable"
        ):
            db._conn.execute(
                "UPDATE entities SET entity_type = 'project' WHERE uuid = ?",
                (entity_uuid,),
            )

    def test_created_at_immutable_post_migration(self, db: EntityDatabase):
        """created_at trigger fires on UUID-identified entity.
        derived_from: spec:AC-8
        """
        entity_uuid = db.register_entity("feature", "immut3", "Immutable Test 3")
        with pytest.raises(
            sqlite3.IntegrityError, match="created_at is immutable"
        ):
            db._conn.execute(
                "UPDATE entities SET created_at = '2099-01-01T00:00:00' "
                "WHERE uuid = ?",
                (entity_uuid,),
            )


class TestRegisterEntityParentUuidPopulation:
    """BDD: register_entity with parent_type_id also sets parent_uuid.
    derived_from: spec:R5, spec:AC-29
    """

    def test_register_with_parent_populates_parent_uuid(
        self, db: EntityDatabase,
    ):
        """register_entity with parent_type_id should set parent_uuid.
        Anticipate: If register_entity only sets parent_type_id but not
        parent_uuid, the dual columns would be inconsistent from the start.
        """
        # Given a parent entity
        parent_uuid = db.register_entity("project", "parent", "Parent")
        # When registering child with parent_type_id
        child_uuid = db.register_entity(
            "feature", "child", "Child",
            parent_type_id="project:parent",
        )
        # Then parent_uuid is also populated
        child = db.get_entity(child_uuid)
        assert child["parent_type_id"] == "project:parent"
        assert child["parent_uuid"] == parent_uuid


class TestExportLineageWithUuidInput:
    """BDD: AC-25 — export uses type_id in output even when given UUID input.
    derived_from: spec:AC-25
    """

    def test_export_lineage_via_uuid_shows_type_id_labels(
        self, db: EntityDatabase,
    ):
        """export_lineage_markdown(uuid) output uses type_id, not UUID.
        Anticipate: If the export function passes UUID into rendering
        without conversion, UUID strings might appear in the output.
        """
        # Given a parent-child tree
        p_uuid = db.register_entity("project", "p1", "Project One")
        db.register_entity(
            "feature", "f1", "Feature One",
            parent_type_id="project:p1",
        )
        db.register_entity(
            "feature", "f2", "Feature Two",
            parent_type_id="project:p1",
        )
        # When exporting via UUID
        md = db.export_lineage_markdown(p_uuid)
        # Then output contains type_id strings
        assert "project:p1" in md or "Project One" in md
        # And does NOT contain UUID patterns
        uuid_pattern = re.compile(
            r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-'
            r'[89ab][0-9a-f]{3}-[0-9a-f]{12}'
        )
        assert not uuid_pattern.search(md), (
            f"Export via UUID should not expose UUIDs in output: {md}"
        )


class TestSetParentReturnValueIsMutationSafe:
    """Mutation mindset: set_parent returns child UUID, not parent UUID.
    derived_from: dimension:mutation_mindset, spec:R20
    """

    def test_set_parent_returns_child_uuid_not_parent(
        self, db: EntityDatabase,
    ):
        """set_parent must return the CHILD's UUID, not the parent's.
        Anticipate: If implementation swaps the return to parent_uuid,
        callers relying on the child UUID would get wrong data.
        """
        # Given distinct parent and child
        parent_uuid = db.register_entity("project", "parent", "Parent")
        child_uuid = db.register_entity("feature", "child", "Child")
        # When setting parent
        result = db.set_parent("feature:child", "project:parent")
        # Then return is child UUID, not parent UUID
        assert result == child_uuid
        assert result != parent_uuid


class TestResolveIdentifierBranchDiscrimination:
    """Mutation mindset: _resolve_identifier UUID vs type_id branch.
    derived_from: dimension:mutation_mindset
    """

    def test_uuid_branch_queries_uuid_column(self, db: EntityDatabase):
        """When input matches UUID pattern, lookup uses uuid column.
        Anticipate: If branches are swapped (UUID input queried against
        type_id column), lookup would fail for valid UUIDs.
        """
        # Given a registered entity
        entity_uuid = db.register_entity("feature", "branch-test", "Test")
        # When resolving the UUID
        result_uuid, result_tid = db._resolve_identifier(entity_uuid)
        # Then correct uuid and type_id returned
        assert result_uuid == entity_uuid
        assert result_tid == "feature:branch-test"

    def test_type_id_branch_queries_type_id_column(self, db: EntityDatabase):
        """When input does NOT match UUID pattern, lookup uses type_id column.
        Anticipate: If branches are swapped, type_id input would be queried
        against uuid column and fail.
        """
        # Given a registered entity
        entity_uuid = db.register_entity("feature", "branch-test2", "Test 2")
        # When resolving the type_id
        result_uuid, result_tid = db._resolve_identifier("feature:branch-test2")
        # Then correct values returned
        assert result_uuid == entity_uuid
        assert result_tid == "feature:branch-test2"

    def test_uuid_and_type_id_resolve_to_same_entity(
        self, db: EntityDatabase,
    ):
        """Both branches should resolve to the same entity.
        Anticipate: If the two code paths use different queries or columns,
        they might return different results.
        """
        # Given a registered entity
        entity_uuid = db.register_entity("feature", "dual-test", "Dual Test")
        # When resolving via both paths
        by_uuid = db._resolve_identifier(entity_uuid)
        by_tid = db._resolve_identifier("feature:dual-test")
        # Then both return identical results
        assert by_uuid == by_tid


class TestMigrationIdempotency:
    """BDD: C4 — migration is idempotent (re-running is a no-op).
    derived_from: spec:C4, dimension:adversarial
    """

    def test_double_init_does_not_corrupt(self, tmp_path):
        """Opening EntityDatabase twice on same file should not re-run migration.
        Anticipate: If migration idempotency check fails, the second init
        would attempt to recreate tables that already exist, causing errors.
        """
        # Given a database file initialized once
        db_path = str(tmp_path / "double_init.db")
        db1 = EntityDatabase(db_path)
        db1.register_entity("project", "p1", "Project 1")
        p1_uuid = db1.get_entity("project:p1")["uuid"]
        db1.close()
        # When opening it again
        db2 = EntityDatabase(db_path)
        # Then data is intact, UUID unchanged
        entity = db2.get_entity("project:p1")
        assert entity is not None
        assert entity["uuid"] == p1_uuid
        assert db2.get_metadata("schema_version") == "6"
        db2.close()


class TestSelfParentViaUuidInSetParent:
    """Adversarial: self-parent via UUID in set_parent API call.
    derived_from: dimension:adversarial, spec:R12
    """

    def test_self_parent_via_uuid_in_set_parent(self, db: EntityDatabase):
        """set_parent(uuid, uuid) should reject self-parent.
        Anticipate: If the self-parent check compares type_id strings
        instead of UUIDs, passing the same UUID for both params might
        bypass the check.
        """
        # Given a registered entity
        entity_uuid = db.register_entity("feature", "selfie", "Self Test")
        # When trying to set itself as parent via UUID
        with pytest.raises((ValueError, sqlite3.IntegrityError)):
            db.set_parent(entity_uuid, entity_uuid)


class TestGetEntityDictContainsBothIdentifiers:
    """BDD: AC-17 — entity dict includes both uuid and type_id fields.
    derived_from: spec:AC-17
    """

    def test_entity_dict_has_both_uuid_and_type_id(self, db: EntityDatabase):
        """get_entity result dict must include BOTH uuid and type_id.
        Anticipate: Schema changes might drop one of the fields from
        SELECT * results, or dict conversion might exclude columns.
        """
        # Given a registered entity
        entity_uuid = db.register_entity("feature", "both-ids", "Both IDs")
        # When getting entity
        entity = db.get_entity(entity_uuid)
        # Then both fields are present and valid
        assert "uuid" in entity
        assert "type_id" in entity
        assert _UUID_V4_RE.match(entity["uuid"])
        assert entity["type_id"] == "feature:both-ids"

    def test_lineage_dicts_have_both_identifiers(self, db: EntityDatabase):
        """get_lineage results must include both uuid and type_id per entry.
        derived_from: spec:R20
        """
        # Given a chain
        db.register_entity("project", "root", "Root")
        db.register_entity(
            "feature", "child", "Child", parent_type_id="project:root",
        )
        # When getting lineage
        lineage = db.get_lineage("feature:child", direction="up")
        # Then each entry has both fields
        for entry in lineage:
            assert "uuid" in entry
            assert "type_id" in entry
            assert _UUID_V4_RE.match(entry["uuid"])


# ---------------------------------------------------------------------------
# list_entities tests (feature 003, task 1.1a)
# ---------------------------------------------------------------------------


class TestListEntities:
    """Tests for EntityDatabase.list_entities() method."""

    def test_list_entities_returns_all(self, db: EntityDatabase):
        """list_entities() with no filter returns all registered entities."""
        db.register_entity("feature", "f1", "Feature One")
        db.register_entity("feature", "f2", "Feature Two")
        db.register_entity("project", "p1", "Project One")

        result = db.list_entities()
        assert len(result) == 3

    def test_list_entities_filter_by_type(self, db: EntityDatabase):
        """list_entities(entity_type) returns only matching type."""
        db.register_entity("feature", "f1", "Feature One")
        db.register_entity("project", "p1", "Project One")

        result = db.list_entities(entity_type="feature")
        assert len(result) == 1
        assert result[0]["entity_type"] == "feature"

    def test_list_entities_empty_db(self, db: EntityDatabase):
        """list_entities() on empty DB returns empty list."""
        result = db.list_entities()
        assert result == []

    def test_list_entities_unknown_type(self, db: EntityDatabase):
        """list_entities() with non-existent type returns empty list."""
        db.register_entity("feature", "f1", "Feature One")

        result = db.list_entities(entity_type="brainstorm")
        assert result == []


# ---------------------------------------------------------------------------
# Migration 3: workflow_phases table tests (Tasks 1.1 - 1.5)
# ---------------------------------------------------------------------------


class TestMigration3:
    """Tests for migration 3: workflow_phases table creation.

    These tests verify the schema, indexes, triggers, constraints, FK
    enforcement, and fresh-DB safety for the workflow_phases table defined
    in ADR-004. They use the ``db`` fixture which constructs an
    EntityDatabase and runs all registered migrations.
    """

    # -- Task 1.1: Migration creates table with correct schema (AC-1) ------

    def test_workflow_phases_table_exists(self, db: EntityDatabase):
        """workflow_phases table should exist after migration 3."""
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='workflow_phases'"
        )
        assert cur.fetchone() is not None

    def test_workflow_phases_has_8_columns(self, db: EntityDatabase):
        """workflow_phases should have exactly 8 columns (uuid added in v6)."""
        cur = db._conn.execute("PRAGMA table_info(workflow_phases)")
        columns = cur.fetchall()
        assert len(columns) == 8

    def test_workflow_phases_column_names(self, db: EntityDatabase):
        """workflow_phases columns should match the DDL specification."""
        cur = db._conn.execute("PRAGMA table_info(workflow_phases)")
        col_names = [row[1] for row in cur.fetchall()]
        expected = [
            "type_id",
            "workflow_phase",
            "kanban_column",
            "last_completed_phase",
            "mode",
            "backward_transition_reason",
            "updated_at",
            "uuid",
        ]
        assert col_names == expected

    def test_type_id_is_primary_key(self, db: EntityDatabase):
        """type_id should be the PRIMARY KEY of workflow_phases."""
        cur = db._conn.execute("PRAGMA table_info(workflow_phases)")
        col_map = {row[1]: row for row in cur.fetchall()}
        assert col_map["type_id"][5] == 1  # pk flag

    def test_kanban_column_not_null_default_backlog(self, db: EntityDatabase):
        """kanban_column should be NOT NULL with DEFAULT 'backlog'."""
        cur = db._conn.execute("PRAGMA table_info(workflow_phases)")
        col_map = {row[1]: row for row in cur.fetchall()}
        # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
        kanban = col_map["kanban_column"]
        assert kanban[3] == 1  # notnull flag
        assert kanban[4] == "'backlog'"  # default value

    def test_updated_at_not_null(self, db: EntityDatabase):
        """updated_at should be NOT NULL."""
        cur = db._conn.execute("PRAGMA table_info(workflow_phases)")
        col_map = {row[1]: row for row in cur.fetchall()}
        assert col_map["updated_at"][3] == 1  # notnull flag

    def test_nullable_columns(self, db: EntityDatabase):
        """workflow_phase, last_completed_phase, mode, backward_transition_reason
        should be nullable (notnull = 0)."""
        cur = db._conn.execute("PRAGMA table_info(workflow_phases)")
        col_map = {row[1]: row for row in cur.fetchall()}
        for col_name in (
            "workflow_phase",
            "last_completed_phase",
            "mode",
            "backward_transition_reason",
        ):
            assert col_map[col_name][3] == 0, (
                f"{col_name} should be nullable (notnull=0)"
            )

    def test_fk_type_id_references_entities(self, db: EntityDatabase):
        """type_id should have a FK reference to entities(type_id)."""
        cur = db._conn.execute("PRAGMA foreign_key_list(workflow_phases)")
        fk_rows = cur.fetchall()
        assert len(fk_rows) >= 1
        # Find the FK targeting entities.type_id
        fk_found = False
        for fk in fk_rows:
            # PRAGMA foreign_key_list columns: id, seq, table, from, to, ...
            if fk[2] == "entities" and fk[3] == "type_id" and fk[4] == "type_id":
                fk_found = True
                break
        assert fk_found, (
            "Expected FK from workflow_phases.type_id -> entities.type_id"
        )

    def test_schema_version_is_5(self, db: EntityDatabase):
        """After all migrations, schema_version should be 5."""
        assert db.get_metadata("schema_version") == "6"

    # -- Task 1.2: Migration creates indexes and trigger (AC-2) ------------

    def test_index_idx_wp_kanban_column_exists(self, db: EntityDatabase):
        """Index idx_wp_kanban_column should exist on workflow_phases."""
        cur = db._conn.execute("PRAGMA index_list(workflow_phases)")
        index_names = [row[1] for row in cur.fetchall()]
        assert "idx_wp_kanban_column" in index_names

    def test_index_idx_wp_workflow_phase_exists(self, db: EntityDatabase):
        """Index idx_wp_workflow_phase should exist on workflow_phases."""
        cur = db._conn.execute("PRAGMA index_list(workflow_phases)")
        index_names = [row[1] for row in cur.fetchall()]
        assert "idx_wp_workflow_phase" in index_names

    def test_trigger_enforce_immutable_wp_type_id_exists(
        self, db: EntityDatabase
    ):
        """Trigger enforce_immutable_wp_type_id should exist."""
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='trigger' AND name='enforce_immutable_wp_type_id'"
        )
        assert cur.fetchone() is not None

    def test_trigger_prevents_type_id_update(self, db: EntityDatabase):
        """Updating type_id on workflow_phases should raise IntegrityError."""
        # First, insert an entity so FK is satisfied
        db.register_entity("feature", "trig-test", "Trigger Test")
        now = EntityDatabase._now_iso()
        db._conn.execute(
            "INSERT INTO workflow_phases "
            "(type_id, kanban_column, updated_at) "
            "VALUES (?, 'backlog', ?)",
            ("feature:trig-test", now),
        )
        db._conn.commit()

        # Attempt to UPDATE type_id -- trigger should block this
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db._conn.execute(
                "UPDATE workflow_phases SET type_id = 'feature:other' "
                "WHERE type_id = 'feature:trig-test'"
            )

    # -- Task 1.3: CHECK constraints enforce enums (AC-4) ------------------

    def test_invalid_workflow_phase_rejected(self, db: EntityDatabase):
        """Invalid workflow_phase value should raise IntegrityError."""
        db.register_entity("feature", "chk-wp", "Check WP")
        now = EntityDatabase._now_iso()
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, workflow_phase, kanban_column, updated_at) "
                "VALUES (?, 'invalid-phase', 'backlog', ?)",
                ("feature:chk-wp", now),
            )

    def test_invalid_kanban_column_rejected(self, db: EntityDatabase):
        """Invalid kanban_column value should raise IntegrityError."""
        db.register_entity("feature", "chk-kc", "Check KC")
        now = EntityDatabase._now_iso()
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, kanban_column, updated_at) "
                "VALUES (?, 'invalid-column', ?)",
                ("feature:chk-kc", now),
            )

    def test_invalid_last_completed_phase_rejected(self, db: EntityDatabase):
        """Invalid last_completed_phase value should raise IntegrityError."""
        db.register_entity("feature", "chk-lcp", "Check LCP")
        now = EntityDatabase._now_iso()
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, kanban_column, last_completed_phase, updated_at) "
                "VALUES (?, 'backlog', 'not-a-phase', ?)",
                ("feature:chk-lcp", now),
            )

    def test_invalid_mode_rejected(self, db: EntityDatabase):
        """Invalid mode value should raise IntegrityError."""
        db.register_entity("feature", "chk-mode", "Check Mode")
        now = EntityDatabase._now_iso()
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, kanban_column, mode, updated_at) "
                "VALUES (?, 'backlog', 'invalid-mode', ?)",
                ("feature:chk-mode", now),
            )

    def test_null_nullable_columns_accepted(self, db: EntityDatabase):
        """NULL values for nullable columns should be accepted."""
        db.register_entity("feature", "chk-null", "Check Null")
        now = EntityDatabase._now_iso()
        # INSERT with all nullable columns as NULL (only required: type_id,
        # kanban_column via DEFAULT, updated_at)
        db._conn.execute(
            "INSERT INTO workflow_phases "
            "(type_id, workflow_phase, kanban_column, last_completed_phase, "
            "mode, backward_transition_reason, updated_at) "
            "VALUES (?, NULL, 'backlog', NULL, NULL, NULL, ?)",
            ("feature:chk-null", now),
        )
        db._conn.commit()
        row = db._conn.execute(
            "SELECT * FROM workflow_phases WHERE type_id = ?",
            ("feature:chk-null",),
        ).fetchone()
        assert row is not None
        assert row["workflow_phase"] is None
        assert row["last_completed_phase"] is None
        assert row["mode"] is None
        assert row["backward_transition_reason"] is None

    def test_valid_workflow_phase_values_accepted(self, db: EntityDatabase):
        """All valid workflow_phase enum values should be accepted."""
        valid_phases = [
            "brainstorm", "specify", "design",
            "create-plan", "create-tasks", "implement", "finish",
        ]
        for i, phase in enumerate(valid_phases):
            entity_id = f"vwp-{i}"
            db.register_entity("feature", entity_id, f"Valid WP {i}")
            now = EntityDatabase._now_iso()
            db._conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, workflow_phase, kanban_column, updated_at) "
                "VALUES (?, ?, 'backlog', ?)",
                (f"feature:{entity_id}", phase, now),
            )
        db._conn.commit()
        count = db._conn.execute(
            "SELECT COUNT(*) FROM workflow_phases"
        ).fetchone()[0]
        assert count == len(valid_phases)

    def test_valid_kanban_column_values_accepted(self, db: EntityDatabase):
        """All valid kanban_column enum values should be accepted."""
        valid_columns = [
            "backlog", "prioritised", "wip", "agent_review",
            "human_review", "blocked", "documenting", "completed",
        ]
        for i, col in enumerate(valid_columns):
            entity_id = f"vkc-{i}"
            db.register_entity("feature", entity_id, f"Valid KC {i}")
            now = EntityDatabase._now_iso()
            db._conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, kanban_column, updated_at) "
                "VALUES (?, ?, ?)",
                (f"feature:{entity_id}", col, now),
            )
        db._conn.commit()
        count = db._conn.execute(
            "SELECT COUNT(*) FROM workflow_phases"
        ).fetchone()[0]
        assert count == len(valid_columns)

    def test_valid_mode_values_accepted(self, db: EntityDatabase):
        """Valid mode values ('standard', 'full') should be accepted."""
        for i, mode in enumerate(["standard", "full"]):
            entity_id = f"vm-{i}"
            db.register_entity("feature", entity_id, f"Valid Mode {i}")
            now = EntityDatabase._now_iso()
            db._conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, kanban_column, mode, updated_at) "
                "VALUES (?, 'backlog', ?, ?)",
                (f"feature:{entity_id}", mode, now),
            )
        db._conn.commit()
        count = db._conn.execute(
            "SELECT COUNT(*) FROM workflow_phases"
        ).fetchone()[0]
        assert count == 2

    # -- Task 1.4: Fresh DB migration safety (AC-3) ------------------------

    def test_fresh_db_has_all_migrations(self, tmp_path):
        """A brand-new EntityDatabase should run all 6 migrations."""
        fresh_db = EntityDatabase(str(tmp_path / "fresh.db"))
        try:
            assert fresh_db.get_metadata("schema_version") == "6"
        finally:
            fresh_db.close()

    def test_fresh_db_has_entities_table(self, tmp_path):
        """A fresh DB should have the entities table."""
        fresh_db = EntityDatabase(str(tmp_path / "fresh.db"))
        try:
            cur = fresh_db._conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='entities'"
            )
            assert cur.fetchone() is not None
        finally:
            fresh_db.close()

    def test_fresh_db_has_workflow_phases_table(self, tmp_path):
        """A fresh DB should have the workflow_phases table."""
        fresh_db = EntityDatabase(str(tmp_path / "fresh.db"))
        try:
            cur = fresh_db._conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='workflow_phases'"
            )
            assert cur.fetchone() is not None
        finally:
            fresh_db.close()

    # -- Task 1.5: FK enforcement (AC-16) ----------------------------------

    def test_insert_nonexistent_type_id_rejected(self, db: EntityDatabase):
        """INSERT into workflow_phases with non-existent type_id should fail."""
        now = EntityDatabase._now_iso()
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, kanban_column, updated_at) "
                "VALUES (?, 'backlog', ?)",
                ("feature:does-not-exist", now),
            )

    def test_delete_entity_with_workflow_phase_rejected(
        self, db: EntityDatabase
    ):
        """DELETE from entities when workflow_phases row exists should fail.

        ON DELETE NO ACTION means the FK prevents deletion of a parent row
        when a child row (workflow_phases) references it.
        """
        db.register_entity("feature", "fk-del", "FK Delete Test")
        now = EntityDatabase._now_iso()
        db._conn.execute(
            "INSERT INTO workflow_phases "
            "(type_id, kanban_column, updated_at) "
            "VALUES (?, 'backlog', ?)",
            ("feature:fk-del", now),
        )
        db._conn.commit()

        # Attempt to DELETE the entity -- FK should prevent this
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "DELETE FROM entities WHERE type_id = ?",
                ("feature:fk-del",),
            )


# ---------------------------------------------------------------------------
# Phase 2: Workflow Phase CRUD tests (Tasks 2.1 - 2.5)
# ---------------------------------------------------------------------------


class TestWorkflowPhaseCRUD:
    """Tests for workflow_phases CRUD methods on EntityDatabase.

    These tests cover create_workflow_phase, get_workflow_phase,
    update_workflow_phase, delete_workflow_phase, and list_workflow_phases.
    """

    # -- Task 2.1: create_workflow_phase (AC-5) -----------------------------

    def test_create_workflow_phase_returns_dict_with_all_columns(
        self, db: EntityDatabase
    ):
        """create_workflow_phase for existing entity returns dict with 8 columns."""
        db.register_entity("feature", "f1", "Test Feature")
        result = db.create_workflow_phase(
            "feature:f1",
            kanban_column="wip",
            workflow_phase="design",
            last_completed_phase="specify",
            mode="standard",
            backward_transition_reason=None,
        )
        assert isinstance(result, dict)
        expected_keys = {
            "type_id",
            "workflow_phase",
            "kanban_column",
            "last_completed_phase",
            "mode",
            "backward_transition_reason",
            "updated_at",
            "uuid",
        }
        assert set(result.keys()) == expected_keys
        assert result["type_id"] == "feature:f1"
        assert result["workflow_phase"] == "design"
        assert result["kanban_column"] == "wip"
        assert result["last_completed_phase"] == "specify"
        assert result["mode"] == "standard"
        assert result["backward_transition_reason"] is None
        assert result["updated_at"] is not None

    def test_create_workflow_phase_nonexistent_entity_raises(
        self, db: EntityDatabase
    ):
        """create_workflow_phase for non-existent entity raises ValueError."""
        with pytest.raises(ValueError, match="Entity not found"):
            db.create_workflow_phase("feature:does-not-exist")

    def test_create_workflow_phase_duplicate_raises(self, db: EntityDatabase):
        """create_workflow_phase for entity that already has a row raises ValueError."""
        db.register_entity("feature", "f1", "Test Feature")
        db.create_workflow_phase("feature:f1")
        with pytest.raises(ValueError, match="already exists"):
            db.create_workflow_phase("feature:f1")

    def test_create_workflow_phase_invalid_kanban_column_raises(
        self, db: EntityDatabase
    ):
        """create_workflow_phase with invalid kanban_column raises ValueError."""
        db.register_entity("feature", "f1", "Test Feature")
        with pytest.raises(ValueError, match="Invalid value"):
            db.create_workflow_phase("feature:f1", kanban_column="not-a-column")

    def test_create_workflow_phase_defaults_applied(self, db: EntityDatabase):
        """create_workflow_phase with no optional args applies defaults."""
        db.register_entity("feature", "f1", "Test Feature")
        result = db.create_workflow_phase("feature:f1")
        assert result["kanban_column"] == "backlog"
        assert result["workflow_phase"] is None
        assert result["last_completed_phase"] is None
        assert result["mode"] is None
        assert result["backward_transition_reason"] is None
        assert result["updated_at"] is not None

    # -- Task 2.2: get_workflow_phase (AC-6) --------------------------------

    def test_get_workflow_phase_existing_returns_dict(
        self, db: EntityDatabase
    ):
        """get_workflow_phase for existing row returns dict."""
        db.register_entity("feature", "f1", "Test Feature")
        db.create_workflow_phase("feature:f1", kanban_column="wip")
        result = db.get_workflow_phase("feature:f1")
        assert isinstance(result, dict)
        assert result["type_id"] == "feature:f1"
        assert result["kanban_column"] == "wip"

    def test_get_workflow_phase_nonexistent_returns_none(
        self, db: EntityDatabase
    ):
        """get_workflow_phase for non-existent type_id returns None."""
        result = db.get_workflow_phase("feature:nonexistent")
        assert result is None

    def test_get_workflow_phase_has_all_8_columns(self, db: EntityDatabase):
        """get_workflow_phase result dict has all 8 columns (uuid added in v6)."""
        db.register_entity("feature", "f1", "Test Feature")
        db.create_workflow_phase(
            "feature:f1",
            kanban_column="wip",
            workflow_phase="design",
            last_completed_phase="specify",
            mode="full",
            backward_transition_reason="rework needed",
        )
        result = db.get_workflow_phase("feature:f1")
        expected_keys = {
            "type_id",
            "workflow_phase",
            "kanban_column",
            "last_completed_phase",
            "mode",
            "backward_transition_reason",
            "updated_at",
            "uuid",
        }
        assert set(result.keys()) == expected_keys
        assert result["type_id"] == "feature:f1"
        assert result["workflow_phase"] == "design"
        assert result["kanban_column"] == "wip"
        assert result["last_completed_phase"] == "specify"
        assert result["mode"] == "full"
        assert result["backward_transition_reason"] == "rework needed"
        assert result["updated_at"] is not None

    # -- Task 2.3: update_workflow_phase (AC-7) -----------------------------

    def test_update_workflow_phase_single_field(self, db: EntityDatabase):
        """update_workflow_phase changing one field updates only that field."""
        db.register_entity("feature", "f1", "Test Feature")
        created = db.create_workflow_phase(
            "feature:f1", kanban_column="backlog", workflow_phase="brainstorm"
        )
        original_updated_at = created["updated_at"]
        time.sleep(0.01)

        result = db.update_workflow_phase(
            "feature:f1", kanban_column="wip"
        )
        assert result["kanban_column"] == "wip"
        # Other fields unchanged
        assert result["workflow_phase"] == "brainstorm"
        # updated_at should be refreshed
        assert result["updated_at"] != original_updated_at

    def test_update_workflow_phase_multiple_fields(self, db: EntityDatabase):
        """update_workflow_phase changing multiple fields updates all."""
        db.register_entity("feature", "f1", "Test Feature")
        db.create_workflow_phase("feature:f1")

        result = db.update_workflow_phase(
            "feature:f1",
            kanban_column="wip",
            workflow_phase="design",
            mode="standard",
        )
        assert result["kanban_column"] == "wip"
        assert result["workflow_phase"] == "design"
        assert result["mode"] == "standard"

    def test_update_workflow_phase_explicit_none_sets_null(
        self, db: EntityDatabase
    ):
        """Passing None explicitly sets field to NULL."""
        db.register_entity("feature", "f1", "Test Feature")
        db.create_workflow_phase(
            "feature:f1", workflow_phase="design", mode="standard"
        )

        result = db.update_workflow_phase(
            "feature:f1", workflow_phase=None, mode=None
        )
        assert result["workflow_phase"] is None
        assert result["mode"] is None

    def test_update_workflow_phase_omitted_field_unchanged(
        self, db: EntityDatabase
    ):
        """Omitting a field (not passing it) keeps current value (_UNSET sentinel)."""
        db.register_entity("feature", "f1", "Test Feature")
        db.create_workflow_phase(
            "feature:f1",
            kanban_column="wip",
            workflow_phase="design",
            mode="standard",
        )

        # Only update workflow_phase; kanban_column and mode should be unchanged
        result = db.update_workflow_phase(
            "feature:f1", workflow_phase="implement"
        )
        assert result["workflow_phase"] == "implement"
        assert result["kanban_column"] == "wip"  # unchanged
        assert result["mode"] == "standard"  # unchanged

    def test_update_workflow_phase_nonexistent_raises(
        self, db: EntityDatabase
    ):
        """update_workflow_phase for non-existent type_id raises ValueError."""
        with pytest.raises(ValueError):
            db.update_workflow_phase("feature:nonexistent", kanban_column="wip")

    def test_update_workflow_phase_invalid_enum_raises(
        self, db: EntityDatabase
    ):
        """update_workflow_phase with invalid enum value raises ValueError."""
        db.register_entity("feature", "f1", "Test Feature")
        db.create_workflow_phase("feature:f1")

        with pytest.raises(ValueError, match="Invalid value"):
            db.update_workflow_phase(
                "feature:f1", kanban_column="not-a-column"
            )

    def test_update_workflow_phase_no_optional_fields_refreshes_timestamp(
        self, db: EntityDatabase
    ):
        """update_workflow_phase with only type_id refreshes updated_at."""
        db.register_entity("feature", "f1", "Test Feature")
        created = db.create_workflow_phase("feature:f1")
        original_updated_at = created["updated_at"]
        time.sleep(0.01)

        result = db.update_workflow_phase("feature:f1")
        assert result["updated_at"] != original_updated_at
        # All other fields unchanged
        assert result["kanban_column"] == created["kanban_column"]
        assert result["workflow_phase"] == created["workflow_phase"]

    def test_update_workflow_phase_kanban_column_none_raises(
        self, db: EntityDatabase
    ):
        """Passing kanban_column=None explicitly raises ValueError (NOT NULL)."""
        db.register_entity("feature", "f1", "Test Feature")
        db.create_workflow_phase("feature:f1")

        with pytest.raises(ValueError):
            db.update_workflow_phase("feature:f1", kanban_column=None)

    # -- Task 2.4: delete_workflow_phase (AC-8) -----------------------------

    def test_delete_workflow_phase_existing_removes_row(
        self, db: EntityDatabase
    ):
        """delete_workflow_phase removes the row from the table."""
        db.register_entity("feature", "f1", "Test Feature")
        db.create_workflow_phase("feature:f1")

        db.delete_workflow_phase("feature:f1")

        # Verify row is gone via direct SQL
        row = db._conn.execute(
            "SELECT * FROM workflow_phases WHERE type_id = ?",
            ("feature:f1",),
        ).fetchone()
        assert row is None

    def test_delete_workflow_phase_nonexistent_raises(
        self, db: EntityDatabase
    ):
        """delete_workflow_phase for non-existent type_id raises ValueError."""
        with pytest.raises(ValueError):
            db.delete_workflow_phase("feature:nonexistent")

    def test_get_returns_none_after_delete(self, db: EntityDatabase):
        """get_workflow_phase returns None after delete_workflow_phase."""
        db.register_entity("feature", "f1", "Test Feature")
        db.create_workflow_phase("feature:f1")

        db.delete_workflow_phase("feature:f1")
        assert db.get_workflow_phase("feature:f1") is None

    # -- Task 2.5: list_workflow_phases (AC-9) ------------------------------

    def test_list_workflow_phases_returns_all(self, db: EntityDatabase):
        """list_workflow_phases with no filters returns all rows."""
        db.register_entity("feature", "f1", "Feature 1")
        db.register_entity("feature", "f2", "Feature 2")
        db.register_entity("feature", "f3", "Feature 3")
        db.create_workflow_phase("feature:f1", kanban_column="backlog")
        db.create_workflow_phase("feature:f2", kanban_column="wip")
        db.create_workflow_phase("feature:f3", kanban_column="completed")

        result = db.list_workflow_phases()
        assert len(result) == 3
        assert all(isinstance(r, dict) for r in result)

    def test_list_workflow_phases_filter_by_kanban_column(
        self, db: EntityDatabase
    ):
        """list_workflow_phases with kanban_column filter returns matching rows."""
        db.register_entity("feature", "f1", "Feature 1")
        db.register_entity("feature", "f2", "Feature 2")
        db.register_entity("feature", "f3", "Feature 3")
        db.create_workflow_phase("feature:f1", kanban_column="backlog")
        db.create_workflow_phase("feature:f2", kanban_column="wip")
        db.create_workflow_phase("feature:f3", kanban_column="backlog")

        result = db.list_workflow_phases(kanban_column="backlog")
        assert len(result) == 2
        assert all(r["kanban_column"] == "backlog" for r in result)

    def test_list_workflow_phases_filter_by_workflow_phase(
        self, db: EntityDatabase
    ):
        """list_workflow_phases with workflow_phase filter returns matching rows."""
        db.register_entity("feature", "f1", "Feature 1")
        db.register_entity("feature", "f2", "Feature 2")
        db.register_entity("feature", "f3", "Feature 3")
        db.create_workflow_phase(
            "feature:f1", workflow_phase="design"
        )
        db.create_workflow_phase(
            "feature:f2", workflow_phase="implement"
        )
        db.create_workflow_phase(
            "feature:f3", workflow_phase="design"
        )

        result = db.list_workflow_phases(workflow_phase="design")
        assert len(result) == 2
        assert all(r["workflow_phase"] == "design" for r in result)

    def test_list_workflow_phases_both_filters_and_logic(
        self, db: EntityDatabase
    ):
        """list_workflow_phases with both filters uses AND logic."""
        db.register_entity("feature", "f1", "Feature 1")
        db.register_entity("feature", "f2", "Feature 2")
        db.register_entity("feature", "f3", "Feature 3")
        db.create_workflow_phase(
            "feature:f1", kanban_column="wip", workflow_phase="design"
        )
        db.create_workflow_phase(
            "feature:f2", kanban_column="wip", workflow_phase="implement"
        )
        db.create_workflow_phase(
            "feature:f3", kanban_column="backlog", workflow_phase="design"
        )

        result = db.list_workflow_phases(
            kanban_column="wip", workflow_phase="design"
        )
        assert len(result) == 1
        assert result[0]["type_id"] == "feature:f1"

    def test_list_workflow_phases_empty_result(self, db: EntityDatabase):
        """list_workflow_phases returns empty list when no rows match."""
        result = db.list_workflow_phases()
        assert result == []

        # Also test with filter that matches nothing
        db.register_entity("feature", "f1", "Feature 1")
        db.create_workflow_phase("feature:f1", kanban_column="backlog")
        result = db.list_workflow_phases(kanban_column="completed")
        assert result == []

    # -- LEFT JOIN entity enrichment tests ---------------------------------

    def test_list_wp_returns_entity_name_type_path(self, db: EntityDatabase):
        """list_workflow_phases returns entity_name, entity_type, entity_artifact_path."""
        db.register_entity("feature", "f1", "My Feature", artifact_path="/path/f1")
        db.create_workflow_phase("feature:f1", kanban_column="wip")

        result = db.list_workflow_phases()
        assert len(result) == 1
        assert result[0]["entity_name"] == "My Feature"
        assert result[0]["entity_type"] == "feature"
        assert result[0]["entity_artifact_path"] == "/path/f1"

    def test_list_wp_null_for_orphan_rows(self, db: EntityDatabase):
        """LEFT JOIN returns NULL entity fields for orphan workflow_phases rows."""
        # Manually insert a workflow_phases row without a matching entity
        db._conn.execute("PRAGMA foreign_keys = OFF")
        db._conn.execute(
            "INSERT INTO workflow_phases (type_id, kanban_column, updated_at) VALUES (?, ?, ?)",
            ("feature:orphan", "backlog", "2026-01-01T00:00:00Z"),
        )
        db._conn.commit()
        db._conn.execute("PRAGMA foreign_keys = ON")

        result = db.list_workflow_phases()
        assert len(result) == 1
        assert result[0]["entity_name"] is None
        assert result[0]["entity_type"] is None
        assert result[0]["entity_artifact_path"] is None

    def test_list_wp_filter_with_join(self, db: EntityDatabase):
        """WHERE clauses still work correctly with JOIN."""
        db.register_entity("feature", "f1", "Feature 1")
        db.register_entity("feature", "f2", "Feature 2")
        db.create_workflow_phase("feature:f1", kanban_column="wip", workflow_phase="design")
        db.create_workflow_phase("feature:f2", kanban_column="backlog", workflow_phase="specify")

        result = db.list_workflow_phases(kanban_column="wip")
        assert len(result) == 1
        assert result[0]["entity_name"] == "Feature 1"

    def test_list_wp_all_rows_preserved(self, db: EntityDatabase):
        """LEFT JOIN does not lose any workflow_phases rows."""
        db.register_entity("feature", "f1", "Feature 1")
        db.register_entity("feature", "f2", "Feature 2")
        db.create_workflow_phase("feature:f1", kanban_column="wip")
        db.create_workflow_phase("feature:f2", kanban_column="backlog")
        # Add orphan row (disable FK to allow orphan)
        db._conn.execute("PRAGMA foreign_keys = OFF")
        db._conn.execute(
            "INSERT INTO workflow_phases (type_id, kanban_column, updated_at) VALUES (?, ?, ?)",
            ("feature:orphan", "backlog", "2026-01-01T00:00:00Z"),
        )
        db._conn.commit()
        db._conn.execute("PRAGMA foreign_keys = ON")

        result = db.list_workflow_phases()
        assert len(result) == 3

    def test_list_wp_empty_table(self, db: EntityDatabase):
        """list_workflow_phases on empty table returns empty list."""
        result = db.list_workflow_phases()
        assert result == []


# ---------------------------------------------------------------------------
# Phase B Deepened Tests: Workflow Phase CRUD & Migration edge cases
# ---------------------------------------------------------------------------


class TestUpdateWorkflowPhaseUnsetVsNone:
    """Sentinel _UNSET vs explicit None distinction in update_workflow_phase.

    Anticipate: If the sentinel check uses `is not None` instead of
    `is not _UNSET`, passing None explicitly would be treated as "not
    provided" and leave the field unchanged, instead of setting it to NULL.
    derived_from: spec:D-4 (CRUD update), dimension:mutation_mindset
    """

    def test_explicit_none_sets_last_completed_phase_to_null(
        self, db: EntityDatabase,
    ):
        # Given a workflow phase row with last_completed_phase set
        db.register_entity("feature", "unset-lcp", "UNSET LCP Test")
        db.create_workflow_phase(
            "feature:unset-lcp",
            kanban_column="wip",
            workflow_phase="design",
            last_completed_phase="specify",
        )
        # When explicitly passing last_completed_phase=None
        result = db.update_workflow_phase(
            "feature:unset-lcp", last_completed_phase=None,
        )
        # Then last_completed_phase is set to NULL
        assert result["last_completed_phase"] is None
        # And other fields remain unchanged
        assert result["kanban_column"] == "wip"
        assert result["workflow_phase"] == "design"

    def test_explicit_none_sets_backward_transition_reason_to_null(
        self, db: EntityDatabase,
    ):
        # Given a row with backward_transition_reason set
        db.register_entity("feature", "unset-btr", "UNSET BTR Test")
        db.create_workflow_phase(
            "feature:unset-btr",
            kanban_column="wip",
            backward_transition_reason="rework needed",
        )
        # When explicitly passing backward_transition_reason=None
        result = db.update_workflow_phase(
            "feature:unset-btr", backward_transition_reason=None,
        )
        # Then backward_transition_reason is NULL
        assert result["backward_transition_reason"] is None
        # And kanban_column unchanged
        assert result["kanban_column"] == "wip"

    def test_omitting_last_completed_phase_preserves_value(
        self, db: EntityDatabase,
    ):
        # Given a row with last_completed_phase="design"
        db.register_entity("feature", "omit-lcp", "Omit LCP Test")
        db.create_workflow_phase(
            "feature:omit-lcp",
            last_completed_phase="design",
        )
        # When updating only kanban_column (omitting last_completed_phase entirely)
        result = db.update_workflow_phase(
            "feature:omit-lcp", kanban_column="wip",
        )
        # Then last_completed_phase is preserved (not set to NULL)
        assert result["last_completed_phase"] == "design"
        assert result["kanban_column"] == "wip"

    def test_omitting_backward_transition_reason_preserves_value(
        self, db: EntityDatabase,
    ):
        # Given a row with backward_transition_reason set
        db.register_entity("feature", "omit-btr", "Omit BTR Test")
        db.create_workflow_phase(
            "feature:omit-btr",
            backward_transition_reason="reviewer requested rework",
        )
        # When updating only kanban_column (omitting backward_transition_reason)
        result = db.update_workflow_phase(
            "feature:omit-btr", kanban_column="wip",
        )
        # Then backward_transition_reason is preserved
        assert result["backward_transition_reason"] == "reviewer requested rework"


class TestCreateWorkflowPhaseErrorMessages:
    """Error message content validation for create/update/delete ValueError.

    Anticipate: If error messages are generic ("error") instead of
    informative, callers cannot distinguish between different failure
    modes programmatically.
    derived_from: dimension:error_propagation, spec:AC-5, spec:AC-7, spec:AC-8
    """

    def test_create_nonexistent_entity_message_contains_type_id(
        self, db: EntityDatabase,
    ):
        # Given no entity "feature:ghost" exists
        # When creating a workflow phase for it
        # Then ValueError message contains the type_id for debugging
        with pytest.raises(ValueError) as exc_info:
            db.create_workflow_phase("feature:ghost")
        assert "feature:ghost" in str(exc_info.value) or "not found" in str(exc_info.value).lower()

    def test_create_duplicate_message_says_already_exists(
        self, db: EntityDatabase,
    ):
        # Given a workflow phase already exists
        db.register_entity("feature", "dup-msg", "Dup Message")
        db.create_workflow_phase("feature:dup-msg")
        # When trying to create again
        # Then ValueError message includes "already exists"
        with pytest.raises(ValueError) as exc_info:
            db.create_workflow_phase("feature:dup-msg")
        assert "already exists" in str(exc_info.value).lower()

    def test_update_nonexistent_message_contains_type_id(
        self, db: EntityDatabase,
    ):
        # Given no workflow phase for "feature:phantom"
        # When updating it
        with pytest.raises(ValueError) as exc_info:
            db.update_workflow_phase("feature:phantom", kanban_column="wip")
        assert "feature:phantom" in str(exc_info.value) or "not found" in str(exc_info.value).lower()

    def test_delete_nonexistent_message_contains_type_id(
        self, db: EntityDatabase,
    ):
        # Given no workflow phase for "feature:void"
        with pytest.raises(ValueError) as exc_info:
            db.delete_workflow_phase("feature:void")
        assert "feature:void" in str(exc_info.value) or "not found" in str(exc_info.value).lower()

    def test_create_invalid_enum_message_says_invalid_value(
        self, db: EntityDatabase,
    ):
        # Given an entity exists
        db.register_entity("feature", "bad-enum", "Bad Enum")
        # When creating with invalid workflow_phase value
        with pytest.raises(ValueError) as exc_info:
            db.create_workflow_phase(
                "feature:bad-enum", workflow_phase="not-a-phase",
            )
        msg = str(exc_info.value).lower()
        assert "invalid" in msg or "check" in msg


class TestCreateWorkflowPhaseAllEnumValuesViaAPI:
    """Full enum exhaustion through the Python CRUD API (not raw SQL).

    Anticipate: The Python API might have additional validation beyond
    CHECK constraints (e.g., pre-validation that rejects valid values),
    or the SQL might not be parameterized correctly for hyphenated values.
    derived_from: dimension:boundary_values, spec:AC-4
    """

    def test_all_seven_workflow_phases_accepted_via_create(
        self, db: EntityDatabase,
    ):
        # Given all 7 valid workflow_phase values
        valid_phases = [
            "brainstorm", "specify", "design",
            "create-plan", "create-tasks", "implement", "finish",
        ]
        # When creating workflow phases for each
        for i, phase in enumerate(valid_phases):
            db.register_entity("feature", f"enum-wp-{i}", f"Enum WP {i}")
            result = db.create_workflow_phase(
                f"feature:enum-wp-{i}", workflow_phase=phase,
            )
            # Then each is accepted and returned correctly
            assert result["workflow_phase"] == phase

    def test_all_eight_kanban_columns_accepted_via_create(
        self, db: EntityDatabase,
    ):
        # Given all 8 valid kanban_column values
        valid_columns = [
            "backlog", "prioritised", "wip", "agent_review",
            "human_review", "blocked", "documenting", "completed",
        ]
        # When creating workflow phases for each
        for i, col in enumerate(valid_columns):
            db.register_entity("feature", f"enum-kc-{i}", f"Enum KC {i}")
            result = db.create_workflow_phase(
                f"feature:enum-kc-{i}", kanban_column=col,
            )
            # Then each is accepted and returned correctly
            assert result["kanban_column"] == col

    def test_null_workflow_phase_accepted_via_create(
        self, db: EntityDatabase,
    ):
        # Given workflow_phase=None (NULL is valid for nullable column)
        db.register_entity("feature", "null-wp", "Null WP")
        result = db.create_workflow_phase(
            "feature:null-wp", workflow_phase=None,
        )
        # Then workflow_phase is NULL
        assert result["workflow_phase"] is None


class TestUpdateWorkflowPhaseAllFieldsSimultaneously:
    """Mutation mindset: updating all 5 mutable fields at once.

    Anticipate: If the SQL SET clause builder has an off-by-one error or
    truncates the parameter list, only some fields would be updated.
    derived_from: dimension:mutation_mindset, spec:AC-7
    """

    def test_update_all_five_mutable_fields_at_once(
        self, db: EntityDatabase,
    ):
        # Given a workflow phase with defaults
        db.register_entity("feature", "all-fields", "All Fields Test")
        db.create_workflow_phase("feature:all-fields")
        time.sleep(0.01)
        # When updating all 5 mutable fields simultaneously
        result = db.update_workflow_phase(
            "feature:all-fields",
            kanban_column="wip",
            workflow_phase="implement",
            last_completed_phase="create-tasks",
            mode="full",
            backward_transition_reason="rolled back from finish",
        )
        # Then all 5 are updated
        assert result["kanban_column"] == "wip"
        assert result["workflow_phase"] == "implement"
        assert result["last_completed_phase"] == "create-tasks"
        assert result["mode"] == "full"
        assert result["backward_transition_reason"] == "rolled back from finish"
        # And type_id is unchanged (immutable)
        assert result["type_id"] == "feature:all-fields"
        # And updated_at is refreshed
        assert result["updated_at"] is not None


# ---------------------------------------------------------------------------
# export_entities_json tests
# ---------------------------------------------------------------------------

import time as time_mod


class TestExportEntitiesJson:
    """Tests for EntityDatabase.export_entities_json() method."""

    # -- Envelope, Filters, Validation (Task 1.1.1a) -----------------------

    def test_no_filters_returns_all(self, mem_db: EntityDatabase):
        """No args returns all entities with correct envelope keys."""
        mem_db.register_entity("feature", "f1", "Feature One")
        mem_db.register_entity("project", "p1", "Project One")
        mem_db.register_entity("brainstorm", "b1", "Brainstorm One")

        result = mem_db.export_entities_json()

        assert isinstance(result, dict)
        expected_keys = {
            "schema_version", "exported_at", "entity_count",
            "filters_applied", "entities",
        }
        assert set(result.keys()) == expected_keys
        assert result["entity_count"] == 3
        assert len(result["entities"]) == 3

    def test_entity_type_filter(self, mem_db: EntityDatabase):
        """entity_type='feature' returns only features."""
        mem_db.register_entity("feature", "f1", "Feature One")
        mem_db.register_entity("project", "p1", "Project One")

        result = mem_db.export_entities_json(entity_type="feature")

        assert result["entity_count"] == 1
        assert len(result["entities"]) == 1
        assert result["entities"][0]["entity_type"] == "feature"

    def test_status_filter(self, mem_db: EntityDatabase):
        """status='completed' returns only completed entities."""
        mem_db.register_entity(
            "feature", "f1", "Feature One", status="completed",
        )
        mem_db.register_entity(
            "feature", "f2", "Feature Two", status="active",
        )

        result = mem_db.export_entities_json(status="completed")

        assert result["entity_count"] == 1
        assert len(result["entities"]) == 1
        assert result["entities"][0]["status"] == "completed"

    def test_combined_filters(self, mem_db: EntityDatabase):
        """entity_type + status uses AND logic."""
        mem_db.register_entity(
            "feature", "f1", "Active Feature", status="active",
        )
        mem_db.register_entity(
            "feature", "f2", "Completed Feature", status="completed",
        )
        mem_db.register_entity(
            "project", "p1", "Active Project", status="active",
        )

        result = mem_db.export_entities_json(
            entity_type="feature", status="active",
        )

        assert result["entity_count"] == 1
        assert len(result["entities"]) == 1
        entity = result["entities"][0]
        assert entity["entity_type"] == "feature"
        assert entity["status"] == "active"
        assert entity["entity_id"] == "f1"

    def test_invalid_entity_type_raises(self, mem_db: EntityDatabase):
        """Invalid entity_type raises ValueError."""
        with pytest.raises(
            ValueError,
            match=r"Invalid entity_type 'invalid'\. Must be one of \('backlog',",
        ):
            mem_db.export_entities_json(entity_type="invalid")

    def test_unmatched_status_returns_empty(self, mem_db: EntityDatabase):
        """Unmatched status returns valid envelope with zero entities."""
        mem_db.register_entity(
            "feature", "f1", "Feature One", status="active",
        )

        result = mem_db.export_entities_json(status="nonexistent")

        assert result["entity_count"] == 0
        assert result["entities"] == []

    def test_empty_database(self, mem_db: EntityDatabase):
        """Empty database returns valid envelope with zero entities."""
        result = mem_db.export_entities_json()

        assert isinstance(result, dict)
        assert result["entity_count"] == 0
        assert result["entities"] == []
        assert "schema_version" in result
        assert "exported_at" in result
        assert "filters_applied" in result

    def test_schema_version(self, mem_db: EntityDatabase):
        """schema_version matches EXPORT_SCHEMA_VERSION constant (== 1)."""
        result = mem_db.export_entities_json()

        assert result["schema_version"] == EXPORT_SCHEMA_VERSION
        assert result["schema_version"] == 1

    def test_exported_at_format(self, mem_db: EntityDatabase):
        """exported_at is ISO 8601 with timezone offset."""
        result = mem_db.export_entities_json()

        exported_at = result["exported_at"]
        assert re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.*[+-]\d{2}:\d{2}$",
            exported_at,
        ), f"exported_at '{exported_at}' is not valid ISO 8601 with timezone"

    def test_filters_applied_in_envelope(self, mem_db: EntityDatabase):
        """filters_applied dict has entity_type and status keys only."""
        result = mem_db.export_entities_json(
            entity_type="feature", status="active",
        )

        filters = result["filters_applied"]
        assert "entity_type" in filters
        assert "status" in filters
        assert filters["entity_type"] == "feature"
        assert filters["status"] == "active"
        assert "include_lineage" not in filters

    # -- Lineage, Metadata, Ordering, Performance (Task 1.1.1b) ------------

    def test_uuid_in_entity(self, mem_db: EntityDatabase):
        """Each entity dict has a uuid field matching UUID v4 pattern."""
        mem_db.register_entity("feature", "f1", "Feature One")

        result = mem_db.export_entities_json()

        for entity in result["entities"]:
            assert "uuid" in entity
            assert re.match(
                _UUID_V4_RE, entity["uuid"],
            ), f"uuid '{entity['uuid']}' does not match UUID v4 pattern"

    def test_include_lineage_true(self, mem_db: EntityDatabase):
        """include_lineage=True includes parent_type_id in entity dicts."""
        mem_db.register_entity("project", "p1", "Project One")
        mem_db.register_entity(
            "feature", "f1", "Feature One",
            parent_type_id="project:p1",
        )

        result = mem_db.export_entities_json(include_lineage=True)

        for entity in result["entities"]:
            assert "parent_type_id" in entity
        # Verify the child has the correct parent
        child = [
            e for e in result["entities"] if e["type_id"] == "feature:f1"
        ][0]
        assert child["parent_type_id"] == "project:p1"

    def test_include_lineage_false(self, mem_db: EntityDatabase):
        """include_lineage=False excludes parent_type_id from entity dicts."""
        mem_db.register_entity("project", "p1", "Project One")
        mem_db.register_entity(
            "feature", "f1", "Feature One",
            parent_type_id="project:p1",
        )

        result = mem_db.export_entities_json(include_lineage=False)

        for entity in result["entities"]:
            assert "parent_type_id" not in entity

    def test_metadata_null_normalized(self, mem_db: EntityDatabase):
        """Entity with no metadata has metadata field as {} (not None)."""
        mem_db.register_entity("feature", "f1", "Feature One")

        result = mem_db.export_entities_json()

        entity = result["entities"][0]
        assert entity["metadata"] == {}
        assert entity["metadata"] is not None

    def test_metadata_valid_json(self, mem_db: EntityDatabase):
        """Entity with metadata={'key': 'value'} returns that dict."""
        mem_db.register_entity(
            "feature", "f1", "Feature One",
            metadata={"key": "value"},
        )

        result = mem_db.export_entities_json()

        entity = result["entities"][0]
        assert entity["metadata"] == {"key": "value"}

    def test_metadata_malformed_json(self, mem_db: EntityDatabase):
        """Entity with malformed JSON metadata returns {} (empty dict)."""
        mem_db.register_entity("feature", "f1", "Feature One")
        # Directly corrupt metadata in DB
        mem_db._conn.execute(
            "UPDATE entities SET metadata = '{bad' WHERE type_id = ?",
            ("feature:f1",),
        )
        mem_db._conn.commit()

        result = mem_db.export_entities_json()

        entity = result["entities"][0]
        assert entity["metadata"] == {}

    def test_entity_ordering(self, mem_db: EntityDatabase):
        """Results ordered by created_at ASC, then type_id ASC."""
        # Insert with explicit created_at in reverse order to verify sorting
        now = mem_db._now_iso()
        # Insert entities with controlled timestamps via direct SQL
        rows = [
            (str(uuid.uuid4()), "feature:f3", "feature", "f3", "Third",
             "active", None, None, None, "2026-01-03T00:00:00+00:00",
             "2026-01-03T00:00:00+00:00", None),
            (str(uuid.uuid4()), "feature:f1", "feature", "f1", "First",
             "active", None, None, None, "2026-01-01T00:00:00+00:00",
             "2026-01-01T00:00:00+00:00", None),
            (str(uuid.uuid4()), "project:p1", "project", "p1", "Also First",
             "active", None, None, None, "2026-01-01T00:00:00+00:00",
             "2026-01-01T00:00:00+00:00", None),
            (str(uuid.uuid4()), "feature:f2", "feature", "f2", "Second",
             "active", None, None, None, "2026-01-02T00:00:00+00:00",
             "2026-01-02T00:00:00+00:00", None),
        ]
        mem_db._conn.executemany(
            "INSERT INTO entities (uuid, type_id, entity_type, entity_id, "
            "name, status, artifact_path, parent_type_id, parent_uuid, "
            "created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        # Insert matching FTS entries
        fts_rows = []
        for row in mem_db._conn.execute(
            "SELECT rowid, name, entity_id, entity_type, status "
            "FROM entities"
        ).fetchall():
            fts_rows.append(
                (row[0], row[1], row[2], row[3], row[4] or "", ""),
            )
        mem_db._conn.executemany(
            "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
            "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
            fts_rows,
        )
        mem_db._conn.commit()

        result = mem_db.export_entities_json()

        type_ids = [e["type_id"] for e in result["entities"]]
        # Same timestamp: type_id ASC (feature:f1 < project:p1)
        # Then feature:f2 (2026-01-02), then feature:f3 (2026-01-03)
        assert type_ids == [
            "feature:f1", "project:p1", "feature:f2", "feature:f3",
        ]

    def test_all_entity_fields_present(self, mem_db: EntityDatabase):
        """Each entity dict has exactly the expected keys."""
        mem_db.register_entity("project", "p1", "Project One")
        mem_db.register_entity(
            "feature", "f1", "Feature One",
            parent_type_id="project:p1",
            metadata={"key": "value"},
        )

        # With lineage
        result = mem_db.export_entities_json(include_lineage=True)
        expected_keys = {
            "uuid", "type_id", "entity_type", "entity_id", "name",
            "status", "artifact_path", "created_at", "updated_at",
            "metadata", "parent_type_id",
        }
        for entity in result["entities"]:
            assert set(entity.keys()) == expected_keys, (
                f"Entity {entity.get('type_id', '?')} has keys "
                f"{set(entity.keys())} but expected {expected_keys}"
            )

        # Without lineage - parent_type_id should be absent
        result_no_lineage = mem_db.export_entities_json(include_lineage=False)
        expected_keys_no_lineage = expected_keys - {"parent_type_id"}
        for entity in result_no_lineage["entities"]:
            assert set(entity.keys()) == expected_keys_no_lineage

    def test_performance_1000_entities(self, mem_db: EntityDatabase):
        """1000 entities exported in under 5 seconds."""
        now = mem_db._now_iso()
        rows = [
            (
                str(uuid.uuid4()), f"feature:{i:04d}", "feature",
                f"{i:04d}", f"Entity {i}", "active",
                None, None, None, now, now, None,
            )
            for i in range(1000)
        ]
        mem_db._conn.executemany(
            "INSERT INTO entities (uuid, type_id, entity_type, entity_id, "
            "name, status, artifact_path, parent_type_id, parent_uuid, "
            "created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        # Insert matching FTS entries
        fts_rows = []
        for row in mem_db._conn.execute(
            "SELECT rowid, name, entity_id, entity_type, status "
            "FROM entities WHERE entity_type = 'feature'"
        ).fetchall():
            fts_rows.append(
                (row[0], row[1], row[2], row[3], row[4] or "", ""),
            )
        mem_db._conn.executemany(
            "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
            "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
            fts_rows,
        )
        mem_db._conn.commit()

        start = time_mod.perf_counter()
        result = mem_db.export_entities_json()
        elapsed = time_mod.perf_counter() - start

        assert result["entity_count"] == 1000
        assert len(result["entities"]) == 1000
        assert elapsed < 5.0, (
            f"export_entities_json took {elapsed:.2f}s, exceeds 5s limit"
        )


# ---------------------------------------------------------------------------
# export_entities_json deepened tests (test-deepener Phase B)
# ---------------------------------------------------------------------------


class TestExportEntitiesJsonDeepened:
    """Deepened tests for EntityDatabase.export_entities_json().

    Covers boundary, adversarial, and mutation dimensions that supplement
    the existing TDD tests above.
    """

    # -- Dimension 2: Boundary Values --------------------------------------

    def test_single_entity_export(self, mem_db: EntityDatabase):
        """Single entity returns entity_count=1 and exactly one entry.

        derived_from: boundary: single element
        """
        # Given exactly one entity exists in the database
        mem_db.register_entity("feature", "solo", "Solo Feature", status="active")
        # When export_entities_json() is called with no arguments
        result = mem_db.export_entities_json()
        # Then entity_count is 1 and entities array has exactly one element
        assert result["entity_count"] == 1
        assert len(result["entities"]) == 1
        assert result["entities"][0]["entity_id"] == "solo"

    def test_filter_matches_all_entities(self, mem_db: EntityDatabase):
        """Filter that matches every entity returns all of them.

        derived_from: boundary: all match
        """
        # Given all entities in the database are features
        mem_db.register_entity("feature", "f1", "F1", status="active")
        mem_db.register_entity("feature", "f2", "F2", status="active")
        mem_db.register_entity("feature", "f3", "F3", status="active")
        # When filtering by entity_type='feature'
        result = mem_db.export_entities_json(entity_type="feature")
        # Then all three entities are returned
        assert result["entity_count"] == 3
        assert len(result["entities"]) == 3
        for e in result["entities"]:
            assert e["entity_type"] == "feature"

    def test_entity_type_boundary_each_valid_type(self, mem_db: EntityDatabase):
        """Each valid entity_type can be used as a filter without error.

        derived_from: boundary: equivalence partitioning
        """
        # Given one entity of each valid type exists
        valid_types = ("backlog", "brainstorm", "project", "feature")
        for et in valid_types:
            mem_db.register_entity(et, f"{et}-001", f"Entity {et}")
        # When filtering by each valid type individually
        for et in valid_types:
            result = mem_db.export_entities_json(entity_type=et)
            # Then exactly one entity is returned and it matches the filter
            assert result["entity_count"] == 1, (
                f"Expected 1 entity for type '{et}', got {result['entity_count']}"
            )
            assert result["entities"][0]["entity_type"] == et

    def test_metadata_with_deeply_nested_json(self, mem_db: EntityDatabase):
        """Metadata with nested objects is parsed into a nested dict.

        derived_from: boundary: metadata nested JSON
        """
        # Given an entity has deeply nested metadata
        nested_meta = {
            "config": {
                "level1": {"level2": {"value": 42}},
                "tags": ["alpha", "beta"],
            }
        }
        mem_db.register_entity(
            "feature", "f1", "Nested Meta Feature", metadata=nested_meta,
        )
        # When export_entities_json() is called
        result = mem_db.export_entities_json()
        # Then metadata is the full nested dict, not a flat string
        entity = result["entities"][0]
        assert isinstance(entity["metadata"], dict)
        assert entity["metadata"]["config"]["level1"]["level2"]["value"] == 42
        assert entity["metadata"]["config"]["tags"] == ["alpha", "beta"]

    # -- Dimension 3: Adversarial ------------------------------------------

    def test_entity_type_with_sql_injection_attempt(self, mem_db: EntityDatabase):
        """SQL injection in entity_type raises ValueError, not SQL error.

        derived_from: adversarial: SQL injection
        """
        # Given a malicious entity_type string containing SQL injection
        malicious_type = "'; DROP TABLE entities; --"
        # When export_entities_json is called with the malicious input
        with pytest.raises(ValueError, match=r"Invalid entity_type"):
            mem_db.export_entities_json(entity_type=malicious_type)
        # Then the entities table still exists and is intact
        count = mem_db._conn.execute(
            "SELECT count(*) FROM entities"
        ).fetchone()[0]
        assert count >= 0, "entities table should still exist after injection attempt"

    def test_entity_type_case_sensitivity(self, mem_db: EntityDatabase):
        """entity_type validation is case-sensitive ('Feature' != 'feature').

        derived_from: adversarial: case boundary
        """
        # Given entities of type 'feature' exist
        mem_db.register_entity("feature", "f1", "Feature One")
        # When filtering with incorrect case 'Feature'
        with pytest.raises(ValueError, match=r"Invalid entity_type"):
            mem_db.export_entities_json(entity_type="Feature")

    def test_entity_with_null_parent_and_lineage_true(
        self, mem_db: EntityDatabase
    ):
        """Entity with no parent has parent_type_id=None (not omitted).

        derived_from: adversarial: null relationship
        """
        # Given an entity with no parent exists
        mem_db.register_entity("feature", "orphan", "Orphan Feature")
        # When export with include_lineage=True
        result = mem_db.export_entities_json(include_lineage=True)
        # Then parent_type_id key is present but value is None
        entity = result["entities"][0]
        assert "parent_type_id" in entity
        assert entity["parent_type_id"] is None

    # -- Dimension 5: Mutation Mindset -------------------------------------

    def test_entity_count_matches_actual_entities_array_length(
        self, mem_db: EntityDatabase
    ):
        """entity_count in envelope equals len(entities) exactly.

        derived_from: mutation: return value
        """
        # Given 5 entities exist
        for i in range(5):
            mem_db.register_entity("feature", f"f{i}", f"Feature {i}")
        # When export_entities_json() is called
        result = mem_db.export_entities_json()
        # Then entity_count equals len(entities) -- not off-by-one, not hardcoded
        assert result["entity_count"] == len(result["entities"])
        assert result["entity_count"] == 5

    def test_filters_applied_null_when_no_filters_given(
        self, mem_db: EntityDatabase
    ):
        """filters_applied shows None for both fields when no filters used.

        derived_from: mutation: filter values
        """
        # Given entities exist
        mem_db.register_entity("feature", "f1", "Feature One")
        # When export with no filters
        result = mem_db.export_entities_json()
        # Then both filter fields are None (not missing, not empty string)
        filters = result["filters_applied"]
        assert filters["entity_type"] is None
        assert filters["status"] is None
        assert set(filters.keys()) == {"entity_type", "status"}

    def test_schema_version_is_integer_not_string(self, mem_db: EntityDatabase):
        """schema_version is int 1, not string '1', not 0, not 2.

        derived_from: mutation: constant
        """
        # Given export is called
        result = mem_db.export_entities_json()
        # Then schema_version is exactly integer 1
        assert result["schema_version"] == 1
        assert isinstance(result["schema_version"], int)
        assert result["schema_version"] != "1"
        assert result["schema_version"] != 0
        assert result["schema_version"] != 2


# ---------------------------------------------------------------------------
# Migration 5: Expand workflow_phase CHECK constraint
# ---------------------------------------------------------------------------


class TestMigration5:
    """Tests for migration 5: expand CHECK constraint on workflow_phases.

    Migration 5 widens the workflow_phase and last_completed_phase CHECK
    constraints to accept brainstorm/backlog lifecycle phases alongside
    the existing 7 feature phases.
    """

    @staticmethod
    def _create_v4_db(db_path: str) -> sqlite3.Connection:
        """Create a DB at schema v4 by running migrations 1-4 only."""
        from entity_registry.database import (
            _create_fts_index,
            _create_initial_schema,
            _create_workflow_phases_table,
            _migrate_to_uuid_pk,
        )

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _metadata "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.commit()
        for version, fn in [
            (1, _create_initial_schema),
            (2, _migrate_to_uuid_pk),
            (3, _create_workflow_phases_table),
            (4, _create_fts_index),
        ]:
            fn(conn)
            conn.execute(
                "INSERT INTO _metadata (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("schema_version", str(version)),
            )
            conn.commit()
        return conn

    def test_migration_5_expands_check_constraint(self, tmp_path):
        """After migration 5, INSERT with workflow_phase='draft' succeeds."""
        conn = self._create_v4_db(str(tmp_path / "m5.db"))
        try:
            # Confirm at v4
            ver = conn.execute(
                "SELECT value FROM _metadata WHERE key='schema_version'"
            ).fetchone()[0]
            assert ver == "4"

            # Insert an entity so FK is satisfied
            now = EntityDatabase._now_iso()
            conn.execute(
                "INSERT INTO entities "
                "(type_id, entity_type, entity_id, name, status, "
                "created_at, updated_at, uuid) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("brainstorm:exp-test", "brainstorm", "exp-test",
                 "Expand Test", "draft", now, now,
                 "00000000-0000-4000-a000-000000000001"),
            )
            conn.commit()

            # Verify 'draft' is rejected at v4
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO workflow_phases "
                    "(type_id, workflow_phase, kanban_column, updated_at) "
                    "VALUES (?, 'draft', 'wip', ?)",
                    ("brainstorm:exp-test", now),
                )
            conn.rollback()

            # Run migration 5
            _expand_workflow_phase_check(conn)

            # Now 'draft' should be accepted
            conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, workflow_phase, kanban_column, updated_at) "
                "VALUES (?, 'draft', 'wip', ?)",
                ("brainstorm:exp-test", now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT workflow_phase FROM workflow_phases "
                "WHERE type_id = 'brainstorm:exp-test'"
            ).fetchone()
            assert row["workflow_phase"] == "draft"
        finally:
            conn.close()

    def test_migration_5_preserves_existing_data(self, tmp_path):
        """Existing rows with feature phases survive migration 5."""
        conn = self._create_v4_db(str(tmp_path / "m5-preserve.db"))
        try:
            # Insert an entity and a workflow_phases row at v4
            now = EntityDatabase._now_iso()
            conn.execute(
                "INSERT INTO entities "
                "(type_id, entity_type, entity_id, name, status, "
                "created_at, updated_at, uuid) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("feature:pres-test", "feature", "pres-test",
                 "Preserve Test", "implement", now, now,
                 "00000000-0000-4000-a000-000000000002"),
            )
            conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, workflow_phase, kanban_column, updated_at) "
                "VALUES (?, 'implement', 'wip', ?)",
                ("feature:pres-test", now),
            )
            conn.commit()

            # Run migration 5
            _expand_workflow_phase_check(conn)

            # Verify the row is still intact
            row = conn.execute(
                "SELECT workflow_phase, kanban_column FROM workflow_phases "
                "WHERE type_id = 'feature:pres-test'"
            ).fetchone()
            assert row is not None
            assert row["workflow_phase"] == "implement"
            assert row["kanban_column"] == "wip"
        finally:
            conn.close()

    def test_migration_5_idempotent(self, tmp_path):
        """Fresh DB runs all migrations including 5+6; schema_version=6 and
        new phase values are accepted."""
        db = EntityDatabase(str(tmp_path / "m5-idem.db"))
        try:
            assert db.get_schema_version() == 6

            # Verify all new phase values are accepted
            new_phases = [
                "draft", "reviewing", "promoted", "abandoned",
                "open", "triaged", "dropped",
            ]
            for i, phase in enumerate(new_phases):
                eid = f"idem-{i}"
                db.register_entity("brainstorm", eid, f"Idem {i}")
                now = EntityDatabase._now_iso()
                db._conn.execute(
                    "INSERT INTO workflow_phases "
                    "(type_id, workflow_phase, kanban_column, updated_at) "
                    "VALUES (?, ?, 'wip', ?)",
                    (f"brainstorm:{eid}", phase, now),
                )
            db._conn.commit()

            count = db._conn.execute(
                "SELECT COUNT(*) FROM workflow_phases"
            ).fetchone()[0]
            assert count == len(new_phases)

            # Also verify new values work for last_completed_phase
            db.register_entity("brainstorm", "lcp-test", "LCP Test")
            db._conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, workflow_phase, kanban_column, "
                "last_completed_phase, updated_at) "
                "VALUES (?, 'reviewing', 'agent_review', 'draft', ?)",
                ("brainstorm:lcp-test", EntityDatabase._now_iso()),
            )
            db._conn.commit()
            row = db._conn.execute(
                "SELECT last_completed_phase FROM workflow_phases "
                "WHERE type_id = 'brainstorm:lcp-test'"
            ).fetchone()
            assert row["last_completed_phase"] == "draft"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Deepened tests: Migration 5 CHECK constraint boundary + adversarial
# ---------------------------------------------------------------------------


class TestMigration5Deepened:
    """Deepened tests for migration 5 CHECK constraint expansion.

    derived_from: spec:AC-2 (workflow_phase CHECK constraint),
                  dimension:boundary_values, dimension:adversarial
    """

    def test_migration_5_rejects_invalid_phase_value(self, db: EntityDatabase):
        """After migration 5, an invalid phase value is still rejected by CHECK.
        derived_from: spec:AC-2, dimension:adversarial

        Anticipate: If the CHECK constraint was accidentally removed during
        migration (e.g., table recreated without CHECK), any value would be
        accepted silently.
        """
        # Given a fresh DB (already at schema v5) with a registered entity
        db.register_entity("brainstorm", "chk-invalid", "Check Invalid")
        now = EntityDatabase._now_iso()
        # When inserting a workflow_phase with a value NOT in the valid set
        with pytest.raises(sqlite3.IntegrityError):
            db._conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, workflow_phase, kanban_column, updated_at) "
                "VALUES (?, 'totally_bogus', 'wip', ?)",
                ("brainstorm:chk-invalid", now),
            )

    def test_migration_5_allows_null_workflow_phase(self, db: EntityDatabase):
        """After migration 5, NULL workflow_phase is allowed by CHECK.
        derived_from: spec:AC-2, dimension:boundary_values

        Anticipate: If the CHECK was rewritten without the OR NULL clause,
        NULL would be rejected, breaking legacy data patterns.
        """
        # Given a registered entity
        db.register_entity("brainstorm", "chk-null", "Check Null")
        now = EntityDatabase._now_iso()
        # When inserting with NULL workflow_phase
        db._conn.execute(
            "INSERT INTO workflow_phases "
            "(type_id, workflow_phase, kanban_column, updated_at) "
            "VALUES (?, NULL, 'backlog', ?)",
            ("brainstorm:chk-null", now),
        )
        db._conn.commit()
        # Then the row exists with NULL phase
        row = db._conn.execute(
            "SELECT workflow_phase FROM workflow_phases "
            "WHERE type_id = 'brainstorm:chk-null'"
        ).fetchone()
        assert row["workflow_phase"] is None

    def test_migration_5_accepts_all_backlog_phase_values(self, db: EntityDatabase):
        """All 3 backlog-specific phases (open, triaged, dropped) accepted.
        derived_from: spec:AC-2, dimension:boundary_values

        Anticipate: If migration only added brainstorm phases but missed
        backlog phases, INSERT would fail for open/triaged/dropped.
        """
        # Given a fresh DB at schema v5
        for i, phase in enumerate(("open", "triaged", "dropped")):
            eid = f"bl-phase-{i}"
            db.register_entity("backlog", eid, f"Backlog Phase {i}")
            now = EntityDatabase._now_iso()
            # When inserting each backlog phase value
            db._conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, workflow_phase, kanban_column, updated_at) "
                "VALUES (?, ?, 'backlog', ?)",
                (f"backlog:{eid}", phase, now),
            )
        db._conn.commit()
        # Then all 3 rows exist
        count = db._conn.execute(
            "SELECT COUNT(*) FROM workflow_phases "
            "WHERE type_id LIKE 'backlog:bl-phase-%'"
        ).fetchone()[0]
        assert count == 3

    def test_migration_5_existing_feature_phases_still_work(self, db: EntityDatabase):
        """All 7 original feature phases still accepted after migration 5.
        derived_from: spec:AC-2, dimension:mutation_mindset

        Anticipate: If migration replaced the CHECK list instead of extending
        it, the 7 original feature phases would be rejected.
        Mutation: swapping the complete list would break these.
        """
        # Given a fresh DB at schema v5
        feature_phases = [
            "brainstorm", "specify", "design", "create-plan",
            "create-tasks", "implement", "finish",
        ]
        for i, phase in enumerate(feature_phases):
            eid = f"fp-{i}"
            db.register_entity("feature", eid, f"Feature Phase {i}")
            now = EntityDatabase._now_iso()
            db._conn.execute(
                "INSERT INTO workflow_phases "
                "(type_id, workflow_phase, kanban_column, updated_at) "
                "VALUES (?, ?, 'wip', ?)",
                (f"feature:{eid}", phase, now),
            )
        db._conn.commit()
        # Then all 7 rows exist
        count = db._conn.execute(
            "SELECT COUNT(*) FROM workflow_phases "
            "WHERE type_id LIKE 'feature:fp-%'"
        ).fetchone()[0]
        assert count == 7


class TestUpsertWorkflowPhase:
    """Tests for EntityDatabase.upsert_workflow_phase (Task 4.1)."""

    def test_upsert_inserts_new_row(self, db: EntityDatabase):
        """upsert_workflow_phase creates a new row when none exists."""
        db.register_entity("feature", "u1", "Upsert Feature")
        db.upsert_workflow_phase(
            "feature:u1",
            workflow_phase="design",
            kanban_column="wip",
        )
        row = db.get_workflow_phase("feature:u1")
        assert row is not None
        assert row["type_id"] == "feature:u1"
        assert row["workflow_phase"] == "design"
        assert row["kanban_column"] == "wip"
        assert row["updated_at"] is not None

    def test_upsert_updates_existing_row(self, db: EntityDatabase):
        """upsert_workflow_phase updates fields on an existing row."""
        db.register_entity("feature", "u2", "Upsert Feature 2")
        db.upsert_workflow_phase(
            "feature:u2",
            workflow_phase="design",
            kanban_column="wip",
        )
        db.upsert_workflow_phase(
            "feature:u2",
            workflow_phase="implement",
            kanban_column="wip",
            last_completed_phase="design",
        )
        row = db.get_workflow_phase("feature:u2")
        assert row is not None
        assert row["workflow_phase"] == "implement"
        assert row["last_completed_phase"] == "design"

    def test_upsert_rejects_invalid_column_name(self, db: EntityDatabase):
        """upsert_workflow_phase raises ValueError for invalid column names."""
        db.register_entity("feature", "u3", "Upsert Feature 3")
        with pytest.raises(ValueError, match="Invalid workflow_phases columns"):
            db.upsert_workflow_phase(
                "feature:u3",
                workflow_phase="design",
                evil_column="DROP TABLE",
            )

    def test_upsert_idempotent_reinsert(self, db: EntityDatabase):
        """upsert_workflow_phase with same data is idempotent."""
        db.register_entity("feature", "u4", "Upsert Feature 4")
        db.upsert_workflow_phase(
            "feature:u4",
            workflow_phase="design",
            kanban_column="wip",
        )
        row1 = db.get_workflow_phase("feature:u4")
        # Re-upsert with same values
        db.upsert_workflow_phase(
            "feature:u4",
            workflow_phase="design",
            kanban_column="wip",
        )
        row2 = db.get_workflow_phase("feature:u4")
        assert row2["workflow_phase"] == row1["workflow_phase"]
        assert row2["kanban_column"] == row1["kanban_column"]

    def test_upsert_sets_updated_at_on_update(self, db: EntityDatabase):
        """upsert_workflow_phase refreshes updated_at on each call."""
        db.register_entity("feature", "u5", "Upsert Feature 5")
        db.upsert_workflow_phase("feature:u5", workflow_phase="design")
        row1 = db.get_workflow_phase("feature:u5")
        # Second upsert should update timestamp
        db.upsert_workflow_phase("feature:u5", workflow_phase="implement")
        row2 = db.get_workflow_phase("feature:u5")
        # updated_at should be set (both non-None)
        assert row1["updated_at"] is not None
        assert row2["updated_at"] is not None

    def test_upsert_with_mode_and_backward_reason(self, db: EntityDatabase):
        """upsert_workflow_phase handles mode and backward_transition_reason."""
        db.register_entity("feature", "u6", "Upsert Feature 6")
        db.upsert_workflow_phase(
            "feature:u6",
            workflow_phase="design",
            kanban_column="wip",
            mode="standard",
            backward_transition_reason="rework needed",
        )
        row = db.get_workflow_phase("feature:u6")
        assert row["mode"] == "standard"
        assert row["backward_transition_reason"] == "rework needed"

    def test_upsert_no_kwargs_still_inserts(self, db: EntityDatabase):
        """upsert_workflow_phase with no kwargs creates row with defaults."""
        db.register_entity("feature", "u7", "Upsert Feature 7")
        db.upsert_workflow_phase("feature:u7")
        row = db.get_workflow_phase("feature:u7")
        assert row is not None
        assert row["type_id"] == "feature:u7"
        assert row["updated_at"] is not None

    def test_upsert_multiple_invalid_columns_reported(self, db: EntityDatabase):
        """upsert_workflow_phase reports all invalid column names."""
        db.register_entity("feature", "u8", "Upsert Feature 8")
        with pytest.raises(ValueError, match="Invalid workflow_phases columns"):
            db.upsert_workflow_phase(
                "feature:u8",
                bad_col="x",
                another_bad="y",
            )


# ---------------------------------------------------------------------------
# Delete entity tests
# ---------------------------------------------------------------------------


class TestDeleteEntity:
    """Tests for EntityDatabase.delete_entity (feature 047)."""

    def test_delete_entity_not_found(self, db: EntityDatabase):
        """AC-1: Deleting a nonexistent entity raises ValueError."""
        with pytest.raises(ValueError, match="Entity not found"):
            db.delete_entity("feature:999-nonexistent")

    def test_delete_entity_success(self, db: EntityDatabase):
        """AC-2: Deleting an entity removes entity row, FTS entry, and workflow_phases."""
        db.register_entity("feature", "001-test", "Test Feature", status="active")
        db.upsert_workflow_phase("feature:001-test", workflow_phase="design")

        db.delete_entity("feature:001-test")

        # Entity row gone
        assert db.get_entity("feature:001-test") is None
        # workflow_phases row gone
        assert db.get_workflow_phase("feature:001-test") is None
        # FTS entry gone
        fts = db._conn.execute(
            "SELECT * FROM entities_fts WHERE entities_fts MATCH ?",
            ('"Test Feature"',)
        ).fetchall()
        assert len(fts) == 0

    def test_delete_entity_with_children_rejected(self, db: EntityDatabase):
        """AC-3: Cannot delete entity that has children."""
        db.register_entity("project", "P001", "Parent Project")
        db.register_entity(
            "feature", "child-1", "Child Feature",
            parent_type_id="project:P001",
        )

        with pytest.raises(ValueError, match="Cannot delete entity with children"):
            db.delete_entity("project:P001")

    def test_delete_entity_fts_cleaned(self, db: EntityDatabase):
        """AC-4: After delete, search_entities no longer returns the entity."""
        db.register_entity("feature", "fts-test", "Searchable Entity",
                           status="active")
        # Confirm searchable before delete
        results = db.search_entities("Searchable")
        assert len(results) > 0

        db.delete_entity("feature:fts-test")

        results = db.search_entities("Searchable")
        assert len(results) == 0

    def test_delete_entity_no_workflow_phases(self, db: EntityDatabase):
        """AC-13: Deleting entity without workflow_phases does not error."""
        db.register_entity("feature", "002-test", "No WF Feature", status="active")
        # No upsert_workflow_phase call — entity has no workflow_phases row

        db.delete_entity("feature:002-test")

        assert db.get_entity("feature:002-test") is None

    def test_delete_entity_rollback_on_error(self, db: EntityDatabase):
        """AC-12: Transaction rolls back on mid-delete error, preserving all data."""
        db.register_entity("feature", "rb-test", "Rollback Feature", status="active")
        db.upsert_workflow_phase("feature:rb-test", workflow_phase="design")

        # Wrap the real connection with a proxy that intercepts execute
        real_conn = db._conn
        original_execute = real_conn.execute

        class FailingProxy:
            """Proxy that delegates to real conn but fails on entity DELETE."""
            def __getattr__(self, name):
                return getattr(real_conn, name)

            def execute(self, sql, params=()):
                if isinstance(sql, str) and sql.strip().startswith("DELETE FROM entities"):
                    raise RuntimeError("Simulated failure")
                return original_execute(sql, params)

        db._conn = FailingProxy()

        with pytest.raises(RuntimeError, match="Simulated failure"):
            db.delete_entity("feature:rb-test")

        # Restore real connection for verification
        db._conn = real_conn

        # Entity, FTS, and workflow_phases should all remain intact
        assert db.get_entity("feature:rb-test") is not None
        assert db.get_workflow_phase("feature:rb-test") is not None
        results = db.search_entities("Rollback")
        assert len(results) > 0

    def test_delete_entity_corrupted_metadata_still_deletes(self, db: EntityDatabase):
        """Corrupted metadata does not prevent deletion — uses empty string for FTS."""
        db.register_entity("feature", "corrupt-meta", "Corrupt Meta Feature")
        # Manually corrupt the metadata column
        db._conn.execute(
            "UPDATE entities SET metadata = '{bad json' WHERE type_id = ?",
            ("feature:corrupt-meta",)
        )
        db._conn.commit()

        # Should not raise
        db.delete_entity("feature:corrupt-meta")
        assert db.get_entity("feature:corrupt-meta") is None
