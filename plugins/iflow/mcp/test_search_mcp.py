"""Tests for search_entities MCP tool in entity_server."""
from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

# Make entity_registry importable from hooks/lib/.
_hooks_lib = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "hooks", "lib")
)
if _hooks_lib not in (os.path.normpath(p) for p in sys.path):
    sys.path.insert(0, _hooks_lib)

import entity_server  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_db(tmp_path):
    """Provide an EntityDatabase via the module global, cleaned up after test."""
    from entity_registry.database import EntityDatabase

    db_path = str(tmp_path / "mcp_search_test.db")
    db = EntityDatabase(db_path)
    entity_server._db = db
    yield db
    entity_server._db = None
    db.close()


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSearchMCPTool:
    def test_tool_registered(self):
        """AC-12: search_entities callable."""
        assert hasattr(entity_server, "search_entities")
        assert callable(entity_server.search_entities)

    def test_formatted_output(self, mcp_db):
        """AC-13: returns human-readable numbered list."""
        mcp_db.register_entity("feature", "recon", "Reconciliation Tool",
                               status="active")
        result = _run(entity_server.search_entities(query="recon"))
        assert "1." in result
        assert "Reconciliation Tool" in result
        assert "feature:recon" in result

    def test_no_results(self, mcp_db):
        """AC-14: returns 'No entities found' message."""
        result = _run(entity_server.search_entities(query="nonexistent"))
        assert "No entities found" in result

    def test_error_handling(self, mcp_db):
        """AC-15: query of only operators returns no-results, not exception."""
        result = _run(entity_server.search_entities(query='*"()+'))
        assert "No entities found" in result

    def test_db_not_initialized(self):
        """Returns error when _db is None."""
        entity_server._db = None
        result = _run(entity_server.search_entities(query="test"))
        assert "Error: database not initialized" in result


# ---------------------------------------------------------------------------
# Deepened Tests — Dimension 1: BDD Scenarios (MCP layer)
# ---------------------------------------------------------------------------


class TestSearchMCPFormatting:
    """BDD scenarios for MCP search_entities output formatting.

    derived_from: spec:AC-13, spec:AC-14
    """

    def test_result_count_in_header(self, mcp_db):
        """derived_from: spec:AC-13 — header shows match count."""
        # Given two registered entities
        mcp_db.register_entity("feature", "fmt-a", "AlphaFeature",
                               status="active")
        mcp_db.register_entity("feature", "fmt-b", "AlphaBravo",
                               status="planned")
        # When searching for "Alpha"
        result = _run(entity_server.search_entities(query="Alpha"))
        # Then header includes count
        assert "Found 2 entities" in result

    def test_result_includes_status(self, mcp_db):
        """derived_from: spec:AC-13 — each result shows status."""
        # Given an entity with status
        mcp_db.register_entity("feature", "fmt-status", "StatusEntity",
                               status="completed")
        # When searching
        result = _run(entity_server.search_entities(query="StatusEntity"))
        # Then status appears in output
        assert "completed" in result

    def test_result_includes_type_id(self, mcp_db):
        """derived_from: spec:AC-13 — each result shows type_id."""
        # Given an entity
        mcp_db.register_entity("brainstorm", "fmt-type", "TypeEntity")
        # When searching
        result = _run(entity_server.search_entities(query="TypeEntity"))
        # Then type_id present
        assert "brainstorm:fmt-type" in result

    def test_no_status_shows_fallback(self, mcp_db):
        """derived_from: spec:AC-13 — entity without status shows 'no status'."""
        # Given an entity without status
        mcp_db.register_entity("feature", "fmt-nostatus", "NoStatusEntity")
        # When searching
        result = _run(entity_server.search_entities(query="NoStatusEntity"))
        # Then shows 'no status' fallback
        assert "no status" in result

    def test_limit_shown_in_footer(self, mcp_db):
        """derived_from: spec:AC-13 — footer shows limit used."""
        # Given an entity
        mcp_db.register_entity("feature", "fmt-footer", "FooterEntity",
                               status="active")
        # When searching with specific limit
        result = _run(entity_server.search_entities(
            query="FooterEntity", limit=5))
        # Then footer shows limit
        assert "limit: 5" in result


# ---------------------------------------------------------------------------
# Deepened Tests — Dimension 3: Adversarial (MCP layer)
# ---------------------------------------------------------------------------


class TestSearchMCPAdversarial:
    """Adversarial inputs through the MCP tool layer.

    derived_from: dimension:adversarial, spec:AC-15
    """

    def test_mcp_catches_valueerror_from_search(self, mcp_db):
        """derived_from: dimension:error_propagation — MCP wraps ValueError."""
        # Given FTS table is dropped (simulates unavailability)
        mcp_db._conn.execute("DROP TABLE entities_fts")
        mcp_db._conn.commit()
        # When searching via MCP tool
        result = _run(entity_server.search_entities(query="test"))
        # Then error message returned, not exception
        assert "Search error" in result
        assert "fts_not_available" in result

    def test_mcp_empty_query_returns_no_results(self, mcp_db):
        """derived_from: dimension:adversarial — empty string via MCP."""
        # Given a db with entities
        mcp_db.register_entity("feature", "mcp-empty", "EmptyQueryTest")
        # When sending empty query via MCP
        result = _run(entity_server.search_entities(query=""))
        # Then returns no-results message
        assert "No entities found" in result

    def test_mcp_whitespace_query_returns_no_results(self, mcp_db):
        """derived_from: dimension:adversarial — whitespace via MCP."""
        # Given a db with entities
        mcp_db.register_entity("feature", "mcp-ws", "WhitespaceTest")
        # When sending whitespace query
        result = _run(entity_server.search_entities(query="   "))
        # Then returns no-results message
        assert "No entities found" in result

    def test_mcp_type_filter(self, mcp_db):
        """derived_from: spec:AC-8 — entity_type filter at MCP level."""
        # Given entities of different types
        mcp_db.register_entity("feature", "mcp-ft", "FilterTest",
                               status="active")
        mcp_db.register_entity("brainstorm", "mcp-ft2", "FilterTestBrain",
                               status="active")
        # When searching with type filter
        result = _run(entity_server.search_entities(
            query="FilterTest", entity_type="brainstorm"))
        # Then only brainstorm type appears
        assert "brainstorm:mcp-ft2" in result
        assert "feature:mcp-ft" not in result

    def test_mcp_operators_sanitized(self, mcp_db):
        """derived_from: spec:AC-21 — operators sanitized at MCP layer."""
        # Given a db with entities
        mcp_db.register_entity("feature", "mcp-ops", "OperatorTest",
                               status="active")
        # When sending query with FTS5 operators
        result = _run(entity_server.search_entities(query="Operator+Test*"))
        # Then no crash, results or no-results message
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Deepened Tests — Dimension 5: Mutation Mindset (MCP layer)
# ---------------------------------------------------------------------------


class TestSearchMCPMutationMindset:
    """Mutation-minded tests for MCP search tool.

    derived_from: dimension:mutation_mindset
    """

    def test_mcp_returns_string_not_list(self, mcp_db):
        """derived_from: dimension:mutation_mindset — MCP always returns str."""
        # Given a db
        mcp_db.register_entity("feature", "mcp-str", "StringReturn")
        # When searching via MCP
        result = _run(entity_server.search_entities(query="StringReturn"))
        # Then result is always a string (not raw list)
        assert isinstance(result, str)

    def test_mcp_db_none_returns_error_not_exception(self):
        """derived_from: dimension:mutation_mindset — None db handled gracefully."""
        # Given _db is None
        entity_server._db = None
        # When searching
        result = _run(entity_server.search_entities(query="anything"))
        # Then returns error string, not raises
        assert isinstance(result, str)
        assert "Error" in result

    def test_mcp_numbered_list_starts_at_one(self, mcp_db):
        """derived_from: dimension:mutation_mindset — numbering starts at 1 not 0."""
        # Given entities
        mcp_db.register_entity("feature", "mcp-num", "NumberedTest",
                               status="active")
        # When searching
        result = _run(entity_server.search_entities(query="NumberedTest"))
        # Then first result is numbered "1." not "0."
        assert "1." in result
        assert "0." not in result
