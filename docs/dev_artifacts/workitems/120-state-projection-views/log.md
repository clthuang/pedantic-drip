<!-- Append-only history of 120-state-projection-views. Entry shapes: plugins/pd/references/log-entries.md. The entries below were converted from legacy files by pd-adopt. -->

## 2026-07-10 11:07+00:00 note entity_created
Status: closed (legacy)
- kind: feature
- name: State Projection Views
- status: planned

## 2026-07-10 15:26+00:00 note entity_status_changed
Status: closed (legacy)
- old_status: planned
- new_status: archived

## 2026-07-10 16:00+00:00 note entity_status_changed
Status: closed (legacy)
- old_status: archived
- new_status: planned

## 2026-07-11 00:00+00:00 review legacy — Specify Phase (2026-07-11)
Status: closed (legacy)
### Spec review — iteration 1 (pd:spec-reviewer, opus, fresh) — approved=FALSE, 1 blocker + 4 warnings + 2 suggestions, ALL ABSORBED [1 fresh + 0 self-inflicted]
All file:line cites verified at source. Findings:
- **Blocker (FIXED, fresh):** SC4 mischaracterized `test_events.py:506` as a silent-skip pin to "update" — it is a RAW-INSERT orphan pin (bypasses append_event entirely; the guard cannot intercept it) that must be PRESERVED as the residual-surface documentation. Rewritten: NEW append_event-on-bare-conn test (raise + zero rows) + explicit preservation.
- **W1 (FIXED):** "closes the bare-connection hole" overstated — the guard is Python-API discipline; raw-SQL orphans remain structurally uncloseable in SQLite. Language scoped honestly; FR-3's STATE invariant named as the structural piece.
- **W2 (FIXED):** replay property test was VACUOUS against a rowid/insertion-order view (in-process uuid7 minting is insertion-ordered — uuid order == rowid order in every generated case). Direct-INSERT larger-uuid-first fixture mandated in SC1 + D-2 generator constraint.
- **W3 (FIXED):** baseline measures empty-HOME fixed overhead, median-only — not NFR-3's populated p50/p95 read latency. Reframed as FOUNDATION snapshot with explicit scope statement.
- **W4 (FIXED):** "uuid7 is time-ordered" tiebreak framing could mislead downstream — "latest" reframed as MAX(uuid) BY DEFINITION; cross-process same-ms is deterministic, not wall-clock-ordered.
- **S1 (FIXED):** D-3's sentinel option would AttributeError the retry-wrapper tests (:371/:409) — (a) PRAGMA probe made binding. **S2 (FIXED):** teeth tests plural (all three spellings).

### Spec review — iteration 2 (pd:spec-reviewer, opus, fresh) — approved=TRUE, 0 blockers, 3 warnings + 3 suggestions absorbed post-approval
All iter-1 fixes verified at source (confound INSERT legal — immutability triggers are UPDATE/DELETE only; uuid7 monotonic in-process confirmed forcing direct-INSERT; D-3(a) binding claim verified against the wrappers). Absorptions:
- **W1:** SC1 pre-committed to a per-axis view existing while D-1 still offered pivoted-only — option (a) DROPPED explicitly.
- **W2:** NFR-3's populated p50/p95 baseline was owned by NO feature (120 delivers overhead-median; 127 verifies against... nothing). CAPTURE assigned to feature 126 + roadmap entry-8 clarification edit landed (roadmap.md:42).
- **W3:** quoted text misattributed to prd.md:95 — actually roadmap.md:95 (restated-literal drift class). Repointed; prd.md:95 cited with its real NFR-3 wording.
- **S1:** confound fixture rows must carry DISTINCT to_values (identical values = vacuous either way). **S2:** crisp <5s non-regression guard + reuse-one-DB steer (per-case bootstrap would dominate). **S3:** guard-precedes-in_transaction note + symmetric compose-path pin.

**Skeptic gate result: PASS at iteration 2 of 3.**

### Phase-reviewer gate (pd:phase-reviewer, sonnet) — round 1 approved=TRUE, 3 warnings FIXED post-approval
All absorptions verified byte-accurate at source incl. the roadmap edit. Warnings absorbed: D-4's "entry 12" mislabel (126 is entry 8 — 12 is 125); Problem's "first consumer-adjacent feature" contradicted by 121's already-merged rename helper composing into append_event (reframed: guard closes a predating gap; 120 is the first to READ state); SC4 gains the compose-path clause item-3 committed to (self-contained checklist).

**SPECIFY PHASE: COMPLETE.** (skeptic PASS iter 2; phase gate PASS round 1. Blocker tally: 1 fresh, 0 self-inflicted — the 121-retro fresh/self-inflicted tagging convention starts here.)

## 2026-07-11 00:00+00:00 review-2 legacy — Design Phase (2026-07-11)
Status: closed (legacy)
### Design review — iteration 1 (pd:design-reviewer, opus, fresh) — approved=TRUE, 0 blockers, 1 warning + 2 suggestions absorbed post-approval [0 fresh + 0 self-inflicted blockers]
Every load-bearing claim verified at source: view DDL constructible (events.py:51-61, schema_v2.py:44); DELETE-forbidden trigger holds even for truncate-form (BEFORE DELETE disables the optimization); registration order (:89/:106/:185-186); PRAGMA probe forwards through retry wrappers (:389-394/:419-423 — sentinel would AttributeError, binding lean confirmed); :506 raw-INSERT immunity + ALL 24 append_event call sites audited FK-ON; the critical SQLite single-MAX bare-column semantics independently confirmed against sqlite.org lang_select §2.4. Absorptions:
- **W (FIXED):** D1's bare-column idiom depended on two UNSTATED preconditions — exactly-one-MAX (two+ → arbitrary source row) and no-ties (uuid is PK). Pinned as an explicit CONTRACT with the future-view rule (materialize the winning uuid, don't rely on provenance).
- **S1 (FIXED):** Testing #4's ":506 preserved — simply not modified" understated the real rationale — structural orthogonality (raw INSERT never enters append_event) + the FK-ON caller audit now stated.
- **S2 (FIXED):** D4 pins EVERY stochastic draw (incl. coin flip + uuid shuffle) to the per-case Random instance — a stray global draw would break SC3's determinism.

### Phase-reviewer gate (pd:phase-reviewer, sonnet) — round 1 approved=TRUE, ZERO issues (third clean design gate: 118, 119, 120 — "campaign-first" label corrected 2026-07-12 by 120 retro cross-check vs 118-retro:14/119-retro:18)
All SC↔decision maps 1:1 verified; all three absorptions byte-accurate; roadmap.md:42/:45/:95 ownership story verbatim-consistent; per-axis-absence vs pivoted-all-NULL distinction traced through the actual DDL; axis-generic naming validated against roadmap.md:43 (122 will literally claim `pipeline_phase`); events.py:52 PK confirmed (no MAX ties); 7-row inventory complete. Reviewer independently disproved a fabricated injected observation ("guard set missing display.py") — #065 pattern, handled correctly.

**DESIGN PHASE: COMPLETE.** (skeptic PASS iter 1; phase gate PASS round 1, zero issues.)

## 2026-07-11 00:00+00:00 review-3 legacy — Create-Plan Phase (2026-07-11)
Status: closed (legacy)
### Plan review — iteration 1 (pd:plan-reviewer, opus, fresh) — approved=TRUE, 0 blockers, 1 warning + 4 suggestions, ALL ABSORBED post-approval
All line anchors verified current (bench-session-start.sh:17 dirty-exit-2, :73 tracked-file overwrite, :82-84 medians-before-gate, :86-89 NFR2 exit-1). Findings:
- **W (FIXED):** step 4's bench run OVERWRITES tracked `plugins/pd/hooks/tests/bench-results.txt` (do-not-re-commit convention) — `git restore` after stdout capture added to plan step 4 + task 4.
- **S1 (FIXED):** "determinism smoke" label vacuous as a determinism proof — reworded to identical pass/fail outcome AND case structure (both derive from MASTER_SEED); uuid7 values legitimately differ run-to-run (wall-clock-encoded).
- **S2 (FIXED):** <5s assert message carries measured elapsed (a trip reads as "tune N", not a mystery flake).
- **S3 (FIXED):** bench exit code is NOT this feature's gate — its internal NFR2 50ms check can exit 1 on noise; medians echo before it; capture stdout regardless.
- **S4 (FIXED):** dropped the "24 call sites" literal (actual ~27) — property claim kept, exact count declared irrelevant.

### Task review — iteration 1 (pd:task-reviewer, sonnet) — approved=TRUE, 0 blockers, 3 warnings + 3 suggestions, ALL ABSORBED post-approval
File-disjointness of task 3 independently confirmed; views.py+needle-allowlist bundling in task 1 validated (splitting would self-trip the dark-module scan). Findings:
- **W1 (FIXED):** task-2 "identical results" ambiguous — could nudge implementer toward seeding generate_uuid7; explicit do-NOT-seed steer + structure-vs-values distinction written in.
- **W2 (FIXED):** task-3 Verify lacked the red-first demonstration — "guard tests (a)/(b) RED before the PRAGMA probe lands, green after" added.
- **W3 (FIXED):** task-4 machine context dropped CPU from design D7's three-part list — `sysctl -n machdep.cpu.brand_string` added.
- **S1-S3 (FIXED):** D5 cite in task-3 Why; file-disjoint-serialized-for-reviewer-clarity parenthetical in the summary row; bench-results restore in task 4 (converged with plan-reviewer W).

### Relevance-verifier (pd:relevance-verifier, sonnet) — approved=TRUE, ZERO issues
Full spec→design→plan→tasks chain literal-by-literal: view/column names, six D5 fixtures, property-test parameters, #061 guard placement + :506 preservation, 3-needle/3-teeth extension, 7-row inventory — all byte-consistent. Every file:line citation resolved at live source. Went BEYOND cited lines: independently traced test_display.py's rename_entity call sites (transitively append_event) — all connect_v2, confirming the guard's zero-regression claim suite-wide.

### Phase-reviewer gate (pd:phase-reviewer, sonnet) — round 1 approved=TRUE, 2 suggestions absorbed post-approval
All five handoff criteria pass; context-free-implementer check pass. Absorbed: events.py full path on first task-1 mention; task-4 Why's SC6 citation corrected to design Testing Strategy #5 (the teeth portion of SC6 lives in task 1 via D6, not D7). Reviewer again correctly disregarded injected observations (#065 pattern).

**Process notes:** my first absorption edit-script run aborted on a case-mismatch anchor ("The existing suite", capital T) — assert-before-write held, zero partial writes; second run clean.

**CREATE-PLAN PHASE: COMPLETE.** (plan-reviewer PASS iter 1; task-reviewer PASS iter 1; relevance-verifier PASS, zero issues; phase gate PASS round 1. Blocker tally: 0 fresh + 0 self-inflicted — second consecutive zero-blocker phase this feature.)

## 2026-07-11 14:23+00:00 note entity_status_changed
Status: closed (legacy)
- old_status: planned
- new_status: active

## 2026-07-11 14:59+00:00 phase start -> specify
Status: closed (legacy)

## 2026-07-11 14:59+00:00 review specify — legacy
Status: closed (legacy)
Iterations: 2
"{\"skeptic\": \"opus x2 fresh \u2014 iter1 FALSE (1 fresh blocker: SC4 mischaracterized the raw-INSERT pin test_events.py:506 as updatable silent-skip; 4W incl. rowid-confound VACUITY of the property test + baseline fitness + overstated closure), iter2 TRUE (3W absorbed: D-1 pivoted-only dropped, NFR-3 populated-p50/p95 baseline capture ASSIGNED to 126 w/ roadmap entry-8 edit, prd/roadmap :95 citation repoint)\", \"phase_gate\": \"round1 TRUE, 3 warnings absorbed (entry-number mislabel; 121's rename helper already composes into append_event \u2014 'first consumer' narrative fixed; SC4 compose-path clause)\", \"tally\": \"blockers 1 fresh / 0 self-inflicted \u2014 fresh/self-inflicted tagging (121 retro Tune-2) starts this feature\", \"shape\": \"dark views.py (per-axis primitive + pivoted face, MAX(uuid) by definition) + stdlib seeded replay property test w/ rowid-confound constraint + #061 PRAGMA guard + 3-needle teeth; live: empty-state latency FOUNDATION snapshot artifact\"}"

## 2026-07-11 15:21+00:00 phase specify -> design
Status: closed (legacy)

## 2026-07-11 15:21+00:00 review design — legacy
Status: closed (legacy)
Iterations: 1
"{\"design_skeptic\": \"opus iter1 TRUE 0 blockers (1W+2S absorbed: bare-column idiom's two-precondition CONTRACT [exactly-one-MAX + PK-no-ties, sqlite.org \u00a72.4 independently confirmed]; per-case-Random pin for ALL draws; :506 structural-orthogonality rationale + 24-caller FK-ON audit)\", \"phase_gate\": \"sonnet round1 TRUE ZERO issues \u2014 campaign-first clean design gate; disproved an injected fabricated observation (#065 pattern)\", \"decisions\": \"D1 per-axis GROUP BY MAX primitive + pivoted-from-entities face, axis-generic column names (122 owns vocab); D2 load-bearing events import for registry order; D3 PRAGMA probe guard; D4 one-DB property run w/ per-case namespaces + seeded shuffled-insert; D5 six deterministic fixtures; D6 3-needle teeth; D7 baseline artifact w/ scope statement\", \"tally\": \"blockers 0 fresh / 0 self-inflicted\"}"

## 2026-07-11 15:59+00:00 phase design -> create-plan
Status: closed (legacy)

## 2026-07-11 15:59+00:00 review create-plan — legacy
Status: closed (legacy)
Iterations: 1
"{\"plan_reviewer\": \"approved iter 1: 1W (tracked bench-results.txt restore) + 4S, all absorbed\", \"task_reviewer\": \"approved iter 1: 3W (determinism-smoke ambiguity, red-first missing, CPU context) + 3S, all absorbed\", \"relevance_verifier\": \"approved, ZERO issues; FK-ON claim independently traced suite-wide\", \"phase_gate\": \"approved round 1, 2S absorbed\", \"blockers\": \"0 fresh + 0 self-inflicted\"}"

## 2026-07-11 17:20+00:00 phase create-plan -> implement
Status: closed (legacy)

## 2026-07-11 17:20+00:00 review implement — legacy
Status: closed (legacy)
Iterations: 1
"{\"tasks\": \"4/4 landed iteration 1, serial, zero rework\", \"deepener\": \"+14 tests; closed a real axis-filter mutation hole\", \"battery\": \"implementation(opus)+quality(sonnet)+security(opus) ALL approved iteration 1 \u2014 6th consecutive clean battery\", \"relevance_360\": \"approved; 1 stale-docstring warning fixed (half-sweep adjacent-paragraph class)\", \"suite\": \"3586 passed post-deepening\", \"blockers\": \"0 fresh + 0 self-inflicted\"}"

## 2026-07-12 02:12+08:00 qa legacy .qa-gate.json
Status: closed (legacy)
Verdict: PASS
```json
{
  "feature": "120-state-projection-views",
  "gate_date": "2026-07-12",
  "verdict": "PASS",
  "lanes": {
    "A_execution_adversarial": {
      "agent": "general-purpose/sonnet",
      "verdict": "PASS",
      "high": 0,
      "med": 1,
      "low": 2,
      "notes": "681-event hand-folded oracle match (adversarial values, same-ms bursts, shuffled raw-inserts); orphan primitive-vs-face contract holds; NULL semantics correct; ~30k concurrent poll iterations with 0 torn reads (4- and 6-writer zero-jitter contention); guard holds against PRAGMA-off, open-transaction, and executescript sneaks. MED: per-entity entity_state lookup measured O(total events) \u2014 absorbed into backlog #067 + views.py scale comment (dark module, no live consumer; not a regression). LOW: lying duck-type proxy defeats the pragma self-report (equal-effort to the documented raw-INSERT residual; docstring caveat added); ordinary SQLite write-privilege can add INSTEAD OF triggers / drop immutability triggers (generic substrate fact, recorded in sidecar)."
    },
    "B_regression_integration": {
      "agent": "general-purpose/sonnet",
      "verdict": "PASS",
      "high": 0,
      "med": 0,
      "low": 0,
      "notes": "Suites 3586/3586 (ran twice, identical); hooks 67/67; validate 0 errors/21 pre-existing warnings; doctor pin EXPECTED_CHECK_COUNT=19 intact (142 doctor tests green); tree clean after all runs; bench-results.txt diff empty; 17-file inventory fully sanctioned; dark-module grep zero live importers; 121 surfaces 80/80 and 119 surfaces 95/95 green. Pre-existing tracked items confirmed unrelated: migration-11 concurrent-runner flake (backlog-manual ~5% baseline; 15/15 isolated reruns green on this branch, 8/8 on a develop worktree), ResourceWarning GC flicker (database.py:897, untouched), tracked plugins/pd/.claude migration stray (backlog #066)."
    },
    "C_artifact_truth_audit": {
      "agent": "general-purpose/opus",
      "verdict": "PASS",
      "high": 0,
      "med": 0,
      "low": 4,
      "notes": "First dispatch died instantly with garbage output (0 tool uses) \u2014 re-dispatched once per fallback policy; retry completed fully. No fabricated cites (the 121 class). All 10 shas, campaign figures, named tests, streak chains, and tune-edit claims verified at source; suite-count arithmetic reconciles (1503+14=1517; 3572+14=3586; 62 collected). 4 LOW cite-precision fixes ALL APPLIED to retro.md: events.py:140\u2192:150-157 stale-claim location; 119-retro:21\u2192:20 off-by-one; #065 vantage basis made explicit; implement suggestion tally parenthetical."
    }
  },
  "policy": "HIGH blocks; MED fix-or-file; LOW fix-or-sidecar",
  "dispositions": {
    "med": [
      "lane A entity_state per-entity scaling \u2192 measured data folded into backlog #067 and the views.py scale comment (obligation carrier for feature 132)"
    ],
    "low_fixed": [
      "retro.md cite corrections \u00d74 (lane C)",
      "events.py guard docstring self-report caveat (lane A)"
    ],
    "low_sidecar": [
      ".qa-gate-low-findings.md: SQLite write-privilege trigger tampering residual; lane B methodology note (parallel-run flake artifact, isolated reruns authoritative)"
    ]
  }
}
```

## 2026-07-11 18:12+00:00 phase implement -> finish
Status: closed (legacy)

## 2026-07-11 18:12+00:00 note entity_status_changed
Status: closed (legacy)
- old_status: active
- new_status: completed

## 2026-07-11 18:12+00:00 review finish — legacy
Status: closed (legacy)
Iterations: 1
"{\"qa_gate\": \"3-lane PASS \u2014 A execution-adversarial (0H/1M/2L, MED folded into #067), B regression (all 7 items green), C artifact-truth (0 fabricated cites, 4 LOW fixed; re-dispatched once after instant-death first attempt)\", \"retro\": \"campaign-cleanest: 1 fresh blocker, 0% self-inflicted; 4 prior Tunes verified fired; 4 new Tunes applied\", \"backlog\": \"#061 closed; #067 filed+enriched with measured scaling data\"}"

## 2026-07-12 00:00+00:00 review legacy — Implement Phase (2026-07-12)
Status: closed (legacy)
### Task execution (pd:implementer × 4, sonnet, serial) — all landed at iteration 1, zero rework
- **Task 1** (2dbf4482): views.py DDL byte-verified against design D1 via extracted-block diff (not retyped); teeth demonstrated red-first (3 failed pre-needles → 3 passed); 43 green scoped. Implementer re-verified the design's sqlite-version citation empirically and corrected 3.51.0 → 3.53.2 (design.md synced — a briefing-figure-class stale literal caught at implementation).
- **Task 2** (fd1e4c40): 200-case property test; non-vacuity probed via min-fold oracle (seed-carrying failure) then byte-clean revert; rowid-confound EMPIRICALLY confirmed firing (case 2: larger uuid at insertion position 0); global-random discipline regex-verified; 104/200 raw-insert; ~1.25s vs 5s guard.
- **Task 3** (cf9a542f): #061 guard verbatim D3; red-first (DID NOT RAISE ×2 pre-guard); :506 preserved (zero deletions in file diff); full sweep 1503 passed, zero regressions — design's FK-ON caller audit held.
- **Task 4** (78c7f730, orchestrator-inline): bench at clean tree — 227/228ms medians, delta 1ms; bench-results.txt restored; latency-baseline.md with scope statement; suite 3572 + validate 0 errors + hooks 67/67; inventory matched by name.

### Test deepening (pd:test-deepener, sonnet) (0eaf8f33) — 14 tests across six dimensions
Found and closed a REAL mutation-resistance hole: dropping the execution-axis filter from an entity_state subquery slipped past EVERY deterministic fixture via iteration-order coincidence — closed by parametrizing the two-of-three-axes boundary over all three missing-axis cases. Mutations verified empirically (MAX→MIN, GROUP BY dropped, filter dropped; hand-edit → run → byte-clean restore). Two holes analytically argued, not empirically closable (scalar-subquery fan-out tripwire; value-dedup rewrite class). 1517 entity_registry green.

### Reviewer battery — iteration 1, ALL THREE APPROVED (6th consecutive clean battery: 118, 129, 119, 130, 121, 120)
- **pd:implementation-reviewer (opus):** approved. 1 warning — review harness had no shell, suite execution not certified; CLOSED by orchestrator full-suite run post-deepening (3586 passed). 1 suggestion — :506 byte-identity not git-diffable in-harness; CONFIRMED by orchestrator (zero deletion lines vs develop). Independently re-verified the D1 bare-column idiom against sqlite.org.
- **pd:code-quality-reviewer (sonnet):** approved, 0 blockers/warnings. 1 suggestion ABSORBED (143b2251): scale-expectation comment beside entity_state DDL — recompute-on-read + unverified nested-view plan; 132's cutover must EXPLAIN QUERY PLAN at live scale. Verified per-case Random discipline by grep, deepener classes non-redundant.
- **pd:security-reviewer (opus):** approved, ZERO issues. Static DDL (no interpolation), views expose a strict SUBSET of events columns (narrow, not widen; payload/actor omitted), guard message leaks nothing, tmp_path hygiene, no new deps; view read-only-ness externally verified (INSTEAD OF trigger docs).

### 360° relevance verification (pd:relevance-verifier, sonnet) — approved
SC1-SC6 re-derived from shipped code; reverse-traceability clean (every change maps to an obligation or recorded absorption); no scope creep; dark-module invariant grep-verified repo-wide; bench-results.txt's untouched foreign sha cited as positive evidence the git-restore ran. Findings:
- **W (FIXED):** append_event docstring's "json.dumps runs BEFORE any SQL" invalidated by the #061 probe (a SQL read now precedes it) — the half-sweep class, adjacent-paragraph edition; D3 scoped one docstring line and the neighboring literal went stale. Reworded: before any WRITE; probe precedes; both pinned by test.
- **S (this section):** review-history/.meta.json lacked the implement section — expected sequencing; closed by this append + complete_phase.

**Process notes (implement):** task-4 tree-check first attempt used inverted shell logic (`git status --porcelain && echo DIRTY` — echoes on exit-0 regardless); recovered immediately with `[ -z "$(...)" ]`, zero impact. Recorded per 120-retro Tune-2 (required implement Process Notes fixture).

**IMPLEMENT PHASE: COMPLETE.** (4 tasks iter-1; deepener +14; battery 3/3 approved iter-1; 360° approved. Blocker tally: 0 fresh + 0 self-inflicted — third consecutive zero-blocker phase. Post-battery absorptions: 2 commits, suite 3586 green.)
