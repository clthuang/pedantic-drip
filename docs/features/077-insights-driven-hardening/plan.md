# Plan: Insights-Driven Workflow & Environment Hardening

## Execution Order

```
Phase 0: Pre-flight verification (V1, V2, V3) — can run in parallel
    │
    ├─ 0.1: Verify PostToolUseFailure event + stdin schema
    ├─ 0.2: Verify async:true hook support
    └─ 0.3: Verify compact SessionStart matcher (best-effort)
    │
Phase 1: Tool-failure capture hook (C1 + C2)
    │ Depends on: Phase 0 V1, V2
    │
    ├─ 1.1: Tests+capture-tool-failure (RED)
    ├─ 1.2: Implement capture-tool-failure.sh (GREEN)
    ├─ 1.3: Register hook in hooks.json
    └─ 1.4: Integration test — end-to-end capture
    │
Phase 2: CLAUDE.md guardrails (C6) — Parallel with Phase 1
    │
    ├─ 2.1: Add Behavioral Guardrails section
    └─ 2.2: Verify size + no hook logic duplication
    │
Phase 3a: Capturing-learnings skill refactor (C3)
    │ Depends on: Phase 1 deployed
    │
    ├─ 3a.1: Remove triggers 2,3 from SKILL.md
    └─ 3a.2: Add non-overlap note
    │
Phase 3b: Pre-validation + iteration cap (C4 + C5)
    │ Depends on: Phase 1 deployed (parallel with 3a)
    │
    ├─ 3b.1: Tests+pre-validation (RED)
    ├─ 3b.2: Implement pre-validation step (GREEN)
    └─ 3b.3: Reduce iteration cap 5→3
    │
Phase 4: Compaction recovery hook (C7) — Conditional on V3
    │
    ├─ 4.1: Create compact-recovery.sh (if V3 passed)
    └─ 4.2: Register hook (if V3 passed)
```

**Rollback strategy (Phase 1):** If hook causes issues (false positives, async problems), remove the PostToolUseFailure entry from hooks.json (single-line revert). Clean captured entries: `search_memory(source="session-capture")` + `delete_memory` for unwanted entries.

## Phase 0: Pre-flight Verification

### 0.1: Verify PostToolUseFailure event + stdin schema (V1)
*Why this item:* Entire C1 design depends on PostToolUseFailure being a recognized event with known stdin fields. *Why this order:* Must precede all implementation — foundational assumption.

- Add temporary debug hook: `#!/bin/bash\ncat > /tmp/posttooluse-debug.json`
- Register in hooks.json as `"event": "PostToolUseFailure"` with Bash matcher — this registration itself validates that CC recognizes the event key
- Trigger a failing Bash command (`ls /nonexistent`)
- Inspect `/tmp/posttooluse-debug.json`: confirm `tool_name`, `tool_input` (object), `error` (string) fields
- Document verified schema
- Remove debug hook
- **Go/No-go:** Fields match design I1 → proceed. Different → update I1/C1. Event key not recognized → check if PostToolUse fires on failures too (fallback).

### 0.2: Verify async:true hook support (V2)
*Why this item:* First-in-codebase usage of async:true — unverified. *Why this order:* Determines C1 execution strategy.

- Add test hook with `"async": true` that writes timestamp to `/tmp/async-test.txt`
- Run a Bash command, verify file appears AND command was not blocked
- **Go/No-go:** Works → use async:true in C2. Not supported → synchronous + `timeout 2` wrapper.

### 0.3: Verify compact SessionStart matcher (V3)
*Why this item:* C7 feasibility depends on this. *Why this order:* Independent of V1/V2, can run in parallel.

- Add test SessionStart hook with `"matcher": "compact"` that writes to `/tmp/compact-test.txt`
- Trigger compaction: use `/compact` command if available, or paste large content to fill context
- If compaction cannot be triggered within 10 minutes of effort, mark V3 as "unverified" and defer C7
- **Go/No-go:** Hook fires → C7 proceeds. Does not fire or untriggerable → C7 deferred to Out of Scope.

## Phase 1: Tool-Failure Capture Hook

### 1.1: Tests+capture-tool-failure (RED)
*Why this item:* TDD — write failing tests before implementation (REQ-1). *Why this order:* RED before GREEN.

**Files:** `plugins/pd/hooks/tests/test-capture-tool-failure.sh` (new, following existing `test-hooks.sh` pattern)

Test cases (pipe mock stdin JSON to script, assert behavior):
1. Bash failure with path error → writer called with category "Path error"
2. Edit failure → writer called
3. Test runner command (pytest) → writer NOT called (exclusion)
4. Git read-only command (git status) → writer NOT called (exclusion)
5. agent_sandbox/ path → writer NOT called (exclusion)
6. `memory_model_capture_mode: off` → writer NOT called
7. No pattern match → writer NOT called, debug log written if PD_HOOK_DEBUG=1
8. Performance: complete within 2s

**Test mechanism:** Replace writer with a stub that writes to a temp file. Assert temp file exists/absent per scenario.

### 1.2: Implement capture-tool-failure.sh (GREEN)
*Why this item:* Core hook implementation (C1, REQ-1). *Why this order:* Makes RED tests pass.

**Files:** `plugins/pd/hooks/capture-tool-failure.sh` (new)

1. Standard preamble (SCRIPT_DIR, common.sh, install_err_trap, PROJECT_ROOT, PLUGIN_ROOT)
2. `INPUT=$(cat)` + inline system python3 JSON parse (following yolo-guard.sh pattern)
3. Config check: `read_local_md_field "$config_file" "memory_model_capture_mode" "silent"` — if `off`, exit 0
4. Extract tool_name, tool_input, error via python3
5. Exclusion filters branched by tool_name:
   - Bash: test runner regex, agent_sandbox/, git read-only regex on `tool_input.command`
   - Edit/Write: agent_sandbox/ check on `tool_input.file_path`
6. Pattern match error against 5 categories (regex)
7. Debug log for unmatched errors (PD_HOOK_DEBUG=1 → append to `~/.claude/pd/unmatched-failures.log`)
8. Build entry JSON, call `semantic_memory.writer` CLI via plugin venv python
9. Run all tests from 1.1 — all must pass

### 1.3: Register hook in hooks.json (C2)
*Why this item:* Makes hook active in CC runtime. *Why this order:* Needs script from 1.2, event format validated in 0.1.

**Files:** `plugins/pd/hooks/hooks.json` (modify)

Add PostToolUseFailure entry (format validated in Phase 0 V1):
```json
{
  "event": "PostToolUseFailure",
  "matcher": "Bash|Edit|Write",
  "hooks": [{ "type": "command", "command": "...", "async": true }]
}
```
Verify JSON valid: `python3 -c "import json; json.load(open('hooks.json'))"`

### 1.4: Integration test — end-to-end capture
*Why this item:* Validates full pipeline works in real CC runtime. *Why this order:* Needs hook registered.

- Run `ls /nonexistent` — verify entry in DB via `search_memory`
- Run `pytest --nonexistent` — verify NO entry
- Set `memory_model_capture_mode: off` — verify no capture
- Run same error twice — verify "Reinforced" (observation_count increment)
- Performance: verify hook completes within 2s

## Phase 2: CLAUDE.md Guardrails (Parallel with Phase 1)

### 2.1: Add Behavioral Guardrails section (C6)
*Why this item:* REQ-5 — environment hardening. *Why this order:* Independent of all other phases.

**Files:** `CLAUDE.md` (modify)

Three guardrails after "Working Standards": YOLO persistence, reviewer iteration targets, SQLite lock recovery. Each in Rule → *Why:* → *Enforced by:* format.

### 2.2: Verify size + no hook logic duplication
*Why this item:* Quality gate for CLAUDE.md changes. *Why this order:* After 2.1.

- `wc -c CLAUDE.md` — verify <13312 bytes
- Grep CLAUDE.md for hook-specific implementation details (regex patterns, JSON schemas, exit codes) — confirm guardrails explain intent only, not enforcement mechanics
- Cross-reference with hooks.json entries — no logic duplication
- If size exceeded: consolidate Commands section to referenced file

## Phase 3a: Skill Refactor (Depends on Phase 1)

### 3a.1: Remove triggers 2,3 from capturing-learnings (C3)
*Why this item:* REQ-2 — eliminate hook/skill overlap. *Why this order:* Phase 1 must be deployed first (hook handles tool failures before skill stops detecting them).

**Files:** `plugins/pd/skills/capturing-learnings/SKILL.md` (modify)

- Remove trigger 2 ("Unexpected system behavior discovered")
- Remove trigger 3 ("Same error repeated in session")
- Renumber: 1→1, 4→2, 5→3

### 3a.2: Add non-overlap note
*Why this item:* Documents the detection split for future maintainers. *Why this order:* After 3a.1.

Add "## Detection Split" section: hook handles tool failures, skill handles user corrections, dedup gate prevents double-capture.

## Phase 3b: Pre-Validation + Iteration Cap (Parallel with 3a, Depends on Phase 1)

### 3b.1: Tests+pre-validation (RED)
*Why this item:* TDD — write failing tests before implementation (REQ-3). *Why this order:* RED before GREEN.

Test cases:
1. search_memory called with category="anti-patterns" before reviewer dispatch
2. Skip when <5 entries returned
3. Graceful skip when search_memory MCP unavailable
4. Fixes logged to .review-history.md when matches found

### 3b.2: Implement pre-validation step (GREEN)
*Why this item:* REQ-3/REQ-4 — front-load validation against KB. *Why this order:* Makes RED tests pass.

**Files:** `plugins/pd/commands/implement.md` (modify)

Insert Step 6b before Step 7:
1. Changed files via `git diff --name-only {base_branch}...HEAD`
2. `search_memory(query, limit=20, category="anti-patterns")`
3. Skip if <5 results
4. Inline self-check prompt (KB patterns only)
5. Auto-fix matches, log to `.review-history.md`
6. Error handling: skip on MCP failure, log reason

### 3b.3: Reduce iteration cap 5→3 (C5)
*Why this item:* REQ-4 — cap aligns with pre-validation. *Why this order:* After pre-validation is in place.

**Files:** `plugins/pd/commands/implement.md` (modify)

- Change all "5 iteration" references to "3 iteration"
- Known locations: lines 15, 248, 1032, 1039, 1186, 1316
- Update YOLO circuit breaker text
- **Verification:** `grep -n 'iteration.*5\|>= 5\|== 5' implement.md` must return zero matches after change

## Phase 4: Compaction Recovery (Conditional on V3)

### 4.1: Create compact-recovery.sh (C7)
*Why this item:* REQ-6 — context recovery after compaction. *Why this order:* Only if V3 passed.

**Files:** `plugins/pd/hooks/compact-recovery.sh` (new, conditional)

SessionStart hook: reads `.meta.json`, outputs `{"hookSpecificOutput": {"additionalContext": "..."}}`

### 4.2: Register compact-recovery hook
*Why this item:* Makes hook active. *Why this order:* After 4.1.

**Files:** `plugins/pd/hooks/hooks.json` (modify, conditional)

## Risk Mitigations

| Risk | Mitigation | Owner |
|------|-----------|-------|
| PostToolUseFailure not recognized as event key | Phase 0 V1 — debug hook registration itself validates | Phase 0 |
| PostToolUseFailure schema differs from docs | Phase 0 V1 — empirical verification | Phase 0 |
| async:true unsupported | Fallback to synchronous + timeout 2 | Phase 0 V2 |
| compact matcher unsupported | Defer C7 to Out of Scope | Phase 0 V3 |
| False-positive captures | Conservative 5-category regex + dedup gates | Phase 1 |
| Hook causes production issues | Rollback: remove hooks.json entry + delete captured entries | Phase 1 |
| Pre-validation doesn't reduce iterations | Additive change, easily removable | Phase 3b |
| CLAUDE.md exceeds 13KB | Consolidate verbose sections | Phase 2 |
