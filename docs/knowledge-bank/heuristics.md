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
- Last observed: Feature 012
- Observation count: 9

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

### Lookup Tables With 5+ Entries Require Independent Cross-Verification
Any constant mapping one domain to another (phase→guard, artifact→guard, enum values) with 5 or more entries should be independently cross-verified against its source document. Table inversions (keys and values swapped) pass casual inspection because the table looks "full" and "correct" even when every entry is wrong.
- Source: Feature 007, design iter 2 — PHASE_GUARD_MAP had all 9 entries inverted, passed design-reviewer iter 1; caught only when reviewer's attention was drawn by a related gap in the same section
- Confidence: high
- Keywords: ["lookup-table", "cross-verification", "design-review", "constant-validation", "inversion-error"]
- Last observed: Feature 007
- Observation count: 1

### Phase-Reviewer Cap Warnings That Don't Materialize Signal Conservative Review, Not Implementation Skill
When unresolved phase-reviewer cap warnings do not cause implementation failures, the warnings were conservatively classified at the phase-reviewer's information level — reasonable at review time but not blocking in practice. Track which cap warnings materialize across features to calibrate review conservatism over time.
- Source: Feature 007 — 3 unresolved cap warnings (create-plan: 2 on per-phase test breakdown and false-green risk; create-tasks: 1 on inline verification commands); 0 implementation deviations, 180 tests passing, 29/29 tasks complete
- Confidence: medium
- Keywords: ["phase-reviewer", "iteration-cap", "warning-calibration", "conservative-review", "materialization-rate"]
- Last observed: Feature 007
- Observation count: 1

### Pre-spec API Research Budget
For features with `depends_on_features`, budget 30 minutes to read each dependency's public interface before spec authoring. Feature 008 had 2 dependencies (007, 005) and all 4 iter-1 specify blockers were API assumption errors resolvable by pre-reading. The 30-minute investment would have saved 2 review iterations (~40 minutes).
- Source: Feature 008, specify phase — 4 iter-1 blockers from unverified API assumptions; 2 dependencies required pre-reading
- Confidence: high
- Keywords: ["pre-spec", "api-research", "dependency", "time-budget", "specify-phase"]
- Last observed: Feature 008
- Observation count: 1

### 4-5:1 Test-to-Code Line Ratio for Transition-Orchestrator Modules
State-machine orchestrators require combinatorial path coverage. A 4-5:1 test-to-code line ratio is a floor, not a ceiling. Feature 008 produced 1,739 test lines for 366 engine lines (4.7:1 ratio) with 85 tests covering all transition paths, gate combinations, and hydration scenarios.
- Source: Feature 008, implement phase — engine.py 366 lines, test_engine.py 1,739 lines / 85 tests (4.7:1 ratio)
- Confidence: medium
- Keywords: ["test-ratio", "state-machine", "orchestrator", "combinatorial-coverage", "transition-engine"]
- Last observed: Feature 008
- Observation count: 1

### Live Line Numbers Expire Before Implementation — Pre-Step Grep Required
When plans reference specific source line numbers for modification targets (e.g., "modify lines 605, 622, 640"), those numbers become stale as prior implementation tasks commit changes that shift line offsets. At the START of each implementation step, run a grep/search to resolve current locations rather than relying on plan-time line numbers.
- Source: Feature 010, create-plan chainReview note — "4.2 line numbers are static approximations — engineer should run pre-commit grep at START of 4.2 to get current line numbers"
- Confidence: high
- Keywords: ["line-numbers", "implementation", "grep", "dynamic-resolution", "stale-references"]
- Last observed: Feature 010
- Observation count: 1

### Force-Approve Correctness Criteria
Force-approve is correct when: (1) all domain reviewers have individually approved at least once, (2) remaining warnings are formatting/documentation only (zero logic issues), and (3) the review loop is at iteration 4+ with no convergence path. Document these criteria as the decision framework rather than treating force-approve as an exception.
- Source: Feature 011, implement phase — all 3 reviewers individually approved; remaining iters 2-4 were type annotation formatting cascade
- Confidence: high
- Keywords: ["force-approve", "circuit-breaker", "review-criteria", "formatting-only", "convergence"]
- Last observed: Feature 011
- Observation count: 1

### FTS5 Database Feature Pre-Spec Checklist
Before specifying any SQLite FTS5 feature, verify: (1) sync mechanism — triggers are infeasible for external content tables, use application-level sync; (2) availability detection — cannot use `SELECT fts5()`, must use CREATE attempt; (3) DELETE/rebuild behavior — DELETE FROM unreliable on external content tables, use DROP+CREATE; (4) keyword operator handling — FTS5 operators (OR, AND, NOT, NEAR) must be stripped from user queries. Each of these surfaced as a separate blocker in Feature 012 across 3 phases.
- Source: Feature 012 — spec iter 1 (trigger infeasibility), design iter 2 (availability detection), plan iter 3 (DELETE unreliability), plan iter 1 (keyword operators)
- Confidence: high
- Last observed: Feature 012
- Observation count: 1

### Schema Version Assertion Census Before Plan Submission
When a migration changes the schema version number, enumerate ALL existing version assertions in tests (via `grep -n 'schema_version.*"N"'`) and include the count in the plan. Feature 012 had 5 such assertions but the plan initially identified only 2, consuming 2 plan-review iterations to discover the remaining 3.
- Source: Feature 012, create-plan phase — plan iter 2 blocker: only 2 of 5 schema_version assertions identified; resolved by grep census
- Confidence: high
- Last observed: Feature 012
- Observation count: 1

### 4.5:1 Test-to-Code Ratio for FTS5 Search Features
FTS5 search features produce a ~4.5:1 test-to-code line ratio due to the combinatorial surface of sync operations (register, update, search) × input categories (normal, adversarial, edge-case) × FTS-specific scenarios (availability, rebuild, operator sanitization). Feature 012 produced 1112 test lines for ~250 implementation lines.
- Source: Feature 012 — test_search.py (864 lines) + test_search_mcp.py (248 lines) for ~250 lines of implementation
- Confidence: high
- Last observed: Feature 012
- Observation count: 1

### TOCTOU Race Uniform Catch Specification
For operations that check-then-create (e.g., check file exists → create record), specify "catch ALL ValueError uniformly" as the stable resolution rather than enumerating individual race scenarios. Enumerating race scenarios is always incomplete and consumes plan-review iterations as each new scenario is discovered.
- Source: Feature 011, create-plan phase — TOCTOU race in meta_json_only path consumed plan-reviewer iterations until uniform catch was specified
- Confidence: medium
- Keywords: ["toctou", "race-condition", "uniform-catch", "valueerror", "check-then-create"]
- Last observed: Feature 011
- Observation count: 1

### Field-Source Mapping Table as Spec Completeness Signal
When a feature compares fields from heterogeneous sources (DB vs filesystem, API vs config), require a unified field-source mapping table in the spec. Prose descriptions of field comparison across multiple requirement sections drive 3+ reviewer iterations as each iteration surfaces one more mapping gap.
- Source: Feature 011, specify phase — comparison semantics described in prose across R1, R2, R8 drove 5 spec-reviewer iterations; a mapping table would have surfaced all gaps at once
- Confidence: high
- Keywords: ["field-source-mapping", "spec-completeness", "comparison-feature", "heterogeneous-sources", "specify-phase"]
- Last observed: Feature 011
- Observation count: 1

### Accepted-Delta Annotation Must Be Self-Sufficient in One Write
When writing an "accepted delta" annotation for a spec-design divergence, complete the annotation in one edit with: (1) the exact canonical format string, (2) any prefix the helper layer adds (e.g., "Error: " + ValueError.message), and (3) one concrete test assertion example.
- Source: Feature 013, design handoff — 5 iterations extracting one sub-component each
- Confidence: high
- Keywords: ["accepted-delta", "annotation-completeness", "handoff-review", "error-format", "one-write"]
- Last observed: Feature 013
- Observation count: 1

### Spec Issue Count Predicts Duration Only When Issues Are Interdependent
10 spec issues in iteration 1 resolved in 3 total iterations when all issues were leaf concerns (each independently fixable). When iteration-1 issues are disjoint, total phase duration scales with distinct concern categories, not total issue count. Only branching concerns (one fix reveals sub-issues) drive high iteration cascades.
- Source: Feature 013, specify phase — 10 issues iter 1 (3 blockers, 7 warnings), all independently fixable; 3 total iterations to approval
- Confidence: medium
- Keywords: ["spec-review", "issue-count", "convergence", "leaf-concerns", "specify-phase"]
- Last observed: Feature 013
- Observation count: 1

### Manual Verification AC Requires Three Elements at Spec Time
When authoring a manual verification AC, include all three: (1) exact environment setup, (2) exact command to run, (3) exact expected output. Missing any one causes the handoff reviewer to request it — one per iteration.
- Source: Feature 014, specify-handoff iters 3-5 — each iteration added one more precision element
- Confidence: high
- Keywords: ["acceptance-criteria", "manual-verification", "specify-phase", "handoff-review", "three-elements"]
- Last observed: Feature 014
- Observation count: 1

### Hook Smoke-Test Task Requires Four Pre-Specified Mechanics
Pre-specify all four: (1) debug copy in hooks dir (not /tmp) for correct SCRIPT_DIR; (2) cp+sed approach, never git checkout; (3) pipe stdin explicitly; (4) capture stdout and debug-stderr separately. These are discovered in strict sequential order by chain reviewers when missing.
- Source: Feature 014, create-tasks chain review iters 1-5
- Confidence: high
- Keywords: ["hook-smoke-test", "bash-hook", "instrumented-copy", "stdin-pipe", "stderr-capture", "task-authoring"]
- Last observed: Feature 014
- Observation count: 1

### Identical-Output Fallback Paths Require Stderr-Based Path Discrimination
When a hook wraps existing logic in try/except with a fallback producing identical stdout, the only verification is stderr inspection. Design the debug strategy around stderr capture before task authoring.
- Source: Feature 014, design + create-tasks — stderr capture strategy discovered during chain review rather than task authoring
- Confidence: high
- Keywords: ["fallback-path", "try-except", "debug-strategy", "stderr", "path-discrimination", "hook-migration"]
- Last observed: Feature 014
- Observation count: 1

### Single-Issue First Implement Iteration on Markdown Files Is a Holistic Sweep Signal
When the first implement review iteration on a markdown-only feature returns exactly one readability warning (not a logic or correctness issue), it signals the quality reviewer is scanning incrementally. Expect 3-4 more single-issue iterations leading to circuit breaker. Intervene immediately: instruct reviewer to read all changed files end-to-end before flagging.
- Source: Feature 015, implement run 1 iter 1 — single stale text warning predicted 3 more single-issue iterations
- Confidence: high
- Keywords: ["first-iteration", "single-issue", "markdown", "holistic-sweep", "quality-reviewer", "early-signal"]
- Last observed: Feature 015
- Observation count: 1

### Unresolved Plan Cap Warnings About Ambiguity Cost 1-2 Task Review Iterations Each
When plan-review hits its iteration cap with unresolved warnings about prose ambiguity in edit steps, each warning materializes as 1-2 task-review blockers. The warnings don't disappear — they shift downstream. Budget accordingly: 2 unresolved plan warnings ≈ 2 extra task-review iterations.
- Source: Feature 015, plan-review cap (iter 5) left 2 warnings → task review iter 1 surfaced 5 issues (3 rooted in plan ambiguity)
- Confidence: high
- Keywords: ["plan-cap", "unresolved-warnings", "downstream-cost", "task-review", "ambiguity", "iteration-budget"]
- Last observed: Feature 015
- Observation count: 1

### Grep-First Scope Discovery for Removal/Renaming Features
For features that remove or rename code references, run a broad-scope grep across the entire codebase before drafting the design component map. This captures all affected files on the first pass instead of discovering them incrementally during review iterations.
- Source: Feature 017, design phase — component map grew 7 to 10 files across 3 iterations; earlier grep would have produced correct scope on first pass
- Confidence: high
- Keywords: ["grep-first", "scope-discovery", "removal-features", "renaming-features", "component-map", "design-phase"]
- Last observed: Feature 017
- Observation count: 1

### Full JSON Response Shapes Inline in Specs
When specifying MCP tool interactions, include the full JSON response shape (including null variants and edge cases) inline in the spec rather than referencing field names only. This prevents downstream phases from hitting blockers when encountering unexpected response structures.
- Source: Feature 017, specify phase — 2 iterations needed for get_phase JSON response shape including null current_phase handling
- Confidence: medium
- Keywords: ["json-response", "mcp-tools", "spec-precision", "null-variants", "inline-documentation"]
- Last observed: Feature 017
- Observation count: 1

### Derive Counts From Lists Rather Than Hardcoding in Prose
When prose references a count (e.g., "7 target files"), derive it from the actual list rather than hardcoding. Lists change during review iterations; hardcoded counts become stale and trigger additional review cycles to correct.
- Source: Feature 017, design phase — file count "7" became stale after adding 3 files, triggering an extra review iteration
- Confidence: high
- Keywords: ["derived-counts", "hardcoded-numbers", "stale-references", "prose-accuracy", "review-iterations"]
- Last observed: Feature 017
- Observation count: 1

### create-plan Double Cap Predicts Three Simultaneous Blocker Categories
When both plan-reviewer and chain-reviewer stages each hit the 5-iteration cap, expect three or more independent blocker categories to be active simultaneously. A single category resolves in 2–3 iterations; double cap requires all categories to converge at the same time, which rarely happens before iteration 8–10. Budget 150–180 minutes for create-plan when the feature combines: (a) TDD methodology, (b) shell wrapper invocation, and (c) a multi-phase dependency graph with 4+ phases.
- Source: Feature 018, create-plan phase — 165 min, 10 iterations, both plan-reviewer and chain-reviewer hit 5/5 cap; three concurrent blocker categories: TDD order inverted, dependency graph contradictions (4.1/4.3 parallel vs sequential redrawn 4 times), shell wrapper invocation pattern ($PLUGIN_DIR/../.. vs direct script path)
- Confidence: medium
- Keywords: ["create-plan", "double-cap", "iteration-budget", "tdd-ordering", "dependency-graph", "shell-wrapper", "concurrent-blockers"]
- Last observed: Feature 018
- Observation count: 1

### Recurring Cross-Phase Blocker in Same Category Signals Missing Spec-Level Annotation
When the same issue category (e.g., Python import paths, PYTHONPATH, shell wrapper mechanics) reappears as a blocker across 3 or more phase boundaries, the spec is missing a foundational annotation that downstream phases are independently re-discovering. Stop and add the annotation to spec before continuing.
- Source: Feature 018 — import path/PYTHONPATH blocker appeared at design, plan iter 1, task iter 2, and task iter 5 (4 phases). The correct PYTHONPATH root and import base were never stated in the spec, so each reviewer had to re-derive them.
- Confidence: high
- Keywords: ["cross-phase-blocker", "recurring-issue", "spec-annotation", "import-path", "pythonpath", "discovery-overhead"]
- Last observed: Feature 018
- Observation count: 1

### PoC Gate Requires Four Elements Before Design Handoff
A PoC validation gate in a design document must specify all four elements atomically before handoff: (1) exact pass/fail criteria with commands and expected output, (2) named failure contingency with alternative approach, (3) task sequencing showing conditional branches, (4) where the PoC artifact lives on disk. Missing any one causes the handoff reviewer to request it in a separate iteration.
- Source: Feature 018, design handoff — 4 iterations to resolve PoC gate mechanics: iter 1 added failure contingency, iter 2 added pass/fail criteria and artifact file location, iter 3 added task sequencing with conditional branches, iter 4 approved
- Confidence: medium
- Keywords: ["poc-gate", "design-handoff", "feasibility", "pass-fail-criteria", "contingency-plan", "atomic-specification", "task-sequencing"]
- Last observed: Feature 018
- Observation count: 1

### Shared Error Utility Section for Multi-Route UI Features
For FastAPI+Jinja2 features with 2+ sibling route modules, include a "Shared Error Utilities" design section naming any common error-response helpers with their module path. This prevents DRY violations from reaching implement review.
- Source: Feature 020, implement iter 1 — board.py duplicated missing-DB error block that entities.py had extracted; fix required creating helpers.py, updating imports in 2 files, correcting 6 test assertions
- Confidence: high
- Keywords: ["shared-utilities", "design-section", "multi-route", "error-helpers", "dry-prevention", "fastapi", "jinja2"]
- Last observed: Feature 020
- Observation count: 1

### 8-10:1 Test-to-Code Ratio for Visualization Integration Features
For features integrating third-party visualization libraries (Mermaid, D3, Chart.js) into existing web UIs, expect an 8-10:1 test-to-code ratio (test lines vs production lines). The production code is thin (glue between library and data), but sanitization, edge cases, and integration points each require dedicated test coverage.
- Source: Feature 021, 727 test lines / 85 production lines = 8.5:1 ratio for Mermaid DAG integration
- Confidence: medium
- Keywords: ["test-ratio", "visualization", "mermaid", "integration", "thin-glue-code", "test-coverage"]
- Last observed: Feature 021
- Observation count: 1

### Mermaid Integration Checklist
When integrating Mermaid.js into a web application, verify these items at design time: (1) securityLevel must be 'loose' for click handlers to work, (2) Jinja2 `| safe` filter required to prevent arrow escaping, (3) _sanitize_label must escape `<`, `>`, `"`, `[`, `]`, `\` for node labels, (4) click handler URLs need URL-encoded special characters (especially `"`→`%22`), (5) ESM module import with startOnLoad handles rendering lifecycle.
- Source: Feature 021, accumulated across specify/design/plan/implement phases — each item discovered at a different phase
- Confidence: high
- Keywords: ["mermaid", "securityLevel", "jinja2-safe", "sanitize-label", "click-handler", "url-encoding", "esm-module", "checklist"]
- Last observed: Feature 021
- Observation count: 1

### User-Safe Error Constants Required at Design Time for Web UI Features
Require user-safe message constants for all error template variables in web UI designs. Design-reviewer prompt should include: "Verify all error template variables use user-safe constants (not str(exc), exception.args, or raw traceback content)."
- Source: Feature 020, implement iter 1 — security reviewer surfaced raw exception message str(exc) rendered in error.html, exposing internal details at two call sites
- Confidence: high
- Keywords: ["error-constants", "user-safe-message", "design-review", "security-check", "template-variables", "web-ui", "data-exposure"]
- Last observed: Feature 020
- Observation count: 1

### Task-Reviewer Blocker Counts for Entity Registry Extensions
For features extending MCP servers with entity registry integration, budget 3-4 task-review iterations. Entity_id conventions, mock shapes, and dependency chains are recurring blocker categories that decrease monotonically (specificity cascade). Phase-reviewer typically approves first pass after task-reviewer convergence.
- Source: Feature 034, create-tasks — 4 iterations with 6→4→3→0 blocker counts. Phase-reviewer approved first pass.
- Confidence: medium
- Keywords: ["task-review", "entity-registry", "mcp-extension", "specificity-cascade", "blocker-budget"]
- Last observed: Feature 034
- Observation count: 1

### PreToolUse Deny Hook for Write Protection Is Fast and Reliable
A bash PreToolUse hook using string matching (~12ms) is sufficient for protecting files from LLM writes. JSONL instrumentation logging adds negligible overhead. This is the correct enforcement pattern for 'no direct writes to X' invariants — replaces non-deterministic LLM writes with deterministic MCP tool code plus defense-in-depth hook.
- Source: Feature 034, meta-json-guard.sh — 9 hook tests, ~12ms latency (well under 50ms NFR-3). Replaces 9 LLM-driven write sites with MCP tool calls + hook enforcement.
- Confidence: high
- Keywords: ["pretooluse-hook", "write-protection", "bash-hook", "string-matching", "latency", "enforcement"]
- Last observed: Feature 034
- Observation count: 1
