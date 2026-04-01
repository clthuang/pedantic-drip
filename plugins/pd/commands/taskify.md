---
description: "Break down any plan into atomic tasks with verified DoDs"
argument-hint: "<plan-path> [--spec=<path>] [--design=<path>] [--output=<path>]"
---

Break down any plan file into atomic, actionable tasks. This is a standalone command that works on ANY plan from ANY project -- no .meta.json, no entity registry, no MCP calls.

## Step 1: Parse Arguments

Extract from the command arguments:
- `plan_path` = first positional argument (REQUIRED)
- `--spec=<path>` = optional spec file for richer traceability validation
- `--design=<path>` = optional design file for richer traceability validation
- `--output=<path>` = optional output path (default: same directory as plan file, named `tasks.md`)

If no `plan_path` provided, output:
```
Usage: /pd:taskify <plan-path> [--spec=<path>] [--design=<path>] [--output=<path>]
```
Then STOP.

## Step 2: Validate Inputs

1. Read the plan file at `plan_path`. If it does not exist:
   ```
   Error: Plan file not found: {plan_path}
   ```
   STOP.

2. If the plan file exists but has fewer than 100 bytes of content:
   ```
   Error: Plan file too small ({byte_count} bytes). Provide a substantive plan (>100 bytes).
   ```
   STOP.

3. If `--spec` provided, verify the file exists. If not:
   ```
   Error: Spec file not found: {spec_path}
   ```
   STOP.

4. If `--design` provided, verify the file exists. If not:
   ```
   Error: Design file not found: {design_path}
   ```
   STOP.

5. Compute `output_path`:
   - If `--output` provided: use that path
   - Otherwise: `{directory of plan_path}/tasks.md`

**IMPORTANT:** Do NOT check for `.meta.json`. Do NOT call any MCP tools. Do NOT access the entity registry. This command is standalone.

## Step 3: Produce Tasks

Follow the **breaking-down-tasks** skill to create tasks from the plan content:
- Read the plan file content
- If `--spec` provided: read the spec file and include its content as additional context for traceability
- If `--design` provided: read the design file and include its content as additional context for traceability
- Generate the task breakdown following the skill's output format (dependency graph, execution strategy, task details)
- Write the result to `output_path`

Adaptations for standalone mode:
- Omit any feature ID references (use the plan's title instead)
- Omit any `.meta.json` state tracking
- Omit any MCP/entity registry calls
- Omit TodoWrite and Vibe-Kanban references

## Step 4: Quality Review Cycle (Automatic)

Set `iteration = 1`, `max_iterations = 3`.

**Loop:**

### 4a. Dispatch task-reviewer

```
Task tool call:
  description: "Review task breakdown quality"
  subagent_type: pd:task-reviewer
  model: sonnet
  prompt: |
    Review the task breakdown for quality and executability.

    ## Required Artifacts
    Read these files:
    - Plan: {plan_path}
    - Tasks: {output_path}
    {if spec_path: "- Spec: {spec_path}"}
    {if design_path: "- Design: {design_path}"}

    Validate:
    1. Plan fidelity - every plan item has tasks
    2. Task executability - any engineer can start immediately
    3. Task size - 5-15 min each
    4. Dependency accuracy - parallel groups correct
    5. Testability - binary done criteria

    Return JSON:
    {
      "approved": true/false,
      "issues": [{"severity": "blocker|warning|suggestion", "task": "...", "description": "...", "suggestion": "..."}],
      "summary": "..."
    }

    This is iteration {iteration} of {max_iterations}.
```

### 4b. Branch on result

- **If `approved: true`:** Proceed to Step 5.
- **If `approved: false` AND `iteration < max_iterations`:**
  - Auto-correct all blocker and warning issues in the tasks file at `output_path`
  - Increment `iteration`
  - Loop back to 4a
- **If `approved: false` AND `iteration == max_iterations`:**
  - Output warning:
    ```
    Warning: Task review did not fully approve after {max_iterations} iterations.
    Unresolved issues:
    {list of remaining blocker/warning issues}
    ```
  - Proceed to Step 5 with tasks as-is.

## Step 5: Output

Count the tasks and parallel groups from the generated file, then output:

```
Tasks created: {n} tasks across {m} parallel groups.
Output: {output_path}
```
