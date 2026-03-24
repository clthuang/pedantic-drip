# Spec: Memory Phase 3 — Feedback Loop Closure

## Problem Statement

pd's semantic memory system has delivery (Phase 1), quality (Phase 2), and diagnostics (Features 059-060). Three PRD gaps remain unclosed:

1. **Gap 2c: First-pass notable catches** — Reviewer blocker issues that are fixed in one iteration are invisible to the memory system. Only multi-iteration patterns (2+ iterations) trigger learning capture.
2. **Gap 3a: Project-scoped filtering** — The `source_project` column exists on every memory entry but is never used in retrieval. All 770+ entries from 6 projects compete equally, drowning project-specific learnings.
3. **Gap 3d: Recall dampening** — `recall_count` feeds prominence via `min(recall_count/10, 1.0)` with no time decay, creating rich-get-richer dynamics where frequently-recalled entries permanently dominate.

## Scope

**In scope:**
- Notable catch capture: extend reviewer output schema and command file review-learning sections
- Project-scoped search: add `project` parameter to `search_memory` MCP tool and `RetrievalPipeline.retrieve()`
- Recall dampening: add time-weighted decay to recall frequency in `MemoryRanker._recall_frequency()`

**Out of scope:**
- Bidirectional knowledge bank sync (DB ↔ markdown)
- Entity registry project-scoped search
- UI for memory management
- Changes to the embedding pipeline

## Requirements

### FR-1: Notable Catch Capture

Extend the review learning capture sections in all 5 workflow command files (specify, design, create-plan, create-tasks, implement) to also capture single-iteration blocker catches.

**Current behavior:** Review learnings are only captured when the review loop runs 2+ iterations. Issues caught and fixed in iteration 1 are lost.

**New behavior:** After a review loop completes (even in 1 iteration), scan the reviewer output for issues with `severity: "blocker"`. If any blocker was found and resolved in a single iteration, store it as a memory entry with:
- `confidence: "medium"` (important enough to block but resolved quickly — sign of good specification)
- `category`: inferred from issue type (same logic as existing review learnings)
- `name`: derived from issue description (max 60 chars)
- `reasoning`: "Single-iteration blocker catch in feature {id} {phase} phase"

**Budget:** Max 2 notable catches per review cycle (on top of the existing max 3 recurring patterns).

**Affected files:** The 5 command files' "Capture Review Learnings" sections:
- `plugins/pd/commands/specify.md`
- `plugins/pd/commands/design.md`
- `plugins/pd/commands/create-plan.md`
- `plugins/pd/commands/create-tasks.md`
- `plugins/pd/commands/implement.md`

### FR-2: Project-Scoped Retrieval

Add a `project` parameter to the retrieval pipeline that implements two-tier blending:

1. Top `N/2` entries from `source_project = current_project` (project-specific)
2. Top `N/2` entries from all projects (universal)
3. Deduplicate by entry ID, interleave by final_score

**Implementation locations:**
- `RetrievalPipeline.retrieve()` in `plugins/pd/hooks/lib/semantic_memory/retrieval.py` — add `project: str | None = None` parameter
- `search_memory` MCP tool in `plugins/pd/mcp/memory_server.py` — add `project` parameter, pass through to pipeline
- `MemoryRanker.rank()` in `plugins/pd/hooks/lib/semantic_memory/ranking.py` — no changes (ranking is score-based, not project-aware; project filtering happens at retrieval level)
- Session-start injector in `plugins/pd/hooks/lib/semantic_memory/injector.py` — pass current project name from `source_project` config or git remote

**When `project` is None:** Existing behavior (no project filtering).
**When `project` is set:** Two-tier blend as described above.

**Project name resolution:** Use the basename of the git remote URL origin, or fall back to the directory name of `project_root`. This matches the `source_project` value already stored on entries by `store_memory`.

### FR-3: Recall Dampening with Time Decay

Modify `MemoryRanker._recall_frequency()` to incorporate time decay:

**Current formula:**
```python
def _recall_frequency(self, recall_count: int) -> float:
    return min(recall_count / 10.0, 1.0)
```

**New formula:**
```python
def _recall_frequency(self, recall_count: int, last_recalled_at: str | None, now: datetime) -> float:
    base = min(recall_count / 10.0, 1.0)
    if last_recalled_at is None:
        return base * 0.5  # never recalled — half credit
    recalled = datetime.fromisoformat(last_recalled_at)
    days_since_recall = max((now - recalled).total_seconds() / 86400.0, 0.0)
    decay = 1.0 / (1.0 + days_since_recall / 14.0)  # 14-day half-life
    return base * decay
```

This means entries recalled recently get full credit, but entries not recalled in 14+ days see their recall advantage halved, allowing newer entries to compete.

**Schema change:** Add `last_recalled_at TEXT` column to the `entries` table. Updated when `recall_count` is incremented (during injection). Default NULL for existing entries.

**Migration:** Add migration 5 to `MemoryDatabase._migrate()` that adds the column with `ALTER TABLE entries ADD COLUMN last_recalled_at TEXT`.

## Non-Requirements

- **NR-1:** Changes to the existing `_recency_decay()` function — already works correctly
- **NR-2:** Changes to influence tracking — already implemented in Phase 2
- **NR-3:** Changes to keyword extraction — already implemented in Phase 2
- **NR-4:** UI or dashboard for memory analytics

## Acceptance Criteria

### AC-1: Notable catch stored on single-iteration blocker
Given a review loop where a blocker is found and fixed in iteration 1, when the review completes, then a memory entry is stored with `confidence="medium"` and reasoning mentioning "single-iteration blocker catch".

### AC-2: Notable catch budget enforced
Given a review loop with 5 single-iteration blockers, when review learnings are captured, then at most 2 notable catches are stored.

### AC-3: Project-scoped search returns blended results
Given `search_memory(query="test", project="pedantic-drip")`, when results are returned, then approximately half come from `source_project="pedantic-drip"` and half from all projects, deduplicated by entry ID.

### AC-4: Project=None preserves existing behavior
Given `search_memory(query="test")` without project parameter, when results are returned, then behavior is identical to pre-feature behavior (no project filtering).

### AC-5: Injector passes project to retrieval
Given a session start, when the injector runs, then it passes the current project name to the retrieval pipeline's `project` parameter.

### AC-6: Recall dampening reduces stale entry scores
Given an entry with `recall_count=10` but `last_recalled_at` 30 days ago, when ranked, then its recall frequency score is significantly lower than an entry with `recall_count=10` recalled today.

### AC-7: New entries compete with stale recalled entries
Given a new entry (recall_count=0) and an old frequently-recalled entry (recall_count=10, last_recalled_at 60 days ago), when ranked with similar vector/keyword scores, then the new entry's prominence is competitive (not dominated by the stale entry's recall count).

### AC-8: Schema migration adds last_recalled_at
Given an existing memory DB with schema_version=4, when MemoryDatabase is constructed, then `last_recalled_at` column exists and schema_version is 5.

### AC-9: last_recalled_at updated on injection
Given an entry injected into a session, when `recall_count` is incremented, then `last_recalled_at` is set to the current timestamp.

## Dependencies

- Feature 055 (memory feedback loop Phase 1) — subagent delivery, dead code removal
- Feature 057 (memory Phase 2) — keywords, dedup, influence tracking
- `semantic_memory.ranking.MemoryRanker` — recall frequency modification
- `semantic_memory.retrieval.RetrievalPipeline` — project filtering
- `semantic_memory.database.MemoryDatabase` — schema migration

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Project name resolution inconsistency (git remote vs stored source_project) | Medium | Medium | Use same resolution logic as store_memory |
| Two-tier blend returns fewer results than limit when project has few entries | Medium | Low | If project tier has < N/2 entries, fill remainder from universal tier |
| Schema migration 5 breaks existing doctor Check 5 (expects schema_version=4) | High | Medium | Update doctor Check 5 to accept schema_version >= 4 |
| Notable catch capture increases memory noise | Low | Low | Budget cap of 2 per cycle + medium confidence (not low) |

## Traceability

This spec implements PRD gaps 2c, 3a, 3d from the Memory Feedback Loop PRD (`docs/brainstorms/20260324-100000-memory-feedback-loop-completion.prd.md`). Completes the 3-phase plan outlined in the PRD's "Phasing Recommendation" section.
