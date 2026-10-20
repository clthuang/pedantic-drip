# RCA: search_memory MCP tool returns "No matching memories found" for all queries

**Date:** 2026-03-19
**Severity:** Critical (feature completely non-functional)
**Component:** `plugins/pd/mcp/memory_server.py` -> `semantic_memory.retrieval` -> `semantic_memory.database`
**Status:** Root causes identified, not yet fixed

## Symptom

The MCP `search_memory` tool returns "No matching memories found" for ALL queries, despite the database containing 676 entries with a working FTS5 index (verified via direct sqlite3 queries).

## Root Causes (5 contributing causes)

### Cause 1: FTS5 implicit AND semantics (CRITICAL)

**Location:** `plugins/pd/hooks/lib/semantic_memory/database.py:416-425` (`fts5_search` method)

FTS5 default query syntax uses implicit AND. A query like `"firebase firestore typescript"` requires ALL three words to appear in the same entry. Since no single entry contains all three, the result is 0 matches.

**Evidence:**
- `fts5_search("firebase firestore typescript")` -> 0 results
- `fts5_search("firebase")` -> 5, `fts5_search("firestore")` -> 7, `fts5_search("typescript")` -> 2
- `MATCH 'firebase OR firestore OR typescript'` -> 14 results

### Cause 2: FTS5 interprets hyphens as column selectors (CRITICAL)

**Location:** `plugins/pd/hooks/lib/semantic_memory/database.py:416-428`

FTS5 syntax `column:term` uses a colon. But hyphens are also interpreted as column selectors: `anti-patterns` is parsed as "term `anti` in column `patterns`". Since `patterns` is not a valid FTS5 column, this throws `OperationalError: no such column: patterns`.

The `except sqlite3.OperationalError` on line 427 silently swallows this error and returns `[]`.

**Affected terms from real usage:** `anti-patterns`, `create-tasks`, `git-flow`, `rename-pedantic-drip`, `built-in`, `claude-plugin/*`

**Evidence:**
- `MATCH 'anti-patterns'` -> ERROR "no such column: patterns"
- `MATCH '"anti-patterns"'` -> 1 result (quoting fixes it)

### Cause 3: FTS5 special character syntax errors (HIGH)

**Location:** Same as Cause 2

Dots (`.`), slashes (`/`), and other special characters in queries cause FTS5 syntax errors, also silently swallowed.

**Evidence:**
- `MATCH '.claude-plugin/marketplace.json'` -> ERROR "syntax error near ."

### Cause 4: 89% of entries lack embeddings (MEDIUM)

**Location:** Database state in `~/.claude/pd/memory/memory.db`

Only 74 of 676 entries (10.9%) have vector embeddings. The embedding generation step (`writer.py:_process_pending_embeddings`) processes in batches of 50 and requires an API key. Most entries were imported without embeddings and never backfilled.

**Impact:** Even when the vector retrieval path is available, it can only match ~11% of entries.

### Cause 5: MCP server environment lacks GEMINI_API_KEY (MEDIUM)

**Location:** `plugins/pd/hooks/lib/semantic_memory/embedding.py:47-59` (`_load_dotenv_once`)

The `_load_dotenv_once` function walks up the directory tree from `embedding.py`'s file location to find `.git`, then loads `.env` from that directory. When the MCP server runs from the plugin cache (`~/.claude/plugins/cache/pedantic-drip-marketplace/pd/`), there is no `.git` directory in any parent, so `.env` is never loaded and `GEMINI_API_KEY` is not available.

**Evidence:**
- Walking up from `/Users/terry/.claude/plugins/cache/pedantic-drip-marketplace/pd/hooks/lib/semantic_memory/` reaches `/` without finding `.git`
- `echo $GEMINI_API_KEY` in current shell -> empty
- `.env` exists at project root with valid key but is unreachable from cache

**Impact:** `create_provider()` returns `None`, disabling ALL vector retrieval. Combined with Causes 1-3 (FTS5 broken), this means zero retrieval candidates for virtually all queries.

### Cause 6: Embedding SDK not installed in fresh venvs (MEDIUM)

**Location:** `plugins/pd/pyproject.toml:16-20` (optional dependencies), `plugins/pd/mcp/bootstrap-venv.sh`

The embedding provider SDKs (`google-genai`, `voyageai`, `openai`, `ollama`) are declared as optional dependencies. `bootstrap-venv.sh` runs `uv sync` without `--extra`, so a fresh install never installs any SDK. `import google.genai` fails silently (caught by `try/except ImportError`), and `create_provider()` returns `None` even when `GEMINI_API_KEY` is correctly set.

**Evidence:**
- `pyproject.toml` lines 16-20: `[project.optional-dependencies]` with `gemini = ["google-genai>=1.0,<2"]`
- `bootstrap-venv.sh` uses `uv sync` without `--extra` flag
- `embedding.py` lines 17-22: `try: from google import genai` with silent `except ImportError`

**Impact:** Vector retrieval completely disabled for all new pd installations, even when API key is configured.

## Interaction Effects

Causes 1-3 and Causes 4-5 form a compound failure:

1. Vector retrieval is disabled (Causes 4-5) -> only FTS5 path remains
2. FTS5 path fails for multi-word queries (Cause 1), hyphenated terms (Cause 2), and special chars (Cause 3) -> returns empty
3. Both retrieval paths return 0 candidates -> ranking has nothing to rank -> "No matching memories found"

The silent error handling in `fts5_search` (catching `OperationalError` and returning `[]`) masks the failure completely. No errors appear in logs; the feature just silently returns nothing.

## Fix Directions (not prescriptive)

| Cause | Fix Direction |
|-------|---------------|
| 1 | Sanitize FTS5 query: join terms with `OR` instead of implicit `AND` |
| 2 | Quote hyphenated terms before passing to FTS5 MATCH (e.g., `"anti-patterns"`) |
| 3 | Strip/escape FTS5 special characters (`.`, `/`, `:`, `#`, `>`, etc.) from query |
| 4 | Add embedding backfill mechanism (batch process entries without embeddings) |
| 5 | Pass `GEMINI_API_KEY` via MCP server env config, or load `.env` from project root (cwd) instead of walking up from file location |
| All | Add diagnostic logging in `fts5_search` when `OperationalError` occurs (at least to stderr) |

## Verification Scripts

All reproduction and verification scripts are in:
- `agent_sandbox/20260319/rca-search-memory/reproduction/test_fts5_match.py` - Initial FTS5 failure reproduction
- `agent_sandbox/20260319/rca-search-memory/experiments/test_fts5_operators.py` - AND vs OR operator verification
- `agent_sandbox/20260319/rca-search-memory/experiments/test_mcp_search_path.py` - Full MCP pipeline simulation
- `agent_sandbox/20260319/rca-search-memory/experiments/test_injector_context.py` - Injector context query analysis
- `agent_sandbox/20260319/rca-search-memory/experiments/test_fix_approach.py` - Fix approach validation
- `agent_sandbox/20260319/rca-search-memory/reproduction/test_vector_retrieval.py` - Vector path analysis
