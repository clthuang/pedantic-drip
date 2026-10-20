# Design: Agent Write Control

## 1. Architecture Overview

### System Context

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude Code Runtime                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────┐    ┌──────────────┐    ┌─────────────────┐   │
│  │  Write  │───▶│  PreToolUse  │───▶│  write-control  │   │
│  │  Edit   │    │    Hook      │    │      .sh        │   │
│  └─────────┘    └──────────────┘    └────────┬────────┘   │
│                                              │             │
│                                              ▼             │
│                                    ┌─────────────────┐    │
│                                    │ write-policies  │    │
│                                    │     .json       │    │
│                                    └─────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │         File System           │
              ├───────────────────────────────┤
              │ Protected: .git/, node_modules│
              │ Warned:    src/, plugins/     │
              │ Safe:      docs/, agent_sandbox│
              └───────────────────────────────┘
```

### Data Flow

```
1. Claude calls Write/Edit tool
       │
       ▼
2. hooks.json routes to write-control.sh
       │
       ▼
3. Hook reads stdin JSON: {tool_name, tool_input}
       │
       ▼
4. Extract and normalize file_path
       │
       ▼
5. Load policies from write-policies.json (or defaults)
       │
       ▼
6. Match path against patterns (order: protected → warned → safe)
       │
       ├──▶ Protected match: Return deny JSON
       │
       ├──▶ Warned match: Return allow JSON with reason
       │
       ├──▶ Safe match: Exit 0 (silent allow)
       │
       └──▶ No match: Exit 0 (silent allow, default behavior)
```

---

## 2. Components

### 2.1 Hook Script: write-control.sh

**Location:** `plugins/iflow-dev/hooks/write-control.sh`

**Responsibility:** Intercept Write/Edit tool calls, evaluate path against policies, return decision.

**Interface:**
- **Input:** JSON on stdin `{"tool_name": "Write|Edit", "tool_input": {"file_path": "...", ...}}`
- **Output:**
  - Deny: JSON with `permissionDecision: "deny"` and reason
  - Allow with warning: JSON with `permissionDecision: "allow"` and reason
  - Silent allow: Exit 0 with no output

**Dependencies:**
- python3 (JSON parsing - consistent with pre-commit-guard.sh)
- bash 4+ (pattern matching)
- lib/common.sh (shared utilities: `escape_json`, `detect_project_root`)
- gtimeout/timeout (optional, for stdin timeout protection)

**Reused from lib/common.sh:**
- `escape_json` - for safe JSON output
- `detect_project_root` - for finding project root (note: NOT used for path normalization since PWD is already project root)

**Error Handling:**
- Invalid stdin JSON → Exit 0 (fail-open)
- Script error → Exit non-zero, Claude proceeds (fail-open)
- stdin timeout → Use empty input, exit 0 (fail-open)

---

### 2.2 Policy Configuration: write-policies.json

**Location:** `plugins/iflow-dev/hooks/config/write-policies.json`

**Responsibility:** Define path patterns for protected, warned, and safe categories.

**Schema:**
```json
{
  "protected": [
    ".git/**",
    "node_modules/**",
    ".env*",
    "*.key",
    "*.pem",
    "package-lock.json",
    "yarn.lock"
  ],
  "warned": [
    "src/**",
    "plugins/**/agents/*.md",
    "plugins/**/commands/*.md",
    "plugins/**/skills/**",
    ".claude-plugin/**"
  ],
  "safe": [
    "docs/**",
    "agent_sandbox/**",
    "tests/**",
    "*.md"
  ]
}
```

**Behavior:**
- File missing → Use hardcoded defaults in script
- Invalid JSON → Use hardcoded defaults (no logging - fail-open silently)

---

### 2.3 Hook Registration: hooks.json

**Location:** `plugins/iflow-dev/hooks/hooks.json`

**Change:** Add PreToolUse entry for Write|Edit matcher.

**Existing Structure:**
```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "...", "hooks": [...] }
    ]
  }
}
```

**New Entry to Add to PreToolUse array:**
```json
{
  "matcher": "Write|Edit",
  "hooks": [
    {
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/write-control.sh"
    }
  ]
}
```

**Note:** `${CLAUDE_PLUGIN_ROOT}` is expanded by Claude Code at runtime to the plugin's absolute path.

---

### 2.4 Sandbox Directory

**Location:** Project root `agent_sandbox/`

**Structure:**
```
agent_sandbox/
└── {YYYY-MM-DD}/
    └── {context-name}/
        └── {files}
```

**Management:**
- Created by agents as needed (not pre-created)
- Gitignored via `.gitignore` entry
- User manually cleans up old dates

---

## 3. Technical Decisions

### TD-1: Pattern Matching Strategy

**Decision:** Use regex-based pattern matching with escaped special characters.

**Rationale:**
- Predictable behavior for `*` and `**` patterns
- Handles literal dots and special characters correctly
- Single implementation, no ambiguity

**Pattern Conversion Rules:**
1. Escape regex special characters (`.`, `+`, `?`)
2. Convert `**` to `(.*)?` (match zero or more of anything) - MUST happen before step 3
3. Convert `*` to `[^/]*` (match any characters except `/`)
4. Anchor pattern with `^` and `$`

**Implementation:** See Contract 5 for the complete `matches_pattern()` function with edge case handling.

---

### TD-2: Policy Loading Strategy

**Decision:** Load policies once at script start, with fallback to hardcoded defaults.

**Rationale:**
- Single file read per hook invocation
- Predictable behavior if config missing
- No caching complexity

**Trade-offs:**
- (+) Simple, fast
- (-) Config changes require new tool call
- (-) Hardcoded defaults duplicated in script

---

### TD-3: Path Normalization Approach

**Decision:** Convert absolute paths to project-relative using `${PWD}` as base, with validation for paths outside project.

**Rationale:**
- Claude Code often passes absolute paths
- Patterns should work regardless of path format
- Project root is stable reference point
- Paths outside project should be blocked for safety

**Context:** Claude Code hooks execute with `PWD` set to the project root (the directory containing `.claude/` or where Claude was invoked). This is guaranteed by the Claude Code runtime.

**Implementation:**
```bash
normalize_path() {
  local path="$1"

  # Handle relative paths that escape project (e.g., ../other/file)
  if [[ "$path" == ../* ]]; then
    echo "OUTSIDE_PROJECT"
    return
  fi

  # Handle absolute paths
  if [[ "$path" == /* ]]; then
    # Check if path is within project root
    if [[ "$path" == "$PWD/"* ]]; then
      # Strip project root prefix
      path="${path#$PWD/}"
    else
      # Path is outside project
      echo "OUTSIDE_PROJECT"
      return
    fi
  fi

  # Remove ./ prefix
  path="${path#./}"

  # Remove trailing slash (directories passed as src/ → src)
  path="${path%/}"

  echo "$path"
}
```

**Handling Outside-Project Paths:**
- Paths that resolve outside the project root are marked as `OUTSIDE_PROJECT`
- These are treated as protected (blocked) for safety
- This prevents accidental writes to system files like `/etc/passwd`

---

### TD-4: Evaluation Order

**Decision:** Evaluate in order: protected → warned → safe → default allow.

**Rationale:**
- Security-first: check dangerous patterns first
- Clear precedence for overlapping patterns
- Default allow is fail-open safety net

**Example:**
```
Path: src/secrets.key
1. Check protected: *.key matches → DENY
(Never reaches warned check for src/**)
```

---

### TD-5: JSON Response Format

**Decision:** Use Claude Code's hookSpecificOutput format.

**Deny Response:**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Protected path: .git/config cannot be modified via Write/Edit tool."
  }
}
```

**Allow with Warning:**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "Production path: src/index.ts - ensure this is intentional implementation."
  }
}
```

**Silent Allow:**
```bash
exit 0  # No output
```

---

## 4. Interfaces

**Note:** TypeScript interfaces in this section are documentation-only. They describe the JSON structure for clarity but are not enforced at runtime. The hook script is pure bash and validates JSON structure using python3.

### Interface 1: Hook Input (stdin)

**Format:** JSON object
```typescript
interface HookInput {
  tool_name: "Write" | "Edit";
  tool_input: {
    file_path: string;      // Absolute or relative path
    content?: string;       // For Write tool
    old_string?: string;    // For Edit tool
    new_string?: string;    // For Edit tool
  };
}
```

**Example:**
```json
{
  "tool_name": "Write",
  "tool_input": {
    "file_path": "/Users/terry/project/src/index.ts",
    "content": "console.log('hello');"
  }
}
```

---

### Interface 2: Hook Output (stdout/exit code)

**Deny:**
```typescript
interface DenyResponse {
  hookSpecificOutput: {
    hookEventName: "PreToolUse";
    permissionDecision: "deny";
    permissionDecisionReason: string;
  };
}
```

**Allow with Message:**
```typescript
interface AllowResponse {
  hookSpecificOutput: {
    hookEventName: "PreToolUse";
    permissionDecision: "allow";
    permissionDecisionReason: string;
  };
}
```

**Silent Allow:**
- Exit code: 0
- stdout: empty

---

### Interface 3: Policy Configuration

**File:** `write-policies.json`

```typescript
interface WritePolicies {
  protected: string[];  // Glob patterns to deny
  warned: string[];     // Glob patterns to allow with warning
  safe: string[];       // Glob patterns to allow silently
}
```

---

### Interface 4: hooks.json Entry

```typescript
interface HooksJsonEntry {
  matcher: string;  // Regex pattern for tool name
  hooks: Array<{
    type: "command";
    command: string;  // Path to hook script
  }>;
}
```

---

## 5. Error Handling

| Error | Detection | Response | Rationale |
|-------|-----------|----------|-----------|
| Invalid stdin JSON | python3 parse fails | Exit 0 | Fail-open |
| Missing config file | File not found | Use defaults | Predictable fallback |
| Invalid config JSON | python3 parse fails | Use defaults silently | Fail-open, no logging |
| Path normalization fails | realpath/substitution fails | Use original path | Best effort |
| Path outside project | OUTSIDE_PROJECT marker | Block (deny) | Security boundary |
| Script crash | Non-zero exit | Claude proceeds | Fail-open by design |

**Note on Logging:** This hook produces no logging output. All errors fail silently (exit 0) to maintain fail-open behavior. The only outputs are:
- JSON to stdout for deny/allow-with-warning decisions
- Exit code 0 for all cases (including errors)

---

## 6. Risks and Mitigations

### Risk 1: Bash Bypass

**Risk:** Agents with Bash access can bypass Write/Edit restrictions using shell commands.

**Mitigation:**
- Most agents don't have Bash tool
- Only `implementer` and `generic-worker` have Bash
- Document as known limitation
- Future: Consider Bash file operation interception

**Severity:** Medium (limited exposure)

---

### Risk 2: Pattern Overlap Confusion

**Risk:** Overlapping patterns could cause unexpected behavior.

**Mitigation:**
- Clear evaluation order (protected → warned → safe)
- Document precedence rules
- Test with overlapping patterns

**Example:**
```
Pattern: *.md (safe) vs plugins/**/*.md (warned)
Path: plugins/iflow/agents/test.md
Result: Warned (checked before safe)
```

**Severity:** Low (deterministic behavior)

---

### Risk 3: Performance Impact

**Risk:** Hook adds latency to every Write/Edit call.

**Mitigation:**
- Minimal processing (python3 + bash matching)
- No network calls
- No file reads except small config
- Target: <50ms per invocation

**Severity:** Low (simple operations)

---

### Risk 4: False Positives

**Risk:** Legitimate writes blocked incorrectly.

**Mitigation:**
- Fail-open design
- Protected list is minimal (clear security targets)
- Warned paths allow with message (not blocked)
- Easy to update config

**Severity:** Low (fail-open + config flexibility)

---

### Risk 5: Symlink Bypass

**Risk:** A symlink from a safe path to a protected path could bypass restrictions.

**Mitigation:**
- Claude Code typically passes canonical paths from tools
- Path normalization operates on string patterns, not filesystem resolution
- Accepted limitation: symlinks are a user-created filesystem construct
- Future consideration: Add `realpath` resolution if this becomes a problem

**Severity:** Low (requires deliberate symlink creation by user)

---

## 7. Testing Strategy

### Unit Tests
- Pattern matching: Test each pattern type
- Path normalization: Test absolute, relative, `./` prefixed
- JSON parsing: Test valid, invalid, missing fields
- Outside-project paths: Test `../` and absolute paths outside project

### Integration Tests
- Hook registration: Verify hooks.json routes correctly
- End-to-end: Write to protected path → denied
- End-to-end: Write to warned path → allowed with message
- End-to-end: Write to safe path → silent allow
- End-to-end: Write to outside-project path → denied

### Test Execution

**Test File Location:** `plugins/iflow-dev/hooks/tests/test-write-control.sh`

**Integration with existing tests:** The existing `test-hooks.sh` tests pre-commit-guard.sh. The new `test-write-control.sh` follows the same pattern but is a separate file for:
- Isolation of concerns (each hook has its own test file)
- Independent execution during development
- Both are executed by `validate.sh`

**validate.sh Integration:** The existing `validate.sh` script runs all `test-*.sh` files in the hooks/tests directory. No changes to validate.sh are needed - the new `test-write-control.sh` will be automatically discovered and executed.

**Test Framework:** Pure bash with assertions (no external test framework required)

**Running Tests:**
```bash
# From plugin root
./hooks/tests/test-write-control.sh

# Or via validate.sh
./validate.sh  # Includes hook tests
```

**Test Structure:**
```bash
#!/usr/bin/env bash
set -euo pipefail

# Source the script functions (not main)
source "${BASH_SOURCE%/*}/../write-control.sh" --source-only

# Test helper
assert_eq() {
  local expected="$1" actual="$2" msg="$3"
  if [[ "$expected" != "$actual" ]]; then
    echo "FAIL: $msg (expected: $expected, got: $actual)"
    exit 1
  fi
  echo "PASS: $msg"
}

# Example test
test_pattern_matching_star() {
  matches_pattern "file.md" "*.md" && assert_eq "0" "$?" "*.md matches file.md"
  matches_pattern "dir/file.md" "*.md" || assert_eq "1" "$?" "*.md does not match dir/file.md"
}

# Run tests
test_pattern_matching_star
# ... more tests
```

---

## 8. Detailed Interface Contracts

### Contract 1: write-control.sh Script

**File:** `plugins/iflow-dev/hooks/write-control.sh`

**Shebang and Options:**
```bash
#!/usr/bin/env bash
set -euo pipefail
```

**Public Interface:**
```
Input:  stdin (JSON)
Output: stdout (JSON or empty)
Exit:   0 (allow), any other value triggers fail-open

Required: python3, bash 4+
Optional: gtimeout/timeout (for stdin protection)
```

**Internal Functions:**

| Function | Signature | Description |
|----------|-----------|-------------|
| `read_tool_input` | `read_tool_input` | Read stdin with timeout, extract file_path |
| `normalize_path` | `normalize_path <path>` | Convert absolute/relative to project-relative |
| `load_policies` | `load_policies` | Load from config or use defaults |
| `matches_pattern` | `matches_pattern <path> <pattern>` | Check if path matches glob pattern |
| `check_protected` | `check_protected <path>` | Return 0 if protected, 1 otherwise |
| `check_warned` | `check_warned <path>` | Return 0 if warned, 1 otherwise |
| `check_safe` | `check_safe <path>` | Return 0 if safe, 1 otherwise |
| `emit_deny` | `emit_deny <path> <reason>` | Output deny JSON to stdout (uses `escape_json`) |
| `emit_allow_warning` | `emit_allow_warning <path> <reason>` | Output allow JSON with reason (uses `escape_json`) |

**Algorithm:**
```bash
# Read stdin with timeout protection (consistent with pre-commit-guard.sh)
read_tool_input() {
  local input timeout_cmd=""
  if command -v gtimeout &>/dev/null; then
    timeout_cmd="gtimeout 5"
  elif command -v timeout &>/dev/null; then
    timeout_cmd="timeout 5"
  fi

  if [[ -n "$timeout_cmd" ]]; then
    input=$($timeout_cmd cat || echo '{}')
  else
    input=$(cat)
  fi

  # Extract file_path using python3 (consistent with pre-commit-guard.sh)
  echo "$input" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''))
except:
    print('')
" 2>/dev/null
}

main() {
  local ORIGINAL_PATH
  ORIGINAL_PATH=$(read_tool_input)

  if [[ -z "$ORIGINAL_PATH" ]]; then
    exit 0  # No path, allow silently
  fi

  FILE_PATH=$(normalize_path "$ORIGINAL_PATH")

  # Block paths outside project
  if [[ "$FILE_PATH" == "OUTSIDE_PROJECT" ]]; then
    emit_deny "$ORIGINAL_PATH" "Path outside project boundary"
    exit 0
  fi

  load_policies

  if check_protected "$FILE_PATH"; then
    emit_deny "$FILE_PATH" "Protected path cannot be modified"
    exit 0
  fi

  if check_warned "$FILE_PATH"; then
    emit_allow_warning "$FILE_PATH" "Production path - ensure intentional"
    exit 0
  fi

  # Safe or unmatched: silent allow
  exit 0
}

# Support --source-only for testing (allows sourcing functions without running main)
if [[ "${1:-}" != "--source-only" ]]; then
  main
fi
```

---

### Contract 2: write-policies.json Configuration

**File:** `plugins/iflow-dev/hooks/config/write-policies.json`

**Full Schema:**
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "protected": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Glob patterns for paths that should be blocked"
    },
    "warned": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Glob patterns for paths that should show warning"
    },
    "safe": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Glob patterns for paths that are silently allowed"
    }
  },
  "required": ["protected", "warned", "safe"]
}
```

**Default Values (hardcoded in script):**
```bash
DEFAULT_PROTECTED=(
  ".git/**"
  "node_modules/**"
  ".env*"
  "*.key"
  "*.pem"
  "package-lock.json"
  "yarn.lock"
)

DEFAULT_WARNED=(
  "src/**"
  "plugins/**/agents/*.md"
  "plugins/**/commands/*.md"
  "plugins/**/skills/**"
  ".claude-plugin/**"
)

DEFAULT_SAFE=(
  "docs/**"
  "agent_sandbox/**"
  "tests/**"
  "*.md"
)
```

**Policy Loading Implementation:**
```bash
# Global arrays populated by load_policies
PROTECTED_PATTERNS=()
WARNED_PATTERNS=()
SAFE_PATTERNS=()

load_policies() {
  local config_file="${SCRIPT_DIR}/config/write-policies.json"

  if [[ -f "$config_file" ]]; then
    # Use python3 to parse JSON and output newline-separated patterns
    local protected warned safe
    protected=$(python3 -c "
import json, sys
try:
    with open('$config_file') as f:
        data = json.load(f)
    for p in data.get('protected', []): print(p)
except: pass
" 2>/dev/null)
    warned=$(python3 -c "
import json, sys
try:
    with open('$config_file') as f:
        data = json.load(f)
    for p in data.get('warned', []): print(p)
except: pass
" 2>/dev/null)
    safe=$(python3 -c "
import json, sys
try:
    with open('$config_file') as f:
        data = json.load(f)
    for p in data.get('safe', []): print(p)
except: pass
" 2>/dev/null)

    # Convert to arrays (empty output = use defaults)
    if [[ -n "$protected" ]]; then
      mapfile -t PROTECTED_PATTERNS <<< "$protected"
    else
      PROTECTED_PATTERNS=("${DEFAULT_PROTECTED[@]}")
    fi

    if [[ -n "$warned" ]]; then
      mapfile -t WARNED_PATTERNS <<< "$warned"
    else
      WARNED_PATTERNS=("${DEFAULT_WARNED[@]}")
    fi

    if [[ -n "$safe" ]]; then
      mapfile -t SAFE_PATTERNS <<< "$safe"
    else
      SAFE_PATTERNS=("${DEFAULT_SAFE[@]}")
    fi
  else
    # Config missing: use defaults
    PROTECTED_PATTERNS=("${DEFAULT_PROTECTED[@]}")
    WARNED_PATTERNS=("${DEFAULT_WARNED[@]}")
    SAFE_PATTERNS=("${DEFAULT_SAFE[@]}")
  fi
}
```

---

### Contract 3: hooks.json Registration

**File:** `plugins/iflow-dev/hooks/hooks.json`

**Existing Structure:**
```json
{
  "hooks": {
    "SessionStart": [...],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [...]
      }
    ]
  }
}
```

**New PreToolUse Entry (append to PreToolUse array):**
```json
{
  "matcher": "Write|Edit",
  "hooks": [
    {
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/write-control.sh"
    }
  ]
}
```

**Variable Expansion:**
- `${CLAUDE_PLUGIN_ROOT}` is expanded by Claude Code at runtime
- Resolves to absolute path of the plugin directory
- Example: `/Users/terry/projects/my-ai-setup/plugins/iflow-dev`

**Ordering Note:**
- Place after existing PreToolUse entries (e.g., pre-commit-guard.sh for Bash)
- Multiple hooks can apply to same tool; all are executed
- Each matcher is evaluated independently

---

### Contract 4: Sandbox Directory Convention

**Location:** `{PROJECT_ROOT}/agent_sandbox/`

**Path Format:**
```
agent_sandbox/{YYYY-MM-DD}/{context-name}/{files}
```

**Constraints:**
- `{YYYY-MM-DD}`: ISO date format, e.g., `2026-02-04`
- `{context-name}`: Lowercase, hyphen-separated, descriptive
- No auto-generation; agents choose meaningful names

**Examples:**
```
agent_sandbox/2026-02-04/auth-probe/test.py       # Good
agent_sandbox/2026-02-04/session-12345/file.txt  # Avoid: meaningless context
```

**Gitignore Entry:**
```
# Agent sandbox (temporary investigation files)
agent_sandbox/
```

**Implementation Note:** The implementation must add this entry to the project's `.gitignore` if not already present. Check for existing entry before appending to avoid duplicates:
```bash
if ! grep -q '^agent_sandbox/' .gitignore 2>/dev/null; then
  echo -e "\n# Agent sandbox (temporary investigation files)\nagent_sandbox/" >> .gitignore
fi
```
This is part of Phase 3 (Documentation & Cleanup) per the spec verification checklist.

---

### Contract 5: Pattern Matching Behavior

**Glob Syntax:**
| Pattern | Meaning |
|---------|---------|
| `*` | Match any characters except `/` (single segment) |
| `**` | Match zero or more path segments (including none) |
| `?` | Match single character except `/` |

**Pattern Semantics:**
| Pattern | Matches | Does Not Match |
|---------|---------|----------------|
| `*.md` | `README.md` (root only) | `docs/file.md` |
| `**/*.md` | `docs/file.md`, `a/b/c.md` | - |
| `src/**` | `src/a.ts`, `src/a/b.ts` | `src` (no trailing content) |
| `.env*` | `.env`, `.env.local` | `env`, `xenv` |
| `.git/**` | `.git/config`, `.git/hooks/x` | `.github/` |

**Note on trailing slashes:** Claude Code typically passes file paths without trailing slashes. Directory paths like `src/` are normalized to `src` before matching. The pattern `src/**` requires content after `src/`, so it matches `src/file` but not `src` alone. This is intentional - we're protecting files within directories, not the directory entries themselves.

**Matching Rules:**
1. Patterns matched against normalized relative path
2. Leading `./` and project root prefix stripped before matching
3. Case-sensitive matching
4. First match wins (evaluation order: protected → warned → safe)
5. Paths outside project root are BLOCKED (treated as protected)

**Implementation:**
```bash
matches_pattern() {
  local path="$1" pattern="$2"

  # Step 1: Escape regex special characters commonly found in paths
  # Note: We escape ., +, and handle ? specially. Other regex chars
  # (^, $, [, ], |, etc.) are unlikely in path patterns and not escaped.
  local regex="$pattern"
  regex="${regex//./\\.}"        # . → \. (literal dot)
  regex="${regex//+/\\+}"        # + → \+
  regex="${regex//\?/[^/]}"      # ? → match single non-slash char

  # Step 2: Handle ** BEFORE * (order matters!)
  # ** at end: match zero or more of anything
  regex="${regex//\*\*/(.*)?}"

  # Step 3: Handle * (must be after ** replacement)
  # * matches any chars except slash
  regex="${regex//\*/[^/]*}"

  # Step 4: Anchor the pattern
  [[ "$path" =~ ^${regex}$ ]]
}
```

**Edge Cases:**
| Path | Pattern | Result | Why |
|------|---------|--------|-----|
| `src/file.ts` | `src/**` | MATCH | `(.*)? ` matches `/file.ts` |
| `src` | `src/**` | NO MATCH | Pattern requires `/` after `src` |
| `.env.local` | `.env*` | MATCH | `\.env[^/]*` matches |
| `myenv` | `.env*` | NO MATCH | Escaped dot requires literal `.` |
| `/etc/passwd` | (any) | BLOCKED | Path outside project |
| `../other/file` | (any) | BLOCKED | Path escapes project |

---

## 9. Implementation Notes

### Existing Code Reference

The existing `pre-commit-guard.sh` provides a pattern for:
- Reading stdin JSON with timeout protection
- Using python3 for JSON parsing
- Returning hook responses
- Error handling with fail-open

**File:** `plugins/iflow-dev/hooks/pre-commit-guard.sh`

### Config Directory

Create new config directory for policy files:
```
plugins/iflow-dev/hooks/
├── config/
│   └── write-policies.json  # NEW
├── lib/
│   └── common.sh
├── hooks.json
├── pre-commit-guard.sh
└── write-control.sh          # NEW
```
