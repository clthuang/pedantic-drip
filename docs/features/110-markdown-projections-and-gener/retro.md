# Retrospective: Feature 110 — Markdown Projections and Generalized Guards

## AORTA Analysis

### A — Actions / O — Observe (Quantitative Metrics)

| Phase | Iterations | Notes |
|---|---|---|
| brainstorm | 1 | Reused parent project PRD (P003) — instant transition |
| specify | 5 (3 spec-reviewer cap-3 + 2 phase-reviewer) | 4 iter-1 blockers + 8 warnings + 3 iter-3 NEW empirical blockers (pathlib.match 3.12 gap, phase_events CHECK violation, NOT NULL columns) all fixed inline post-cap |
| design | 3 (2 design-reviewer + 1 phase-reviewer) | 6 iter-1 blockers + 3 iter-2 factual blockers (fix_actions symbol mismatch, archive_entity contradictory signatures, TD-10 two-format reality) — all resolved in rev 3 |
| create-plan | 4 reviewer dispatches | plan-reviewer iter 1 found 3 blockers (text hallucinations + TDD-order) + 7 warnings; task-reviewer iter 2 found 5 more blockers (Task 9.2 sentinel, Task 8.2 filename, Task 11.3 MCP invocation, Task 2.2 ordering, Task 12.1 step number) |
| implement | 15 Group-level subagent dispatches (worktree-isolated) | 1 merge conflict (test_audit_writes.py — Group 12 + Group 15 both created the file) — manually resolved by combining scaffolds + AST walks + TD-7b lint |

**Cumulative reviewer iterations across pre-implement phases: 12+** (5 specify + 3 design + 4 create-plan).

**Final feature-110-scoped test count:** 63 passing, 1 skipped, 0 failed.
**Broader suite at merge:** 2619+ tests passing across entity_registry, doctor, workflow_engine, mcp.

### R — Review (Qualitative Observations)

1. **SUT-verification heuristic from feature-109 KB paid dividends.** Spec §1.1 was empirically grounded from session-start (codebase-explorer dispatched before iter-1 spec draft), yet iter-3 STILL caught 3 NEW blockers (pathlib.match Python 3.12 gap, phase_events CHECK violation post-12, NOT NULL columns). The heuristic doesn't eliminate iter-3 catches but it prevents them from being structural-impossibility blockers — these were all factual-correction blockers fixable inline.

2. **Empirical-correction-during-implementation pattern.** Multiple Groups discovered that design assumptions were wrong (Group 9 found `fnmatch` row 5 actually returns `True` not `False`; Group 14 found phase_events JOIN is on `type_id` not `entity_uuid`). Implementers corrected and documented inline rather than escalating — the pattern works when the correction is mechanical.

3. **Worktree-isolated parallel dispatch had one merge conflict, easily resolved.** Both Group 12 and Group 15 independently created `test_audit_writes.py` (because neither had visibility into the other's worktree). The conflict was clean (different sections of the file) and resolved by combining. Cost: ~5 minutes manual merge. Compare to serial dispatch which would have added ~10 minutes of total wall-clock — net win.

4. **TDD discipline was deferred to implementer-skill enforcement.** The plan-reviewer iter 1 called out systematic implementation-before-tests ordering in every Group. Fix: added a TDD preamble to tasks.md stating "implementer-skill must execute RED-tests-first regardless of task list order." Implementers honored this — most reports mentioned writing RED tests first. Pragmatic compromise: documentation gate vs. wholesale task reordering.

5. **~500 test fixtures need post-feature cleanup.** Group 2 Task 2.0 introduced `register_entity` strict-format check (`^\d+-.+`). ~500 test sites use non-conformant entity_ids (e.g., `'test-bs'`, `'parent-bs'`). Resolution: env-gated opt-out (`PD_REGISTER_ENTITY_STRICT_ID_FORMAT=0`) in conftest.py allows existing tests to pass while production callers get strict-by-default. Follow-up: migrate fixtures, remove opt-out.

### T — Tune (Process Recommendations)

1. **Promote the "factual blocker remap" pattern as a tune.** Iter-3 of spec found 3 NEW factual blockers introduced by iter-2 fixes (pathlib.match, phase_events CHECK, NOT NULL). All were mechanical corrections per empirical evidence — they didn't warrant an iter-4 adversarial review. Applying inline + documenting in `.review-history.md` worked. Add this as an explicit heuristic: "If iter-N blockers are factual corrections per empirical evidence (file:line, schema introspection, library docs), fix inline without an iter-N+1 adversarial pass."

2. **Capture the worktree-conflict-prevention check.** Future parallel implementer dispatches should declare which files they create. The orchestrator can flag conflicts pre-dispatch. Or: implementer prompts should include "if this file exists in your worktree, append; do not overwrite."

3. **Document test fixture migration as a follow-up feature.** ~500 register_entity sites with non-conformant entity_ids is real tech debt. File a follow-up: migrate fixtures to `^\d+-.+` form, remove the conftest opt-out. Until done, AC-8.2 1:1 invariant for test-suite entities is opt-out-mode-only.

### A — Act (Knowledge Bank Updates)

Knowledge bank updates added to `docs/knowledge-bank/{patterns,anti-patterns,heuristics}.md`:

- **Pattern:** Factual-Blocker-Remap At Cap (no iter-N+1 needed for empirical corrections).
- **Pattern:** Worktree-Isolated Parallel Dispatch With Manual Conflict Merge (cost-acceptable when conflicts are file-scope additions).
- **Anti-Pattern:** Strict-Format Validation Without Fixture Migration Plan (~500 test fixtures broken; opt-out env-var works but accrues debt).
- **Heuristic:** TDD Discipline Via Preamble (not task reordering) for large multi-Group features.

## Summary

Feature 110 delivered the full F4 + F7 + F8 scope (markdown-as-projection + generalized data-file guard + entity_display table) across 15 Groups with ~70 tasks. 12+ pre-implement reviewer iterations across 3 phases converged with all blockers resolved. Implementation was parallel-where-possible (Groups 0/14, 8/9, 12/15 ran in parallel worktree-isolated batches), with 1 trivially-resolved merge conflict. Final state: 63 feature-tests pass, schema migration 13 in place, hooks/scripts/MCP all wired through projection-only path.

**Final commit on `feature/110-markdown-projections-and-gener`:** 1700+ lines of production + test code across `database.py`, `workflow_state_server.py`, `data_file_guards/`, `pd_state_diff.py`, `parse_backlog_md.py`, `compare_backlog_projection.py`, plus 133 file removals from index.

**Tooling friction:** Codex CLI broken (ENOENT) — all reviewer dispatches used pd:Task per codex-routing fallback protocol.
