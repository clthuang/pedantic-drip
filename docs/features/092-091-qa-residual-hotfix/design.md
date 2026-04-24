# Design: Feature 092 — 091 QA Residual Hotfix

## Status
- Created: 2026-04-20
- Phase: design
- Upstream: `docs/features/092-091-qa-residual-hotfix/spec.md`

## Prior Art

Spec covers 9 surgical fixes with full before/after code snippets and binary-verifiable ACs. Design phase adds:
- Architecture overview (work streams + dependency graph)
- Technical decision records (TDs) capturing the hard choices from advisors
- Interfaces (I-1..I-5) consolidating signatures/contracts from spec
- Risk matrix (carries R-1..R-4 from PRD)

No external research needed — all fixes target existing internal code with clear mutation paths.

## Architecture Overview

9 fixes organized into 4 streams:

| Stream | Items | Touch points | Dependencies |
|--------|-------|--------------|--------------|
| **A: Production-code hardening** | FR-1 clamp, FR-5 regex validate, FR-8 batch_demote guard | `database.py` | None (independent) |
| **B: Test harness hardening** | FR-2 trap+mktemp, FR-3 AC-4d fix, FR-4 cp -R -P, FR-7 helper extraction, FR-9 PASS markers | `test-hooks.sh` | FR-2/3/4 land first; FR-7 helper absorbs them |
| **C: Documentation** | FR-6 spec clamp values | `docs/features/091-082-qa-residual-cleanup/spec.md` | None |
| **D: New tests** | AC-1, AC-7, AC-10 pytests | `test_database.py` | Depends on Stream A code landing |

### Dependency Graph

```
Stream C (FR-6) ──┐  independent (docs only)
Stream A (FR-1) ──┤  independent
Stream A (FR-5) ──┤  independent
Stream A (FR-8) ──┤  independent
Stream B (FR-2) ──┐
Stream B (FR-3) ──┼──▶ Stream B (FR-7 helper absorbs) ──▶ Stream B (FR-9 marker added to helper)
Stream B (FR-4) ──┘
                                     │
Stream D (AC-1/7/10) ────────────────┼──▶ all stream A code landed
                                     ▼
                          Quality gates (pytest + test-hooks.sh + validate.sh + pd:doctor)
                                     ▼
                          Post-merge adversarial QA (AC-12 / structural exit gate)
```

## Technical Decisions

### TD-1: Clamp-not-raise for FR-1 `scan_limit < 0`

**Decision:** `scan_limit = max(0, scan_limit)` at method entry.

**Alternatives rejected:**
- Raise `ValueError`: propagation hazard — escapes `decay_confidence`'s `except sqlite3.Error` block silently (no diagnostic). Untested.
- Clamp to upper bound: no upstream context to pick a reasonable upper; zero clamp is sufficient to eliminate the DoS vector.

**Rationale:** Pre-mortem + antifragility advisors converged on this. Matches docstring intent ("yields zero rows"). Production caller already clamps upstream via `_resolve_int_config` so never hits negative.

### TD-2: Log-and-skip for FR-5 invalid `not_null_cutoff`

**Decision:** On regex mismatch, write stderr warning + return empty generator. No exception.

**Alternatives rejected:**
- Raise `ValueError`: same propagation hazard as TD-1. Untested path through `decay_confidence`.
- Clamp/sanitize to a default: no sensible default; silently returning empty is already the safe SQL behavior.

**Rationale:** Consistency with TD-1 clamp philosophy. Stderr warning surfaces to operator on direct invocation / in pytest capsys; absorbed by session-start's `2>/dev/null` in production (acceptable because production caller provably cannot produce bad cutoffs).

### TD-3: Raise-not-skip for FR-8 empty `now_iso` (asymmetry with TD-2)

**Decision:** `if not ids: return 0` kept; then `if not now_iso: raise ValueError(...)`.

**Rationale for asymmetry (corrected after design-review iter 1 flagged wrong ground truth):** Both `_select_candidates → scan_decay_candidates` AND `batch_demote` are called inside the SAME `try: … except sqlite3.Error:` block at `maintenance.py:464-500`. ValueError escapes that handler identically in both cases. The asymmetry is NOT about call-path topology — it is about **read-vs-write semantics**:

- `scan_decay_candidates` is a **READ** returning a generator. Empty result = "no candidates found" = semantically safe (decay loop no-ops, no data corruption). Silent log-and-skip on invalid input is defensible: the worst outcome is a tick with zero demotions, which is indistinguishable from a valid-but-empty DB.
- `batch_demote` is a **WRITE**. Silently accepting empty `now_iso` would bind `updated_at=""` into the entries table — downstream queries (`updated_at < ?` guards in intra-tick idempotency) break against empty strings in ways hard to diagnose. Raising forces the bug to surface at the boundary rather than poisoning persistent state.

So: log-and-skip is safe for reads (no data loss); raise is safer for writes (prevents data corruption). Both propagate past `except sqlite3.Error` identically; `_main` at `maintenance.py:606` wraps in try/**finally** (not try/except), and session-start's `2>/dev/null` absorbs the traceback — but stderr in direct invocation / pytest capsys still surfaces the diagnostic. Empty-ids short-circuit preserved to avoid breaking empty-list callers.

### TD-4: Explicit guards (NOT `set -e`, NOT `set -u`) for FR-2 mktemp hardening

**Decision:** `PKG_TMPDIR=$(mktemp -d) || { log_fail ...; exit 1; }` + `[ -n ]` + `[ -d ]` checks. `set +e` inside subshell (matches pre-092 pattern). Each setup step has explicit `|| { echo "FAIL: ..."; exit 1; }` override.

**Alternatives rejected:**
- `set -eo pipefail`: `set -e` terminates the subshell when the negative-control Python invocation returns non-zero (which is its contract — we are injecting a fault). Subshell exits BEFORE `raw_exit=$?` can capture the exit code, breaking the entire fault-injection test pattern.
- Add `set -u`: bash 3.2 portability hazard (same class as the `declare -A` issue from 091 plan-review iter 3). `raw_exit` and other conditionally-set variables could trigger spurious failures.

**Rationale:** Pre-mortem + antifragility recommend explicit guards over shell modes. `set +e` preserves the old idiomatic fault-injection pattern (capture deliberately-non-zero exit codes). Explicit `|| echo FAIL; exit 1` on each setup step provides the same defense as `set -e` would for setup failures, while keeping the negative-control contract intact.

### TD-5: Single-quoted `trap` body for deferred expansion

**Decision:** `trap 'rm -rf -- "$PKG_TMPDIR"' EXIT` (single-quoted).

**Contrast with current buggy pattern:** `trap "rm -rf \"$PKG_TMPDIR\"" EXIT` (double-quoted) — expands at trap-set time. If `mktemp -d` failed and `$PKG_TMPDIR` was empty, old trap registers as `rm -rf ""` (harmless), but the subsequent `mkdir -p "$PKG_TMPDIR/semantic_memory"` becomes `mkdir -p /semantic_memory` (filesystem root). Single-quoted trap body defers expansion until trap fires, and the three entry guards ensure `$PKG_TMPDIR` is always valid before the trap can reference it.

The `--` after `rm -rf` guards against `$PKG_TMPDIR` that starts with `-` (mktemp-d output is typically `/var/folders/...` so very unlikely, but defensive).

### TD-6: Helper extraction with fault-injection parametrization

**Decision:** `_run_maintenance_fault_test` takes 4 args: test_label, t7_tag, inject_mode ("append"|"prepend"), inject_payload. Case/esac branches on inject_mode.

**Alternatives considered:**
- Two separate helpers (`_run_append_fault` + `_run_prepend_fault`): less DRY, but simpler control flow. Rejected — inject mode is the ONLY difference; a single 4-line case/esac is cleaner.
- Callback-based injection (helper accepts a function pointer): over-engineered for 2 call sites.

**Rationale:** Matches "one parameter controls the only variation" surgical pattern. Two DIFFERENT test function call sites (`test_memory_decay_syntax_error_tolerated` + `test_memory_decay_import_error_tolerated`) ensure helper bugs fail both tests loudly, preventing silent-pass tautology.

### TD-7: AC-5 fire-test is MANUAL (not automated)

**Decision (resolving phase-reviewer suggestion):** AC-5's fire-test ("manually dirty `maintenance.py`, verify AC-4d invariant actually FAILS") is a ONE-TIME manual verification during implementation, NOT a recurring automated pytest.

**Rationale:** Automating the fire-test would require git-index manipulation in pytest (complex + fragile). The invariant's correctness is a static property of the one-line fix (`git -C "$(git rev-parse --show-toplevel)" ...`). Manual verification at implementation time + code review is sufficient. Documented in tasks.md as an implementer checklist item.

## Interfaces

### I-1: `MemoryDatabase.scan_decay_candidates` (FR-1 + FR-5)

**Module:** `semantic_memory.database`

**Updated contract:**
```python
def scan_decay_candidates(
    self,
    *,
    not_null_cutoff: str,
    scan_limit: int,
) -> Iterator[sqlite3.Row]:
    """Yield candidate rows for decay confidence processing.

    Feature 092 (FR-5): not_null_cutoff must match Z-suffix ISO-8601
    (YYYY-MM-DDTHH:MM:SSZ). On mismatch: stderr warning + empty return
    (no exception — consistent with FR-1 clamp philosophy). Production
    caller (_select_candidates via _iso_utc) always produces Z-suffix
    so never triggers the warning path.

    Feature 092 (FR-1): scan_limit < 0 clamped to 0 (NOT raises) to
    avoid SQLite LIMIT -1 = unlimited DoS vector. Zero-row generator
    preserves "always returns iterator" contract.
    """
```

**Contract change** (vs 091 baseline):
- Invalid `not_null_cutoff` → empty generator + stderr (was: no validation; SQL would execute with wrong data).
- `scan_limit < 0` → zero rows (was: SQL LIMIT -1 = unlimited).

### I-2: `MemoryDatabase.batch_demote` (FR-8)

**Module:** `semantic_memory.database`

**Updated contract:**
```python
def batch_demote(self, ids, new_confidence, now_iso):
    """Feature 092 (FR-8): empty now_iso raises ValueError ONLY when
    ids is non-empty (empty-ids short-circuit preserved)."""
    if not ids:
        return 0  # UNCHANGED
    if not now_iso:
        raise ValueError("now_iso must be non-empty ISO-8601 timestamp")
    # ... existing new_confidence validation + SQL body
```

### I-3: `_run_maintenance_fault_test` helper (FR-7)

**Module:** `test-hooks.sh`

**Signature + contract:** 4-argument bash function (label, t7_tag, inject_mode, inject_payload). Full pseudocode in spec FR-7. Inject mode "append" uses `printf '%s' "$payload" >> file`; "prepend" uses `{ echo "$payload"; cat file; } > tmp && mv tmp file`.

**Safety invariants:**
- `set +e` inside subshell (NOT `-e` — negative-control Python invocation deliberately returns non-zero; `set -e` would terminate before `raw_exit=$?` captures the exit). No `-u` — bash 3.2 portability.
- Triple guard after `mktemp -d`: failure-check, non-empty-check, is-directory-check.
- Single-quoted trap body for deferred expansion.
- Each setup step (mkdir, cp, append/prepend, clean-import) has explicit `|| { echo "FAIL: ..."; exit 1; }` so setup failures surface with diagnostic.
- Explicit `echo "AC-22X PASS: ..."` marker INSIDE subshell (where `raw_exit` is live).

### I-4: `_ISO8601_Z_PATTERN` module-level regex (FR-5)

**Module:** `semantic_memory.database`

```python
_ISO8601_Z_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
```

**Placement:** after module imports, before class definitions. Compiled once at module load.

### I-5: Feature-091 spec FR-4 clamp values (FR-6)

**File:** `docs/features/091-082-qa-residual-cleanup/spec.md`

Two edits:
- Line 49: `[1000, 500000]` → `[1000, 10_000_000]`
- Line 139: `[1000, 500000]` → `[1000, 10_000_000]`

Both match actual `_resolve_int_config` clamp at `maintenance.py:462`.

## Risks

Carried from PRD, plus the phase-reviewer R-5 suggestion:

- **R-1 [LOW]** FR-5 regex rejects `+00:00`-suffixed valid UTC strings (intentional — matches `_iso_utc` Z-suffix contract). Mitigated by `test_scan_decay_candidates_matches_iso_utc_output`.
- **R-2 [LOW]** FR-7 helper extraction introduces one shared dependency. Mitigated by `set +e` + explicit `|| { echo FAIL; exit 1; }` guards on each setup step + two different test function call sites (helper bugs fail both loudly).
- **R-3 [LOW]** FR-9 explicit echo markers create output-format contract. Acceptable — matches DoD intent.
- **R-4 [MED]** Structural exit gate (AC-12) requires 4-reviewer post-merge QA dispatch. Execution burden ~10 min. Deferring means pattern recurrence.
- **R-5 [LOW]** FR-5 uses log-and-skip, FR-8 uses raise — intentional asymmetry per TD-3 (different call-path contexts). Documented here for design-phase awareness; implementer must respect the asymmetry.
- **R-6 [LOW]** TD-7 fire-test is manual (one-time). Implementer must execute + document in implementation-log.

## Out of Scope

- Pre-release adversarial QA gate in `/pd:finish-feature` (PRD Open Q #1) — separate backlog entry.
- 15 LOW/test-gap findings from 091 post-release QA (#00202–#00216).

## Implementation Order

Recommended (parallelizable within each bullet):

1. **Stream A (parallel):** FR-1 (clamp + docstring), FR-5 (regex + log-and-skip), FR-8 (empty now_iso raise after empty-ids short-circuit).
2. **Stream D tests (parallel, depend on A):** AC-1/AC-7/AC-10 pytests.
3. **Stream C (independent):** FR-6 spec clamp edits.
4. **Stream B:** FR-2 → FR-3 → FR-4 → FR-7 helper → FR-9 marker (sequential within the helper; iterate once).
5. **Quality gates:** pytest suite, test-hooks.sh, validate.sh.
6. **Post-merge:** 4-reviewer adversarial QA (AC-12).

Given scope (~9 small changes), direct-orchestrator (no implementer subagent) is appropriate per 090/091 pattern.
