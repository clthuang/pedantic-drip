---
name: implementing
description: Dispatches per-task implementer agents from tasks.md, collecting reports into implementation-log.md. Use when the user says 'implement the feature', 'start coding', 'write the code', or 'execute tasks'.
---

# Implementation Phase

## Static Reference
Execute the implementation plan with a structured per-task dispatch approach.

## Prerequisites

- If `tasks.md` exists: Read for task list
- If not: "No tasks found. Run /pd:create-plan first, or describe what to implement."

## Related Skills

For complex implementations:
- `implementing-with-tdd` - RED-GREEN-REFACTOR discipline

## Process

### Step 1: Read Task List

1. Read `tasks.md` from the active feature directory
2. Parse all task headings using regex: `/^(#{3,4})\s+Task\s+(\d+(?:\.\d+)*):?\s*(.+)$/`
3. For each match, extract:
   - **Task number** (string, e.g., "1.1")
   - **Task title**
   - **Task body** (from heading through next same-or-higher-level heading, or EOF)
   - **Why/Source** field value (from `**Why:**` or `**Source:**`, if present)
   - **Done when** criteria (from `**Done when:**`, if present)
4. If no task headings found: log error, surface to user, STOP

### Step 2: Per-Task Dispatch Loop (parallel worktree dispatch)

Step 2 dispatches implementer agents in batches of up to `max_concurrent_agents`, each in its own git worktree, then merges the worktree branches into the feature branch in task-document order. The structure is three phases per batch:

- **Phase 1: Worktree setup** — resume detection, then create one worktree per task (with per-task fallback on failure)
- **Phase 2: Parallel agent dispatch** — issue all agent Task calls in a single message with worktree-aware prompts
- **Phase 3: Post-agent validation + sequential merge + cleanup** — SHA check, halt-on-conflict merge, worktree removal

If a batch surfaces SQLite BUSY errors, all remaining batches fall back to serial, no-worktree dispatch (see Phase 3 below).

#### Step 2a: Prepare context (per task, shared across both dispatch modes)

**Parse traceability references** from the task's `**Why:**` or `**Source:**` field value:

1. If the field is present, split its value on comma and trim each reference.
2. Match each reference against these patterns:
   - Plan reference: `/Plan (?:Step )?(\w+\.\w+)/i` — captures plan identifier (e.g., "1A.2")
   - Design reference: `/Design (?:Component )?(\w+[-\w]*)/i` — captures design identifier (e.g., "event-bus")
   - Spec reference: `/Spec (\w+\.\w+)/i` — informational only; spec is always loaded in full
3. Collect matched plan identifiers and design identifiers into separate lists.

**Extract scoped sections** using heading extraction:

For each plan identifier, extract its section from `plan.md`. For each design identifier, extract its section from `design.md`. Use this procedure:

To extractSection(markdown, identifier): scan all headings in the markdown. Find the first heading whose text contains the identifier as a case-insensitive substring. Extract everything from that heading through (but not including) the next heading at the same level, or through EOF if no same-level heading follows.

To extractSectionWithFallback(markdown, identifier): first try extractSection with the full identifier. If no heading matches and the identifier contains a dot, strip everything after the last dot (e.g., "1A.1" becomes "1A") and retry with that prefix. Return the matched section text, or null if still not found.

Apply extractSectionWithFallback for each identifier. If any extraction returns null, discard all partial results for that artifact and load the full file instead.

**Fallback: load full artifacts when traceability is unavailable.** If the Why/Source field is absent, empty, or none of its references match the patterns above, load design.md and plan.md in full. Log a warning: "No parseable traceability references — loading full artifacts." Known fallback scenarios:
- Feature 018 uses a `§` separator format that the regexes will not match
- Feature 020 has no traceability fields
- Features 002-016 predate the traceability template

**Assemble context for dispatch:**
- `design.md`: scoped sections joined in order (or full file if any extraction failed or fallback triggered)
- `plan.md`: scoped sections joined in order (or full file if any extraction failed or fallback triggered)
- `prd.md` (I8 resolve_prd): resolve the PRD file path before dispatch:
  1. Check if `{feature_path}/prd.md` exists
  2. If exists → PRD path = `{feature_path}/prd.md`
  3. If not → check `.meta.json` for `brainstorm_source`
     a. If found → PRD path = brainstorm_source value
     b. If not → PRD line = `- PRD: No PRD — feature created without brainstorm`
- `spec.md`: referenced in Required Artifacts block — agent reads via Read tool on demand

**Load project context (conditional):**

Check the feature's `.meta.json` for a `project_id` field. If absent or null, skip this entire block — no error, no warning (AC-10).

If `project_id` is present (non-null):

1. **Resolve project directory:** Glob `{pd_artifacts_root}/projects/{project_id}-*/`. If not found, log warning and skip project context entirely.
2. **Load project goals:** Read the project's `prd.md`. Extract `## Problem Statement` and `## Goals` sections (heading through next `##`). Summarize to 2-3 bullet points (~100 tokens).
3. **Load feature dependency status:** Read this feature's `.meta.json` `depends_on_features` list. If absent or empty, omit dependencies from the block. For each reference: glob `{pd_artifacts_root}/features/{ref}-*/`, read its `.meta.json` `status` field. Categorize into completed[], in-progress[], blocked[].
4. **Load priority signal:** Read the project's `roadmap.md` if it exists. Find the milestone containing this feature's ID or slug. Extract milestone name and position (~50 tokens). If `roadmap.md` missing, omit priority signal.
5. **Format the block** (~200-500 tokens total):

```markdown
## Project Context
**Project:** {project name} | **This feature:** {feature name}
**Project goals:** {2-3 bullet summary from project PRD}
**Feature dependencies:** completed: {names} | in-progress: {names} | blocked: {names}
**Priority signal:** {milestone name, or "not on roadmap"}
```

6. **Token budget enforcement:** If the formatted block exceeds ~500 tokens (e.g., many dependencies), truncate dependency details to counts only ("3 completed, 1 in-progress") and trim goal bullets.

**Graceful degradation:** Project dir not found: skip block. `roadmap.md` missing: omit priority line. `depends_on_features` absent: omit dependencies line. Any individual dependency glob fails: skip that dependency, continue with others.

#### Step 2b: Batch planning and entry-time resume detection

1. Compute the list of unchecked tasks in document order.
2. Record the feature branch HEAD SHA once, before any worktrees are created:
   ```bash
   FEATURE_BRANCH=$(git rev-parse --abbrev-ref HEAD)
   MAIN_SHA=$(git rev-parse HEAD)
   ```
   This SHA is the pre-dispatch checkpoint used by Phase 3 stray-commit detection.
3. Initialize `SERIAL_FALLBACK=false`. This flag promotes all remaining batches to serial, no-worktree dispatch after a SQLite BUSY report (see Step 2e Phase 3).
4. Ensure `.pd-worktrees/` is present in the project's `.gitignore`. If missing, append it and commit on the feature branch before dispatching.
5. **Resume detection (T2.10):** List existing worktree branches for this feature:
   ```bash
   EXISTING=$(git worktree list --porcelain | awk '/^branch / { print $2 }' | sed 's|^refs/heads/||' | grep "^worktree-{feature_id}-task-")
   ```
   For each task, if `worktree-{feature_id}-task-{N}` is present in `EXISTING`, mark the task as `resume=true`. Phase 1 will skip creation for resume tasks; Phase 2 will skip dispatch for resume tasks (their work is already on disk in the worktree); Phase 3 merges them in task order alongside freshly dispatched tasks.
6. Chunk the remaining tasks into batches of size `min(len(remaining_tasks), max_concurrent_agents)`. Process batches sequentially; within each batch, run Phase 1 → Phase 2 → Phase 3 before starting the next batch.

#### Step 2c: Phase 1 — Worktree setup (per batch)

If `SERIAL_FALLBACK=true`, skip this phase entirely and jump to Step 2d with `worktree_mode=false` for every task in the batch.

For each task in the batch (in task-document order):

1. If the task is marked `resume=true`, skip creation — the worktree is already on disk. Record its path as `.pd-worktrees/task-{N}` and continue to the next task.
2. Otherwise, attempt creation:
   ```bash
   git worktree add ".pd-worktrees/task-{N}" -b "worktree-{feature_id}-task-{N}"
   ```
3. **Per-task fallback on failure (T2.8):** If the command exits non-zero, that task drops to no-worktree dispatch for this batch only; other tasks in the batch continue with their worktrees. **Critical branch-leak cleanup:** Per `plugins/pd/hooks/tests/test-worktree-dispatch.sh` test 4(a), `git worktree add -b BRANCH PATH` on git 2.50+ creates `BRANCH` before validating `PATH`, so a failed add can leave an orphaned branch behind. Before recording the fallback, run:
   ```bash
   git branch -D "worktree-{feature_id}-task-{N}" 2>/dev/null || true
   ```
   Without this cleanup, a retry (or Phase 3 merge) would hit a duplicate-branch error on the next attempt. Flag the task with `worktree_mode=false` and `worktree_path=null`; surface a warning like "Worktree creation failed for task {N}; dispatching without isolation."

After Phase 1, each task in the batch carries one of three states:
- `worktree_mode=true, resume=false, worktree_path=.pd-worktrees/task-{N}` — fresh worktree created
- `worktree_mode=true, resume=true,  worktree_path=.pd-worktrees/task-{N}` — existing worktree reused, skip dispatch
- `worktree_mode=false, worktree_path=null` — per-task fallback, dispatch without isolation

#### Step 2d: Phase 2 — Parallel agent dispatch (per batch)

Dispatch every task in the batch whose state is NOT `resume=true` **in a single message**, issuing one Task tool call per task so CC runs them concurrently. This replaces the previous serial loop.

Concurrency is capped at `max_concurrent_agents` by construction, since each batch is sized to that limit.

**Prompt template (worktree mode, `worktree_mode=true`):**

```
Task tool call:
  subagent_type: pd:implementer
  model: opus
  prompt: |
    ## Worktree Instructions (MANDATORY)
    You are working in an isolated git worktree. Absolute worktree path:
      {abs_project_root}/.pd-worktrees/task-{N}/

    Rules:
    - Use ABSOLUTE paths for every Read, Edit, Write, Glob, and Grep call. Relative paths resolve against the orchestrator's cwd, not your worktree.
    - Before ANY Bash command, run: `cd {abs_project_root}/.pd-worktrees/task-{N}`
    - Do NOT modify files outside your worktree directory.
    - Do NOT modify `.meta.json` anywhere. The orchestrating skill is the sole writer; worktree agents that touch `.meta.json` will have their changes discarded.
    - If an entity DB write fails repeatedly with "database is locked" / SQLITE_BUSY, surface the failure verbatim in your report under a **Concerns** line so the orchestrator can trigger full-serial fallback for remaining batches.

    {task description with done-when criteria}

    {## Project Context block, if prepared above — omit entirely if not project-linked}

    ## Required Artifacts
    You MUST read the following files before beginning your work.
    After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
    - Spec: {feature_path}/spec.md
    {resolve_prd() output — emit "- PRD: {path}" or "- PRD: No PRD — feature created without brainstorm"}

    ## Design Context (scoped)
    {design.md scoped sections via extractSection()}

    ## Plan Context (scoped)
    {plan.md scoped sections via extractSection()}
```

**Prompt template (no-worktree fallback, `worktree_mode=false`):** identical to the worktree template except the `## Worktree Instructions` block is replaced with:

```
## Isolation Notice
Worktree isolation was not available for this task (per-task fallback or full-serial fallback). Work in the main project tree. Do NOT modify `.meta.json` — the orchestrating skill is the sole writer.
```

**Dispatch protocol:**

- Emit all Task calls in a single assistant message (the same pattern the researching skill uses for Phase 1 parallel dispatch). CC runs them concurrently up to the platform limit.
- Skip dispatch for any task with `resume=true` — its commits are already on its worktree branch from a prior interrupted run.
- Wait for all dispatched agents to return before starting Phase 3.

**Fallback detection (I9):** For each returned report, search for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: implementer did not confirm artifact reads` to `.review-history.md`. Proceed regardless — this is observational only.

#### Step 2e: Phase 3 — Validation, merge, cleanup (per batch)

**1. Stray-commit detection (T2.5).** Immediately after agents return, re-read the feature branch HEAD:

```bash
CURRENT_SHA=$(git rev-parse HEAD)
```

- If `CURRENT_SHA == MAIN_SHA` **and** `git diff --name-only` is empty, proceed to the merge step.
- If `CURRENT_SHA != MAIN_SHA`, one or more agents committed directly to the feature branch in violation of the worktree directive. Halt Step 2 and surface:
  ```
  WARNING: Agent(s) committed to feature branch outside worktrees
  Unexpected commits: $(git log --oneline ${MAIN_SHA}..HEAD)
  Manual review required before merging worktree branches.
  ```
  Do NOT attempt merges — stop and return to the user with these details so they can review/revert before re-entry.
- If HEAD is unchanged but `git diff --name-only` shows uncommitted writes in the main tree, discard them with `git checkout -- .` and continue (stray writes without commits are safe to drop; commits are not).

**2. Collect reports + detect SQLite BUSY (T2.9).** For each returned agent report, extract the standard fields (Files changed, Decisions, Deviations, Concerns) using case-insensitive substring match on the field headers. Scan the entire report (not just the Concerns field) for the substrings `SQLITE_BUSY` or `database is locked`. If any report matches, set `SERIAL_FALLBACK=true` — this promotes all future batches (starting with the next one) to no-worktree serial dispatch. The current batch still finishes its Phase 3 merge sequence; the fallback takes effect on the next batch only.

**3. Sequential merge with halt-on-conflict (T2.6).** Ensure the current branch is the feature branch (`git checkout {FEATURE_BRANCH}` if needed). Then, for each task in the batch **in task-document order** (including resumed tasks, excluding tasks whose state is `worktree_mode=false`):

```bash
git merge --no-ff "worktree-{feature_id}-task-{N}" -m "merge task {N}: {title}"
```

If the merge exits non-zero (merge conflict), halt the merge sequence immediately:

- Do NOT attempt merges for subsequent tasks in the batch — conflict resolution may alter the tree in ways that change downstream merges.
- Do NOT remove any worktrees; the failed task's worktree stays on disk for debugging and resume.
- Surface to the user: the conflicting task number, the conflicted paths (`git diff --name-only --diff-filter=U`), the unmerged branch name, and a recovery instruction: "Resolve the conflict, commit, then re-run `/pd:implement` — Step 2 resume detection will pick up from the next unmerged worktree branch."
- Return from Step 2 with the halt state; do not run Step 3.

Tasks with `worktree_mode=false` have no worktree branch to merge — their changes are already on the feature branch (written directly by the fallback-dispatched agent).

**4. Worktree cleanup (T2.7).** After each successful merge, remove the corresponding worktree:

```bash
git worktree remove ".pd-worktrees/task-{N}" 2>/dev/null
```

Do NOT pass `--quiet` to `git worktree remove` — it is unsupported on git 2.50+ (observed on Apple Git-155). Redirect stderr with `2>/dev/null` if you want to suppress noise. Failed merges leave their worktree on disk intentionally so the user can inspect it; only successful merges trigger removal.

After a successful merge, update `MAIN_SHA` to the new feature-branch HEAD so the next batch's Phase 3 stray-commit detection uses a current baseline:

```bash
MAIN_SHA=$(git rev-parse HEAD)
```

**5. Append implementation-log.md entries.** For each task in batch order, write to `implementation-log.md` in the active feature directory. Create the file with `# Implementation Log` header on the first task:

```markdown
## Task {number}: {title}
- **Files changed:** {from report}
- **Decisions:** {from report, or "none"}
- **Deviations:** {from report, or "none"}
- **Concerns:** {from report, or "none"}
```

#### Step 2f: Per-task error handling

- **Dispatch failure (AC-20):** Log the error, then ask the user whether to retry or skip via AskUserQuestion. If the user skips, leave any created worktree on disk (resume detection will pick it up on re-entry).
- **Malformed report (AC-21):** Write a partial log entry with whatever fields are available; still run Phase 3 validation and merge for that task — report quality does not affect branch state.

#### Step 2g: Proceed to next batch

After Phase 3 completes for the current batch, move to the next batch. If `SERIAL_FALLBACK=true`, every remaining batch dispatches with `worktree_mode=false` for all tasks (skipping Phase 1 and the merge step of Phase 3 entirely; agents write directly to the feature branch in task-document order, one at a time).

### Step 3: Return Results

After all tasks dispatched:

1. Report summary: N tasks completed, M skipped/blocked
2. Return deduplicated list of all files changed
3. `implementation-log.md` is on disk for retro to read later

## Commit Pattern

After all tasks dispatched:
```
git add {files}
git commit -m "feat: {brief description}"
```

## Error Handling

If implementation is stuck:
1. Try a different approach
2. Break into smaller pieces
3. Ask user for guidance

See Step 2e for per-task dispatch failure (AC-20) and malformed report (AC-21) handling.

Never spin endlessly. Ask when stuck.

## Completion

After all tasks:
"Implementation complete. {N} tasks completed, {M} skipped."
"Proceeding to code simplification and review phases (3 reviewers dispatched in parallel, within `max_concurrent_agents` budget)."

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

## Read Feature Context

1. Find active feature folder in `{pd_artifacts_root}/features/`
2. Read `.meta.json` for mode and context
3. Adjust behavior based on mode:
   - Standard: Full process with optional verification
   - Full: Full process with required verification
