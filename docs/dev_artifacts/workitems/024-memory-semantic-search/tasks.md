# Tasks: Semantic Memory System

**Convention:** Phase test tasks (T1.5, T2.5, T3.3, T4.4) are hard gates. All tasks starting the next phase depend on the previous phase's test task. Dependencies track execution ordering; code-level imports are specified in each task's Do section.

## Dependency Graph

```
Phase 0:
  T0.1

Phase 1:
  T1.1 ◄── T0.1
  T1.2 ◄── T0.1          (T1.1, T1.2 parallel)
  T1.3 ◄── T1.1
  T1.4 ◄── T1.3
  T1.5 ◄── T1.1, T1.2, T1.3, T1.4   [PHASE GATE]

Phase 2:
  T2.1 ◄── T1.5          (T2.1, T2.3, T2.4 parallel)
  T2.3 ◄── T1.5
  T2.4 ◄── T1.5
  T2.2 ◄── T2.1          (sequential after T2.1)
  T2.5 ◄── T2.1, T2.2, T2.3, T2.4   [PHASE GATE]

Phase 3:
  T3.1 ◄── T2.5          (T3.1, T3.2 parallel)
  T3.2 ◄── T2.5
  T3.3 ◄── T3.1, T3.2              [PHASE GATE]

Phase 4:
  T4.1 ◄── T3.3          (T4.1, T4.2, T4.3 parallel)
  T4.2 ◄── T3.3
  T4.3 ◄── T3.3
  T4.4 ◄── T4.1, T4.2, T4.3       [PHASE GATE]

Phase 5:
  T5.1 ◄── T4.4          (T5.1, T5.2, T5.3 parallel)
  T5.2 ◄── T4.4
  T5.3 ◄── T4.4

Phase 6:
  T6.1 ◄── T5.1, T5.2, T5.3
  T6.2 ◄── T6.1
```

## Execution Strategy

### Parallel Group 1 (No dependencies)
- T0.1: Create pyproject.toml and initialize venv

### Parallel Group 2 (after T0.1)
- T1.1: Create package structure with __init__.py and types.py
- T1.2: Implement configuration reader

### Sequential Group 3 (after T1.1)
- T1.3: Implement database schema and basic CRUD
- T1.4: Add FTS5 detection and embedding methods

### Phase 1 Gate (after T1.1-T1.4)
- T1.5: Write and run Phase 1 unit tests

### Parallel Group 4 (after T1.5)
- T2.1: Implement EmbeddingProvider protocol and GeminiProvider
- T2.3: Implement keyword generator with tiered providers
- T2.4: Implement ranking engine

### Sequential within Phase 2 (after T2.1)
- T2.2: Implement NormalizingWrapper and create_provider factory

### Phase 2 Gate (after T2.1-T2.4)
- T2.5: Write and run Phase 2 unit tests

### Parallel Group 5 (after T2.5)
- T3.1: Implement retrieval pipeline
- T3.2: Implement markdown importer

### Phase 3 Gate (after T3.1-T3.2)
- T3.3: Write and run Phase 3 unit tests

### Parallel Group 6 (after T3.3)
- T4.1: Implement injector CLI
- T4.2: Implement writer CLI
- T4.3: Implement MCP memory server

### Phase 4 Gate (after T4.1-T4.3)
- T4.4: Write and run Phase 4 unit tests

### Parallel Group 7 (after T4.4)
- T5.1: Modify session-start.sh for semantic branch
- T5.2: Update retrospective skill and retro-facilitator agent
- T5.3: Register MCP server in .mcp.json

### After Phase 5
- T6.1: Write end-to-end integration tests
- T6.2: Run validate.sh and verify all tests pass

## Plan-to-Task Mapping

| Plan Item | Task(s) | Notes |
|-----------|---------|-------|
| 0.1 | T0.1 | |
| 1.1 | T1.1 | |
| 1.2 | T1.2 | |
| 1.3a | T1.3 | Schema + CRUD |
| 1.3b | T1.4 | FTS5 + embeddings |
| 1.4 | T1.5 | |
| 2.1 | T2.1, T2.2 | Split: protocol+providers / wrapper+factory |
| 2.2 | T2.3 | |
| 2.3 | T2.4 | |
| 2.4 | T2.5 | |
| 3.1 | T3.1 | |
| 3.2 | T3.2 | |
| 3.3 | T3.3 | |
| 4.1 | T4.1 | |
| 4.2 | T4.2 | |
| 4.3 | T4.3 | |
| 4.4 | T4.4 | |
| 5.1 | T5.1 | |
| 5.2 | T5.2 | |
| 5.3 | T5.3 | |
| 6.1 | T6.1 | |
| 6.2 | T6.2 | |

## Task Details

### Phase 0: Environment Setup

#### Task 0.1: Create pyproject.toml and initialize venv
- **Why:** Plan 0.1 / TD10, TD11 — numpy and provider SDKs must be importable before any Python module
- **Depends on:** None
- **Blocks:** T1.1, T1.2
- **Files:** `plugins/iflow-dev/pyproject.toml`
- **Do:**
  1. Create `plugins/iflow-dev/pyproject.toml` with:
     - `[project]` name=`iflow-dev-hooks`, version=`0.1.0`, requires-python=`>=3.9`
     - `dependencies = ["numpy>=1.24"]`
     - `[project.optional-dependencies]` mcp=`["mcp>=1.0"]`, gemini=`["google-genai>=1.0"]`, voyage=`["voyageai>=0.3"]`, openai=`["openai>=1.0"]`
  2. Run `cd plugins/iflow-dev && uv sync`
  3. Run `uv sync --extra mcp --extra gemini` to install MCP + Gemini SDKs
  4. Verify numpy: `.venv/bin/python -c "import numpy; print(numpy.__version__)"`
  5. Verify Gemini SDK API surface: `.venv/bin/python -c "from google.genai import types; types.EmbedContentConfig(task_type='RETRIEVAL_QUERY', output_dimensionality=768)"`
  6. Verify MCP import: `.venv/bin/python -c "from mcp.server.fastmcp import FastMCP"`
- **Test:** All three verification commands exit 0
- **Done when:** `.venv/bin/python -c "import numpy"` succeeds and SDK verification passes

---

### Phase 1: Foundation

#### Task 1.1: Create package structure with __init__.py and types.py
- **Why:** Plan 1.1 / TD1 — package layout, content_hash shared utility, shared dataclasses to break circular deps
- **Depends on:** T0.1
- **Blocks:** T1.3, T1.5
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/__init__.py`, `plugins/iflow-dev/hooks/lib/semantic_memory/types.py`
- **Do:**
  1. Create directory `plugins/iflow-dev/hooks/lib/semantic_memory/`
  2. Create `__init__.py` with:
     - `__version__ = "0.1.0"`
     - `content_hash(description: str) -> str` using `SHA-256(" ".join(description.lower().strip().split()))[:16]`
     - `class EmbeddingError(Exception): pass`
  3. Create `types.py` with:
     - `@dataclass CandidateScores`: `vector_score: float = 0.0`, `bm25_score: float = 0.0`
     - `@dataclass RetrievalResult`: `candidates: dict[str, CandidateScores]`, `vector_candidate_count: int = 0`, `fts5_candidate_count: int = 0`, `context_query: str | None = None`
- **Test:** `cd plugins/iflow-dev/hooks/lib && ../.venv/bin/python -c "from semantic_memory import content_hash; print(content_hash('test description'))"` prints 16-char hex. `from semantic_memory.types import RetrievalResult, CandidateScores` succeeds.
- **Done when:** Both import commands succeed and content_hash returns correct hex string

#### Task 1.2: Implement configuration reader
- **Why:** Plan 1.2 / TD5 — every component reads config; must match bash read_local_md_field exactly
- **Depends on:** T0.1
- **Blocks:** T1.5
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/config.py`
- **Do:**
  1. Create `config.py` with `read_config(project_root: str) -> dict`
  2. Define defaults dict matching spec Configuration section: `memory_semantic_enabled: True`, `memory_vector_weight: 0.5`, `memory_keyword_weight: 0.2`, `memory_prominence_weight: 0.3`, `memory_embedding_provider: "gemini"`, `memory_embedding_model: "gemini-embedding-001"`, `memory_keyword_provider: "auto"`, `memory_injection_limit: 20`
  3. Scan ALL lines of `.claude/iflow-dev.local.md` for `^field:` patterns (no --- delimiter awareness)
  4. Type coercion: strip ALL spaces via `tr -d ' '` equivalent, `"true"/"false"` → bool, numeric strings → int/float, else str
  5. Return merged defaults + parsed values
- **Test:** Write inline test: mock file with `memory_semantic_enabled: true\nmemory_vector_weight: 0.5` → returns correct types. Missing file → returns all defaults.
- **Done when:** `read_config()` correctly parses real `iflow-dev.local.md` or returns defaults when missing

#### Task 1.3: Implement database schema and basic CRUD
- **Why:** Plan 1.3a / C1 — central persistence layer with schema, PRAGMAs, migrations, basic CRUD
- **Depends on:** T1.1
- **Blocks:** T1.4, T1.5
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/database.py`
- **Do:**
  1. Create `database.py` with `class MemoryDatabase`
  2. `__init__(self, db_path: str)`: open connection, set PRAGMAs (WAL, synchronous=NORMAL, busy_timeout=5000, cache_size=-8000), run migrations
  3. `MIGRATIONS = {1: create_initial_schema}` — creates `entries` table with 16 columns:
     - `id TEXT PRIMARY KEY` — content_hash
     - `name TEXT NOT NULL`
     - `description TEXT NOT NULL`
     - `reasoning TEXT` — why this matters
     - `category TEXT NOT NULL` — anti-patterns|patterns|heuristics
     - `keywords TEXT` — JSON array of strings
     - `source TEXT NOT NULL CHECK(source IN ('retro', 'session-capture', 'manual', 'import'))`
     - `source_project TEXT` — project root path
     - `references TEXT` — JSON array of file/feature references
     - `observation_count INTEGER DEFAULT 1`
     - `confidence TEXT DEFAULT 'medium'` — high|medium|low
     - `recall_count INTEGER DEFAULT 0`
     - `last_recalled_at TEXT` — ISO timestamp
     - `embedding BLOB` — float32 bytes (768 dims x 4 bytes = 3072 bytes)
     - `created_at TEXT NOT NULL` — ISO timestamp
     - `updated_at TEXT NOT NULL` — ISO timestamp
     Also creates `_metadata` table (`key TEXT PRIMARY KEY`, `value TEXT`)
  4. `migrate(conn)` — read schema_version from _metadata (0 if missing), apply pending migrations
  5. Implement 8 methods: `close()`, `upsert_entry(entry: dict)`, `get_entry(entry_id: str) -> dict | None`, `get_all_entries() -> list[dict]`, `count_entries() -> int`, `get_metadata(key: str) -> str | None`, `set_metadata(key: str, value: str)`, migration helper `get_schema_version()`
  6. `upsert_entry` uses INSERT ... ON CONFLICT(id) DO UPDATE SET observation_count = observation_count + 1, updated_at = ? (NOT INSERT OR REPLACE which deletes the old row). On new entry: insert all provided values. On existing entry: increment `observation_count`, update `updated_at`. Keywords merge: replace (not union) — if incoming keywords is non-null, overwrite; if null, keep existing. Same for description, reasoning, references: overwrite if non-null, keep existing if null.
- **Test:** In-memory DB: upsert entry, get_entry by ID verifies all 16 fields. Migration from 0→1 creates tables. get_metadata/set_metadata round-trips.
- **Done when:** In-memory DB passes CRUD round-trip test

#### Task 1.4: Add FTS5 detection and embedding methods to database
- **Why:** Plan 1.3b / C1 — FTS5 keyword search and embedding BLOB operations for retrieval
- **Depends on:** T1.3
- **Blocks:** T1.5
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/database.py` (extends T1.3)
- **Do:**
  1. Add FTS5 detection at `__init__()`: attempt `CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_test USING fts5(x); DROP TABLE _fts5_test;` in try/except. Set `self._fts5_available` flag. Log to stderr if unavailable.
  2. Add `@property fts5_available -> bool`
  3. Conditionally create FTS5 virtual table `entries_fts` and 3 triggers (INSERT/DELETE/UPDATE) with JSON-stripping REPLACE chain for keywords column
  4. Implement 6 methods: `fts5_search(query: str, limit: int = 100) -> list[tuple[str, float]]`, `get_all_embeddings(expected_dims: int = 768) -> tuple[list[str], np.ndarray] | None`, `update_embedding(entry_id: str, embedding: bytes)`, `clear_all_embeddings()`, `get_entries_without_embedding(limit: int = 50) -> list[dict]`, `update_recall(entry_ids: list[str], timestamp: str)`
  5. `get_all_embeddings` validates BLOB length == expected_dims * 4, skips corrupted entries with stderr warning
  6. `fts5_search` negates BM25 score so higher = more relevant
- **Test:** FTS5 search returns results. get_all_embeddings returns None when empty. update_recall increments. BLOB round-trip: store float32.tobytes(), read back with np.frombuffer, verify equality.
- **Done when:** All 6 new methods work with in-memory DB, FTS5 detection runs without error

#### Task 1.5: Write and run Phase 1 unit tests
- **Why:** Plan 1.4 — validate foundation before building on it; phase gate for Phase 2
- **Depends on:** T1.1, T1.2, T1.3, T1.4
- **Blocks:** T2.1, T2.3, T2.4 (phase gate)
- **Files:** `plugins/iflow-dev/hooks/tests/test_foundation.py`
- **Do:**
  1. Create test file with `sys.path.insert` for semantic_memory imports
  2. Test content_hash: known input → known 16-char hex output, normalization (whitespace, case)
  3. Test config reader: mock file with various types, missing file → defaults, space stripping
  4. Test database CRUD: in-memory DB, upsert/get/count/metadata round-trips
  5. Test FTS5: insert entries with keywords, fts5_search finds by keyword
  6. Test embedding BLOB: store float32 tobytes, read back, verify array equality
  7. Test migration: version 0→1 creates all tables
- **Test:** `cd plugins/iflow-dev && .venv/bin/python -m pytest hooks/tests/test_foundation.py -v`
- **Done when:** All tests pass with `pytest -v` showing green

---

### Phase 2: Core Modules

#### Task 2.1: Implement EmbeddingProvider protocol and GeminiProvider
- **Why:** Plan 2.1 / C2 — embedding generation for write and query paths
- **Depends on:** T1.5 (phase gate; uses config.py from Phase 1)
- **Blocks:** T2.2, T2.5
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/embedding.py`
- **Do:**
  1. Create `embedding.py`
  2. Define `EmbeddingProvider` Protocol with: `embed(text, task_type="query") -> np.ndarray`, `embed_batch(texts, task_type="document") -> list[np.ndarray]`, `dimensions -> int`, `provider_name -> str`, `model_name -> str`
  3. Implement `GeminiProvider`:
     - `__init__(api_key, model="gemini-embedding-001", dimensions=768)` — validates SDK supports task_type at init (fail-fast RuntimeError)
     - `TASK_TYPE_MAP = {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY"}`
     - `embed()` using `self._client.models.embed_content()` with `types.EmbedContentConfig`
     - `embed_batch()` using Gemini SDK batch capability
  4. Implement `OllamaProvider`: raises `NotImplementedError("Ollama provider not yet implemented...")`
  5. Re-export `EmbeddingError` from `__init__.py`
- **Test:** Mock provider test: embed returns float32 array of correct dims. OllamaProvider raises NotImplementedError.
- **Done when:** GeminiProvider __init__ validates SDK, embed/embed_batch have correct signatures, OllamaProvider raises

#### Task 2.2: Implement NormalizingWrapper and create_provider factory
- **Why:** Plan 2.1 / C2 — centralized L2 normalization enforcement and provider construction
- **Depends on:** T2.1
- **Blocks:** T2.5
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/embedding.py` (extends T2.1)
- **Do:**
  1. Add `NormalizingWrapper` class wrapping any EmbeddingProvider:
     - `embed()`: call inner.embed(), compute norm, raise EmbeddingError if norm < 1e-9, return vec / norm
     - `embed_batch()`: delegate to inner.embed_batch(), normalize each, raise if any zero vector
     - Forward properties: dimensions, provider_name, model_name
  2. Add `create_provider(config: dict) -> EmbeddingProvider | None`:
     - Read provider_name from config
     - Map to env var: gemini→GEMINI_API_KEY, voyage→VOYAGE_API_KEY, openai→OPENAI_API_KEY
     - Return None if API key missing
     - Construct provider: gemini→GeminiProvider, ollama→OllamaProvider, else None
     - Wrap in NormalizingWrapper
     - Catch ImportError → return None
- **Test:** NormalizingWrapper normalizes [3, 4, 0...0] to unit length. Zero vector raises EmbeddingError. create_provider returns None when env var missing.
- **Done when:** NormalizingWrapper enforces normalization, factory correctly constructs or returns None

#### Task 2.3: Implement keyword generator with tiered providers
- **Why:** Plan 2.2 / C3 — LLM-generated keyword labels for FTS5 indexing
- **Depends on:** T1.5 (phase gate; uses config.py from Phase 1)
- **Blocks:** T2.5
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/keywords.py`
- **Do:**
  1. Create `keywords.py`
  2. Define `KeywordGenerator` Protocol with `generate(name, description, reasoning, category) -> list[str]`
  3. Define STOPWORD_LIST matching AC5: `["code", "development", "software", "system", "application", "implementation", "feature", "project", "function", "method", "file", "data", "error", "bug", "fix", "update", "change"]`
  4. Define KEYWORD_PROMPT template matching C3 design
  5. Implement `TieredKeywordGenerator`:
     - `__init__(config)` — build tier list based on `memory_keyword_provider` config value
     - `generate()` — try each tier with 5s timeout, post-LLM validation: per-keyword filter against `^[a-z0-9][a-z0-9-]*$`, reject stopwords, return 3-10 valid keywords
     - `_validate_keyword(kw: str) -> bool` — regex match + stopword check
  6. Implement `SkipKeywordGenerator` returning empty list (tier 4 / "off" mode)
- **Test:** Mock tier returns `["fts5", "sqlite", "INVALID!", "parser-error", "code"]` → keeps fts5, sqlite, parser-error (3), filters INVALID! (bad chars) and code (stopword).
- **Done when:** Keyword validation filters correctly, tier fallback works, stopwords rejected

#### Task 2.4: Implement ranking engine
- **Why:** Plan 2.3 / C5 — scoring and selection independent of retrieval strategy
- **Depends on:** T1.5 (phase gate; uses types.py and config.py from Phase 1)
- **Blocks:** T2.5
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/ranking.py`
- **Do:**
  1. Create `ranking.py` with `class RankingEngine`
  2. `__init__(config)` — read vector_weight, keyword_weight, prominence_weight from config
  3. `rank(result: RetrievalResult, entries: dict[str, dict], limit: int) -> list[dict]`:
     - Min-max normalize vector_score and bm25_score across candidates (max=0 → weight redistributed)
     - Compute prominence per entry: `0.3*norm_obs + 0.2*confidence + 0.3*recency + 0.2*recall` where norm_obs = entry.observation_count / max(e.observation_count for e in entries.values()) across ALL entries passed to rank() (not just candidates; max=0 → norm_obs=0)
     - Confidence mapping (fixed, not data-dependent, per design C5): high=1.0, medium=2/3≈0.667, low=1/3≈0.333. Use exact fractions in code. Add code comment referencing design C5 and spec D3 for provenance.
     - Recency decay: `1.0 / (1.0 + days_since_updated / 30.0)`
     - Recall frequency: `min(recall_count / 10.0, 1.0)`
     - Weight redistribution: if vector_candidate_count=0, redistribute vector_weight to keyword+prominence proportionally. Same for fts5_candidate_count=0.
     - Score: `final_score = vw * norm_vector + kw * norm_bm25 + pw * prominence`
     - Category-balanced selection: min-3 per non-empty category when limit >= 9
     - Fill remaining by final_score descending
  4. Return ordered list with `final_score` key added to each entry dict
- **Test:** Known inputs: 3 entries with specific scores → verify ordering. Weight redistribution when vector_candidate_count=0. Category balance with 3 categories and limit=20.
- **Done when:** Ranking produces correct ordering for known inputs, weight redistribution works, category balance enforced

#### Task 2.5: Write and run Phase 2 unit tests
- **Why:** Plan 2.4 — validate core modules before building pipelines; phase gate for Phase 3
- **Depends on:** T2.1, T2.2, T2.3, T2.4
- **Blocks:** T3.1, T3.2 (phase gate)
- **Files:** `plugins/iflow-dev/hooks/tests/test_core_modules.py`
- **Do:**
  1. Create test file with sys.path.insert
  2. Test NormalizingWrapper: normalizes to unit length, zero vector raises EmbeddingError
  3. Test create_provider: returns None with missing env var, returns wrapped provider with valid env
  4. Test keyword validation: per-keyword filtering, stopword rejection, regex validation
  5. Test ranking formula: known score inputs → expected ordering
  6. Test weight redistribution: vector_candidate_count=0 → vector_weight redistributed
  7. Test category balance: 3 categories with limit=20 → min-3 per category
  8. Test prominence sub-components: known obs/confidence/recency/recall → expected prominence
- **Test:** `cd plugins/iflow-dev && .venv/bin/python -m pytest hooks/tests/test_core_modules.py -v`
- **Done when:** All tests pass green

---

### Phase 3: Pipelines

#### Task 3.1: Implement retrieval pipeline
- **Why:** Plan 3.1 / C4 — orchestrates context collection, vector + FTS5 retrieval, merging
- **Depends on:** T2.5 (phase gate; uses database.py FTS5 methods, embedding.py provider)
- **Blocks:** T3.3
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/retrieval.py`
- **Do:**
  1. Create `retrieval.py` with `class RetrievalPipeline`
  2. `__init__(db, provider, config)` — provider can be None (degradation)
  3. `collect_context(project_root) -> str | None`:
     - Scan `docs/dev_artifacts/workitems/*/.meta.json` for active feature (highest numeric ID if multiple)
     - Extract slug, spec.md first paragraph (max 100 words), lastCompletedPhase
     - Git diff: `git diff --name-only HEAD~3..HEAD`, fallback HEAD~1, skip on error
     - Compose: `"{slug}: {description}. Phase: {phase}. Files: {files}"`
     - Return None if no signals
     - Log .meta.json parse errors to stderr
  4. `retrieve(context_query) -> RetrievalResult`:
     - If context_query is None: return empty RetrievalResult (zero candidates)
     - Vector retrieval: if provider and numpy available, load all embeddings via db.get_all_embeddings(), compute `matrix @ query_embedding`, populate vector_score for each entry
     - Keyword retrieval: if db.fts5_available, run db.fts5_search(context_query), populate bm25_score
     - Merge: union candidates, entries found by both carry both scores
     - Populate RetrievalResult metadata (counts)
  5. Handle all degradation: no provider, no FTS5, no numpy, no context
- **Test:** Mock DB with 5 entries and pre-computed embeddings. collect_context with mock .meta.json. retrieve with both signals, vector-only, FTS5-only, neither.
- **Done when:** All 4 degradation paths return valid RetrievalResult without error

#### Task 3.2: Implement markdown importer
- **Why:** Plan 3.2 / C7 — first-run import of existing knowledge bank entries
- **Depends on:** T2.5 (phase gate; type-level imports from embedding.py and keywords.py exist in the file for constructor signature, but at runtime both provider and keyword_gen are passed as None for first-run import)
- **Blocks:** T3.3
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/importer.py`
- **Do:**
  1. Create `importer.py` with `class MarkdownImporter`
  2. `__init__(db, provider, keyword_gen)` — keyword_gen typed as `KeywordGenerator | None`
  3. `import_all(project_root, global_store) -> int`:
     - Scan local `docs/dev_artifacts/knowledge-bank/*.md` and global `{global_store}/*.md`
     - For each file: derive category from filename (anti-patterns.md → anti-patterns, etc.)
     - Call `_parse_markdown_entries(filepath, category)`
     - Upsert each entry with `source="import"`, `source_project` from project_root
     - Skip embeddings and keywords (both NULL) — deferred processing on next write-path
     - Dedup by content hash (db.upsert_entry handles this)
     - Return count imported
  4. `_parse_markdown_entries(filepath, category) -> list[dict]`:
     - Read memory.py parse_entries() source (lines 68-72) first to match exactly
     - Heading format: `### {OptionalPrefix}{Name}` — strip only "Anti-Pattern: " and "Pattern: " prefixes (NO "Heuristic: " prefix; heuristics.md entries use plain names). Iterate prefixes, break on first match, else use full header text as name.
     - Body: everything until next `###` heading
     - Metadata: `- Observation count: N`, `- Confidence: high|medium|low`
     - Category derived from filename, not heading prefix
- **Test:** Mock anti-patterns.md with 3 entries → 3 DB rows. Re-import idempotent (same count). Embeddings/keywords NULL.
- **Done when:** Import correctly parses markdown matching memory.py format, dedup works

#### Task 3.3: Write and run Phase 3 unit tests
- **Why:** Plan 3.3 — validate pipeline modules before entry points; phase gate for Phase 4
- **Depends on:** T3.1, T3.2
- **Blocks:** T4.1, T4.2, T4.3 (phase gate)
- **Files:** `plugins/iflow-dev/hooks/tests/test_pipelines.py`
- **Do:**
  1. Create test file with sys.path.insert
  2. Test retrieval: all 4 degradation paths (both signals, vector-only, FTS5-only, neither)
  3. Test collect_context: mock .meta.json + git output → correct query string
  4. Test collect_context: no active feature → git diff filenames only
  5. Test collect_context: no signals → returns None
  6. Test importer: parse real-format markdown file → correct entries
  7. Test importer: re-import is idempotent (same entry count)
  8. Test importer: keyword_gen=None → keywords NULL in DB
- **Test:** `cd plugins/iflow-dev && .venv/bin/python -m pytest hooks/tests/test_pipelines.py -v`
- **Done when:** All tests pass green

---

### Phase 4: Entry Points

#### Task 4.1: Implement injector CLI
- **Why:** Plan 4.1 / I6 — main entry point from session-start.sh, orchestrates full query pipeline
- **Depends on:** T3.3 (phase gate; uses config.py, database.py, embedding.py, ranking.py, retrieval.py, importer.py)
- **Blocks:** T4.4
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/injector.py`
- **Do:**
  1. Create `injector.py` with `sys.path.insert` at top of `if __name__ == "__main__"` (absolute imports, NOT relative — see plan import path strategy)
  2. `main()` CLI: parse `--project-root`, `--limit`, `--global-store` args
  3. Read config via `read_config(project_root)`
  4. Open MemoryDatabase at `{global_store}/memory.db` (create dirs if needed)
  5. If DB empty (count_entries() == 0): run `MarkdownImporter(db, provider=None, keyword_gen=None).import_all(project_root=args.project_root, global_store=args.global_store)` (no API calls within 3s timeout)
  6. Create embedding provider via `create_provider(config)` — may return None if no API key
  7. Collect context → retrieve → rank → select top entries by limit
  8. RecallTracker: batch `db.update_recall(selected_ids, now_iso)` for all injected entries
  9. Format output matching I10:
     - Category sections: `### Anti-Patterns to Avoid`, `### Heuristics`, `### Patterns to Follow`
     - Each entry: `### Category: Name\n{description}\n- Observation count: N\n- Confidence: level`
     - Diagnostic line with vector/fts5 counts, context query (truncated to 30 chars), model name
     - Zero entries: produce no output
  10. Never corrupt stdout on error — all errors to stderr, exit with empty output
- **Test:** Mock DB with entries → stdout matches expected format. Diagnostic line has correct counts. Empty DB triggers import with provider=None. Errors produce empty output.
- **Done when:** Injector produces I10-format output, diagnostic line correct, errors silent

#### Task 4.2: Implement writer CLI
- **Why:** Plan 4.2 / I9 — CLI entry point for retro dual-writes via Bash tool
- **Depends on:** T3.3 (phase gate; uses config.py, database.py, embedding.py)
- **Blocks:** T4.4
- **Files:** `plugins/iflow-dev/hooks/lib/semantic_memory/writer.py`
- **Do:**
  1. Create `writer.py` with `sys.path.insert` at top of `if __name__ == "__main__"`
  2. `main()` CLI: parse `--action upsert`, `--global-store PATH`, `--entry-json JSON | --entry-file PATH`
  3. Validate entry: non-empty name/description, valid category (anti-patterns|patterns|heuristics)
  4. Open MemoryDatabase at `{global_store}/memory.db`
  5. Read config for embedding provider
  6. Compute content hash as entry ID
  7. Upsert entry (if exists: increment observation_count, merge keywords)
  8. Generate embedding if provider available (no timeout constraint for write path)
  9. Process pending embeddings batch: `db.get_entries_without_embedding(limit=50)`, embed each, update
  10. Check provider migration (TD9): compare config provider vs _metadata, clear all embeddings if changed
  11. Exit codes: 0=success, 1=validation error, 2=DB error
  12. Print confirmation: `"Stored: {name} (id: {hash})"`
- **Test:** Valid entry JSON → DB entry with correct hash. Invalid JSON exits 1. Provider unavailable → stored without embedding. Pending batch processes up to 50.
- **Done when:** Writer upserts entries, generates embeddings, processes pending batch, correct exit codes

#### Task 4.3: Implement MCP memory server
- **Why:** Plan 4.3 / C6 — standalone MCP server for mid-session capture
- **Depends on:** T3.3 (phase gate; uses database.py, embedding.py, keywords.py)
- **Blocks:** T4.4
- **Files:** `plugins/iflow-dev/mcp/memory-server.py`
- **Do:**
  1. Create `plugins/iflow-dev/mcp/` directory if needed
  2. Create `memory-server.py` with `sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))`
  3. Import smoke test at startup: `from semantic_memory.database import MemoryDatabase`
  4. Define `_process_store_memory(db, provider, keyword_gen, name, description, reasoning, category, references) -> str`:
     - Validate inputs: non-empty name/description/reasoning, valid category
     - Compute content hash
     - Set `source='session-capture'` per spec D6 (MCP entries use session-capture, not "mcp")
     - Generate embedding if provider available
     - Generate keywords via keyword_gen
     - Upsert into DB
     - Return `"Stored: {name} (id: {hash})"`
  5. Create FastMCP server: `mcp = FastMCP("memory-server")`
  6. Lifespan handler: open DB connection on startup, close on shutdown
  7. `@mcp.tool() async def store_memory(name, description, reasoning, category, references=[])`:
     - Delegate to `_process_store_memory()`
  8. `mcp.run(transport="stdio")`
- **Test:** Call `_process_store_memory()` directly: creates entry with all fields. Invalid category returns error. Empty name returns error. Duplicate increments observation_count.
- **Done when:** `_process_store_memory()` works in isolation, MCP server structure is correct

#### Task 4.4: Write and run Phase 4 unit tests
- **Why:** Plan 4.4 — validate all entry points; phase gate for Phase 5
- **Depends on:** T4.1, T4.2, T4.3
- **Blocks:** T5.1, T5.2, T5.3 (phase gate)
- **Files:** `plugins/iflow-dev/hooks/tests/test_entry_points.py`
- **Do:**
  1. Create test file with sys.path.insert
  2. Test injector: mock DB → stdout format matches I10
  3. Test injector: diagnostic line has correct vector/fts5 counts
  4. Test injector: recall tracking increments after injection
  5. Test injector: empty DB triggers import with provider=None, keyword_gen=None
  6. Test writer: valid entry JSON → correct content hash in DB
  7. Test writer: invalid JSON → exit code 1
  8. Test writer: pending batch processes up to 50 entries
  9. Test MCP: _process_store_memory creates entry, invalid category rejected, empty name rejected
  10. Test MCP: duplicate entry increments observation_count
- **Test:** `cd plugins/iflow-dev && .venv/bin/python -m pytest hooks/tests/test_entry_points.py -v`
- **Done when:** All tests pass green

---

### Phase 5: Integration

#### Task 5.1: Modify session-start.sh for semantic branch
- **Why:** Plan 5.1 / TD4 — bash hook branches on memory_semantic_enabled
- **Depends on:** T4.4 (phase gate; uses injector.py)
- **Blocks:** T6.1
- **Files:** `plugins/iflow-dev/hooks/session-start.sh`
- **Do:**
  1. Read current `build_memory_context()` function in session-start.sh
  2. Add `memory_semantic_enabled` config read via `read_local_md_field`
  3. **Toggle precedence:** If `memory_injection_enabled` is `false`, skip both paths entirely (no memory output). If `memory_injection_enabled` is `true` (or unset, default true): check `memory_semantic_enabled` to choose path.
  4. Add venv Python resolution: check `${plugin_dir}/.venv/bin/python`, fallback to `python3`
  5. Add if/else branch:
     - `true`: invoke `$python_cmd ${SCRIPT_DIR}/lib/semantic_memory/injector.py --project-root "$PROJECT_ROOT" --limit "$limit" --global-store "$HOME/.claude/iflow/memory"` with timeout and stderr suppression
     - `false`: invoke existing `memory.py` path unchanged
  6. Both paths wrapped in `$timeout_cmd ... 2>/dev/null) || memory_output=""`
- **Test:** Run `test-hooks.sh` (Test 6, Test 7) to verify no regressions. Verify semantic branch: capture stdout of `build_memory_context()` with `memory_semantic_enabled: true`, assert output contains substring `semantic: active` in diagnostic line. Verify fallback: with `false`, assert output contains `semantic: disabled`.
- **Done when:** test-hooks.sh passes, semantic branch produces output with `semantic: active` diagnostic

#### Task 5.2: Update retrospective skill and retro-facilitator agent output schema
- **Why:** Plan 5.2 / TD6 — retro Step 4 dual-writes to SQLite with keyword/reasoning extraction
- **Depends on:** T4.4 (phase gate; uses writer.py)
- **Blocks:** T6.1
- **Files:** `plugins/iflow-dev/skills/retrospecting/SKILL.md`, `plugins/iflow-dev/agents/retro-facilitator.md`
- **Do:**
  1. Read current SKILL.md Step 4 to understand existing write logic
  2. Add conditional block after existing markdown write:
     ```
     If memory_semantic_enabled: true:
       Extract from agent response: keywords, reasoning (default [] and "" if missing)
       Build entry JSON with field mapping:
         agent text → description, provenance → references, confidence → confidence,
         keywords → keywords, reasoning → reasoning
       Invoke: writer.py --action upsert --global-store $HOME/.claude/iflow/memory --entry-json '{...}'
     ```
  3. Read current retro-facilitator.md Act section
  4. Add to Act section output instructions (retro-facilitator is a read-only analysis agent — it outputs structured text that SKILL.md Step 4 processes; the agent does NOT write to the DB directly):
     - `keywords: array of 3-10 lowercase keyword strings` with quality constraints matching C3 prompt
     - `reasoning: string explaining WHY this matters (1-2 sentences)`
  5. Update output schema example in retro-facilitator.md to include keywords and reasoning fields
- **Test:** Review: SKILL.md Step 4 has conditional dual-write. retro-facilitator.md includes keywords/reasoning in output schema. Functional: `writer.py --entry-json '{"name":"test","description":"test","category":"patterns"}'` succeeds with missing keywords/reasoning (backward-compat defaults).
- **Done when:** SKILL.md has dual-write block, retro-facilitator.md has updated output schema, SKILL.md remains under 500 lines and 5,000 tokens per CLAUDE.md budget (if exceeded, extract dual-write logic into a helper reference)

#### Task 5.3: Register MCP server in .mcp.json
- **Why:** Plan 5.3 / TD7 — register memory-server MCP endpoint
- **Depends on:** T4.4 (phase gate; uses memory-server.py)
- **Blocks:** T6.1
- **Files:** `.mcp.json`
- **Do:**
  1. Read current `.mcp.json`
  2. Add `memory-server` entry to `mcpServers`:
     ```json
     "memory-server": {
       "command": "plugins/iflow-dev/.venv/bin/python",
       "args": ["plugins/iflow-dev/mcp/memory-server.py"]
     }
     ```
  3. Verify JSON is valid
- **Test:** `jq '.mcpServers["memory-server"]' .mcp.json` returns the correct config object
- **Done when:** `.mcp.json` has valid memory-server entry

---

### Phase 6: Validation

#### Task 6.1: Write end-to-end integration tests
- **Why:** Plan 6.1 — AC1b, AC2, AC3, AC4, AC6, AC7, AC9a validation
- **Depends on:** T5.1, T5.2, T5.3
- **Blocks:** T6.2
- **Files:** `plugins/iflow-dev/hooks/tests/test_integration.py`
- **Do:**
  1. Create integration test file with sys.path.insert
  2. **AC1b (semantic relevance):** Create test DB with 50 entries (20 parser, 20 deployment, 10 testing), all with controlled prominence (obs_count=1, confidence=medium). Mock embeddings: parser entries cosine similarity >0.8 to test query, others <0.3. Assert 18/20 parser entries in top 25.
  3. **AC9a (timeout safety):** Create 10K entries with random pre-normalized float32 (10000,768) mock embeddings. Time the `matrix @ query_embedding` matmul plus `RankingEngine.rank()` only — excluding DB I/O, embedding generation, and FTS5 search. Assert <100ms.
  4. **AC2 (cross-project):** Create entry with `source_project="project-a"`, run retrieval with different project_root context, verify entry appears in results.
  5. **AC3 (recall tracking):** Run 3 injection cycles on same DB. Assert entry recall_count=3 and last_recalled_at updated after each cycle.
  6. **AC4 (MCP capture):** Call `_process_store_memory()`, verify entry in DB, run injector, verify entry appears in output.
  7. **AC6 (toggle fallback):** Test at bash integration level: mock session-start.sh's `build_memory_context()` with `memory_semantic_enabled: false`, verify it invokes `memory.py` (not `injector.py`). With `true`, verify it invokes `injector.py`. Test by capturing the command string or mocking the Python invocation.
  8. **AC7 (degradation chain):** (a) provider=None: retrieval uses FTS5+prominence only, no errors. (b) fts5_available=False: retrieval uses vector+prominence only, no errors. (c) DB unavailable (FileNotFoundError): falls back gracefully, empty output.
  9. Each test scenario is a separate test function
  10. **Note:** AC1 (full embedding quality integration test) is intentionally omitted — spec notes it is environment-dependent and not suitable for CI. AC1b (pre-computed embeddings) provides deterministic ranking validation. Add a comment in test_integration.py documenting this.
- **Test:** `cd plugins/iflow-dev && .venv/bin/python -m pytest hooks/tests/test_integration.py -v`
- **Done when:** All 7 AC test scenarios pass green

#### Task 6.2: Run validate.sh and verify all tests pass
- **Why:** Plan 6.2 / AC13 — no regressions from new files
- **Depends on:** T6.1
- **Blocks:** None
- **Files:** No new files
- **Do:**
  1. Run `./validate.sh` from project root
  2. If validation fails: fix issues (likely line counts, formatting)
  3. Run full pytest suite: `cd plugins/iflow-dev && .venv/bin/python -m pytest hooks/tests/ -v`
  4. Verify all test files pass: test_foundation.py, test_core_modules.py, test_pipelines.py, test_entry_points.py, test_integration.py
- **Test:** `./validate.sh` exits 0. All pytest files pass.
- **Done when:** Both validate.sh and full pytest suite exit 0

## Summary

- **Total tasks:** 24
- **Phases:** 7 (Phase 0-6)
- **Parallel groups:** 7 (plus 4 phase gates and 1 sequential group)
- **Critical path:** T0.1 → T1.1 → T1.3 → T1.4 → T1.5 → T2.1 → T2.2 → T2.5 → T3.1 → T3.3 → T4.1 → T4.4 → T5.1 → T6.1 → T6.2 (15 tasks)
