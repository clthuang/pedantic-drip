# Retrospective: 123-unified-transition-engine

**Completed:** 2026-07-13 · **Branch:** feature/123-unified-transition-engine → develop · **P004 cluster 2 (FR-7)**
**Verdict:** shipped clean — 0 production defects past deepener/battery/360°; **11 blockers** (~82% self-inflicted, 2 documented swings); joint third-highest with 125, behind the twin 12s (126/128); residual blind spots named — intra-design D-section collisions (novel) + the persistent half-sweep execution gap.

Facilitator: pd:retro-facilitator (opus, read-only), all briefing figures re-derived from `.review-history.md`, `.meta.json`, the 4 artifacts, and chain-verified against 125/retro.md.

## Briefing verification (3 corrections + 1 flag — 123 is NOT a zero-correction briefing)

| Briefed | Corrected | Root cause |
|---|---|---|
| specify 5 blockers (2+2+1) | **4 (2+2+0)** — i3 approved 0B (2 warnings, not blockers); `.meta.json specify.blockers_total = 4` | "2+2+1" mis-transcribed from 125-retro:11, where 125's *own* spec had a post-cap i3 blocker. The dispatch-briefing-restated-literal class; re-derivation caught it. |
| TOTAL 12 | **11** (4+5+2+0) | Cascade from the specify error. |
| trajectory "123:12 — three-way tie rank-1 (126/128/123)" | **123:11 — joint third-highest with 125**, behind the twin 12s. No three-way tie. | Same cascade. 125-retro:21 called itself "sole rank-3" — accurate then; now joint. |
| H1 crash variant at "get_state" | site is `_derive_completed_phases` ("Unknown phase: discover") | Naming slip; substance correct. |
| half-sweep "~6×" | **5 distinct** — "spec-i3-B" maps to no blocker (i3 was 0B); "D7-S1-citation" double-counts the :416-426 fix relevance-r1-B closed | Over-count. |
| 22 commits (flag: read-only facilitator could only corroborate via `.meta.json` sums 5+5+6+6) | **git-verified by orchestrator pre-dispatch:** `git rev-list --count 64ab6b9e..HEAD` = 22 | Closed per 125-A5. |

**Streak bookkeeping:** 123's briefing needed corrections → **125 remains the sole zero-correction briefing** (worded per 125-retro:5: first since the corrections streak 130→126→122→128→127). 123 does not extend it.

## Activities (re-derived)

| Layer | Rounds | Blockers | Note |
|---|---|---|---|
| Spec skeptic (opus, fresh/round) | 3 (cap) | **4** (2+2+0) | i3 approved clean; 2 post-cap warnings gate-verified |
| Specify gate (sonnet) | 1 | 0 | 2 warnings — both cross-contract grep collisions; **the 125 guardrail's first live catches** |
| Design skeptic (opus, fresh/round) | 3 (cap) | **5** (2+3+0) | i3 approved; 5 post-cap warnings; 7 upward sweeps into spec (relevance r1: 6/7 propagated clean) |
| Design gate (sonnet) | 1 | 0 | 3 warnings |
| Plan-reviewer (opus) | 2 | **1** | i1-B1 = engine.py:111 **design-internal D3-vs-D8 contradiction**; i2 approved |
| Task-reviewer (sonnet) | 1 | 0 | parallel w/ plan-i1, verdicts extracted after both returned (countermeasure); 6W/2S |
| Relevance-verifier (sonnet) | 2 | **1** | r1-B = spec :416-426 half-sweep (5th); r2 approved, 24/24 hazards exact |
| Battery (opus/sonnet/opus) | 1 | 0 | **12th consecutive iteration-1-clean** |
| 360° (shell) | 1 | 0 | concurrent-run transient (hooks 66/67, validate 1 err) — same contention artifact as 125's 360°; isolated re-runs clean |

**Total: 11 blockers.** Trajectory: 131:7→118:5→129:9→119:2→130:3→121:10→120:1→**126:12**→122:3→**128:12**→127:10→125:11→**123:11** (joint 3rd with 125, behind the twin 12s).

## Outcomes

**Shipped (0 production defects past deepener/battery/360°):** P004 FR-7 delivered (prd.md:85, cluster-2). The split `ENTITY_MACHINES` + `WorkflowStateEngine` pair collapsed into a per-kind router via a **descriptor/validator split**: all 8 machines implement `GraphDescriptor` (SC1 graph-diff harness enumerates it); FiveDMachine + LifecycleMachine add `validate()`; **FeatureMachine is descriptor-only — feature validation stays in the frozen engine, wrapped by dispatch.** `route_transition` was dropped entirely (design-i2-B1); router.py owns REGISTRY+machines, dispatch stays the two existing MCP surfaces consuming `get_machine(kind)`. D8 zero-engine-changes held except the one forced `engine.py:111` kwarg drop.

**Tests:** 3737→**3810** passed / 3 skipped (+73: +37 router/task-1, +8 task-2, +27 deepener, +1 protocol smoke). **validate.sh:** 0 err / 11→**9** warnings. Hooks 67/67. Diff gate: 14 non-docs files, every one ∈ D8.

**Latent bug fixed (behavior change — CHANGELOG-worthy):** 5D **backward** transitions previously returned `allowed=True` but **skipped the DB write** (never persisted). The unified `if decision.allowed: write` path now persists on backward, matching the frozen engine's warn-and-write (G-18). Git-verified at merge-base (`git show 64ab6b9e:…entity_engine.py` :508-546 — old branch early-returned before the :549-551 write). No test pinned the old skip-write quirk.

**Artifacts stayed compact pointer-style** despite the heavy loop: spec 74, design 86, plan 57, tasks 29 lines. Friction was in *precision* (citations/sweeps/contradictions), not volume — the "thin-pointer + attach-full-set-at-dispatch" pattern (task-rev S2).

**Backlog:** #072 filed (security S1 — generic-handler `str(exc)` sanitization, pre-existing).

## Reflections

**R1 — Cross-contract collision has an INTRA-artifact variant the 125 guardrail doesn't cover (signature).** `engine.py:111` was a **D3-vs-D8 contradiction inside the design itself**: D3 said ":478-546 deleted / expected zero engine changes" while D8 item-4 + the frozen engine's `TransitionResponse(…, degraded=False)` constructor forced a real edit. It survived all four design rounds (i1/i2/i3/gate) and was caught only at plan-i1 — one artifact later. The 125 guardrail checks *spec-SC vs design-content*; it does not check *design-D-section vs design-D-section*. Meanwhile the guardrail's first live catches landed at the 123 specify gate (2 collisions: models.py:27-31 comment in SC3 scope; SC4 secondary grep repo-wide). → Action A3 (#073).

**R2 — Implementer as de-facto last reviewer held (matches 125-R2).** Two implement adjudications, both flagged not silent, both verified: (a) `entity_lifecycle\b` gate narrowing — literal sweep hit a concept function-name (`test_entity_lifecycle_valueerror_…`), pattern narrowed to a word boundary, 0 final hits; (b) backward-write parity (Decision #1) — flagged for battery, git-confirmed. The implementer also self-caught two docstrings tripping its own sweep and an over-greedy Edit (grep-and-recompute, not assumption).

**R3 — Both standing countermeasures held, no regressions.** Parallel-review absorption discipline: plan+task verdicts extracted after all returned; battery extracted all 3 before any absorption. Collision guardrail: live catches at gate (×2) and plan (engine.py:111). Zero repeat of a prior incident.

**R4 — Half-sweep / incomplete-restatement is still the #1 execution gap.** Re-fired **5×** (design-i2-B2 deletion-scope; design-i3-W5 spec :508-546 residue = "4th"; plan-i2-W1 tasks Files annotation; relevance-r1-B spec :416-426 = "5th"; + the design-i1-S2 origin). 100% gate-caught, 0% prevented — identical to 125-R4. The mechanized grep-sweep (task-1 acceptance, plan-i2 S1) was introduced mid-feature and worked for that one sweep, but the class kept re-firing on OTHER restatements. The gap is executing the sweep from grep output, not rule coverage. → Action A4 (#074).

**R5 — Adversarial loop again produced the architecture AND surfaced a latent bug (matches 125-R5).** The descriptor/validator split + route_transition drop + frozen-engine-stays-feature-validator all came from blocker resolutions (design i1-B1, i2-B1). The validate+write collapse is what exposed the backward-write-skip bug. Architecture + latent-defect value, near-zero downstream tax.

### Per-layer catch analysis (reachable earlier?)

- **Caught at first review of the introducing artifact, or one round after an absorption introduced them** — fresh-reviewer-per-round working as designed: spec-i2-B1 (regression from i1-W3), design-i2-B1 (route_transition from i1-B1 fix), design-i2-B2 (from i1-S2), relevance-r1-B (from task-rev-S1's :416-426 fix landing in design+plan but not spec).
- **One clear earlier-reachable escape: plan-i1-B1 (engine.py:111).** A design-internal contradiction that should have been a design-gate catch (D8 "expected zero changes" vs D3 deletion + the :111 constructor). Escaped 4 design rounds. This is R1's signature.
- **design-i2-B3 (:6367 third producer site)** reachable at design-i1 with a complete 42-occurrence sweep; the i1-W1 reviewer under-swept and asserted "only such site besides :6583" — a false reviewer-claim caught by the i2 fresh reviewer (reviewer-claim-not-self-verifying).

### Fresh vs self-inflicted split

**~2F / 9S — ~82% self-inflicted** (range 0–2 fresh depending on swing calls; 82–100% self). Notably higher than 125's ~64%.

- **Self-inflicted (9):** spec-i1-B1 (spec falsely said task status-only vs 4 live code sites), spec-i1-B2 (SC3 mis-scoped/mis-cited), spec-i2-B1 (absorption regression), design-i1-B1 (protocol unimplementable + internal contradiction), design-i1-B2 (fabricated "five reads"→actual three), design-i2-B1 (route_transition unwired), design-i2-B2 (deletion-scope half-sweep), plan-i1-B1 (engine.py:111 design-internal), relevance-r1-B (spec :416-426 half-sweep).
- **Swing → lean fresh (2, documented):** spec-i2-B2 (H1 fix under-scoped; reviewer enumerated 2 more real call sites :1371/:1442 — *gap-in-enumeration* vs *under-scope*); design-i2-B3 (:6367 real breaking test discovered — *fresh discovery* vs *correcting a false i1 claim*). Both self if under-scoping counts as self → 0F/11S.
- **Interpretation (consistent with 125's standing finding):** self-inflicted share tracks review-loop friction, not shipped danger — 123 shipped 0 defects like 125. The mass is the half-sweep + internal-contradiction + restated-literal cluster.

## Themes

1. **Self-inflicted friction dominates (~82%+), zero shipped defects** — the loop pays for itself in architecture + precision, not defect-catching (125-Theme-2, amplified).
2. **Half-sweep is the durable execution gap** — 5× at 123, 100% caught / 0% prevented, *despite* mid-feature mechanization. Rule coverage is complete; execution isn't.
3. **Cross-contract collision has an intra-design blind spot** — the guardrail caught 2 at the specify gate but the D3-vs-D8 *intra-design* contradiction slipped all design rounds.
4. **Countermeasures + fresh-per-round reviewer are load-bearing and holding** — most self-inflicted regressions were caught the very next round.

## Actions

| # | Action | Disposition |
|---|---|---|
| A1 | Security S1 — generic-handler `str(exc)` sanitization (mirror the builder) | **FILED #072** (pre-existing), confirmed present in backlog-manual.md. |
| A2 | Quality-reviewer actionable-ratio watch (#063) now n=3 (123: ~2/4 actionable) | **Threshold reached — evaluated; verdict appended to #063:** track-dependence confirmed (UI-track ~0 actionable ×2, engine-track actionable at 123); enactment subsumed by the workflow-rebuild track's implement-QA redesign. |
| A3 | Extend the cross-contract collision check to intra-design D-section contradictions (expected-zero-changes-vs-forced-edit class) | **FILED #073.** |
| A4 | Promote the mechanized cross-restatement grep-sweep from per-feature acceptance to a standing pre-gate check (half-sweep class) | **FILED #074.** |
| A5 | 132 handoff — rewire `LifecycleMachine.validate` as the `transition_entity_phase` enforcement path (currently descriptor role-note only; D6 move-contract deferred it) | **FILED #075** (code-quality W1). |
| A6 | `is_forward` 4-line duplication across FiveDMachine/FeatureMachine (different phase sources) | **Recorded, declined** (code-quality S1). Not filed. |
| A7 | Commit-count git-verification | **Closed:** orchestrator ran `git rev-list --count 64ab6b9e..HEAD` = 22 before facilitator dispatch, per 125-A5. |
