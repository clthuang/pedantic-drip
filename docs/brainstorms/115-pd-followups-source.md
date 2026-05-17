# Feature 115 Brainstorm Source: pd Data-Model + Memory Followups

**Source:** Deferred clusters from feature 114 (`docs/features/114-pd-data-model-hardening/`). 114 landed Clusters A, D, B-H2 (the production blockers); 115 picks up the remaining 5 sub-clusters that were deferred for risk/triage reasons. All evidence, repro, and design contracts are already in 114's spec.md and design.md — 115 should reuse them as the canonical reference rather than re-deriving.

## Problem Statement

Feature 114 fixed the 3 production blockers (M12 stub trap, workspace fallback, capture hook noise) but deferred 5 sub-clusters because of risk/scope concerns:

1. **Cluster C** (audit invariant): `update_entity` doesn't emit `entity_status_changed`; production phase_events table has **0 such events out of 945**. The F111 audit invariant has never held. Deferred because: 17 production caller sites + F111 manual emit removal + AST whitelist removal = high test-fixture-breakage risk requiring careful sweep.
2. **Cluster E** (cross-workspace gates): 3 MCP write paths (`set_parent`, `add_dependency`, `add_okr_alignment`) lack the cross-workspace assertion that `issue_spawn` got in F111. Production DB has **21 live cross-workspace `parent_uuid` links** that may be intentional. Deferred because: hardening gates without triage tool first would blockade valid workflows.
3. **Cluster E.2** (cross-workspace triage tool): Doctor fix_action with per-link AskUserQuestion offering re-attribute/delete/grandfather options. Prerequisite for E hardening.
4. **Cluster B-H3** (writer CLI quality gates): 91% of memory DB entries (1441/1581) enter via CLI back door, bypassing the 20-char min / 0.95 near-dup / 0.90 dedup-merge gates. Deferred because: independent of A/D/B-H2 cluster, not a production blocker.
5. **Cluster B-H4** (hash-drift backfill): 10 memory entries inflated to `observation_count=1438` from cross-writer hash drift; `writer.py:72` hashes `description`, `importer.py:86` hashes `raw_chunk`. Plus the ~464 noise-row cleanup. Deferred because: requires implement-phase manifest freeze against live memory.db.

## Scope (5 clusters, ordered for safest landing)

**Tier 1 — Audit invariant (Cluster C)**: Add emit to `update_entity` (`database.py:7156-7236`) when `status is not None AND status != current`. Fail-open with stderr `pd.audit.emit_failed` tag + counter increment. Remove F111 manual emit at `workflow_state_server.py:1344-1356` in the SAME commit. Migration 15 (`_migration_15_audit_emit_counter` init counter to 0). New AST audit check `check_audit_counter_write_path.py`. ~~Test fixture sweep + remove `'update_entity'` from `_PERMITTED_ENCLOSING_DEFS` at `check_status_write_path.py:37`.~~ ← **DEFERRED TO FEATURE 116** per PRD Non-Goals (FM-4 risk-reduction; FR-C.5 fixture sweep also pushed to 116).

**Tier 2 — Cross-workspace gates (Cluster E + E.2)**: Extract `_assert_same_workspace_pairwise(db, pair, op_name)` helper. Apply at 3 MCP handlers. New `CrossWorkspaceError(ValueError)` + envelope translator update. Warning-only doctor check (NOT hard-error). New Migration 17 creating `cross_workspace_allowlist` table. New doctor fix_action `_fix_triage_cross_workspace_link` with 4-option AskUserQuestion harness.

**Tier 3 — Memory hygiene (Cluster B-H3 + B-H4)**: Extract `_apply_quality_gates(description, db, config) -> QualityGateResult` helper. Both `_process_store_memory` AND `writer.py:main` call it. Unify `source_hash` input (canonical: `description`). Migration 6 (memory.db) hash unify + cleanup query `DELETE FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%'`. Migration 7 (memory.db) `UPDATE entries SET observation_count=1 WHERE source='import' AND observation_count > 100`.

## Empirical Pins (carried from 114 spec rev 4)

| Pin | Source-of-truth |
|-----|-----------------|
| 17 production `update_entity(status=...)` callers enumerated | 114/spec.md Pin F.1 |
| 0 `entity_status_changed` rows / 945 phase_events | direct DB query at 114-time |
| 21 cross-workspace `parent_uuid` rows | direct DB query at 114-time |
| 464 `Tool failure:` rows in memory.db (29% of 1581) | direct DB query at 114-time |
| 10 entries at observation_count=1438 | direct DB query at 114-time |
| entities.db migrations: M14 is current head (post-114 merge); M15/M17 new | git log + grep |
| memory.db migrations: M5 is current head; M6/M7 new | direct DB query |

## Goals / Success Criteria

1. **Audit invariant (observability-grade)**: 100% of `update_entity(status=...)` mutations either emit `entity_status_changed` event OR emit `pd.audit.emit_failed` stderr line + counter increment. Strict transactional coupling is NOT a goal. Verified via per-callsite integration tests for the 17 production callers.
2. **Cross-workspace isolation**: `set_parent`, `add_dependency`, `add_okr_alignment` reject cross-workspace inputs with typed `error_type=cross_workspace_forbidden` envelope. Doctor check reports `severity=warning` (NOT error) for existing 21 links. Triage tool offers 4 options per link.
3. **Post-triage**: `SELECT COUNT(*) FROM entities e JOIN entities p ON e.parent_uuid=p.uuid LEFT JOIN cross_workspace_allowlist a ON a.parent_uuid=p.uuid AND a.child_uuid=e.uuid WHERE e.workspace_uuid != p.workspace_uuid AND a.id IS NULL == 0`.
4. **Memory hygiene**: `writer.py:main` calls `_apply_quality_gates` exactly once before `db.upsert_entry`. AST/grep check confirms gate logic appears once in `memory_server.py` (no inline duplicates). All 10 inflated entries reset to `observation_count=1`. All 464 noise rows deleted.

## Non-Goals

- **Hard-error escalation** for Cluster E doctor check (gates remain warning-only at end of 115; future feature can escalate after operator confidence builds).
- **Full event-sourcing audit retrofit** (observability-grade fail-open emit only).
- **Migration 17 ON DELETE CASCADE semantics changes** for allowlist (accept current design).
- **Re-attribution of `_UNKNOWN_WORKSPACE_UUID` entities** (separate concern — 114 carry-forward).
- **Fingerprint-based M12 detector** (114 shipped column-presence approach; sufficient for now).

## Risks Carried Forward

From 114 retro and design:

1. **CRITICAL — Cluster C 17-caller blast radius**: `update_entity(status=...)` callers span workflow_engine, reconciliation_orchestrator, doctor/fix_actions, scripts/cleanup_backlog, mcp/entity_server, mcp/workflow_state_server, entity_registry/dependencies, entity_registry/entity_lifecycle. If emit can't resolve `project_id` for some callers (especially `__unknown__` workspace context), MCP startup could crash. **Mitigation**: emit fail-open with try/except; status UPDATE happens before emit so it has already committed.
2. **CRITICAL — F111 manual-emit removal MUST be same-commit as Cluster C emit insertion** (else double-emit; AC-C.1 "exactly one row" fails). Plus: `closed_by_uuid` metadata key permanently lost in closures (operators correlate via `entity_relations.fixes` instead). Accepted observability tradeoff per 114 retro.
3. **HIGH — AST whitelist removal at `check_status_write_path.py:37` must follow test fixture sweep**. Production callers covered by Cluster C emit, but test files calling `db.update_entity(status=...)` directly need either refactor to `upsert_entity`/`promote_entity` or allowlist entry in new `_PERMITTED_TEST_FILES` frozenset.
4. **HIGH — Cluster E doctor check must be warning-only, NEVER error** until 21 links triaged. Cluster E.2 triage tool ships in same feature so user has a recovery path.
5. **MEDIUM — Hash unify backfill (B-H4)** must produce frozen manifest at implement-phase before migration body lands. Migration aborts if observed `shifted_ids` differs from manifest. Prevents silent re-import of all 1581 entries.

## Reference Files

Feature 114 artifacts are the canonical evidence base — 115 spec/design should reference rather than re-derive:

- 114 spec: `docs/features/114-pd-data-model-hardening/spec.md` (rev 4) — contains all FR-C, FR-E, FR-E.2, FR-B-H3, FR-B-H4 + AC blocks + Pin F.1 enumerated callers
- 114 design: `docs/features/114-pd-data-model-hardening/design.md` (rev 2) — contains all IF-2, IF-3, IF-5 contracts + C7, C10, C13, C14 component specs
- 114 retro: `docs/features/114-pd-data-model-hardening/retro.md` — implementation strategy + carry-forward notes

## Implementation Strategy (carried from 114 retro)

Recommended approach per 114 retro `Carry-forward for next feature`:

1. **Cluster C first** (Tier 1). Pattern:
   - Add emit to `update_entity` first.
   - Run full pytest — expect F111 closure tests to fail with "exactly one row" → "got 2".
   - Remove F111 manual emit at `workflow_state_server.py:1344-1356` in same commit.
   - Re-run full pytest — expect green.
   - Add Migration 15.
   - Defer AST whitelist removal to separate commit after caller sweep.

2. **Cluster E** (Tier 2). Pattern:
   - Build helper + typed error first.
   - Apply at 3 MCP handlers + envelope translator.
   - Doctor check WARNING-ONLY.

3. **Cluster E.2** (Tier 2). Pattern:
   - Migration 17 first (creates table).
   - Doctor fix_action with AskUserQuestion harness extension.

4. **Cluster B-H3** (Tier 3). Pattern:
   - Extract helper from `_process_store_memory`.
   - Refactor MCP path + add CLI call.

5. **Cluster B-H4** (Tier 3). Pattern:
   - Write recompute helper.
   - Dry-run against live memory.db.
   - Freeze manifest fixture.
   - Write Migration 6 body consuming fixture.
   - Migration 7 (cleanup) separate.

## YOLO Mode Constraints

User explicit instructions for this feature:
- Run full ritual (brainstorm → specify → design → create-plan → implement → finish).
- 5 hours+ session-time tolerance accepted.
- Merge to develop (NEVER main).
- Compress reviewer iterations where reasonable (accept warnings at convergence per 114 pattern).
