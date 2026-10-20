# Plan: Fix memory search — FTS5 query sanitization and vector path recovery

## Implementation Order

Two independent tracks that can be implemented in parallel, followed by integration verification.

### Track A: FTS5 Fixes (R1-R4)

```
A1: Add _sanitize_fts5_query() + unit tests
    ↓
A2: Integrate sanitizer into fts5_search() + add error logging
    ↓
A3: Add integration tests for search_memory MCP tool
```

### Track B: Vector Path Fixes (R5-R6)

```
B1: Update _load_dotenv_once() with cwd fallback + unit tests
    ↓
B2: Update run-memory-server.sh (.env loading + SDK install)
```

### Integration

```
C1: End-to-end verification with real memory.db
```

## Steps

### A1: FTS5 Query Sanitizer Function + Tests

**Files:** `plugins/pd/hooks/lib/semantic_memory/database.py`, `plugins/pd/hooks/lib/semantic_memory/test_database.py`

**TDD order:** Write `TestFts5Sanitizer` tests first (red), then implement `_sanitize_fts5_query()` (green).

**Implementation:**
1. Add `TestFts5Sanitizer` test class first
2. Add `_FTS5_STRIP_RE` regex and `_sanitize_fts5_query()` function (from design Interface 1)
3. Tests covering:
   - Multi-word → OR join (`"firebase firestore typescript"` → `"firebase OR firestore OR typescript"`)
   - Hyphenated → quoted (`"anti-patterns"` → `'"anti-patterns"'`)
   - Mixed (`"source:session-capture"` → `'source OR "session-capture"'`)
   - Special chars stripped (`".claude-plugin/marketplace.json"` → `"claude OR plugin OR marketplace OR json"`)
   - Double-quotes stripped (AC-3.4)
   - Standalone `-` dropped
   - All-special-chars → empty string
   - Empty input → empty string
   - Single word unchanged

**Test command:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -v -k "TestFts5Sanitizer"`

**Dependencies:** None
**Spec coverage:** R1 (partial), R2 (partial), R3, AC-3.3, AC-3.4

---

### A2: Integrate Sanitizer into fts5_search() + Error Logging

**Files:** `plugins/pd/hooks/lib/semantic_memory/database.py`, `plugins/pd/hooks/lib/semantic_memory/test_database.py`

**Implementation:**
1. Update `fts5_search()` to call `_sanitize_fts5_query(query)` before MATCH
2. Return `[]` immediately if sanitized query is empty
3. In `except sqlite3.OperationalError as e` block, add stderr logging (design Interface 2)
4. Add/update tests in existing FTS5 test classes:
   - `test_fts5_search_matches_name` etc. — verify still pass (regression)
   - New: multi-word OR search returns entries matching any term (AC-1.1)
   - New: BM25 ranking with multi-match entry ranked higher (AC-1.3)
   - New: hyphenated term search returns matches (AC-2.1, AC-2.2)
   - New: special char query returns results (AC-3.1, AC-3.2)
   - New: OperationalError logged to stderr (AC-4.1, AC-4.2)

**Test command:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -v -k "fts5"`

**Dependencies:** A1
**Spec coverage:** R1, R2, R4, AC-1.1 through AC-4.2

---

### A3: MCP Integration Tests

**Files:** `plugins/pd/mcp/test_memory_server.py`

**Implementation:**
1. Add `TestSearchMemoryFts5Sanitization` class with tests:
   - Multi-word query through `_process_search_memory` returns results
   - Hyphenated query returns results
   - Special character query does not error
   - Category filter + sanitized query work together
2. Run existing test suite to verify no regressions

**Test command:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v`

**Dependencies:** A2
**Spec coverage:** Full R1-R4 integration verification

---

### B1: Update _load_dotenv_once() + Tests

**Files:** `plugins/pd/hooks/lib/semantic_memory/embedding.py`, `plugins/pd/hooks/lib/semantic_memory/test_embedding.py`

**Implementation:**
1. Update `_load_dotenv_once()` per design Interface 3:
   - Fast path: return early if any known API key already in env
   - Try cwd `.env` (additive, no early return)
   - Fall through to `.git` walk-up
   - Add docstring comment about singleton behavior
2. Add tests:
   - API key already set → dotenv not called
   - cwd `.env` loaded when present
   - `.git` walk-up still works as fallback
   - Both cwd and `.git` paths run additively (cwd `.env` missing key, `.git` `.env` has it)

**Test command:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_embedding.py -v -k "dotenv or load_env"`

**Dependencies:** None
**Spec coverage:** R5 (AC-5.1 through AC-5.3)

---

### B2: Update run-memory-server.sh

**Files:** `plugins/pd/mcp/run-memory-server.sh`

**Implementation:**
1. Add selective `.env` key export via grep (design Interface 4, lines 222-228):
   - Extract only `GEMINI_API_KEY`, `OPENAI_API_KEY`, `VOYAGE_API_KEY`, `MEMORY_EMBEDDING_PROVIDER`
   - Comment documenting supported `.env` formats
2. Add post-bootstrap SDK install block (design Interface 4, lines 235-250):
   - Case map: provider → (pip package, import name)
   - Import check before install (fast skip if already present)
   - Install with error shown on stderr
3. Verify existing bootstrap tests still pass

**Test command:** `bash plugins/pd/mcp/test_run_memory_server.sh`

**Dependencies:** None (B1 and B2 are independently testable — different files, different layers)
**Spec coverage:** R5 (AC-5.4), R6 (AC-6.1 through AC-6.3)

---

### C1: End-to-End Verification

**Not a code task — manual verification step.**

1. Run `search_memory` MCP tool with multi-word query against real `~/.claude/pd/memory/memory.db`
2. Verify results returned (not "No matching memories found")
3. Verify hyphenated queries work (`"anti-patterns"`)
4. Check stderr for diagnostic messages (should be clean, no FTS5 errors for normal queries)

**Dependencies:** A3, B2

## Risk Mitigations

| Step | Risk | Mitigation |
|------|------|------------|
| A1 | Sanitizer regex misses edge case | Comprehensive unit tests with real-world queries from RCA |
| A2 | Regression in existing FTS5 tests | Run full test suite after integration |
| B2 | Shell `.env` parsing fails on unusual formats | Only grep known key names; comment supported formats |
| B2 | SDK install fails silently | Error shown on stderr + warning message |

## Estimated Complexity

| Step | Size | Notes |
|------|------|-------|
| A1 | Small | ~20 lines implementation + ~60 lines tests |
| A2 | Small | ~10 lines change + ~80 lines tests |
| A3 | Small | ~40 lines tests |
| B1 | Small | ~15 lines change + ~40 lines tests |
| B2 | Medium | ~30 lines shell changes + manual verification |
| C1 | Trivial | Manual verification only |
