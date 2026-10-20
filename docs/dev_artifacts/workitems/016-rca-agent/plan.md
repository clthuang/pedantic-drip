# Plan: Root Cause Analysis Agent & Command

## Implementation Order

The build order follows TDD principles and dependency hierarchy:

```
1. Skill reference files (no dependencies)
   ↓
2. SKILL.md (depends on references)
   ↓
3. Agent (depends on skill)
   ↓
4. Command (depends on agent and skill)
   ↓
5. Static Validation (syntax checks)
   ↓
6. Integration Test (functional verification)
```

## Tasks

### Task 1: Create Skill Reference Files

**Files:**
- `plugins/iflow-dev/skills/root-cause-analysis/references/five-whys-template.md`
- `plugins/iflow-dev/skills/root-cause-analysis/references/fishbone-categories.md`
- `plugins/iflow-dev/skills/root-cause-analysis/references/rca-report-template.md`

**Why First:** Reference files have no dependencies. SKILL.md references them.

**Actions:**
1. Create skill directory: `mkdir -p plugins/iflow-dev/skills/root-cause-analysis/references`
2. Create all 3 files atomically (in sequence, verify each before proceeding):
   - five-whys-template.md - 5 Whys worksheet with problem statement, why table, root cause section
   - fishbone-categories.md - Software Ishikawa categories table and mermaid template
   - rca-report-template.md - Full RCA report structure with all sections
3. Verify all files exist: `ls -la plugins/iflow-dev/skills/root-cause-analysis/references/`

**Content Source:** design.md contains full content for each file (see design.md References section).

**Acceptance:** All 3 files exist with complete template content.

**Rollback:** If any file fails, delete the entire `root-cause-analysis/` directory and restart.

---

### Task 2: Create SKILL.md

**File:** `plugins/iflow-dev/skills/root-cause-analysis/SKILL.md`

**Dependencies:** Task 1 (reference files must exist for links to work)

**Actions:**
1. Create SKILL.md with frontmatter (required fields per validate.sh):
   ```yaml
   ---
   name: root-cause-analysis
   description: |
     This skill should be used when the user says 'run RCA', 'thorough investigation',
     'find ALL root causes', 'comprehensive debugging', or runs /root-cause-analysis command.
     For quick debugging guidance, use systematic-debugging skill instead.
     This skill produces a formal RCA report with reproduction, experiments, and evidence.
   ---
   ```
2. Add body content (~1500 words):
   - Process Overview (mermaid diagram showing 6-phase flow)
   - 6 phases with actions, outputs, tools, references
   - Behavioral Rules section
   - Related Resources section linking to systematic-debugging and verifying-before-completion
3. Verify reference links resolve: manually check `[5 Whys Template](references/five-whys-template.md)` path is correct

**Acceptance:**
- Frontmatter has required `name:` field (validate.sh line 48-51)
- Description uses third-person format ("This skill should be used when...")
- Body <500 lines, <5000 tokens (per component authoring guide)
- References link correctly to files in references/
- Trigger phrases explicitly differentiated from systematic-debugging

---

### Task 3: Create Agent

**File:** `plugins/iflow-dev/agents/rca-investigator.md`

**Dependencies:** Task 2 (agent references skill content)

**Actions:**
1. Create agent file with frontmatter (required fields per validate.sh):
   ```yaml
   ---
   name: rca-investigator
   description: |
     Proactive root cause analysis agent that finds ALL contributing causes.
     Use this agent when: (1) user runs /root-cause-analysis command,
     (2) user says 'run RCA' or 'thorough investigation',
     (3) user says 'find ALL root causes' (emphasis on ALL),
     (4) user mentions failed multiple fix attempts (3-fix rule).

     <example>
     Context: User has a failing test
     user: "/root-cause-analysis test_auth is failing with 'token expired'"
     assistant: "I'll investigate all potential root causes for this test failure."
     <commentary>User explicitly invokes RCA command with test failure.</commentary>
     </example>

     <example>
     Context: User wants thorough investigation
     user: "The API returns 500 sometimes but not always, I need a thorough RCA"
     assistant: "I'll use the rca-investigator to systematically find all contributing factors."
     <commentary>User explicitly requests thorough RCA for intermittent issue.</commentary>
     </example>

     <example>
     Context: User frustrated with repeated failures
     user: "This test keeps failing, I've tried fixing it 3 times already"
     assistant: "Multiple fix attempts indicate this needs systematic RCA. Let me investigate."
     <commentary>3-fix rule triggers thorough investigation.</commentary>
     </example>
   tools: [Read, Glob, Grep, Bash, Write, Edit, WebSearch]
   color: cyan
   ---
   ```
2. Add body content with 6-phase process, behavioral rules, edge cases
3. Verify `name:` field exists at start of frontmatter (validate.sh requirement)

**Acceptance:**
- Frontmatter has required `name:` field (validate.sh line 52-55)
- Description includes 3 example blocks with commentary
- Body covers 6 phases, behavioral rules, edge cases
- Tools list: [Read, Glob, Grep, Bash, Write, Edit, WebSearch]

---

### Task 4: Create Command

**File:** `plugins/iflow-dev/commands/root-cause-analysis.md`

**Dependencies:** Task 2, Task 3 (command loads skill and dispatches to agent)

**Actions:**
1. Create command with frontmatter:
   ```yaml
   ---
   description: Investigate bugs and failures to find all root causes
   argument-hint: <bug description or test failure>
   ---
   ```
2. Add body that:
   - Accepts $ARGUMENTS as bug/test description
   - Prompts via AskUserQuestion if $ARGUMENTS is empty
   - Invokes root-cause-analysis skill via `@plugins/iflow-dev/skills/root-cause-analysis/SKILL.md`
   - Dispatches to rca-investigator agent via Task tool
   - On completion, offers AskUserQuestion handoff:
     ```
     questions: [{
       "question": "RCA complete. What would you like to do?",
       "header": "Next Step",
       "options": [
         {"label": "Create feature for fix", "description": "Start /create-feature with RCA findings"},
         {"label": "Save and exit", "description": "Keep report, end session"}
       ]
     }]
     ```
   - If "Create feature for fix": Invoke `/create-feature "Fix: {rca-title}"` then display "RCA report available at: {path}"

**Handoff Interface (verified compatible):**
- /create-feature accepts a description string as argument (no special --rca flag needed)
- Agent/user manually references RCA report during brainstorm/specify phases
- No modifications to create-feature.md required (info-only handoff per TD-3)

**Acceptance:**
- Frontmatter has description and argument-hint
- Body dispatches to agent
- Handoff uses AskUserQuestion with create-feature option
- Handoff passes description string only (not file path parameter)

---

### Task 5: Static Validation

**Command:** `./validate.sh`

**Dependencies:** Tasks 1-4

**Actions:**
1. Run validation script: `./validate.sh`
2. Verify output includes new components:
   - Agent: rca-investigator
   - Skill: root-cause-analysis
   - Command: root-cause-analysis
3. Fix any validation errors

**Acceptance:**
- ./validate.sh exits with code 0
- Agent frontmatter validates (name, description, tools, color)
- Skill frontmatter validates (description format)
- Command frontmatter validates (description, argument-hint)

---

### Task 6: Integration Test

**Purpose:** Verify command → agent → skill dispatch chain works.

**Dependencies:** Task 5 (syntax must be valid first)

**Test Method:** Manual verification by implementer in Claude Code session.

**Actions:**
1. Start new Claude Code session in this repository
2. Run `/root-cause-analysis "test failure - mock issue for integration test"`
3. Verify:
   - Command loads without error (no parsing errors in output)
   - Skill content is injected (look for RCA process phases in context)
   - Agent is dispatched via Task tool (check tool invocation)
   - Agent receives the bug description
4. Abort the RCA early (Ctrl+C) after verifying dispatch works - no need to complete full RCA
5. Verify skill reference links by reading SKILL.md and confirming paths exist:
   ```bash
   ls plugins/iflow-dev/skills/root-cause-analysis/references/
   ```

**Acceptance:**
- Command executes without syntax/parsing errors
- Agent dispatches successfully (Task tool invoked)
- Reference files exist at expected paths

**Note:** Full end-to-end RCA workflow testing is out of scope. This test verifies component wiring only.

---

## Dependency Graph

```
Task 1 (References)
    ↓
Task 2 (SKILL.md)
    ↓
Task 3 (Agent) ←─┐
    ↓            │
Task 4 (Command) ┘
    ↓
Task 5 (Static Validation)
    ↓
Task 6 (Integration Test)
```

## Mapping to Acceptance Criteria

| AC | Task | Coverage |
|----|------|----------|
| AC-1: Agent Creation | Task 3 | Frontmatter with name field, examples, tools, color |
| AC-2: Skill Creation | Tasks 1, 2 | SKILL.md, references directory |
| AC-3: Command Creation | Task 4 | Frontmatter, dispatch, handoff |
| AC-4: Sandbox Isolation | Task 3 | Agent behavioral rules |
| AC-5: Multiple Hypotheses | Tasks 2, 3 | Skill + Agent both enforce |
| AC-6: Report Generation | Tasks 1, 2 | Template in references, process in skill |
| AC-7: Workflow Handoff | Task 4, 6 | AskUserQuestion in command, integration test verifies |
| AC-8: Validation | Task 5 | ./validate.sh passes |

## Risk Mitigations in Plan

| Risk | Task | Mitigation |
|------|------|------------|
| R-1: Production code modification | Task 3 | Agent instructions explicit about sandbox-only writes |
| R-3: Fewer than 3 hypotheses | Tasks 2, 3 | Document considered-discarded alternatives |
| R-4: Trigger collision | Task 2 | Skill description differentiates from systematic-debugging |
| Partial file creation | Task 1 | Atomic approach with rollback strategy |
| Integration failures | Task 6 | Dedicated integration test after static validation |

## Notes

- No modifications needed to existing files (create-feature.md unchanged per TD-3)
- Directory creation (agent_sandbox/, docs/rca/) handled by agent at runtime via mkdir -p
- All content from design.md is implementation-ready with full templates
- Content source: design.md in this feature folder contains complete content for all files
- Token budget: SKILL.md must be <500 lines, <5000 tokens per component authoring guide
