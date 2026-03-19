---
name: creating-specialist-teams
description: Creates ephemeral specialist teams via template injection into generic-worker. Use when the user says 'create specialist team', 'assemble team', or 'deploy specialists'.
---

# Creating Specialist Teams

Create ephemeral specialist teams for complex tasks by injecting structured templates into `pd:generic-worker` instances.

## Concept

Instead of creating permanent agent files, specialist teams are:
- **Ephemeral** — templates injected at runtime, no files on disk
- **Focused** — each specialist has a narrow scope with specific success criteria
- **Coordinated** — deployed as parallel fan-out or sequential pipeline

## Available Templates

Locate via two-location Glob: `~/.claude/plugins/cache/*/pd*/*/skills/creating-specialist-teams/references/`, fallback `plugins/*/skills/creating-specialist-teams/references/` (dev workspace):

| Template | Tools | Focus |
|----------|-------|-------|
| `code-analyzer.template.md` | Read, Glob, Grep | Read-only analysis, structured findings |
| `research-specialist.template.md` | Read, Glob, Grep, WebSearch | Evidence gathering, source citations |
| `implementation-specialist.template.md` | Read, Write, Edit, Bash, Glob, Grep | TDD code writing, commit discipline |
| `domain-expert.template.md` | Read, Glob, Grep | Advisory output, structured recommendations |
| `test-specialist.template.md` | Read, Write, Edit, Bash, Glob, Grep | Coverage analysis, edge case matrices |

## Template Placeholders

Each template contains placeholders that are filled before injection:

| Placeholder | Description |
|-------------|-------------|
| `{TASK_DESCRIPTION}` | The specific assignment for this specialist |
| `{CODEBASE_CONTEXT}` | Relevant files and patterns discovered via Glob/Grep |
| `{SUCCESS_CRITERIA}` | What constitutes successful output |
| `{OUTPUT_FORMAT}` | Required structure for findings |
| `{SCOPE_BOUNDARIES}` | What the specialist should NOT do |
| `{WORKFLOW_CONTEXT}` | Active feature state, current phase, next phase, available artifacts. "No active feature workflow." when standalone. |

## Coordination Patterns

### Parallel Fan-Out
All specialists work independently on different aspects of the same task. Best for analysis and review tasks.

### Sequential Pipeline
Output of one specialist feeds into the next. Best for analyze → implement → test workflows.

## Team Size

Maximum 5 specialists per team. Prefer smaller teams (2-3) for focused tasks.
