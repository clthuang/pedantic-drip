# Plan: Feature 093 — 092 QA Residual Hotfix

## Status
- Created: 2026-04-24
- Phase: create-plan
- Upstream: spec.md + design.md

## Implementation Order

Single atomic commit covering all 6 FRs. Direct-orchestrator (no subagent dispatch).

| # | Plan Item | File | FR |
|---|-----------|------|----|
| PI-1 | Harden `_ISO8601_Z_PATTERN`: `\d` → `[0-9]` + `re.ASCII` flag + remove `^/$` anchors | `database.py:17` | FR-1 |
| PI-2 | Convert `.match()` → `.fullmatch()` in `scan_decay_candidates` | `database.py:991` | FR-2 |
| PI-3 | Symmetric `_ISO8601_Z_PATTERN.fullmatch(now_iso)` in `batch_demote` | `database.py:1055` | FR-3 |
| PI-4 | Bounded `{!r:.80}` in scan_decay_candidates stderr warning | `database.py:994` | FR-6 |
| PI-5 | Parametrize existing `test_iso_utc_output_matches_regex` → rename to `test_iso_utc_output_always_passes_hardened_pattern`, 5 datetime boundaries | `test_database.py` | FR-4 |
| PI-6 | Add 3 new parametrized test methods: unicode digits, trailing whitespace, batch_demote invalid + empty-ids short-circuit | `test_database.py` | FR-5 |
| QG | Quality gates: Q1 pytest / Q2 test-hooks.sh / Q3 validate.sh | all | NFR-2/3 |

## Dependency Graph

PI-1 → (PI-2, PI-3, PI-4, PI-5, PI-6 all independent after pattern hardening).
QG sequential after all PI-*.

## AC Coverage Matrix

| AC | Verified by | Test/command |
|----|-------------|--------------|
| AC-1 (pattern uses `[0-9]`) | PI-1 | grep `database.py` |
| AC-1b (`re.ASCII` present) | PI-1 | grep |
| AC-1c (Unicode rejected) | PI-6 | pytest `test_pattern_rejects_unicode_digits` |
| AC-2 (`.fullmatch()` used) | PI-2 + PI-3 | grep |
| AC-2b (trailing whitespace rejected) | PI-6 | pytest `test_pattern_rejects_trailing_whitespace` |
| AC-3 (batch_demote rejects 8 invalid) | PI-6 | pytest `test_batch_demote_rejects_invalid_now_iso` |
| AC-3b (TD-3 preserved) | PI-6 | pytest `test_batch_demote_empty_ids_short_circuits_before_now_iso_check` |
| AC-4 (format-drift pin) | PI-5 | pytest `test_iso_utc_output_always_passes_hardened_pattern` |
| AC-5 (single source of truth) | PI-1 | grep `_ISO8601_Z_PATTERN = re.compile` = 1 |
| AC-6 (regression) | QG | pytest suite ≥ 267 passed |
| AC-7 (shell tests) | QG | test-hooks.sh 109/109 |
| AC-8 (validate.sh) | QG | exit 0 |
| AC-9 (bounded repr) | PI-4 | grep `{not_null_cutoff!r:.80}` |

## Quality Gates

1. **Q1 pytest:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/test_maintenance.py plugins/pd/hooks/lib/semantic_memory/test_database.py -v` → ≥ 267 passed (262 baseline + ≥5 new parametrized)
2. **Q2 test-hooks.sh:** `bash plugins/pd/hooks/tests/test-hooks.sh` → 109/109 unchanged
3. **Q3 validate.sh:** `./validate.sh` → exit 0

**Q5 (post-merge, structural exit per NFR-6):** 4-reviewer adversarial QA dispatch — ≤ 2 MED, zero HIGH.

## Out of Scope

Same as spec — no separate tasks.md. Task breakdown is trivial for surgical scope (6 edits + 4 test methods); design.md Implementation Order + this AC matrix IS the task list.
