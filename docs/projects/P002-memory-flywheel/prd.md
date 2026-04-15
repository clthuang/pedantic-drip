# PRD: Memory Flywheel — Close the Self-Improvement Loop (REVISED)

*Source: Backlog #00053*
*Original: 2026-04-15. Revised: 2026-04-15 after 4-agent empirical re-verification.*

## Status
- Created: 2026-04-15
- Last updated: 2026-04-15 (rescoped post-investigation)
- Status: Active (1 of 5 features shipped: 079 FTS5 backfill)
- Problem Type: Multi-Feature Project
- Archetype: improving-an-existing-system

## Rescope Notes (2026-04-15)

After shipping 079 and starting 080, empirical re-verification by 4 parallel codebase-explorer agents found that **the original PRD was substantially wrong about 3 of 5 leverage items**:

| Item | Original claim | Verified state | Real gap |
|---|---|---|---|
| Influence wiring | "never called by any orchestrator" | **REFUTED.** 14 callsites in implement/specify/design/create-plan; `_influence_score()` already in `rank()` via `_prominence()` weight 0.05 | Tuning (threshold/weight) + diagnostics, not wiring |
| FTS5 backfill | "vector=964, fts5=0 = empty table" | **REFUTED.** Table had 972 rows; `fts5=0` was `fts5_candidate_count` from a specific query, not table row count | Defensive migration 5 added anyway (079, shipped) |
| Recall tracking | "only increments on dedup-merge" | **REFUTED.** `recall_count` updates on retrieval (`injector.py:281`); promotion `low→medium→high` exists in `merge_duplicate` (database.py:512-531) | Persistent confidence decay job (only real gap) |
| Mid-session refresh | "no PostToolUse refresh hooks" | **PARTIAL.** No hook, but 17 pre-dispatch `search_memory` calls already act as per-dispatch refresh for sub-agents. Main LLM context still gets stale | Orchestrator-side refresh (CronCreate-pattern from 078) |
| Promote-pattern | "command doesn't exist" | **VERIFIED.** Genuinely greenfield | Greenfield MVP (CLAUDE.md target only first) |

The original investigation conflated "table empty" with "query returned zero candidates," and "wiring missing" with "wiring present but tuning weak." This addendum corrects the scope.

## Problem Statement (revised)

The pd plugin's memory system has more shipped capability than the original PRD assumed. The remaining real gaps are smaller and more targeted:

1. **Apply loop is wired but undertuned** — `record_influence_by_content` fires from 14 sites; threshold 0.70 is too strict (likely <5% hit rate); weight 0.05 contributes ~1.5% of final ranking score. No diagnostics expose the hit rate.
2. **Confidence promotion exists but decay does not** — entries can move `low→medium→high` via `merge_duplicate` when `memory_auto_promote` is enabled; nothing demotes stale entries.
3. **Mid-session refresh works for sub-agents but not the orchestrator's own context** — pre-dispatch enrichment refreshes per-Task-call; orchestrating Claude only sees session-start snapshot.
4. **Pattern codification path is missing** — KB has 60+ patterns, no skill/command/agent converts them into enforceable rules in CLAUDE.md, hooks, or skill bodies.

## Goals (revised)

1. **Activate influence with measurement** — make influence tracking observable (hit-rate diagnostics) and tunable (config-driven threshold/weight).
2. **Add confidence decay** — degrade stale entries' confidence over time so signal quality stays clean.
3. **Refresh orchestrator context mid-session** — extend the existing pre-dispatch enrichment pattern to keep main-LLM context current at phase boundaries.
4. **Codify high-confidence patterns** — `/pd:promote-pattern` MVP for CLAUDE.md target (highest leverage, lowest cost).

## Success Criteria (revised)

- [ ] **Influence tuning (080):** `record_influence_by_content` hit rate observable per dispatch; default threshold lowered + config-driven; weight tunable. Within 5 cycles after merge, ≥30% of injected entries get an influence event (currently ~5%).
- [x] **FTS5 (079):** ✅ shipped — `entries=973`, `entries_fts=973`, schema v5, 411/411 tests pass.
- [ ] **Confidence decay (082):** scheduled or session-start-triggered job demotes confidence for entries unobserved for >N days; tested; respects existing promotion path.
- [ ] **Mid-session refresh (081):** orchestrator's working memory refreshes at phase boundaries (post-`complete_phase` or pre-`Skill` dispatch); bounded token cost (≤500 tokens per refresh).
- [ ] **Promote-pattern (083):** `/pd:promote-pattern` accepts a pattern name/ID, classifies into one of {hook, skill, agent, command}, produces target-appropriate diff for review, applies on approval. CLAUDE.md is explicitly NOT a target (accumulation anti-pattern). At least 1 high-confidence pattern promoted to each target type (hook, skill, agent) in manual test; command promotion optional.

## Out of Scope (revised, expanded)

- CLAUDE.md as promotion target (anti-pattern: accumulation clogs the file, reduces signal-to-noise, token inflation per session)
- Cross-project influence ranking (separate concern)
- Influence weight rebalancing within `_prominence()` formula (separate spec exercise)
- Embedding model migration (`gemini-embedding-001` stays)
- Multi-target promotion in one invocation (MVP: one pattern → one target per run)
- Auto-promotion (no human-in-the-loop); MVP is diff-preview + AskUserQuestion approval

## Revised Feature Decomposition

Same 5 IDs (preserve audit trail), renamed scopes:
- **079** ✅ FTS5 backfill (shipped, defensive even though gap was misdiagnosed)
- **080** Influence tuning + diagnostics (was: "wiring")
- **081** Orchestrator mid-session refresh (was: "any mid-session refresh")
- **082** Confidence decay job (was: full recall + decay + promotion; recall and promotion are already done)
- **083** `/pd:promote-pattern` MVP, targets = {hook, skill, agent, command}. CLAUDE.md explicitly excluded as target (accumulation anti-pattern).

Dependency order unchanged: 080 informs 082 tuning; 083 unchanged.

## Decomposition Hints (revised)

| Feature | New scope | Files | Complexity |
|---|---|---|---|
| 080 | Add `--debug-influence` mode to retrieval; emit per-dispatch hit-rate; expose `memory_influence_threshold` and `memory_influence_weight` config; lower threshold default to 0.55. | `memory_server.py:614` (record_influence_by_content), `ranking.py:176` (_influence_score), `pd.local.md` template | Low |
| 081 | Add `refresh_memory_context` instruction emitter to `complete_phase` MCP response (or PostToolUse hook on Skill dispatch). Reuse 17-site pre-dispatch enrichment pattern. | `mcp/workflow_state_server.py` complete_phase tool, optional new hook | Low-Medium |
| 082 | New `decay_confidence(db, config)` in writer.py or maintenance.py. Daily-style demotion when `last_recalled_at < now - N days`. New SessionStart trigger. Tests. | `semantic_memory/writer.py` or new `maintenance.py`, `session-start.sh` trigger, tests | Medium |
| 083 | New `/pd:promote-pattern` slash command. Read KB entries (filter: confidence=high, observation_count≥3), present selection, classify target ∈ {hook, skill, agent, command}, produce target-appropriate diff, apply on approve. Mark pattern `promoted: {target_type}:{target_path}` in KB markdown. Target classification: keyword heuristic (e.g. `PreToolUse`/`on Edit`→hook; `reviewer`→agent; gerund (`implementing`, `creating`)→skill) → LLM fallback for ambiguous → user override. CLAUDE.md explicitly excluded. | `plugins/pd/commands/promote-pattern.md`, `plugins/pd/skills/promoting-patterns/SKILL.md`, target-type generators (hook template, skill-patch, agent-patch, command-patch) | Medium-High |
