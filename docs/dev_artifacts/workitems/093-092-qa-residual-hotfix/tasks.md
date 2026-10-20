# Tasks: Feature 093 — 092 QA Residual Hotfix

**Direct-orchestrator execution** — tight scope (6 FRs, ~20 prod LOC + ~80 test LOC) lands in a single atomic commit. Full task detail is co-located in `plan.md`'s Implementation Order + AC Coverage Matrix (deliberate — separate `tasks.md` would duplicate content for this surgical scope).

## Task Index

| ID | Title | File | Depends on |
|----|-------|------|------------|
| T1 | Pattern hardening + symmetric application (PI-1..PI-4) | `plugins/pd/hooks/lib/semantic_memory/database.py` | none |
| T2 | Format-drift pin parametrized test (PI-5) | `plugins/pd/hooks/lib/semantic_memory/test_database.py` | T1 |
| T3 | 4 new parametrized test methods (PI-6) | `plugins/pd/hooks/lib/semantic_memory/test_database.py` | T1 |
| Q1 | Full pytest suite | all | T1, T2, T3 |
| Q2 | `bash plugins/pd/hooks/tests/test-hooks.sh` | — | — |
| Q3 | `./validate.sh` | — | — |

## T1 — Pattern hardening + symmetric application

**File:** `plugins/pd/hooks/lib/semantic_memory/database.py`

Edits (see spec FR-1, FR-2, FR-3, FR-6 for exact before/after):

1. Line 17: pattern → `re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', re.ASCII)` (anchors removed)
2. Line 991: `.match()` → `.fullmatch()` in `scan_decay_candidates`
3. Line 994: bounded repr `{not_null_cutoff!r:.80}` in stderr warning
4. Line 1055: `if not now_iso:` → `if not _ISO8601_Z_PATTERN.fullmatch(now_iso):` + updated ValueError message with `{now_iso!r:.80}`

**DoD:**
```bash
grep -c '\\d{4}' plugins/pd/hooks/lib/semantic_memory/database.py        # = 0
grep -cE 're\.compile.*re\.ASCII' plugins/pd/hooks/lib/semantic_memory/database.py  # >= 1
grep -c '_ISO8601_Z_PATTERN\.fullmatch' plugins/pd/hooks/lib/semantic_memory/database.py  # >= 2
grep -c '_ISO8601_Z_PATTERN\.match(' plugins/pd/hooks/lib/semantic_memory/database.py  # = 0
grep -c '{not_null_cutoff!r:\.80}' plugins/pd/hooks/lib/semantic_memory/database.py  # >= 1
grep -c '_ISO8601_Z_PATTERN = re\.compile' plugins/pd/hooks/lib/semantic_memory/database.py  # = 1
```

## T2 — Format-drift pin parametrized test

**File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`

Rename + parametrize existing `test_scan_decay_candidates_matches_iso_utc_output` to `test_iso_utc_output_always_passes_hardened_pattern` per spec FR-4. 5 datetime boundaries: canonical, microsecond=999999, year=9999, year=1, leap year.

**DoD:** `pytest -k test_iso_utc_output_always_passes_hardened_pattern` → 5 parametrized passed.

## T3 — 4 new parametrized test methods

**File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`

Add per spec FR-5:
1. `test_pattern_rejects_unicode_digits` (3 parametrized: fullwidth, Arabic-Indic, Devanagari)
2. `test_pattern_rejects_trailing_whitespace` (3 parametrized: `\n`, ` `, `\r\n`)
3. `test_batch_demote_rejects_invalid_now_iso` (8 parametrized per spec)
4. `test_batch_demote_empty_ids_short_circuits_before_now_iso_check`

**DoD:** all 4 methods pass; AC-3 covers 8 invalid cases; AC-3b passes; AC-1c/AC-2b pass.

## Q1 / Q2 / Q3

Per plan.md Quality Gates — pytest ≥ 267 passed, test-hooks.sh 109/109, validate.sh exit 0.
