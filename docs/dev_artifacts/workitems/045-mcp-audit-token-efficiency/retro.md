# Retrospective: 045-mcp-audit-token-efficiency

## AORTA Analysis

### Observe

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 10m 43s | 3 | Audited 25 tools across 3 MCP servers; 15 acceptance criteria |
| design | 16m 28s | 4 | Highest iteration count — false positive CHECK constraint, _project_meta_json coupling |
| create-plan | 9m 18s | 3 | 12 items, 6 stages, full dependency graph and file concurrency constraints |
| create-tasks | N/A | 5 | 3 task-review + 2 phase-review; signature ambiguity, hidden dependency, wrapper contract gaps |
| implement | N/A | 6 rounds | All 12 tasks complete; simplification pass; 1086 tests passing |

**Summary:** 29 commits, 23 files changed, +3913/-643 lines, 4 new library files. 15 pre-impl planning review cycles. 6 parallel dispatch rounds (max 4 concurrent). Opus hit 529 API errors during review; sonnet fallback succeeded.

### Review

1. **Design correctness drove iteration count** — Both blocking design issues (CHECK constraint false positive, _project_meta_json coupling) were correctness failures requiring deeper source reading, not scope ambiguity.

2. **Task authoring underspecified extraction contracts** — 5 create-tasks iterations. Recurring gaps: signature ambiguity, hidden dependencies, wrapper patterns not stating "library returns dict, MCP wrapper serializes to JSON."

3. **Primary token-efficiency goal missed in implementation** — export_entities inline path retained indent=2 after all review cycles. Caught only in simplification pass. No format-specific test existed.

4. **Library extraction produced utility duplication** — feature_lifecycle.py duplicated 4 utilities from workflow_state_server.py. Design did not prescribe shared utility location.

5. **Opus 529 errors disrupted review** — Both implementation and security reviewers hit 529. Sonnet fallback adequate for refactoring reviews.

### Tune

1. Add prior-art verification step to design agent for DB/coupling changes (high confidence)
2. Standardize extraction task template with wrapper contract and dependency chain (high confidence)
3. Add format-specific assertions for token-efficiency acceptance criteria (high confidence)
4. Require design to identify shared utility destination for extractions (high confidence)
5. Formalize opus→sonnet fallback for review agents (medium confidence)

### Act

**Patterns:** Token-efficiency needs format-specific tests; parallel dispatch with file concurrency constraints works; extraction tasks need explicit wrapper contracts.

**Anti-patterns:** Don't leave shared utility placement unspecified in extraction designs; don't rely on reviewers to catch JSON format regressions; don't propose DB constraints without verifying current source behavior.

**Heuristics:** 15+ AC specs predict 4+ design iterations; schedule post-impl simplification for engineering-excellence features; retry on sonnet when opus returns 529.

## Raw Data
- Branch lifetime: single day (2026-03-18)
- Total review iterations: 15 pre-impl + 3 post-impl
- Commits: 29, Files: 23 (+3913/-643)
- Tests: 1086 (entity 757, workflow 284, memory 45)
- New files: entity_lifecycle.py, feature_lifecycle.py + tests
