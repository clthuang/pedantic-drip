# Tasks: Feature 095 — Test-Hardening Sweep for `_ISO8601_Z_PATTERN`

**Direct-orchestrator** with **single-file scope** — atomic commit. ~80 net LOC + 17 new parametrized assertions in `plugins/pd/hooks/lib/semantic_memory/test_database.py`.

**⚠ Co-read requirement:** This file is a compact task index. Full Old/New text quotes + method bodies live in `plan.md` T1-T9. The direct-orchestrator MUST co-read `plan.md` Implementation Order when running each task.

## Task Index

| ID | Title | File | Depends on |
|----|-------|------|------------|
| **T0** | Capture baselines (PRE_HEAD, PRE_LINES_TD, PRE_PYTEST_PASS=197) | — | none |
| **T1** | Module-level imports — extend line 15 + add `import inspect` | `test_database.py:15-16` | T0 |
| **T2** | Remove redundant inline `_ISO8601_Z_PATTERN` import at ~line 2041 | `test_database.py:~2041` | T1 |
| **T3** | Extend `test_batch_demote_rejects_invalid_now_iso` parametrize: +2 cases (trailing-space + trailing-CRLF) + add `ids=` (FR-2 + FR-4) | `test_database.py:~2102` (TestBatchDemote) | T1 |
| **T4** | Add `test_pattern_rejects_partial_unicode_injection` to `TestScanDecayCandidates` (4 cases) | `test_database.py:~1905` | T1 |
| **T5** | Add `test_batch_demote_rejects_partial_unicode_injection` to `TestBatchDemote` (4 cases) | `test_database.py:~2087` | T1 |
| **T6** | Add new `TestIso8601PatternSourcePins` class with 5 methods (FR-1) | `test_database.py:~2130 (after TestBatchDemote)` | T1, T2 |
| **T7** | Quality gates: validate.sh + pytest count = 214 + database.py diff = 0 | — | T1-T6 |
| **T8** | File backlog entry for `_ISO8601_Z_PATTERN` relocation (Open Q 2) | `docs/backlog.md` | T7 |
| **T9** | `/pd:finish-feature` → triggers feature 094 Step 5b gate (FIRST PRODUCTION RUN) | — | T8 |

## T0 — Baselines

```bash
PRE_HEAD=$(git rev-parse HEAD)
PRE_LINES_TD=$(wc -l < plugins/pd/hooks/lib/semantic_memory/test_database.py)
PRE_PYTEST_PASS=$(plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q 2>&1 | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+')
# Expected PRE_PYTEST_PASS == 197
```

**DoD:** all 3 captured; PRE_PYTEST_PASS = 197 ± 0 else investigate.

## T1 — Module-level imports

Per plan T1: extend line 15 + add `import inspect`.

**DoD:** 2 greps pass (per plan T1 DoD).

## T2 — Remove inline import

Per plan T2: delete inline import inside `test_iso_utc_output_always_passes_hardened_pattern`.

**DoD:** `grep -c 'from semantic_memory.database import _ISO8601_Z_PATTERN' test_database.py` = exactly 1.

## T3 — Extend parametrize

Per plan T3: 8 → 10 cases in `test_batch_demote_rejects_invalid_now_iso`; add `ids=`.

**DoD:** pytest -v shows 10 PASS cases with descriptive ids.

## T4 — TestScanDecayCandidates partial Unicode

Per plan T4: paste 4-case parametrized method.

**DoD:** pytest -v shows 4 PASS cases.

## T5 — TestBatchDemote partial Unicode

Per plan T5: paste 4-case parametrized method.

**DoD:** pytest -v shows 4 PASS cases.

## T6 — TestIso8601PatternSourcePins (NEW class, 5 methods)

Per plan T6: paste full class — 5 methods, 7 assertions total (1+1+3+2).

**DoD:** `grep -qE '^class TestIso8601PatternSourcePins'` AND pytest -v shows 7 PASS cases.

## T7 — Quality gates

```bash
./validate.sh                                                                   # exit 0
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_database.py -q 2>&1 | tail -1    # = "214 passed"
git diff develop...HEAD -- plugins/pd/hooks/lib/semantic_memory/database.py | wc -l    # = 0
```

**DoD:** all 3 commands return expected output.

## T8 — File backlog entry

Per plan T8: append new entry to `docs/backlog.md` for `_ISO8601_Z_PATTERN` relocation to `_config_utils.py`.

**DoD:** new entry with `(filed by feature:095 — relocate pattern to config-utils)` marker.

## T9 — /pd:finish-feature (gate dogfood)

Per plan T9: run `/pd:finish-feature` on feature/095 branch. **This is the first production exercise of feature 094's Step 5b gate.**

**DoD:**
- Gate dispatches 4 reviewers (security, code-quality, implementation, test-deepener Step A)
- AC-13a: retro.md "Manual Verification" section contains required tokens
- AC-13b: retro.md captures `+++ b/plugins/pd/hooks/lib/semantic_memory/test_database.py` from one reviewer's dispatch context
- Merge → release; pushed to main; v4.16.5 tag (or whatever release.sh determines)
- If gate fails on first run: R-5 contingency — capture failure in retro, file backlog against feature 094, use qa-override.md ≥50-char rationale path

## AC Coverage (summary)

All 14 ACs auto-verified per plan.md AC Coverage Matrix:
- AC-1, AC-2, AC-10, AC-11, AC-12: structural greps + counts
- AC-3..AC-9: pytest -v shows passing cases
- AC-13a, AC-13b: retro.md grep + dispatch-text capture during T9
