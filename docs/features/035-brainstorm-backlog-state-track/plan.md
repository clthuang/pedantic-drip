# Plan: Brainstorm & Backlog State Tracking

## Implementation Order

The design specifies 9 components (C1-C9) with a dependency DAG. This plan sequences them into 8 tasks with TDD order (test infrastructure first, then implementation).

```
T1: Migration 5 (C1)
  ↓
T2: Error decorator + Constants (C2, C3)
  ↓
T3: init_entity_workflow MCP tool (C4)
  ↓
T4: transition_entity_phase MCP tool (C5)
  ↓
T5: Backfill update (C6)
  ↓
T6: UI card template + PHASE_COLORS (C7, C8)
  ↓
T7: Skill/command file updates (C9)
  ↓
T8: Integration verification
```

## Tasks

### T1: Migration 5 — Expand CHECK Constraint

**File:** `plugins/iflow/hooks/lib/entity_registry/database.py`

**Test first:**
- Add test in `plugins/iflow/hooks/lib/entity_registry/test_database.py` (or appropriate test file):
  - `test_migration_5_expands_check_constraint`: Create DB at schema v4, run migration, verify new phase values are accepted
  - `test_migration_5_preserves_existing_data`: Insert rows with feature phases, run migration, verify data intact
  - `test_migration_5_idempotent`: Run migration twice, verify no error

**Implement:**
1. Add `_expand_workflow_phase_check(conn)` function after `_create_fts_index`
2. Follow Migration 3 pattern: PRAGMA foreign_keys OFF, BEGIN IMMEDIATE, CREATE workflow_phases_new with expanded CHECK, copy data, drop old, rename, recreate trigger + indexes, COMMIT, PRAGMA foreign_keys ON, FK check
3. Expanded CHECK values: existing 7 feature phases + `draft`, `reviewing`, `promoted`, `abandoned`, `open`, `triaged`, `dropped`
4. Same expansion for `last_completed_phase` column
5. Add `5: _expand_workflow_phase_check` to `MIGRATIONS` dict (the `_migrate()` loop auto-discovers target version via `max(MIGRATIONS)` and writes `schema_version` to `_metadata` after each migration — no separate constant to bump)
6. Migration 3 writes `schema_version` inside its own transaction for crash safety. Follow same pattern: include `UPDATE _metadata SET value='5' WHERE key='schema_version'` inside the BEGIN IMMEDIATE / COMMIT block. This is intentional redundancy — the inner write provides crash safety within the transaction, the outer write in `_migrate()` (line 1431-1436) is the standard pattern. Both write the same value.

**Acceptance:** AC-DB-1 through AC-DB-4

**Depends on:** Nothing

### T2: Error Decorator + State Machine Constants

**File:** `plugins/iflow/mcp/workflow_state_server.py`

**Test first:**
- Add tests in `plugins/iflow/mcp/test_workflow_state_server.py`:
  - `test_catch_entity_value_error_entity_not_found`: Verify prefix routing
  - `test_catch_entity_value_error_invalid_entity_type`: Verify prefix routing
  - `test_catch_entity_value_error_invalid_transition`: Verify prefix routing
  - `test_catch_entity_value_error_unexpected_reraise`: Verify non-matching ValueError propagates
  - `test_entity_machines_brainstorm_transitions`: Verify brainstorm state machine structure
  - `test_entity_machines_backlog_transitions`: Verify backlog state machine structure
  - `test_entity_machines_columns_cover_all_phases`: Every phase in transitions appears in columns

**Implement:**
1. Add `ENTITY_MACHINES` constant after imports (per design C3)
2. Add `_ENTITY_RECOVERY_HINTS` dict
3. Add `_catch_entity_value_error` decorator after `_catch_value_error` (per design C2)

**Note:** Tests should verify against `_make_error` output format (dict with keys: `error`, `error_type`, `message`, `recovery_hint`). Verify `_make_error` signature at line ~311 before writing test assertions.

**Acceptance:** AC-ERR-1 through AC-ERR-4

**Depends on:** Nothing (can parallelize with T1 but same-file risk is low since different files)

### T3: `init_entity_workflow` MCP Tool

**File:** `plugins/iflow/mcp/workflow_state_server.py`

**Test first:**
- Add tests in `plugins/iflow/mcp/test_workflow_state_server.py`:
  - `test_init_entity_workflow_creates_row`: Happy path — entity exists, no workflow_phases row
  - `test_init_entity_workflow_idempotent`: Row already exists → returns existing values with `created: false`
  - `test_init_entity_workflow_entity_not_found`: Non-existent type_id → error response
  - `test_init_entity_workflow_validates_phase_against_machine`: Invalid phase for known entity type → error
  - `test_init_entity_workflow_validates_kanban_column_consistency`: Mismatched column → error
  - `test_init_entity_workflow_rejects_feature_entity_type`: Feature type_id → invalid_entity_type error (prevents conflict with feature workflow engine)
  - `test_init_entity_workflow_rejects_project_entity_type`: Project type_id → invalid_entity_type error

**Implement:**
1. Add `_process_init_entity_workflow` function (per design C4)
2. Register `init_entity_workflow` MCP tool with async wrapper

**Acceptance:** AC-REG-5 through AC-REG-8

**Depends on:** T1 (expanded CHECK), T2 (decorator + constants)

### T4: `transition_entity_phase` MCP Tool

**File:** `plugins/iflow/mcp/workflow_state_server.py`

**Test first:**
- Add tests in `plugins/iflow/mcp/test_workflow_state_server.py`:
  - `test_transition_brainstorm_draft_to_reviewing`: Valid forward transition
  - `test_transition_brainstorm_reviewing_to_promoted`: Terminal transition
  - `test_transition_brainstorm_reviewing_to_draft`: Backward transition (last_completed_phase unchanged)
  - `test_transition_backlog_open_to_triaged`: Valid forward transition
  - `test_transition_backlog_triaged_to_promoted`: Terminal transition
  - `test_transition_invalid_from_terminal`: promoted/abandoned/dropped → error
  - `test_transition_feature_entity_rejected`: feature type_id → invalid_entity_type error
  - `test_transition_entity_not_found`: Non-existent type_id → error
  - `test_transition_null_current_phase_error`: NULL workflow_phase → clear error message
  - `test_transition_updates_entities_status`: Verify entities.status is updated alongside workflow_phases
  - `test_transition_forward_sets_last_completed_phase`: Forward transition updates last_completed_phase
  - `test_transition_backward_preserves_last_completed_phase`: Backward transition does not update

**Implement:**
1. Add `_process_transition_entity_phase` function (per design C5)
2. Register `transition_entity_phase` MCP tool with async wrapper

**Acceptance:** AC-MCP-1 through AC-MCP-6

**Depends on:** T1 (expanded CHECK), T2 (decorator + constants). Test fixtures use direct SQL INSERT to create workflow_phases rows — no runtime dependency on T3.

### T5: Backfill Update

**File:** `plugins/iflow/hooks/lib/entity_registry/backfill.py`

**Test first:**
- Add tests in `plugins/iflow/hooks/lib/entity_registry/test_backfill.py` (or appropriate test file):
  - `test_backfill_brainstorm_no_row_creates_draft`: No workflow_phases row → INSERT with draft/wip
  - `test_backfill_backlog_no_row_creates_open`: No workflow_phases row → INSERT with open/backlog
  - `test_backfill_brainstorm_nonnull_phase_skipped`: Existing row with workflow_phase='reviewing' → skip
  - `test_backfill_brainstorm_null_phase_updated`: Existing row with NULL workflow_phase → UPDATE to draft/wip
  - `test_backfill_backlog_null_phase_updated`: Existing row with NULL workflow_phase → UPDATE to open/backlog
  - `test_backfill_child_completion_override_preserved`: Brainstorm with all completed children → kanban_column='completed'
  - `test_backfill_returns_updated_counter`: Return dict includes `updated` key

**Implement:**

**Insertion point:** Add an early-exit guard **before** the STATUS_TO_KANBAN lookup (before line 200). STATUS_TO_KANBAN runs before the feature block, so brainstorm/backlog entities with statuses like `"draft"` would get spurious warnings if they reached it. The early-exit guard handles all 3 cases and `continue`s, preventing brainstorm/backlog from reaching STATUS_TO_KANBAN or the feature block:

```python
# Early handling for brainstorm/backlog — skip STATUS_TO_KANBAN
if entity_type in ("brainstorm", "backlog"):
    # Child-completion override (moved here from general block)
    kanban_column = None  # will be set below
    children = [
        e for e in all_entities
        if e.get("parent_type_id") == type_id
        and e["entity_type"] == "feature"
    ]
    all_children_completed = children and all(
        c.get("status") == "completed" for c in children
    )

    # Check existing workflow_phases row
    existing_row = db._conn.execute(
        "SELECT workflow_phase FROM workflow_phases WHERE type_id = ?",
        (type_id,)
    ).fetchone()

    if existing_row and existing_row["workflow_phase"] is not None:
        skipped += 1
        continue

    # Derive defaults
    if entity_type == "brainstorm":
        workflow_phase = "draft"
        kanban_column = "wip"
    else:
        workflow_phase = "open"
        kanban_column = "backlog"

    # Apply child-completion override
    if all_children_completed:
        kanban_column = "completed"

    # Case 3: existing row with NULL phase → UPDATE
    if existing_row and existing_row["workflow_phase"] is None:
        db._conn.execute(
            "UPDATE workflow_phases SET workflow_phase = ?, kanban_column = ?, "
            "updated_at = ? WHERE type_id = ?",
            (workflow_phase, kanban_column, db._now_iso(), type_id),
        )
        updated += 1
        continue

    # Case 1: no row → INSERT inline (do NOT fall through — subsequent
    # code would overwrite workflow_phase/kanban_column via STATUS_TO_KANBAN)
    cursor = db._conn.execute(
        "INSERT OR IGNORE INTO workflow_phases "
        "(type_id, kanban_column, workflow_phase, "
        "last_completed_phase, mode, "
        "backward_transition_reason, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (type_id, kanban_column, workflow_phase, None, None, None, db._now_iso()),
    )
    if cursor.rowcount > 0:
        created += 1
    else:
        skipped += 1  # concurrent insert won the race
    continue
```

All three cases `continue` — brainstorm/backlog entities never reach STATUS_TO_KANBAN or the feature block. No per-entity `commit()` inside the guard — all changes are committed by the existing bulk `db._conn.commit()` at the end of the function (matching the established pattern).

1. Add early-exit guard for brainstorm/backlog BEFORE STATUS_TO_KANBAN (line ~200)
2. Move child-completion override logic INTO the early-exit guard
3. All 3 cases `continue` inside the guard: (1) non-null phase → skip, (2) null phase → UPDATE, (3) no row → INSERT
4. Add `updated` counter to return dict
5. Remove the old child-completion block (lines 210-221) — it only applied to brainstorm/backlog. Projects are unaffected (line 212 guard was `if entity_type in ("brainstorm", "backlog")` — projects never matched it).
6. Before implementing, grep for callers of `backfill_workflow_phases` to verify adding `updated` key won't break any destructuring assertions

**Acceptance:** AC-BF-1 through AC-BF-4

**Depends on:** T1 (expanded CHECK for new phase values)

### T6: UI Card Template + PHASE_COLORS

**Files:** `plugins/iflow/ui/templates/_card.html`, `plugins/iflow/ui/__init__.py`

**Test first:**
- Update `plugins/iflow/ui/tests/test_filters.py`:
  - `test_phase_colors_match_db_check_constraint`: Add 7 new phase values to expected set
- Add tests:
  - `test_card_feature_renders_mode_badge`: Feature entity shows mode badge
  - `test_card_brainstorm_renders_type_badge`: Brainstorm entity shows "brainstorm" type badge, no mode badge
  - `test_card_backlog_renders_type_badge`: Backlog entity shows "backlog" type badge
  - `test_card_project_renders_type_badge`: Project entity shows "project" type badge
  - `test_card_feature_shows_last_completed_phase`: Feature shows last_completed_phase
  - `test_card_brainstorm_hides_last_completed_phase`: Non-feature hides last_completed_phase

**Implement:**
1. Expand `PHASE_COLORS` dict with 7 new phases (per design C8)
2. Replace `_card.html` with entity-type-aware template (per design C7):
   - Extract entity_type via `item.type_id.split(':')[0]`
   - Conditional badges: mode for features, type badge for brainstorm/backlog/project
   - last_completed_phase only for features

**Acceptance:** AC-UI-1 through AC-UI-5

**Depends on:** Soft dependency on T1 — PHASE_COLORS test values must align with T1's expanded CHECK constraint values. Implement T1 first or verify phase values match.

### T7: Skill/Command File Updates

**Files:**
- `plugins/iflow/skills/brainstorming/SKILL.md`
- `plugins/iflow/commands/add-to-backlog.md`

**No automated tests** — these are prompt files, not code. Verification is manual/integration.

**Implement:**
1. **Brainstorming SKILL.md:**
   - Stage 3: After `register_entity`, add `init_entity_workflow` call with `workflow_phase="draft"`, `kanban_column="wip"`
   - Stage 4 entry: Add `transition_entity_phase` call to advance to `reviewing`
   - Stage 6 "Promote to Feature": Add `transition_entity_phase` to `promoted`
   - Stage 6 "Refine Further": Add `transition_entity_phase` to `draft`
   - Backlog reference handling: 3-step sequence (register → init_workflow → transition to triaged)
   - All MCP calls wrapped in warn-but-don't-block error handling

2. **Add-to-backlog command:**
   - After markdown row append: `register_entity` + `init_entity_workflow` calls
   - Error handling: warn but don't block markdown creation

**Acceptance:** Skill/command changes per design C9

**Depends on:** T3, T4 (MCP tools must exist for the calls to work at runtime)

### T8: Integration Verification

**No new code.** Run all existing test suites to confirm no regressions.

**T7 verification checklist:**
1. Review brainstorming SKILL.md: verify `init_entity_workflow` call present in Stage 3, `transition_entity_phase` calls in Stage 4 and Stage 6
2. Review add-to-backlog.md: verify `register_entity` + `init_entity_workflow` calls present after markdown row append
3. Verify all MCP calls have warn-but-don't-block error handling wrappers
4. Verify backlog reference handling has the 3-step sequence (register → init_workflow → transition)

**Commands:**
```bash
# Entity registry tests (667+ tests)
plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v

# Workflow engine tests (289 tests)
plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/ -v

# Transition gate tests (257 tests)
plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/ -v

# Workflow state MCP server tests (146+ tests)
plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v

# UI server tests (178+ tests)
PYTHONPATH="plugins/iflow/hooks/lib:plugins/iflow" plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/ -v

# Reconciliation tests (103 tests)
plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_reconciliation.py -v

# Hook guard audit (manual review of 4 hooks per spec)
```

**Acceptance:** AC-HOOK-1, AC-HOOK-2, all existing test suites pass

**Depends on:** T1-T7 complete

## Risk Mitigations

| Risk | Mitigation | Task |
|------|-----------|------|
| R1: Phase name collision | Phase names stored with type_id; PHASE_COLORS shared colors intentional | T6 |
| R2: Backfill race with MCP | Pre-check SELECT prevents overwriting; backfill runs before MCP available | T5 |
| R3: Orphaned workflow_phases | Backfill creates missing rows; board handles entities without rows | T5, T8 |

## Scope Guard

- Do NOT modify `WorkflowStateEngine`, `transition_gate/`, or existing `_process_*` functions
- Do NOT add `.meta.json` files for brainstorms or backlogs
- Do NOT add hook enforcement for brainstorm/backlog transitions
- Do NOT add board filtering by entity type
- Do NOT modify `entity_detail.html` (v1 acceptable — null rendering works)
