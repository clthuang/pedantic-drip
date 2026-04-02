# Tasks: Memory Feedback Loop Hardening

**Feature:** 076-memory-feedback-loop-hardening
**Plan:** plan.md
**Created:** 2026-04-03

## Stage 1: Core MCP Changes

### Task 1.1: Write test for store_memory source parameter passthrough [TDD: test first]
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Add test: call `_process_store_memory()` with `source="retro"`, assert DB entry has `source="retro"`. Add test: call without source, assert default `"session-capture"`.
**Time:** 5 min
**Done:** Tests written and fail (source param not yet accepted)
**Depends on:** none

### Task 1.2: Add source parameter to store_memory MCP [TDD: make green]
**File:** `plugins/pd/mcp/memory_server.py`
**Change:** Add `source: str = "session-capture"` to `store_memory()` signature (line 347). Remove hardcoded `source = "session-capture"` at line 81. Pass `source` through to `_process_store_memory()`. Pass to `db.upsert_entry()`.
**Time:** 10 min
**Done:** Task 1.1 tests pass; existing tests still pass
**Depends on:** Task 1.1

### Task 1.3: Write tests for Tier 1 min-length gate [TDD: test first]
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Add test: description "short" (5 chars) → rejected with "description too short". Add test: description of exactly 20 chars → accepted. Add test: description of 19 chars → rejected.
**Time:** 5 min
**Done:** Tests written and fail (gate not implemented)
**Depends on:** none

### Task 1.4: Write tests for Tier 1 near-duplicate gate [TDD: test first]
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Add test: store entry A, then store entry B with cosine > 0.95 to A but different name → rejected with "near-duplicate". Add test: same-name entry at cosine > 0.95 → falls through to merge (not rejected). Add test: embedding unavailable → skip gate, allow entry.
**Time:** 10 min
**Done:** Tests written and fail (gate not implemented)
**Depends on:** none

### Task 1.5: Write test for constitution write-protection [TDD: test first]
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Add test: `store_memory(category="constitution")` → rejected with "constitution entries are import-only".
**Time:** 5 min
**Done:** Test written and fails
**Depends on:** none

### Task 1.6: Implement Tier 1 gates in _process_store_memory [TDD: make green]
**File:** `plugins/pd/mcp/memory_server.py`
**Change:** In `_process_store_memory`, after existing category validation: add constitution write-protection check. Before dedup: add min-length check (len(description) < 20 → reject). After embedding computation: add near-duplicate check (check_duplicate at 0.95, get_entry for name lookup, reject if name differs). Skip near-duplicate if embedding is None (log warning).
**Time:** 15 min
**Done:** Tasks 1.3, 1.4, 1.5 tests pass; existing dedup tests still pass
**Depends on:** Tasks 1.3, 1.4, 1.5

### Task 1.7: Write test for ranking weight change [TDD: test first]
**File:** `plugins/pd/hooks/lib/semantic_memory/test_ranking.py` or relevant test file
**Change:** Add test asserting prominence formula uses weights 0.30/0.15/0.35/0.15/0.05. Run test — expect failure (old weights).
**Time:** 5 min
**Done:** Test written and fails
**Depends on:** none

### Task 1.8: Update ranking weights [TDD: make green]
**File:** `plugins/pd/hooks/lib/semantic_memory/ranking.py`
**Change:** Line 242 (docstring) and line 252 (formula): change to `0.30*obs + 0.15*confidence + 0.35*recency + 0.15*recall + 0.05*influence`.
**Time:** 5 min
**Done:** Task 1.7 test passes; existing ranking tests updated
**Depends on:** Task 1.7

## Stage 2: New MCP Tool

### Task 2.1: Write tests for record_influence_by_content [TDD: test first]
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Add tests: (1) output text matching an injected entry → influence recorded, (2) output text not matching → no influence, (3) empty injected list → no error, (4) embedding unavailable → graceful degradation with warning, (5) chunks < 20 chars filtered out.
**Time:** 15 min
**Done:** Tests written and fail (tool not implemented)
**Depends on:** none

### Task 2.2: Implement record_influence_by_content MCP tool [TDD: make green]
**File:** `plugins/pd/mcp/memory_server.py`
**Change:** Add new `record_influence_by_content` MCP tool. Implementation: truncate input to last 2000 chars, chunk by `\n\n`, filter chunks < 20 chars, compute per-chunk embeddings, compare against stored entry embeddings, record influence for matches >= threshold (default 0.70).
**Time:** 20 min
**Done:** Task 2.1 tests pass
**Depends on:** Task 2.1

## Stage 3: Category + Config Fixes

### Task 3.1: Write test for constitution import [TDD: test first]
**File:** `plugins/pd/hooks/lib/semantic_memory/test_importer.py` (or test_memory_server.py)
**Change:** Add test: create constitution.md with entries, run import_all(), assert entries appear in DB with category="constitution". Add test: search_memory with category="constitution" returns results.
**Time:** 10 min
**Done:** Tests written and fail (category not registered)
**Depends on:** none

### Task 3.2: Add constitution to import + injection categories [TDD: make green]
**File:** `plugins/pd/hooks/lib/semantic_memory/importer.py`, `injector.py`, `__init__.py`
**Change:** importer.py:22 — add `("constitution.md", "constitution")` to CATEGORIES. injector.py:34 — add `"constitution"` to end of CATEGORY_ORDER. injector.py:38 — add `"constitution": "### Core Principles"` to CATEGORY_HEADERS. __init__.py:8 — add `"constitution"` to VALID_CATEGORIES frozenset.
**Time:** 5 min
**Done:** Task 3.1 tests pass
**Depends on:** Task 3.1

### Task 3.3: Align injection limit default
**File:** `plugins/pd/hooks/session-start.sh`
**Change:** Line 421: change fallback `"20"` to `"15"`. Line 422: change regex fallback `limit="20"` to `limit="15"`.
**Time:** 5 min
**Done:** Both fallbacks read 15; matches config.py default
**Depends on:** none

## Stage 4: Instruction Text Changes

### Task 4.1: Add reviewer_feedback_summary to Phase Context injection
**File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
**Change:** In Step 1b Prior Phase Summaries format, add `Reviewer feedback: {reviewer_feedback_summary}` line after `Artifacts:` (conditional: only when non-null/non-empty). Update omission note at line 109 to: "included during backward travel, omitted during forward travel."
**Time:** 5 min
**Done:** Phase Context template includes reviewer feedback line; note updated
**Depends on:** none

### Task 4.2: Lower review learnings threshold to 1+ in specify.md
**File:** `plugins/pd/commands/specify.md`
**Change:** Lines 353,358: replace "2+ iterations" with "1+ iterations". Add two-path template (1 iter = direct store confidence="low", 2+ = grouped patterns).
**Time:** 5 min
**Done:** Trigger text updated; two-path logic present
**Depends on:** none

### Task 4.3: Lower review learnings threshold to 1+ in design.md
**File:** `plugins/pd/commands/design.md`
**Change:** Lines 614,619: same change as Task 4.2.
**Time:** 5 min
**Done:** Trigger text updated; two-path logic present
**Depends on:** none

### Task 4.4: Lower review learnings threshold to 1+ in create-plan.md
**File:** `plugins/pd/commands/create-plan.md`
**Change:** Lines 499,504: same change as Task 4.2.
**Time:** 5 min
**Done:** Trigger text updated; two-path logic present
**Depends on:** none

### Task 4.5: Lower review learnings threshold to 1+ in implement.md
**File:** `plugins/pd/commands/implement.md`
**Change:** Lines 1228,1233: same change as Task 4.2.
**Time:** 5 min
**Done:** Trigger text updated; two-path logic present
**Depends on:** none

### Task 4.6: Add source="retro" to retrospecting store_memory call
**File:** `plugins/pd/skills/retrospecting/SKILL.md`
**Change:** In Step 3a store_memory call, add `source="retro"` parameter.
**Time:** 5 min
**Done:** store_memory call includes source="retro"
**Depends on:** Task 1.2 (source param must exist)

### Task 4.7: Add source="manual" to remember.md store_memory call
**File:** `plugins/pd/commands/remember.md`
**Change:** In store_memory call (line 28), add `source="manual"` parameter.
**Time:** 5 min
**Done:** store_memory call includes source="manual"
**Depends on:** Task 1.2 (source param must exist)

### Task 4.8: Migrate influence tracking in specify.md (2 locations)
**File:** `plugins/pd/commands/specify.md`
**Change:** Replace both post-dispatch influence tracking blocks with `record_influence_by_content` call pattern per design I4.
**Time:** 5 min
**Done:** `grep -c 'record_influence(' specify.md` returns 0; `grep -c 'record_influence_by_content' specify.md` returns 2
**Depends on:** Task 2.2 (tool must exist)

### Task 4.9: Migrate influence tracking in design.md (2 locations)
**File:** `plugins/pd/commands/design.md`
**Change:** Same as Task 4.8 but for design.md.
**Time:** 5 min
**Done:** `grep` counts: record_influence=0, record_influence_by_content=2
**Depends on:** Task 2.2

### Task 4.10: Migrate influence tracking in create-plan.md (3 locations)
**File:** `plugins/pd/commands/create-plan.md`
**Change:** Same as Task 4.8 but for create-plan.md (3 locations).
**Time:** 5 min
**Done:** `grep` counts: record_influence=0, record_influence_by_content=3
**Depends on:** Task 2.2

### Task 4.11: Migrate influence tracking in implement.md (7 locations)
**File:** `plugins/pd/commands/implement.md`
**Change:** Same as Task 4.8 but for implement.md (7 locations).
**Time:** 10 min
**Done:** `grep` counts: record_influence=0, record_influence_by_content=7
**Depends on:** Task 2.2

## Stage 5: Testing & Verification

### Task 5.1: Run full regression test suite
**Change:** Run all affected test suites:
```bash
# Memory server tests
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v
# Entity registry tests
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v
# Ranking tests (if separate file exists)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v
```
**Time:** 15 min
**Done:** All test suites pass with zero regressions
**Depends on:** All Tasks 1.x-4.x

### Task 5.2: Verify influence tracking migration completeness
**Change:** Run: `grep -c 'record_influence(' plugins/pd/commands/specify.md plugins/pd/commands/design.md plugins/pd/commands/create-plan.md plugins/pd/commands/implement.md`. All counts should be 0. Run: `grep -c 'record_influence_by_content' {same files}`. Counts should be specify:2, design:2, create-plan:3, implement:7.
**Time:** 5 min
**Done:** All counts match expected values
**Depends on:** Tasks 4.8-4.11

## Task Dependencies

```
1.1 → 1.2 (TDD: test then source param)
1.3, 1.4, 1.5 → 1.6 (TDD: tests then gates)
1.7 → 1.8 (TDD: test then weights)
2.1 → 2.2 (TDD: test then new tool)
3.1 → 3.2 (TDD: test then categories)
1.2 → 4.6, 4.7 (source param must exist)
2.2 → 4.8, 4.9, 4.10, 4.11 (new tool must exist)
All → 5.1 (regression)
4.8-4.11 → 5.2 (verification)

Parallel groups:
- Stage 1 tasks (1.1-1.8) and Stage 2 (2.1-2.2) and Stage 3 (3.1-3.3) can run in parallel
- Stage 4 tasks (4.1-4.5) are independent of each other
- Stage 4 tasks (4.6-4.7) depend on 1.2; (4.8-4.11) depend on 2.2
```

## Summary

| Stage | Tasks | Est. Time | Type |
|-------|-------|-----------|------|
| Stage 1: Core MCP | 1.1-1.8 | 60 min | TDD: Python code |
| Stage 2: New Tool | 2.1-2.2 | 35 min | TDD: Python code |
| Stage 3: Category/Config | 3.1-3.3 | 20 min | TDD + bash config |
| Stage 4: Instruction Text | 4.1-4.11 | 65 min | SKILL.md + command files |
| Stage 5: Verification | 5.1-5.2 | 20 min | Tests + grep |
| **Total** | **26 tasks** | **~3.3 hours** | |
