# Retrospective: Evidence-Grounded Workflow Phases

## What Went Well

- Clear problem statement with evidence-first approach resonated immediately
- Spec phase approved in single iteration - problem framing was solid
- Design phase iterations (2) produced high-quality output with architectural clarity
- Review history captured detailed blockers and resolutions enabling future learning
- Auto-commit feature properly integrated without breaking changes
- Tool additions (Context7, WebSearch) were additive - safe integration pattern
- Stage 0 Research properly handles failures with graceful degradation and skip option
- Reasoning fields adoption accepted without resistance from reviewers
- Task phase passed on first review - proof of clear planning upstream
- Implementation balanced: 13 files, 326 insertions, 16 deletions
- All 4 phase commands enhanced with auto-commit in consistent parallel pattern

## What Could Improve

- Design phase required 2 iterations due to TD-5 evidence citation error - domain knowledge validation needed earlier
- Concurrent planning (AC-9) deferred after design approval - scope decisions should be made in spec phase
- Tool naming verification delayed to design review iteration 2 - should validate in spec phase feasibility
- Terminology inconsistency between SC-6 and AC-5 claim counts carried as warning through multiple phases
- Stage 0 failure handling added as iteration 1 blocker - comprehensive failure mode analysis needed earlier
- E2E test cleanup specification emerged late in task review - testing strategy needs early definition

## Learnings Captured

### Patterns Worth Reusing

1. **Two-iteration design is expected** for 12-component systems requiring architectural refinement
2. **Additive approach scales well**: ~25 lines/file average is sustainable
3. **Feasibility scale (5 levels)** mirrors confidence intervals - concrete and actionable
4. **Research stage placement (Stage 0)** before architecture prevents confirmation bias
5. **Auto-commit failure handling**: commit blocks, push warns - matches unix philosophy
6. **Reasoning fields propagate**: Spec → Design → Plan → Tasks creates clear traceability
7. **Independent verification spot-checking** (1-2 claims) is practical; exhaustive would block iteration

### Anti-Patterns to Avoid

1. Evidence citation errors at design review → spec should require link validation
2. Concurrent planning deferral after design → flag tentative AC items in spec
3. Tool availability verification during design review → validate dependencies in spec feasibility
4. Testing strategy details missing from plan → E2E infrastructure needs explicit specification

### Heuristics for Future Features

1. For multi-phase features with 12+ components: expect 2 design iterations
2. For tool integrations: validate tool names and availability in spec feasibility
3. For deferral decisions: flag AC items as 'Deferred' in spec, not during design
4. For reasoning propagation: use 'Why' questions across all phases
5. For error handling: distinguish local failures (block) from remote failures (warn)
6. For agent enhancement: include explicit 'MUST verify N claims' instruction
7. For auto-commit steps: include .review-history.md in git add
8. For research stages: provide explicit 'Skip (domain expert)' option

## Metrics

| Metric | Value |
|--------|-------|
| Total Duration | ~4 hours |
| Phases Completed | 5 (specify, design, plan, tasks, implement) |
| Total Iterations | 5 (1+2+2+1+1) |
| Files Changed | 13 |
| Lines Added | 326 |
| Lines Deleted | 16 |

## Knowledge Bank Updates

- Pattern: "Reasoning field propagation" - added to workflow patterns
- Heuristic: "12+ component features expect 2 design iterations"
- Anti-pattern: "Deferring scope decisions after design approval"
