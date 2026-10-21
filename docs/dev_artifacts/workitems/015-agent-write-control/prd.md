# PRD: Agent Write Control

## Problem Statement

Currently, all agents with Write/Edit tools have unrestricted access to the entire project directory. This poses risks:

1. **Investigation agents** probing code might accidentally write probe scripts or temp files to production directories
2. **Research agents** creating notes could pollute the codebase
3. **Documentation agents** could accidentally overwrite production code
4. **Worker agents** in non-implementation contexts might modify files they shouldn't

The lack of write boundaries means agents must self-regulate, which is error-prone.

## User Stories

### US1: Sandboxed Investigation
As a developer using investigation agents, I want their scratch files written to a sandbox directory, so that my production code stays clean.

### US2: Protected Production Code
As a developer using non-implementation agents, I want production directories protected from accidental writes, so that only intentional implementation changes affect my codebase.

### US3: Transparent Violations
As a developer, I want to see when an agent attempts to write outside its allowed paths, so that I understand what boundaries are enforced.

## Key Constraint: No Agent Context in Hooks

**Critical finding:** PreToolUse hooks receive only `{tool_name, tool_input}` via stdin. There is no mechanism to identify which agent or skill is making the tool call. The hook cannot distinguish between `implementer` and `documentation-writer` at runtime.

This fundamentally changes the approach.

## Proposed Solution: Path-Based Enforcement

Since hooks cannot detect agent context, we use **path-based rules** that apply to all Write/Edit calls:

1. **Protected paths** - Always blocked for Write/Edit (e.g., `src/`, critical configs)
2. **Documentation paths** - Always allowed (e.g., `docs/`, `*.md`)
3. **Sandbox paths** - Always allowed, encouraged for scratch work
4. **Production paths** - Require explicit user confirmation OR trust main Claude

### Two Approaches

#### Approach A: Trust-Based (Recommended for MVP)

Agent tool restrictions are enforced via **tool declarations in frontmatter** (existing mechanism):
- `documentation-writer`: `tools: [Read, Write, Edit, Glob, Grep]` - can write, but agent instructions limit to docs
- `investigation-agent`: `tools: [Read, Glob, Grep]` - **no Write/Edit tools**
- `implementer`: `tools: [Read, Write, Edit, Bash, Glob, Grep]` - full access

**Hook adds safety net:**
- Protect critical paths from ALL Write/Edit (`.git/`, `node_modules/`, etc.)
- Warn (but allow) writes to potentially dangerous paths
- Provide sandbox as preferred location for scratch work

#### Approach B: Restrictive (Future enhancement)

Require explicit path allowlists:
- All Write/Edit blocked by default
- User must pre-approve paths or use sandbox
- More friction but stronger guarantees

**Recommendation:** Start with Approach A for MVP.

### Sandbox Directory Structure
```
agent_sandbox/
└── 2026-02-04/
    ├── investigation-probe-auth/
    │   └── test_script.py
    ├── research-api-patterns/
    │   └── notes.md
    └── debug-session-123/
        └── repro.py
```

## Agent Tool Restrictions (Existing Mechanism)

The primary control is **which tools agents have access to**:

### Full Write Access (3 agents)
| Agent | Tools | Rationale |
|-------|-------|-----------|
| `implementer` | Read, Write, Edit, Bash, Glob, Grep | Core implementation |
| `generic-worker` | Read, Write, Edit, Bash, Glob, Grep | General purpose |
| `documentation-writer` | Read, Write, Edit, Glob, Grep | Docs only (by instruction) |

### No Write Access (18 agents)
All reviewers, researchers, and investigation agents have **no Write/Edit in their tools list**. This is the primary enforcement mechanism.

## Hook-Based Safety Net

### Protected Paths (Always Blocked)
```
.git/**
node_modules/**
.env*
*.key
*.pem
package-lock.json
yarn.lock
```

### Warned Paths (Allowed with Warning)
```
src/**
plugins/*/agents/*.md
plugins/*/commands/*.md
plugins/*/skills/**
.claude-plugin/**
```

Warning message shown to Claude:
> "Writing to production path: {path}. Ensure this is intentional implementation work."

### Safe Paths (Always Allowed)
```
docs/**
agent_sandbox/**
*.md (project root)
tests/**
```

## Technical Design

### Hook Implementation
```bash
#!/usr/bin/env bash
# write-control.sh - PreToolUse hook for Write/Edit

set -euo pipefail

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path')

# Normalize path
FILE_PATH=$(realpath --relative-to="$PWD" "$FILE_PATH" 2>/dev/null || echo "$FILE_PATH")

# Check protected paths (always block)
PROTECTED_PATTERNS=(
  ".git/*"
  "node_modules/*"
  ".env*"
  "*.key"
  "*.pem"
  "package-lock.json"
  "yarn.lock"
)

for pattern in "${PROTECTED_PATTERNS[@]}"; do
  if [[ "$FILE_PATH" == $pattern ]]; then
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Protected path: $FILE_PATH cannot be modified via Write/Edit tool."
  }
}
EOF
    exit 0
  fi
done

# Check warned paths (allow with warning)
WARNED_PATTERNS=(
  "src/*"
  "plugins/*/agents/*.md"
  "plugins/*/commands/*.md"
  "plugins/*/skills/*"
  ".claude-plugin/*"
)

for pattern in "${WARNED_PATTERNS[@]}"; do
  if [[ "$FILE_PATH" == $pattern ]]; then
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "Production path: $FILE_PATH - ensure this is intentional implementation."
  }
}
EOF
    exit 0
  fi
done

# All other paths: allow silently
exit 0
```

### Policy Configuration (JSON)
```json
{
  "protected": [
    ".git/**",
    "node_modules/**",
    ".env*",
    "*.key",
    "*.pem"
  ],
  "warned": [
    "src/**",
    "plugins/**/agents/*.md",
    "plugins/**/commands/*.md"
  ],
  "safe": [
    "docs/**",
    "agent_sandbox/**",
    "tests/**"
  ]
}
```

## Skills and Main Session

**Skills are not subagents** - they execute in the main Claude context with full tool access.

Skill write restrictions work through:
1. **Skill instructions** - Tell Claude where to write (e.g., "Write spec to docs/features/{id}/spec.md")
2. **Hook safety net** - Block protected paths, warn on production paths
3. **Agent discipline** - Skills don't spawn agents with broader permissions than needed

No special enforcement needed beyond the hook.

## Success Metrics

1. **Zero accidental production writes** - No writes to `.git/`, `node_modules/`, etc.
2. **Clear feedback** - Blocked writes show reason; warned writes show caution
3. **No implementation friction** - `implementer` works normally with warnings only
4. **Sandbox adoption** - Investigation/research work goes to `agent_sandbox/`

## Implementation Phases

### Phase 1: Protected Paths Hook
- Create PreToolUse hook for Write/Edit
- Block writes to `.git/`, `node_modules/`, sensitive files
- Add to hooks.json

### Phase 2: Warning System
- Add warned paths (src/, plugins/)
- Show non-blocking warnings for production writes
- Create agent_sandbox/ structure

### Phase 3: Documentation & Cleanup
- Add .gitignore for agent_sandbox/
- Document sandbox usage in agent instructions
- Add date-based cleanup script

## Limitations

1. **Bash bypass** - Bash commands can still write anywhere. Mitigated by most agents not having Bash access.
2. **No agent differentiation** - Hook cannot distinguish implementer from documentation-writer. Mitigated by tool restrictions in frontmatter.
3. **Warning fatigue** - Too many warnings reduce effectiveness. Mitigated by careful path selection.

## Out of Scope

- Bash command interception
- Dynamic policy changes
- Per-project overrides
- Read restrictions

## Open Questions

1. Should sandbox be auto-gitignored or optionally committed?
2. Should there be a "paranoid mode" that blocks all production paths?
3. Should warnings be suppressible via config?

## References

- Investigation: 18/21 agents already have no Write/Edit tools
- Only 3 agents need production write access
- Hook input format: `{tool_name, tool_input}` - no agent context available
