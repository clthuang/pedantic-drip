# Retrospective: 056-sqlite-write-contention-fix

## Summary
Fixed SQLite multi-process write contention in the workflow engine. Added atomic transactions, retry with backoff, PID monitoring, and increased busy_timeout. Originated from RCA during feature 055 when workflow DB errors blocked phase transitions.

## Metrics
- **Phases:** specify (3 iter) → design (3 iter) → plan (2 iter) → tasks (1 iter) → implement (1 iter)
- **Total review iterations:** 10 across pre-implementation phases, 1 for implementation (all 3 reviewers approved first pass)
- **Files changed:** 5 (database.py, workflow_state_server.py, entity_server.py, test_database.py, test_workflow_state_server.py)
- **Lines delta:** +265 / -21
- **Tests added:** 19 (5 db-layer, 11 MCP-layer, 3 PID)
- **Total tests passing:** 2,041

## What Went Well
1. **RCA-driven development** — the feature was precisely scoped from a thorough root cause analysis, avoiding wasted effort on symptoms
2. **Spec-reviewer caught critical design flaw** — internal commit() calls in database.py would defeat the transaction wrapper; caught at spec review, not implementation
3. **Design-reviewer caught shared-DB assumption** — the engine uses the same EntityDatabase instance (not its own connection), requiring engine calls inside the transaction
4. **All 3 implementation reviewers approved on first pass** — heavy upfront review investment (10 iterations across specify/design/plan) produced clean implementation
5. **Ironic dogfooding** — the very bug being fixed (DB errors) blocked the workflow engine during development, validating the RCA findings in real-time

## What Could Improve
1. **AC-2 grep count was wrong** — spec said expect 1 `self._conn.commit()` but actual is 2 (forgot _commit() helper itself contains the call). Caught by implementation reviewer.
2. **Workflow DB errors during development** — had to manually update .meta.json via bash multiple times because the MCP workflow tools couldn't complete phase transitions (the bug we were fixing)

## Key Decisions
- **TD-1:** transaction() as new method alongside existing begin_immediate() (different use cases)
- **TD-2:** _with_retry stacks inside _with_error_handling (retry before terminal conversion)
- **TD-3:** Only "locked" errors retried, not "SQL logic error" (too broad)
- **TD-4:** ROLLBACK failure suppressed (original exception preserved)
- **TD-5:** _project_meta_json outside transaction (filesystem after DB commit)
