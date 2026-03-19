"""Unit tests for Mermaid DAG builder module."""

import re


# ===========================================================================
# Phase 1: _sanitize_id tests (Task 1.1)
# ===========================================================================


def test_sanitize_id_special_chars():
    """feature:021-foo → feature_021_foo_ + 4 hex chars."""
    from ui.mermaid import _sanitize_id

    result = _sanitize_id("feature:021-foo")
    assert result.startswith("feature_021_foo_")
    assert len(result) == len("feature_021_foo_") + 4


def test_sanitize_id_no_collision():
    """Two type_ids differing only in : vs - produce different safe IDs."""
    from ui.mermaid import _sanitize_id

    assert _sanitize_id("a:b") != _sanitize_id("a-b")


def test_sanitize_id_regex_safe():
    """Result matches ^[a-zA-Z_][a-zA-Z0-9_]*$."""
    from ui.mermaid import _sanitize_id

    for tid in ["feature:021-foo", "a:b", "1abc", "order", "xray", "hello"]:
        result = _sanitize_id(tid)
        assert re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", result), f"Failed for {tid}: {result}"


def test_sanitize_id_digit_prefix():
    """type_id starting with digit gets n prefix."""
    from ui.mermaid import _sanitize_id

    result = _sanitize_id("1abc")
    assert result.startswith("n")


def test_sanitize_id_o_x_prefix():
    """type_id starting with o or x gets n prefix."""
    from ui.mermaid import _sanitize_id

    assert _sanitize_id("order").startswith("n")
    assert _sanitize_id("xray").startswith("n")


# ===========================================================================
# Phase 1: _sanitize_label tests (Task 1.2)
# ===========================================================================


def test_sanitize_label_quotes():
    """Double quotes replaced with single quotes."""
    from ui.mermaid import _sanitize_label

    assert _sanitize_label('He said "hello"') == "He said 'hello'"


def test_sanitize_label_brackets():
    """Square brackets replaced with parentheses."""
    from ui.mermaid import _sanitize_label

    assert _sanitize_label("feature[0]") == "feature(0)"


def test_sanitize_label_backslash():
    """Backslash replaced with forward slash."""
    from ui.mermaid import _sanitize_label

    assert _sanitize_label("a\\b") == "a/b"


def test_sanitize_label_less_than():
    """< replaced with &lt;."""
    from ui.mermaid import _sanitize_label

    assert _sanitize_label("<script>") == "&lt;script&gt;"


def test_sanitize_label_greater_than():
    """> replaced with &gt;."""
    from ui.mermaid import _sanitize_label

    assert _sanitize_label("a>b") == "a&gt;b"


# ===========================================================================
# Phase 2: build_mermaid_dag tests (Task 2.1)
# ===========================================================================


def _entity(type_id, name=None, entity_type="feature", parent_type_id=None):
    """Helper to create an entity dict."""
    return {
        "type_id": type_id,
        "name": name,
        "entity_type": entity_type,
        "parent_type_id": parent_type_id,
    }


def test_output_starts_with_flowchart_td():
    """First line is 'flowchart TD'."""
    from ui.mermaid import build_mermaid_dag

    entity = _entity("feature:001", "Test")
    result = build_mermaid_dag(entity, [], [])
    assert result.split("\n")[0] == "flowchart TD"


def test_single_entity_no_lineage():
    """1 node, 0 edges, 0 click lines."""
    from ui.mermaid import build_mermaid_dag, _sanitize_id

    entity = _entity("feature:solo", "Solo")
    result = build_mermaid_dag(entity, [], [])
    lines = result.split("\n")

    safe_id = _sanitize_id("feature:solo")
    node_defs = [l for l in lines if '["' in l and "-->" not in l]
    edges = [l for l in lines if "-->" in l]
    clicks = [l for l in lines if l.strip().startswith("click ")]

    assert len(node_defs) == 1
    assert len(edges) == 0
    assert len(clicks) == 0


def test_linear_chain_four_entities():
    """4 nodes, 3 edges, 3 click lines (current excluded)."""
    from ui.mermaid import build_mermaid_dag

    gp = _entity("project:gp", "Grandparent", "project")
    p = _entity("feature:p", "Parent", "feature", parent_type_id="project:gp")
    current = _entity("feature:c", "Current", "feature", parent_type_id="feature:p")
    child = _entity("feature:ch", "Child", "feature", parent_type_id="feature:c")

    result = build_mermaid_dag(current, [gp, p], [child])
    lines = result.split("\n")

    node_defs = [l for l in lines if '["' in l and "-->" not in l]
    edges = [l for l in lines if "-->" in l]
    clicks = [l for l in lines if l.strip().startswith("click ")]

    assert len(node_defs) == 4
    assert len(edges) == 3
    assert len(clicks) == 3  # current excluded


def test_fan_out_multiple_children():
    """Parent with 3 children → 3 edges."""
    from ui.mermaid import build_mermaid_dag

    parent = _entity("project:p", "Parent", "project")
    c1 = _entity("feature:c1", "C1", "feature", parent_type_id="project:p")
    c2 = _entity("feature:c2", "C2", "feature", parent_type_id="project:p")
    c3 = _entity("feature:c3", "C3", "feature", parent_type_id="project:p")

    result = build_mermaid_dag(parent, [], [c1, c2, c3])
    edges = [l for l in result.split("\n") if "-->" in l]

    assert len(edges) == 3


def test_current_entity_not_clickable():
    """No click line for current entity."""
    from ui.mermaid import build_mermaid_dag, _sanitize_id

    current = _entity("feature:cur", "Current")
    safe_id = _sanitize_id("feature:cur")
    result = build_mermaid_dag(current, [], [])
    clicks = [l for l in result.split("\n") if l.strip().startswith("click ")]

    for click in clicks:
        assert safe_id not in click


def test_current_entity_gets_current_class():
    """Output contains 'class {safe_id} current'."""
    from ui.mermaid import build_mermaid_dag, _sanitize_id

    current = _entity("feature:cur", "Current")
    safe_id = _sanitize_id("feature:cur")
    result = build_mermaid_dag(current, [], [])

    assert f"class {safe_id} current" in result


def test_name_none_falls_back_to_type_id():
    """Node label uses type_id when name is None."""
    from ui.mermaid import build_mermaid_dag, _sanitize_id, _sanitize_label

    current = _entity("feature:unnamed", None)
    result = build_mermaid_dag(current, [], [])
    safe_label = _sanitize_label("feature:unnamed")

    assert f'["{safe_label}"]' in result


def test_duplicate_entities_deduped():
    """Same type_id in ancestors+children → count node defs = 1."""
    from ui.mermaid import build_mermaid_dag

    entity = _entity("feature:main", "Main")
    dup = _entity("feature:dup", "Dup", "feature", parent_type_id="feature:main")

    # Same entity in both ancestors and children
    result = build_mermaid_dag(entity, [dup], [dup])
    lines = result.split("\n")

    node_defs = [l for l in lines if '["' in l and "-->" not in l]
    # Should have 2 unique nodes: main + dup (not 3)
    assert len(node_defs) == 2


def test_unknown_entity_type_defaults_feature():
    """entity_type='custom' → class {id} feature."""
    from ui.mermaid import build_mermaid_dag, _sanitize_id

    current = _entity("feature:main", "Main")
    child = _entity("custom:child", "Child", "custom", parent_type_id="feature:main")

    result = build_mermaid_dag(current, [], [child])
    safe_id = _sanitize_id("custom:child")

    assert f"class {safe_id} feature" in result


def test_click_handler_uses_href_keyword():
    """Click line matches 'click .* href "/entities/.*"'."""
    from ui.mermaid import build_mermaid_dag

    current = _entity("feature:cur", "Current")
    child = _entity("feature:ch", "Child", "feature", parent_type_id="feature:cur")

    result = build_mermaid_dag(current, [], [child])
    clicks = [l for l in result.split("\n") if l.strip().startswith("click ")]

    assert len(clicks) == 1
    assert re.search(r'click .* href "/entities/.*"', clicks[0])


def test_click_handler_raw_type_id_with_colon():
    """Click line contains /entities/feature:021."""
    from ui.mermaid import build_mermaid_dag

    current = _entity("project:p", "P", "project")
    child = _entity("feature:021", "F021", "feature", parent_type_id="project:p")

    result = build_mermaid_dag(current, [], [child])
    clicks = [l for l in result.split("\n") if l.strip().startswith("click ")]

    assert any("/entities/feature:021" in c for c in clicks)


def test_click_handler_url_encodes_double_quote_in_tid():
    """Double-quote in type_id is URL-encoded to %22 in click handler URL.

    Prevents breakout from Mermaid quoted string in click href.
    """
    from ui.mermaid import build_mermaid_dag

    current = _entity("project:p", "P", "project")
    child = _entity('feature:"evil"', "Evil", "feature", parent_type_id="project:p")

    result = build_mermaid_dag(current, [], [child])
    clicks = [l for l in result.split("\n") if l.strip().startswith("click ")]

    # The raw double-quote should NOT appear in the URL portion
    assert any('/entities/feature:%22evil%22' in c for c in clicks)
    # Ensure no unescaped " in the URL (beyond the wrapping quotes)
    for c in clicks:
        url_part = c.split('href "')[1].rsplit('"')[0]
        assert '"' not in url_part, f"Unescaped double-quote in URL: {url_part}"


def test_classdef_lines_emitted():
    """Output contains classDef for feature, project, brainstorm, backlog, current."""
    from ui.mermaid import build_mermaid_dag

    entity = _entity("feature:x", "X")
    result = build_mermaid_dag(entity, [], [])

    assert "classDef feature" in result
    assert "classDef project" in result
    assert "classDef brainstorm" in result
    assert "classDef backlog" in result
    assert "classDef current" in result
    assert "fill:#1d4ed8" in result  # feature fill
    assert "fill:#059669" in result  # project fill
    assert "fill:#0891b2" in result  # brainstorm fill
    assert "fill:#4b5563" in result  # backlog fill
    assert "fill:#7c3aed" in result  # current fill


# ===========================================================================
# Deepened tests: Boundary Value & Equivalence Partitioning
# ===========================================================================


def test_sanitize_id_empty_string():
    """Empty type_id produces a valid Mermaid identifier (no crash).
    derived_from: dimension:boundary_values (empty input)
    """
    # Given an empty type_id string
    from ui.mermaid import _sanitize_id

    # When we sanitize it
    result = _sanitize_id("")

    # Then the result is still a valid Mermaid ID (non-empty, starts with letter/underscore)
    assert len(result) > 0
    assert re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", result), f"Invalid ID: {result}"


def test_sanitize_id_all_special_chars():
    """':::' becomes all underscores + hash suffix.
    derived_from: dimension:boundary_values (all-special input)
    """
    # Given a type_id composed entirely of special characters
    from ui.mermaid import _sanitize_id

    # When we sanitize it
    result = _sanitize_id(":::")

    # Then the base is all underscores and the result is valid
    assert re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", result), f"Invalid ID: {result}"
    # The base portion (before hash) should be underscores only
    base = result.rsplit("_", 1)[0]
    assert all(c == "_" for c in base), f"Expected all underscores in base, got: {base}"


def test_sanitize_id_starts_with_uppercase():
    """Uppercase first char does NOT get 'n' prefix — only digits, 'o', 'x' do.
    derived_from: dimension:boundary_values (uppercase prefix)
    """
    # Given a type_id starting with uppercase letter
    from ui.mermaid import _sanitize_id

    # When we sanitize it
    result = _sanitize_id("Alpha")

    # Then it should NOT start with 'n' prefix
    assert result.startswith("Alpha_"), f"Expected 'Alpha_...' but got: {result}"


def test_sanitize_label_empty_string():
    """Empty string label returns empty string.
    derived_from: dimension:boundary_values (empty input)
    """
    # Given an empty label string
    from ui.mermaid import _sanitize_label

    # When we sanitize it
    result = _sanitize_label("")

    # Then the result is empty
    assert result == ""


def test_sanitize_label_all_special_combined():
    """All escapable characters in a single string are all replaced.
    derived_from: dimension:boundary_values (combined specials)
    """
    # Given a label containing every escapable character
    from ui.mermaid import _sanitize_label

    # When we sanitize a string with all special chars: " [ ] \ < >
    result = _sanitize_label('"hello" [world] a\\b <c>')

    # Then every special char is replaced
    assert result == "'hello' (world) a/b &lt;c&gt;"


def test_hash_suffix_exactly_4_hex():
    """Hash suffix is exactly 4 hex characters after the last underscore.
    derived_from: dimension:mutation_mindset (pin hash length)
    """
    # Given various type_ids
    from ui.mermaid import _sanitize_id

    for tid in ["feature:001", "project:abc", "x", ":::", ""]:
        # When we sanitize each
        result = _sanitize_id(tid)
        # Then the last 4 chars after the final underscore are hex
        parts = result.rsplit("_", 1)
        assert len(parts) == 2, f"Expected underscore separator in: {result}"
        hex_part = parts[1]
        assert len(hex_part) == 4, f"Expected 4 hex chars, got {len(hex_part)}: {hex_part}"
        assert re.match(r"^[0-9a-f]{4}$", hex_part), f"Not hex: {hex_part}"


# ===========================================================================
# Deepened tests: Adversarial / Negative Testing
# ===========================================================================


def test_entity_with_parent_type_id_not_in_all_entities():
    """Orphan parent_type_id should not produce an edge.
    derived_from: dimension:adversarial (orphan parent ref)
    """
    # Given a child entity whose parent_type_id is NOT in ancestors or children
    from ui.mermaid import build_mermaid_dag

    current = _entity("feature:cur", "Current")
    orphan_child = _entity("feature:orphan", "Orphan", "feature", parent_type_id="feature:missing")

    # When we build the DAG
    result = build_mermaid_dag(current, [], [orphan_child])
    edges = [l for l in result.split("\n") if "-->" in l]

    # Then no edge is created for the orphan parent reference
    assert len(edges) == 0, f"Expected 0 edges for orphan parent, got: {edges}"


def test_entity_name_with_mermaid_syntax():
    """Entity name containing --> [] and " chars is safely escaped.
    derived_from: dimension:adversarial (mermaid injection)
    """
    # Given an entity whose name contains Mermaid syntax characters
    from ui.mermaid import build_mermaid_dag

    dangerous_name = 'A --> B ["inject"]'
    current = _entity("feature:danger", dangerous_name)

    # When we build the DAG
    result = build_mermaid_dag(current, [], [])

    # Then the raw dangerous chars should NOT appear in node definitions
    node_lines = [l for l in result.split("\n") if '["' in l and "flowchart" not in l]
    assert len(node_lines) == 1
    # The label should have " replaced with ' and [] replaced with ()
    assert "--&gt;" in node_lines[0] or "-->" not in node_lines[0].split('["')[1]
    assert '"inject"' not in node_lines[0].split('["', 1)[1].rsplit('"]', 1)[0]


def test_current_entity_also_in_ancestors():
    """Current entity appearing in ancestors is deduped; current dict wins.
    derived_from: dimension:adversarial (dedup + current wins)
    """
    # Given the current entity also appears in the ancestors list
    from ui.mermaid import build_mermaid_dag

    current = _entity("feature:dup", "CurrentVersion")
    ancestor_copy = _entity("feature:dup", "AncestorVersion")

    # When we build the DAG
    result = build_mermaid_dag(current, [ancestor_copy], [])
    node_lines = [l for l in result.split("\n") if '["' in l and "-->" not in l]

    # Then only one node def exists (deduped)
    assert len(node_lines) == 1
    # And the current entity's name wins (entity is appended last)
    assert "CurrentVersion" in node_lines[0]


def test_sanitize_id_unicode():
    """Unicode characters in type_id are replaced, result is valid.
    derived_from: dimension:adversarial (unicode input)
    """
    # Given a type_id with unicode characters
    from ui.mermaid import _sanitize_id

    # When we sanitize it
    result = _sanitize_id("feature:café-résumé")

    # Then the result is a valid Mermaid identifier
    assert re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", result), f"Invalid ID: {result}"
    assert len(result) > 4  # At least hash suffix


# ===========================================================================
# Deepened tests: Error Propagation & Failure Modes
# ===========================================================================


def test_build_mermaid_dag_entity_missing_name_key():
    """Entity dict with no 'name' key falls back to type_id for label.
    derived_from: dimension:error_propagation (absent name key)
    """
    # Given an entity dict that has no 'name' key at all
    from ui.mermaid import build_mermaid_dag, _sanitize_label

    entity = {"type_id": "feature:noname", "entity_type": "feature", "parent_type_id": None}

    # When we build the DAG
    result = build_mermaid_dag(entity, [], [])

    # Then it doesn't crash and falls back to type_id as label
    safe_label = _sanitize_label("feature:noname")
    assert f'["{safe_label}"]' in result


# ===========================================================================
# Deepened tests: Mutation Testing Mindset
# ===========================================================================


def test_edge_direction_parent_to_child():
    """Edge goes parent --> child, NOT child --> parent.
    derived_from: dimension:mutation_mindset (direction swap)
    """
    # Given a parent and child entity
    from ui.mermaid import build_mermaid_dag, _sanitize_id

    parent = _entity("project:parent", "Parent", "project")
    child = _entity("feature:child", "Child", "feature", parent_type_id="project:parent")

    parent_id = _sanitize_id("project:parent")
    child_id = _sanitize_id("feature:child")

    # When we build the DAG
    result = build_mermaid_dag(child, [parent], [])
    edges = [l for l in result.split("\n") if "-->" in l]

    # Then the edge direction is parent --> child
    assert len(edges) == 1
    assert edges[0].strip() == f"{parent_id} --> {child_id}"
    # And NOT the reverse
    assert f"{child_id} --> {parent_id}" not in result


def test_entity_dict_wins_over_ancestor_duplicate():
    """When same type_id in ancestors and as current, current entity dict wins.
    derived_from: dimension:mutation_mindset (merge order)
    """
    # Given an ancestor with same type_id but different name than current
    from ui.mermaid import build_mermaid_dag

    ancestor_version = _entity("feature:shared", "OldName")
    current_version = _entity("feature:shared", "NewName")

    # When we build the DAG (entity is current_version)
    result = build_mermaid_dag(current_version, [ancestor_version], [])
    node_lines = [l for l in result.split("\n") if '["' in l and "-->" not in l]

    # Then only one node exists with the current entity's name
    assert len(node_lines) == 1
    assert "NewName" in node_lines[0]
    assert "OldName" not in node_lines[0]
