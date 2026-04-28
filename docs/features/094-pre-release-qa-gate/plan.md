# Plan: Feature 094 — Pre-Release Adversarial QA Gate

## Status
- Created: 2026-04-29
- Phase: create-plan
- Upstream: design.md (7 TDs + C1..C5 + I-1..I-6 + R-1..R-7); spec.md (21 ACs + 12 FRs)

## Architecture Summary

One feature, four files touched (one new), one atomic commit. The gate is **prose interpreted by Claude at run-time** in `finish-feature.md` + extracted procedure doc; the only executable code is bash inside test-hooks assertions and the dispatch-time `python3 -c` JSON parse helper (TD-8) inlined in the procedure doc.

```
plugins/pd/commands/finish-feature.md           [edit, ~+50 lines]
docs/dev_guides/qa-gate-procedure.md            [new, ~180 lines]
plugins/pd/skills/retrospecting/SKILL.md        [edit, ~+15 lines]
plugins/pd/hooks/tests/test-hooks.sh            [edit, ~+35 lines]
```

## Implementation Order

Sequential, no parallelism — single-thread for atomicity. Direct-orchestrator (per 091/092/093 template).

### Step 1 — Edit `plugins/pd/commands/finish-feature.md` (insert Step 5b)

**Old text** (locate exactly between current Step 5a end and Step 5a-bis start):
```
{end of Step 5a — validate.sh discovery loop ends with "If max attempts hit..."}
```
becomes:
```
{Step 5a end content unchanged}

## Step 5b: Pre-Release Adversarial QA Gate

# YOLO exception: HIGH findings always exit non-zero; gate never prompts; MED/LOW auto-file silently.

[Inline content per design C1: dispatch table (FR-2 4-row), severity rubric (AC-5 + AC-5b),
 decision tree (HIGH→block / MED→file / LOW→sidecar), reference link to procedure doc.]

In a single Claude message, **dispatch all 4 reviewers in parallel** using the Task tool.
Do NOT dispatch sequentially. See `docs/dev_guides/qa-gate-procedure.md` for full dispatch
prompts, JSON parse contract, and severity bucketing logic.

[... see Task T1 for full Step 5b inline content ...]

## Step 5a-bis: Security Review
{Step 5a-bis content unchanged}
```

**DoD** (binary):
- `grep -qE '^##\s.*Step 5b.*Pre-Release Adversarial QA Gate' plugins/pd/commands/finish-feature.md` returns exit 0 (AC-1)
- `grep -q 'dispatch all 4 reviewers in parallel' plugins/pd/commands/finish-feature.md` exit 0 (AC-3 + design C4)
- All 4 reviewer agent names present (AC-2, 4 greps)
- `Step A` token present (AC-4)
- `.qa-gate.json` and `.qa-gate-low-findings.md` referenced (AC-12, AC-14.7-8)
- `no spec.md found` literal present (AC-15 + design C4)
- `wc -l plugins/pd/commands/finish-feature.md` < 600 (AC-18)

### Step 2 — Create `docs/dev_guides/qa-gate-procedure.md` (NEW)

**Action:** Create new file with sections corresponding to design FR-3..FR-11. Each section explicit:

- **§1 Dispatch prompt template** (FR-3 + I-5): the 4-reviewer prompt body including spec.md path, fallback string, diff range, severity rubric reminder, output schema instruction. Includes the `file:line` location-format directive (per design I-6 addendum).
- **§2 test-deepener Step A invocation** (FR-4): the Step-A-only directive with explicit "Do NOT write tests" instruction.
- **§3 JSON parse contract** (FR-10 + TD-8): full python3 -c heredoc with stdlib-only json+re extraction + per-reviewer schema validation.
- **§4 Severity bucket two-phase** (FR-5 + AC-5b + I-6): collection phase + bucket() pseudocode + normalize_location() rule + cross_confirmed() predicate.
- **§5 MED auto-file to backlog** (FR-7a + AC-19 + TD-7): per-feature section heading + ID extraction algorithm + sequential reservation.
- **§6 LOW auto-file to sidecar** (FR-7a): `.qa-gate-low-findings.md` format.
- **§7 Idempotency cache** (FR-8 + TD-5): atomic-rename writes + corruption handling + Step 5a→5b ordering.
- **§8 Override path** (FR-9 + TD-3): first-override frontmatter + Nth-override H2 sections + per-section trimmed-count bypass check.
- **§9 Incomplete-run policy** (FR-10): block on any reviewer parse-or-schema failure.
- **§10 YOLO surfacing** (FR-11): stdout + non-zero exit, no AskUserQuestion.
- **§11 Large-diff fallback** (R-7): >2000 LOC threshold + file-list-summary mitigation + 10-min budget.
- **§12 R-1 override-storm warning** (design R-1): if `^## Override [0-9]+` count ≥ 3 in qa-override.md, append `## Override-Storm Warning` H2 to retro.md.

**DoD** (binary):
- File exists at `docs/dev_guides/qa-gate-procedure.md`
- `grep -q 'FR-3\|FR-8\|FR-9' docs/dev_guides/qa-gate-procedure.md` exit 0 (AC-18 + design suggestion 1)
- File contains all 12 section headings (`grep -cE '^##\s§[0-9]+' >= 12`)
- File contains TD-8 python3 heredoc snippet (`grep -q 'import sys, json, re'`)

### Step 3 — Edit `plugins/pd/skills/retrospecting/SKILL.md` (FR-7b)

**Action:** Add a step (anywhere before retro.md final write) that:
1. Checks for `{feature_dir}/.qa-gate-low-findings.md` and `{feature_dir}/.qa-gate.log` independently.
2. For each present sidecar: read content, append under `## Pre-release QA notes` H2 in retro.md (create section if absent), with sub-heading `### LOW findings` for the .md file and `### Audit log` for the .log file.
3. Delete each consumed sidecar (`rm` after fold).
4. If neither present: skip silently (no-op).

Per design C3: ~15 lines added.

**DoD** (binary):
- `grep -q 'qa-gate-low-findings\.md' plugins/pd/skills/retrospecting/SKILL.md` exit 0
- `grep -q 'qa-gate\.log' plugins/pd/skills/retrospecting/SKILL.md` exit 0
- `grep -q 'Pre-release QA notes' plugins/pd/skills/retrospecting/SKILL.md` exit 0

### Step 4 — Edit `plugins/pd/hooks/tests/test-hooks.sh` (FR-12 + AC-18 + design C4)

**Action:** Add 3 new test functions (per design C4) and register them in the test runner section.

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

Register all three in the test runner section (likely near other `test_finish_feature_*` calls).

**DoD** (binary):
- `bash plugins/pd/hooks/tests/test-hooks.sh` exit 0
- All 3 new tests appear in the output (PASS lines)
- Total test count went up by exactly 3

### Step 5 — Quality gates

**Run in order:**
1. `./validate.sh` → exit 0
2. `bash plugins/pd/hooks/tests/test-hooks.sh` → exit 0, all 3 new tests pass

**DoD:** Both gates green; total test count = baseline + 3.

### Step 6 — Two-phase dogfood self-test (DoD-strengthening)

**Phase (a) — self-dispatch:**
1. Stage all changes from Steps 1-4.
2. Manually invoke the gate procedure (NOT via `/pd:finish-feature` since we want to dogfood without committing). Run:
   - `git diff --stat develop...HEAD` to confirm diff exists.
   - For each of 4 reviewers, dispatch via Task tool against the staged diff.
   - Verify all 4 return JSON; bucket findings; verify gate would have NOT blocked (or surfaces only test-feature self-references that are remapped to MED/LOW).
3. Document outcome in retro.md "Manual Verification" section.

**Phase (b) — synthetic-HIGH injection (sanity check):**
1. Create scratch branch `feature/094-pre-release-qa-gate-dogfood-test` from current HEAD.
2. Inject a HIGH-equivalent into a Python file (e.g., add `LIMIT -1` SQL query or `subprocess.Popen(shell=True, f"...{user_input}")` pattern).
3. Re-dispatch 4 reviewers; verify at least one flags HIGH.
4. Discard the scratch branch (`git branch -D`).

**Phase (c) — cleanup:**
- Verify no synthetic injection leaked back to `feature/094-pre-release-qa-gate`.

**DoD:** All 3 phases documented in retro.md before merge.

## AC Coverage Matrix

| AC | Tested by | Step | Notes |
|----|-----------|------|-------|
| AC-1, AC-2, AC-4, AC-12, AC-14, AC-3, AC-15 | `test_finish_feature_step_5b_present` (10 greps) | T4 | Auto |
| AC-5 | Manual review of severity prose in §4 of procedure doc | T2 | Semantic |
| AC-5b | Manual + §4 algorithm review | T2 | Semantic |
| AC-6, AC-7, AC-17 | Regex shape verified in dogfood T6(a) | T2/T6 | Manual |
| AC-8, AC-9 | Manual: T6(a) override-flow + per-section bypass test | T2/T6 | Manual |
| AC-10 | Manual: simulate reviewer error in T6 | T6 | Manual |
| AC-11 | Manual: trigger HIGH in YOLO during T6 | T6 | Manual |
| AC-13 | Manual: place sidecar, run /pd:retrospect | T3/T6 | Manual |
| AC-16 | Source-file grep included in T4 (`{pd_base_branch}` substring) | T4 | Auto |
| AC-18 | `test_finish_feature_under_600_lines` + `test_qa_gate_procedure_doc_exists` | T4 | Auto |
| AC-19 | Manual: trigger MED, verify max+1 ID + section heading | T6 | Manual |
| AC-20 | `validate.sh` (no new pip/brew/npm files) | T5 | Auto |

**Auto-tested:** AC-1, AC-2, AC-3, AC-4, AC-12, AC-14, AC-15, AC-16, AC-18, AC-20 (10 ACs)  
**Manual via dogfood:** AC-5, AC-5b, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-13, AC-17, AC-19 (11 ACs)

The Manual Verification Gate (design.md) captures the manual ACs in retro.md.

## Quality Gates

- `./validate.sh` exit 0 (no new errors; pre-existing warnings unchanged)
- `bash plugins/pd/hooks/tests/test-hooks.sh` exit 0; total = baseline + 3
- All 21 ACs verified (10 auto + 11 manual via dogfood T6)

## Dependencies

- `python3` (already required) — for TD-8 JSON parse heredoc
- `git`, `wc`, `grep`, `sed`, `awk` (POSIX) — already used by pd
- 4 existing reviewer agents (no new agents)
- Existing `pd:retrospecting` skill (extended, not replaced)

No new external dependencies. AC-20 verifiable via `validate.sh`.

## Risks Carried from Design

- **R-1 [HIGH]** Override normalization — partially mitigated; structural backstop deferred to Open Question 1
- **R-2..R-7** — all mitigated per design Risk section
- Implementation-specific risk: large diff text inlined into 4 reviewer prompts → R-7 file-list-summary fallback at >2000 LOC

## Out of Scope (carried forward)

Same as PRD/spec/design. Notably: consensus weighting (Open Q 1), AC-12 retirement (Open Q 2), anti-pattern KB injection (Open Q 3), cross-feature interaction-bug detection (R-4).
