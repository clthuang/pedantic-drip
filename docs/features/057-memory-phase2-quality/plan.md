# Plan: Memory System Phase 2 — Quality & Influence

## Build Order

Three phases, ordered by dependency: Foundation → Integration → Wiring.

### Phase 1: Foundation (independent modules, no integration)

Build the three new modules in isolation with full test coverage before touching any existing code.

#### 1.1 Database Migration & merge_duplicate (C3 schema + C2 dependency)

**Why first:** Both dedup (C2) and influence (C3) depend on schema changes. Migration must land before any code that reads `influence_count` or writes to `influence_log`.

**Steps:**
1. Add `"influence_count"` to `_COLUMNS` list in database.py (line 246)
2. Write `_migration_4()` function (ALTER TABLE + CREATE TABLE influence_log) with `**_kwargs` signature
3. Add migration 4 to `MIGRATIONS` dict
4. Write `merge_duplicate()` method on `MemoryDatabase` (use `BEGIN IMMEDIATE` write-lock pattern, same as `upsert_entry()` — read existing keywords, UPDATE, COMMIT). Handle malformed existing keywords JSON with try/except, falling back to empty list.
5. Write tests in test_database.py:
   - Migration 4 creates column and table
   - Migration 4 is idempotent (re-run safe via schema_version check)
   - `merge_duplicate()` increments observation_count
   - `merge_duplicate()` unions keywords
   - `merge_duplicate()` preserves other fields unchanged
   - `merge_duplicate()` on non-existent ID raises ValueError
   - `merge_duplicate()` handles malformed existing keywords JSON gracefully

**Files:** `database.py`, `test_database.py`
**Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -v -k "migration_4 or merge_duplicate"`

#### 1.2 Keyword Extractor (C1)

**Why second:** Independent module, no DB dependencies. Backfill (1.4) and integration (2.1) depend on this.

**Steps:**
1. Create `keywords.py` with constants (`_KEYWORD_RE`, `_STOPWORDS`, `KEYWORD_PROMPT`)
2. Implement `_tier1_extract(text)` — tokenize, filter, stopword removal, multi-word extraction
3. Implement `_tier2_extract(name, description, reasoning, category)` — Gemini generateContent with JSON cleanup. Verify `google-genai` is in plugin pyproject.toml dependencies (used by embedding provider). Graceful degradation: if `GEMINI_API_KEY` absent or API call fails, return `[]`
4. Implement `extract_keywords()` orchestrator — Tier 1 first, Tier 2 fallback if < 3
5. Create `test_keywords.py`:
   - Tier 1 extracts keywords from technical text (>= 3 keywords)
   - Tier 1 returns empty for pure stopword text
   - Tier 1 handles hyphenated multi-word terms
   - Tier 2 fires only when Tier 1 < 3 (mock Gemini API)
   - Tier 2 handles malformed JSON (markdown fences, extra text)
   - Tier 2 validates keywords against regex + stopwords
   - Tier 2 gracefully degrades on API failure (returns [])
   - `extract_keywords()` returns Tier 1 result when >= 3
   - `extract_keywords()` combines Tier 1 + Tier 2 when Tier 1 < 3
   - AC-1: entry with "grep", "source files" produces domain-specific keywords
   - AC-2: 7/10 representative entries produce >= 3 keywords from Tier 1 alone

**Files:** `keywords.py`, `test_keywords.py`
**Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_keywords.py -v`

#### 1.3 Dedup Checker (C2)

**Why third:** Depends on 1.1 (merge_duplicate, get_all_embeddings). Independent of keywords.

**Steps:**
1. Create `dedup.py` with `DedupResult` dataclass and `check_duplicate()` function
2. Implement embedding comparison via matmul on normalized vectors
3. Implement None return guard (`get_all_embeddings()` returns `None`, not empty tuple, when no embeddings exist): `result = db.get_all_embeddings(); if result is None: return DedupResult(False, None, 0.0); ids, matrix = result`
4. Implement graceful degradation (numpy unavailable, provider error)
5. Create `test_dedup.py`:
   - Returns `is_duplicate=True` when similarity > threshold
   - Returns `is_duplicate=False` when similarity < threshold
   - Returns correct `existing_entry_id` via `ids[np.argmax(scores)]`
   - `get_all_embeddings()` returns None → `DedupResult(False, None, 0.0)`
   - Graceful degradation when no entries have embeddings
   - Threshold parameter is respected (0.90 vs 0.80 vs 0.95)
   - AC-6: near-duplicate detection at cosine > 0.90

**Files:** `dedup.py`, `test_dedup.py`
**Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_dedup.py -v`

#### 1.4 Config Extension (C5)

**Why here:** Quick change, needed by integration phase.

**Steps:**
1. Add `"memory_dedup_threshold": 0.90` to DEFAULTS in config.py
2. Add `memory_dedup_threshold: 0.90` to `.claude/pd.local.md` memory config block
3. Verify config read test passes (existing test infrastructure handles float coercion)

**Files:** `config.py`, `.claude/pd.local.md`
**Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v -k "config"`

### Phase 2: Integration (wire modules into existing code)

#### 2.1 Integrate keywords + dedup into store_memory (C1+C2 → memory_server.py)

**Why:** Core integration — connects the foundation modules to the hot path.

**Depends on:** 1.1, 1.2, 1.3, 1.4

**Steps:**
1. Import `extract_keywords` from `keywords.py` and `check_duplicate` from `dedup.py` into memory_server.py (note: `_embed_text_for_entry` already imported at line 27)
2. Refactor `_process_store_memory()`:
   a. Replace `keywords_json = "[]"` with `extract_keywords()` call
   b. Compute embedding EARLY, BEFORE dedup check (TD-3): build partial dict → `_embed_text_for_entry()` → `provider.embed(embed_text, task_type="document")`
   c. Add dedup check: if `check_duplicate(embedding_vec, db, threshold)` returns duplicate, call `db.merge_duplicate()` and return "Reinforced: ..."
   d. After dedup passes and entry is upserted, call `db.update_embedding(entry_id, embedding_vec.tobytes())` with the pre-computed vector. Remove the existing post-upsert embedding re-computation block (lines 103-115) — the vector was already computed in step 2b. Note: two-write approach (upsert + update_embedding) is intentional — upsert_entry() builds the entry dict from params without the embedding field, and update_embedding() is a separate BLOB write. Changing this to single-write would require modifying upsert_entry()'s entry dict construction, which is out of scope.
4. Update test_memory_server.py:
   - `store_memory` produces non-empty keywords
   - `store_memory` with near-duplicate returns "Reinforced:" message
   - `store_memory` with unique entry returns "Stored:" message
   - Keywords are stored in DB entry
   - Dedup gracefully degrades when embedding unavailable
   - AC-4: stored entry has 3-10 keyword elements

**Files:** `memory_server.py`, `test_memory_server.py`
**Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v`

#### 2.2 Add record_influence MCP tool (C3 → memory_server.py)

**Why:** Independent of 2.1, can be built in parallel.

**Depends on:** 1.1 (schema)

**Steps:**
1. Add database methods to `MemoryDatabase` in database.py (DB encapsulation — no raw SQL in memory_server.py):
   a. `find_entry_by_name(name: str) -> dict | None` — case-insensitive exact match, LIKE fallback with escaped wildcards
   b. `increment_influence(entry_id: str) -> None` — UPDATE influence_count + 1
   c. `log_influence(entry_id: str, agent_role: str, feature_type_id: str | None) -> None` — INSERT into influence_log
2. Add `record_influence` tool registration in memory_server.py (alongside `store_memory`, `search_memory`, `delete_memory`)
3. Implement `_process_record_influence()` using the database methods from step 1:
   a. `entry = db.find_entry_by_name(entry_name)`
   b. If entry: `db.increment_influence(entry["id"])`, `db.log_influence(entry["id"], agent_role, feature_type_id)`
   c. If no entry: return error string
5. Update test_memory_server.py and test_database.py:
   - `find_entry_by_name` exact match finds entry (test_database.py)
   - `find_entry_by_name` LIKE fallback finds entry (test_database.py)
   - `find_entry_by_name` returns None for non-existent entry (test_database.py)
   - SQL wildcard characters in entry_name are escaped (test_database.py)
   - `record_influence` MCP tool increments influence_count (test_memory_server.py)
   - `record_influence` MCP tool inserts influence_log row (test_memory_server.py)
   - `record_influence` MCP tool returns error for non-existent entry (test_memory_server.py)
   - AC-8: influence_count incremented after recording

**Files:** `database.py`, `memory_server.py`, `test_database.py`, `test_memory_server.py`
**Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v -k "influence"`

#### 2.3 Update prominence ranking (C3 → ranking.py)

**Why:** Independent of 2.1 and 2.2.

**Depends on:** 1.1 (influence_count column exists in entry dicts)

**Steps:**
1. **Audit first:** Read test_ranking.py and grep for old weight values (0.3, 0.2) to find ALL hardcoded prominence score assertions. Update them to use the new formula. Consider computing expected values from weight constants rather than hardcoding new magic numbers.
2. Add `_influence_score()` helper method (same pattern as `_recall_frequency()`)
3. Update `_prominence()` formula: `0.25*obs + 0.15*confidence + 0.25*recency + 0.15*recall + 0.20*influence`
4. Handle missing `influence_count` key gracefully (default 0 for pre-migration entries)
5. Update test_ranking.py (fix existing hardcoded scores AND add new tests):
   - Entries with higher influence_count rank higher
   - influence_count = 0 produces influence score = 0.0
   - influence_count >= 10 produces influence score = 1.0 (capped)
   - Missing influence_count key defaults to 0
   - AC-9: prominence ordering changes with influence signal

**Files:** `ranking.py`, `test_ranking.py`
**Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_ranking.py -v`

### Phase 3: Wiring (CLI + config + final validation)

#### 3.1 Backfill command (C4 → writer.py)

**Why last:** Uses keywords.py (1.2) in a batch context. Not on the hot path.

**Depends on:** 1.2

**Steps:**
1. Add `'backfill-keywords'` to `--action` choices in writer.py argparser
2. Implement `_backfill_keywords(db, config)`:
   a. Query entries where `keywords = '[]'`
   b. For each: `extract_keywords()` → `db.update_keywords()`
   c. Batch progress output every 50 entries
   d. Continue on per-entry failures (log and skip)
3. Wire action in `main()` dispatch
4. Add backfill tests to `test_keywords.py` (exercises extract_keywords in batch mode):
   - Backfill processes entries with empty keywords and populates them
   - Backfill skips entries that already have keywords
   - Backfill continues on per-entry failures
   - AC-5: `backfill-keywords` processes entries with empty keywords
   - Test DB must use `MemoryDatabase()` (auto-runs migrations including migration 4)

**Files:** `writer.py`, `test_keywords.py`
**Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_keywords.py -v -k "backfill"`

#### 3.2 Full regression test

**Why last:** Validates all changes work together.

**Steps:**
1. Run full semantic memory test suite
2. Run memory server tests
3. Run ranking tests
4. Verify AC-10: all existing tests pass

**Verify:**
```bash
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v
```

---

## Dependency Graph

```
1.1 Database Migration ──┬──► 2.1 Integrate store_memory ──► 3.2 Regression
                         │
1.2 Keywords ────────────┤
                         │
1.3 Dedup ───────────────┘

1.1 Database Migration ──┬──► 2.2 record_influence
                         │
                         └──► 2.3 Ranking update

1.2 Keywords ────────────────► 3.1 Backfill command

1.4 Config ──────────────────► 2.1 Integrate store_memory
```

**Parallelization opportunities:**
- Phase 1: 1.2 and 1.3 can run in parallel after 1.1 completes. 1.4 is independent.
- Phase 2: 2.1, 2.2, and 2.3 can all run in parallel (after their Phase 1 deps).
- Phase 3: 3.1 can run as soon as 1.2 is done. 3.2 runs last.

---

## Risk Mitigations

| Risk | Mitigation in Plan |
|------|--------------------|
| Migration breaks existing tests | 1.1 runs first with its own test validation before any integration |
| Embedding double-computation | TD-3 explicitly addressed in 2.1 step 3b — compute once, pass to both dedup and storage |
| Dedup false merges | 1.3 tests include threshold boundary cases; 1.4 makes threshold configurable |
| Tier 2 API unavailability | 1.2 tests include graceful degradation; backfill (3.1) can retry failures |
| _COLUMNS list stale | 1.1 step 1 updates _COLUMNS before any code reads influence_count |

---

## Acceptance Criteria Coverage

| AC | Plan Step | How Verified |
|----|-----------|--------------|
| AC-1 | 1.2 | Unit test with controlled input |
| AC-2 | 1.2 | Unit test with 10 representative entries |
| AC-3 | 1.2 | Unit test with mock API |
| AC-4 | 2.1 | Integration test: store_memory → read DB → assert keywords |
| AC-5 | 3.1 | Test on DB with empty-keyword entries |
| AC-6 | 1.3 + 2.1 | Unit test + integration test |
| AC-7 | 1.4 | Config read test |
| AC-8 | 2.2 | Unit test of MCP tool |
| AC-9 | 2.3 | Unit test comparing ranking with/without influence |
| AC-10 | 3.2 | Full regression suite |
