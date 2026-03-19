# Tasks: Fix memory search — FTS5 query sanitization and vector path recovery

## Phase 1: FTS5 Sanitizer (Track A — independent of Phase 2)

### Task 1.1: Write TestFts5Sanitizer unit tests (RED)
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
- **Action:** Add `TestFts5Sanitizer` class with tests for `_sanitize_fts5_query()`:
  - `test_multi_word_joins_with_or` — `"firebase firestore typescript"` → `"firebase OR firestore OR typescript"`
  - `test_single_word_unchanged` — `"firebase"` → `"firebase"`
  - `test_hyphenated_quoted` — `"anti-patterns"` → `'"anti-patterns"'`
  - `test_mixed_hyphen_and_plain` — `"source session-capture"` → `'source OR "session-capture"'`
  - `test_colon_stripped` — `"source:session-capture"` → `'source OR "session-capture"'`
  - `test_special_chars_stripped` — `".claude-plugin/marketplace.json"` → `"claude OR plugin OR marketplace OR json"`
  - `test_double_quotes_stripped` — `'"hello"'` → `"hello"`
  - `test_standalone_dash_dropped` — `"foo - bar"` → `"foo OR bar"`
  - `test_all_special_chars_returns_empty` — `"..."` → `""`
  - `test_empty_input_returns_empty` — `""` → `""`
- **Done when:** Tests exist and fail (function not yet implemented). Do not run full suite until Task 1.2 completes.
- **Depends on:** Nothing
- **Plan ref:** A1

### Task 1.2: Implement _sanitize_fts5_query() (GREEN)
- **File:** `plugins/pd/hooks/lib/semantic_memory/database.py`
- **Action:** Add `_FTS5_STRIP_RE` regex and `_sanitize_fts5_query()` function per design Interface 1
- **Done when:** All Task 1.1 tests pass
- **Depends on:** 1.1
- **Plan ref:** A1

### Task 1.3: Integrate sanitizer into fts5_search() + add error logging
- **File:** `plugins/pd/hooks/lib/semantic_memory/database.py`
- **Action:**
  - Call `_sanitize_fts5_query(query)` at top of `fts5_search()`
  - Return `[]` if sanitized is empty
  - Add `print(f"semantic_memory: FTS5 error for query {query!r}: {e}", file=sys.stderr)` in except block
- **Done when:** Existing fts5 tests still pass. Run: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -v -k "fts5"` — zero failures.
- **Depends on:** 1.2
- **Plan ref:** A2

### Task 1.4: Add fts5_search integration tests
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
- **Action:** Add tests using controlled test DB with known entries:
  - `test_fts5_or_search_returns_any_match` — multi-word query returns entries matching any term (AC-1.1)
  - `test_fts5_bm25_ranks_multi_match_higher` — entry matching 2/3 terms ranks above 1/3 (AC-1.3)
  - `test_fts5_hyphenated_search` — `"anti-patterns"` returns matches (AC-2.1)
  - `test_fts5_multi_hyphenated_search` — `"create-tasks git-flow"` returns matches for both (AC-2.2)
  - `test_fts5_special_char_query` — `".claude-plugin/marketplace.json"` returns results (AC-3.1)
  - `test_fts5_colon_query` — `"source:session-capture"` returns results (AC-3.2)
  - `test_fts5_error_logged_to_stderr` — force OperationalError, verify stderr output (AC-4.1)
- **Test command:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -v -k "fts5"`
- **Done when:** All tests pass; full fts5 test suite has no regressions
- **Depends on:** 1.3
- **Plan ref:** A2

### Task 1.5: Add MCP search integration tests
- **File:** `plugins/pd/mcp/test_memory_server.py`
- **Action:** Add `TestSearchMemoryFts5Sanitization` class:
  - `test_multiword_query_returns_results` — via `_process_search_memory`
  - `test_hyphenated_query_returns_results`
  - `test_special_char_query_no_error`
  - `test_category_filter_with_sanitized_query`
- **Done when:** All tests pass; existing test suite has no regressions
- **Depends on:** 1.4
- **Plan ref:** A3

## Phase 2: Vector Path Fixes (Track B — independent of Phase 1)

### Task 2.1: Update _load_dotenv_once() + tests
- **File:** `plugins/pd/hooks/lib/semantic_memory/embedding.py`, `plugins/pd/hooks/lib/semantic_memory/test_embedding.py`
- **Action:**
  - Update `_load_dotenv_once()` per design Interface 3 (fast path + cwd + .git walk-up, no early return after cwd)
  - Add comment: "Process-lifetime singleton — re-loading not expected in normal MCP server lifecycle"
  - Add tests:
    - `test_dotenv_skipped_when_key_in_env` — API key set → dotenv not called
    - `test_dotenv_loads_from_cwd` — cwd `.env` loaded
    - `test_dotenv_git_walkup_fallback` — `.git` walk-up still works
    - `test_dotenv_additive_cwd_and_git` — cwd `.env` missing key, `.git` `.env` has it → key loaded
- **Done when:** All tests pass
- **Depends on:** Nothing
- **Plan ref:** B1

### Task 2.2: Update run-memory-server.sh (.env + SDK install)
- **File:** `plugins/pd/mcp/run-memory-server.sh`
- **Action:**
  - Add selective `.env` key export via grep (GEMINI_API_KEY, OPENAI_API_KEY, VOYAGE_API_KEY, MEMORY_EMBEDDING_PROVIDER)
  - Add comment: `# Supports KEY=value, KEY="value", KEY='value' — not multi-line values`
  - Add post-bootstrap SDK install block with provider→(package, import) case map
  - Keep existing bootstrap_venv call unchanged
- **Done when:**
  1. `bash plugins/pd/mcp/test_run_memory_server.sh` passes (no regressions)
  2. Manual .env verify: create temp `.env` with `GEMINI_API_KEY=test123`, run grep extraction in isolation, confirm var is exported
  3. Manual SDK verify: set `MEMORY_EMBEDDING_PROVIDER=gemini`, confirm the case-map produces correct package/import pair
  4. Spot-check `.env` formats: `KEY=value`, `KEY="value"`, `KEY='value'` all parse correctly
- **Depends on:** Nothing
- **Plan ref:** B2

## Phase 3: Verification

### Task 3.1: Run full test suites + end-to-end verification
- **Action:** Run all affected test suites and verify no regressions:
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -v`
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_embedding.py -v`
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v`
  - `bash plugins/pd/mcp/test_run_memory_server.sh`
- **Manual e2e verification** (against real `~/.claude/pd/memory/memory.db`):
  1. Run `search_memory` MCP tool with multi-word query — confirm results returned (not "No matching memories found")
  2. Run hyphenated query (e.g., `"anti-patterns"`) — confirm matches
  3. Check stderr is clean (no FTS5 errors for normal queries)
- **Done when:** All automated tests pass (zero failures) + manual e2e returns results
- **Depends on:** 1.5, 2.1, 2.2 (all Phase 1 and Phase 2 tasks complete)
- **Plan ref:** C1
