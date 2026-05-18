# F117 Implementation Log

## Phase A — Theme A (Production trigger drop/recreate)

### TA.1 — `_CANONICAL_TRIGGER_SQL` + `_recreate_workspace_uuid_trigger`
- **File:** `plugins/pd/hooks/lib/doctor/test_fix_actions.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - Constant + helper added near top of file (lines 35-58).
  - Em-dash U+2014 confirmed via `grep -n "—"` at line 43 (canonical SQL body).

### TA.2 — `test_re_attribute_against_trigger_active_db` (TDD red)
- **File:** `plugins/pd/hooks/lib/doctor/test_fix_actions.py`
- **Status:** ✅ COMPLETE (red → green confirmed)
- **DoD verified:**
  - Parametrized test added (re-attribute parent + re-attribute child variants).
  - Red phase: `sqlite3.IntegrityError: workspace_uuid is immutable` raised at `fix_actions/__init__.py:532` — production bug reproduced.
  - Green phase: post-TA.3, both variants pass.

### TA.3 — `_execute_re_attribute_with_trigger_dance` helper + UPDATE replacements
- **File:** `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - Helper added with R-2 docstring note (CPython sqlite3 legacy autocommit assumption per design TD-A.1).
  - 2 bare UPDATE blocks replaced with helper calls (parent + child branches).
  - `grep -cE '^def _execute_re_attribute_with_trigger_dance' → 1`; `grep -cE '_execute_re_attribute_with_trigger_dance\(' → 3` (1 def + 2 call sites).
  - TA.2 test now PASSES (TDD green confirmed).

### TA.4 — FR-A.4 + FR-A.6 + R-1 tests
- **File:** `plugins/pd/hooks/lib/doctor/test_fix_actions.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - 3 new tests added: `test_re_attribute_aborts_when_trigger_absent` (FR-A.6), `test_re_attribute_restores_trigger_on_update_failure` (FR-A.4 via `_FailingUpdateConn` proxy with explicit `__enter__`/`__exit__`), `test_canonical_trigger_sql_matches_production_source` (R-1 drift detector).
  - All 3 pass.

### TA.5 — Re-arm trigger in 4 existing TC.4 sites
- **File:** `plugins/pd/hooks/lib/doctor/test_fix_actions.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - `_recreate_workspace_uuid_trigger()` call added after `_seed_cross_workspace_pair()` in 4 sites (`test_t2a_7_triage_branch`, `test_t2a_7_triage_grandfather_without_reason_uses_fallback`, `test_t2a_7_triage_unknown_choice_raises_value_error`, `test_fr9_legitimate_grandfather_with_reason_preserves_behavior`).
  - Full `test_fix_actions.py` test suite: 21 passed (15 F116 + 6 new F117).

## Phase B — Theme B (Dynamic version pinning + test sweep)

### TB.1 — `_get_expected_*_version` helpers in `checks.py`
- **File:** `plugins/pd/hooks/lib/doctor/checks.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - Hardcoded constants `ENTITY_SCHEMA_VERSION = 11` / `MEMORY_SCHEMA_VERSION = 4` removed.
  - Lazy-import helpers added (returns `max(MIGRATIONS.keys())`).
  - Smoke test via `cd plugins/pd && PYTHONPATH=hooks/lib .venv/bin/python -c "..."` prints `17 7`.

### TB.2 — Update `db_readiness` + `memory_health` to use helpers
- **File:** `plugins/pd/hooks/lib/doctor/checks.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - `check_db_readiness` calls `_get_expected_entity_version()`.
  - `check_memory_health` calls `_get_expected_memory_version()`.
  - Doctor stale-version errors: 2 → 0 (production bug fix confirmed).

### TB.3 — Sweep 6 entity_registry test_database.py sites
- **File:** `plugins/pd/hooks/lib/entity_registry/test_database.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - Helper `_latest_entity_version()` added.
  - 6 sites converted (lines 370, 678, 2688, 2890, 3081, 4673).
  - EXPORT_SCHEMA_VERSION sites at lines 4077-4081, 4524 preserved (out of sweep regex scope).
  - `grep -nE 'get_metadata\("schema_version"\)\s*==\s*"\d+"|get_schema_version\(\)\s*==\s*\d+' → 0 matches`.

### TB.4 — Sweep 8 semantic_memory test_database.py sites
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - Helper `_latest_memory_version()` added.
  - 8 sites converted (lines 91, 116, 123, 127, 191, 1266, 1306, 1310).
  - Migration-safety pin at line 2863 (`_read_schema_version(db_path) == "5"`) preserved.

### TB.5 — Full pytest + validate.sh regression
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - `pytest plugins/pd/hooks/lib/{doctor,entity_registry,semantic_memory}/` (from project root): **2166 passed, 3 skipped, 0 failures**.
  - `./validate.sh`: **0 errors, 5 warnings** (matches F116 baseline).
  - FR-B.3 forward-compat: `grep -rn 'len(CHECK_ORDER)\s*==\s*[0-9]\+' plugins/pd → 0 matches`.
  - **Pre-existing test_checks.py brittleness resolved (leave-the-ground-tidier):** 2 fixtures hardcoded `schema_version='11'` and the `_make_memory_db` helper hardcoded `'4'`. Updated to use dynamic `_get_expected_*_version()` helpers (F117-attributable since F117 changed the expected versions).

## Phase C — Theme C (State reconciliation)

### TC.1 — `reconcile_check` dry-run
- **File:** `docs/features/117-post-f116-hygiene/reconcile-dry-run.json`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - JSON captured (3950 lines).
  - `jq` valid; summary: 3 in_sync, 3 meta_json_only (F114/F115/F116/F117 pending), 197 db_only (cross-workspace from other projects — correctly NOT reconciled), 1 phase_events_drift.

### TC.2 — `reconcile_apply`
- **Status:** ✅ COMPLETE (after entity registration repair)
- **DoD verified:**
  - First `reconcile_apply` returned 3 errors (Entity not found) — F114/F115/F116 records didn't exist in DB.
  - Manually registered F114, F115, F116 entities via `register_entity` MCP (`status='completed'`).
  - Second `reconcile_apply` succeeded: 3 created, 200 skipped (cross-workspace), 0 errors.
- **Key finding (retro-worthy):** The 132 `feature_status` + 129 `workflow_phase` doctor warnings are cross-workspace pollution from other projects' entities in the shared `~/.claude/pd/entities/entities.db`. They are NOT pedantic-drip drift and CANNOT be reconciled via `reconcile_apply` (which correctly leaves cross-workspace entities alone). The PRD/spec's "≥261 reduction from reconcile" assumption was based on an incomplete understanding of what reconcile addresses.

### TC.3 — 4 brainstorm transitions
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - 4 `update_entity` calls succeeded (F114, F115, F116, older phase-transition-summary brainstorms → `status='promoted'`).
  - Post-call SQL query: 2 active brainstorms remaining (`three-claws-v2-protocol`, `openclaw-gap-analysis`) — both cross-project, out of F117 scope.

### TC.4 — 21-link cross-workspace triage
- **Status:** ⏸️ DEFERRED per FR-C.4 deferral path
- **Rationale:**
  - 21 cross-workspace `parent_uuid` links require operator-interactive judgment per link (re-attribute parent / re-attribute child / delete relation / grandfather).
  - In autonomous YOLO session, deferring is appropriate.
  - AC-C.5 IF-deferred branch applies: reduction target ≥ 259 instead of ≥ 280.
- **Deferred artifact:** see `## Deferred Triage Links` section below + retro.md (to be created in /pd:finish-feature).

### TC.5 — Final doctor sanity check
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - 0 errors ✓ (F117-attributable: 2 stale-version errors eliminated).
  - `severity_summary` field present: `{error: 0, warning: 537, info: 1}` (F116 invariant preserved).
  - Total issues: 538 vs baseline 537 = +1 (F117 entity itself contributes 1 orphan warning during reconcile transition state).
  - **AC-C.5 verdict:** Reduction target NOT met because 132/129 warnings are cross-workspace pollution (not F117-addressable). Critical F117 outcomes (0 errors, production bug fix landed, dynamic versioning landed) all confirmed.

## Deferred Triage Links (FR-C.4 — for future operator session)

The following 21 cross-workspace `parent_uuid` links require operator-interactive triage. Each link's `child_uuid` is the entity with a `parent_uuid` pointing across workspaces. Operator must choose per link: re-attribute parent / re-attribute child / delete relation / grandfather.

| # | Child UUID (`entity` field from doctor issue) |
|---|-----------------------------------------------|
| 1 | 154eb998-51d0-458c-897b-86a90cf9f654 |
| 2 | 45fcda8a-c6ef-4dcd-879f-e03dbf62941a |
| 3 | d291bdbc-9e4d-4fb9-94d1-fc634b5d03b0 |
| 4 | 157247ab-0a89-41bf-a900-426f68f1eb87 |
| 5 | 2b3aba82-52da-4018-86d8-7e3c154e792c |
| 6 | cecf3490-f7db-4181-99de-49022766c993 |
| 7 | f7029b56-83ee-4734-b416-113c1b132411 |
| 8 | 6e9d81f4-d419-45e6-97d1-900bd22dd258 |
| 9 | 2d76911e-fa98-49f2-986d-631f221e18d9 |
| 10 | 16c2a8a1-0e54-4a30-8d6e-d398e475dceb |
| 11 | 8dcae2d8-f70d-4047-b3f5-9164051c889e |
| 12 | 19e5e946-8f35-411d-abe5-6afa6c2124b6 |
| 13 | d03e8286-a18e-4ed1-b03c-139a013f1ec9 |
| 14 | fc26509f-02ed-48e0-be06-65106caf0876 |
| 15 | 0a07b8e6-749b-47a6-afb2-c750e8fccb86 |
| 16 | 7fa83a07-0b71-48c0-b86a-7d6432c1aa39 |
| 17 | b51e42fa-e9b3-4376-a5d9-ccb6e5b5a8ec |
| 18 | d137f12e-0368-4530-a0b9-7df953b85588 |
| 19 | 5f7f9f78-8abb-4a02-8ae4-29c1bf131556 |
| 20 | b681a4d1-ebe8-46a4-b348-a30956b4eb49 |
| 21 | ed0ac402-a0ca-4a6e-abef-913e5543b20c |

To resume triage in a future session:
```bash
# Option 1: invoke doctor --fix with interactive harness (current pd:doctor pattern)
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m doctor --fix \
  --entities-db ~/.claude/pd/entities/entities.db \
  --memory-db ~/.claude/pd/memory/memory.db \
  --project-root /Users/terry/projects/pedantic-drip \
  --artifacts-root docs

# Option 2: per-link manual via _fix_triage_cross_workspace_link
# (F117 made this work against the trigger-active DB)
```

## Aggregate Summary

- **Files changed:**
  - `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py` (FR-A.1 helper + 2 call-site updates)
  - `plugins/pd/hooks/lib/doctor/checks.py` (FR-B.1 dynamic helpers, hardcoded constants removed)
  - `plugins/pd/hooks/lib/doctor/test_fix_actions.py` (4 new F117 tests + 4 fixture re-arms)
  - `plugins/pd/hooks/lib/doctor/test_checks.py` (3 fixtures updated to dynamic versions — leave-the-ground-tidier)
  - `plugins/pd/hooks/lib/entity_registry/test_database.py` (TB.3 sweep — 6 sites)
  - `plugins/pd/hooks/lib/semantic_memory/test_database.py` (TB.4 sweep — 8 sites)
- **Tests:** 6 new (4 F117 + 2 helpers); 21 existing in `test_fix_actions.py` adapted via fixture re-arm.
- **Regression gate:** 2166 passed, 3 skipped, 0 failures.
- **validate.sh:** 0 errors, 5 warnings (baseline match).
- **Doctor:** 0 errors (down from 2); 537 warnings (cross-workspace pollution — non-F117-addressable).
- **TC.4 deferred:** 21 cross-workspace links recorded for future session.
