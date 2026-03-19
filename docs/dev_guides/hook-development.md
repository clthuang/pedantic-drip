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
