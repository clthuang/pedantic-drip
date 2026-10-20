# Plan: Workflow Hardening — Backward Travel, Pre-Implementation Gate, Taskify

## Implementation Order

### Stage 0: Infrastructure (no dependencies)
Foundation changes that all other stages depend on.

1. **Remove create-tasks from PHASE_SEQUENCE and constants** — Update transition gate infrastructure
   - **Why this item:** All downstream changes (merged create-plan, backward travel, relevance gate) depend on the correct phase sequence
   - **Why this order:** Must happen first — constants.py is imported by every workflow component
   - **Deliverable:** Updated PHASE_SEQUENCE (6 phases: brainstorm, specify, design, create-plan, implement, finish), ARTIFACT_PHASE_MAP restructured to dict[str, list[str]], HARD_PREREQUISITES updated, GUARD_METADATA (14 guards) updated, PHASE_GUARD_MAP updated, reverse lookup in gate.py:160 changed to flattening comprehension
   - **Complexity:** Medium (many cross-references but mechanical)
   - **Files:** `transition_gate/constants.py`, `transition_gate/gate.py`
   - **Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/transition_gate/ -v` — all existing tests updated and passing

2. **Update frontmatter_inject.py ARTIFACT_PHASE_MAP** — Align artifact→phase mapping
   - **Why this item:** Frontmatter sync depends on correct artifact→phase mapping
   - **Why this order:** Parallel with item 1 (independent file)
   - **Deliverable:** Update "tasks" → "create-plan" (from "create-tasks") in frontmatter_inject.py
   - **Complexity:** Simple
   - **Files:** `entity_registry/frontmatter_inject.py`
   - **Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_frontmatter*.py -v`

3. **DB migration: remove create-tasks from workflow_phases CHECK constraint** — Schema update
   - **Why this item:** workflow_phases table rejects 'create-tasks' as invalid after phase removal
   - **Why this order:** Parallel with items 1-2 (independent layer)
   - **Deliverable:** Migration 9: ALTER workflow_phases CHECK constraint to remove 'create-tasks'. Existing rows with 'create-tasks' migrated to 'create-plan'.
   - **Complexity:** Medium (follows 8 prior migration templates but requires careful constraint handling)
   - **Files:** `entity_registry/database.py`
   - **Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v`

4. **Update _EXPECTED_ARTIFACTS and backfill.py** — Fix finish-phase artifact validation and backfill phase sequence
   - **Why this item:** Finish phase checks expected artifacts per mode; backfill.py has its own hardcoded phase sequence with _derive_next_phase() returning create-tasks
   - **Why this order:** After item 1 (depends on PHASE_SEQUENCE change)
   - **Deliverable:** Update _EXPECTED_ARTIFACTS in workflow_state_server.py. Update backfill.py phase sequence (line 33) to remove create-tasks. Update test_backfill.py assertions (lines 1857-1869, 1885).
   - **Complexity:** Simple
   - **Files:** `mcp/workflow_state_server.py`, `entity_registry/backfill.py`, `entity_registry/test_backfill.py`
   - **Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py plugins/pd/hooks/lib/entity_registry/test_backfill.py -v`

5. **Sweep all remaining create-tasks references** — Comprehensive cross-codebase update
   - **Why this item:** ~200 occurrences of 'create-tasks' across ~46 files — items 1-4 cover infrastructure but skills, commands, hooks, workflow_engine, UI, doctor, and test files also reference the old phase
   - **Why this order:** After items 1-4 (infrastructure correct first, then sweep consumers)
   - **Deliverable:** Update all references in: skills/ (workflow-transitions, planning, implementing, reviewing-artifacts, workflow-state), commands/ (create-plan.md, secretary.md, show-status.md, list-features.md), hooks/ (session-start.sh, yolo-stop.sh), workflow_engine/ (templates.py, kanban.py), and test files (test_reconciliation.py, test_entity_engine.py, test_kanban.py, test_rollup.py)
   - **Complexity:** Medium (many files but mechanical find-and-replace with semantic verification)
   - **Files:** ~20 files across skills/, commands/, hooks/, workflow_engine/
   - **Verification:** `grep -rn 'create.tasks' plugins/pd/ --include='*.py' --include='*.md' --include='*.sh' | grep -v '.venv' | wc -l` should be ≤1 (only deprecation stub). Includes test files — stale test references cause failures. Then run full test suite.

### Stage 1: Standalone Taskify (NO dependencies — can run in parallel with Stage 0)
New command with zero risk to existing workflow. Validates task-reviewer cycle independently.

6. **Create /pd:taskify command** — Standalone task breakdown with quality review
   - **Why this item:** Design C4 — standalone taskify is the lowest-risk component (new command, no state machine changes)
   - **Why this order:** Migration path step 1: validate task-reviewer cycle works independently before merging into create-plan
   - **Deliverable:** New `commands/taskify.md` that accepts any plan file, applies breaking-down-tasks skill, runs task-reviewer (max 3 iterations), outputs tasks.md. Optional --spec/--design args. No MCP, no .meta.json.
   - **Complexity:** Medium (new command orchestration + built-in reviewer cycle)
   - **Files:** `commands/taskify.md`
   - **Verification:** Run `/pd:taskify` on a sample plan file, verify tasks.md produced with dependency graph and atomic task details. Run with --spec and --design to verify richer traceability.

### Stage 2: Merged Create-Plan (depends on Stage 0 + Stage 1)
Absorbs create-tasks into create-plan.

7. **Modify /pd:create-plan to invoke both skills** — Produce plan.md + tasks.md
   - **Why this item:** Design C3/I6 — merged create-plan is the core phase change
   - **Why this order:** After Stage 0 (constants updated) and Stage 1 (taskify validates the task-reviewer pattern)
   - **Deliverable:** Modified `commands/create-plan.md` that invokes planning skill then breaking-down-tasks skill, produces both plan.md and tasks.md, with combined review loop (plan-reviewer → task-reviewer → phase-reviewer, max 5 iterations)
   - **Complexity:** Complex (largest single change — merging two 400+ line commands into one coherent flow)
   - **Files:** `commands/create-plan.md`
   - **Verification:** Run `/pd:create-plan` on a feature with design.md, verify both plan.md and tasks.md produced with correct quality

8. **Create /pd:create-tasks deprecation stub** — Redirect to create-plan
   - **Why this item:** Design FR-12 — backward compatibility
   - **Why this order:** After item 7 (redirect target must exist)
   - **Deliverable:** Modified `commands/create-tasks.md` that outputs deprecation notice and redirects to `/pd:create-plan`
   - **Complexity:** Simple
   - **Files:** `commands/create-tasks.md`
   - **Verification:** Run `/pd:create-tasks`, verify deprecation message shown and `/pd:create-plan` invoked

### Stage 3: Backward Travel (depends on Stage 2)
Core novel work — forward re-run orchestration.

9. **Extend reviewer response schema** — Add backward_to and backward_context fields
   - **Why this item:** Design I1 — all reviewers must support backward travel fields
   - **Why this order:** Must precede orchestration logic (items 10-12)
   - **Deliverable:** Updated prompt templates for 6 existing reviewer agents (spec-reviewer, design-reviewer, plan-reviewer, task-reviewer, phase-reviewer, implementation-reviewer) to include optional backward_to/backward_context in their response schema. Note: relevance-verifier (item 15) will be created with backward_to support built-in.
   - **Complexity:** Simple (prompt template changes only — no code)
   - **Files:** All reviewer agent .md files in `agents/`
   - **Verification:** Dispatch a test reviewer with the updated prompt, verify response can include backward_to field

10. **Implement handleReviewerResponse()** — New shared procedure in workflow-transitions
   - **Why this item:** Design I2 — central orchestration for backward travel decisions
   - **Why this order:** After item 9 (needs reviewers that can produce backward_to)
   - **Deliverable:** New procedure in `skills/workflow-transitions/SKILL.md` that parses reviewer response for backward_to, stores backward_context/backward_return_target in entity metadata, logs to backward_history, calls transition_phase to upstream phase, invokes target phase command
   - **Complexity:** Complex (novel orchestration logic, metadata writes, audit trail)
   - **Files:** `skills/workflow-transitions/SKILL.md`
   - **Verification:** Test backward travel from create-plan to specify — verify context stored in entity metadata, upstream phase invoked, backward_history logged

11. **Extend _project_meta_json()** — Project backward fields to .meta.json
    - **Why this item:** validateAndSetup reads .meta.json — backward fields must be projected BEFORE any code tries to read them
    - **Why this order:** After item 10 (handleReviewerResponse stores the fields). MUST precede item 12 (validateAndSetup reads the projection).
    - **Deliverable:** Add backward_context and backward_return_target to _project_meta_json() projection. Exclude backward_history (audit-only, stays in DB).
    - **Complexity:** Simple (add 2 fields to existing projection function)
    - **Files:** `mcp/workflow_state_server.py`
    - **Verification:** After backward travel, verify .meta.json contains backward_context and backward_return_target fields

12. **Extend validateAndSetup() for backward context injection** — Read and inject context
    - **Why this item:** Design I3 — upstream phases must receive backward context
    - **Why this order:** After item 11 (_project_meta_json must project the fields before validateAndSetup can read them)
    - **Deliverable:** Extended Step 1b in `skills/workflow-transitions/SKILL.md` that reads backward_context from .meta.json, formats as markdown block, prepends to phase prompt context, clears after phase completes
    - **Complexity:** Medium (new step in existing procedure, formatting + lifecycle)
    - **Files:** `skills/workflow-transitions/SKILL.md`
    - **Verification:** After backward travel, verify upstream phase receives formatted backward context and addresses the cited issues

13. **Extend commitAndComplete() for forward re-run** — One-phase-at-a-time advancement
    - **Why this item:** Design I4 — after backward fix, workflow must advance forward through intermediate phases
    - **Why this order:** After items 10-12 (orchestration, projection, and context injection must work first)
    - **Deliverable:** Extended Step 3b in `skills/workflow-transitions/SKILL.md` that checks backward_return_target, advances to next phase via standard YOLO auto-chain, clears target when reached
    - **Complexity:** Medium (reuses existing auto-chain pattern, adds target tracking)
    - **Files:** `skills/workflow-transitions/SKILL.md`
    - **Verification:** Trigger backward travel from create-plan to specify, verify workflow advances: specify → design → create-plan (one at a time), then resumes normal flow

14. **Implement ping-pong detection** — Findings-count-decrease rule
    - **Why this item:** Design I9 — prevents infinite backward travel loops
    - **Why this order:** After item 10 (uses backward_history from handleReviewerResponse)
    - **Deliverable:** Logic in handleReviewerResponse that compares issue_count against most recent previous entry for same source→target pair; forces approve or escalation when no progress detected
    - **Complexity:** Simple (comparison logic on backward_history array)
    - **Files:** `skills/workflow-transitions/SKILL.md` (within handleReviewerResponse)
    - **Verification:** Simulate 3 backward travels with same issue count, verify ping-pong detection triggers

### Stage 4: Relevance Gate (depends on Stage 2 + Stage 3)
Pre-implementation coherence check.

15. **Create relevance-verifier agent** — New agent for artifact chain verification
    - **Why this item:** Design C2/I5 — the gate needs its agent
    - **Why this order:** Must precede gate dispatch (item 16)
    - **Deliverable:** New `agents/relevance-verifier.md` with model: opus, tools: [Read, Glob, Grep]. Checks coverage, completeness, testability, coherence across spec/design/plan/tasks. Returns structured JSON with per-check pass/fail and optional backward_to.
    - **Complexity:** Medium (new agent definition + prompt engineering)
    - **Files:** `agents/relevance-verifier.md`
    - **Verification:** Dispatch agent with test artifacts, verify structured response with per-check results

16. **Add relevance gate dispatch to create-plan completion** — Pre-implementation check
    - **Why this item:** Design I5 — gate runs after create-plan commits, before auto-chain to implement
    - **Why this order:** After items 7 (merged create-plan) and 15 (agent exists)
    - **Deliverable:** Modified create-plan.md completion section: after commitAndComplete, dispatch relevance-verifier. On pass → auto-chain to implement. On fail with backward_to → invoke handleReviewerResponse. On fail without backward_to → emit safety keyword "relevance verification failed" → halt YOLO.
    - **Complexity:** Medium (new dispatch point + safety keyword integration)
    - **Files:** `commands/create-plan.md`, `hooks/yolo-guard.sh` (add safety keyword)
    - **Verification:** Run create-plan on a feature with a spec gap, verify gate catches it and halts/backward-travels

### Stage 5: Post-Implementation 360 QA (depends on Stage 3 + item 15)
Restructured implementation review.

17. **Restructure implement.md review section** — 3-level sequential QA
    - **Why this item:** Design C5/I8 — layered task→spec→standards verification
    - **Why this order:** After Stage 3 (backward travel from QA needs handleReviewerResponse) AND item 15 (Level 2 dispatches relevance-verifier agent)
    - **Deliverable:** Modified review section: Level 1 (implementation-reviewer for task DoDs), Level 2 (relevance-verifier for spec ACs), Level 3 (code-quality + security reviewers). Sequential dispatch. 5 total iterations shared. Backward travel from Level 1/2 via handleReviewerResponse.
    - **Complexity:** Complex (restructuring existing 3-reviewer loop, adding backward travel integration)
    - **Files:** `commands/implement.md`
    - **Verification:** Run implementation with a task DoD gap, verify Level 1 catches it. Run with spec AC gap, verify Level 2 catches it.

### Stage 6: Documentation & Cleanup (depends on all prior stages)

18. **Update CLAUDE.md, READMEs, component docs** — Documentation sync
    - **Why this item:** CLAUDE.md doc sync rules require updates when components change
    - **Why this order:** After all code changes
    - **Deliverable:** Update phase sequence references, command tables, agent counts in README.md, README_FOR_DEV.md, plugins/pd/README.md. Update CLAUDE.md test commands if needed.
    - **Complexity:** Simple
    - **Files:** Documentation files
    - **Verification:** Run `./validate.sh` — no component count mismatches

19. **Regression test run** — Full pd test suite
    - **Why this item:** Zero regression verification
    - **Why this order:** After all changes
    - **Deliverable:** Clean test run across all suites
    - **Complexity:** Simple
    - **Files:** No files modified
    - **Verification:** All test suites pass (entity_registry, workflow_engine, memory_server, doctor, transition_gate, reconciliation, UI)

## Dependency Graph

```
Items 1,2,3 (parallel) ──→ Item 4 ──→ Item 5 (sweep) ──→ Item 7 (merged create-plan) ──→ Item 8
        │                                                           │
        │                                                 Item 9 (reviewer schema)
        │                                                           │
Item 6 (taskify,                                         Item 10 (handleReviewerResponse)
 independent)                                                       │
                                                         Item 11 (_project_meta_json)
                                                                    │
                                                         Item 12 (context inject)
                                                                    │
                                                     ┌──────────────┼──────────────┐
                                                     │              │              │
                                                  Item 13        Item 14
                                                  (forward       (ping-pong)
                                                   re-run)
                                                     │
                                                     └──────────────┤
                                                                    │
                                                     ┌──────────────┴──────────────┐
                                                     │                             │
                                                  Item 15 ──────────────────→ Item 17
                                                  (agent)                    (360 QA — needs agent)
                                                     │
                                                  Item 16
                                                  (gate dispatch)
                                                     │
                                              Items 18,19 (parallel)
```

## Risk Areas

- **Item 6 (merged create-plan):** Largest single change — merging two complex commands. Risk of breaking existing plan quality. Mitigation: Stage 1 taskify validates the pattern first.
- **Items 9-11 (backward travel orchestration):** Novel logic with no codebase precedent. Risk of edge cases in forward re-run. Mitigation: design recommends prototyping the orchestration loop first.
- **Item 3 (DB migration):** Schema changes are irreversible. Risk of breaking existing features with 'create-tasks' phase. Mitigation: migration updates existing rows to 'create-plan'.
- **Item 16 (360 QA restructure):** Changes the implementation review loop that's critical for code quality. Risk of weakening review. Mitigation: reuses existing reviewer agents, only changes orchestration order.

## Testing Strategy

- **Unit tests:** Items 1-4 (constants, frontmatter, migration, expected artifacts) — run existing test suites after changes
- **Integration tests:** Item 5 (standalone taskify on sample plan), Item 6 (merged create-plan on real feature)
- **E2E tests:** Items 9-12 (backward travel full cycle — backward travel from create-plan to specify, forward re-run through intermediate phases)
- **Regression tests:** Item 18 (full test suite across all modules)

## Definition of Done

- [ ] PHASE_SEQUENCE has 6 phases (create-tasks removed)
- [ ] ARTIFACT_PHASE_MAP is dict[str, list[str]] with create-plan → ["plan.md", "tasks.md"]
- [ ] DB migration removes create-tasks from CHECK constraint
- [ ] `/pd:taskify` works standalone on any plan file with built-in reviewer cycle
- [ ] `/pd:create-plan` produces both plan.md and tasks.md
- [ ] `/pd:create-tasks` shows deprecation notice and redirects
- [ ] All 7 reviewer agents support backward_to in response schema
- [ ] handleReviewerResponse() orchestrates backward travel with context storage
- [ ] validateAndSetup() injects backward context from .meta.json
- [ ] commitAndComplete() handles forward re-run via backward_return_target
- [ ] Ping-pong detection prevents infinite backward loops
- [ ] _project_meta_json() projects backward_context and backward_return_target
- [ ] relevance-verifier agent checks artifact chain coherence
- [ ] Relevance gate runs after create-plan, halts YOLO on failure
- [ ] 360 QA runs task→spec→standards verification after implementation
- [ ] All existing pd tests pass (zero regression)
- [ ] Documentation updated (README, CLAUDE.md, component tables)
