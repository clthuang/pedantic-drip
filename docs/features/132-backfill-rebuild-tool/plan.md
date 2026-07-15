# Plan: 132-backfill-rebuild-tool

Implements design.md (578cd7d). FOUR serial tasks — database.py is the shared spine of 1/3/4 (guard → dual-write → deletions), and the backfill (2) must exist green before the deletions (4) can retire the machinery it reads.

## Task slicing rationale

- **Task 1 = inert infrastructure.** The `_migrate()` generation guard (no-op on every existing v1 file), D7b's `events_no_replace` guard trigger (v2-side only), and the rebuild tool's D1 build steps (staging construction → selective seed → stamp). Nothing live changes; SC1 + FR132-7 teeth go green here.
- **Task 2 = backfill + report + swap.** D2/D3 import with the pre-import vocab diff, D7 reports, D8 FTS, D4 WAL-safe swap choreography + D4b readiness measurement. **The tool VENDORS a frozen private copy of the kanban derivation (`rebuild_tool._derive_kanban_frozen`, comment-marked) — the public `derive_kanban` still exists at this point, but task 4 deletes it and SC2's idempotent re-run must survive that** (design D2's "via the current derive_kanban logic" is satisfied by the vendored copy being byte-derived from kanban.py:25 at task-2 time).
- **Task 3 = live dual-write.** D5's `_emit_v2_event` + the five-writer wiring incl. update_entity's fail-open→fail-closed move and the entity_engine.py:559 deletion (#080 single-fire). SC7/SC8 go green here. Ordered AFTER task 2 so a cutover DB exists for end-to-end dual-write tests, but the code paths are v1-file-safe (emit no-ops when the events table is absent? NO — the emit requires the v2 events table; d) — **guard: `_emit_v2_event` writes ONLY when `schema_generation='v2'`** (one `_metadata` read, cached per connection) so pre-cutover v1 files keep working through the suite; the SC8 tests run on tool-built v2 files.
- **Task 4 = deletions + allocator + #075 + SC5 gate.** D6.1-.10 in one sweep (derive_kanban module+6 sites+test surface, both M11 shims incl. migration-11's :1861 call edit, LEGACY_VALUE_REMAP, D6.9 allocator cutover, #075 validate rewire), then the SC5 grep gate LAST when every disposition has landed. Full suite + hooks + validate green.

## Task 1 — Guard, trigger, build steps (D1, D7b)

- `_migrate()` generation guard after the `_metadata` CREATE (database.py:10095 region), above the version loop; SC1's phantom-migration-20 probe + v1 positive control per spec.
- `events_no_replace` BEFORE INSERT guard added to events.py's `_EVENTS_DDL` (ships inside the `events` registry owner — D7b/D1-step2); teeth test `::test_insert_or_replace_rejected`.
- `rebuild_tool.py` build steps: step-1 `EntityDatabase(staging)` construct+close; step-2 raw connection, import events/views + `register_vocab_ddl()`, execute owners events/views/axes/axes_vocab_triggers, `foreign_keys=ON`; step-3 generation stamp + #062 upsert. `--staging-only` flag so tasks 2's import develops against a real staging file.
- Gate: suite green (guard inert on all existing fixtures); SC1 named tests green; diff confined to database.py/events.py/rebuild_tool.py(+test).

## Task 2 — Backfill, report, swap (D2, D3, D4, D4b, D7, D8)

- Import per D2 (ro-URI read, FK-safe topological order, one transaction, old→new uuid map + secondary (workspace,type_id)→new_uuid map, within-workspace dedup, anomaly rows) with D3's emission mapping (actor='backfill:132', kind/event_type bucketing, lifecycle-only for non-phase/legacy values, ascending domain-timestamp insert order) and the pre-import vocab diff (aborts BEFORE any write; surface incl. kanban_column+mode CHECKs).
- Vendored `_derive_kanban_frozen` (see rationale) writes the stored v1 columns + the execution-axis `status_backfilled` event.
- D7 reports (machine JSON to ~/.claude/pd/migrations/, counts-only committed summary), D8 FTS rebuild, D4 swap (checkpoint TRUNCATE both sides, sidecar abort check, marker JSON, loud restart warning), D6.9's sequences seeding (census max per kind×workspace — lands HERE in the import transaction; the command/guard edits stay in task 4).
- SC2 (pathological corpus incl. bug-kind + within-workspace dup), SC3(a)(b) as rescoped, SC4 (D4b statement-2 EXPLAIN + p95), SC6 (read-only old file + marker) named tests green. NO live-path behavior change yet.
- Gate: suite green; diff confined to rebuild_tool.py(+test) and report artifacts.

## Task 3 — Dual-write (D5)

- `_emit_v2_event` helper (database.py) with the v2-generation guard (above); wired into append_phase_event, register_entity/upsert_entity, delete_entity, create_workflow_phase (establishment event), update_entity (emit moves IN-transaction, fail-closed, `audit_emit_failed_count` machinery deleted).
- entity_engine.py:559 cascade_unblock call deleted (slot returns `unblocked=[]`); `_run_cascade`'s rollup/notifications retained; test_entity_engine.py's 6 refs updated.
- SC7 (#055/#060 incident-shaped pins) + SC8 (6 classes, update_entity ROLLBACK assertion, single cascade fire) green on tool-built v2 files.
- Gate: suite green (v1 fixtures unaffected via the generation guard); diff confined to database.py, entity_engine.py, dependencies-adjacent tests.

## Task 4 — Deletions, allocator, #075, SC5 gate (D6)

- D6.1-.3: kanban.py module + test_kanban.py deleted; six call sites rewired to stored values; repo-wide test rewrites (incl. mcp/test_workflow_state_server.py's TestCompletePhaseKanbanMatchesDeriveKanban and ui/tests files); test_axes.py:530-543 subset pin RE-PINNED first.
- D6.4-.5: `_resolve_workspace_uuid_kwargs` + 6 callers rewired + `_atomic_write_workspace_mapping` + migration-11 :1861 call edit (chain-replay identity test re-run proves DDL-neutrality).
- D6.6-.7: LEGACY_VALUE_REMAP + helpers/board/test_app rewrites; comment sweep (axes.py:70, constants.py:4, router.py:70, schema_v2.py:64).
- D6.9: create-project.md allocator rewrite + entity_server.py:673-682 guard removal + coupled docstring edits; `::test_allocator_cutover_project_kind`.
- D6.8/#075: `_process_transition_entity_phase` → `get_machine(kind).validate()`; moved-legacy validators deleted.
- SC5 grep gate LAST (plugins/pd/ scope per D6.10, exemptions per spec).
- Gate: full suite + hooks 67/67 + validate 0 errors; SC5 output pasted into the QA record; diff-vs-develop ⊆ D10.

## Risks

- **Task-2 vendored deriver drift** — frozen copy taken AFTER any task-1 churn (there is none in kanban.py) and byte-compared to kanban.py:25's logic in the task-2 review.
- **update_entity fail-closed blast (task 3)** — abandon-feature/cleanup_backlog paths now roll back on emit failure; their tests must cover the rollback (SC8's classes do).
- **Suite churn (task 4)** — the widest diff; the D6 inventory + repo-wide greps (design re-grep mandate) bound it; H4's 120/126 dark-suite fixture moves land here too.
- **Live-DB window (H5)** — the tool never runs at import; suite uses tmp paths only; the REAL cutover of ~/.claude/pd is a MANUAL post-merge step (explicitly NOT in any task's tests).

## Verification (end of task 4)

Standard-scope suite green; hooks; validate; SC1-SC8 + FR132-7 + allocator tests each named green; SC5 grep output recorded; diff-gate ⊆ D10; the committed summary report present; MANUAL post-merge runbook printed by the tool (cutover + restart warning) verified by eye.
