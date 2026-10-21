# Spec: Memory System Phase 2 — Quality & Influence

## Problem Statement

pd's semantic memory system delivers entries to subagents (Feature 055) but has three remaining quality gaps from the PRD (docs/features/057-memory-phase2-quality/prd.md):

1. **Keywords always empty** — FTS5 BM25 scoring operates on name/description/reasoning but the `keywords` column is always `"[]"` (keyword generator was deleted as dead code in Feature 055). The 0.2 weight allocated to keyword matching contributes nothing.
2. **Near-duplicates accumulate** — 766 entries with no dedup at capture time. Different wordings of the same learning create separate entries, diluting retrieval quality.
3. **No influence measurement** — `recall_count` tracks injection but not whether injected memories actually influenced agent behavior. The feedback loop is open at consumption.

## Scope

Three sub-features in one delivery:
1. **Gap 3c:** Tiered keyword extraction — coding agent first, LLM API fallback
2. **Gap 2a:** Semantic deduplication at capture time
3. **Gap 4:** Influence measurement after subagent dispatch

## Requirements

### FR-1: Tiered keyword extraction at store_memory time

When `store_memory` is called, extract 3-10 keywords from the entry using a tiered approach:

**Tier 1 — Regex/heuristic extraction (primary, zero-cost):**
Extract keywords from the entry's name, description, and reasoning using pattern matching:
1. Split text into tokens, lowercase
2. Filter to tokens matching `_KEYWORD_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")`
3. Remove stopwords: `["code", "development", "software", "system", "application", "implementation", "feature", "project", "function", "method", "file", "data", "error", "bug", "fix", "update", "change"]`
4. Extract multi-word terms: scan for hyphenated tokens (e.g., "content-hash", "fts5-search") that already match `_KEYWORD_RE`. Also join consecutive sequences of 2 capitalized words as hyphenated terms (e.g., "Entity Registry" → "entity-registry").
5. Deduplicate and limit to 3-10 keywords
6. If result has >= 3 keywords: return (skip Tier 2)

**Tier 2 — LLM API fallback (only when Tier 1 produces < 3 keywords):**
Call Gemini's `generateContent` API (via `google.genai.Client.models.generate_content()`, NOT the embedding endpoint) with the following prompt template:

```
KEYWORD_PROMPT = (
    "Extract 3-10 keyword labels from this knowledge bank entry.\n"
    "\n"
    "Title: {name}\n"
    "Content: {description}\n"
    "Reasoning: {reasoning}\n"
    "Category: {category}\n"
    "\n"
    'Return ONLY a JSON array of lowercase keyword strings. '
    'Example: ["fts5", "sqlite", "content-hash", "parser-error"]\n'
    "\n"
    "Rules:\n"
    "- Use specific technical terms (tool names, patterns, file types, techniques)\n"
    "- 1-3 words per keyword, lowercase, hyphenated if multi-word\n"
    "- EXCLUDE generic words: code, development, software, system, application, "
    "implementation, feature, project, function, method, file, data, error, bug, fix, update, change\n"
    "- Minimum 3, maximum 10 keywords"
)
```

Parse the JSON array response. Validate each keyword against `_KEYWORD_RE` + stopword filter. Use model `gemini-2.0-flash` for low cost/latency. Requires `GEMINI_API_KEY` (same key as embeddings). If API call fails, return empty list (keywords stay empty for this entry — backfill can retry later).

**Implementation location:** New `extract_keywords()` function in a new `plugins/pd/hooks/lib/semantic_memory/keywords.py` file (reusing the filename). Called from `_process_store_memory()` in memory_server.py.

**Backfill:** Add a `backfill-keywords` subcommand to the writer CLI (`semantic_memory.writer`) that iterates all entries with empty keywords and runs the tiered extraction. This is a one-time batch operation for the 766 existing entries.

**What stays unchanged:** The `keywords` TEXT column, FTS5 trigger indexing keywords, and `memory_keyword_weight: 0.2` config key all remain from Feature 055 (they were intentionally kept).

### FR-2: Semantic deduplication at capture time

Before storing a new entry via `store_memory`, check for semantic near-duplicates:

1. Compute the embedding for the new entry's `description` text
2. If embedding provider is available, compute cosine similarity against the top-5 existing entries (by vector similarity to the new entry)
3. If any existing entry has similarity > 0.90: **merge** instead of creating new
   - Increment `observation_count` on the existing entry
   - Update `updated_at` timestamp
   - Merge keywords (union of existing + new)
   - Return "Reinforced: {existing name} (observation #{count})" instead of "Stored: ..."
4. If no near-duplicate found (or embedding provider unavailable): store normally

**Implementation location:** In `_process_store_memory()` in memory_server.py, after validation but before `db.upsert_entry()`.

**Threshold:** 0.90 (configurable via `memory_dedup_threshold` in pd.local.md, default 0.90). Higher than the PRD's suggested 0.85 to reduce false merges.

**Graceful degradation:** If embedding provider is unavailable (no API key, numpy missing), skip dedup and store normally. The content-hash dedup that already exists (same description → same ID → upsert increments observation_count) still operates as a safety net.

### FR-3: Influence measurement after subagent dispatch

After each subagent completes, scan its output for references to injected memory entries and record matches.

**Mechanism — orchestrator-side scanning:**
The pre-dispatch memory enrichment (Feature 055 FR-1) injects entries with their names in the `## Relevant Engineering Memory` section. After the subagent returns, the orchestrator checks if any injected entry names appear in the subagent's output text.

**Implementation:** Add a post-dispatch instruction block to each of the 5 workflow command files, placed AFTER each `Task tool call:` block that has a pre-dispatch enrichment:

```markdown
**Post-dispatch influence check:** After receiving the agent's response above,
check if any entries from the "## Relevant Engineering Memory" section were
referenced or applied in the output. For each referenced entry, call
`record_influence` with entry_name={name} and agent_role={role}.
```

**New MCP tool — `record_influence`:**
```
record_influence(
  entry_name: str,   # name of the memory entry that was referenced
  agent_role: str,   # e.g., "implementer", "spec-reviewer"
  feature_type_id: str | None  # current feature context
) -> str
```

Looks up the entry by name (fuzzy match: case-insensitive substring), increments `influence_count` on the entry, and logs to a new `influence_log` table.

**Schema addition — `influence_log` table:**
```sql
CREATE TABLE IF NOT EXISTS influence_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT NOT NULL,
    agent_role TEXT NOT NULL,
    feature_type_id TEXT,
    timestamp TEXT NOT NULL
);
```

**Schema addition — `influence_count` column on `entries`:**
```sql
ALTER TABLE entries ADD COLUMN influence_count INTEGER DEFAULT 0;
```

**Ranking integration:** In `_prominence()` in ranking.py, add `influence_count` as a signal alongside `recall_count`. New formula:
```
prominence = 0.25 * norm_obs + 0.15 * confidence + 0.25 * recency + 0.15 * recall + 0.20 * influence
```

Where `influence = min(influence_count / 10.0, 1.0)` (same scaling as recall_frequency).

**Reliability note:** Like the pre-dispatch enrichment, the post-dispatch scanning is prompt-instructed and not deterministic. The orchestrator may skip the check under context pressure. This is accepted — influence tracking provides directional data, not exact counts.

## Non-Requirements (Out of Scope)

- **NR-1:** Confidence auto-promotion (Gap 2b) — deferred from PRD Phase 2 to a future feature. Rationale: auto-promotion depends on semantic dedup (Gap 2a, this feature) to prevent inflated observation_count from merge-only increments. Implementing them together risks masking dedup bugs. Ship dedup first, validate, then add promotion.
- **NR-2:** Project-scoped filtering (Gap 3a) — deferred from PRD Phase 2 to a future feature. Rationale: project filtering benefits from keyword-enriched ranking (Gap 3c, this feature). Keywords must be populated first so the two-tier blend has quality signals to rank by.
- **NR-3:** Recall dampening (Gap 3d) — deferred to Phase 3
- **NR-4:** First-pass notable catches (Gap 2c) — deferred to Phase 3
- **NR-5:** Changing the `entries` table schema beyond adding `influence_count`
- **NR-6:** Changing the FTS5 trigger (keywords are already indexed)
- **NR-7:** Real-time influence streaming — the post-dispatch scan is batch per agent response

## Acceptance Criteria

### AC-1: Tiered keyword extraction works
Given an entry with name "Verify codebase facts before artifact review" and description mentioning "grep", "source files", "factual claims": `extract_keywords()` returns >= 3 keywords including domain-specific terms. Verified by unit test with controlled input.

### AC-2: Tier 1 produces keywords for typical entries without API calls
Given 10 representative entries from the knowledge bank, Tier 1 (regex/heuristic) produces >= 3 keywords for at least 7 of them. Verified by unit test.

### AC-3: Tier 2 fires only when Tier 1 fails
Given an entry where Tier 1 produces < 3 keywords, Tier 2 (LLM API) is called. Given an entry where Tier 1 produces >= 3 keywords, Tier 2 is NOT called. Verified by unit test with mock API.

### AC-4: Keywords stored on new entries
After `store_memory` is called with a typical entry, the stored entry's `keywords` field is a non-empty JSON array with 3-10 elements. Verified by unit test: call `store_memory`, read entry from DB, assert `len(json.loads(entry["keywords"])) >= 3`.

### AC-5: Backfill command exists and works
`semantic_memory.writer --action backfill-keywords` processes entries with empty keywords. Verified by running on test DB.

### AC-6: Semantic dedup merges near-duplicates
Given two entries with cosine similarity > 0.90, the second `store_memory` call increments `observation_count` on the first entry instead of creating a new one. Return message contains "Reinforced:". Verified by unit test.

### AC-7: Dedup threshold configurable
`memory_dedup_threshold` in pd.local.md controls the similarity threshold. Default 0.90. Verified by config read test.

### AC-8: Influence tracking records matches
After a subagent dispatch that references an injected memory entry name in its output, `record_influence` is called and `influence_count` is incremented. Verified by unit test of the MCP tool.

### AC-9: Influence affects ranking
Entries with higher `influence_count` score higher in prominence ranking. Verified by unit test comparing ranking with and without influence signal.

### AC-10: Existing tests pass
All semantic memory tests, memory server tests, and ranking tests continue to pass.

## Dependencies

- `search_memory` MCP tool (exists, used for pre-dispatch enrichment)
- Gemini embedding provider (exists, used for cosine similarity)
- Gemini API key (needed for Tier 2 LLM keywords — graceful degradation if absent)
- `keywords` column + FTS5 trigger (exist, preserved from Feature 055)

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Tier 1 regex produces low-quality keywords for abstract entries | Medium | Low | Tier 2 LLM fallback catches these; 0.2 weight means keywords are supplementary, not primary |
| Dedup threshold 0.90 too aggressive — merges distinct entries | Low | Medium | Start conservative at 0.90; configurable; content-hash dedup is safety net |
| Dedup threshold 0.90 too conservative — misses near-dupes | Medium | Low | Threshold can be lowered later based on observation |
| Influence scanning skipped under context pressure | Medium | Low | Directional data, not exact counts; improves ranking signal over time |
| influence_log grows unboundedly | Low | Low | Pruning can be added later; entries are small (5 columns) |
| Schema migration (ALTER TABLE + new table) fails on locked DB | Low | Medium | Feature 056 atomic transactions + retry protect migration writes |
