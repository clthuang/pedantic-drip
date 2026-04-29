# Plan: Feature 096 — Relocate `_ISO8601_Z_PATTERN`

## Status
- Created: 2026-04-29
- Phase: create-plan
- Upstream: design.md (5 TDs + 3 components + 3 interfaces + 6 risks); spec.md (15 ACs incl AC-3a, 8 FRs, 4 NFRs)

## Architecture Summary

3-file edit, single atomic commit. Direct-orchestrator pattern (091/092/093/094/095 surgical-feature template). Net production-touch: **+2 LOC** (excluding blank-line separators).

```
plugins/pd/hooks/lib/semantic_memory/_config_utils.py   [edit, +13 LOC]
plugins/pd/hooks/lib/semantic_memory/database.py        [edit, net -12 LOC]
plugins/pd/hooks/lib/semantic_memory/test_database.py   [edit, +1 LOC]
```

## T0 — Capture Baselines (BEFORE any edits)

```bash
PRE_HEAD=$(git rev-parse HEAD)
PRE_PYTEST_PASS=$(plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q 2>&1 | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
PRE_PYTEST_PASS_WIDE=$(plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ -q 2>&1 | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')

# Expected (verified at plan-write time):
# PRE_HEAD       = current feature/096-iso8601-pattern-relocation HEAD
# PRE_PYTEST_PASS = 214
# PRE_PYTEST_PASS_WIDE = 3198
```

**T0 DoD:** 3 baselines captured. PRE_PYTEST_PASS == 214 and PRE_PYTEST_PASS_WIDE == 3198 else investigate before any edits.

## Implementation Order — TDD-aware

The relocation is structurally additive at destination + subtractive at source. Order matters because intermediate states are broken until all 3 files are saved (atomic-commit invariant per TD-4 / AC-13). Edits run in working tree; quality gates run AFTER all 3 edits; commit is single atomic.

### T1 — Edit `_config_utils.py` (add `import re` + relocated definition with comments)

**File:** `plugins/pd/hooks/lib/semantic_memory/_config_utils.py`

**Edit 1a — Add `import re`:**

**Old text** (line 27, exact verbatim):
```
import sys
```

**New text:**
```
import re
import sys
```

**Edit 1b — Add comment block + definition + convention comment + feature 096 annotation, AFTER `_iso_utc` (line 47):**

**Old text** (lines 47-50, exact verbatim — `_iso_utc` ending followed by 2 blank lines + `_warn_and_default` start):
```
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _warn_and_default(
```

**New text** (insert comment block + definition + convention comment + feature 096 annotation between):
```
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


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


def _warn_and_default(
```

**T1 DoD:**
- `grep -qE '^import re$' plugins/pd/hooks/lib/semantic_memory/_config_utils.py` (AC-1)
- `grep -qE '^_ISO8601_Z_PATTERN = re.compile\(' plugins/pd/hooks/lib/semantic_memory/_config_utils.py` (AC-2 anchor)
- `grep -qF "r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z'" plugins/pd/hooks/lib/semantic_memory/_config_utils.py` (AC-2 literal)
- `grep -qF 're.ASCII' plugins/pd/hooks/lib/semantic_memory/_config_utils.py` (AC-2 flag)
- `grep -q 'Feature 093 FR-1' plugins/pd/hooks/lib/semantic_memory/_config_utils.py` (AC-3)
- `grep -q 'Feature 092 shipped' plugins/pd/hooks/lib/semantic_memory/_config_utils.py` (AC-3)
- AC-3a (anchored): `awk '/^# Feature 093 FR-1/,/^_ISO8601_Z_PATTERN = re.compile/' plugins/pd/hooks/lib/semantic_memory/_config_utils.py | grep -q 'Feature 096 #00277'` — verifies the feature 096 annotation lives **between** the lineage-comment start and the definition (rejects displaced or duplicated annotations elsewhere in the file)
- `grep -qE 'validators? for formats produced' plugins/pd/hooks/lib/semantic_memory/_config_utils.py` (AC-4)
- `grep -cE '^from semantic_memory.database' plugins/pd/hooks/lib/semantic_memory/_config_utils.py` returns `0` (AC-14)

### T2 — Edit `database.py` (remove old definition + comment, add import line)

**File:** `plugins/pd/hooks/lib/semantic_memory/database.py`

**Ordering directive:** Edits 2a and 2b are **text-anchored** (verbatim Old/New string match via the Edit tool, not line-number-based). **Apply 2a (removal) BEFORE 2b (insertion)** — 2a's Old text spans lines 14-26 and is unambiguous; 2b's anchor is the unchanged `from typing import Callable` block at line 12 which is unaffected by 2a. Reversing the order would still work text-anchored, but the canonical path is 2a→2b for review readability.

**Note on `import re`:** `database.py:7` already has `import re` and **stays** — it's still required by `_FTS5_STRIP_RE` (database.py:60). Do NOT remove the `import re` from `database.py`; only the `_ISO8601_Z_PATTERN` definition + its 9-line lineage comment are removed.

**Edit 2a — Remove lines 14-26 (9-line lineage comment + 4-line definition):**

**Old text** (verbatim, lines 14-26):
```
# Feature 093 FR-1 (#00219, #00220): Z-suffix ISO-8601 format matching production
# `_config_utils._iso_utc` output (strftime("%Y-%m-%dT%H:%M:%SZ")).
# Used symmetrically by `MemoryDatabase.scan_decay_candidates` (read path, log-and-skip)
# and `MemoryDatabase.batch_demote` (write path, raise) to validate ISO-8601 Z-suffix
# timestamps. Feature 092 shipped `\d` without `re.ASCII` which accepted Unicode digit
# codepoints (Arabic-Indic ٠١٢, Devanagari ०१२, fullwidth ０١２); 093 hardens via:
#   - `[0-9]` literal (ASCII-only, primary defense against Unicode homograph)
#   - `re.ASCII` flag (defense-in-depth against future class expansion)
#   - call sites use `.fullmatch()` instead of `.match()` to reject trailing `\n` (#00220)
_ISO8601_Z_PATTERN = re.compile(
    r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z',
    re.ASCII,
)
```

**New text:** delete entirely (the blank line at line 27 stays as-is, becoming the blank between the imports block and `_assert_testing_context()` at line 29).

**Edit 2b — Add import line after `from typing import Callable` (line 12):**

**Old text** (lines 12-13, exact verbatim — current import block ends + blank):
```
from typing import Callable

```

**New text** (insert import line after `Callable`, preserving the blank line above the now-removed comment block):
```
from typing import Callable

from semantic_memory._config_utils import _ISO8601_Z_PATTERN

```

**T2 DoD:**
- `grep -cE '^_ISO8601_Z_PATTERN = re.compile' plugins/pd/hooks/lib/semantic_memory/database.py` returns `0` (AC-5)
- `grep -c 'Feature 093 FR-1' plugins/pd/hooks/lib/semantic_memory/database.py` returns `0` (AC-6)
- `grep -qE '^from semantic_memory._config_utils import.*_ISO8601_Z_PATTERN' plugins/pd/hooks/lib/semantic_memory/database.py` (AC-7)

### T3 — Edit `test_database.py:17` (split import line)

**File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`

**Old text** (line 17, exact verbatim):
```
from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query, _ISO8601_Z_PATTERN
```

**New text** (split into 2 lines):
```
from semantic_memory.database import MemoryDatabase, _sanitize_fts5_query
from semantic_memory._config_utils import _ISO8601_Z_PATTERN
```

**T3 DoD:**
- `grep -cE '^from semantic_memory.database import .*_ISO8601_Z_PATTERN' plugins/pd/hooks/lib/semantic_memory/test_database.py` returns `0` (AC-8)
- `grep -qE '^from semantic_memory._config_utils import.*_ISO8601_Z_PATTERN' plugins/pd/hooks/lib/semantic_memory/test_database.py` (AC-9)

### T4 — Quality gates (BEFORE commit)

```bash
./validate.sh                                                                              # exit 0
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q | tail -1   # = "214 passed"
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ -q | tail -1                  # = "3198 passed"
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py::TestIso8601PatternSourcePins -q | tail -1   # = "7 passed" (AC-11)
git diff develop...HEAD -- plugins/pd/hooks/lib/semantic_memory/_config_utils.py | grep -cE '^\+\+\+ b/' && \
git diff develop...HEAD -- plugins/pd/hooks/lib/semantic_memory/database.py | grep -cE '^\+\+\+ b/' && \
git diff develop...HEAD -- plugins/pd/hooks/lib/semantic_memory/test_database.py | grep -cE '^\+\+\+ b/'  # all = 1
```

**T4 DoD:**
- `validate.sh` exit 0 (AC-12)
- `pytest test_database.py` = 214 passed (AC-10 narrow)
- `pytest plugins/pd/hooks/lib/` = 3198 passed (AC-10 wide)
- `TestIso8601PatternSourcePins` = 7 passed (AC-11)
- All 3 production files appear in diff (sanity check before commit)

### T5 — Atomic commit + AC-13 hash-equality verification

```bash
git add plugins/pd/hooks/lib/semantic_memory/_config_utils.py \
        plugins/pd/hooks/lib/semantic_memory/database.py \
        plugins/pd/hooks/lib/semantic_memory/test_database.py
git commit -m "pd(096): relocate _ISO8601_Z_PATTERN to _config_utils.py per #00277

Co-locates the validator with its producer (_iso_utc) per first-principles
advisor finding from feature 095. Closes recursive test-hardening cycle
flagged across 091/092/093/095. Net +2 LOC across 3 files.

- _config_utils.py: +import re + relocated definition + 9-line lineage
  comment + 3-line feature 096 annotation + convention comment seed
- database.py: -definition -lineage comment + new import line
- test_database.py: split line 17 import into 2 lines

Zero behavior change. Pytest pass count: 214 (test_database.py) and
3198 (plugins/pd/hooks/lib/) — exact match to baselines."

# AC-13 atomic-commit verification:
H1=$(git log develop..HEAD --format=%H -- plugins/pd/hooks/lib/semantic_memory/_config_utils.py)
H2=$(git log develop..HEAD --format=%H -- plugins/pd/hooks/lib/semantic_memory/database.py)
H3=$(git log develop..HEAD --format=%H -- plugins/pd/hooks/lib/semantic_memory/test_database.py)
test "$H1" = "$H2" -a "$H2" = "$H3" -a -n "$H1" && [[ $(echo "$H1" | wc -w) -eq 1 ]] && echo "AC-13 PASS" || echo "AC-13 FAIL"
```

**T5 DoD:**
- Single commit on feature branch contains all 3 production files (AC-13)
- `H1 == H2 == H3` and is non-empty (catches 2-commit anti-pattern)

### T6 — `/pd:finish-feature` (SECOND production exercise of feature 094 gate)

Run `/pd:finish-feature` on feature 096 branch. Triggers feature 094's Step 5b gate against the 3-file production diff:

1. Step 5a: validate.sh
2. **Step 5b: 4 reviewers parallel dispatch** (security + code-quality + implementation + test-deepener Step A)
3. Step 5a-bis: /security-review
4. Retro
5. Merge to develop
6. Release script → v4.16.6

**T6 DoD:**
- Gate dispatches 4 reviewers
- Aggregate severity per AC-5b: 0 HIGH preferred (gate PASS); if HIGH > 0, R-6 contingency applies (capture in retro, file backlog, qa-override.md)
- Merged to develop, pushed, v4.16.6 tagged
- AC-13 retro-fold path exercised (feature 094's deferred-verification): retrospecting skill processes any `.qa-gate.log` / `.qa-gate-low-findings.md` sidecars produced by gate

## AC Coverage Matrix (1-row-per-AC)

| AC | Verification | Step |
|----|--------------|------|
| AC-1 (`import re` in `_config_utils.py`) | grep | T1 |
| AC-2 (definition with re.ASCII) | 3 grep checks (anchor + literal + flag) | T1 |
| AC-3 (lineage comment in destination) | 2 grep checks | T1 |
| AC-3a (feature 096 annotation in destination) | grep | T1 |
| AC-4 (convention comment) | grep | T1 |
| AC-5 (definition removed from database.py) | grep -c returns 0 | T2 |
| AC-6 (lineage comment removed from database.py) | grep -c returns 0 | T2 |
| AC-7 (database.py imports from _config_utils) | grep | T2 |
| AC-8 (test_database.py: symbol absent from database-side import) | grep -c returns 0 | T3 |
| AC-9 (test_database.py: symbol on _config_utils-side import) | grep | T3 |
| AC-10 (pytest counts: 214 + 3198) | 2 pytest runs | T4 |
| AC-11 (feature 095 source-pin tests pass: 7) | pytest | T4 |
| AC-12 (validate.sh exit 0) | shell | T4 |
| AC-13 (atomic commit hash-equality) | 4-line bash assertion | T5 |
| AC-14 (no circular import) | 2 grep checks return 0 | T1 |

All 15 ACs binary-verifiable. Zero manual-only ACs.

## Quality Gates (recap)

- `./validate.sh` exit 0
- `pytest test_database.py` = 214 PASS exact
- `pytest plugins/pd/hooks/lib/` = 3198 PASS exact (no out-of-scope regressions)
- `TestIso8601PatternSourcePins` = 7 PASS (feature 095 source-pin compatibility)
- AC-13 hash-equality assertion exit 0
- AC-14 no circular-import grep returns 0

## Dependencies

- Standard pd toolchain (no new external deps per NFR-3)
- Python 3.14.4 (project venv)
- Existing 4 reviewer agents for T6 gate dispatch

## Risks Carried from Design

All 6 risks (R-1..R-6) per design.md Risks section. R-1 (atomic-commit constraint) mitigated by T5 hash-equality assertion. R-6 (feature 094 gate first/second exercise) — second production exercise; first run on feature 095 succeeded; same contingency path applies.

## Out of Scope

Same as PRD/spec/design. No expansion.

## Notes — Direct-orchestrator vs taskification

Direct-orchestrator chosen because:
- 3-file scope, +2 LOC net production touch
- Single atomic commit required (TD-4)
- Sequential dependencies (T1 → T2 → T3 → T4 → T5 → T6)
- No worktree-parallelism win

## Review History

### plan-reviewer iter 1 (2026-04-29) — NOT APPROVED → corrections applied

**Findings:**
- [warning] AC-12 retained an obsolete "warning count unchanged" clause that referenced a baseline that was never captured. (at: spec.md AC-12)
- [warning] T2 split into 2a/2b without an explicit text-anchored ordering directive. Reviewer flagged risk that an implementer could read it as line-number-anchored and apply edits in the wrong order. (at: plan.md T2)
- [suggestion] AC-3a grep was too loose — bare `grep -q 'Feature 096 #00277'` would also pass if the annotation was misplaced elsewhere in the file. Tighten to anchored awk-pipeline between lineage start and definition. (at: plan.md T1 DoD AC-3a)
- [suggestion] T2 should explicitly note that `import re` at `database.py:7` is retained for `_FTS5_STRIP_RE`. Without the note, an over-aggressive implementer might remove it. (at: plan.md T2)
- [suggestion] AC-8 multi-line note (low priority, deferred — single-line invariant of test_database.py:17 is structurally enforced by Edit text-anchoring).

**Corrections Applied:**
- spec.md AC-12 simplified: dropped warning-count comparison clause; binding signal is `validate.sh` exit 0.
- plan.md T2: prepended explicit ordering directive ("apply 2a BEFORE 2b") and `import re` retention note.
- plan.md T1 DoD AC-3a: replaced bare grep with awk-pipeline anchor between lineage-comment start (`^# Feature 093 FR-1`) and definition line (`^_ISO8601_Z_PATTERN = re.compile`).

### task-reviewer iter 1 (2026-04-29) — APPROVED → 1 suggestion applied

**Findings:**
- [suggestion] tasks.md T1 DoD parenthetical said "8 grep assertions per plan T1 DoD" but plan.md T1 DoD lists 9 distinct grep commands. (at: tasks.md T1 DoD)

**Corrections Applied:**
- tasks.md T1 DoD: "8 grep assertions" → "9 grep assertions".

### plan-reviewer iter 2 + phase-reviewer + relevance-verifier (2026-04-29) — ALL APPROVED

**Findings:**
- plan-reviewer iter 2: APPROVED, zero issues. All iter 1 corrections verified against production files (text anchors match byte-for-byte).
- phase-reviewer: APPROVED, 2 cosmetic suggestions: (1) design.md Status said "14 ACs", should be "15"; (2) plan.md called it "Stage 0" while tasks.md called it "T0".
- relevance-verifier: APPROVED, 2 cosmetic observations (same "14 ACs" stale count + T6 "preferred" qualifier). All 15 ACs trace to tasks with binary DoDs; all 5 TDs/3 components/3 interfaces have implementing tasks; plan text anchors verified.

**Corrections Applied:**
- design.md Status: "14 ACs" → "15 ACs".
- plan.md: renamed "Stage 0" → "T0" (header + DoD line) for 1:1 mapping with tasks.md.
- T6 DoD "preferred" qualifier left as-is — contingency path (qa-override.md) is concretely defined; no implementer ambiguity.
