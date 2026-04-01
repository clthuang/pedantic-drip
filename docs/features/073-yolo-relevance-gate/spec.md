# Specification: Workflow Hardening — Backward Travel, Pre-Implementation Gate, Taskify

## Problem Statement
pd's workflow is forward-only with no mechanism to route work back to the upstream root cause when a downstream reviewer discovers a deficiency. Combined with no pre-implementation coherence check and separate plan/tasks phases, this leads to cascading quality issues and wasted implementation effort.

## Success Criteria
- [ ] Phase reviewers can recommend backward travel to any earlier phase with structured context
- [ ] Backward travel re-runs each intermediate phase forward one at a time after the fix
- [ ] Resource guardrail (`yolo_usage_limit`) caps backward travel cost — no arbitrary count limit
- [ ] Pre-implementation relevance gate catches spec↔tasks misalignment before code is written
- [ ] `/pd:create-plan` produces both plan.md and tasks.md in a single phase
- [ ] `/pd:taskify` works standalone on any plan file with built-in task-reviewer quality cycle
- [ ] Post-implementation 360 QA verifies at task, spec, and standards levels
- [ ] All changes are backward-compatible — existing completed features unaffected

## Scope

### In Scope

**A. Backward Travel**
- Extend phase reviewer response schema with `backward_to` and `backward_context` fields
- Backward transition triggering: phase command orchestration (not workflow engine) parses reviewer response for `backward_to` and initiates the backward transition. This logic lives in the shared workflow-transitions skill (commitAndComplete or a new handleReviewerResponse step), not in individual phase commands.
- Context injection mechanism: backward_context is written to `{feature_dir}/.backward-context.json`. Phase commands read this file when present and include its contents as additional input alongside existing artifacts. The file is deleted after the phase completes successfully.
- Forward re-run orchestration: entity metadata stores `backward_return_target` (the phase that initiated the backward travel). After the upstream fix, the orchestrator advances one phase at a time until reaching backward_return_target, then resumes normal flow. This is NEW orchestration logic — not covered by existing complete_phase().
- Ping-pong detection via artifact hashing: SHA-256 hash of target phase's output artifact stored in backward_history entries. If same source→target pair occurs 3x with same artifact hash → escalate.
- Backward context carries only the most recent backward travel context (not accumulated). Previous contexts preserved in backward_history for audit but not injected into prompts.
- YOLO auto-accepts backward travel recommendations

**B. Pre-Implementation Relevance Gate**
- New `relevance-verifier` agent dispatched between create-plan and implement phases
- Reads full artifact chain: spec.md, design.md, plan.md, tasks.md
- Checks: coverage (spec ACs → task DoDs), completeness (design components → tasks), testability (binary DoDs), coherence (task approaches reflect design decisions)
- Can recommend backward travel to specific upstream phase
- Halts YOLO via safety keyword "relevance verification failed"

**C. Merged Create-Plan**
- `/pd:create-plan` invokes planning skill then breaking-down-tasks skill sequentially
- Produces plan.md and tasks.md as separate artifacts
- Combined review: plan-reviewer → task-reviewer → phase-reviewer (max 5 iterations)
- Remove `create-tasks` phase from PHASE_SEQUENCE and workflow_phases CHECK constraint
- Update all references to create-tasks across the codebase:
  - `transition_gate/constants.py`: PHASE_SEQUENCE (remove create_tasks), HARD_PREREQUISITES (remove create-tasks entry; create-plan prereqs remain ["spec.md", "design.md"]; implement prereqs remain ["spec.md", "tasks.md"] since tasks.md is now produced by create-plan), ARTIFACT_PHASE_MAP (restructure from 1:1 dict to 1:many — create-plan maps to ["plan.md", "tasks.md"]; update reverse lookup in gate.py:160 accordingly), GUARD_METADATA (all guards referencing create-tasks in affected_phases have it replaced with create-plan: G-04, G-08, G-11, G-17, G-18, G-22, G-23, G-25, G-36, G-37, G-45, G-50, G-51, G-60)
  - `entity_registry/frontmatter_inject.py`: Update ARTIFACT_PHASE_MAP to map "tasks" → "create-plan" (currently maps to "create-tasks"). Update test assertions in test_frontmatter.py and test_frontmatter_sync.py.
  - `workflow_phases` CHECK constraint: DB migration to remove 'create-tasks' from valid values
  - Test files: test_gate.py, test_constants.py, test_entity_lifecycle.py, test_workflow_state_server.py, test_engine.py
- Deprecation redirect if `/pd:create-tasks` is invoked

**D. Standalone Taskify**
- New `/pd:taskify` command — not a workflow phase
- Input: any plan file path (CC plan-mode output, pasted plans, etc.)
- Applies breaking-down-tasks skill (NOT planning skill — plan already exists)
- Built-in task-reviewer cycle (up to 3 iterations)
- No pd context required (no .meta.json, no MCP, no entity registry)
- Optional `--spec=` and `--design=` for richer traceability validation

**E. Post-Implementation 360 QA**
- Three sequential verification levels after implementation:
  1. Task-level: `implementation-reviewer` agent reads tasks.md DoDs and verifies each against actual code changes (git diff + file reads)
  2. Spec-level: `relevance-verifier` agent (same agent as pre-impl gate) reads spec.md ACs and verifies against implementation. Uses deterministic checks (test execution, build) where possible, agent-judged for the rest.
  3. Standards-level: existing `code-quality-reviewer` + `security-reviewer` agents (unchanged from current 3-reviewer loop)
- Task and spec failures may recommend backward travel
- Standards failures fixed in-place
- This restructures (not replaces) the current 3-reviewer loop by adding task-level and spec-level verification as a first pass before the standards review

### Out of Scope
- Backward travel across feature boundaries
- Relevance gate for brainstorm → specify transition
- `/pd:taskify` integration with external task systems
- Adaptive reviewer iteration budgets
- Extracting metadata JSON blob into structured DB tables (backlog #00051)
- Automated git rollback on backward travel. Note: backward travel phases create new commits (standard phase behavior). Existing commits from prior forward runs are not amended or reverted. Git history accumulates naturally.

## Acceptance Criteria

### A. Backward Travel

#### AC-A1: Reviewer Schema Extension
- Given a phase reviewer completes its review
- When the root cause of an issue is in an upstream phase
- Then the reviewer's JSON response includes `backward_to: "{phase_name}"` and `backward_context: {structured findings}`
- And the `backward_to` value is a valid phase name earlier in the sequence than the current phase

#### AC-A2: Backward Transition Execution
- Given a reviewer recommends `backward_to: "specify"`
- When the phase command's orchestration logic (in workflow-transitions skill) processes this recommendation
- Then it writes `backward_context` to `{feature_dir}/.backward-context.json` with schema: `{source_phase, target_phase, findings, original_reviewer_response}`
- And it stores `backward_return_target` in entity metadata (the phase that initiated backward travel)
- And it invokes the target phase command (e.g., `/pd:specify`) with the backward context file present
- And the target phase reads `.backward-context.json` and includes its contents as additional input alongside existing artifacts
- And when the target is `brainstorm`, the phase runs in clarification mode (skipping research stages — already completed). backward_context indicates this is a refinement, not a fresh brainstorm.

#### AC-A3: Forward Re-Run After Fix
- Given the upstream phase (specify) completes after a backward travel fix
- When the orchestration logic checks entity metadata for `backward_return_target`
- Then it advances one phase at a time: specify → design → create-plan
- And each intermediate phase re-runs fully (produces complete new artifacts, not incremental diffs)
- And `.backward-context.json` is deleted after the upstream phase completes (not carried forward)
- And when the workflow reaches `backward_return_target`, it clears the field and resumes normal flow

#### AC-A4: Resource Guardrail
- Given YOLO mode is active with `yolo_usage_limit` configured
- When backward travel consumes tokens
- Then backward travel is counted against the same budget as forward travel
- And no separate backward travel counter or cap exists

#### AC-A5: Ping-Pong Detection
- Given the same backward travel pair (e.g., create-plan → specify) occurs 3 times
- When the SHA-256 hash of the target phase's output artifact (e.g., spec.md) is identical between the 2nd and 3rd backward travel
- Then the reviewer must either escalate to user or approve with warnings
- And the workflow does not loop again on the same pair without artifact change
- And hashes are stored in `backward_history` entries in entity metadata for comparison
- And hash is computed over all output artifacts of the target phase concatenated in alphabetical order by filename (e.g., for create-plan: plan.md + tasks.md)

#### AC-A6: Backward History Audit
- Given backward travel occurs during a feature's lifecycle
- When the feature's entity metadata is queried
- Then `backward_history` array contains entries with: source_phase, target_phase, reason, timestamp, context_summary

#### AC-A7: YOLO Backward Travel
- Given YOLO mode is active and a reviewer recommends backward travel
- When the YOLO guard processes the recommendation
- Then backward travel is auto-accepted (no AskUserQuestion prompt)
- And the target phase runs in YOLO mode with backward context injected

### B. Pre-Implementation Relevance Gate

#### AC-B1: Gate Trigger
- Given create-plan phase completes (producing both plan.md and tasks.md)
- When the workflow transitions toward implement
- Then a relevance-verifier agent is dispatched before implementation begins

#### AC-B2: Coverage Check
- Given spec.md has 5 acceptance criteria
- When the relevance gate runs
- Then it verifies each spec AC has ≥1 task with a DoD that traces to it
- And reports which ACs are covered and which are not

#### AC-B3: Completeness Check
- Given design.md defines 4 components
- When the relevance gate runs
- Then it verifies each design component has ≥1 task
- And reports which components are covered and which are not

#### AC-B4: Testability Check
- Given tasks.md has 8 tasks
- When the relevance gate runs
- Then it verifies each task's DoD is binary (pass/fail, not subjective)
- And flags any DoD containing vague language ("works properly", "is correct", "handles appropriately")

#### AC-B5: Coherence Check
- Given design.md specifies "use filesystem scan for feature detection"
- When the relevance gate runs
- Then it verifies no task contradicts this (e.g., a task saying "query entity DB for active features")

#### AC-B6: Gate Failure with Backward Travel
- Given the relevance gate finds a blocker (e.g., spec AC-3 has no traceable task)
- When the gate reports failure
- Then the report identifies the upstream source of the gap (spec.md, design.md, or plan.md)
- And recommends backward travel to the specific phase
- And in YOLO mode, the orchestration code (not the agent) emits a user-visible message containing safety keyword "relevance verification failed" after receiving a blocker failure from the relevance-verifier agent, which triggers yolo-guard.sh to halt auto-chaining

#### AC-B7: Gate Pass
- Given all checks pass (coverage, completeness, testability, coherence)
- When the gate reports success
- Then the workflow proceeds to implement phase without interruption

### C. Merged Create-Plan

#### AC-C1: Dual Artifact Production
- Given design.md is complete
- When `/pd:create-plan` runs
- Then it produces both plan.md (staged implementation order with dependencies) and tasks.md (atomic tasks with DoDs)

#### AC-C2: Sequential Skill Invocation
- Given `/pd:create-plan` starts
- When it invokes skills
- Then it runs planning skill first (produces plan.md), then breaking-down-tasks skill (produces tasks.md from plan.md)
- And both existing skills are used unmodified

#### AC-C3: Combined Review Loop
- Given plan.md and tasks.md are produced
- When the review loop runs
- Then plan-reviewer validates plan quality first
- Then task-reviewer validates task breakdown quality
- Then phase-reviewer validates handoff readiness for implementation
- And max 5 iterations for the combined loop

#### AC-C4: Phase State Machine Update
- Given the feature workflow
- When PHASE_SEQUENCE is evaluated
- Then it contains: brainstorm, specify, design, create-plan, implement, finish
- And `create-tasks` is not present
- And `workflow_phases` CHECK constraint allows `create-plan` but not `create-tasks`

#### AC-C5: Deprecation Redirect
- Given a user runs `/pd:create-tasks`
- When the command loads
- Then it outputs: "Note: /pd:create-tasks has been merged into /pd:create-plan. Redirecting..."
- And automatically invokes `/pd:create-plan` with the same arguments (redirect, not block)

### D. Standalone Taskify

#### AC-D1: Standalone Execution
- Given a plan file at `agent_sandbox/my-plan.md`
- When the user runs `/pd:taskify agent_sandbox/my-plan.md`
- Then tasks.md is produced alongside the input file (at `agent_sandbox/tasks.md`)
- And no .meta.json, entity registry, or MCP calls are made

#### AC-D2: Task-Reviewer Quality Cycle
- Given `/pd:taskify` produces tasks.md
- When the built-in task-reviewer runs
- Then it validates: executability, 5-15 min sizing, binary DoDs, dependency accuracy, plan traceability
- And iterates up to 3 times, auto-correcting issues between iterations
- And outputs the final tasks.md only after reviewer approval or 3 iterations exhausted

#### AC-D3: Optional Context Arguments
- Given the user runs `/pd:taskify plan.md --spec=spec.md --design=design.md`
- When the task-reviewer runs
- Then it uses spec.md and design.md for richer traceability validation (spec ACs → task DoDs, design components → tasks)

#### AC-D4: CC Plan-Mode Compatibility
- Given a plan produced by Claude Code's plan mode (unstructured markdown)
- When `/pd:taskify` processes it
- Then it produces structured tasks.md with dependency graph, parallel groups, and atomic task details
- And warns if the input lacks structured plan format but still produces best-effort output

#### AC-D5: Output Path Override
- Given the user runs `/pd:taskify plan.md --output=docs/tasks.md`
- When tasks.md is produced
- Then it is written to `docs/tasks.md` instead of alongside the input file

### E. Post-Implementation 360 QA

#### AC-E1: Task-Level Verification
- Given implementation is complete
- When 360 QA runs
- Then it reads tasks.md and verifies each task's DoD criteria against the actual implementation
- And reports pass/fail per task with evidence

#### AC-E2: Spec-Level Verification
- Given implementation is complete
- When 360 QA runs
- Then it reads spec.md acceptance criteria and verifies each against the implementation
- And uses deterministic checks where possible (test execution, build verification)
- And uses agent-judged assessment for non-mechanically-testable criteria

#### AC-E3: Standards-Level Verification
- Given implementation is complete
- When 360 QA runs
- Then it runs code quality and security review (reusing existing reviewer agents)
- And reports issues at standards level

#### AC-E4: Backward Travel from QA
- Given 360 QA finds a spec-level gap (e.g., AC-3 not satisfied)
- When the gap is reported
- Then QA may recommend backward travel to specify (or the appropriate upstream phase)
- And backward travel follows the same rules as in-workflow backward travel (AC-A2 through AC-A7)

#### AC-E5: Standards Fixed In-Place
- Given 360 QA finds a standards-level issue (code quality, naming, security)
- When the issue is reported
- Then it is fixed in the current implementation phase (no backward travel for style issues)

## Feasibility Assessment

### Assessment
**Overall:** Likely
**Reasoning:**
- Backward travel: G-18 allows backward transitions (warns, doesn't block). `complete_phase()` handles backward re-runs. However, **forward re-run orchestration is novel** — no existing mechanism drives one-phase-at-a-time advancement back to the return target. This requires new orchestration logic in the workflow-transitions skill, a `backward_return_target` field in entity metadata, and `.backward-context.json` storage/injection. This is the core new work.
- Relevance gate: Single new agent dispatch reading existing artifacts. Well-understood pattern (similar to existing reviewer dispatches).
- Merged create-plan: Both skills already exist. The merge is command-level orchestration, not skill changes. PHASE_SEQUENCE update + DB migration are well-documented patterns (8 prior migrations).
- Standalone taskify: breaking-down-tasks skill + task-reviewer agent already exist. The new command is a thin wrapper.
- 360 QA: Restructuring existing 3-reviewer loop. Agents already exist.

**Key Assumptions:**
- Backward transition support in workflow engine is sufficient (G-18 warns, doesn't block) — Status: Verified at transition_gate/gate.py:267-287
- `complete_phase()` handles backward re-runs — Status: Verified at workflow_engine/engine.py:134-147
- `workflow_phases` CHECK constraint migration is straightforward — Status: Verified (8 prior migrations exist as templates)
- Existing reviewer agents can produce `backward_to` field with prompt changes only — Status: Needs verification during implementation

**Open Risks:**
- **[Highest risk]** Forward re-run orchestration after backward travel is novel — no existing pattern in the codebase. Design phase should prototype this orchestration loop in workflow-transitions skill before detailing other components.
- Context injection bloat mitigated by resolved decision: most recent context only, not accumulated

## Dependencies
- Existing planning skill (`skills/planning/SKILL.md`)
- Existing breaking-down-tasks skill (`skills/breaking-down-tasks/SKILL.md`)
- Existing reviewer agents (plan-reviewer, task-reviewer, phase-reviewer, implementation-reviewer, code-quality-reviewer, security-reviewer)
- `workflow_engine/engine.py` backward transition support (G-18)
- `entity_registry/database.py` migration infrastructure

## Open Questions (Resolved)
- ~~How should backward context accumulate across multiple backward jumps?~~ → Resolved: Most recent context only. Previous contexts preserved in `backward_history` for audit but not injected into prompts. Bounds prompt size while maintaining audit trail.
- ~~Should the relevance gate be skippable in interactive mode?~~ → Resolved: Gate always runs. In interactive mode, user can choose to proceed despite failures (same pattern as phase reviewers). No skip mechanism — the gate runs, results are presented, user decides.
- ~~How does forward re-run handle design.md when sent back to specify?~~ → Resolved: Each intermediate phase re-runs fully, producing complete new artifacts (not incremental diffs). This matches existing phase behavior — phases always produce complete artifacts.
