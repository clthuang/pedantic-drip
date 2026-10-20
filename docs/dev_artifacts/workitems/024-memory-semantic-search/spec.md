# Spec: Semantic Memory System

## Overview

Build a persistent, embedding-based semantic memory system for Claude Code that retrieves contextually relevant learnings across projects. Entries are stored in a SQLite database with pre-computed vector embeddings. At session start, the system generates a query embedding from the current context and retrieves the most semantically relevant entries using cosine similarity — replacing the current metadata-only ranking with true semantic understanding.

The system builds on Feature #023's memory injection pipeline (v2.11.0) and replaces the current `memory.py` (296 lines) which ranks entries solely by observation count, confidence, and recency. Markdown knowledge bank files remain importable but are no longer the primary storage.

## Problem

Three scaling limits in the current memory system:

1. **No semantic understanding.** Ranking by observation count/confidence/recency has zero awareness of session context. At 100+ entries, "Reviewer Iteration Count as Complexity Signal" (observation count 3) always outranks "Read real file samples when parsing" (observation count 1), even in a parser-building session. Keyword search (FTS5/BM25) improves this but still fails on semantic synonyms, paraphrases, and conceptual relationships.

2. **No mid-session capture.** Entries are created only during retrospectives. Debugging insights, codebase discoveries, and architectural decisions made mid-session are lost unless manually recalled during the next retro.

3. **Flat, unconnected entries.** No keyword labels for cross-topic discovery. No code/file references for traceability. No reasoning chains explaining *why* a conclusion was reached. No recall-frequency tracking for intelligent prioritisation.

## Deliverables

### D1: Persistent Memory Database

A SQLite database (`memory.db`) storing all memory entries with rich metadata. One database at `~/.claude/iflow/memory/memory.db`, aggregating learnings across all projects. This single global database replaces the local/global file split from Feature #023. All entries are stored globally with `source_project` tracking their origin project. Project-specific entries (those the retro classifies as project-local in Step 4c) are still stored in this global DB but tagged with their `source_project` — they are retrievable across projects when semantically relevant.

**Entry schema:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | TEXT PRIMARY KEY | Content hash: `SHA-256(" ".join(description.lower().strip().split()))[:16]` — matching current `memory.py` normalization |
| `name` | TEXT NOT NULL | Short title |
| `description` | TEXT NOT NULL | Full description including conclusions |
| `reasoning` | TEXT | Why this conclusion was reached, how it was discovered |
| `category` | TEXT NOT NULL | `anti-patterns` \| `patterns` \| `heuristics` |
| `keywords` | TEXT | JSON array, max 10 LLM-generated keyword labels |
| `references` | TEXT | JSON array of code files, features, projects |
| `observation_count` | INTEGER DEFAULT 1 | Times observed across retros |
| `confidence` | TEXT DEFAULT 'medium' | `high` \| `medium` \| `low` |
| `recall_count` | INTEGER DEFAULT 0 | Times injected into sessions, actively updated |
| `last_recalled_at` | TEXT | ISO timestamp of most recent injection |
| `created_at` | TEXT NOT NULL | ISO timestamp |
| `updated_at` | TEXT NOT NULL | ISO timestamp. Updated only on content changes and retro observations — NOT on re-embedding or metadata-only updates |
| `source` | TEXT NOT NULL | `retro` \| `session-capture` \| `manual` \| `import` |
| `source_project` | TEXT | Project where entry originated |
| `embedding` | BLOB | Pre-computed embedding vector (float32 array, serialised) |

The database also includes:
- An FTS5 virtual table indexing `name`, `description`, `keywords`, and `reasoning` for keyword-based fallback search.
- A `_metadata` table storing database-level settings: `embedding_provider`, `embedding_model`, `embedding_dimensions`, and `schema_version`. Used to detect provider changes and trigger re-embedding migration.

### D2: Retrieval Pipeline

Retrieval is responsible for finding candidate entries — it produces a scored candidate set but does NOT make the final selection. Retrieval and ranking are separate concerns.

**Step 1: Context signal collection.** Gather signals and compose into a context query string:
- **Feature name:** From `.meta.json` `slug` field of the active feature (if any)
- **Feature description:** First paragraph of `spec.md` (text before first `##` heading), or first paragraph of `prd.md` if spec unavailable. Max 100 words.
- **Current phase:** `lastCompletedPhase` from `.meta.json`
- **Recent file changes:** Changed filenames from `git diff --name-only HEAD~3..HEAD` (space-separated, max 20 files). Fallback for shallow history: if HEAD~3 is unreachable, try HEAD~1; if no commits exist, skip file changes signal entirely.
- **Composed query:** `"{feature_name}: {feature_description}. Phase: {phase}. Files: {changed_filenames}"`
- If no active feature, query is composed from git diff filenames only. If no signals at all, context query is None — skip both vector embedding generation (no API call) and FTS5 MATCH (no query terms to match). All entries are passed to ranking with zero retrieval scores; ranking uses prominence_score only (vector_weight and keyword_weight are zeroed, prominence_weight=1.0).

**Step 2: Multi-signal retrieval.** Run up to two independent retrieval strategies in parallel, each producing a candidate set with raw scores:

- **Vector retrieval (primary):** Generate a query embedding from the context query using the configured embedding provider (same model used at write time — see D4). Load all stored embeddings from the database, compute cosine similarity via numpy. At 10,000 entries x 768 dimensions = ~30MB, brute-force cosine similarity completes in <10ms. Output: all entries with a `vector_score` in [-1.0, 1.0].

- **Keyword retrieval (supplementary):** Run FTS5 MATCH query against `name`, `description`, `keywords`, and `reasoning` fields. Output: matching entries with a raw `bm25_score` (negated so higher = more relevant).

**Step 3: Merge.** Union the two candidate sets. Entries found by both strategies carry both scores. Entries found by only one carry a zero for the other.

**Degradation:**
- If embedding provider unavailable → vector retrieval skipped, keyword retrieval only
- If FTS5 unavailable → keyword retrieval skipped, vector retrieval only
- If both unavailable → all entries passed to ranking with zero retrieval scores
- If database unavailable → fall back to current MD-based `memory.py` pipeline entirely

### D3: Ranking Engine

Ranking takes the merged candidate set from retrieval and produces the final ordered selection. It combines retrieval scores with entry metadata signals.

**Scoring formula:**
```
final_score = (vector_weight * normalized_vector_score)
            + (keyword_weight * normalized_bm25_score)
            + (prominence_weight * prominence_score)
```

Where:
- `normalized_vector_score` = cosine similarity normalised to [0.0, 1.0] (divide by max in candidate set)
- `normalized_bm25_score` = BM25 score normalised to [0.0, 1.0] (divide by max in candidate set)
- `prominence_score` = weighted combination of:
  - Observation count (normalised by max across all entries)
  - Confidence level (high=3, medium=2, low=1, normalised to [0, 1])
  - Recency (content): hyperbolic decay `1.0 / (1.0 + days_since_updated / 30.0)` using `updated_at` — 30-day half-life, so a 1-day-old entry scores ~0.97, 30-day ~0.50, 90-day ~0.25. Note: `last_recalled_at` exists for diagnostic/tracking purposes but does NOT drive this recency component.
  - Recall frequency: `min(recall_count / 10.0, 1.0)` — linear up to 10 recalls, capped at 1.0

Default weights: `vector_weight=0.5`, `keyword_weight=0.2`, `prominence_weight=0.3`. User-configurable.

**Edge cases:** If max score for a signal is 0 (no matches from that retrieval path), treat its weight as 0 and redistribute proportionally to remaining signals — same as degradation behaviour. If all entries have identical scores for a signal, normalised score is 1.0 for all (no differentiation from that signal).

When a retrieval signal is unavailable (degradation), its weight is redistributed proportionally to the remaining signals.

**Selection:**
1. Score all candidates using the formula above
2. Apply category-balanced selection: min-3 entries per non-empty category (when limit >= 9), sorted by `final_score` within each category bucket
3. Fill remaining slots by `final_score` descending across all categories (intentional change from current `memory.py` which fills by category priority order — anti-patterns first; the new system removes category-priority bias in favor of relevance-based ranking)
4. Respect the injection limit

When all vector scores are identical, normalization to 1.0 is intentional — the signal provides no differentiation, so other signals (keyword, prominence) drive ranking.

### D4: Embedding Generation (Single Provider for Write and Query)

Write-time and query-time embeddings **must use the same model** — cosine similarity is only meaningful within a single embedding space. Different models (even at the same dimensionality) produce incompatible vector spaces.

**Single configurable provider** via adapter pattern:
- **Default:** Google Gemini `gemini-embedding-001` (free tier). Default output is 3072 dimensions; the system requests `output_dimensionality=768` to keep memory footprint low (~30MB at 10K entries). Claude Code requires internet, so network availability is a given.
- **Alternatives:** Voyage AI `voyage-code-3` (code-specialised), OpenAI `text-embedding-3-small`, Ollama `nomic-embed-text` (local, for users preferring offline operation)
- **Fallback chain:** Configured provider → store entry without embedding (keyword-only retrieval for that entry)
- **API key configuration:** Provider API keys are read from environment variables: `GEMINI_API_KEY`, `VOYAGE_API_KEY`, `OPENAI_API_KEY`. Ollama requires no key (local). If the configured provider's API key is missing, treat as provider unavailable (fall back to keyword-only retrieval). No API keys are stored in config files.

**Gemini-specific parameters:**
- `output_dimensionality=768` — reduces from default 3072 to keep memory footprint low
- `taskType=RETRIEVAL_DOCUMENT` for write-time embeddings (entry storage)
- `taskType=RETRIEVAL_QUERY` for query-time embeddings (context query at session start)
- These task types produce embeddings optimized for asymmetric retrieval (short query vs longer document)

**L2 normalization:** Gemini's documentation requires L2 normalization for sub-3072 dimensionalities. All embeddings (both write-time and query-time) are L2-normalized after generation before storage or comparison. This ensures accurate cosine similarity. The adapter interface includes normalization as a post-processing step, so alternative providers that already return normalized embeddings are unaffected (normalizing an already-normalized vector is a no-op).

**Write-time (entry creation/update):** Pre-compute embeddings when entries are created or updated — during retrospectives or MCP capture. No timeout constraint.

**Query-time (session start):** Generate an embedding for the context query string using the same provider. For Gemini (default), this adds ~200-700ms network latency, well within the 3-second budget. For local providers (Ollama), ~50ms. If the provider is unavailable at query time, vector retrieval is skipped entirely (keyword + prominence fallback).

**Provider change migration:** When the user changes `memory_embedding_provider`, all existing embeddings become invalid (wrong vector space). The system detects this via the `_metadata` table (stores current `embedding_provider` and `embedding_model`). Re-embedding is performed in batches of 50 entries per retro, with progress tracked in `_metadata`. If the provider returns HTTP 429 (rate limit), pause re-embedding and resume at next retro. Entries without valid embeddings fall back to keyword-only retrieval until re-embedded.

### D5: Keyword Label Generation (via Tiered Provider)

Each entry receives up to 10 keyword labels generated by an LLM at write time.

**Keyword generation provider (tiered):**
1. In-session Claude (free — the model is already running during retro)
2. Claude API Haiku (fast, cheap)
3. Ollama local model
4. Skip — entry stored without keywords (FTS5 indexes name/description directly)

`auto` mode tries providers in tier order (in-session Claude first, then Haiku, then Ollama), falling back to skip if all fail. Each tier times out after 5 seconds before falling to the next. Keyword generation failures are non-blocking — entries are stored with an empty keywords array and FTS5 indexes name/description directly. Keyword generation prompt to be defined during design phase.

Keywords are stored as a JSON array and indexed by FTS5 for keyword-based retrieval.

### D6: MCP Memory Capture Tool

An MCP tool `store_memory` that allows the model to save a learning mid-session.

**MCP server:** A new standalone Python MCP server (`plugins/iflow-dev/mcp/memory-server.py`) using stdio transport. Registered in the project root `.mcp.json` (alongside the existing Playwright entry) with `{"command": "python", "args": ["plugins/iflow-dev/mcp/memory-server.py"], "transport": "stdio"}`. The server connects directly to the SQLite database at `~/.claude/iflow/memory/memory.db`. Designed to be extensible — future tools like `search_memory` can be added without restructuring.

**Interface:**
```
store_memory(
  name: str,           # Short title (required)
  description: str,    # What was learned (required)
  reasoning: str,      # Why it matters, how it was discovered (required)
  category: str,       # anti-patterns | patterns | heuristics (required)
  references: list[str] # Related files, features, projects (optional, default [])
)
```

All fields except `references` are required. The tool rejects calls with empty `name`, `description`, `reasoning`, or invalid `category`.

Entries captured via MCP are:
- Stored immediately in the database with `source: "session-capture"`
- Embedding generated synchronously if provider is available, otherwise stored without embedding (keyword-only retrieval until next retro re-embeds)
- Keyword labels generated using the tiered provider
- Deduplicated against existing entries by content hash

### D7: Markdown Import and Backward Compatibility

**Import:** On first run (or when the database is empty), import all entries from existing markdown knowledge bank files (local `docs/dev_artifacts/knowledge-bank/*.md` and global `~/.claude/iflow/memory/*.md`) into the SQLite database. Imported entries get `source: "import"`. Embeddings and keywords are generated for imported entries.

**Toggle:** The entire semantic memory system can be enabled or disabled via configuration:
- `memory_semantic_enabled: true` — use SQLite + embeddings retrieval
- `memory_semantic_enabled: false` — fall back to current MD-based `memory.py` pipeline (no SQLite, no embeddings, exact current behaviour)

This toggle enables gradual rollout and provides a safety net.

### D8: Recall Tracking

Each time an entry is injected into a session, increment its `recall_count` and update `last_recalled_at`. This data feeds into the prominence score — frequently recalled entries are "likely" to matter more and receive a scoring boost.

Recall tracking is written back to the database after each injection cycle.

### D9: Retrospective Integration

Extend the retrospecting skill to write entries into both the SQLite database AND markdown files (dual-write). SQLite is the source of truth for retrieval; markdown files are an append-only human-readable audit trail. Manual edits to markdown files are NOT synced back to the database. If the database is corrupted or deleted, D7's import mechanism can rebuild it from markdown files (idempotent via content hash). This preserves the existing retro Steps 4b/4c logic (staleness validation, global promotion).

1. During retro Step 4 (knowledge bank update), entries are written to both markdown files (existing behaviour) and the SQLite database
2. Embedding generated via configured provider
3. Keyword labels generated via in-session Claude
4. Code references populated from the git diff of the feature branch
5. Reasoning field populated from the retro analysis context
6. If `memory_semantic_enabled: false`, entries are written to markdown files only (current behaviour), no database operations

### D10: Diagnostic Output

Extend the injected memory block with a diagnostic line:

**When semantic retrieval active:**
```
*Memory: {N} entries from {total} | semantic: active (vector={n_vector_matches}, fts5={n_keyword_matches}) | context: "{truncated_query}..." | model: {embedding_model}*
```

**When falling back to MD-based:**
```
*Memory: {N} entries ({local} local, {global} global) | semantic: disabled*
```

## Acceptance Criteria

1. **Semantic relevance measurable (integration):** Given a 50-entry test database (20 about "parser" topics, 20 about "deployment" topics, 10 about "testing" topics — all with similar observation counts), and a context query "building a file parser with error handling", at least 15 of the 20 parser entries appear in the top 25 selected entries. With the current prominence-only system, parser entries appear no more frequently than any other category (statistical baseline ~10/25). *Note: This is an integration test dependent on embedding model quality. If the embedding model changes, thresholds may need recalibration.*

1b. **Ranking logic verifiable (unit):** Given a test database with pre-computed embeddings where 20 parser entries have cosine similarity >0.8 to the test query and 30 other entries have cosine similarity <0.3, at least 18 of 20 parser entries appear in the top 25. This isolates the ranking engine from embedding quality.

2. **Cross-project retrieval works:** An entry created in Project A with `source_project: "project-a"` is retrievable when working in Project B, ranked by semantic relevance to Project B's context.

3. **Recall tracking updates:** After 3 injection cycles where entry X is included, entry X's `recall_count` equals 3 and `last_recalled_at` reflects the most recent injection timestamp.

4. **MCP capture works:** Calling `store_memory` mid-session creates a database entry with all required fields populated. The entry is retrievable in subsequent sessions.

5. **Keyword labels generated:** Entries created during retrospectives have 3-10 keyword labels. At least 3 keywords per entry must either (a) appear as a substring in the entry's description or reasoning, OR (b) be a morphological variant (e.g., parse/parsing/parser) of a word in the description or reasoning. Keywords must not be from the generic stopword list: `[code, development, software, system, application, implementation, feature, project, function, method, file, data, error, bug, fix, update, change]`.

6. **Toggle fallback works:** Setting `memory_semantic_enabled: false` produces output identical to the current `memory.py` system. No SQLite queries, no embedding operations.

7. **Degradation chain works:** (a) With embedding provider unavailable: retrieval uses FTS5 + prominence, no errors. (b) With FTS5 unavailable: retrieval uses vector + prominence, no errors. (c) With database unavailable: falls back to MD-based pipeline, no errors.

8. **Import populates database:** On first run with an empty database, all existing markdown entries are imported with correct field mapping. Deduplication by content hash prevents double-import on subsequent runs.

9. **Timeout safety:** Two checks: (a) Local computation (vector search + scoring + formatting, excluding network) completes in <100ms for 10,000 entries with mock embeddings (random float32 arrays of shape (10000, 768), pre-normalized to unit length). (b) End-to-end including Gemini query embedding completes within 2 seconds (best-effort, environment-dependent, not a hard gate for CI). The full pipeline must not exceed the 3-second `session-start.sh` timeout.

10. **References populated:** Entries created during retros include at least one code file reference from the feature's git diff.

11. **Reasoning captured:** Entries created during retros include a non-empty reasoning field explaining why the conclusion matters.

12. **Category balance preserved:** At least 3 entries per non-empty category when limit >= 9.

13. **`./validate.sh` passes** including Python compilation checks.

## Configuration

All settings in `iflow-dev.local.md` YAML frontmatter:

```yaml
# Core toggle
memory_semantic_enabled: true          # true = SQLite + embeddings; false = MD-based fallback

# Retrieval weights (must sum to 1.0)
memory_vector_weight: 0.5             # Weight for vector cosine similarity
memory_keyword_weight: 0.2            # Weight for FTS5 BM25 keyword match
memory_prominence_weight: 0.3         # Weight for prominence (obs count, confidence, recency, recall)

# Embedding configuration (single provider for both write-time and query-time)
memory_embedding_provider: gemini     # gemini (default, free) | voyage | openai | ollama
memory_embedding_model: gemini-embedding-001  # Model name within provider

# Keyword generation
memory_keyword_provider: auto         # auto = in-session Claude → Haiku → Ollama | claude | haiku | ollama | off

# Existing (from Feature #023)
memory_injection_enabled: true        # Master on/off for memory injection
memory_injection_limit: 20            # Max entries injected per session
```

All new configuration fields have sensible defaults. Existing `iflow-dev.local.md` files without these fields use defaults: `memory_semantic_enabled: true`, `memory_vector_weight: 0.5`, `memory_keyword_weight: 0.2`, `memory_prominence_weight: 0.3`, `memory_embedding_provider: gemini`, `memory_keyword_provider: auto`. No manual configuration changes are required for basic operation.

## Scope Boundaries

### In Scope
- Persistent SQLite database for memory entries
- Pre-computed embedding vectors stored at write time
- Cosine similarity retrieval via numpy at query time (keyword + prominence fallback if numpy unavailable)
- FTS5 keyword search as supplementary retrieval signal
- Hybrid scoring (vector + keyword + prominence) with clear retrieval/ranking separation
- Single configurable embedding provider for both write and query (Gemini default, Voyage, OpenAI, Ollama)
- LLM-generated keyword labels (max 10 per entry)
- Code/file/feature references per entry
- Reasoning field per entry
- Recall count and recency tracking
- MCP `store_memory` tool for mid-session capture
- Toggle on/off with MD-based fallback
- Markdown import into database
- Diagnostic output
- Retrospective integration for database writes

### Out of Scope
- Real-time streaming capture (every tool call)
- Multi-user / team-shared memory
- Memory visualisation UI
- Graph-based knowledge relationships
- Custom embedding model training
- External knowledge base integration (Confluence, Notion)
- Pull-based mid-session retrieval MCP server (`search_memory` tool — future phase)
- Persistent index rebuild on retro write (replaced by persistent SQLite DB)
- Changes to existing knowledge bank markdown file format

## Technical Constraints

- **3-second timeout budget.** The `timeout 3` wrapper in `session-start.sh` is a hard kill — if the memory pipeline exceeds 3 seconds, the process is terminated and memory output is empty (existing fallback: `memory_output=""`). The retrieval pipeline targets 2 seconds to leave headroom. If any component (e.g., Gemini API) is slow, the system degrades gracefully within the budget rather than blocking. Write-time operations (embedding generation, keyword generation) have no timeout constraint.
- **Graceful degradation.** Every component in the retrieval chain must handle failure silently: embedding provider unavailable, FTS5 unavailable, database corrupted, numpy missing. The system must always produce valid output or fall back to MD-based injection.
- **Environment management.** Python managed via pyenv, dependencies via uv. No pip.
- **Single-file database.** SQLite provides single-file storage with ACID guarantees. No external database servers. Database opened with WAL journal mode and `busy_timeout=5000` to handle concurrent writes from MCP server and retro pipeline.
- **Network-dependent query path.** The default provider (Gemini) requires a network call at query time (~200-700ms). This is acceptable since Claude Code requires internet to function. Users preferring offline operation can switch to Ollama.

## Dependencies

- Python 3.9+ managed via pyenv; dependencies managed via uv (`uv add numpy`)
- sqlite3 + FTS5 (stdlib)
- numpy (for vector operations). If numpy is not importable, vector retrieval is skipped entirely and the system falls back to keyword + prominence retrieval only. (Pure-Python cosine similarity over 10K x 768 vectors would exceed the 2-second budget; numpy is the practical requirement for vector search.)
- Google Gemini API access (default embedding provider, free tier)
- Optional: Ollama/Voyage/OpenAI (alternative embedding providers, user-configured)
- Claude model access during retro for keyword generation (in-session, free)
- MCP server: new Python stdio server at `plugins/iflow-dev/mcp/memory-server.py`

## Open Questions

- **Keyword generation prompt:** Deferred to design phase. Must produce 3-10 keywords per entry satisfying AC5 constraints (content-specific, no stopwords).
- **Embedding BLOB serialization:** Exact serialization method (e.g., `numpy.ndarray.tobytes()`) to be decided in design.
- All other questions resolved during specification (5 spec-reviewer iterations).
