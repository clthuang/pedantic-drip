# Plan: Memory Phase 3 — Feedback Loop Closure

## Context

Feature 061. Closes the final 3 PRD gaps: notable catches (prompt extension), project-scoped filtering (retrieval + ranking), recall dampening (time decay formula).

## Execution Order (TDD)

```
Task 1 (recall dampening + tests) → Task 2 (project filtering + tests)
  → Task 3 (MCP tool + injector + tests) → Task 4 (notable catches — prompt changes)
  → Task 5 (docs)
```

## Tasks

### Task 1: Recall Dampening

**Why:** Implements design C4 + spec FR-3.
**Files:** `plugins/pd/hooks/lib/semantic_memory/ranking.py`, `plugins/pd/hooks/lib/semantic_memory/test_ranking.py`
**Do:**
1. Update `_recall_frequency(self, recall_count, last_recalled_at=None, now=None)` — backward compat: no time args returns base
2. Update `_prominence()` line 222: pass `entry.get("last_recalled_at")` and `now`
**Tests:** decay at 14/30/60 days, backward compat (no args), None last_recalled_at (0.5 multiplier), recall_count=0 stays 0
**Done when:** All existing ranking tests pass + 4 new tests pass

### Task 2: Project-Scoped Ranking

**Why:** Implements design C2 + C3 + spec FR-2.
**Files:** `plugins/pd/hooks/lib/semantic_memory/retrieval_types.py`, `plugins/pd/hooks/lib/semantic_memory/retrieval.py`, `plugins/pd/hooks/lib/semantic_memory/ranking.py`, `plugins/pd/hooks/lib/semantic_memory/test_retrieval.py`, `plugins/pd/hooks/lib/semantic_memory/test_ranking.py`
**Do:**
1. Add `project: str | None = None` to `RetrievalResult` dataclass
2. Add `project` param to `retrieve()` — pass through to RetrievalResult (no filtering in retrieve)
3. Update `rank()` — when `result.project` is set: score all, split by `entries[cid]["source_project"]`, select N/2 from project tier via `_balanced_select`, fill remainder from universal (excluding already-selected), merge by final_score
**Tests:** project=None unchanged, project set with enough entries (5/5 split), project set with underfill, dedup of overlapping entries
**Done when:** All existing tests pass + 4 new tests pass

### Task 3: MCP Tool + Injector

**Why:** Implements design C5 + MCP layer. Depends on Tasks 1-2.
**Files:** `plugins/pd/mcp/memory_server.py`, `plugins/pd/hooks/lib/semantic_memory/injector.py`, `plugins/pd/hooks/lib/semantic_memory/test_injector.py`
**Do:**
1. Add `_resolve_project_name(project_root)` to injector.py — git remote basename, fallback to dirname
2. Pass `project=project_name` to `pipeline.retrieve(context_query, project=...)` in injector main()
3. Add `project: str | None = None` param to `search_memory` MCP tool in memory_server.py, pass through to pipeline
**Tests:** _resolve_project_name with/without git remote, injector passes project to retrieve (mock test)
**Done when:** 3 new tests pass + existing injector/server tests pass

### Task 4: Notable Catches (Prompt Changes)

**Why:** Implements design C1 + spec FR-1. Prompt-only, no Python.
**Files:** 5 command files (specify.md, design.md, create-plan.md, create-tasks.md, implement.md)
**Do:** Add to each file's "Capture Review Learnings" section:
```
**Notable catches (single-iteration blockers):**
If the review loop completed in 1 iteration AND the reviewer found issues
with severity "blocker":
1. For each blocker issue (max 2):
   - Store via store_memory: name from description, confidence="medium",
     reasoning="Single-iteration blocker catch in feature {id} {phase} phase",
     category inferred from issue type
```
**Done when:** `grep -c "notable catch\|single-iteration blocker" plugins/pd/commands/{specify,design,create-plan,create-tasks,implement}.md` returns >= 1 for each file

### Task 5: Documentation

**Files:** `CHANGELOG.md`
**Do:** Add entries under [Unreleased] for project-scoped search, recall dampening, notable catches
**Done when:** grep confirms entries

## Verification

1. `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_ranking.py -v` — all pass
2. `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_retrieval.py -v` — all pass
3. `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_injector.py -v` — all pass
4. Existing doctor tests still pass: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -q`
