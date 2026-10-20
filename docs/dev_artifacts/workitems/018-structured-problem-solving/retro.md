# Retrospective: Structured Problem-Solving

## What Went Well
- Thin orchestrator pattern kept SKILL.md at 114 lines while 4 reference files hold all domain knowledge (~480 lines) — extensible without touching core logic
- Cross-skill Read mechanism (deriving sibling path from Base directory) worked as a novel pattern for skill composition
- AskUserQuestion "Other" option confirmed as built-in, eliminating need for explicit 7th option while satisfying FR-4
- Design Divergences table (4 entries) caught PRD/spec/design mismatches early, preventing implementation confusion
- Criteria table duplication was an intentional, documented trade-off — agent needs inline access at runtime
- Line budget management: brainstorming SKILL.md landed at 482/500 (18 headroom), well within limits
- All 3 reviewers (implementation, quality, security) approved with only upstream documentation concerns

## What Could Improve
- PRD FR-9 (MCP tool for Mermaid) contradicted the spec/design resolution (inline Mermaid) — frozen PRD artifacts should note known divergences
- Cross-skill Read runtime verification was deferred — static path checks passed but no actual skill invocation test was performed
- Implementation reviewer flagged 4 "blockers" that were all upstream doc concerns, not code defects — reviewer calibration could improve
- Task line number references (4.2-4.4) shifted after Task 4.1 insertion — semantic anchors were used but the tasks.md text was initially confusing
- Code simplifier found no actionable changes — all suggestions were intentional design decisions, suggesting the simplification phase added limited value for this feature

## Learnings Captured

### Patterns
- **Thin orchestrator + reference files:** Keep SKILL.md as a process orchestrator (<120 lines), push domain knowledge to `references/` directory. Enables extension without core logic changes.
- **Cross-skill Read via Base directory:** Derive sibling skill path by replacing skill name in Base directory path. Document as novel pattern with graceful degradation fallback.
- **AskUserQuestion built-in "Other":** Use N explicit options; the system automatically provides "Other" for free text. No need to waste an option slot.
- **Design Divergences table:** When spec/design intentionally deviate from PRD, document divergences in plan.md with rationale. Prevents reviewer confusion during implementation.
- **Criteria duplication as trade-off:** When an agent needs inline access to criteria at runtime, duplicate from canonical source and document the trade-off with verification step.
- **Conditional PRD sections:** Use "only when type is not 'none'" guards for optional sections. Backward compatibility = absence means default behavior.
- **Inline Mermaid over MCP tools:** Fenced Mermaid code blocks are more portable and don't require MCP configuration. Prefer inline for documentation artifacts.

### Anti-Patterns
- **Frozen artifact contradiction:** PRD said "use MCP tool" but spec/design resolved to inline Mermaid. Frozen brainstorm artifacts should not be retroactively edited, but divergences should be noted in the artifact itself.
- **Line number references in tasks:** Referencing specific line numbers in tasks that will shift after earlier task insertions. Always use semantic anchors (exact text search targets) instead.
- **Over-counting reviewer "blockers":** Implementation reviewer flagged documentation-level concerns as "blockers" — severity calibration should distinguish code defects from upstream doc concerns.
- **Deferred runtime verification:** Static path verification is necessary but not sufficient for novel patterns. Plan for runtime verification in the first actual invocation.
- **Unnecessary simplification phase:** When all design decisions are intentional and documented, the code simplifier adds overhead without value. Consider skipping for prompt-only features.

### Heuristics
- **Reference file sizing:** ~100-160 lines per reference file balances completeness with readability. 4 files at ~480 total lines is a good ratio for a thin orchestrator.
- **Line budget headroom:** Target 90-95% of budget (450-475 of 500 lines). Landing at 96% (482) is acceptable but leaves minimal room for future additions.
- **Criteria table width:** 5 universal + 3 type-specific criteria per type is the right granularity for review — enough to catch gaps without overwhelming the reviewer.
- **Graceful degradation depth:** One fallback level (hardcoded SCQA template) is sufficient. Two levels of fallback adds complexity without proportional reliability gain.
- **Cross-skill coupling:** Keep cross-skill dependencies to Read-only access of reference files. Never have one skill Write to another skill's directory.
- **Backward compatibility via absence:** "Missing field = default behavior" is simpler than version flags or migration scripts for private tooling.
- **Problem type taxonomy size:** 5 explicit types + Other + Skip = 7 user choices. This is the upper limit for AskUserQuestion usability.

## Knowledge Bank Updates
- Added pattern: Thin orchestrator + reference files for skill composition
- Added pattern: Cross-skill Read via Base directory path derivation
- Added heuristic: Reference file sizing (~100-160 lines each)
- Added anti-pattern: Line number references in sequential tasks
