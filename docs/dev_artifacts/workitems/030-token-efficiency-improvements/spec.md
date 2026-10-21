# Spec: Token Efficiency Improvements

## Problem Statement

The iflow plugin uses **Full Artifact Injection** — every subagent dispatch embeds the complete contents of all upstream artifacts (prd.md, spec.md, design.md, plan.md, tasks.md) directly into prompts. This causes:

- **O(N) token growth**: Each phase adds artifacts; downstream agents receive all prior artifacts in full.
- **Massive redundancy in review loops**: The implement command dispatches 3 reviewers per iteration (up to 5 iterations), each receiving the same 5 static documents + code. That's up to 15 full-artifact dispatches where the artifacts never change.
- **Wasted cost and latency**: Input tokens dominate spend; static artifacts are re-sent verbatim.

## Scope

Three focused improvements, ordered by impact:

1. **Agent Reuse via `resume`** — Reuse reviewer agents across review loop iterations instead of spawning new ones each time.
2. **Lazy-Load References** — Replace inline artifact injection with file-path references; agents read only what they need.
3. **Role-Specific Context Pruning** — Reduce per-reviewer artifact sets to only what their rubric requires.

### Out of Scope

- **Anthropic API-level prompt caching** (ephemeral cache blocks) — iflow operates through Claude Code's Task tool, not the raw API. Cache control headers are not accessible. Note: Anthropic applies automatic prompt caching for prompts exceeding 1024 tokens. The current full-injection approach may already benefit from this. R2 (lazy-load) changes prompt content to short file paths, which shifts token cost from input to tool-use (Read calls). This tradeoff is acceptable because total token consumption is still reduced — the artifacts are read once per dispatch rather than injected verbatim into every prompt prefix. If empirical measurement (NFR1) shows otherwise, re-evaluate.
- **RAG/embedding-based retrieval** — premature for current artifact sizes.
- **Lossy summarization** — violates iflow's accuracy-over-tokens principle.
- **MCP memory server as artifact store** — adds latency without clear benefit over file reads.

## Requirements

### R1: Agent Reuse via `resume` in Review Loops

**Context**: The Task tool's input schema includes a `resume` parameter: `"resume": {"description": "Optional agent ID to resume from. If provided, the agent will continue from the previous execution transcript.", "type": "string"}`. This is confirmed in the tool definition available to the orchestrating agent. Currently, every review iteration spawns a brand-new agent and re-sends all artifacts. The current command templates explicitly state "always a NEW Task tool dispatch per iteration" — this constraint is relaxed because `resume` preserves the agent's full transcript, making fresh dispatches with re-injected artifacts redundant.

**R1.1**: In `implement.md` review cycle (steps 7a-7c), on iteration 2+, use `Task({ resume: agent_id, prompt: delta_prompt })` to continue the same reviewer agent instead of creating a new one.

**R1.2**: The resumed prompt sends only the **delta**: (1) `git diff --stat` plus `git diff` output for all files changed since the previous review iteration, and (2) the implementer agent's fix summary from the fix dispatch. If the character count of the combined delta string (diff output + fix summary text) exceeds 50% of the character count of the iteration 1 prompt string (the full prompt passed to the first Task dispatch), fall back to a fresh dispatch (the savings no longer justify resume complexity).

**R1.3**: On iteration 1, dispatch normally with full context (establishing the agent's baseline). Store the returned `agent_id` for each reviewer.

**R1.4**: Apply the same resume pattern to the `specify.md` review loop (spec-reviewer, phase-reviewer) and `design.md` review loop (design-reviewer, phase-reviewer). Remove the "always a NEW Task tool dispatch per iteration" directive from these commands and replace with the resume-with-delta pattern.

**R1.5**: Apply the same resume pattern to `create-plan.md` (plan-reviewer, phase-reviewer) and `create-tasks.md` (task-reviewer, phase-reviewer). Remove the "always a NEW Task tool dispatch per iteration" directive from these commands.

**R1.6**: Apply resume to the **implementer fix dispatch** in `implement.md` Step 7e. On fix iteration 2+, resume the same implementer agent with: (1) the new issue list from failed reviewers, and (2) a list of changed file paths for the implementer to re-read via Read tool. The resumed implementer should re-read changed files as needed rather than relying on stale transcript context. Implementation file paths are re-listed in the resumed prompt for navigation. On fix iteration 1, dispatch fresh with full context.

**R1.7**: If a resumed agent fails (error from Task tool), fall back to a fresh dispatch using the R2 lazy-load reference format (not the old inline injection format). Log the fallback in `.review-history.md`.

**R1.8**: Test-deepener Phase A and Phase B are separate dispatches with different purposes (outline generation vs. test writing) — they do NOT use resume. Each phase dispatches fresh.

**Acceptance Criteria**:
- Review loop iteration 2+ uses `resume` instead of new dispatch.
- Resumed prompts contain only delta content (diff + fix summary), not full artifacts.
- Delta size guard: fresh dispatch if delta exceeds 50% of original prompt size.
- Fallback to fresh dispatch (with R2 lazy-load format) on resume failure.
- No behavioral change to review outcomes — same approval/rejection logic applies.

### R2: Lazy-Load File References

**Context**: Instead of embedding `{content of prd.md}` in prompts, pass the file path and instruct the agent to read it using its Read tool. All reviewer agents already have Read in their tools list (verified via codebase inspection).

**R2.1**: In all command prompt templates, replace inline artifact content blocks with mandatory-read reference blocks.

Current pattern:
```
## PRD (original requirements)
{content of prd.md}

## Spec (acceptance criteria)
{content of spec.md}
```

New pattern (combined with R3 pruning — this example is for security-reviewer in implement.md):
```
## Required Artifacts
You MUST read the following files before beginning your review.
After reading, confirm by stating the file names and their approximate line counts.
- Design: {feature_path}/design.md
- Spec: {feature_path}/spec.md
```

**R2.2**: Each reviewer's prompt lists ONLY the artifacts required by R3's per-role mapping. The prompt uses mandatory language ("You MUST read") rather than optional ("read on demand").

**R2.3**: The implementer agent prompt (initial task dispatch in `plugins/iflow/skills/implementing/SKILL.md` Step 2b) uses a hybrid approach: the implementing skill **retains** `extractSection()` scoping for plan.md and design.md (these are already efficiently scoped per task — only the relevant section is extracted). Other artifacts (spec.md, prd.md) use lazy-load references. Task description and "done when" criteria remain inline. Implementation file lists continue to be inlined (the implementer needs to know which files to work on).

**R2.4**: First-iteration reviewer dispatches include: "You MUST read the following files before beginning your review." Resumed iterations (R1) say: "You already have the artifacts in context from your previous review. Review only the following changes: {delta}."

**R2.5**: Apply lazy-load to ALL dispatch sites in `implement.md`, including:
- Step 5: code-simplifier dispatch
- Step 6: test-deepener dispatch
- Steps 7a-7c: reviewer dispatches
- Step 7e: implementer fix dispatch

**Acceptance Criteria**:
- No command prompt template contains `{content of prd.md}`, `{content of spec.md}`, `{content of design.md}`, `{content of plan.md}`, or `{content of tasks.md}` inline injection patterns.
- All artifact references use absolute file paths that agents can read via Read tool.
- Prompts use mandatory read language with confirmation directive.
- All dispatch sites in implement.md are covered (steps 5, 6, 7a-7c, 7e).

### R3: Role-Specific Context Pruning

**Context**: Not all reviewers need all artifacts. Tailor artifact references per role based on what their rubric actually evaluates.

**R3.1**: Define per-reviewer artifact requirements in `implement.md`:

| Reviewer | Required Artifacts | Rationale |
|---|---|---|
| implementation-reviewer | PRD, Spec, Design, Plan, Tasks | Full chain validation across all 4 levels |
| code-quality-reviewer | Design, Spec | Design for architecture rules (SOLID/KISS); Spec for YAGNI judgment (knows what was requested vs unnecessary) |
| security-reviewer | Design, Spec | Design for threat model/auth patterns; Spec for security requirements validation |
| code-simplifier | Design | Architecture patterns to simplify against |
| test-deepener | Spec, Design, Tasks, PRD | Phase A uses Tasks for test-to-task traceability and PRD Goals for business-level test scenarios |

**R3.2**: Define per-reviewer artifact requirements for phase commands:

| Phase Command | Domain Reviewer | Artifacts | Phase Reviewer | Artifacts |
|---|---|---|---|---|
| specify.md | spec-reviewer | PRD | phase-reviewer | PRD, Spec |
| design.md | design-reviewer | PRD, Spec | phase-reviewer | PRD, Spec, Design |
| create-plan.md | plan-reviewer | PRD, Spec, Design | phase-reviewer | PRD, Spec, Design, Plan |
| create-tasks.md | task-reviewer | PRD, Spec, Design, Plan | phase-reviewer | PRD, Spec, Design, Plan, Tasks |

**R3.3**: Each prompt template lists only the artifact paths from the tables above. No generic "all artifacts" blocks.

**Acceptance Criteria**:
- code-quality-reviewer and security-reviewer prompts reference Design + Spec (not PRD, Plan, Tasks).
- code-simplifier references Design only.
- test-deepener references Spec + Design + Tasks + PRD.
- Each reviewer prompt lists exactly the artifacts from the tables above.
- implementation-reviewer retains full chain access.

## Affected Files

Commands (prompt template changes — all dispatch sites within each):
- `plugins/iflow/commands/specify.md` — spec-reviewer, phase-reviewer dispatches
- `plugins/iflow/commands/design.md` — design-reviewer, phase-reviewer dispatches. Note: Stage 0 research agents (codebase-explorer, internet-researcher) receive a feature description summary, not full artifact content — they are excluded from R2/R3 conversion. No changes needed for these dispatch sites.
- `plugins/iflow/commands/create-plan.md` — plan-reviewer, phase-reviewer dispatches
- `plugins/iflow/commands/create-tasks.md` — task-reviewer, phase-reviewer dispatches
- `plugins/iflow/commands/implement.md` — code-simplifier (step 5), test-deepener (step 6), implementation-reviewer (7a), code-quality-reviewer (7b), security-reviewer (7c), implementer fix (7e)

Skills (implementer dispatch changes):
- `plugins/iflow/skills/implementing/SKILL.md` — per-task implementer dispatch (Step 2b)

Agents (verify Read tool access — already confirmed present):
- All reviewer agents in `plugins/iflow/agents/`

## Constraints

- **No behavioral regression**: Review approval/rejection logic must remain identical. Only the transport mechanism changes.
- **Fallback safety**: Resume failures fall back to fresh dispatch with R2 format. No preservation of old inline injection templates needed.
- **Agent tool access**: All reviewer agents already have Read in their tools list (verified). If any future agent lacks it, add it.
- **Prompt clarity**: Reference blocks use mandatory read language with confirmation to prevent agents from skipping file reads.
- **Preserve per-task scoping**: The implementing skill's `extractSection()` per-task scoping is **retained** for plan.md and design.md — it already efficiently extracts only the relevant section per task. Other artifacts (spec.md, prd.md) use lazy-load references. This avoids the anti-pattern of N tasks each reading the full file when only a section is relevant.

## Non-Functional Requirements

- **NFR1**: The prompt text for iteration 2+ dispatches (resume + delta) must be shorter than the iteration 1 prompt text (full references + read directives). Verify by comparing character counts of prompt strings in the command template logic. Alternatively, inspect subagent transcripts if available.
- **NFR2**: Track lazy-load fallback events (agents failing to read required artifacts, evidenced by reviewer responses that lack artifact-derived content). If fallback rate exceeds 20% of dispatches across the first 3 features using the new system, escalate for re-evaluation of the mandatory-read directive.

## Test Strategy

- **Grep audit**: After changes, `grep -rP "\{.*content.*\.md\}" plugins/iflow/` should return zero matches. This broad pattern catches all inline injection placeholders regardless of formatting (e.g., `{content of prd.md}`, `{spec.md content}`, `{design.md content}`).
- **Agent frontmatter check**: All reviewer agents have `Read` in their tools list.
- **Manual end-to-end validation**: Run a feature through the full workflow (specify → design → plan → tasks → implement) and verify:
  - Review loops use `resume` on iteration 2+
  - Agent prompts contain file references, not inline content
  - Reviewers read only their designated artifacts
  - No regression in review quality
- **Baseline comparison**: Re-run a completed feature's specify phase with new templates and compare review outcomes to the original `.review-history.md`. If the same issues surface in approximately the same order, confidence is high.
