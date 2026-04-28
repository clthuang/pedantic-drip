# Plan: Feature 094 — Pre-Release Adversarial QA Gate

## Status
- Created: 2026-04-29
- Phase: create-plan (review iteration 2 after plan-reviewer iter 1: 5 blockers + 5 warnings + 2 suggestions)
- Upstream: design.md (7 TDs + C1..C5 + I-1..I-6 + R-1..R-7); spec.md (21 ACs + 12 FRs)

## Architecture Summary

One feature, four files touched (one new), one atomic commit. The gate is **prose interpreted by Claude at run-time** in `finish-feature.md` + extracted procedure doc. Bash code lives only in test-hooks assertions and the dispatch-time `python3 -c` JSON parse helper (TD-8) inside the procedure doc.

```
plugins/pd/commands/finish-feature.md           [edit, +30-50 lines]
docs/dev_guides/qa-gate-procedure.md            [new, ~180 lines]
plugins/pd/skills/retrospecting/SKILL.md        [edit, +15 lines]
plugins/pd/hooks/tests/test-hooks.sh            [edit, +35 lines, +3 tests]
```

Direct-orchestrator pattern justified: total touch ~280 LOC across 4 files; atomic commit cohesion outweighs parallelism. Steps T2/T3/T4 are independent — could be parallelized via worktrees if desired; documented as alternative in Notes section.

## Stage 0 — Capture Baselines (BEFORE any edits)

Run these commands once and record output in implementation-log.md or a scratch comment block. All later DoDs reference these baselines.

```bash
PRE_HEAD=$(git rev-parse HEAD)
PRE_LINES_FF=$(wc -l < plugins/pd/commands/finish-feature.md)
PRE_LINES_TH=$(wc -l < plugins/pd/hooks/tests/test-hooks.sh)
PRE_LINES_RS=$(wc -l < plugins/pd/skills/retrospecting/SKILL.md)
PRE_TEST_COUNT=$(grep -c 'log_test ' plugins/pd/hooks/tests/test-hooks.sh)
PRE_LOG_PASS_COUNT=$(bash plugins/pd/hooks/tests/test-hooks.sh 2>&1 | grep -c '  PASS')

# Expected baselines (verified at plan-write time):
# PRE_LINES_FF = 508
# PRE_LINES_TH = 3494
# PRE_TEST_COUNT = 111
# PRE_LOG_PASS_COUNT = 111
```

**Stage 0 DoD:** all 6 variables captured; if any value differs from "Expected baselines" by >5%, pause and investigate (a recent commit may have shifted state since plan was written).

## Implementation Order — TDD-first

Inverted from initial draft per plan-reviewer iter 1 blocker 2. Tests come first (RED), then implementation makes them pass (GREEN). Each step's DoD includes the corresponding test transition.

### T1 — Add 3 anti-drift tests (RED phase)

**File:** `plugins/pd/hooks/tests/test-hooks.sh`
**Action:** Add 3 new test functions and register them. Tests will FAIL initially because the prose they verify doesn't exist yet. Confirming the RED state proves the tests catch the regression.

**Old text** (registration block, line 3411-3414):
```
    test_sync_cache_json
    test_sync_cache_missing_source
    test_sync_cache_detects_arbitrary_marketplace
    test_sync_cache_marketplace_json_target_derives
```

**New text** (append 3 calls in same block):
```
    test_sync_cache_json
    test_sync_cache_missing_source
    test_sync_cache_detects_arbitrary_marketplace
    test_sync_cache_marketplace_json_target_derives
    test_finish_feature_step_5b_present
    test_finish_feature_under_600_lines
    test_qa_gate_procedure_doc_exists
```

**Function definitions** — add anywhere in the function-definition section (e.g., after the existing `test_sync_cache_*` functions around line 388):

```bash
test_finish_feature_step_5b_present() {
    log_test "finish-feature.md contains Step 5b QA gate dispatch"
    local file="${PROJECT_ROOT}/plugins/pd/commands/finish-feature.md"
    local fails=0
    grep -qE '^##\s.*Step 5b.*Pre-Release Adversarial QA Gate' "$file" || { echo "  AC-14.1 missing Step 5b heading"; ((fails++)); }
    grep -q 'pd:security-reviewer' "$file" || { echo "  AC-14.2 missing pd:security-reviewer"; ((fails++)); }
    grep -q 'pd:code-quality-reviewer' "$file" || { echo "  AC-14.3 missing pd:code-quality-reviewer"; ((fails++)); }
    grep -q 'pd:implementation-reviewer' "$file" || { echo "  AC-14.4 missing pd:implementation-reviewer"; ((fails++)); }
    grep -q 'pd:test-deepener' "$file" || { echo "  AC-14.5 missing pd:test-deepener"; ((fails++)); }
    grep -q 'Step A' "$file" || { echo "  AC-14.6 missing 'Step A' token"; ((fails++)); }
    grep -q '\.qa-gate\.json' "$file" || { echo "  AC-14.7 missing .qa-gate.json reference"; ((fails++)); }
    grep -q '\.qa-gate-low-findings\.md' "$file" || { echo "  AC-14.8 missing .qa-gate-low-findings.md reference"; ((fails++)); }
    grep -q 'dispatch all 4 reviewers in parallel' "$file" || { echo "  AC-3 missing literal parallel-dispatch phrase"; ((fails++)); }
    grep -q 'no spec.md found' "$file" || { echo "  AC-15 missing spec-absent fallback string"; ((fails++)); }
    grep -q 'securitySeverity' "$file" || { echo "  AC-5 missing severity predicate"; ((fails++)); }
    grep -q 'mutation_caught' "$file" || { echo "  AC-5b missing test-deepener narrowed-remap predicate"; ((fails++)); }
    if [[ $fails -eq 0 ]]; then log_pass; else log_fail "$fails assertion(s) failed"; fi
}

test_finish_feature_under_600_lines() {
    log_test "finish-feature.md kept under 600 lines (Step 5b detail extracted)"
    local lines
    lines=$(wc -l < "${PROJECT_ROOT}/plugins/pd/commands/finish-feature.md")
    if [[ $lines -lt 600 ]]; then log_pass; else log_fail "finish-feature.md is $lines lines (>=600)"; fi
}

test_qa_gate_procedure_doc_exists() {
    log_test "qa-gate-procedure.md exists and references key FRs"
    local doc="${PROJECT_ROOT}/docs/dev_guides/qa-gate-procedure.md"
    if [[ ! -f "$doc" ]]; then log_fail "missing $doc"; return; fi
    grep -q 'FR-3\|FR-8\|FR-9' "$doc" || { log_fail "qa-gate-procedure.md missing key FR section markers"; return; }
    log_pass
}
```

**Note on grep count expansion (12, was 10 in design C4):** Plan-reviewer iter 1 warning 7 noted AC-5 requires the severity predicates in the command prose, not just the procedure doc. Added `securitySeverity` (AC-5) and `mutation_caught` (AC-5b) as greps 11+12. Updated design C4 reference in retro.md.

**T1 DoD (RED expected):**
- Functions defined
- Registration added
- `bash plugins/pd/hooks/tests/test-hooks.sh` exit non-zero (RED)
- Output contains `test_finish_feature_step_5b_present` FAIL with all 12 sub-assertions failed
- Output contains `test_finish_feature_under_600_lines` PASS (current is 508, < 600)
- Output contains `test_qa_gate_procedure_doc_exists` FAIL (file doesn't exist yet)
- Total `log_pass` count = `PRE_LOG_PASS_COUNT + 1` (only `test_finish_feature_under_600_lines` passes initially)

### T2 — Edit `finish-feature.md` (insert Step 5b — GREEN for test_finish_feature_step_5b_present)

**File:** `plugins/pd/commands/finish-feature.md`

**Old text** (lines 369-374, exact verbatim):
```
Fix these issues manually, then run /finish-feature again.
```

Do NOT proceed to Create PR or Merge & Release if validation is failing.

### Step 5a-bis: Security Review (CC Native)
```

**New text** (insert Step 5b between line 372 "Do NOT proceed..." and line 374 "### Step 5a-bis"):
```
Fix these issues manually, then run /finish-feature again.
```

Do NOT proceed to Create PR or Merge & Release if validation is failing.

### Step 5b: Pre-Release Adversarial QA Gate

> **YOLO exception:** HIGH findings always exit non-zero; gate never prompts; MED/LOW auto-file silently.

After Step 5a (validate.sh) passes, dispatch the 4 adversarial reviewer agents against the feature branch diff.

**In a single Claude message, dispatch all 4 reviewers in parallel using the Task tool. Do NOT dispatch sequentially.**

**Dispatch table:**

| # | subagent_type | model | Output |
|---|---|---|---|
| 1 | `pd:security-reviewer` | opus | JSON `{approved, issues[{severity, securitySeverity, location, ...}], summary}` |
| 2 | `pd:code-quality-reviewer` | sonnet | JSON `{approved, issues[{severity, location, ...}], summary}` |
| 3 | `pd:implementation-reviewer` | opus | JSON `{approved, issues[{severity, level, ...}], summary}` |
| 4 | `pd:test-deepener` | opus | **Step A** mode only — JSON `{gaps[{severity, mutation_caught, location, ...}], summary}` |

Each dispatch prompt includes: feature spec.md content (or fallback `no spec.md found — review for general defects against the diff; do not synthesize requirements`), diff via `git diff {pd_base_branch}...HEAD`, and an instruction to emit `location` as `file:line` for cross-confirmation.

**Severity rubric** (AC-5):
- HIGH: `severity == "blocker"` OR `securitySeverity in {"critical", "high"}`
- MED: `severity == "warning"` OR `securitySeverity == "medium"`
- LOW: `severity == "suggestion"` OR `securitySeverity == "low"`

**Test-deepener narrowed remap** (AC-5b): test-deepener gaps with severity HIGH remap to MED **only when** `mutation_caught == false` AND no other reviewer flagged the same location. Cross-confirmed gaps stay HIGH.

**Decision tree:**
- **HIGH count > 0** → block merge unless `qa-override.md` ≥ 50 chars (per-section trimmed-count)
- **MED findings** → auto-file to `docs/backlog.md` under `## From Feature {feature_id} Pre-Release QA Findings`
- **LOW findings** → append to `docs/features/{id}-{slug}/.qa-gate-low-findings.md` sidecar
- **Idempotency:** if `.qa-gate.json` exists with current HEAD SHA, skip dispatch and log to `.qa-gate.log`

**See `docs/dev_guides/qa-gate-procedure.md`** for full dispatch prompts, JSON parse contract (TD-8 python3 heredoc), severity bucketing two-phase logic (FR-5/AC-5b), per-feature backlog sectioning (TD-7), override path (FR-9/TD-3), incomplete-run handling (FR-10), YOLO surfacing (FR-11), and large-diff fallback (R-7).

### Step 5a-bis: Security Review (CC Native)
```

**T2 DoD:**
- `wc -l plugins/pd/commands/finish-feature.md` ≤ `PRE_LINES_FF + 50` AND `< 600`
- `test_finish_feature_step_5b_present` transitions FAIL → PASS (all 12 greps pass)
- `test_finish_feature_under_600_lines` still PASS

### T3 — Create `docs/dev_guides/qa-gate-procedure.md` (GREEN for test_qa_gate_procedure_doc_exists)

**File:** `docs/dev_guides/qa-gate-procedure.md` (NEW, ~180 lines)
**Action:** Create file with H2-headed sections (canonical form: `## §N — Title`).

**12 required sections:**
1. `## §1 — Dispatch prompt template (FR-3, I-5)` — full prompt body for each of 4 reviewers, includes spec-absent fallback string verbatim, diff range token `{pd_base_branch}...HEAD`, severity rubric reminder, location-format `file:line` directive.
2. `## §2 — test-deepener Step A invocation (FR-4)` — explicit "Run Step A (Outline Generation) ONLY. Do NOT write tests" directive; reference to `plugins/pd/agents/test-deepener.md` Step A.
3. `## §3 — JSON parse contract (FR-10, TD-8)` — full python3 -c heredoc verbatim from design.md TD-8 (must contain literal `import sys, json, re`).
4. `## §4 — Severity bucket two-phase (FR-5, AC-5b, I-6)` — Phase 1 collection, Phase 2 bucket() pseudocode, normalize_location() rule, cross_confirmed() predicate.
5. `## §5 — MED auto-file to backlog (FR-7a, AC-19, TD-7)` — per-feature section heading template `## From Feature {feature_id} Pre-Release QA Findings ({date})`; ID extraction algorithm `^- \*\*#[0-9]{5}\*\*` regex; sequential reservation for batch.
6. `## §6 — LOW auto-file to sidecar (FR-7a)` — `.qa-gate-low-findings.md` markdown format.
7. `## §7 — Idempotency cache (FR-8, TD-5)` — atomic-rename writes (tmp file + mv); corruption handling (treat as cache-miss); Step 5a→5b ordering dependency.
8. `## §8 — Override path (FR-9, TD-3)` — first-override frontmatter; Nth-override H2 sections; per-section trimmed-count bypass check (awk pipeline).
9. `## §9 — Incomplete-run policy (FR-10)` — block on parse-or-schema failure; emit INCOMPLETE message; exit non-zero.
10. `## §10 — YOLO surfacing (FR-11)` — stdout findings + non-zero exit; NO AskUserQuestion.
11. `## §11 — Large-diff fallback (R-7)` — >2000 LOC threshold; file-list-summary + per-file clarification; 10-min budget extension.
12. `## §12 — Override-storm warning (R-1)` — count `^## Override [0-9]+` headings; if ≥3, append `## Override-Storm Warning` H2 to retro.md.

**T3 DoD:**
- File exists at `docs/dev_guides/qa-gate-procedure.md`
- `grep -cE '^## §[0-9]+ — ' docs/dev_guides/qa-gate-procedure.md` returns ≥ 12
- `grep -q 'import sys, json, re' docs/dev_guides/qa-gate-procedure.md` exit 0
- `grep -q 'FR-3\|FR-8\|FR-9' docs/dev_guides/qa-gate-procedure.md` exit 0
- `test_qa_gate_procedure_doc_exists` transitions FAIL → PASS

### T4 — Edit `retrospecting/SKILL.md` (FR-7b sidecar fold)

**File:** `plugins/pd/skills/retrospecting/SKILL.md`

**Old text** (line 168, before Step 3 "Write retro.md"):
```
### Step 3: Write retro.md
```

**New text** (insert new Step 2c before Step 3):
```
### Step 2c: Fold Pre-Release QA Sidecars (FR-7b from feature 094)

If `{pd_artifacts_root}/features/{id}-{slug}/.qa-gate-low-findings.md` exists:
1. Read its content.
2. Append under `## Pre-release QA notes` H2 in the planned `retro.md` content (create section if absent), prefixed with sub-heading `### LOW findings`.
3. After successful append, `rm` the sidecar file.

If `{pd_artifacts_root}/features/{id}-{slug}/.qa-gate.log` exists:
1. Read its content (skip lines + count lines per AC-7/AC-17 patterns).
2. Append under `## Pre-release QA notes` H2 in `retro.md` (create section if absent), prefixed with sub-heading `### Audit log`.
3. After successful append, `rm` the sidecar file.

**Note:** Each sidecar may exist independently. A skip-only gate run produces only `.qa-gate.log`; a clean dispatch with no LOW findings also produces only `.qa-gate.log`. The fold step must handle each independently.

If neither sidecar exists: skip silently (no-op).

### Step 3: Write retro.md
```

**T4 DoD:**
- `grep -q 'qa-gate-low-findings\.md' plugins/pd/skills/retrospecting/SKILL.md` exit 0
- `grep -q 'qa-gate\.log' plugins/pd/skills/retrospecting/SKILL.md` exit 0
- `grep -q 'Pre-release QA notes' plugins/pd/skills/retrospecting/SKILL.md` exit 0
- `wc -l plugins/pd/skills/retrospecting/SKILL.md` = `PRE_LINES_RS + 15` (±5)

### T5 — Quality gates

```bash
./validate.sh                                    # exit 0
bash plugins/pd/hooks/tests/test-hooks.sh        # exit 0, +3 tests
```

**T5 DoD:**
- Both gates exit 0
- `bash plugins/pd/hooks/tests/test-hooks.sh 2>&1 | grep -c '  PASS'` = `PRE_LOG_PASS_COUNT + 3` (3 new tests pass)
- `validate.sh` warning count unchanged from baseline

### T6 — Two-phase dogfood self-test

**T6 needs the gate's prose to actually be in `finish-feature.md`. Therefore phase (a) is run AFTER T2 makes the prose live, but BEFORE the final commit.**

**Phase (a) — Self-dispatch via /pd:finish-feature:**

This is the canonical end-to-end test: run `/pd:finish-feature` against the feature 094 branch itself with `--dry-run-step-5b-only` semantics (i.e., halt before merge). Concrete steps:

1. Stage all uncommitted changes (T1–T4 work) so the gate sees the prose-only diff.
2. Manually invoke just the Step 5b dispatch logic by reading `finish-feature.md` Step 5b prose + the procedure doc — Claude executes the parallel 4-reviewer Task() block against `git diff develop...HEAD`.
3. Observe per-reviewer JSON outputs; bucket findings; verify:
   - **AC-5/5b:** Severity predicates resolve to expected buckets (manually trace one finding through the predicate).
   - **AC-6:** `.qa-gate.json` would be written on PASS — inspect format if written.
   - **AC-17:** `.qa-gate.log` `count:` lines emitted — inspect format.
   - **AC-10:** Simulate one reviewer error (e.g., remove its model frontmatter temporarily) and confirm INCOMPLETE block.
4. Document each AC observation in `docs/features/094-pre-release-qa-gate/retro.md` "Manual Verification" section.
5. **Note on limitation:** This dogfood pass exercises dispatch + bucket + parse logic on a prose-only feature. Cache write/read (FR-8), override flow (FR-9), and YOLO HIGH-stop (FR-11) are not exercised in this run — they validate on the FIRST subsequent feature whose `/pd:finish-feature` invocation hits the new gate. Document these as "AC-deferred-verification: feature 095 first-run" in retro.md.

**Phase (b) — Synthetic-HIGH injection (sanity check):**

1. Create scratch branch: `git checkout -b feature/094-dogfood-test`.
2. Inject TWO synthetic HIGH patterns (deterministic — require ≥1 of 2 detected to mitigate per-reviewer variance):
   - Pattern A (SQL injection / unbounded LIMIT): add a Python file with `cursor.execute(f"SELECT * FROM t LIMIT {user_input}")` (no validation).
   - Pattern B (shell injection): add `subprocess.Popen(f"echo {user_input}", shell=True)`.
3. Re-dispatch the 4 reviewers via Task() against this branch's diff.
4. Verify ≥1 reviewer flags HIGH on each pattern.
5. **Fallback:** If both patterns escape ALL 4 reviewers, file a HIGH backlog entry "(surfaced by feature:094 dogfood self-test)" against the gate itself, treat feature 094 as needing strengthening before merge.
6. Discard scratch branch: `git checkout feature/094-pre-release-qa-gate && git branch -D feature/094-dogfood-test`.

**Phase (c) — Cleanup before commit:**

1. Run `git status docs/features/094-pre-release-qa-gate/` — if any of `.qa-gate.json`, `.qa-gate.log`, `.qa-gate-low-findings.md`, `qa-override.md` appear (generated during T6(a)), `rm` them.
2. Verify no scratch-branch synthetic injection leaked back to feature 094 branch.
3. Add `.qa-gate.json`, `.qa-gate.log`, `.qa-gate-low-findings.md` to `.gitignore` at repo root (these are runtime state, never committed). `qa-override.md` is intentionally committed as audit trail per FR-9.

**T6 DoD:**
- All 3 phases documented in retro.md "Manual Verification" section
- `git status` clean of dogfood artifacts before final commit
- `.gitignore` updated with 3 new patterns

## AC Coverage Matrix (1-row-per-AC)

| AC | Summary | Verification | Step |
|----|---------|--------------|------|
| AC-1 | Step 5b heading present | `test_finish_feature_step_5b_present` grep #1 | T2 |
| AC-2 | All 4 reviewer agent names | `test_finish_feature_step_5b_present` greps #2-5 | T2 |
| AC-3 | Literal "dispatch all 4 reviewers in parallel" phrase | grep #9 | T2 |
| AC-4 | "Step A" token | grep #6 | T2 |
| AC-5 | Severity predicates inline | grep #11 (`securitySeverity`) | T2 |
| AC-5b | test-deepener narrowed-remap (mutation_caught + cross-confirm) | grep #12 (`mutation_caught`) | T2 |
| AC-6 | `.qa-gate.json` schema | Manual T6(a) inspection | T6 |
| AC-7 | Skip pattern in `.qa-gate.log` | Manual T6(a) inspection | T6 |
| AC-8 | qa-override trimmed-count ≥ 50 | Manual T6(a) | T6 |
| AC-9 | Override-N counting | Manual T6(a) (deferred — needs 2 HIGH events on same feature) | T6 |
| AC-10 | Incomplete-run = block | Manual T6(a) (simulate error) | T6 |
| AC-11 | YOLO surfacing | AC-deferred-verification: feature 095 first-run | T6/post |
| AC-12 | `.qa-gate-low-findings.md` reference | grep #8 | T2 |
| AC-13 | retrospecting fold | T4 grep + Manual on feature 095 | T4/post |
| AC-14 | 8 distinct test assertions | `test_finish_feature_step_5b_present` itself | T1 |
| AC-15 | Spec-absent fallback string | grep #10 | T2 |
| AC-16 | `{pd_base_branch}...HEAD` token | Manual T6(a) check on dispatch prose | T6 |
| AC-17 | Per-reviewer count pattern | Manual T6(a) `.qa-gate.log` inspection | T6 |
| AC-18 | <600 lines + procedure doc exists | `test_finish_feature_under_600_lines` + `test_qa_gate_procedure_doc_exists` | T1/T2/T3 |
| AC-19 | Backlog ID extraction + per-feature section | Manual on feature 095 first-run with MED finding | post |
| AC-20 | No new external deps | `validate.sh` | T5 |

**Auto-tested (10):** AC-1, AC-2, AC-3, AC-4, AC-5, AC-5b, AC-12, AC-15, AC-18, AC-20  
**Manual via T6 dogfood (6):** AC-6, AC-7, AC-8, AC-9, AC-10, AC-16, AC-17  
**AC-deferred-verification (post-merge / feature 095 first-run, 4):** AC-11, AC-13, AC-19, plus end-to-end coverage of AC-6/7/8/9/10/17. These are not "unverified" — they're verified by the gate's first real production use, which happens immediately on the next feature merge. retro.md captures this contingency.

The Manual Verification Gate (design.md) captures all manual + deferred ACs in retro.md as a checklist.

## Quality Gates (recap)

- `./validate.sh` exit 0 (no new errors; pre-existing warnings unchanged)
- `bash plugins/pd/hooks/tests/test-hooks.sh` exit 0; total = `PRE_LOG_PASS_COUNT + 3`
- All 21 ACs verified per matrix above (10 auto in CI; 7 manual in T6; 4 deferred to feature 095 first-run with explicit retro contingency)

## Dependencies

- `python3` (already required) — for TD-8 JSON parse heredoc
- `git`, `wc`, `grep`, `sed`, `awk` (POSIX) — already used by pd
- 4 existing reviewer agents (no new agents)
- Existing `pd:retrospecting` skill (extended, not replaced)

No new external dependencies. AC-20 verifiable via `validate.sh`.

## Risks Carried from Design

- **R-1 [HIGH]** Override normalization — partially mitigated; structural backstop deferred to Open Question 1
- **R-2..R-7** — all mitigated per design Risk section
- **Implementation-specific:** large diff text inlined into 4 reviewer prompts → R-7 file-list-summary fallback at >2000 LOC
- **Synthetic-HIGH escape (T6 phase b):** if both injected patterns escape all 4 reviewers, treat as HIGH against feature 094 itself; document fallback in T6 phase (b)

## Out of Scope (carried forward)

Same as PRD/spec/design. Notably: consensus weighting (Open Q 1), AC-12 retirement (Open Q 2), anti-pattern KB injection (Open Q 3), cross-feature interaction-bug detection (R-4).

## Notes — Direct-orchestrator vs taskification

Plan-reviewer iter 1 warning 6 surfaced this. Decision: **keep direct-orchestrator** (single atomic commit) for the following reasons:
- Total touch ~280 LOC across 4 files — at the ceiling but still surgical.
- All 4 file edits cross-reference each other (Step 5b references qa-gate-procedure.md; retrospecting consumes sidecars defined in qa-gate-procedure.md; test-hooks asserts both files; etc.). Atomic commit ensures no transient state where one artifact references another that doesn't exist yet.
- T2/T3/T4 *could* be parallelized via worktrees, but the wall-clock saving (~5-10 min) doesn't justify the merge-conflict complexity for this scope.

Alternative if the implementer prefers parallelization: T1 → fan out (T2 || T3 || T4) → T5 → T6 in 3 worktrees. Documented for completeness but not the chosen path.

## Review History

### Iteration 1 — plan-reviewer (opus, 2026-04-29)

**Findings:** 5 blockers + 5 warnings + 2 suggestions

**Corrections applied (this revision):**
- TDD order inverted — T1 now adds tests FIRST (RED), T2-T4 are GREEN. Reason: blocker 2.
- T1/T2/T4 — exact Old/New text quotes added (was placeholder paraphrase). Reason: blocker 1.
- T6 phase (a) — clarified to actually run /pd:finish-feature gate prose on real branch; documented AC-deferred-verification for ACs that can't be tested without a second feature. Reason: blocker 3.
- Stage 0 NEW — captures PRE_HEAD, PRE_LINES_FF, PRE_TEST_COUNT, PRE_LOG_PASS_COUNT before any edits; T2 DoD references PRE_LINES_FF + 50. Reason: blocker 4.
- Heading form — picked H2 (`## §N — Title`); updated DoD regex to `^## §[0-9]+ — `. Reason: blocker 5.
- T1 grep count expanded from 10 to 12 (added `securitySeverity` for AC-5 + `mutation_caught` for AC-5b — predicates must be in command prose per spec AC-5). Reason: warning 7.
- T4 — added Old text quote bracketing line 168; documented integration ordering after Step 2c new step. Reason: warning 8.
- T6 phase (b) — required two deterministic patterns + fallback if both escape (file HIGH against gate itself). Reason: warning 9.
- T1 — registration block now shows exact Old/New diff at lines 3411-3414. Reason: warning 10.
- AC Coverage Matrix — restructured to 1-row-per-AC with 21 distinct rows; auto/manual/deferred categorization explicit. Reason: suggestion 11.
- T6 phase (c) — added .gitignore + cleanup substep for dogfood-generated runtime files. Reason: suggestion 12.
- Direct-orchestrator vs taskification — kept direct-orchestrator with explicit justification (atomic commit cohesion); documented worktree alternative. Reason: warning 6.
