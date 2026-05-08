# Spec: Fix SessionStart hook broken-pipe failure

- **Feature:** 107-fix-sessionstart-broken-pipe
- **Mode:** standard
- **Created:** 2026-05-08
- **RCA reference:** `docs/rca/20260508-110928-sessionstart-skills.md`
- **Status:** draft (rev 3 — addresses spec-reviewer iterations 1 and 2)

## Problem Statement

`plugins/pd/hooks/session-start.sh` exits non-zero on some Claude Code startups, producing the error `SessionStart:startup hook error / Failed with non-blocking status code: No stderr output`. The failure occurs when Claude Code closes the hook's stdout before the hook finishes writing its `hookSpecificOutput` JSON (e.g. during `/clear`, `/compact`, or specific bootstrap paths in CC v2.1.x).

The script's existing defenses are insufficient:

1. `trap '' PIPE` (line 10) was intended to neutralize SIGPIPE, but under `set -euo pipefail` (line 4) it only converts a SIGPIPE-141 child death into an EPIPE-write-error-exit-1, which `set -e` then propagates as the hook's exit code. The script's own banner comment (lines 6–10) claims this trap fixes the symptom — that claim is wrong.
2. `install_err_trap` in `lib/common.sh:152` (`trap 'echo "{}" 2>/dev/null; exit 0' ERR`) cannot self-recover because the trap body's own `echo` writes to the same closed stdout, fails with EPIPE, and aborts the trap before reaching `exit 0`.

When the hook fails, the user loses workflow-state context, memory injection, doctor summary, and reconciliation summary on that startup. The bug is intermittent and cosmetic in steady state, but workflow-degrading when it triggers.

## In Scope

- `plugins/pd/hooks/session-start.sh` — the hook script itself.
- `plugins/pd/hooks/lib/common.sh` — specifically `install_err_trap` and any shared write helpers that emit to stdout. **Scope guard:** see "Scope Guards" below — modifying `install_err_trap` requires re-review.
- `plugins/pd/hooks/tests/test-session-start.sh` — must gain closed-stdout reproduction cases.
- The hook's stale banner comment (lines 6–10) — must be corrected so future readers don't re-introduce the same misunderstanding.

## Out of Scope

- **Symptom B (61 skill descriptions dropped).** This is Claude Code v2.1.129+ `skillListingBudgetFraction` enforcement, not a pd defect. Confirmed by GitHub issue [anthropics/claude-code#56448](https://github.com/anthropics/claude-code/issues/56448). User mitigation is `~/.claude/settings.json` tuning, or cross-plugin description pruning — neither is a pd code change.
- Other hooks in `plugins/pd/hooks/` that may share the same anti-pattern. They will be audited in a follow-up if this fix establishes a working pattern, but are not in this feature's scope.
- Refactoring the hook's content-injection logic. The fix must be additive/defensive, not a rewrite.
- Performance optimization of the hook beyond the regression budget in NFR2.

## Scope Guards

**SG1.** If the design phase concludes that `install_err_trap` in `lib/common.sh` must be redesigned (vs. only `session-start.sh` patched locally), this spec MUST be re-reviewed before design proceeds. `install_err_trap` is shared by other hooks; redesigning it expands blast radius beyond the symptom this feature addresses.

**SG2.** If the design phase introduces any change to a hook other than `session-start.sh` and any change to `lib/common.sh` strictly required to fix `session-start.sh`, this spec MUST be re-reviewed.

## Key Definitions

For requirement testability, the following terms have normative meanings throughout:

- **"Closed-stdout pre-write"** — the hook is invoked with stdout redirected through `dd of=/dev/null bs=1 count=0`, which closes the read end before any byte is consumed.
- **"Closed-stdout mid-write"** — the hook is invoked with stdout redirected through `head -c 1 >/dev/null`, which consumes one byte and closes.
- **"Closed-stdout AND-stderr"** — the hook is invoked with both stdout and stderr redirected through closed pipes (matches the literal screenshot symptom in the RCA where neither stream produced visible output).
- **"Happy path"** — the hook is invoked with stdout redirected to a file descriptor that consumes all bytes successfully (e.g., `> /tmp/out.json`), which is how CC normally invokes hooks.

## Functional Requirements

**FR1 — Hook exits 0 under closed-stdout pre-write.**
When `bash plugins/pd/hooks/session-start.sh < /dev/null | dd of=/dev/null bs=1 count=0` runs, the hook MUST exit 0. (Today it exits 1 — see RCA reproduction matrix.)

**FR2 — Hook exits 0 under closed-stdout mid-write.**
When `bash plugins/pd/hooks/session-start.sh < /dev/null | head -c 1 >/dev/null` runs, the hook MUST exit 0.

**FR3 — Hook exits 0 under closed-stdout AND-stderr.**
When the hook is invoked with both stdout and stderr redirected through closed pipes (the RCA's literal-screenshot scenario), the hook MUST exit 0. Specifically: `bash plugins/pd/hooks/session-start.sh < /dev/null > >(dd of=/dev/null bs=1 count=0) 2> >(dd of=/dev/null bs=1 count=0)` MUST exit 0.

**FR4 — Hook continues to emit valid `hookSpecificOutput` JSON on the happy path.**
When stdout is healthy, the hook MUST emit a single JSON object on stdout where:
- `jq -e '.hookSpecificOutput.hookEventName == "SessionStart"'` succeeds, AND
- `jq -e '.hookSpecificOutput.additionalContext | type == "string"'` succeeds (the field exists and is a string; empty string is permitted on a clean install where `build_context` returns empty by design — see `session-start.sh:423` and the conditional accumulators at lines 865–917).

This MUST hold both before and after the fix (no regression). Note: the previous version of FR4 required non-empty `additionalContext`, which would have failed on a clean install where all 7 conditional context sources are empty.

**FR5 — Failures route to a structured log file.**
When the hook encounters an internal failure (broken pipe, ERR trap fired, Python subshell crash that propagates), it MUST append exactly one diagnostic line to the log path (resolution rule below) before exiting 0. The line MUST follow this exact schema (UTC, no fractional seconds, trailing `Z`):

```
<UTC-timestamp>\t<script-basename>:<line-no>\t<exit-code>\t<short-reason>
```

- `<UTC-timestamp>` is produced by `date -u +%Y-%m-%dT%H:%M:%SZ`. Example: `2026-05-08T03:14:11Z`.
- Fields are tab-separated; one line; no embedded newlines.
- Concrete example: `2026-05-08T03:14:11Z\tsession-start.sh:807\t1\tEPIPE on cat`.

**Log path resolution:**
1. If `PD_SESSION_START_LOG` env var is set and non-empty, use that path.
2. Else, use `$HOME/.claude/pd/session-start.log` (normative default).
3. The hook MUST `mkdir -p "$(dirname "$LOG_PATH")"` (idempotent, ignore errors) before append, to handle the first-run case where `$HOME/.claude/pd/` may not exist.

**Recovery-of-recovery (sub-FR5):** If the log write itself fails (disk full, permissions, etc.), the hook MUST still exit 0. Silent failure of the recovery path is preferable to surfacing a hook error to CC.

Suppressing diagnostics with `2>/dev/null` is no longer acceptable for the recovery path itself (the path writes to the log); however, the log-write command MAY use `|| true` to satisfy the recovery-of-recovery clause.

**FR5b — Log rotation.**
When the log file exceeds 1 MB at write time, the hook MUST truncate it: keep the last ~500 KB (tail) and discard the rest. Bash-side implementation: `tail -c 524288 "$LOG_PATH" > "$LOG_PATH.tmp" && mv "$LOG_PATH.tmp" "$LOG_PATH"` (or equivalent). External tools (logrotate, etc.) MUST NOT be required (NFR1). Rotation MUST happen before the new line is appended, so the appended line is always preserved. Running 1000 failure-loop iterations against the recovery path MUST NOT grow the file beyond 2 MB (verified by AC5).

**FR6 — Banner comment reflects reality.**
The comment at `session-start.sh:6-10` MUST be replaced. The replacement MUST cite `docs/dev_guides/hook-development.md` (or a new section therein) as the canonical source-of-truth for the broken-pipe handling pattern. The replacement MUST NOT claim that `trap '' PIPE` alone fixes the symptom. The single source of truth (FR6's referenced doc) MUST be updated to describe the actual pattern used.

**FR7 — Test harness covers closed-stdout failure modes.**
`plugins/pd/hooks/tests/test-session-start.sh` (or a new sibling test file invoked from `test-hooks.sh`) MUST contain at least these tests:
- **T1:** closed-stdout pre-write — exits 0.
- **T2:** closed-stdout mid-write — exits 0.
- **T3:** closed-stdout AND-stderr — exits 0.
- **T4:** happy path — exits 0 AND stdout passes the FR4 jq assertions.
- **T5:** log-file population — after running T1, T2, T3, the log file at `$HOME/.claude/pd/session-start.log` (or a test-overridden path via env var, see SG-test-isolation below) contains at least one line matching the FR5 schema regex `^[0-9T:Z-]+\t[a-z-]+\.sh:[0-9]+\t[0-9]+\t.+$`.

**SG-test-isolation:** Tests MUST NOT pollute the user's real `$HOME/.claude/pd/session-start.log`. The hook MUST honor a `PD_SESSION_START_LOG` environment variable; tests set this to a tempfile and clean up after. If the env var is unset, the hook uses the normative path.

**FR8 — Static guard against new uncaptured writes.**
The fix MUST include a CI-checkable guard (test assertion or shellcheck custom rule) that fails the test suite when a new uncaptured `echo`, `printf`, or `cat` (i.e., not inside `$(...)` command substitution and not piped through an EPIPE-safe wrapper) is added to `session-start.sh`. The guard's exact mechanism is design-phase choice (OQ-static-guard) but MUST be CI-checkable — a pure-comment banner-invariant does NOT satisfy this FR. AC11 enforces the guard's existence via a positive control (intentionally adding an unsafe `echo` to a test fixture and asserting the guard catches it).

## Non-Functional Requirements

**NFR1 — No new external dependencies.** The fix MUST use only tools already required by the pd plugin's hook layer (bash 3.2+, `jq`, the bundled `.venv` Python). No new system packages, no new pip dependencies.

**NFR2 — Latency budget (verifiable).** Median wall-clock time of `time bash plugins/pd/hooks/session-start.sh </dev/null >/dev/null 2>&1` over 11 runs (drop fastest and slowest, take median of remaining 9) MUST NOT exceed the same median measured against `develop` (pre-change) by more than 50 ms. AC8 enforces this. If NFR2 cannot be met, the design phase MUST escalate before implementation begins.

**NFR3 — Bash 3.2 compatibility.** The fix MUST work on macOS's default bash 3.2. No bash 4+ features (associative arrays, `${var,,}`, etc.) introduced solely by this fix.

**NFR4 — Idempotent and side-effect free under failure.** When the hook fails internally and recovers via FR5's log-and-exit-0 path, it MUST NOT leave stale state (lock files, temp files, half-written caches) that affects future invocations.

## Acceptance Criteria

The feature is complete when ALL of the following are true:

**AC1 — Reproduction passes.** A reproduction driver committed at `plugins/pd/hooks/tests/repro-broken-pipe.sh` (a permanent location, NOT under `agent_sandbox/`) shows hook exit 0 in all four scenarios from Key Definitions (happy path, closed-stdout pre-write, closed-stdout mid-write, closed-stdout AND-stderr). Today the equivalent scenarios produce exit 1 in two cases (per RCA reproduction matrix). The implement phase is responsible for promoting the agent_sandbox repro into the permanent test path.

**AC2 — New closed-stdout tests pass.** All five tests T1–T5 from FR7 pass on first run via `bash plugins/pd/hooks/tests/test-hooks.sh`.

**AC3 — Happy-path FR4 assertion passes.** A new test (or extension to T4) asserts `jq -e '.hookSpecificOutput.hookEventName == "SessionStart"'` and `jq -e '.hookSpecificOutput.additionalContext | type == "string"'` against the hook's stdout on a clean invocation. Both succeed (empty-string `additionalContext` is permitted, per FR4).

**AC4 — Existing tests still pass.** All existing `test-session-start.sh` and `test-hooks.sh` cases pass with no regressions.

**AC5 — Diagnostic log captures broken-pipe events and rotates per FR5b.** Two parts:
- **AC5a:** After running AC1's three failure scenarios, the log at `$PD_SESSION_START_LOG` (or default per FR5) contains at least one line per failure scenario matching the strict FR5 regex `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\t[a-z0-9_.-]+\.sh:[0-9]+\t[0-9]+\t.+$`.
- **AC5b:** Running the closed-stdout-pre-write scenario in a 1000-iteration loop does NOT grow the log file beyond 2 MB (verifies FR5b rotation is wired up). Test sets `PD_SESSION_START_LOG` to a tempfile.

**AC6 — Banner comment is corrected AND SoT doc is updated.** Three parts:
- **AC6a:** `session-start.sh:1-20` after the fix contains no claim that `trap '' PIPE` alone fixes broken-pipe failure.
- **AC6b:** `session-start.sh:1-20` after the fix contains a reference (file path or URL) to `docs/dev_guides/hook-development.md`.
- **AC6c:** `docs/dev_guides/hook-development.md` after the fix contains a section describing the broken-pipe handling pattern. The section MUST contain the strings `EPIPE`, `set -e`, and a reference to `session-start.sh`. The section MUST be added/modified by a commit on this feature's branch (verifiable via `git log --oneline docs/dev_guides/hook-development.md` showing a feature/107-* commit).

**AC7 — Manual smoke test in CC.** Running Claude Code ≥ v2.1.129 (the closer-cause version where skillListingBudgetFraction shipped; reporter saw symptom on v2.1.133) in this project with the patched hook installed: opening a fresh session, running `/clear` 3 times, and running `/compact` 3 times does NOT surface the `SessionStart:startup hook error` message at any point. (Verified by user before merge; the user records the CC version in the PR description.) **Fallback procedure:** if AC7 fails despite AC1–AC6 passing, the design phase MUST be re-entered with new evidence about CC's actual stdout-closure pattern; the spec is amended; a new design and implementation cycle runs. Do NOT merge if AC7 fails.

**AC8 — NFR2 latency budget met.** A benchmark script committed at `plugins/pd/hooks/tests/bench-session-start.sh` (a permanent location, NOT under `agent_sandbox/`) measures the 11-run median per NFR2 against `develop`'s baseline and against the patched hook. The patched median MUST NOT exceed the baseline median + 50 ms. The benchmark output (a small text or JSON file at `plugins/pd/hooks/tests/bench-results.txt`) is committed alongside the implementation.

**AC9 — No new lint or shellcheck violations.** `./validate.sh` passes; `shellcheck plugins/pd/hooks/session-start.sh plugins/pd/hooks/lib/common.sh` produces no new warnings introduced by this change.

**AC10 — Prerequisite verified during specify (probe committed).** A1's prerequisite (a bash construct of `set -euo pipefail; trap '' PIPE; { printf '{}\n' 2>/dev/null || true; }; exit 0` reliably exits 0 under closed-stdout) was verified during the specify phase. The verification probe MUST be committed at `plugins/pd/hooks/tests/probe-a1-exit0-under-broken-pipe.sh` (NOT in `/tmp/`) and MUST be runnable by any reviewer. The probe is part of the PR.

**AC11 — FR8 static guard catches new unsafe writes (positive control).** The implementation MUST include a positive-control test: a fixture script (e.g. `plugins/pd/hooks/tests/fixtures/unsafe-write-fixture.sh`) containing an intentionally-unsafe uncaptured `echo "foo"` outside command substitution, AND the FR8 guard's test, when pointed at this fixture, MUST report a failure. Conversely, when pointed at the post-fix `session-start.sh`, the guard MUST report success. This proves the guard is non-trivial.

**AC12 — First-run directory creation (A2 verified).** When `$HOME/.claude/pd/` does NOT exist (first-run scenario), the hook MUST still satisfy FR5: it creates the directory before logging, and the logging succeeds. Test: `HOME=$(mktemp -d) bash plugins/pd/hooks/session-start.sh | dd of=/dev/null bs=1 count=0 ; ls "$HOME/.claude/pd/session-start.log"` exits 0 in both commands.

## Verified Prerequisites

**A1 (verified, was Assumption).** During spec revision, a controlled test confirmed the fix-strategy prerequisite: a bash script with `set -euo pipefail; trap '' PIPE; { printf '{}\n' 2>/dev/null || true; } ; exit 0` exits with status 0 when stdout is redirected through `dd of=/dev/null bs=1 count=0`. Therefore, the proposed approach (emit a fallback `{}` JSON guarded with `|| true` before exit) is sufficient to satisfy FR1–FR3 at the bash level, regardless of whether CC's "non-blocking status code" message is conditional on exit code, stdout content, or both — exit-0 is the necessary and sufficient condition. The exact CC display logic is no longer load-bearing; the hook satisfies its API contract by exiting 0.

**A2 (resolved-by-FR5).** The diagnostic log path is `$HOME/.claude/pd/session-start.log` (or override via `PD_SESSION_START_LOG`), and FR5 explicitly requires `mkdir -p` before the first append to handle the first-run case where the directory may not exist. AC12 verifies first-run handling. A2 is therefore no longer load-bearing as an unverified assumption.

**A3 (verified-via-RCA).** The two `cat <<EOF` blocks at `session-start.sh:807` and `:922` are the only stdout-emitting surfaces vulnerable to broken-pipe failure on the current code. RCA hypothesis A-H3 verified this via static sweep — every other write is captured into `$(...)` (so its stdout is bash, not the hook's). FR8 prevents future regressions by adding a guard.

## Open Questions for Design Phase

- **OQ1.** Should the fix disable `set -e` only around at-risk write blocks, or wrap all writes in a helper that swallows EPIPE explicitly? Tradeoff: localized vs. systemic.
- **OQ2.** Should the EXIT trap (not just ERR trap) be the primary recovery mechanism, per the engineering memory entry "Hooks should install EXIT trap emitting valid default output"? Tradeoff: belt-and-suspenders vs. complexity.
- **OQ3.** Should `install_err_trap` in `lib/common.sh` be redesigned (affects other pd hooks) or only `session-start.sh` patched (localized)? **Per SG1 above, redesigning `install_err_trap` triggers spec re-review.**
- **OQ-static-guard.** What concrete CI-checkable mechanism implements FR8: shellcheck custom rule vs. test-time grep vs. pre-commit hook? (Pure banner-invariant is no longer an option per rev 3 FR8.)
- **OQ4 (resolved by FR5b).** Log rotation: bash-side `tail -c 524288 > tmp && mv` (or equivalent) at 1 MB threshold. NFR1 forbids external dependencies, and FR5b commits to bash-side. Implementation tactic remains design's choice.

## References

- RCA: `docs/rca/20260508-110928-sessionstart-skills.md`
- Anti-pattern memory: "trap '' PIPE doesn't fix SIGPIPE under set -e" (high confidence)
- Anti-pattern memory: "ERR-trap can't self-rescue when stdout is the broken pipe" (high confidence)
- Heuristic memory: "Hooks should install EXIT trap emitting valid default output"
- Heuristic memory: "Test bash hooks under SIGPIPE / closed-stdout conditions"
- Reproduction driver: `agent_sandbox/2026-05-08/rca-sessionstart-skills/reproduction/run-hook-baseline.sh`
- A1 verification probe: to be committed at `plugins/pd/hooks/tests/probe-a1-exit0-under-broken-pipe.sh` during implement (probe content recorded in this spec's conversation log; AC10 enforces commit)
- CC issue (Symptom B context, out of scope): [anthropics/claude-code#56448](https://github.com/anthropics/claude-code/issues/56448)
- Long-lived doc target for FR6 SoT: `docs/dev_guides/hook-development.md`

## Revision Notes

**Rev 3 (2026-05-08, post spec-reviewer iteration 2):**
- FR8: removed deferred option (b) (banner-invariant); FR8 now requires a CI-checkable guard. Added AC11 positive-control test to enforce non-triviality.
- Split FR5 into FR5 + FR5b. FR5b normatively commits to bash-side `tail -c`+`mv` rotation at 1 MB. AC5 split into AC5a (per-line schema with strict regex) and AC5b (1000-iteration cap at 2 MB).
- Softened FR4 to allow empty-string `additionalContext` (the previous tightening would have failed clean-install scenarios where `build_context` returns empty by design — verified via `session-start.sh:865-917`). AC3 updated.
- FR5 now commits to UTC-only `date -u +%Y-%m-%dT%H:%M:%SZ`; AC5a regex tightened to match exactly (no fractional, no offset).
- FR5: added explicit `mkdir -p` requirement and recovery-of-recovery clause (log-write failure still exits 0). A2 promoted from unverified assumption to resolved-by-FR5; AC12 verifies first-run directory creation.
- AC1, AC8, AC10: moved load-bearing scripts out of `agent_sandbox/` into permanent `plugins/pd/hooks/tests/` paths (per CLAUDE.md, agent_sandbox is non-canonical).
- AC6 split into AC6a/b/c. AC6c verifies that `docs/dev_guides/hook-development.md` was actually updated by this feature's commits (not just referenced).
- AC7: tightened CC version requirement from "v2.1.x" to "≥ v2.1.129" (closer-cause version where the symptom emerged).
- Added AC11 (FR8 positive control) and AC12 (first-run directory creation).

**Rev 2 (2026-05-08, post spec-reviewer iteration 1):**
- Added "Key Definitions" with normative reproduction commands; rewrote FR1/FR2/FR3 to cite them (was: prose only). New FR3 covers the closed-stdout-AND-stderr scenario from the RCA's literal-screenshot match (was: only mentioned in AC1 with no FR backing).
- Specified FR5 log line schema concretely (TSV with named fields and example).
- Promoted A1 from assumption to verified prerequisite via in-conversation probe; added AC10 to record the verification. Reframed: the load-bearing question is "does the hook exit 0?", which is verifiable; CC display behavior is no longer on the critical path.
- Added AC7 fallback procedure (was: no plan if AC7 failed); changed AC7 to require multiple `/clear` and `/compact` invocations (was: one each).
- Added Scope Guards (SG1, SG2) and tied OQ3 to SG1 (was: scope creep risk implicit only).
- Promoted A3 to "verified-via-RCA" with reference to RCA hypothesis A-H3 sweep (was: unverified assumption).
- Added FR8 (static guard) so future commits can't silently regress A3.
- NFR2: added concrete benchmark mechanism (11-run median); added AC8 to enforce.
- Committed FR4 to a normative jq-assertion shape; added AC3 to enforce on happy path.
- Committed FR5 to `$HOME/.claude/pd/session-start.log` as normative path with `PD_SESSION_START_LOG` env-var override for tests; AC5 references both.
- Committed FR6 SoT pointer to `docs/dev_guides/hook-development.md` (was: ambiguous "lib/common.sh or this spec").
- Added SG-test-isolation under FR7 to prevent test pollution of user state.
