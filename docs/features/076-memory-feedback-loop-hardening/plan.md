# Implementation Plan: Memory Feedback Loop Hardening

**Feature:** 076-memory-feedback-loop-hardening
**Spec:** spec.md | **Design:** design.md
**Created:** 2026-04-03

## Implementation Order

### Stage 1: Core MCP Changes (store_memory + ranking)

**Item 1: C1 — store_memory source parameter**
Add `source` parameter to `store_memory` MCP tool. Remove hardcoded `source = "session-capture"` at memory_server.py:81. Pass through to `_process_store_memory()`.
- Why: Unblocks auto-promote logic (retro-source entries can promote to high confidence). Unblocks Item 9 (source propagation).
- Why this order: No dependencies. Modifies memory_server.py function signature — must be done before Items 2 and 5 (which add more logic to same function).
- File: `plugins/pd/mcp/memory_server.py`
- TDD: Tests+C1 RED → Impl C1 GREEN (see tasks.md 1.1→1.2)
- Complexity: Simple

**Item 2: C2 — Tier 1 quality gate (min-length + near-duplicate + constitution write-protection)**
Add min-length check (< 20 chars → reject) and near-duplicate check (cosine > 0.95 with different name → reject) to `_process_store_memory`. Constitution write-protection (category="constitution" → reject). Gates run before existing dedup merge logic.
- Why: Prevents error propagation and noise accumulation in memory DB. Constitution is import-only.
- Why this order: Modifies same function as Item 1 — function signature must be stable first. File-level ordering constraint (not a logical dependency).
- File: `plugins/pd/mcp/memory_server.py`
- TDD: Tests+C2 RED → Impl C2 GREEN (see tasks.md 1.3-1.6)
- Note: Near-duplicate gate reuses existing `check_duplicate` with threshold=0.95. DedupResult has `existing_entry_id` field (verified dedup.py:28). Use `db.get_entry(existing_entry_id)` to look up matched name.
- Complexity: Medium

**Item 3: C3 — Ranking weight redistribution**
Update prominence formula: influence 0.20→0.05, observation 0.25→0.30, recency 0.25→0.35. Update docstring and formula at ranking.py:242,252.
- Why: Influence signal is dormant (rarely >0). Redistributing its weight to observation and recency improves retrieval quality for active entries.
- Why this order: Independent of Items 1-2 (different file). No dependencies.
- File: `plugins/pd/hooks/lib/semantic_memory/ranking.py`
- TDD: Tests+C3 RED → Impl C3 GREEN (see tasks.md 1.7→1.8)
- Complexity: Simple

### Stage 2: New MCP Tool (record_influence_by_content)

**Item 4: C4 — record_influence_by_content MCP tool**
New tool that accepts subagent output text, chunks by paragraph (skip <20 chars), truncates to last 2000 chars, computes per-chunk embeddings, compares against injected entry embeddings, records influence for matches >= threshold.
- Why: Replaces dormant name-match influence tracking with embedding-based attribution that actually fires.
- Why this order: Independent of Items 1-3 (new tool, doesn't modify existing code). Unblocks Item 10 (command file migration).
- File: `plugins/pd/mcp/memory_server.py`
- TDD: Tests+C4 RED → Impl C4 GREEN (see tasks.md 2.1→2.2). Includes degradation test (embedding provider unavailable → return empty matches with warning).
- Complexity: Medium

### Stage 3: Category + Config Fixes

**Item 5: C5 — Constitution import**
Add constitution.md to MarkdownImporter CATEGORIES, CATEGORY_ORDER, CATEGORY_HEADERS, VALID_CATEGORIES. Write-protection already added in Item 2 (constitution check is part of the Tier 1 gate in `_process_store_memory`).
- Why: Surfaces foundational principles (KISS, YAGNI) in memory retrieval and session injection.
- Why this order: Category registration is independent of Items 1-4. File-level: importer/injector/__init__.py are separate from memory_server.py.
- Files: `plugins/pd/hooks/lib/semantic_memory/importer.py`, `injector.py`, `__init__.py`
- TDD: Tests+C5 RED → Impl C5 GREEN (see tasks.md 3.1→3.2)
- Complexity: Simple

**Item 6: C6 — Injection limit alignment**
Replace both hardcoded `"20"` fallbacks with `"15"` in session-start.sh:421-422.
- Why: Removes config inconsistency between Python (15) and bash (20) defaults.
- Why this order: Completely independent. Single-file bash change.
- File: `plugins/pd/hooks/session-start.sh`
- Complexity: Simple

### Stage 4: Instruction Text Changes (SKILL.md + command files)

**Item 7: C7 — reviewer_feedback_summary in Phase Context**
Add `Reviewer feedback: {reviewer_feedback_summary}` line to Phase Context injection template in SKILL.md Step 1b. Update the omission note at line 109.
- Why: Surfaces stored reviewer feedback during backward travel (data exists but was never read).
- Why this order: No code dependencies. SKILL.md template change only.
- File: `plugins/pd/skills/workflow-transitions/SKILL.md`
- Verification: `grep 'Reviewer feedback:' plugins/pd/skills/workflow-transitions/SKILL.md` returns 1 match
- Complexity: Simple

**Item 8: C8 — Review learnings threshold (1+ iterations)**
Replace "2+ iterations" with "1+ iterations" trigger in all 4 command files (8 locations). Add two-path template: 1 iteration → direct store, 2+ → grouped patterns.
- Why: Captures single-pass blockers — highest-density learning signals currently lost.
- Why this order: No code dependencies. Command file text changes only.
- Files: `plugins/pd/commands/specify.md`, `design.md`, `create-plan.md`, `implement.md`
- Verification: `grep -c '2+ iterations' plugins/pd/commands/{specify,design,create-plan,implement}.md` returns 0 for all
- Complexity: Simple

**Item 9: C9 — Caller source propagation**
Add `source="retro"` to retrospecting SKILL.md store_memory call. Add `source="manual"` to remember.md.
- Why: Enables downstream auto-promote logic to distinguish retro-sourced entries from session-captured ones.
- Why this order: Depends on Item 1 (source param must exist in store_memory).
- Files: `plugins/pd/skills/retrospecting/SKILL.md`, `plugins/pd/commands/remember.md`
- Complexity: Simple

**Item 10: I4 — Command file influence tracking migration**
Replace all 14 influence tracking blocks across 4 command files with `record_influence_by_content` call pattern.
- Why: Migrates from dormant name-match tracking to working embedding-based attribution.
- Why this order: Depends on Item 4 (new tool must exist before callers reference it).
- Files: `plugins/pd/commands/specify.md` (2), `design.md` (2), `create-plan.md` (3), `implement.md` (7)
- Verification: `grep -c 'record_influence(' plugins/pd/commands/{specify,design,create-plan,implement}.md` all return 0; `grep -c 'record_influence_by_content'` returns specify:2, design:2, create-plan:3, implement:7
- Complexity: Medium (14 locations, mechanical but error-prone)

### Stage 5: Testing & Verification

**Item 11: Full regression suite**
Run all affected test suites to verify no regressions:
```bash
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_memory_server.py -v
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/ -v
bash plugins/pd/mcp/test_run_memory_server.sh
```
- Complexity: Simple

## Dependency Graph

```
Item 1 (source param) ──┐
Item 2 (quality gate) ──┼──> Item 5 (constitution, uses gate)
Item 3 (weights) ────────┘
                         ├──> Item 9 (source propagation, uses source param)
Item 4 (new MCP tool) ──┴──> Item 10 (influence migration, uses new tool)
Items 1-6 ───────────────┬──> Item 7 (SKILL.md, no code deps)
                         ├──> Item 8 (threshold change, no code deps)
                         └──> Item 11 (regression)
Item 6 (config fix): independent
```

Items 1, 3, 4, 6 are independent (different files). Items 7, 8 are independent of each other (different files, no code deps). Item 2 depends on Item 1 (file-level: both modify `_process_store_memory`, function signature must be stable). Item 5 is independent of Item 2 (category registration is in separate files; write-protection was added in Item 2). Item 9 depends on Item 1 (source param must exist). Item 10 depends on Item 4 (new tool must exist before callers reference it).

## Risk Areas

1. **Two-threshold dedup ordering** — The 0.95 gate must run before the 0.90 merge. Implementer must not reorder.
2. **14 influence tracking locations** — High count, easy to miss one. Grep verification step mitigates.
3. **Embedding provider dependency** — Items 2 and 4 require embedding provider. All gates degrade gracefully when unavailable.

## Definition of Done

- [ ] store_memory accepts and passes through source parameter
- [ ] Min-length and near-duplicate gates reject invalid entries
- [ ] Constitution is import-only (write-protected)
- [ ] Ranking weights updated (0.30/0.15/0.35/0.15/0.05)
- [ ] record_influence_by_content tool works with chunking
- [ ] Constitution entries appear in search_memory
- [ ] Injection limit defaults aligned to 15
- [ ] reviewer_feedback_summary in Phase Context injection
- [ ] Review learnings trigger at 1+ iterations
- [ ] All callers pass correct source
- [ ] All 14 influence tracking locations migrated
- [ ] All tests pass (new + regression)
