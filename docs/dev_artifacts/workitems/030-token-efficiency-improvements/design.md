# Design: Token Efficiency Improvements

## Prior Art Research

### Codebase Patterns
- **Full artifact injection is universal**: Every command template uses `{content of <file>.md}` placeholders. No lazy-load or reference pattern exists for artifact documents.
- **Implementation files already use file-list references**: Reviewer prompts pass `{list of files with code}` and agents read files themselves — this is the existing analog to lazy-load.
- **extractSection() is the only scoping mechanism**: The implementing skill extracts relevant plan.md/design.md sections per task via traceability references. PRD is already section-scoped (Problem Statement + Goals only).
- **All reviewer agents have Read tool**: Every reviewer (implementation, code-quality, security, spec, design, task, phase) declares Read, Glob, Grep in frontmatter tools.
- **No `resume` usage exists**: Zero commands use the Task tool's resume parameter.
- **PRD source is conditional**: Commands use `{content of prd.md, or "None - feature created without brainstorm"}`. Features from brainstorms have PRD copied to the feature directory; features without brainstorm have no prd.md.

### Industry Patterns
- **Google ADK**: Uses "ephemeral expansion" — agents receive lightweight artifact references and call LoadArtifactsTool on demand. Sub-agents scoped via `include_contents`.
- **LangGraph**: Passes only state deltas between graph nodes (most token-efficient framework).
- **AutoGen**: Provides TransformMessages with token limiters and uses "carryover" summaries for sequential chats.
- **Progressive context loading**: Demonstrated 98% token reduction (150K → 2K) by loading context on demand via routing matrix.

### Design Implications
Our approach aligns with Google ADK's ephemeral expansion. The implementation is **phased**: R2 (lazy-load) + R3 (pruning) deliver value immediately. R1 (resume) is decoupled and contingent on Task tool resume reliability (see Risk 2).

---

## Architecture Overview

### Implementation Phases

**Phase 1 (this feature)**: R2 (Lazy-Load References) + R3 (Role-Specific Pruning)
- Replaces all `{content of X.md}` injection with file-path reference blocks
- Applies per-role artifact mapping
- Delivers token savings from eliminating redundant artifact embedding
- Every review iteration still dispatches a fresh agent (current behavior preserved)

**Phase 2 (future, contingent)**: R1 (Agent Reuse via Resume)
- Requires validation that Task tool `resume` works with tool-using agents
- Known issue: GitHub #13619 documents 400 errors when resuming agents that used tools
- Phase 2 is NOT implemented in this feature. Design interfaces are defined for forward compatibility but the `resume` logic is not added to command templates
- Gate: Before Phase 2 implementation, run a validation test (dispatch a reviewer with Read tool, capture agent_id, attempt resume). If it fails, defer R1 indefinitely
- **Phase 2 does not require plan tasks in this feature** — it is a separate future feature contingent on the resume validation gate. I2, I3, and I6 are documentation-only forward-compatibility definitions

### Current Architecture (Before)

```
Orchestrator (command template)
    │
    ├── Read prd.md     ──→ embed full content in prompt
    ├── Read spec.md    ──→ embed full content in prompt
    ├── Read design.md  ──→ embed full content in prompt
    ├── Read plan.md    ──→ embed full content in prompt
    ├── Read tasks.md   ──→ embed full content in prompt
    │
    └── Task({ prompt: "[all content]", subagent_type: "reviewer" })
        └── NEW agent per iteration (no state reuse)
```

### Phase 1 Architecture (After)

```
Orchestrator (command template)
    │
    ├── Resolve PRD source (prd.md or brainstorm file or "None")
    ├── Look up per-role artifact mapping
    │
    └── Task({ prompt: "[artifact paths + mandatory-read + role-specific list]" })
        ├── Agent reads ONLY its required files via Read tool
        └── Fresh dispatch each iteration (same as current)
```

### Phase 2 Architecture (Future — NOT implemented now)

```
Orchestrator (command template)
    │
    ├── Iteration 1: same as Phase 1
    │   └── Store agent_id from result
    │
    ├── Iteration 2+: Resume with delta
    │   └── Task({ resume: agent_id, prompt: "[diff + fix summary]" })
    │
    └── Fallback: If resume fails → fresh dispatch (Phase 1 template)
```

### Components

**C1: Prompt Template Layer** (command .md files) — Phase 1
- Transforms `{content of X.md}` inline blocks into file-reference blocks
- Applies R3 per-role pruning (different artifact sets per reviewer)
- Resolves PRD source conditionally (see I8)

**C2: Implementing Skill Hybrid Layer** (implementing/SKILL.md) — Phase 1
- Retains extractSection() for plan.md and design.md per-task scoping
- Converts spec.md to mandatory-read reference; prd.md to mandatory-read reference
- Preserves inline task description and file lists

**C3: Resume Orchestration Logic** — Phase 2 (deferred)
- Stores agent_id, constructs delta prompts, implements fallback
- NOT included in Phase 1 implementation

### Excluded from Scope

- **`plugins/iflow/skills/brainstorming/SKILL.md`**: The brainstorming skill's prd-reviewer and brainstorm-reviewer dispatches are excluded. These are lightweight, single-artifact reviews (the PRD being drafted) where token savings from lazy-load are minimal — the PRD is the artifact being written, not an upstream reference.
- **Stage 0 research agents in `design.md`**: codebase-explorer and internet-researcher receive feature description summaries, not full artifact content. No changes needed.

---

## Technical Decisions

### TD1: Mandatory-Read Directive over Optional Reference
**Decision**: Prompts say "You MUST read the following files" with confirmation, not "files are available if needed."
**Rationale**: LLM agents may skip optional reads. The confirmation directive ("state file names and line counts") forces the Read tool call. Aligned with Google ADK's pattern.
**Tradeoff**: Adds ~1 line to each agent response for confirmation. Acceptable vs risk of incomplete reviews.

### TD2: Conditional PRD Resolution
**Decision**: Before emitting artifact references, the orchestrating command checks whether prd.md exists at the feature path. If not, it emits an inline note: "No PRD — feature created without brainstorm" instead of a file reference.
**Rationale**: Features created via `/iflow:create-feature` (without brainstorm) have no prd.md. Current templates use `{content of prd.md, or "None - feature created without brainstorm"}` — this conditional must be preserved.
**Implementation**: See I8 (PRD Resolution Logic).

### TD3: File References Use Absolute Paths
**Decision**: Artifact paths in prompts use absolute paths resolved from the feature directory.
**Rationale**: Agents need absolute paths for the Read tool. The orchestrating agent resolves from `.meta.json` or the active feature directory, same as current behavior.

### TD4: Preserve extractSection() for Implementer Dispatches
**Decision**: The implementing skill's per-task extractSection() for plan.md and design.md is retained. Spec.md and prd.md convert to mandatory-read lazy-load.
**Rationale**: extractSection() scopes to the relevant section per task — more efficient than N agents each reading the full file. For 10 tasks, this avoids 10 full-file reads.
**N-reads tradeoff**: spec.md and prd.md are read in full by each per-task implementer dispatch (no per-task section structure exists for these). File sizes are typically small (spec: ~200 lines, PRD: ~100 lines), making the N-reads overhead acceptable.

### TD5b: R3 Pruning is an Intentional Behavioral Adjustment
**Decision**: R3 (per-role pruning) changes the content available to some reviewers, not just the transport mechanism. This is distinct from R2 (which is transport-only).
**Changes**: (1) code-simplifier loses spec.md context (YAGNI checks rely on design patterns only). (2) test-deepener receives full PRD instead of section-scoped Problem Statement + Goals — this expands context marginally but simplifies the lazy-load pattern by avoiding extractSection for PRD.
**Rationale**: The spec's constraint "No behavioral regression: Review approval/rejection logic must remain identical" applies to R2's transport change. R3's pruning is an intentional context adjustment per the spec's R3.1 table. If pruning degrades review quality, expand artifact sets per NFR2 tracking.

### TD5: Consistent Mandatory Language in I7
**Decision**: The implementer skill dispatch (I7) uses "You MUST read" for spec.md and prd.md, consistent with TD1. The current "always loaded in full" behavior for spec.md converts to mandatory lazy-load read.
**Rationale**: Consistency across all dispatch sites. The implementer needs spec context for acceptance criteria validation, so it MUST read spec.md — optional language would risk skipped reads.

---

## Risks

### Risk 1: Agent Ignores Mandatory-Read Directive
**Likelihood**: Low.
**Mitigation**: Confirmation directive forces acknowledgment. If the orchestrating command detects the reviewer response lacks confirmation, log a `LAZY-LOAD-WARNING` entry in `.review-history.md`. The adversarial review loop catches incomplete reviews.
**Fallback**: Not automated — rely on review quality gates.

### Risk 2: Task Tool `resume` Bug (#13619)
**Likelihood**: High — GitHub issue #13619 (Dec 2025) documents 400 errors when resuming agents that used tools. Every iflow reviewer uses Read/Glob/Grep.
**Mitigation**: R1 (resume) is deferred to Phase 2, contingent on bug resolution. Phase 1 delivers value independently via R2+R3.
**Gate**: Before Phase 2, validate with a manual test: dispatch reviewer → capture agent_id → resume. If it fails, R1 is permanently deferred.

### Risk 3: Pruned Artifacts Miss Relevant Context
**Likelihood**: Low-Medium.
**Mitigation**: Conservative pruning — security-reviewer and code-quality-reviewer still get Design + Spec. Only Plan and Tasks are pruned from these roles. Implementation-reviewer retains full chain.
**Fallback**: If review quality degrades, expand artifact sets per NFR2 tracking.

---

## Interfaces

### I1: Reviewer Prompt Template (Phase 1 — Fresh Dispatch)

Used by: All reviewer dispatches across all commands, every iteration.

```
Task tool call:
  description: "{review description}"
  subagent_type: {agent_type}
  model: {model}
  prompt: |
    {review task description and rubric — unique per agent}

    ## Required Artifacts
    You MUST read the following files before beginning your review.
    After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
    {for each artifact in ARTIFACT_MAP[agent_type]:}
    {  resolved_path = resolve_prd(artifact) if artifact == "prd.md" else feature_path/artifact}
    {  if resolved_path is "NONE": emit "- PRD: No PRD — feature created without brainstorm"}
    {  else: emit "- {Artifact Name}: {resolved_path}"}

    ## Implementation Files (implement.md dispatches only)
    {list of changed files — inline, same as current}
    (This section is omitted for phase command dispatches — specify.md, design.md,
     create-plan.md, create-tasks.md — which review artifacts, not code files.)

    ## Iteration Context
    This is iteration {n} of {max}.
    {if n > 1: "Previous issues to re-evaluate:\n{issue list from previous iteration}"}

    {review instructions and JSON return format — same as current}
```

**Variable resolution**:
- `{feature_path}`: Resolved from active feature directory
- `{ARTIFACT_MAP}`: Per-role mapping from I4/I5
- `{resolve_prd()}`: See I8
- `{review task description}`: Unchanged from current — each agent's specific instructions

### I2: Resumed Reviewer Prompt Template (Phase 2 — Future)

Defined here for forward compatibility. NOT used in Phase 1 implementation.

```
Task tool call:
  resume: {stored_agent_id}
  prompt: |
    Review iteration {n} of {max}. You already have the upstream artifacts
    in context from your previous review.

    ## Changes Since Last Review
    The following changes were made to address your previous issues:

    ### Fix Summary
    {implementer/orchestrator fix summary text}

    ### Diff
    ```
    {git diff --stat output}
    {git diff output}
    ```

    Review ONLY the changes above. Assess whether your previous issues
    are resolved and check for new issues introduced by the fixes.

    {JSON return format — same as current}
```

### I3: Fresh Fallback Prompt Template (Phase 2 — Future)

Defined here for forward compatibility. NOT used in Phase 1.

Identical to I1 but with:
- Iteration context notes: "(Fresh dispatch — prior session unavailable.)"
- Includes previous issues from prior iteration

### I4: Per-Role Artifact Mapping (implement.md)

```
ARTIFACT_MAP = {
  "implementation-reviewer": ["prd.md", "spec.md", "design.md", "plan.md", "tasks.md"],
  "code-quality-reviewer":   ["design.md", "spec.md"],
  "security-reviewer":       ["design.md", "spec.md"],
  "code-simplifier":         ["design.md"],  // spec R3.1 intentionally excludes spec.md; YAGNI judgment relies on design patterns only. If this degrades simplifier quality, expand to ["design.md", "spec.md"] per NFR2 tracking.
  "test-deepener":           ["spec.md", "design.md", "tasks.md", "prd.md"],  // reads full PRD (not section-scoped) — acceptable since test-deepener needs Goals for business-level test scenarios
  "implementer":             ["prd.md", "spec.md", "design.md", "plan.md", "tasks.md"]
}
```

Note: `"implementer"` is the logical key for the Step 7e fix dispatch. The actual `subagent_type` is `iflow:implementer` (same agent as initial implementation). This key distinguishes the fix dispatch's artifact needs from the per-task dispatch in the implementing skill (which uses extractSection + lazy-load hybrid per I7).

### I5: Per-Role Artifact Mapping (phase commands)

Note: The artifact under review (e.g., spec.md for spec-reviewer, design.md for design-reviewer) is included in the prompt body as the review target, separate from the Required Artifacts reference block. The mappings below list only the upstream context artifacts the reviewer needs to read via lazy-load. Implementers: do NOT add the review-target artifact to the Required Artifacts block — it is already present in the prompt body.

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

Note: `"prd.md"` is a logical key resolved via I8 (PRD Resolution Logic) at template render time. The orchestrating command resolves it to the actual PRD file path or emits the "No PRD" sentinel.

### I6: Resume State Management (Phase 2 — Future)

Defined for forward compatibility. NOT used in Phase 1.

```
resume_state = {
  "{agent_role}": {
    "agent_id": "{returned from Task tool result}",
    "iteration1_prompt_length": {character count of first dispatch prompt},
    "last_iteration": {iteration number}
  }
}
```

`agent_role` keys: reviewer type names from I4/I5 (e.g., "implementation-reviewer", "implementer" for fix dispatch). Each role gets its own independent resume chain.

### I7: Implementing Skill Hybrid Dispatch (SKILL.md Step 2b)

```
Task tool call:
  description: "Implement task {n}: {task_subject}"
  subagent_type: iflow:implementer
  model: opus
  prompt: |
    Implement the following task:

    ## Task
    {task description — inline, from tasks.md}

    ## Done When
    {acceptance criteria — inline, from tasks.md}

    ## Design Context (scoped)
    {extractSection(design.md, task.traceability_ref) — inline, retained}

    ## Plan Context (scoped)
    {extractSection(plan.md, task.traceability_ref) — inline, retained}

    ## Required Artifacts
    You MUST read the following files before beginning your work.
    After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
    {resolve_prd("prd.md") → emit path or "No PRD" sentinel}
    - Spec: {feature_path}/spec.md
    (Note: prd.md is read in full rather than section-scoped. Current templates scope PRD
     to Problem Statement + Goals, but the full PRD is small enough that reading it whole
     is acceptable. This simplifies the lazy-load pattern — no extractSection needed for PRD.)

    ## Project Context
    {project context block — same as current, with token budget}

    ## Files to Work On
    {inline file list — same as current}

    {implementation instructions — same as current}
```

### I8: PRD Resolution Logic

Used by all prompt templates when the artifact mapping includes "prd.md":

```
function resolve_prd(feature_path):
  1. Check if {feature_path}/prd.md exists
  2. If exists → return "- PRD: {feature_path}/prd.md"
  3. If not exists → check .meta.json for brainstorm_source
     a. If brainstorm_source exists → return "- PRD: {brainstorm_source path}"
        (Defensive fallback: brainstorm-promoted features copy prd.md in create-feature,
         so step 1 should always match for them. Step 3a handles edge cases where the
         copy failed or prd.md was deleted after creation.)
     b. If brainstorm_source not exists → return "- PRD: No PRD — feature created without brainstorm"
```

This preserves the current `{content of prd.md, or "None - feature created without brainstorm"}` conditional behavior.

**Example output** when resolve_prd returns the "No PRD" sentinel (feature created without brainstorm):
```
## Required Artifacts
You MUST read the following files before beginning your review.
After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
- PRD: No PRD — feature created without brainstorm
- Spec: /Users/terry/projects/my-project/docs/features/031-example/spec.md
```

### I9: Lazy-Load Fallback Detection

Applied to all 6 in-scope files (specify.md, design.md, create-plan.md, create-tasks.md, implement.md, implementing/SKILL.md). After receiving the agent response and before parsing the JSON review result, the orchestrating command checks for artifact confirmation:

```
function check_artifact_confirmation(response, expected_artifacts):
  1. Search response for pattern: "Files read:" followed by file names
  2. If pattern found → pass (no action)
  3. If pattern NOT found:
     a. Log to .review-history.md: "LAZY-LOAD-WARNING: {agent_type} did not confirm artifact reads"
     b. Do NOT block or retry — proceed with review result as-is
     c. The LAZY-LOAD-WARNING entry logged in step 3a constitutes the NFR2 tracking record (no separate counter variable)
```

This is intentionally observational and non-blocking. Within a review loop iteration, the adversarial multi-reviewer design provides redundancy — if one reviewer skips artifact reads, others catch the gap. NFR2 uses accumulated fallback_count to assess lazy-load reliability post-deployment. If fallback rate exceeds 20%, the lazy-load approach itself is re-evaluated.

Cross-feature accumulation: LAZY-LOAD-WARNING entries persist in each feature's `.review-history.md`. To measure the accumulated rate across features: `grep -r "LAZY-LOAD-WARNING" docs/features/*/.review-history.md | wc -l`.

---

## File Change Summary

| File | Phase | Changes |
|---|---|---|
| `plugins/iflow/commands/specify.md` | 1 | Replace `{content of prd.md}` / `{content of spec.md}` with I1 template; apply I5 mapping; add I8 PRD resolution; add I9 fallback detection; remove "always a NEW Task" directive text (behavior unchanged in Phase 1 — still fresh dispatches) |
| `plugins/iflow/commands/design.md` | 1 | Replace inline artifacts in Stages 3-4 with I1 template; apply I5 mapping; add I8; add I9 fallback detection; Stage 0 research dispatches unchanged |
| `plugins/iflow/commands/create-plan.md` | 1 | Replace inline artifacts with I1 template; apply I5 mapping; add I8; add I9 fallback detection |
| `plugins/iflow/commands/create-tasks.md` | 1 | Replace inline artifacts with I1 template; apply I5 mapping; add I8; add I9 fallback detection |
| `plugins/iflow/commands/implement.md` | 1 | Replace inline artifacts in steps 5, 6, 7a-7c, 7e with I1 template; apply I4 mapping (step 7e uses I1 with "implementer" key from I4, same template as other dispatches); add I8; add I9 fallback detection |
| `plugins/iflow/skills/implementing/SKILL.md` | 1 | Convert Step 2b to I7 hybrid template (retain extractSection for plan/design, mandatory-read for spec/prd via I8); add I9 fallback detection |

Files are independently changeable in any order. Suggested sequence: implementing/SKILL.md first (validates the hybrid I7 template), then commands in workflow order: specify.md, design.md, create-plan.md, create-tasks.md, implement.md.

### Verification Note

The spec's grep audit pattern (`grep -rP "\{.*content.*\.md\}" plugins/iflow/`) may produce false positives from:
1. Non-artifact content injections in prose or comments explaining the old pattern
2. **Excluded-from-scope files** that intentionally retain inline injection: `plugins/iflow/skills/brainstorming/SKILL.md` (prd-reviewer and brainstorm-reviewer dispatches) and `plugins/iflow/skills/retrospecting/SKILL.md` (which uses `{content of references/aorta-framework.md}`)
3. **Retained hybrid patterns** in `plugins/iflow/skills/implementing/SKILL.md`: two extractSection-scoped inline injections for design.md and plan.md content per TD4 (the `{extractSection(design.md, ...)}` and `{extractSection(plan.md, ...)}` patterns) — these are expected remaining matches, not missed conversions.
During verification, manually inspect each match to confirm it is an actual in-scope inline injection site.
