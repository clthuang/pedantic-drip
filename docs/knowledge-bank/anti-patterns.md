# Anti-Patterns

Things to avoid. Updated through retrospectives.

---

## Known Anti-Patterns

### Anti-Pattern: Working in Wrong Worktree
Making changes in main worktree when a feature worktree exists.
- Observed in: Feature #002
- Cost: Had to stash, move changes, re-apply in correct worktree
- Instead: Check `git worktree list` at session start; work in feature worktree if one exists
- Last observed: Feature #33
- Observation count: 1

### Anti-Pattern: Over-Granular Tasks
Breaking a single file modification into many small separate tasks.
- Observed in: Feature #003
- Cost: Initial 31 tasks had to be consolidated to 18 during verification
- Example: 4 tasks for one skill file (create structure, add sequence, add validation, add patterns)
- Instead: One task per logical unit of work (one file = one task, or one component = one task)
- Last observed: Feature #33
- Observation count: 1

### Anti-Pattern: Relative Paths in Hooks
Using `find .` or relative paths in hooks for project file discovery.
- Observed in: Plugin cache staleness bug
- Cost: Missed test files when Claude ran from subdirectories; stale feature metadata
- Root cause: `find .` searches from PWD; `PLUGIN_ROOT` points to cached copy
- Instead: Use `detect_project_root()` from shared library, search from `PROJECT_ROOT`
- Last observed: Feature #33
- Observation count: 1

### Anti-Pattern: Skipping Workflow for "Simple" Tasks
Rationalizing that a task is "just mechanical" to justify skipping workflow phases.
- Observed in: Feature #008
- Cost: Had to retroactively create feature; missed the brainstorm → feature promotion checkpoint
- Root cause: Task felt simple (search-and-replace), so jumped from option selection to implementation
- Instead: Brainstorm phase ends with "Turn this into a feature?" - always ask, let user decide to skip
- Last observed: Feature #33
- Observation count: 1

### Anti-Pattern: Line Number References in Sequential Tasks
Referencing specific line numbers in tasks that will shift after earlier task insertions.
- Observed in: Feature #018
- Cost: Tasks 4.2-4.4 line numbers shifted ~60 lines after Task 4.1 insertion, causing confusion
- Root cause: Line numbers are brittle anchors when tasks modify the same file sequentially
- Instead: Use semantic anchors (exact text search targets) that survive insertions
- Last observed: Feature #025
- Observation count: 3

### Anti-Pattern: Frozen Artifact Contradictions
Leaving PRD claims that contradict later spec/design resolutions without noting the divergence.
- Observed in: Feature #018
- Cost: Implementation reviewer flagged PRD FR-9 (MCP tool) vs actual implementation (inline Mermaid) as a "blocker"
- Root cause: PRD is frozen brainstorm artifact but readers don't know which claims were superseded
- Instead: Add Design Divergences table in plan.md documenting PRD/spec/design deviations with rationale
- Last observed: Feature #33
- Observation count: 2

### Anti-Pattern: Dual-Representation Dependency Graphs
Maintaining dependency information in both ASCII art and textual description invites contradictions.
- Observed in: Feature #021
- Cost: Plan dependency graph redrawn 3+ times across 6 iterations to fix graph-vs-text mismatches
- Root cause: Two representations of the same data with no single source of truth
- Instead: Use mermaid for dependency graphs (serves both visual and textual roles) or maintain only one representation
- Last observed: Feature #33
- Observation count: 1

### Anti-Pattern: Bash Variable Interpolation in Inline Python
Using `${VARIABLE}` inside Python strings embedded in bash scripts enables injection.
- Observed in: Feature #021
- Cost: Security reviewer flagged session-start.sh line 169 using `${PROJECT_ROOT}` in Python glob
- Root cause: Bash expands variables before Python sees the string; special characters in paths could break or inject
- Instead: Pass external values via `sys.argv` or environment variables; never string interpolation
- Last observed: Feature #33
- Observation count: 2

### Anti-Pattern: Parser Against Assumed Format
Designing parsers against assumed format without verifying against actual files. Writing regex patterns or format specifications based on what the format "should be" rather than reading actual files to confirm.
- Observed in: Feature #022, design phase iteration 3
- Cost: Design circuit breaker hit (5 iterations); task parser regex was checkbox-based but actual tasks.md uses heading-based format
- Instead: Read actual target files before writing parsers; add "verified against: <file path>" annotation to design documents
- Last observed: Feature #029
- Observation count: 3

### Anti-Pattern: Post-Approval Informational Iterations
Continuing review iterations after approval when all remaining issues are informational ("no change needed"). Adds wall-clock time without producing artifact changes.
- Observed in: Feature #022, create-plan phase
- Cost: Plan review iterations 4-5 after iter 3 approval produced zero changes, adding ~30 min
- Instead: Implement early-exit when reviewer approves with zero actionable issues
- Last observed: Feature #33
- Observation count: 1

### Anti-Pattern: Spec-Level Numeric Divergence Deferred to Implementation
When a numeric mismatch between spec and design (counts, caps, limits) is flagged during design review but resolved with a "spec should be updated during implementation" note rather than an immediate cross-artifact fix, the divergence propagates to handoff review and plan review before being resolved. Each propagation consumes a full review iteration from each downstream reviewer.
- Observed in: Feature #028, design iter 4 through handoff iter 1 — scaffold dispatch cap (spec=4, design=5) survived 3+ review iterations with a deferred note before handoff reviewer forced immediate spec.md edit
- Cost: 2 extra review iterations (one handoff, traceable plan iteration) from a fix that took one edit
- Instead: Numeric spec-design mismatches must be fixed immediately — edit spec.md in the same review response that identifies the mismatch
- Confidence: high
- Last observed: Feature #028
- Observation count: 1

<!-- Example format:
### Anti-Pattern: Premature Optimization
Optimizing before measuring actual performance.
- Observed in: Feature #35
- Cost: 2 days wasted on unnecessary caching
- Instead: Measure first, optimize bottlenecks only
-->

### Anti-Pattern: Specifying a Parser Without a Complete Round-Trip Example
When design describes a parser (fields extracted, splitting logic, metadata structure) but does not include a fully worked example showing input text and resulting data structure with ALL fields populated, downstream phases repeatedly discover missing fields or format gaps, causing cascading review iterations.
- Observed in: Feature #023, design through create-tasks phases
- Cost: 3+ extra review iterations across 3 phases as format was refined piecemeal
- Instead: Include at least one complete input→output example with all parser fields in the design
- Confidence: high
- Last observed: Feature #33
- Observation count: 1

### Anti-Pattern: Implementation Reviewer Flagging Pre-Existing Code as Blockers
When the quality reviewer flags code quality issues on lines not introduced by the current feature (e.g., a bare except clause in a function written months ago), it wastes review iterations on rebuttals and creates noise that obscures genuine issues in the new code.
- Observed in: Feature #023, implement phase
- Cost: 2 wasted review iterations (iterations 3-4 produced zero code changes)
- Instead: Reviewer should check git diff to verify flagged code is from the current feature before classifying as blocker
- Confidence: high
- Last observed: Feature #33
- Observation count: 1

### Anti-Pattern: Over-Documentation Before System Maturity
Adding behavioral guidance for features/behaviors not yet consistently observed in practice. Documentation should trail patterns by at least one reinforcement cycle (observed in 2+ features).
- Observed in: CLAUDE.md template analysis — most template items were aspirational rather than proven
- Cost: False authority and wasted reader attention on unproven patterns
- Instead: Wait for observational evidence from 1+ cycles before documenting as standard guidance
- Confidence: medium
- Last observed: 2026-02-22
- Observation count: 1

### Anti-Pattern: Classifying Absent Content Without Full-Artifact Verification
Asserting that a required element is missing without verifying its absence in the full artifact. Summarized reviewer inputs mask content that exists in the full document, producing false-positive blockers that waste a full review iteration.
- Observed in: Feature #026 — design iter 1 (3 false-positive blockers), task review iter 1 (2), chain review iter 3 (1)
- Cost: 6 wasted blocker rebuttals across 3 phases
- Instead: Before classifying an element as absent, verify it is genuinely not present in the full artifact
- Confidence: high
- Last observed: Feature #028
- Observation count: 2

### Anti-Pattern: Flagging Annotated Spec Deviations as Implementation Failures
When a spec-design deviation is annotated in the design document (TD-* entry) and acknowledged in the spec, treating it as a spec failure during implementation review wastes a circuit-breaker slot on a non-fixable issue.
- Observed in: Feature #026, implement iter 5 — AC-5 vs TD-5 flagged as spec failure despite annotation in design.md
- Cost: Consumed final circuit-breaker iteration on a non-resolvable issue
- Instead: Check for deviation annotations before flagging spec mismatches as blockers
- Confidence: high
- Last observed: 2026-02-22
- Observation count: 1

### Anti-Pattern: Open-Ended Security Review Without a Threat Model
Conducting security review on a path extraction subsystem without first defining a threat model. Each fix closes one attack path and reveals the next, producing escalating iterations rather than convergence.
- Observed in: Feature #026, implement iters 3-5 — path validation hardened 3 times without converging
- Cost: 3 iterations of security review; circuit breaker reached without resolution
- Instead: Require a Security Threat Model subsection in design defining allowed path forms, rejected patterns, and acceptable residual risks
- Confidence: medium
- Last observed: 2026-02-22
- Observation count: 1

### Anti-Pattern: Describing Algorithms Without Specifying Concrete I/O and Edge Cases
Mentioning an algorithm by name (e.g., "Accept-some merge") without documenting step-by-step inputs, outputs, and edge cases causes blockers in downstream phases as each consumer interprets the gap differently.
- Observed in: Feature #027, design iter 1 blocker ("Accept-some partial merge algorithm unspecified") + tasks iter 2 (4 blockers: content unspecified, CHANGE scope unclear, merge algorithm undocumented, extraction target unspecified)
- Cost: Same underspecification caused blockers in two separate phases
- Instead: For every algorithm described, document: all inputs, all outputs, error/edge cases, write targets
- Confidence: high
- Last observed: Feature #027
- Observation count: 1

### Anti-Pattern: Hardcoding Year Values in Search Queries
Embedding literal year values (e.g., "2026") in search queries or date-sensitive prompts causes silent degradation as time passes — no error signal, just less relevant results.
- Observed in: Feature #027, implementation iter 2 — quality reviewer flagged hardcoded year in refresh-prompt-guidelines.md search queries
- Cost: Silently stale results with no visible error
- Instead: Use dynamic placeholders like {current year} with instructions to resolve at runtime
- Confidence: high
- Last observed: Feature #027
- Observation count: 1

### Anti-Pattern: Two-Layer Architecture Without AC Traceability
Implementing a storage layer and a rendering/presentation layer for the same spec ACs without an explicit traceability map. The storage layer satisfies the data model; the rendering layer silently omits required fields. Gap is invisible until end-to-end output testing.
- Observed in: Feature #029, implement iter 2 — AC-5 depends_on_features stored in DB but _format_entity_label ignored metadata
- Cost: Blocker at implementation iter 2; required 7 new tests
- Instead: For separated storage+rendering layers, map each AC to both the storage AND rendering functions
- Confidence: high
- Last observed: Feature #029
- Observation count: 1

### Anti-Pattern: Python-Side Recursion Against Relational DB for Tree Traversal
Using Python-side recursion (or N+1 queries) for tree traversal when the backing store is SQL. Produces O(N^2) or O(N) round-trip patterns and has no natural depth limit.
- Observed in: Feature #029, implement iters 1+3 — N+1 export recursion and O(N^2) set comprehension in render_tree
- Cost: Security and quality warnings requiring 2 fix iterations
- Instead: Use recursive CTEs with max_depth guard; do all tree work in SQL
- Confidence: high
- Last observed: Feature #029
- Observation count: 1

### Anti-Pattern: Dispatching Reviewers with Compressed Artifacts
When large artifacts (>200 lines) are compressed by prompt compression before reaching a reviewer agent, the reviewer receives summaries instead of full content, producing false-positive blockers. Feature #030 had 2 full review iterations consumed and 8 false-positive blockers total across create-plan and create-tasks phases.
- Observed in: Feature #030, create-plan chain iter 1 + create-tasks iter 2
- Cost: 2 full review iterations wasted on false positives
- Instead: Pre-declare artifact completeness with line-count headers; add reviewer instruction to flag truncated artifacts as process errors
- Confidence: high
- Last observed: Feature #030
- Observation count: 1

### Anti-Pattern: Reviewer Output Format as Plain Prose Instead of JSON Schema
Specifying reviewer return format as plain prose ("Return assessment with approval status") instead of an explicit JSON schema block. Caught late in implement review rather than design phase, doubling correction cost per iteration.
- Observed in: Feature #030, implement iters 1–2 — code-quality-reviewer (7b) and security-reviewer (7c) both had prose return format
- Cost: 2 additional implement review iterations
- Instead: All reviewer dispatch prompts must include explicit JSON return schema with approved/issues/summary structure
- Confidence: high
- Last observed: Feature #030
- Observation count: 1

### Anti-Pattern: Design Label References Without Inline Reproduction
Referencing design templates by label name (e.g., "I1 template", "I8 format") in plan/tasks documents without reproducing the template content inline. Forces cross-document lookup and blocks reviewers who cannot verify completeness.
- Observed in: Feature #030, plan iter 1 + task iters 2–4 — I1, I8, I9 templates and {feature_path} not reproduced
- Cost: 3 consecutive task-review iterations addressing same root cause; cap reached
- Instead: Reproduce all cross-task templates verbatim in a Shared Templates section
- Confidence: high
- Last observed: Feature #030
- Observation count: 1

### Anti-Pattern: Curly-Brace Placeholders in Code-Fenced Shell Commands
Using curly-brace template placeholders ({variable}) inside code-fenced shell commands in task descriptions. These are not executable and produce vacuous grep matches or shell errors.
- Observed in: Feature #031, create-tasks phase — '{actual_headers}' placeholder caused blocker in chain review iter 1 and persisted through iter 4; '{phase}' placeholder caused blocker in task review iter 5
- Cost: Combined, these two placeholders drove 4+ review iterations across both stages
- Instead: Use concrete examples with prose substitution instructions, or mark explicitly as "substitute before executing"
- Confidence: high
- Last observed: Feature #031
- Observation count: 1

### Anti-Pattern: Self-Attestation Verification in Acceptance Criteria
Using self-attestation verification methods ('mark each checked', 'trace and confirm') in task acceptance criteria. Reviewers correctly reject these as unverifiable, but replacements (label-dependent grep) can be equally weak.
- Observed in: Feature #031, create-tasks phase — Task 12 iterated from self-attestation (iter 4) to grep verification (iter 5) to label-dependent grep (chain iter 5 cap)
- Cost: Verification weakness never fully resolved before circuit breaker
- Instead: Explicitly mark criteria requiring human judgment as 'manual verification' rather than disguising as automatable checks
- Confidence: high
- Last observed: Feature #031
- Observation count: 1

### Anti-Pattern: Same Variable Name for Skill and Command File References
Using the same variable name (e.g., `original_content`) in both a skill and its orchestrating command with different referents. Causes naming collision blockers in plan review when both contexts are active simultaneously.
- Observed in: Feature #032, create-plan phase — design used `original_content` in skill Step 2c (raw file content) and command Step 2.5 (post-parse content); one rename resolved it
- Cost: Plan review blocker consuming a full iteration
- Instead: Use distinct names that encode scope (e.g., `target_content` for skill, `original_content` for command)
- Confidence: high
- Last observed: Feature #032
- Observation count: 1

### Anti-Pattern: Task Invocation as Vague Procedure Without CLI Specification
Describing task invocation as 'run the pilot file' or 'invoke the command' without specifying the exact CLI, session type (CC interactive vs headless), and input sourcing. Drives 4-5 iteration specificity cascade as reviewers force progressive disclosure of: which binary, which flags, which session type, how to source input arguments.
- Observed in: Feature #033, create-tasks — T02 invocation mechanism iterated 5 times through pseudo-code → tool names → slash commands → claude -p flag assembly; 42% of all create-tasks concerns were invocation-mechanism issues
- Cost: Task review cap hit (5/5 iterations exhausted) without resolving T02
- Instead: Each task requiring CLI invocation must specify exact command, session type, and input sourcing at authoring time
- Confidence: high
- Last observed: Feature #033
- Observation count: 1

### Anti-Pattern: Planning Claude -p Tasks Without Environmental Constraint Modeling
Planning tasks that require `claude -p` or interactive CC sessions without explicitly modeling the nested-session constraint. These tasks are silently included in scope and surface as blocked only during implementation.
- Observed in: Feature #033, implement phase — 12/40 tasks (30%) blocked by CLAUDECODE env var preventing nested claude -p invocations; tasks T01, T11, T33-T40 all require fresh terminal session
- Cost: 30% implementation task block, incomplete pilot gate report, batch scoring deferred post-feature
- Instead: Tag `claude -p` dependent tasks at create-tasks time with [REQUIRES_FRESH_TERMINAL] and group them as a post-feature manual step
- Confidence: high
- Last observed: Feature #033
- Observation count: 1

### Anti-Pattern: Deferring SQLite Platform-Default Verification to Implement Review
Leaving SQLite FK ON DELETE defaults, CHECK constraint syntax, and WAL mode implications unverified at design time causes comment-level corrections (RESTRICT vs NO ACTION) to surface as security-reviewer blockers during implementation, consuming 2+ review iterations on a non-behavioral fix.
- Observed in: Feature #004, implement iters 2-3 — SQLite FK default NO ACTION vs RESTRICT unknown at design time; caught by security reviewer; drove 2 of 4 implement iterations
- Cost: 2 implement review iterations on a one-lookup platform fact
- Instead: Add a platform-default verification checklist to design-reviewer for database schema features
- Confidence: high
- Last observed: Feature #004
- Observation count: 1

### Anti-Pattern: Specifying Forward Transitions Without Addressing Backward Transitions
When a spec defines state-machine forward transitions without explicitly addressing backward transitions (even as an out-of-scope statement), plan reviewers treat the silence as an open gap and raise it as a blocker — two phases after the appropriate fix point.
- Observed in: Feature #004, create-plan phase — backward transition gap raised at plan review rather than specify; resolved with one sentence that should have been in the spec
- Cost: 1 plan-review iteration on a one-sentence scope clarification
- Instead: Spec-reviewer checklist should require explicit backward-transition coverage for any feature specifying state-machine transitions
- Confidence: medium
- Last observed: Feature #004
- Observation count: 1

### Anti-Pattern: Fixing a Structured-List Bug Without Verifying All Siblings
When an implement reviewer finds a field-ordering or formatting bug in one entry of a YAML/JSON array, fixing only the flagged entry without scanning all sibling entries for the same defect guarantees the bug recurs in the next review iteration. The same consolidation_notes field-ordering error (placed before duplicates/consolidation_target) recurred at G-14, G-15, and G-16 across three separate implement review iterations.
- Observed in: Feature 006, implement phase — G-14 fixed iter 1, G-15 same bug iter 2, G-16 same bug iter 4; full sibling verification only at iter 5 after exhausting 4 of 5 iterations
- Cost: 3 of 5 implement review iterations consumed by a structural defect fully knowable from the first fix
- Instead: When fixing a field-ordering bug in a structured list, sweep all entries in the same list for the same defect before declaring the fix complete
- Confidence: high
- Last observed: Feature 006
- Observation count: 1

### Anti-Pattern: Gradual Checkpoint Escalation Across Chain Review Iterations
When a plan-reviewer first flags an intermediate checkpoint as a "suggestion" in iteration 1 and the author treats it as optional, subsequent chain review iterations will escalate it progressively (suggestion to recommendation to required) until it becomes mandatory. Each escalation step consumes a full review iteration. The final enforcement level is knowable from the first flag.
- Observed in: Feature 006, create-plan chain review — scratch-note checkpoint escalated from suggestion (iter 1) to recommendation (iter 2) to intermediate checkpoint (iter 3) to mandatory required step (iter 4), consuming all 4 chain review iterations
- Cost: 3 wasted chain review iterations on a concern whose resolution was knowable from iter 1
- Instead: When a checkpoint concern is first raised in iter 1 (at any severity), immediately elevate it to a required plan step with explicit completion signal
- Confidence: high
- Last observed: Feature 006
- Observation count: 1

### Anti-Pattern: Assuming External Library Availability Without Venv Audit
Planning implementation steps that use external Python libraries (PyYAML, requests, etc.) without verifying they are present in the project venv. The plan compiles syntactically; the test fails at runtime with ModuleNotFoundError — silent until test execution.
- Observed in: Feature 007, create-plan iter 2 blocker — "PyYAML not in venv dependencies — YAML validation test would fail with ModuleNotFoundError"; resolved by redesigning to stdlib line-by-line string parsing
- Cost: 1 plan-review blocker; implementation approach redesign required in the same iteration
- Instead: Plan-reviewer must verify all non-stdlib imports against `plugins/iflow/.venv` installed packages before approving
- Confidence: high
- Keywords: ["python-dependency", "venv", "pyyaml", "stdlib", "dependency-audit", "plan-review"]
- Last observed: Feature 007
- Observation count: 1

### Anti-Pattern: str(Enum) for String Extraction Instead of .value
Using `str(SomeEnum.member)` to extract the string value of a Python Enum. `str()` output format varies by Python version and produces `EnumClass.member_name` format in some versions rather than the enum's `.value` string. `.value` is the portable, explicit, intention-revealing approach.
- Observed in: Feature 007, implement iter 1 blocker — "gate.py uses str(PHASE_SEQUENCE[i]) at lines 298, 319, 345 — Python-version-unsafe. Should use .value"; 3 fix sites required
- Cost: 1 implement blocker; 3 fix sites; correctable in tasks if specified
- Instead: Always use `enum_instance.value` for string extraction; `str(enum_instance)` is for display or debug output only
- Confidence: high
- Keywords: ["python-enum", "str-conversion", "portability", "enum-value", "python-version"]
- Last observed: Feature 007
- Observation count: 1

### Anti-Pattern: Applying TDD Reorder Fix Without Per-Phase Verification
When a TDD ordering fix claims "reordered all phases," verify each phase individually. Unverified global claims guarantee follow-up blockers. In feature 008, plan iter 1 fix stated "Reordered all phase sub-steps" but did not reorder Phase 1, which still scaffolded production files before tests — causing a second blocker in iter 2.
- Observed in: Feature 008, create-plan phase — TDD ordering blocker at iter 1 AND iter 2 (partial fix); iter 1 claimed global reorder but missed Phase 1
- Cost: 2 plan-review blockers; could have been 1 if per-phase verification was applied
- Instead: After any "reorder all" fix, enumerate and verify each phase/section individually before submitting
- Confidence: high
- Keywords: ["tdd-ordering", "per-phase-verification", "partial-fix", "global-claim", "plan-review"]
- Last observed: Feature 008
- Observation count: 1

### Anti-Pattern: Unspecified Exception Catch Scope in Race Condition Handlers
When design describes a race condition handler without specifying catch scope, implement reviewers will flip-flop between "too narrow" and "too broad." In feature 008, ValueError catch scope flip-flopped between implement iters 2 and 4 — iter 2 broadened the catch (remove string-match), iter 4 narrowed it (bare catch masks errors). Resolution required only a comment documenting pre-validation invariants.
- Observed in: Feature 008, implement phase — ValueError catch scope flip-flopped between iters 2 and 4; no design TD addressed catch scope
- Cost: 2 implement review iterations; flip-flop wasted both iterations
- Instead: Design Technical Decisions must specify exception types caught and pre-validation invariants that make the catch safe
- Confidence: medium
- Keywords: ["exception-catch-scope", "race-condition", "design-td", "valueerror", "flip-flop"]
- Last observed: Feature 008
- Observation count: 1
