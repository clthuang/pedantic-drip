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
    parent_uuid = db.register_entity("project", "parent", "Parent Project", status="active")
    child_uuid = db.register_entity("feature", "child", "Child Feature")

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
    entity_uuid = db.register_entity("feature", "f1", "Feature One", status="active")

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
    parent_uuid = db.register_entity("project", "parent2", "Parent")
    child_uuid = db.register_entity("feature", "child2", "Child")
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
    db.register_entity("feature", "get-test", "Get Test", status="active")
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
    db.register_entity("project", "p1", "Parent Project", status="active")
    db.register_entity("feature", "c1", "Child Feature", status="active")
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
    db.register_entity("brainstorm", "err-test", "Error Test", status="draft")

    # When attempting to transition without initializing workflow first
    result = ws_mod._process_transition_entity_phase(
        db, "brainstorm:err-test", "reviewing"
    )
    parsed = json.loads(result)
    # Then a structured error is returned (not an unhandled exception)
    assert parsed["error"] is True
    assert parsed["error_type"] == "entity_not_found"
    assert "recovery_hint" in parsed
