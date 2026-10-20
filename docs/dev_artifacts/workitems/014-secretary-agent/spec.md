# Specification: Secretary Agent

## Overview

This specification defines the secretary agent—a meta-agent that interprets vague user requests, discovers available agents, delegates work, and supervises execution. Implementation follows a phased approach with Phase 1a (Discovery + Interpretation) as MVP.

## Scope

### In Scope (Phase 1a MVP)
- Agent discovery across all installed plugins
- Request interpretation with ambiguity clarification
- Routing recommendations with user confirmation
- `/secretary` command for explicit invocation

### In Scope (Phase 1b)
- Single-agent delegation via Task tool
- Completion review on subagent return
- Result presentation to user

### Out of Scope (Future Phases)
- Auto-creation of missing agents (Phase 3)
- Active supervision with checkpoints (Phase 2)
- Context learning and preferences (Phase 4)
- Proactive mode with UserPromptSubmit hook

---

## Component Inventory

### New Components

| Type | Name | Location |
|------|------|----------|
| Agent | secretary | `plugins/iflow-dev/agents/secretary.md` |
| Command | secretary | `plugins/iflow-dev/commands/secretary.md` |
| Hook script | inject-secretary-context.sh | `plugins/iflow-dev/hooks/inject-secretary-context.sh` |
| Config template | secretary.local.md | `.claude/secretary.local.md` (user creates) |

### Modified Components

| Type | Name | Location | Change |
|------|------|----------|--------|
| Hook config | hooks.json | `plugins/iflow-dev/hooks/hooks.json` | Add SessionStart entry for aware mode |

---

## Detailed Requirements

### REQ-1: Agent Discovery

**Description:** Secretary discovers all available agents across installed plugins at the start of each request.

**Acceptance Criteria:**
- AC-1.1: Reads plugin list from `.claude-plugin/marketplace.json` if exists
  - Expected structure: `{"plugins": [{"name": "plugin-name", "source": "./plugins/plugin-name"}]}`
  - Falls back to glob-all approach if file not found
- AC-1.2: Globs `plugins/*/agents/*.md` to find agent files
- AC-1.3: Parses YAML frontmatter to extract: name, description, tools
- AC-1.4: Builds in-memory index of agents with format: `{plugin}:{agent-name}`
- AC-1.5: Index is rebuilt per request (no caching across requests in Phase 1a)

**Test Scenarios:**
```
Given: plugins/iflow-dev/agents/security-reviewer.md exists with valid frontmatter
When: Secretary runs discovery
Then: Index contains entry "iflow-dev:security-reviewer" with description
```

---

### REQ-2: Request Interpretation

**Description:** Secretary analyzes user requests to determine intent and identify ambiguities.

**Acceptance Criteria:**
- AC-2.1: Extracts intent keywords from natural language request
- AC-2.2: Identifies ambiguous requests requiring clarification
- AC-2.3: Uses AskUserQuestion to resolve ambiguities (max 3 questions)
- AC-2.4: Records clarified intent for delegation
- AC-2.5: If clarification times out or user provides no response after 3 attempts, proceeds with best-effort interpretation of original request

**Ambiguity Detection Heuristics:**
- Request contains vague terms: "better", "improve", "fix", "help"
- Request mentions multiple potential domains: "auth and UI"
- No clear action verb: "the login" (vs "fix the login")

**Test Scenarios:**
```
Given: User request "make auth better"
When: Secretary interprets request
Then: AskUserQuestion is used to clarify: security? UX? performance?

Given: User request "review src/auth.ts for security issues"
When: Secretary interprets request
Then: No clarification needed, proceeds to matching
```

---

### REQ-3: Capability Matching

**Description:** Secretary matches clarified intent to available agents using LLM-based evaluation.

**Acceptance Criteria:**
- AC-3.1: Loads agent descriptions into context (≤20 agents: all; >20 agents: top 10 by keyword)
  - Keyword extraction: word tokenization with stop-word removal, scored by word overlap count
- AC-3.2: Presents user intent + agent descriptions to LLM for evaluation
- AC-3.3: Returns ranked matches with confidence scores (0-100%)
- AC-3.4: If no match >70% confidence, reports "no suitable agent found"
  - Confidence is LLM-evaluated semantic similarity on 0-100 scale
- AC-3.5: For workflow-like requests, matches to existing commands (e.g., "new feature" → brainstorm)

**Matching Prompt Template:**
```
Given the user's request and available agents, identify the best match.

User Request: {clarified_intent}

Available Agents:
{for each agent}
- {plugin}:{name}: {description}
{end for}

Return JSON:
{
  "matches": [
    {"agent": "plugin:name", "confidence": 85, "reason": "..."},
    ...
  ],
  "recommendation": "plugin:name" | null,
  "workflow_match": "brainstorm" | "implement" | null
}
```

**Test Scenarios:**
```
Given: User wants "security review of auth module"
And: iflow-dev:security-reviewer exists with description mentioning "security"
When: Secretary matches
Then: security-reviewer has confidence >80%

Given: User wants "add a notification feature"
When: Secretary matches
Then: workflow_match = "brainstorm" (recognized as feature request)
```

---

### REQ-4: Routing Recommendation

**Description:** Secretary presents routing recommendation to user for confirmation before delegation.

**Acceptance Criteria:**
- AC-4.1: Shows best match with confidence and reason
- AC-4.2: Offers alternatives if multiple matches >50% confidence
- AC-4.3: User can accept, choose alternative, or cancel
- AC-4.4: If no match, offers to escalate or describe manually

**Output Format:**
```
I understand you want to: {clarified_intent}

Recommended: iflow-dev:security-reviewer (85% match)
Reason: Agent specializes in security vulnerability detection.

Alternatives:
- iflow-dev:code-quality-reviewer (62% match)

[Accept / Choose Alternative / Cancel]
```

**Test Scenarios:**
```
Given: Match found with 85% confidence
When: Secretary presents recommendation
Then: AskUserQuestion with Accept/Alternative/Cancel options

Given: No match >70%
When: Secretary presents recommendation
Then: Message explains no suitable agent, offers manual description
```

---

### REQ-5: Task Delegation (Phase 1b)

**Description:** After user confirms, secretary delegates to the selected agent via Task tool.

**Acceptance Criteria:**
- AC-5.1: Constructs Task tool call with: subagent_type, description, prompt
- AC-5.2: Passes clarified intent and relevant context in prompt
- AC-5.3: Waits for subagent completion
- AC-5.4: Presents subagent result to user

**Delegation Template:**
```javascript
Task({
  subagent_type: "{plugin}:{agent}",
  description: "{brief task description}",
  prompt: `
    Task: {clarified_intent}

    Context:
    {relevant_context}

    Requirements:
    - {specific requirements from user}

    Return your findings/work in structured format.
  `
})
```

---

### REQ-6: Workflow Routing

**Description:** For requests matching iflow-dev workflows, secretary invokes the appropriate command.

**Acceptance Criteria:**
- AC-6.1: Recognizes feature requests → routes to `/iflow-dev:brainstorm`
- AC-6.2: Recognizes implementation requests → routes to `/iflow-dev:implement`
- AC-6.3: Recognizes review requests → routes to appropriate reviewer agent
- AC-6.4: Uses Skill tool for workflow commands

**Pattern Matching:**
| Request Pattern | Route To |
|-----------------|----------|
| "new feature", "add capability" | `/iflow-dev:brainstorm` |
| "implement the design", "build this" | `/iflow-dev:implement` |
| "review for security" | `iflow-dev:security-reviewer` |
| "check code quality" | `iflow-dev:code-quality-reviewer` |

---

### REQ-7: Command Interface

**Description:** `/secretary` command provides explicit entry point to secretary agent.

**Acceptance Criteria:**
- AC-7.1: `/secretary <request>` invokes secretary with the request
- AC-7.2: `/secretary help` shows usage instructions
- AC-7.3: `/secretary mode` shows current activation mode
- AC-7.4: `/secretary mode <manual|aware|proactive>` updates config file
- Note: `/secretary status` deferred to Phase 2 (Active Supervision)

**Command File:**
```yaml
---
description: Intelligent orchestrator for vague or complex requests
argument-hint: <request> | help | mode [manual|aware|proactive]
---
```

---

### REQ-8: Activation Mode Configuration

**Description:** Secretary supports three activation modes configurable via persistent config.

**Acceptance Criteria:**
- AC-8.1: Config stored in `.claude/secretary.local.md` with YAML frontmatter
- AC-8.2: `manual` mode: secretary only responds to explicit `/secretary` invocation
- AC-8.3: `aware` mode: SessionStart hook injects secretary awareness
- AC-8.4: `proactive` mode: (Phase 2+) UserPromptSubmit hook evaluates prompts
- AC-8.5: Mode changes require session restart to take effect
- AC-8.6: When config file not found, defaults to `manual` mode
- AC-8.7: `/secretary mode <mode>` creates config file if missing

**Config Schema:**
```yaml
---
activation_mode: manual  # manual | aware | proactive
preferred_review_agents: []  # Phase 2+: used to break ties in matching
auto_create_missing: false   # Phase 3+
supervision_level: light     # Phase 2+: light | standard | full | adaptive
---
```

---

### REQ-9: SessionStart Hook (Aware Mode)

**Description:** In `aware` mode, injects secretary availability context at session start.

**Acceptance Criteria:**
- AC-9.1: Hook script checks `activation_mode` in config
- AC-9.2: If mode != `aware`, script exits 0 (no-op)
- AC-9.3: If mode == `aware`, outputs hookSpecificOutput with additionalContext
- AC-9.4: Context injection reminds Claude that secretary is available

**Hook Output:**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Secretary agent available. For vague or multi-step tasks, invoke via Task({ subagent_type: 'iflow-dev:secretary' })"
  }
}
```

---

## Agent System Prompt

```markdown
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

# Secretary Agent

You are a secretary agent responsible for understanding user requests and routing them to the right specialist agents.

## Workflow

1. **Discover** available agents by globbing `plugins/*/agents/*.md` and parsing frontmatter
2. **Interpret** the user's request to understand their true intent
3. **Clarify** any ambiguities using AskUserQuestion (max 3 questions)
4. **Match** the clarified intent to available agents using semantic evaluation
5. **Recommend** the best agent with reasoning, let user confirm
6. **Delegate** via Task tool once user approves

## Rules

- ALWAYS discover agents before matching (state changes between sessions)
- ALWAYS clarify vague requests before routing
- ALWAYS show your reasoning when recommending an agent
- NEVER delegate without user confirmation
- NEVER pass excessive context to subagents—summarize
- If no suitable agent found, explain clearly and offer alternatives

## Output Format for Recommendations

```
**Understanding:** {your interpretation of the request}

**Recommended Agent:** {plugin}:{agent} ({confidence}% match)
**Reason:** {why this agent fits}

**Alternatives:**
- {other matches if any}

[Use AskUserQuestion for confirmation]
```

## Workflow Recognition

If user request matches these patterns, route to workflow commands:
- "new feature" / "add capability" → /iflow-dev:brainstorm
- "implement" / "build" → /iflow-dev:implement
- "create plan" → /iflow-dev:create-plan

For direct tool/task requests, route to appropriate specialist agent.
```

---

## File Structure

```
plugins/iflow-dev/
├── agents/
│   └── secretary.md                    # NEW: Secretary agent definition
├── commands/
│   └── secretary.md                    # NEW: /secretary command
└── hooks/
    ├── hooks.json                      # MODIFY: Add SessionStart hook
    └── inject-secretary-context.sh     # NEW: Aware mode hook script

.claude/
└── secretary.local.md                  # USER CREATES: Config file
```

---

## Error Handling

| Error | Handling |
|-------|----------|
| No plugins found | Report "No plugins installed. Install plugins first." |
| Agent file parse error | Skip agent, log warning, continue with others |
| Clarification timeout | Proceed with best-effort interpretation |
| No matching agent | Report clearly, suggest user describe task manually |
| Delegation failure | Report error, offer retry or manual action |

---

## Dependencies

- Claude Code Task tool for subagent invocation
- Glob tool for agent discovery
- Read tool for parsing agent frontmatter
- AskUserQuestion tool for clarification and confirmation

---

## Verification Checklist

### Phase 1a (MVP)
- [ ] `/secretary help` displays usage instructions
- [ ] `/secretary "review auth for security"` discovers and recommends security-reviewer
- [ ] Vague requests trigger clarification via AskUserQuestion
- [ ] User confirmation required before delegation
- [ ] `/secretary mode` shows current activation mode
- [ ] `/secretary mode aware` updates config file
- [ ] SessionStart hook injects context when mode=aware

### Phase 1b
- [ ] Delegation via Task tool completes successfully
- [ ] Subagent results presented to user
- [ ] Workflow routing invokes correct command
