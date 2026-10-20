# Plan: Feature 097 — Test-pin v2 bundle for `_ISO8601_Z_PATTERN`

## Status
- Created: 2026-04-29
- Phase: create-plan
- Upstream: design.md (7 components, 3 interfaces, 5 TDs, 7 risks); spec.md (16 ACs, 8 FRs, 6 NFRs)

## Architecture Summary

Single test file edit + atomic commit. Direct-orchestrator pattern. Net production-touch: **0 LOC**. Net test count delta: **+14** (224→238 narrow, 3208→3222 wide; TestIso8601PatternSourcePins 7→21).

```
plugins/pd/hooks/lib/semantic_memory/test_database.py   [edit, ~+100 LOC test code]
```

## T0 — Capture baselines + verify preconditions

```bash
PRE_HEAD=$(git rev-parse HEAD)
PRE_NARROW=$(plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q 2>&1 | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
PRE_WIDE=$(plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ -q 2>&1 | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
PRE_SOURCE_PINS=$(plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py::TestIso8601PatternSourcePins -q 2>&1 | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')

# Expected (post-feature-096 + #00286/#00287):
# PRE_NARROW       == 224
# PRE_WIDE         == 3208
# PRE_SOURCE_PINS  == 7

# FR-7 precondition: database._ISO8601_Z_PATTERN module-accessible
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -c \
  "from semantic_memory import database; assert hasattr(database, '_ISO8601_Z_PATTERN'), 'FR-7 precondition fails'"

# FR-6 precondition: 13 curated codepoints categorize as Nd
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -c \
  "import unicodedata; assert all(unicodedata.category(c) == 'Nd' for c in '２٢२২༢២၂೨௨୨൨๒᮲'), 'FR-6 codepoints fail'"
```

**T0 DoD:** `PRE_NARROW == 224`, `PRE_WIDE == 3208`, `PRE_SOURCE_PINS == 7`, both precondition assertions pass.

## Implementation Order — Direct-Orchestrator

The class refactor is structurally additive (new fixture + 5 new tests + 1 new module-level constant) plus 4 in-place strengthenings/replacements. Per design TD-1, single atomic edit avoids churn.

### T1 — Edit `test_database.py` (atomic class rewrite + imports + module constant)

**File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`

**Edit 1a — Add `import ast`, `import textwrap`, `import unicodedata` to imports block (after `import struct`):**

**Old text** (line 9-10, exact verbatim):
```
import struct
import sqlite3
```

**New text:**
```
import struct
import sqlite3
import ast
import textwrap
import unicodedata
```

**Edit 1b — Replace TestIso8601PatternSourcePins class entirely:**

**Old text** (lines 2266-2326, the entire `TestIso8601PatternSourcePins` class verbatim including the 4-method body and trailing blank line before `class TestExecuteChunkSeam`):
```python
class TestIso8601PatternSourcePins:
    """Feature 095 — source-level mutation-resistance pins for _ISO8601_Z_PATTERN.

    Closes feature 093 post-release adversarial QA gaps #00246-#00250.
    Per advisor consensus, uses _ISO8601_Z_PATTERN.pattern / .flags (stable Python 3.7+
    public attrs) where signal is equivalent; uses inspect.getsource() only for call-site
    .fullmatch() pin (#00250) where call-form IS the contract.
    """

    def test_pattern_source_uses_explicit_digit_class(self):
        """Closes #00246 — pin literal `[0-9]` in pattern source, NOT `\\d`.

        #00287 (2026-04-29): also pin absence of `\\D` (negation of non-digit, equivalent
        to `\\d` mod Unicode). Realistic mutation pattern is unusual but cheap to defend.
        """
        assert '[0-9]' in _ISO8601_Z_PATTERN.pattern, \
            "_ISO8601_Z_PATTERN.pattern must use explicit [0-9] character class for ASCII-only matching"
        assert r'\d' not in _ISO8601_Z_PATTERN.pattern, \
            "_ISO8601_Z_PATTERN.pattern must NOT use \\d (Unicode-digit-permissive in Python 3 str patterns)"
        assert r'\D' not in _ISO8601_Z_PATTERN.pattern, \
            "_ISO8601_Z_PATTERN.pattern must NOT use \\D (negation-form Unicode-digit-permissive equivalent)"

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

        Catches combined mutation: swap [0-9] -> \\d AND drop re.ASCII flag (which would
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
        and confirm both share _ISO8601_Z_PATTERN as single source of truth.

        This is the only test in this class that uses inspect.getsource() — required because
        the contract IS the call-form, not an attribute of the pattern object.
        """
        src = inspect.getsource(method)
        assert '_ISO8601_Z_PATTERN.fullmatch(' in src, \
            f"{method.__name__} must use _ISO8601_Z_PATTERN.fullmatch()"
        assert '_ISO8601_Z_PATTERN.match(' not in src, \
            f"{method.__name__} must NOT use _ISO8601_Z_PATTERN.match() (allows trailing newline bypass)"
        assert 're.compile(' not in src, \
            f"{method.__name__} must NOT define a local re.compile() — must use the module-level _ISO8601_Z_PATTERN constant"

```

**New text** (replacement — adds `_UNICODE_DIGIT_SCRIPTS` module-level constant immediately before the class, then full v2 class body):

```python
# Curated Unicode-Nd script samples for FR-6 parametrize.
# Empirically verified at spec time on Python 3.14.4 via unicodedata.category(c) == 'Nd'.
# 13 distinct scripts (3 from feature 095 + 10 added by feature 097 #00278 sub-item h).
_UNICODE_DIGIT_SCRIPTS = [
    ('２０２６-04-20T00:00:00Z',  'fullwidth-year'),    # U+FF10..FF19
    ('٢٠٢٦-04-20T00:00:00Z',     'arabic-indic-year'), # U+0660..0669
    ('२०२६-04-20T00:00:00Z',     'devanagari-year'),   # U+0966..096F
    ('২০২৬-04-20T00:00:00Z',     'bengali-year'),      # U+09E6..09EF
    ('༢༠༢༦-04-20T00:00:00Z',     'tibetan-year'),      # U+0F20..0F29
    ('២០២៦-04-20T00:00:00Z',     'khmer-year'),        # U+17E0..17E9
    ('၂၀၂၆-04-20T00:00:00Z',     'myanmar-year'),      # U+1040..1049
    ('೨೦೨೬-04-20T00:00:00Z',     'kannada-year'),      # U+0CE6..0CEF
    ('௨௦௨௬-04-20T00:00:00Z',     'tamil-year'),        # U+0BE6..0BEF
    ('୨୦୨୬-04-20T00:00:00Z',     'oriya-year'),        # U+0B66..0B6F
    ('൨൦൨൬-04-20T00:00:00Z',     'malayalam-year'),    # U+0D66..0D6F
    ('๒๐๒๖-04-20T00:00:00Z',     'thai-year'),         # U+0E50..0E59
    ('᮲᮰᮲᮶-04-20T00:00:00Z',     'sundanese-year'),    # U+1BB0..1BB9
]


class TestIso8601PatternSourcePins:
    """Feature 097 (#00278) — refactored source-level mutation-resistance pins for _ISO8601_Z_PATTERN.

    Refactored from feature 095's substring/closed-set pins to use:
    - exact-string equality (FR-1 / sub-item a)
    - component-flag assertions (FR-2a / sub-item b)
    - behavioral lowercase-z negative case (FR-2b / sub-item b)
    - AST-walk open-set call-site discovery (FR-3 / sub-items c+d+e)
    - leading-WS rejection (FR-4 / sub-item f)
    - pytest.importorskip partial-isolation fixture (FR-5 / sub-item g)
    - curated 13-script Unicode-Nd parametrize + dynamic coverage (FR-6 / sub-item h)
    - identity-pin (FR-7 / bonus i)

    Closes backlog #00278 (8 sub-items consolidated from #00278-#00285).
    """

    EXPECTED_PATTERN = r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'

    @pytest.fixture(autouse=True, scope='class')
    def _pattern_probe(self):
        """FR-5 partial-isolation fixture (side-effect-only, no return).

        Skips this class via pytest.importorskip if `_ISO8601_Z_PATTERN` is renamed
        in `_config_utils.py`. Other tests in this file still depend on the
        module-level import (line 18); full isolation is out of scope.
        """
        config_utils = pytest.importorskip(
            'semantic_memory._config_utils',
            reason='_ISO8601_Z_PATTERN producer module unavailable',
        )
        if getattr(config_utils, '_ISO8601_Z_PATTERN', None) is None:
            pytest.skip('_ISO8601_Z_PATTERN absent from _config_utils')

    def test_pattern_source_exact_equality(self):
        """FR-1 — exact-string equality strictly subsumes substring + \\d/\\D negatives."""
        assert _ISO8601_Z_PATTERN.pattern == self.EXPECTED_PATTERN

    def test_pattern_compiled_flags_components(self):
        """FR-2a — component-level flag assertions, robust to Python flag-default drift."""
        assert _ISO8601_Z_PATTERN.flags & re.ASCII
        assert not (_ISO8601_Z_PATTERN.flags & re.IGNORECASE)
        assert not (_ISO8601_Z_PATTERN.flags & re.MULTILINE)
        assert not (_ISO8601_Z_PATTERN.flags & re.DOTALL)
        assert not (_ISO8601_Z_PATTERN.flags & re.VERBOSE)

    def test_pattern_rejects_lowercase_z(self):
        """FR-2b — defends against `re.ASCII | re.IGNORECASE` mutation that would keep `flags & re.ASCII` truthy while making lowercase z match."""
        assert _ISO8601_Z_PATTERN.fullmatch('2026-04-20T00:00:00z') is None

    def test_call_sites_only_use_fullmatch(self):
        """FR-3 — open-set AST-walk over MemoryDatabase methods, allowlist `.fullmatch()` only.

        Closes sub-items c+d+e: open-set discovery, comment/docstring immunity, full negative coverage.
        Limitation: only handles bare-Name receiver `_ISO8601_Z_PATTERN.method()`. Qualified module
        access (`some_alias._ISO8601_Z_PATTERN.method()`) out of scope per design R-4.
        """
        methods_with_pattern_calls = []
        for name, method in inspect.getmembers(MemoryDatabase, predicate=inspect.isfunction):
            try:
                src = inspect.getsource(method)
            except (TypeError, OSError):
                continue
            if '_ISO8601_Z_PATTERN' not in src:
                continue
            tree = ast.parse(textwrap.dedent(src))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == '_ISO8601_Z_PATTERN'):
                    assert node.func.attr == 'fullmatch', (
                        f"{name} uses _ISO8601_Z_PATTERN.{node.func.attr}() — "
                        f"only .fullmatch() is allowed (rejects trailing whitespace/newline)"
                    )
            methods_with_pattern_calls.append(name)
        assert methods_with_pattern_calls, (
            "No MemoryDatabase method references _ISO8601_Z_PATTERN — "
            "either the validator is unused (suspicious) or discovery is broken"
        )

    @pytest.mark.parametrize("leading_input,case_name", [
        (' 2026-04-20T00:00:00Z',     "leading-space"),
        ('  2026-04-20T00:00:00Z  ',  "leading-and-trailing-space"),
    ])
    def test_pattern_rejects_leading_whitespace(self, leading_input, case_name):
        """FR-4 — defends against `now_iso.strip()` pre-fullmatch mutation that would pass
        both source pin AND trailing-WS-only behavioral tests.
        """
        assert _ISO8601_Z_PATTERN.fullmatch(leading_input) is None, \
            f"[{case_name}] pattern must reject leading whitespace"

    @pytest.mark.parametrize("unicode_input,case_name", _UNICODE_DIGIT_SCRIPTS)
    def test_pattern_rejects_unicode_digits_directly(self, unicode_input, case_name):
        """FR-6 curated — 13 distinct Unicode-Nd scripts. All codepoints empirically
        verified at spec time on Python 3.14.4.
        """
        assert _ISO8601_Z_PATTERN.fullmatch(unicode_input) is None, \
            f"[{case_name}] pattern must reject Unicode-digit input directly"

    def test_unicode_nd_coverage_matches_python_3_14(self):
        """FR-6 dynamic — sanity assertion on Python 3.14.4 Nd-script count.

        Non-blocking signal: if Python's Unicode database expands substantially,
        revisit _UNICODE_DIGIT_SCRIPTS. Threshold ≥70 accommodates ~5 new scripts
        without spec revision; significant growth beyond that triggers NFR-6.
        """
        nd_scripts = set()
        for cp in range(0x110000):
            c = chr(cp)
            try:
                if unicodedata.category(c) != 'Nd':
                    continue
            except ValueError:
                continue
            name = unicodedata.name(c, '')
            if ' DIGIT ' in name:
                nd_scripts.add(name.rsplit(' DIGIT ', 1)[0])
        assert len(nd_scripts) >= 70, (
            f'Expected ≥70 Nd scripts in Python 3.14.4 (actual: 75); '
            f'got {len(nd_scripts)}. Update _UNICODE_DIGIT_SCRIPTS if Unicode '
            f'database expanded substantially.'
        )

    def test_pattern_is_single_source_of_truth(self):
        """FR-7 — identity-pin defends against future local re-shadowing post-feature-096."""
        from semantic_memory import database, _config_utils
        assert database._ISO8601_Z_PATTERN is _config_utils._ISO8601_Z_PATTERN, \
            'database._ISO8601_Z_PATTERN must be the same object as _config_utils._ISO8601_Z_PATTERN (single source of truth)'

```

Note: New text ends with exactly ONE trailing blank line. Combined with the existing blank at file line 2327 (NOT in Old text), this yields exactly 2 blank lines between `TestIso8601PatternSourcePins` and `class TestExecuteChunkSeam` — PEP-8 E303 compliant.

**T1 DoD (grep checks for AC-1 through AC-11):**
- AC-1: `grep -qE '_ISO8601_Z_PATTERN\.pattern == ' plugins/pd/hooks/lib/semantic_memory/test_database.py` ✓
- AC-2 component flags: `grep -qE 'flags & re\.ASCII' plugins/pd/hooks/lib/semantic_memory/test_database.py` AND `grep -qE 'not.*flags & re\.IGNORECASE' plugins/pd/hooks/lib/semantic_memory/test_database.py` ✓
- AC-3 lowercase-z: `grep -qE "fullmatch.*'2026.*z'" plugins/pd/hooks/lib/semantic_memory/test_database.py` ✓
- AC-4 open-set: `grep -q 'inspect.getmembers(MemoryDatabase' plugins/pd/hooks/lib/semantic_memory/test_database.py` ✓
- AC-5 AST-walk: `grep -qE 'ast\.parse|ast\.walk' plugins/pd/hooks/lib/semantic_memory/test_database.py` AND `grep -qE 'ast\.Call|ast\.Attribute' plugins/pd/hooks/lib/semantic_memory/test_database.py` ✓
- AC-6 allowlist: `grep -q "attr == 'fullmatch'" plugins/pd/hooks/lib/semantic_memory/test_database.py` ✓
- AC-7 leading-WS: `grep -qE 'leading-space|leading-and-trailing-space' plugins/pd/hooks/lib/semantic_memory/test_database.py` ✓
- AC-8 importorskip: `grep -q 'pytest.importorskip' plugins/pd/hooks/lib/semantic_memory/test_database.py` ✓
- AC-10 unicodedata + script count: `grep -q 'unicodedata' plugins/pd/hooks/lib/semantic_memory/test_database.py` AND parametrize list has ≥13 cases (visual / `grep -cE "^\s*\(.+,\s*'.+-year'\)" plugins/pd/hooks/lib/semantic_memory/test_database.py` ≥ 13) ✓
- AC-11 identity-pin: `grep -qE 'is _config_utils._ISO8601_Z_PATTERN|database._ISO8601_Z_PATTERN is' plugins/pd/hooks/lib/semantic_memory/test_database.py` ✓

### T1.5 — Collection-only fail-fast checkpoint

```bash
plugins/pd/.venv/bin/python -m pytest --collect-only \
  plugins/pd/hooks/lib/semantic_memory/test_database.py::TestIso8601PatternSourcePins -q | tail -3
# Must show "21 tests collected" (no errors)
```

**T1.5 DoD:** Exactly 21 tests collected. Zero collection errors.

### T2 — Quality gates (BEFORE commit)

```bash
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py::TestIso8601PatternSourcePins -q | tail -1   # = "21 passed" (AC-16)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q | tail -1                                # = "$((PRE_NARROW + 14)) passed"  (AC-13; expected 238)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ -q | tail -1                                                                # = "$((PRE_WIDE + 14)) passed"   (AC-14; expected 3222)
./validate.sh                                                                                                                            # exit 0 (AC-15)
git diff develop...HEAD -- \
  plugins/pd/hooks/lib/semantic_memory/_config_utils.py \
  plugins/pd/hooks/lib/semantic_memory/database.py \
  plugins/pd/hooks/lib/semantic_memory/maintenance.py \
  plugins/pd/hooks/lib/semantic_memory/refresh.py \
  plugins/pd/hooks/lib/semantic_memory/memory_server.py \
  plugins/pd/hooks/lib/semantic_memory/conftest.py | wc -l   # = 0 (AC-12)
```

**T2 DoD:**
- AC-16: TestIso8601PatternSourcePins = 21 passed
- AC-13: narrow = `PRE_NARROW + 14` (expect 238)
- AC-14: wide = `PRE_WIDE + 14` (expect 3222)
- AC-15: validate.sh exit 0
- AC-12: scope-guard diff returns 0 lines (no production module touched)

### T3 — Atomic commit + emit `implementation-log.md` + `complete_phase` MCP

**Sequencing:** Write `implementation-log.md` BEFORE committing so both files land in a single atomic commit. This ensures the log is auditable post-merge and present in the feature artifact set.

```bash
# Step 1: write implementation-log.md (template per tasks.md T3)
# (do this BEFORE git add)

# Step 2: stage both files
git add plugins/pd/hooks/lib/semantic_memory/test_database.py \
        docs/features/097-iso8601-test-pin-v2/implementation-log.md

# Step 3: atomic commit
git commit -m "test(semantic_memory): refactor TestIso8601PatternSourcePins for v2 mutation coverage (#00278)

Closes 8 sub-items + bonus identity-pin:
- (a) FR-1: exact-string equality (drops substring negatives)
- (b) FR-2a/b: component flags + lowercase-z behavioral
- (c+d+e) FR-3: AST-walk open-set, allowlist fullmatch only
- (f) FR-4: leading-WS rejection (parametrize 2)
- (g) FR-5: pytest.importorskip class fixture (partial isolation)
- (h) FR-6: curated 13-script + dynamic Nd-coverage assertion
- (i) FR-7: identity-pin database._ISO8601_Z_PATTERN is _config_utils._ISO8601_Z_PATTERN

Net delta: +14 (224 → 238 narrow, 3208 → 3222 wide).
Net production-touch: 0 LOC. Test-only-equivalent risk profile.
QA: validate.sh exit 0; pytest source-pins=21; identity check via
hasattr(database, '_ISO8601_Z_PATTERN') verified at T0.

Closes #00278 (consolidated from #00278-#00285)."
```

Then call `complete_phase(feature_type_id="feature:097-iso8601-test-pin-v2", phase="implement", iterations=1)` per NFR-5 (Tune #3).

**T3 DoD:**
- Single atomic commit on feature branch contains BOTH test_database.py changes AND implementation-log.md
- `implementation-log.md` populated with actual captured T0 baselines (NOT spec-time estimates) + per-task DoD + tooling-friction notes
- workflow-engine `last_completed_phase == "implement"` post-call

### T4 — `/pd:finish-feature`

Run `/pd:finish-feature` on feature 097 branch. Triggers feature 094 Step 5b QA gate against test-only diff. Will be the THIRD production exercise of the gate.

**T4 DoD:**
- 4 reviewers dispatched against test-only diff
- Gate verdict: HIGH=0 → PASS preferred
- Merge to develop, push, v4.16.7 tagged

## AC Coverage Matrix

| AC | Verification | Step |
|----|--------------|------|
| AC-1 (FR-1 exact-string) | grep | T1 |
| AC-2 (FR-2a flag components) | 2 grep checks | T1 |
| AC-3 (FR-2b lowercase-z) | grep | T1 |
| AC-4 (FR-3 open-set) | grep | T1 |
| AC-5 (FR-3 AST-walk) | 2 grep checks | T1 |
| AC-6 (FR-3 allowlist) | grep | T1 |
| AC-7 (FR-4 leading-WS) | grep | T1 |
| AC-8 (FR-5 importorskip) | grep | T1 |
| AC-9 (FR-5 partial-isolation) | manual / non-gating | — |
| AC-10 (FR-6 curated + dynamic) | grep + parametrize count | T1 |
| AC-11 (FR-7 identity-pin) | grep | T1 |
| AC-12 (NFR-1 scope guard) | git diff = 0 | T2 |
| AC-13 (NFR-4 narrow) | pytest = T0+14 | T2 |
| AC-14 (NFR-4 wide) | pytest = T0+14 | T2 |
| AC-15 (validate.sh) | exit 0 | T2 |
| AC-16 (TestIso8601PatternSourcePins survives) | pytest = 21 | T2 |

15 gating ACs binary-verifiable. AC-9 manual non-gating.

## Quality Gates (recap)

- `./validate.sh` exit 0
- `pytest TestIso8601PatternSourcePins` = 21 PASS
- `pytest test_database.py` = `PRE_NARROW + 14` PASS exact
- `pytest plugins/pd/hooks/lib/` = `PRE_WIDE + 14` PASS exact
- Production scope guard: `git diff develop...HEAD -- {6 production files + conftest.py}` empty

## Dependencies

- pytest (already a project dependency)
- Python stdlib: `re`, `inspect`, `ast`, `textwrap`, `unicodedata` (3 of these are NEW imports added by Edit 1a)
- No new external Python packages

## Risks Carried from Design

All 7 risks (R-1..R-7) from design.md. R-7 (mid-T1 partial-edit syntax break) mitigated by T1.5 collection-only checkpoint.

## Out of Scope

Same as spec/design. No expansion.

## Notes — Direct-Orchestrator Hygiene (NFR-5)

Per feature 096 retro Tune #2 + #3 (now in `implementing` skill SKILL.md § Direct-Orchestrator Mode):
- Emit `implementation-log.md` with T0 baselines + per-task DoD outcomes + tooling-friction notes (T3 DoD)
- Call `complete_phase` MCP at implement-phase boundary (T3 DoD)

This is the FIRST feature to dogfood these requirements after they were promoted into the skill SKILL.md.

## Review History

### plan-reviewer iter 1 (2026-04-29) — NOT APPROVED → corrections applied

**Findings:**
- [warning] Edit 1b's New text had 2 trailing blank lines vs file's 1 preserved blank → 3 blanks between classes (PEP-8 E303 risk).
- [warning] T3 sequence emitted implementation-log.md POST-commit, leaving it uncommitted (NFR-5 hygiene gap).
- [suggestion] isort ordering for new imports (sqlite3 → ast → textwrap → unicodedata not alphabetical).

**Corrections Applied:**
- Edit 1b New text reduced to exactly 1 trailing blank line; explanatory note added clarifying file's preserved blank at 2327 yields total 2 blanks (E303 compliant).
- T3 sequencing rewritten: implementation-log.md written FIRST, then BOTH files staged atomically.
- isort suggestion deferred (existing block already non-alphabetical; validate.sh in T2 catches regressions).

### task-reviewer iter 1 (2026-04-29) — NOT APPROVED → corrections applied

**Findings:**
- [blocker] T2 hardcoded `238 passed` / `3222 passed` instead of NFR-4 `PRE_NARROW + 14` formulas.
- [warning] T1 DoD wording "11 grep assertions" inconsistent with AC Coverage summary "10 ACs via grep".
- [suggestion] Implementation-log.md template hardcoded literal baselines (224/3208/7).

**Corrections Applied:**
- T2 commands and DoD switched to `$((PRE_NARROW + 14))` / `$((PRE_WIDE + 14))` formulas; literals retained as advisory parentheticals.
- T1 DoD reworded to "10 ACs verified via 12 grep/count commands"; reconciled with AC Coverage summary.
- Template T0 baselines switched to `{actual_value}` placeholders with spec-time estimates as parentheticals.

### plan-reviewer iter 2 (2026-04-29) — APPROVED

Zero issues. All iter-1 corrections verified in plan.md.

### task-reviewer iter 2 (2026-04-29) — APPROVED

Zero issues. All iter-1 corrections verified in tasks.md.

### phase-reviewer iter 1 (2026-04-29) — APPROVED with 1 warning → fixed

**Findings:**
- [warning] tasks.md T3 git add omitted `implementation-log.md` (plan T3 staged both correctly; tasks.md staged only test_database.py).

**Corrections Applied:**
- tasks.md T3 git add updated to stage both `test_database.py` AND `implementation-log.md` per plan T3 sequencing. DoD reworded to require atomic commit of both files.
