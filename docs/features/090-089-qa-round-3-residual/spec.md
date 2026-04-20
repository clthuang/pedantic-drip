# Feature 090: 089 QA Round 3 Residual (Surgical Hotfix)

Consolidates 5 findings from feature 089's adversarial review (#00172 HIGH + #00173–#00176 MED). Skips 15 LOWs as accepted tech debt.

## Problem Statement

Feature 089's own adversarial QA (2026-04-20) surfaced 20 findings. After triage:
- 1 HIGH: AC-21 test replays Python-subprocess fallback inline instead of invoking `run_memory_decay` — doesn't exercise the shell's command-selector branching.
- 4 MED: `_assert_testing_context()` bypass vectors, migration 10 schema_version crash window, `query_phase_events_bulk(event_types=[])` contract violation, AC-22 test-spec drift.
- 15 LOW: accepted tech debt (see backlog #00177–#00191).

## Scope

### In scope (fix)
- **#00172 HIGH** AC-21 test invokes real `run_memory_decay`
- **#00173 MED** `_assert_testing_context()` requires `PYTEST_CURRENT_TEST`
- **#00174 MED** Migration 10 in-function schema_version INSERT restored
- **#00175 MED** `query_phase_events_bulk(event_types=[])` contract fix
- **#00176 MED** AC-22 test docstring updated to match current behavior

### Out of scope
- 15 LOW findings (#00177–#00191) — filed as tech debt.

## Functional Requirements

**FR-1 (#00172):** `test-hooks.sh::test_decay_python_subprocess_timeout_fallback` MUST invoke the production `run_memory_decay` function with PATH stripped of `gtimeout`/`timeout`. No inline Python-fallback replay. Test verifies the shell's selector correctly routes to the Python fallback branch.

**FR-2 (#00173):** `_assert_testing_context()` MUST require `os.environ.get('PYTEST_CURRENT_TEST')` in addition to either the `PD_TESTING` env var or `'pytest' in sys.modules`. The `PYTEST_CURRENT_TEST` var is set only WHILE pytest is actively running a test — closes both the parent-shell-env-inheritance and transitive-pytest-import loopholes.

**FR-3 (#00174):** `_migration_10_phase_events` MUST restore the in-function `INSERT OR REPLACE INTO _metadata VALUES ('schema_version', '10')` IMMEDIATELY before its `conn.commit()`. Schema + stamp must commit atomically to eliminate the crash window between migration body and outer-loop stamping. The outer `_migrate()` loop's subsequent stamp becomes a no-op (idempotent ON CONFLICT).

**FR-4 (#00175):** `query_phase_events_bulk(event_types=[])` MUST return zero rows (empty list), not all rows. Change guard from `if event_types:` to `if event_types is not None:` + add explicit `if not event_types: return []` short-circuit at method entry.

**FR-5 (#00176):** `test_record_backward_event_ignores_caller_project_id_mismatch` test docstring MUST be updated to accurately reflect current MCP signature (post-089 the parameter is removed; test pins server-side resolution, not "caller passes fake project_id"). Rename to `test_record_backward_event_uses_entity_project_id_not_server_global`.

## Acceptance Criteria

- **AC-1 (FR-1):** `test-hooks.sh::test_decay_python_subprocess_timeout_fallback` uses `source session-start.sh` + `PATH=/var/empty run_memory_decay` + asserts wall-time < 20s AND stderr contains `'subprocess timeout (10s)'`. No inline Python fallback copy in the test.
- **AC-2 (FR-2):** Unit test: with `PD_TESTING=1` set but `PYTEST_CURRENT_TEST` unset, `_assert_testing_context()` raises `RuntimeError`. With both set, it passes. With only pytest-imported, raises.
- **AC-3 (FR-3):** `grep -nE "INSERT\s+OR\s+REPLACE\s+INTO\s+_metadata.*schema_version.*10" plugins/pd/hooks/lib/entity_registry/database.py` matches INSIDE `_migration_10_phase_events` function body. Test: simulated crash (rollback injected) between migration body and outer stamp — DB has schema_version=10 and phase_events populated, not desynced.
- **AC-4 (FR-4):** `query_phase_events_bulk(type_ids=['feature:x'], event_types=[])` returns `[]`. With `event_types=None`, returns all event types. With `event_types=['started']`, returns only started.
- **AC-5 (FR-5):** Test name is `test_record_backward_event_uses_entity_project_id_not_server_global` (renamed from `_ignores_caller_project_id_mismatch`). Docstring describes the actual server-side resolution contract.

## Implementation Plan

| Task | File | FR | Effort |
|------|------|-----|--------|
| T1 | `plugins/pd/hooks/tests/test-hooks.sh` | FR-1 | rewrite one test function (~30 LOC) |
| T2 | `plugins/pd/hooks/lib/semantic_memory/database.py` | FR-2 | add `PYTEST_CURRENT_TEST` to guard + unit test |
| T3 | `plugins/pd/hooks/lib/entity_registry/database.py` | FR-3 | re-add one INSERT OR REPLACE + update idempotency test |
| T4 | `plugins/pd/hooks/lib/entity_registry/database.py` | FR-4 | guard change + unit test |
| T5 | `plugins/pd/mcp/test_workflow_state_server.py` | FR-5 | rename + docstring update |

Single commit per fix, single implementer dispatch for the whole bundle.

## Non-Functional Requirements

- **NFR-1:** All tests pass (baseline 483 + new tests).
- **NFR-2:** `./validate.sh` passes.
- **NFR-3:** `bash test-hooks.sh` passes (107 + 1 strengthened).

## Success Criteria

1. All 5 ACs pass.
2. 5 backlog entries (#00172–#00176) marked `dropped` in entity DB.
3. Retro captures lessons: (a) grep-AC delegation anti-pattern recurrence at new abstraction layer, (b) atomic-commit discipline in migrations, (c) defense-in-depth guards must check the narrowest signal.
