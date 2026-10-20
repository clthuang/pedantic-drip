# Design: Root Cause Analysis Agent & Command

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    User Entry Points                             │
├─────────────────────────────────────────────────────────────────┤
│  /root-cause-analysis [bug description]                         │
│  Direct: "run RCA", "thorough investigation", "find ALL causes" │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               Command: root-cause-analysis.md                    │
│  - Accept $ARGUMENTS                                            │
│  - Load root-cause-analysis skill                               │
│  - Dispatch to rca-investigator agent                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Agent: rca-investigator                          │
│  Tools: [Read, Glob, Grep, Bash, Write, Edit, WebSearch]        │
│  Color: cyan                                                     │
├─────────────────────────────────────────────────────────────────┤
│  6-Phase Process:                                               │
│  1. CLARIFY → 2. REPRODUCE → 3. INVESTIGATE →                   │
│  4. EXPERIMENT → 5. ANALYZE → 6. REPORT                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               Skill: root-cause-analysis                         │
│  - RCA methodology (5 Whys, Fishbone, Fault Tree)               │
│  - Phase definitions and outputs                                 │
│  - Report template                                               │
│  - References: templates, categories                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Outputs                                     │
├─────────────────────────────────────────────────────────────────┤
│  docs/rca/{timestamp}-{slug}.md     ← RCA Report                │
│  agent_sandbox/{date}/rca-{slug}/   ← Experiment artifacts      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Optional Handoff                                │
│  AskUserQuestion → /create-feature --rca={report-path}          │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Command: root-cause-analysis.md

**Location:** `plugins/iflow-dev/commands/root-cause-analysis.md`

**Responsibilities:**
- Entry point for RCA workflow
- Accept bug description via $ARGUMENTS
- Prompt for description if not provided
- Load skill and dispatch to agent

**Design Decision:** Command is thin wrapper, logic lives in skill.
- Rationale: Follows brainstorm.md pattern - command invokes skill which does the work.

### 2. Agent: rca-investigator.md

**Location:** `plugins/iflow-dev/agents/rca-investigator.md`

**Responsibilities:**
- Execute 6-phase RCA process
- Manage sandbox experiments
- Generate RCA report
- Offer handoff to /create-feature

**Tool Selection:**
| Tool | Purpose |
|------|---------|
| Read | Read source files for analysis |
| Glob | Find files matching patterns |
| Grep | Search for code patterns |
| Bash | Run experiments, copy to sandbox |
| Write | Create RCA report, experiment scripts |
| Edit | Update experiment scripts |
| WebSearch | Research error messages, known issues |

**Design Decision:** Include Write/Edit/Bash for sandbox work.
- Rationale: Unlike investigation-agent (read-only), RCA needs to create reproduction scripts and experiment artifacts.
- Constraint: MUST only write to agent_sandbox/ and docs/rca/

### 3. Skill: root-cause-analysis/SKILL.md

**Location:** `plugins/iflow-dev/skills/root-cause-analysis/`

**Directory Structure:**
```
root-cause-analysis/
├── SKILL.md                           # Main skill (process, phases)
└── references/
    ├── five-whys-template.md          # 5 Whys worksheet
    ├── fishbone-categories.md         # Software Ishikawa categories
    └── rca-report-template.md         # Full report structure
```

**Responsibilities:**
- Define 6-phase process with clear outputs
- Provide RCA methodology guidance
- Include reference materials for each technique

**Design Decision:** Separate from systematic-debugging skill.
- Rationale: systematic-debugging is general guidance; root-cause-analysis is structured process with report output.
- Relationship: RCA skill references systematic-debugging's Iron Law and 3-fix rule.

**SKILL.md Body Structure (~1500 words):**
```markdown
# Root Cause Analysis

## Process Overview
[Mermaid diagram showing 6-phase flow]

## Phase 1: CLARIFY
- Actions: Ask targeted questions about symptom, timeline, changes
- Output: Clear problem statement
- Tools: AskUserQuestion

## Phase 2: REPRODUCE
- Actions: Copy code to sandbox, create minimal reproduction
- Output: Reproduction script or "intermittent" note
- Tools: Bash (mkdir, cp), Write

## Phase 3: INVESTIGATE
- Actions: Apply 5 Whys, trace backward, search codebase
- Output: Hypothesis list (minimum 3)
- Tools: Read, Glob, Grep
- Reference: [5 Whys Template](references/five-whys-template.md)

## Phase 4: EXPERIMENT
- Actions: Write verification scripts, test each hypothesis
- Output: Evidence for/against each hypothesis
- Tools: Write, Bash, Edit

## Phase 5: ANALYZE
- Actions: Identify all causes, check interactions
- Output: Root cause list with evidence
- Reference: [Fishbone Categories](references/fishbone-categories.md)

## Phase 6: REPORT
- Actions: Generate RCA report, offer handoff
- Output: docs/rca/{timestamp}-{slug}.md
- Reference: [RCA Report Template](references/rca-report-template.md)

## Behavioral Rules
- MUST reproduce before analyzing
- MUST explore 3+ hypotheses
- MUST NOT modify production code
- MUST NOT propose fixes

## Related Resources
- [systematic-debugging](../systematic-debugging/SKILL.md) - Iron Law, 3-fix rule
- [verifying-before-completion](../verifying-before-completion/SKILL.md) - Evidence requirements
```

**Reference File Contents:**

**references/five-whys-template.md:**
```markdown
# 5 Whys Template

## Problem Statement
{one sentence description of the symptom}

## Why Analysis
| # | Question | Answer | Evidence |
|---|----------|--------|----------|
| 1 | Why did {symptom} happen? | {answer} | {source} |
| 2 | Why did {answer-1} happen? | {answer} | {source} |
| 3 | Why did {answer-2} happen? | {answer} | {source} |
| 4 | Why did {answer-3} happen? | {answer} | {source} |
| 5 | Why did {answer-4} happen? | {answer} | {source} |

## Root Cause
{The deepest answer with actionable insight}

## When to Stop
- Answer is outside your control (external system)
- Answer is a process/policy issue
- Answer is actionable
```

**references/fishbone-categories.md:**
```markdown
# Fishbone (Ishikawa) Categories for Software

## Software-Specific Categories

| Category | What to Check | Examples |
|----------|---------------|----------|
| **Code** | Logic errors, race conditions, edge cases | Off-by-one, null handling, async bugs |
| **Config** | Settings, environment variables, feature flags | Wrong env, missing config, typos |
| **Data** | Input validation, data corruption, schema | Bad input, migration issues, encoding |
| **Environment** | OS, runtime, network, resources | Memory, disk, network timeouts |
| **Dependencies** | Libraries, APIs, services | Version mismatch, API changes, outages |
| **Integration** | Component boundaries, protocols | Contract violations, timing issues |

## Mermaid Diagram Template
\`\`\`mermaid
graph LR
    subgraph Code
        C1[Logic error]
        C2[Race condition]
    end
    subgraph Config
        CF1[Wrong setting]
    end
    subgraph Data
        D1[Bad input]
    end
    Code --> Problem
    Config --> Problem
    Data --> Problem
\`\`\`
```

**references/rca-report-template.md:**
```markdown
# RCA Report: {Title}

## Summary
- **Issue:** {one-line description}
- **Reported:** {date}
- **Investigated:** {date}
- **Status:** {Resolved | Needs Fix | Monitoring}

## Timeline
| Time | Event |
|------|-------|
| {time} | {what happened} |

## Reproduction

### Environment
- {relevant environment details}

### Steps to Reproduce
1. {step}

### Reproduction Result
{Reproduced successfully | Could not reproduce - marked intermittent}

## Investigation

### Hypotheses Explored
| # | Hypothesis | Evidence For | Evidence Against | Verdict |
|---|------------|--------------|------------------|---------|
| 1 | {hypothesis} | {evidence} | {evidence} | {Confirmed/Rejected/Partial} |
| 2 | {hypothesis} | {evidence} | {evidence} | {Confirmed/Rejected/Partial} |
| 3 | {hypothesis} | {evidence} | {evidence} | {Confirmed/Rejected/Partial} |

### Experiments Conducted
#### Experiment 1: {name}
- **Script:** \`agent_sandbox/{path}\`
- **Purpose:** {what we tested}
- **Result:** {outcome}

## Root Causes

### Primary Cause
{description with evidence}

### Contributing Factors
1. {factor} — Evidence: {source}
2. {factor} — Evidence: {source}

### Interaction Effects
{how causes interact, if applicable}

## Fishbone Analysis
{mermaid diagram if multiple cause categories - see fishbone-categories.md}

## Recommendations
1. {recommendation}
2. {recommendation}

## Next Steps
- [ ] {action item}

---
*Generated by rca-investigator agent*
```

## Technical Decisions

### TD-1: Sandbox Directory Structure

**Decision:** Use `agent_sandbox/{YYYYMMDD}/rca-{slug}/` for experiments.

**Directory Creation:** Agent creates directories on first use via Bash:
```bash
mkdir -p agent_sandbox/$(date +%Y%m%d)/rca-{slug}/{reproduction,experiments,logs}
```

**Structure:**
```
agent_sandbox/
└── 20260205/
    └── rca-auth-token-expired/
        ├── reproduction/           # Minimal reproduction code
        │   └── test_repro.py
        ├── experiments/            # Hypothesis verification
        │   ├── exp1_check_expiry.py
        │   └── exp2_check_refresh.py
        └── logs/                   # Captured output
            └── experiment_log.txt
```

**Rationale:**
- Date-based grouping provides visual organization (cleanup-sandbox.sh uses mtime, not directory name, but date naming aids human navigation)
- RCA-specific subdirectory prevents collision with other agent work
- Separation of reproduction/experiments/logs aids clarity
- mkdir -p is idempotent - safe to run even if directories already exist

### TD-2: Report Storage

**Decision:** Store reports in `docs/dev_artifacts/rca/` with timestamp-slug naming.

**Directory Creation:** Agent creates docs/rca/ on first use via Bash:
```bash
mkdir -p docs/rca  # Idempotent - safe if already exists
```

**Timestamp Generation:** Use `date -u` for UTC consistency:
```bash
TIMESTAMP=$(date -u +%Y%m%d-%H%M%S)
REPORT_PATH="docs/rca/${TIMESTAMP}-${SLUG}.md"
```

**Format:** `docs/dev_artifacts/rca/{YYYYMMDD}-{HHMMSS}-{slug}.md` (UTC timestamps for consistency)

**Rationale:**
- Timestamp ensures uniqueness (UTC for cross-timezone consistency)
- Slug provides human-readable identification
- Separate from feature docs (RCA may not lead to feature)
- Persistent (not cleaned up like sandbox)
- mkdir -p ensures directory exists before Write tool call

### TD-3: Handoff Mechanism

**Decision:** Simple handoff - pass RCA path as informational context only.

**Flow:**
1. RCA completes → AskUserQuestion with options
2. User selects "Create feature for fix"
3. Invoke: `/create-feature "Fix: {rca-title}"`
4. Display: "RCA report available at: docs/rca/{report}.md - reference for Problem Statement"

**Rationale:** No modification to create-feature.md needed for MVP.
- User/agent can manually reference RCA report during brainstorm/specify phases
- Avoids cross-component coupling
- Future enhancement: Add --rca flag to auto-populate PRD (out of scope this release)

**Alternative (Future):** If full integration desired later:
```yaml
# create-feature.md would add:
# If --rca provided: Read RCA, extract Root Causes for Problem Statement
```

### TD-4: Hypothesis Minimum Enforcement

**Decision:** Agent MUST document 3+ hypotheses, using "considered but discarded" if fewer apply.

**Implementation:**
- SKILL.md specifies: "Minimum 3 hypotheses required"
- Report template has 3 rows minimum
- Agent instructions: "If fewer than 3 likely causes, document alternative hypotheses you considered and why you rejected them before investigation"

**Rationale:** Addresses reviewer concern about cases where fewer than 3 causes genuinely apply.

### TD-5: Integration with Existing Skills

**Decision:** Reference, don't duplicate, existing content.

| Existing Resource | Usage in RCA |
|-------------------|--------------|
| systematic-debugging/SKILL.md | Reference Iron Law, 3-fix rule |
| systematic-debugging/references/root-cause-tracing.md | Reference for tracing methodology |
| verifying-before-completion/SKILL.md | Apply to RCA findings |
| investigation-agent.md | Inform output format (but RCA has different structure) |

## Interfaces

### Command Interface

```yaml
# plugins/iflow-dev/commands/root-cause-analysis.md
---
description: Investigate bugs and failures to find all root causes
argument-hint: <bug description or test failure>
---
```

**Input:** `$ARGUMENTS` - Bug description or test failure message
**Output:** RCA report path, optional handoff to /create-feature

### Agent Interface

```yaml
# plugins/iflow-dev/agents/rca-investigator.md
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

# RCA Investigator Agent

You are a proactive root cause analysis agent. Your job is to find ALL contributing causes, not just the first one.

## Your Process

Follow these 6 phases in order:

### Phase 1: CLARIFY
Ask targeted questions about the symptom, timeline, and recent changes.
Output: Clear problem statement.

### Phase 2: REPRODUCE
Copy relevant code to agent_sandbox/ and create a minimal reproduction.
Output: Reproduction script or "intermittent" note if cannot reproduce after 3 attempts.

### Phase 3: INVESTIGATE
Apply 5 Whys methodology. Trace causality backward. Search codebase for related patterns.
Output: Hypothesis list (MINIMUM 3 - if fewer likely causes, document alternatives you considered).

### Phase 4: EXPERIMENT
Write verification scripts in sandbox. Test each hypothesis.
Output: Evidence for/against each hypothesis.

### Phase 5: ANALYZE
Identify all contributing causes. Check for interaction effects between causes.
Output: Root cause list with evidence.

### Phase 6: REPORT
Generate RCA report at docs/rca/{timestamp}-{slug}.md. Offer handoff to /create-feature.

## Behavioral Rules

- MUST reproduce before analyzing (or document failed attempts)
- MUST explore at least 3 hypothesis paths
- MUST NOT modify production code (agent_sandbox/ and docs/rca/ only)
- MUST NOT propose fixes (report causes only, fixing is separate)
- MUST write verification scripts for findings
- MUST respect CLAUDE.md writing guidelines

## Edge Cases

- Cannot reproduce: Document attempts, mark as "intermittent", proceed with code analysis
- External dependency: Document boundary, provide evidence, recommend escalation
- Fewer than 3 causes: Document alternative hypotheses you considered and why rejected
```

**Input:** Bug description from command or direct invocation
**Output:** RCA report at docs/rca/{timestamp}-{slug}.md

### Skill Interface

```yaml
# plugins/iflow-dev/skills/root-cause-analysis/SKILL.md
---
description: |
  This skill should be used when the user says 'run RCA', 'thorough investigation',
  'find ALL root causes', 'comprehensive debugging', or runs /root-cause-analysis command.
  For quick debugging guidance, use systematic-debugging skill instead.
  This skill produces a formal RCA report with reproduction, experiments, and evidence.
---
```

**Trigger Differentiation from systematic-debugging:**
| Trigger | Skill | Rationale |
|---------|-------|-----------|
| "debug this", "find root cause" | systematic-debugging | Quick guidance, no report |
| "run RCA", "thorough investigation" | root-cause-analysis | Formal process, report output |
| /root-cause-analysis command | root-cause-analysis | Explicit invocation |

**Provides:**
- 6-phase process definition
- RCA methodology guidance
- Report template
- Reference materials

### Handoff Interface

**AskUserQuestion after RCA completion:**
```
questions: [{
  "question": "RCA complete. What would you like to do?",
  "header": "Next Step",
  "options": [
    {"label": "Create feature for fix", "description": "Start /create-feature with RCA findings"},
    {"label": "Save and exit", "description": "Keep report, end session"}
  ],
  "multiSelect": false
}]
```

**If "Create feature for fix":**
- Extract title from RCA report
- Invoke: `/create-feature "Fix: {rca-title}"`
- Display: "RCA report available at: {report-path} - reference for Problem Statement"

## File Outputs

### RCA Report (docs/rca/{timestamp}-{slug}.md)

See spec.md for full template. Key sections:
- Summary (issue, dates, status)
- Timeline (events leading to bug)
- Reproduction (environment, steps, result)
- Investigation (hypotheses table, experiments)
- Root Causes (primary, contributing, interactions)
- Fishbone Analysis (mermaid diagram if applicable)
- Recommendations
- Next Steps

### Sandbox Artifacts (agent_sandbox/{date}/rca-{slug}/)

- `reproduction/` - Minimal code to reproduce
- `experiments/` - Hypothesis verification scripts
- `logs/` - Captured output from experiments

## Risks and Mitigations

### R-1: Agent Modifies Production Code
**Risk:** Despite constraints, agent writes to wrong location.
**Mitigation:**
- Explicit instructions in agent: "ONLY write to agent_sandbox/ and docs/rca/"
- CLAUDE.md writing guidelines reinforced in agent
- No hooks needed (agent instructions are sufficient)

### R-2: Reproduction Takes Too Long
**Risk:** Complex bugs may require extensive reproduction effort.
**Mitigation:**
- Phase 2 has explicit timeout guidance: "If cannot reproduce after 3 attempts, mark as intermittent and proceed with code analysis"
- Agent can ask user for help with reproduction

### R-3: Fewer Than 3 Hypotheses
**Risk:** Simple bugs may not have 3 real hypotheses.
**Mitigation:**
- TD-4 addresses this: document considered-and-discarded hypotheses
- Report template allows "Rejected before investigation" verdict

### R-4: Trigger Phrase Collision
**Risk:** User says "find root cause" - which skill triggers?
**Mitigation:**
- Differentiated triggers: systematic-debugging for quick guidance, root-cause-analysis for formal RCA
- RCA skill explicitly says "For quick debugging, use systematic-debugging instead"
- Command invocation (/root-cause-analysis) always triggers RCA workflow

## Dependencies

| Dependency | Type | Status |
|------------|------|--------|
| agent_sandbox/ directory | Existing | Parent exists; agent creates dated subdirs via mkdir -p |
| cleanup-sandbox.sh hook | Existing | Available |
| systematic-debugging skill | Existing | Reference only |
| verifying-before-completion skill | Existing | Apply to findings |
| create-feature command | Existing | No changes needed (info handoff only) |
| docs/rca/ directory | New | Created by agent via mkdir -p |
