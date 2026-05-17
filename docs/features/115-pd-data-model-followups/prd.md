# PRD: pd Data-Model + Memory Followups (Feature 115)

## Status

- Created: 2026-05-16
- Brainstorm source: `docs/brainstorms/115-pd-followups-source.md`
- Reference artifacts: `docs/features/114-pd-data-model-hardening/{spec.md,design.md,retro.md}` (canonical evidence base — DO NOT re-derive)
- Mode: Standard (YOLO)
- Problem Type: Technical/Architecture
- Archetype: exploring-an-idea

## Problem

Feature 114 fixed 3 production blockers (M12 stub trap, workspace fallback, capture hook noise) and deferred 5 sub-clusters because of risk or prerequisite-triage concerns. Feature 115 picks up the deferred work as a single bundled feature per user explicit instruction:

1. **Cluster C — audit invariant**: `db.update_entity` does not emit `entity_status_changed`. Production phase_events: **0 such events out of 945**. F111-stated invariant has never held. Deferred from 114 because: 17 production callers + F111 manual-emit removal + AST whitelist removal = high test-fixture breakage risk requiring careful sweep. — Evidence: 114/spec.md Pin F.1; SQL queries against `~/.claude/pd/entities/entities.db`.

2. **Cluster E — cross-workspace gates**: 3 MCP write paths (`set_parent`, `add_dependency`, `add_okr_alignment`) lack the assertion that `issue_spawn` got in F111. **21 live cross-workspace `parent_uuid` links** in production. — Evidence: 114/spec.md Pin E; direct DB query.

3. **Cluster E.2 — cross-workspace triage tool**: Doctor fix_action with per-link AskUserQuestion offering re-attribute/delete/grandfather. Prerequisite for E hardening (otherwise gates blockade valid workflows).

4. **Cluster B-H3 — writer CLI quality gates**: 91% of memory entries (1441/1581) enter via CLI back door bypassing 20-char min / 0.95 near-dup / 0.90 dedup-merge gates.

5. **Cluster B-H4 — hash-drift backfill + 114 B-H2 cleanup follow-through**: 10 entries inflated to `observation_count=1438` from `writer.py:72` vs `importer.py:86` hash-input disagreement. **Plus** the 464 `Tool failure:%` noise rows that 114 retro-marked as "B-H2 landed" but where only the HOOK SOURCE file deletion shipped (commit `f60e3f58`) — the actual DELETE migration body was placed inside `_migration_6_unify_source_hash` per 114 FR-B-H2.2, and that migration was deferred along with the rest of B-H4. Grep confirms zero `DELETE FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%'` across the repo. The 464 rows still live in `~/.claude/pd/memory/memory.db`.

## Goals / Success Criteria

1. **Audit invariant (observability-grade)**: 100% of `update_entity(status=...)` mutations either emit `entity_status_changed` event OR emit `pd.audit.emit_failed` stderr line + `audit_emit_failed_count` increment. Verified per-callsite for the 17 enumerated callers (pin count re-verified during specify per Open Question #5).
2. **Single-commit, single-emit (FM-1 binary AC)**:
   - **Atomicity**: The commit that inserts the `db.update_entity` emit in `plugins/pd/hooks/lib/entity_registry/database.py` MUST also delete the F111 manual emit block in `plugins/pd/mcp/workflow_state_server.py` (the `db.append_phase_event(event_type='entity_status_changed', metadata={'closed_by_uuid': ...})` call inside the closure_targets loop — specify-phase re-pins exact line range; 114 spec Pin F.1 entry #3 said 1344-1356 but HEAD shows ~1364-1375). Content-based selector preferred over line-number selector for the implement-phase pre-commit assertion (refuses commit if either side is missing).
   - **Runtime exactly-once**: Integration test `test_complete_phase_closes_emits_exactly_once` asserts `SELECT COUNT(*) FROM phase_events WHERE event_type='entity_status_changed' AND type_id=?` == 1 per closed entity (NOT 2 — that would mean both sources fired; NOT 0 — that would mean neither fired). Required to pass before merge.
3. **Cross-workspace isolation**: `set_parent`, `add_dependency`, `add_okr_alignment` reject cross-workspace inputs with typed `error_type=cross_workspace_forbidden` envelope. New doctor check `check_cross_workspace_parent_uuid` emits per-link issues with `severity='warning'` (NEVER `'error'`, NEVER `'suggestion'`; bound to 114 IF-9 vocabulary `{error, warning, info}`). Acceptance test runs doctor against DB with N cross-workspace `parent_uuid` rows (N pinned during specify) and asserts `severity_summary.warning >= N` AND `severity_summary.error == 0`.
4. **Post-triage**: After E.2 triage tool runs and operator chooses allow/re-attribute/delete per link, `SELECT COUNT(*)` of unallowlisted cross-workspace `parent_uuid` rows == 0.
5. **Memory hygiene (115 scope, NOT inherited from 114 — DELETE never shipped)**:
   - `writer.py:main` calls `_apply_quality_gates` exactly once before `db.upsert_entry`. AST/grep confirms gate logic appears once in `memory_server.py`.
   - All inflated entries (114 pinned 10 at `observation_count=1438`; specify-phase re-pins) reset to `observation_count=1` via M7 migration body.
   - All `Tool failure:%` rows (114 pinned 464; specify-phase re-pins to 464±50) deleted via M6 migration body. **This is NEW work — 114's `f60e3f58` only deleted the hook source file, not the historical rows.**

## Non-Goals (explicit deferrals)

- **Hard-error escalation for Cluster E doctor check** — gates remain warning-only at end of 115; future feature can escalate after operator confidence builds.
- **Full event-sourcing audit retrofit** — observability-grade fail-open emit only.
- **Re-attribution of `_UNKNOWN_WORKSPACE_UUID` entities** — separate concern; 114 carry-forward.
- **Fingerprint-based M12 detector** — 114 shipped column-presence approach; sufficient.
- **AST whitelist removal in 115** — AST whitelist removal at `check_status_write_path.py:37` is **deferred to feature 116** (not 115). 115 ships the `update_entity` emit + same-commit F111 manual-emit removal only. The whitelist stays in place at end of 115 so test fixtures calling `db.update_entity(status=...)` directly continue passing without a parallel test-fixture sweep. **Consequence**: 114 spec FR-C.5 (test-fixture sweep + `_PERMITTED_TEST_FILES` allowlist authoring) is also deferred to 116 — 115 does NOT need to touch test files calling `db.update_entity(status=...)` because the whitelist still allows the call. Feature 116 can do the sweep + whitelist removal once 115 lands and operators confirm no regressions. (Per 114 retro TD-7 and Pre-Mortem FM-4 risk-reduction.)

## Cluster Sequencing (per 114 retro + advisor recommendations)

```
[Tier 1] Cluster C        (audit invariant; highest correctness value)
            → M15 (entities.db, audit_emit_failed_count)
   ↓
[Tier 2] Cluster E.2      (triage tool + Migration 17 — must land before E hardening)
            → M17 (entities.db, cross_workspace_allowlist table)
   ↓
[Tier 2] Cluster E        (cross-workspace gates; warning-only doctor check)
            → no migration; helper + handler refactor only
   ↓
[Tier 3] Cluster B-H3     (writer CLI quality gate extraction)
            → no migration; helper extraction only
   ↓
[Tier 3] Cluster B-H4     (hash unify + Tool-failure cleanup + observation reset)
            → M6 (memory.db, source_hash unify + `Tool failure:%` DELETE — 114 FR-B-H2.2 carried forward; the DELETE NEVER shipped in 114, only the hook source did)
            → M7 (memory.db, observation_count reset for inflated entries)
```

**Migration numbering** (verified during specify per Open Question #1):
- entities.db current head: M14 (verified via `MIGRATIONS` dict at `plugins/pd/hooks/lib/entity_registry/database.py:5404`).
- memory.db current head: M5 (verified via `test_database.py:85` assertion `db.get_schema_version() == 5`).
- New entries: entities.db M15 + M17; memory.db M6 + M7.
- Specify-phase guard: `grep -c '_migration_1[5-9]_' plugins/pd/hooks/lib/entity_registry/database.py == 0` AND `grep -c '_migration_[6-9]_' plugins/pd/hooks/lib/semantic_memory/database.py == 0` before assigning new numbers.

**80/20 fallback if implement time exhausts** (per Opportunity-Cost advisor):
- **Floor**: C + E.2 + E (Tier 1 + Tier 2). These are highest correctness/risk-reduction value and have hard sequencing dependencies (E.2 before E).
- **Drop order under time pressure**: drop **B-H3 first**, then **B-H4** (note: this is the INVERSE of the original Opportunity-Cost #3 work-sharing claim — the cross-validation of `_apply_quality_gates` against B-H4 manifest is nice-to-have but not load-bearing; preserving B-H4 over B-H3 means the 464 noise rows + 10 inflated entries get cleaned even if B-H3's CLI-gate-extraction has to slip). If implementation prefers to retain the cross-validation, drop B-H4 first instead — but the consequence is that historical noise rows persist into 116.

## Strategic Analysis

### Pre-Mortem Advisor

**Top 5 failure modes** (full text condensed for PRD; see brainstorm source):

- **FM-1 CRITICAL — Double-emit on Cluster C** if F111 manual-emit removal is NOT same-commit as `update_entity` emit insertion. Blast: AC-C.1 "exactly one row" invariant fails; audit-counter doctor check may break MCP startup. Mitigation: end-to-end test `complete_phase(closes=[...])` asserts `COUNT(entity_status_changed) == 1` before merge.

- **FM-2 HIGH — Cluster E doctor check escalates to hard error**. Blast: MCP startup breaks if doctor blocks on 21 existing links. Mitigation: new doctor check `check_cross_workspace_parent_uuid` bound to 114 IF-9 severity vocabulary `{error, warning, info}` (NOT `suggestion`); explicit integration test asserts `severity='warning'` for ALL emitted issues (not error, not info); triage tool E.2 must ship in same feature so user has recovery path.

- **FM-3 HIGH — B-H4 cleanup query deletes wrong rows**. 114 FR-B-H4.3 uses the predicate `UPDATE entries SET observation_count=1 WHERE source='import' AND observation_count > 100`; if a new legitimate `source='import'` entry with `observation_count>100` lands between manifest freeze and M7 application, it gets silently reset. Mitigation: **keep the 114 predicate** (no need to invent a frozen-ID-list override) **but gate it with a bounded count assertion** — specify-phase pins `expected_count = 10` (or re-pinned value), and M7 migration body asserts observed count is within `expected_count ± 2` before applying the UPDATE; aborts otherwise. This is functionally equivalent to the frozen-ID-list risk-control without the schema bookkeeping. The M6 Tool-failure DELETE uses the same bounded-count gate (`expected_count = 464 ± 50`). **Recovery path on abort**: M6/M7 emit a stderr diagnostic listing observed vs. expected, hint at root-cause investigation (hook regression for M6; import-tool regression for M7), and instruct operator to (a) investigate the drift source, (b) optionally amend the spec to update the bounded range, (c) re-run the migration after pin refresh. Bounded-count gates without explicit recovery paths tend to become stuck-migration traps; the diagnostic + amend-spec path prevents that.

- **FM-4 MEDIUM — AST whitelist removal breaks tests** if test-file sweep is incomplete. Mitigation: explicit pre-removal sweep task running `rg 'db.update_entity.*status' plugins/pd/hooks/lib --include='*.py' -l`; every match must be either covered by new emit OR added to `_PERMITTED_TEST_FILES`.

- **FM-5 MEDIUM — B-H2 cleanup query miscounted as "already shipped"** (corrected from prior PRD draft; the DELETE never ran). The 114 retro and `f60e3f58` commit only deleted the HOOK SOURCE FILE (`capture-tool-failure.sh` heuristic branch), preventing NEW noise rows. The DELETE migration body that would clean the existing 464 historical rows was placed inside `_migration_6_unify_source_hash` per 114 FR-B-H2.2, and that migration was deferred along with the rest of B-H4. Grep across the repo for `DELETE FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%'` returns 0 matches. **Risk if PRD/spec inherits the false belief**: 115 would skip the DELETE and the 464 rows persist indefinitely. **Mitigation**: explicitly include the DELETE in M6 body; specify-phase re-runs the count query against live memory.db and pins expected_count ± 50; M6 migration aborts if observed_count is outside that range (prevents silent drop or over-deletion of new entries that landed between freeze and migration).

— Evidence Quality: strong

### Opportunity-Cost Advisor

**Verdict on bundle (per user explicit direction):** All 5 clusters bundled; no scope challenge from this advisor. Honest assessment: 5-cluster bundle is materially less risky than 114's 7-cluster scope because (a) artifacts are pre-existing, (b) implementations are smaller-scope changes (no migration recovery), (c) clear sequencing.

**Concrete work-sharing opportunities identified for implement phase:**

1. **AskUserQuestion harness shared between E.2 + B-H4 dry-run**. Extract `_interactive_triage_loop(items, build_question_fn, apply_fn)` helper in `doctor/fix_actions/`. Saves ~40 lines + shared test coverage.

2. **Migration registration single-pass**: M15 (entities.db, Cluster C) + M17 (entities.db, Cluster E.2) + M6/M7 (memory.db, Cluster B-H4) all registered in same MIGRATIONS dict pass per their respective DB.

3. **`_apply_quality_gates` cross-validates B-H4 manifest**: B-H4's dry-run should run incoming entries through B-H3's extracted helper to confirm the noise-row count (expected 464) matches what the gate would reject post-extraction.

**Drop candidates under time pressure:** B-H3, then B-H4 (in that order). C + E + E.2 are the floor.

— Evidence Quality: strong

## Approaches Considered

**Approach 1 (chosen): Single feature 115 with all 5 clusters in 3 tiers**
- Pro: User explicit instruction; sequencing locked; pre-existing artifacts reduce per-cluster cost.
- Pro: 80/20 fallback already identified (drop B-H4, then B-H3 if time pressure hits).
- Con: ~4-5 hour implement window; if any tier blocks, downstream tiers blocked too.

**Approach 2 (rejected): 115 (C+E+E.2) + 116 (B-H3+B-H4)**
- Con: User explicitly rejected this split.

## Constraints

- **Cluster D (workspace fallback) is a hard prerequisite for Cluster C** — D landed in 114 commit `7591cd2b`. Implement-phase verifies only the canonical FR-D.1 fix at `plugins/pd/mcp/workflow_state_server.py:1190` is intact (`rg '_workspace_uuid or _UNKNOWN_WORKSPACE_UUID' plugins/pd/mcp/workflow_state_server.py` returns ≥1 hit). Note: `entity_server.py:567` and `:710` intentionally retain `_workspace_uuid or ""` per 114 retro (FR-D.2 reverts because the change broke `test_register_entity_handler_concise_message`) — those reverts are accepted and out-of-scope for 115.
- **Cluster C 17-caller blast radius** — `update_entity(status=...)` callers span workflow_engine, reconciliation_orchestrator, doctor/fix_actions, scripts/cleanup_backlog, mcp/entity_server, mcp/workflow_state_server, entity_registry/dependencies, entity_registry/entity_lifecycle. Emit must be fail-open (try/except wrap; status UPDATE has already committed before emit attempts). Pin count re-verified during specify-phase.
- **F111 manual-emit removal MUST be same-commit as Cluster C emit insertion** — non-atomic commit triggers FM-1. Binary AC: single git commit contains both `database.py` emit insertion AND `workflow_state_server.py:1344-1356` deletion.
- **Cluster E doctor check warning-only** — new check `check_cross_workspace_parent_uuid` bound to 114 IF-9 severity vocabulary `{error, warning, info}` (NOT `suggestion`). Escalation to error blocks MCP startup (FM-2).
- **B-H4 cleanup queries gated by bounded count** — keep 114 FR-B-H4.3 predicate semantics; specify-phase pins expected counts (464 ± 50 for Tool-failure DELETE; 10 ± 2 for observation reset); migration aborts if observed count is outside the pinned range. Functionally equivalent to a frozen-ID-list (FM-3 mitigation) without the schema bookkeeping.
- **B-H4 implement-phase pin refresh BEFORE migration body lands** — implement-only sequencing gate. Refresh count assertions from live `~/.claude/pd/memory/memory.db` immediately before authoring M6/M7 bodies.
- **AST whitelist removal NOT in 115 scope** — deferred to feature 116 per Non-Goals (FM-4 risk-reduction; avoids test-fixture sweep coupling).
- **B-H2 `Tool failure:%` DELETE is NEW work in 115** — 114's `f60e3f58` only deleted the hook source file, not historical rows. M6 must include the DELETE (with bounded-count gate). DO NOT inherit the false "already shipped" framing from earlier PRD drafts (FM-5 corrected).
- **Merge to develop only, never main** — per user memory.
- **YOLO autonomous; reviewer iter cap 3 per phase; compress where reasonable.**

## Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Cluster C double-emit if same-commit broken | CRITICAL | Single-commit assertion in plan (git log resolves database.py emit insertion + workflow_state_server.py:1344-1356 deletion to same SHA); integration test asserts `COUNT(entity_status_changed) == 1` per closure |
| Cluster E doctor check escalates to hard-error | HIGH | New check bound to 114 IF-9 severity vocab `{error, warning, info}`; integration test asserts ALL emitted issues use `severity='warning'`; E.2 ships in same feature |
| B-H4 cleanup deletes new entries silently | HIGH | Keep 114 predicate semantics; gate with bounded-count assertion (464 ± 50 for DELETE; 10 ± 2 for observation reset); migration aborts if outside range |
| B-H2 `Tool failure:%` DELETE silently dropped from 115 scope | HIGH | FM-5 explicitly flags the 114 retro miscount; Goal #5 + Constraints reinforce that the DELETE is NEW work in 115 (M6 body) |
| Pin staleness — 114 numeric pins may have drifted | MEDIUM | Specify-phase re-runs 5 pin queries (17 callers, cross-workspace links, 464 Tool-failure rows, 10 inflated entries, schema heads) against current code/DB state; PRD-stated values become bounds, not exact targets |
| AST whitelist accidentally removed in 115 | MEDIUM | Non-Goals explicitly defers to feature 116; plan-phase task list MUST NOT include whitelist-removal task |
| Session time exhaustion mid-implementation | MEDIUM | 80/20 drop order: B-H3 first, then B-H4 (preserves 464-row + observation cleanup over CLI-gate-extraction); C+E.2+E are floor |
| Implement-phase work-sharing missed | LOW | Extract `_interactive_triage_loop` helper early (shared between E.2 + B-H4 dry-run); single migration registration pass |

## Open Questions (deferred to specify)

1. **Entities.db migration head**: M14 was head at 114-merge (verified via `MIGRATIONS` dict at `plugins/pd/hooks/lib/entity_registry/database.py:5404`). Re-verify during specify: `grep -cE "def _migration_1[5-9]_" plugins/pd/hooks/lib/entity_registry/database.py == 0` before assigning M15/M17.
2. **Memory.db migration head**: M5 is current head (verified via `plugins/pd/hooks/lib/semantic_memory/test_database.py:85` assertion `db.get_schema_version() == 5`). Re-verify during specify: `grep -cE "def _migration_[6-9]_" plugins/pd/hooks/lib/semantic_memory/database.py == 0` before assigning M6/M7.
3. **B-H4 cleanup-query scope**: Specify confirms — keep 114 FR-B-H4.3 predicate (`source='import' AND observation_count > 100`) gated by bounded-count assertion (10 ± 2 for observation reset; 464 ± 50 for Tool-failure DELETE). Override 114 only if specify-phase re-pinning shows counts have drifted >10% from 114 numbers; in that case, recompute ± ranges.
4. **Interactive triage loop helper location**: `doctor/fix_actions/_interactive.py` or `doctor/utils/triage.py` — pick during specify based on existing fix_action conventions.
5. **F111 manual-emit removal — single commit boundary**: spec/plan must encode the atomic commit invariant for Cluster C.1+C.2 as a single task with explicit pre-commit assertion (refuse commit if either side is missing).
6. **Specify-phase pin refresh**: Re-verify 5 numeric pins against current state — (a) 17 `update_entity(status=...)` callers via 114 Pin F.1 rg command, (b) cross-workspace link count via 114 AC-E.5 SQL, (c) `Tool failure:%` row count, (d) inflated-observation entry count, (e) entities.db/memory.db migration heads. Update Goal acceptance thresholds to reflect drift. Note: user's local DB was rolled back to schema_version=11 mid-114-session (per 114 retro) so some runtime counts may differ from 114-time snapshots.

## Next Steps

→ Promote to Feature → `/pd:specify` to crystallize FRs and ACs (largely derivable from 114 spec rev 4) → `/pd:design` (largely derivable from 114 design rev 2 with refinements per advisor risks) → `/pd:create-plan` honoring tier sequencing → `/pd:implement` per tier with same-commit invariants enforced → `/pd:finish-feature` merge to develop.

## Reference Files

- Feature 114 artifacts: `docs/features/114-pd-data-model-hardening/` (canonical evidence base)
- Brainstorm source: `docs/brainstorms/115-pd-followups-source.md`
- 114 retro carry-forward notes: `docs/features/114-pd-data-model-hardening/retro.md` (Carry-forward for next feature section)

## Review History

(Populated during prd-reviewer and brainstorm-reviewer iterations.)
