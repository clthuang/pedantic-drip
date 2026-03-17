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

### Anti-Pattern: Approximate Call-Site Counts in Migration Plans
Plans that reference specific line numbers or approximate call-site counts (e.g., "14 assigning sites at lines 605, 622, 640...") become stale by implementation time as prior task commits shift line numbers. Implementers either waste time reconciling stale references or risk missing call sites.
- Observed in: Feature 010, create-plan phase — plan listed 14 call sites by line number; chainReview iter 5 flagged "line numbers are static approximations — engineer should run pre-commit grep at START of 4.2 to get current line numbers"
- Cost: create-plan hit cap (5+5 iterations) partly due to line number precision debates; chainReview note became required implementation guidance
- Instead: Plans should specify grep patterns or AST queries to locate call sites dynamically at implementation time, not static line numbers
- Confidence: medium
- Last observed: Feature 010
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

### Anti-Pattern: Assuming FTS5 Availability via SQL Function Call
Testing FTS5 availability by calling `SELECT fts5()` — FTS5 is a loadable module, not a callable SQL function. The correct approach is to attempt CREATE VIRTUAL TABLE with FTS5 and catch the error, or check `PRAGMA compile_options` for ENABLE_FTS5.
- Observed in: Feature 012, design iter 2 — FTS5 availability check via `SELECT fts5()` flagged as invalid; resolved by CREATE error catching
- Cost: 1 design review iteration on a factual SQLite error
- Instead: Test FTS5 availability by attempting to create a temporary FTS5 table and catching OperationalError
- Confidence: high
- Last observed: Feature 012
- Observation count: 1

### Anti-Pattern: Truthy Check for Optional String Fields in FTS Sync
Using `name or old_name` (truthiness) instead of `name if name is not None else old_name` (identity check) for optional string fields in FTS sync logic. Empty strings are valid values that should be synced to FTS; truthiness check treats them as absent, causing FTS drift.
- Observed in: Feature 012, design iter 3 — I4 Step 4 used `name or old_name` which would skip empty-string values; resolved by switching to identity check pattern
- Cost: 1 design review iteration; would have caused silent FTS drift for empty-string fields
- Instead: Use `field if field is not None else old_field` for all optional parameters in FTS sync
- Confidence: high
- Last observed: Feature 012
- Observation count: 1

### Anti-Pattern: Type Annotation Branch Cascade
Adding type annotations to individual branches of an if/else statement instead of at the variable declaration site. Each fix triggers the next reviewer iteration: add annotation to if-branch → reviewer flags missing else-branch → add to both → reviewer flags redundant double annotation → remove else-branch. Three iterations with zero logic changes.
- Observed in: Feature 011, implement phase — iters 2-4 consumed by type annotation formatting with zero logic changes
- Cost: 3 wasted review iterations on non-functional formatting
- Instead: Annotate at the variable declaration site before the conditional, not at each branch
- Confidence: high
- Keywords: ["type-annotation", "branch-cascade", "review-waste", "formatting", "python"]
- Last observed: Feature 011
- Observation count: 1

### Anti-Pattern: Partial Accepted-Delta Annotation Requiring Iterative Narrowing
Annotating a spec-design divergence as "accepted delta" without specifying the full error surface (canonical format string, prefix chain, concrete test assertion example) causes the handoff reviewer to extract each sub-component in separate iterations, consuming the iteration cap on a single concern.
- Observed in: Feature 013, design handoff — 5 iterations all addressing the same error-message format delta
- Cost: 4 of 5 handoff iterations consumed by a concern whose full resolution was knowable from iter 2's fix
- Instead: Complete the accepted-delta annotation in one atomic write with: (1) exact canonical format string, (2) any prefix the helper layer adds, (3) one concrete test assertion example
- Confidence: high
- Keywords: ["accepted-delta", "error-format", "handoff-reviewer", "incomplete-annotation", "iteration-cap"]
- Last observed: Feature 013
- Observation count: 1

### Anti-Pattern: Running Debug Hook Copy From /tmp Instead of Hook Directory
Placing a debug copy of a bash hook in /tmp causes SCRIPT_DIR to resolve to /tmp, making PYTHONPATH point to /tmp/lib (nonexistent). Engine imports fail silently, fallback runs with empty stderr, giving a false-positive pass on the primary path.
- Observed in: Feature 014, create-tasks chain review iter 4
- Cost: 1 chain review blocker; would have caused undetected false-positive verification
- Instead: Place debug copy in the same directory as the original hook so SCRIPT_DIR resolves correctly. Delete after verification.
- Confidence: high
- Keywords: ["hook-debug", "script-dir", "pythonpath", "tmp-directory", "false-positive", "bash-hook"]
- Last observed: Feature 014
- Observation count: 1

### Anti-Pattern: Restoring Modified Hook Files With git checkout During Verification
Using `git checkout <hook-file>` to restore after instrumented testing destroys uncommitted migration changes on a feature branch.
- Observed in: Feature 014, create-tasks chain review iter 3
- Cost: 1 chain review blocker; would have destroyed the feature's implementation
- Instead: Create a debug copy via `cp + sed`, run verification against the copy, then delete it. Never modify committed hook files in-place during verification.
- Confidence: high
- Keywords: ["git-checkout", "restore", "hook-testing", "migration", "uncommitted-changes", "destructive"]
- Last observed: Feature 014
- Observation count: 1

### Anti-Pattern: Serial Single-Issue Implement Review Iterations on Markdown Files
Quality reviewer finds exactly one readability issue per iteration on markdown command files, each fix exposing an adjacent concern. Pattern: iter 1 stale text, iter 2 enum mismatch, iter 3 scope description, iter 4 missing formatting — all independent issues discoverable by holistic pre-flight read. This always terminates at the circuit breaker (5 iterations) with no logic or correctness issues resolved.
- Observed in: Feature 015, implement run 1 iters 1-4 — four consecutive single-issue warnings on show-status.md and list-features.md, circuit breaker at iter 5
- Cost: 5 wasted review iterations + circuit breaker trigger + fresh run required
- Instead: Mandate holistic pre-flight sweep — read all changed files end-to-end before flagging any individual issue on markdown command migrations.
- Confidence: high
- Keywords: ["serial-review", "single-issue", "markdown-migration", "circuit-breaker", "quality-reviewer", "holistic-sweep"]
- Last observed: Feature 015
- Observation count: 1

### Anti-Pattern: Plan Edit Descriptions Without Exact Old/New Text Pairs Propagate as Task-Review Blockers
When plan.md edit steps describe changes in prose ("update Section 1.5 to include...") instead of quoting exact old/new text, the ambiguity propagates to task-review as blockers: task too large (combines unclear edits), missing explicit instructions, subjective acceptance criteria. Plan-review cap warnings about ambiguity directly cause 1-2 extra task-review iterations.
- Observed in: Feature 015, plan-review cap warning about step 1.4 ambiguity → task review iter 1 surfaced 5 issues rooted in the same precision gaps
- Cost: 2 unresolved plan warnings → 2 extra task-review iterations (5 issues in iter 1)
- Instead: Require every plan edit step to include quoted old/new text pairs for markdown files.
- Confidence: high
- Keywords: ["plan-ambiguity", "edit-descriptions", "old-new-pairs", "task-review-blockers", "downstream-propagation"]
- Last observed: Feature 015
- Observation count: 1

### Anti-Pattern: Building Component Maps From Planned Scope Not Grep Results
When a design component map is built from the initially planned scope (e.g., "7 target files") instead of running a broad grep first, stale references outside that list are discovered only during review iterations. In feature 017, the target file list grew from 7 to 10 files across 3 design iterations.
- Observed in: Feature 017, design phase — 3 files outside initial 7 targets contained stale references (hookify.docs-sync.local.md, command-template.md, patterns.md), discovered across 3 design review iterations
- Cost: 3 extra design review iterations to expand scope from 7 to 10 files
- Instead: Run broad-scope grep before drafting the component map to capture all affected files on first pass.
- Confidence: high
- Keywords: ["component-map", "scope-discovery", "grep-first", "design-review", "stale-references"]
- Last observed: Feature 017
- Observation count: 1

### Anti-Pattern: Referencing MCP Response Shapes By Field Name Only
When specs reference MCP tool response shapes by field name only (e.g., "use the current_phase field") without documenting the full JSON structure including null variants, downstream phases hit blockers when encountering unexpected null values. Feature 017 needed 2 spec iterations for get_phase JSON response shape.
- Observed in: Feature 017, specify phase — 2 iterations needed for get_phase JSON response shape including null current_phase handling
- Cost: 2 extra spec review iterations
- Instead: Document full MCP tool response shapes (including null variants) inline in the spec.
- Confidence: high
- Keywords: ["mcp-response", "json-shape", "null-handling", "spec-precision", "field-reference"]
- Last observed: Feature 017
- Observation count: 1

### Anti-Pattern: Specifying Smoke Tests With Unverified CLI Flags
When smoke test specifications assume CLI flags exist without verifying against the actual interface, the test goes through multiple revision cycles. In feature 017, a --feature flag was assumed to exist but didn't, causing 4 revision cycles for the smoke test specification.
- Observed in: Feature 017, create-tasks phase — --feature flag assumed to exist but was nonexistent, causing 4 revision cycles
- Cost: 4 revision cycles for smoke test specification
- Instead: Verify smoke test command syntax against actual CLI interface during spec authoring.
- Confidence: high
- Keywords: ["smoke-test", "cli-flags", "unverified-assumptions", "test-specification", "revision-cycles"]
- Last observed: Feature 017
- Observation count: 1

### Anti-Pattern: Spec Dependency Claims Without Venv Verification
Writing spec statements like "Jinja2 already available in venv" or referencing CDN URLs without verifying against actual project files. These false-certainty claims propagate as design-phase blockers and require explicit correction sections in subsequent artifacts.
- Observed in: Feature 018, design iter 1 — two blockers both from unverified spec claims: Jinja2 not in venv (spec line 112 "already available"), CDN URL wrong (cdn.tailwindcss.com vs @tailwindcss/browser@4); required "Spec inaccuracies addressed by this design" section and a plan correction task
- Cost: 2+ design iterations; required explicit spec-correction section in design.md and a correction task in plan
- Instead: For each external library listed as "available," verify presence in plugins/iflow/.venv/lib. For each CDN URL, verify against an existing sibling file. Annotate "verified against: <file>:<line>".
- Confidence: high
- Keywords: ["spec-accuracy", "venv-verification", "cdn-url", "dependency-claims", "false-certainty", "design-blockers"]
- Last observed: Feature 018
- Observation count: 1

### Anti-Pattern: Switching Install Command Without Auditing Dependency Manifest
Changing a bootstrap wrapper from `uv pip install <list>` to `uv sync --no-dev` without immediately auditing pyproject.toml [project] dependencies. The hand-maintained install list and the manifest can silently diverge, with the gap only discovered at runtime execution — potentially several review iterations after the change.
- Observed in: Feature 018, implement iters 1 and 4 — quality reviewer improved install step at iter 1; uvicorn absent from [project] deps; caught only at iter 4 final validation when uv sync --no-dev was actually executed
- Cost: 1 extra implement review iteration; blocked final validation requiring a pyproject.toml + uv lock fix
- Instead: When switching from uv pip install to uv sync --no-dev, immediately compare the hand-maintained package list against pyproject.toml [project] deps and reconcile before declaring the task done.
- Confidence: high
- Keywords: ["uv-sync", "install-command", "manifest-audit", "bootstrap-wrapper", "runtime-gap", "pyproject-toml"]
- Last observed: Feature 018
- Observation count: 1

### Anti-Pattern: Sibling Route Modules Without Named Shared Error Utility at Design Time
Designing sibling route modules (e.g., board.py and entities.py) without naming shared error-response helpers at design time. The DRY violation only surfaces at implement review, requiring creation of a helpers.py module, import updates in 2 files, and correction of 6 test assertions.
- Observed in: Feature 020, implement iter 1 — quality reviewer caught board.py duplicating the missing-DB error block that entities.py had extracted into _missing_db_response()
- Cost: Extra implement review iteration; required creating helpers.py, updating imports in 2 files, correcting 6 test assertions
- Instead: When a design covers 2+ sibling route modules, include a "Shared Utilities" subsection naming any common error-response helpers with their module path.
- Confidence: high
- Keywords: ["dry-violation", "sibling-routes", "shared-helpers", "design-gap", "error-response", "fastapi", "route-modules"]
- Last observed: Feature 020
- Observation count: 1

### Anti-Pattern: Incremental Sanitization Strategy Changes Across Phases
Changing sanitization encoding rules incrementally across review iterations in different phases (e.g., `&`→`&amp;` in plan iter 1, then `<`/`>` escaping in iter 2, then bare `&` with deferred verification in iter 3). Each change requires cross-artifact updates and risks introducing double-encoding or inconsistency. Instead, enumerate the full sanitization strategy at design time with a lookup table of all characters requiring escaping and their target encodings.
- Observed in: Feature 021, _sanitize_label encoding changed 3 times across plan-reviewer iterations — ampersand, angle brackets, then bare ampersand
- Cost: 3 plan-reviewer iterations, cross-artifact updates to spec + design + plan each time
- Instead: Define complete sanitization table at design time. Research the rendering library's escaping behavior (DOM textContent vs innerHTML) before choosing encoding strategy.
- Confidence: high
- Keywords: ["sanitization", "encoding", "double-encoding", "cross-phase-changes", "mermaid", "html-escaping", "incremental-strategy"]
- Last observed: Feature 021
- Observation count: 1

### Anti-Pattern: Raw Exception Content as HTML Error Template Variables
Passing raw exception content (str(exc)) as template variables to HTML error pages, exposing internal details (file paths, SQL queries, stack traces) to end users. This is a web UI security class not caught at design time.
- Observed in: Feature 020, implement iter 1 — security reviewer surfaced raw exception rendering in error.html at two call sites
- Cost: Required creating DB_ERROR_USER_MESSAGE constant, updating 2 error handlers, correcting 6 test assertions
- Instead: Always use user-safe message constants for all error template variables in web UI designs. Keep detailed error in stderr log only.
- Confidence: high
- Keywords: ["raw-exception", "html-template", "data-exposure", "error-message", "security", "str-exc", "jinja2", "web-ui"]
- Last observed: Feature 020
- Observation count: 1

### Anti-Pattern: Design Pseudocode With Wrong Access Pattern for Existing API
Writing design pseudocode that uses attribute-style access (entity.metadata) when the actual API returns dicts (entity['metadata']) forces plan-level overrides and creates a spec-design divergence that must be resolved during implementation.
- Observed in: Feature 034, design phase — pseudocode used attribute-style access; plan overrode to dict-style access for entity metadata
- Cost: Plan-level override required; caught at plan phase, not design review
- Instead: Design-reviewer should verify access patterns against the actual API return type before approving pseudocode
- Confidence: medium
- Keywords: ["pseudocode", "access-pattern", "dict-vs-attribute", "entity-registry", "design-accuracy"]
- Last observed: Feature 034
- Observation count: 1

### Anti-Pattern: Passing Design Through Review Without Enumerating Database Row States
Not explicitly enumerating all possible database row states (no row, null fields, populated fields) for each DB-touching component. Missing states surface later as plan-reviewer blockers or implementation bugs.
- Observed in: Feature 035, design phase — design.md C6 initially missed the null-phase UPDATE case for backfill. Discovered during plan creation, requiring retroactive design fix (commit 9db4135).
- Cost: Retroactive design fix + extra plan iteration
- Instead: For any component touching DB tables, design-reviewer should require enumeration of all row states with handling logic for each
- Confidence: medium
- Keywords: ["database-state-enumeration", "design-completeness", "backfill", "null-handling", "row-states"]
- Last observed: Feature 035
- Observation count: 1

### Anti-Pattern: Defining Migration Bundle Schema as Prose Without Complete JSON Example
Describing a manifest/bundle structure in prose without a complete worked JSON example causes structural ambiguities (flat vs nested, array vs object) to survive to implementation review as blockers.
- Observed in: Feature 037, implement review — manifest structure mismatch (flat checksums+counts vs per-file files dict) found as a blocker
- Cost: Full manifest restructure across 7 files mid-implementation
- Instead: Include at least one complete JSON example with all fields at correct nesting in the design
- Confidence: high
- Keywords: ["manifest-schema", "migration-bundle", "json-example", "serialization-design", "design-completeness"]
- Last observed: Feature 037
- Observation count: 1

### Anti-Pattern: Dynamic SQL Construction Without Design-Time Injection Surface Enumeration
When design selects ATTACH DATABASE or SQL-level merge patterns, failing to enumerate injectable parameters and escaping strategy leaves SQL injection for implementation reviewers to find.
- Observed in: Feature 037, implement review — SQL injection in entity merge Phase 4 using f-string interpolation in WHERE IN clause
- Cost: Blocker requiring parameterized query rewrite + regression testing
- Instead: Design TD for SQL merge must list all injectable parameters with escaping strategy
- Confidence: high
- Keywords: ["sql-injection", "dynamic-sql", "attach-database", "security-surface", "design-review", "migration-tool"]
- Last observed: Feature 037
- Observation count: 1

### Anti-Pattern: Per-Consumer Dependency Subsets for a Shared Resource
Defining per-consumer dependency subsets for a shared resource (venv, DB schema, cache) instead of a single canonical dependency list. Whichever consumer bootstraps the resource first installs only its subset; subsequent consumers find the resource in a partial state and fail at import/access time.
- Observed in: Feature 039, prd.md RC-2 — entity-server and workflow-server installed only `mcp`; memory-server required `numpy` and `dotenv`; whichever ran first left an incomplete venv
- Cost: All MCP servers non-functional on fresh marketplace installs; required architectural refactor
- Instead: Define a single canonical dependency list at the shared resource level serving all consumers
- Confidence: high
- Keywords: ["shared-resource", "dependency-subset", "bootstrap", "venv", "canonical-list", "partial-state"]
- Last observed: Feature 039
- Observation count: 1
