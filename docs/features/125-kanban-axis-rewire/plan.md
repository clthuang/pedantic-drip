# Implementation Plan: Kanban Axis Rewire (feature 125)

## Objective

Land design D1-D8 in three serial tasks: the DB read-alias (tiny, everything depends on it); the cohesive UI rewire with its full test sweep (one implementer holds the whole rename contract — splitting UI code from UI tests would break every-commit-green); integration QA with the SC2 grep, merge-base baseline, and the #063 watch data point.

## Prerequisites

Branch `feature/125-kanban-axis-rewire` (active; spec + design committed at 62b7a6cb). Design D1-D8 binding: the pinned helper/docstring/grouping code blocks, the zero-occurrence detail path (get_workflow_phase untouched AND uncalled by the route), the CHECK-aware :934 fix (literal 8-value tuple, never the 7-value COLUMN_ORDER), the D7 enumerated test edits incl. the adjacent-docstring sweep, ready=badge-secondary, `ready` THIRD in the expected literal. `pytest` = `plugins/pd/.venv/bin/python -m pytest`.

## Step Ordering Rationale

Task 1 (two SELECT alias lines) is the substrate — the UI rewire reads the aliased keys, so task 2 depends on it; task 1 alone is invisible to every existing consumer (additive keys, callers verified twice). Task 2 is deliberately ONE task: the grouping-key switch, template renames, color realignment, and their test updates form a single rename contract — any split ships a red intermediate commit. Task 3 runs whole-tree QA over the final tree. Within task 2, red-first runs SC3a/SC3c and the :94-102 inversion against the pre-rewire code first.

## Task 1 — list_workflow_phases aliases (D3; substrate for FR125-2/3/5)

**Do:**
1. database.py:9029-9031: add `wp.kanban_column AS execution_status, wp.workflow_phase AS pipeline_phase` to the SELECT per D3's pinned SQL. Nothing else in the method changes; `get_workflow_phase` byte-untouched.
2. Caller re-verification on the final text (OQ-1 residual): grep list_workflow_phases callers (engine.py, reconciliation.py, backfill.py, MCP list tools) — confirm key-reads only, no key-set asserts; record in the task report.

**Verify:** `pytest plugins/pd/hooks/lib/entity_registry/ plugins/pd/mcp/ -q` green (no consumer notices additive keys); `pytest plugins/pd/ui/tests/ -q` green (UI untouched, old key still present via wp.*).

## Task 2 — the UI rewire + full test sweep (D1, D2, D4, D5, D6, D7, D7b; FR125-1..5, SC1/3/4/6)

**Do (every item pinned in the design — read D1-D7 alongside):**
1. helpers.py: `LEGACY_VALUE_REMAP` + `resolve_execution_status` VERBATIM from D1.
2. board.py: `COLUMN_ORDER = list(EXECUTION_STATUSES)` (axes import per D2/OQ-4); `_group_by_column` body+docstring replaced VERBATIM from D2 (name KEPT).
3. entities.py: list annotation → execution_status via the helper (D4); detail route → the zero-occurrence aliased-list-filter path with the LOAD-BEARING `if workflow is not None` guard (D4's pinned snippet); get_workflow_phase NOT called.
4. __init__.py: COLUMN_COLORS → EXECUTION_STATUSES keys; ready=badge-secondary (D6).
5. Templates per D5: _card.html :12/:13/:14 all three → pipeline_phase; _entities_content.html :66 header → "Execution Status" + :81 BOTH reads → execution_status; entity_detail.html FOUR tokens (:50 label, :51 guard, :52 both); entity_detail.html:56-57 workflow_phase KEPT deliberately (D5's S4 note); _board_content.html untouched.
6. Tests per D7 EXACTLY — design D7 is the GOVERNING COMPLETE list, this bullet is a digest (plan review S3: the digest omits e.g. the :169 and :186-198 seed-key flips; an implementer works from D7, not from here): the enumerated updates (test_app.py :55-62/:68-78/:88-flip/:94-102-inversion/:143-163-docstring; test_deepened_app.py :168-modulo + :177-179 distribution + :566-590 literal/name/comment + :600-flip + :926-960 CHECK-aware literal-tuple fix; test_entities.py :1219-1230/:1234-1249/:1584-flip; test_filters.py :84-89 rename) + the 6 new tests (SC1 vocabulary-order route test; SC3a ready synthetic; SC3c seeded agent_review route test; SC4 marker test WITH type_id; SC6 producer-union input-space driven; helper unit matrix) + the adjacent-docstring sweep (D7's gate-added list: test_app.py:85, test_deepened_app.py:598-599, test_entities.py:1236/:519).
7. RED-FIRST: before the code edits, run SC3a + SC3c + the :94-102 inversion against the pre-rewire tree and record the failures. SC3a's assertion is written KeyError-safe (`assert row in result.get("ready", [])` — the pre-rewire dict has no 'ready' key; the safe form makes the red read as a behavioral gap, not an incidental crash — plan review S1).

**Verify:** `pytest plugins/pd/ui/tests/ -q` green in full; red-first evidence recorded; `grep -rn "kanban_column" plugins/pd/ui/routes/ plugins/pd/ui/templates/ plugins/pd/ui/__init__.py` → 0 hits (SC2's production half).

## Task 3 — integration QA (D8 QA deliverables; FR125-6, SC2/5 + #063)

**Do:**
1. Merge-base suite baseline in a scratch worktree (campaign pattern; the venv-missing worktree artifact is known — account it), then the feature-branch run; every delta accounted.
2. Full `pytest plugins/pd/hooks/lib/ plugins/pd/mcp/ plugins/pd/ui/ -q`; `./validate.sh` 0 errors; `bash plugins/pd/hooks/tests/test-hooks.sh`; doctor pin unchanged.
3. SC2 complete: production grep 0 hits + tests-side inspection (every remaining occurrence a DB-seed write site; list them in the report).
4. Final-tree sweep `agent_review|human_review` — expected survivors: helpers.py's remap dict + comment ONLY.
5. Diff gate as SET-MEMBERSHIP: every changed file ∈ D8 items 1-8; item 8's feature-docs bundle INCLUDES the task reports and .review-history (plan review S2 — the gate must not false-positive on the evidence files the plan itself mandates); nothing outside.
6. Backlog #063 note: staged for the battery (the reviewer prompt carries the watch; the QA task records the pointer).

**Verify:** all gates green; delta arithmetic exact; sweep results match D8(e).

## Risks & Mitigations

- **Vacuous SC4 (the value-equality trap):** the marker test uses DIFFERING pipeline_phase/workflow_phase values — pinned in D7 with type_id.
- **The i%8 class (two instances found across two review rounds):** both cited with exact fixes; task 3's full-suite run is the backstop for a third.
- **Seed-key half-flips:** D7 enumerates flip vs no-edit per test precisely (None-value rows flip; the :208 no-key row doesn't).
- **Reviewer cap:** 3 iterations per reviewer, then documented escalation.

## Rollback

One commit per task; task 1 reverts independently (additive aliases); task 2 reverts as a unit (code+tests consistent both sides); task 3 is QA-only.

## Success Check (spec SCs)

SC1 → task 2 (new route test); SC2 → task 2 (production grep) + task 3 (tests-side inspection); SC3 → task 2 (SC3a/SC3c + inversion, red-first); SC4 → task 2 (marker test); SC5 → task 3; SC6 → task 2 (producer-union test).
