---
description: Start brainstorming to produce evidence-backed PRD
argument-hint: [topic or idea to explore]
---

# /pd:brainstorm Command

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

## Steps

### Step 1: Execute Brainstorming Skill

Invoke `/pd:brainstorming` skill which runs 7 stages:

| Stage | Name | Action | Output |
|-------|------|--------|--------|
| 1 | CLARIFY | Q&A to resolve ambiguities | Clear problem + goals |
| 2 | RESEARCH | Parallel subagent research | Evidence from 3 sources |
| 3 | DRAFT PRD | Generate PRD with citations | PRD file |
| 4 | CRITICAL REVIEW | prd-reviewer challenges draft | Issues list |
| 5 | AUTO-CORRECT | Apply reviewer fixes | Updated PRD |
| 6 | READINESS CHECK | brainstorm-reviewer validates | Approval status |
| 7 | USER DECISION | Promote, refine, or save | Next action |

### Step 2: Handle Output

PRD saved to `{pd_artifacts_root}/brainstorms/YYYYMMDD-HHMMSS-{slug}.prd.md`
