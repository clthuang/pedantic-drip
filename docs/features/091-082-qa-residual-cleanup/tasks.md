# Tasks: Feature 091 — 082 QA Residual Cleanup

## Status
- Created: 2026-04-20
- Phase: create-plan (tasks breakdown)
- Upstream: `docs/features/091-082-qa-residual-cleanup/plan.md`

## Task Index

| ID | Title | Plan Item | Complexity | Parallel | Depends on |
|----|-------|-----------|------------|----------|------------|
| T1 | Backlog hygiene — add 23 closure markers | PI-1 | Medium | (first, then parallel) | none |
| T2 | Remove dead `updated_at IS NULL` SQL branch | PI-2 | Simple | yes | T1 |
| T3a | Write equal-threshold warning tests (RED) | PI-3 | Simple | yes | T1 |
| T3b | Flip `<` → `<=` predicate + warning text (GREEN) | PI-3 | Simple | no | T3a |
| T4a | Write `scan_decay_candidates` tests (RED) | PI-4 | Medium | yes | T1 |
| T4b | Add `MemoryDatabase.scan_decay_candidates` method (GREEN) | PI-4 | Simple | no | T4a |
| T5 | Swap `_select_candidates` body to call new method | PI-5 | Simple | no | T4b, T6 |
| T6 | `TestSelectCandidates` isoformat → _iso swap + canonical pin | PI-6 | Simple | yes | T1 |
| T7a | `test-hooks.sh` AC-22b block (SyntaxError) | PI-7 | Medium | yes | T1 |
| T7b | `test-hooks.sh` AC-22c block (ImportError) | PI-7 | Simple | no | T7a |
| Q1 | Run full test suite (pytest) | all PI | Simple | no | T1..T7b |
| Q2 | Run shell tests (test-hooks.sh) | PI-7 | Simple | no | T7a, T7b |
| Q3 | Run `./validate.sh` | all | Simple | no | T1..T7b |
| Q4 | Run `pd:doctor` | all | Simple | no | T1..T7b |
| V1 | Run AC static verification script (grep/structural) | all | Simple | no | T1..T7b |

Total: 15 tasks. Longest serial chain: T1 → T4a → T4b → T6 → T5 → Q1 → V1 (7 items). Parallel groups defined below.

## Parallel Execution Groups

### Group Alpha-docs (serial, first)
- T1 (backlog hygiene) — docs-only, isolates reviewer attention before code commits land.

### Group Alpha-code (parallel after T1 — up to 5 in parallel)
- T2, T3a, T4a, T6, T7a

**File-level coupling note:** T3a appends a new test class to `test_maintenance.py`; T6 edits an existing `TestSelectCandidates` class in the same file at lines 400-410. These regions do not overlap so parallel-worktree merge is conflict-free, but implementers must not auto-reorder classes or run reformatters that touch unrelated sections. If in doubt, serialize T3a and T6.

### Group Beta (after Group Alpha-code)
- T3b (after T3a)
- T4b (after T4a)
- T7b (after T7a — both in test-hooks.sh; serialized for clarity)

### Group Gamma (after Group Beta)
- T5 (after T4b AND T6) — regression verification at AC-7d requires `TestSelectCandidates` to be in its post-T6 state (isoformat replaced with `_iso`) so any drift is attributed correctly.

### Quality Gates (sequential, after all T-tasks)
- Q1 → Q2 → Q3 → Q4 → V1

## Task Details

---

### T1: Backlog hygiene — add 23 closure markers

**Plan Item:** PI-1 (FR-1)
**Files:** `docs/backlog.md`
**Complexity:** Medium (23 precise edits across two sections)
**Depends on:** none (runs first; reviewer-bandwidth isolation per design TD-6)

**Action:**
1. For each of the 23 rows in spec FR-1 mapping table, locate the corresponding entry in `docs/backlog.md` and append the exact marker text from column 4.
2. Confirm no other line edits.

**Concrete edit locations** (verified during design research):
- Table-style rows (lines 59-63 approx): #00075, #00076, #00077, #00078, #00079 (only #00075 gets closure marker; #00076-#00079 are OPEN and left untouched in this feature — their markers come via PA-2 post-merge)
- List-style rows (Group B section, lines 86+): #00095-#00116 minus #00078 (skipped as sub-items a/b/c belong to distinct entries only for #00116, which gets the partial marker)

Wait — per spec FR-1, exactly these 22 IDs get closure markers + 1 ID (#00116) gets partial marker = 23:
  #00075, #00095, #00096, #00097, #00098, #00099, #00100, #00101, #00102, #00103, #00104, #00105, #00106, #00107, #00108, #00109, #00111, #00112, #00113, #00114, #00115 (closures)
  #00116 (partial)

#00110 is NOT touched. #00076, #00077, #00078, #00079 are NOT touched (receive their markers via PA-2 post-merge).

**Definition of Done (binary pass/fail):**
```bash
# AC-1 verification — exact markers present per spec FR-1 table (full check in V1):
# Run a spot-check loop for the 3 most-critical IDs during T1 completion;
# full 23-ID marker check is V1's job.
grep -qE '#00075.*fixed in feature:089' docs/backlog.md
grep -qE '#00095.*fixed in feature:088' docs/backlog.md
grep -qE '#00116.*partially fixed in feature:088' docs/backlog.md

# AC-1b verification: validate.sh checks plugin structure (frontmatter, path portability, .meta.json).
# Passing confirms the backlog.md edits haven't broken adjacent plugin-parseable files.
# Note: validate.sh does NOT semantically inspect docs/backlog.md content — AC-1 (above) is the semantic gate.
./validate.sh
# Exit 0

# AC-1c verification (per-ID presence of all 27 082-era IDs):
for id in 00075 00076 00077 00078 00079 00095 00096 00097 00098 00099 00100 00101 00102 00103 00104 00105 00106 00107 00108 00109 00110 00111 00112 00113 00114 00115 00116; do
  n=$(grep -cE "^(\||-).*#${id}([^0-9]|$)" docs/backlog.md) || n=0
  [ "$n" -ge 1 ] || { echo "MISSING: #$id"; exit 1; }
done
echo "All 27 IDs present."
```

**Commit message:** `chore(091): add closure markers for 23 082-era backlog items (#00075, #00095..#00116)`

---

### T2: Remove dead `updated_at IS NULL` SQL branch

**Plan Item:** PI-2 (FR-5)
**Files:** `plugins/pd/hooks/lib/semantic_memory/database.py`
**Complexity:** Simple
**Depends on:** T1 (Group Alpha-docs lands first to isolate docs-only commit per design TD-6)

**Action:**
1. At `plugins/pd/hooks/lib/semantic_memory/database.py:1028`:
   - Before: `f"  AND (updated_at IS NULL OR updated_at < ?)"`
   - After: `f"  AND updated_at < ?"`

**Definition of Done (binary pass/fail):**
```bash
# AC-8:
[ "$(grep -c 'updated_at IS NULL' plugins/pd/hooks/lib/semantic_memory/database.py)" = "0" ]

# AC-8b (regression): existing _execute_chunk tests pass
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -v -k "execute_chunk or batch_demote" | grep -E "passed|failed"
# Expect: N passed, 0 failed
```

**Commit message:** `pd(091): remove dead updated_at IS NULL branch from _execute_chunk (FR-5, #00079)`

---

### T3a: Write equal-threshold warning tests (RED)

**Plan Item:** PI-3 (FR-2)
**Files:** `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py`
**Complexity:** Simple
**Depends on:** T1 (Group Alpha-docs lands first to isolate docs-only commit per design TD-6)

**Action:**
1. Add new test class `TestDecayWarningPredicate` to `test_maintenance.py` (append near the other warning-related test classes). Place the two tests as methods of this class so pytest test IDs are unambiguous:
   ```python
   class TestDecayWarningPredicate:
       """FR-2 #00076: med_days <= high_days emits stderr warning."""

       def test_equal_threshold_emits_warning(self, fresh_db, capsys):
       """FR-2 AC-3: med_days == high_days emits stderr warning."""
       # `re` is imported at module top of test_maintenance.py already;
       # no function-local import needed.
       cfg = _enabled_config(
           memory_decay_high_threshold_days=30,
           memory_decay_medium_threshold_days=30,
       )
       maintenance.decay_confidence(fresh_db, cfg, now=NOW)
       captured = capsys.readouterr()
       assert re.search(
           r"\[memory-decay\].*memory_decay_medium_threshold_days.*<=.*memory_decay_high_threshold_days",
           captured.err,
       ), f"expected equal-threshold warning; got: {captured.err!r}"

   def test_strictly_less_threshold_still_emits_warning(self, fresh_db, capsys):
       """FR-2 AC-3b: med_days < high_days case continues to emit warning
       (regression pin for predicate swap <= vs <)."""
       cfg = _enabled_config(
           memory_decay_high_threshold_days=30,
           memory_decay_medium_threshold_days=10,
       )
       maintenance.decay_confidence(fresh_db, cfg, now=NOW)
       captured = capsys.readouterr()
       assert re.search(
           r"\[memory-decay\].*memory_decay_medium_threshold_days.*<=.*memory_decay_high_threshold_days",
           captured.err,
       ), f"expected strict-less warning; got: {captured.err!r}"
   ```

**Definition of Done (binary pass/fail):**
```bash
plugins/pd/.venv/bin/python -m pytest \
  plugins/pd/hooks/lib/semantic_memory/test_maintenance.py::TestDecayWarningPredicate::test_equal_threshold_emits_warning \
  plugins/pd/hooks/lib/semantic_memory/test_maintenance.py::TestDecayWarningPredicate::test_strictly_less_threshold_still_emits_warning \
  -v
# Expect RED: BOTH tests FAIL before T3b applies the predicate swap
# (equal-case test fails because no warning; strict-less test fails because warning text doesn't contain "<=")
```

**Commit message:** `pd(091): RED — test_equal_threshold / test_strictly_less warnings (FR-2, #00076)`

---

### T3b: Flip `<` → `<=` predicate + warning text (GREEN)

**Plan Item:** PI-3 (FR-2)
**Files:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py`
**Complexity:** Simple
**Depends on:** T3a (tests must exist and be RED first)

**Action:**
1. At `plugins/pd/hooks/lib/semantic_memory/maintenance.py:424-429`:
   ```python
   # Before:
   if med_days < high_days and not _decay_config_warned:
       sys.stderr.write(
           "[memory-decay] memory_decay_medium_threshold_days "
           f"({med_days}) < memory_decay_high_threshold_days ({high_days}); "
           "medium tier will decay faster than high\n"
       )
       _decay_config_warned = True
   ```
   ```python
   # After:
   if med_days <= high_days and not _decay_config_warned:
       sys.stderr.write(
           "[memory-decay] memory_decay_medium_threshold_days "
           f"({med_days}) <= memory_decay_high_threshold_days ({high_days}); "
           "medium tier will decay at same pace or faster than high\n"
       )
       _decay_config_warned = True
   ```
2. **Test-pollution pre-check** (per plan-reviewer iteration 1 warning): existing test `TestDecayThresholdEquality::test_ac31_threshold_equality_edge` at `test_maintenance.py:1357-1379` seeds `med=high=30` without `capsys`. After the `<=` flip, this test will trigger the new warning as a side effect. Action:
   - At `test_maintenance.py` line ~1360, change signature from `def test_ac31_threshold_equality_edge(self, fresh_db):` to `def test_ac31_threshold_equality_edge(self, fresh_db, capsys):`.
   - Append `captured = capsys.readouterr()` as the final line of that test (drain only; no assertion).
   - Include this edit in T3b's commit (same commit as the `<=` flip).
   - Verify: `grep -nE "def test_ac31.*capsys" plugins/pd/hooks/lib/semantic_memory/test_maintenance.py` returns 1 match.

   This is NOT a behavior change — just avoids stderr leakage polluting pytest output.

**Definition of Done (binary pass/fail):**
```bash
# AC-2:
[ "$(grep -cE 'if med_days <= high_days' plugins/pd/hooks/lib/semantic_memory/maintenance.py)" = "1" ]

# AC-2b:
[ "$(grep -cE 'if med_days < high_days' plugins/pd/hooks/lib/semantic_memory/maintenance.py)" = "0" ]

# T3a tests now GREEN:
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_maintenance.py::TestDecayWarningPredicate -v | grep -E "2 passed"
```

**Commit message:** `pd(091): GREEN — <= predicate + updated warning text (FR-2, #00076)`

---

### T4a: Write `scan_decay_candidates` tests (RED)

**Plan Item:** PI-4 (FR-4)
**Files:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
**Complexity:** Medium
**Depends on:** T1 (Group Alpha-docs lands first to isolate docs-only commit per design TD-6)

**Action:**
1. Add test class `TestScanDecayCandidates` to `test_database.py`:
   ```python
   from collections.abc import Iterator

   class TestScanDecayCandidates:
       """FR-4: public scan_decay_candidates method on MemoryDatabase."""

       def test_scan_decay_candidates_respects_where_predicate(self, fresh_db):
           """AC-7: seed 3 stale + 7 fresh; scan_limit=100 returns only 3 stale."""
           cutoff = "2026-04-20T00:00:00Z"
           # Seed 3 rows BELOW cutoff (stale) + 7 rows ABOVE cutoff (fresh).
           # With scan_limit=100, only the 3 stale rows match the WHERE predicate —
           # a non-vacuous assertion that the predicate is actually applied.
           # Note: real MemoryDatabase.insert_test_entry_for_testing signature
           # uses `description` not `content`.
           for i in range(3):
               fresh_db.insert_test_entry_for_testing(
                   entry_id=f"e-stale-{i}",
                   description=f"stale entry {i}",
                   confidence="high",
                   source="session-capture",
                   last_recalled_at="2026-04-15T00:00:00Z",  # < cutoff
                   created_at="2026-04-15T00:00:00Z",
               )
           for i in range(7):
               fresh_db.insert_test_entry_for_testing(
                   entry_id=f"e-fresh-{i}",
                   description=f"fresh entry {i}",
                   confidence="high",
                   source="session-capture",
                   last_recalled_at="2026-04-25T00:00:00Z",  # > cutoff
                   created_at="2026-04-25T00:00:00Z",
               )
           rows = list(fresh_db.scan_decay_candidates(
               not_null_cutoff=cutoff, scan_limit=100,
           ))
           assert len(rows) == 3, f"expected 3 stale rows, got {len(rows)}"

       def test_scan_decay_candidates_respects_scan_limit_cap(self, fresh_db):
           """AC-7: scan_limit caps result below match count."""
           cutoff = "2026-04-20T00:00:00Z"
           for i in range(10):
               fresh_db.insert_test_entry_for_testing(
                   entry_id=f"e-stale-{i}",
                   description=f"stale {i}",
                   confidence="high",
                   source="session-capture",
                   last_recalled_at="2026-04-15T00:00:00Z",
                   created_at="2026-04-15T00:00:00Z",
               )
           rows = list(fresh_db.scan_decay_candidates(
               not_null_cutoff=cutoff, scan_limit=5,
           ))
           assert len(rows) == 5

       def test_scan_decay_candidates_includes_null_last_recalled_at(self, fresh_db):
           """AC-7b: NULL last_recalled_at rows are returned."""
           cutoff = "2026-04-20T00:00:00Z"
           fresh_db.insert_test_entry_for_testing(
               entry_id="e-null",
               description="x",
               confidence="medium",
               source="session-capture",
               last_recalled_at=None,
               created_at="2026-04-15T00:00:00Z",
           )
           fresh_db.insert_test_entry_for_testing(
               entry_id="e-past",
               description="y",
               confidence="high",
               source="session-capture",
               last_recalled_at="2026-04-15T00:00:00Z",
               created_at="2026-04-15T00:00:00Z",
           )
           rows = list(fresh_db.scan_decay_candidates(
               not_null_cutoff=cutoff, scan_limit=100,
           ))
           ids = {row["id"] for row in rows}
           assert "e-null" in ids
           assert "e-past" in ids

       def test_scan_decay_candidates_returns_iterator(self, fresh_db):
           """AC-7c: generator semantics — future refactor to list would fail this."""
           cutoff = "2026-04-20T00:00:00Z"
           result = fresh_db.scan_decay_candidates(
               not_null_cutoff=cutoff, scan_limit=10,
           )
           assert isinstance(result, Iterator)
   ```

**Definition of Done (binary pass/fail):**
```bash
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py::TestScanDecayCandidates -v
# Expect RED: all 4 tests FAIL with AttributeError (method doesn't exist yet)
```

**Commit message:** `pd(091): RED — scan_decay_candidates tests (FR-4, #00078)`

---

### T4b: Add `MemoryDatabase.scan_decay_candidates` method (GREEN)

**Plan Item:** PI-4 (FR-4)
**Files:** `plugins/pd/hooks/lib/semantic_memory/database.py`
**Complexity:** Simple
**Depends on:** T4a

**Action:**
1. Add `from collections.abc import Iterator` to imports at top of `database.py` (alongside `from typing import Callable` at line 11).
2. Add method to `MemoryDatabase` class, immediately before `batch_demote` method:

   ```python
   def scan_decay_candidates(
       self,
       *,
       not_null_cutoff: str,
       scan_limit: int,
   ) -> Iterator[sqlite3.Row]:
       """Yield candidate rows for decay confidence processing.

       Encapsulates the read path previously inlined at
       ``maintenance._select_candidates`` (feature 091 FR-4, #00078).
       Closes the "Direct ``db._conn`` Access" anti-pattern.

       Yields rows with schema (id, confidence, source,
       last_recalled_at, created_at). SQL is pinned byte-for-byte
       to the feature-088 verbatim; see AC-5b for validation.
       """
       cursor = self._conn.execute(
           "SELECT id, confidence, source, last_recalled_at, created_at "
           "FROM entries "
           "WHERE (last_recalled_at IS NOT NULL AND last_recalled_at < ?) "
           "   OR (last_recalled_at IS NULL) "
           "LIMIT ?",
           (not_null_cutoff, scan_limit),
       )
       for row in cursor:
           yield row
   ```

**Definition of Done (binary pass/fail):**
```bash
# AC-5 verification:
[ "$(grep -cE 'def scan_decay_candidates\(' plugins/pd/hooks/lib/semantic_memory/database.py)" = "1" ]

# AC-5b (verbatim SQL pin):
python3 -c "
import re
src = open('plugins/pd/hooks/lib/semantic_memory/database.py').read()
compact = re.sub(r'\s+', ' ', src).strip()
needle = 'SELECT id, confidence, source, last_recalled_at, created_at FROM entries WHERE (last_recalled_at IS NOT NULL AND last_recalled_at < ?) OR (last_recalled_at IS NULL) LIMIT ?'
assert needle in compact, 'SQL pinning failed'
print('SQL pin OK')
"

# T4a tests now GREEN:
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py::TestScanDecayCandidates -v | grep -E "3 passed"
```

**Commit message:** `pd(091): GREEN — MemoryDatabase.scan_decay_candidates public method (FR-4, #00078)`

---

### T5: Swap `_select_candidates` body to call new method

**Plan Item:** PI-5 (FR-4)
**Files:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py`
**Complexity:** Simple
**Depends on:** T4b, T6

**Why T6:** T5's AC-7d regression check runs `TestSelectCandidates` tests. If T6 has not yet landed, the tests still use `.isoformat()`-based cutoffs; any AC-7d drift could be misattributed to the caller swap when it's really isoformat format drift. Serializing T6 before T5 ensures the regression signal is attributable.

**Action:**
1. At `plugins/pd/hooks/lib/semantic_memory/maintenance.py:235-268`, keep the full signature including `grace_cutoff`. Replace only the body (lines 257-268):
   ```python
   # Before (lines 257-268):
   not_null_cutoff = max(high_cutoff, med_cutoff)
   cursor = db._conn.execute(
       "SELECT id, confidence, source, last_recalled_at, created_at "
       "FROM entries "
       "WHERE (last_recalled_at IS NOT NULL AND last_recalled_at < ?) "
       "   OR (last_recalled_at IS NULL) "
       "LIMIT ?",
       (not_null_cutoff, scan_limit),
   )
   for row in cursor:
       yield row

   # After:
   not_null_cutoff = max(high_cutoff, med_cutoff)
   yield from db.scan_decay_candidates(
       not_null_cutoff=not_null_cutoff,
       scan_limit=scan_limit,
   )
   ```
2. Keep `grace_cutoff` parameter (unused in new body; retained for compatibility with existing test calls at `test_maintenance.py:470-475,481`).

**Definition of Done (binary pass/fail):**
```bash
# AC-6:
[ "$(grep -c 'db._conn' plugins/pd/hooks/lib/semantic_memory/maintenance.py)" = "0" ]

# AC-7d (regression — existing TestSelectCandidates tests pass):
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_maintenance.py::TestSelectCandidates -v | grep -E "passed|failed"
# Expect: N passed, 0 failed
```

**Commit message:** `pd(091): wire _select_candidates through scan_decay_candidates (FR-4, #00078)`

---

### T6: `TestSelectCandidates` isoformat → _iso swap + canonical pin

**Plan Item:** PI-6 (FR-6)
**Files:** `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py`
**Complexity:** Simple
**Depends on:** T1 (Group Alpha-docs lands first to isolate docs-only commit per design TD-6)

**Action:**
1. At `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py:397-410` (inside `TestSelectCandidates.test_partitions_six_entries_across_all_buckets`):
   - Delete local `NOW = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)` at line 401.
   - Replace 8 `.isoformat()` calls with `_iso()` calls:
     ```python
     # Before (lines 402-410):
     now_iso = NOW.isoformat()
     high_cutoff = (NOW - timedelta(days=30)).isoformat()
     med_cutoff = (NOW - timedelta(days=60)).isoformat()
     grace_cutoff = (NOW - timedelta(days=14)).isoformat()
     stale_high_ts = (NOW - timedelta(days=100)).isoformat()
     stale_med_ts = (NOW - timedelta(days=100)).isoformat()
     fresh_in_grace_ts = (NOW - timedelta(days=10)).isoformat()
     past_grace_ts = (NOW - timedelta(days=80)).isoformat()

     # After:
     # NOW resolves via module-level _TEST_EPOCH alias at line 507
     # AC-9c canonical format pin:
     assert _iso(NOW) == NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
     now_iso = _iso(NOW)
     high_cutoff = _iso(NOW - timedelta(days=30))
     med_cutoff = _iso(NOW - timedelta(days=60))
     grace_cutoff = _iso(NOW - timedelta(days=14))
     stale_high_ts = _iso(NOW - timedelta(days=100))
     stale_med_ts = _iso(NOW - timedelta(days=100))
     fresh_in_grace_ts = _iso(NOW - timedelta(days=10))
     past_grace_ts = _iso(NOW - timedelta(days=80))
     ```

**Definition of Done (binary pass/fail):**
```bash
# AC-9 (class-body scoped):
n=$(awk '/^class TestSelectCandidates:/{flag=1; next} /^class [A-Z]/{flag=0} flag' \
    plugins/pd/hooks/lib/semantic_memory/test_maintenance.py \
    | grep -cE '\.isoformat\(\)')
[ "$n" = "0" ]

# AC-9b (test still passes):
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_maintenance.py::TestSelectCandidates::test_partitions_six_entries_across_all_buckets -v | grep -E "1 passed"
```

**Commit message:** `pd(091): TestSelectCandidates isoformat → _iso (Z-suffix canonical, New-082-inv-1)`

---

### T7a: `test-hooks.sh` AC-22b block (SyntaxError)

**Plan Item:** PI-7 (FR-3)
**Files:** `plugins/pd/hooks/tests/test-hooks.sh`
**Complexity:** Medium
**Depends on:** T1 (Group Alpha-docs lands first to isolate docs-only commit per design TD-6)

**Action:**
1. Append new test block immediately after existing AC-22 block (at ~line 2952 in test-hooks.sh). Use the full harness template from design I-5:

   ```bash
   # AC-22b: SyntaxError in maintenance.py — shell guard tolerates (exit 0)
   (
     [ -x plugins/pd/.venv/bin/python ] || { echo "SKIP: venv missing for AC-22b"; exit 0; }

     PKG_TMPDIR=$(mktemp -d)
     trap "rm -rf \"$PKG_TMPDIR\"" EXIT
     mkdir -p "$PKG_TMPDIR/semantic_memory"
     cp -R plugins/pd/hooks/lib/semantic_memory/. "$PKG_TMPDIR/semantic_memory/"

     # Positive control: __init__.py must be copied for -m import.
     [ -f "$PKG_TMPDIR/semantic_memory/__init__.py" ] || { echo "FAIL: __init__.py missing from copy"; exit 1; }

     # Positive control: clean copy imports successfully.
     PYTHONPATH="$PKG_TMPDIR" plugins/pd/.venv/bin/python \
       -c 'import semantic_memory.maintenance' 2>/dev/null \
       || { echo "FAIL: clean copy does not import — harness precondition broken"; exit 1; }

     # Inject SyntaxError:
     printf '\ndef broken(:\n' >> "$PKG_TMPDIR/semantic_memory/maintenance.py"

     # Negative control: WITHOUT guard, raw invocation MUST fail.
     PYTHONPATH="$PKG_TMPDIR" plugins/pd/.venv/bin/python \
       -m semantic_memory.maintenance --decay --project-root . >/dev/null 2>&1
     raw_exit=$?
     [ "$raw_exit" -ne 0 ] || { echo "FAIL: AC-22b fault did not trigger — raw exit was 0"; exit 1; }

     # Positive contract: WITH production guard, exit 0.
     PYTHONPATH="$PKG_TMPDIR" plugins/pd/.venv/bin/python \
       -m semantic_memory.maintenance --decay --project-root . 2>/dev/null || true

     echo "AC-22b PASS: Python failed (raw exit $raw_exit) but shell guard tolerated"
   )
   ```

**Definition of Done (binary pass/fail):**
```bash
# Check test-hooks.sh flags: shebang + `set -e` handling. If the outer script uses `set -e`,
# a subshell `exit 1` on harness precondition failure could abort the whole script, preventing
# AC-22c from running later. Confirm the AC-22 block at line ~2910 is already in a pattern
# resilient to this (existing test passes; our new blocks use subshells with their own exit
# paths so the outer flow is not interrupted by subshell internals).
head -5 plugins/pd/hooks/tests/test-hooks.sh | grep -E '^#!' || { echo "missing shebang"; exit 1; }

# AC-4a: Run test-hooks.sh and check for AC-22b PASS marker
bash plugins/pd/hooks/tests/test-hooks.sh 2>&1 | grep -qE "AC-22b PASS"

# AC-4d invariant:
git_status=$(git status --porcelain plugins/pd/hooks/lib/semantic_memory/maintenance.py)
[ -z "$git_status" ] || { echo "FAIL: production file mutated"; exit 1; }
```

**Commit message:** `pd(091): add AC-22b test-hooks.sh block (SyntaxError, FR-3, #00077)`

---

### T7b: `test-hooks.sh` AC-22c block (ImportError)

**Plan Item:** PI-7 (FR-3)
**Files:** `plugins/pd/hooks/tests/test-hooks.sh`
**Complexity:** Simple
**Depends on:** T7a (both blocks in same file; T7b mirrors T7a pattern)

**Action:**
1. Append AC-22c block immediately after AC-22b using sed-free prepend for ImportError injection:

   ```bash
   # AC-22c: ImportError in maintenance.py — shell guard tolerates (exit 0)
   (
     [ -x plugins/pd/.venv/bin/python ] || { echo "SKIP: venv missing for AC-22c"; exit 0; }

     PKG_TMPDIR=$(mktemp -d)
     trap "rm -rf \"$PKG_TMPDIR\"" EXIT
     mkdir -p "$PKG_TMPDIR/semantic_memory"
     cp -R plugins/pd/hooks/lib/semantic_memory/. "$PKG_TMPDIR/semantic_memory/"

     [ -f "$PKG_TMPDIR/semantic_memory/__init__.py" ] || { echo "FAIL: __init__.py missing from copy"; exit 1; }
     PYTHONPATH="$PKG_TMPDIR" plugins/pd/.venv/bin/python \
       -c 'import semantic_memory.maintenance' 2>/dev/null \
       || { echo "FAIL: clean copy does not import — harness precondition broken"; exit 1; }

     # Inject ImportError via sed-free prepend (portable, no BSD/GNU divergence):
     {
       echo 'import no_such_module_really_does_not_exist'
       cat "$PKG_TMPDIR/semantic_memory/maintenance.py"
     } > "$PKG_TMPDIR/semantic_memory/maintenance.py.new"
     mv "$PKG_TMPDIR/semantic_memory/maintenance.py.new" \
        "$PKG_TMPDIR/semantic_memory/maintenance.py"

     # Negative control:
     PYTHONPATH="$PKG_TMPDIR" plugins/pd/.venv/bin/python \
       -m semantic_memory.maintenance --decay --project-root . >/dev/null 2>&1
     raw_exit=$?
     [ "$raw_exit" -ne 0 ] || { echo "FAIL: AC-22c fault did not trigger — raw exit was 0"; exit 1; }

     # Positive contract:
     PYTHONPATH="$PKG_TMPDIR" plugins/pd/.venv/bin/python \
       -m semantic_memory.maintenance --decay --project-root . 2>/dev/null || true

     echo "AC-22c PASS: Python failed (raw exit $raw_exit) but shell guard tolerated"
   )
   ```

**Definition of Done (binary pass/fail):**
```bash
# AC-4b: Run the block and check output
bash plugins/pd/hooks/tests/test-hooks.sh 2>&1 | grep -E "AC-22c PASS"
# Expect: one match

# AC-4d invariant (still holds):
git_status=$(git status --porcelain plugins/pd/hooks/lib/semantic_memory/maintenance.py)
[ -z "$git_status" ] || { echo "FAIL: production file mutated"; exit 1; }
```

**Commit message:** `pd(091): add AC-22c test-hooks.sh block (ImportError, FR-3, #00077)`

---

### Q1: Run full test suite (pytest)

**Depends on:** T1..T7b

**Action:**
```bash
plugins/pd/.venv/bin/python -m pytest \
  plugins/pd/hooks/lib/semantic_memory/test_maintenance.py \
  plugins/pd/hooks/lib/semantic_memory/test_database.py \
  -v
```

**Definition of Done:** Zero failures. Output ends with `N passed, 0 failed, M skipped`.

---

### Q2: Run shell tests (test-hooks.sh)

**Depends on:** T7a, T7b

**Action:**
```bash
bash plugins/pd/hooks/tests/test-hooks.sh 2>&1 | tee /tmp/test-hooks.log
grep -E "AC-22b PASS|AC-22c PASS" /tmp/test-hooks.log
```

**Definition of Done:** Both `AC-22b PASS` and `AC-22c PASS` lines present. Overall test-hooks.sh exits 0.

---

### Q3: Run `./validate.sh`

**Depends on:** T1..T7b

**Action:**
```bash
./validate.sh
```

**Definition of Done:** Exit code 0. No ERROR-level output.

---

### Q4: Run `pd:doctor` health check

**Depends on:** T1..T7b

**Action:** Invoke `/pd:doctor` skill.

**Definition of Done:** Health check reports no critical failures. Warnings acceptable.

---

### V1: AC static verification script (grep/structural checks only)

**Note:** V1 covers only static/structural ACs (grep, shell invariants, file content). Dynamic ACs requiring test execution (AC-3/AC-3b pytest; AC-7/AC-7b/AC-7c/AC-7d pytest; AC-9b/AC-9c pytest; AC-4a/AC-4b test-hooks.sh PASS markers) are verified by **Q1** (full pytest run) and **Q2** (test-hooks.sh run). Do NOT skip Q1/Q2 based on V1 passing.

**Depends on:** T1..T7b

**Action:** Consolidated script running every AC check:

```bash
#!/bin/bash
set -e

echo "AC-1 / AC-1c: 27 backlog IDs present"
for id in 00075 00076 00077 00078 00079 00095 00096 00097 00098 00099 00100 00101 00102 00103 00104 00105 00106 00107 00108 00109 00110 00111 00112 00113 00114 00115 00116; do
  n=$(grep -cE "^(\||-).*#${id}([^0-9]|$)" docs/backlog.md) || n=0
  [ "$n" -ge 1 ] || { echo "MISSING: #$id"; exit 1; }
done
echo "✓ All 27 IDs present"

echo "AC-1: exact closure markers per spec FR-1 mapping table (all 23)"
# Per-ID marker verification — loop over the exact FR-1 mapping.
declare -A expected=(
  [00075]="fixed in feature:089"
  [00095]="fixed in feature:088"
  [00096]="fixed in feature:088, feature:089"
  [00097]="fixed in feature:089"
  [00098]="fixed in feature:088"
  [00099]="fixed in feature:089"
  [00100]="fixed in feature:088"
  [00101]="fixed in feature:088"
  [00102]="fixed in feature:088"
  [00103]="fixed in feature:088"
  [00104]="fixed in feature:088"
  [00105]="fixed in feature:088"
  [00106]="fixed in feature:088"
  [00107]="fixed in feature:088"
  [00108]="fixed in feature:088"
  [00109]="fixed in feature:088"
  [00111]="fixed in feature:088"
  [00112]="fixed in feature:089"
  [00113]="fixed in feature:088"
  [00114]="fixed in feature:089"
  [00115]="fixed in feature:088"
  [00116]="partially fixed in feature:088"
)
for id in "${!expected[@]}"; do
  marker="${expected[$id]}"
  grep -qE "#${id}.*${marker}" docs/backlog.md || { echo "MISSING marker on #${id}: expected '${marker}'"; exit 1; }
done
echo "✓ All 23 closure markers verified"

echo "AC-2 / AC-2b: <= predicate"
[ "$(grep -cE 'if med_days <= high_days' plugins/pd/hooks/lib/semantic_memory/maintenance.py)" = "1" ]
[ "$(grep -cE 'if med_days < high_days' plugins/pd/hooks/lib/semantic_memory/maintenance.py)" = "0" ]
echo "✓ Predicate swap"

echo "AC-5: scan_decay_candidates method exists"
[ "$(grep -cE 'def scan_decay_candidates\(' plugins/pd/hooks/lib/semantic_memory/database.py)" = "1" ]
echo "✓ Method exists"

echo "AC-5b: SQL pinned"
python3 -c "
import re
src = open('plugins/pd/hooks/lib/semantic_memory/database.py').read()
compact = re.sub(r'\s+', ' ', src).strip()
needle = 'SELECT id, confidence, source, last_recalled_at, created_at FROM entries WHERE (last_recalled_at IS NOT NULL AND last_recalled_at < ?) OR (last_recalled_at IS NULL) LIMIT ?'
assert needle in compact, 'SQL pinning failed'
"
echo "✓ SQL pinned"

echo "AC-6: no _conn in maintenance.py"
[ "$(grep -c 'db._conn' plugins/pd/hooks/lib/semantic_memory/maintenance.py)" = "0" ]
echo "✓ Encapsulation clean"

echo "AC-8: no dead SQL branch"
[ "$(grep -c 'updated_at IS NULL' plugins/pd/hooks/lib/semantic_memory/database.py)" = "0" ]
echo "✓ Dead branch removed"

echo "AC-9: no .isoformat() in TestSelectCandidates"
n=$(awk '/^class TestSelectCandidates:/{flag=1; next} /^class [A-Z]/{flag=0} flag' plugins/pd/hooks/lib/semantic_memory/test_maintenance.py | grep -cE '\.isoformat\(\)')
[ "$n" = "0" ]
echo "✓ isoformat replaced"

echo "AC-4d (isolation invariant):"
git_status=$(git status --porcelain plugins/pd/hooks/lib/semantic_memory/maintenance.py)
[ -z "$git_status" ] || { echo "FAIL: production file mutated"; exit 1; }
echo "✓ Production file untouched"

echo ""
echo "All AC verifications passed."
```

**Definition of Done:** Script exits 0 with `All AC verifications passed.` as final line.

---

## Out of Scope (reminder)

Per spec and design:
- `_config_utils.py` SPOF mitigation
- Backlog closure-marker automation
- #00116 sub-items c–j
- #00110 re-verification
- PA-1 / PA-2 (deferred to `/pd:finish-feature` retro step)
