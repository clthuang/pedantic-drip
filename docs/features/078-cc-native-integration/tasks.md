# Tasks: CC Native Feature Integration

## Task Group 0: SQLite Concurrency Spike (C4)
*Depends on: nothing | Blocks: Group 2*

- [ ] T0.1: Create `test-sqlite-concurrency.sh` skeleton with setup (temp repo, 3 worktrees) and teardown
  - **DoD:** Script creates 3 git worktrees from a temp repo, cleans up on exit
  - **File:** `plugins/pd/hooks/tests/test-sqlite-concurrency.sh`

- [ ] T0.2: Implement parallel entity write test — 3 processes, 10 entities each, WAL + busy_timeout=15000
  - **DoD:** Script spawns 3 background processes writing entities via Python entity_registry library (bypassing MCP); waits for all; asserts 30 entities in DB
  - **File:** `plugins/pd/hooks/tests/test-sqlite-concurrency.sh`

- [ ] T0.3: Add contention metrics collection and document results
  - **DoD:** Script reports success rate, retry count, wall-clock time. Results written to `docs/features/078-cc-native-integration/spike-results.md`
  - **File:** `plugins/pd/hooks/tests/test-sqlite-concurrency.sh`, `docs/features/078-cc-native-integration/spike-results.md`

- [ ] T0.4: Agent path compliance spike — manual test with documented procedure
  - **Procedure:** (1) Create temp feature dir and worktree: `git worktree add .pd-worktrees/spike-test -b spike-test`. (2) Record SHA: `BEFORE=$(git rev-parse HEAD)`. (3) In a CC session, dispatch an Agent with prompt: "Work ONLY in {abs_path}/.pd-worktrees/spike-test/. Use absolute paths for ALL Read/Edit/Write/Glob/Grep. Create a file called spike-marker.txt with content 'hello'." (4) After agent completes: `git rev-parse HEAD` must equal `$BEFORE`; `git diff --name-only` must be empty; `.pd-worktrees/spike-test/spike-marker.txt` must exist. (5) Cleanup: `git worktree remove .pd-worktrees/spike-test`.
  - **DoD:** Results recorded in `spike-results.md`: agent path compliance = pass/fail + evidence (git commands output).
  - **Note:** Manual test (~30 min). If agent does not comply, worktree approach is blocked.

## Task Group 1: Behavioral Regression Tests Baseline (C3-a)
*Depends on: nothing | Blocks: Group 2*

- [ ] T1.1: Create `test-workflow-regression.sh` skeleton with mock feature setup/teardown
  - **DoD:** Script creates temp dir with mock feature folder + .meta.json, temp entity DB; cleans up on exit
  - **File:** `plugins/pd/hooks/tests/test-workflow-regression.sh`

- [ ] T1.2: Test entity DB state after task entity registration
  - **DoD:** Test registers task entity via Python library, asserts entity exists with correct status in DB
  - **File:** `plugins/pd/hooks/tests/test-workflow-regression.sh`

- [ ] T1.3: Test .meta.json state after complete_phase
  - **DoD:** Test calls workflow state server's complete_phase via Python library: `plugins/pd/.venv/bin/python -c "from workflow_state.server import complete_phase_impl; ..."` (bypasses MCP, calls underlying function directly). Asserts .meta.json has status=completed and non-null completed timestamp.
  - **File:** `plugins/pd/hooks/tests/test-workflow-regression.sh`
  - **Note:** All regression tests use plugin venv Python directly, not MCP server calls. This matches existing test patterns.

- [ ] T1.4: Test phase transition guards (valid + invalid)
  - **DoD:** Test asserts transition_phase(target=design) succeeds after specify; transition_phase(target=implement) fails before design
  - **File:** `plugins/pd/hooks/tests/test-workflow-regression.sh`

- [ ] T1.5: Run baseline — all tests pass on current code
  - **DoD:** `bash test-workflow-regression.sh` exits 0 with all tests passing

## Task Group 2: Worktree Parallel Dispatch (C1)
*Depends on: Group 0 (pass), Group 1 (baseline) | Blocks: Group 2-post*

- [ ] T2.0: Create `test-worktree-dispatch.sh` with git worktree mechanics tests (TDD: tests first)
  - **DoD:** Tests verify: worktree creation + cleanup roundtrip, sequential merge of 2 branches, SHA-based stray-commit detection, fallback on worktree add failure. All pass.
  - **File:** `plugins/pd/hooks/tests/test-worktree-dispatch.sh`
  - **Note:** Tests exercise git mechanics only (no agent dispatch). Uses plugin venv Python for entity DB assertions.

- [ ] T2.1: Add `.pd-worktrees/` to `.gitignore` and document in CLAUDE.md
  - **DoD:** `.gitignore` contains `.pd-worktrees/`; CLAUDE.md has a note about worktree directory

- [ ] T2.2: Modify implementing/SKILL.md Step 2 — add Phase 1 worktree creation
  - **DoD:** Step 2 creates worktrees with `git worktree add .pd-worktrees/task-{N} -b worktree-{feature_id}-task-{N}` for each task in batch
  - **File:** `plugins/pd/skills/implementing/SKILL.md`

- [ ] T2.3: Modify implementing/SKILL.md Step 2 — add worktree-aware prompt directives
  - **DoD:** Each implementer agent prompt includes absolute worktree path instructions and .meta.json write prohibition
  - **File:** `plugins/pd/skills/implementing/SKILL.md`

- [ ] T2.4: Modify implementing/SKILL.md Step 2 — dispatch in parallel (multiple Agent calls in single message)
  - **DoD:** Step 2 dispatches up to `max_concurrent_agents` agents simultaneously instead of serially
  - **File:** `plugins/pd/skills/implementing/SKILL.md`

- [ ] T2.5: Add Phase 3 — SHA-based post-agent validation
  - **DoD:** After agents complete, verify `git rev-parse HEAD` unchanged on feature branch; flag stray commits
  - **File:** `plugins/pd/skills/implementing/SKILL.md`

- [ ] T2.6: Add Phase 3 — sequential merge with halt-on-conflict
  - **DoD:** Merge worktree branches in task order; halt and surface conflict details if merge fails
  - **File:** `plugins/pd/skills/implementing/SKILL.md`

- [ ] T2.7: Add Phase 3 — worktree cleanup after successful merge
  - **DoD:** `git worktree remove` called after each successful merge; failed merges leave worktree for debugging
  - **File:** `plugins/pd/skills/implementing/SKILL.md`

- [ ] T2.8: Add fallback logic — per-task worktree creation failure
  - **DoD:** If `git worktree add` fails for a task, that task dispatches without worktree; others continue in worktrees
  - **File:** `plugins/pd/skills/implementing/SKILL.md`

- [ ] T2.9: Add fallback logic — full-serial on SQLite failure detection
  - **DoD:** After batch, if any agent report contains SQLite BUSY errors, remaining batches switch to serial (no worktree)
  - **File:** `plugins/pd/skills/implementing/SKILL.md`

- [ ] T2.10: Add worktree resume detection on re-entry
  - **DoD:** On Step 2 entry, check `git worktree list` for `worktree-{feature_id}-task-*` branches; skip creation for existing, proceed to merge
  - **File:** `plugins/pd/skills/implementing/SKILL.md`

- [ ] T2.11: Add orphaned worktree cleanup to doctor health checks
  - **DoD:** New check function in `plugins/pd/hooks/lib/doctor/checks.py`: scans `.pd-worktrees/` directory, cross-references with `git worktree list`, returns issues for orphaned worktrees. Doctor output includes "stale_worktrees" check.
  - **File:** `plugins/pd/hooks/lib/doctor/checks.py`

## Task Group 2-post: Regression Validation
*Depends on: Group 2*

- [ ] T2.12: Run regression tests post-integration — all baseline tests still pass
  - **DoD:** `bash test-workflow-regression.sh` exits 0 with all tests passing after C1 changes

## Task Group 3: Security Review Pre-Merge (C2)
*Depends on: nothing (independent)*

- [ ] T3.1: Bundle security-review.md template from anthropics/claude-code-security-review
  - **Retrieval:** `curl -o plugins/pd/references/security-review.md https://raw.githubusercontent.com/anthropics/claude-code-security-review/main/.claude/commands/security-review.md`
  - **DoD:** File exists at `plugins/pd/references/security-review.md` with SHA comment on line 1: `<!-- Source: anthropics/claude-code-security-review @ {commit-SHA} -->`
  - **File:** `plugins/pd/references/security-review.md`

- [ ] T3.2: Add doctor health check for `.claude/commands/security-review.md`
  - **DoD:** Doctor warns if file missing: "security-review command not installed"
  - **File:** `plugins/pd/commands/doctor.md` or doctor module

- [ ] T3.3: Add Step 5a-bis to finish-feature.md
  - **DoD:** After existing checks pass, instruction tells agent to run `/security-review`; graceful skip if unavailable
  - **File:** `plugins/pd/commands/finish-feature.md`

- [ ] T3.4: Add identical Step 5a-bis to wrap-up.md
  - **DoD:** Same instruction block as T3.3 in wrap-up command
  - **File:** `plugins/pd/commands/wrap-up.md`

## Task Group 4: Context Fork Research (C5, Stretch)
*Depends on: nothing (independent stretch)*

- [ ] T4.1: Spike — test context: fork with a minimal skill
  - **Procedure:** (1) Create `plugins/pd/skills/test-fork/SKILL.md` with frontmatter `---\nname: test-fork\ncontext: fork\nagent: general-purpose\n---\nOutput the string FORK_VERIFIED.` (2) In a CC session, invoke the skill. (3) Verify main conversation receives "FORK_VERIFIED" output. (4) Clean up test skill after verification.
  - **DoD:** spike-results.md records: context:fork = pass (output received) or fail (empty/error). Test skill deleted after verification.

- [ ] T4.2: Verify MCP server access from forked context
  - **DoD:** Forked skill successfully calls search_memory and register_entity, or documents that MCP is inaccessible

- [ ] T4.3: If verified — add context: fork to researching/SKILL.md
  - **DoD:** Researching skill frontmatter includes `context: fork` and `agent: general-purpose`; Phase 1 results surface correctly
  - **File:** `plugins/pd/skills/researching/SKILL.md`

## Task Group 5: CronCreate Doctor (C6, Stretch)
*Depends on: nothing (independent stretch)*

- [ ] T5.1: Add `doctor_schedule` field to config template
  - **DoD:** `plugins/pd/templates/config.local.md` includes `doctor_schedule:` field with documentation
  - **File:** `plugins/pd/templates/config.local.md`

- [ ] T5.2: Add CronCreate instruction to session-start.sh additionalContext
  - **DoD:** When `doctor_schedule` is non-empty, session-start outputs CronCreate instruction; skips silently if empty
  - **File:** `plugins/pd/hooks/session-start.sh`

- [ ] T5.3: Document in README_FOR_DEV.md
  - **DoD:** New config field documented with example cron expression
  - **File:** `README_FOR_DEV.md`
