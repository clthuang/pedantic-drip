# Spec: Feature 094 — Pre-Release Adversarial QA Gate

## Status
- Phase: specify
- Created: 2026-04-29
- PRD: `docs/features/094-pre-release-qa-gate/prd.md`
- Source: backlog #00217
- Target: v4.17.0

## Overview

Insert a new **Step 5b** into `plugins/pd/commands/finish-feature.md` between Step 5a (`validate.sh`) and Step 5a-bis (`/security-review`) that dispatches the existing 4 adversarial reviewer agents (`pd:security-reviewer`, `pd:code-quality-reviewer`, `pd:implementation-reviewer`, `pd:test-deepener`) in one parallel `Task()` batch against the feature branch diff, applies a HIGH-blocks / MED-files / LOW-notes severity rubric, and is idempotent on re-run via a HEAD-SHA-keyed cache.

This closes the structural gap responsible for 4 consecutive post-release adversarial-QA residual rounds (091→24, 092→18, 093→27, sync-cache→4 findings) including 3 HIGH-severity production bugs that required hotfix releases.

## Acceptance Criteria (binary-verifiable)

- **AC-1** `plugins/pd/commands/finish-feature.md` contains a heading line matching `^##\s.*Step 5b.*Pre-Release Adversarial QA Gate` between the existing Step 5a end and Step 5a-bis start.
- **AC-2** Step 5b prose contains all 4 reviewer agent names: `pd:security-reviewer`, `pd:code-quality-reviewer`, `pd:implementation-reviewer`, `pd:test-deepener` — each with explicit `model:` line matching the agent's frontmatter (opus/sonnet/opus/opus respectively).
- **AC-3** Step 5b prose contains the literal phrase `dispatch all 4 reviewers in parallel` (no "or equivalent" — exact match required for binary verification via `grep -q`).
- **AC-4** Step 5b dispatches `pd:test-deepener` in **Step A mode only** — the dispatch prompt explicitly contains the literal token `Step A` and instructs the agent to return JSON outline only (no test-write).
- **AC-5** Severity bucket logic is implemented as explicit predicates in the command prose:
  - HIGH: `severity == "blocker" OR (securitySeverity in {"critical", "high"})`
  - MED: `severity == "warning" OR (securitySeverity == "medium")`
  - LOW: `severity == "suggestion" OR (securitySeverity == "low")`
- **AC-5b** test-deepener exception: command prose contains a literal clause documenting that test-deepener gaps are remapped HIGH→MED **only when** `mutation_caught == false` AND no other reviewer flagged the same `location`. Cross-confirmed gaps stay HIGH. Rationale text states: "uncaught mutation-resistance gaps are coverage-debt unless cross-confirmed."
- **AC-6** Idempotency cache file is named `.qa-gate.json`, lives in feature directory. Required fields verifiable via regex (Claude generates the JSON per FR-8 template, not deterministic shell):
  - `head_sha` matches `[0-9a-f]{40}`
  - `gate_passed_at` matches `\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z`
  - `summary` is an object with `high`, `med`, `low` integer fields
- **AC-7** On re-run with matching HEAD SHA, the gate skips dispatch and appends one line to `.qa-gate.log` (sidecar in feature dir) matching pattern `^skip: HEAD [0-9a-f]{40} at \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z` (audit log; folded into retro.md by retrospecting skill per FR-7b).
- **AC-8** `qa-override.md` requirement: gate accepts override only when file exists AND `wc -c < qa-override.md` ≥ 50.
- **AC-9** Override file format:
  - First override: gate writes top-level YAML frontmatter listing offending finding(s) + a `## Override 1 ({date})` H2 section with rationale comment placeholder. User fills the rationale below the comment (≥ 50 chars total file size).
  - Nth override (N ≥ 2): gate **does NOT modify the top-level frontmatter**. Gate appends a new H2 heading `## Override {N} ({date})` where N = `(max integer found in existing headings matching ^## Override (\d+)) + 1`; if no such headings exist, N = 1. Each H2 section contains its own inline findings list (markdown bullet list) + rationale comment placeholder.
- **AC-10** Incomplete-run policy: if any of the 4 dispatched reviewers fails the JSON parse + schema validation contract per FR-10, gate emits `INCOMPLETE: {n} of 4 reviewers failed: [{reviewer}: {reason}, ...]` and exits non-zero (treats as block, not pass).
- **AC-11** YOLO override scope:
  - HIGH findings: gate prints findings to stdout and exits the `finish-feature` command with non-zero status. Does NOT invoke `AskUserQuestion` (preserves YOLO non-interactive contract). User discovers the block via the failed `finish-feature` artifact / next CLI session.
  - MED findings: auto-file to backlog without prompt (per FR-7a).
  - LOW findings: auto-file to sidecar without prompt (per FR-7a).
- **AC-12** LOW findings sidecar file path: `docs/features/{id}-{slug}/.qa-gate-low-findings.md` (regex-asserted in test-hooks).
- **AC-13** `plugins/pd/skills/retrospecting/SKILL.md` updated: contains a step that reads `.qa-gate-low-findings.md` AND `.qa-gate.log` if present, appends contents under `## Pre-release QA notes` H2 in `retro.md`, and deletes both sidecars.
- **AC-14** Test-hooks integration test asserts 8 distinct assertions (1:1 with FR-12 grep block):
  1. Step 5b heading present
  2. `pd:security-reviewer` present
  3. `pd:code-quality-reviewer` present
  4. `pd:implementation-reviewer` present
  5. `pd:test-deepener` present
  6. `Step A` token present
  7. `.qa-gate.json` reference present
  8. `.qa-gate-low-findings.md` reference present
- **AC-15** Spec-absent fallback: when feature dir lacks `spec.md`, the dispatch prompts to `pd:implementation-reviewer` and `pd:test-deepener` contain the literal text `no spec.md found — review for general defects against the diff; do not synthesize requirements`.
- **AC-16** Diff range: the source file `plugins/pd/commands/finish-feature.md` contains the literal token `{pd_base_branch}...HEAD` (curly braces preserved). At runtime the pd config-injection mechanism substitutes `{pd_base_branch}` with the resolved branch before Claude reads the dispatch prose. Test-hooks grep targets the source file (un-substituted form).
- **AC-17** Per-run telemetry: gate appends one line per reviewer to `.qa-gate.log` (same sidecar as AC-7) matching pattern `^count: \[{reviewer-name}\]: HIGH=\d+ MED=\d+ LOW=\d+` (folded into retro.md by retrospecting skill per FR-7b — enables Open Question 1 false-block-rate measurement).
- **AC-18** Step 5b procedural detail is **always** extracted to `docs/dev_guides/qa-gate-procedure.md`. `finish-feature.md` keeps only: dispatch shape (FR-2 table), severity rubric (FR-5), high-level decision tree (HIGH→block / MED→file / LOW→sidecar), and a reference link to the procedure doc. Post-edit `wc -l plugins/pd/commands/finish-feature.md` < 600 (verified by test-hooks).
- **AC-19** MED auto-file to backlog: each MED finding produces one new entry in `docs/backlog.md` with marker `(surfaced by feature:{feature_id} pre-release QA)` where `{feature_id}` is the running feature's ID (parameterized, NOT hardcoded `094`). Entries are appended (not inserted), preserving chronological sectioning. ID extraction algorithm: scan entire `docs/backlog.md` with regex `^- \*\*#(\d{5})\*\*` (anchored to start-of-list-line), take `max + 1`; if no matches, start at `00001`. When multiple MEDs file in one run, IDs are reserved sequentially in the order the gate processes findings.
- **AC-20** No new external dependencies introduced — no new pip / brew / npm / etc. requirements; the gate is **prose interpreted by Claude at run-time**. ISO-8601 timestamps and YAML frontmatter are produced by Claude per the templates in FR-8 and FR-9. Test-hooks verifies presence/shape via regex (per AC-6 and AC-9), not deterministic byte-equality. Underlying tools used by Claude inside `Bash` calls: `git`, `wc`, `grep`, `sed` only — all already required by existing pd commands.

## Functional Requirements

### FR-1 — Step 5b heading + insertion point

**File:** `plugins/pd/commands/finish-feature.md`
**Insertion:** between current line 373 (Step 5a closing) and current line 374 (Step 5a-bis opening)
**Heading:** `## Step 5b: Pre-Release Adversarial QA Gate`
**Body:** sub-steps documented per FR-2..FR-12 below.

### FR-2 — Parallel 4-reviewer dispatch

The Step 5b prose must contain the literal phrase `dispatch all 4 reviewers in parallel` (per AC-3 — anti-pattern guard against sequential dispatch). Required full instruction text: "In a single Claude message, dispatch all 4 reviewers in parallel using the Task tool. Do NOT dispatch sequentially."

Dispatch list:

| # | subagent_type | model | Output shape |
|---|---|---|---|
| 1 | `pd:security-reviewer` | opus | JSON `{approved, issues[{severity, securitySeverity, location, description, suggestion}], summary}` |
| 2 | `pd:code-quality-reviewer` | sonnet | JSON `{approved, strengths[], issues[{severity, location, description, suggestion}], summary}` |
| 3 | `pd:implementation-reviewer` | opus | JSON `{approved, levels{}, issues[{severity, level, category, description, location, suggestion}], summary}` |
| 4 | `pd:test-deepener` | opus | JSON gap outlines (Step A mode) — `{gaps[{severity, description, location, mutation_caught, suggested_test}], summary}` |

### FR-3 — Reviewer dispatch prompts

Each prompt must include:
- Feature ID and slug (for context)
- Spec.md content if `docs/features/{id}-{slug}/spec.md` exists; otherwise the literal fallback string from AC-15
- Diff: `git diff {pd_base_branch}...HEAD` output
- Severity rubric reminder (HIGH/MED/LOW) so reviewer assigns severity consistently
- Iteration context: this is a pre-release gate, not the in-implement review

### FR-4 — test-deepener Step A invocation

The dispatch prompt to `pd:test-deepener` must:
1. Open with the literal directive: "Run **Step A** (Outline Generation) ONLY. Do NOT write tests."
2. Reference the agent's own spec at `plugins/pd/agents/test-deepener.md` Step A.
3. Require JSON output: `{gaps[{severity, description, location, mutation_caught, suggested_test}], summary}`.

### FR-5 — Severity bucket logic

Bucket findings into HIGH / MED / LOW per AC-5 predicates. Findings without severity field are bucketed MED with a warning note.

**test-deepener narrowed remap (AC-5b):** test-deepener gaps remap HIGH→MED **only when both** (a) `mutation_caught == false` AND (b) no other reviewer (security/code-quality/implementation) flagged the same `location`. If either condition fails, the gap stays HIGH. Rationale: uncaught mutation-resistance gaps are coverage-debt; cross-confirmed gaps are real production-bug-class risks. This is the *only* per-reviewer remap.

### FR-6 — HIGH = block

If aggregated `HIGH > 0` AND no `qa-override.md` ≥ 50 chars:
- Emit findings list (one block per HIGH, with reviewer name, location, description, suggested_fix)
- Print: "QA gate FAILED — {h} HIGH, {m} MED, {l} LOW. Fix HIGHs and re-run, or write rationale to `qa-override.md` (≥50 chars)."
- Exit non-zero from `finish-feature` (block merge)

### FR-7 — MED + LOW auto-file (split FR-7a / FR-7b)

**FR-7a — gate writes:**
- For each MED finding: append to `docs/backlog.md` per AC-19. Algorithm:
  1. Scan entire `docs/backlog.md` with regex `^- \*\*#(\d{5})\*\*` (anchored).
  2. Compute `next_id = max(matched_ids) + 1`; if no matches, start at `00001`.
  3. When N MEDs file in one run, reserve IDs sequentially (`next_id`, `next_id+1`, ..., `next_id+N-1`) in the order the gate processes findings.
  4. Template (parameterized — `{feature_id}` is the running feature's ID, NOT hardcoded):
     ```markdown
     - **#{NNNNN}** [{MED|MED-quality|MED-security}] {description}. (surfaced by feature:{feature_id} pre-release QA)
     ```
- For each LOW finding: append to `docs/features/{id}-{slug}/.qa-gate-low-findings.md` (create if absent) with format:
  ```markdown
  ### LOW: {short title}
  - Reviewer: {agent-name}
  - Location: {file:line}
  - Description: {description}
  - Suggested fix: {suggestion}
  ```
- For audit + telemetry (AC-7, AC-17): append to `docs/features/{id}-{slug}/.qa-gate.log` (create if absent):
  - On skip: one `skip:` line per AC-7 pattern.
  - On full dispatch: one `count:` line per reviewer per AC-17 pattern.

**FR-7b — retrospecting skill update:**

Modify `plugins/pd/skills/retrospecting/SKILL.md` to add a step (anywhere before retro.md final write):

1. For each sidecar in `{feature_dir}/`: `.qa-gate-low-findings.md` and `.qa-gate.log`:
   - If exists: read content.
   - Append under `## Pre-release QA notes` H2 in `retro.md` (create section if absent). For `.qa-gate.log`, prefix entries with sub-heading `### Audit log`. For `.qa-gate-low-findings.md`, prefix with sub-heading `### LOW findings`.
   - `rm` the sidecar after successful fold.
2. If neither sidecar exists: skip silently (no-op).

### FR-8 — Idempotency via HEAD-SHA cache

**File:** `docs/features/{id}-{slug}/.qa-gate.json`

**Schema:**
```json
{
  "head_sha": "{40-char hex}",
  "gate_passed_at": "{ISO-8601 Z}",
  "summary": {"high": 0, "med": N, "low": N}
}
```

**Logic:**
1. Compute current HEAD SHA: `git rev-parse HEAD`.
2. If `.qa-gate.json` exists AND its `head_sha` matches current: SKIP dispatch, append `skip:` line to `.qa-gate.log` (per AC-7), proceed to Step 5a-bis.
3. Cache miss (HEAD differs OR file absent): dispatch reviewers. **Do NOT delete the existing `.qa-gate.json` yet.** Only on PASS, atomically overwrite with new `head_sha` + `gate_passed_at` + `summary`. On INCOMPLETE or HIGH-block, leave previous cache untouched (a re-run on a subsequent fix-commit will simply mismatch SHA and re-dispatch).
4. Atomic write: write to `.qa-gate.json.tmp` then `mv` to `.qa-gate.json` (POSIX atomic-rename).

### FR-9 — Override path

**File:** `docs/features/{id}-{slug}/qa-override.md`

**Logic:**

**First override** (file does not exist):
1. On HIGH-block, gate creates `qa-override.md` with top-level YAML frontmatter listing the offending finding(s) + an `## Override 1 ({date})` H2 section with rationale comment placeholder:
   ```markdown
   ---
   gate_run_at: {ISO}
   findings:
     - reviewer: {name}
       severity: HIGH
       location: {file:line}
       description: {short}
   ---

   ## Override 1 ({date})

   <!-- User: write your rationale here (≥50 chars). Why is this finding a false positive or acceptable risk? -->
   ```
2. User fills in rationale below the comment.
3. Bypass check: file exists AND `wc -c < qa-override.md` ≥ 50 → skip dispatch.

**Nth override** (file already exists, gate fires again on different findings):
1. Gate **does NOT modify the top-level frontmatter** (it preserves the first invocation's record).
2. Compute N: `(max integer found in existing headings matching ^## Override (\d+)) + 1`; if none, N = 1.
3. Append a new H2 section `## Override {N} ({date})` with its own inline findings list (markdown bullets) followed by a fresh rationale comment placeholder:
   ```markdown

   ## Override {N} ({date})

   Findings this run:
   - reviewer: {name}, severity: HIGH, location: {file:line}, description: {short}

   <!-- User: write your rationale here (≥50 chars). -->
   ```
4. User fills in rationale. Bypass check (same as first override): `wc -c < qa-override.md` ≥ 50 → skip dispatch. Git history is the audit log of all override invocations.

### FR-10 — Incomplete-run = block

**JSON parse + schema validation contract:**
1. **Extract:** From each reviewer's Task() output, extract the first ```` ```json ... ``` ```` fenced block. If absent, attempt to find the first balanced `{ ... }` block that parses with `json.loads`.
2. **Schema validate** against the per-reviewer required fields from FR-2 table:
   - security-reviewer / code-quality-reviewer / implementation-reviewer: `{approved: bool, issues: list, summary: string}`
   - test-deepener: `{gaps: list, summary: string}`
3. **INCOMPLETE iff** any of: extraction fails, JSON does not parse, OR schema validation fails on a required field.

**On INCOMPLETE:**
- Print: `QA gate INCOMPLETE: {n} of 4 reviewers failed: [{reviewer}: {reason}, ...]. Re-run or override via qa-override.md.`
- Exit non-zero (block merge — never silent-pass).

### FR-11 — YOLO override scope

In YOLO mode (`yolo_mode: true`):
- **HIGH findings:** gate prints findings to stdout and exits the `finish-feature` command with non-zero status. **Does NOT invoke `AskUserQuestion`** (preserves YOLO non-interactive contract). The user discovers the block via the failed `finish-feature` artifact / next CLI session.
- **MED findings:** auto-file to backlog without prompt (per FR-7a).
- **LOW findings:** auto-file to sidecar without prompt (per FR-7a).

This MUST be documented at the top of Step 5b prose with the comment `# YOLO exception: HIGH findings always exit non-zero; gate never prompts; MED/LOW auto-file silently.`

### FR-12 — Test-hooks anti-drift assertion

Add to `plugins/pd/hooks/tests/test-hooks.sh` a new function `test_finish_feature_step_5b_present` with **8 distinct grep assertions** (1:1 with AC-14):

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
    if [[ $fails -eq 0 ]]; then log_pass; else log_fail "$fails assertion(s) failed"; fi
}

# Also: verify post-edit file size constraint per AC-18
test_finish_feature_under_600_lines() {
    log_test "finish-feature.md kept under 600 lines (Step 5b detail extracted)"
    local lines
    lines=$(wc -l < "${PROJECT_ROOT}/plugins/pd/commands/finish-feature.md")
    if [[ $lines -lt 600 ]]; then log_pass; else log_fail "finish-feature.md is $lines lines (>=600)"; fi
}
```

Register both in test runner section. Both must pass before merge.

## Non-Functional Requirements

- **NFR-1** Wall-clock target: ≤5 min for diffs ≤500 LOC. Above that, gate emits warning `large diff (LOC=N) — coverage confidence reduced` but proceeds.
- **NFR-2** No new external dependencies (pip/brew/npm). Uses existing reviewer agents + bash + git.
- **NFR-3** All `subagent_type` references include matching `model:` line per CLAUDE.md "Agent model tiers" guideline.
- **NFR-4** Step 5b procedural detail is **always** extracted to `docs/dev_guides/qa-gate-procedure.md` (no conditional). Post-edit `wc -l plugins/pd/commands/finish-feature.md` MUST be < 600 (asserted by `test_finish_feature_under_600_lines` in FR-12). Inline content kept in `finish-feature.md`: dispatch shape (FR-2 table), severity rubric (FR-5), high-level decision tree (HIGH→block / MED→file / LOW→sidecar), reference link to procedure doc.

## Edge Cases (mirror PRD)

| Scenario | Expected | Verified by |
|----------|----------|-------------|
| Reviewer agent errors / times out | block (incomplete) | AC-10, FR-10 |
| Diff > 1000 LOC | warn, proceed | NFR-1 |
| Re-run on same HEAD with prior pass | skip, log to retro | AC-7, FR-8 |
| Re-run after force-push | recompute SHA, re-dispatch | FR-8 step 1 |
| No spec.md (direct-create feature) | use fallback prompt string | AC-15, FR-3 |
| YOLO + HIGH | stop YOLO, surface findings | AC-11, FR-11 |
| YOLO + only MED/LOW | auto-file, proceed | AC-11, FR-11 |
| Single-reviewer HIGH while others LOW | block (no consensus weighting in v1) | AC-5, FR-6 (revisit per Open Question 1) |
| `qa-override.md` exists but <50 chars | reject override, treat as block | AC-8, FR-9 |

## Out of Scope (mirror PRD)

- Adding new reviewer agents (5th/6th)
- Replacing `/security-review`
- Modifying existing reviewer agent prompts
- Cross-feature interaction-bug detection (diff scope only)
- Anti-pattern KB injection into reviewer prompts (future)
- Consensus weighting (≥2 of 4 must agree on HIGH) — deferred per Open Question 1
- Reviewer feedback loop (gate findings → KB) — deferred

## Implementation Notes

- **Estimated touch (revised after spec-reviewer feedback — original 80-line estimate was unrealistic for 11 sub-pieces):**
  - `plugins/pd/commands/finish-feature.md`: +30–50 lines (dispatch shape + severity rubric + decision tree + reference to procedure doc)
  - `docs/dev_guides/qa-gate-procedure.md`: NEW, 150–200 lines (FR-3..FR-11 procedural detail)
  - `plugins/pd/skills/retrospecting/SKILL.md`: +15 lines (FR-7b sidecar fold step)
  - `plugins/pd/hooks/tests/test-hooks.sh`: +30 lines (FR-12 + AC-18 size check)
- **Always extract** Step 5b procedural detail to `qa-gate-procedure.md` (per AC-18) — this removes NFR-4's conditional branch and is the cleaner option per spec-reviewer recommendation.
- The gate is **prose interpreted by Claude at run-time**. ISO-8601 timestamps and YAML frontmatter are produced by Claude per templates in FR-8 and FR-9. Tests verify presence/shape via regex, not deterministic byte-equality.
- No production Python paths change. Backwards compatibility: features already merged remain unaffected (gate only fires on `/pd:finish-feature` invocations going forward).

## Review History

### Iteration 1 — spec-reviewer (opus, 2026-04-29)

**Findings:** 4 blockers + 8 warnings + 3 suggestions

**Corrections applied:**
- AC-3 — dropped "or equivalent"; required exact literal phrase `dispatch all 4 reviewers in parallel`. Reason: testability blocker / warning 6.
- AC-5b NEW — narrowed test-deepener HIGH→MED remap to (a) `mutation_caught == false` AND (b) no other reviewer flagged same location; cross-confirmed gaps stay HIGH. Reason: warning 5.
- AC-6, AC-20 — clarified runtime model: gate is prose interpreted by Claude; tests verify regex shape, not byte equality. Reason: warning 9.
- AC-7, AC-17 — moved skip-audit + per-reviewer telemetry from `retro.md` to `.qa-gate.log` sidecar (mirroring LOWs sidecar pattern). Avoids retro.md-may-not-exist ambiguity. Reason: blocker 3.
- AC-9 / FR-9 — specified Override-N counting algorithm (max+1 from `^## Override (\d+)`); first-vs-Nth override semantics; preserved top-level frontmatter; per-section findings list for Nth. Reason: blocker 1 + suggestion 15.
- AC-10 / FR-10 — specified JSON parse + schema validation contract (extract fenced `​```json…```​` block, fall back to balanced `{…}`, schema-validate against per-reviewer required fields). Reason: warning 7.
- AC-11 / FR-11 — specified YOLO surfacing: stdout + non-zero exit, NO `AskUserQuestion` (preserves YOLO non-interactive contract). Reason: warning 12.
- AC-13, FR-7b — extended retrospecting fold step to also consume `.qa-gate.log` (with `### Audit log` sub-heading). Reason: cascading from blocker 3 fix.
- AC-14 / FR-12 — restated AC-14 as 8 enumerated assertions matching FR-12's 8 grep calls 1:1; added separate `test_finish_feature_under_600_lines` for AC-18. Reason: warning 11.
- AC-16 — clarified source-file targeting and config-injection substitution timing. Reason: suggestion 14.
- AC-18, NFR-4 — switched to **unconditional** extraction of Step 5b detail to `qa-gate-procedure.md`; AC-18 now requires `< 600` lines as a hard test. Reason: blocker 4 (line-budget inconsistency).
- AC-19, FR-7a — parameterized `{feature_id}` (no longer hardcoded `094`); specified ID extraction algorithm (regex `^- \*\*#(\d{5})\*\*`, take max+1, sequential reservation for multi-MED runs). Reason: blocker 2 + warning 10.
- FR-8 — specified atomic-rename write semantics + leave-stale-cache-untouched on INCOMPLETE/HIGH-block. Reason: warning 8.
- Implementation Notes — revised line estimates (30–50 / 150–200 / 15 / 30) per spec-reviewer's "implausibly tight" critique. Reason: blocker 4.
- Definition of Done — strengthened dogfood self-test to require synthetic-HIGH injection. Reason: suggestion 13.

## Definition of Done

- [ ] All 21 ACs (AC-1..AC-20 + AC-5b) pass binary verification
- [ ] All 12 FRs implemented (FR-7 split as FR-7a + FR-7b)
- [ ] All 4 NFRs met
- [ ] `validate.sh` exit 0
- [ ] `bash plugins/pd/hooks/tests/test-hooks.sh` exit 0 with both new tests (`test_finish_feature_step_5b_present` + `test_finish_feature_under_600_lines`) passing
- [ ] **Strengthened dogfood self-test:** dispatch the new gate against this feature's own diff (prose-only). Manually inject ONE synthetic HIGH-equivalent finding (e.g., a fake unbounded-LIMIT pattern in a code-block comment) into a sample file and confirm at least one reviewer flags it. Remove the synthetic injection before merge. The vacuous "zero findings on prose-only diff" pass is NOT sufficient evidence the dispatch+severity path works.
