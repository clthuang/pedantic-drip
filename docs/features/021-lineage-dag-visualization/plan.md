# Plan: Lineage DAG Visualization

**Feature:** 021-lineage-dag-visualization
**Design:** docs/features/021-lineage-dag-visualization/design.md
**Spec:** docs/features/021-lineage-dag-visualization/spec.md

## Build Order

Strict dependency chain: C1 → C2 → C3. Each step follows TDD (test first, then implement).

## Steps

### Step 1: Create `mermaid.py` with `_sanitize_id` and `_sanitize_label`

**Component:** C1 (mermaid.py) — helper functions only
**Files:**
- NEW: `plugins/iflow/ui/mermaid.py` — `_sanitize_id()`, `_sanitize_label()`, module constants (`_ENTITY_TYPE_STYLES`, `_CURRENT_STYLE`, `_KNOWN_ENTITY_TYPES`)
- NEW: `plugins/iflow/ui/tests/test_mermaid.py` — tests for sanitization functions

**Tests (write first):**
- `test_sanitize_id_special_chars` — AC-R1.6: `feature:021-foo` → `feature_021_foo_XXXX`
- `test_sanitize_id_no_collision` — AC-R1.7: different inputs → different outputs
- `test_sanitize_id_regex_safe` — AC-R1.8: result matches `^[a-zA-Z_][a-zA-Z0-9_]*$`
- `test_sanitize_id_digit_prefix` — type_id starting with digit gets `n` prefix
- `test_sanitize_id_o_x_prefix` — type_id starting with `o` or `x` gets `n` prefix (Mermaid reserved)
- `test_sanitize_label_quotes` — AC-R1.9: `"` → `'`
- `test_sanitize_label_brackets` — AC-R1.10: `[]` → `()`
- `test_sanitize_label_backslash` — `\` → `/`
- `test_sanitize_label_ampersand` — `&` → `&amp;` (defense-in-depth for Jinja2 `| safe`)

**Implementation:**
- `_sanitize_id`: `re.sub` + digit/o/x prefix + SHA-256 hash suffix (4 hex chars, UTF-8 encoded)
- `_sanitize_label`: chained `.replace()` calls (including `&` → `&amp;` to prevent HTML injection when rendered with `| safe`)
- Constants: `_ENTITY_TYPE_STYLES` dict, `_CURRENT_STYLE` string, `_KNOWN_ENTITY_TYPES` set

**Dependencies:** None (pure stdlib: `re`, `hashlib`)
**Verification:** `PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_mermaid.py -v`

---

### Step 2: Implement `build_mermaid_dag` function

**Component:** C1 (mermaid.py) — main builder function
**Files:**
- EDIT: `plugins/iflow/ui/mermaid.py` — add `build_mermaid_dag()`
- EDIT: `plugins/iflow/ui/tests/test_mermaid.py` — add builder function tests

**Tests (write first):**
- `test_output_starts_with_flowchart_td` — AC-R1.1: first line is `flowchart TD`
- `test_single_entity_no_lineage` — AC-R1.2: 1 node, 0 edges, 0 clicks
- `test_linear_chain_four_entities` — AC-R1.3: 4 nodes, 3 edges, 3 clicks
- `test_fan_out_multiple_children` — multiple children produce correct edges
- `test_current_entity_not_clickable` — AC-R1.4: no `click` line for current entity
- `test_current_entity_gets_current_class` — AC-R1.4: `class ... current` for current
- `test_name_none_falls_back_to_type_id` — AC-R1.5: type_id used as label
- `test_duplicate_entities_deduped` — same type_id in ancestors+children → 1 node
- `test_unknown_entity_type_defaults_feature` — AC-R4.3: unknown type → `feature` class
- `test_click_handler_uses_href_keyword` — click line contains `href "/entities/..."`
- `test_click_handler_raw_type_id_with_colon` — type_id with colon appears unencoded in URL
- `test_classdef_lines_emitted` — output contains all 5 classDef lines (feature, project, brainstorm, backlog, current) with correct fill values

**Implementation:**
- 1 prep step + 6 emission steps per design
- Dict merge: `ancestors + children + [entity]` (entity last wins)
- Click: `click {safe_id} href "/entities/{tid}"` — contingency: if Step 5 browser verification reveals Mermaid fails to parse colons in relative URLs, URL-encode the type_id (`feature%3A021-foo`); FastAPI's path parameter decodes automatically
- Class: `current` for entity, `entity_type` (default `feature`) for others

**Dependencies:** Step 1 (uses `_sanitize_id`, `_sanitize_label`, constants)
**Verification:** `PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_mermaid.py -v`

---

### Step 3: Route integration — depth change + mermaid_dag context

**Component:** C2 (entities.py route)
**Files:**
- EDIT: `plugins/iflow/ui/routes/entities.py` — import `build_mermaid_dag`, change depth 1→10, add `mermaid_dag` to context
- EDIT: `plugins/iflow/ui/tests/test_entities.py` — add integration tests

**Tests (write first):**
- `test_entity_detail_has_mermaid_dag` — AC-R2.1: `response.text` contains `flowchart TD` (validates mermaid_dag passed to template and rendered)
- `test_entity_detail_mermaid_dag_contains_entity_node` — AC-R2.1: `response.text` contains entity's sanitized node ID
- `test_entity_detail_children_depth_beyond_one` — AC-R2.2: grandchildren present in response
- Add `_seed_entity_with_parent(db_file, ...)` helper to test file (sets both `parent_type_id` and `parent_uuid`)

**Note:** Seed entities in parent-first order (project → brainstorm → feature) so `parent_uuid` lookup resolves correctly.

**Implementation:**
1. Add import: `from ui.mermaid import build_mermaid_dag`
2. Change `db.get_lineage(type_id, "down", 1)` → `db.get_lineage(type_id, "down", 10)` — note: this also affects the flat children list in `<details>` fallback (now shows all descendants without nesting; accepted trade-off per design)
3. Add `mermaid_dag = build_mermaid_dag(entity, ancestors, children)` after lineage computation
4. Add `"mermaid_dag": mermaid_dag` to template context dict

**Dependencies:** Step 2 (imports `build_mermaid_dag`)
**Verification:** `PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_entities.py -v`

---

### Step 4: Template changes — Mermaid diagram + flat list fallback

**Component:** C3 (entity_detail.html template)
**Files:**
- EDIT: `plugins/iflow/ui/templates/entity_detail.html` — add `<pre class="mermaid">`, wrap lists in `<details>`, add Mermaid CDN script
- EDIT: `plugins/iflow/ui/tests/test_entities.py` — add template integration tests

**Tests (write first):**
- `test_entity_detail_contains_mermaid_pre` — AC-R3.1: `<pre class="mermaid">` in response
- `test_entity_detail_flat_list_in_details` — AC-R3.2: `<details>` wrapping lists, no `open` attribute
- `test_board_page_no_mermaid_script` — AC-R3.4: board page has no mermaid references
- `test_entity_list_no_mermaid_script` — AC-R3.5: entity list has no mermaid references

**Implementation:**
1. Replace Lineage card content (the `<!-- Lineage -->` section):
   - Add `<pre class="mermaid">{{ mermaid_dag | safe }}</pre>` above existing lists (Jinja2 autoescaping is enabled by default in Starlette — `| safe` required to prevent `-->` being escaped to `--&gt;`; safe because `_sanitize_label` strips dangerous characters and entity data is internal)
   - Wrap existing ancestor/children markup in `<details class="mt-3">` with summary
2. Add Mermaid CDN script before `{% endblock %}`:
   ```html
   <script type="module">
       import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
       mermaid.initialize({ startOnLoad: true, securityLevel: 'loose', theme: 'dark' });
   </script>
   ```

**Dependencies:** Step 3 (template receives `mermaid_dag` from route)
**Verification:** `PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/ -v`

---

### Step 5: Browser verification (Playwright MCP)

**Component:** All (end-to-end)
**Files:** None modified — manual verification only

**Checks:**
- Start UI server: `PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m ui --port 8718`
- Navigate to entity detail page → verify SVG rendered in place of `<pre>`
- Click a non-current node → verify navigation to that entity's detail page
- Verify node colors match entity type (blue=feature, green=project, cyan=brainstorm, gray=backlog)
- Verify current entity node is purple with 3px border
- Verify hover cursor shows pointer on clickable nodes
- Check no console errors
- Verify board page (`/`) has no mermaid script
- Verify entity list page (`/entities`) has no mermaid script

**Dependencies:** Steps 1-4 all complete
**Verification:** Playwright MCP browser tools. Fallback: manually start UI server and verify in browser if Playwright MCP is unavailable.

## Dependency Graph

```
Step 1: _sanitize_id + _sanitize_label + constants
  ↓
Step 2: build_mermaid_dag (depends on Step 1 functions)
  ↓
Step 3: Route integration (imports Step 2 function)
  ↓
Step 4: Template changes (receives context from Step 3)
  ↓
Step 5: Browser verification (all steps complete)
```

## Risk Mitigations Applied

- **TDD order:** Tests written before implementation in each step
- **Incremental verification:** Each step runs its own test suite before proceeding
- **Integration test seeding:** `_seed_entity_with_parent` sets both `parent_type_id` and `parent_uuid` for `get_lineage()` CTE traversal
- **Mermaid reserved IDs:** `_sanitize_id` prefixes `n` for digit/o/x starts
- **Click handler:** Uses `href` keyword for explicit URL link syntax
- **Dict merge order:** `ancestors + children + [entity]` ensures entity dict wins
- **Jinja2 autoescaping:** Template uses `| safe` filter; `_sanitize_label` handles `&` → `&amp;` as defense-in-depth
- **Seed ordering:** Integration tests seed entities parent-first so `parent_uuid` lookup resolves
