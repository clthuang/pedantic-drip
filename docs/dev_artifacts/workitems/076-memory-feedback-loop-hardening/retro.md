# Retrospective: Memory Feedback Loop Hardening

## AORTA Analysis

### Observe

| Phase | Iterations | Notes |
|-------|------------|-------|
| specify | 3 | 1 spec-review (3 blockers on AC-4 MCP mechanism) + 1 fix + 1 phase-review |
| design | 3 | 1 design-review (3 blockers on DedupResult fields, chunking, granularity) + 1 fix + 1 phase-review |
| create-plan | 2 | 1 task-review (4 blockers on TDD specificity) + 1 fix with phase-review |
| implement | 2 | All 4 reviewers found issues: CATEGORY_PREFIXES missing, injector fallback 20, source allowlist, threshold bounds |
| **Total** | **10** | |

### Review

1. **CATEGORY_PREFIXES omission** — design C5 listed 4 of 5 category dicts but missed CATEGORY_PREFIXES. All 4 reviewers caught it independently during implement review. This is a systematic gap: when adding a new value to a multi-dict system, the design must enumerate ALL dicts that key on the same domain.
2. **Security reviewer caught 3 actionable issues** on first pass — source allowlist, threshold bounds, frombuffer guard. All were genuine gaps (not pre-existing).
3. **Spec reviewer caught the AC-4 MCP mechanism gap** — embedding computation can't happen in command markdown. Led to the `record_influence_by_content` MCP tool design.
4. **Injector fallback 20→15** — a third location for the same default (beyond session-start.sh and config.py). Relevance verifier caught it.

### Tune

1. **When adding a new enum value to a multi-dict system, enumerate ALL dicts** (high) — CATEGORY_PREFIXES was missed because the design listed CATEGORY_ORDER, CATEGORY_HEADERS, VALID_CATEGORIES but not CATEGORY_PREFIXES. Add a "grep for all usages of the enum key" step to the design checklist.
2. **Add VALID_SOURCES allowlist for any new string parameter** (high) — the security reviewer correctly flagged that source had no allowlist despite following the same pattern as category/confidence. Every enumerated parameter needs a frozenset guard.

### Act

- Anti-pattern: Incomplete multi-dict enum expansion (missed CATEGORY_PREFIXES)
- Pattern: Source allowlist validation matches category/confidence pattern
- Heuristic: grep for all dict/frozenset keyed by same domain when adding new values

## Raw Data
- Feature: 076-memory-feedback-loop-hardening
- Total iterations: 10 (specify 3, design 3, create-plan 2, implement 2)
- Files changed: 16
- Python lines: ~160 new (memory_server.py)
- Command file locations changed: 14 (influence tracking migration)
