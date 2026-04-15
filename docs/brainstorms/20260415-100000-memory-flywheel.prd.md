# PRD: Memory Flywheel — Close the Self-Improvement Loop

*Source: Backlog #00053*

## Status
- Created: 2026-04-15
- Last updated: 2026-04-15
- Status: Draft
- Problem Type: Multi-Feature Project
- Archetype: improving-an-existing-system

## Problem Statement

The pd plugin's memory system is a well-architected **write-and-recall-once log**, not a self-improving flywheel. A 4-agent investigation on 2026-04-15 (`/pd:subagent-ras`) found that capture and recall loops work, but the apply, measure, curate, and promote loops are broken or missing. Five concrete leverage items account for the gap.

### Evidence (from 2026-04-15 investigation, conversation summary)

- **Apply loop broken:** `record_influence_by_content` MCP exists and is *documented* in `implement.md`, `create-plan.md`, `researching/SKILL.md` but **never actually called** by any orchestrator. `_influence_score()` exists in `ranking.py` but `rank()` doesn't invoke it. **935 of 943 entries (99.1%) have `influence_count=0`** — Evidence: SQLite query against `~/.claude/pd/memory/memory.db`.
- **Hybrid retrieval is vector-only:** DB shows `vector=964, fts5=0`. The FTS5 virtual table exists but is never populated, so the keyword-search leg returns empty and full ranking weight collapses onto vectors — Evidence: SessionStart memory injection diagnostic line shows `(vector=964, fts5=0)` confirmed at session start 2026-04-15.
- **Recall tracking decoupled from retrieval:** `recall_count` increments only on dedup-merge in `writer.py`, not on actual retrieval in `retrieval.py`. Confidence is one-way sticky at `low` with no upgrade path — Evidence: `plugins/pd/hooks/lib/semantic_memory/database.py` schema, `retrieval.py` line ~207 (vector search has no count update).
- **Push-only at session start:** Memory injection happens once in `session-start.sh` and never refreshes mid-session even when feature/phase context changes substantially — Evidence: `plugins/pd/hooks/session-start.sh` build_*_context functions emit once, no PostToolUse/PreToolUse refresh hooks exist for memory.
- **No promotion path:** High-confidence patterns (3+ observations) accumulate in `docs/knowledge-bank/` markdown forever; nothing converts them into enforceable rules (skill content, hook scripts, CLAUDE.md entries) — Evidence: knowledge-bank file inventory + grep across skills/ for KB references shows 0 cross-links.

## Goals

1. **Activate the apply loop** — make influence tracking real, not just declarative.
2. **Restore hybrid retrieval** — populate FTS5 so keyword search contributes to ranking.
3. **Make confidence dynamic** — recall counting + decay + promotion path so signal quality evolves.
4. **Move from push to pull** — refresh memory mid-session at meaningful boundaries.
5. **Close the codification loop** — high-confidence patterns become enforceable rules.

## Success Criteria

- [ ] **Influence:** within 5 review cycles after merge, ≥30% of memory entries surfaced via `search_memory` carry `influence_count ≥ 1` (currently 0.9%). `_influence_score()` is part of `rank()`'s active calculation, not dead code.
- [ ] **FTS5:** `vector` and `fts5` row counts match (within 1) post-backfill; FTS5 keyword search returns non-empty for queries against indexed entries; ranking correctly blends vector + BM25 scores.
- [ ] **Recall:** `recall_count` increments on every `search_memory` call (not just dedup); decay function reduces confidence over time without observation; promotion path raises confidence on accumulated observation+influence signal.
- [ ] **Mid-session refresh:** memory re-queries on phase boundaries (e.g., post-`complete_phase`) without requiring SessionStart restart; refreshed entries surface in subsequent agent dispatches.
- [ ] **Promotion:** `/pd:promote-pattern` command exists and successfully converts at least 1 high-confidence pattern from knowledge-bank into a deployed rule (skill addition, hook, or CLAUDE.md entry) during a manual test.

## User Stories

### Story 1: Influence telemetry
**As a** pd user **I want** the system to track which memory entries actually influenced agent outputs **so that** ranking surfaces high-impact entries and dead weight gets demoted naturally over time.
- AC: After running 5 features post-merge, influence_count > 0 for ≥30% of recently-recalled entries.
- AC: `record_influence_by_content` is invoked by implementer/reviewer Task return-handlers in `implement.md`, `create-plan.md`, `design.md`.
- AC: `rank()` in `ranking.py` includes `_influence_score()` in its weighted sum (visible in unit tests).

### Story 2: Keyword search comes back
**As a** pd user **I want** memory retrieval to use both semantic similarity and keyword matching **so that** queries with rare technical terms (like file names, error codes, MCP tool names) find relevant entries that vector search misses.
- AC: After backfill, `sqlite3 ... "SELECT COUNT(*) FROM entries_fts"` returns within 1 of `entries` row count.
- AC: Insert/update triggers keep FTS5 in sync going forward (no future drift).
- AC: BM25 keyword score component is visible in `rank()` weighted output.

### Story 3: Self-curating confidence
**As a** pd user **I want** confidence levels that evolve with usage **so that** entries earn `medium`/`high` confidence by being repeatedly observed and influencing real work, not just by initial agent classification.
- AC: `recall_count` increments on every `search_memory` call.
- AC: Confidence decay function (e.g., `confidence *= 0.8^(days_since_updated/90)`) runs daily or on retrieval.
- AC: Promotion function raises `low → medium → high` based on `observation_count × influence_count` threshold.

### Story 4: Memory that knows where I am
**As a** pd user **I want** memory injection to refresh when my work context changes substantially **so that** mid-session phase transitions surface phase-relevant memory without restarting.
- AC: Refresh hook fires on `complete_phase` (or equivalent boundary); refreshed entries appear in subsequent dispatches.
- AC: Refresh adds bounded token cost (≤500 additional tokens per refresh).
- AC: Existing SessionStart injection still works as the initial baseline.

### Story 5: Patterns become rules
**As a** pd user **I want** high-confidence patterns from my knowledge bank to become enforceable rules **so that** repeated learnings codify into the system instead of rotting as markdown.
- AC: `/pd:promote-pattern` command exists and accepts a pattern ID or name.
- AC: Command produces a diff (skill content, hook script, or CLAUDE.md entry) for user review before applying.
- AC: At least 1 high-confidence pattern gets promoted in a manual end-to-end test.

## Use Cases

### UC-1: Implementer dispatch records influence
**Actors:** implementer agent, orchestrating skill | **Preconditions:** `search_memory` was called pre-dispatch with results passed in prompt
**Flow:** 1. Implementer agent returns output 2. Orchestrating skill calls `record_influence_by_content(output, injected_entry_names, agent_role, feature_type_id)` 3. Embedding similarity threshold (0.70) determines which entries actually influenced output 4. Influence_count incremented in DB
**Postconditions:** Future `rank()` calls weight high-influence entries higher
**Edge cases:** Empty output, MCP unavailable (skip with warning), no entries surfaced pre-dispatch (skip)

### UC-2: FTS5 trigger sync
**Actors:** writer.py, semantic_memory module | **Preconditions:** new memory entry being upserted
**Flow:** 1. `upsert_entry()` writes to `entries` table 2. INSERT/UPDATE trigger fires on FTS5 virtual table 3. `entries_fts` row created/updated to mirror searchable text fields
**Postconditions:** FTS5 search returns this entry for matching keyword queries
**Edge cases:** Migration backfills 943 existing entries without trigger; partial migration recoverable; FTS5 unavailable on this SQLite build (graceful fallback to vector-only)

### UC-3: Pattern promotion
**Actors:** pd user, /pd:promote-pattern skill | **Preconditions:** a knowledge-bank pattern has observation_count ≥ 3 AND confidence = high
**Flow:** 1. User invokes `/pd:promote-pattern <name>` 2. Skill reads pattern + classifies target (skill rule / hook / CLAUDE.md entry) 3. Skill produces diff and asks user to approve 4. On approval, applies diff and updates pattern with `promoted: true` field 5. Future retros track promotion outcomes
**Postconditions:** Pattern is now an enforceable rule, not just docs
**Edge cases:** Pattern doesn't fit any target template (manual override); diff conflicts with existing skill content (3-way merge prompt)

## Edge Cases & Error Handling

| Scenario | Expected Behavior | Rationale |
|---|---|---|
| `record_influence_by_content` MCP fails | Log warning, continue | Don't block agent dispatch on telemetry failures |
| FTS5 backfill mid-flight crash | Resumable; partial state OK | Backfill is idempotent per-row |
| Confidence decay produces confidence < 0 | Floor at "low" | No "negative" confidence concept |
| Mid-session refresh exceeds token budget | Skip refresh, log warning | Don't blow context budget for memory |
| Promote-pattern target file doesn't exist | Create with header + entry | Avoid silent skip |
| `entries_fts` unavailable on this SQLite build | Skip FTS5 entirely; document fallback | Graceful degradation |

## Out of Scope

- Cross-project ranking filter (the `source_project` filter gap is captured separately as a follow-up; out of scope for the 5 main features unless trivially adjacent)
- Silent fallback fixes in `remember` CLI and `capture-tool-failure` (separate hardening pass)
- Implementer self-capture of validated design decisions (separate feature)
- Embedding model migration (out of scope; current `gemini-embedding-001` stays)

## Decomposition Hints

The 5 leverage items are natural feature boundaries:
1. **Influence wiring** — small, high-impact, single-session feature.
2. **FTS5 backfill + triggers** — small data migration + schema fix.
3. **Recall tracking + confidence decay + promotion** — medium, touches retrieval + writer + a daily/triggered job.
4. **Mid-session refresh hook** — small, one new hook.
5. **Promote-pattern command** — medium, new skill + command + classification heuristics.

Suggested feature dependency order:
- 1 (influence) and 2 (FTS5) are independent and can ship in parallel.
- 3 (recall/decay/promotion) depends on 1 (influence_count is the upgrade signal).
- 4 (refresh) is independent.
- 5 (promote-pattern) depends on 3 (needs confidence-elevation signal to know what to promote).
