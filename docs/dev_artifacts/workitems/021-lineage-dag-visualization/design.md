# Design: Lineage DAG Visualization

**Feature:** 021-lineage-dag-visualization
**Spec:** docs/features/021-lineage-dag-visualization/spec.md
**PRD:** docs/brainstorms/20260308-075713-lineage-dag-visualization.prd.md

## Prior Art Research

**Codebase patterns:**
- No existing Mermaid usage in the codebase — first integration
- `get_lineage()` returns `list[dict]` with full entity rows including `parent_type_id` for edge inference
- Route already fetches ancestors (depth=10) and children (depth=1), strips self via `_strip_self_from_lineage()`
- UI test pattern: `_StubDB` classes for unit tests, `TestClient(app)` with real DB for integration
- `_seed_entity()` helper doesn't set `parent_type_id` — integration tests need custom seeding
- `conftest.py` already adds both `plugins/iflow` and `plugins/iflow/hooks/lib` to sys.path

**External research:**
- Mermaid v11 ESM CDN import is the standard pattern for browser-side rendering
- `securityLevel: 'loose'` confirmed required for click handlers (GitHub issue #6809 — fails silently at default `strict`)
- Reserved node IDs: bare `end`, IDs starting with `o` or `x` can create special edge types — hash suffix in `_sanitize_id` prevents collision
- Pure string-template generation is idiomatic Python — no library dependency needed
- Dark theme: `theme: 'dark'` with `darkMode: true` for correct derived colors; only hex codes in `themeVariables`
- Label escaping: double-quoted labels (`node["label"]`) handle most special characters

## Architecture Overview

### Component Topology

```
┌─────────────────────────────────────┐
│  entity_detail route (entities.py)  │
│  - fetches lineage (depth=10)       │
│  - calls build_mermaid_dag()        │
│  - passes mermaid_dag string        │
└──────────┬──────────────────────────┘
           │ mermaid_dag: str
           ▼
┌─────────────────────────────────────┐
│  entity_detail.html (template)      │
│  - <pre class="mermaid">            │
│  - <details> fallback flat lists    │
│  - <script> Mermaid CDN init        │
└─────────────────────────────────────┘
           ▲
           │ import (ESM)
┌─────────────────────────────────────┐
│  Mermaid.js CDN (v11)               │
│  - startOnLoad: true                │
│  - securityLevel: 'loose'           │
│  - theme: 'dark'                    │
└─────────────────────────────────────┘
```

**Data flow:** DB → `get_lineage()` → route → `build_mermaid_dag()` → template context → Jinja2 render → browser → Mermaid.js → SVG

### Components

#### C1: Mermaid DAG Builder (`plugins/iflow/ui/mermaid.py`)

**Responsibility:** Pure function module — converts entity lineage data into Mermaid flowchart syntax. Zero dependencies on FastAPI, Jinja2, or any web framework.

**Design rationale:** Separate module (not inline in route) because:
1. Unit-testable without web framework overhead
2. Single Responsibility — string generation is distinct from HTTP handling
3. Reusable if other routes/views need Mermaid diagrams later

**Internal structure:**
- `build_mermaid_dag()` — public entry point, orchestrates the 6-step emission pipeline
- `_sanitize_id()` — private, converts type_id to Mermaid-safe identifier
- `_sanitize_label()` — private, escapes Mermaid-breaking characters in labels
- `_ENTITY_TYPE_STYLES` — module-level dict constant mapping entity_type → classDef CSS
- `_CURRENT_STYLE` — module-level string constant for the current entity highlight
- `_KNOWN_ENTITY_TYPES` — set of valid entity types for default fallback

#### C2: Route Integration (`plugins/iflow/ui/routes/entities.py`)

**Responsibility:** Orchestrates data fetching and template rendering. Changes are minimal — 3 lines added.

**Design rationale:** Keep `build_mermaid_dag` call inside the existing `try/except` block so any generation errors are caught by the existing error handler.

#### C3: Template Changes (`plugins/iflow/ui/templates/entity_detail.html`)

**Responsibility:** Renders the Mermaid diagram and provides fallback.

**Design rationale:**
- `<pre class="mermaid">` is the standard Mermaid auto-discovery element
- `<details>` fallback keeps flat lists accessible when CDN fails
- Script tag at bottom of `{% block content %}` — page-scoped, not in base.html

### Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Mermaid generation | Server-side string (Python) | Unit-testable, no client-side computation, template just renders `{{ mermaid_dag }}` |
| Mermaid loading | CDN ESM import | No build step, lazy-loaded per page, ~760KB but cached by browser |
| Click handling | URL link syntax + `securityLevel: 'loose'` | URL links are the simplest click pattern; `loose` is required (confirmed by Mermaid docs + GitHub issue #6809); safe because we only emit URL strings |
| ID sanitization | Regex replace + SHA-256 hash suffix | Prevents collision between type_ids that differ only in special characters (e.g., `feature:foo` vs `feature-foo`) |
| Color scheme | Inline `classDef` per diagram | No external CSS needed; colors are Tailwind palette hex values matching the app's design system |
| Unknown entity_type | Default to `feature` classDef | Safe fallback; `feature` is the most common type |
| Python library | None (pure string builder) | `mermaid-py` and `python_mermaid` add dependency for a simple string concatenation task |
| `darkMode` config | `theme: 'dark'` only (no `darkMode: true`) | `darkMode: true` is only needed with `theme: 'base'` + `themeVariables`; `theme: 'dark'` applies full dark preset |

### Risks

| Risk | Mitigation |
|------|------------|
| Reserved Mermaid node IDs (`end`, IDs starting with `o`/`x`) | `_sanitize_id()` prefixes with `n` if the sanitized base starts with a digit, `o`, or `x`, and appends a 4-char hash suffix — eliminating bare reserved IDs like `end` (→ `end_XXXX`) and reserved-prefix IDs like `o_foo` (→ `no_foo_XXXX`) |
| CDN unavailable | Raw Mermaid text in `<pre>` is still human-readable; flat list in `<details>` is expandable |
| Large graphs (>50 nodes) | Depth=10 on entity hierarchies typically yields <50 nodes; Mermaid handles hundreds of nodes |
| HTMX partial navigation breaks Mermaid | Current detail page is full-page load; if HTMX partial nav is added later, `htmx:afterSwap` → `mermaid.run()` will be needed |
| Flat children list shows all descendants | With depth=10, the fallback flat list shows all descendants without hierarchy nesting. Accepted trade-off — the DAG is the primary view, flat list is a CDN-failure fallback |
| ESM module load timing | `startOnLoad: true` calls `mermaid.run()` internally after `initialize()`. ESM modules execute after DOM is ready, so `<pre class="mermaid">` elements are already present. Mermaid detects and processes existing elements even when initialize runs after DOMContentLoaded. If issues arise, fallback: call `await mermaid.run()` explicitly after `initialize()` |

## Interfaces

### C1: Mermaid DAG Builder API

#### `build_mermaid_dag(entity, ancestors, children) -> str`

```python
def build_mermaid_dag(
    entity: dict,
    ancestors: list[dict],
    children: list[dict],
) -> str:
    """Build Mermaid flowchart TD definition from lineage data.

    Args:
        entity: Current entity dict. Required keys: type_id, name, entity_type.
        ancestors: Ancestor entities, root-first order, self already stripped.
            Required keys per item: type_id, name, entity_type, parent_type_id.
        children: Child entities, BFS order, self already stripped.
            Required keys per item: type_id, name, entity_type, parent_type_id.

    Returns:
        Multi-line Mermaid flowchart definition string starting with "flowchart TD".
    """
```

**Pre-condition:** `ancestors` and `children` must not contain the entity itself (ensured by `_strip_self_from_lineage()` in the route).

**Emission pipeline (1 prep step + 6 emission steps, all appending to a `lines: list[str]`):**

1. **Header:** `"flowchart TD"`
2. **Build `all_entities`:** `{e["type_id"]: e for e in ancestors + children + [entity]}` — entity dict is last, so it wins on any duplicate `type_id` (defensive against data anomalies).
3. **Nodes:** For each entity in `all_entities` (deduped by `type_id`):
   ```
       {_sanitize_id(tid)}["{_sanitize_label(name or tid)}"]
   ```
4. **Edges:** For each entity with `parent_type_id` present in `all_entities`:
   ```
       {_sanitize_id(parent_type_id)} --> {_sanitize_id(tid)}
   ```
5. **Click handlers:** For each entity EXCEPT current:
   ```
       click {_sanitize_id(tid)} href "/entities/{tid}"
   ```
   Uses `href` keyword for explicit URL link syntax (both `click A "url"` and `click A href "url"` work in Mermaid v11, but `href` is more explicit and future-proof). Type IDs containing special URL characters (colons, etc.) are safe because FastAPI's `{identifier:path}` route parameter handles them, and Mermaid treats the quoted string as an opaque URL.
6. **Class definitions:** 5 `classDef` lines (feature, project, brainstorm, backlog, current)
7. **Class assignments:** For each entity:
   ```
       class {_sanitize_id(tid)} {cls}
   ```
   Where `cls` = `"current"` if `tid == entity["type_id"]`, else `entity_type` (defaulting to `"feature"` for unknown types).

**Return:** `"\n".join(lines)`

#### `_sanitize_id(type_id: str) -> str`

```python
def _sanitize_id(type_id: str) -> str:
    """Convert type_id to Mermaid-safe node identifier.

    Rules:
    1. Replace non-alphanumeric chars with '_'
    2. Prefix with 'n' if starts with digit, 'o', or 'x' (Mermaid reserved prefixes)
    3. Append '_' + first 4 hex chars of SHA-256(type_id.encode('utf-8'))
    """
```

**Implementation:**
```python
import hashlib
import re

def _sanitize_id(type_id: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]", "_", type_id)
    if base and (base[0].isdigit() or base[0] in ("o", "x")):
        base = "n" + base
    suffix = hashlib.sha256(type_id.encode("utf-8")).hexdigest()[:4]
    return f"{base}_{suffix}"
```

**Edge cases:** `type_id = ":::"` → base = `"___"`, result = `"____XXXX"` (valid). `type_id = ""` → base = `""`, result = `"_XXXX"` (starts with `_`, valid per regex). Empty type_id is not expected in practice but handled safely.

#### `_sanitize_label(text: str) -> str`

```python
def _sanitize_label(text: str) -> str:
    """Escape Mermaid-breaking characters in node labels.

    Replacements: " → ', [ → (, ] → ), \\ → /
    """
    return text.replace('"', "'").replace("[", "(").replace("]", ")").replace("\\", "/")
```

#### Module-Level Constants

```python
_ENTITY_TYPE_STYLES: dict[str, str] = {
    "feature": "fill:#1d4ed8,stroke:#3b82f6,color:#fff",
    "project": "fill:#059669,stroke:#10b981,color:#fff",
    "brainstorm": "fill:#0891b2,stroke:#22d3ee,color:#fff",
    "backlog": "fill:#4b5563,stroke:#6b7280,color:#fff",
}

_CURRENT_STYLE: str = "fill:#7c3aed,stroke:#a78bfa,color:#fff,stroke-width:3px"

_KNOWN_ENTITY_TYPES: set[str] = set(_ENTITY_TYPE_STYLES.keys())
```

### C2: Route Integration

**File:** `plugins/iflow/ui/routes/entities.py`

**Change 1** — Import at top of file:
```python
from ui.mermaid import build_mermaid_dag
```

**Change 2** — In `entity_detail()`, change children depth (line 162):
```python
# Before:
child_lineage = db.get_lineage(type_id, "down", 1)
# After:
child_lineage = db.get_lineage(type_id, "down", 10)
```

**Change 3** — In `entity_detail()`, add mermaid_dag generation after children computation (after line 163):
```python
mermaid_dag = build_mermaid_dag(entity, ancestors, children)
```

**Change 4** — Add to template context dict (in the return statement):
```python
"mermaid_dag": mermaid_dag,
```

### C3: Template Changes

**File:** `plugins/iflow/ui/templates/entity_detail.html`

**Change 1** — Replace the Lineage card content (lines 69-102). New structure:

```html
<!-- Lineage -->
<div class="card bg-base-200 shadow-sm p-4">
    <h2 class="text-lg font-bold mb-3">Lineage</h2>
    <pre class="mermaid">{{ mermaid_dag }}</pre>
    <details class="mt-3">
        <summary class="text-sm cursor-pointer text-base-content/50">Show flat list</summary>
        <div class="mt-2">
            <div class="mb-3">
                <h3 class="text-sm font-semibold mb-1">Ancestors</h3>
                {% if ancestors %}
                <ul class="list-disc list-inside text-sm">
                    {% for a in ancestors %}
                    <li>
                        <a href="/entities/{{ a.type_id }}" class="link link-primary">{{ a.name or a.type_id }}</a>
                        <span class="badge badge-xs badge-outline">{{ a.entity_type }}</span>
                    </li>
                    {% endfor %}
                </ul>
                {% else %}
                <p class="text-sm text-base-content/50">No parent</p>
                {% endif %}
            </div>
            <div>
                <h3 class="text-sm font-semibold mb-1">Children</h3>
                {% if children %}
                <ul class="list-disc list-inside text-sm">
                    {% for c in children %}
                    <li>
                        <a href="/entities/{{ c.type_id }}" class="link link-primary">{{ c.name or c.type_id }}</a>
                        <span class="badge badge-xs badge-outline">{{ c.entity_type }}</span>
                    </li>
                    {% endfor %}
                </ul>
                {% else %}
                <p class="text-sm text-base-content/50">No children</p>
                {% endif %}
            </div>
        </div>
    </details>
</div>
```

**Change 2** — Add Mermaid CDN script at the end of `{% block content %}`, before `{% endblock %}`:

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

### Test Architecture

#### Unit Tests (`test_mermaid.py`)

**No web framework dependency.** Direct imports from `ui.mermaid`.

```python
from ui.mermaid import build_mermaid_dag, _sanitize_id, _sanitize_label
```

**Test data factory:**
```python
def _make_entity(type_id, name=None, entity_type="feature", parent_type_id=None):
    return {
        "type_id": type_id,
        "name": name,
        "entity_type": entity_type,
        "parent_type_id": parent_type_id,
    }
```

**Assertion patterns:**
- Node count: `sum(1 for line in output.split("\n") if '["' in line)`
- Edge count: `sum(1 for line in output.split("\n") if " --> " in line)`
- Click count: `sum(1 for line in output.split("\n") if line.strip().startswith("click "))`
- Class assignment: `f"class {_sanitize_id(tid)} current"` in output
- Click URL with colon: `f'click {_sanitize_id("feature:021-foo")} href "/entities/feature:021-foo"'` in output (pins raw type_id in URL contract)

#### Integration Tests (additions to `test_entities.py`)

**Requires custom seeding with `parent_type_id`** — the existing `_seed_entity()` helper doesn't set it.

```python
def _seed_entity_with_parent(db_file, type_id, name, entity_type, parent_type_id=None):
    """Seed entity with parent linkage for lineage traversal.

    Matches existing _seed_entity(db_file, ...) pattern — manages its own connection.
    Sets both parent_type_id AND parent_uuid — get_lineage() uses
    recursive CTE on parent_uuid, so parent_type_id alone is insufficient.
    """
    conn = sqlite3.connect(db_file)
    entity_uuid = str(uuid.uuid4())
    parent_uuid = None
    if parent_type_id:
        row = conn.execute(
            "SELECT uuid FROM entities WHERE type_id = ?", (parent_type_id,)
        ).fetchone()
        if row:
            parent_uuid = row[0]
    conn.execute(
        """INSERT OR IGNORE INTO entities
           (uuid, type_id, entity_type, entity_id, name, status,
            parent_type_id, parent_uuid)
           VALUES (?, ?, ?, ?, ?, 'active', ?, ?)""",
        (entity_uuid, type_id, entity_type, type_id, name,
         parent_type_id, parent_uuid),
    )
    conn.commit()
    conn.close()
```

**Important:** Entities must be seeded in parent-first order so `parent_uuid` lookup succeeds.

**Test setup:** Create a 3-level hierarchy (project → brainstorm → feature) to verify:
- `mermaid_dag` in response context
- `<pre class="mermaid">` in HTML
- `<details>` wrapping flat lists
- Mermaid script absent from board/list pages
- Depth>1 children present in DAG

## Dependency Graph

```
C1 (mermaid.py)  ← no dependencies (pure stdlib: re, hashlib)
     ↑
C2 (entities.py) ← imports C1; depends on entity_registry DB (existing)
     ↑
C3 (entity_detail.html) ← receives mermaid_dag from C2; loads Mermaid CDN
```

**Build order:** C1 → C2 → C3 (strict dependency chain)
