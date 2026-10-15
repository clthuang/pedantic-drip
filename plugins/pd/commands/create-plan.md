---
description: Derive an ordered task plan from the shape document
argument-hint: "[--feature=<id-slug>]"
---

# /pd:create-plan

Contract command. Shared mechanics (entry, exit, YOLO, review gate, dispatch hygiene): workflow-transitions skill.

**Purpose:** give the implementer an execution order it does not have to re-derive.

**Inputs:** `shape.md` `## Requirements` and `## Design`; engine phase state.

**Output:** `plan.md` `## Plan` — an ordered task list. Each task names what it changes, the files it touches, and the command that proves it done (test invocation, script, or grep). Tasks whose file sets do not intersect are marked parallel-safe; the `implementing` skill dispatches those into `.pd-worktrees/task-{N}` and merges the branches back.

**Steps:**
1. Engine entry (workflow-transitions) with `target_phase="create-plan"`.
2. Derive the tasks from `shape.md` — tests before code wherever the design pins a contract.
3. Write `## Plan` into `plan.md` in the feature directory.
4. Mechanical gate: `bash ${CLAUDE_PLUGIN_ROOT}/scripts/phase-gate.sh create-plan {feature-dir}`.
5. Engine exit (workflow-transitions) with artifacts `[plan.md]`.

**Constraints:** no separate `tasks.md`, ever — the list lives in `## Plan` and implement re-reads it at dispatch time, so editing the plan is the only way a task changes. No LLM review at this phase. A task with no verification command is not finished being written. No state writes outside MCP tools; no phase-sequence or status-vocabulary restatement.
