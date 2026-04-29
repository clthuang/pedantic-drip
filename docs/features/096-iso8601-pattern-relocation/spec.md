# Spec: Feature 096 — Relocate `_ISO8601_Z_PATTERN` to `_config_utils.py`

## Status
- Phase: specify
- Created: 2026-04-29
- PRD: `docs/features/096-iso8601-pattern-relocation/prd.md`
- Source: backlog #00277
- Target: v4.16.6 (test-only-equivalent risk; pure architectural relocation)

## Overview

Move `_ISO8601_Z_PATTERN` from `plugins/pd/hooks/lib/semantic_memory/database.py:14-26` (definition + 9-line comment block) to `plugins/pd/hooks/lib/semantic_memory/_config_utils.py` (after `_iso_utc` at line 47). Update `database.py` to import the symbol from `_config_utils.py` instead of defining it locally. Update `test_database.py:17` to import from the new location.

**Net production-touch:** +13 (`_config_utils.py`) − 12 (`database.py`) + 1 (`test_database.py`) = **+2 LOC** across 3 files. Single atomic commit. Zero behavior change.

## Acceptance Criteria (binary-verifiable)

- **AC-1** `plugins/pd/hooks/lib/semantic_memory/_config_utils.py` contains `import re` near the top of the file (with the existing stdlib imports). Verifiable: `grep -qE '^import re$' plugins/pd/hooks/lib/semantic_memory/_config_utils.py`.
- **AC-2** `_config_utils.py` contains the relocated definition matching exactly: `_ISO8601_Z_PATTERN = re.compile(...)` with the same source string `r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'` and `re.ASCII` flag. Verifiable (using `grep -F` for literal substring matching, eliminates regex metachar ambiguity):
  - `grep -qE "^_ISO8601_Z_PATTERN = re.compile\(" plugins/pd/hooks/lib/semantic_memory/_config_utils.py`
  - `grep -qF "r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'" plugins/pd/hooks/lib/semantic_memory/_config_utils.py`
  - `grep -qF "re.ASCII" plugins/pd/hooks/lib/semantic_memory/_config_utils.py`
- **AC-3** The 9-line lineage comment block (currently `database.py:14-22`) is moved to `_config_utils.py` immediately above the relocated `_ISO8601_Z_PATTERN` definition. Verifiable: `grep -q 'Feature 093 FR-1' plugins/pd/hooks/lib/semantic_memory/_config_utils.py` AND `grep -q 'Feature 092 shipped' plugins/pd/hooks/lib/semantic_memory/_config_utils.py`.
- **AC-4** `_config_utils.py` contains a one-line convention comment near `_ISO8601_Z_PATTERN` per FR-4 (flywheel advisor recommendation). Verifiable: `grep -qE 'validators? for formats produced' plugins/pd/hooks/lib/semantic_memory/_config_utils.py`.
- **AC-5** `_ISO8601_Z_PATTERN` is **REMOVED** from `database.py` (no longer defined locally). Verifiable: `grep -cE '^_ISO8601_Z_PATTERN = re.compile' plugins/pd/hooks/lib/semantic_memory/database.py` returns `0`.
- **AC-6** The 9-line lineage comment block is **REMOVED** from `database.py` (migrated, not duplicated). Verifiable: `grep -c 'Feature 093 FR-1' plugins/pd/hooks/lib/semantic_memory/database.py` returns `0` for the comment-block lineage marker.
- **AC-7** `database.py` imports `_ISO8601_Z_PATTERN` from `_config_utils.py`. Verifiable: `grep -qE '^from semantic_memory._config_utils import.*_ISO8601_Z_PATTERN' plugins/pd/hooks/lib/semantic_memory/database.py`.
- **AC-8** `test_database.py` no longer imports `_ISO8601_Z_PATTERN` from `database`. Verifiable: `grep -cE '^from semantic_memory.database import .*_ISO8601_Z_PATTERN' plugins/pd/hooks/lib/semantic_memory/test_database.py` returns `0` (the symbol is no longer imported on a database-side import line).
- **AC-9** `test_database.py` imports `_ISO8601_Z_PATTERN` from `_config_utils`. Verifiable: `grep -qE '^from semantic_memory._config_utils import.*_ISO8601_Z_PATTERN' plugins/pd/hooks/lib/semantic_memory/test_database.py`.
- **AC-10** Pytest pass count unchanged: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q | tail -1` returns `214 passed`. Wider regression check: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ -q | tail -1` returns `3198 passed` exact (baseline captured 2026-04-29 on feature/096 HEAD pre-edit; no out-of-scope regressions allowed).
- **AC-11** Feature 095 source-pin tests in `TestIso8601PatternSourcePins` continue to pass without modification (count-relative, not hardcoded). Verifiable: `pytest plugins/pd/hooks/lib/semantic_memory/test_database.py::TestIso8601PatternSourcePins -q | tail -1` returns the SAME pass count post-feature-096 as on develop pre-edit (no regressions, no test removals). Pre-edit baseline (captured 2026-04-29): 7 passed.
- **AC-12** `validate.sh` exit 0; warning count unchanged from baseline.
- **AC-13** Single atomic commit covers all 3 production files (atomicity verified across the entire feature branch, not just HEAD). Verifiable:
  - `git log develop..HEAD --oneline -- plugins/pd/hooks/lib/semantic_memory/_config_utils.py | wc -l` returns `1`
  - `git log develop..HEAD --oneline -- plugins/pd/hooks/lib/semantic_memory/database.py | wc -l` returns `1`
  - `git log develop..HEAD --oneline -- plugins/pd/hooks/lib/semantic_memory/test_database.py | wc -l` returns `1`
  - All three commands return the SAME commit hash.

- **AC-14** No circular-import risk introduced. Verifiable: `grep -cE '^from semantic_memory.database' plugins/pd/hooks/lib/semantic_memory/_config_utils.py` returns `0` AND `grep -cE '^from \.database' plugins/pd/hooks/lib/semantic_memory/_config_utils.py` returns `0`. Mirrors PRD constraint into the spec as a binary check.

## Functional Requirements

### FR-1 — Add `import re` to `_config_utils.py`

**File:** `plugins/pd/hooks/lib/semantic_memory/_config_utils.py`
**Location:** with the existing stdlib imports (currently `import sys` at line ~26, `from datetime import ...` at line 28).
**New text:** add line `import re` between `import sys` and `from datetime import datetime, timezone`.

### FR-2 — Migrate the 9-line lineage comment block

**Source:** `database.py:14-22` (verbatim). Quote:
```
# Feature 093 FR-1 (#00219, #00220): Z-suffix ISO-8601 format matching production
# `_config_utils._iso_utc` output (strftime("%Y-%m-%dT%H:%M:%SZ")).
# Used symmetrically by `MemoryDatabase.scan_decay_candidates` (read path, log-and-skip)
# and `MemoryDatabase.batch_demote` (write path, raise) to validate ISO-8601 Z-suffix
# timestamps. Feature 092 shipped `\d` without `re.ASCII` which accepted Unicode digit
# codepoints (Arabic-Indic ٠١٢, Devanagari ०१२, fullwidth ０１２); 093 hardens via:
#   - `[0-9]` literal (ASCII-only, primary defense against Unicode homograph)
#   - `re.ASCII` flag (defense-in-depth against future class expansion)
#   - call sites use `.fullmatch()` instead of `.match()` to reject trailing `\n` (#00220)
```

**Destination:** `_config_utils.py` immediately above the relocated `_ISO8601_Z_PATTERN` definition (after `_iso_utc` ends at line 47, with a blank line above and below the comment-block-plus-definition).

### FR-3 — Define `_ISO8601_Z_PATTERN` in `_config_utils.py`

**Location:** immediately after the migrated comment block.
**Definition (verbatim from current database.py:23-26):**
```python
_ISO8601_Z_PATTERN = re.compile(
    r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z',
    re.ASCII,
)
```

### FR-4 — Convention comment (flywheel seed)

**Location:** `_config_utils.py` immediately AFTER the `_ISO8601_Z_PATTERN` definition (with one blank line separating the definition from the convention comment, and one blank line separating the convention comment from `_warn_and_default`). Single deterministic placement chosen — do NOT include in the lineage comment block above (which is symbol-history specific).
**Text:** `# Convention: validators for formats produced by this module live here (see _iso_utc + _ISO8601_Z_PATTERN).`

### FR-5 — Remove from `database.py`

**Action:** delete `database.py:14-26` (9-line comment block at 14-22 + 4-line definition at 23-26 = 13 lines total). Replace with nothing (the blank line at 27 stays).

### FR-6 — Add new import line in `database.py`

**Location:** with the existing imports near the top (after `from typing import Callable` at line 12, before the now-deleted lines that previously held the comment+definition).
**New text:** `from semantic_memory._config_utils import _ISO8601_Z_PATTERN`

(Confirmed at PRD-review iter 0: `database.py` has no existing `from semantic_memory._config_utils import` line; this is a new line.)

### FR-7 — Update `test_database.py` import

**Old text** (line 17, exact verbatim):
```
from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query, _ISO8601_Z_PATTERN
```

**New text** (split into 2 lines):
```
from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query
from semantic_memory._config_utils import _ISO8601_Z_PATTERN
```

### FR-8 — Atomic commit

All 3 production-file edits MUST land in a single commit alongside feature artifacts. Two-commit path produces a 214-test collection bomb between commits (per adoption-friction advisor R-1).

## Non-Functional Requirements

- **NFR-1** Zero behavior change. Pytest pass count exactly **214** (unchanged from feature 095 baseline).
- **NFR-2** Wall-clock implementation: <15 min (smaller scope than feature 095).
- **NFR-3** No new external dependencies (uses stdlib `re` only — already a transitive dependency).
- **NFR-4** All 3 feature 095 source-pin tests in `TestIso8601PatternSourcePins` continue to pass without modification — `inspect.getsource()` reads method bodies (not module imports), so the call-site name token `_ISO8601_Z_PATTERN.fullmatch(` is preserved across relocation.

## Edge Cases (mirror PRD)

| Scenario | Expected | Verified by |
|----------|----------|-------------|
| Two-commit non-atomic path | NOT ALLOWED — collection-bomb between commits | FR-8 + AC-13 |
| `inspect.getsource()` source-pin tests post-relocation | Continue to PASS unchanged | AC-11 |
| `re` import missing from `_config_utils.py` | NameError on first pytest run | AC-1 + AC-10 |
| Comment block left orphaned in database.py | NOT ALLOWED — must migrate WITH symbol | AC-3 + AC-6 (assert presence in destination AND absence in source) |
| Stale `.pyc` cache (zip-import / read-only FS) | Out of scope — standard `plugins/cache/` install regenerates `.pyc` automatically | N/A |

## Out of Scope (mirror PRD)

- #00278 sub-items (b, d, f, h) — not obviated by relocation; remain open
- Extracting to dedicated `_validators.py` — premature with one validator
- Pattern source-string changes
- `pd:retrospecting` skill updates

## Implementation Notes

- Total touch: 3 files, +2 LOC net production touch
- Direct-orchestrator pattern (091/092/093/094/095 surgical-feature template)
- Followed by `/pd:finish-feature` triggering feature 094's Step 5b gate (SECOND production exercise — closes feature 094 deferred AC-13 retro-fold path)

## Definition of Done

- [ ] All 14 ACs (AC-1..AC-14) pass binary verification
- [ ] All 8 FRs implemented (FR-1..FR-8)
- [ ] All 4 NFRs met
- [ ] `validate.sh` exit 0
- [ ] Pytest pass count = 214 exactly (test_database.py) and 3198 exact (wider plugins/pd/hooks/lib/)
- [ ] Single atomic commit verified per AC-13 (3 files in 1 commit on the feature branch)
- [ ] No circular-import per AC-14
- [ ] Feature 094 gate dispatches successfully on T9 (no INCOMPLETE failures)

## Review History

### Iteration 1 — spec-reviewer (opus, 2026-04-29)

**Findings:** 4 warnings + 3 suggestions

**Corrections applied:**
- AC-10 — replaced unbound `PRE_PYTEST_PASS_WIDE` placeholder with concrete baseline `3198 passed` (captured 2026-04-29 on feature/096 HEAD pre-edit). Reason: Warning 1.
- AC-13 — strengthened atomicity check from HEAD-only `git show --stat` to per-file `git log develop..HEAD` returning exactly 1 commit hash (same hash for all 3 files). Catches 2-commit anti-pattern. Reason: Warning 2.
- AC-14 NEW — added explicit grep-based circular-import check (mirrors PRD constraint into spec). Reason: Warning 3.
- AC-8 — rephrased to strict `grep -c ... returns 0` count check (was prose-described). Reason: Warning 4.
- AC-2 — switched to `grep -F` literal substring matching for the pattern source string (eliminates regex metachar ambiguity from `r.` permissive matching). Reason: Suggestion 5.
- AC-11 — replaced hardcoded "7 cases" assertion with count-relative "SAME pass count as develop pre-edit" + baseline citation. Reason: Suggestion 6.
- FR-4 — resolved placement ambiguity to single deterministic option (immediately AFTER definition with blank-line separators). Reason: Suggestion 7.
