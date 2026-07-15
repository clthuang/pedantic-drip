# Design: 132-backfill-rebuild-tool

Implements spec.md (e70d2a7). Pointer-style; the spec's FR/SC/H text is binding — D-sections pin mechanics and resolve OQ-1/2/3.

## D1 — Build pipeline (Scope-model steps, connections pinned)

- **Step 1 (chain replay) = `EntityDatabase(staging_path)` construction, nothing more.** On an empty file `_migrate()` runs the full chain 1→19 (database.py:6210-6215, :10101-10112) — the sanctioned initial use the spec names; the tool then `.close()`s it. No hand-rolled replay loop.
- **Step 2 (selective v2 seed) = one raw `sqlite3.connect(staging_path)`** applying, in one transaction: `events` DDL + indices (events.py), the two views (views.py), 122's vocab triggers (axes.py `register_vocab_triggers` — grep exact symbol at implement), and `_metadata` rows `('v2_seeded','1')`. NOT `bootstrap_v2()` (spec: IF-NOT-EXISTS would skip chain-shaped tables silently). sequences/workspaces/entity_relations keep chain shapes.
- **Step 3 (stamp) = same raw connection**: upsert `schema_generation='v2'` + `schema_version=str(V2_SCHEMA_VERSION)` (#062's ON CONFLICT DO UPDATE lands in the shared upsert helper both generations use).
- **`_migrate()` generation guard (v1-layer edit, FR132-1):** first statement — `SELECT value FROM _metadata WHERE key='schema_generation'`; `'v2'` → `return`. Table-absent (pre-M1 file) → proceed (chain creates it). Guard lives ABOVE the version loop, so the phantom-migration-20 probe (SC1) discriminates guard vs empty-range.
- **Staging path:** `<dir>/entities.db.rebuild-<yyyymmdd>` beside the live file. The tool aborts if it already exists unless `--resume-check` re-verifies its report (idempotence per SC2).

## D2 — Backfill algorithm (order + dedup + remap)

Read the OLD file via `sqlite3.connect("file:...?mode=ro", uri=True)` — never EntityDatabase (its construction mutates). Import order (FK-safe): workspaces → entities in parent-topological order (parent_uuid before children; cycle = anomaly row, imported parentless with note) → entity_relations → workflow_phases rows → phase_events (copied, uuid/type-remapped, `source='backfill'` — the CHECK admits it, database.py:5224-5239) → v2 `events` emission per D3. Per-entity uuid7 re-mint into one in-memory `old→new` map applied everywhere (H1: whole import is ONE transaction on the staging connection).
Dedup (spec #054(a)): WITHIN-workspace `(workspace_uuid, type_id)` collision → keep newest `updated_at`, losers recorded as anomalies with their old uuids (their relations re-point at the survivor); cross-workspace collisions preserved. Empty/blank `entity_id`/`name` → normalized to `unnamed-<old-uuid-prefix>` + anomaly row. Every anomaly is a report entry, never a skip (prd.md:106).

## D3 — Event emission mapping (FR132-2b)

| Census source | axis | event_type | to_value |
|---|---|---|---|
| entity row (all kinds) | lifecycle | entity_created | NULL (payload carries old_uuid, kind, display fields) |
| phase_events of feature-kind (6-phase vocab) | pipeline | carried event_type | the phase (⊆ PIPELINE_PHASES) |
| phase_events of 5D/brainstorm/backlog/task kinds | lifecycle | carried event_type | the phase (lifecycle axis is vocab-free, axes.py:122-131) |
| final derived status per entity (derive_kanban ONCE, prd.md:142) | execution | status_backfilled | the derived value (⊆ EXECUTION_STATUSES) |

Pre-import (SC5 #077 clause): `SELECT DISTINCT` over every census phase/status/kind/relation-kind value, diffed against PIPELINE_PHASES/EXECUTION_STATUSES/the axis CHECK/the entities polymorphic CHECK/the phase_events vocab/`('fixes','blocks')` — mismatch aborts BEFORE any write, listing the offending values. Insert order within an entity: ascending domain timestamp (spec FR132-2; MAX(uuid) correctness).

## D4 — Cutover = rename swap (resolves OQ-1)

18 hard-coded `~/.claude/pd/entities/entities.db` literals + 8 `ENTITY_DB_PATH` readers exist; the swap touches NONE of them: (1) `chmod a-w` old + rename old → `entities.db.v1-readonly`; (2) rename staging → `entities.db`; (3) write marker `~/.claude/pd/migrations/v2-cutover.json` `{cutover_at, old_file, expiry: +30d, old_sha256, report_path}`; (4) print the H3 session-restart warning LOUDLY. Rollback = reverse renames (D10). FR132-6 fail-loud: the read-only chmod makes any stale writer raise `sqlite3.OperationalError: attempt to write a readonly database` — the test asserts exactly that; the doctor gains a marker-aware check at 133 (not here — spec Non-goals).

## D5 — Dual-write wiring (FR132-4b, five writers)

- `append_phase_event` (database.py, the transition/complete/cascade path): inside its existing transaction, after the phase_events INSERT, emit the v2 `events` row (same axis mapping as D3's live half). ONE new private helper `_emit_v2_event(conn, ...)` shared by all writers — single implementation, no drift.
- `update_entity` status branch: the post-commit fail-open `append_phase_event` call (~:7930-8020) MOVES inside the transaction and the `except`-swallow around it is REMOVED for status-changing calls (fail-closed); `audit_emit_failed_count` bookkeeping stays only for non-status metadata-only paths if any remain.
- `create_workflow_phase` (:9178): emits the establishment event (pipeline or lifecycle axis per kind; to_value = initial workflow_phase, NULL-safe) in its INSERT transaction.
- `update_workflow_phase`/`upsert_workflow_phase`: excluded (presentational; recorded in code comment referencing the guard's fix_hint).
- `register_entity`/`upsert_entity`/`delete_entity`: entity_created / entity_deleted lifecycle events in their existing transactions.
- **#080 single-fire decision: the EXPLICIT `_run_cascade` path survives; the `:7574`-class DB trigger is DROPPED** in the same change (visible, steppable, already carries 124's per-flip transaction semantics; a trigger cannot emit the v2 event). SC8 asserts exactly one `cascade_ready` per flip.
- Design re-ran the #078 pass over `_PERMITTED_ENCLOSING_DEFS` (check_status_write_path.py:31-39): no sixth production writer exists at HEAD; doctor fix actions route through `update_entity`/`append_phase_event` (verify at implement with the guard's own AST walk).

## D6 — Deletion inventory (file-by-file, from spec FR132-5 + gate-r1 sweep)

1. `workflow_engine/kanban.py` — module DELETED (derive_kanban + helpers). test_kanban.py DELETED.
2. Six call sites rewired to stored values: workflow_state_server.py:1003/:1272, backfill.py:335, reconciliation.py:201, feature_lifecycle.py:205, engine.py:529.
3. Test rewrites: test_constants.py, test_backfill.py, test_reconciliation.py, test_engine.py, doctor/test_checks.py:956, mcp/test_workflow_state_server.py (TestCompletePhaseKanbanMatchesDeriveKanban → asserts stored-value equality instead), ui/tests/test_deepened_app.py:1015-1020; test_axes.py:530-543 subset pin RE-PINNED against D3's execution-axis writers BEFORE kanban.py deletes.
4. `_resolve_workspace_uuid_kwargs` (database.py:6285) + its callers' legacy `project_id` params + entity_server tool params (design grep at implement start; update_entity's `_resolve_identifier` alias :7863 is OUT of scope — spec SC5 qualifier).
5. `_atomic_write_workspace_mapping` (database.py:1726) + migration 11's :1861 call (DDL-neutral edit — spec FR132-5b NOTE; chain-replay test re-run proves identity).
6. `LEGACY_VALUE_REMAP` + resolve_execution_status simplification (helpers.py:144-160), board.py:28 docstring, ui/tests/test_app.py:258-374 rewrite.
7. Comment/docstring sweep: axes.py:70, constants.py:4, router.py:70, schema_v2.py:64 ("132" note updates to done), imports.
8. #075: transition_entity_phase → `get_machine(kind).validate()` for lifecycle kinds; moved-legacy validators deleted (router.py + workflow_state_server handler).

## D7 — Report artifact (resolves OQ-3)

Machine report (full, entity-named): `~/.claude/pd/migrations/rebuild-report-<ts>.json` — outside the repo, no leak. Committed artifact: `docs/features/132-backfill-rebuild-tool/rebuild-report-summary.md` — COUNTS ONLY (per kind × workspace, anomaly-class tallies, checksum, duration), zero entity names. SC2's parity assertions run against the machine report.

## D8 — FTS (resolves OQ-2)

After the import transaction commits: `INSERT INTO entities_fts(entities_fts) VALUES('rebuild')` once (533 rows — trivial). The chain's sync triggers keep it live thereafter (verify trigger presence via the step-1 file's sqlite_master in the SC1 test).

## D9 — Test map (SC → named test)

SC1 test_rebuild_tool.py::test_fresh_bootstrap (+ phantom-migration-20 guard probe + trigger-fires probe); SC2 ::test_backfill_parity_pathological_corpus (+ ::test_idempotent_rerun); SC3 ::test_replay_reproduces_views (FR-11 field set); SC4 ::test_resolver_explain_and_latency; SC5 shell grep gate in the verification script + ::test_preimport_vocab_diff_aborts; SC6 ::test_old_file_readonly_and_marker; SC7 ::test_backlog_registration_visible_immediately + ::test_phase_event_exists_after_success; SC8 ::test_dual_write_per_class (6 classes) + ::test_emit_failure_rolls_back_status + ::test_cascade_single_fire.

## D10 — File inventory (diff gate) + rollback

New: `entity_registry/rebuild_tool.py` (+ its test), `rebuild-report-summary.md`, marker JSON (untracked, ~/.claude). Modified: database.py (guard, dual-write emits, deletions incl. m11 :1861, trigger drop), dependencies.py (cascade fire), events.py/axes.py/views.py (only if step-2 DDL needs export helpers), workflow_state_server.py, entity_server.py, reconciliation.py, feature_lifecycle.py, engine.py, router.py, helpers.py, board.py (docstring), schema_v2.py:64, cleanup_backlog.py (if its archival path needs the emit — verify), 12+ test files per D6. Deleted: kanban.py, test_kanban.py. Anything outside this list = diff-gate failure.
Rollback: pre-swap = delete staging; post-swap = reverse renames (old file untouched, still read-only — chmod back). The live DB at `~/.claude/pd` is NOT touched by the suite (all tests run on tmp paths; H5 discipline — the tool runs only via explicit CLI invocation).
