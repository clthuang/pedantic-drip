# Plan: CC Native Feature Integration

## Implementation Order

```
Phase 0: Spikes (SQLite concurrency + agent path compliance)
    ↓ (gate: both pass)
Phase 1: Regression test baseline
    ↓
Phase 2: Worktree parallel dispatch (TDD: tests → implement → verify)
    ↓
Phase 3: Security review pre-merge (independent, can parallel with Phase 2)
    ↓
Phase 4-5: Stretch goals (context: fork, CronCreate)
```

## Phase 0: Validation Spikes (C4 + path compliance)

**Why:** Two critical assumptions must be validated before committing to the worktree approach: (a) SQLite handles parallel writes from worktrees, (b) agents respect path directives.
**Why this order:** Cheapest to run, gates all subsequent work. No point building worktree dispatch if either fails.
**Complexity:** Medium

### Steps:
1. Create `test-sqlite-concurrency.sh` — 3 worktrees, parallel entity writes via plugin venv Python (`plugins/pd/.venv/bin/python -c "from entity_registry.database import EntityDB; ..."`)
2. Create agent path compliance test — dispatch a test agent with worktree path directive, verify it only modifies files within the worktree directory (check via `git diff --name-only` in main tree)
3. Document results in `spike-results.md`

**Done when:** Both tests pass. spike-results.md documents: SQLite success rate = 100%, agent path compliance = verified.
**Gate:** If either fails → feature blocked; document failure mode and stop.

**Key files:** `plugins/pd/hooks/tests/test-sqlite-concurrency.sh`, `docs/dev_artifacts/workitems/078-cc-native-integration/spike-results.md`

## Phase 1: Behavioral Regression Tests Baseline (C3-a)

**Why:** Need a baseline proving current workflow behavior is correct before modifying it (REQ-4, spec).
**Why this order:** Must run BEFORE Phase 2 changes; captures "before" assertions.
**Complexity:** Medium

### Steps:
1. Create `test-workflow-regression.sh` with mock feature setup/teardown
2. Tests invoke entity DB via plugin venv Python (same mechanism as spike: `plugins/pd/.venv/bin/python`)
3. Test cases: entity state after registration, .meta.json after complete_phase, phase transition guards
4. Run baseline — all tests pass on current code

**Done when:** `bash test-workflow-regression.sh` exits 0 with all tests passing.

**Key files:** `plugins/pd/hooks/tests/test-workflow-regression.sh`

## Phase 2: Worktree Parallel Dispatch (C1)

**Why:** Core feature — enables parallel implementation via worktree isolation (FR-1).
**Why this order:** Gated by Phase 0 (spikes pass) and Phase 1 (baseline captured).
**Complexity:** Complex — largest change, most risk.

**Implementation form:** Changes to `implementing/SKILL.md` are embedded Bash code blocks within the markdown skill instructions (same pattern as existing `git add`, `git commit` blocks in workflow-transitions). Prose instructions tell the orchestrating agent when to execute each phase. Worktree management helper script (`.sh`) keeps SKILL.md readable.

### Steps (TDD order):
1. **Tests first:** Create `test-worktree-dispatch.sh` with test cases for:
   - Worktree creation + cleanup (git worktree add/remove roundtrip)
   - Sequential merge of 2 worktree branches
   - SHA-based stray-commit detection
   - Fallback on worktree creation failure
   - These test the git mechanics, not the agent dispatch itself
2. Add `.pd-worktrees/` to project `.gitignore` at runtime (SKILL.md Phase 1 checks and adds if missing)
3. Modify `implementing/SKILL.md` Step 2 with 3 phases:
   - Phase 1: Bash blocks for worktree creation
   - Phase 2: Multiple Agent tool calls in single message (parallel dispatch pattern from researching skill)
   - Phase 3: SHA validation + sequential merge + cleanup
4. Add fallback prose: per-task worktree failure, full-serial SQLite fallback (detected from agent reports)
5. Add worktree resume detection (check `git worktree list` on entry)
6. Add orphaned worktree cleanup to doctor checks
7. **Verify:** Run regression tests (Phase 1 baseline still passes) + manual 2-task parallel dispatch test

**Done when:** implementing/SKILL.md updated, test-worktree-dispatch.sh passes, regression tests pass, manual smoke test of parallel dispatch succeeds on a test feature.

**Key files:**
- `plugins/pd/hooks/tests/test-worktree-dispatch.sh` (new)
- `plugins/pd/skills/implementing/SKILL.md`
- `plugins/pd/commands/doctor.md`

## Phase 3: Security Review Pre-Merge (C2)

**Why:** Defense-in-depth — catches vulnerabilities even if implement review loop was skipped (FR-2).
**Why this order:** Independent of Phase 2; can proceed in parallel. Simple markdown additions.
**Complexity:** Simple

### Steps:
1. Copy `security-review.md` from `anthropics/claude-code-security-review` (current version, note commit SHA in comment). Save to `plugins/pd/references/security-review.md`
2. Add doctor health check: warn if `.claude/commands/security-review.md` missing in project
3. Add Step 5a-bis to `finish-feature.md`: "Run `/security-review`" instruction with graceful skip
4. Add identical Step 5a-bis to `wrap-up.md`

**Done when:** Both commands include security-review instruction; doctor warns if command file missing.

**Key files:** `plugins/pd/references/security-review.md`, `plugins/pd/commands/finish-feature.md`, `plugins/pd/commands/wrap-up.md`, `plugins/pd/commands/doctor.md`

## Phase 4: Context Fork Research (C5, Stretch)

**Why:** Context window savings for research agents (FR-3, stretch).
**Why this order:** After core features; spike-first to validate feasibility.
**Complexity:** Medium (spike-dependent)

### Steps:
1. Spike: test `context: fork` with minimal skill, verify return mechanism
2. Verify MCP server access from forked context
3. If both pass: add frontmatter to `researching/SKILL.md`
4. Manual quality comparison on 2 test cases

**Done when:** Researching skill uses context: fork with equivalent output quality, OR spike documents why it's infeasible and feature is deferred.

## Phase 5: CronCreate Doctor (C6, Stretch)

**Why:** Automated health monitoring without manual invocation (FR-4, stretch).
**Why this order:** Lowest priority; simple config plumbing.
**Complexity:** Simple

### Steps:
1. Add `doctor_schedule` field to config template
2. Add CronCreate instruction to session-start.sh additionalContext
3. Document in README_FOR_DEV.md

**Done when:** Non-empty `doctor_schedule` triggers CronCreate instruction at session start.
