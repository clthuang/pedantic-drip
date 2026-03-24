# Plan: pd:doctor — Phase 1 Data Consistency Diagnostic

## Context

Feature 059. The pd plugin has 7 data stores that drift out of sync. This feature creates a `pd:doctor` command running 10 read-only checks. Adversarial probing found real issues: 25 orphaned cross-project entities, 37 missing brainstorm_source files, 10+ features with stale lastCompletedPhase, 6 brainstorm entities with missing files. 11 hardening sub-checks are folded into the existing 10-check structure.

Three rounds of adversarial review addressed: plan blockers (R1), side effects/rework safety (R2), and cross-project/marketplace scenarios (R3).

---

## Task 0: Project-Scoping Utility

**File:** `plugins/pd/hooks/lib/doctor/checks.py` (helper at top)

**Deliverable:** `_build_local_entity_set(entities_conn, artifacts_root) -> set[str]`

Scans `{artifacts_root}/features/*/` directories to build a set of local feature entity_ids (directory names). Used by Checks 1, 2, 6, 7 to distinguish local entities from cross-project entities in the shared global DB.

Also: `_is_local_entity(entity_id, local_ids) -> bool` — returns True if entity matches a local directory.

**Why:** The entity DB (`~/.claude/pd/entities/entities.db`) is global across all projects but has no `project` column. Without this filter, Checks 1, 2, and 7 produce dozens of false warnings for cross-project entities.

**Verification:** Test with mixed local/cross-project entities → correctly partitions.

---

## Task 1: Data Models

**File:** `plugins/pd/hooks/lib/doctor/models.py` (new)

**Deliverables:**
- `Issue` dataclass: fields `check`, `severity`, `entity`, `message`, `fix_hint`
- `CheckResult` dataclass: fields `name`, `passed`, `issues`, `elapsed_ms`, `extras: dict` (default empty — for side-channel data like DB lock status)
- `DiagnosticReport` dataclass: fields `healthy`, `checks`, `total_issues`, `error_count`, `warning_count`, `elapsed_ms`
- `to_dict()` on each using `dataclasses.asdict()` — None values serialize as `null`
- Also create empty `plugins/pd/hooks/lib/doctor/__init__.py`

**Verification:**
```bash
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -c "from doctor.models import Issue, CheckResult, DiagnosticReport; print('OK')"
```

---

## Task 2: Check 8 — DB Readiness

**File:** `plugins/pd/hooks/lib/doctor/checks.py` (new, first check)

**Function:** `check_db_readiness(entities_db_path, memory_db_path, **_) -> CheckResult`

**Sub-checks:**
1. Entity DB: `BEGIN IMMEDIATE` with 2s timeout → **ROLLBACK immediately** after success → error if locked
2. Memory DB: `BEGIN IMMEDIATE` with 2s timeout → **ROLLBACK immediately** after success → error if locked
3. Entity DB schema_version == 7 (separate read-only query) → error if wrong
4. WAL journal mode on both (separate read-only query) → warning if not WAL

**Critical:** Each `BEGIN IMMEDIATE` must be followed by immediate `ROLLBACK` to release the write lock within milliseconds. Schema/WAL checks use separate `BEGIN` (shared read) transactions.

**Returns:** `CheckResult` with `extras={"entity_db_ok": bool, "memory_db_ok": bool}` — orchestrator reads `extras` to decide which checks to skip. (Memory DB schema_version is checked by Check 5, not duplicated here.)

**Verification:** Test with valid DBs → passes. Test with locked DB → reports error. Test with wrong schema version → reports error.

---

## Task 3: Check 1 — Feature Status

**Function:** `check_feature_status(entities_conn, artifacts_root, local_entity_ids, **_) -> CheckResult`

**Sub-checks:**
1. Scan `{artifacts_root}/features/*/.meta.json` — try-parse each, report error if malformed JSON (don't crash)
2. Compare .meta.json `status` vs entity DB `entities.status` → error on mismatch
3. Missing from DB (local feature) → warning. Missing .meta.json (local feature) → warning
4. **Cross-project filter:** DB entities not in `local_entity_ids` → skip (not reported, handled by Check 7)
5. **Hardening:** If .meta.json has `phases` with `completed` timestamps but `lastCompletedPhase` is null → warning with fix_hint

**Verification:** Test status mismatch → error (AC-3). Test malformed JSON → error, no crash. Test null lastCompletedPhase with completed phases → warning.

---

## Task 4: Check 2 — Workflow Phase

**Function:** `check_workflow_phase(entities_db_path, artifacts_root, **_) -> CheckResult`

**Sub-checks:**
1. Construct `EntityDatabase(entities_db_path)` + `WorkflowStateEngine(db, artifacts_root)` in try/finally
2. **Hang mitigation (B3):** Wrap `EntityDatabase()` construction in try/except for `sqlite3.OperationalError`. If `_migrate()` blocks, report error and skip remaining sub-checks.
3. Call `check_workflow_drift()` — translate drift reports to Issues
4. **Backward transition awareness (R2):** For each feature, if DB `workflow_phase` index < `last_completed_phase` index, this is a legitimate rework state — report as `info` ("Feature in rework state"), NOT error. Only report drift as error when both directions indicate forward-only state.
5. **Preserve drift direction (R5-conflict):** Translate `WorkflowDriftReport.status` preserving directionality:
   - `meta_json_ahead` → error, fix_hint: "Run reconcile_apply to sync"
   - `db_ahead` → error, fix_hint: "DB has newer state — manually inspect .meta.json"
   - `meta_json_only` → warning, fix_hint: "Run reconcile_apply to create DB row"
   - `db_only` → **Cross-project filter:** skip if entity_id not in `local_entity_ids`. Otherwise → warning "Entity has DB row but no .meta.json"
6. **Kanban drift (conflict #5):** Inspect `report.mismatches` for `kanban_column` entries even on `in_sync` features → warning if kanban diverges

**Reuses:** `check_workflow_drift` from `workflow_engine.reconciliation:634`, `EntityDatabase` from `entity_registry.database:954`, `WorkflowStateEngine` from `workflow_engine.engine:43`

**Verification:** Test phase mismatch → error (AC-4). Test in-sync feature → passes. Test backward-transitioned feature → info (not error). Test kanban-only drift → warning. Test meta_json_ahead vs db_ahead → different fix_hints.

---

## Task 5: Check 3 — Brainstorm Status

**Function:** `check_brainstorm_status(entities_conn, artifacts_root, **_) -> CheckResult`

**Sub-checks:**
1. For each brainstorm entity with status != "promoted": scan feature .meta.json for `brainstorm_source` references. If a completed feature references it → warning "should be promoted"
2. **Fallback (B4):** Also check `entity_dependencies` for brainstorm→feature edges as alternate linkage path
3. **Hardening:** For each feature with `brainstorm_source`, verify file exists → warning if missing (37 real cases)

**Verification:** Test brainstorm referenced by completed feature → warning (AC-5). Test brainstorm linked via entity_dependencies only → warning. Test missing brainstorm_source file → warning.

---

## Task 6: Check 4 — Backlog Status

**Function:** `check_backlog_status(entities_conn, artifacts_root, **_) -> CheckResult`

**Sub-checks:**
1. Parse `{artifacts_root}/backlog.md` for `(promoted →` annotations
2. Cross-ref entity DB `backlog:{id}` status → warning if annotated but entity not updated
3. Entity updated but not annotated → info

**Verification:** Test annotated but entity not promoted → warning. Test no backlog.md → passes with info.

---

## Task 7: Check 5 — Memory Health

**Function:** `check_memory_health(memory_conn, **_) -> CheckResult`

**Sub-checks:**
1. schema_version == 4 → error if wrong
2. Tables exist: entries, _metadata, influence_log → error if missing
3. FTS5 virtual table `entries_fts` exists → error if missing
4. 3 FTS triggers exist (entries_ai, entries_ad, entries_au) → error if missing
5. **Hardening:** FTS row count vs entries row count → warning if divergent
6. Entries with `keywords = '[]'` → info if > 0
7. NULL embedding > 10% of total → warning
8. `length(embedding) != 3072` for non-NULL → error
9. WAL journal mode → warning if not WAL

**Verification:** Test wrong schema → error (AC-6). Test FTS row count mismatch → warning. Test healthy DB → passes.

---

## Task 8: Check 6 — Branch Consistency

**Function:** `check_branch_consistency(entities_conn, artifacts_root, project_root, base_branch, **_) -> CheckResult`

**Sub-checks:**
1. **Hardening (first):** Verify base_branch exists via `git rev-parse --verify {base_branch}` → error if missing, skip remaining sub-checks
2. **Also check `origin/{base_branch}`** if local base_branch not found (W5: remote-only branch)
3. For each active feature: read branch from .meta.json, check `git branch --list '{branch}'`
4. Active + no branch + merged to base (`git log --max-count=1`):
   - **Rework-aware (R3):** If DB `workflow_phase` index < `last_completed_phase` index → warning with fix_hint "Create new branch for rework" (NOT "mark as completed")
   - Otherwise → error with fix_hint "Feature merged but still active"
5. Active + no branch + not merged → warning

**Verification:** Test missing base_branch → error (no crash). Test active feature with deleted branch → warning/error. Test reworked feature with merged branch → warning (not error).

---

## Task 9: Check 7 — Entity Orphans

**Function:** `check_entity_orphans(entities_conn, artifacts_root, **_) -> CheckResult`

**Sub-checks:**
1. **Cross-project safe (R1):** Build set of local entity_ids by scanning `{artifacts_root}/features/` directories. Only flag as orphans DB entities whose `entity_id` matches a known-local pattern (has a matching directory prefix) but directory is missing. Entities with no local match → `info` "Entity may belong to another project" (NOT warning/error, NOT suggesting deletion).
2. Feature directories with .meta.json but no entity in DB → warning
3. Entities with non-NULL `artifact_path`: only flag if path is under current `project_root` AND doesn't exist → warning. Skip cross-project artifact_paths.
4. **Hardening:** Brainstorm .prd.md files in `{artifacts_root}/brainstorms/` without corresponding brainstorm entity → warning

**Verification:** Test orphaned DB entity (local) → warning. Test cross-project entity → info (not warning). Test orphaned .prd.md file → warning. Test all matched → passes.

---

## Task 10: Check 9 — Referential Integrity

**Function:** `check_referential_integrity(entities_conn, **_) -> CheckResult`

**Sub-checks:**
1. `parent_type_id` references existing entity → error if dangling
2. `parent_uuid` matches entity with `parent_type_id` → error if mismatched
3. `workflow_phases.type_id` references existing entity → error if orphaned
4. No self-referential parents → error if found
5. **Hardening:** parent_type_id set but parent_uuid is NULL → error (migration 2 gap)
6. **Hardening:** Circular parent chains via recursive walk (depth limit 20) → error if cycle
7. **Hardening:** entity_dependencies rows where entity_uuid or blocked_by_uuid not in entities.uuid → warning
8. **Hardening:** entity_tags rows where entity_uuid not in entities.uuid → warning

**Verification:** Test dangling parent → error. Test parent_uuid NULL with parent_type_id → error. Test circular chain → error. Test orphaned dependency row → warning.

---

## Task 11: Check 10 — Config Validity

**Function:** `check_config_validity(project_root, **_) -> CheckResult`

**Reuses:** `read_config()` from `semantic_memory.config:59`

**Sub-checks:**
1. **Hardening (first):** Verify `artifacts_root` directory exists → error if missing
2. Memory weights sum to 1.0 (±0.01) → warning if not
3. Thresholds in [0.0, 1.0] → warning if out of range
4. Embedding provider set when semantic_enabled=true → warning if missing

**Verification:** Test weights sum 0.9 → warning (AC-8). Test missing artifacts_root → error. Test valid config → passes.

---

## Task 12: Orchestrator

**File:** `plugins/pd/hooks/lib/doctor/__init__.py` (update)

**Deliverables:**
- `run_diagnostics(entities_db_path, memory_db_path, artifacts_root, project_root) -> DiagnosticReport`
- **Self-resolve config:** Read `read_config(project_root)` to resolve `base_branch` (falling back to `"main"`) and validate `artifacts_root` matches config. No extra params in public API.
- **Guard DB paths (C2 fix):** Before `sqlite3.connect()`, check `os.path.isfile(db_path)`. If missing, produce error CheckResult "DB not found at {path}" — do NOT create empty files.
- `CHECK_ORDER` list defining execution sequence (Check 8 first)
- Build `local_entity_ids` set via `_build_local_entity_set()` — pass in ctx for Checks 1, 2, 6, 7
- Skip logic: read `check8_result.extras["entity_db_ok"]` / `["memory_db_ok"]` — if False, produce sentinel CheckResults for dependent checks
- Per-check try/except producing error CheckResult on uncaught exception
- Connection lifecycle: try/finally closing both connections

**Verification:**
```bash
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -c "
from doctor import run_diagnostics
r = run_diagnostics(
    '/Users/terry/.claude/pd/entities/entities.db',
    '/Users/terry/.claude/pd/memory/memory.db',
    'docs', '.'
)
print(f'healthy={r.healthy}, checks={len(r.checks)}, errors={r.error_count}, warnings={r.warning_count}')
"
```
Must output exactly 10 checks (AC-1).

---

## Task 13: CLI Entry Point

**File:** `plugins/pd/hooks/lib/doctor/__main__.py` (new)

**Deliverables:**
- argparse: `--entities-db`, `--memory-db`, `--project-root` (required), `--artifacts-root` (optional, defaults to config value)
- `artifacts_root` resolved via: CLI arg > `read_config(project_root)["artifacts_root"]` > `"docs"`
- `base_branch` resolved internally by `run_diagnostics()` via `read_config()`
- Calls `run_diagnostics()`, prints `DiagnosticReport.to_dict()` as JSON to stdout
- Exit code 0 always

**Verification:**
```bash
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m doctor \
  --entities-db ~/.claude/pd/entities/entities.db \
  --memory-db ~/.claude/pd/memory/memory.db \
  --artifacts-root docs --project-root . | python3 -m json.tool
```
Must output valid JSON with 10 checks.

---

## Task 14: Tests (BDD)

**File:** `plugins/pd/hooks/lib/doctor/test_checks.py` (new)

**Test structure:** Follow `test_reconciliation.py` patterns — in-memory `EntityDatabase(":memory:")`, `tmp_path` fixtures, class-based grouping.

**Shared test helpers:**
- `_make_db()` — `EntityDatabase(":memory:")`
- `_register_feature(db, slug, status)` — register feature, return type_id
- `_create_meta_json(tmp_path, slug, ...)` — write `.meta.json`
- `_create_brainstorm_prd(tmp_path, slug)` — write `.prd.md`
- `_make_memory_db(schema_version, ...)` — create in-memory memory DB

**85 BDD scenarios organized in 7 groups:**

### Group 1: Core ACs (13 scenarios)
| Test | Given | When | Then |
|------|-------|------|------|
| `test_report_has_10_checks` | any project | `run_diagnostics()` | 10 unique CheckResults |
| `test_report_10_checks_even_when_locked` | entity DB locked | `run_diagnostics()` | 10 checks, locked ones have sentinel |
| `test_healthy_project_all_pass` | 3 matched features, valid DBs | `run_diagnostics()` | healthy=True, all passed |
| `test_info_issues_do_not_flip_passed` | info-only issues | `run_diagnostics()` | passed=True, healthy=True |
| `test_check1_status_mismatch_reports_error` | meta=active, DB=completed | check_feature_status() | error, mentions both |
| `test_check2_workflow_phase_drift` | meta phase != DB phase | check_workflow_phase() | error with fix_hint |
| `test_check3_brainstorm_should_be_promoted` | active brainstorm, completed feature refs it | check_brainstorm_status() | warning "should be promoted" |
| `test_check5_memory_schema_wrong` | schema_version=3 | check_memory_health() | error |
| `test_check8_db_lock_detected` | entity DB locked | check_db_readiness() | error, extras.entity_db_ok=False |
| `test_check10_config_weights_sum` | weights=0.9 | check_config_validity() | warning |
| `test_cli_json_output_has_10_checks` | valid DBs | subprocess python -m doctor | valid JSON, 10 checks |
| `test_cli_exit_code_always_zero` | broken project | subprocess python -m doctor | exit=0, healthy=false |
| `test_works_without_mcp` | no MCP | `run_diagnostics()` | no ImportError |

### Group 2: Check-Specific (34 scenarios)
**Check 1 (6):** all_match, missing_from_db, missing_meta, malformed_json, null_lastCompletedPhase, cross_project_skip
**Check 2 (6):** in_sync, meta_ahead_hint, db_ahead_hint, meta_only_warning, kanban_drift, construction_failure
**Check 3 (4):** no_promotion_needed, entity_deps_fallback, source_missing, no_brainstorms
**Check 4 (4):** annotated_not_promoted, missing_file, promoted_not_annotated_info, empty_backlog
**Check 5 (9):** healthy, missing_table, missing_fts, missing_trigger, fts_rowcount_divergence, empty_keywords_info, null_embedding_above_threshold, wrong_dimension, non_wal
**Check 6 (5):** all_branches_exist, base_branch_missing, active_no_branch_not_merged, active_merged_not_rework_error, remote_base_fallback
**Check 7 (5):** all_matched, orphaned_local, dir_no_entity, orphaned_brainstorm_prd, cross_project_artifact_skipped
**Check 8 (6):** both_healthy, entity_locked, memory_locked, wrong_schema, non_wal, immediate_rollback
**Check 9 (8):** valid_refs, dangling_parent, uuid_mismatch, orphaned_workflow_phases, self_ref, null_uuid_with_type_id, circular_chain, orphaned_deps, orphaned_tags
**Check 10 (5):** valid_config, artifacts_root_missing, threshold_range, missing_provider, missing_config_defaults

### Group 3: Cross-Project (6 scenarios)
| Test | Validates |
|------|-----------|
| `test_cross_project_entity_info_not_warning` | Check 7: non-local → info |
| `test_cross_project_entities_aggregated_info` | Check 7: single summary, not N issues |
| `test_cross_project_check1_no_warning` | Check 1: non-local skipped |
| `test_cross_project_check2_db_only_skipped` | Check 2: db_only filtered |
| `test_build_local_entity_set` | utility: correct set from dirs |
| `test_check6_only_checks_local_features` | Check 6: non-local branches skipped |

### Group 4: Backward Transition (5 scenarios)
| Test | Validates |
|------|-----------|
| `test_backward_transition_not_error` | Check 2: phase < last_completed → info |
| `test_backward_transition_null_reason` | null reason still → info |
| `test_reworked_feature_merged_branch` | Check 6: "create branch" hint |
| `test_forward_feature_merged_branch_error` | Check 6: "merged but active" hint |
| `test_phase_regression_vs_corruption` | NULL phase vs regressed phase |

### Group 5: Orchestrator (9 scenarios)
| Test | Validates |
|------|-----------|
| `test_entity_db_lock_skips_dependent` | Checks 1-4,6,7,9 sentinel |
| `test_memory_db_lock_skips_check5` | Check 5 sentinel only |
| `test_per_check_exception_isolation` | RuntimeError caught, 10 checks |
| `test_connections_closed_on_success` | try/finally lifecycle |
| `test_connections_closed_on_exception` | try/finally on error |
| `test_base_branch_from_config` | reads pd.local.md |
| `test_base_branch_default_main` | no config → "main" |
| `test_missing_db_file_no_create` | os.path.isfile guard |
| `test_check8_runs_first` | execution order |

### Group 6: CLI (6 scenarios)
| Test | Validates |
|------|-----------|
| `test_cli_json_structure_matches_model` | all keys present |
| `test_cli_artifacts_root_cli_arg_precedence` | CLI arg > config |
| `test_cli_artifacts_root_config_fallback` | config > default |
| `test_cli_artifacts_root_default_docs` | no config → "docs" |
| `test_cli_none_serializes_as_json_null` | null, not "None" |
| `test_serialization_roundtrip` | json.dumps/loads roundtrip |

### Group 7: Edge Cases (12 scenarios)
| Test | Validates |
|------|-----------|
| `test_fresh_project_empty` | no features/brainstorms/backlog |
| `test_empty_entity_db` | schema but zero rows |
| `test_100_features_performance` | < 10s (@pytest.mark.slow) |
| `test_feature_dir_no_meta_json` | empty dir |
| `test_meta_json_extra_fields_ignored` | unknown fields OK |
| `test_zero_length_embedding` | boundary |
| `test_multiple_backlog_annotations` | 3 annotations, 2 unsynced |
| `test_deep_chain_no_false_positive` | depth 19, valid |
| `test_chain_at_depth_limit` | depth 20, defined behavior |
| `test_both_dbs_locked` | all locked, Check 10 still runs |
| `test_check_result_passed_logic` | error/warning/info semantics |
| `test_diagnostic_report_healthy_aggregate` | 9 pass + 1 fail = unhealthy |

**Verification:**
```bash
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/test_checks.py -v
```
85 BDD scenarios across 7 groups.

---

## Task 15: Command File

**File:** `plugins/pd/commands/doctor.md` (new)

**Deliverables:**
- Frontmatter: `description: Run diagnostic checks on pd workspace health`
- Plugin portability pattern (cache primary, dev workspace fallback)
- **Use `{pd_artifacts_root}` variable** (expanded by Claude Code) — NOT hardcoded `docs`
- **Venv-missing guard (D fix):** If both primary and fallback venv paths fail, output synthetic JSON error: `{"healthy":false,...,"error":"Plugin venv not found"}`
- Bash invocation with path resolution
- JSON output parsing
- Table format: `Check | Status | Issues`
- Failed check details section
- Footer note: "Doctor runs after session-start reconciliation. Issues here indicate problems that survived auto-repair."

**Verification:** `test_cli_json_output_has_10_checks` in Task 14 validates JSON structure. Command file format verified by running the Bash invocation directly and checking output contains table header `Check | Status | Issues`.

---

## Task 16: Documentation Sync

**Files:** `README.md`, `README_FOR_DEV.md`, `plugins/pd/README.md`

**Deliverables:**
- Add `doctor` to command tables in all 3 files
- Add test command to README_FOR_DEV.md
- Update component counts in plugins/pd/README.md

**Verification:** `grep -c 'doctor' README.md README_FOR_DEV.md plugins/pd/README.md` — each returns ≥1.

---

## Execution Order

```
Task 1 (models)
  → Task 2 (Check 8: DB Readiness)
  → Tasks 3-11 (Checks 1-7, 9-10) — sequential, each adds one function to checks.py
  → Task 12 (orchestrator)
  → Task 13 (CLI)
  → Task 14 (tests) — run and iterate until green
  → Task 15 (command file)
  → Task 16 (docs)
```

---

## Critical Files

| File | Action |
|------|--------|
| `plugins/pd/hooks/lib/doctor/__init__.py` | Create (Task 1 stub → Task 12 orchestrator) |
| `plugins/pd/hooks/lib/doctor/models.py` | Create (Task 1) |
| `plugins/pd/hooks/lib/doctor/checks.py` | Create (Tasks 2-11, incremental) |
| `plugins/pd/hooks/lib/doctor/__main__.py` | Create (Task 13) |
| `plugins/pd/hooks/lib/doctor/test_checks.py` | Create (Task 14) |
| `plugins/pd/commands/doctor.md` | Create (Task 15) |
| `README.md` | Update (Task 16) |
| `README_FOR_DEV.md` | Update (Task 16) |
| `plugins/pd/README.md` | Update (Task 16) |

## Key Reuse

| Import | From | Used By |
|--------|------|---------|
| `check_workflow_drift` | `workflow_engine.reconciliation:634` | Task 4 (Check 2) |
| `WorkflowStateEngine` | `workflow_engine.engine:43` | Task 4 (Check 2) |
| `EntityDatabase` | `entity_registry.database:954` | Task 4 (Check 2) |
| `read_config` | `semantic_memory.config:59` | Task 11 (Check 10) |

## Adversarial Review Resolutions

### Round 1 (Plan Review)

| ID | Issue | Resolution |
|----|-------|------------|
| B1 | `run_diagnostics` signature has extra `base_branch` param | Removed — resolved internally via `read_config()` |
| B2 | Memory DB schema_version checked in both Check 8 and Check 5 | Removed from Check 8, kept only in Check 5 |
| B3 | `EntityDatabase()` constructor blocks 15s on locked DB | Check 2 wraps construction in try/except with timeout-aware handling |
| B4 | Spec Check 3 entity_dependencies fallback missing | Added to Task 5 sub-checks |
| B5 | AC-9 untested | Added `test_cli_json_output_has_10_checks` to Task 14 |
| W1/W6 | No side-channel for DB lock status | Added `extras: dict` field to `CheckResult` model |
| W2 | Column existence checks redundant with schema_version | Removed from Check 8 |
| W4 | git log without depth limit | Added `--max-count=1` to Check 6 |
| W5 | base_branch may be remote-only | Check 6 also checks `origin/{base_branch}` |
| W7 | No test for Check 4 | Added 2 tests for backlog scenarios |
| I6 | CLI defaults to `main` instead of config | CLI removed `--base-branch`, resolved by orchestrator via config |

### Round 2 (Side Effects & Conflicts)

| ID | Issue | Resolution |
|----|-------|------------|
| R1 | Cross-project entities falsely flagged as orphans | Check 7 only flags local-match entities; cross-project → info |
| R2 | Backward transitions reported as phase drift errors | Check 2 detects rework state (phase < last_completed) → info |
| R3 | Merged-branch fix_hint suggests completing reworked feature | Check 6 rework-aware: suggests "create branch" instead |
| R5 | Drift direction flattened, fix_hint goes wrong way | Check 2 preserves meta_ahead/db_ahead with direction-specific hints |
| C5 | Kanban-only drift missed on in_sync features | Check 2 inspects mismatches list even for in_sync status |
| C7 | Doctor runs after session-start reconciliation (undocumented) | Document in command file output: "Issues found here survived auto-repair" |
| C8 | Check 8 `BEGIN IMMEDIATE` holds write lock too long | Immediate `ROLLBACK` after lock test; schema checks use read txn |

### Round 3 (Cross-Project & Marketplace)

| ID | Issue | Resolution |
|----|-------|------------|
| A5/B1 | Hardcoded `--artifacts-root docs` in command file | Use `{pd_artifacts_root}` variable; CLI makes it optional with config fallback |
| B2-C1 | Checks 1, 2 produce cross-project false positives | Added Task 0: `_build_local_entity_set()` utility; Checks 1, 2 filter by local_entity_ids |
| B2-C2 | Check 2 db_only drift for cross-project entities | db_only reports filtered by local_entity_ids |
| C2 | Check 8 `sqlite3.connect()` creates empty DB files | Guard with `os.path.isfile()` before connecting |
| D | No venv = silent failure | Command file outputs synthetic JSON error if venv missing |
| A3 | Check 7 emits N info issues for N cross-project entities | Aggregate into single summary info issue per check |

## End-to-End Verification

1. `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/test_checks.py -v` — 85 BDD tests pass
2. CLI on live data — outputs valid JSON with 10 checks, reports known issues (orphaned entities, stale brainstorms)
3. No MCP dependency — works with MCP servers killed
4. Regression check — `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/ plugins/pd/hooks/lib/entity_registry/ -v --timeout=60`
