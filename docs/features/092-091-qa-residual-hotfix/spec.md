# Spec: Feature 092 — 091 QA Residual Hotfix

## Status
- Created: 2026-04-20
- Phase: specify
- Mode: standard
- Source PRD: `docs/features/092-091-qa-residual-hotfix/prd.md`

## Scope

9 surgical fixes for feature 091 post-release adversarial QA findings (#00193–#00201). Direct-orchestrator implementation following Feature 090 surgical template. Target: v4.16.1 patch release.

## Functional Requirements

### FR-1: #00193 — Clamp `scan_limit < 0` to 0

**Change:** `plugins/pd/hooks/lib/semantic_memory/database.py:scan_decay_candidates` — add `scan_limit = max(0, scan_limit)` at entry; correct docstring.

**Rationale (pre-mortem + antifragility):** ValueError escapes `decay_confidence`'s `except sqlite3.Error` block silently (no diagnostic trace). Clamping preserves "always returns generator" contract, matches documented behavior (`scan_limit <= 0 yields zero rows`), eliminates propagation-test coverage gap.

**Docstring correction:**
- Before: `"scan_limit <= 0 yields zero rows (SQLite LIMIT semantics) with no exception."`
- After: `"scan_limit <= 0 yields zero rows (negative values clamped to 0 before SQL binding to avoid SQLite LIMIT -1 = unlimited semantics)."`

### FR-2: #00194 — Harden AC-22b/c trap + mktemp (explicit guards, NOT set -u)

**Changes in `plugins/pd/hooks/tests/test-hooks.sh`** (both AC-22b at line 2980 and AC-22c at line 3041):

Before:
```bash
PKG_TMPDIR=$(mktemp -d)
trap "rm -rf \"$PKG_TMPDIR\"" EXIT
mkdir -p "$PKG_TMPDIR/semantic_memory"
```

After:
```bash
PKG_TMPDIR=$(mktemp -d) || { log_fail "mktemp -d failed"; exit 1; }
[ -n "$PKG_TMPDIR" ] || { log_fail "mktemp -d returned empty"; exit 1; }
[ -d "$PKG_TMPDIR" ] || { log_fail "mktemp -d target not a directory"; exit 1; }
trap 'rm -rf -- "$PKG_TMPDIR"' EXIT  # single-quoted: expansion deferred to fire-time
mkdir -p "$PKG_TMPDIR/semantic_memory"
```

**Do NOT add `set -u`** — bash 3.2 portability risk (pre-mortem concern; same class as the declare -A issue from 091).

### FR-3: #00195 — AC-4d invariant uses repo-root-absolute git call

**Change in `test-hooks.sh`** (both call sites):

Before:
```bash
git_status=$(cd "$(dirname "${HOOKS_DIR}")" && git status --porcelain "plugins/pd/hooks/lib/semantic_memory/maintenance.py" 2>/dev/null || true)
```

After:
```bash
git_status=$(git -C "$(git rev-parse --show-toplevel)" status --porcelain plugins/pd/hooks/lib/semantic_memory/maintenance.py 2>/dev/null || true)
```

### FR-4: #00196 — `cp -R -P` (no-dereference)

**Change in `test-hooks.sh`** (both AC-22b and AC-22c):

Before: `cp -R "${HOOKS_DIR}/lib/semantic_memory/." "$PKG_TMPDIR/semantic_memory/"`
After: `cp -R -P "${HOOKS_DIR}/lib/semantic_memory/." "$PKG_TMPDIR/semantic_memory/"`

`-P` is portable across BSD (macOS) and GNU cp with identical semantics.

### FR-5: #00197 — `not_null_cutoff` format validation in `scan_decay_candidates`

**Rationale update (spec-reviewer iteration 1 flag):** Raising `ValueError` at method entry creates the same propagation-gap hazard that PRD rejected for FR-1 — ValueError escapes `decay_confidence`'s `except sqlite3.Error` block silently. For consistency with FR-1's clamp philosophy, FR-5 uses **log-and-skip** instead of raise.

**Change:** add regex validation at method entry. On mismatch, emit stderr warning and return immediately (empty generator) — NO exception:

```python
# Module-level compile:
_ISO8601_Z_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')

def scan_decay_candidates(self, *, not_null_cutoff: str, scan_limit: int) -> Iterator[sqlite3.Row]:
    if not _ISO8601_Z_PATTERN.match(not_null_cutoff):
        sys.stderr.write(
            f"[scan_decay_candidates] not_null_cutoff format violation: "
            f"expected YYYY-MM-DDTHH:MM:SSZ, got {not_null_cutoff!r}; "
            f"returning empty result\n"
        )
        return  # empty generator (no yield)
    scan_limit = max(0, scan_limit)  # FR-1 clamp
    # ... existing SQL body
```

**Contract:** method silently returns empty on invalid cutoff; operator-visible diagnostic via stderr (absorbed by session-start `2>/dev/null` but visible on direct invocation or in test capsys). Production caller (`_select_candidates` via `_iso_utc`) always produces Z-suffix so never triggers the warning path.

**Regex-vs-production-helper pin:** new test `test_scan_decay_candidates_matches_iso_utc_output` verifies `_config_utils._iso_utc(now)` output passes the regex — prevents silent production breaker if `_iso_utc` format ever changes.

**Test coverage for the malformed path:** `test_scan_decay_candidates_rejects_malformed_cutoff` passes `"+00:00"`, `""`, `"not-iso"` and asserts (a) empty result list, (b) stderr contains `"format violation"`, (c) NO exception raised.

### FR-6: #00198 — Correct stale spec clamp values in feature 091 artifacts

**Changes:**
- `docs/features/091-082-qa-residual-cleanup/spec.md:49` — change `[1000, 500000]` → `[1000, 10_000_000]` (in FR-1 row 14 closure marker for #00107)
- `docs/features/091-082-qa-residual-cleanup/spec.md:139` — change `[1000, 500000]` → `[1000, 10_000_000]` (in FR-4 body "Current production callers..." paragraph)

Both match actual clamp at `plugins/pd/hooks/lib/semantic_memory/maintenance.py:462`: `clamp=(1000, 10_000_000)`.

Note: Does NOT modify `docs/backlog.md` #00107 marker (already correct at `[1000, 10_000_000]`).

### FR-7: #00199 — Extract `_run_maintenance_fault_test` helper

**Change in `test-hooks.sh`**: extract shared scaffold from `test_memory_decay_syntax_error_tolerated` (~60 lines) and `test_memory_decay_import_error_tolerated` (~64 lines) into a helper function. The ~55 lines of identical scaffold (venv guard, subshell wrapper, mktemp guards, cp -R -P, `__init__.py` check, clean-import positive control, negative control, positive contract, subshell exit check, AC-4d git-status invariant) are centralized.

**Helper signature + body pseudocode** (pinned to prevent design-phase drift on inject-mode branching):
```bash
# Usage: _run_maintenance_fault_test <test_label> <t7_tag> <inject_mode> <inject_payload>
# inject_mode: "append" (AC-22b/SyntaxError) | "prepend" (AC-22c/ImportError)
# inject_payload: the text to inject into the temp maintenance.py copy
_run_maintenance_fault_test() {
    local test_label="$1"
    local t7_tag="$2"
    local inject_mode="$3"
    local inject_payload="$4"

    if [[ ! -x "$PLUGIN_VENV_PYTHON" ]]; then
        log_pass  # SKIP: venv missing
        return
    fi

    (
        set +e  # Must NOT use set -e: the negative-control Python invocation
                # below deliberately returns non-zero, and `set -e` would
                # terminate the subshell before raw_exit=$? can capture it.
                # Same rationale as pre-092 style (test-hooks.sh:2978, 3039).
        PKG_TMPDIR=$(mktemp -d) || { log_fail "mktemp -d failed"; exit 1; }
        [ -n "$PKG_TMPDIR" ] || { log_fail "mktemp -d returned empty"; exit 1; }
        [ -d "$PKG_TMPDIR" ] || { log_fail "mktemp -d target not a directory"; exit 1; }
        trap 'rm -rf -- "$PKG_TMPDIR"' EXIT

        mkdir -p "$PKG_TMPDIR/semantic_memory" \
            || { echo "FAIL: mkdir -p failed"; exit 1; }
        cp -R -P "${HOOKS_DIR}/lib/semantic_memory/." "$PKG_TMPDIR/semantic_memory/" \
            || { echo "FAIL: cp -R -P failed"; exit 1; }

        [ -f "$PKG_TMPDIR/semantic_memory/__init__.py" ] \
            || { echo "FAIL: __init__.py missing"; exit 1; }

        # Positive control: clean copy must import.
        PYTHONPATH="$PKG_TMPDIR" "$PLUGIN_VENV_PYTHON" \
            -c 'import semantic_memory.maintenance' 2>/dev/null \
            || { echo "FAIL: clean copy does not import"; exit 1; }

        # Inject fault per mode:
        case "$inject_mode" in
            append)
                printf '%s' "$inject_payload" >> "$PKG_TMPDIR/semantic_memory/maintenance.py" \
                    || { echo "FAIL: append failed"; exit 1; }
                ;;
            prepend)
                {
                    echo "$inject_payload"
                    cat "$PKG_TMPDIR/semantic_memory/maintenance.py"
                } > "$PKG_TMPDIR/semantic_memory/maintenance.py.new" \
                    || { echo "FAIL: prepend failed"; exit 1; }
                mv "$PKG_TMPDIR/semantic_memory/maintenance.py.new" \
                   "$PKG_TMPDIR/semantic_memory/maintenance.py" \
                    || { echo "FAIL: mv failed"; exit 1; }
                ;;
            *)
                echo "FAIL: unknown inject_mode=$inject_mode"; exit 1
                ;;
        esac

        # Negative control: WITHOUT shell guard, raw invocation MUST fail.
        # (set +e above lets us capture the non-zero exit into raw_exit.)
        PYTHONPATH="$PKG_TMPDIR" "$PLUGIN_VENV_PYTHON" \
            -m semantic_memory.maintenance --decay --project-root . >/dev/null 2>&1
        raw_exit=$?
        [ "$raw_exit" -ne 0 ] || { echo "FAIL: ${test_label} fault did not trigger"; exit 1; }

        # Positive contract: WITH guard, exit 0.
        PYTHONPATH="$PKG_TMPDIR" "$PLUGIN_VENV_PYTHON" \
            -m semantic_memory.maintenance --decay --project-root . 2>/dev/null || true

        # FR-9: explicit PASS marker (inside subshell — raw_exit in scope):
        echo "${test_label} PASS: shell guard tolerated Python failure (raw_exit=$raw_exit)"
    )
    local subshell_exit=$?
    if [ "$subshell_exit" -eq 0 ]; then
        log_pass
    else
        log_fail "${test_label} subshell reported failure (exit $subshell_exit)"
    fi

    # AC-4d invariant: production file untouched (repo-root-absolute git):
    local git_status
    git_status=$(git -C "$(git rev-parse --show-toplevel)" status --porcelain \
        plugins/pd/hooks/lib/semantic_memory/maintenance.py 2>/dev/null || true)
    if [ -n "$git_status" ]; then
        log_test "AC-4d invariant: production maintenance.py untouched (${t7_tag})"
        log_fail "production maintenance.py mutated: $git_status"
    fi
}

test_memory_decay_syntax_error_tolerated() {
    log_test "session-start guard tolerates SyntaxError in maintenance.py (AC-22b, FR-3)"
    _run_maintenance_fault_test "AC-22b" "T7a" "append" $'\ndef broken(:\n'
}

test_memory_decay_import_error_tolerated() {
    log_test "session-start guard tolerates ImportError in maintenance.py (AC-22c, FR-3)"
    _run_maintenance_fault_test "AC-22c" "T7b" "prepend" "import no_such_module_really_does_not_exist"
}
```

**Safety invariant:** helper uses `set +e` (NOT `-e`, because the negative-control Python invocation deliberately returns non-zero and `set -e` would terminate the subshell before `raw_exit=$?` captures it — matches pre-092 pattern at `test-hooks.sh:2978, 3039`). Each setup step that could fail (mktemp, mkdir, cp, append/prepend, clean-import, `__init__.py` existence) has an explicit `|| { echo "FAIL: ..."; exit 1; }` override preserving diagnostic output. Two DIFFERENT test function call sites ensure helper bugs fail both tests loudly, not silently.

### FR-8: #00200 — `batch_demote` empty `now_iso` validation

**Change in `database.py:batch_demote`** — add validation AFTER the existing `if not ids: return 0` short-circuit (preserves empty-ids contract) but BEFORE the `new_confidence` validation:

```python
def batch_demote(self, ids, new_confidence, now_iso):
    if not ids:
        return 0  # UNCHANGED — preserves empty-ids short-circuit
    if not now_iso:
        raise ValueError("now_iso must be non-empty ISO-8601 timestamp")
    # ... existing new_confidence validation + SQL body
```

**Rationale (spec-reviewer iteration 1 flag):** Placing validation after `if not ids` preserves backward-compat contract: `batch_demote([], 'medium', '')` continues to return 0 silently (empty-ids trumps empty-now_iso). Only `batch_demote([id1, ...], 'medium', '')` raises ValueError.

Current production caller (`decay_confidence` via `_iso_utc`) provably cannot produce empty. Safeguards future direct callers without disturbing empty-ids callers.

### FR-9: #00201 — Explicit "AC-22b PASS" / "AC-22c PASS" markers

**Change in helper from FR-7** — emit an explicit marker INSIDE the subshell (where `$raw_exit` is in scope), BEFORE the subshell exits. After the subshell completes, helper calls `log_pass`. Outer scope emits a label-only summary if desired (no `$raw_exit` available there):

```bash
# Inside the subshell (where raw_exit is live):
echo "${test_label} PASS: shell guard tolerated Python failure (raw_exit=$raw_exit)"
# Then subshell exits 0.
# After subshell returns in outer scope, helper calls:
log_pass
```

This ensures `grep -qE "AC-22b PASS"` / `grep -qE "AC-22c PASS"` match, AND `$raw_exit` is in scope at the echo site. Lock-in on the "AC-Xx PASS: ..." prefix is acceptable — this IS the DoD contract.

## Non-Functional Requirements

### NFR-1: LOC budget
- Net production LOC: ≤ +50 (FR-1 clamp: 1 line; FR-5 regex: ~8 lines; FR-8 validation: 2 lines; doc fixes: ~4 lines)
- Net test LOC: NEGATIVE ≤ -30 (FR-7 helper extraction removes ~110 duplicated lines, adds ~70-line helper + ~3-line thin call sites each = ~-33 net)

### NFR-2: Zero regressions
- `test_maintenance.py` + `test_database.py` + `test-hooks.sh` all pass.
- Existing production caller path (`decay_confidence` → `_select_candidates` → `scan_decay_candidates`) unchanged behaviorally.

### NFR-3: `./validate.sh` passes; `pd:doctor` passes.

### NFR-4: Reviewer iteration target (aspirational, not a gate): ≤ 2 iterations per phase.

### NFR-5: Structural exit (per PRD SC-1)
Post-merge adversarial QA by 4 parallel reviewers (security, code-quality, test-deepener Phase A, implementation-reviewer) must surface ≤ 3 MED findings and zero HIGH against the merged 092 diff.

## Acceptance Criteria

- **AC-1 (#00193 clamp):** `grep -E "scan_limit = max\(0, scan_limit\)" plugins/pd/hooks/lib/semantic_memory/database.py` returns 1 match; `plugins/pd/.venv/bin/python -c "from semantic_memory.database import MemoryDatabase; db=MemoryDatabase(':memory:'); print(list(db.scan_decay_candidates(not_null_cutoff='2026-04-20T00:00:00Z', scan_limit=-1)))"` prints `[]`. Pytest: new `test_scan_decay_candidates_clamps_negative_scan_limit_to_zero`.
- **AC-2 (#00193 docstring):** docstring no longer claims `scan_limit <= 0 yields zero rows (SQLite LIMIT semantics) with no exception`; new text references the clamp.
- **AC-3 (#00194 trap):** `grep -cE "trap 'rm -rf --" plugins/pd/hooks/tests/test-hooks.sh` returns ≥ 1 (1 if FR-7 helper consolidates; 2 if inline in both tests). ADDITIONALLY: `grep -cE 'trap "rm -rf' plugins/pd/hooks/tests/test-hooks.sh` returns 0 (double-quoted trap body fully eliminated — this is the meaningful invariant).
- **AC-4 (#00194 mktemp guards):** three conjunctive greps pin all three guards from FR-2:
  - `grep -cE 'PKG_TMPDIR=\$\(mktemp -d\) \|\| \{ log_fail' plugins/pd/hooks/tests/test-hooks.sh` ≥ 1 (mktemp failure guard)
  - `grep -cE '\[ -n "\$PKG_TMPDIR" \]' plugins/pd/hooks/tests/test-hooks.sh` ≥ 1 (empty guard)
  - `grep -cE '\[ -d "\$PKG_TMPDIR" \]' plugins/pd/hooks/tests/test-hooks.sh` ≥ 1 (directory guard)
- **AC-5 (#00195 AC-4d fix):** `grep -cE 'git -C "\$\(git rev-parse --show-toplevel\)"' test-hooks.sh` ≥ 1. New test: manually dirty `plugins/pd/hooks/lib/semantic_memory/maintenance.py`, run AC-22b block, verify AC-4d invariant actually FAILS (fire test).
- **AC-6 (#00196 `cp -R -P`):** `grep -cE 'cp -R -P' test-hooks.sh` = 1 (in helper after FR-7) or = 2 (pre-helper). `grep -cE 'cp -R "' test-hooks.sh` = 0 (no un-flagged `cp -R` in the AC-22b/c test region).
- **AC-7 (#00197 regex validation):** `grep -cE "_ISO8601_Z_PATTERN" database.py` ≥ 2 (pattern definition + match call). New test `test_scan_decay_candidates_rejects_malformed_cutoff` pins log-and-skip behavior: for each of `"+00:00"`, `""`, `"not-iso"` asserts (a) `list(scan_decay_candidates(...))` is empty, (b) `"format violation"` in stderr, (c) NO exception raised. New test `test_scan_decay_candidates_matches_iso_utc_output` verifies `_iso_utc(datetime.now(timezone.utc))` matches the regex.
- **AC-8 (#00198 spec fix):** `grep -c '1000, 500000' docs/features/091-082-qa-residual-cleanup/spec.md` = 0; `grep -c '1000, 10_000_000' docs/features/091-082-qa-residual-cleanup/spec.md` ≥ 2.
- **AC-9 (#00199 helper):** `grep -c "_run_maintenance_fault_test" test-hooks.sh` ≥ 3 (1 definition + 2 call sites). Line-count decrease: `wc -l test-hooks.sh` (post-092) < `wc -l test-hooks.sh` (pre-092) - 30.
- **AC-10 (#00200 batch_demote):** new pytest `test_batch_demote_empty_now_iso_with_ids_raises` asserts `ValueError` when `ids=["x"]` and `now_iso=""`. Companion pytest `test_batch_demote_empty_now_iso_with_empty_ids_returns_zero` asserts `batch_demote([], 'medium', '')` returns 0 (preserves empty-ids short-circuit).
- **AC-11 (#00201 markers):** `bash test-hooks.sh 2>&1 | grep -cE "AC-22b PASS: shell guard"` = 1; same for `AC-22c PASS: shell guard`. (Uses unique prefix rather than `^` anchor to tolerate any test-runner line prefixing.)
- **AC-12 (structural exit):** Post-merge adversarial QA by 4 parallel reviewers produces zero HIGH findings. Decider: feature author.

## Assumptions

1. **A1:** `_config_utils._iso_utc` emits `strftime("%Y-%m-%dT%H:%M:%SZ")`. Verified at `plugins/pd/hooks/lib/semantic_memory/_config_utils.py:31-47`.
2. **A2:** No test currently passes `scan_limit=-1` or empty `now_iso` as a sentinel. Verified via grep.
3. **A3:** BSD `cp -P` semantics match GNU `cp -P` (preserve symlinks). Verified via `man cp` on macOS (BSD).
4. **A4:** `set -euo pipefail` in helper function body works under bash 3.2 (macOS `/usr/bin/bash`). `set -eo pipefail` is portable; `set -u` is NOT added (per FR-2 constraint).

## Risks

1. **R-1 [LOW]** FR-5 regex rejects `+00:00`-suffixed valid UTC strings. Intentional — matches `_iso_utc` Z-suffix contract. New test `test_scan_decay_candidates_matches_iso_utc_output` guards against format drift.
2. **R-2 [LOW]** FR-7 helper extraction introduces one shared dependency. Mitigated by `set +e` + explicit `|| { echo FAIL; exit 1; }` guards on each setup step + two different test functions (helper bugs fail both loudly, not silently).
3. **R-3 [LOW]** FR-9 explicit echo markers create an output-format contract. Acceptable — matches DoD intent.
4. **R-4 [MED]** Structural exit gate (AC-12) requires 4-reviewer post-merge QA dispatch. Execution burden ~10 min. Deferring = pattern recurrence (091 → 24 post-release findings).

## Out of Scope

- Pre-release adversarial QA gate in `/pd:finish-feature` (PRD Open Q #1). Separate backlog entry (#00217 proposed).
- Any of the 15 LOW/test-gap findings from 091 post-release QA (#00202-#00216). Deferred to future test-hardening feature.

## Evidence Map

| Requirement | Evidence |
|------------|----------|
| FR-1/AC-1/AC-2 | `database.py:953-990` current scan_decay_candidates + docstring |
| FR-2/AC-3/AC-4 | `test-hooks.sh:2980,3041` current trap + mktemp lines |
| FR-3/AC-5 | `test-hooks.sh:3023` current wrong-cwd git call |
| FR-4/AC-6 | `test-hooks.sh:2982,3043` current `cp -R` without `-P` |
| FR-5/AC-7 | `database.py:953-990` + `_config_utils.py:31-47` |
| FR-6/AC-8 | `spec.md:49,139` stale `[1000, 500000]` |
| FR-7/AC-9 | `test-hooks.sh:2969-3093` two 60-line near-duplicate functions |
| FR-8/AC-10 | `database.py:992-1034` batch_demote without now_iso validation |
| FR-9/AC-11 | `test-hooks.sh:37-39` `log_pass` emits "  PASS" not "AC-22b PASS" |
