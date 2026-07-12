# AORTA Retrospective — Feature 128 (degraded-read-only-mode)

**Mode:** standard · **10th P004-lineage feature** (131→118→129→119→130→121→120→126→122→**128**). Facilitated by pd:retro-facilitator (opus, read-only, all figures re-derived); written by the orchestrator with the facilitator's corrections APPLIED. Active window ~3h48m (specify 2026-07-12T04:58 → implement-complete 08:46 UTC); 10 pre-finish commits off `888835ff` (finish commits land after — reflog-verified). Both skeptics used the full 3-iteration cap; zero dispatch deaths, zero retries.

## Briefing corrections (4th consecutive feature needing facilitator-caught figure corrections: 130, 126, 122, 128)

1. **"FIRST P004 feature changing LIVE behavior" was FALSE** — 118 (uuid7 floor guard), 129 (workspace-scoped queries), and 131 (doctor fix) all shipped live changes. The defensible narrow claim: 128 is the **first to change the live engine's DEGRADED-MODE ERROR CONTRACT** (silent fallback-write → fail-loud raise on the live mutation path). The superlative-label class firing again (119 battery, 120 design-gate, 126 spec-label, 122 campaign-first — now 128's live-behavior label); core counts were clean for the FIRST time this campaign.
2. **SC1 0→1→0 catch attribution:** the battery implementation reviewer caught it (fix at 572697cf), not the 360° — .review-history.md corrected with a dated marker.
3. **Half-sweep occurrence numbering retired:** "12th-13th" was imprecise against 122's "9th-10th" (granularity drift). Stated plainly: the class recurred FOUR more times this feature (three backward at relevance round 1, one upward at the 360°), all gate-caught.

## A — Activities (re-derived from .review-history.md; reflog gaps agree to the second)

| Phase | Dispatches | Blockers F/S | Gate | Proxy duration |
|---|---|---|---|---|
| specify | 5 (skeptic ×3, gate ×2) | 5 (4F/1S) | skeptic 3/3 cap; gate round 2 | not isolable (idle-dominated) |
| design | 4 (skeptic ×3, gate ×1) | 2 (2F/0S) | skeptic 3/3 cap; gate round 1 | ~52m |
| create-plan | 6 (plan, task, relevance ×2, gate ×2) | 5 (2F/3S) | relevance round 2; gate round 2 | ~1h13m |
| implement | 8 (3 implementer, deepener, battery ×3, 360°) | 0 | battery 3/3 iter-1; 360° approved | ~1h43m |

**Totals:** 23 dispatches (19 review/gate + 3 implementer + 1 deepener). Per-phase durations remain #055-lagged; proxies only.

## O — Outcomes

**Shipped (LIVE degraded-mode error contract):** `WorkflowDBUnavailableError(sqlite3.OperationalError)` + helper in models.py (D1 verbatim; cause chained never embedded; "locked"-free message riding `is_transient`); four engine branches RAISE, `_write_meta_json_fallback` DELETED (db2e4768); dead :1191 ternary deleted, :925 retained with dated 123-handoff comment, cascade-skip branch + `_SOURCE_DEGRADED` dead (391a008a); three-technique census reconciled zero-gap, fix_actions smoke, baseline 3682 → 3674 = −8 node-ID-exact (32423400); +10 deepener pins incl. the OQ-1 regression pin and the locked-ref accepted-vector pin (86fe07af); battery + 360° absorptions (572697cf, de739455). Zero new MCP code — the subclassing choice rides the existing `_with_error_handling` envelope. Suite at finish: 3684 measured (3674 + 10 deepener defs, 1 def = 1 case this time — recount discipline). Degraded READS unchanged; 5D silent degrades explicitly deferred to 123 with the :925 mitigation.

**Campaign blocker trajectory (per-retro re-derived):** 131:7 → 118:5 → 129:9 → 119:2 → 130:3 → 121:10 → 120:1 → 126:12 → 122:3 → **128:12 (8F/4S)** — ties 126 EXACTLY (total AND split) for campaign-highest. Decisive difference from 121's high count: 67% FRESH — defect discovery in the genuinely hard census-completeness problem, not review-loop friction. All 12 gate-caught; ZERO reached implement. Self-inflicted share: 3rd consecutive feature at 33%.

**"9th consecutive clean battery" — VERIFIED link-by-link** (chain through 122-retro:28 + this feature's battery section; fixed basis 130-retro:19).

**Cross-feature coordination:** #068 stands (119-owned REPLACE bypass); the :925 guard + `TransitionResponse.degraded` field + 5D conversion + typed-error pattern all handed to 123 in the spec; fix_actions un-transacted finish path recorded pre-existing/no-worse.

## R — Reflections

- **Headline: census completeness came from enumerating injection MECHANISMS, then expecting MULTIPLE TECHNIQUES per mechanism.** The old-contract test census grew at EVERY review layer — symbol-grep (missed ~13) → behavior scope (missed 2 vocab-invisible) → injection-site sweep (missed 3 MCP survivors) → the db.close() technique (missed 1 + its survivor sibling). Five passes, four methods; the iteration-3 skeptic RUNNING the design's own sweep — and the gate adding the technique the sweep's patterns couldn't see — is what converged it. No single clever grep was ever going to be complete.
- **The :925 near-miss is the feature's cautionary tale:** spec iteration-1's absorbed ":925 unreachable post-128" would have shipped a 5D loudness REGRESSION; the fresh iteration-2 skeptic re-derived it. Unverified reviewer text is input, not truth — the feature's other instance (the phantom `TestWorkflowStateDegradedMode` class name) was the same act at lower stakes.
- **Subclass-the-envelope elegance:** pinning `sqlite3.OperationalError` as the base class deleted an entire planned work item (the "new MCP mapping") — the second-cheapest line in the feature bought SC5 for free. The ponytail ladder working at the design layer.
- **Half-sweep recurred four more times (all gate-caught; the class's ~100%-caught/0%-prevented record holds).** Root cause unchanged: the sweep ran from memory instead of from grep output. The one UPWARD instance (design's correction never reaching spec.md) extends the direction-agnostic lesson to REQUIREMENTS artifacts.
- **What worked:** red-first with recorded pre-flip failures (items 1/2/3); the atomic-commit boundary honored after plan review falsified the first draft's split (the :386 existence check); task 1's self-caught import revert; the deepener's OQ-1 pin (healthy-DB-still-raises — the single test most likely to save a future regression).

## T — Tune

**Prior Tunes fired (evidence-verified, 9 of 10):** 130-T1 re-derivation (this retro's label correction; the reflog commit count) · 120-T3/126-T2 exhaustive superlatives (killed the live-behavior label pre-ship) · 126-T4 sweep-mandatory (fired at absorptions; missed 4×, gate-caught) · 126-T5 claims-trail/probe-before-author (the SC1 time-ordered variant; the measured-3684 discipline) · 131/118 non-vacuity (red-first; scratch-offender audit probe; OQ-1 pin) · 119/129-T3 citations (docs.python.org hierarchy check; sqlite_retry.py:24) · 119-T1 keep-all-gates (every create-plan gate was load-bearing — plan-review found the atomicity blocker, relevance the half-sweeps, the gate the third technique) · 120-T2 Process-Notes (all four phases) · 121-T1 adjacent-surface (fix_actions→fixer.py:155 analysis). Not triggered: 126-T3 source-class hierarchy (same as 122).

**New Tunes: NONE — 4th consecutive decline.** The facilitator's borderline candidate ("census by mechanism, expecting multiple techniques") is treated as VALIDATION of the existing enumerate-by-mechanism family, not a new standing rule — the frictions this feature were all re-fires of existing rules' execution gaps.

## Process notes

- **#055 projection lag** confirmed (started≈completed all phases); **#065 injected-observation noise** disregarded throughout (all subagents reported doing so).
- **Figure-correction streak now 4 (130, 126, 122, 128)** — but 128's was a superlative-label overstatement with core counts CLEAN for the first time; the re-derivation Tune's remaining gap is labels, not numbers.
- **Both skeptics hit the 3-iteration cap** — first feature where specify AND design both used the full allowance; both converged (no escalation). The census problem earned it.
- **Nothing material unrecorded** — the near-miss, the phantom class name, the 27→28 reconciliation, and the SC1 0→1→0 all landed in Process Notes in-phase.
