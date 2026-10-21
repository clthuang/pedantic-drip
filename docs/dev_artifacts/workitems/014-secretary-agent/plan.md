# Implementation Plan: Secretary Agent

## Overview

This plan sequences the implementation of the secretary agent following TDD principles. Implementation is divided into Phase 1a (MVP) and Phase 1b, with clear dependencies between components.

**TDD Approach:** Each step defines acceptance criteria and test scenarios FIRST, then implementation tasks.

## Implementation Order

```
Step 0: Interface Contracts (documentation)
    ↓
Step 1: Configuration Component
    ↓
Step 2: Hook Script (inject-secretary-context.sh)
    ↓
Step 3: hooks.json Modification
    ↓
Step 4: Secretary Agent (Core Logic)
    ↓
Step 5: Secretary Command
    ↓
Step 6: Integration Testing
```

**Parallelization Note:** After Step 0, two independent branches can proceed:
- **Branch A (sequential):** Step 1 → Step 2 → Step 3 (Config → Hook Script → hooks.json)
- **Branch B (independent):** Step 4 (Secretary Agent)

Step 5 (Command) requires BOTH branches to complete before starting. Step 6 waits for Step 5.

---

## Step 0: Interface Contracts (Documentation)

**Files:** None (contracts documented in design.md)

**Priority:** P0 (Prerequisite for parallel work)

**Dependencies:** None

**Description:**
Review and confirm interface contracts from design.md before parallel implementation begins. This ensures Steps 1-3 and Step 4 can work independently.

**Contracts to Verify:**
1. Interface 7 (Configuration): Config schema, file location, default values
2. Interface 1 (Command → Agent): Task tool invocation format
3. Interface 8 (Hook Output): hookSpecificOutput JSON structure

**Acceptance Criteria:**
- [ ] All interface contracts reviewed and understood
- [ ] No ambiguities that would block parallel implementation

**Exit Gate:** This step is a prerequisite gate. Both Branch A and Branch B can proceed only after this review is complete. In tasks phase, this may be implicit rather than a separate task.

---

## Step 1: Configuration Component

**Files:**
- Template documentation for `.claude/secretary.local.md`
- Actual template file: `plugins/iflow-dev/templates/secretary.local.md`

**Priority:** P0 (Foundation)

**Dependencies:** Step 0 (Interface Contracts)

**Description:**
Create the configuration template that users will use. This is needed before hooks and command can read config.

### Acceptance Criteria (define FIRST):
- [ ] Config schema documented in design.md (already done)
- [ ] Template file exists at plugins/iflow-dev/templates/secretary.local.md
- [ ] .claude directory creation handled (create if missing)
- [ ] Default behavior defined: when config missing → manual mode

### Test Scenarios (RED phase - define expected behavior):
1. **Config file exists with valid YAML** → values readable via grep/sed
2. **Config file missing** → defaults applied (activation_mode=manual)
3. **Config file malformed YAML** → defaults applied with no crash
4. **.claude directory missing** → created on first /secretary mode <mode>

### Implementation Tasks (GREEN phase):
1. Create templates directory: `mkdir -p plugins/iflow-dev/templates`
2. Create template file at `plugins/iflow-dev/templates/secretary.local.md`:
   ```yaml
   ---
   activation_mode: manual
   preferred_review_agents: []
   auto_create_missing: false
   supervision_level: light
   ---
   ```
3. Document that .claude/ directory creation is handled by /secretary mode command
4. Define bash parsing pattern for hooks:
   ```bash
   # Note: sed 's/^[^:]*: *//' matches first colon only, so handles values that contain colons
   MODE=$(grep "^activation_mode:" "$CONFIG" 2>/dev/null | head -1 | sed 's/^[^:]*: *//' | tr -d ' ')
   ```

---

## Step 2: Hook Script (inject-secretary-context.sh)

**Files:** `plugins/iflow-dev/hooks/inject-secretary-context.sh`

**Priority:** P0 (Foundation for aware mode)

**Dependencies:** Step 1 (Config Component - for config schema and parsing pattern)

**Description:**
Create bash script that conditionally injects secretary awareness at session start.

### Acceptance Criteria (define FIRST):
- [ ] Script created at correct location
- [ ] Script is executable (chmod +x)
- [ ] Sources lib/common.sh for detect_project_root (path: `${SCRIPT_DIR}/lib/common.sh`)
- [ ] Correctly reads config when present
- [ ] Defaults to no-op when config missing
- [ ] Only outputs for aware mode

### Test Scenarios (RED phase - define expected behavior):
1. **Config missing** → exit 0, no output (silent no-op)
2. **Config exists, mode=manual** → exit 0, no output
3. **Config exists, mode=aware** → output valid JSON with hookSpecificOutput
4. **Config exists, mode=proactive** → exit 0, no output (proactive uses different hook in Phase 2+)
5. **Config exists, malformed** → exit 0, no output (fail safe to no-op)
6. **Config exists, activation_mode commented out (# activation_mode: aware)** → defaults to manual, exit 0
7. **Config exists, missing newline at EOF** → parses correctly
8. **Config exists, value contains colon (e.g., preferred_review_agents: ["foo:bar"])** → activation_mode still parses correctly (grep matches first colon only)

### Implementation Tasks (GREEN phase):
1. Create script with proper header and lib/common.sh sourcing (matches existing hook patterns)
   - Use: `source "${SCRIPT_DIR}/lib/common.sh"` (same as session-start.sh)
2. Use detect_project_root to find config in PROJECT_ROOT/.claude/
3. Parse activation_mode using grep/sed pattern from Step 1
4. Output JSON only when mode=aware
5. Make executable: `chmod +x`

**Implementation:**
```bash
#!/usr/bin/env bash
# inject-secretary-context.sh - Inject secretary awareness at session start (aware mode only)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

# detect_project_root returns PWD if no project markers found, so this won't fail
# If somehow it does fail, we want the script to exit early (fail-safe behavior)
PROJECT_ROOT="$(detect_project_root)"

CONFIG_FILE="${PROJECT_ROOT}/.claude/secretary.local.md"

# Default to manual if no config - silent exit
if [ ! -f "$CONFIG_FILE" ]; then
  exit 0
fi

# Read activation_mode (default: manual)
# Note: grep "^activation_mode:" only matches uncommented lines at start of line
# sed 's/.*: *//' matches first colon, so "activation_mode: aware" extracts "aware"
# Values with colons in other fields (e.g., preferred_review_agents: ["foo:bar"]) don't affect this
# The || echo "manual" handles both missing config and commented-out activation_mode
MODE=$(grep "^activation_mode:" "$CONFIG_FILE" 2>/dev/null | head -1 | sed 's/^[^:]*: *//' | tr -d ' ' || echo "manual")

# Only output for aware mode
if [ "$MODE" != "aware" ]; then
  exit 0
fi

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

**Estimated Lines:** ~35 (including headers, comments, proper error handling)

---

## Step 3: hooks.json Modification

**Files:** `plugins/iflow-dev/hooks/hooks.json`

**Priority:** P0 (Required for hook to fire)

**Dependencies:** Step 2 (Hook Script must exist)

**Description:**
Register the SessionStart hook in hooks.json. Critical: hooks.json is shared by all plugin hooks - malformed JSON breaks the entire plugin.

### Acceptance Criteria (define FIRST):
- [ ] hooks.json remains valid JSON after modification
- [ ] New entry appended to existing SessionStart array
- [ ] Matcher includes all 4 events: startup|resume|clear|compact (matches existing hooks)
- [ ] Rollback possible if validation fails

### Test Scenarios (RED phase - define expected behavior):
1. **Session start (startup)** → hook fires, script executed
2. **Session resume** → hook fires, script executed
3. **After /clear** → hook fires (context re-injected)
4. **After /compact** → hook fires (context re-injected)
5. **hooks.json invalid** → validated before save, rollback to previous

### Error Recovery Strategy:
1. **Before editing:** Read and store current hooks.json content (using Read tool)
2. **After editing:** Validate JSON using Bash tool:
   ```bash
   python3 -c "import json; json.load(open('plugins/iflow-dev/hooks/hooks.json'))"
   ```
   (use the full relative path from project root)
3. **If validation fails:** Restore original content using Write tool, report error
4. **If validation passes:** Confirm success

### Implementation Tasks (GREEN phase):
1. Read current hooks.json
2. Append new entry to SessionStart array (DO NOT replace existing entries)
3. Use matcher `startup|resume|clear|compact` (consistent with existing hooks)
4. Validate JSON before finalizing

**Implementation:**
Append to existing SessionStart array:
```json
{
  "matcher": "startup|resume|clear|compact",
  "hooks": [
    {
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/inject-secretary-context.sh"
    }
  ]
}
```

**Note:** Existing SessionStart array has 3 entries (sync-cache, cleanup-locks, session-start). This adds a 4th entry.

---

## Step 4: Secretary Agent (Core Logic)

**Files:** `plugins/iflow-dev/agents/secretary.md`

**Priority:** P0 (Core functionality)

**Dependencies:**
- Step 0 (Interface Contracts - for output formats)
- Interface 2 (Discovery Output schema)
- Interface 3 (Matcher Output schema)
- Interface 5 (Task Delegation format)

**Note:** While the agent doesn't depend on Steps 1-3 for execution, it shares Interface 7 (Configuration) for understanding mode. The agent can be developed in parallel with Steps 1-3 after Step 0 completes.

**Description:**
Create the secretary agent with full orchestration logic: discovery, interpretation, matching, recommendation, delegation.

### Acceptance Criteria (define FIRST):
- [ ] Agent file created with valid YAML frontmatter
- [ ] Discovery module finds existing agents via Glob
- [ ] Interpreter module detects vague requests
- [ ] Matcher module returns ranked results with confidence scores
- [ ] Recommender module uses AskUserQuestion for confirmation
- [ ] Delegator module invokes Task tool correctly
- [ ] Error handling for no agents, no match, delegation failure

### Test Scenarios (RED phase - define expected behavior):
1. **Clear request "review auth for security"** → skips clarification, matches security-reviewer
2. **Vague request "make it better"** → asks clarifying questions via AskUserQuestion
3. **Security review request** → matches iflow-dev:security-reviewer with high confidence
4. **Feature request "add notifications"** → matches brainstorm workflow
5. **No matching agent** → reports clearly with suggestions
6. **>20 agents** → pre-filters by keyword, then semantic match on top 10

### Implementation Tasks (GREEN phase):

#### 4.1 Agent Frontmatter
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

#### 4.2 System Prompt Sections

**Section A: Discovery Module**
- Check `.claude-plugin/marketplace.json` first (OPTIONAL - may not exist)
  - Path: `.claude-plugin/marketplace.json` relative to project root (agent uses Read tool from project root context)
- If marketplace.json exists: read plugin paths from it
- If marketplace.json doesn't exist: fall back to Glob `plugins/*/agents/*.md`
- Parse YAML frontmatter from each file (LLM text extraction)
- Build agent index: `{plugin, name, description, tools}`
- Handle parse errors gracefully (skip and continue)

**Section B: Interpreter Module**
- Analyze request for ambiguity signals (vague terms, multiple domains, missing action verb)
- Generate clarifying questions if needed
- Use AskUserQuestion (max 3 questions)
- Return clarified intent

**Section C: Matcher Module**
- If agent count ≤20: load all descriptions
- If agent count >20: pre-filter by keyword overlap, take top 10
- LLM evaluates semantic fit
- Return ranked matches with confidence scores (0-100)
- Detect workflow patterns (brainstorm, implement, etc.)

**Section D: Recommender Module**
- Format recommendation message with confidence and reasoning
- Show alternatives >50% confidence inline
- Use AskUserQuestion for confirmation (Accept/Alternative/Cancel)
- Handle user selection

**Section E: Delegator Module**
- If workflow_match: use Skill tool
- Else: use Task tool with subagent_type format "plugin:agent"
- Return result to user

#### 4.3 Error Handling
- No agents found: "No agents found. Install plugins with agents first."
- No match: "No suitable agent found for your request." + suggestions
- Delegation failure: Offer retry/alternative/cancel via AskUserQuestion

**Estimated Lines:** ~200-300 (agent markdown with system prompt; may reach 400+ if thorough module documentation and examples included - estimate is flexible)

---

## Step 5: Secretary Command

**Files:** `plugins/iflow-dev/commands/secretary.md`

**Priority:** P0 (User entry point)

**Dependencies:**
- Step 4 (Secretary Agent - must exist for delegation)
- Step 1 (Config - for mode subcommand schema and .claude directory creation)

**Description:**
Create the `/secretary` command as a thin wrapper that routes to appropriate behavior.

### Acceptance Criteria (define FIRST):
- [ ] Command file created with valid YAML frontmatter
- [ ] help subcommand displays usage instructions
- [ ] mode subcommand (no arg) reads and displays current mode
- [ ] mode subcommand (with arg) updates config file
- [ ] mode subcommand creates .claude directory if missing
- [ ] mode subcommand creates config file if missing
- [ ] Request routing invokes secretary agent via Task tool

### Test Scenarios (RED phase - define expected behavior):
1. **`/secretary help`** → shows usage instructions
2. **`/secretary mode` (no config)** → "Config not found. Using defaults (manual mode)."
3. **`/secretary mode` (with config)** → "Current activation mode: {mode}"
4. **`/secretary mode aware`** → creates/updates config, reports success
5. **`/secretary mode aware` (.claude missing)** → creates .claude directory first
6. **`/secretary mode invalid`** → "Invalid mode. Use: manual, aware, or proactive"
7. **`/secretary review code`** → invokes secretary agent with request

### Implementation Tasks (GREEN phase):

#### 5.1 Command Frontmatter
```yaml
---
description: Intelligent orchestrator for vague or complex requests
argument-hint: <request> | help | mode [manual|aware|proactive]
---
```

#### 5.2 Command Logic

**help subcommand:**
Display usage instructions inline (no tool call):
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

**mode subcommand (no argument):**
1. Use Read tool to check `.claude/secretary.local.md`
2. If file not found: Report "Config not found. Using defaults (manual mode)."
3. If file exists: Parse frontmatter, report "Current activation mode: {mode}"

**mode subcommand (with argument):**
1. Validate argument is manual|aware|proactive
2. If invalid: "Invalid mode. Use: manual, aware, or proactive"
3. Check if .claude/ directory exists
4. If .claude/ missing: Use Bash `mkdir -p .claude`
5. If config exists: Use Edit tool to update activation_mode
6. If config missing: Use Write tool to create from template
7. Report: "Activation mode set to {mode}. Restart session to apply."

**request (default):**
1. Invoke secretary agent via Task tool:
   ```
   Task({
     subagent_type: "iflow-dev:secretary",
     description: "Process user request",
     prompt: "User request: {request}"
   })
   ```
2. Return agent result to user

**Estimated Lines:** ~80-100 (command markdown)

---

## Step 6: Integration Testing

**Priority:** P1 (Validation)

**Dependencies:** Steps 1-5

**Description:**
Test the complete flow from command invocation through agent execution.

### Acceptance Criteria (define FIRST):
- [ ] Basic flow completes end-to-end (command → agent → delegation → result)
- [ ] Vague requests trigger clarification questions
- [ ] Workflow patterns route to correct skill
- [ ] Mode toggle creates/updates config and takes effect on restart
- [ ] No-match scenario reports clearly with suggestions
- [ ] All error handling paths work as designed

### Test Scenarios (RED phase - define expected behavior with pass/fail):

#### 6.1 Basic Flow
**Input:** `/secretary review src/auth.ts for security issues`
**Expected Output:**
- Agent outputs "Understanding: review auth for security"
- Agent recommends security-reviewer with confidence >70%
- AskUserQuestion shown with Accept/Cancel options
**Pass Criteria:** User accepts → Task tool invoked with subagent_type "iflow-dev:security-reviewer"
**Fail Criteria:** No recommendation, wrong agent, no confirmation step

#### 6.2 Vague Request
**Input:** `/secretary make the code better`
**Expected Output:**
- Agent detects vague request ("better" is ambiguous)
- AskUserQuestion with clarification options (security? performance? readability?)
**Pass Criteria:** After clarification → proceeds to matching with clarified intent
**Fail Criteria:** Skips clarification, matches without understanding

#### 6.3 Workflow Recognition
**Input:** `/secretary add a notification feature`
**Expected Output:**
- Agent recognizes "add feature" pattern
- Routes to brainstorm workflow
**Pass Criteria:** Skill tool invoked with skill "iflow-dev:brainstorm"
**Fail Criteria:** Routes to wrong agent or no workflow match

#### 6.4 Mode Toggle
**Input Sequence:**
1. `/secretary mode` (no config exists)
2. `/secretary mode aware`
3. Session restart
**Expected Output:**
1. "Config not found. Using defaults (manual mode)."
2. "Activation mode set to aware. Restart session to apply." + config file created
3. SessionStart hook outputs additionalContext about secretary
**Pass Criteria:** Config persists, hook fires on restart
**Fail Criteria:** Config not created, hook doesn't fire, wrong mode stored

#### 6.5 No Match
**Input:** `/secretary perform quantum entanglement analysis`
**Expected Output:**
- Agent discovers no suitable agent
- Reports: "No suitable agent found for your request."
- Suggests: "Describe your task more specifically" or "Use /secretary help"
**Pass Criteria:** Clear message with actionable suggestions
**Fail Criteria:** Crashes, hangs, or gives unhelpful response

### Implementation Tasks (GREEN phase):
1. Execute test scenarios **sequentially** (6.1 → 6.2 → 6.3 → 6.4 → 6.5)
   - 6.4 (Mode Toggle) requires session restart, so run last before 6.5
2. Document results in test log
3. Fix any failures and re-test
4. Mark all acceptance criteria as complete

**Test Execution Order:** Run 6.1, 6.2, 6.3 first (order within these doesn't matter), then 6.4 (requires restart), then 6.5.

---

## Dependency Graph

```
                  ┌─────────────────────┐
                  │  Step 0: Interface  │
                  │     Contracts       │
                  └──────────┬──────────┘
                             │
            ┌────────────────┴────────────────┐
            │                                 │
            ▼                                 ▼
┌─────────────────┐                 ┌─────────────────┐
│  Step 1: Config │                 │ Step 4: Agent   │
│    Component    │                 │  (Secretary)    │
└────────┬────────┘                 └────────┬────────┘
         │                                   │
         ▼                                   │
┌─────────────────┐                          │
│ Step 2: Hook    │                          │
│    Script       │                          │
└────────┬────────┘                          │
         │                                   │
         ▼                                   │
┌─────────────────┐                          │
│ Step 3: hooks   │                          │
│    .json        │                          │
└────────┬────────┘                          │
         │                                   │
         └───────────────┬───────────────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Step 5: Command │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Step 6: Testing │
                └─────────────────┘
```

**Parallel Execution Strategy:**
- After Step 0 completes, two branches can proceed independently:
  - Branch A: Steps 1→2→3 (sequential within branch)
  - Branch B: Step 4 (independent)
- Step 5 waits for BOTH branches to complete (merge point)
- Step 6 waits for Step 5

---

## Risk Mitigation

| Risk | Mitigation in Plan |
|------|-------------------|
| Frontmatter parsing fails | Step 4 includes error handling, skip and continue |
| Hook doesn't fire | Step 3 validates JSON, Step 6 tests hook firing |
| Agent matching inaccurate | Step 4 requires user confirmation, shows confidence |
| Config file corruption | Steps 1-2 define defaults when config unreadable |

---

## Deliverables Summary

| Step | File(s) | Lines Est. |
|------|---------|------------|
| 0 | (Review only) | N/A |
| 1 | templates/secretary.local.md | ~10 |
| 2 | inject-secretary-context.sh | ~35 |
| 3 | hooks.json (modification) | ~10 |
| 4 | secretary.md (agent) | ~200-300 |
| 5 | secretary.md (command) | ~100 |
| 6 | (Testing, no new files) | N/A |

**Total new files:** 4
**Modified files:** 1
