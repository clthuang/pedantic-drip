# Spec: Feature 095 — Test-Hardening Sweep for `_ISO8601_Z_PATTERN` Mutation-Resistance Gaps

## Status
- Phase: specify
- Created: 2026-04-29
- PRD: `docs/features/095-test-hardening-iso8601/prd.md`
- Source: backlog #00246 (closes #00246-#00252; cheap MED extensions for #00253-#00259)
- Target: v4.16.5 (test-only; zero production code change)

## Overview

Add 5 new test methods + 2 parametrize extensions to `plugins/pd/hooks/lib/semantic_memory/test_database.py` that close 7 HIGH source-level mutation-resistance gaps for `_ISO8601_Z_PATTERN`. Per advisor consensus (first-principles + antifragility), prefer `pattern.pattern` + `pattern.flags & re.ASCII` (Python public-attribute assertions, stable since 3.7) over `inspect.getsource()` text-grep where the same signal is available. Use `inspect.getsource()` only for call-site `.fullmatch()` source-pins where call-form IS the contract.

Test-only feature; zero production code changes.

## Acceptance Criteria (binary-verifiable)

- **AC-1** `plugins/pd/hooks/lib/semantic_memory/test_database.py` contains a new test class `TestIso8601PatternSourcePins`. Verifiable: `grep -qE '^class TestIso8601PatternSourcePins' plugins/pd/hooks/lib/semantic_memory/test_database.py`.
- **AC-2** Module-level imports added near top of test_database.py (NOT inside test methods):
  - `import inspect` present (verifiable: `grep -qE '^import inspect' test_database.py`)
  - `from semantic_memory.database import _ISO8601_Z_PATTERN` present at module top (verifiable: `grep -qE '^from semantic_memory.database import.*_ISO8601_Z_PATTERN' test_database.py`)
- **AC-3** `TestIso8601PatternSourcePins` contains method `test_pattern_source_uses_explicit_digit_class` whose body asserts `'[0-9]' in _ISO8601_Z_PATTERN.pattern` AND `r'\d' not in _ISO8601_Z_PATTERN.pattern`. Closes #00246.
- **AC-4** `TestIso8601PatternSourcePins` contains method `test_pattern_compiled_with_re_ascii_flag` whose body asserts `bool(_ISO8601_Z_PATTERN.flags & re.ASCII)` is True. Closes #00247.
- **AC-5** `TestIso8601PatternSourcePins` contains method `test_pattern_rejects_unicode_digits_directly` parametrized over fullwidth/Arabic-Indic/Devanagari direct cases (3 cases minimum) with `ids=[...]` argument. Each asserts `_ISO8601_Z_PATTERN.fullmatch(case) is None` directly on the pattern object (decoupled from call sites). Closes #00248.
- **AC-6** `TestIso8601PatternSourcePins` contains method `test_call_sites_use_fullmatch_not_match` parametrized over `[MemoryDatabase.scan_decay_candidates, MemoryDatabase.batch_demote]` with `ids=['scan_decay_candidates', 'batch_demote']`. For each method, uses `inspect.getsource()` and asserts:
  - `'_ISO8601_Z_PATTERN.fullmatch(' in src` (positive — fullmatch is used)
  - `'_ISO8601_Z_PATTERN.match(' not in src` (negative — match is NOT used)
  - `'re.compile(' not in src` (negative — no local re-compile)
  Closes #00250 + #00249 (both call sites verified to share single source of truth).
- **AC-7** `TestBatchDemote.test_batch_demote_rejects_invalid_now_iso` parametrize list extended with **2 new cases** (per FR-2 below):
  - `("2026-04-20T00:00:00Z ", "trailing-space")`
  - `("2026-04-20T00:00:00Z\r\n", "trailing-crlf")`
  Closes #00251 (cross-call-site rejection parity with `test_pattern_rejects_trailing_whitespace` in `TestScanDecayCandidates`).
- **AC-8** `TestScanDecayCandidates` contains method `test_pattern_rejects_partial_unicode_injection` parametrized over 4 positions (day/hour/minute/second) with single fullwidth `１` substituted (e.g., `"2026-01-0１T00:00:00Z"`). Each asserts call-site rejection via `scan_decay_candidates`. Closes #00252 at scan path.
- **AC-9** `TestBatchDemote` contains method `test_batch_demote_rejects_partial_unicode_injection` parametrized identically to AC-8. Each asserts `pytest.raises(ValueError, match="Z-suffix ISO-8601")` via `batch_demote(["x"], "medium", case)`. Closes #00252 at batch path.
- **AC-10** All NEW parametrize blocks in feature 095 include `ids=[...]` argument with descriptive labels (per feature 094 retro #00243 + FR-4). Verifiable: every new parametrize decorator in `TestIso8601PatternSourcePins`, `test_pattern_rejects_partial_unicode_injection`, `test_batch_demote_rejects_partial_unicode_injection` has `ids=` keyword argument.
- **AC-11** Pytest baseline transition: pre-feature pass count → post-feature pass count = pre + 15 to pre + 25 (15-25 net new parametrized assertions per NFR-1). No regressions.
- **AC-12** Zero changes to `plugins/pd/hooks/lib/semantic_memory/database.py`. Verifiable: `git diff develop...HEAD -- plugins/pd/hooks/lib/semantic_memory/database.py` returns no output.
- **AC-13** Pre-mortem advisor concern (test self-update co-commit) is acknowledged in retro.md "Manual Verification" section as fundamental limitation — feature 094 pre-release QA gate is the structural backstop; verify gate sees test files (Open Question 1 closure) during T6 dogfood by inspecting reviewer dispatch diff scope.

## Functional Requirements

### FR-1 — `TestIso8601PatternSourcePins` class (NEW)

**File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
**Insertion point:** After `class TestBatchDemote` (line ~2087 area) but before `class TestExecuteChunkSeam` (preserves existing alphabetical-ish class ordering and groups regex-related tests together).

**Class body (5 methods):**

```python
class TestIso8601PatternSourcePins:
    """Source-level mutation-resistance pins for _ISO8601_Z_PATTERN.

    Closes feature 093 post-release adversarial QA gaps #00246-#00250 (#00248 narrowed).
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

### FR-2 — Extend `test_batch_demote_rejects_invalid_now_iso` parametrize (closes #00251)

**File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py` (existing method in `TestBatchDemote` ~line 2102-2122)

Add 2 cases to the existing parametrize list:

```python
("2026-04-20T00:00:00Z ", "trailing-space"),       # NEW (#00251)
("2026-04-20T00:00:00Z\r\n", "trailing-crlf"),     # NEW (#00251)
```

Existing 8 cases remain unchanged.

### FR-3 — Mixed ASCII+Unicode partial-injection tests (closes #00252)

Add `test_pattern_rejects_partial_unicode_injection` to BOTH `TestScanDecayCandidates` AND `TestBatchDemote`.

**Body template (4 parametrized cases per call site):**

```python
@pytest.mark.parametrize("partial_unicode_input,case_name", [
    ("2026-01-0１T00:00:00Z", "day-pos"),       # fullwidth 1 in day position
    ("2026-01-01T０0:00:00Z", "hour-pos"),      # fullwidth 0 in hour position
    ("2026-01-01T00:０0:00Z", "minute-pos"),    # fullwidth 0 in minute position
    ("2026-01-01T00:00:０0Z", "second-pos"),    # fullwidth 0 in second position
], ids=["day-pos", "hour-pos", "minute-pos", "second-pos"])
def test_pattern_rejects_partial_unicode_injection(self, db, partial_unicode_input, case_name):
    """Closes #00252 — pin rejection of mid-string single Unicode digit injection.

    All-Unicode-year tests already cover full Unicode replacement (test_pattern_rejects_unicode_digits).
    This test pins the partial-injection case at each datetime field position.
    """
    # For TestScanDecayCandidates:
    captured = capsys.readouterr()  # capture stderr warnings
    list(db.scan_decay_candidates(partial_unicode_input, scan_limit=10))
    assert "format violation" in captured.err, \
        f"[{case_name}] scan_decay_candidates must reject partial Unicode injection in {case_name}"

# For TestBatchDemote: same parametrize, but body is:
def test_batch_demote_rejects_partial_unicode_injection(self, partial_unicode_input, case_name):
    db = MemoryDatabase(":memory:")
    try:
        with pytest.raises(ValueError, match="Z-suffix ISO-8601"):
            db.batch_demote(["x"], "medium", partial_unicode_input)
    finally:
        db.close()
```

### FR-4 — `ids=[...]` on all NEW parametrize blocks

All 4 new parametrize decorators (`test_pattern_rejects_unicode_digits_directly`, `test_call_sites_use_fullmatch_not_match`, `test_pattern_rejects_partial_unicode_injection` ×2, plus the FR-2 extension which doesn't introduce a new decorator but the existing block already uses `case_name` so we follow up by adding `ids=[c for _, c in ...]`) include `ids=` argument.

### FR-5 — Module-level imports

Add to `plugins/pd/hooks/lib/semantic_memory/test_database.py` near existing imports (top of file):

```python
import inspect
from semantic_memory.database import _ISO8601_Z_PATTERN, MemoryDatabase
```

`MemoryDatabase` is already imported elsewhere in the file — no duplicate, just confirm. `_ISO8601_Z_PATTERN` was previously imported INSIDE `test_iso_utc_output_always_passes_hardened_pattern`; lift to module top so parametrize-level decorators can reference it (FR-1's `test_call_sites_use_fullmatch_not_match` parametrize uses `MemoryDatabase.scan_decay_candidates` etc., which only needs `MemoryDatabase` at decoration time; the `_ISO8601_Z_PATTERN` lift is for the other 3 methods that reference it in body assertions).

## Non-Functional Requirements

- **NFR-1** Net new parametrized assertions: 15-25
  - `test_pattern_source_uses_explicit_digit_class`: 1 method × 1 case = 1
  - `test_pattern_compiled_with_re_ascii_flag`: 1 × 1 = 1
  - `test_pattern_rejects_unicode_digits_directly`: 1 × 3 = 3
  - `test_call_sites_use_fullmatch_not_match`: 1 × 2 = 2
  - `test_batch_demote_rejects_invalid_now_iso` extension: +2 cases = 2
  - `test_pattern_rejects_partial_unicode_injection` (scan): 1 × 4 = 4
  - `test_batch_demote_rejects_partial_unicode_injection`: 1 × 4 = 4
  - **Total: 17 net new parametrized assertions** (within 15-25 target)
- **NFR-2** Zero changes to `plugins/pd/hooks/lib/semantic_memory/database.py`. Verified by AC-12.
- **NFR-3** No new external dependencies. Stdlib `inspect` + `re` only.
- **NFR-4** Wall-clock direct-orchestrator implementation: target <30 min.

## Edge Cases (mirror PRD)

| Scenario | Expected Behavior | Verified by |
|----------|-------------------|-------------|
| Python 3.13+ `inspect.getsource()` regression returns wrong line | Test FAILS LOUDLY (red CI) — false-RED is correct vs false-GREEN | AC-6, FR-1 (only `test_call_sites_use_fullmatch_not_match` uses `getsource`; structural pins #00246/#00247/#00248 use stable public attrs instead) |
| `_ISO8601_Z_PATTERN` renamed in future refactor | All 5 source-pin tests fail at module collection (`ImportError`) | AC-2 module import + Edge Cases distribution: 4 of 7 pin tests live in NEW class; 3 (FR-2 + FR-3 ×2) live in EXISTING classes — partial protection if rename happens |
| Test class collection-failure SPOF | Mitigated by 2-class distribution: 4 source-pins in `TestIso8601PatternSourcePins`; 3 behavioral pins in existing `TestScanDecayCandidates` / `TestBatchDemote` | FR-1 + FR-2 + FR-3 |
| Test self-update during refactor (test+prod co-commit) | Documented limitation; feature 094 pre-release QA gate is structural backstop | AC-13 |
| Feature 094 gate excludes `tests/` from diff scope | Verified empirically during T6 dogfood per Success Criterion + Open Question 1 | T6 + retro.md |

## Out of Scope (mirror PRD)

- Production code changes to `database.py`
- Relocation of `_ISO8601_Z_PATTERN` to `_config_utils.py` (file as separate backlog item before merge)
- LOW items #00260-#00263 (deferred to future feature)
- Adding `inspect.getsource()` brittleness to feature 094 QA gate's known-limitations doc

## Implementation Notes

- Total touch: 1 file (`test_database.py`) + 0 production files
- Estimated LOC: ~80 net (5 new methods + 2 parametrize cases + 2 imports)
- Direct-orchestrator pattern fits (091/092/093/094 surgical-feature template)
- All 17 new parametrized assertions added in ONE atomic commit
- Followed by `/pd:finish-feature` which will trigger the new pre-release QA gate (Step 5b) — first production exercise of feature 094

## Definition of Done

- [ ] All 13 ACs (AC-1..AC-13) pass binary verification
- [ ] All 5 FRs implemented
- [ ] All 4 NFRs met
- [ ] `validate.sh` exit 0 (no new errors; pre-existing warnings unchanged)
- [ ] Pytest pass count = baseline + 17 (NFR-1 says 15-25; we ship exactly 17)
- [ ] Zero production code changes (AC-12)
- [ ] Backlog item filed for `_ISO8601_Z_PATTERN` relocation to `_config_utils.py` per Open Question 2
- [ ] Feature 094 gate test-file scope verified empirically during T6 dogfood (Open Question 1 closure)
- [ ] Retro.md "Manual Verification" section documents AC-13 + Open Question 1 closure
