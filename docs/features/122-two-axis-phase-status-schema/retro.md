# AORTA Retrospective — Feature 122 (two-axis-phase-status-schema)

**Mode:** standard · **9th P004-lineage feature** (131→118→129→119→130→121→120→126→**122**). Facilitated by pd:retro-facilitator (opus, read-only, all figures re-derived); written by the orchestrator with the facilitator's three briefing corrections APPLIED (below). Active window ~2h56m (specify 2026-07-12T00:32 → implement-complete 03:27); pre-specify idle ~37h24m — campaign-longest (exceeds 126's ~31h56m; queue-position artifact of the 2026-07-10 batch creation, not a process signal). 9 commits develop..HEAD off `eeea6274`.

## Briefing corrections (the restated-literal class, caught by facilitator re-derivation — 3rd consecutive briefing with errors: 130, 126, 122)

1. **"Campaign-first zero-blocker create-plan AND implement back-to-back" was FALSE** — 120 did it first (120-retro: its single blocker sat at design; create-plan and implement were both 0). 122 is the **2nd**, after 120. Caught by the exhaustive-superlative check before any artifact shipped it.
2. **Commit count is 9, not the briefed "8"** — the briefing itself LISTED nine shas while captioning them "8 commits expected" (`git rev-list develop..HEAD --count` = 9, orchestrator re-verified). The off-by-one lived only in the caption.
3. **Risk-note phrasing precision:** the half-sweep recurred twice this feature, but only the SECOND miss (implement, plan.md:40) was the quadruple's risk-note member; the first (create-plan, Task-3) was a plain Do-section restatement. "The risk-note member missed twice" overstated it.

## A — Activities (re-derived from .review-history.md)

| Phase | Dispatches | Blockers F/S | Gate | Proxy duration |
|---|---|---|---|---|
| specify | 3 (skeptic ×2, gate ×1) | 1 (1F/0S) | skeptic PASS iter 2/2; gate round 1 | not isolable (idle-dominated) |
| design | 4 (skeptic ×3, gate ×1) | 2 (1F/1S) | skeptic PASS iter 3/3 (cap, converged); gate round 1 | ~47m |
| create-plan | 5 (plan, task, relevance ×2, gate) | 0 | relevance converged round 2; gate round 1 | ~46m |
| implement | 8 (3 implementer, 1 deepener, battery ×3, 360°) | 0 | battery 3/3 iter-1; 360° approved | ~1h23m |

**Totals:** 20 dispatches (16 review/gate + 3 implementer + 1 deepener). Zero dispatch deaths, zero retries — the 64k output-overflow class did not recur under the <300-line chunking brief. Per-phase durations remain unrecoverable (#055 projection lag: started≈completed within 9-14s all four phases); proxies are completion-to-completion gaps.

## O — Outcomes

**Shipped (dark; the view is EMPTY of live data until 132's cutover):** `axes.py` — PIPELINE_PHASES (6) / EXECUTION_STATUSES (7 = six reachable derive_kanban outputs + `ready` per PRD FR-8, 124's cascade slot) + frozenset views; register-on-demand expression-RAISE vocab triggers (≥3.47.0 typed-RuntimeError-guarded; messages name axis + quote(value)); latch-free `is_vocab_registered()`; `entity_phase_status` FR-6 view (thin rename over 120's entity_state, zero new aggregates) (`dbe424fa`) · trigger-teeth battery incl. self-verifying kanban subset + leak-detection pin (`0e816b8b`) · dark-guard needles/teeth red-first + merge-base baseline re-derivation (`5d67ebc3`) · +10 deepener defs/11 cases (`d43f2182`) · battery absorption: typed raises, class fold, frozenset pin, #068 filed (`0aeb35f4`). Suite 3631 → 3670 (+39 = 36+3 exact at Task 3) → 3671 net post-absorption; 184 cases across the five entity_registry files; validate 0 errors; hooks 67/67; doctor pin 19.

**Campaign blocker trajectory (per-retro re-derived):** 131:7 → 118:5 → 129:9 → 119:2 → 130:3 → 121:10 → 120:1 → 126:12 → **122:3 (2F/1S)** — ties 130 for 3rd-lowest (behind 120:1, 119:2); NOT a campaign low. Self-inflicted share (tracked since 120): 120:0 → 126:4 (33%) → **122:1 (33%)** — 126's rate at far lower volume.

**"8th consecutive clean battery" — VERIFIED link-by-link** (118-retro:22 → 129-retro:57 → 119-retro:20 → 130-retro:19 → 121-retro:19 → 120-retro:11 → 126-retro:27 → **122**, .review-history.md battery section). Basis fixed at 130-retro:19 (all-three-approved-iteration-1); 131 excluded definitionally (guardrail source, not beneficiary).

**Cross-feature coordination:** roadmap entries 9/12/15; 120-spec dated correction (derive_kanban deletion → 132); spec 124/125/132 handoffs (ready membership; board silent-drop + ready column; quote() control-char sanitization). **#068 filed:** pre-existing `INSERT OR REPLACE` immutability bypass on events (REPLACE's delete-half fires no BEFORE DELETE trigger, recursive_triggers default OFF; sqlite.org-verified at the security battery) — 119-owned, 132 remediation.

## R — Reflections

- **Headline: probe-BEFORE-author, not probe-when-challenged — now demonstrated in both directions.** The feature's one self-inflicted blocker was a design-layer unprobed behavior claim ("RAISE is static-string only") that WEAKENED an already-approved spec; the refuting probe took ~20 seconds once run. The same rule then fired CORRECTLY one layer down: Task-1's implementer probed both paren forms in sqlite3 before writing any DDL (design D2's literal reading double-parenthesizes — "row value misused"), and the orchestrator dated the design note the SAME turn, so battery reviewers read a consistent design and no iteration burned. The cost asymmetry is the lesson: 20 seconds of probe vs. a full skeptic iteration plus a spec revert.
- **Whole-artifact sweep generalizes to REQUIREMENTS sources.** Design iter-2's fresh blocker (excluding `ready`) was single-FR tunnel vision — refuted by PRD FR-8 two sections away. Checking the FR you started from is not checking the PRD.
- **Half-sweep: 9th and 10th occurrences, both gate-caught.** Create-plan's Task-3 restatement (relevance round 1) and implement's plan.md:40 risk-note (360°) continue the class's 100%-caught / ~0%-prevented record. The quadruple grep (headline/table/prose/risk-note) must be run LITERALLY against the artifact set after every absorption — both misses happened when the sweep ran from memory instead of from grep output.
- **What worked:** the deepener def-recount caught the ×2-parametrize ambiguity PRE-commit (the 126 "+17 vs 16" class, now caught before it lands); Task-2's scratch fixture-order mutation proved the battery non-vacuous ("5 rejections DID NOT RAISE" unregistered); register-on-demand + the leak-detection pin made sibling isolation structural (SC6 delivered with zero sibling test edits); convergent independent findings (security + quality both flagging assert-under--O) made the typed-raise absorption an easy call.

## T — Tune

**Prior Tunes fired (evidence-verified, 8 of 10):** 130-T1 re-derivation (kanban path grep; merge-base baseline; THIS retro's three briefing corrections) · 120-T3/126-T2 exhaustive superlatives (killed the false campaign-first label pre-ship) · 126-T4 sweep-mandatory (fired at specify self-sweep; missed twice, gate-caught) · 126-T5 claims-trail/probe-before-author (violated→corrected at design; fired correctly at implementer) · 131/118 non-vacuity (scratch-mutation proof; red-first teeth) · 119/129-T3 citations (sqlite.org + empirical probe) · 119-T1 keep-all-gates (relevance round 1 load-bearing) · 120-T2 Process-Notes (all four phases). Not exercised this feature: 126-T3 source-class hierarchy, 121-T1 adjacent-surface (no triggering conditions arose).

**New Tunes: NONE — Tune-fatigue check says stop.** 8 standing Tunes fired with evidence; both misses were execution slips of the EXISTING sweep rule (the fix is running the quadruple grep literally, which the rule already mandates). Adding a 9th sweep-adjacent rule would repeat the anti-fatigue violation 126-retro:50 explicitly declined.

## Process notes

- **#055 projection lag** confirmed again — all four phases started≈completed; durations are gap-proxies only.
- **#065 injected-observation noise** disregarded at every artifact read and by every subagent (incl. a fabricated "retrospective analysis initiated" flavor at facilitation); all figures re-derived from primary sources.
- **Briefing-error streak is now 3 (130, 126, 122)** — every orchestrator briefing since the re-derivation Tune landed has carried at least one figure error the facilitator caught. The Tune is load-bearing; composing briefings FROM re-derived figures (not memory) remains the unmet bar.
- **Nothing material unrecorded** — the single-paren deviation, both half-sweep misses, the def-recount, and #068 all landed in Process Notes in-phase.
