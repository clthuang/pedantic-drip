# Tasks: Enhanced Brainstorm-to-PRD Workflow

## Task List

### Phase 1: Foundation (Agents)

#### Task 1.1: Create Internet Researcher Agent
- **Files:** `plugins/iflow-dev/agents/internet-researcher.md`
- **Do:** Create agent with YAML frontmatter (name, description, tools: WebSearch, WebFetch). Define input/output format per design interface. Include "no findings" handling.
- **Test:** Verify file exists and has valid YAML frontmatter
- **Done when:** Agent file matches interface spec in design.md

#### Task 1.2: Create Codebase Explorer Agent
- **Files:** `plugins/iflow-dev/agents/codebase-explorer.md`
- **Do:** Create agent with YAML frontmatter (name, description, tools: Glob, Grep, Read). Define input/output format per design interface. Include "no findings" handling.
- **Test:** Verify file exists and has valid YAML frontmatter
- **Done when:** Agent file matches interface spec in design.md

#### Task 1.3: Create Skill Searcher Agent
- **Files:** `plugins/iflow-dev/agents/skill-searcher.md`
- **Do:** Create agent with YAML frontmatter (name, description, tools: Glob, Grep, Read). Define input/output format per design interface. Focus search on `plugins/*/skills/*/SKILL.md` paths.
- **Test:** Verify file exists and has valid YAML frontmatter
- **Done when:** Agent file matches interface spec in design.md

#### Task 1.4: Create PRD Reviewer Agent
- **Files:** `plugins/iflow-dev/agents/prd-reviewer.md`
- **Do:** Create agent with YAML frontmatter (name, description, tools: Read). Define quality criteria checklist inline. Define output format with severity levels. Emphasize challenging assumptions and flagging false certainty.
- **Test:** Verify file exists and has valid YAML frontmatter with quality criteria
- **Done when:** Agent file matches interface spec in design.md, includes full quality criteria

### Phase 2: Core Implementation (Skill Modification)

#### Task 2.1: Add PRD Template to Skill
- **Files:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Do:** Add new section "## PRD Output Format" with full template from brainstorm document. Include all 13+ sections: Status, Problem Statement, Goals, Success Criteria, User Stories, Use Cases, Edge Cases, Constraints, Requirements, Non-Goals, Out of Scope, Research Summary, Review History, Open Questions.
- **Test:** Template section exists in skill file
- **Done when:** PRD template matches brainstorm document specification

#### Task 2.2: Modify Stage 1 (Clarify)
- **Depends on:** Task 2.1
- **Files:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Do:** Update "## Process" section. Rename/restructure as "### Stage 1: CLARIFY". Keep existing probing questions. Add note that clarification must complete before research.
- **Test:** Stage 1 section exists with clear boundary
- **Done when:** Clarification stage is clearly delimited with completion marker

#### Task 2.3: Add Stage 2 (Research)
- **Depends on:** Tasks 1.1-1.3, Task 2.2
- **Files:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Do:** Add "### Stage 2: RESEARCH". Include parallel Task tool invocation for all 3 research agents. Show how to invoke them in parallel (multiple Task calls in same response). Define how to collect and merge findings.
- **Test:** Stage 2 section exists with parallel invocation instructions
- **Done when:** Research stage specifies parallel agent invocation with finding collection

#### Task 2.4: Add Stage 3 (Draft PRD)
- **Depends on:** Tasks 2.1, 2.3
- **Files:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Do:** Add "### Stage 3: DRAFT PRD". Instructions to populate PRD template using research findings. Each claim must cite evidence type. Use inline citation format: `{claim} — Evidence: {source}`.
- **Test:** Stage 3 section exists with evidence citation instructions
- **Done when:** Draft PRD stage includes evidence citation format and references template

#### Task 2.5: Add Stage 4 (Review)
- **Depends on:** Tasks 1.4, 2.4
- **Files:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Do:** Add "### Stage 4: CRITICAL REVIEW". Instructions to invoke prd-reviewer agent via Task tool. Pass PRD content and quality criteria. Parse JSON response.
- **Test:** Stage 4 section exists with reviewer invocation
- **Done when:** Review stage specifies agent invocation and response parsing

#### Task 2.6: Add Stage 5 (Auto-Correct)
- **Depends on:** Task 2.5
- **Files:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Do:** Add "### Stage 5: AUTO-CORRECT". Instructions to iterate through issues array. Apply fixes where actionable. Record what was changed and why. Update PRD file with corrections.
- **Test:** Stage 5 section exists with correction logic
- **Done when:** Auto-correct stage specifies issue iteration and fix application

#### Task 2.7: Modify Stage 6 (User Decision)
- **Depends on:** Task 2.6
- **Files:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Do:** Update existing promotion flow. Change options to: Refine (loop to Stage 1), Promote (invoke /iflow:create-feature), Abandon (save and exit). Use AskUserQuestion with 3 options.
- **Test:** Stage 6 section exists with 3-option decision
- **Done when:** User decision uses AskUserQuestion with Refine/Promote/Abandon options

### Phase 3: Integration

#### Task 3.1: Update Output File Naming
- **Depends on:** Tasks 2.1-2.7
- **Files:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Do:** Change all references from `brainstorm.md` or `{timestamp}-{slug}.md` to `{timestamp}-{slug}.prd.md`. Update standalone mode file creation.
- **Test:** File naming shows `.prd.md` extension
- **Done when:** All output file references use `.prd.md` extension

#### Task 3.2: Add Error Handling
- **Depends on:** Tasks 2.1-2.7
- **Files:** `plugins/iflow-dev/skills/brainstorming/SKILL.md`
- **Do:** Add graceful degradation section. If WebSearch unavailable → skip internet research with warning. If agent unavailable → proceed with warning. If all research fails → proceed with "Assumption: needs verification" labels.
- **Test:** Error handling section exists
- **Done when:** Error handling covers all risk scenarios from design

#### Task 3.3: Update Command Registration
- **Depends on:** Tasks 3.1, 3.2
- **Files:** `plugins/iflow-dev/commands/brainstorm.md` (if exists), skill YAML frontmatter
- **Do:** Verify command registration is correct. Update description if needed to reflect PRD output.
- **Test:** Command invocation works
- **Done when:** `/iflow:brainstorm` command reflects new PRD-focused behavior

## Summary

- Total tasks: 14
- Phase 1: 4 tasks (agents)
- Phase 2: 7 tasks (skill stages)
- Phase 3: 3 tasks (integration)
