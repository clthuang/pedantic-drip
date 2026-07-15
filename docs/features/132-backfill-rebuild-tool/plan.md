# Plan: 132-backfill-rebuild-tool

Implements design.md (578cd7d). FIVE serial tasks (i1 split of the old task 4 — ~10 disjoint sub-changes under one gate gave no failure signal). database.py is the shared spine of 1/3/4/5; the backfill (2) must exist green before the retirements (4/5) delete the machinery it reads.

## Task slicing rationale

- **Task 1 = inert infrastructure + the m11 ordering fix.** The `_migrate()` generation guard, D7b's `events_no_replace` trigger, the rebuild tool's D1 build steps, AND the migration-11 :1861 call-site neutralization — design D1 pins "ships WITH or BEFORE the tool" and i1 proved the stray-write live (unprotected fresh-DB tests exist at test_database.py:3140/:3148/:3160/:4968); the plan's earlier task-4 deferral silently reversed that design decision. The `_atomic_write_workspace_mapping` FUNCTION body survives (callerless, harmless) until task 5's sweep. Task 1 also runs D1's migration-body side-effect grep (`os\.\b|open\(` over migration fns on an empty file).
- **Task 2 = backfill + report + swap.** D2/D3 import with the pre-import vocab diff, D7 reports, D8 FTS, D4 swap, D4b measurement, D6.9's sequences seeding. **The tool VENDORS a frozen private derivation named `_frozen_kanban_derivation`** — renamed at plan-i1: the earlier `_derive_kanban_frozen` name (and any comment using the bare token) contains the exact `derive_kanban` token task 5's SC5 gate greps, and rebuild_tool.py sits INSIDE the gate's plugins/pd/ scope — the 125-class collision, caught pre-implementation. Its comment cites "kanban.py:25's derivation, frozen at task-2 time" WITHOUT the bare symbol token; **SC5's grep pattern is pinned as the literal token `derive_kanban`** (word-boundary irrelevant once no identifier/comment carries the token).
- **Task 3 = live dual-write.** D5's `_emit_v2_event` gated on `schema_generation='v2'` (one `_metadata` read, cached per connection — v1 files have NO events table, so the guard is non-vacuously bracketed: a broken always-emit crashes the v1 suite, a broken never-emit fails SC8), the five-writer wiring incl. update_entity's fail-closed move (+ the D5-mandated code comment recording the update/upsert_workflow_phase presentational exclusion), the entity_engine.py:559 deletion, and the cleanup_backlog.py archival-path emit verification D10 hedges.
- **Task 4 = derive_kanban retirement.** D6.1-.3 (module + 6 call sites + repo-wide test surface + comment sweep) — the widest-churn slice, isolated so its failures signal cleanly.
- **Task 5 = shims, remap, allocator, #075, SC5 gate.** D6.4-.10 remainder + the gate LAST + full verification.

## Task 1 — Guard, trigger, build steps, m11 ordering (D1, D7b, D6.5-call-half)

- `_migrate()` generation guard after the `_metadata` CREATE (database.py:10095 region); SC1 phantom-migration-20 probe + v1 positive control.
- `events_no_replace` BEFORE INSERT guard inside `_EVENTS_DDL` (events owner); `::test_insert_or_replace_rejected`.
- `rebuild_tool.py` build steps (D1: construct+close staging; selective registry seed with `foreign_keys=ON`; generation stamp + #062 upsert); `--staging-only` flag.
- Migration-11 :1861 call REMOVED (D6.5's call-half; DDL-neutral — chain-replay identity test proves it); migration-body side-effect grep documented in the task record. 120/126 dark suites: verify the 122-trigger activation is TOOL-LOCAL (D1-step2 — staging connection only); grep those suites for trigger-ABSENCE assertions (none expected; H4 churn scoped to tool-builder adopters only).
- Gate: suite green; SC1 + FR132-7 tests green; diff ⊆ {database.py, events.py, rebuild_tool.py, tests}.

## Task 2 — Backfill, report, swap (D2, D3, D4, D4b, D7, D8, D6.9-seed-half)

- Import per D2/D3 (ro-URI read, topological order, ONE transaction, dual maps, within-workspace dedup, anomaly rows; actor='backfill:132'; ascending domain-timestamp insert order; `_frozen_kanban_derivation` writes stored v1 columns + the execution-axis `status_backfilled` event).
- Pre-import vocab diff (aborts BEFORE any write; surface incl. kanban_column+mode CHECKs) — **`::test_preimport_vocab_diff_aborts` is TASK 2 acceptance** (i1: it was orphaned to the task-5 gate; SC2's corpus proves the success path, this proves the abort path — mutually exclusive scenarios, both needed here).
- D6.9 sequences seeding (census max per kind×workspace) — **task-2 acceptance asserts the seeded rows' values directly** (i1: SC2 parity covers entities/phase_events, not sequences).
- D7 reports, D8 FTS rebuild, D4 WAL-safe swap + marker, D4b measurement.
- Gate: SC2 (+bug-kind probe, idempotent re-run), SC3(a)(b), SC4, SC6, the two i1 additions; suite green; diff ⊆ {rebuild_tool.py, tests, report artifacts}.

## Task 3 — Dual-write (D5)

- `_emit_v2_event` + five-writer wiring; update_entity emit IN-transaction fail-closed (+ counter machinery deleted); create_workflow_phase establishment event; presentational-exclusion comment; entity_engine.py:559 deletion (`_run_cascade` rollup/notifications retained; test_entity_engine.py 6 refs); cleanup_backlog.py archival-path emit VERIFIED (edit only if needed — record the verdict).
- Gate: SC7 + SC8 green on tool-built v2 files; v1 fixtures unaffected; diff ⊆ {database.py, entity_engine.py, cleanup_backlog.py?, test_entity_engine.py, test_database.py, test_dependencies.py, test_rebuild_tool.py} (D10 updated at plan-i1 to carry the test files).

## Task 4 — derive_kanban retirement (D6.1-.3 + comment sweep)

- kanban.py + test_kanban.py DELETED; six call sites rewired to stored values (workflow_state_server.py:1003/:1272, backfill.py:335, reconciliation.py:201, feature_lifecycle.py:205, engine.py:529); test_axes.py:530-543 RE-PINNED first; repo-wide test rewrites (test_constants, test_backfill, test_reconciliation, test_engine, doctor test_checks:956, mcp test_workflow_state_server TestCompletePhaseKanbanMatchesDeriveKanban, ui test_deepened_app); comments (axes.py:70, constants.py:4, router.py:70).
- Gate: suite green; zero `derive_kanban` tokens in plugins/pd/ EXCEPT rebuild_tool's token-free vendored copy (by construction), the not-yet-swept D6.4-.7 files, and schema_v2.py:64 (task 5); diff confined.

## Task 5 — Shims, remap, allocator, #075, SC5 gate (D6.4-.10)

- `_resolve_workspace_uuid_kwargs`(:6286) + 6 callers (:7085/:7381/:8070/:9423/:9883/:10034) + external project_id-passer sweep; `_atomic_write_workspace_mapping`(:1726) body deletion (call already gone at task 1); LEGACY_VALUE_REMAP + helpers/board/test_app; schema_v2.py:64 comment; create-project.md allocator rewrite + entity_server.py:673-682 guard removal + docstrings ~:640-649/:655 + `::test_allocator_cutover_project_kind`; #075 `_process_transition_entity_phase` → `get_machine(kind).validate()` + moved-legacy validator deletion.
- SC5 grep gate LAST (pattern: literal `derive_kanban`, `_resolve_workspace_uuid_kwargs`, `_atomic_write_workspace_mapping`, `LEGACY_VALUE_REMAP`, FR132-5b-scoped legacy `project_id` kwarg; scope plugins/pd/ per D6.10).
- Gate: full suite + hooks 67/67 + validate 0 errors; SC5 output recorded; diff-vs-develop ⊆ D10.

## Risks

- **Vendored-derivation drift** — `_frozen_kanban_derivation` byte-compared to kanban.py:25's logic at task-2 review (kanban.py still exists then).
- **update_entity fail-closed blast (task 3)** — abandon-feature/cleanup_backlog roll back on emit failure; SC8's classes cover the rollback.
- **Task-4 churn** — widest diff; isolated to its own gate at i1's split.
- **Live-DB window (H5)** — the tool never runs at import; suite uses tmp paths only; the REAL cutover of ~/.claude/pd is a MANUAL post-merge step, never in tests.
- **m11 residue** — between task 1 and task 5 the callerless `_atomic_write_workspace_mapping` body remains; harmless (gitignore absorbs #066 strays; no caller). 

## Verification (end of task 5)

Standard-scope suite green; hooks; validate; SC1-SC8 + FR132-7 + allocator + vocab-abort tests each named green; SC5 grep output recorded; diff-gate ⊆ D10; committed summary report present; the tool's manual-cutover runbook (print + marker) eyeball-verified.
