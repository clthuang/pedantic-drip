# Specification: Root Cause Analysis Agent & Command

## Overview

Create an RCA investigation system with three components:
1. **Agent:** `rca-investigator` - Proactive debugger that finds ALL root causes
2. **Skill:** `root-cause-analysis` - RCA methodology and report format
3. **Command:** `root-cause-analysis` - Entry point for RCA workflow

## Components

### 1. Agent: rca-investigator

**File:** `plugins/iflow-dev/agents/rca-investigator.md`

**Frontmatter:**
```yaml
name: rca-investigator
description: |
  Proactive root cause analysis agent that finds ALL contributing causes, not just the first one.
  Use this agent when: (1) user runs /root-cause-analysis command, (2) user says 'run RCA' or 'thorough investigation',
  (3) user says 'find ALL root causes' (emphasis on ALL), (4) user mentions failed multiple fix attempts (3-fix rule).

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
tools: [Read, Glob, Grep, Bash, Write, Edit, WebSearch]
color: cyan
```

**System Prompt Requirements:**
- Second person ("You investigate...")
- Clear 6-phase process (see Process section below)
- Output format specification (RCA report structure)
- Behavioral constraints (sandbox only, no fixes without RCA, explore 3+ hypotheses)
- Edge case handling (cannot reproduce, external dependencies)

**Process (6 Phases):**

| Phase | Name | Actions | Output |
|-------|------|---------|--------|
| 1 | CLARIFY | Ask targeted questions about symptom, timeline, changes | Clear problem statement |
| 2 | REPRODUCE | Copy relevant code to agent_sandbox/, create minimal reproduction | Reproduction script or "intermittent" note |
| 3 | INVESTIGATE | Apply 5 Whys, trace causality backward, search codebase | Hypothesis list (minimum 3) |
| 4 | EXPERIMENT | Write verification scripts, test hypotheses in sandbox | Evidence for/against each hypothesis |
| 5 | ANALYZE | Identify all contributing causes, check for interactions | Root cause list with evidence |
| 6 | REPORT | Generate structured RCA report, offer handoff | docs/rca/{timestamp}-{slug}.md |

**Behavioral Constraints:**
- MUST reproduce before analyzing (or document failed attempts)
- MUST explore at least 3 hypothesis paths
- MUST NOT modify production code (sandbox only)
- MUST NOT propose fixes (report causes only)
- MUST write verification scripts for findings
- MUST respect CLAUDE.md writing guidelines

### 2. Skill: root-cause-analysis

**File:** `plugins/iflow-dev/skills/root-cause-analysis/SKILL.md`

**Frontmatter:**
```yaml
description: |
  This skill should be used when the user says 'run RCA', 'thorough investigation',
  'find ALL root causes', 'comprehensive debugging', or runs /root-cause-analysis command.
  For quick debugging guidance, use systematic-debugging skill instead.
  This skill produces a formal RCA report with reproduction, experiments, and evidence.
```

**Content Structure:**
1. **Process Overview** - 6-phase methodology diagram
2. **Phase Details** - Each phase with actions, tools, outputs
3. **RCA Methodologies**
   - 5 Whys: When to use, template
   - Fishbone (Ishikawa): Categories for software (Code, Config, Data, Environment, Dependencies, Integration)
   - Fault Tree: For multi-factor failures
4. **Report Format** - Standard structure (see below)
5. **Sandbox Usage** - How to set up isolated experiments
6. **Handoff** - How to transition to /create-feature

**References Directory:**
- `references/five-whys-template.md` - 5 Whys worksheet
- `references/fishbone-categories.md` - Software-specific Ishikawa categories
- `references/rca-report-template.md` - Full report template

### 3. Command: root-cause-analysis

**File:** `plugins/iflow-dev/commands/root-cause-analysis.md`

**Frontmatter:**
```yaml
description: Investigate bugs and failures to find all root causes
argument-hint: <bug description or test failure>
```

**Body:**
1. Accept $ARGUMENTS as bug/test description (or prompt if empty)
2. Invoke root-cause-analysis skill
3. Dispatch to rca-investigator agent
4. On completion, offer handoff options via AskUserQuestion

## RCA Report Format

**File location:** `docs/dev_artifacts/rca/{YYYYMMDD}-{HHMMSS}-{slug}.md`

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
- **Script:** `agent_sandbox/{path}`
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
{mermaid diagram if multiple cause categories}

## Recommendations
1. {recommendation}
2. {recommendation}

## Next Steps
- [ ] {action item}

---
*Generated by rca-investigator agent*
```

## Acceptance Criteria

### AC-1: Agent Creation
- [ ] `rca-investigator.md` exists in `plugins/iflow-dev/agents/`
- [ ] Frontmatter has name, description with examples, tools, color
- [ ] Description includes 2+ example blocks with commentary
- [ ] Tools list is [Read, Glob, Grep, Bash, Write, Edit, WebSearch]
- [ ] Color is cyan

### AC-2: Skill Creation
- [ ] `root-cause-analysis/SKILL.md` exists in `plugins/iflow-dev/skills/`
- [ ] Description uses third-person "This skill should be used when..."
- [ ] Body is <5000 words with imperative verb form
- [ ] References directory contains templates
- [ ] Process defines 6 phases with clear outputs

### AC-3: Command Creation
- [ ] `root-cause-analysis.md` exists in `plugins/iflow-dev/commands/`
- [ ] Frontmatter has description and argument-hint
- [ ] Body dispatches to rca-investigator agent
- [ ] Offers handoff to /create-feature on completion

### AC-4: Sandbox Isolation
- [ ] All experiments happen in `agent_sandbox/` directory
- [ ] Agent copies code to sandbox before modification
- [ ] Production code is never modified directly

### AC-5: Multiple Hypothesis Exploration
- [ ] Agent documents at least 3 hypotheses in every RCA
- [ ] Each hypothesis has evidence for/against columns
- [ ] Verdict is recorded for each hypothesis

### AC-6: Report Generation
- [ ] Reports saved to `docs/dev_artifacts/rca/{timestamp}-{slug}.md`
- [ ] Report follows standard template structure
- [ ] Report includes Timeline, Hypotheses, Experiments, Root Causes sections

### AC-7: Workflow Handoff
- [ ] After RCA completes, agent offers AskUserQuestion with options
- [ ] "Create feature for fix" passes RCA path to /create-feature
- [ ] "Save and exit" saves report without further action

### AC-8: Validation
- [ ] `./validate.sh` passes with new components
- [ ] Agent frontmatter validates (name, description, tools, color)
- [ ] Skill frontmatter validates (description format)
- [ ] Command frontmatter validates (description, argument-hint)

## Test Scenarios

### Scenario 1: Simple Test Failure
**Input:** `/root-cause-analysis "test_login fails with AssertionError"`
**Expected:**
1. Agent asks clarifying questions
2. Agent reproduces in sandbox
3. Agent explores 3+ hypotheses
4. Agent generates RCA report
5. Agent offers handoff

### Scenario 2: Intermittent Bug
**Input:** `/root-cause-analysis "API returns 500 randomly"`
**Expected:**
1. Agent attempts reproduction multiple times
2. Agent marks as "intermittent" if cannot reproduce
3. Agent still explores hypotheses via code analysis
4. Report notes reproduction status

### Scenario 3: Handoff to Feature
**Input:** User selects "Create feature for fix" after RCA
**Expected:**
1. `/create-feature` is invoked with RCA path
2. Feature PRD references RCA findings
3. RCA report is preserved

## Dependencies

- Existing: `agent_sandbox/` directory pattern
- Existing: `systematic-debugging` skill (reference, not replace)
- Existing: `cleanup-sandbox.sh` hook for 7-day cleanup
- Existing: `verifying-before-completion` skill for evidence requirements

## Out of Scope

- Git bisection automation
- External logging integration
- Performance profiling
- Automatic fix generation
