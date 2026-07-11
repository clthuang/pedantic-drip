# AORTA Retrospective — Feature 120 (state-projection-views)

**Mode:** standard · **Branch:** `feature/120-state-projection-views` · **7th P004-lineage feature** (execution order 131 → 118 → 129 → 119 → 130 → 121 → **120**). Facilitated by pd:retro-facilitator (opus, read-only, all figures re-derived from primary sources); written by the orchestrator. Implement-complete commit `37dc9b07`, ~3h wall-clock after 121's completion.

## Provenance / re-derivation note

Per the standing briefing order (*trust no number in the prompt*), every figure is cited to a primary source. Re-derivation catches this feature:

- **Injected "prior observation" system-reminders disregarded** (the #065 pattern), including one asserting "11 Files Changed, 1333 Insertions, 7 Deletions" — conflates code + doc files and is not corroborable from the design's 7-row inventory (design.md:82-92); rejected. Second retro-layer vantage on #065 (121-retro obs-6 was the first at this layer; counting the original 121-implement filing it is the third overall).
- **"campaign-first clean design gate" (.review-history.md:36) — OVERSTATED self-label**, corrected with dated marker: 118's and 119's design gates were also clean 0/0 (118-retro:14, 119-retro:18). Defensible claim: **third clean design gate** (118, 119, 120) and **second fully-clean design phase** (skeptic iter-1 + gate 0/0: 119, then 120). Same self-label-miscount class as 130's "(second consecutive)" correction of 119.
- **"6th consecutive clean battery" — VERIFIED** (chain: 118-retro:22 → 129-retro:57 → 119-retro:20 → 130-retro:19 → 121-retro:19 → .review-history.md:79). Caveat: 131's battery was also all-approved-iter-1 (131-retro:21); its exclusion is definitional (streak basis fixed at 130-retro:19 counts P004 features benefiting from 131's encoded guardrails), not because 131's battery was dirty.
- **"zero-blocker phases" — TRUE for design + create-plan + implement** (3 consecutive); specify carried the feature's 1 fresh blocker. The feature is not all-zero-blocker.

## A — Activities (re-derived)

Durations: `.meta.json` phase timestamps unusable (9-14s started≈completed windows — the end-of-phase transition+complete artifact documented since 119-retro:13). Reflog commit-gap proxies used.

| Phase | Dispatches | Blockers (fresh/self) | Findings absorbed | Gate | Proxy duration |
|---|---|---|---|---|---|
| specify | 3 (skeptic ×2, gate ×1) | 1 / 0 | 1B + 10W + 5S | PASS iter 2/3; gate round 1 | ~22m |
| design | 2 (skeptic ×1, gate ×1) | 0 / 0 | 1W + 2S | PASS iter 1; gate 0-issue | ~38m |
| create-plan | 4 (plan, task, relevance, gate) | 0 / 0 | 4W + 9S | all PASS iter 1 | ~14m |
| implement | 9 (4 implementer, deepener, battery ×3, 360°) | 0 / 0 | 2W + 2S (+1 self-referential 360° bookkeeping S, excluded from the tally); +14 deepener tests | tasks iter-1; battery 3/3; 360° approved | ~1h13m |

**Totals:** 18 agent dispatches (13 review/gate + 4 implementer + 1 deepener). Absorption rate ≈ 100% — only deferrals are explicit ownership transfers: NFR-3 populated baseline → 126/127 (.review-history.md:17); #061 closure → finish (design.md:92); nested-view scale benchmark → 132 cutover (views.py scale note, commit `143b2251`). Fresh/self-inflicted tagging (121-Tune-2) adopted here for the first time (.review-history.md:26).

## O — Outcomes

**Commit trail (develop..HEAD = 10 pre-finish commits):** `964e7dce` specify · `25e2afd2` design · `35d83579` create-plan · `2dbf4482` task1 · `fd1e4c40` task2 · `cf9a542f` task3 · `78c7f730` task4 · `0eaf8f33` deepener · `143b2251` scale-note · `37dc9b07` implement-close. Merge-base `641a57be`.

**Shipped surface (verified at source):** NEW `views.py` (91 lines; `_VIEWS_DDL` byte-matching design D1; load-bearing events import; two-precondition bare-column CONTRACT docstring) · `events.py` #061 PRAGMA guard as append_event's first statement · NEW `test_views.py` (six D5 fixtures, 6 immutability pins, column-set pin, 200-case seeded replay property test, 7 deepener classes) · `test_events.py` guard tests + preserved `:506` orphan pin · `test_schema_v2.py` dark-module extension (3 needles, 3 teeth) · NEW `latency-baseline.md` (227/228 ms medians, +1 ms delta, empty-HOME scope statement).

**Gates:** every gate green. Deepener closed one REAL mutation hole (dropped execution-axis subquery filter slipped every deterministic fixture via iteration-order coincidence — closed by parametrizing the two-of-three-axes boundary). Suite 3586 passed post-deepening.

**Campaign placement:**

| Feature | 131 | 118 | 129 | 119 | 130 | 121 | **120** |
|---|---|---|---|---|---|---|---|
| Total blockers | 7 | 5 | 9 | 2 | 3 | 10 | **1** |
| Self-inflicted | — | — | — | — | — | 5 (50%) | **0 (0%)** |

120 is the campaign blocker LOW (below 119's 2) with the cleanest self-inflicted profile — the exact inverse of 121's 50%.

## R — Reflections

**What worked:**
- **Front-loaded rigor → a 1-blocker feature.** One fresh spec blocker, then three consecutive zero-blocker phases and a clean iter-1 battery — the sharpest instance yet of the 118/129 "front-load skeptic rounds → implement goes 1-and-done" pattern (118-retro:45).
- **Design pinned an API-behavior claim to primary docs.** The bare-column-with-MAX idiom's two-precondition CONTRACT verified against sqlite.org lang_select §2.4 AND empirically on the venv — direct fire of 119-Tune-3 / 129-Tune-3.
- **Non-vacuity designed in at spec, enforced at deepen.** Spec iter-1 W2 killed the rowid-confound vacuity (in-process uuid7 is insertion-ordered — a rowid-latest view would have passed every naive case); the deepener then caught the axis-filter hole. Two independent fires of the 131/118 non-vacuity guard.
- **Fresh/self-inflicted tagging paid off on first use** — 120's "1 blocker, 0%" is legible against 121's "10, 50%" with zero re-derivation.

**What didn't:**
- **The half-sweep/adjacent-literal class recurred — now inside CODE.** The D3 guard (a PRAGMA read preceding `json.dumps`) left the neighboring append_event docstring's "json.dumps runs BEFORE any SQL" claim stale; D3 scoped one docstring line and the adjacent literal rotted. Caught at the last gate (implement 360°). Lineage: 131 (RC4, intra-doc) → 130 (stale inventory) → 121 (half-swept restatements ×4, all artifacts) → **120 (the class migrates from prose artifacts into a shipped code docstring — the stale claim sat at events.py:150-152 pre-fix, reworded at :153-157; cite corrected 2026-07-12 by QA lane C from an erroneous :140)**. The post-contract-fix sweep must now cover code docstrings/comments adjacent to a changed contract — Tune 1.
- **The briefing-figure guardrail fired twice:** (i) task-1 implementer re-derived the design's sqlite version, correcting stale 3.51.0 → 3.53.2 against the live venv; (ii) this retro rejected the injected 11-files/1333-insertions observation. Both are the CLAUDE.md "Dispatch-briefing figures are restated literals too" class working as intended.
- **Create-plan three-gate convergence didn't replicate:** relevance-verifier was zero-issue at create-plan (unlike 130/121 where it caught distinct blockers there) but earned its keep at the implement 360° instead. "Keep all three mandatory" still validates; "all three independently productive at create-plan" did not.

## T — Tune

**Prior Tune actions that demonstrably paid off this feature:**
1. **130-Tune-1 briefing-figures guardrail — PAID OFF (high):** sqlite 3.51.0→3.53.2 catch + this retro's injected-figure rejection.
2. **121-Tune-2 fresh/self-inflicted tagging — ADOPTED & PAID OFF (high):** first eligible feature; made the campaign table one-glance derivable.
3. **131/118 non-vacuity guard — FIRED (high):** spec W2 rowid-confound + deepener axis-filter hole.
4. **119/129-Tune-3 behavior-claims-need-citations — FIRED (high):** D1 CONTRACT vs sqlite.org + venv.
5. **119-Tune-1 keep-all-create-plan-gates — VALIDATED with nuance (medium):** relevance-verifier idle at create-plan, load-bearing at 360°.

**Still unproven / not exercised:** 121-Tune-1 (adjacent-surface check on scope-widening fixes — no scope-widening fix occurred); 129-Tune-1 (blocker severity split — mooted by n=1); 129-Tune-5 (skip confirmatory reruns — every gate one-round).

**New Tune actions (applied at finish):**
1. **Extend the post-contract-fix sweep to adjacent code docstrings/comments** — CLAUDE.md mechanical-sweep line extended. Signal: events.py:140 stale ordering claim. Confidence: high.
2. **Make implement-phase Process Notes a required .review-history.md fixture** — recurrence of the 129/130 "recovered-but-unrecorded incident" anti-pattern (task-4's inverted tree-check one-liner went unrecorded until this retro flagged the gap; 121 formalized Process Notes and 120's implement section still lacked one). Applied: incident now recorded; implement.md gains the requirement. Confidence: high.
3. **Superlative self-label check** — "campaign-first/Nth-consecutive" claims must be verified against the prior-retro chain before entering an artifact (two corrections in two features: 119's battery label, 120's design-gate label). Appended to the CLAUDE.md briefing-figures guardrail. Confidence: medium-high.
4. **Carry the nested-view scale-benchmark obligation into 132's spec inputs** — currently held only by a code comment + quality suggestion (weakest carrier; echoes 118's SQLITE_LOCKED docstring-only risk that 119 nearly missed). Filed as backlog watch-item #067. Confidence: medium.

## Process notes

- **#065 injected-observation noise:** disregarded by this retro, by the create-plan phase gate, and by the design gate (fabricated "guard set missing display.py" disproven) — three independent vantages this feature.
- **sqlite-version stale citation:** task-1 implementer re-verified empirically, corrected 3.51.0 → 3.53.2, design.md synced. Briefing-figure class caught at the implement layer.
- **Task-4 tree-check shell-logic inversion (orchestrator, recovered immediately):** `git status --porcelain && echo DIRTY` echoes DIRTY on exit-0 regardless of output — replaced with `[ -z "$(git status --porcelain)" ]`. Zero impact (the correct check ran before the bench); recorded here because it initially went unrecorded — the very gap Tune 2 closes.
- **Create-plan edit-script anchor mismatch:** case-sensitive anchor aborted run 1; assert-before-write held, zero partial writes.
