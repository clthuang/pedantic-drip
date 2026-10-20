# Specification: Insights-Driven Workflow & Environment Hardening

## Overview
Two-track improvement to pd's feedback loops and Claude Code environment, driven by quantitative usage analysis (111 sessions, March-April 2026). Track 1 adds automated tool-failure capture and knowledge-bank-grounded pre-validation to the pd plugin. Track 2 hardens the Claude Code environment with rationale-first CLAUDE.md guardrails.

## Scope

### In Scope
- PostToolUse tool-failure monitor hook (shell `command` type)
- `capturing-learnings` skill refactor (remove tool-failure triggers, retain user-correction triggers)
- Knowledge-bank-grounded pre-validation before reviewer dispatch
- Review iteration cap reduction (5 → 3)
- CLAUDE.md guardrails: YOLO persistence, reviewer iteration caps, SQLite lock recovery protocol
- Compaction recovery hook (conditional on `compact` matcher verification)

### Out of Scope
- User correction detection via hooks (PostToolUse lacks conversation context — stays in skill)
- Client-server DB migration (WAL + doctor already resolves SQLite locking)
- Headless mode cron scheduling for ACM
- Agent teams for parallel review
- `.claude/rules/*.md` file splitting

## Requirements

### REQ-1: PostToolUse Tool-Failure Monitor Hook

**What:** A shell (`command` type) PostToolUse hook that detects tool failures and stores learnings automatically.

**Trigger conditions:**
- Bash tool: non-zero exit code (error field present in stdin JSON)
- Edit tool: edit failure (error field present)
- Write tool: write failure (error field present)

**Exclusion filters (must NOT capture):**
- Test runner commands: stdin `tool_input` contains `pytest`, `jest`, `npm test`, `cargo test`, `go test`, or `python -m pytest`
- Intentional failures in `agent_sandbox/` paths
- Commands where `tool_input` contains read-only git ops that may exit non-zero: match via regex `\bgit\s+(status|diff|log|branch|tag|remote|show|rev-parse)\b` anywhere in the input string (not just at start, since commands may have `cd` prefixes or environment variables)

**Pattern matching categories for error output:**
| Category | Pattern (regex on error/output) | Example |
|----------|-------------------------------|---------|
| Path error | `No such file\|not found\|ENOENT\|FileNotFoundError` | Wrong import path |
| Compatibility | `not compatible\|version mismatch\|unsupported\|deprecated` | Bash associative array on old bash |
| Missing dependency | `ModuleNotFoundError\|Cannot find module\|ImportError\|not installed` | Missing pip package |
| Syntax error | `SyntaxError\|unexpected token\|parse error` | Malformed JSON/Python |
| Permission | `Permission denied\|EACCES\|Operation not permitted` | File permission issue |

**Plugin root resolution:** The hook script derives its root using the established pattern from existing hooks (e.g., `post-enter-plan.sh:6-9`):
```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
install_err_trap
PROJECT_ROOT="$(detect_project_root)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"  # hooks/ → plugin root
```
Note: `${CLAUDE_PLUGIN_ROOT}` is used in `hooks.json` for command paths. Inside the hook script itself, `PLUGIN_ROOT` is derived from `SCRIPT_DIR` (not from an environment variable).

**Storage:**
- Call: `PYTHONPATH="${PLUGIN_ROOT}/hooks/lib" "${PLUGIN_ROOT}/.venv/bin/python" -m semantic_memory.writer --action upsert --global-store ~/.claude/pd/memory --entry-json '{...}'`
- Entry fields:
  - `name`: `"Tool failure: {category} — {brief description}"` (max 60 chars)
  - `description`: Error message + command that triggered it (min 20 chars)
  - `reasoning`: `"Automatic capture from PostToolUse hook in feature {active_feature_id}"`
  - `category`: `"anti-patterns"`
  - `source`: `"session-capture"`
  - `confidence`: `"low"`
- Dedup: Handled by writer's existing gates (0.95 cosine rejection, 0.90 merge)

**Config integration:**
- Read `memory_model_capture_mode` from `${PROJECT_ROOT}/.claude/pd.local.md` (project-level config, matching existing hook pattern from `post-enter-plan.sh:12`). Use `read_local_md_field` from `lib/common.sh`.
- If `off`: exit 0 immediately (no capture)
- If `silent` or `ask-first`: capture silently (hook cannot ask user — command hooks cannot emit user-visible messages without blocking)
- **Divergence from PRD FR-2:** PRD states ask-first mode "emits a hint message." In the hook context, this is not feasible. The hook treats ask-first identically to silent. The ask-first interactive behavior is preserved in the `capturing-learnings` skill only.

**Performance:**
- Must complete within 2 seconds
- Run all external commands with stderr suppressed (`2>/dev/null`)
- Implementation: always background the `semantic_memory.writer` call and exit immediately. This is simpler and more deterministic than a `timeout` wrapper:
  ```bash
  "${PLUGIN_ROOT}/.venv/bin/python" -m semantic_memory.writer ... 2>/dev/null &
  disown
  ```
  Assumption: CC preserves backgrounded+disowned processes after hook exit. **Verify in Phase 0** alongside stdin schema check: have the debug hook background a process that writes to a temp file after a 1-second sleep, then verify the file appears after hook exit. If backgrounding does not survive, fallback: run the writer synchronously with `timeout 2` wrapper.

**Hook registration in `hooks.json`:**
PostToolUse matchers support the same regex pipe syntax as PreToolUse matchers (precedent: PreToolUse `meta-json-guard.sh` uses `Write|Edit` matcher at `hooks.json:78`). If pipe syntax is empirically found not to work for PostToolUse, fall back to three separate hook entries (one per tool).
```json
{
  "event": "PostToolUse",
  "matcher": "Bash|Edit|Write",
  "hooks": [{
    "type": "command",
    "command": "${CLAUDE_PLUGIN_ROOT}/hooks/capture-tool-failure.sh"
  }]
}
```

**Phase 0 verification (PostToolUse stdin JSON schema):**
Before implementing REQ-1, empirically verify the PostToolUse stdin JSON schema by adding a temporary debug hook:
```bash
#!/bin/bash
cat > /tmp/posttooluse-debug.json
```
Run a failing Bash command and inspect `/tmp/posttooluse-debug.json` to confirm the presence and structure of `tool_name`, `tool_input`, `tool_output`, and `error` fields. Document the verified schema in a comment at the top of `capture-tool-failure.sh`. This is critical-path — the entire REQ-1 design depends on this schema.

**Acceptance criteria:**
- [ ] Hook fires on Bash failures, captures learning with correct category
- [ ] Hook does NOT fire on pytest/jest test runner failures
- [ ] Hook does NOT fire when `memory_model_capture_mode` is `off`
- [ ] Hook completes within 2 seconds
- [ ] If backgrounding does not survive hook exit (per Phase 0 verification), writer runs synchronously with `timeout 2` wrapper instead
- [ ] Stored entries have `source="session-capture"` and `confidence="low"`
- [ ] Duplicate errors produce "Reinforced" (observation count increment), not new entries — this is a dependency guarantee from `semantic_memory.writer`'s existing dedup gates (tested separately); verify via integration test that runs hook twice with similar errors and checks DB observation_count

### REQ-2: Capturing-Learnings Skill Refactor

**What:** Split detection responsibilities between hook (tool failures) and skill (user corrections).

**Changes to `skills/capturing-learnings/SKILL.md`:**

Remove triggers 2 and 3:
- ~~Trigger 2: "Unexpected system behavior discovered"~~ → Now handled by PostToolUse hook
- ~~Trigger 3: "Same error repeated in session"~~ → Now handled by PostToolUse hook (dedup merge increments observation_count)

Retain triggers 1, 4, 5:
- Trigger 1: "User explicitly corrects model behavior" — requires conversation context
- Trigger 4: "User shares preference or convention" — requires conversation context
- Trigger 5: "Workaround found" — requires conversation context + judgment

**Add non-overlap note:**
Add a section explaining that tool-failure detection is handled by the PostToolUse `capture-tool-failure.sh` hook, and the skill should NOT attempt to capture the same errors. If the skill detects a user correction about a tool failure that was already captured by the hook, the dedup gate (0.95 cosine) prevents double-storage.

**Acceptance criteria:**
- [ ] Triggers 2 and 3 removed from SKILL.md
- [ ] Triggers 1, 4, 5 retained with unchanged behavior
- [ ] Non-overlap note added referencing PostToolUse hook
- [ ] No double-capture when both hook and skill process the same error context

### REQ-3: Knowledge-Bank-Grounded Pre-Validation

**What:** Before dispatching reviewers in the implement command, run a self-check that loads relevant anti-patterns from the knowledge bank and scans the current implementation for matches.

**Integration point:** `commands/implement.md`, before the reviewer dispatch loop (Step 7).

**Mechanism:**
1. Call `search_memory` MCP with:
   - `query`: `"{feature slug} {phase} {space-separated changed file names}"`
   - `limit`: 20
   - `category`: `"anti-patterns"`
   - `brief`: true
2. If fewer than 5 entries returned: skip pre-validation (insufficient KB data for meaningful matching). The search limit (20) is intentionally higher than the skip threshold (5) to ensure the threshold reflects actual KB coverage, not the search cap.
3. For each returned anti-pattern entry:
   - This is an LLM prompt-based semantic check performed inline as a self-directed reasoning step within the implement command (not a subagent dispatch — avoids extra token cost). The prompt presents the KB anti-pattern descriptions and the changed file contents, asking: "Does this code exhibit any of these specific anti-patterns?" The LLM must not identify issues beyond the provided list — it evaluates only whether the listed anti-patterns apply to the code under review.
4. If matches found:
   - Auto-fix the matching issues before dispatching the reviewer
   - Log fixes to `.review-history.md` as "Pre-validation auto-fix"
5. If zero matches: proceed directly to reviewer dispatch

**Error handling:** If `search_memory` MCP is unavailable, times out, or the self-check prompt errors out, skip pre-validation and proceed directly to reviewer dispatch. Log the skip reason to `.review-history.md`.

**Pre-validation replaces first iteration:**
- If pre-validation finds and fixes issues, the first reviewer dispatch sees cleaner artifacts
- This effectively replaces what would have been the first reviewer iteration's findings
- The iteration counter still starts at 1 for the reviewer loop

**Acceptance criteria:**
- [ ] Pre-validation queries `search_memory` with category `"anti-patterns"` before reviewer dispatch
- [ ] Skips gracefully when KB returns <5 entries (matching mechanism section threshold; diverges from PRD FR-5 which says <10 — threshold lowered because search limit was raised from 10 to 20, making 5 returned entries a meaningful signal of sparse coverage)
- [ ] Auto-fixes matched anti-patterns before reviewer sees artifacts
- [ ] Fixes logged to `.review-history.md`
- [ ] Pre-validation prompt includes ONLY KB-sourced anti-pattern descriptions as match candidates — does not ask LLM to identify additional issues beyond provided patterns

### REQ-4: Review Iteration Cap Reduction

**What:** Reduce the maximum review iterations from 5 to 3 in `commands/implement.md`.

**Changes:**
- Line ~248: Change `Maximum 5 iterations` to `Maximum 3 iterations`
- Update all references to the iteration cap throughout the file
- The YOLO circuit breaker reference should also update to 3

**Rationale:** Combined with pre-validation (REQ-3), 3 iterations should be sufficient. If blockers persist after 3 rounds, summarize remaining issues and ask user for guidance.

**Acceptance criteria:**
- [ ] Max iterations changed from 5 to 3 in implement.md
- [ ] All cap references updated consistently
- [ ] Circuit breaker text updated

### REQ-5: CLAUDE.md Guardrails

**What:** Add behavioral guardrails to CLAUDE.md in rationale-first format. Each guardrail follows: Rule → *Why:* → *Enforced by:*.

**New section to add (after "Working Standards"):**

```markdown
## Behavioral Guardrails

**YOLO mode persistence:** In YOLO mode, do not disable or exit YOLO mode. Continue executing autonomously through errors. Fix errors and keep going.
*Why:* YOLO mode disabling forces user intervention across sessions, defeating the purpose of autonomous execution.
*Enforced by:* `yolo-guard.sh` hook intercepts AskUserQuestion in YOLO mode.

**Reviewer iteration targets:** Target 1-2 reviewer iterations per phase. Hard cap: 3 iterations. After 3 rounds, summarize remaining issues and ask user for guidance rather than looping indefinitely.
*Why:* 3-5 iteration cycles consumed large portions of context and time. Pre-validation against knowledge bank should catch known issues before the first reviewer round.
*Enforced by:* Iteration cap in `implement.md`.

**SQLite lock recovery:** When encountering "database is locked" errors: (1) check for orphaned processes with `lsof +D ~/.claude/pd | grep .db`, (2) kill stale Python/MCP processes, (3) verify WAL mode with `PRAGMA journal_mode`. Do not silently swallow database exceptions.
*Why:* SQLite locking from stale MCP server processes was the most persistent friction source across 8+ sessions.
*Addressed by:* Doctor auto-fix at session start (`session-start.sh`), WAL mode enforced on every connection, `cleanup-locks.sh` SessionStart hook.
```

**Size check:** After adding, verify CLAUDE.md stays under ~13KB. If it exceeds, consolidate by moving verbose sections to referenced files.

**Format rules:**
- Guardrails explain *why* — they don't duplicate hook enforcement logic
- Each guardrail references the enforcement mechanism
- No standalone rules without rationale

**Acceptance criteria:**
- [ ] Three guardrails added: YOLO persistence, reviewer iterations, SQLite recovery
- [ ] Each follows Rule → *Why:* → *Enforced by:* format
- [ ] No duplication of existing hook enforcement rules
- [ ] CLAUDE.md stays under 13KB after additions. If exceeded, consolidate verbose sections (e.g., Commands reference, Key References) into referenced external files.
- [ ] Guardrails reference specific hook/command files

### REQ-6: Compaction Recovery Hook (Conditional)

**What:** SessionStart hook with `compact` matcher that re-injects workflow context after context compaction.

**Prerequisite:** Verify `compact` is a valid SessionStart matcher in current Claude Code version.

**If verified as supported:**
- Add SessionStart hook entry in `hooks.json` with `"matcher": "compact"`
- Hook script reads `.meta.json` for active feature, phase, branch
- Hook outputs `{"additionalContext": "..."}` matching the CC hooks response format, consistent with existing `session-start.sh` output pattern
- Includes: active feature ID/slug, current phase, branch name, last 3 memory entries

**If NOT supported:**
- Move to Out of Scope
- Document in spec that existing `session-start.sh` runs on `startup|resume|clear` and provides partial recovery

**Acceptance criteria:**
- [ ] `compact` matcher verified before implementation begins
- [ ] If supported: hook re-injects feature/phase/branch context after compaction
- [ ] If not supported: documented as deferred with rationale

## Technical Constraints

- All hook scripts must suppress stderr (`2>/dev/null`) per hook development guide
- No hardcoded `plugins/pd/` paths — use `${CLAUDE_PLUGIN_ROOT}` in hooks.json
- PostToolUse hook stdin JSON format (assumed — verify in Phase 0): `{"tool_name": "...", "tool_input": "...", "tool_output": "...", "error": "..."}`. Field names are provisional; Phase 0 verification (REQ-1) establishes the actual schema before implementation. Fields may be named `tool_response` or `tool_result` instead of `tool_output`.
- `semantic_memory.writer` CLI requires: `PYTHONPATH="${PLUGIN_ROOT}/hooks/lib"` and `"${PLUGIN_ROOT}/.venv/bin/python"`
- `store_memory` quality gates: 20-char min description, 0.95 cosine rejection, 0.90 merge threshold

## Migration Phases

| Phase | Requirements | Risk | Behavior Change |
|-------|-------------|------|-----------------|
| 0: Pre-flight | REQ-6 `compact` matcher + REQ-1 PostToolUse stdin schema + REQ-1 background process survival | None | None |
| 1: Passive infra | REQ-1 (hook) | Low — hook is passive, silent | None |
| 2: Environment | REQ-5 (CLAUDE.md) | Low — documentation only | Reference reading |
| 3a: Structural | REQ-2 (skill refactor) | Low — removing triggers | None |
| 3b: Cognitive | REQ-3 (pre-validation), REQ-4 (cap reduction) | Medium — changes review flow | Front-load verification |

## Dependencies

- REQ-2 depends on REQ-1 (remove tool-failure triggers only after hook is deployed)
- REQ-4 depends on REQ-3 (reduce cap only after pre-validation is in place)
- REQ-5 is independent (can deploy in any order)
- REQ-6 is independent but conditional

## Test Strategy

### REQ-1 Tests
- Unit: Hook script with mock stdin JSON (Bash failure, Edit failure, test runner exclusion, off mode)
- Integration: End-to-end with `semantic_memory.writer` verifying entry stored in DB
- Integration (dedup): Run hook twice with similar error, verify DB observation_count incremented (not two entries)
- Performance: Verify hook completes within 2s with `time` wrapper
- Phase 0: Verify PostToolUse stdin JSON schema empirically; verify backgrounded+disowned process survival

### REQ-2 Tests
- Verify SKILL.md has exactly 3 triggers (1, 4, 5) after refactor
- Verify non-overlap note references `capture-tool-failure.sh`

### REQ-3 Tests
- Mock `search_memory` with known anti-patterns, verify pre-validation catches matches
- Verify skip behavior when KB returns <5 entries (threshold) with limit=20 (search cap)
- Verify fixes logged to `.review-history.md`
- Verify graceful skip when `search_memory` MCP is unavailable

### REQ-4 Tests
- Grep verify: `Maximum 3 iterations` in implement.md
- No references to `Maximum 5` remaining

### REQ-5 Tests
- Verify CLAUDE.md contains all 3 guardrails with *Why:* and *Enforced by:* sections
- Verify CLAUDE.md file size < 13KB
- Verify no duplication with existing hook rules

### REQ-6 Tests
- If supported: Verify hook fires on compaction and outputs correct context
- If not supported: Verify documented as deferred
