# Implementation Log — Feature 106

Direct-orchestrator pattern (6th consecutive feature: 101, 102, 104, 105, 106). Heavy upstream review (specify 2 + design 1 + create-plan 3 = 6 iterations) enabled single-pass implementation.

## Summary

All 10 tasks executed; all 18 ACs verified PASS.

| Task | FR | Backlog | Status | Notes |
|------|-----|---------|--------|-------|
| T1 | FR-5 | #00315 | PASS | guard added inline; CLAUDE_CODE_DEV_MODE=1 exported in test-capture-on-stop.sh |
| T2 | FR-2 | #00311 | PASS | 3 test scripts wired into test-hooks.sh; commands-reference.md updated |
| T3 | FR-3 | #00312 | PASS | 6 tests in consolidated test-session-start.sh (1 corr + 5 mcp); sed-extract for both |
| T4 | FR-4 | #00313 | PASS | test_category_mapping → 2 functions; bottom invocation updated |
| T5 | FR-6 | #00316 | PASS | log_info lines swapped in validate.sh |
| T6 | FR-7 | #00318 | PASS | "(line 726)" dropped from secretary.md R-8 note |
| T7 | FR-1a | #00310 | PASS | TD-2 amendment appended to feature 104 design.md |
| T8 | FR-1b | #00319 | PASS | "Committed vs gitignored evidence paths" subsection added to component-authoring.md |
| T10 | — | — | PASS | validate.sh exit 0; test-hooks.sh 114/114 + 6/6 external = 120 tests; pattern_promotion 226/226 |
| T9 | FR-8 | #00310-#00319 | PASS | all 10 backlog rows annotated with (closed: ...) |

## Verification Outputs

### T1 (FR-5)
- AC-5.1 PASS: guard `CLAUDE_CODE_DEV_MODE` present in seam section
- AC-5.2 PASS: `test-capture-on-stop.sh` 10/10 tests pass after guard + export

### T3 (FR-3)
- AC-3.1 PASS: hyphenated file exists, underscored deleted, both function refs present
- AC-3.2 PASS: sed-extract for both `cleanup_stale_correction_buffers` and `cleanup_stale_mcp_servers`
- AC-3.3 PASS: 6 test functions in consolidated file
- AC-3.4 PASS: `test-session-start.sh` 6/6 tests pass

### T4 (FR-4)
- AC-4.1 PASS: 2 functions matching `^test_category_mapping_(anti_patterns|preference)\(\)`
- AC-4.2 PASS: `test-capture-on-stop.sh` 11/11 tests pass after refactor

### T2 (FR-2)
- AC-2.1 PASS: 3 invocation lines for the 3 external scripts in test-hooks.sh
- AC-2.2 PASS: `test-hooks.sh` 114/114 + 6 external = 120 tests pass; exit 0
- AC-2.3 PASS: commands-reference.md references test-hooks.sh

### T10 (Final validation)
- `./validate.sh` exit 0 (Errors: 0, Warnings: 5)
- `bash plugins/pd/hooks/tests/test-hooks.sh` exit 0 (114/114 internal + 6/6 external)
- `cd plugins/pd && PYTHONPATH=hooks/lib .venv/bin/python -m pytest hooks/lib/pattern_promotion/ -q` → 226 passed

### T9 (FR-8)
- AC-8.1 PASS: all 10 rows (#00310-#00319) annotated with (closed: ...) text

## Files Changed

10 modifies + 1 delete:
- plugins/pd/hooks/capture-on-stop.sh
- plugins/pd/hooks/tests/test-capture-on-stop.sh
- plugins/pd/hooks/tests/test-session-start.sh
- plugins/pd/hooks/tests/test-hooks.sh
- plugins/pd/commands/secretary.md
- validate.sh
- docs/features/104-batch-b-test-hardening/design.md (TD-2 amendment)
- docs/dev_guides/component-authoring.md (new subsection)
- docs/dev_guides/commands-reference.md (test-hooks.sh comment)
- docs/backlog.md (10 row annotations)
- DELETE: plugins/pd/hooks/tests/test_session_start_cleanup.sh
