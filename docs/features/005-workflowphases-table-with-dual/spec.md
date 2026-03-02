# Specification: WorkflowPhases Table with Dual-Dimension Status Model

## Problem Statement

The entity registry database has no concept of workflow phase state or kanban process state. All workflow tracking lives in `.meta.json` files per feature, read and written by the LLM. Feature 004 produced an ADR (ADR-004) defining a dual-dimension status model — `workflow_phase` (lifecycle progress) and `kanban_column` (process state) — stored in a new `workflow_phases` table with 1:1 FK to `entities`. This feature implements that table as a database migration, adds Python CRUD methods to `EntityDatabase`, and backfills existing entities into the new table.

## Success Criteria

- [ ] `workflow_phases` table created via migration 3 in `database.py` matching ADR-004 Appendix E DDL (adapted: migration 3 instead of ADR-004's migration 2; FK targets `entities(type_id)` which is UNIQUE after migration 2)
- [ ] `EntityDatabase` exposes CRUD methods for `workflow_phases`: create, get, update, delete, list/query
- [ ] Backfill function populates `workflow_phases` rows for all existing feature, brainstorm, and backlog entities (project entities excluded per ADR-004 Appendix D)
- [ ] Backfill maps existing `status` field to `kanban_column` per ADR-004 Appendix G conversion table
- [ ] Backfill maps existing `lastCompletedPhase` (from `.meta.json`) to `workflow_phases.last_completed_phase` when available
- [ ] All new code has tests with >90% coverage
- [ ] Existing entity registry tests continue to pass (zero regressions)
- [ ] Migration is safe: runs on fresh DB and on DB already at schema version 2

## Scope

### In Scope

- Database migration 3: `workflow_phases` table DDL, immutability trigger, indexes (from ADR-004 Appendix E)
- `EntityDatabase` methods for `workflow_phases` CRUD:
  - `create_workflow_phase(type_id, ...) -> dict` — insert a row, return the inserted row as dict
  - `get_workflow_phase(type_id) -> dict | None` — read a row by PK, return None if not found
  - `update_workflow_phase(type_id, **kwargs) -> dict` — update mutable fields, return updated row; `updated_at` is always auto-generated via `_now_iso()`, not caller-supplied
  - `delete_workflow_phase(type_id) -> None` — delete a row
  - `list_workflow_phases(kanban_column=None, workflow_phase=None) -> list[dict]` — query with optional filters
- Backfill function: `backfill_workflow_phases(db, artifacts_root)` — scan entities and `.meta.json` files to populate rows
- Schema version bump to 3
- Test coverage for migration, CRUD methods, backfill, edge cases

### Out of Scope

- State engine logic / transition validation (feature 008)
- Per-entity-type kanban column restrictions at application level (feature 008)
- Transition audit log / per-phase history (feature 008)
- MCP tool exposure of workflow phase methods (feature 009)
- Kanban UI rendering (feature 019)
- Reconciliation tool (feature 011)
- Modifying any existing command or skill to use these methods
- FR-5 per-phase timestamps, iterations, reviewerNotes, skippedPhases — partially addressed by this feature (table creation, lastCompletedPhase, mode, kanban_column) and partially deferred to feature 008 (transition log with per-phase detail)

## Decisions

### D-1: Migration version number
**Decision:** Migration 3 (not 2 as the ADR originally described — migration 2 was claimed by feature 001's UUID migration).
**Rationale:** Sequential integer-based migration system. The `MIGRATIONS` dict in `database.py` already has `{1: _create_initial_schema, 2: _migrate_to_uuid_pk}`.

### D-2: FK column type
**Decision:** FK remains `TEXT ... REFERENCES entities(type_id)` since `type_id` is `TEXT NOT NULL UNIQUE` after migration 2. No change needed from ADR-004 DDL.
**Rationale:** SQLite allows FK references to UNIQUE columns, not just PRIMARY KEY. The ADR's DDL is directly usable.

### D-3: Backfill data source
**Decision:** Backfill reads from the `entities` table for entity existence and `status`, and reads `.meta.json` files from the artifacts root for `lastCompletedPhase` and `mode`. It does NOT read `workflow_phase` (derived from lastCompletedPhase if active) or other phase-level data (deferred to feature 008).
**Rationale:** The `entities` table has `status` but not `lastCompletedPhase` or `mode`. These live in `.meta.json`. The backfill bridges both sources.

### D-4: Backfill idempotency
**Decision:** Backfill uses `INSERT OR IGNORE` — existing rows are not overwritten. This makes backfill re-runnable.
**Rationale:** The PRD identifies one-shot backfill as a known anti-pattern. Idempotent backfill is safer for migration reruns and testing.

### D-5: workflow_phase derivation during backfill
**Decision:** The ordered phase sequence for derivation is: `brainstorm`, `specify`, `design`, `create-plan`, `create-tasks`, `implement`, `finish`. Derivation rules by entity status:
- **active** → `workflow_phase` = the phase after `lastCompletedPhase` in the sequence. If `lastCompletedPhase` is `finish`, set to `finish`. If `lastCompletedPhase` is NULL or unrecognized, set to NULL.
- **completed** → `workflow_phase` = `finish`
- **planned** → `workflow_phase` = NULL
- **abandoned** → `workflow_phase` = the phase after `lastCompletedPhase` if available (preserving the phase where work stopped), or NULL if `lastCompletedPhase` is unavailable. This aligns with ADR-004 Appendix F scenario #6 where `kanban_column=completed` AND `workflow_phase != finish` signals abandonment.
- **brainstorm/backlog entities** → always NULL regardless of status.
**Rationale:** The `workflow_phase` column represents the current active phase. Deriving it from `lastCompletedPhase` is the most accurate mapping without a running state engine. Abandoned features preserve their last-known phase position to distinguish them from completed features.

### D-6: Migration 3 transaction management
**Decision:** Migration 3 follows the same self-managed transaction pattern as migration 2 (`BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK`), including updating `schema_version` within its own transaction.
**Rationale:** Migration 3 performs DDL operations (CREATE TABLE, CREATE TRIGGER, CREATE INDEX). The database.py migration 2 docstring explicitly requires: "Future migrations MUST follow this same pattern if they perform DDL operations." The outer `_migrate()` commit is a no-op for self-managed migrations.

### D-7: Backfill invocation timing
**Decision:** Backfill is a separate callable function, not automatically invoked by migration 3. Migration 3 only creates the table structure. Backfill must be invoked separately (e.g., by the caller after `EntityDatabase` construction, or by a dedicated backfill script/CLI).
**Rationale:** Separating DDL migration from data migration keeps the migration function simple, testable, and safe for fresh databases (which have no entities to backfill).

### D-8: .meta.json path resolution
**Decision:** Backfill locates `.meta.json` files using the `artifact_path` column from the `entities` table. For each entity with a non-NULL `artifact_path`, the backfill looks for `{artifact_path}/.meta.json`. If `artifact_path` is NULL, the backfill falls back to the convention `{artifacts_root}/{entity_type}s/{entity_id}/.meta.json` (e.g., `docs/features/005-workflowphases-table-with-dual/.meta.json`). If `.meta.json` does not exist for an entity, backfill proceeds with default values (`workflow_phase=NULL`, `mode=NULL`, `last_completed_phase=NULL`).
**Rationale:** The `entities` table already stores `artifact_path` for most entities. Falling back to convention-based paths handles legacy entries. Missing `.meta.json` is a normal condition for brainstorm/backlog entities.
**Note:** For brainstorm and backlog entities, `artifact_path` points to a file (not a directory), so the `{artifact_path}/.meta.json` lookup will not find a file. This is expected — per D-5 and D-9, these entities proceed with defaults. The path resolution logic is primarily relevant to feature entities, which are the only entity type with per-entity `.meta.json` files.

### D-9: .meta.json error tolerance
**Decision:** Backfill handles `.meta.json` gracefully:
1. If `.meta.json` does not exist → proceed with defaults (NULL for all .meta.json-sourced fields)
2. If `.meta.json` contains malformed JSON → log a warning, proceed with defaults
3. If `lastCompletedPhase` contains an unrecognized phase value (not in the 7-phase sequence) → set `workflow_phase` and `last_completed_phase` to NULL, log a warning
4. If `mode` contains an invalid value (not `standard`/`full`) → set `mode` to NULL, log a warning
**Rationale:** `.meta.json` files are written by the LLM and have known inconsistencies (per PRD problem statement). Backfill must be resilient to malformed data.

### D-10: CRUD methods do not enforce entity-type restrictions
**Decision:** CRUD methods in this feature do NOT enforce per-entity-type `kanban_column` restrictions (e.g., brainstorm entities limited to `backlog`/`prioritised`). That is feature 008's responsibility. Backfill data written by this feature may violate application-level invariants from ADR-004 Appendix D; feature 008's state engine is expected to reconcile on first use.
**Rationale:** Keeping CRUD methods simple and generic. Application-level validation belongs in the state engine layer, not the data access layer.

## Acceptance Criteria

### AC-1: Migration Creates Table
- Given a database at schema version 2
- When migration 3 runs
- Then `workflow_phases` table exists with columns: `type_id`, `workflow_phase`, `kanban_column`, `last_completed_phase`, `mode`, `backward_transition_reason`, `updated_at`
- And `type_id` is PRIMARY KEY with FK to `entities(type_id)`
- And CHECK constraints enforce valid enum values for `workflow_phase`, `kanban_column`, `last_completed_phase`, `mode`
- And `kanban_column` has NOT NULL DEFAULT 'backlog'
- And `updated_at` is NOT NULL
- And schema version is 3

### AC-2: Migration Creates Indexes and Trigger
- Given migration 3 has run
- Then index `idx_wp_kanban_column` exists on `kanban_column`
- And index `idx_wp_workflow_phase` exists on `workflow_phase`
- And trigger `enforce_immutable_wp_type_id` prevents UPDATE of `type_id`

### AC-3: Migration Is Safe on Fresh DB
- Given a brand-new empty database
- When `EntityDatabase(path)` is constructed
- Then migrations 1, 2, 3 run sequentially without error
- And schema version is 3
- And both `entities` and `workflow_phases` tables exist

### AC-4: CHECK Constraints Enforce Enums
- Given a `workflow_phases` row
- When `workflow_phase` is set to an invalid value (e.g., 'invalid')
- Then the INSERT/UPDATE fails with IntegrityError
- And valid values are: `brainstorm`, `specify`, `design`, `create-plan`, `create-tasks`, `implement`, `finish`, NULL
- And valid `kanban_column` values are: `backlog`, `prioritised`, `wip`, `agent_review`, `human_review`, `blocked`, `documenting`, `completed`
- And valid `last_completed_phase` values are: `brainstorm`, `specify`, `design`, `create-plan`, `create-tasks`, `implement`, `finish`, NULL (same as `workflow_phase`)
- And valid `mode` values are: `standard`, `full`, NULL

### AC-5: CRUD — Create
- Given an entity exists in the `entities` table
- When `create_workflow_phase(type_id, kanban_column='backlog')` is called
- Then a row is inserted into `workflow_phases`
- And calling it for a non-existent entity raises ValueError (FK violation)
- And calling it for an entity that already has a row raises ValueError (PK conflict)

### AC-6: CRUD — Get
- Given a `workflow_phases` row exists for type_id "feature:005-example"
- When `get_workflow_phase("feature:005-example")` is called
- Then a dict is returned with all 7 columns
- And calling it for a non-existent type_id returns None

### AC-7: CRUD — Update
- Given a `workflow_phases` row exists
- When `update_workflow_phase(type_id, kanban_column='wip', workflow_phase='design')` is called
- Then the row is updated with the new values
- And `updated_at` is refreshed to current UTC time in ISO-8601 format (matching `EntityDatabase._now_iso()` pattern)
- And calling it for a non-existent type_id raises ValueError
- And `type_id` cannot be updated (trigger enforces immutability)

### AC-8: CRUD — Delete
- Given a `workflow_phases` row exists for type_id "feature:005-example"
- When `delete_workflow_phase("feature:005-example")` is called
- Then the row is removed
- And calling it for a non-existent type_id raises ValueError

### AC-9: CRUD — List/Query
- Given multiple `workflow_phases` rows exist
- When `list_workflow_phases()` is called with no filters
- Then all rows are returned
- When `list_workflow_phases(kanban_column='wip')` is called
- Then only rows with kanban_column='wip' are returned
- When `list_workflow_phases(workflow_phase='design')` is called
- Then only rows with workflow_phase='design' are returned
- When both filters are provided, both are applied (AND logic)

### AC-10: Backfill — Feature Entities
- Given feature entities exist in `entities` table with status values
- When `backfill_workflow_phases(db, artifacts_root)` is called
- Then a `workflow_phases` row is created for each feature entity
- And `kanban_column` is mapped from entity `status` per ADR-004 conversion table:
  - planned → backlog
  - active → wip
  - completed → completed
  - abandoned → completed
- And `last_completed_phase` is read from `.meta.json` `lastCompletedPhase` field if available
- And `workflow_phase` is derived per D-5:
  - active → next phase after `lastCompletedPhase` (or NULL if unavailable)
  - completed → `finish`
  - planned → NULL
  - abandoned → next phase after `lastCompletedPhase` (or NULL if unavailable)

### AC-11: Backfill — Brainstorm and Backlog Entities
- Given brainstorm and backlog entities exist
- When backfill runs
- Then `workflow_phases` rows are created with `workflow_phase=NULL` (always NULL for brainstorm/backlog)
- And `kanban_column` uses the same status-to-column conversion as features:
  - planned → backlog
  - active → wip
  - completed → completed
  - abandoned → completed
- Note: ADR-004 Appendix D restricts brainstorm/backlog to `backlog` and `prioritised` columns at application level. This backfill intentionally writes `completed` for completed brainstorms — feature 008's state engine may normalize these values when it assumes authority over transitions.

### AC-12: Backfill — Project Entities Excluded
- Given project entities exist
- When backfill runs
- Then NO `workflow_phases` rows are created for project entities (per ADR-004 Appendix D)

### AC-13: Backfill — Idempotent
- Given backfill has already run
- When backfill is run again
- Then no errors occur (INSERT OR IGNORE)
- And existing rows are not modified
- And the function returns a dict: `{"created": int, "skipped": int, "errors": list[str]}` summarizing the backfill outcome

### AC-14: Backfill — Mode and workflow_phase from .meta.json
- Given a feature entity with a `.meta.json` containing `"mode": "standard"` and `"lastCompletedPhase": "design"`
- When backfill runs for that entity
- Then `workflow_phases.mode` is set to `"standard"`
- And `workflow_phases.last_completed_phase` is set to `"design"`
- And `workflow_phases.workflow_phase` is derived as the next phase after `design` (i.e., `create-plan`) if entity status is `active`

### AC-15: Existing Tests Pass
- Given the full entity registry test suite
- When run after migration 3 is added
- Then all existing tests pass with zero regressions

### AC-16: FK Enforcement
- Given `PRAGMA foreign_keys = ON`
- When attempting to INSERT into `workflow_phases` with a `type_id` that does not exist in `entities`
- Then the INSERT fails with IntegrityError
- When attempting to DELETE an entity that has a `workflow_phases` row
- Then the DELETE fails with IntegrityError (ON DELETE NO ACTION)

### AC-17: Backfill — Abandoned Features
- Given a feature entity with status `abandoned` and `.meta.json` containing `"lastCompletedPhase": "design"`
- When backfill runs for that entity
- Then `kanban_column` is set to `completed` (per conversion table)
- And `workflow_phase` is derived as the next phase after `design` (i.e., `create-plan`) — preserving where work stopped
- And `last_completed_phase` is set to `design`
- This distinguishes abandoned from completed: both have `kanban_column=completed`, but completed features have `workflow_phase=finish` while abandoned have `workflow_phase != finish`

### AC-18: Backfill — .meta.json Error Tolerance
- Given a feature entity whose `.meta.json` contains malformed JSON
- When backfill runs for that entity
- Then backfill proceeds with defaults (`workflow_phase=NULL`, `mode=NULL`, `last_completed_phase=NULL`)
- And a warning is logged (not an exception)
- Given a feature entity whose `.meta.json` has `"lastCompletedPhase": "unknown-invalid-phase"`
- When backfill runs for that entity
- Then `workflow_phase` and `last_completed_phase` are set to NULL
- And a warning is logged
- Given a feature entity with no `.meta.json` file
- When backfill runs for that entity
- Then backfill proceeds with defaults (no error)

## Feasibility Assessment

### Assessment Approach
1. **Codebase Evidence** — Entity registry migration framework proven (2 migrations deployed). DDL from ADR-004 is well-defined. EntityDatabase class has clear patterns for CRUD methods.
2. **Schema Validation** — The FK `REFERENCES entities(type_id)` works because `type_id` is UNIQUE after migration 2. Verified in SQLite documentation: FKs can reference any UNIQUE column.
3. **Test Infrastructure** — 436+ existing tests in `entity_registry/` provide patterns for testing migrations, CRUD, and edge cases.

### Assessment
**Overall:** Confirmed
**Reasoning:** Straightforward DDL migration following established patterns. The ADR provides complete DDL. CRUD methods follow EntityDatabase's existing API patterns. Backfill is the most complex piece but is bounded in scope.
**Key Assumptions:**
- SQLite FK to UNIQUE column works — Status: Verified in SQLite docs and existing `parent_type_id` FK pattern
- Migration framework handles version 3 — Status: Verified, `_migrate()` iterates `range(current + 1, target + 1)`
- `.meta.json` files accessible during backfill — Status: Verified, same pattern used by `frontmatter_sync.py` backfill
**Open Risks:**
- Migration must handle both fresh DB (no existing data) and existing DB (with entities). Mitigated by `CREATE TABLE IF NOT EXISTS` and idempotent backfill.

## Dependencies

- Feature 001 (entity-uuid-primary-key-migrat) — **completed** — provides migration 2 and current schema
- Feature 004 (status-taxonomy-design-and-sch) — **completed** — provides ADR-004 with DDL and taxonomy definitions
- `plugins/iflow/hooks/lib/entity_registry/database.py` — migration framework, EntityDatabase class
