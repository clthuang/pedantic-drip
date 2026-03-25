# Tasks: Memory Feedback Loop (064)

## Phase 1: Parallel Implementation (C1, C2, C4)

### Group A: Confidence Auto-Promotion (C2)

#### Task 1.1: Add promotion config keys to DEFAULTS
- **File:** `plugins/pd/hooks/lib/semantic_memory/config.py`
- **Action:** Add 3 keys to DEFAULTS dict: `memory_auto_promote` (False), `memory_promote_low_threshold` (3), `memory_promote_medium_threshold` (5)
- **Done when:** `read_config()` returns all 3 keys with correct defaults when not set in pd.local.md
- **Depends on:** nothing

#### Task 1.2: Write promotion unit tests (RED)
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
- **Action:** Write 6 unit tests for merge_duplicate() promotion logic:
  1. `test_merge_duplicate_promotes_low_to_medium` — obs_count >= 3, confidence low, auto_promote=True → medium
  2. `test_merge_duplicate_promotes_medium_to_high_retro_only` — obs_count >= 5, confidence medium, source=retro → high
  3. `test_merge_duplicate_no_promote_when_disabled` — auto_promote=False → confidence unchanged
  4. `test_merge_duplicate_no_promote_import_source` — source=import → never promotes
  5. `test_merge_duplicate_no_promote_below_threshold` — obs_count < threshold → unchanged
  6. `test_merge_duplicate_already_at_target` — confidence already at target → no-op
- **Done when:** All 6 tests exist and FAIL (red) because promotion logic doesn't exist yet
- **Depends on:** Task 1.1

#### Task 1.3: Implement promotion logic in merge_duplicate() (GREEN)
- **File:** `plugins/pd/hooks/lib/semantic_memory/database.py`
- **Action:** Add `config: dict | None = None` parameter to `merge_duplicate()`. Insert conditional confidence UPDATE between the existing `UPDATE entries SET observation_count...` and `self._conn.commit()` within the same `BEGIN IMMEDIATE` transaction. Check `config.get("memory_auto_promote")` gate, then threshold checks. Skip promotion for source=import.
- **Done when:** All 6 unit tests from Task 1.2 pass (green)
- **Depends on:** Task 1.2

#### Task 1.4: Wire config through call site
- **File:** `plugins/pd/mcp/memory_server.py`
- **Action:** Change `db.merge_duplicate(dedup_result.existing_entry_id, keywords)` → `db.merge_duplicate(dedup_result.existing_entry_id, keywords, config=cfg)` in `_process_store_memory()`
- **Done when:** `cfg` (which includes promotion keys from DEFAULTS) reaches `merge_duplicate()`
- **Depends on:** Task 1.3

#### Task 1.5: Write MCP integration test
- **File:** `plugins/pd/mcp/test_memory_server.py`
- **Action:** Add `test_store_memory_dedup_triggers_promotion` — store entry, store duplicate with auto_promote config, verify confidence promoted
- **Done when:** Integration test passes end-to-end through MCP
- **Depends on:** Task 1.4

#### Task 1.5b: Write record_influence latency test
- **File:** `plugins/pd/mcp/test_memory_server.py`
- **Action:** Add `test_record_influence_latency` — call `db.record_influence()` 10 times, assert each call completes in <100ms using `time.perf_counter()`
- **Done when:** Test passes on local hardware
- **Depends on:** Task 1.4

#### Task 1.6: Verify existing ranking tests cover REQ-6
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_ranking.py`
- **Action:** Check if existing `TestInfluenceInProminence` and `TestRecallFrequency` test classes satisfy REQ-6 acceptance criteria (entries with non-zero influence_count/recall_count rank higher). If covered, map test names to REQ-6 ACs. If gaps, add: (1) `test_influence_count_affects_ranking` — two entries identical except influence_count=0 vs 5, assert 5 ranks first; (2) `test_recall_count_affects_ranking` — same pattern with recall_count.
- **Done when:** Either existing test names mapped to REQ-6 ACs OR both new tests pass
- **Depends on:** nothing

### Group B: Legacy Path Deprecation (C4)

#### Task 2.1: Write deprecation warning test (RED)
- **File:** `plugins/pd/hooks/tests/test-deprecation-warning.sh` (new script)
- **Action:** Create a Bash test script that sources session-start.sh, sets `memory_semantic_enabled=false`, calls `build_memory_context()`, and asserts the output contains the string `"memory_semantic_enabled=false is deprecated"` using grep. Run with: `bash plugins/pd/hooks/tests/test-deprecation-warning.sh`
- **Done when:** Test script exists and FAILS (legacy path has no warning yet)
- **Depends on:** nothing

#### Task 2.2: Implement legacy deprecation in session-start.sh (GREEN)
- **File:** `plugins/pd/hooks/session-start.sh`
- **Action:** In `build_memory_context()`, invert the `memory_semantic_enabled` conditional: check `= "false"` first with `echo "$deprecation_warning"` to stdout, else branch runs semantic injector (default)
- **Done when:** Test from 2.1 passes; setting `memory_semantic_enabled: false` produces warning in session output
- **Depends on:** Task 2.1

### Group C: Command File Memory Pattern (C1)

#### Task 3.1: Write structural validation tests (RED)
- **Files:** New test script (e.g., `plugins/pd/hooks/tests/test-memory-pattern.sh`)
- **Action:** Write 2 structural tests parametrized per command file:
  1. `test_memory_section_inside_prompt_blocks` — for EACH of 5 command files independently, verify `## Relevant Engineering Memory` appears between `prompt: |` and the next block-closing marker within each eligible dispatch block. Per-file pass/fail allows incremental validation.
  2. `test_influence_tracking_section_present` — verify `record_influence` string appears in EACH of 5 command files independently
- **Done when:** Both tests exist with per-file granularity and FAIL for all 5 files (memory section still outside prompt blocks, no record_influence)
- **Depends on:** nothing

#### Task 3.2: Apply memory pattern to specify.md (template)
- **File:** `plugins/pd/commands/specify.md`
- **Action:** For both dispatch blocks (spec-reviewer line 57, phase-reviewer line 198):
  - Move `## Relevant Engineering Memory` section inside `prompt: |` field
  - Add "Store entry names for influence tracking" instruction before dispatch
  - Add "Post-dispatch influence tracking" block after dispatch (case-insensitive substring match, non-blocking, dynamic feature_type_id)
- **Done when:** Structural validation test passes for specify.md
- **Depends on:** Task 3.1

#### Task 3.3: Verify template pattern on specify.md
- **Action:** Run structural validation tests on specify.md only. If fail, fix template before replicating.
- **Done when:** Both structural tests pass for specify.md
- **Depends on:** Task 3.2

#### Task 3.4: Replicate pattern to design.md
- **File:** `plugins/pd/commands/design.md`
- **Action:** Apply same pattern to 2 eligible blocks (design-reviewer line 246, phase-reviewer line 435). Skip research agents (codebase-explorer, internet-researcher).
- **Done when:** Per-file structural test passes for design.md
- **Depends on:** Task 3.3

#### Task 3.5: Replicate pattern to create-plan.md
- **File:** `plugins/pd/commands/create-plan.md`
- **Action:** Apply same pattern to 2 blocks (plan-reviewer line 63, phase-reviewer line 188)
- **Done when:** Per-file structural test passes for create-plan.md
- **Depends on:** Task 3.3

#### Task 3.6: Replicate pattern to create-tasks.md
- **File:** `plugins/pd/commands/create-tasks.md`
- **Action:** Apply same pattern to 2 blocks (task-reviewer line 63, phase-reviewer line 223)
- **Done when:** Per-file structural test passes for create-tasks.md
- **Depends on:** Task 3.3

#### Task 3.7: Replicate pattern to implement.md
- **File:** `plugins/pd/commands/implement.md`
- **Action:** Apply same pattern to 7 eligible blocks (fresh dispatches only, not resumed):
  - code-simplifier (line 74, category: patterns)
  - test-deepener (line 131, category: anti-patterns)
  - test-deepener (line 187, category: anti-patterns)
  - implementation-reviewer (line 306, category: anti-patterns)
  - code-quality-reviewer (line 482, category: anti-patterns)
  - security-reviewer (line 635, category: anti-patterns)
  - implementer (line 845, category: none)
- **Done when:** Per-file structural test passes for implement.md; all 7 blocks have memory inside prompt and influence tracking post-dispatch
- **Depends on:** Task 3.3

#### Task 3.8: Run full structural validation
- **Action:** Run both structural tests across all 5 command files simultaneously
- **Done when:** All tests green
- **Depends on:** Tasks 3.4, 3.5, 3.6, 3.7

## Phase 2: Migration

#### Task 4.1: Backup memory database
- **Action:** `cp ~/.claude/pd/memory/memory.db ~/.claude/pd/memory/memory.db.pre-064-backfill`
- **Done when:** Backup file exists
- **Depends on:** nothing

#### Task 4.2: Establish keyword quality baseline
- **Action:** Query 10 random entries with empty keywords before backfill: `sqlite3 ~/.claude/pd/memory/memory.db "SELECT name, description FROM entries WHERE keywords = '[]' ORDER BY RANDOM() LIMIT 10"`. Review descriptions to set expectations for what Tier 1 regex should produce.
- **Done when:** Baseline sample reviewed, expectations set for keyword quality
- **Depends on:** Task 4.1

#### Task 4.3: Run full keyword backfill
- **Action:** Run `semantic_memory.writer --action backfill-keywords --global-store ~/.claude/pd/memory`
- **Done when:** CLI completes without errors
- **Depends on:** Task 4.2

#### Task 4.4: Validate backfill results
- **Action:** Run SQL: `SELECT COUNT(*) * 100.0 / (SELECT COUNT(*) FROM entries) FROM entries WHERE keywords = '[]'`. Spot-check 10 random entries for keyword quality.
- **Done when:** Result < 10.0%; spot-check shows reasonable keywords
- **Depends on:** Task 4.3

## Phase 3: Integration Validation

#### Task 5.1: Run all test suites
- **Action:** Run:
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v`
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v`
  - Deprecation warning test from Task 2.1
  - Structural validation tests from Task 3.1
- **Done when:** All tests pass with zero failures
- **Depends on:** All Phase 1 and Phase 2 tasks

#### Task 5.2: NFR validation
- **Action:** Verify `record_influence` latency (< 100ms in unit test). Run 5 manual session starts, confirm all complete within 5s.
- **Done when:** Latency within budget; no session-start timeouts
- **Depends on:** Task 5.1

## Summary

- **Total tasks:** 22
- **Phases:** 3 (parallel implementation, migration, validation)
- **Parallel groups in Phase 1:** 3 (A: 7 tasks, B: 2 tasks, C: 8 tasks)
- **Critical path:** Group C (8 tasks) → Phase 2 (4 tasks) → Phase 3 (2 tasks)
