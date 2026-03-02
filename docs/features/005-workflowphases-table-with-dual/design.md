# Design: WorkflowPhases Table with Dual-Dimension Status Model

## Prior Art Research

### Codebase Patterns
- **Migration framework**: `MIGRATIONS` dict maps version→function. `_migrate()` iterates `range(current+1, target+1)`. Migration 2 uses self-managed transactions (`BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK`) with FK toggle.
- **CRUD pattern**: `_resolve_identifier()` for UUID/type_id lookup, `set_parts/params` dynamic builder for UPDATE, `dict(row)` returns, `ValueError` for not-found, `_now_iso()` for timestamps.
- **Backfill pattern**: `backfill.py` uses `_read_json()` helper (returns None on error), iterates glob paths, calls `register_entity()` per item.
- **Test pattern**: `@pytest.fixture` with `tmp_path`, file-based and in-memory DB fixtures, `PRAGMA table_info` for schema assertions, `pytest.raises(IntegrityError)` for constraints.

### External Research
- Self-managed transaction pattern is SQLite best practice for DDL migrations — matches migration 2 approach.
- Dual-dimension status (workflow_phase + kanban_column) is a production-proven pattern (Microsoft Dynamics 365 uses Status + Document Status).
- `INSERT OR IGNORE` is the standard SQLite idempotent backfill pattern.
- CHECK constraints enforce enums at DB layer — fail fast, preferred over app-only validation.

## Architecture Overview

Three isolated components added to the existing entity registry:

```
┌──────────────────────────────────────────────────┐
│                 database.py                       │
│                                                   │
│  MIGRATIONS = {                                   │
│    1: _create_initial_schema,                     │
│    2: _migrate_to_uuid_pk,                        │
│    3: _create_workflow_phases_table,  ← NEW        │
│  }                                                │
│                                                   │
│  class EntityDatabase:                            │
│    # Existing entity CRUD...                      │
│    create_workflow_phase()    ← NEW                │
│    get_workflow_phase()       ← NEW                │
│    update_workflow_phase()    ← NEW                │
│    delete_workflow_phase()    ← NEW                │
│    list_workflow_phases()     ← NEW                │
│                                                   │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│              backfill.py (extended)                │
│                                                   │
│  backfill_workflow_phases(db, artifacts_root)      │
│    ← NEW standalone function                      │
│    Reads: entities table + .meta.json files        │
│    Writes: workflow_phases rows via INSERT OR      │
│            IGNORE                                  │
│    Returns: {"created", "skipped", "errors"}       │
│                                                   │
└──────────────────────────────────────────────────┘
```

### Component 1: Migration 3 (`_create_workflow_phases_table`)

**Location**: `plugins/iflow/hooks/lib/entity_registry/database.py`, module-level function.

**Responsibility**: Create the `workflow_phases` table, immutability trigger, and indexes. Self-managed transaction following migration 2 pattern.

**DDL**: Directly from ADR-004 Appendix E, adapted:
- Migration version 3 (not 2 as ADR described)
- FK targets `entities(type_id)` which is UNIQUE after migration 2

**Transaction pattern**: Replicates migration 2 exactly:
1. `PRAGMA foreign_keys = OFF` (outside try — PRAGMA cannot run inside transaction)
2. Verify FK disabled
3. `BEGIN IMMEDIATE`
4. Pre-migration FK check
5. `CREATE TABLE IF NOT EXISTS workflow_phases (...)` with CHECK constraints
6. `CREATE TRIGGER IF NOT EXISTS enforce_immutable_wp_type_id`
7. `CREATE INDEX IF NOT EXISTS idx_wp_kanban_column`
8. `CREATE INDEX IF NOT EXISTS idx_wp_workflow_phase`
9. Upsert `schema_version = '3'` in same transaction
10. `COMMIT` (or `ROLLBACK` on exception)
11. `PRAGMA foreign_keys = ON` in `finally`
12. Post-migration FK check

**Why self-managed?** Migration 2's docstring mandates it: "Future migrations MUST follow this same pattern if they perform DDL operations." Migration 3 performs DDL (CREATE TABLE, CREATE TRIGGER, CREATE INDEX).

**Risk**: Migration 3 is additive (CREATE IF NOT EXISTS) — no data manipulation, no table reconstruction. Lower risk than migration 2's destructive rename.

### Component 2: CRUD Methods on EntityDatabase

**Location**: `plugins/iflow/hooks/lib/entity_registry/database.py`, new methods in `EntityDatabase` class.

Five methods following existing patterns:

| Method | Pattern | Return | Not-found |
|--------|---------|--------|-----------|
| `create_workflow_phase` | INSERT + SELECT-back | `dict` | `ValueError` (FK/PK) |
| `get_workflow_phase` | SELECT WHERE PK | `dict \| None` | `None` |
| `update_workflow_phase` | Dynamic SET builder | `dict` | `ValueError` |
| `delete_workflow_phase` | DELETE WHERE PK | `None` | `ValueError` |
| `list_workflow_phases` | SELECT with optional WHERE | `list[dict]` | `[]` |

**Design decisions**:
- CRUD methods operate on `type_id` directly (no UUID resolution needed — `type_id` IS the PK of `workflow_phases`)
- `create_workflow_phase` validates FK existence via SELECT before INSERT to provide clear ValueError rather than raw IntegrityError
- `update_workflow_phase` uses `set_parts/params` dynamic builder matching `update_entity` pattern; always auto-sets `updated_at` via `self._now_iso()`
- No entity-type restrictions (D-10) — all type_ids accepted; application-level validation deferred to feature 008
- `updated_at` always auto-generated, never caller-supplied
- **IntegrityError handling**: Both `create_workflow_phase` and `update_workflow_phase` catch `IntegrityError` and inspect the error message string to distinguish causes: `"UNIQUE constraint failed"` → `ValueError("Workflow phase already exists for: {type_id}")`, `"CHECK constraint failed"` → `ValueError("Invalid value: {error_detail}")`, other → re-raise as `ValueError` with original SQLite message. This ensures callers always get `ValueError` with a descriptive message, never raw `IntegrityError`.

### Component 3: Backfill Function

**Location**: `plugins/iflow/hooks/lib/entity_registry/backfill.py`, new module-level function.

**Responsibility**: Populate `workflow_phases` rows for existing entities using data from `entities` table + `.meta.json` files.

**Data flow**:
```
entities table ──→ type_id, entity_type, artifact_path
                      │
                      ▼
              ┌─────────────────────┐
              │  .meta.json read    │
              │  (via _resolve_     │
              │   meta_path)        │
              └────────┬────────────┘
                       │
                       ▼
              ┌─────────────────────┐
              │  Status Resolution  │
              │  (ordered fallback) │
              │                     │
              │  1. .meta.json      │
              │     "status" field  │
              │  2. entities.status │
              │     (often NULL)    │
              │  3. default:        │
              │     "planned"       │
              └────────┬────────────┘
                       │
                       ▼
              ┌─────────────────────┐
              │  Derivation Engine  │
              │                     │
              │  status →           │
              │    kanban_column    │
              │                     │
              │  lastCompletedPhase │
              │    → workflow_phase │
              └────────┬────────────┘
                       │
                       ▼
              INSERT OR IGNORE
              into workflow_phases
              (updated_at = db._now_iso())
```

**Entity query**: `SELECT type_id, entity_type, status, artifact_path FROM entities WHERE entity_type != 'project'` — project exclusion at query level (not per-row skip).

**Status resolution priority**: The existing `_scan_features()` backfill does NOT pass `status` to `register_entity()`, so `entities.status` is NULL for most entities. The backfill resolves status via:
1. `.meta.json` `status` field (primary — always populated by iflow workflow)
2. `entities.status` column (fallback — may be NULL)
3. Default to `"planned"` if both are NULL (maps to kanban `"backlog"`)

**Processing per entity**:
1. Skip project entities (per ADR-004 Appendix D)
2. Resolve `.meta.json` path: `artifact_path/.meta.json` first, then convention fallback
3. Read `.meta.json` with error tolerance (D-9)
4. Resolve status: `.meta.json` `status` → `entities.status` → `"planned"` default
5. Map resolved status → `kanban_column` via `STATUS_TO_KANBAN`
6. Extract `lastCompletedPhase` and `mode` from `.meta.json`
7. Derive `workflow_phase` per D-5 rules
8. Generate `updated_at` via `db._now_iso()` (see TD-8)
9. `INSERT OR IGNORE` into `workflow_phases` (all 7 columns supplied)

**Phase sequence constant**: `PHASE_SEQUENCE = ("brainstorm", "specify", "design", "create-plan", "create-tasks", "implement", "finish")`

**Status-to-kanban mapping**: `STATUS_TO_KANBAN = {"planned": "backlog", "active": "wip", "completed": "completed", "abandoned": "completed"}`

**Timestamp generation**: Backfill generates `updated_at` via `db._now_iso()` (see TD-8). This is the same `@staticmethod` used by CRUD methods, ensuring consistent ISO 8601 UTC format across all `workflow_phases` writes.

**Brainstorm/backlog entities**: `_resolve_meta_path` returns `None` for entities without `artifact_path` and no matching convention directory. This is expected — brainstorms and backlogs may lack `.meta.json` files. When `_resolve_meta_path` returns `None`, the backfill uses defaults: `kanban_column` from status resolution, `workflow_phase = None`, `last_completed_phase = None`, `mode = None`.

## Technical Decisions

### TD-1: Migration function placement
**Decision**: `_create_workflow_phases_table(conn)` is a module-level function in `database.py`, added to `MIGRATIONS[3]`.
**Rationale**: Follows migration 1 and 2 convention. Module-level functions receive raw `sqlite3.Connection`.

### TD-2: CRUD method section placement
**Decision**: New "Workflow Phase CRUD" section in `EntityDatabase`, after existing "Entity CRUD" section and before "Export" section.
**Rationale**: Logical grouping. Entity CRUD and Workflow Phase CRUD are related but separate concerns.

### TD-3: Backfill in backfill.py, not database.py
**Decision**: `backfill_workflow_phases()` lives in `backfill.py` as a standalone function taking `(db: EntityDatabase, artifacts_root: str)`.
**Rationale**: Backfill is a data migration concern, not a core database concern. `backfill.py` already contains `run_backfill()` for entity backfill — workflow phase backfill is the same pattern. Keeps `database.py` focused on schema + CRUD.

### TD-4: No _resolve_identifier for workflow_phase CRUD
**Decision**: Workflow phase CRUD methods accept `type_id: str` directly and query `workflow_phases` table by PK. They do NOT use `_resolve_identifier()`.
**Rationale**: `workflow_phases.type_id` is the PK. There's no UUID column in `workflow_phases`. Using `_resolve_identifier()` would require an extra lookup to `entities` table that's unnecessary. The FK constraint already ensures `type_id` exists in `entities`.

### TD-5: create_workflow_phase validates FK before INSERT (advisory)
**Decision**: `create_workflow_phase` does `SELECT 1 FROM entities WHERE type_id = ?` before INSERT. Raises `ValueError("Entity not found: {type_id}")` if not found. This is an advisory check — see TD-9 for TOCTOU analysis.
**Rationale**: Provides clear error message matching existing `_resolve_identifier` convention rather than exposing raw `sqlite3.IntegrityError`. For PK conflict (duplicate insert), catch `IntegrityError` and raise `ValueError("Workflow phase already exists for: {type_id}")`. The DB-level FK constraint is the authoritative enforcement.

### TD-6: update_workflow_phase returns updated row
**Decision**: After UPDATE, does `SELECT * FROM workflow_phases WHERE type_id = ?` and returns `dict(row)`.
**Rationale**: Spec requires `-> dict` return. The SELECT-back ensures the returned dict reflects the actual DB state including auto-generated `updated_at`.

### TD-7: Logging for backfill warnings
**Decision**: Backfill uses `logging.getLogger(__name__).warning()` for error tolerance messages (malformed JSON, unrecognized phase, invalid mode).
**Rationale**: Follows Python logging best practice. Callers can configure handlers. No `print(file=sys.stderr)` — that pattern is for hooks only.

### TD-8: `_now_iso()` access for backfill
**Decision**: `_now_iso()` is a `@staticmethod` on `EntityDatabase` (not a module-level function). Backfill accesses it via `db._now_iso()` using the passed `db: EntityDatabase` parameter.
**Rationale**: The backfill already receives a `db` instance. Calling `db._now_iso()` is the simplest path — no import gymnastics, no extracting the static method. CRUD methods access it as `self._now_iso()` internally. Both paths produce the same ISO 8601 UTC timestamp.

### TD-9: FK validation is advisory, not authoritative
**Decision**: `create_workflow_phase`'s pre-INSERT `SELECT 1 FROM entities WHERE type_id = ?` is an advisory check — a TOCTOU race condition exists between the SELECT and INSERT.
**Rationale**: The DB-level FK constraint is the authoritative enforcement. The advisory SELECT provides a clear `ValueError` message instead of a raw `IntegrityError` for the common case (single-writer CLI tool). In the unlikely race scenario, the FK constraint catches it and `IntegrityError` propagates. This matches the existing `_resolve_identifier` pattern which has the same advisory-then-authoritative layering.

### TD-10: Backfill bypasses CRUD for INSERT OR IGNORE
**Decision**: Backfill writes directly via `INSERT OR IGNORE` SQL instead of calling `create_workflow_phase()`.
**Rationale**: `create_workflow_phase()` raises `ValueError` on duplicate — incompatible with idempotent backfill semantics. `INSERT OR IGNORE` is the standard SQLite pattern for "insert if not exists, skip otherwise." This creates schema coupling between backfill and the `workflow_phases` DDL, but this is acceptable because: (1) both live in the same package, (2) the DDL is unlikely to change without a new migration, (3) tests validate both paths against the same schema.

## Interfaces

### Migration 3

```python
def _create_workflow_phases_table(conn: sqlite3.Connection) -> None:
    """Migration 3: Create workflow_phases table with dual-dimension status model.

    Self-managed transaction (BEGIN IMMEDIATE / COMMIT / ROLLBACK).
    The outer _migrate() performs a second schema_version upsert + commit
    after this function returns. Both writes set version=3, so the second
    write is a no-op at the data level but does execute a SQL statement
    and commit.
    """
```

Registration:
```python
MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _create_initial_schema,
    2: _migrate_to_uuid_pk,
    3: _create_workflow_phases_table,
}
```

### CRUD Methods

```python
class EntityDatabase:

    # -- Workflow Phase CRUD --

    def create_workflow_phase(
        self,
        type_id: str,
        kanban_column: str = "backlog",
        workflow_phase: str | None = None,
        last_completed_phase: str | None = None,
        mode: str | None = None,
        backward_transition_reason: str | None = None,
    ) -> dict:
        """Create a workflow phase row for an entity.

        Parameters
        ----------
        type_id:
            Entity type_id (must exist in entities table).
        kanban_column:
            Kanban board column (default: 'backlog').
        workflow_phase:
            Current workflow phase (nullable).
        last_completed_phase:
            Last completed phase (nullable).
        mode:
            Workflow mode: 'standard' or 'full' (nullable).
        backward_transition_reason:
            Reason for backward transition (nullable).

        Returns
        -------
        dict
            The inserted row as a dictionary with all 7 columns.

        Raises
        ------
        ValueError
            If entity does not exist or workflow phase already exists.
        """

    def get_workflow_phase(self, type_id: str) -> dict | None:
        """Get workflow phase for an entity.

        Parameters
        ----------
        type_id:
            Entity type_id to look up.

        Returns
        -------
        dict | None
            Row as dictionary, or None if not found.
        """

    def update_workflow_phase(
        self,
        type_id: str,
        kanban_column=_UNSET,           # str | None; _UNSET = not provided
        workflow_phase=_UNSET,           # str | None; _UNSET = not provided
        last_completed_phase=_UNSET,     # str | None; _UNSET = not provided
        mode=_UNSET,                     # str | None; _UNSET = not provided
        backward_transition_reason=_UNSET,  # str | None; _UNSET = not provided
    ) -> dict:
        """Update mutable fields of a workflow phase row.

        Only provided fields are updated. updated_at is always refreshed.
        Uses _UNSET sentinel: omitted kwargs keep current value;
        explicitly passing None sets the field to NULL.

        Parameters
        ----------
        type_id:
            Entity type_id (must have existing workflow_phases row).
        kanban_column:
            New kanban column value (if provided).
        workflow_phase:
            New workflow phase (if provided; None sets to NULL).
        last_completed_phase:
            New last completed phase (if provided; None sets to NULL).
        mode:
            New mode (if provided; None sets to NULL).
        backward_transition_reason:
            New reason (if provided; None sets to NULL).

        Returns
        -------
        dict
            The updated row as a dictionary.

        Raises
        ------
        ValueError
            If no workflow phase exists for the given type_id.
        """

    def delete_workflow_phase(self, type_id: str) -> None:
        """Delete a workflow phase row.

        Parameters
        ----------
        type_id:
            Entity type_id whose workflow phase row to delete.

        Raises
        ------
        ValueError
            If no workflow phase exists for the given type_id.
        """

    def list_workflow_phases(
        self,
        kanban_column: str | None = None,
        workflow_phase: str | None = None,
    ) -> list[dict]:
        """List workflow phase rows with optional filters.

        Parameters
        ----------
        kanban_column:
            Filter by kanban column (if provided).
        workflow_phase:
            Filter by workflow phase (if provided).

        Returns
        -------
        list[dict]
            Matching rows as dictionaries. Empty list if none match.
        """
```

**Sentinel pattern for update**: The `update_workflow_phase` method uses `_UNSET` (a module-level sentinel object) as default for nullable fields. This distinguishes "not provided" (keep current value) from `None` (set to NULL).

**Note**: This is a **new pattern** not present in existing EntityDatabase code. The existing `update_entity` uses `None` to mean "not provided" and cannot set fields to NULL. The sentinel pattern is well-established in Python (Django, attrs, pydantic all use it) and is necessary here because `workflow_phases` has legitimately nullable fields that callers need to explicitly clear.

```python
_UNSET = object()  # module-level sentinel

def update_workflow_phase(self, type_id, kanban_column=_UNSET, workflow_phase=_UNSET, ...):
    set_parts = ["updated_at = ?"]
    params = [self._now_iso()]
    if kanban_column is not _UNSET:
        set_parts.append("kanban_column = ?")
        params.append(kanban_column)
    # ... same for each nullable field
```

### Backfill Function

```python
# Constants
PHASE_SEQUENCE: tuple[str, ...] = (
    "brainstorm", "specify", "design", "create-plan",
    "create-tasks", "implement", "finish",
)

STATUS_TO_KANBAN: dict[str, str] = {
    "planned": "backlog",
    "active": "wip",
    "completed": "completed",
    "abandoned": "completed",
}

VALID_MODES: frozenset[str] = frozenset({"standard", "full"})


def backfill_workflow_phases(
    db: EntityDatabase,
    artifacts_root: str,
) -> dict:
    """Backfill workflow_phases rows for all eligible entities.

    Reads entity data from DB + .meta.json files. Creates rows
    using INSERT OR IGNORE for idempotency.

    Parameters
    ----------
    db:
        Open EntityDatabase instance.
    artifacts_root:
        Root directory containing feature/brainstorm/backlog artifacts.

    Returns
    -------
    dict
        {"created": int, "skipped": int, "errors": list[str]}
    """
```

**Internal helpers** (private to backfill.py):

```python
def _derive_next_phase(last_completed: str) -> str | None:
    """Return the phase after last_completed, or None if finish/unrecognized."""

def _read_meta_json(path: str) -> dict | None:
    """Read and parse .meta.json. Wraps existing _read_json with
    additional warning logging for malformed files per D-9 error tolerance.
    Reuses _read_json for file I/O and JSON parsing; adds entity-specific
    field validation warnings (missing lastCompletedPhase, invalid mode)."""

def _resolve_meta_path(
    entity: dict, artifacts_root: str
) -> str | None:
    """Resolve .meta.json path from artifact_path or convention fallback.

    Returns None for entities without artifact_path and no matching
    convention directory (expected for brainstorms/backlogs without
    artifact directories). Caller uses defaults when None returned.
    """
```

## Risks

### R-1: Self-managed transaction complexity
**Risk**: Incorrectly replicating migration 2's transaction pattern could leave DB in inconsistent state.
**Mitigation**: Migration 3 is purely additive (CREATE IF NOT EXISTS). No data manipulation, no table drops. Even a partial failure leaves a clean state. Tests verify both success and rollback paths.

### R-2: .meta.json format inconsistencies
**Risk**: LLM-written `.meta.json` files may have unexpected formats.
**Mitigation**: D-9 error tolerance — every `.meta.json` read is wrapped in try/except with fallback to defaults. Backfill is resilient by design.

### R-3: Sentinel pattern complexity in update
**Risk**: Using `_UNSET` sentinel for nullable fields adds implementation complexity.
**Mitigation**: Pattern is well-established in Python (Django, attrs, pydantic all use sentinels). The alternative — not supporting "set to NULL" — would be a functional gap. Clearly documented with examples in docstring.

### R-4: Backfill path resolution failures
**Risk**: `artifact_path` in entities table may be stale or incorrect.
**Mitigation**: Two-level fallback (artifact_path → convention path → defaults). Missing `.meta.json` is a normal condition, not an error.
