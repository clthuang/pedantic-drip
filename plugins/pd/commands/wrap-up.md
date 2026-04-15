---
description: Wrap up implementation - review, retro, merge or PR
argument-hint: ""
---

# /pd:wrap-up Command

Wrap up the current implementation with code review, retrospective, and merge/PR. This command is for work done outside the pd feature workflow (e.g., after plan mode).

## Config Variables
Use these values from session context (injected at session start):
- `{pd_base_branch}` — base branch for merges (default: `main`)
- `{pd_release_script}` — path to release script (empty if not configured)

## YOLO Mode Overrides

If `[YOLO_MODE]` is active:
- Step 2a (tasks incomplete) → auto "Continue anyway"
- Step 2b (researcher no_updates_needed + empty affected_tiers) → auto-select Skip
- Step 2b (docs updates found) → proceed with writer dispatches (no prompt needed)
- Step 4 (completion decision) → auto "Merge & Release (Recommended)" (or "Merge (Recommended)" if `{pd_release_script}` is not configured)
- **Git merge failure:** STOP and report. Do NOT attempt to resolve merge conflicts
  autonomously. Output: "YOLO MODE STOPPED: Merge conflict on {pd_base_branch}. Resolve manually."

---

## Step 1: Auto-Commit and Push

### Step 1a: Commit and Push

1. Check for uncommitted changes via `git status --short`
2. If uncommitted changes found:
   - `git add -A && git commit -m "wip: uncommitted changes before wrap-up"`
   - `git push`
   - On push failure: Show error and STOP - user must resolve manually
3. If no uncommitted changes: Continue

---

## Step 2: Pre-Completion Reviews

### Step 2a: Check Task Completion

1. Call `TaskList` to get all tasks
2. Count pending/in_progress tasks
3. If no tasks exist: Continue (skip this step)

If incomplete tasks found:

```
AskUserQuestion:
  questions: [{
    "question": "{n} tasks still incomplete. How to proceed?",
    "header": "Tasks",
    "options": [
      {"label": "Continue anyway", "description": "Proceed despite incomplete tasks"},
      {"label": "Review and complete tasks first", "description": "Go back and finish remaining tasks"}
    ],
    "multiSelect": false
  }]
```

If "Review and complete tasks first": Show "Complete remaining tasks, then run /pd:wrap-up again." → STOP

### Step 2b: Documentation Update (Enriched)

#### Mode

Mode is always `incremental` in wrap-up. Scaffold mode is not supported — run `/generate-docs` to scaffold documentation if needed.

#### Tier Resolution

<!-- SYNC: tier-resolution -->
1. Parse `pd_doc_tiers` from session context — split on comma, trim whitespace, filter to recognized values (`user-guide`, `dev-guide`, `technical`). If `pd_doc_tiers` is not set or empty, default to all three tiers.
2. For each recognized tier, check if `docs/{tier}/` exists (relative to project root). If missing, output:

```
Note: docs/{tier}/ directory does not exist. Run /generate-docs to scaffold documentation. Skipping {tier} tier.
```

Continue with remaining available tiers.

<!-- SYNC: enriched-doc-dispatch -->
#### Doc-Schema Resolution

3. Resolve doc-schema content: Glob `~/.claude/plugins/cache/*/pd*/*/references/doc-schema.md` — use first match. Fallback (dev workspace): `plugins/pd/references/doc-schema.md`.
4. Read the resolved file content, store as `{doc_schema_content}`.
5. Replace all occurrences of `{pd_artifacts_root}` in `{doc_schema_content}` with the actual session value.

<!-- SYNC: enriched-doc-dispatch -->
#### Pre-Computed Git Timestamps

For each enabled tier (that has an existing directory), compute the last-modified timestamp from source paths:

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
  description: "Research documentation state for wrap-up"
  subagent_type: pd:documentation-researcher
  model: sonnet
  prompt: |
    Research current documentation state for recent implementation work.

    Mode: incremental
    Enabled tiers: {enabled_tiers}

    Context (from git only — no feature artifacts in wrap-up):
    - Git diff (staged + unstaged): {git diff output against base branch}
    - Recent commits: {git log --oneline -20}

    Doc-schema reference:
    {doc_schema_content}

    Pre-computed tier timestamps:
    {timestamps_json}

    Analyze which tiers need updates based on recent changes and
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

**Graceful degradation:** If zero tier directories exist after filtering (all tiers missing), skip tier writing entirely and dispatch only the README/CHANGELOG writer (see below).

**Budget:** 1 researcher (done) + 1 tier writer + 1 README/CHANGELOG writer = 3 max dispatches (always incremental).

**Tier writer dispatch (incremental — single dispatch for all affected tiers):**

```
Task tool call:
  description: "Update tier documentation"
  subagent_type: pd:documentation-writer
  model: sonnet
  prompt: |
    Update documentation for affected tiers.

    Mode: incremental
    Affected tiers: {affected_tiers}
    Research findings: {researcher findings}
    Doc-schema: {doc_schema_content}

    Update existing docs in affected tier directories.
    Return summary of changes made.
```

<!-- SYNC: readme-changelog-dispatch -->
#### README/CHANGELOG Writer Dispatch

```
Task tool call:
  description: "Update README and CHANGELOG"
  subagent_type: pd:documentation-writer
  model: sonnet
  prompt: |
    Update README.md and CHANGELOG.md based on recent changes.

    Research findings: {researcher findings}

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

### Step 3a: Run Retrospective

Dispatch retro-facilitator agent with lightweight context:

```
Task tool call:
  description: "Run retrospective"
  subagent_type: pd:retro-facilitator
  model: opus
  prompt: |
    Run an AORTA retrospective on the recent implementation work.

    Context:
    - Recent commits: {git log --oneline -20}
    - Files changed: {git diff --stat summary}

    Analyze what went well, obstacles encountered, and learnings.
    Return structured findings.
```

If retro-facilitator fails, fall back to:
```
Task tool call:
  description: "Gather retrospective context"
  subagent_type: pd:investigation-agent
  model: sonnet
  prompt: |
    Analyze the recent implementation work for learnings.
    - Recent commits: {git log}
    - Files changed: {list}
    Return key observations and learnings.
```

Store learnings directly via `store_memory` MCP tool (no retro.md file).

Commit if any changes were made.

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
   git commit -m "chore: update CLAUDE.md with session learnings" --allow-empty
   git push
   ```

---

## Step 4: Completion Decision

The option labels depend on whether `{pd_release_script}` is configured:

```
AskUserQuestion:
  questions: [{
    "question": "Work complete. How would you like to finish?",
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

Before executing the selected option, discover and run project checks.

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

Fix these issues manually, then run /pd:wrap-up again.
```

Do NOT proceed to Create PR or Merge & Release if validation is failing.

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

    Address these issues manually, then run /pd:wrap-up again.
    ```

- If invocation fails for any other reason (command errors, agent cannot locate the command at runtime, etc.) → log "security-review invocation failed, skipping" and proceed to the selected option. Do NOT block the merge on invocation errors; a missing or broken command is a degradation, not a vulnerability signal.

Do NOT proceed to Create PR or Merge & Release if `/security-review` is failing with unresolved critical/high findings. A skipped security-review (unavailable or invocation error) does NOT block the merge.

### If "Create PR":

```bash
git push -u origin HEAD
gh pr create --title "{Brief summary from commits}" --body "## Summary
{Brief description from recent changes}

## Changes
{List of key changes}

## Testing
{Test instructions}"
```

Output: "PR created: {url}"
→ Continue to Step 6

### If "Merge & Release" (or "Merge"):

```bash
# Merge to base branch
git checkout {pd_base_branch}
git pull origin {pd_base_branch}
git merge {current-branch}
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

## Step 6: Cleanup

### Step 6a: Branch Cleanup

Determine current branch:
- If on `{pd_base_branch}` or `main`: No branch cleanup needed
- If on a feature/topic branch:
  - After PR: Branch will be deleted when PR merged via GitHub
  - After Merge & Release: `git branch -d {branch-name}`

### Step 6b: Final Output

```
Work wrapped up successfully.
{PR created: {url} | Released v{version}}

Learnings captured via memory tools.
```
