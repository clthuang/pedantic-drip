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
- **AC-2** `_config_utils.py` contains the relocated definition matching exactly: `_ISO8601_Z_PATTERN = re.compile(...)` with the same source string `r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'` and `re.ASCII` flag. Verifiable: `grep -qE "_ISO8601_Z_PATTERN = re.compile\(" plugins/pd/hooks/lib/semantic_memory/_config_utils.py` AND `grep -q 'r.\[0-9\]\{4\}-\[0-9\]\{2\}-\[0-9\]\{2\}T\[0-9\]\{2\}:\[0-9\]\{2\}:\[0-9\]\{2\}Z' plugins/pd/hooks/lib/semantic_memory/_config_utils.py` AND `grep -q 're.ASCII' plugins/pd/hooks/lib/semantic_memory/_config_utils.py`.
- **AC-3** The 9-line lineage comment block (currently `database.py:14-22`) is moved to `_config_utils.py` immediately above the relocated `_ISO8601_Z_PATTERN` definition. Verifiable: `grep -q 'Feature 093 FR-1' plugins/pd/hooks/lib/semantic_memory/_config_utils.py` AND `grep -q 'Feature 092 shipped' plugins/pd/hooks/lib/semantic_memory/_config_utils.py`.
- **AC-4** `_config_utils.py` contains a one-line convention comment near `_ISO8601_Z_PATTERN` per FR-4 (flywheel advisor recommendation). Verifiable: `grep -qE 'validators? for formats produced' plugins/pd/hooks/lib/semantic_memory/_config_utils.py`.
- **AC-5** `_ISO8601_Z_PATTERN` is **REMOVED** from `database.py` (no longer defined locally). Verifiable: `grep -cE '^_ISO8601_Z_PATTERN = re.compile' plugins/pd/hooks/lib/semantic_memory/database.py` returns `0`.
- **AC-6** The 9-line lineage comment block is **REMOVED** from `database.py` (migrated, not duplicated). Verifiable: `grep -c 'Feature 093 FR-1' plugins/pd/hooks/lib/semantic_memory/database.py` returns `0` for the comment-block lineage marker.
- **AC-7** `database.py` imports `_ISO8601_Z_PATTERN` from `_config_utils.py`. Verifiable: `grep -qE '^from semantic_memory._config_utils import.*_ISO8601_Z_PATTERN' plugins/pd/hooks/lib/semantic_memory/database.py`.
- **AC-8** `test_database.py:17` no longer imports `_ISO8601_Z_PATTERN` from `database`. Verifiable: `grep -E '^from semantic_memory.database import' plugins/pd/hooks/lib/semantic_memory/test_database.py | grep -v '_ISO8601_Z_PATTERN'` returns the import line (i.e., the symbol is NOT in the database-side import).
- **AC-9** `test_database.py` imports `_ISO8601_Z_PATTERN` from `_config_utils`. Verifiable: `grep -qE '^from semantic_memory._config_utils import.*_ISO8601_Z_PATTERN' plugins/pd/hooks/lib/semantic_memory/test_database.py`.
- **AC-10** Pytest pass count unchanged: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q | tail -1` returns `214 passed`. Wider regression check: `pytest plugins/pd/hooks/lib/ -q` returns `PRE_PYTEST_PASS_WIDE` exact (no out-of-scope regressions).
- **AC-11** Feature 095 source-pin tests in `TestIso8601PatternSourcePins` continue to pass without modification. Verifiable: `pytest plugins/pd/hooks/lib/semantic_memory/test_database.py::TestIso8601PatternSourcePins -v` shows all 7 cases PASS (1+1+3+2 from feature 095).
- **AC-12** `validate.sh` exit 0; warning count unchanged from baseline.
- **AC-13** Single atomic commit covers all 3 production files. Verifiable: `git show --stat HEAD` shows `_config_utils.py`, `database.py`, `test_database.py` all in the same commit (plus feature artifacts).

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

**Location:** `_config_utils.py` immediately after the `_ISO8601_Z_PATTERN` definition (or as part of the same comment block above the definition).
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

- [ ] All 13 ACs (AC-1..AC-13) pass binary verification
- [ ] All 8 FRs implemented (FR-1..FR-8)
- [ ] All 4 NFRs met
- [ ] `validate.sh` exit 0
- [ ] Pytest pass count = 214 exactly (unchanged from feature 095 baseline)
- [ ] Wider regression check `pytest plugins/pd/hooks/lib/` exit 0 with no new failures
- [ ] Single atomic commit verified via `git show --stat HEAD`
- [ ] Feature 094 gate dispatches successfully on T9 (no INCOMPLETE failures)
