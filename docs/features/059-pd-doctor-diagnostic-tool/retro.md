# Retrospective: 059-pd-doctor-diagnostic-tool

## Summary
New `pd:doctor` command providing 10 read-only data consistency checks across entity DB, memory DB, workflow state, git branches, and filesystem. Cross-project safe, backward-transition aware, marketplace compatible.

## Metrics
- **Phases:** brainstorm → specify → design → create-plan → create-tasks → implement → finish
- **Commits:** 19
- **Lines added:** ~6,290 (across 17 files)
- **Tests:** 99 passing in 15s
- **Review iterations:** plan 2/5, tasks 1/5, implement 2/5
- **Mode:** standard

## What Went Well (Amplify)

1. **Adversarial review rounds caught real issues before implementation.** Three rounds of adversarial subagent probing (failure modes, side effects, cross-project) identified 24 issues that were incorporated into the plan before a single line of code was written. The biggest catch: cross-project entity false positives (25 real orphaned entities in the shared DB) would have made doctor noisy and untrustworthy.

2. **BDD test catalog (85 scenarios) provided clear implementation targets.** Each task had specific test names listed, making TDD execution straightforward. The implementer agents knew exactly what to test without ambiguity.

3. **Wrong entity_dependencies column names caught by implementation reviewer.** The reviewer cross-referenced against `database.py` and found `source_uuid/target_uuid` vs actual `entity_uuid/blocked_by_uuid`. Tests passed because the test helper created the table with the wrong schema — a classic mock-vs-production divergence.

## What Went Wrong (Observe)

1. **entity_dependencies column name mismatch.** The implementer hallucinated column names (`source_uuid/target_uuid`) instead of reading the actual schema from `database.py`. The test helper compounded this by creating a table with the wrong schema, so tests passed against a wrong model. This is the same anti-pattern class as "mocked tests passed but prod failed" documented in the knowledge bank.

2. **DB state management was fragile throughout.** The entity DB was persistently locked by MCP servers (PIDs 1675, 16896, 32911) during the session, preventing `complete_phase` MCP calls. Had to use direct SQL and Python workarounds to update `.meta.json` and workflow state. The doctor tool itself is designed to diagnose this exact class of problem.

3. **Plan phase was heavy.** Three adversarial review rounds + 85 BDD scenarios generated a 490-line plan.md. While thorough, this consumed significant context and time. For a feature of this scope (10 check functions + orchestrator), a lighter plan with fewer adversarial rounds would have been sufficient.

## Patterns Identified (Root-cause & Track)

1. **Anti-pattern: Test schema diverges from production schema.** When test helpers create their own table schema instead of importing from the production code, column name mismatches go undetected. Fix: test helpers should either import the CREATE TABLE statement from the production module or use the production constructor (e.g., `EntityDatabase(":memory:")`) to create the schema.

2. **Heuristic: Adversarial review has diminishing returns after round 2.** Round 1 (plan structure) found 5 blockers. Round 2 (side effects/rework) found critical backward-transition issues. Round 3 (cross-project) found important marketplace issues but also added complexity. Two rounds would have caught 80% of the value.

3. **Pattern: Direct SQLite fallback works when MCP is locked.** When MCP tools return `db_unavailable` errors, the workaround is: (1) identify lock holder via `fuser`, (2) use direct `sqlite3` with `busy_timeout`, (3) update `.meta.json` via Python. This is exactly what the doctor tool's design choice (TD-1: direct SQLite, not MCP) anticipated.

## Action Items

1. **Update test helper pattern guidance** — Add to knowledge bank: "Test helpers that create DB tables should use production schema (import or constructor), not hand-written CREATE TABLE statements."
2. **Consider 2-round adversarial review as default** — 3 rounds were valuable for this feature but may not be warranted for simpler features.
3. **Investigate persistent MCP DB locks** — The entity DB was locked for the entire session. This suggests an MCP server is holding a transaction open indefinitely.
