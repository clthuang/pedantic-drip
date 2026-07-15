# Tasks: 132-backfill-rebuild-tool

Serial ×4. Each ends with the full standard-scope suite green + a confined-diff check. Full artifact set (spec/design/plan) attached at dispatch — tasks are thin pointers.

## Task 1 — Guard, trigger, build steps

**Implements:** D1 (build pipeline + generation guard), D7b (REPLACE guard trigger). **Files:** database.py (`_migrate` guard after :10095's CREATE), events.py (`events_no_replace` in `_EVENTS_DDL`), NEW `entity_registry/rebuild_tool.py` + test_rebuild_tool.py, test additions in test_events.py.
**Acceptance:** SC1 (fresh bootstrap; phantom-migration-20 guard probe + v1 positive control; single version cell + #062 upsert; 122 triggers fire from birth); FR132-7 teeth (`INSERT OR REPLACE` on an existing event uuid raises, row byte-unchanged); guard inert on every existing v1 fixture (suite green unchanged). Diff ⊆ {database.py, events.py, rebuild_tool.py, tests}.

## Task 2 — Backfill, report, swap

**Implements:** D2 (import: ro-URI, topological, one transaction, dual maps, dedup), D3 (emission mapping + actor + pre-import vocab diff incl. kanban/mode CHECKs), D4 (WAL-safe swap + marker), D4b (SC4 measurement), D7 (reports), D8 (FTS), D6.9's sequences seeding (import-transaction half ONLY). Vendors `_derive_kanban_frozen` (byte-derived from kanban.py:25 — public module untouched until task 4; SC2's idempotent re-run must pass WITHOUT the public module post-task-4).
**Acceptance:** SC2 (pathological corpus: empty ids, within-workspace dup, cross-workspace P001s preserved, uuid4 rows, blocks edges, 5D/lifecycle histories, bug-kind probe; idempotent re-run byte-identical report), SC3(a) axis-view replay + SC3(b) rich-field parity (source EXCLUDED, actual-columns list), SC4 (statement-2 EXPLAIN pushdown + p95 ≤ 5ms @ ~533), SC6 (old-file write fails loud; dated marker). No live-path change. Diff ⊆ {rebuild_tool.py, tests, report artifacts}.

## Task 3 — Dual-write

**Implements:** D5 — `_emit_v2_event` (v2-generation-guarded), five-writer wiring (append_phase_event; register/upsert; delete_entity; create_workflow_phase establishment; update_entity emit IN-transaction fail-closed + `audit_emit_failed_count` deletion), entity_engine.py:559 cascade call deletion (`_run_cascade` rollup/notifications retained). **Files:** database.py, entity_engine.py, test_entity_engine.py (:231/:256/:261/:690/:758/:791), test_database.py, test_dependencies.py additions.
**Acceptance:** SC7 (#055 phase-event-exists-after-success; #060 backlog-registration-visible-immediately), SC8 (6 mutation classes dual-write atomically; injected emit failure ROLLS BACK the update_entity status write — asserted on both tables; exactly one `cascade_ready` per flip). v1 fixtures unaffected (generation guard). Diff ⊆ {database.py, entity_engine.py, tests}.

## Task 4 — Deletions, allocator, #075, SC5 gate

**Implements:** D6.1-.10 complete. **Files:** kanban.py + test_kanban.py DELETED; workflow_state_server.py:1003/:1272, backfill.py:335, reconciliation.py:201, feature_lifecycle.py:205, engine.py:529 rewired; test_constants/test_backfill/test_reconciliation/test_engine/doctor test_checks:956/mcp test_workflow_state_server (TestCompletePhaseKanbanMatchesDeriveKanban)/ui test_deepened_app/ui test_app rewritten; test_axes.py:530-543 RE-PINNED first; `_resolve_workspace_uuid_kwargs`(:6286) + 6 callers (:7085/:7381/:8070/:9423/:9883/:10034) + `_atomic_write_workspace_mapping`(:1726) + migration-11 :1861 call edited; LEGACY_VALUE_REMAP (helpers.py:144) + board.py:28 + test_app.py:258-374; comments (axes.py:70, constants.py:4, router.py:70, schema_v2.py:64); create-project.md allocator rewrite + entity_server.py:673-682 guard removal + docstrings ~:640-649/:655; `_process_transition_entity_phase` → `get_machine(kind).validate()` + moved-legacy validator deletion.
**Acceptance:** `::test_allocator_cutover_project_kind`; chain-replay DDL-identity test green post-m11-edit; SC5 grep gate (plugins/pd/ scope, D6.10 exemptions) output recorded; full suite + hooks 67/67 + validate 0 errors; diff-vs-develop ⊆ D10.
