# Tasks: pd Data-Model + Memory Followups (Feature 115)

**Source plan:** `docs/features/115-pd-data-model-followups/plan.md`

All tasks are 5-15 minute granularity. Sequential within Tier; Tiers run in order.

**Complexity codes**: S=Simple (<5 min), M=Medium (5-10 min), C=Complex (10-15 min, may need careful inspection).

## Phase: Tier 0 — Prereq Verification

### T0.1: Verify FR-D inheritance intact

- [ ] Run `rg '_workspace_uuid or _UNKNOWN_WORKSPACE_UUID' plugins/pd/mcp/workflow_state_server.py | wc -l` — assert ≥1 hit.
- [ ] Run `rg -B5 '_workspace_uuid or _UNKNOWN_WORKSPACE_UUID' plugins/pd/mcp/workflow_state_server.py | grep -q _process_complete_phase` — assert exit 0.
- [ ] On failure: ABORT — surface "FR-D regression on develop" and stop. Do NOT proceed to Tier 1.

**Why:** FR-C-115 emit relies on FR-D's workspace fallback being in place. AC-PRE.1.

### T0.2: Verify FR-D.2 accepted reverts intact

- [ ] Run `rg '_workspace_uuid or ""' plugins/pd/mcp/entity_server.py | wc -l` — assert exactly 2.
- [ ] On 0 hits: surface "Someone re-applied FR-D.2 and broke `test_register_entity_handler_concise_message`" and pause.

**Why:** Catches accidental re-application of the 114-reverted FR-D.2 change. AC-PRE.2.

## Phase: Tier 1 — Cluster C (audit invariant + atomicity)

### T1.1: Author `scripts/dev/check_fr_c_115_atomicity.sh`

- [ ] Create `scripts/dev/check_fr_c_115_atomicity.sh` per design C17.1.
- [ ] `chmod +x scripts/dev/check_fr_c_115_atomicity.sh`.

**Why:** Pre-commit guard for FR-C-115.1 single-commit invariant.

### T1.2: Author `scripts/dev/check_fr_c_115_msg.sh`

- [ ] Create `scripts/dev/check_fr_c_115_msg.sh` per design C17.2 (commit-msg marker enforcer).
- [ ] `chmod +x scripts/dev/check_fr_c_115_msg.sh`.

**Why:** Enforces `^FR-C-115.1:` commit message marker for AC-C-115.1 verification.

### T1.3: Author `scripts/dev/check_fr_c_115_atomicity_postmerge.sh`

- [ ] Create `scripts/dev/check_fr_c_115_atomicity_postmerge.sh` per design C17.3.
- [ ] `chmod +x scripts/dev/check_fr_c_115_atomicity_postmerge.sh`.
- [ ] Locally test against a synthetic two-commit branch where the FR-C-115.1 commit fails the atomicity check (e.g., missing one of the two file changes).

**Why:** Post-merge enforcement gate for AC-C-115.1.

### T1.4: Commit T1.1-T1.3 atomicity guard scripts (separate commit, BEFORE T1.5a)

- [ ] `git add scripts/dev/check_fr_c_115_*.sh && git commit -m "build(115): atomicity guard scripts for FR-C-115.1"`

**Why:** Scripts must exist before the FR-C-115.1 commit so they can be invoked. **Complexity: S.**

### T1.4a: Symlink atomicity guards to `.git/hooks/` BEFORE the FR-C-115.1 commit

- [ ] `ln -sf $(realpath scripts/dev/check_fr_c_115_atomicity.sh) .git/hooks/pre-commit`
- [ ] `ln -sf $(realpath scripts/dev/check_fr_c_115_msg.sh) .git/hooks/commit-msg`
- [ ] Verify: `ls -la .git/hooks/pre-commit .git/hooks/commit-msg` shows symlinks.

**Why:** Design TD-115-3 says scripts are NOT auto-installed; implementer must manually symlink before the FR-C-115.1 commit so the atomicity invariant is enforced at commit time (not just post-merge). **Complexity: S.**

### T1.5a: Author failing test `test_complete_phase_closes_emits_exactly_once` FIRST (TDD)

- [ ] Add test to `plugins/pd/mcp/tests/test_workflow_state_server.py` (or equivalent test file).
- [ ] Test calls `_process_complete_phase` directly via pytest fixture seeded with feature entity in `active` status.
- [ ] Test asserts: `SELECT COUNT(*) FROM phase_events WHERE event_type='entity_status_changed' AND type_id=?` == 1 (catches double-emit regression — the load-bearing TDD predicate).
- [ ] **TDD invariant**: pre-impl, BOTH F111 manual emit AND new emit fire when both code paths exist → COUNT==2 → test FAILS red. Post-impl (T1.6), F111 manual removed (only new emit) → COUNT==1 → test PASSES green. This is the canonical TDD signature.
- [ ] **Important**: do NOT assert presence/absence of `closed_by_uuid` in metadata. Spec AC-C-115.3 explicitly says closed_by_uuid MAY appear post-impl (no contract guarantees absence), so a closed_by_uuid-shape assertion would be unstable.
- [ ] **Alternative (simpler) test setup if both code paths are too entangled to coexist**: write the test post-T1.6 but with a parametrized fixture that toggles the F111 manual emit on/off via monkeypatch. With manual ON → COUNT==2 (asserted failure mode). With manual OFF (post-T1.6 state) → COUNT==1 (asserted pass).

**Why:** TDD ordering. The test pins AC-C-115.2 (single-emit COUNT) + AC-C-115.3 (closed_by_uuid loss); impl in T1.6 must satisfy both. **Complexity: M.**

### T1.5: Locate exact insertion point in `db.update_entity` for emit

- [ ] Read `plugins/pd/hooks/lib/entity_registry/database.py` around `update_entity` definition.
- [ ] Identify the line immediately after the status UPDATE statement and its implicit commit, but BEFORE any return.
- [ ] Document the chosen line range in implementation-log.md.

**Why:** Per TD-115-6 (post-UPDATE emit). Implementation needs exact line. **Complexity: M.**

### T1.6: Implement emit insertion + F111 manual emit deletion (SAME commit, FR-C-115.1)

- [ ] Apply 114 design C10.1 emit insertion code block at the line identified in T1.5.
- [ ] In `plugins/pd/mcp/workflow_state_server.py`, delete the `db.append_phase_event(event_type="entity_status_changed", ...)` block (currently lines ~1364-1375 per spec Pin F.3-115).
- [ ] Stage both files: `git add plugins/pd/hooks/lib/entity_registry/database.py plugins/pd/mcp/workflow_state_server.py`.
- [ ] The pre-commit hook (symlinked in T1.4a) fires automatically at `git commit` — verifies atomicity. Manual sanity: `bash scripts/dev/check_fr_c_115_atomicity.sh` — assert exit 0.
- [ ] `git commit -m "FR-C-115.1: emit entity_status_changed in update_entity; remove F111 manual emit"`. The commit-msg hook (symlinked in T1.4a) fires automatically.
- [ ] Run T1.5a's test — should now PASS (COUNT==1, exactly the new emit).

**Why:** FR-C-115.1 atomic landing. AC-C-115.1, AC-C-115.2. **Complexity: C.**

### T1.6a: Remove atomicity guard symlinks AFTER FR-C-115.1 commit

- [ ] `rm .git/hooks/pre-commit .git/hooks/commit-msg`
- [ ] Verify: `ls .git/hooks/pre-commit 2>/dev/null` returns empty.

**Why:** Per design TD-115-3, atomicity hooks are one-shot — only needed for the FR-C-115.1 commit. Removing prevents ongoing overhead on unrelated commits. **Complexity: S.**

### T1.7: Run full pytest after T1.6

- [ ] Before T0 begins: capture baseline test count via `plugins/pd/.venv/bin/python -m pytest plugins/pd/ --co -q | tail -1` and record in implementation-log.md.
- [ ] At T1.7: `plugins/pd/.venv/bin/python -m pytest plugins/pd/ -x`.
- [ ] Assert: 0 FAIL, 0 ERROR. New test count ≥ baseline + 1 (T1.5a). Test count delta from baseline should be ≥ +1 and ≤ +50 (sanity check; if outside, document in implementation-log.md).
- [ ] If any test fails: investigate, fix, re-commit on a SEPARATE commit (NOT amending T1.6 — preserves atomicity audit trail).

**Why:** Detects double-emit regressions (FM-1) and per-callsite emit correctness (AC-C-115.2). **Complexity: M.**

### T1.8: Write per-callsite emit tests for AC-C.1 — **GRANULARITY EXCEPTION**

> **Granularity note**: 17 sub-tests, expected 60-90 minutes — NOT standard 5-15 min granularity. Justified by shared fixture infrastructure.

**17 production callers** (inlined from spec Pin F.1; original from 114 spec, line numbers re-verified at 115 spec time — exact lines may drift, use function-name + grep):

| # | File | Line (115 spec time) | Status target | Notes |
|---|---|---|---|---|
| 1 | `plugins/pd/scripts/cleanup_backlog.py` | 224 | `'archived'` | type_id parameter |
| 2 | `plugins/pd/mcp/entity_server.py` | 369-373 | param `status` | `_process_update_entity` canonical mutation site |
| 3 | `plugins/pd/mcp/workflow_state_server.py` | 1359-1361 | param `terminal` | F111 closure multi-line; manual emit at 1364-1375 REMOVED by T1.6 |
| 4 | `plugins/pd/hooks/lib/doctor/fix_actions/_implementations.py` | (post-T2a.5 rename) | `'promoted'` | (was fix_actions.py:177) |
| 5 | `plugins/pd/hooks/lib/doctor/fix_actions/_implementations.py` | (post-T2a.5 rename) | `'dropped'` | (was fix_actions.py:185) |
| 6 | `plugins/pd/hooks/lib/workflow_engine/entity_engine.py` | 371 | `'abandoned'` | parent abandoned |
| 7 | `plugins/pd/hooks/lib/workflow_engine/entity_engine.py` | 398 | `'abandoned'` | child abandoned |
| 8 | `plugins/pd/hooks/lib/workflow_engine/entity_engine.py` | 477 | `'completed'` | |
| 9 | `plugins/pd/hooks/lib/workflow_engine/engine.py` | 180 | `'completed'` | feature completed |
| 10 | `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py` | 93 | `'promoted'` | |
| 11 | `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py` | 200 | param `status` | generic |
| 12 | `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py` | 338 | `'active'` | |
| 13 | `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py` | 53-55 | `'archived'` | stub orchestrator method |
| 14 | `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py` | 83-85 | param `meta_status` | stub orchestrator method |
| 15 | `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py` | 209-211 | `'archived'` | stub orchestrator method |
| 16 | `plugins/pd/hooks/lib/entity_registry/dependencies.py` | 109 | `'planned'` | |
| 17 | `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py` | 183 | param `target_phase` | |

- [ ] For each caller, write a test that stubs the entity into the documented pre-mutation status and invokes the calling code path.
- [ ] Assert exactly one new `phase_events` row with `event_type='entity_status_changed'`, `metadata.type_id` matching, and consistent `old_status` / `new_status`.
- [ ] For reconciliation callers (#13-15), stub at the orchestrator-method level (full cycle not required).
- [ ] Test name pattern: `test_audit_emit_{file_stem}_{line}` (e.g., `test_audit_emit_entity_engine_371`).
- [ ] If line numbers have drifted, use the function-name grep from the file column to locate the actual line.

**Why:** AC-C.1 (114 inherited) — per-callsite verification of audit invariant. **Complexity: 3×C (split into T1.8a callers 1-6, T1.8b callers 7-12, T1.8c callers 13-17 if time pressure hits).**

### T1.9: Implement Migration 15 (`_migration_15_audit_emit_counter`)

- [ ] Add migration body per 114 design C10.3 to `plugins/pd/hooks/lib/entity_registry/database.py`.
- [ ] Add `INSERT OR REPLACE INTO _metadata(key, value) VALUES ('audit_emit_failed_count', '0')`.
- [ ] Register in `MIGRATIONS` and `MIGRATIONS_DOWN` dicts at the appropriate slot.
- [ ] Write migration-runner unit test asserting M15 produces `audit_emit_failed_count=0`.

**Why:** AC-C.7a (114 inherited).

### T1.10: Write M15 preservation test (AC-C.7b)

- [ ] Create synthetic test migration `_migration_test_99` that touches `_metadata` for an unrelated key.
- [ ] Test: pre-condition `audit_emit_failed_count=3`; run M15; run test_99; assert `audit_emit_failed_count` still 3.

**Why:** AC-C.7b — M15 reset must be one-shot.

### T1.11: Implement `check_audit_counter_write_path.py` AST check

- [ ] Create `plugins/pd/hooks/lib/doctor/check_audit_counter_write_path.py` per 114 design C10.4 pattern (mirror of `check_status_write_path.py`).
- [ ] Test: synthetic violating migration body asserted to fail the AST check.

**Why:** AC-C.7c — guards future migrations from clobbering audit counter.

### T1.12: Implement audit-counter doctor health-check

- [ ] Extend doctor `__main__.py` (or existing check) to read `audit_emit_failed_count` and emit `severity=warning` if > 0.
- [ ] Test: seed value=5; doctor output JSON contains warning issue with `count` field == 5.

**Why:** AC-C.5.

### T1.13: Register `scripts/dev/check_fr_c_115_atomicity_postmerge.sh` in validate.sh

- [ ] Append the stanza from design C17.3 "Activation surface" to the end of `validate.sh`.
- [ ] Test by running `./validate.sh` — assert exit 0.

**Why:** AC-C-115.1 post-merge enforcement; closes rebase/amend loophole. **Complexity: M.**

### T1.13b: Self-test validate.sh stanza catches FR-C-115.1 violations

- [ ] Temporarily rename `FR-C-115.1` to `FR-X-999.1` in the T1.6 commit's MESSAGE only via `git commit --amend` (do NOT modify code).
- [ ] Run `./validate.sh` — assert non-zero exit with error mentioning FR-C-115 atomicity.
- [ ] Restore original commit message via `git commit --amend`.
- [ ] Re-run `./validate.sh` — assert exit 0.

**Why:** Self-test validates that the stanza actually fires when triggered; without this, validate.sh could be silently broken. Design C17.3 line 539 specifies this self-test step. **Complexity: M.**

### T1.Final: End-of-Tier-1 regression check

- [ ] `plugins/pd/.venv/bin/python -m pytest plugins/pd/` from repo root.
- [ ] Assert all tests pass (≥ baseline + Tier 1 additions).
- [ ] If any test fails: stop and resolve before proceeding to Tier 2a.

**Why:** Catches per-Tier regressions early instead of accumulating until TFinal.1. **Complexity: S.**

## Phase: Tier 2a — Cluster E.2 (triage tool + M16 stub + M17 allowlist + sub-package)

### T2a.1: Author `scripts/dev/check_migration_contiguity.sh`

- [ ] Create per design §6 (M16/M17 ordering note).
- [ ] `chmod +x`.

**Why:** Guards Tier 2a M16→M17 ordering.

### T2a.2: Implement M16 no-op stub

- [ ] Add `_migration_16_reserved` and `_migration_16_reserved_down` per design C16.
- [ ] Register in `MIGRATIONS` and `MIGRATIONS_DOWN` dicts.
- [ ] Commit separately BEFORE M17.
- [ ] Run `bash scripts/dev/check_migration_contiguity.sh` — assert exit 0.

**Why:** AC-Migrations-115.2; runner contiguity.

### T2a.3: Implement M17 (`cross_workspace_allowlist` table)

- [ ] Add `_migration_17_cross_workspace_allowlist` per 114 spec FR-E.2.1 / 114 design C13.
- [ ] Schema (inlined from 114 spec FR-E.2.1):
  ```sql
  CREATE TABLE cross_workspace_allowlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_uuid TEXT NOT NULL,
    child_uuid TEXT NOT NULL,
    reason TEXT NOT NULL,
    grandfathered_by TEXT NOT NULL DEFAULT 'operator',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(parent_uuid, child_uuid),
    FOREIGN KEY (parent_uuid) REFERENCES entities(uuid) ON DELETE CASCADE,
    FOREIGN KEY (child_uuid) REFERENCES entities(uuid) ON DELETE CASCADE
  );
  ```
- [ ] Register in MIGRATIONS dicts.
- [ ] Add `_migration_17_cross_workspace_allowlist_down` with DROP TABLE + schema_version=16 stamp in `BEGIN IMMEDIATE`.
- [ ] Test: `PRAGMA table_info(cross_workspace_allowlist)` returns 6 rows; column names are exactly `{id, parent_uuid, child_uuid, reason, grandfathered_by, created_at}` (verify by set equality).

**Why:** AC-E.2.1. **Complexity: M.**

### T2a.4: rg discovery of `fix_actions` callers

- [ ] Run `rg 'from.*fix_actions import' plugins/pd/` — capture all imported names.
- [ ] Run `rg 'fix_actions\.' plugins/pd/` — capture all attribute accesses.
- [ ] Document the union of names (public + `_`-prefixed) in a one-line list for use in T2a.5.

**Why:** TD-115-5 step 1 prerequisite for explicit re-export.

### T2a.5: Promote `fix_actions.py` to `fix_actions/` sub-package

- [ ] `mkdir plugins/pd/hooks/lib/doctor/fix_actions/`
- [ ] `git mv plugins/pd/hooks/lib/doctor/fix_actions.py plugins/pd/hooks/lib/doctor/fix_actions/_implementations.py`
- [ ] Create `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py` with explicit re-export list from T2a.4.
- [ ] Run full pytest — assert no ImportError.

**Why:** TD-115-5 step 2/3; spec FR-E.2-115.1.

### T2a.6: Implement `_interactive_triage_loop` helper

- [ ] Create `plugins/pd/hooks/lib/doctor/fix_actions/_interactive.py` per IF-115-4.
- [ ] Add to `__init__.py` re-export.
- [ ] Unit test with mocked AskUserQuestion harness.

**Why:** Shared helper for triage tool.

### T2a.7: Implement `_fix_triage_cross_workspace_link` per 114 design IF-8

- [ ] Add function to `fix_actions/_implementations.py` (or new module within the sub-package).
- [ ] Use `_interactive_triage_loop` for per-link iteration.
- [ ] Tests with mocked AskUserQuestion covering 4 decision paths (re-attribute parent/child, delete relation, grandfather).

**Why:** AC-E.2.2, AC-E.2.3.

### T2a.8: Post-triage SQL verification test

- [ ] Test: seed 21 cross-workspace `parent_uuid` rows; run triage tool selecting "grandfather" for all.
- [ ] Assert AC-E.5 SQL returns 0 (no unallowlisted rows remain).

**Why:** AC-E.5 binary AC.

### T2a.Final: End-of-Tier-2a regression check

- [ ] `plugins/pd/.venv/bin/python -m pytest plugins/pd/` — assert all pass.

**Why:** Catches sub-package promotion regressions (TD-115-5 risk R-115-3) before Tier 2b builds on the new module structure. **Complexity: S.**

## Phase: Tier 2b — Cluster E (gates + envelope + doctor check)

### T2b.1: Implement `CrossWorkspaceError` exception class

- [ ] Add to `plugins/pd/hooks/lib/entity_registry/database.py` per 114 design IF-3 (inherits ValueError).
- [ ] Test: instantiation with op_name + pairs serializes to expected string.

**Why:** 114 IF-3 + spec OQ-9 resolution.

### T2b.2: Implement `_assert_same_workspace_pairwise` helper

- [ ] Add per 114 design IF-3 verbatim.
- [ ] Test: matching workspace returns None; mismatching raises CrossWorkspaceError; allowlisted pair returns None.

**Why:** 114 FR-E.1.

### T2b.3: Add envelope translator branch for `CrossWorkspaceError`

- [ ] In `plugins/pd/mcp/entity_server.py` and `plugins/pd/hooks/lib/entity_registry/server_helpers.py`, add `isinstance(exc, CrossWorkspaceError)` branch returning `error_type=cross_workspace_forbidden` envelope per 114 design IF-3.
- [ ] Test: handler receives mismatched UUIDs; envelope contains `error_type=cross_workspace_forbidden`.

**Why:** FR-E.3.

### T2b.4: Add gate calls to 3 MCP handlers (content-based locators)

- [ ] **Handler 1**: locate via `rg "def _process_set_parent" plugins/pd/hooks/lib/entity_registry/server_helpers.py` (≈line 483 at 115 spec time). Insert `_assert_same_workspace_pairwise(db, (child_uuid, parent_uuid), 'set_parent')` immediately after UUID validation, before the `db.update_entity` or `db.set_parent` mutation.
- [ ] **Handler 2**: locate via `rg "def _process_add_dependency" plugins/pd/mcp/entity_server.py` (≈line 1149). Invoke for `(entity_uuid, blocked_by_uuid)`.
- [ ] **Handler 3**: locate via `rg "def _process_add_okr_alignment" plugins/pd/mcp/entity_server.py` (≈line 1281). Invoke for `(entity_uuid, key_result_uuid)`.
- [ ] Content-based locators (rg the function definition) are authoritative; line numbers are advisory only and may drift.

**Why:** 114 FR-E.2; AC-E.1. **Complexity: M.**

### T2b.5: Tests for AC-E.1, AC-E.2, AC-E.3

- [ ] Cross-workspace call → envelope error_type=cross_workspace_forbidden (AC-E.1).
- [ ] Same-workspace call → succeeds (AC-E.2).
- [ ] Allowlisted pair → succeeds (AC-E.3).
- [ ] 3 handlers × 3 ACs = 9 test cases minimum.

**Why:** AC-E.1, AC-E.2, AC-E.3.

### T2b.6: Implement `check_cross_workspace_parent_uuid` doctor check

- [ ] Create `plugins/pd/hooks/lib/doctor/check_cross_workspace_parent_uuid.py` per design C13-115.3 verbatim (note: uses `Issue(check=...)` not `check_name=`).
- [ ] Register in doctor `__main__.py` check list.

**Why:** FR-E-115.1.

### T2b.7: Test C13-115.3 emits warning-only

- [ ] Fixture DB with 21 cross-workspace `parent_uuid` rows.
- [ ] Invoke `check()` directly.
- [ ] Assert all 21 emitted Issues have `severity='warning'` exactly.
- [ ] Assert NO Issue has `severity in {'error', 'info', 'suggestion'}`.

**Why:** AC-E-115.1, AC-E-115.2, AC-E-115.3.

### T2b.8: Implement `check_severity_vocab.py` AST check

- [ ] Create `plugins/pd/hooks/lib/doctor/check_severity_vocab.py` per design C15-115.1.
- [ ] AST-scan all `check_*.py` files in `plugins/pd/hooks/lib/doctor/`.
- [ ] Assert every `severity=` literal is in `{"error", "warning", "info"}`.

**Why:** TD-115-4 + AC-Sev.3.

### T2b.9: Test severity vocab AST check catches drift

- [ ] Add a synthetic check file with `severity='suggestion'` to a temp dir.
- [ ] AST check picks it up; reports the violation.
- [ ] Remove temp file.

**Why:** Verification that the guard works.

### T2b.10: Verify `severity_summary` output schema

- [ ] Test: doctor invocation against fixture DB returns JSON with top-level `severity_summary: {error: N, warning: N, info: N}` field.
- [ ] All N ≥ 0.

**Why:** AC-Sev.1, AC-Sev.2 (114 inherited).

### T2b.Final: End-of-Tier-2b regression check

- [ ] `plugins/pd/.venv/bin/python -m pytest plugins/pd/` — assert all pass.

**Why:** Catches cross-workspace gate regressions before Tier 3 touches memory.db. **Complexity: S.**

## Phase: Tier 3a — Cluster B-H3 (writer CLI gates) (114 C7 unchanged)

### T3a.1: Extract `_apply_quality_gates` from `_process_store_memory`

- [ ] Read `plugins/pd/mcp/memory_server.py:92-147` (per 114 design C7).
- [ ] Extract logic to module-level function per 114 IF-2 signature.
- [ ] Verify the original `_process_store_memory` now calls `_apply_quality_gates` exactly once.

**Why:** 114 FR-B-H3.1, AC-B-H3.2.

### T3a.2: Update `writer.py:main` to call `_apply_quality_gates`

- [ ] Import the helper.
- [ ] Call before any `db.upsert_entry`.
- [ ] On `passed=False`: exit code 0 for `deduped`, non-zero for `too_short`/`near_dup`; stderr message describes which gate fired.

**Why:** 114 FR-B-H3.2.

### T3a.3: AST/grep verification

- [ ] AST scan `writer.py:main` — exactly one call to `_apply_quality_gates`.
- [ ] AST scan `memory_server.py` — gate logic literals (20-char min, 0.95, 0.90) appear EXACTLY ONCE in the file, inside `_apply_quality_gates`.

**Why:** AC-B-H3.1, AC-B-H3.2.

### T3a.4: Integration tests for writer CLI gates

- [ ] Empty description → exit code != 0 (AC-B-H3.3).
- [ ] Near-dup at ≥0.95 → exit code != 0 with stderr matching 'near-dup rejection' (AC-B-H3.4).
- [ ] Dedup at ≥0.90 → exit code 0 with observation_count bumped on existing entry.

**Why:** AC-B-H3.3, AC-B-H3.4.

### T3a.Final: End-of-Tier-3a regression check

- [ ] `plugins/pd/.venv/bin/python -m pytest plugins/pd/` — assert all pass.

**Why:** Catches CLI gate extraction regressions before Tier 3b memory.db migrations. **Complexity: S.**

## Phase: Tier 3b — Cluster B-H4 (recompute helper + M6 + M7)

### T3b.1: Implement `recompute_source_hash.py` module

- [ ] Create `plugins/pd/hooks/lib/semantic_memory/recompute_source_hash.py` with `recompute_all`, `recompute_all_with_conn`, and `report` functions per IF-115-2 + 114 IF-5.
- [ ] CLI entry: `python -m plugins.pd.hooks.lib.semantic_memory.recompute_source_hash --report` and `--apply`.

**Why:** Per design C8-115.1.

### T3b.2: Run dry-run --report against live memory.db; verify pins

- [ ] `python -m plugins.pd.hooks.lib.semantic_memory.recompute_source_hash --report` against `~/.claude/pd/memory/memory.db`.
- [ ] Assert: `n_tool_failure ∈ [418, 518]` (Pin H-115), `n_inflated ∈ [9, 15]` (Pin I-115), `n_shifted >= 1`.
- [ ] **Explicit ISO 8601 check**: `python3 -c "from datetime import datetime; datetime.fromisoformat(report['observed_at'])"` — must not raise. Alternately regex `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}` matches.
- [ ] If `n_shifted == 0`: surface and pause (per AC-B-H4-115.5(c) — dry-run zero shifts is suspicious).
- [ ] Document the observed n_shifted value for use in T3b.7 sanity check.

**Why:** AC-B-H4-115.5 (all four conditions a/b/c/d) + spec-time pin refresh. **Complexity: M.**

### T3b.3a: Author failing tests for M6 Op 1 (DELETE) BEFORE implementation

- [ ] Test 1: Fixture seeded with 600 Tool-failure rows (out of range) → assert MigrationAbort + stderr matches `pd.migrate.m6_count_drift: {...}` with required payload keys per IF-115-1 (observed, expected, tolerance, stage=1, recount_command, identity_sample, pin_to_amend, migration_id, suggested_new_tolerance).
- [ ] Test 2: Fixture with 468 Tool-failure rows but only 50% `created_at < '2026-05-16'` → assert `pd.migrate.m6_identity_drift` abort (stage=2 payload).
- [ ] Test 3: Fixture with 468 rows, 95%+ pre-freeze → expect DELETE succeeds and `SELECT COUNT(*) FROM entries WHERE source='session-capture' AND name LIKE 'Tool failure:%'` == 0 post-migration. Test currently FAILS (M6 not implemented).

**Why:** TDD ordering. AC-B-H4-115.1, AC-B-H4-115.3. **Complexity: C.**

### T3b.3b: Author failing tests for M6 Op 2 (hash unify) BEFORE implementation

- [ ] Test 1: Fixture where stored `source_hash` differs from recomputed (`source_hash(description)`) on N>=1 rows → after M6, all rows have unified hashes (verified by re-running source_hash over each row's description and comparing).
- [ ] Test 2: Fixture where dry-run produced n_shifted=0 (hashes already unified) → M6 Op 2 runs as no-op; no abort.

**Why:** TDD ordering. AC-B-H4.2 (114 inherited), AC-B-H4-115.5 condition (c) divergence (dry-run vs migration). **Complexity: M.**

### T3b.3c: Implement M6 body

- [ ] Add `_migration_6_unify_source_hash_and_cleanup` to `plugins/pd/hooks/lib/semantic_memory/database.py` per design C8-115.2 (copy the Python code block verbatim — properly indented inside `try` block, with `PRAGMA busy_timeout = 5000` + `BEGIN IMMEDIATE`).
- [ ] Add `_migration_6_unify_source_hash_and_cleanup_down` (in-tx schema_version=5 stamp).
- [ ] Register in `MIGRATIONS` and `MIGRATIONS_DOWN` dicts at slots 6.
- [ ] Run T3b.3a + T3b.3b tests — assert all PASS.

**Why:** FR-B-H4-115.2; satisfies tests authored in T3b.3a/b. **Complexity: C.**

### T3b.4: Author failing tests for M7 BEFORE implementation (TDD)

- [ ] Test 1: Fixture seeded with 30 inflated rows (`source='import' AND observation_count > 100`, out of [9,15] range) → assert MigrationAbort + stderr matches `pd.migrate.m7_count_drift: {...}` with stage=1 payload keys per IF-115-1 (observed, expected=12, tolerance=3, stage=1, recount_command, identity_sample=[], pin_to_amend, migration_id="m7_observation_reset", suggested_new_tolerance).
- [ ] Test 2: Fixture with 12 inflated rows but only 50% `created_at < '2026-05-16'` → assert `pd.migrate.m7_identity_drift` abort (stage=2 payload with populated identity_sample list).
- [ ] Test 3: Fixture with 12 inflated rows, 100% pre-freeze → expect UPDATE succeeds and `SELECT COUNT(*) FROM entries WHERE source='import' AND observation_count > 100` == 0 post-migration. Test currently FAILS (M7 not implemented).

**Why:** TDD ordering (mirrors T3b.3a/b → T3b.3c pattern). AC-B-H4-115.2, AC-B-H4-115.4. **Complexity: C.**

### T3b.5: Implement M7 body

- [ ] Add `_migration_7_reset_inflated_observation_count` per design C8-115.3 (copy verbatim, properly indented).
- [ ] Add `_migration_7_reset_inflated_observation_count_down` (in-tx schema_version=6 stamp).
- [ ] Register in MIGRATIONS dicts at slot 7.
- [ ] Run T3b.4 tests — assert all 3 PASS.

**Why:** FR-B-H4-115.3; satisfies tests authored in T3b.4. **Complexity: C.**

### T3b.6: Additional M7 verification (post-impl)

- [ ] AST/grep verify `_migration_7_reset_inflated_observation_count_down` body contains `BEGIN IMMEDIATE` + `INSERT OR REPLACE INTO _metadata ... 'schema_version', '6'` per framework down-migration requirements.

**Why:** Catches missing in-tx schema_version stamp (the same defect class as M16 iter 1 blocker). **Complexity: S.**

### T3b.7: End-to-end migration cycle test

- [ ] Run M6 + M7 against a clean fixture DB seeded with both Pin H-115 + Pin I-115 candidates.
- [ ] Post-migration: `n_tool_failure==0` AND `n_inflated==0` AND `schema_version==7`.
- [ ] Run down-migration sequence: M7-down then M6-down → schema_version==5; deleted rows are NOT restored (destructive operation, documented limitation).

**Why:** Migration framework integration.

## Phase: Final Verification

### TFinal.1: Run full pytest

- [ ] `plugins/pd/.venv/bin/python -m pytest plugins/pd/` from repo root.
- [ ] Assert all tests pass (114 baseline 1861 + new tests from 115).

**Why:** Regression check.

### TFinal.2: Run validate.sh

- [ ] `./validate.sh` — assert exit 0.
- [ ] Verifies (a) FR-C-115.1 atomicity post-merge gate, (b) any other discovered checks pass.

**Why:** Pre-merge validation per `/pd:finish-feature` Step 5a.

### TFinal.3: Doctor smoke test

- [ ] `python -m plugins.pd.hooks.lib.doctor` against `~/.claude/pd/entities/entities.db` + `~/.claude/pd/memory/memory.db`.
- [ ] Assert output JSON contains `severity_summary` with non-negative integer values; `severity_summary.error == 0` (no new error-level issues introduced).

**Why:** AC-Sev.* binary check.
