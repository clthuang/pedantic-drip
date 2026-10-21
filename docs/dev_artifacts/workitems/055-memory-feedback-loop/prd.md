# PRD: Memory System Feedback Loop Completion

## Problem Statement

pd's semantic memory system (Feature 024) has a sophisticated hybrid retrieval pipeline (vector + FTS5 + prominence) but suffers from a fundamentally broken feedback loop. Three adversarial reviews conducted on 2026-03-24 independently identified the same core failure: **the system records learnings but doesn't close the loop to influence agent behavior**.

### Evidence Summary

- **End-to-end signal survival: 5-15%** — most learnable moments either aren't captured or don't reach the agents that need them.
- **Subagent gap (Critical):** Implementer, reviewers, and test-deepener agents never see injected memories. The retrieval pipeline terminates at the orchestrator, which doesn't forward memories to dispatched subagents.
- **High selection ratio:** This repo overrides `memory_injection_limit` to 50 (default is 20), selecting 50/749 = 6.7% of entries. While not the 67% initially claimed, the real problem is that in degraded mode (no context signals), all 749 entries score equally on vector+FTS5 and prominence-only ranking selects the most generic entries. Even at 20 entries, the ranking barely discriminates when context is absent.
- **No influence measurement:** `recall_count` tracks "was injected" not "was useful." The system cannot distinguish actionable entries from noise.
- **Keyword system dead:** 444+ lines of code producing zero output (TieredKeywordGenerator always returns `[]`).
- **One filter per search:** Both `search_memory` (category only) and `search_entities` (entity_type only) lack project scoping, status filtering, and confidence filtering.

### Current Architecture Strengths (Preserve)

- Hybrid retrieval pipeline (vector cosine + FTS5 BM25 + prominence) — genuinely good engineering.
- Context-aware injection via `collect_context()` — session signals drive relevance.
- Content-hash deduplication with observation_count increment — prevents duplicates cleanly.
- Category-balanced selection — ensures diversity across anti-patterns/patterns/heuristics.
- Cross-project global DB — enables knowledge transfer between projects.
- Multiple capture paths (review learnings, /remember, capturing-learnings, retro).

## Goals

### G1: Close the Subagent Delivery Gap
Every dispatched subagent (implementer, reviewers, test-deepener) receives task-relevant memories in its dispatch prompt, not just the generic session injection.

### G2: Improve Ingestion Quality
Reduce near-duplicate accumulation, add semantic deduplication at capture time, and implement confidence auto-promotion based on validation.

### G3: Improve Retrieval Precision
Add project-scoped filtering, reduce injection volume to increase signal density, and fix the dead keyword weight.

### G4: Add Influence Measurement
Track whether injected memories are referenced in agent output, enabling data-driven ranking improvements.

### G5: Simplify — Remove Dead Code
Delete the keyword stub system (444+ lines) and unused embedding providers (3 of 4), reducing maintenance burden.

## Non-Goals

- Replacing the memory system with a simpler alternative (CLAUDE.md-only approach). The cross-project and auto-capture value justifies the system's existence.
- Adding a UI for memory management. CLI and MCP tools are sufficient.
- Changing the entity registry architecture. Entity filtering improvements are a separate concern (captured as related work).
- Real-time memory streaming to subagents via MCP. The simpler approach (orchestrator queries and injects) is sufficient.

## Detailed Gap Analysis

### Gap 1: Subagent Delivery (Signal Attenuation: ~50%)

**Current state:** Session-start injection produces a markdown block in the orchestrator's context. Subagents are dispatched via Task tool with custom prompts containing spec/design/plan context but zero memory entries. Confirmed by grep across all 5 command files and all agent definitions.

**Data path (broken):**
```
memory.db → injector → session context → orchestrator reads → [BREAK] → subagent never sees it
```

**Proposed fix — Task-scoped memory query:**

Before each subagent dispatch, the orchestrator calls `search_memory` with task-specific context and includes top 3-5 results in the dispatch prompt:

```
## Relevant Engineering Memory
{search_memory results for: task description + files being touched}
```

**Implementation mechanism:** Command files are markdown prompt templates interpreted by Claude. The orchestrator (Claude) must be instructed to call `search_memory` MCP tool before building each dispatch prompt. This is a prompt instruction, not executable code:

```markdown
Before dispatching, call search_memory with query derived from the task description
and file list. Include top 3-5 results as "## Relevant Engineering Memory" in the
dispatch prompt.
```

**Reliability note:** Prompt-instructed MCP calls are not deterministic — the orchestrator may skip them under context pressure. Phase 1 should include minimal injection logging (entry IDs included in dispatch) to verify the mechanism works before investing in influence tracking.

**Where to implement:** The 5 workflow command files that dispatch subagents:
- `commands/specify.md` — spec-reviewer, phase-reviewer dispatches
- `commands/design.md` — design-reviewer, phase-reviewer dispatches
- `commands/create-plan.md` — plan-reviewer, phase-reviewer dispatches
- `commands/create-tasks.md` — task-reviewer, phase-reviewer dispatches
- `commands/implement.md` — implementer, code-simplifier, test-deepener, implementation-reviewer, code-quality-reviewer, security-reviewer dispatches

**Token economics:** 3-5 entries × ~70 tokens = 210-350 tokens per dispatch, vs. ~3,700 tokens broadcast at session start. Net improvement: more relevant, less total tokens.

**Interaction with session injection:** Session injection continues for the orchestrator. Subagent injection is additive and task-scoped. No duplication risk because subagents don't see session injection.

### Gap 2: Ingestion Quality (Signal Attenuation: ~30%)

**Current state:** All captures via `store_memory` accept arbitrary text with no quality gate. Near-duplicate descriptions (different wording, same learning) create separate entries. Confidence is always "low" for non-retro captures and never promotes.

**Sub-gap 2a: Semantic deduplication at capture time**

Before storing a new entry, compute cosine similarity against existing entries. If similarity > 0.85, merge (increment observation_count on the existing entry) rather than creating a new entry. This prevents the long tail of near-duplicates that dilute retrieval quality.

Implementation: In `memory_server.py:_process_store_memory()`, after computing the embedding, run a similarity check against the top-5 existing entries. If a near-match is found, upsert to the existing entry instead of creating a new one.

**Sub-gap 2b: Confidence auto-promotion**

Current: the MCP tool defaults to `confidence="medium"`, but all workflow command files (specify, design, create-plan, create-tasks, implement) explicitly pass `confidence="low"` for review learnings captures. In practice, non-retro session-captures are low confidence.

Proposed promotion rules:
- `low` → `medium`: observation_count >= 3 (seen across multiple captures)
- `medium` → `high`: observation_count >= 5 AND validated during retrospective

Implementation: In `database.py:upsert_entry()`, after incrementing observation_count, check thresholds and auto-promote. The retro-facilitator already validates pre-existing entries (CONFIRMED/CONTRADICTED) — wire the CONFIRMED signal to promote confidence.

**Sub-gap 2c: First-pass notable catches**

Current: review learnings only capture when iterations >= 2. Single-pass catches of real issues are invisible.

Proposed: Add a `notable_catch` field to reviewer output schema. When a reviewer flags a blocker-severity issue that is fixed in one iteration, store it with `confidence="medium"` (it was important enough to block but was resolved quickly — that's a sign of good specification, not unimportance).

### Gap 3: Retrieval & Ranking Precision (Signal Attenuation: ~20%)

**Sub-gap 3a: Project-scoped filtering**

The `source_project` column exists on every memory entry (6 distinct projects in the DB) but is never used in retrieval. The entity registry has no project filter at all.

Proposed: Add `project` parameter to `search_memory` and `RetrievalPipeline.retrieve()`. When set, apply a two-tier blend:
1. Top N/2 entries from `source_project = current_project` (project-specific)
2. Top N/2 entries from all projects (generic/universal)
3. Deduplicate and interleave by score

This ensures project-specific learnings aren't drowned out by generic ones, while still surfacing universal patterns.

**Sub-gap 3b: Reduce injection volume**

Current: 50 entries injected regardless of relevance (67% of corpus). This is a newspaper, not a search result.

Proposed: Add a minimum relevance threshold — only inject entries with `final_score > 0.3`. If fewer than 5 entries meet the threshold, inject those and stop. Skip injection entirely when context signals are absent (no active feature, no branch, no changed files) — prominence-only ranking is not worth the token cost. Reduce `memory_injection_limit` default from 20 to 15 (this repo's override of 50 should also be reduced to 20-25).

**Sub-gap 3c: Fix keyword weight allocation**

Current: 0.2 weight allocated to BM25 keyword matching, but keywords are always empty. FTS5 still operates on name/description/reasoning, so the weight isn't fully wasted — but it's allocated to a column that contributes nothing.

Proposed (chosen): Implement LLM-based keyword generation using the existing `KEYWORD_PROMPT` template (already defined and tested in `keywords.py`). The coding agent (implementer) fills in the `TieredKeywordGenerator` with a real provider that calls the configured embedding API's chat/completion endpoint (Gemini) to extract 3-10 keywords per entry. Keywords are generated at `store_memory` time (async, non-blocking — store succeeds immediately, keywords backfilled).

For existing entries without keywords (749 entries with `keywords=[]`), run a one-time backfill batch via the writer CLI. Use the API as a feedback signal: if keyword generation fails or produces low-quality output, fall through to `SkipKeywordGenerator` (existing pattern). The `KEYWORD_PROMPT` template, validation rules (regex, stopwords, 3-10 bounds), and tier fallback loop are already scaffolded — the gap is only the API call implementation.

Rejected alternative: Regex-based extraction. While zero-latency, regex cannot capture semantic keywords (e.g., "schema migration" from a description about "changing database tables"). LLM extraction produces higher-quality keywords that meaningfully improve BM25 precision.

**Sub-gap 3d: Recall dampening**

Current: `recall_count` feeds prominence and creates rich-get-richer dynamics. Ceiling at 10 bounds the effect but doesn't prevent early lock-in.

Proposed: Apply time decay to recall_count contribution: `recall_frequency = min(recall_count / 10.0, 1.0) * recency_factor`. This means entries that haven't been recalled recently lose their recall advantage, allowing new entries to compete.

### Gap 4: Influence Measurement (Signal Attenuation: ~100%)

**Current state:** Zero measurement of whether injected memories change behavior. The loop is open at the consumption stage.

**Proposed — Lightweight influence tracking:**

After each subagent completes, scan its output for references to injected memory entries (string overlap with entry names/descriptions). Record matches in a new `influence_log` table:

```sql
CREATE TABLE influence_log (
    entry_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    agent_role TEXT NOT NULL,  -- e.g., "implementer", "security-reviewer"
    feature_type_id TEXT,
    timestamp TEXT NOT NULL
);
```

Update a new `influence_count` field on the entry. Use this in prominence ranking alongside (or replacing) `recall_count`. This closes the loop: entries that actually influence behavior get boosted; entries that are injected but ignored get dampened.

**Implementation complexity:** Medium. The string overlap analysis runs in the orchestrator after each subagent returns. False positives (coincidental term matches) are a concern — mitigate by requiring match on entry `name` (shorter, more specific) rather than full `description`.

### Gap 5: Dead Code Removal

**Keyword system (444+ lines):**
- `keywords.py`: 149 lines
- `test_keywords.py`: 245 lines (estimated)
- DB triggers, writer merge logic, config keys: ~50 lines
- KEYWORD_PROMPT constant: never called

**Unused embedding providers (~850 lines):**
- `OpenAIProvider`, `OllamaProvider`, `VoyageProvider` in `embedding.py`: ~350 lines
- Tests for unused providers: ~500 lines

**Proposed:** Delete keyword system entirely (or replace with lightweight regex extraction per Gap 3c). Delete 3 unused embedding providers. Retain Gemini only. Re-add from git history if ever needed.

**Risk:** None. All code is in git history. No external consumers.

## Success Criteria

| ID | Criterion | Measurement |
|----|-----------|-------------|
| SC-1 | Subagents receive task-relevant memories | Every reviewer/implementer dispatch prompt contains `## Relevant Engineering Memory` section |
| SC-2 | Injection volume reduced to 15-20 entries | `memory_injection_limit` default changed; `.last-injection.json` shows lower counts |
| SC-3 | Near-duplicate entries merged at capture | `store_memory` with cosine > 0.85 existing match increments observation_count |
| SC-4 | Confidence auto-promotes | Entries with observation_count >= 3 have confidence="medium" |
| SC-5 | Project-scoped search available | `search_memory(query, project="pedantic-drip")` returns filtered results |
| SC-6 | Influence tracking operational | `influence_log` table populated after subagent dispatches |
| SC-7 | Dead code removed | `grep -c "SkipKeywordGenerator\|OllamaProvider\|VoyageProvider" plugins/pd/` returns 0 |

## Phasing Recommendation

### Phase 1: Delivery & Simplification (Highest ROI)
- Gap 1 (subagent delivery) — close the broadcast problem
- Gap 5 (dead code removal) — simplify before adding
- Gap 3b (reduce injection volume) — config change + threshold

### Phase 2: Ingestion & Retrieval Quality
- Gap 2a (semantic deduplication)
- Gap 2b (confidence auto-promotion)
- Gap 3a (project-scoped filtering)
- Gap 3c (keyword weight fix)

### Phase 3: Feedback Loop Closure
- Gap 4 (influence measurement)
- Gap 2c (first-pass notable catches)
- Gap 3d (recall dampening)

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Prompt-instructed MCP calls unreliable — orchestrator skips search_memory before dispatch | Medium | High (Gap 1 doesn't work) | Add injection logging in Phase 1 to detect skips; consider hook-based fallback if skip rate > 20% |
| Semantic dedup threshold too aggressive — merges distinct-but-related entries at cosine > 0.85 | Medium | Medium (knowledge loss) | Start with 0.90 threshold, tune based on false-merge rate. Log merges for manual review. |
| Influence tracking false positives — common terms in entry names match coincidentally | High | Low (corrupts ranking signal slowly) | Use entry ID tags (e.g., `[MEM-abc123]`) injected alongside entries instead of string overlap. Defer to Phase 3. |
| LLM keyword generation latency on store_memory hot path | Medium | Medium (adds 1-2s per capture) | Generate keywords async — store succeeds immediately, keywords backfilled. Existing SkipKeywordGenerator fallback on API failure. |
| LLM keyword quality inconsistency | Low | Low (FTS5 still works on raw text) | KEYWORD_PROMPT template already defines output format with validation. Backfill batch allows quality review before committing. |
| Confidence auto-promotion triggers on observation_count inflated by dedup merges | Medium | Medium (premature high-confidence) | Only count observations from distinct sessions/features, not from semantic merges |

## Related Work (Not In Scope)

- Entity registry project-scoped search (add `project_type_id` filter to `search_entities`)
- Entity registry status filter (add `status` parameter to `search_entities`)
- Embedding migration safety in injector (add provider check from writer.py)
- Bidirectional knowledge bank sync (DB → markdown)

## References

- Feature 024: semantic memory search (original implementation)
- Adversarial architecture review (2026-03-24, this conversation)
- Adversarial token economics review (2026-03-24, this conversation)
- Adversarial feedback loop review (2026-03-24, this conversation)
- RCA: FTS5 entities_fts metadata_text mismatch (docs/rca/20260323-fts-metadata-text-mismatch.md)
