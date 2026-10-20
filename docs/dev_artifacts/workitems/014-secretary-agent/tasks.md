# Tasks: Secretary Agent

## Overview

This document breaks down the implementation plan into actionable tasks.
- Each task is 5-15 minutes
- Tasks have binary done criteria
- Parallel groups marked for concurrent execution

---

## Phase 0: Interface Contract Review (Prerequisite Gate)

**Parallel Group:** None (must complete before parallel branches)

### Task 0.1: Review Interface 7 (Configuration)
**File:** `/Users/terry/projects/my-ai-setup/docs/features/014-secretary-agent/design.md` (read-only)
**Action:** Read Interface 7, write down the 4 key points below
**Key Points to Extract:**
- Config location: `.claude/secretary.local.md`
- Schema fields: activation_mode, preferred_review_agents, auto_create_missing, supervision_level
- Default mode: manual
- Default behavior when config missing: use manual mode
**Done When:** All 4 key points written in notes/comments
**Acceptance:** Written notes contain: (1) file path, (2) all 4 field names, (3) default mode value, (4) missing-config behavior

### Task 0.2: Review Interface 1 (Command → Agent)
**File:** `/Users/terry/projects/my-ai-setup/docs/features/014-secretary-agent/design.md` (read-only)
**Action:** Read Interface 1, write the exact Task tool invocation template
**Key Points to Extract:**
- Task tool invocation format: `{subagent_type: "iflow-dev:secretary", description, prompt}`
- Description field purpose: brief summary
- Prompt field purpose: contains user request
**Done When:** Task tool template written in notes/comments
**Acceptance:** Written notes contain exact invocation: `Task({ subagent_type: "iflow-dev:secretary", description: "...", prompt: "..." })`

### Task 0.3: Review Interface 8 (Hook Output)
**File:** `/Users/terry/projects/my-ai-setup/docs/features/014-secretary-agent/design.md` (read-only)
**Action:** Read Interface 8, write the exact JSON output structure
**Key Points to Extract:**
- Output structure: `{hookSpecificOutput: {hookEventName, additionalContext}}`
- hookEventName value: "SessionStart"
- additionalContext purpose: describes secretary availability
**Done When:** JSON template written in notes/comments
**Acceptance:** Written notes contain exact structure: `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}`

---

## Phase 1: Configuration Component (Branch A)

**Parallel Group:** A (can run parallel with Phase 4)
**Blocks:** Phase 2

### Task 1.1: Create templates directory
**Command:** `mkdir -p /Users/terry/projects/my-ai-setup/plugins/iflow-dev/templates`
**Verification:** `ls /Users/terry/projects/my-ai-setup/plugins/iflow-dev/templates`
**Done When:** Directory exists (ls command succeeds)
**Acceptance:** Directory created and listed

### Task 1.2: Create config template file
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/templates/secretary.local.md`
**Content:** File contains only YAML frontmatter (no markdown body):
```yaml
---
activation_mode: manual
preferred_review_agents: []
auto_create_missing: false
supervision_level: light
---
```
**Note:** Ensure file ends with a newline character after final `---`
**Done When:** File exists with content above
**Acceptance:** File parseable by grep/sed pattern (verified in Task 1.3)

### Task 1.3: Verify config parsing pattern
**Test:** Run grep/sed on template file
```bash
grep "^activation_mode:" /Users/terry/projects/my-ai-setup/plugins/iflow-dev/templates/secretary.local.md | head -1 | sed 's/^[^:]*: *//' | tr -d ' '
```
**Done When:** Returns "manual"
**Acceptance:** Pattern works on template file

---

## Phase 2: Hook Script (Branch A)

**Parallel Group:** A (sequential after Phase 1)
**Depends On:** Phase 1
**Blocks:** Phase 3

### Task 2.1: Create hook script header
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/hooks/inject-secretary-context.sh`
**Done When:** File exists with:
```bash
#!/usr/bin/env bash
# inject-secretary-context.sh - Inject secretary awareness at session start (aware mode only)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"
```
**Acceptance:** Script sources lib/common.sh correctly

### Task 2.2: Add project root detection
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/hooks/inject-secretary-context.sh`
**Done When:** Added after source line:
```bash
# detect_project_root returns PWD if no project markers found, so this won't fail
PROJECT_ROOT="$(detect_project_root)"
CONFIG_FILE="${PROJECT_ROOT}/.claude/secretary.local.md"
```
**Acceptance:** PROJECT_ROOT and CONFIG_FILE variables set

### Task 2.3: Add config check (no-op if missing)
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/hooks/inject-secretary-context.sh`
**Done When:** Added:
```bash
# Default to manual if no config - silent exit
if [ ! -f "$CONFIG_FILE" ]; then
  exit 0
fi
```
**Acceptance:** Script exits 0 when config missing

### Task 2.4: Add activation_mode parsing
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/hooks/inject-secretary-context.sh`
**Done When:** Added:
```bash
# Read activation_mode (default: manual)
MODE=$(grep "^activation_mode:" "$CONFIG_FILE" 2>/dev/null | head -1 | sed 's/^[^:]*: *//' | tr -d ' ' || echo "manual")

# Only output for aware mode
if [ "$MODE" != "aware" ]; then
  exit 0
fi
```
**Acceptance:** Extracts mode correctly, exits if not "aware"

### Task 2.5: Add JSON output for aware mode
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/hooks/inject-secretary-context.sh`
**Done When:** Added at end:
```bash
# Output hook context
cat << 'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Secretary agent available for orchestrating complex requests. For vague or multi-step tasks, consider: Task({ subagent_type: 'iflow-dev:secretary', prompt: <user_request> })"
  }
}
EOF
```
**Acceptance:** Outputs valid JSON when mode=aware

### Task 2.6: Make script executable
**Command:** `chmod +x /Users/terry/projects/my-ai-setup/plugins/iflow-dev/hooks/inject-secretary-context.sh`
**Done When:** Script is executable
**Acceptance:** `test -x /Users/terry/projects/my-ai-setup/plugins/iflow-dev/hooks/inject-secretary-context.sh` returns 0

### Task 2.7: Test hook script manually
**Working Directory:** `/Users/terry/projects/my-ai-setup`
**Test Script:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/hooks/inject-secretary-context.sh`

**Test Case 1: No config file**
```bash
# Ensure no config exists
rm -f /Users/terry/projects/my-ai-setup/.claude/secretary.local.md 2>/dev/null
/Users/terry/projects/my-ai-setup/plugins/iflow-dev/hooks/inject-secretary-context.sh
echo "Exit code: $?"
# Expected: No output, exit code 0
```

**Test Case 2: Config with mode=manual**
```bash
mkdir -p /Users/terry/projects/my-ai-setup/.claude
cat > /Users/terry/projects/my-ai-setup/.claude/secretary.local.md << 'EOF'
---
activation_mode: manual
---
EOF
/Users/terry/projects/my-ai-setup/plugins/iflow-dev/hooks/inject-secretary-context.sh
echo "Exit code: $?"
# Expected: No output, exit code 0
```

**Test Case 3: Config with mode=aware**
```bash
cat > /Users/terry/projects/my-ai-setup/.claude/secretary.local.md << 'EOF'
---
activation_mode: aware
---
EOF
/Users/terry/projects/my-ai-setup/plugins/iflow-dev/hooks/inject-secretary-context.sh | python3 -c "import json,sys; json.load(sys.stdin); print('Valid JSON')"
# Expected: Valid JSON output with hookSpecificOutput
```

**Cleanup:**
```bash
rm -f /Users/terry/projects/my-ai-setup/.claude/secretary.local.md
rmdir /Users/terry/projects/my-ai-setup/.claude 2>/dev/null || true
```
**Note:** rmdir only removes if empty; `|| true` prevents error if directory has other files
**Done When:** All 3 cases produce expected results
**Acceptance:** Exit codes and output match expectations

---

## Phase 3: hooks.json Modification (Branch A)

**Parallel Group:** A (sequential after Phase 2)
**Depends On:** Phase 2
**Blocks:** Phase 5

### Task 3.1: Read current hooks.json
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/hooks/hooks.json`
**Action:** Read file content and store mentally or in clipboard for rollback
**Rollback Procedure:** If Task 3.3 validation fails, use Write tool to restore the original content
**Done When:** Current hooks.json content is read and understood
**Acceptance:** Can restore original content if needed

### Task 3.2: Append secretary hook to SessionStart array
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/hooks/hooks.json`

**Edit Instructions:**
Use Edit tool with exact strings from file (lines 22-31):

**old_string:** (exact match required including whitespace)
```
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
```

**new_string:** (adds comma, new entry, preserves array closing)
```
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh"
          }
        ]
      },
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/inject-secretary-context.sh"
          }
        ]
      }
    ],
```

**Note:** Indentation is 2 spaces per level. The old_string captures the 3rd (last) SessionStart entry plus the array closing `],`
**Done When:** SessionStart array has 4 entries
**Acceptance:** JSON is valid (verified in Task 3.3)

### Task 3.3: Validate JSON syntax
**Command:**
```bash
python3 -c "import json; json.load(open('/Users/terry/projects/my-ai-setup/plugins/iflow-dev/hooks/hooks.json')); print('Valid JSON')"
```
**Done When:** Command outputs "Valid JSON" and exits 0
**Acceptance:** hooks.json is valid JSON
**If Fails:** Use Write tool to restore content from Task 3.1, then retry Task 3.2

---

## Phase 4: Secretary Agent (Branch B)

**Parallel Group:** B (can run parallel with Phases 1-3)
**Blocks:** Phase 5

### Task 4.0: Create empty agent file with structure
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/agents/secretary.md`
**Action:** Create file with placeholder structure (to be filled by Tasks 4.1-4.8):
```markdown
---
# Frontmatter (Task 4.1)
---

# Secretary Agent

<!-- Discovery Module (Task 4.2) -->

<!-- Interpreter Module (Task 4.3) -->

<!-- Matcher Module (Task 4.4) -->

<!-- Recommender Module (Task 4.5) -->

<!-- Delegator Module (Task 4.6) -->

<!-- Error Handling (Task 4.7) -->

<!-- Rules (Task 4.8) -->
```
**Done When:** File exists with placeholder structure
**Acceptance:** Each subsequent task replaces its placeholder

### Task 4.1: Fill agent frontmatter
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/agents/secretary.md`
**Action:** Replace the frontmatter placeholder with:
```yaml
---
name: secretary
description: |
  Intelligent orchestrator that interprets vague requests, discovers available agents,
  and delegates work to appropriate specialists.

  Use this agent when:
  - You have a vague or complex request
  - You don't know which agent to use
  - A task requires coordination across specialists
tools: [Read, Glob, Grep, Task, AskUserQuestion, Skill]
model: opus
---
```
**Note:** `model: opus` is intentional per spec - secretary needs advanced reasoning for semantic matching
**Done When:** Frontmatter is valid YAML
**Acceptance:** Agent recognized by Claude Code plugin system

### Task 4.2: Write Discovery Module section
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/agents/secretary.md`
**Action:** Replace `<!-- Discovery Module (Task 4.2) -->` placeholder with content below
**Done When:** Added after frontmatter:
```markdown
# Secretary Agent

You are a secretary agent responsible for understanding user requests and routing them to the right specialist agents.

## Discovery Module

Your first step is to discover available agents:

1. Try to read `.claude-plugin/marketplace.json` (optional - may not exist)
2. If not found, use Glob: `plugins/*/agents/*.md`
3. For each agent file:
   - Read the file
   - Extract YAML frontmatter (content between `---` markers)
   - Parse: name, description, tools
4. Build agent index with format: `{plugin}:{agent-name}`
5. Skip files that fail to parse (continue with others)
```
**Acceptance:** Discovery algorithm documented

### Task 4.3: Write Interpreter Module section
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/agents/secretary.md`
**Action:** Replace `<!-- Interpreter Module (Task 4.3) -->` placeholder with content below
**Done When:** Added:
```markdown
## Interpreter Module

Analyze the user request for ambiguity:

**Ambiguity Signals:**
- Vague terms: "better", "improve", "fix", "help"
- Multiple domains: "auth and UI"
- Missing action verb: "the login" (vs "fix the login")

**Clarification Process:**
1. If ambiguous, use AskUserQuestion (max 3 questions)
2. Questions should have concrete options
3. Record clarified intent for matching

**If request is clear:** Skip clarification, proceed to matching.
```
**Acceptance:** Interpretation logic documented

### Task 4.4: Write Matcher Module section
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/agents/secretary.md`
**Action:** Replace `<!-- Matcher Module (Task 4.4) -->` placeholder with content below
**Done When:** Added:
```markdown
## Matcher Module

Match clarified intent to available agents:

1. **If ≤20 agents:** Evaluate all agent descriptions
2. **If >20 agents:**
   - Extract keywords from intent
   - Pre-filter by keyword overlap
   - Take top 10 for evaluation

**For each agent, assess:**
- Semantic fit (0-100 confidence score)
- Reason for match/non-match

**Workflow Pattern Detection:**
- "new feature" / "add capability" → workflow: brainstorm
- "implement" / "build" → workflow: implement
- "review for security" → agent: security-reviewer

**Output:**
- Ranked matches with confidence scores
- Top recommendation (if >70% confidence)
- workflow_match (if pattern detected)
```
**Acceptance:** Matching algorithm documented

### Task 4.5: Write Recommender Module section
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/agents/secretary.md`
**Action:** Replace `<!-- Recommender Module (Task 4.5) -->` placeholder with content below
**Done When:** Added:
```markdown
## Recommender Module

Present recommendation to user:

**Output Format:**
```
**Understanding:** {your interpretation}

**Recommended:** {plugin}:{agent} ({confidence}% match)
**Reason:** {why this agent fits}

**Alternatives:**
- {other matches >50% if any}
```

**Use AskUserQuestion for confirmation:**
- Options: Accept {agent}, [alternatives if any], Cancel
- If user selects alternative, proceed with that agent
- If user cancels, abort with message
```
**Acceptance:** Recommendation format documented

### Task 4.6: Write Delegator Module section
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/agents/secretary.md`
**Action:** Replace `<!-- Delegator Module (Task 4.6) -->` placeholder with content below
**Done When:** Added:
```markdown
## Delegator Module

After user confirms, delegate to selected agent:

**If workflow_match:**
```
Skill({ skill: "iflow-dev:{workflow}", args: "{request}" })
```

**If agent match:**
```
Task({
  subagent_type: "{plugin}:{agent}",
  description: "{brief task description}",
  prompt: "Task: {clarified intent}\n\nContext: {summary}\n\nReturn your findings in structured format."
})
```

**Present result to user after delegation completes.**
```
**Acceptance:** Delegation logic documented

### Task 4.7: Write Error Handling section
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/agents/secretary.md`
**Action:** Replace `<!-- Error Handling (Task 4.7) -->` placeholder with content below
**Done When:** Added:
```markdown
## Error Handling

**No agents found:**
"No agents found. Install plugins with agents first."

**No match (all <70% confidence):**
"No suitable agent found for your request."
Suggestions:
- Describe your task more specifically
- Use /secretary help to see available options

**Delegation failure:**
Use AskUserQuestion with options:
- Retry
- Choose different agent
- Cancel
```
**Acceptance:** Error cases documented

### Task 4.8: Write Rules section
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/agents/secretary.md`
**Action:** Replace `<!-- Rules (Task 4.8) -->` placeholder with content below
**Done When:** Added:
```markdown
## Rules

- ALWAYS discover agents before matching (state changes between sessions)
- ALWAYS clarify vague requests before routing
- ALWAYS show your reasoning when recommending
- NEVER delegate without user confirmation
- NEVER pass excessive context—summarize for subagents
```
**Acceptance:** Rules clearly stated

---

## Phase 5: Secretary Command

**Parallel Group:** None (merge point)
**Depends On:** Phase 3 (Branch A) AND Phase 4 (Branch B)
**Blocks:** Phase 6

### Task 5.1: Create command file with frontmatter
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/commands/secretary.md`
**Done When:** File exists with:
```yaml
---
description: Intelligent orchestrator for vague or complex requests
argument-hint: <request> | help | mode [manual|aware|proactive]
---
```
**Acceptance:** Valid YAML frontmatter

### Task 5.2: Write help subcommand logic
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/commands/secretary.md`
**Done When:** Added:
```markdown
# Secretary Command

## Subcommand: help

If argument is "help", display:

```
Secretary Agent - Routes requests to appropriate specialists

Usage:
  /secretary <request>     Process a request
  /secretary help          Show this help
  /secretary mode          Show current activation mode
  /secretary mode <mode>   Set activation mode (manual|aware|proactive)

Modes:
  manual    - Only responds to explicit /secretary invocation (default)
  aware     - Injects awareness at session start
  proactive - Evaluates every prompt (Phase 2+)

Examples:
  /secretary review auth for security issues
  /secretary add a notification feature
  /secretary mode aware
```
```
**Acceptance:** Help text complete

### Task 5.3: Write mode subcommand (read) logic
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/commands/secretary.md`
**Done When:** Added:
```markdown
## Subcommand: mode (no argument)

If argument is exactly "mode":

1. Use Read tool with path `.claude/secretary.local.md` (relative to project root/working directory)
   - Note: Read tool requires absolute path, so construct from working directory context
2. If file not found (Read returns error):
   - Output: "Config not found. Using defaults (manual mode)."
3. If file exists:
   - Parse YAML frontmatter (extract text between `---` markers)
   - Find line starting with `activation_mode:`
   - Extract value after colon
   - Output: "Current activation mode: {mode}"
```
**Acceptance:** Mode read logic documented with tool usage clarified

### Task 5.4: Write mode subcommand (write) logic
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/commands/secretary.md`
**Done When:** Added:
```markdown
## Subcommand: mode <value>

If argument starts with "mode " followed by a value:

1. Extract mode value from argument (e.g., "mode aware" → "aware")
2. Validate mode is one of: manual, aware, proactive
3. If invalid:
   - Output: "Invalid mode. Use: manual, aware, or proactive"
   - Stop
4. Check if `.claude/` directory exists using Glob tool
5. If missing: Use Bash tool: `mkdir -p .claude`
6. Check if `.claude/secretary.local.md` exists using Read tool
7. If file exists:
   - Read current content to find current mode
   - Use Edit tool:
     - old_string: `activation_mode: {current_mode}`
     - new_string: `activation_mode: {new_mode}`
8. If file missing: Use Write tool to create file:
   ```yaml
   ---
   activation_mode: {new_mode}
   preferred_review_agents: []
   auto_create_missing: false
   supervision_level: light
   ---
   ```
9. Output: "Activation mode set to {mode}. Restart session to apply."
```
**Acceptance:** Mode write logic documented with explicit tool invocations

### Task 5.5: Write request routing logic
**File:** `/Users/terry/projects/my-ai-setup/plugins/iflow-dev/commands/secretary.md`
**Done When:** Added:
```markdown
## Default: Process Request

If argument is not "help" and not "mode" or "mode <value>":

Invoke the secretary agent:

```
Task({
  subagent_type: "iflow-dev:secretary",
  description: "Process user request via secretary",
  prompt: "User request: {argument}"
})
```

Return the agent's result to the user.
```
**Acceptance:** Request routing documented

---

## Phase 6: Integration Testing

**Parallel Group:** None (final phase)
**Depends On:** Phase 5

**Execution Environment:** Fresh Claude Code session in project directory
**Results File:** Document results in `/Users/terry/projects/my-ai-setup/docs/features/014-secretary-agent/test-results.md`

### Task 6.1: Test basic flow
**Execution:**
1. Start new Claude Code session in `/Users/terry/projects/my-ai-setup`
2. Type: `/secretary review src/auth.ts for security issues`
3. Observe output

**Expected:**
- Agent outputs understanding of request
- Recommends security-reviewer with confidence score
- Shows AskUserQuestion with Accept/Cancel

**Pass Criteria:** User accepts → delegation to security-reviewer occurs
**Fail Criteria:** No recommendation, wrong agent, or no confirmation step
**Document:** Timestamp, actual output, PASS/FAIL in test-results.md
**Done When:** Test executed and documented

### Task 6.2: Test vague request
**Execution:**
1. In Claude Code session, type: `/secretary make the code better`
2. Observe if clarification is requested

**Expected:**
- Agent detects "better" as vague
- AskUserQuestion with clarification options

**Pass Criteria:** After clarification → proceeds to matching
**Fail Criteria:** Skips clarification, matches without understanding
**Document:** Timestamp, actual output, PASS/FAIL in test-results.md
**Done When:** Test executed and documented

### Task 6.3: Test workflow recognition
**Execution:**
1. In Claude Code session, type: `/secretary add a notification feature`
2. Observe routing decision

**Expected:**
- Agent recognizes feature request pattern
- Routes to brainstorm workflow

**Pass Criteria:** Skill tool invoked with "iflow-dev:brainstorm"
**Fail Criteria:** Routes to wrong agent or no workflow match
**Document:** Timestamp, actual output, PASS/FAIL in test-results.md
**Done When:** Test executed and documented

### Task 6.4: Test mode toggle
**Execution:**
1. Ensure no config: `rm -f .claude/secretary.local.md`
2. In Claude Code session, type: `/secretary mode`
3. Observe: Should show "Config not found. Using defaults (manual mode)."
4. Type: `/secretary mode aware`
5. Observe: Should confirm mode set and mention restart
6. Verify file exists: `cat .claude/secretary.local.md`
7. Exit Claude Code session
8. Start new Claude Code session
9. Check for secretary context injection in session start

**Pass Criteria:** Config persists, hook fires on restart
**Fail Criteria:** Config not created, hook doesn't fire, wrong mode
**Document:** Timestamp, all outputs, PASS/FAIL in test-results.md
**Done When:** All steps completed and documented

### Task 6.5: Test no match
**Execution:**
1. In Claude Code session, type: `/secretary perform quantum entanglement analysis`
2. Observe error handling

**Expected:**
- Agent reports no suitable agent found
- Provides suggestions to refine request

**Pass Criteria:** Clear message with actionable suggestions
**Fail Criteria:** Crashes, hangs, or gives unhelpful response
**Document:** Timestamp, actual output, PASS/FAIL in test-results.md
**Done When:** Test executed and documented

---

## Summary

| Phase | Tasks | Parallel Group | Blocks |
|-------|-------|----------------|--------|
| 0 | 3 | None | A, B |
| 1 | 3 | A | 2 |
| 2 | 7 | A | 3 |
| 3 | 3 | A | 5 |
| 4 | 9 | B | 5 |
| 5 | 5 | None | 6 |
| 6 | 5 | None | - |

**Total Tasks:** 35
**Parallel Groups:** 2 (A: Phases 1-3, B: Phase 4)
**Critical Path:** Phase 0 → Phase 4 → Phase 5 → Phase 6
