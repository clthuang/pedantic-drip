# Implementation Log: 131-rotted-doctor-check-fix

## Dispatch 1 — Tasks 1.1, 1.2, 2.1, 2.2, 2.3 (pd:implementer, TDD)

- **Files changed:** `plugins/pd/hooks/lib/doctor/checks.py`, `plugins/pd/hooks/lib/doctor/test_checks.py`
- **Delivered:** `_run_live_schema_query` helper (`(rows, tolerated)` contract, PRAGMA-probe discriminator, EMIT-ONCE dedupe) + 4 unit tests; live fixtures `_make_live_db` (returns `(db, conn)`), `_register_live_feature` (defaults `_UNKNOWN_WORKSPACE_UUID`, `kind=` param), `_insert_workspace`, `_entity_uuid` + 2 smoke tests (incl. workspace round-trip); three checks rewritten to `kind` (sites :709, :988, :1083, :1391, :1398, :1488) with two-arm workspace scoping, merged step-1 loop, steps 2/4 tolerate gates; suites repointed with non-vacuity assertions; scoping tests (a)/(b) TDD-front-loaded.
- **Test run:** test_checks.py 122 passed / 1 skipped (baseline 114); full doctor package 236 passed.
- **Decisions:** separate raw connection alongside EntityDatabase (WAL cross-connection visibility verified); `db.add_dependency()` over raw INSERT; lazy `_UNKNOWN_WORKSPACE_UUID` import mirroring sibling check.
- **Deviations:** task selector strings `-k feature_status`/`-k brainstorm_status` match zero tests (suites are `TestCheck1*`/`TestCheck3*`) — verified via `-k check1_`/`-k check3_`; removed a mid-test connection reopen in the cross-project test (fixture returns a connection, check is read-only, assertions preserved).
- **Concerns:** `check_feature_status` still emits disk-not-in-DB warnings on a tolerated (pre-Mig-11) DB — design-consistent (only `check_entity_orphans` gates membership steps; deliberate asymmetry per design [D].4).

## Dispatch 2 — Tasks 3.1, 4.1, 4.2 (pd:implementer)

- **Files changed:** `checks.py`, `doctor/__init__.py`, `fix_actions/__init__.py`, `fixer.py`, `test_doctor.py`, `test_checks.py`
- **Delivered:** `check_project_attribution` fully deregistered (function, `__init__.py` import/CHECK_ORDER/_ENTITY_DB_CHECKS, `_fix_project_attribution`, `fixer.py` import + `_SAFE_PATTERNS` entry, `test_doctor.py` expected_names); KEPT `backfill_project_ids` + `check_unknown_workspace_orphans`. Behavior tests: a-inverse (unscoped legacy warns), foreign on-disk not step-2-flagged, unknown-bucket on-disk not step-2-flagged (pins spec AC#6), ambiguity fallback, tolerate whole-check zero Issues, empty-DB all-three-clean, check-level surface branch (connection wrapper, exactly one error Issue). Committed EXPLAIN scan test (AST constants-only, 26 sites, 0 failures, ≥20 guard).
- **Test run:** full doctor package 244 passed / 1 skipped.
- **Grep verifications:** zero live `check_project_attribution`/`_fix_project_attribution` references; fixer-net clean (only `workspaces`-table `project_id_legacy` writers).
- **Deviations:** 14 pre-existing CHECK_ORDER count assertions updated 21→20 (direct collateral of the deletion, not enumerated in the surface; leave-ground-tidier).
- **Concerns:** pre-existing class-name misnomer `Test*Has14Checks` (asserts 20) — out of scope, flagged.

## Task 5.1 — Integration verification (orchestrator, inline)

- **Full suite:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/` → 244 passed, 1 skipped, exit 0.
- **Live doctor run** (`PYTHONPATH=plugins/pd/hooks/lib ... -m doctor --entities-db ~/.claude/pd/entities/entities.db --project-root . --artifacts-root docs`):
  - `project_attribution` issues: **0** (spec SC#5 ✓)
  - Orphan-class flags: 12, **genuine false positives (both DB and disk present): 0** — the ~320-warning false-positive class is eliminated (spec SC#2 ✓; discrimination step cross-referenced every flag against disk + `kind='feature'` DB membership)
  - Candidate sets non-empty: `feature_status` 283 issues, `brainstorm_status` 5 (checks ALIVE again — previously silent no-ops; spec SC#3 ✓)
  - Issue totals: 601 before (with dead checks + false positives) → 740 after (0 false positives; previously-hidden true drift now visible — the drift itself is P004 features 126/127's target)
