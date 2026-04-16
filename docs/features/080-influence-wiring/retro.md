# Retrospective: 080-influence-wiring

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Iterations | Notes |
|-------|-----------:|-------|
| specify | 3 | Iter 1 + 2 blockers around 14-caller migration path and stderr destination; iter 3 polish for class name + error/boundary AC expansion |
| design | 3 | Iter 1 blockers: `Ranker` vs `RankingEngine` class name mismatch, early-return diagnostic policy; iter 2 wrapper-side emission fix; iter 3 bool-rejection code polish |
| create-plan | 2 | Iter 1 blockers: missing `pathlib.Path` import, missing `sys` import, TDD ordering of Task 2.1, config monkeypatch semantics |
| implement | 1 | Clean — implementation-reviewer approved 4/4 levels zero issues |

**Totals:** 9 review iterations. Small scope: ~150 LOC across 5 files (memory_server.py, ranking.py, test files, 3 config/docs files) + 14 mechanical caller migrations.

**Tests landed:** 501/501 pass after merge (+143 new tests for this feature covering AC-1 through AC-11). `validate.sh`: 0 errors, 8 warnings (= baseline, unchanged). `test-hooks.sh`: 101/101.

### Review (Qualitative Observations)

1. **Upstream class-name error surfaced at design review, fixed in spec too.** Spec FR-2 referenced `Ranker._prominence` when the actual class is `RankingEngine`. Design-reviewer iter 1 caught it. The design-phase backward-travel path worked cleanly — we applied the rename to both spec and design in one iteration rather than a full backward phase transition.

2. **Spec-reviewer caught the 14-caller migration trap.** Iter 1 blocker: changing the function signature default from 0.70→0.55 would have been a no-op because 14 command files pass `threshold=0.70` literally. Had the spec approved without this catch, the implementation would have "worked" in isolated tests but failed the Success Criteria in production (30% hit rate). This is the exact class of bug adversarial review is for.

3. **Early-return diagnostic policy is a subtle gotcha in MCP tooling with `@with_retry`.** Design-reviewer iter 1 flagged that emitting diagnostics "at the bottom of the helper" would silently skip 5 early-return paths (empty injected, numpy missing, provider unavailable, no chunks, no embeddings) — exactly the scenarios operators enable debug to observe. Moving emission to the MCP wrapper (outside `@with_retry`) resolved both the early-return gap and the double-logging risk in one change.

4. **Implementation fixed pre-existing test bug per leave-ground-tidier memory.** `TestSysPathIdempotency::test_sys_path_no_duplicate_hooks_lib` was already failing on base branch when test_memory_server + test_ranking ran together (pytest prepended hooks/lib automatically for test_ranking). Implementer correctly tightened the assertion to the narrower guard-idempotency invariant rather than normalizing pytest's sys.path behavior.

### Tune (Process Recommendations)

1. **spec-reviewer should specifically check for "default-change → caller-miss" patterns** (Confidence: high)
   - Signal: when a spec says "lower default from X to Y," explicitly grep for `argument=X` in callers and assert caller migration is in scope. This feature's 14-caller trap would have been caught in spec iter 1 without the adversarial reviewer having to find it organically.

2. **Design review for MCP tools should audit `@with_retry` decorated functions for side-effect placement** (Confidence: medium)
   - Signal: any new side-effect (logging, metrics, notifications) added to a `@with_retry` function doubles on retry. Rule: prefer wrapper-side emission outside the retry boundary.

3. **Plan-reviewer should verify all new module-level symbols have their imports** (Confidence: high)
   - Signal: iter 1 blockers were pure missing imports (`pathlib.Path`, `sys`) — mechanical oversights. Checklist item: "For each new module-level symbol, confirm the module already imports the dependency."

### Act (Knowledge Bank Updates)

**Patterns added:**
- **Wrapper-Side Emission Outside `@with_retry`** — when adding diagnostics to a `@with_retry`-decorated helper, emit from the outer wrapper (not the helper body) so retries don't double-log and early-return paths are still covered.

**Anti-patterns added:**
- **Default-Change Without Caller Migration** — changing a function's parameter default has zero effect on callers that pass the argument explicitly. When a spec says "lower the default," the spec must also require an explicit caller-migration task with verification grep.

**Heuristics added:**
- **Point-of-Consumption Config Coercion (over `config.py` modification)** — add per-field type validation at the consumer site (e.g., `Ranker.__init__`, MCP helper) not in the shared `read_config` path. Scopes the change to the feature; preserves existing tolerant-parse behavior for all other consumers.

## Raw Data
- Feature: 080-influence-wiring
- Mode: standard
- Branch: feature/080-influence-wiring
- Total review iterations: 9 (3 + 3 + 2 + 1)
- Tests landed: 501 passing (143 new)
- Final validate.sh: 0 errors, 8 pre-existing warnings unchanged
