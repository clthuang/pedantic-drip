# Tasks: Memory Feedback Loop Hardening

**Feature:** 076-memory-feedback-loop-hardening
**Plan:** plan.md
**Created:** 2026-04-03

## Stage 1: Core MCP Changes

### Task 1.1: Write test for store_memory source parameter passthrough [TDD: test first]
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Add test: call `_process_store_memory()` with `source="retro"`, assert DB entry has `source="retro"`. Add test: call without source, assert default `"session-capture"`.
**Done:** Tests written and fail (source param not yet accepted)
**Depends on:** none

### Task 1.2: Add source parameter to store_memory MCP [TDD: make green]
**File:** `plugins/pd/mcp/memory_server.py`
**Change:** (1) Add `source: str = "session-capture"` to `store_memory()` signature at line 347. (2) Add `source: str = "session-capture"` to `_process_store_memory()` signature at line 42. (3) Remove hardcoded `source = "session-capture"` at line 81. (4) Pass `source` from `store_memory()` → `_process_store_memory()` → `db.upsert_entry()`.
**Done:** Task 1.1 tests pass; existing tests still pass
**Depends on:** Task 1.1

### Task 1.3: Write tests for Tier 1 min-length gate [TDD: test first]
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Add test: description "short" (5 chars) → rejected with "description too short". Add test: description of exactly 20 chars → accepted. Add test: description of 19 chars → rejected.
**Done:** Tests written and fail (gate not implemented)
**Depends on:** none

### Task 1.4: Write tests for Tier 1 near-duplicate gate [TDD: test first]
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Add test: store entry A, then store entry B with cosine > 0.95 to A but different name → rejected with "near-duplicate". Add test: same-name entry at cosine > 0.95 → falls through to merge (not rejected). Add test: embedding unavailable → skip gate, allow entry.
**Done:** Tests written and fail (gate not implemented)
**Depends on:** none

### Task 1.5: Write test for constitution write-protection [TDD: test first]
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Add test: `store_memory(category="constitution")` → rejected with "constitution entries are import-only".
**Done:** Test written and fails
**Depends on:** none

### Task 1.6: Implement Tier 1 gates in _process_store_memory [TDD: make green]
**File:** `plugins/pd/mcp/memory_server.py`
**Change:** In `_process_store_memory`, add gates in this exact order after existing `if category not in VALID_CATEGORIES` check (line 66):
1. Constitution write-protection: `if category == "constitution": return "Entry rejected: constitution entries are import-only (edit docs/knowledge-bank/constitution.md directly)"` — goes right after VALID_CATEGORIES check (requires Task 3.2 to add "constitution" to VALID_CATEGORIES first, otherwise it's caught by the existing check).
2. Min-length: `if len(description) < 20: return "Entry rejected: description too short (min 20 chars)"`
3. After embedding computation: near-duplicate at 0.95: `dup = check_duplicate(embedding, db, threshold=0.95)` → if `dup.is_duplicate`: look up name via `db.get_entry(dup.existing_entry_id)` → if name differs: reject. DedupResult fields: `is_duplicate` (bool), `existing_entry_id` (str), `similarity` (float).
4. Skip near-duplicate if embedding is None (log warning to stderr).
**Done:** Tasks 1.3, 1.4, 1.5 tests pass; existing dedup tests still pass
**Depends on:** Tasks 1.3, 1.4, 1.5, 3.2 (constitution must be in VALID_CATEGORIES)

### Task 1.7: Update ranking weight test assertion [TDD: test first]
**File:** `plugins/pd/hooks/lib/semantic_memory/test_ranking.py`
**Change:** At line 529-531, locate the existing weight constants `W_OBS, W_CONF, W_REC, W_RECALL, W_INF = 0.25, 0.15, 0.25, 0.15, 0.20`. Update to `W_OBS, W_CONF, W_REC, W_RECALL, W_INF = 0.30, 0.15, 0.35, 0.15, 0.05`. Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_ranking.py -v` — expect failures (old weights in production code).
**Done:** Test constants updated; test suite shows failing assertions referencing new weight values
**Depends on:** none

### Task 1.8: Update ranking weights [TDD: make green]
**File:** `plugins/pd/hooks/lib/semantic_memory/ranking.py`
**Change:** Line 242 (docstring) and line 252 (formula): change to `0.30*obs + 0.15*confidence + 0.35*recency + 0.15*recall + 0.05*influence`.
**Done:** Task 1.7 test passes; existing ranking tests updated
**Depends on:** Task 1.7

## Stage 2: New MCP Tool

### Task 2.1: Write tests for record_influence_by_content [TDD: test first]
**File:** `plugins/pd/mcp/test_memory_server.py`
**Change:** Add tests: (1) output text matching an injected entry → influence recorded, (2) output text not matching → no influence, (3) empty injected list → no error, (4) embedding unavailable → graceful degradation with warning, (5) chunks < 20 chars filtered out.
**Done:** Tests written and fail (tool not implemented)
**Depends on:** none

### Task 2.2: Implement record_influence_by_content MCP tool [TDD: make green]
**File:** `plugins/pd/mcp/memory_server.py`
**Change:** Add new `record_influence_by_content` MCP tool. Steps in order:
1. If `len(subagent_output_text) > 2000`: take last 2000 chars (conclusion is at end)
2. Split truncated text by `\n\n` into paragraphs
3. Filter paragraphs shorter than 20 chars
4. Compute embedding per paragraph via `provider.embed(chunk, task_type="query")`
5. For each injected entry: look up stored embedding via `db.find_entry_by_name(name)`
6. For each entry × chunk pair: compute cosine similarity; take max per entry across all chunks
7. Record influence for entries where max similarity >= threshold
8. Return JSON: `{"matched": [...], "skipped": N}`
**Done:** Task 2.1 tests pass
**Depends on:** Task 2.1

## Stage 3: Category + Config Fixes

### Task 3.1: Write test for constitution import [TDD: test first]
**File:** `plugins/pd/hooks/lib/semantic_memory/test_importer.py`
**Change:** Add test using the same markdown fixture format as existing anti-patterns.md tests. Constitution.md uses heading-based entry format (see `importer.py:parse_markdown_file` — entries delimited by `### ` headings with body text below). Create a tmp constitution.md with 2 test entries, call `import_all()`, assert entries appear in DB with `category="constitution"`. Add test: `search_memory(category="constitution")` returns matching results.
**Done:** Tests written and fail (category not in CATEGORIES)
**Depends on:** none

### Task 3.2: Add constitution to import + injection categories [TDD: make green]
**File:** `plugins/pd/hooks/lib/semantic_memory/importer.py`, `injector.py`, `__init__.py`
**Change:** importer.py:22 — add `("constitution.md", "constitution")` to CATEGORIES. injector.py:34 — add `"constitution"` to end of CATEGORY_ORDER. injector.py:38 — add `"constitution": "### Core Principles"` to CATEGORY_HEADERS. __init__.py:8 — add `"constitution"` to VALID_CATEGORIES frozenset.
**Done:** Task 3.1 tests pass
**Depends on:** Task 3.1

### Task 3.3: Align injection limit default
**File:** `plugins/pd/hooks/session-start.sh`
**Change:** Line 421: change fallback `"20"` to `"15"`. Line 422: change regex fallback `limit="20"` to `limit="15"`.
**Done:** Both fallbacks read 15; matches config.py default
**Depends on:** none

## Stage 4: Instruction Text Changes

### Task 4.1: Add reviewer_feedback_summary to Phase Context injection
**File:** `plugins/pd/skills/workflow-transitions/SKILL.md`
**Change:** In Step 1b Prior Phase Summaries format, add `Reviewer feedback: {reviewer_feedback_summary}` line after `Artifacts:` (conditional: only when non-null/non-empty). Update omission note at line 109 to: "included during backward travel, omitted during forward travel."
**Done:** Phase Context template includes reviewer feedback line; note updated
**Depends on:** none

### Task 4.2: Lower review learnings threshold to 1+ in specify.md
**File:** `plugins/pd/commands/specify.md`
**Change:** Lines 353,358: replace "2+ iterations" with "1+ iterations". Add two-path template (1 iter = direct store confidence="low", 2+ = grouped patterns).
**Done:** Trigger text updated; two-path logic present
**Depends on:** none

### Task 4.3: Lower review learnings threshold to 1+ in design.md
**File:** `plugins/pd/commands/design.md`
**Change:** Lines 614,619: same change as Task 4.2.
**Done:** Trigger text updated; two-path logic present
**Depends on:** none

### Task 4.4: Lower review learnings threshold to 1+ in create-plan.md
**File:** `plugins/pd/commands/create-plan.md`
**Change:** Lines 499,504: same change as Task 4.2.
**Done:** Trigger text updated; two-path logic present
**Depends on:** none

### Task 4.5: Lower review learnings threshold to 1+ in implement.md
**File:** `plugins/pd/commands/implement.md`
**Change:** Lines 1228,1233: same change as Task 4.2.
**Done:** Trigger text updated; two-path logic present
**Depends on:** none

### Task 4.6: Add source="retro" to retrospecting store_memory call
**File:** `plugins/pd/skills/retrospecting/SKILL.md`
**Change:** In Step 3a store_memory call, add `source="retro"` parameter.
**Done:** store_memory call includes source="retro"
**Depends on:** Task 1.2 (source param must exist)

### Task 4.7: Add source="manual" to remember.md store_memory call
**File:** `plugins/pd/commands/remember.md`
**Change:** In store_memory call (line 28), add `source="manual"` parameter.
**Done:** store_memory call includes source="manual"
**Depends on:** Task 1.2 (source param must exist)

### Task 4.8: Migrate influence tracking in specify.md (2 locations)
**File:** `plugins/pd/commands/specify.md`
**Change:** Replace both post-dispatch influence tracking blocks with `record_influence_by_content` call pattern per design I4.
**Done:** `grep -c 'record_influence(' specify.md` returns 0; `grep -c 'record_influence_by_content' specify.md` returns 2
**Depends on:** Task 2.2 (tool must exist)

### Task 4.9: Migrate influence tracking in design.md (2 locations)
**File:** `plugins/pd/commands/design.md`
**Change:** Same as Task 4.8 but for design.md.
**Done:** `grep` counts: record_influence=0, record_influence_by_content=2
**Depends on:** Task 2.2

### Task 4.10: Migrate influence tracking in create-plan.md (3 locations)
**File:** `plugins/pd/commands/create-plan.md`
**Change:** Same as Task 4.8 but for create-plan.md (3 locations).
**Done:** `grep` counts: record_influence=0, record_influence_by_content=3
**Depends on:** Task 2.2

### Task 4.11: Migrate influence tracking in implement.md (7 locations)
**File:** `plugins/pd/commands/implement.md`
**Change:** Same as Task 4.8 but for implement.md (7 locations).
**Done:** `grep` counts: record_influence=0, record_influence_by_content=7
**Depends on:** Task 2.2

## Stage 5: Testing & Verification

### Task 5.1: Run full regression test suite
**Change:** Run affected test suites (no entity_registry — this feature doesn't touch it):
```bash
# Memory server tests
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v
# Semantic memory tests (ranking, importer, injector, database)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v
# Memory server bootstrap
bash plugins/pd/mcp/test_run_memory_server.sh
```
Also verify session-start.sh config change: `grep '"15"' plugins/pd/hooks/session-start.sh` returns 2 matches at lines 421-422.
**Done:** All test suites pass with zero regressions; session-start.sh defaults verified
**Depends on:** All Tasks 1.x-4.x

### Task 5.2: Verify influence tracking migration completeness
**Change:** Run: `grep -c 'record_influence(' plugins/pd/commands/specify.md plugins/pd/commands/design.md plugins/pd/commands/create-plan.md plugins/pd/commands/implement.md`. All counts should be 0. Run: `grep -c 'record_influence_by_content' {same files}`. Counts should be specify:2, design:2, create-plan:3, implement:7.
**Done:** All counts match expected values
**Depends on:** Tasks 4.8-4.11

## Task Dependencies

```
1.1 → 1.2 (TDD: test then source param)
1.3, 1.4, 1.5, 3.2 → 1.6 (TDD: tests then gates; 3.2 adds constitution to VALID_CATEGORIES first)
1.7 → 1.8 (TDD: test then weights)
2.1 → 2.2 (TDD: test then new tool)
3.1 → 3.2 (TDD: test then categories)
1.2 → 4.6, 4.7 (source param must exist)
2.2 → 4.8, 4.9, 4.10, 4.11 (new tool must exist)
All → 5.1 (regression)
4.8-4.11 → 5.2 (verification)

Parallel groups:
- Stage 1 tasks 1.1-1.5, 1.7-1.8 and Stage 2 (2.1-2.2) and Stage 3 (3.1-3.3) can run in parallel
- Task 1.6 depends on 3.2 — must run after 3.2 completes (cross-stage dependency)
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
