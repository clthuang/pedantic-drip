---
name: implementing
description: Dispatches per-task implementer agents from tasks.md, collecting reports into implementation-log.md. Use when the user says 'implement the feature', 'start coding', 'write the code', or 'execute tasks'.
---

# Implementation Phase

## Static Reference
Execute the implementation plan with a structured per-task dispatch approach.

## Prerequisites

- If `tasks.md` exists: Read for task list
- If not: "No tasks found. Run /pd:create-tasks first, or describe what to implement."

## Related Skills

For complex implementations:
- `implementing-with-tdd` - RED-GREEN-REFACTOR discipline

## Process

### Step 1: Read Task List

1. Read `tasks.md` from the active feature directory
2. Parse all task headings using regex: `/^(#{3,4})\s+Task\s+(\d+(?:\.\d+)*):?\s*(.+)$/`
3. For each match, extract:
   - **Task number** (string, e.g., "1.1")
   - **Task title**
   - **Task body** (from heading through next same-or-higher-level heading, or EOF)
   - **Why/Source** field value (from `**Why:**` or `**Source:**`, if present)
   - **Done when** criteria (from `**Done when:**`, if present)
4. If no task headings found: log error, surface to user, STOP

### Step 2: Per-Task Dispatch Loop

For each task (in document order, top to bottom):

**a. Prepare context**

**Parse traceability references** from the task's `**Why:**` or `**Source:**` field value:

1. If the field is present, split its value on comma and trim each reference.
2. Match each reference against these patterns:
   - Plan reference: `/Plan (?:Step )?(\w+\.\w+)/i` — captures plan identifier (e.g., "1A.2")
   - Design reference: `/Design (?:Component )?(\w+[-\w]*)/i` — captures design identifier (e.g., "event-bus")
   - Spec reference: `/Spec (\w+\.\w+)/i` — informational only; spec is always loaded in full
3. Collect matched plan identifiers and design identifiers into separate lists.

**Extract scoped sections** using heading extraction:

For each plan identifier, extract its section from `plan.md`. For each design identifier, extract its section from `design.md`. Use this procedure:

To extractSection(markdown, identifier): scan all headings in the markdown. Find the first heading whose text contains the identifier as a case-insensitive substring. Extract everything from that heading through (but not including) the next heading at the same level, or through EOF if no same-level heading follows.

To extractSectionWithFallback(markdown, identifier): first try extractSection with the full identifier. If no heading matches and the identifier contains a dot, strip everything after the last dot (e.g., "1A.1" becomes "1A") and retry with that prefix. Return the matched section text, or null if still not found.

Apply extractSectionWithFallback for each identifier. If any extraction returns null, discard all partial results for that artifact and load the full file instead.

**Fallback: load full artifacts when traceability is unavailable.** If the Why/Source field is absent, empty, or none of its references match the patterns above, load design.md and plan.md in full. Log a warning: "No parseable traceability references — loading full artifacts." Known fallback scenarios:
- Feature 018 uses a `§` separator format that the regexes will not match
- Feature 020 has no traceability fields
- Features 002-016 predate the traceability template

**Assemble context for dispatch:**
- `design.md`: scoped sections joined in order (or full file if any extraction failed or fallback triggered)
- `plan.md`: scoped sections joined in order (or full file if any extraction failed or fallback triggered)
- `prd.md` (I8 resolve_prd): resolve the PRD file path before dispatch:
  1. Check if `{feature_path}/prd.md` exists
  2. If exists → PRD path = `{feature_path}/prd.md`
  3. If not → check `.meta.json` for `brainstorm_source`
     a. If found → PRD path = brainstorm_source value
     b. If not → PRD line = `- PRD: No PRD — feature created without brainstorm`
- `spec.md`: referenced in Required Artifacts block — agent reads via Read tool on demand

**Load project context (conditional):**

Check the feature's `.meta.json` for a `project_id` field. If absent or null, skip this entire block — no error, no warning (AC-10).

If `project_id` is present (non-null):

1. **Resolve project directory:** Glob `{pd_artifacts_root}/projects/{project_id}-*/`. If not found, log warning and skip project context entirely.
2. **Load project goals:** Read the project's `prd.md`. Extract `## Problem Statement` and `## Goals` sections (heading through next `##`). Summarize to 2-3 bullet points (~100 tokens).
3. **Load feature dependency status:** Read this feature's `.meta.json` `depends_on_features` list. If absent or empty, omit dependencies from the block. For each reference: glob `{pd_artifacts_root}/features/{ref}-*/`, read its `.meta.json` `status` field. Categorize into completed[], in-progress[], blocked[].
4. **Load priority signal:** Read the project's `roadmap.md` if it exists. Find the milestone containing this feature's ID or slug. Extract milestone name and position (~50 tokens). If `roadmap.md` missing, omit priority signal.
5. **Format the block** (~200-500 tokens total):

```markdown
## Project Context
**Project:** {project name} | **This feature:** {feature name}
**Project goals:** {2-3 bullet summary from project PRD}
**Feature dependencies:** completed: {names} | in-progress: {names} | blocked: {names}
**Priority signal:** {milestone name, or "not on roadmap"}
```

6. **Token budget enforcement:** If the formatted block exceeds ~500 tokens (e.g., many dependencies), truncate dependency details to counts only ("3 completed, 1 in-progress") and trim goal bullets.

**Graceful degradation:** Project dir not found: skip block. `roadmap.md` missing: omit priority line. `depends_on_features` absent: omit dependencies line. Any individual dependency glob fails: skip that dependency, continue with others.

**b. Dispatch implementer agent**

```
Task tool call:
  subagent_type: pd:implementer
  model: opus
  prompt: |
    {task description with done-when criteria}

    {## Project Context block, if prepared above — omit entirely if not project-linked}

    ## Required Artifacts
    You MUST read the following files before beginning your work.
    After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
    - Spec: {feature_path}/spec.md
    {resolve_prd() output — emit "- PRD: {path}" or "- PRD: No PRD — feature created without brainstorm"}

    ## Design Context (scoped)
    {design.md scoped sections via extractSection()}

    ## Plan Context (scoped)
    {plan.md scoped sections via extractSection()}
```

**Fallback detection (I9):** After receiving the agent's response, search for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: implementer did not confirm artifact reads` to `.review-history.md`. Proceed regardless — this is observational only.

**c. Collect report**

Extract from the agent's text response:
- **Files changed** — required
- **Decisions** — optional, default "none"
- **Deviations** — optional, default "none"
- **Concerns** — optional, default "none"

Use substring match (case-insensitive) for field headers.

**d. Append implementation-log.md entry**

Write to `implementation-log.md` in the active feature directory.
Create with `# Implementation Log` header if this is the first task.

```markdown
## Task {number}: {title}
- **Files changed:** {from report}
- **Decisions:** {from report, or "none"}
- **Deviations:** {from report, or "none"}
- **Concerns:** {from report, or "none"}
```

**e. Error handling per task**

- **Dispatch failure (AC-20):** Log the error, then ask the user whether to retry or skip via AskUserQuestion.
- **Malformed report (AC-21):** Write a partial log entry with whatever fields are available, then proceed to the next task.

**f. Proceed to next task**

### Step 3: Return Results

After all tasks dispatched:

1. Report summary: N tasks completed, M skipped/blocked
2. Return deduplicated list of all files changed
3. `implementation-log.md` is on disk for retro to read later

## Commit Pattern

After all tasks dispatched:
```
git add {files}
git commit -m "feat: {brief description}"
```

## Error Handling

If implementation is stuck:
1. Try a different approach
2. Break into smaller pieces
3. Ask user for guidance

See Step 2e for per-task dispatch failure (AC-20) and malformed report (AC-21) handling.

Never spin endlessly. Ask when stuck.

## Completion

After all tasks:
"Implementation complete. {N} tasks completed, {M} skipped."
"Proceeding to code simplification and review phases (3 reviewers dispatched in parallel, within `max_concurrent_agents` budget)."

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

## Read Feature Context

1. Find active feature folder in `{pd_artifacts_root}/features/`
2. Read `.meta.json` for mode and context
3. Adjust behavior based on mode:
   - Standard: Full process with optional verification
   - Full: Full process with required verification
