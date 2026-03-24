# Spec: Memory Feedback Loop — Phase 1 (Delivery & Simplification)

## Problem Statement

pd's semantic memory system records learnings but doesn't close the feedback loop to influence subagent behavior. Three adversarial reviews (2026-03-24) found that the retrieval pipeline terminates at the orchestrator — implementer, reviewer, and test-deepener agents never see injected memories. Additionally, 444+ lines of dead keyword code and 3 unused embedding providers add maintenance burden without value.

**PRD:** `docs/features/055-memory-feedback-loop/prd.md` (full 5-gap analysis; this spec covers Phase 1 only)

## Scope — Phase 1 Only

This spec covers the three highest-ROI items from the PRD:
1. **Gap 1:** Task-scoped memory delivery to subagents
2. **Gap 5:** Dead code removal (keyword stub, unused providers)
3. **Gap 3b:** Injection volume reduction (relevance threshold)

Gaps 2 (ingestion quality), 3a (project filtering), 3c (LLM keywords), 3d (recall dampening), and 4 (influence tracking) are deferred to subsequent features.

## Requirements

### FR-1: Task-scoped memory query before subagent dispatch

Before each subagent dispatch in workflow command files, the orchestrator must call `search_memory` MCP tool with a query derived from the task description and files being touched, then include the top 3-5 results in the dispatch prompt under a `## Relevant Engineering Memory` section.

**Affected command files (5) with fresh dispatch counts:**
- `plugins/pd/commands/specify.md` — 2 fresh dispatches (spec-reviewer, phase-reviewer)
- `plugins/pd/commands/design.md` — 4 fresh dispatches (codebase-explorer, internet-researcher, design-reviewer, phase-reviewer)
- `plugins/pd/commands/create-plan.md` — 2 fresh dispatches (plan-reviewer, phase-reviewer)
- `plugins/pd/commands/create-tasks.md` — 2 fresh dispatches (task-reviewer, phase-reviewer)
- `plugins/pd/commands/implement.md` — 7 fresh dispatches (code-simplifier, test-deepener x2, implementation-reviewer, code-quality-reviewer, security-reviewer, implementer)

**Note:** Research agents (codebase-explorer, internet-researcher) also receive memory enrichment — past learnings about codebase patterns and prior art are relevant to their exploration tasks.

**Mechanism:** Each command file's Task dispatch template gains a pre-dispatch instruction block:

```markdown
**Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
call `search_memory` with query: "{task description} {space-separated file list}"
and limit=5, brief=true. Include non-empty results as:

## Relevant Engineering Memory
{search_memory results}
```

This instruction is placed before each `Task tool call:` block. The orchestrator (Claude) interprets it as a prompt instruction and calls the MCP tool.

**Scope boundary:** Only fresh dispatches get the pre-dispatch instruction. Resumed dispatches do not — the memory was already included in the original context. Fresh dispatches are identifiable in command files as `Task tool call:` blocks containing `subagent_type:`. Resumed dispatches contain `resume:` instead. Every `subagent_type:` block gets the pre-dispatch instruction.

**All dispatches in implement.md** (including conditional ones like code-simplifier and test-deepener) receive the pre-dispatch instruction. The latency of `search_memory` calls (~100-500ms) is negligible compared to subagent execution time.

**Reliability:** Prompt-instructed MCP calls are not deterministic. The orchestrator may skip the call under context pressure. This is an accepted limitation for Phase 1. Influence tracking (Phase 3 of PRD) will measure actual delivery rates.

### FR-2: Remove dead keyword system

Delete the `TieredKeywordGenerator` and `SkipKeywordGenerator` classes, the `KEYWORD_PROMPT` constant, the `STOPWORD_LIST`, and all keyword-related infrastructure. The `keywords` column in the DB schema and FTS5 index remain unchanged (removing them would require a DB migration).

**Files to modify:**
- `plugins/pd/hooks/lib/semantic_memory/keywords.py` — delete entire file
- `plugins/pd/hooks/lib/semantic_memory/test_keywords.py` — delete entire file
- `plugins/pd/mcp/memory_server.py` — remove keyword_gen instantiation and usage
- `plugins/pd/hooks/lib/semantic_memory/writer.py` — remove keyword merge logic
- `plugins/pd/hooks/lib/semantic_memory/config.py` — remove `memory_keyword_provider` from DEFAULTS

**What stays:** The `keywords` TEXT column in `entries` table, the FTS5 trigger that indexes keywords, and the `memory_keyword_weight` config key. The `memory_keyword_weight` is retained unchanged — while the keywords column will always be empty, the FTS5 weight distributes across all indexed columns (name, description, reasoning, keywords) and removing it would change ranking behavior. This is a Phase 2 concern when LLM keywords are implemented.

**Forward-compatibility note:** Phase 2 (LLM keyword generation, per PRD Gap 3c) will need to implement a keyword generator from scratch rather than building on `SkipKeywordGenerator`, since the stub infrastructure is being removed. This is acceptable because the existing stub produces zero output — a fresh implementation is simpler than extending dead code.

### FR-3: Remove unused embedding providers

Delete `OpenAIProvider`, `OllamaProvider`, and `VoyageProvider` from `embedding.py`. Keep only `GeminiProvider` and `NormalizingWrapper`. Remove associated test code.

**Files to modify:**
- `plugins/pd/hooks/lib/semantic_memory/embedding.py` — remove 3 provider classes
- `plugins/pd/hooks/lib/semantic_memory/test_embedding.py` — remove tests for deleted providers (OpenAIProvider, OllamaProvider, VoyageProvider)
- `plugins/pd/hooks/lib/semantic_memory/config.py` — remove provider-specific config keys if any

**What stays:** The `create_provider(config)` factory function, but simplified to only handle `"gemini"` and `None`. The `memory_embedding_provider` config key stays (needed to select Gemini or disable embeddings).

### FR-4: Add relevance threshold to session injection

Modify the injector to skip entries below a minimum relevance score and skip injection entirely when context signals are absent.

**Changes to `plugins/pd/hooks/lib/semantic_memory/injector.py`:**

1. After ranking, filter entries to those with `final_score > 0.3` (configurable via `memory_relevance_threshold` in pd.local.md, default 0.3)
2. If fewer than 3 entries meet the threshold, inject those entries (do not pad with low-relevance entries)
3. If the context query from `collect_context()` contains only project-level description signals (no active feature, no feature branch, no recently changed files), skip injection entirely and return an empty string with a diagnostic note: `"Memory: skipped (no context signals)"`

**Implementation note:** `collect_context()` almost never returns `None` because signal #4 (project-level description from CLAUDE.md/README.md) is always included. The skip condition must therefore check for "weak context" — a context string that lacks feature, branch, and file signals — not just `None`. Modify `collect_context()` to return a `ContextResult` with a `has_work_signals: bool` flag (True when any of signals 1-3, 5, or 6 are present), or add a separate method `has_work_context()` that the injector calls before deciding to inject.

**Changes to config:** Add `memory_relevance_threshold` to DEFAULTS (default: 0.3).

**Changes to `pd.local.md` template:** Add `memory_relevance_threshold: 0.3` entry.

### FR-5: Reduce default injection limit

Change `memory_injection_limit` default from 20 to 15. Update this repo's override in `.claude/pd.local.md` from 50 to 20.

## Non-Requirements (Out of Scope)

- **NR-1:** LLM-based keyword generation (deferred to Phase 2 feature, per PRD Gap 3c).
- **NR-2:** Project-scoped filtering (deferred to Phase 2 feature, per PRD Gap 3a).
- **NR-3:** Semantic deduplication at capture time (deferred to Phase 2 feature, per PRD Gap 2a).
- **NR-4:** Confidence auto-promotion (deferred to Phase 2 feature, per PRD Gap 2b).
- **NR-5:** Influence measurement/tracking (deferred to Phase 3 feature, per PRD Gap 4).
- **NR-6:** Recall dampening (deferred to Phase 3 feature, per PRD Gap 3d).
- **NR-7:** Changing the `entries` table schema or FTS5 triggers.
- **NR-8:** Changing the entity registry.

## Acceptance Criteria

### AC-1: Subagent dispatch prompts include memory enrichment instruction
Each of the 5 workflow command files contains the pre-dispatch memory enrichment instruction block before every fresh Task dispatch block. Verified by `grep -c "Pre-dispatch memory enrichment" plugins/pd/commands/{specify,design,create-plan,create-tasks,implement}.md` returning a count matching the number of fresh dispatch blocks in each file.

### AC-2: keywords.py deleted
`plugins/pd/hooks/lib/semantic_memory/keywords.py` no longer exists. `grep -r "TieredKeywordGenerator\|SkipKeywordGenerator\|KEYWORD_PROMPT" plugins/pd/` returns zero matches (excluding git history and test deletions).

### AC-3: Unused providers deleted
`grep -r "OllamaProvider\|VoyageProvider\|OpenAIProvider" plugins/pd/hooks/lib/semantic_memory/` returns zero matches.

### AC-4: Relevance threshold filters low-scoring entries
Given scored entries with known `final_score` values (e.g., `[0.8, 0.5, 0.2, 0.1]`), when the injector's filtering logic runs with threshold 0.3, only entries with `final_score > 0.3` are included in injection output. Test by mocking `RankingEngine.rank()` to return entries with controlled scores, or by testing the filtering logic as a standalone function.

### AC-5: No-context injection skipped
Given no active feature, no feature branch (on main/develop), and no recently changed files (only project-level description signals present), when the injector runs, the output contains the diagnostic note `"Memory: skipped (no context signals)"` and no memory entries are included.

### AC-6: Default injection limit reduced
`config.py` DEFAULTS has `memory_injection_limit: 15`. This repo's `.claude/pd.local.md` has `memory_injection_limit: 20`.

### AC-7: Existing memory tests pass
All existing semantic memory tests pass after the deletions. The memory server's `store_memory`, `search_memory`, and `delete_memory` tools work correctly without the keyword generator.

### AC-8: Existing workflow tests unaffected
The 5 command files are markdown templates — no executable tests. Verify by reading each file and confirming the pre-dispatch instruction doesn't break the existing Task dispatch syntax.

## Dependencies

- No external dependencies. All changes are within the pd plugin.
- `search_memory` MCP tool already exists and works.
- The `brief=true` parameter on `search_memory` already exists (returns compact one-line-per-entry format).

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Orchestrator skips search_memory call under context pressure | Medium | Medium (subagents don't get memories) | Accepted for Phase 1. Influence tracking in Phase 3 will measure delivery rates. |
| Removing keyword code breaks existing memory server | Low | High | Keywords are a no-op stub — removing them simplifies, not changes, behavior. Tests verify. |
| Relevance threshold too aggressive — filters useful entries | Low | Medium | Default 0.3 is conservative. Configurable via pd.local.md. |
| Reducing injection limit loses useful broad context | Low | Low | Moving from 50→20 still injects top 20 entries. Task-scoped delivery (FR-1) compensates by targeting specific entries to specific agents. |
