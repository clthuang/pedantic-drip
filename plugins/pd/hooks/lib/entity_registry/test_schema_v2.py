"""Tests for entity_registry.schema_v2 (dark-shipped v2 core schema/bootstrap).

Covers design 118 Testing Strategy #1-6: bootstrap shape (uuid PKs, UNIQUE
index sweep), business-key non-uniqueness, the DDL registry extension point,
bootstrap idempotency, the one-version-write source discipline, and the
PRAGMA contract (WAL / foreign_keys / busy_timeout) on the connection
bootstrap_v2 returns.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from entity_registry import schema_v2

# The 4 core tables carrying a uuid7 TEXT primary key. `_metadata` is
# deliberately excluded — it's key/value bookkeeping with PK `key` (task 4's
# own DDL), not an entity-shaped table.
_CORE_TABLES_WITH_UUID_PK = ("workspaces", "entities", "entity_relations", "sequences")

# Business-key / human-readable fields FR-4 forbids UNIQUE constraints on.
_FORBIDDEN_UNIQUE_COLUMNS = {"type_id", "slug", "name", "display_name", "display"}

_NOW = "2026-01-01T00:00:00Z"

# Matches an executable SQL write statement (INSERT/UPDATE/REPLACE) that
# targets _metadata. Deliberately tight (requires the real SQL shape, e.g.
# "INSERT ... INTO _metadata" / "UPDATE _metadata" / "REPLACE INTO
# _metadata") rather than loose keyword co-occurrence, so prose mentioning
# both a write verb and "_metadata" in the same paragraph can't false-positive.
_METADATA_WRITE_RE = re.compile(
    r"\bINSERT(?:\s+OR\s+\w+)?\s+INTO\s+_metadata\b"
    r"|\bUPDATE\s+_metadata\b"
    r"|\bREPLACE\s+INTO\s+_metadata\b",
    re.IGNORECASE,
)


def _strip_comments(source: str) -> str:
    """Strip '--' SQL comments and '#' Python comments, line by line.

    Adequate (not a general SQL/Python parser) because we control the
    source being scanned: neither language construct spans multiple lines
    in schema_v2.py, and no string literal in that file contains a literal
    '--' or '#'.
    """
    cleaned_lines = []
    for line in source.splitlines():
        sql_comment_at = line.find("--")
        if sql_comment_at != -1:
            line = line[:sql_comment_at]
        hash_comment_at = line.find("#")
        if hash_comment_at != -1:
            line = line[:hash_comment_at]
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _unique_indexes(conn: sqlite3.Connection):
    """Yield (table, index_name, covered_columns) for every UNIQUE index
    across every table in *conn*, including implicit PK autoindexes."""
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    for table in tables:
        for index_row in conn.execute(f"PRAGMA index_list({table})").fetchall():
            index_name, is_unique = index_row[1], index_row[2]
            if not is_unique:
                continue
            covered_columns = frozenset(
                info_row[2]
                for info_row in conn.execute(
                    f"PRAGMA index_info({index_name})"
                ).fetchall()
            )
            yield table, index_name, covered_columns


@pytest.fixture(autouse=True)
def _reset_ddl_registry():
    """Snapshot/restore DDL_REGISTRY around every test.

    It's a module-level list mutated by register_ddl() — without this,
    a test that registers a "dummy" owner would leak that registration
    into every test that runs after it in the same process.
    """
    original_registry = list(schema_v2.DDL_REGISTRY)
    yield
    schema_v2.DDL_REGISTRY[:] = original_registry


@pytest.fixture
def bootstrapped_conn(tmp_path):
    """A connection from a fresh bootstrap_v2() call, closed after the test."""
    conn = schema_v2.bootstrap_v2(str(tmp_path / "v2.db"))
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Design test #1: bootstrap shape — uuid PKs + UNIQUE index sweep
# ---------------------------------------------------------------------------
class TestBootstrapShape:
    def test_uuid_text_primary_key_on_core_tables(self, bootstrapped_conn):
        """Each of the 4 core tables has exactly one PK column, named
        'uuid', typed TEXT."""
        for table in _CORE_TABLES_WITH_UUID_PK:
            columns = bootstrapped_conn.execute(f"PRAGMA table_info({table})").fetchall()
            pk_columns = [col for col in columns if col[5] == 1]
            assert len(pk_columns) == 1, f"{table} must have exactly one PK column"
            pk_name, pk_type = pk_columns[0][1], pk_columns[0][2]
            assert pk_name == "uuid", f"{table} PK must be 'uuid', got {pk_name!r}"
            assert pk_type.upper() == "TEXT", f"{table}.uuid must be TEXT, got {pk_type!r}"

    def test_metadata_primary_key_is_key_not_uuid(self, bootstrapped_conn):
        """_metadata is excluded from the uuid-PK sweep: its PK is `key`
        (key/value bookkeeping, per this task's own DDL)."""
        columns = bootstrapped_conn.execute("PRAGMA table_info(_metadata)").fetchall()
        pk_columns = [col for col in columns if col[5] == 1]
        assert len(pk_columns) == 1
        assert pk_columns[0][1] == "key"
        assert not any(col[1] == "uuid" for col in columns)

    def test_no_unique_index_covers_business_key_columns(self, bootstrapped_conn):
        """Sweep every UNIQUE index (by covered column set, not per-table
        hardcode): only idx_relations_dedup (from_uuid, to_uuid, kind) is
        allowed. No UNIQUE index may cover type_id/slug/name/display fields
        (FR-4: no uniqueness on human-readable business keys)."""
        seen_dedup_index = False
        for table, index_name, covered_columns in _unique_indexes(bootstrapped_conn):
            if index_name == "idx_relations_dedup":
                assert table == "entity_relations"
                assert covered_columns == {"from_uuid", "to_uuid", "kind"}
                seen_dedup_index = True
                continue
            forbidden_hit = covered_columns & _FORBIDDEN_UNIQUE_COLUMNS
            assert not forbidden_hit, (
                f"UNIQUE index {index_name!r} on {table} covers business-key "
                f"column(s) {forbidden_hit} — FR-4 forbids uniqueness on "
                f"human-readable fields"
            )
        assert seen_dedup_index, "expected idx_relations_dedup to exist"


# ---------------------------------------------------------------------------
# Design test #2: business-key non-uniqueness
# ---------------------------------------------------------------------------
class TestBusinessKeyNonUniqueness:
    def test_duplicate_type_id_same_workspace_both_insert_succeed(self, bootstrapped_conn):
        """Two entities sharing the same (type_id, workspace) both insert
        without error — there is no UNIQUE constraint on type_id (FR-4)."""
        conn = bootstrapped_conn
        workspace_uuid = "workspace-uuid-1"
        conn.execute(
            "INSERT INTO workspaces (uuid, project_root, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (workspace_uuid, "/tmp/project", _NOW, _NOW),
        )
        for entity_uuid in ("entity-uuid-1", "entity-uuid-2"):
            conn.execute(
                "INSERT INTO entities (uuid, workspace_uuid, type, kind, "
                "lifecycle_class, type_id, name, artifact_path, parent_uuid, "
                "created_at, updated_at, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entity_uuid, workspace_uuid, "feature", "feature",
                    "artifact", "shared-type-id", "Some Name", None, None,
                    _NOW, _NOW, None,
                ),
            )
        row_count = conn.execute(
            "SELECT COUNT(*) FROM entities WHERE type_id = ?", ("shared-type-id",)
        ).fetchone()[0]
        assert row_count == 2


# ---------------------------------------------------------------------------
# Design test #3: DDL registry extension point
# ---------------------------------------------------------------------------
class TestDdlRegistryExtensionPoint:
    def test_register_ddl_entry_is_applied_by_bootstrap(self, tmp_path):
        schema_v2.register_ddl(
            "dummy", "CREATE TABLE IF NOT EXISTS dummy_t (uuid TEXT PRIMARY KEY)"
        )
        conn = schema_v2.bootstrap_v2(str(tmp_path / "v2.db"))
        try:
            table_names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            assert "dummy_t" in table_names
        finally:
            conn.close()

    def test_register_ddl_duplicate_owner_raises(self):
        schema_v2.register_ddl("dummy", "CREATE TABLE IF NOT EXISTS dummy_t (uuid TEXT PRIMARY KEY)")
        with pytest.raises(ValueError):
            schema_v2.register_ddl(
                "dummy", "CREATE TABLE IF NOT EXISTS other_t (uuid TEXT PRIMARY KEY)"
            )


# ---------------------------------------------------------------------------
# Design test #4: bootstrap idempotency
# ---------------------------------------------------------------------------
class TestBootstrapIdempotency:
    def test_double_bootstrap_no_error_version_unchanged_single_row(self, tmp_path):
        db_path = str(tmp_path / "v2.db")
        first_conn = schema_v2.bootstrap_v2(db_path)
        first_conn.close()

        second_conn = schema_v2.bootstrap_v2(db_path)  # must not raise
        try:
            rows = second_conn.execute(
                "SELECT value FROM _metadata WHERE key = 'schema_version'"
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == str(schema_v2.V2_SCHEMA_VERSION)

            total_metadata_rows = second_conn.execute(
                "SELECT COUNT(*) FROM _metadata"
            ).fetchone()[0]
            assert total_metadata_rows == 1
        finally:
            second_conn.close()


# ---------------------------------------------------------------------------
# Design test #5: one-version-location source discipline
# ---------------------------------------------------------------------------
class TestSchemaVersionWriteDiscipline:
    def test_exactly_one_metadata_write_statement_in_source(self):
        source = Path(schema_v2.__file__).read_text()
        cleaned_source = _strip_comments(source)
        matches = _METADATA_WRITE_RE.findall(cleaned_source)
        assert len(matches) == 1, (
            f"expected exactly one executable write statement targeting "
            f"_metadata, found {len(matches)}: {matches}"
        )


# ---------------------------------------------------------------------------
# Design test #6: PRAGMA contract on the connection bootstrap_v2 returns
# ---------------------------------------------------------------------------
class TestConnectionPragmas:
    def test_wal_mode_on_returned_connection(self, bootstrapped_conn):
        journal_mode = bootstrapped_conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode.lower() == "wal"

    def test_foreign_keys_enforced_on_returned_connection(self, bootstrapped_conn):
        foreign_keys_status = bootstrapped_conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert foreign_keys_status == 1

        # Non-vacuous: an FK-violating insert must actually be rejected.
        with pytest.raises(sqlite3.IntegrityError):
            bootstrapped_conn.execute(
                "INSERT INTO entities (uuid, workspace_uuid, type, kind, "
                "lifecycle_class, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "entity-uuid-orphan", "nonexistent-workspace-uuid",
                    "feature", "feature", "artifact", _NOW, _NOW,
                ),
            )

    def test_busy_timeout_value_on_returned_connection(self, bootstrapped_conn):
        busy_timeout_ms = bootstrapped_conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert busy_timeout_ms == schema_v2._BUSY_TIMEOUT_MS
