# PRD: Workflow Rebuild — Lean Canonical Workflow + Express Mode

## Status
- Created: 2026-07-10
- Last updated: 2026-07-25 (revision 2)
- Status: Draft
- Problem Type: none
- Archetype: improving-existing-work
- Entity: `brainstorm:20260710-153500-workflow-rebuild`
- Track: 1 of 2 (companion: `20260710-153600-entity-db-redesign.prd.md`) — **DB track shipped 2026-07-19 (P004, 16/16 features)**
- Revision 2 (2026-07-25): premise sharpened from capability-decay research + P004 campaign evidence — models no longer need instructions; they still need external verification. Changes logged in Review History.

## Problem Statement

The workflow's implementation is a 2024-era exoskeleton built to babysit weaker models. Its essence — staged uncertainty reduction with research-grounded gates, narrow-purpose agents, and independent review — is sound; the machinery wrapped around it costs tokens, wall-clock, and reading time without buying quality, and the repo's own retrospective evidence says the review loops actively don't work. Revision 2 sharpens the premise: what survives contact with 2026 evidence is not phase prose plus review choreography but **the state machine as sole state-holder plus mechanical, execution-grounded verification** — frontier models need verification, not instructions.

### Evidence
Verified 2026-07-10 (verbosity census + dispatch-count analysis + the repo's own artifacts):

- **Volume:** ~74,000 words of orchestration prose (8,181 command lines + 5,616 skill lines). In the four artifact-producing commands (`implement`, `create-plan`, `design`, `specify`), **75–80% is defensive scaffolding + duplicated boilerplate**, not intent. `implement.md`'s review phase spans lines 210–1095 (~78% of the file).
- **Duplication:** the reviewer JSON return schema is restated **62× across 23 files** (3× per reviewer per command: fresh / resumed / final-validation dispatch). `resume_state` machinery: **239 occurrences**. Codex-routing preamble copy-pasted in 11 files. 58 per-command YOLO override blocks. The one factored-out counter-example (`workflow-transitions` validateAndSetup/commitAndComplete) proves the DRY alternative works.
- **Dispatch cost:** a small feature run = **33 subagent dispatches minimum, ~85 at caps**. `implement`'s happy path alone is ≥8 reviewer dispatches — a mandatory full 4-reviewer re-validation runs even when everything passed first time (`implement.md:250,910`).
- **The loops don't earn it (repo's own artifacts):** `docs/pd-audit-findings.md:13-39` rates the reviewer loops **Critical**, citing self-correction research (DeepMind: 7.6% of wrong answers fixed vs 8.8% of right answers broken; Self-Refine: diminishing returns after 1–2 iterations) and recommends removing the loops. Feature 006: **38 review iterations for a documentation-only feature** (`heuristics.md:293`). A reviewer finding one nitpick per iteration until the circuit breaker fires with zero correctness issues resolved (`anti-patterns.md:419`). Final-validation counting against the iteration cap means **the legitimate completion path can trip the circuit breaker** (`anti-patterns.md:645`).
- **Complexity managing complexity:** the resume/delta/compaction apparatus exists to manage the token cost of the loop design itself — guards for the machinery, not for any model failure.

### Evidence added at revision 2 (verified 2026-07-25)

- **Scaffold decay is measured, not speculative:** mini-swe-agent (~100 lines, bash-only) scores >74% on SWE-bench Verified and is now the standard evaluation harness (vals.ai, DeepSWE) precisely so the model, not the scaffold, is what's measured; a 2026 harness benchmark found the minimal harness beat feature-rich harnesses (including Claude Code) with the same frontier model AND gained ~2× more from a model upgrade (+11.5% vs +6.1%) — rigid harnesses restrict scaling.
- **Self-review did NOT improve with capability:** 2025–26 research reports a ~64.5% blind-spot rate for models correcting their own errors vs identical external ones (Self-Correction Bench), and the TACL survey pins the working condition: correction grounded in external feedback (tests, error localization). Generator and evaluator share failure modes; a same-context review pass is weak evidence.
- **Our own frontier-era data agrees (P004, 16 features, Jun–Jul 2026):** implementation-review yield is collapsing (feature 133's three-reviewer battery: 0 blockers ×3; feature 129: 4 of 9 blockers were self-signaling — they would have failed loudly in the next task's own verify step; backlog #057) while artifact-chain self-consistency dominates the blocker ledger (the restatement/half-sweep class re-fired 5× within feature 123 alone, "100% gate-caught, 0% prevented" — #074 — with the cross-feature tally reaching its 7th occurrence by feature 126 per the CLAUDE.md guardrail note; a phantom deletion target survived 14 review rounds — 133 retro). The four-artifact chain generates the failure surface the review chain then catches.
- **What actually caught 2026 failures was mechanical, not prose:** def-diff derivation, existence probes, mutation-proven tests, pinned greps (133 retro: "the gates that worked all asked what does the TREE say"). The deletion target is process prose; the keep is mechanical verification.

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
2. Cut the harness to what a frontier model still needs: the state machine as sole state-holder, short contracts, mechanical gates, and execution-grounded verification — verification, not instructions.
3. Add an express lane for small / low-uncertainty tasks without forking the tracking model (user R1.3).

## Success Criteria

- [x] Orchestration prose ≤ 8,000 words, measured by the census `scope_words_orchestration` metric — **landed 7,718 (87% reduction from the 60,082 baseline)**. Scope resolution at implementation (2026-07-25): the full commands+skills tree includes ~22k words of domain-knowledge packs that Non-Goals forbid rewriting, plus ~4k of advisor-persona knowledge, so the target binds the orchestration subset pinned in `scripts/verbosity-census.sh` (DOMAIN_SKILLS / DOMAIN_COMMANDS / ADVISOR_REFS exclude lists). Target revised 5,000 → 8,000 at implementation with arithmetic shown in Review History: FR-3's own 200–500-word contract band × the pinned 38-file orchestration inventory floors near 7,000 — the two pins collided (the #125 spec-vs-design collision class, caught at execution). Verified by `scripts/verbosity-census.sh`.
- [ ] Small feature, deep mode: ≤ 8 subagent dispatches; express mode: ≤ 3 (from 33–85) — measured by a census-script dispatch metric (pinned grep over Task/`subagent_type` dispatch sites per mode's command path), re-runnable like the word-count baseline.
- [ ] LLM review moments per deep-mode feature ≤ 2 (one design review, one adversarial code review) — counted by the same dispatch metric (review dispatches are a labeled subset); every mechanizable phase-boundary check (existence probes, contract-restatement greps, count/consistency checks) runs as a script/hook at zero dispatch cost.
- [ ] Review pattern per gate: one pass + at most one fix round, then user escalation — no iteration-to-cap loops; **zero circuit-breaker trips on happy paths**.
- [ ] Reviewer return schemas defined in exactly one place each (agent files); the census script's schema-restatement pattern over `plugins/pd/commands/` = 0.
- [ ] All model-independent guards still present: prompt-injection hardening, data-file single-writer, MCP degradation ladders, prerequisite fail-fast, one bounded breaker that final validation does NOT count against.
- [ ] Every retained guard carries an expiry/re-test condition in the guard-classification table ("build for deletion" — a kept guard without a named re-test condition is a deletion candidate by default).
- [ ] `./validate.sh` green after the rewrite (incl. doc-drift gate counts, hooks contract, codex-routing coverage list).

## User Stories

### Story 1: Deep-work feature
**As a** developer building a risky feature **I want** the full 6-phase pipeline with research agents, mechanical phase gates, and two LLM review moments **So that** decisions stay grounded and blindspots are caught — at ≤8 dispatches instead of 33–85.
**Acceptance:** all six phases execute, producing the artifacts named in FR-11's per-mode inventory; phase boundaries run mechanical checks; design gets one independent review; implement pairs an execution-verifying QA agent with one adversarial code review.

### Story 2: Express fix
**As a** developer making a small, low-uncertainty change **I want** triage to route me through mini-spec → implement → one combined QA+review pass **So that** a one-file fix doesn't pay six phase gates.
**Acceptance:** express run ≤ 3 dispatches; a mini-spec is recorded as an event; skipped phases recorded; same entity tracking as deep mode. Seam status at rev 2: `skipped` events SHIPPED in P004 (`_V2_PHASE_NAMED_EVENT_TYPES`, `database.py:6089`); `mini_spec` is still absent from the v2 event vocabulary — see Technical constraints.

### Story 3: Triage with override
**As a** user **I want** the secretary to assess uncertainty/risk and recommend deep vs express — and to accept my override in both directions, including escalating express → deep mid-flight **So that** mode selection is a default, not a cage.
**Acceptance:** triage states its mode rationale in one short block; `--deep`/`--express` force flags work; mid-flight escalation carries the mini-spec forward as brainstorm input.

### Story 4: YOLO run
**As a** user running autonomously **I want** one global YOLO rule (auto-answer prompts, halt on safety keywords) defined once in workflow-transitions **So that** behavior is uniform and not re-specified per command.
**Acceptance:** per-command YOLO blocks deleted; the global rule covers every AskUserQuestion site; safety hard-stops unchanged.

## Requirements

### Functional
- **FR-1 (R1.1 — single entry):** `/pd:secretary` remains the unified entry point, slimmed to *triage-that-selects-mode*: assess uncertainty, risk, and blast radius → route to deep mode, express mode, or a specialist. Replaces the 8-step pipeline + 11 lookup tables with a short routing contract.
- **FR-2 (R1.2 — canonical spine):** Deep mode keeps brainstorm → specify → design → create-plan → implement → finish, each phase advancing the artifact chain (producing or updating the artifacts in FR-11's per-mode inventory) and reducing uncertainty from boundaries to details. Narrow-purpose research agents (codebase-explorer, internet-researcher, skill-searcher, advisors) remain the anti-context-pollution mechanism.
- **FR-3 (contracts, not scripts):** Each phase command is rewritten as a contract — inputs, output artifact, definition of done, constraints — targeting 200–500 words. Skills carry knowledge/criteria, not step-by-step procedure. Shared mechanics stay factored in `workflow-transitions` (the pattern that already works).
- **FR-4 (two-tier gates — revised at rev 2):** Phase boundaries get a **mechanical gate**: scripted, deterministic checks (artifact/deletion-target existence probes, contract-restatement greps, count/consistency checks — the catchers P004 proved out) at zero dispatch cost. **LLM review is reserved for two judgment gates per deep feature:** one independent design review and one adversarial code review (FR-5). Protocol for any review: one pass → at most one fix round → escalate remaining issues to the user; no iteration-to-cap. Independence rules: the reviewer runs in fresh context; factual claims cite a verifying file:line (CLAUDE.md guardrail); self-signaling issue classes — ones that would fail loudly in the next execution step — are warnings, not blockers (#057).
- **FR-5 (implementation QA, R1.2):** Implement pairs the implementer with (a) an independent QA agent doing **execution-based verification** — run the tests, drive the affected flow — and (b) one adversarial code-review pass (the second LLM review moment). The mandatory second full-review round is deleted; the circuit breaker remains but final validation does not count against it.
- **FR-6 (schema single-source):** Reviewer return schemas live only in the reviewer agent files; dispatching commands reference the agent.
- **FR-7 (R1.3 — express mode):** Express path = inline mini-spec (recorded as an event) → implement → one combined QA+review pass → finish. Same entity/state tracking as deep mode; skipped phases recorded via the DB track's event model. Seam contract: `mini_spec` + `skipped` event types — `skipped` shipped in P004; `mini_spec` is a pinned early input (Technical constraints).
- **FR-8 (global YOLO):** One YOLO override rule in `workflow-transitions`; per-command blocks deleted. Safety hard-stops (merge conflict, review failure, missing prerequisites) unchanged.
- **FR-9 (deletion inventory):** Remove: `resume_state` machinery (~239 refs), delta-size guards (16), context-compaction detection (~12), `Files read:` confirmation ritual (~38), LAZY-LOAD warnings (13), JSON parse/retry ladders, per-command schema restatements (~62 sites across 23 files), the mandatory post-pass re-validation round, per-command YOLO blocks (58). Counts are from the 2026-07-10 session sweep; the census script (Next Steps) pins each metric's exact pattern and scope (test files in/out) — the pinned numbers become the regression baseline, superseding these approximations.
- **FR-10 (guards kept):** Prompt-injection hardening in dispatches, `data-file-guard` single-writer, MCP degradation ladders, prerequisite fail-fast (one line, not 4-level message ladders), one bounded circuit breaker.
- **FR-11 (restatement elimination — new at rev 2):** The artifact chain must not restate derivable content: every contract is pinned in exactly ONE location; downstream artifacts link, never re-quote. The per-mode artifact inventory is decided at design with a default bias to fewer documents (deep-mode default: spec+design merge into one shape document unless triage flags high uncertainty; tasks derived at dispatch time from the design rather than maintained as a fourth artifact). Phases remain state-machine states regardless of artifact count — merging artifacts does not change the phase vocabulary. Evidence: restatement drift is the top measured blocker class (#074: re-fired 5× in feature 123 alone, 100% gate-caught / 0% prevented, 7th cross-feature occurrence by 126; a phantom deletion target rode 14 review rounds).
- **FR-12 (state machine as harness spine — new at rev 2):** Agents never track or manage workflow state. All phase state lives in and flows through the workflow engine (v2 events + projections); dispatch prompts carry the task-scoped contract plus pointers, nothing more; command prose must not restate state the machine owns (phase sequences, transition rules, and status vocabularies exist ONLY as engine/schema definitions and are queried, not quoted).

### Non-Functional
- **NFR-1:** `validate.sh` stays green throughout — the rewrite updates its hard-coded contracts in the same change: codex-routing coverage allowlist ("Codex Reviewer Routing exclusion" expected-files list), hooks.json registration contract, and doc-drift gate README counts when components change (CLAUDE.md docs-sync checklist applies).
- **NFR-2:** Docs sync — README/README_FOR_DEV component tables and counts updated with the rewrite (enforced by the doc-drift gate).
- **NFR-3:** Every reviewer/QA dispatch remains a separately-contexted subagent (context isolation preserved even as counts drop).
- **NFR-4 (DB-trust prerequisite — new at rev 2):** No feature that deletes prose/artifact redundancy may land before (a) the v1→v2 cutover has executed (backlog #085) and (b) the acknowledged-but-lost write bugs are fixed (#055 phase-event loss, #056 double-encoded params, #060 vanishing backlog registrations). Rationale: artifacts and `.meta.json` are today's redundancy that exposes DB write loss; this PRD makes the DB sole memory, which converts those bugs from parked annoyances into silent state corruption. Scope: "redundancy-deleting" means removing artifact/`.meta.json` authority as the DB's backstop (FR-11's artifact reduction, FR-12's projections-only stance); FR-9's prose/scaffolding deletions (resume_state, schema restatements, YOLO blocks) are NOT gated by this NFR.

## Edge Cases & Error Handling

| Scenario | Expected Behavior | Rationale |
|----------|-------------------|-----------|
| Triage misroutes (too shallow/deep) | User override flags both directions; triage states rationale so misroutes are visible | mode is a default, not a cage |
| Express task reveals hidden depth | Escalate to deep mid-flight; mini-spec becomes brainstorm input; event records the escalation | no restart penalty |
| Reviewer rejects twice | Stop and escalate to user with the open issues — never loop further | evidence: loops past 1–2 iterations degrade |
| MCP down mid-phase | Existing degradation ladder (proceed, reconcile later for non-state ops; state mutations fail loud per DB track FR-10) | model-independent guard kept |
| DB write silently lost once DB is sole memory | Structurally ordered out: NFR-4 lands the trust fixes before redundancy deletion; post-cutover engine writes are fail-loud (P004) | the old artifact redundancy is exactly what this track deletes |
| YOLO safety keyword hit | Hard stop, report — unchanged | safety boundary |

## Constraints

### Behavioral (Must NOT do)
- No reintroduction of per-command schema restatements, resume machinery, or double-review pairs — Rationale: that's the regression this PRD exists to prevent; the census numbers are the regression test.
- Must not change the phase vocabulary — Rationale: DB track models it; seam stays single-sourced.

### Technical
- **DB track shipped 2026-07-19** (P004, 16/16: DB sole truth, read-only projections, `skipped` events live). Residual seam: `mini_spec` event type absent from the v2 event-type vocabulary and code (verified 2026-07-25: `_V2_PHASE_NAMED_EVENT_TYPES` at `database.py:6089`; the token appears only as forward references in planning docs — this PRD and feature 123's spec.md:32). Adding it touches CHECK-constrained event-type columns — the #077 hazard class (design-pinned write-value vs live CHECK shipped feature 124 silently inert) — so it requires a forward-only migration and must be pinned as an explicit early input at decomposition, not discovered mid-implement.
- NFR-4's trust gate: #085 cutover + #055/#056/#060 fixes are prerequisites for redundancy-deleting features; they may run as their own mini-campaign before or in parallel with this track's early features.
- Circuit breaker: final validation excluded from the count (fixes `anti-patterns.md:645`).

## Approaches Considered

| Approach | Verdict | Why |
|---|---|---|
| Collapse 6 phases → 3 (Shape/Build/Ship) | **Rejected (user R1.2)** | The spine IS the uncertainty-reduction model; the cost problem is the implementation, not the phase count |
| Keep skeptic + gatekeeper pairs, lower caps | Rejected | Evidence: paired loops produce nitpick churn and breaker misfires; one merged reviewer contract covers both questions (rev 1 — superseded by two-tier gates, next row) |
| One LLM reviewer at EVERY phase gate (revision 1's FR-4) | **Superseded (rev 2)** | P004 data: the drift classes were caught by mechanical checks; per-phase LLM review was increasingly confirmatory (0-blocker batteries; #057's self-signaling share, 4 of 9; #058's zero-finding rerun) |
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
| DB is sole memory while write-loss bugs are open | NFR-4 hard-orders #085/#055/#056/#060 ahead of redundancy deletion |
| A deleted guard turns out load-bearing after a model change | Guard table's expiry/re-test column names each kept guard's re-test condition; the census re-run is the tripwire |

## Open Questions

1. Express-mode audit minimum: mini-spec event only, or also a one-paragraph design note for non-trivial expresses?
2. Triage rubric signals: estimated diff size, novelty, blast radius, security surface — which are load-bearing, and what's the default when uncertain (recommend: deep)?
3. **Resolved at rev 2 by FR-11:** the per-mode artifact inventory is a design decision with a default bias to fewer documents (deep-mode default: spec+design merge); phases-as-states are unchanged either way.
4. Codex-routing preamble: factor into workflow-transitions once, or drop entirely while the toggle is disabled?
5. **Resolved at rev 2 by FR-4's two-tier design:** mechanical gates carry the drift classes that episode belonged to (feature 131's false reviewer claim — refuted at database.py:7818-7824 — was a citation-verification failure); the remaining LLM reviews run fresh-context with mandatory file:line citations (CLAUDE.md guardrail), and self-signaling classes demote to warnings so the next execution step is the independent recheck (#057).

## Next Steps

1. ~~DB track proceeds first~~ **Done:** DB track shipped 2026-07-19 (P004, 16/16 features).
2. **Trust-gate mini-campaign (NFR-4 — can start now):** run backlog #085's cleaning pre-pass + the real v1→v2 cutover; fix #055/#056/#060. Independent of this track's create-project; prerequisite only for its redundancy-deleting features.
3. **Pre-work — done 2026-07-25:** `scripts/verbosity-census.sh` persisted (one pinned pattern per FR-9 metric + word counts + schema-restatement + dispatch/review-moment counts, test-file scope stated) and the guard-classification table with per-guard expiry/re-test conditions lives at `docs/workflow-rebuild-guard-classification.md` (baseline run recorded there).
4. **`mini_spec` vocabulary decision:** small DB-side addition (#077-class; forward-only migration) — either the first P005 feature or a standalone pre-feature.
5. `/pd:create-project` this PRD; pilot with the specify command per the Pre-Mortem recommendation (convert one command end-to-end, run a real feature through it, then mass-convert).

## Reference Files

- Verbosity/dispatch evidence: `plugins/pd/commands/{implement,secretary,create-plan,design,finish-feature,specify}.md`, `plugins/pd/skills/workflow-transitions/SKILL.md`
- Repo's own indictments: `docs/pd-audit-findings.md:13-39`, `docs/knowledge-bank/heuristics.md:293,806`, `docs/knowledge-bank/anti-patterns.md:419,645`, `docs/brainstorms/20260406-120000-insights-driven-improvement.prd.md:15,136`
- Guard classification + census baseline: `docs/workflow-rebuild-guard-classification.md` + `scripts/verbosity-census.sh` (pinned 2026-07-25; supersedes the 2026-07-10 session-sweep summary in Problem Statement)
- Revision-2 evidence: minimal-harness benchmarks (mini-swe-agent >74% SWE-bench Verified; 2026 same-model harness comparisons), self-correction limits (arXiv 2310.01798; Kamoi et al., TACL; Self-Correction Bench, arXiv 2507.02778), harness-decay engineering literature ("build for deletion"). Internal: `docs/features/133-doctor-check-retirement/retro.md`, `docs/backlog-manual.md` #055/#056/#057/#058/#060/#074/#077/#085.
- validate.sh contracts touched by the rewrite: `validate.sh` (codex-routing exclusion list, hooks.json contract), `scripts/check-doc-drift.sh`
- Companion track: `docs/brainstorms/20260710-153600-entity-db-redesign.prd.md`

## Review History

### Review 1 (2026-07-10) — pd:prd-reviewer
- **Verdict:** APPROVED, zero blockers. All load-bearing citations verified exact (audit-findings:13-39, heuristics:293, anti-patterns:419/645, implement.md:250/910, the 78% figure, companion OQ-6 seam).
- **Warnings addressed in this revision:** census persistence added as explicit pre-work (`scripts/verbosity-census.sh` + guard-classification table) so SC-1/SC-4 are re-runnable; Story 2/FR-7 acceptance explicitly tagged contingent on DB-track OQ-6 with the minimal seam contract named (`mini_spec` + `skipped` events); FR-9 counts marked as session-sweep approximations superseded by the pinned census baseline; SC-1 made a firm ≤10,000; dispatch figures relabeled "derived from dispatch-graph analysis".

### Revision 2 (2026-07-25) — capability-decay update (changelog, pre-review)
- **Premise:** keep = state machine + mechanical verification + two LLM review moments; delete = process prose + per-phase review choreography. Driven by external research (scaffold decay measured; self-review still structurally weak at frontier) and P004 campaign data (review-yield collapse; restatement-drift dominance).
- **Targets tightened:** prose ≤10,000 → ≤5,000 words; dispatches 12/4 → 8/3; new criteria for ≤2 LLM review moments per deep feature and per-guard expiry/re-test conditions.
- **Requirements:** FR-4 rewritten (two-tier gates: mechanical + two judgment reviews); FR-11 (restatement elimination / per-mode artifact inventory) and FR-12 (state machine as harness spine) added; NFR-4 (DB-trust prerequisite: #085 cutover + #055/#056/#060 before redundancy deletion) added.
- **Resolved:** OQ-3 (via FR-11) and OQ-5 (via FR-4); DB-track dependency updated to shipped status; `mini_spec` vocabulary gap verified absent and pinned as an explicit early input.

### Review 2 (2026-07-25) — pd:prd-reviewer (on revision 2)
- **Verdict:** 1 blocker + 5 warnings; all six absorbed same-day. Reviewer verified every load-bearing citation against the tree (database.py:6089 vocabulary frozenset; backlog #055/#056/#057/#058/#060/#074/#077/#085; 133-retro battery/phantom/TREE claims; audit-findings:13-39; anti-patterns:419/645; heuristics:293; implement.md:250/910; database.py:7818-7824 for the feature-131 episode). Both coherence questions resolved in the PRD's favor (FR-11 preserves phase vocabulary; NFR-4 consistent with Next Steps 2).
- **Blocker absorbed:** Approaches row said "#057's self-signaling majority" — the source (backlog-manual.md:44-46) and this PRD's own Evidence bullet say 4 of 9, a minority → reworded to "share, 4 of 9". The author-restated-literal class, caught inside the very revision written about that class.
- **Warnings absorbed:** #074 count re-attributed in both restatements (5× within feature 123 per #074; 7th cross-feature occurrence by 126 per the CLAUDE.md note); FR-2 + Story 1 reworded to defer to FR-11's artifact inventory instead of asserting six artifacts; dispatch/review-moment criteria given a census measurement mechanism and the census pre-work scope extended to match; "zero repo occurrences" scoped to vocabulary/code with planning-doc forward-references noted; NFR-4's "redundancy-deleting" term defined (FR-11/FR-12 surfaces gated; FR-9 prose deletions not).
- **Closure without confirmatory re-dispatch:** every fix is a quoted-phrase replacement mechanically verifiable against the reviewer's cited lines — backlog #058's inline-verifiable criterion; a zero-finding rerun is the exact pattern it flags.

### Implementation clarifications (2026-07-25) — feature/134-workflow-rebuild
- **SC word-count scope resolved:** the ≤5,000 target binds `scope_words_orchestration` (baseline 60,082), not the full tree — a literal full-tree target is unsatisfiable while Non-Goals protect ~22k words of domain packs. Exclude lists pinned in `scripts/verbosity-census.sh`; guard-classification note updated in the same pass.
- **OQ-4 resolved:** codex-routing preambles dropped from all commands/skills (toggle disabled); `plugins/pd/references/codex-routing.md` retained; validate.sh FR-2b allowlist emptied in the same change (NFR-1).
- **OQ-1 resolved:** express-mode audit minimum = the `mini_spec` event (text in metadata) + skipped events; no design note required.
- **OQ-2 resolved:** triage rubric pinned in secretary.md — security surface / migration / multi-file blast radius / novel domain / non-mechanical success criteria ⇒ deep mandatory; uncertain ⇒ deep.
- **FR-11 inventory decided:** deep = prd.md → shape.md (Requirements+Design) → plan.md → code+tests → retro.md; tasks derive at dispatch time (taskify/create-tasks retired); no implementation log; `.review-history.md` retired (reviewer notes live on completed events).
- **SC word-target revision (2026-07-25, implementation):** ≤5,000 → ≤8,000 for `scope_words_orchestration`. Arithmetic: FR-3 pins 200–500 words per contract command; the pinned orchestration inventory is 25 commands + 13 skills. Phase+entity commands at the band's low end ≈ 2,300; spine skills (workflow-transitions 470 + workflow-state 141) ≈ 600; section-quality skills (specifying/designing/planning/researching/finishing-branch/detecting-kanban) ≈ 1,050; implementing/decomposing/retrospecting/updating-docs ≈ 1,260; brainstorming SKILL 398; utility command contracts ≈ 1,900. Floor ≈ 7,000 — the 5,000 pin (authored 2026-07-10 against a smaller imagined surface) and the FR-3 band cannot both hold over this inventory. Landed: 7,718 = 87% below baseline. Deletion metrics all hit zero (resume_state 239→0, delta guards 48→0, compaction 37→0, files-read 40→0, lazy-load 14→0, schema restatements 41→0, YOLO headers 13→1 global). Utility-trim headroom (~400 words) noted as non-gating.
- **QA-round design decisions (2026-07-25, absorption):** (1) The engine accepts any `skipped_phases` list (G-08 exempts only the skipped phases' own artifacts; the target's prerequisites otherwise hold) — skip *legitimacy* is triage's job (secretary rubric), per feature 123's overlay model; an engine-level mode gate was considered (qa-server M6) and declined as mode-plumbing the express design deliberately avoids. (2) Fresh `EntityDatabase` files bootstrap v1-generation and migrate through the v1 chain (now v20, which admits `mini_spec`); the v2 lineage applies only to cutover/rebuild-produced files (qa-exec two-chain finding) — both chains share the widening helper, and consolidating new-file bootstrap onto schema_v2 is left as a future simplification, not a defect.
- **qa-mig3 absorption (2026-07-25, migration lens — landed on 4th attempt, Opus/1M, empirically probed):** HIGH: the last-skipped-wins defect fixed on workflow_phases lived on in the v2 event-sourced views (`entity_axis_state` MAX(uuid) over ALL events) — absorbed as a DELIBERATE revision to feature 120's view contract: `skipped` rows are excluded from state (`WHERE event_type != 'skipped'`, v2 migration 3 / v1 migration 21 rebuild the views on existing files; write-site-only fixes could not reach backfilled skips already in the immutable events store). NULL-to_value visibility is PRESERVED — `phase_reset` pins NULL as the designed reset semantic — so the audit-only `mini_spec` event is excluded at the write sites instead (append_phase_event Step 6 + backfill emit). MEDIUM: `max(V2_MIGRATIONS) == V2_SCHEMA_VERSION` now asserted at import (stamped-ahead files were unfixable). LOWs: `DROP TABLE IF EXISTS phase_events_new` insurance; `_apply_v2_chain` non-vacuity pinned (isolated from the v1-chain aliases). Pre-existing fresh-file concurrent-bootstrap race recorded as backlog #088 (mis-cited as #086 here and in cbee6257's message at commit time — #086 is 132's skipped_phases char-explosion item; corrected in the 2026-09-16 close-out; verified develop-identical).
