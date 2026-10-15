---
description: Turn a brainstorm PRD into shape.md requirements
argument-hint: "[--feature=<id-slug>]"
---

# /pd:specify

Contract command. Shared mechanics (entry, exit, YOLO, review gate, dispatch hygiene): workflow-transitions skill.

**Purpose:** convert the promoted PRD — or the mini-spec, when an express feature escalates to deep mode — into requirements design can build against.

**Inputs:** the feature's `prd.md` if present, else the `mini_spec` phase event, else the user's description; engine phase state.

**Output:** `shape.md` `## Requirements` in the feature directory — problem statement; success criteria written as mechanically checkable statements (each one a command, grep, count, or file predicate another person can run and get the same answer); in-scope and out-of-scope lists; edge cases with their expected behavior.

**Steps:**
1. Engine entry (workflow-transitions) with `target_phase="specify"`.
2. Read the PRD or mini-spec. Ask the user only about contradictions and unstated decisions the source cannot answer.
3. Write `## Requirements` into `{pd_artifacts_root}/features/{id}-{slug}/shape.md`.
4. Mechanical gate: `bash ${CLAUDE_PLUGIN_ROOT}/scripts/phase-gate.sh specify {feature-dir}`. Each failure line names the missing artifact or section — fix and re-run.
5. Engine exit (workflow-transitions) with artifacts `[shape.md]`.

**Constraints:** no LLM review at this phase — the gate is the whole check. A criterion needing human judgment to score goes back to the user as a question, not into the artifact. No state writes outside MCP tools; no phase-sequence or status-vocabulary restatement.
