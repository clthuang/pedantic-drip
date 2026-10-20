# Design: Semantic Memory System

## Prior Art Research

### Codebase Patterns

| Pattern | Location | Design Impact |
|---------|----------|---------------|
| `memory.py` parsing/dedup/selection pipeline | `hooks/lib/memory.py` | Preserve `content_hash()` formula for import dedup compatibility. New system replaces `select_entries()` with semantic ranking but keeps identical output format |
| Session-start 3-second timeout wrapper | `session-start.sh:234-246` | New injector invoked identically: `$timeout_cmd python3 ...`. Stderr suppressed. Failure = `memory_output=""` |
| Config via YAML frontmatter | `common.sh:88-103` (`read_local_md_field`) | New Python config reader must parse same format: `grep "^field:" then extract value then default if missing` |
| MCP registration in `.mcp.json` | `.mcp.json` (project root) | Add `memory-server` entry alongside existing `playwright` entry |
| Retro knowledge bank writes | `retrospecting/SKILL.md:163-252` | Extend Step 4 to dual-write: existing markdown + SQLite INSERT. Step 4c global promotion writes to both stores |
| No existing SQLite or numpy usage | Full codebase scan | First SQLite + numpy integration — need pyproject.toml, uv dependency setup |
| Hook test infrastructure | `hooks/tests/test-hooks.sh` | Bash test framework exists; Python tests need their own runner |

### External Research

| Finding | Source | Design Decision |
|---------|--------|-----------------|
| `np.float32.tobytes()` for BLOB serialization | sqlite-vec docs, numpy community | Use `tobytes()` for write, `np.frombuffer(blob, dtype=np.float32)` for read. 768 dims = 3072 bytes per BLOB. No serialization overhead, no security concerns |
| Gemini taskType: RETRIEVAL_DOCUMENT (write) / RETRIEVAL_QUERY (query) | Google AI docs | Asymmetric embedding critical for retrieval quality — never use SEMANTIC_SIMILARITY for retrieval |
| L2 normalization required for Gemini 768-dim output | Google AI docs | Normalize all embeddings post-generation before storage. Pre-normalized vectors make cosine similarity = dot product |
| MCP Python: FastMCP + `@mcp.tool()` + `mcp.run(transport='stdio')` | MCP Python SDK | Use FastMCP with lifespan handler for DB connection. Never write to stdout (corrupts JSON-RPC) |
| Cosine similarity as dot product on pre-normalized vectors: `scores = matrix @ query_vector` | simonw/llm, numpy BLAS | Load all embeddings into matrix at query time; single matmul = all similarities in <5ms |
| RRF (Reciprocal Rank Fusion) avoids score normalization issues | Hybrid search best practices | Spec mandates min-max normalization — follow spec, but note RRF as future optimization if score distributions prove problematic |
| SQLite WAL: `synchronous=NORMAL`, short write transactions | charlesleifer.com | Set WAL + busy_timeout=5000 at connection open. Each connection sets PRAGMAs (only journal_mode persists) |
| Keyword extraction prompt: constrain to JSON array, provide stopword list, few-shot examples | KeyLLM, content enrichment research | Design specific prompt template below |

## Architecture Overview

```
SESSION START (query path, 3-second budget):

  session-start.sh
       |
       v
  MemoryInjector -----> ConfigReader
  (main entry)
       |
   +---+------+
   v          v
Database   RetrievalPipeline
             |
   +---------+---------+
   v                   v
Vector retrieval    Keyword retrieval
(EmbeddingProvider  (FTS5 MATCH)
 + numpy matmul)
       |                   |
       +-------+-------+
               v
         RankingEngine
         (score + select)
               |
               v
         Formatted output -> stdout


WRITE PATHS:

  Retro Skill -------+    MCP Server ------+    Import --------+
  (dual-write)       |    (store_memory)   |    (first-run)    |
                     v                     v                   v
               +------------------------------------------+
               |              Database                     |
               |  entries | entries_fts | _metadata        |
               +------------------------------------------+
                     |                     |
                     v                     v
               EmbeddingProvider    KeywordGenerator
               (write-time)         (write-time)
```

## Components

### C1: MemoryDatabase

SQLite database wrapper managing all persistence. Single file at `~/.claude/iflow/memory/memory.db`.

**Responsibilities:**
- Schema creation and migration (versioned via `_metadata.schema_version`)
- CRUD operations for memory entries
- FTS5 virtual table management (auto-synced with entries table via triggers)
- FTS5 availability detection (compile-time optional extension)
- Embedding BLOB storage and bulk loading
- Metadata tracking (provider, model, dimensions, schema version)
- Connection management (WAL mode, busy_timeout, PRAGMAs)

**FTS5 availability detection:** At `__init__()`, attempt `CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_test USING fts5(x); DROP TABLE _fts5_test;` inside a try/except. If OperationalError, set `self.fts5_available = False` and log to stderr (`print("Warning: FTS5 not available, keyword search disabled", file=sys.stderr)`). Skip FTS5 virtual table creation and trigger setup in migrations. RetrievalPipeline checks `db.fts5_available` before calling `fts5_search()`. macOS system Python and Homebrew Python both ship with FTS5; this is a safeguard for unusual Linux builds.

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    reasoning TEXT,
    category TEXT NOT NULL CHECK(category IN ('anti-patterns', 'patterns', 'heuristics')),
    keywords TEXT,          -- JSON array string
    "references" TEXT,      -- JSON array string (quoted: reserved word)
    observation_count INTEGER DEFAULT 1,
    confidence TEXT DEFAULT 'medium' CHECK(confidence IN ('high', 'medium', 'low')),
    recall_count INTEGER DEFAULT 0,
    last_recalled_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('retro', 'session-capture', 'manual', 'import')),
    source_project TEXT,
    embedding BLOB          -- float32 tobytes(), 768 dims = 3072 bytes
);

CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    name, description, keywords, reasoning,
    content='entries',
    content_rowid='rowid'
);

-- Keep FTS5 in sync via triggers (strip JSON array syntax from keywords for clean tokenization)
CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, name, description, keywords, reasoning)
    VALUES (new.rowid, new.name, new.description,
            REPLACE(REPLACE(REPLACE(REPLACE(new.keywords, '["', ''), '"]', ''), '","', ' '), '"', ''),
            new.reasoning);
END;

CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, name, description, keywords, reasoning)
    VALUES ('delete', old.rowid, old.name, old.description,
            REPLACE(REPLACE(REPLACE(REPLACE(old.keywords, '["', ''), '"]', ''), '","', ' '), '"', ''),
            old.reasoning);
END;

CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
    INSERT INTO entries_fts(entries_fts, rowid, name, description, keywords, reasoning)
    VALUES ('delete', old.rowid, old.name, old.description,
            REPLACE(REPLACE(REPLACE(REPLACE(old.keywords, '["', ''), '"]', ''), '","', ' '), '"', ''),
            old.reasoning);
    INSERT INTO entries_fts(rowid, name, description, keywords, reasoning)
    VALUES (new.rowid, new.name, new.description,
            REPLACE(REPLACE(REPLACE(REPLACE(new.keywords, '["', ''), '"]', ''), '","', ' '), '"', ''),
            new.reasoning);
END;

CREATE TABLE IF NOT EXISTS _metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Initial metadata: schema_version=1, embedding_provider, embedding_model, embedding_dimensions
```

**Connection setup** (every connection):
```python
conn = sqlite3.connect(db_path, timeout=5.0)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA busy_timeout=5000")
conn.execute("PRAGMA cache_size=-8000")  # 8MB
```

### C2: EmbeddingProvider (Protocol + Adapters)

Adapter pattern for multiple embedding APIs. Single provider used for both write-time and query-time.

**Adapters:**
- `GeminiProvider` — Default. Uses `google-genai` SDK. Sets `output_dimensionality=768`, appropriate `taskType`.
- `VoyageProvider` — Code-specialized. Uses `voyageai` SDK.
- `OpenAIProvider` — Uses `openai` SDK.
- `OllamaProvider` — Local, no API key needed. Uses HTTP API at `localhost:11434`.

All adapters return L2-normalized float32 numpy arrays. Normalization is enforced centrally via a `create_provider()` factory function that wraps any adapter in a `NormalizingWrapper`. The wrapper calls the adapter's raw `embed()`, then L2-normalizes the result. This prevents individual adapters from forgetting normalization — the Protocol defines the raw contract, the wrapper enforces post-processing. Normalizing a pre-normalized vector is a no-op (norm ≈ 1.0, division is identity).

### C3: KeywordGenerator (Protocol + Tiered Implementation)

Tiered keyword generation with 5-second timeout per tier.

**Tiers (in order):**
1. **In-session Claude** — During retros only. Keywords are produced by the retro-facilitator agent as part of its output (no separate API call). NOT available for MCP captures or imports.
2. **Claude API (Haiku)** — Fast, cheap API call. Used as first tier for MCP-captured entries and imports (since in-session Claude is unavailable outside retros).
3. **Ollama local** — Fallback for offline operation.
4. **Skip** — Store entry without keywords; FTS5 indexes name/description directly.

**Context-aware keyword source (NOT tier selection — retros bypass TieredKeywordGenerator entirely):**
- **Retro context:** Keywords are EXTRACTED from retro-facilitator agent output (already produced by the model during analysis). No TieredKeywordGenerator call is made. The model produces keywords as part of its structured JSON response (see TD6 modified output schema). If the agent response is missing keyword/reasoning fields (backward compatibility), SKILL.md Step 4 defaults to empty keywords and empty reasoning — no fallback to TieredKeywordGenerator.
- **MCP capture context:** TieredKeywordGenerator is called starting at tier 2 (Haiku API). Tier 1 (in-session Claude) is NOT available outside retros.
- **Import context:** TieredKeywordGenerator is called starting at tier 2 (Haiku API). For batch imports, keywords may be skipped entirely (tier 4) to avoid API rate limits.

**Keyword generation prompt** (used by TieredKeywordGenerator and referenced by retro-facilitator agent modification):
```
Extract 3-10 keyword labels from this knowledge bank entry.

Title: {name}
Content: {description}
Reasoning: {reasoning}
Category: {category}

Return ONLY a JSON array of lowercase keyword strings. Example: ["fts5", "sqlite", "content-hash", "parser-error"]

Rules:
- Use specific technical terms from the content (tool names, patterns, file types, techniques)
- 1-3 words per keyword, lowercase, hyphenated if multi-word
- EXCLUDE these generic words: code, development, software, system, application, implementation, feature, project, function, method, file, data, error, bug, fix, update, change
- Minimum 3, maximum 10 keywords
```

**FTS5 keyword storage:** The `keywords` column in the `entries` table stores a JSON array string for programmatic access. However, the FTS5 trigger converts the JSON array to a space-separated string before indexing to avoid JSON punctuation noise in the token stream:

```sql
CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, name, description, keywords, reasoning)
    VALUES (new.rowid, new.name, new.description,
            REPLACE(REPLACE(REPLACE(REPLACE(new.keywords, '["', ''), '"]', ''), '","', ' '), '"', ''),
            new.reasoning);
END;
```

This strips JSON array syntax (`["`, `"]`, `","`, `"`) leaving clean space-separated keywords for FTS5 tokenization. The same transformation applies to the UPDATE and DELETE triggers.

**Important:** The REPLACE chain applies ONLY to the `keywords` column (JSON array string). The `reasoning` column is indexed by FTS5 as raw text — if reasoning contains JSON syntax (e.g., "Discovered pattern: {\"key\": \"value\"}"), FTS5 indexes it with JSON characters intact. This is correct behavior: reasoning is free-form text, not structured data.

**Defensive per-keyword filtering in KeywordGenerator:** Before storing, validate each keyword individually against `^[a-z0-9][a-z0-9-]*$` (lowercase alphanumeric, optional hyphens). Filter out any keyword containing `[`, `]`, `"`, `,`, or other JSON-special characters — keep keywords that pass, discard only those that fail. If zero keywords pass validation, store entry with empty keywords array (FTS5 indexes name/description directly). This per-keyword approach avoids discarding 9 valid keywords because 1 fails validation.

### C4: RetrievalPipeline

Finds candidate entries from the database. Does NOT rank — produces raw scored candidate sets.

**Step 1: Context signal collection** (`collect_context` pseudocode):
```python
def collect_context(project_root: str) -> str | None:
    signals = []

    # 1. Find active feature
    meta_files = glob("docs/features/*/.meta.json", root=project_root)
    active = []
    for m in meta_files:
        try:
            data = json.load(open(m))
            if data.get("status") == "active":
                active.append(m)
        except (json.JSONDecodeError, KeyError, IOError) as e:
            print(f"Warning: skipping {m}: {e}", file=sys.stderr)
            continue  # Skip invalid/unreadable .meta.json files
    if len(active) > 1:
        # Pick most recently created (highest numeric ID prefix)
        import re
        active.sort(key=lambda m: int(re.search(r'/(\d+)-', m).group(1)), reverse=True)
    meta = json.load(active[0]) if active else None

    if meta:
        # 2. Feature name from slug
        signals.append(meta["slug"])

        # 3. Feature description: first paragraph of spec.md, or prd.md if spec unavailable
        feature_dir = os.path.dirname(active[0])
        spec_path = os.path.join(feature_dir, "spec.md")
        prd_path = os.path.join(feature_dir, "prd.md")
        desc_path = spec_path if os.path.exists(spec_path) else (prd_path if os.path.exists(prd_path) else None)
        if desc_path:
            text = open(desc_path).read()
            first_para = text.split("\n## ")[0].strip()
            # Truncate to 100 words
            words = first_para.split()[:100]
            signals.append(" ".join(words))

        # 4. Phase
        signals.append(f"Phase: {meta.get('lastCompletedPhase', 'unknown')}")

    # 5. Git diff filenames
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~3..HEAD"],
            capture_output=True, text=True, timeout=2, cwd=project_root
        )
        files = result.stdout.strip().split("\n")[:20]
        if files and files[0]:
            signals.append(f"Files: {' '.join(files)}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~1..HEAD"],
                capture_output=True, text=True, timeout=2, cwd=project_root
            )
            files = result.stdout.strip().split("\n")[:20]
            if files and files[0]:
                signals.append(f"Files: {' '.join(files)}")
        except Exception:
            pass  # No git signals

    if not signals:
        return None
    return ". ".join(signals)
```

**Step 2: Multi-signal retrieval** — Vector retrieval (numpy matmul) + keyword retrieval (FTS5 MATCH)
**Step 3: Merge** — Union candidates; entries found by both carry both scores

### C5: RankingEngine

Scores candidates and produces the final ordered selection.

**Inputs:** Merged candidate set with `vector_score` and `bm25_score`, plus entry metadata from DB.
**Output:** Ordered list of entries, category-balanced, within injection limit.

Scoring formula, normalization, edge cases, and category-balanced selection as defined in spec D3.

**Prominence sub-component formula** (spec D3 lists four sub-components but not their combination):
```python
prominence_score = (
    0.3 * normalized_obs_count +      # observation_count / max(observation_count)
    0.2 * normalized_confidence +       # high=1.0, medium=0.67, low=0.33
    0.3 * recency_decay +              # 1.0 / (1.0 + days_since_updated / 30.0)
    0.2 * recall_frequency             # min(recall_count / 10.0, 1.0)
)
```

Rationale: Observation count and recency are the strongest signals (0.3 each) — they represent empirical evidence (how often seen) and temporal relevance (how recent). Confidence and recall frequency are secondary (0.2 each) — confidence is a subjective tag, recall frequency bootstraps slowly for new entries.

**First-session edge case:** After initial import, all entries have `observation_count=1` and `recall_count=0`. Prominence differentiation comes only from `confidence` (high=1.0, medium=0.67, low=0.33) and `recency` (days since `updated_at`). If all imported entries share the same confidence and update date, prominence is identical for all — ranking is determined entirely by vector/keyword relevance. This is correct: prominence is a tiebreaker when entries have different observation histories.

### C6: MemoryServer (MCP)

Standalone Python MCP server exposing `store_memory` tool via stdio transport.

**Registration:** Added to project root `.mcp.json` alongside existing entries.

**Lifecycle:** Opens DB connection on startup (lifespan handler), closes on shutdown. Generates embedding and keywords synchronously per capture.

**Async/sync note:** Tool handlers are `async def` per FastMCP convention, but sqlite3 calls are synchronous. This is acceptable for a stdio single-connection server processing one request at a time. No concurrent requests occur. If future tools need concurrency, wrap DB calls in `asyncio.to_thread()`.

### C7: MarkdownImporter

One-time import of existing knowledge bank markdown entries into SQLite. Runs on first invocation when DB is empty (no entries in `entries` table). Uses same parsing logic as current `memory.py:parse_entries()` for format compatibility.

**Two-phase import strategy** (avoids API calls at session start):
1. **Phase 1 (synchronous, at session start):** Parse markdown files and INSERT all entries into DB WITHOUT embeddings (`embedding = NULL`). No API calls. This is fast (<100ms for 50 entries). FTS5 is immediately populated via triggers, so keyword retrieval works on first session.
2. **Phase 2 (deferred, triggered by ANY write-path):** Generate embeddings for entries with `embedding IS NULL` in batches of 50 per invocation. This triggers on retro dual-writes, MCP captures, or any DB write-path — NOT only retros. If the user never runs a retro but uses MCP capture, Phase 2 still progresses. Each write-path invocation checks `SELECT COUNT(*) FROM entries WHERE embedding IS NULL` and processes up to 50 entries if any are pending.

**Bootstrapping tracking:** `_metadata` key `pending_embeddings` stores the count of entries awaiting embeddings. Updated after each batch. The diagnostic line shows `pending_embedding: N` when entries await embeddings. When `pending_embeddings` reaches 0, the system is fully bootstrapped.

### C8: RecallTracker

Thin utility inlined into `injector.py` (not a separate module). After injection, batch-updates `recall_count` and `last_recalled_at` for all injected entries via `db.update_recall(entry_ids, timestamp)`. Single UPDATE query with entry IDs. No separate interface — the logic is 3-4 lines calling `MemoryDatabase.update_recall()` in the injector's step 6.

## Technical Decisions

### TD1: Package Structure

```
plugins/iflow-dev/
  hooks/lib/
    memory.py              # PRESERVED — MD-based fallback
    semantic_memory/       # NEW package
      __init__.py          # Package init, version, content_hash() utility
      database.py          # C1: MemoryDatabase
      embedding.py         # C2: EmbeddingProvider protocol + adapters
      keywords.py          # C3: KeywordGenerator
      retrieval.py         # C4: RetrievalPipeline
      ranking.py           # C5: RankingEngine
      importer.py          # C7: MarkdownImporter
      config.py            # Config reading from iflow-dev.local.md
      injector.py          # Query entry point (session-start.sh, replaces memory.py)
      writer.py            # Write entry point (SKILL.md Step 4 via Bash tool)
  mcp/
    memory-server.py       # C6: MCP server (standalone, imports from semantic_memory)
  hooks/
    session-start.sh       # MODIFIED — branch on memory_semantic_enabled
```

**Rationale:** Flat package (no nested sub-packages) keeps imports simple. Each file maps 1:1 to a component. `injector.py` is the CLI entry point called from session-start.sh. `memory-server.py` is the MCP entry point, importing shared modules.

**Shared utility — `content_hash()`:** The content hash formula (`SHA-256(" ".join(description.lower().strip().split()))[:16]`) is defined once in `__init__.py` and imported by all components that compute entry IDs: `MemoryDatabase.upsert_entry()`, `MemoryServer.store_memory()`, `MemoryWriter`, and `MarkdownImporter`. This prevents inconsistent hash implementations across components.

### TD2: Embedding BLOB Serialization

**Format:** `numpy.ndarray.astype(np.float32).tobytes()` stored as SQLite BLOB.
**Read:** `np.frombuffer(blob, dtype=np.float32)` produces a 768-element array.

768 dims x 4 bytes = 3072 bytes per embedding. At 10K entries = ~30MB of embedding data.

**Rationale:** Simplest and fastest approach. Same format sqlite-vec uses internally. No serialization overhead or security concerns.

### TD3: Query-Time Embedding Matrix Loading

At query time, load ALL embeddings from DB into a single numpy matrix:

```python
rows = db.execute("SELECT id, embedding FROM entries WHERE embedding IS NOT NULL")
ids, blobs = zip(*rows)
matrix = np.vstack([np.frombuffer(b, dtype=np.float32) for b in blobs])
# matrix shape: (N, 768), already L2-normalized at write time
```

Then compute all similarities in one operation:
```python
query_embedding = provider.embed(context_query)  # (768,), L2-normalized
scores = matrix @ query_embedding  # (N,) dot products = cosine similarities
```

**No caching across sessions.** Each session start loads fresh from DB. At 10K entries, loading + matmul < 50ms total. Caching adds complexity (invalidation on writes from MCP/retro) for negligible benefit.

**MCP server caching:** The MCP server (long-running process) CAN cache the matrix in memory and append new vectors. But for the session-start query path, fresh load is simpler and fast enough.

### TD4: Session-Start Hook Integration

```bash
# In session-start.sh build_memory_context():
build_memory_context() {
    local config_file="${PROJECT_ROOT}/.claude/iflow-dev.local.md"
    local enabled
    enabled=$(read_local_md_field "$config_file" "memory_injection_enabled" "true")
    if [[ "$enabled" != "true" ]]; then
        return
    fi

    local semantic_enabled
    semantic_enabled=$(read_local_md_field "$config_file" "memory_semantic_enabled" "true")

    local limit
    limit=$(read_local_md_field "$config_file" "memory_injection_limit" "20")
    [[ "$limit" =~ ^-?[0-9]+$ ]] || limit="20"

    local timeout_cmd=""
    if command -v gtimeout >/dev/null 2>&1; then
        timeout_cmd="gtimeout 3"
    elif command -v timeout >/dev/null 2>&1; then
        timeout_cmd="timeout 3"
    fi

    # Resolve Python with uv venv if available
    local python_cmd="python3"
    local plugin_dir
    plugin_dir="$(cd "${SCRIPT_DIR}/.." && pwd)"
    if [[ -f "${plugin_dir}/.venv/bin/python" ]]; then
        python_cmd="${plugin_dir}/.venv/bin/python"
    fi

    local memory_output
    if [[ "$semantic_enabled" == "true" ]]; then
        # Semantic pipeline (needs numpy + provider SDKs from venv)
        memory_output=$($timeout_cmd "$python_cmd" \
            "${SCRIPT_DIR}/lib/semantic_memory/injector.py" \
            --project-root "$PROJECT_ROOT" \
            --limit "$limit" \
            --global-store "$HOME/.claude/iflow/memory" 2>/dev/null) || memory_output=""
    else
        # MD-based fallback (stdlib only, works with any python3)
        memory_output=$($timeout_cmd python3 \
            "${SCRIPT_DIR}/lib/memory.py" \
            --project-root "$PROJECT_ROOT" \
            --limit "$limit" \
            --global-store "$HOME/.claude/iflow/memory" 2>/dev/null) || memory_output=""
    fi
    echo "$memory_output"
}
```

**Key decisions:**
- The toggle is at the bash level. Both paths produce identical output format (markdown text to stdout).
- The 3-second timeout wraps whichever path runs.
- **Python environment resolution:** The semantic pipeline uses the venv at `plugins/iflow-dev/.venv/bin/python` (created by `uv sync`). This venv contains numpy and provider SDKs. The MD-based fallback uses bare `python3` since it needs only stdlib.
- If the venv doesn't exist, `$python_cmd` falls back to bare `python3`. The injector handles `ImportError` for numpy gracefully (skips vector retrieval, uses FTS5+prominence).

### TD5: Python Config Reader

Python reimplementation of `common.sh:read_local_md_field`:

```python
def read_config(project_root: str) -> dict:
    """Read config from .claude/iflow-dev.local.md. Matches bash read_local_md_field."""
    config_path = os.path.join(project_root, ".claude", "iflow-dev.local.md")
    defaults = {
        "memory_semantic_enabled": True,
        "memory_vector_weight": 0.5,
        "memory_keyword_weight": 0.2,
        "memory_prominence_weight": 0.3,
        "memory_embedding_provider": "gemini",
        "memory_embedding_model": "gemini-embedding-001",
        "memory_keyword_provider": "auto",
        "memory_injection_limit": 20,
    }
    # Scan ALL lines for "key: value" patterns (no --- delimiter awareness)
    # Matches bash: grep "^${field}:" "$file" | head -1 | sed 's/^[^:]*: *//' | tr -d ' '
    # Return merged defaults + parsed values
```

No YAML library dependency — simple line-by-line `grep "^field:"` scanning of the entire file, matching the bash `read_local_md_field` implementation exactly.

**Type coercion rules** (matching bash `read_local_md_field` behavior including `tr -d ' '` space stripping):
- Strip ALL spaces from raw values including internal spaces (matches bash `tr -d ' '`). Example: `gemini embedding 001` becomes `geminiembedding001`. Config values must not contain meaningful spaces — use hyphens instead (e.g., `gemini-embedding-001`).
- `"true"` / `"false"` → Python `bool`
- Values matching `^-?[0-9]+$` → `int`
- Values matching `^-?[0-9]*\.[0-9]+$` → `float`
- Everything else → `str`
- Missing keys → use default from defaults dict (preserving default's type)

### TD6: Retrospective Dual-Write Integration

The retrospecting skill's Step 4 is extended. After writing each entry to markdown (existing behavior), also write to SQLite:

```
Step 4 (extended):
  For each entry from retro-facilitator act section:
    1. Write to markdown file (EXISTING — unchanged)
    2. If memory_semantic_enabled:
       a. Extract keywords and reasoning from retro-facilitator agent response
          (already produced by the model — no separate generation step)
          If keywords/reasoning fields missing (backward compat): defaults to [] and ""
       b. Build entry JSON with all fields (name, description, reasoning, category,
          keywords, references from git diff, source="retro", source_project)
       c. Invoke writer CLI via Bash tool:
          $python_cmd "${plugin_dir}/hooks/lib/semantic_memory/writer.py" \
            --action upsert \
            --global-store "$HOME/.claude/iflow/memory" \
            --entry-json '{"name":"...","description":"...","reasoning":"...",
              "category":"patterns","keywords":["k1","k2"],"references":["file.py"],
              "source":"retro","source_project":"my-project"}'
       d. writer.py handles: content hash computation, DB upsert (increment
          observation_count if exists), embedding generation via configured
          provider, and Phase 2 pending embedding processing (batch of 50)
```

**Invocation mechanism:** SKILL.md Step 4 uses the Bash tool to call `writer.py` — a CLI entry point analogous to `injector.py` for session-start.sh. The orchestrating agent constructs the entry JSON from the retro-facilitator's response and passes it as a CLI argument. This avoids inline Python and keeps the interface explicit.

**writer.py CLI interface:**
```
Usage: writer.py --action upsert --global-store PATH --entry-json JSON
       writer.py --action upsert --global-store PATH --entry-file PATH

Actions:
  upsert   Insert new entry or update existing (increment observation_count)

Exit codes: 0 = success, 1 = validation error (stderr), 2 = DB error (stderr)
```

The `--entry-file` variant accepts a path to a JSON file, useful when the entry JSON is too large for a command-line argument (Bash arg length limits). SKILL.md Step 4 can use either form.

**Keyword source during retros:** Keywords are EXTRACTED from the retro-facilitator agent's JSON output (the model already produced them as part of its analysis). No TieredKeywordGenerator call is made during retros. The TieredKeywordGenerator is only used for MCP captures and imports, starting at tier 2 (Haiku API).

**In-session keyword generation:** The retro-facilitator agent prompt is modified to produce keywords and reasoning alongside its existing output. This is free (model already running) and produces highest quality keywords since it has full feature context.

**File to modify:** `plugins/iflow-dev/agents/retro-facilitator.md`

Add to the Act section output instructions (after the existing text/provenance/confidence fields):
```
For each entry in act.patterns, act.anti_patterns, and act.heuristics, include:
- keywords: array of 3-10 lowercase keyword strings. Use specific technical terms from the content (tool names, patterns, file types, techniques). 1-3 words per keyword, lowercase, hyphenated if multi-word. EXCLUDE these generic words: code, development, software, system, application, implementation, feature, project, function, method, file, data, error, bug, fix, update, change.
- reasoning: string explaining WHY this matters and HOW it was discovered (1-2 sentences)
```

These keyword quality constraints match the TieredKeywordGenerator prompt template (C3), ensuring consistent keyword quality regardless of generation path.

Modified output schema:
```json
{
  "act": {
    "patterns": [
      {
        "text": "...",
        "provenance": "...",
        "confidence": "...",
        "keywords": ["keyword1", "keyword2"],
        "reasoning": "Why this conclusion was reached"
      }
    ]
  }
}
```

The orchestrating retrospecting skill (SKILL.md Step 4) extracts `keywords` and `reasoning` from the agent response and passes them to the database write. If fields are missing (backward compatibility), defaults to empty keywords and empty reasoning.

**Step 4c (global promotion) interaction with SQLite:**
- All entries go into the single global SQLite DB regardless of local/universal classification
- The `universal` vs `project-specific` classification maps to `source_project`: NULL for universal entries, set to project name for project-specific entries
- Markdown dual-write continues to both local (`docs/dev_artifacts/knowledge-bank/`) and global (`~/.claude/iflow/memory/`) for the audit trail, matching current behavior unchanged
- The SQLite upsert uses content hash for dedup — same entry from local and global markdown resolves to one DB row
- When Step 4c promotes a local entry to global, the DB entry already exists (written in Step 4). The global markdown write is the only new action

### TD7: MCP Server Registration

Add to project root `.mcp.json`:
```json
{
  "mcpServers": {
    "playwright": { "..." : "..." },
    "memory-server": {
      "command": "plugins/iflow-dev/.venv/bin/python",
      "args": ["plugins/iflow-dev/mcp/memory-server.py"]
    }
  }
}
```

**Python environment:** The MCP server uses the venv Python directly (same venv as session-start). This ensures numpy, mcp, and provider SDKs are available.

**Path resolution assumption:** The `.mcp.json` lives at this project's root (`my-ai-setup/.mcp.json`). The relative path `plugins/iflow-dev/.venv/bin/python` resolves from there. This is private tooling with a single installation point — the path is always correct.

**Package import — two entry points with different import resolution:**
- `injector.py` lives inside `hooks/lib/semantic_memory/` and uses standard relative imports (`from .database import MemoryDatabase`)
- `memory-server.py` lives in `mcp/` and uses sys.path insertion to reach the shared package:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
from semantic_memory.database import MemoryDatabase
from semantic_memory.embedding import create_provider
```
Both paths should have import smoke tests in their respective startup sequences (fail fast with clear error message if semantic_memory package is unreachable).

### TD8: Database Migration Strategy

Migrations tracked via `_metadata.schema_version`:

```python
MIGRATIONS = {
    1: create_initial_schema,  # entries, entries_fts, _metadata, triggers
}

def migrate(conn):
    current = get_schema_version(conn)  # 0 if _metadata doesn't exist
    for version in sorted(MIGRATIONS):
        if version > current:
            MIGRATIONS[version](conn)
            set_schema_version(conn, version)
    conn.commit()
```

Future schema changes add entries to MIGRATIONS dict. Each migration is idempotent (uses `IF NOT EXISTS`).

### TD9: Provider Change Detection and Re-embedding

On every write-path invocation (retro, MCP capture, or import):
1. Read `_metadata.embedding_provider` and `_metadata.embedding_model`
2. Compare against current config
3. If changed:
   - Update `_metadata` with new provider/model/dimensions
   - Mark all existing embeddings as stale (set `embedding = NULL`)
   - Re-embed in batches of 50 per write-path invocation
   - On HTTP 429: stop re-embedding, resume next write-path invocation
4. Entries with `embedding IS NULL` fall back to keyword-only retrieval

### TD10: Dependency Management

```toml
# plugins/iflow-dev/pyproject.toml (NEW)
[project]
name = "iflow-dev-hooks"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = [
    "numpy>=1.24",
]

[project.optional-dependencies]
mcp = ["mcp>=1.0"]
gemini = ["google-genai>=1.0"]
voyage = ["voyageai>=0.3"]
openai = ["openai>=1.0"]
```

Install: `uv add numpy` for the core dependency. MCP and provider SDKs installed as optional: `uv add "iflow-dev-hooks[mcp,gemini]"`.

**numpy availability check:** At import time, try `import numpy`. If ImportError, set a module-level flag. `RetrievalPipeline` checks this flag and skips vector retrieval entirely if numpy is unavailable. No conditional imports scattered through the code.

### TD11: Setup and Bootstrapping

**First-time setup:** The venv at `plugins/iflow-dev/.venv/` is created by `cd plugins/iflow-dev && uv sync`. This must be run once before semantic memory is functional. The release script (`scripts/release.sh`) should include this step.

**Diagnostic when venv missing:** If `memory_semantic_enabled: true` but numpy is not importable (venv missing or incomplete), the diagnostic line shows:
```
*Memory: 20 entries from 54 | semantic: degraded (numpy unavailable, run: cd plugins/iflow-dev && uv sync) | context: "..." | model: none*
```

**MCP server with missing venv:** If the venv doesn't exist, Claude Code will fail to start the memory-server MCP (command not found). This is acceptable — the MCP server is optional (mid-session capture only). Session-start injection still works via FTS5+prominence fallback with bare python3.

## Interfaces

**Note:** Code snippets below are illustrative contracts showing method signatures, types, and key logic. They define the interface boundaries and invariants but are not prescriptive implementations. The planning phase should reference signatures and contracts without treating method bodies as copy-paste targets.

### I1: MemoryDatabase

```python
class MemoryDatabase:
    def __init__(self, db_path: str):
        """Open database, run migrations, set PRAGMAs."""

    def close(self):
        """Close connection."""

    @property
    def fts5_available(self) -> bool:
        """Whether FTS5 extension is available. Set at __init__ via detection probe."""

    def upsert_entry(self, entry: dict) -> None:
        """INSERT or UPDATE entry. Handles content hash dedup.
        Entry dict keys match column names.
        Keywords and references stored as JSON strings."""

    def get_entry(self, entry_id: str) -> dict | None:
        """Get single entry by content hash ID."""

    def get_all_entries(self) -> list[dict]:
        """Get all entries (for ranking). Excludes embedding BLOB for efficiency."""

    def get_all_embeddings(self, expected_dims: int = 768) -> tuple[list[str], np.ndarray] | None:
        """Load all non-null embeddings as (ids, matrix).
        Returns None if no embeddings exist or numpy unavailable.
        Matrix shape: (N, expected_dims), dtype float32.
        Validates each BLOB length == expected_dims * 4. Skips entries
        with corrupted/wrong-size embeddings (logs to stderr)."""

    def fts5_search(self, query: str, limit: int = 100) -> list[tuple[str, float]]:
        """FTS5 MATCH search. Returns [(entry_id, bm25_score), ...].
        BM25 score negated so higher = more relevant."""

    def update_recall(self, entry_ids: list[str], timestamp: str) -> None:
        """Batch increment recall_count and set last_recalled_at."""

    def get_metadata(self, key: str) -> str | None:
        """Read from _metadata table."""

    def set_metadata(self, key: str, value: str) -> None:
        """Write to _metadata table."""

    def count_entries(self) -> int:
        """Total entry count."""

    def get_entries_without_embedding(self, limit: int = 50) -> list[dict]:
        """Get entries with NULL embedding for re-embedding migration."""

    def update_embedding(self, entry_id: str, embedding: bytes) -> None:
        """Update embedding BLOB for a single entry."""

    def clear_all_embeddings(self) -> None:
        """Set all embeddings to NULL (provider change migration)."""
```

### I2: EmbeddingProvider (Protocol)

```python
from typing import Protocol

class EmbeddingProvider(Protocol):
    def embed(self, text: str, task_type: str = "query") -> np.ndarray:
        """Generate embedding for text. Returns L2-normalized float32 array.
        task_type: "query" (RETRIEVAL_QUERY) or "document" (RETRIEVAL_DOCUMENT).
        Raises EmbeddingError on failure."""

    def embed_batch(self, texts: list[str], task_type: str = "document") -> list[np.ndarray]:
        """Batch embed. Same contract as embed(). Used for import/migration."""

    @property
    def dimensions(self) -> int:
        """Output dimensionality (768 for Gemini default config)."""

    @property
    def provider_name(self) -> str:
        """Provider identifier for _metadata tracking."""

    @property
    def model_name(self) -> str:
        """Model identifier for _metadata tracking."""
```

**GeminiProvider specifics:**
```python
from google import genai
from google.genai import types

class GeminiProvider:
    TASK_TYPE_MAP = {
        "document": "RETRIEVAL_DOCUMENT",
        "query": "RETRIEVAL_QUERY",
    }

    def __init__(self, api_key: str, model: str = "gemini-embedding-001",
                 dimensions: int = 768):
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._dimensions = dimensions
        # Verify SDK supports task_type at init time (fail fast, not per-call)
        try:
            types.EmbedContentConfig(task_type="RETRIEVAL_QUERY", output_dimensionality=dimensions)
        except TypeError as e:
            raise RuntimeError(
                f"google-genai SDK does not support task_type in EmbedContentConfig. "
                f"Upgrade: uv add 'google-genai>=1.0'. Error: {e}"
            ) from e

    def embed(self, text: str, task_type: str = "query") -> np.ndarray:
        result = self._client.models.embed_content(
            model=self._model,
            contents=text,
            config=types.EmbedContentConfig(
                task_type=self.TASK_TYPE_MAP[task_type],
                output_dimensionality=self._dimensions,
            ),
        )
        # Convert to float32 (normalization handled by NormalizingWrapper)
        return np.array(result.embeddings[0].values, dtype=np.float32)
```

**Provider factory and normalization enforcement:**
```python
def create_provider(config: dict) -> 'EmbeddingProvider | None':
    """Factory: reads API key from env, constructs provider, wraps with normalizer.
    Returns None if provider unavailable (missing API key, import error)."""
    provider_name = config.get("memory_embedding_provider", "gemini")
    key_env_map = {"gemini": "GEMINI_API_KEY", "voyage": "VOYAGE_API_KEY", "openai": "OPENAI_API_KEY"}

    api_key = None
    if provider_name in key_env_map:
        api_key = os.environ.get(key_env_map[provider_name])
        if not api_key:
            return None  # Provider unavailable — degrade to keyword+prominence

    try:
        if provider_name == "gemini":
            raw = GeminiProvider(api_key=api_key)
        elif provider_name == "ollama":
            raw = OllamaProvider()  # No API key needed
        else:
            return None  # Voyage/OpenAI deferred to v2
    except ImportError:
        return None

    return NormalizingWrapper(raw)


class NormalizingWrapper:
    """Wraps any EmbeddingProvider to enforce L2 normalization."""
    def __init__(self, inner):
        self._inner = inner

    def embed(self, text: str, task_type: str = "query") -> np.ndarray:
        vec = self._inner.embed(text, task_type)
        norm = np.linalg.norm(vec)
        if norm < 1e-9:
            raise EmbeddingError("Provider returned zero vector")
        return vec / norm

    def embed_batch(self, texts, task_type="document"):
        # Delegate to inner's true batch call, then normalize each result
        raw_vecs = self._inner.embed_batch(texts, task_type)
        normalized = []
        for vec in raw_vecs:
            norm = np.linalg.norm(vec)
            if norm < 1e-9:
                raise EmbeddingError("Provider returned zero vector in batch")
            normalized.append(vec / norm)
        return normalized

    @property
    def dimensions(self): return self._inner.dimensions
    @property
    def provider_name(self): return self._inner.provider_name
    @property
    def model_name(self): return self._inner.model_name
```

### I3: KeywordGenerator (Protocol)

```python
class KeywordGenerator(Protocol):
    def generate(self, name: str, description: str, reasoning: str,
                 category: str) -> list[str]:
        """Generate 3-10 keyword labels. Returns list of lowercase strings.
        Returns empty list on failure (non-blocking)."""

class TieredKeywordGenerator:
    """Tries providers in tier order with 5s timeout each."""

    def __init__(self, config: dict):
        # Build tier list based on config['memory_keyword_provider']
        # 'auto' -> [InSessionClaude, HaikuAPI, Ollama, Skip]
        # 'claude' -> [InSessionClaude, Skip]
        # 'haiku' -> [HaikuAPI, Skip]
        # 'ollama' -> [Ollama, Skip]
        # 'off' -> [Skip]

    def generate(self, name: str, description: str, reasoning: str,
                 category: str) -> list[str]:
        # Try each tier with 5s timeout, return first success
        # Post-LLM validation: 3-10 keywords, not in stopword list, all lowercase
        # Reject keywords containing double quotes, square brackets, or JSON-special chars
        # (defensive: prevents FTS5 trigger REPLACE chain edge cases)
```

### I4: RetrievalPipeline

```python
class RetrievalPipeline:
    def __init__(self, db: MemoryDatabase, provider: EmbeddingProvider | None,
                 config: dict):
        """provider is None when embedding provider is unavailable."""

    def collect_context(self, project_root: str) -> str | None:
        """Gather context signals and compose query string.
        Returns None if no signals available."""

    def retrieve(self, context_query: str | None) -> RetrievalResult:
        """Run retrieval strategies and merge results.
        Returns RetrievalResult with candidates and diagnostic metadata.
        When context_query is None: returns empty candidates (all entries get zero scores)."""

@dataclass
class CandidateScores:
    vector_score: float = 0.0  # Raw cosine similarity [-1, 1]
    bm25_score: float = 0.0    # Raw BM25 score (negated, higher = better)

@dataclass
class RetrievalResult:
    candidates: dict[str, CandidateScores]  # {entry_id: scores}
    vector_candidate_count: int = 0         # Entries with non-zero vector_score
    fts5_candidate_count: int = 0           # Entries returned by FTS5 MATCH
    context_query: str | None = None        # The composed query (for diagnostic truncation)
```

### I5: RankingEngine

```python
class RankingEngine:
    def __init__(self, config: dict):
        """config provides vector_weight, keyword_weight, prominence_weight."""

    def rank(self, result: RetrievalResult,
             entries: dict[str, dict], limit: int) -> list[dict]:
        """Score, normalize, and select entries.
        result: RetrievalResult from pipeline (includes candidates and signal availability)
        entries: {id: entry_dict} all entries from DB
        limit: max entries to return

        Weight redistribution: If result.vector_candidate_count == 0, vector signal
        is unavailable — redistribute vector_weight proportionally to keyword and
        prominence. Same for fts5_candidate_count == 0. This distinguishes 'no
        relevant matches' (score 0, weight active) from 'signal unavailable'
        (weight redistributed).

        Returns ordered list of entry dicts with added 'final_score' key.
        Applies category-balanced selection per spec D3."""
```

### I6: MemoryInjector (CLI Entry Point)

```python
def main():
    """CLI entry point called from session-start.sh.
    Args: --project-root, --limit, --global-store
    Output: formatted markdown to stdout (same format as memory.py)
    Exit: 0 on success, 1 on error (stderr only, never corrupt stdout)"""

    # 1. Read config
    # 2. Open database (create if needed)
    # 3. If DB empty: run importer (returns 0 if no markdown files exist)
    # 4. Check provider migration (deferred embedding processing)
    # 5. Collect context -> retrieve -> rank -> select
    #    result = pipeline.retrieve(context_query)  # Returns RetrievalResult
    #    selected = engine.rank(result.candidates, entries, limit)
    # 6. Update recall tracking
    # 7. Format output with diagnostics
    #    - Zero entries: produce no output (matches current memory.py behavior)
    #    - Diagnostic line composed by injector from RetrievalResult metadata:
    #      total_count = db.count_entries()
    #      pending = int(db.get_metadata("pending_embeddings") or "0")
    #      model = config.get("memory_embedding_model", "none")
    #      query_display = (result.context_query[:30] + "...") if result.context_query else "none"
    #      If pending > 0:
    #        f"*Memory: {len(selected)} entries from {total_count} | semantic: active (vector={result.vector_candidate_count}, fts5={result.fts5_candidate_count}, pending_embedding={pending}) | context: \"{query_display}\" | model: {model}*"
    #      Else:
    #        f"*Memory: {len(selected)} entries from {total_count} | semantic: active (vector={result.vector_candidate_count}, fts5={result.fts5_candidate_count}) | context: \"{query_display}\" | model: {model}*"
    # 8. Print to stdout
```

### I7: MemoryServer (MCP)

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("memory-server")

@mcp.tool()
async def store_memory(
    name: str,
    description: str,
    reasoning: str,
    category: str,
    references: list[str] = []
) -> str:
    """Save a learning to long-term memory.
    Returns confirmation message or error."""
    # 1. Validate inputs (non-empty name/description/reasoning, valid category)
    # 2. Compute content hash
    # 3. Generate embedding (sync, provider.embed with task_type="document")
    # 4. Generate keywords (tiered, 5s timeout per tier)
    # 5. Upsert into database
    # 6. Return "Stored: {name} (id: {hash})"
```

### I8: MarkdownImporter

```python
class MarkdownImporter:
    def __init__(self, db: MemoryDatabase, provider: EmbeddingProvider | None,
                 keyword_gen: KeywordGenerator):
        pass

    def import_all(self, project_root: str, global_store: str) -> int:
        """Import all markdown knowledge bank entries into DB.
        Returns count of entries imported.
        Deduplicates by content hash (same formula as memory.py).
        Skips entries already in DB."""

    def _parse_markdown_entries(self, filepath: str, category: str) -> list[dict]:
        """Parse markdown file using same logic as memory.py:parse_entries().
        Maps parsed fields to DB schema.

        Markdown format (knowledge bank files):
        - Files: anti-patterns.md, patterns.md, heuristics.md (category from filename)
        - Entry heading: ### Anti-Pattern: {name} (or ### Pattern: / ### Heuristic:)
        - Body: description text (everything until next heading)
        - Metadata lines: '- Observation count: N', '- Confidence: high|medium|low'
        - Category derived from filename, not heading prefix
        Exact parsing logic matches memory.py:parse_entries() for import compatibility."""
```

### I9: MemoryWriter (CLI Entry Point for Retro Writes)

```python
def main():
    """CLI entry point called from SKILL.md Step 4 via Bash tool.
    Args: --action upsert, --global-store PATH, --entry-json JSON | --entry-file PATH
    Output: confirmation to stdout ("Stored: {name} (id: {hash})")
    Exit: 0 = success, 1 = validation error (stderr), 2 = DB error (stderr)"""

    # 1. Parse args (--entry-json or --entry-file)
    # 2. Validate entry: non-empty name/description, valid category
    # 3. Open database at global-store/memory.db
    # 4. Read config for embedding provider
    # 5. Compute content hash as entry ID
    # 6. Upsert entry (if exists: increment observation_count, merge keywords)
    # 7. Generate embedding if provider available (no timeout constraint)
    # 8. Process pending embeddings batch (up to 50, Phase 2 deferred processing)
    # 9. Check provider migration (TD9)
    # 10. Print confirmation to stdout
```

**File location:** `plugins/iflow-dev/hooks/lib/semantic_memory/writer.py`

### I10: Output Format

The injector produces markdown text identical in structure to current memory.py output, with an added diagnostic line. **New fields (reasoning, keywords, references, recall_count) are stored in DB for search/ranking but NOT rendered in session output.** The output format matches what the model currently sees — changing it would alter model behavior.

```markdown
## Engineering Memory (from knowledge bank)

*Memory: 20 entries from 154 | semantic: active (vector=142, fts5=38) | context: "memory-semantic-search: Build a pers..." | model: gemini-embedding-001*

### Anti-Patterns to Avoid
### Anti-Pattern: Stale Review Iteration Counts
{description}
- Observation count: 3
- Confidence: high
...

### Heuristics
...

### Patterns to Follow
...

---
```

When entries await embedding generation (first run or provider migration):
```markdown
*Memory: 20 entries from 54 | semantic: active (vector=12, fts5=38, pending_embedding=42) | context: "..." | model: gemini-embedding-001*
```

When semantic retrieval is disabled:
```markdown
*Memory: 20 entries (15 local, 5 global) | semantic: disabled*
```

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Gemini API latency exceeds 2s budget at query time | Medium | Timeout, empty memory | Pre-computed embeddings mean only ONE API call (query embedding). 200-700ms typical. If slow, vector retrieval skipped, FTS5+prominence fallback |
| numpy not available in user's Python environment | Low | No vector search | Module-level import check. Skip vector retrieval entirely. FTS5+prominence still works. `uv add numpy` in setup instructions |
| MCP server and retro write concurrently | Medium | SQLite lock contention | WAL mode + busy_timeout=5000. Write transactions are single-row INSERTs (<1ms). WAL allows concurrent readers |
| First-run import of 50+ entries hits Gemini rate limit | Medium | Import partially completes | Batch in groups of 50 with 1s delay between batches. HTTP 429 then pause, resume next session. Entries without embeddings use keyword-only retrieval |
| FTS5 BM25 ranking noisy at current corpus size (<100 entries) | Low-Medium | Suboptimal keyword scores | BM25 is one of three signals (weight 0.2). Vector similarity (0.5) and prominence (0.3) compensate. Binary match signal still useful |
| Embedding provider SDK import adds startup latency | Low | Slower session start | Lazy import: only import provider SDK when `memory_semantic_enabled: true`. SDK import is one-time cost (~50ms for google-genai) |
| Database corruption from unclean shutdown | Low | Lost memory data | Markdown files serve as append-only audit trail. D7 import rebuilds DB from markdown. WAL mode provides crash recovery |
| Content hash collision (16 hex chars = 64 bits) | Very Low | Two different entries share an ID | Birthday problem: collision probability <0.1% at 10K entries. Acceptable for this use case. Matches existing memory.py behavior |
