# Design: Memory System Phase 2 — Quality & Influence

## Prior Art Research

### Codebase Patterns
- `_process_store_memory()` hardcodes `keywords_json = '[]'` (memory_server.py:76) — insertion point for keyword extraction
- Pre-normalized embeddings + matmul pattern for cosine similarity (retrieval.py:211) — reuse for dedup
- `database.py` has 3 migrations, `update_keywords()`, `get_all_embeddings()` returning (ids, matrix)
- FTS5 triggers auto-convert keyword JSON → tokens — no trigger changes needed
- `_prominence()` formula: `0.3*obs + 0.2*confidence + 0.3*recency + 0.2*recall` — rebalance for influence
- `config.py` DEFAULTS dict pattern for new settings
- `writer.py` --action choices=['upsert', 'delete'] — extend with 'backfill-keywords'

### External Research
- **KeyLLM/KeyBERT hybrid**: Embedding-based candidate identification + LLM refinement is state-of-art for short text. Pure regex insufficient for semantic keywords. Our Tier 1 (regex) + Tier 2 (LLM) aligns with this pattern.
- **Dedup thresholds**: Domain-specific tuning mandatory. False merges are the primary risk. Start conservative (0.90), inspect lowest-similarity merges, relax iteratively. Single universal threshold is an anti-pattern — but acceptable for v1 with configurable override.
- **Influence tracking**: MARK framework uses feedback-aware scoring — downstream task signals update entry scores. Our `influence_count` approach is a simplified version of this pattern. Directional data is sufficient without perfect attribution.

---

## Architecture Overview

Three independent subsystems added to the existing semantic memory pipeline, all converging in the `store_memory` hot path:

```
store_memory() call
    │
    ├─ 1. Extract keywords (new keywords.py)
    │     Tier 1: regex/heuristic → if >= 3 keywords, done
    │     Tier 2: Gemini generateContent → parse + validate
    │
    ├─ 2. Dedup check (new dedup.py)
    │     Embed description → top-5 similarity → threshold check
    │     If match: merge (increment obs_count, union keywords)
    │     If no match: proceed to store
    │
    └─ 3. Store entry (existing database.py)
          keywords populated, influence_count column available
          FTS5 triggers index keywords automatically

Post-dispatch (orchestrator-side):
    Agent returns → scan output for injected entry names
    → record_influence MCP tool → increment influence_count + log
```

### Data Flow

```
                    ┌──────────────┐
  store_memory() ──►│ keywords.py  │──► keywords JSON
                    │  extract()   │
                    └──────────────┘
                           │
                           ▼
                    ┌──────────────┐     ┌─────────────┐
                    │  dedup.py    │────►│ MERGE path  │──► update existing entry
                    │  check()     │     │ (obs_count++) │   (keywords union, timestamp)
                    └──────────────┘     └─────────────┘
                           │ no match
                           ▼
                    ┌──────────────┐
                    │ database.py  │──► INSERT new entry
                    │ upsert_entry │    (with keywords)
                    └──────────────┘

  ── Post-dispatch ──

  Agent output ──► scan for entry names ──► record_influence()
                                                │
                                           ┌────┴────┐
                                           │influence │
                                           │_log table│
                                           └─────────┘
```

---

## Components

### C1: Keyword Extractor (`plugins/pd/hooks/lib/semantic_memory/keywords.py`)

**New file.** Provides `extract_keywords(name, description, reasoning, category, config)` → `list[str]`.

Two-tier extraction:
- **Tier 1**: Regex/heuristic. Tokenize, filter by `_KEYWORD_RE`, remove stopwords, extract multi-word hyphenated terms. Zero-cost, no external calls.
- **Tier 2**: Gemini `generateContent` with `KEYWORD_PROMPT` template. Only fires when Tier 1 produces < 3 keywords. Uses `gemini-2.0-flash` model via existing `google.genai.Client`.

**Dependencies**: `google.genai` (optional, Tier 2 only), `re` (stdlib).

### C2: Dedup Checker (`plugins/pd/hooks/lib/semantic_memory/dedup.py`)

**New file.** Provides `check_duplicate(embedding_vec, db, threshold)` → `DedupResult`.

```python
@dataclass
class DedupResult:
    is_duplicate: bool
    existing_entry_id: str | None  # ID of matched entry if duplicate
    similarity: float              # highest similarity score
```

Takes a pre-computed embedding vector (not raw text) to avoid double-computation. The caller (`_process_store_memory`) computes the embedding once and passes it to both dedup and storage. The embedding is NOT returned in DedupResult — the caller already has it.

Uses existing `get_all_embeddings()` + matmul pattern from retrieval.py. `get_all_embeddings()` returns `(ids: list[str], matrix: np.ndarray)` — entry ID lookup via `ids[np.argmax(scores)]`. Self-matching is not possible because the new entry hasn't been inserted yet at dedup check time. Threshold from `config["memory_dedup_threshold"]` (default 0.90).

**Dependencies**: `numpy`, `semantic_memory.database`, `semantic_memory.embedding`.

### C3: Influence Tracker (extensions to `memory_server.py` + `database.py`)

**New MCP tool** `record_influence(entry_name, agent_role, feature_type_id)` in memory_server.py.

**Schema additions** in database.py Migration 4:
- `influence_count INTEGER DEFAULT 0` column on `entries`
- `influence_log` table (id, entry_id, agent_role, feature_type_id, timestamp)

**Ranking update** in ranking.py: `_prominence()` rebalanced to include influence signal.

### C4: Backfill Command (extension to `writer.py`)

New `--action backfill-keywords` choice in writer CLI. Iterates entries with `keywords = '[]'`, runs `extract_keywords()` on each, calls `db.update_keywords()`.

### C5: Config Extension (`config.py` + `pd.local.md`)

New key: `memory_dedup_threshold` (default: `0.90`, type: float).

---

## Technical Decisions

### TD-1: Keyword extraction as separate module vs. inline in memory_server

**Decision:** Separate `keywords.py` module.
**Rationale:** Testable in isolation. Tier 2 LLM call has its own error handling and mock surface. Backfill command reuses the same function. Follows existing module-per-concern pattern (embedding.py, ranking.py, retrieval.py).

### TD-2: Dedup as separate module vs. inline in memory_server

**Decision:** Separate `dedup.py` module.
**Rationale:** Same reasoning as TD-1. The dedup logic (embed → compare → decide) is a self-contained concern with its own test surface. The `_process_store_memory()` function stays as an orchestrator that calls out to keyword extraction, dedup check, and database write.

### TD-3: Dedup embedding computation — compute once, reuse for storage

**Decision:** Compute the embedding ONCE in `_process_store_memory()`, BEFORE the dedup check. Pass the pre-computed vector to `check_duplicate()`. If dedup passes (no match), reuse the same vector for `db.upsert_entry()` storage — skip the second embedding call.
**Rationale:** The existing flow computes the embedding after upsert. The new flow moves embedding computation earlier (after keyword extraction, before dedup check) so the same vector serves both dedup comparison and storage. This avoids the double-computation anti-pattern flagged in review.

### TD-4: Dedup merge strategy — upsert vs. direct UPDATE

**Decision:** Direct UPDATE via new `merge_duplicate()` method on database.
**Rationale:** `upsert_entry()` has complex logic for handling existing entries (skipping empty keywords, preserving fields). For dedup merging, we need precise control: increment `observation_count`, union keywords, update `updated_at`, but NOT overwrite name/description/reasoning/category. A dedicated method is clearer than repurposing upsert semantics.

### TD-5: Influence lookup — case-insensitive exact match with LIKE fallback

**Decision:** Case-insensitive exact match on entry `name` field, with parameterized `LIKE ? ESCAPE '\'` fallback if exact match fails.
**Rationale:** The orchestrator is instructed to pass the exact entry name from the `## Relevant Engineering Memory` section, so exact match (case-insensitive) is the primary lookup. LIKE fallback handles cases where the orchestrator truncates or slightly modifies the name. The `entry_name` parameter is the name as passed by the orchestrator, not raw agent output — the orchestrator does the output scanning and calls `record_influence` with the matched entry name. This simplifies the matching: no need for 3-word overlap heuristics.
**SQL safety:** LIKE fallback uses parameterized query (`LIKE ? ESCAPE '\'`) with `%` and `_` characters in `entry_name` escaped before constructing the `%{escaped_name}%` pattern. Prevents SQL wildcard injection from entry names containing special characters.

### TD-6: Influence recording — synchronous vs. async

**Decision:** Synchronous MCP tool call from orchestrator.
**Rationale:** The `record_influence` call is lightweight (one DB lookup + one INSERT + one UPDATE). No need for async infrastructure. The orchestrator calls it after each subagent returns, before proceeding to the next dispatch. If the call fails, it's logged and skipped — influence tracking is best-effort.

### TD-7: Migration strategy — ALTER TABLE + new table in single migration

**Decision:** Single Migration 4 function that: (1) `ALTER TABLE entries ADD COLUMN influence_count INTEGER DEFAULT 0`, (2) `CREATE TABLE IF NOT EXISTS influence_log (...)`.
**Rationale:** Both changes are needed together — influence recording requires both the column and the log table. SQLite ALTER TABLE ADD COLUMN is safe (no table rebuild). Following the existing migration pattern (MIGRATIONS dict with sequential keys).

### TD-8: Backfill batch size and error handling

**Decision:** Process all entries in a single pass, 50 at a time for Tier 2 API calls, continue on per-entry failures.
**Rationale:** 766 entries is small. Tier 1 (regex) is instant. Tier 2 (API) at ~100ms/call × worst case 766 entries = ~77s. Batching in groups of 50 provides progress feedback. Per-entry failures logged and skipped — the backfill can be re-run to retry failures.

### TD-9: Gemini client construction for Tier 2 keywords

**Decision:** Reuse the `google.genai.Client` construction pattern from `embedding.py:create_provider()` but call `client.models.generate_content()` instead of the embedding endpoint.
**Rationale:** Same API key (`GEMINI_API_KEY`), same client library. The spec explicitly calls for `generate_content()` on `gemini-2.0-flash`. Lazy-initialize the client only when Tier 2 is needed (< 3 keywords from Tier 1).

---

## Interfaces

### I1: `extract_keywords()` — keywords.py

```python
def extract_keywords(
    name: str,
    description: str,
    reasoning: str,
    category: str,
    config: dict | None = None,
) -> list[str]:
    """Extract 3-10 keywords from entry fields using tiered approach.

    Tier 1: Regex/heuristic (zero-cost)
    Tier 2: Gemini LLM (only if Tier 1 < 3 keywords and GEMINI_API_KEY available)

    Returns list of lowercase keyword strings. May return fewer than 3 if both tiers fail.
    """
```

Internal helpers:
```python
def _tier1_extract(text: str) -> list[str]:
    """Regex/heuristic keyword extraction."""

def _tier2_extract(name: str, description: str, reasoning: str, category: str) -> list[str]:
    """LLM-based keyword extraction via Gemini generateContent.

    Response parsing: strip markdown code fences (```json ... ```) and
    leading/trailing non-JSON text before json.loads(). Validate each
    keyword against _KEYWORD_RE + _STOPWORDS. If parsing fails after
    cleanup, return empty list (graceful degradation).
    """
```

Constants:
```python
_KEYWORD_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

_STOPWORDS = frozenset([
    "code", "development", "software", "system", "application",
    "implementation", "feature", "project", "function", "method",
    "file", "data", "error", "bug", "fix", "update", "change",
])

KEYWORD_PROMPT = (
    "Extract 3-10 keyword labels from this knowledge bank entry.\n"
    # ... (as specified in spec FR-1)
)
```

### I2: `check_duplicate()` — dedup.py

```python
@dataclass
class DedupResult:
    is_duplicate: bool
    existing_entry_id: str | None
    similarity: float

def check_duplicate(
    embedding_vec: np.ndarray,
    db: MemoryDatabase,
    threshold: float = 0.90,
) -> DedupResult:
    """Check if a new entry (by its pre-computed embedding) is a near-duplicate.

    Compares embedding_vec against all existing entries via matmul on
    normalized vectors. Uses db.get_all_embeddings() which returns
    (ids: list[str], matrix: np.ndarray). Match lookup: ids[np.argmax(scores)].

    Self-matching is not possible — the new entry hasn't been inserted yet.

    Graceful degradation: returns DedupResult(is_duplicate=False, None, 0.0)
    if numpy is unavailable or no entries exist in the database.

    Empty DB guard: if len(ids) == 0, return early before matmul.
    """
```

### I3: `merge_duplicate()` — database.py

```python
def merge_duplicate(
    self,
    existing_id: str,
    new_keywords: list[str],
) -> dict:
    """Merge a near-duplicate into an existing entry.

    Updates ONLY:
    - observation_count: incremented by 1
    - updated_at: refreshed to current timestamp
    - keywords: union of existing + new_keywords

    Preserves unchanged:
    - name, description, reasoning, category, confidence, references,
      source, source_project, source_hash, recall_count, influence_count,
      last_recalled_at, embedding, created_at, created_timestamp_utc

    Returns the updated entry dict (via get_entry after UPDATE).

    FTS5 re-indexing: the UPDATE triggers the existing entries_au AFTER
    UPDATE trigger, which rebuilds the FTS row automatically. No additional
    FTS5 work needed.
    """
```

### I4: `record_influence` — MCP tool in memory_server.py

```python
def _process_record_influence(
    entry_name: str,
    agent_role: str,
    feature_type_id: str | None = None,
) -> str:
    """Record that a memory entry influenced agent behavior.

    Lookup strategy (per TD-5):
    1. Case-insensitive exact match: SELECT WHERE LOWER(name) = LOWER(entry_name)
    2. Fallback: LIKE '%entry_name%' (case-insensitive)
    3. If no match found: return error message, do not raise

    On match:
    - Increments influence_count on the entry (UPDATE entries SET influence_count = influence_count + 1)
    - Inserts row into influence_log table

    Returns: "Recorded influence: {entry_name} by {agent_role}"
    or "Entry not found: {entry_name}" if no match.
    """
```

### I5: Database schema — Migration 4

```python
def _migration_4(conn: sqlite3.Connection, **_kwargs: object) -> None:
    """Add influence tracking: influence_count column + influence_log table.

    Follows existing migration calling convention — accepts **_kwargs
    because the migration runner passes fts5_available= to all migrations.
    """
    conn.execute("ALTER TABLE entries ADD COLUMN influence_count INTEGER DEFAULT 0")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS influence_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id TEXT NOT NULL,
            agent_role TEXT NOT NULL,
            feature_type_id TEXT,
            timestamp TEXT NOT NULL
        )
    """)
```

**Post-migration requirement:** Add `"influence_count"` to the `_COLUMNS` list (database.py:246) so that `_ALL_ENTRY_COLS` (used by `get_all_entries()`) includes the new column. `get_entry()` uses `SELECT *` and picks it up automatically.

**Note:** The `MIGRATIONS` dict type annotation (`dict[int, Callable[[Connection], None]]`) is looser than actual usage (runner passes `fts5_available=` kwarg). This is pre-existing — migration 4 follows the same `**_kwargs` pattern as migrations 2 and 3.

### I6: Updated `_prominence()` — ranking.py

```python
def _prominence(self, entry: dict) -> float:
    """Calculate prominence score with influence signal.

    New formula:
    prominence = 0.25 * norm_obs + 0.15 * confidence + 0.25 * recency
                + 0.15 * recall + 0.20 * influence

    Where influence = min(influence_count / 10.0, 1.0)
    """
```

### I7: Updated `_process_store_memory()` orchestration — memory_server.py

```python
# Pseudocode for updated flow:
def _process_store_memory(params):
    # 1. Validate params (existing)
    # 2. Extract keywords (NEW)
    keywords = extract_keywords(name, description, reasoning, category, config)
    keywords_json = json.dumps(keywords)
    # 3. Compute embedding EARLY (moved from step 5, per TD-3)
    #    Build partial dict for _embed_text_for_entry() (from writer.py)
    embedding_vec = None
    if embedding_provider:
        partial_entry = {"name": name, "description": description,
                         "keywords": keywords_json, "reasoning": reasoning}
        embed_text = _embed_text_for_entry(partial_entry)  # writer.py:103
        embedding_vec = embedding_provider.embed(embed_text, task_type="document")
    # 4. Check for duplicates (NEW) — uses pre-computed embedding
    if embedding_vec is not None:
        dedup_result = check_duplicate(embedding_vec, db, threshold)
        if dedup_result.is_duplicate:
            merged = db.merge_duplicate(dedup_result.existing_entry_id, keywords)
            return f"Reinforced: {merged['name']} (observation #{merged['observation_count']})"
    # 5. Build entry dict with keywords (existing, modified)
    # 6. Upsert entry with PRE-COMPUTED embedding (skip re-computation)
    #    entry["embedding"] = embedding_vec (serialized)
    return f"Stored: {name}"
```

### I8: Config addition — config.py

```python
DEFAULTS = {
    # ... existing keys ...
    "memory_dedup_threshold": 0.90,
}
```

### I9: Backfill CLI — writer.py

```python
# New action choice: 'backfill-keywords'
# When --action backfill-keywords:
def _backfill_keywords(db, config):
    """Backfill keywords for all entries with empty keywords.

    Iterates entries where keywords = '[]'.
    For each: extract_keywords() → db.update_keywords().
    Processes in batches of 50 with progress output.

    Note: embedding recomputation after keyword backfill is NOT needed.
    Keywords affect FTS5 scoring (indexed via triggers) independently of
    vector similarity. The embedding includes keywords in its text
    (via _embed_text_for_entry), but re-embedding all 766 entries for
    marginally different keyword text is not worth the API cost. Embeddings
    will naturally update when entries are next upserted via store_memory.
    """
```

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Tier 1 regex produces low-quality keywords for abstract entries | Medium | Low | Tier 2 LLM fallback catches these; 0.2 FTS5 weight means keywords are supplementary |
| Dedup false merges at 0.90 threshold | Low | Medium | Conservative threshold; configurable; log merges for review; content-hash dedup as safety net |
| `get_all_embeddings()` matmul slow with large corpus | Low | Low | 766 entries × 768 dims = ~2.3MB matrix; matmul is < 1ms. Viable up to ~10K entries (~30MB). Current growth rate (~750 over project lifetime) makes this unlikely within 2 years. Beyond 10K, consider ANN index. |
| Gemini API failure on Tier 2 keywords | Medium | Low | Graceful degradation: return empty list, entry stores with empty keywords. Backfill can retry. |
| `record_influence` entry name lookup returns wrong entry | Low | Medium | Case-insensitive exact match primary, LIKE fallback secondary. Orchestrator passes exact entry name. Influence is directional data, not exact counts. |
| Migration 4 fails on locked DB | Low | Medium | Feature 056 atomic transactions + retry protect migration writes. ALTER TABLE ADD COLUMN is lightweight. |

---

## File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `plugins/pd/hooks/lib/semantic_memory/keywords.py` | **New** | Tiered keyword extraction (Tier 1 regex + Tier 2 Gemini LLM) |
| `plugins/pd/hooks/lib/semantic_memory/dedup.py` | **New** | Semantic deduplication check via embedding cosine similarity |
| `plugins/pd/hooks/lib/semantic_memory/database.py` | Modify | Migration 4 (influence_count + influence_log), `merge_duplicate()` method, add `"influence_count"` to `_COLUMNS` list (line 246) |
| `plugins/pd/hooks/lib/semantic_memory/ranking.py` | Modify | `_prominence()` rebalanced with influence signal |
| `plugins/pd/hooks/lib/semantic_memory/config.py` | Modify | Add `memory_dedup_threshold` to DEFAULTS |
| `plugins/pd/hooks/lib/semantic_memory/writer.py` | Modify | Add `backfill-keywords` action |
| `plugins/pd/mcp/memory_server.py` | Modify | Integrate keywords + dedup in `_process_store_memory()`, add `record_influence` MCP tool |
| `.claude/pd.local.md` | Modify | Add `memory_dedup_threshold: 0.90` to memory config block |
| `plugins/pd/hooks/lib/semantic_memory/test_keywords.py` | **New** | Tests for keyword extraction (Tier 1 + Tier 2 with mocked API) |
| `plugins/pd/hooks/lib/semantic_memory/test_dedup.py` | **New** | Tests for dedup checker (threshold, merge path, graceful degradation) |
| `plugins/pd/hooks/lib/semantic_memory/test_database.py` | Modify | Tests for Migration 4, `merge_duplicate()` method |
| `plugins/pd/mcp/test_memory_server.py` | Modify | Tests for `record_influence` MCP tool |
| `plugins/pd/hooks/lib/semantic_memory/test_ranking.py` | Modify | Tests for updated `_prominence()` with influence signal |
