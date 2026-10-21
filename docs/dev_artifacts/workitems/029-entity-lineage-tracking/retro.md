# Retrospective: 029-entity-lineage-tracking

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 35 min | 4 (3 spec + 1 phase) | 6 blockers resolved across iters 1-2. Phase-reviewer approved on first pass. |
| design | 95 min | 8 (3 design + 5 handoff) | Major architectural pivot at design iter 1 (DB-centric over file-based). Design approved iter 3/5. Handoff hit cap at 5/5. |
| create-plan | 135 min | 10 (5 plan + 5 phase) | Both reviewers hit caps. All blockers resolved by iter 1; iters 2-5 refined parallelism, venv edge cases, ordering. |
| create-tasks | 85 min | 10 (5 task + 5 chain) | Both reviewers hit caps. Specificity cascade pattern: blocker counts escalated per iteration (0-1-7-5-3). |
| implement | 265 min | 5 (3 fix rounds + validation) | Key fixes: AC-5/I7 rendering, O(N^2) pattern, silent error swallowing, depth guards, path containment. 184 tests passing. |

**Totals:** 10 hours 50 minutes. 37 review iterations across 5 phases. 32 pre-implementation iterations. 30 files changed, 8,459 insertions.

---

### Review (Qualitative Observations)

1. **Format assumption mismatches recurred across spec AND design phases** — Spec phase had 6 blockers from wrong assumptions about brainstorm ID structure, file extension conventions, and backlog marker strings. Design phase repeated this with marker format distribution and wrong MCP registration target. No one read real files before specifying format expectations.

2. **Task review exhibited a specificity cascade** — Blocker counts escalated per iteration (0-1-7-5-3 at cap) rather than converging. Each resolved ambiguity revealed adjacent underspecification one abstraction level deeper: method signature -> parameter contract -> DDL -> CHECK constraint SQL -> CTE bind parameter semantics.

3. **AC-5 depends_on_features rendering was silently absent** — Backfill scanner stored metadata correctly but `_format_entity_label` in server_helpers.py ignored the metadata field entirely. Gap was invisible until implementation iter 2 — the storage layer satisfied the data model but the rendering layer did not.

---

### Tune (Process Recommendations)

1. **Add Prior Art Verification to specify** for features that parse existing file formats. Read 3+ real examples before specifying format expectations. (Confidence: high — 3rd occurrence across features 022, 023, 029)

2. **Require complete DDL, signatures, and worked examples in plans** for SQL/API-heavy features. Plan-reviewer should treat absence as a blocker. (Confidence: high)

3. **Add design completeness pre-flight checklist** before handoff review: test strategy, TD alternatives, dep sets, merge semantics. Would reduce handoff iterations from 5 to 2-3. (Confidence: medium)

4. **Add AC traceability task** for features with separated storage and rendering layers. Map each AC to storage AND rendering functions. (Confidence: medium)

5. **Budget 30-40 pre-implementation review iterations** for multi-integration MCP server features. Frame reviewer caps as expected behavior, not quality failure. (Confidence: high)

---

### Act (Knowledge Bank Updates)

**Patterns:** INSERT OR IGNORE for idempotent registration, recursive CTE + depth guard for tree registries, uv bootstrap + PYTHONUNBUFFERED=1 for MCP stdio servers, topological backfill ordering.

**Anti-patterns:** Designing parsers against assumed conventions without reading real files (3rd occurrence), two-layer architectures with no AC traceability, Python-side recursion against relational DB for tree traversal.

**Heuristics:** Multi-integration MCP budget (30-40 iterations), specificity cascade signal (escalating blockers), design handoff pre-flight checklist, AC traceability pass for two-layer architectures.

---

## Raw Data

- Feature: 029-entity-lineage-tracking
- Mode: standard
- Branch lifetime: same-day (2026-02-27)
- Total review iterations: 37
- Pre-implementation iterations: 32
- Implementation iterations: 5
- Tests at completion: 184
- Files changed: 30 (+8,459 / -6)
- Reviewer caps hit: 5 of 6 reviewer sequences
- Key architectural decision: DB-centric (SQLite WAL + MCP tools as exclusive write interface)
