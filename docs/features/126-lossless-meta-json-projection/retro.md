# AORTA Retrospective — Feature 126 (lossless-meta-json-projection)

**Mode:** standard · **8th P004-lineage feature** (131→118→129→119→130→121→120→**126**). Facilitated by pd:retro-facilitator (opus, read-only, all figures re-derived); written by the orchestrator with the facilitator's two figure corrections APPLIED (below). Active window 4h10m (specify 07-11T19:04 → implement-complete 23:14); pre-specify idle ~31h56m — campaign-longest batch-queue idle. 10 commits develop..HEAD off `f3bf6591`.

## Figure corrections (the restated-literal class, caught by re-derivation)

1. **Blocker total is 12 (8 fresh / 4 self-inflicted), not the 13 (9F/4S) the running tallies asserted.** The itemized findings sum to 12; the phantom was a FRESH design blocker — the skippedPhases finding double-counted across its design-gate detection and its spec-layer correction. Self-inflicted count (4) was correct. `.review-history.md` corrected with dated markers.
2. **"Campaign's first spec-layer self-inflicted blocker" was FALSE** — 121 had three spec-layer self-inflicted blockers one feature earlier (121-retro:16/:25/:61). True only for the false-premise-about-unread-code sub-type. Third campaign label correction (119's battery, 120's design-gate, now this) — and it slipped WHILE the battery streak was being checked, so the superlative check must be exhaustive, not one-claim (Tune 2).

## A — Activities (re-derived)

| Phase | Dispatches | Blockers F/S (corrected) | Gate | Proxy duration |
|---|---|---|---|---|
| specify | 4 (skeptic ×3, gate ×1) | 6 (5F/1S) | skeptic PASS iter 3/3 (cap, zero residual); gate round 1 | — |
| design | 4 (skeptic ×2, gate ×2) | 3 (2F/1S) | skeptic iter 2; gate round 2 after ONE BACKWARD-TO-SPECIFY | ~59m |
| create-plan | 5 (plan, task, relevance ×2, gate) | 3 (1F/2S) | relevance converged round 2; gate round 1 zero-issue | ~53m |
| implement | 9 (4 impl, deepener, battery ×3, 360°) | 0 | battery 3/3 iter-1; 360° approved | ~2h18m |

**Totals:** 22 dispatches (17 review/gate + 4 implementer + 1 deepener). Task-2's first dispatch died on a 64k output-token overflow with zero writes — clean chunked retry.

## O — Outcomes

**Shipped:** dark `meta_projection.py` (232 lines) + 21 tests (`6442fce1`) · 453-line seeded property test (`23560163`) · NFR-3 two-component harness + census seeder (`86410074`) · baseline artifact (`c892ad75`) · +17 deepener tests + matcher hardening (`add79b48`) · battery absorptions (`762f1781`). FR-11 registry +3 keys (073/075) with consumer attribution corrected. Suite 3631 post-everything; validate 0 errors; hooks 67/67. NFR-3: walk 29/31 ms p50/p95 @ recorded N=22 (40/42 @ 220); glob no-match 29/32 (36/38); census 533/5,644/7 in 0.113 s.

**Campaign blocker trajectory (per-retro re-derived):** 131:7 → 118:5 → 129:9 → 119:2 → 130:3 → 121:10 → 120:1 → **126:12**. Self-inflicted (tracked since 120): 121:5 (50%) → 120:0 → **126:4 (33%)** — 120's zero-self profile did NOT replicate; all 4 of 126's are the fix-introduced/half-sweep family.

**"7th consecutive clean battery" — VERIFIED** (chain: 118-retro:22 → 129-retro:57 → 119-retro:20 → 130-retro:19 → 121-retro:19 → 120-retro:11 → 126). Standing caveat: 131's battery was also iter-1-clean; excluded by the fixed basis (130-retro:19).

**"First backward transition" — holds for RECORDED phase-gate reversals only** (via record_backward_event; 118's create-plan "backward-to-design" was a within-phase reviewer push, not a recorded transition).

## R — Reflections

- **Headline: source-class diversity beats more eyes on the same source.** Three spec skeptic iterations all verified skippedPhases against the SAME two on-disk files and passed; the design gate went to the WRITER'S OWN TESTS and proved a second live shape (native array), forcing the backward transition and the shape-preserving-passthrough redesign. On-disk artifacts are downstream projections; the writer's tests are the behavior. Generalizes 118's "grep the right pattern space" to "verify against the right source CLASS" — now a CLAUDE.md hierarchy (Tune 3).
- **Half-sweep recurred POST-guardrail — reverse direction, 7th occurrence.** 120-Tune-1's extension covered code-docstrings; 126's miss was upstream design.md restatements of downstream plan/task fixes. The rule was already direction-agnostic — the sweep simply wasn't executed during absorption. 7 occurrences: 100% gate-caught, ~0% prevented. Tune 4 targets execution, not another rule.
- **Deepener earned its dispatch again:** the sentinel matcher accepted fused marker suffixes (awk substring). The hardening itself broke on legitimate annotations first (smoke exit-3 caught pre-commit), refined to marker==line-or-space-prefix, probe-verified against the real file. Second consecutive feature where the deepener found a real defect beyond coverage.
- **Claim-ahead-of-verification (orchestrator):** the matcher-fix commit message claimed "probe verified exit-3" one step before the probe ran; caught in immediate self-review, probe then run for real. Convention pinned: claims trail verification, even in commit messages (Tune 5).
- **What worked:** per-shape passthrough (no normalization = no lossiness argument to defend); exact-count smokes as non-vacuity (211-event pin, oracle-denylist probe); the output-overflow retry protocol (chunk + short-report re-brief, zero partial writes); Process Notes now in all four phases — the 120-Tune-2 fixture EXCEEDED (nothing material unrecorded this feature, unlike 129/130).

## T — Tune

**Prior Tunes fired (evidence-verified):** 130-Tune-1 re-derivation (caught both figure corrections) · 121-Tune-2 tagging (localized the phantom to FRESH) · 121-Tune-1 adjacent-surface (first substantive exercise — classified spec-B3, didn't prevent) · 119/129-Tune-3 citations (the backward transition IS its refinement case) · 131/118 non-vacuity (×3) · 129-Tune-5 skip-confirmatory-reruns (task-reviewer not re-dispatched) · 119-Tune-1 keep-all-gates (relevance load-bearing at create-plan this time) · 120-Tune-2 Process-Notes (all four phases) · 120-Tune-3 superlative check (PARTIAL — battery yes, spec-label no).

**New Tunes (applied at finish):**
1. **Corrected tallies shipped** — 12 (8F/4S) in this retro + dated corrections in .review-history.md. Done.
2. **Superlative check made EXHAUSTIVE** — CLAUDE.md: grep for every first/only/Nth/consecutive/highest claim, chain-verify each. Done.
3. **Source-class hierarchy** — CLAUDE.md: writer's tests outrank on-disk artifacts for behavior/shape claims. Done.
4. **Sweep as mandatory absorption step** — CLAUDE.md: direction-agnostic, every absorption edit; the gap is execution not coverage. Done.
5. **Claims trail verification** — CLAUDE.md line beside the sweep rule. Done.

**Tune-fatigue check: healthy** — 9 distinct prior Tunes fired with evidence this feature. Anti-fatigue flag honored: no 8th half-sweep rule added (Tune 4 is enforcement).

## Process notes

- **#065 injected-observation noise:** disregarded at the specify gate, the 360° verification (a fabricated "Restored from Backup Copy" claim), and 6 reminders at retro compilation. Standing item.
- **Nothing material unrecorded** — task-2 overflow retry, the broken-then-refined matcher hardening, and the claim-ahead incident all landed in Process Notes in-phase.
