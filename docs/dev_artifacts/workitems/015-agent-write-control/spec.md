# Specification: Agent Write Control

## Overview

This specification defines a PreToolUse hook that enforces path-based write restrictions on Write/Edit tool calls. The hook acts as a safety net, blocking writes to critical paths and warning on production path writes.

## Scope

### In Scope
- PreToolUse hook for Write and Edit tools
- Protected path blocking (always deny)
- Warned path notices (allow with message)
- Sandbox directory structure
- Policy configuration file

### Out of Scope
- Bash command interception
- Agent-specific policies (hooks cannot detect agent context)
- Dynamic policy changes mid-session
- Read restrictions
- Per-project policy overrides

---

## Component Inventory

### New Components

| Type | Name | Location |
|------|------|----------|
| Hook script | write-control.sh | `plugins/iflow-dev/hooks/write-control.sh` |
| Config | write-policies.json | `plugins/iflow-dev/hooks/config/write-policies.json` |
| Directory | agent_sandbox | Project root `agent_sandbox/` (user creates) |
| Gitignore | .gitignore entry | Append to project `.gitignore` |

### Modified Components

| Type | Name | Location | Change |
|------|------|----------|--------|
| Hook config | hooks.json | `plugins/iflow-dev/hooks/hooks.json` | Add PreToolUse entry for Write/Edit |

---

## Detailed Requirements

### REQ-1: Hook Registration

**Description:** Register write-control.sh as a PreToolUse hook for Write and Edit tools.

**Acceptance Criteria:**
- AC-1.1: hooks.json contains PreToolUse entry with matcher `"Write|Edit"`
- AC-1.2: Hook command uses `${CLAUDE_PLUGIN_ROOT}/hooks/write-control.sh`
- AC-1.3: Hook executes for every Write and Edit tool call

**Test Scenarios:**
```
Given: hooks.json configured with Write|Edit matcher
When: Claude calls Write tool
Then: write-control.sh receives tool input on stdin
```

---

### REQ-2: Protected Path Blocking

**Description:** Block Write/Edit to critical paths that should never be modified via these tools.

**Acceptance Criteria:**
- AC-2.1: Writes to `.git/**` are blocked with denial message
- AC-2.2: Writes to `node_modules/**` are blocked
- AC-2.3: Writes to `.env*` files are blocked
- AC-2.4: Writes to `*.key` and `*.pem` files are blocked
- AC-2.5: Writes to `package-lock.json` and `yarn.lock` are blocked
- AC-2.6: Blocked writes return JSON with `permissionDecision: "deny"`
- AC-2.7: Denial message includes the blocked path and reason

**Test Scenarios:**
```
Given: Hook is active
When: Write tool called with file_path ".git/config"
Then: Hook returns deny with message "Protected path: .git/config cannot be modified"

Given: Hook is active
When: Write tool called with file_path "secrets.key"
Then: Hook returns deny with message containing "Protected path"
```

---

### REQ-3: Warned Path Notice

**Description:** Allow writes to production paths but show a warning message to Claude.

**Acceptance Criteria:**
- AC-3.1: Writes to `src/**` show warning but are allowed
- AC-3.2: Writes to `plugins/**/agents/*.md` show warning
- AC-3.3: Writes to `plugins/**/commands/*.md` show warning
- AC-3.4: Writes to `plugins/**/skills/**` show warning
- AC-3.5: Writes to `.claude-plugin/**` show warning
- AC-3.6: Warning returns JSON with `permissionDecision: "allow"` and `permissionDecisionReason`
- AC-3.7: Warning message indicates this is a production path

**Test Scenarios:**
```
Given: Hook is active
When: Write tool called with file_path "src/index.ts"
Then: Hook returns allow with reason "Production path: src/index.ts - ensure this is intentional"

Given: Hook is active
When: Write tool called with file_path "plugins/iflow-dev/agents/new-agent.md"
Then: Hook returns allow with warning about production path
```

---

### REQ-4: Safe Path Passthrough

**Description:** Allow writes to documentation and sandbox paths without any message.

**Acceptance Criteria:**
- AC-4.1: Writes to `docs/**` are silently allowed
- AC-4.2: Writes to `agent_sandbox/**` are silently allowed
- AC-4.3: Writes to `tests/**` are silently allowed
- AC-4.4: Writes to `*.md` in project root are silently allowed
- AC-4.5: Silent allow means hook exits 0 with no output

**Test Scenarios:**
```
Given: Hook is active
When: Write tool called with file_path "docs/README.md"
Then: Hook exits 0 with no output (silent allow)

Given: Hook is active
When: Write tool called with file_path "agent_sandbox/2026-02-04/test/script.py"
Then: Hook exits 0 with no output
```

---

### REQ-5: Path Normalization

**Description:** Normalize file paths before pattern matching to handle relative and absolute paths.

**Acceptance Criteria:**
- AC-5.1: Absolute paths are converted to project-relative paths
- AC-5.2: Paths like `/full/path/to/project/src/file.ts` match `src/**`
- AC-5.3: Paths with `./` prefix are normalized
- AC-5.4: Missing files still have their paths evaluated (path doesn't need to exist)

**Test Scenarios:**
```
Given: Project root is /Users/terry/project
When: Write tool called with file_path "/Users/terry/project/src/file.ts"
Then: Path is normalized to "src/file.ts" and matches warned pattern

Given: Hook is active
When: Write tool called with file_path "./docs/new-doc.md"
Then: Path is normalized to "docs/new-doc.md" and silently allowed
```

---

### REQ-6: Policy Configuration

**Description:** Load path patterns from a configuration file.

**Acceptance Criteria:**
- AC-6.1: Hook reads patterns from `write-policies.json`
- AC-6.2: Config contains `protected`, `warned`, and `safe` arrays
- AC-6.3: Missing config file uses hardcoded defaults
- AC-6.4: Invalid JSON in config is handled gracefully (use defaults)

**Configuration Schema:**
```json
{
  "protected": ["pattern1", "pattern2"],
  "warned": ["pattern1", "pattern2"],
  "safe": ["pattern1", "pattern2"]
}
```

**Test Scenarios:**
```
Given: write-policies.json exists with custom protected paths
When: Hook evaluates a path
Then: Custom patterns are used for matching

Given: write-policies.json is missing
When: Hook evaluates a path
Then: Hardcoded default patterns are used
```

---

### REQ-7: Sandbox Directory

**Description:** Provide a standard location for scratch/investigation work.

**Acceptance Criteria:**
- AC-7.1: Sandbox root is `agent_sandbox/` in project root
- AC-7.2: Sandbox structure is `agent_sandbox/{date}/{context}/`
- AC-7.3: Date format is `YYYY-MM-DD`
- AC-7.4: Context is a meaningful directory name (not auto-generated)
- AC-7.5: `agent_sandbox/` is in `.gitignore`

**Example Structure:**
```
agent_sandbox/
└── 2026-02-04/
    ├── auth-investigation/
    │   └── probe.py
    └── api-research/
        └── notes.md
```

---

### REQ-8: Default Behavior

**Description:** Paths not matching any pattern category are silently allowed.

**Acceptance Criteria:**
- AC-8.1: Paths not in protected, warned, or safe lists are allowed
- AC-8.2: No message is shown for unmatched paths
- AC-8.3: Hook exits 0 with no output for unmatched paths

**Test Scenarios:**
```
Given: Hook is active, path "random/file.txt" matches no patterns
When: Write tool called with file_path "random/file.txt"
Then: Hook exits 0 with no output (silent allow)
```

---

### REQ-9: Glob Pattern Matching

**Description:** Use glob-style patterns for path matching.

**Acceptance Criteria:**
- AC-9.1: `*` matches any single path segment
- AC-9.2: `**` matches any number of path segments
- AC-9.3: `*.ext` matches files with extension in current directory
- AC-9.4: Pattern matching is case-sensitive
- AC-9.5: Patterns are matched against normalized relative paths

**Pattern Examples:**
| Pattern | Matches | Does Not Match |
|---------|---------|----------------|
| `.git/**` | `.git/config`, `.git/hooks/pre-commit` | `.github/workflows` |
| `*.key` | `server.key`, `api.key` (root only) | `keys/server.key` (subdirectory) |
| `src/**` | `src/index.ts`, `src/lib/util.ts` | `test/src/mock.ts` |
| `plugins/**/agents/*.md` | `plugins/iflow/agents/foo.md` | `plugins/iflow/skills/foo.md` |
| `*.md` | `README.md`, `CHANGELOG.md` (root only) | `docs/guide.md` (use `docs/**` instead) |

**Note:** Patterns without `**/` prefix match only at the specified depth. `*.md` matches root-level markdown files only.

---

### REQ-10: Error Handling (Fail-Open)

**Description:** Hook errors should not block legitimate writes. Fail-open on errors.

**Acceptance Criteria:**
- AC-10.1: If hook script exits non-zero, the tool call proceeds
- AC-10.2: If stdin JSON is invalid, hook exits 0 (allow silently)
- AC-10.3: If config file has invalid JSON, use hardcoded defaults
- AC-10.4: If path normalization fails, use original path as-is

**Test Scenarios:**
```
Given: Hook script has a bug causing exit 1
When: Write tool is called
Then: Write proceeds (fail-open)

Given: Hook receives malformed JSON on stdin
When: Hook parses input
Then: Hook exits 0, write proceeds
```

---

## Verification Checklist

### Phase 1: Hook Infrastructure
- [ ] hooks.json has PreToolUse entry for Write|Edit
- [ ] write-control.sh is executable
- [ ] Hook receives stdin JSON with tool_name and tool_input
- [ ] Hook returns valid JSON for deny/allow decisions

### Phase 2: Path Enforcement
- [ ] Protected paths are blocked with deny
- [ ] Warned paths show message but allow
- [ ] Safe paths are silently allowed
- [ ] Unmatched paths default to silently allowed (REQ-8)

### Phase 3: Configuration & Cleanup
- [ ] write-policies.json is read and applied
- [ ] Missing config uses defaults
- [ ] agent_sandbox/ is in .gitignore
- [ ] Documentation updated

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Hook script fails (exit non-0) | Tool call proceeds (fail-open) |
| Invalid JSON in stdin | Exit 0, allow silently |
| Invalid config file | Use hardcoded defaults |
| Path normalization fails | Use original path as-is |

---

## Non-Functional Requirements

- **Latency:** Hook execution < 50ms (no network calls, minimal processing)
- **Reliability:** Fail-open - if hook fails, writes proceed
- **Compatibility:** Works with existing pre-commit-guard.sh hook

---

## Dependencies

- python3 (for JSON parsing in bash - consistent with pre-commit-guard.sh)
- bash 4+ (for pattern matching)
- Existing hooks infrastructure (hooks.json, ${CLAUDE_PLUGIN_ROOT})
- gtimeout/timeout (optional, for stdin timeout protection)

---

## Deferred Decisions

The following PRD open questions are not addressed in MVP:

1. **Paranoid mode** - A stricter mode that blocks all production paths (not just warns) is deferred to future enhancement.
2. **Suppressible warnings** - Config option to suppress warnings for specific paths is deferred.

These can be added in future iterations based on user feedback.

---

## Success Metrics Traceability

| PRD Metric | Requirements |
|------------|--------------|
| Zero accidental production writes | REQ-2 (protected paths blocked) |
| Clear feedback | REQ-2.7 (denial reason), REQ-3.6-3.7 (warning message) |
| No implementation friction | REQ-3 (warned, not blocked), REQ-8 (unmatched allowed) |
| Sandbox adoption | REQ-7 (sandbox structure), REQ-4.2 (sandbox is safe path) |

---

## Industry Alignment

This design aligns with industry patterns:

| Pattern | Our Implementation |
|---------|-------------------|
| gitignore-style exclusion (Roo, Gemini) | write-policies.json with glob patterns |
| Path-based deny lists (Claude Code, Copilot) | Protected paths list with explicit deny |
| Fail-open for usability (NVIDIA guidance) | REQ-10: Hook errors allow writes |
| Ephemeral sandbox (NVIDIA guidance) | agent_sandbox/ is gitignored |

**Note:** Research confirmed `.claudeignore` is unreliable for preventing file access. Our hook-based approach with explicit deny patterns is the recommended solution per Claude Code documentation.
