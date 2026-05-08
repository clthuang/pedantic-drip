# Design: Fix SessionStart hook broken-pipe failure

- **Feature:** 107-fix-sessionstart-broken-pipe
- **Spec:** `docs/features/107-fix-sessionstart-broken-pipe/spec.md` (rev 3)
- **Status:** draft (rev 3 — addresses design-reviewer iterations 1 and 2)

## Prior Art Research

**Codebase patterns found** (`pd:codebase-explorer` agent, sonnet):

1. `emit_hook_json` already exists in `plugins/pd/hooks/lib/common.sh:175-215`. It uses `printf '%s\n' "$out"` (jq-built path) and `printf '...' ...` (fallback path). It is NOT currently used by `session-start.sh`. Both paths are EPIPE-vulnerable — there is no `|| true` on the printfs.
2. `install_err_trap` at `lib/common.sh:151-153` uses `trap 'echo "{}" 2>/dev/null; exit 0' ERR`. The `2>/dev/null` masks the trap's own diagnostic; under `set -e` the failing echo aborts the trap before `exit 0` (RCA Cause 2).
3. EXIT trap pattern already used in pd: `capture-on-stop.sh:14`, `tag-correction.sh:15`, `pre-edit-unicode-guard.sh:13` use `trap 'printf "{}\n"' EXIT` or equivalent. None currently EPIPE-guard the printf.
4. **9 pd hooks use `cat <<EOF`** for JSON emission (session-start.sh has 2 sites; 8 other hooks). Per SG2, only `session-start.sh` is in scope; the helper added here is generic so other hooks could adopt it later.
5. **Established log path convention**: `$HOME/.claude/pd/<name>.log`. `meta-json-guard.log` (JSONL with timestamp+tool+path+feature_id at `meta-json-guard.sh:101`) is the closest precedent. We use TSV for simpler grep/regex testing.
6. **No closed-stdout test idiom exists** anywhere in `plugins/pd/hooks/tests/`. Introduced here.
7. **`jq -nc --arg`** is the established JSON-construction pattern (`capture-on-stop.sh:99,134`, `tag-correction.sh:52`). `session-start.sh` builds via bash string concat + `escape_json` then heredoc-emits.

**External research findings** (`pd:internet-researcher` agent, sonnet):

1. **`SIG_IGN` is preserved across `execve(2)`**: a parent that ignores SIGPIPE causes its child processes (`cat`) to inherit `SIG_IGN`. Children **cannot reset SIGPIPE to default** via bash `trap`. This means: for child-process writes, `trap '' PIPE` in the hook is functionally a no-op for inheritance — children inherit SIG_IGN from the parent's runner regardless. **However, for the hook's own bash-builtin writes (e.g. `printf`), `trap '' PIPE` IS effective and load-bearing** — without it, the hook process itself dies with SIGPIPE-141 on a closed-stdout write. See "Verified Bash Behavior" below for the empirical evidence.
2. **`{ cat <<'EOF' || true; ... EOF }` is parse-correct**: bash scans heredoc markers at parse time; `|| true` applies to cat's runtime exit status.
3. **`printf` (bash builtin) avoids the child-process inheritance issue** but is itself a write through stdout fd; under default SIGPIPE disposition the bash process dies. Therefore `printf '%s\n' "$json" 2>/dev/null || true` is EPIPE-safe **only when SIGPIPE is ignored at the bash level via `trap '' PIPE`**.
4. **EXIT trap > ERR trap for fallback emission**: ERR misses failures inside `if`/`while`/`&&`/`||` conditionals; EXIT always fires. Pattern: `_fb() { local rc=$?; ...; }; trap '_fb' EXIT`.
5. **Log rotation atomicity**: `tail -c N file > tmpfile && mv tmpfile file` is atomic via `rename(2)` within a single rotation. Concurrent rotations are last-writer-wins (R8 below).
6. **Claude Code hook conventions**: must exit 0 for JSON to be processed; `hookSpecificOutput` JSON wrapper enables `additionalContext` injection.

Sources captured in `references/research-2026-05-08.md` (committed alongside design).

### Verified Bash Behavior (added rev 2 — addresses design-reviewer blocker #1)

A controlled experiment (logged in conversation, to be committed at `plugins/pd/hooks/tests/probe-printf-sigpipe.sh`) verified the following exit-code matrix on macOS bash 3.2 with subshell stdout piped through `head -c 1`:

| Configuration | Outer pipeline rc | Inner subshell behavior |
|---|---|---|
| no trap, no `\|\| true`, no `set -e` | 0 (head's rc) | Bash subshell SIGPIPE-killed silently after first write past head's read |
| `trap '' PIPE`, no `\|\| true` | 0 | printf returns rc=1 on EPIPE; subshell continues until `\|\| { exit 1 }` fires |
| `set -e`, no `trap '' PIPE`, with `\|\| true` | 0 (head's rc) | Bash subshell SIGPIPE-killed before `\|\| true` runs |
| `set -e` + `trap '' PIPE` + `{ ...; } \|\| true` | 0 | printf returns 1, `\|\| true` swallows, loop completes normally |

**Conclusion:** `trap '' PIPE` is load-bearing for the printf-based fix. Removing it would re-introduce SIGPIPE-141 silent death of the hook process. The fix uses BOTH `trap '' PIPE` AND `{ printf ...; } || true`, which is co-load-bearing — neither alone is sufficient.

This is the canonical fix and the basis for TD1 (rev 2) and TD8.

## Architecture Overview

```mermaid
flowchart TD
    A[Hook invoked by CC] --> B[trap '' PIPE retained at line 10]
    B --> C[install_session_start_traps installed]
    C --> D[main: build_context]
    D --> E[safe_emit_hook_json json]
    E -->|happy| F[main returns 0]
    E -->|EPIPE| G[printf returns 1, '|| true' swallows]
    G --> F
    F --> H[EXIT trap fires]
    H --> I{rc==0?}
    I -->|yes| J[exit 0 — main already emitted]
    I -->|no| K[set +e defensive]
    K --> L[printf '{}' fallback EPIPE-safe]
    L --> M[pd_log_diagnostic to file]
    M --> N[exit 0]
```

The fix is **additive** to `session-start.sh` and adds new helpers in **a new file `plugins/pd/hooks/lib/session-start-helpers.sh`** (rev 2 — addresses design-reviewer warning #5; keeps shared `lib/common.sh` clean of session-start-specific code). `install_err_trap` is **untouched** (per SG1).

### Components

#### C1. New helper: `safe_emit_hook_json` (in `lib/session-start-helpers.sh`)

Replaces the two `cat <<EOF` heredoc blocks at `session-start.sh:807` and `:922`. Uses `printf` with EPIPE guard.

```bash
# REQUIRES: caller has set 'trap "" PIPE' before invocation. Without it,
# the bash process is SIGPIPE-killed before printf returns and '|| true'
# never runs. See verified bash behavior in design.md.
safe_emit_hook_json() {
    local json="$1"
    { printf '%s\n' "$json" 2>/dev/null; } || true
}
```

This is the **EPIPE-safe wrapper** referenced in FR8 (resolves spec suggestion #2). The function name is the canonical token for the FR8 grep guard (TD9).

#### C2. New helper: `pd_log_diagnostic` (in `lib/session-start-helpers.sh`)

Implements FR5/FR5b. Generic across log paths via the env-var-name parameter (rev 2 — addresses warning #5):

```bash
# Generic diagnostic logger. log_env_var_name lets callers (e.g. session-start.sh)
# wire to PD_SESSION_START_LOG; other hooks could pass their own.
pd_log_diagnostic() {
    local log_env_var_name="$1"
    local default_log_path="$2"
    local script_basename="$3"
    local line_no="$4"
    local exit_code="$5"
    local reason="$6"

    # Indirect lookup of env var (bash 3.2 compat)
    local log_path
    eval "log_path=\${$log_env_var_name:-$default_log_path}"

    local log_dir
    log_dir="$(dirname "$log_path")"
    mkdir -p "$log_dir" 2>/dev/null || return 0

    # Rotation: if file > 1 MB, keep last 500 KB (FR5b, TD3)
    if [[ -f "$log_path" ]]; then
        local size
        size=$(stat -f%z "$log_path" 2>/dev/null || stat -c%s "$log_path" 2>/dev/null || echo 0)
        if (( size > 1048576 )); then
            local tmp
            tmp=$(mktemp "${log_path}.XXXXXX" 2>/dev/null) || return 0
            tail -c 524288 "$log_path" > "$tmp" 2>/dev/null && mv "$tmp" "$log_path" 2>/dev/null
        fi
    fi

    # Append TSV line; recovery-of-recovery: failures swallowed
    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "0000-00-00T00:00:00Z")
    printf '%s\t%s:%s\t%s\t%s\n' "$ts" "$script_basename" "$line_no" "$exit_code" "$reason" \
        >> "$log_path" 2>/dev/null || return 0
}
```

Convenience wrapper for session-start specifically:

```bash
pd_log_session_start_diagnostic() {
    pd_log_diagnostic "PD_SESSION_START_LOG" "$HOME/.claude/pd/session-start.log" \
        "session-start.sh" "$1" "$2" "$3"
}
```

#### C3. New helper: `install_session_start_traps` (in `lib/session-start-helpers.sh`)

Installs ERR + EXIT traps. The EXIT trap is the recovery path; ERR is for diagnostics only. **Defensively `set +e` inside the trap body** (rev 2 — addresses blocker #3).

```bash
# Sets up traps for session-start.sh. Caller's set -e remains active during
# main(), is disabled inside the trap bodies for robust recovery.
install_session_start_traps() {
    trap '__pd_err_handler ${LINENO} $?' ERR
    trap '__pd_exit_handler $?' EXIT
}

__pd_err_handler() {
    local line_no="$1"
    local rc="$2"
    set +e   # defensive (rev 2)
    pd_log_session_start_diagnostic "$line_no" "$rc" "ERR trap fired"
    # ERR trap fires under set -e; the script then exits at the failing site
    # after this function returns. The EXIT trap runs next and handles
    # fallback emission. We do not call `exit` explicitly here so the EXIT
    # trap observes the original failure rc via $?.
}

__pd_exit_handler() {
    local rc="$?"
    set +e   # defensive (rev 2 — blocker #3 mitigation)

    if (( rc != 0 )); then
        # Main failed; emit fallback JSON (only on failure path; happy path
        # already emitted via main's safe_emit_hook_json call). This avoids
        # double emission and removes the need for an emission-tracking flag.
        # (rev 2 — blocker #2 resolution: no global flag, no subshell hazard.)
        { printf '{}\n' 2>/dev/null; } || true
        pd_log_session_start_diagnostic "${BASH_LINENO[0]:-0}" "$rc" "EXIT non-zero"
    fi

    # CRITICAL: exit 0 regardless of upstream rc. AC1/FR1-3 depend on this.
    exit 0
}
```

**Edge case considered:** main path emits partial JSON before stdout closes mid-write (FR2 scenario). `safe_emit_hook_json` returns 0 (via `|| true`); main returns 0; EXIT trap sees rc=0; emits nothing extra. CC reads partial JSON which it ignores (per CC convention, exit-0-with-malformed-stdout → CC ignores stdout). FR4 jq assertion runs only on a clean test environment where stdout is healthy, so no test-time conflict.

#### C4. `session-start.sh` modifications

```bash
# Lines 1-15: REPLACE banner comment block
# New banner content:
#   SessionStart hook for pd. Emits hookSpecificOutput JSON for context injection.
#
#   Broken-pipe handling: see docs/dev_guides/hook-development.md (section
#   "Broken-pipe handling for hooks emitting structured output"). DO NOT
#   remove `trap '' PIPE` below — it is co-load-bearing with safe_emit_hook_json.
#
# Line 4: keep `set -euo pipefail` (unchanged)
# Line 10: keep `trap '' PIPE` (RETAINED — TD8)
# Line 13: replace `install_err_trap` with:
#   source "$SCRIPT_DIR/lib/session-start-helpers.sh"
#   install_session_start_traps
# Line 807: replace `cat <<EOF ... EOF` with safe_emit_hook_json call (see below)
# Line 922: replace `cat <<EOF ... EOF` with safe_emit_hook_json call (see below)
```

JSON construction at the call sites uses `jq -nc --arg` when available, `printf`+`escape_json` fallback otherwise (rev 2 — addresses suggestion #13):

```bash
local payload
if command -v jq >/dev/null 2>&1; then
    payload=$(jq -nc --arg event "SessionStart" --arg ctx "$escaped_context" \
        '{hookSpecificOutput: {hookEventName: $event, additionalContext: $ctx}}')
else
    # Fallback: build JSON manually using existing escape_json helper
    payload=$(printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}' \
        "$escaped_context")
fi
safe_emit_hook_json "$payload"
```

The fallback assumes `$escaped_context` is already JSON-string-safe (existing `escape_json` helper guarantees this). If `escape_json` produces output that differs from `jq --arg`'s encoding (R1), tests catch it.

#### C5. `docs/dev_guides/hook-development.md` update

Add (or extend existing) section: "Broken-pipe handling for hooks emitting structured output". Required content (per AC6c — must contain literal strings `EPIPE`, `set -e`, and `session-start.sh`):

- Why `set -e` + `cat <<EOF` is unsafe (RCA reproduction matrix).
- Why `trap '' PIPE` is necessary but not sufficient (it converts SIGPIPE-141 into EPIPE-write-error-rc-1; `set -e` then propagates the rc unless `|| true` is also present).
- The canonical pattern: `safe_emit_hook_json` + `install_session_start_traps`, both in `lib/session-start-helpers.sh`.
- Test recipes (closed-stdout pre-write, mid-write, AND-stderr).
- Reference to RCA `docs/rca/20260508-110928-sessionstart-skills.md` and feature 107.

#### C6. New test artifacts

All under `plugins/pd/hooks/tests/`:

- `repro-broken-pipe.sh` — driver running 4 scenarios (happy, pre-write, mid-write, AND-stderr) and asserting exit 0. Used by AC1.
- `bench-session-start.sh` — 11-run timing harness (TD7 detail below). Used by AC8.
- `bench-results.txt` — committed alongside (TD7).
- `probe-a1-exit0-under-broken-pipe.sh` — A1 probe (content inlined below). Used by AC10.
- `probe-printf-sigpipe.sh` — printf-vs-trap exit-code matrix probe (content inlined below; rev 2 — empirically grounds TD8). Used by AC10's "Verified Bash Behavior" claim.

**Inlined probe content (rev 3 — addresses suggestion #5):** copy these verbatim during implement to satisfy AC10.

`probe-a1-exit0-under-broken-pipe.sh`:
```bash
#!/usr/bin/env bash
# Verifies: bash with set -e + trap '' PIPE + EPIPE-safe write exits 0
# under closed-stdout. Run: bash probe-a1-exit0-under-broken-pipe.sh
set -euo pipefail
trap '' PIPE
{ printf '{}\n' 2>/dev/null; } || true
exit 0
# Invocation under closed-stdout (asserts exit 0):
#   bash probe-a1-exit0-under-broken-pipe.sh | dd of=/dev/null bs=1 count=0 ; echo "rc=$?"
```

`probe-printf-sigpipe.sh`:
```bash
#!/usr/bin/env bash
# Verifies the Verified Bash Behavior matrix in design.md.
# Each subshell writes >64KB to ensure pipe-close is detected.
report() { echo "=== $1 ==="; }

report "no trap, no '|| true'"
( for i in $(seq 1 1500); do printf '%0100d\n' $i 2>/dev/null || exit 1; done; echo OK >&2 ) | head -c 1 >/dev/null
echo "rc=$?"

report "trap '' PIPE, no '|| true'"
( trap '' PIPE; for i in $(seq 1 1500); do printf '%0100d\n' $i 2>/dev/null || exit 1; done; echo OK >&2 ) | head -c 1 >/dev/null
echo "rc=$?"

report "set -e, no trap, with '|| true'"
( set -e; for i in $(seq 1 1500); do { printf '%0100d\n' $i 2>/dev/null; } || true; done; echo OK >&2 ) | head -c 1 >/dev/null
echo "rc=$?"

report "set -e + trap '' PIPE + '|| true' (the safe pattern)"
( set -e; trap '' PIPE; for i in $(seq 1 1500); do { printf '%0100d\n' $i 2>/dev/null; } || true; done; echo OK >&2 ) | head -c 1 >/dev/null
echo "rc=$?"
```
- `fixtures/unsafe-write-fixture.sh` — intentionally-unsafe `cat <<EOF ... EOF` (FR8 positive control). Used by AC11.
- `test-session-start-broken-pipe.sh` — hosts T1–T8 (FR7 + new T6/T7/T8). Invoked by `test-hooks.sh`.
- `check-no-unsafe-writes.sh` — FR8 static guard (TD9 — descoped to a tighter, regex-checkable invariant).

#### C7. `bench-session-start.sh` baseline pinning (resolves spec suggestion #3; rev 2 — addresses blocker #4)

The benchmark uses `git worktree add` (NOT plain `git checkout`) to avoid destroying uncommitted work. CLAUDE.md establishes `.pd-worktrees/` as the worktree root; we reuse:

```bash
# bench-session-start.sh (sketch)
set -euo pipefail
[[ -z "$(git status --porcelain)" ]] || { echo "Working tree dirty; commit or stash"; exit 2; }

baseline_sha=$(git merge-base HEAD develop)
worktree_dir=".pd-worktrees/bench-${baseline_sha:0:8}"
git worktree add "$worktree_dir" "$baseline_sha"

baseline_ms=$(measure_median "$worktree_dir/plugins/pd/hooks/session-start.sh")
patched_ms=$(measure_median "plugins/pd/hooks/session-start.sh")

git worktree remove "$worktree_dir"

cat > plugins/pd/hooks/tests/bench-results.txt <<EOF
baseline_sha=$baseline_sha
baseline_median_ms=$baseline_ms
patched_median_ms=$patched_ms
delta_ms=$(( patched_ms - baseline_ms ))
threshold_ms=50
EOF

(( patched_ms - baseline_ms <= 50 ))
```

Where `measure_median` runs the hook 11 times under `time -p`, drops fastest+slowest, computes median of remaining 9 in milliseconds. Bash 3.2 compatible (no associative arrays).

The pre-flight `git status --porcelain` check fails fast if working tree is dirty, defensive even with worktree (NFR4).

### Technical Decisions

#### TD1. Use `printf` not `cat <<EOF` — but co-load-bearing with `trap '' PIPE`

Decision: replace both `cat <<EOF` blocks with `safe_emit_hook_json` (printf-based). **Both** the printf migration **AND** the existing `trap '' PIPE` are required.

Rationale (rev 2 — addresses blocker #1):
- Verified empirically (Verified Bash Behavior table): `set -e` + no trap + `|| true` → SIGPIPE kills bash before `|| true` runs. The trap is essential.
- `printf` removes the child-process SIGPIPE inheritance footgun (relevant for `cat`).
- Combined with `|| true 2>/dev/null`, this gives EPIPE-safe write that survives both happy and closed-stdout paths.
- The banner comment (C4) explicitly warns against removing `trap '' PIPE`.

Rejected alternative: keep `cat <<EOF` and add `|| true 2>/dev/null` around it. Works (per research finding 2) but leaves child-process SIGPIPE inheritance as a latent issue if SIGPIPE disposition flips upstream.

#### TD2. EXIT trap as primary fallback; ERR trap for diagnostics only

(unchanged from rev 1)

#### TD3. Bash-side log rotation

(unchanged)

#### TD4. Don't migrate `install_err_trap` (SG1)

(unchanged)

#### TD5. UTC-only ISO-8601 timestamp; one regex source

(unchanged)

#### TD6. Test isolation via `PD_SESSION_START_LOG` env var

(unchanged)

#### TD7. NFR2 benchmark uses `git worktree add` for baseline (rev 2 — blocker #4)

Decision: `bench-session-start.sh` uses `git worktree add` (not `git checkout`) under `.pd-worktrees/bench-<sha>/`, with a pre-flight `git status --porcelain` check. The merge-base SHA is committed in `bench-results.txt`.

Rationale: plain `git checkout` of a SHA puts the working tree in detached HEAD and overwrites uncommitted files. CLAUDE.md establishes `.pd-worktrees/` as the worktree convention — we reuse it. The pre-flight check defends against dirty trees even when worktree is used (paranoia is cheap).

#### TD8. Retain `trap '' PIPE` in session-start.sh (rev 2 — blocker #1)

Decision: keep `trap '' PIPE` at session-start.sh:10, and document explicitly in the banner comment that it is co-load-bearing with `safe_emit_hook_json`.

Rationale (per Verified Bash Behavior matrix):
- Without `trap '' PIPE`: bash printf builtin's write to closed stdout receives SIGPIPE-141, killing the bash process before `|| true` can run. Hook exits 141.
- With `trap '' PIPE`: SIGPIPE is ignored; printf's write returns EPIPE; printf exits 1; `|| true` swallows; bash continues.
- Without `|| true`: under `set -e`, printf's exit 1 propagates as the script's exit code.

Both are required. The banner comment in C4 warns future contributors against removing either.

#### TD9. FR8 static guard descoped to tighter invariant (rev 2 — warning #7; rev 3 — warnings #1 and #2)

Decision: `check-no-unsafe-writes.sh` enforces a single tight, BSD-portable invariant. The script accepts a **target path argument** so the same code path can be exercised by both production check and AC11's positive control.

```bash
#!/usr/bin/env bash
# Usage: check-no-unsafe-writes.sh [target_path]
# Default target: plugins/pd/hooks/session-start.sh
#
# Forbids line-leading `cat <<` heredoc (legal cat-heredocs in pd are
# always inside `$(...)` substitutions, which are not line-leading).
#
# CRITICAL: Use POSIX [[:space:]] not `\s` — BSD grep on macOS does NOT
# support `\s` in ERE; using `\s` would silently match nothing.

set -euo pipefail
target="${1:-plugins/pd/hooks/session-start.sh}"
violations=$(grep -nE '^[[:space:]]*cat[[:space:]]*<<' "$target" || true)
if [[ -n "$violations" ]]; then
    echo "FR8 violation in $target:" >&2
    echo "$violations" >&2
    exit 1
fi
exit 0
```

Negative control: all current `cat` calls in session-start.sh are inside `$(...)` substitutions, so they are NOT line-leading (`=$(cat ...)` is prefixed with `=$(`). Verified by manual sweep during design; the test will run this guard against the post-fix file and assert zero output.

Positive control (AC11): `tests/fixtures/unsafe-write-fixture.sh` contains a line-leading `cat <<EOF`. The test invokes `check-no-unsafe-writes.sh plugins/pd/hooks/tests/fixtures/unsafe-write-fixture.sh` — the SAME code path as production — and asserts non-zero exit + violation message on stderr.

This drops `echo` and `printf` from FR8's scope (they're heavily used inside `$(...)` and have low SIGPIPE risk in command substitution). The narrower invariant is grep-checkable and has zero false positives on current code.

**Portability check:** verified during design (rev 3) that `[[:space:]]` works under both GNU grep (Linux) and BSD grep (macOS default). `\s` was rejected because BSD ERE treats it as a literal `s`.

### Risks

#### R1. (medium) Migrating from `cat <<EOF` may break existing escape behavior

`escape_json` produces a JSON-string-safe encoding for the heredoc; `jq -nc --arg` re-encodes. May produce subtly different output for edge characters (newlines, backslashes, unicode).

**Mitigation:** Before merge, compare jq output vs current heredoc output on a representative `additionalContext` containing newlines, quotes, backslashes, unicode. Add T6 — happy path with multiline `additionalContext` containing `"`, `\`, `\n`, unicode — assert `jq -e '.hookSpecificOutput.additionalContext | contains("\n")'` and assert byte-equality against a frozen reference fixture.

#### R2. (low) `mkdir -p` race during first-run

(unchanged — `mkdir -p` is idempotent.)

#### R3. (low) macOS vs Linux `stat` flags

(unchanged — fallback chain handles both.)

#### R4. (low) `BASH_LINENO[0]` unreliable in some bash 3.2 trap contexts

(unchanged — `${BASH_LINENO[0]:-0}` defaults to 0.)

#### R5. (medium) `jq` unavailable on user's system

(unchanged — fallback shown in C4.)

#### R6. (eliminated by rev 2) — formerly: EXIT trap could mask bugs

The defensive `set +e` at the start of `__pd_exit_handler` (rev 2) removes the footgun. R6 retired.

#### R7. (rev 2 — design-reviewer warning #8) `set -e` propagation through `$(...)` in bash 3.2

`session-start.sh` calls `$(build_context)`, `$(build_memory_context)`, `$(run_doctor_autofix)` etc. (lines 838–860). bash 3.2 has known edge cases where errors inside `$(...)` may not propagate to the parent shell's ERR trap.

**Mitigation (rev 3 — committed strategy):** The EXIT trap is the sole defense; we do NOT add explicit `|| x=""` guards at the call sites. Rationale:
- The EXIT trap fires regardless of how main exits (success or failure, ERR-trap-fired or not).
- An empty result from `$(build_context)` causes `additionalContext` to be empty — which FR4 (rev 3 spec) explicitly permits.
- Adding guards at 6+ call sites is a wider change than fixing the symptom and risks introducing the very `|| true` over-suppression patterns we're trying to avoid in lib code review.

**T8 verification:** the test injects a controlled failure (env var `PD_FORCE_BUILD_CONTEXT_FAIL=1` honored at the top of `build_context` to `return 1`). The test asserts `bash session-start.sh` exits 0 in this case. If T8 reveals that the EXIT trap is bypassed, we re-enter design (per spec SG fallback procedures); the design does NOT pre-commit to a different mitigation that may not be needed.

#### R8. (NEW rev 2 — design-reviewer warning #10) Concurrent rotation race

Two parallel CC sessions rotating simultaneously: both compute size > 1MB, both create distinct mktemp files, both `mv`, second `mv` overwrites first.

**Mitigation:** Acceptable. Last-writer-wins; resulting file is still valid TSV (each rotated tail is itself valid TSV). Worst case: a few diagnostic lines lost. No data integrity issue. Not worth the complexity of `flock` (and `flock` is not universally available on macOS — would violate NFR1's spirit).

### Reason Vocabulary (rev 2 — warning #6)

The diagnostic log uses a closed set of `<reason>` strings. Tests assert against these:

| Reason string | Emitted by | Trigger |
|---|---|---|
| `ERR trap fired` | `__pd_err_handler` | Any `set -e` propagation in main path |
| `EXIT non-zero` | `__pd_exit_handler` | EXIT trap fires with rc != 0 |
| `mkdir failed` | `pd_log_diagnostic` (would-be log entry, can't actually log itself) | First-run `mkdir -p` failed; this entry is suppressed (recovery-of-recovery) |

Future expansion: each new failure mode gets a new reason string added here.

The spec FR5 example (`EPIPE on cat`) is now obsolete — under the new design, `cat <<EOF` is removed, so that reason will never be emitted. Spec FR5 example is updated in lockstep (see "Spec Amendment" below).

### Spec Amendment Notes (rev 2)

The design phase identified that the spec's FR5 example reason string `EPIPE on cat` no longer matches the post-fix code (since `cat <<EOF` is replaced). This is a stale example; spec FR5's regex is what matters for AC5a, and the regex still validates `ERR trap fired` and `EXIT non-zero` (both have only `[a-z A-Z]+`-class characters in the trailing field). No spec re-review is required because the FR5 schema regex is unchanged; only the example needs an inline annotation. Recommendation: when the implement phase updates the spec, replace the example with one that matches the actual reason vocabulary. (This is a documentation tidy-up; not a scope change.)

### Out of Scope (per spec)

- Other 8 hooks using `cat <<EOF` (SG2). They could adopt `safe_emit_hook_json` later.
- Refactoring `escape_json` or `build_context`.
- Rewriting `session-start.sh` to use `emit_hook_json` from common.sh.

## Interfaces

### `safe_emit_hook_json(json: string) → void`

- **Location:** `plugins/pd/hooks/lib/session-start-helpers.sh`
- **Inputs:** `$1` — complete JSON document as a single string.
- **Preconditions:** caller has `trap '' PIPE` set (TD8).
- **Outputs:** Writes JSON + `\n` to stdout.
- **Side effects:** None on failure.
- **Exit code:** Always 0 (function-internal).
- **Bash 3.2 compat:** Yes.

### `pd_log_diagnostic(log_env_var_name, default_log_path, script_basename, line_no, exit_code, reason) → void`

- **Location:** `plugins/pd/hooks/lib/session-start-helpers.sh`
- **Inputs:** as named.
- **Outputs:** Appends one TSV line to `${$log_env_var_name:-$default_log_path}`.
- **Side effects:** Creates log directory if missing; rotates file if > 1 MB.
- **Exit code:** Always 0.
- **Bash 3.2 compat:** Yes (uses `eval` for indirect env var expansion; `stat` flag fallback).

### `pd_log_session_start_diagnostic(line_no, exit_code, reason) → void`

- **Location:** `plugins/pd/hooks/lib/session-start-helpers.sh`
- **Inputs:** subset of `pd_log_diagnostic`'s args.
- **Effect:** wraps `pd_log_diagnostic` with `PD_SESSION_START_LOG` and the default path.

### `install_session_start_traps() → void`

- **Location:** `plugins/pd/hooks/lib/session-start-helpers.sh`
- **Effects:** Installs ERR + EXIT traps. Both call `set +e` defensively.

### Log line schema (FR5, normative)

(unchanged regex)

```
^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\t[a-z0-9_.-]+\.sh:[0-9]+\t[0-9]+\t.+$
```

### Test command vocabulary

(unchanged from rev 1)

## Verification Mapping

| Spec Item | Component | Test |
|---|---|---|
| FR1 (closed-stdout pre-write → exit 0) | C1, C3, TD8 | T1 |
| FR2 (closed-stdout mid-write → exit 0) | C1, C3, TD8 | T2 |
| FR3 (closed-stdout AND-stderr → exit 0) | C1, C3, TD8 | T3 |
| FR4 (happy-path JSON shape) | C1, C4 | T4 + AC3 |
| FR5 (log line schema) | C2 | T5 |
| FR5b (rotation) | C2 (TD3) | AC5b 1000-loop test |
| FR6 (banner + SoT doc) | C4 banner, C5 doc | AC6a/b/c |
| FR7 (test harness) | C6 | self |
| FR8 (static guard) | TD9 `check-no-unsafe-writes.sh` | AC11 + negative control |
| NFR1 (no new deps) | All — bash builtins, jq, printf only | implicit |
| NFR2 (latency budget) | C7 with `git worktree` (TD7) | AC8 |
| NFR3 (bash 3.2) | All | implicit |
| NFR4 (no stale state) | `mktemp` cleanup, `git worktree remove` | implicit |
| **set -e in $() (R7)** | `__pd_exit_handler` rc=$? defensive | T8 |
| **JSON encoding parity (R1)** | C4 fallback | T6 |

### Scope Guards Compliance (rev 2 — suggestion #12)

- **SG1:** `install_err_trap` is **not modified** (TD4). New trap setup is `install_session_start_traps` in a new file `lib/session-start-helpers.sh`. `install_err_trap` remains in `lib/common.sh` for any other hook still using it. ✓
- **SG2:** Only `session-start.sh` is modified among hooks. The new `lib/session-start-helpers.sh` is a new file (not `lib/common.sh`), strictly required to fix `session-start.sh`. No other hook is modified. The new helpers are NOT adopted by other hooks in this PR (their adoption would be follow-up work). ✓

## Resolved Spec Suggestions

1. **FR7 T5 vs AC5a regex** → TD5: single regex constant. ✓
2. **EPIPE-safe wrapper definition** → C1's `safe_emit_hook_json`. ✓
3. **AC8 baseline pinning** → TD7: `git worktree add` against merge-base; SHA recorded in `bench-results.txt`. ✓
4. **AC10 tense** → spec already disambiguates ("verified during specify... committed during implement"); design treats them as separate steps. ✓

## Open Questions for Plan/Implement

- **OQ-bench-baseline.** If `develop` is fast-moving, merge-base may be stale by merge time. Suggested: bench runs at PR-open against merge-base; if NFR2 fails, user re-runs against current develop HEAD before merge.
- **OQ-jq-fallback.** Resolved in design (C4 fallback shown).
- **OQ-fixture-naming.** `fixtures/` subdir vs flat `tests/` files — verify the existing test harness supports `fixtures/` discovery; if not, flatten to `tests/fixture-unsafe-write.sh`. Implement-phase verification.
- **OQ-T8-mechanism.** What's the cleanest way to inject controlled failure into `build_context` for T8? Suggested: env var `PD_FORCE_BUILD_CONTEXT_FAIL` checked at the top of `build_context`; tests set it. Implement-phase mechanic.
