# Design: Entity UUID Primary Key Migration

## Prior Art Research

### Codebase Patterns

- **Migration framework**: `MIGRATIONS` dict maps version int to callable. `_migrate()` loops `current+1..max(MIGRATIONS)`, calls each fn with `conn`, then commits version. Migration 1 uses `executescript()`. Extension point: add `2: _migrate_to_uuid_pk` entry.
- **Immutability enforcement**: 5 triggers (type_id, entity_type, created_at immutability + 2 self-parent prevention). Tests assert exactly 5 by sorted name.
- **No UUID usage in codebase**: `import uuid` will be introduced for the first time.
- **Backfill compatibility**: `register_entity()` return captured at backfill.py:187, passed to `set_parent()`. Post-migration, variable holds UUID but `set_parent()` dual-read handles it transparently. No backfill changes needed.
- **Server helpers**: `render_tree()` keys `by_id` on `type_id`, builds `children` from `parent_type_id`. Display via `_format_entity_label()` shows `type_id` in tree output.
- **MCP server**: `set_parent` handler (entity_server.py:150-152) ignores return value — must capture UUID return post-migration.

### External Research

- **SQLite PK migration**: Industry standard is CREATE-COPY-DROP-RENAME (12-step pattern). SQLite cannot ALTER TABLE to change PK.
- **UUID storage**: TEXT (36-char) is standard for SQLite. BLOB saves ~45% space but adds conversion overhead. TEXT is simpler — matches our needs.
- **DDL transaction control**: Python sqlite3 legacy mode does NOT auto-BEGIN for DDL — explicit `BEGIN IMMEDIATE` is required. `executescript()` auto-commits, breaking transactional safety.
- **PRAGMA foreign_keys**: Must be set outside any transaction — silently fails if run within one. Our `_set_pragmas()` runs in `__init__` before `_migrate()`, so this is safe.
- **INSERT OR IGNORE pitfall**: `cursor.lastrowid` retains previous value on ignored inserts. Always-SELECT pattern is correct.
- **UUID v4 scatter**: B-tree fragmentation is a one-time cost during migration batch INSERT, not a runtime concern for our small dataset.

## Architecture Overview

### Layered Change Propagation

The migration flows through 4 layers, each building on the one below:

```
Layer 1: Schema (DDL)
  Migration 2 function — table recreation, triggers, indexes
      ↓
Layer 2: Database API (EntityDatabase)
  _resolve_identifier(), register_entity(), set_parent(),
  get_entity(), get_lineage(), update_entity(), export_lineage_markdown()
      ↓
Layer 3: Server Helpers (server_helpers.py)
  render_tree(), _format_entity_label(), _process_register_entity(),
  _process_get_lineage()
      ↓
Layer 4: MCP Server (entity_server.py)
  Tool handlers capture UUID returns, format dual-identity messages
```

### Key Invariants

1. **type_id remains human-readable**: All display output uses `type_id`, never UUID
2. **uuid is the canonical identity**: All internal joins, FK lookups, and return values use UUID
3. **Dual-read is transparent**: Callers pass either UUID or type_id; the system resolves internally
4. **Backward compatibility via type_id UNIQUE**: `INSERT OR IGNORE` duplicate detection unchanged
5. **Trigger parity**: Every safety constraint on type_id-based columns has a UUID-based counterpart

## Components

### C1: Migration 2 Function (`_migrate_to_uuid_pk`)

**Location**: `database.py`, module-level function added to `MIGRATIONS[2]`

**Responsibility**: Transform schema from v1 (type_id PK) to v2 (uuid PK, type_id UNIQUE)

**Approach**: Single function that:
1. Disables foreign key enforcement via `PRAGMA foreign_keys = OFF` (required before table recreation, must be outside any transaction)
1b. Verifies `PRAGMA foreign_keys` returns 0; if not, raises `RuntimeError("PRAGMA foreign_keys = OFF did not take effect — aborting migration")`
2. Begins explicit `BEGIN IMMEDIATE` transaction
3. Runs `PRAGMA foreign_key_check` to validate FK integrity before migration. Aborts with clear error if violations exist (prevents silently orphaned parent_uuid entries).
4. Creates `entities_new` with exact DDL from I9 (table name `entities_new`):
   ```sql
   CREATE TABLE entities_new (
       uuid           TEXT NOT NULL PRIMARY KEY,
       type_id        TEXT NOT NULL UNIQUE,
       entity_type    TEXT NOT NULL CHECK(entity_type IN ('backlog','brainstorm','project','feature')),
       entity_id      TEXT NOT NULL,
       name           TEXT NOT NULL,
       status         TEXT,
       parent_type_id TEXT REFERENCES entities_new(type_id),
       parent_uuid    TEXT REFERENCES entities_new(uuid),
       artifact_path  TEXT,
       created_at     TEXT NOT NULL,
       updated_at     TEXT NOT NULL,
       metadata       TEXT
   );
   ```
5. Copies data from `entities` to `entities_new`, generating UUID v4 per row using Python (not SQL)
6. Populates `parent_uuid` from `parent_type_id` via a correlated UPDATE
7. Drops old `entities` table
8. Renames `entities_new` to `entities`
9. Recreates all 8 triggers (5 existing + 3 new)
10. Recreates all 4 indexes (3 existing + 1 new `idx_parent_uuid`)
11. Updates `schema_version` to `'2'` inside the transaction (atomic with DDL/DML)
12. Commits transaction
13. Re-enables foreign key enforcement via `PRAGMA foreign_keys = ON`
14. Runs `PRAGMA foreign_key_check` to verify FK integrity post-migration

**Error handling**: try/except wraps steps 2-12. On exception: rollback, re-enable foreign_keys, re-raise.

**Data copy strategy**: Read all rows from old table into Python list, generate UUID per row, bulk INSERT into new table. This avoids SQL-level uuid generation (SQLite has no uuid function by default) and ensures each row gets a unique v4 UUID.

**Parent UUID population**: After copying rows with `parent_uuid = NULL`, run a single UPDATE joining on `parent_type_id` to fill `parent_uuid` from the parent's newly-assigned UUID.

**Schema version ownership**: Migration 2 updates `schema_version` to `'2'` INSIDE its own transaction (before COMMIT). This ensures atomicity — if Migration 2 commits, the version is guaranteed to be updated. The outer `_migrate()` loop's schema_version update becomes a no-op (INSERT OR REPLACE with same value). This prevents a crash-window where the DB has v2 schema but v1 version, which would cause Migration 2 to re-run against an already-migrated table.

**Idempotency**: The outer `_migrate()` loop checks `schema_version` — Migration 2 only runs when version is 1.

### C2: Dual-Read Resolver (`_resolve_identifier`)

**Location**: `database.py`, private method on `EntityDatabase`

**Responsibility**: Accept either UUID or type_id string, return `(uuid, type_id)` tuple

**Approach**:
1. Normalize input to lowercase
2. Match against UUID v4 regex: `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`
3. If match: `SELECT uuid, type_id FROM entities WHERE uuid = ?`
4. If no match: `SELECT uuid, type_id FROM entities WHERE type_id = ?`
5. If no row found: raise `ValueError(f"Entity not found: {identifier!r}")`

**Compiled regex**: Store as module-level `_UUID_V4_RE = re.compile(...)` for performance.

### C3: EntityDatabase API Updates

**Location**: `database.py`, modifications to existing methods

**Changes per method**:

| Method | Input Change | Internal Change | Output Change |
|--------|-------------|-----------------|---------------|
| `register_entity()` | None (same params) | Generate UUID v4, INSERT with uuid column, always-SELECT after INSERT OR IGNORE | Returns UUID string (was type_id) |
| `set_parent()` | Accepts UUID or type_id for both params | Resolve both via `_resolve_identifier`, UPDATE both parent columns, CTE joins on uuid/parent_uuid | Returns UUID (was type_id) |
| `get_entity()` | Accepts UUID or type_id | Resolve via `_resolve_identifier` (catch ValueError → None) | Dict includes `uuid` field |
| `get_lineage()` | Accepts UUID or type_id | Resolve via `_resolve_identifier` (catch ValueError → []), CTEs join on uuid/parent_uuid | Each dict includes `uuid` field |
| `update_entity()` | Accepts UUID or type_id | Resolve via `_resolve_identifier` (let ValueError propagate), WHERE clause uses uuid | No change (returns None) |
| `export_lineage_markdown()` | Accepts UUID or type_id | Root-finding selects uuid, `_export_tree` CTE joins on uuid/parent_uuid | No change (returns markdown) |
| `_export_tree()` (internal) | None | `leaf_ids` built from `row["uuid"]`; child-check query uses `WHERE parent_uuid IN (...)` instead of `parent_type_id` | None |

### C4: Server Helpers Updates

**Location**: `server_helpers.py`

**Changes**:

- `render_tree()`: Key `by_id` on `uuid`, build `children` from `parent_uuid`, `root_type_id` parameter now receives UUID. Display labels unchanged (still use type_id via `_format_entity_label`). Note: `_render_node`'s internal `type_id` parameter is semantically overloaded — it carries UUID values post-migration despite the parameter name (per R33 naming retention). All internal dict lookups (`by_id[type_id]`, `children.get(type_id)`) operate on UUID keys. `_format_entity_label` receives the full entity dict and correctly accesses `entity["type_id"]` for display, so output is unaffected.
- `_process_register_entity()`: Capture UUID return, construct `type_id` from input params (`f"{entity_type}:{entity_id}"`), format message as `"Registered entity: {uuid} ({type_id})"`. No extra DB call needed.
- `_process_get_lineage()`: Pass `entities[0]["uuid"]` as root identifier to `render_tree()`. The 'Entity not found' error message (server_helpers.py `_process_get_lineage`) must handle UUID input: when `type_id` parameter contains a UUID, the error message should display it as-is rather than assuming it is a type_id. Use `f"Entity not found: {type_id}"` (the parameter name is retained per R33, but the displayed value is whatever the caller passed — UUID or type_id).

### C5: MCP Server Updates

**Location**: `entity_server.py`

**Changes**:

- `set_parent` handler: Capture UUID return value, format message with both identifiers. Use `get_entity()` to retrieve both uuid and type_id for child and parent.
- `update_entity` handler: Capture return and use `get_entity()` to get both identifiers for message.
- `get_entity` handler: Result dict now includes `uuid` field (automatic from DB layer).
- Other handlers: Transparent changes via dual-read in DB layer.

**Note on FK pragma and ALTER TABLE RENAME (SQLite >= 3.26.0)**: SQLite >= 3.26.0 automatically updates FK references when a table is renamed via `ALTER TABLE ... RENAME TO ...`, regardless of the `PRAGMA foreign_keys` setting (the pragma only controls FK enforcement, not reference updating during DDL). The `legacy_alter_table` pragma (default OFF) controls this behavior — when OFF (default), FK references are updated. We do NOT set `legacy_alter_table = ON`, so FK references in our schema are automatically updated during the RENAME step. The `PRAGMA foreign_key_check` post-migration verifies correctness. Python 3.9+ bundles SQLite >= 3.31.0, satisfying this requirement.

### C6: Test Updates

**Location**: `test_database.py`, `test_server_helpers.py`, `test_backfill.py`

**Existing test updates** (behavioral changes):
- `test_entities_has_10_columns` → assert 12 columns
- `test_entities_column_names` → add uuid, parent_uuid to expected list
- `test_type_id_is_primary_key` → assert uuid is PK, type_id is not
- `test_schema_version_is_1` → assert schema_version == "2"
- `test_has_five_triggers` → assert 8 triggers with updated name list
- `test_happy_path` (register) → assert UUID v4 format return
- `test_happy_path` (set_parent) → assert UUID return
- Server helper tests → updated message assertions
- **Raw SQL INSERT tests** must include uuid column: `test_entity_type_check_constraint`, `test_valid_entity_types_accepted`, `test_self_parent_on_insert`, and any other tests using direct `conn.execute('INSERT INTO entities ...')` must generate uuid via `str(uuid.uuid4())` and include it in the VALUES clause (uuid is NOT NULL PRIMARY KEY)

**New tests** (minimum 10 functions per AC-27):
1. `test_register_returns_uuid_v4_format`
2. `test_register_duplicate_returns_existing_uuid`
3. `test_resolve_identifier_with_uuid`
4. `test_resolve_identifier_with_type_id`
5. `test_resolve_identifier_not_found`
6. `test_migration_fresh_db`
7. `test_migration_populated_db_preserves_data`
8. `test_migration_populates_parent_uuid`
9. `test_migration_rollback_on_failure`
10. `test_uuid_immutability_trigger`
11. `test_self_parent_uuid_insert_trigger`
12. `test_self_parent_uuid_update_trigger`
13. `test_set_parent_mixed_identifiers`
14. `test_set_parent_updates_both_parent_columns`
15. `test_get_lineage_with_uuid`

## Technical Decisions

### TD-1: UUID as TEXT, not BLOB

**Decision**: Store UUID as TEXT (36 chars, lowercase with hyphens).

**Rationale**: TEXT is human-debuggable via sqlite3 CLI, matches `uuid.uuid4().__str__()` output directly, avoids conversion overhead. The ~45% space savings of BLOB is irrelevant for our dataset size (<1000 entities).

### TD-2: Python-Side UUID Generation During Migration

**Decision**: Read all existing rows into Python, generate UUID v4 per row, bulk INSERT into new table.

**Rationale**: SQLite has no built-in uuid() function. Using `uuid_generate_v4()` would require loading an extension. Python-side generation is simple, reliable, and consistent with runtime behavior (register_entity also uses Python uuid4()).

### TD-3: PRAGMA foreign_keys OFF/ON Around Table Recreation

**Decision**: Disable FKs before table recreation, re-enable after RENAME.

**Rationale**: SQLite's FK checking during table recreation can fail when the target table is temporarily absent (between DROP and RENAME). Disabling FKs during the window is the documented SQLite pattern. `PRAGMA foreign_key_check` after re-enabling verifies integrity.

**Constraint**: `PRAGMA foreign_keys = OFF` must be executed outside any transaction — it silently fails within one. The migration function sets it before `BEGIN IMMEDIATE` and re-enables after `COMMIT`.

### TD-4: Always-SELECT After INSERT OR IGNORE

**Decision**: Always follow `INSERT OR IGNORE` with `SELECT uuid FROM entities WHERE type_id = ?`.

**Rationale**: `cursor.lastrowid` retains its previous value on ignored inserts (does not reset to 0). `conn.total_changes` requires careful before/after comparison. The always-SELECT pattern is simple, correct, and has negligible overhead for a single-row query on an indexed column.

### TD-5: Retain Both parent_type_id and parent_uuid

**Decision**: Keep `parent_type_id` alongside `parent_uuid` indefinitely.

**Rationale**: Backward compatibility for existing callers that pass type_id strings. `set_parent()` atomically updates both columns, ensuring consistency. Removing `parent_type_id` is out of scope per PRD.

### TD-6: Module-Level Compiled Regex for UUID Detection

**Decision**: `_UUID_V4_RE = re.compile(r'^[0-9a-f]{8}-...$')` at module level.

**Rationale**: Compiled once, used on every `_resolve_identifier` call. Strict v4 pattern (position 13 = `4`, position 18 = `[89ab]`) prevents false matches. Lowercase normalization before matching handles mixed-case input.

### TD-7: Internal Queries Join on uuid/parent_uuid

**Decision**: All recursive CTEs (`_lineage_up`, `_lineage_down`, `_export_tree`, circular reference detection) join on `uuid`/`parent_uuid` columns.

**Rationale**: UUID is the canonical identity. Joining on type_id would bypass the PK index and undermine the migration's purpose. The uuid column is the PK (automatically indexed), making CTE joins efficient.

## Risks

### Risk 1: Migration Failure Leaves DB in Partial State

**Mitigation**: Explicit `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` wrapping all DDL+DML. On any exception, rollback restores original schema. `PRAGMA foreign_keys = OFF` is set before BEGIN and restored in both success and failure paths.

**Residual risk**: If the Python process is killed between COMMIT and `PRAGMA foreign_keys = ON`, the DB will have valid schema but FKs disabled until next `EntityDatabase.__init__` call (which always runs `_set_pragmas()`). This is acceptable.

### Risk 2: PRAGMA foreign_keys = OFF Silently Fails

**Mitigation**: The pragma is executed outside any transaction (before `BEGIN IMMEDIATE`). Verify by checking `PRAGMA foreign_keys` returns 0 before proceeding with DDL. If it doesn't return 0, the migration should abort.

### Risk 2a: Pre-existing FK Violations Cause Inconsistent parent_uuid

**Mitigation**: Run `PRAGMA foreign_key_check` before starting migration. If violations exist (dangling `parent_type_id` references), abort with clear error message listing the violations. This prevents the migration from silently creating entries where `parent_type_id` has a value but `parent_uuid` is NULL (because the referenced parent doesn't exist in `row_uuids`).

### Risk 3: Existing Tests Assume type_id Returns

**Mitigation**: Spec enumerates every method's before/after return type (R20). Test updates are scoped to behavioral changes, not wholesale rewrites. No test deletions — only assertion updates and additions.

### Risk 4: Backfill Variable Name Misleading

**Mitigation**: Backfill captures `register_entity()` return into variable named `type_id` (backfill.py:187). Post-migration this holds a UUID. The variable name is a misnomer but functionally irrelevant — `set_parent()` accepts either identifier type. Documented in spec (R31) as no-change-needed with explicit analysis.

### Risk 5: UUID/type_id Ambiguity

**Mitigation**: C8 constraint analysis confirms existing entity_id values cannot match UUID v4 format. The `type_id` format includes a colon, which is not a valid UUID character. Strict v4 regex with version nibble check prevents false matches.

## Interfaces

### I1: Migration 2 Function Signature

```python
def _migrate_to_uuid_pk(conn: sqlite3.Connection) -> None:
    """Migration 2: Add UUID primary key, retain type_id as UNIQUE.

    This migration manages its own transaction (BEGIN IMMEDIATE / COMMIT /
    ROLLBACK). The outer _migrate() commit is a no-op. Future migrations
    MUST follow this same pattern if they perform DDL operations.
    """
```

**Contract**:
- Input: open sqlite3.Connection with FKs and WAL mode already set
- Side effects: transforms entities table schema, adds triggers, indexes, updates schema_version to '2'
- Output: None (or raises on failure, triggering rollback)
- Idempotency: handled by `_migrate()` loop's schema_version check
- Schema version: updated INSIDE Migration 2's transaction (atomic with DDL/DML). Outer `_migrate()` loop's subsequent schema_version update is a no-op.

### I2: `_resolve_identifier` Method

```python
def _resolve_identifier(self, identifier: str) -> tuple[str, str]:
    """Resolve a UUID or type_id to (uuid, type_id) tuple.

    Parameters
    ----------
    identifier:
        Either a UUID v4 string or a type_id string.
        Must not be None (caller responsibility).
        Empty/whitespace strings are treated as type_id lookups.

    Returns
    -------
    tuple[str, str]
        (uuid, type_id) of the resolved entity.

    Raises
    ------
    ValueError
        If no entity matches the identifier.
    """
```

### I3: Updated `register_entity` Return

```python
def register_entity(
    self,
    entity_type: str,
    entity_id: str,
    name: str,
    artifact_path: str | None = None,
    status: str | None = None,
    parent_type_id: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Register an entity with INSERT OR IGNORE semantics.

    Returns
    -------
    str
        The UUID of the entity (newly generated or existing on duplicate).
    """
```

**Changed behavior**:
- Generates `entity_uuid = str(uuid.uuid4())` before INSERT
- INSERT includes `uuid` column value
- After INSERT OR IGNORE, always runs `SELECT uuid FROM entities WHERE type_id = ?`
- Returns the SELECT result (correct UUID whether new or existing)

### I4: Updated `set_parent` Internal Flow

```python
def set_parent(self, type_id: str, parent_type_id: str) -> str:
    """Set or change the parent of an entity.

    Parameters accept either UUID or type_id (dual-read).

    Returns
    -------
    str
        UUID of the updated entity.
    """
```

**Internal flow**:
1. `child_uuid, child_type_id = self._resolve_identifier(type_id)`
2. `parent_uuid, parent_type_id_resolved = self._resolve_identifier(parent_type_id)`
3. Self-parent check using UUIDs: `if child_uuid == parent_uuid: raise ValueError`
4. Circular reference CTE: walks `uuid`/`parent_uuid` chain
5. UPDATE: `SET parent_type_id = ?, parent_uuid = ?, updated_at = ? WHERE uuid = ?`
6. Return `child_uuid`

### I5: Updated `get_entity` Internal Flow

```python
def get_entity(self, type_id: str) -> dict | None:
    """Retrieve entity by UUID or type_id. Returns None if not found."""
```

**Internal flow**:
1. Try `_resolve_identifier(type_id)` → catch `ValueError` → return `None`
2. `SELECT * FROM entities WHERE uuid = ?` using resolved uuid
3. Return `dict(row)` (now includes `uuid` and `parent_uuid` columns)

### I6: Updated Lineage CTEs

**`_lineage_up` CTE** (after migration):
```sql
WITH RECURSIVE ancestors(uid, depth) AS (
    SELECT ?, 0
    UNION ALL
    SELECT e.parent_uuid, a.depth + 1
    FROM entities e
    JOIN ancestors a ON e.uuid = a.uid
    WHERE e.parent_uuid IS NOT NULL
      AND a.depth < ?
)
SELECT e.* FROM ancestors a
JOIN entities e ON e.uuid = a.uid
ORDER BY a.depth DESC
```

**`_lineage_down` CTE** (after migration):
```sql
WITH RECURSIVE descendants(uid, depth) AS (
    SELECT ?, 0
    UNION ALL
    SELECT e.uuid, d.depth + 1
    FROM entities e
    JOIN descendants d ON e.parent_uuid = d.uid
    WHERE d.depth < ?
)
SELECT e.* FROM descendants d
JOIN entities e ON e.uuid = d.uid
ORDER BY d.depth ASC
```

**`_export_tree` CTE** (after migration):
```sql
WITH RECURSIVE tree(uid, depth) AS (
    SELECT ?, 0
    UNION ALL
    SELECT e.uuid, t.depth + 1
    FROM entities e
    JOIN tree t ON e.parent_uuid = t.uid
    WHERE t.depth < ?
)
SELECT e.*, t.depth FROM tree t
JOIN entities e ON e.uuid = t.uid
ORDER BY t.depth ASC, e.entity_type, e.name
```

**`_export_tree` truncation check** (database.py `_export_tree` method): When `max_depth` is reached, the method checks for children beyond the depth limit to append a `"..."` indicator. Post-migration, this check must use `uuid`/`parent_uuid`: extract `leaf_ids` as `row['uuid']` from the deepest level, then check `SELECT 1 FROM entities WHERE parent_uuid IN ({placeholders}) LIMIT 1`. Currently uses `type_id`/`parent_type_id` — must be updated.

**Root-finding query** (when type_id=None in `export_lineage_markdown`):
```sql
SELECT uuid FROM entities WHERE parent_type_id IS NULL
ORDER BY entity_type, name
```
Note: uses `parent_type_id IS NULL` (not `parent_uuid IS NULL`) because both columns are kept in sync — either works. `parent_type_id` is used here for consistency with existing behavior.

### I7: Updated `render_tree` Signature

```python
def render_tree(
    entities: list[dict], root_type_id: str, max_depth: int = 50
) -> str:
```

**Internal changes** (parameter name retained per R33):
- `by_id` keyed on `entity["uuid"]` instead of `entity["type_id"]`
- `children` built from `entity.get("parent_uuid")` instead of `entity.get("parent_type_id")`
- `root_type_id` compared against `entity["uuid"]` in by_id lookup
- `_render_node` traverses using uuid keys
- `_format_entity_label` unchanged — still displays `entity["type_id"]`

### I8: Updated MCP Tool Messages

**`register_entity` handler**:
```python
uuid = db.register_entity(...)
type_id = f"{entity_type}:{entity_id}"  # construct from input params, avoids extra DB call
return f"Registered entity: {uuid} ({type_id})"
```

**`set_parent` handler**:
```python
child_uuid = db.set_parent(type_id, parent_type_id)
child = db.get_entity(child_uuid)
parent = db.get_entity(child["parent_uuid"])
return f"Set parent of {child_uuid} ({child['type_id']}) to {child['parent_uuid']} ({parent['type_id']})"
```

**`update_entity` handler**:
```python
db.update_entity(type_id, ...)
entity = db.get_entity(type_id)  # dual-read resolves to uuid internally
return f"Updated entity: {entity['uuid']} ({entity['type_id']})"
```

### I9: New Schema (Post-Migration 2)

```sql
CREATE TABLE entities (
    uuid           TEXT NOT NULL PRIMARY KEY,
    type_id        TEXT NOT NULL UNIQUE,
    entity_type    TEXT NOT NULL CHECK(entity_type IN ('backlog','brainstorm','project','feature')),
    entity_id      TEXT NOT NULL,
    name           TEXT NOT NULL,
    status         TEXT,
    parent_type_id TEXT REFERENCES entities(type_id),
    parent_uuid    TEXT REFERENCES entities(uuid),
    artifact_path  TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    metadata       TEXT
);
```

**Column count**: 12 (was 10)
**Trigger count**: 8 (was 5)
**Index count**: 4 (was 3 — new `idx_parent_uuid` needed for child-lookup queries in CTEs; PK index on uuid covers uuid lookups but not `WHERE parent_uuid = ?` scans)

**FK to UNIQUE columns**: `parent_type_id REFERENCES entities(type_id)` targets a UNIQUE column, not the PK. SQLite supports FK references to UNIQUE columns per SQL standard. `PRAGMA foreign_key_check` verifies both PK-targeted and UNIQUE-targeted FK relationships.

**parent_uuid nullable**: `parent_uuid` has no NOT NULL constraint, matching `parent_type_id` behavior — root entities have both parent columns as NULL.

### I10: Migration 2 Data Copy Strategy

```python
# Step 1: Read all existing rows
rows = conn.execute("SELECT * FROM entities").fetchall()

# Step 2: Generate UUID per row
import uuid as uuid_mod
row_uuids = {}
for row in rows:
    row_uuids[row["type_id"]] = str(uuid_mod.uuid4())

# Step 3: INSERT into entities_new with uuid
# parent_uuid intentionally omitted — populated in Step 4 via UPDATE;
# SQLite defaults omitted column to NULL
for row in rows:
    conn.execute(
        "INSERT INTO entities_new (uuid, type_id, entity_type, entity_id, "
        "name, status, parent_type_id, artifact_path, created_at, "
        "updated_at, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (row_uuids[row["type_id"]], row["type_id"], row["entity_type"],
         row["entity_id"], row["name"], row["status"],
         row["parent_type_id"], row["artifact_path"],
         row["created_at"], row["updated_at"], row["metadata"]),
    )

# Step 4: Populate parent_uuid from parent_type_id
for row in rows:
    if row["parent_type_id"] is not None:
        parent_uuid = row_uuids.get(row["parent_type_id"])
        if parent_uuid:
            conn.execute(
                "UPDATE entities_new SET parent_uuid = ? WHERE type_id = ?",
                (parent_uuid, row["type_id"]),
            )
```
