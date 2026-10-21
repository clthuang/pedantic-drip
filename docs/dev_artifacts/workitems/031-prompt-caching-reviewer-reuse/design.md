# Design: Prompt Caching & Reviewer Reuse

## Prior Art Research

### Codebase Patterns (from Stage 0 explorer)

- **Feature 030 foundation**: All 5 command files use the I1 lazy-load template from feature 030. Reviewer prompts emit file-path references; agents read via Read tool. Per-role artifact mapping (I4/I5) is in place.
- **Zero `resume:` usage**: No command or skill file uses the Task tool's `resume` parameter. All reviewer dispatches are fresh per iteration.
- **Current prompt section ordering varies by reviewer**:
  - spec-reviewer, design-reviewer: rubric → Required Artifacts → artifact content → iteration context → rubric coda → JSON schema
  - plan-reviewer: rubric → Required Artifacts → artifact content → JSON schema (no iteration context)
  - task-reviewer: rubric → Required Artifacts → artifact content → validate checklist → JSON schema (no iteration context)
  - implementation-reviewer: rubric → Required Artifacts → file list → validate levels → prose return instruction (no explicit JSON schema block, no iteration context)
  - code-quality-reviewer, security-reviewer: rubric → Required Artifacts → file list → check list → JSON schema (no iteration context)
  - phase-reviewer (all commands): rubric → Required Artifacts → domain outcome → next phase → iteration context → JSON schema
  In all cases, the JSON schema (where present) appears AFTER the artifact content — moving it above extends the stable prefix.
- **12 "Fresh dispatch per iteration" annotations**: 3 each in specify.md, design.md, create-plan.md, create-tasks.md. implement.md has zero such annotations. These are R1.8 removal targets.
- **implement.md selective dispatch**: Uses `reviewer_status` dict with `pending`/`passed`/`failed` values. Three reviewers (implementation, code-quality, security) with final validation round dispatching all three.
- **No git diff usage**: implement.md does not currently use git diff for detecting changes between iterations.
- **Agent system prompts are static**: All agent .md files contain fixed instructions with no dynamic content — cache sharing across same-type dispatches already works.

### External Research (from Stage 0 researcher)

- **Claude Code automatic prompt caching**: Cache breakpoints placed on conversation turns. Minimum 1,024 tokens for Opus/Sonnet. TTL: 5 min (Pro plan), 1 hour (Max plan). Cache reads at 0.1x; writes at 1.25x.
- **Resume mechanics**: `resume` re-sends the full prior transcript as a cacheable prefix. If within TTL, those tokens are served at 0.1x cost.
- **GitHub issue status**:
  - #10864 (agent_id not returned for sync dispatches): **Fixed in v2.0.28**
  - #11712 (user prompts missing in transcripts on resume): **Fixed in v2.0.43**
  - #11892 (stateless guidance contradicts resume): **Fixed**
  - #13619 (400 errors resuming tool-using agents): **Closed as duplicate** — no confirmed fix for tool_use_id mismatch
  - v2.1.20 mentions "subagent resume" improvements
- **Official resume guidance**: "Provide MINIMAL context in resume prompt" — aligns with R1.2 delta-only design.

### Design Implications

The R1.0 validation gate is critical — #13619's fix status is ambiguous. R4 (prompt reordering) delivers value independently. R1 (resume) is gated behind R1.0 validation. The design structures implementation so R4 can proceed regardless of R1.0 outcome.

---

## Architecture Overview

### Execution Flow

```
R1.0 Validation Gate (prerequisite)
    │
    ├── ALL V1-V4 PASS → Implement R1 + R4
    │
    └── ANY V1-V4 FAIL → Implement R4 only
                          Document failure in .meta.json
```

### R4: Prompt Structure Reordering (Independent)

**Guiding Principle**: All static content (role description, rubric, rubric coda, Required Artifacts block, validate/check lists, JSON return schema) MUST appear at the TOP of every dispatch prompt. All dynamic content (artifact-under-review content, iteration context, domain reviewer outcome, file lists that change) MUST appear at the BOTTOM. This maximizes the cache-hit prefix between iterations of the same agent type.

**Goal**: Move the JSON return schema block and all other static instructions above dynamic content (artifact-under-review, iteration context) so the stable prefix is maximized for cache hits across iterations.

```
BEFORE (typical, feature 030):               AFTER (R4.1):
┌──────────────────────────────┐              ┌──────────────────────────────┐
│ 1. Role + Rubric             │ ← stable     │ 1. Role + Rubric             │ ← stable
│ 2. Required Artifacts block  │ ← stable     │ 2. Required Artifacts block  │ ← stable
│ 3. Artifact-under-review     │ ← DYNAMIC    │ 3. JSON Return Schema        │ ← stable ★
│ 4. JSON Return Schema        │ ← stable     │ 4. Artifact-under-review     │ ← DYNAMIC
└──────────────────────────────┘              │ 5. Iteration Context         │ ← DYNAMIC
                                              └──────────────────────────────┘
                                               ↑ stable prefix is now 3 sections
                                                 instead of 2, improving cache hits
```

**Per-reviewer R4 transformation** (actual current structure → target):

| Reviewer | Current Order | R4 Reordered (static top, dynamic bottom) |
|----------|--------------|-------------------------------------------|
| spec-reviewer | rubric → artifacts → **content → iter context → rubric coda → JSON** | rubric → **rubric coda** → artifacts → **JSON** → content → iter context |
| design-reviewer | rubric → artifacts → **content → iter context → rubric coda → JSON** | rubric → **rubric coda** → artifacts → **JSON** → content → iter context |
| plan-reviewer | rubric → artifacts → **content → JSON** | rubric → artifacts → **JSON** → content |
| task-reviewer | rubric → artifacts → **content → validate checklist → JSON** | rubric → artifacts → **validate checklist → JSON** → content |
| implementation-reviewer | rubric → artifacts → **file list → validate levels → prose return** | rubric → artifacts → **validate levels → JSON (new)** → file list |
| code-quality-reviewer | rubric → artifacts → **file list → check list → JSON** | rubric → artifacts → **check list → JSON** → file list |
| security-reviewer | rubric → artifacts → **file list → check list → JSON** | rubric → artifacts → **check list → JSON** → file list |
| phase-reviewer (all) | rubric → artifacts → **domain outcome → next phase → iter context → JSON** | rubric → artifacts → **next phase → JSON** → domain outcome → iter context |

**Bold** = sections that change position. All static instructions (rubric, rubric coda, artifacts, validate/check lists, JSON schema, next phase expectations) are above the line; all dynamic content (artifact content, file lists, iteration context, domain outcome) is below.

**Applies to**: All fresh dispatch prompts (iteration 1 and fallback dispatches). Does NOT apply to resumed dispatches (R1, iteration 2+), which are inherently delta-only.

**Token count estimate**: For a typical design-reviewer prompt, the stable prefix (rubric ~150 tokens + Required Artifacts block ~80 tokens + JSON schema ~100 tokens) totals ~330 tokens. This is below the 1,024-token minimum for automatic cache breakpoints. However, Claude Code places cache breakpoints on conversation turns, not on prompt subsections — the entire subagent system prompt (~2,000+ tokens) is cached separately. R4's benefit is that when the same agent type is dispatched multiple times in a loop, more of the dispatch prompt matches between calls, improving cache hit rate on the user-message portion of the API call. The primary measurable benefit is reduced token cost for fresh dispatches of the same agent type within a single review loop.

### R1: Agent Reuse via Resume (Gated)

**Prerequisite**: R1.0 validation passes all V1-V4 tests.

```
Review Loop (per command file):

Iteration 1:
  ┌─────────────────────────────────┐
  │ Fresh dispatch (I1 template)    │
  │ Full context: rubric + artifacts│
  │ + schema + artifact content     │
  │ + iteration context             │
  └─────────┬───────────────────────┘
            │ capture agent_id → resume_state[role]
            ▼
Iteration 2+:
  ┌─────────────────────────────────┐
  │ Delta size check:               │
  │ delta_chars > 50% of I1 chars?  │
  │                                 │
  │ YES → Fresh dispatch (I1)       │
  │        reset resume_state[role] │
  │                                 │
  │ NO  → Resume dispatch (I2)      │
  │        Task({resume: agent_id,  │
  │              prompt: delta})     │
  └─────────┬───────────────────────┘
            │ on error → I3 fallback
            │            log RESUME-FALLBACK
            ▼
  ┌─────────────────────────────────┐
  │ Parse JSON result               │
  │ Branch: pass/fail               │
  └─────────────────────────────────┘
```

### R1 in implement.md (Selective Re-dispatch)

implement.md has a unique pattern: three reviewers with selective re-dispatch. Resume interacts with this as follows:

```
Iteration 1: Dispatch all 3 reviewers fresh → store 3 agent_ids
    │
Iteration 2+: Only failed reviewers re-dispatched
    │   ├── Resume with delta (git diff + fix summary)
    │   └── Passed reviewers: keep agent_id, do NOT dispatch
    │
Final Validation: All 3 re-dispatched
    │   ├── Each reviewer: attempt resume with since-last-review summary
    │   └── On resume error: fallback to fresh (I3)
    │
Edge case: Final validation catches regression
    │   ├── Failed reviewer re-enters fix cycle
    │   └── Its agent_id is preserved for next resume attempt
```

### Components

**C1: Prompt Template Layer** (command .md files)
- Reorders sections per R4.1 canonical skeleton
- Adds resume logic for iteration 2+ dispatches
- Manages `resume_state` dict lifecycle
- Generates deltas (text diff for phase commands, git diff for implement)

**C2: Validation Gate** (R1.0)
- Executes V1-V4 structured validation before any R1 changes
- Documents results in `.meta.json`
- Gates R1 implementation

**C3: Delta Generation** (R1.2)
- **Phase commands (R1.2a)**: After revision, `git add` + `git commit` creates diff anchor, then `git diff {last_commit_sha} HEAD -- {artifact}` computes the delta. See TD2.
- **Implement command (R1.2b)**: After implementer fix, `git add -A` + `git commit` creates diff anchor, then `git diff {last_commit_sha} HEAD` for all changed files. See TD2.

**C4: Resume Orchestration** (R1.1, R1.3, R1.6)
- Stores agent_id after iteration 1
- Constructs resumed prompts with delta-only content
- Implements fallback to fresh dispatch on error
- Logs RESUME-FALLBACK markers

---

## Technical Decisions

### TD1: R4 Before R1 in Implementation Order

**Decision**: Implement R4 (prompt reordering) first, across all 5 command files. Then implement R1 (resume) if R1.0 passes.
**Rationale**: R4 is independent and risk-free — it only reorders existing sections. R1 is gated behind validation. If R1.0 fails, R4 still delivers value. If R1.0 passes, R4's reordered templates become the new I1 baseline that I3 (fallback) uses.

### TD2: Git Commit + Git Diff for All Deltas (R1.2a + R1.2b Unified)

**Decision**: After every artifact revision (both phase command artifacts and implement.md code fixes), the orchestrator commits changes via Bash tool: `git add {artifact_path} && git commit -m "iflow: {phase} review iteration {n}"`. Then computes the delta via `git diff {last_commit_sha} HEAD -- {paths}` (where `last_commit_sha` is the SHA stored after the previous iteration's commit). This unified approach applies to both phase commands (R1.2a) and implement.md (R1.2b).

**Rationale**: The spec (R1.2a) prefers "the simplest available mechanism: if the artifact content is already held in a variable at revision time, use in-memory string comparison." However, the orchestrator is an LLM following markdown instructions — it cannot programmatically compute diffs or hold variables. The Bash tool with `git diff` is the simplest mechanism available to an LLM-based orchestrator. Using git for both phase commands and implement.md unifies the approach (no separate temp file management). Per-iteration commits create reliable diff anchors and integrate naturally with the git workflow.

**Mechanism for phase commands (R1.2a)**: Each command file's review loop adds explicit steps after the orchestrator revises the artifact:
  1. After revision: `Bash: git add {feature_path}/{artifact}.md && git diff --cached --quiet && echo "NO_CHANGES" || git commit -m "iflow: {phase} review iteration {n}"`
  2. If NO_CHANGES: no commit created, delta is empty — proceed with fresh dispatch (no meaningful delta to resume with). Reset `resume_state[role]` since the fresh dispatch creates a new agent context.
  3. If committed: capture `new_sha=$(git rev-parse HEAD)`. Compute delta: `Bash: git diff {last_commit_sha} HEAD -- {feature_path}/{artifact}.md` — capture output as `delta_content`. Update `resume_state[role].last_commit_sha = new_sha`.

**Mechanism for implement.md (R1.2b)**: After each implementer fix dispatch completes:
  1. Commit fixes: `Bash: git add -A && git diff --cached --quiet && echo "NO_CHANGES" || git commit -m "iflow: implement review iteration {n} fixes"`
  2. If NO_CHANGES: fall back to fresh dispatch.
  3. If committed: capture `new_sha=$(git rev-parse HEAD)`. Compute delta: `Bash: git diff {last_commit_sha} HEAD --stat && git diff {last_commit_sha} HEAD` — both stat summary and full diff as `delta_content`. Update `resume_state[role].last_commit_sha = new_sha`.

**Fallback**: If git commit or diff fails (actual error, not "no changes"), fall back to fresh dispatch. The delta size guard also applies — if diff output exceeds 50% of iteration 1 prompt length, use fresh dispatch. If the orchestrator loses a stored SHA due to context compaction mid-loop, the delta cannot be computed — fall back to fresh dispatch (I3). This is self-correcting: the I3 fallback re-establishes a baseline for subsequent iterations.

**Working commits**: These per-iteration commits are working commits that will appear in the merge history. The finish-feature command uses `git merge` (not `--squash`), so they persist as individual commits. This is acceptable — they provide an audit trail of the review-fix cycle, similar to the existing `wip:` commits that finish-feature already creates. If squashing is desired in the future, that is a finish-feature change (out of scope for this feature).

*Note: TD3 was merged into TD2 during design review iteration 1 (originally "Per-Iteration Git Commits" — now unified with TD2's git-based delta approach).*

### TD4: Resume State Lifecycle Spans Full Review Loop

**Decision**: The `resume_state` dict persists across all iterations of a command's review loop (including final validation in implement.md). It is NOT reset between iterations unless a fresh dispatch replaces a resume.
**Rationale**: R1.9 requires that previously-passing reviewers can be resumed for final validation. Their agent_ids must survive intermediate iterations where they were not dispatched.
**Scope**: `resume_state` is local to a single command execution — not persisted to disk or `.meta.json`. If the session crashes mid-loop, fresh dispatches resume naturally (no stale state).
**Reset on rerun**: When the user selects "Fix and rerun reviews" (resetting iteration counters to 0), `resume_state` is also reset. The re-run starts with fresh dispatches since the user has made manual edits outside the review loop.

### TD5: 50% Delta Size Threshold (Carried Forward)

**Decision**: If delta character count exceeds 50% of the iteration 1 prompt character count, fall back to fresh dispatch.
**Rationale**: Carried forward from feature 030's spec. At 50% delta, the resumed prompt is at worst half the cost of fresh. Conservative threshold — revisable based on post-deployment monitoring.
**Measurement**: Compare `len(delta_prompt)` against `resume_state[role].iteration1_prompt_length`.

### TD6: Resumed Prompts Omit Required Artifacts Block

**Decision**: Iteration 2+ resumed prompts do NOT re-list the Required Artifacts block. They begin with the delta context directive.
**Rationale**: The agent already has all artifact content in its transcript from iteration 1. Re-listing paths would trigger redundant Read tool calls. The official guidance ("provide MINIMAL context in resume prompt") supports this.
**Exception**: If a fresh fallback (I3) is triggered, the full I1 template (including Required Artifacts) is used.

### TD7: RESUME-FALLBACK Logging Format

**Decision**: Resume failures are logged to `.review-history.md` with the format: `RESUME-FALLBACK: {agent_role} iteration {n} — {error summary}`. This is appended as a standalone line within the current iteration's review history entry.
**Rationale**: Consistent with feature 030's LAZY-LOAD-WARNING pattern. Enables post-deployment monitoring via `grep -r "RESUME-FALLBACK" docs/features/*/.review-history.md | wc -l`.

### TD8: Canonical Skeleton Documented as Shared Reference

**Decision**: The R4.1 canonical skeleton is defined once in this design as interface I1-R4 (updated I1). All 5 command files reference this skeleton.
**Rationale**: Avoids duplication drift. The spec requires the skeleton to be "documented as a shared reference in the design." Each command file's dispatch prompt follows the skeleton; deviations are documented per-command.

---

## Risks

### Risk 1: R1.0 Validation Fails (Resume Not Functional)

**Likelihood**: Medium — #13619 closed but fix unconfirmed.
**Impact**: R1 is dropped. Only R4 is implemented. R4 delivers moderate value independently.
**Mitigation**: R1.0 is the first implementation task. Clean decision gate — no wasted effort.

### Risk 2: Delta Size Guard Triggers Frequently for Phase Commands

**Likelihood**: Medium — large revisions to spec/design may exceed 50%.
**Impact**: Phase command review loops fall back to fresh dispatch (no resume benefit, but no regression).
**Mitigation**: Unified diff format compresses changes. Post-deployment monitoring tracks trigger rate.

### Risk 3: Cache TTL Expiration Between Selective Iterations

**Likelihood**: Medium — implement.md iterations can span 5-10 minutes.
**Impact**: Resume still works (cache miss = full input cost, not an error).
**Mitigation**: No action needed — resume is still cheaper than fresh dispatch (avoids re-reading artifacts via Read tool).

### Risk 4: Context Compression Loses Pre-Revision Content

**Likelihood**: Low — only affects very long review loops (4+ iterations with large artifacts).
**Impact**: Cannot compute delta → fresh dispatch fallback.
**Mitigation**: Delta size guard naturally handles this — if pre-revision content is lost, delta is unmeasurable, triggering fresh dispatch.

---

## Interfaces

### I1-R4: Canonical Reviewer Dispatch Template (Fresh, R4-Reordered)

Supersedes feature 030's I1. Used by all fresh dispatches (iteration 1 + fallback).

```
Task tool call:
  description: "{review description}"
  subagent_type: {agent_type}
  model: {model}
  prompt: |
    --- STABLE PREFIX (same across all iterations of this agent type) ---

    {review task description and rubric — unique per agent}

    {rubric coda if applicable: "Your job: Find weaknesses before X does.
    Be the skeptic. Challenge assumptions. Find gaps."}

    ## Required Artifacts
    You MUST read the following files before beginning your review.
    After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
    {for each artifact in ARTIFACT_MAP[agent_type]:}
    {  resolved_path = resolve_prd(artifact) if artifact == "prd.md" else feature_path/artifact}
    {  if resolved_path is "NONE": emit "- PRD: No PRD — feature created without brainstorm"}
    {  else: emit "- {Artifact Name}: {resolved_path}"}

    {validate/check list if applicable:
      e.g., "Validate all 4 levels: ..."
      or "Check: Readability, KISS, YAGNI, ..."
      — these are static per agent type, part of stable prefix}

    Return your assessment as JSON:
    {per-agent JSON schema — see deviations below}

    --- DYNAMIC SUFFIX (changes per iteration) ---

    ## {Artifact-Under-Review Header}
    {For phase commands: content of the artifact being reviewed (spec.md, design.md, etc.)}
    {For implement.md: "## Implementation Files\n{list of files with code}"}

    ## Iteration Context  {if applicable — some reviewers omit this}
    This is iteration {n} of {max}.
    {if n > 1: "Previous issues to re-evaluate:\n{issue list from previous iteration}"}
```

**Key changes from 030-I1**:
1. JSON return schema moved from after dynamic content to after Required Artifacts block — extends stable prefix.
2. Rubric coda ("Your job: Find weaknesses...") moved from after artifact content to section 1 — part of stable prefix.
3. Validate/check lists moved above artifact content — part of stable prefix.
4. All static instructions now precede all dynamic content — maximizes cache-hit prefix between iterations.

**Per-command deviations**:
- **specify.md** spec-reviewer: No Required Artifacts for spec.md itself (it IS the artifact-under-review, included inline). PRD is the only Required Artifact. Rubric coda ("Your job: Find weaknesses...") moves into section 1 (stable prefix), before JSON schema.
- **specify.md/design.md** domain reviewers: Have a rubric coda ("Your job: Find weaknesses. Be the skeptic. Challenge assumptions. Find gaps.") that currently appears AFTER artifact content. In R4, this moves into section 1 (role + rubric) as part of the stable prefix. Note: design-reviewer's dispatch prompt uses `"suggestion"` as the issue field name, while the design-reviewer agent itself uses `"challenge"` in its responses — this is a pre-existing inconsistency. R4 preserves the dispatch prompt's `"suggestion"` field name for consistency with all other reviewers.
- **plan-reviewer**: JSON schema is compact single-line format (`{approved, issues, summary}`); no `"category"` field in issues; no Iteration Context section.
- **task-reviewer**: JSON schema uses `"task"` field instead of `"location"` in issues; no `"category"` field; has validate checklist (plan fidelity, executability, size, dependencies, testability) that is stable — moves above dynamic content.
- **implementation-reviewer**: Has NO explicit JSON schema block — currently uses prose instruction ("Return JSON with approval status, level results, issues, and evidence."). R4 adds an explicit JSON schema block matching the prose expectation. Also has "Validate all 4 levels" instructions after the rubric — these are stable prefix content.
- **code-quality-reviewer**: Has `"category"` values specific to quality (`readability|kiss|yagni|formatting|flow`). Check list is stable — moves above file list.
- **security-reviewer**: Has `"category"` values specific to security (`injection|auth|crypto|exposure|config`). Check list is stable — moves above file list.
- **phase-reviewer** (all commands): "Next Phase Expectations" is static (same text every iteration) — moves to stable prefix. "Domain Reviewer Outcome" is dynamic (reviewer result changes each iteration). JSON schema and "Next Phase Expectations" appear before the dynamic "Domain Reviewer Outcome" and "Iteration Context" sections.
- **implement.md** reviewers: "Implementation Files" section replaces "Artifact-Under-Review" section. File list is inline (agents read files themselves).

### I2: Resumed Reviewer Prompt Template (R1, Iteration 2+)

Used when: resume_state[role].agent_id exists AND delta_chars <= 50% of iteration1_prompt_length.

```
Task tool call:
  resume: {resume_state[role].agent_id}
  prompt: |
    You already have the upstream artifacts and the previous version of
    {artifact_name} in context from your prior review.

    The following changes were made to address your previous issues:

    ## Delta
    {R1.2a for phase commands: git diff {last_commit_sha} HEAD -- {artifact}.md output}
    {R1.2b for implement.md: git diff {last_commit_sha} HEAD --stat + git diff {last_commit_sha} HEAD output}

    ## Fix Summary
    {orchestrator revision summary (phase commands) OR implementer fix summary text (implement.md)}

    Review the changes above. Assess whether your previous issues are resolved
    and check for new issues introduced by the fixes.

    This is iteration {n} of {max}.

    Return your assessment as JSON:
    {
      "approved": true/false,
      "issues": [{"severity": "blocker|warning|suggestion", "category": "...", "description": "...", "location": "...", "suggestion": "..."}],
      "summary": "..."
    }
```

**Key properties**:
- NO Required Artifacts block (agent already has files in transcript)
- NO rubric repetition (agent already has it from iteration 1)
- Delta content is the primary payload
- JSON schema is repeated (small, ensures correct output format)

### I2-FV: Resumed Prompt for Final Validation (implement.md R1.9)

Used when: a previously-passing reviewer is resumed for final validation round.

**Delta size guard**: The 50% threshold (TD5) does NOT apply to I2-FV. Final validation is mandatory — if the diff since the reviewer's last review is large, the reviewer still needs to see it. If resume fails (R1.6 error), fall back to I3 (fresh dispatch with full context).

```
Task tool call:
  resume: {resume_state[role].agent_id}
  prompt: |
    You already have the upstream artifacts and implementation files
    in context from your prior review at iteration {resume_state[role].last_iteration}.

    Since your last review, the following fixes were applied to address
    issues from other reviewers:

    ## Changes Since Your Last Review
    {git diff --stat between last_iteration commit and current HEAD}
    {git diff between last_iteration commit and current HEAD}

    ## Fix Summary
    {consolidated fix summaries from all intermediate iterations}

    Perform a full regression check. Verify your previous approval still
    holds given these changes, and check for any new issues.

    This is the final validation round (iteration {n} of {max}).

    Return your assessment as JSON:
    {
      "approved": true/false,
      "issues": [{"severity": "blocker|warning|suggestion", "category": "...", "description": "...", "location": "...", "suggestion": "..."}],
      "summary": "..."
    }
```

### I3: Fresh Fallback Prompt Template (R1.6)

Used when: resume attempt fails (API/tool error from Task tool).

Identical to I1-R4 but with:
- Additional line in Iteration Context: `"(Fresh dispatch — prior review session unavailable.)"`
- Previous iteration issues included (same as I1-R4 iteration 2+ behavior)

```
## Iteration Context
This is iteration {n} of {max}.
(Fresh dispatch — prior review session unavailable.)
Previous issues to re-evaluate:
{issue list from previous iteration}
```

**Logging**: When I3 is triggered, append to `.review-history.md`:
`RESUME-FALLBACK: {agent_role} iteration {n} — {error summary}`

### I4: Per-Role Artifact Mapping (implement.md)

Unchanged from feature 030. Reproduced for completeness:

```
ARTIFACT_MAP = {
  "implementation-reviewer": ["prd.md", "spec.md", "design.md", "plan.md", "tasks.md"],
  "code-quality-reviewer":   ["design.md", "spec.md"],
  "security-reviewer":       ["design.md", "spec.md"],
  "code-simplifier":         ["design.md"],
  "test-deepener":           ["spec.md", "design.md", "tasks.md", "prd.md"],
  "implementer":             ["prd.md", "spec.md", "design.md", "plan.md", "tasks.md"]
}
```

### I5: Per-Role Artifact Mapping (phase commands)

Unchanged from feature 030. Reproduced for completeness:

```
# specify.md
ARTIFACT_MAP = {
  "spec-reviewer":  ["prd.md"],
  "phase-reviewer": ["prd.md", "spec.md"]
}

# design.md
ARTIFACT_MAP = {
  "design-reviewer": ["prd.md", "spec.md"],
  "phase-reviewer":  ["prd.md", "spec.md", "design.md"]
}

# create-plan.md
ARTIFACT_MAP = {
  "plan-reviewer":  ["prd.md", "spec.md", "design.md"],
  "phase-reviewer": ["prd.md", "spec.md", "design.md", "plan.md"]
}

# create-tasks.md
ARTIFACT_MAP = {
  "task-reviewer":  ["prd.md", "spec.md", "design.md", "plan.md"],
  "phase-reviewer": ["prd.md", "spec.md", "design.md", "plan.md", "tasks.md"]
}
```

### I6: Resume State Management

```
resume_state = {
  "{agent_role}": {
    "agent_id": "{returned from Task tool result}",
    "iteration1_prompt_length": {character count of first dispatch prompt},
    "last_iteration": {iteration number of last dispatch for this role},
    "last_commit_sha": "{git rev-parse HEAD after this role's last iteration commit}"
  }
}
```

The `last_commit_sha` field is used to compute git diffs:
- **Phase commands**: `git diff {last_commit_sha} HEAD -- {artifact}.md` produces the delta for resumed prompts (I2).
- **implement.md**: `git diff {last_commit_sha} HEAD` for I2 (iteration 2+) and I2-FV (final validation) — showing exactly what changed since the reviewer last saw the codebase.

**Lifecycle**:
- **Created**: After iteration 1 dispatch, populate with agent_id and prompt length. Capture `last_commit_sha` = current HEAD after the iteration's per-iteration commit (see TD2).
- **Updated**: After each subsequent dispatch of this role, update `last_iteration` and `last_commit_sha`.
- **Reset**: When a fresh dispatch replaces a resume (delta too large or fallback), replace the entry with new agent_id and prompt length.
- **Scope**: In-memory only, per review loop execution. NOT persisted to disk.

**Keys for phase commands**: `"spec-reviewer"`, `"phase-reviewer"`, `"design-reviewer"`, `"plan-reviewer"`, `"task-reviewer"`

**Keys for implement.md**: `"implementation-reviewer"`, `"code-quality-reviewer"`, `"security-reviewer"`, `"implementer"` (fix dispatch)

### I7: Implementer Fix Dispatch (Resume-Enabled)

Extends the existing implementer fix dispatch from implement.md Step 7e.

**Iteration 1 (fresh)**:
```
Task tool call:
  description: "Fix review issues iteration {n}"
  subagent_type: iflow:implementer
  model: opus
  prompt: |
    Fix the following review issues:

    ## Required Artifacts
    You MUST read the following files before beginning your work.
    After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
    {resolved PRD line from I8}
    - Spec: {feature_path}/spec.md
    - Design: {feature_path}/design.md
    - Plan: {feature_path}/plan.md
    - Tasks: {feature_path}/tasks.md

    ## All Implementation Files
    {complete list of all files assigned to this implementation task}

    ## Issues to Fix
    {consolidated issue list from failed reviewers}
```

**Iteration 2+ (resume)**:
```
Task tool call:
  resume: {resume_state["implementer"].agent_id}
  prompt: |
    You already have the upstream artifacts and implementation files
    in context from your previous fix session.

    ## New Issues to Fix
    {consolidated issue list from reviewers that failed THIS iteration}

    ## Changed Files to Re-read
    {list of files changed since last fix iteration — implementer should re-read these}

    ## All Implementation Files (for reference)
    {complete list of all files assigned to this implementation task}

    Fix all listed issues. After fixing, briefly summarize what you changed.
```

### I8: PRD Resolution Logic

Unchanged from feature 030. Used by all prompt templates when artifact mapping includes "prd.md".

### I9: Lazy-Load Fallback Detection

Unchanged from feature 030. Applied after receiving agent response, before parsing JSON.

### I10: R1.0 Validation Gate Protocol

Executed once before implementing any R1 changes. Must be the first implementation task.

```
Validation sequence:

V1: Dispatch spec-reviewer (foreground, synchronous)
    prompt: "Review this file: {path to spec.md}. List the first line verbatim."
    → PASS: Task result contains agent_id field
    → FAIL: No agent_id returned → R1 blocked

V2: Resume the agent
    Task({ resume: V1.agent_id, prompt: "Confirm you can still respond." })
    → PASS: No API error, agent responds
    → FAIL: 400/500 error → R1 blocked

V3: Context preservation test
    In the resume prompt: "Repeat verbatim the first line of the file you read."
    → PASS: Response matches the exact first line from V1's Read result
    → FAIL: Mismatch or no answer → R1 blocked

V4: Structured memory test
    "How many issues did you identify in your V1 review?"
    → PASS: Count matches actual number from V1 response
    → FAIL: Mismatch → R1 blocked
```

**Decision gate**: ALL four must pass. If ANY fail:
- Document failure in `.meta.json`: `"r1_deferred_reason": "{test_id}: {failure description}"`
- Proceed with R4-only implementation
- R1 tasks are skipped

### Template Selection Decision Matrix (implement.md)

implement.md has multiple dispatch scenarios. This matrix maps each scenario to the correct template:

| Scenario | Condition | Template | Notes |
|----------|-----------|----------|-------|
| Reviewer, iteration 1, all 3 | `iteration == 1` | I1-R4 (fresh, full context) | Store agent_id in resume_state |
| Reviewer, iteration 2+, failed only | `reviewer_status == "failed"` AND resume_state exists AND delta ≤ 50% | I2 (resumed, delta) | Delta = git diff from per-iteration commit |
| Reviewer, iteration 2+, delta too large | `reviewer_status == "failed"` AND delta > 50% | I1-R4 (fresh fallback) | Reset resume_state for this role |
| Reviewer, iteration 2+, resume error | Resume Task tool returns error | I3 (fresh fallback + log) | Log RESUME-FALLBACK, reset resume_state |
| Reviewer, final validation, passed | `is_final_validation` AND `reviewer_status == "passed"` | I2-FV (resumed, since-last diff) | Uses last_commit_sha for diff range |
| Reviewer, final validation, resume error | I2-FV resume fails | I3 (fresh fallback + log) | Full I1-R4 with fresh context |
| Implementer fix, iteration 1 | First fix dispatch | I7 fresh (full context) | Store agent_id |
| Implementer fix, iteration 2+ | Subsequent fix AND delta ≤ 50% | I7 resumed (new issues + changed files) | Delta = new issue list |
| Implementer fix, delta too large | Subsequent fix AND delta > 50% | I7 fresh (full context) | Reset resume_state for implementer |

---

## Agent Context Changes

Per feature 030 retro recommendation (require Behavioral Change Table):

| Agent | Change | Rationale |
|-------|--------|-----------|
| All reviewers | Iteration 2+ receives delta-only prompt via resume instead of full context | Prior transcript provides full context; delta is sufficient for re-evaluation |
| All reviewers | JSON schema moves before artifact content in fresh dispatches | Extends stable cache prefix; no change to schema content |
| Implementer (fix) | Iteration 2+ receives issue list + changed file paths via resume | Prior transcript has all artifacts; only new issues and changed paths needed |
| Phase-reviewer (final validation) | Receives since-last-review diff summary via resume | Needs awareness of changes since its passing review |

**No behavioral change**: Review approval/rejection logic, JSON schema format, strict threshold rules, selective re-dispatch logic — all unchanged.

---

## File Change Summary

| File | Changes |
|------|---------|
| `plugins/iflow/commands/specify.md` | R4: reorder spec-reviewer and phase-reviewer prompts (static at top, dynamic at bottom). R1: add resume_state tracking, resume logic for iteration 2+ in both Stage 1 and Stage 2 loops. Remove "Fresh dispatch per iteration" annotations (3 sites). Add per-iteration git commit + git diff for R1.2a delta. |
| `plugins/iflow/commands/design.md` | R4: reorder design-reviewer (Stage 3) and phase-reviewer (Stage 4) prompts (static at top, dynamic at bottom). R1: add resume logic for both review loops. Remove "Fresh dispatch per iteration" annotations (3 sites). Add per-iteration git commit + git diff for R1.2a delta. |
| `plugins/iflow/commands/create-plan.md` | R4: reorder plan-reviewer (Stage 1) and phase-reviewer (Stage 2) prompts (static at top, dynamic at bottom). R1: add resume logic for both review loops. Remove "Fresh dispatch per iteration" annotations (3 sites). Add per-iteration git commit + git diff for R1.2a delta. |
| `plugins/iflow/commands/create-tasks.md` | R4: reorder task-reviewer (Stage 1) and phase-reviewer (Stage 2) prompts (static at top, dynamic at bottom). R1: add resume logic for both review loops. Remove "Fresh dispatch per iteration" annotations (3 sites). Add per-iteration git commit + git diff for R1.2a delta. |
| `plugins/iflow/commands/implement.md` | R4: reorder 7a/7b/7c reviewer prompts + 7e implementer fix prompt (move JSON schema and check lists/validate levels above file lists). R4: add explicit JSON schema block to implementation-reviewer (7a) replacing prose instruction. R1: add resume_state tracking across selective re-dispatch, resume logic for iteration 2+ reviewer dispatches, resume logic for implementer fix dispatch (R1.5), final validation resume (R1.9). Add per-iteration git commit + git diff capture for R1.2b delta. |

| `{feature_path}/.meta.json` | R1.0: Add `r1_deferred_reason` field if any V1-V4 test fails. No changes if R1.0 passes. |

**No changes to**:
- Agent `.md` files (system prompts already static)
- `plugins/iflow/skills/implementing/SKILL.md` (per-task dispatch is not a review loop — no resume applicable)
- `plugins/iflow/skills/brainstorming/SKILL.md` (excluded from scope)
- Stage 0 research dispatches in design.md (single dispatch, not a review loop)

### Implementation Sequence

1. **R1.0 validation gate** — execute V1-V4 tests. Gate decision.
2. **R4 prompt reordering** — all 5 command files, independent of R1.0 outcome.
3. **R1 resume logic** — all 5 command files. **Only if R1.0 passes.** If R1.0 fails: skip step 3, proceed with steps 2, 4, 5 only.
4. **Annotation cleanup** — remove all "Fresh dispatch per iteration" annotations. (Applies regardless of R1.0 outcome — annotations reference "Phase 2" which is this feature.)
5. **Verification** — grep audits, prompt ordering audits, NFR3 validation.
