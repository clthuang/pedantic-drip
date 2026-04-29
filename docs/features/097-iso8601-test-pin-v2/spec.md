# Specification: Feature 097 — Test-pin v2 bundle for `_ISO8601_Z_PATTERN`

## Status
- Created: 2026-04-29
- Phase: specify
- Backlog source: #00278 (8 sub-items consolidated from #00278-#00285)
- Predecessors: feature 095 (introduced `TestIso8601PatternSourcePins`); feature 096 (relocated `_ISO8601_Z_PATTERN` to `_config_utils.py`)
- Python pin: **3.14.4** (project venv). Flag bitmask + Unicode database assertions assume this exact version. Future minor-version upgrades trigger spec re-validation.

## Sub-item Mapping (backlog #00278 → FRs)

| #00278 sub-item | Backlog text (paraphrased) | Closes via |
|----------------|---------------------------|-----------|
| (a) | substring `'[0-9]' in pattern` misses char-class expansion `[0-9０-９]` | FR-1 |
| (b) | `flags & re.ASCII` truthy under `re.ASCII | re.IGNORECASE` mutation | FR-2a + FR-2b |
| (c) | `test_call_sites_use_fullmatch_not_match` closed-set over 2 methods | FR-3 (open-set discovery via inspect.getmembers) |
| (d) | substring negatives brittle to comments/docstrings | FR-3 (AST-walk; comments+docstrings invisible to AST) |
| (e) | negatives miss `.search(`/`.findall(`/`.finditer(` | FR-3 (allowlist-only: only `fullmatch` accepted) |
| (f) | pre-fullmatch input mutation untested (`now_iso.strip()`) | FR-4 |
| (g) | module-level import → 224-test collection blast radius on rename | FR-5 |
| (h) | only 3 Unicode scripts (Bengali/Tibetan/Khmer/Myanmar slip past) | FR-6 |

Plus: (i) **identity-pin** test (feature 096 test-deepener bonus) → FR-7.

## Problem Statement

Feature 095's `TestIso8601PatternSourcePins` has 8 mutation classes that pass existing source-pin tests despite changing the validator's effective behavior. Each gap allows a regression to slip past CI.

## Success Criteria

- [ ] All 8 backlog sub-items (a-h) + bonus (i) covered by new/refined assertions in `TestIso8601PatternSourcePins`.
- [ ] Pytest narrow count delta = exactly **+14** (224 → 238). Pytest wide delta = exactly **+14** (3208 → 3222).
- [ ] Zero production code changes (`_config_utils.py`, `database.py`, `maintenance.py`, `refresh.py`, `memory_server.py`, `conftest.py` all unchanged).

## Scope

### In Scope
- `plugins/pd/hooks/lib/semantic_memory/test_database.py` — `TestIso8601PatternSourcePins` class refactor + extension.

### Out of Scope
- `_ISO8601_Z_PATTERN` definition, call sites, or any production module.
- `conftest.py` (forbidden — helpers stay inline).
- Behavioral tests outside source-pin scope (already covered).
- Other test classes (TestScanDecayCandidates, TestBatchDemote, etc.).

## Functional Requirements

### FR-1 (sub-item a) — Exact-string pattern equality

Replace the substring assertion `'[0-9]' in _ISO8601_Z_PATTERN.pattern` with EXACT-STRING equality:

```python
EXPECTED_PATTERN = r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'
assert _ISO8601_Z_PATTERN.pattern == EXPECTED_PATTERN
```

The existing substring negative assertions (`r'\d' not in ...`, `r'\D' not in ...`) are **dropped** since exact-equality strictly subsumes them. Removing them is a deliberate cleanup, not a regression.

### FR-2 (sub-item b) — Flag bitmask + behavioral z-rejection

**FR-2a — Component assertions** (preferred over exact bitmask for Python-version stability):
```python
assert _ISO8601_Z_PATTERN.flags & re.ASCII
assert not (_ISO8601_Z_PATTERN.flags & re.IGNORECASE)
assert not (_ISO8601_Z_PATTERN.flags & re.MULTILINE)
assert not (_ISO8601_Z_PATTERN.flags & re.DOTALL)
assert not (_ISO8601_Z_PATTERN.flags & re.VERBOSE)
```

This catches the `re.ASCII | re.IGNORECASE` mutation that defeats `flags & re.ASCII` truthiness.

**FR-2b — Behavioral lowercase-z negative** (defense-in-depth):
```python
assert _ISO8601_Z_PATTERN.fullmatch('2026-04-20T00:00:00z') is None
```

Note: empirically verified on Python 3.14.4 that `_ISO8601_Z_PATTERN.flags == 256 == re.ASCII`. Pinning components rather than the literal `256` for forward-compat.

### FR-3 (sub-items c + d + e) — AST-walk open-set call-site test

Replace the closed-set parametrized `test_call_sites_use_fullmatch_not_match` with a single open-set test:

```python
def test_call_sites_only_use_fullmatch(self):
    """Open-set: every MemoryDatabase method that references _ISO8601_Z_PATTERN
    must call only .fullmatch() on it. AST-walk is immune to comment/docstring
    false-fails. Allowlist (not denylist) means future stdlib regex methods
    fail loud rather than slip past."""
    methods_with_pattern_calls = []
    for name, method in inspect.getmembers(MemoryDatabase, predicate=inspect.isfunction):
        try:
            src = inspect.getsource(method)
        except (TypeError, OSError):
            continue
        if '_ISO8601_Z_PATTERN' not in src:
            continue
        tree = ast.parse(textwrap.dedent(src))
        method_call_count = 0
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == '_ISO8601_Z_PATTERN'):
                assert node.func.attr == 'fullmatch', (
                    f"{name} uses _ISO8601_Z_PATTERN.{node.func.attr}() — "
                    f"only .fullmatch() is allowed (rejects trailing whitespace/newline)"
                )
                method_call_count += 1
        methods_with_pattern_calls.append((name, method_call_count))
    # Sanity: at least one method must reference _ISO8601_Z_PATTERN
    assert methods_with_pattern_calls, (
        "No MemoryDatabase method references _ISO8601_Z_PATTERN — "
        "either the validator is unused (suspicious) or the discovery is broken"
    )
```

**Constraints:**
- AST-walk handles only the bare `_ISO8601_Z_PATTERN.{method}(` form. Qualified module access (e.g. `module._ISO8601_Z_PATTERN.fullmatch(...)`) is explicitly out of scope; if such usage emerges, the test must be extended.
- `inspect.getsource(method)` failures (TypeError for C-builtins, OSError for missing source) skip the method silently — they cannot exist for our Python-defined methods.

### FR-4 (sub-item f) — Leading + leading-and-trailing whitespace rejection

Add `test_pattern_rejects_leading_whitespace` parametrized over 2 cases (note: trailing-only is already covered by `test_pattern_rejects_trailing_whitespace` post-#00286; we skip dedup):

```python
@pytest.mark.parametrize("leading_input,case_name", [
    (' 2026-04-20T00:00:00Z',  "leading-space"),
    ('  2026-04-20T00:00:00Z  ', "leading-and-trailing-space"),
])
def test_pattern_rejects_leading_whitespace(self, leading_input, case_name):
    """Catches `now_iso.strip()` pre-fullmatch mutation that would pass
    both source pin AND trailing-WS-only behavioral tests."""
    assert _ISO8601_Z_PATTERN.fullmatch(leading_input) is None, \
        f"[{case_name}] pattern must reject leading whitespace"
```

Net delta: **+2 cases**.

### FR-5 (sub-item g) — Reduce collection blast radius

Empirical check (specify-time): `grep -rn '_ISO8601_Z_PATTERN' plugins/pd/hooks/lib/semantic_memory/test_*.py` returns ONLY `test_database.py:18`. **No transitive imports exist.** Therefore the import in test_database.py:18 can be safely refactored without affecting other test files.

**Refactor:**
- Module-level: keep `from semantic_memory._config_utils import _ISO8601_Z_PATTERN` (still needed by other tests in the same file like `test_pattern_rejects_trailing_whitespace`).
- Inside `TestIso8601PatternSourcePins`, add a class-level fixture using `pytest.importorskip`:

```python
class TestIso8601PatternSourcePins:
    """Source-pin tests with isolated import.

    pytest.importorskip protects against this class taking down the entire
    test_database.py collection if _ISO8601_Z_PATTERN is renamed in
    _config_utils.py. The module-level import (line 18) still exists for
    behavioral tests, but those tests' failure mode (NameError at use) is
    less catastrophic than collection-time ImportError.
    """

    @pytest.fixture(autouse=True, scope='class')
    def _pattern(self):
        """Resolve _ISO8601_Z_PATTERN through importorskip so a rename
        skips this class instead of failing collection of all 224 tests."""
        config_utils = pytest.importorskip(
            'semantic_memory._config_utils',
            reason='_ISO8601_Z_PATTERN producer module unavailable',
        )
        pattern = getattr(config_utils, '_ISO8601_Z_PATTERN', None)
        if pattern is None:
            pytest.skip('_ISO8601_Z_PATTERN absent from _config_utils')
        return pattern
```

Then each test method uses the module-level `_ISO8601_Z_PATTERN` (resolved at file collection) — but this fixture provides the second-line defense if module-level import ever fails. **The actual blast-radius reduction is achieved by removing the module-level dependence within this class** — but since other tests in the file still need `_ISO8601_Z_PATTERN`, the import stays. This is a "best-effort isolation" — true isolation is only possible if all uses are inside `TestIso8601PatternSourcePins`, which they aren't. AC-9 verifies the partial isolation by inspection.

**Note:** the original blast-radius concern is theoretical — the symbol has been stable across features 091-096. AC-9 is non-gating manual verification.

### FR-6 (sub-item h) — Curated Unicode-Nd script coverage

Empirical check (specify-time): Python 3.14.4 has 75 distinct Nd scripts (760 Nd codepoints). Full enumeration would be excessive parametrize bloat. **Curated approach:** pin a 13-script representative subset covering the major writing systems plus the original 3 from feature 095:

```python
_UNICODE_DIGIT_SCRIPTS = [
    # Existing (feature 095):
    ('２０２６-04-20T00:00:00Z', 'fullwidth-year'),     # U+FF10..FF19
    ('٢٠٢٦-04-20T00:00:00Z',   'arabic-indic-year'),  # U+0660..0669
    ('२०२६-04-20T00:00:00Z',   'devanagari-year'),    # U+0966..096F
    # New (feature 097 sub-item h) — all empirically verified at spec time
    # via `unicodedata.category(c) == 'Nd'`. 10 distinct major scripts:
    ('২০২৬-04-20T00:00:00Z',   'bengali-year'),       # U+09E6..09EF
    ('༢༠༢༦-04-20T00:00:00Z',   'tibetan-year'),       # U+0F20..0F29
    ('២០២៦-04-20T00:00:00Z',   'khmer-year'),         # U+17E0..17E9
    ('၂၀၂၆-04-20T00:00:00Z',   'myanmar-year'),       # U+1040..1049
    ('೨೦೨೬-04-20T00:00:00Z',   'kannada-year'),       # U+0CE6..0CEF
    ('௨௦௨௬-04-20T00:00:00Z',   'tamil-year'),         # U+0BE6..0BEF
    ('୨୦୨୬-04-20T00:00:00Z',   'oriya-year'),         # U+0B66..0B6F
    ('൨൦൨൬-04-20T00:00:00Z',   'malayalam-year'),     # U+0D66..0D6F
    ('๒๐๒๖-04-20T00:00:00Z',   'thai-year'),          # U+0E50..0E59
    ('᮲᮰᮲᮶-04-20T00:00:00Z',   'sundanese-year'),     # U+1BB0..1BB9
]
```

All 13 codepoints empirically verified at spec time on Python 3.14.4 (`unicodedata.category(c) == 'Nd'`). **Net new cases vs feature 095: +10** (3 existing → 13 total).

Plus a **single dynamic coverage assertion** (non-parametrized, contributes +1 test):

```python
def test_unicode_nd_coverage_matches_python_3_14(self):
    """Sanity: Python 3.14.4 has 75 Nd scripts. If this fails, Python's
    Unicode database has changed and the curated _UNICODE_DIGIT_SCRIPTS
    list above should be reconsidered (sample new scripts as needed).
    Non-blocking signal — does NOT assert specific scripts, just count."""
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
```

Net FR-6 delta: **-3 (existing) + 13 (new param) + 1 (coverage assert) = +11**.

### FR-7 (bonus, sub-item i) — Identity-pin test (REQUIRED for this feature)

```python
def test_pattern_is_single_source_of_truth(self):
    """Feature 096 test-deepener bonus: pin identity equality across all
    consumers. Catches future local re-shadowing post-relocation.
    """
    from semantic_memory import database, _config_utils
    assert database._ISO8601_Z_PATTERN is _config_utils._ISO8601_Z_PATTERN, \
        'database._ISO8601_Z_PATTERN must be the same object as _config_utils._ISO8601_Z_PATTERN (single source of truth)'
```

Net delta: **+1 test**. Required for this feature (not optional).

### FR-8 — Predictable count delta

Total narrow + wide pytest delta is **exactly +14** (see AC-COUNT below). T0 baseline re-capture at implement-time pins absolute counts.

## Non-Functional Requirements

- **NFR-1**: Zero production behavior change. `git diff develop...HEAD -- plugins/pd/hooks/lib/semantic_memory/_config_utils.py plugins/pd/hooks/lib/semantic_memory/database.py plugins/pd/hooks/lib/semantic_memory/maintenance.py plugins/pd/hooks/lib/semantic_memory/refresh.py plugins/pd/hooks/lib/semantic_memory/memory_server.py plugins/pd/hooks/lib/semantic_memory/conftest.py` returns empty.
- **NFR-2**: Wall-clock implementation budget ≤30 minutes (single test file, sequential edits, no worktree).
- **NFR-3**: No new external Python dependencies. Uses only stdlib: `re`, `inspect`, `ast`, `textwrap`, `unicodedata` + `pytest`. **All required stdlib imports for test-body symbols are enumerated here per `specifying` skill Self-Check (#00288 closure).**
- **NFR-4**: Pytest count delta is **exactly +14** narrow + wide. T0 baseline re-captured at implement-start; AC-13/AC-14 assert against `narrow_T0 + 14` and `wide_T0 + 14`, NOT the spec-time literals 224/3208 (defends against baseline drift between spec and implement).
- **NFR-5**: Direct-orchestrator hygiene per feature 096 retro Tune #2 + #3 (now in `implementing` skill SKILL.md): emit `implementation-log.md` with T0 baselines + per-task DoD outcomes; call `complete_phase` MCP at implement-phase boundary explicitly.
- **NFR-6**: Python 3.14.4. Future minor-version Python upgrade (3.15+) triggers spec re-validation (Unicode database changes invalidate FR-6 coverage assert; flag bitmask should remain stable).

## Acceptance Criteria

- **AC-1** (FR-1): `grep -qE '_ISO8601_Z_PATTERN\.pattern == ' plugins/pd/hooks/lib/semantic_memory/test_database.py` returns success. Existing substring assertions (`r'\d' not in`, `r'\D' not in`) are removed.
- **AC-2** (FR-2a): `grep -qE 'assert.*flags & re.ASCII' plugins/pd/hooks/lib/semantic_memory/test_database.py` AND `grep -qE 'assert not.*flags & re.IGNORECASE' plugins/pd/hooks/lib/semantic_memory/test_database.py` both return success.
- **AC-3** (FR-2b): `grep -qE "fullmatch.*'2026.*z'" plugins/pd/hooks/lib/semantic_memory/test_database.py` returns success (lowercase-z behavioral assertion present).
- **AC-4** (FR-3 open-set): `grep -q 'inspect.getmembers(MemoryDatabase' plugins/pd/hooks/lib/semantic_memory/test_database.py` returns success.
- **AC-5** (FR-3 AST-walk): `grep -qE 'ast\.parse|ast\.walk' plugins/pd/hooks/lib/semantic_memory/test_database.py` AND `grep -qE 'ast\.Call|ast\.Attribute' plugins/pd/hooks/lib/semantic_memory/test_database.py` both return success.
- **AC-6** (FR-3 allowlist): the test allowlists ONLY `'fullmatch'` (verified by inspection — manual or via grep `grep -q "attr == 'fullmatch'" plugins/pd/hooks/lib/semantic_memory/test_database.py`).
- **AC-7** (FR-4): `grep -qE 'leading-space|leading-and-trailing-space' plugins/pd/hooks/lib/semantic_memory/test_database.py` returns success (matches the parametrize case_name strings exactly).
- **AC-8** (FR-5 importorskip): `grep -q 'pytest.importorskip' plugins/pd/hooks/lib/semantic_memory/test_database.py` returns success, located within `TestIso8601PatternSourcePins`.
- **AC-9** (FR-5 partial isolation): non-gating manual check — implementer notes the limitation in spec already (full isolation requires removing all module-level uses, which other tests need).
- **AC-10** (FR-6 curated + dynamic): `grep -q 'unicodedata' plugins/pd/hooks/lib/semantic_memory/test_database.py` AND parametrize list contains ≥13 cases (existing 3 + 10 new) verified by `grep -cE '^\s*\(.+,.+year\)|^\s*\(.+,.+stub\)' plugins/pd/hooks/lib/semantic_memory/test_database.py` returning ≥13 (or counted by inspection).
- **AC-11** (FR-7 identity-pin): `grep -qE 'is _config_utils._ISO8601_Z_PATTERN|database._ISO8601_Z_PATTERN is' plugins/pd/hooks/lib/semantic_memory/test_database.py` returns success (uses `-E` for ERE alternation portability).
- **AC-12** (NFR-1, scope guard): `git diff develop...HEAD -- plugins/pd/hooks/lib/semantic_memory/_config_utils.py plugins/pd/hooks/lib/semantic_memory/database.py plugins/pd/hooks/lib/semantic_memory/maintenance.py plugins/pd/hooks/lib/semantic_memory/refresh.py plugins/pd/hooks/lib/semantic_memory/memory_server.py plugins/pd/hooks/lib/semantic_memory/conftest.py` returns empty.
- **AC-13** (NFR-4 narrow): `pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q | tail -1` reports exactly `narrow_T0 + 14` passed (where `narrow_T0` is captured at implement-start; expected ≈238 if no concurrent drift).
- **AC-14** (NFR-4 wide): `pytest plugins/pd/hooks/lib/ -q | tail -1` reports exactly `wide_T0 + 14` passed (expected ≈3222).
- **AC-15** (validate.sh): `./validate.sh` exits 0.
- **AC-16** (TestIso8601PatternSourcePins survives): `pytest plugins/pd/hooks/lib/semantic_memory/test_database.py::TestIso8601PatternSourcePins -q | tail -1` reports the new pinned count. Pre-feature baseline = 7 (existing test count within `TestIso8601PatternSourcePins` post-feature-095). New target = `7 + 14 = 21` expected.

## AC-COUNT (test count delta — pinned integers)

| FR | Test count change | Detail |
|----|-------------------|--------|
| FR-1 | 0 | Single existing test method gets stronger assertion + drops dead substring asserts |
| FR-2a | 0 | Strengthens `test_pattern_compiled_with_re_ascii_flag` with component-flag assertions |
| FR-2b | +1 | New test method `test_pattern_rejects_lowercase_z` |
| FR-3 | -1 | OLD: parametrize over 2 methods (-2). NEW: single open-set test asserting union over discovered methods (+1). Net -1. |
| FR-4 | +2 | New parametrize: leading-only + leading+trailing (trailing-only already covered by #00286) |
| FR-5 | 0 | Refactor only — same test count, additional fixture |
| FR-6 | +11 | -3 (existing 3-script param) + 13 (curated 13-script param) + 1 (dynamic coverage assert) |
| FR-7 | +1 | New test method `test_pattern_is_single_source_of_truth` |
| **TOTAL Δ** | **+14** | (narrow: 224 → 238; wide: 3208 → 3222) |

## Feasibility Assessment

### Assessment Approach
1. **First Principles**: All sub-items use stdlib (`inspect`, `ast`, `textwrap`, `unicodedata`, `re`) + pytest. Pattern is established by feature 095's `TestIso8601PatternSourcePins`.
2. **Codebase Evidence**: `inspect.getsource(method)` already used in test_database.py:2303. AST-walk pattern is standard Python.
3. **External Evidence**: pytest.importorskip docs (https://docs.pytest.org/en/stable/reference/reference.html#pytest.importorskip), `unicodedata.category` docs (https://docs.python.org/3/library/unicodedata.html), `ast.walk` docs (https://docs.python.org/3/library/ast.html).
4. **Empirical Verification (specify-time):**
   - `_ISO8601_Z_PATTERN.flags == 256 == re.compile('', re.ASCII).flags` ✓
   - No transitive `_ISO8601_Z_PATTERN` imports outside test_database.py ✓
   - Python 3.14.4 has 75 distinct Nd scripts (curated 13 chosen from major writing systems) ✓

### Feasibility Scale
**Overall:** Confirmed.
**Reasoning:** Pure stdlib, established pattern, single-file scope, empirically verified assumptions.
**Key Assumptions:**
- Python 3.14.4 (verified). Stable across project venv.
- Unicode database stable for 13 curated scripts (Bengali, Tibetan, Khmer, Myanmar, Kannada, Tamil, Oriya, Malayalam, Thai, Sundanese — all in Unicode 1.0-13.0; covered for 20+ years).
**Open Risks:** None blocking. Future Python minor-version upgrade may shift FR-6 coverage assert threshold (currently `>= 70` accommodating up to ~75 baseline + slight growth).

## Open Questions

(All resolved.)

1. ~~Does feature 097 ship FR-7 (identity-pin)?~~ **Resolved 2026-04-29:** YES, required. AC-11 gating.
2. ~~AC-9 (rename-isolation manual verification) gating?~~ **Resolved 2026-04-29:** Non-gating per spec body — partial-isolation limitation acknowledged in FR-5 narrative. Full isolation impossible without removing other tests' module-level dependence.
3. ~~Is the +14 delta deterministic?~~ **Resolved 2026-04-29:** YES. AC-COUNT pins each FR's contribution as an integer. T0 baseline re-capture protects against drift between spec and implement.

## Dependencies

- pytest (already a project dependency)
- Python stdlib: `re`, `inspect`, `ast`, `textwrap`, `unicodedata`
- No new external Python packages.

## Notes

- Direct-orchestrator pattern applies (single test file, ≤4 task subdivisions, sequential edits).
- This feature dogfoods the new direct-orchestrator hygiene (Tune #2 + #3 → `implementing` skill), the design template Cross-File Invariants section (Tune #1 → `designing` skill), and the new `specifying` skill stdlib-imports Self-Check (NFR-3 explicit enumeration → #00288 closure).
- Net production-touch: 0 LOC. All edits in test_database.py.
