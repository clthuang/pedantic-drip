# Tasks: Memory System Phase 2 — Quality & Influence

## Phase 1: Foundation

### 1.1 Database Migration & merge_duplicate

#### Task 1.1.1: Add influence_count to _COLUMNS list
- **File:** `plugins/pd/hooks/lib/semantic_memory/database.py`
- **Action:** Add `"influence_count"` to `_COLUMNS` list (after `"created_timestamp_utc"`)
- **Done:** `_COLUMNS` has 19 elements, last is `"influence_count"`
- **Depends on:** none

#### Task 1.1.2: Write migration 4 function
- **File:** `plugins/pd/hooks/lib/semantic_memory/database.py`
- **Action:** Create `_migration_4(conn: sqlite3.Connection, **_kwargs: object) -> None:` that runs `ALTER TABLE entries ADD COLUMN influence_count INTEGER DEFAULT 0` and `CREATE TABLE IF NOT EXISTS influence_log (id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id TEXT NOT NULL, agent_role TEXT NOT NULL, feature_type_id TEXT, timestamp TEXT NOT NULL)`
- **Done:** Function exists, accepts `**_kwargs`, runs both statements
- **Depends on:** 1.1.1

#### Task 1.1.3: Register migration 4 in MIGRATIONS dict
- **File:** `plugins/pd/hooks/lib/semantic_memory/database.py`
- **Action:** Add `4: _migration_4` to `MIGRATIONS` dict
- **Done:** `MIGRATIONS[4]` points to `_migration_4`
- **Depends on:** 1.1.2

#### Task 1.1.4: Implement merge_duplicate method
- **File:** `plugins/pd/hooks/lib/semantic_memory/database.py`
- **Action:** Add `merge_duplicate(self, existing_id: str, new_keywords: list[str]) -> dict` method. Use `BEGIN IMMEDIATE`. Read existing entry. Parse existing keywords with try/except (fall back to `[]` on malformed JSON). Union with new_keywords. UPDATE observation_count +1, updated_at, keywords. Return `self.get_entry(existing_id)`.
- **Done:** Method exists, uses BEGIN IMMEDIATE, handles malformed JSON, raises ValueError for non-existent ID
- **Depends on:** 1.1.3 (needs migration for influence_count column to exist in schema)

#### Task 1.1.5: Write migration 4 tests
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
- **Action:** Add tests: migration creates influence_count column and influence_log table; migration is idempotent (schema_version check prevents re-run)
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -v -k "migration_4"`
- **Done:** Tests pass
- **Depends on:** 1.1.3

#### Task 1.1.6: Write merge_duplicate tests
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
- **Action:** Add tests: increments observation_count; unions keywords; preserves other fields unchanged; raises ValueError for non-existent ID; handles malformed existing keywords JSON gracefully
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -v -k "merge_duplicate"`
- **Done:** Tests pass
- **Depends on:** 1.1.4

### 1.2 Keyword Extractor

#### Task 1.2.1: Create keywords.py with constants
- **File:** `plugins/pd/hooks/lib/semantic_memory/keywords.py` (new)
- **Action:** Create file with `_KEYWORD_RE`, `_STOPWORDS`, and `KEYWORD_PROMPT` constants as specified in spec FR-1
- **Done:** File exists with all three constants matching spec
- **Depends on:** none

#### Task 1.2.2: Implement _tier1_extract
- **File:** `plugins/pd/hooks/lib/semantic_memory/keywords.py`
- **Action:** Implement `_tier1_extract(text: str) -> list[str]`. Tokenize via `re.split(r"[\s\W]+", text.lower())` (split on whitespace and non-word characters). Filter by `_KEYWORD_RE`, remove `_STOPWORDS`. Extract hyphenated multi-word terms already present in text. Join consecutive capitalized word sequences from original text as hyphenated terms (e.g., "Entity Registry" → "entity-registry"). Deduplicate, limit to 10.
- **Done:** Function returns 0-10 lowercase keyword strings
- **Depends on:** 1.2.1

#### Task 1.2.3: Implement _tier2_extract
- **File:** `plugins/pd/hooks/lib/semantic_memory/keywords.py`
- **Action:** Implement `_tier2_extract(name, description, reasoning, category) -> list[str]`. Uses `google.genai.Client.models.generate_content()` with `gemini-2.0-flash` model. Strip markdown code fences before JSON parse. Validate each keyword against `_KEYWORD_RE` + `_STOPWORDS`. Return `[]` on any failure (API error, missing GEMINI_API_KEY, parse failure). Lazy-initialize client.
- **Done:** Function calls Gemini API, parses response, validates keywords, gracefully degrades
- **Depends on:** 1.2.1

#### Task 1.2.4: Implement extract_keywords orchestrator
- **File:** `plugins/pd/hooks/lib/semantic_memory/keywords.py`
- **Action:** Implement `extract_keywords(name, description, reasoning, category, config=None) -> list[str]`. Concatenate name+description+reasoning, call `_tier1_extract()`. If >= 3 results, return them. Otherwise call `_tier2_extract()`, combine with Tier 1 results, deduplicate, limit to 10.
- **Done:** Function returns Tier 1 results when >= 3, falls back to Tier 2 otherwise
- **Depends on:** 1.2.2, 1.2.3

#### Task 1.2.5: Write keyword extraction tests
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_keywords.py` (new)
- **Action:** Create test file with tests for: Tier 1 technical text (>= 3 keywords); Tier 1 pure stopwords (empty); Tier 1 hyphenated terms; Tier 2 mock API (fires only when Tier 1 < 3); Tier 2 malformed JSON handling; Tier 2 stopword validation; Tier 2 API failure (returns []); extract_keywords returns Tier 1 when >= 3; extract_keywords combines when Tier 1 < 3; AC-1 test; AC-2 test with 10 representative entries
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_keywords.py -v`
- **Done:** All tests pass
- **Depends on:** 1.2.4

### 1.3 Dedup Checker

#### Task 1.3.1: Create dedup.py with DedupResult and check_duplicate
- **File:** `plugins/pd/hooks/lib/semantic_memory/dedup.py` (new)
- **Action:** Create file with `DedupResult` dataclass (`is_duplicate: bool`, `existing_entry_id: str | None`, `similarity: float`) and `check_duplicate(embedding_vec: np.ndarray, db: MemoryDatabase, threshold: float = 0.90) -> DedupResult`. Guard: `result = db.get_all_embeddings(); if result is None: return DedupResult(False, None, 0.0)`. Compute `scores = matrix @ embedding_vec`, find top match via `ids[np.argmax(scores)]`, compare against threshold.
- **Done:** Function returns correct DedupResult for duplicate/non-duplicate/empty-DB cases
- **Depends on:** 1.1.3 (migration must exist for schema compatibility)

#### Task 1.3.2: Write dedup tests
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_dedup.py` (new)
- **Action:** Create test file with tests for: similarity > threshold returns duplicate; similarity < threshold returns non-duplicate; correct entry ID via argmax; get_all_embeddings returns None; graceful degradation; threshold parameter respected (0.90 vs 0.80 vs 0.95); AC-6 near-duplicate detection
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_dedup.py -v`
- **Done:** All tests pass
- **Depends on:** 1.3.1

### 1.4 Config Extension

#### Task 1.4.1: Add memory_dedup_threshold to config defaults
- **File:** `plugins/pd/hooks/lib/semantic_memory/config.py`
- **Action:** Add `"memory_dedup_threshold": 0.90` to `DEFAULTS` dict
- **Done:** `DEFAULTS["memory_dedup_threshold"]` == 0.90
- **Depends on:** none

#### Task 1.4.2: Add memory_dedup_threshold to pd.local.md
- **File:** `.claude/pd.local.md`
- **Action:** Add `memory_dedup_threshold: 0.90` to the memory config block (after existing memory_* keys)
- **Done:** Key present in pd.local.md
- **Depends on:** none

---

## Phase 2: Integration

### 2.1 Integrate keywords + dedup into store_memory

#### Task 2.1.1: Add imports to memory_server.py
- **File:** `plugins/pd/mcp/memory_server.py`
- **Action:** Add `from semantic_memory.keywords import extract_keywords` and `from semantic_memory.dedup import check_duplicate` to imports. Note: `_embed_text_for_entry` already imported at line 27.
- **Done:** Both imports present, no duplicates
- **Depends on:** 1.2.4, 1.3.1

#### Task 2.1.2: Replace hardcoded keywords with extract_keywords
- **File:** `plugins/pd/mcp/memory_server.py`
- **Action:** In `_process_store_memory()`, replace `keywords_json = "[]"` (line 76) with: `keywords = extract_keywords(name, description, reasoning, category)` then `keywords_json = json.dumps(keywords)`
- **Done:** `keywords_json` populated from `extract_keywords()` instead of hardcoded `"[]"`
- **Depends on:** 2.1.1

#### Task 2.1.3: Move embedding computation before dedup check
- **File:** `plugins/pd/mcp/memory_server.py`
- **Action:** In `_process_store_memory()`, BEFORE the upsert call, compute embedding early: set `embedding_vec = None`. Wrap in `if provider is not None:` guard. Build `partial_entry = {"name": name, "description": description, "keywords": keywords_json, "reasoning": reasoning}`, call `embed_text = _embed_text_for_entry(partial_entry)`, then `embedding_vec = provider.embed(embed_text, task_type="document")`.
- **Done:** `embedding_vec` is None when no provider, computed vector when provider available
- **Depends on:** 2.1.2

#### Task 2.1.4: Add dedup check before store
- **File:** `plugins/pd/mcp/memory_server.py`
- **Action:** After embedding computation, before upsert: read threshold from config (`config.get("memory_dedup_threshold", 0.90)`). If `embedding_vec is not None`: call `dedup_result = check_duplicate(embedding_vec, db, threshold)`. If `dedup_result.is_duplicate`: call `merged = db.merge_duplicate(dedup_result.existing_entry_id, keywords)` and return `f"Reinforced: {merged['name']} (observation #{merged['observation_count']})"`.
- **Done:** Near-duplicates trigger merge path, unique entries proceed to upsert
- **Depends on:** 2.1.3, 1.4.1

#### Task 2.1.5: Replace post-upsert embedding with pre-computed
- **File:** `plugins/pd/mcp/memory_server.py`
- **Action:** Remove the existing post-upsert embedding block (find the `if provider is not None:` block after `db.upsert_entry(entry)` that calls `_embed_text_for_entry(stored)` → `provider.embed(embed_text, task_type="document")` → `db.update_embedding(entry_id, vec.tobytes())` — approximately 12 lines). Replace with: `if embedding_vec is not None: db.update_embedding(entry_id, embedding_vec.tobytes())`. This uses the pre-computed vector from Task 2.1.3.
- **Done:** Embedding computed once (not twice), stored via update_embedding after upsert
- **Depends on:** 2.1.4

#### Task 2.1.6: Write store_memory integration tests
- **File:** `plugins/pd/mcp/test_memory_server.py`
- **Action:** Add tests: store_memory produces non-empty keywords; store_memory with near-duplicate returns "Reinforced:"; store_memory with unique entry returns "Stored:"; keywords are stored in DB entry; dedup gracefully degrades when embedding unavailable; AC-4 (3-10 keyword elements)
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v -k "keyword or dedup or reinforced"`
- **Done:** All tests pass
- **Depends on:** 2.1.5

### 2.2 Add record_influence MCP tool

#### Task 2.2.1: Add find_entry_by_name to MemoryDatabase
- **File:** `plugins/pd/hooks/lib/semantic_memory/database.py`
- **Action:** Add `find_entry_by_name(self, name: str) -> dict | None`. Primary: `SELECT * FROM entries WHERE LOWER(name) = LOWER(?)`. Fallback: escape `%` and `_` in name, then `SELECT * FROM entries WHERE name LIKE ? ESCAPE '\'` with `%{escaped}%` pattern. Return first match or None.
- **Done:** Method exists with exact match + LIKE fallback, SQL wildcards escaped
- **Depends on:** 1.1.3

#### Task 2.2.2: Add increment_influence and log_influence to MemoryDatabase
- **File:** `plugins/pd/hooks/lib/semantic_memory/database.py`
- **Action:** Add `increment_influence(self, entry_id: str) -> None` (UPDATE influence_count + 1). Add `log_influence(self, entry_id: str, agent_role: str, feature_type_id: str | None) -> None` (INSERT into influence_log with current timestamp).
- **Done:** Both methods exist, operate on correct tables
- **Depends on:** 1.1.3

#### Task 2.2.3: Register record_influence MCP tool
- **File:** `plugins/pd/mcp/memory_server.py`
- **Action:** Add `record_influence` tool to FastMCP server with params: `entry_name: str`, `agent_role: str`, `feature_type_id: str | None = None`. Implement `_process_record_influence()`: call `db.find_entry_by_name(entry_name)`, if found: `db.increment_influence(entry["id"])` + `db.log_influence(entry["id"], agent_role, feature_type_id)` + return success message. If not found: return `"Entry not found: {entry_name}"`.
- **Done:** Tool registered and callable via MCP
- **Depends on:** 2.2.1, 2.2.2

#### Task 2.2.4: Write influence database method tests
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
- **Action:** Add tests: find_entry_by_name exact match; find_entry_by_name LIKE fallback; find_entry_by_name returns None for non-existent; SQL wildcards escaped; increment_influence updates count; log_influence inserts row
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -v -k "influence or find_entry"`
- **Done:** All tests pass
- **Depends on:** 2.2.1, 2.2.2

#### Task 2.2.5: Write record_influence MCP tool tests
- **File:** `plugins/pd/mcp/test_memory_server.py`
- **Action:** Add tests: record_influence increments influence_count; record_influence inserts influence_log row; record_influence returns error for non-existent entry; AC-8
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v -k "influence"`
- **Done:** All tests pass
- **Depends on:** 2.2.3

### 2.3 Update prominence ranking

#### Task 2.3.1: Audit test_ranking.py for hardcoded scores
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_ranking.py`
- **Action:** Run `grep -n "0\.3\|0\.2" plugins/pd/hooks/lib/semantic_memory/test_ranking.py` to find all prominence score float literals. Write a list of each line + assertion that needs updating for the new formula weights.
- **Verify:** `grep -c "0\.3\|0\.2" plugins/pd/hooks/lib/semantic_memory/test_ranking.py` returns a count
- **Done:** All prominence score float literals identified by line number
- **Depends on:** none

#### Task 2.3.2: Add _influence_score helper and update _prominence
- **File:** `plugins/pd/hooks/lib/semantic_memory/ranking.py`
- **Action:** Add `_influence_score(self, entry: dict) -> float` returning `min(entry.get("influence_count", 0) / 10.0, 1.0)`. Update `_prominence()` to use new formula: `0.25 * norm_obs + 0.15 * confidence + 0.25 * recency + 0.15 * recall + 0.20 * influence`. Handle missing `influence_count` key via `.get()` default.
- **Done:** New formula active, missing influence_count defaults to 0
- **Depends on:** 1.1.1

#### Task 2.3.3: Update existing ranking tests and add influence tests
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_ranking.py`
- **Action:** Fix hardcoded prominence assertions from 2.3.1 audit. Add new tests: higher influence_count ranks higher; influence_count=0 → score 0.0; influence_count>=10 → score 1.0 (capped); missing influence_count defaults to 0; AC-9
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_ranking.py -v`
- **Done:** All tests pass (old + new)
- **Depends on:** 2.3.1, 2.3.2

---

## Phase 3: Wiring

### 3.1 Backfill command

#### Task 3.1.1: Add backfill-keywords action to writer.py
- **File:** `plugins/pd/hooks/lib/semantic_memory/writer.py`
- **Action:** Add `'backfill-keywords'` to `--action` choices in argparser. Implement `_backfill_keywords(db, config)`: query entries where `keywords = '[]'`, for each call `extract_keywords()` → `db.update_keywords()`, progress output every 50, continue on per-entry failures. Wire in `main()` dispatch.
- **Done:** `--action backfill-keywords` accepted and routes to `_backfill_keywords`
- **Depends on:** 1.2.4

#### Task 3.1.2: Write backfill tests
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_keywords.py`
- **Action:** Add tests: backfill processes empty-keyword entries and populates them; backfill skips entries with existing keywords; backfill continues on per-entry failures; CLI dispatch via `main()` with `--action backfill-keywords` routes correctly; AC-5. Test DB uses `MemoryDatabase()` for auto-migration.
- **Verify:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_keywords.py -v -k "backfill"`
- **Done:** All tests pass
- **Depends on:** 3.1.1

### 3.2 Full regression

#### Task 3.2.1: Run full regression suite
- **Action:** Run all semantic memory tests + memory server tests + ranking tests. Fix any failures.
- **Verify:**
  ```
  plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v
  plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v
  ```
- **Done:** All tests pass (AC-10)
- **Depends on:** 2.1.6, 2.2.5, 2.3.3, 3.1.2

---

## Summary

- **Total tasks:** 27
- **Phases:** 3
- **Parallel groups:** Phase 1 (1.2 + 1.3 parallel after 1.1; 1.4 independent), Phase 2 (2.1 + 2.2 + 2.3 parallel), Phase 3 (3.1 then 3.2)
- **New files:** 4 (keywords.py, test_keywords.py, dedup.py, test_dedup.py)
- **Modified files:** 9 (database.py, test_database.py, memory_server.py, test_memory_server.py, ranking.py, test_ranking.py, config.py, writer.py, pd.local.md)
