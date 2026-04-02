# Specification: Memory Feedback Loop Hardening

**Origin:** Gap analysis of pd memory system (2026-04-03). Ten gaps identified across write paths, read paths, ranking signals, quality control, and feedback capture.

## Problem Statement

pd's memory system has the right architecture (hybrid retrieval, multi-factor ranking, structured write paths) but multiple broken or dormant feedback loops prevent it from being a self-improving system. The `source` field is hardcoded, influence tracking is nearly dormant (20% ranking weight on a near-zero signal), memory writes have no quality gate, single-iteration reviewer blockers are never captured, and several data channels are orphaned (constitution.md, reviewer_feedback_summary, research summaries).

## Scope

### In Scope (Priority 1-7 from gap analysis)
1. Fix `source` hardcoding in `store_memory` MCP — add `source` parameter
2. Fix influence tracking — reweight ranking formula, replace verbatim name matching with embedding similarity
3. Add Tier 1 automated review gate to `store_memory` — reject low-quality entries at write time
4. Lower review learnings threshold from 2+ to 1+ iterations — capture single-pass blockers
5. Add `constitution.md` to `MarkdownImporter.CATEGORIES`
6. Align `memory_injection_limit` default (config.py vs session-start.sh)
7. Surface `reviewer_feedback_summary` in Phase Context injection

### Out of Scope (deferred)
- Tier 1c contradiction detection via LLM comparison (Gap 9 Tier 1c) — deferred; requires LLM call within MCP tool which has latency and cost implications
- Tier 2 agent review gate for retro learnings (requires separate feature for LLM-in-the-loop write validation)
- Tier 3 periodic KB audit (requires metrics infrastructure)
- Gap 8 event-driven learning hooks (PostToolUse denial detection, AskUserQuestion correction capture, rejection_log) — partially addressed by lowering review learnings threshold (in-scope item #4); remaining items deferred to backlog
- Metrics infrastructure for measuring self-improvement (backlog #00052)
- Cross-feature `backward_history` analysis (backlog #00053)
- RAS → memory pipeline (backlog #00054)
- Write-time conflict resolution (Mem0 ADD/UPDATE/DELETE/NOOP pattern)
- Importance-gated decay + auto-prune (FadeMem)
- Tiered TTL for memory entries

## Success Criteria
- [ ] `store_memory` MCP accepts a `source` parameter and passes it to the DB writer
- [ ] All callers of `store_memory` pass their actual source (retro→'retro', remember→'manual', RCA→'session-capture', review learnings→'session-capture')
- [ ] Influence ranking weight reduced from 0.20 to 0.05; redistributed to observation (0.30) and recency (0.35)
- [ ] Post-dispatch influence tracking uses embedding cosine similarity (threshold 0.70) instead of verbatim name match
- [ ] `store_memory` rejects entries with description < 20 chars (returns error, does not store)
- [ ] `store_memory` rejects entries with cosine similarity > 0.95 to an existing entry of different name (stricter than 0.90 dedup merge)
- [ ] Review learnings capture (Step 7f in all 4 command files) triggers on 1+ iterations, not just 2+
- [ ] `constitution.md` entries appear in `search_memory` results and session injection
- [ ] `memory_injection_limit` has a single source of truth (config.py default, session-start.sh reads it)
- [ ] `reviewer_feedback_summary` appears in Phase Context injection block during backward travel

## Acceptance Criteria

### AC-1: store_memory source parameter
- Given `store_memory` is called with `source="retro"`
- When the entry is stored in the DB
- Then the `source` column contains `"retro"` (not `"session-capture"`)
- And calling without `source` defaults to `"session-capture"` (backward compatible)

### AC-2: Caller source propagation
- Given the retrospecting skill calls `store_memory` in Step 3a
- When it passes `source="retro"`
- Then the stored entry has `source="retro"` in the DB
- And `/pd:remember` calls with `source="manual"`
- And review learnings (Step 7f) calls with `source="session-capture"`
- And RCA calls with `source="session-capture"`
- And wrap-up calls with `source="session-capture"` (default)
- And capturing-learnings calls with `source="session-capture"` (default)

### AC-3: Influence weight rebalanced
- Given the prominence formula in `ranking.py`
- When ranking entries
- Then influence weight is 0.05 (was 0.20)
- And observation weight is 0.30 (was 0.25)
- And recency weight is 0.35 (was 0.25)
- And confidence (0.15) and recall (0.15) are unchanged

### AC-4: Embedding-based influence attribution
- Given a subagent output that paraphrases but does not name a memory entry verbatim
- When post-dispatch influence tracking runs
- Then the orchestrator calls a new MCP tool `record_influence_by_content(subagent_output_text, injected_entry_names, threshold=0.70)` on the memory-server
- And the MCP tool computes an embedding of the subagent output, retrieves stored embeddings for the injected entries, computes cosine similarity, and records influence for entries with similarity >= threshold
- And entries matched by embedding have their `influence_count` incremented
- Note: The 0.70 threshold needs calibration — see Feasibility Assessment. If calibration shows 0.70 is too noisy, increase to 0.80.
- Note: When embedding provider is unavailable, skip embedding-based influence attribution and log a warning. Do not fall back to name matching (the old behavior is being replaced, not kept as fallback).
- **Affected locations (14 total):** All post-dispatch influence tracking blocks across 4 command files: specify.md (2), design.md (2), create-plan.md (3), implement.md (7 — test-deepener A/B, implementation-reviewer, relevance-verifier, code-quality-reviewer, security-reviewer, implementer)

### AC-5: Minimum description length gate
- Given `store_memory` is called with `description="too short"`
- When the description is < 20 characters
- Then the entry is rejected with error message "Entry rejected: description too short (min 20 chars)"
- And no entry is stored in the DB

### AC-6: Near-duplicate rejection gate
- Given an existing entry "Always use ValueError for validation" in the DB
- When `store_memory` is called with description "Use ValueError for input validation" (cosine > 0.95 to existing)
- And the new entry has a different `name` from the existing entry
- Then the entry is rejected with error "Entry rejected: near-duplicate of existing entry '{name}'"
- And no new entry is stored (the existing entry is not merged)
- Note: If the new entry has the same `name` as the existing entry, the existing dedup-merge logic (cosine > 0.90) still applies — this gate only blocks entries that are near-identical in content but different in name
- Note: When embedding provider is unavailable, skip the near-duplicate cosine check (allow the entry through). Log a warning: "Near-duplicate check skipped: embedding provider unavailable." This matches the existing graceful degradation pattern.

### AC-7: Single-iteration blocker capture
- Given a review loop completes in exactly 1 iteration with blocker issues found and fixed
- When review learnings capture runs (Step 7f equivalent)
- Then each blocker issue is stored directly via `store_memory` with `confidence="low"` (skip the recurring-pattern grouping step — single-pass blockers are first-time observations, not confirmed patterns)
- And the threshold trigger text "2+ iterations" is replaced with "1+ iterations" in all 4 command files (specify.md, design.md, create-plan.md, implement.md)
- Note: Multi-iteration recurring patterns (2+ iterations) continue to use `confidence="low"` and the existing grouping logic. The "Notable catches (single-iteration blockers)" section already exists in implement.md — the change is to also enable the main trigger at 1+ iterations.

### AC-8: Constitution imported to DB
- Given `docs/knowledge-bank/constitution.md` contains entries
- When `MarkdownImporter.import_all()` runs (session start reconciliation)
- Then constitution entries appear in the `entries` table with `category="constitution"`
- And `search_memory(query="...", category="constitution")` returns matching entries
- And session injection includes constitution entries when relevant

### AC-9: Injection limit single source of truth
- Given `pd.local.md` may or may not contain `memory_injection_limit`
- When `session-start.sh` reads the injection limit
- Then it uses the value from `pd.local.md` if set, otherwise defaults to 15 (matching config.py)
- And the hardcoded fallback `20` in session-start.sh is replaced with `15` to match config.py's default
- Source of truth: `pd.local.md` (user config) > `config.py` default (15). Both session-start.sh and config.py use the same default value.

### AC-10: reviewer_feedback_summary in Phase Context
- Given a backward transition to a phase with existing `phase_summaries`
- When Phase Context injection builds the `### Prior Phase Summaries` block
- Then each summary entry includes a `Reviewer feedback: {reviewer_feedback_summary}` line
- And the line is omitted when `reviewer_feedback_summary` is null or empty
- Note: The existing comment in SKILL.md Step 1b ("reviewer_feedback_summary is omitted from injection to save tokens") must be updated to reflect the new behavior: included during backward travel, still omitted during forward travel.

### AC-11: Zero behavior change for features without memory entries
- Given a project with no memory.db entries
- When `store_memory` is called, the min-length and near-duplicate gates do not raise unhandled exceptions (they return structured error messages)
- And when influence tracking runs with no injected entries, no errors are produced
- And when session injection runs, the empty result set does not trigger warnings
- And when `MarkdownImporter.import_all()` runs with no constitution.md, no errors are produced

## API Changes

### store_memory MCP tool — new `source` parameter
```python
# Before:
store_memory(name, description, reasoning, category, references, confidence)
# source hardcoded to "session-capture"

# After:
store_memory(name, description, reasoning, category, references, confidence, source="session-capture")
# source passed through to DB writer
```

### Ranking formula — weight redistribution
```python
# Before:
prominence = 0.25*obs + 0.15*confidence + 0.25*recency + 0.15*recall + 0.20*influence

# After:
prominence = 0.30*obs + 0.15*confidence + 0.35*recency + 0.15*recall + 0.05*influence
```

### New MCP tool: record_influence_by_content
```python
# New tool on memory-server:
record_influence_by_content(
    subagent_output_text: str,   # Full text output from the subagent
    injected_entry_names: list,  # Names of entries injected into the subagent prompt
    agent_role: str,             # Role of the agent (e.g., "spec-reviewer")
    feature_type_id: str = None, # Current feature context
    threshold: float = 0.70      # Cosine similarity threshold
)
# Returns: list of entry names that matched + their similarity scores
```

The existing `record_influence(entry_name, agent_role, feature_type_id)` tool is retained for backward compatibility but all command-file dispatches migrate to `record_influence_by_content`. Deprecation of `record_influence` is deferred.

### Influence tracking — command file change (14 locations)
```markdown
# Before (in all 4 command files, 14 total locations):
# "For each entry name in the stored list:
#    If entry name appears as a case-insensitive exact substring in the subagent's output:
#      call record_influence(entry_name=<name>, agent_role=..., feature_type_id=...)"

# After:
# "If search_memory returned entries before this dispatch:
#    call record_influence_by_content(
#      subagent_output_text=<full agent output>,
#      injected_entry_names=<stored entry names list>,
#      agent_role=<role>, feature_type_id=<type_id>, threshold=0.70)"
```

## Feasibility Assessment

### Assessment
**Overall:** Confirmed
**Reasoning:** All changes target existing, well-understood code paths. The `store_memory` source parameter is a one-line addition to the MCP handler + Pydantic model. The ranking weight change is a constant update in `ranking.py`. The Tier 1 quality gate adds ~20 lines to `store_memory`. The constitution import is a one-line category list change. The injection limit alignment is a config read change. The reviewer_feedback_summary surfacing is a template text addition in SKILL.md.

**Key Assumptions:**
- `store_memory` can accept an optional `source` parameter without breaking existing callers — Verified (Pydantic defaults handle this)
- Embedding computation for influence tracking is available at post-dispatch time — Verified (embeddings are generated on store and cached in the entries table; `record_influence_by_content` can compute a query embedding and compare against stored entry embeddings server-side)
- The 0.95 cosine threshold for near-duplicate rejection is distinguishable from the 0.90 dedup merge threshold — Needs validation via sampling existing entries
- The 0.70 cosine threshold for influence attribution is not too noisy — Needs calibration: run against 5 recent feature subagent outputs with thresholds 0.60/0.70/0.80 and compare match counts to ground truth (manual inspection). If 0.70 produces >50% false positives, increase to 0.80.

## Dependencies
- `plugins/pd/mcp/memory_server.py` — store_memory MCP handler
- `plugins/pd/hooks/lib/semantic_memory/database.py` — DB writer, dedup logic
- `plugins/pd/hooks/lib/semantic_memory/ranking.py` — prominence formula weights
- `plugins/pd/hooks/lib/semantic_memory/importer.py` — MarkdownImporter CATEGORIES
- `plugins/pd/hooks/lib/semantic_memory/injector.py` — session injection categories
- `plugins/pd/hooks/lib/semantic_memory/config.py` — config defaults
- `plugins/pd/hooks/session-start.sh` — injection limit fallback
- `plugins/pd/skills/workflow-transitions/SKILL.md` — Phase Context injection template
- `plugins/pd/commands/{specify,design,create-plan,implement}.md` — review learnings threshold, influence tracking
- `plugins/pd/skills/retrospecting/SKILL.md` — source parameter for retro store_memory calls
- `plugins/pd/commands/remember.md` — source parameter for manual capture
- `plugins/pd/commands/wrap-up.md` — store_memory caller (uses default source)
- `plugins/pd/skills/capturing-learnings/SKILL.md` — store_memory caller (uses default source)
