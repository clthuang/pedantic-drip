# Spec: Fix memory search — FTS5 query sanitization and vector path recovery

## Problem Statement

The MCP `search_memory` tool returns "No matching memories found" for virtually all queries. Root cause analysis (docs/rca/20260319-search-memory-returns-no-results.md) identified 6 contributing causes forming a compound failure where both retrieval paths (FTS5 + vector) are broken simultaneously.

## Scope

**In scope:**
- FTS5 query sanitization (Causes 1-3): fix the keyword retrieval path
- Vector path environment fix (Cause 5): enable embedding-based retrieval from plugin cache
- Embedding SDK dependency installation (Cause 6): fresh installs lack optional deps for vector path
- Diagnostic logging for FTS5 errors (silent failures → logged warnings)

**Out of scope:**
- Embedding backfill (Cause 4): separate operational task, not a code fix
- Changing the hybrid ranking algorithm
- Adding new retrieval strategies

## Requirements

### R1: FTS5 multi-word queries use OR semantics

`fts5_search()` must split multi-word queries into individual terms joined with `OR` so that entries matching ANY term are returned (not just entries matching ALL terms).

**Acceptance criteria:**
- AC-1.1: `fts5_search("firebase firestore typescript")` returns entries matching any of the three terms. Tests use a controlled test database with known entries and assert exact match counts.
- AC-1.2: Single-word queries continue to work unchanged
- AC-1.3: `fts5_search()` still uses BM25 ranking (`ORDER BY rank`). Verified via test: Entry A contains terms X and Y, Entry B contains only term X. Query `"X Y"` returns Entry A ranked above Entry B.

### R2: FTS5 hyphenated terms are quoted

Hyphenated terms in queries must be double-quoted before being passed to FTS5 MATCH, preventing FTS5 from interpreting them as column:value syntax.

**Acceptance criteria:**
- AC-2.1: `fts5_search("anti-patterns")` returns matches instead of silently failing. Tests use controlled test data with a known entry containing "anti-patterns".
- AC-2.2: `fts5_search("create-tasks git-flow")` returns results including at least one entry matching `create-tasks` AND at least one entry matching `git-flow`, using controlled test data with known entries for each term
- AC-2.3: Non-hyphenated terms in the same query are not affected

### R3: FTS5 special characters are stripped or escaped

FTS5 metacharacters must be stripped from the query before MATCH. The complete set: `.`, `/`, `:`, `#`, `>`, `*`, `^`, `~`, `(`, `)`, `+`, `"`, and standalone `-` (not hyphens within words, which are handled by R2).

**Acceptance criteria:**
- AC-3.1: `fts5_search(".claude-plugin/marketplace.json")` does not throw; returns results matching constituent words (`claude`, `plugin`, `marketplace`, `json`)
- AC-3.2: `fts5_search("source:session-capture")` does not throw; returns results matching constituent words
- AC-3.3: Empty query after sanitization returns empty list (no error)
- AC-3.4: Queries containing double-quote characters do not produce FTS5 syntax errors

### R4: FTS5 OperationalError is logged, not silently swallowed

When `fts5_search()` catches `sqlite3.OperationalError`, it must log a warning with the query and error message before returning empty.

**Acceptance criteria:**
- AC-4.1: `OperationalError` produces a line on stderr matching the pattern `semantic_memory: FTS5 error for query <query>: <error>` containing the failing query text. Testable with stderr capture + string match.
- AC-4.2: The function still returns `[]` on error (no behavior change for callers)

### R5: Vector embedding path loads API key from environment

`_load_dotenv_once()` must be able to find the API key when running from the plugin cache location (`~/.claude/plugins/cache/...`), not only from a git repository.

**Context:** Claude Code launches MCP servers with cwd set to the user's project root. The `run-memory-server.sh` wrapper can source `.env` from this cwd before launching Python, which is more reliable than Python-level cwd detection.

**Acceptance criteria:**
- AC-5.1: When `GEMINI_API_KEY` is set in the process environment, `create_provider()` returns a valid provider regardless of working directory
- AC-5.2: `_load_dotenv_once()` additionally tries loading `.env` from `os.getcwd()` as a fallback between the env-check and the `.git` walk-up
- AC-5.3: The `.git` walk-up remains as a final fallback, not removed
- AC-5.4: `run-memory-server.sh` wrapper sources project `.env` (from cwd) and exports API keys before launching the Python server. This is the primary fix; AC-5.2 is defense-in-depth.

### R6: Embedding SDK installed by default for configured provider

The embedding provider SDKs (e.g., `google-genai`) are declared as optional dependencies in `pyproject.toml`. A fresh `uv sync` only installs base deps, so `import google.genai` fails silently and `create_provider()` returns `None` even when `GEMINI_API_KEY` is set.

**Config key:** `memory_embedding_provider` — already exists in `embedding.py:create_provider()` (read from the `config` dict). Valid values: `gemini`, `openai`, `voyage`, `ollama` (matching the `[project.optional-dependencies]` groups in `pyproject.toml`). The value is passed to MCP servers via their config dict at startup.

**Acceptance criteria:**
- AC-6.1: `run-memory-server.sh` reads `MEMORY_EMBEDDING_PROVIDER` from env, and after `bootstrap_venv` completes, runs `uv pip install {provider-pkg}` if the SDK is not already importable (e.g., `uv pip install "google-genai>=1.0,<2"` when `MEMORY_EMBEDDING_PROVIDER=gemini`)
- AC-6.2: If no provider is configured, base deps only (no change from current behavior)
- AC-6.3: Given a fresh venv (no `google-genai` installed), `MEMORY_EMBEDDING_PROVIDER=gemini`, and `GEMINI_API_KEY` set, after running `run-memory-server.sh` bootstrap sequence, `import google.genai` succeeds and `create_provider()` returns a non-None provider

## Technical Approach

### FTS5 query sanitizer (R1-R3)

Add a `_sanitize_fts5_query(raw: str) -> str` function in `database.py`.

**Pipeline order (explicit):**
1. Strip FTS5 metacharacters: `.` `/` `:` `#` `>` `*` `^` `~` `(` `)` `+` `"` and standalone `-` (a `-` token not embedded within a word; intra-word hyphens like `anti-patterns` are preserved and handled in step 4)
2. Tokenize on whitespace
3. Drop empty tokens
4. Double-quote tokens containing hyphens (e.g., `anti-patterns` → `"anti-patterns"`)
5. Join tokens with `OR`
6. Return empty string if no valid tokens remain

**Example:** `source:session-capture` → strip `:` → `source session-capture` → tokenize → `["source", "session-capture"]` → quote hyphenated → `["source", '"session-capture"']` → join → `source OR "session-capture"`

Call this from `fts5_search()` before passing to MATCH. If sanitized query is empty, return `[]` immediately.

### Diagnostic logging (R4)

In the `except sqlite3.OperationalError as e` block, add:
```python
print(f"semantic_memory: FTS5 error for query {query!r}: {e}", file=sys.stderr)
```

### Environment fix (R5)

In `_load_dotenv_once()`:
1. If any known API key env var is already set, return early (no dotenv needed)
2. Try loading `.env` from `os.getcwd()` (defense-in-depth for MCP server context)
3. Fall back to existing `.git` walk-up from `__file__`

In `run-memory-server.sh` (primary fix):
1. If `.env` exists in cwd, source it
2. Export relevant API key vars (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `VOYAGE_API_KEY`)

### Embedding SDK bootstrap (R6)

**Call chain:** `run-memory-server.sh` reads `MEMORY_EMBEDDING_PROVIDER` from env → after `bootstrap_venv` completes → checks if SDK is importable → if not, runs `uv pip install {pkg}`.

In `run-memory-server.sh`:
1. Read `MEMORY_EMBEDDING_PROVIDER` from environment (set by MCP server config or `.env`)
2. After `bootstrap_venv` completes, if provider is set and matches a known provider, check if the SDK is importable
3. If not importable, run `uv pip install {pkg}` (e.g., `"google-genai>=1.0,<2"` for gemini)
4. If provider is empty or unknown, skip (current behavior)

`bootstrap-venv.sh` is NOT modified — it remains generic shared infrastructure.

## Files to Modify

| File | Change |
|------|--------|
| `plugins/pd/hooks/lib/semantic_memory/database.py` | Add `_sanitize_fts5_query()`, update `fts5_search()` |
| `plugins/pd/hooks/lib/semantic_memory/embedding.py` | Update `_load_dotenv_once()` with cwd fallback |
| `plugins/pd/mcp/run-memory-server.sh` | Source `.env`, export API keys, install provider SDK post-bootstrap |
| `plugins/pd/hooks/lib/semantic_memory/test_database.py` | Add tests for sanitizer and OR semantics (existing file — 829+ lines of FTS5 tests already present) |
| `plugins/pd/mcp/test_memory_server.py` | Add integration tests for multi-word and special char queries |

## Non-Goals

- No schema migrations needed
- No changes to the ranking module
- No changes to the MCP tool interface (search_memory signature unchanged)
- No embedding backfill automation
