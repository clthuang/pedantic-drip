# Retrospective: 012-full-text-entity-search-mcp-to

## AORTA Framework Analysis

### Observe (Metrics)

| Phase | Review Iterations | Duration (approx) | Notes |
|-------|------------------:|-------------------:|-------|
| specify | 4 spec + 2 phase = 6 | ~45 min | FTS5 trigger assumptions drove 3 blockers iter 1 |
| design | 4 design + 2 handoff = 6 | ~65 min | FTS5 availability check, truthiness vs identity |
| create-plan | 5 plan + 2 chain = 7 | ~65 min | Plan-reviewer cap hit (5/5); DROP+CREATE pivot |
| create-tasks | 3 task + 3 chain = 6 | ~30 min | Footer format, error string, line number staleness |
| implement | 3 (2 impl, 2 quality, 1 security) | ~75 min | Clean pass — 0 blockers, warnings only |
| **Total** | **25 pre-impl + 3 impl = 28** | **~280 min** | |

**Code output:** 12 files changed, +2920/-18 lines (1396 implementation lines, 1060 documentation lines)
**Test output:** 864 lines (test_search.py) + 248 lines (test_search_mcp.py) = 1112 test lines
**Test-to-code ratio:** ~4.5:1 (1112 test lines / ~250 implementation lines)

### Review (Qualitative Observations)

**1. FTS5 Technology Minefield**
FTS5 external content tables are a technology minefield for specifications. Three distinct assumption categories drove early-phase iterations:
- Trigger-based sync (spec iter 1) — SQLite triggers cannot INSERT into FTS5 external content tables
- FTS5 availability detection (design iter 2) — `SELECT fts5()` is invalid; FTS5 is a module not a function
- DELETE FROM on FTS5 tables (plan iter 3) — unreliable on external content tables; DROP+CREATE required

Each was a factual correctness issue discoverable by reading SQLite FTS5 documentation, but each surfaced only when a reviewer challenged the assumption. A pre-spec FTS5 checklist would front-load these discoveries.

**2. Plan Reviewer Cap via Specificity Cascade**
Plan review hit the 5-iteration cap, driven by a specificity cascade: cursor capture → keyword operators → schema version assertion census → migration idempotency → test naming. Each fix revealed the next layer of underspecification. The cascade bottomed out at concrete DDL/DML operations — consistent with the known heuristic.

**3. Clean Implementation Despite Heavy Pre-Implementation Investment**
25 pre-implementation review iterations produced an implementation with 0 blockers across all 3 reviewers. Only quality warnings (stale test names, missing comments, assertion cleanup) required fixes. This continues the "Heavy Upfront Review Investment" pattern (now observed 9 times).

### Tune (Recommendations)

1. **Create FTS5 pre-spec checklist** — Before specifying any FTS5 feature, verify: sync mechanism (triggers vs application-level), availability detection method, DELETE/rebuild behavior on external content tables, keyword operator handling
2. **Schema version assertion census before plan submission** — When a migration changes the schema version, enumerate ALL existing version assertions (grep) and include the count in the plan. Prevents the 2-iteration discovery pattern seen here.
3. **Calibrate test-to-code ratio expectation for FTS features** — 4.5:1 test-to-code ratio reflects the combinatorial surface of FTS sync (register + update + search + adversarial). Document as expected baseline.
4. **Application-level FTS sync is the correct default** — Triggers are infeasible for FTS5 external content tables. Start with application-level sync and document why.
5. **Migration idempotency via DROP+CREATE** — For FTS5 tables, DROP TABLE IF EXISTS + CREATE is more reliable than DELETE FROM for re-run safety. Document as the default pattern.

### Act (Knowledge Bank Updates)

**Patterns (new):**
- Application-Level FTS5 Sync Over Triggers
- Migration Idempotency via DROP+CREATE for FTS5 Tables

**Patterns (updated):**
- Heavy Upfront Review Investment: observation count 8→9, last observed Feature 012

**Anti-Patterns (new):**
- Assuming FTS5 Availability via SQL Function Call
- Truthy Check for Optional String Fields in FTS Sync

**Heuristics (new):**
- FTS5 Database Feature Pre-Spec Checklist
- Schema Version Assertion Census Before Plan Submission
- 4.5:1 Test-to-Code Ratio for FTS5 Search Features

**Heuristics (updated):**
- Reviewer Iteration Count as Complexity Signal: observation count 8→9, last observed Feature 012
