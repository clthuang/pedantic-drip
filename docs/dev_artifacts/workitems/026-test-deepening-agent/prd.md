# PRD: Test Deepening Agent

## Problem Statement

The current workflow enforces TDD during implementation — every task goes through RED-GREEN-REFACTOR via the implementer agent. This establishes interfaces, scaffolds, and basic happy-path coverage. However, the TDD phase is interface-leading: it proves the code works for the cases the developer thought of, not that it works for the cases that would break it.

There is no dedicated phase for systematically deepening test coverage after scaffolding is complete. The code-quality-reviewer checks "test coverage adequate" as one bullet among many, but doesn't generate tests or analyze gaps. Edge cases, boundary conditions, error propagation, state transitions, and performance contracts are left to the implementer's judgment — which is implementation-biased by design.

**The core risk:** An AI agent that wrote the code will write tests that confirm its own assumptions. Research shows LLM-generated test oracles suffer a 9-percentage-point accuracy collapse on buggy code because they mirror implementation behavior rather than specified behavior. — Evidence: [Do LLMs Generate Test Oracles That Capture Actual or Expected Behavior? (2024)](https://arxiv.org/html/2410.21136v1)

## Goals

1. **Deepen correctness** — Systematically identify and test edge cases, boundary values, and error paths that TDD's happy-path focus misses
2. **Enforce behavioral framing** — Express tests as Given/When/Then BDD scenarios derived from the spec, not from reading implementation code
3. **Break implementation bias** — Use two-phase dispatch and adversarial framing to prevent self-confirming tests
4. **Validate performance contracts** — Where the spec defines performance requirements, assert them as testable SLAs
5. **Integrate seamlessly** — Slot into the existing implement command between simplification and review with zero workflow disruption

## Non-Goals

- Replacing the TDD phase — the implementer agent continues to own RED-GREEN-REFACTOR for scaffolding
- Running actual mutation testing frameworks — the agent applies mutation *mindset* heuristically
- Load testing or infrastructure-level performance testing — only code-level micro-benchmarks and SLA assertions
- Generating Gherkin `.feature` files for a BDD framework — the agent writes tests in the project's native test framework using Given/When/Then as *structural comments*
- Full test suite audit of pre-existing code — only tests code changed in the current feature

## User Persona

The plugin user: a developer using the iflow-dev workflow to build features. They've completed the implementation phase (all tasks done, TDD scaffolding in place) and want confidence that their code handles more than the happy path before entering review.

## Proposed Solution

### Component: `test-deepener` Agent

A new agent at `plugins/iflow-dev/agents/test-deepener.md` that operates in two phases:

**Phase A (Spec-Only Context):** Receives spec, design, tasks, and PRD goals — but NOT the files-changed list or implementation details. Generates test outlines (Given/When/Then scenario descriptions) organized by six dimensions.

**Phase B (Full Context):** Receives the Phase A outlines PLUS the files-changed list. Reads existing TDD tests to avoid duplication. Writes executable test code, runs the suite, and reports results.

This two-phase dispatch enforces genuine spec-first sequencing — the agent cannot mirror implementation behavior in Phase A because it has no access to it.

### Workflow Integration

Insert as new **Step 6** in `implement.md`. The actual implement.md uses steps 1-8. After insertion:

**Before (current implement.md):**
```
Steps 1-3: Validate, Branch Check, Partial Recovery, Mark Started
Step 4:    Implementation Phase (per-task implementer agents)
Step 5:    Code Simplification Phase (code-simplifier agent)
Step 6:    Review Phase (sub-steps 6a-6e, 3-reviewer loop)
Step 7:    Update State
Step 8:    Completion Message
```

**After (with test deepening):**
```
Steps 1-3: Validate, Branch Check, Partial Recovery, Mark Started
Step 4:    Implementation Phase (per-task implementer agents)
Step 5:    Code Simplification Phase (code-simplifier agent)
Step 6:    Test Deepening Phase (test-deepener agent)       ← NEW
Step 7:    Review Phase (sub-steps 7a-7e, 3-reviewer loop)  ← was Step 6
Step 8:    Update State                                      ← was Step 7
Step 9:    Completion Message                                ← was Step 8
```

#### Dispatch Template

The dispatch follows the same pattern as Step 5 (code-simplifier) in implement.md:

**Phase A — Generate test outlines from spec only:**
```
Task tool call:
  description: "Generate test outlines from spec"
  subagent_type: iflow-dev:test-deepener
  prompt: |
    PHASE A: Generate test outlines from specifications only.
    Do NOT read implementation files. Do NOT use Glob/Grep to find source code.
    You will receive implementation access in Phase B.

    Feature: {feature name}

    ## Spec (acceptance criteria — your primary test oracle)
    {content of spec.md}

    ## Design (error handling contracts, performance constraints)
    {content of design.md}

    ## Tasks (what was supposed to be built)
    {content of tasks.md}

    ## PRD Goals
    {Problem Statement + Goals from PRD}

    Generate Given/When/Then test outlines for all applicable dimensions.
    Return as structured JSON with dimension, scenario name, given/when/then text,
    and derived_from reference to spec criterion.
```

**Phase B — Write executable tests:**
```
Task tool call:
  description: "Write and verify deepened tests"
  subagent_type: iflow-dev:test-deepener
  prompt: |
    PHASE B: Write executable test code from these outlines.

    Feature: {feature name}

    ## Test Outlines (from Phase A)
    {Phase A JSON output}

    ## Files Changed (implementation + simplification)
    {deduplicated file list from implementation-log.md UNION files modified in Step 5}

    Read existing test files for changed code first — skip scenarios already
    covered by TDD tests. Then write executable tests, run the suite, and report.

    Return structured JSON report.
```

#### Failure Mode Control Flow

When newly generated tests fail, the agent distinguishes two categories:

1. **Test syntax/compilation errors:** The agent MUST fix these before reporting. These are bugs in the test code itself, not in the implementation. The agent iterates internally (max 3 attempts) until tests compile and run.

2. **Assertion failures (tests run but fail):** The agent reports these as **spec divergences** — the test expected behavior X (derived from spec) but the implementation produces behavior Y. The agent does NOT rewrite the test to match the implementation. Instead, it includes each divergence in the `spec_divergences` array with:
   - Which spec criterion the test is derived from
   - Expected behavior (from spec)
   - Actual behavior (from test run)
   - The failing test name and file

**Implement.md control flow after Phase B:**
- If `spec_divergences` is empty: proceed to Step 7 (Review Phase)
- If `spec_divergences` is non-empty: surface divergences to user via AskUserQuestion:
  ```
  AskUserQuestion:
    questions: [{
      "question": "Test deepening found {n} spec divergences. How to proceed?",
      "header": "Spec Divergences",
      "options": [
        {"label": "Fix implementation", "description": "Dispatch implementer to fix code to match spec. Re-run test deepening."},
        {"label": "Accept implementation", "description": "The spec was wrong. Skip divergent tests and proceed to review."},
        {"label": "Review manually", "description": "Inspect divergences before deciding."}
      ],
      "multiSelect": false
    }]
  ```
  - "Fix implementation": dispatch implementer agent with divergence list, then re-run full Phase A + Phase B cycle (implementation changes may invalidate Phase A outlines)
  - "Accept implementation": remove divergent tests, proceed to Step 7
  - "Review manually": output divergence details, stop execution

### Six Testing Dimensions

The agent works through these dimensions sequentially. Each dimension has a structured checklist and an **applicability guard** that lets the agent report "N/A — no applicable surface" when a dimension doesn't fit the feature.

#### Dimension 1: Spec-Driven BDD Scenarios

**Source:** Spec acceptance criteria (NOT implementation code)
**Applicability:** Always applicable — every feature has acceptance criteria
**Method:** Each acceptance criterion becomes one or more Given/When/Then scenarios
**Format:** Tests use the project's native framework with Given/When/Then as structural comments:
```python
def test_user_login_with_valid_credentials():
    # Given a registered user with valid credentials
    user = create_test_user(email="test@example.com", password="valid123")
    # When they submit the login form
    response = client.post("/login", data={"email": user.email, "password": "valid123"})
    # Then they receive an auth token and 200 status
    assert response.status_code == 200
    assert "token" in response.json()
```
**Unique Example Rule:** Each test must demonstrate a distinct behavior, not merely vary data — Evidence: [Automation Panda / Three Amigos](https://automationpanda.com/tag/three-amigos/)

#### Dimension 2: Boundary Value & Equivalence Partitioning

**Source:** Function signatures, type constraints, documented limits
**Applicability:** When functions have numeric, bounded-string, or collection parameters. Skip for pure orchestration code with no parametric inputs.
**Method:** For each input parameter with a range or constraint, apply the BVA canonical set: `{min-1, min, min+1, typical, max-1, max, max+1}`
**Equivalence classes:** Group inputs where behavior should be identical, test one representative per class
**Checklist:**
- [ ] Numeric ranges: test both boundaries and one value outside each
- [ ] String lengths: empty, one char, max length, max+1
- [ ] Collections: empty, single element, typical, large
- [ ] Optional/nullable: null, undefined, missing key

#### Dimension 3: Adversarial / Negative Testing

**Source:** Eight exploratory heuristics (Xray/Cem Kaner tradition) — Evidence: [Xray Exploratory Testing Heuristics](https://www.getxray.app/blog/useful-heuristics-for-effective-exploratory-testing-xray-blog)
**Applicability:** When the feature exposes public interfaces or processes user-facing input. Skip for internal refactors with no new API surface.
**Checklist (agent must address each applicable heuristic):**

| Heuristic | Test Question |
|-----------|---------------|
| Never/Always | What invariants must always hold? Test violations. |
| Zero/One/Many | What happens with 0, 1, and N items? |
| Beginning/Middle/End | Position-dependent behavior in sequences? |
| CRUD completeness | Can you Create, Read, Update, Delete — and do they interact correctly? |
| Follow the Data | Track a value from entry to output — does it survive transforms? |
| Some/None/All | Test permission/selection sets at each extreme |
| Starve | What happens under resource pressure (large input, slow dependency)? |
| Interrupt | What happens if the operation is interrupted mid-way? |

**Additional negative categories:**
- Wrong data type (string where number expected)
- Logically invalid but syntactically correct (end date before start date)
- State transition violations (skip required workflow steps)

#### Dimension 4: Error Propagation & Failure Modes

**Source:** Design.md error handling contracts, function signatures
**Applicability:** When design.md documents error contracts or functions have explicit error paths. Skip when the feature is purely additive with no failure modes.
**Method:** For each function that can fail, verify:
- Error is raised/returned (not silently swallowed)
- Error message is informative (contains context, not just "error")
- Caller handles the error (propagation doesn't stop mid-chain)
- Partial failures leave state consistent (no half-written data)
**Checklist:**
- [ ] Each documented error path has a test
- [ ] Upstream dependency failures are simulated (mock timeouts, network errors, file-not-found)
- [ ] Error responses match documented contracts (status codes, error shapes)

#### Dimension 5: Mutation Testing Mindset

**Source:** Implementation code (read in Phase B, AFTER generating spec-driven outlines in Phase A)
**Applicability:** Always applicable — every function should be behaviorally pinned
**Method:** Apply five mental mutation operators to each function — Evidence: [Master Software Testing - Mutation Testing](https://mastersoftwaretesting.com/testing-fundamentals/types-of-testing/mutation-testing)

| Operator | Question |
|----------|----------|
| Arithmetic swap (+ ↔ -) | Would tests catch if I swapped + and -? |
| Boundary shift (>= → >) | Would tests detect off-by-one? |
| Logic inversion (&& ↔ \|\|) | Would tests fail if condition logic changed? |
| Line deletion | Remove this line — do tests notice? |
| Return value mutation | Change return to null/0/empty — do callers catch it? |

**Behavioral pinning check:** A test pins behavior only if: (a) it has specific value assertions (not just type checks), (b) it exercises both sides of branches, (c) it tests at least one boundary per comparison

#### Dimension 6: Performance Contracts

**Source:** Spec performance requirements (if any), design.md performance constraints
**Applicability:** Only when the spec explicitly defines performance requirements. Performance tests without SLA targets are noise — report "N/A — no performance SLAs in spec."
**Types:**
- **Micro-benchmarks:** Isolated function timing with statistical analysis (repeated runs, median + p95)
- **SLA assertions:** Percentile-based contracts: `p50 < Xms, p95 < Yms, p99 < Zms` — Evidence: [Aerospike P99 Latency](https://aerospike.com/blog/what-is-p99-latency/)
- **Memory bounds:** Assert no monotonic memory growth over repeated operations
- **Regression baselines:** Capture current performance as baseline for future comparison

### Anti-Blind-Spot Design

The agent's design encodes six safeguards against self-confirming tests:

1. **Two-phase dispatch (enforced sequencing):** Phase A receives spec-only context and generates test outlines without implementation access. Phase B receives implementation details to write executable code. This is a genuine architectural separation — not a prompt-ordering heuristic. The agent physically cannot read implementation code during Phase A because no file paths are provided and the prompt explicitly prohibits Glob/Grep. — Evidence: Specification-first prompting reduces implementation mirroring ([2024 Oracle Research](https://arxiv.org/html/2410.21136v1)). Note: prompt-level instructions to "not read files" are a soft constraint; the two-phase dispatch is the enforcement mechanism.

2. **Adversarial persona:** System prompt framing: "You are a skeptical QA engineer. Your job is to find what the implementation gets wrong, not to confirm what it gets right. Every test you write should be one that *could* fail."

3. **Structured category checklist:** The six dimensions above are mandatory (with applicability guards) — the agent must address each applicable dimension, preventing gravitational pull toward easy happy-path tests. — Evidence: AI-generated tests cluster around happy-path inputs producing low semantic diversity ([EvoGPT 2025](https://arxiv.org/html/2505.12424v1/))

4. **Mutation testing mindset:** After writing tests, the agent reviews them through the five mutation operators and asks "would this test catch a realistic bug?"

5. **Independent context injection:** The spec's acceptance criteria are the test oracle, not the implementation. System prompt directive: "If the implementation and spec disagree, the spec is correct — write the test to match the spec, and report the divergence."

6. **Descriptive test naming:** Test names must describe the expected behavior in plain English (e.g., `test_rejects_negative_quantities` not `test_quantity_check`). Descriptive naming improves LLM oracle quality by 6-16%. — Evidence: [2024 Oracle Research](https://arxiv.org/html/2410.21136v1)

**Limitation acknowledged:** Safeguards 2, 4, 5, and 6 are prompt-level heuristics with unknown enforcement strength. Safeguard 1 (two-phase dispatch) is the only architectural guarantee. The others reduce mirroring probability but cannot eliminate it.

### Agent Configuration

```yaml
name: test-deepener
description: >
  Deepens test coverage after TDD scaffolding with BDD scenarios,
  edge cases, adversarial testing, and performance SLAs.
  Use when (1) implement command dispatches test deepening phase,
  (2) user says 'deepen tests', (3) user says 'add edge case tests'.
model: opus
tools: [Read, Write, Edit, Bash, Glob, Grep]
color: green  # code-generation category (writes test files)
```

**Model rationale:** Opus for v1 to establish quality baseline. The agent performs multi-dimensional adversarial reasoning, writes correct test code in arbitrary frameworks, and must resist mirroring bias — arguably harder than what the implementer does. Downgrade to sonnet after confirming quality is sufficient across 2-3 features.

**Tool rationale:**
- `Read, Glob, Grep` — analyze existing code and tests
- `Write, Edit` — create/modify test files
- `Bash` — run test suites to verify new tests pass
- No `WebSearch` or `Context7` — the agent works from spec + code, not external docs

### Output Format

```json
{
  "tests_added": [
    {
      "file": "tests/test_auth_edge_cases.py",
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
    "mutation_gaps_found": {"count": 2, "applicability": "applicable"},
    "performance_contracts": {"count": 0, "applicability": "N/A — no performance SLAs in spec"}
  },
  "existing_tests_reviewed": 12,
  "duplicates_skipped": 3,
  "spec_divergences": [
    {
      "spec_criterion": "AC-7",
      "expected": "timeout should be 30s",
      "actual": "implementation uses 60s",
      "failing_test": "tests/test_timeout.py::test_default_timeout_matches_spec"
    }
  ],
  "all_tests_pass": true,
  "summary": "Added 25 tests across 3 files. Reviewed 12 existing TDD tests, skipped 3 duplicates. Found 1 spec divergence."
}
```

### Files Changed List

The files-changed list passed to Phase B is the **union** of:
1. Files from the implementation-log.md (Step 4 output)
2. Files modified during code simplification (Step 5)

This ensures the test-deepener sees the final shape of the code, not the pre-simplification shape. The implement.md command assembles this union before dispatching Phase B.

### Test Budget Guidance

The agent targets **15-30 tests per feature**. If exceeding 40, the agent re-prioritizes to the highest-risk tests per dimension rather than generating exhaustively. This is a soft budget in the system prompt, not a hard cap — complex features with many acceptance criteria may legitimately need more.

## Success Criteria

1. **Dimension coverage:** Agent addresses all 6 dimensions for each feature (reporting "N/A" with reason for inapplicable dimensions)
2. **Spec traceability:** Every test has a non-empty `derived_from` field referencing a specific spec acceptance criterion, design contract, or testing dimension (e.g., `dimension:mutation` for mutation-derived tests) — not a source file
3. **Existing test awareness:** Agent reports `existing_tests_reviewed` count and `duplicates_skipped` count, demonstrating it read TDD tests before generating
4. **Test suite green:** All new tests pass. Assertion failures are reported as spec divergences with expected-vs-actual evidence, not silently fixed to match implementation
5. **Seamless integration:** Implement command runs test deepening (both phases) without user intervention; review phase benefits from deeper coverage

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Agent mirrors implementation despite two-phase dispatch | Low-Medium | High | Phase A has no implementation access (architectural); adversarial persona + mutation mindset as secondary checks; spec divergences surfaced in output |
| Too many tests generated (noise) | Medium | Medium | Applicability guards per dimension; soft budget of 15-30 tests; agent prioritizes high-risk areas |
| Performance tests flaky in CI | Low | Medium | Performance dimension only activates when spec has explicit SLAs; uses statistical runs not single measurements |
| Agent generates tests that don't compile | Low | Medium | Phase B iterates internally (max 3 attempts) until tests compile; compilation failures are agent bugs, not spec divergences |
| Test deepening phase adds significant time | Medium | Medium | Two agent calls (Phase A + B) instead of one; mitigated by focused scope (only changed files) and soft test budget |
| Phase A outlines are too abstract to implement in Phase B | Low | Medium | Phase A returns structured JSON with specific Given/When/Then text, not vague descriptions; Phase B has full implementation context to concretize |

## Open Questions

1. Should the test-deepener have a reviewer loop (like implementation), or is a single pass sufficient? — Assumption: Single pass for v1; add reviewer if quality issues emerge
2. Should the agent's test-generation be configurable per-feature (e.g., skip specific dimensions)? — Assumption: No configuration for v1; applicability guards handle scoping automatically
3. Should opus be downgraded to sonnet after quality baseline is established? — Assumption: Yes, evaluate after 2-3 features; track test quality and spec-divergence detection rate as metrics
