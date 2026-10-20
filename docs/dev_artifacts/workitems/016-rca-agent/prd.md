# PRD: Root Cause Analysis Agent & Command

## Status
- Created: 2026-02-05
- Last updated: 2026-02-05
- Status: Reviewed

## Problem Statement

When debugging complex issues, developers and AI agents often stop at the first apparent cause rather than investigating all contributing factors. This leads to:
- Incomplete fixes that address symptoms but not root causes
- Recurring issues due to unaddressed interaction effects
- Missed edge cases that resurface later
- Wasted time on multiple fix attempts (the "3-fix rule" indicator)

Current LLM-based debugging approaches have low success rates—even Claude 3.5 (best performer) solved only 11.34% of failure cases in the OpenRCA benchmark.

### Evidence
- OpenRCA benchmark shows LLMs struggle with RCA — Source: https://openreview.net/forum?id=M4qNIzQYpd
- "Root cause analysis should address 'causes' (plural) because there is never just one reason why systems fail" — Source: https://www.opsatscale.com/articles/Root-cause-analysis-and-postmortem/
- Existing systematic-debugging skill establishes "3-fix rule" for detecting architectural problems — Source: plugins/iflow-dev/skills/systematic-debugging/SKILL.md

## Goals

1. Create a proactive RCA agent that finds ALL root causes, not just the first one
2. Challenge assumptions and conduct experiments before proposing solutions
3. Reproduce problems in isolated sandbox environments
4. Produce well-documented RCA reports with verified findings
5. Integrate with iflow workflow via optional handoff to create-feature

## Success Criteria

- [ ] Agent reproduces reported issues in agent_sandbox/ before analysis
- [ ] Agent explicitly explores multiple hypothesis paths, documenting at least 3 alternative causes considered (even if ultimately discarded)
- [ ] Agent writes verification scripts to confirm findings
- [ ] RCA report includes timeline, evidence, experiments conducted, and root causes
- [ ] Command provides entry point at same level as /brainstorm
- [ ] Optional handoff to /create-feature when fix is needed

## User Stories

### Story 1: Debug a Failing Test
**As a** developer
**I want** to run `/root-cause-analysis` with a failing test
**So that** I understand ALL reasons why it fails, not just the obvious one

**Acceptance criteria:**
- Agent accepts test failure output as input
- Agent reproduces failure in sandbox
- Agent traces back through multiple potential causes
- Report lists all contributing factors with evidence

### Story 2: Investigate Production Bug
**As a** developer
**I want** to describe a bug symptom and have it thoroughly investigated
**So that** I get a comprehensive RCA report before attempting fixes

**Acceptance criteria:**
- Agent accepts bug description as input
- Agent challenges my assumptions about the cause
- Agent runs experiments to verify hypotheses
- Agent identifies interaction effects and edge cases

### Story 3: Transition to Fix Implementation
**As a** developer
**I want** to create a feature branch after RCA completes
**So that** I can implement a fix using the full iflow workflow

**Acceptance criteria:**
- After RCA completes, agent offers handoff to /create-feature
- RCA findings are preserved and linked to feature
- User can decline handoff and save RCA report only

## Use Cases

### UC-1: Test Failure Investigation
**Actors:** Developer, RCA Agent
**Preconditions:** Test is failing with error output
**Flow:**
1. User runs `/root-cause-analysis "test X is failing with error Y"`
2. Agent clarifies: what changed recently? when did it start?
3. Agent recreates minimal test case in agent_sandbox/
4. Agent runs experiments: bisect commits, isolate dependencies, vary inputs
5. Agent traces causality backward using 5 Whys + Fishbone approach
6. Agent identifies 1-N root causes with evidence
7. Agent generates RCA report
8. Agent offers handoff to /create-feature
**Postconditions:** RCA report saved, optional feature created
**Edge cases:**
- Cannot reproduce: Document reproduction attempts, note as "intermittent"
- Multiple unrelated causes: List each with separate evidence chains

### UC-2: Bug Description Investigation
**Actors:** Developer, RCA Agent
**Preconditions:** User describes bug symptoms
**Flow:**
1. User runs `/root-cause-analysis "when I do X, Y happens instead of Z"`
2. Agent gathers context: environment, steps to reproduce, expected behavior
3. Agent searches codebase for related code paths
4. Agent creates reproduction script in agent_sandbox/
5. Agent instruments code with logging/tracing (in sandbox copy)
6. Agent identifies failure points and traces causality
7. Agent challenges assumptions: "Could it also be caused by...?"
8. Agent generates RCA report with all findings
**Postconditions:** RCA report saved with verified findings
**Edge cases:**
- User's description is incomplete: Agent asks clarifying questions
- Bug is in external dependency: Document boundary, recommend escalation

## Edge Cases & Error Handling

| Scenario | Expected Behavior | Rationale |
|----------|-------------------|-----------|
| Cannot reproduce bug | Document all reproduction attempts in report, mark as "intermittent", suggest logging/monitoring approach | Intermittent bugs need different strategies — Source: https://medium.com/@case_lab/identifying-and-reproducing-intermittent-bugs-efce4ffb5af3 |
| Multiple independent causes | List each cause separately with own evidence chain | "Never just one reason why systems fail" — Source: https://www.opsatscale.com/articles/Root-cause-analysis-and-postmortem/ |
| Cause is in external code | Document boundary, provide evidence, recommend escalation path | Agent can investigate but cannot fix external dependencies |
| Sandbox experiments fail | Report experiment failures as data points, try alternative approaches | Failed experiments provide valuable negative evidence |
| User wants to skip reproduction | Warn that findings may be less reliable, proceed with code analysis only | Reproduction is preferred but not always possible |

## Constraints

### Behavioral Constraints (Must NOT do)
- MUST NOT modify production code directly — Rationale: All experiments happen in agent_sandbox/ to protect codebase
- MUST NOT propose fixes before completing RCA — Rationale: "Iron Law" from systematic-debugging skill
- MUST NOT stop at first cause found — Rationale: Core value proposition is finding ALL causes
- MUST NOT claim completion without verification — Rationale: verifying-before-completion skill requirements

### Technical Constraints
- Uses agent_sandbox/ for all experimental code — Evidence: Existing pattern from generic-worker, implementer agents
- Respects CLAUDE.md writing guidelines — Evidence: User requirement
- Read-only access to production code (can copy to sandbox) — Evidence: User requirement
- 7-day sandbox cleanup applies — Evidence: cleanup-sandbox.sh hook

## Requirements

### Functional

**Agent: rca-investigator**
- FR-1: Accept bug description OR test failure output as input
- FR-2: Clarify problem through targeted questions (like brainstorming Stage 1)
- FR-3: Reproduce issue in agent_sandbox/ directory
- FR-4: Apply multiple RCA methodologies (5 Whys, Fishbone, Fault Tree)
- FR-5: Write verification scripts to confirm hypotheses
- FR-6: Trace causality backward to find all contributing factors
- FR-7: Challenge assumptions explicitly ("Could it also be...?")
- FR-8: Generate structured RCA report with evidence
- FR-9: Offer optional handoff to /create-feature (pass RCA report path; create-feature reads findings for Problem Statement)

**Skill: root-cause-analysis**
- FR-10: Define RCA process phases and methodology
- FR-11: Include reference materials (5 Whys template, Fishbone categories)
- FR-12: Define RCA report output format
- FR-13: Reference existing systematic-debugging skill where appropriate

**Command: root-cause-analysis**
- FR-14: Entry point at same level as /brainstorm
- FR-15: Accept optional argument for bug/test description
- FR-16: Dispatch to rca-investigator agent
- FR-17: Handle workflow continuation after RCA completes

### Non-Functional
- NFR-1: Agent should use existing tools (Glob, Grep, Read, Bash, Write, Edit, WebSearch, context7)
- NFR-2: Sandbox experiments should be isolated and reproducible
- NFR-3: RCA reports should be saved to docs/rca/ directory
- NFR-4: Agent color should be cyan (investigation category)

### Quality Standards (from claude-plugins-official)

**Agent (rca-investigator.md):**
- Name: kebab-case, 3-50 chars, alphanumeric start/end
- Description: 10-5000 chars with triggering conditions ("Use this agent when...") and 2-4 `<example>` blocks with Context/user/assistant/commentary
- System prompt: 500-3000 chars, second person, clear responsibilities, process steps, output format, edge case handling
- Tools: Follow least privilege — investigation needs [Read, Glob, Grep, Bash, Write, Edit, WebSearch]
- Color: cyan (analysis/investigation category)

**Skill (root-cause-analysis/SKILL.md):**
- Description: Third-person format ("This skill should be used when...")
- Body: <5000 words (target 1500-2000), imperative/infinitive verb form
- Progressive disclosure: Metadata (~100 words) → SKILL.md body → references/ for detailed patterns
- Include trigger phrases in description

**Command (root-cause-analysis.md):**
- Frontmatter: description, argument-hint for documenting args
- Body: Instructions FOR Claude, not messages TO users
- Support $ARGUMENTS for user input
- Use @file references if needed

**General:**
- Use ${CLAUDE_PLUGIN_ROOT} for portable paths in any scripts
- Validate with existing ./validate.sh
- Follow kebab-case naming throughout

## Non-Goals
Strategic decisions about what this feature will NOT aim to achieve.

- Automatic fix implementation — Rationale: RCA agent finds causes, separate implementer fixes them
- Real-time production monitoring — Rationale: Agent works on reported issues, not live systems
- Performance profiling — Rationale: Different tool category, could be separate agent

## Out of Scope (This Release)

- Integration with external logging systems (ELK, Splunk) — Future consideration: Could enhance intermittent bug investigation
- Distributed tracing support — Future consideration: Microservices debugging
- Automated bisection of git history — Future consideration: Could be added to sandbox experiments
- Memory/CPU profiling integration — Future consideration: Performance-specific RCA

## Research Summary

### Internet Research
- RCA should address causes (plural) - systems fail for multiple reasons — Source: https://www.opsatscale.com/articles/Root-cause-analysis-and-postmortem/
- 5 Whys works for simple issues but needs integration with Fishbone for complex ones — Source: https://www.isixsigma.com/cause-effect/root-cause-analysis-ishikawa-diagrams-and-the-5-whys/
- Fault Tree Analysis maps how multiple issues combine into failures — Source: https://www.priz.guru/root-cause-analysis-guide/
- Bugs persist at integration boundaries, concurrency issues need isolation testing — Source: https://sapient.pro/blog/identifying-root-causes-of-persistent-bugs-in-software
- Intermittent bugs need controlled environments, load simulation, binary search — Source: https://medium.com/@case_lab/identifying-and-reproducing-intermittent-bugs-efce4ffb5af3
- Good RCA report: Issue Summary, Timeline, Impact, Root Cause, Remediation — Source: https://www.datadoghq.com/blog/incident-postmortem-process-best-practices/
- LLMs struggle with RCA - Claude 3.5 only 11.34% on OpenRCA benchmark — Source: https://openreview.net/forum?id=M4qNIzQYpd
- ReAct agents with retrieval tools perform best for RCA — Source: https://2024.esec-fse.org/details/fse-2024-industry/20/Exploring-LLM-based-Agents-for-Root-Cause-Analysis
- Meta combines heuristic retrieval with LLM ranking for RCA — Source: https://www.infoq.com/news/2024/08/meta-rca-ai-driven/

### Codebase Analysis
- systematic-debugging skill has four phases: Investigate, Analyze Patterns, Hypothesize/Test, Implement — Location: plugins/iflow-dev/skills/systematic-debugging/SKILL.md
- "Iron Law: NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST" — Location: plugins/iflow-dev/skills/systematic-debugging/SKILL.md
- investigation-agent is READ-ONLY pattern with structured output — Location: plugins/iflow-dev/agents/investigation-agent.md
- root-cause-tracing reference defines backward tracing methodology — Location: plugins/iflow-dev/skills/systematic-debugging/references/root-cause-tracing.md
- agent_sandbox/ pattern established by generic-worker, implementer agents — Location: plugins/iflow-dev/agents/generic-worker.md:34-36
- find-polluter.sh script uses bisection for test pollution — Location: plugins/iflow-dev/skills/systematic-debugging/scripts/find-polluter.sh
- Agent colors: cyan for investigation, magenta for review, green for implementation — Location: plugins/iflow-dev/agents/investigation-agent.md:5

### Official Plugin Quality Standards
- Agent descriptions MUST include triggering conditions and 2-4 example blocks — Source: https://github.com/anthropics/claude-plugins-official/blob/main/plugins/plugin-dev/skills/agent-development/SKILL.md
- Skills use 3-level progressive disclosure: metadata, body, references — Source: https://github.com/anthropics/claude-plugins-official/blob/main/plugins/plugin-dev/skills/skill-development/SKILL.md
- Commands are instructions FOR Claude with YAML frontmatter — Source: https://github.com/anthropics/claude-plugins-official/blob/main/plugins/plugin-dev/skills/command-development/SKILL.md
- Use ${CLAUDE_PLUGIN_ROOT} for portable paths — Source: https://github.com/anthropics/claude-plugins-official/blob/main/plugins/plugin-dev/skills/plugin-structure/SKILL.md

### Existing Capabilities
- systematic-debugging skill — Provides four-phase methodology, Iron Law, 3-fix rule. RCA agent should USE this skill.
- investigation-agent — Read-only research pattern. RCA agent can REFERENCE this output format.
- verifying-before-completion skill — Evidence-based claims. RCA agent should APPLY this for findings.
- root-cause-tracing reference — Backward tracing methodology. RCA agent should INCORPORATE this.
- chain-reviewer agent — Validates completeness. RCA report could be reviewed by similar pattern.

## Design Rationale: Addressing LLM RCA Limitations

The OpenRCA benchmark shows LLMs struggle with root cause analysis (11.34% success). This agent design addresses those limitations through:

1. **Structured methodology over freeform reasoning** — Fishbone, 5 Whys, and Fault Tree provide scaffolding that prevents premature conclusions
2. **Sandbox reproduction** — Forcing reproduction before analysis ensures the agent works with real behavior, not assumptions
3. **ReAct-style tool use** — FSE 2024 research shows retrieval + tool agents outperform pure reasoning; this agent uses Grep, Read, Bash, context7
4. **Verification scripts** — Writing scripts to confirm findings creates falsifiable hypotheses
5. **Multiple cause exploration requirement** — Explicit requirement to explore 3+ hypotheses counters single-cause bias

## Open Questions

- Should the agent create a Fishbone diagram (mermaid) in the report? (Decided: Yes, optional section when multiple cause categories apply)
- Should there be a "quick RCA" mode that skips reproduction? (Decided: No, reproduction is core value; user can skip manually if needed)

## Review History

### Review 1 (2026-02-05)
**Reviewer:** prd-reviewer agent

**Findings:**
- [warning] Open questions remain unresolved (at: Open Questions section)
- [warning] Success criteria lack measurability for 'multiple causes' (at: Success Criteria line 35)
- [warning] NFR-3 conflicts with Open Question 1 (at: NFR-3 vs Open Questions)
- [suggestion] LLM benchmark cited without mitigation strategy (at: Problem Statement)
- [suggestion] Handoff mechanism underspecified (at: FR-9)

**Corrections Applied:**
- Resolved open questions with decisions — Reason: warning about unresolved questions
- Reframed success criterion to "explores 3+ hypothesis paths" — Reason: warning about measurability
- Removed conflicting open question, committed to docs/rca/ — Reason: warning about NFR-3 conflict
- Added "Design Rationale" section explaining how design addresses LLM limitations — Reason: suggestion about benchmark mitigation
- Specified handoff mechanism in FR-9 — Reason: suggestion about underspecification

## Next Steps

Ready for /iflow-dev:create-feature to begin implementation.
