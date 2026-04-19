# Hook Development Guide

Guidelines for developing hooks in the pedantic-drip plugin.

## Critical Concept: PLUGIN_ROOT vs PROJECT_ROOT

### The Problem

When Claude Code installs a plugin, it copies files to a cache directory:
```
~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/
```

Hooks receive `CLAUDE_PLUGIN_ROOT` pointing to this cached location. However:
- **Static plugin assets** (scripts, templates): Use PLUGIN_ROOT
- **Dynamic project state** (features, source code): Use PROJECT_ROOT

### The Solution

Always use the shared library to get PROJECT_ROOT:

```bash
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
PROJECT_ROOT="$(detect_project_root)"
```

### When to Use Each

| Variable | Use For | Example |
|----------|---------|---------|
| `PLUGIN_ROOT` | Static plugin files | Template files, reference docs |
| `PROJECT_ROOT` | Dynamic project state | Feature metadata, test files, source code |
| `PWD` | User's current directory | Relative path display |

## Hook Output Format

All hooks must output valid JSON. Use `escape_json()` from the shared library:

```bash
source "${SCRIPT_DIR}/lib/common.sh"

local message="Line 1\nLine 2"
local escaped
escaped=$(escape_json "$message")

cat <<EOF
{
  "decision": "allow",
  "additionalContext": "${escaped}"
}
EOF
```

## Shared Library Functions

Located at `hooks/lib/common.sh`:

### detect_project_root()
Walks up from PWD to find project root (directory containing `.git` or `docs/features`).

### escape_json()
Escapes special characters for JSON output: newlines, tabs, quotes, backslashes.

## Memory Library

Located at `hooks/lib/memory.py`:

Python module used by `session-start.sh` to inject knowledge bank entries into session context. Parses entries from project-local (`docs/knowledge-bank/`) and global (`~/.claude/pd/memory/`) stores, deduplicates by content hash, selects top entries by priority, and outputs formatted markdown.

## Testing Hooks

Run the hook test suite:
```bash
./hooks/tests/test-hooks.sh
```

Or via validation:
```bash
./validate.sh
```

## Anti-Patterns

| Don't | Why | Do Instead |
|-------|-----|------------|
| Use `find .` for project files | Wrong results from subdirectories | Use `find "${PROJECT_ROOT}"` |
| Read metadata from PLUGIN_ROOT | Stale cached data | Use PROJECT_ROOT for dynamic state |
| Duplicate utility functions | Maintenance burden, drift | Source `lib/common.sh` |
| Output unescaped strings in JSON | Invalid JSON breaks hook | Use `escape_json()` |

## Hook Types Reference

| Event | Can Block | Receives Stdin | Returns |
|-------|-----------|----------------|---------|
| SessionStart | No | None | `{"hookSpecificOutput": {...}}` |
| PreToolUse | Yes (exit 2) | Tool input JSON | `{"decision": "allow/block", ...}` |
| PostToolUse | No | Tool output JSON | Context additions |
| Stop | Yes | None | Confirmation |

## Hook JSON Output Schema

Claude Code enforces a schema on hook JSON output. **Every `hookSpecificOutput` block MUST include a `hookEventName` field** matching the event the hook is registered for:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow"
  }
}
```

### Preferred: use the shared helper

Instead of emitting JSON by hand, source `lib/common.sh` and call `emit_hook_json`:

```bash
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
emit_hook_json "PreToolUse" '{"permissionDecision":"allow"}'
```

`emit_hook_json` always wraps the payload with the correct `hookEventName`. Prefer this over hand-rolled `printf '{"hookSpecificOutput":{...}}'` to prevent the bug class documented in `docs/rca/20260419-hookSpecificOutput-missing-hookEventName-round2.md`.

### Common pitfall: missing `hookEventName`

Omitting `hookEventName` produces this error in user transcripts:

```
PreToolUse:Bash hook error — Hook JSON output validation failed
hookSpecificOutput is missing required field "hookEventName"
```

### Cross-event error attribution — the label is misleading

**Claude Code attributes a hook's JSON-validation failure to the NEXT tool event in the transcript, not to the hook that actually produced the malformed JSON.** If you see `PreToolUse:Bash hook error` but your PreToolUse:Bash hooks look fine, grep ALL hooks for the emission pattern — the bug is most likely in a PostToolUse or PostToolUse:EnterPlanMode hook that fired just before the Bash invocation.

Example from feature 085 RCA: a PostToolUse:EnterPlanMode hook emitted malformed `hookSpecificOutput`; CC reported the error as `PreToolUse:Bash hook error` on the next Bash invocation. Scope-matched search ("find PreToolUse:Bash hooks with hookSpecificOutput") missed the actual emitter.

### Stale cached plugin versions

CC does not garbage-collect pre-fix cached plugin versions when a new release lands. Long-running sessions continue referencing the previous version's hook scripts until the user starts a new session. If a hook fix doesn't seem to take effect:

1. Start a new Claude Code session (don't resume).
2. Delete stale caches: `rm -rf ~/.claude/plugins/cache/pedantic-drip-marketplace/pd/X.Y.Z/` for each non-active version.

The `cleanup-stale-versions.sh` SessionStart hook (feature 087) automates this — it reads `installed_plugins.json` and removes any cached version that doesn't match the active one.

### Enforcement

`validate.sh` runs a static scanner on every PR: any `"hookSpecificOutput":` emission (literal JSON-emission signature) without `hookEventName` in the same file fails CI. Test-consumer files under `plugins/pd/hooks/tests/` are excluded (they read hook output, not emit it).
