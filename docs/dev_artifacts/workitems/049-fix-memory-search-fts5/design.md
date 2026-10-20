# Design: Fix memory search — FTS5 query sanitization and vector path recovery

## Prior Art Research

### Codebase patterns
- All `run-*.sh` scripts follow identical pattern: set vars → source `bootstrap-venv.sh` → call `bootstrap_venv` → exec Python
- `bootstrap_venv()` uses `uv pip install` with hardcoded `DEP_PIP_NAMES` array (NOT `uv sync`). No `.env` loading in shell
- Config loaded via `read_config(os.getcwd())` in Python; `memory_embedding_provider` defaults to `"gemini"`
- No FTS5 sanitization exists anywhere in the codebase; `fts5_search()` passes raw input to MATCH

### Industry standards (FTS5 sanitization)
- Canonical technique: double-quote each token to neutralize operators, then join with OR
- `sqlite-utils` provides `db.quote_fts()` — same approach: `'"' + s.replace('"', '""') + '"'`
- Datasette escapes all user input by default; raw query mode is opt-in
- SQL parameterization alone is insufficient — FTS5 still parses operators within bound values

## Architecture Overview

Three independent fixes addressing two retrieval paths:

```
┌─────────────────────────────────────────────────┐
│              search_memory (MCP)                 │
│                     │                            │
│         ┌──────────┴──────────┐                  │
│         ▼                     ▼                  │
│  ┌─────────────┐    ┌──────────────┐            │
│  │ FTS5 Path   │    │ Vector Path  │            │
│  │ (R1-R4)     │    │ (R5-R6)      │            │
│  │             │    │              │            │
│  │ sanitize →  │    │ .env load →  │            │
│  │ MATCH →     │    │ SDK install →│            │
│  │ log errors  │    │ embed →      │            │
│  └─────────────┘    └──────────────┘            │
│         │                     │                  │
│         └──────────┬──────────┘                  │
│                    ▼                             │
│            RankingPipeline                       │
└─────────────────────────────────────────────────┘
```

### Component 1: FTS5 Query Sanitizer (database.py)

New module-level function `_sanitize_fts5_query()` in `database.py`.

**Decision:** Per-token quoting + OR join (not whole-string quoting). Rationale: whole-string quoting creates a phrase match requiring terms in order, which is too restrictive for search. Per-token quoting with OR preserves BM25 ranking across individual term matches.

**FTS5 tokenizer note:** The `unicode61` tokenizer (used by `entries_fts`) splits on hyphens by default — meaning `anti-patterns` in the FTS index is stored as two tokens: `anti` and `patterns`. When the sanitizer produces `"anti-patterns"` (a quoted phrase), FTS5 matches documents containing `anti` immediately followed by `patterns`. This is correct behavior — it matches entries containing the hyphenated term.

### Component 2: .env + API Key Loading (run-memory-server.sh + embedding.py)

Shell-level `.env` sourcing in `run-memory-server.sh` (primary) + Python-level cwd fallback in `_load_dotenv_once()` (defense-in-depth).

**Decision:** Shell wrapper is primary fix because it runs before Python and is guaranteed to have cwd = project root (set by Claude Code MCP launch). Python cwd fallback is kept as defense-in-depth for non-MCP usage (e.g., direct CLI invocation).

### Component 3: Optional SDK Bootstrap (run-memory-server.sh)

Post-bootstrap `uv pip install` of provider SDK package in `run-memory-server.sh`.

**Decision:** Install in `run-memory-server.sh` AFTER `bootstrap_venv` completes, not inside `bootstrap-venv.sh`. Rationale: `bootstrap-venv.sh` is shared infrastructure for all servers — adding memory-server-specific embedding deps there would violate single-responsibility. The memory server wrapper knows which provider is needed.

## Technical Decisions

| Decision | Choice | Alternative | Rationale |
|----------|--------|-------------|-----------|
| Sanitizer location | `database.py` module-level function | Separate `sanitizer.py` module | Single file touched, function is ~20 lines, only one consumer (`fts5_search`) |
| OR vs AND after sanitization | OR semantics | AND semantics | Matches spec R1; OR returns more results, BM25 still ranks multi-match entries higher |
| Token quoting strategy | Quote only hyphenated tokens | Quote all tokens | Quoting all tokens would prevent prefix matching; only hyphens cause column-selector misparse |
| Standalone `-` handling | Drop `-`-only tokens at step 3 | Strip `-` chars from raw string | Stripping from raw string would remove intra-word hyphens before quoting step |
| .env primary mechanism | Shell-level sourcing | Python-level only | Shell runs first, guaranteed cwd = project root, no `.git` walk needed |
| .env sourcing scope | Export only known API key names | `set -a` (export all) | Avoids leaking unrelated vars to child processes |
| Optional SDK install location | `run-memory-server.sh` | `bootstrap-venv.sh` | Keeps shared bootstrap generic; only memory server needs embedding SDKs |
| Optional SDK install method | `uv pip install` after bootstrap | Extend `DEP_PIP_NAMES` | `DEP_PIP_NAMES` is shared by all servers; conditional install keeps it simple |

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Sanitizer strips meaningful query tokens | Low | Medium | Comprehensive test suite with real-world query examples from RCA |
| `.env` sourcing leaks vars to child processes | Low | Low | Only export known API key names (not `set -a`) |
| Optional SDK install adds latency to server start | Medium | Low | Only runs when SDK not already importable; `uv pip install` is fast for single packages |
| FTS5 tokenizer splits differently than our sanitizer | Low | Medium | Use same whitespace tokenization; FTS5 `unicode61` tokenizer handles the rest after our sanitized query reaches MATCH |
| `.env` has shell-incompatible syntax | Low | Low | Only grep/export specific known key names, don't source blindly |

## Interfaces

### 1. `_sanitize_fts5_query(raw: str) -> str`

**Location:** `plugins/pd/hooks/lib/semantic_memory/database.py`

```python
import re

# FTS5 metacharacters to strip (everything except intra-word hyphens)
_FTS5_STRIP_RE = re.compile(r'[./:>#*^~()+"]')

def _sanitize_fts5_query(raw: str) -> str:
    """Sanitize a raw query string for safe FTS5 MATCH usage.

    Pipeline:
    1. Strip FTS5 metacharacters (. / : # > * ^ ~ ( ) + ")
    2. Tokenize on whitespace
    3. Drop empty tokens and standalone-'-' tokens
    4. Double-quote tokens containing hyphens (phrase match for adjacency)
    5. Join with OR
    6. Return empty string if no valid tokens remain

    Examples:
        >>> _sanitize_fts5_query("firebase firestore typescript")
        'firebase OR firestore OR typescript'
        >>> _sanitize_fts5_query("anti-patterns")
        '"anti-patterns"'
        >>> _sanitize_fts5_query("source:session-capture")
        'source OR "session-capture"'
        >>> _sanitize_fts5_query("...")
        ''
    """
    # Step 1: strip metacharacters
    cleaned = _FTS5_STRIP_RE.sub(" ", raw)
    # Step 2-3: tokenize, drop empty and standalone-'-' tokens
    tokens = [t for t in cleaned.split() if t and t != "-"]
    # Step 4: quote hyphenated tokens
    quoted = [f'"{t}"' if "-" in t else t for t in tokens]
    # Step 5-6: join with OR or return empty
    return " OR ".join(quoted)
```

**Caller:** `fts5_search()` calls this before passing to MATCH. If result is empty string, returns `[]` immediately without executing SQL.

### 2. Updated `fts5_search()` signature (unchanged externally)

```python
def fts5_search(self, query: str, limit: int = 100) -> list[tuple[str, float]]:
    if not self._fts5_available:
        return []

    sanitized = _sanitize_fts5_query(query)
    if not sanitized:
        return []

    try:
        cur = self._conn.execute(
            "SELECT e.id, -rank AS score "
            "FROM entries_fts f "
            "JOIN entries e ON e.rowid = f.rowid "
            "WHERE entries_fts MATCH ? "
            "ORDER BY score DESC "
            "LIMIT ?",
            (sanitized, limit),
        )
        return [(row[0], float(row[1])) for row in cur.fetchall()]
    except sqlite3.OperationalError as e:
        print(
            f"semantic_memory: FTS5 error for query {query!r}: {e}",
            file=sys.stderr,
        )
        return []
```

### 3. Updated `_load_dotenv_once()` (embedding.py)

```python
def _load_dotenv_once() -> None:
    """Load .env — checks env vars first, then cwd, then .git walk-up.

    Tries multiple strategies to find API keys:
    1. If any known key already in env, skip (already available)
    2. Try .env in cwd (MCP servers launched with cwd = project root)
    3. Walk up from __file__ looking for .git (dev workspace)

    Both cwd and .git walk-up run (load_dotenv with override=False is
    additive and idempotent), maximizing chances of finding the key.
    """
    if load_dotenv is None or getattr(_load_dotenv_once, "_done", False):
        return
    _load_dotenv_once._done = True

    # Fast path: if any known API key is already in env, skip dotenv
    known_keys = ("GEMINI_API_KEY", "OPENAI_API_KEY", "VOYAGE_API_KEY")
    if any(os.environ.get(k) for k in known_keys):
        return

    # Try cwd first (MCP servers launched with cwd = project root)
    cwd_env = Path(os.getcwd()) / ".env"
    if cwd_env.is_file():
        load_dotenv(cwd_env, override=False)

    # Also try .git walk-up (additive — override=False won't overwrite)
    d = Path(__file__).resolve().parent
    while d != d.parent:
        if (d / ".git").exists():
            env_file = d / ".env"
            if env_file.is_file():
                load_dotenv(env_file, override=False)
            return
        d = d.parent
```

**Key change from v1 design:** No early `return` after cwd `.env` load. Both cwd and `.git` walk-up paths run, since `load_dotenv(override=False)` is additive and idempotent. This handles the case where cwd `.env` exists but doesn't contain the API key.

### 4. Updated `run-memory-server.sh`

```bash
#!/bin/bash
# Bootstrap and run the MCP memory server.
# Uses shared bootstrap-venv.sh for coordinated venv creation.
#
# Called by Claude Code via plugin.json mcpServers — do NOT write to stdout
# (would corrupt MCP stdio protocol). All diagnostics go to stderr.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PLUGIN_DIR/.venv"
SERVER_SCRIPT="$SCRIPT_DIR/memory_server.py"

export PYTHONPATH="$PLUGIN_DIR/hooks/lib${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

# --- .env loading (R5) ---
# Export only known API key vars from project .env (cwd = project root)
if [ -f ".env" ]; then
    for _key in GEMINI_API_KEY OPENAI_API_KEY VOYAGE_API_KEY MEMORY_EMBEDDING_PROVIDER; do
        _val=$(grep -E "^${_key}=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/^["'"'"']//;s/["'"'"']$//')
        if [ -n "$_val" ]; then
            export "$_key=$_val"
        fi
    done
fi

source "$SCRIPT_DIR/bootstrap-venv.sh"
bootstrap_venv "$VENV_DIR" "memory-server"

# --- Optional embedding SDK (R6) ---
# MEMORY_EMBEDDING_PROVIDER may come from .env or MCP server env config
_PROVIDER="${MEMORY_EMBEDDING_PROVIDER:-}"
if [ -n "$_PROVIDER" ]; then
    case "$_PROVIDER" in
        gemini)  _PKG="google-genai>=1.0,<2"; _IMPORT="google.genai" ;;
        openai)  _PKG="openai>=1.0,<3"; _IMPORT="openai" ;;
        voyage)  _PKG="voyageai>=0.3,<1"; _IMPORT="voyageai" ;;
        ollama)  _PKG="ollama>=0.4,<1"; _IMPORT="ollama" ;;
        *)       _PKG=""; _IMPORT="" ;;
    esac
    if [ -n "$_PKG" ] && [ -n "$_IMPORT" ]; then
        if ! "$PYTHON" -c "import $_IMPORT" 2>/dev/null; then
            echo "memory-server: installing ${_PROVIDER} SDK..." >&2
            uv pip install --python "$PYTHON" "$_PKG" >&2 || \
                echo "memory-server: WARNING: failed to install ${_PROVIDER} SDK" >&2
        fi
    fi
fi

exec "$PYTHON" "$SERVER_SCRIPT" "$@"
```

**Changes from current:**
- Selective `.env` key export via grep (not `set -a; source .env`) — avoids shell-incompatible syntax and var leakage
- Post-bootstrap SDK install with correct import-to-package mapping
- Install errors shown on stderr (not suppressed) for debuggability

## Dependencies

```
R1-R3 (sanitizer) ─── independent, no deps
R4 (logging) ──────── independent, trivial
R5 (.env loading) ─── independent of R1-R4
R6 (SDK install) ──── depends on R5 (.env must be sourced first to read MEMORY_EMBEDDING_PROVIDER)
```

All FTS5 fixes (R1-R4) are independent of vector path fixes (R5-R6). Can be implemented and tested in parallel.
