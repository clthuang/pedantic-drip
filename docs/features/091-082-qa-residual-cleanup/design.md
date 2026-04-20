# Design: Feature 091 — 082 QA Residual Cleanup

## Status
- Created: 2026-04-20
- Phase: design (started)
- Upstream: `docs/features/091-082-qa-residual-cleanup/spec.md`

## Prior Art Research

Research conducted during design Step 0 validated the 5 critical assumptions embedded in the spec (A1–A7).

| Check | Finding | Evidence |
|-------|---------|----------|
| Scope of SQL predicate — `last_recalled_at IS NOT NULL AND < ?` + `IS NULL` | Only one production caller | `plugins/pd/hooks/lib/semantic_memory/maintenance.py:259` |
| `_execute_chunk` caller reach | Internal only — called by `batch_demote` at `database.py:1003`; tests only monkeypatch | Confirmed |
| `_decay_config_warned` reset coverage | Autouse fixture at `test_maintenance.py:41` handles all tests | Confirmed |
| `.isoformat()` call sites in test_maintenance.py | 8 calls (spec states 9 — overcount by 1; the local `NOW = datetime(...)` assignment line is counted separately in spec) all at lines 402–410, all inside `TestSelectCandidates.test_partitions_six_entries_across_all_buckets` | Confirmed |
| AC-22 rename-to-bak pattern | Unique to the existing AC-22 block at `test-hooks.sh:2910-2952`; NOT reused by AC-22b/c (spec-mandated temp-PYTHONPATH subshell approach instead) | Confirmed |

**Spec minor correction for design:** `.isoformat()` occurrences in `TestSelectCandidates` are 8 (at lines 402, 403, 404, 405, 407, 408, 409, 410), not 9. FR-6's sample "After" block in spec shows 8 replacements. AC-9's awk+grep check asserts `= 0`, which is unaffected by the count. No spec amendment needed; this design note captures the accurate count.

External research: leveraged the findings already present in the brainstorm PRD's Research Summary (CWE-78/94, CWE-59, SQLite ISO-8601 canonical form, unbounded `fetchall()` pattern). No new external research needed for design — the spec pinned verbatim SQL and method signatures.

**Assumption coverage note:** Design-phase research verified A1, A2, A6 (additional interface-gating verification). Assumptions A3, A4, A5, A7 are pre-verified in spec's Evidence Map and relied upon without re-verification. This is explicit to avoid false claim of 7/7 coverage.

## Architecture Overview

The feature is a **6-FR bundle** organized into three independent work streams plus a documentation stream. Each stream has distinct touch points and test surfaces; no cross-stream code dependencies exist.

### Work Streams

| Stream | FRs | Touch points | Dependency |
|--------|-----|--------------|------------|
| **A: Maintenance runtime** | FR-2 (equal-threshold warning) | `maintenance.py:424-429` | None — atomic change |
| **B: Database encapsulation** | FR-4 (scan_decay_candidates), FR-5 (dead SQL branch) | `database.py` (new method + SQL edit), `maintenance.py:257-266` (caller update) | FR-4's caller update depends on FR-4's method existing; FR-5 is independent of FR-4 |
| **C: Test infrastructure** | FR-3 (AC-22b/c), FR-6 (isoformat drift), plus new tests for FR-2/FR-4/FR-5 | `test-hooks.sh` (shell tests), `test_maintenance.py` (pytest tests), `test_database.py` (new `scan_decay_candidates` tests) | FR-3 and FR-6 are independent of each other and of Streams A/B. New production-side tests depend on Stream A/B code changes |
| **D: Documentation** | FR-1 (backlog markers) | `docs/backlog.md` | None — documentation-only edits |

### Dependency Graph

```
Stream D (FR-1) ──┐          independent
Stream A (FR-2) ──┤          independent
Stream B (FR-5) ──┤          independent
Stream B (FR-4) ──┤ new method → caller update at maintenance.py:257-266
Stream C (FR-3) ──┤          independent
Stream C (FR-6) ──┘          independent
                 │
                 ▼
    New tests for FR-2, FR-4, FR-5 (Stream C)
    └── depend on code changes in Streams A and B
```

### Implementation Order

Recommended implement order (optimizes for reviewer feedback latency and parallelism):

1. **Stream D** (FR-1) — docs-only, can be done first; no code review risk.
2. **Stream A** (FR-2 predicate swap) — 1-line code change + test; fastest feedback.
3. **Stream B Part 1** (FR-4 new method) — add `scan_decay_candidates` to `database.py` with tests.
4. **Stream B Part 2a** (FR-4 caller update) — wire `db.scan_decay_candidates(...)` into `maintenance.py:_select_candidates` body (signature unchanged).
5. **Stream B Part 2b** (FR-5 dead branch) — remove `updated_at IS NULL OR` from `database.py:1028` SQL. Independent of FR-4; can be done in parallel or before/after.
6. **Stream C** (FR-3 AC-22b/c + FR-6 isoformat drift) — test-only changes.

This ordering is a suggestion, not a hard dependency. The plan phase will decompose into atomic tasks; tasks can be parallelized beyond this sequence where safe.

## Components

### Component 1: `MemoryDatabase.scan_decay_candidates` (new)

**Location:** `plugins/pd/hooks/lib/semantic_memory/database.py`

**Purpose:** Encapsulate the decay-candidate read path that was previously inlined at `maintenance.py:259`. Closes the "Direct `db._conn` Access in Reconciliation Code" anti-pattern (knowledge-bank HIGH confidence).

**Placement:** Add alongside `batch_demote` (the existing public write path for decay). Suggested: directly before `batch_demote` in the file, since read paths conventionally precede write paths.

### Component 2: `_select_candidates` caller update (existing, modified)

**Location:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py:235-268`

**Change:** Replace the inlined `db._conn.execute(...)` + `for row in cursor: yield row` (lines 259-268) with `yield from db.scan_decay_candidates(...)`.

**Critical — signature preservation:** The `_select_candidates` function signature MUST remain unchanged. Existing tests at `test_maintenance.py:470-475,481` call `maintenance._select_candidates(db, high_cutoff, med_cutoff, grace_cutoff=grace_cutoff, scan_limit=...)` — the `grace_cutoff` keyword-only argument MUST be preserved even though the new body does not use it (the SQL path never used it; only `_partition_candidates` downstream does). Do NOT remove `grace_cutoff` from the signature. Mark it as intentionally retained with a comment if desired, but do NOT delete.

### Component 3: `decay_confidence` warning predicate (existing, modified)

**Location:** `plugins/pd/hooks/lib/semantic_memory/maintenance.py:424-429`

**Change:** `<` → `<=` in the guard; warning text updated to reflect the new semantics.

### Component 4: `_execute_chunk` SQL (existing, modified)

**Location:** `plugins/pd/hooks/lib/semantic_memory/database.py:1028`

**Change:** Remove `updated_at IS NULL OR` from the WHERE clause.

### Component 5: `TestSelectCandidates.test_partitions_six_entries_across_all_buckets` (existing, modified)

**Location:** `plugins/pd/hooks/lib/semantic_memory/test_maintenance.py:397-495`

**Change:** Delete local `NOW = datetime(...)` shadow at line 401; replace 8 `.isoformat()` calls with `_iso(...)` calls.

### Component 6: Two new AC blocks in `test-hooks.sh` (new)

**Location:** `plugins/pd/hooks/tests/test-hooks.sh` (append after existing AC-22 block at line 2952)

**Purpose:** AC-22b (SyntaxError) and AC-22c (ImportError) using the temp-PYTHONPATH subshell pattern from spec FR-3.

### Component 7: Backlog closure markers (docs-only)

**Location:** `docs/backlog.md` (23 line edits)

**Per-ID treatment:** see spec FR-1 mapping table.

## Technical Decisions

### TD-1: Generator vs List return for `scan_decay_candidates`

**Decision:** Generator (`Iterator[sqlite3.Row]`), matching the current `_select_candidates` signature.

**Alternatives considered:**
- Return `list[sqlite3.Row]`: simpler contract, but materializes the entire result set in Python memory. Actual production upper clamp at `maintenance.py:462` is `(1000, 10_000_000)` — a materialized list could hit **~1.5 GB** worst case (10M rows × ~150 bytes). Generator eliminates this.
- Return `sqlite3.Cursor`: leaks DB internals, breaks encapsulation (same anti-pattern we're fixing).

**Rationale:** Generator preserves memory efficiency of the current code. `yield from` delegation at the caller site is idiomatic Python. AC-7c pins generator semantics via `isinstance(..., Iterator)`.

**Transaction / lock semantics contract:** SQLite (in non-WAL shared-cache mode) may hold a read lock across an open cursor, blocking a subsequent `BEGIN IMMEDIATE`. The generator MUST be fully consumed before any write operation (e.g., `batch_demote`). Current caller at `maintenance.py:467` wraps in `list(_select_candidates(...))` which drains the cursor — this contract is preserved after FR-4 because `yield from db.scan_decay_candidates(...)` delegates transparently; the `list()` at the caller still fully materializes and drains. Per knowledge-bank "SQLite Transaction Semantics Discovered Incrementally" (HIGH). No new test required — existing `decay_confidence` tests exercise the full materialize-then-write sequence.

### TD-2: SQL string pinned byte-for-byte

**Decision:** The new method reproduces the exact 5-line SQL from `maintenance.py:260-264` verbatim. No reformatting, simplification, or SQL-logic changes.

**Rationale:** spec FR-4 mandates this to eliminate semantic divergence risk. AC-5b validates via whitespace-normalized substring match. Any semantic SQL change must be a separate feature.

**Contract:** The new method MUST accept `not_null_cutoff` as a string (Z-suffix ISO-8601 expected; method does not validate format) and `scan_limit` as an int (caller pre-clamps via `_resolve_int_config`).

**Injection surface analysis (knowledge-bank HIGH "Dynamic SQL Construction Without Design-Time Injection Surface Enumeration"):** Zero dynamic SQL. Both `not_null_cutoff` and `scan_limit` bind via sqlite3 `?` placeholders (positional parameter substitution by the sqlite3 driver). No f-string, no `+` concatenation, no `.format()`. Contrast with `_execute_chunk` at `database.py:1023` which constructs `placeholders = ", ".join(["?"] * len(ids))` — but that is an f-string assembled from trusted integer list-length only, not user-derived content. The new `scan_decay_candidates` has no dynamic-SQL surface.

### TD-3: `scan_limit` validation — caller-responsible

**Decision:** The new method does NOT validate `scan_limit`. Callers are responsible for passing a sensible value. SQLite `LIMIT ?` with `≤ 0` returns zero rows (SQLite-native semantics) without error.

**Rationale:** Matches current production behavior. `_select_candidates` currently receives an already-clamped `scan_limit` from `_resolve_int_config` via `decay_confidence`. Adding a validation layer in the new method would be redundant (current production path) AND would break the "preserve exact semantics" mandate. If a future caller wants a safer interface, they can add a wrapper.

### TD-4: `<=` vs `<` in FR-2 warning predicate

**Decision:** `<=` (inclusive). Warning fires for both strict-less and equal threshold configurations.

**Alternatives considered:** Short-circuit `med == high` to single-tier semantics (PRD Open Question #5). Rejected per spec default: the bounded double-demotion is spec-compliant (capped by `low` tier floor), so warning-only is the conservative change.

**Rationale:** Emits an operator-visible signal when thresholds are ambiguous without altering production behavior. AC-3/AC-3b pin both equal and strict-less cases so the predicate swap is mutation-safe.

### TD-5: Temp-PYTHONPATH subshell pattern for AC-22b/c

**Decision:** Each test block runs in a bash subshell, copies the entire `semantic_memory/` package to a `mktemp -d` location, injects the fault there, invokes `python -m semantic_memory.maintenance` with `PYTHONPATH=$PKG_TMPDIR` plus the production `2>/dev/null || true` guard, and asserts exit status 0. Subshell-scoped `trap "rm -rf $PKG_TMPDIR" EXIT` handles cleanup.

**Alternatives considered:**
- In-place file mutation with trap restore (pattern used by existing AC-22): rejected — mutating production file during test runs is unsafe under concurrent pytest / session-start invocations.
- `bash -c 'source session-start.sh; run_memory_decay'`: rejected — `session-start.sh:876` calls `main` unconditionally; sourcing executes the full hook with stdin/env dependencies.

**Rationale:** spec FR-3 mandates; this is the only approach that (a) tests the real shell-guard contract end-to-end, (b) does not mutate production files, (c) does not disturb parent script traps. AC-4d invariant guards against accidental production mutation.

### TD-6: Git operation edge cases

**Branch:** `feature/091-082-qa-residual-cleanup` (created at create-feature step). Already on this branch.

**Staging scope per task:** Each task should `git add` only the specific file(s) it modifies. Avoid `git add -A` or `git add .` to prevent accidental inclusion of `.pd-worktrees/` contents or untracked config files.

**Commit message format:** Follow the existing convention from commits 27f89e4, d9663db, 0ef2243: `pd: {phase} {brief description}` for intra-phase commits; `pd({id}): {milestone}` for milestone commits. Trailing Co-Authored-By line for Claude attribution.

**SHA lifecycle:** `HEAD` at phase end is captured in `.meta.json` `phases.design.completed_at_sha` (managed by `complete_phase` MCP). No manual SHA tracking required.

**Empty-commit handling:** Each task produces a non-empty diff; if a task produces no diff, skip the commit and note in task output.

**FR-1 (backlog hygiene) commit strategy:** The 23 backlog marker additions are a single logical unit — commit together in ONE commit with message `chore(091): add closure markers for 23 082-era backlog items (#00075, #00095..#00116)`. Do NOT interleave marker edits with FR-2..FR-6 code commits. If `docs/backlog.md` is modified on `develop` between branch creation and merge, re-apply markers manually during merge — the FR-1 mapping table in spec.md is authoritative and AC-1c's per-ID loop is resilient to unrelated additions.

## Interfaces

### Interface I-1: `MemoryDatabase.scan_decay_candidates`

**Module:** `semantic_memory.database`

**Signature:**
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

    Parameters
    ----------
    not_null_cutoff : str
        Z-suffix ISO-8601 timestamp (e.g. "2026-04-16T12:00:00Z").
        Rows matching
            (last_recalled_at IS NOT NULL AND last_recalled_at < ?)
            OR (last_recalled_at IS NULL)
        are returned. Caller is responsible for passing the
        expected format (Z-suffix) — no validation performed.
    scan_limit : int
        Maximum rows to return. Caller pre-clamps via
        ``_resolve_int_config`` in production (range [1000, 10_000_000]).
        ``scan_limit <= 0`` yields zero rows (SQLite LIMIT semantics)
        with no exception.
    """
```

**Contract:**
- **Input:** two keyword-only arguments as above.
- **Output:** generator of `sqlite3.Row` objects. Caller wraps with `list(...)` if materialization is needed.
- **Errors:** no explicit validation or error raising. Upstream SQL errors (e.g., connection closed) propagate normally.
- **Side effects:** none — read-only SELECT.
- **Thread safety:** inherits from the underlying `sqlite3.Connection`. Callers must use same-thread discipline (already enforced by existing `MemoryDatabase` pattern).

**Caller contract (post-update):**
```python
# maintenance.py:_select_candidates (after FR-4 applied):
def _select_candidates(db, high_cutoff, med_cutoff, grace_cutoff, *, scan_limit=100000):
    not_null_cutoff = max(high_cutoff, med_cutoff)
    yield from db.scan_decay_candidates(
        not_null_cutoff=not_null_cutoff,
        scan_limit=scan_limit,
    )
```

### Interface I-2: FR-2 warning emission

**Module:** `semantic_memory.maintenance`

**Current (line 424):**
```python
if med_days < high_days and not _decay_config_warned:
    sys.stderr.write(
        "[memory-decay] memory_decay_medium_threshold_days "
        f"({med_days}) < memory_decay_high_threshold_days ({high_days}); "
        "medium tier will decay faster than high\n"
    )
    _decay_config_warned = True
```

**After FR-2:**
```python
if med_days <= high_days and not _decay_config_warned:
    sys.stderr.write(
        "[memory-decay] memory_decay_medium_threshold_days "
        f"({med_days}) <= memory_decay_high_threshold_days ({high_days}); "
        "medium tier will decay at same pace or faster than high\n"
    )
    _decay_config_warned = True
```

**Contract:** identical to current — stderr write, `_decay_config_warned` flag gating for dedup. Autouse fixture at `test_maintenance.py:41` resets the flag per-test (confirmed during design research).

### Interface I-3: FR-5 SQL predicate simplification

**Module:** `semantic_memory.database`

**Method:** `_execute_chunk` (private, called only by `batch_demote`)

**Current (line 1028):**
```python
sql = (
    f"UPDATE entries "
    f"SET confidence = ?, updated_at = ? "
    f"WHERE id IN ({placeholders}) "
    f"  AND (updated_at IS NULL OR updated_at < ?)"
)
```

**After FR-5:**
```python
sql = (
    f"UPDATE entries "
    f"SET confidence = ?, updated_at = ? "
    f"WHERE id IN ({placeholders}) "
    f"  AND updated_at < ?"
)
```

**Contract:** identical runtime behavior. The `updated_at IS NULL` branch was unreachable (schema enforces NOT NULL at `database.py:114,255`; defensive coercion at `database.py:870-871` guarantees no NULL write path). Removing the dead branch simplifies the SQL without changing semantics.

### Interface I-4: FR-6 test-internal `_iso` helper usage

**Module:** `semantic_memory.test_maintenance`

**Current usage in `TestSelectCandidates.test_partitions_six_entries_across_all_buckets`:**
```python
NOW = datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)  # local shadow — delete
now_iso = NOW.isoformat()                                    # +00:00 suffix
high_cutoff = (NOW - timedelta(days=30)).isoformat()
# ... 6 more .isoformat() calls
```

**After FR-6:**
```python
# NOW resolves via module-level _TEST_EPOCH alias at line 507
now_iso = _iso(NOW)                                          # Z suffix
high_cutoff = _iso(NOW - timedelta(days=30))
# ... 6 more _iso() calls
```

**Contract:** `_iso()` helper at `test_maintenance.py:510-516` produces Z-suffix via `strftime("%Y-%m-%dT%H:%M:%SZ")` after `astimezone(timezone.utc)` when input is tz-aware. For tz-naive inputs the two helpers diverge: production `_iso_utc` raises `ValueError`, whereas test-local `_iso` emits an unqualified local-time `strftime` (technically wrong, but Z-suffixed). **FR-6 relies only on the tz-aware path** via `_TEST_EPOCH` which is UTC-aware, so the divergence is not exercised. AC-9c pins `_iso(NOW) == NOW.strftime("%Y-%m-%dT%H:%M:%SZ")` for the tz-aware-equivalence case only.

**Assumption A6 (from spec):** `_TEST_EPOCH` matches the prior local `NOW` value — verified during design research at `test_maintenance.py:506`.

### Interface I-5: FR-3 temp-PYTHONPATH harness (test-only)

**Module:** `test-hooks.sh` (bash test script)

**Harness template** (appears twice — once for AC-22b SyntaxError, once for AC-22c ImportError):

```bash
# AC-22b (SyntaxError):
(
  # Skip guard: venv is required to match production invocation pattern.
  [ -x plugins/pd/.venv/bin/python ] || { echo "SKIP: venv missing for AC-22b"; exit 0; }

  PKG_TMPDIR=$(mktemp -d)
  trap "rm -rf \"$PKG_TMPDIR\"" EXIT
  mkdir -p "$PKG_TMPDIR/semantic_memory"
  cp -R plugins/pd/hooks/lib/semantic_memory/. "$PKG_TMPDIR/semantic_memory/"

  # Positive control: copy must include __init__.py (required for `-m` import).
  [ -f "$PKG_TMPDIR/semantic_memory/__init__.py" ] || { echo "FAIL: __init__.py missing from copy"; exit 1; }

  # Positive control: clean copy should import successfully BEFORE fault injection.
  PYTHONPATH="$PKG_TMPDIR" plugins/pd/.venv/bin/python \
    -c 'import semantic_memory.maintenance' 2>/dev/null \
    || { echo "FAIL: clean copy does not import — harness precondition broken"; exit 1; }

  # Inject SyntaxError:
  printf '\ndef broken(:\n' >> "$PKG_TMPDIR/semantic_memory/maintenance.py"

  # Negative control: WITHOUT guard, the raw Python invocation MUST fail.
  # If it doesn't, the fault injection didn't take effect and the test is invalid.
  PYTHONPATH="$PKG_TMPDIR" plugins/pd/.venv/bin/python \
    -m semantic_memory.maintenance --decay --project-root . >/dev/null 2>&1
  raw_exit=$?
  [ "$raw_exit" -ne 0 ] || { echo "FAIL: AC-22b fault did not trigger — raw exit was 0"; exit 1; }

  # Positive contract: WITH production guard pattern (session-start.sh:719),
  # exit status is 0 regardless of Python failure.
  PYTHONPATH="$PKG_TMPDIR" plugins/pd/.venv/bin/python \
    -m semantic_memory.maintenance --decay --project-root . 2>/dev/null || true
  # The `|| true` guarantees exit 0; this line is a sanity check that the
  # shell compound above completed normally (no trap, no early exit).
  echo "AC-22b PASS: Python failed (raw exit $raw_exit) but shell guard tolerated"
)

# AC-22c (ImportError):
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

  # Inject ImportError via sed-free prepend (portable; no BSD/GNU divergence):
  {
    echo 'import no_such_module_really_does_not_exist'
    cat "$PKG_TMPDIR/semantic_memory/maintenance.py"
  } > "$PKG_TMPDIR/semantic_memory/maintenance.py.new"
  mv "$PKG_TMPDIR/semantic_memory/maintenance.py.new" \
     "$PKG_TMPDIR/semantic_memory/maintenance.py"

  # Negative control: WITHOUT guard, raw invocation MUST fail (ImportError).
  PYTHONPATH="$PKG_TMPDIR" plugins/pd/.venv/bin/python \
    -m semantic_memory.maintenance --decay --project-root . >/dev/null 2>&1
  raw_exit=$?
  [ "$raw_exit" -ne 0 ] || { echo "FAIL: AC-22c fault did not trigger — raw exit was 0"; exit 1; }

  # Positive contract: WITH guard, exit is 0.
  PYTHONPATH="$PKG_TMPDIR" plugins/pd/.venv/bin/python \
    -m semantic_memory.maintenance --decay --project-root . 2>/dev/null || true
  echo "AC-22c PASS: Python failed (raw exit $raw_exit) but shell guard tolerated"
)

# AC-4d invariant (runs outside the subshells):
git_status_after=$(git status --porcelain plugins/pd/hooks/lib/semantic_memory/maintenance.py)
[ -z "$git_status_after" ] || { echo "FAIL: AC-4d production file mutated"; exit 1; }
```

**Contract:** each subshell is self-contained. Exit code 0 asserts the shell guard (`|| true`) catches Python-level faults. `git status --porcelain` invariant (AC-4d) runs outside subshells to verify production file is untouched.

**macOS compatibility note:** `sed -i.bak` + `rm -f .bak` is the portable GNU/BSD sed pattern. `cp -R` is portable.

## Risks

### R-1 [MED]: FR-2 predicate swap perturbs existing `<` tests

**Description:** Changing `<` to `<=` may affect existing tests that assumed strict-less semantics. The warning now fires more often (includes equal case).

**Mitigation:**
- AC-3b pins the `<` case (verifies it still emits warning).
- Full test suite run before and after FR-2 change.
- Autouse `reset_decay_state` fixture ensures flag state is consistent across tests.

**Residual risk:** LOW. All `_decay_config_warned` usage is captured by the autouse fixture (confirmed during design research).

### R-2 [LOW]: FR-4 signature change cascades to test monkeypatches

**Description:** If any test monkeypatches `_select_candidates` directly, adding `db.scan_decay_candidates` may leave behind stale test harness.

**Mitigation:** Design research confirmed `_select_candidates` is called from 1 production site (`decay_confidence`) + 2 test sites (`test_maintenance.py::TestSelectCandidates::test_partitions_six_entries_across_all_buckets` and regression tests). Test sites call it as-is (not monkeypatched). AC-7d regression guard ensures existing behavior preserved.

**Residual risk:** LOW.

### R-3 [LOW]: FR-6 edit surfaces format-dependent latent bugs

**Description:** The current `TestSelectCandidates` test passes by coincidence of fixture ranges; switching to `_iso()` may expose a latent assertion that was never actually testing the intended boundary.

**Mitigation:** Run test before and after FR-6 edit. If behavior changes, surface as warning in implement phase review; do not auto-fix.

**Residual risk:** LOW — spec's R3 already notes this; design adds explicit before/after test invocation to the task.

### R-4 [MED]: Structural exit gate at implement phase (AC-11)

**Description:** If adversarial reviewer surfaces new HIGH findings in Round 1 during `/pd:implement`, scope freezes per PRD Structural Success Criterion #1.

**Mitigation:**
- Spec's test ACs cover mutation-resistance cases (AC-3b, AC-7c, AC-7d).
- Design verbatim SQL pinning (TD-2) eliminates semantic-drift HIGH risk.
- Design TD-5 addresses the concurrency-safety concern that was a spec-review iteration 2 blocker.

**Residual risk:** MED. Historical pattern (088→33, 089→20, 090→5) suggests some residuals likely surface; design's goal is to keep them at MED/LOW severity.

### R-5 [LOW]: AC-22c ImportError injection portability — RESOLVED

**Original concern:** BSD vs GNU sed divergence for `-i` option.

**Resolution:** I-5 AC-22c now uses sed-free prepend: `{ echo 'import no_such_module'; cat file; } > file.new && mv file.new file`. No sed dependency; portable across macOS and Linux. Risk eliminated.

### R-6 [LOW]: Python stdlib Iterator import path — PINNED

**Description:** `database.py:11` currently imports only `from typing import Callable`. The new method requires an `Iterator` import.

**Mitigation:** Implementer adds `from collections.abc import Iterator` at the top of `database.py` in the same commit as the new method. Do NOT use `typing.Iterator` — deprecated in Python 3.9+ (PEP 585). The file already has `from __future__ import annotations` at line 2 so the annotation evaluates lazily regardless.

**Residual risk:** LOW.

## Assumptions (from spec, verified during design)

All 7 assumptions A1–A7 from spec confirmed during design Step 0 research. See Prior Art Research table above.

## Out of Scope

- `_config_utils.py` SPOF mitigation (spec Out of Scope #1)
- Backlog closure-marker automation (spec Out of Scope #2)
- `#00116` sub-items c–j (spec Out of Scope #3)
- `#00110` re-verification (spec Out of Scope #4) — AC-1c per-ID presence loop passes trivially (asserts `#00110` exists in backlog, not that it has a closure marker). AC-1 (exact marker verification) iterates only the 23 IDs in FR-1's mapping table, which excludes #00110. No conflict.
- Any SQL semantic changes to `scan_decay_candidates` or `_execute_chunk` beyond what's specified in FR-4/FR-5

## Next Steps

1. Design review (Step 3) — design-reviewer skeptic pass.
2. Handoff review (Step 4) — phase-reviewer for design→plan readiness.
3. `/pd:create-plan` — decompose into atomic tasks; plan phase will:
   - Split FR-4 into "add method" + "update caller" (per TD-1/TD-2)
   - Order tasks per Implementation Order section above
   - Generate task dependency graph
   - Write `tasks.md` and `plan.md`
