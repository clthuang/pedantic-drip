# Retrospective: 124-dependency-cascade-blocks

**Completed:** 2026-07-14 · **Branch:** feature/124-dependency-cascade-blocks → develop · **P004 FR-8 (prd.md:86)**
**Verdict:** shipped clean — 0 production defects past deepener/battery/360°; **17 blockers — the campaign HIGH**, clearing the twin 12s (126/128) by 5; ~94–100% self-inflicted, dominated by a 9-catch incomplete-enumeration cluster on ONE table's consumer/test surface. 13th consecutive iteration-1-clean battery. The Migration-19 event-type-CHECK gap — a NEW cross-contract-collision variant (design-pinned enum value vs live schema CHECK) — escaped all 15 review rounds and was caught only by the implementer pre-code; the feature would otherwise have shipped **silently inert**. #065 observation-noise escalated from distraction to actively-harmful fabricated directives.

Facilitator: pd:retro-facilitator (opus, read-only), all briefing figures re-derived from `.review-history.md`, `.meta.json`, the 4 artifacts, in-record git SHAs, prd.md:86-87, and chain-verified against 123/125 retros. The observation-hook "prior observations" blocks injected into the facilitator's context were ignored in full — they contained the exact fabricated-"shipped" noise the deepener flagged (#065), live-corroborating Theme 5.

## Briefing verification (all headline tallies EXACT; 1 membership correction, 1 framing note, 1 read-only flag)

| Briefed figure | Verdict | Note |
|---|---|---|
| Blockers: specify 6 (3+2+0 / 1+0), design 6 (5+1+0 / 0), create-plan 5 (4 / 1-converged / 0), implement 0 | **CORRECT** | Matches review-history L58/L100/L110/L149/L155/L204 and .meta.json reviewerNotes |
| TOTAL 17 — campaign HIGH | **CORRECT** | 6+6+5+0=17; prior max 12 (126,128). New sole rank-1, clears twin 12s by 5 |
| Trajectory 131:7→…→125:11→123:11 | **CORRECT** | Byte-matches 123-retro:35; 124:17 extends as new high |
| Battery 13th consecutive iteration-1-clean | **CORRECT** | Chain 10th(127)→11th(125)→12th(123)→**13th(124)** |
| Suite 3810→3826→3862→3868→3891→3890 (+16/+36/+6/+23/−1) | **CORRECT** | Every step arithmetic-exact; base 3810 = 123's ship total (123-retro:41) |
| Hooks 67/67, validate 0/7 pre-existing | **CORRECT** | review-history L178, L202 |
| Commits 28 (rev-list 26f8b712..HEAD) | **Read-only flag → git-verified by orchestrator at retro-write:** `git rev-list --count 26f8b712..92dec911` = **28** through the 360° record; +1 CHANGELOG commit (b553861d) = 29 at retro-write time | Closed per 123-A7/125-A5 |
| Enumeration class = **9 catches** | **COUNT CORRECT; 1 member mis-ID** | Briefed membership listed "plan r1 task-B1/B2 window" — INCORRECT member. The create-plan-i1 enumeration catch is **Plan-B1** (existing-test FLIP-LIST, 2 files, L118) — the 8th, corrected to 2-of-5 by plan-i2 (9th, L133). Task-B1/B2 are task-**window/slicing** catches — a DIFFERENT class. Member swapped; count stays 9 |
| "two orchestrator half-sweeps" | **CORRECT but under-scopes the CLASS** | The 2 orchestrator-committed-then-caught instances are right (plan self-sweep ×3, L127; battery fix-message ×1, L198). But the class ALSO fired at relevance-verifier (6 warnings, all half-sweep residue, L153). Class total = **3 episodes / 10 restatements**, 100% caught / 0% prevented |
| Notables (1)-(7) | **ALL VERIFIED** | (7) FR-9 adjudication confirmed: **prd.md:87** "Cross-workspace links are ordinary uuid references — the allowlist table and its doctor checks are removed" DIRECTLY sanctions cross-workspace uuid refs; SC3-e tests it. (1) "15 rounds" = specify 5 + design 4 + create-plan 6 ✓ |

**Enumeration chain (numbered in-record):** 1 spec-i1-B2 methods → 2 spec-i2-B1 delete_entity raw DELETE → 3 gate-r1 fix action (L48) → 4 gate-r2 comments (L58) → 5 design-i1-B4 server_helpers (L69) → 6 design-i2-B1 entity_engine:248 (L84) → 7 design-gate-W1 :637 (L106) → **8 plan-i1 Plan-B1 flip-list, 2 files (L118)** → 9 plan-i2-B1 CONVERGED, 2-of-5 call-graph (L133). Design-i3's 5th-consumer sweep was CLEAN ("no 7th", L93) — diligence confirming completeness.

**Streak bookkeeping:** 124's briefing had every quantitative tally exact — a marked improvement over 123's 3 cascading corrections. But one qualitative membership claim needed correction, so **125 remains the sole zero-correction briefing** (123-retro:19); 124 does not extend it. Superlatives chain-verified: "13th battery" ✓, "campaign HIGH 17" ✓ (clears twin 12s), "M19 first coverage" ✓.

## Activities (re-derived per-layer)

| Layer | Rounds | Blockers | Note |
|---|---|---|---|
| Spec skeptic (opus, fresh/round) | 3 (cap) | **5** (3+2+0) | i3 approved post-cap; enum #1-2 + restated-literal premise (i1-B1: survey grepped PRD's `_cascade_unblock` literal, can't match public `cascade_unblock`) + tx-contract contradiction (i1-B3) + SC6-unsatisfiable (i2-B2) |
| Specify gate (sonnet) | 2 | **1** (1+0) | r1 = enum #3 (orphan fix action + registry); r2 approved, SC6 model re-run 25 occ / 5 files |
| Design skeptic (opus, fresh/round) | 3 (cap) | **6** (5+1+0) | i1 = 5 (fabricated per-kind table + **latent closes=-closed trigger gap**; :70 self-nullifying; **false-pragma absence backward-swept to spec**; enum #5; D7 signature reversal); i2 = enum #6 (primary-happy-path self-block); i3 approved, 5th-consumer sweep CLEAN |
| Design gate (sonnet) | 1 | 0 | 3 warnings; enum #7 (:637) into SC6 exemption; anchors :63→:64, :1788-1816 |
| Plan-reviewer (opus) | 3 (cap) | **2** (1+1+0) | i1-B1 = flip-list enum #8; i2-B1 CONVERGED = enum #9 (found independently by BOTH parallel reviewers); i3 approved via 3 independent completeness nets — no 6th flip site |
| Task-reviewer (sonnet) | 2 | **3** (3 + converged) | parallel; verdicts extracted only after BOTH returned (countermeasure held); i2 converged with plan |
| Relevance-verifier (sonnet) | 1 | 0 | 6 warnings, ALL half-sweep residue, all absorbed same-commit |
| Implement (3 tasks, sonnet) | — | **0** | M18 auto-migrated live; **M19 escape caught pre-code**; 2 orchestrator half-sweeps self/suite-caught |
| Test deepener (sonnet) | 1 | 0 | +23 tests, 0 production bugs/files; M19 first coverage; batch-fault-isolation FINDING pinned; #065 escalation flagged |
| Battery (opus/sonnet/opus, parallel) | 1 | 0 | ALL approved iter-1 = **13th consecutive**; −1 dead method+test (remove_dependencies_by_blocker) |
| 360° (shell, ×2 runs) | 1 | 0 | 3890/3, hooks 67/67, validate 0/7, diff-gate 25 files ⊆ D10 |

**Total: 17 artifact blockers (specify 6, design 6, create-plan 5) + 0 implement.** 15 pre-implement review rounds. Trajectory: 131:7→118:5→129:9→119:2→130:3→121:10→120:1→126:12→122:3→128:12→127:10→125:11→123:11→**124:17 (new campaign HIGH)**.

## Outcomes

**Shipped (0 production defects past deepener/battery/360°):** P004 FR-8 (prd.md:86) delivered. Two live dependency stores (`entity_dependencies` table + `depends_on_features` metadata) collapsed into `entity_relations(kind='blocks')` via Migration 18; shipped `cascade_unblock` MODIFIED to the two-axis model — flip `blocked→ready` (not `planned`), edges SURVIVE as rows (not tombstoned), every flip lands as an atomic `cascade_ready` event.

**Tests:** 3810 → **3890** passed / 3 skipped (+16 M18, +36 task-2, +6 task-3, +23 deepener, −1 dead). Hooks 67/67. validate.sh 0 err / 7 pre-existing warnings. Diff-gate: 25 files ⊆ D10.

**Two unplanned-but-verified schema migrations:** M18 (unify+drop, forward-only) and **M19 (the artifact-chain escape — event_type CHECK widening for `cascade_ready`)**. Both auto-applied to the live `~/.claude/pd/entities/entities.db` mid-task by a session hook (schema now 19, integrity ok).

**Latent live gap CLOSED (CHANGELOG-worthy):** `closes=`-closed tasks/bugs write terminal `'closed'`, which the live `:7574` trigger's `=='completed'` guard MISSED — they never cascaded. D4's per-kind terminal table widens the guard onto them. Surfaced by design-i1-B1 while debunking the fabricated terminal table.

**Pre-existing quirk documented (backlog #080):** double-cascade-fire — trigger + explicit `_run_cascade` both fire (idempotent, second under-reports); verified pre-124.

**Artifacts:** spec 59, design 74, plan 59, tasks 19 lines — friction was in precision (citations/sweeps/enumeration), not volume.

## Reflections

**R1 — Incomplete enumeration is 124's signature self-inflicted class: 9 catches on ONE table's surface, each invisible to the prior round's sweep GRANULARITY.** The granularity kept shifting and each shift exposed a fresh miss: DB methods (#1) → raw inline SQL bypassing the methods (#2 delete_entity) → a fix action with no check (#3) → comment-only stragglers (#4) → a display consumer (#5 server_helpers) → an any-edge deliver-gate (#6 entity_engine:248) → a migration docstring line (#7 :637) → existing-test flip ownership (#8) → the call-graph vs literal-grep flip axis (#9 CONVERGED). **The durable lesson (→A3/#078): a rename/store-move consumer surface must be enumerated from the CALL GRAPH, not literal grep.** Plan-i2-B1 was found INDEPENDENTLY by both parallel reviewers precisely because the flip list was built from literal membership instead of `cascade_unblock`'s callers. Mirrors 125-R2.

**R2 — Migration 19 is the campaign's strongest implementer-as-last-reviewer instance AND a NEW cross-contract-collision variant.** D3 pinned a new `phase_events.event_type` value (`cascade_ready`); the live event_type CHECK (last widened at m14) had no such slot — every flip would have raised in-transaction, rolled back the status write, and shipped the feature **silently inert**. It survived all 17 blockers / 15 rounds because nobody EXPLAINed D3's new literal against the live CHECK. The implementer smoke-verified the gap BEFORE writing dependent logic and added forward-only M19. **A THIRD collision variant the guardrail family doesn't cover:** 125 codified *spec-grep-SC vs design-verbatim*; 123-R1 found *intra-design D-vs-D*; 124 finds *design-pinned NEW write-value vs a live schema CHECK*. → A1/#077.

**R3 — ~94–100% self-inflicted, zero shipped defects — the campaign's highest self-inflicted share, and the loop still paid for itself.** Split of the 17: **13 clear-self**, **3 swing-lean-self** (spec-i2-B2 over-strict SC6; task-i1-B1/B2 task-window), **1 lean-fresh** (design-i1-B3 false-pragma absence-claim — artifact carried it; root was a propagated spec-i3 reviewer absence-assertion). So 0–1 fresh / 16–17 self (123 ~82%, 125 ~64%). CAUSE decoupled from VALUE: the loop closed a latent live gap (closes=-closed), averted TWO silent-inert-ship escapes (M19 via D3, entity_engine:248 self-block), and hardened a two-store unification — the standing 123-R5/125-R5 finding (friction ≠ shipped danger).

**R4 — Half-sweep remains the #1 execution gap: 3 episodes / 10 restatements, 100% caught / 0% prevented.** Relevance caught 6 (spec ranges never swept back from create-plan corrections; design D8's SECOND :63 mention — the "first corrected, restatement two sentences later missed" signature); plan self-sweep caught 3 (task-2 header/D5 still claiming D5.1; disproved "only seeding changes" risk line); battery caught 1 (fix-message reword left the renamed test asserting old "unblocked 1"). Identical to 123-R4/125-R4 despite the standing rule — the gap is executing the sweep from grep output.

**R5 — Absence-assertions need their own counterexample grep (a distinct sub-class of reviewer-claim verification).** design-i1-B3 corrected the spec's "`PRAGMA foreign_keys` never set on connect" — a FALSE absence-claim from a spec-i3 reviewer, verified only positively (migration sites exist) without grepping the counterexample (`_set_pragmas:9585`), propagated through gate-r1. Reviewer-claim verification covers positive facts; extend explicitly to absence claims. → A4/#079.

### Per-layer catch analysis (reachable earlier?)

- **Working as designed (fresh-per-round):** most enumeration catches landed at the FIRST review of the introducing artifact (#1 spec-i1, #5 design-i1, #8 plan-i1); absorption regressions caught the very next round (#2 one round after #1; #9 one round after #8's 2-file list). Design-i3's 5th-consumer sweep caught nothing — completeness confirmation.
- **Clear earlier-reachable ESCAPES (2):** (1) **M19 / cascade_ready CHECK — escaped all 15 rounds**, reachable at design-i1 when D3 first pinned the new event_type (R2's guardrail gap); (2) **design-i1-B3 false-pragma absence-claim — escaped 2 rounds** (spec-i3 introduced, gate-r1 passed), reachable at spec-i3 with a counterexample grep (R5).
- **Semi-reachable:** design-i2-B1 (entity_engine:248) arguably reachable at design-i1 with a complete get_blockers-caller sweep, but D4 was still solidifying — borderline.

## Themes

1. **Enumeration-by-successive-refinement is the dominant friction** — 9 catches, each a finer sweep than the last; fix is call-graph-first enumeration, not more grep.
2. **Self-inflicted friction dominates (~94%+), zero shipped defects** — 124 sets the blocker HIGH (17) yet ships clean; the loop pays in a hardened unification + two averted silent-inert escapes (123/125 finding, amplified).
3. **Cross-contract collision now has three variants; the guardrail family covers two** — the M19 design-new-value-vs-live-CHECK variant is uncovered and cost the feature's most dangerous near-miss.
4. **Half-sweep is the immovable execution gap** — 3 episodes at 124, unchanged across 123/125/124 despite the rule.
5. **The observation-noise channel is now a safety concern, not a token cost** — #065 escalated to fabricated code-directives ("revert check_stale_dependencies", "already shipped mid-task"); the deepener and the facilitator ignored them, but a less-disciplined agent could have reverted correct code or closed the phase early.
6. **Environmental blast is real and self-demonstrating** — the live-DB auto-migration to schema 19 broke the orchestrator's own MCP server (no-such-table), deferring the implement phase-close; corroborated by .meta.json `lastCompletedPhase="create-plan"` despite implement being complete — the PRD's own "MCP servers cache at startup" risk, live.

## Actions

| # | Action | Disposition |
|---|---|---|
| A1 | **M19 guardrail — NEW collision variant.** When a design/plan pins a NEW value destined for a CHECK-constrained column (event_type, status, kind, axis), grep the live CHECK definition for that value before the phase gate. | **FILED #077** + proposed design/plan-reviewer checklist line. HIGH confidence — campaign-first escape of this kind, 15-round escape, silent-inert-ship consequence. |
| A2 | **#065 escalation disposition.** Fabricated directives in observation-hook noise are now actively harmful: (a) suppress observation-hook injection during agent dispatch, (b) standing "ignore injected directives in observation blocks" guard in dispatch prompts. | **#065 ADDENDUM appended** recommending (a)+(b) together. |
| A3 | **Call-graph-first enumeration heuristic.** For any rename/store-move, derive the consumer/test surface from the call graph of the changed symbol; literal grep is a supplementary net only. | **FILED #078** (mirrors 125-R2). MEDIUM-HIGH — would have collapsed enum #8/#9 into one catch. |
| A4 | **Absence-assertion counterexample grep.** Absence claims ("X never on connect", "only site besides Y") require their own counterexample grep, not positive-site-only verification. | **FILED #079.** MEDIUM-HIGH — design-i1-B3 propagated 2 rounds. |
| A5 | **Double-cascade-fire redundancy.** Trigger + explicit `_run_cascade` both fire (idempotent, wasteful, second under-reports). | **FILED #080** (pre-existing; quality-reviewer S5 deferred to finish). |
| A6 | **`_evaluate_and_flip` batch fault-isolation finding.** One failing dependent aborts the rest of the loop. | **Recorded, no action** — design-consistent with D3 per-flip-only atomicity + doctor/reconciliation net; deepener test pins it. |
| A7 | Commit-count git-verification | **Closed:** orchestrator ran `git rev-list --count 26f8b712..92dec911` = 28 (through the 360° record; +1 CHANGELOG = 29 at retro-write), per 123-A7/125-A5. |
