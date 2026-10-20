# PRD: Feature 093 — 092 QA Residual Hotfix

## Status
- Created: 2026-04-24
- Stage: Draft
- Problem Type: Product/Feature
- Archetype: fixing-something-broken
- Source: Backlog #00219, #00220, #00221

## Summary

Surgical hotfix addressing 3 findings from feature:092 post-release adversarial QA — 1 HIGH (#00219 Unicode-digit bypass of `_ISO8601_Z_PATTERN`) + 2 MED (#00220 `$`-anchor trailing-newline bypass; #00221 `batch_demote` `not now_iso` guard is narrower than timestamp-validity). All three findings trace to a single root cause: **FR-5 and FR-8 validation are asymmetric and shallow**. One unified fix — hardened regex (`re.ASCII` + `[0-9]` instead of `\d`) + `re.fullmatch()` instead of `re.match()` + symmetric application to both `scan_decay_candidates` AND `batch_demote` — closes all three findings.

Target: v4.16.2 patch release. Direct-orchestrator implementation per 090/092 surgical-hotfix template. Scope is ~20 LOC production + ~50 LOC tests.

## Problem

Feature 092 (shipped as v4.16.1 on 2026-04-24) introduced `_ISO8601_Z_PATTERN` at `plugins/pd/hooks/lib/semantic_memory/database.py:17` and used it to validate `scan_decay_candidates(not_null_cutoff=...)`. It also added an empty-string guard to `batch_demote(now_iso=...)`. Post-release adversarial QA by 3 parallel reviewers (security, code-quality, test-deepener) found 3 related defects:

1. **#00219 [HIGH] Unicode-digit homograph bypass.** Pattern `r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$'` — in Python 3's `re` module, `\d` in a `str` pattern matches all Unicode digit code points (category `Nd`), not just ASCII `[0-9]`. An attacker-crafted cutoff like `'２０２６-04-20T00:00:00Z'` (fullwidth digits) or `'٢٠٢٦-04-20T00:00:00Z'` (Arabic-Indic) passes the regex but is NOT a valid ASCII ISO-8601 timestamp. SQLite `WHERE last_recalled_at < ?` with a non-ASCII string produces undefined lex ordering — rows may be incorrectly included or excluded. — Evidence: https://docs.python.org/3/library/re.html#re.ASCII and `plugins/pd/hooks/lib/semantic_memory/database.py:17`.

2. **#00220 [MED] `$` anchor trailing-newline bypass.** `_ISO8601_Z_PATTERN.match(x)` with pattern ending in `$` matches `'2026-04-20T00:00:00Z\n'` successfully because `$` (without `re.MULTILINE`) still matches BEFORE a trailing `\n`. Log-injection vector if the cutoff is later echoed to stderr (the warning at `database.py:994` uses `{not_null_cutoff!r}` which repr-escapes the newline, mitigating direct injection, but the format check was intended to reject trailing whitespace). — Evidence: https://docs.python.org/3/library/re.html#re.search ("`$` matches at the end of the string and immediately before the newline (if any) at the end of the string").

3. **#00221 [MED] `batch_demote` guard semantically narrower than timestamp-validity.** `if not now_iso:` catches empty string only. The following all pass:
   - `"   "` (whitespace-only) → SQLite stores 3-space `updated_at`; lex compare `updated_at < '2026...'` evaluates TRUE because space (`0x20`) < digit (`0x30`). Idempotency guard silently inverted.
   - `"\n"` (newline-only) → same pattern.
   - `"​"` (U+200B zero-width space) — non-empty, visually empty.
   - `"10000-01-01T00:00:00Z"` (5-digit year) — SQLite lex compares char-by-char; `'1' < '2'` so `'10000...' < '2026...'` evaluates TRUE when it should be FALSE. **Year-10000 class bug.**
— Evidence: `plugins/pd/hooks/lib/semantic_memory/database.py:1055`.

**Root-cause unification:** FR-5 validates read-path format; FR-8 validates only write-path emptiness. The asymmetry — symmetric inputs, asymmetric validation depth — is the structural gap. Applying the same hardened `_ISO8601_Z_PATTERN` to BOTH paths closes all 3 findings with one regex edit + one new validation line in `batch_demote`.

## Target User

Single operator of the pd plugin on macOS (personal tooling). No external users. Shared-host threat model: adversarial input can reach `scan_decay_candidates` via config file poisoning or cross-project memory DB (future multi-tenant). Current production caller (`_iso_utc`) provably cannot emit Unicode digits or trailing newlines, so this is defense-in-depth, not a live exploit. Multi-tenant threat model (future multi-project memory DB sharing) is out of scope for 093; deferred to a future backlog item if adopted.

## Success Criteria

**Functional:**
1. **#00219 closed:** `_ISO8601_Z_PATTERN` rejects Unicode-digit inputs. New pytest `test_pattern_rejects_unicode_digits` seeds `'２０２６-04-20T00:00:00Z'`, `'٢٠٢٦-04-20T00:00:00Z'`, `'०२०२६-04-20T00:00:00Z'` and asserts `pattern.fullmatch(x) is None` for each.
2. **#00220 closed:** pattern usage rejects trailing-newline input. `pattern.fullmatch('2026-04-20T00:00:00Z\n')` returns None. New pytest `test_pattern_rejects_trailing_newline`.
3. **#00221 closed:** `batch_demote` applies the same regex to `now_iso`. `batch_demote(['x'], 'medium', '   ')`, `batch_demote(['x'], 'medium', '10000-01-01T00:00:00Z')`, and `batch_demote(['x'], 'medium', '2026-04-20T00:00:00Z\n')` all raise `ValueError`. Empty-ids short-circuit preserved: `batch_demote([], 'medium', 'garbage')` still returns 0.

**Non-functional:**
1. LOC budget: ≤ +30 production, ≤ +80 tests.
2. Zero regressions in `test_maintenance.py`, `test_database.py`, `test-hooks.sh`.
3. `./validate.sh` passes; `pd:doctor` passes.
4. Reviewer iterations ≤ 2 per phase (per recurring 090/092 pattern).
5. Symmetry invariant: FR-5 + FR-8 use the SAME pattern constant. No duplication — single `_ISO8601_Z_PATTERN` module-level def, called from both methods.

**Structural (carry-forward from 092 Structural Success Criterion):**
1. **Binding gate:** post-merge adversarial QA by 4 parallel reviewers (security + code-quality + test-deepener Phase A + implementation-reviewer) surfaces **≤ 2 MED findings and zero HIGH**. If a new HIGH surfaces, freeze scope; file as separate backlog. (Non-binding trend observation: 091→24 findings, 092→18 — monotonic decrease expected but not a pass/fail criterion.)

## Constraints

- Personal tooling — no backward-compatibility shims.
- Python 3 stdlib only; no new deps.
- Base branch: `develop` (currently at 4.16.1-dev).
- Release: v4.16.2 via `scripts/release.sh --ci`.
- **Hard constraint: symmetric validation.** FR-5 and FR-8 MUST use the same `_ISO8601_Z_PATTERN` (not two independent patterns). One source of truth; single test verifies pattern correctness; both call sites inherit.
- **Must preserve existing production contract:** current prod caller uses `_iso_utc()` output which produces valid Z-suffix ASCII strings. Hardened regex MUST continue to accept `_iso_utc(now)` output. Test: `test_pattern_matches_iso_utc_output` (already exists from 092 FR-5).
- **Do NOT change log-and-skip philosophy for FR-5** (TD-2 from 092): rejected cutoff still returns empty generator + stderr warning, no exception.
- **FR-8 raise-on-invalid stays** (TD-3 from 092): read-vs-write asymmetry justifies raising on write path. Invalid `now_iso` raises `ValueError` with specific message.

## Research Summary

### Codebase verification (pre-093 start)
- `database.py:17`: `_ISO8601_Z_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')` — current state, confirmed. — Evidence: `plugins/pd/hooks/lib/semantic_memory/database.py:17`.
- `database.py:991-997`: `if not _ISO8601_Z_PATTERN.match(not_null_cutoff):` in `scan_decay_candidates` — current call site uses `.match()` not `.fullmatch()`. — Evidence: `plugins/pd/hooks/lib/semantic_memory/database.py:991`.
- `database.py:1055`: `if not now_iso: raise ValueError(...)` in `batch_demote` — empty-string only check. — Evidence: `plugins/pd/hooks/lib/semantic_memory/database.py:1055`.
- `_iso_utc` helper: emits `strftime("%Y-%m-%dT%H:%M:%SZ")` — ASCII Z-suffix, no microseconds, no trailing newline. — Evidence: `plugins/pd/hooks/lib/semantic_memory/_config_utils.py:31-47`.

### External Research
- **Python `re` module Unicode semantics:** Bare `\d` in `str` patterns matches `[0-9]` PLUS all Unicode digits (category Nd). `re.ASCII` flag restricts `\d`, `\w`, `\s` to ASCII. `[0-9]` literal is always ASCII-only regardless of flags. — Evidence: https://docs.python.org/3/library/re.html#re.ASCII and https://docs.python.org/3/howto/regex.html#non-greedy.
- **Python `re` module anchor semantics:** `$` matches end-of-string OR immediately before trailing `\n`. `\Z` matches end-of-string ONLY. `re.fullmatch()` is equivalent to anchoring with `\A...\Z`. — Evidence: https://docs.python.org/3/library/re.html#re.fullmatch.
- **Year-10000 class bug:** ISO-8601 specifies 4-digit year by default; 5-digit year requires prefix `+` per ISO-8601:2004. SQLite sort by STRING is char-by-char lexicographic. `'1' < '2'` so `'10000-...' < '2026-...'` incorrectly. — Evidence: https://www.iso.org/iso-8601-date-and-time-format.html, https://sqlite.org/lang_datefunc.html.

### Skill/Agent Inventory
- Standard 4-reviewer implement-phase loop (implementation-reviewer, relevance-verifier, code-quality-reviewer, security-reviewer).
- Pattern: direct-orchestrator implementation (no implementer subagent dispatch) per 092 retro "rigorous-upstream-enables-direct-orchestrator-implement".

## Strategic Analysis

### First-principles
- **Core Finding:** The 3 findings are one finding. Writing 3 separate fixes would duplicate the validation surface — and duplication is precisely why 092 shipped with asymmetric FR-5/FR-8. The disciplined move: one module-level `_ISO8601_Z_PATTERN` hardened correctly, used symmetrically, tested against the pattern constant (not against each call site).
- **Analysis:** Python's default `\d` Unicode behavior is a well-known stdlib footgun — stdlib `datetime.fromisoformat` used to accept Arabic digits until Python 3.11. The 092 spec cited `\d` without noticing the stdlib-semantics trap. The `$` vs `\Z` choice has the same quality: a well-documented Python anchor asymmetry. Neither defect required external research; they required naming the right primitives. The right-problem framing is not "patch 3 regex bugs" but "make the pattern correct once and apply it symmetrically."
- **Key Risks:** (a) Treating as 3 fixes inflates scope + test count; (b) asymmetric fixes re-introduce the structural cause in 094; (c) chosen approach must preserve `_iso_utc` output match (regression guard).
- **Recommendation:** Single regex change (`[0-9]` + `re.ASCII` belt-and-suspenders + `fullmatch`). Single FR-8 line (call `_ISO8601_Z_PATTERN.fullmatch(now_iso)`). Symmetry invariant enforced via a new test `test_pattern_is_single_source_of_truth` that asserts the same module-level constant is used from both call sites (via inspection or re-import).
- **Evidence Quality:** strong

### Pre-mortem
- **Core Finding:** Most likely failure: a symmetric FR-8 regex check raises `ValueError` on inputs the current prod path produces, breaking the idempotency guard in the field. Current prod `batch_demote` callers pass `_iso_utc(now)` output — must verify the hardened pattern still matches that output EXACTLY.
- **Analysis:** 092's TD-3 justified raise-on-write-path via "silent-accept-corrupt-write corrupts state." The new pattern is stricter than the old `not now_iso` check. If `_iso_utc` ever emits a format variant (e.g., under a future timezone fix), `batch_demote` starts raising in production. Mitigation: pin the `_iso_utc → _ISO8601_Z_PATTERN` match with a dedicated test that fires on EVERY `_iso_utc` output (parametrized across representative datetimes including microsecond=0, microsecond=999999, tz-aware-UTC, tz-aware-non-UTC).
- **Key Risks:**
  - **[MED]** FR-8 tightening breaks current prod callers if `_iso_utc` output diverges from the pattern at any datetime value.
  - **[LOW]** `re.ASCII` flag affects `\s` and `\w` too — if the pattern ever grows those classes, behavior changes. Use `[0-9]` literal as primary guard; keep `re.ASCII` as defense-in-depth.
  - **[LOW]** `re.fullmatch` returns Match object not re.Match — check no caller relies on `.match()` group semantics (current code only does truthiness check).
- **Recommendation:** Parametrize the `test_pattern_matches_iso_utc_output` test with ≥5 representative datetimes, and add a test `test_fr8_does_not_reject_iso_utc_output` that invokes `batch_demote(['x'], 'medium', _iso_utc(now))` with those same datetimes to prove zero regression for production callers.
- **Evidence Quality:** strong

### Antifragility
- **Core Finding:** The hardened pattern creates a NEW failure surface: future `_iso_utc` changes could silently break `batch_demote`. The mitigation (test pinning) is the load-bearing defense. Without it, hardening is fragile — it closes 3 holes but opens a tighter coupling between `_iso_utc` and both call sites.
- **Analysis:** Current prod has a decoupled pair: `_iso_utc` emits strings, `batch_demote` accepts any non-empty string. That's loose coupling, which is why 092's `not now_iso` guard is so shallow. Tightening both call sites to a single pattern creates tight coupling — a `_iso_utc` format change is now a breaking change for the write path (previously silent data corruption, which IS worse, but fails-loud). The antifragile move is to make the coupling EXPLICIT via a test that FAILS if `_iso_utc` output diverges from the pattern.
- **Key Risks:**
  - **[HIGH]** Without a format-drift pin, a future `_iso_utc` refactor breaks production silently-or-loudly.
  - **[MED]** Single-source-of-truth pattern means one bug in the regex breaks BOTH paths. Read path fails silent (log-and-skip); write path fails loud (raise). Worst case: entire decay loop becomes a no-op that also crashes on any write attempt.
  - **[LOW]** Unicode-digit rejection is defensive — no known attacker path today, but future multi-project memory DB sharing could introduce one.
- **Recommendation:** Ship BOTH the fix AND the format-drift pin in the same commit. The pin test is non-negotiable — if it doesn't land, the fix is net-negative antifragility.
- **Evidence Quality:** strong

**Advisor consensus:** (1) single fix, not three; (2) parametrize `_iso_utc → pattern` test with ≥5 representative datetimes; (3) `[0-9]` literal AS PRIMARY + `re.ASCII` as secondary + `fullmatch` for anchoring.

## Symptoms

1. **#00219 Unicode bypass:** `_ISO8601_Z_PATTERN.match('２０２６-04-20T00:00:00Z')` returns a Match object when it should return None. Downstream `WHERE last_recalled_at < '２０２６...'` produces undefined SQLite ordering.
2. **#00220 Trailing-newline bypass:** `_ISO8601_Z_PATTERN.match('2026-04-20T00:00:00Z\n')` returns a Match object when it should return None. Log-injection vector if input is later echoed to human-visible stream.
3. **#00221 FR-8 narrowness:** `batch_demote(['x'], 'medium', '10000-01-01T00:00:00Z')` silently succeeds and writes `updated_at='10000-...'` which lex-compares less than all 4-digit-year strings — inverts the idempotency guard.

## Reproduction Steps

### Symptom 1 (Unicode bypass)
```python
from semantic_memory.database import _ISO8601_Z_PATTERN
assert _ISO8601_Z_PATTERN.match('２０２６-04-20T00:00:00Z') is None, \
    "Expected rejection of fullwidth digits; got match"
# Currently FAILS — pattern accepts the input.
```

### Symptom 2 (trailing-newline bypass)
```python
from semantic_memory.database import _ISO8601_Z_PATTERN
assert _ISO8601_Z_PATTERN.match('2026-04-20T00:00:00Z\n') is None, \
    "Expected rejection of trailing newline; got match"
# Currently FAILS.
```

### Symptom 3 (FR-8 narrowness)
```python
from semantic_memory.database import MemoryDatabase
db = MemoryDatabase(':memory:')
# No exception — silent-accept of corrupt timestamp:
db.batch_demote(['some_id'], 'medium', '10000-01-01T00:00:00Z')
# SQLite stores updated_at='10000-...'. Downstream `updated_at < '2026-...'` evaluates TRUE.
```

## Hypotheses

| # | Hypothesis | Evidence For | Evidence Against | Status |
|---|-----------|--------------|-----------------|--------|
| 1 | All 3 findings reduce to one root cause (asymmetric shallow validation) | 092 QA filed them together; same pattern / same validation layer | None | Confirmed |
| 2 | Single fix (hardened pattern + fullmatch + symmetric application) closes all 3 | Pattern change covers #00219+#00220; symmetric FR-8 call covers #00221 | None | Confirmed |
| 3 | Current prod `_iso_utc` output passes the hardened pattern | `_iso_utc` uses `strftime("%Y-%m-%dT%H:%M:%SZ")` — always ASCII, fixed-length | Untested against ALL datetime boundary cases (microsecond, year-boundary, DST) | Probable; pin via parametrized test |
| 4 | `[0-9]` literal is safer than `\d + re.ASCII` as primary guard | `[0-9]` is unambiguous; `re.ASCII` affects other char classes | None | Confirmed — use both (belt + suspenders) |
| 5 | `re.fullmatch()` is preferable to `\Z` anchor | `fullmatch` is newer (3.4+) and intent-revealing; `\Z` is cryptic | `\Z` is slightly faster (one check vs two) | Choose `fullmatch` for readability |

## Evidence Map

| Symptom | Direct Evidence | Root Cause |
|---------|----------------|------------|
| S1 Unicode bypass | `database.py:17` pattern uses `\d` | Python 3 `\d` matches all Unicode digits by default |
| S2 Newline bypass | `database.py:991` uses `.match()` with `$` anchor | Python `$` matches before trailing `\n` in non-multiline mode |
| S3 FR-8 narrowness | `database.py:1055` uses `if not now_iso:` | Truthy check is semantically narrower than "valid ISO-8601" |

## Review History

### Stage 4 Iter 1 (2026-04-24)
- [warning] Line numbers used `~` prefix — replaced with exact values verified via grep (991, 1055).
- [warning] Structural gate conflated binding criterion with trend observation — clarified "binding gate" vs "non-binding trend observation".
- [suggestions] Hypothesis cross-ref + open-question justification noted; not applied (cosmetic).

### Stage 4 Iter 2 (2026-04-24)
- Approved, zero issues.

### Stage 5 Iter 1 (2026-04-24)
- Approved with 1 suggestion: multi-tenant threat model defer statement added to Target User section.

## Open Questions

1. **Should `_ISO8601_Z_PATTERN` move to `_config_utils.py`** (co-located with `_iso_utc`)? Pro: single module for format + regex. Con: `semantic_memory.database` already imports from `_config_utils`, which would become a cyclic import if the pattern is used in `_config_utils` tests. **Decision: keep in `database.py`** for now; file as separate backlog if multi-module regex usage appears.
2. **Should FR-8 use log-and-skip like FR-5 (symmetric behavior)** or keep raise (TD-3 asymmetry)? **Decision: keep raise** per TD-3 read-vs-write semantics (corrupted write silently is worse than loud failure).
3. **Should test parametrize cover year 9999 + year 0001?** **Decision: yes** — include in the 5-datetime parametrize set to pin boundary behavior.

## Next Steps

1. Promote to feature `/pd:create-feature` (mode: Standard).
2. Feature name: `093-092-qa-residual-hotfix`.
3. Stage 5 exit criterion: post-fix adversarial QA ≤ 2 MED, zero HIGH.
4. Release: `scripts/release.sh --ci` for v4.16.2.
