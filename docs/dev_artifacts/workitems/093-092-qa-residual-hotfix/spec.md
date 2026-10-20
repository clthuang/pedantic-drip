# Spec: Feature 093 — 092 QA Residual Hotfix

## Status
- Created: 2026-04-24
- Phase: specify
- Mode: standard
- Source PRD: `docs/dev_artifacts/workitems/093-092-qa-residual-hotfix/prd.md`

## Scope

3 findings from 092 post-release adversarial QA (1 HIGH + 2 MED) unified under one root cause (asymmetric shallow validation between FR-5 and FR-8). One fix: hardened `_ISO8601_Z_PATTERN` + symmetric application to `scan_decay_candidates` AND `batch_demote`.

## Functional Requirements

### FR-1: Harden `_ISO8601_Z_PATTERN` regex (#00219 + #00220)

**File:** `plugins/pd/hooks/lib/semantic_memory/database.py:17`

**Change:**
```python
# Before (current, vulnerable):
_ISO8601_Z_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')

# After (hardened):
_ISO8601_Z_PATTERN = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', re.ASCII)
```

**Rationale:**
- Replace `\d` with `[0-9]` literal — ASCII-only, independent of `re.ASCII` flag (#00219 primary defense).
- Add `re.ASCII` flag — defense-in-depth against any future class expansion (`\w`, `\s`).
- Remove `^` and `$` anchors from the pattern. Instead, call sites use `re.fullmatch()` (the idiomatic Python 3.4+ anchoring primitive). `fullmatch` requires the entire string to match — no trailing-newline bypass possible (#00220).

### FR-2: Convert call sites from `.match()` to `.fullmatch()` (#00220)

**File:** `plugins/pd/hooks/lib/semantic_memory/database.py:991`

**Change:**
```python
# Before:
if not _ISO8601_Z_PATTERN.match(not_null_cutoff):

# After:
if not _ISO8601_Z_PATTERN.fullmatch(not_null_cutoff):
```

### FR-3: Apply `_ISO8601_Z_PATTERN.fullmatch()` to `batch_demote` (#00221)

**File:** `plugins/pd/hooks/lib/semantic_memory/database.py:1055`

**Change:**
```python
# Before:
if not now_iso:
    raise ValueError("now_iso must be non-empty ISO-8601 timestamp")

# After:
if not _ISO8601_Z_PATTERN.fullmatch(now_iso):
    raise ValueError(
        f"now_iso must be Z-suffix ISO-8601 (YYYY-MM-DDTHH:MM:SSZ), "
        f"got {now_iso!r:.80}"
    )
```

**Rationale:**
- Symmetric pattern (same `_ISO8601_Z_PATTERN` as FR-2) — single source of truth per PRD constraint.
- Catches empty string (current behavior preserved): `fullmatch('')` → None → raises.
- Catches whitespace-only, newline-only, zero-width-space, 5-digit year (all the #00221 cases).
- Error message bounded to 80 chars (defense against log-leak via `{!r}`).
- Empty-ids short-circuit preserved: `if not ids: return 0` remains first guard (092 TD-3 preserved).

### FR-4: Parametrized format-drift pin test

**File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`

**New test** (replaces existing `test_scan_decay_candidates_matches_iso_utc_output` with parametrized version):

```python
@pytest.mark.parametrize("test_dt", [
    datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc),          # canonical
    datetime(2026, 4, 16, 12, 0, 0, 999999, tzinfo=timezone.utc),  # microsecond=max (strftime truncates)
    datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc),       # year 9999 upper boundary
    datetime(1, 1, 1, 0, 0, 0, tzinfo=timezone.utc),               # year 0001 lower boundary
    datetime(2024, 2, 29, 12, 0, 0, tzinfo=timezone.utc),          # leap year
])
def test_iso_utc_output_always_passes_hardened_pattern(test_dt):
    """FR-4 format-drift pin: _iso_utc output MUST pass _ISO8601_Z_PATTERN.fullmatch
    for all representative datetime boundaries. Catches regression where _iso_utc
    changes format and would silently break scan_decay_candidates AND batch_demote."""
    from semantic_memory._config_utils import _iso_utc
    from semantic_memory.database import _ISO8601_Z_PATTERN
    output = _iso_utc(test_dt)
    assert _ISO8601_Z_PATTERN.fullmatch(output), (
        f"_iso_utc({test_dt!r}) = {output!r} does not match hardened pattern"
    )
```

### FR-5: New pytests for #00219 + #00220 + #00221

**File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`

Add to `TestScanDecayCandidates`:

```python
@pytest.mark.parametrize("unicode_cutoff", [
    "２０２６-04-20T00:00:00Z",   # fullwidth digits
    "٢٠٢٦-04-20T00:00:00Z",   # Arabic-Indic digits
    "२०२६-04-20T00:00:00Z",   # Devanagari digits
])
def test_pattern_rejects_unicode_digits(unicode_cutoff, db, capsys):
    """FR-1 (#00219): hardened pattern uses [0-9] + re.ASCII; Unicode digits rejected."""
    rows = list(db.scan_decay_candidates(
        not_null_cutoff=unicode_cutoff, scan_limit=100,
    ))
    assert rows == []
    captured = capsys.readouterr()
    assert "format violation" in captured.err

@pytest.mark.parametrize("trailing_whitespace_cutoff", [
    "2026-04-20T00:00:00Z\n",      # trailing newline (#00220)
    "2026-04-20T00:00:00Z ",       # trailing space
    "2026-04-20T00:00:00Z\r\n",    # CRLF
])
def test_pattern_rejects_trailing_whitespace(trailing_whitespace_cutoff, db, capsys):
    """FR-2 (#00220): fullmatch rejects trailing whitespace that `$` would accept."""
    rows = list(db.scan_decay_candidates(
        not_null_cutoff=trailing_whitespace_cutoff, scan_limit=100,
    ))
    assert rows == []
    captured = capsys.readouterr()
    assert "format violation" in captured.err
```

Add to `TestBatchDemote`:

```python
@pytest.mark.parametrize("invalid_now_iso,case_name", [
    ("", "empty"),
    ("   ", "whitespace-only"),
    ("\n", "newline-only"),
    ("​", "zero-width-space"),
    ("10000-01-01T00:00:00Z", "5-digit-year"),
    ("2026-04-20T00:00:00Z\n", "trailing-newline"),
    ("２０２６-04-20T00:00:00Z", "unicode-digits"),
    ("2026-04-20T00:00:00+00:00", "plus-offset-not-Z"),
])
def test_batch_demote_rejects_invalid_now_iso(self, invalid_now_iso, case_name, db):
    """FR-3 (#00221): batch_demote uses same pattern as scan_decay_candidates.
    All symmetric inputs raise ValueError."""
    with pytest.raises(ValueError, match="Z-suffix ISO-8601"):
        db.batch_demote(["x"], "medium", invalid_now_iso)

def test_batch_demote_empty_ids_short_circuits_before_now_iso_check(self, db):
    """Regression guard: empty-ids short-circuit MUST still execute before the
    now_iso regex check (092 TD-3 preserved)."""
    # Should return 0 without raising, even though now_iso is garbage.
    assert db.batch_demote([], "medium", "garbage") == 0
```

### FR-6: Update `scan_decay_candidates` error message to match FR-3 style (bounded repr)

**File:** `plugins/pd/hooks/lib/semantic_memory/database.py:994`

**Change:**
```python
# Before:
sys.stderr.write(
    f"[scan_decay_candidates] not_null_cutoff format violation: "
    f"expected YYYY-MM-DDTHH:MM:SSZ, got {not_null_cutoff!r}; "
    f"returning empty result\n"
)

# After:
sys.stderr.write(
    f"[scan_decay_candidates] not_null_cutoff format violation: "
    f"expected YYYY-MM-DDTHH:MM:SSZ, got {not_null_cutoff!r:.80}; "
    f"returning empty result\n"
)
```

(Closes #00226 from 092 backlog — bounded repr defense-in-depth.)

## Non-Functional Requirements

- **NFR-1 LOC budget:** ≤ +30 production LOC (2 regex edits + 2 call-site conversions + 1 FR-3 new block + 1 bounded-repr edit), ≤ +80 test LOC (1 parametrized format-drift test, 2 new parametrized test classes, 2 new batch_demote tests, 1 empty-ids regression guard).
- **NFR-2 Zero regressions:** all existing pytest + test-hooks.sh tests pass.
- **NFR-3:** `./validate.sh` passes.
- **NFR-4:** reviewer iterations ≤ 2 per phase.
- **NFR-5 Single source of truth:** `_ISO8601_Z_PATTERN` constant is used by BOTH `scan_decay_candidates` AND `batch_demote`. No second pattern definition anywhere in `semantic_memory/`.
- **NFR-6 Structural exit gate:** post-merge adversarial QA by 4 parallel reviewers surfaces ≤ 2 MED findings and zero HIGH. If new HIGH surfaces, freeze scope; file new backlog.

## Acceptance Criteria

- **AC-1 (#00219):** `grep -cE 'r'"'"'\[0-9\]\{4\}-\[0-9\]\{2\}-\[0-9\]\{2\}T\[0-9\]\{2\}:\[0-9\]\{2\}:\[0-9\]\{2\}Z'"'"' database.py | head -1'` (or simpler): pattern uses `[0-9]` literal, not `\d`. Grep: `grep -c '\\\\d{4}' plugins/pd/hooks/lib/semantic_memory/database.py` = 0 (old pattern removed).
- **AC-1b (#00219):** `grep -cE 're\.compile.*re\.ASCII' plugins/pd/hooks/lib/semantic_memory/database.py` ≥ 1 (ASCII flag present).
- **AC-1c (#00219):** pytest `test_pattern_rejects_unicode_digits` passes for all 3 Unicode variants.
- **AC-2 (#00220):** `grep -c '_ISO8601_Z_PATTERN\.match(' plugins/pd/hooks/lib/semantic_memory/database.py` = 0 (all `.match()` converted). `grep -c '_ISO8601_Z_PATTERN\.fullmatch(' plugins/pd/hooks/lib/semantic_memory/database.py` ≥ 2 (used in both call sites).
- **AC-2b (#00220):** pytest `test_pattern_rejects_trailing_whitespace` passes for newline, space, CRLF.
- **AC-3 (#00221):** pytest `test_batch_demote_rejects_invalid_now_iso` passes for all 8 parametrized cases.
- **AC-3b (#00221):** pytest `test_batch_demote_empty_ids_short_circuits_before_now_iso_check` passes (TD-3 preserved).
- **AC-4 (format-drift pin):** pytest `test_iso_utc_output_always_passes_hardened_pattern` passes for all 5 parametrized datetime boundaries (including year 9999, year 0001, leap year, microsecond=999999).
- **AC-5 (single source of truth):** `grep -c '_ISO8601_Z_PATTERN = re\.compile' plugins/pd/hooks/lib/semantic_memory/database.py` = 1 (only one definition). `grep -rcE 're\.compile.*YYYY|re\.compile.*ISO' plugins/pd/hooks/lib/semantic_memory/` = 0 (no shadow patterns in other modules).
- **AC-6 (regression):** full pytest suite passes (`plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_maintenance.py plugins/pd/hooks/lib/semantic_memory/test_database.py`) with N_passed ≥ 267 (262 baseline + ≥5 new).
- **AC-7 (shell tests):** `bash plugins/pd/hooks/tests/test-hooks.sh` → 109/109 passed (unchanged; 093 does not touch shell tests).
- **AC-8 (validate.sh):** `./validate.sh` exit 0.
- **AC-9 (error message bound):** `grep -cE '\{not_null_cutoff!r:\.80\}' plugins/pd/hooks/lib/semantic_memory/database.py` ≥ 1.

## Assumptions

- `_iso_utc` in `_config_utils.py:31-47` emits `strftime("%Y-%m-%dT%H:%M:%SZ")` — 4-digit year, no microseconds, ASCII only. Verified via grep.
- No existing test currently passes a non-ASCII digit, trailing-whitespace, 5-digit year, or whitespace-only string to `batch_demote` or `scan_decay_candidates`. Verified via grep for test-literal usage.
- `re.ASCII` flag + `[0-9]` literal is redundant; using both is explicit defense-in-depth per advisor consensus.
- Year 9999 upper boundary is ISO-8601-valid. Year 0001 lower boundary is also valid (ISO-8601:2004 supports year 0000–9999 by default).

## Risks

- **R-1 [MED]** Tightening `batch_demote` validation could break current prod callers if `_iso_utc` ever emits a value that doesn't match the pattern. Mitigated by: FR-4 parametrized format-drift pin + FR-5 test `test_batch_demote_rejects_invalid_now_iso` covering real `_iso_utc(now)` inputs as positive control.
- **R-2 [LOW]** `re.fullmatch` is marginally slower than `re.match` (~2x for a short string). Called once per decay tick / once per batch — negligible.
- **R-3 [LOW]** New tests add ~40 assertions across parametrized cases. Test suite wall time increase < 100ms. Acceptable.

## Out of Scope

- #00222–#00236 (LOW quality + test gaps from 092 QA) — deferred to future test-hardening feature.
- Pre-release adversarial QA gate in `/pd:finish-feature` (#00217) — separate structural work.
- Multi-project memory DB validation (hypothetical future threat model).
