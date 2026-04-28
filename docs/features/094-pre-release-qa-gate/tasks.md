# Tasks: Feature 094 — Pre-Release Adversarial QA Gate

**Direct-orchestrator execution** with **TDD-first ordering** — tight scope (4 files, ~280 LOC) lands in a single atomic commit.

**⚠ Co-read requirement:** This file is a compact task index. The exact Old/New text quotes, function bodies, prose to insert, and 12-section content live in `plan.md`. The direct-orchestrator (Claude executing the implement phase) MUST co-read `plan.md` Implementation Order + AC Coverage Matrix when running each task — `tasks.md` alone is insufficient for execution. This is intentional per the 091/092/093 surgical-feature template (deliberate to avoid prose duplication between plan and tasks).

If the implementer is a distributed subagent that receives ONLY `tasks.md`, that subagent must Read `plan.md` as its first action.

## Task Index

| ID | Title | File | Depends on |
|----|-------|------|------------|
| **T0** | Capture baselines (PRE_HEAD, PRE_LINES_FF, PRE_TEST_COUNT, PRE_LOG_PASS_COUNT) | — (record in implementation-log.md) | none |
| **T1** | Add 3 anti-drift tests (RED) — `test_finish_feature_step_5b_present` (12 greps), `test_finish_feature_under_600_lines`, `test_qa_gate_procedure_doc_exists` | `plugins/pd/hooks/tests/test-hooks.sh` | T0 |
| **T2** | Insert Step 5b into finish-feature.md (GREEN for grep test) | `plugins/pd/commands/finish-feature.md` | T1 (RED state) |
| **T3** | Create qa-gate-procedure.md (NEW, ~180 lines, 12 H2 sections) (GREEN for procedure-doc-exists test) | `docs/dev_guides/qa-gate-procedure.md` | T1 |
| **T4** | Update retrospecting/SKILL.md — add Step 2c sidecar fold (FR-7b) | `plugins/pd/skills/retrospecting/SKILL.md` | none (independent of T1-T3) |
| **T5** | Quality gates (validate.sh + test-hooks.sh exit 0; +3 PASS) | — | T1, T2, T3, T4 |
| **T6** | Two-phase dogfood self-test + cleanup + .gitignore update | `retro.md` + `.gitignore` | T5 |

T2, T3, T4 are independent — could parallelize via worktrees. Direct-orchestrator runs them sequentially for atomic commit cohesion (justified in plan.md Notes).

## T0 — Capture baselines

Record before any edits:
```bash
PRE_HEAD=$(git rev-parse HEAD)
PRE_LINES_FF=$(wc -l < plugins/pd/commands/finish-feature.md)         # expect 508
PRE_LINES_TH=$(wc -l < plugins/pd/hooks/tests/test-hooks.sh)          # expect 3494
PRE_LINES_RS=$(wc -l < plugins/pd/skills/retrospecting/SKILL.md)
PRE_TEST_COUNT=$(grep -c 'log_test ' plugins/pd/hooks/tests/test-hooks.sh)  # expect 111
PRE_LOG_PASS_COUNT=$(bash plugins/pd/hooks/tests/test-hooks.sh 2>&1 | grep -c '  PASS')  # expect 111
```
**DoD:** all 6 captured; ±5% from expected else investigate.

## T1 — RED tests

Per plan.md T1: add 3 functions + register them. Confirm RED state (`bash plugins/pd/hooks/tests/test-hooks.sh` exits non-zero with `test_finish_feature_step_5b_present` + `test_qa_gate_procedure_doc_exists` failing; `test_finish_feature_under_600_lines` passes since 508 < 600).

**DoD:** RED confirmed; only 1 of 3 new tests passes (`under_600_lines`); `PRE_LOG_PASS_COUNT + 1` total.

## T2 — Step 5b prose (GREEN for grep test)

Per plan.md T2: insert Step 5b between line 372 ("Do NOT proceed...") and line 374 ("### Step 5a-bis"). Full New-text content in plan.md.

**DoD:**
- `wc -l plugins/pd/commands/finish-feature.md` ≤ `PRE_LINES_FF + 50` AND `< 600`
- `test_finish_feature_step_5b_present` flips FAIL → PASS (all 12 greps)

## T3 — qa-gate-procedure.md (NEW)

Per plan.md T3: 12 H2 sections matching `^## §[0-9]+ — `. Critical inline content per design TDs:
- §3 must include `import sys, json, re` (TD-8 heredoc)
- §4 must include `normalize_location` + `cross_confirmed`
- §5 must include `^- \*\*#[0-9]{5}\*\*` regex + per-feature heading template
- §7 must include atomic-rename pseudocode
- §8 must include `awk "/^## Override ${last_n} /,0"`
- §11 must document >2000 LOC threshold
- §12 must document override-storm trigger

**DoD:**
- `[ -f docs/dev_guides/qa-gate-procedure.md ]` exit 0
- `grep -cE '^## §[0-9]+ — ' docs/dev_guides/qa-gate-procedure.md` ≥ 12
- `grep -q 'import sys, json, re' docs/dev_guides/qa-gate-procedure.md` exit 0
- `grep -q 'FR-3\|FR-8\|FR-9' docs/dev_guides/qa-gate-procedure.md` exit 0
- `test_qa_gate_procedure_doc_exists` flips FAIL → PASS

## T4 — retrospecting/SKILL.md (FR-7b)

Per plan.md T4: insert "Step 2c: Fold Pre-Release QA Sidecars" before existing "Step 3: Write retro.md" at line 168.

**DoD (3 separate greps — all must exit 0):**
- `grep -q 'qa-gate-low-findings\.md' plugins/pd/skills/retrospecting/SKILL.md` exit 0
- `grep -q 'qa-gate\.log' plugins/pd/skills/retrospecting/SKILL.md` exit 0
- `grep -q 'Pre-release QA notes' plugins/pd/skills/retrospecting/SKILL.md` exit 0
- `wc -l < plugins/pd/skills/retrospecting/SKILL.md` = `PRE_LINES_RS + 15` (±5)

## T5 — Quality gates

```bash
./validate.sh                                    # exit 0
bash plugins/pd/hooks/tests/test-hooks.sh        # exit 0
```

**DoD:**
- Both exit 0
- `bash plugins/pd/hooks/tests/test-hooks.sh 2>&1 | grep -c '  PASS'` = `PRE_LOG_PASS_COUNT + 3`
- `validate.sh` warning count unchanged

## T6 — Dogfood self-test (3 phases)

**Pre-step:** if `docs/features/094-pre-release-qa-gate/retro.md` does not exist, create it with `# Retro: Feature 094 — Pre-Release Adversarial QA Gate` H1. The "Manual Verification" section gets appended below; retrospect skill on completion will fold its own AORTA content above this section.

Per plan.md T6:
- **(a)** Self-dispatch via /pd:finish-feature gate prose on feature 094 branch — verify dispatch + bucket + parse paths; document AC-6/7/8/10/16/17 observations in retro.md "Manual Verification" section. Document AC-deferred-verification for AC-9/11/13/19 (need feature 095 first-run).
- **(b)** Synthetic-HIGH injection (2 patterns: SQL + shell) on scratch branch; require ≥1 detection per pattern; fallback if both escape = HIGH against gate itself.
- **(c)** Cleanup: `rm` any dogfood-generated `.qa-gate*` files from feature dir; add `.qa-gate.json`, `.qa-gate.log`, `.qa-gate-low-findings.md` to repo `.gitignore`.

**DoD:**
- All 3 phases documented in `retro.md` "Manual Verification" section
- `git status` clean of dogfood artifacts
- `.gitignore` updated with 3 new patterns

## AC Coverage (summary)

Per plan.md AC Coverage Matrix:
- **Auto-tested (10 ACs):** AC-1, 2, 3, 4, 5, 5b, 12, 15, 18, 20 (via test-hooks)
- **Manual via T6 dogfood (7 ACs):** AC-6, 7, 8, 9, 10, 16, 17
- **AC-deferred-verification (4 ACs):** AC-11, 13, 19 + end-to-end coverage — verified by feature 095 first-run; documented in retro.md as known contingency

## Manual ACs tracked in retro.md

11 ACs (AC-5b, 6, 7, 8, 9, 10, 11, 13, 17, 19) require manual confirmation during T6 dogfood + post-merge feature 095 first-run. Each tracked as a checkbox in retro.md "Manual Verification" section per design Manual Verification Gate.
