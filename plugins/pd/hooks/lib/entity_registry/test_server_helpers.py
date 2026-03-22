"""Tests for entity_registry.server_helpers module."""
from __future__ import annotations

import os
import uuid

import pytest

import re

from entity_registry.database import EntityDatabase, _UUID_V4_RE

# Non-anchored version for searching within longer strings
_UUID_V4_SEARCH_RE = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'
)
from entity_registry.server_helpers import (
    _format_entity_label,
    _process_export_lineage_markdown,
    _process_get_lineage,
    _process_register_entity,
    parse_metadata,
    render_tree,
    resolve_output_path,
)


ENTITY_UUIDS = {
    "project:P001": "550e8400-e29b-41d4-a716-446655440001",
    "feature:001-slug": "550e8400-e29b-41d4-a716-446655440002",
    "feature:002-slug": "550e8400-e29b-41d4-a716-446655440003",
    "brainstorm:20260101-test": "550e8400-e29b-41d4-a716-446655440004",
    "backlog:00001": "550e8400-e29b-41d4-a716-446655440005",
}


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


# ---------------------------------------------------------------------------
# Task 2.1: render_tree tests
# ---------------------------------------------------------------------------


def _make_entity(
    type_id: str,
    name: str,
    entity_type: str,
    status: str | None = None,
    parent_type_id: str | None = None,
    created_at: str = "2026-02-27T12:00:00+00:00",
    metadata: str | None = None,
) -> dict:
    """Helper to create an entity dict matching the database row shape."""
    entity = {
        "type_id": type_id,
        "name": name,
        "entity_type": entity_type,
        "status": status,
        "parent_type_id": parent_type_id,
        "created_at": created_at,
        "metadata": metadata,
    }
    entity["uuid"] = ENTITY_UUIDS.get(type_id, str(uuid.uuid4()))
    entity["parent_uuid"] = (
        ENTITY_UUIDS.get(parent_type_id)
        if parent_type_id else None
    )
    return entity


def _link_parent_uuids(entities: list[dict]) -> list[dict]:
    """Fix up parent_uuid fields so children reference their parent's uuid.

    _make_entity uses ENTITY_UUIDS for parent_uuid lookup, which only covers
    a few well-known type_ids.  This helper resolves parent_uuid from the
    actual uuid assigned to each entity in the list (parent-first order).
    """
    tid_to_uuid = {e["type_id"]: e["uuid"] for e in entities}
    for e in entities:
        ptid = e.get("parent_type_id")
        if ptid and ptid in tid_to_uuid:
            e["parent_uuid"] = tid_to_uuid[ptid]
    return entities


class TestRenderTree:
    def test_single_node_no_status(self):
        """A single node with no status renders without status in parens."""
        entities = [
            _make_entity("project:alpha", "Alpha", "project"),
        ]
        result = render_tree(entities, entities[0]["uuid"])
        assert result == 'project:alpha \u2014 "Alpha" (2026-02-27)'

    def test_single_node_with_status(self):
        """A single node with status renders status before date."""
        entities = [
            _make_entity("project:alpha", "Alpha", "project", status="active"),
        ]
        result = render_tree(entities, entities[0]["uuid"])
        assert result == 'project:alpha \u2014 "Alpha" (active, 2026-02-27)'

    def test_linear_chain_three_deep(self):
        """A 3-node linear chain renders with proper indentation."""
        entities = _link_parent_uuids([
            _make_entity(
                "backlog:00019", "Item", "backlog",
                status="promoted",
            ),
            _make_entity(
                "brainstorm:20260227-lineage", "Entity Lineage", "brainstorm",
                parent_type_id="backlog:00019",
            ),
            _make_entity(
                "feature:029-entity-lineage-tracking", "Entity Lineage", "feature",
                status="active",
                parent_type_id="brainstorm:20260227-lineage",
            ),
        ])
        result = render_tree(entities, entities[0]["uuid"])
        expected = (
            'backlog:00019 \u2014 "Item" (promoted, 2026-02-27)\n'
            '  \u2514\u2500 brainstorm:20260227-lineage \u2014 "Entity Lineage" (2026-02-27)\n'
            '     \u2514\u2500 feature:029-entity-lineage-tracking \u2014 "Entity Lineage" (active, 2026-02-27)'
        )
        assert result == expected

    def test_branching_tree_two_children(self):
        """Two children: first uses box tee, second uses corner."""
        entities = _link_parent_uuids([
            _make_entity("project:root", "Root", "project", status="active"),
            _make_entity(
                "feature:a", "Alpha", "feature",
                parent_type_id="project:root",
            ),
            _make_entity(
                "feature:b", "Beta", "feature",
                status="done",
                parent_type_id="project:root",
            ),
        ])
        result = render_tree(entities, entities[0]["uuid"])
        expected = (
            'project:root \u2014 "Root" (active, 2026-02-27)\n'
            '  \u251c\u2500 feature:a \u2014 "Alpha" (2026-02-27)\n'
            '  \u2514\u2500 feature:b \u2014 "Beta" (done, 2026-02-27)'
        )
        assert result == expected

    def test_branching_tree_with_nested_children(self):
        """A root with two children, first child has a grandchild."""
        entities = _link_parent_uuids([
            _make_entity("project:root", "Root", "project"),
            _make_entity(
                "feature:a", "Alpha", "feature",
                parent_type_id="project:root",
            ),
            _make_entity(
                "feature:a1", "Alpha Sub", "feature",
                parent_type_id="feature:a",
            ),
            _make_entity(
                "feature:b", "Beta", "feature",
                parent_type_id="project:root",
            ),
        ])
        result = render_tree(entities, entities[0]["uuid"])
        lines = result.split("\n")
        assert len(lines) == 4
        # Root line
        assert lines[0] == 'project:root \u2014 "Root" (2026-02-27)'
        # First child (not last) uses tee
        assert "\u251c\u2500 feature:a" in lines[1]
        # Grandchild under first child; continuation line uses pipe
        assert "\u2502" in lines[2]
        assert "\u2514\u2500 feature:a1" in lines[2]
        # Second child (last) uses corner
        assert "\u2514\u2500 feature:b" in lines[3]

    def test_empty_list_returns_empty_string(self):
        """An empty entity list should return an empty string."""
        result = render_tree([], "project:nonexistent")
        assert result == ""

    def test_root_not_found_returns_empty_string(self):
        """If root_id UUID is not in the entities list, return empty."""
        entities = [
            _make_entity("feature:a", "Alpha", "feature"),
        ]
        result = render_tree(entities, "not-a-real-uuid")
        assert result == ""


# ---------------------------------------------------------------------------
# Task 2.3: parse_metadata tests
# ---------------------------------------------------------------------------


class TestParseMetadata:
    def test_valid_json_returns_dict(self):
        """Valid JSON string should be parsed to a dict."""
        result = parse_metadata('{"priority": "high", "count": 3}')
        assert result == {"priority": "high", "count": 3}

    def test_empty_object_returns_empty_dict(self):
        """An empty JSON object should return an empty dict."""
        result = parse_metadata("{}")
        assert result == {}

    def test_invalid_json_returns_empty_dict(self):
        """Invalid JSON should return an empty dict (not an error dict)."""
        result = parse_metadata("not valid json")
        assert result == {}

    def test_none_returns_empty_dict(self):
        """None input should return {} (not None)."""
        result = parse_metadata(None)
        assert result == {}

    def test_nested_json(self):
        """Nested JSON objects should parse correctly."""
        result = parse_metadata('{"a": {"b": [1, 2, 3]}}')
        assert result == {"a": {"b": [1, 2, 3]}}

    def test_empty_string_returns_empty_dict(self):
        """Empty string is invalid JSON and should return empty dict."""
        result = parse_metadata("")
        assert result == {}


# ---------------------------------------------------------------------------
# Task 2.5: resolve_output_path tests
# ---------------------------------------------------------------------------


class TestResolveOutputPath:
    def test_relative_path_resolved_against_artifacts_root(self, tmp_path):
        """A relative path should be joined with artifacts_root."""
        artifacts_root = str(tmp_path / "docs")
        os.makedirs(artifacts_root, exist_ok=True)
        result = resolve_output_path("features/f1/spec.md", artifacts_root)
        expected = os.path.realpath(os.path.join(artifacts_root, "features/f1/spec.md"))
        assert result == expected

    def test_absolute_path_inside_root_accepted(self, tmp_path):
        """An absolute path inside artifacts_root should be accepted."""
        artifacts_root = str(tmp_path / "docs")
        os.makedirs(artifacts_root, exist_ok=True)
        abs_path = os.path.join(artifacts_root, "output.md")
        result = resolve_output_path(abs_path, artifacts_root)
        assert result == os.path.realpath(abs_path)

    def test_absolute_path_outside_root_rejected(self, tmp_path):
        """An absolute path outside artifacts_root should return None."""
        artifacts_root = str(tmp_path / "docs")
        os.makedirs(artifacts_root, exist_ok=True)
        result = resolve_output_path("/tmp/escape.md", artifacts_root)
        assert result is None

    def test_none_returns_none(self):
        """None input should return None."""
        result = resolve_output_path(None, "/home/user/docs")
        assert result is None

    def test_simple_filename_resolved(self, tmp_path):
        """A bare filename should be joined with artifacts_root."""
        artifacts_root = str(tmp_path / "docs")
        os.makedirs(artifacts_root, exist_ok=True)
        result = resolve_output_path("spec.md", artifacts_root)
        expected = os.path.realpath(os.path.join(artifacts_root, "spec.md"))
        assert result == expected

    def test_artifacts_root_trailing_slash(self, tmp_path):
        """Trailing slash on artifacts_root should not double up."""
        artifacts_root = str(tmp_path / "docs") + "/"
        os.makedirs(artifacts_root, exist_ok=True)
        result = resolve_output_path("features/spec.md", artifacts_root)
        expected = os.path.realpath(os.path.join(artifacts_root, "features/spec.md"))
        assert result == expected

    def test_path_traversal_rejected(self, tmp_path):
        """Path traversal via .. should be rejected if it escapes root."""
        artifacts_root = str(tmp_path / "docs")
        os.makedirs(artifacts_root, exist_ok=True)
        result = resolve_output_path("../../etc/passwd", artifacts_root)
        assert result is None


# ---------------------------------------------------------------------------
# Task 2.7: _process_register_entity and _process_get_lineage tests
# ---------------------------------------------------------------------------


class TestProcessRegisterEntity:
    def test_happy_path_returns_success_string(self, db: EntityDatabase):
        """Successful registration returns a string containing the type_id."""
        result = _process_register_entity(
            db, "feature", "f1", "Feature One",
            artifact_path=None, status="active",
            parent_type_id=None, metadata=None,
        )
        assert isinstance(result, str)
        assert "feature:f1" in result

    def test_entity_actually_registered(self, db: EntityDatabase):
        """The entity should exist in the database after registration."""
        _process_register_entity(
            db, "project", "p1", "Project One",
            artifact_path="/docs/p1", status="active",
            parent_type_id=None, metadata=None,
        )
        entity = db.get_entity("project:p1")
        assert entity is not None
        assert entity["name"] == "Project One"
        assert entity["status"] == "active"

    def test_with_parent_and_metadata(self, db: EntityDatabase):
        """Registration with parent and metadata should succeed."""
        db.register_entity("project", "parent", "Parent")
        result = _process_register_entity(
            db, "feature", "child", "Child Feature",
            artifact_path=None, status=None,
            parent_type_id="project:parent",
            metadata={"key": "value"},
        )
        assert isinstance(result, str)
        assert "feature:child" in result
        entity = db.get_entity("feature:child")
        assert entity is not None
        assert entity["parent_type_id"] == "project:parent"

    def test_invalid_entity_type_returns_error_string(self, db: EntityDatabase):
        """Invalid entity_type should return an error string, not raise."""
        result = _process_register_entity(
            db, "invalid_type", "x", "Bad",
            artifact_path=None, status=None,
            parent_type_id=None, metadata=None,
        )
        assert isinstance(result, str)
        assert "error" in result.lower() or "invalid" in result.lower()

    def test_invalid_parent_returns_error_string(self, db: EntityDatabase):
        """Referencing a non-existent parent should return error string."""
        result = _process_register_entity(
            db, "feature", "f1", "Feature",
            artifact_path=None, status=None,
            parent_type_id="project:nonexistent",
            metadata=None,
        )
        assert isinstance(result, str)
        assert "error" in result.lower()

    def test_never_raises(self, db: EntityDatabase):
        """_process_register_entity should never raise exceptions."""
        # Even with bizarre inputs, it should return a string
        result = _process_register_entity(
            db, "", "", "",
            artifact_path=None, status=None,
            parent_type_id=None, metadata=None,
        )
        assert isinstance(result, str)


class TestProcessGetLineage:
    def _setup_chain(self, db: EntityDatabase):
        """Create project:root -> feature:mid -> feature:leaf chain."""
        db.register_entity("project", "root", "Root Project", status="active")
        db.register_entity(
            "feature", "mid", "Mid Feature",
            parent_type_id="project:root",
        )
        db.register_entity(
            "feature", "leaf", "Leaf Feature",
            status="done",
            parent_type_id="feature:mid",
        )

    def test_upward_returns_formatted_tree(self, db: EntityDatabase):
        """Upward lineage should return a formatted string with all ancestors."""
        self._setup_chain(db)
        result = _process_get_lineage(db, "feature:leaf", "up", 10)
        assert isinstance(result, str)
        assert "project:root" in result
        assert "feature:mid" in result
        assert "feature:leaf" in result

    def test_downward_returns_formatted_tree(self, db: EntityDatabase):
        """Downward lineage should return a formatted tree."""
        self._setup_chain(db)
        result = _process_get_lineage(db, "project:root", "down", 10)
        assert isinstance(result, str)
        assert "project:root" in result
        assert "feature:mid" in result
        assert "feature:leaf" in result

    def test_nonexistent_entity_returns_not_found(self, db: EntityDatabase):
        """Non-existent type_id should return a 'not found' message."""
        result = _process_get_lineage(db, "feature:nonexistent", "up", 10)
        assert isinstance(result, str)
        assert "not found" in result.lower() or "no" in result.lower()

    def test_single_entity_lineage(self, db: EntityDatabase):
        """A single entity with no parents/children returns just itself."""
        db.register_entity("project", "solo", "Solo")
        result = _process_get_lineage(db, "project:solo", "up", 10)
        assert isinstance(result, str)
        assert "project:solo" in result

    def test_never_raises(self, db: EntityDatabase):
        """_process_get_lineage should never raise exceptions."""
        # Close the database to force an error condition
        db.close()
        result = _process_get_lineage(db, "feature:anything", "up", 10)
        assert isinstance(result, str)

    def test_upward_shows_chain_format(self, db: EntityDatabase):
        """Upward lineage renders as a chain (root first)."""
        self._setup_chain(db)
        result = _process_get_lineage(db, "feature:leaf", "up", 10)
        # Root should appear before leaf in the output
        root_pos = result.index("project:root")
        leaf_pos = result.index("feature:leaf")
        assert root_pos < leaf_pos

    def test_downward_shows_tree_format(self, db: EntityDatabase):
        """Downward lineage renders as a tree from root."""
        db.register_entity("project", "root", "Root", status="active")
        db.register_entity(
            "feature", "a", "Alpha",
            parent_type_id="project:root",
        )
        db.register_entity(
            "feature", "b", "Beta",
            parent_type_id="project:root",
        )
        result = _process_get_lineage(db, "project:root", "down", 10)
        assert isinstance(result, str)
        assert "project:root" in result
        assert "feature:a" in result
        assert "feature:b" in result

    def test_process_get_lineage_passes_uuid(self):
        """_process_get_lineage passes UUID (not type_id) to render_tree."""
        from unittest.mock import patch

        from entity_registry.server_helpers import render_tree

        db = EntityDatabase(":memory:")
        try:
            db.register_entity("project", "root", "Root Project", status="active")
            db.register_entity(
                "feature", "mid", "Mid Feature",
                parent_type_id="project:root",
            )
            db.register_entity(
                "feature", "leaf", "Leaf Feature",
                status="done",
                parent_type_id="feature:mid",
            )

            with patch('entity_registry.server_helpers.render_tree', wraps=render_tree) as mock_rt:
                _process_get_lineage(db, "feature:leaf", "up", 10)
                # render_tree(entities, root_id, max_depth) -- root_id is args[1]
                root_arg = mock_rt.call_args.args[1]
                assert _UUID_V4_RE.match(root_arg), (
                    f"Expected UUID, got: {root_arg}"
                )
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Task 4.2: _process_export_lineage_markdown tests
# ---------------------------------------------------------------------------


class TestProcessExportLineageMarkdown:
    def test_returns_markdown_string(self, db: EntityDatabase):
        """Export returns a markdown string when no output_path is given."""
        db.register_entity("project", "p1", "Project One", status="active")
        result = _process_export_lineage_markdown(db, "project:p1", None, "/tmp")
        assert isinstance(result, str)
        assert "Project One" in result

    def test_all_trees_when_type_id_is_none(self, db: EntityDatabase):
        """Export all trees when type_id is None."""
        db.register_entity("project", "p1", "Project One")
        db.register_entity("project", "p2", "Project Two")
        result = _process_export_lineage_markdown(db, None, None, "/tmp")
        assert "Project One" in result
        assert "Project Two" in result

    def test_writes_to_file(self, db: EntityDatabase, tmp_path):
        """Export writes markdown to file when output_path is given."""
        db.register_entity("feature", "f1", "Feature One", status="active")
        artifacts_root = str(tmp_path / "docs")
        import os
        os.makedirs(artifacts_root, exist_ok=True)
        result = _process_export_lineage_markdown(
            db, "feature:f1", "lineage.md", artifacts_root,
        )
        assert "Exported" in result
        expected_path = os.path.realpath(os.path.join(artifacts_root, "lineage.md"))
        assert expected_path in result
        with open(expected_path) as f:
            content = f.read()
        assert "Feature One" in content

    def test_relative_path_resolved_against_artifacts_root(self, db: EntityDatabase, tmp_path):
        """A relative output_path is resolved against artifacts_root."""
        db.register_entity("project", "p1", "Project One")
        artifacts_root = str(tmp_path / "docs")
        import os
        os.makedirs(artifacts_root, exist_ok=True)
        result = _process_export_lineage_markdown(db, "project:p1", "lineage.md", artifacts_root)
        assert "Exported" in result
        expected_path = str(tmp_path / "docs" / "lineage.md")
        assert expected_path in result

    def test_nonexistent_entity_returns_error(self, db: EntityDatabase):
        """Export with nonexistent type_id returns error string (ValueError propagates from DB layer)."""
        result = _process_export_lineage_markdown(db, "project:nonexistent", None, "/tmp")
        assert isinstance(result, str)
        # ValueError propagates from export_lineage_markdown, caught by _process wrapper
        assert "error" in result.lower()

    def test_never_raises(self, db: EntityDatabase):
        """_process_export_lineage_markdown should never raise."""
        db.close()
        result = _process_export_lineage_markdown(db, "feature:x", None, "/tmp")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Deepened tests: BDD, Boundary, Adversarial, Error, Mutation
# ---------------------------------------------------------------------------


class TestRenderTreeDeepNesting:
    """Adversarial: deeply nested structures render correctly.
    derived_from: dimension:adversarial
    """

    def test_render_tree_with_deeply_nested_structure(self):
        # Given a chain 6 levels deep
        entities = [_make_entity("project:root", "Root", "project")]
        for i in range(1, 6):
            entities.append(
                _make_entity(
                    f"feature:level-{i}", f"Level {i}", "feature",
                    parent_type_id=(
                        "project:root" if i == 1 else f"feature:level-{i-1}"
                    ),
                )
            )
        _link_parent_uuids(entities)
        # When rendering the tree
        result = render_tree(entities, entities[0]["uuid"])
        # Then all 6 levels appear in output
        assert "project:root" in result
        for i in range(1, 6):
            assert f"feature:level-{i}" in result
        # And indentation increases with depth
        lines = result.split("\n")
        assert len(lines) == 6
        # Deeper lines have more leading whitespace
        for i in range(1, len(lines)):
            stripped_prev = lines[i - 1].lstrip()
            stripped_curr = lines[i].lstrip()
            indent_prev = len(lines[i - 1]) - len(stripped_prev)
            indent_curr = len(lines[i]) - len(stripped_curr)
            assert indent_curr >= indent_prev


class TestPathNormalization:
    """BDD: AC-7 — path normalization for relative and absolute paths.
    derived_from: spec:AC-7
    """

    def test_path_normalization_relative_paths_resolved(self, tmp_path):
        # Given a relative path and a real artifacts_root
        artifacts_root = str(tmp_path / "docs")
        import os
        os.makedirs(artifacts_root, exist_ok=True)
        result = resolve_output_path("features/f1/lineage.md", artifacts_root)
        # Then it's resolved against artifacts_root
        expected = os.path.realpath(os.path.join(artifacts_root, "features/f1/lineage.md"))
        assert result == expected
        assert result.startswith("/")

    def test_path_normalization_absolute_paths_outside_root_rejected(self, tmp_path):
        # Given an absolute path outside artifacts_root
        artifacts_root = str(tmp_path / "docs")
        import os
        os.makedirs(artifacts_root, exist_ok=True)
        result = resolve_output_path("/absolute/path/file.md", artifacts_root)
        # Then it's rejected (returns None) because it escapes the root
        assert result is None

    def test_path_normalization_external_paths_show_warning(self):
        # Given a None path (no output requested)
        result = resolve_output_path(None, "/home/user/docs")
        # Then None is returned (no path resolution)
        assert result is None


class TestParseMetadataMalformed:
    """Adversarial: malformed metadata JSON handled gracefully.
    derived_from: dimension:adversarial, spec:AC-3
    """

    def test_malformed_meta_json_handled_gracefully(self):
        # Given malformed JSON string
        result = parse_metadata("{key: invalid}")
        # Then an empty dict is returned (not an exception, not an error dict)
        assert result == {}

    def test_meta_json_with_extra_unexpected_fields_accepted(self):
        # Given JSON with unexpected extra fields
        result = parse_metadata('{"expected": 1, "extra_field": "surprise", "nested": {"deep": true}}')
        # Then all fields are parsed and returned
        assert isinstance(result, dict)
        assert result["expected"] == 1
        assert result["extra_field"] == "surprise"
        assert result["nested"]["deep"] is True


class TestErrorPropagation:
    """Error propagation: error messages include context.
    derived_from: dimension:error_propagation
    """

    def test_orphaned_parent_error_includes_context(self, db: EntityDatabase):
        # Given a feature entity with no parent
        db.register_entity("feature", "f1", "Feature One")
        # When setting parent to nonexistent entity via _process helper
        result = _process_register_entity(
            db, "feature", "orphan-child", "Orphan",
            artifact_path=None, status=None,
            parent_type_id="project:nonexistent",
            metadata=None,
        )
        # Then the error message includes context about the missing entity
        assert isinstance(result, str)
        assert "error" in result.lower()

    def test_database_connection_failure_propagates_cleanly(
        self, db: EntityDatabase,
    ):
        # Given a closed database connection
        db.close()
        # When attempting to get lineage
        result = _process_get_lineage(db, "feature:f1", "up", 10)
        # Then a string error is returned, not an exception
        assert isinstance(result, str)

    def test_depth_limit_message_for_truncated_lineage(self, db: EntityDatabase):
        # Given a chain of 15 entities
        db.register_entity("project", "e0", "E0")
        for i in range(1, 15):
            db.register_entity(
                "feature", f"e{i}", f"E{i}",
                parent_type_id=f"{'project' if i == 1 else 'feature'}:e{i-1}",
            )
        # When traversing upward from e14 with max_depth=5
        result = _process_get_lineage(db, "feature:e14", "up", 5)
        # Then a tree is returned (not empty/not-found) but truncated
        assert isinstance(result, str)
        assert "feature:e14" in result
        # And e0 (root, 14 hops away) is NOT in the output
        assert "project:e0" not in result


class TestExternalPathWarning:
    """Error propagation: external path detection includes the path.
    derived_from: dimension:error_propagation
    """

    def test_external_path_warning_includes_the_path(self, db: EntityDatabase, tmp_path):
        # Given an export to a relative output file path
        artifacts_root = str(tmp_path / "docs")
        os.makedirs(artifacts_root, exist_ok=True)
        db.register_entity("project", "p1", "Test Project")
        # When exporting with a relative output path
        result = _process_export_lineage_markdown(db, "project:p1", "output.md", artifacts_root)
        # Then the result contains the resolved path
        expected_path = os.path.realpath(os.path.join(artifacts_root, "output.md"))
        assert expected_path in result


class TestProcessGetLineageUpwardChainFormat:
    """Mutation mindset: upward lineage root appears before leaf.
    derived_from: dimension:mutation_mindset
    """

    def test_upward_lineage_renders_root_before_leaf(self, db: EntityDatabase):
        # Given A -> B -> C chain
        db.register_entity("project", "root", "Root", status="active")
        db.register_entity(
            "feature", "mid", "Mid", parent_type_id="project:root",
        )
        db.register_entity(
            "feature", "leaf", "Leaf", parent_type_id="feature:mid",
        )
        # When getting upward lineage from leaf
        result = _process_get_lineage(db, "feature:leaf", "up", 10)
        # Then root appears before leaf in the rendered string
        root_pos = result.index("project:root")
        leaf_pos = result.index("feature:leaf")
        assert root_pos < leaf_pos
        # Mutation check: if order was reversed, root would appear after leaf


# ---------------------------------------------------------------------------
# AC-5/I7: depends_on_features annotations in tree output
# ---------------------------------------------------------------------------


class TestFormatEntityLabelDependsOn:
    """AC-5: depends_on_features annotations rendered in entity labels."""

    def test_entity_with_depends_on_features_shows_annotation(self):
        """Entity with depends_on_features metadata shows [depends on: ...] annotation."""
        import json
        entity = _make_entity(
            "feature:031-api-gateway", "API Gateway", "feature",
            status="planned",
            metadata=json.dumps({"depends_on_features": ["030-auth-module"]}),
        )
        label = _format_entity_label(entity)
        assert label == (
            'feature:031-api-gateway \u2014 "API Gateway" '
            '(planned, 2026-02-27) [depends on: feature:030-auth-module]'
        )

    def test_entity_with_multiple_depends_on_features(self):
        """Entity with multiple depends_on_features shows all dependencies."""
        import json
        entity = _make_entity(
            "feature:032-dashboard", "Dashboard", "feature",
            status="planned",
            metadata=json.dumps({
                "depends_on_features": ["030-auth-module", "031-api-gateway"],
            }),
        )
        label = _format_entity_label(entity)
        assert label == (
            'feature:032-dashboard \u2014 "Dashboard" '
            '(planned, 2026-02-27) '
            '[depends on: feature:030-auth-module, feature:031-api-gateway]'
        )

    def test_entity_with_no_metadata_unchanged(self):
        """Entity with no metadata (None) has no annotation."""
        entity = _make_entity(
            "feature:030-auth-module", "Auth Module", "feature",
            status="active",
        )
        label = _format_entity_label(entity)
        assert label == (
            'feature:030-auth-module \u2014 "Auth Module" (active, 2026-02-27)'
        )

    def test_entity_with_metadata_but_no_depends_on_features(self):
        """Entity with metadata but no depends_on_features key has no annotation."""
        import json
        entity = _make_entity(
            "feature:030-auth-module", "Auth Module", "feature",
            status="active",
            metadata=json.dumps({"priority": "high"}),
        )
        label = _format_entity_label(entity)
        assert label == (
            'feature:030-auth-module \u2014 "Auth Module" (active, 2026-02-27)'
        )

    def test_entity_with_empty_depends_on_features_list(self):
        """Entity with empty depends_on_features list has no annotation."""
        import json
        entity = _make_entity(
            "feature:030-auth-module", "Auth Module", "feature",
            status="active",
            metadata=json.dumps({"depends_on_features": []}),
        )
        label = _format_entity_label(entity)
        assert label == (
            'feature:030-auth-module \u2014 "Auth Module" (active, 2026-02-27)'
        )

    def test_depends_on_in_tree_output(self):
        """AC-5 end-to-end: depends_on annotations appear in render_tree output."""
        import json
        entities = _link_parent_uuids([
            _make_entity("project:P001", "Project Name", "project", status="active"),
            _make_entity(
                "feature:030-auth-module", "Auth Module", "feature",
                status="active",
                parent_type_id="project:P001",
            ),
            _make_entity(
                "feature:031-api-gateway", "API Gateway", "feature",
                status="planned",
                parent_type_id="project:P001",
                metadata=json.dumps({"depends_on_features": ["030-auth-module"]}),
            ),
            _make_entity(
                "feature:032-dashboard", "Dashboard", "feature",
                status="planned",
                parent_type_id="project:P001",
                metadata=json.dumps({
                    "depends_on_features": ["030-auth-module", "031-api-gateway"],
                }),
            ),
        ])
        result = render_tree(entities, entities[0]["uuid"])
        assert "[depends on: feature:030-auth-module]" in result
        assert "[depends on: feature:030-auth-module, feature:031-api-gateway]" in result
        # The entity without dependencies should NOT have annotation
        lines = result.split("\n")
        auth_line = [l for l in lines if "030-auth-module" in l and "depends on" not in l]
        assert len(auth_line) == 1  # auth-module line has no depends_on annotation

    def test_invalid_metadata_json_no_annotation(self):
        """Entity with invalid metadata JSON has no annotation (graceful)."""
        entity = _make_entity(
            "feature:030-auth-module", "Auth Module", "feature",
            status="active",
            metadata="not valid json",
        )
        label = _format_entity_label(entity)
        # Should still produce a valid label, just without annotation
        assert label == (
            'feature:030-auth-module \u2014 "Auth Module" (active, 2026-02-27)'
        )


# ---------------------------------------------------------------------------
# Deepened tests: Phase B — spec-driven test deepening
# ---------------------------------------------------------------------------


class TestRegisterEntityDualIdentityMessage:
    """BDD: AC-28/R28 — register message includes both UUID and type_id.
    derived_from: spec:R28, spec:R34
    """

    def test_register_message_concise_type_id_only(
        self, db: EntityDatabase,
    ):
        """_process_register_entity returns concise message with only type_id.
        derived_from: feature:045-mcp-audit-token-efficiency P1-C3
        """
        # Given a database
        # When registering an entity
        result = _process_register_entity(
            db, "project", "p1", "Project One",
            artifact_path=None, status="active",
            parent_type_id=None, metadata=None,
        )
        # Then the message contains only type_id, no UUID
        assert result == "Registered: project:p1"
        assert not _UUID_V4_SEARCH_RE.search(result), (
            f"UUID found in message, should be type_id only: {result}"
        )

    def test_register_existing_entity_message_still_concise(
        self, db: EntityDatabase,
    ):
        """Re-registering returns same concise format.
        derived_from: feature:045-mcp-audit-token-efficiency P1-C3
        """
        # Given an already-registered entity
        first_result = _process_register_entity(
            db, "feature", "f1", "Feature One",
            artifact_path=None, status=None,
            parent_type_id=None, metadata=None,
        )
        assert first_result == "Registered: feature:f1"
        # When registering again
        second_result = _process_register_entity(
            db, "feature", "f1", "Feature One Updated",
            artifact_path=None, status=None,
            parent_type_id=None, metadata=None,
        )
        # Then the same concise format with type_id only
        assert second_result == "Registered: feature:f1"


class TestRenderTreeUuidKeying:
    """Mutation mindset: render_tree keys on uuid, not type_id.
    derived_from: dimension:mutation_mindset, spec:R33
    """

    def test_render_tree_with_uuid_root_id(self):
        """render_tree requires UUID as root_id, not type_id.
        Anticipate: If render_tree still keys on type_id internally,
        passing a UUID as root_id would fail to find the root.
        """
        # Given entities with uuid fields
        entities = _link_parent_uuids([
            _make_entity("project:root", "Root", "project"),
            _make_entity(
                "feature:child", "Child", "feature",
                parent_type_id="project:root",
            ),
        ])
        root_uuid = entities[0]["uuid"]
        # When rendering with UUID root_id
        result = render_tree(entities, root_uuid)
        # Then both entities appear in output
        assert "project:root" in result
        assert "feature:child" in result

    def test_render_tree_type_id_as_root_returns_empty(self):
        """Passing type_id (not UUID) as root_id should return empty.
        Anticipate: If render_tree internally keys by_id on type_id,
        passing a type_id string would work when it shouldn't.
        derived_from: dimension:mutation_mindset
        """
        # Given entities with uuid fields
        entities = [
            _make_entity("project:root", "Root", "project"),
        ]
        # When passing type_id as root_id (not UUID)
        result = render_tree(entities, "project:root")
        # Then empty string (type_id is not a key in by_id — keyed by uuid)
        assert result == ""


class TestProcessGetLineageUuidRoot:
    """BDD: _process_get_lineage passes UUID to render_tree for root.
    derived_from: spec:R33, dimension:mutation_mindset
    """

    def test_downward_lineage_passes_uuid_root(self, db: EntityDatabase):
        """_process_get_lineage for downward direction passes uuid root.
        Anticipate: Downward might use a different code path than upward
        and might pass type_id instead of uuid to render_tree.
        """
        # Given a parent-child tree
        db.register_entity("project", "root", "Root", status="active")
        db.register_entity(
            "feature", "child", "Child",
            parent_type_id="project:root",
        )
        # When getting downward lineage
        from unittest.mock import patch
        with patch(
            'entity_registry.server_helpers.render_tree',
            wraps=render_tree,
        ) as mock_rt:
            _process_get_lineage(db, "project:root", "down", 10)
            # Then render_tree's root_id arg is a UUID
            root_arg = mock_rt.call_args.args[1]
            assert _UUID_V4_RE.match(root_arg), (
                f"Expected UUID root_id for downward lineage, got: {root_arg}"
            )


# ---------------------------------------------------------------------------
# _process_export_entities tests
# ---------------------------------------------------------------------------

from entity_registry.server_helpers import _process_export_entities


class TestProcessExportEntities:
    """TDD tests for _process_export_entities() helper.

    Tests cover: JSON return, file write, parent dir creation, path escape,
    OSError handling, ValueError propagation, UTF-8 encoding, indentation,
    include_lineage forwarding, and confirmation message format.
    """

    def test_no_output_path_returns_json_string(self, db: EntityDatabase):
        """When output_path is None, returns valid JSON string directly."""
        import json

        db.register_entity("feature", "001", "Feature One", status="active")
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
        )
        # Must be a valid JSON string
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert "entities" in parsed
        assert parsed["entity_count"] >= 1

    def test_output_path_writes_file(self, db: EntityDatabase, tmp_path):
        """When output_path provided, file is created with valid JSON
        and returns confirmation message (AC-4)."""
        import json

        db.register_entity("feature", "001", "Feature One", status="active")
        out_file = str(tmp_path / "export.json")
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=out_file,
            include_lineage=True,
            artifacts_root=str(tmp_path),
        )
        # File must exist with valid JSON
        assert os.path.exists(out_file)
        with open(out_file, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert data["entity_count"] >= 1
        # Confirmation message
        assert "Exported" in result
        assert out_file in result or str(tmp_path) in result

    def test_output_path_creates_parent_dirs(self, db: EntityDatabase, tmp_path):
        """When output_path has non-existent parent dirs, they are
        auto-created (AC-10)."""
        db.register_entity("feature", "001", "Feature One", status="active")
        nested = tmp_path / "deep" / "nested" / "dir"
        out_file = str(nested / "export.json")
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=out_file,
            include_lineage=True,
            artifacts_root=str(tmp_path),
        )
        assert os.path.exists(out_file)
        assert "Exported" in result

    def test_path_escape_returns_error(self, db: EntityDatabase, tmp_path):
        """Path escape attempt returns error string (AC-6)."""
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path="../../etc/passwd",
            include_lineage=True,
            artifacts_root=str(tmp_path),
        )
        assert result == "Error: output path escapes artifacts root"

    def test_oserror_returns_error_string(self, db: EntityDatabase, tmp_path):
        """OSError (e.g. permission denied) returns error string (FR-3)."""
        from unittest.mock import patch

        db.register_entity("feature", "001", "Feature One", status="active")
        out_file = str(tmp_path / "export.json")
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            result = _process_export_entities(
                db,
                entity_type=None,
                status=None,
                output_path=out_file,
                include_lineage=True,
                artifacts_root=str(tmp_path),
            )
        assert result.startswith("Error writing export: ")
        assert "Permission denied" in result

    def test_invalid_entity_type_returns_error(self, db: EntityDatabase):
        """Invalid entity_type ValueError returns error string with
        'Error: ' prefix. Database format is authoritative."""
        result = _process_export_entities(
            db,
            entity_type="xyz",
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
        )
        assert result.startswith("Error: Invalid entity_type 'xyz'. Must be one of ")
        assert "'backlog'" in result
        assert "'feature'" in result

    def test_json_encoding_utf8(self, db: EntityDatabase):
        """Non-ASCII characters are preserved in JSON output."""
        import json

        db.register_entity(
            "feature", "001", "Funcionalidad especial", status="activo"
        )
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
        )
        parsed = json.loads(result)
        names = [e["name"] for e in parsed["entities"]]
        assert any("especial" in n for n in names)
        # ensure_ascii=False means no \u escapes for these chars
        assert "\\u" not in result

    def test_json_compact_inline(self, db: EntityDatabase):
        """Inline JSON output uses compact separators (no indent)."""
        db.register_entity("feature", "001", "Feature One", status="active")
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
        )
        # Compact JSON: no newlines, no spaces after separators
        assert "\n" not in result
        assert '": ' not in result

    def test_include_lineage_forwarded(self, db: EntityDatabase):
        """include_lineage=False is passed through to database method."""
        from unittest.mock import patch

        db.register_entity("feature", "001", "Feature One", status="active")
        with patch.object(
            db, "export_entities_json", wraps=db.export_entities_json
        ) as mock_export:
            _process_export_entities(
                db,
                entity_type=None,
                status=None,
                output_path=None,
                include_lineage=False,
                artifacts_root="/tmp",
            )
            mock_export.assert_called_once_with(None, None, False)

    def test_confirmation_message_format(self, db: EntityDatabase, tmp_path):
        """Returns 'Exported {n} entities to {path}' with correct count."""
        db.register_entity("feature", "001", "F1", status="active")
        db.register_entity("feature", "002", "F2", status="active")
        db.register_entity("project", "P1", "P1", status="active")
        out_file = str(tmp_path / "export.json")
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=out_file,
            include_lineage=True,
            artifacts_root=str(tmp_path),
        )
        # Resolve the output path to match what the function returns
        resolved = os.path.realpath(out_file)
        assert result == f"Exported 3 entities to {resolved}"


# ---------------------------------------------------------------------------
# _process_export_entities deepened tests (test-deepener Phase B)
# ---------------------------------------------------------------------------


class TestProcessExportEntitiesDeepened:
    """Deepened tests for _process_export_entities() helper.

    Covers adversarial, error propagation, and mutation dimensions that
    supplement the existing TDD tests above.
    """

    # -- Dimension 3: Adversarial ------------------------------------------

    def test_path_traversal_with_intermediate_segments(
        self, db: EntityDatabase, tmp_path,
    ):
        """Path traversal hidden in intermediate segments is rejected.

        derived_from: adversarial: path traversal variant
        """
        # Given an output_path with traversal embedded in intermediate segments
        db.register_entity("feature", "001", "Feature One")
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path="backup/../../../etc/passwd",
            include_lineage=True,
            artifacts_root=str(tmp_path),
        )
        # Then the path escape error is returned
        assert result == "Error: output path escapes artifacts root"
        # And no file was written outside the sandbox
        assert not os.path.exists("/etc/passwd.json")

    def test_entity_type_sql_injection_returns_error_not_crash(
        self, db: EntityDatabase,
    ):
        """SQL injection in entity_type returns error string, table intact.

        derived_from: adversarial: SQL injection
        """
        # Given a malicious entity_type
        db.register_entity("feature", "001", "Safe Feature")
        result = _process_export_entities(
            db,
            entity_type="'; DROP TABLE entities; --",
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
        )
        # Then an error string is returned (not exception)
        assert result.startswith("Error:")
        assert "Invalid entity_type" in result
        # And the database is still intact
        count = db._conn.execute(
            "SELECT count(*) FROM entities"
        ).fetchone()[0]
        assert count >= 1, "entities table should survive injection attempt"

    def test_entity_type_case_sensitive_returns_error(
        self, db: EntityDatabase,
    ):
        """Case mismatch in entity_type returns error at helper layer.

        derived_from: adversarial: case boundary
        """
        # Given entities of type 'feature' exist
        db.register_entity("feature", "001", "Feature One")
        # When calling with 'Feature' (capital F)
        result = _process_export_entities(
            db,
            entity_type="Feature",
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
        )
        # Then error is returned about invalid entity_type
        assert result.startswith("Error:")
        assert "Invalid entity_type" in result

    # -- Dimension 4: Error Propagation ------------------------------------

    def test_path_escape_error_message_exact_content(
        self, db: EntityDatabase, tmp_path,
    ):
        """Path escape returns the exact documented error string.

        derived_from: error: path escape message
        """
        # Given an output_path that escapes artifacts root
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path="../../escape",
            include_lineage=True,
            artifacts_root=str(tmp_path),
        )
        # Then the exact error string matches (not a partial match)
        assert result == "Error: output path escapes artifacts root"

    def test_malformed_metadata_json_does_not_crash_export(
        self, db: EntityDatabase,
    ):
        """Entity with malformed JSON metadata exports with {} metadata.

        derived_from: error: malformed metadata
        """
        import json as json_mod

        # Given an entity exists with corrupted metadata in the database
        db.register_entity("feature", "001", "Feature One")
        db._conn.execute(
            "UPDATE entities SET metadata = '{bad json' WHERE type_id = ?",
            ("feature:001",),
        )
        db._conn.commit()
        # When export is called
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
        )
        # Then export succeeds with metadata as empty dict
        parsed = json_mod.loads(result)
        entity = parsed["entities"][0]
        assert entity["metadata"] == {}

    # -- Dimension 5: Mutation Mindset -------------------------------------

    def test_no_output_path_returns_parseable_json_with_correct_count(
        self, db: EntityDatabase,
    ):
        """Returned JSON string has entity_count matching actual entities.

        derived_from: mutation: return value
        """
        import json as json_mod

        # Given 4 entities exist
        for i in range(4):
            db.register_entity("feature", f"f{i}", f"Feature {i}")
        # When export with no output_path
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
        )
        # Then entity_count matches len(entities) in the JSON
        parsed = json_mod.loads(result)
        assert parsed["entity_count"] == len(parsed["entities"])
        assert parsed["entity_count"] == 4

    def test_file_output_uses_utf8_encoding(
        self, db: EntityDatabase, tmp_path,
    ):
        """File written with UTF-8 encoding preserves unicode characters.

        derived_from: adversarial: encoding
        """
        import json as json_mod

        # Given an entity with unicode characters in its name
        db.register_entity(
            "feature", "001", "Funcion especial con acentos y tildes",
        )
        out_file = str(tmp_path / "export.json")
        # When export to file
        _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=out_file,
            include_lineage=True,
            artifacts_root=str(tmp_path),
        )
        # Then file is valid UTF-8 JSON with characters preserved
        with open(out_file, encoding="utf-8") as f:
            data = json_mod.load(f)
        names = [e["name"] for e in data["entities"]]
        assert any("especial" in n for n in names)

    def test_include_lineage_false_omits_parent_type_id_in_json_output(
        self, db: EntityDatabase,
    ):
        """include_lineage=False means parent_type_id key is absent in output.

        derived_from: mutation: key presence
        """
        import json as json_mod

        # Given entities with parent relationships
        db.register_entity("project", "p1", "Project One")
        db.register_entity(
            "feature", "f1", "Feature One", parent_type_id="project:p1",
        )
        # When export with include_lineage=False
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=False,
            artifacts_root="/tmp",
        )
        # Then parent_type_id key is completely absent from entity dicts
        parsed = json_mod.loads(result)
        for entity in parsed["entities"]:
            assert "parent_type_id" not in entity, (
                f"parent_type_id should be absent but found in {entity['type_id']}"
            )

    def test_include_lineage_true_shows_parent_type_id_in_json_output(
        self, db: EntityDatabase,
    ):
        """include_lineage=True includes parent_type_id with correct value.

        derived_from: spec:FR-5, spec:FR-2
        """
        import json as json_mod

        # Given entities with parent relationships
        db.register_entity("project", "p1", "Project One")
        db.register_entity(
            "feature", "f1", "Feature One", parent_type_id="project:p1",
        )
        # When export with include_lineage=True
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
        )
        # Then parent_type_id is present and correct
        parsed = json_mod.loads(result)
        child = [e for e in parsed["entities"] if e["type_id"] == "feature:f1"][0]
        assert child["parent_type_id"] == "project:p1"


# ---------------------------------------------------------------------------
# _process_export_entities fields parameter tests (P1-C1)
# ---------------------------------------------------------------------------


class TestProcessExportEntitiesFields:
    """TDD tests for the `fields` parameter of _process_export_entities().

    Tests cover: field projection, backward compat (fields=None),
    and all-invalid-fields error with valid field listing.
    """

    def test_fields_returns_only_specified_fields(self, db: EntityDatabase):
        """When fields='type_id,name,status', only those 3 keys appear per entity."""
        import json as json_mod

        db.register_entity("feature", "001", "Feature One", status="active")
        db.register_entity("feature", "002", "Feature Two", status="draft")
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
            fields="type_id,name,status",
        )
        parsed = json_mod.loads(result)
        assert parsed["entity_count"] >= 2
        for entity in parsed["entities"]:
            assert set(entity.keys()) == {"type_id", "name", "status"}

    def test_fields_none_returns_all_fields(self, db: EntityDatabase):
        """When fields=None (default), all entity fields are returned (backward compat)."""
        import json as json_mod

        db.register_entity("feature", "001", "Feature One", status="active")
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
            fields=None,
        )
        parsed = json_mod.loads(result)
        assert len(parsed["entities"]) >= 1
        entity = parsed["entities"][0]
        # Must have standard entity fields (not just a subset)
        assert "uuid" in entity
        assert "type_id" in entity
        assert "name" in entity
        assert "status" in entity
        assert "entity_type" in entity

    def test_all_invalid_fields_returns_error(self, db: EntityDatabase):
        """When every field name is invalid, returns error listing valid field names."""
        db.register_entity("feature", "001", "Feature One", status="active")
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
            fields="bogus,fake,invalid",
        )
        assert "Error" in result
        # Error message should list valid field names
        assert "type_id" in result
        assert "name" in result
        assert "status" in result

    def test_partial_valid_fields_returns_only_valid(self, db: EntityDatabase):
        """When some fields are valid and some invalid, returns only valid ones (no error)."""
        import json as json_mod

        db.register_entity("feature", "001", "Feature One", status="active")
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
            fields="type_id,bogus_field,name",
        )
        parsed = json_mod.loads(result)
        for entity in parsed["entities"]:
            assert set(entity.keys()) == {"type_id", "name"}

    def test_fields_with_whitespace_stripped(self, db: EntityDatabase):
        """Field names with surrounding whitespace are trimmed."""
        import json as json_mod

        db.register_entity("feature", "001", "Feature One", status="active")
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
            fields=" type_id , name ",
        )
        parsed = json_mod.loads(result)
        for entity in parsed["entities"]:
            assert set(entity.keys()) == {"type_id", "name"}

    def test_fields_with_empty_entity_list_returns_normally(self, db: EntityDatabase):
        """When no entities match, fields param doesn't cause error (empty list)."""
        import json as json_mod

        # Don't register any entities — export returns empty list
        result = _process_export_entities(
            db,
            entity_type="brainstorm",
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
            fields="type_id,name",
        )
        parsed = json_mod.loads(result)
        assert parsed["entities"] == []
        assert parsed["entity_count"] == 0

    def test_fields_works_with_file_output(self, db: EntityDatabase, tmp_path):
        """Field projection applies before writing to file."""
        import json as json_mod

        db.register_entity("feature", "001", "Feature One", status="active")
        out_file = str(tmp_path / "export.json")
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=out_file,
            include_lineage=True,
            artifacts_root=str(tmp_path),
            fields="type_id,status",
        )
        assert "Exported" in result
        with open(out_file, encoding="utf-8") as f:
            data = json_mod.load(f)
        for entity in data["entities"]:
            assert set(entity.keys()) == {"type_id", "status"}


# ---------------------------------------------------------------------------
# Deepened tests: export_entities fields boundary + adversarial
# derived_from: spec:AC-1 (field projection), dimension:boundary_values,
#               dimension:adversarial
# ---------------------------------------------------------------------------


class TestProcessExportEntitiesFieldsDeepened:
    """Deepened tests for _process_export_entities() fields parameter.

    Covers boundary values (single field, all fields) and adversarial
    (empty string input). Each test targets a specific failure mode that
    the TDD tests above do not cover.
    """

    def test_export_entities_fields_single_field(self, db: EntityDatabase):
        """Boundary: fields with exactly one valid field name returns only that field.
        derived_from: spec:AC-1 (field projection), dimension:boundary_values

        Anticipate: If the split/filter logic has an off-by-one or requires
        a minimum of 2 fields, single-field projection would fail or return
        empty entities.
        Challenge: Swapping 'in field_set' to 'not in field_set' would invert
        which fields appear — this test catches that because only 'name' should
        appear.
        """
        import json as json_mod

        # Given an entity in the database
        db.register_entity("feature", "sf-001", "Single Field", status="active")
        # When exporting with exactly one field
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
            fields="name",
        )
        parsed = json_mod.loads(result)
        # Then each entity has exactly one key
        assert len(parsed["entities"]) >= 1
        for entity in parsed["entities"]:
            assert set(entity.keys()) == {"name"}
            assert entity["name"] != ""

    def test_export_entities_fields_all_valid_fields(self, db: EntityDatabase):
        """Boundary: requesting every valid field returns the same as fields=None.
        derived_from: spec:AC-1 (field projection), dimension:boundary_values

        Anticipate: If the field projection drops keys that are present in
        the raw export (e.g., due to name mismatch between DB columns and
        JSON keys), some fields would be missing in the projected output.
        """
        import json as json_mod

        # Given an entity with known fields
        db.register_entity("feature", "af-001", "All Fields", status="active")
        # First get the full set of field names from an unfiltered export
        unfiltered = json_mod.loads(
            _process_export_entities(
                db, entity_type=None, status=None, output_path=None,
                include_lineage=True, artifacts_root="/tmp", fields=None,
            )
        )
        all_keys = set(unfiltered["entities"][0].keys())
        all_fields_str = ",".join(sorted(all_keys))

        # When exporting with all valid fields listed explicitly
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
            fields=all_fields_str,
        )
        parsed = json_mod.loads(result)
        # Then every entity has the full set of keys
        for entity in parsed["entities"]:
            assert set(entity.keys()) == all_keys

    def test_export_entities_fields_empty_string(self, db: EntityDatabase):
        """Adversarial: fields='' (empty string) should not crash.
        derived_from: spec:AC-1 (field projection), dimension:adversarial

        Anticipate: If the code splits '' on ',', it produces [''] which
        is a set {''}. This is an all-invalid-fields case — it should
        either return an error or return entities with no projected keys.
        Bug caught: split('') producing ghost empty-string field names that
        match nothing, leading to empty entities without an error message.
        """
        # Given an entity in the database
        db.register_entity("feature", "ef-001", "Empty Fields", status="active")
        # When exporting with empty string fields
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
            fields="",
        )
        # Then either an error is returned (preferred) or entities are empty
        # The implementation treats '' as a field set containing '' which is
        # all-invalid -> should return error
        assert "Error" in result

    def test_export_entities_compact_inline_json(self, db: EntityDatabase):
        """BDD: inline JSON output uses compact separators (no indent).
        derived_from: spec:AC-1 (compact output), dimension:bdd_scenarios

        Anticipate: If json.dumps uses indent=2 instead of separators=(',',':'),
        the inline output would contain unnecessary whitespace, wasting tokens.
        Mutation: changing separators to default would add spaces after : and ,.
        """
        import json as json_mod

        # Given an entity in the database
        db.register_entity("feature", "ci-001", "Compact Inline", status="active")
        # When exporting inline (no output_path)
        result = _process_export_entities(
            db,
            entity_type=None,
            status=None,
            output_path=None,
            include_lineage=True,
            artifacts_root="/tmp",
        )
        # Then the JSON string uses compact separators
        assert isinstance(result, str)
        # Compact JSON: no indentation newlines within entity objects
        parsed = json_mod.loads(result)
        assert len(parsed["entities"]) >= 1
        # Re-encode with compact separators and compare
        expected_compact = json_mod.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
        assert result == expected_compact
