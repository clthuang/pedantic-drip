# Retrospective: Game Design Domain Skill

## What Went Well
- Spec iteration front-loading (5 iterations) eliminated all downstream ambiguity -- design, plan, tasks, and implementation each completed in 1 iteration
- Thin orchestrator + reference files pattern replicated perfectly from Feature 018. Cross-skill Read, graceful degradation, and AskUserQuestion patterns all transferred cleanly.
- Line budget management succeeded: whitespace trimming freed 30+ lines of headroom, all 4 C2 insertions fit within 500-line budget (landed at ~484)
- All NFRs met with comfortable margins: SKILL.md at 103/120, reference files 53-108/160, brainstorming at ~484/500
- Plan-reviewer caught 3 critical blockers (interleaved verification, code fence insertion, dependency graph) that would have caused implementation confusion
- Tech-evaluation-criteria.md successfully avoids all static engine/platform recommendations -- behavioral constraint BS-6 enforced throughout pipeline
- Two-phase write strategy elegantly solved the temporal dependency on Stage 2 research data
- Feature 018's retro directly accelerated 019's design -- knowledge-bank flywheel working as intended

## What Could Improve
- 5 spec iterations is high -- initial spec draft had 8 blockers. Consider a pre-spec checklist: field-level testability, temporal consistency of data flow, enforcement boundary clarity, exact output format.
- AskUserQuestion wording deviated from spec without explicit acknowledgment. Specs should distinguish binding requirements from guidance ("exact" vs "semantic intent").
- Line count discrepancy tracked across phases (482 vs 483 vs 484) caused confusion in multiple reviews. Use a single authoritative count and update after each modification.
- Cross-skill Read mechanism has still never been tested at runtime (same gap flagged in Feature 018 retro). Static path derivation is correct but actual invocation during a brainstorming session has not been verified.
- Review-history.md at 353 lines is substantial overhead. Consider summary format for non-blocker items.

## Learnings Captured

### Patterns
- **Spec Iteration Front-Loading:** Invest 3-5 spec review iterations to resolve all ambiguity. Cheaper than fixing issues downstream. Well-iterated spec enables 1-iteration downstream phases.
- **Two-Phase Write for Temporal Dependencies:** When Stage N content depends on Stage N+1 data, hold in memory and write later. Document scratch-section fallback for context pressure.
- **Interleaved Verification in Plans:** Add inline verification within each phase rather than deferring all checks to a final cross-check phase.
- **Orthogonal Dimension Extension:** New optional dimensions should be independent of existing ones. Separate Steps, PRD sections, and review criteria. Both/either/neither must work.
- **Whitespace Budget Recovery:** Markdown files typically have 20-30% blank lines. Trim to 1 blank between sections to recover headroom before adding content.
- **Behavioral Constraint Cascade:** Define constraints in PRD, reinforce in spec, verify in plan, include in task criteria, validate in implementation. Each stage checks independently.
- **Domain Skill Pattern:** SKILL.md (<120 lines) as orchestrator, 5-7 reference files (each <160 lines), cross-skill Read for loading, graceful per-file degradation.

### Anti-Patterns
- **Stale Line Count Propagation:** Never carry forward line counts from earlier artifacts. Re-verify after each modification.
- **Over-Specifying UI Text:** Mark user-facing text as "semantic intent" vs "exact wording required". Allow refinement at implementation time.
- **Deferred Runtime Verification:** Two features now use cross-skill Read without runtime test. Add smoke test after third occurrence.

### Heuristics
- Spec iterations: 1-3 first-pass blockers = 2 iterations; 4-8 blockers = 3-5 iterations
- Reference file sizing: Target 70-135 lines per file
- SKILL.md budget: 15% frontmatter, 40% process, 30% output, 15% error handling
- Whitespace trimming: Add 3-line safety margin over estimated insertion size
- Domain review criteria: Always warnings, never blockers. Check existence, not correctness.
- Brainstorming SKILL.md at ~484/500 -- only 16 lines headroom for future domain skills

## Knowledge Bank Updates
- Domain Skill Pattern documented (extends 018's thin orchestrator pattern)
- Spec Iteration Front-Loading heuristic validated with data
- Two-Phase Write pattern documented for temporal dependencies
