"""Tests for MCP ref parameter resolution (Task 1b.5).

Verifies that entity_server.py and workflow_state_server.py MCP tools
accept `ref` as an alternative to `type_id`, resolving via db.resolve_ref().
"""
from __future__ import annotations

import json
import os
import sys
import uuid

import pytest

from entity_registry.database import EntityDatabase

# Make MCP server modules importable.
_mcp_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp"))
if _mcp_dir not in sys.path:
    sys.path.insert(0, _mcp_dir)

# Import the ref resolution helpers from both servers.
from entity_server import _resolve_ref_param
from workflow_state_server import _resolve_ref_to_feature_type_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """In-memory EntityDatabase with 3 features."""
    database = EntityDatabase(":memory:")
    database.register_entity("feature", "050-alpha", "Alpha Feature")
    database.register_entity("feature", "051-beta", "Beta Feature")
    database.register_entity("feature", "052-reactive-entity", "Reactive Entity")
    yield database
    database.close()


# ---------------------------------------------------------------------------
# entity_server._resolve_ref_param
# ---------------------------------------------------------------------------


class TestEntityServerResolveRef:
    """Test _resolve_ref_param from entity_server.py."""

    def test_type_id_passthrough(self, db):
        """When type_id is provided and ref is None, return type_id as-is."""
        result = _resolve_ref_param(db, type_id="feature:050-alpha", ref=None)
        assert result == "feature:050-alpha"

    def test_ref_exact_type_id(self, db):
        """ref as exact type_id resolves to that type_id."""
        result = _resolve_ref_param(db, type_id=None, ref="feature:050-alpha")
        assert result == "feature:050-alpha"

    def test_ref_uuid(self, db):
        """ref as UUID resolves to the entity's type_id."""
        entity = db.get_entity("feature:050-alpha")
        result = _resolve_ref_param(db, type_id=None, ref=entity["uuid"])
        assert result == "feature:050-alpha"

    def test_ref_prefix_unique(self, db):
        """ref as unique prefix resolves to the entity's type_id."""
        result = _resolve_ref_param(db, type_id=None, ref="feature:052")
        assert result == "feature:052-reactive-entity"

    def test_ref_prefix_ambiguous_on_read(self, db):
        """ref as ambiguous prefix on read returns the first match's type_id
        or raises — behavior depends on is_mutation flag."""
        # Ambiguous prefix "feature:05" matches all 3
        with pytest.raises(ValueError, match="Multiple"):
            _resolve_ref_param(db, type_id=None, ref="feature:05", is_mutation=False)

    def test_ref_prefix_ambiguous_on_mutation_errors(self, db):
        """Ambiguous ref on mutation always errors."""
        with pytest.raises(ValueError, match="Multiple"):
            _resolve_ref_param(db, type_id=None, ref="feature:05", is_mutation=True)

    def test_ref_not_found(self, db):
        """ref that matches nothing raises ValueError."""
        with pytest.raises(ValueError, match="No entity found"):
            _resolve_ref_param(db, type_id=None, ref="feature:999")

    def test_neither_provided_errors(self, db):
        """Both type_id and ref are None -> error."""
        with pytest.raises(ValueError, match="type_id.*ref"):
            _resolve_ref_param(db, type_id=None, ref=None)

    def test_both_provided_type_id_wins(self, db):
        """When both type_id and ref provided, type_id takes precedence."""
        result = _resolve_ref_param(
            db, type_id="feature:050-alpha", ref="feature:051-beta"
        )
        assert result == "feature:050-alpha"


# ---------------------------------------------------------------------------
# workflow_state_server._resolve_ref_to_feature_type_id
# ---------------------------------------------------------------------------


class TestWorkflowServerResolveRef:
    """Test _resolve_ref_to_feature_type_id from workflow_state_server.py."""

    def test_feature_type_id_passthrough(self, db):
        result = _resolve_ref_to_feature_type_id(
            db, feature_type_id="feature:050-alpha", ref=None
        )
        assert result == "feature:050-alpha"

    def test_ref_resolves_to_feature_type_id(self, db):
        result = _resolve_ref_to_feature_type_id(
            db, feature_type_id=None, ref="feature:052-reactive-entity"
        )
        assert result == "feature:052-reactive-entity"

    def test_ref_by_uuid(self, db):
        entity = db.get_entity("feature:050-alpha")
        result = _resolve_ref_to_feature_type_id(
            db, feature_type_id=None, ref=entity["uuid"]
        )
        assert result == "feature:050-alpha"

    def test_ref_prefix_unique_resolves(self, db):
        result = _resolve_ref_to_feature_type_id(
            db, feature_type_id=None, ref="feature:052"
        )
        assert result == "feature:052-reactive-entity"

    def test_ref_ambiguous_errors(self, db):
        with pytest.raises(ValueError, match="Multiple"):
            _resolve_ref_to_feature_type_id(
                db, feature_type_id=None, ref="feature:05"
            )

    def test_neither_provided_errors(self, db):
        with pytest.raises(ValueError, match="feature_type_id.*ref"):
            _resolve_ref_to_feature_type_id(
                db, feature_type_id=None, ref=None
            )
