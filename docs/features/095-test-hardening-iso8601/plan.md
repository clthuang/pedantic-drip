# Plan: Feature 095 — Test-Hardening Sweep for `_ISO8601_Z_PATTERN`

## Status
- Created: 2026-04-29
- Phase: create-plan
- Upstream: design.md (6 TDs incl renumbered, 4 components, 6 interfaces, 5 risks); spec.md (14 ACs incl AC-13a/13b, 5 FRs, 4 NFRs)

## Architecture Summary

One file touched, ~80 net LOC, single atomic commit. Direct-orchestrator pattern (091/092/093/094 surgical-feature template). Test-only feature — zero production code changes (AC-12).

```
plugins/pd/hooks/lib/semantic_memory/test_database.py    [edit only, +~80 LOC, +17 parametrized assertions]
```

All test code already drafted in design.md FR-1/FR-2/FR-3 + interfaces I-1..I-6 — plan executes verbatim.

## Stage 0 — Capture Baselines + verify feature 094 dispatch format (BEFORE any edits)

```bash
PRE_HEAD=$(git rev-parse HEAD)
PRE_LINES_TD=$(wc -l < plugins/pd/hooks/lib/semantic_memory/test_database.py)
PRE_PYTEST_PASS=$(plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q 2>&1 | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')

# Wider regression sentinel for T7 cross-check (per plan-reviewer iter 1 suggestion 6):
PRE_PYTEST_PASS_WIDE=$(plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ -q 2>&1 | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || echo "unknown")

# Expected baselines (verified at plan-write time):
# PRE_HEAD = current feature/095 HEAD
# PRE_LINES_TD = ~3500 (test_database.py)
# PRE_PYTEST_PASS = 197

# Verify feature 094 dispatch diff format (per plan-reviewer iter 1 warning 2):
# qa-gate-procedure.md §1 line 19 says: `git diff {pd_base_branch}...HEAD` (NO flags) — emits unified diff with `+++ b/path` headers.
# Confirm:
grep -nE 'git diff \{pd_base_branch\}\.\.\.HEAD' docs/dev_guides/qa-gate-procedure.md
# Expected: line 19 + line 316 — both un-flagged form (NOT --stat or --name-only).
# This validates AC-13b's `+++ b/test_database.py` marker assumption.
```

**Stage 0 DoD:**
- All 4 baselines captured (PRE_HEAD, PRE_LINES_TD, PRE_PYTEST_PASS, PRE_PYTEST_PASS_WIDE)
- `PRE_PYTEST_PASS = 197` (else pause, investigate)
- grep for `git diff {pd_base_branch}...HEAD` finds line 19 + 316 in qa-gate-procedure.md (validates AC-13b's `+++ b/` marker assumption — the un-flagged form emits unified diff)

## Implementation Order — TDD-aware

This feature is purely additive tests; there's no separate "RED" step in the traditional sense (the test code IS the implementation). However, we order tasks so module-level imports come first (so subsequent test edits compile), then existing-block extensions (low-risk), then new methods (additive), then quality gates.

### T1 — Module-level imports (`test_database.py:15-16`)

**Old text** (line 15, exact verbatim):
```
from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query
```

**New text** (replace line 15, add line 16):
```
from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query, _ISO8601_Z_PATTERN
import inspect
```

**T1 DoD:**
- `grep -qE '^from semantic_memory.database import.*_ISO8601_Z_PATTERN' plugins/pd/hooks/lib/semantic_memory/test_database.py`
- `grep -qE '^import inspect$' plugins/pd/hooks/lib/semantic_memory/test_database.py`

### T2 — Remove redundant inline import (line ~2041)

**Old text** (find inside `test_iso_utc_output_always_passes_hardened_pattern` body):
```python
        from semantic_memory.database import _ISO8601_Z_PATTERN
```

**New text:** delete the line (body now uses module-level import from T1).

**T2 DoD:**
- `grep -c 'from semantic_memory.database import _ISO8601_Z_PATTERN' plugins/pd/hooks/lib/semantic_memory/test_database.py` returns exactly **1** (only the line-15 module-level import).

### T3 — Extend `test_batch_demote_rejects_invalid_now_iso` parametrize (FR-2 + FR-4)

**File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`, inside `class TestBatchDemote` (around line 2102).

**Old text** (the existing `@pytest.mark.parametrize` decorator + 8 cases — exact form per code-explorer line 2102-2110):
```python
    @pytest.mark.parametrize("invalid_now_iso,case_name", [
        ("", "empty"),
        ("   ", "whitespace-only"),
        ("\n", "newline-only"),
        ("​", "zero-width-space"),
        ("10000-01-01T00:00:00Z", "5-digit-year-breaks-sqlite-lex-collation"),
        ("2026-04-20T00:00:00Z\n", "trailing-newline"),
        ("２０２６-04-20T00:00:00Z", "unicode-digits"),
        ("2026-04-20T00:00:00+00:00", "plus-offset-not-Z-suffix"),
    ])
```

**New text** (add 2 cases + add `ids=` derived from cases tuple per design TD-6 — eliminates dual-list drift):
```python
    _INVALID_NOW_ISO_CASES = [
        ("", "empty"),
        ("   ", "whitespace-only"),
        ("\n", "newline-only"),
        ("​", "zero-width-space"),
        ("10000-01-01T00:00:00Z", "5-digit-year-breaks-sqlite-lex-collation"),
        ("2026-04-20T00:00:00Z\n", "trailing-newline"),
        ("2026-04-20T00:00:00Z ", "trailing-space"),       # NEW (#00251)
        ("2026-04-20T00:00:00Z\r\n", "trailing-crlf"),     # NEW (#00251)
        ("２０２６-04-20T00:00:00Z", "unicode-digits"),
        ("2026-04-20T00:00:00+00:00", "plus-offset-not-Z-suffix"),
    ]

    @pytest.mark.parametrize(
        "invalid_now_iso,case_name",
        _INVALID_NOW_ISO_CASES,
        ids=[c for _, c in _INVALID_NOW_ISO_CASES],
    )
```

**Drift safety (per design TD-6 + plan-reviewer iter 1 warning 4):** `ids=[c for _, c in _INVALID_NOW_ISO_CASES]` derives ids from the tuple list — adding/reordering a case automatically updates the ids without manual sync.

**T3 DoD:**
- pytest `-v` output for `test_batch_demote_rejects_invalid_now_iso` shows 10 cases (was 8) with descriptive ids
- All 10 cases PASS
- AC-7 + AC-10 satisfied (cross-call-site parity #00251 + ids retrofit per FR-4)

### T4 — Add `test_pattern_rejects_partial_unicode_injection` to `TestScanDecayCandidates`

**File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
**Insertion anchor (verbatim quote of last line of `test_pattern_rejects_trailing_whitespace` body, line 2084):**
```
        assert "format violation" in captured.err
```
Insert immediately after this line (preserve 4-space class-body indentation; class boundary at line 2087 begins `class TestBatchDemote`). New text indents at 4 spaces (method-level inside `TestScanDecayCandidates`).

**New text** (paste the full method body from spec FR-3 / design I-6):
```python
    @pytest.mark.parametrize("partial_unicode_input,case_name", [
        ("2026-01-0１T00:00:00Z", "day-pos"),       # fullwidth 1 at day-units
        ("2026-01-01T0１:00:00Z", "hour-pos"),      # fullwidth 1 at hour-units
        ("2026-01-01T00:0１:00Z", "minute-pos"),    # fullwidth 1 at minute-units
        ("2026-01-01T00:00:0１Z", "second-pos"),    # fullwidth 1 at second-units
    ], ids=["day-pos", "hour-pos", "minute-pos", "second-pos"])
    def test_pattern_rejects_partial_unicode_injection(
        self, db: MemoryDatabase, capsys, partial_unicode_input, case_name,
    ):
        """Closes #00252 — pin rejection of mid-string single Unicode digit injection."""
        list(db.scan_decay_candidates(partial_unicode_input, scan_limit=10))
        captured = capsys.readouterr()
        assert "format violation" in captured.err, (
            f"[{case_name}] scan_decay_candidates must reject partial Unicode injection"
        )
```

**T4 DoD:**
- pytest `-v` output for `test_pattern_rejects_partial_unicode_injection` shows 4 PASS cases with descriptive ids
- AC-8 satisfied

### T5 — Add `test_batch_demote_rejects_partial_unicode_injection` to `TestBatchDemote`

**File:** same.
**Insertion anchor (verbatim quote of last line of `test_batch_demote_rejects_invalid_now_iso` body, line 2122):**
```
            db.close()
```
This is the `finally` close inside `test_batch_demote_rejects_invalid_now_iso`. Insert new method immediately after the blank line that follows. New text indents at 4 spaces (method inside `TestBatchDemote`).

**New text** (paste from spec FR-3 / design I-6):
```python
    @pytest.mark.parametrize("partial_unicode_input,case_name", [
        ("2026-01-0１T00:00:00Z", "day-pos"),
        ("2026-01-01T0１:00:00Z", "hour-pos"),
        ("2026-01-01T00:0１:00Z", "minute-pos"),
        ("2026-01-01T00:00:0１Z", "second-pos"),
    ], ids=["day-pos", "hour-pos", "minute-pos", "second-pos"])
    def test_batch_demote_rejects_partial_unicode_injection(self, partial_unicode_input, case_name):
        db = MemoryDatabase(":memory:")
        try:
            with pytest.raises(ValueError, match="Z-suffix ISO-8601"):
                db.batch_demote(["x"], "medium", partial_unicode_input)
        finally:
            db.close()
```

**T5 DoD:**
- pytest `-v` output for `test_batch_demote_rejects_partial_unicode_injection` shows 4 PASS cases
- AC-9 satisfied

### T6 — Add `TestIso8601PatternSourcePins` class (5 methods)

**File:** same.
**Insertion anchor (verbatim quote of next class start, line 2207 pre-edit):**
```
class TestExecuteChunkSeam:
```
Insert new `TestIso8601PatternSourcePins` class **before** this line, with one blank line above and below the new class block. New class starts at column 0 (module-level). Note that line 2207 will shift by the new-class LOC after edit; the anchor is stable at "before `class TestExecuteChunkSeam:`".

**New text** (paste full class from spec FR-1 / design I-1..I-4):
```python
class TestIso8601PatternSourcePins:
    """Source-level mutation-resistance pins for _ISO8601_Z_PATTERN.

    Closes feature 093 post-release adversarial QA gaps #00246-#00250.
    Per advisor consensus, uses _ISO8601_Z_PATTERN.pattern / .flags (stable Python 3.7+
    public attrs) where signal is equivalent; uses inspect.getsource() only for call-site
    .fullmatch() pin (#00250) where call-form IS the contract.
    """

    def test_pattern_source_uses_explicit_digit_class(self):
        """Closes #00246 — pin literal `[0-9]` in pattern source, NOT `\\d`."""
        assert '[0-9]' in _ISO8601_Z_PATTERN.pattern, \
            "_ISO8601_Z_PATTERN.pattern must use explicit [0-9] character class for ASCII-only matching"
        assert r'\d' not in _ISO8601_Z_PATTERN.pattern, \
            "_ISO8601_Z_PATTERN.pattern must NOT use \\d (Unicode-digit-permissive in Python 3 str patterns)"

    def test_pattern_compiled_with_re_ascii_flag(self):
        """Closes #00247 — pin re.ASCII flag presence (defense-in-depth)."""
        assert bool(_ISO8601_Z_PATTERN.flags & re.ASCII), \
            "_ISO8601_Z_PATTERN must be compiled with re.ASCII flag (defense-in-depth against future class expansion)"

    @pytest.mark.parametrize("unicode_input,case_name", [
        ("２０２６-04-20T00:00:00Z", "fullwidth-year"),
        ("٢٠٢٦-04-20T00:00:00Z", "arabic-indic-year"),
        ("२०२६-04-20T00:00:00Z", "devanagari-year"),
    ], ids=["fullwidth", "arabic-indic", "devanagari"])
    def test_pattern_rejects_unicode_digits_directly(self, unicode_input, case_name):
        """Closes #00248 — direct pattern-object Unicode rejection, decoupled from call sites.

        Catches combined mutation: swap [0-9] → \\d AND drop re.ASCII flag (which would
        re-introduce #00219 Unicode-digit bypass). Behavior tests via call sites also
        catch this combined mutation, but this test catches it without needing a DB.
        """
        assert _ISO8601_Z_PATTERN.fullmatch(unicode_input) is None, \
            f"[{case_name}] Pattern must reject Unicode-digit input directly"

    @pytest.mark.parametrize("method", [
        MemoryDatabase.scan_decay_candidates,
        MemoryDatabase.batch_demote,
    ], ids=["scan_decay_candidates", "batch_demote"])
    def test_call_sites_use_fullmatch_not_match(self, method):
        """Closes #00250 + #00249 — pin .fullmatch() call-form at both call sites,
        and confirm both share _ISO8601_Z_PATTERN as single source of truth (no local re.compile).

        This is the only test in this class that uses inspect.getsource() — required because
        the contract IS the call-form, not an attribute of the pattern object.
        """
        src = inspect.getsource(method)
        assert '_ISO8601_Z_PATTERN.fullmatch(' in src, \
            f"{method.__name__} must use _ISO8601_Z_PATTERN.fullmatch()"
        assert '_ISO8601_Z_PATTERN.match(' not in src, \
            f"{method.__name__} must NOT use _ISO8601_Z_PATTERN.match() (allows trailing \\n bypass)"
        assert 're.compile(' not in src, \
            f"{method.__name__} must NOT define a local re.compile() — must use the module-level _ISO8601_Z_PATTERN constant"
```

**T6 DoD:**
- `grep -qE '^class TestIso8601PatternSourcePins' test_database.py` (AC-1)
- pytest `-v` output for the 5 new methods shows: 1 + 1 + 3 + 2 = **7 PASS** assertions
- AC-3 + AC-4 + AC-5 + AC-6 satisfied

### T7 — Quality gates

```bash
./validate.sh                                                                  # exit 0
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q 2>&1 | tail -1
# Expected: "214 passed" (= 197 baseline + 17 new per AC-11 NFR-1)

# Wider regression check (per plan-reviewer iter 1 suggestion 6):
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ -q 2>&1 | tail -1
# Expected: PRE_PYTEST_PASS_WIDE + 17

git diff develop...HEAD -- plugins/pd/hooks/lib/semantic_memory/database.py | wc -l   # = 0 (AC-12)
```

**T7 DoD:**
- validate.sh exit 0; warning count unchanged
- pytest test_database.py pass count = exactly **214** (197 + 17)
- pytest plugins/pd/hooks/lib/ pass count = PRE_PYTEST_PASS_WIDE + 17 (no out-of-scope regressions)
- `database.py` diff is empty
- **Atomic commit boundary:** at this point, T1-T6 (test_database.py edits) + T8 (backlog.md edit, executed before T7 if you prefer atomic-commit ordering, OR after T7 with re-run of gates) are all staged. Run `git add plugins/pd/hooks/lib/semantic_memory/test_database.py docs/backlog.md` then `git commit -m "..."` as one atomic commit. Verify via `git show --stat HEAD`.

### T8 — File backlog item for `_ISO8601_Z_PATTERN` relocation (Open Question 2)

**Order:** execute BEFORE T7 quality gates so backlog edit is part of the same atomic commit (per plan-reviewer iter 1 warning 3 + design line 35 "All in one atomic commit").

Append new entry to `docs/backlog.md` (next ID after current max — compute via `grep -oE '^- \*\*#[0-9]{5}\*\*' docs/backlog.md | grep -oE '[0-9]{5}' | sort -n | tail -1` then increment):

```markdown
- **#NNNNN** [MED/architecture] Relocate `_ISO8601_Z_PATTERN` from `database.py:23-26` to `_config_utils.py` near `_iso_utc`. Co-locating the validator with its producer would: (1) make source-level pins trivially checkable as `assert _PATTERN.flags & re.ASCII` without `inspect.getsource()`; (2) centralize the two call sites onto a single import; (3) make module-level invariants testable without implementation coupling to `database.py` internals. Filed by feature:095 first-principles advisor (architectural debt root-cause for the recursive test-hardening pattern across 091/092/093/095). (filed by feature:095 — relocate pattern to config-utils)
```

**T8 DoD:**
- New backlog entry visible in `docs/backlog.md`
- ID follows existing max+1 convention
- Edit STAGED but NOT yet committed (commit happens at T7 atomic boundary)

### T9 — `/pd:finish-feature` (FIRST PRODUCTION EXERCISE OF FEATURE 094 GATE)

Run `/pd:finish-feature` on feature 095 branch. This will:
1. Validate (Step 5a)
2. **Step 5b: dispatch 4 reviewers in parallel** ← FIRST PRODUCTION USE of feature 094's pre-release QA gate
3. Step 5a-bis: /security-review
4. Retro
5. Merge to develop
6. Release script

**T9 DoD:**
- Step 5b dispatches 4 reviewers; gate result captured
- AC-13a: retro.md "Manual Verification" section contains required tokens
- AC-13b: retro.md captures `+++ b/plugins/pd/hooks/lib/semantic_memory/test_database.py` from one reviewer's dispatch context
- If gate produces false-blocker on this first run: per R-5 contingency, capture failure mode in retro, file backlog item against feature 094, use `qa-override.md` (≥50-char rationale)

## AC Coverage Matrix

| AC | Verification | Step |
|----|--------------|------|
| AC-1 | `grep -qE '^class TestIso8601PatternSourcePins' test_database.py` | T6 |
| AC-2 | 2 greps for `import inspect` + module-level `_ISO8601_Z_PATTERN` | T1 |
| AC-3 | pytest run of `test_pattern_source_uses_explicit_digit_class` | T6 |
| AC-4 | pytest run of `test_pattern_compiled_with_re_ascii_flag` | T6 |
| AC-5 | pytest run × 3 cases | T6 |
| AC-6 | pytest run × 2 cases | T6 |
| AC-7 | pytest run × 10 cases (was 8) | T3 |
| AC-8 | pytest run × 4 cases | T4 |
| AC-9 | pytest run × 4 cases | T5 |
| AC-10 | grep `ids=` in 5 parametrize decorators | T3, T4, T5, T6 |
| AC-11 | `pytest -q` final line = "214 passed" | T7 |
| AC-12 | `git diff -- database.py | wc -l` = 0 | T7 |
| AC-13a | grep retro.md for "Manual Verification" + "094 gate" + "test self-update" | T9 |
| AC-13b | grep retro.md for `+++ b/...test_database.py` | T9 |

All 14 ACs binary-verifiable. No manual-only ACs.

## Quality Gates

- `./validate.sh` exit 0 (no new errors; warning count unchanged)
- `pytest test_database.py` pass count = 214 (197 + 17 exact)
- `git diff -- database.py` = empty (AC-12)
- All 14 ACs verified per matrix above

## Dependencies

- `inspect` (stdlib) — added at T1
- `_ISO8601_Z_PATTERN` symbol — already exists at `database.py:23-26`
- Python 3.14.4 (project venv)
- 0 new external dependencies (NFR-3)

## Risks Carried from Design

All 5 risks (R-1..R-5) per design.md Risks section. R-5 (feature 094 first-gate-run failure) is the most consequential — explicit contingency in T9 DoD.

## Out of Scope

Same as PRD/spec/design. No expansion. Backlog filing of `_config_utils.py` relocation handled at T8 within feature 095 scope (one-line addition to backlog.md, not a separate feature).

## Notes — Direct-orchestrator vs taskification

Direct-orchestrator (single atomic commit) chosen because:
- Single file touch (test_database.py)
- ~80 net LOC
- All edits independent (T1-T6 don't depend on each other beyond import-before-use ordering)
- No worktree-parallelism win for one-file feature

## Review History

### Iteration 1 — plan-reviewer (opus, 2026-04-29)

**Findings:** 0 blockers + 4 warnings + 2 suggestions

**Corrections applied:**
- T4/T5/T6 — added verbatim insertion-anchor quotes (line 2084 "format violation in captured.err" for T4; line 2122 "db.close()" for T5; "class TestExecuteChunkSeam:" line for T6). Reason: Warning 1.
- Stage 0 — added grep verification for feature 094's un-flagged `git diff {pd_base_branch}...HEAD` form, validating AC-13b's `+++ b/` marker assumption empirically before any edits. Reason: Warning 2.
- T7/T8 — reconciled atomic-commit boundary: T8 (backlog edit) executes BEFORE T7 quality gates, both staged together for one atomic commit. T7 DoD now explicitly states `git add ... && git commit ... && git show --stat HEAD` verification. Reason: Warning 3.
- T3 — switched from hand-aligned `ids=[...]` to derived `ids=[c for _, c in _INVALID_NOW_ISO_CASES]` form per design TD-6. Eliminates dual-list drift risk. Reason: Warning 4.
- T7 — added wider regression check via `pytest plugins/pd/hooks/lib/ -q` against PRE_PYTEST_PASS_WIDE captured at Stage 0. Reason: Suggestion 6.
- T6 — kept verbatim duplication of class body (vs spec.md FR-1) with explicit awareness; design TD-6 lists this as the chosen path. Suggestion 5 acknowledged as a tradeoff.
