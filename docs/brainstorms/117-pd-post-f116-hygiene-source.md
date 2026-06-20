# Feature 117 Brainstorm Source: pd Post-F116 Production Hygiene

**Source:** Empirically-discovered open work items from doctor + entity DB survey conducted 2026-05-18 after F116 merge. Three themes bundled into one feature for atomic landing — they share a common root (state reconciliation + version-pin debt from F108-F116 sequence) and small-fix character (no new functional surface).

## Problem Statement

After F116 closed F115's 8 HIGH carry-forwards (severity rollup + AST vocab + standalone helper + defensive parser), a post-merge audit surfaced 5 actionable items that the F116 retro identified but did not address (out of scope for coverage-only feature). They cluster into three themes:

### Theme A — Production bug: cross-workspace re-attribute fails against immutable trigger

`_fix_triage_cross_workspace_link` at `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py:472-482` issues `UPDATE entities SET workspace_uuid = ?` directly for the `re-attribute parent` and `re-attribute child` branches. Production entities.db has the `enforce_immutable_workspace_uuid` trigger active (post-Migration-11), which rejects this UPDATE with `'workspace_uuid is immutable — use re-attribution API'`. Two of the four triage branches are therefore broken in production. **Discovered during F116 TC.4** but flagged for follow-up (out of scope for coverage-only feature).

**Evidence:**
- `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py:472-482` — the UPDATE statements
- `plugins/pd/hooks/lib/entity_registry/database.py` — `enforce_immutable_workspace_uuid` trigger definition
- `plugins/pd/hooks/lib/entity_registry/database.py:7956-7975` — `claim_unknown_entities` shows the correct pattern (drop trigger, UPDATE, recreate)
- F116 retro: `docs/features/116-f115-qa-deferred/retro.md` (Reflections #2; "Production gap filed for F117" appendix)

### Theme B — Doctor check version pin debt

Two doctor checks emit `severity='error'` because their hardcoded "expected" version constants are stale relative to current schema versions:

- `db_readiness`: expects schema_version=11, actual=17 (F115 added M15/M16/M17 + F108-114 added more)
- `memory_health`: expects schema_version=4, actual=7 (F115 added M6/M7; earlier features added M5)

These check the WRONG direction — they think the schema is "ahead of expected" rather than "behind." The fix is to use `max(MIGRATIONS.keys())` dynamically (per F115 retro KB candidate #6, validated by F116 test-fixture sweep cost). Same dynamic pattern would obviate ~30 other hardcoded `schema_version == "N"` assertions in `test_database.py` files (both entities + semantic_memory).

**Evidence:**
- Doctor output: 2 errors with messages "Entity DB schema_version is 17, expected 11" and "Memory DB schema_version is 7, expected 4"
- `plugins/pd/hooks/lib/semantic_memory/database.py:517` — `MIGRATIONS: dict[int, ...]` module-level dict
- `plugins/pd/hooks/lib/entity_registry/database.py` — equivalent MIGRATIONS dict
- F115 retro KB candidate #6 + F116 retro KB candidate "deferring dynamic-fixture refactors" anti-pattern

### Theme C — State reconciliation across F108-F116 MCP-unavailable sessions

The entity DB shows accumulated drift from sessions where the MCP entity-server was unavailable (lingering M12 from F108):

- **132 `feature_status` doctor warnings** — `.meta.json` `status` field for completed/archived features doesn't match the entity DB
- **129 `workflow_phase` doctor warnings** — phase_events sequence drift; many features have phase transitions that weren't recorded in DB
- **250 `entity_orphans` doctor warnings** — entities with `parent_uuid` pointing at deleted/missing parents OR entities whose parent_uuid is set but should be NULL
- **4 stale brainstorms** with status `active` that should be `promoted`: `20260516-210137-pd-followups` (F115 brainstorm), `20260516-184258-pd-data-model-hardening` (F114 brainstorm), `20260517-053927-f115-qa-deferred` (F116 brainstorm), and `20260327-050000-phase-transition-summary` (older). These weren't transitioned via MCP when their parent features were created.
- **21 cross-workspace `parent_uuid` links** (warning-only) — the F115-time pin; unchanged. F116 built the triage tool but Theme A bug blocks it. Once Theme A is fixed, these can be triaged via `pd:doctor --fix` or direct invocation.

Most of these resolve via a single `reconcile_apply` call (now that MCP is available). The brainstorm statuses are explicit `update_entity` calls. The cross-workspace links require the triage UX once Theme A unblocks it.

**Evidence:**
- Doctor output: see counts above
- `sqlite3 ~/.claude/pd/entities/entities.db "SELECT kind, status, COUNT(*) ..."` confirms 4 stuck-active brainstorms + 21 open backlog (separate scope) + 0 active features (clean post-F116)
- F114, F115, F116 `.meta.json` reviewerNotes all reference "MCP entity-server unavailable; manual .meta.json fallback per use-mcp-not-manual-json exception"

## Scope (3 themes bundled)

**Tier 1 — Theme A (production blocker; 1 code-surface change)**: Wrap re-attribute branches in `_fix_triage_cross_workspace_link` with the `BEGIN IMMEDIATE; DROP TRIGGER enforce_immutable_workspace_uuid; UPDATE...; <recreate trigger>; COMMIT` pattern from `claim_unknown_entities:7956-7975`. Add regression tests that exercise re-attribute against a DB with the trigger active (test_fix_actions.py TC.4 test currently drops the trigger in fixture — that masked the production bug).

**Tier 2 — Theme B (test-fixture hygiene; 30-50 site sweep)**: Replace hardcoded `expected_version` constants in `db_readiness` and `memory_health` doctor checks with `max(MIGRATIONS.keys())` import. Then sweep ~30 hardcoded `schema_version == "N"` and `len(CHECK_ORDER) == N` assertions across `test_database.py` (entities + semantic_memory) + `test_checks.py` to use dynamic references. Mechanical sed-replace; bounded one-shot work.

**Tier 3 — Theme C (operational cleanup; reconcile + targeted updates)**: Invoke `reconcile_apply` to flush feature_status + workflow_phase drift (132 + 129 = 261 doctor warnings). Then run targeted `update_entity` calls for the 4 stuck-active brainstorms. Then invoke `_fix_triage_cross_workspace_link` for each of the 21 cross-workspace links (depends on Theme A landing first). Verify post-reconcile that doctor reports < 50 issues.

## Empirical Pins (verified 2026-05-18 at session start)

| Pin | Source-of-truth | Value |
|-----|-----------------|-------|
| Doctor total issues | `python -m doctor` JSON output | 537 (2 error / 534 warning / 1 info) |
| `entity_orphans` count | Per-check `issues_count` | 250 |
| `feature_status` count | Per-check | 132 |
| `workflow_phase` count | Per-check | 129 |
| `cross_workspace_parent_uuid` count | Per-check | 21 (unchanged from F115) |
| `db_readiness` actual schema_version | `_metadata.schema_version` | 17 (entities) |
| `db_readiness` expected schema_version | doctor check constant | 11 (stale) |
| `memory_health` actual schema_version | `_metadata.schema_version` | 7 (memory) |
| `memory_health` expected schema_version | doctor check constant | 4 (stale) |
| Stuck-active brainstorms | entities table query | 4 |
| Open backlog (separate scope) | entities table query | 20 |
| F116 production bug location | `fix_actions/__init__.py` | lines 472-482 |
| Trigger drop pattern reference | `database.py` `claim_unknown_entities` | lines 7956-7975 |

## Out of Scope (explicit Non-Goals)

- 17 MED test-deepener findings from F116 retro (separate F-next feature; see F116 retro §17-MED).
- 20 open backlog items from F088/F089 (all LOW; date 2026-04-20; not relevant to current state).
- 250 `entity_orphans` — needs targeted investigation of which orphans are valid vs invalid; out of scope for a hygiene feature. Most will likely auto-resolve via reconcile.
- New MCP tools, new migrations, new exception classes (matches F116 constraints).

## Risk + Resolution Strategy

1. **HIGH — Theme A regression test must reproduce production behavior.** The F116 TC.4 test drops the trigger in fixture (this masked the bug). New regression test MUST run against the actual trigger-active state. Mitigation: invert the fixture — don't drop the trigger; assert the fix succeeds.

2. **MED — Theme B test-fixture sweep introduces TestFailure noise during the refactor.** ~30 sites all swap to dynamic. Mitigation: do it in one commit (mechanical sed-replace), run full pytest after, expect 0 regressions.

3. **MED — `reconcile_apply` may produce unexpected DB writes.** Three sessions of accumulated drift means the reconcile output could be large. Mitigation: dry-run first via `reconcile_check`; review the diff; then apply.

4. **LOW — 21 cross-workspace links may not all be triage-able.** Some may need human judgment (which workspace is "correct"?). Mitigation: run triage in interactive mode (NOT YOLO) for this step; user picks per link.

## Reference Files

F116 + F115 inheritance — F117 should reuse rather than re-derive:

- F116 retro: `docs/features/116-f115-qa-deferred/retro.md` (production gap + KB predictions)
- F116 spec: `docs/features/116-f115-qa-deferred/spec.md` (FR-7 + FR-9 patterns for re-attribute SQL semantics)
- F115 retro: `docs/features/115-pd-data-model-followups/retro.md` (KB candidate #6: dynamic-fixture refactor)
- F115 design rev 2: `docs/features/115-pd-data-model-followups/design.md` (C13/C14 cross-workspace components)

## Implementation Strategy

Theme A first (production blocker; unblocks Theme C link triage). Theme B second (mechanical sweep; low risk). Theme C third (depends on A; requires interactive judgment for 21 links).

Within Theme A:
1. Write failing test that runs re-attribute against trigger-active DB (without dropping trigger in fixture)
2. Add trigger-drop-update-recreate pattern to `_fix_triage_cross_workspace_link`
3. Verify F116 TC.4 tests still pass (they should — they explicitly drop the trigger so the new logic is a no-op for them)
4. Add a second regression test ensuring trigger is restored after the UPDATE (atomicity)

Within Theme B:
1. Add `max(MIGRATIONS.keys())` import path to both doctor check files
2. Replace `expected_version` constants with dynamic
3. Grep for hardcoded `schema_version == "N"` and `len(CHECK_ORDER) == N` across test files
4. Mechanical sed-replace to dynamic references
5. Full pytest to verify 0 regressions

Within Theme C:
1. `reconcile_check` dry-run; capture diff to retro
2. `reconcile_apply` to flush
3. `update_entity` for each of 4 stuck-active brainstorms → `promoted`
4. For 21 cross-workspace links: run `_fix_triage_cross_workspace_link` via doctor harness — interactive prompts per link
5. Post-fix doctor sanity check: expect << 50 issues remaining

## YOLO Mode Constraints

Per established F114/F115/F116 pattern:
- Run full ritual (brainstorm → specify → design → create-plan → implement → finish).
- Compress reviewer iterations.
- Merge to develop ONLY (never main).
- Release script triggers separately as v4.18.3 (or higher) after F117 lands on develop.
- Theme C link triage step requires user interaction — break YOLO mode for that one step (acceptable per harness, since interactive choice is the design intent of the triage UX).
