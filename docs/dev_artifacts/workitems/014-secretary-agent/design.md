# Design: Secretary Agent

## Architecture Overview

The secretary agent is a **supervisor pattern** implementation that routes user requests to specialized agents through LLM-based capability matching.

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Request                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    /secretary Command                           │
│  (Entry point - parses subcommands: help, mode, <request>)      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Secretary Agent                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Discovery   │→ │ Interpreter  │→ │   Matcher    │          │
│  │   Module     │  │    Module    │  │    Module    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│         │                                    │                  │
│         ▼                                    ▼                  │
│  ┌──────────────┐                    ┌──────────────┐          │
│  │ Agent Index  │                    │ Recommender  │          │
│  │ (in-memory)  │                    │    Module    │          │
│  └──────────────┘                    └──────────────┘          │
│                                              │                  │
│                                              ▼                  │
│                                      ┌──────────────┐          │
│                                      │  Delegator   │          │
│                                      │    Module    │          │
│                                      └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Specialist Agents                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  security-   │  │    code-     │  │   iflow-dev  │          │
│  │   reviewer   │  │   quality    │  │   workflows  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. Command Component (`/secretary`)

**Responsibility:** Entry point that routes to appropriate behavior based on subcommand.

**Location:** `plugins/iflow-dev/commands/secretary.md`

**Behavior:**
- `/secretary help` → Display usage instructions inline
- `/secretary mode` → Read and display current mode from config
- `/secretary mode <mode>` → Update config file
- `/secretary <request>` → Invoke secretary agent via Task tool

**Design Decision:** Command is thin wrapper that delegates to agent for complex logic. This keeps the command simple and testable.

---

### 2. Secretary Agent

**Responsibility:** Core orchestration logic—discovery, interpretation, matching, recommendation, delegation.

**Location:** `plugins/iflow-dev/agents/secretary.md`

**Internal Modules (conceptual, implemented in system prompt):**

#### 2.1 Discovery Module

**Input:** None (uses Glob tool)
**Output:** Agent index (array of `{plugin, name, description, tools}`)

**Algorithm:**
```
1. Check for .claude-plugin/marketplace.json
   a. If exists: read and extract plugin paths from "plugins" array
      Expected structure:
      {
        "plugins": [
          { "name": "plugin-name", "source": "./plugins/plugin-name" },
          ...
        ]
      }
   b. If not exists: fall back to glob-all approach (plugins/*/agents/*.md)
2. For each plugin:
   a. Glob {plugin_path}/agents/*.md
3. For each agent file:
   a. Extract plugin name from path (parent directory name)
   b. Read file content via Read tool
   c. Parse YAML frontmatter (text extraction between --- markers)
   d. Extract: name, description, tools
   e. Validate: name and description required; tools optional (default: all)
4. Return array of agent records
```

**YAML Frontmatter Parsing:**
The agent uses the Read tool to get file content, then extracts frontmatter:
```
1. Find content between first two "---" lines
2. For each line in frontmatter:
   - Split on first ":" to get key/value
   - Handle multi-line values (indented continuation)
   - Handle arrays (lines starting with "- ")
3. LLM interprets structure—no external YAML parser needed
```

Note: This relies on LLM's text understanding capability rather than a formal parser.
Well-formed frontmatter is expected; malformed files are skipped.

**Validation Rules:**
- `name`: Required. Must be lowercase with hyphens.
- `description`: Required. Used for matching.
- `tools`: Optional. Defaults to full tool access if omitted.

**Error Handling:**
- Marketplace.json not found: Fall back to glob `plugins/*/agents/*.md`
- Parse failure: Skip file, log warning, continue with others
- Missing required field: Skip file, continue
- No agents found: Return empty array (handled by Matcher)

#### 2.2 Interpreter Module

**Input:** Raw user request string
**Output:** Clarified intent string

**Algorithm:**
```
1. Analyze request for ambiguity signals:
   - Vague terms: "better", "improve", "fix", "help"
   - Multiple domains: "auth and UI"
   - Missing action verb
2. If ambiguous:
   a. Generate clarifying question(s)
   b. Use AskUserQuestion (max 3 questions)
   c. Incorporate answers into clarified intent
3. Return clarified intent
```

**Design Decision:** Interpreter is LLM-driven, not rule-based. The secretary's system prompt guides interpretation behavior rather than explicit code.

#### 2.3 Matcher Module

**Input:** Clarified intent, Agent index
**Output:** Ranked matches with confidence scores

**Algorithm:**
```
1. If agent count <= 20:
   a. Load all agent descriptions into matching prompt
2. If agent count > 20:
   a. Extract keywords from user intent (nouns, verbs, domain terms)
   b. Score each agent by keyword overlap with description
   c. Take top 10 by keyword score
   d. Load these 10 into matching prompt
3. LLM evaluates semantic fit against loaded agents
4. Parse response for:
   - matches: [{agent, confidence, reason}]
   - recommendation: best match or null
   - workflow_match: recognized workflow or null
5. Return matches sorted by confidence
```

**Keyword Extraction (for >20 agents):**
Simple word overlap algorithm:
```
1. Tokenize user intent into words
2. Remove stop words (the, a, an, is, etc.)
3. For each agent: count matching words in description
4. Rank by match count (ties broken alphabetically)
```

Note: This is a coarse pre-filter. LLM semantic matching handles nuance.

**Confidence Thresholds:**
- >70%: Strong match, recommend
- 50-70%: Alternative, show as option
- <50%: Don't show

#### 2.4 Recommender Module

**Input:** Ranked matches
**Output:** User-facing recommendation with AskUserQuestion

**Algorithm:**
```
1. Format recommendation message:
   - Show understanding of intent
   - Show top match with confidence and reason
   - List alternatives >50% confidence (max 3 shown)
2. Use AskUserQuestion with options:
   - Accept (proceed with top match)
   - [Alternative names] (if alternatives exist, each as separate option)
   - Cancel (abort)
3. Return user's choice
```

**Alternative Selection Flow:**
When alternatives exist, they are shown directly as options (not nested):
```
AskUserQuestion:
  questions: [{
    question: "I'll delegate to security-reviewer (92% match). Confirm?",
    header: "Routing",
    options: [
      { label: "Accept security-reviewer", description: "Best match for security review" },
      { label: "Use code-quality-reviewer", description: "Alternative: 62% match" },
      { label: "Cancel", description: "Abort request" }
    ],
    multiSelect: false
  }]
```

If user selects an alternative, proceed directly to delegation with that agent.
"Other" option allows user to type a custom agent reference manually.

#### 2.5 Delegator Module

**Input:** Selected agent, clarified intent
**Output:** Delegation result

**Algorithm:**
```
1. If workflow_match:
   a. Use Skill tool to invoke workflow command
   b. Return result
2. Else:
   a. Construct Task tool call:
      - subagent_type: selected agent
      - description: brief summary
      - prompt: clarified intent + context
   b. Invoke Task tool
   c. Return result to user
```

---

### 3. Hook Component (Aware Mode)

**Responsibility:** Inject secretary awareness at session start when mode=aware.

**Location:** `plugins/iflow-dev/hooks/inject-secretary-context.sh`

**Behavior:**
```bash
1. Read activation_mode from .claude/secretary.local.md
2. If mode != "aware": exit 0 (no-op)
3. Output JSON with hookSpecificOutput.additionalContext
```

**Design Decision:** Conditional hook script rather than dynamic hooks.json modification. All hooks are registered, but scripts check mode and exit early if not applicable.

---

### 4. Configuration Component

**Responsibility:** Store user preferences for secretary behavior.

**Location:** `.claude/secretary.local.md` (user creates)

**Schema:**
```yaml
---
activation_mode: manual  # manual | aware | proactive
preferred_review_agents: []
auto_create_missing: false
supervision_level: light
---
```

**Default Behavior (Config Not Found):**
When `.claude/secretary.local.md` does not exist:
- `activation_mode` defaults to `manual`
- Hook scripts exit 0 (no-op) since mode != aware
- `/secretary mode` reports "Config not found. Using defaults (manual mode)."
- `/secretary mode <mode>` creates the config file with specified mode

**Config Creation (on first `/secretary mode <mode>`):**
```
1. Check if .claude/ directory exists; create if not
2. Write default config with specified activation_mode
3. Report "Config created at .claude/secretary.local.md"
```

**Design Decision:** Use .local.md pattern (YAML frontmatter in markdown) consistent with other plugin config files. Not tracked in git.

**Note on `preferred_review_agents`:** This field is included for future Phase 2+ use. In Phase 1a, it is read but not used. When multiple reviewers match equally, preferences would break ties.

---

## Technical Decisions

### TD-1: LLM-Based Matching vs Rule-Based

**Decision:** Use LLM-based semantic matching

**Rationale:**
- Vague requests don't map well to keywords
- Agent descriptions are natural language
- LLM can understand semantic similarity
- More flexible as agents are added

**Trade-off:** Uses more tokens per request (~2000 for agent descriptions). Acceptable for typical plugin sets (<20 agents).

---

### TD-2: Per-Request Discovery vs Cached Index

**Decision:** Rebuild index per request (no caching in Phase 1a)

**Rationale:**
- Agents may be added/removed between requests
- Index is small (~20 agents typical)
- Simpler implementation
- Caching optimization deferred to Phase 4

**Trade-off:** Redundant file reads. Negligible performance impact for <50 agents.

---

### TD-3: Confirmation Before Delegation

**Decision:** Always require user confirmation before delegating

**Rationale:**
- Builds trust—user sees routing decision
- Prevents mistakes from misinterpretation
- Allows user to correct or cancel
- Matches "manual" mode philosophy

**Trade-off:** Extra interaction step. Acceptable for first version; can add "auto-accept" option later.

---

### TD-4: Thin Command, Fat Agent

**Decision:** Command handles only subcommand routing; agent contains all business logic

**Rationale:**
- Agent has full tool access (Glob, Read, Task, AskUserQuestion)
- Agent can maintain context across multi-turn interactions
- Command is simple string parsing, easily tested
- Follows existing iflow-dev patterns

---

### TD-5: Conditional Hooks vs Dynamic Registration

**Decision:** Register all hooks in hooks.json, use conditional scripts

**Rationale:**
- hooks.json is static (read at session start)
- Can't dynamically add/remove hooks at runtime
- Conditional scripts check mode and exit early
- Simpler than generating hooks.json

**Implementation:**
```bash
# All hooks registered, but:
if [ "$MODE" != "aware" ]; then
  exit 0  # No-op
fi
```

---

## Data Flow

### Request Processing Flow

```
User: "/secretary review auth for security"
                    │
                    ▼
┌─────────────────────────────────────────┐
│ Command: Parse subcommand               │
│ → Not help/mode, invoke secretary agent │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│ Discovery: Glob plugins/*/agents/*.md   │
│ → Parse frontmatter, build index        │
│ → Returns: [{plugin:"iflow-dev",        │
│     name:"security-reviewer",           │
│     description:"Reviews code..."}]     │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│ Interpreter: Analyze request            │
│ → "review auth for security" is clear   │
│ → No clarification needed               │
│ → Returns: "review auth for security"   │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│ Matcher: LLM semantic evaluation        │
│ → Compare intent to agent descriptions  │
│ → Returns: [{agent:"iflow-dev:security- │
│     reviewer", confidence:92}]          │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│ Recommender: Present to user            │
│ → "Recommended: security-reviewer (92%)"│
│ → AskUserQuestion: Accept/Cancel        │
│ → User selects: Accept                  │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│ Delegator: Invoke via Task tool         │
│ → Task({subagent_type:"iflow-dev:       │
│     security-reviewer", prompt:...})    │
│ → Wait for completion                   │
│ → Present results to user               │
└─────────────────────────────────────────┘
```

---

## Risks and Mitigations

### Risk 1: Poor Matching Accuracy

**Risk:** LLM matcher recommends wrong agent, user accepts, work is wasted.

**Mitigation:**
- Show confidence score and reasoning
- Always require user confirmation
- Show alternatives when multiple matches exist

### Risk 2: Discovery Performance

**Risk:** Too many agents slows down discovery phase.

**Mitigation:**
- Current: Acceptable for <50 agents
- Future (Phase 4): Cache index with invalidation on file change

### Risk 3: Vague Clarification

**Risk:** Interpreter asks unclear questions, user gives unhelpful answers.

**Mitigation:**
- Limit to 3 questions max
- Use AskUserQuestion with concrete options where possible
- Fall back to best-effort interpretation

### Risk 4: Context Bloat in Delegation

**Risk:** Secretary passes too much context to subagent, causing confusion.

**Mitigation:**
- Summarize context, don't pass raw
- Include only task-relevant information
- Follow "minimal context" principle from PRD

---

## Dependencies

| Dependency | Type | Purpose |
|------------|------|---------|
| Claude Code Task tool | Platform | Invoke subagents |
| Claude Code Glob tool | Platform | Discover agent files |
| Claude Code Read tool | Platform | Parse agent frontmatter |
| Claude Code AskUserQuestion | Platform | User interaction |
| Claude Code Skill tool | Platform | Invoke workflow commands |
| YAML frontmatter parsing | In-agent | Extract agent metadata |

---

## File Inventory

| File | Type | Status |
|------|------|--------|
| `plugins/iflow-dev/agents/secretary.md` | Agent | NEW |
| `plugins/iflow-dev/commands/secretary.md` | Command | NEW |
| `plugins/iflow-dev/hooks/inject-secretary-context.sh` | Script | NEW |
| `plugins/iflow-dev/hooks/hooks.json` | Config | MODIFY |
| `.claude/secretary.local.md` | User config | Template provided |

### hooks.json Modification Details

Add the following entry to the existing `hooks` object in `plugins/iflow-dev/hooks/hooks.json`:

```json
{
  "hooks": {
    // ... existing hooks ...
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/inject-secretary-context.sh"
          }
        ]
      }
    ]
  }
}
```

Note: If `SessionStart` already has entries, append this matcher configuration to the existing array.

---

## Interfaces

### Interface 1: Command → Agent

**Purpose:** Command invokes secretary agent for request processing.

**Contract:**
```typescript
// Command invokes via Task tool
interface CommandToAgentInvocation {
  subagent_type: "iflow-dev:secretary";
  description: string;  // Brief description of task
  prompt: string;       // User's request
}

// Example:
Task({
  subagent_type: "iflow-dev:secretary",
  description: "Process user request",
  prompt: "User request: review auth module for security issues"
})
```

**Responsibilities:**
- Command: Parse subcommands, invoke agent for non-trivial requests
- Agent: Process request through discovery → interpretation → matching → delegation

---

### Interface 2: Discovery Output

**Purpose:** Agent index data structure used by Matcher module.

**Contract:**
```typescript
interface AgentRecord {
  plugin: string;       // e.g., "iflow-dev"
  name: string;         // e.g., "security-reviewer"
  description: string;  // From frontmatter
  tools: string[];      // From frontmatter (optional)
}

type AgentIndex = AgentRecord[];

// Example:
[
  {
    plugin: "iflow-dev",
    name: "security-reviewer",
    description: "Reviews code for security vulnerabilities...",
    tools: ["Read", "Grep", "Glob"]
  },
  {
    plugin: "iflow-dev",
    name: "code-quality-reviewer",
    description: "Reviews code for quality and best practices...",
    tools: ["Read", "Grep", "Glob"]
  }
]
```

**Source:** Parsed from agent markdown files via Glob + Read tools.

---

### Interface 3: Matcher Output

**Purpose:** Ranked matches returned by capability matching.

**Contract:**
```typescript
interface AgentMatch {
  agent: string;        // "plugin:name" format
  confidence: number;   // 0-100 percentage
  reason: string;       // Why this agent matches
}

interface MatchResult {
  matches: AgentMatch[];           // Sorted by confidence desc
  recommendation: string | null;   // Top match if confidence >70%
  workflow_match: string | null;   // "brainstorm" | "implement" | null
}

// Example:
{
  matches: [
    { agent: "iflow-dev:security-reviewer", confidence: 92, reason: "Specializes in security review" },
    { agent: "iflow-dev:code-quality-reviewer", confidence: 45, reason: "Reviews code but not security-focused" }
  ],
  recommendation: "iflow-dev:security-reviewer",
  workflow_match: null
}
```

**Consumer:** Recommender module uses this to present options to user.

---

### Interface 4: User Confirmation

**Purpose:** AskUserQuestion interaction for routing confirmation.

**Contract:**
```typescript
// AskUserQuestion call - alternatives shown inline
// Note: AskUserQuestion automatically provides an "Other" option for free-text input
interface RoutingConfirmation {
  questions: [{
    question: string;     // "I'll delegate to {agent} ({confidence}% match). Confirm?"
    header: "Routing";
    options: [
      { label: "Accept {agent}", description: "Best match for {intent}" },
      // If alternatives exist, add each as separate option (max 2 alternatives):
      { label: "Use {alt-agent}", description: "Alternative: {alt-confidence}% match" },
      { label: "Cancel", description: "Abort request" }
    ];
    // AskUserQuestion automatically adds "Other" option for custom input
    multiSelect: false;
  }]
}

// Response - matches selected option label or custom text
type UserChoice = string;  // "Accept security-reviewer" | "Use code-quality-reviewer" | "Cancel" | custom text
```

**Flow:**
- "Accept {agent}" → Proceed to delegation with recommended agent
- "Use {alt-agent}" → Proceed to delegation with selected alternative
- "Cancel" → Abort with message
- Custom text (via built-in "Other" option) → Parse as agent reference in format "plugin:agent", attempt delegation if valid format, otherwise report error

---

### Interface 5: Task Delegation

**Purpose:** Secretary delegates to specialist agent.

**Contract:**
```typescript
interface DelegationCall {
  subagent_type: string;   // "plugin:agent" from MatchResult
  description: string;     // Brief task summary
  prompt: string;          // Structured delegation prompt
}

// Delegation prompt structure:
const delegationPrompt = `
Task: ${clarifiedIntent}

Context:
${contextSummary}

Requirements:
${specificRequirements}

Return your findings in structured format.
`;
```

**Example:**
```javascript
Task({
  subagent_type: "iflow-dev:security-reviewer",
  description: "Security review of auth module",
  prompt: `
    Task: Review src/auth/ for security vulnerabilities

    Context:
    User is concerned about authentication security.
    Focus on: input validation, session handling, credential storage.

    Requirements:
    - Check for OWASP Top 10 vulnerabilities
    - Provide severity ratings for findings
    - Suggest fixes for critical issues

    Return your findings in structured format.
  `
})
```

---

### Interface 6: Workflow Routing

**Purpose:** Secretary routes to iflow-dev workflow commands.

**Contract:**
```typescript
// Skill tool call for workflow routing
interface WorkflowRouting {
  skill: string;    // "iflow-dev:brainstorm" | "iflow-dev:implement" | etc.
  args?: string;    // Optional arguments
}

// Pattern recognition
const workflowPatterns: Record<string, string[]> = {
  "iflow-dev:brainstorm": ["new feature", "add capability", "create feature"],
  "iflow-dev:implement": ["implement", "build", "code this"],
  "iflow-dev:create-plan": ["plan", "create plan", "implementation plan"]
};
```

**Example:**
```javascript
// User: "I want to add a notification feature"
// Matcher recognizes workflow pattern
Skill({
  skill: "iflow-dev:brainstorm",
  args: "notification feature"
})
```

---

### Interface 7: Configuration

**Purpose:** User-configurable secretary behavior.

**Contract:**
```yaml
# .claude/secretary.local.md
---
activation_mode: manual | aware | proactive
preferred_review_agents: string[]  # e.g., ["security-reviewer"]
auto_create_missing: boolean       # Phase 3+
supervision_level: light | standard | full | adaptive  # Phase 2+
---
```

**Reading Config (from hook scripts - bash context):**
```bash
# Check if config exists first
if [ -f ".claude/secretary.local.md" ]; then
  MODE=$(grep "^activation_mode:" .claude/secretary.local.md | sed 's/.*: *//')
else
  MODE="manual"  # Default when config not found
fi
```

**Reading Config (from agent - Claude context):**
```
1. Use Read tool to read .claude/secretary.local.md
2. If file not found: use defaults
3. Parse frontmatter (extract between --- markers)
4. Extract activation_mode value
```

**Updating Config (via command):**
```javascript
// /secretary mode aware

// If config exists, use Edit:
Edit({
  file_path: ".claude/secretary.local.md",
  old_string: "activation_mode: manual",
  new_string: "activation_mode: aware"
})

// If config doesn't exist, use Write to create:
Write({
  file_path: ".claude/secretary.local.md",
  content: `---
activation_mode: aware
preferred_review_agents: []
auto_create_missing: false
supervision_level: light
---
`
})
```

---

### Interface 8: Hook Output (Aware Mode)

**Purpose:** SessionStart hook injects secretary awareness.

**Contract:**
```typescript
interface HookOutput {
  hookSpecificOutput: {
    hookEventName: "SessionStart";
    additionalContext: string;
  }
}

// Example output:
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Secretary agent available for orchestrating complex requests. For vague or multi-step tasks, consider: Task({ subagent_type: 'iflow-dev:secretary', prompt: <user_request> })"
  }
}
```

**Trigger:** Script runs on SessionStart event, checks mode, outputs if mode=aware.

---

## Error Interfaces

### Error: No Agents Found

```typescript
interface NoAgentsError {
  type: "NO_AGENTS";
  message: "No agents found. Install plugins with agents first.";
  suggestion: "Run /plugin install <plugin-name>";
}
```

### Error: Parse Failure

```typescript
interface ParseError {
  type: "PARSE_ERROR";
  file: string;
  message: string;
  action: "skip";  // Continue with other agents
}
```

### Error: No Match

```typescript
interface NoMatchResult {
  type: "NO_MATCH";
  message: "No suitable agent found for your request.";
  suggestions: [
    "Describe your task more specifically",
    "Use /secretary help to see available options"
  ];
}
```

### Error: Delegation Failure

```typescript
interface DelegationError {
  type: "DELEGATION_FAILED";
  agent: string;
  error: string;
  options: ["Retry", "Choose different agent", "Cancel"];
}
```
