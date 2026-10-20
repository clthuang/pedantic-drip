# Retrospective: Feature 030 — Token Efficiency Improvements

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 30 min | 5 (spec×3, phase×2) | Approved without cap. Clean pre-design phase. |
| design | 155 min | 9 (design×5 cap, handoff×4) | Design cap driven by R3 behavioral-change implications across multiple sub-issues. |
| create-plan | 75 min | 9 (plan×4, chain×5 cap) | Chain reviewer iter 1 was a full false-positive round (prompt compression). Step count metadata corrected at cap (16→18). |
| create-tasks | 90 min | 9 (task×5 cap, chain×3+) | Task cap with 1 warning remaining ({feature_path} undefined). 6 false-positive blockers at task iter 2 (prompt compression). |
| implement | 105 min | 4 | JSON schema consistency fixed iters 1–2. Final validation clean. R1 deferral acknowledged. |

**Total branch lifetime:** ~8h 05m across 5 phases
**Total review iterations:** 36 across all phases
**Iteration caps hit:** 3 of 5 phases (design, create-plan chain, create-tasks)
**Implementation outcome:** 18 tasks, zero deviations, 47 structural tests passing
**False-positive blocker rounds:** 2 — combined 8 false-positive blockers from prompt compression

---

### Review (Qualitative Observations)

1. **Prompt compression silently degraded reviewer inputs, producing false-positive blockers.** In create-plan chain review iter 1, the reviewer received a compressed summary instead of the 252-line plan.md, raising 2 blockers about content that was in fact present. In create-tasks iter 2, all 6 blockers were false positives from the same cause (462-line tasks.md). Evidence: _"All issues were caused by prompt compression in the previous session, not actual plan.md deficiencies."_

2. **Design templates referenced by design label in task descriptions without inline reproduction created a persistent blocker pattern.** Task review iters 2–4 repeatedly addressed the same root: I1, I8, I9 templates and {feature_path} not reproduced in tasks.md. At iter 4: _"Tasks 2-15: I1/I8/I9 templates referenced by name but never reproduced — engineer cannot execute without design doc."_ The gap survived to the cap.

3. **R3 behavioral-change implications required clarification across 4 design iterations and 2 plan iterations.** Initially framed as transport optimization, reviewers repeatedly surfaced that removing artifacts from agent dispatches is a behavioral change requiring per-agent justification. Design iter 4: _"R3 pruning is behavioral change, not just transport — constraint imprecision."_

4. **JSON return schema inconsistency in reviewer prompts was caught in implement review (iters 1–2) rather than design.** Both code-quality-reviewer and security-reviewer dispatch prompts used plain prose return format. Implement iter 1: _"Step 7b uses 'Return assessment with approval status.' — plain prose without JSON schema, inconsistent with 7a, 7c, and all phase command dispatches."_

---

### Tune (Process Recommendations)

1. **Add artifact completeness headers to large-artifact reviewer dispatches** (Confidence: high)
   - Signal: 2 full review iterations consumed on false-positive blockers from prompt compression. 8 false-positive blockers total across create-plan and create-tasks phases.
   - Recommendation: Require a completeness header before large artifacts: _"Full plan.md — 255 lines, complete content follows."_ Update phase-reviewer and chain-reviewer prompts: _"If the artifact appears truncated or summarized, flag this immediately as a process error before evaluating content."_

2. **Require a Shared Templates section in tasks.md for cross-task design templates** (Confidence: high)
   - Signal: 3 consecutive task-review iterations addressed missing inline template definitions. Cap reached with {feature_path} still undefined.
   - Recommendation: Update the create-tasks skill prompt: _"Before writing individual tasks, identify all cross-task templates, format patterns, and variable definitions from the design. Reproduce them verbatim in a 'Shared Templates' section at the top of tasks.md. Tasks must be self-contained."_

3. **Require a Behavioral Change Table in design.md for any feature modifying agent context** (Confidence: high)
   - Signal: R3 behavioral implications required 4 design and 2 plan review iterations across 6+ sub-issues, each adding a note or comment rather than a structured before/after view.
   - Recommendation: Require an _"Agent Context Changes"_ section with columns: Agent | Artifact Added/Removed | Rationale. Add to design-reviewer checklist: _"Are all behavioral changes to agent context documented in a structured table?"_

4. **Enforce JSON return schema consistency in design phase for all reviewer dispatch prompts** (Confidence: medium)
   - Signal: Schema inconsistency in 2 reviewer prompts caught in implement review despite design specifying schema standardization. Catching one per implement iteration doubled correction cost.
   - Recommendation: Add design-reviewer checklist item: _"Do all new or modified reviewer prompt templates include an explicit JSON return schema block?"_

5. **Scope grep audit steps to changed files only, with pre-declared false positives** (Confidence: high)
   - Signal: grep false positive list required 4 corrections across plan review iters 1–4. Task iter 4 finally scoped grep to 6 changed files.
   - Recommendation: Plan authoring convention: grep verification steps must scope to the explicit list of changed files, not the full directory, and enumerate expected false positives with rationale.

---

### Act (Knowledge Bank Updates)

**Patterns added:**
- Shared Templates in tasks.md for cross-task design templates — reproduce verbatim rather than referencing design labels. (from: Feature 030, create-tasks — task-reviewer iter 4 blocker, cap with {feature_path} undefined)
- Artifact-under-review stays inline in reviewer dispatch; only upstream context is lazy-loaded. (from: Feature 030, design iters 3–4)
- Behavioral changes to agent context require explicit before/after documentation, not framing as transport optimization. (from: Feature 030, design iter 4 + plan iter 1)
- Zero-deviation implementation follows when tasks contain binary done-when criteria, verbatim templates, and scoped grep patterns. (from: Feature 030, implement phase — 18 tasks, 0 deviations)

**Anti-patterns added:**
- Dispatching reviewers with compressed artifacts produces false-positive blockers that consume full review iterations. (from: Feature 030, create-plan chain iter 1 + create-tasks iter 2)
- Reviewer output format specified as plain prose instead of JSON schema is caught late in implement review. (from: Feature 030, implement iters 1–2)
- Design label references without inline reproduction in plan/tasks documents force cross-document lookup and block reviewers. (from: Feature 030, plan iter 1 + task iters 2–4)

**Heuristics added:**
- If 3+ review iterations address the same issue category, the underlying section has a structural gap — restructure it, don't add more notes. (from: Feature 030, design — R3 implications recurred iters 1, 3, 4, 5)
- Pre-declare artifact completeness in large-artifact dispatches with a line-count header to make compression detectable. (from: Feature 030, create-plan + create-tasks — both false-positive incidents involved artifacts over 200 lines)
- Scope grep audit steps to changed files and enumerate expected false positives upfront for deterministic pass/fail signals. (from: Feature 030, plan iters 1–4 + task iter 4)

---

## Raw Data

- Feature: 030-token-efficiency-improvements
- Mode: standard
- Branch: feature/030-token-efficiency-improvements
- Branch lifetime: ~8h 05m (2026-02-27T18:00 to 2026-02-28T02:05, +08:00)
- Git: 8 commits, 15 files changed, +3280 -166 lines
- Phases: 5 (specify, design, create-plan, create-tasks, implement)
- Total review iterations: 36
- Iteration caps hit: 3 of 5 phases (design, create-plan chain, create-tasks)
- False-positive blocker rounds: 2 (8 false-positive blockers total)
- Implementation tasks: 18, zero deviations
- Structural tests: 47 passing
- R1 (Agent Reuse via Resume): deferred to Phase 2 — GitHub #13619
- R2 (Lazy-Load References): 15 dispatch sites converted
- R3 (Role-Specific Context Pruning): per-role artifact mapping implemented
- Backlog source: 00021
