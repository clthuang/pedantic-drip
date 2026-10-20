# Hooks Implementation Design

## Overview

Add Claude Code hooks to the my-ai-setup plugin for workflow automation and guardrails.

## Scope

Two hooks only (lean approach after critical review):

| Hook | Event | Purpose |
|------|-------|---------|
| session-start.sh | SessionStart | Inject workflow context, surface active feature |
| pre-commit-guard.sh | PreToolUse (Bash) | Block commits to main, remind about tests |

## Design Decisions

### What We're NOT Building (and Why)

| Original Idea | Why Removed |
|---------------|-------------|
| TDD enforcement hook | Technically infeasible—can't detect failing tests without running test suite |
| PostToolUse metadata updates | Creates two sources of truth with skills |
| Stop session summary | Hook can't access conversation history |
| UserPromptSubmit skip detection | Claude's semantic understanding handles this better |

### Principles

1. **Hooks enforce guardrails; skills guide behavior**
2. **Graceful degradation** when no feature context exists
3. **Non-blocking by default** except for hard guardrails (commit to main)
4. **Concise context injection** - orient Claude, don't dump content

---

## Hook 1: SessionStart

**File:** `hooks/session-start.sh`

**Triggers:** `startup`, `resume`, `clear`, `compact`

**Behavior:**

1. Find active feature (most recently modified `.meta.json` in `docs/dev_artifacts/workitems/`)
2. Build context message with:
   - Workflow overview (available commands, skill progression)
   - Active feature info if exists (name, mode, current phase, worktree)
   - No feature: note that `/create-feature` is available
3. Return JSON with `additionalContext`

**Output Format (with feature):**

```
You're working on feature 003-user-auth (Standard mode).
Current phase: specifying
Worktree: ../my-project-003-user-auth

Available commands: /brainstorm → /specify → /design → /create-tasks → /implement → /verify → /finish
```

**Output Format (no feature):**

```
No active feature. Use /create-feature to start a structured workflow,
or work freely—skills are available on demand.
```

**Exit Codes:**
- Always exit 0 (non-blocking)

---

## Hook 2: PreToolUse Commit Guard

**File:** `hooks/pre-commit-guard.sh`

**Triggers:** PreToolUse on `Bash` tool when command contains `git commit`

**Behavior:**

1. Parse Bash command from stdin (JSON)
2. Check if command contains `git commit`
   - If not: pass through (exit 0)
3. Check current branch:
   - If `main` or `master`: BLOCK (exit 2)
   - If feature branch: continue
4. Check for test files:
   - If test files exist: add reminder to context
   - If no test files: pass through silently
5. Return JSON with decision

**Blocking Response (commit to main):**

```json
{
  "decision": "block",
  "reason": "Direct commits to main branch are blocked. Create a feature branch first:\n  git checkout -b feature/your-feature-name\n\nOr use /create-feature for the full workflow."
}
```

**Advisory Response (tests exist):**

```json
{
  "decision": "allow",
  "additionalContext": "Reminder: Test files exist in this project. Have you run the tests?"
}
```

**Pass-through Response:**

```json
{
  "decision": "allow"
}
```

**Test File Detection Patterns:**

- `**/test_*.py`
- `**/*_test.py`
- `**/*.test.ts`
- `**/*.test.js`
- `**/*_test.go`
- `**/Test*.java`
- `**/*Test.java`
- `**/*_spec.rb`

**Exit Codes:**
- 0: Allow (with optional context)
- 2: Block

---

## File Structure

```
hooks/
├── hooks.json              # Hook registry
├── session-start.sh        # SessionStart hook
└── pre-commit-guard.sh     # PreToolUse hook
```

## hooks.json

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/pre-commit-guard.sh"
          }
        ]
      }
    ]
  }
}
```

## Cross-Platform Support

- Scripts use `#!/usr/bin/env bash`
- Claude Code 2.1+ auto-detects .sh files on Windows
- No .cmd wrapper needed

## Integration

- No changes to `plugin.json` required
- Claude Code auto-discovers `hooks/hooks.json`

## Future Expansion (Only If Pain Points Emerge)

| Potential Hook | Trigger | Purpose |
|----------------|---------|---------|
| PreToolUse (Write) | Write outside worktree | Warn when editing files outside feature worktree |
| UserPromptSubmit | Every prompt | Inject active feature reminder |

Only add these if specific problems arise that skills can't address.
