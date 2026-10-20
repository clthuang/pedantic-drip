# Tasks: Feature 096 — Relocate `_ISO8601_Z_PATTERN`

**Direct-orchestrator** with **single-file-per-task scope**. Total: 3-file edit + atomic commit. Net +2 LOC production touch.

**⚠ Co-read requirement:** This file is a compact task index. Full Old/New text quotes + verbatim code blocks live in `plan.md` T1-T6. Direct-orchestrator MUST co-read `plan.md` Implementation Order when running each task.

## Task Index

| ID | Title | File | Depends on |
|----|-------|------|------------|
| **T0** | Capture baselines (PRE_HEAD, PRE_PYTEST_PASS=214, PRE_PYTEST_PASS_WIDE=3198) | — | none |
| **T1** | Edit `_config_utils.py`: add `import re` + lineage comment + definition + feature 096 annotation + convention comment | `_config_utils.py` | T0 |
| **T2** | Edit `database.py`: remove lines 14-26 (def + comment), add new import line | `database.py` | T1 |
| **T3** | Edit `test_database.py:17`: split into 2-line import block | `test_database.py` | T2 |
| **T4** | Quality gates: validate.sh + pytest narrow=214 + pytest wide=3198 + TestIso8601PatternSourcePins=7 | — | T1, T2, T3 |
| **T5** | Atomic commit + AC-13 hash-equality assertion | — | T4 |
| **T6** | `/pd:finish-feature` → SECOND production exercise of feature 094 Step 5b gate → release v4.16.6 | — | T5 |

## T0 — Baselines

```bash
PRE_HEAD=$(git rev-parse HEAD)
PRE_PYTEST_PASS=$(plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q 2>&1 | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
PRE_PYTEST_PASS_WIDE=$(plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ -q 2>&1 | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
# Expected: PRE_PYTEST_PASS=214; PRE_PYTEST_PASS_WIDE=3198
```

**DoD:** 3 baselines captured; both pytest counts match expected exactly.

## T1 — `_config_utils.py` edit

Per plan T1: add `import re` + relocated definition with 9-line lineage comment + 3-line feature 096 annotation + convention comment, after `_iso_utc` (line 47).

**DoD:** All AC-1, AC-2, AC-3, AC-3a, AC-4, AC-14 grep checks pass (9 grep assertions per plan T1 DoD).

## T2 — `database.py` edit

Per plan T2: remove lines 14-26 (lineage comment + definition) + add `from semantic_memory._config_utils import _ISO8601_Z_PATTERN` after `from typing import Callable` (line 12).

**DoD:** AC-5, AC-6, AC-7 grep checks pass (3 assertions).

## T3 — `test_database.py:17` edit

Per plan T3: split line 17 into 2 import lines (database-side keeps `MemoryDatabase, _sanitize_fts5_query`; new line for `_config_utils._ISO8601_Z_PATTERN`).

**DoD:** AC-8 (`grep -c returns 0`), AC-9 (grep) pass.

## T4 — Quality gates

```bash
./validate.sh                                                                              # exit 0
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q | tail -1   # = "214 passed"
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ -q | tail -1                  # = "3198 passed"
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py::TestIso8601PatternSourcePins -q | tail -1   # = "7 passed"
```

**DoD:** AC-10 (both pytest counts), AC-11 (TestIso8601PatternSourcePins=7), AC-12 (validate.sh exit 0).

## T5 — Atomic commit

```bash
git add plugins/pd/hooks/lib/semantic_memory/{_config_utils,database,test_database}.py
git commit -m "pd(096): relocate _ISO8601_Z_PATTERN to _config_utils.py per #00277"

# AC-13 hash-equality verification
H1=$(git log develop..HEAD --format=%H -- plugins/pd/hooks/lib/semantic_memory/_config_utils.py)
H2=$(git log develop..HEAD --format=%H -- plugins/pd/hooks/lib/semantic_memory/database.py)
H3=$(git log develop..HEAD --format=%H -- plugins/pd/hooks/lib/semantic_memory/test_database.py)
test "$H1" = "$H2" -a "$H2" = "$H3" -a -n "$H1" && [[ $(echo "$H1" | wc -w) -eq 1 ]] && echo PASS || echo FAIL
```

**DoD:** AC-13 returns PASS (3 hashes equal, single non-empty hash).

## T6 — `/pd:finish-feature` (gate dogfood + release)

Run `/pd:finish-feature` on feature 096 branch. Triggers feature 094 Step 5b gate (SECOND production exercise).

**DoD:**
- 4 reviewers dispatched in parallel against 3-file production diff
- Gate verdict per FR-6: HIGH=0 → PASS (preferred), else qa-override.md path per R-6 contingency
- Auto-fold of any `.qa-gate.log` / `.qa-gate-low-findings.md` sidecars (closes feature 094 AC-13 retro-fold deferred-verification)
- Merged to develop, pushed, v4.16.6 tagged

## AC Coverage (summary)

All 15 ACs auto-verified per plan.md AC Coverage Matrix:
- T1 covers: AC-1, AC-2, AC-3, AC-3a, AC-4, AC-14 (6 ACs)
- T2 covers: AC-5, AC-6, AC-7 (3 ACs)
- T3 covers: AC-8, AC-9 (2 ACs)
- T4 covers: AC-10, AC-11, AC-12 (3 ACs)
- T5 covers: AC-13 (1 AC)

Zero manual-only ACs.
