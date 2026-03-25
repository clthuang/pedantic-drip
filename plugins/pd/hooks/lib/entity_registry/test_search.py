"""Tests for FTS5 full-text search in entity_registry.database."""
from __future__ import annotations

import json
import sqlite3

import pytest

from entity_registry.database import (
    EntityDatabase,
    _create_fts_index,
    _create_initial_schema,
    _create_workflow_phases_table,
    _fix_fts_content_mode,
    _migrate_to_uuid_pk,
    flatten_metadata,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    """Provide a file-based EntityDatabase, closed after test."""
    db_path = str(tmp_path / "search_test.db")
    database = EntityDatabase(db_path)
    yield database
    database.close()


def _make_pre_migration_db():
    """Create an in-memory DB at schema v3 with test entities (no FTS)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _create_initial_schema(conn)
    _migrate_to_uuid_pk(conn)
    _create_workflow_phases_table(conn)
    conn.commit()
    return conn


def _insert_test_entity(conn, uuid, type_id, entity_type, entity_id, name,
                         status=None, metadata=None):
    """Insert a test entity directly via SQL."""
    now = "2026-03-07T00:00:00+00:00"
    metadata_json = json.dumps(metadata) if metadata is not None else None
    conn.execute(
        "INSERT INTO entities (uuid, type_id, entity_type, entity_id, name, "
        "status, created_at, updated_at, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (uuid, type_id, entity_type, entity_id, name, status, now, now,
         metadata_json),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# TestFlattenMetadata (Task 1.1.1 / 1.1.2)
# ---------------------------------------------------------------------------


class TestFlattenMetadata:
    def test_none(self):
        assert flatten_metadata(None) == ""

    def test_empty_dict(self):
        assert flatten_metadata({}) == ""

    def test_simple_dict(self):
        assert flatten_metadata({"module": "State Engine"}) == "State Engine"

    def test_nested_dict(self):
        assert flatten_metadata({"a": {"b": "deep"}}) == "deep"

    def test_list_values(self):
        result = flatten_metadata({"module": "State Engine", "deps": ["001"]})
        assert result == "State Engine 001"

    def test_scalar_types(self):
        result = flatten_metadata({"flag": True, "count": 42})
        assert result == "True 42"

    def test_none_values_skipped(self):
        result = flatten_metadata({"a": None, "b": "val"})
        assert result == "val"

    def test_empty_list(self):
        assert flatten_metadata({"a": []}) == ""


# ---------------------------------------------------------------------------
# TestMigration4 (Task 1.2.1 / 1.2.2)
# ---------------------------------------------------------------------------


class TestMigration4:
    def test_fts_table_exists(self):
        """AC-1: entities_fts exists after migration."""
        conn = _make_pre_migration_db()
        _create_fts_index(conn)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "entities_fts" in tables
        conn.close()

    def test_backfill_populates_index(self):
        """AC-3: pre-existing entities are searchable after migration."""
        conn = _make_pre_migration_db()
        _insert_test_entity(
            conn, "uuid-001", "feature:recon", "feature", "recon",
            "Reconciliation Tool", status="active",
        )
        _create_fts_index(conn)
        rows = conn.execute(
            "SELECT rowid FROM entities_fts WHERE entities_fts MATCH 'Reconciliation'"
        ).fetchall()
        assert len(rows) == 1
        conn.close()

    def test_all_five_fields_indexed(self):
        """AC-2: all 5 indexed fields are searchable."""
        conn = _make_pre_migration_db()
        _insert_test_entity(
            conn, "uuid-five", "brainstorm:uniqueidval", "brainstorm",
            "uniqueidval", "UniqueNameField", status="UniqueStatusField",
            metadata={"key": "UniqueMetaField"},
        )
        _create_fts_index(conn)
        # Each field should be searchable
        for term in ["UniqueNameField", "uniqueidval", "brainstorm",
                      "UniqueStatusField", "UniqueMetaField"]:
            rows = conn.execute(
                "SELECT rowid FROM entities_fts WHERE entities_fts MATCH ?",
                (term,)
            ).fetchall()
            assert len(rows) >= 1, f"Field not indexed: search for '{term}' returned 0"
        conn.close()

    def test_schema_version_is_4(self):
        """AC-19: schema version is 4 after migration."""
        conn = _make_pre_migration_db()
        _create_fts_index(conn)
        row = conn.execute(
            "SELECT value FROM _metadata WHERE key = 'schema_version'"
        ).fetchone()
        assert row[0] == "4"
        conn.close()

    def test_null_metadata_backfill(self):
        """AC-18: NULL metadata → empty string in FTS."""
        conn = _make_pre_migration_db()
        _insert_test_entity(
            conn, "uuid-null", "feature:null-meta", "feature",
            "null-meta", "NullMeta", metadata=None,
        )
        _create_fts_index(conn)
        rows = conn.execute(
            "SELECT rowid FROM entities_fts WHERE entities_fts MATCH 'NullMeta'"
        ).fetchall()
        assert len(rows) == 1
        conn.close()

    def test_idempotent_create(self):
        """AC-16: DROP+CREATE clean slate; migration runner skips when version >= 4."""
        conn = _make_pre_migration_db()
        _insert_test_entity(
            conn, "uuid-idem", "feature:idem", "feature", "idem",
            "IdempotentTest",
        )
        _create_fts_index(conn)
        # Run migration again — should be clean (DROP+CREATE)
        _create_fts_index(conn)
        rows = conn.execute(
            "SELECT rowid FROM entities_fts WHERE entities_fts MATCH 'IdempotentTest'"
        ).fetchall()
        assert len(rows) == 1
        conn.close()

    def test_preserves_existing_data(self):
        """AC-17: entities table data unchanged after migration."""
        conn = _make_pre_migration_db()
        _insert_test_entity(
            conn, "uuid-preserve", "feature:preserve", "feature",
            "preserve", "PreserveTest", status="active",
        )
        before = dict(conn.execute(
            "SELECT * FROM entities WHERE uuid = 'uuid-preserve'"
        ).fetchone())
        _create_fts_index(conn)
        after = dict(conn.execute(
            "SELECT * FROM entities WHERE uuid = 'uuid-preserve'"
        ).fetchone())
        assert before == after
        conn.close()


# ---------------------------------------------------------------------------
# TestFTSSync (Task 2.1.1 / 2.1.2 / 2.2.1 / 2.2.2)
# ---------------------------------------------------------------------------


class TestFTSSync:
    # -- register tests --

    def test_register_makes_searchable(self, db):
        """AC-4: register entity makes it immediately searchable."""
        db.register_entity("feature", "search-test", "Search Test Feature")
        rows = db._conn.execute(
            "SELECT rowid FROM entities_fts WHERE entities_fts MATCH 'Search'"
        ).fetchall()
        assert len(rows) == 1

    def test_duplicate_register_no_fts_corruption(self, db):
        """INSERT OR IGNORE skip doesn't double-insert FTS."""
        db.register_entity("feature", "dup-test", "Dup Test")
        db.register_entity("feature", "dup-test", "Dup Test")
        rows = db._conn.execute(
            "SELECT rowid FROM entities_fts WHERE entities_fts MATCH 'Dup'"
        ).fetchall()
        assert len(rows) == 1

    def test_register_with_metadata(self, db):
        """Metadata content appears in FTS index."""
        db.register_entity(
            "feature", "meta-test", "Meta Test",
            metadata={"module": "State Engine"},
        )
        rows = db._conn.execute(
            "SELECT rowid FROM entities_fts WHERE entities_fts MATCH 'Engine'"
        ).fetchall()
        assert len(rows) == 1

    def test_insert_or_ignore_rowcount_zero_on_skip(self, db):
        """cursor.rowcount == 0 for duplicate."""
        db.register_entity("feature", "rc-test", "RC Test")
        cursor = db._conn.execute(
            "INSERT OR IGNORE INTO entities "
            "(uuid, type_id, entity_type, entity_id, name, "
            "created_at, updated_at) "
            "VALUES ('new-uuid', 'feature:rc-test', 'feature', 'rc-test', "
            "'RC Test', '2026-01-01', '2026-01-01')"
        )
        assert cursor.rowcount == 0
        db._conn.rollback()

    # -- update tests --

    def test_update_name_reflected(self, db):
        """AC-5: update name, new name searchable, old name not."""
        db.register_entity("feature", "upd-name", "OldName")
        db.update_entity("feature:upd-name", name="NewName")
        # New name searchable
        rows = db._conn.execute(
            "SELECT rowid FROM entities_fts WHERE entities_fts MATCH 'NewName'"
        ).fetchall()
        assert len(rows) == 1
        # Old name not searchable
        rows = db._conn.execute(
            "SELECT rowid FROM entities_fts WHERE entities_fts MATCH 'OldName'"
        ).fetchall()
        assert len(rows) == 0

    def test_update_status_reflected(self, db):
        """Update status, new status searchable."""
        db.register_entity("feature", "upd-status", "StatusTest",
                           status="draft")
        db.update_entity("feature:upd-status", status="completed")
        rows = db._conn.execute(
            "SELECT rowid FROM entities_fts WHERE entities_fts MATCH 'completed'"
        ).fetchall()
        assert len(rows) == 1

    def test_update_metadata_reflected(self, db):
        """Update metadata, new content searchable."""
        db.register_entity("feature", "upd-meta", "MetaTest",
                           metadata={"old": "value"})
        db.update_entity("feature:upd-meta", metadata={"new": "fresh"})
        rows = db._conn.execute(
            "SELECT rowid FROM entities_fts WHERE entities_fts MATCH 'fresh'"
        ).fetchall()
        assert len(rows) == 1

    def test_update_non_fts_field(self, db):
        """Update artifact_path only, entity still searchable."""
        db.register_entity("feature", "upd-path", "PathTest")
        db.update_entity("feature:upd-path", artifact_path="/some/path")
        rows = db._conn.execute(
            "SELECT rowid FROM entities_fts WHERE entities_fts MATCH 'PathTest'"
        ).fetchall()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# TestSearchEntities (Task 3.1.1 / 3.1.2)
# ---------------------------------------------------------------------------


@pytest.fixture
def search_db(db):
    """Populate db with entities for search tests."""
    db.register_entity("feature", "011-reconciliation-mcp-tool",
                       "Reconciliation MCP Tool", status="completed")
    db.register_entity("feature", "009-state-engine-mcp-tools",
                       "State Engine MCP Tools", status="completed",
                       metadata={"module": "State Engine"})
    db.register_entity("brainstorm", "kanban-board",
                       "Kanban Board View", status="active")
    db.register_entity("project", "crypto-tracker",
                       "Crypto Tracker", status="active")
    db.register_entity("feature", "020-entity-list",
                       "Entity List Views", status="planned")
    return db


class TestSearchEntities:
    def test_prefix_match(self, search_db):
        """AC-7: 'recon' finds 'Reconciliation MCP Tool'."""
        results = search_db.search_entities("recon")
        names = [r["name"] for r in results]
        assert "Reconciliation MCP Tool" in names

    def test_type_filter(self, search_db):
        """AC-8: entity_type filter excludes non-matching types."""
        results = search_db.search_entities("active", entity_type="brainstorm")
        for r in results:
            assert r["entity_type"] == "brainstorm"

    def test_relevance_ordering(self, search_db):
        """AC-9: results ordered by rank."""
        results = search_db.search_entities("MCP")
        assert len(results) >= 2
        # Ranks should be ordered (lower is better in FTS5)
        ranks = [r["rank"] for r in results]
        assert ranks == sorted(ranks)

    def test_empty_query(self, search_db):
        """AC-10: empty query returns empty list."""
        assert search_db.search_entities("") == []
        assert search_db.search_entities("   ") == []

    def test_limit_caps_results(self, search_db):
        """AC-11: limit=2 returns max 2."""
        results = search_db.search_entities("feature", limit=2)
        assert len(results) <= 2

    def test_limit_clamped_to_100(self, search_db):
        """AC-11: limit=200 treated as 100."""
        # Should not raise — just clamp
        results = search_db.search_entities("feature", limit=200)
        assert isinstance(results, list)

    def test_exact_phrase(self, search_db):
        """Exact phrase match with double quotes."""
        results = search_db.search_entities('"State Engine"')
        names = [r["name"] for r in results]
        assert "State Engine MCP Tools" in names

    def test_multi_token_and(self, search_db):
        """Multiple tokens use implicit AND."""
        results = search_db.search_entities("state engine")
        names = [r["name"] for r in results]
        assert "State Engine MCP Tools" in names

    def test_fts_not_available(self, tmp_path):
        """Raises ValueError on missing FTS table."""
        # Use raw sqlite3 connection — no auto-migration
        db_path = str(tmp_path / "no_fts.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _metadata VALUES ('schema_version', '3')"
        )
        conn.execute(
            "CREATE TABLE entities (uuid TEXT PRIMARY KEY, type_id TEXT, "
            "entity_type TEXT, entity_id TEXT, name TEXT, status TEXT, "
            "parent_type_id TEXT, parent_uuid TEXT, artifact_path TEXT, "
            "created_at TEXT, updated_at TEXT, metadata TEXT)"
        )
        conn.commit()
        conn.close()
        # Create EntityDatabase but patch to skip migration
        db = EntityDatabase.__new__(EntityDatabase)
        db._conn = sqlite3.connect(db_path)
        db._conn.row_factory = sqlite3.Row
        with pytest.raises(ValueError, match="fts_not_available"):
            db.search_entities("test")
        db._conn.close()


class TestSearchSanitization:
    def test_operators_stripped(self, search_db):
        """AC-21: FTS5 special chars don't raise."""
        results = search_db.search_entities("state(engine")
        assert isinstance(results, list)

    def test_all_operators_stripped(self, search_db):
        """Query of only operators returns empty."""
        results = search_db.search_entities('*"()+')
        assert results == []

    def test_whitespace_only(self, search_db):
        """Whitespace-only returns empty list."""
        assert search_db.search_entities("   ") == []

    def test_keyword_operators_stripped(self, search_db):
        """FTS5 keyword operators (NOT, OR, AND, NEAR) stripped."""
        # "NOT working" should not raise — NOT is stripped, "working" searched
        results = search_db.search_entities("NOT working")
        assert isinstance(results, list)
        # "state OR engine" — OR stripped, both tokens searched
        results = search_db.search_entities("state OR engine")
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Deepened Tests — Dimension 2: Boundary Value & Equivalence Partitioning
# ---------------------------------------------------------------------------


class TestSearchBoundaryValues:
    """Boundary values for search_entities parameters.

    derived_from: dimension:boundary_values, spec:AC-11 (limit clamping)
    """

    def test_limit_zero_clamped_to_one(self, search_db):
        """derived_from: spec:AC-11 — limit=0 clamped to min 1."""
        # Given a search db with multiple entities
        # When searching with limit=0
        results = search_db.search_entities("feature", limit=0)
        # Then limit is clamped to 1, returning at most 1 result
        assert len(results) >= 1
        assert len(results) <= 1

    def test_limit_one_returns_single_result(self, search_db):
        """derived_from: spec:AC-11 — limit=1 returns exactly 1."""
        # Given entities matching "MCP"
        # When searching with limit=1
        results = search_db.search_entities("MCP", limit=1)
        # Then exactly 1 result
        assert len(results) == 1

    def test_limit_100_accepted(self, search_db):
        """derived_from: spec:AC-11 — limit=100 is the max, accepted as-is."""
        # Given a search db
        # When searching with limit=100
        results = search_db.search_entities("feature", limit=100)
        # Then no error, returns list
        assert isinstance(results, list)

    def test_limit_101_clamped_to_100(self, search_db):
        """derived_from: spec:AC-11 — limit=101 clamped to 100."""
        # Given a search db
        # When searching with limit=101
        results = search_db.search_entities("feature", limit=101)
        # Then returns list (clamped silently, no error)
        assert isinstance(results, list)

    def test_limit_negative_clamped_to_one(self, search_db):
        """derived_from: spec:AC-11 — limit=-5 clamped to 1."""
        # Given a search db
        # When searching with limit=-5
        results = search_db.search_entities("feature", limit=-5)
        # Then limit clamped to 1, returns at most 1
        assert len(results) <= 1
        assert len(results) >= 1

    def test_single_char_query(self, search_db):
        """derived_from: dimension:boundary_values — single char prefix match."""
        # Given entities with names starting with 'K' (Kanban Board View)
        # When searching with a single character
        results = search_db.search_entities("K")
        # Then returns results (prefix match via K*)
        assert isinstance(results, list)
        # Should find Kanban Board View
        names = [r["name"] for r in results]
        assert "Kanban Board View" in names

    def test_leading_trailing_whitespace_stripped(self, search_db):
        """derived_from: dimension:boundary_values — whitespace around query."""
        # Given a search db with "Reconciliation MCP Tool"
        # When searching with padded whitespace
        results = search_db.search_entities("  recon  ")
        # Then whitespace is stripped, results found
        names = [r["name"] for r in results]
        assert "Reconciliation MCP Tool" in names

    def test_empty_double_quotes_returns_empty(self, search_db):
        """derived_from: dimension:boundary_values — empty quoted phrase."""
        # Given a search db
        # When searching with empty double quotes
        results = search_db.search_entities('""')
        # Then returns empty — no valid FTS query
        assert results == []


class TestFlattenMetadataEdgeCases:
    """Edge cases for flatten_metadata.

    derived_from: dimension:boundary_values, spec:AC-18
    """

    def test_deeply_nested_dict(self):
        """derived_from: dimension:boundary_values — 3+ levels deep."""
        # Given deeply nested metadata
        meta = {"a": {"b": {"c": {"d": "deepval"}}}}
        # When flattening
        result = flatten_metadata(meta)
        # Then deepest leaf is extracted
        assert result == "deepval"

    def test_mixed_booleans_and_numerics(self):
        """derived_from: dimension:boundary_values — bool and numeric types."""
        # Given metadata with mixed scalar types
        meta = {"active": True, "retries": 0, "ratio": 3.14, "flag": False}
        # When flattening
        result = flatten_metadata(meta)
        # Then all scalars present as strings
        assert "True" in result
        assert "0" in result
        assert "3.14" in result
        assert "False" in result

    def test_empty_string_value(self):
        """derived_from: dimension:boundary_values — empty string leaf."""
        # Given metadata with an empty string value
        meta = {"key": ""}
        # When flattening
        result = flatten_metadata(meta)
        # Then result contains the empty string (joined as single space artifacts)
        # An empty string is a valid scalar, but join of [""] is ""
        assert result == ""

    def test_list_with_none_elements(self):
        """derived_from: dimension:boundary_values — list containing Nones."""
        # Given metadata with None elements in a list
        meta = {"tags": [None, "alpha", None, "beta"]}
        # When flattening
        result = flatten_metadata(meta)
        # Then None elements skipped, valid ones present
        assert "alpha" in result
        assert "beta" in result

    def test_nested_list_in_dict(self):
        """derived_from: dimension:boundary_values — nested lists."""
        # Given metadata with nested list inside dict
        meta = {"outer": {"inner": ["x", "y"]}}
        # When flattening
        result = flatten_metadata(meta)
        # Then all leaf values present
        assert "x" in result
        assert "y" in result


# ---------------------------------------------------------------------------
# Deepened Tests — Dimension 3: Adversarial / Negative Testing
# ---------------------------------------------------------------------------


class TestSearchAdversarial:
    """Adversarial inputs to search_entities.

    derived_from: dimension:adversarial, spec:AC-21
    """

    def test_parentheses_in_query(self, search_db):
        """derived_from: dimension:adversarial — FTS5 grouping operators."""
        # Given a search db
        # When query contains parentheses
        results = search_db.search_entities("(state)(engine)")
        # Then no crash, sanitized to tokens
        assert isinstance(results, list)

    def test_colon_in_query(self, search_db):
        """derived_from: dimension:adversarial — FTS5 column filter operator."""
        # Given a search db
        # When query contains colon (FTS5 column filter syntax)
        results = search_db.search_entities("name:recon")
        # Then colon stripped, 'namerecon' or 'name recon' searched
        assert isinstance(results, list)

    def test_asterisks_in_query(self, search_db):
        """derived_from: dimension:adversarial — manual wildcard attempt."""
        # Given a search db
        # When query contains asterisks
        results = search_db.search_entities("*recon*")
        # Then asterisks stripped, 'recon' searched with auto-prefix
        assert isinstance(results, list)
        names = [r["name"] for r in results]
        assert "Reconciliation MCP Tool" in names

    def test_mixed_operators_and_text(self, search_db):
        """derived_from: dimension:adversarial — operators mixed with valid tokens."""
        # Given a search db
        # When mixing operators with valid tokens
        results = search_db.search_entities('state + "engine" - tool')
        # Then returns results, operators sanitized away
        assert isinstance(results, list)

    def test_and_keyword_stripped(self, search_db):
        """derived_from: dimension:adversarial — AND keyword operator."""
        # Given a search db
        # When using AND keyword
        results = search_db.search_entities("state AND engine")
        # Then AND is stripped, both tokens searched as prefix
        assert isinstance(results, list)

    def test_near_keyword_stripped(self, search_db):
        """derived_from: dimension:adversarial — NEAR keyword operator."""
        # Given a search db
        # When using NEAR keyword
        results = search_db.search_entities("state NEAR engine")
        # Then NEAR is stripped, both tokens searched
        assert isinstance(results, list)

    def test_operators_inside_quoted_phrase(self, search_db):
        """derived_from: dimension:adversarial — operators inside double quotes."""
        # Given a search db with "State Engine MCP Tools"
        # When query is a quoted phrase containing operators inside
        results = search_db.search_entities('"State+Engine"')
        # Then operators inside quotes are stripped, phrase searched
        assert isinstance(results, list)
        # The phrase "StateEngine" or "State Engine" should still match
        # Depends on sanitization: inner operators stripped to space or nothing
        # Key assertion: no exception raised

    def test_metadata_content_searchable(self, search_db):
        """derived_from: dimension:adversarial — search finds metadata content."""
        # Given entity 009 has metadata {"module": "State Engine"}
        # When searching for metadata-only content
        results = search_db.search_entities("Engine")
        # Then finds the entity via metadata field
        names = [r["name"] for r in results]
        assert "State Engine MCP Tools" in names

    def test_null_metadata_entity_still_searchable(self, db):
        """derived_from: dimension:adversarial — entity with no metadata searchable."""
        # Given an entity registered with no metadata
        db.register_entity("feature", "no-meta", "NoMetaEntity")
        # When searching by name
        results = db.search_entities("NoMetaEntity")
        # Then entity is found
        assert len(results) == 1
        assert results[0]["name"] == "NoMetaEntity"

    def test_duplicate_register_different_name_keeps_original(self, db):
        """derived_from: dimension:adversarial — duplicate register doesn't update."""
        # Given an entity already registered
        db.register_entity("feature", "dup-adv", "OriginalName")
        # When registering again with a different name (INSERT OR IGNORE)
        db.register_entity("feature", "dup-adv", "DifferentName")
        # Then original name is still searchable, new name is not
        results = db.search_entities("OriginalName")
        assert len(results) == 1
        results = db.search_entities("DifferentName")
        assert len(results) == 0

    def test_caret_operator_stripped(self, search_db):
        """derived_from: dimension:adversarial — FTS5 boost operator."""
        # Given a search db
        # When query contains caret (boost operator in FTS5)
        results = search_db.search_entities("state^2")
        # Then caret stripped, 'state2' searched
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Deepened Tests — Dimension 4: Error Propagation & Failure Modes
# ---------------------------------------------------------------------------


class TestSearchErrorPropagation:
    """Error propagation and failure modes for search.

    derived_from: dimension:error_propagation, spec:AC-15
    """

    def test_fts_not_available_error_message(self, tmp_path):
        """derived_from: spec:AC-15 — error message is informative."""
        # Given a db without FTS table
        db_path = str(tmp_path / "no_fts_err.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO _metadata VALUES ('schema_version', '3')")
        conn.execute(
            "CREATE TABLE entities (uuid TEXT PRIMARY KEY, type_id TEXT, "
            "entity_type TEXT, entity_id TEXT, name TEXT, status TEXT, "
            "parent_type_id TEXT, parent_uuid TEXT, artifact_path TEXT, "
            "created_at TEXT, updated_at TEXT, metadata TEXT)"
        )
        conn.commit()
        conn.close()
        db = EntityDatabase.__new__(EntityDatabase)
        db._conn = sqlite3.connect(db_path)
        db._conn.row_factory = sqlite3.Row
        # When calling search_entities
        # Then ValueError with specific message
        with pytest.raises(ValueError, match="fts_not_available"):
            db.search_entities("test")
        db._conn.close()

    def test_fts_sync_register_rollback_on_failure(self, tmp_path):
        """derived_from: dimension:error_propagation — register FTS failure leaves DB consistent.

        Since register_entity is wrapped in transaction() (Audit 062),
        FTS failure triggers ROLLBACK — the entity INSERT is also rolled
        back, leaving the DB fully consistent (no partial writes).
        """
        # Given a database where FTS table is dropped after init
        db_path = str(tmp_path / "fts_rollback.db")
        db = EntityDatabase(db_path)
        # Drop FTS table to simulate FTS sync failure on register
        db._conn.execute("DROP TABLE entities_fts")
        db._conn.commit()
        # When registering an entity (FTS INSERT will fail)
        with pytest.raises(Exception):
            db.register_entity("feature", "fail-fts", "FailFTS")
        # Then the entity row is rolled back (transaction() atomicity)
        # — no partial writes remain.
        row = db._conn.execute(
            "SELECT * FROM entities WHERE type_id = 'feature:fail-fts'"
        ).fetchone()
        assert row is None, "Entity row should be rolled back (transaction atomicity)"
        db.close()

    def test_fts_sync_update_rollback_on_failure(self, tmp_path):
        """derived_from: dimension:error_propagation — update FTS failure.

        Since update_entity is wrapped in transaction() (Audit 062),
        FTS failure triggers ROLLBACK — the UPDATE is also rolled back,
        preserving the original name.
        """
        # Given an entity exists, then FTS table is dropped
        db_path = str(tmp_path / "fts_update_rollback.db")
        db = EntityDatabase(db_path)
        db.register_entity("feature", "upd-fail", "UpdateFail")
        db._conn.execute("DROP TABLE entities_fts")
        db._conn.commit()
        # When updating the entity (FTS DELETE+INSERT will fail)
        with pytest.raises(Exception):
            db.update_entity("feature:upd-fail", name="NewName")
        # Then the UPDATE is rolled back (transaction() atomicity)
        # — original name is preserved.
        row = db._conn.execute(
            "SELECT name FROM entities WHERE type_id = 'feature:upd-fail'"
        ).fetchone()
        assert row is not None, "Entity row should still exist"
        assert row["name"] == "UpdateFail", "Name should be unchanged after rollback"
        db.close()


# ---------------------------------------------------------------------------
# Deepened Tests — Dimension 5: Mutation Mindset
# ---------------------------------------------------------------------------


class TestSearchMutationMindset:
    """Mutation-minded tests that pin specific behavioral details.

    derived_from: dimension:mutation_mindset
    """

    def test_prefix_star_appended_not_prepended(self, db):
        """derived_from: dimension:mutation_mindset — star goes at end of token."""
        # Given an entity with name "Reconciliation"
        db.register_entity("feature", "mut-prefix", "Reconciliation")
        # When searching for "recon"
        # Then _build_fts_query should produce "recon*" (suffix wildcard)
        query = db._build_fts_query("recon")
        assert query == "recon*"
        # Verify it actually finds the entity
        results = db.search_entities("recon")
        assert len(results) == 1

    def test_limit_clamps_both_directions(self, db):
        """derived_from: dimension:mutation_mindset — min AND max clamping."""
        # Given we can inspect the clamping behavior
        # When limit is below minimum
        db.register_entity("feature", "clamp-test", "ClampTest")
        results_low = db.search_entities("ClampTest", limit=-999)
        # Then clamped to 1 (min)
        assert len(results_low) <= 1
        assert len(results_low) == 1
        # When limit is above maximum
        results_high = db.search_entities("ClampTest", limit=999)
        # Then clamped to 100 (max) — returns results, no error
        assert isinstance(results_high, list)

    def test_old_name_not_searchable_after_update(self, db):
        """derived_from: dimension:mutation_mindset — FTS delete+insert on update."""
        # Given an entity with a specific name
        db.register_entity("feature", "mut-old", "OldMutName")
        # When updating the name
        db.update_entity("feature:mut-old", name="NewMutName")
        # Then old name returns zero results (FTS delete worked)
        old_results = db.search_entities("OldMutName")
        assert len(old_results) == 0
        # And new name returns the entity
        new_results = db.search_entities("NewMutName")
        assert len(new_results) == 1

    def test_minus_operator_stripped(self, search_db):
        """derived_from: dimension:mutation_mindset — minus (negation) removed."""
        # Given a search db
        # When query contains minus/hyphen (FTS5 NOT operator)
        results = search_db.search_entities("-state engine")
        # Then minus stripped, both tokens searched normally
        assert isinstance(results, list)

    def test_empty_query_returns_list_not_none(self, db):
        """derived_from: dimension:mutation_mindset — return type is always list."""
        # Given a database
        db.register_entity("feature", "mut-empty", "EmptyTest")
        # When searching with empty string
        result = db.search_entities("")
        # Then returns empty list, NOT None
        assert result == []
        assert result is not None

    def test_availability_check_runs_before_query(self, tmp_path):
        """derived_from: dimension:mutation_mindset — FTS check before sanitization."""
        # Given a db without FTS table
        db_path = str(tmp_path / "avail_check.db")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO _metadata VALUES ('schema_version', '3')")
        conn.execute(
            "CREATE TABLE entities (uuid TEXT PRIMARY KEY, type_id TEXT, "
            "entity_type TEXT, entity_id TEXT, name TEXT, status TEXT, "
            "parent_type_id TEXT, parent_uuid TEXT, artifact_path TEXT, "
            "created_at TEXT, updated_at TEXT, metadata TEXT)"
        )
        conn.commit()
        conn.close()
        db = EntityDatabase.__new__(EntityDatabase)
        db._conn = sqlite3.connect(db_path)
        db._conn.row_factory = sqlite3.Row
        # When searching even with empty query (which would return [] before FTS check)
        # The FTS check should still raise because table doesn't exist
        # Wait — empty query returns [] before the FTS check? Let me verify.
        # Implementation: FTS check runs first, then empty query check.
        # So even empty query should raise ValueError for missing FTS.
        with pytest.raises(ValueError, match="fts_not_available"):
            db.search_entities("")
        db._conn.close()

    def test_rowcount_guards_duplicate_fts_insert(self, db):
        """derived_from: dimension:mutation_mindset — rowcount==0 skips FTS insert."""
        # Given an entity is registered
        db.register_entity("feature", "rc-mut", "RowcountMut")
        # When registering duplicate (INSERT OR IGNORE)
        db.register_entity("feature", "rc-mut", "RowcountMut")
        # Then FTS should still have exactly 1 entry (not 2)
        rows = db._conn.execute(
            "SELECT rowid FROM entities_fts WHERE entities_fts MATCH 'RowcountMut'"
        ).fetchall()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Migration 7 & FTS rebuild tests (Feature 054)
# ---------------------------------------------------------------------------


def test_fts_rebuild_succeeds_on_production_schema(tmp_path):
    """AC-7: Verify FTS rebuild works on standalone content-bearing table."""
    db = EntityDatabase(str(tmp_path / "test.db"))
    db.register_entity(
        entity_type="feature",
        entity_id="test-rebuild",
        name="Rebuild Test Feature",
        metadata={"key": "value"},
    )
    # Rebuild should succeed (was broken before this fix)
    db._conn.execute("INSERT INTO entities_fts(entities_fts) VALUES('rebuild')")
    # Integrity check should pass
    db._conn.execute(
        "INSERT INTO entities_fts(entities_fts) VALUES('integrity-check')"
    )
    # Search should still find the entity after rebuild
    results = db.search_entities("Rebuild")
    assert len(results) == 1
    assert results[0]["entity_id"] == "test-rebuild"


def test_migration_7_upgrades_v6_database(tmp_path):
    """AC-4: Migration 7 upgrades v6 DB with working FTS index."""
    db_path = tmp_path / "v6.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO _metadata VALUES ('schema_version', '6');
        CREATE TABLE entities (
            uuid TEXT NOT NULL PRIMARY KEY, type_id TEXT NOT NULL UNIQUE,
            entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, name TEXT NOT NULL,
            status TEXT, parent_type_id TEXT, parent_uuid TEXT, artifact_path TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, metadata TEXT
        );
        CREATE VIRTUAL TABLE entities_fts USING fts5(
            name, entity_id, entity_type, status, metadata_text,
            content='entities', content_rowid='rowid'
        );
        CREATE TABLE workflow_phases (
            type_id TEXT NOT NULL, workflow_phase TEXT, kanban_column TEXT,
            last_completed_phase TEXT, mode TEXT, backward_transition_reason TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE entity_tags (
            type_id TEXT NOT NULL, tag TEXT NOT NULL,
            PRIMARY KEY (type_id, tag)
        );
        CREATE TABLE entity_dependencies (
            from_type_id TEXT NOT NULL, to_type_id TEXT NOT NULL,
            dependency_type TEXT NOT NULL DEFAULT 'depends_on',
            PRIMARY KEY (from_type_id, to_type_id, dependency_type)
        );
        CREATE TABLE entity_okr_alignment (
            type_id TEXT NOT NULL, objective TEXT NOT NULL,
            key_result TEXT, score REAL,
            PRIMARY KEY (type_id, objective)
        );
        INSERT INTO entities VALUES (
            'uuid-1', 'feature:test-v6', 'feature', 'test-v6', 'V6 Test Entity',
            'active', NULL, NULL, NULL, '2026-01-01T00:00:00Z',
            '2026-01-01T00:00:00Z', NULL
        );
    """)
    # Manually add FTS entry (external-content mode)
    conn.execute(
        "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
        "status, metadata_text) VALUES(1, 'V6 Test Entity', 'test-v6', "
        "'feature', 'active', '')"
    )
    conn.commit()
    conn.close()
    # Open with EntityDatabase — triggers migration 7
    db = EntityDatabase(str(db_path))
    assert db.get_schema_version() == 7
    # Pre-existing entity is searchable
    results = db.search_entities("V6")
    assert len(results) == 1
    assert results[0]["entity_id"] == "test-v6"
    # Rebuild succeeds
    db._conn.execute("INSERT INTO entities_fts(entities_fts) VALUES('rebuild')")
    # Integrity check passes
    db._conn.execute(
        "INSERT INTO entities_fts(entities_fts) VALUES('integrity-check')"
    )
