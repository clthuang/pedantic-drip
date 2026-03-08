# Spec: Lineage DAG Visualization

**Feature:** 021-lineage-dag-visualization
**PRD:** docs/brainstorms/20260308-075713-lineage-dag-visualization.prd.md

## Overview

Add a Mermaid.js-rendered DAG diagram to the entity detail page's Lineage section. Nodes represent entities, edges represent parent→child relationships, and clicking a node navigates to that entity's detail page. The existing flat lists are preserved as a collapsed fallback.

## Scope Boundaries

**In scope:**
- Server-side Mermaid flowchart string generation (`build_mermaid_dag`)
- Client-side rendering via Mermaid.js CDN (lazy-loaded on detail page only)
- Clickable nodes using URL link syntax with `securityLevel: 'loose'` (safe — only URL strings emitted, no JS callbacks)
- Entity type color coding + current node highlighting
- Increase children depth from 1 to 10
- Collapsed `<details>` fallback for flat ancestor/children lists

**Out of scope:**
- Dedicated `/lineage` route
- Editing relationships from UI
- Server-side SVG rendering
- Pagination, sorting, or graph layout controls

## Requirements

### R1: Mermaid DAG Builder Module

**New file:** `plugins/iflow/ui/mermaid.py`

**Functions:**

#### `build_mermaid_dag(entity: dict, ancestors: list[dict], children: list[dict]) -> str`

Generates a Mermaid `flowchart TD` definition string.

**Input contract:**
- `entity`: dict with keys `type_id` (str), `name` (str|None), `entity_type` (str)
- `ancestors`: list of entity dicts (root-first order, self already stripped)
- `children`: list of entity dicts (BFS order, self already stripped)
- Each entity dict must have: `type_id`, `name` (optional), `entity_type`, `parent_type_id` (optional)

**Output:** Multi-line string starting with `flowchart TD\n`.

**Behavior:**
1. Build `all_entities` dict keyed by `type_id` from `ancestors + [entity] + children` (deduplication via dict merge)
2. Emit node definitions: `{safe_id}["{safe_label}"]` for each entity
3. Emit edges: `{safe_parent_id} --> {safe_child_id}` where `parent_type_id` exists in `all_entities`
4. Emit click handlers: `click {safe_id} "/entities/{type_id}"` (URL link syntax, no tooltip/target needed) for every entity EXCEPT the current one
5. Emit classDef blocks for entity types + `current` style
6. Emit class assignments: `current` for the entity itself, entity_type for all others. Unknown `entity_type` values default to `feature` class

**AC:**
- AC-R1.1: Output starts with `flowchart TD` and contains structurally valid node/edge/class definitions (testable via string assertions)
- AC-R1.2: Single entity (no lineage) → output contains exactly 1 node, 0 edges, 0 click handlers
- AC-R1.3: Linear chain of 4 entities → 4 nodes, 3 edges, 3 click handlers (current excluded)
- AC-R1.4: Current entity gets class `current`, not a click handler
- AC-R1.5: Entity with `name=None` uses `type_id` as label fallback

#### `_sanitize_id(type_id: str) -> str`

Converts a type_id into a Mermaid-safe node identifier.

**Rules:**
1. Replace any character NOT in `[a-zA-Z0-9]` with `_`
2. If result starts with a digit, prefix with `n`
3. Append `_` + first 4 hex chars of SHA-256 hash of original `type_id` (UTF-8 encoded) to prevent collisions

**AC:**
- AC-R1.6: `feature:021-foo` → `feature_021_foo_XXXX` (4-char hash suffix)
- AC-R1.7: Two type_ids differing only in `:` vs `-` produce different safe IDs (hash differs)
- AC-R1.8: Result matches regex `^[a-zA-Z_][a-zA-Z0-9_]*$`

#### `_sanitize_label(text: str) -> str`

Escapes characters that would break Mermaid node labels inside double quotes.

**Rules:**
1. Replace `"` with `'` (single quote)
2. Replace `[` and `]` with `(` and `)` respectively
3. Replace `\` with `/`

**AC:**
- AC-R1.9: `He said "hello"` → `He said 'hello'`
- AC-R1.10: `feature[0]` → `feature(0)`

### R2: Route Changes

**File:** `plugins/iflow/ui/routes/entities.py`

**Changes:**

1. **Increase children depth:** In the `entity_detail` route function, change `db.get_lineage(type_id, "down", 1)` to `db.get_lineage(type_id, "down", 10)`. Entity hierarchies are typically <50 nodes, so depth=10 is well within performance bounds.

2. **Generate mermaid_dag:** After computing `ancestors` and `children`, call:
   ```python
   from ui.mermaid import build_mermaid_dag
   mermaid_dag = build_mermaid_dag(entity, ancestors, children)
   ```

3. **Add to context:** Add `"mermaid_dag": mermaid_dag` to the template context dict returned by `entity_detail()`

**AC:**
- AC-R2.1: Entity detail context contains `mermaid_dag` key with non-empty string value
- AC-R2.2: Children lineage fetched with depth=10
- AC-R2.3: No changes to entity list route or board route

### R3: Template Changes

**File:** `plugins/iflow/ui/templates/entity_detail.html`

**Changes to Lineage card (the `<!-- Lineage -->` section in entity_detail.html):**

1. Add Mermaid diagram above the existing lineage lists:
   ```html
   <pre class="mermaid">{{ mermaid_dag }}</pre>
   ```

2. Wrap existing ancestor/children lists in collapsed `<details>`:
   ```html
   <details class="mt-3">
       <summary class="text-sm cursor-pointer text-base-content/50">Show flat list</summary>
       {existing ancestor + children markup}
   </details>
   ```

3. Add Mermaid.js lazy-load script at bottom of `{% block content %}`:
   ```html
   <script type="module">
       import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
       mermaid.initialize({
           startOnLoad: true,
           securityLevel: 'loose',
           theme: 'dark'
       });
   </script>
   ```

   **Rendering notes:**
   - `startOnLoad: true` causes Mermaid to scan the DOM for `<pre class="mermaid">` elements on page load, render them to SVG, and bind click handlers automatically. No manual `mermaid.run()` or `bindFunctions()` call is needed for full-page loads.
   - `securityLevel: 'loose'` is required for click URL links to be interactive. This is safe because we only emit URL strings (no JS callbacks) in the Mermaid definition.
   - Before Mermaid initializes, the raw flowchart text is briefly visible in the `<pre>` block. This is acceptable — the text is human-readable and renders within ~200ms on typical hardware.
   - Note: PRD assumed URL links work without `securityLevel: 'loose'`; Mermaid docs confirm click functionality requires `loose` or `antiscript` level regardless of syntax.

**AC:**
- AC-R3.1: Entity detail page contains `<pre class="mermaid">` element
- AC-R3.2: Flat lists are inside a `<details>` element, collapsed by default
- AC-R3.3: Mermaid.js CDN script appears only in entity_detail.html, not in base.html
- AC-R3.4: Board page (`/`) HTML does not contain `mermaid` script references
- AC-R3.5: Entity list page (`/entities`) HTML does not contain `mermaid` script references
- AC-R3.6: Clicking a non-current node in the rendered DAG navigates to that entity's detail page (browser verification)

### R4: Color Scheme

**Entity type → Mermaid classDef mapping:**

| Entity Type | Fill | Stroke | Text | Hex Values |
|-------------|------|--------|------|------------|
| feature | blue | light blue | white | `fill:#1d4ed8,stroke:#3b82f6,color:#fff` |
| project | green | light green | white | `fill:#059669,stroke:#10b981,color:#fff` |
| brainstorm | cyan | light cyan | white | `fill:#0891b2,stroke:#22d3ee,color:#fff` |
| backlog | gray | light gray | white | `fill:#4b5563,stroke:#6b7280,color:#fff` |
| current (overlay) | purple | light purple | white | `fill:#7c3aed,stroke:#a78bfa,color:#fff,stroke-width:3px` |

**AC:**
- AC-R4.1: All 4 entity types have distinct fill colors
- AC-R4.2: Current entity uses `current` class (purple, 3px border) regardless of entity_type
- AC-R4.3: Unknown entity_type defaults to `feature` styling
- AC-R4.4: All fill/text color combinations provide sufficient contrast for legibility on dark backgrounds (white text on saturated fills — traces PRD AC-12)

## Error Handling

- **Mermaid CDN fails to load:** Flat list remains visible inside `<details>` (collapsed but expandable). No JavaScript error handling needed — the `<pre class="mermaid">` simply shows raw text, which is still readable as a text-based diagram.
- **Empty lineage (orphan entity):** `build_mermaid_dag` returns a single-node diagram. No edges, no click handlers. The `<details>` flat list shows "No parent" / "No children" as before.
- **Entity with no name:** Label falls back to `type_id`. Both `_sanitize_label` and display remain functional.

## Files Modified

| File | Type | Changes |
|------|------|---------|
| `plugins/iflow/ui/mermaid.py` | NEW | `build_mermaid_dag`, `_sanitize_id`, `_sanitize_label` |
| `plugins/iflow/ui/routes/entities.py` | EDIT | Import mermaid builder, depth 1→10, add `mermaid_dag` to context |
| `plugins/iflow/ui/templates/entity_detail.html` | EDIT | Add `<pre class="mermaid">`, wrap lists in `<details>`, add Mermaid CDN script |
| `plugins/iflow/ui/tests/test_mermaid.py` | NEW | Unit tests for all 3 functions |
| `plugins/iflow/ui/tests/test_entities.py` | EDIT | Integration tests for mermaid context + deeper children |

## Test Plan

### Unit Tests (`test_mermaid.py`)

| Test | Validates |
|------|-----------|
| `test_single_entity_no_lineage` | AC-R1.2: 1 node, 0 edges, 0 clicks |
| `test_linear_chain_four_entities` | AC-R1.3: 4 nodes, 3 edges, 3 clicks |
| `test_fan_out_multiple_children` | Multiple children produce correct edges |
| `test_current_entity_not_clickable` | AC-R1.4: no `click` line for current entity |
| `test_current_entity_gets_current_class` | AC-R1.4: `class ... current` for current |
| `test_name_none_falls_back_to_type_id` | AC-R1.5: type_id used as label |
| `test_sanitize_id_special_chars` | AC-R1.6: colons, dashes replaced |
| `test_sanitize_id_no_collision` | AC-R1.7: different inputs → different outputs |
| `test_sanitize_id_regex_safe` | AC-R1.8: matches `^[a-zA-Z_]...` |
| `test_sanitize_label_quotes` | AC-R1.9: `"` → `'` |
| `test_sanitize_label_brackets` | AC-R1.10: `[]` → `()` |
| `test_output_starts_with_flowchart_td` | AC-R1.1: first line is `flowchart TD` |
| `test_duplicate_entities_deduped` | Same type_id in ancestors+children → 1 node |
| `test_unknown_entity_type_defaults_feature` | AC-R4.3 |

### Integration Tests (additions to `test_entities.py`)

| Test | Validates |
|------|-----------|
| `test_entity_detail_contains_mermaid_pre` | AC-R3.1 |
| `test_board_page_no_mermaid_script` | AC-R3.4 |
| `test_entity_list_no_mermaid_script` | AC-R3.5 |
| `test_entity_detail_context_has_mermaid_dag` | AC-R2.1 |
| `test_entity_detail_mermaid_dag_contains_entity_node` | AC-R2.1: mermaid_dag string contains sanitized node ID for the entity |
| `test_entity_detail_children_depth_beyond_one` | AC-R2.2: mermaid_dag or children list contains grandchildren (depth>1 entities) |

### Browser Verification (Playwright MCP)

| Check | Validates |
|-------|-----------|
| Entity detail → SVG rendered | Mermaid initializes correctly |
| Click non-current node → navigates | AC-5 click navigation |
| Node colors match entity type | AC-R4.1 |
| Current node visually distinct | AC-R4.2 |
| Hover shows pointer on clickable | AC-7 |
| No console errors | Clean integration |
