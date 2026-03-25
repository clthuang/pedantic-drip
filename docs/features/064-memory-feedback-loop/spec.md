# Spec: Memory Feedback Loop — Closing the Loop

## Overview

Wire up the existing but dormant memory feedback infrastructure so that: (1) subagents reliably receive relevant memory via structured prompt embedding, (2) influence tracking records which memories affected agent behavior, (3) confidence auto-promotes based on accumulated evidence, (4) keyword backfill enables FTS5 retrieval, and (5) the legacy `memory.py` injection path is deprecated.

## Scope

### In Scope
- Restructure `search_memory` + Task dispatch pattern in 5 command files (`specify`, `design`, `create-plan`, `create-tasks`, `implement`)
- Add `record_influence` calls after subagent returns in the same 5 command files
- Implement confidence auto-promotion in `database.py` merge path (behind `memory_auto_promote` config flag)
- Run keyword backfill on existing entries via Tier 1 regex
- Deprecate legacy `memory.py` injection path with 1-release escape hatch
- Remove `memory_semantic_enabled` config toggle (after deprecation period)

### Out of Scope
- Reranking with cross-encoder models
- Memory decay / automatic forgetting
- DSPy-style automatic retrieval optimization
- Structured memory representations (triples)
- New user-facing commands or workflows
- Changes to `store_memory` / `search_memory` MCP API contracts

## Requirements

### REQ-1: Structural Memory Embedding in Subagent Prompts

**What:** In all 5 workflow command files, move the `search_memory` results from outside the Task `prompt:` YAML block to inside it.

**Current state:** Each command has a "Pre-dispatch memory enrichment" instruction block that tells the orchestrator to call `search_memory` and include results as `## Relevant Engineering Memory`. This block sits between the enrichment instruction and the Task tool call, making delivery depend on model instruction-following rather than structural embedding.

**Target state:** The `## Relevant Engineering Memory` section must appear INSIDE the `prompt: |` field of every Task tool call that dispatches a subagent. The search_memory call instruction stays before the Task block, but its results must be explicitly referenced as a placeholder within the prompt template.

**Pattern (before):**
```
Pre-dispatch memory enrichment:
call search_memory...

## Relevant Engineering Memory
{search_memory results}

Dispatch agent:
  Task tool call:
    prompt: |
      Review the implementation...
```

**Pattern (after):**
```
Pre-dispatch memory enrichment:
call search_memory...

Dispatch agent:
  Task tool call:
    prompt: |
      Review the implementation...

      ## Relevant Engineering Memory
      {search_memory results from the pre-dispatch call above}
```

**Scope decision — research agents:** Research agents (`codebase-explorer`, `internet-researcher`) in design.md are excluded from memory enrichment and influence tracking. Rationale: they gather raw data, not act on engineering judgments where past learnings apply. Only reviewer/implementer agents receive memory.

**Files affected (verified via `grep subagent_type:`):**
- `plugins/pd/commands/specify.md` — 2 dispatch blocks: spec-reviewer (line 57), phase-reviewer (line 198)
- `plugins/pd/commands/design.md` — 2 eligible dispatch blocks: design-reviewer (line 246), phase-reviewer (line 435). Excluded: codebase-explorer (line 65), internet-researcher (line 88)
- `plugins/pd/commands/create-plan.md` — 2 dispatch blocks: plan-reviewer (line 63), phase-reviewer (line 188)
- `plugins/pd/commands/create-tasks.md` — 2 dispatch blocks: task-reviewer (line 63), phase-reviewer (line 223)
- `plugins/pd/commands/implement.md` — 7 dispatch blocks: code-simplifier (line 74), test-deepener (line 131), test-deepener (line 187), implementation-reviewer (line 306), code-quality-reviewer (line 482), security-reviewer (line 635), implementer (line 845)

**Total eligible dispatch blocks: 15 across 5 command files.**

**Acceptance criteria:**
- [ ] Every Task `prompt:` field in the 5 command files includes the `## Relevant Engineering Memory` section as an inline placeholder
- [ ] When `search_memory` returns empty, the section is omitted (not an empty heading)
- [ ] Existing dispatch behavior is otherwise unchanged

### REQ-2: Post-Dispatch Influence Recording

**What:** After each subagent returns, the orchestrating command scans the subagent's output for references to injected memory entry names, and calls `record_influence` for each match.

**Mechanism:**
1. Before dispatch: the command calls `search_memory` and receives a list of entry results. Each result contains a `name` field.
2. The command stores the list of entry names (e.g., `["Always validate hook JSON output", "FTS5 query sanitization required"]`).
3. After the subagent completes: the command scans the subagent's output text for exact substring matches on each stored entry name.
4. For each match: call `record_influence(entry_name=<name>, agent_role=<subagent_type>, feature_type_id=<current_feature_type_id>)` where `current_feature_type_id` is resolved at runtime from the feature's `.meta.json` (e.g., `"feature:064-memory-feedback-loop"`).
5. If `record_influence` MCP call fails: log warning, do not block.

**Command template addition (after each Task result block):**
```
Post-dispatch influence tracking:
If search_memory returned entries before this dispatch:
  For each entry name in the stored list:
    If entry name appears in the subagent's output:
      call record_influence(entry_name=<name>, agent_role=<subagent_type>, feature_type_id=<current feature type_id>)
  If no entries matched: no action (valid signal — not all injected memories will be referenced)
  If record_influence fails: warn "Influence tracking failed: {error}", continue
```

**v1 limitation:** Exact substring matching may produce false positives for entries with common-word names (e.g., "Always validate input"). This is acceptable for initial signal collection — the goal is to collect coarse influence data. LLM-based attribution in Phase 3 will improve precision once we have baseline data to calibrate against.

**Files affected:** Same 5 command files as REQ-1, same eligible dispatch blocks (15 total).

**Acceptance criteria:**
- [ ] Each dispatch block in the 5 commands has a post-dispatch influence tracking section
- [ ] `influence_log` table receives entries when subagents reference memory names
- [ ] `influence_count` on matched entries increments
- [ ] MCP failures are non-blocking (warn and continue)

### REQ-3: Confidence Auto-Promotion

**What:** When `store_memory` detects a duplicate and merges (incrementing `observation_count`), check promotion thresholds and upgrade `confidence` if criteria are met.

**Code path clarification:** Promotion logic is added to `merge_duplicate()` ONLY (not `_update_existing()`). Rationale: `merge_duplicate()` handles semantic-similarity dedup merges and already fetches the full row (line 455-461), providing access to `entry["confidence"]` and `entry["source"]`. `_update_existing()` handles hash-based upserts and does not need promotion because it only fires on exact content-hash collisions (same description = same entry, no new evidence).

**Logic (in `database.py:merge_duplicate()`):**

`merge_duplicate()` must accept a new optional parameter `config: dict | None = None` to receive promotion settings.

```python
# After incrementing observation_count:
new_obs_count = entry["observation_count"] + 1
current_confidence = entry["confidence"]
original_source = entry.get("source", "")

# Promotion check (gated by config)
promoted = False
cfg = config or {}
if cfg.get("memory_auto_promote", False):
    promote_low = cfg.get("memory_promote_low_threshold", 3)
    promote_med = cfg.get("memory_promote_medium_threshold", 5)

    # Skip promotion for imported entries
    if original_source != "import":
        if current_confidence == "low" and new_obs_count >= promote_low:
            new_confidence = "medium"
            promoted = True
        elif (current_confidence == "medium"
              and new_obs_count >= promote_med
              and original_source == "retro"):
            new_confidence = "high"
            promoted = True

if promoted:
    # Include confidence in the UPDATE statement
    set_parts.append("confidence = ?")
    params.append(new_confidence)
```

**Source semantics clarified:** The `source == "retro"` check refers to the ORIGINAL source of the entry (the `source` column in the entries table), not the source of the current merge trigger. This means only entries that were first captured during a retrospective can reach `"high"` confidence. This is intentional: retro-originated entries have been through structured AORTA analysis and represent higher-quality learnings than session captures. A session-captured entry that is later reinforced during a retro would NOT promote to high because its original source remains `"session-capture"`.

**Design note:** If future requirements need "retro-validated" to mean "an entry that was re-observed during any retro," `merge_duplicate()` would need to also accept the triggering source as a parameter. This is deferred — the simpler original-source check is sufficient for v1.

**Configuration:**
- `memory_auto_promote`: boolean, default `false` — master switch
- `memory_promote_low_threshold`: integer, default `3` — observation_count for low→medium
- `memory_promote_medium_threshold`: integer, default `5` — observation_count for medium→high (also requires `source == "retro"`)

**Guard rails:**
- Skip promotion when `source == "import"` (bulk imports inherit original confidence)
- Only promote on dedup merge path (not on initial insert)
- The `retro` source requirement for high prevents session-capture spam from reaching high confidence

**Files affected:**
- `plugins/pd/hooks/lib/semantic_memory/database.py` — `merge_duplicate()` method
- `plugins/pd/hooks/lib/semantic_memory/config.py` — new config keys
- `plugins/pd/mcp/memory_server.py` — pass config to merge path

**Acceptance criteria:**
- [ ] When `memory_auto_promote` is `false` (default): no confidence changes occur
- [ ] When enabled: entries with `observation_count >= 3` and `confidence == "low"` promote to `"medium"` on next dedup merge
- [ ] Entries with `observation_count >= 5`, `confidence == "medium"`, and `source == "retro"` promote to `"high"`
- [ ] Source `"import"` entries never promote
- [ ] Thresholds are configurable via `pd.local.md`
- [ ] Unit tests cover all promotion paths and guard rails

### REQ-4: Keyword Backfill

**What:** Run `semantic_memory.writer --action backfill-keywords` to populate keywords for all entries that currently have empty `[]` keywords.

**Mechanism:** The existing `backfill-keywords` action in `writer.py` (line 148: `_backfill_keywords()`, line 254: CLI dispatch) iterates entries with empty keywords and calls `extract_keywords()` (Tier 1 regex). This is already implemented — the requirement is to ensure it works correctly on the existing 774-entry corpus and is run as part of the feature delivery.

**Acceptance criteria:**
- [ ] After backfill: <10% of entries have empty keywords (`SELECT COUNT(*) FROM entries WHERE keywords = '[]'` / total < 0.10)
- [ ] Backfill is idempotent (re-running produces same result)
- [ ] No API calls required (Tier 1 regex only)
- [ ] FTS5 index is refreshed (triggers fire automatically on UPDATE)

### REQ-5: Legacy Injection Path Deprecation

**What:** Deprecate the `memory.py` markdown-based injection path in `session-start.sh`.

**Phase 1 (this release):**
1. Both `config.py` (line 21) and `session-start.sh` (line 425) already default `memory_semantic_enabled` to `true`. No default change needed.
2. When `memory_semantic_enabled` is explicitly set to `false` in `pd.local.md`: log deprecation warning in session output: `"Warning: memory_semantic_enabled=false is deprecated. Legacy memory.py injection will be removed in the next release."`
3. The toggle remains functional — `memory.py` still works if explicitly enabled

**Phase 2 (next release, out of scope):**
- Remove `memory.py` file entirely
- Remove `memory_semantic_enabled` config key
- Remove the legacy branch in `session-start.sh`

**Files affected:**
- `plugins/pd/hooks/session-start.sh` — default change + deprecation warning
- `plugins/pd/hooks/lib/memory.py` — no changes this release (kept as escape hatch)

**Acceptance criteria:**
- [ ] `memory_semantic_enabled` defaults to `true`
- [ ] Setting `memory_semantic_enabled: false` in `pd.local.md` still works but prints deprecation warning
- [ ] `memory.py` file is not deleted in this release

### REQ-6: Ranking Engine Verification (No Code Change)

**What:** Verify that the existing ranking engine in `ranking.py` correctly incorporates `influence_count` and `recall_count` when they are non-zero. This is PRD FR-6 — no implementation needed, just validation.

**Acceptance criteria:**
- [ ] Unit test confirms that entries with non-zero `influence_count` rank higher than entries with zero `influence_count` (all else equal)
- [ ] Unit test confirms that entries with non-zero `recall_count` rank higher than entries with zero `recall_count` (all else equal)
- [ ] Both signals contribute to the prominence sub-score as documented (15% recall, 20% influence)

## Behavioral Constraints

- MUST NOT add new user-facing commands or workflows
- MUST NOT break existing `store_memory` / `search_memory` MCP API contracts
- MUST NOT make influence tracking blocking on agent dispatch (non-blocking with warn on failure)
- MUST NOT modify `store_memory` or `search_memory` function signatures
- MUST preserve the `semantic_memory.writer` CLI public interface (used by `capturing-learnings` and `/remember` Bash fallbacks)

## Non-Functional Requirements

- **NFR-1:** Session-start injection p95 latency must remain under 5s
- **NFR-2:** `record_influence` calls must complete in <100ms (SQLite local write)
- **NFR-3:** Keyword backfill must be idempotent
- **NFR-4:** All changes must have test coverage:
  - Unit tests for confidence promotion logic (all paths + guard rails)
  - Integration tests for influence recording (store → search → dispatch → record_influence → verify influence_log)
  - Regression tests for command file changes (grep-based validation that memory section is inside prompt: blocks)

## Test Plan

### Unit Tests (database.py)
1. `test_merge_duplicate_promotes_low_to_medium` — obs_count crosses threshold, confidence changes
2. `test_merge_duplicate_promotes_medium_to_high_retro_only` — requires source=retro
3. `test_merge_duplicate_no_promote_when_disabled` — memory_auto_promote=false
4. `test_merge_duplicate_no_promote_import_source` — source=import skipped
5. `test_merge_duplicate_no_promote_below_threshold` — obs_count < threshold
6. `test_merge_duplicate_already_at_target` — confidence already at target level

### Unit Tests (memory_server.py)
7. `test_store_memory_dedup_triggers_promotion` — end-to-end through MCP
8. `test_record_influence_increments_count` — existing test, verify still passes

### Integration Tests (command validation)
9. `test_memory_section_inside_prompt_blocks` — grep all 5 command files for `## Relevant Engineering Memory` appearing between `prompt: |` and the next triple-backtick close within each dispatch block. Pattern: within each ``` code block that contains `prompt: |`, the string `Relevant Engineering Memory` must appear. Use multiline grep or script-based validation.
10. `test_influence_tracking_section_present` — grep for `record_influence` in all 5 command files; verify at least one occurrence per command file

### Ranking Verification Tests
11. `test_influence_count_affects_ranking` — entries with influence_count > 0 rank higher than equivalent entries with influence_count = 0
12. `test_recall_count_affects_ranking` — entries with recall_count > 0 rank higher than equivalent entries with recall_count = 0

### NFR Validation
13. `test_record_influence_latency` — unit test that times `db.record_influence()` call and asserts < 100ms (SQLite local write on typical hardware)
14. NFR-1 (session-start p95 < 5s) — manual validation: run 5 session starts with the changes and confirm injection completes within timeout (no automated test — depends on environment)

### Migration Validation
15. `test_keyword_backfill_coverage` — after running backfill, <10% entries have empty keywords

## File Change Summary

| File | Change Type | Description |
|------|------------|-------------|
| `plugins/pd/commands/specify.md` | Edit | Move memory section inside prompt:, add influence tracking |
| `plugins/pd/commands/design.md` | Edit | Move memory section inside prompt:, add influence tracking |
| `plugins/pd/commands/create-plan.md` | Edit | Move memory section inside prompt:, add influence tracking |
| `plugins/pd/commands/create-tasks.md` | Edit | Move memory section inside prompt:, add influence tracking |
| `plugins/pd/commands/implement.md` | Edit | Move memory section inside prompt:, add influence tracking |
| `plugins/pd/hooks/lib/semantic_memory/database.py` | Edit | Add confidence promotion in merge_duplicate() |
| `plugins/pd/hooks/lib/semantic_memory/config.py` | Edit | Add 3 new config keys |
| `plugins/pd/mcp/memory_server.py` | Edit | Pass promotion config to merge path |
| `plugins/pd/hooks/session-start.sh` | Edit | Default memory_semantic_enabled=true, add deprecation warning |
| `plugins/pd/mcp/test_memory_server.py` | Edit | Add promotion tests |
| `plugins/pd/hooks/lib/semantic_memory/test_database.py` | Edit | Add promotion unit tests |
