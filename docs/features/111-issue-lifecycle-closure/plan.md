# Plan — Feature 111: Issue Lifecycle Closure

- **Spec:** spec.md rev 3.4
- **Design:** design.md rev 2.3
- **Status:** revision 1
- **Mode:** standard

## §1 Strategy

5 implementation groups with **strict A → B → {C ∥ D ∥ E}** ordering. Group A is DDL-only (atomic-commit-discipline per NFR-1). Group B ships all Python constants + exception classes + helper methods + tests; this is what C/D/E depend on. Groups C, D, E run in parallel worktrees once B is merged.

**TDD ordering:** Implementer-skill executes RED-tests-first regardless of in-group task order. Every Group's "test" task block describes the test surface; implementer writes failing tests first, then production code.

**Commit boundary:** One commit per Group. Group A ships migration code only (no Python logic); Group B ships all Python constants, exception classes, helpers, and migration tests (since tests reference Group B symbols).

**Same-PR constraint:** Group A and Group B MUST land in the same PR. Splitting them creates a partial-deploy window. Implementer queues both commits before pushing to develop.

## §2 Dependency Graph

```
       ┌─────────────────────────────────────────────┐
       │  Group A — Migration 14 (DDL only)          │
       │  database.py:                               │
       │   • _migration_14_issue_lifecycle_closure   │
       │   • MIGRATIONS[14], MIGRATIONS_DOWN[14]     │
       │   • _copy_rename helpers (up + down)        │
       └─────────────────────────────────────────────┘
                            │
                            ▼
       ┌─────────────────────────────────────────────┐
       │  Group B — Discriminator/constants/helpers  │
       │   • _KIND_TO_TYPE_LIFECYCLE += {bug, task}  │
       │   • _VALID_PARAMS += {spawned_child}        │
       │   • _CLOSES_TERMINAL = {...}                │
       │   • VALID_ENTITY_TYPES += 'bug'             │
       │   • Exception classes (IF-9)                │
       │   • 4 new EntityDatabase helpers (C11)      │
       │   • transition_entity_phase defensive raise │
       │   • test_migration_14_safety.py +           │
       │     test_status_only_lifecycle.py +         │
       │     test_entity_lifecycle.py extensions     │
       └─────────────────────────────────────────────┘
            │              │              │
            ▼              ▼              ▼
       ┌───────────┐  ┌───────────┐  ┌───────────┐
       │ Group C   │  │ Group D   │  │ Group E   │
       │ issue_    │  │ complete_ │  │ Cleanup + │
       │ spawn MCP │  │ phase     │  │ new       │
       │           │  │ closes=   │  │ doctor    │
       │           │  │           │  │ check     │
       └───────────┘  └───────────┘  └───────────┘
```

**No conflicts between C/D/E:** C touches `entity_server.py`; D touches `workflow_state_server.py`; E touches `entity_registry/backfill.py` + `doctor/checks.py` + `doctor/__init__.py`. Each Group creates distinct test files.

## §3 Group-Level Plan

### Group A — Migration 14 (DDL only)

**Goal:** Schema migration adding `entity_relations` table, widening `entities` (type, kind) CHECK to admit `'bug'`, widening `phase_events` event_type CHECK to admit `'spawned_child'`, remapping any kind='task' rows to `lifecycle_class='task_flow'`. Down-migration with pre-flight refuses on bug entities or relation rows.

**Files:** `plugins/pd/hooks/lib/entity_registry/database.py` only.

**Functions added:**
- `_migration_14_issue_lifecycle_closure(conn)` — main up-migration body.
- `_copy_rename_entities_for_v14(conn)` — entities CHECK widening copy-rename helper.
- `_copy_rename_phase_events_for_v14(conn)` — phase_events CHECK widening copy-rename helper.
- `_migration_14_down(conn)` — down-migration with pre-flight refuse.
- `_copy_rename_entities_to_v13(conn)` — entities CHECK narrowing helper.
- `_copy_rename_phase_events_to_v13(conn)` — phase_events CHECK narrowing helper.
- `MIGRATIONS[14] = _migration_14_issue_lifecycle_closure`.
- `MIGRATIONS_DOWN[14] = _migration_14_down`.

**Note:** NO test file in this commit (test_migration_14_safety.py lives in Group B per atomic-DDL-only rule).

**Acceptance:** Migration runs on a v13 DB → schema_version=14, entity_relations table exists with 3 indices, (type, kind) CHECK admits `'bug'`, phase_events event_type CHECK admits `'spawned_child'`, kind='task' rows have lifecycle_class='task_flow'. Down-migration on v14 DB with 0 bugs + 0 relations → schema_version=13. Down with bugs → MigrationError.

### Group B — Discriminator + constants + helpers + tests

**Goal:** All Python application logic + new exception classes + 4 new EntityDatabase helpers + transition_entity_phase defensive raise + the migration safety tests.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/database.py` — add constants + helpers + exceptions.
- `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py` — add defensive raise.
- `plugins/pd/hooks/lib/entity_registry/test_migration_14_safety.py` (NEW) — verifies Group A migration.
- `plugins/pd/hooks/lib/entity_registry/test_status_only_lifecycle.py` (NEW) — verifies AC-BL.x.
- `plugins/pd/hooks/lib/entity_registry/test_entity_lifecycle.py` — extend with AC-BL.7 defensive raise tests.
- `plugins/pd/mcp/test_workflow_state_server.py` — audit + extend if needed for ENTITY_MACHINES introspection assertions impacted by defensive raise.

**Additions:**
- `_KIND_TO_TYPE_LIFECYCLE` at database.py:48: add `'bug': ('work', 'bug_flow')`; remap `'task': ('work', 'task_flow')`.
- `_VALID_PARAMS` at database.py:4442: add `'spawned_child': {'metadata'}`.
- `_CLOSES_TERMINAL` (NEW module-level dict at database.py near `_KIND_TO_TYPE_LIFECYCLE`): `{'bug_flow': 'closed', 'task_flow': 'closed', 'work_flow': 'dropped'}`.
- `VALID_ENTITY_TYPES` tuple at database.py:4534: add `'bug'` (9 values total).
- `EntityNotFoundError(ValueError)` + `InvalidCloseTargetError(ValueError)` near EntityExistsError at :4484.
- 4 new EntityDatabase methods: `get_entity_by_uuid`, `get_prior_closer`, `insert_entity_relation`, `resolve_entity_uuid`.
- `transition_entity_phase`: pre-validation raise for `kind in {'bug', 'task'}` with message `"invalid_entity_type: {kind} uses status-only lifecycle; use update_entity directly"`.

**Acceptance:** All AC-BL.x + AC-EX.x + AC-MR.x pass. `pytest plugins/pd/hooks/lib/entity_registry/test_status_only_lifecycle.py test_migration_14_safety.py test_entity_lifecycle.py -v` green.

### Group C — F9 `issue_spawn` MCP

**Goal:** New MCP tool that spawns bug/task issue entities linked to a parent, appends `spawned_child` event on parent without modifying parent's `workflow_phase` or `kanban_column`.

**Files:**
- `plugins/pd/mcp/entity_server.py` — add `@mcp.tool() async def issue_spawn(...)`.
- `plugins/pd/mcp/test_issue_spawn.py` (NEW) — verifies AC-9.x.

**Implementation** (per IF-1 + IF-9 mapping): see design IF-1 step-by-step.

**Acceptance:** All AC-9.x pass. `pytest plugins/pd/mcp/test_issue_spawn.py -v` green.

### Group D — F10 `complete_phase` closes= extension

**Goal:** Extend existing `complete_phase` MCP to accept `closes: list[str] | None` kwarg; atomic transaction writes `entity_relations(kind='fixes')` rows + transitions closed entities to terminal status; idempotent on same-closer replay; cross-workspace closure forbidden.

**Files:**
- `plugins/pd/mcp/workflow_state_server.py:1086` (`_process_complete_phase`) and `:1809` (MCP signature) — add `closes` kwarg + closure block per IF-2.
- `plugins/pd/mcp/test_complete_phase_closes.py` (NEW) — verifies AC-10.x.

**Implementation pin:** see design IF-2 + the CRITICAL transaction-close ordering note. Implementer MUST verify the existing transaction boundary at workflow_state_server.py:1127-1234 includes the closure writes BEFORE COMMIT; if existing flow commits early, closure block hoists above the early commit.

**Acceptance:** All AC-10.x (10.1 through 10.11) pass. `pytest plugins/pd/mcp/test_complete_phase_closes.py -v` green.

### Group E — Cleanup + new doctor check

**Goal:** Remove free-text suffix parsers from production code, add `check_no_free_text_status_parsers` doctor check.

**Files:**
- `plugins/pd/hooks/lib/entity_registry/backfill.py:418-444` — DELETE derived_status block.
- `plugins/pd/hooks/lib/doctor/checks.py:983-1015` — DELETE regex compilation + line-loop; preserve entities_conn cross-ref infra.
- `plugins/pd/hooks/lib/doctor/checks.py` (bottom) — add `check_no_free_text_status_parsers` per IF-8.
- `plugins/pd/hooks/lib/doctor/__init__.py:11-27` (import block) + `:32` (CHECK_ORDER list) — register new check.
- `plugins/pd/hooks/lib/entity_registry/test_backfill.py:981, 992, 1037` — migrate fixtures to DB-state inputs OR delete parser-exercise-only tests.
- `plugins/pd/hooks/lib/entity_registry/test_entity_status.py:385-1168` — same triage.
- `plugins/pd/hooks/lib/entity_registry/test_cleanup_suffix_parsers.py` (NEW) — verifies AC-CL.x.
- `plugins/pd/hooks/lib/doctor/test_doctor.py` — extend with `check_no_free_text_status_parsers` smoke tests + 2-CWD assertion.

**Acceptance:** All AC-CL.x pass (1 grep returns 0; 2 backfill behavior documented as changed; 3 doctor reads from DB; 4 new check passes from project root AND from a subdirectory).

## §4 Risks (carry-forward from spec/design)

- **R1–R8** (see spec.md §7 + design.md §3) — all addressed.
- **Implementer must verify:**
  - IF-2 step 5 transaction COMMIT-ordering at `workflow_state_server.py:1127-1234` (design notes critical verification).
  - test_workflow_state_server.py impact from defensive raise in transition_entity_phase (Group B sub-task).
  - Same-PR constraint for Groups A + B (must merge together).
- **Accepted out-of-scope:** orphan detection (entities whose parent has no `spawned_child` audit row) — explicit design decision; no compensating code.

## §5 Acceptance Map

| Spec AC | Group | Test file |
|---|---|---|
| AC-9.1 – 9.9 | C | `test_issue_spawn.py` |
| AC-10.1 – 10.11 | D | `test_complete_phase_closes.py` |
| AC-MR.1 – 11 | A (DDL) + B (tests) | `test_migration_14_safety.py` |
| AC-BL.1 – 7 | B | `test_status_only_lifecycle.py` + `test_entity_lifecycle.py` |
| AC-CL.1 – 4 | E | `test_cleanup_suffix_parsers.py` + `test_doctor.py` |
| AC-EX.1 – 2 | B | `test_status_only_lifecycle.py` (or dedicated section) |
