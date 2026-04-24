# Tasks: Feature 092 — 091 QA Residual Hotfix

## Global Context

- **Branch:** `feature/092-091-qa-residual-hotfix`
- **Venv:** `plugins/pd/.venv/bin/python` (used for all pytest invocations)
- **Baselines to capture at branch start:**
  - `PRE_092_SHA=$(git rev-parse HEAD)` — set at branch creation
  - `PRE_092_TEST_HOOKS_LOC=$(wc -l < plugins/pd/hooks/tests/test-hooks.sh)` — captured pre-T6/T7 edits
- **Q2 baseline test-hooks.sh count:** `109/109 passed` (pre-092 state; T7 helper extraction may change this — re-baseline after T7 lands)

## Task Index

| ID | Title | Plan Item | Complexity | Depends on |
|----|-------|-----------|------------|------------|
| T12 | FR-1 + FR-5 combined: module-level regex + log-and-skip + clamp + docstring (both edits to `scan_decay_candidates` in same function — sequenced to avoid same-file conflict) | PI-1 + PI-2 | Medium | none |
| T3 | FR-8 `batch_demote` empty-`now_iso` raise (after empty-ids short-circuit) | PI-3 | Simple | none |
| T4 | New pytests: AC-1, AC-7 (2 subtests), AC-10 (2 subtests) | PI-4 | Medium | T12, T3 |
| T5 | FR-6 feature-091 spec clamp edits (2 occurrences) | PI-5 | Simple | none |
| T6a | FR-2 trap/mktemp hardening inline in AC-22b | PI-6 | Simple | none |
| T6b | FR-2 trap/mktemp hardening inline in AC-22c | PI-6 | Simple | T6a (share pattern) |
| T6c | FR-3 AC-4d `git -C` fix in both AC-22b and AC-22c | PI-6 | Simple | T6a, T6b |
| T6d | FR-4 `cp -R -P` in both AC-22b and AC-22c | PI-6 | Simple | T6a, T6b |
| T78 | FR-7 helper extraction + FR-9 PASS marker (co-landed per plan PI-7+8 note) | PI-7+8 | Medium | T6a–T6d |
| Q1 | pytest (test_maintenance.py + test_database.py) | all | Simple | T12, T3, T4, T78 |
| Q2 | test-hooks.sh | B | Simple | T78 |
| Q3 | ./validate.sh | all | Simple | T12, T3, T4, T78 |
| Q4 | Manual AC-5 fire-test | B | Simple | T6c, T78 |

Longest chain: T12→T4→Q1 or T6a→T6b→T6c/T6d→T78→Q2. Direct-orchestrator execution.

## Parallel Execution

**Group Alpha (parallel, independent, up to 5):** T12, T3, T5, T6a
**Group Beta (after Alpha):** T6b (after T6a), T4 (after T12 + T3)
**Group Gamma (after Beta):** T6c, T6d (both after T6b)
**Group Delta (after Gamma):** T78 (absorbs T6a-T6d scaffold edits + adds FR-9 marker)
**Group Epsilon (quality gates):** Q1, Q2, Q3, Q4 (sequential after T78)

## Task Details

### T12: FR-1 + FR-5 combined `scan_decay_candidates` hardening

**Why:** Combines PI-1 (FR-1 #00193 scan_limit DoS-vector clamp) with PI-2 (FR-5 #00197 regex format validation). Both edit the same function in `database.py` — keeping them in one task avoids same-file parallel-edit conflicts flagged by task-reviewer iter 1.

**Files:** `plugins/pd/hooks/lib/semantic_memory/database.py`
**Complexity:** Medium

**Action (perform in order):**
1. Add module-level compiled regex after existing imports (top of file, alongside other module-level constants):
   ```python
   _ISO8601_Z_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
   ```
   (`re` and `sys` are already imported per head of file.)

2. In `scan_decay_candidates`, add regex validation + clamp AT METHOD ENTRY (before existing SQL execute):
   ```python
   if not _ISO8601_Z_PATTERN.match(not_null_cutoff):
       sys.stderr.write(
           f"[scan_decay_candidates] not_null_cutoff format violation: "
           f"expected YYYY-MM-DDTHH:MM:SSZ, got {not_null_cutoff!r}; "
           f"returning empty result\n"
       )
       return  # empty generator (no yield)
   scan_limit = max(0, scan_limit)  # FR-1 (#00193): clamp negatives (SQLite LIMIT -1 = unlimited)
   ```

3. Update docstring:
   - `scan_limit`: replace `"scan_limit <= 0 yields zero rows (SQLite LIMIT semantics) with no exception."` with `"scan_limit <= 0 yields zero rows (negative values clamped to 0 before SQL binding to avoid SQLite LIMIT -1 = unlimited semantics)."`
   - `not_null_cutoff`: add one sentence noting Z-suffix requirement and log-and-skip behavior on mismatch (no exception).

**DoD (all pass):**
```bash
grep -cE "scan_limit = max\(0, scan_limit\)" plugins/pd/hooks/lib/semantic_memory/database.py  # = 1
grep -cE "SQLite LIMIT -1 = unlimited semantics" plugins/pd/hooks/lib/semantic_memory/database.py  # = 1
grep -cE "_ISO8601_Z_PATTERN" plugins/pd/hooks/lib/semantic_memory/database.py  # >= 2 (module-level def + match call)
grep -cE "format violation" plugins/pd/hooks/lib/semantic_memory/database.py  # = 1
```

**Commit:** `pd(092): FR-1 + FR-5 scan_decay_candidates hardening — clamp + regex log-and-skip (#00193, #00197)`

---

### T3: FR-8 `batch_demote` empty-`now_iso` raise

**Files:** `plugins/pd/hooks/lib/semantic_memory/database.py`
**Complexity:** Simple

**Action:**
In `batch_demote`, add validation AFTER `if not ids: return 0` but BEFORE `new_confidence` validation:

```python
def batch_demote(self, ids, new_confidence, now_iso):
    if not ids:
        return 0  # UNCHANGED — preserves empty-ids short-circuit
    if not now_iso:
        raise ValueError("now_iso must be non-empty ISO-8601 timestamp")
    # ... existing new_confidence validation continues
```

**DoD:**
```bash
grep -cE "now_iso must be non-empty ISO-8601 timestamp" plugins/pd/hooks/lib/semantic_memory/database.py  # = 1
```

**Commit:** `pd(092): FR-8 validate non-empty now_iso in batch_demote (#00200)`

---

### T4: New pytests for AC-1, AC-7, AC-10

**Files:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
**Complexity:** Medium
**Depends on:** T1, T2, T3

**Action:** add 5 new test methods to `TestScanDecayCandidates` (AC-1 + AC-7×2) and `TestBatchDemote` (AC-10×2):

```python
# In TestScanDecayCandidates:
def test_scan_decay_candidates_clamps_negative_scan_limit_to_zero(self, db):
    """AC-1: scan_limit=-1 → zero rows (clamped, not SQLite LIMIT -1 unlimited)."""
    db.insert_test_entry_for_testing(
        entry_id="e1", description="x", confidence="high",
        source="session-capture",
        last_recalled_at="2026-04-15T00:00:00Z",
        created_at="2026-04-15T00:00:00Z",
    )
    rows = list(db.scan_decay_candidates(
        not_null_cutoff="2026-04-20T00:00:00Z", scan_limit=-1,
    ))
    assert rows == []

def test_scan_decay_candidates_rejects_malformed_cutoff(self, db, capsys):
    """AC-7: malformed cutoff → empty + stderr 'format violation' + NO exception."""
    for bad_cutoff in ["+00:00", "", "not-iso", "2026-04-20T00:00:00+00:00"]:
        rows = list(db.scan_decay_candidates(
            not_null_cutoff=bad_cutoff, scan_limit=100,
        ))
        assert rows == []
    captured = capsys.readouterr()
    assert "format violation" in captured.err

def test_scan_decay_candidates_matches_iso_utc_output(self, db):
    """AC-7: production _iso_utc output passes the regex (prevents format drift)."""
    from datetime import datetime, timezone
    from semantic_memory._config_utils import _iso_utc
    from semantic_memory.database import _ISO8601_Z_PATTERN
    now_iso = _iso_utc(datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc))
    assert _ISO8601_Z_PATTERN.match(now_iso), \
        f"_iso_utc output {now_iso!r} does not match regex — format drift"

# In TestBatchDemote:
def test_batch_demote_empty_now_iso_with_ids_raises(self):
    """AC-10: ids=['x'] + now_iso='' → ValueError."""
    db = MemoryDatabase(":memory:")
    try:
        with pytest.raises(ValueError, match="now_iso must be non-empty"):
            db.batch_demote(["x"], "medium", "")
    finally:
        db.close()

def test_batch_demote_empty_now_iso_with_empty_ids_returns_zero(self):
    """AC-10: ids=[] + now_iso='' → 0 (preserves empty-ids short-circuit)."""
    db = MemoryDatabase(":memory:")
    try:
        assert db.batch_demote([], "medium", "") == 0
    finally:
        db.close()
```

**DoD:**
```bash
plugins/pd/.venv/bin/python -m pytest \
    plugins/pd/hooks/lib/semantic_memory/test_database.py::TestScanDecayCandidates::test_scan_decay_candidates_clamps_negative_scan_limit_to_zero \
    plugins/pd/hooks/lib/semantic_memory/test_database.py::TestScanDecayCandidates::test_scan_decay_candidates_rejects_malformed_cutoff \
    plugins/pd/hooks/lib/semantic_memory/test_database.py::TestScanDecayCandidates::test_scan_decay_candidates_matches_iso_utc_output \
    plugins/pd/hooks/lib/semantic_memory/test_database.py::TestBatchDemote::test_batch_demote_empty_now_iso_with_ids_raises \
    plugins/pd/hooks/lib/semantic_memory/test_database.py::TestBatchDemote::test_batch_demote_empty_now_iso_with_empty_ids_returns_zero \
    -v | grep -E "5 passed"
```

**Commit:** `pd(092): AC-1/7/10 pytests — clamp, regex log-and-skip, batch_demote validation`

---

### T5: FR-6 feature-091 spec clamp edits

**Files:** `docs/features/091-082-qa-residual-cleanup/spec.md`
**Complexity:** Simple

**Action:** Two literal edits:
- Line 49: `[1000, 500000]` → `[1000, 10_000_000]` (FR-1 row 14 closure marker for #00107)
- Line 139: `[1000, 500000]` → `[1000, 10_000_000]` (FR-4 body)

**DoD:**
```bash
grep -c '1000, 500000' docs/features/091-082-qa-residual-cleanup/spec.md  # = 0
grep -c '1000, 10_000_000' docs/features/091-082-qa-residual-cleanup/spec.md  # >= 2
```

**Commit:** `pd(092): FR-6 correct stale scan_limit clamp values in feature 091 spec (#00198)`

---

### T6a: FR-2 trap/mktemp hardening in AC-22b

**Files:** `plugins/pd/hooks/tests/test-hooks.sh`
**Complexity:** Simple

**Action:** In `test_memory_decay_syntax_error_tolerated`, replace:
```bash
PKG_TMPDIR=$(mktemp -d)
trap "rm -rf \"$PKG_TMPDIR\"" EXIT
mkdir -p "$PKG_TMPDIR/semantic_memory"
```
With:
```bash
PKG_TMPDIR=$(mktemp -d) || { log_fail "mktemp -d failed"; exit 1; }
[ -n "$PKG_TMPDIR" ] || { log_fail "mktemp -d returned empty"; exit 1; }
[ -d "$PKG_TMPDIR" ] || { log_fail "mktemp -d target not a directory"; exit 1; }
trap 'rm -rf -- "$PKG_TMPDIR"' EXIT
mkdir -p "$PKG_TMPDIR/semantic_memory" || { echo "FAIL: mkdir -p failed"; exit 1; }
```

**DoD:** grep the single-quoted trap + three guards present in AC-22b region. T6a landed in pre-helper form (will be absorbed by T7).

**Commit:** `pd(092): FR-2 harden AC-22b trap + mktemp guards (inline, #00194)`

---

### T6b: FR-2 trap/mktemp hardening in AC-22c

**Why:** Mirrors T6a for the ImportError test function so both AC-22b/c blocks have identical hardened scaffold before T78 consolidates them into a helper.

**Files:** `plugins/pd/hooks/tests/test-hooks.sh`
**Complexity:** Simple
**Depends on:** T6a (use identical pattern)

**Action:** In `test_memory_decay_import_error_tolerated` (the second of the two AC-22 functions), apply the same 3-guard + single-quoted-trap + explicit-fail edits as T6a. Before/after is identical to T6a:

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
trap 'rm -rf -- "$PKG_TMPDIR"' EXIT
mkdir -p "$PKG_TMPDIR/semantic_memory" || { echo "FAIL: mkdir -p failed"; exit 1; }
```

**DoD:**
```bash
grep -cE "trap 'rm -rf --" plugins/pd/hooks/tests/test-hooks.sh  # = 2 (post T6a+T6b, pre-T78)
grep -cE 'trap "rm -rf' plugins/pd/hooks/tests/test-hooks.sh  # = 0 (old double-quoted pattern fully eliminated)
```

**Commit:** `pd(092): FR-2 harden AC-22c trap + mktemp guards (inline, #00194)`

---

### T6c: FR-3 AC-4d `git -C` fix in both AC-22b and AC-22c

**Action:** Replace in both test functions (2 occurrences):
```bash
git_status=$(cd "$(dirname "${HOOKS_DIR}")" && git status --porcelain "plugins/pd/hooks/lib/semantic_memory/maintenance.py" 2>/dev/null || true)
```
With:
```bash
git_status=$(git -C "$(git rev-parse --show-toplevel)" status --porcelain plugins/pd/hooks/lib/semantic_memory/maintenance.py 2>/dev/null || true)
```

**DoD:**
```bash
grep -cE 'git -C "\$\(git rev-parse --show-toplevel\)"' plugins/pd/hooks/tests/test-hooks.sh  # >= 1
grep -cE 'cd "\$\(dirname' plugins/pd/hooks/tests/test-hooks.sh  # reduce by 2
```

**Commit:** `pd(092): FR-3 AC-4d invariant uses repo-root-absolute git call (#00195)`

---

### T6d: FR-4 `cp -R -P` in both AC-22b and AC-22c

**Action:** Replace `cp -R "${HOOKS_DIR}/...` → `cp -R -P "${HOOKS_DIR}/...` in both sites.

**DoD:**
```bash
grep -cE 'cp -R -P "\$\{HOOKS_DIR\}' test-hooks.sh  # >= 2 (pre-T7) or >= 1 (post-T7)
grep -cE 'cp -R "\$\{HOOKS_DIR\}/lib/semantic_memory' test-hooks.sh  # = 0
```

**Commit:** `pd(092): FR-4 cp -R -P (no-dereference symlinks, #00196)`

---

### T78: FR-7 helper extraction + FR-9 PASS marker (co-landed)

**Why:** Per plan PI-7+8 co-landing note, FR-7 helper extraction and FR-9 echo-marker addition are one atomic change. The helper body (implemented per spec FR-7 pseudocode) includes the `echo "${test_label} PASS: ..."` line INSIDE the subshell. Two separate tasks would risk double-adding or mis-omitting the marker.

**Files:** `plugins/pd/hooks/tests/test-hooks.sh`
**Complexity:** Medium
**Depends on:** T6a, T6b, T6c, T6d (helper absorbs their hardened scaffold)

**Action:**

1. Add `_run_maintenance_fault_test` helper function alongside other helpers (near top of test-hooks.sh, after `log_pass`/`log_fail`/`log_test`). Use the full body from spec FR-7 pseudocode — note the `echo "${test_label} PASS: ..."` line inside the subshell (this is FR-9's marker).

2. Replace the bodies of both test functions to simply call the helper:
   ```bash
   test_memory_decay_syntax_error_tolerated() {
       log_test "session-start guard tolerates SyntaxError in maintenance.py (AC-22b, FR-3)"
       _run_maintenance_fault_test "AC-22b" "T7a" "append" $'\ndef broken(:\n'
   }

   test_memory_decay_import_error_tolerated() {
       log_test "session-start guard tolerates ImportError in maintenance.py (AC-22c, FR-3)"
       _run_maintenance_fault_test "AC-22c" "T7b" "prepend" "import no_such_module_really_does_not_exist"
   }
   ```

3. Manually run AC-5 fire-test (per TD-7): after helper lands, modify `plugins/pd/hooks/lib/semantic_memory/maintenance.py` locally (add a blank line), run AC-22b, verify AC-4d invariant FAILS with `"production maintenance.py mutated: ..."` message. Revert the local modification. Record result in implementation-log.md ("AC-5 fire-test: verified AC-4d invariant fails on dirty production file on 2026-04-20").

**DoD (all pass):**
```bash
# FR-7 helper exists:
grep -c "_run_maintenance_fault_test" plugins/pd/hooks/tests/test-hooks.sh  # >= 3 (1 def + 2 calls)

# FR-9 markers emitted:
bash plugins/pd/hooks/tests/test-hooks.sh 2>&1 | grep -cE "AC-22b PASS: shell guard"  # = 1
bash plugins/pd/hooks/tests/test-hooks.sh 2>&1 | grep -cE "AC-22c PASS: shell guard"  # = 1

# AC-9 line-count reduction (test-hooks.sh got smaller after helper consolidation):
# Compare against captured PRE_092_TEST_HOOKS_LOC from Global Context.
# Expected: helper (~65 lines) replaces 2×60-line inline functions → net ≈ -55 lines.
[ "$(wc -l < plugins/pd/hooks/tests/test-hooks.sh)" -lt "$PRE_092_TEST_HOOKS_LOC" ]
```

**Commit:** `pd(092): FR-7 helper + FR-9 markers — _run_maintenance_fault_test with AC-22X PASS echo (#00199, #00201)`

---

### Q1-Q4: Quality gates

Each gate's DoD already defined in each Txx task's DoD block above — Q1-Q4 are orchestration wrappers that execute the task-level DoDs as a final check.

- **Q1:** Full pytest suite
  ```bash
  plugins/pd/.venv/bin/python -m pytest \
    plugins/pd/hooks/lib/semantic_memory/test_maintenance.py \
    plugins/pd/hooks/lib/semantic_memory/test_database.py 2>&1 | tail -3
  ```
  Pass: last line contains `"N passed"` (N = baseline + 5 new from T4); `0 failed`.

- **Q2:** Shell test harness
  ```bash
  bash plugins/pd/hooks/tests/test-hooks.sh 2>&1 | grep 'Results:'
  ```
  Pass: `Results: X/X passed` (X = 109 or whatever baseline captures; T4 adds Python tests not shell tests, so count is unchanged).

- **Q3:** `./validate.sh` → exit 0 (errors count = 0; warnings OK).

- **Q4 (manual AC-5 fire-test):** handled inline during T78 per TD-7. Verification lives in implementation-log.md.

Overall AC verification is the union of per-task DoDs (T12 + T3 + T4 + T5 + T6a/b/c/d + T78). No separate `V1` script — the task-level DoDs provide binary verification.

## Out of Scope

Same as spec — no expansion.
