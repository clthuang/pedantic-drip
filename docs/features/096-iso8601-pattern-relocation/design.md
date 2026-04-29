# Design: Feature 096 — Relocate `_ISO8601_Z_PATTERN`

## Status
- Created: 2026-04-29
- Phase: design
- Upstream: spec.md (14 ACs, 8 FRs, 4 NFRs)

## Prior Art Research

**Direct precedent:** Feature 089 FR-3.2 / AC-12 (#00148) relocated `_iso_utc` from `maintenance.py` to `_config_utils.py` for the SAME co-location reason. Documented in `_config_utils.py:31-44` docstring. The relocation pattern is proven in this codebase.

**Codebase facts (from brainstorm Stage 2):**
- `_config_utils.py:1-29` — module preamble + `import sys` (line 27) + `from datetime import datetime, timezone` (line 28)
- `_config_utils.py:31-47` — `_iso_utc` definition
- `_config_utils.py:50` — `_warn_and_default` (next function)
- `database.py:1-12` — preamble + stdlib imports (`re` at line 7)
- `database.py:14-22` — 9-line lineage comment block
- `database.py:23-26` — `_ISO8601_Z_PATTERN` definition
- `database.py:1001`, `database.py:1068` — two `.fullmatch()` call sites
- `test_database.py:17` — module-level import (split target)
- 4 existing files import from `_config_utils.py` (well-trodden path)

## Architecture

3-file edit, single atomic commit. Direct-orchestrator pattern (091/092/093/094/095 surgical-feature template).

```
_config_utils.py    [edit, +13 LOC: import re + 9-line comment + 4-line definition + convention comment]
                    └─→ exports _ISO8601_Z_PATTERN as a module-level symbol

database.py         [edit, -13/+1 LOC: remove definition+comment, add 1 import line]
                    └─→ imports _ISO8601_Z_PATTERN from _config_utils
                    └─→ scan_decay_candidates + batch_demote bodies UNCHANGED
                        (still reference `_ISO8601_Z_PATTERN.fullmatch(...)` by name)

test_database.py    [edit, +1 LOC: split line 17 into 2 import lines]
                    └─→ imports _ISO8601_Z_PATTERN from _config_utils (was: from .database)
                    └─→ all 17 feature 095 source-pin tests + 18 feature 093 behavior tests UNCHANGED
                        (inspect.getsource() reads function bodies only, not module imports)
```

## Technical Decisions

### TD-1: Migrate the 9-line lineage comment WITH the symbol

**Decision:** Move the comment block at `database.py:14-22` to `_config_utils.py` immediately above the relocated `_ISO8601_Z_PATTERN` definition. Do not leave it in `database.py`.

**Alternatives rejected:**
- Leave comment in `database.py` as orphan documentation pointing to `_config_utils.py` — re-creates the dispersal problem (self-cannibalization advisor R-2).
- Drop the comment entirely — loses feature 092→093 lineage history.

**Rationale:** Self-cannibalization advisor: comment must follow the symbol or documentation diverges. The comment IS the historical context for why this pattern hardened the way it did; it lives where the pattern lives.

### TD-2: Add convention comment for flywheel seed

**Decision:** Add `# Convention: validators for formats produced by this module live here (see _iso_utc + _ISO8601_Z_PATTERN).` immediately AFTER the definition (with blank-line separators), separate from the lineage comment block above.

**Alternatives rejected:**
- Skip convention comment — flywheel advisor's "one-shot vs compounding" finding: without explicit convention signal, the move reads as historical cleanup rather than prescriptive pattern.
- Embed in lineage comment — conflates symbol-history (single-symbol scope) with module-level convention (cross-symbol scope).
- Update module docstring — expands docstring scope ambiguously; deferred per Out of Scope.

**Rationale:** Flywheel advisor: single-contributor context removes peer-review reinforcement; convention must be self-evident from reading the file. Two-line comment is the cheapest path to compounding value.

### TD-3: New import line in `database.py` (NOT append to existing _config_utils import)

**Decision:** Add new import line `from semantic_memory._config_utils import _ISO8601_Z_PATTERN` to `database.py`. Confirmed at PRD-review iter 0: `database.py` has NO existing `from semantic_memory._config_utils import` line, so this is unambiguously a new line.

**Alternatives rejected:**
- Append to existing line — none exists today.
- Use relative import (`from ._config_utils import ...`) — inconsistent with existing absolute-import style in the test files and other consumers (`maintenance.py`, `refresh.py` use absolute form).

**Rationale:** Match existing import-style precedent. New line keeps the diff small (+1 LOC) and easy to grep-verify (AC-7).

### TD-4: Atomic commit with verification across feature branch

**Decision:** All 3 production-file edits land in a single commit. AC-13 verifies atomicity per-file via `git log develop..HEAD --oneline -- <file> | wc -l == 1` for each of the 3 files, all returning the SAME commit hash.

**Alternatives rejected:**
- Two-commit path (e.g., commit `_config_utils.py` first, then `database.py + test_database.py`) — produces a 214-test collection bomb between commits because `test_database.py:17` would import a removed symbol from `database.py`. Catastrophic intermediate state masquerading as environment failure.
- HEAD-only verification (`git show --stat HEAD`) — passes if the most recent commit happens to touch all 3 files, even if a prior commit on the branch touched some of them. Per spec-reviewer iter 1 warning 2.

**Rationale:** Adoption-friction advisor R-1: collection-bomb risk is the single highest-friction adoption point; atomic commit is the only mitigation; per-file branch-level verification is the only AC that catches the 2-commit anti-pattern after the fact.

### TD-5: Test-side import update via line split (not symbol-removal-only)

**Decision:** `test_database.py:17` splits into 2 lines:
- `from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query` (existing symbols stay on the database-side import)
- `from semantic_memory._config_utils import _ISO8601_Z_PATTERN` (NEW line for the relocated symbol)

**Alternatives rejected:**
- Append `_ISO8601_Z_PATTERN` to an existing test_database.py `from semantic_memory._config_utils import ...` line — none exists at module level (line 2042 has an INLINE `_iso_utc` import inside a function body, not a module-level import).
- Drop `_sanitize_fts5_query` import — used elsewhere in the test file (out of scope).

**Rationale:** Cleanest 2-line split with zero collateral changes. AC-8 + AC-9 jointly verify the split landed correctly (symbol absent from database-side import AND present on _config_utils-side import).

## Components

### C1: `_config_utils.py` extension

**Owner:** `plugins/pd/hooks/lib/semantic_memory/_config_utils.py`  
**Responsibility:** Co-locate the validator with its producer; add `import re`; add convention seed comment.  
**Size:** +13 LOC (1 import + 9-line comment block + 4-line definition + 2-line convention comment with blank-line separators) — actual closer to +15 with blank lines.

### C2: `database.py` removal + import

**Owner:** `plugins/pd/hooks/lib/semantic_memory/database.py`  
**Responsibility:** Remove local definition + comment block; add new import from `_config_utils.py`.  
**Size:** -13 LOC + 1 LOC = net -12 LOC.

### C3: `test_database.py:17` split

**Owner:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`  
**Responsibility:** Split single import line into 2 lines pointing at correct origin modules.  
**Size:** +1 LOC (one line becomes two).

## Interfaces

### I-1: `_config_utils.py` insertion-point block

```python
# {existing _iso_utc function ending at line 47}


# Feature 093 FR-1 (#00219, #00220): Z-suffix ISO-8601 format matching production
# `_iso_utc` output (strftime("%Y-%m-%dT%H:%M:%SZ")).
# Used symmetrically by `MemoryDatabase.scan_decay_candidates` (read path, log-and-skip)
# and `MemoryDatabase.batch_demote` (write path, raise) to validate ISO-8601 Z-suffix
# timestamps. Feature 092 shipped `\d` without `re.ASCII` which accepted Unicode digit
# codepoints (Arabic-Indic ٠١٢, Devanagari ०१२, fullwidth ０１２); 093 hardens via:
#   - `[0-9]` literal (ASCII-only, primary defense against Unicode homograph)
#   - `re.ASCII` flag (defense-in-depth against future class expansion)
#   - call sites use `.fullmatch()` instead of `.match()` to reject trailing `\n` (#00220)
#
# Feature 096 #00277: relocated here from `database.py` to co-locate with `_iso_utc`
# (the producer). Source-level pins now use `_ISO8601_Z_PATTERN.pattern` and `.flags`
# directly without `inspect.getsource()` brittleness.
_ISO8601_Z_PATTERN = re.compile(
    r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z',
    re.ASCII,
)

# Convention: validators for formats produced by this module live here (see _iso_utc + _ISO8601_Z_PATTERN).


def _warn_and_default(...):
    {existing function unchanged}
```

**Note:** The lineage comment block is verbatim from `database.py:14-22` with one substantive update — line 2 changes `_config_utils._iso_utc` to `_iso_utc` (same module now, drop module qualifier). One additional 3-line annotation appended at the bottom of the lineage block citing this relocation (feature 096 #00277).

### I-2: `database.py` post-edit imports block

```python
"""SQLite database layer for the semantic memory system."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Callable

from semantic_memory._config_utils import _ISO8601_Z_PATTERN


def _assert_testing_context() -> None:
    {existing function unchanged}
```

**Note:** Lines 14-26 of pre-edit (9-line comment + 4-line definition) deleted. Single new import line added after `from typing import Callable`. The blank line at pre-edit line 27 stays.

### I-3: `test_database.py` post-edit line 17 area

```python
from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query
from semantic_memory._config_utils import _ISO8601_Z_PATTERN
```

**Note:** Pre-edit line 17 (single line with 3 symbols) becomes 2 lines (2 symbols on database-side import + 1 symbol on _config_utils-side import). All other test code references the symbol by name (e.g., `_ISO8601_Z_PATTERN.pattern`) which works regardless of which module the symbol came from at import time.

## Risks

- **R-1 [HIGH]** Atomic-commit constraint not enforced by tooling — any 2-commit path produces 214-test collection bomb. **Mitigated:** AC-13 per-file branch-level verification catches this after the fact (post-implementation).
- **R-2 [MED]** Comment-block migration could lose lineage if implementer overlooks line range. **Mitigated:** AC-3 + AC-6 jointly verify presence-in-destination AND absence-in-source.
- **R-3 [LOW]** `inspect.getsource()` source-pin tests (feature 095) interaction post-relocation. **Mitigated:** `inspect.getsource()` reads method bodies only (not module imports); the name `_ISO8601_Z_PATTERN` still appears in `scan_decay_candidates` + `batch_demote` bodies. AC-11 verifies feature 095 source-pin tests still pass without modification.
- **R-4 [LOW]** Circular-import accidental introduction by future maintainer. **Mitigated:** AC-14 grep-based check.
- **R-5 [LOW]** Stale `.pyc` for zip-imported / read-only-FS pd installations. **Not mitigated by feature 096:** standard `plugins/cache/` installations regenerate `.pyc` automatically; out of scope.
- **R-6 [LOW]** Feature 094 gate (T9 dogfood) failure modes — second production exercise; first exercise (feature 095) succeeded. **Mitigated:** if gate flags HIGH, R-5 contingency from feature 094 design applies (capture in retro, file backlog, use qa-override.md).

## Out of Scope

Same as PRD/spec. No expansion. The convention comment is in scope (FR-4 / TD-2); module docstring update is out of scope.

## Implementation Order

Direct-orchestrator. Single atomic commit:

1. **T0** — capture baselines (PRE_HEAD, PRE_PYTEST_PASS=214, PRE_PYTEST_PASS_WIDE=3198, PRE_TEST_DB_LINES).
2. **T1** — edit `_config_utils.py`: add `import re` + comment block + definition + convention comment.
3. **T2** — edit `database.py`: remove old comment+definition (lines 14-26), add import line.
4. **T3** — edit `test_database.py`: split line 17 into 2 lines.
5. **T4** — quality gates: pytest test_database.py = 214; pytest plugins/pd/hooks/lib = 3198; validate.sh exit 0; AC-14 circular-import grep returns 0.
6. **T5** — atomic commit (3 production files + feature artifacts).
7. **T6** — `/pd:finish-feature` triggers feature 094 Step 5b gate (SECOND production exercise).

## Test Strategy

| AC | Verified by | Step |
|----|-------------|------|
| AC-1 (import re) | grep at T1 | T1 |
| AC-2 (relocated definition with re.ASCII) | 3 grep checks at T1 (literal substring + line anchor) | T1 |
| AC-3 (lineage comment in destination) | 2 grep checks at T1 | T1 |
| AC-4 (convention comment) | grep at T1 | T1 |
| AC-5 (definition removed from database.py) | grep -c returns 0 at T2 | T2 |
| AC-6 (lineage comment removed from database.py) | grep -c returns 0 at T2 | T2 |
| AC-7 (database.py import line) | grep at T2 | T2 |
| AC-8 (test_database.py: symbol absent from database-side import) | grep -c returns 0 at T3 | T3 |
| AC-9 (test_database.py: symbol on _config_utils-side import) | grep at T3 | T3 |
| AC-10 (pytest counts unchanged) | pytest at T4 | T4 |
| AC-11 (feature 095 source-pin tests pass) | pytest at T4 | T4 |
| AC-12 (validate.sh) | shell at T4 | T4 |
| AC-13 (atomic commit per-file) | 3 git log commands at T5 | T5 |
| AC-14 (no circular import) | grep at T4 | T4 |

All 14 ACs binary-verifiable. Zero manual-only ACs.

## Definition of Done

Per spec.md DoD:
- All 14 ACs pass binary verification
- All 8 FRs implemented
- All 4 NFRs met
- `validate.sh` exit 0; pytest counts: 214 (test_database.py) + 3198 (plugins/pd/hooks/lib)
- Single atomic commit per AC-13
- No circular import per AC-14
- Feature 094 gate dispatches successfully on T6 with no INCOMPLETE failures
