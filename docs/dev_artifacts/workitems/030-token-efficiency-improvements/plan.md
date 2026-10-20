# Plan: Token Efficiency Improvements

## Overview

18 steps across 7 phases: Replace all inline artifact injection (`{content of X.md}`) across 6 files with lazy-load file references (I1 template), role-specific artifact mapping (I4/I5), conditional PRD resolution (I8), and fallback detection (I9). 15 conversion steps + 3 verification steps. Phase 2 (resume/R1) is deferred — no resume logic is implemented.

## Conventions

**Review-target transport**: The artifact under review (e.g., spec.md for spec-reviewer, design.md for design-reviewer) remains orchestrator-injected inline in the prompt body. This is intentional — the reviewer needs immediate access to the artifact it is reviewing. Only upstream context artifacts are lazy-loaded via Required Artifacts block. implement.md dispatches (steps 5-7e) have no single "review target" — all artifacts go through lazy-load.

**R3 pruning acknowledgment**: Some steps change which artifacts a reviewer receives (R3), not just how they receive them (R2). These are called out explicitly with "R3 pruning change" labels. The current templates give all reviewers all 5 artifacts; the new templates give each reviewer only its designated set from I4/I5.

**"Always a NEW Task" directive**: Exists only in the 4 phase commands (specify.md, design.md, create-plan.md, create-tasks.md) as parenthetical remarks within step instructions (e.g., "Return to step 4b (always a NEW Task tool dispatch per iteration)"). Replace the parenthetical with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)`, preserving the surrounding prose. Does NOT apply to implement.md (which has no such directive).

**I9 for action agents**: I9 fallback detection applies to all dispatch sites per design. Action agents (code-simplifier, test-deepener, implementer) may produce LAZY-LOAD-WARNING entries more frequently than reviewers since their output formats differ. This is expected and acceptable — I9 is observational-only and non-blocking.

**I9 insertion point**: Per design I9, the check is inserted immediately after receiving the agent response text and before parsing the JSON result. Scan response for "Files read:" pattern; if absent, log LAZY-LOAD-WARNING to `.review-history.md`. The check does not alter control flow — proceed to JSON parsing regardless. See Design I9 (`check_artifact_confirmation` function) for the verbatim check to insert.

**PRD conditional pattern variance**: Phase commands use `{content of prd.md, or "None - feature created without brainstorm"}` while implement.md uses `{content of prd.md or brainstorm file}`. Both map to I8's 3-step resolution: (1) check prd.md → (2) check brainstorm_source → (3) "No PRD" sentinel. Step 2 covers implement.md's "brainstorm file" case. The sentinel in step 3 replaces both "None" and the implicit "no file" case.

**Batch note for Phases 1B-1E**: These four phase commands follow an identical conversion pattern (I1 template + I5 mapping + I8 + I9). Each has two dispatches (domain reviewer + phase reviewer). The only variation is the artifact mapping from I5. Can be implemented in batch (all four files at once) or sequentially in any order. The 1B-1C-1D-1E numbering reflects workflow sequence for readability, not implementation dependency.

## Implementation Phases

### Phase 1A: Implementing Skill Hybrid Template

**Why this item**: SKILL.md is the only hybrid template (I7) — it retains extractSection for plan/design while adding lazy-load for spec/prd. This is the most complex conversion pattern.
**Why this order**: Starting with the most complex case first de-risks the simpler I1-only command conversions. If the hybrid pattern works, the command conversions are straightforward.

**Step 1A.1: Convert SKILL.md Step 2b dispatch**
- File: `plugins/iflow/skills/implementing/SKILL.md`
- Replace the inline `{spec.md content}` and `{Problem Statement + Goals from prd.md}` blocks with mandatory-read reference blocks per I7
- Retain extractSection() for design.md and plan.md (TD4) — these remain inline
- Add `resolve_prd()` logic per I8: check prd.md → check brainstorm_source → "No PRD" sentinel
- Add I9 fallback detection after implementer response: check for "Files read:" confirmation, log LAZY-LOAD-WARNING if absent
- Remove inline `## Spec` and `## PRD Context` sections; replace with `## Required Artifacts` block with mandatory-read directive
- Traceability: Design I7, I8, I9; Spec R2.3, R2.1

### Phase 1B: specify.md Command

**Why this item**: specify.md is the first phase command in the workflow — the simplest case (only 2 artifacts: PRD and Spec) and validates the I1+I5 pattern for all subsequent commands.
**Why this order**: After 1A validates the hybrid pattern, the simplest command conversion confirms the I1 template works for standard dispatches.

**Step 1B.1: Convert spec-reviewer dispatch (Stage 1)**
- File: `plugins/iflow/commands/specify.md`
- Replace `## PRD (original requirements)\n{content of prd.md, or "None - feature created without brainstorm"}` with I1 Required Artifacts block
- Spec is the review target — remains orchestrator-injected inline in the prompt body (not in Required Artifacts)
- Apply I5 mapping for spec-reviewer: `["prd.md"]` only in Required Artifacts
- Add I8 PRD resolution (the current `or "None"` conditional converts to resolve_prd())
- Add I9 fallback detection after response parsing
- Replace parenthetical `(always a NEW Task tool dispatch per iteration)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)` per Convention
- Traceability: Design I1, I5, I8, I9; Spec R2.1, R3.2

**Step 1B.2: Convert phase-reviewer dispatch (Stage 2)**
- File: `plugins/iflow/commands/specify.md`
- Replace inline PRD and Spec content blocks with I1 Required Artifacts block
- Spec is NOT the review target here (phase-reviewer reviews readiness, not spec content) — both PRD and Spec go in Required Artifacts
- Apply I5 mapping for phase-reviewer: `["prd.md", "spec.md"]`
- Add I8 PRD resolution
- Add I9 fallback detection
- Replace parenthetical `(always a NEW Task...)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)` per Convention
- Traceability: Design I1, I5, I8, I9; Spec R2.1, R3.2

### Phase 1C: design.md Command

**Why this item**: design.md adds one more artifact (Design) to the mapping and has Stage 0 exclusions to verify.
**Why this order**: Follows specify.md in workflow sequence — progressively more artifacts per I5 mapping.

Stage 0 research agents are excluded (they receive feature description summaries, not artifacts).

**Step 1C.1: Convert design-reviewer dispatch (Stage 3)**
- File: `plugins/iflow/commands/design.md`
- Replace inline PRD and Spec content blocks with I1 Required Artifacts block
- Design.md is the review target — remains orchestrator-injected inline in the prompt body
- Apply I5 mapping for design-reviewer: `["prd.md", "spec.md"]`
- Add I8 PRD resolution
- Add I9 fallback detection
- Replace parenthetical `(always a NEW Task...)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)` per Convention
- Traceability: Design I1, I5, I8, I9; Spec R2.1, R3.2

**Step 1C.2: Convert phase-reviewer dispatch (Stage 4)**
- File: `plugins/iflow/commands/design.md`
- Replace inline PRD, Spec, and Design content blocks with I1 Required Artifacts block
- Apply I5 mapping for phase-reviewer: `["prd.md", "spec.md", "design.md"]`
- Add I8 PRD resolution
- Add I9 fallback detection
- Replace parenthetical `(always a NEW Task...)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)` per Convention
- Traceability: Design I1, I5, I8, I9; Spec R2.1, R3.2

### Phase 1D: create-plan.md Command

**Why this item**: create-plan.md adds Design to the mapping and introduces the pattern where plan.md is the review target (inline) while 3 upstream artifacts are lazy-loaded.
**Why this order**: Follows design.md in workflow sequence.

**Step 1D.1: Convert plan-reviewer dispatch (Stage 1)**
- File: `plugins/iflow/commands/create-plan.md`
- Replace inline PRD, Spec, and Design content blocks with I1 Required Artifacts block
- Plan.md is the review target — remains orchestrator-injected inline in the prompt body
- Apply I5 mapping for plan-reviewer: `["prd.md", "spec.md", "design.md"]`
- Add I8 PRD resolution
- Add I9 fallback detection
- Replace parenthetical `(always a NEW Task...)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)` per Convention
- Traceability: Design I1, I5, I8, I9; Spec R2.1, R3.2

**Step 1D.2: Convert phase-reviewer dispatch (Stage 2)**
- File: `plugins/iflow/commands/create-plan.md`
- Replace inline PRD, Spec, Design, and Plan content blocks with I1 Required Artifacts block
- Apply I5 mapping for phase-reviewer: `["prd.md", "spec.md", "design.md", "plan.md"]`
- Add I8 PRD resolution
- Add I9 fallback detection
- Replace parenthetical `(always a NEW Task...)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)` per Convention
- Traceability: Design I1, I5, I8, I9; Spec R2.1, R3.2

### Phase 1E: create-tasks.md Command

**Why this item**: create-tasks.md is the last phase command — 5 artifacts in the phase-reviewer mapping (the maximum for phase commands).
**Why this order**: Follows create-plan.md in workflow sequence. Completes the phase command conversions before tackling implement.md.

**Step 1E.1: Convert task-reviewer dispatch (Stage 1)**
- File: `plugins/iflow/commands/create-tasks.md`
- Replace inline PRD, Spec, Design, and Plan content blocks with I1 Required Artifacts block
- Tasks.md is the review target — remains orchestrator-injected inline in the prompt body
- Apply I5 mapping for task-reviewer: `["prd.md", "spec.md", "design.md", "plan.md"]`
- Add I8 PRD resolution
- Add I9 fallback detection
- Replace parenthetical `(always a NEW Task...)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)` per Convention
- Traceability: Design I1, I5, I8, I9; Spec R2.1, R3.2

**Step 1E.2: Convert phase-reviewer dispatch (Stage 2)**
- File: `plugins/iflow/commands/create-tasks.md`
- Replace inline content blocks with I1 Required Artifacts block
- Apply I5 mapping for phase-reviewer: `["prd.md", "spec.md", "design.md", "plan.md", "tasks.md"]`
- Add I8 PRD resolution
- Add I9 fallback detection
- Replace parenthetical `(always a NEW Task...)` with `(Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support.)` per Convention
- Traceability: Design I1, I5, I8, I9; Spec R2.1, R3.2

### Phase 1F: implement.md Command

**Why this item**: implement.md has the most dispatch sites (6) and the most differentiated artifact mappings via I4. It includes both reviewer dispatches and action-agent dispatches (code-simplifier, test-deepener, implementer). Three of its dispatches involve R3 pruning changes that reduce the artifact set.
**Why this order**: Last command file. Phase commands (1B-1E) validate the I1 pattern first; implement.md then applies I4's differentiated mappings. Doing implement.md last means all simpler conversions are proven before tackling the most complex file.

Steps within implement.md must be executed sequentially (same file); ordering by document step number is both convenient and required to avoid conflicts.

**Step 1F.1: Convert code-simplifier dispatch (Step 5)**
- File: `plugins/iflow/commands/implement.md`
- Replace inline Spec and Design content blocks with I1 Required Artifacts block
- Apply I4 mapping for code-simplifier: `["design.md"]` only
- **R3 pruning change**: Current template has 2 artifacts (spec.md, design.md); new template has 1 (design.md only). Spec.md removal is intentional per TD5b/R3.1 — YAGNI judgment relies on design patterns, not spec requirements
- Add I9 fallback detection
- I8 PRD resolution omitted from prompt body (PRD not in I4 mapping for this role). The resolve_prd() helper is not called here
- Traceability: Design I1, I4, I9, TD5b; Spec R2.5, R3.1

**Step 1F.2: Convert test-deepener dispatch (Step 6)**
- File: `plugins/iflow/commands/implement.md`
- **Phase A only**: Replace inline Spec, Design, Tasks, and PRD content blocks with I1 Required Artifacts block
- Apply I4 mapping for test-deepener: `["spec.md", "design.md", "tasks.md", "prd.md"]`
- **R3 pruning change**: Current template has section-scoped PRD (Problem Statement + Goals only); new template gives full PRD via lazy-load. This expands test-deepener's PRD context — intentional per TD5b to simplify lazy-load pattern
- **Phase B is excluded from conversion** — it receives Phase A output and file lists only, with no upstream artifact injection. No changes needed for Phase B
- Add I8 PRD resolution for Phase A
- Add I9 fallback detection for Phase A
- Traceability: Design I1, I4, I8, I9, TD5b; Spec R2.5, R3.1

**Step 1F.3: Convert implementation-reviewer dispatch (Step 7a)**
- File: `plugins/iflow/commands/implement.md`
- Replace all 5 inline artifact content blocks with I1 Required Artifacts block
- Apply I4 mapping for implementation-reviewer: `["prd.md", "spec.md", "design.md", "plan.md", "tasks.md"]`
- No R3 pruning change — implementation-reviewer retains full chain (same 5 artifacts as current)
- Keep Implementation files list inline (agents need to know which files to review)
- Add I8 PRD resolution
- Add I9 fallback detection
- Traceability: Design I1, I4, I8, I9; Spec R2.5, R3.1

**Step 1F.4: Convert code-quality-reviewer dispatch (Step 7b)**
- File: `plugins/iflow/commands/implement.md`
- Replace inline content blocks with I1 Required Artifacts block
- Apply I4 mapping for code-quality-reviewer: `["design.md", "spec.md"]`
- **R3 pruning change**: Current template has 5 artifacts (prd.md, spec.md, design.md, plan.md, tasks.md); new template has 2 (design.md, spec.md). PRD, Plan, and Tasks removal is intentional per R3.1 — code-quality-reviewer evaluates SOLID/KISS against Design and YAGNI against Spec
- Keep Files changed list inline
- Add I9 fallback detection
- I8 PRD resolution omitted from prompt body (PRD not in I4 mapping for this role). The resolve_prd() helper is not called here
- Traceability: Design I1, I4, I9; Spec R2.5, R3.1

**Step 1F.5: Convert security-reviewer dispatch (Step 7c)**
- File: `plugins/iflow/commands/implement.md`
- Replace inline content blocks with I1 Required Artifacts block
- Apply I4 mapping for security-reviewer: `["design.md", "spec.md"]`
- **R3 pruning change**: Current template has 5 artifacts; new template has 2 (design.md, spec.md). PRD, Plan, and Tasks removal is intentional per R3.1 — security-reviewer evaluates threat model against Design and security requirements against Spec
- Keep Files changed list inline
- Add I9 fallback detection
- I8 PRD resolution omitted from prompt body (PRD not in I4 mapping for this role). The resolve_prd() helper is not called here
- Traceability: Design I1, I4, I9; Spec R2.5, R3.1

**Step 1F.6: Convert implementer fix dispatch (Step 7e)**
- File: `plugins/iflow/commands/implement.md`
- Replace all 5 inline artifact content blocks with I1 Required Artifacts block
- Apply I4 mapping for implementer: `["prd.md", "spec.md", "design.md", "plan.md", "tasks.md"]`
- No R3 pruning change — implementer retains full chain (same 5 artifacts as current)
- Keep Implementation files list and Issues to fix list inline
- Add I8 PRD resolution
- Add I9 fallback detection
- Traceability: Design I1, I4, I8, I9; Spec R2.5, R3.1

### Phase 1G: Verification

**Why this item**: Confirms all inline injections are removed and agents have required tool access.
**Why this order**: Runs after all implementation steps to validate the complete conversion.

**Step 1G.1: Grep audit**
- Run: `grep -rE "\{.*content.*\.md\}" plugins/iflow/` (or `rg "\{.*content.*\.md\}" plugins/iflow/`)
- Expected: Zero matches in the 6 changed files
- Expected remaining matches (NOT missed conversions):
  1. `plugins/iflow/skills/retrospecting/SKILL.md` — excluded from scope, uses `{content of references/aorta-framework.md}`
  2. `plugins/iflow/skills/brainstorming/SKILL.md` — excluded from scope per design (prd-reviewer and brainstorm-reviewer dispatches are lightweight single-artifact reviews)
  3. `plugins/iflow/skills/implementing/SKILL.md` extractSection patterns — `{extractSection(design.md, ...)}` and `{extractSection(plan.md, ...)}` are retained per I7/TD4, not inline injection
- Note: brainstorming/SKILL.md's pattern `{read PRD file and paste full markdown content here}` does not match the primary grep regex, but may match on other inline patterns
- **Secondary grep** for section-scoped PRD patterns: `grep -rE "Problem Statement.*prd|Goals.*prd" plugins/iflow/` — catches `{Problem Statement + Goals from prd.md}` injections that the primary grep misses. Expected zero matches in changed files after conversion (1A.1 removes SKILL.md pattern, 1F.2 removes implement.md pattern)
- Manually inspect any matches to confirm they are in excluded-from-scope files only
- Traceability: Spec Test Strategy

**Step 1G.2: Agent frontmatter check**
- Purpose: Verify all agents that will receive lazy-load prompts have `Read` in their frontmatter tools list, so they can read the artifact files referenced in the Required Artifacts block
- Required agents: implementation-reviewer, code-quality-reviewer, security-reviewer, code-simplifier, test-deepener, implementer, spec-reviewer, design-reviewer, plan-reviewer, task-reviewer, phase-reviewer
- Run: `grep -l "Read" plugins/iflow/agents/*.md` and confirm all 11 agents above are present in the output
- Pass/fail: All 11 agents appear in output → pass. Any missing → add Read to that agent's tools list
- Traceability: Spec Test Strategy

**Step 1G.3: Manual end-to-end validation**
- Run one phase command (e.g., `/iflow:specify`) on a test feature after all conversions
- Verify: (a) agent reads files via Read tool (visible in agent transcript), (b) review outcome is comparable to baseline, (c) no LAZY-LOAD-WARNING is triggered
- This is a manual post-implementation check, not automated
- Traceability: Spec Test Strategy ("Manual end-to-end validation")

## Dependencies

```
1A.1 (implementing/SKILL.md) — no dependencies, start first
  ↓ validates hybrid pattern
1B.1 → 1B.2 (specify.md: spec-reviewer before phase-reviewer — same file)
1C.1 → 1C.2 (design.md: design-reviewer before phase-reviewer — same file)
1D.1 → 1D.2 (create-plan.md: plan-reviewer before phase-reviewer — same file)
1E.1 → 1E.2 (create-tasks.md: task-reviewer before phase-reviewer — same file)
1F.1 → 1F.2 → 1F.3 → 1F.4 → 1F.5 → 1F.6 (implement.md: ordered by document step for readability, not strict dependency)
1G.1, 1G.2, 1G.3 — depend on ALL of 1A through 1F completing
```

Cross-file dependencies: None. Files 1B-1F are independently changeable in any order. 1A is recommended first to validate the hybrid pattern. 1G runs last as verification.

## Risk Mitigations

- **Agent ignores mandatory-read**: I9 fallback detection logs warnings for monitoring. Multi-reviewer redundancy provides safety net.
- **PRD resolution edge cases**: I8's 3-step fallback (file → brainstorm_source → sentinel) covers all feature creation paths.
- **Grep audit false positives**: Only 2 excluded-from-scope files should match; post-conversion SKILL.md extractSection patterns do not contain "content".
- **R3 pruning degrades review quality**: NFR2 tracking via LAZY-LOAD-WARNING entries and cross-feature grep. If quality drops, expand artifact sets.
