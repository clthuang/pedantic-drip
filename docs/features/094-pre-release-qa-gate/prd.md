# PRD: Pre-Release Adversarial QA Gate in /pd:finish-feature

*Source: Backlog #00217*

## Status
- Created: 2026-04-29
- Last updated: 2026-04-29
- Status: Draft
- Problem Type: Product/Feature
- Archetype: fixing-something-broken

## Problem Statement

Post-release adversarial QA dispatched after merge has produced 4 consecutive rounds of HIGH-severity findings (091→24, 092→18, 093→27, sync-cache→4 findings) that the *same* 4-reviewer quartet (`pd:security-reviewer` + `pd:code-quality-reviewer` + `pd:test-deepener` + `pd:implementation-reviewer`) catches every time — but only after merge to develop. Notable HIGH findings shipped to production then later patched in hotfixes:
- **#00193** [HIGH/security] `scan_decay_candidates` accepts `scan_limit < 0` → SQLite `LIMIT -1` = unlimited; memory-exhaustion DoS
- **#00194** [HIGH/security] AC-22b/c trap expansion + mktemp-failure path writes `printf >> /semantic_memory/maintenance.py` (filesystem root) under root user
- **#00219** [HIGH/security] `_ISO8601_Z_PATTERN` Unicode-digit bypass via `\d` without `re.ASCII`

The structural gap: `/pd:finish-feature` has no pre-merge adversarial QA dispatch. Every release ships HIGH bugs that the existing reviewer quartet would have caught one release earlier — at zero rollback cost — if dispatched against the feature branch diff before merge.

### Evidence
- **docs/backlog.md:222-271** — feature 091 post-release QA findings (24 items, 2 HIGH) — Evidence: file
- **docs/backlog.md:273-296** — feature 092 post-release QA findings (18 items, 1 HIGH) — Evidence: file
- **docs/backlog.md:299-340** — feature 093 post-release QA findings (27 items, 0 HIGH but 7 HIGH test-mutation gaps) — Evidence: file
- **docs/features/092-091-qa-residual-hotfix/retro.md** — first-principles advisor flagged this as structural gap across 082→088→089→091 — Evidence: file
- **plugins/pd/commands/finish-feature.md:339-418** — current Step 5a (`validate.sh`) and Step 5a-bis (`/security-review`) exist but no parallel multi-reviewer dispatch — Evidence: file:line

## Goals
1. Block any post-release HIGH-severity finding that the existing 4-reviewer quartet can detect.
2. Auto-file MED/LOW findings to backlog/retro to keep the feedback loop closed without blocking merge.
3. Keep wall-clock cost under 5 minutes per typical surgical feature.
4. Stay compatible with YOLO autonomous mode without becoming advisory-theatre.

## Success Criteria
- [ ] `/pd:finish-feature` Step 5b dispatches all 4 reviewers in one parallel `Task()` batch against `{pd_base_branch}...HEAD` diff
- [ ] HIGH-severity findings block merge until either fixed (re-run gate) or explicitly overridden via written rationale
- [ ] MED-severity findings auto-append to `docs/backlog.md` with marker `(surfaced by feature:094 pre-release QA)`
- [ ] LOW-severity findings auto-append to `retro.md` "Pre-release QA notes" section
- [ ] Re-running `/pd:finish-feature` on the same HEAD skips the gate (idempotency) AND logs the skip to retro for audit
- [ ] Test-deepener output shape (writes tests, not JSON) is handled explicitly — not silently ignored
- [ ] Wall-clock budget: <5 minutes for a feature with diff ≤500 LOC; warn (don't block) above
- [ ] Existing post-merge AC-12 dispatch (if any) is explicitly retired or scoped down to avoid double-cost
- [ ] Test-hooks integration test asserts Step 5b dispatch is present in `finish-feature.md` (anti-drift guard)
- [ ] Each gate run logs reviewer-by-reviewer HIGH/MED/LOW counts to retro.md so false-block rate is computable across features (enables Open Question 1 revisit trigger)
- [ ] `plugins/pd/skills/retrospecting/SKILL.md` updated per FR-7b to detect and fold `.qa-gate-low-findings.md` sidecar into retro.md on retrospect run (anti-orphan guard)

## User Stories

### Story 1: Surgical hotfix shipper
**As a** pd plugin maintainer  
**I want** the same 4 reviewers that find post-release HIGHs to run pre-merge  
**So that** I stop discovering HIGH bugs after rolling them into a release

**Acceptance criteria:**
- Running `/pd:finish-feature` on feature branch with a HIGH-introducing commit blocks merge until fixed
- The block message lists offending finding(s) with severity, location, and suggested fix from reviewer
- An override is possible but requires writing a one-paragraph rationale to `qa-override.md` in the feature directory

### Story 2: YOLO autonomous run
**As a** YOLO-mode user  
**I want** the gate to auto-handle MED/LOW findings without prompting  
**So that** autonomous flow continues but HIGH findings still surface  

**Acceptance criteria:**
- YOLO auto-files MED/LOW without prompting
- YOLO does NOT auto-override HIGH findings — gate stops and surfaces the findings, requiring user intervention
- This is the one YOLO exception in `finish-feature.md`

## Use Cases

### UC-1: Clean feature passes gate
**Actors:** developer  | **Preconditions:** feature branch on develop, all tasks complete, validate.sh passed  
**Flow:**
1. Run `/pd:finish-feature`
2. Step 5a (validate.sh) passes
3. **Step 5b dispatches 4 reviewers in parallel against `develop...HEAD` diff**
4. All 4 return zero HIGH/MED findings
5. Step 5a-bis (/security-review) runs
6. Merge to develop proceeds

**Postconditions:** zero pre-release residuals filed, retro notes "QA gate clean"

### UC-2: HIGH finding blocks merge
**Actors:** developer | **Preconditions:** feature branch contains a regression equivalent to #00193 or #00194  
**Flow:**
1. Step 5b dispatches reviewers
2. Security-reviewer returns HIGH severity finding
3. Gate output: "QA gate FAILED — 1 HIGH, 2 MED, 1 LOW"
4. MED/LOW are filed; HIGH is reported with location + suggested_fix
5. User fixes the finding, commits, re-runs `/pd:finish-feature`
6. Gate re-dispatches against new HEAD; if clean, merge proceeds

**Postconditions:** the HIGH bug never lands on develop

### UC-3: Override path
**Actors:** developer | **Preconditions:** HIGH finding is a confirmed false positive  
**Flow:**
1. Gate blocks with HIGH finding
2. User runs `/pd:finish-feature --override` (or chooses "Override" via AskUserQuestion in non-YOLO)
3. Command requires `qa-override.md` exists in feature dir with non-empty rationale
4. Override committed; gate skipped on re-run
5. Merge proceeds with override flag in retro

**Postconditions:** the false-positive override is auditable in git history

### UC-4: Reviewer agent fails mid-run
**Actors:** developer | **Preconditions:** one of the 4 agent dispatches errors out (timeout, model API error)  
**Flow:**
1. Step 5b dispatches 4 reviewers
2. 3 complete, 1 errors out
3. Gate treats as INCOMPLETE (not pass) — blocks merge with message "1 of 4 reviewers failed: {error}"
4. User can re-run gate or override via UC-3 path

**Postconditions:** never silent-pass on incomplete coverage

## Edge Cases & Error Handling

| Scenario | Expected Behavior | Rationale |
|----------|-------------------|-----------|
| Reviewer agent errors / times out | Treat as INCOMPLETE → block, do not silently pass | Antifragility advisor: silent partial-pass is worse than status quo |
| Diff > 1000 LOC | Run gate; emit warning "coverage confidence reduced for large diffs"; do not auto-skip | Antifragility advisor: don't blind to scale |
| Re-run on same HEAD with prior pass | Skip gate; append "QA gate skipped: HEAD {sha}" to retro.md (audit log) | Pre-mortem advisor: silent skip is invisible failure |
| Re-run on same HEAD after force-push | Recompute HEAD SHA; if differs from cache, re-dispatch | Pre-mortem: amend+force-push is common |
| Feature branch has no spec.md (direct-create) | Implementation-reviewer + test-deepener get a fallback prompt: "no spec — review for general defects" | Antifragility: spec-absent path elevates false positives |
| YOLO mode + HIGH finding | Block; do not auto-override | Pre-mortem: YOLO auto-override of HIGH = gate becomes theatre |
| YOLO mode + only MED/LOW | Auto-file MED to backlog, LOW to retro, proceed | Maintains autonomous-flow ergonomics |
| Single-reviewer HIGH while others are LOW | Block merge | Antifragility flagged consensus weighting; revisit trigger captured in Open Question 1 (false-block rate >15% after 3 features) |
| `qa-override.md` exists but is empty | Reject override; require ≥50 chars | Pre-mortem: empty rationale = no rationalization barrier |

## Constraints

### Behavioral Constraints (Must NOT do)
- MUST NOT auto-override HIGH findings in YOLO mode — Rationale: pre-mortem advisor identified this as the dominant gate-collapse failure mode for single-developer + autonomous flow
- MUST NOT silent-pass on incomplete reviewer runs — Rationale: antifragility advisor; partial coverage worse than status quo
- MUST NOT replace `/security-review` (Step 5a-bis) — Rationale: out-of-scope; that's CC-native and orthogonal
- MUST NOT add new reviewer agents — Rationale: scope discipline; reuse the proven quartet
- MUST NOT change existing reviewer agents themselves — Rationale: scope discipline; only their dispatch context changes
- MUST NOT depend on internet access — Rationale: pd is offline-friendly personal tooling

### Technical Constraints
- All 4 reviewers must dispatch in one parallel batch — Evidence: `max_concurrent_agents: 5` in `.claude/pd.local.md`; 4 ≤ 5
- Diff target: `{pd_base_branch}...HEAD` (three-dot, merge-base) — Evidence: `plugins/pd/commands/implement.md:250` (established convention)
- Idempotency cache key: HEAD SHA — Evidence: `plugins/pd/commands/implement.md:1140` (existing precedent)
- test-deepener writes tests directly (different output shape than JSON-finding reviewers) — Evidence: `plugins/pd/agents/test-deepener.md:1-7`

## Requirements

### Functional
- **FR-1:** Insert new "Step 5b: Pre-Release Adversarial QA Gate" in `plugins/pd/commands/finish-feature.md` between line 373 (Step 5a end) and line 374 (Step 5a-bis start)
- **FR-2:** Step 5b dispatches `pd:security-reviewer` (opus) + `pd:code-quality-reviewer` (sonnet) + `pd:implementation-reviewer` (opus) + `pd:test-deepener` (opus) in one parallel `Task()` batch
- **FR-3:** Each reviewer prompt receives: feature spec.md path (if exists; else fallback notice), feature diff via `git diff {pd_base_branch}...HEAD`, severity rubric reminder
- **FR-4:** test-deepener handling: invoke in **Step A mode only** (outline-generation, JSON output per `plugins/pd/agents/test-deepener.md` Step A — no test-write) so output is structured findings comparable to other reviewers; document this constraint in command file
- **FR-5:** Aggregate findings into `{HIGH, MED, LOW}` buckets per severity rubric:
  - HIGH = `severity: blocker` OR `securitySeverity: critical|high`
  - MED = `severity: warning` OR `securitySeverity: medium`
  - LOW = `severity: suggestion` OR `securitySeverity: low`
- **FR-6:** If any HIGH: block merge, emit findings list with location + suggested_fix, list override path
- **FR-7:** Non-blocking findings auto-file:
  - **MED:** append to `docs/backlog.md` with marker `(surfaced by feature:{id} pre-release QA)`
  - **LOW:** append to `docs/features/{id}-{slug}/.qa-gate-low-findings.md` (sidecar file the gate creates if absent).
- **FR-7b:** Modify `plugins/pd/skills/retrospecting/SKILL.md` so its run detects `.qa-gate-low-findings.md` in the feature directory, appends its contents to `retro.md` under a `## Pre-release QA notes` H2 section, then deletes the sidecar. Without this update, the FR-7 LOW sidecar would accumulate unconsumed.
- **FR-8:** Idempotency: store HEAD SHA + gate-pass timestamp in `.qa-gate.json` in feature dir on PASS. On re-run with matching HEAD, skip dispatch and log "QA gate skipped: HEAD {sha}" to retro.md
- **FR-9:** Override path: require a non-empty `qa-override.md` (≥50 chars rationale) in feature dir; gate writes the offending finding(s) into the file as a frontmatter block on first invocation, user fills in the rationale below, gate commits and bypasses on next run. Single-file form (not timestamped) — git history is the audit log; subsequent overrides append to the same file with a new dated H2 section.
- **FR-10:** Incomplete-run policy: if any of the 4 reviewers errors out, treat as INCOMPLETE → block (not pass)
- **FR-11:** YOLO override of FR-6: even in YOLO mode, HIGH findings stop autonomous flow; MED/LOW auto-file proceeds
- **FR-12:** Test-hooks integration test in `plugins/pd/hooks/tests/test-hooks.sh` asserting "Step 5b" present in `finish-feature.md` and assertion that 4 specific reviewer agent names appear in the dispatch block (anti-drift)

### Non-Functional
- **NFR-1:** Wall-clock target ≤5 min for diffs ≤500 LOC; warn above (do not block on size alone)
- **NFR-2:** No new external dependencies (offline-compatible)
- **NFR-3:** All 4 reviewer dispatches must specify `model:` matching their frontmatter (per CLAUDE.md "Agent model tiers" guideline)
- **NFR-4:** `finish-feature.md` is currently 508 lines (already over the 500-line SKILL/command soft limit). If Step 5b prose pushes the file over 600 lines, extract the procedural detail to a referenced helper file (e.g., `docs/dev_guides/qa-gate-procedure.md`); keep the inline command prose to the dispatch shape + severity rules + decision tree only.

## Non-Goals
- Adding new reviewer agents (5th/6th) — Rationale: 4 is what catches the post-release residuals; adding more dilutes signal and inflates wall-clock
- Replacing `/security-review` (Step 5a-bis) — Rationale: orthogonal CC-native check, not in scope
- Modifying existing reviewer agent prompts — Rationale: their post-release behavior is what we're moving forward in time
- Cross-feature interaction-bug detection — Rationale: first-principles advisor flagged this; diff-scoped review can't see post-merge integration bugs by definition. File as separate backlog item if pursued.
- Pattern recurrence suppression — Rationale: first-principles advisor flagged that the same vulnerability classes recur (#00194 = same class as feature-083 anti-pattern); injecting anti-pattern KB into reviewer prompts is a separate enhancement
- Consensus weighting (≥2 of 4 reviewers must agree on HIGH) — Rationale: antifragility advisor flagged this; deferred to design phase as Open Question
- Reviewer feedback loop (gate findings → KB) — Rationale: antifragility advisor recommended; deferred to future feature

## Out of Scope (This Release)
- Anti-pattern KB injection into reviewer prompts — Future consideration: feature 095+ if pattern recurrence persists
- Consensus weighting / multi-reviewer agreement threshold — Future consideration: revisit after 3 features ship through new gate; if false-block rate >15%, add weighting
- Cross-feature interaction-bug coverage — Future consideration: would require post-merge gate or full-codebase review pass; out-of-band
- Replacing manual backlog auto-filing with a structured tool/skill — Future consideration: feature 095+ codifies the "file MED finding to backlog" recipe as a reusable command
- Migrating existing post-release adversarial QA pattern (currently invoked manually after each release) — Future consideration: explicit retirement should land in this PRD's design phase. See Open Question 2 for the trigger condition (retire after 2 proven gate runs).

## Research Summary

### Internet Research
- GitHub Copilot review (2025-2026) is advisory by design; merge enforcement requires CI wrapper that parses output — Source: https://medium.com/kairi-ai/githubs-2025-copilot-review-can-t-satisfy-the-merge-gate-f1de0e535788
- Semgrep's three rule modes (Monitor / Comment / Block) match the proposed HIGH-blocks / MED-files / LOW-notes rubric directly — Source: https://semgrep.dev/docs/semgrep-code/policies
- Snyk's per-severity break-config: Critical+High = pipeline break, Medium = warn, Low = advisory (industry default) — Source: https://docs.snyk.io/manage-risk/prioritize-issues-for-fixing/severity-levels
- Parallel LLM reviewer wall-clock at 4 agents ≈ 60–90s; under 2 min generally tolerated as CI noise — Source: https://redis.io/blog/how-to-improve-llm-ux-speed-latency-and-caching/
- Mozilla Star Chamber consensus model: single-reviewer findings are low-confidence observations, not blockers — Source: https://blog.mozilla.ai/the-star-chamber-multi-llm-consensus-for-code-quality/

### Codebase Analysis
- Insertion point: `plugins/pd/commands/finish-feature.md:373-374` (between Step 5a end and Step 5a-bis start) — Location: file:line
- Reviewer agents exist: `plugins/pd/agents/{security-reviewer,code-quality-reviewer,implementation-reviewer,test-deepener}.md` — Location: dir
- Established severity trichotomy `blocker | warning | suggestion` defined in reviewer JSON output schemas — Location: `plugins/pd/agents/security-reviewer.md:106` + `plugins/pd/agents/code-quality-reviewer.md:61`. Block-vs-warn rule (FAIL = blocker OR warning) at `plugins/pd/commands/implement.md:1047-1048`.
- No existing parallel reviewer dispatch in any command — feature 094 establishes the first such pattern in the command layer; closest precedent is implement.md sequential level dispatch — Location: `plugins/pd/commands/implement.md:343,530,697,869`
- Idempotency-via-HEAD-SHA precedent: `plugins/pd/commands/implement.md:1140` — Location: file:line
- Block-with-override UX precedents: `finish-feature.md:57-70`, `:374-418`, `workflow-transitions/SKILL.md:55-69`, `implement.md:1332-1347` — Location: 4 instances

### Existing Capabilities
- `pd:reviewing-artifacts` skill: static checklist reference for severity criteria, NOT a dispatcher — How it relates: provides the severity vocabulary, but does not orchestrate; Step 5b implementation is in command layer
- `pd:capturing-learnings` skill: writes to semantic memory store, NOT to `docs/backlog.md` — How it relates: cannot be reused for backlog auto-filing; FR-7's MED-to-backlog write must be implemented inline in the command
- `pd:researching` skill: dispatches 2 agents in parallel + 1 synthesizer sequential — How it relates: closest existing parallel pattern; Step 5b extends to 4 parallel without synthesis (each reviewer's findings are merged by severity, not synthesized)

## Strategic Analysis

*Advisor team configured per archetype default for fixing-something-broken (first-principles, pre-mortem, antifragility) — all three are risk-focused, deliberately. The user's prior 4-release residual cycle is the empirical motivation for this feature; an opportunity-cost or value-questioning advisor would be re-litigating a settled question. The advisor outputs below should be read as "given that we are doing this, what are the failure modes" rather than "should we do this at all".*

### First-principles
- **Core Finding:** The proposed gate addresses the correct structural gap (no pre-merge adversarial review), but rests on an unexamined assumption that the same quartet of reviewers whose post-merge findings reveal the gap will reliably catch the same classes of bugs pre-merge — when temporal positioning is the only variable being changed.

#### Analysis

**Is this the right problem?** Socratically: why do HIGH findings ship to production? The surface answer is 'no pre-merge gate.' But ask one level deeper: why are HIGH findings appearing repeatedly in the *same functional areas*? Findings #00193 (LIMIT -1 DoS), #00194 (trap/filesystem root write), #00219 (Unicode-digit bypass) are not random — they are variants of three recurring vulnerability classes: unclamped numeric input, unsanitized shell interpolation, and character-class bypass. The knowledge bank confirms this: anti-patterns "Unsanitized Interpolation of LLM/User Input Into Generated Shell Scripts" (feature 083) and "Bash Variable Interpolation in Inline Python" (feature 021) document the same injection class that surfaced in #00194. The real problem may not be *when* review happens but *that these patterns keep being introduced.* The gate addresses detection timing; it does not address pattern recurrence.

However, for a single-user personal-tooling context with no external contributors, a pre-merge gate that catches pattern instances before they land is the least-ceremony intervention. The archetype "fixing-something-broken" is correctly applied.

**What assumptions are we making, and are they valid?** *Assumption 1: The same 4 reviewers pre-merge will catch what they catch post-merge.* Likely — the reviewers are stateless agents whose quality depends on diff quality, not timing. Concern is not competence but scope: pre-merge they see the feature diff; post-merge they see the merged codebase plus integration context. None of the three cited HIGH findings are cross-feature interaction bugs — they are self-contained — so this assumption holds for the observed failure mode.

*Assumption 2: HIGH findings block merge.* Correct severity threshold; matches feature 092 plan.md acceptance criterion.

*Assumption 3: Wall-clock <5 min is achievable.* Plausible for surgical features (~200 LOC). Optimistic for large cross-cutting features. Idempotency provides safety valve.

*Assumption 4: test-deepener "special handling" is resolvable.* Live unresolved assumption — must concretize at design time or this becomes anti-pattern "Describing Algorithms Without Specifying Concrete I/O and Edge Cases."

*Assumption 5: This is a new structural gap.* Not entirely — feature 092's AC-12 was explicitly post-merge mandatory QA. The proposal moves the gate pre-merge.

**Has this been solved elsewhere?** Shift-left testing literature confirms elite performers use pre-merge validation; arxiv adversarial multi-agent review research (2604.19049) found 83% kill rate on adversarial candidates — supporting the proposal.

**Simplest irreducible truth:** Bugs found pre-merge cost zero rollbacks; bugs found post-merge cost both rollbacks and hotfix features.

#### Key Risks
- Cross-feature interaction bugs (new function calling existing vulnerable helper) escape pre-merge review (diff scope only)
- test-deepener output shape ambiguity — must resolve at design time
- If post-merge AC-12 dispatch is retained alongside new pre-merge gate, same 4 reviewers run twice with no incremental signal
- Pattern recurrence not addressed — anti-pattern KB exists but is not injected into reviewer prompts
- YOLO HIGH-override = gate is advisory in autonomous mode unless explicitly prohibited

#### Recommendation
Resolve test-deepener output-shape handling concretely at design time. Explicitly retire or downscale duplicate post-merge AC-12 dispatch. Consider injecting anti-pattern KB into reviewer prompts as future enhancement.

- **Evidence Quality:** strong

### Pre-mortem
- **Core Finding:** The gate was built but not hardened — it runs, produces findings, and then defers to the author's judgment under YOLO-mode pressure, leaving the only human-in-the-loop (clthuang) as both the sole judge and the most motivated party to rationalize past it.

#### Analysis

**The override path is too comfortable.** YOLO mode already auto-approves 5 of 7 gate points in finish-feature.md. Adding a sixth auto-approval makes the gate theater. Single-developer context means no second reviewer to push back on rationalization. After 2-3 overrides, overriding becomes the default. The gate exists, fires, the HIGH appears, override is exercised, until override is normalized. Six months later the residual cycle continues.

**The idempotency cache is an unexamined SPOF.** "Skip if already-dispatched-for-this-HEAD" introduces a new failure mode: if the cache misfires (stale entry, hash collision on amended commits, amend-then-force-push workflow), reviewers silently don't run. Because the 4-reviewer dispatch is the only new signal — validate.sh and /security-review already exist — a silent skip means the gate never fired. With no audit log, no detection until a post-release HIGH surfaces.

**The test-deepener divergent output shape is a known unhandled edge.** "Special handling" in the spec without concretizing what it means risks: orchestrator parses uniform JSON envelope, test-deepener returns file edits, severity check either crashes or silently zero-counts test-deepener findings — dropping 25% of reviewer surface.

#### Key Risks
1. **YOLO-mode override normalization** (HIGH likelihood, HIGH impact) — adding HIGH-override to YOLO defeats the gate
2. **Idempotency cache false-hit** (MED likelihood, HIGH impact) — silent skip invisible to author
3. **test-deepener output shape mismatch** (MED likelihood, HIGH impact) — silently drops 25% coverage
4. **Reviewer model context-window saturation** on large diffs (MED likelihood, MED impact)
5. **Gate scope creep** in 508-line file (LOW likelihood, HIGH cumulative) — vulnerable to accidental removal
6. **Step 5a-bis /security-review redundancy** (LOW likelihood, MED impact) — mental merging leads to one being deprecated

#### Recommendation
Make the override path maximally painful — prohibit YOLO auto-override of HIGH; require written rationale committed as `qa-override-{timestamp}.md`. Implement skip-audit log. Add test-hooks assertion that Step 5b is present.

- **Evidence Quality:** moderate

### Antifragility
- **Core Finding:** The Step 5b gate is structurally robust in the nominal case but catastrophically fragile at exactly the failure mode it was designed to catch — when the diff is largest, the feature is most chaotic, and the reviewer signal is most contested, the gate is most likely to be overridden or silently bypassed, converting a blocking control into a performative ritual.

#### Analysis

**Stress 1 — large diffs (1000+ LOC).** LLM reviewer precision degrades, false HIGH rate climbs. The proposal counts any HIGH from any of 4 reviewers as hard block; first false HIGH triggers override path; after 2-3 such events override becomes default. Canonical alarm-fatigue collapse.

**Stress 2 — reviewer disagreement (one HIGH, others LOW).** No resolution protocol. Single outlier blocks merge regardless of consensus. Mozilla Star Chamber model treats single-reviewer findings as low-confidence observations, not blockers. Without weighting, gate is veto-by-singleton — maximally fragile to any one reviewer having a bad day.

**Stress 3 — reviewer failure (one of 4 errors out).** No explicit handling. Silent pass on 3/4 = worse than status quo (post-release QA always runs all 4 to completion).

**Stress 4 — spec drift (direct-create features, no spec.md).** implementation-reviewer + test-deepener reference spec docs; absence → hallucinated specs or generic findings unanchored to intent → elevated false-positive rates on the features most likely to need the gate.

**Stress 5 — false positive cascade.** SAST research: developers begin overriding when false-positive rate >15-20%. At 4 parallel reviewers, ~15% per reviewer compounds to ~50% chance of at least one false HIGH per run.

**Antifragility opportunity:** if HIGH findings caught pre-merge feed back as examples into reviewer prompts (or KB via /pd:remember), reviewers' calibration improves over time. Currently spec lacks this. Without the loop, gate is robust (resists regression) not antifragile (improves from exposure).

#### Key Risks
- **CRITICAL** — override normalization under false-positive pressure (no consensus weighting)
- **HIGH** — incomplete reviewer run treated as pass
- **HIGH** — large-diff degradation
- **MEDIUM** — spec-absent feature path elevates false-positive rate
- **MEDIUM** — no feedback loop for gate calibration
- **LOW** — YOLO mode interaction with override AskUserQuestion

#### Recommendation
Apply consensus weighting (≥2 of 4 reviewers must agree on HIGH); explicit error-out policy (incomplete = block, not pass); feedback write-back to KB on each gate invocation outcome.

- **Evidence Quality:** moderate

## Symptoms

- 4 consecutive feature releases (091, 092, 093, plus the v4.16.3 sync-cache fix) have produced post-release adversarial QA residual rounds totaling 73 findings, including 3 HIGH-severity production bugs that required hotfix releases.
- Each post-release QA round dispatches the *same* 4 reviewer agents that would have run pre-merge — proving the bugs were detectable before release, just not detected.
- Retros for 091, 092, 093 each independently flagged the structural gap; first-principles advisor identified it as recurring across 082→088→089→091.
- The pattern has now persisted across 5+ releases without correction.

## Reproduction Steps

1. Pick any of features 091/092/093.
2. `git diff develop...feature/{N}-{slug}` to recover the pre-merge diff.
3. Dispatch the 4 reviewer agents against that diff.
4. Observe HIGH-severity findings that match the post-release backlog entries (#00193, #00194, #00219, etc.) — items the user already paid hotfix cost to resolve.

## Hypotheses

| # | Hypothesis | Evidence For | Evidence Against | Status |
|---|-----------|-------------|-----------------|--------|
| 1 | Pre-merge dispatch of the same 4 reviewers would catch the post-release HIGHs | All 3 cited HIGHs (#00193, #00194, #00219) are diff-local self-contained bugs; reviewers caught them post-merge against substantially the same code | Cross-feature interaction bugs require post-merge integration view (first-principles flagged) | Confirmed for current observed failure mode |
| 2 | The gate fails by override normalization under YOLO + single-developer pressure | Pre-mortem advisor + antifragility advisor both flagged independently; YOLO already auto-approves 5/7 gate points | Override path can be designed with friction (rationale file, no YOLO HIGH-override) | Mitigatable by design — see FR-9, FR-11 |
| 3 | test-deepener's divergent output shape silently drops 25% of coverage | First-principles + pre-mortem both flagged as live unresolved | Resolvable by Step A-only invocation per FR-4 | Resolved by FR-4 |
| 4 | The idempotency cache silently skips on amend/force-push | Pre-mortem flagged; HEAD-SHA-based caching has known edge cases | Mitigatable with audit log per FR-8 | Resolved by FR-8 |
| 5 | Single-reviewer HIGH veto produces high false-positive rate that conditions override | Antifragility advisor; 15-20% per-reviewer false-positive rate compounds across 4 reviewers; SAST literature | Speculative without empirical data; deferred to Open Question | Open — revisit after 3 features ship through gate |

## Evidence Map

- **Symptom (residual cycle 091→092→093→sync-cache)** ↔ **Hypothesis 1** ↔ **FR-1 through FR-7** (the core dispatch + severity logic)
- **Symptom (override-prone single-dev context)** ↔ **Hypothesis 2** ↔ **FR-9, FR-11** (rationale file, YOLO HIGH-stop)
- **Symptom (test-deepener writes tests)** ↔ **Hypothesis 3** ↔ **FR-4** (Step A invocation only)
- **Symptom (cache silent-skip risk)** ↔ **Hypothesis 4** ↔ **FR-8** (HEAD-SHA cache + audit log)
- **Open question (consensus weighting)** ↔ **Hypothesis 5** ↔ deferred to design / future feature

## Review History

### Review 0 (2026-04-29) — prd-reviewer (opus)

**Findings:**
- [warning] FR-4 + Hypothesis 3 use "Phase A" but test-deepener.md uses "Step A" terminology (at: FR-4, Hypotheses row 3)
- [warning] Codebase Analysis cites `implement.md:1047-1048` as severity-trichotomy source, but those lines only define blocker+warning (at: Codebase Analysis, FR-5)
- [warning] FR-7 "append to retro.md" is ambiguous because retro.md may not exist yet at Step 5b time (at: FR-7)
- [suggestion] FR-9 / UC-3 use single `qa-override.md`; pre-mortem advisor recommended timestamped form — trade-off not made visible (at: FR-9, UC-3)
- [suggestion] Open Question 1's revisit trigger (false-block rate >15%) has no measurement mechanism specified (at: Open Questions #1, Success Criteria)
- [suggestion] Edge Cases table row 8 ("Single-reviewer HIGH") mixes runtime behavior with policy lifecycle (at: Edge Cases row 8)
- [suggestion] NFR-4 says 500-line soft limit but finish-feature.md is already 508 lines (at: NFR-4)

**Corrections Applied:**
- FR-4 + Hypothesis 3 — replaced "Phase A" with "Step A" + added agent-file reference. Reason: Warning 1.
- Codebase Analysis severity-trichotomy bullet — re-cited to `security-reviewer.md:106` + `code-quality-reviewer.md:61` (where the trichotomy is actually defined); kept implement.md as the block-vs-warn rule citation. Reason: Warning 2.
- FR-7 — switched LOW handling to a sidecar `.qa-gate-low-findings.md` that retrospect skill folds into retro.md and deletes. Eliminates the "may not exist yet" ambiguity. Reason: Warning 3.
- FR-9 — clarified single-file form with explicit rationale (git history is the audit log) + append-with-dated-H2 semantics for repeat overrides. Reason: Suggestion on advisor trade-off.
- Success Criteria — added a measurement criterion (gate logs reviewer-by-reviewer HIGH/MED/LOW counts to retro.md). Reason: Suggestion on revisit-trigger measurability.
- Edge Cases row 8 — split runtime behavior ("Block merge") from policy lifecycle (Open Question 1 reference). Reason: Suggestion on table consistency.
- NFR-4 — explicit acknowledgement of the 508-line baseline + 600-line extraction trigger. Reason: Suggestion on existing overage.

### Review 1 (2026-04-29) — prd-reviewer (opus)

**Findings:**
- [warning] Evidence Map line still says "Phase A invocation only" — incomplete fix from Review 0 (at: Evidence Map)
- [warning] FR-7's sidecar mechanism creates undeclared dependency on retrospecting skill (at: FR-7)

**Corrections Applied:**
- Evidence Map — replaced "Phase A invocation only" with "Step A invocation only" to match test-deepener.md canonical terminology. Reason: Warning 1.
- FR-7 split into FR-7 (sidecar write) + new FR-7b (retrospecting skill update to fold + delete the sidecar). Reason: Warning 2.

### Review 2 (2026-04-29) — brainstorm-reviewer (sonnet, readiness check)

**Findings:**
- [warning] Open Question 4 + FR-3 leave spec-absent fallback prompt as design-phase placeholder (at: FR-3, Open Questions #4)
- [warning] Strategic Analysis advisors are all risk-focused; no value-questioning counter-voice (at: Strategic Analysis)
- [suggestion] FR-7b lacks corresponding Success Criterion (at: FR-7b, Success Criteria)
- [suggestion] Open Question 2 (AC-12 retirement) not cross-referenced from Out of Scope (at: Open Questions #2, Out of Scope)

**Corrections Applied:**
- Open Question 4 — strengthened wording: "design phase MUST define the exact fallback prompt text" with concrete example. Reason: Warning 1 (eliminates the soft-defer ambiguity).
- Strategic Analysis — added a preamble paragraph acknowledging the deliberate risk-focused advisor selection given the empirical 4-release residual cycle, framing the analyses as "given we're doing this, what fails" not "should we do this." Reason: Warning 2.
- Success Criteria — added a criterion for the FR-7b retrospecting skill update (anti-orphan guard). Reason: Suggestion 1.
- Out of Scope — cross-referenced Open Question 2 from the AC-12 migration line. Reason: Suggestion 2.

## Open Questions

1. **Consensus weighting threshold** — should HIGH require ≥2 of 4 reviewers to agree, or any single HIGH? Antifragility flagged single-reviewer veto as fragility. Recommendation: ship with single-reviewer block (current FR-6) but add metric to retro for 3 features; revisit if false-block rate >15%.
2. **AC-12 post-merge retirement** — does the existing post-merge adversarial QA (manual dispatch after release) get retired, downscaled, or kept as a separate validation pass? First-principles flagged double-cost risk. Recommendation: remove from manual-after-release ritual once pre-merge gate is proven on 2 features.
3. **Anti-pattern KB injection into reviewer prompts** — could reduce pattern recurrence (#00194 = same class as feature-083 anti-pattern). Out of scope for 094 but could be a feature 095+ enhancement.
4. **Spec-absent feature handling** — what fallback prompt do implementation-reviewer + test-deepener get when no spec.md exists? Current FR-3 says "fallback notice"; **design phase MUST define the exact fallback prompt text** (e.g., "no spec.md found — review for general defects against the diff; do not synthesize requirements"). This is a hard gate on the spec.md phase exit, not a soft note.
5. **`qa-override.md` rationale format** — is plain prose enough, or should it be structured (template with reviewer-name + finding-id + why-false-positive)? Design phase decision.

## Next Steps
Ready for /pd:create-feature to begin implementation.
