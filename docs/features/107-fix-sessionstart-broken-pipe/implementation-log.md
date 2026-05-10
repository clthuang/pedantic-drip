# Implementation Log: feature/107-fix-sessionstart-broken-pipe

**Mode:** Direct-orchestrator (per "rigorous-upstream-enables-direct-orchestrator-implement" pattern; binary DoDs in tasks.md make per-task subagent dispatch unnecessary).

## T0 Baselines

- Branch: `feature/107-fix-sessionstart-broken-pipe`
- Base: `develop`
- HEAD before implement: `4f485a0` (post create-plan completion)
- Pre-existing hook test suite count: 114 tests (verified passing post-implementation).

## Per-Task DoD Outcomes

| Task | DoD outcome |
|---|---|
| T1 (probes) | PASS: probe-a1 exits 0 under closed-stdout; probe-printf-sigpipe runs cleanly |
| T2 (FR8 fixture) | PASS: line-leading `cat <<EOF` present |
| T3 (FR8 guard) | PASS: positive control catches fixture, negative control passes empty file, uses `[[:space:]]` |
| T4 (repro driver) | PASS: 4/4 scenarios exit 0 after the fix |
| T5 (test file T1-T9) | PASS: 15 sub-tests (T1-T9 + T5b/T5c rotation + T4/T7 multi-assert) all pass |
| T6 (helpers lib) | PASS: file sourceable; functions defined; bash 3.2 compat verified (eval indirect lookup, stat fallback chain) |
| T7 (build_context guard) | PASS: structural grep finds guard; T7 sub-test verifies behavior |
| T8 (banner + traps) | PASS: banner cites SoT doc + warns DO NOT remove `trap '' PIPE`; install_session_start_traps active |
| T9 (L807 swap) | PASS: zero line-leading cat heredocs at L807 area; safe_emit_hook_json call present |
| T10 (L922 swap) | PASS: zero line-leading cat heredocs in entire file (FR8 invariant); jq path + escape_json fallback |
| T11 (full verification) | PASS: 4/4 repro + 15/15 sub-tests + 114/114 existing hook tests |
| T12 (SoT doc) | PASS: `docs/dev_guides/hook-development.md` extended; contains EPIPE/set -e/session-start.sh/safe_emit_hook_json |
| T13a (bench script) | PASS: bench-session-start.sh executable; uses git worktree + HOME isolation + hook staging |
| T13b (bench run + commit) | PASS: bench-results.txt committed; **delta_ms=-42** (patched 42ms FASTER than baseline; NFR2 PASS) |
| T14 (spec amendment) | PASS: FR5 example reason updated `EPIPE on cat` → `EXIT non-zero` |
| T15 (validate.sh + CI integration) | PASS: validate.sh passes (after extending err-trap check to also accept install_session_start_traps); test-hooks.sh integrates both new test scripts |

## Tooling-Friction Notes

1. **NFR2 bench methodology bug discovered + fixed.** Initial bench compared HEAD's project state (with feature 107 active) vs merge-base's worktree (without it), producing a 577ms apparent regression. The actual code is FASTER. Fixed by staging both hook versions against HEAD's project state with `HOME=$(mktemp -d)` isolation. Lesson: when benchmarking hooks, isolate ALL state-driven inputs, not just `$HOME`.
2. **escape_json optimization (perf side-quest).** Discovered escape_json was called even on the jq path (which doesn't use the result, since jq --arg handles encoding). Skipping it on jq path saved ~30ms on large contexts.
3. **validate.sh err-trap invariant required updating** to accept the new `install_session_start_traps` (a strict superset of `install_err_trap` that adds the EXIT trap). Without this, the project's own validation gate would reject the fix.
4. **T5 design assumption was inverted** — the fix makes closed-stdout NOT a failure, so it doesn't trigger the diagnostic log. T5 had to switch to `PD_FORCE_BUILD_CONTEXT_FAIL=1` (which forces the EXIT trap log path) to verify the log machinery.
5. **T8 hardcoded `/tmp/t7-out.json` removed** during task-reviewer iter 1; switched to `mktemp` per-test for CI parallel safety.

## Phase Outcome

All 15 tasks completed with binary DoDs satisfied. Implementation phase complete pending the standard 3-level reviewer dispatch (workflow Step 7).

