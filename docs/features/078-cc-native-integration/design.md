# Design: CC Native Feature Integration

## Prior Art Research

### Codebase Patterns
- Implementing skill serial dispatch: `SKILL.md:37-156` — Step 2 loop iterates tasks in document order, one Task call per task, `subagent_type: pd:implementer`, `model: opus`. No isolation or concurrency fields.
- Pre-merge validation discovery: `finish-feature.md:339-371` and `wrap-up.md:314-344` — identical 4-source discovery (CI yml, validate.sh, package.json scripts, Makefile targets), sequential execution, 3 auto-fix attempts.
- Researching skill parallel dispatch: `researching/SKILL.md:27-78` — Phase 1 dispatches 2 Task calls in same message (codebase-explorer + internet-researcher). Phase 2 dispatches synthesizer after Phase 1 completes.
- Session-start config injection: `session-start.sh:429-432` — reads `max_concurrent_agents` from `pd.local.md`, validates as integer, injects into session context.
- Graceful degradation pattern: `capture-tool-failure.sh` — wraps all operations in `|| { echo '{}'; exit 0; }` fallback. `yolo-guard.sh` — fast path exits silently for non-matching tools.
- Entity DB connection: `database.py` — opens with WAL mode AND `busy_timeout=15000` (15 seconds) by default (line 3505-3506). Provides `is_healthy()` check. The 15s busy_timeout means SQLite internally waits up to 15s before returning SQLITE_BUSY — any additional retry logic should account for this existing configuration.

### External Research
- **CRITICAL:** `isolation: worktree` is **silently ignored for plugin-defined subagent_type values** (CC Issues #33045, #37030). pd's `pd:implementer` is plugin-defined → inline `isolation: worktree` will NOT create worktrees. Bug filed late March 2026, no fix documented.
- **Workaround:** Manually create worktrees with `git worktree add`, prepend absolute-path directives to agent prompts. Only Bash `cd` respects worktree paths automatically; Read/Edit/Glob/Grep require explicit absolute paths.
- MCP servers NOT isolated by worktree — all worktree agents share the same MCP server instances and global DB at `~/.claude/pd/`.
- SQLite WAL allows unlimited concurrent readers but only ONE writer at a time. Parallel agents writing to same DB will serialize and may hit "database is locked". Per-worktree DB copies are the documented solution for true isolation.
- **CRITICAL:** Invoking CC slash commands (`/security-review`) from skill/command markdown is NOT a supported pattern. Built-in commands are not available through the Skill tool. Agent can only invoke them if instructed via natural language and the command is available in the session.
- `context: fork`: skill frontmatter field, runs skill in isolated subagent context (separate conversation, NOT separate worktree). Issue #17283 fixed Jan 2026.
- CronCreate is session-scoped, invoked by Claude via natural language. Max 50 tasks/session, 7-day expiry.

## Architecture Overview

### Component Diagram

```
┌─────────────────────────────────────────────────────┐
│                  pd Plugin                           │
│                                                      │
│  ┌──────────────────┐    ┌─────────────────────┐    │
│  │ implementing      │    │ finish-feature /     │    │
│  │ SKILL.md          │    │ wrap-up commands     │    │
│  │                   │    │                      │    │
│  │  Step 2: Dispatch │    │  Step 5a: Pre-merge  │    │
│  │  ┌─────────────┐ │    │  ┌────────────────┐  │    │
│  │  │ Parallel    │ │    │  │ Check Pipeline │  │    │
│  │  │ Worktree    │ │    │  │ + /security-   │  │    │
│  │  │ Dispatch    │ │    │  │   review       │  │    │
│  │  └──────┬──────┘ │    │  └────────────────┘  │    │
│  └─────────┼────────┘    └──────────────────────┘    │
│            │                                          │
│  ┌─────────▼────────┐    ┌─────────────────────┐    │
│  │ CC Agent Tool     │    │ researching          │    │
│  │ isolation:worktree│    │ SKILL.md             │    │
│  │                   │    │ context: fork        │    │
│  │ ┌───┐ ┌───┐ ┌───┐│    │ (stretch)            │    │
│  │ │WT1│ │WT2│ │WT3││    └─────────────────────┘    │
│  │ └─┬─┘ └─┬─┘ └─┬─┘│                               │
│  │   └──┬──┘──┬──┘   │    ┌─────────────────────┐    │
│  │      ▼     ▼      │    │ session-start.sh     │    │
│  │  Sequential Merge  │    │ + CronCreate doctor  │    │
│  │  to feature branch │    │ (stretch)            │    │
│  └───────────────────┘    └─────────────────────┘    │
│                                                      │
│  ┌────────────────────────────────────────────┐      │
│  │ Shared: ~/.claude/pd/entities/entities.db  │      │
│  │ WAL mode + retry-on-SQLITE_BUSY            │      │
│  └────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────┘
```

### Components

**C1: Parallel Worktree Dispatcher** (modifies `implementing/SKILL.md`)
- Replaces serial Step 2 dispatch loop with parallel dispatch
- Adds `isolation: "worktree"` to each Agent/Task call
- Dispatches up to `max_concurrent_agents` simultaneously
- Manages worktree branch merge sequence post-completion
- Handles per-task worktree failure fallback and full-serial SQLite fallback

**C2: Pre-Merge Security Gate** (modifies `finish-feature.md`, `wrap-up.md`)
- Adds `/security-review` invocation after existing Step 5a checks pass
- Natural language instruction to orchestrating agent
- Graceful skip if command unavailable

**C3: Behavioral Regression Tests** (new `test-workflow-regression.sh`)
- Automated shell tests for phase outcome verification
- Tests entity DB states, .meta.json transitions, workflow engine guards
- Uses existing test infrastructure (log_test, log_pass, log_fail)

**C4: SQLite Concurrency Spike** (new `test-sqlite-concurrency.sh`)
- Phase 0 gate for C1
- Tests parallel writes from actual git worktrees
- Validates WAL mode + retry under real topology

**C5: Context-Forked Research** (modifies `researching/SKILL.md`) [STRETCH]
- Adds `context: fork` frontmatter to researching skill
- Isolates Phase 1 agent context from main conversation

**C6: Scheduled Doctor** (modifies `session-start.sh`, `config.local.md`) [STRETCH]
- New `doctor_schedule` config field
- CronCreate invocation at session start when configured

## Technical Decisions

### TD-1: Dispatch Model Change (Serial → Parallel)

**Current:** Step 2 iterates tasks sequentially, dispatching one implementer at a time.

**New:** Step 2 collects all unchecked tasks, creates worktrees manually, dispatches agents with worktree-aware prompts.

**CRITICAL CONSTRAINT:** `isolation: "worktree"` is silently ignored for plugin-defined `subagent_type` values (CC Issue #33045, #37030). pd's `pd:implementer` is plugin-defined. Therefore, we CANNOT use the inline `isolation` parameter. Instead, we use the documented workaround:

```
# Phase 1: Create worktrees manually
for task in batch:
    git worktree add .pd-worktrees/task-{N} -b worktree-{feature_id}-task-{N}

# Phase 2: Dispatch agents with worktree-aware prompts
for task in batch:
    dispatch(task, prompt_prefix="""
        IMPORTANT: Work ONLY in the worktree directory:
        {absolute_path}/.pd-worktrees/task-{N}/
        Use absolute paths for ALL file operations (Read, Edit, Write, Glob, Grep).
        Use `cd {worktree_path}` before any Bash commands.
        Do NOT modify files in the main working directory.
    """)

# Phase 3: Merge sequentially after all agents complete
for task in batch:
    git checkout feature/{id}-{slug}
    git merge worktree-{feature_id}-task-{N}
    git worktree remove .pd-worktrees/task-{N}
```

**Worktree directory:** `.pd-worktrees/` at project root (NOT inside `.claude/` which is typically gitignored). Add `.pd-worktrees/` to `.gitignore` during Phase 1 if not already present. Create directory with `mkdir -p .pd-worktrees/`.

**Branch naming:** `worktree-{feature_id}-task-{N}` (e.g., `worktree-078-task-3`).

**Post-merge cleanup:** `git worktree remove <path>` after successful merge. On failure, leave worktree for debugging.

**SQLite concurrency strategy:** Rely on existing `busy_timeout=15000` (15s) in `database.py` for short contention. If SQLITE_BUSY persists beyond busy_timeout, retry the full DB operation twice more with 5s delays between attempts. If still failing after 3 total attempts (including the initial 15s wait), trigger full-serial fallback for remaining tasks. The spike (C4) must validate whether busy_timeout alone is sufficient under the actual worktree topology.

**Complexity estimate:** Manual worktree approach adds ~150-200 lines to implementing/SKILL.md (worktree creation, path injection, merge orchestration, validation, cleanup, fallback logic). This is justified per NFR-3 because: (a) it's a workaround for a CC bug (#33045), not architectural complexity; (b) when CC fixes the bug, ~120 of those lines can be removed, leaving only the merge orchestration; (c) the alternative (no parallelism) leaves a documented capability gap.

**Alternative (if CC fixes #33045):** Switch to inline `isolation: "worktree"` on Agent tool calls. The manual workaround is a bridge until the CC bug is resolved. Track CC Issue #33045 for status.

### TD-2: Two-Tier Fallback Strategy

| Failure Type | Detection Point | Fallback Scope | Behavior |
|---|---|---|---|
| Worktree creation (`git worktree add` non-zero) | At dispatch time | Per-task | That task dispatches without isolation; others continue in worktrees |
| Agent writes outside worktree (post-agent `git diff --name-only` detects changes in main tree) | Phase 3 pre-merge validation | Per-task | Flag task for manual review; do not merge worktree branch |
| SQLite BUSY after busy_timeout (existing 15s) exhausted | During agent execution | Full batch | Remaining tasks in current and future batches dispatch serially (no worktree) |
| Merge conflict | At merge time | Halt | Surface conflict details, document recovery path, halt further merges |

**Merge conflict recovery:** After user resolves conflict and commits, re-run `/pd:implement` which detects remaining un-merged worktree branches (via `git worktree list`) and continues the merge sequence from the next unmerged task.

**Post-agent worktree validation** (Phase 3, before merge):
```bash
# Check main tree for unexpected modifications
main_changes=$(git diff --name-only)
if [[ -n "$main_changes" ]]; then
    echo "WARNING: Agent modified files outside worktree: $main_changes"
    echo "Skipping merge for task {N}. Manual review required."
    # Do NOT merge this worktree branch
fi
```

### TD-3: .meta.json Write Isolation

Implementer agents in worktrees MUST NOT write to `.meta.json`. The orchestrating skill (implementing/SKILL.md) is the sole writer:
- Updates task completion status after successful merge
- Updates implementation-log.md after each agent completes
- Updates .meta.json phase tracking after all tasks done

This is already the current behavior — implementer agents produce reports that the orchestrator consumes. No code change needed for this constraint; it's a documented invariant.

### TD-4: /security-review Integration Mechanism

**CONSTRAINT:** CC slash commands cannot be invoked programmatically from skill/command markdown (CC docs confirm this). However, `/security-review` is an open-source reference implementation that can be copied to `.claude/commands/security-review.md` in the project. Once present, the orchestrating agent CAN invoke it via natural language instruction.

**Implementation path:**
1. Copy `security-review.md` from `anthropics/claude-code-security-review` to the project's `.claude/commands/` directory (one-time setup, or pd could auto-scaffold this)
2. Add instruction block to Step 5a in both `finish-feature.md` and `wrap-up.md`:

```markdown
### Step 5a-bis: Security Review

After all discovered project checks pass:

1. Instruct the orchestrating agent: "Run /security-review to analyze pending changes for security vulnerabilities."
2. The agent invokes the command if `.claude/commands/security-review.md` exists in the project.
3. If critical/high severity findings: treat as blocking failure (same auto-fix loop as other checks).
4. If the command is not found or fails: output "security-review not available, skipping" and proceed.
```

**Note:** This requires the project to have the security-review command installed. pd could auto-detect and scaffold it during session-start, or document it as a prerequisite.

### TD-5: Graceful Degradation Pattern (Universal)

All CC native integrations follow:
```
try_native_feature()
  → success: use result
  → unavailable/error: log warning, continue with previous behavior
  → never: block workflow on CC native feature failure
```

This matches existing patterns in pd (capture-tool-failure.sh, yolo-guard.sh fast path).

## Interfaces

### I1: Implementing Skill Dispatch Interface (modified)

**Current interface** (SKILL.md Step 2b):
```yaml
Task:
  description: "Implement task {N}: {title}"
  subagent_type: pd:implementer
  model: opus
  prompt: |
    {task context and instructions}
```

**New interface** (manual worktree due to CC Issue #33045):
```yaml
# Phase 1: Create worktrees (Bash tool, before agent dispatch)
Bash: |
  for N in {task_numbers}; do
    git worktree add .pd-worktrees/task-$N -b worktree-{feature_id}-task-$N
  done

# Phase 2: Dispatch agents (multiple Agent calls in single message)
Agent:
  description: "Implement task {N}: {title}"
  subagent_type: pd:implementer
  model: opus
  prompt: |
    WORKTREE INSTRUCTIONS:
    Work ONLY in: {abs_project_root}/.pd-worktrees/task-{N}/
    Use absolute paths for ALL Read, Edit, Write, Glob, Grep operations.
    Run `cd {worktree_path}` before any Bash commands.
    Do NOT modify files outside your worktree directory.
    Do NOT modify .meta.json.

    {task context and instructions}

# Phase 3: Merge (Bash tool, after all agents complete)
Bash: |
  for N in {task_numbers_in_order}; do
    git merge worktree-{feature_id}-task-$N || { echo "CONFLICT on task $N"; exit 1; }
    git worktree remove .pd-worktrees/task-$N
  done
```

**Batch dispatch pattern** (replaces serial loop):
```
tasks = parse_unchecked_tasks(tasks_md)
batch_size = min(len(tasks), max_concurrent_agents)

for batch in chunk(tasks, batch_size):
    # Phase 1: Create worktrees
    create_worktrees(batch)

    # Phase 2: Dispatch all in batch simultaneously
    results = dispatch_parallel(batch)  # no isolation param needed

    # Phase 3: Merge sequentially, cleanup
    for task, result in zip(batch, results):
        merge_result = git_merge(result.branch, feature_branch)
        if merge_result.conflict:
            surface_conflict(merge_result)
            HALT
        cleanup_worktree(result)
        update_implementation_log(task, result)
```

### I2: Pre-Merge Security Check Interface (new step in existing pipeline)

**Insertion point:** After Step 5a check loop completes successfully, before executing merge/PR.

**Interface:** Natural language instruction in command markdown. No programmatic API.

```markdown
# In finish-feature.md and wrap-up.md, after Step 5a passes:

6. **Security Review (CC Native)**
   Run `/security-review` to check for security vulnerabilities in pending changes.
   - If critical/high findings: treat as Step 5a failure, enter auto-fix loop
   - If command unavailable: skip with warning, proceed to merge/PR
```

### I3: Behavioral Regression Test Interface (new test file)

**Location:** `plugins/pd/hooks/tests/test-workflow-regression.sh`

**Test cases:**

```bash
# Test 1: Entity DB state after task completion
test_entity_state_after_task_completion() {
    # Setup: create mock feature, register task entities
    # Action: simulate task completion via MCP register_entity(status=completed)
    # Assert: entity DB contains task with status=completed
}

# Test 2: .meta.json after finish-feature
test_meta_json_after_completion() {
    # Setup: create mock feature with .meta.json (status=active)
    # Action: call complete_phase(feature_type_id, "finish")
    # Assert: .meta.json has status=completed, completed timestamp non-null
}

# Test 3: Phase transition guards
test_phase_transition_guards() {
    # Setup: create mock feature, complete specify phase
    # Assert: transition_phase(target=design) succeeds
    # Assert: transition_phase(target=implement) fails (design not completed)
}
```

### I4: SQLite Concurrency Spike Interface (new test file)

**Location:** `plugins/pd/hooks/tests/test-sqlite-concurrency.sh`

```bash
# Creates 3 git worktrees, runs parallel entity writes from each
test_parallel_worktree_entity_writes() {
    # Setup: create temp repo, init 3 worktrees, create test DB
    # Action: spawn 3 background processes, each writing 10 entities
    #         with WAL mode + retry (100ms, 500ms, 2s backoff)
    # Assert: all 30 entities present in DB
    # Assert: zero data corruption (entity count matches, no duplicates)
    # Report: lock contention count, retry count, wall-clock time
}
```

### I5: Context-Forked Research Interface (stretch, modifies SKILL.md frontmatter)

**Current frontmatter** (researching/SKILL.md):
```yaml
---
name: researching
description: Orchestrates parallel research...
---
```

**New frontmatter:**
```yaml
---
name: researching
description: Orchestrates parallel research...
context: fork
agent: general-purpose
---
```

**Caveat:** `context: fork` makes the ENTIRE skill run in a forked context. The skill's Phase 1 parallel dispatches would then be nested agents within the fork. This may or may not work — REQ-5 acceptance criteria require verification. If forking the whole skill is incompatible (e.g., MCP access lost), the alternative is to keep the skill inline but wrap Phase 1 dispatches individually with `context: fork` comments (not currently supported as a per-dispatch option).

### I6: CronCreate Doctor Scheduling (stretch, modifies session-start.sh)

**Config field** (in `pd.local.md`):
```yaml
doctor_schedule: ""  # cron expression, e.g., "0 */4 * * *" for every 4 hours
```

**Session-start integration:**
```bash
# In session-start.sh, after config injection:
DOCTOR_SCHEDULE=$(read_local_md_field "$PD_CONFIG" "doctor_schedule" "")
if [[ -n "$DOCTOR_SCHEDULE" ]]; then
    # Output instruction for CronCreate (hook cannot invoke tools directly)
    # Include in additionalContext for the agent to act on
    echo "Schedule pd:doctor with cron: $DOCTOR_SCHEDULE"
fi
```

**Note:** Hooks output `additionalContext` strings, not tool calls. The CronCreate invocation must be an instruction to the agent, not a direct hook action. This is the same pattern as TD-4.

## Risks & Mitigations

| Risk | Component | Mitigation |
|------|-----------|------------|
| `isolation: worktree` silently ignored for plugin agents (CC #33045) | C1 | Manual worktree creation workaround; track CC issue for fix |
| SQLite locks under parallel writes | C1 | Phase 0 spike (C4) validates before commitment; WAL + busy_timeout + retry |
| Agents ignore worktree path directives | C1 | Absolute path prefix in prompt; validate in spike that Read/Edit honor paths |
| Merge conflicts between worktree agents | C1 | Halt-and-surface (TD-2); user resolves manually |
| `/security-review` command not installed in project | C2 | Auto-detect `.claude/commands/security-review.md`; skip if missing |
| `context: fork` drops MCP access | C5 | Verify in spike; user approval if capabilities lost |
| CronCreate disabled by env var | C6 | Skip silently; doctor still runs at session start |

## Dependency Graph

```
C4 (SQLite spike) ───┐
                     ├──→ C1 (worktree dispatch) ──→ C3 (regression tests, post-validation)
C3 (regression tests, baseline) ──┘
C2 (/security-review) ── independent
C5 (context: fork) ── independent stretch
C6 (CronCreate) ── independent stretch
```

**Implementation order:** C4 → C3 (baseline) → C1 → C3 (post-validation) → C2 → C5 → C6
