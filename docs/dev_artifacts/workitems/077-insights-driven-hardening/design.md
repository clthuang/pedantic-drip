# Design: Insights-Driven Workflow & Environment Hardening

## Prior Art Research

### Codebase Patterns
- Existing PostToolUse hooks (post-enter-plan.sh, post-exit-plan.sh) do NOT read stdin — they use environment context only and output JSON via heredoc with `escape_json()`
- PreToolUse hooks read stdin via `INPUT=$(cat)` + python3 inline parse (yolo-guard.sh, pre-push-guard.sh)
- Standard hook preamble: `set -euo pipefail; SCRIPT_DIR=...; source common.sh; install_err_trap; PROJECT_ROOT=detect_project_root()`
- `semantic_memory.writer` CLI pattern from capturing-learnings: `PYTHONPATH="$PLUGIN_ROOT/hooks/lib" "$PLUGIN_ROOT/.venv/bin/python" -m semantic_memory.writer --action upsert --global-store ~/.claude/pd/memory --entry-json '{...}'`
- implement.md reviewer dispatch: max 5 iterations, selective dispatch on iterations 2+, learning capture at Step 7f

### External Research (Critical Design Corrections)
- **PostToolUseFailure is the correct event for failed tool calls** — PostToolUse only fires on successful completions. PostToolUseFailure fires on failures with fields: `tool_name`, `tool_input`, `error` (string), `is_interrupt`.
- **PostToolUseFailure is non-blocking** — hooks cannot use `decision: block`, only `additionalContext`
- **Pipe-separated matchers confirmed** for all hook events
- **`async: true`** in hook config is the documented mechanism for non-blocking hook execution (not shell `& disown`)
- **PostToolUseFailure response**: supports `additionalContext` in `hookSpecificOutput`

### Impact on Spec (Spec Overrides)
The spec (REQ-1) assumed PostToolUse event with error detection. Research reveals the correct event is **PostToolUseFailure**. The following spec statements are **superseded by this design**:

| Spec Statement | Superseded By |
|---|---|
| REQ-1: "PostToolUse `command` hook" | Design C1: PostToolUseFailure event |
| REQ-1: stdin fields `tool_output` | Design I1: field is `error` (string), no `tool_output` |
| REQ-1: "error field present in stdin JSON" detection | Design: PostToolUseFailure only fires on errors — no detection needed |
| REQ-1 AC: "If backgrounding does not survive hook exit" | Design TD-2: `async: true` replaces backgrounding; fallback is synchronous `timeout 2` if async unsupported |
| REQ-1: hooks.json with `"event": "PostToolUse"` | Design C2: `"event": "PostToolUseFailure"` |
| Technical Constraints: PostToolUse stdin schema | Design I1: PostToolUseFailure schema (verified from CC docs) |

**Implementers should follow this design document, not the spec, for these specific items.** The spec remains authoritative for all non-overridden requirements.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Claude Code Runtime                       │
│                                                             │
│  Tool execution ──→ PostToolUseFailure event                │
│                         │                                    │
│                         ▼                                    │
│              capture-tool-failure.sh                         │
│              (async: true, non-blocking)                     │
│                         │                                    │
│                         ▼                                    │
│              Pattern match error → category                  │
│                         │                                    │
│                         ▼                                    │
│              semantic_memory.writer CLI                      │
│              (backgrounded, async)                           │
│                         │                                    │
│                         ▼                                    │
│              ~/.claude/pd/memory/memory.db                   │
│              (dedup gates: 0.95 reject, 0.90 merge)          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                implement.md Reviewer Flow                    │
│                                                             │
│  Implementation done                                        │
│         │                                                    │
│         ▼                                                    │
│  Pre-validation (inline self-check)                          │
│  ├─ search_memory(category="anti-patterns", limit=20)        │
│  ├─ If <5 results: skip                                      │
│  ├─ Prompt: "Does code exhibit these anti-patterns?"         │
│  └─ Auto-fix matches                                         │
│         │                                                    │
│         ▼                                                    │
│  Reviewer dispatch (max 3 iterations)                        │
│  (existing selective dispatch + resume pattern)              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   CLAUDE.md Guardrails                        │
│                                                             │
│  YOLO persistence ──→ refs yolo-guard.sh                     │
│  Iteration caps ───→ refs implement.md                       │
│  SQLite recovery ──→ refs doctor + cleanup-locks.sh          │
│                                                             │
│  Format: Rule → Why → Enforced by                            │
└─────────────────────────────────────────────────────────────┘
```

## Components

### C1: capture-tool-failure.sh (New Hook Script)

**Location:** `plugins/pd/hooks/capture-tool-failure.sh`

**Event:** `PostToolUseFailure` (NOT `PostToolUse` — critical correction from research)

**Architecture decisions:**
- Uses `async: true` in hooks.json config for non-blocking execution (CC documented mechanism, first-in-codebase — verify in Phase 0)
- Reads stdin JSON with `INPUT=$(cat)` then inline **system python3** parse (following PreToolUse pattern from yolo-guard.sh). If system python3 unavailable, exit 0 silently.
- Calls `semantic_memory.writer` CLI via **plugin venv python** (`${PLUGIN_ROOT}/.venv/bin/python`). If venv python unavailable, exit 0 silently.
- Uses standard hook preamble from common.sh
- Two python runtimes by design: system python3 for fast JSON parsing (lightweight, no deps), plugin venv python for writer (needs semantic_memory deps)

**Input (PostToolUseFailure stdin JSON):**
```json
{
  "hook_event_name": "PostToolUseFailure",
  "tool_name": "Bash",
  "tool_input": {"command": "ls /nonexistent"},
  "error": "ls: /nonexistent: No such file or directory",
  "is_interrupt": false,
  "tool_use_id": "...",
  "session_id": "...",
  "cwd": "..."
}
```
Note: `tool_input` is an object (not string). For Bash, it has `command` key. For Edit, it has `file_path`, `old_string`, `new_string`. For Write, it has `file_path`, `content`.

**Output:** `{}` (empty JSON — non-blocking, no additionalContext needed since the learning is stored to DB, not injected into conversation)

**Flow:**
```
1. Read stdin JSON
2. Check config: memory_model_capture_mode
   └─ If "off" → exit 0
3. Extract tool_name, tool_input, error
4. Apply exclusion filters (branched by tool_name):
   **For Bash:**
   ├─ tool_input.command contains test runner regex → exit 0
   ├─ tool_input.command contains agent_sandbox/ → exit 0
   └─ tool_input.command matches git read-only regex → exit 0
   **For Edit/Write:**
   └─ tool_input.file_path contains agent_sandbox/ → exit 0
   (test-runner and git exclusions do not apply to Edit/Write)
5. Pattern match error against categories
   ├─ If match → proceed to step 6
   └─ If no match → optionally log to debug file, then exit 0
       Debug: if PD_HOOK_DEBUG=1 env var set, append unmatched error to
       ~/.claude/pd/unmatched-failures.log (tool_name, error, timestamp)
       for periodic review of filter gaps
6. Build entry JSON
7. Call semantic_memory.writer (backgrounded)
8. Exit 0
```

### C2: hooks.json Registration (Modified)

**Add new entry:**
```json
{
  "event": "PostToolUseFailure",
  "matcher": "Bash|Edit|Write",
  "hooks": [{
    "type": "command",
    "command": "${CLAUDE_PLUGIN_ROOT}/hooks/capture-tool-failure.sh",
    "async": true
  }]
}
```

Key: `"async": true` ensures the hook never blocks tool execution, regardless of how long the writer takes.

**Phase 0 verification required:** `async: true` is a first-in-codebase usage. Verify in Phase 0 that CC supports it in the installed version. If not supported, fallback: remove `async: true` from hooks.json and use synchronous execution with `timeout 2` wrapper around the writer call inside the hook script.

### C3: capturing-learnings/SKILL.md (Modified)

**Changes:**
- Remove trigger 2 ("Unexpected system behavior discovered") — now handled by C1
- Remove trigger 3 ("Same error repeated in session") — now handled by C1 (dedup merge)
- Retain triggers 1, 4, 5 (require conversation context)
- Add non-overlap note explaining the detection split

**No structural changes** — the skill remains a declarative instruction set, not executable code.

### C4: implement.md Pre-Validation (Modified)

**Integration point:** Before Step 7 reviewer dispatch loop.

**New step inserted:**
```
Step 6b: Pre-validation Against Knowledge Bank
1. Determine changed files: `git diff --name-only {base_branch}...HEAD`
   (files changed on the feature branch, consistent with implement.md delta patterns)
2. Call search_memory(query="{slug} {phase} {changed file names}", limit=20, category="anti-patterns")
3. If <5 results → skip to Step 7
4. Build self-check prompt with ONLY the returned anti-pattern descriptions + changed file contents
5. For each match: auto-fix and log to .review-history.md
6. Proceed to Step 7 (reviewer dispatch)
```

**This is an inline self-check** — no subagent dispatch. The model reads the anti-patterns and inspects its own implementation within the same context window. Pre-validation instructions are executed once and do not persist into subsequent review iterations (only the fixes and log carry forward).

### C5: implement.md Iteration Cap (Modified)

**Change:** `Maximum 5 iterations` → `Maximum 3 iterations` throughout implement.md.

**Affected locations:** All references to the iteration cap, YOLO circuit breaker, and iteration budget text.

### C6: CLAUDE.md Guardrails Section (Modified)

**New section after "Working Standards":**
Three guardrails in rationale-first format (Rule → Why → Enforced by).

**No hook logic duplicated** — CLAUDE.md explains intent and references enforcement mechanisms.

### C7: Compaction Recovery Hook (Conditional — New)

**Prerequisite:** Phase 0 verifies `compact` as valid SessionStart matcher.

**If verified:** New SessionStart hook with `compact` matcher, outputs `additionalContext` with active feature/phase/branch from `.meta.json`.

**If not verified:** Deferred to Out of Scope.

## Technical Decisions

### TD-1: PostToolUseFailure vs PostToolUse
**Decision:** Use `PostToolUseFailure` event.
**Rationale:** Research confirmed PostToolUse fires only on successful tool completions. PostToolUseFailure fires specifically on failures — exactly what we need. This eliminates the need to check for error presence in the stdin JSON (the event itself implies failure).

### TD-2: async: true vs & disown
**Decision:** Use `async: true` in hooks.json config.
**Rationale:** This is the CC-documented mechanism for non-blocking hooks. Shell backgrounding with `& disown` has unverified behavior regarding process survival after hook exit. `async: true` is explicit and deterministic.

### TD-3: Inline Pre-Validation vs Subagent
**Decision:** Inline self-check within implement command context.
**Rationale:** Avoids subagent token cost. The model already has the implementation files in context — adding 5-20 anti-pattern descriptions and asking "does this code exhibit these?" is a lightweight reasoning step. No need for a separate agent dispatch.

### TD-4: tool_input Parsing
**Decision:** Parse `tool_input` as JSON object, extract command/file_path based on `tool_name`.
**Rationale:** Research confirmed `tool_input` is an object (e.g., `{"command": "..."}` for Bash, `{"file_path": "...", "old_string": "...", "new_string": "..."}` for Edit). The hook must handle each tool type's input structure.

### TD-5: Category as anti-patterns Only
**Decision:** All hook-captured entries use `category: "anti-patterns"`.
**Rationale:** Tool failures are things that went wrong — they are inherently anti-patterns. This also makes them queryable via `search_memory(category="anti-patterns")` for pre-validation (C4).

### TD-6: Config Read from Project-Level File
**Decision:** Read `memory_model_capture_mode` from `${PROJECT_ROOT}/.claude/pd.local.md`.
**Rationale:** Matches established hook pattern (post-enter-plan.sh:12). Project-level config allows per-project override of capture behavior.

## Risks

### R-1: PostToolUseFailure stdin schema unverified empirically
**Mitigation:** Phase 0 verification with debug hook (spec REQ-1). If schema differs from research, update hook script accordingly. Research findings are from CC docs, not empirical testing.

### R-1b: async: true untested in this codebase
**Mitigation:** Phase 0 verification — register a test hook with `async: true` and confirm it fires without blocking. Fallback: synchronous execution with `timeout 2` wrapper.

### R-2: False-positive captures from noisy errors
**Mitigation:** Conservative pattern matching (only 5 specific categories). `async: true` means false captures don't slow execution. Dedup gates (0.95 cosine) prevent noise accumulation. User can delete entries via `delete_memory` MCP.

### R-3: Pre-validation may not reduce reviewer iterations
**Mitigation:** Pre-validation is additive — worst case it adds a few seconds to the implement flow. If it doesn't help, remove it without affecting the rest of the feature. The iteration cap reduction (5→3) stands independently.

### R-4: CLAUDE.md size approaching 13KB limit
**Mitigation:** Three guardrails add ~500 bytes. Current CLAUDE.md is well under 13KB. If exceeded, consolidate verbose sections to referenced files.

## Interfaces

### I1: capture-tool-failure.sh stdin (Input)

```typescript
interface PostToolUseFailureInput {
  hook_event_name: "PostToolUseFailure";
  tool_name: "Bash" | "Edit" | "Write";  // filtered by matcher
  tool_input: BashInput | EditInput | WriteInput;
  error: string;  // error message from tool failure
  is_interrupt?: boolean;
  tool_use_id: string;
  session_id: string;
  cwd: string;
}

interface BashInput { command: string; timeout?: number; }
interface EditInput { file_path: string; old_string: string; new_string: string; }
interface WriteInput { file_path: string; content: string; }
```

### I2: capture-tool-failure.sh stdout (Output)

```typescript
// Always outputs empty JSON — no additionalContext needed
interface HookOutput {
  // empty object: {}
}
```

### I3: semantic_memory.writer CLI (Called by C1)

```bash
# Entry JSON structure
{
  "name": "Tool failure: {category} — {brief}",     # max 60 chars
  "description": "{error_message} — Command: {cmd}", # min 20 chars
  "reasoning": "Automatic capture from PostToolUseFailure in feature {id}",
  "category": "anti-patterns",
  "source": "session-capture",
  "confidence": "low"
}
# Note: 'keywords' field omitted — writer auto-extracts keywords from name/description/category
```
```

### I4: Pre-Validation Self-Check Prompt (C4)

```
The knowledge bank contains these anti-patterns relevant to this feature:

{list of anti-pattern names and descriptions from search_memory}

Review the following implementation files for any of these specific anti-patterns:

{changed file contents}

For each anti-pattern that applies, explain which code exhibits it and suggest a fix.
Do NOT identify issues beyond the listed anti-patterns.
```

### I5: CLAUDE.md Guardrails Section (C6)

```markdown
## Behavioral Guardrails

**YOLO mode persistence:** In YOLO mode, do not disable or exit YOLO mode. Continue executing autonomously through errors. Fix errors and keep going.
*Why:* YOLO mode disabling forces user intervention, defeating autonomous execution.
*Enforced by:* `yolo-guard.sh` hook intercepts AskUserQuestion in YOLO mode.

**Reviewer iteration targets:** Target 1-2 reviewer iterations per phase. Hard cap: 3 iterations. After 3 rounds, summarize remaining issues and ask user for guidance.
*Why:* 3-5 iteration cycles consumed large context/time portions.
*Enforced by:* Iteration cap in `implement.md`.

**SQLite lock recovery:** When encountering "database is locked" errors: (1) check for orphaned processes with `lsof +D ~/.claude/pd | grep .db`, (2) kill stale Python/MCP processes, (3) verify WAL mode with `PRAGMA journal_mode`. Do not silently swallow database exceptions.
*Why:* SQLite locking from stale MCP processes was the most persistent friction source.
*Addressed by:* Doctor auto-fix at session start, WAL mode on connect, `cleanup-locks.sh` hook.
```

## File Change Summary

| File | Action | Component |
|------|--------|-----------|
| `plugins/pd/hooks/capture-tool-failure.sh` | **Create** | C1 |
| `plugins/pd/hooks/hooks.json` | **Modify** — add PostToolUseFailure entry | C2 |
| `plugins/pd/skills/capturing-learnings/SKILL.md` | **Modify** — remove triggers 2,3; add non-overlap note | C3 |
| `plugins/pd/commands/implement.md` | **Modify** — add Step 6b pre-validation; change cap 5→3 | C4, C5 |
| `CLAUDE.md` | **Modify** — add Behavioral Guardrails section | C6 |
| `plugins/pd/hooks/compact-recovery.sh` | **Create** (conditional on Phase 0 V3) | C7 |
| `~/.claude/pd/unmatched-failures.log` | **Create** (conditional on PD_HOOK_DEBUG=1 env var) | C1 debug |

## Dependencies

```
Phase 0: Verify three items before implementation:
  ├─ V1: PostToolUseFailure stdin JSON schema (debug hook → /tmp/posttooluse-debug.json)
  │   Go: fields match I1 interface. No-go: update I1 and C1 to actual schema.
  ├─ V2: `async: true` support in hooks.json (test hook with async flag)
  │   Go: hook fires without blocking. No-go: use synchronous + timeout 2.
  └─ V3: `compact` SessionStart matcher (test hook with compact matcher)
      Go: C7 proceeds. No-go: C7 deferred to Out of Scope.
         │
Phase 1: C1 (hook) + C2 (hooks.json) ──→ Deploy & validate
         │
Phase 2: C6 (CLAUDE.md guardrails) ──→ Independent
         │
Phase 3a: C3 (skill refactor) ──→ Depends on C1 being deployed
         │
Phase 3b: C4 (pre-validation) + C5 (cap reduction) ──→ Depends on C3
         │
Phase 0 result ──→ C7 (compaction hook) if verified
```
