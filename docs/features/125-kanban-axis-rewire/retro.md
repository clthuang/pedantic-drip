# Retrospective: 125-kanban-axis-rewire

**Date:** 2026-07-13 · **Facilitator:** pd:retro-facilitator (opus, read-only); retro.md written by the orchestrator · **Verdict:** shipped clean — 0 production defects past deepener/battery/360°; the review loop's residual blind spot named (cross-contract collisions).

**Briefing verification:** every quantitative briefing figure re-derived EXACT by the facilitator — the first zero-correction briefing since the corrections streak began (that streak closes at 5: 130→126→122→128→127, per 127-retro:5's verified membership; rule: corrections to the retro's OWN briefing/tallies). The one figure the read-only facilitator could not verify (commit count) was git-verified by the orchestrator before this file was written: `git rev-list ef6abbe5..HEAD` = 11.

## Activities

| Layer | Rounds | Blockers | Note |
|---|---|---|---|
| Spec skeptic (opus, fresh per round) | 3 (cap) | 5 (2+2+1) | i3's blocker fixed post-cap, gate-verified |
| Specify gate (sonnet) | 1 | 0 | 1 warning |
| Design skeptic (opus, fresh per round) | 3 (cap) | 4 (2+2+0) | i3 approved |
| Design gate (sonnet) | 1 | 0 | 2 warnings |
| Plan-reviewer (opus) | 1 | 0 | approved i1 |
| Task-reviewer (sonnet) | 2 | 2 | i1: 1 INTEGRITY + 1 citation gap |
| Relevance-verifier (sonnet) | 1 | 0 | first-round approval |
| Battery (opus/sonnet/opus) | 1 | 0 | **11th consecutive iteration-1-clean** (127-retro:28 verified the 10th link-by-link) |
| 360° (shell) | 1 | 0 | one concurrent-run validate.sh transient; 2 isolated re-runs clean |

**Total: 11 blockers** — campaign trajectory 131:7→118:5→129:9→119:2→130:3→121:10→120:1→126:12→122:3→128:12→127:10→**125:11** (third-highest, sole rank-3, behind the twin 12s).

**Implement:** 3 tasks (aliases `047eac40`, UI rewire `4d3746dc`, orchestrator QA `99f48731`) + 13-test deepening (`c26bf20e`, zero production findings) + battery absorptions (`1e023b2f`). Tests: ui 230→**249** (+6 D7, +13 deepener); full scope 3718→**3737** passed / 3 skipped — every delta accounted. 11 commits.

**Fresh vs self-inflicted:** ~4F/7S (~64% self-inflicted; swing cases documented in the facilitator analysis — spec-i2-B1 and design-i2-B2 defensible either way). The self-inflicted mass = the half-sweep cluster (spec i3, design i2 ×2) + both create-plan blockers. Consistent with the standing finding: self-inflicted count tracks review-loop friction, not shipped danger.

## Outcomes

Read-side-only cluster-7 delivery: UI grouped/rendered by `execution_status`/`pipeline_phase` through two ADDITIVE `list_workflow_phases` aliases (`get_workflow_phase` and its ~18 non-UI callers byte-untouched); one shared `resolve_execution_status` helper + `LEGACY_VALUE_REMAP` unifies the legacy display remap across all three surfaces; 8→7 columns with `ready` third; unknown values bucket loud (one `!r`-escaped stderr warning per row) instead of silently dropping. SC2 exact: zero production `kanban_column` tokens; tests-side survivors all physical-column seed machinery. Every bridge dated to 132 (aliases, remap, WARN-format churn, seed tokens).

## Reflections

**R1 — Cross-contract collision is the residual review blind spot (signature, novel).** Two of the six implementer-adjudicated deviations were collisions between two independently-pinned contracts in the SAME artifact set, each internally sound, that surfaced only at execution (the D1 collision, pinned at design i1, survived SIX subsequent review passes — design i2/i3, design gate, plan, task, relevance; the D7 one, pinned later, survived fewer): (a) D1's verbatim code block carried `kanban_column` in its own comment/docstring inside SC2's grep scope — three design rounds pinned both without running one against the other; (b) D7's `:205-214 NO EDIT` (behaviorally correct) vs SC2's unconditional tests-side clause (the test's name/docstring became factually false post-D2). Reviewers verify each contract's internal soundness; nobody ran the spec's grep-SC against the design's pinned prose. Both reachable by one mechanical grep. → Tune codified (Actions).

**R2 — Implementer as de-facto last reviewer: healthy flagging, concerning coverage.** All six deviations were FLAGGED (none silent) and orchestrator-adjudicated. Three were D7 inventory gaps execution exposed — canonical instance: a mock targeting `get_workflow_phase` cannot fail a route D4 made no longer call it. Heuristic worth keeping: **re-derive the mock inventory from the POST-rewire call graph.**

**R3 — The parallel-review integrity countermeasure HELD.** After task-reviewer i1's incident (artifact changed mid-review; a citation preceded its record), the countermeasure — absorb only after ALL parallel reviewers return; commit before re-review; a verdict is recorded in .review-history.md BEFORE being cited — held for the rest of the feature: relevance r1 verified it in the committed tree; the battery extracted all three verdicts before any absorption. No second incident.

**R4 — Half-sweep re-fired 3× (spec i3, design i2 ×2), 100% gate-caught / 0% prevented.** Each ran the sweep from memory instead of from grep output. The standing gap remains execution, not rule coverage.

**R5 — The adversarial loop again designed the winning architecture, this time at low footprint cost.** Design i1's NO-RENAME decision killed a collection-time-ImportError failure class outright; the zero-occurrence detail path let the spec's transient SC2 exemption be reverted upward. Unlike 127's route-D cascade, the read-only bridge posture kept the downstream tax near zero.

## Themes

1. Internal soundness is well-covered; collisions BETWEEN pinned contracts are not — invisible until execution unless mechanically checked.
2. ~64% self-inflicted friction, zero shipped defects — the loop pays for itself in architecture (R5), not just defect-catching.
3. Read-side-only staging (additive aliases + display remap + dated bridges) is a clean blast-radius pattern for the 132 cutover to reuse.

## Actions

| # | Action | Disposition |
|---|---|---|
| A1 | Backlog #063 quality-reviewer watch: n=2 = 4/6 actionable | continue; hold for n≥3 before tuning |
| A2 | Cross-contract collision check | **CODIFIED** — CLAUDE.md guardrail added this commit: when a spec pins a grep/scan-based SC and a design pins verbatim content inside that scan's scope, run the SC's scan against the pinned content (including its comments/docstrings) before approving |
| A3 | Consolidate duplicate `_seed_workflow_row` (test_app.py vs test_deepened_app.py, divergent signatures) into conftest.py | **FILED** backlog #071 (pre-existing, out of 125 scope) |
| A4 | 132 handoffs: physical column drop/rename; remap deletion; `[board] WARN:` format churn (S4 declined here — D2 pins the format); seed-token removal | recorded here + in CHANGELOG entry |
| A5 | Commit count git-verification | **DONE** pre-write: 11 |
