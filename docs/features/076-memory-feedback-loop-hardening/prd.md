# pd Memory System Gap Analysis

**Date:** 2026-04-03
**Query:** Thoroughly review the memory system of pd and identify gaps for a comprehensive self-improving feedback loop

## Executive Summary

pd's memory system is architecturally sound and matches several SOTA patterns (hybrid retrieval, multi-factor ranking, structured write paths). However, seven concrete gaps prevent it from functioning as a true self-improving feedback loop: broken write-path metadata (source hardcoding), orphaned data channels (constitution.md, reviewer feedback, research outputs), and a near-dormant influence signal that holds 20% ranking weight. Most fixes are small to medium effort.

---

## What pd Already Does Well

- **Hybrid retrieval** (vector cosine + FTS5 BM25) — matches Mem0 and A-Mem approaches
- **5-factor prominence ranking** (0.25 obs + 0.15 confidence + 0.25 recency + 0.15 recall + 0.20 influence) with decay — comparable to Stanford Generative Agents
- **Dedup with cosine threshold** (0.90) — prevents entry proliferation
- **Multiple structured write paths** (retro, review learnings, user corrections, RCA, capturing-learnings)
- **Session-start injection** with relevance filtering and work context signals
- **Reconciliation sync** at session start keeps markdown KB and DB in sync

---

## Critical Gaps

### Gap 1: `source='retro'` unreachable via MCP
**Severity: high | Confidence: high | Effort: small**

`store_memory` MCP hardcodes `source='session-capture'` (memory_server.py:48). Retro learnings, RCA findings, and `/pd:remember` entries are all tagged identically. This breaks auto-promote logic that requires `source='retro'` to promote confidence past 'medium'.

**Location:** `plugins/pd/mcp/memory_server.py:48`
**Fix:** Add a `source` parameter to `store_memory` MCP, defaulting to `'session-capture'`, allowing callers to pass their actual source.

### Gap 2: Influence tracking nearly dormant
**Severity: high | Confidence: high | Effort: medium**

Post-dispatch influence tracking fires only on verbatim case-insensitive name match in subagent output. Subagents paraphrase rather than quoting entry names. `influence_count` is rarely incremented, making the 20% influence weight in ranking a near-zero signal that dilutes the other four factors.

**Location:** `plugins/pd/commands/implement.md:468-474` (and equivalent in specify, design, create-plan)
**Fix (quick):** Reduce influence weight from 0.20 to 0.05 and redistribute to obs/recency.
**Fix (proper):** Replace name matching with embedding-based content similarity attribution.

### Gap 3: No self-improvement metrics
**Severity: high | Confidence: medium | Effort: large**

pd has no tracking of whether memory actually improves outcomes. No precision/recall metrics, no false-positive detection, no 30/60/90 day trends. Research shows indiscriminate storage degrades performance — without measurement, pd can't detect this failure mode.

**Fix:** Log per-session metrics to a lightweight table: memories injected count, memories cited in subagent output, review iteration count, goal completion. Analyze 30/60/90 day trends.

---

## Moderate Gaps

### Gap 4: constitution.md never imported to DB
**Severity: medium | Confidence: high | Effort: small**

`docs/knowledge-bank/constitution.md` exists but `MarkdownImporter.CATEGORIES` (importer.py:21-26) only covers 3 of 4 categories. Constitution entries cannot be surfaced by search_memory or session injection.

**Fix:** Add `('constitution.md', 'constitution')` to `MarkdownImporter.CATEGORIES` and add 'constitution' to `CATEGORY_ORDER`/`CATEGORY_HEADERS` in injector.py.

### Gap 5: reviewer_feedback_summary stored but never read
**Severity: medium | Confidence: high | Effort: small**

`phase_summaries` stores `reviewer_feedback_summary` per phase, but it's explicitly omitted from Phase Context injection (SKILL.md:109 "to save tokens") and not included in retro context bundles.

**Fix:** Include `reviewer_feedback_summary` in Phase Context injection during backward travel (Step 1b).

### Gap 6: backward_history never analyzed cross-feature
**Severity: medium | Confidence: medium | Effort: medium**

`backward_history` accumulates per-feature backward transitions. It's only used for same-feature ping-pong detection. Never aggregated across features, never surfaced to retro, never analyzed for systemic patterns.

**Fix:** During retro, query entity DB for all features' backward_history entries. Detect patterns like "design phase consistently bounces back to specify" and store as anti-patterns.

### Gap 7: Research summaries not fed back to memory
**Severity: medium | Confidence: medium | Effort: medium**

RAS skill saves findings to `agent_sandbox/{date}/ras-{slug}.md` but never extracts learnings into `store_memory`.

**Fix:** Add a step in the RAS synthesizer to extract 1-3 key learnings from each research session and store via `store_memory` MCP.

### Gap 8: No just-in-time learning on rejection/denial events
**Severity: high | Confidence: high | Effort: medium**

When something goes wrong — a user denies a tool call, a reviewer rejects an artifact on iteration 1, or the user corrects a behavior — there is no structural trigger to capture the learning. The current mechanisms are all passive or threshold-gated:

1. **User tool denial:** Claude Code has no hook event type for "user denied tool execution." The denial becomes conversation context, but nothing fires to log it.
2. **Single-iteration reviewer rejections:** Step 7f (review learnings) only triggers when the review loop runs 2+ iterations. Blocker issues caught and fixed in a single pass are never captured — yet these are often the most valuable learnings (the first-time mistakes).
3. **User corrections mid-session:** The `capturing-learnings` skill relies on the LLM passively detecting correction patterns in conversation text (e.g., "no, always use X"). This is unreliable — the LLM may not recognize the pattern, or may be focused on executing the next task.
4. **Reviewer backward travel:** When a reviewer sends work backward (e.g., design→specify), the `backward_context` is stored in entity metadata for the rework phase, but the *reason* the backward travel was needed is never extracted as a generalizable learning.

**What this means for the feedback loop:** The system learns from **aggregated patterns** (retro, multi-iteration reviews) but misses **individual signal events** — exactly the moments with the highest learning density. This is the equivalent of a human only learning from quarterly reviews, never from real-time feedback.

**Fix — Event-Driven Learning Hook:**
1. Add a `PostToolUse` hook for all tool types that inspects the tool result for denial/rejection signals. When detected, log: `{tool, input_summary, denial_reason, timestamp}` to a lightweight `rejection_log` (SQLite table or JSONL file).
2. Lower the Step 7f threshold from 2+ iterations to 1+ — any reviewer blocker should be captured, not just recurring ones.
3. Add a `PostToolUse` hook (or enhance capturing-learnings) that detects when AskUserQuestion returns "Other" (custom user input) — these are corrections/preferences that should always trigger capture.
4. At session end or retro time, scan the rejection_log for patterns and batch-store as memory entries.

**Architectural note:** Claude Code's hook system supports `PreToolUse` and `PostToolUse` but not a dedicated "UserDenied" event. However, `PostToolUse` receives the tool result, and denied tools could be detected by checking for denial markers in the conversation context. The more robust approach is to handle this in the LLM layer (enhanced capturing-learnings with explicit instructions to watch for denial events) rather than the hook layer.

### Gap 9: No review gate before memory writes — quality uncontrolled
**Severity: high | Confidence: high | Effort: medium**

Every write path to memory goes in without validation or review. External research (Mem0, FadeMem, arXiv:2505.16067) explicitly warns that **indiscriminate storage degrades long-term performance** — a wrong memory confidently retrieved is worse than no memory at all.

**Unreviewed write paths (7 total):**

| Write Path | Volume | Gate? |
|---|---|---|
| Retro → store_memory (Step 3a) | 3-5 per retro | None |
| Retro → KB markdown append (Step 4) | Same entries | None |
| Review learnings (Step 7f) in specify/design/create-plan/implement | Max 5 per phase | None |
| `/pd:remember` | 1 per invocation | None |
| `capturing-learnings` silent mode | Budget-limited (default 5) | None (ask-first mode has user prompt, but no quality check) |
| RCA → store_memory | 2 per RCA | None |
| `wrap-up` → store_memory | Variable | None |

**Risks of unreviewed writes:**
1. **Error propagation:** A retro-facilitator hallucination becomes a "pattern" injected into all future sessions. The LLM executing the retro can misattribute causation, invent correlations, or overgeneralize from a single observation — and the entry goes straight to memory.db with no second opinion.
2. **Contradictory entries:** Two retros from different features can produce contradictory learnings (e.g., "always use cross-references" vs. "inline duplication is acceptable for <5 files"). Both get stored; retrieval returns whichever ranks higher by prominence, not by correctness.
3. **Low-signal noise:** Review learnings (Step 7f) capture recurring review issues at confidence='low'. Over many features, this accumulates a long tail of low-confidence entries that crowd out high-signal entries in retrieval results, despite the relevance threshold filter.
4. **Stale entries persist:** There is no mechanism to mark an entry as outdated when the codebase changes. A pattern from feature 030 may be wrong by feature 075, but it stays in the DB with its original confidence.

**Fix — Tiered Review Gate:**

1. **Tier 1 — Automated quality check (all writes):** Before any `store_memory` call, run a lightweight validation:
   - Reject entries with description < 20 chars (too vague)
   - Reject entries whose name is a near-duplicate of an existing entry (cosine > 0.95 — stricter than dedup's 0.90 merge threshold)
   - Reject entries that contradict an existing high-confidence entry (LLM comparison against top-3 similar entries)
   This can be implemented as a pre-write hook inside `store_memory` MCP itself.

2. **Tier 2 — Agent review gate (retro + review learnings):** Before persisting retro learnings (Step 3a) and review learnings (Step 7f) to the KB, dispatch a lightweight reviewer that checks:
   - Is this a genuine pattern or a single-observation overgeneralization?
   - Does it contradict existing KB entries?
   - Is it actionable (would an agent change behavior based on this)?
   Reject entries that fail. Budget: 1 reviewer dispatch per retro (batched), not per entry.

3. **Tier 3 — Periodic KB audit (session start or weekly):** During reconciliation, scan for:
   - Entries with 0 recall_count after 30 days (never retrieved → likely irrelevant)
   - Entries with 0 influence_count after 10 recalls (retrieved but never applied → likely too generic)
   - Contradictory entry pairs (high cosine similarity but different categories)
   Flag for human review or auto-archive.

**Architectural note:** The Mem0 pattern of LLM-powered ADD/UPDATE/DELETE/NOOP at write time is the production standard for this. pd could adopt this by making `store_memory` compare the candidate entry against existing similar entries and decide the operation, rather than always ADDing (with dedup merge as the only safeguard).

### Gap 10: memory_injection_limit default discrepancy
**Severity: low | Confidence: high | Effort: small**

`config.py:29` defaults to 15, `session-start.sh:421` uses 20. Whichever runs last wins.

**Fix:** Align session-start.sh to read from config.py's default.

---

## Strategic Opportunities (from SOTA Research)

### Write-time conflict resolution (Mem0 pattern)
Currently pd can only merge duplicates. It cannot update contradicted entries or invalidate stale ones. Mem0's ADD/UPDATE/DELETE/NOOP approach with LLM-powered conflict resolution at write time is the production standard. Would prevent stale/contradictory memories from accumulating.

### Importance-gated decay + auto-prune (FadeMem)
pd has no pruning mechanism. Entries accumulate indefinitely. FadeMem's `R = importance * e^(-decay_rate * t)` with auto-delete at R<0.05 would clean up stale entries at retrieval time without requiring a separate maintenance job.

### Retroactive memory linking (A-Mem Zettelkasten)
When a new memory is stored, it could retroactively update related older entries as new context clarifies them. pd currently treats each entry as independent — no inter-entry links.

### Success learning, not just failure learning (SAGE)
pd's pre-dispatch enrichment filters to `category='anti-patterns'` only. Injecting proven patterns and successful heuristics alongside anti-patterns would give agents positive signals, not just warnings.

### Tiered TTL (Mem0, FadeMem)
All entries persist equally. Corrections should be permanent; session-level context should expire in 3-7 days; project context in 30 days.

### Double-loop learning (Argyris)
Periodically question whether the memory strategy itself is working. An open gap across all production agent systems. Would require metrics infrastructure (Gap 3) as a prerequisite.

---

## Priority Ranking

| # | Item | Effort | Impact |
|---|------|--------|--------|
| 1 | Fix `source` hardcoding in MCP | small | Unblocks auto-promote chain |
| 2 | Fix influence tracking (reduce weight or fuzzy match) | small/medium | Corrects ranking signal corruption |
| 3 | Memory write review gate (Tier 1 automated + Tier 2 agent) | medium | Prevents error propagation and noise accumulation |
| 4 | Just-in-time learning on rejection/denial events | medium | Captures highest-density learning signals |
| 5 | Add `constitution.md` to importer | small | Surfaces missing KB content |
| 6 | Align `injection_limit` default | small | Removes config inconsistency |
| 7 | Surface `reviewer_feedback_summary` | small | Completes feature 075 data flow |
| 8 | Add RAS -> memory pipeline | medium | Closes research feedback loop |
| 9 | Cross-feature `backward_history` analysis | medium | Enables systemic pattern detection |
| 10 | Metrics infrastructure | large | Enables double-loop learning |

---

## Sources

### Codebase
- `plugins/pd/hooks/lib/semantic_memory/database.py:54-276` (schema)
- `plugins/pd/hooks/lib/semantic_memory/ranking.py:134-252` (prominence formula)
- `plugins/pd/hooks/lib/semantic_memory/injector.py:199-311` (session injection)
- `plugins/pd/hooks/lib/semantic_memory/importer.py:21-76` (KB sync)
- `plugins/pd/hooks/lib/semantic_memory/config.py:15-34` (tunables)
- `plugins/pd/mcp/memory_server.py:40-259` (MCP tools)
- `plugins/pd/skills/workflow-transitions/SKILL.md:71-347` (phase context + summaries)
- `plugins/pd/skills/retrospecting/SKILL.md:212-349` (retro -> KB chain)
- `plugins/pd/commands/implement.md:468-474, 1226-1268` (influence tracking, review learnings)

### External Research
- Reflexion (NeurIPS 2023) — arxiv.org/abs/2303.11366
- A-Mem (Feb 2025) — arxiv.org/html/2502.12110v1
- Mem0 (Apr 2025) — arxiv.org/html/2504.19413v1
- SAGE (Sep 2024) — arxiv.org/html/2409.00872v1
- FadeMem — arXiv:2601.18642
- Memory in the Age of AI Agents (survey) — arxiv.org/abs/2512.13564
- AWS AgentCore Long-Term Memory — aws.amazon.com/blogs
