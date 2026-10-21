# Spec: Test Deepening Agent

## Overview

Add a `test-deepener` agent to the iflow-dev plugin that systematically deepens test coverage after TDD scaffolding completes. The agent operates in two phases (spec-first outlines, then implementation-aware test writing) across six testing dimensions, and integrates as a new step in the implement command.

## Scope

### In Scope

1. **New agent file:** `plugins/iflow-dev/agents/test-deepener.md` with two-phase system prompt
2. **Implement command modification:** Insert Step 6 (Test Deepening) in `plugins/iflow-dev/commands/implement.md` between Code Simplification (Step 5) and Review Phase (renumbered to Step 7)
3. **Six testing dimensions** embedded in agent system prompt: BDD scenarios, boundary values, adversarial testing, error propagation, mutation mindset, performance contracts
4. **Failure mode control flow:** Spec divergence handling with user decision point

### Out of Scope

- Changes to the implementer agent or TDD skill
- Gherkin `.feature` file generation
- Mutation testing framework integration
- Load testing / infrastructure performance testing
- Pre-existing code test audit
- Reviewer loop for the test-deepener (v1 is single-pass)
- Per-feature dimension configuration

## Deliverables

| # | Deliverable | File(s) |
|---|-------------|---------|
| D1 | Test-deepener agent definition | `plugins/iflow-dev/agents/test-deepener.md` |
| D2 | Implement command update | `plugins/iflow-dev/commands/implement.md` |
| D3 | Documentation updates | `README.md`, `README_FOR_DEV.md`, `plugins/iflow-dev/README.md` |
| D4 | Secretary fast-path entry | `plugins/iflow-dev/agents/secretary.md` |

## Functional Requirements

### FR-1: Agent Definition

The agent file `plugins/iflow-dev/agents/test-deepener.md` must contain:

**Frontmatter:**
- `name: test-deepener`
- `description:` with trigger phrases: "deepen tests", "add edge case tests", "test deepening phase"
- `model: opus` (v1 quality baseline; downgrade to sonnet after 2-3 features confirm quality — see PRD open question 3)
- `tools: [Read, Write, Edit, Bash, Glob, Grep]`
- `color: green`

**System prompt must include:**
- Two-phase operation instructions (Phase A: outlines only, Phase B: executable tests)
- Adversarial persona framing ("skeptical QA engineer", "try to break it")
- All six testing dimension checklists with applicability guards
- Five mutation operators table
- Spec-is-oracle directive ("If implementation and spec disagree, spec is correct")
- Descriptive test naming requirement
- Soft budget guidance (15-30 tests per feature, re-prioritize above 40)
- Given/When/Then structural comment format
- Output JSON schema for both Phase A and Phase B

### FR-2: Phase A — Spec-Only Test Outline Generation

Phase A prompt context must include ONLY:
- Spec content (acceptance criteria)
- Design content (error contracts, performance constraints)
- Tasks content (what was built)
- PRD goals (problem statement + goals)

Phase A prompt must explicitly:
- Instruct "Do NOT read implementation files. Do NOT use Glob/Grep to find source code."
- State "You will receive implementation access in Phase B."

Phase A output schema:
```json
{
  "outlines": [
    {
      "dimension": "bdd_scenarios | boundary_values | adversarial | error_propagation | mutation_mindset | performance_contracts",
      "scenario_name": "test_rejects_negative_quantities",
      "given": "A product with quantity field accepting integers 1-999",
      "when": "User submits quantity of -1",
      "then": "System rejects with validation error",
      "derived_from": "spec:AC-3 (input validation)"
    }
  ],
  "dimensions_assessed": {
    "bdd_scenarios": "applicable",
    "boundary_values": "applicable",
    "adversarial": "N/A — no public API surface",
    "error_propagation": "applicable",
    "mutation_mindset": "applicable",
    "performance_contracts": "N/A — no SLAs in spec"
  }
}
```

### FR-3: Phase B — Executable Test Writing

Phase B prompt context must include:
- Phase A outlines (JSON output)
- Files-changed list (union of implementation + simplification files)

Phase B agent behavior:
1. Read existing test files for changed code to identify TDD coverage
2. Skip outlines already covered by existing TDD tests
3. Write test code using project's native test framework (identified from existing TDD test files — if no TDD tests exist, report error: "No TDD tests found — cannot determine test framework." This is unreachable since Step 4 enforces TDD.)
4. Use Given/When/Then as structural comments within tests
5. Use descriptive test names (behavior in plain English)
6. Run tests scoped to the newly created/modified test files. Use file-level targeting if the runner supports it (e.g., `pytest path/to/file.py`). If file-level targeting fails due to runner setup requirements (e.g., missing conftest.py context), fall back to the containing test directory or suite root, and log the fallback reason in the summary field.
7. Fix compilation/syntax errors internally (max 3 attempts)
8. Report assertion failures as spec divergences (do NOT rewrite to match implementation)

Phase B output schema:
```json
{
  "tests_added": [
    {
      "file": "path/to/test_file.py",
      "dimension": "adversarial",
      "tests": ["test_rejects_empty_password", "test_rejects_sql_injection_in_email"],
      "derived_from": "spec:AC-3 (input validation)"
    }
  ],
  "dimensions_covered": {
    "bdd_scenarios": {"count": 5, "applicability": "applicable"},
    "boundary_values": {"count": 8, "applicability": "applicable"},
    "adversarial": {"count": 6, "applicability": "applicable"},
    "error_propagation": {"count": 4, "applicability": "applicable"},
    "mutation_mindset": {"count": 2, "applicability": "applicable"},
    "performance_contracts": {"count": 0, "applicability": "N/A — no performance SLAs in spec"}
  },
  "existing_tests_reviewed": 12,
  "duplicates_skipped": 3,
  "spec_divergences": [],
  "all_tests_pass": true,
  "summary": "Added 25 tests across 3 files."
}
```

### FR-4: Implement Command Integration

Modify `plugins/iflow-dev/commands/implement.md` to add Step 6 (Test Deepening Phase):

**Step renumbering:**
- Current Step 6 (Review Phase) becomes Step 7 (sub-steps 7a-7e)
- Current Step 7 (Update State) becomes Step 8
- Current Step 8 (Completion Message) becomes Step 9
- All internal references to step numbers must be updated (e.g., "proceed to step 7" in the review loop)

**New Step 6 must contain:**
1. Phase A dispatch template (spec-only context)
2. Phase B dispatch template (full context with files-changed union)
3. Files-changed union assembly: implementation-log.md files + Step 5 modified files
4. Spec divergence control flow:
   - Empty divergences: proceed to Step 7
   - Non-empty: AskUserQuestion with three options (Fix implementation, Accept implementation, Review manually)
   - "Fix implementation" re-runs Phase B only (Phase A outlines are reused since spec/design/tasks inputs are unchanged; max 2 re-runs; if divergences remain after 2 fix cycles, escalate to user with only "Accept implementation" and "Review manually" options)
   - "Accept implementation" removes divergent tests, proceeds to Step 7. The agent does not modify spec.md — the user is responsible for updating it if needed.
   - Under YOLO mode: default to "Fix implementation" for the first divergence cycle; if divergences persist after max re-runs, stop execution and surface to user (consistent with YOLO circuit breaker pattern).
   - "Review manually" stops execution

### FR-5: Documentation Updates

Update component counts and tables in:
- `README.md` — agent count
- `README_FOR_DEV.md` — agent table
- `plugins/iflow-dev/README.md` — component counts table and agent table
- `plugins/iflow-dev/agents/secretary.md` — add fast-path entry: "deepen tests" / "add edge case tests" -> iflow-dev:test-deepener at 95% confidence. Match the format of existing fast-path entries.

Note: `plugins/iflow-dev/skills/workflow-state/SKILL.md` Workflow Map shows phases (brainstorm, specify, design, etc.), not sub-steps within the implement phase. The test-deepening step is internal to the implement phase — no Workflow Map update needed.

## Acceptance Criteria

### AC-1: Agent File Valid
- [ ] File exists at `plugins/iflow-dev/agents/test-deepener.md`
- [ ] Frontmatter has all 5 required fields (name, description, model, tools, color)
- [ ] `./validate.sh` passes with no errors for the agent

### AC-2: Two-Phase Dispatch Works
- [ ] Phase A dispatch template in implement.md includes spec, design, tasks, PRD goals — but NOT files-changed list
- [ ] Phase A dispatch includes explicit prohibition on reading implementation files
- [ ] Phase B dispatch template includes Phase A outlines AND files-changed list
- [ ] Files-changed list is assembled as union of implementation + simplification outputs

### AC-3: Six Dimensions Complete
- [ ] Agent system prompt contains all six dimension sections with checklists
- [ ] Each dimension has an applicability guard
- [ ] Dimension 1 (BDD): Given/When/Then format with structural comment example
- [ ] Dimension 2 (BVA): Canonical set `{min-1, min, min+1, typical, max-1, max, max+1}` documented
- [ ] Dimension 3 (Adversarial): Eight heuristics table present
- [ ] Dimension 4 (Error Propagation): Three-item checklist present
- [ ] Dimension 5 (Mutation): Five operators table present
- [ ] Dimension 6 (Performance): Percentile-based SLA pattern documented, N/A guard present

### AC-4: Anti-Blind-Spot Safeguards
- [ ] Adversarial persona framing in system prompt
- [ ] Spec-is-oracle directive in system prompt
- [ ] Descriptive test naming requirement in system prompt
- [ ] Soft budget guidance (15-30 per feature) in system prompt
- [ ] Limitation acknowledgment: prompt-level safeguards are heuristics, two-phase dispatch is the architectural guarantee

### AC-5: Failure Mode Control Flow
- [ ] Implement.md distinguishes test compilation errors (agent self-fixes) from assertion failures (spec divergences)
- [ ] Spec divergence AskUserQuestion has three options: Fix implementation, Accept implementation, Review manually
- [ ] "Fix implementation" re-runs Phase B only (Phase A outlines reused since inputs unchanged) with max 2 re-runs circuit breaker
- [ ] "Accept implementation" removes divergent tests and proceeds to review (does not modify spec.md)
- [ ] YOLO mode defaults to "Fix implementation" on first divergence, stops on max re-runs

### AC-6: Step Renumbering Correct
- [ ] Current Step 6 (Review Phase) renumbered to Step 7 with sub-steps 7a-7e
- [ ] Current Step 7 (Update State) renumbered to Step 8
- [ ] Current Step 8 (Completion Message) renumbered to Step 9
- [ ] All internal cross-references updated (e.g., "proceed to step 7" in review loop, "return to step 7a" in iteration logic)
- [ ] Step 6e (Capture Review Learnings) renumbered to 7e
- [ ] Completion Message (Step 9) "Fix and rerun reviews" option references Step 7 (not Step 6)
- [ ] Review loop "proceed to step 7" references are correct throughout

### AC-7: Output Schemas Valid
- [ ] Phase A output schema includes: outlines array, dimensions_assessed object
- [ ] Phase B output schema includes: tests_added, dimensions_covered, existing_tests_reviewed, duplicates_skipped, spec_divergences, all_tests_pass, summary
- [ ] Every test in tests_added has non-empty derived_from field

### AC-8: Documentation Synced
- [ ] Agent count incremented in README.md, README_FOR_DEV.md, plugins/iflow-dev/README.md
- [ ] test-deepener listed in agent tables with description
- [ ] Secretary.md fast-path entry added for "deepen tests" / "add edge case tests" patterns

### AC-9: Agent File Size Manageable
- [ ] Agent system prompt is under 500 lines. If exceeding, extract dimension checklists to `plugins/iflow-dev/agents/references/test-deepener-dimensions.md` and add a Read instruction at the start of each phase in the agent prompt.

## Constraints

- Agent file must follow existing agent pattern (frontmatter + examples + sections)
- No changes to implementer agent, TDD skill, or existing reviewer agents
- Step renumbering must not break any existing implement.md behavior
- Agent is auto-discovered from agents/ directory — no plugin.json changes needed

## Dependencies

- None — all changes are additive to existing files
