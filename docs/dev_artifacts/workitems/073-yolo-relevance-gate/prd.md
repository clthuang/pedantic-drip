# PRD: Workflow Hardening — Backward Travel, Pre-Implementation Gate, Taskify

## Status
- Created: 2026-04-01
- Last updated: 2026-04-01
- Status: Draft
- Problem Type: Product/Feature
- Archetype: improving-existing-work

## Problem Statement
pd's workflow pipeline has three structural weaknesses:

1. **Forward-only progression:** Phase reviewers can only approve or iterate within the current phase. If a design reviewer discovers the spec was unclear, or a task reviewer finds the plan's DoD is insufficient, there's no mechanism to send the workflow backward to the root cause. The only option is to force-proceed with warnings, letting upstream deficiencies cascade through implementation.

2. **No pre-implementation relevance check:** The pipeline transitions directly from task breakdown to implementation without verifying that the complete deliverable landscape (spec → design → plan → tasks) is coherent and aligned with the original intent. Implementation is the most expensive phase — starting it with misaligned upstream artifacts wastes the most effort.

3. **Separate plan and tasks phases:** create-plan and create-tasks are independent phases with independent dual-reviewer loops (up to 10 iterations each). For most features they're sequential and tightly coupled. Additionally, task breakdown is useful beyond pd's feature workflow — any plan (including CC plan-mode plans) could benefit from structured taskification.

### Evidence
- Phase reviewers return `{approved, issues, summary}` with no mechanism to reference upstream phases — Evidence: all phase command files
- Force-proceed on cap (iteration 5) propagates unresolved issues downstream — Evidence: e2e audit, workflow-transitions skill
- YOLO auto-chains all phases but has no relevance check before implementation — Evidence: hooks/yolo-guard.sh, all command YOLO overrides
- create-plan and create-tasks have 20 combined max iterations, producing sequential artifacts (plan.md → tasks.md) — Evidence: commands/create-plan.md, create-tasks.md
- Standard vs Full modes run identical review loops — the distinction is cosmetic — Evidence: all phase commands

## Goals
1. Enable phase reviewers to send the workflow backward to any previous phase when the root cause of an issue is upstream, carrying downstream context
2. Add a pre-implementation relevance gate that verifies the full artifact chain (spec → design → plan → tasks) is coherent before implementation begins
3. Merge planning and task breakdown into the existing `/pd:create-plan` phase (produces both plan.md and tasks.md)
4. Create a standalone `/pd:taskify` command that breaks down any plan into atomic tasks with verified DoDs — usable independently of pd's feature workflow

## Success Criteria
- [ ] A phase reviewer can recommend backward travel to a specific upstream phase (e.g., "design needs clarification, send back to specify")
- [ ] Backward travel carries the downstream context (reviewer findings, current artifacts) to the upstream phase as additional input
- [ ] Each backward travel moves only one step forward at a time (no skipping phases on the way back up)
- [ ] Pre-implementation relevance gate verifies spec ACs are testable, design decisions are reflected in tasks, and task DoDs are traceable to spec criteria
- [ ] Relevance gate failure halts YOLO with a structured drift report
- [ ] `/pd:create-plan` produces both plan.md and tasks.md in a single phase (merging current create-plan + create-tasks)
- [ ] `/pd:taskify` works standalone (outside pd workflow) — breaks any plan into atomic tasks with verified DoDs
- [ ] `/pd:taskify` includes a task-reviewer cycle to ensure task quality is foolproof before output
- [ ] Existing review quality is preserved (same skills, agents, reference materials)

## User Stories

### Story 1: Backward Travel on Quality Issues
**As a** developer running the pd workflow **I want** phase reviewers to send work back to the upstream phase that caused the issue **So that** root causes are fixed at the source instead of patched downstream

**Acceptance criteria:**
- Phase reviewer's JSON response can include `backward_to: "specify"` (or any earlier phase) with `reason` and `context`
- The workflow transitions directly to the identified upstream phase (can jump multiple steps — e.g., task reviewer can send work back to specify if that's where the root cause is)
- After fixing, the workflow moves forward one phase at a time (re-running each intermediate phase with the improved upstream artifact)
- No arbitrary count cap on backward jumps — the goal is to produce the most intention-fitting, valuable, and foolproof work. Resource guardrail: total session cost tracked via `yolo_usage_limit` config (existing mechanism) — backward travel consumes the same budget as forward travel

### Story 2: Pre-Implementation Relevance Gate
**As a** developer **I want** verification that my spec, design, plan, and tasks are coherent before implementation starts **So that** I don't waste implementation effort on misaligned artifacts

**Acceptance criteria:**
- After taskify completes (tasks.md produced), a relevance-verifier agent reads the full artifact chain and checks alignment
- Deterministic checks: every spec AC has a traceable task DoD; every design component has tasks; every plan item is decomposed
- Agent-judged checks: DoDs are genuinely verifiable; task instructions are unambiguous; design decisions are reflected in task approach
- If the gate fails, it identifies which upstream artifact has the deficiency and recommends backward travel

### Story 3: Merged Create-Plan Phase
**As a** developer running the pd workflow **I want** `/pd:create-plan` to produce both a plan and task breakdown in one phase **So that** I don't run two separate phases with two separate review loops for tightly coupled artifacts

**Acceptance criteria:**
- `/pd:create-plan` invokes planning skill then breaking-down-tasks skill sequentially
- Produces both plan.md and tasks.md in the feature folder
- Single combined review loop: plan-reviewer → task-reviewer → phase-reviewer (max 5 iterations)
- Occupies one phase slot ("create-plan") in the state machine — `/pd:create-tasks` phase is removed
- Backward travel from task-reviewer can send work back to design if plan gaps trace to design issues

### Story 4: Standalone Taskify
**As a** developer **I want** to run `/pd:taskify` on any plan — including CC plan-mode output, pasted plans, or plan files — **So that** I get foolproof atomic task breakdown without needing the full pd workflow

**Acceptance criteria:**
- `/pd:taskify path/to/plan.md` works without an active pd feature, .meta.json, or entity registry
- Applies the breaking-down-tasks skill to decompose the plan into atomic tasks with well-defined, verifiable DoDs
- Runs a task-reviewer cycle (up to 3 iterations) to ensure every task is unambiguous, sized correctly (5-15 min), has binary DoDs, and has correct dependencies
- Output: tasks.md written alongside the input plan (or to specified output path)
- Does NOT produce plan.md — it takes a plan as input and produces tasks as output

### Story 4: Post-Implementation QA
**As a** developer **I want** 360-degree verification after implementation **So that** the code meets task definitions, spec requirements, and engineering standards

**Acceptance criteria:**
- After implementation, run three verification passes: (1) task-level — each task's DoD met, (2) spec-level — acceptance criteria satisfied, (3) engineering-level — code quality, security, standards
- This replaces the current 3-reviewer loop (implementation-reviewer, code-quality-reviewer, security-reviewer) with a more structured approach
- Failures identify the specific artifact level where the gap exists

## Use Cases

### UC-1: Backward Travel During Task Review
**Actors:** Developer, task-reviewer agent
**Flow:** 1. Task reviewer finds "DoD for task T3 says 'config works' — not verifiable" 2. Reviewer traces root cause: spec AC-2 says "configuration is correct" without defining what correct means 3. Reviewer returns `{approved: false, backward_to: "specify", reason: "AC-2 is not testable", context: "Task T3 DoD inherits vagueness from spec AC-2"}` 4. Workflow transitions back to specify phase with reviewer context injected 5. Spec is revised to make AC-2 testable 6. Workflow moves forward: specify → design (re-run with updated spec) → taskify (re-run) → relevance gate
**Postconditions:** Root cause fixed at source, all downstream artifacts updated

### UC-2: Pre-Implementation Gate Catches Misalignment
**Actors:** Developer, relevance-verifier agent
**Flow:** 1. Taskify produces tasks.md 2. Relevance gate reads spec.md + design.md + plan.md + tasks.md 3. Gate finds: design component C3 has no corresponding tasks 4. Gate returns `{pass: false, gaps: [{type: "missing_coverage", source: "design.md C3", detail: "No tasks implement the generate-mcp-config.sh component"}]}` 5. In YOLO: halts with drift report. In interactive: user decides whether to fix or proceed.

### UC-3: Standalone Taskify on CC Plan-Mode Output
**Actors:** Developer
**Flow:** 1. Developer exits CC plan mode with a plan 2. Developer runs `/pd:taskify agent_sandbox/plan.md` 3. Taskify reads the plan, applies breaking-down-tasks skill to decompose into atomic tasks 4. Task-reviewer validates quality (up to 3 iterations): executability, DoD verifiability, dependency accuracy 5. Produces tasks.md with dependency graph, parallel groups, and foolproof task details 6. No pd feature context needed
**Postconditions:** tasks.md alongside the input plan, all tasks verified by reviewer

## Edge Cases & Error Handling
| Scenario | Expected Behavior | Rationale |
|----------|-------------------|-----------|
| Backward travel resource exhaustion | `yolo_usage_limit` halts the session when cost budget is exceeded — applies equally to forward and backward travel | Resource guardrail, not quality limiter |
| Backward travel ping-pong (same phase sent back repeatedly) | Each backward jump logged with reason — if same source→target pair occurs 3 times with no artifact change, reviewer must escalate or approve with warnings | Prevents literal infinite loops without capping genuine refinement |
| Backward travel to brainstorm | Allowed but skips brainstorm's research stages (already done); focuses on clarifying intent | Research is expensive and already completed |
| Relevance gate partial failure | Reports which checks passed and which failed; doesn't block entirely on minor gaps | Some gaps are acceptable (suggestions vs blockers) |
| Standalone taskify on unstructured text | Best-effort decomposition; warns "input lacks structured plan format" | Graceful degradation for informal plans |
| Standalone taskify with --spec/--design | Task-reviewer uses additional context for traceability checks | Richer validation when upstream artifacts available |
| Standalone taskify reviewer finds unfixable issues | After 3 iterations, outputs best-effort tasks.md with warnings | Standalone mode shouldn't block indefinitely |
| YOLO + backward travel | Auto-accepts backward travel recommendation; re-runs upstream phase in YOLO mode | Backward travel is a quality improvement, not a human decision point |
| Post-implementation QA finds spec-level gap | Recommends backward travel to specify (if backward budget remaining) or reports as unresolved | QA is the last safety net before merge |

## Constraints
### Behavioral Constraints (Must NOT do)
- Backward travel must carry context — the upstream phase receives the downstream findings, not just "go back and fix it"
- Backward travel can jump directly to any earlier phase (reviewer identifies root cause). Forward re-run after fix must go one phase at a time (no skipping intermediate phases)
- `/pd:taskify` standalone mode must NOT require .meta.json, entity registry, or active feature state — it's a general-purpose tool
- Post-implementation QA must use a separate agent from the implementer (self-validation prevention)

### Technical Constraints
- Phase state machine (ENTITY_MACHINES) must support backward transitions — currently only forward — Evidence: workflow_engine/engine.py
- Backward travel needs a new field in phase reviewer response schema: `backward_to` — Evidence: all reviewer agent prompts
- Merging create-tasks into create-plan requires ENTITY_MACHINES update (remove create-tasks phase), transition gate changes, and test updates — Evidence: CLAUDE.md gotchas
- `/pd:taskify` is a standalone command (not a workflow phase) — it has no phase state machine entry
- Existing planning and breaking-down-tasks skills are reused — no new skills created

## Requirements

### Functional

**Backward Travel:**
- FR-1: Extend phase reviewer response schema to include optional `backward_to` field (phase name) and `backward_context` (structured findings for the upstream phase)
- FR-2: When a reviewer recommends backward travel, the workflow transitions to the target phase, injecting `backward_context` as additional input alongside existing artifacts
- FR-3: After the upstream phase completes, the workflow moves forward one phase at a time, re-running each intermediate phase (with updated upstream artifacts as input)
- FR-4: No arbitrary cap on backward travel count. The resource guardrail is `yolo_usage_limit` (existing config) — backward travel consumes the same token/cost budget as forward travel. Each backward jump is logged in .meta.json (`backward_history` array) for audit/retro purposes, tracking: which phase sent back, to where, why, and what context was carried.
- FR-5: In YOLO mode, backward travel is auto-accepted (no user prompt). The upstream phase runs in YOLO mode with backward context injected.

**Pre-Implementation Relevance Gate:**
- FR-6: After taskify completes, dispatch a relevance-verifier agent that reads the full artifact chain (spec.md, design.md, plan.md, tasks.md) and checks:
  - Coverage: every spec AC has ≥1 task with traceable DoD
  - Completeness: every design component has ≥1 task
  - Testability: every task DoD is binary and verifiable
  - Coherence: task approaches reflect design decisions (not contradicting them)
- FR-7: Relevance gate returns structured results per check. Blocker failures halt YOLO via safety keyword "relevance verification failed". The gate may recommend backward travel to the specific upstream phase with the deficiency.
- FR-8: In interactive mode, relevance gate results are presented to user who decides: proceed, fix locally, or accept backward travel recommendation.

**Merged Create-Plan (absorbs create-tasks):**
- FR-9: Extend `/pd:create-plan` to invoke both planning skill and breaking-down-tasks skill sequentially. Produces plan.md and tasks.md as separate artifacts in a single phase.
- FR-10: Review loop: plan-reviewer runs first (validates plan quality), then task-reviewer (validates task breakdown), then phase-reviewer (validates handoff readiness for implementation). Max 5 iterations for the combined loop.
- FR-11: Remove `/pd:create-tasks` as a separate command and phase. The "create-tasks" phase is removed from ENTITY_MACHINES. `/pd:create-plan` occupies the single phase slot and outputs both artifacts.
- FR-12: Backward compatibility: if someone runs `/pd:create-tasks`, show deprecation notice directing them to `/pd:create-plan`.

**Standalone Taskify:**
- FR-13: Create `/pd:taskify` as a standalone command (not a workflow phase). Accepts a file path argument pointing to any plan — CC plan-mode output, pasted plans, or plan files.
- FR-14: `/pd:taskify` applies the breaking-down-tasks skill to decompose the input plan into atomic tasks with well-defined, verifiable DoDs. It does NOT invoke the planning skill (the plan already exists as input).
- FR-15: `/pd:taskify` includes a built-in task-reviewer cycle (up to 3 iterations) that validates: task executability, 5-15 min sizing, binary DoDs, dependency accuracy, and traceability to plan items. The reviewer runs automatically — no user prompt needed.
- FR-16: `/pd:taskify` requires no pd context — no .meta.json, no entity registry, no MCP calls, no active feature. Output (tasks.md) written alongside the input file or to a specified output path.
- FR-17: `/pd:taskify` can optionally accept `--spec=path` and `--design=path` arguments to give the task-reviewer additional context for traceability validation. These are optional — without them, traceability checks are limited to plan-to-task coverage only.

**Post-Implementation QA:**
- FR-18: After implementation phase, run a 360-degree QA pass with three verification levels:
  - Task-level: each task's DoD criteria verified against actual implementation
  - Spec-level: each spec acceptance criterion verified (deterministic checks where possible)
  - Standards-level: code quality and security review (existing reviewers reused)
- FR-19: QA failures at task or spec level may recommend backward travel (if budget remaining). Standards-level failures are fixed in-place (no backward travel for code style issues).

### Non-Functional
- NFR-1: Backward travel adds ≤ 1 phase transition overhead per backward step (no batch re-computation)
- NFR-2: Relevance gate completes within 60 seconds (reads artifacts, no code execution)
- NFR-3: `/pd:taskify` standalone mode completes within the same time as current create-plan + create-tasks combined
- NFR-4: No new Python dependencies

## Non-Goals
- Replacing the existing phase sequence — backward travel extends it, doesn't change the forward order
- Automated rollback of git commits on backward travel — only phase state changes, not git history
- Making every phase reviewer aware of all upstream artifacts — only the backward context is injected, not the full artifact chain (that's the relevance gate's job)
- Building a standalone relevance-verifier CLI tool — it's an agent dispatch within the workflow

## Out of Scope (This Release)
- Backward travel across feature boundaries (e.g., from a decomposed feature back to the parent project PRD)
- Relevance gate for brainstorm → specify transition (brainstorm quality is handled by prd-reviewer)
- `/pd:taskify` integration with external task management systems (Linear, Jira)
- Adaptive reviewer iteration budgets based on feature complexity

## Research Summary
### Internet Research
- Spec-driven verification: 4-stage pipeline with separate verifier agent — prevents self-congratulation — Source: agent-wars.com
- Test-Driven Agentic Development (TDAD): spec as executable contracts; agent implements against criteria it did not write — Source: Medium
- McKinsey QuantumBlack: evaluation gate between each step; human review only at end — Source: Medium
- Deterministic workflow pattern: commands/checks run deterministically; only code generation is probabilistic — Source: sedkodes.com

### Codebase Analysis
- YOLO auto-chains via [YOLO_MODE] arg propagation + yolo-guard.sh hook — Location: all phase commands
- Safety valve keywords prevent YOLO from overriding critical failures — Location: hooks/yolo-guard.sh:54-88
- Phase state machine only supports forward transitions — Location: workflow_engine/engine.py
- create-plan and create-tasks: 20 combined max iterations, sequential artifacts — Location: commands/
- Planning skill + breaking-down-tasks skill are independent, sequential — Location: skills/
- All phase reviewers use identical response schema (approved/issues/summary) with no backward reference — Location: all reviewer agents
- Force-proceed on cap (iteration 5) cascades issues downstream — Location: workflow-transitions skill

### Existing Capabilities
- YOLO mode auto-chains all phases with safety valves
- skippedPhases infrastructure tracks phase skips in .meta.json
- Phase-reviewer soft cap at iteration 3+
- Implementation phase has 3-reviewer validation (implementation, code-quality, security)

## Current State Assessment

### What Works Today
- Forward-only phase progression with quality gates at each boundary
- Two-step reviewer loops (domain + phase) catch phase-local issues
- YOLO auto-chains the full pipeline end-to-end

### What's Missing
- **No backward travel:** Reviewers can flag upstream issues but can't route the workflow back to fix them. Force-proceed on cap propagates deficiencies.
- **No pre-implementation coherence check:** The full artifact chain isn't verified as a whole before the most expensive phase begins.
- **Separate plan/tasks overhead:** Two phases with independent review loops for tightly coupled artifacts.
- **No standalone taskification:** Task breakdown is locked inside pd's feature workflow.

### Change Impact
- **Backward travel:** Extends phase reviewer schema, adds backward transition support to workflow engine, adds context injection for upstream phases. Requires ENTITY_MACHINES update for backward transitions and .meta.json tracking of backward count.
- **Relevance gate:** New agent + dispatch point between create-plan and implement. Integrates with backward travel (can recommend going back).
- **Merged create-plan:** Absorbs create-tasks into create-plan. Removes "create-tasks" from ENTITY_MACHINES. create-plan command gains task breakdown + task-reviewer. Produces both plan.md and tasks.md.
- **Standalone taskify:** New command, not a workflow phase. No state machine changes. Uses breaking-down-tasks skill + task-reviewer. Standalone entry point for any plan.
- **Post-implementation QA:** Restructures the existing 3-reviewer loop into a layered verification (task → spec → standards). Reuses existing reviewer agents.

### Migration Path
1. **Standalone taskify first** — new command, zero risk to existing workflow. Validates the task-reviewer cycle works independently.
2. **Merge create-tasks into create-plan** — absorb task breakdown into create-plan, remove create-tasks phase from state machine
3. **Relevance gate** — add pre-implementation check after merged create-plan
4. **Backward travel** — extend phase reviewer schema, add backward transitions
5. **Post-implementation QA** — restructure implementation review into layered verification
6. **Deprecate** — remove /pd:create-tasks command after merge is proven

## Proposed Workflow

```
brainstorm → specify → design → create-plan → RELEVANCE → implement → 360 QA → finish
                                (plan+tasks)     GATE
     ▲           ▲         ▲        │                                    │
     │           │         │        │                                    │
     └───────────┴─────────┴────────┘                                    │
         backward travel (max 2)                                         │
         carries downstream context                                      │
         re-runs forward 1 step at a time                               │
                                                         ┌───────┴───────┐
                                                       PASS             FAIL
                                                         │               │
                                                      finish          backward travel
                                                                      or halt

Standalone (outside pd workflow):
  /pd:taskify plan.md  →  task-reviewer (3 iter)  →  tasks.md
```

## Review History
### Review 1 (2026-04-01) — from original PRD version
- [blocker] Relevance gate undefined → Fixed: specified separate agent with deterministic + agent-judged checks
- [blocker] Option A/B misalignment → Fixed: this revision adopts a unified approach incorporating all three changes

### Review 2 (2026-04-01) — user direction change
- Backward travel added as FR-1 through FR-5
- Relevance gate moved from post-implementation to pre-implementation (between taskify and implement)
- Plan+tasks merger confirmed (no longer deferred) as `/pd:taskify`
- `/pd:taskify` standalone mode added (works outside pd workflow)
- Post-implementation QA added as 360-degree verification (task + spec + standards levels)
- Decision matrix from original PRD superseded by user direction

## Open Questions
- How does backward travel interact with git commits? Each phase commits artifacts — backward travel means re-running on committed files. Should backward phases amend commits or create new ones?
- ~~Should `/pd:taskify` standalone mode produce a plan.md?~~ → Resolved: No — taskify takes a plan as input and produces tasks as output. Planning stays in `/pd:create-plan`.
- ~~What is the maximum backward travel depth?~~ → Resolved: No arbitrary cap. Resource guardrail via `yolo_usage_limit`. Ping-pong detection (same pair 3x with no change) prevents literal loops.
- Should post-implementation QA replace the existing 3-reviewer loop entirely, or run alongside it?
- How does backward travel affect .review-history.md? Should it append "backward travel" entries or start a fresh review section?

## Next Steps
Ready for /pd:specify to define precise acceptance criteria and scope boundaries.
