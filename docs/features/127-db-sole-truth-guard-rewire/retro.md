# AORTA Retrospective — Feature 127 (db-sole-truth-guard-rewire)

**Mode:** standard · **11th P004-lineage feature** (131→118→129→119→130→121→120→126→122→128→**127**). Facilitated by pd:retro-facilitator (opus, read-only, all figures re-derived from primary sources); written by the orchestrator with the facilitator's three briefing corrections APPLIED (below). Active window ~2h48m (specify-complete 2026-07-12T10:05 → implement-complete 12:53 UTC; #055 lag makes these completion-anchored proxies). 10 commits develop..HEAD (git-verified by the orchestrator: 3 phase-doc + 4 per-task + deepener + battery-absorption + 360°-absorption). F/S headline 5F/5S per the facilitator's center estimate (swing blockers #4/#7 documented in the per-blocker table; range 4F/6S–6F/4S).

## Briefing corrections (the restated-literal class, caught by facilitator re-derivation — 6th consecutive feature needing corrections: 130, 126, 122, 128, 127)

1. **Specify phase gate was 0-issue, not 1-warning.** `.meta.json` records the specify phase-reviewer as APPROVED 0 issues (`.review-history.md` logs no separate specify gate). The 1W is the specify **skeptic i3** approval (0B/1W/4S); the design gate is the genuine 1W.
2. **"First 4-way parallel implementation" was FALSE** — 126 also dispatched 4 concurrent implementers (126-retro:17). Defensible narrow claim: 127 is the **first 4-way with zero dispatch deaths** (126's task-2 died on a 64k overflow + retried, 126-retro:19). Same superlative-label class as 128's live-behavior label, 126's spec-label, 120's design-gate label — caught pre-ship.
3. **Blocker total is 10 distinct (11 raw), 5F/5S** — plan-reviewer and task-reviewer flagged the SAME README-count conflict (task-reviewer read a pre-absorption tasks.md), de-duplicated per the 126 precedent. F/S is facilitator judgment; range 4F/6S–6F/4S, center 5F/5S.

## A — Activities (re-derived from .review-history.md + .meta.json)

| Phase | Dispatches | Blockers F/S | Gate | Proxy duration |
|---|---|---|---|---|
| specify | 4 (skeptic ×3, gate ×1) | 3 (3F/0S) | skeptic 3/3 cap; gate round 1 (0-issue) | not isolable (idle-dominated; ~47h batch-queue idle before) |
| design | 4 (skeptic ×3, gate ×1) | 4 (2F/2S) | skeptic 3/3 cap; gate round 1 (1W) | ~54m |
| create-plan | 4 (plan, task, relevance ×2) | 3 distinct / 4 raw (0F/3S) | relevance converged round 2; no separate gate in record | ~36m |
| implement | 9 (4 implementer, deepener, battery ×3, 360°) | 0 | battery 3/3 iter-1 (10th consecutive); 360° approved | ~1h18m |

**Totals:** 21 dispatches (16 review/gate + 4 implementer + 1 deepener). Zero dispatch deaths, zero retries — first clean 4-way parallel implement (126's 4-way lost task-2 to a 64k overflow). Both skeptics used the full 3-iteration cap and converged (as 121 and 128 also did — not novel). Per-phase durations remain #055-lagged; proxies are completion-to-completion gaps.

## O — Outcomes

**Shipped (LIVE `.meta.json` write-deny + read-only projection):** guard flip + 3 deny-matrix tests (`05c85e62`); the real 4-member `META_JSON_WRITER_ALLOWLIST` pinned with per-entry rationale + exact set-membership test (`43093f12`); **route D — a NEW `reproject_meta_json` MCP tool** (5th projection call-site; ref-resolution in the async tool body mirroring get_phase; json.dumps envelope) + abandon-feature Steps 4/5 collapse + README tool count 21→22 re-counted live (`62ba3960`); `bench-db-direct-read.sh` (351 lines; 3 seeded censuses 22/220/533; view materialized post-seed) + 412-line verification artifact (`c20302b6`); +9 deepener functions/27 cases with 3 real gaps closed (`f746f0d7`); battery + 360° absorptions (`04ad6504`, `07d0d225`). Suite 3684 (merge-base effective) → 3691 (tasks, +7 exact) → **3718** (deepener +27); validate 0 errors; hooks 67/67. **NFR-3 GO (double-basis):** walk-equivalent p95 29ms ≤ 31 (recorded) AND ≤ 35 (fresh); workspace-lookup 29 ≤ 32/36 — robust to a +2-6ms fresh-baseline drift under concurrent sibling load.

**Campaign blocker trajectory (per-retro re-derived):** 131:7 → 118:5 → 129:9 → 119:2 → 130:3 → 121:10 → 120:1 → 126:12 → 122:3 → 128:12 → **127:10 (5F/5S; 11 raw)** — ties 121 at 10, behind only the twin 12s (126, 128); joint-3rd-highest total but 5 fresh vs those 12s' 8 each. **Self-inflicted share ~50%** — up from the 126→122→128 run of 33%, back to 121's profile; concentrated in the route-D footprint cascade.

**"10th consecutive clean battery" — VERIFIED link-by-link** (118-retro:22 → 129-retro:57 → 119-retro:20 → 130-retro:19 → 121-retro:19 → 120-retro:11 → 126-retro:27 → 122-retro:28 → 128-retro:28 → **127**). Basis fixed at 130-retro:19; 131 excluded definitionally.

**Cross-feature coordination:** 132 handoffs — latest-event (not MAX(uuid) lexicographic) semantics before cutover; build the real latency verdict on task-4's per-entity SEARCH primitive (the walk-equivalent is a no-match GROUP-BY latency analogue, not correctness-faithful); the inline-bypass valve's removal is 132's call (FR127-7 break-glass posture). 133 handoff — D8 confirmed nothing to retire. Backlog **#069** (dispatcher fnmatch traversal, pre-existing feature-110 infra) and **#070** (artifact_path containment, pre-existing projection path) FILED by the security reviewer — both pre-existing surfaces, no new write window opened.

## R — Reflections

- **Headline: the review loop designed the winning architecture — and paid its own footprint tax.** FR127-7's route evolved spec's two options → design i0's third (in-process `python -c` reaching a leading-underscore internal from unaudited markdown) → skeptic B1 rejecting it for undercutting FR127-3/SC2's audit intent → the skeptic's OWN S4 becoming **route D**, a sanctioned public MCP tool on the audited tree. The adversarial loop produced the feature's best decision. But route D's footprint (a new tool, a new file pair, a +1 tool count, a new diff-gate bucket, a new SC4 restatement) then generated the feature's ENTIRE self-inflicted half: the `str=""` signature-default hazard (design i2), the README count, the diff-gate route-D-bucket omission and the D7(b) SC4 half-sweep (relevance r1). A mid-feature architectural pivot's blast radius must be swept into every downstream inventory artifact the same turn it lands — 121-T1's adjacent-surface rule already says so; the gap was execution, and every miss was gate-caught.
- **Create-plan's entire blocker load (3/3) was route-D-footprint cleanup — 0 fresh.** The cleanest illustration yet that self-inflicted count measures review-loop friction, not artifact danger: three blockers, zero shipped risk, all one architectural pull-in the plan-phase artifacts hadn't fully absorbed.
- **Double-basis verdict as robustness engineering.** Binding the GO against both the recorded 126 baseline AND a fresh re-measure meant the +2-6ms concurrent-load drift never threatened the go/no-go — the claims-trail discipline (126-T5) applied to measurement.
- **Half-sweep re-fired 3× (all gate-caught):** D7(b) SC4 (relevance r1), diff-gate route-D bucket (relevance r1), post-gate backlog-file/diff-gate (360°) — the class's ~100%-caught/~0%-prevented record holds; each miss ran the sweep from memory instead of grep output.
- **What worked:** first clean 4-way disjoint-file parallel implement with per-task scoped commits, zero deaths; red-first evidence (tasks 1+3); the deepener's 3 real gaps (dispatcher end-to-end routing, projected:false branch, not_initialized for the new tool); two independent reviewers converging on the README count (reviewer-quality signal, not a doubled defect); the tuple==set non-vacuity self-check killing a vacuous-green allowlist test at authoring.

## T — Tune

**Prior Tunes fired (evidence-verified, 10 of the standing set):** 130-T1 re-derivation · 120-T3/126-T2 exhaustive superlatives · **121-T1 adjacent-surface (clearest exercise — route D is the exemplar scope-widening fix)** · 126-T4 sweep-mandatory (3 gate-caught misses) · 126-T5 claims-trail/probe-before-author · 131/118 non-vacuity · 119/129-T3 citations · 119-T1 keep-all-gates (three-gate convergence replicated) · 120-T2 Process-Notes · 121-T2 fresh/self tagging. Not distinctly triggered: 126-T3 source-class hierarchy; 129-T5 skip-confirmatory-reruns.

**New Tunes: NONE as standing rules.** The one candidate — a **double-basis NFR verdict** (bind perf go/no-go against recorded AND fresh-re-measured baselines under representative concurrent load) — is handed to **132's spec inputs** rather than codified globally (Tune-fatigue; 132 is where the cutover latency verdict pays off). All other frictions are execution-gap re-fires of 121-T1 + 126-T4 + shared-config-blast-radius, all gate-caught — consistent with 122/128's declines. No "Nth consecutive decline" ordinal asserted (unverifiable against the prior-retro chain; 128's "4th" reads inconsistent with 126/120 having added Tunes).

## Process notes

- **#055 projection lag** confirmed (started≈completed all four phases); durations are completion-to-completion proxies only.
- **#065 injected-observation noise** disregarded throughout — the PreToolUse:Read reminders fired on every primary-source read this session (including "prior observation" IDs claiming approvals/backups); every figure re-derived from .review-history.md / .meta.json / prior retros.
- **Figure-correction streak continues** (specify-gate severity, the 4-implementer superlative) — composing briefings FROM re-derived figures, not memory, remains the unmet bar.
- **120-T2 Process-Notes fixture:** 127's .review-history.md captures the material incident (the `04ad6504` backlog file filed AFTER the task-5 gate, forcing the 15-vs-14 diff-gate re-sweep at the 360°) inside the 360° section rather than a dedicated `### Process Notes` heading — intent met, heading convention drifted; worth restoring for consistency.
- **Nothing material unrecorded** — the route-D evolution, the post-gate re-sweep, the argparse hex-parse fix (seed 0x126→294), and the shellcheck citation corrections all landed in-phase.
