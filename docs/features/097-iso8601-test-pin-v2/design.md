# Design: Feature 097 — Test-pin v2 bundle for `_ISO8601_Z_PATTERN`

## Status
- Created: 2026-04-29
- Phase: design
- Upstream: spec.md (16 ACs, 8 FRs, 6 NFRs); backlog #00278

## Prior Art Research

### Research Conducted

| Question | Source | Finding |
|----------|--------|---------|
| Similar source-pin pattern in this codebase? | feature 095 | `TestIso8601PatternSourcePins` (test_database.py:2256-2309) — established 5-method class using `inspect.getsource()` + attribute pins. Direct precedent. |
| `inspect.getsource()` failure modes for AST-walk? | Python 3 docs | Raises TypeError for builtin/C-extension methods, OSError for missing source. Pure-Python class methods always work. |
| `pytest.importorskip` semantics for test isolation? | pytest 8.x docs | Skips test (or class) when import fails. Used here as belt-and-suspenders against future symbol rename. |
| `unicodedata.category(c) == 'Nd'` enumeration on Python 3.14.4? | empirical | 760 codepoints across 75 distinct scripts. Curated subset of 13 chosen for parametrize coverage. |
| AST-walk for `ast.Call` filter pattern? | Python 3 ast docs | Standard idiom. Allowlist via `node.func.attr == 'fullmatch'` after type-narrowing through ast.Attribute → ast.Name chain. |
| `database._ISO8601_Z_PATTERN` accessible at module level (FR-7 precondition)? | empirical | YES — verified at design time via `python -c "from semantic_memory import database; print(hasattr(database, '_ISO8601_Z_PATTERN'))"` returning `True`. Post-feature-096, `database.py:14` has `from ._config_utils import _ISO8601_Z_PATTERN`, exposing it as a module attribute. Identity check `database._ISO8601_Z_PATTERN is _config_utils._ISO8601_Z_PATTERN` returns `True`. |
| FR-6 13-codepoint Unicode-Nd verification command (re-runnable) | empirical | `python3 -c "import unicodedata; [print(c, unicodedata.category(c)) for c in '２٢२২༢២၂೨௨୨൨๒᮲']"` — all 13 must report `Nd`. Run on Python upgrade per NFR-6. |

### Existing Solutions Evaluated

| Solution | Source | Why Used/Not Used |
|----------|--------|-------------------|
| Substring-based source pins | feature 095 | **Replaced.** Substring is provably weaker than exact-string equality for character-class expansion mutations. |
| `inspect.getsource()` on call-site method bodies | feature 095 | **Retained as base mechanism** but combined with `ast.parse()` for semantic precision. |
| Closed-set parametrize over known call sites | feature 095 | **Replaced.** Open-set discovery via `inspect.getmembers(MemoryDatabase, predicate=inspect.isfunction)` auto-pins future call sites. |
| Bitmask exact pin (`flags == 256`) | considered, rejected | Brittle to Python micro-version flag-default changes. Component-level bitmask check (`flags & re.ASCII`, `not flags & re.IGNORECASE`, etc.) is robust and equally precise. |

### Novel Work Justified

The 8 sub-items + bonus identity-pin require a coordinated rewrite of `TestIso8601PatternSourcePins`. The methods are internally-consistent (each fixes a specific mutation class) but tightly coupled (the AST-walk replacement subsumes 3 sub-items, the import-isolation fixture changes the class structure). A piecemeal sub-item-at-a-time approach would churn through the class twice. Atomic refactor is the natural unit.

## Architecture Overview

Single test class refactor + extension. Net production-touch: 0 LOC. All edits in `plugins/pd/hooks/lib/semantic_memory/test_database.py` `TestIso8601PatternSourcePins` class (lines 2256-2309 currently).

Net test count delta: **+14** (from AC-COUNT in spec).

```
Before (feature 095 baseline):
  TestIso8601PatternSourcePins
    ├── test_pattern_source_uses_explicit_digit_class    (1 test)
    ├── test_pattern_compiled_with_re_ascii_flag         (1 test)
    ├── test_pattern_rejects_unicode_digits_directly     (3 tests, parametrize)
    └── test_call_sites_use_fullmatch_not_match          (2 tests, parametrize)
  Total: 7 tests
  (Note: #00287 added a third assertion *inside* test_pattern_source_uses_explicit_digit_class
   in the prior session — no test-count change; baseline remains 7.)

After (feature 097):
  TestIso8601PatternSourcePins
    ├── (class fixture: pytest.importorskip + getattr probe)  [FR-5]
    ├── test_pattern_source_exact_equality                    (1 test)  [FR-1]
    ├── test_pattern_compiled_flags_components                (1 test)  [FR-2a]
    ├── test_pattern_rejects_lowercase_z                      (1 test)  [FR-2b]
    ├── test_call_sites_only_use_fullmatch                    (1 test, open-set + AST-walk)  [FR-3]
    ├── test_pattern_rejects_leading_whitespace               (2 tests, parametrize)  [FR-4]
    ├── test_pattern_rejects_unicode_digits_directly          (13 tests, expanded parametrize)  [FR-6 curated]
    ├── test_unicode_nd_coverage_matches_python_3_14          (1 test, dynamic coverage)  [FR-6 dynamic]
    └── test_pattern_is_single_source_of_truth                (1 test)  [FR-7]
  Total: 21 tests (Δ = +14)
```

## Components

### C1 — Pattern source-string assertion (FR-1)
- **Purpose:** Pin `_ISO8601_Z_PATTERN.pattern` exact string equality.
- **Inputs:** `_ISO8601_Z_PATTERN.pattern` (str).
- **Outputs:** Pass/fail assertion.
- **Replaces:** `test_pattern_source_uses_explicit_digit_class` (substring `'[0-9]' in` + negative substring `r'\d' not in`, `r'\D' not in`).
- **Notes:** Existing substring assertions are dropped (strictly subsumed by exact-string equality).

### C2 — Flag-component assertions + behavioral z-rejection (FR-2a + FR-2b)
- **Purpose:** Pin flag bitmask robustly + verify lowercase-z rejection.
- **Inputs:** `_ISO8601_Z_PATTERN.flags` (int); `'2026-04-20T00:00:00z'` (str).
- **Outputs:** Pass/fail assertions.
- **Replaces (strengthens):** `test_pattern_compiled_with_re_ascii_flag` (now component-level + lowercase-z behavioral as separate test).

### C3 — AST-walk open-set call-site test (FR-3)
- **Purpose:** Single test that auto-discovers all `MemoryDatabase` methods using `_ISO8601_Z_PATTERN` and verifies they ONLY call `.fullmatch()` on it.
- **Inputs:** `MemoryDatabase` class object.
- **Outputs:** Pass/fail per method-call-site.
- **Replaces:** `test_call_sites_use_fullmatch_not_match` (closed-set parametrize over 2 methods, substring negatives).
- **Stdlib deps:** `inspect`, `ast`, `textwrap`.

### C4 — Leading-WS rejection (FR-4)
- **Purpose:** Verify `_ISO8601_Z_PATTERN.fullmatch()` rejects inputs with leading whitespace.
- **Inputs:** parametrized over 2 cases: `' 2026-04-20T00:00:00Z'`, `'  2026-04-20T00:00:00Z  '`.
- **Outputs:** Pass/fail (assertion `fullmatch is None`).
- **Net new:** trailing-only already covered by `test_pattern_rejects_trailing_whitespace` (#00286).

### C5 — Importorskip fixture (FR-5)
- **Purpose:** Class-level fixture using `pytest.importorskip` + `getattr` probe to provide partial isolation against future symbol rename.
- **Inputs:** `semantic_memory._config_utils` module.
- **Outputs:** `_pattern` fixture or skip/error.
- **Limitation:** Other tests in test_database.py still depend on module-level `_ISO8601_Z_PATTERN` import. Full isolation requires removing all uses, which is out of scope. Best-effort partial isolation only — AC-9 explicitly non-gating.

### C6 — Curated 13-script parametrize + dynamic coverage assert (FR-6)
- **Purpose:** Verify `_ISO8601_Z_PATTERN` rejects digits from 13 distinct Unicode scripts (Bengali, Tibetan, Khmer, Myanmar, Kannada, Tamil, Oriya, Malayalam, Thai, Sundanese + existing 3) AND log expected Python-3.14.4 Nd-script count.
- **Inputs:** `_UNICODE_DIGIT_SCRIPTS` list (13 entries) + `unicodedata` enumeration loop.
- **Outputs:** 13 parametrize cases + 1 dynamic coverage test.
- **Replaces (extends):** `test_pattern_rejects_unicode_digits_directly` (3 → 13 cases).
- **All 13 codepoints empirically verified at spec time** via `unicodedata.category(c) == 'Nd'` on Python 3.14.4.

### C7 — Identity-pin test (FR-7)
- **Purpose:** Verify `database._ISO8601_Z_PATTERN is _config_utils._ISO8601_Z_PATTERN` (single source of truth post-feature-096).
- **Inputs:** module objects.
- **Outputs:** Pass/fail identity comparison.
- **Catches:** local re-shadowing, accidental rebinding, future fork.

## Interfaces

### I-1 — `TestIso8601PatternSourcePins` class structure (post-feature-097)

```python
class TestIso8601PatternSourcePins:
    """Source-level mutation-resistance pins for _ISO8601_Z_PATTERN.

    Feature 097 (#00278): refactored from feature 095's substring/closed-set pins
    to use exact-string equality (FR-1), component-flag assertions (FR-2a),
    behavioral lowercase-z (FR-2b), AST-walk open-set call-site discovery (FR-3),
    leading-WS rejection (FR-4), pytest.importorskip partial-isolation fixture
    (FR-5), curated 13-script Unicode-Nd parametrize + dynamic coverage (FR-6),
    and identity-pin (FR-7).
    """

    EXPECTED_PATTERN = r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'

    @pytest.fixture(autouse=True, scope='class')
    def _pattern_probe(self):
        """FR-5 partial-isolation fixture — see design C5.

        Note: side-effect-only (no return value). Spec FR-5's draft fixture
        body returned `pattern`, but tests still resolve `_ISO8601_Z_PATTERN`
        via the module-level import (line 18 of test_database.py) — the return
        value would be unused. Renaming `_pattern` → `_pattern_probe` reflects
        the side-effect role (skip-or-pass guard), not a parameter-injection
        contract. This is a deliberate design decision diverging from spec
        FR-5's example, captured here for traceability.
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
        """FR-2a — robust to Python flag-default drift."""
        assert _ISO8601_Z_PATTERN.flags & re.ASCII
        assert not (_ISO8601_Z_PATTERN.flags & re.IGNORECASE)
        assert not (_ISO8601_Z_PATTERN.flags & re.MULTILINE)
        assert not (_ISO8601_Z_PATTERN.flags & re.DOTALL)
        assert not (_ISO8601_Z_PATTERN.flags & re.VERBOSE)

    def test_pattern_rejects_lowercase_z(self):
        """FR-2b — defends against `re.ASCII | re.IGNORECASE` mutation."""
        assert _ISO8601_Z_PATTERN.fullmatch('2026-04-20T00:00:00z') is None

    def test_call_sites_only_use_fullmatch(self):
        """FR-3 — open-set + AST-walk + allowlist-only.

        See design C3. Implementation per spec FR-3 pseudocode.
        """
        # ... (per spec FR-3 body, unchanged)

    @pytest.mark.parametrize("leading_input,case_name", [
        (' 2026-04-20T00:00:00Z',     "leading-space"),
        ('  2026-04-20T00:00:00Z  ',  "leading-and-trailing-space"),
    ])
    def test_pattern_rejects_leading_whitespace(self, leading_input, case_name):
        """FR-4 — defends against `now_iso.strip()` pre-fullmatch mutation."""
        assert _ISO8601_Z_PATTERN.fullmatch(leading_input) is None

    @pytest.mark.parametrize("unicode_input,case_name", _UNICODE_DIGIT_SCRIPTS)
    def test_pattern_rejects_unicode_digits_directly(self, unicode_input, case_name):
        """FR-6 curated — 13 scripts. (Renamed parametrize variable list lives
        at module level just above the class — see C6.)"""
        assert _ISO8601_Z_PATTERN.fullmatch(unicode_input) is None

    def test_unicode_nd_coverage_matches_python_3_14(self):
        """FR-6 dynamic — sanity assertion on Python 3.14.4 Nd-script count."""
        # ... (per spec FR-6 body)

    def test_pattern_is_single_source_of_truth(self):
        """FR-7 — identity-pin defends against local re-shadowing."""
        from semantic_memory import database, _config_utils
        assert database._ISO8601_Z_PATTERN is _config_utils._ISO8601_Z_PATTERN
```

### I-2 — Module-level constants (added near top of file, near existing imports)

Add `_UNICODE_DIGIT_SCRIPTS` constant near `TestIso8601PatternSourcePins`:

```python
# Curated Unicode-Nd script samples for FR-6 parametrize.
# Empirically verified on Python 3.14.4 via unicodedata.category(c) == 'Nd'.
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
```

### I-3 — Required stdlib imports (verified per `specifying` skill Self-Check)

The test bodies reference: `re` (already imported at top), `inspect` (already imported), `ast` (NEW), `textwrap` (NEW), `unicodedata` (NEW), `pytest` (already imported).

Add to imports block at top of test_database.py (if not already present):

```python
import ast
import textwrap
import unicodedata
```

(`re`, `inspect`, `pytest` already imported.)

## Cross-File Invariants

Single-file scope reduces cross-file invariants to:

| Invariant | Verification |
|-----------|-------------|
| Scope guard (no production-module diff) | AC-12: `git diff develop...HEAD -- {6 production files + conftest.py}` returns empty. |
| Test count delta (predictable) | AC-13/AC-14: `pytest ... | tail -1` reports `narrow_T0 + 14` / `wide_T0 + 14` exactly. T0 re-captured at implement-start (NFR-4). |
| Source-pin transparency (post-feature-096) | Existing test_pattern_rejects_trailing_whitespace etc. continue passing post-refactor. AC-16: TestIso8601PatternSourcePins reports 21 tests (7 baseline + 14). |

No atomic-commit invariant required (single file, pure-additive test code). No source-pin transparency concern (this feature IS the source-pin refactor).

## Technical Decisions

### TD-1 — Atomic class rewrite vs piecemeal sub-item-at-a-time

- **Choice:** Atomic class rewrite (single commit) covering all 8 sub-items + bonus.
- **Alternatives Considered:**
  1. Piecemeal sub-item commits (one per FR) — Rejected: would churn the class twice (the AST-walk in FR-3 subsumes the closed-set parametrize from feature 095, and the importorskip fixture (FR-5) restructures the class header).
  2. Two commits (refactor + extension) — Rejected: refactor and extension are interleaved (FR-1 strengthens existing, FR-3 replaces existing, FR-4 adds new — no clean split).
- **Trade-offs:** Pros: clean diff, single AC-13 verification point, single quality-gate run. Cons: harder to bisect if a single sub-item regresses (mitigated by per-test failure mode).
- **Rationale:** The class is 50 LOC pre-feature, ~150 LOC post-feature. Refactor diff complexity is bounded.
- **Engineering Principle:** KISS — single coherent diff over fragmented commits.
- **Evidence:** feature 095 retro confirmed the class is internally cohesive; feature 096 retro Tune #2 + #3 documented direct-orchestrator hygiene which applies here.

### TD-2 — Component-flag assertions vs literal bitmask pin

- **Choice:** Component-flag assertions (`flags & re.ASCII`, `not flags & re.IGNORECASE`, etc.).
- **Alternatives Considered:**
  1. Literal bitmask `assert _ISO8601_Z_PATTERN.flags == 256` — Rejected: brittle to Python micro-version changes (e.g. if Python 3.15 adds a new default flag bit).
  2. Dynamic `assert flags == re.compile('', re.ASCII).flags` — Rejected: empirically equivalent to literal pin; doesn't gain robustness.
- **Trade-offs:** Pros: robust to Python flag-default drift; explicit about WHICH mutations are caught. Cons: 5 assertions instead of 1.
- **Rationale:** The point of FR-2a is to catch the `re.ASCII | re.IGNORECASE` mutation (and similar). Component assertions are precise and self-documenting.
- **Engineering Principle:** Defense-in-depth: explicit flag-by-flag invariants > opaque bitmask.
- **Evidence:** Spec FR-2a empirical verification on Python 3.14.4 (`flags == 256 == re.ASCII`).

### TD-3 — AST-walk vs textual substring

- **Choice:** AST-walk (`ast.parse()` + `ast.walk()` + node-type filter).
- **Alternatives Considered:**
  1. Substring search (current) — Rejected: brittle to comments/docstrings (sub-item d), misses `.search(`/`.findall(`/`.finditer(` (sub-item e).
  2. Regex-based search — Rejected: same fragility as substring; AST is structurally precise.
- **Trade-offs:** Pros: comment-immune, semantically precise, allowlist-only (rejects future stdlib regex methods). Cons: slightly more code; one stdlib import (`ast`, `textwrap`).
- **Rationale:** Sub-items d and e require AST-level precision. Sub-item c (open-set discovery) layers on top via `inspect.getmembers`.
- **Engineering Principle:** Use the right abstraction — text for surface checks, AST for semantic checks.
- **Evidence:** Python `ast` module docs (https://docs.python.org/3/library/ast.html); `textwrap.dedent` for de-indenting method source.

### TD-4 — Curated 13-script parametrize vs full enumeration

- **Choice:** Curated 13-script subset + 1 dynamic coverage assert.
- **Alternatives Considered:**
  1. Full enumeration (75 parametrize cases) — Rejected: AC-COUNT delta would explode to +75; brittle to Python Unicode database expansion.
  2. Pure dynamic enumeration (no curated) — Rejected: AC-13/AC-14 binary-verification depends on stable test count; dynamic enumeration would yield drift on Python upgrade.
- **Trade-offs:** Pros: fixed AC-COUNT delta; readable test names; covers major writing systems. Cons: doesn't catch all 75 scripts (75-13 = 62 left uncovered, but they share the same regex-rejection mechanism).
- **Rationale:** Per backlog #00278 sub-item (h): "Bengali, Tibetan, Khmer, Myanmar slip past" — the 4 named scripts plus reasonable extension to 13 (covering all major Indic + East Asian + SE Asian + Sundanese) addresses the backlog ask. The dynamic coverage assert (`>= 70`) ensures Python's `unicodedata` doesn't silently shrink coverage.
- **Engineering Principle:** YAGNI — pin enough to catch realistic mutations; don't over-test.
- **Evidence:** Spec FR-6 empirical verification (75 scripts in Python 3.14.4); backlog sub-item (h) lists 4 named scripts.

### TD-5 — Class-level `pytest.importorskip` fixture vs module-level

- **Choice:** Class-level fixture (`scope='class'`) inside `TestIso8601PatternSourcePins`.
- **Alternatives Considered:**
  1. Module-level — Rejected: would skip all 224 tests on rename, defeating purpose.
  2. Per-test fixture — Rejected: redundant overhead (same import resolution per test).
- **Trade-offs:** Pros: scoped isolation (only this class); zero per-test overhead. Cons: doesn't fully isolate (other tests in file still need module-level import).
- **Rationale:** FR-5's stated goal is partial isolation; full isolation requires architectural change beyond scope. Class-level fixture is the sharpest tool for the job.
- **Engineering Principle:** Scope changes to where they belong.
- **Evidence:** pytest.importorskip docs.

## Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| **R-1**: Python 3.14.4 → 3.15+ Unicode database expansion may shift FR-6 coverage assert threshold (currently `>= 70`). | LOW | NFR-6 trigger: spec re-validation on Python minor-version upgrade. Threshold `>= 70` accommodates ~5 new scripts without revision. |
| **R-2**: `inspect.getsource(method)` fails for C-extension/builtin methods. | LOW | C3 spec body wraps in try/except (TypeError, OSError) — silent skip. MemoryDatabase has only Python-defined methods (verified via inspect — all source-resolvable). |
| **R-3**: T0 baseline drift between spec and implement (other features ship in interim). | LOW | NFR-4: T0 re-capture at implement-start. AC-13/AC-14 use `narrow_T0 + 14` / `wide_T0 + 14` formulation. |
| **R-4**: Future `MemoryDatabase` method that uses qualified-module access (`some_alias._ISO8601_Z_PATTERN.fullmatch(...)`) slips past AST-walk. | LOW | C3 explicitly notes this limitation. AST-walk only handles bare-Name receiver. Mitigated by allowlist-only failure mode (false-positive on novel call form is louder than false-negative). |
| **R-5**: Curated 13-script list misses an obscure script that has known production exposure. | LOW | Dynamic coverage assert ensures total ≥70 in Python's `unicodedata`; per-script rejection is regex-mechanical (any Nd that's not `[0-9]` rejects). Curated list is for explicit traceability, not exhaustive coverage. |
| **R-6**: AC-9 (rename-isolation manual verification) is non-gating but flagged by reviewer as the entire stated value of FR-5. | MEDIUM | Acknowledged in spec narrative + design C5. The "value" of FR-5 is best-effort partial isolation, not full isolation (which requires removing other tests' imports — out of scope). |
| **R-7**: Mid-T1 partial-edit could leave `TestIso8601PatternSourcePins` in syntactically broken state, masquerading as test failures during T2. | LOW | T1.5 `pytest --collect-only` checkpoint catches collection-time syntax/import errors before T2 wide pytest run. Costs ~1s. |

## Dependencies

- pytest (project dependency, already present)
- Python stdlib: `re`, `inspect`, `ast`, `textwrap`, `unicodedata`
- No new external Python packages.

## Test Strategy

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
| AC-10 (FR-6 curated + dynamic) | grep + count | T1 |
| AC-11 (FR-7 identity-pin) | grep | T1 |
| AC-12 (NFR-1 production guard) | git diff returns empty | T2 |
| AC-13 (NFR-4 narrow) | pytest count = T0+14 | T2 |
| AC-14 (NFR-4 wide) | pytest count = T0+14 | T2 |
| AC-15 (validate.sh) | exit 0 | T2 |
| AC-16 (TestIso8601PatternSourcePins) | pytest count = 21 | T2 |

All 16 ACs are binary-verifiable (15 gating + 1 manual non-gating).

## Implementation Order (Direct-Orchestrator)

Direct-orchestrator pattern applies (single test file, sequential edits, per spec NFR-5):

1. **T0**: Capture baselines (PRE_HEAD, PRE_NARROW, PRE_WIDE, PRE_SOURCE_PINS). Verify FR-7 precondition: `python3 -c "from semantic_memory import database; assert hasattr(database, '_ISO8601_Z_PATTERN')"` succeeds. Verify FR-6 13-codepoint Unicode-Nd categorization.
2. **T1**: Edit `test_database.py` — single atomic edit covering all 7 components C1-C7 + module-level constant + new imports. Run grep DoD (AC-1..AC-11).
3. **T1.5**: Collection-only fail-fast checkpoint — `pytest --collect-only plugins/pd/hooks/lib/semantic_memory/test_database.py::TestIso8601PatternSourcePins -q` reports 21 tests collected (no syntax/import errors). Cheap (~1s) sanity gate before wide pytest. Catches mid-T1 partial-edit syntax breaks.
4. **T2**: Quality gates — pytest narrow + wide + source-pins + validate.sh (AC-12..AC-16).
5. **T3**: Commit + emit `implementation-log.md` per direct-orchestrator hygiene (NFR-5). Call `complete_phase` MCP at implement-phase boundary.
6. **T4**: `/pd:finish-feature` → release v4.16.7.

Per feature 096 retro Tune #2 + #3 (now in implementing skill SKILL.md):
- `implementation-log.md` MUST contain T0 baselines + per-task DoD outcomes + tooling-friction notes.
- `complete_phase` MUST be called explicitly at implement-phase boundary (default subagent-dispatch flow does this; direct-orchestrator does not).

## Out of Scope

Same as spec. No expansion.

## Notes

- Feature dogfoods all three feature-096 retro Tunes:
  - Tune #1 (design template Cross-File Invariants) — applied as single-file scope-guard table.
  - Tune #2 (implementation-log.md emission) — required by NFR-5.
  - Tune #3 (explicit complete_phase) — required by NFR-5.
- Net production-touch: 0 LOC. Net test-touch: ~+100 LOC (refactor + 14 new test cases).
- This is the THIRD production exercise of feature 094's pre-release QA gate (after 095 first-run, 096 second-run). Will validate gate handles a test-only feature.
