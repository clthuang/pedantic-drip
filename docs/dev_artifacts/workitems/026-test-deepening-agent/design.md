# Design: Test Deepening Agent

> **Spec deviation note:** This design intentionally deviates from spec FR-4 and AC-5 on re-run scope — re-runs use Phase B only (not Phase A + B) since Phase A inputs are unchanged after implementation fixes. See TD-5 for rationale.

## Prior Art Research

### Codebase Patterns

- **Agent file pattern:** frontmatter (5 fields: name, description, model, tools, color) + examples + structured sections + output format + MUST NOT constraints. Reference: `plugins/iflow-dev/agents/code-simplifier.md`
- **Dispatch template pattern:** Step 5 in `implement.md` shows the canonical Task tool dispatch — description, subagent_type, prompt with injected context sections. New Step 6 follows this pattern.
- **No `references/` directory for agents:** Only skills use `references/`. If the agent exceeds 500 lines (AC-9), this would be the first agent to use a references file.
- **Secretary fast-path format:** `| Pattern (case-insensitive) | Agent | Confidence |` at 95% confidence level. Reference: `plugins/iflow-dev/agents/secretary.md`
- **Current counts:** 28 agents total, 5 Workers. test-deepener becomes agent #29, Worker #6.

### External Research

1. **Persona labels don't reliably improve LLM performance.** A 162-persona study found simple persona assignments have no consistent effect on output quality. *However*, structured adversarial reasoning protocols (Devil's Advocate three-stage introspection: anticipate failures, align post-action, review) reduce plan revisions by 45%. **Design implication:** Replace simple "You are a skeptical QA engineer" persona label with a structured adversarial reasoning protocol — concrete steps the agent must follow, not a role it must inhabit.

2. **SymPrompt structured checklist prompting achieves 2-5x coverage improvement** over free-form generation. Each dimension checklist with concrete items (BVA canonical set, adversarial heuristics table, mutation operators) is more effective than open-ended "think about edge cases." **Design implication:** Keep the six dimension checklists as structured, concrete artifacts. Don't summarize them into prose.

3. **Chain-of-Agents pattern validates two-phase restricted context.** Workers receiving constrained context chunks produce higher-quality output than workers with full context. This validates the Phase A (spec-only) / Phase B (full context) architecture. **Design implication:** The two-phase dispatch is well-supported. Phase A's context restriction is the primary quality mechanism.

4. **General best practice: just-in-time context loading** for long prompts. Loading full dimension checklists into the system prompt when only some are applicable adds noise. **Design implication:** If agent file exceeds 500 lines, extract dimension checklists to a references file. The agent reads it at the start of each phase. This adds a Read call but reduces prompt noise.

5. **Separate agents for skeptical roles** perform better than one agent switching between constructive and critical modes. **Design implication:** The test-deepener is already a separate agent from the implementer, which is the correct architecture.

## Architecture Overview

### System Context

```
implement.md (orchestrator)
  │
  ├── Step 4: Implementation Phase ──→ implementer agent (per-task)
  ├── Step 5: Simplification Phase ──→ code-simplifier agent
  ├── Step 6: Test Deepening Phase ──→ test-deepener agent (NEW)
  │     ├── Phase A dispatch (spec-only context)
  │     ├── Phase B dispatch (full context + Phase A outlines)
  │     └── Divergence control flow
  ├── Step 7: Review Phase ──→ 3 reviewer agents (was Step 6)
  ├── Step 8: Update State (was Step 7)
  └── Step 9: Completion Message (was Step 8)
```

### Two-Phase Dispatch Architecture

The agent is dispatched twice per feature, with different context windows:

```
Phase A (spec-only)                    Phase B (full context)
┌─────────────────────┐               ┌─────────────────────────┐
│ Inputs:             │               │ Inputs:                 │
│ - spec.md           │               │ - Phase A outlines JSON │
│ - design.md         │               │ - files-changed list    │
│ - tasks.md          │     ──→       │                         │
│ - PRD goals         │               │ Agent behavior:         │
│                     │               │ - Read existing tests   │
│ Prohibited:         │               │ - Skip duplicates       │
│ - No file paths     │               │ - Write executable code │
│ - No Glob/Grep      │               │ - Run test suite        │
│                     │               │ - Report divergences    │
│ Output:             │               │ Output:                 │
│ - Test outlines JSON│               │ - Test report JSON      │
└─────────────────────┘               └─────────────────────────┘
```

**Why two dispatches instead of one:** Research shows LLM-generated tests suffer 9-percentage-point accuracy collapse on buggy code because they mirror implementation behavior. Phase A physically cannot mirror implementation — it has no access. Phase B receives outlines that were already derived from spec, anchoring its test writing to spec-derived expectations.

### Files-Changed Union Assembly

Phase B receives the union of files from two sources:

1. **Implementation files** — the orchestrator holds these in memory from Step 4's aggregate summary (`files_changed` list). As a fallback, parse `implementation-log.md` task entries for lines matching `- path/to/file.ext` under "Files changed" headings.
2. **Simplification files** — the orchestrator holds these from Step 5's code-simplifier JSON output. Extract file paths from each `simplifications[].location` field (strip the `:line` suffix).

The implement.md orchestrator builds this union before dispatching Phase B.

**Concrete assembly in implement.md Step 6:**
```
# files from Step 4 (already in orchestrator context)
implementation_files = step_4_aggregate.files_changed

# files from Step 5 (already in orchestrator context)
simplification_files = [s.location.split(":")[0] for s in step_5_output.simplifications]

# union and deduplicate
files_changed = sorted(set(implementation_files + simplification_files))
```

**Fallback if context was compacted:** If the orchestrator no longer holds Step 4/5 data in context (due to conversation compaction), parse `implementation-log.md` directly. Each task section contains a "Files changed" or "files_changed" field with file paths. This is unstructured markdown, so match lines that look like file paths (contain `/` and end with a file extension). This fallback covers Step 4 files only. Step 5 (simplification) file paths are not persisted to disk, but this is acceptable because the code-simplifier only modifies files that were already changed in Step 4 — Step 5 paths are always a subset of Step 4 paths, so no coverage gap exists.

## Components

### C1: Agent File (`plugins/iflow-dev/agents/test-deepener.md`)

**Structure** (following established pattern):

```
---
frontmatter (5 fields)
---

<example> blocks (2-3 triggering examples)

# Test Deepener

## Structured Adversarial Protocol
  (replaces simple persona label — evidence-based)
  Three concrete steps: anticipate, challenge, verify

## Spec-Is-Oracle Directive
  Core behavioral rule

## Testing Dimensions
  Six dimension sections, each with:
  - Applicability guard
  - Structured checklist / table
  - Example (first dimension only — BDD Given/When/Then)

## Test Writing Rules
  - Descriptive naming requirement
  - Given/When/Then structural comments
  - Soft budget (15-30 tests per feature)
  - derived_from requirement

## Phase A: Outline Generation
  - What you receive (spec, design, tasks, PRD goals)
  - What you MUST NOT do (read implementation, use Glob/Grep)
  - Output JSON schema

## Phase B: Executable Test Writing
  - What you receive (outlines + files-changed)
  - Step-by-step process (read tests → skip duplicates → write → run → report)
  - Error handling (3 compile attempts, assertion failures = divergences)
  - Output JSON schema

## What You MUST NOT Do
  - Rewrite tests to match implementation when assertions fail
  - Read implementation files during Phase A
  - Generate tests without derived_from traceability
  - Exceed 40 tests without re-prioritizing
```

**Line budget breakdown:**

| Section | Estimated Lines |
|---------|----------------|
| Frontmatter | ~10 |
| Examples (2-3 blocks) | ~15 |
| Structured Adversarial Protocol | ~20 |
| Spec-Is-Oracle Directive | ~10 |
| Six Dimension Checklists (~25 each) | ~150 |
| Mutation Operators Table | ~15 |
| Test Writing Rules | ~25 |
| Phase A Instructions + Schema | ~40 |
| Phase B Instructions + Schema | ~45 |
| MUST NOT constraints | ~15 |
| **Total** | **~345** |

Under the 500-line AC-9 threshold, so no references file extraction needed. The dimension checklists are the largest section — if any dimension needs expansion, this is where the 500-line threshold would be tested.

**Model:** `opus` (v1 quality baseline). The agent performs multi-dimensional adversarial reasoning across six dimensions, writes correct test code in arbitrary frameworks, and must resist implementation mirroring. This is harder than what the implementer does. Downgrade to sonnet after 2-3 features confirm quality.

### C2: Implement Command Update (`plugins/iflow-dev/commands/implement.md`)

**Changes:**

1. **Insert Step 6** (Test Deepening Phase) between current Step 5 and current Step 6
2. **Renumber** current Steps 6-8 to Steps 7-9
3. **Update all cross-references:**
   - See I8 cross-reference table for the authoritative text-based mapping of all references. Use Grep to locate each reference by content pattern rather than line numbers (line numbers shift after Step 6 insertion).

4. **New Step 6 content:**
   - Phase A dispatch template
   - Phase B dispatch template
   - Files-changed union assembly logic
   - Divergence control flow with AskUserQuestion
   - YOLO mode handling

### C3: Documentation Updates

- `README.md` — increment agent count (28 → 29)
- `README_FOR_DEV.md` — add test-deepener to Workers category in agent table (Workers: 5 → 6, Total: 28 → 29). Entry: `test-deepener — Systematically deepens test coverage after TDD scaffolding with spec-driven adversarial testing`
- `plugins/iflow-dev/README.md` — increment agent count in component table (28 → 29), add test-deepener to agent table

### C4: Secretary Fast-Path Entry (`plugins/iflow-dev/agents/secretary.md`)

Add row to Specialist Fast-Path table:
```
| "deepen tests" / "add edge case tests" / "test deepening" | iflow-dev:test-deepener | 95% |
```

## Technical Decisions

### TD-1: Structured Adversarial Protocol over Simple Persona

**Decision:** Replace `"You are a skeptical QA engineer"` persona label with a structured three-step adversarial reasoning protocol.

**Rationale:** Research shows persona labels have no reliable effect (162-persona study). Structured adversarial reasoning (Devil's Advocate protocol) reduces plan revisions by 45%. The structured protocol gives the agent concrete steps:

1. **Anticipate:** Before writing each test, state what could go wrong with the implementation for this scenario
2. **Challenge:** Ask "If the implementation has a bug here, would this test catch it?"
3. **Verify:** After writing, apply the mutation mindset operators — would swapping `>` to `>=` make this test pass when it shouldn't?

**Note:** The spec (FR-1) mentions "adversarial persona framing" and AC-4 checks for it. The structured protocol satisfies this requirement — it's an adversarial reasoning structure, not just a label. The spec's example phrases ("skeptical QA engineer", "try to break it") can appear as context framing within the structured protocol.

### TD-2: Dimension Checklists Inline (No References File)

**Decision:** Keep all six dimension checklists in the agent file rather than extracting to a references file.

**Rationale:** Estimated line count is ~350-400, under the 500-line threshold (AC-9). Inlining avoids an extra Read call per phase and keeps the agent self-contained. If future dimensions push past 500 lines, extract per the spec's escape hatch.

### TD-3: Phase A Prohibition Enforcement

**Decision:** Phase A prohibition on implementation access is enforced at two levels:
1. **Architectural:** The dispatch template provides no file paths. The agent has no `files-changed` list.
2. **Prompt-level:** Explicit instruction "Do NOT read implementation files. Do NOT use Glob/Grep to find source code."

**Rationale:** Level 1 is the real enforcement — the agent can't read files it doesn't know about. Level 2 is defense-in-depth for the case where the agent might try to Glob for test files or source files by guessing paths. Both levels together satisfy AC-2.

**Known limitation:** The agent has Glob and Grep tools (needed for Phase B) and could theoretically discover implementation files during Phase A by guessing patterns like `*.py` or `src/**/*.ts`. The prompt-level prohibition is the only control here — there is no way to restrict tool access per-phase in a single agent dispatch. This is an acceptable risk for v1 because: (1) the agent receives separate dispatch calls for each phase, so the Phase A dispatch prompt strongly frames the restricted context, and (2) if the agent does read implementation files in Phase A, the outlines would still be structured by the dimension checklists, limiting the damage. A future hardening option would be to use a separate agent definition with restricted tools for Phase A.

### TD-4: Test Runner Scoping Strategy

**Decision:** Use file-level targeting first, fall back to containing directory.

**Rationale:** File-level targeting (e.g., `pytest path/to/test_file.py`) avoids running the entire suite. If it fails due to missing fixtures or conftest context, fall back to the containing test directory. Log the fallback reason in the summary field per FR-3.

### TD-5: Divergence Re-Run Cycle

**Decision:** "Fix implementation" dispatches the implementer agent to fix code, then re-runs Phase B only (not Phase A + B).

**Rationale:** Phase A receives only spec, design, tasks, and PRD goals — none of which change when the implementer fixes code. Re-running Phase A on identical inputs produces identical outlines, wasting an opus dispatch. Phase B re-run is sufficient: the outlines are the same, but the implementation has changed, so the test results will differ. Max 2 re-runs before escalating (spec FR-4).

**Cost implication:** Each re-run cycle = 1 implementer dispatch + 1 Phase B dispatch = 2 opus dispatches. Worst case (initial Phase A + Phase B + 2 re-run cycles) = 2 + 2 + 2 = 6 opus dispatches total. The user is informed of divergences via AskUserQuestion before each re-run, so they can choose "Accept implementation" or "Review manually" to avoid further cost. In YOLO mode, the first re-run is auto-selected but the circuit breaker stops after 2 re-runs.

**Note:** The spec (FR-4) says "re-runs full Phase A + Phase B cycle." This design deviates: we re-run Phase B only because Phase A inputs are unchanged. This is a safe optimization — if a future scenario requires Phase A re-run (e.g., spec.md is modified during the fix), it can be added. For v1, the optimization halves the re-run cost.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Agent file exceeds 500 lines | Low | Low | Line estimate is ~350-400. If exceeded, extract per AC-9 escape hatch |
| Step renumbering breaks cross-references | Medium | High | Enumerate ALL cross-references before editing. Use Grep to find every "step 6", "step 7", "step 8", "6a", "6b", etc. |
| Phase A generates low-quality outlines | Low-Med | Medium | Structured dimension checklists (SymPrompt pattern) provide concrete generation framework. Soft budget prevents unfocused generation |
| Divergence cycle loops unnecessarily | Low | Medium | Circuit breaker at 2 re-runs. YOLO mode stops after max re-runs rather than auto-accepting |
| Existing TDD tests use inconsistent patterns | Medium | Low | Phase B reads existing test files to identify framework and patterns. Falls back to error message if no TDD tests exist (unreachable per spec) |

## Interfaces

### I1: Phase A Input Contract

The implement.md orchestrator provides these context sections to Phase A:

```
PHASE A: Generate test outlines from specifications only.
Do NOT read implementation files. Do NOT use Glob/Grep to find source code.
You will receive implementation access in Phase B.

Feature: {feature name from .meta.json slug}

## Spec (acceptance criteria — your primary test oracle)
{full content of spec.md}

## Design (error handling contracts, performance constraints)
{full content of design.md}

## Tasks (what was supposed to be built)
{full content of tasks.md}

## PRD Goals
{Problem Statement + Goals sections from prd.md}
```

### I2: Phase A Output Contract

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

**Validation rules:**
- `outlines` must be non-empty (at least BDD scenarios are always applicable)
- Each outline must have a non-empty `derived_from` field
- `dimensions_assessed` must contain all six dimension keys
- N/A dimensions must include a reason after the dash

### I3: Phase B Input Contract

The implement.md orchestrator provides these context sections to Phase B:

```
PHASE B: Write executable test code from these outlines.

Feature: {feature name}

## Test Outlines (from Phase A)
{Phase A JSON output — the full outlines array}

## Files Changed (implementation + simplification)
{deduplicated file list: implementation-log.md files UNION Step 5 modified files}

Step 1: Read existing test files for changed code to identify the test
framework, assertion patterns, and file organization conventions. Match
these exactly when writing new tests.

Step 2: Skip scenarios already covered by existing TDD tests.

Step 3: Write executable tests, run the suite, and report.
```

### I4: Phase B Output Contract

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

**Validation rules:**
- `tests_added` entries must have non-empty `derived_from`
- `dimensions_covered` must contain all six dimension keys
- `existing_tests_reviewed` must be >= 0
- `all_tests_pass` is `true` only when `spec_divergences` is empty AND all tests compile and pass
- `spec_divergences` entries (if any) must contain: `spec_criterion`, `expected`, `actual`, `failing_test`

### I5: Spec Divergence Entry Schema

```json
{
  "spec_criterion": "AC-7",
  "expected": "timeout should be 30s per spec",
  "actual": "implementation uses 60s timeout",
  "failing_test": "tests/test_timeout.py::test_default_timeout_matches_spec"
}
```

### I6: Divergence Control Flow Interface

The implement.md orchestrator handles divergences with this decision tree:

```
Phase B output received
  │
  ├── spec_divergences is empty
  │     └── Proceed to Step 7 (Review Phase)
  │
  └── spec_divergences is non-empty
        │
        ├── YOLO mode OFF:
        │     └── AskUserQuestion with 3 options:
        │           │
        │           ├── "Fix implementation":
        │           │     1. Dispatch implementer agent with spec_divergences
        │           │        as issues to fix (Step 7d dispatch pattern).
        │           │        Prompt includes: spec.md, design.md, implementation
        │           │        files, and spec_divergences formatted as issues
        │           │        (spec_criterion→requirement, expected→target,
        │           │        actual→bug, failing_test→evidence)
        │           │     2. Re-run Phase B only (Phase A outlines unchanged —
        │           │        spec inputs don't change when implementation is fixed)
        │           │     3. Max 2 re-runs; if divergences persist, escalate
        │           │        with only "Accept implementation" and "Review manually"
        │           │
        │           ├── "Accept implementation":
        │           │     1. For each divergence in spec_divergences, delete the
        │           │        test function identified by failing_test from the file
        │           │     2. After ALL deletions, re-run test suite once to verify
        │           │        remaining tests pass
        │           │     3. Proceed to Step 7
        │           │
        │           └── "Review manually" → stop execution
        │
        └── YOLO mode ON:
              ├── re-run count < 2:
              │     └── Auto-select "Fix implementation" (steps 1-2 above)
              └── re-run count >= 2:
                    └── STOP execution, surface to user
```

### I7: Files-Changed Union Assembly

See Architecture Overview > Files-Changed Union Assembly for the full mechanism including concrete assembly code and compaction fallback. The orchestrator builds the union from Step 4 and Step 5 data already in context, with a markdown-parsing fallback for compacted sessions.

### I8: Step Renumbering Map

| Original | New | Content |
|----------|-----|---------|
| Step 6 | Step 7 | Review Phase (sub-steps 7a-7e) |
| Step 6a | Step 7a | Implementation Review |
| Step 6b | Step 7b | Code Quality Review |
| Step 6c | Step 7c | Security Review |
| Step 6d | Step 7d | Automated Iteration Logic |
| Step 6e | Step 7e | Capture Review Learnings |
| Step 7 | Step 8 | Update State |
| Step 8 | Step 9 | Completion Message |
| (new) Step 6 | Step 6 | Test Deepening Phase |

**Cross-references to update in implement.md:**

| Location | Current text | New text | Reason |
|----------|-------------|----------|--------|
| Step 6 heading | "### 6. Review Phase" | "### 7. Review Phase" | Renumbered |
| Step 6a heading (line ~99) | "**6a. Implementation Review**" | "**7a. Implementation Review**" | Sub-step renumbered |
| Step 6b heading (line ~134) | "**6b. Code Quality Review**" | "**7b. Code Quality Review**" | Sub-step renumbered |
| Step 6c heading (line ~170) | "**6c. Security Review**" | "**7c. Security Review**" | Sub-step renumbered |
| Step 6d heading | "**6d. Automated Iteration Logic**" | "**7d. Automated Iteration Logic**" | Sub-step renumbered |
| Step 6d (IF all PASS) | "Proceed to step 7" | "Proceed to step 8" | Step 7 (Update State) is now Step 8 |
| Step 6d (Force approve) | "proceed to step 7" | "proceed to step 8" | Same reason |
| Step 6d (Else) | "Loop back to step 6a" | "Loop back to step 7a" | Step 6a is now 7a |
| Step 6e heading | "### 6e. Capture Review Learnings" | "### 7e. Capture Review Learnings" | Sub-step renumbered |
| Step 7 heading | "### 7. Update State" | "### 8. Update State" | Renumbered |
| Step 8 heading | "### 8. Completion Message" | "### 9. Completion Message" | Renumbered |
| Step 8 (Fix and rerun) | "return to Step 6" | "return to Step 7" | Review Phase is now Step 7 |

## Error Contracts

### Agent Compilation Error Handling

The test-deepener agent handles compilation errors internally:
1. Run tests
2. If compilation/syntax error: fix and re-run (max 3 attempts)
3. If still failing after 3 attempts: include in output as a note, do not report as spec divergence
4. If tests run but assertions fail: report as spec divergences

### Implement.md Error Handling

The orchestrator handles these error conditions:
- **Phase A returns empty outlines:** Log warning ("Test deepening Phase A returned no outlines — skipping test deepening"), then proceed to Step 7. This shouldn't happen since BDD is always applicable, but the warning ensures silent failures are visible
- **Phase B reports "No TDD tests found":** This is unreachable since Step 4 enforces TDD, but the agent should handle it gracefully. Phase B should: (1) check project config files (package.json, pyproject.toml, Cargo.toml) for test framework dependencies, (2) check design.md for test framework decisions. If framework is identified, proceed with test writing. If not, report error "Cannot determine test framework — no TDD tests found and no framework in project config" and proceed to Step 7
- **Phase A or B agent dispatch fails:** Log error, proceed to Step 7 — test deepening is additive, failure should not block the review phase
