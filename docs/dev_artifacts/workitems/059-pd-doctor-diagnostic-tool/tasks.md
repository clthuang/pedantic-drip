# Tasks: pd:doctor — Phase 1 Data Consistency Diagnostic

## Phase 1: Foundation (sequential)

### Task 1.1: Data Models + Tests
**File:** `plugins/pd/hooks/lib/doctor/models.py`, `plugins/pd/hooks/lib/doctor/__init__.py`, `plugins/pd/hooks/lib/doctor/test_checks.py`
**Do:**
1. Create `plugins/pd/hooks/lib/doctor/` package with `__init__.py` (empty stub)
2. Create `models.py` with 3 dataclasses:
   - `Issue(check, severity, entity, message, fix_hint)` — all str except entity/fix_hint which are `str | None`
   - `CheckResult(name, passed, issues, elapsed_ms, extras)` — extras: `dict` with `field(default_factory=dict)`
   - `DiagnosticReport(healthy, checks, total_issues, error_count, warning_count, elapsed_ms)`
3. Add `to_dict()` on each using `dataclasses.asdict()` — None → JSON null
4. Create `test_checks.py` with helpers (`_make_db`, `_register_feature`, `_create_meta_json`, `_make_memory_db`) and model tests
**Tests:** `test_check_result_passed_logic`, `test_diagnostic_report_healthy_aggregate`, `test_serialization_roundtrip`
**Done when:** `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -c "from doctor.models import Issue, CheckResult, DiagnosticReport; print('OK')"` succeeds AND 3 model tests pass
**Depends on:** none

### Task 1.2: Check 8 (DB Readiness) + Project-Scoping Utility + Tests
**File:** `plugins/pd/hooks/lib/doctor/checks.py`
**Do:**
1. Create `checks.py` with helper `_build_local_entity_set(artifacts_root) -> set[str]` — scans `{artifacts_root}/features/*/` dirs
2. Implement `check_db_readiness(entities_db_path, memory_db_path, **_) -> CheckResult`
3. Each lock test: open dedicated short-lived connection with `busy_timeout=2000`, `BEGIN IMMEDIATE`, immediate `ROLLBACK`, close
4. Schema version check (entity DB == 7) on separate read-only connection
5. WAL mode check on both DBs (read-only)
6. Return `extras={"entity_db_ok": bool, "memory_db_ok": bool}`
**Tests:** `test_check8_both_dbs_healthy`, `test_check8_entity_db_locked`, `test_check8_wrong_entity_schema_version`, `test_check8_non_wal_mode`, `test_check8_immediate_rollback_releases_lock`, `test_build_local_entity_set`
**Done when:** 6 tests pass
**Depends on:** 1.1

## Phase 2: Entity Checks (sequential — each builds on checks.py)

### Task 2.1: Check 1 (Feature Status) + Tests
**File:** `plugins/pd/hooks/lib/doctor/checks.py` (append)
**Do:**
1. Implement `check_feature_status(entities_conn, artifacts_root, **kwargs) -> CheckResult`
2. Extract `local_entity_ids = kwargs.get("local_entity_ids", set())` from ctx
3. Scan `{artifacts_root}/features/*/.meta.json` — try-parse each (report error on malformed JSON, don't crash)
4. Compare .meta.json `status` vs entity DB `entities.status` → error on mismatch
5. Missing from DB (local) → warning. Missing .meta.json (local) → warning
6. Cross-project filter: skip DB entities not in local_entity_ids
7. Hardening: null lastCompletedPhase with completed phase timestamps → warning
**Tests:** `test_check1_all_statuses_match`, `test_check1_status_mismatch_reports_error`, `test_check1_missing_from_db_warning`, `test_check1_malformed_meta_json_no_crash`, `test_check1_null_last_completed_phase`, `test_check1_cross_project_entity_no_warning`
**Done when:** 6 tests pass
**Depends on:** 1.2

### Task 2.2: Check 2 (Workflow Phase) + Tests
**File:** `plugins/pd/hooks/lib/doctor/checks.py` (append)
**Do:**
1. Implement `check_workflow_phase(entities_db_path, artifacts_root, **kwargs) -> CheckResult`
2. Construct `db = EntityDatabase(entities_db_path)`, `engine = WorkflowStateEngine(db, artifacts_root)` in try/finally (db.close()). Wrap in try/except `sqlite3.OperationalError` for hang mitigation.
3. Call `result = check_workflow_drift(engine, db, artifacts_root)` — signature: `check_workflow_drift(engine: WorkflowStateEngine, db: EntityDatabase, artifacts_root: str, feature_type_id: str | None = None) -> WorkflowDriftResult`. Translate each `WorkflowDriftReport` in `result.features` to Issues.
4. Backward transition awareness: use phase sequence from `workflow_engine.constants.PHASE_SEQUENCE` (or equivalent). Compare `PHASE_SEQUENCE.index(workflow_phase)` vs `PHASE_SEQUENCE.index(last_completed_phase)`. If former < latter → info "Feature in rework state"
5. Preserve drift direction: meta_json_ahead → error "Run reconcile_apply", db_ahead → error "DB has newer state", meta_json_only → warning, db_only → filter by local_entity_ids
6. Kanban drift: inspect report.mismatches for kanban_column entries on in_sync features → warning
**Tests:** `test_check2_in_sync_passes`, `test_check2_meta_json_ahead_fix_hint`, `test_check2_db_ahead_fix_hint`, `test_check2_kanban_only_drift_detected`, `test_backward_transition_not_error`, `test_cross_project_check2_db_only_skipped`
**Done when:** 6 tests pass
**Depends on:** 2.1

### Task 2.3: Check 3 (Brainstorm Status) + Tests
**File:** `plugins/pd/hooks/lib/doctor/checks.py` (append)
**Do:**
1. Implement `check_brainstorm_status(entities_conn, artifacts_root, **_) -> CheckResult`
2. For each brainstorm entity with status != "promoted": scan feature .meta.json for brainstorm_source refs → warning if completed feature references it
3. Fallback: check entity_dependencies for brainstorm→feature edges
4. Hardening: verify brainstorm_source file exists → warning if missing
**Tests:** `test_check3_no_promotion_needed`, `test_check3_brainstorm_should_be_promoted`, `test_check3_entity_deps_fallback`, `test_check3_brainstorm_source_missing`
**Done when:** 4 tests pass
**Depends on:** 2.2

### Task 2.4: Check 4 (Backlog Status) + Tests
**File:** `plugins/pd/hooks/lib/doctor/checks.py` (append)
**Do:**
1. Implement `check_backlog_status(entities_conn, artifacts_root, **_) -> CheckResult`
2. Parse `{artifacts_root}/backlog.md` for `(promoted →` annotations
3. Cross-ref entity DB backlog:{id} status → warning if annotated but entity not updated
4. Entity updated but not annotated → info
**Tests:** `test_check4_annotated_not_promoted`, `test_check4_backlog_missing_file_passes`, `test_check4_promoted_not_annotated_info`, `test_check4_empty_backlog_passes`
**Done when:** 4 tests pass
**Depends on:** 2.3

## Phase 3: Infrastructure Checks (sequential)

### Task 3.1: Check 5 (Memory Health) + Tests
**File:** `plugins/pd/hooks/lib/doctor/checks.py` (append)
**Do:**
1. Implement `check_memory_health(memory_conn, **_) -> CheckResult`
2. Sub-checks: schema_version==4, tables exist (entries, _metadata, influence_log), FTS5 table exists, 3 triggers exist, FTS row count vs entries row count (hardening), keywords=='[]' count (info), NULL embedding >10% (warning), length(embedding)!=3072 (error), WAL mode (warning)
**Tests:** `test_check5_healthy_memory_db`, `test_check5_memory_schema_wrong`, `test_check5_missing_fts_table`, `test_check5_missing_fts_trigger`, `test_check5_fts_row_count_divergence`, `test_check5_null_embedding_above_threshold`, `test_check5_wrong_embedding_dimension`, `test_check5_empty_keywords_info`, `test_check5_non_wal_mode`
**Done when:** 9 tests pass
**Depends on:** 2.4

### Task 3.2: Check 6 (Branch Consistency) + Tests
**File:** `plugins/pd/hooks/lib/doctor/checks.py` (append)
**Do:**
1. Implement `check_branch_consistency(entities_conn, artifacts_root, project_root, base_branch, **kwargs) -> CheckResult`
2. Verify base_branch via `git rev-parse --verify {base_branch}` → fallback to `origin/{base_branch}` → error if neither exists, skip remaining
3. For each active local feature: read branch from .meta.json, `git branch --list '{branch}'`
4. Active + no branch + merged (`git log --max-count=1`): check rework state via raw SQL on entities_conn: `SELECT workflow_phase, last_completed_phase FROM workflow_phases WHERE type_id = 'feature:{folder_name}'`. If phase index < last_completed index → warning "Create new branch for rework", otherwise → error "merged but active"
5. Active + no branch + not merged → warning
**Tests:** `test_check6_all_branches_exist`, `test_check6_base_branch_missing`, `test_check6_active_no_branch_not_merged_warning`, `test_check6_active_merged_not_rework_error`, `test_check6_remote_base_branch_fallback`
**Done when:** 5 tests pass
**Depends on:** 3.1

### Task 3.3: Check 7 (Entity Orphans) + Tests
**File:** `plugins/pd/hooks/lib/doctor/checks.py` (append)
**Do:**
1. Implement `check_entity_orphans(entities_conn, artifacts_root, **kwargs) -> CheckResult`
2. Cross-project safe: local entities with missing dirs → warning. Non-local entities → single aggregated info "N entities may belong to other projects"
3. Feature directories with .meta.json but no entity in DB → warning
4. Entities with artifact_path under project_root that doesn't exist → warning. Skip cross-project paths.
5. Brainstorm .prd.md without entity → warning
**Tests:** `test_check7_all_matched`, `test_check7_orphaned_local_entity`, `test_check7_directory_no_entity_warning`, `test_check7_orphaned_brainstorm_prd`, `test_cross_project_entity_info_not_warning`, `test_cross_project_entities_aggregated_info`
**Done when:** 6 tests pass
**Depends on:** 3.2

## Phase 4: Integrity & Config Checks (sequential)

### Task 4.1: Check 9 (Referential Integrity) + Tests
**File:** `plugins/pd/hooks/lib/doctor/checks.py` (append)
**Do:**
1. Implement `check_referential_integrity(entities_conn, **_) -> CheckResult`
2. Dangling parent_type_id → error
3. parent_uuid mismatch with parent_type_id entity → error
4. workflow_phases.type_id without entity → error
5. Self-referential parent → error
6. parent_type_id set but parent_uuid NULL → error (migration gap)
7. Circular parent chains: Python dict traversal with visited set, depth 20 → error if cycle, warning if depth limit reached on valid chain
8. entity_dependencies orphans (detection only) → warning
9. entity_tags orphans (detection only) → warning
**Tests:** `test_check9_valid_references`, `test_check9_dangling_parent_type_id`, `test_check9_parent_uuid_mismatch`, `test_check9_orphaned_workflow_phases`, `test_check9_self_referential_parent`, `test_check9_parent_uuid_null_with_type_id`, `test_check9_circular_parent_chain`, `test_check9_orphaned_dependency_row`, `test_check9_deep_chain_no_false_positive`, `test_check9_chain_at_depth_limit`
**Done when:** 10 tests pass
**Depends on:** 3.3

### Task 4.2: Check 10 (Config Validity) + Tests
**File:** `plugins/pd/hooks/lib/doctor/checks.py` (append)
**Do:**
1. Implement `check_config_validity(project_root, **kwargs) -> CheckResult`
2. Reuse `read_config()` from `semantic_memory.config`
3. Verify artifacts_root dir exists → error if missing
4. Memory weights sum to 1.0 (±0.01) → warning
5. Thresholds in [0.0, 1.0] → warning
6. Embedding provider set when semantic_enabled=true → warning
**Tests:** `test_check10_valid_config`, `test_check10_config_weights_sum`, `test_check10_artifacts_root_missing`, `test_check10_threshold_out_of_range`, `test_check10_missing_embedding_provider`, `test_check10_missing_config_file_uses_defaults`
**Done when:** 6 tests pass
**Depends on:** 4.1

## Phase 5: Integration (sequential)

### Task 5.1: Orchestrator + Tests
**File:** `plugins/pd/hooks/lib/doctor/__init__.py` (update from stub)
**Do:**
1. Implement `run_diagnostics(entities_db_path, memory_db_path, artifacts_root, project_root) -> DiagnosticReport`
2. Self-resolve: wrap `read_config(project_root)` in try/except → fallback base_branch="main"
3. Guard DB paths: `os.path.isfile(db_path)` before connect → error CheckResult if missing, don't create files
4. Build `local_entity_ids` via `_build_local_entity_set(artifacts_root)` → add to ctx
5. `CHECK_ORDER = [check_db_readiness, check_feature_status, check_workflow_phase, check_brainstorm_status, check_backlog_status, check_memory_health, check_branch_consistency, check_entity_orphans, check_referential_integrity, check_config_validity]`
6. Skip logic: read `check8_result.extras["entity_db_ok"]`/`["memory_db_ok"]` → sentinel CheckResults for locked-out checks
7. Per-check try/except → error CheckResult on uncaught exception
8. try/finally close connections. Close dedicated lock-test connections before opening read-only ones.
**Tests:** `test_report_has_10_checks`, `test_report_10_checks_even_when_locked`, `test_healthy_project_all_pass`, `test_info_issues_do_not_flip_passed`, `test_entity_db_lock_skips_dependent`, `test_memory_db_lock_skips_check5`, `test_per_check_exception_isolation`, `test_missing_db_file_no_create`, `test_base_branch_from_config`, `test_base_branch_default_main`, `test_check8_runs_first`, `test_both_dbs_locked`, `test_fresh_project_empty`, `test_works_without_mcp`, `test_connections_closed_on_success`, `test_connections_closed_on_exception`
**Done when:** 16 tests pass AND `run_diagnostics()` on live data returns 10 checks
**Depends on:** 4.2

### Task 5.2: CLI Entry Point + Tests
**File:** `plugins/pd/hooks/lib/doctor/__main__.py`
**Do:**
1. argparse: `--entities-db`, `--memory-db`, `--project-root` (required), `--artifacts-root` (optional)
2. Resolve artifacts_root: CLI arg > `read_config(project_root)["artifacts_root"]` > `"docs"`
3. Call `run_diagnostics()`, print `json.dumps(report.to_dict(), indent=2)` to stdout
4. Exit code 0 always
**Tests:** `test_cli_json_output_has_10_checks`, `test_cli_exit_code_always_zero`, `test_cli_json_structure_matches_model`, `test_cli_artifacts_root_cli_arg_precedence`, `test_cli_artifacts_root_config_fallback`, `test_cli_artifacts_root_default_docs`, `test_cli_none_serializes_as_json_null`
**Done when:** 7 tests pass AND CLI on live data outputs valid JSON
**Depends on:** 5.1

### Task 5.3: Command File
**File:** `plugins/pd/commands/doctor.md`
**Do:**
1. Frontmatter: `description: Run diagnostic checks on pd workspace health`
2. Plugin portability pattern (cache primary, dev workspace fallback)
3. Use `{pd_artifacts_root}` variable — NOT hardcoded `docs`
4. Venv-missing guard: output synthetic JSON error if neither venv found
5. Bash invocation → parse JSON → format as table: `Check | Status | Issues`
6. Show details for failed checks
7. Footer: "Doctor runs after session-start reconciliation. Issues here indicate problems that survived auto-repair."
**Done when:** Command file exists with frontmatter, portability pattern, and table format instructions
**Depends on:** 5.2

### Task 5.4: Documentation Sync
**Files:** `README.md`, `README_FOR_DEV.md`, `plugins/pd/README.md`
**Do:**
1. Add `doctor` to command tables in all 3 files
2. Add test command to README_FOR_DEV.md: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v`
3. Update component counts in plugins/pd/README.md
**Done when:** `grep -c 'doctor' README.md README_FOR_DEV.md plugins/pd/README.md` each returns ≥1
**Depends on:** 5.3
