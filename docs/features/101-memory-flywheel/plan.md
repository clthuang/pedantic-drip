# Feature 101 — Memory Flywheel Loop Closure (Plan)

> Spec: `spec.md` · Design: `design.md` · PRD: `prd.md` · Backlog #00053

## Overview

Three-stage implementation closing four flow gaps in pd's memory subsystem.
Each stage is independently testable. TDD ordering: tests first (red),
implementation (green), then refactor.

**Stage placement reconciliation (per design C-8 / Stage Boundaries):**
FR-4 function definitions + `_select_upgrade_candidates` + `upgrade_confidence`
wrapper + `run_memory_decay` integration belong to Stage 1 (P1.5);
only the `merge_duplicate` inline call + integration tests with real
influence_count data flowing belong to Stage 2 (P2.5). FR-1 prose
restructuring + sidecar + audit form Stage 2's core (P2.1-P2.4).

```
Stage 1: Foundations (FR-2/3/5 + FR-4 code)     ─── localized backend, no orchestrator prose changes
   ↓
Stage 2: Influence Wiring + FR-4 activation     ─── 14 prose blocks + sidecar + audit + merge_duplicate hook
   ↓
Stage 3: Adoption Trigger (FR-6)                ─── retrospecting Step 4c.1 + dogfood validation
```

## Complexity Convention

Per CLAUDE.md plan-reviewer rubric, tasks use **complexity tiers**
instead of minute estimates:

- **S** (Simple): mechanical / single-file ≤ ~15 lines / one assertion
- **M** (Medium): multi-step / one cross-file change / 2-5 assertions
- **C** (Complex): cross-file orchestration / new module / non-trivial logic

Total complexity counts inform scheduling; exact wall-clock varies by
implementer and worktree-parallelism state.

## Stage 1 — Foundations (FR-2 + FR-3 + FR-5)

**Outcome:** FTS5 self-heal, mid-session recall tracking, project-scoped
influence filtering — all backend changes; no orchestrator-prose edits.
Stage ships independently testable.

### P1.1 — FR-2: FTS5 integrity check + rebuild CLI

| # | Task | TDD | File | Cx | Depends |
|---|------|-----|------|----|---------|
| T1.1.1 | Write `test_rebuild_fts5_basic` (drop+populate+rebuild → count > 0) | RED | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` | S | — |
| T1.1.2 | Write `test_rebuild_fts5_diagnostic_file` (8 JSON fields) | RED | same | S | T1.1.1 |
| T1.1.3 | Write `test_rebuild_fts5_refire` (refires array append) | RED | same | S | T1.1.2 |
| T1.1.4 | Write `test_rebuild_fts5_user_version_classification` | RED | same | M | T1.1.3 |
| T1.1.5 | Implement `rebuild_fts5(db_path)` with isolation_level=None + BEGIN IMMEDIATE + retry + integrity-check | GREEN | `plugins/pd/hooks/lib/semantic_memory/maintenance.py` | C | T1.1.4 |
| T1.1.6 | Implement diagnostic JSON read-modify-write | GREEN | same | M | T1.1.5 |
| T1.1.7 | Add `--rebuild-fts5` CLI subcommand | GREEN | same | S | T1.1.6 |
| T1.1.8 | Add `check_fts5_integrity()` to `session-start.sh` | GREEN | `plugins/pd/hooks/session-start.sh` | M | T1.1.7 |
| T1.1.9 | Run all FR-2 tests | VERIFY | — | S | T1.1.8 |

### P1.2 — FR-3: Mid-session recall tracking

| # | Task | TDD | File | Cx | Depends |
|---|------|-----|------|----|---------|
| T1.2.1 | Write `test_search_memory_increments_recall_count` | RED | `plugins/pd/mcp/test_memory_server.py` | S | — |
| T1.2.2 | Write `test_search_memory_within_call_dedup` | RED | same | S | T1.2.1 |
| T1.2.3 | Write `test_search_memory_across_calls_increments_per_call` | RED | same | S | T1.2.2 |
| T1.2.4 | Write `test_search_memory_recall_failure_logs_warn_returns_entries` | RED | same | M | T1.2.3 |
| T1.2.5 | Modify `_process_search_memory` to call `db.update_recall` (set-deduped ids) | GREEN | `plugins/pd/mcp/memory_server.py` | M | T1.2.4 |
| T1.2.6 | Wrap update_recall try/except; log warn, no raise | GREEN | same | S | T1.2.5 |
| T1.2.7 | Write `test_search_memory_benchmark.py` (monkeypatch baseline + post-FR-3, AC-3.6 P50 bound) | GREEN | new file | C | T1.2.6 |
| T1.2.8 | Run benchmark; assert `delta_p50 < max(5, 0.05 * baseline_p50_ms)`. **HARD GATE: on failure, do NOT proceed; trigger R-11 mitigation review.** | VERIFY | — | S | T1.2.7 |

### P1.3 — FR-5: source_project filter at influence recording

**Same-file conflict notice:** P1.2 and P1.3 both modify
`plugins/pd/mcp/memory_server.py`. **Work serially** in one worktree
(P1.2 first since FR-3 changes are smaller), or coordinate imports +
module-state references explicitly if running in parallel worktrees.

| # | Task | TDD | File | Cx | Depends |
|---|------|-----|------|----|---------|
| T1.3.1 | Write `test_record_influence_filters_cross_project` | RED | `plugins/pd/mcp/test_memory_server.py` | S | T1.2.6 |
| T1.3.2 | Write `test_record_influence_same_project_passes` | RED | same | S | T1.3.1 |
| T1.3.3 | Write `test_record_influence_null_project_root_bypass_with_warn` | RED | same | M | T1.3.2 |
| T1.3.4 | Modify `_process_record_influence_by_content` filter + null bypass | GREEN | `plugins/pd/mcp/memory_server.py` | M | T1.3.3 |
| T1.3.5 | Add null-`_project_root` bypass + stderr warning | GREEN | same | S | T1.3.4 |
| T1.3.6 | Run all FR-5 tests | VERIFY | — | S | T1.3.5 |

### P1.5 — FR-4 code (function defs + run_memory_decay wiring; merge_duplicate hook deferred to Stage 2)

Per design C-8 / Stage Boundaries: FR-4 function definitions belong
to Stage 1; only the `merge_duplicate` inline call + integration tests
exercising the use gate with real influence_count data flowing belong
to Stage 2 (P2.5).

| # | Task | TDD | File | Cx | Depends |
|---|------|-----|------|----|---------|
| T1.5.1 | Write `test_recompute_confidence_observation_gate` | RED | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` | S | — |
| T1.5.2 | Write `test_recompute_confidence_use_gate_with_floor` | RED | same | S | T1.5.1 |
| T1.5.3 | Write `test_recompute_confidence_recall_only_no_promotion` (floor blocks) | RED | same | S | T1.5.2 |
| T1.5.4 | Write `test_recompute_confidence_neither_gate_no_op` | RED | same | S | T1.5.3 |
| T1.5.5 | Write `test_recompute_confidence_medium_to_high_obs` | RED | same | S | T1.5.4 |
| T1.5.6 | Write `test_recompute_confidence_medium_to_high_use` | RED | same | S | T1.5.5 |
| T1.5.7 | Write `test_recompute_confidence_high_idempotent` | RED | same | S | T1.5.6 |
| T1.5.8 | Write `test_select_upgrade_candidates_query` (hot non-stale) | RED | same | M | T1.5.7 |
| T1.5.9 | Write `test_upgrade_confidence_wrapper` (end-to-end) | RED | same | M | T1.5.8 |
| T1.5.10 | Write `test_batch_promote_basic` parallel to existing batch_demote | RED | `plugins/pd/hooks/lib/semantic_memory/test_database.py` | M | T1.5.9 |
| T1.5.11 | Write `test_run_memory_decay_invokes_upgrade_after_decay` (mock+spy call order) | RED | `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` | M | T1.5.10 |
| T1.5.12 | Implement `_recompute_confidence(entry)` in maintenance.py | GREEN | `plugins/pd/hooks/lib/semantic_memory/maintenance.py` | M | T1.5.11 |
| T1.5.13 | Implement `_select_upgrade_candidates(db, scan_limit)` SQL helper | GREEN | same | M | T1.5.12 |
| T1.5.14 | Implement `upgrade_confidence(db, scan_limit)` wrapper | GREEN | same | M | T1.5.13 |
| T1.5.15 | Implement `db.batch_promote(ids, new_confidence, now_iso)` | GREEN | `plugins/pd/hooks/lib/semantic_memory/database.py` | M | T1.5.14 |
| T1.5.16 | Wire `upgrade_confidence` into `run_memory_decay` AFTER `decay_confidence` returns. Pre-check: grep callers of `run_memory_decay` to confirm no caller relies on existing return-shape (`upgraded` key is additive). | GREEN | maintenance.py | M | T1.5.15 |
| T1.5.17 | Document `memory_promote_use_signal` (default 5) in `.claude/pd.local.md` (existing config-key file; add inline alongside `memory_promote_min_observations`) | DOCS | `.claude/pd.local.md` | S | T1.5.16 |
| T1.5.18 | Run all FR-4 Stage-1 tests | VERIFY | — | S | T1.5.17 |

### P1.4 — Stage 1 integration

| # | Task | TDD | File | Cx | Depends |
|---|------|-----|------|----|---------|
| T1.4.1 | Run combined Stage 1 test suite (`pytest plugins/pd/hooks/lib/semantic_memory/ plugins/pd/mcp/`) | VERIFY | — | S | T1.1.9 + T1.2.8 + T1.3.6 + T1.5.18 |
| T1.4.2 | Run validate.sh | VERIFY | — | S | T1.4.1 |
| T1.4.3 | Manual smoke: drop entries_fts on test DB, run session-start, verify rebuild + diag JSON | VERIFY | — | M | T1.4.2 |
| T1.4.4 | Commit Stage 1: `pd(101): Stage 1 — Foundations (FTS5 + recall + project filter + FR-4 code)` | COMMIT | — | S | T1.4.3 |

**Stage 1 task count:** P1.1=9 + P1.2=8 + P1.3=6 + P1.5=18 + P1.4=4 = **45 tasks**.
Lands before Stage 2; FR-1's audit consumes FR-3 + FR-5 + FR-4 data flows.

---

## Stage 2 — Influence Wiring + Lifecycle (FR-1 + FR-4)

**Outcome:** 14 prose blocks restructured + sidecar + audit CLI + ordering
validator + confidence upgrade scan path. Stage 2 produces the data
that exercises Stage 1's `update_recall` mid-session bumps and FR-5
filter end-to-end.

### P2.1 — FR-1 prerequisites: helpers + sidecar + audit

| # | Task | TDD | File | Cx | Depends |
|---|------|-----|------|----|---------|
| T2.1.1 | Write `test_append_influence_log_atomic` (flock concurrent-write) | RED | `plugins/pd/hooks/lib/semantic_memory/test_influence_log.py` (new) | M | Stage 1 |
| T2.1.2 | Write `test_append_influence_log_creates_parent_dir` (mkdir defense) | RED | same | S | T2.1.1 |
| T2.1.3 | Write `test_append_influence_log_handles_long_lines` (>512 byte JSON) | RED | same | S | T2.1.2 |
| T2.1.4 | Implement `influence_log.py` with `append_influence_log()` (fcntl.flock + mkdir) | GREEN | `plugins/pd/hooks/lib/semantic_memory/influence_log.py` (new) | M | T2.1.3 |
| T2.1.5 | Write `test_audit_basic` (mock sidecar + DB) | RED | `plugins/pd/hooks/lib/semantic_memory/test_audit.py` (new) | M | T2.1.4 |
| T2.1.6 | Write `test_audit_cutover_filter` | RED | same | M | T2.1.5 |
| T2.1.7 | Write `test_audit_source_project_filter` | RED | same | M | T2.1.6 |
| T2.1.8 | Write `test_audit_malformed_line_handling` | RED | same | S | T2.1.7 |
| T2.1.9 | Write `test_audit_strict_exit_code` | RED | same | S | T2.1.8 |
| T2.1.10 | Implement `audit.py` with full CLI + filter logic | GREEN | `plugins/pd/hooks/lib/semantic_memory/audit.py` (new) | C | T2.1.9 |
| T2.1.11 | Write `test_check_block_ordering_basic` (14-marker fixture) | RED | `plugins/pd/scripts/test_check_block_ordering.py` (new) | M | T2.1.10 |
| T2.1.12 | Write `test_check_block_ordering_fails_on_misorder` | RED | same | S | T2.1.11 |
| T2.1.13 | Write `test_check_block_ordering_count_mismatch` | RED | same | S | T2.1.12 |
| T2.1.14 | Implement `check_block_ordering.py` script | GREEN | `plugins/pd/scripts/check_block_ordering.py` (new) | M | T2.1.13 |
| T2.1.15 | Add `.gitignore` entry for `docs/features/*/.influence-log.jsonl` | GREEN | `.gitignore` (root) | S | T2.1.14 |

### P2.2 — FR-1 prose-block restructuring (14 sites)

**Prerequisite RED tests for canonical block content** (NOT just
positional ordering — these verify the block's behavior produces
correct sidecar entries):

| # | Task | TDD | File | Cx | Depends |
|---|------|-----|------|----|---------|
| T2.2.0a | Write `test_canonical_block_content_complete` — assert each restructured site contains literal substrings: `record_influence_by_content`, `append_influence_log`, `mcp_status`, `matched_count`, AND HTML marker `<!-- influence-tracking-site: sN -->` (N matching the site_id table). | RED | `plugins/pd/scripts/test_canonical_block_content.py` (new) | M | T2.1.15 |
| T2.2.0b | Write `test_canonical_block_writes_correct_mcp_status` — fixture simulates 3 paths (MCP success → `'ok'` + matched_count from response; MCP exception → `'error'` + matched_count=null; MCP unavailable → `'skipped'` + matched_count=null). Assert each path appends sidecar with the matching `mcp_status`. **This validates the audit's three-way breakdown.** | RED | same | C | T2.2.0a |
| T2.2.1 | Capture FR-1 cutover SHA. **Pre-check + recovery:** if `.influence-log.jsonl` exists with content from a prior partial implement run, rename to `.influence-log.jsonl.pre-cutover` and continue. Then `git rev-parse HEAD > docs/features/101-memory-flywheel/.fr1-cutover-sha` | SETUP | feature dir | S | T2.2.0b |
| T2.2.2 | Restructure s1 (specify.md spec-reviewer, 1st) per C-1 canonical template | GREEN | `plugins/pd/commands/specify.md` | M | T2.2.1 |
| T2.2.3 | Restructure s2 (specify.md phase-reviewer, 2nd) | GREEN | same | M | T2.2.2 |
| T2.2.4 | Restructure s3, s4 (design.md ×2) | GREEN | `plugins/pd/commands/design.md` | M | T2.2.3 |
| T2.2.5 | Restructure s5, s6, s7 (create-plan.md ×3) | GREEN | `plugins/pd/commands/create-plan.md` | M | T2.2.4 |
| T2.2.6 | Restructure s8, s9 (implement.md test-deepener Phase A + B) | GREEN | `plugins/pd/commands/implement.md` | M | T2.2.5 |
| T2.2.7 | Restructure s10-s14 (implement.md remaining 5 sites; confirm roles by reading subagent_type per dispatch) | GREEN | same | C | T2.2.6 |
| T2.2.8 | Run `check_block_ordering.py` + `test_canonical_block_content.py` — assert all green | VERIFY | — | S | T2.2.7 |
| T2.2.9 | Run `grep -c 'Influence recorded:' plugins/pd/commands/{specify,design,create-plan,implement}.md` — assert 2/2/3/7 | VERIFY | — | S | T2.2.8 |
| T2.2.10 | Add `check_block_ordering.py` + `test_canonical_block_content.py` to `validate.sh` component-check loop | GREEN | `validate.sh` | S | T2.2.9 |

### P2.3 — FR-4 Stage-2 portion: `merge_duplicate` hook + live integration

(FR-4 code already shipped in Stage 1 P1.5. T2.3.1+T2.3.2 are
DB-layer unit work that depend ONLY on P1.5; T2.3.3 integration test
is the only piece that requires Stage 2 prose to be live to populate
sidecar with real influence data.)

| # | Task | TDD | File | Cx | Depends |
|---|------|-----|------|----|---------|
| T2.3.1 | Write `test_merge_duplicate_recomputes_confidence` (mock _recompute_confidence; assert called with merged-entry dict after observation_count++) | RED | `plugins/pd/hooks/lib/semantic_memory/test_database.py` | M | T1.5.18 (only needs P1.5 code) |
| T2.3.2 | Wire `_recompute_confidence` into `merge_duplicate` (after observation_count++) | GREEN | `plugins/pd/hooks/lib/semantic_memory/database.py` | M | T2.3.1 |
| T2.3.3 | Write integration test `test_use_gate_promotes_via_real_influence_data` — populate sidecar via reviewer-dispatch fixture (or mocked equivalent), run upgrade_confidence, assert at least one entry promotes via use-gate path | RED→GREEN | new integration test | C | T2.3.2 + T2.4.5 (Stage 2 prose committed) |
| T2.3.4 | Run all FR-4 Stage-2 tests | VERIFY | — | S | T2.3.3 |

### P2.4 — Stage 2 prose-block + helper integration + LIVE smoke

| # | Task | TDD | File | Cx | Depends |
|---|------|-----|------|----|---------|
| T2.4.1 | Run combined Stage 2 test suite (P2.1 + P2.2) | VERIFY | — | S | All P2.1/P2.2 |
| T2.4.2 | **Live smoke** — run `bash plugins/pd/scripts/smoke-influence-block.sh` (NEW; simulates the orchestrator emitting the canonical block by extracting the bash snippet from a restructured site, executing it with mock `record_influence_by_content` MCP, and asserting `.influence-log.jsonl` gains a well-formed I-7 line). **HARD GATE: on failure, revert P2.2 uncommitted edits via `git checkout HEAD -- plugins/pd/commands/{specify,design,create-plan,implement}.md` before continuing.** | VERIFY | — | M | T2.4.1 |
| T2.4.3 | Run `python -m semantic_memory.audit --feature 101` — verify it produces a table (may have low rate pre-cutover) | VERIFY | — | S | T2.4.2 |
| T2.4.4 | Run `validate.sh` — assert check_block_ordering passes | VERIFY | — | S | T2.4.3 |
| T2.4.5 | Commit Stage 2 prose: `pd(101): Stage 2 — Influence wiring (14 sites) + sidecar + audit` | COMMIT | — | S | T2.4.4 |

### P2.5 — Stage 2 FR-4 hook + final integration

| # | Task | TDD | File | Cx | Depends |
|---|------|-----|------|----|---------|
| T2.5.1 | Run `python -m semantic_memory.audit --feature 101` and verify the `mcp_status` breakdown shows non-zero count for at least the `'ok'` bucket (proves real MCP calls fired during the live smoke and Stage 2 reviewer dispatches). | VERIFY | — | S | T2.4.5 + T2.3.4 |
| T2.5.2 | Commit Stage 2 FR-4 hook: `pd(101): Stage 2 — merge_duplicate FR-4 hook + live integration` | COMMIT | — | S | T2.5.1 |

**Stage 2 task count:** P2.1=15 + P2.2=12 + P2.3=4 + P2.4=5 + P2.5=2 = **38 tasks**
across P2.1/2.2/2.3/2.4/2.5.

---

## Stage 3 — Adoption Trigger (FR-6)

**Outcome:** Retrospecting Step 4c.1 surfaces `/pd:promote-pattern`
when qualifying KB entries exist. Includes YOLO auto-chain + dogfood
validation.

### P3.1 — Retrospecting Step 4c.1

Skill prose validation uses Python pytest convention (matches existing
pd test pattern `plugins/pd/mcp/test_*.py`; bash tests in
`plugins/pd/hooks/tests/` are for shell scripts only — skill markdown
is parsed by Python tests):

| # | Task | TDD | File | Cx | Depends |
|---|------|-----|------|----|---------|
| T3.1.1 | Write `test_promote_trigger_zero_qualifying_silent` — parse SKILL.md, assert Step 4c.1 block contains the count-check + silent-skip path | RED | `plugins/pd/skills/retrospecting/test_promote_trigger.py` (new) | M | T2.5.2 |
| T3.1.2 | Write `test_promote_trigger_with_qualifying_emits_question` — assert AskUserQuestion options text present in non-YOLO branch | RED | same | M | T3.1.1 |
| T3.1.3 | Write `test_promote_trigger_yolo_chains_skill` — assert YOLO branch contains `Skill({skill: "pd:promoting-patterns"})` invocation | RED | same | M | T3.1.2 |
| T3.1.4 | Write `test_promote_trigger_subprocess_failure_isolated` — assert error-handling prose ("log warn + continue retro") present | RED | same | S | T3.1.3 |
| T3.1.5 | Insert Step 4c.1 prose into `retrospecting/SKILL.md` per design C-10 template | GREEN | `plugins/pd/skills/retrospecting/SKILL.md` | M | T3.1.4 |
| T3.1.6 | Verify YOLO detection via `[YOLO_MODE]` substring token (matches `specifying/SKILL.md:16` precedent) | VERIFY | — | S | T3.1.5 |
| T3.1.7 | Run all FR-6 tests: `pytest plugins/pd/skills/retrospecting/ -v` | VERIFY | — | S | T3.1.6 |

### P3.2 — Dogfood validation

| # | Task | TDD | File | Cx | Depends |
|---|------|-----|------|----|---------|
| T3.2.1 | Run final SC-1 audit: `python -m semantic_memory.audit --feature 101 --strict`. Assert rate ≥ 80% post-cutover OR diagnose via `mcp_status` breakdown. | VERIFY | — | S | T3.1.7 |
| T3.2.2 | Smoke-test FR-6 trigger: invoke retrospecting Step 4c.1 logic against deliberately seeded test KB (≥1 qualifying entry); verify trigger fires | VERIFY | — | M | T3.2.1 |
| T3.2.3 | Run `validate.sh` end-to-end | VERIFY | — | S | T3.2.2 |
| T3.2.4 | Commit Stage 3: `pd(101): Stage 3 — Promote-pattern adoption trigger` | COMMIT | — | S | T3.2.3 |

**Stage 3 task count:** P3.1=7 + P3.2=4 = **11 tasks**.

---

## Dependency Summary

```
Stage 1 (FR-2/3/5 + FR-4 code)  ─────► Stage 2 (FR-1 + FR-4 hook)  ─────► Stage 3 (FR-6)
    │                                       │                                   │
    └─ FR-3 update_recall                   └─ FR-1 sidecar consumed           └─ Audit final
       feeds FR-4 use gate                     by FR-1 audit + use-gate            SC-1 + dogfood
       FR-4 code in place                      activation via merge_duplicate
```

### Parallel-execution batches within a stage

**Within Stage 1:**
- P1.1 (FR-2: `maintenance.py` + `session-start.sh`) and P1.5 (FR-4
  code: `maintenance.py` + `database.py`) **share `maintenance.py`** —
  serialize within one worktree, OR coordinate function-boundary
  additions if running parallel worktrees.
- P1.2 (FR-3: `memory_server.py`) and P1.3 (FR-5: `memory_server.py`)
  **share `memory_server.py`** — work serially in one worktree
  (P1.2 first → P1.3) per the same-file-conflict notice in P1.3.
- P1.1 + P1.5 chain is genuinely independent of the P1.2 → P1.3 chain
  (different files, no overlap). Can run as 2 parallel worktrees.
- P1.4 integration runs after all four sub-batches converge.

**Within Stage 2:**
- P2.1 (helpers) MUST complete before P2.2 (prose).
- P2.2 (prose restructure) is sequential within (per-file ordering).
- P2.3 (FR-4 hook) depends on P2.4.5 (Stage 2 prose committed).
- P2.5 final.

**Within Stage 3:** sequential single-file change.

### Risk-mitigation gates

- **After P1.4 commit:** verify validate.sh + smoke-test before
  starting P2.x.
- **After P2.4 commit:** verify SC-1 audit produces output (even if
  rate < 80% at this point — that's expected since Stage 2 just
  landed).
- **After P3.2.1:** ENFORCE SC-1 ≥ 80% via `--strict`. If fails:
  diagnose via audit's `mcp_status` breakdown (was it MCP errors
  or semantic non-matches?) before declaring feature done.

## Task Count Summary

| Stage | Tasks |
|-------|-------|
| Stage 1 (P1.1=9 + P1.2=8 + P1.3=6 + P1.5=18 + P1.4=4) | 45 |
| Stage 2 (P2.1=15 + P2.2=12 + P2.3=4 + P2.4=5 + P2.5=2) | 38 |
| Stage 3 (P3.1=7 + P3.2=4) | 11 |
| **Total** | **94** |

Tasks use Cx tier (S/M/C) per CLAUDE.md plan-reviewer rubric — no
time/LOC estimates. Implementer reports actual wall-clock in retrospect.

## New Deliverables Summary

Files created during implementation (consolidated for traceability):
- `plugins/pd/hooks/lib/semantic_memory/influence_log.py` (FR-1 helper)
- `plugins/pd/hooks/lib/semantic_memory/audit.py` (FR-1 audit CLI)
- `plugins/pd/scripts/check_block_ordering.py` (FR-1 ordering validator)
- `plugins/pd/scripts/test_canonical_block_content.py` (FR-1 content validator + tests)
- `plugins/pd/scripts/smoke-influence-block.sh` (FR-1 live-smoke harness for T2.4.2)
- `plugins/pd/skills/retrospecting/test_promote_trigger.py` (FR-6 SKILL.md prose tests)
- `docs/features/101-memory-flywheel/.fr1-cutover-sha` (one-line cutover marker)
- `docs/features/101-memory-flywheel/.influence-log.jsonl` (gitignored sidecar)
- `~/.claude/pd/memory/.fts5-rebuild-diag.json` (FR-2 diagnostic, not in git)
