# Retrospective: feature/107-fix-sessionstart-broken-pipe

- **Mode:** standard
- **Started:** 2026-05-08T03:14:11Z
- **Implement complete:** 2026-05-08T04:54:52Z
- **Wall-clock:** ~1 h 40 min
- **Branch lifetime:** ~1 day; 22 commits, 22 files changed (+2291 / −28)
- **Total reviewer dispatches:** 18 across 4 phases
- **Origin RCA:** `docs/rca/20260508-110928-sessionstart-skills.md`

## AORTA Analysis

### Achievements

| # | Outcome | Evidence |
|---|---|---|
| 1 | Functional fix verified end-to-end | 4/4 repro scenarios exit 0 (was 2/4 failing); 15/15 new feature-107 sub-tests pass; 114/114 pre-existing hook tests green; FR8 invariant clean (zero line-leading `cat <<`) |
| 2 | NFR2 latency: **−42 ms vs baseline** (PASS, ≤ +50 ms) | `bench-results.txt` committed with merge-base SHA pinning; 11-run median, drop fastest+slowest |
| 3 | Empirically grounded canonical pattern | `probe-printf-sigpipe.sh` produced 4-row Verified Bash Behavior table; `safe_emit_hook_json` + `trap '' PIPE` proven co-load-bearing under `set -e` |
| 4 | SoT documentation extended | `docs/dev_guides/hook-development.md` now contains EPIPE / set -e / session-start.sh / safe_emit_hook_json section, modified by feature/107 commits (AC6c) |
| 5 | Static guard installed (FR8) | `check-no-unsafe-writes.sh` + `fixture-unsafe-write.sh` positive-control: same code path, parameterized target, BSD-portable `[[:space:]]` |
| 6 | Trap robustness improved | `__pd_exit_handler` defensively `set +e`; `__PD_HOOK_EMITTED` global flag eliminated; rc-gated fallback only on failure path |
| 7 | Latent perf side-quest | `escape_json` skipped on jq path (was redundant with `jq --arg`) — saved ~30 ms on large contexts |

### Observations

| Phase | Reviewer iterations | Notes |
|---|---|---|
| specify | 4 (3 spec-reviewer + 1 phase-reviewer) | Iter-1 had 3 blockers + 6 warnings; iter-2 had 2 blockers + 6 warnings; iter-3 was clean (4 suggestions only). Phase-reviewer agreed on the same 4 suggestions — a cross-vantage-point calibration signal. |
| design | 5 (3 design-reviewer + 2 phase-reviewer) | Iter-1 had 4 blockers + 6 warnings; the BIG one (TD1 conflating "printf is bash builtin" with "SIGPIPE-safe") was resolved by the empirical Verified Bash Behavior probe. Handoff bounced once on unresolved Open Questions (OQ-fixture-naming, OQ-T8-mechanism). |
| create-plan | 7 (3 plan-reviewer + 2 task-reviewer + 2 phase-reviewer) | Highest reviewer count of the workflow. Most issues were tactical (renumbering, DoD circularity, tdd-order, AC12 missing-task). Cross-reviewer consistency was high — same circular-dependency observation flagged by both task-reviewer iter-1 and phase-reviewer iter-1. |
| implement | 2 (4 reviewers in parallel + 1 quality re-review) | L1+L2+L3-security all approved iter-1; L3-code-quality flagged a `$?`-in-trap timing claim that was empirically disproved in 30 seconds. Iter-2 was a clean approval with one doc-drift suggestion. |

**Cross-cutting observations:**

1. **Reviewer-iteration count fell monotonically with downstream phases** (specify→design→create-plan→implement: 4, 5, 7, 2). Implement was the cheapest phase despite touching production code — binary-DoD plan made direct-orchestrator dispatch viable. **Rigorous-upstream-enables-direct-orchestrator-implement** in action.
2. **Bench methodology pivoted twice before producing trustworthy numbers.** First bench showed +577 ms phantom regression because baseline worktree had a *different project state* than HEAD's worktree. Fix: stage both hook versions against HEAD's project state with `HOME=$(mktemp -d)` isolation. Lesson: hook benchmarks need *workspace-state* isolation, not just `$HOME` isolation.
3. **The empirical printf-vs-trap probe was the design-phase keystone.** Design-reviewer iter-1 blocker #1 conflated bash builtins with SIGPIPE safety. Resolution wasn't argument — it was a 4-row probe matrix. Once inlined in design.md and committed as `probe-printf-sigpipe.sh`, the pattern became self-defending: future contributors who try to remove `trap '' PIPE` can re-run the probe.
4. **L3 code-quality reviewer iter-1 false-positive caught by 30-second empirical check.** Reviewer claimed `$?` in `trap '...' EXIT` strings expands at registration time. Quick probe: `__handler() { local rc="$1"; }; trap '__handler $?' EXIT; false; exit 7` → handler received `rc=7`. Conclusion: `$?` in trap strings expands at *fire* time. **Verifying reviewer assertions empirically (not just textually) caught a false-positive that would have driven a needless code change.**
5. **Suggestion overlap across reviewers is a high-confidence signal.** Spec-reviewer iter-3 produced 4 suggestions; phase-reviewer iter-1 produced the same 4. When two reviewers from different vantage points (skeptic vs gatekeeper) flag the same items, severity calibration is reliable.
6. **T5 design assumption inverted at implement time.** Design assumed "closed stdout → log entry"; the actual fix makes closed stdout NOT a failure (so no log entry). T5 had to swap to `PD_FORCE_BUILD_CONTEXT_FAIL=1` to exercise the log path. Caught during implement; cost was small because OQ-T8-mechanism had been resolved at design handoff.

### Reflections

**What went well:**

- **Spec rigor paid off.** Two-iteration spec convergence on a hard set of issues. Iter-3 was strict-threshold-clean.
- **Design grounded in empirical evidence.** Verified Bash Behavior table + Reason Vocabulary subsection + Scope Guards Compliance subsection turned design.md into a self-defending document.
- **Direct-orchestrator implement was viable.** Binary DoDs in tasks.md → no per-task subagent dispatch → 14-task implementation in one orchestrator pass with low review iterations.
- **Cross-reviewer consistency was high.** Where two reviewers agreed, severity calibration was trustworthy.

**What didn't go as well:**

- **create-plan needed 7 reviewer iterations** — highest of any phase. Most issues were tactical (renumbering, DoD ordering, sequencing inconsistencies between plan.md mermaid and tasks.md). The plan-vs-tasks dual-source-of-truth problem caused at least 3 of those iterations.
- **Bench methodology bug consumed implement time.** A +577 ms phantom regression caused real fear before the workspace-state-isolation pivot. A workspace-isolation checklist in `hook-development.md` would have prevented this.
- **Reviewer suggestions deferred to implement could pile up.** Spec iter-3 deferred 4 suggestions ("at engineer's discretion"); design iter-2 deferred 2; design iter-3 deferred 2; create-plan iter-3 deferred 1. Some (like the AC8 baseline-pinning ambiguity) DID resurface during implement.
- **L3 code-quality false-positive.** A reviewer got bash semantics wrong. Cost was 30 seconds of probe time — but a less skeptical implementer might have made the wrong code change.

### Themes

| Theme | Manifestations |
|---|---|
| **Spec/design rigor pays off in implement** | 4+5+7 = 16 upstream iterations vs 2 in implement; direct-orchestrator possible |
| **Empirical grounding > textual argument** | Verified Bash Behavior matrix; A1 probe; printf-sigpipe probe; `$?`-in-trap probe disproving false-positive |
| **Bash 3.2 portability requires extra care** | BSD grep `\s` vs `[[:space:]]`; `eval` vs `${!var}` indirect expansion; `stat -f%z` vs `stat -c%s` fallback chain; `BASH_LINENO[0]:-0` defensive default |
| **Workspace-state isolation matters for hook benchmarks** | `HOME=$(mktemp -d)` alone insufficient; staging both hook versions against HEAD's project state required |
| **Plan/tasks dual-SoT causes iteration churn** | mermaid edges contradicted Sequencing Note; T8 numbering collision; tasks.md treated as authoritative late |
| **Reviewer-suggestion calibration via overlap** | spec-reviewer iter-3 + phase-reviewer iter-1 produced identical 4 suggestions → high confidence on severity |
| **Reviewer claims are hypotheses, not directives** | `$?`-in-trap empirical disproof saved a needless code change |

### Actions

1. **Document the workspace-state-isolation checklist** in `docs/dev_guides/hook-development.md` (next to the new broken-pipe section): when benchmarking hooks, isolate `$HOME` AND project state (.git, lockfiles, fixtures) AND pd env vars.
2. **Promote tasks.md as single SoT for execution sequencing.** Plan.md mermaid is illustrative; if it disagrees with tasks.md, tasks.md wins. Add a one-line policy note to `creating-plans` SKILL.md or the plan template.
3. **Capture deferred suggestions as backlog items.** When a reviewer approves with N>0 suggestions and the implementer chooses not to address them inline, automatically add a backlog entry with "deferred from {feature}/{phase}/iter-{n}" provenance.
4. **Add a "verify reviewer claims empirically" reminder** to `implement.md` for low-level language-semantics warnings (signals, traps, set -e, expansion timing).
5. **Audit other 8 hooks using `cat <<EOF`** for the same vulnerability (per spec SG2 — out of scope for feature 107 but enabled by the canonical pattern now in place). Track as backlog item.
6. **Inline empirical-evidence matrices** in design.md whenever a fix depends on subtle language semantics.

## Knowledge Bank Updates

### Already captured mid-flight via store_memory (13 entries)

- "trap '' PIPE doesn't fix SIGPIPE under set -e" (anti-pattern, high)
- "trap '' PIPE is co-load-bearing with || true under set -e" (high — empirically verified)
- "ERR-trap can't self-rescue when stdout is the broken pipe" (high)
- "Hooks should install EXIT trap emitting valid default output" (heuristic)
- "Test bash hooks under SIGPIPE / closed-stdout conditions" (heuristic)
- "CC v2.1.129+ skillListingBudgetFraction drops skills" (heuristic)
- "Pin AC scripts to permanent paths, not agent_sandbox/" (heuristic)
- "Every NFR needs a paired AC with a verification command" (heuristic)
- "Use [[:space:]] not \\s in grep regex for BSD/macOS portability" (heuristic)
- "Task DoDs that source production scripts as libs are unexecutable" (heuristic)
- "Negative-control DoDs need an actually-existing file" (heuristic)
- "Use ${!varname} indirect expansion (bash 2.0+); avoid eval" (heuristic)
- "$? in trap '...' EXIT expands at fire time, not registration" (heuristic)

### NEW KB candidates (3 highest-value, captured below as separate store_memory calls)

1. **Pattern: Inline 'Verified Behavior' matrix in design when fix depends on language semantics** — design rigor pattern, high confidence
2. **Anti-pattern: Hook benchmarks require workspace-state isolation, not just HOME isolation** — measurement methodology, high confidence
3. **Heuristic: Verify reviewer assertions empirically before applying code changes** — iter-economics, high confidence

## Raw Data

- **Feature:** 107-fix-sessionstart-broken-pipe
- **Mode:** standard
- **Branch lifetime:** ~1 day
- **Total reviewer iterations:** 18 across 4 phases
- **Commits:** 22 (ahead of develop)
- **Files changed:** 22 (+2291 / −28)
- **Origin RCA:** `docs/rca/20260508-110928-sessionstart-skills.md`
- **Test outcomes:** 4/4 repro scenarios PASS; 15/15 new sub-tests PASS; 114/114 pre-existing hook tests PASS; FR8 invariant PASS; NFR2 delta_ms = -42 (PASS).
