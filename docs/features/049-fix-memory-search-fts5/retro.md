# Retrospective: 049-fix-memory-search-fts5

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 11 min | 2 | 6 requirements across 2 independent tracks; required second pass |
| design | 9 min | 2 | v1 had early-return bug in _load_dotenv_once(); corrected in v2 |
| create-plan | 3 min | 1 | Two-track parallel plan passed first review |
| create-tasks | 3 min | 1 | TDD order explicit per task; passed first review |
| implement | 7 min | 1 | 25 tests added, zero regressions, 6 files changed |

Total active time: ~33 min. Specify and design each required 2 iterations; all downstream phases passed first-try. The RCA (written as a pre-feature step) front-loaded root cause analysis and made implementation fast.

### Review (Qualitative Observations)

1. **Design iteration caused by control-flow error in defense-in-depth logic** — v1 of _load_dotenv_once() returned early after loading cwd .env, silently blocking the .git walk-up fallback. Fixed in v2 by removing the early return and letting load_dotenv(override=False) run additively.

2. **Silent exception handling masked all three FTS5 root causes** — the existing except sqlite3.OperationalError block returned [] without logging, making Causes 1-3 invisible in production.

3. **RCA pre-work produced direct 1-to-1 spec traceability** — each of the 6 RCA causes mapped to a named requirement (R1-R6) with verified acceptance criteria. This eliminated ambiguity in all downstream phases.

### Tune (Process Recommendations)

1. **Require RCA-to-requirement traceability table in bug-fix specs** (high) — For bug-fix features, the spec phase should require a table mapping each root cause to a named requirement.

2. **Require test outlines for defensive code paths at design phase** (high) — Design artifacts for defensive/fallback code paths should include test outlines demonstrating that primary-path failure activates the fallback.

3. **Mandate logging in all catch-and-return-empty exception handlers** (high) — Any exception handler in a retrieval/search function that returns an empty collection must emit a log line before returning.

4. **Bootstrap layer must install optional deps when their feature is configured** (high) — When a config key enables an optional feature, the server bootstrap wrapper is responsible for installing that feature's dep.

5. **Use compound-failure isolation as first debugging step for no-results features** (high) — For hybrid-retrieval features, test each path in isolation with synthetic known-good data before diagnosing data quality.

### Act (Knowledge Bank Updates)

**Patterns:** RCA-driven spec, two-track parallel plan, shell .env selective grep export
**Anti-patterns:** Silent catch-and-return-empty, optional deps not auto-installed, early return in multi-fallback dotenv chain
**Heuristics:** FTS5 query safety, compound silent failure isolation, MCP server env loading from cwd

## Raw Data

- Feature: 049-fix-memory-search-fts5
- Mode: standard
- Created: 2026-03-19T09:57:18Z
- Implement completed: 2026-03-19T10:32:22Z
- Total review iterations: 7 (specify: 2, design: 2, plan: 1, tasks: 1, implement: 1)
- Tests added: 25
- Files changed: 6 (3 implementation + 3 test)
- Root causes addressed: 5 of 6 (Cause 4 — embedding backfill — scoped out)
