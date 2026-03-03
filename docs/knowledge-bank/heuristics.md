# Heuristics

Decision guides for common situations. Updated through retrospectives.

---

## Decision Heuristics

### Reference File Sizing
Target ~100-160 lines per reference file for balance between completeness and readability.
- 4 files at ~480 total lines is a good ratio for a thin orchestrator pattern
- Benefit: Each file is independently readable without scrolling fatigue
- Source: Feature #018
- Last observed: Feature #33
- Observation count: 1

### Line Budget Management
Target 90-95% of SKILL.md budget (450-475 of 500 lines).
- Landing at 96% (482/500) is acceptable but leaves minimal room for future additions
- If approaching 98%+, consider extracting content to reference files
- Source: Feature #018
- Last observed: Feature #33
- Observation count: 2

### AskUserQuestion Option Count
Keep AskUserQuestion to 6 explicit options maximum (7 with built-in "Other").
- The system automatically provides "Other" for free text — no need to waste an option slot
- 7 total choices is the upper limit for usability
- Source: Feature #018
- Last observed: Feature #33
- Observation count: 1

### Cross-Skill Coupling Depth
Keep cross-skill dependencies to read-only access of reference files only.
- Never have one skill Write to another skill's directory
- One fallback level (hardcoded content) is sufficient for graceful degradation
- Two levels of fallback adds complexity without proportional reliability gain
- Source: Feature #018
- Last observed: Feature #33
- Observation count: 1

### Graph-Text Consistency as First-Pass Check
When reviewing plans with dependency graphs, validate graph-text consistency before deeper review.
- 4 of 6 plan iterations in Feature #021 were caused by graph-text mismatches
- Check: Every dependency mentioned in text appears as an edge in the graph, and vice versa
- Source: Feature #021
- Last observed: Feature #33
- Observation count: 1

### Read Target Files During Task Creation
When creating tasks for file modifications, read the target file first and include exact line numbers.
- Tasks without this specificity (7.1, 7.2, 7.3) were the ones blocked in task review
- Investment in precision during task creation pays off with lower implementation iteration count
- Source: Feature #021
- Last observed: Feature #33
- Observation count: 2

### Reviewer Iteration Count as Complexity Signal
Reviewer iteration counts suggest complexity: 2 = straightforward, 3 = moderate, 4+ = initially underspecified. High early-phase iterations predict thorough preparation, not implementation risk -- Features #022 and #025 both had 15-30 pre-implementation iterations but 0-1 implementation issues. Exception: Feature #027 had 19 pre-implementation iterations AND 10 implementation iterations, suggesting complex merge/transformation logic creates sustained review surface area even after thorough pre-implementation review.
- Feature #021 plan had 6 iterations (highest), mostly from dependency graph contradictions
- If plan iterations exceed 3, check for structural issues (dual representations, missing test cases)
- Source: Feature #021
- Last observed: Feature #031
- Observation count: 8

### Circuit Breaker Hits as Assumption Signals
Circuit breaker hits in design review indicate a fundamental assumption mismatch, not incremental quality issues. When design review hits 5 iterations, the root cause is typically a wrong foundational assumption (e.g., wrong file format) rather than accumulated small issues.
- Source: Feature #022, design phase
- Last observed: Feature #031
- Observation count: 3

### Per-File Anchor Verification for Cross-Cutting Changes
Cross-cutting changes touching 14+ files benefit from explicit per-file insertion anchor verification in the plan phase. Every insertion point needs unique verification when files have different structures.
- Source: Feature #022, plan/tasks phases -- prevented 4 incorrect line references
- Last observed: Feature #33
- Observation count: 1

<!-- Example format:
### When to Create a New Service
Create a new service when:
- Functionality is used by 3+ other components
- Has distinct lifecycle from parent
- Needs independent scaling

Otherwise: Keep it as a module within existing service.
-->

### Read Real File Samples During Design When Parsing Existing Files
When a feature involves parsing existing files, the designer should read at least one real instance of each input file and note structural quirks (HTML comment blocks, template examples, empty sections) that the parser must handle. These quirks are invisible from spec descriptions alone and will surface as blockers in later phases.
- Source: Feature #023 — Plan review iter 2 discovered HTML comment blocks in knowledge bank files that design did not account for
- Confidence: high
- Last observed: Feature #33
- Observation count: 1

### Comprehensive Brainstorm PRDs Correlate With Fast Specify Phases
When a brainstorm PRD exists and is comprehensive (300+ lines with explicit success criteria), the specify phase acts as a scoping/structuring pass rather than a discovery pass, typically completing in under 30 minutes with minimal review iterations.
- Source: Feature #023 — 404-line brainstorm PRD led to 29-minute specify phase with zero review iterations
- Confidence: high
- Last observed: Feature #025
- Observation count: 2

### Expect Extra Task Review Iterations When Plan Leaves Format Details Ambiguous
If the plan describes 'what' a format contains but not the exact 'shape' (all fields, ordering, delimiters), task review will iterate until the format is unambiguous enough for implementation. Budget 2-3 extra iterations for this.
- Source: Feature #023 — 3 of 5 taskReview iterations were format back-fill (missing dependency, unspecified synthetic format, missing metadata field)
- Confidence: high
- Last observed: Feature #33
- Observation count: 1

### Probe Runtime Behavior Boundaries During Design Review
For each component interface, explicitly ask 'What does the caller see for each distinct outcome?' and 'How does the component access its configuration at runtime?' These two questions catch the most common class of design-phase blockers.
- Source: Feature #025 — 3 of 5 design blockers were runtime behavior gaps: differentiated return (Stored vs Reinforced), config injection (model cannot read files during session), MCP-to-CLI fallback undefined
- Confidence: high
- Last observed: Feature #025
- Observation count: 1

### Validate TDD Test Ordering and RED-Phase Authenticity in Plans
When a plan claims TDD methodology, verify (1) test steps precede implementation steps, and (2) each RED test includes a concrete reason it will fail against current code. Tests that pass immediately are not valid RED tests.
- Source: Feature #025 — Plan iter 1: TDD order violation (tests after implementation); Plan iter 2: test_new_entry_returns_stored would pass immediately against current code
- Confidence: medium
- Last observed: Feature #025
- Observation count: 1

### Lightweight Documentation Improvements Skip Feature Workflow
For scoped documentation changes (<50 lines, single-pass analysis, no cross-system rework), direct commits to primary branches are appropriate. Reserve feature workflow for substantive changes requiring multi-file validation.
- Source: CLAUDE.md Working Standards addition — +12 lines, no review iterations, verified against three anchor points
- Confidence: high
- Last observed: 2026-02-22
- Observation count: 1

### Markdown-Only Feature Task Sizing
For features producing exclusively markdown artifacts (agents, skills, commands), the natural task decomposition limit is one section or dimension per task, which may require 20-30 minutes. Document this as the natural decomposition limit rather than treating exceeded 15-min guidelines as a violation.
- Source: Feature #026, create-tasks — 4 chain review iterations consumed by task-size concern; domain reviewer confirmed no split was possible
- Confidence: high
- Last observed: 2026-02-22
- Observation count: 1

### Shifting Security Concern Frames as Threat Model Gap Signal
When a security reviewer's concern shifts to a new frame each iteration after a fix is applied (basic validation -> canonicalization bypass -> allowlist), the root cause is a missing threat model, not an incomplete fix. Stop applying fixes and define the threat model first.
- Source: Feature #026, implement iters 3-5 — path extraction security review ran 3 iterations with shifting frames
- Confidence: medium
- Last observed: 2026-02-22
- Observation count: 1

### Budget 8-10 Implementation Iterations for Complex Merge/Transformation Skills
When a SKILL.md requires complex merge/transformation logic (Accept-some, CHANGE markers, multi-step file rewriting), expect 8-10 implementation review iterations. Each fix in conditional logic exposes adjacent problems in a cascading pattern. Consider pre-extracting the complex logic into a reference file to reduce the review surface area.
- Source: Feature #027 — 8-step process with CHANGE/END CHANGE generation, Accept-some merge, and malformed marker fallback took 10 implementation iterations
- Confidence: medium
- Last observed: Feature #027
- Observation count: 1

### Standard Mode Sufficient for Standalone New-Component Features
Standard mode is sufficient for features that introduce new standalone components (skill + commands + reference files) without modifying existing workflow phases. Reserve Full mode for features that modify existing phase sequences or cross-cutting concerns.
- Source: Feature #027 — Standard mode produced complete 3,228-line feature in 5.6 hours without modifying existing components
- Confidence: medium
- Last observed: Feature #027
- Observation count: 1

### Phase-Reviewer Cap Saturation Rate as Feature Scope Signal
When the phase-reviewer (gatekeeper) hits the 5-iteration cap in 3 or more of 5 phases, the feature has complex multi-file coordination requiring explicit inter-artifact invariants. Budget an extra 30-60 minutes per capped phase for the additional resolution iterations. This is distinct from a quality problem — it reflects the number of enumerable invariants that must be explicitly stated across artifacts.
- Source: Feature #028 — phase-reviewer hit cap in 4/5 phases (specify, design-review, design-handoff, create-tasks both stages). Feature involved 8 files with coordinated dispatch logic across 3 commands and a skill.
- Confidence: medium
- Last observed: Feature #028
- Observation count: 1

### Budget 30-40 Pre-Implementation Review Iterations for Multi-Integration MCP Features
Multi-integration MCP server features (DB + backfill + server + bootstrap + hooks) should budget 30-40 pre-implementation review iterations. Reviewer caps should be framed as expected behavior, not quality failure. The combinatorial surface area of SQL schema + MCP tools + backfill logic + stdio transport creates enumerable invariants that reviewers discover incrementally.
- Source: Feature #029 — 32 pre-implementation iterations, 5 of 6 reviewer sequences hit caps, yet implementation completed in 5 iterations with 184 tests passing
- Confidence: high
- Last observed: Feature #029
- Observation count: 1

### Specificity Cascade Signal in Task Review
When task review blocker counts escalate per iteration (e.g., 0→1→7→5→3) rather than converge, each resolved ambiguity is revealing adjacent underspecification one abstraction level deeper. This is a specificity cascade — not a quality problem. Budget extra iterations and expect the cascade to bottom out when concrete types (DDL, CTE bind parameters, CHECK constraints) are reached.
- Source: Feature #029, create-tasks phase — blocker counts escalated through 5 iterations as method signature → parameter contract → DDL → CHECK constraint → CTE semantics were progressively specified
- Confidence: high
- Last observed: Feature #029
- Observation count: 1

### Design Handoff Pre-Flight Checklist
Before submitting design.md to handoff review, verify: (1) test strategy section exists, (2) all TD alternatives documented, (3) dependency sets enumerated per component, (4) merge/conflict semantics specified. Would reduce handoff iterations from 5 to 2-3.
- Source: Feature #029 — handoff review hit 5-iteration cap; most iterations addressed items that a pre-flight checklist would have caught
- Confidence: medium
- Last observed: Feature #029
- Observation count: 1

### AC Traceability Pass for Two-Layer Architectures
For features with separated storage and rendering layers, add an explicit traceability task mapping each acceptance criterion to BOTH storage AND rendering functions. Gaps between layers are invisible until end-to-end output testing.
- Source: Feature #029 — AC-5 depends_on_features stored correctly in DB but _format_entity_label ignored the metadata field; gap invisible until implementation iter 2
- Confidence: medium
- Last observed: Feature #029
- Observation count: 1

### Reviewer Iteration Count as Structural Gap Signal
If 3+ review iterations address the same issue category, the underlying section has a structural gap — restructure it, don't add more notes. Adding incremental comments to an ill-structured section does not converge.
- Source: Feature #030, design — R3 implications recurred iters 1, 3, 4, 5; only resolved when restructured as a behavioral change table
- Confidence: high
- Last observed: Feature #030
- Observation count: 1

### Pre-Declare Artifact Completeness in Large-Artifact Dispatches
Add a line-count header before large artifacts (>200 lines) in reviewer dispatches: "Full plan.md — 255 lines, complete content follows." Instruct reviewers to flag truncated artifacts as process errors before evaluating content. Makes prompt compression detectable.
- Source: Feature #030, create-plan + create-tasks — both false-positive incidents involved artifacts over 200 lines
- Confidence: high
- Last observed: Feature #030
- Observation count: 1

### Scope Grep Audit Steps to Changed Files with Pre-Declared False Positives
Grep verification steps in plans must scope to the explicit list of changed files (not full directory) and enumerate expected false positives with rationale. Eliminates the multi-iteration correction pattern for false positive lists.
- Source: Feature #030, plan iters 1–4 + task iter 4 — grep false positive list required 4 corrections before scoping to 6 changed files
- Confidence: high
- Last observed: Feature #030
- Observation count: 1

### Double Circuit Breaker Indicates Structural Authoring Problem
If both stages of a two-stage review hit the circuit breaker (iteration cap), the artifact has a structural problem that iteration cannot fix. Stop and re-examine the approach: the issue categories from unresolved warnings point to the structural root cause.
- Source: Feature #031, create-tasks phase — both taskReview (5/5) and chainReview (5/5) hit cap; unresolved warnings pointed to placeholder syntax and verification weakness — both are authoring-pattern issues
- Confidence: high
- Last observed: Feature #031
- Observation count: 1

### Plan Review Iterations Scale With Concern Domains
Plan review iterations scale with the number of distinct concern domains in the feature. Features touching git operations, prompt engineering, and test infrastructure simultaneously should expect 4+ plan review iterations.
- Source: Feature #031, create-plan phase — 8 iterations across git operations (5 issues), test regression (2 issues), dependency ordering (3 issues), and verification feasibility (2 issues)
- Confidence: medium
- Last observed: Feature #031
- Observation count: 1

### Design Handoff Pre-Flight Check for Edge-Case Test Scenarios
Before submitting design.md to handoff review, scan all TD sections for "test" or "testing" keywords. Any test scenario described in a TD must be promoted to either an AC or a named plan task. Buried test scenarios in TDs propagate as blockers across 2+ downstream phases.
- Source: Feature #032 — TD2 "testing note" for reversed attribute order drove design handoff cap and plan-reviewer blocker (3 downstream iterations)
- Confidence: high
- Last observed: Feature #032
- Observation count: 1

### Shared Algorithm Without Named Contract Predicts 3-4 Extra Chain Iterations
When a design describes the same algorithm in two or more sections using parallel prose (no shared name, no I/O contract), expect 3-4 extra chain review iterations to incrementally define: name, label, inputs, outputs, and placement ordering. Each iteration adds one missing contract element.
- Source: Feature #032 — match_anchors_in_original described in C6 and C9 took 4 chain iterations to fully specify; create-plan duration was 2x create-tasks, signaling underspecified shared behavior
- Confidence: high
- Last observed: Feature #032
- Observation count: 1

### Task Review Cap on Invocation Issues Signals Missing Template Field
When task review hits the iteration cap and the majority of unresolved concerns are invocation-mechanism issues (how to run something), the task template is missing a required 'Invocation' field. The review loop cannot converge without a structural template fix.
- Source: Feature #033, create-tasks — taskReview hit 5/5 cap with 42% of concerns being invocation-mechanism issues (T02 iterated through 5 forms without resolving)
- Confidence: high
- Last observed: Feature #033
- Observation count: 1

### For 40+ Task Features Create-Tasks Is the Bottleneck
For features with 40+ tasks, create-tasks is the bottleneck — budget 90-120 min and 8-10 review iterations. Invocation mechanism clarity determines whether the cap is hit. Two-stage review (task review + chain review) compounds iteration count.
- Source: Feature #033 — 40 tasks required 9 create-tasks iterations (5 task review + 4 chain review), taking ~95 min; cap hit on task review stage
- Confidence: high
- Last observed: Feature #033
- Observation count: 1

### Text-Refactoring Features Budget Heavily for Planning, Lightly for Implementation
Text-refactoring features (70+ files, uniform mechanical changes) produce clean implementations — budget heavily for planning phases (specify/design/create-tasks) and lightly for implementation. The planning investment prevents implementation rework; the refactoring itself executes cleanly.
- Source: Feature #033 — 70 files, 5004 insertions, 589 deletions, only 2 implementation blockers (both trivial grep flags); 29 pre-implementation review iterations vs 5 implementation review iterations
- Confidence: medium
- Last observed: Feature #033
- Observation count: 1

### SQLite Platform Default Verification at Design Time
For database schema features using SQLite, verify FK ON DELETE default (NO ACTION, not RESTRICT), CHECK constraint syntax, and WAL mode implications during design. These are one-lookup facts that surface as security-reviewer blockers when deferred to implementation.
- Source: Feature #004 — SQLite FK default unknown at design time consumed 2 of 4 implement review iterations
- Confidence: high
- Last observed: Feature #004
- Observation count: 1

### Explicit Verification Strategy for Documentation-Only Features
Documentation-only features (ADRs, design docs, knowledge artifacts) should include a verification strategy section in the plan that distinguishes automatable grep checks from manual readability and completeness gates. Without explicit labeling, grep checks appear equivalent to executable tests in review.
- Source: Feature #004 — grep-based verification was the only strategy; readability issue surfaced at implement review with no earlier gate
- Confidence: medium
- Last observed: Feature #004
- Observation count: 1

### Audit and Analysis Features Require Bespoke Completeness Criteria
Documentation/analysis features that perform exhaustive discovery (guard audits, dependency mapping, API inventories) have no natural termination condition. The specify phase must invent a project-specific completeness criterion (e.g., two-pass convergence check, row-count validation, coverage matrix) before implementation can begin. Budget 3-4 extra specify iterations for this invention step, and expect 4 blockers in iter 1.
- Source: Feature 006 — specify phase required 10 review iterations; 4 blockers in iter 1 were all completeness-criterion gaps; all 4 resolved by iter 2 once two-pass methodology was introduced
- Confidence: high
- Last observed: Feature 006
- Observation count: 1

### Intermediate Result Persistence Overhead Scales With Session Count, Not Task Complexity
For single-session documentation/analysis tasks, intermediate result persistence requirements are proportional to session count, not task complexity. A complex 60-guard audit in one session requires less persistence infrastructure than a simple 5-file rename across two sessions. When session count is provably 1 and intermediate outputs are reconstructible in minutes, limit design investment in recovery paths to a single sentence.
- Source: Feature 006 — design handoff consumed 4 of 5 iterations on C1-C3 ephemeral result persistence for a task designed for single-session execution; accepted at cap as acceptable risk
- Confidence: medium
- Last observed: Feature 006
- Observation count: 1

### Reviewer Cap Saturation Across All Phases Is Normal for First-of-Kind Audit Features
When a feature type has no established workflow template (first audit, novel analysis methodology), expect the iteration cap to be hit in every review phase. This is not a quality failure — it reflects the overhead of inventing the template simultaneously with validating the artifact. Extract the discovered template elements into the specifying skill so the next audit feature completes specify in 2-3 iterations rather than 10.
- Source: Feature 006 — all 5 review phases hit the iteration cap (5) or near-cap (4); 38 total review iterations for a documentation-only feature; completeness criterion, output schema, and verification procedure were all invented during the specify phase
- Confidence: medium
- Last observed: Feature 006
- Observation count: 1
