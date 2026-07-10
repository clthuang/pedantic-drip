# PRD: Workflow Rebuild — Lean Canonical Workflow + Express Mode

## Status
- Created: 2026-07-10
- Last updated: 2026-07-10
- Status: Draft
- Problem Type: none
- Archetype: improving-existing-work
- Entity: `brainstorm:20260710-153500-workflow-rebuild`
- Track: 1 of 2 (companion: `20260710-153600-entity-db-redesign.prd.md`) — **ships after the DB track**

## Problem Statement

The workflow's implementation is a 2024-era exoskeleton built to babysit weaker models. Its essence — staged uncertainty reduction with research-grounded gates, narrow-purpose agents, and independent review — is sound; the machinery wrapped around it costs tokens, wall-clock, and reading time without buying quality, and the repo's own retrospective evidence says the review loops actively don't work.

### Evidence
Verified 2026-07-10 (verbosity census + dispatch-count analysis + the repo's own artifacts):

- **Volume:** ~74,000 words of orchestration prose (8,181 command lines + 5,616 skill lines). In the four artifact-producing commands (`implement`, `create-plan`, `design`, `specify`), **75–80% is defensive scaffolding + duplicated boilerplate**, not intent. `implement.md`'s review phase spans lines 210–1095 (~78% of the file).
- **Duplication:** the reviewer JSON return schema is restated **62× across 23 files** (3× per reviewer per command: fresh / resumed / final-validation dispatch). `resume_state` machinery: **239 occurrences**. Codex-routing preamble copy-pasted in 11 files. 58 per-command YOLO override blocks. The one factored-out counter-example (`workflow-transitions` validateAndSetup/commitAndComplete) proves the DRY alternative works.
- **Dispatch cost:** a small feature run = **33 subagent dispatches minimum, ~85 at caps**. `implement`'s happy path alone is ≥8 reviewer dispatches — a mandatory full 4-reviewer re-validation runs even when everything passed first time (`implement.md:250,910`).
- **The loops don't earn it (repo's own artifacts):** `docs/pd-audit-findings.md:13-39` rates the reviewer loops **Critical**, citing self-correction research (DeepMind: 7.6% of wrong answers fixed vs 8.8% of right answers broken; Self-Refine: diminishing returns after 1–2 iterations) and recommends removing the loops. Feature 006: **38 review iterations for a documentation-only feature** (`heuristics.md:293`). A reviewer finding one nitpick per iteration until the circuit breaker fires with zero correctness issues resolved (`anti-patterns.md:419`). Final-validation counting against the iteration cap means **the legitimate completion path can trip the circuit breaker** (`anti-patterns.md:645`).
- **Complexity managing complexity:** the resume/delta/compaction apparatus exists to manage the token cost of the loop design itself — guards for the machinery, not for any model failure.

## Current State Assessment

| Aspect | Today | Consequence |
|---|---|---|
| Phase commands | 1,000+ line procedural scripts | intent buried in scaffolding; drift between copies |
| Review per phase | skeptic + gatekeeper pairs, iterate to cap (3–5) | 33–85 dispatches/feature; nitpick loops; breaker misfires |
| Implement QA | 4 prose reviewers × up to 3 iterations + mandatory re-validation | happy path pays 2× full review |
| Secretary | 8-step DISCOVER→DELEGATE pipeline, 11 lookup tables | hand-built router for a task the model does natively |
| Resilience | resume_state / delta guards / compaction detection / JSON retry ladders | 2024-era defenses; largest single verbosity source |
| YOLO | 58 per-command override blocks | same rule restated everywhere |

## Goals

1. Preserve the workflow's essence: research-grounded, uncertainty-reducing phases; narrow-purpose agents; independent QA + review closing each cycle (user R1.2).
2. Cut the implementation to what a frontier model needs: contracts over scripts, one review moment per gate, execution over prose-review.
3. Add an express lane for small / low-uncertainty tasks without forking the tracking model (user R1.3).

## Success Criteria

- [ ] Orchestration prose ≤ 10,000 words total across commands + skills (from ~74k) — verified by `scripts/verbosity-census.sh` (persisted pre-work, see Next Steps; pins the exact grep pattern per metric and whether test files count).
- [ ] Small feature, deep mode: ≤ 12 subagent dispatches; express mode: ≤ 4 (from 33–85).
- [ ] Review pattern per gate: one pass + at most one fix round, then user escalation — no iteration-to-cap loops; **zero circuit-breaker trips on happy paths**.
- [ ] Reviewer return schemas defined in exactly one place each (agent files); the census script's schema-restatement pattern over `plugins/pd/commands/` = 0.
- [ ] All model-independent guards still present: prompt-injection hardening, data-file single-writer, MCP degradation ladders, prerequisite fail-fast, one bounded breaker that final validation does NOT count against.
- [ ] `./validate.sh` green after the rewrite (incl. doc-drift gate counts, hooks contract, codex-routing coverage list).

## User Stories

### Story 1: Deep-work feature
**As a** developer building a risky feature **I want** the full 6-phase pipeline with research agents and an independent reviewer at each gate **So that** decisions stay grounded and blindspots are caught — at ≤12 dispatches instead of 33–85.
**Acceptance:** all six phases produce their artifacts; each gate = one reviewer pass (+ ≤1 fix round); implement pairs an execution-verifying QA agent with one adversarial code review.

### Story 2: Express fix
**As a** developer making a small, low-uncertainty change **I want** triage to route me through mini-spec → implement → one combined QA+review pass **So that** a one-file fix doesn't pay six phase gates.
**Acceptance (contingent on DB-track OQ-6):** express run ≤ 4 dispatches; a mini-spec is recorded as an event; skipped phases recorded; same entity tracking as deep mode. Minimal event fields this track needs from OQ-6: a `mini_spec` event (entity ref + spec text payload) and per-phase `skipped` events — assertable once OQ-6 lands.

### Story 3: Triage with override
**As a** user **I want** the secretary to assess uncertainty/risk and recommend deep vs express — and to accept my override in both directions, including escalating express → deep mid-flight **So that** mode selection is a default, not a cage.
**Acceptance:** triage states its mode rationale in one short block; `--deep`/`--express` force flags work; mid-flight escalation carries the mini-spec forward as brainstorm input.

### Story 4: YOLO run
**As a** user running autonomously **I want** one global YOLO rule (auto-answer prompts, halt on safety keywords) defined once in workflow-transitions **So that** behavior is uniform and not re-specified per command.
**Acceptance:** per-command YOLO blocks deleted; the global rule covers every AskUserQuestion site; safety hard-stops unchanged.

## Requirements

### Functional
- **FR-1 (R1.1 — single entry):** `/pd:secretary` remains the unified entry point, slimmed to *triage-that-selects-mode*: assess uncertainty, risk, and blast radius → route to deep mode, express mode, or a specialist. Replaces the 8-step pipeline + 11 lookup tables with a short routing contract.
- **FR-2 (R1.2 — canonical spine):** Deep mode keeps brainstorm → specify → design → create-plan → implement → finish, each phase producing its artifact and reducing uncertainty from boundaries to details. Narrow-purpose research agents (codebase-explorer, internet-researcher, skill-searcher, advisors) remain the anti-context-pollution mechanism.
- **FR-3 (contracts, not scripts):** Each phase command is rewritten as a contract — inputs, output artifact, definition of done, constraints — targeting 200–500 words. Skills carry knowledge/criteria, not step-by-step procedure. Shared mechanics stay factored in `workflow-transitions` (the pattern that already works).
- **FR-4 (one review moment per gate):** Each phase boundary gets ONE independent reviewer whose contract covers both artifact quality and handoff readiness (merging today's skeptic + gatekeeper). Protocol: one pass → at most one fix round → escalate remaining issues to the user. No iteration-to-cap.
- **FR-5 (implementation QA, R1.2):** Implement pairs the implementer with (a) an independent QA agent doing **execution-based verification** — run the tests, drive the affected flow — and (b) one adversarial code-review pass. The mandatory second full-review round is deleted; the circuit breaker remains but final validation does not count against it.
- **FR-6 (schema single-source):** Reviewer return schemas live only in the reviewer agent files; dispatching commands reference the agent.
- **FR-7 (R1.3 — express mode):** Express path = inline mini-spec (recorded as an event) → implement → one combined QA+review pass → finish. Same entity/state tracking as deep mode; skipped phases recorded via the DB track's event model. **Acceptance is blocked-until DB PRD OQ-6 resolves** (representation owned there); the seam contract this track requires: `mini_spec` + `skipped` event types.
- **FR-8 (global YOLO):** One YOLO override rule in `workflow-transitions`; per-command blocks deleted. Safety hard-stops (merge conflict, review failure, missing prerequisites) unchanged.
- **FR-9 (deletion inventory):** Remove: `resume_state` machinery (~239 refs), delta-size guards (16), context-compaction detection (~12), `Files read:` confirmation ritual (~38), LAZY-LOAD warnings (13), JSON parse/retry ladders, per-command schema restatements (~62 sites across 23 files), the mandatory post-pass re-validation round, per-command YOLO blocks (58). Counts are from the 2026-07-10 session sweep; the census script (Next Steps) pins each metric's exact pattern and scope (test files in/out) — the pinned numbers become the regression baseline, superseding these approximations.
- **FR-10 (guards kept):** Prompt-injection hardening in dispatches, `data-file-guard` single-writer, MCP degradation ladders, prerequisite fail-fast (one line, not 4-level message ladders), one bounded circuit breaker.

### Non-Functional
- **NFR-1:** `validate.sh` stays green throughout — the rewrite updates its hard-coded contracts in the same change: codex-routing coverage allowlist ("Codex Reviewer Routing exclusion" expected-files list), hooks.json registration contract, and doc-drift gate README counts when components change (CLAUDE.md docs-sync checklist applies).
- **NFR-2:** Docs sync — README/README_FOR_DEV component tables and counts updated with the rewrite (enforced by the doc-drift gate).
- **NFR-3:** Each phase's reviewer dispatch remains a separately-contexted subagent (context isolation preserved even as counts drop).

## Edge Cases & Error Handling

| Scenario | Expected Behavior | Rationale |
|----------|-------------------|-----------|
| Triage misroutes (too shallow/deep) | User override flags both directions; triage states rationale so misroutes are visible | mode is a default, not a cage |
| Express task reveals hidden depth | Escalate to deep mid-flight; mini-spec becomes brainstorm input; event records the escalation | no restart penalty |
| Reviewer rejects twice | Stop and escalate to user with the open issues — never loop further | evidence: loops past 1–2 iterations degrade |
| MCP down mid-phase | Existing degradation ladder (proceed, reconcile later for non-state ops; state mutations fail loud per DB track FR-10) | model-independent guard kept |
| YOLO safety keyword hit | Hard stop, report — unchanged | safety boundary |

## Constraints

### Behavioral (Must NOT do)
- No reintroduction of per-command schema restatements, resume machinery, or double-review pairs — Rationale: that's the regression this PRD exists to prevent; the census numbers are the regression test.
- Must not change the phase vocabulary — Rationale: DB track models it; seam stays single-sourced.

### Technical
- Depends on the DB track for all state writes (events, skipped-phase recording) — **DB track ships first**; phase vocabulary is frozen so DB work is already unblocked.
- Circuit breaker: final validation excluded from the count (fixes `anti-patterns.md:645`).

## Approaches Considered

| Approach | Verdict | Why |
|---|---|---|
| Collapse 6 phases → 3 (Shape/Build/Ship) | **Rejected (user R1.2)** | The spine IS the uncertainty-reduction model; the cost problem is the implementation, not the phase count |
| Keep skeptic + gatekeeper pairs, lower caps | Rejected | Evidence: paired loops produce nitpick churn and breaker misfires; one merged reviewer contract covers both questions |
| Prose-review loops for implement QA | Rejected | Self-correction research + repo retros; execution-based verification catches what prose review doesn't |
| Delete secretary, use raw model routing | Rejected (user R1.1) | Single triage entry is a requirement; slim it, don't remove it |

## Strategic Analysis

### Pre-Mortem Advisor
- **Core Finding:** The likeliest failure is deleting a guard that was quietly load-bearing, or express mode under-gating a risky change.
- **Analysis:** The review's guard classification separates model-independent guards (keep) from weak-model-era scaffolding (delete), but a few deletions interact with infrastructure (e.g., JSON retry ladders also masked MCP hiccups; validate.sh has hard-coded contracts that a command rewrite silently trips). Express mode's risk is a mis-scored triage sending a security-surface change through the shallow path.
- **Key Risks:** guard misclassification; triage under-scoring; validate.sh contract drift mid-rewrite.
- **Recommendation:** rewrite one phase command first (specify — smallest) as a pilot; run a real feature through it before converting the rest. Triage rubric must treat security-touching paths as deep-mode-mandatory. Update validate.sh contracts in the same commits as the commands they reference.
- **Evidence Quality:** strong for the verbosity census (grep-measured) and dispatch figures (derived from dispatch-graph analysis, not instrumented runs); moderate for the guard-interaction risk (inferred).

### Opportunity-Cost Advisor
- **Core Finding:** Every feature built before this ships pays the 33–85-dispatch tax; the rewrite is mostly deletion, so its cost is low and front-loaded.
- **Analysis:** The repo's own history quantifies the ongoing cost (38 iterations for a docs feature; 3–5 iterations/phase average that a prior improvement cycle only capped, not fixed). Deletion-dominant work carries low regression risk relative to greenfield. Sequencing after the DB track delays the payoff but avoids writing state plumbing twice.
- **Key Risks:** doing this before the DB track would double-touch every state write site.
- **Recommendation:** hold sequencing (DB first); extract nothing forward except the pilot-phase experiment if desired.
- **Evidence Quality:** strong.

## Non-Goals

- No new phases, reviewer roles, or state vocabulary — Rationale: R1.2 preserves the spine; DB track owns state.
- Not rewriting domain-knowledge skills (DS/game/crypto packs) — Rationale: knowledge, not orchestration; not part of the verbosity problem.
- Not removing the secretary — Rationale: R1.1.

## Out of Scope (This Release)

- Codex-routing preamble consolidation vs deletion — decided at design (OQ-4); the toggle is currently disabled either way.
- Reviewer-model tier re-assignment (opus/sonnet mapping) — revisit after dispatch counts drop.

## Risks

| Risk | Mitigation |
|---|---|
| Load-bearing guard deleted | Pilot one phase command end-to-end before mass conversion; guard-classification table from the review is the checklist |
| Express under-gates risky change | Triage rubric: security surface / migration / multi-file blast radius ⇒ deep mandatory; user override logged as event |
| validate.sh contract drift | Update codex allowlist, hooks contract, doc-drift counts in the same commit as each component change |
| Census regression over time | Success criteria include re-runnable census greps; consider a lightweight word-count line in the doc-drift gate later |

## Open Questions

1. Express-mode audit minimum: mini-spec event only, or also a one-paragraph design note for non-trivial expresses?
2. Triage rubric signals: estimated diff size, novelty, blast radius, security surface — which are load-bearing, and what's the default when uncertain (recommend: deep)?
3. Do brainstorm and specify merge into one "shape" phase in deep mode? (R1.2 spirit-compatible either way; decide at design.)
4. Codex-routing preamble: factor into workflow-transitions once, or drop entirely while the toggle is disabled?
5. Single-reviewer-per-gate vs false-reviewer-claims (evidence from feature 131 retro, 2026-07-10): FR-4 collapses skeptic+gatekeeper into one reviewer pass per gate, but 131's spec loop absorbed a FALSE reviewer claim (backfill_project_ids "writes dropped project_id" — refuted at database.py:7818-7824) that only a SECOND independent dispatch caught. Before design: decide how one-reviewer-per-gate preserves that self-correction (e.g., reviewer must cite verifying file:line for factual claims — now a CLAUDE.md guardrail — or the next phase gate doubles as the independent recheck).

## Next Steps

1. DB track (`20260710-153600-entity-db-redesign.prd.md`) proceeds first via `/pd:create-project`.
2. **Pre-work (before this track's create-project):** persist `scripts/verbosity-census.sh` — one pinned grep pattern per FR-9 metric + total-word count + schema-restatement pattern, with test-file scope stated — plus the guard-classification table (keep/delete) as a repo artifact. SC-1/SC-4 and the FR-9 regression baseline run off it.
3. When DB track's event model lands (or its design freezes OQ-6), `/pd:create-project` this PRD; pilot with the specify command per Pre-Mortem recommendation.

## Reference Files

- Verbosity/dispatch evidence: `plugins/pd/commands/{implement,secretary,create-plan,design,finish-feature,specify}.md`, `plugins/pd/skills/workflow-transitions/SKILL.md`
- Repo's own indictments: `docs/pd-audit-findings.md:13-39`, `docs/knowledge-bank/heuristics.md:293,806`, `docs/knowledge-bank/anti-patterns.md:419,645`, `docs/brainstorms/20260406-120000-insights-driven-improvement.prd.md:15,136`
- Guard classification + census numbers: session evidence report 2026-07-10 (summarized in Problem Statement)
- validate.sh contracts touched by the rewrite: `validate.sh` (codex-routing exclusion list, hooks.json contract), `scripts/check-doc-drift.sh`
- Companion track: `docs/brainstorms/20260710-153600-entity-db-redesign.prd.md`

## Review History

### Review 1 (2026-07-10) — pd:prd-reviewer
- **Verdict:** APPROVED, zero blockers. All load-bearing citations verified exact (audit-findings:13-39, heuristics:293, anti-patterns:419/645, implement.md:250/910, the 78% figure, companion OQ-6 seam).
- **Warnings addressed in this revision:** census persistence added as explicit pre-work (`scripts/verbosity-census.sh` + guard-classification table) so SC-1/SC-4 are re-runnable; Story 2/FR-7 acceptance explicitly tagged contingent on DB-track OQ-6 with the minimal seam contract named (`mini_spec` + `skipped` events); FR-9 counts marked as session-sweep approximations superseded by the pinned census baseline; SC-1 made a firm ≤10,000; dispatch figures relabeled "derived from dispatch-graph analysis".
