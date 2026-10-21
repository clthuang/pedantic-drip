# Design: Enhanced Brainstorm-to-PRD Workflow

## Architecture Overview

The brainstorm command becomes a 6-stage orchestrator that delegates research and review to specialized subagents:

```
User → Brainstorming Skill (Orchestrator)
            │
            ├─ Stage 1: CLARIFY (interactive Q&A)
            │
            ├─ Stage 2: RESEARCH (parallel subagents)
            │     ├─ internet-researcher
            │     ├─ codebase-explorer
            │     └─ skill-searcher
            │
            ├─ Stage 3: DRAFT PRD (orchestrator)
            │
            ├─ Stage 4: CRITICAL REVIEW
            │     └─ prd-reviewer
            │
            ├─ Stage 5: AUTO-CORRECT (orchestrator)
            │
            └─ Stage 6: USER DECISION
                  ├─ Refine → Loop to Stage 1
                  ├─ Promote → /iflow:create-feature
                  └─ Abandon → End
```

## Components

### 1. Brainstorming Skill (Orchestrator)
- Purpose: Coordinates 6-stage flow, manages state, writes PRD
- Inputs: Topic from user, research findings from subagents, review feedback
- Outputs: PRD file at `docs/dev_artifacts/brainstorms/{timestamp}-{slug}.prd.md`
- Location: `plugins/iflow-dev/skills/brainstorming/SKILL.md` (modified)

### 2. Internet Researcher Agent
- Purpose: Search web for best practices, prior art, standards
- Inputs: Topic/query string, specific questions to research
- Outputs: Findings with sources `[{finding, source_url}]`
- Location: `plugins/iflow-dev/agents/internet-researcher.md`

### 3. Codebase Explorer Agent
- Purpose: Analyze existing patterns, constraints, related code
- Inputs: Topic/query string, file patterns to search
- Outputs: Findings with locations `[{finding, file_path, line}]`
- Location: `plugins/iflow-dev/agents/codebase-explorer.md`

### 4. Skill Searcher Agent
- Purpose: Find relevant existing skills in the plugin
- Inputs: Topic/query string
- Outputs: Relevant skills `[{skill_name, relevance, path}]`
- Location: `plugins/iflow-dev/agents/skill-searcher.md`

### 5. PRD Reviewer Agent
- Purpose: Critical review challenging assumptions, gaps, false certainty
- Inputs: PRD content
- Outputs: Issues with severity, evidence, fixes `{approved, issues[], summary}`
- Location: `plugins/iflow-dev/agents/prd-reviewer.md`

## Interfaces

### Research Subagent Interface (internet-researcher, codebase-explorer, skill-searcher)

```
Input:  {
  "query": "string - the topic or question to research",
  "context": "string - additional context about what we're building"
}

Output: {
  "findings": [
    {
      "finding": "string - what was discovered",
      "source": "string - URL, file:line, or skill path",
      "relevance": "high | medium | low"
    }
  ],
  "no_findings_reason": "string | null - explanation if nothing found"
}

Errors: Returns empty findings with no_findings_reason if:
  - No relevant results found
  - Tool unavailable (e.g., WebSearch not working)
```

### PRD Reviewer Interface

```
Input:  {
  "prd_content": "string - full PRD markdown content",
  "quality_criteria": "string - checklist to evaluate against"
}

Output: {
  "approved": boolean,
  "issues": [
    {
      "severity": "blocker | warning | suggestion",
      "description": "string - what's wrong",
      "location": "string - PRD section or line",
      "evidence": "string - why this is an issue",
      "suggested_fix": "string - how to address it"
    }
  ],
  "summary": "string - 1-2 sentence overall assessment"
}

Errors: Graceful degradation - if reviewer fails, proceed with warning
```

### PRD Output Format

```
Output file: docs/brainstorms/{timestamp}-{slug}.prd.md

Sections:
- Status (Draft/Ready/Approved/Abandoned)
- Problem Statement + Evidence
- Goals
- Success Criteria (checkboxes)
- User Stories (As a/I want/So that)
- Use Cases (Actors/Pre/Flow/Post/Edge)
- Edge Cases table
- Constraints (Behavioral + Technical)
- Requirements (Functional + Non-Functional)
- Non-Goals
- Out of Scope
- Research Summary (Internet/Codebase/Skills)
- Review History
- Open Questions
```

## Technical Decisions

### TD-1: Modify Existing Skill vs. Create New
- **Choice:** Modify existing `brainstorming/SKILL.md`
- **Alternatives:** Create new `prd-creation/SKILL.md`
- **Rationale:** The command name `/iflow:brainstorm` remains intuitive; avoids user confusion; the output (PRD) is a formalized brainstorm

### TD-2: Sequential vs. Parallel Research Subagents
- **Choice:** Parallel invocation
- **Alternatives:** Sequential invocation
- **Rationale:** Research subagents explore independent domains (internet, codebase, skills) with no dependencies between them; parallel execution is faster and more efficient

### TD-3: Agent Definition Format
- **Choice:** YAML frontmatter + markdown (same as existing agents)
- **Alternatives:** JSON config, separate files
- **Rationale:** Consistency with existing `plugins/iflow-dev/agents/*.md` format

### TD-4: Evidence Citation Format
- **Choice:** Inline with claim: `{claim} — Evidence: {source}`
- **Alternatives:** Footnotes, separate section
- **Rationale:** Keeps evidence visible next to claims; easier to verify; matches brainstorm document style

### TD-5: Review Loop Strategy
- **Choice:** Single review pass with auto-correct
- **Alternatives:** Multiple iterations until perfect
- **Rationale:** Scope says "single pass for now"; avoids infinite loops; user can choose "refine" for more passes

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Research subagents return no findings | PRD lacks evidence | Return explicit "no findings" with reason; proceed with "Assumption: needs verification" labels |
| WebSearch/WebFetch unavailable | No internet research | Graceful degradation; skip with warning; proceed with codebase-only research |
| PRD reviewer unavailable | No critical review | Graceful degradation; proceed with warning (existing pattern in brainstorm-reviewer) |
| User abandons mid-flow | Partial PRD state | Save progress to file at each stage; allow resume on next invocation |
| PRD format too rigid | Difficult to fill all sections | Mark optional sections; allow "N/A" where appropriate |

## Dependencies

- Existing Task tool for spawning subagents
- WebSearch/WebFetch tools (may be unavailable in some environments)
- Glob/Grep/Read tools for codebase exploration
- Existing agent YAML frontmatter format
- Existing `/iflow:create-feature` command for promotion
