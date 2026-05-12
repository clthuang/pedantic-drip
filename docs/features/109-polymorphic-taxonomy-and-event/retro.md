# Retrospective: Feature 109 — Polymorphic Taxonomy and Event-Sourced State

## AORTA Analysis

### A — Actions / O — Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| brainstorm | 4 s | 1 | Reused parent PRD `docs/projects/P003-entity-system-redesign/prd.md` — no fresh brainstorm |
| specify | 29 min | **5** (3 spec-reviewer + 2 phase-reviewer) | 9 blockers + 17 warnings cumulative; iter-2 SUT-verification unmasked 5 NEW blockers |
| design | 23 min | **4** (3 design-reviewer cap-3 + 1 phase-reviewer) | 2 cumulative blockers + 5 warnings resolved inline in rev 4; cross-phase spec patch FR-4↔AC-4.4 |
| create-plan | 30 min | **5** (2 plan-reviewer + 1 task-reviewer + 1 phase-reviewer + plan rev 5) | 6+1 plan blockers, 5 task blockers, 3 phase blockers cumulative; Group 11 REMOVED into Group 3 mid-flight |
| implement | hours | not captured in .meta.json | ~16 Groups, ~72 atomic tasks; direct-orchestrator mode; 8+ commits; 46 files / +9,728/-709 LOC |

**Cumulative reviewer iterations across pre-implement phases: 14** (5 specify + 4 design + 5 create-plan). Within budget per CLAUDE.md "1-2 target / cap-3" applied per reviewer role.

Final test count: 2772 passed / 3 skipped / 0 failed in feature-109-scoped suite.

### R — Review (Qualitative Observations)

1. **SUT-verification at spec iter-2 acted as a force-multiplier blocker generator** — Iteration 1 produced 4 blockers from prose-level review; iteration 2 (with codebase-explorer/grep) produced 5 entirely new blockers (parallel `enforce_immutable_type_id` trigger at 6 sites, FTS5 column dependency, `mcp/` vs `mcp_server/` path, Python-caller audit gap, SQL-trigger feasibility). All five were structural correctness issues invisible to non-empirical review.
   - Evidence: `.review-history.md:49-54` — iter-2 blockers all annotated "verified via codebase grep".

2. **Cross-phase consistency patches saved an entire backward-travel cycle** — Design-reviewer iter 1 flagged FR-4 body vs AC-4.4 contradiction (broad UPDATE vs status-only); resolved by editing spec.md in-place during design phase rather than backward-travel to specify.
   - Evidence: `.review-history.md:160-162`.

3. **Workspace-scoping bugs propagated across phases as the same defect class** — Design iter-2 caught `get_entity(type_id=...)` being cross-workspace-ambiguous; iter-3 caught `append_phase_event` missing `workspace_uuid` plumbing (same root cause, different call site). The pattern recurred because design iter-2 fix was point-applied, not class-applied.
   - Evidence: `.review-history.md:207-208` vs `.review-history.md:236-237`.

4. **Codex routing fallback was friction-free but invisible** — Codex CLI unavailable at session start; all reviewer dispatches fell back to pd:Task per codex-routing protocol. Outcome was clean but the friction was uncaptured outside the explicit notes in iter-1 spec review header.

5. **Implementation surfaced 2 design-time-unknown failure modes** — (a) WAL read-snapshot under concurrent migration (Groups 1+2, mitigated via `PRAGMA table_info` idempotency); (b) cross-table trigger problem in Groups 6+7 where `workflow_phases` triggers referenced `entities` — required dynamic capture/recreate cycle not in plan.

### T — Tune (Process Recommendations)

1. **Mandate codebase-explorer dispatch before spec iter-1 for schema-migration features** (Confidence: high). Add an explicit "Pre-spec SUT verification" task to `specifying-feature/SKILL.md` for any feature touching DB schema, triggers, or virtual tables. Cost saved: ≈1 spec-review iteration per schema-migration feature.

2. **Promote workspace_uuid as a required parameter contract in entity-touching helpers at design-review time** (Confidence: high). Add an entry to `plugins/pd/agents/design-reviewer.md` checklist: "For any helper that queries or mutates `entities`/`phase_events` by `type_id`, verify `workspace_uuid` is in the parameter list AND in the WHERE clause."

3. **Track Codex availability as a session metric, not just a routing fallback note** (Confidence: medium). Add a `tools_friction` array to feature `.meta.json` capturing entries like `{"tool":"codex","status":"unavailable","fallback":"pd:Task","at":"specify_iter_1"}`.

4. **Add "live-DB pre-migration probe" gate task to implementing skill for schema features** (Confidence: medium). Promote the deferred Task X.3 + stale-test cleanup into a follow-up feature tagged `tech-debt:entity_type-column-cleanup`.

5. **Add atomic-class-fix discipline to design-reviewer prompt** (Confidence: medium). After applying any fix, grep for sibling sites of the same anti-pattern.

### A — Act (Knowledge Bank Updates)

Updates appended to `docs/knowledge-bank/{patterns,anti-patterns,heuristics}.md`:
- **Patterns:** SUT-Verification Pass, Cross-Phase Spec Patch, Skip-Marker Strategy
- **Anti-patterns:** Point-Fix Workspace-Scoping, Static Caller-Count Drift, Hardcoded Schema Column Lists, Deferred Failures Without Backlog
- **Heuristics:** Pre-Spec Grep for Schema Migrations, Skip-Marker for 10+ Groups, Cap-3 With Inline Resolution = Clean Approval, 5+4+5 Budget for Multi-Group Schema Migrations, Tooling Friction in .meta.json

## Summary

Feature 109 was a textbook front-loaded-review migration: 14 cumulative pre-implement reviewer iterations across 3 phases, all within cap-3 budgets per reviewer role, producing a clean ~72-task implementation with 2772 passing tests and zero failures. SUT-verification at spec iter-2 acted as the decisive force-multiplier — it generated 5 structural blockers prose review could not have detected.

**Final state:** 46 files changed, +9,728/-709 LOC on `feature/109` vs `develop`. Notable friction: Codex CLI unavailable (medium); WAL concurrent-migration mitigation (Groups 1+2); cross-table trigger problem (Groups 6+7); 19→0 skip-marker lifecycle.
