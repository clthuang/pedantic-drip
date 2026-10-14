---
description: Turn shape.md requirements into a reviewed technical design
argument-hint: "[--feature=<id-slug>]"
---

# /pd:design

Contract command. Shared mechanics (entry, exit, YOLO, review gate, dispatch hygiene): workflow-transitions skill.

**Purpose:** extend the feature's `shape.md` with a technical design grounded in the codebase.

**Inputs:** `shape.md` `## Requirements` (specify output); engine phase state.

**Output:** `shape.md` `## Design` section — an `### Architecture` mermaid diagram (modules, data flows, the contract on each edge), decisions with rationale, data/schema changes, each interface contract pinned in exactly ONE code block (a second restatement anywhere in the artifact set is a defect), risks with mitigations, test strategy.

**Steps:**
1. Engine entry (workflow-transitions) with `target_phase="design"`.
2. Ground in code: dispatch codebase-explorer for affected-surface mapping; internet-researcher only for external unknowns. Prompts carry pointers, not file dumps.
3. Write `## Design` into `shape.md` — one shape document; a separate design file is not part of the inventory (FR-11).
4. Mechanical gate: `bash scripts/phase-gate.sh design {feature-dir}` — must pass before review.
5. Review moment (1 of 2): dispatch `pd:design-reviewer` (fresh context; return schema lives in the agent file). One pass → at most one fix round → remaining blockers go to the user.
6. Engine exit (workflow-transitions) with artifacts `[shape.md]`.

**Constraints:** no state writes outside MCP tools; no phase-sequence or status-vocabulary restatement; security-surface, migration, or multi-file-blast-radius features must not skip this phase.
