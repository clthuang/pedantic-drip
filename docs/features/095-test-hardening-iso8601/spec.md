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
- **AC-10** All NEW parametrize blocks AND the FR-2 extension to `test_batch_demote_rejects_invalid_now_iso` include `ids=[...]` argument with descriptive labels (per feature 094 retro #00243 + FR-4). Verifiable: every parametrize decorator added/modified by feature 095 — `TestIso8601PatternSourcePins.test_pattern_rejects_unicode_digits_directly`, `TestIso8601PatternSourcePins.test_call_sites_use_fullmatch_not_match`, `TestScanDecayCandidates.test_pattern_rejects_partial_unicode_injection`, `TestBatchDemote.test_batch_demote_rejects_partial_unicode_injection`, AND the extended `TestBatchDemote.test_batch_demote_rejects_invalid_now_iso` — has `ids=` keyword argument.
- **AC-11** Pytest baseline pinned at feature 095 start: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q | tail -1` returns `197 passed` (measured 2026-04-29). Post-feature count must equal `214 passed` (= 197 baseline + 17 new per NFR-1). No regressions; exact +17 delta.
- **AC-12** Zero changes to `plugins/pd/hooks/lib/semantic_memory/database.py`. Verifiable: `git diff develop...HEAD -- plugins/pd/hooks/lib/semantic_memory/database.py` returns no output.
- **AC-13a** Retro.md contains "Manual Verification" section with literal text matching `094 gate` AND `test self-update`. Verifiable: `grep -qE 'Manual Verification' docs/features/095-test-hardening-iso8601/retro.md && grep -qE '094 gate' docs/features/095-test-hardening-iso8601/retro.md && grep -qE 'test self-update' docs/features/095-test-hardening-iso8601/retro.md`.
- **AC-13b** Open Question 1 closure: T6 dogfood verifies feature 094 gate's reviewer-dispatch diff scope INCLUDES test files. Verifiable: dogfood diff capture shows `test_database.py` in the path list passed to reviewers. Concrete artifact: `git diff develop...HEAD -- 'plugins/pd/hooks/lib/semantic_memory/test_database.py' | wc -l` returns > 0 captured in retro.md as evidence.

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

For `TestScanDecayCandidates` — match existing fixture pattern (`db: MemoryDatabase, capsys` per `test_pattern_rejects_unicode_digits` at `test_database.py:2011-2016`):

```python
@pytest.mark.parametrize("partial_unicode_input,case_name", [
    ("2026-01-0１T00:00:00Z", "day-pos"),       # fullwidth 1 in day position
    ("2026-01-01T０0:00:00Z", "hour-pos"),      # fullwidth 0 in hour position
    ("2026-01-01T00:０0:00Z", "minute-pos"),    # fullwidth 0 in minute position
    ("2026-01-01T00:00:０0Z", "second-pos"),    # fullwidth 0 in second position
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

For `TestBatchDemote` — match existing pattern (no `db` fixture; manual construct + try/finally per `test_batch_demote_rejects_invalid_now_iso` at `test_database.py:2112-2122`):

```python
@pytest.mark.parametrize("partial_unicode_input,case_name", [
    ("2026-01-0１T00:00:00Z", "day-pos"),
    ("2026-01-01T０0:00:00Z", "hour-pos"),
    ("2026-01-01T00:０0:00Z", "minute-pos"),
    ("2026-01-01T00:00:０0Z", "second-pos"),
], ids=["day-pos", "hour-pos", "minute-pos", "second-pos"])
def test_batch_demote_rejects_partial_unicode_injection(self, partial_unicode_input, case_name):
    db = MemoryDatabase(":memory:")
    try:
        with pytest.raises(ValueError, match="Z-suffix ISO-8601"):
            db.batch_demote(["x"], "medium", partial_unicode_input)
    finally:
        db.close()
```

**Fixture asymmetry rationale:** mirrors existing precedent — `TestScanDecayCandidates` uses class-level `db` fixture + `capsys` for stderr capture (log-and-skip read path); `TestBatchDemote` does NOT have a `db` fixture (raise-on-invalid write path tests are stateless). Pattern unchanged from feature 093.

**Warning string evidence:** `"format violation"` literal verified in existing `test_pattern_rejects_unicode_digits` body comment at `test_database.py:2014` — same string, same assertion shape.

### FR-4 — `ids=[...]` on all NEW parametrize blocks

All 4 new parametrize decorators (`test_pattern_rejects_unicode_digits_directly`, `test_call_sites_use_fullmatch_not_match`, `test_pattern_rejects_partial_unicode_injection` ×2, plus the FR-2 extension which doesn't introduce a new decorator but the existing block already uses `case_name` so we follow up by adding `ids=[c for _, c in ...]`) include `ids=` argument.

### FR-5 — Module-level imports

Verified state at feature 095 start (via `grep -nE '^from semantic_memory.database import' test_database.py`):

```
test_database.py:15: from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query
```

So `MemoryDatabase` is already module-level imported (good — AC-6 parametrize uses it at decoration time). FR-5 modifies line 15 to add `_ISO8601_Z_PATTERN`:

```python
from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query, _ISO8601_Z_PATTERN
```

Plus add `import inspect` at top of file (verifiable via `grep -qE '^import inspect$' test_database.py` post-edit).

The previous inline `from semantic_memory.database import _ISO8601_Z_PATTERN` inside `test_iso_utc_output_always_passes_hardened_pattern` (line 2041) becomes redundant — leave it for now (no harm, doesn't conflict with module-level import); could be cleaned up in a future pass.

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
| Python `inspect.getsource()` regression returns wrong line (CPython #122981, fixed in 3.13.0 final; project runs **Python 3.14.4** per `plugins/pd/.venv/bin/python --version`, so risk is theoretical for current target) | Test FAILS LOUDLY (red CI) — false-RED is correct vs false-GREEN | AC-6, FR-1 (only `test_call_sites_use_fullmatch_not_match` uses `getsource`; structural pins #00246/#00247/#00248 use stable public attrs instead) |
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

## Review History

### Iteration 1 — spec-reviewer (opus, 2026-04-29)

**Findings:** 2 blockers + 4 warnings + 2 suggestions

**Corrections applied:**
- FR-3 (TestScanDecayCandidates body) — added `capsys` to method signature; matches existing `test_pattern_rejects_unicode_digits` pattern at `test_database.py:2011-2016`. Reason: Blocker 1.
- AC-13 split into AC-13a (binary grep on retro.md prose markers) + AC-13b (binary diff-list capture). Both now grep-verifiable. Reason: Blocker 2.
- AC-11 — pinned baseline to 197 PASS measured 2026-04-29 with target 214 PASS (= 197 + 17 per NFR-1). Tightened from 15-25 range to exact +17. Reason: Warning 3.
- FR-5 — quoted exact existing import line `test_database.py:15` and prescribed in-place modification. Reason: Warning 4.
- FR-3 — explained fixture asymmetry (TestScanDecayCandidates uses `db + capsys`, TestBatchDemote uses manual construct) by citing existing precedents. Reason: Warning 5.
- AC-10 — explicitly states the FR-2 extension to existing block ALSO requires `ids=` (resolves AC-10 vs FR-4 ambiguity). Reason: Warning 6.
- FR-3 — added "Warning string evidence" note quoting `test_database.py:2014` for the literal `"format violation"` substring. Reason: Suggestion 7.
- Edge Cases — added explicit Python 3.14.4 version + CPython #122981 fixed-in-3.13.0-final note. Reason: Suggestion 8.

## Definition of Done

- [ ] All 14 ACs (AC-1..AC-12, AC-13a, AC-13b) pass binary verification
- [ ] All 5 FRs implemented
- [ ] All 4 NFRs met
- [ ] `validate.sh` exit 0 (no new errors; pre-existing warnings unchanged)
- [ ] Pytest pass count = 197 baseline + 17 = 214 PASS (per AC-11 pinned baseline)
- [ ] Zero production code changes (AC-12)
- [ ] Backlog item filed for `_ISO8601_Z_PATTERN` relocation to `_config_utils.py` per Open Question 2
- [ ] Feature 094 gate test-file scope verified empirically during T6 dogfood (AC-13b closure)
- [ ] Retro.md "Manual Verification" section documents AC-13a + AC-13b closure
