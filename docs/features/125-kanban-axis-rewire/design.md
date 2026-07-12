# Design: Kanban Axis Rewire (feature 125)

Implements spec FR125-1..6. Every probe below was run against the live tree at design time (2026-07-12); OQ-1..4 resolved here. Iteration-1 rewrite: `_group_by_column` KEEPS its name (the rename's collection-time ImportError blast radius was the blocker); the detail route adopts the ZERO-occurrence read path (the one-shim SC2 exemption is REVERTED in the spec — swept in the same revision).

## D1 — the shared helper (FR125-1's remap)

New in `plugins/pd/ui/routes/helpers.py` (board.py:8 and entities.py:10 already import this module — no new import edge, no cycle):

```python
# Stored v1 kanban_column values with no v2 EXECUTION_STATUSES home.
# agent_review IS live (brainstorm reviewing -> agent_review,
# entity_lifecycle.py:26); human_review is defensive (zero producers, but
# the v1 CHECK still admits stored rows). DELETE at 132 once the backfill
# translates stored values at source (this mapping is its display precedent).
LEGACY_VALUE_REMAP: dict[str, str] = {
    "agent_review": "wip",
    "human_review": "wip",
}


def resolve_execution_status(value: str | None) -> str | None:
    """Map a stored v1 kanban_column value to its v2 execution_status.

    Vocabulary values pass through; legacy values remap; None/unknown pass
    through unchanged (the CALLER decides defaulting/warning — board
    grouping defaults None->backlog and warns on unknowns per FR125-4;
    the entities annotation/detail render whatever comes back).
    """
    if value in LEGACY_VALUE_REMAP:
        return LEGACY_VALUE_REMAP[value]
    return value
```

Scalar-in/scalar-out per the gate-reconciled signature; `pipeline_phase` is a verbatim `workflow_phase` rename at each surface, no shared call.

## D2 — board.py rewire (FR125-1, FR125-4) — NO function rename

- `COLUMN_ORDER = list(EXECUTION_STATUSES)` via `from entity_registry.axes import EXECUTION_STATUSES` (OQ-4 RESOLVED by probe: double-import module-cached; `register_ddl("axes", ...)` is a pure in-memory list append — ValueError only on dual-path double-execution, which the canonical spelling avoids; no bare `axes` import exists in the tree; `import ui` + `import entity_registry.axes` coexist, probed both orders). The hand-copied 8-entry list dies.
- `_group_by_column` KEEPS ITS NAME (iteration-1 S1: spec FR125-4 uses this exact name; 5 by-name test imports incl. a MODULE-TOP one at test_deepened_app.py:16 — renaming would collection-time-ImportError the whole file, the feature-118 class). Its body AND docstring are replaced (iteration-2 W1: the live docstring board.py:30-34 carries three `kanban_column` tokens — an SC2 grep hit — plus "all 8 columns" and a "silently dropped" line that contradicts FR125-4; the replacement docstring is pinned in the code block):

```python
def _group_by_column(rows: list[dict]) -> dict[str, list[dict]]:
    """Group rows by execution_status (v2 vocabulary).

    Returns dict with every EXECUTION_STATUSES column as a key (empty list
    if no rows). None defaults to 'backlog'; legacy values remap via
    LEGACY_VALUE_REMAP; unknown values land in 'backlog' WITH one stderr
    warning (never silently dropped).
    """
    columns: dict[str, list[dict]] = {col: [] for col in COLUMN_ORDER}
    for row in rows:
        status = resolve_execution_status(row.get("execution_status")) or "backlog"
        if status not in columns:
            print(
                f"[board] unknown execution_status {status!r} on "
                f"{row.get('type_id')!r} — bucketed to backlog",
                file=sys.stderr,
            )
            status = "backlog"
        columns[status].append(row)
    return columns
```

Truth-table order verified: (1) None/empty → helper passes None through → `or "backlog"`, no warning; (2) vocabulary → in columns, no warning; (3) legacy → remapped FIRST (helper runs before membership), no warning; (4) else → backlog + ONE stderr warning. The route passes rows straight through.

## D3 — list_workflow_phases aliases (OQ-1's alias half)

database.py:9029-9031's SELECT gains two aliased projections:

```sql
SELECT wp.*, wp.kanban_column AS execution_status,
       wp.workflow_phase AS pipeline_phase,
       e.name AS entity_name, e.kind AS entity_type,
       e.artifact_path AS entity_artifact_path
FROM workflow_phases wp LEFT JOIN entities e ON wp.type_id = e.type_id
```

Additive keys; the aliases create DISTINCT column names beside wp.*'s originals (no dict-key collision — verified by the iteration-1 skeptic against the row_factory). Caller re-verification (OQ-1 residual, design-time): engine.py, reconciliation.py, backfill.py, and the MCP list tools read named keys, never assert key sets. `get_workflow_phase` is byte-untouched.

## D4 — entities.py (both read paths) — the ZERO-occurrence detail path

**List annotation (:101-104):** the lookup rows already come from `list_workflow_phases` — the annotation becomes `e["execution_status"] = resolve_execution_status(workflow_lookup.get(e["type_id"], {}).get("execution_status"))`. The `kanban_column` key name dies here.

**Detail route (:148-196):** adopts the iteration-1 W1 path — `get_workflow_phase` is NOT called anymore by this route (the method itself stays byte-untouched for its 18 non-UI callers); the route instead reads the ALREADY-ALIASED list and filters to the one row:

```python
rows = db.list_workflow_phases()  # unscoped — preserves get_workflow_phase's non-scoped semantics
workflow = next((r for r in rows if r.get("type_id") == type_id), None)
if workflow is not None:
    workflow["execution_status"] = resolve_execution_status(workflow.get("execution_status"))
```

- ZERO `kanban_column` tokens anywhere in ui routes/templates/__init__ — the spec's one-shim SC2 exemption is REVERTED (upward sweep in the same revision; SC2 back to a 0-hit grep). The iteration-0 "must read the v1 key somewhere ui-side" premise was a false dichotomy (not-modifying a method ≠ must-call it).
- The `if workflow is not None` guard is LOAD-BEARING (iteration-1 W6): entities with no workflow_phases row (new backlog/brainstorm) return no row; entity_detail.html:44's `{% if workflow %}` renders the page without the Workflow State card — unconditional normalization would crash to the DB-error page, a FR125-6 regression.
- Trade-off recorded: full-table LEFT JOIN scan vs single-row lookup — the entity-LIST route already pays exactly this cost per page load; the detail page is lower-traffic; at live scale (~600 rows) the difference is sub-millisecond. 132's source flip lands in ONE place (list_workflow_phases) for all three surfaces.
- `pipeline_phase` arrives pre-aliased from D3 — no route-side work.

## D5 — templates (ALL occurrences enumerated — iteration-1 W2/W3/S3)

- `_card.html` :12/:13/:14 — THREE `item.workflow_phase` occurrences (guard, color lookup, display) ALL become `item.pipeline_phase` (a :13-only edit would half-rename and violate FR125-3's key contract).
- `_entities_content.html` :66 header `Kanban Column` → `Execution Status` (OQ-2 RESOLVED — the table's existing "Status" header is registry status; "Execution Status" is the unambiguous v2 name); :81 value cell — TWO reads on the one line (`entity.kanban_column if entity.kanban_column is not none else ''`) BOTH → `execution_status` (iteration-2 S1).
- `entity_detail.html` — FOUR tokens: :50 header label `Kanban Column` → `Execution Status` (consistency with :66's rename); :51 guard `{% if workflow.kanban_column %}` → `execution_status`; :52 BOTH reads (color lookup + display) → `execution_status`.
- `_board_content.html`: iterates the columns dict, no key reads — untouched (verified).
- entity_detail.html:56-57's "Workflow Phase" row KEEPS `workflow.workflow_phase` DELIBERATELY (iteration-2 S4): spec FR125-3 scopes the pipeline_phase rename to the CARD BADGE; the detail row renders the same value pre-132 and is not a badge — recorded so QA doesn't read it as a missed rename.

## D6 — COLUMN_COLORS realignment (ui/__init__.py:41-50)

Keys become exactly EXECUTION_STATUSES: drop `agent_review` (badge-secondary) and `human_review` (badge-accent); add `"ready": "badge-secondary"` — REUSES the class freed by agent_review's removal and is distinct from prioritised's badge-info (iteration-1 W4: the earlier badge-info choice collided with the ADJACENT prioritised column). The Jinja global wiring (:160) untouched.

## D7 — test plan (inventory COMPLETED at iteration 1 + new tests)

**Updates (every touched assert cited; NO function rename, so zero import-site edits):**
- test_app.py:55-62 exact-set → `set(EXECUTION_STATUSES)`; :68-78 seed dict key → `execution_status` (asserts wip grouping); :86-93 None-value seed key flipped per the W2 collapse below; :94-102 INVERTED (seed key → `execution_status`: unknown value → backlog + capsys stderr assert — WITH the key flipped, else it hits None→backlog and the warning assert fails vacuously); :143-163 docstring refreshed ("all 8" → vocabulary-sized).
- test_deepened_app.py :16 module-top import UNCHANGED (name kept); :163-179 — seed keys + :168's `COLUMN_ORDER[i % 8]` → `i % len(COLUMN_ORDER)` (IndexError on 7 otherwise) AND :179's `assert len(result[col]) in (12, 13)` → `in (14, 15)` (iteration-2 B2: 100 rows over 7 columns = 14 remainder 2 — two columns get 15, five get 14; the :177 "100 / 8 = 12.5" comment refreshed with it); :186-198 (seed keys; blocked-50 assert); :205-214 NO EDIT (the ONLY genuine no-key row — :208 is `{"type_id": ...}` with no kanban_column key; missing key → None → backlog passes unchanged); None-VALUE rows DO flip for a clean v2 pin (iteration-3 W2 collapsed the contradictory :86-93 instructions — test_app.py:88's and test_deepened_app.py:600's `{"kanban_column": None}` both become `{"execution_status": None}`; either way passes, the flip pins the v2 key); :566-575+:578+:590 (list literal, `== expected`, `len == 8` → 7; the test NAME `test_column_order_has_exactly_8_entries` and its :589 comment refreshed too — iteration-2 S3; the updated `expected` literal MUST match EXECUTION_STATUSES order exactly with `ready` THIRD, after prioritised — iteration-3 S2); :926-960 `test_ttfb_under_200ms_for_100_features` (iteration-2 B1 — a SECOND uncited `COLUMN_ORDER[i % 8]` at :934 that IndexErrors on 7; AND the naive modulo fix is WRONG here: :934 feeds a DB seed through INSERT OR IGNORE (:41), so cycling the new 7-value COLUMN_ORDER would push CHECK-invalid `ready` (database.py:1212-1216 excludes it) into silently-dropped inserts, seeding ~86 of the promised 100 rows — fix: cycle over a literal tuple of the 8 DB-CHECK-valid values, independent of COLUMN_ORDER, with a comment naming the constraint).
- test_entities.py:1219-1230 annotation test → execution_status (docstring refreshed); :1234-1249 header test → "Execution Status"; :1584's helper-dict assertion `result[...]["kanban_column"] == "wip"` FLIPPED to `["execution_status"]` (iteration-3 W1: it passes either way via the additive alias, but flipping keeps SC2's tests-side "seed-writes-only" clause literally true — no exception needed).
- test_filters.py:84-89 renamed `test_column_colors_match_execution_statuses` asserting `set(COLUMN_COLORS.keys()) == set(EXECUTION_STATUSES)` + one-line rationale (PHASE_COLORS sibling :70-82 untouched).

**New tests:**
1. SC1: rendered board column headers == EXECUTION_STATUSES order (route test).
2. SC3a (synthetic unit): `{"execution_status": "ready"}` row → ready bucket (RED-FIRST: dropped today).
3. SC3c (seeded route test): DB-seeded `agent_review` row (CHECK-legal) renders in wip, NO warning (RED-FIRST: renders in agent_review today). (SC3b unknown-warning IS the :94-102 inversion — no duplicate.)
4. SC4 non-vacuous KEY test (iteration-1 W5): render `_card.html` via the app template env with a synthetic item `{"type_id": "feature:x", "pipeline_phase": "marker-pp", "workflow_phase": "marker-wf"}` — type_id REQUIRED (iteration-3 S1: _card.html:10 splits it; UndefinedError without) — assert marker-pp rendered, marker-wf absent (value-equality pre-132 makes any value-based test vacuous; only differing markers pin the KEY).
5. SC6 producer-union pin (iteration-1 W7 — executable enumeration, no hand-copied literals): drive `derive_kanban` over its FULL input space — `for status in ("active","completed","abandoned","blocked","planned"): for phase in list(PHASE_TO_KANBAN) + [None]:` collect outputs — UNION `{col for m in ENTITY_MACHINES.values() for col in m["columns"].values()}`; assert every member lands in EXECUTION_STATUSES_SET after `resolve_execution_status` (PHASE_TO_KANBAN.values() alone yields only 4 of the six — completed/blocked are body literals, kanban.py:34-39; input-space driving cannot under-cover).
6. Helper unit: LEGACY_VALUE_REMAP passthrough/remap/None matrix.

**Adjacent docstrings/comments sweep (gate warning — the feature-120 #061 class):** test_app.py:85 ("A row with kanban_column=None..."), test_deepened_app.py:598-599 (docstring + comment), test_entities.py:1236 (header-test docstring), test_entities.py:519 (comment "Workflow fields from the template (kanban_column, workflow_phase)") — all refreshed to the v2 key names when their tests are touched (none affects pass/fail; the sweep keeps prose truthful).

Red-first evidence recorded in the task report for SC3a/SC3c + the :94-102 inversion.

## D7b — OQ-3 RESOLVED (labeling completed at gate)

The dead-column consumer sweep ran at design time: `agent_review|human_review` appears at exactly five ui/ sites (board.py:21-22, __init__.py:45-46, test_app.py:57-58, test_deepened_app.py:570-571, test_filters.py:86-87) — every one in the D2/D6/D7 edit inventory — plus zero docs/README hits. D8(e)'s final-tree sweep is the QA backstop.

## D8 — file inventory (complete) + QA deliverables

1. plugins/pd/ui/routes/helpers.py (+helper, +remap — NO shim, the zero-occurrence path)
2. plugins/pd/ui/routes/board.py (D2)
3. plugins/pd/ui/routes/entities.py (D4)
4. plugins/pd/ui/__init__.py (D6)
5. plugins/pd/ui/templates/{_card.html, _entities_content.html, entity_detail.html}
6. plugins/pd/hooks/lib/entity_registry/database.py (D3 — the one non-UI file; two alias lines)
7. plugins/pd/ui/tests/{test_app.py, test_deepened_app.py, test_entities.py, test_filters.py} per D7
8. Feature docs (spec/design/plan/tasks/.review-history + the SC2 REVERT upward sweep)

No command/skill/agent/hook/MCP-tool changes → no README count syncs. No doctor changes → pin unchanged.

**QA deliverables:** (a) suite baseline at merge-base (scratch worktree, campaign pattern), every delta accounted; (b) SC2 grep = ZERO hits over routes/templates/__init__ (the reverted contract) + the tests-side seed-write-only inspection; (c) SC5 full suite + validate.sh + hooks; (d) backlog #063 data point at battery (quality-reviewer actionable-fix rate, UI-track, n=2); (e) final-tree sweep `agent_review|human_review` — expected survivors: helpers.py's remap dict + comment ONLY.
