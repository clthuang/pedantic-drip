# PRD: YOLO Relevance Gate & Plan+Tasks Phase Evaluation

## Status
- Created: 2026-04-01
- Last updated: 2026-04-01
- Status: Draft
- Problem Type: Product/Feature
- Archetype: improving-existing-work

## Problem Statement
pd's workflow pipeline has two friction points: (1) YOLO mode auto-answers prompts and auto-chains phases but lacks safeguards against delivering irrelevant work when running fully unattended — there's no verification that the output matches the original intent, (2) create-plan and create-tasks are separate phases with separate dual-reviewer loops (up to 10 iterations each), adding overhead for features where the plan is straightforward enough to produce tasks directly.

### Evidence
- YOLO mode already auto-chains all phases via `[YOLO_MODE]` argument propagation at every phase boundary — Evidence: plugins/pd/commands/specify.md, design.md, create-plan.md, create-tasks.md (YOLO Mode Overrides sections)
- yolo-guard.sh hook intercepts AskUserQuestion and auto-selects "(Recommended)" option — Evidence: plugins/pd/hooks/yolo-guard.sh:94-104
- Safety valve keywords (circuit breaker, 5 iterations, merge conflict, abandon) bypass YOLO auto-selection — Evidence: plugins/pd/hooks/yolo-guard.sh:54-88
- create-plan has max 10 review iterations (5 plan-reviewer + 5 phase-reviewer) — Evidence: plugins/pd/commands/create-plan.md
- create-tasks has max 10 review iterations (5 task-reviewer + 5 phase-reviewer) — Evidence: plugins/pd/commands/create-tasks.md
- Standard vs Full modes run identical review loops — the "optional vs required verification" distinction is declared but not enforced — Evidence: All phase command files run the same two-step reviewer loop regardless of mode
- ECC comparison doc identifies "Quick mode" (specify→implement for 1-2 file changes) as a known improvement — Evidence: docs/ecc-comparison-improvements.md item 4
- Backlog 00027 proposes simplifying secretary by removing orchestrate/aware modes — Evidence: docs/backlog.md

## Goals
1. Add a relevance verification gate to existing YOLO mode that prevents delivery of irrelevant work when running fully autonomous
2. Evaluate merging create-plan and create-tasks into a single phase while preserving planning rigor and task decomposition quality
3. Preserve Standard and Full modes unchanged — turbo is additive, not replacing

## Success Criteria
- [ ] YOLO with relevance gate completes a simple feature (3-5 files, clear scope) end-to-end without human intervention and produces correct, relevant output
- [ ] YOLO with relevance gate halts and surfaces a relevance mismatch when the implementation drifts from the original intent
- [ ] Merged plan+tasks phase (if pursued) produces equivalent-quality tasks.md as the current two-phase approach in fewer total reviewer iterations
- [ ] Existing Standard/Full workflows pass all tests unchanged

## User Stories
### Story 1: Unattended Feature Delivery
**As a** solo developer **I want** to describe a well-understood feature and walk away while pd builds it **So that** I return to a completed, correct implementation

**Acceptance criteria:**
- YOLO mode (existing) auto-chains brainstorm→specify→design→plan→tasks→implement→finish (already works)
- A new relevance verification gate runs before finish-feature, checking implementation against spec.md acceptance criteria
- If relevance check fails, YOLO halts (via existing safety valve mechanism) with a structured explanation of drift
- No new "YOLO with relevance gate" concept — the relevance gate is an enhancement to existing YOLO

### Story 2: Faster Planning for Simple Features
**As a** developer working on straightforward features **I want** plan and task breakdown in a single phase **So that** I spend fewer iterations on overhead when the scope is clear

**Acceptance criteria:**
- Single combined command produces both plan.md and tasks.md
- Uses existing planning and breaking-down-tasks skills (no new skills)
- Total reviewer iterations ≤ current two-phase total for same-complexity features

## Use Cases
### UC-1: YOLO with Relevance Gate
**Actors:** Developer | **Preconditions:** Feature scope is clear, YOLO enabled
**Flow:** 1. Developer runs `/pd:create-feature --prd=brainstorm.prd.md` with YOLO active 2. Pipeline auto-chains through all phases (existing behavior) 3. Before finish-feature, relevance gate reads spec.md acceptance criteria and verifies implementation 4. Gate passes → finish-feature proceeds 5. Developer reviews PR
**Postconditions:** Feature branch with verified implementation, ready for merge
**Edge cases:** Relevance gate fails → YOLO halts via safety valve, developer reviews drift

### UC-2: Merged Plan+Tasks on a Simple Feature
**Actors:** Developer | **Preconditions:** Feature in design phase, design.md complete
**Flow:** 1. Developer runs `/pd:create-plan-tasks` 2. Planning skill produces staged plan 3. Breaking-down-tasks skill decomposes into atomic tasks 4. Combined reviewer validates both 5. Single phase completion
**Postconditions:** Both plan.md and tasks.md produced in one phase
**Edge cases:** Complex feature → reviewer pushes back on insufficient plan detail → iterate

## Edge Cases & Error Handling
| Scenario | Expected Behavior | Rationale |
|----------|-------------------|-----------|
| YOLO with relevance gate on a feature that's actually complex | Relevance gate catches drift; turbo halts | Overconfidence in "well-understood" classification is the primary failure mode |
| Reviewer iteration cap hit in YOLO with relevance gate | Safety valve fires (existing "5 iterations" keyword bypasses YOLO) | Existing circuit breaker prevents infinite loops |
| Plan+tasks merger loses planning-level review rigor | Plan-reviewer still runs first, then task-reviewer | Both review perspectives preserved in sequence, not merged into one |
| YOLO with relevance gate merge conflict at finish | Existing safety keyword "merge conflict" halts YOLO | Already handled |
| Mid-turbo context compaction loses state | .meta.json persists phase state; agent reads on resume | Existing recovery mechanism |

## Constraints
### Behavioral Constraints (Must NOT do)
- Must not modify Standard or Full mode behavior — Rationale: Turbo is additive
- Minimize new components — one new agent (relevance-verifier) is justified by the self-validation research finding: the verifier must be separate from the implementing agent to avoid "self-congratulation" bias
- Must not skip review loops entirely in YOLO with relevance gate — Rationale: Reviews catch errors; turbo accelerates, not bypasses

### Technical Constraints
- YOLO mode infrastructure (hook + per-command overrides) already handles auto-chaining — Evidence: Codebase analysis
- Phase state machine (ENTITY_MACHINES) requires updates if phases change — Evidence: CLAUDE.md entity state machine gotchas
- Standard vs Full distinction is declared but not enforced — Evidence: All commands run identical reviewer loops

## Requirements
### Functional
- FR-1: Add a relevance verification gate to the existing YOLO pipeline that runs between implement and finish-feature phases. No new mode concept — this enhances YOLO, not replaces it.
- FR-2: The relevance gate dispatches a **separate agent** (not the implementing agent) that reads spec.md acceptance criteria and verifies the implementation satisfies them. The verifier uses deterministic checks where possible (test execution, build verification) and agent-judged assessment for criteria that aren't mechanically testable. This addresses the self-validation problem: the verifier did not write the implementation and evaluates against criteria it did not author.
- FR-3: When the relevance gate fails, the finish-feature command surfaces an AskUserQuestion prompt containing the safety valve keyword "relevance verification failed" (which yolo-guard.sh passes through to the user, since it matches the safety keyword pattern). The prompt includes a structured drift report: which acceptance criteria passed, which failed, and what the implementation actually does vs what was expected.

### Deferred/Conditional (pending iteration count measurement)
- FR-4: Evaluate creating a `/pd:create-plan-tasks` combined command that invokes both planning and breaking-down-tasks skills sequentially with a combined review gate. Only pursue if median iteration counts from .review-history.md show > 3 iterations per phase on average.
- FR-5: If plan+tasks merger is pursued, maintain separate plan.md and tasks.md artifacts (same outputs, merged command)

### Non-Functional
- NFR-1: Relevance gate adds ≤ 1 additional agent dispatch beyond existing YOLO pipeline
- NFR-2: No new Python dependencies
- NFR-3: Relevance gate completes within 60 seconds (reads spec + scans implementation, no full rebuild)

## Non-Goals
- Replacing Standard or Full modes — Rationale: They serve different risk profiles
- Removing human review entirely — Rationale: Reviews catch errors; turbo reduces friction between phases, not within them
- Auto-deploying or auto-merging to base branch — Rationale: Final merge is always human-approved
- Implementing "Quick mode" (specify→implement skip) — Rationale: Separate backlog item, different scope

## Out of Scope (This Release)
- Multi-feature turbo orchestration — Future consideration: turbo on project decomposition
- YOLO with relevance gate for brainstorm phase — Future consideration: brainstorm is exploratory, not well-suited for autonomous execution
- Automated rollback on turbo failure — Future consideration: git revert of turbo branch

## Research Summary
### Internet Research
- Spec-driven verification (opslane/verify pattern): 4-stage pipeline — bash pre-flight, Opus planning, parallel Sonnet testing per AC, Opus judge — Source: agent-wars.com
- Self-validation is the primary autonomous agent failure mode — agents writing their own tests produce "self-congratulation machines" — Source: agent-wars.com
- Test-Driven Agentic Development (TDAD): encode spec as executable contracts + behavioral tests; agent implements against criteria it did not write — Source: Medium
- McKinsey QuantumBlack: co-locate requirements and tasks in single folder; evaluation gate (deterministic + agentic) between each step; human review only at end — Source: Medium
- Deterministic workflow pattern: commands/checks run deterministically; only code generation is probabilistic — Source: sedkodes.com

### Codebase Analysis
- YOLO auto-chains via [YOLO_MODE] arg propagation + yolo-guard.sh hook — Location: all phase commands + hooks/yolo-guard.sh
- Safety valve keywords prevent YOLO from overriding critical failures — Location: hooks/yolo-guard.sh:54-88
- create-plan: 5+5 reviewer iterations max — Location: commands/create-plan.md
- create-tasks: 5+5 reviewer iterations max — Location: commands/create-tasks.md
- Standard vs Full modes are identical in practice (same review loops) — Location: all phase commands
- Planning skill and breaking-down-tasks skill are sequential, not overlapping — Location: skills/planning/ and skills/breaking-down-tasks/
- ECC comparison doc identifies "Quick mode" (specify→implement) — Location: docs/ecc-comparison-improvements.md
- Secretary orchestrate mode exists for YOLO-only autonomous workflow — Location: commands/secretary.md

### Existing Capabilities
- YOLO mode — already auto-chains all phases, auto-selects at prompts, has safety valves
- skippedPhases — infrastructure allows skipping phases with tracking in .meta.json
- Phase-reviewer soft cap — reviewers prefer approving with warnings over blocking on iteration 3+

## Current State Assessment
### What Works Today
- YOLO mode auto-chains the full pipeline end-to-end (brainstorm → finish)
- Safety valves halt YOLO on circuit breakers, merge conflicts, iteration caps
- Two-step reviewer loops (domain + phase) provide quality gates at every phase
- yolo-stop hook prevents session termination during autonomous runs

### What's Missing
- **Relevance verification gate:** No mechanism checks whether the final implementation matches the original intent. YOLO trusts that if each phase's reviewer approves, the output is correct — but reviewers check phase-local quality, not end-to-end alignment.
- **Phase transition overhead:** create-plan and create-tasks run 20 maximum reviewer iterations combined. For simple features where the plan is obvious, this is disproportionate.
- **Mode enforcement:** Standard and Full are declared but functionally identical. No "turbo" classification exists.

### Change Impact
- **YOLO with relevance gate:** Adds a single relevance verification gate at implement→finish boundary. The gate is a new agent dispatch (relevance-verifier) that reads spec.md acceptance criteria and verifies the implementation satisfies them. Minimal code change — primarily a new agent + a conditional dispatch in finish-feature command.
- **Plan+tasks merger:** Combines two commands into one. Both skills are reused. Review loop restructured: plan-reviewer runs first (quality gate), then task-reviewer (execution gate), then single phase-reviewer (handoff gate). Reduces from 20 max iterations to 15 max. Requires ENTITY_MACHINES update, transition gate update, and test updates in two files.

### Migration Path
- YOLO with relevance gate is purely additive — a new mode option at feature creation, no existing behavior changes
- Plan+tasks merger could be optional — `/pd:create-plan-tasks` alongside existing separate commands — or replace them. Recommended: optional first, deprecate later if proven effective.

## Strategic Analysis

### Pre-mortem
- **Core Finding:** The most likely failure mode is definitional overconfidence — Terry classifies a feature as "well-understood" when it isn't. YOLO with relevance gate silences the friction signals (review prompts, phase boundaries) that would otherwise catch misclassification early.
- **Analysis:** The design assumes the user accurately identifies features as low-risk before starting. Features often reveal hidden complexity mid-stream. An auto-chained workflow cannot cleanly abort mid-flight. The relevance verification gate is the only safeguard — but it runs at the END, after implementation is complete. If the spec drifted from intent during brainstorm/specify, the gate catches a correct implementation of the wrong thing, which is the costliest failure mode (revert + redo costs 3x the time turbo saved). Named YOLO with relevance gates in developer tooling consistently expand to progressively less-clear-cut cases, degrading safety properties.
- **Key Risks:**
  - [Critical] Relevance verification gate is undefined — the core safeguard is a placeholder
  - [High] Phase state race condition if auto-chain invokes next command before prior flush
  - [High] Merged reviewer model tier ambiguity for plan+tasks
  - [Medium] Scope creep of YOLO with relevance gate to progressively less-clear cases
  - [Medium] Median review overhead may be overstated (cap is 10, typical may be 1-2)
- **Recommendation:** Before building: (1) measure actual median iteration counts from .review-history.md across recent features, (2) define the relevance verification gate specification with failure criteria. If median iterations are already 1-2, the problem framing needs revision.
- **Evidence Quality:** moderate

### Opportunity-cost
- **Core Finding:** YOLO already auto-chains every phase. The stated capability gap ("no true end-to-end autonomous mode") may not exist. Before building anything, test YOLO end-to-end on one feature and measure what actually breaks.
- **Analysis:** The problem statement treats "YOLO with relevance gate" and "improved YOLO" as different things, but codebase analysis shows YOLO already implements auto-chaining via [YOLO_MODE] argument propagation. The actual gap is narrower: YOLO lacks a relevance verification gate. Building a "YOLO with relevance gate" as a new concept adds a third mode alongside Standard/Full that every command must handle — this is significant complexity for what may be a single missing gate. The minimum experiment is a 30-minute end-to-end YOLO test on a real feature. For the merged plan+tasks: the commands are the most complex in the codebase (400+ lines each with resume-state logic). Merging carries high regression risk. The do-nothing cost is ~5-10 minutes per feature in phase transition prompts.
- **Key Risks:**
  - CLI bridge may solve a phantom problem (YOLO already auto-chains)
  - Merged-phase complexity debt (3+ reviewer contexts in one command)
  - Lost granularity in ENTITY_MACHINES and workflow tests
  - Premature commitment: days to implement correctly, risk of breaking intricate resume-state machinery
- **Recommendation:** Run the minimum experiment: test YOLO end-to-end on one feature. If it works as designed, the problem collapses to "add relevance gate to YOLO" — not a new mode. Only pursue plan+tasks merger if iteration count measurement shows it's actually a bottleneck.
- **Evidence Quality:** strong

## Options Evaluated

| Option | Description | Effort | Risk |
|--------|------------|--------|------|
| A: Add relevance gate to existing YOLO | Add post-implementation verification without new mode concept | Low (1 new agent dispatch) | Low |
| B: Create Turbo as new mode | Third mode with different phase sequence + relevance gate | Medium (new mode, every command updated) | Medium |
| C: Merge plan+tasks into single phase | Combined `/pd:create-plan-tasks` command | High (complex command merge, state machine changes) | High |
| D: Merge plan+tasks + YOLO with relevance gate | Both changes together | Very High | Very High |
| E: Do nothing (YOLO is sufficient) | Current YOLO already auto-chains | Zero | None |

## Decision Matrix

| Criterion (weight) | A: YOLO+gate | B: YOLO with relevance gate | C: Merge phases | D: Both | E: Do nothing |
|---------------------|-------------|---------------|-----------------|---------|---------------|
| Implementation effort (3) | 5 | 3 | 2 | 1 | 5 |
| Regression risk (3) | 5 | 3 | 2 | 1 | 5 |
| User value (2) | 4 | 4 | 3 | 5 | 2 |
| Maintenance burden (2) | 5 | 3 | 2 | 1 | 5 |
| Reuse of existing code (1) | 5 | 4 | 3 | 2 | 5 |
| **Weighted total** | **51** | **35** | **24** | **19** | **45** |

**Option A wins decisively.** Adding a relevance gate to existing YOLO delivers the core value (unattended correct delivery) at minimal cost and risk. "Do nothing" is a strong second — confirming that the problem may be smaller than initially framed.

Plan+tasks merger (Option C) scores poorly due to high regression risk in the most complex commands. It should only be pursued after measuring actual iteration counts.

## Review History
### Review 1 (2026-04-01)
**Findings:**
- [blocker] Relevance gate is undefined — core deliverable is a placeholder (at: FR-2) — Fixed: specified separate agent, deterministic + agent-judged verification, self-validation mitigation
- [blocker] Analysis recommends Option A but requirements describe Option B (YOLO with relevance gate) (at: Requirements, User Stories) — Fixed: aligned all to Option A (enhance YOLO, no new mode concept)
- [warning] YOLO end-to-end experiment not yet run (at: Open Questions) — Acknowledged: experiment is prerequisite before promotion to feature
- [warning] Iteration count overhead claim unverified (at: Problem Statement) — Acknowledged: measurement is prerequisite; plan+tasks merger moved to Deferred/Conditional
- [warning] NFR-2 targets a feature the analysis recommends against (at: NFR-2) — Fixed: removed NFR-2 for merged phase, replaced with relevance gate performance NFR
- [warning] Self-validation research contradicts approach (at: Research Summary) — Fixed: FR-2 now specifies separate agent + deterministic checks to address self-validation bias

**Corrections Applied:**
- Rewrote FR-1/FR-2/FR-3 to describe Option A (YOLO + relevance gate, no new mode)
- Rewrote User Story 1 and UC-1 to remove "YOLO with relevance gate" concept
- Moved FR-4/FR-5/NFR-2 to Deferred/Conditional section
- Specified relevance gate mechanism: separate agent, deterministic checks, structured drift report
- Added self-validation mitigation to FR-2

## Open Questions
- **[Prerequisite before promotion]** Does YOLO actually work end-to-end today without failures? Run the 30-minute experiment on a real simple feature.
- **[Prerequisite for plan+tasks merger]** What is the actual median iteration count for create-plan and create-tasks across completed features? Measure from .review-history.md files.
- ~~What does the relevance verification gate specification look like?~~ → Resolved: FR-2 specifies separate agent + deterministic/agent-judged verification
- ~~Should it be a separate mode toggle or just YOLO + relevance gate?~~ → Resolved: Option A — enhance YOLO, no new mode concept

## Next Steps
1. Run YOLO end-to-end on a real simple feature — validate auto-chaining works
2. Measure median iteration counts from recent .review-history.md files
3. If YOLO works: build Option A (relevance gate addition)
4. If iteration counts are high: evaluate plan+tasks merger as a separate feature
