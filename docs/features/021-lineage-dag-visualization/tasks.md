# Tasks: Lineage DAG Visualization

**Feature:** 021-lineage-dag-visualization
**Plan:** docs/features/021-lineage-dag-visualization/plan.md

## Phase 1: Sanitization helpers and constants (Plan Step 1)

### Task 1.1: Write tests for `_sanitize_id`
**File:** NEW `plugins/iflow/ui/tests/test_mermaid.py`
**Do:**
- Create test file with imports (`from ui.mermaid import _sanitize_id, _sanitize_label`)
- Write `test_sanitize_id_special_chars`: `_sanitize_id("feature:021-foo")` → matches `feature_021_foo_` + 4 hex chars
- Write `test_sanitize_id_no_collision`: `_sanitize_id("a:b")` != `_sanitize_id("a-b")`
- Write `test_sanitize_id_regex_safe`: result matches `^[a-zA-Z_][a-zA-Z0-9_]*$`
- Write `test_sanitize_id_digit_prefix`: `_sanitize_id("1abc")` starts with `n`
- Write `test_sanitize_id_o_x_prefix`: `_sanitize_id("order")` and `_sanitize_id("xray")` start with `n`
**Done when:** Tests exist and fail with `ImportError` (module not yet created)
**Depends on:** none

### Task 1.2: Write tests for `_sanitize_label`
**File:** EDIT `plugins/iflow/ui/tests/test_mermaid.py`
**Do:**
- Write `test_sanitize_label_quotes`: `'He said "hello"'` → `"He said 'hello'"`
- Write `test_sanitize_label_brackets`: `"feature[0]"` → `"feature(0)"`
- Write `test_sanitize_label_backslash`: `"a\\b"` → `"a/b"`
- Write `test_sanitize_label_less_than`: `"<script>"` → `"&lt;script&gt;"`
- Write `test_sanitize_label_greater_than`: `"a>b"` → `"a&gt;b"`
**Done when:** Tests exist (will fail until implementation)
**Depends on:** Task 1.1 (same file)

### Task 1.3: Implement `_sanitize_id`, `_sanitize_label`, and constants
**File:** NEW `plugins/iflow/ui/mermaid.py`
**Do:**
- Create module with `import re, hashlib`
- Implement `_sanitize_id(type_id: str) -> str`: `re.sub(r"[^a-zA-Z0-9]", "_", type_id)`, prefix `n` if starts with digit/o/x, append `_` + SHA-256[:4] hex of UTF-8 encoded type_id
- Implement `_sanitize_label(text: str) -> str`: chain `.replace('"', "'").replace("[", "(").replace("]", ")").replace("\\", "/").replace("<", "&lt;").replace(">", "&gt;")`
- Define `_ENTITY_TYPE_STYLES` dict: feature→`fill:#1d4ed8,stroke:#3b82f6,color:#fff`, project→`fill:#059669,stroke:#10b981,color:#fff`, brainstorm→`fill:#0891b2,stroke:#22d3ee,color:#fff`, backlog→`fill:#4b5563,stroke:#6b7280,color:#fff`
- Define `_CURRENT_STYLE = "fill:#7c3aed,stroke:#a78bfa,color:#fff,stroke-width:3px"`
- Define `_KNOWN_ENTITY_TYPES = set(_ENTITY_TYPE_STYLES.keys())`
**Done when:** `PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_mermaid.py -v` — all 10 tests pass
**Depends on:** Task 1.2

---

## Phase 2: Mermaid DAG builder function (Plan Step 2)

### Task 2.1: Write tests for `build_mermaid_dag`
**File:** EDIT `plugins/iflow/ui/tests/test_mermaid.py`
**Do:**
- Add `from ui.mermaid import build_mermaid_dag` import
- Helper: `_entity(type_id, name=None, entity_type="feature", parent_type_id=None)` returns dict (note: design.md calls this `_make_entity` — use `_entity` here for brevity)
- Write `test_output_starts_with_flowchart_td`: first line == `"flowchart TD"`
- Write `test_single_entity_no_lineage`: 1 node def, 0 `-->` edges, 0 `click` lines
- Write `test_linear_chain_four_entities`: 4 node defs, 3 edges, 3 click lines (current excluded)
- Write `test_fan_out_multiple_children`: parent with 3 children → 3 edges
- Write `test_current_entity_not_clickable`: no `click` line containing current entity's safe_id
- Write `test_current_entity_gets_current_class`: output contains `class {safe_id} current`
- Write `test_name_none_falls_back_to_type_id`: node label uses type_id when name is None
- Write `test_duplicate_entities_deduped`: same type_id in ancestors+children → count node defs = 1
- Write `test_unknown_entity_type_defaults_feature`: entity_type="custom" → `class {id} feature`
- Write `test_click_handler_uses_href_keyword`: click line matches `click .* href "/entities/.*"`
- Write `test_click_handler_raw_type_id_with_colon`: click line contains `/entities/feature:021`
- Write `test_classdef_lines_emitted`: output contains `classDef feature`, `classDef project`, `classDef brainstorm`, `classDef backlog`, `classDef current` with correct fill values
**Done when:** Tests exist and fail with `ImportError` on `build_mermaid_dag`
**Depends on:** Task 1.3

### Task 2.2: Implement `build_mermaid_dag`
**File:** EDIT `plugins/iflow/ui/mermaid.py`
**Do:**
- Add `build_mermaid_dag(entity: dict, ancestors: list[dict], children: list[dict]) -> str`
- Step 0 (prep): build `all_entities` dict keyed by `type_id` from `ancestors + children + [entity]` (entity last wins)
- Step 1: emit `flowchart TD`
- Step 2: emit node definitions `{safe_id}["{safe_label}"]` for each entity (label = name or type_id)
- Step 3: emit edges `{safe_parent_id} --> {safe_child_id}` where parent_type_id exists in all_entities
- Step 4: emit click handlers `click {safe_id} href "/entities/{type_id}"` for non-current entities
- Step 5: emit classDef blocks for each type in `_ENTITY_TYPE_STYLES` + `classDef current {_CURRENT_STYLE}`
- Step 6: emit class assignments — `class {safe_id} current` for entity, `class {safe_id} {entity_type}` for others (default to `feature` if entity_type not in `_KNOWN_ENTITY_TYPES`)
- Join all lines with `\n`
**Done when:** `PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_mermaid.py -v` — all ~23 tests pass
**Depends on:** Task 2.1

---

## Phase 3: Route integration (Plan Step 3)

### Task 3.1: Add `_seed_entity_with_parent` helper to test file
**File:** EDIT `plugins/iflow/ui/tests/test_entities.py`
**Do:**
- Add `import uuid, sqlite3` if not present
- Add helper function `_seed_entity_with_parent(db_file, type_id, name, entity_type, parent_type_id=None)`:
  - Generate `entity_uuid = str(uuid.uuid4())`
  - If `parent_type_id`: lookup `parent_uuid` via `SELECT uuid FROM entities WHERE type_id = ?`
  - `INSERT OR IGNORE INTO entities (uuid, type_id, entity_type, entity_id, name, status, parent_type_id, parent_uuid) VALUES (...)`
  - Commit and close
- Seed entities in parent-first order in tests
**Done when:** Run `PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_entities.py -v` — all pre-existing tests pass
**Depends on:** Task 2.2

### Task 3.2: Write integration tests for mermaid_dag in route
**File:** EDIT `plugins/iflow/ui/tests/test_entities.py`
**Do:**
- Write `test_entity_detail_has_mermaid_dag`: seed an entity, GET `/entities/{type_id}`, assert `"flowchart TD"` in `response.text`
- Write `test_entity_detail_mermaid_dag_contains_entity_node`: import `_sanitize_id` from `ui.mermaid`, compute `expected_node_id = _sanitize_id(type_id)`, assert `expected_node_id in response.text`
- Write `test_entity_detail_children_depth_beyond_one`: seed grandparent→parent→child→grandchild (parent-first order), GET parent's detail page, assert grandchild's type_id appears in response
**Done when:** Tests exist and fail (route not yet modified)
**Depends on:** Task 3.1

### Task 3.3: Modify entity_detail route
**File:** EDIT `plugins/iflow/ui/routes/entities.py`
**Do:**
- Add `from ui.mermaid import build_mermaid_dag` at top
- Change `db.get_lineage(type_id, "down", 1)` → `db.get_lineage(type_id, "down", 10)`
- After `children = ...` line, add: `mermaid_dag = build_mermaid_dag(entity, ancestors, children)`
- Add `"mermaid_dag": mermaid_dag` to the template context dict
**Done when:** `PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_entities.py -v` — all tests pass (existing + new)
**Depends on:** Task 3.2

---

## Phase 4: Template changes (Plan Step 4)

### Task 4.1: Write template integration tests
**File:** EDIT `plugins/iflow/ui/tests/test_entities.py`
**Do:**
- Write `test_entity_detail_contains_mermaid_pre`: assert `'<pre class="mermaid">'` in response.text
- Write `test_entity_detail_flat_list_in_details`: assert `"<details"` in response.text, assert `'open'` not in the details tag
- Write `test_board_page_no_mermaid_script`: GET `/`, assert `"cdn.jsdelivr.net/npm/mermaid"` not in response.text
- Write `test_entity_list_no_mermaid_script`: GET `/entities`, assert `"cdn.jsdelivr.net/npm/mermaid"` not in response.text
**Done when:** All 4 tests exist. `test_board_page_no_mermaid_script` and `test_entity_list_no_mermaid_script` pass. `test_entity_detail_contains_mermaid_pre` and `test_entity_detail_flat_list_in_details` are expected to fail at this point (template not yet modified) — correct TDD behavior.
**Depends on:** Task 3.3

### Task 4.2: Add Mermaid diagram to entity_detail.html
**File:** EDIT `plugins/iflow/ui/templates/entity_detail.html`
**Do:**
- In the `<!-- Lineage -->` section, add above existing lists: `<pre class="mermaid">{{ mermaid_dag | safe }}</pre>`
- Wrap existing ancestor/children markup in `<details class="mt-3"><summary class="text-sm cursor-pointer text-base-content/50">Show flat list</summary>...existing markup...</details>`
**Done when:** Run `PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_entities.py::test_entity_detail_contains_mermaid_pre plugins/iflow/ui/tests/test_entities.py::test_entity_detail_flat_list_in_details -v` — both tests pass
**Depends on:** Task 4.1

### Task 4.3: Add Mermaid CDN script to entity_detail.html
**File:** EDIT `plugins/iflow/ui/templates/entity_detail.html`
**Do:**
- Add before `{% endblock %}`:
  ```html
  <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
      mermaid.initialize({ startOnLoad: true, securityLevel: 'loose', theme: 'dark' });
  </script>
  ```
**Done when:** `PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/ -v` — all tests pass
**Depends on:** Task 4.2

---

## Phase 5: Browser verification (Plan Step 5)

### Task 5.1: Start UI server and verify Mermaid rendering
**Files:** None modified
**Do:**
- Start server: `PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m ui --port 8718`
- Navigate to an entity detail page with lineage
- Verify: SVG rendered in place of `<pre>`, node colors match entity types, current node is purple with 3px border
- Verify: clicking a non-current node navigates to that entity's detail page
- Verify: hover shows pointer cursor on clickable nodes
- Check: no console errors
**Done when:** All visual checks pass
**Depends on:** Task 4.3

### Task 5.2: Verify no mermaid leakage to other pages
**Files:** None modified
**Do:**
- Navigate to board page (`/`) — verify no mermaid script tag in page source
- Navigate to entity list page (`/entities`) — verify no mermaid script tag in page source
**Done when:** Neither page contains mermaid references
**Depends on:** Task 5.1

---

## Dependency Graph

```
Task 1.1 → Task 1.2 → Task 1.3
                          ↓
Task 2.1 → Task 2.2
              ↓
Task 3.1 → Task 3.2 → Task 3.3
                          ↓
Task 4.1 → Task 4.2 → Task 4.3
                          ↓
Task 5.1 → Task 5.2
```

## Summary

- **14 tasks** across **5 phases**
- **0 parallel groups** (strict linear chain)
- Estimated scope: ~2-3 hours implementation time
- TDD enforced: tests written before implementation in every phase
