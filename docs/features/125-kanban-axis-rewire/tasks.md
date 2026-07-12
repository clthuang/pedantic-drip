# Tasks: Kanban Axis Rewire (feature 125)

**Global context (every task):** `pytest` = `plugins/pd/.venv/bin/python -m pytest`. Binding references (open alongside EVERY task): design.md + spec.md + plan.md in this directory — every "D*n*" and "plan Task *n*" pointer resolves to exact pinned text there (code blocks are VERBATIM contracts); they are source, not context.

Serial: task 2 depends on task 1's aliases; task 3 runs whole-tree QA last.

## Task 1 — list_workflow_phases aliases

**Why:** design D3; the substrate FR125-2/3/5 read from.
**Files:** `plugins/pd/hooks/lib/entity_registry/database.py`
**Depends on:** none
**Do:** D3 verbatim — the SELECT at :9029-9031 gains `wp.kanban_column AS execution_status, wp.workflow_phase AS pipeline_phase` (additive; nothing else in the method; `get_workflow_phase` byte-untouched). Caller re-verification per D3: grep callers (engine.py, reconciliation.py, backfill.py, MCP list tools) → key-reads only, no key-set asserts; record in the task report.
**Acceptance:** `pytest plugins/pd/hooks/lib/entity_registry/ plugins/pd/mcp/ -q` green; `pytest plugins/pd/ui/tests/ -q` green (UI untouched — old key still present via `wp.*`); the caller-verification note in the report.

## Task 2 — UI rewire + full test sweep

**Why:** design D1/D2/D4/D5/D6/D7/D7b; spec FR125-1..5; SC1/SC2-production/SC3/SC4/SC6.
**Files:** `plugins/pd/ui/routes/helpers.py`, `plugins/pd/ui/routes/board.py`, `plugins/pd/ui/routes/entities.py`, `plugins/pd/ui/__init__.py`, `plugins/pd/ui/templates/{_card.html,_entities_content.html,entity_detail.html}`, `plugins/pd/ui/tests/{test_app.py,test_deepened_app.py,test_entities.py,test_filters.py}`
**Depends on:** task 1
**Do:**
1. RED-FIRST (before any code edit): add + run SC3a (synthetic ready-dict → ready bucket, KeyError-safe form `result.get("ready", [])`), SC3c (DB-seeded agent_review row → wip, no warning), and the :94-102 inversion against the PRE-rewire tree; record the verbatim failures.
2. helpers.py: `LEGACY_VALUE_REMAP` + `resolve_execution_status` VERBATIM from design D1.
3. board.py: `COLUMN_ORDER = list(EXECUTION_STATUSES)` (`from entity_registry.axes import EXECUTION_STATUSES` — the OQ-4-probed canonical spelling); `_group_by_column` body+docstring VERBATIM from D2 (name KEPT — 5 by-name test imports).
4. entities.py: annotation `e["execution_status"] = resolve_execution_status(...)` (D4) INCLUDING the :101 comment rewrite (it names kanban_column — an SC2 grep hit, plan review W1); detail route = D4's pinned aliased-list-filter snippet with the `if workflow is not None` guard; `get_workflow_phase` NOT called by the route.
5. __init__.py: COLUMN_COLORS keys == EXECUTION_STATUSES; `"ready": "badge-secondary"` (D6).
6. Templates (D5, ALL occurrences): _card.html :12/:13/:14 → `item.pipeline_phase`; _entities_content.html :66 → "Execution Status", :81 both reads → `execution_status`; entity_detail.html :50 label + :51 guard + :52 both reads → `execution_status`; :56-57 `workflow.workflow_phase` KEPT (deliberate — D5's note); _board_content.html untouched.
7. Test updates EXACTLY per D7 (D7 is the GOVERNING COMPLETE list — this is a digest; the :169 and :186-198 seed flips are in D7): test_app.py :55-62 (`set(EXECUTION_STATUSES)`), :68-78 (key flip), :88 (None-value flip), :94-102 (INVERSION: key flip + backlog + capsys stderr assert), :143-163 (docstring), :85 (docstring sweep); test_deepened_app.py :168 (`i % len(COLUMN_ORDER)`) + :169 (seed-key flip — INLINE per task review i1), :177-179 (`in (14, 15)` + comment), :186-198 (seed-key flip + the blocked-50 assert block — INLINE per task review i1), :566-590 (literal with `ready` THIRD + `len == 7` + test name + :589 comment), :598-600 (docstring/comment sweep + None-value flip), :926-960 (:934 → literal 8-value CHECK-valid tuple, NEVER COLUMN_ORDER — INSERT OR IGNORE drops CHECK-invalid `ready` silently; comment names the constraint); test_entities.py :1219-1230 (execution_status + docstring), :1234-1249 ("Execution Status" + :1236 docstring), :1584 (flip to `execution_status`), :519 (comment sweep); test_filters.py :84-89 (rename `test_column_colors_match_execution_statuses`, assert vs `set(EXECUTION_STATUSES)`, one-line rationale).
8. New tests (D7 — 6 total; SC3a/SC3c are added in item 1's red-first step, the remaining 4 here): SC1 rendered-column-order == EXECUTION_STATUSES (route test); SC4 marker test (`{"type_id": "feature:x", "pipeline_phase": "marker-pp", "workflow_phase": "marker-wf"}` via the app template env — marker-pp rendered, marker-wf absent); SC6 producer-union (drive `derive_kanban` over statuses `("active","completed","abandoned","blocked","planned")` × phases `list(PHASE_TO_KANBAN) + [None]` ∪ ENTITY_MACHINES columns → all in EXECUTION_STATUSES_SET after the helper); helper unit matrix (passthrough/remap/None).
**Acceptance:** `pytest plugins/pd/ui/tests/ -q` green in full; red-first evidence in the report; `grep -rn "kanban_column" plugins/pd/ui/routes/ plugins/pd/ui/templates/ plugins/pd/ui/__init__.py` → 0 hits.

## Task 3 — integration QA

**Why:** design D8 QA deliverables; spec FR125-6; SC2-tests-side + SC5; backlog #063 staging.
**Files:** none (QA + report; scratch worktree for baseline)
**Depends on:** tasks 1-2
**Do:** plan Task 3 verbatim — merge-base baseline (scratch worktree; account the known venv-missing artifact) then feature-branch run, deltas accounted; full suite (`plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/`); `./validate.sh`; hooks suite; doctor pin; SC2 COMPLETE = the production grep re-run (routes/templates/__init__ → 0 hits) PLUS the tests-side inspection (list every remaining `kanban_column` under ui/tests/ — all must be DB-seed write sites) — both halves inline per task review i2; final-tree `agent_review|human_review` sweep (survivors: helpers.py remap dict + comment ONLY); diff gate as SET-MEMBERSHIP vs D8 items 1-8 where item 8's feature-docs bundle INCLUDES task reports + .review-history (the plan-review S2 clarification, inline per task review i2); #063 pointer recorded for the battery.
**Acceptance:** all gates green; delta arithmetic exact; sweep survivors match D8(e); zero undispositioned diff-gate files.
