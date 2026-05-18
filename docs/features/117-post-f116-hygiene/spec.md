# Spec: F117 — pd Post-F116 Production Hygiene

## Status

- Created: 2026-05-18
- Branch: `feature/117-post-f116-hygiene`
- Mode: standard (YOLO autonomous)
- PRD: `docs/features/117-post-f116-hygiene/prd.md` (Rev 2.2 — Approved by prd-reviewer 3 iter + brainstorm-reviewer Stage 6)

## Overview

F117 bundles 3 themes from the post-F116 audit (2026-05-18) into a single atomic landing:

- **Theme A** — Production bug fix: `_fix_triage_cross_workspace_link` re-attribute branches survive against trigger-active DB via `sqlite_master` capture/replay of `enforce_immutable_workspace_uuid` (a stricter variant of `claim_unknown_entities`'s pattern, which uses hardcoded trigger SQL — see FR-A.1 for the strengthening rationale).
- **Theme B** — Doctor version-pin debt: `db_readiness` + `memory_health` doctor checks use `max(MIGRATIONS.keys())`; 14 hardcoded test sweep sites (6 entity_registry + 8 semantic_memory) converted to dynamic references. Migration-safety pins (test_migration_13_safety.py:194/205/224 + sibling files) preserved.
- **Theme C** — State reconciliation: `reconcile_apply` flush + 4 brainstorm transitions + 21 cross-workspace link triage (operator-interactive).

Scope discipline (preserved from PRD): no new MCP tools, no new migrations, no new exception classes. Theme A's bug-fix adds bounded new code surface inside `_fix_triage_cross_workspace_link`.

## Functional Requirements

### Theme A — Cross-workspace re-attribute trigger drop/recreate

**FR-A.1: sqlite_master capture/replay wrapper**

The `_fix_triage_cross_workspace_link` function in `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py` (lines 488-561 — function body; the `UPDATE entities SET workspace_uuid = ?` statements live at lines 532-535 and 538-541) MUST replace each of the two re-attribute branches (`re-attribute parent` and `re-attribute child`) with the following sequence. The function currently operates on raw `ctx.entities_conn` (a `sqlite3.Connection` — verified at line 500, line 520, line 560), with a final explicit `ctx.entities_conn.commit()` at line 560. F117 adds connection-level rollback via `with ctx.entities_conn:` plus the trigger drop/recreate dance:

```python
# Implementation site: inside _fix_triage_cross_workspace_link, replacing the
# bare UPDATE inside `if choice == "re-attribute parent":` and
# `elif choice == "re-attribute child":` branches.
trigger_sql_row = ctx.entities_conn.execute(
    "SELECT sql FROM sqlite_master WHERE name='enforce_immutable_workspace_uuid'"
).fetchone()
if trigger_sql_row is None or not trigger_sql_row[0]:
    raise RuntimeError(
        "F117 FR-A.1: enforce_immutable_workspace_uuid trigger not found in "
        "sqlite_master; cannot safely drop/recreate. Aborting re-attribute."
    )
captured_sql = trigger_sql_row[0]

# `with sqlite3.Connection:` provides connection-level atomicity:
# auto-commit on clean exit, auto-rollback if any statement raises.
with ctx.entities_conn:
    ctx.entities_conn.execute(
        "DROP TRIGGER IF EXISTS enforce_immutable_workspace_uuid"
    )
    try:
        ctx.entities_conn.execute(
            "UPDATE entities SET workspace_uuid = ? WHERE uuid = ?",
            (target_workspace_uuid, target_entity_uuid),
        )
    finally:
        # Re-issue the captured trigger SQL byte-identical. This fires
        # even if the UPDATE raised — the connection-level rollback then
        # discards both the DROP and any partial UPDATE work, while the
        # trigger SQL is re-asserted at the DDL layer (DDL is implicitly
        # committed by sqlite3 on each execute, but DROP within a tx is
        # reverted by `with conn:` rollback per SQLite semantics).
        ctx.entities_conn.execute(captured_sql)
# The standalone `ctx.entities_conn.commit()` at line 560 (post-branch) is
# preserved for the other branches (delete relation, grandfather) — those
# do not need the trigger dance and use the legacy explicit commit.
```

Constraints:
- Trigger SQL MUST be captured BEFORE the `DROP TRIGGER`. If the SELECT returns no row (trigger absent), abort with `RuntimeError` — do NOT proceed with bare UPDATE.
- The `try/finally` MUST be structurally present so the recreate fires even on UPDATE exception.
- The recreate MUST use the captured SQL string (`ctx.entities_conn.execute(captured_sql)`), NOT a hand-written `CREATE TRIGGER ... BEGIN ... END` statement.
- The `with ctx.entities_conn:` block scopes the DROP + UPDATE + recreate into a single connection-level transaction. On clean exit the changes commit; on exception inside the block the connection rolls back the UPDATE.
- **Implementation note on timestamp:** the production function does not currently mutate `updated_at` on the re-attribute branches (verified at lines 532-541 — no `updated_at = ?` clause). F117 preserves this behavior; the UPDATE statement remains `UPDATE entities SET workspace_uuid = ? WHERE uuid = ?` (no timestamp mutation). If a future spec wants `updated_at` mutation here, it can use `datetime.now(timezone.utc).isoformat(timespec="microseconds")` inline — but that is out of F117 scope.
- This pattern strengthens the reference at `entity_registry/database.py:7956-7975` (`claim_unknown_entities`), which uses inline hardcoded `CREATE TRIGGER IF NOT EXISTS` SQL. The PRD frames this as a deliberate strengthening for byte-identity against future trigger SQL drift in `database.py`.

**FR-A.2: Atomicity invariant — trigger restoration + connection-level rollback**

A SQL exception during the `UPDATE` (between DROP and the `finally` block) MUST result in:
- The trigger being restored (via the `finally` block re-issuing `captured_sql`).
- The UPDATE statement itself either fully applies or fully fails (SQLite single-statement atomicity — guaranteed by the `UPDATE entities SET workspace_uuid = ? WHERE uuid = ?` being a single SQL statement; partial column writes are not possible).
- The `with ctx.entities_conn:` context manager rolls back any DML changes that occurred inside its block when an exception propagates out (sqlite3.Connection's documented context-manager semantics: on exception → `ROLLBACK`, on clean exit → `COMMIT`). This means a successful DROP + failed UPDATE leaves the workspace_uuid unchanged at the row level.

Verification (post-exception):
- `SELECT sql FROM sqlite_master WHERE name='enforce_immutable_workspace_uuid'` MUST return the captured text byte-identical.
- `SELECT workspace_uuid FROM entities WHERE uuid=?` MUST return the pre-exception value (proves rollback semantics).
- A fresh subsequent bare `UPDATE entities SET workspace_uuid = ? WHERE uuid = ?` against the same row MUST raise `sqlite3.IntegrityError` whose message contains the substring `"workspace_uuid is immutable"` (proves the recreated trigger is enforcing).

**FR-A.3: Regression test against trigger-active DB**

A new test `test_re_attribute_against_trigger_active_db` MUST be added to `plugins/pd/hooks/lib/doctor/test_fix_actions.py`. Constraints:

- The test fixture MUST NOT drop the `enforce_immutable_workspace_uuid` trigger in setup (this inverts F116 TC.4's fixture polarity, which masked the production bug).
- The test MUST exercise both `re-attribute parent` and `re-attribute child` branches.
- The test MUST assert that post-call: (a) the workspace_uuid changed as expected, (b) `SELECT sql FROM sqlite_master WHERE name='enforce_immutable_workspace_uuid'` returns the snapshotted SQL verbatim (byte-identical to pre-call query), (c) the trigger still enforces immutability after the call (sanity check: a fresh bare `UPDATE entities SET workspace_uuid = ? WHERE uuid = ?` against any non-target row MUST raise `sqlite3.IntegrityError` whose message contains the substring `"workspace_uuid is immutable"` — substring match per canonical message at `entity_registry/database.py:2045`).

**FR-A.4: Trigger-restored mid-UPDATE failure test**

A new test `test_re_attribute_restores_trigger_on_update_failure` MUST be added. Constraints:

- Fixture: trigger active. Failure-injection mechanism: pass an entity_uuid that does not exist in `workspaces.uuid` (the entities table's `workspace_uuid` column is `TEXT NOT NULL REFERENCES workspaces(uuid)` per `database.py:1984`). With `PRAGMA foreign_keys = ON` enabled on the connection (verify in the test fixture; if not enabled, the fixture MUST enable it via `conn.execute("PRAGMA foreign_keys = ON")` before the test), the UPDATE raises `sqlite3.IntegrityError: FOREIGN KEY constraint failed`.
- Pre-flight verification: before fixing the implementation, the test author MUST manually verify that `conn.execute("PRAGMA foreign_keys=ON; UPDATE entities SET workspace_uuid='nonexistent-uuid' WHERE uuid=?", (...,))` against a trigger-dropped fixture raises `sqlite3.IntegrityError` with `"FOREIGN KEY constraint failed"` in the message. If `PRAGMA foreign_keys` is OFF by default in the project's connection wrapper, the test fixture MUST explicitly enable it. (Fallback if FK enforcement is impractical: use `pytest.MonkeyPatch.setattr` on `ctx.entities_conn.execute` to raise `sqlite3.OperationalError("simulated failure")` on the second call (the UPDATE), keeping the first call (DROP TRIGGER) intact. Document the chosen mechanism in the test docstring.)
- Assertion: after the exception propagates from `_fix_triage_cross_workspace_link` to the test, (a) `SELECT sql FROM sqlite_master WHERE name='enforce_immutable_workspace_uuid'` returns the captured text byte-identical (the `finally` re-issued it), (b) the original `workspace_uuid` on the target entity is unchanged (the `with ctx.entities_conn:` rollback discarded the UPDATE — `SELECT workspace_uuid FROM entities WHERE uuid=?` returns the pre-call value), (c) the raised exception is the original mechanism's type (`sqlite3.IntegrityError` for FK injection, `sqlite3.OperationalError` for monkey-patched), NOT a wrapped exception — the function does not swallow.

**FR-A.5: F116 TC.4 test compatibility (modified fixture flow)**

The existing F116 TC.4 re-attribute tests in `test_fix_actions.py` would break under FR-A.1 as written: their `_seed_cross_workspace_pair` helper (at `test_fix_actions.py:78-89`) drops the `enforce_immutable_workspace_uuid` trigger before INSERTing cross-workspace rows (the trigger would otherwise block setup). After fixture exit, the trigger is gone, so FR-A.1's `SELECT sql FROM sqlite_master ...` returns None → `RuntimeError` (FR-A.6). F117 makes the fixture explicit about timing:

**Resolution path (ordered):**
1. `_seed_cross_workspace_pair` continues to DROP TRIGGER as its first step (preserve existing seeding semantics — the trigger would block the INSERTs).
2. After the helper completes its INSERTs but BEFORE the test invokes `_fix_triage_cross_workspace_link`, the test (or a new helper `_recreate_workspace_uuid_trigger(conn)`) MUST execute the canonical trigger SQL to re-arm the constraint:
   ```python
   conn.execute("""
       CREATE TRIGGER enforce_immutable_workspace_uuid
       BEFORE UPDATE OF workspace_uuid ON entities
       BEGIN SELECT RAISE(ABORT,
           'workspace_uuid is immutable — use re-attribution API'
       ); END
   """)
   ```
3. The test then invokes `_fix_triage_cross_workspace_link`; FR-A.1's capture/replay finds the just-created trigger, drops it, runs UPDATE, recreates from captured SQL.
4. Post-call assertions per FR-A.3.

**Trigger SQL canonicality:** the literal SQL above MUST match `entity_registry/database.py:2043-2046` (the canonical CREATE TRIGGER source). If `database.py`'s trigger definition changes in a future feature, the test helper's CREATE TRIGGER MUST be updated to match — this coupling is intentional: it forces test/source synchronization. (Alternative: import the trigger SQL from a single source via a new module-level constant in `database.py`; F117 does not pursue this — flagged as F117 retro KB candidate alongside the `claim_unknown_entities` backport.)

**No behavior change to F116 TC.4 assertions:** The original assertions (re-attribute succeeds, child/parent workspace_uuid updated) still hold; only the fixture is augmented with the re-create step.

**FR-A.6: Trigger absence safeguard**

If `_fix_triage_cross_workspace_link` is invoked against a DB where the `enforce_immutable_workspace_uuid` trigger has been intentionally removed (e.g., during a migration in progress), the captured-SQL SELECT returns no row, and the function MUST raise `RuntimeError` with message: `"F117 FR-A.1: enforce_immutable_workspace_uuid trigger not found in sqlite_master; cannot safely drop/recreate. Aborting re-attribute."` (see FR-A.1 code block). This prevents the function from silently degrading into a bare-UPDATE path against future schema states.

### Theme B — Dynamic doctor version constants + test sweep

**FR-B.1: Dynamic version constants in doctor checks**

The `plugins/pd/hooks/lib/doctor/checks.py` file MUST replace its hardcoded version constants (`ENTITY_SCHEMA_VERSION = 11` and `MEMORY_SCHEMA_VERSION = 4`, lines 14-15) with dynamic imports computed at check-time:

- `db_readiness` check MUST compute its expected version via:
  ```python
  def _get_expected_entity_version() -> int:
      # Lazy import to avoid module-load circular risk
      from entity_registry.database import MIGRATIONS as ENTITY_MIGRATIONS
      return max(ENTITY_MIGRATIONS.keys())
  ```
- `memory_health` check MUST do the same for `semantic_memory.database.MIGRATIONS`:
  ```python
  def _get_expected_memory_version() -> int:
      from semantic_memory.database import MIGRATIONS as MEMORY_MIGRATIONS
      return max(MEMORY_MIGRATIONS.keys())
  ```
- The lazy import pattern (inside the check function body, not module-level) prevents potential circular-import risk between `doctor` and `entity_registry` / `semantic_memory`.
- The hardcoded `ENTITY_SCHEMA_VERSION` and `MEMORY_SCHEMA_VERSION` module-level constants MUST be removed entirely (not just unused — actively deleted to prevent future re-introduction).

**FR-B.2a: Test sweep — current-version assertions (entity_registry)**

The following 6 sites in `plugins/pd/hooks/lib/entity_registry/test_database.py` MUST be converted from hardcoded version literals to dynamic references via a fixture or module-level helper:

| Line | Current form | Target form |
|------|--------------|-------------|
| 370 | `assert db.get_metadata("schema_version") == "17"` | `assert db.get_metadata("schema_version") == str(_latest_entity_version())` |
| 678 | `assert db.get_metadata("schema_version") == "17"` | (same) |
| 2688 | `assert db2.get_metadata("schema_version") == "17"` | (same) |
| 2890 | `assert db.get_metadata("schema_version") == "17"` | (same) |
| 3081 | `assert fresh_db.get_metadata("schema_version") == "17"` | (same) |
| 4673 | `assert db.get_schema_version() == 17` | `assert db.get_schema_version() == _latest_entity_version()` (int form) |

A module-level helper MUST be added near the top of `test_database.py`:
```python
def _latest_entity_version() -> int:
    from entity_registry.database import MIGRATIONS
    return max(MIGRATIONS.keys())
```

**FR-B.2a (continued): Test sweep — current-version assertions (semantic_memory)**

The following 8 sites in `plugins/pd/hooks/lib/semantic_memory/test_database.py` MUST be converted similarly. The same helper pattern applies:
```python
def _latest_memory_version() -> int:
    from semantic_memory.database import MIGRATIONS
    return max(MIGRATIONS.keys())
```

Sites: lines 91, 116, 123, 127, 191, 1266, 1306, 1310 (all of the form `assert dbN.get_schema_version() == 7` → `== _latest_memory_version()`).

**FR-B.2b: Preserve migration-safety pinned sites (NO sweep)**

Empirical enumeration (verified 2026-05-18 via grep `schema_version.*== *"\|MIGRATION_SAFETY`):

1. `plugins/pd/hooks/lib/entity_registry/test_migration_13_safety.py` — 3 pinned sites:
   - Line 194: `assert v is not None and v[0] == "13"` (replay-drift check)
   - Line 205: `assert v is not None and v[0] == "13"` (post-migration stamp)
   - Line 224: `assert stamp_idx >= 0, "migration 13 must stamp schema_version=13"` (static source check)
2. `plugins/pd/hooks/lib/entity_registry/test_migration_14_safety.py` — **0 hardcoded `== "N"` assertion-form sites** (verified via grep). No FR-B.2b exclusion required for this file; FR-B.2a sweep does not touch it either.
3. `plugins/pd/hooks/lib/entity_registry/test_migration_safety.py` — **0 hardcoded `== "N"` assertion-form sites** (verified via grep). Same status as #2.
4. `plugins/pd/hooks/lib/semantic_memory/test_database.py:2857`: `assert _read_schema_version(db_path) == "5"` — post-migration backstop assertion. Pins explicitly to "5". MUST remain hardcoded.
5. `plugins/pd/hooks/lib/semantic_memory/test_database.py:2876, 2883, 2897, 2901, 2955, 2970, 2986, 2993`: these compare `_read_schema_version(db_path) == pre_version` (relative comparison, not a literal pin). FR-B.2a's sweep regex `_read_schema_version\(...\)\s*==\s*"\d+"` does NOT match this form; they are safe by exclusion.

**Verification commands (run post-sweep):**
- `grep -nE '_latest_entity_version|_latest_memory_version' plugins/pd/hooks/lib/entity_registry/test_migration_13_safety.py` → expect 0 matches.
- `grep -nE '_latest_memory_version' plugins/pd/hooks/lib/semantic_memory/test_database.py | grep -E ':(2857)'` → expect 0 matches (line 2857 not converted).

**FR-B.2c: Excluded patterns (false positives)**

The following sites MUST NOT be swept (they reference `EXPORT_SCHEMA_VERSION`, an independent versioning system for the export-format JSON, NOT the entity DB schema):
- `plugins/pd/hooks/lib/entity_registry/test_database.py:4077-4081`: `result["schema_version"] == 1` (export schema)
- `plugins/pd/hooks/lib/entity_registry/test_database.py:4524`: `result["schema_version"] == 1` (export schema)

Spec phase note: the sweep regex MUST be `get_metadata\("schema_version"\)\s*==\s*"\d+"` and `get_schema_version\(\)\s*==\s*\d+` to avoid these false positives. A naive `schema_version\s*==\s*\d+` regex would catch them and corrupt the export-format tests.

**Verification command (run pre-sweep):** `grep -nE 'get_metadata\("schema_version"\)\s*==\s*"\d+"|get_schema_version\(\)\s*==\s*\d+' plugins/pd/hooks/lib/entity_registry/test_database.py` MUST output exactly the 6 sites enumerated in FR-B.2a (lines 370, 678, 2688, 2890, 3081, 4673) — and MUST NOT output lines 4077-4081, 4524. If the grep output differs from this expected list, the sweep regex is mis-specified; abort and re-verify.

**FR-B.3: Verify zero hardcoded CHECK_ORDER counts**

`grep -rn 'len(CHECK_ORDER)\s*==\s*[0-9]\+' plugins/pd` MUST return 0 matches (already true at session start 2026-05-18; F117 verifies post-sweep that no new such pattern was introduced).

`len(report.checks) == 20` assertions in `plugins/pd/hooks/lib/doctor/test_checks.py` (10 sites, F116-introduced) remain unchanged in F117 — they are within scope of the F116 sweep and are correct for the current 20-check count. Out of F117 scope; flagged for potential future dynamic conversion via a separate `_check_count()` helper if a 21st check is added.

**FR-B.4: AST check forward-compat**

F115's `check_audit_counter_write_path` AST check MUST continue passing — its source-code-level assertions are not affected by schema version migration.

**FR-B.5: validate.sh / full pytest regression gate**

After the FR-B sweep is complete, the following commands MUST run with 0 regressions:
- `./validate.sh` — 0 errors.
- `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ plugins/pd/hooks/lib/semantic_memory/ plugins/pd/hooks/lib/doctor/` — all currently-passing tests still pass.

### Theme C — State reconciliation

**FR-C.1: Reconcile dry-run capture**

`reconcile_check` MUST be invoked via MCP before any apply, and its output captured to `docs/features/117-post-f116-hygiene/reconcile-dry-run.json` for retro reference. The dry-run output MUST be reviewed (visually or via diff) before apply.

**FR-C.2: Reconcile apply**

`reconcile_apply` MUST be invoked via MCP. Post-apply doctor count MUST show a reduction of ≥ 261 in the `feature_status` + `workflow_phase` warning counts (pre-apply: 132 + 129 = 261; post-apply: target < 5 in each category).

**FR-C.3: Brainstorm status transitions**

The following 4 stuck-active brainstorms MUST be transitioned to `status='promoted'` via `update_entity` MCP calls (one per brainstorm):

| Brainstorm `entity_id` | Parent feature |
|-----------------------|----------------|
| `20260516-210137-pd-followups` | F115 |
| `20260516-184258-pd-data-model-hardening` | F114 |
| `20260517-053927-f115-qa-deferred` | F116 |
| `20260327-050000-phase-transition-summary` | (older, no direct parent) |

Verification: post-call, `sqlite3 ~/.claude/pd/entities/entities.db "SELECT entity_id, status FROM entities WHERE kind='brainstorm' AND status='active'"` MUST return 0 rows.

**FR-C.4: Cross-workspace link triage (operator-interactive)**

The 21 cross-workspace `parent_uuid` links flagged by doctor MUST be triaged via `_fix_triage_cross_workspace_link` invocations (one per link). Constraints:

- This step REQUIRES operator interactive judgment per link (which workspace is correct? grandfather?).
- YOLO break is explicitly authorized per the PRD's YOLO Mode Exceptions section.
- Post-triage invariant: `remaining_cross_workspace_count == new_allowlist_row_count` — i.e., the only cross-workspace links remaining are those explicitly grandfathered with allowlist entries.

If the operator is unavailable or pauses (e.g., interactive prompt times out, user requests break), the implement phase MAY skip the triage loop and complete F117 with FR-C.4 marked deferred. The 21 links would remain as warnings until a follow-up session re-invokes the triage tool.

**FR-C.5: Post-fix doctor sanity check**

After Themes A/B/C complete, `python -m doctor` MUST return:
- 0 errors (Theme B eliminates the 2 stale-version "errors").
- Doctor total issue reduction ≥ 280 from the pre-F117 baseline of 537.
- `severity_summary` field present in the JSON output (F116 invariant preserved).

## Non-Functional Requirements

- **NFR-1 (test runner):** All tests run under `plugins/pd/.venv/bin/python -m pytest`.
- **NFR-2 (validate.sh):** 0 errors after F117.
- **NFR-3 (Theme A test budget):** ~3-7 new tests focused on regression coverage: trigger-active re-attribute success (FR-A.3), mid-UPDATE rollback safety (FR-A.4), trigger-absent safeguard (FR-A.6), optional concurrent-writer behavior.
- **NFR-4 (no new config):** No new config keys.
- **NFR-5 (check count invariant):** Doctor check count remains 20 (F116 added the 20th; F117 does not add or remove). FR-B.3 verifies.
- **NFR-6 (no new MCP tools / migrations / exception classes):** Theme A/B/C use existing infrastructure only.
- **NFR-7 (compress reviewer iterations):** Target 1-2 reviewer iterations per phase per F114/F115/F116 strategy. Reviewer notes documented in `.review-history.md`.

## Acceptance Criteria

### AC-A: Theme A (Production bug fix)

- **AC-A.1:** `_fix_triage_cross_workspace_link` re-attribute branches succeed against a fixture with `enforce_immutable_workspace_uuid` trigger active.
- **AC-A.2:** Post-call sqlite_master trigger SQL is byte-identical to pre-call.
- **AC-A.3:** Mid-UPDATE exception → trigger restored AND original workspace_uuid unchanged.
- **AC-A.4:** Trigger absent at call time → `RuntimeError` with canonical message (FR-A.1).
- **AC-A.5:** F116 TC.4 tests continue passing (with fixture-drop scope adjusted per FR-A.5).

### AC-B: Theme B (Dynamic version pinning + sweep)

- **AC-B.1:** `db_readiness` doctor check emits OK (no error) when entity DB schema matches `max(MIGRATIONS.keys())`.
- **AC-B.2:** `memory_health` doctor check emits OK when memory DB schema matches `max(MIGRATIONS.keys())`.
- **AC-B.3:** All 14 current-version sweep sites (6 entity_registry + 8 semantic_memory) use dynamic helpers per FR-B.2a.
- **AC-B.4:** Migration-safety pinned sites (FR-B.2b) remain hardcoded; grep verification returns 0 dynamic-helper matches in those files.
- **AC-B.5:** Excluded EXPORT_SCHEMA_VERSION sites (FR-B.2c) untouched.
- **AC-B.6:** Hardcoded `ENTITY_SCHEMA_VERSION` and `MEMORY_SCHEMA_VERSION` constants removed from `checks.py:14-15`.
- **AC-B.7:** `./validate.sh` 0 errors; `pytest plugins/pd/hooks/lib/{entity_registry,semantic_memory,doctor}/` 0 new failures.

### AC-C: Theme C (Reconciliation)

- **AC-C.1:** `reconcile_check` dry-run output captured to `docs/features/117-post-f116-hygiene/reconcile-dry-run.json`.
- **AC-C.2:** `reconcile_apply` invoked; post-apply doctor `feature_status` + `workflow_phase` counts < 5 each (down from 132 + 129).
- **AC-C.3:** 4 stuck-active brainstorms → `status='promoted'`; verification query returns 0 active rows.
- **AC-C.4:** 21 cross-workspace links triaged (operator-interactive); post-triage invariant `remaining_cross_workspace_count == new_allowlist_row_count`. Deferral acceptable per FR-C.4.
- **AC-C.5:** Post-F117 doctor: 0 errors. Total issue reduction:
    - **IF FR-C.4 triage completed**: reduction ≥ 280 from baseline of 537 (= 261 reconcile + 21 triage − slack for auto-resolved orphans that share root cause with phase drift).
    - **IF FR-C.4 triage deferred** (operator unavailable per FR-C.4): reduction ≥ 259 from baseline of 537 (= 280 target − 21 unhandled cross-workspace warnings). The deferral case MUST be documented in `retro.md` with explicit follow-up scheduling.

### AC-D: Cross-cutting

- **AC-D.1:** F115 + F116 regression suite passes (0 new test failures attributable to F117).
- **AC-D.2:** Merge target: `develop` branch (NOT main, per user memory `merge-to-develop-not-main`).
- **AC-D.3:** `.meta.json` `lastCompletedPhase` advances through specify → design → create-plan → implement → finish.

## Test Strategy

### Theme A — New tests

| Test name | File | Scenario |
|-----------|------|----------|
| `test_re_attribute_against_trigger_active_db` | `test_fix_actions.py` | Fixture keeps trigger active; both re-attribute branches succeed; trigger SQL byte-identical post-call. |
| `test_re_attribute_restores_trigger_on_update_failure` | `test_fix_actions.py` | Mid-UPDATE exception; trigger restored; original workspace_uuid unchanged; original exception type re-raised. |
| `test_re_attribute_aborts_when_trigger_absent` | `test_fix_actions.py` | Pre-drop the trigger before call; expect `RuntimeError` with canonical message (FR-A.6). |
| `test_re_attribute_post_call_trigger_enforces_immutability` | `test_fix_actions.py` | After successful re-attribute, a bare `UPDATE entities SET workspace_uuid = ?` raises `sqlite3.IntegrityError` with the immutability message. |

### Theme B — Modified tests (mechanical sweep)

14 sites converted to dynamic helpers (FR-B.2a). No new test functions; existing tests' assertion form changes only. Helper functions `_latest_entity_version()` and `_latest_memory_version()` added near the top of the two test_database.py files.

### Theme C — Operational tests (not pytest)

| Step | Verification |
|------|--------------|
| FR-C.1 dry-run | File `reconcile-dry-run.json` exists; valid JSON; contains expected counts. |
| FR-C.2 apply | Pre/post doctor diff: `feature_status` + `workflow_phase` reduced by ≥ 261. |
| FR-C.3 brainstorms | Post-update SQL query: 0 active brainstorm rows. |
| FR-C.4 triage | Post-triage doctor: cross_workspace_parent_uuid count == new allowlist row count. |
| FR-C.5 final | Doctor JSON: 0 errors; total issues reduced ≥ 280. |

## Out of Scope

- Investigating 250 `entity_orphans` warnings (most expected to auto-resolve via FR-C.2 reconcile; remainder deferred to F118 candidate).
- Closing 20 open F088/F089 backlog items (all LOW; separate hygiene pass).
- Addressing 17 F116 MED test-deepener findings (separate coverage feature; F118 candidate per F116 retro Tune #5).
- Releasing v4.18.3 (release script triggered manually after F117 lands on develop, matching F116 pattern).
- Changing M15 INSERT-OR-REPLACE semantics (F116 documented this; out of scope).
- Backporting FR-A.1's sqlite_master capture/replay pattern to `claim_unknown_entities` (flagged for F117 retro KB; not in F117 scope).
- Converting `len(report.checks) == 20` assertions in `test_checks.py` (F116-era; correct for current count; future hygiene if a 21st check is added).

## Open Questions

*(None — all resolved during PRD review.)*

## Implementation Phase Coordination Notes

For the create-plan phase, anticipate the following TDD ordering:

1. **TA.1** (Theme A red): Write `test_re_attribute_against_trigger_active_db` first — verify it fails against current code (production bug reproduced in test).
2. **TA.2** (Theme A green): Apply FR-A.1 sqlite_master capture/replay wrapper in `fix_actions/__init__.py`.
3. **TA.3** (Theme A green): Write FR-A.4, FR-A.6 tests; verify they pass with the new logic.
4. **TA.4** (Theme A green): Adjust F116 TC.4 fixture per FR-A.5; verify TC.4 tests still pass.
5. **TB.1** (Theme B): Apply FR-B.1 dynamic constants in `checks.py`; verify doctor errors clear locally.
6. **TB.2** (Theme B): Apply FR-B.2a sweep to entity_registry/test_database.py (6 sites).
7. **TB.3** (Theme B): Apply FR-B.2a sweep to semantic_memory/test_database.py (8 sites).
8. **TB.4** (Theme B): Run full pytest regression; verify 0 failures.
9. **TC.1** (Theme C): `reconcile_check` dry-run; capture to `reconcile-dry-run.json`.
10. **TC.2** (Theme C): `reconcile_apply`; verify count reduction.
11. **TC.3** (Theme C): 4 `update_entity` calls for brainstorm transitions.
12. **TC.4** (Theme C): Interactive triage loop for 21 cross-workspace links (operator break).
13. **TC.5** (Theme C): Final doctor sanity check; capture to retro.

## Review History

### Spec-Reviewer Iteration 1 (2026-05-18)

**Result:** Not approved. 2 blockers + 4 warnings + 3 suggestions.

**Findings (resolved in rev 2):**

| # | Severity | Issue | Resolution |
|---|----------|-------|------------|
| 1 | blocker | FR-A.2 claimed atomicity via "outer `with self.transaction():` rolls back" but production `_fix_triage_cross_workspace_link` uses raw `ctx.entities_conn` + explicit `commit()` at line 560; no such wrapper exists | FR-A.1 rewritten to add explicit `with ctx.entities_conn:` context manager wrapping the DROP/UPDATE/recreate sequence (sqlite3.Connection auto-rollback semantics). FR-A.2 rewritten to scope atomicity precisely (single-statement UPDATE atomicity + connection-level rollback + trigger restore via `finally`). |
| 2 | blocker | FR-A.4 prescribed 3 alternative failure-injection mechanisms (monkey-patch, CHECK constraint, FK violation) without verifying any would actually fire mid-UPDATE | FR-A.4 rewritten with primary FK-injection mechanism (entities.workspace_uuid is `TEXT NOT NULL REFERENCES workspaces(uuid)` at database.py:1984; with `PRAGMA foreign_keys=ON`, passing a nonexistent workspace UUID raises sqlite3.IntegrityError). Fallback monkey-patch documented for when FK enforcement is impractical. Pre-flight verification step required. |
| 3 | warning | FR-A.5 TC.4 fixture re-creation ordering ambiguous (could be misread as re-create-before-INSERTs, which would break seed) | FR-A.5 rewritten with explicit 4-step ordering: seed-drops-trigger (preserved) → seed-INSERTs → fixture-re-creates-trigger → test-invokes-fix. Canonical CREATE TRIGGER SQL embedded inline with reference to `database.py:2043-2046`. |
| 4 | warning | AC-C.5 reduction target ≥ 280 unachievable if FR-C.4 triage deferred | AC-C.5 rewritten with conditional acceptance: ≥ 280 if triage completed, ≥ 259 if triage deferred (= 280 − 21 unhandled cross-workspace warnings). Deferral case requires retro documentation. |
| 5 | warning | FR-A.3 didn't quote literal trigger error message — risk of test mismatch | FR-A.3 acceptance criterion (c) rewritten to assert substring `"workspace_uuid is immutable"` (substring match per canonical message at database.py:2045). FR-A.2 verification reuses same form. |
| 6 | warning | FR-B.2c regex spec correct but not falsifiable by example | FR-B.2c augmented with explicit `grep -nE` verification command + expected output (6 specific line numbers); abort path documented if mismatch. |
| 7 | suggestion | FR-B.2b sibling files (test_migration_14_safety.py, test_migration_safety.py) said "deferred to spec phase" — spec phase IS this phase | FR-B.2b enumerated empirically: both sibling files have 0 hardcoded `== "N"` assertion-form sites (verified via grep). No exclusions needed; documented as such. |
| 8 | suggestion | FR-A.1 pseudocode used unbound `now_iso` variable — `ctx` does not provide a `_now_iso()` method | FR-A.1 implementation note added: production `_fix_triage_cross_workspace_link` does not mutate `updated_at` on re-attribute branches (verified at lines 532-541). F117 preserves this — UPDATE statement remains `SET workspace_uuid = ?` only, no timestamp clause. Pseudocode updated accordingly. |
| 9 | suggestion | Overview section did not propagate the "stricter variant" framing from PRD rev 2.1 | Overview Theme A bullet expanded with the strengthening rationale (stricter variant of `claim_unknown_entities`'s hardcoded pattern). |

**Rev 2 summary:** All 2 blockers resolved with concrete implementation-ready specifications; 4 warnings resolved with explicit ordering / quoting / falsifiable verification commands; 3 suggestions absorbed into spec body (no separate addendum needed).

## Evidence + Reference Trail

| Pin | Source |
|-----|--------|
| Production bug location | `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py:472-482` |
| Reference pattern (inline) | `plugins/pd/hooks/lib/entity_registry/database.py:7956-7975` |
| Trigger definition source | `plugins/pd/hooks/lib/entity_registry/database.py:2043` (CREATE TRIGGER enforce_immutable_workspace_uuid) |
| Doctor stale constants | `plugins/pd/hooks/lib/doctor/checks.py:14-15` |
| 6 entity_registry sweep sites | `plugins/pd/hooks/lib/entity_registry/test_database.py:370, 678, 2688, 2890, 3081, 4673` |
| 8 semantic_memory sweep sites | `plugins/pd/hooks/lib/semantic_memory/test_database.py:91, 116, 123, 127, 191, 1266, 1306, 1310` |
| Migration-safety pins (preserve) | `plugins/pd/hooks/lib/entity_registry/test_migration_13_safety.py:194, 205, 224` + sibling files |
| Excluded false positives | `plugins/pd/hooks/lib/entity_registry/test_database.py:4077-4081, 4524` (EXPORT_SCHEMA_VERSION) |
| 4 brainstorms (queried) | `~/.claude/pd/entities/entities.db` `SELECT entity_id FROM entities WHERE kind='brainstorm' AND status='active'` |
| Doctor baseline | 537 issues (2 error / 534 warning / 1 info) — pre-F117 session start |
