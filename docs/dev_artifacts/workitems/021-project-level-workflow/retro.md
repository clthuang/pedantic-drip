# Retrospective: Project-Level Workflow

## What Went Well
- Multi-layer review system caught blockers at each phase boundary (5 spec, 4 design, 5 plan, 6 task, 1 implementation) -- each layer found issues appropriate to its abstraction level
- Implementation completed in only 2 functional iterations (plus 1 quality/security pass), indicating strong upstream preparation
- Brainstorm-skip suppression solved with zero code changes to validateTransition by setting `lastCompletedPhase` to `"brainstorm"` -- elegant state machine reuse
- Token budget risk for decomposing skill (~450 lines of 500 max) identified proactively as Risk R1 with prioritized mitigation steps
- Phased PRD scoping (3 phases with explicit FR assignment) kept this project-scale feature deliverable as Phase 1 MVP
- 16-task breakdown with binary done-when criteria and 5 parallel groups enabled smooth implementation
- Security review caught bash variable interpolation vulnerability in session-start.sh inline Python
- Test fixture location mismatch caught by plan reviewer (agent_sandbox/ vs docs/features/) -- would have been inoperative

## What Could Improve
- Plan phase consumed 6 iterations (highest of any phase) -- initial plans should include negative test cases and graph-text consistency checks
- FR numbering collision between PRD (FR-1 to FR-9) and spec (FR-1 to FR-6 for Phase 1) caused traceability friction
- ASCII dependency graphs in the plan were redrawn 3+ times due to contradictions with textual dependency lists
- Task review took 3 iterations to reach sufficient specificity -- tasks for peripheral modifications (7.1, 7.2, 7.3) lacked exact line numbers initially
- Design review iteration 2 still had 8 warnings despite all blockers resolved -- design writing checklist could catch these earlier

## Learnings Captured
- **Pattern: Zero-code-change state machine solutions** -- Explore whether existing transition logic can be leveraged by setting the right initial state values rather than adding new conditional branches
- **Pattern: Test fixtures must match tool scan paths** -- Place fixtures where tools actually scan, not in temporary/sandbox locations
- **Pattern: Independent iteration budgets for nested cycles** -- Separate reviewer-decomposer iterations from user refinement iterations with independent caps
- **Anti-pattern: Dual-representation dependency graphs** -- ASCII art + textual description invites contradictions; use a single source of truth
- **Anti-pattern: Bash variable interpolation in inline Python** -- Use sys.argv or environment variables to pass external values, never string interpolation
- **Heuristic: Graph-text consistency first** -- Validate dependency graph vs text consistency as first-pass check before deeper plan review
- **Heuristic: Read target files during task creation** -- Tasks for file modifications need exact line numbers; read the file and include them upfront

## Knowledge Bank Updates
- Added 3 patterns to patterns.md
- Added 2 anti-patterns to anti-patterns.md
- Added 3 heuristics to heuristics.md
