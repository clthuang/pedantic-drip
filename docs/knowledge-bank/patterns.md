# Patterns

Approaches that have worked well. Updated through retrospectives.

---

## Development Patterns

### Pattern: Context7 for Configuration Verification
Use Context7 to look up Claude Code documentation before guessing configuration syntax.
- Used in: Feature #002
- Benefit: Discovered correct hooks auto-discovery path (plugin root, not .claude-plugin/)
- Avoided: Wrong fix that would have required later correction

### Pattern: Follow Skill Completion Guidance
Read skill completion messages for the correct next step instead of guessing.
- Used in: Feature #002
- Benefit: Skills define the workflow; following them ensures consistency
- Example: designing skill says "Run /create-plan" not "/create-tasks"

### Pattern: Coverage Matrix for Multi-Component Work
When modifying multiple similar components, create a coverage matrix early.
- Used in: Feature #003
- Benefit: Caught missing brainstorm and verify commands during task verification
- Example: Matrix showing Command × (Validation, Reviewer Loop, State Update)
- Instead of: Discovering gaps during implementation

### Pattern: Hardened Persona for Review Agents
Define explicit "MUST NOT" constraints for reviewer agents to prevent scope creep.
- Used in: Feature #003
- Benefit: Clear boundaries prevent reviewers from suggesting new features
- Mantra: "Is this artifact clear and complete FOR WHAT IT CLAIMS TO DO?"
- Key constraints: No new features, no nice-to-haves, no questioning product decisions

### Pattern: Chain Validation Principle
Each workflow phase output should be self-sufficient for the next phase.
- Used in: Feature #003
- Benefit: Clear reviewer context - what to validate and why
- Question: "Can next phase complete its work using ONLY this artifact?"
- Enables: Expectations table defining what each phase needs from previous

### Pattern: PROJECT_ROOT vs PLUGIN_ROOT in Hooks
Use PROJECT_ROOT for dynamic project state, PLUGIN_ROOT for static plugin assets.
- Discovered in: Plugin cache staleness bug fix
- Benefit: Prevents reading stale cached data when plugin files are copied
- Implementation: Shared `detect_project_root()` function in `hooks/lib/common.sh`
- Key insight: Claude's PWD may be a subdirectory, so walk up to find `.git`
- See: [Hook Development Guide](../guides/hook-development.md)

### Pattern: Hook Schema Compliance
Hook JSON output must use correct field names for each hook type.
- Discovered in: Feature #005
- Problem: PreToolUse used `decision`/`additionalContext` but should use `permissionDecision`/`permissionDecisionReason`
- Key insight: Different hook types have different valid fields:
  - SessionStart: `hookSpecificOutput.additionalContext`
  - PreToolUse: `hookSpecificOutput.permissionDecision`, `permissionDecisionReason`
  - PostToolUse: `hookSpecificOutput.additionalContext`
- Validation: Use Context7 to look up Claude Code hook documentation for authoritative schema
- Solution: Tests should validate output structure matches expected schema per hook type

### Pattern: Retroactive Feature Creation as Recovery
When work is done outside the workflow, recover by creating feature artifacts after the fact.
- Used in: Feature #008
- Steps: Create folder + .meta.json, write brainstorm.md/spec.md, create branch, commit, run /iflow:finish
- Benefit: Preserves audit trail without discarding completed work
- Trade-off: Artifacts are reconstructed, not organic; less detailed than if created during work

### Pattern: Two-Plugin Coexistence
Maintain separate dev (iflow/) and production (iflow/) plugin directories.
- Used in: Feature #012
- Benefit: Clean releases via copy, no branch-based transformations
- Protection: Pre-commit hook blocks direct commits to production plugin

### Pattern: Environment Variable Bypass for Automation
Use env var (e.g., IFLOW_RELEASE=1) to bypass protective hooks during scripted operations.
- Used in: Feature #012
- Benefit: Hooks protect interactive use while allowing automation
- Key: Check early in hook, output allow with reason, exit cleanly

### Pattern: Parallel Subagent Delegation for Independent Research
Deploy multiple subagents in parallel when researching independent domains.
- Used in: Feature #013
- Benefit: Faster research, no dependencies between internet/codebase/skills searches
- Implementation: Multiple Task tool calls in single response for simultaneous invocation
- Key: Each agent has clear domain boundary and returns structured findings

### Pattern: Evidence-Backed Claims in Documentation
Require citations for technical claims in PRDs and design documents.
- Used in: Feature #013
- Benefit: Improves intellectual honesty, surfaces assumptions vs verified facts
- Format: `{claim} — Evidence: {source}` or `{claim} — Assumption: needs verification`
- Quality gate: Reviewer challenges uncited claims and false certainty

### Pattern: Trigger Phrase Descriptions for Skills and Agents
Use explicit trigger phrases in descriptions to enable intent matching.
- Source: [Anthropic plugin-dev](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/plugin-dev)
- Format: `This skill should be used when the user says 'X', 'Y', or 'Z'. [Capability description].`
- Benefit: AI can match user intent to components via quoted phrases
- Key: Use third-person language, not second-person; include 3-4 trigger phrases
- Applied: 2026-02-04 quality improvements

### Pattern: Semantic Color Coding for Agents
Assign colors to agents based on functional category for visual distinction.
- Used in: 2026-02-04 quality improvements
- Categories:
  - `cyan` = Research (exploration, investigation)
  - `green` = Implementation (writing code/docs)
  - `blue` = Planning/validation (chain, design, plan review)
  - `yellow` = Early-stage review (brainstorm, PRD)
  - `magenta` = Quality/compliance review (spec, security, final)
  - `red` = Simplification
- Benefit: Terminal output distinguishes agent types at a glance

### Pattern: Thin Orchestrator + Reference Files
Keep SKILL.md as a process orchestrator (<120 lines), push domain knowledge to `references/` directory.
- Used in: Feature #018
- Benefit: Extensible without touching core logic; new types/methods added to reference files only
- Structure: SKILL.md defines Input/Process/Output, references/ holds domain-specific content
- Example: structured-problem-solving SKILL.md (114 lines) + 4 reference files (~480 lines total)

### Pattern: Cross-Skill Read via Base Directory
Derive sibling skill path by replacing skill name in Base directory path for read-only access.
- Used in: Feature #018
- Mechanism: Replace `skills/{current-skill}` with `skills/{target-skill}` in Base directory
- Constraint: Read-only access to reference files only; never write to another skill's directory
- Fallback: Copy needed content to own `references/` directory if path resolution fails

### Pattern: Conditional PRD Sections
Use "only when condition is met" guards for optional sections in document templates.
- Used in: Feature #018
- Benefit: Backward compatibility — absence of condition means default behavior
- Example: Structured Analysis section only appears when Problem Type is not "none"
- Key: Missing field = default behavior, no version flags or migration scripts needed

### Pattern: Zero-Code-Change State Machine Solutions
Explore whether existing transition logic can handle new cases by setting the right initial state values.
- Used in: Feature #021
- Benefit: Avoided modifying core validateTransition logic for planned→active feature transitions
- Example: Setting `lastCompletedPhase = "brainstorm"` made /specify a normal forward transition (index 1 == 0 + 1)
- Key: Reuse existing invariants rather than adding conditional branches

### Pattern: Test Fixtures Must Match Tool Scan Paths
Place test fixtures where validation tools actually scan, not in temporary/sandbox locations.
- Used in: Feature #021
- Benefit: Plan reviewer caught that fixtures in agent_sandbox/ would be invisible to validate.sh scanning docs/features/
- Instead: Use docs/features/999-test-*/ for validate.sh fixtures, with explicit cleanup steps

### Pattern: Independent Iteration Budgets for Nested Cycles
When a workflow has nested iteration loops, make budgets independent.
- Used in: Feature #021
- Benefit: Reviewer-decomposer cycle (max 3) doesn't consume user refinement cycle (max 3) budget
- Key: Each cycle has its own counter and max, preventing one from starving the other

### Pattern: Heavy Upfront Review Investment
Heavy upfront review investment (15-30+ pre-implementation review iterations) correlates with clean implementation (0-1 actionable issues across all reviewers). Front-loading review effort shifts risk discovery to phases where changes are cheap (text edits) rather than expensive (code changes).
- Observed in: Feature #022, implementation phase
- Confidence: high
- Last observed: Feature 021
- Observation count: 11

### Pattern: Template Indentation Matching
When inserting blocks into existing prompt templates, read the target file first and match its specific indentation level (which may differ per file). Prevents downstream formatting issues.
- Observed in: Feature #022, Task 1.5
- Confidence: medium
- Last observed: Feature #022
- Observation count: 1

### Pattern: SYNC Markers for Copy-Paste Cross-File Consistency
When identical dispatch logic must live in 3+ files with no include mechanism, place a named HTML comment marker (e.g., `<!-- SYNC: enriched-doc-dispatch -->`) at each copy site. Use `grep -c` on the marker string to verify all copies are present. The expected count becomes a grep-verifiable contract.
- Observed in: Feature #028, design handoff phase — TD7 decision for 3-file dispatch duplication across updating-docs SKILL.md, finish-feature.md, and wrap-up.md
- Confidence: high
- Last observed: Feature #028
- Observation count: 1

### Pattern: Pre-computed Shell Values Preserve Agent READ-ONLY Constraints
When agent logic conceptually requires shell execution (git timestamps, file sizes, directory listings), the calling command should pre-compute these values and inject them as context rather than assigning shell operations to the agent. This preserves the agent's READ-ONLY tool constraint without sacrificing capability.
- Observed in: Feature #028, design iter 3 — researcher agent (Read/Glob/Grep only) could not run git log for drift detection; resolved by adding timestamp pre-computation step to calling commands (I9, I10)
- Confidence: high
- Last observed: Feature #028
- Observation count: 1

<!-- Example format:
### Pattern: Early Interface Definition
Define interfaces before implementation. Enables parallel work.
- Used in: Feature #42
- Benefit: Reduced integration issues by 50%
-->

### Pattern: Skeptic Design Reviewer Catches Feasibility Blockers Early
When the design reviewer operates in 'skeptic' mode and challenges unverified assumptions (CLI mechanisms, parser complexity, file format handling, runtime behavior gaps), it prevents costly rework in later phases. Architectural pivots and behavioral clarifications made during design are far cheaper than discovering these issues during implementation.
- Observed in: Feature #023, design phase
- Confidence: high
- Last observed: Feature #033
- Observation count: 3

### Pattern: Detailed Rebuttals With Line-Number Evidence Resolve False Positives
When the implementer provides exact line references, quotes from spec/design, and git-blame evidence for pre-existing code, false-positive review blockers are resolved without code churn. This preserves implementation quality while avoiding unnecessary changes.
- Observed in: Feature #023, implement phase
- Confidence: medium
- Last observed: Feature #023
- Observation count: 1

### Pattern: Documentation Gap Verification via Three-Point Anchor
When merging documentation improvements into CLAUDE.md, cross-examine candidate items against three anchor points: (1) constitution.md core principles, (2) system prompt enforced behaviors, (3) workflow phase safety mechanisms. Items present in all three are redundant; items in none are genuine gaps.
- Observed in: CLAUDE.md Working Standards addition — filtered 8 candidates to 5
- Confidence: high
- Last observed: 2026-02-22
- Observation count: 1

### Pattern: Directive Specificity via Tooling References
When writing behavioral guidance in documentation, include explicit tool/command references (e.g., `/iflow:remember`, `systematic-debugging` skill) instead of abstract principles. Concrete references reduce interpretation variance.
- Observed in: CLAUDE.md Working Standards section
- Confidence: medium
- Last observed: 2026-02-22
- Observation count: 1

### Pattern: Domain Reviewer Approval Gates Chain Reviewer Escalation
When the domain reviewer (task-reviewer, plan-reviewer) has explicitly approved a domain-specific concern (task sizing, heuristic tolerances, format specifics), the chain reviewer (phase-reviewer) may note it but may not re-raise it as Needs Revision. Domain expertise on domain concerns is final for structural gatekeepers.
- Observed in: Feature #026, create-tasks phase — 5 chain review iterations on task-size concern approved by domain reviewer at iter 3
- Confidence: high
- Last observed: 2026-02-22
- Observation count: 1

### Pattern: Extract Behavioral Anchors to Reference Files for Evaluator Skills
When building a skill with an LLM-as-evaluator pattern (score N dimensions, generate improved version), extract behavioral anchors into a separate reference file (scoring-rubric.md) rather than embedding them in SKILL.md. This keeps the skill under token budget and allows rubric updates without modifying the skill.
- Observed in: Feature #027, design phase — SKILL.md landed at 216 lines (well under 500) because behavioral anchors lived in references/
- Confidence: high
- Last observed: Feature #027
- Observation count: 1

### Pattern: Calibration Gates Between Skill and Command Creation
After building an evaluator skill, run it on 2-3 diverse inputs and verify score differentiation (e.g., 20+ point spread) before proceeding to build dispatcher commands. Without early calibration, a rubric that fails to differentiate would only be discovered during end-to-end validation, requiring cascading rework.
- Observed in: Feature #027, plan phase — plan-reviewer iter 2 blocker: "No intermediate calibration testing — late-stage rework risk for scoring rubric"
- Confidence: high
- Last observed: Feature #027
- Observation count: 1

### Pattern: Compose-Then-Write for Multi-Transformation File Updates
For patterns where multiple transformations apply to one file, build the complete content in memory first and perform a single write rather than multiple sequential writes. Prevents partial-update states and reduces error surface.
- Observed in: Feature #027, implementation iter 7 — quality reviewer flagged 3 sequential writes to same file; restructured to compose-then-write
- Confidence: high
- Last observed: Feature #027
- Observation count: 1

### Pattern: INSERT OR IGNORE for Idempotent Entity Registration
For entity registries backed by SQLite, INSERT OR IGNORE provides correct idempotency across backfill re-runs, server restarts, and duplicate calls without application-level dedup logic. Combine with a metadata marker (e.g., `backfill_complete`) to skip re-scans.
- Used in: Feature #029
- Confidence: high
- Last observed: Feature #029
- Observation count: 1

### Pattern: Recursive CTE + Depth Guard for Tree Registries
Use a single recursive CTE (not Python-side recursion) for tree traversal in SQL-backed registries. Eliminates O(N) round trips, enables depth guards at the SQL layer, and returns depth values directly usable for indentation. Default `max_depth=50`.
- Used in: Feature #029, implement iter 1
- Confidence: high
- Last observed: Feature #029
- Observation count: 1

### Pattern: Topological Backfill Ordering for Entity Registries
Backfill scanners must process entities in parent-first order (backlog -> brainstorm -> project -> feature). Combine with synthetic 'orphaned' and 'external' entity stubs for nodes whose parent cannot be found.
- Used in: Feature #029, design iter 2
- Confidence: high
- Last observed: Feature #029
- Observation count: 1

### Pattern: Shared Templates in tasks.md for Cross-Task Design Patterns
When design.md defines templates, format patterns, or variable definitions referenced by multiple tasks, reproduce them verbatim in a "Shared Templates" section at the top of tasks.md. Tasks must be self-contained — referencing design labels without inline reproduction forces cross-document lookup and blocks reviewers.
- Used in: Feature #030, create-tasks — task-reviewer iter 4 blocker, cap with {feature_path} undefined
- Confidence: high
- Last observed: Feature #030
- Observation count: 1

### Pattern: Artifact-Under-Review Stays Inline in Reviewer Dispatch
The artifact being reviewed (e.g., spec.md for spec-reviewer, design.md for design-reviewer) stays inline in the dispatch prompt. Only upstream context artifacts (PRD, spec for a design review) are lazy-loaded via Required Artifacts references.
- Used in: Feature #030, design iters 3–4
- Confidence: high
- Last observed: Feature #030
- Observation count: 1

### Pattern: Behavioral Changes Require Explicit Before/After Documentation
When a feature modifies agent context (adding/removing artifacts from dispatches), document the change as a behavioral change with an explicit before/after table — not as "transport optimization." Include Agent, Artifact Added/Removed, and Rationale columns.
- Used in: Feature #030, design iter 4 + plan iter 1
- Confidence: high
- Last observed: Feature #030
- Observation count: 1

### Pattern: Zero-Deviation Implementation via Binary Done-When Criteria
When tasks contain binary done-when criteria, verbatim templates, and scoped grep patterns, implementation achieves zero deviations. 18 tasks in Feature #030 completed with 0 deviations.
- Used in: Feature #030, implement phase — 18 tasks, 0 deviations
- Confidence: high
- Last observed: Feature #030
- Observation count: 1

### Pattern: Three-Reviewer Parallel Dispatch With Selective Re-Dispatch
Three-reviewer parallel dispatch with selective re-dispatch resolves implementation issues efficiently: quality catches logic bugs, security catches safety issues, implementation catches spec compliance — all in a single iteration cycle.
- Observed in: Feature #031, implement phase — 3 distinct issue categories found and fixed in one cycle
- Evidence: Quality caught phase_iteration off-by-one, security caught git add -A staging scope, implementation caught spec compliance — all fixed in 1 pass, approved by iter 2
- Confidence: high
- Last observed: Feature 020
- Observation count: 3

### Pattern: Enumerate Git Edge Cases in Design Technical Decisions
When design involves git operations (diff, commit, staging), enumerate all edge cases in a dedicated Technical Decision section: diff baseline strategy, empty commit handling, staging scope, commit message format, SHA lifecycle.
- Observed in: Feature #031, design phase — 2 of 3 iterations driven by git edge cases (TD2 in-memory diff infeasibility blocker, HEAD~1 vs last_commit_sha contradiction blocker)
- Evidence: Front-loading these into a structured TD section would have prevented 2 of 3 design iterations
- Confidence: high
- Last observed: Feature #031
- Observation count: 1

### Pattern: Edge-Case Test Scenarios Belong in ACs, Not Technical Decisions
When a Technical Decision section describes an edge-case test scenario (e.g., "reversed attribute order"), promote it to a named Acceptance Criterion or plan task before design handoff. TD "testing notes" are not contractual and propagate as blockers across downstream phases.
- Observed in: Feature #032, design handoff → plan review — reversed-attribute-order TD2 note drove handoff cap and plan-reviewer blocker (3 downstream iterations from one unspecified edge case)
- Confidence: high
- Last observed: Feature #032
- Observation count: 1

### Pattern: Name Shared Sub-Procedures at Design Time With Full I/O Contract
When two or more design sections describe the same algorithm in parallel prose, extract it as a named sub-procedure with explicit inputs, outputs, and placement ordering at design time. Unnamed shared logic acquires its contract incrementally across chain review iterations.
- Observed in: Feature #032, create-plan phase — match_anchors_in_original described in both C6 and C9 required 4 chain iterations to acquire name, label, I/O contract, and placement ordering
- Confidence: high
- Last observed: Feature #032
- Observation count: 1

### Pattern: Reactive Downstream Steps Signal Upstream Template Gaps
When a downstream phase adds a compensating step to recover from an upstream gap (e.g., a grep discovery pre-step in plan because spec missed .meta.json fields), the correct fix is a structural update to the upstream template, not the downstream workaround.
- Observed in: Feature #004, specify phase — spec reviewer caught missing .meta.json fields twice; recovery was a grep pre-step in plan rather than a spec template fix
- Confidence: high
- Last observed: Feature #004
- Observation count: 1

### Pattern: ADR Appendix Readability Ownership
For ADR-style documentation features with multiple appendices, verify at design-handoff that every section exceeding 80 lines has explicit subheadings. Readability is a structural concern — catching it at implement review is one phase too late.
- Observed in: Feature #004, implement phase — Appendix G readability split caught only at implement iter 1
- Confidence: medium
- Last observed: Feature #004
- Observation count: 1

### Pattern: Two-Pass Audit Methodology with Convergence Check
For exhaustive codebase audits, a two-pass methodology (Pass 1: grep-based candidate extraction with triage; Pass 2: structural file walk by directory) with an explicit convergence check produces reliable completeness. The convergence check compares entry counts between passes and flags discrepancies for investigation, transforming a subjective "I think I found them all" into an objective cross-validation between independent search methods.
- Observed in: Feature 006, specify phase — spec-reviewer iter 1 blocker "no verifiable completeness criterion"; resolved by adding two-pass methodology with convergence check; 60 guards cataloged with verified completeness
- Confidence: high
- Keywords: audit, two-pass, grep, convergence, completeness, codebase-analysis, documentation
- Last observed: Feature 006
- Observation count: 1

### Pattern: Phase-Reviewer as Cross-Artifact Consistency Checker
The phase-reviewer (gatekeeper) catches cross-artifact consistency failures that domain reviewers miss because it is the only reviewer in the chain with visibility across all artifacts simultaneously. Domain reviewers focus on their artifact type; the phase-reviewer reads the full artifact graph and is structurally positioned to detect cross-artifact contradictions invisible in isolation.
- Observed in: Feature 007, all 5 phases — PHASE_GUARD_MAP inversion (9 entries inverted, caught design iter 2 after domain approval), __init__.py stub ordering (create-plan), GUARD_METADATA batch verification scope (create-tasks)
- Confidence: high
- Keywords: ["phase-reviewer", "cross-artifact", "consistency", "gatekeeper", "review-chain"]
- Last observed: Feature 007
- Observation count: 1

### Pattern: Zero-Deviation Implementation After Phase-Reviewer Cap Iterations
When phase-reviewer caps are hit during create-plan or create-tasks phases, the additional iterations represent front-loaded investment that produces clean implementations. Feature 007 hit caps in both create-plan and create-tasks yet produced 0 deviations across 29 tasks and 180 passing tests. Phase-reviewer caps are not quality failures — they are the pre-implementation investment that eliminates implementation rework.
- Observed in: Feature 007, implement phase — 0 deviations across 29 tasks, 180 tests passing; preceded by phase-reviewer caps at create-plan iter 5 and create-tasks iter 5
- Also observed in: Feature 010, implement phase — 0 deviations across 22 tasks, 269 tests passing; preceded by create-plan planReview cap (5 iters, 6 reviewer notes) and chainReview cap (5 iters, 1 reviewer note). All reviewer notes served as implementation guidance.
- Confidence: high
- Keywords: ["phase-reviewer-cap", "zero-deviation", "pre-implementation-investment", "implementation-quality", "front-loading"]
- Last observed: Feature 010
- Observation count: 2

### Pattern: Dependency API Pre-Read Before Spec Authoring
For features with `depends_on_features`, read each dependency's public interface before authoring any FR. Annotate each consumed API reference with `verified against: <file>:<line>`. All 4 iter-1 blockers in feature 008 specify phase were resolvable by reading feature 007 and feature 005 source before spec authoring — non-existent DB method, wrong function signature, wrong return type, missing entity-existence precondition.
- Observed in: Feature 008, specify phase — 4 iter-1 blockers all from API assumption errors; resolved by reading dependency source code before authoring FRs
- Confidence: high
- Keywords: ["dependency-api", "pre-read", "spec-authoring", "api-assumption", "depends-on-features"]
- Last observed: Feature 008
- Observation count: 1

### Pattern: Sibling-Sweep After Cross-Cutting Fix
After fixing a pattern that must be consistent across N sections, verify the fix is present in ALL sibling sections before submitting. The `if not last_completed:` vs `if last_completed is None:` defect class in feature 008 appeared at iter 2 (derivation path) and iter 3 (hydration path) because the iter 2 fix addressed `_derive_completed_phases` but did not sweep `_hydrate_from_meta_json`.
- Observed in: Feature 008, implement phase — falsy guard recurred across iters 2 and 3 due to partial-fix sweep; resolved by sweeping all sibling sections
- Confidence: high
- Keywords: ["sibling-sweep", "cross-cutting", "partial-fix", "consistency", "none-check"]
- Last observed: Feature 008
- Observation count: 1

### Pattern: ValueError Prefix Convention for Multi-Error-Type Routing
Establish a ValueError prefix convention (e.g., "feature_not_found:", "invalid_type_id:") at design time as a routing contract for catch-all handlers. When multiple error types share ValueError, the prefix enables downstream code to route errors without coupling to message content. Document the prefix registry in the design TD section.
- Observed in: Feature 011, create-tasks phase — AC-18 error type ambiguity resolved by establishing ValueError prefix convention at chain review iter 2
- Confidence: medium
- Keywords: ["valueerror", "prefix-convention", "error-routing", "design-td", "catch-scope"]
- Last observed: Feature 011
- Observation count: 1

### Pattern: Application-Level FTS5 Sync Over Triggers
For SQLite FTS5 external content tables, application-level sync (explicit INSERT/DELETE in Python after each entity mutation) is the correct default over database triggers. FTS5 external content tables do not support trigger-based INSERT, and trigger-based DELETE is unreliable. Application-level sync is explicit, testable, and avoids SQLite trigger limitations.
- Observed in: Feature 012, specify phase — spec iter 1 blocker: trigger-based FTS sync infeasible; resolved by switching to application-level sync
- Confidence: high
- Last observed: Feature 012
- Observation count: 1

### Pattern: Migration Idempotency via DROP+CREATE for FTS5 Tables
For FTS5 virtual tables, use DROP TABLE IF EXISTS + CREATE VIRTUAL TABLE (without IF NOT EXISTS) to ensure migration idempotency. DELETE FROM is unreliable on FTS5 external content tables, and IF NOT EXISTS silently skips re-creation of corrupted tables. DROP+CREATE guarantees a clean state on re-run.
- Observed in: Feature 012, create-plan phase — plan iter 3 blocker: DELETE FROM entities_fts unreliable; resolved by DROP+CREATE pattern
- Confidence: high
- Last observed: Feature 012
- Observation count: 1

### Pattern: Design Enhancement Three-Step Atomic Trace
When design introduces a new enum value or concept not in spec (e.g., ReconcileAction 'created'), complete the three-step trace atomically in one edit: (1) annotate definition with spec deviation note, (2) map to all affected ACs, (3) add test strategy note. Iterating these steps one-per-review-round consumed 5 handoff iterations in Feature 011.
- Observed in: Feature 011, design handoff phase — ReconcileAction 'created' traced across 5 iterations instead of 1 atomic edit
- Confidence: high
- Keywords: ["design-enhancement", "three-step-trace", "spec-deviation", "atomic-edit", "handoff-review"]
- Last observed: Feature 011
- Observation count: 1

### Pattern: Unresolved Manual Verification AC Requires Design-Phase Gate Formalization
When a manual verification AC exits specify with an unresolved formalization concern, the design artifact must include a 'Manual Verification Gate' subsection specifying: (1) responsible party, (2) exact environment setup, (3) exact command, (4) expected output, (5) where result is recorded. Without this, the concern propagates independently to every downstream phase boundary.
- Observed in: Feature 014, specify-handoff (cap) -> design-handoff iter 1 -> create-tasks task-reviewer (cap) -> implement iter 1 — AC-8 formalization crossed 4 phase boundaries
- Confidence: high
- Keywords: ["manual-verification", "ac-formalization", "phase-propagation", "gate-task", "specify-handoff", "design-gate"]
- Last observed: Feature 014
- Observation count: 1

### Pattern: Live-State Verification Evidence Resolves Static Review Stalls in One Iteration
When a static code reviewer cannot confirm that a live-state gate task was executed, presenting captured evidence (exact command, stdout output, debug-stderr content, restore confirmation) resolves the stall in one iteration without code changes.
- Observed in: Feature 014, implement iters 1-2 — Task 3.1 evidence (stdout "Invoke /iflow:design", empty debug stderr, restored .meta.json) turned warning into approval
- Confidence: high
- Keywords: ["manual-verification", "evidence-provision", "implement-review", "static-review-limit", "gate-task"]
- Last observed: Feature 014
- Observation count: 1

### Pattern: sed+diff Algorithm Consistency Check for SYNC-Marked Duplicate Blocks
When two or more files contain SYNC-marked duplicate blocks (e.g., `<!-- SYNC: phase-resolution-algorithm -->`), run a character-identity diff between the canonical blocks after any edit to either file. This catches enum value inconsistencies (`complete` vs `completed`), stale prose, and scope description mismatches that serial single-issue reviewers find one at a time.
- Observed in: Feature 015, implement run 1 iters 1-4 — four independent readability issues in SYNC blocks between show-status.md and list-features.md discovered one per iteration
- Confidence: high
- Keywords: ["sync-markers", "duplicate-blocks", "diff-verification", "markdown-migration", "consistency-check"]
- Last observed: Feature 015
- Observation count: 1

### Pattern: Fresh Implement Review Run Catches Structural Issues Serial Runs Miss
When a circuit breaker terminates an implement review run that was dominated by serial surface-level fixes, a fresh review run (reset reviewers, full scope) finds qualitatively different structural issues: SYNC cross-reference gaps, missing status variants in display examples, incomplete gather step scoping. The fresh run converges faster (2-3 iterations vs 5 circuit breaker) because it reviews holistically rather than incrementally.
- Observed in: Feature 015, implement run 2 — found SYNC cross-reference gaps, gather step scope issue, missing abandoned feature row, display example completeness; converged in 3 iterations vs run 1's 5-iteration circuit breaker
- Confidence: high
- Keywords: ["circuit-breaker", "fresh-review", "structural-issues", "holistic-review", "implement-review"]
- Last observed: Feature 015
- Observation count: 1

### Pattern: Inline Verbatim Replacement Text in Tasks
When plan/task steps that write to files include exact verbatim replacement text inline (rather than referencing spec section numbers), implementation proceeds with zero blockers. In feature 017, 5 of 6 task-review blockers involved text referenced by spec section — inlined tasks had zero implementation blockers.
- Observed in: Feature 017, create-tasks phase — tasks referencing spec sections caused 5 blockers; inlined tasks had zero
- Confidence: high
- Keywords: ["verbatim-text", "task-authoring", "inline-content", "replacement-text", "implementation-blockers"]
- Last observed: Feature 017
- Observation count: 1

### Pattern: Parallelize Implementation Across Disjoint File Sets
When implementation tasks target non-overlapping file sets, they can be dispatched in parallel without merge conflicts or ordering concerns. Feature 017 successfully parallelized across 4 phases targeting disjoint file groups.
- Observed in: Feature 017, implement phase — 4 phases with disjoint file targets executed cleanly
- Confidence: high
- Keywords: ["parallel-implementation", "disjoint-files", "task-dispatch", "merge-conflict-avoidance"]
- Last observed: Feature 017
- Observation count: 1

### Pattern: uv sync --no-dev Requires Complete Base Dependency Audit
When upgrading a shell bootstrap wrapper from a hand-maintained `uv pip install <list>` to `uv sync --no-dev`, immediately audit `[project]` dependencies in pyproject.toml to confirm every package required at runtime is listed. The switch from explicit install to lockfile-driven sync exposes implicit deps that the hand-maintained list was masking.
- Observed in: Feature 018, implement phase — quality reviewer improved Step 3 from uv pip install to uv sync --no-dev at iter 1; uvicorn was absent from [project] deps; caught only at iter 4 final validation when uv sync --no-dev was actually executed end-to-end
- Confidence: high
- Keywords: ["uv-sync", "pyproject-toml", "runtime-deps", "bootstrap-wrapper", "dependency-audit", "no-dev"]
- Last observed: Feature 018
- Observation count: 1

### Pattern: Security Surface Enumeration at Spec Time
When a spec introduces security-relevant third-party configuration (e.g., securityLevel, template escaping modes, CDN-loaded scripts), add a dedicated section listing: template escaping interaction, sanitization requirements, known CVEs, and residual risk acceptance. This prevents security concerns from threading across every subsequent phase as each discovers a new facet of the same attack surface.
- Observed in: Feature 021, securityLevel 'loose' identified at specify (blocker), validated at design, caught at plan (Jinja2 autoescaping), hardened at implement (CVE references)
- Confidence: high
- Keywords: ["security-surface", "spec-enumeration", "third-party-config", "cve-documentation", "xss-mitigation", "mermaid"]
- Last observed: Feature 021
- Observation count: 1

### Pattern: Library Integration Research Sub-Step in Design
For features integrating third-party rendering libraries, explicitly research during the design phase: security model, escaping behavior, interaction handler syntax, and template engine gotchas. This prevents discovery of library-specific constraints during plan/implement phases where changes are more expensive.
- Observed in: Feature 021, Mermaid click syntax (bare vs href), Jinja2 autoescaping interaction with Mermaid arrows, ESM module timing — each discovered at different phases
- Confidence: high
- Keywords: ["library-integration", "design-research", "third-party-rendering", "mermaid", "jinja2", "template-engine"]
- Last observed: Feature 021
- Observation count: 1

### Pattern: Early Feature Absorption as Planning Efficiency
When a planned feature's scope is a strict subset of another feature already in planning, absorb it early (during spec/design) rather than running a separate full cycle. This eliminates redundant brainstorm-to-implement overhead while preserving all requirements.
- Observed in: Feature 021 absorbed Feature 022 (kanban-card-click-through-navi) during planning, eliminating a full separate development cycle
- Confidence: medium
- Keywords: ["feature-absorption", "scope-overlap", "planning-efficiency", "redundancy-elimination"]
- Last observed: Feature 021
- Observation count: 1

### Pattern: Establish Python Import Root at Spec Time for New Packages
When a feature introduces a new Python package under plugins/iflow/, annotate all FR import examples with the verified import root at spec time. Confirm which directory sits on PYTHONPATH (`plugins/iflow/` itself, not its parent) and use that as the import base. Add conftest.py with sys.path insertion as a mandatory task 1.x whenever a new package with tests is introduced.
- Observed in: Feature 018, multi-phase — import path blocker recurred at design, plan iter 1, task iter 2, and task iter 5; same root cause crossed 4 phase boundaries before conftest.py solution was fully specified
- Confidence: high
- Keywords: ["python-imports", "pythonpath", "package-structure", "conftest", "sys-path", "new-package", "spec-annotation"]
- Last observed: Feature 018
- Observation count: 1

### Pattern: CQRS Pattern Naming in Plan Reduces Plan Review Iterations
When a feature's architecture maps to a named pattern (CQRS, event sourcing, saga), naming it explicitly in the plan makes the structure self-evident to reviewers. Plan-reviewer approved in 2 iterations (vs typical 3-5) and phase-reviewer approved on first attempt.
- Observed in: Feature 034, create-plan phase — plan-reviewer 2 iterations, phase-reviewer 1 iteration (first-pass). CQRS: SQLite DB as write model, .meta.json as synchronous read projection.
- Confidence: medium
- Keywords: ["cqrs", "architecture-naming", "plan-review", "design-pattern", "review-efficiency"]
- Last observed: Feature 034
- Observation count: 1

### Pattern: Keyword-Only Params With None Defaults for Backward-Compatible MCP Tool Extension
When extending existing MCP tool functions with new parameters (db, iterations, reviewer_notes), use keyword-only params with None defaults instead of positional params. This preserves backward compatibility with all existing call sites and degraded-mode tests without requiring simultaneous updates.
- Observed in: Feature 034, implement phase — D7 decision: keyword params (db=None defaults) preserved backward compat with 14 transition_phase and 7 complete_phase existing call sites. Zero breakage across 289 engine tests.
- Confidence: high
- Keywords: ["keyword-params", "backward-compat", "mcp-extension", "none-defaults", "api-evolution"]
- Last observed: Feature 034
- Observation count: 1

### Pattern: Phased Task Grouping (A-E) With Bridge Tasks for Large Implementation Sets
Organizing 36 tasks into 5 named phases (A: Foundation, B: Projection, C: MCP Tools, D: Write Sites, E: Enforcement) with explicit bridge tasks between phases produces clean sequential execution with clear checkpoints.
- Observed in: Feature 034, implement phase — 36/36 tasks completed with 0 blockers across 3 reviewers. Implementation log shows clean phase transitions with running test counts at each checkpoint.
- Confidence: high
- Keywords: ["phased-grouping", "task-organization", "bridge-tasks", "implementation-checkpoints", "large-feature"]
- Last observed: Feature 034
- Observation count: 1

### Pattern: Detailed Plan With Inline Code Produces First-Try Implementation Approval
When plan phase includes inline code snippets with exact insertion points and edge-case handling, implementation passes all 3 reviewers on the first iteration. The cost of plan iterations (text-only) is lower than implementation iterations (code + tests).
- Observed in: Feature 035 — plan required 4 iterations (3 plan-reviewer + 1 phase-reviewer) but implementation passed all 3 reviewers first try. Plan included inline backfill guard code with 3-case logic.
- Confidence: high
- Keywords: ["plan-detail", "first-try-approval", "insertion-point", "tdd-task-structure", "inline-code"]
- Last observed: Feature 035
- Observation count: 1

### Pattern: Isolation Principle for MCP Server Extensions
When adding new functionality to an existing MCP server, use own error decorator, own constants, and zero shared code paths with existing tools. Makes it impossible for new code to break existing tests.
- Observed in: Feature 035 — _catch_entity_value_error decorator + ENTITY_MACHINES constants isolated from feature workflow. 1,658 tests passed with zero modifications to existing feature tests.
- Confidence: high
- Keywords: ["mcp-isolation", "error-decorator", "zero-coupling", "regression-safety", "extension"]
- Last observed: Feature 035
- Observation count: 1
