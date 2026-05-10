"""Tests for entity_server MCP handler dual-identity messages."""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

# Make entity_server importable.
_mcp_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp"))
if _mcp_dir not in sys.path:
    sys.path.insert(0, _mcp_dir)

import entity_server
from entity_registry.database import EntityDatabase

_UUID_V4_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Provide EntityDatabase and inject into entity_server._db."""
    database = EntityDatabase(str(tmp_path / "test.db"))
    monkeypatch.setattr(entity_server, "_db", database)
    yield database
    database.close()


@pytest.mark.asyncio
async def test_set_parent_handler_concise_message(db):
    """set_parent handler returns concise message with only type_ids, no UUIDs.
    derived_from: feature:045-mcp-audit-token-efficiency P1-C3
    """
    parent_uuid = db.register_entity("project", "parent", "Parent Project", status="active", project_id="__unknown__")
    child_uuid = db.register_entity("feature", "child", "Child Feature", project_id="__unknown__")

    result = await entity_server.set_parent("feature:child", "project:parent")

    assert isinstance(result, str)
    assert result == "Parent set: feature:child \u2192 project:parent"
    # UUIDs must NOT appear in confirmation messages
    assert child_uuid not in result
    assert parent_uuid not in result


@pytest.mark.asyncio
async def test_update_entity_handler_concise_message(db):
    """update_entity handler returns concise message with only type_id, no UUID.
    derived_from: feature:045-mcp-audit-token-efficiency P1-C3
    """
    entity_uuid = db.register_entity("feature", "f1", "Feature One", status="active", project_id="__unknown__")

    result = await entity_server.update_entity("feature:f1", status="completed")

    assert isinstance(result, str)
    assert result == "Updated: feature:f1"
    # UUID must NOT appear in confirmation message
    assert entity_uuid not in result


# ---------------------------------------------------------------------------
# Deepened tests: Phase B — spec-driven test deepening
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_entity_handler_concise_message(db):
    """register_entity handler returns concise message with only type_id, no UUID.
    derived_from: feature:045-mcp-audit-token-efficiency P1-C3
    """
    result = await entity_server.register_entity(
        entity_type="feature",
        entity_id="reg-test",
        name="Registration Test",
        project_id="__unknown__",
    )
    assert isinstance(result, str)
    assert result == "Registered: feature:reg-test"
    # UUID must NOT appear in confirmation message
    assert not _UUID_V4_RE.search(result), f"UUID found in message: {result}"


@pytest.mark.asyncio
async def test_set_parent_handler_uses_uuid_identifiers(db):
    """set_parent handler can accept UUID identifiers (not just type_id).
    Anticipate: If handler passes raw input to set_parent without
    dual-read resolution, UUID input would fail.
    derived_from: spec:R27, dimension:adversarial
    """
    parent_uuid = db.register_entity("project", "parent2", "Parent", project_id="__unknown__")
    child_uuid = db.register_entity("feature", "child2", "Child", project_id="__unknown__")
    # Use UUID for child and type_id for parent
    result = await entity_server.set_parent(child_uuid, "project:parent2")
    assert isinstance(result, str)
    # Should not contain "Error"
    assert "Error" not in result
    # Concise message uses type_ids only
    assert "Parent set:" in result


@pytest.mark.asyncio
async def test_get_entity_handler_compact_output(db):
    """get_entity handler returns compact JSON without uuid, entity_id, parent_uuid.
    These internal fields are stripped for token efficiency — callers already
    know the type_id they queried with, and uuid/parent_uuid are internal.
    derived_from: feature:045-mcp-audit-token-efficiency P1-C2
    """
    db.register_entity("feature", "get-test", "Get Test", status="active", project_id="__unknown__")
    result = await entity_server.get_entity("feature:get-test")
    assert isinstance(result, str)
    parsed = json.loads(result)
    # Excluded fields
    assert "uuid" not in parsed
    assert "entity_id" not in parsed
    assert "parent_uuid" not in parsed
    # Retained fields
    assert parsed["type_id"] == "feature:get-test"
    assert parsed["name"] == "Get Test"
    assert parsed["status"] == "active"
    # Compact JSON: no indentation, minimal separators
    assert "\n" not in result
    assert ": " not in result  # compact separators use ':' not ': '


# ---------------------------------------------------------------------------
# Deepened tests Phase B: MCP Audit Token Efficiency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_entity_not_found_returns_message(db):
    """get_entity for a non-existent type_id returns a not-found message, not crash.
    derived_from: spec:AC-2 (error handling), dimension:error_propagation

    Anticipate: If get_entity doesn't handle None from db.get_entity(),
    it would crash with AttributeError when trying to pop keys from None.
    This test verifies graceful handling of the not-found path.
    """
    # Given a database with no matching entity
    # When requesting a non-existent entity
    result = await entity_server.get_entity("feature:does-not-exist")
    # Then a human-readable not-found message is returned
    assert isinstance(result, str)
    assert "not found" in result.lower() or "Entity not found" in result
    assert "does-not-exist" in result


@pytest.mark.asyncio
async def test_set_parent_delegates_to_server_helpers(db):
    """set_parent MCP handler delegates to _process_set_parent helper.
    derived_from: spec:AC-15 (delegation to helpers), dimension:bdd_scenarios

    Anticipate: If set_parent inlines the logic instead of delegating to
    _process_set_parent, future changes to the helper would not be picked up
    by the MCP tool. This test verifies the delegation chain works end-to-end.
    """
    # Given parent and child entities
    db.register_entity("project", "p1", "Parent Project", status="active", project_id="__unknown__")
    db.register_entity("feature", "c1", "Child Feature", status="active", project_id="__unknown__")
    # When setting parent via MCP handler
    result = await entity_server.set_parent("feature:c1", "project:p1")
    # Then success message is returned
    assert "Parent set:" in result
    assert "feature:c1" in result
    assert "project:p1" in result


@pytest.mark.asyncio
async def test_entity_lifecycle_valueerror_caught_by_mcp_decorator(db):
    """Entity lifecycle ValueError is caught and returned as structured error.
    derived_from: spec:AC-5 (error handling), dimension:error_propagation

    Anticipate: If the init_entity_workflow or transition_entity_phase MCP
    handlers don't have the _catch_entity_value_error decorator, ValueErrors
    would propagate as unhandled exceptions instead of structured error JSON.
    This test verifies the end-to-end error handling chain via the workflow
    state server processing function.
    """
    import workflow_state_server as ws_mod

    # Given a brainstorm entity but NO workflow_phases row
    db.register_entity("brainstorm", "err-test", "Error Test", status="draft", project_id="__unknown__")

    # When attempting to transition without initializing workflow first
    result = ws_mod._process_transition_entity_phase(
        db, "brainstorm:err-test", "reviewing"
    )
    parsed = json.loads(result)
    # Then a structured error is returned (not an unhandled exception)
    assert parsed["error"] is True
    assert parsed["error_type"] == "entity_not_found"
    assert "recovery_hint" in parsed


# ---------------------------------------------------------------------------
# Metadata dict coercion tests (feature 046)
# ---------------------------------------------------------------------------


class TestMetadataDictCoercion:
    """Tests for dict-to-JSON-string coercion in register_entity and update_entity."""

    def test_register_entity_metadata_dict(self, db: EntityDatabase):
        """AC-1: Dict metadata is accepted and stored as JSON string."""
        entity_server._db = db
        import asyncio
        result = asyncio.run(
            entity_server.register_entity(
                entity_type="feature", entity_id="meta-dict-001",
                name="Dict Test", metadata={"description": "test value"},
                project_id="__unknown__",
            )
        )
        assert "Registered:" in result
        entity = db.get_entity("feature:meta-dict-001")
        meta = json.loads(entity["metadata"]) if isinstance(entity["metadata"], str) else entity["metadata"]
        assert meta["description"] == "test value"

    def test_register_entity_metadata_string(self, db: EntityDatabase):
        """AC-3: String metadata passthrough unchanged."""
        entity_server._db = db
        import asyncio
        result = asyncio.run(
            entity_server.register_entity(
                entity_type="feature", entity_id="meta-str-001",
                name="String Test", metadata='{"key": "val"}',
                project_id="__unknown__",
            )
        )
        assert "Registered:" in result
        entity = db.get_entity("feature:meta-str-001")
        meta = json.loads(entity["metadata"]) if isinstance(entity["metadata"], str) else entity["metadata"]
        assert meta["key"] == "val"

    def test_register_entity_metadata_none(self, db: EntityDatabase):
        """AC-4: None metadata stores no metadata."""
        entity_server._db = db
        import asyncio
        result = asyncio.run(
            entity_server.register_entity(
                entity_type="feature", entity_id="meta-none-001",
                name="None Test", metadata=None,
                project_id="__unknown__",
            )
        )
        assert "Registered:" in result

    def test_update_entity_metadata_dict(self, db: EntityDatabase):
        """AC-2: Dict metadata accepted by update_entity, stored as JSON string."""
        db.register_entity("feature", "meta-upd-001", "Update Test", status="active", project_id="__unknown__")
        entity_server._db = db
        import asyncio
        result = asyncio.run(
            entity_server.update_entity(
                type_id="feature:meta-upd-001",
                metadata={"updated": True},
            )
        )
        assert "Updated:" in result
        entity = db.get_entity("feature:meta-upd-001")
        meta = json.loads(entity["metadata"]) if isinstance(entity["metadata"], str) else entity["metadata"]
        assert meta["updated"] is True

    def test_register_entity_metadata_invalid_json_string(self, db: EntityDatabase):
        """AC-7: Invalid JSON string handled gracefully by parse_metadata.
        derived_from: server_helpers:parse_metadata, dimension:delegation
        """
        entity_server._db = db
        import asyncio
        result = asyncio.run(
            entity_server.register_entity(
                entity_type="feature", entity_id="meta-bad-001",
                name="Bad JSON Test", metadata="{bad json}",
                project_id="__unknown__",
            )
        )
        # Should succeed (parse_metadata returns {"error": "..."} for invalid JSON)
        assert "Registered:" in result


# ---------------------------------------------------------------------------
# Phase 4: Cross-project entity scoping — startup and project tools
# ---------------------------------------------------------------------------


class TestProjectStartup:
    """T4.1: entity_server startup with project_id detection."""

    def test_project_id_set_after_detection(self, db, monkeypatch):
        """Monkeypatch detect_project_id and verify _project_id is set."""
        monkeypatch.setattr(entity_server, "_project_id", "")
        monkeypatch.setattr(
            "entity_server.detect_project_id", lambda _root: "abc123def456"
        )
        monkeypatch.setattr(
            "entity_server.collect_git_info",
            lambda _root: entity_server.GitProjectInfo(
                project_id="abc123def456",
                root_commit_sha="a" * 40,
                name="test-project",
                remote_url="",
                normalized_url="",
                remote_host="",
                remote_owner="",
                remote_repo="",
                default_branch="main",
                project_root="/tmp/test",
                is_git_repo=True,
            ),
        )
        # Simulate the startup sequence
        entity_server._project_id = entity_server.detect_project_id("/tmp/test")
        info = entity_server.collect_git_info("/tmp/test")
        entity_server._upsert_project(db, info)

        assert entity_server._project_id == "abc123def456"
        # Verify project was inserted
        row = db._conn.execute(
            "SELECT * FROM projects WHERE project_id = ?", ("abc123def456",)
        ).fetchone()
        assert row is not None
        assert row["name"] == "test-project"

    def test_backfill_claims_unknown_entities(self, db, monkeypatch):
        """Pre-populate __unknown__ entity with matching artifact_path, verify claimed."""
        project_root = "/tmp/my-project"
        project_id = "testproj1234"

        # Register an entity with __unknown__ project_id and matching artifact_path
        db.register_entity(
            "feature", "bf-test", "Backfill Test",
            artifact_path="/tmp/my-project/docs/features/test/design.md",
            project_id="__unknown__",
        )
        # Verify starts as __unknown__
        entity = db.get_entity("feature:bf-test")
        assert entity["project_id"] == "__unknown__"

        # Run backfill
        count = entity_server._backfill_project_ids(db, project_root, project_id)
        assert count == 1

        # Verify entity was claimed
        entity = db.get_entity("feature:bf-test")
        assert entity["project_id"] == project_id


class TestListProjects:
    """T4.5: list_projects MCP tool."""

    def test_list_projects_returns_inserted_project(self, db, monkeypatch):
        """Insert a project via _upsert_project, then list_projects returns it."""
        from entity_registry.project_identity import GitProjectInfo

        monkeypatch.setattr(entity_server, "_db", db)
        info = GitProjectInfo(
            project_id="proj12345678",
            root_commit_sha="b" * 40,
            name="list-test-project",
            remote_url="https://github.com/test/repo.git",
            normalized_url="github.com/test/repo",
            remote_host="github.com",
            remote_owner="test",
            remote_repo="repo",
            default_branch="main",
            project_root="/tmp/list-test",
            is_git_repo=True,
        )
        entity_server._upsert_project(db, info)

        import asyncio
        result = asyncio.run(entity_server.list_projects())
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) >= 1
        project_ids = [p["project_id"] for p in parsed]
        assert "proj12345678" in project_ids
        matched = [p for p in parsed if p["project_id"] == "proj12345678"][0]
        assert matched["name"] == "list-test-project"


class TestSearchProjectFiltering:
    """T4.3: search_entities project_id filtering."""

    @pytest.mark.asyncio
    async def test_search_filters_by_project(self, db, monkeypatch):
        """Search with project_id filters results to that project."""
        # Feature 108 Migration 11: project_id alias requires a matching
        # workspaces row. Pre-register both legacy ids.
        from entity_registry.test_helpers import bootstrap_test_workspace
        bootstrap_test_workspace(db, "project_aaa")
        bootstrap_test_workspace(db, "project_bbb")
        # Register entities under different projects
        db.register_entity(
            "feature", "proj-a-feat", "Project A Feature",
            status="active", project_id="project_aaa",
        )
        db.register_entity(
            "feature", "proj-b-feat", "Project B Feature",
            status="active", project_id="project_bbb",
        )

        monkeypatch.setattr(entity_server, "_project_id", "project_aaa")

        # Default search (scoped to project_aaa)
        result = await entity_server.search_entities(query="Feature")
        assert "proj-a-feat" in result
        assert "proj-b-feat" not in result

        # Wildcard search (all projects)
        result = await entity_server.search_entities(query="Feature", project_id="*")
        assert "proj-a-feat" in result
        assert "proj-b-feat" in result
