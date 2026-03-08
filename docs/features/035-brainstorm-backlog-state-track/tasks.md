# Tasks: Brainstorm & Backlog State Tracking

## Phase 1: DB Foundation (T1)

### 1.1 Write Migration 5 tests
- [ ] **File:** `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- [ ] Add `test_migration_5_expands_check_constraint`: Create DB at v4, run migration, INSERT row with `workflow_phase='draft'` — verify no CHECK violation
- [ ] Add `test_migration_5_preserves_existing_data`: INSERT row with `workflow_phase='implement'` at v4, run migration, verify row intact
- [ ] Add `test_migration_5_idempotent`: Create DB (runs all migrations), verify schema_version=5 and new phase values accepted
- [ ] **Done when:** All 3 tests fail (RED phase — migration not yet written)

### 1.2 Implement Migration 5
- [ ] **File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
- [ ] Add `_expand_workflow_phase_check(conn)` function after `_create_fts_index` (line ~396)
- [ ] Pattern: PRAGMA foreign_keys OFF → BEGIN IMMEDIATE → PRAGMA foreign_key_check → CREATE workflow_phases_new (expanded CHECK) → INSERT SELECT → DROP old → RENAME → recreate trigger `enforce_immutable_wp_type_id` → recreate indexes `idx_wp_kanban_column`, `idx_wp_workflow_phase` → UPDATE _metadata schema_version=5 → COMMIT → PRAGMA foreign_keys ON → PRAGMA foreign_key_check
- [ ] CHECK values for `workflow_phase`: `'brainstorm','specify','design','create-plan','create-tasks','implement','finish','draft','reviewing','promoted','abandoned','open','triaged','dropped'` OR NULL
- [ ] Same CHECK expansion for `last_completed_phase`
- [ ] Add `5: _expand_workflow_phase_check` to `MIGRATIONS` dict (line ~404)
- [ ] **Done when:** All 3 tests from 1.1 pass (GREEN)

### 1.3 Run entity registry tests
- [ ] `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- [ ] **Done when:** All existing + new tests pass, zero failures

## Phase 2: MCP Infrastructure (T2)

### 2.1 Write ENTITY_MACHINES constant tests
- [ ] **File:** `plugins/iflow/mcp/test_workflow_state_server.py`
- [ ] Add `test_entity_machines_brainstorm_transitions`: Assert `ENTITY_MACHINES["brainstorm"]["transitions"]` has keys `draft`, `reviewing` with correct target lists
- [ ] Add `test_entity_machines_backlog_transitions`: Assert `ENTITY_MACHINES["backlog"]["transitions"]` has keys `open`, `triaged` with correct target lists
- [ ] Add `test_entity_machines_columns_cover_all_phases`: For each entity type, every phase appearing in `transitions` (both keys and values) also appears in `columns`
- [ ] **Done when:** Tests fail (RED — constant not yet added)

### 2.2 Implement ENTITY_MACHINES constant
- [ ] **File:** `plugins/iflow/mcp/workflow_state_server.py`
- [ ] Add `ENTITY_MACHINES` dict after imports, before helper functions (per design C3)
- [ ] Brainstorm: transitions `{draft: [reviewing, abandoned], reviewing: [promoted, draft, abandoned]}`, columns `{draft: wip, reviewing: agent_review, promoted: completed, abandoned: completed}`, forward set
- [ ] Backlog: transitions `{open: [triaged, dropped], triaged: [promoted, dropped]}`, columns `{open: backlog, triaged: prioritised, promoted: completed, dropped: completed}`, forward set
- [ ] **Done when:** Tests from 2.1 pass (GREEN)

### 2.3 Write error decorator tests
- [ ] **File:** `plugins/iflow/mcp/test_workflow_state_server.py`
- [ ] Verify `_make_error` signature at line ~311 returns dict with keys: `error`, `error_type`, `message`, `recovery_hint`
- [ ] Add `test_catch_entity_value_error_entity_not_found`: Decorated function raises `ValueError("entity_not_found: foo")` → returns error dict with `error_type="entity_not_found"`
- [ ] Add `test_catch_entity_value_error_invalid_entity_type`: `ValueError("invalid_entity_type: ...")` → `error_type="invalid_entity_type"`
- [ ] Add `test_catch_entity_value_error_invalid_transition`: `ValueError("invalid_transition: ...")` → `error_type="invalid_transition"`
- [ ] Add `test_catch_entity_value_error_unexpected_reraise`: `ValueError("some_other: ...")` → re-raises (not caught)
- [ ] **Done when:** Tests fail (RED)

### 2.4 Implement error decorator + recovery hints
- [ ] **File:** `plugins/iflow/mcp/workflow_state_server.py`
- [ ] Add `_ENTITY_RECOVERY_HINTS` dict after `_catch_value_error` (line ~367)
- [ ] Add `_catch_entity_value_error` decorator: sync `def wrapper`, iterates 3 prefixes, calls `_make_error(error_type, message, recovery_hint)` on match (uses existing `_make_error` function — NOT a direct dict), re-raises unmatched
- [ ] Stacking order: `@_with_error_handling` (outer) → `@_catch_entity_value_error` (inner)
- [ ] **Done when:** Tests from 2.3 pass (GREEN)

### 2.5 Run workflow state server tests
- [ ] `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v`
- [ ] **Done when:** All existing + new tests pass, zero failures

## Phase 3: MCP Tools (T3, T4)

### 3.1 Write init_entity_workflow tests
- [ ] **File:** `plugins/iflow/mcp/test_workflow_state_server.py`
- [ ] Add `test_init_entity_workflow_creates_row`: Register brainstorm entity, call init, verify workflow_phases row created with correct phase/column
- [ ] Add `test_init_entity_workflow_idempotent`: Call init twice, second returns `created: false` with existing values
- [ ] Add `test_init_entity_workflow_entity_not_found`: Non-existent type_id → `error_type="entity_not_found"`
- [ ] Add `test_init_entity_workflow_validates_phase_against_machine`: Call with `workflow_phase="invalid"` for brainstorm → `error_type="invalid_transition"`
- [ ] Add `test_init_entity_workflow_validates_kanban_column_consistency`: Call with `kanban_column="wrong"` for brainstorm draft → `error_type="invalid_transition"`
- [ ] Add `test_init_entity_workflow_rejects_feature_entity_type`: Feature type_id → `error_type="invalid_entity_type"`
- [ ] Add `test_init_entity_workflow_rejects_project_entity_type`: Project type_id → `error_type="invalid_entity_type"`
- [ ] **Done when:** Tests fail (RED)

### 3.2 Implement _process_init_entity_workflow + register MCP tool
- [ ] **File:** `plugins/iflow/mcp/workflow_state_server.py`
- [ ] Add `_process_init_entity_workflow(db, type_id, workflow_phase, kanban_column)` per design C4
- [ ] Step 1: `db.get_entity(type_id)` — raise `entity_not_found` if None
- [ ] Step 1b: Reject feature/project entity types → raise `invalid_entity_type`
- [ ] Step 1b: If entity_type in ENTITY_MACHINES: if workflow_phase not in columns → raise `ValueError("invalid_transition: workflow_phase {phase} not valid for {entity_type}")`; if kanban_column != columns[workflow_phase] → raise `ValueError("invalid_transition: kanban_column {col} inconsistent with workflow_phase {phase}")`
- [ ] Step 2: SELECT existing row — if exists, return `created: false` with existing values
- [ ] Step 3: INSERT row, commit, return `created: true`
- [ ] Apply decorators: `@_with_error_handling` outer, `@_catch_entity_value_error` inner
- [ ] Add `@mcp.tool()` async wrapper: `async def init_entity_workflow(type_id, workflow_phase, kanban_column) -> str`
- [ ] Check `_db is None` → return `_NOT_INITIALIZED`
- [ ] Delegate to `_process_init_entity_workflow(_db, ...)`
- [ ] **Done when:** Tests from 3.1 pass (GREEN)

### 3.3 Write transition_entity_phase tests
- [ ] **File:** `plugins/iflow/mcp/test_workflow_state_server.py`
- [ ] Test fixtures: use direct SQL INSERT to create workflow_phases rows (no T3 dependency)
- [ ] Add `test_transition_brainstorm_draft_to_reviewing`: Forward, returns `transitioned: true`, kanban_column updated to `agent_review`
- [ ] Add `test_transition_brainstorm_reviewing_to_promoted`: Terminal forward, kanban_column → `completed`
- [ ] Add `test_transition_brainstorm_reviewing_to_draft`: Backward — `last_completed_phase` NOT updated
- [ ] Add `test_transition_backlog_open_to_triaged`: Forward, kanban_column → `prioritised`
- [ ] Add `test_transition_backlog_triaged_to_promoted`: Terminal forward, kanban_column → `completed`
- [ ] Add `test_transition_invalid_from_terminal`: Try promoted→anything → `invalid_transition`
- [ ] Add `test_transition_feature_entity_rejected`: feature:xxx type_id → `invalid_entity_type`
- [ ] Add `test_transition_entity_not_found`: Non-existent type_id → `entity_not_found`
- [ ] Add `test_transition_null_current_phase_error`: Row with NULL workflow_phase → `invalid_transition` with "call init_entity_workflow first"
- [ ] Add `test_transition_updates_entities_status`: After transition, `entities.status` matches target_phase
- [ ] Add `test_transition_forward_sets_last_completed_phase`: After draft→reviewing, `last_completed_phase='draft'`
- [ ] Add `test_transition_backward_preserves_last_completed_phase`: After reviewing→draft, `last_completed_phase` unchanged
- [ ] Add `test_transition_brainstorm_draft_to_abandoned`: Valid direct-to-terminal from initial state
- [ ] Add `test_transition_backlog_open_to_dropped`: Valid direct-to-terminal from initial state
- [ ] **Done when:** Tests fail (RED)

### 3.4 Implement _process_transition_entity_phase + register MCP tool
- [ ] **File:** `plugins/iflow/mcp/workflow_state_server.py`
- [ ] Add `_process_transition_entity_phase(db, type_id, target_phase)` per design C5
- [ ] Steps: parse entity_type → validate in ENTITY_MACHINES → get_entity → SELECT current_phase → check NULL → validate transition → lookup kanban_column → check forward → UPDATE entities.status → UPDATE workflow_phases → commit
- [ ] Apply decorators: `@_with_error_handling` outer, `@_catch_entity_value_error` inner
- [ ] Add `@mcp.tool()` async wrapper: `async def transition_entity_phase(type_id, target_phase) -> str`
- [ ] Check `_db is None` → return `_NOT_INITIALIZED`
- [ ] Delegate to `_process_transition_entity_phase(_db, ...)`
- [ ] **Done when:** Tests from 3.3 pass (GREEN)

### 3.5 Run full MCP server tests
- [ ] `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v`
- [ ] **Done when:** All existing + new tests pass, zero failures

## Phase 4: Backfill (T5)

### 4.1 Grep backfill callers for return dict safety
- [ ] `grep -rn 'backfill_workflow_phases' plugins/iflow/` — identify all callers
- [ ] Verify callers use `dict.get()` or don't destructure exact keys
- [ ] **Done when:** Confirmed adding `updated` key is safe

### 4.2 Verify child-completion block scope
- [ ] Read lines 210-221 of `backfill.py` — confirm guard is `if entity_type in ("brainstorm", "backlog")`
- [ ] Confirm projects never match this guard
- [ ] **Done when:** Confirmed safe to remove and replace

### 4.3 Write backfill tests
- [ ] **File:** `plugins/iflow/hooks/lib/entity_registry/test_backfill.py` (exists)
- [ ] Add `test_backfill_brainstorm_no_row_creates_draft`: Brainstorm entity, no workflow_phases row → INSERT with workflow_phase='draft', kanban_column='wip'
- [ ] Add `test_backfill_backlog_no_row_creates_open`: Backlog entity → INSERT with workflow_phase='open', kanban_column='backlog'
- [ ] Add `test_backfill_brainstorm_nonnull_phase_skipped`: Existing row with workflow_phase='reviewing' → skipped, not overwritten
- [ ] Add `test_backfill_brainstorm_null_phase_updated`: Existing row with NULL workflow_phase → UPDATE to draft/wip
- [ ] Add `test_backfill_backlog_null_phase_updated`: Existing row with NULL workflow_phase → UPDATE to open/backlog
- [ ] Add `test_backfill_child_completion_override_preserved`: Brainstorm with all completed child features → kanban_column='completed' (overrides 'wip')
- [ ] Add `test_backfill_returns_updated_counter`: Return dict includes `updated` key with correct count
- [ ] **Done when:** Tests fail (RED)

### 4.4 Implement backfill early-exit guard
- [ ] **File:** `plugins/iflow/hooks/lib/entity_registry/backfill.py`
- [ ] Add `updated = 0` counter initialization alongside existing `created`/`skipped`
- [ ] Add `if entity_type in ("brainstorm", "backlog"):` guard BEFORE STATUS_TO_KANBAN lookup (before line ~200). **Note:** plan.md takes precedence over design.md C6 for insertion point — use early-exit guard BEFORE STATUS_TO_KANBAN, not after the feature block
- [ ] Inside guard: child-completion override, existing row check, 3-case logic (skip/UPDATE/INSERT), all `continue`
- [ ] Remove old child-completion block (lines 210-221) — confirmed brainstorm/backlog only in 4.2
- [ ] Add `updated` to return dict
- [ ] **Done when:** Tests from 4.3 pass (GREEN)

### 4.5 Run backfill + entity registry tests
- [ ] `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- [ ] **Done when:** All existing + new tests pass, zero failures

## Phase 5: UI (T6)

### 5.1 Write PHASE_COLORS test update
- [ ] **File:** `plugins/iflow/ui/tests/test_filters.py`
- [ ] Update `test_phase_colors_match_db_check_constraint`: Add 7 values to expected set: `draft`, `reviewing`, `promoted`, `abandoned`, `open`, `triaged`, `dropped`
- [ ] **Done when:** Test fails (RED — PHASE_COLORS not yet expanded)

### 5.2 Write card template tests
- [ ] **File:** `plugins/iflow/ui/tests/test_deepened_app.py`
- [ ] Add `test_card_feature_renders_mode_badge`: Feature entity with mode → HTML contains mode badge
- [ ] Add `test_card_brainstorm_renders_type_badge`: Brainstorm entity → HTML contains "brainstorm" badge, no mode badge
- [ ] Add `test_card_backlog_renders_type_badge`: Backlog entity → HTML contains "backlog" badge
- [ ] Add `test_card_project_renders_type_badge`: Project entity → HTML contains "project" badge
- [ ] Add `test_card_feature_shows_last_completed_phase`: Feature with last_completed_phase → HTML contains "last:" text
- [ ] Add `test_card_brainstorm_hides_last_completed_phase`: Brainstorm entity → HTML does NOT contain "last:" text
- [ ] Add `test_card_brainstorm_null_phase_shows_no_phase_badge`: Brainstorm entity with workflow_phase=None → HTML does NOT contain a phase badge element (AC-UI-5)
- [ ] **Done when:** Tests fail (RED)

### 5.3 Implement PHASE_COLORS expansion
- [ ] **File:** `plugins/iflow/ui/__init__.py`
- [ ] Add 7 entries: `draft: badge-info`, `reviewing: badge-secondary`, `promoted: badge-success`, `abandoned: badge-neutral`, `open: badge-ghost`, `triaged: badge-info`, `dropped: badge-neutral`
- [ ] **Done when:** Test from 5.1 passes (GREEN)

### 5.4 Implement entity-type-aware card template
- [ ] **File:** `plugins/iflow/ui/templates/_card.html`
- [ ] Add `{% set entity_type = item.type_id.split(':')[0] if ':' in item.type_id else 'unknown' %}`
- [ ] Show workflow_phase badge for all entities (existing)
- [ ] Show mode badge only for `entity_type == 'feature'`
- [ ] Show type badge (brainstorm/backlog/project) for non-feature entities
- [ ] Show last_completed_phase only for `entity_type == 'feature'`
- [ ] **Done when:** Tests from 5.2 pass (GREEN)

### 5.5 Run UI tests
- [ ] `PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/ -v`
- [ ] **Done when:** All existing + new tests pass, zero failures

## Phase 6: Skill/Command Updates (T7)

### 6.1 Update brainstorming SKILL.md — Stage 3
- [ ] **File:** `plugins/iflow/skills/brainstorming/SKILL.md`
- [ ] After `register_entity` call in Stage 3 Entity Registration, add `init_entity_workflow(type_id="brainstorm:{stem}", workflow_phase="draft", kanban_column="wip")`
- [ ] Wrap in error handling: `If MCP call fails, warn "Workflow init failed: {error}" but do NOT block brainstorm creation.`
- [ ] **Done when:** Stage 3 contains init_entity_workflow call with error handling

### 6.2 Update brainstorming SKILL.md — Stage 4
- [ ] Before dispatching prd-reviewer, add `transition_entity_phase(type_id="brainstorm:{stem}", target_phase="reviewing")`
- [ ] Wrap in error handling: warn but don't block
- [ ] **Done when:** Stage 4 contains transition call

### 6.3 Update brainstorming SKILL.md — Stage 6 decisions
- [ ] "Promote to Feature": Add `transition_entity_phase(type_id="brainstorm:{stem}", target_phase="promoted")` before invoking create-feature
- [ ] "Promote to Feature": If brainstorm references a backlog item, also call `transition_entity_phase(type_id="backlog:{id}", target_phase="promoted")` after the brainstorm transition
- [ ] "Refine Further": Add `transition_entity_phase(type_id="brainstorm:{stem}", target_phase="draft")` before looping back
- [ ] Wrap all in error handling: warn but don't block
- [ ] **Done when:** Stage 6 handlers contain: (1) brainstorm→promoted transition, (2) backlog→promoted transition in "Promote to Feature", (3) brainstorm→draft transition in "Refine Further", all with error handling

### 6.4 Update brainstorming SKILL.md — backlog reference handling
- [ ] In Stage 3 Entity Registration, after backlog entity registration:
  1. `register_entity(entity_type="backlog", entity_id="{id}", ...)` — swallow duplicate error
  2. `init_entity_workflow(type_id="backlog:{id}", workflow_phase="open", kanban_column="backlog")` — idempotent
  3. `transition_entity_phase(type_id="backlog:{id}", target_phase="triaged")` — warn on failure
- [ ] **Note:** `init_entity_workflow` is idempotent — if `add-to-backlog` already created the workflow_phases row, the second call returns `created: false` without error
- [ ] **Done when:** 3-step sequence present with error handling

### 6.5 Update add-to-backlog command
- [ ] **File:** `plugins/iflow/commands/add-to-backlog.md`
- [ ] After markdown row append, add:
  1. `register_entity(entity_type="backlog", entity_id="{5-digit-id}", name="{description}", artifact_path="{artifacts_root}/backlog.md", status="open")`
  2. `init_entity_workflow(type_id="backlog:{5-digit-id}", workflow_phase="open", kanban_column="backlog")`
- [ ] Wrap in error handling: `If MCP call fails, warn "Entity registration failed: {error}" but do NOT block backlog creation.`
- [ ] **Done when:** Command contains register_entity + init_entity_workflow with error handling. Verify AC-REG-1 (markdown row + entity entry), AC-REG-2 (workflow_phases row with open/backlog), AC-REG-3 (failure non-blocking), AC-REG-4 (type_id format backlog:NNNNN)

## Phase 7: Integration Verification (T8)

### 7.1 Run all test suites
- [ ] Entity registry: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- [ ] Workflow engine: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/ -v`
- [ ] Transition gate: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/ -v`
- [ ] MCP server: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v`
- [ ] UI: `PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/ -v`
- [ ] Reconciliation: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_reconciliation.py -v`
- [ ] **Done when:** All suites pass with zero failures

### 7.2 T7 manual verification
- [ ] Review SKILL.md: `init_entity_workflow` in Stage 3, `transition_entity_phase` in Stage 4 and Stage 6
- [ ] Review add-to-backlog.md: `register_entity` + `init_entity_workflow` after row append
- [ ] All MCP calls have warn-but-don't-block error handling
- [ ] Backlog reference handling has 3-step sequence (register → init_workflow → transition to triaged)
- [ ] Backlog promotion transition present in Stage 6 "Promote to Feature" handler
- [ ] **Done when:** All 4 checks pass

### 7.3 Hook guard audit
- [ ] Read `plugins/iflow/hooks/meta-json-guard.sh` — confirm triggers on `.meta.json` paths only (brainstorms/backlogs have none)
- [ ] Read `plugins/iflow/hooks/pre-commit-guard.sh` — confirm entity-type-agnostic
- [ ] Read `plugins/iflow/hooks/yolo-guard.sh` — confirm entity-type-agnostic
- [ ] Read `plugins/iflow/hooks/pre-exit-plan-review.sh` — confirm entity-type-agnostic
- [ ] **Done when:** All 4 hooks confirmed safe (AC-HOOK-1)
