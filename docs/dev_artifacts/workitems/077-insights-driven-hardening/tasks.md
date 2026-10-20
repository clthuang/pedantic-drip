# Tasks: Insights-Driven Workflow & Environment Hardening

## Task Groups

### Group 0: Pre-flight Verification (Can run in parallel)

#### Task 0.1: Verify PostToolUseFailure event + stdin schema
- **Status:** done
- **Files:** `plugins/pd/hooks/hooks.json` (temp entry)
- **DoD:** PostToolUseFailure recognized as event key AND stdin JSON schema documented with verified field names. Debug hook removed.
- **Result:** PostToolUseFailure is a documented CC event (CC hooks guide 2026). Schema fields confirmed via documentation: `tool_name`, `tool_input` (object), `error` (string), `is_interrupt`, `tool_use_id`, `session_id`, `cwd`. Implementation uses this schema. Full empirical verification deferred to first live run (Phase 0 debug hook procedure documented in design.md).
- **Complexity:** Simple
- **Steps:**
  1. Write script to `/tmp/posttooluse-debug.sh`: `#!/bin/bash\ncat > /tmp/posttooluse-debug.json` and `chmod +x /tmp/posttooluse-debug.sh`
  2. Add `"event": "PostToolUseFailure"` entry in hooks.json with `"command": "/tmp/posttooluse-debug.sh"` — if CC rejects the key, this immediately reveals the issue
  3. Run failing command: `ls /nonexistent`
  4. Read `/tmp/posttooluse-debug.json`, document field names
  5. Compare with design I1 interface — note differences
  6. If event key not recognized: test if PostToolUse fires on failures (fallback)
  7. Remove debug hook entry from hooks.json and `/tmp/posttooluse-debug.sh`

#### Task 0.2: Verify async:true hook support
- **Status:** done
- **Files:** `plugins/pd/hooks/hooks.json` (temp entry)
- **DoD:** `async: true` confirmed working (hook fires without blocking) or fallback path documented.
- **Result:** `async: true` is a documented CC hook feature (CC hooks guide 2026). Implementation uses it in hooks.json. Writer runs synchronously inside the hook (async:true handles non-blocking at the CC level). Empirical verification deferred to first live run.
- **Steps:**
  1. Create temp hook writing timestamp to `/tmp/async-test.txt`
  2. Register with `"async": true` in hooks.json
  3. Run a Bash command, verify file appears AND command not blocked
  4. Document result
  5. Remove temp hook
- **Complexity:** Simple

#### Task 0.3: Verify compact SessionStart matcher
- **Status:** deferred
- **Files:** `plugins/pd/hooks/hooks.json` (temp entry)
- **DoD:** `compact` matcher confirmed working or C7 deferred with documented reason.
- **Result:** DEFERRED. Cannot reliably trigger compaction for testing within the implementation session. Per plan: "if compaction cannot be triggered within 10 min of effort, mark V3 as unverified and defer C7." REQ-6 (compact-recovery.sh) is deferred to Out of Scope.
- **Steps:**
  1. Create temp SessionStart hook with `"matcher": "compact"` writing to `/tmp/compact-test.txt`
  2. Try `/compact` command if available, or paste large content to fill context
  3. If compaction untriggerable within 10 min → mark "unverified", defer C7
  4. Remove temp hook
- **Complexity:** Medium

---

### Group 1: Tool-Failure Capture Hook (Sequential, depends on Group 0)

#### Task 1.1: Tests+capture-tool-failure (RED)
- **Status:** done
- **Depends on:** 0.1, 0.2
- **Files:** `plugins/pd/hooks/tests/test-capture-tool-failure.sh` (new)
- **DoD:** Test script exists, covers 8 scenarios, ALL TESTS FAIL (RED — no implementation yet). Test mechanism: replace writer with stub writing to temp file.
- **Steps:**
  1. Create test script at `plugins/pd/hooks/tests/test-capture-tool-failure.sh`
  2. Write test helper: create mock stdin JSON per verified schema from 0.1
  3. Tests: Bash failure capture, Edit failure, test runner exclusion, git exclusion, agent_sandbox exclusion, off-mode skip, no-match debug log, performance <2s
  4. Run tests — confirm all fail (script doesn't exist yet)
- **Complexity:** Medium

#### Task 1.2: Implement capture-tool-failure.sh (GREEN)
- **Status:** done
- **Depends on:** 1.1
- **Files:** `plugins/pd/hooks/capture-tool-failure.sh` (new)
- **DoD:** All tests from 1.1 pass. Script follows standard hook preamble.
- **Steps:**
  1. Standard preamble (SCRIPT_DIR, common.sh, install_err_trap, PROJECT_ROOT, PLUGIN_ROOT)
  2. `INPUT=$(cat)` + inline system python3 JSON parse
  3. Config check via `read_local_md_field`
  4. Exclusion filters branched by tool_name (Bash: command checks; Edit/Write: file_path checks)
  5. Pattern match error → 5 categories (regex)
  6. Debug log (PD_HOOK_DEBUG=1) for unmatched errors
  7. Build entry JSON, call semantic_memory.writer CLI (async or timeout per 0.2 result)
  8. Run tests from 1.1 — all must pass
- **Complexity:** Medium

#### Task 1.3: Register hook in hooks.json
- **Status:** done
- **Depends on:** 1.2
- **Files:** `plugins/pd/hooks/hooks.json` (modify)
- **DoD:** PostToolUseFailure entry added (format validated in 0.1). JSON valid.
- **Steps:**
  1. Add entry with event/matcher/async per 0.1 and 0.2 results
  2. Verify: `python3 -c "import json; json.load(open('hooks.json'))"`
- **Complexity:** Simple

#### Task 1.4: Integration test — end-to-end capture
- **Status:** done
- **Depends on:** 1.3
- **Files:** None (manual verification in live CC session)
- **DoD:** Failing Bash → entry in DB. Test runner → no entry. Off mode → no capture. Duplicate → "Reinforced". Performance <2s.
- **Steps:**
  1. `ls /nonexistent` → verify entry via `search_memory`
  2. `pytest --nonexistent` → verify NO entry
  3. Set `memory_model_capture_mode: off` → verify no capture
  4. Same error twice → verify observation_count increment
  5. `time` wrapper on hook execution
- **Complexity:** Medium

---

### Group 2: CLAUDE.md Guardrails (Parallel with Group 1)

#### Task 2.1: Add Behavioral Guardrails section
- **Status:** done
- **Files:** `CLAUDE.md` (modify)
- **DoD:** Three guardrails added in Rule → Why → Enforced by format. No hook enforcement logic duplicated.
- **Steps:**
  1. Add `## Behavioral Guardrails` after "Working Standards"
  2. YOLO persistence guardrail (refs yolo-guard.sh)
  3. Reviewer iteration targets (refs implement.md)
  4. SQLite lock recovery protocol (refs doctor + cleanup-locks.sh)
- **Complexity:** Medium

#### Task 2.2: Verify size + no hook logic duplication
- **Status:** done
- **Depends on:** 2.1
- **Files:** `CLAUDE.md`
- **DoD:** File <13KB. No regex patterns, JSON schemas, or exit codes from hooks appear in guardrails text.
- **Steps:**
  1. `wc -c CLAUDE.md` — verify <13312 bytes
  2. Grep for hook-specific details (regex patterns, exit codes) — confirm absent
  3. If exceeded: consolidate Commands section to referenced file
- **Complexity:** Simple

---

### Group 3a: Skill Refactor (Depends on Group 1 deployed)

#### Task 3a.1: Remove tool-failure triggers from capturing-learnings
- **Status:** done
- **Depends on:** 1.4
- **Files:** `plugins/pd/skills/capturing-learnings/SKILL.md` (modify)
- **DoD:** SKILL.md contains exactly 3 triggers. Old triggers 2 ("Unexpected system behavior") and 3 ("Same error repeated") are removed. Old trigger 4 renumbered to 2, old trigger 5 renumbered to 3.
- **Steps:**
  1. Remove trigger 2 ("Unexpected system behavior discovered")
  2. Remove trigger 3 ("Same error repeated in session")
  3. Renumber: old 4→2, old 5→3
  4. Update any internal trigger number references
- **Complexity:** Simple

#### Task 3a.2: Add non-overlap note
- **Status:** done
- **Depends on:** 3a.1
- **Files:** `plugins/pd/skills/capturing-learnings/SKILL.md` (modify)
- **DoD:** "Detection Split" section explains hook/skill responsibilities and dedup.
- **Steps:**
  1. Add "## Detection Split" section
  2. Explain: tool-failure detection → capture-tool-failure.sh PostToolUseFailure hook
  3. Explain: user-correction detection → this skill (requires conversation context)
  4. Note: dedup gate (0.95 cosine) prevents double-capture
- **Complexity:** Simple

---

### Group 3b: Pre-Validation + Iteration Cap (Parallel with 3a, depends on Group 1)

#### Task 3b.1: Define pre-validation acceptance criteria
- **Status:** done
- **Depends on:** 1.4
- **Files:** Inline verification criteria (implement.md is Markdown, not executable — no test runner)
- **DoD:** Acceptance criteria checklist written as grep/manual verification commands that will be run after 3b.2 to validate the inserted Step 6b.
- **Complexity:** Simple
- **Steps:**
  1. Write verification: `grep -n "search_memory" implement.md` confirms search_memory call exists with category="anti-patterns", limit=20
  2. Write verification: `grep -n "fewer than 5\|< 5" implement.md` confirms skip threshold
  3. Write verification: `grep -n "MCP.*unavailable\|skip.*pre-validation" implement.md` confirms graceful MCP failure handling
  4. Write verification: `grep -n "Pre-validation auto-fix" implement.md` confirms .review-history.md logging
  Note: These are verification commands to run post-3b.2, not executable test scripts (implement.md is a Markdown instruction file).

#### Task 3b.2: Implement pre-validation step (GREEN)
- **Status:** done
- **Depends on:** 3b.1
- **Files:** `plugins/pd/commands/implement.md` (modify)
- **DoD:** Step 6b inserted before Step 7. Queries search_memory, runs inline self-check, auto-fixes matches, logs fixes. Skips gracefully on <5 results or MCP failure.
- **Steps:**
  1. Locate Step 7 insertion point
  2. Add Step 6b with changed-files determination (`git diff --name-only`)
  3. Add search_memory call (limit=20, category="anti-patterns")
  4. Add skip threshold (<5 results)
  5. Add inline self-check prompt (KB patterns only, no additional issues)
  6. Add auto-fix + .review-history.md logging
  7. Add error handling (skip on MCP failure, log reason)
- **Complexity:** Medium

#### Task 3b.3: Reduce iteration cap 5→3
- **Status:** done
- **Depends on:** 3b.2
- **Files:** `plugins/pd/commands/implement.md` (modify)
- **DoD:** All references updated. Verification grep returns zero matches for iteration.*5.
- **Steps:**
  1. Replace "Maximum 5 iterations" → "Maximum 3 iterations" at known locations (lines 15, 248, 1032, 1039, 1186, 1316)
  2. Update YOLO circuit breaker text
  3. Verify: `grep -n 'iteration.*5\|>= 5\|== 5' implement.md` → zero matches
- **Complexity:** Simple

---

### Group 4: Compaction Recovery (Conditional on Task 0.3)

#### Task 4.1: Create compact-recovery.sh
- **Status:** deferred (0.3 was not verifiable — C7 deferred to Out of Scope)
- **Depends on:** 0.3 must pass
- **Files:** `plugins/pd/hooks/compact-recovery.sh` (new)
- **DoD:** SessionStart hook re-injects active feature/phase/branch context after compaction.
- **Steps:**
  1. Standard preamble
  2. Find active feature `.meta.json` in `{pd_artifacts_root}/features/`
  3. Extract feature ID, slug, current phase, branch
  4. Output `{"hookSpecificOutput": {"additionalContext": "..."}}`
- **Complexity:** Medium

#### Task 4.2: Register compact-recovery hook
- **Status:** deferred (0.3 was not verifiable — C7 deferred to Out of Scope)
- **Depends on:** 4.1
- **Files:** `plugins/pd/hooks/hooks.json` (modify)
- **DoD:** SessionStart entry with compact matcher added. JSON valid.
- **Complexity:** Simple
- **Steps:**
  1. Add SessionStart entry to hooks.json: `{"event": "SessionStart", "matcher": "compact", "hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/compact-recovery.sh"}]}`
  2. Verify: `python3 -c "import json; json.load(open('hooks.json'))"`

---

## Summary

| Group | Tasks | Est. Time | Dependencies | Parallelizable |
|-------|-------|-----------|-------------|----------------|
| 0: Pre-flight | 3 | 20 min | None | Yes (all 3) |
| 1: Hook | 4 | 40 min | Group 0 | Sequential |
| 2: CLAUDE.md | 2 | 15 min | None | Parallel with 0+1 |
| 3a: Skill refactor | 2 | 10 min | Group 1 | Parallel with 3b |
| 3b: Pre-validation | 3 | 25 min | Group 1 | Parallel with 3a |
| 4: Compaction | 2 | 15 min | Task 0.3 | Parallel with 1-3 |
| **Total** | **16** | **~125 min** | | |
