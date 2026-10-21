# Design: Memory Feedback Loop Hardening

**Feature:** 076-memory-feedback-loop-hardening
**Spec:** spec.md (source of truth)
**Created:** 2026-04-03

## Prior Art Research

| Question | Source | Finding |
|----------|--------|---------|
| How does store_memory currently handle source? | memory_server.py:80-81 | Hardcoded `source = "session-capture"` per spec D6. The DB column accepts retro/session-capture/manual/import but MCP only writes session-capture. |
| Where are ranking weights defined? | ranking.py:252 | `0.25*obs + 0.15*confidence + 0.25*recency + 0.15*recall + 0.20*influence` — influence at 20% but almost never >0 due to dormant tracking. |
| How does dedup work? | dedup.py:32, database.py:442 | `check_duplicate(embedding, db, threshold=0.90)` returns DedupResult. If duplicate found, `merge_duplicate()` increments observation_count and unions keywords. |
| How are embeddings computed? | embedding.py:96,331; writer.py:104,132 | `NormalizingProvider.embed(text, task_type)` produces unit-length vectors. Text built from name+description+keywords+reasoning. Available for arbitrary text via `provider.embed()`. |
| How does record_influence find entries? | memory_server.py:242-259 | `db.find_entry_by_name(entry_name)` — exact string match (case-insensitive, LIKE fallback). No embedding-based lookup. |
| What categories does the importer support? | importer.py:22-25 | 3 categories: anti-patterns, patterns, heuristics. Constitution excluded. |
| What categories does the injector support? | injector.py:34,36-40 | CATEGORY_ORDER and CATEGORY_HEADERS for same 3. VALID_CATEGORIES frozenset in __init__.py:8. |
| Mem0 write-time validation pattern? | arxiv:2504.19413 | ADD/UPDATE/DELETE/NOOP decided by LLM comparing candidate against top-10 similar. We adopt a lighter version: automated min-length + cosine near-duplicate rejection (no LLM in loop). |
| FadeMem ranking decay? | arXiv:2601.18642 | `R = importance × e^(-decay_rate × t)` with auto-prune at R<0.05. pd's current decay (`log(1/(1+days/30) + 1)`) is similar in spirit but has no pruning threshold. Out of scope. |

## Architecture Overview

```
                    Write Path Changes
                    ==================

  Caller (retro/      store_memory MCP         Tier 1 Gate              DB Writer
  remember/RCA/       (new: source param)      (new: min-length +       (unchanged)
  review-learnings)   ───────────────────>     near-duplicate check)    ────────>
                      memory_server.py:339     memory_server.py:~85     database.py
                      source default =         reject if <20 chars
                      "session-capture"        reject if cosine>0.95
                                               to existing entry

                    Read Path Changes
                    =================

  Ranking Engine       prominence formula       Session Injection        Phase Context
  ranking.py:252       weight redistribution    injector.py:34           SKILL.md Step 1b
  influence: 0.20→0.05 obs: 0.25→0.30          + constitution category  + reviewer_feedback_summary
  obs: 0.25→0.30       recency: 0.25→0.35
  recency: 0.25→0.35

                    Influence Tracking Changes
                    ==========================

  Post-dispatch        record_influence_by_content    Memory Server
  (14 locations in     (NEW MCP tool)                 Computes embedding,
  4 command files)     ──────────────────────────>    cosine similarity
                       subagent_output_text +          against injected entries
                       injected_entry_names            threshold >= 0.70
```

## Components

### C1: store_memory Source Parameter

**Location:** `plugins/pd/mcp/memory_server.py:339-347` (tool signature), `memory_server.py:80-81` (hardcoded source)

**Change:** Add `source: str = "session-capture"` parameter to the `store_memory` function signature. Remove the hardcoded `source = "session-capture"` at line 81. Pass the `source` parameter through to `_process_store_memory()`.

### C2: Tier 1 Quality Gate

**Location:** `plugins/pd/mcp/memory_server.py:~85` (inside `_process_store_memory`, before dedup check)

**Change:** Add two validation checks before the existing dedup logic:
1. If `len(description) < 20`: return error "Entry rejected: description too short (min 20 chars)"
2. Run `check_duplicate(embedding, db, threshold=0.95)`. If match found AND match.name != new_entry.name: return error "Entry rejected: near-duplicate of existing entry '{match.name}'"
3. If embedding provider unavailable: skip the near-duplicate check (log warning), proceed with min-length check only.

**Ordering:** min-length → near-duplicate → existing dedup (0.90 merge) → store. The 0.95 gate rejects before the 0.90 merge fires.

### C3: Ranking Weight Redistribution

**Location:** `plugins/pd/hooks/lib/semantic_memory/ranking.py:242,252`

**Change:** Update both the docstring and the formula:
```python
# Before: 0.25*obs + 0.15*confidence + 0.25*recency + 0.15*recall + 0.20*influence
# After:  0.30*obs + 0.15*confidence + 0.35*recency + 0.15*recall + 0.05*influence
```

### C4: record_influence_by_content MCP Tool

**Location:** `plugins/pd/mcp/memory_server.py` (new tool, after existing `record_influence`)

**Change:** New MCP tool that accepts subagent output text, computes its embedding, and compares against stored embeddings of injected entries.

### C5: Constitution Import

**Location:** `plugins/pd/hooks/lib/semantic_memory/importer.py:22-25`, `injector.py:34,36-40`, `__init__.py:8`

**Change:**
- Add `("constitution.md", "constitution")` to `CATEGORIES` in importer.py
- Add `"constitution"` to `CATEGORY_ORDER` in injector.py (at end, lowest priority)
- Add `"constitution": "### Core Principles"` to `CATEGORY_HEADERS` in injector.py
- Add `"constitution"` to `VALID_CATEGORIES` frozenset in `__init__.py`
- Add a rejection in `_process_store_memory` for `category="constitution"`: return "Entry rejected: constitution entries are import-only (edit docs/knowledge-bank/constitution.md directly)". Constitution is a read-only category — only `MarkdownImporter` writes it.

### C6: Injection Limit Alignment

**Location:** `plugins/pd/hooks/session-start.sh:421-422`

**Change:** Replace **both** hardcoded `"20"` values with `"15"`:
- Line 421: `read_local_md_field "$config_file" "memory_injection_limit" "20"` → `"15"`
- Line 422: regex fallback `limit="20"` → `limit="15"`

### C7: reviewer_feedback_summary Surfacing

**Location:** `plugins/pd/skills/workflow-transitions/SKILL.md:109` (omission note), Step 1b injection template

**Change:** In the `### Prior Phase Summaries` rendering format (which only renders during backward travel — when `phases[phaseName].completed` exists), add a `Reviewer feedback: {reviewer_feedback_summary}` line after the `Artifacts:` line. Conditional: only when non-null/non-empty. Update the omission note at line 109 to: "reviewer_feedback_summary is included during backward travel Phase Context injection, omitted during forward travel."

### C8: Review Learnings Threshold

**Location:** 8 locations across 4 command files (specify.md:353,358; design.md:614,619; create-plan.md:499,504; implement.md:1228,1233)

**Change:** Replace the trigger and grouping text at all 8 locations with a two-path template:

```markdown
**Trigger:** Only execute if the review loop ran 1+ iterations.

**Process:**
IF exactly 1 iteration with blocker issues:
  - Store each blocker directly via store_memory with confidence="low"
  - Skip recurring-pattern grouping (single observation, not a confirmed pattern)
  - Budget: max 2 entries

IF 2+ iterations:
  - Use existing recurring-pattern grouping logic (identify issues in 2+ iterations)
  - Store grouped patterns with confidence="low"
  - Budget: max 3 entries
```

### C9: Caller Source Propagation

**Location:** Multiple command/skill files that call `store_memory`

**Changes:**
- `plugins/pd/skills/retrospecting/SKILL.md` Step 3a: add `source="retro"` to store_memory call
- `plugins/pd/commands/remember.md`: add `source="manual"` to store_memory call
- All other callers (review learnings in 4 command files, RCA, wrap-up, capturing-learnings): use default `source="session-capture"` (no change needed — the default handles them)

## Interfaces

### I1: store_memory MCP — Updated Signature

```python
async def store_memory(
    name: str,
    description: str,
    reasoning: str,
    category: str,
    references: list[str] | None = None,
    confidence: str = "medium",
    source: str = "session-capture",  # NEW
) -> str:
```

### I2: Tier 1 Gate — Validation Flow

```python
def _process_store_memory(db, name, description, reasoning, category, references, confidence, source):
    # --- Tier 1 Gate: min-length ---
    if len(description) < 20:
        return "Entry rejected: description too short (min 20 chars)"

    # --- Existing: compute embedding ---
    embedding = compute_embedding(name, description, reasoning, ...)

    # --- Tier 1 Gate: near-duplicate (0.95) ---
    if embedding is not None:
        dup_result = check_duplicate(embedding, db, threshold=0.95)
        if dup_result.is_duplicate:
            matched_entry = db.get_entry(dup_result.existing_entry_id)
            matched_name = matched_entry["name"] if matched_entry else "unknown"
            if matched_name != name:
                return f"Entry rejected: near-duplicate of existing entry '{matched_name}'"
    # else: embedding unavailable, skip near-duplicate check (log warning)

    # --- Existing: dedup merge (0.90) ---
    # Optimization: reuse similarity scores from 0.95 check if available.
    # If 0.95 matched same-name → falls through to 0.90 merge path below.
    dup_result_merge = check_duplicate(embedding, db, threshold=0.90)
    if dup_result_merge.is_duplicate:
        db.merge_duplicate(dup_result_merge.existing_entry_id, ...)
        return f"Reinforced: {name}"

    # --- Store new entry ---
    db.upsert_entry({..., "source": source})
    return f"Stored: {name}"
```

**Notes:**
- The two `check_duplicate` calls share the same embedding vector. The implementer should extract the scores array from the first call and pass it to the second (add an optional `precomputed_scores` param to `check_duplicate`) to avoid double-scanning. If the DB is small (<1000 entries), two calls is acceptable.
- The 0.95 near-duplicate threshold is hardcoded (not configurable). The 0.90 merge threshold MUST continue reading from `cfg.get('memory_dedup_threshold', 0.90)` to preserve existing config override capability.
- The constitution write-protection check (`if category == "constitution": return rejection`) goes after the existing `VALID_CATEGORIES` check (which now includes 'constitution') but before content hash computation — approximately line 75 in current code.

### I3: record_influence_by_content MCP — New Tool

```python
async def record_influence_by_content(
    subagent_output_text: str,
    injected_entry_names: list[str],
    agent_role: str,
    feature_type_id: str | None = None,
    threshold: float = 0.70,
) -> str:
```

**Implementation:**
1. **Truncate input:** If `subagent_output_text` > 2000 chars, take the last 2000 chars (conclusion/summary is typically at the end of agent output). Gemini embedding-001 supports up to 2048 tokens; 2000 chars is a safe approximation.
2. **Chunk for granularity:** Split the (truncated) text into paragraphs (split on `\n\n`). Compute an embedding for each chunk via `provider.embed(chunk, task_type="query")`.
3. Look up stored embeddings for each name in `injected_entry_names` via `db.find_entry_by_name(name)`.
4. For each injected entry with a stored embedding: compute cosine similarity against **each chunk**. Take the **maximum** similarity across chunks (a single paragraph that matches an entry is sufficient evidence of influence).
5. For entries where max similarity >= threshold: call `db.record_influence(entry_id, agent_role, feature_type_id)`.
6. Return JSON: `{"matched": [{"name": "...", "similarity": 0.xx}], "skipped": N}`

**Why chunking:** A full document embedding averages across all topics, diluting any single entry's signal. Per-paragraph chunking preserves topic-specific signal: if one paragraph discusses the same concept as a memory entry, the chunk-level similarity will be high even if the overall document embedding is weak. This addresses the document-vs-paragraph granularity mismatch.

**Chunk filter:** Skip chunks shorter than 20 chars before computing embeddings (same threshold as store_memory min-length gate). This filters out headings, blank lines, and degenerate fragments.

**Cost note:** With ~5 injected entries and ~5 chunks per output, this is ~5 embedding calls per dispatch (chunks) + 0 (entries already have stored embeddings). At 14 dispatches per feature, that's ~70 embedding calls total — negligible cost.

**Graceful degradation:** If embedding provider unavailable, return `{"matched": [], "skipped": len(injected_entry_names), "warning": "embedding provider unavailable"}`

### I4: Command File Influence Tracking Template

Replace the existing influence tracking block (14 locations) with:

```markdown
**Post-dispatch influence tracking:**
If search_memory returned entries before this dispatch:
  call record_influence_by_content(
    subagent_output_text=<full agent output text>,
    injected_entry_names=<list of entry names from search_memory results>,
    agent_role="{role}",
    feature_type_id=<current feature type_id from .meta.json>,
    threshold=0.70)
  If record_influence_by_content fails: warn "Influence tracking failed: {error}", continue
  If .meta.json missing or type_id unresolvable: skip influence recording with warning
```

### I5: Phase Context reviewer_feedback_summary Format

Update the per-entry format in SKILL.md Step 1b:

```markdown
**{phase}** ({timestamp}): {outcome}
  Key decisions: {key_decisions}
  Artifacts: {comma-separated artifacts_produced}
  Reviewer feedback: {reviewer_feedback_summary}  ← NEW, only if non-null/non-empty
  Rework trigger: {rework_trigger}  ← only if non-null
```

## Technical Decisions

### TD-1: Two-threshold dedup strategy (0.95 reject + 0.90 merge)

**Decision:** The 0.95 near-duplicate gate runs before the 0.90 dedup merge. They are sequential checks on the same embedding, not alternatives.

**Rationale:** 0.95 catches near-identical content masquerading under different names (a quality problem). 0.90 catches genuine re-observations of the same concept (a dedup benefit). Separating them gives distinct error messages and preserves the merge behavior for legitimate reinforcement.

### TD-2: New MCP tool for influence tracking (not modifying record_influence)

**Decision:** Add `record_influence_by_content` as a new tool rather than modifying the existing `record_influence`.

**Rationale:** The existing tool is called from 14 locations in command markdown. Changing its signature to accept text blobs would break all callers simultaneously. A new tool lets us migrate callers incrementally and deprecate the old one later.

### TD-3: Embedding-based influence with configurable threshold

**Decision:** Default threshold 0.70, configurable per-call, with 0.80 as fallback if calibration isn't done.

**Rationale:** The 0.70 value is unvalidated (flagged in spec feasibility). Making it a parameter allows calibration without code changes. The conservative fallback (0.80) prevents false-positive influence inflation.

### TD-4: Session-start fallback alignment to 15 (not making bash read Python config)

**Decision:** Simply change the hardcoded `"20"` to `"15"` in session-start.sh rather than adding Python config reading from bash.

**Rationale:** The session-start.sh already reads from pd.local.md via `read_local_md_field`. The issue is just the fallback default mismatch. Aligning the two fallbacks to 15 is a one-line fix. Adding a Python subprocess call from bash to read config.py would add startup latency for no benefit.

### TD-5: Constitution as lowest-priority injection category

**Decision:** Add `"constitution"` at the end of `CATEGORY_ORDER`, after patterns.

**Rationale:** Constitution entries are foundational principles (KISS, YAGNI, etc.) that are broadly applicable but rarely the most relevant match for a specific task. Anti-patterns and heuristics should rank higher in injection order. Constitution entries still participate in relevance-filtered retrieval.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| 0.95 near-duplicate gate blocks legitimate similar entries | Low | Medium | Gate only fires when names differ. Same-name entries use the existing 0.90 merge path. Threshold can be tuned via config. |
| 0.70 influence threshold produces false positives | Medium | Low | Parameter is configurable per-call. Conservative fallback at 0.80. Influence weight is only 5% of prominence (reduced from 20%). |
| Embedding provider unavailable during store | Low | Low | All embedding-dependent gates degrade gracefully (skip check, log warning, proceed). Min-length gate always works. |
| Callers forget to pass source parameter | Low | Low | Default is "session-capture" (backward compatible). Only 2 callers need explicit values (retro→"retro", remember→"manual"). |
| Constitution entries pollute injection context | Low | Low | Constitution is last in CATEGORY_ORDER. Standard relevance filtering applies. Only surfaced when genuinely relevant to query. |

## Dependencies

### Files to Modify

| File | Component | Change |
|------|-----------|--------|
| `plugins/pd/mcp/memory_server.py` | C1, C2, C4 | Add source param (C1), Tier 1 gate (C2), new record_influence_by_content tool (C4) |
| `plugins/pd/hooks/lib/semantic_memory/ranking.py` | C3 | Update prominence weights |
| `plugins/pd/hooks/lib/semantic_memory/importer.py` | C5 | Add constitution to CATEGORIES |
| `plugins/pd/hooks/lib/semantic_memory/injector.py` | C5 | Add constitution to CATEGORY_ORDER/HEADERS |
| `plugins/pd/hooks/lib/semantic_memory/__init__.py` | C5 | Add constitution to VALID_CATEGORIES |
| `plugins/pd/hooks/session-start.sh` | C6 | Change fallback 20→15 |
| `plugins/pd/skills/workflow-transitions/SKILL.md` | C7 | Add reviewer_feedback_summary to injection template |
| `plugins/pd/commands/specify.md` | C8, I4 | Lower threshold to 1+, update influence tracking (2 locations) |
| `plugins/pd/commands/design.md` | C8, I4 | Lower threshold to 1+, update influence tracking (2 locations) |
| `plugins/pd/commands/create-plan.md` | C8, I4 | Lower threshold to 1+, update influence tracking (3 locations) |
| `plugins/pd/commands/implement.md` | C8, I4 | Lower threshold to 1+, update influence tracking (7 locations) |
| `plugins/pd/skills/retrospecting/SKILL.md` | C9 | Add source="retro" to store_memory call |
| `plugins/pd/commands/remember.md` | C9 | Add source="manual" to store_memory call |

### Files Read-Only (no changes)

| File | Reason |
|------|--------|
| `plugins/pd/hooks/lib/semantic_memory/database.py` | merge_duplicate, upsert_entry, record_influence all already support needed operations |
| `plugins/pd/hooks/lib/semantic_memory/dedup.py` | check_duplicate already accepts threshold parameter |
| `plugins/pd/hooks/lib/semantic_memory/embedding.py` | embed() already available for arbitrary text |
| `plugins/pd/hooks/lib/semantic_memory/config.py` | Default already 15, no change needed |

### Test Impact

| Test File | Changes Needed |
|-----------|---------------|
| `plugins/pd/mcp/test_memory_server.py` | New tests: source param passthrough, min-length rejection, near-duplicate rejection (0.95), constitution write rejection, record_influence_by_content with chunking |
| `plugins/pd/hooks/lib/semantic_memory/test_ranking.py` (or inline in test_database.py) | Updated weight assertions (0.30/0.15/0.35/0.15/0.05) |
| `plugins/pd/hooks/lib/semantic_memory/test_importer.py` (if exists) | Constitution category import test |
| `plugins/pd/hooks/lib/semantic_memory/test_injector.py` (if exists) | Constitution in CATEGORY_ORDER/HEADERS |
