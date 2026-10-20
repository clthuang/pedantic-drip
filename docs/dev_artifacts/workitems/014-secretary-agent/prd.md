# PRD: Secretary Agent

## Overview

A meta-agent that interprets vague user requests, clarifies ambiguities, determines required capabilities, and orchestrates specialized agents to complete tasks—automatically creating missing agents/skills when needed.

## Problem Statement

Users often have vague, high-level requests that don't map directly to existing agents or skills. Currently, users must:
1. Know which agents exist and their capabilities
2. Manually decompose complex tasks
3. Invoke agents explicitly with `/plugin:agent-name`
4. Handle gaps when no suitable agent exists

This creates friction and requires domain knowledge that users shouldn't need.

## Solution

A **secretary agent** that acts as an intelligent front-end:
1. **Interprets** vague requests to understand true intent
2. **Clarifies** ambiguities through targeted questions
3. **Plans** the work by identifying required capabilities
4. **Discovers** available agents across all installed plugins
5. **Creates** missing agents/skills via plugin-dev when gaps exist
6. **Delegates** work to appropriate specialists
7. **Supervises** execution with active progress monitoring
8. **Course-corrects** when agents go off-track

## Relationship to Existing Workflows

The secretary is a **layer above** existing workflow commands, not a replacement:

| Scenario | Behavior |
|----------|----------|
| User says "Add notifications feature" | Secretary routes to `/iflow-dev:brainstorm` → existing workflow |
| User says "Review this code" | Secretary finds `security-reviewer` agent → direct delegation |
| User says "Make auth better" | Secretary clarifies → routes to appropriate workflow/agent |
| User says "Generate API docs" | Secretary identifies gap → creates agent → uses it |

Secretary wraps existing commands when appropriate, delegates directly when simpler.

## User Stories

### US1: Vague Request Interpretation
**As a** user with a vague request
**I want** the secretary to understand my intent
**So that** I don't need to know the exact agent or command to use

**Example:**
- User: "Make the auth better"
- Secretary interprets: security hardening? UX improvement? performance? asks clarifying questions
- Once clarified, delegates to appropriate agent(s)

### US2: Automatic Capability Discovery
**As a** user making a request
**I want** the secretary to find the right agent automatically
**So that** I don't need to know what agents are available

**Example:**
- User: "Review my code for security issues"
- Secretary discovers `iflow-dev:security-reviewer` exists
- Delegates with appropriate context

### US3: Gap Filling
**As a** user needing a capability that doesn't exist
**I want** the secretary to create it
**So that** my request still gets fulfilled

**Example:**
- User: "Generate API documentation"
- Secretary finds no documentation-generator agent
- Creates one via plugin-dev, then uses it

### US4: Multi-Agent Orchestration
**As a** user with a complex task
**I want** the secretary to coordinate multiple agents
**So that** I get a complete solution

**Example:**
- User: "Add a new feature for user notifications"
- Secretary recognizes this as a feature request → invokes `/iflow-dev:brainstorm`
- Workflow proceeds through existing phases (specify → design → implement)

### US5: Active Supervision
**As a** user delegating to agents
**I want** the secretary to monitor progress
**So that** work doesn't go off-track

**Example:**
- Implementer agent starts over-engineering
- Secretary detects deviation via checkpoint, intervenes
- Redirects agent back to original scope

## Functional Requirements

### FR1: Request Interpretation
- Parse natural language requests to extract intent
- Identify ambiguities requiring clarification
- Use AskUserQuestion for targeted disambiguation
- Maintain conversation context for follow-up requests

### FR2: Agent Discovery
- Query all installed plugins for available agents
- Parse agent frontmatter to understand capabilities
- Match request intent to agent descriptions
- Rank matches by relevance

### FR3: Capability Gap Analysis
- Compare required skills to available agents
- Identify specific gaps (missing agent, missing skill, missing tool)
- Propose new component specifications

### FR4: Auto-Creation of Missing Components *(Phase 3 - depends on agent-creator)*
- Generate agent/skill specs based on identified gaps
- Invoke plugin-dev:agent-creator with spec *(requires building this agent first)*
- Validate created components before use
- Add to discovery registry

### FR5: Task Delegation
- Construct appropriate prompts for delegated agents
- Pass necessary context (not excessive)
- Set up supervision checkpoints
- Handle parallel vs sequential execution

### FR6: Progress Supervision
- Define checkpoint intervals based on task complexity
- Compare agent progress against expected trajectory
- Detect: scope creep, infinite loops, hallucinations, blocked state
- Intervene with corrections or early termination

### FR7: Context Management
- **Session-wide (secretary only):** remember clarifications and preferences within secretary's context
- **Per-request (passed to subagents):** explicit task description, relevant context summary
- **Persistent:** store learned user patterns in config file

Note: Subagents have isolated context windows. They only see what secretary explicitly passes to them.

## Technical Design

### Architecture Pattern: Supervisor with LLM-Based Routing

Based on research findings, the secretary uses:
- **LLM-based routing** for flexible request classification [^1]
- **Supervisor pattern** for orchestration and course-correction [^2]
- **Checkpoint-based supervision** (no real-time inter-agent communication)

**Why these patterns:**
- LLM routing is more flexible than rule-based matching for vague requests
- Supervisor pattern enables course-correction without complex agent-to-agent protocols
- Checkpoints work within Claude Code's model where subagents return results to parent

### Agent Discovery Mechanism

```
1. List plugins from .claude.json mcpServers + .claude-plugin/marketplace.json
2. For each plugin, glob for agents/*.md
3. Parse frontmatter: name, description, tools
4. Build capability index (in-memory, session-scoped)
5. Use index for subsequent lookups
```

### Capability Matching Algorithm

```
1. Load all agent descriptions into secretary's context (one-time per session)
2. Present user request + all agent descriptions to LLM
3. LLM evaluates fit and returns ranked matches with confidence scores
4. If no match > 70% confidence, flag as gap

Trade-off: Loading all descriptions uses context tokens but enables
semantic matching. For typical plugin setups (<20 agents), this is
~2000 tokens—acceptable overhead for accurate routing.
```

**Fallback for large agent sets (>50 agents):**
1. Pre-filter by keyword matching on description
2. Load top 10 candidates into context
3. LLM evaluates reduced set

### Agent Invocation Mechanism

Secretary invokes discovered agents via the **Task tool**:

```javascript
// Secretary constructs Task tool call dynamically
Task({
  subagent_type: "plugin-name:agent-name",  // e.g., "iflow-dev:security-reviewer"
  description: "Review auth module for security issues",
  prompt: `Review the following files for security vulnerabilities:
           ${file_list}

           Focus on: ${clarified_user_intent}

           Return findings in structured format.`
})
```

For workflow commands, secretary uses Bash or direct skill invocation:
```javascript
// Route to existing workflow
Skill({ skill: "iflow-dev:brainstorm", args: "user notifications feature" })
```

### Gap-Fill Workflow *(Phase 3)*

**Prerequisite:** Build `plugin-dev:agent-creator` agent first.

```
1. Secretary identifies gap: "Need agent for API documentation"
2. Draft agent spec:
   - name: "api-doc-generator"
   - description: "Generates API documentation from code"
   - tools: [Read, Grep, Glob, Write]
   - system_prompt: [generated instructions]
3. Invoke: Task({ subagent_type: "plugin-dev:agent-creator", prompt: spec })
4. agent-creator writes agent file to plugins/secretary-generated/agents/
5. Secretary re-runs discovery to find new agent
6. Validate: delegate test task, verify output format
7. If validation fails, escalate to user (max 2 attempts)
```

**Agent namespace decision:** Auto-created agents go to `plugins/secretary-generated/` directory:
- Separates generated from hand-crafted agents
- Easy to audit and clean up
- Doesn't pollute development plugins

### Supervision Checkpoints

Use checkpoint-based supervision since real-time monitoring isn't available:

**Complexity heuristics:**
| Criteria | Supervision Level |
|----------|-------------------|
| Single file, simple edit | Light (completion review only) |
| 2-3 files, moderate changes | Standard (initial + completion) |
| 4+ files or complex logic | Full (initial + milestones + completion) |

**Checkpoint evaluation:**
- On-track: continue
- Minor deviation: add corrective guidance via follow-up prompt
- Major deviation: terminate subagent, restart with refined prompt
- Blocked: escalate to user with context

### Hook Integration

**Verified capability:** SubagentStop hooks with `type: "prompt"` are supported per Claude Code documentation.

```json
{
  "hooks": {
    "SubagentStop": [{
      "matcher": "*",
      "hooks": [{
        "type": "prompt",
        "prompt": "Evaluate if subagent completed its delegated task correctly. Check: (1) Task completed per spec (2) No scope creep (3) Output format correct. Return {\"decision\": \"approve\"} or {\"decision\": \"block\", \"reason\": \"...\"}",
        "timeout": 15
      }]
    }]
  }
}
```

## Entry Points

### Explicit Invocation
- `/secretary <request>` - process a request
- `/secretary help` - explain capabilities
- `/secretary status` - show active delegations
- `/secretary mode <manual|aware|proactive>` - show/set activation mode

### Configurable Activation
Activation mode is stored in `.claude/secretary.local.md` and controls how proactively secretary engages:

| Command | Effect |
|---------|--------|
| `/secretary mode manual` | Only responds when explicitly invoked |
| `/secretary mode aware` | Injects awareness at session start |
| `/secretary mode proactive` | Evaluates every prompt, suggests routing |

**Note:** The `/secretary mode` command updates the config file. Changes take effect on next session since hooks read config at startup.

## Agent Definition

```yaml
---
name: secretary
description: |
  Intelligent orchestrator that interprets vague requests, discovers available agents,
  creates missing capabilities, delegates work, and supervises execution.

  Use this agent when:
  - You have a vague or complex request
  - You don't know which agent to use
  - A task requires multiple specialized agents
  - You want supervised, coordinated execution
tools: [Read, Write, Edit, Glob, Grep, Task, AskUserQuestion, Bash, Skill]
model: opus
---
```

## Context Persistence

### Session Memory (secretary-only)
Secretary maintains in its own context:
- Clarified interpretations from user Q&A
- User preference signals observed during session
- Active delegation status and history

**Important:** This memory is NOT shared with subagents. Subagents only receive explicit context passed via Task tool prompt.

### Persistent Config (.claude/secretary.local.md)
```yaml
---
preferred_review_agents: [security-reviewer, code-quality-reviewer]
auto_create_missing: true
supervision_level: adaptive  # light, standard, full, adaptive
default_checkpoint_interval: 3
activation_mode: manual  # manual | aware | proactive
---
```

**Activation Modes:**
| Mode | Behavior | Mechanism |
|------|----------|-----------|
| `manual` | Only responds to `/secretary` command | None |
| `aware` | Injects context at session start | SessionStart hook (command type) |
| `proactive` | Evaluates every prompt, suggests routing | UserPromptSubmit hook (prompt type) |

Toggle via: Edit `.claude/secretary.local.md` and change `activation_mode`, then restart session.

### Activation Hooks

**SessionStart Hook (mode: aware)**

Note: SessionStart only supports `type: "command"` hooks, not prompt hooks.

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "startup|resume",
      "hooks": [{
        "type": "command",
        "command": "${CLAUDE_PLUGIN_ROOT}/hooks/inject-secretary-context.sh"
      }]
    }]
  }
}
```

The bash script outputs context injection:
```bash
#!/bin/bash
# inject-secretary-context.sh
cat << 'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Secretary agent available for orchestrating complex requests. For vague or multi-step tasks, consider: Task({ subagent_type: 'iflow-dev:secretary', prompt: <user_request> })"
  }
}
EOF
```

**UserPromptSubmit Hook (mode: proactive)**

Note: UserPromptSubmit fires on EVERY user prompt (matchers are ignored for this event).

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "hooks": [{
        "type": "prompt",
        "prompt": "Evaluate if this user prompt would benefit from secretary orchestration. Signs: vague request ('make it better', 'fix this'), multi-step task, unclear which agent fits. Return {\"decision\": \"block\", \"reason\": \"Route through secretary\", \"systemMessage\": \"Consider using secretary agent for this request.\"} to suggest routing, or {} to proceed normally.",
        "timeout": 5
      }]
    }]
  }
}
```

**Proactive Mode Considerations:**
- Adds ~2-5 seconds latency to every prompt (Haiku evaluation)
- On hook timeout/failure: fail-open (prompt proceeds normally)
- If user declines routing suggestion: prompt proceeds with original intent
- Cost: ~100 tokens per prompt evaluation

**Recommendation:** Start with `manual` or `aware` mode. `proactive` mode is higher friction and best suited for users who frequently work with vague requirements.

### Hook Enablement Mechanism

The secretary plugin uses **conditional hook scripts** rather than dynamic hooks.json modification:

1. All three hooks are registered in hooks.json
2. Each hook script reads `activation_mode` from `.claude/secretary.local.md`
3. If mode doesn't match, script exits with no output (no-op)
4. If mode matches, script executes its logic

This avoids modifying hooks.json at runtime while still enabling mode-based behavior.

```bash
# Example: inject-secretary-context.sh
#!/bin/bash
MODE=$(grep "^activation_mode:" .claude/secretary.local.md | cut -d' ' -f2)
if [ "$MODE" != "aware" ]; then
  exit 0  # No-op for other modes
fi
# ... actual context injection ...
```

## Success Criteria (Qualitative for v1)

Quantitative metrics require tracking infrastructure not yet available. For v1, success is qualitative:

| Criterion | Evidence |
|-----------|----------|
| Request resolution | User doesn't need to manually re-route to different agent |
| Clarification quality | User confirms interpretation is correct before major work |
| Delegation accuracy | Subagent produces relevant output on first attempt |
| Supervision effectiveness | User doesn't report off-track work after secretary delegates |

**Future (with logging):** Track resolution rate, clarification count, override rate.

## Risks and Mitigations

### Risk: Infinite Loop in Gap-Fill
Secretary creates agent → agent inadequate → creates another → loop

**Mitigation:** Max 2 creation attempts per request; escalate to user after

### Risk: Over-Interpretation
Secretary makes wrong assumptions about user intent

**Mitigation:** Always confirm interpretation before major actions; show reasoning

### Risk: Context Bloat
Passing too much context to delegated agents

**Mitigation:** Summarize context; pass only task-relevant information [^3]

### Risk: Supervision Overhead
Checkpoints slow down simple tasks

**Mitigation:** Adaptive supervision based on complexity heuristics (see above)

## Implementation Phases

### Phase 1a: Discovery + Interpretation (MVP)
- Agent discovery across plugins (glob + parse frontmatter)
- Request interpretation with clarification flow
- Manual routing recommendation (suggest agent, user confirms)

### Phase 1b: Delegation + Review
- Single-agent delegation via Task tool
- Completion review (simple SubagentStop check)
- Result presentation to user

### Phase 2: Active Supervision
- Complexity-based checkpoint levels
- Deviation detection and correction
- Full SubagentStop hook integration

### Phase 3: Auto-Creation
**Prerequisite:** Build `plugin-dev:agent-creator` agent
- Gap analysis and spec generation
- agent-creator integration
- Validation before use
- `secretary-generated` plugin namespace

### Phase 4: Context Learning
- Session memory utilization
- Persistent preference configuration
- Pattern-based optimization

## Out of Scope (v1)

- Real-time inter-agent communication (platform limitation)
- GUI/visual orchestration view
- Cross-session memory beyond explicit config
- Cost optimization routing (always use specified model)

## Decisions Made

| Question | Decision | Rationale |
|----------|----------|-----------|
| Explicit vs implicit activation | Explicit only (v1) | Reduces surprise; users opt-in to orchestration |
| Model selection | Opus for interpretation | Vague requests need strong reasoning; simpler routing can use Haiku in future |
| Agent namespace | `plugins/secretary-generated/` | Clean separation, easy audit, no dev plugin pollution |
| Delegation transparency | Show routing decision | User sees "Delegating to security-reviewer because..." for trust |

## Research Findings Summary

Key insights from research that informed this design:

**From LangGraph [^1]:**
- Subagents pattern: coordinator manages specialists as tools ✓ adopted
- Skills pattern (single agent loads prompts) rejected—separate agents provide context isolation

**From Microsoft AI Patterns [^2]:**
- Supervisor pattern for managed coordination ✓ adopted
- Handoff pattern (dynamic delegation) ✓ adopted for agent-to-agent routing
- Group chat limited to ≤3 agents to prevent loops ✓ noted for future

**From Multi-Agent Failure Research:**
- Error cascade prevention via supervision checkpoints ✓ adopted
- Max retry limits to prevent infinite loops ✓ adopted (2 attempts)

## References

[^1]: LangGraph Multi-Agent Patterns - https://docs.langchain.com/oss/python/langchain/multi-agent - Informed subagent architecture and routing strategy
[^2]: Microsoft AI Agent Orchestration Patterns - https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns - Supervisor and handoff patterns
[^3]: Context window management research - pass only task-relevant information to avoid latency without value
