# Specification: CC Native Feature Integration

## Overview

Integrate Claude Code native features into pd plugin to enable parallel implementation via worktree isolation, add `/security-review` to pre-merge validation, and prepare stretch integrations for `context: fork` and CronCreate. All integrations must degrade gracefully when CC native features are unavailable or changed.

## Scope

### In Scope
- FR-0: SQLite concurrency spike (Phase 0 gate for worktree isolation)
- FR-1: Worktree isolation for implementing skill's parallel task dispatch
- FR-2: `/security-review` integration in pre-merge validation
- FR-5: Behavioral regression test suite for workflow phases
- FR-3: `context: fork` for researching skill (stretch)
- FR-4: CronCreate for scheduled doctor (stretch)

### Out of Scope
- `/batch` integration (no candidates in pd codebase)
- Monitor tool integration (no long-running operations identified)
- Replacing MCP memory-server with CC native auto-memory
- Replacing entity registry or workflow engine

## Requirements

### REQ-1: SQLite Concurrency Spike (FR-0)

**What:** Run a controlled test with 3 parallel worktree agents writing to entity DB simultaneously under WAL mode + retry logic.

**Acceptance Criteria:**
- [ ] Test script creates 3 actual git worktrees, each running entity writes from their own worktree directory to the shared global `~/.claude/pd/entities/entities.db`
- [ ] Test covers BOTH scenarios: (a) writes via shared MCP server instance, (b) writes via separate MCP server instances per worktree (simulating real worktree-agent topology where MCP servers are NOT isolated by worktree)
- [ ] Each process writes 10 entity records under WAL mode (already default) with retry-on-SQLITE_BUSY (3 retries, exponential backoff: 100ms, 500ms, 2s)
- [ ] Results documented: success rate, lock contention count, any data corruption, MCP instance behavior
- [ ] If success rate < 100%: FR-1 is BLOCKED with documented failure mode
- [ ] If success rate == 100%: FR-1 proceeds with documented WAL + retry as the concurrency strategy
- [ ] Test script added to `plugins/pd/hooks/tests/` as `test-sqlite-concurrency.sh`

### REQ-2: Worktree Isolation for Implementing Skill (FR-1)

**What:** Modify implementing skill to dispatch implementer agents with `isolation: "worktree"` for parallel execution.

**Precondition:** REQ-1 passes (100% success rate).

**Acceptance Criteria:**
- [ ] `plugins/pd/skills/implementing/SKILL.md` Step 2 dispatch block includes `isolation: "worktree"` on each Agent/Task tool call (CC's Agent tool schema accepts `isolation` as an inline parameter — verified in tool definition: `"isolation": {"enum": ["worktree"]}`). Alternative path: agent frontmatter in `.claude/agents/pd-implementer.md` with `isolation: worktree` field. Prefer inline parameter to avoid requiring a separate agent definition file.
- [ ] Dispatch model changes from serial (one-at-a-time) to parallel (up to `max_concurrent_agents` simultaneous agents)
- [ ] After all parallel agents complete, worktree branches are merged sequentially to the feature branch
- [ ] Worktree creation failure: per-task fallback (that specific task dispatches without isolation; remaining tasks continue in worktrees). Distinct from SQLite concurrency failure: if entity DB writes fail after 3 retries with exponential backoff, ALL remaining tasks fall back to serial dispatch (full serial fallback).
- [ ] If merge conflict occurs, implementing skill halts with conflict details surfaced to main conversation and user prompted for resolution
- [ ] `.worktreeinclude` documentation added to CLAUDE.md noting that projects using worktree-parallel implementation should list gitignored files needed by build/test

**Behavioral Constraints:**
- Entity DB writes from worktree agents MUST use WAL mode + retry (inherited from existing DB connection setup)
- `.meta.json` updates MUST NOT happen from worktree agents — only the orchestrating skill updates `.meta.json` after merge
- Worktree branches MUST be cleaned up after successful merge (git worktree remove)

### REQ-3: `/security-review` in Pre-Merge Validation (FR-2)

**What:** Add CC's native `/security-review` as an additional check in the pre-merge validation pipeline (Step 5a) of finish-feature and wrap-up commands.

**Acceptance Criteria:**
- [ ] `plugins/pd/commands/finish-feature.md` Step 5a adds `/security-review` invocation after discovered project checks pass
- [ ] `plugins/pd/commands/wrap-up.md` Step 5a adds identical `/security-review` invocation
- [ ] Invocation verification spike: before full integration, confirm that the orchestrating agent can invoke `/security-review` from command markdown. Test: add a temporary instruction in finish-feature.md and verify it executes in a test session.
- [ ] Primary mechanism: natural language instruction in command markdown ("Run `/security-review` to check pending changes"). Fallback if invocation fails: skip with warning (graceful degradation per TD-4)
- [ ] If `/security-review` reports critical vulnerabilities: treated as blocking failure (same as other check failures)
- [ ] If `/security-review` is unavailable (command not found, invocation fails, plugin not installed): skip with warning "security-review not available, skipping", do NOT block merge
- [ ] Does NOT modify implement.md's existing security-reviewer agent dispatch

**Behavioral Constraints:**
- `/security-review` runs AFTER project-specific checks (validate.sh, tests) pass — not before
- Token cost acknowledged: `/security-review` adds ~5-15K tokens per invocation; acceptable for pre-merge (runs once per feature, not per iteration)

### REQ-4: Behavioral Regression Test Suite (FR-5)

**What:** Create automated test suite verifying workflow phase outcomes are preserved after integrations.

**Acceptance Criteria:**
- [ ] Test file: `plugins/pd/hooks/tests/test-workflow-regression.sh`
- [ ] Tests cover 3 phase outcomes:
  - (a) implement phase: after simulating task completion (direct MCP calls: `register_entity(type=task, status=completed)`), entity DB contains task entities with `status=completed`
  - (b) finish-feature: after calling `complete_phase(feature_type_id, "finish")`, `.meta.json` has `status=completed` and non-null `completed` timestamp
  - (c) phase transitions: `transition_phase(target_phase="design")` succeeds after specify completes; `transition_phase(target_phase="implement")` before design fails with guard error
- [ ] Tests use existing test infrastructure patterns (setup/teardown, temp dirs with mock feature folders, `log_test`/`log_pass`/`log_fail`)
- [ ] Tests require test fixtures: mock feature dir with `.meta.json`, mock entity DB entries (created via `register_entity` calls in setup)
- [ ] Baseline = committed test assertions that pass on current code. "Before" means tests pass before FR-1/FR-2. "After" means same tests still pass post-integration.
- [ ] Tests pass both before and after integration changes
- [ ] Tests added to main test runner or runnable standalone

### REQ-5: `context: fork` for Researching Skill (FR-3, Stretch)

**What:** Convert researching skill Phase 1 parallel Task dispatches to use `context: fork` frontmatter for automatic context isolation.

**Acceptance Criteria:**
- [ ] Researching skill Phase 1 agents (codebase-explorer, internet-researcher) execute in forked context
- [ ] Results from forked execution surface to main conversation with same quality as current Task dispatch
- [ ] MCP server access verified: confirm forked agents can access entity-registry and memory-server
- [ ] If MCP servers are NOT accessible from forked context: document the lost capabilities (memory search, influence tracking) and get explicit user approval before proceeding — this is a feature regression, not an acceptable silent adaptation
- [ ] If `context: fork` is not honored by CC runtime: skill falls back to current inline Task dispatch with no user-visible error
- [ ] No degradation in research output quality (validated by manual comparison on 2 test cases)

### REQ-6: CronCreate for Scheduled Doctor (FR-4, Stretch)

**What:** Add optional desktop-tier CronCreate scheduling for pd:doctor health checks.

**Acceptance Criteria:**
- [ ] New config field in `pd.local.md`: `doctor_schedule` (cron expression, default: empty/disabled)
- [ ] If `doctor_schedule` is set: session-start.sh invokes CronCreate with the configured schedule
- [ ] Scheduled doctor runs use desktop scheduling tier (local file access required)
- [ ] If CronCreate is unavailable (`CLAUDE_CODE_DISABLE_CRON=1`): skip silently, log to debug
- [ ] Doctor results from scheduled runs surface via CC notification system
- [ ] Config field documented in `README_FOR_DEV.md` and `plugins/pd/templates/config.local.md`

## Dependency Order

```
REQ-4 (regression tests) ──────────────────┐
                                            ├──→ REQ-2 (worktree isolation)
REQ-1 (SQLite spike) ──────────────────────┘
REQ-3 (/security-review) ─── independent, can proceed in parallel
REQ-5 (context: fork) ─── independent stretch, can proceed anytime
REQ-6 (CronCreate) ─── independent stretch, can proceed anytime
```

## Technical Decisions

### TD-1: Worktree Merge Strategy
Sequential merge after all parallel agents complete. Order: task document order (same as current serial dispatch). Branch naming: `worktree-{feature_id}-task-{N}` where N is the task number from tasks.md. Rationale: predictable merge order, matches existing task numbering, unique branch names aid debugging. If conflict on merge N, halt and surface all conflict details — do not attempt remaining merges. This is a deliberately conservative choice: conflict resolution may change the codebase in ways that affect subsequent merges. Future optimization: attempt remaining merges and surface all conflicts at once.

### TD-2: Entity DB Concurrency Strategy
WAL mode (already default) + retry-on-SQLITE_BUSY with exponential backoff (100ms → 500ms → 2s, 3 retries). Rationale: WAL allows concurrent reads during writes; retry handles brief lock contention. Validated by REQ-1 spike.

### TD-3: `/security-review` Invocation Mechanism
Natural language instruction in command markdown: "Run `/security-review` to check for security vulnerabilities in the pending changes." CC's orchestrating agent interprets this as a command invocation. Rationale: `/security-review` is a CC command, not a programmatic API — instruction-based invocation is the only integration path. Fallback: if agent cannot find the command, it skips with a warning.

### TD-4: Graceful Degradation Pattern
All CC native integrations follow the same pattern:
1. Attempt the native feature
2. If unavailable/fails: log warning, continue with previous behavior (serial dispatch, no security review, inline execution)
3. Never block workflow on CC native feature failure

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| SQLite locks under parallel worktree writes | Medium | High | FR-0 spike validates before commitment; WAL + retry |
| CC changes worktree behavior in future version | Low | Medium | Graceful degradation (TD-4); behavioral regression tests (REQ-4) |
| `/security-review` unavailable in some CC configurations | Medium | Low | Skip with warning; pre-merge not blocked |
| `context: fork` not inheriting MCP access | Medium | Medium | REQ-5 acceptance criteria includes MCP verification; fallback to inline |
| Worktree merge conflicts on overlapping tasks | Low | Medium | Halt-and-surface strategy (TD-1); user resolves manually |
