# Tasks: F117 — pd Post-F116 Production Hygiene

## Overview

15 tasks across 3 themes, mirroring design.md §Implementation Phase Coordination Notes 15-step TDD ordering. Each task has explicit DoD (definition of done) — binary pass/fail.

**Dispatch strategy:** Phase A and Phase B may be dispatched in parallel (no shared files). Phase C strictly serial after both A and B complete.

---

## Phase A — Theme A (Production trigger drop/recreate fix)

### TA.1 — Add `_CANONICAL_TRIGGER_SQL` constant + `_recreate_workspace_uuid_trigger` helper

**File:** `plugins/pd/hooks/lib/doctor/test_fix_actions.py`
**Complexity:** Simple (single-file mechanical addition)
**Depends on:** plan approved

**Why first:** TA.2's red test will USE `_recreate_workspace_uuid_trigger` in its fixture. Helper must exist before red test can be authored. Test-file only — no production code, no behavior change.

**Action:**
1. Add module-level constant `_CANONICAL_TRIGGER_SQL` near top of file (after imports). Content = canonical CREATE TRIGGER SQL byte-identical to `entity_registry/database.py:2042-2046`, including the em-dash (U+2014).
2. Add module-level helper `_recreate_workspace_uuid_trigger(conn: sqlite3.Connection) -> None` that executes `_CANONICAL_TRIGGER_SQL`.
3. Verify em-dash character is U+2014 (check via `hexdump` or by visual inspection of the saved file).

**DoD:**
- [ ] `_CANONICAL_TRIGGER_SQL` constant exists.
- [ ] `_recreate_workspace_uuid_trigger` function exists.
- [ ] `grep -P "—" plugins/pd/hooks/lib/doctor/test_fix_actions.py` finds the em-dash (U+2014 verified).

---

### TA.2 — Write `test_re_attribute_against_trigger_active_db` (TDD red)

**File:** `plugins/pd/hooks/lib/doctor/test_fix_actions.py`
**Complexity:** Medium (new test + new logic depending on helper from TA.1)
**Depends on:** TA.1 (uses `_recreate_workspace_uuid_trigger` in fixture)

**Action:**
1. Add new test function `test_re_attribute_against_trigger_active_db`. **Write as a single parametrized test** (`@pytest.mark.parametrize("choice", ["re-attribute parent", "re-attribute child"])`) so TA.5 requires only one `_recreate_workspace_uuid_trigger` call site for this test function (single re-arm covers both parameter values — matches design §C-A.2 step 2).
2. Setup: call `_seed_cross_workspace_pair` then call `_recreate_workspace_uuid_trigger(entities_db_session)` from TA.1.
3. Action: invoke `_fix_triage_cross_workspace_link` with the parametrized `choice` value.
4. Assertions:
   - Pre-call: `SELECT sql FROM sqlite_master WHERE name='enforce_immutable_workspace_uuid'` returns the canonical SQL.
   - Action: invoke fix function.
   - Post-call: workspace_uuid changed; same SELECT returns identical SQL; subsequent bare UPDATE against non-target row raises `sqlite3.IntegrityError` with substring `"workspace_uuid is immutable"`.

**DoD:**
- [ ] New parametrized test function exists in `test_fix_actions.py`.
- [ ] `pytest plugins/pd/hooks/lib/doctor/test_fix_actions.py::test_re_attribute_against_trigger_active_db` runs and FAILS (both parametrized variants) with `sqlite3.IntegrityError: workspace_uuid is immutable` (production bug reproduced — TDD red phase confirmed).

---

### TA.3 — Add `_execute_re_attribute_with_trigger_dance` helper + replace bare UPDATEs (TDD green)

**File:** `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py`
**Complexity:** Medium (new logic + 2 call-site replacements + R-2 docstring note)
**Depends on:** TA.1, TA.2

**Action:**
1. Add module-level helper function `_execute_re_attribute_with_trigger_dance(conn, target_entity_uuid, target_workspace_uuid)` per design §C-A.1 pseudocode. **Include R-2 mitigation docstring note** per design TD-A.1: "Per Python 3.6+ sqlite3 semantics (bpo-27334) — CPython legacy autocommit mode — DDL (DROP/CREATE) autocommits immediately; the `finally` block is the SOLE trigger-restoration mechanism. The `with conn:` rolls back the UPDATE's implicit DML transaction only. Both layers are load-bearing — neither is optional. PyPy may diverge; F117 assumes CPython only."
2. Replace bare UPDATE block in `re-attribute parent` branch (lines 532-535) with:
   ```python
   _execute_re_attribute_with_trigger_dance(
       ctx.entities_conn, parent_uuid, child_ws
   )
   ```
3. Replace bare UPDATE block in `re-attribute child` branch (lines 538-541) with:
   ```python
   _execute_re_attribute_with_trigger_dance(
       ctx.entities_conn, child_uuid, parent_ws
   )
   ```
4. Preserve existing `ctx.entities_conn.commit()` at line 560 (benign dual-commit per design Note).

**DoD:**
- [ ] `_execute_re_attribute_with_trigger_dance` exists as module-private helper with the R-2 docstring note (R-2 mitigation artifact).
- [ ] Both bare UPDATE blocks replaced.
- [ ] `grep -cE '^def _execute_re_attribute_with_trigger_dance' plugins/pd/hooks/lib/doctor/fix_actions/__init__.py` → 1 (definition).
- [ ] `grep -cE '_execute_re_attribute_with_trigger_dance\(' plugins/pd/hooks/lib/doctor/fix_actions/__init__.py` → 3 (1 def line with paren + 2 call sites).
- [ ] `pytest plugins/pd/hooks/lib/doctor/test_fix_actions.py::test_re_attribute_against_trigger_active_db` now PASSES (both parametrized variants — TDD green confirmed).

---

### TA.4 — Write FR-A.4 + FR-A.6 + R-1 tests (parallel with TA.5)

**File:** `plugins/pd/hooks/lib/doctor/test_fix_actions.py`
**Complexity:** Medium (3 new tests with non-trivial fixtures: proxy class, RuntimeError guard, regex extraction)
**Depends on:** TA.3 (production fix landed). May run in parallel with TA.5.

**Action:**
1. Add `test_re_attribute_restores_trigger_on_update_failure` (FR-A.4). Use `_FailingUpdateConn` proxy class per design §C-A.2 — proxy MUST include explicit `__enter__` / `__exit__` delegating to `self._real.__enter__/__exit__` per design rev 2.1 fix.
2. Add `test_re_attribute_aborts_when_trigger_absent` (FR-A.6). Setup: call `_seed_cross_workspace_pair` but DO NOT re-arm trigger; expect `pytest.raises(RuntimeError, match="enforce_immutable_workspace_uuid trigger not found")`.
3. Add `test_canonical_trigger_sql_matches_production_source` (R-1 mitigation). Use regex substring-scan per design §R-1 with `re.DOTALL | re.MULTILINE`; pin to `_migration_11_workspace_identity` (database.py:1772) form.

**DoD:**
- [ ] 3 new tests exist in `test_fix_actions.py`.
- [ ] `pytest plugins/pd/hooks/lib/doctor/test_fix_actions.py -k "restores_trigger or aborts_when_trigger or canonical_trigger_sql"` — all 3 pass.
- [ ] `_FailingUpdateConn` class includes both `__enter__` and `__exit__` methods (verify via grep).

---

### TA.5 — Re-arm trigger in 4 existing TC.4 sites (parallel with TA.4)

**File:** `plugins/pd/hooks/lib/doctor/test_fix_actions.py`
**Complexity:** Simple (4 single-line additions; no new logic)
**Depends on:** TA.1 (`_recreate_workspace_uuid_trigger` helper exists), TA.3 (production fix landed). May run in parallel with TA.4.

**Action:**
Add `_recreate_workspace_uuid_trigger(entities_db_session)` immediately after `_seed_cross_workspace_pair(entities_db_session)` in each of:
1. `test_t2a_7_triage_branch` (line 195 — parametrized 4-way)
2. `test_t2a_7_triage_grandfather_without_reason_uses_fallback` (line 215)
3. `test_t2a_7_triage_unknown_choice_raises_value_error` (line 242)
4. `test_fr9_legitimate_grandfather_with_reason_preserves_behavior` (line 297)

**DoD:**
- [ ] 4 re-arm calls added (verify with `grep -n "_recreate_workspace_uuid_trigger" plugins/pd/hooks/lib/doctor/test_fix_actions.py` → ≥ 5 matches: 1 def + 4 call sites + N in new tests).
- [ ] `pytest plugins/pd/hooks/lib/doctor/test_fix_actions.py` — ALL tests pass (TC.4 existing + 4 new F117 tests).

---

## Phase B — Theme B (Dynamic doctor version + 14-site test sweep)

### TB.1 — Add `_get_expected_*_version` helpers in checks.py; remove hardcoded constants

**File:** `plugins/pd/hooks/lib/doctor/checks.py`
**Complexity:** Medium (2-helper addition + constant deletion; lazy-import semantics)
**Depends on:** plan approved (parallel with Phase A)

**Action:**
1. Delete module-level constants at lines 14-15: `ENTITY_SCHEMA_VERSION = 11` and `MEMORY_SCHEMA_VERSION = 4`.
2. Add 2 helper functions (anywhere in module, recommend near top after imports):
   ```python
   def _get_expected_entity_version() -> int:
       from entity_registry.database import MIGRATIONS as ENTITY_MIGRATIONS
       return max(ENTITY_MIGRATIONS.keys())

   def _get_expected_memory_version() -> int:
       from semantic_memory.database import MIGRATIONS as MEMORY_MIGRATIONS
       return max(MEMORY_MIGRATIONS.keys())
   ```

**DoD:**
- [ ] `grep -n 'ENTITY_SCHEMA_VERSION\|MEMORY_SCHEMA_VERSION' plugins/pd/hooks/lib/doctor/checks.py` → 0 matches.
- [ ] `_get_expected_entity_version` and `_get_expected_memory_version` functions exist.
- [ ] Smoke test via the project's PYTHONPATH (NOT absolute dotted path — the venv sets `plugins/pd/hooks/lib` as site-package root, not `plugins.pd.hooks.lib`):
  ```bash
  cd plugins/pd && PYTHONPATH=hooks/lib .venv/bin/python -c "from doctor.checks import _get_expected_entity_version, _get_expected_memory_version; print(_get_expected_entity_version(), _get_expected_memory_version())"
  ```
  Expected stdout: `17 7` (or current latest values per `max(MIGRATIONS.keys())`).

---

### TB.2 — Update db_readiness + memory_health to use helpers

**File:** `plugins/pd/hooks/lib/doctor/checks.py`
**Complexity:** Simple (mechanical replacement of constant references)
**Depends on:** TB.1. May run in parallel with TB.3 / TB.4 (different files).

**Action:**
1. In `db_readiness` check body, replace all references to `ENTITY_SCHEMA_VERSION` with `_get_expected_entity_version()`.
2. In `memory_health` check body, replace all references to `MEMORY_SCHEMA_VERSION` with `_get_expected_memory_version()`.

**DoD:**
- [ ] No remaining references to deleted constants (already verified in TB.1 DoD).
- [ ] `python -m doctor` JSON output: 0 errors from `db_readiness` and `memory_health` checks (down from 2 stale-version errors).
- [ ] `pytest plugins/pd/hooks/lib/doctor/test_checks.py` — 0 new failures.

---

### TB.3 — Sweep 6 entity_registry test_database.py sites

**File:** `plugins/pd/hooks/lib/entity_registry/test_database.py`
**Complexity:** Simple (mechanical 6-site sweep + 1 helper definition)
**Depends on:** TB.1. May run in parallel with TB.2 and TB.4.

**Action:**
1. Add module-level helper near top of file (after imports):
   ```python
   def _latest_entity_version() -> int:
       from entity_registry.database import MIGRATIONS
       return max(MIGRATIONS.keys())
   ```
2. Convert 5 string-form sites:
   - Line 370: `db.get_metadata("schema_version") == "17"` → `db.get_metadata("schema_version") == str(_latest_entity_version())`
   - Line 678: same pattern.
   - Line 2688: `db2.get_metadata(...)` → analogous.
   - Line 2890: same pattern.
   - Line 3081: `fresh_db.get_metadata(...)` → analogous.
3. Convert 1 int-form site:
   - Line 4673: `db.get_schema_version() == 17` → `db.get_schema_version() == _latest_entity_version()`

**DoD:**
- [ ] `grep -nE 'get_metadata\("schema_version"\)\s*==\s*"\d+"|get_schema_version\(\)\s*==\s*\d+' plugins/pd/hooks/lib/entity_registry/test_database.py` → 0 matches (all 6 converted).
- [ ] Migration-safety pin sites in `test_database.py` (if any) untouched — verify lines 4077-4081 + 4524 still use `result["schema_version"] == 1` (EXPORT_SCHEMA_VERSION, excluded).
- [ ] `pytest plugins/pd/hooks/lib/entity_registry/test_database.py` — 0 new failures.

---

### TB.4 — Sweep 8 semantic_memory test_database.py sites

**File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
**Complexity:** Simple (mechanical 8-site sweep + 1 helper definition)
**Depends on:** TB.1. May run in parallel with TB.2 and TB.3.

**Action:**
1. Add module-level helper near top of file:
   ```python
   def _latest_memory_version() -> int:
       from semantic_memory.database import MIGRATIONS
       return max(MIGRATIONS.keys())
   ```
2. Convert 8 sites at lines 91, 116, 123, 127, 191, 1266, 1306, 1310:
   - Form: `assert dbN.get_schema_version() == 7` → `assert dbN.get_schema_version() == _latest_memory_version()`

**DoD:**
- [ ] `grep -nE 'get_schema_version\(\)\s*==\s*\d+' plugins/pd/hooks/lib/semantic_memory/test_database.py` → 0 matches. (Migration-safety pins use `_read_schema_version(...) == "..."` form which this regex does not match; line 2857 confirmed safe by the separate preservation check below — no parenthetical scope qualifier needed.)
- [ ] Line 2857 (`_read_schema_version(db_path) == "5"`) MUST remain untouched (FR-B.2b pinned site). Verify: `grep -n '_read_schema_version(db_path) == "5"' plugins/pd/hooks/lib/semantic_memory/test_database.py` → 1 match at line 2857.
- [ ] `pytest plugins/pd/hooks/lib/semantic_memory/test_database.py` — 0 new failures.

---

### TB.5 — Full pytest + validate.sh regression check

**File:** N/A (verification only)
**Complexity:** Simple (verification only — no code change)
**Depends on:** TB.1, TB.2, TB.3, TB.4 (all Phase B code changes complete)

**Action:**
1. **Capture baseline FIRST** (before any TB.* edits land — to make the "no new failures" criterion binary). Implementer SHOULD have captured this at session start; if not, capture from `git stash` of all F117 changes:
   ```bash
   git stash push -m "f117-tb5-baseline-capture" -- plugins/pd/hooks/lib/
   plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ --tb=no -q 2>&1 | tail -5 > /tmp/f117-pytest-baseline.txt
   ./validate.sh 2>&1 | tail -20 > /tmp/f117-validate-baseline.txt
   git stash pop
   ```
   The expected baseline on develop branch (verified 2026-05-18 at session start by F116 finish): pytest passes; validate.sh exits 0 with 5 pre-existing cosmetic warnings (per F116 .meta.json `validate.sh: 0 errors, 5 warnings (pre-existing cosmetic)`).
2. Run `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/` — capture summary.
3. Run `./validate.sh` — capture exit code + errors.
4. Compare against baseline: 0 NEW failures or NEW errors attributable to F117 changes.

**DoD:**
- [ ] Pytest summary: 0 failures in `doctor`, `entity_registry`, `semantic_memory` test modules.
- [ ] `./validate.sh` exit code matches baseline (expected: 0 errors).
- [ ] Validate.sh warning count matches baseline (expected: 5 pre-existing cosmetic warnings — same set, no new ones). If new warning text appears, diff against baseline to identify the F117-attributable warning and resolve before proceeding.

---

## Phase C — Theme C (Operational reconciliation)

### TC.1 — `reconcile_check` dry-run

**File:** `docs/features/117-post-f116-hygiene/reconcile-dry-run.json` (NEW)
**Complexity:** Simple (MCP invocation + JSON capture)
**Depends on:** TA.5, TB.5 (Phases A + B complete)

**Action:**
1. Invoke `reconcile_check` via workflow-engine MCP.
2. Capture full JSON response to `docs/features/117-post-f116-hygiene/reconcile-dry-run.json`.
3. Visual review of the dry-run output: count `feature_status` corrections, `workflow_phase` corrections, `entity_orphans` corrections.

**DoD:**
- [ ] `reconcile-dry-run.json` exists in feature folder.
- [ ] `jq . docs/features/117-post-f116-hygiene/reconcile-dry-run.json` returns valid JSON without errors.
- [ ] Diff is sanity-checked (no archive operations against active features; no parent_uuid clears on non-orphans).

---

### TC.2 — `reconcile_apply`

**File:** N/A (operational + retro entry)
**Complexity:** Simple (MCP invocation + post-doctor count diff)
**Depends on:** TC.1

**Action:**
1. Invoke `reconcile_apply` via workflow-engine MCP.
2. Capture post-apply doctor count for `feature_status` + `workflow_phase` warnings.
3. Verify reduction ≥ 261 (132 + 129 from pre-F117 baseline).

**DoD:**
- [ ] `reconcile_apply` returned success result.
- [ ] Pre-apply vs post-apply doctor JSON shows `feature_status` count < 5 AND `workflow_phase` count < 5.

---

### TC.3 — 4 brainstorm transitions

**File:** N/A (operational; entity DB writes)
**Complexity:** Simple (4 sequential MCP calls)
**Depends on:** TC.2 (reconcile clean state)

**Action:**
Invoke `update_entity` MCP 4 times (one per brainstorm) with `status="promoted"`:

1. `update_entity(type_id="brainstorm:20260516-210137-pd-followups", status="promoted")` — F115 brainstorm
2. `update_entity(type_id="brainstorm:20260516-184258-pd-data-model-hardening", status="promoted")` — F114 brainstorm
3. `update_entity(type_id="brainstorm:20260517-053927-f115-qa-deferred", status="promoted")` — F116 brainstorm
4. `update_entity(type_id="brainstorm:20260327-050000-phase-transition-summary", status="promoted")` — older

**DoD:**
- [ ] `sqlite3 ~/.claude/pd/entities/entities.db "SELECT COUNT(*) FROM entities WHERE kind='brainstorm' AND status='active'"` → 0.
- [ ] Each `update_entity` call returned success (not error_type=not_found).

---

### TC.4 — 21-link interactive triage (operator YOLO break)

**File:** N/A (operational; entity DB writes)
**Complexity:** Complex (operator-interactive; cross-component dependency on Theme A fix)
**Depends on:** TC.3 (brainstorm transitions complete), TA.3 (production fix landed — required for triage tool to work)

**Action:**
1. Run `pd doctor --fix` against the 21 cross-workspace links via the doctor harness.
2. For each link, operator selects one of: `re-attribute parent | re-attribute child | delete relation | grandfather`.
3. YOLO break authorized per PRD §YOLO Mode Exceptions.

**Deferral path (if operator unavailable):**
- Per design §C-C.4 deferral semantics, record unprocessed links to retro.md "Deferred Triage Links" table.
- Reduction accounting falls under AC-C.5 IF-deferred branch (≥ 259).

**DoD:**
- [ ] EITHER: all 21 links processed (operator made 21 decisions); post-triage doctor `cross_workspace_parent_uuid` count = `cross_workspace_allowlist` row count.
- [ ] OR: deferral artifact present in retro.md "Deferred Triage Links" section with unprocessed (parent_uuid, child_uuid) pairs listed.

---

### TC.5 — Final doctor sanity check + retro entry

**File:** `docs/features/117-post-f116-hygiene/retro.md` (referenced; created by /pd:finish-feature)
**Complexity:** Simple (verification + retro data capture)
**Depends on:** TC.4 (or deferral artifact)

**Action:**
1. Run `python -m doctor` JSON output; capture to a temporary file (e.g., `/tmp/f117-final-doctor.json`).
2. Verify each of the 3 AC-C.5 criteria via binary commands (see DoD below).
3. Add the doctor output diff + summary table to `retro.md` notes section (will be created in /pd:finish-feature, but TC.5 prepares the data).

**DoD:**
- [ ] **0 errors check:** `jq '[.checks[].issues[] | select(.severity == "error")] | length' /tmp/f117-final-doctor.json` → `0`.
- [ ] **severity_summary F116 invariant preserved:** `jq '.severity_summary' /tmp/f117-final-doctor.json` returns a non-null object of form `{"error": 0, "warning": N, "info": M}` (NOT `null`, NOT missing).
- [ ] **Reduction threshold (AC-C.5 conditional):**
    - IF TC.4 completed (all 21 links processed): `jq '[.checks[].issues[]] | length' /tmp/f117-final-doctor.json` ≤ (537 − 280) = 257.
    - IF TC.4 deferred: `jq '[.checks[].issues[]] | length' /tmp/f117-final-doctor.json` ≤ (537 − 259) = 278.
- [ ] Doctor output captured (file path or inline summary in retro draft).

---

## Risk Mitigations (cross-task)

| Risk | Mitigating task |
|------|----------------|
| R-1 (HIGH) Trigger SQL drift | TA.4 → `test_canonical_trigger_sql_matches_production_source` |
| R-2 (MED) PyPy semantics | N/A — CPython-only assumption (no task; documented in design) |
| R-3 (MED) FK enforcement | TA.4 uses proxy injection (FK rejected at design); no PRAGMA needed |
| R-4 (LOW) reconcile unexpected writes | TC.1 dry-run before TC.2 apply |
| R-5 (LOW) Operator unavailable | TC.4 deferral path documented |

## Parallelism Notes

**Dispatch groups (for /pd:implement parallel agent dispatch):**

- **Group 1 (Phase A core):** TA.1 → TA.2 → TA.3 (sequential within group; TDD red-green chain).
- **Group 2 (Phase A additional):** TA.4 + TA.5 (after TA.3, can run in parallel with each other).
- **Group 3 (Phase B core):** TB.1 → TB.2 (sequential).
- **Group 4 (Phase B sweep):** TB.3 + TB.4 (after TB.1, can run in parallel with each other and with TB.2).
- **Group 5 (Phase B regression):** TB.5 (after all Phase B code changes).
- **Group 6 (Phase C):** TC.1 → TC.2 → TC.3 → TC.4 → TC.5 (strictly sequential; operational only).

**Critical-path step count (with parallelism):** 9 steps (TA.1 → TA.2 → TA.3 → (TA.4 || TA.5) → TC.1 → TC.2 → TC.3 → TC.4 → TC.5) — see plan.md Critical path.
