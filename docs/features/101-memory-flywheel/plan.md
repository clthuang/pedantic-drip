# Feature 101 — Memory Flywheel Loop Closure (Plan)

> Spec: `spec.md` · Design: `design.md` · PRD: `prd.md` · Backlog #00053

## Overview

Three-stage implementation closing four flow gaps in pd's memory subsystem.
Each stage is independently testable. TDD ordering: tests first (red),
implementation (green), then refactor.

```
Stage 1: Foundations (FR-2/3/5)         ─── localized backend, no orchestrator changes
   ↓
Stage 2: Influence Wiring + Lifecycle (FR-1/4)  ─── 14 prose blocks + sidecar + audit + upgrade
   ↓
Stage 3: Adoption Trigger (FR-6)         ─── retrospecting Step 4c.1 + dogfood validation
```

## Stage 1 — Foundations (FR-2 + FR-3 + FR-5)

**Outcome:** FTS5 self-heal, mid-session recall tracking, project-scoped
influence filtering — all backend changes; no orchestrator-prose edits.
Stage ships independently testable.

### P1.1 — FR-2: FTS5 integrity check + rebuild CLI

| # | Task | TDD step | File | Time | Depends |
|---|------|----------|------|------|---------|
| T1.1.1 | Write `test_rebuild_fts5_basic` (drop+populate+rebuild → count > 0) | RED | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` | 8m | — |
| T1.1.2 | Write `test_rebuild_fts5_diagnostic_file` (asserts JSON schema fields) | RED | same | 6m | T1.1.1 |
| T1.1.3 | Write `test_rebuild_fts5_refire` (second rebuild appends to refires array) | RED | same | 6m | T1.1.2 |
| T1.1.4 | Write `test_rebuild_fts5_user_version_classification` (refire across user_version) | RED | same | 6m | T1.1.3 |
| T1.1.5 | Implement `rebuild_fts5(db_path)` in maintenance.py with `BEGIN IMMEDIATE` + retry + integrity-check + autocommit isolation_level | GREEN | `plugins/pd/hooks/lib/semantic_memory/maintenance.py` | 15m | T1.1.4 |
| T1.1.6 | Implement diagnostic JSON read-modify-write at `~/.claude/pd/memory/.fts5-rebuild-diag.json` | GREEN | same | 10m | T1.1.5 |
| T1.1.7 | Add `--rebuild-fts5` CLI subcommand to `maintenance.py:main()` | GREEN | same | 5m | T1.1.6 |
| T1.1.8 | Add `check_fts5_integrity()` function to `session-start.sh`; invoke from main flow | GREEN | `plugins/pd/hooks/session-start.sh` | 10m | T1.1.7 |
| T1.1.9 | Run all FR-2 tests; verify integrity-check + rebuild + diagnostic file all green | VERIFY | — | 5m | T1.1.8 |

### P1.2 — FR-3: Mid-session recall tracking

| # | Task | TDD step | File | Time | Depends |
|---|------|----------|------|------|---------|
| T1.2.1 | Write `test_search_memory_increments_recall_count` (call MCP → assert recall_count++) | RED | `plugins/pd/mcp/test_memory_server.py` | 8m | — |
| T1.2.2 | Write `test_search_memory_within_call_dedup` (same entry returned 2× in result → bumps once) | RED | same | 6m | T1.2.1 |
| T1.2.3 | Write `test_search_memory_across_calls_increments_per_call` (2 calls → +2) | RED | same | 6m | T1.2.2 |
| T1.2.4 | Write `test_search_memory_recall_failure_logs_warn_returns_entries` (locked-DB scenario) | RED | same | 8m | T1.2.3 |
| T1.2.5 | Modify `_process_search_memory` to call `db.update_recall(set-deduped ids, _iso_utc(now()))` before returning | GREEN | `plugins/pd/mcp/memory_server.py` | 10m | T1.2.4 |
| T1.2.6 | Wrap update_recall in try/except; log warning on failure, do not raise | GREEN | same | 5m | T1.2.5 |
| T1.2.7 | Write `test_search_memory_benchmark.py` with monkeypatched-baseline + actual fixture; assert P50 delta within AC-3.6 bounds; report P95 informationally | GREEN | new file | 15m | T1.2.6 |
| T1.2.8 | Run all FR-3 tests; verify P50 within bound | VERIFY | — | 5m | T1.2.7 |

### P1.3 — FR-5: source_project filter at influence recording

| # | Task | TDD step | File | Time | Depends |
|---|------|----------|------|------|---------|
| T1.3.1 | Write `test_record_influence_filters_cross_project` (project A entry; record from project B → no update) | RED | `plugins/pd/mcp/test_memory_server.py` | 8m | — |
| T1.3.2 | Write `test_record_influence_same_project_passes` (project A entry; record from project A → +1) | RED | same | 6m | T1.3.1 |
| T1.3.3 | Write `test_record_influence_null_project_root_bypass_with_warn` (capsys captures warning) | RED | same | 8m | T1.3.2 |
| T1.3.4 | Modify `_process_record_influence_by_content` to apply source_project filter on candidates list | GREEN | `plugins/pd/mcp/memory_server.py` | 10m | T1.3.3 |
| T1.3.5 | Add null-`_project_root` bypass branch with stderr warning | GREEN | same | 5m | T1.3.4 |
| T1.3.6 | Run all FR-5 tests; verify cross-project rejection AND same-project acceptance AND null bypass | VERIFY | — | 5m | T1.3.5 |

### P1.4 — Stage 1 integration

| # | Task | TDD step | File | Time | Depends |
|---|------|----------|------|------|---------|
| T1.4.1 | Run combined Stage 1 test suite (`pytest plugins/pd/hooks/lib/semantic_memory/ plugins/pd/mcp/`) | VERIFY | — | 10m | All P1.1/1.2/1.3 |
| T1.4.2 | Run validate.sh; ensure no regressions | VERIFY | — | 10m | T1.4.1 |
| T1.4.3 | Manual smoke: drop entries_fts on a test DB, restart session, verify auto-rebuild + diag JSON | VERIFY | — | 10m | T1.4.2 |
| T1.4.4 | Commit Stage 1: `pd(101): Stage 1 — FTS5 self-heal + recall tracking + project filter` | COMMIT | — | 3m | T1.4.3 |

**Stage 1 estimate: ~3.5 hours total.** Lands before Stage 2 because
FR-1's audit (Stage 2) consumes FR-3's recall_count and FR-5's filter
behavior.

---

## Stage 2 — Influence Wiring + Lifecycle (FR-1 + FR-4)

**Outcome:** 14 prose blocks restructured + sidecar + audit CLI + ordering
validator + confidence upgrade scan path. Stage 2 produces the data
that exercises Stage 1's `update_recall` mid-session bumps and FR-5
filter end-to-end.

### P2.1 — FR-1 prerequisites: helpers + sidecar + audit

| # | Task | TDD step | File | Time | Depends |
|---|------|----------|------|------|---------|
| T2.1.1 | Write `test_append_influence_log_atomic` (flock concurrent-write fixture) | RED | `plugins/pd/hooks/lib/semantic_memory/test_influence_log.py` (new) | 12m | Stage 1 |
| T2.1.2 | Write `test_append_influence_log_creates_parent_dir` (mkdir defense) | RED | same | 5m | T2.1.1 |
| T2.1.3 | Write `test_append_influence_log_handles_long_lines` (>512 byte JSON line) | RED | same | 8m | T2.1.2 |
| T2.1.4 | Implement `influence_log.py` module with `append_influence_log()` (fcntl.flock + mkdir) | GREEN | `plugins/pd/hooks/lib/semantic_memory/influence_log.py` (new) | 15m | T2.1.3 |
| T2.1.5 | Write `test_audit_basic` (mock sidecar + DB; assert markdown table output) | RED | `plugins/pd/hooks/lib/semantic_memory/test_audit.py` (new) | 12m | T2.1.4 |
| T2.1.6 | Write `test_audit_cutover_filter` (sidecar with mixed pre/post-cutover SHAs) | RED | same | 12m | T2.1.5 |
| T2.1.7 | Write `test_audit_source_project_filter` (cross-project name collision) | RED | same | 8m | T2.1.6 |
| T2.1.8 | Write `test_audit_malformed_line_handling` (corrupt JSONL line → skip+warn) | RED | same | 6m | T2.1.7 |
| T2.1.9 | Write `test_audit_strict_exit_code` (--strict + rate < 80% → exit 2) | RED | same | 6m | T2.1.8 |
| T2.1.10 | Implement `audit.py` module with full CLI + filter logic | GREEN | `plugins/pd/hooks/lib/semantic_memory/audit.py` (new) | 25m | T2.1.9 |
| T2.1.11 | Write `test_check_block_ordering_basic` (synthetic md fixture with 14 markers) | RED | `plugins/pd/scripts/test_check_block_ordering.py` (new) | 10m | T2.1.10 |
| T2.1.12 | Write `test_check_block_ordering_fails_on_misorder` (marker after Branch) | RED | same | 6m | T2.1.11 |
| T2.1.13 | Write `test_check_block_ordering_count_mismatch` (13 markers instead of 14) | RED | same | 6m | T2.1.12 |
| T2.1.14 | Implement `check_block_ordering.py` script | GREEN | `plugins/pd/scripts/check_block_ordering.py` (new) | 15m | T2.1.13 |
| T2.1.15 | Add `.gitignore` entry for `docs/features/*/.influence-log.jsonl` | GREEN | `.gitignore` (root) | 2m | T2.1.14 |

### P2.2 — FR-1 prose-block restructuring (14 sites)

| # | Task | TDD step | File | Time | Depends |
|---|------|----------|------|------|---------|
| T2.2.1 | Capture FR-1 cutover SHA pre-restructure: `git rev-parse HEAD > docs/features/101-memory-flywheel/.fr1-cutover-sha` | SETUP | feature dir | 1m | P2.1 |
| T2.2.2 | Restructure s1 (specify.md spec-reviewer, 1st occurrence) per C-1 canonical template | GREEN | `plugins/pd/commands/specify.md` | 8m | T2.2.1 |
| T2.2.3 | Restructure s2 (specify.md phase-reviewer, 2nd occurrence) | GREEN | same | 8m | T2.2.2 |
| T2.2.4 | Restructure s3, s4 (design.md ×2) | GREEN | `plugins/pd/commands/design.md` | 12m | T2.2.3 |
| T2.2.5 | Restructure s5, s6, s7 (create-plan.md ×3) | GREEN | `plugins/pd/commands/create-plan.md` | 15m | T2.2.4 |
| T2.2.6 | Restructure s8, s9 (implement.md test-deepener Phase A + B) | GREEN | `plugins/pd/commands/implement.md` | 12m | T2.2.5 |
| T2.2.7 | Restructure s10-s14 (implement.md remaining 5 sites; confirm roles by reading subagent_type per dispatch) | GREEN | same | 25m | T2.2.6 |
| T2.2.8 | Run `check_block_ordering.py` — assert 14 markers, 2/2/3/7 distribution, all before Branch | VERIFY | — | 5m | T2.2.7 |
| T2.2.9 | Run `grep -c 'Influence recorded:' plugins/pd/commands/{specify,design,create-plan,implement}.md` — assert 2/2/3/7 | VERIFY | — | 2m | T2.2.8 |
| T2.2.10 | Add `check_block_ordering.py` invocation to `validate.sh` component-check loop | GREEN | `validate.sh` | 5m | T2.2.9 |

### P2.3 — FR-4 confidence upgrade

| # | Task | TDD step | File | Time | Depends |
|---|------|----------|------|------|---------|
| T2.3.1 | Write `test_recompute_confidence_observation_gate` | RED | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` | 6m | Stage 1 |
| T2.3.2 | Write `test_recompute_confidence_use_gate_with_floor` | RED | same | 8m | T2.3.1 |
| T2.3.3 | Write `test_recompute_confidence_recall_only_no_promotion` (floor blocks) | RED | same | 6m | T2.3.2 |
| T2.3.4 | Write `test_recompute_confidence_neither_gate_no_op` | RED | same | 5m | T2.3.3 |
| T2.3.5 | Write `test_recompute_confidence_medium_to_high_obs` | RED | same | 5m | T2.3.4 |
| T2.3.6 | Write `test_recompute_confidence_medium_to_high_use` | RED | same | 5m | T2.3.5 |
| T2.3.7 | Write `test_recompute_confidence_high_idempotent` | RED | same | 4m | T2.3.6 |
| T2.3.8 | Write `test_select_upgrade_candidates_query` (SQL returns hot non-stale entries) | RED | same | 10m | T2.3.7 |
| T2.3.9 | Write `test_upgrade_confidence_wrapper` (end-to-end via run_memory_decay) | RED | same | 10m | T2.3.8 |
| T2.3.10 | Write `test_batch_promote_basic` (parallel to test_batch_demote) | RED | `plugins/pd/hooks/lib/semantic_memory/test_database.py` | 8m | T2.3.9 |
| T2.3.11 | Implement `_recompute_confidence(entry)` in maintenance.py | GREEN | `plugins/pd/hooks/lib/semantic_memory/maintenance.py` | 10m | T2.3.10 |
| T2.3.12 | Implement `_select_upgrade_candidates(db, scan_limit)` SQL helper | GREEN | same | 10m | T2.3.11 |
| T2.3.13 | Implement `upgrade_confidence(db, scan_limit)` wrapper | GREEN | same | 10m | T2.3.12 |
| T2.3.14 | Implement `db.batch_promote(ids, new_confidence, now_iso)` in database.py | GREEN | `plugins/pd/hooks/lib/semantic_memory/database.py` | 8m | T2.3.13 |
| T2.3.15 | Wire `upgrade_confidence` into `run_memory_decay` (called AFTER `decay_confidence`) | GREEN | maintenance.py | 5m | T2.3.14 |
| T2.3.16 | Wire `_recompute_confidence` into `merge_duplicate` (after observation_count++) | GREEN | database.py | 8m | T2.3.15 |
| T2.3.17 | Document new config key `memory_promote_use_signal` in pd.local.md reference | DOCS | `plugins/pd/references/memory-config.md` (or equivalent) | 5m | T2.3.16 |
| T2.3.18 | Run all FR-4 tests; verify all 7 seed cases pass | VERIFY | — | 5m | T2.3.17 |

### P2.4 — Stage 2 integration + dogfood validation

| # | Task | TDD step | File | Time | Depends |
|---|------|----------|------|------|---------|
| T2.4.1 | Run combined Stage 2 test suite | VERIFY | — | 10m | All P2.x |
| T2.4.2 | Run `python -m semantic_memory.audit --feature 101` — verify it produces a table (may have low rate at this point) | VERIFY | — | 5m | T2.4.1 |
| T2.4.3 | Run `validate.sh` — assert check_block_ordering passes | VERIFY | — | 5m | T2.4.2 |
| T2.4.4 | Commit Stage 2: `pd(101): Stage 2 — Influence wiring + confidence upgrade` | COMMIT | — | 3m | T2.4.3 |

**Stage 2 estimate: ~5 hours total.** The 14 prose-block restructure
is the largest scope item; do not parallelize across files but DO
parallelize within a single command file via batch edits.

---

## Stage 3 — Adoption Trigger (FR-6)

**Outcome:** Retrospecting Step 4c.1 surfaces `/pd:promote-pattern`
when qualifying KB entries exist. Includes YOLO auto-chain + dogfood
validation.

### P3.1 — Retrospecting Step 4c.1

| # | Task | TDD step | File | Time | Depends |
|---|------|----------|------|------|---------|
| T3.1.1 | Write `test_retrospecting_promote_trigger_zero_qualifying_silent` (mock enumerate returns count=0) | RED | `plugins/pd/skills/retrospecting/test_promote_trigger.sh` (new) | 8m | Stage 2 |
| T3.1.2 | Write `test_retrospecting_promote_trigger_with_qualifying_emits_question` (count>0 + non-YOLO → AskUserQuestion text grep) | RED | same | 8m | T3.1.1 |
| T3.1.3 | Write `test_retrospecting_promote_trigger_yolo_chains_skill` (YOLO branch → Skill invocation grep) | RED | same | 6m | T3.1.2 |
| T3.1.4 | Write `test_retrospecting_promote_trigger_subprocess_failure_isolated` (enumerate errors → log + continue) | RED | same | 6m | T3.1.3 |
| T3.1.5 | Insert Step 4c.1 prose block into retrospecting/SKILL.md per design C-10 template | GREEN | `plugins/pd/skills/retrospecting/SKILL.md` | 12m | T3.1.4 |
| T3.1.6 | Verify YOLO detection via `[YOLO_MODE]` substring token (matches specifying/SKILL.md:16 precedent) | VERIFY | — | 3m | T3.1.5 |
| T3.1.7 | Run all FR-6 tests | VERIFY | — | 5m | T3.1.6 |

### P3.2 — Dogfood validation

| # | Task | TDD step | File | Time | Depends |
|---|------|----------|------|------|---------|
| T3.2.1 | Run final SC-1 audit: `python -m semantic_memory.audit --feature 101 --strict` — assert ≥80% influence rate on post-cutover dispatches | VERIFY | — | 5m | All Stage 2 |
| T3.2.2 | Smoke-test FR-6 trigger by manually exercising retrospecting Step 4c.1 logic on this feature's KB entries (or a deliberately seeded test set) | VERIFY | — | 10m | T3.2.1 |
| T3.2.3 | Run `validate.sh` end-to-end | VERIFY | — | 10m | T3.2.2 |
| T3.2.4 | Commit Stage 3: `pd(101): Stage 3 — Promote-pattern adoption trigger` | COMMIT | — | 3m | T3.2.3 |

**Stage 3 estimate: ~1 hour total.**

---

## Dependency Summary

```
Stage 1 (FR-2/3/5)  ────────► Stage 2 (FR-1/4)  ────────► Stage 3 (FR-6)
    │                              │                              │
    └─ FR-3 update_recall          └─ FR-1 sidecar consumed      └─ Audit final
       feeds FR-4 use gate            by FR-1 audit                 SC-1 check
```

### Parallel-execution batches within a stage

Within Stage 1:
- P1.1 (FR-2), P1.2 (FR-3), P1.3 (FR-5) are **independent**; can be
  worked in parallel across 3 implementer worktrees.
- P1.4 integration runs after all three.

Within Stage 2:
- P2.1 (helpers) MUST complete before P2.2 (prose) and P2.3 (FR-4).
- P2.2 (prose restructure) and P2.3 (FR-4) are **independent**; can
  parallelize.
- P2.4 integration runs after both.

Within Stage 3:
- All sequential (single skill file).

### Risk-mitigation gates

- **After P1.4 commit:** verify validate.sh + smoke-test before
  starting P2.x.
- **After P2.4 commit:** verify SC-1 audit produces output (even if
  rate < 80% at this point — that's expected since Stage 2 just
  landed).
- **After P3.2.1:** ENFORCE SC-1 ≥ 80% via `--strict`. If fails:
  diagnose via audit's `mcp_status` breakdown (was it MCP errors
  or semantic non-matches?) before declaring feature done.

## Total estimate

- Stage 1: ~3.5h
- Stage 2: ~5.0h
- Stage 3: ~1.0h
- **Total: ~9.5h** spread across the 9.5h would land in 1.5–2 working days
  with parallel implementation worktrees on Stage 1 and Stage 2 sub-batches.
