# Spec: Prompt Caching & Reviewer Reuse

## Problem Statement

Feature 030 implemented lazy-load references (R2) and role-specific pruning (R3), but **deferred R1 (agent reuse via resume)** due to GitHub #13619 (400 errors when resuming tool-using agents). Every review iteration across all phase commands still spawns a fresh subagent, re-warming the cache and re-reading all artifacts from scratch. This causes:

- **Wasted cache warm-up cost**: Each fresh dispatch creates a new subagent context. The system prompt and tool definitions are re-cached (1.25x write cost) per dispatch, even though every dispatch of the same agent type has an identical system prompt. Within a 5-iteration review loop, that's 5 cache writes for the same system prompt.
- **Redundant artifact reads**: On iteration 2+, the reviewer re-reads the same artifact files via Read tool, producing identical content. With `resume`, the prior transcript (including previous Read results) is already in context — no re-read needed for unchanged artifacts.
- **No exploitation of conversation-level caching**: A resumed subagent's full prior transcript becomes part of the API call prefix. If the cache is warm (within TTL), those tokens are served at 0.1x cost. A fresh dispatch discards this entirely.

**Assumption (A1)**: Claude Code applies automatic prompt caching to resumed subagent transcripts (the re-sent prior conversation serves as a cacheable prefix). If this assumption is false, R1 still provides value by avoiding redundant Read tool calls (agents already have artifacts in transcript), but the 0.1x cache-read cost benefit may not materialize. R1.0 validation should include observation of whether resumed dispatches are noticeably faster than fresh dispatches (a rough proxy for cache hits).

Additionally, iflow's dispatch prompt structure has not been audited for cache-hit optimization. The order of content within dispatch prompts affects how much of the prefix can be served from cache across iterations.

## Scope

Two focused improvements:

1. **R1: Agent Reuse via `resume`** — Implement the deferred Phase 2 from feature 030. Reuse reviewer agents across review loop iterations using the Task tool's `resume` parameter.
2. **R4: Prompt Structure Optimization** — Reorder dispatch prompt sections to maximize the cached prefix. Stable content (rubric, role description, artifact references, JSON schema) first; dynamic content (iteration context, delta, previous issues) last.

### Out of Scope

- **Cross-phase reviewer reuse** (e.g., reusing a phase-reviewer from specify into design). Different phases have fundamentally different review contexts and artifact sets. The overhead of providing phase transition context would negate savings.
- **Anthropic API-level cache control configuration** (TTL, explicit breakpoints). iflow operates through Claude Code's Task tool, not the raw API. Claude Code manages cache breakpoints automatically.
- **Main session prompt caching** — already handled by Claude Code's automatic caching of system prompt + CLAUDE.md + tool definitions. No iflow changes needed.
- **Subagent system prompt changes** — agent .md files are already static (no dynamic content). Cache sharing across same-type dispatches already works automatically.
- **Brainstorming skill dispatches** — excluded in feature 030, remains excluded. PRD-under-review is the only artifact; lightweight single-round reviews.

## Requirements

### R1: Agent Reuse via `resume` in Review Loops

**Context**: The Task tool's `resume` parameter accepts an agent ID and continues from the previous execution transcript. Feature 030's spec defined R1.1-R1.8 in detail. Those requirements are adopted here with the following updates reflecting current codebase state (post-feature-030 lazy-load conversion):

- Added R1.0 (prerequisite validation gate with structured checklist)
- R1.1 expanded to cover all 5 command files (030 listed only implement.md)
- R1.2 generalized delta definition for phase commands vs implement.md, added diff-based delta option for phase commands
- R1.4 corresponds to 030-R1.2 delta guard (renumbered)
- R1.5 corresponds to 030-R1.6 (implementer fix dispatch)
- R1.6 adds RESUME-FALLBACK marker (030-R1.7 had no marker)
- R1.3 corresponds to 030-R1.3, adds explicit `resume_state` dict structure
- R1.7-R1.8 unchanged from 030
- R1.9 is new (selective dispatch + final validation interaction, not addressed in 030)

**R1.0 (Prerequisite Validation)**: Before implementing any R1 changes, validate that Task tool `resume` works correctly with tool-using agents. Run a structured validation test with the following pass/fail checklist:

| # | Test | Pass Criteria |
|---|------|---------------|
| V1 | Dispatch spec-reviewer with a prompt that triggers Read tool use. Capture the agent_id from the Task tool result. | agent_id is present in the Task tool result for a synchronous (foreground) dispatch. If NOT present, R1 is blocked — document workaround or defer. |
| V2 | Resume the agent using `Task({ resume: agent_id, prompt: "..." })`. | No API error (no 400/500 status). Agent responds. |
| V3 | In the resumed prompt, ask the agent to repeat verbatim the first line of the file it read in V1. | Response contains the exact first-line string from the Read result in V1. Binary pass/fail. |
| V4 | Ask the resumed agent how many issues it found in its V1 review. | Count matches the actual number of issues in the V1 response JSON. Binary pass/fail. |

**Known GitHub issues that may cause V1-V4 failures:**
- #13619: 400 errors when resuming agents that used tools (closed as duplicate)
- #11712: Subagent transcripts missing user prompts on resume
- #10864: Task tool not returning agent_id for completed (synchronous) agents
- #11892: Task tool guidance contradicts resume functionality

**Decision gate:** ALL four tests must pass. If ANY fail, R1 is deferred — proceed with R4 only. Document the failure in `.meta.json` as `"r1_deferred_reason": "{test_id}: {failure description}"`.

**R1.1**: In all review loop iterations 2+, use `Task({ resume: agent_id, prompt: delta_prompt })` instead of a fresh dispatch. Applies to:
- `specify.md`: spec-reviewer loop, phase-reviewer loop
- `design.md`: design-reviewer loop, phase-reviewer loop
- `create-plan.md`: plan-reviewer loop, phase-reviewer loop
- `create-tasks.md`: task-reviewer loop, phase-reviewer loop
- `implement.md`: implementation-reviewer (7a), code-quality-reviewer (7b), security-reviewer (7c) in selective re-dispatch

**R1.2**: The resumed prompt sends only the **delta**. Two distinct delta strategies:

**R1.2a (Phase command delta)**: For specify, design, create-plan, create-tasks — a **unified text diff** of the single artifact-under-review (before vs after orchestrator revision). The orchestrator must capture the artifact content before applying revisions, then diff against the revised content. Prefer the simplest available mechanism: if the artifact content is already held in a variable at revision time, use in-memory string comparison; fall back to temp-file diff or `diff` CLI only if in-memory is unavailable. If the diff exceeds the R1.4 threshold, fall back to fresh dispatch.

**R1.2b (Implement delta)**: For implement.md — `git diff` output for all implementation files changed since the previous iteration, plus the implementer fix summary text.

**Common rules for both**:
- The resumed prompt does NOT re-list the Required Artifacts block — the agent already has those files in its transcript from iteration 1.
- The resumed prompt includes: "You already have the upstream artifacts and the previous version of {artifact} in context from your prior review. The following changes were made:"

**R1.3**: On iteration 1, dispatch normally with full context (current I1 template from feature 030). Store the returned `agent_id` for each reviewer role in a `resume_state` dict keyed by reviewer role name.

**R1.4**: Delta size guard: if the character count of the delta prompt exceeds 50% of the iteration 1 prompt character count, fall back to a fresh dispatch. Rationale: at 50% delta size, the resumed prompt is at worst half the cost of a fresh dispatch (the prior transcript is cached). The 50% threshold is conservative — carried forward from feature 030's spec. If empirical data shows a different threshold is optimal, adjust.

**R1.5**: Apply resume to the **implementer fix dispatch** in `implement.md` Step 7e. On fix iteration 2+, resume the same implementer with: (1) the consolidated issue list from all failed reviewers, (2) changed file paths for the implementer to re-read via Read tool, and (3) the complete list of all files assigned to this implementation task (not just changed files — the implementer may need to re-read any of them after applying fixes). Required Artifacts are NOT re-sent (already in transcript). On fix iteration 1, dispatch fresh.

**R1.6**: If a resumed agent fails (error from Task tool), fall back to a fresh dispatch using the current lazy-load template (I1 from feature 030). Log the fallback in `.review-history.md` with marker `RESUME-FALLBACK: {agent_role} iteration {n} — {error summary}`. Note: a resume after cache TTL expiration is NOT an error — the agent still resumes correctly, it just incurs full input token cost (cache miss). R1.6 fallback only triggers on actual API/tool errors.

**R1.7**: Test-deepener Phase A and Phase B remain separate fresh dispatches (different purposes). Code-simplifier is a single dispatch (no iteration loop) — no resume applicable.

**R1.8**: Remove the "Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support." annotations from all command files. Replace with the resume-with-delta pattern.

**R1.9 (Selective dispatch + final validation in implement.md)**: In implement.md, reviewers that passed on a given iteration may be re-dispatched during the final validation round (all-pass confirmation). For the final validation round:
- If the stored agent_id is still available, attempt resume. The cache may be cold (TTL expired between iterations), but resume still works — it just costs more.
- If resume fails (R1.6), fall back to fresh dispatch.
- The `resume_state` dict persists across all iterations of the implement review loop, regardless of whether a reviewer was dispatched in intermediate iterations.
- When a previously-passing reviewer is resumed for final validation, the resumed prompt must include a brief summary of changes made since its last review (e.g., "Since your last review at iteration {n}, the following fixes were applied: {fix summary}"), so the reviewer is not evaluating against a stale understanding of the codebase.

**Acceptance Criteria**:
- Review loop iteration 2+ uses `resume` instead of new dispatch
- Resumed prompts contain only delta content (diff for phase commands, git diff for implement)
- Delta size guard triggers fresh dispatch when delta > 50% of iteration 1 prompt
- Fallback to fresh dispatch on resume failure, logged as `RESUME-FALLBACK`
- Selective re-dispatch in implement.md preserves per-reviewer status tracking
- No change to review approval/rejection logic

### R4: Prompt Structure Optimization for Cache Hits

**Context**: Claude Code's automatic prompt caching uses a prefix cache. The longer the matching prefix between two API calls, the more tokens are served from cache at 0.1x cost. Within a subagent's context, the order of content in the dispatch prompt affects cache hit rate on fresh dispatches of the same agent type.

**R4.1**: All reviewer dispatch prompts must follow this canonical section ordering:

```
## Canonical Dispatch Template Skeleton

--- STABLE PREFIX (same across all iterations) ---

1. ROLE + TASK DESCRIPTION
   "{role-specific review instructions and rubric}"

2. REQUIRED ARTIFACTS
   "## Required Artifacts
   You MUST read the following files before beginning your review.
   After reading, confirm: 'Files read: {name} ({N} lines), ...' in a single line.
   - {artifact}: {path}
   ..."

3. JSON RETURN SCHEMA
   "Return your assessment as JSON:
   { approved, issues[{severity, ...}], summary }"

--- DYNAMIC SUFFIX (changes per iteration) ---

4. ARTIFACT-UNDER-REVIEW CONTENT
   For phase commands: the current draft of the artifact being reviewed
   (spec.md content, design.md content, etc. — revised each iteration).
   For implement.md: the implementation files list.

5. ITERATION CONTEXT
   "This is iteration {n} of {max}."
   "{if n > 1: previous issues to re-evaluate}"
```

**R4.2**: For resumed dispatches (R1, iteration 2+), the prompt is inherently dynamic (delta-only). The canonical skeleton applies to iteration 1 dispatches and fresh fallback dispatches only.

**R4.3**: The implementer dispatch (implementing/SKILL.md Step 2b) already has a stable structure (task description, design context, plan context are all per-task-fixed). No reordering needed — verified that no dynamic content precedes stable content.

**Acceptance Criteria**:
- All iteration 1 dispatch prompts follow the canonical skeleton ordering
- Rubric and JSON schema appear before artifact-under-review content and iteration context
- Required Artifacts block appears before the artifact-under-review content
- The canonical skeleton is documented as a shared reference in the design

## Affected Files

Commands (dispatch prompt reordering + resume pattern):
- `plugins/iflow/commands/specify.md` — spec-reviewer and phase-reviewer: add resume logic, reorder prompts
- `plugins/iflow/commands/design.md` — design-reviewer and phase-reviewer: add resume logic, reorder prompts
- `plugins/iflow/commands/create-plan.md` — plan-reviewer and phase-reviewer: add resume logic, reorder prompts
- `plugins/iflow/commands/create-tasks.md` — task-reviewer and phase-reviewer: add resume logic, reorder prompts
- `plugins/iflow/commands/implement.md` — steps 7a-7c reviewers + step 7e implementer: add resume logic, reorder prompts

No changes to skill files — `plugins/iflow/skills/specifying/SKILL.md` references `specify.md` for review dispatch but does not contain dispatch logic itself.

No agent file changes needed — system prompts are already static.

## Constraints

- **No behavioral regression**: Review approval/rejection logic remains identical. Only the dispatch mechanism (resume vs fresh) and prompt ordering change.
- **Feature 030 foundation**: All changes build on the existing lazy-load (R2) and pruning (R3) patterns. Do not regress to inline artifact injection.
- **Resume validation gate (R1.0)**: If ANY of V1-V4 tests fail, R1 is dropped and only R4 is implemented.
- **Preserve selective re-dispatch**: implement.md's per-reviewer `reviewer_status` tracking and selective re-dispatch of only failed reviewers must be preserved. Resume applies only to reviewers being re-dispatched.
- **Agent tool access unchanged**: No changes to agent frontmatter tool lists.
- **Assumption A1 acknowledged**: Cache benefit from resumed transcripts is an assumption based on Claude Code's documented caching behavior, not a verified guarantee. R1's primary measurable benefit is reduced prompt size (fewer characters sent). Cache cost savings are a secondary benefit that may or may not materialize.

## Non-Functional Requirements

- **NFR1**: Iteration 2+ resumed prompts must be shorter (by character count) than iteration 1 full prompts. Verify by comparing prompt strings in command template logic.
- **NFR2**: Track resume fallback events via `RESUME-FALLBACK` markers in `.review-history.md`. Acceptance criterion: a simulated resume failure (e.g., invalid agent_id) correctly writes a `RESUME-FALLBACK` marker to `.review-history.md`. The 20% threshold evaluation across 3 features is a post-deployment monitoring concern.
- **NFR3**: Total characters sent across a 5-iteration review loop with resume must be less than 50% of total characters sent across the same loop with 5 fresh dispatches. Computed from prompt template character counts, not from API-level token metrics (which are not observable from iflow's abstraction layer).

### Post-Deployment Monitoring

The following thresholds are evaluated after 3 features have used the new system:

| Metric | Threshold | Action |
|--------|-----------|--------|
| RESUME-FALLBACK rate | >20% of resume attempts | Escalate — resume may be fundamentally unreliable |
| Delta size guard trigger rate (phase commands) | >50% of phase command iterations | Adjust threshold or switch to full-artifact delta |
| LAZY-LOAD-WARNING rate (from feature 030) | >20% of dispatches | Re-evaluate mandatory-read directive |

## Risks

### Risk 1: Task Tool Resume Not Functional
**Likelihood**: Medium — multiple GitHub issues suggest resume may be broken or incomplete for tool-using agents.
**Mitigation**: R1.0 structured validation gate with 4 explicit pass/fail tests. If any fail, R1 is cleanly deferred.
**Impact if realized**: Only R4 is implemented. R4 delivers moderate value independently.

### Risk 2: Delta Size Guard Triggers Frequently for Phase Commands
**Likelihood**: Medium — phase command artifacts (spec, design, plan, tasks) are the primary content being reviewed. If revisions are extensive, the diff may exceed 50%.
**Mitigation**: Use unified diff format (R1.2) rather than full revised artifact. Diffs are typically much smaller than full files. If delta guard triggers >50% of the time in the first 3 features, adjust threshold or switch to full-artifact-as-delta for phase commands.
**Impact if realized**: Phase command review loops fall back to fresh dispatch. implement.md loops (where deltas are naturally smaller) still benefit.

### Risk 3: Cache TTL Expiration Between Selective Iterations
**Likelihood**: Medium — implement.md iterations can span 5-10 minutes when the implementer fix dispatch runs.
**Mitigation**: Resume still works after TTL expiration — it just costs more (cache miss). R1.9 documents this behavior. No functional impact, only cost impact.

## Test Strategy

- **Resume validation test (R1.0)**: Execute V1-V4 checklist before any implementation. Document results.
- **Annotation audit**: After changes, `grep -r "Fresh dispatch per iteration" plugins/iflow/` should return zero matches. All "Phase 1 behavior" annotations must be removed.
- **Resume pattern audit**: `grep -rn "resume:" plugins/iflow/commands/` should show resume usage in all 5 command files' review loops.
- **Prompt ordering audit**: For each command file, verify sections follow canonical skeleton: rubric → artifacts → schema → content → iteration context.
- **Fallback tracking test**: Trigger a resume with an invalid agent_id. Verify `.review-history.md` contains a correctly formatted `RESUME-FALLBACK` marker entry.
- **NFR3 validation**: For one command file (e.g., specify.md), compute total prompt character count for a hypothetical 5-iteration loop under both strategies: (a) 5 fresh dispatches using the I1 template, and (b) 1 fresh + 4 resumed dispatches using a representative delta size. Verify total characters for (b) is less than 50% of (a). Computable from template structure without running a live feature.
- **Manual end-to-end validation**: Run a feature through specify with a spec that has an intentional deficiency (e.g., missing acceptance criteria for one requirement) to trigger 2+ review iterations. Verify:
  - Iteration 1 dispatches fresh with full context
  - Iteration 2 uses `resume` with diff-only prompt
  - Review outcome quality is equivalent to fresh-dispatch behavior
  - `.review-history.md` contains no `RESUME-FALLBACK` entries (happy path)
