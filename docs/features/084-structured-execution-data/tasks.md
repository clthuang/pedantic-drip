# Tasks: Structured Workflow Execution Data (Feature 084)

Each task is 5-15 minutes. All tasks within a phase are serialized (shared test files).

---

## Phase 0: Baselines

- [ ] **0.1** Capture baseline counts to `agent_sandbox/084-baselines.txt`.
  - Run: `./validate.sh 2>&1 | tail -5` → extract warning count.
  - Run: `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ --collect-only -q 2>&1 | tail -3` → entity test count.
  - Run: `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py --collect-only -q 2>&1 | tail -3` → workflow test count.
  - Done: baselines file has 3 counts.
  - Size: 5 min.

---

## Phase 1: database.py (migration 10 + methods)

- [ ] **1.1** Write migration 10 + insert/query method tests [TDD red].
  - Create `plugins/pd/hooks/lib/entity_registry/test_phase_events.py` (NEW file).
  - `TestMigration10`:
    - AC-1: after migration, `SELECT name FROM sqlite_master WHERE type='table' AND name='phase_events'` → 1 row.
    - AC-2: `PRAGMA table_info(phase_events)` → 12 columns with correct names/types.
    - AC-3: `SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='phase_events'` → 3 indexes.
    - AC-8: seed 3 entities with metadata containing phase_timing dicts BEFORE migration runs. After migration, `SELECT COUNT(*) FROM phase_events WHERE source='backfill'` → N rows matching seeded phases.
    - AC-9: seed 1 entity with `metadata='not json'`. Migration completes without error. 0 rows for that entity.
    - AC-10: backfill rows have `source='backfill'`.
    - AC-18: calling `_migrate()` twice at version 10 produces no duplicate rows.
  - `TestInsertPhaseEvent`: verify INSERT with all columns, verify None return.
  - `TestQueryPhaseEvents`: verify filter by type_id, project_id, phase, event_type; verify limit; verify ORDER BY.
  - Done: ~12 red tests.
  - Size: 15 min.

- [ ] **1.2** Implement migration 10 [TDD green].
  - Add `_migration_10_phase_events(conn)` to `database.py` per design I-1.
  - Add `10: _migration_10_phase_events` to MIGRATIONS dict.
  - CREATE TABLE + 3 composite indexes + backfill loop + schema_version upsert with `ON CONFLICT(key) DO UPDATE SET`.
  - Backfill: parse metadata JSON, INSERT started/completed/skipped/backward events with `source='backfill'`. Skip malformed JSON with stderr warning.
  - Done: AC-1/2/3/8/9/10/18 tests pass.
  - Size: 15 min. `requires: 1.1`

- [ ] **1.3** Implement `EntityDatabase.insert_phase_event` [TDD green].
  - Per design I-2. Keyword-only params. Simple INSERT. Returns None.
  - Done: TestInsertPhaseEvent passes.
  - Size: 10 min. `requires: 1.2`

- [ ] **1.4** Implement `EntityDatabase.query_phase_events` [TDD green].
  - Per design I-3. Dynamic WHERE with parameterized filters. `min(limit, 500)` cap. ORDER BY timestamp DESC. Returns `[dict(r) for r in rows]`.
  - Done: TestQueryPhaseEvents passes. All existing entity_registry tests pass unchanged.
  - Size: 10 min. `requires: 1.3`

---

## Phase 2: workflow_state_server.py (dual-write + MCP tools)

- [ ] **2.1** Write dual-write + resilience tests [TDD red].
  - Add to `test_workflow_state_server.py`:
  - `TestPhaseEventsDualWrite`:
    - AC-4: call `transition_phase`. Query `phase_events` for started event → 1 row.
    - AC-5: call `complete_phase` with iterations=3. Query for completed event → `iterations=3`.
    - AC-6: call `transition_phase` with `skipped_phases='["brainstorm"]'`. Query for skipped event → 1 row.
    - AC-16: monkeypatch `insert_phase_event` to raise. Call `transition_phase`. Assert: transition succeeds, metadata updated, stderr warning emitted.
    - AC-19: after `complete_phase`, read entity metadata JSON — `phase_timing` dict still present.
  - Done: 5 red tests.
  - Size: 15 min. `requires: 1.4`

- [ ] **2.2** Implement dual-write [TDD green].
  - In `_process_transition_phase`: refactor line ~617 `_iso_now()` to `ts = _iso_now(); phase_timing[...]["started"] = ts`. Add try/except `db.insert_phase_event(...)` for started + skipped events.
  - In `_process_complete_phase`: refactor line ~763 `_iso_now()` to `ts = _iso_now(); phase_timing[...]["completed"] = ts`. Add try/except `db.insert_phase_event(...)` for completed event.
  - Done: AC-4/5/6/16/19 tests pass.
  - Size: 15 min. `requires: 2.1`

- [ ] **2.3** Write `record_backward_event` test [TDD red].
  - AC-7: call `record_backward_event(type_id="feature:test", source_phase="design", target_phase="specify", reason="scope gap", project_id="test-proj")`. Query for backward event → `phase='design'`, `backward_target='specify'`, `backward_reason='scope gap'`.
  - Done: 1 red test.
  - Size: 10 min. `requires: 2.2`

- [ ] **2.4** Implement `record_backward_event` MCP tool [TDD green].
  - Per design I-6. `@mcp.tool()` decorator. Accepts `project_id` as parameter (not resolved from entity). Calls `db.insert_phase_event(event_type="backward", ...)`.
  - Done: AC-7 test passes.
  - Size: 10 min. `requires: 2.3`

- [ ] **2.5** Wire `record_backward_event` into workflow-transitions skill.
  - Edit `plugins/pd/skills/workflow-transitions/SKILL.md`: in the backward-transition handler (after calling `transition_phase` and `update_entity` for backward_history), add instruction for the orchestrator to call `record_backward_event(type_id, source_phase, target_phase, reason, project_id)`.
  - The skill already has all these values in scope from the reviewer response parsing.
  - Done: skill file updated; `grep -c "record_backward_event" plugins/pd/skills/workflow-transitions/SKILL.md` returns ≥1.
  - Size: 10 min. `requires: 2.4`

- [ ] **2.6** Write `query_phase_analytics` tests [TDD red].
  - `TestQueryPhaseAnalytics`:
    - AC-11: seed events with known timestamps, call `phase_duration` → correct duration_seconds.
    - AC-11b: seed 2 started + 2 completed for same feature+phase (s1<c1<s2<c2). Call phase_duration → 2 rows with correct pairing.
    - AC-12: call `iteration_summary` → iterations counts sorted descending.
    - AC-13: call `backward_frequency` → per-phase backward counts.
    - AC-14: call `raw_events` with limit=10 → ≤10 rows.
    - AC-15: call with `project_id="P002"` filter → only P002 events.
  - Done: 6 red tests.
  - Size: 15 min. `requires: 2.4`

- [ ] **2.7** Implement `query_phase_analytics` + `_compute_durations` [TDD green].
  - Per design I-7. 4 query types. Z-normalization: `.replace("Z", "+00:00")` before `fromisoformat()`.
  - `_compute_durations`: group by (type_id, phase), sort by timestamp, pair Nth started with Nth completed.
  - Done: AC-11/11b/12/13/14/15 tests pass. All existing workflow tests pass (AC-17).
  - Size: 15 min. `requires: 2.6`

---

## Phase 3: Docs + verification

- [ ] **3.1** Update `README_FOR_DEV.md` (AC-20).
  - Add brief note about `phase_events` table and `query_phase_analytics` tool after the entity registry section.
  - Done: `grep -c "phase_events" README_FOR_DEV.md` ≥ 1.
  - Size: 5 min. `requires: 2.7`

- [ ] **3.2** Run full test suites.
  - Entity registry: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v` → all green, count ≥ baseline + ~10.
  - Workflow state: `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v` → all green, count ≥ baseline + ~10.
  - Done: both suites green.
  - Size: 5 min. `requires: 3.1`

- [ ] **3.3** Run `./validate.sh` — 0 errors, warnings ≤ baseline.
  - Done: clean.
  - Size: 5 min. `requires: 3.2`

- [ ] **3.4** Delete `agent_sandbox/084-baselines.txt`.
  - Done: file removed.
  - Size: 1 min. `requires: 3.3`

---

## Summary

**Task count:** 16 tasks across 4 phases.
**Estimated total:** ~3-4 hours of focused implementation.
**Serialization:** all tasks within each phase are serial (shared test files).
**AC coverage:** AC-1..AC-20 + AC-11b all assigned to tasks.
