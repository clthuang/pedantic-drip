# Implementation Log — Feature 097

## T0 — Baselines (captured at implement-start, 2026-04-29)
- PRE_HEAD: b3552ce20d638ae6b83647d5c16a4f23a482fa2e
- PRE_NARROW: 224 (test_database.py; spec-time estimate: 224 — exact match)
- PRE_WIDE: 3208 (plugins/pd/hooks/lib/; spec-time estimate: 3208 — exact match)
- PRE_SOURCE_PINS: 7 (TestIso8601PatternSourcePins; spec-time estimate: 7 — exact match)
- FR-7 precondition: `database._ISO8601_Z_PATTERN` module-accessible — **PASS** (verified via `hasattr(database, '_ISO8601_Z_PATTERN')` returning True)
- FR-6 precondition: 13 curated codepoints all category=Nd on Python 3.14.4 — **PASS**
- Tooling friction at T0: initial PRE_NARROW capture returned 223 due to grep parsing artifact (`grep -oE '[0-9]+'` matched timing component `2.63` first); fixed by adding `head -1` after first grep. Captured value confirmed at 224 via direct pytest run.

## T1 — Edit test_database.py
- **Edit 1a** (3 imports added after `import sqlite3`): `ast`, `textwrap`, `unicodedata`. Used Edit tool, byte-exact match.
- **Edit 1b** (atomic class rewrite): replaced `TestIso8601PatternSourcePins` class + added `_UNICODE_DIGIT_SCRIPTS` module-level constant (13 entries) immediately preceding the class. Applied via Python read-modify-write per direct-orchestrator hygiene heuristic (systematic-debugging skill § Tooling Friction Escape Hatches): the curated list contains 13 distinct Unicode-Nd scripts that Edit tool would strip if embedded directly in `old_string`. Generated codepoints at runtime via `chr(int(hex_str, 16))` to bypass Write/Edit stripping.
- **Tooling friction at T1**: initial Python script's f-string format `f"({datetime!r:30s} '{name}'),"` omitted the comma between the two strings, producing implicit-string-concatenation tuples (`('2026...Z'         'fullwidth-year')`) which collapsed to 1-tuples instead of 2-tuples. Caught by AC-10b grep returning 0 entries instead of ≥13. Fixed via second pass with regex `('([^']+T00:00:00Z)')\\s+('([\\w-]+-year)')` → `\\1, \\3` to insert missing commas in all 13 entries. Net result: 13/13 valid `(str, str)` tuples in `_UNICODE_DIGIT_SCRIPTS`.
- **DoD: 10 ACs verified via 13 grep/count commands — all PASS:**
  - AC-1 (FR-1 exact-string equality): PASS
  - AC-2a (flags & re.ASCII): PASS
  - AC-2b (not flags & re.IGNORECASE): PASS
  - AC-3 (lowercase-z behavioral): PASS
  - AC-4 (open-set inspect.getmembers): PASS
  - AC-5a (ast.parse/walk): PASS
  - AC-5b (ast.Call/Attribute): PASS
  - AC-6 (allowlist `attr == 'fullmatch'`): PASS
  - AC-7 (leading-WS): PASS
  - AC-8 (pytest.importorskip): PASS
  - AC-10a (unicodedata): PASS
  - AC-10b (script count = 13): PASS
  - AC-11 (identity-pin): PASS

## T1.5 — Collection-only fail-fast checkpoint
- `pytest --collect-only TestIso8601PatternSourcePins`: **21 tests collected, 0 errors** (PASS, exact match to design Architecture Overview target).

## T2 — Quality gates
- **AC-16** TestIso8601PatternSourcePins: **21 passed** in 0.10s (PASS — exact target)
- **AC-13** pytest narrow (test_database.py): **238 passed** in 2.68s (PASS — exact = PRE_NARROW + 14 = 224 + 14)
- **AC-14** pytest wide (plugins/pd/hooks/lib/): **3222 passed** in 39.33s (PASS — exact = PRE_WIDE + 14 = 3208 + 14)
- **AC-15** validate.sh: **exit 0**, errors=0, warnings=4 (PASS — preserved warning baseline)
- **AC-12** production scope guard: `git diff develop...HEAD -- _config_utils.py database.py maintenance.py refresh.py memory_server.py conftest.py` produces **0 bytes** (PASS — pure test-file change confirmed)

## T3 — Atomic commit
- Pre-commit verification: both `test_database.py` (production-code-equivalent) and `implementation-log.md` (artifact) are staged together for atomic commit.
- Commit SHA: {to be filled by git commit step below}
- complete_phase MCP call: result captured below.

## Closure
- All 16 ACs satisfied (15 gating + 1 manual non-gating AC-9 acknowledged in spec/design narrative).
- All 8 backlog #00278 sub-items closed: (a) FR-1, (b) FR-2a/2b, (c+d+e) FR-3, (f) FR-4, (g) FR-5, (h) FR-6, plus bonus (i) FR-7.
- Net production-touch: 0 LOC. Net test count delta: +14 (224→238 narrow, 3208→3222 wide; TestIso8601PatternSourcePins 7→21).
- Direct-orchestrator hygiene per feature 096 retro Tune #2 + #3: implementation-log.md emitted (this file); complete_phase MCP call follows the atomic commit; both files in single commit.
