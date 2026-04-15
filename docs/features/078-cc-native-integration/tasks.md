# Tasks: CC Native Feature Integration

**Feature:** 078-cc-native-integration
**Plan:** plan.md
**Created:** 2026-04-12

## Stage 0: SQLite Concurrency Spike (C4)

### Task 0.1: Create test-sqlite-concurrency.sh skeleton
**File:** `plugins/pd/hooks/tests/test-sqlite-concurrency.sh`
**Change:** Create bash script skeleton with setup (temp repo, 3 git worktrees) and teardown (cleanup on exit via trap).
**Done:** Script creates 3 git worktrees from a temp repo, cleans up on exit
**Depends on:** none

### Task 0.2: Implement parallel entity write test
**File:** `plugins/pd/hooks/tests/test-sqlite-concurrency.sh`
**Change:** Extend skeleton with 3-process parallel entity write test (10 entities each, WAL + busy_timeout=15000). Use Python entity_registry library directly (bypassing MCP). Wait for all processes; assert 30 entities in DB.
**Done:** Script spawns 3 background processes writing entities; waits for all; asserts 30 entities in DB
**Depends on:** Task 0.1

### Task 0.3: Add contention metrics and document results
**File:** `plugins/pd/hooks/tests/test-sqlite-concurrency.sh`, `docs/features/078-cc-native-integration/spike-results.md`
**Change:** Add metrics collection (success rate, retry count, wall-clock time) to script. Create spike-results.md with format template and run the script, writing results.
**Done:** Script reports success rate, retry count, wall-clock time. Results written to spike-results.md
**Depends on:** Task 0.2

### Task 0.4: Agent path compliance spike (manual)
**File:** `docs/features/078-cc-native-integration/spike-results.md`
**Change:** Document as blocked-manual. Add section to spike-results.md explaining manual procedure: (1) create `.pd-worktrees/spike-test` via `git worktree add`, (2) record `BEFORE=$(git rev-parse HEAD)`, (3) dispatch Agent with absolute-path prompt to create spike-marker.txt, (4) verify HEAD unchanged + marker exists, (5) cleanup. Mark status as "requires human verification in interactive CC session".
**Done:** spike-results.md has agent-path-compliance section with full procedure and status=blocked-manual
**Depends on:** none

## Stage 1: Behavioral Regression Tests Baseline (C3-a)

### Task 1.1: Create test-workflow-regression.sh skeleton
**File:** `plugins/pd/hooks/tests/test-workflow-regression.sh`
**Change:** Create bash script skeleton with mock feature setup (temp dir with mock feature folder + .meta.json, temp entity DB) and teardown.
**Done:** Script creates temp dir with mock feature folder + .meta.json, temp entity DB; cleans up on exit
**Depends on:** none

### Task 1.2: Test entity DB state after task entity registration
**File:** `plugins/pd/hooks/tests/test-workflow-regression.sh`
**Change:** Add test that registers a task entity via Python `entity_registry` library and asserts entity exists with correct status in DB.
**Done:** Test registers task entity via Python library, asserts entity exists with correct status in DB
**Depends on:** Task 1.1

### Task 1.3: Test .meta.json state after complete_phase
**File:** `plugins/pd/hooks/tests/test-workflow-regression.sh`
**Change:** Add test that calls workflow state server's complete_phase via plugin venv Python directly (not MCP): `plugins/pd/.venv/bin/python -c "from workflow_state.server import complete_phase_impl; ..."`. Assert .meta.json has status=completed and non-null completed timestamp.
**Done:** Test invokes complete_phase_impl via venv Python; .meta.json asserts pass
**Depends on:** Task 1.1

### Task 1.4: Test phase transition guards (valid + invalid)
**File:** `plugins/pd/hooks/tests/test-workflow-regression.sh`
**Change:** Add test: transition_phase(target=design) succeeds after specify; transition_phase(target=implement) fails before design.
**Done:** Test asserts valid transition succeeds and invalid transition fails with expected error
**Depends on:** Task 1.1

### Task 1.5: Run baseline and verify all tests pass on current code
**File:** (no new file; verify test execution)
**Change:** Run `bash plugins/pd/hooks/tests/test-workflow-regression.sh` and verify clean exit with all assertions passing. Fix any bugs in the tests discovered during baseline run.
**Done:** `bash test-workflow-regression.sh` exits 0 with all tests passing
**Depends on:** Task 1.2, Task 1.3, Task 1.4

## Stage 2: Worktree Parallel Dispatch (C1)

### Task 2.0: Create test-worktree-dispatch.sh with git worktree mechanics tests
**File:** `plugins/pd/hooks/tests/test-worktree-dispatch.sh`
**Change:** Create test script (TDD: tests first) that verifies: worktree creation + cleanup roundtrip, sequential merge of 2 branches, SHA-based stray-commit detection, fallback on worktree add failure. Tests exercise git mechanics only (no agent dispatch). Use plugin venv Python for entity DB assertions.
**Done:** All four test scenarios pass when run
**Depends on:** Task 0.3, Task 1.5

### Task 2.1: Add .pd-worktrees/ to .gitignore and document in CLAUDE.md
**File:** `.gitignore`, `CLAUDE.md`
**Change:** Append `.pd-worktrees/` to `.gitignore`. Add a note in CLAUDE.md explaining the worktree directory (used by implementing skill for parallel task dispatch; auto-cleaned after successful merges).
**Done:** `.gitignore` contains `.pd-worktrees/`; CLAUDE.md has note about worktree directory
**Depends on:** Task 2.0

### Task 2.2: Modify implementing/SKILL.md Step 2 — Phase 1 worktree creation
**File:** `plugins/pd/skills/implementing/SKILL.md`
**Change:** Modify Step 2 to add Phase 1 worktree creation. For each task in batch: `git worktree add .pd-worktrees/task-{N} -b worktree-{feature_id}-task-{N}`.
**Done:** Step 2 documents worktree creation per task in batch
**Depends on:** Task 2.1

### Task 2.3: Modify implementing/SKILL.md Step 2 — worktree-aware prompt directives
**File:** `plugins/pd/skills/implementing/SKILL.md`
**Change:** Update implementer dispatch prompt template to include absolute worktree path instructions and .meta.json write prohibition.
**Done:** Each implementer agent prompt includes absolute worktree path and .meta.json write prohibition
**Depends on:** Task 2.2

### Task 2.4: Modify implementing/SKILL.md Step 2 — dispatch in parallel
**File:** `plugins/pd/skills/implementing/SKILL.md`
**Change:** Update Step 2 to dispatch up to `max_concurrent_agents` agents simultaneously (multiple Task calls in single message) instead of serially.
**Done:** Step 2 dispatches up to max_concurrent_agents agents simultaneously
**Depends on:** Task 2.3

### Task 2.5: Add Phase 3 — SHA-based post-agent validation
**File:** `plugins/pd/skills/implementing/SKILL.md`
**Change:** Add Phase 3 to Step 2: after agents complete, verify `git rev-parse HEAD` unchanged on feature branch; flag stray commits.
**Done:** Phase 3 in SKILL.md validates HEAD unchanged and flags stray commits
**Depends on:** Task 2.4

### Task 2.6: Add Phase 3 — sequential merge with halt-on-conflict
**File:** `plugins/pd/skills/implementing/SKILL.md`
**Change:** Add merge step to Phase 3: merge worktree branches into feature branch in task order; halt and surface conflict details if merge fails.
**Done:** Phase 3 includes sequential merge with halt-on-conflict instruction
**Depends on:** Task 2.5

### Task 2.7: Add Phase 3 — worktree cleanup after successful merge
**File:** `plugins/pd/skills/implementing/SKILL.md`
**Change:** Add cleanup step: `git worktree remove` called after each successful merge; failed merges leave worktree for debugging.
**Done:** Phase 3 includes conditional worktree cleanup
**Depends on:** Task 2.6

### Task 2.8: Add fallback logic — per-task worktree creation failure
**File:** `plugins/pd/skills/implementing/SKILL.md`
**Change:** Add fallback: if `git worktree add` fails for a task, that task dispatches without worktree; other tasks in batch continue in worktrees.
**Done:** Per-task worktree creation failure fallback documented
**Depends on:** Task 2.7

### Task 2.9: Add fallback logic — full-serial on SQLite failure
**File:** `plugins/pd/skills/implementing/SKILL.md`
**Change:** Add batch-level fallback: after batch, if any agent report contains SQLite BUSY errors, remaining batches switch to serial (no worktree).
**Done:** Full-serial fallback on SQLite BUSY errors documented
**Depends on:** Task 2.8

### Task 2.10: Add worktree resume detection on re-entry
**File:** `plugins/pd/skills/implementing/SKILL.md`
**Change:** On Step 2 entry, check `git worktree list` for `worktree-{feature_id}-task-*` branches; skip creation for existing; proceed to merge.
**Done:** Step 2 entry includes resume detection
**Depends on:** Task 2.9

### Task 2.11: Add orphaned worktree cleanup to doctor health checks
**File:** `plugins/pd/hooks/lib/doctor/checks.py`
**Change:** Add new check function that scans `.pd-worktrees/` directory, cross-references with `git worktree list`, returns issues for orphaned worktrees. Doctor output includes "stale_worktrees" check.
**Done:** Doctor has stale_worktrees check that detects orphaned directories
**Depends on:** Task 2.10

### Task 2.12: Run regression tests post-integration
**File:** (no new file; verify test execution)
**Change:** Run `bash plugins/pd/hooks/tests/test-workflow-regression.sh` after all Stage 2 changes. Verify baseline tests still pass unchanged.
**Done:** `bash test-workflow-regression.sh` exits 0 with all tests passing after C1 changes
**Depends on:** Task 2.11

## Stage 3: Security Review Pre-Merge (C2)

### Task 3.1: Bundle security-review.md template
**File:** `plugins/pd/references/security-review.md`
**Change:** Retrieve template from upstream: `curl -o plugins/pd/references/security-review.md https://raw.githubusercontent.com/anthropics/claude-code-security-review/main/.claude/commands/security-review.md`. Add SHA provenance comment on line 1: `<!-- Source: anthropics/claude-code-security-review @ {commit-SHA} -->`.
**Done:** File exists with SHA provenance comment; content matches upstream
**Depends on:** none

### Task 3.2: Add doctor health check for security-review command
**File:** `plugins/pd/hooks/lib/doctor/checks.py`
**Change:** Add check that verifies `.claude/commands/security-review.md` exists in project. Warn if missing: "security-review command not installed".
**Done:** Doctor warns if `.claude/commands/security-review.md` missing
**Depends on:** Task 3.1

### Task 3.3: Add Step 5a-bis to finish-feature.md
**File:** `plugins/pd/commands/finish-feature.md`
**Change:** After existing pre-merge checks pass, add Step 5a-bis instructing the agent to run `/security-review`. Skip gracefully (warning log, don't block merge) if unavailable.
**Done:** finish-feature.md has Step 5a-bis with graceful-skip behavior
**Depends on:** Task 3.2

### Task 3.4: Add identical Step 5a-bis to wrap-up.md
**File:** `plugins/pd/commands/wrap-up.md`
**Change:** Add the same Step 5a-bis instruction block as Task 3.3 to wrap-up.md.
**Done:** wrap-up.md has identical Step 5a-bis block
**Depends on:** Task 3.3

## Stage 4: Context Fork Research (C5, Stretch)

### Task 4.1: Spike context:fork with minimal skill (manual)
**File:** `docs/features/078-cc-native-integration/spike-results.md`
**Change:** Document as blocked-manual. Add section explaining procedure: (1) create `plugins/pd/skills/test-fork/SKILL.md` with `context: fork` and `agent: general-purpose` frontmatter outputting "FORK_VERIFIED", (2) invoke in interactive CC session, (3) verify main conversation receives output, (4) delete test skill. Mark status as "requires human verification in interactive CC session".
**Done:** spike-results.md has context-fork section with procedure and status=blocked-manual
**Depends on:** none

### Task 4.2: Verify MCP server access from forked context (deferred)
**File:** `docs/features/078-cc-native-integration/spike-results.md`
**Change:** Document as deferred-pending-T4.1. After T4.1 is verified in interactive session, a follow-up spike confirms forked skill can call search_memory and register_entity. Add section noting dependency on T4.1 verification.
**Done:** spike-results.md has mcp-from-fork section marked deferred
**Depends on:** Task 4.1

### Task 4.3: If verified — add context:fork to researching/SKILL.md
**File:** `plugins/pd/skills/researching/SKILL.md`
**Change:** CONDITIONAL ON T4.1+T4.2 verification. Since T4.1 is blocked-manual, document in spike-results.md that this task is deferred pending manual verification. Do not modify researching/SKILL.md now. Add a note in spike-results.md recording the exact diff that WOULD be applied once verification completes.
**Done:** spike-results.md documents deferred modification with diff preview
**Depends on:** Task 4.2

## Stage 5: CronCreate Doctor (C6, Stretch)

### Task 5.1: Add doctor_schedule field to config template
**File:** `plugins/pd/templates/config.local.md`
**Change:** Add `doctor_schedule:` field to YAML frontmatter of config template with comment explaining cron expression format (e.g., `"0 */4 * * *"`). Default empty (disabled).
**Done:** Config template includes doctor_schedule field with documentation
**Depends on:** none

### Task 5.2: Add CronCreate instruction to session-start.sh
**File:** `plugins/pd/hooks/session-start.sh`
**Change:** When `doctor_schedule` is non-empty in project config, session-start.sh emits a CronCreate instruction block in additionalContext. Skip silently if empty or field absent.
**Done:** session-start.sh conditionally emits CronCreate instruction based on doctor_schedule config
**Depends on:** Task 5.1

### Task 5.3: Document in README_FOR_DEV.md
**File:** `README_FOR_DEV.md`
**Change:** Add section documenting doctor_schedule config field with example cron expression and explanation that it requires CronCreate availability (desktop tier).
**Done:** README_FOR_DEV.md documents doctor_schedule field and prerequisites
**Depends on:** Task 5.2
