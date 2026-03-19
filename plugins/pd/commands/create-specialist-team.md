---
description: Create ephemeral specialist teams for complex tasks
argument-hint: <task description>
---

# /pd:create-specialist-team Command

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Create and deploy a team of specialists for a complex task.

## No Arguments

If no argument provided:

Display brief usage:
```
Usage: /pd:create-specialist-team <task description>

Creates an ephemeral team of specialists to analyze or implement a complex task.

Examples:
  /pd:create-specialist-team "analyze auth security and suggest improvements"
  /pd:create-specialist-team "research caching strategies for our API"
  /pd:create-specialist-team "implement and test a rate limiter"
```

## Main Flow

### Step 1: Analyze Task

Parse the task description to determine:

1. **Domains** — what areas of expertise are needed (security, performance, testing, etc.)
2. **Capabilities** — what tools are required (read-only analysis vs implementation)
3. **Team size** — how many specialists (cap at 5)
4. **Coordination pattern**:
   - **Sequential pipeline** — output of one feeds into next (e.g., analyze → implement → test)
   - **Parallel fan-out** — independent specialists working simultaneously (e.g., security + performance + quality review)

### Step 2: Select Templates and Confirm

Available templates (locate via two-location Glob: `~/.claude/plugins/cache/*/pd*/*/skills/creating-specialist-teams/references/`, fallback `plugins/*/skills/creating-specialist-teams/references/`):

| Template | Best For |
|----------|----------|
| `code-analyzer.template.md` | Read-only code analysis, pattern detection, structural findings |
| `research-specialist.template.md` | Evidence gathering, best practices research, comparisons |
| `implementation-specialist.template.md` | Writing code with TDD, making changes |
| `domain-expert.template.md` | Advisory analysis, architectural recommendations |
| `test-specialist.template.md` | Test coverage, edge cases, test implementation |

Map task domains to templates. Assign specific focus areas to each specialist.

**Present team for approval:**
```
AskUserQuestion:
  questions: [{
    question: "Proposed team for '{task}'. Deploy?",
    header: "Team",
    options: [
      { label: "Deploy", description: "{n} specialists: {list with roles}" },
      { label: "Customize", description: "Modify team composition" },
      { label: "Cancel", description: "Abort" }
    ],
    multiSelect: false
  }]
```

**If user selects "Customize":**
```
AskUserQuestion:
  questions: [{
    question: "Select specialists for this team:",
    header: "Customize",
    options: [
      { label: "Code Analyzer", description: "Read-only analysis of codebase patterns" },
      { label: "Research Specialist", description: "Web research for best practices" },
      { label: "Implementation Specialist", description: "Write code with TDD" },
      { label: "Domain Expert", description: "Advisory recommendations" }
    ],
    multiSelect: true
  }]
```
Then re-confirm the customized team.

**YOLO override:** If args contain `[YOLO_MODE]`, skip team approval and auto-deploy recommended team.

### Step 3: Inject Context

For each selected template:

1. Read the scaffold template via two-location Glob:
   ```
   Glob ~/.claude/plugins/cache/*/pd*/*/skills/creating-specialist-teams/references/{type}.template.md — read first match.
   Fallback: Read plugins/pd/skills/creating-specialist-teams/references/{type}.template.md (dev workspace).
   ```

2. Gather codebase context relevant to the task:
   - Glob for files related to the task keywords
   - Grep for relevant code patterns
   - Limit context to most relevant 10-15 files

3. Gather workflow context:
   - Glob for `{pd_artifacts_root}/features/*/.meta.json`
   - Find the active feature (`"status": "active"`)
     - If multiple active features: use highest ID number, log warning
   - If found: extract id, slug, lastCompletedPhase, mode; determine next phase
      by calling `get_phase("feature:{id}-{slug}")` (using `id` and `slug` extracted above).
      Parse the JSON response: if `current_phase` is non-null, use it; if null, determine next
      phase from `last_completed_phase` using the canonical sequence in workflow-state SKILL.md.
      If MCP unavailable, fall back to `lastCompletedPhase` from `.meta.json` (already extracted).
      Apply the same edge cases: null+null → route to specify, last=finish → complete, no active feature → brainstorm.
     Check which artifacts exist (prd.md, spec.md, design.md, plan.md, tasks.md)
   - Format as:
     ```
     Active feature: {id}-{slug} ({mode} mode)
     Current phase: {phase}
     Next phase: {next phase}
     Artifacts: {comma-separated existing artifacts}
     Directory: {pd_artifacts_root}/features/{id}-{slug}/
     ```
   - If no active feature: "No active feature workflow. Specialist output is standalone."
   - If gathering fails (Glob error, malformed JSON): "Workflow context unavailable."

4. Fill template placeholders:
   - `{TASK_DESCRIPTION}` — the specific assignment for this specialist
   - `{CODEBASE_CONTEXT}` — relevant files and patterns found
   - `{WORKFLOW_CONTEXT}` — workflow state gathered in step 3
   - `{SUCCESS_CRITERIA}` — what constitutes successful output
   - `{OUTPUT_FORMAT}` — structured format for findings
   - `{SCOPE_BOUNDARIES}` — what the specialist should NOT do

### Step 4: Deploy Specialists

Dispatch each specialist via generic-worker:

```
Task({
  subagent_type: "pd:generic-worker",
  model: "opus",
  description: "{role}: {brief assignment}",
  prompt: "{filled template content}"
})
```

**Coordination patterns:**
- **Parallel fan-out**: Dispatch specialists in batches of `max_concurrent_agents` (from session context, default 5). If team size exceeds the limit, dispatch in waves — wait for each wave to complete before the next.
- **Sequential pipeline**: Dispatch first specialist, wait for result, include result in next specialist's context

### Step 5: Synthesize Results

After all specialists complete:

1. Collect outputs from all specialists
2. Present combined results:

```
## Specialist Team Results

### Task: {original description}
### Team: {list of specialists}

{For each specialist:}
#### {Role} Findings
{specialist output}

---

### Synthesis
{Brief summary of key findings across all specialists}

### Recommended Next Steps
{Actionable follow-ups based on combined findings}
```

3. **Assess workflow routing** — determine which workflow phase matches the specialist outputs:

   Read active feature state (Glob `{pd_artifacts_root}/features/*/.meta.json`, find `"status": "active"`).

   Phase names map 1:1 to commands: `pd:{phase-name}`, except:
   - finish → `pd:finish-feature`

   #### If no active feature:
   | Output signals | Recommended action |
   |---------------|-------------------|
   | Research/exploration findings, problem framing | `/brainstorm` — seed brainstorm with findings |
   | Detailed requirements, acceptance criteria | `/create-feature` — findings are specified enough |
   | Code fixes already implemented | Done — standalone fix, no feature needed |
   | General analysis | `/brainstorm` — formalize into a feature |

   #### If active feature exists:
   Determine next phase from `lastCompletedPhase`. Check if specialist output aligns:

   | Output signals | Suggested phase (.meta.json name) |
   |---------------|----------------------------------|
   | Research, trade-off analysis, recommendations | `specify` (if brainstorm done) |
   | Requirements, acceptance criteria, success criteria | `specify` |
   | Architecture, components, interfaces, contracts | `design` |
   | Prioritized action items, implementation plan | `create-plan` |
   | Code changes, tests added, implementation complete | `implement` (continue) or `finish` |
   | Coverage gaps, test results | `implement` (address gaps) |

   If the suggested phase differs from the MCP-reported current phase (from the
   `get_phase` response `current_phase` field), recommend the current phase instead
   (prerequisites must be satisfied first).

4. **Present workflow-aware follow-up:**

```
AskUserQuestion:
  questions: [{
    question: "What would you like to do with these results?",
    header: "Follow-up",
    options: [
      { label: "Continue to /{recommended-phase}", description: "{reason} (Recommended)" },
      { label: "Deep dive", description: "Investigate specific findings further" },
      { label: "Done", description: "Results meet acceptance criteria" }
    ],
    multiSelect: false
  }]
```

   If user selects the recommended phase:
     `Skill({ skill: "pd:{phase-command}", args: "{synthesized context}" })`

   If user selects "Deep dive":
     Offer focused follow-up team (existing behavior).

   **YOLO override:** If `[YOLO_MODE]` active, skip AskUserQuestion and directly invoke
   the recommended phase.
