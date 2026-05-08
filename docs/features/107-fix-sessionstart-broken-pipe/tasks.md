# Tasks: Fix SessionStart hook broken-pipe failure

- **Feature:** 107-fix-sessionstart-broken-pipe
- **Plan:** `plan.md`

Each task: 5–15 min. DoD = binary pass/fail criteria.

### Task 1: Create A1 + printf-SIGPIPE probe scripts

**Files:** `plugins/pd/hooks/tests/probe-a1-exit0-under-broken-pipe.sh`, `plugins/pd/hooks/tests/probe-printf-sigpipe.sh`
**Source:** Copy verbatim from design.md C6 inlined probe content.
**Action:** Create both files; `chmod +x`. Both should be self-contained bash scripts.
**DoD:**
- `bash plugins/pd/hooks/tests/probe-a1-exit0-under-broken-pipe.sh | dd of=/dev/null bs=1 count=0; echo $?` → `0`
- `bash plugins/pd/hooks/tests/probe-printf-sigpipe.sh` runs and prints 4 scenario blocks (no shell error).
- Files are executable.
**Depends on:** none.

### Task 2: Create FR8 static-guard fixture

**File:** `plugins/pd/hooks/tests/fixture-unsafe-write.sh`
**Action:** Create file with intentionally line-leading `cat <<EOF` followed by a stub heredoc body and `EOF` marker. Content (one line-leading cat heredoc):
```bash
#!/usr/bin/env bash
# Intentionally unsafe — fixture for FR8 positive control. Do not source.
cat <<EOF
{"unsafe": "fixture"}
EOF
```
Make executable.
**DoD:**
- File exists at `plugins/pd/hooks/tests/fixture-unsafe-write.sh`.
- `grep -nE '^[[:space:]]*cat[[:space:]]*<<' plugins/pd/hooks/tests/fixture-unsafe-write.sh` produces ≥1 match.
**Depends on:** none.

### Task 3: Create FR8 static-guard script

**File:** `plugins/pd/hooks/tests/check-no-unsafe-writes.sh`
**Action:** Create per design TD9. Accepts a target path argument (defaulting to `plugins/pd/hooks/session-start.sh`). Greps for line-leading `cat <<` using `[[:space:]]` POSIX class; exits 1 with violation message if found.
**DoD:**
- `bash plugins/pd/hooks/tests/check-no-unsafe-writes.sh plugins/pd/hooks/tests/fixture-unsafe-write.sh; echo $?` → `1` (positive control catches the fixture).
- `bash plugins/pd/hooks/tests/check-no-unsafe-writes.sh /tmp/empty-file-no-cat.sh` → `0` (negative control on a clean file).
- Uses `[[:space:]]` not `\s` (verify by grep `\\s` returns no match in the script).
**Depends on:** Task 2.

### Task 4: Create AC1 reproduction driver

**File:** `plugins/pd/hooks/tests/repro-broken-pipe.sh`
**Action:** Create driver running 4 scenarios (happy, closed-stdout pre-write, mid-write, AND-stderr) per design Test command vocabulary. Each invokes `plugins/pd/hooks/session-start.sh` and asserts hook exit 0. Sets `PD_SESSION_START_LOG=$(mktemp)` to isolate.
**DoD (creation-time, binary):**
- File exists, executable.
- `bash -n plugins/pd/hooks/tests/repro-broken-pipe.sh` parses cleanly (no syntax errors).
- Script comment documents the expected pre-fix baseline (≥2 of 4 scenarios fail) so future readers understand the regression test.
**DoD (post-implementation, verified by Task 11):** All 4 scenarios pass (exit 0). Task 4 marks done at creation; final pass verification deferred to Task 11.
**Depends on:** Task 1.

### Task 5: Create test-session-start-broken-pipe.sh (T1–T9, T-recovery)

**File:** `plugins/pd/hooks/tests/test-session-start-broken-pipe.sh`
**Action:** Create the test file containing the following sub-tests:
- **T1:** closed-stdout pre-write → exit 0
- **T2:** closed-stdout mid-write → exit 0
- **T3:** closed-stdout AND-stderr → exit 0
- **T4:** happy path → exit 0 + jq assertions for `hookSpecificOutput.hookEventName == "SessionStart"` and `additionalContext | type == "string"`
- **T5:** log-file population — runs T1+T2+T3, asserts `$PD_SESSION_START_LOG` matches `PD_LOG_LINE_REGEX` constant. Also tests AC5b (1000-iteration loop, log size < 2 MB).
- **T6:** happy-path with multiline `additionalContext` containing `"`, `\`, `\n`, unicode — JSON parses cleanly (R1 mitigation).
- **T7:** *(removed — defensive `set +e` is verified by code review of `__pd_exit_handler`; T1-T3 already exercise the EXIT trap recovery path. Adding a `false`-injection test would require a production-helper backdoor that's out of scope.)*
- **T8 (renumbered to T7):** `PD_FORCE_BUILD_CONTEXT_FAIL=1` — assert hook still exits 0 with valid JSON (R7 mitigation).
- **T8 (NEW — AC12 first-run):** Run `HOME=$(mktemp -d) PD_SESSION_START_LOG="$HOME/.claude/pd/session-start.log" bash plugins/pd/hooks/session-start.sh </dev/null | dd of=/dev/null bs=1 count=0 ; rc=$?` — assert `rc == 0` AND assert `[[ -f "$HOME/.claude/pd/session-start.log" ]]` (directory was auto-created and a log line was appended; per AC12).
- **T9 (NEW — FR5 recovery-of-recovery):** Set `PD_SESSION_START_LOG=/dev/null/cannot-create.log` (an unwriteable path) and invoke under closed-stdout; assert hook still exits 0 (log-write failure is silently swallowed per FR5 recovery-of-recovery clause).
- Single regex constant `PD_LOG_LINE_REGEX` used by T5 (per TD5).
- Add an invocation in `plugins/pd/hooks/tests/test-hooks.sh` so it runs as part of the suite.

**DoD (creation-time, binary):**
- File exists, executable.
- `bash -n plugins/pd/hooks/tests/test-session-start-broken-pipe.sh` parses cleanly.
- Test file references `PD_LOG_LINE_REGEX` constant (single source of truth).
- All 9 sub-tests are present in the file (T1-T9).

**DoD (post-implementation, verified by Task 11):** `bash plugins/pd/hooks/tests/test-session-start-broken-pipe.sh` exits 0 with all 9 sub-tests passing.

**Depends on:** Tasks 1, 3.

### Task 6: Create lib/session-start-helpers.sh

**File:** `plugins/pd/hooks/lib/session-start-helpers.sh`
**Action:** Create new file containing per design C1, C2, C3:
- `safe_emit_hook_json(json)` — `{ printf '%s\n' "$json" 2>/dev/null; } || true`
- `pd_log_diagnostic(env_var_name, default_path, basename, line, exit_code, reason)` — generic with rotation, `[[:space:]]`-equivalent path handling, `mkdir -p`, BSD/GNU `stat` fallback chain.
- `pd_log_session_start_diagnostic(line, exit_code, reason)` — convenience wrapper.
- `install_session_start_traps()` — installs ERR + EXIT traps with `set +e` defensive.
- `__pd_err_handler(line, rc)` and `__pd_exit_handler(rc)` — both `set +e` first; EXIT trap gates fallback emission on `rc != 0`.
**DoD:**
- File exists; sourceable: `bash -c 'source plugins/pd/hooks/lib/session-start-helpers.sh; type safe_emit_hook_json'` exits 0 and prints "function".
- `shellcheck plugins/pd/hooks/lib/session-start-helpers.sh` produces no NEW warnings beyond documented `# shellcheck disable=` comments (acceptable for the `eval` indirect lookup, which requires SC2086/SC2294 disable with rationale comment). Aligns with spec AC9 ("no new shellcheck violations introduced by this change").
**Depends on:** none.

### Task 7: Add T8 guard to build_context

**File:** `plugins/pd/hooks/session-start.sh` (around line 423)
**Action:** Add the `PD_FORCE_BUILD_CONTEXT_FAIL` guard at the top of `build_context()`:
```bash
build_context() {
    if [[ -n "${PD_FORCE_BUILD_CONTEXT_FAIL:-}" ]]; then
        return 1
    fi
    # ... existing body ...
}
```
**DoD:**
- `PD_FORCE_BUILD_CONTEXT_FAIL=1 bash -c 'source plugins/pd/hooks/session-start.sh; build_context'` returns 1.
- Without the env var, `build_context` returns 0 on a clean invocation.
**Depends on:** none (modifies session-start.sh but only adds a 4-line guard at function start).

### Task 8: Update session-start.sh banner and trap installer

**File:** `plugins/pd/hooks/session-start.sh` (lines 1-15)
**Action:**
- Replace lines 1-15 banner with new content per design C4 (references `docs/dev_guides/hook-development.md`; warns DO NOT remove `trap '' PIPE`).
- KEEP `set -euo pipefail` at line 4.
- KEEP `trap '' PIPE` at line 10 (TD8).
- Replace `install_err_trap` (around line 13) with:
  ```bash
  source "$SCRIPT_DIR/lib/session-start-helpers.sh"
  install_session_start_traps
  ```
**DoD:**
- `head -20 plugins/pd/hooks/session-start.sh` does NOT contain "trap '' PIPE alone fixes" or similar wrong claim.
- `head -20 plugins/pd/hooks/session-start.sh` contains the string "hook-development.md".
- `grep -n "trap '' PIPE" plugins/pd/hooks/session-start.sh` shows line 10 still present.
- `grep -n "install_session_start_traps" plugins/pd/hooks/session-start.sh` shows the new call.
- `bash plugins/pd/hooks/session-start.sh </dev/null >/tmp/out.json 2>&1; echo $?` → `0` (happy path still works after this change alone).
**Depends on:** Tasks 6, 7.

### Task 9: Replace cat <<EOF at line 807

**File:** `plugins/pd/hooks/session-start.sh` (around line 807)
**Action:** Replace the `cat <<EOF ... EOF` heredoc emission block with:
```bash
local payload
payload=$(printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}' "$escaped_message")
safe_emit_hook_json "$payload"
```
(This block is the early-exit JSON for missing python3; uses simple string interpolation, no jq.)
**DoD:**
- `grep -nE '^[[:space:]]*cat[[:space:]]*<<' plugins/pd/hooks/session-start.sh` produces NO match for line 807 area.
- Existing test (manually triggering python3-missing path) still emits valid JSON.
**Depends on:** Task 8.

### Task 10: Replace cat <<EOF at line 922 (with jq fallback)

**File:** `plugins/pd/hooks/session-start.sh` (around line 922)
**Action:** Replace the main JSON emission heredoc with the `command -v jq` branch from design C4:
```bash
local payload
if command -v jq >/dev/null 2>&1; then
    payload=$(jq -nc --arg event "SessionStart" --arg ctx "$escaped_context" \
        '{hookSpecificOutput: {hookEventName: $event, additionalContext: $ctx}}')
else
    payload=$(printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}' "$escaped_context")
fi
safe_emit_hook_json "$payload"
```
**DoD:**
- `grep -nE '^[[:space:]]*cat[[:space:]]*<<' plugins/pd/hooks/session-start.sh` produces NO match (FR8 invariant: zero line-leading cat heredocs).
- `bash plugins/pd/hooks/session-start.sh </dev/null | jq -e '.hookSpecificOutput.hookEventName == "SessionStart"'` → exit 0.
- `bash plugins/pd/hooks/tests/check-no-unsafe-writes.sh plugins/pd/hooks/session-start.sh; echo $?` → `0`.
**Depends on:** Tasks 8, 9.

### Task 11: Run repro driver + full test file; verify all green

**Action:** Execute `bash plugins/pd/hooks/tests/repro-broken-pipe.sh` and `bash plugins/pd/hooks/tests/test-session-start-broken-pipe.sh`. All 4 repro scenarios MUST exit 0; all T1–T8 MUST pass.
**DoD:**
- Repro: 4/4 scenarios pass (exit 0).
- Test file: T1–T8 all pass.
- `bash plugins/pd/hooks/tests/test-hooks.sh` overall exit 0.
- `./validate.sh` passes.
**Depends on:** Tasks 4, 5, 6, 7, 8, 9, 10.

### Task 12: Update docs/dev_guides/hook-development.md

**File:** `docs/dev_guides/hook-development.md`
**Action:** Add (or extend) section "Broken-pipe handling for hooks emitting structured output" per design C5. Required content:
- Explanation of why `set -e` + `cat <<EOF` is unsafe (cite RCA).
- Explanation of why `trap '' PIPE` is necessary but not sufficient.
- The canonical pattern (`safe_emit_hook_json` + `install_session_start_traps`) with code example.
- Test recipes (closed-stdout pre-write, mid-write, AND-stderr).
- Reference to RCA `docs/rca/20260508-110928-sessionstart-skills.md` and feature 107.
**DoD:**
- File exists.
- File contains literal strings `EPIPE`, `set -e`, `session-start.sh`, `safe_emit_hook_json`.
- `git log --oneline docs/dev_guides/hook-development.md` shows a feature/107-* commit (AC6c).
**Depends on:** none (documentation task).

### Task 13a: Create bench-session-start.sh

**File:** `plugins/pd/hooks/tests/bench-session-start.sh`
**Action:** Create the script per design C7: pre-flight `git status --porcelain` check, `git worktree add .pd-worktrees/bench-<sha>/` against merge-base, 11-run median (drop fastest+slowest, median of 9), `git worktree remove`, write results to `bench-results.txt`.
**DoD:**
- `bench-session-start.sh` exists, executable.
- `bash -n plugins/pd/hooks/tests/bench-session-start.sh` parses cleanly.
- Script's helper functions (e.g., `measure_median`) parse without syntax error in a dry-run sourced context.
- Script header comments cite design TD7 + C7.
**Depends on:** Task 11.

### Task 13b: Run bench-session-start.sh and commit bench-results.txt

**File:** `plugins/pd/hooks/tests/bench-results.txt`
**Action:** Run `bash plugins/pd/hooks/tests/bench-session-start.sh` and commit the resulting `bench-results.txt` with the banner comment "# Generated at PR open; re-run locally to re-verify but do not re-commit." Note: the `#` prefix is a bash-source comment (the file is plain text and `source`-able as bash key=value).
**DoD:**
- `bench-results.txt` exists, contains `baseline_sha=`, `baseline_median_ms=`, `patched_median_ms=`, `delta_ms=`, `threshold_ms=50` lines.
- First line of the file is the banner comment.
- `delta_ms` ≤ 50 (NFR2 verified per AC8).
- File is committed in this feature branch.
**Depends on:** Task 13a.

### Task 14: Spec amendment — update FR5 example reason string

**File:** `docs/features/107-fix-sessionstart-broken-pipe/spec.md` (FR5 example block)
**Action:** Replace the example reason string `EPIPE on cat` with a string from the Reason Vocabulary table (e.g., `EXIT non-zero`). Two-line edit.
**DoD:**
- `grep -n 'EPIPE on cat' docs/features/107-fix-sessionstart-broken-pipe/spec.md` produces no match.
- `grep -n 'EXIT non-zero' docs/features/107-fix-sessionstart-broken-pipe/spec.md` produces ≥1 match (in FR5 example).
**Depends on:** none (documentation task; can run in parallel with T12, T13).

### Task 15: Final validate.sh + check-no-unsafe-writes guard CI integration

**Action:**
- Add `bash plugins/pd/hooks/tests/check-no-unsafe-writes.sh` to `plugins/pd/hooks/tests/test-hooks.sh` so it runs as part of the suite.
- Run `./validate.sh` to confirm no plugin-validation regressions.
- Run `bash plugins/pd/hooks/tests/test-hooks.sh` to confirm full hook suite passes.
- Run `bash plugins/pd/hooks/tests/check-no-unsafe-writes.sh` (no args; default to session-start.sh) — exits 0.
**DoD:**
- `./validate.sh` exit 0.
- `bash plugins/pd/hooks/tests/test-hooks.sh` exit 0 with no errors in summary.
- `check-no-unsafe-writes.sh` runs as part of `test-hooks.sh`.
**Depends on:** all prior tasks.

## Parallel Execution Plan

| Group | Tasks | Notes |
|---|---|---|
| A | T1, T2, T12, T14 | All independent — no shared file edits |
| B | T3, T6 | After T2 (T3 needs fixture); T6 independent |
| C | T7 | Modifies session-start.sh — MUST NOT parallelize with T8/T9/T10 |
| D | T4, T5 | T4 after T1; T5 after T1+T3 |
| E | T8 | After T6, T7. **Sequential file edit on session-start.sh** |
| F | T9 | After T8. **Sequential file edit on session-start.sh** |
| G | T10 | After T9. **Sequential file edit on session-start.sh** |
| H | T11 | After T4, T5, T6, T7, T8, T9, T10 |
| I | T13a | After T11 (bench needs working hook) |
| J | T13b | After T13a (run + commit) |
| K | T15 | After all prior tasks |

**Critical sequential constraint:** T7, T8, T9, T10 all modify `plugins/pd/hooks/session-start.sh`. They MUST run serially (or in the same merge serialization step under `.pd-worktrees/`-style worktree dispatch). The implementer's worktree orchestration must respect this.
