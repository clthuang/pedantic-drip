---
description: Complete a feature - merge, run retro, cleanup branch
argument-hint: [feature-id]
---

# /pd:finish-feature Command

Complete a feature and clean up.

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)
- `{pd_base_branch}` — base branch for merges (default: `main`)
- `{pd_release_script}` — path to release script (empty if not configured)

## YOLO Mode Overrides

If `[YOLO_MODE]` is active:
- Step 2a (tasks incomplete) → auto "Continue anyway"
- Step 2b (scaffold gate) → auto-select Skip (skip tier scaffolding, still run README/CHANGELOG writer)
- Step 2b (researcher no_updates_needed + empty affected_tiers) → auto-select Skip
- Step 2b (docs updates found) → proceed with writer dispatches (no prompt needed)
- Step 4 (completion decision) → auto "Merge & Release (Recommended)" (or "Merge (Recommended)" if `{pd_release_script}` is not configured)
- **Git merge failure:** STOP and report. Do NOT attempt to resolve merge conflicts
  autonomously. Output: "YOLO MODE STOPPED: Merge conflict on {pd_base_branch}. Resolve manually,
  then run /secretary continue"

## Determine Feature

Same logic as /pd:show-status command.

---

## Step 1: Auto-Commit (with Branch/Step Checks)

### Steps 1a-1c: Branch Check, Partial Recovery, Mark Started

Follow `validateAndSetup("finish")` from the **workflow-transitions** skill (skip transition validation since finish has no hard prerequisites).

### Step 1d: Commit and Push

1. Check for uncommitted changes via `git status --short`
2. If uncommitted changes found:
   - `git add -A && git commit -m "wip: uncommitted changes before finish"`
   - `git push`
   - On push failure: Show error and STOP - user must resolve manually
3. If no uncommitted changes: Continue

---

## Step 2: Pre-Completion Reviews

### Step 2a: Check Tasks Completion

If `tasks.md` exists, check for incomplete tasks (unchecked `- [ ]` items).

If incomplete tasks found:

```
AskUserQuestion:
  questions: [{
    "question": "{n} tasks still incomplete. How to proceed?",
    "header": "Tasks",
    "options": [
      {"label": "Continue anyway", "description": "Proceed despite incomplete tasks"},
      {"label": "Run /pd:implement", "description": "Execute implementation once more"},
      {"label": "Run /pd:implement until done", "description": "Loop until all tasks complete"}
    ],
    "multiSelect": false
  }]
```

If "Run /pd:implement": Execute `/pd:implement`, then return to Step 2.
If "Run /pd:implement until done": Loop `/pd:implement` until no incomplete tasks, then continue.

### Step 2b: Documentation Update (Enriched)

#### Mode Resolution

<!-- SYNC: tier-resolution -->
1. Parse `pd_doc_tiers` from session context — split on comma, trim whitespace, filter to recognized values (`user-guide`, `dev-guide`, `technical`). If `pd_doc_tiers` is not set or empty, default to all three tiers.
2. For each recognized tier, check if `docs/{tier}/` exists (relative to project root).
3. If any enabled tier directory is missing → `mode = scaffold`. If all enabled tier directories exist → `mode = incremental`.

<!-- SYNC: enriched-doc-dispatch -->
#### Doc-Schema Resolution

4. Resolve doc-schema content: Glob `~/.claude/plugins/cache/*/pd*/*/references/doc-schema.md` — use first match. Fallback (dev workspace): `plugins/pd/references/doc-schema.md`.
5. Read the resolved file content, store as `{doc_schema_content}`.
6. Replace all occurrences of `{pd_artifacts_root}` in `{doc_schema_content}` with the actual session value.

#### Scaffold UX Gate (scaffold mode only)

If `mode = scaffold`:

```
AskUserQuestion:
  questions: [{
    "question": "Documentation scaffold needed — some tier directories are missing. How to proceed?",
    "header": "Documentation Scaffold",
    "options": [
      {"label": "Skip", "description": "Skip documentation scaffolding for now"},
      {"label": "Scaffold", "description": "Create missing tier directories and seed files"},
      {"label": "Defer", "description": "Skip scaffolding — handle later"}
    ],
    "multiSelect": false
  }]
```

If "Skip" or "Defer": Skip to README/CHANGELOG Writer Dispatch below (bypasses tier scaffolding, researcher, and tier writers — but README/CHANGELOG still updated).
If "Scaffold": Continue with enriched documentation flow below.

**YOLO override:** Auto-select "Skip" (skip tier scaffolding, still run README/CHANGELOG writer).

<!-- SYNC: enriched-doc-dispatch -->
#### Pre-Computed Git Timestamps

For each enabled tier, compute the last-modified timestamp from source paths:

- **user-guide:** `git log -1 --format=%aI -- README.md package.json setup.py pyproject.toml bin/`
- **dev-guide:** `git log -1 --format=%aI -- src/ test/ Makefile .github/ CONTRIBUTING.md docker-compose.yml`
- **technical:** `git log -1 --format=%aI -- src/ docs/technical/`

If any command returns empty, use `"no-source-commits"` for that tier. Store as JSON map:

```json
{
  "user-guide": "2026-02-25T10:30:00-05:00",
  "dev-guide": "no-source-commits",
  "technical": "2026-02-24T14:15:00-05:00"
}
```

<!-- SYNC: enriched-doc-dispatch -->
#### Researcher Dispatch

```
Task tool call:
  description: "Research documentation state for feature {id}-{slug}"
  subagent_type: pd:documentation-researcher
  model: sonnet
  prompt: |
    Research current documentation state for feature {id}-{slug}.

    Mode: {mode}
    Enabled tiers: {enabled_tiers}

    Feature context:
    - Git diff (staged + unstaged): {git diff output against base branch}
    - Recent commits: {git log --oneline -20}

    Doc-schema reference:
    {doc_schema_content}

    Pre-computed tier timestamps:
    {timestamps_json}

    Analyze which tiers need updates based on the feature changes and
    source-path timestamps. Return structured JSON with:
    - no_updates_needed: boolean
    - affected_tiers: list of tier names that need doc updates
    - findings: per-tier analysis of what changed and what docs need updating
```

#### Researcher Evaluation Gate

If researcher returns `no_updates_needed: true` AND `affected_tiers` is empty:

```
AskUserQuestion:
  questions: [{
    "question": "Documentation researcher found no updates needed. Skip documentation?",
    "header": "Documentation",
    "options": [
      {"label": "Skip documentation", "description": "No documentation updates needed"},
      {"label": "Force update", "description": "Run documentation writer anyway"}
    ],
    "multiSelect": false
  }]
```

**YOLO override:** Auto-select "Skip documentation".

If "Skip documentation": Continue to Step 3.

#### Writer Dispatch

Build writer context from: researcher findings + mode + enabled tiers + `{doc_schema_content}` + ADR context (read `design.md` if it exists in feature artifacts directory).

**Budget breakdown:**
- **Scaffold mode:** 1 researcher (done) + up to 3 tier writers (sequential, one per affected tier) + 1 README/CHANGELOG writer = 5 max dispatches
- **Incremental mode:** 1 researcher (done) + 1 tier writer (handles all affected tiers) + 1 README/CHANGELOG writer = 3 max dispatches

**Tier writer dispatch (scaffold mode — one per affected tier, sequential):**

```
Task tool call:
  description: "Write {tier} documentation for feature {id}-{slug}"
  subagent_type: pd:documentation-writer
  model: sonnet
  prompt: |
    Write documentation for the {tier} tier.

    Mode: scaffold
    Feature: {id}-{slug}
    Research findings: {researcher findings for this tier}
    Doc-schema: {doc_schema_content}
    ADR context: {design.md content if exists, else "none"}

    Create the docs/{tier}/ directory and seed files per doc-schema.
    Return summary of files created.
```

**Tier writer dispatch (incremental mode — single dispatch for all affected tiers):**

```
Task tool call:
  description: "Update documentation for feature {id}-{slug}"
  subagent_type: pd:documentation-writer
  model: sonnet
  prompt: |
    Update documentation for affected tiers.

    Mode: incremental
    Feature: {id}-{slug}
    Affected tiers: {affected_tiers}
    Research findings: {researcher findings}
    Doc-schema: {doc_schema_content}
    ADR context: {design.md content if exists, else "none"}

    Update existing docs in affected tier directories.
    Return summary of changes made.
```

<!-- SYNC: readme-changelog-dispatch -->
#### README/CHANGELOG Writer Dispatch

```
Task tool call:
  description: "Update README and CHANGELOG for feature {id}-{slug}"
  subagent_type: pd:documentation-writer
  model: sonnet
  prompt: |
    Update README.md and CHANGELOG.md based on feature changes.

    Feature: {id}-{slug}
    Research findings: {researcher findings, OR if scaffold was skipped: "No researcher findings (scaffold skipped). Use git diff (staged + unstaged) against base branch for context:\n" + git diff output}

    README.md:
    - Pay special attention to any drift_detected entries — components that
      exist on the filesystem but are missing from README.md (or vice versa).
    - Update README.md (root). If plugins/pd/README.md exists (dev workspace),
      update it too.
    - Add missing entries to matching tables, remove stale entries,
      correct component count headers.

    CHANGELOG.md:
    - Add entries under the ## [Unreleased] section
    - Use Keep a Changelog categories: Added, Changed, Fixed, Removed
    - Only include user-visible changes (new commands, skills, config options,
      behavior changes)
    - Skip internal refactoring, test additions, and code quality changes

    Return summary of changes made.
```

#### Documentation Commit

```bash
git add docs/ README.md CHANGELOG.md
git commit -m "docs: update documentation"
git push
```

---

## Step 3: Retrospective (Automatic)

Run retrospective automatically without asking permission.

### Step 3a: Run Retrospective

Follow the `retrospecting` skill, which handles:
1. Context bundle assembly (.meta.json, .review-history.md, git summary, artifact stats)
2. retro-facilitator agent dispatch (AORTA framework analysis)
3. retro.md generation
4. Knowledge bank updates
5. Commit

The skill includes graceful degradation — if retro-facilitator fails, it falls back to investigation-agent.

### Step 3b: CLAUDE.md Update

Capture session learnings into project CLAUDE.md.

**Dependency:** Requires `claude-md-management` plugin (from claude-plugins-official marketplace).

1. **Invoke skill:**
   Invoke the `claude-md-management:revise-claude-md` skill via the Skill tool.

2. **If skill unavailable** (plugin not installed):
   Log "claude-md-management plugin not installed, skipping CLAUDE.md update." and continue to Step 4.

3. **If changes made:**
   ```bash
   git add CLAUDE.md .claude.local.md 2>/dev/null
   git commit -m "chore: update CLAUDE.md with feature {id}-{slug} learnings" --allow-empty
   git push
   ```

---

## Step 4: Completion Decision

Present only two options:

The option labels depend on whether `{pd_release_script}` is configured:

```
AskUserQuestion:
  questions: [{
    "question": "Feature {id}-{slug} complete. How would you like to finish?",
    "header": "Finish",
    "options": [
      {"label": "Merge & Release (Recommended)", "description": "Merge to {pd_base_branch} and run release script"},
      // ↑ Use "Merge (Recommended)" and description "Merge to {pd_base_branch}"
      //   if {pd_release_script} is not configured
      {"label": "Create PR", "description": "Open pull request for team review"}
    ],
    "multiSelect": false
  }]
```

---

## Step 5: Execute Selected Option

### Step 5a: Pre-Merge Validation

Before executing the selected option, discover and run project checks to catch issues while still on the feature branch.

**Discovery** — scan in this order, collecting checks from all matching categories:

1. **CI/CD config**: Glob for `.github/workflows/*.yml`. For each file, grep for `run:` lines that reference local scripts or common commands (e.g. `./validate.sh`, `npm test`, `npm run lint`). Deduplicate against checks already collected.
2. **Validation script**: Check if `validate.sh` exists at the project root. If found, add `./validate.sh`.
3. **Package.json scripts**: If `package.json` exists, read it and look for scripts named `test`, `lint`, `check`, or `validate`. For each found, add `npm run {name}`.
4. **Makefile**: If `Makefile` exists, grep for targets named `check`, `test`, `lint`, or `validate`. For each found, add `make {target}`.

Deduplicate: if the same underlying command appears via multiple discovery paths, run it only once.

If **no checks discovered**: Log "No project checks found — skipping pre-merge validation." and proceed.

**Execution loop** (max 3 attempts):

1. Run all discovered checks sequentially.
2. If all pass → proceed to the selected option below.
3. If any check fails:
   - Analyze the failure output and attempt to fix the issues automatically.
   - Commit fixes: `git add -A && git commit -m "fix: address pre-merge validation failures"`.
   - Re-run all checks (counts as next attempt).
4. If checks still fail after 3 attempts, STOP and inform the user:

```
Pre-merge validation failed after 3 attempts.

Still failing:
- {check command}: {brief error summary}

Fix these issues manually, then run /finish-feature again.
```

Do NOT proceed to Create PR or Merge & Release if validation is failing.

### Step 5b: Pre-Release Adversarial QA Gate

> **YOLO exception:** HIGH findings always exit non-zero; gate never prompts; MED/LOW auto-file silently. This is the one explicit YOLO exception in `finish-feature.md`.

After Step 5a (validate.sh) passes, dispatch the 4 adversarial reviewer agents against the feature branch diff to catch HIGH-severity issues that would otherwise surface only in post-release adversarial QA.

**In a single Claude message, dispatch all 4 reviewers in parallel using the Task tool. Do NOT dispatch sequentially.**

**Dispatch table:**

| # | subagent_type | model | Output shape |
|---|---|---|---|
| 1 | `pd:security-reviewer` | opus | JSON `{approved, issues[{severity, securitySeverity, location, ...}], summary}` |
| 2 | `pd:code-quality-reviewer` | sonnet | JSON `{approved, issues[{severity, location, ...}], summary}` |
| 3 | `pd:implementation-reviewer` | opus | JSON `{approved, issues[{severity, level, ...}], summary}` |
| 4 | `pd:test-deepener` | opus | **Step A** mode only — JSON `{gaps[{severity, mutation_caught, location, ...}], summary}` |

Each dispatch prompt MUST include: feature `spec.md` content (or fallback `no spec.md found — review for general defects against the diff; do not synthesize requirements`), diff via `git diff {pd_base_branch}...HEAD`, and an instruction to emit `location` as `file:line` for cross-confirmation.

**Severity rubric** (predicates inline per AC-5):

- HIGH: `severity == "blocker"` OR `securitySeverity in {"critical", "high"}`
- MED: `severity == "warning"` OR `securitySeverity == "medium"`
- LOW: `severity == "suggestion"` OR `securitySeverity == "low"`

**test-deepener narrowed remap** (AC-5b): test-deepener gaps with severity HIGH remap to MED **only when** `mutation_caught == false` AND no other reviewer flagged the same `location`. Cross-confirmed gaps stay HIGH (uncaught coverage-debt only).

**Test-only-refactor downgrade** (feature 099 FR-1): Before the bucketing loop, compute `IS_TEST_ONLY_REFACTOR` via `git diff {pd_base_branch}...HEAD --name-only` filtered by the test-file regex `(^|/)test_[^/]*\.py$|_test\.py$|(^|/)tests/.*\.py$` (re.search; non-empty AND all-match → True). Pass `is_test_only_refactor=...` kwarg to each `bucket()` call. When the conditions of AC-5b would have produced HIGH→MED AND `IS_TEST_ONLY_REFACTOR == True` AND the finding's location matches the same test-file regex (with `:line` suffix stripped), the bucketing further downgrades HIGH → LOW. LOW folds to retro sidecar instead of auto-filing to backlog. Prevents recursive test-hardening accumulation per `{pd_artifacts_root}/features/097-iso8601-test-pin-v2/qa-override.md` rationale.

**Decision tree:**

- **HIGH count > 0** → block merge unless `qa-override.md` exists with ≥ 50 chars of user-authored rationale (per-section trimmed-count). Print findings list with location + suggested_fix per finding. Exit non-zero.
- **MED findings** → auto-file each to `{pd_artifacts_root}/backlog.md` under `## From Feature {feature_id} Pre-Release QA Findings ({date})` section (next-available 5-digit ID).
- **LOW findings** → append each to `{pd_artifacts_root}/features/{id}-{slug}/.qa-gate-low-findings.md` sidecar (created if absent). Folded into `retro.md` by `pd:retrospecting` skill.
- **Idempotency:** if `.qa-gate.json` exists with `head_sha == $(git rev-parse HEAD)`, skip dispatch and append `skip:` line to `.qa-gate.log`.
- **Incomplete-run** (any reviewer fails JSON parse + schema validation): block; print `INCOMPLETE: {n} of 4 reviewers failed: [...]`; exit non-zero. Never silent-pass on partial coverage.

**Audit/telemetry:** gate appends one `count: [pd:reviewer]: HIGH=N MED=N LOW=N` line per reviewer to `.qa-gate.log` (per AC-17).

**See [`docs/dev_guides/qa-gate-procedure.md`](../../../docs/dev_guides/qa-gate-procedure.md)** for full dispatch prompts (§1), test-deepener Step A invocation (§2), JSON parse contract via `python3 -c` heredoc (§3), severity bucketing two-phase logic (§4), per-feature backlog sectioning + ID extraction (§5), LOW sidecar format (§6), idempotency cache + atomic-rename writes + corruption handling (§7), override path with per-section trimmed-count (§8), incomplete-run policy (§9), YOLO surfacing (§10), large-diff fallback (§11), and override-storm warning (§12).

### Step 5a-bis: Security Review (CC Native)

After all discovered project checks pass (or when none are discovered), run CC's native `/security-review` as a complementary defense-in-depth check on the pending changes. This does NOT replace pd's security-reviewer agent in the implement review loop — it is an additional gate specifically for pre-merge.

**Availability check:**

1. Check whether `.claude/commands/security-review.md` exists in the project root.
2. If **not present**: log the following warning and skip this step without blocking the merge:

   ```
   security-review not available, skipping pre-merge security scan.
   To enable: copy the bundled template to .claude/commands/security-review.md.
   Template location: `plugins/pd/references/security-review.md` (dev workspace) or
   the equivalent `~/.claude/plugins/cache/*/pd*/*/references/security-review.md`.
   ```

   Then proceed to the selected option below. Do NOT enter the auto-fix loop for a missing command.

3. If **present**: proceed to invocation.

**Invocation:**

Instruct the orchestrating agent to run `/security-review` to analyze the pending changes for security vulnerabilities.

**Result handling:**

- If `/security-review` returns with no critical/high findings → proceed to the selected option below.
- If `/security-review` reports critical or high severity findings → treat as a pre-merge validation failure equivalent to a failed check in Step 5a:
  - Attempt to fix the flagged issues automatically.
  - Commit fixes: `git add -A && git commit -m "fix: address security-review findings"`.
  - Re-run `/security-review` (counts as an attempt under the same 3-attempt cap as Step 5a).
  - If still failing after 3 attempts, STOP and inform the user:

    ```
    /security-review reported unresolved findings after 3 attempts.

    Remaining findings:
    - {finding summary}

    Address these issues manually, then run /finish-feature again.
    ```

- If invocation fails for any other reason (command errors, agent cannot locate the command at runtime, etc.) → log "security-review invocation failed, skipping" and proceed to the selected option. Do NOT block the merge on invocation errors; a missing or broken command is a degradation, not a vulnerability signal.

Do NOT proceed to Create PR or Merge & Release if `/security-review` is failing with unresolved critical/high findings. A skipped security-review (unavailable or invocation error) does NOT block the merge.

### If "Create PR":

```bash
git push -u origin feature/{id}-{slug}
gh pr create --title "Feature: {slug}" --body "## Summary
{Brief description from spec.md}

## Changes
{List of key changes}

## Testing
{Test instructions or 'See tasks.md'}"
```

Output: "PR created: {url}"
→ Continue to Step 6

### If "Merge & Release" (or "Merge"):

```bash
# Merge to base branch
git checkout {pd_base_branch}
git pull origin {pd_base_branch}
git merge feature/{id}-{slug}
git push
```

If `{pd_release_script}` is set and the file exists at that path, run it:
```bash
{pd_release_script}
```
Otherwise, skip the release step and output "No release script configured."

Output: "Merged to {pd_base_branch}." followed by "Release: v{version}" if release script ran, or "No release script configured." if not.
→ Continue to Step 6

---

## Step 6: Cleanup (Automatic)

Run automatically after Step 5 completes.

### Step 6a: Complete Feature State

Call `complete_phase` MCP tool to set terminal status and update `.meta.json`:

1. Construct feature_type_id as "feature:{folder_name}" where {folder_name} is the
   feature directory name (e.g., "015-small-command-migration-finish").
2. Call `complete_phase(feature_type_id, "finish")`.
   This sets entity status to "completed" and projects the final `.meta.json` with
   `status: "completed"`, `lastCompletedPhase: "finish"`, and completion timestamps.
3. If the call succeeds: no additional output needed.
4. If the call fails (MCP unavailable, phase mismatch, feature not found, or
   no active phase in DB): output a warning line "Note: Workflow DB sync
   skipped -- {error reason}. State will reconcile on next reconcile_apply
   run." but do NOT stop or block the completion flow. All error types are
   handled identically.
5. Commit the updated `.meta.json`:
   ```bash
   git add {pd_artifacts_root}/features/{id}-{slug}/.meta.json
   git diff --cached --quiet || git commit -m "chore: mark feature {id} as completed in .meta.json"
   git push
   ```
   - If nothing to commit: no-op (`.meta.json` may already be committed).
   - If push fails: warn but do not block cleanup.

### Step 6b: Delete temporary files

```bash
rm {pd_artifacts_root}/features/{id}-{slug}/.review-history.md 2>/dev/null || true
rm {pd_artifacts_root}/features/{id}-{slug}/implementation-log.md 2>/dev/null || true
```

### Step 6c: Delete Feature Branch

- After PR: Branch will be deleted when PR merged via GitHub
- After Merge & Release: `git branch -d feature/{id}-{slug}`

### Step 6d: Final Output

```
Feature {id}-{slug} completed
Retrospective saved to retro.md
Branch cleaned up
{PR created: {url} | Released v{version}}

Learnings captured in knowledge bank.
```
