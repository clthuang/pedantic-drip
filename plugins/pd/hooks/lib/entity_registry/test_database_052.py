"""Tests for Feature 052 EntityDatabase extensions.

Tasks 1b.3a (get_entity_by_uuid, resolve_ref),
      1b.3b (search_by_type_id_prefix, begin_immediate),
      1b.9a (add_tag, get_tags, query_by_tag, MCP tools).
"""
from __future__ import annotations

import json
import os
import sys
import uuid

import pytest

from entity_registry.database import EntityDatabase

# Make entity_server importable.
_mcp_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp"))
if _mcp_dir not in sys.path:
    sys.path.insert(0, _mcp_dir)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Provide an in-memory EntityDatabase, closed after test."""
    database = EntityDatabase(":memory:")
    yield database
    database.close()


@pytest.fixture
def populated_db(db):
    """DB with 3 entities pre-registered for ref resolution and tagging tests."""
    db.register_entity("feature", "050-alpha", "Alpha Feature")
    db.register_entity("feature", "051-beta", "Beta Feature")
    db.register_entity("feature", "052-gamma", "Gamma Feature")
    return db


# ---------------------------------------------------------------------------
# Task 1b.3a: get_entity_by_uuid
# ---------------------------------------------------------------------------


class TestGetEntityByUuid:
    def test_returns_entity_dict_for_valid_uuid(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test Feature")
        result = db.get_entity_by_uuid(entity_uuid)
        assert result is not None
        assert result["uuid"] == entity_uuid
        assert result["type_id"] == "feature:001-test"
        assert result["name"] == "Test Feature"

    def test_returns_none_for_nonexistent_uuid(self, db):
        fake_uuid = str(uuid.uuid4())
        result = db.get_entity_by_uuid(fake_uuid)
        assert result is None

    def test_returns_none_for_invalid_string(self, db):
        result = db.get_entity_by_uuid("not-a-uuid")
        assert result is None

    def test_returns_full_entity_dict(self, db):
        entity_uuid = db.register_entity(
            "feature", "002-full", "Full Feature",
            status="active", artifact_path="/some/path",
            metadata={"key": "value"},
        )
        result = db.get_entity_by_uuid(entity_uuid)
        assert result["status"] == "active"
        assert result["artifact_path"] == "/some/path"
        assert result["entity_type"] == "feature"


# ---------------------------------------------------------------------------
# Task 1b.3a: resolve_ref
# ---------------------------------------------------------------------------


class TestResolveRef:
    def test_resolve_by_uuid(self, populated_db):
        """UUID input resolves directly."""
        entity = populated_db.get_entity("feature:050-alpha")
        entity_uuid = entity["uuid"]
        resolved = populated_db.resolve_ref(entity_uuid)
        assert resolved == entity_uuid

    def test_resolve_by_full_type_id(self, populated_db):
        """Full type_id resolves to uuid."""
        entity = populated_db.get_entity("feature:051-beta")
        resolved = populated_db.resolve_ref("feature:051-beta")
        assert resolved == entity["uuid"]

    def test_resolve_by_unique_prefix(self, populated_db):
        """Unique prefix match resolves to single uuid."""
        entity = populated_db.get_entity("feature:050-alpha")
        resolved = populated_db.resolve_ref("feature:050")
        assert resolved == entity["uuid"]

    def test_resolve_ambiguous_prefix_raises_valueerror(self, populated_db):
        """Ambiguous prefix (matches 050, 051, 052) raises ValueError with candidates."""
        with pytest.raises(ValueError, match="Multiple entities match"):
            populated_db.resolve_ref("feature:05")

    def test_resolve_ambiguous_lists_candidates(self, populated_db):
        """Error message includes matching type_ids."""
        with pytest.raises(ValueError) as exc_info:
            populated_db.resolve_ref("feature:05")
        msg = str(exc_info.value)
        assert "feature:050-alpha" in msg
        assert "feature:051-beta" in msg
        assert "feature:052-gamma" in msg

    def test_resolve_not_found_raises_valueerror(self, populated_db):
        """Non-matching ref raises ValueError."""
        with pytest.raises(ValueError, match="No entity found"):
            populated_db.resolve_ref("feature:999")

    def test_resolve_not_found_for_nonexistent_uuid(self, db):
        """Non-existent UUID raises ValueError."""
        fake_uuid = str(uuid.uuid4())
        with pytest.raises(ValueError, match="No entity found"):
            db.resolve_ref(fake_uuid)

    def test_resolve_not_found_for_garbage(self, db):
        """Totally invalid ref raises ValueError."""
        with pytest.raises(ValueError, match="No entity found"):
            db.resolve_ref("nonsense")


# ---------------------------------------------------------------------------
# Task 1b.3b: search_by_type_id_prefix
# ---------------------------------------------------------------------------


class TestSearchByTypeIdPrefix:
    def test_returns_matching_entities(self, populated_db):
        results = populated_db.search_by_type_id_prefix("feature:05")
        assert len(results) == 3
        type_ids = {r["type_id"] for r in results}
        assert type_ids == {
            "feature:050-alpha",
            "feature:051-beta",
            "feature:052-gamma",
        }

    def test_returns_single_match(self, populated_db):
        results = populated_db.search_by_type_id_prefix("feature:050")
        assert len(results) == 1
        assert results[0]["type_id"] == "feature:050-alpha"

    def test_returns_empty_for_no_match(self, populated_db):
        results = populated_db.search_by_type_id_prefix("feature:999")
        assert results == []

    def test_returns_full_entity_dicts(self, populated_db):
        results = populated_db.search_by_type_id_prefix("feature:052")
        assert len(results) == 1
        r = results[0]
        assert "uuid" in r
        assert "type_id" in r
        assert "name" in r
        assert r["name"] == "Gamma Feature"

    def test_prefix_across_types(self, db):
        db.register_entity("feature", "001-x", "Feature X")
        db.register_entity("project", "001-y", "Project Y")
        results = db.search_by_type_id_prefix("feature:001")
        assert len(results) == 1
        assert results[0]["type_id"] == "feature:001-x"

    def test_exact_type_id_match(self, populated_db):
        results = populated_db.search_by_type_id_prefix("feature:050-alpha")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Task 1b.3b: begin_immediate
# ---------------------------------------------------------------------------


class TestBeginImmediate:
    def test_commits_on_success(self, db):
        """Context manager commits when block completes without exception."""
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        with db.begin_immediate():
            db._conn.execute(
                "UPDATE entities SET name = ? WHERE uuid = ?",
                ("Updated", entity_uuid),
            )
        # Verify commit persisted
        row = db._conn.execute(
            "SELECT name FROM entities WHERE uuid = ?", (entity_uuid,)
        ).fetchone()
        assert row["name"] == "Updated"

    def test_rolls_back_on_exception(self, db):
        """Context manager rolls back when block raises."""
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        with pytest.raises(RuntimeError):
            with db.begin_immediate():
                db._conn.execute(
                    "UPDATE entities SET name = ? WHERE uuid = ?",
                    ("Should rollback", entity_uuid),
                )
                raise RuntimeError("boom")
        # Verify rollback
        row = db._conn.execute(
            "SELECT name FROM entities WHERE uuid = ?", (entity_uuid,)
        ).fetchone()
        assert row["name"] == "Test"

    def test_returns_connection(self, db):
        """Context manager yields the connection for direct SQL."""
        with db.begin_immediate() as conn:
            assert conn is not None
            result = conn.execute("SELECT 1").fetchone()
            assert result[0] == 1


# ---------------------------------------------------------------------------
# Task 1b.9a: Entity Tagging CRUD
# ---------------------------------------------------------------------------


class TestAddTag:
    def test_add_single_tag(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        db.add_tag(entity_uuid, "security")
        tags = db.get_tags(entity_uuid)
        assert tags == ["security"]

    def test_add_multiple_tags(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        db.add_tag(entity_uuid, "security")
        db.add_tag(entity_uuid, "platform")
        tags = db.get_tags(entity_uuid)
        assert sorted(tags) == ["platform", "security"]

    def test_duplicate_tag_is_idempotent(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        db.add_tag(entity_uuid, "security")
        db.add_tag(entity_uuid, "security")  # should not raise
        tags = db.get_tags(entity_uuid)
        assert tags == ["security"]

    def test_invalid_tag_uppercase_raises(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        with pytest.raises(ValueError, match="[Ii]nvalid tag"):
            db.add_tag(entity_uuid, "Security")

    def test_invalid_tag_spaces_raises(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        with pytest.raises(ValueError, match="[Ii]nvalid tag"):
            db.add_tag(entity_uuid, "my tag")

    def test_invalid_tag_too_long_raises(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        long_tag = "a" * 51
        with pytest.raises(ValueError, match="[Ii]nvalid tag"):
            db.add_tag(entity_uuid, long_tag)

    def test_invalid_tag_empty_raises(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        with pytest.raises(ValueError, match="[Ii]nvalid tag"):
            db.add_tag(entity_uuid, "")

    def test_valid_tag_with_hyphens(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        db.add_tag(entity_uuid, "my-security-tag")
        assert db.get_tags(entity_uuid) == ["my-security-tag"]

    def test_valid_tag_with_numbers(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        db.add_tag(entity_uuid, "phase-2")
        assert db.get_tags(entity_uuid) == ["phase-2"]

    def test_valid_tag_max_length(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        tag_50 = "a" * 50
        db.add_tag(entity_uuid, tag_50)
        assert db.get_tags(entity_uuid) == [tag_50]


class TestGetTags:
    def test_empty_tags(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        assert db.get_tags(entity_uuid) == []

    def test_tags_sorted_alphabetically(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        db.add_tag(entity_uuid, "zebra")
        db.add_tag(entity_uuid, "alpha")
        db.add_tag(entity_uuid, "middle")
        assert db.get_tags(entity_uuid) == ["alpha", "middle", "zebra"]


class TestQueryByTag:
    def test_query_returns_tagged_entities(self, populated_db):
        """Tag 3 entities with 'security' -> query returns all 3."""
        e1 = populated_db.get_entity("feature:050-alpha")
        e2 = populated_db.get_entity("feature:051-beta")
        e3 = populated_db.get_entity("feature:052-gamma")

        populated_db.add_tag(e1["uuid"], "security")
        populated_db.add_tag(e2["uuid"], "security")
        populated_db.add_tag(e3["uuid"], "security")

        results = populated_db.query_by_tag("security")
        assert len(results) == 3
        result_uuids = {r["uuid"] for r in results}
        assert result_uuids == {e1["uuid"], e2["uuid"], e3["uuid"]}

    def test_query_returns_only_matching(self, populated_db):
        """Only entities with the specific tag are returned."""
        e1 = populated_db.get_entity("feature:050-alpha")
        e2 = populated_db.get_entity("feature:051-beta")

        populated_db.add_tag(e1["uuid"], "security")
        populated_db.add_tag(e2["uuid"], "platform")

        results = populated_db.query_by_tag("security")
        assert len(results) == 1
        assert results[0]["uuid"] == e1["uuid"]

    def test_query_returns_empty_for_unused_tag(self, populated_db):
        results = populated_db.query_by_tag("nonexistent")
        assert results == []

    def test_query_returns_full_entity_dicts(self, populated_db):
        e1 = populated_db.get_entity("feature:050-alpha")
        populated_db.add_tag(e1["uuid"], "security")
        results = populated_db.query_by_tag("security")
        assert len(results) == 1
        r = results[0]
        assert "uuid" in r
        assert "type_id" in r
        assert "name" in r
        assert r["name"] == "Alpha Feature"

    def test_query_across_entity_types(self, db):
        """Tags work across entity types (AC-36)."""
        u1 = db.register_entity("feature", "001-feat", "Feature One")
        u2 = db.register_entity("project", "001-proj", "Project One")
        u3 = db.register_entity("brainstorm", "001-brain", "Brainstorm One")

        db.add_tag(u1, "security")
        db.add_tag(u2, "security")
        db.add_tag(u3, "security")

        results = db.query_by_tag("security")
        assert len(results) == 3
        types = {r["entity_type"] for r in results}
        assert types == {"feature", "project", "brainstorm"}


class TestRemoveTag:
    def test_remove_existing_tag(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        db.add_tag(entity_uuid, "security")
        db.remove_tag(entity_uuid, "security")
        assert db.get_tags(entity_uuid) == []

    def test_remove_nonexistent_tag_is_silent(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        db.remove_tag(entity_uuid, "nonexistent")  # should not raise

    def test_remove_only_specified_tag(self, db):
        entity_uuid = db.register_entity("feature", "001-test", "Test")
        db.add_tag(entity_uuid, "security")
        db.add_tag(entity_uuid, "platform")
        db.remove_tag(entity_uuid, "security")
        assert db.get_tags(entity_uuid) == ["platform"]


# ---------------------------------------------------------------------------
# Task 1b.9a: MCP Tool Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_db(tmp_path, monkeypatch):
    """Provide EntityDatabase and inject into entity_server._db."""
    import entity_server
    database = EntityDatabase(str(tmp_path / "test.db"))
    monkeypatch.setattr(entity_server, "_db", database)
    yield database
    database.close()


class TestMcpAddEntityTag:
    @pytest.mark.asyncio
    async def test_add_tag_success(self, mcp_db):
        import entity_server
        mcp_db.register_entity("feature", "001-test", "Test Feature")
        result = await entity_server.add_entity_tag("feature:001-test", "security")
        parsed = json.loads(result)
        assert "result" in parsed
        assert "security" in parsed["result"]

    @pytest.mark.asyncio
    async def test_add_tag_invalid_format(self, mcp_db):
        import entity_server
        mcp_db.register_entity("feature", "001-test", "Test Feature")
        result = await entity_server.add_entity_tag("feature:001-test", "INVALID")
        parsed = json.loads(result)
        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_add_tag_entity_not_found(self, mcp_db):
        import entity_server
        result = await entity_server.add_entity_tag("feature:nonexistent", "security")
        assert "not found" in result.lower()


class TestMcpGetEntityTags:
    @pytest.mark.asyncio
    async def test_get_tags_success(self, mcp_db):
        import entity_server
        entity_uuid = mcp_db.register_entity("feature", "001-test", "Test")
        mcp_db.add_tag(entity_uuid, "security")
        mcp_db.add_tag(entity_uuid, "platform")
        result = await entity_server.get_entity_tags("feature:001-test")
        parsed = json.loads(result)
        assert parsed["type_id"] == "feature:001-test"
        assert sorted(parsed["tags"]) == ["platform", "security"]

    @pytest.mark.asyncio
    async def test_get_tags_entity_not_found(self, mcp_db):
        import entity_server
        result = await entity_server.get_entity_tags("feature:nonexistent")
        assert "not found" in result.lower()
