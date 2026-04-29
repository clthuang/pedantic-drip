# Design: Feature 095 — Test-Hardening Sweep for `_ISO8601_Z_PATTERN`

## Status
- Created: 2026-04-29
- Phase: design
- Upstream: spec.md (14 ACs incl AC-13a/13b, 5 FRs, 4 NFRs); PRD with 3 advisor analyses

## Prior Art Research

Already collected during brainstorm Stage 2 + spec phase. Key findings folded into design:

**Codebase patterns (`pd:codebase-explorer` + `pd:skill-searcher`):**
- `_ISO8601_Z_PATTERN` definition at `database.py:23-26` (post-093 hardened form: `[0-9]` literal + `re.ASCII` flag)
- Two `.fullmatch()` call sites: `database.py:1001` (scan_decay_candidates) + `database.py:1068` (batch_demote)
- Existing test classes: `TestScanDecayCandidates` (line 1905, uses `db: MemoryDatabase, capsys` fixture) + `TestBatchDemote` (line 2087, manual `MemoryDatabase(":memory:")` construction)
- Existing 4 ISO-8601 test methods at `test_database.py:2025-2122` (parametrized, no `ids=` per feature 094 retro #00243)
- Module-level import at line 15: `from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query`
- Inline `_ISO8601_Z_PATTERN` import at line 2041 (redundant after FR-5 lift)
- Pytest baseline: **197 PASS** in `test_database.py` (measured 2026-04-29 with Python 3.14.4)

**`inspect.getsource()` precedents in repo:**
- `plugins/pd/mcp/test_workflow_state_server.py:1851-1857` — handler list iteration + literal-token assertion
- `plugins/pd/mcp/test_workflow_state_server.py:2717-2721` — same pattern second batch
- `plugins/pd/hooks/lib/entity_registry/test_backfill.py:2073-2084` — module-scope exclusion-grep

**`pattern.pattern` / `pattern.flags` precedents:** none in repo. Feature 095 establishes the pattern.

**Industry / advisor calibration:**
- First-principles + antifragility advisors: prefer `pattern.pattern` + `pattern.flags & re.ASCII` (stable Python 3.7+ public attrs) over `inspect.getsource()` text-grep where signal is equivalent
- Pre-mortem advisor: tests + prod can be co-updated in same commit (self-defeating); structural backstop is feature 094 pre-release QA gate (verified by AC-13b)
- CPython #122981: fixed in 3.13.0 final; project runs Python 3.14.4 → risk theoretical

## Architecture

One file, three test classes touched, single atomic commit. Direct-orchestrator pattern (091/092/093/094 surgical-feature template).

```
plugins/pd/hooks/lib/semantic_memory/test_database.py    [edit, +~80 LOC, +17 parametrized assertions]
  ├─ Line 15:           module-level import extended (+ _ISO8601_Z_PATTERN)
  ├─ Line 16 (NEW):     `import inspect`
  ├─ Line 2041:         redundant inline import REMOVED
  ├─ TestScanDecayCandidates (line 1905):  + test_pattern_rejects_partial_unicode_injection (4 cases)
  ├─ TestBatchDemote (line 2087):          + test_batch_demote_rejects_partial_unicode_injection (4 cases)
  │                                        + 2 cases extending test_batch_demote_rejects_invalid_now_iso (with ids=)
  └─ TestIso8601PatternSourcePins (NEW):   5 methods (1+1+3+2+0 = 7 assertions; +2 from method dispatch = 9)
```

Inserted between existing `TestBatchDemote` (ends ~line 2122) and next class. Total 17 net new parametrized assertions (per spec NFR-1 math: 1+1+3+2+2+4+4 = 17).

**Zero production code changes** in `database.py` (AC-12).

## Technical Decisions

### TD-1: Public attribute pins for #00246-#00248 (NOT inspect.getsource)

**Decision:** `test_pattern_source_uses_explicit_digit_class` + `test_pattern_compiled_with_re_ascii_flag` + `test_pattern_rejects_unicode_digits_directly` use `_ISO8601_Z_PATTERN.pattern` (raw regex string) and `_ISO8601_Z_PATTERN.flags & re.ASCII` (compiled flag bitmask) — both stable Python public attributes since 3.7.

**Alternatives rejected:**
- `inspect.getsource()` text-grep on `database.py:23-26` — works today but couples to whitespace/comments/encoding; CPython #122981 regression class.
- AST-walk via `ast.parse()` — overkill for a 1-character literal pin; reader confusion.

**Rationale:** First-principles + antifragility advisors converged. `pattern.pattern` returns the exact source-string the regex was compiled from (`'[0-9]{4}-[0-9]{2}-...'`). `pattern.flags & re.ASCII` returns truthy iff the `re.ASCII` flag is set. Direct, deterministic, version-stable.

### TD-2: `inspect.getsource()` ONLY for call-site `.fullmatch()` pin (#00249 + #00250)

**Decision:** `test_call_sites_use_fullmatch_not_match` is the SOLE method using `inspect.getsource()`. The contract being tested is "call-site uses `.fullmatch()` not `.match()` and references `_ISO8601_Z_PATTERN` not a local re-compile" — that's call-form, not an attribute of the pattern object.

**Alternatives rejected:**
- AST-walk inspection — heavyweight; the literal-substring grep is sufficient signal.
- Skip the source-pin entirely; rely on behavior tests for `.match()` revert detection — fails for #00250 single-call-site revert at one of two call sites (asymmetric coverage).

**Rationale:** Pattern follows existing in-repo precedent (`test_workflow_state_server.py:1851`). Python 3.14.4 (project version) is post-CPython-#122981 fix. False-RED on Python upgrade is acceptable; false-GREEN avoided.

### TD-3: Two-class distribution (avoid collection-error SPOF)

**Decision:** Source-level structural pins (#00246-#00250, all 5 methods) live in NEW `TestIso8601PatternSourcePins` class. Behavioral pins (#00251 trailing-WS parity, #00252 partial-injection ×2) live in EXISTING `TestScanDecayCandidates` + `TestBatchDemote` classes.

**Alternatives rejected:**
- All 7 pins in one new class → single import-error kills all 7 simultaneously (antifragility R-2 collection-error SPOF)
- All 7 pins distributed in existing classes → blurs source-vs-behavior boundary; readers can't grep one class for "structural pins"

**Rationale:** Antifragility advisor recommendation. If `_ISO8601_Z_PATTERN` is renamed/moved, only the 5 pins in `TestIso8601PatternSourcePins` fail at collection; the 12 behavioral assertions (4 partial-injection scan + 4 partial-injection batch + 2 trailing-WS extension + existing behavior tests) continue to fire and emit signal.

### TD-4: Match existing fixture asymmetry (don't normalize)

**Decision:** `TestScanDecayCandidates.test_pattern_rejects_partial_unicode_injection` uses `db: MemoryDatabase, capsys` fixture (matches sibling `test_pattern_rejects_unicode_digits` at `test_database.py:2011-2016`). `TestBatchDemote.test_batch_demote_rejects_partial_unicode_injection` uses manual `MemoryDatabase(":memory:")` + try/finally (matches sibling `test_batch_demote_rejects_invalid_now_iso` at `test_database.py:2112-2122`).

**Alternatives rejected:**
- Force both to use `db` fixture — would diverge from existing TestBatchDemote convention; out of scope.
- Force both to use manual construction — would diverge from existing TestScanDecayCandidates `capsys`-based stderr capture pattern.

**Rationale:** Spec discipline. Fixture asymmetry mirrors the read-vs-write semantic split shipped in feature 092 (TD-3 read-path log-and-skip vs write-path raise). Tests should match call-site posture, not normalize for cosmetic uniformity.

### TD-5: In-place cleanup of redundant inline import (FR-5 cleanup expansion)

**Decision:** Per phase-reviewer suggestion, the redundant inline `from semantic_memory.database import _ISO8601_Z_PATTERN` at line 2041 is REMOVED in this feature (in-scope, since we're already touching the file).

**Alternatives rejected:**
- Defer to "future pass" (original FR-5 v1 wording) — leaves dead code that future readers may interpret as load-bearing.
- Promote to backlog item — micro-task that pollutes backlog with trivial cleanup.

**Rationale:** Cheapest path forward. One-line edit. Verified by AC-11 baseline pass count: removing the inline import doesn't change behavior since module-level import already covers the same symbol.

## Components

### C1: New `TestIso8601PatternSourcePins` class

**Owner:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`  
**Responsibility:** 5 source-level structural pins (#00246-#00250) using stable public-attribute assertions + 1 inspect.getsource() pin for call-form contract  
**Size:** ~50 LOC

### C2: Extension to `TestBatchDemote.test_batch_demote_rejects_invalid_now_iso`

**Owner:** existing class  
**Responsibility:** add 2 parametrize cases (trailing-space, trailing-CRLF) for #00251 cross-call-site parity. Add `ids=` argument per FR-4.  
**Size:** ~5 LOC

### C3: New behavioral-pin methods (×2)

**Owner:** existing classes (`TestScanDecayCandidates` + `TestBatchDemote`)  
**Responsibility:** `test_pattern_rejects_partial_unicode_injection` (×2 — one per call site) for #00252  
**Size:** ~25 LOC total

### C4: Module-level imports (FR-5)

**Owner:** test_database.py:15-16  
**Responsibility:** extend line 15 import + add line 16 `import inspect` + remove line 2041 inline import  
**Size:** -1 line net (1 add at top, 1 remove inline)

## Interfaces

### I-1: Pattern source-string assertions

```python
assert '[0-9]' in _ISO8601_Z_PATTERN.pattern        # AC-3, #00246
assert r'\d' not in _ISO8601_Z_PATTERN.pattern      # AC-3, #00246 negative
```

### I-2: Pattern flag assertion

```python
assert bool(_ISO8601_Z_PATTERN.flags & re.ASCII)    # AC-4, #00247
```

### I-3: Direct pattern-object Unicode rejection (parametrized over 3 cases)

```python
assert _ISO8601_Z_PATTERN.fullmatch(unicode_input) is None  # AC-5, #00248
```

### I-4: Call-site source-form pins (parametrized over 2 methods)

```python
src = inspect.getsource(method)                                  # AC-6
assert '_ISO8601_Z_PATTERN.fullmatch(' in src                    # #00249 + #00250 positive
assert '_ISO8601_Z_PATTERN.match(' not in src                    # #00250 negative
assert 're.compile(' not in src                                  # #00249 negative (no local re-compile)
```

### I-5: Cross-call-site rejection parity (parametrize extension)

```python
("2026-04-20T00:00:00Z ", "trailing-space"),       # AC-7, #00251 new case 1
("2026-04-20T00:00:00Z\r\n", "trailing-crlf"),     # AC-7, #00251 new case 2
```

### I-6: Partial Unicode-injection cases (parametrized over 4 positions × 2 call sites)

```python
[
    ("2026-01-0１T00:00:00Z", "day-pos"),
    ("2026-01-01T０0:00:00Z", "hour-pos"),
    ("2026-01-01T00:０0:00Z", "minute-pos"),
    ("2026-01-01T00:00:０0Z", "second-pos"),
]
```

Scan-path body: `list(db.scan_decay_candidates(case, scan_limit=10))` + `assert "format violation" in capsys.readouterr().err`  
Batch-path body: `pytest.raises(ValueError, match="Z-suffix ISO-8601")` around `db.batch_demote(["x"], "medium", case)`

## Risks

- **R-1 [LOW]** `inspect.getsource()` returns wrong content for decorated callable. **Mitigated:** call sites are plain methods (no decorators); only used in 1 method (TD-1 minimizes blast). Python 3.14.4 post-#122981.
- **R-2 [LOW]** Test self-update co-commit (test + prod changed together) — fundamental limitation of any pin test. **Mitigated:** AC-13a/13b; structural backstop is feature 094 pre-release QA gate (Open Question 1 closure verifies test-file scope).
- **R-3 [LOW]** Renaming `_ISO8601_Z_PATTERN` causes 5 pin tests to fail at collection. **Acceptable:** rename refactor must touch tests anyway; loud collection-error IS the alarm.

## Out of Scope

- Production code changes to `database.py` (AC-12)
- `_ISO8601_Z_PATTERN` relocation to `_config_utils.py` (file as separate backlog item per Open Question 2)
- LOW items #00260-#00263 (deferred per spec discipline)
- Cleaning up `+00:00` legacy format in `_seed_entry_for_demote` helper (#00240 from feature 093 backlog) — separate concern

## Implementation Order

Direct-orchestrator (091/092/093/094 surgical template). All in one atomic commit:

1. T0 — capture baselines (PRE_HEAD, pytest pass count = 197, test class line numbers).
2. T1 — module-level import edits (line 15 extend + line 16 add `import inspect`).
3. T2 — remove redundant inline import at line 2041.
4. T3 — add 2 parametrize cases + `ids=` to `test_batch_demote_rejects_invalid_now_iso` (C2).
5. T4 — add `test_pattern_rejects_partial_unicode_injection` to `TestScanDecayCandidates` (C3 part 1).
6. T5 — add `test_batch_demote_rejects_partial_unicode_injection` to `TestBatchDemote` (C3 part 2).
7. T6 — add `TestIso8601PatternSourcePins` class with 5 methods (C1).
8. T7 — quality gates: `validate.sh` exit 0; pytest pass count = 197 + 17 = 214.
9. T8 — file backlog item for `_ISO8601_Z_PATTERN` relocation (Open Question 2 closure).
10. T9 — `/pd:finish-feature` triggers feature 094's Step 5b gate (first production exercise).

## Test Strategy

| AC | Verified by |
|----|-------------|
| AC-1 | `grep -qE '^class TestIso8601PatternSourcePins' test_database.py` |
| AC-2 | 2 separate greps for `import inspect` + `_ISO8601_Z_PATTERN` import |
| AC-3 | pytest run of `test_pattern_source_uses_explicit_digit_class` |
| AC-4 | pytest run of `test_pattern_compiled_with_re_ascii_flag` |
| AC-5 | pytest run of `test_pattern_rejects_unicode_digits_directly` × 3 cases |
| AC-6 | pytest run of `test_call_sites_use_fullmatch_not_match` × 2 cases |
| AC-7 | pytest run of extended `test_batch_demote_rejects_invalid_now_iso` × 10 cases (was 8) |
| AC-8 | pytest run of `TestScanDecayCandidates.test_pattern_rejects_partial_unicode_injection` × 4 cases |
| AC-9 | pytest run of `TestBatchDemote.test_batch_demote_rejects_partial_unicode_injection` × 4 cases |
| AC-10 | grep for `ids=` keyword in each new/extended parametrize decorator |
| AC-11 | pytest pass count = 214 exactly (197 baseline + 17 new) |
| AC-12 | `git diff develop...HEAD -- ...database.py` returns no output |
| AC-13a | grep on retro.md for "Manual Verification" + "094 gate" + "test self-update" |
| AC-13b | dogfood diff capture in retro.md showing test_database.py in path list |

All ACs binary-verifiable. No manual ACs.

## Definition of Done

- All 14 ACs pass binary verification
- All 5 FRs implemented
- All 4 NFRs met
- `validate.sh` exit 0
- Pytest pass count = 214 (197 baseline + 17 new)
- Zero production code changes
- Backlog item filed for `_ISO8601_Z_PATTERN` relocation per Open Question 2
- Feature 094 gate test-file scope verified empirically during T6 dogfood (AC-13b closure)
- Retro.md "Manual Verification" section documents AC-13a + AC-13b
