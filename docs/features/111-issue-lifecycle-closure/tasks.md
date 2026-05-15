# Tasks — Feature 111: Issue Lifecycle Closure

- **Plan:** plan.md rev 1
- **Status:** revision 1
- **TDD discipline:** Implementer-skill MUST execute RED-tests-first regardless of task list order. Each Group's task list is logical ordering, not test-after-code.

## Group A — Migration 14 (DDL only)

**Scope:** `plugins/pd/hooks/lib/entity_registry/database.py` ONLY. No Python logic outside the migration. No test files. Commit boundary: one commit, schema DDL only.

### Task A.1 — Define MigrationError + import audit_log helper (if needed)
- **File:** `database.py`
- **What:** Verify `MigrationError` is importable (existing) and `_append_migration_audit_log` helper exists. If not, skip — the function names used in `_migration_14_*` may already exist from features 109/110 precedent.
- **Done when:** Grep `class MigrationError` and `def _append_migration_audit_log` confirm both symbols.
- **Time:** 3 min

### Task A.2 — Write `_copy_rename_entities_for_v14(conn)` helper
- **File:** `database.py` (alongside migration-12 copy-rename helpers around `:2960-3030`)
- **What:** Replicate migration-12 entities copy-rename idiom with widened (type, kind) CHECK: `(type='work' AND kind IN ('feature','backlog','bug','initiative','objective','key_result','task'))`. Preserve all existing columns by name. Save + restore triggers and non-FTS indices.
- **Done when:** Function compiles; ready for use by main migration body.
- **Time:** 12 min

### Task A.3 — Write `_copy_rename_phase_events_for_v14(conn)` helper
- **File:** `database.py`
- **What:** Replicate migration-12 phase_events copy-rename idiom with widened event_type CHECK adding `'spawned_child'` (8 values total). Save + restore triggers and indices.
- **Done when:** Function compiles.
- **Time:** 12 min

### Task A.4 — Write `_migration_14_issue_lifecycle_closure(conn)` main body
- **File:** `database.py`
- **What:** Implement per design IF-3 skeleton: idempotency early-return, PRAGMA foreign_keys=OFF, BEGIN IMMEDIATE, concurrent re-check, pre-flight gates (schema_version=13, entity_display present, migration_audit_log present, entity_relations absent), CREATE entity_relations + 3 indices, UPDATE entities SET lifecycle_class='task_flow' WHERE kind='task', call _copy_rename_entities_for_v14, call _copy_rename_phase_events_for_v14, pre-commit FK check, stamp schema_version=14 + audit log, COMMIT.
- **Done when:** Function compiles; ready to register in MIGRATIONS dict.
- **Time:** 15 min

### Task A.5 — Write `_copy_rename_entities_to_v13(conn)` + `_copy_rename_phase_events_to_v13(conn)` down helpers
- **File:** `database.py`
- **What:** Mirror images of A.2 and A.3 — narrow CHECKs back to v13 form. Drop `'bug'` from work-kind enum; drop `'spawned_child'` from event_type enum.
- **Done when:** Both functions compile.
- **Time:** 15 min

### Task A.6 — Write `_migration_14_down(conn)` (down-migration)
- **File:** `database.py`
- **What:** Per design IF-3 `_migration_14_down`: pre-flight refuse if `kind='bug'` rows or entity_relations rows exist; drop entity_relations + indices; DELETE phase_events WHERE event_type='spawned_child'; call _copy_rename_phase_events_to_v13; call _copy_rename_entities_to_v13; revert task lifecycle_class remap.
- **Done when:** Function compiles.
- **Time:** 12 min

### Task A.7 — Register migration in MIGRATIONS + MIGRATIONS_DOWN dicts
- **File:** `database.py` (near top, where MIGRATIONS dict lives)
- **What:** `MIGRATIONS[14] = _migration_14_issue_lifecycle_closure`. `MIGRATIONS_DOWN[14] = _migration_14_down`.
- **Done when:** Both dict entries present.
- **Time:** 3 min

### Task A.8 — Smoke-validate via Python REPL
- **What:** `python -c "from entity_registry.database import MIGRATIONS, MIGRATIONS_DOWN; assert 14 in MIGRATIONS and 14 in MIGRATIONS_DOWN; print('OK')"` (or use the project's venv).
- **Done when:** Prints "OK" — confirms registration. No DB run yet (Group B's tests run the migration).
- **Time:** 3 min

### Task A.9 — Commit Group A
- **What:** `git add database.py; git commit -m "feat(111): Migration 14 — entity_relations table + (type,kind) + event_type CHECK widenings"`
- **Done when:** Commit lands cleanly on feature branch. No test files in the commit.
- **Time:** 3 min

**Group A total:** ~80 min for ~750 lines of DDL/migration code.

---

## Group B — Discriminator + constants + helpers + tests

**Scope:** All Python application logic, exception classes, new EntityDatabase helpers, defensive raise, and Group A's tests (which depend on Group B symbols).

### Task B.1 — RED: Write test_migration_14_safety.py
- **File:** `plugins/pd/hooks/lib/entity_registry/test_migration_14_safety.py` (NEW)
- **What:** Verify all AC-MR.x (1-11). Tests run the migration on a synthetic v13 fixture DB and assert:
  - `PRAGMA table_info(entity_relations)` matches schema
  - 3 indices present
  - `sqlite_master.sql for 'entities'` contains substring `'feature','backlog','bug','initiative','objective','key_result','task'`
  - `sqlite_master.sql for 'phase_events'` contains `'spawned_child'`
  - Pre-flight failures (stale-12 DB, existing entity_relations table) abort with substring-matching messages
  - Replay no-op
  - Down-migration on clean v14 → byte-identical to pre-v14 (entities, workflow_phases, phase_events excluding spawned_child) plus schema_migrations.MAX=13
  - Down-migration with bug entities → MigrationError "Cannot down-migrate v14...bug entities"
  - Down-migration with entity_relations rows → MigrationError "...entity_relations"
  - FK enforcement after migration (INSERT entity_relations with non-existent from_uuid raises FK violation)
- **Done when:** Tests written; running them FAILS (expected — Group A symbols don't yet have their tests; this is RED phase).
- **Time:** 25 min

### Task B.2 — RED: Write test_status_only_lifecycle.py
- **File:** `plugins/pd/hooks/lib/entity_registry/test_status_only_lifecycle.py` (NEW)
- **What:** Verify all AC-BL.x (1-7):
  - `ENTITY_MACHINES` does NOT contain 'bug' or 'task' keys
  - `_KIND_TO_TYPE_LIFECYCLE['bug']` returns `('work', 'bug_flow')`; `_KIND_TO_TYPE_LIFECYCLE['task']` returns `('work', 'task_flow')`
  - `_CLOSES_TERMINAL` dict contents (3 keys, correct values)
  - After register_entity(entity_type='bug', auto_id, status='open'): entities row has correct triple; NO workflow_phases row
  - Direct `update_entity(bug_uuid, status='resolved')` succeeds; no workflow_phases write
  - closes= on a status='open' bug → status='closed' + entity_relations row + NO workflow_phases gain
  - `transition_entity_phase(type_id='bug:X', ...)` raises ValueError with substring "uses status-only lifecycle"
- **Done when:** Tests written; running them FAILS.
- **Time:** 20 min

### Task B.3 — RED: Add AC-EX.x tests to test_status_only_lifecycle.py
- **File:** same as B.2
- **What:** Two test cases:
  - `from entity_registry.database import EntityNotFoundError, InvalidCloseTargetError` succeeds; both `issubclass(..., ValueError)` is True.
  - MCP error envelope shape: smoke-test that complete_phase MCP returns `{"error": true, "error_type": "entitynotfounderror", "message": "..."}` for a nonexistent caller (this overlaps with AC-EX.2 — may move to test_complete_phase_closes.py in Group D).
- **Done when:** Both assertions written; FAIL until Group B code lands.
- **Time:** 6 min

### Task B.4 — RED: Extend test_entity_lifecycle.py for AC-BL.7
- **File:** `plugins/pd/hooks/lib/entity_registry/test_entity_lifecycle.py`
- **What:** Add 1-2 tests asserting `transition_entity_phase(type_id='bug:X', workflow_phase='resolved', ...)` raises ValueError with substring "uses status-only lifecycle".
- **Done when:** Tests added; FAIL.
- **Time:** 5 min

### Task B.5 — RED: Audit test_workflow_state_server.py
- **File:** `plugins/pd/mcp/test_workflow_state_server.py`
- **What:** Per CLAUDE.md "ENTITY_MACHINES has assertions in TWO test files", grep this file for `ENTITY_MACHINES` references. If any test asserts specific keys or transition graphs, update so it doesn't break when Group B lands the defensive raise.
- **Done when:** Audit complete; either no impact OR fixtures updated.
- **Time:** 5 min

### Task B.6 — GREEN: Add EntityNotFoundError + InvalidCloseTargetError
- **File:** `database.py` near line 4484 (`EntityExistsError`)
- **What:** Per IF-9 — both classes subclass `ValueError`, single-line `pass` body, docstrings per IF-9 template.
- **Done when:** Both classes defined; importable.
- **Time:** 5 min

### Task B.7 — GREEN: Add `_CLOSES_TERMINAL` dict
- **File:** `database.py` near `_KIND_TO_TYPE_LIFECYCLE` (line 48)
- **What:** Module-level dict per IF-7: `_CLOSES_TERMINAL = {"bug_flow": "closed", "task_flow": "closed", "work_flow": "dropped"}`.
- **Done when:** Constant defined.
- **Time:** 3 min

### Task B.8 — GREEN: Extend `_KIND_TO_TYPE_LIFECYCLE`
- **File:** `database.py:48`
- **What:** Add `'bug': ('work', 'bug_flow')` row; change `'task'` row from `('work', 'work_flow')` to `('work', 'task_flow')`.
- **Done when:** Dict has 9 rows; tests B.2 row referencing bug/task pass.
- **Time:** 3 min

### Task B.9 — GREEN: Extend `_VALID_PARAMS`
- **File:** `database.py:4442`
- **What:** Add `'spawned_child': {'metadata'}` row to dict.
- **Done when:** Dict has 8 rows.
- **Time:** 3 min

### Task B.10 — GREEN: Extend `VALID_ENTITY_TYPES` tuple
- **File:** `database.py:4534`
- **What:** Add `'bug'` to the tuple (9 values).
- **Done when:** Tuple has 9 values; tests pass.
- **Time:** 3 min

### Task B.11 — GREEN: Add `db.get_entity_by_uuid` method
- **File:** `database.py` (alongside existing entity methods)
- **What:** Public method: `def get_entity_by_uuid(self, uuid: str) -> dict | None`. SELECTs all entities columns for the uuid; returns dict (use `sqlite3.Row` → dict conversion) or None.
- **Done when:** Method works; unit test in test_status_only_lifecycle.py passes.
- **Time:** 7 min

### Task B.12 — GREEN: Add `db.get_prior_closer` method
- **File:** `database.py`
- **What:** `def get_prior_closer(self, to_uuid: str) -> str | None`. SELECT `from_uuid FROM entity_relations WHERE to_uuid=? AND kind='fixes' LIMIT 1`; return uuid or None.
- **Done when:** Method works.
- **Time:** 5 min

### Task B.13 — GREEN: Add `db.insert_entity_relation` method
- **File:** `database.py`
- **What:** `def insert_entity_relation(self, from_uuid: str, to_uuid: str, kind: str, on_conflict: str = "raise") -> bool`. INSERT INTO entity_relations(from_uuid, to_uuid, kind, created_at); when `on_conflict='ignore'`, append `ON CONFLICT(from_uuid, to_uuid, kind) DO NOTHING`. Returns True on insert, False on conflict-ignore. Use `conn.execute().rowcount` to detect.
- **Done when:** Method works for both modes.
- **Time:** 8 min

### Task B.14 — GREEN: Add `db.resolve_entity_uuid` method
- **File:** `database.py`
- **What:** `def resolve_entity_uuid(self, workspace_uuid: str, type_id: str) -> tuple[str | None, str | None]`. SELECT `uuid, workspace_uuid FROM entities WHERE workspace_uuid=? AND type_id=?`; return `(uuid, workspace_uuid)` or `(None, None)`.
- **Done when:** Method works.
- **Time:** 5 min

### Task B.15 — GREEN: Add defensive raise in `transition_entity_phase`
- **File:** `entity_lifecycle.py:124` (transition_entity_phase function)
- **What:** Before the existing `ENTITY_MACHINES[entity_type]` lookup, add: `if entity_type in ("bug", "task"): raise ValueError(f"invalid_entity_type: {entity_type} uses status-only lifecycle; use update_entity directly")`.
- **Done when:** Tests B.4 + relevant B.2 case pass.
- **Time:** 5 min

### Task B.16 — Run all Group B tests + Group A's tests via Group B's test files
- **What:** `cd plugins/pd && .venv/bin/python -m pytest hooks/lib/entity_registry/test_migration_14_safety.py hooks/lib/entity_registry/test_status_only_lifecycle.py hooks/lib/entity_registry/test_entity_lifecycle.py -v`
- **Done when:** All tests green. AC-MR.x + AC-BL.x + AC-EX.x verified.
- **Time:** 5 min

### Task B.17 — Commit Group B
- **What:** `git add database.py entity_lifecycle.py test_migration_14_safety.py test_status_only_lifecycle.py test_entity_lifecycle.py [test_workflow_state_server.py]; git commit -m "feat(111): Group B — discriminator constants + helpers + exceptions + migration tests"`
- **Done when:** Commit lands. PR contains both Group A and Group B commits.
- **Time:** 3 min

**Group B total:** ~120 min for ~600 LoC application + ~400 LoC tests.

---

## Group C — F9 `issue_spawn` MCP (parallelizable with D, E after B)

### Task C.1 — RED: Write test_issue_spawn.py
- **File:** `plugins/pd/mcp/test_issue_spawn.py` (NEW)
- **What:** Verify all AC-9.x:
  - AC-9.1: issue_spawn(kind='bug', summary='Foo') → entity (work, bug, bug_flow, status='open', parent_uuid set, entity_id matches `^\d+-foo`); response JSON contains uuid; entity_display row exists
  - AC-9.2: column-level invariance of parent's `workflow_phase` and `kanban_column`
  - AC-9.3: exactly 1 phase_event on parent with event_type='spawned_child', phase IS NULL, metadata contains child_uuid/child_kind/child_name
  - AC-9.4: invalid kind raises ValueError before any DB write (counts unchanged)
  - AC-9.5: nonexistent parent_uuid → ValueError; disallowed parent kind → ValueError
  - AC-9.6: entity_id matches `^\d+-.+`
  - AC-9.7: entity_display row count = 1 with non-null seq + slug
  - AC-9.8: doctor check_status_write_path passes on issue_spawn code
  - AC-9.9: metadata shallow merge with system keys winning; `parent_uuid` injected metadata key is dropped
- **Done when:** Tests written; fail (issue_spawn doesn't exist yet).
- **Time:** 30 min

### Task C.2 — GREEN: Implement `issue_spawn` MCP tool
- **File:** `plugins/pd/mcp/entity_server.py`
- **What:** Per design IF-1 steps 1-11. Use new helpers from Group B (`db.get_entity_by_uuid`, `id_generator.generate_entity_id`, `db.register_entity`, `db.append_phase_event`). Add `@mcp.tool()` decorator. Mirror error-translation pattern from existing register_entity MCP.
- **Done when:** All AC-9.x tests pass.
- **Time:** 25 min

### Task C.3 — Verify check_status_write_path
- **What:** Run the doctor AST check against entity_server.py: `cd plugins/pd && .venv/bin/python -m doctor check_status_write_path` (or whatever the invocation is per existing doctor patterns).
- **Done when:** Check passes (issue_spawn uses append_phase_event for parent events, no direct phase_events INSERT).
- **Time:** 3 min

### Task C.4 — Commit Group C
- **What:** `git add entity_server.py test_issue_spawn.py; git commit -m "feat(111): F9 — issue_spawn MCP for spontaneous mid-flight issue capture"`
- **Done when:** Commit lands.
- **Time:** 3 min

**Group C total:** ~60 min.

---

## Group D — F10 complete_phase closes= extension (parallelizable with C, E after B)

### Task D.1 — Verify transaction-close ordering at workflow_state_server.py:1127-1234
- **File:** read-only audit of `plugins/pd/mcp/workflow_state_server.py:1086-1234`
- **What:** Per design IF-2 CRITICAL note: identify where the existing `with db.transaction():` block COMMITs. If a post-commit dual-write of `append_phase_event` exists OUTSIDE the with-block, the closure block must be inserted BEFORE the COMMIT (inside the with-block). Document findings inline in commit message.
- **Done when:** Audit complete; design phase implementer plan for IF-2 inline-or-hoist decided.
- **Time:** 8 min

### Task D.2 — RED: Write test_complete_phase_closes.py
- **File:** `plugins/pd/mcp/test_complete_phase_closes.py` (NEW)
- **What:** Verify all AC-10.x (10.1–10.11):
  - 10.1: closes=[u_bug, u_task] → both closed + 2 entity_relations rows in one transaction
  - 10.2: closes=None → response includes `closes_applied: []`, identical to pre-feature-111 behavior
  - 10.3: atomic rollback on lifecycle_class mismatch (feature in closes list); feature's phase unchanged
  - 10.4: 3 replays with same closer → 1 entity_relations row + 1 entity_status_changed phase_event per uuid
  - 10.5: cross-closer raises with substring "already closed by different closer"
  - 10.6: cross-workspace raises with substring "cross-workspace closure forbidden"
  - 10.7: terminal-without-closer raises with substring "already terminal but no closer record"
  - 10.8: closed entities receive entity_status_changed phase_event with metadata old_status/new_status/closed_by_uuid
  - 10.9: caller not registered → EntityNotFoundError (or its MCP-translated envelope)
  - 10.10: feature in closes → InvalidCloseTargetError "feature entities cannot be closed via closes="
  - 10.11: backlog at status='open' closed via closes= → status='dropped' (state-machine bypass) + phase_event metadata old_status='open'
- **Done when:** Tests written; fail (closes= not implemented).
- **Time:** 35 min

### Task D.3 — GREEN: Extend `_process_complete_phase` with closure block
- **File:** `plugins/pd/mcp/workflow_state_server.py:1086`
- **What:** Per design IF-2 pseudocode. Use new helpers (`db.resolve_entity_uuid`, `db.get_entity_by_uuid`, `db.get_prior_closer`, `db.insert_entity_relation`). Honor the COMMIT-ordering decision from D.1. Pass `workspace_uuid=caller_workspace_uuid` to `append_phase_event` for entity_status_changed events. Append to `closes_applied` unconditionally (after insert, including replay path).
- **Done when:** All AC-10.x tests pass.
- **Time:** 30 min

### Task D.4 — GREEN: Extend `complete_phase` MCP signature
- **File:** `plugins/pd/mcp/workflow_state_server.py:1809`
- **What:** Add `closes: list[str] | None = None` keyword arg (after `*, ref`). Pass-through to `_process_complete_phase`. Response JSON includes `closes_applied` field.
- **Done when:** Smoke-test: calling `complete_phase` without closes still works; calling with closes=[u1] writes the relation row.
- **Time:** 5 min

### Task D.5 — Commit Group D
- **What:** `git add workflow_state_server.py test_complete_phase_closes.py; git commit -m "feat(111): F10 — complete_phase(closes=[...]) atomic closure linkage"`
- **Done when:** Commit lands.
- **Time:** 3 min

**Group D total:** ~85 min.

---

## Group E — Cleanup + new doctor check (parallelizable with C, D after B)

### Task E.1 — RED: Write test_cleanup_suffix_parsers.py
- **File:** `plugins/pd/hooks/lib/entity_registry/test_cleanup_suffix_parsers.py` (NEW)
- **What:** Verify AC-CL.1 + AC-CL.2 + AC-CL.3:
  - AC-CL.1: grep `\(closed:|\(promoted →|\(fixed:` against `entity_registry/backfill.py` and `doctor/checks.py` returns 0 matches
  - AC-CL.2: backfill behavior documented as changed; no parse of historical free-text markers
  - AC-CL.3: synthetic backlog row with status='dropped' + entity_relations row → doctor identifies it as closed-by-feature_X (no parsing involved)
- **Done when:** Tests written; AC-CL.1 fails (parsers still present); AC-CL.3 may already pass or fail depending on current doctor logic.
- **Time:** 15 min

### Task E.2 — RED: Extend test_doctor.py for check_no_free_text_status_parsers
- **File:** `plugins/pd/hooks/lib/doctor/test_doctor.py`
- **What:** Verify AC-CL.4:
  - check_no_free_text_status_parsers PASSES on production code (grep returns 0)
  - synthetic regression (inject `(closed:` into a temp copy of backfill.py) → check FAILS
  - check produces identical result from project root AND from a subdirectory (2-CWD test)
- **Done when:** Tests written; fail (check doesn't exist yet).
- **Time:** 12 min

### Task E.3 — DELETE: Free-text parser at entity_registry/backfill.py:418-444
- **File:** `plugins/pd/hooks/lib/entity_registry/backfill.py`
- **What:** Remove the derived_status block (lines 418-444 per codebase-explorer pin). Keep the `get_entity` + `upsert_entity` calls above it.
- **Done when:** Grep at AC-CL.1 passes against this file. Existing backfill tests that consume the parser output need migration (Task E.5).
- **Time:** 5 min

### Task E.4 — DELETE: Free-text parser at doctor/checks.py:983-1015
- **File:** `plugins/pd/hooks/lib/doctor/checks.py`
- **What:** Remove the regex compilation (promoted_pattern, closed_pattern) and the line-loop matching block. Preserve the entities_conn cross-ref infra below line :1029 — this becomes the sole closure detection mechanism (DB state replaces text matching).
- **Done when:** Grep at AC-CL.1 passes against this file.
- **Time:** 5 min

### Task E.5 — Migrate test_backfill.py fixtures
- **File:** `plugins/pd/hooks/lib/entity_registry/test_backfill.py:981, 992, 1037`
- **What:** Audit each test. If a test ONLY exercises the parser, delete it. If it has a meaningful DB-state assertion, refactor the fixture to use synthetic entities with explicit status= columns instead of free-text-marker description.
- **Done when:** All tests pass; AC-CL.x doesn't regress.
- **Time:** 12 min

### Task E.6 — Migrate test_entity_status.py fixtures
- **File:** `plugins/pd/hooks/lib/entity_registry/test_entity_status.py:385-1168`
- **What:** Same triage as E.5 — preserve fixtures using DB-state, delete parser-exercise-only tests.
- **Done when:** All tests pass.
- **Time:** 12 min

### Task E.7 — GREEN: Implement check_no_free_text_status_parsers
- **File:** `plugins/pd/hooks/lib/doctor/checks.py` (bottom)
- **What:** Per design IF-8: use PROJECT_ROOT env var → git rev-parse fallback; grep both files; return CheckResult per outcome. Match existing CheckResult shape.
- **Done when:** Function defined; importable; passes the smoke test in E.2.
- **Time:** 10 min

### Task E.8 — GREEN: Register check in doctor's CHECK_ORDER
- **File:** `plugins/pd/hooks/lib/doctor/__init__.py:11-27` (import block) + `:32` (CHECK_ORDER list)
- **What:** Add `from doctor.checks import check_no_free_text_status_parsers` to the import block. Append `check_no_free_text_status_parsers` to CHECK_ORDER after `check_status_write_path`.
- **Done when:** `/pd:doctor` or equivalent invocation runs the new check.
- **Time:** 4 min

### Task E.9 — Run full test suite
- **What:** `cd plugins/pd && .venv/bin/python -m pytest hooks/lib/entity_registry/ hooks/lib/doctor/ mcp/ -v 2>&1 | tail -30`
- **Done when:** No regressions; all AC-9.x + AC-10.x + AC-MR.x + AC-BL.x + AC-CL.x + AC-EX.x green.
- **Time:** 8 min

### Task E.10 — Commit Group E
- **What:** `git add backfill.py doctor/checks.py doctor/__init__.py test_backfill.py test_entity_status.py test_cleanup_suffix_parsers.py test_doctor.py; git commit -m "feat(111): Cleanup — remove free-text status parsers + new check_no_free_text_status_parsers doctor check"`
- **Done when:** Commit lands.
- **Time:** 3 min

**Group E total:** ~85 min.

---

## §X — Cross-Group Verification

### Task X.1 — Full feature-111 test scope smoke
- **What:** Run all 5 new test files plus extended ones:
  ```
  cd plugins/pd && .venv/bin/python -m pytest \
    hooks/lib/entity_registry/test_migration_14_safety.py \
    hooks/lib/entity_registry/test_status_only_lifecycle.py \
    hooks/lib/entity_registry/test_entity_lifecycle.py \
    hooks/lib/entity_registry/test_cleanup_suffix_parsers.py \
    hooks/lib/doctor/test_doctor.py \
    mcp/test_issue_spawn.py \
    mcp/test_complete_phase_closes.py \
    -v 2>&1 | tail -40
  ```
- **Done when:** All passing.
- **Time:** 5 min

### Task X.2 — Broader regression check
- **What:** `cd plugins/pd && .venv/bin/python -m pytest 2>&1 | tail -10` (full suite). Compare with pre-feature-111 baseline (Group A commit's parent).
- **Done when:** No new failures; numbers approximately matching pre-feature-111 baseline + new feature-111 tests.
- **Time:** 10 min

### Task X.3 — Doctor health check
- **What:** Run `/pd:doctor` or equivalent. Verify check_no_free_text_status_parsers appears and PASSES.
- **Done when:** Doctor output green.
- **Time:** 3 min

---

## Time Estimate Total

| Group | Time | Tasks |
|---|---|---|
| A | 80 min | 9 |
| B | 120 min | 17 |
| C | 60 min | 4 |
| D | 85 min | 5 |
| E | 85 min | 10 |
| X | 20 min | 3 |
| **Total** | **450 min (~7.5h)** | **48** |

With parallel execution of C/D/E after B merges: critical path ≈ A (80) + B (120) + max(C, D, E) (85) + X (20) = **~305 min**.
