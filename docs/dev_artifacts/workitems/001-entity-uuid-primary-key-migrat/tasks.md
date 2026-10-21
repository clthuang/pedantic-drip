# Tasks: Entity UUID Primary Key Migration

## Phase 1: Schema Foundation

**File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
**Test file:** `plugins/iflow/hooks/lib/entity_registry/test_database.py`

### 1.1 Migration 2 Schema DDL

- [ ] **T1.1.1: Write test_migration_fresh_db (schema shape only)**
  Create `test_migration_fresh_db` in `test_database.py`. First, add a stub to `database.py` so the import succeeds:
  ```python
  def _migrate_to_uuid_pk(conn):
      raise NotImplementedError("Migration 2 not yet implemented")
  ```
  Test calls `_create_initial_schema(conn)` to build v1 DB, then calls `_migrate_to_uuid_pk(conn)` directly. Asserts: 12 columns exist, uuid is PK, type_id is UNIQUE, parent_uuid column exists. Does NOT assert triggers or indexes (deferred to 1.3).
  **Done:** Test file imports cleanly (stub exists). Running pytest shows 1 failed test with `NotImplementedError` at the call site, not an `ImportError` at collection time.

- [ ] **T1.1.2: Add imports and UUID regex constant**
  Add `import uuid as uuid_mod` and `import re` at module top of `database.py`. Add module-level constant:
  ```python
  _UUID_V4_RE = re.compile(
      r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  )
  ```
  **Done:** Imports present, `_UUID_V4_RE.match("550e8400-e29b-41d4-a716-446655440000")` returns a match object.

- [ ] **T1.1.3: Create _migrate_to_uuid_pk function — PRAGMA and BEGIN**
  Create `def _migrate_to_uuid_pk(conn):` with docstring per I1. Implement steps 1 and 1b only:
  ```python
  conn.execute("PRAGMA foreign_keys = OFF")
  fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
  if fk_status != 0:
      raise RuntimeError(
          "PRAGMA foreign_keys = OFF did not take effect — aborting migration"
      )
  conn.execute("BEGIN IMMEDIATE")
  ```
  Then step 3 — pre-migration FK validation:
  ```python
  fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
  if fk_violations:
      conn.rollback()
      raise RuntimeError(f"FK violations found before migration: {fk_violations}")
  ```
  **Done:** Function exists. PRAGMA OFF executes and verifies. BEGIN IMMEDIATE starts transaction. FK check runs pre-migration.
  **Note:** This function body will be restructured in T1.4.2 — the PRAGMA OFF+verify block will move before a try block, and BEGIN IMMEDIATE through FK check will move inside try. Write the code as listed here; T1.4.2 is an explicit refactor step that wraps it.

- [ ] **T1.1.4: Add CREATE TABLE entities_new DDL**
  Inside `_migrate_to_uuid_pk`, after FK check, add step 4:
  ```python
  conn.execute("""
      CREATE TABLE entities_new (
          uuid           TEXT NOT NULL PRIMARY KEY,
          type_id        TEXT NOT NULL UNIQUE,
          entity_type    TEXT NOT NULL CHECK(entity_type IN (
              'backlog','brainstorm','project','feature')),
          entity_id      TEXT NOT NULL,
          name           TEXT NOT NULL,
          status         TEXT,
          parent_type_id TEXT REFERENCES entities_new(type_id),
          parent_uuid    TEXT REFERENCES entities_new(uuid),
          artifact_path  TEXT,
          created_at     TEXT NOT NULL,
          updated_at     TEXT NOT NULL,
          metadata       TEXT
      )
  """)
  ```
  **Done:** `test_migration_fresh_db` passes (green) for schema shape assertions (12 columns, uuid PK, type_id UNIQUE).

### 1.2 Migration 2 Data Copy

- [ ] **T1.2.1: Write test_migration_populated_db_preserves_data**
  Create test that builds v1 DB via `_create_initial_schema(conn)`, inserts 3+ entities using v1 INSERT (no uuid column), calls `_migrate_to_uuid_pk(conn)`, verifies: (a) all rows exist with correct field values, (b) each row has a valid UUID v4 in uuid column matching `_UUID_V4_RE`.
  **Done:** Test exists, runs red (migration function doesn't copy data yet).

- [ ] **T1.2.2: Write test_migration_populates_parent_uuid**
  Create test that builds v1 DB, inserts parent entity + child entity with `parent_type_id` referencing parent, calls migration, verifies child's `parent_uuid` equals parent's `uuid`.
  **Done:** Test exists, runs red.

- [ ] **T1.2.3: Implement data copy — read rows, generate UUIDs, INSERT**
  In `_migrate_to_uuid_pk`, after CREATE TABLE, implement I10 steps 1-3:
  ```python
  # Step 1: Read all existing rows
  rows = conn.execute("SELECT * FROM entities").fetchall()

  # Step 2: Generate UUID per row
  row_uuids = {}
  for row in rows:
      row_uuids[row["type_id"]] = str(uuid_mod.uuid4())

  # Step 3: INSERT into entities_new (parent_uuid omitted — defaults NULL)
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
  ```
  **Done:** Data rows copied with UUIDs generated. `test_migration_populated_db_preserves_data` partially passes (data + UUIDs correct, parent_uuid still NULL).

- [ ] **T1.2.4: Implement parent_uuid population**
  After INSERT loop, implement I10 step 4:
  ```python
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
  **Done:** `test_migration_populates_parent_uuid` passes.

- [ ] **T1.2.5: Add DROP old table and RENAME**
  After parent_uuid population, add steps 7-8:
  ```python
  conn.execute("DROP TABLE entities")
  conn.execute("ALTER TABLE entities_new RENAME TO entities")
  ```
  **Done:** `test_migration_populated_db_preserves_data` fully passes. Old table gone, new table named `entities`.

### 1.3 Trigger + Index Recreation

- [ ] **T1.3.1: Write trigger tests — uuid immutability and self-parent UUID**
  Create three tests, each calls `_create_initial_schema(conn)` then `_migrate_to_uuid_pk(conn)`:
  - `test_uuid_immutability_trigger`: INSERT entity with all NOT NULL columns (use `test_uuid = str(uuid.uuid4())`), then attempt `UPDATE entities SET uuid = 'new-uuid' WHERE type_id = ?`, assert `sqlite3.IntegrityError` raised with `"uuid is immutable"`.
  - `test_self_parent_uuid_insert_trigger`: Use a pre-generated UUID: `test_uuid = str(uuid.uuid4())`. INSERT with parent_uuid = uuid (same value):
    ```python
    conn.execute(
        "INSERT INTO entities (uuid, type_id, entity_type, entity_id, name, "
        "created_at, updated_at, parent_uuid) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (test_uuid, "feature:self", "feature", "self", "Self",
         "2026-01-01T00:00:00", "2026-01-01T00:00:00", test_uuid),
    )
    ```
    Assert `sqlite3.IntegrityError` raised with `"entity cannot be its own parent"`.
  - `test_self_parent_uuid_update_trigger`: INSERT entity (no parent_uuid), then `UPDATE entities SET parent_uuid = uuid WHERE type_id = ?`, assert `sqlite3.IntegrityError` raised with `"entity cannot be its own parent"`.
  **Done:** Tests exist, run red.

- [ ] **T1.3.2: Extend test_migration_fresh_db for triggers and indexes**
  Add assertions to `test_migration_fresh_db`:
  - 8 triggers (sorted): `enforce_immutable_created_at`, `enforce_immutable_entity_type`, `enforce_immutable_type_id`, `enforce_immutable_uuid`, `enforce_no_self_parent`, `enforce_no_self_parent_update`, `enforce_no_self_parent_uuid_insert`, `enforce_no_self_parent_uuid_update`
  - 4 indexes (sorted): `idx_entity_type`, `idx_parent_type_id`, `idx_parent_uuid`, `idx_status`
  These assertions go green only after 1.3.3-1.3.4 are implemented.
  **Done:** Assertions added to existing test.

- [ ] **T1.3.3: Implement trigger recreation — all 8 triggers**
  After RENAME, create all 8 triggers using `CREATE TRIGGER IF NOT EXISTS` for all triggers (matches Migration 1 DDL style and prevents failures on partial-run recovery). **Existing 5** (based on Migration 1 `_create_initial_schema`, with IS NOT NULL guard added intentionally to self-parent triggers — the original triggers omit the guard, but NULL = type_id evaluates to UNKNOWN in SQL so the trigger never fires on NULL anyway; the guard makes intent explicit and matches the new uuid self-parent triggers):
  ```sql
  CREATE TRIGGER IF NOT EXISTS enforce_immutable_type_id
      BEFORE UPDATE OF type_id ON entities
      BEGIN SELECT RAISE(ABORT, 'type_id is immutable'); END;

  CREATE TRIGGER IF NOT EXISTS enforce_immutable_entity_type
      BEFORE UPDATE OF entity_type ON entities
      BEGIN SELECT RAISE(ABORT, 'entity_type is immutable'); END;

  CREATE TRIGGER IF NOT EXISTS enforce_immutable_created_at
      BEFORE UPDATE OF created_at ON entities
      BEGIN SELECT RAISE(ABORT, 'created_at is immutable'); END;

  CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent
      BEFORE INSERT ON entities
      WHEN NEW.parent_type_id IS NOT NULL AND NEW.parent_type_id = NEW.type_id
      BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END;

  CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_update
      BEFORE UPDATE OF parent_type_id ON entities
      WHEN NEW.parent_type_id IS NOT NULL AND NEW.parent_type_id = NEW.type_id
      BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END;
  ```
  **New 3** (R10, R12):
  ```sql
  CREATE TRIGGER IF NOT EXISTS enforce_immutable_uuid
      BEFORE UPDATE OF uuid ON entities
      BEGIN SELECT RAISE(ABORT, 'uuid is immutable'); END;

  CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_uuid_insert
      BEFORE INSERT ON entities
      WHEN NEW.parent_uuid IS NOT NULL AND NEW.parent_uuid = NEW.uuid
      BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END;

  CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_uuid_update
      BEFORE UPDATE OF parent_uuid ON entities
      WHEN NEW.parent_uuid IS NOT NULL AND NEW.parent_uuid = NEW.uuid
      BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END;
  ```
  **Done:** All 8 triggers created. Trigger tests from T1.3.1 pass.

- [ ] **T1.3.4: Implement index recreation — all 4 indexes**
  Recreate 3 existing indexes + 1 new:
  ```sql
  CREATE INDEX idx_entity_type ON entities(entity_type);
  CREATE INDEX idx_status ON entities(status);
  CREATE INDEX idx_parent_type_id ON entities(parent_type_id);
  CREATE INDEX idx_parent_uuid ON entities(parent_uuid);
  ```
  **Done:** 4 indexes exist. `test_migration_fresh_db` fully passes (schema + triggers + indexes).

### 1.4 Migration Error Handling + Idempotency

- [ ] **T1.4.1: Write test_migration_rollback_on_failure**
  Create test that builds v1 DB with 2+ entities. Call `_migrate_to_uuid_pk(wrapped_conn)` with a Python wrapper that intercepts the DROP TABLE call. Note: `sqlite3.Connection.execute` is a C extension method — `monkeypatch.setattr` cannot patch it on instances. Use a thin wrapper class instead:
  ```python
  class FailOnDropConn:
      """Proxy that delegates to real conn but raises on DROP TABLE."""
      def __init__(self, real_conn):
          self._real = real_conn
      def execute(self, sql, *args, **kwargs):
          if isinstance(sql, str) and "DROP TABLE" in sql:
              raise RuntimeError("injected")
          return self._real.execute(sql, *args, **kwargs)
      def __getattr__(self, name):
          return getattr(self._real, name)

  wrapped = FailOnDropConn(conn)
  with pytest.raises(RuntimeError, match="injected"):
      _migrate_to_uuid_pk(wrapped)
  ```
  After the raised exception, verify on the ORIGINAL `conn` (not `wrapped`): original v1 schema intact (type_id is PK, no uuid column), `_metadata.schema_version` remains `'1'`, all data preserved.
  **Done:** Test exists, runs red.

- [ ] **T1.4.2: Wrap migration in try/except/finally**
  **Pre-step:** Read the current `_migrate_to_uuid_pk` function body in full. Verify it contains: PRAGMA OFF block (T1.1.3), BEGIN IMMEDIATE (T1.1.3), FK check (T1.1.3), CREATE TABLE (T1.1.4), data copy steps (T1.2.3-T1.2.4), DROP+RENAME (T1.2.5), triggers (T1.3.3), indexes (T1.3.4). The refactor only reorganizes existing code — no new logic is added except the except/finally blocks and schema_version UPDATE.
  Restructure `_migrate_to_uuid_pk` by moving the PRAGMA OFF + verify block (from T1.1.3) to BEFORE a new try block. The try block begins with `conn.execute("BEGIN IMMEDIATE")`. Move ALL code from T1.1.3's BEGIN IMMEDIATE onward (FK check, CREATE TABLE, data copy, DROP, RENAME, triggers, indexes) inside the try block. Add schema_version update, commit, except/rollback, and finally/PRAGMA ON. Full skeleton:
  ```python
  def _migrate_to_uuid_pk(conn):
      """Migration 2: ... (docstring per I1)"""
      # OUTSIDE try — PRAGMA cannot run inside transaction
      conn.execute("PRAGMA foreign_keys = OFF")
      fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
      if fk_status != 0:
          raise RuntimeError(
              "PRAGMA foreign_keys = OFF did not take effect — aborting migration"
          )
      try:
          conn.execute("BEGIN IMMEDIATE")
          # Pre-migration FK check (from T1.1.3)
          fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
          if fk_violations:
              conn.rollback()
              raise RuntimeError(f"FK violations found before migration: {fk_violations}")
          # CREATE TABLE entities_new (from T1.1.4)
          # ... all DDL/DML from T1.1.4 through T1.3.4 ...
          # Data copy (T1.2.3, T1.2.4)
          # DROP + RENAME (T1.2.5)
          # Triggers (T1.3.3)
          # Indexes (T1.3.4)
          # Update schema_version inside transaction
          conn.execute(
              "INSERT INTO _metadata(key, value) VALUES('schema_version', '2') "
              "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
          )
          conn.commit()
      except Exception:
          conn.rollback()
          raise
      finally:
          # Re-enable FKs — runs on both success and failure
          conn.execute("PRAGMA foreign_keys = ON")
      # Post-migration FK check — outside try, after commit
      post_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
      if post_violations:
          raise RuntimeError(f"FK violations after migration: {post_violations}")
  ```
  Key restructure: the PRAGMA OFF and verify from T1.1.3 are now BEFORE the try block (they were previously at the start of the function body without try wrapping). Everything from BEGIN IMMEDIATE onward moves inside try.
  **Done:** `test_migration_rollback_on_failure` passes (rollback restores v1 schema, PRAGMA ON always re-enabled).

- [ ] **T1.4.3: Register in MIGRATIONS dict and verify idempotency**
  Add `2: _migrate_to_uuid_pk` to the `MIGRATIONS` dict in `database.py`.
  **Done:** `EntityDatabase(":memory:")` initializes with `schema_version='2'`.

- [ ] **T1.4.4: Write test_init_already_migrated_db**
  Create test that constructs v2 DB (call `_create_initial_schema` + `_migrate_to_uuid_pk` directly), then creates `EntityDatabase` on the same DB file. Verify: no errors, `schema_version` remains `'2'`, migration does not re-run (row count unchanged).
  **Done:** Test exists, passes (idempotency confirmed).

## Phase 2: Core Database API

**File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
**Test file:** `plugins/iflow/hooks/lib/entity_registry/test_database.py`

**Parallel group A:** T2.1.x and T2.2.x are independent — can be implemented in parallel.
**Parallel group B:** T2.4.x and T2.5.1-T2.5.2 are independent after T2.3.x completes. **Note:** T2.5.3 (update_entity) internally calls `self.get_entity()` — T2.4.2 must complete before T2.5.3 begins.

### 2.1 `_resolve_identifier` Method

- [ ] **T2.1.1: Write _resolve_identifier tests**
  Create three tests (each registers an entity first via `db.register_entity(...)`, captures the returned UUID):
  - `test_resolve_identifier_with_uuid`: Call `db._resolve_identifier(uuid)`, assert returns `(uuid, "feature:test-id")`.
  - `test_resolve_identifier_with_type_id`: Call `db._resolve_identifier("feature:test-id")`, assert returns `(uuid, "feature:test-id")`.
  - `test_resolve_identifier_not_found`: Call `db._resolve_identifier("nonexistent")`, assert raises `ValueError` with message containing `"nonexistent"`.
  **Done:** Tests exist, run red (`AttributeError: 'EntityDatabase' object has no attribute '_resolve_identifier'`).

- [ ] **T2.1.2: Implement _resolve_identifier**
  Add method per I2:
  ```python
  def _resolve_identifier(self, identifier: str) -> tuple[str, str]:
      normalized = identifier.lower()
      if _UUID_V4_RE.match(normalized):
          row = self._conn.execute(
              "SELECT uuid, type_id FROM entities WHERE uuid = ?",
              (normalized,),
          ).fetchone()
      else:
          row = self._conn.execute(
              "SELECT uuid, type_id FROM entities WHERE type_id = ?",
              (normalized,),
          ).fetchone()
      if row is None:
          raise ValueError(f"Entity not found: {identifier!r}")
      return (row["uuid"], row["type_id"])
  ```
  **Done:** All three `_resolve_identifier` tests pass.

### 2.2 `register_entity` Update

- [ ] **T2.2.1: Write register_entity UUID tests**
  Create two tests:
  - `test_register_returns_uuid_v4_format`: Call `db.register_entity("feature", "test", "Test")`, assert return value matches `_UUID_V4_RE`.
  - `test_register_duplicate_returns_existing_uuid`: Register same entity twice, assert both calls return the same UUID string.
  **Done:** Tests exist, run red (register currently returns type_id string, not UUID).

- [ ] **T2.2.2: Update register_entity to generate and return UUID**
  In `register_entity` method body:
  1. Before the existing INSERT, add: `entity_uuid = str(uuid_mod.uuid4())`
  2. Add `uuid` to the INSERT column list and `entity_uuid` to the VALUES tuple
  3. After INSERT OR IGNORE (before the existing `self._conn.commit()`), add: `result = self._conn.execute("SELECT uuid FROM entities WHERE type_id = ?", (type_id,)).fetchone()`
  4. Change the return statement from `return type_id` to `return result["uuid"]`
  5. Update existing tests that assert type_id return values so the suite stays green:
     - `test_insert_or_ignore_idempotency`: change return assertion to check UUID v4 format (`_UUID_V4_RE.match(result)`)
     - `TestRegisterEntity.test_happy_path`: change `assert result == "feature:test-id"` to `assert _UUID_V4_RE.match(result)`
     - `TestRegisterEntity.test_type_id_auto_constructed`: same UUID format assertion
     - `TestRegisterEntity.test_all_valid_types`: same UUID format assertion
  **Done:** Both new register UUID tests pass AND all 4 updated existing tests pass. Suite stays green.

### 2.3 `set_parent` Update

- [ ] **T2.3.1: Write set_parent tests**
  Create two tests:
  - `test_set_parent_mixed_identifiers`: Register parent + child, call `db.set_parent(child_uuid, parent_type_id)` (UUID for child, type_id for parent), assert returns child's UUID.
  - `test_set_parent_updates_both_parent_columns`: After set_parent, query child entity, assert both `parent_type_id` matches parent's type_id AND `parent_uuid` matches parent's uuid.
  **Done:** Tests exist, run red.

- [ ] **T2.3.2: Update set_parent implementation**
  Read the existing `set_parent` method body before editing. Replace the entire body with:
  1. Resolve both params (the raw `parent_type_id` parameter is intentionally shadowed by `parent_type_id_resolved` — replace ALL uses of the raw parameter in the method body after this point):
     ```python
     child_uuid, child_type_id = self._resolve_identifier(type_id)
     parent_uuid, parent_type_id_resolved = self._resolve_identifier(parent_type_id)
     ```
  2. Self-parent check using UUIDs:
     ```python
     if child_uuid == parent_uuid:
         raise ValueError("entity cannot be its own parent")
     ```
  3. Circular reference CTE (replaces existing CTE — use `parent_uuid` and `child_uuid` variables, not the raw `parent_type_id` parameter):
     ```sql
     WITH RECURSIVE anc(uid) AS (
         SELECT parent_uuid FROM entities WHERE uuid = :parent_uuid
         UNION ALL
         SELECT e.parent_uuid FROM entities e
         JOIN anc a ON e.uuid = a.uid
         WHERE e.parent_uuid IS NOT NULL
     )
     SELECT 1 FROM anc WHERE uid = :child_uuid
     ```
     Bind `{"parent_uuid": parent_uuid, "child_uuid": child_uuid}`.
  4. UPDATE both parent columns (use `parent_type_id_resolved`, not the raw `parent_type_id` parameter):
     ```sql
     UPDATE entities
     SET parent_type_id = ?, parent_uuid = ?, updated_at = ?
     WHERE uuid = ?
     ```
     Bind `(parent_type_id_resolved, parent_uuid, now, child_uuid)`.
  5. `self._conn.commit()` (existing)
  6. `return child_uuid`
  **Done:** Both set_parent tests pass. No raw `parent_type_id` parameter used in SQL bindings.

### 2.4 `get_entity` Update

- [ ] **T2.4.1: Write get_entity dual-read tests**
  Create three tests:
  - `test_get_entity_by_uuid`: Register entity, get by UUID, assert dict includes `uuid` field.
  - `test_get_entity_by_type_id`: Register entity, get by type_id, assert same entity returned.
  - `test_get_entity_not_found_returns_none`: Call `db.get_entity("nonexistent")`, assert returns `None`.
  **Done:** Tests exist, run red.

- [ ] **T2.4.2: Update get_entity implementation**
  Replace lookup logic:
  ```python
  try:
      uuid, _ = self._resolve_identifier(type_id)
  except ValueError:
      return None
  row = self._conn.execute(
      "SELECT * FROM entities WHERE uuid = ?", (uuid,)
  ).fetchone()
  return dict(row) if row else None
  ```
  **Done:** All three get_entity tests pass.

### 2.5 `get_lineage` + `update_entity` Updates

- [ ] **T2.5.1: Write get_lineage and update_entity UUID tests**
  Create two tests:
  - `test_get_lineage_with_uuid`: Register grandparent → parent → child chain, call `db.get_lineage(child_uuid, direction="up")`, verify returns correct 3-entity ancestry with `uuid` field in each dict.
  - `test_update_entity_with_uuid`: Register entity, call `db.update_entity(uuid, name="New Name")`, verify name changed via `db.get_entity(uuid)`.
  **Done:** Tests exist, run red.

- [ ] **T2.5.2: Update get_lineage implementation**
  1. Replace the current identifier lookup at the start of `get_lineage` with `_resolve_identifier`. This replaces whatever type_id-based lookup exists:
     ```python
     try:
         resolved_uuid, _ = self._resolve_identifier(type_id)
     except ValueError:
         return []
     ```
  2. Replace `_lineage_up` CTE with (bind `resolved_uuid` from step 1, not the raw `type_id` parameter):
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
     Bind `(resolved_uuid, max_depth)`.
  3. Replace `_lineage_down` CTE with:
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
     Bind `(resolved_uuid, max_depth)`.
  **Done:** `test_get_lineage_with_uuid` passes.

- [ ] **T2.5.3: Update update_entity implementation**
  Replace identifier resolution. Use `self.get_entity(identifier)` (not `_resolve_identifier` directly) because the existing `update_entity` body uses `existing["metadata"]` for a JSON shallow merge further down in the method — the full entity dict is required, not just the UUID:
  ```python
  existing = self.get_entity(identifier)
  if existing is None:
      raise ValueError(f"Entity not found: {identifier!r}")
  uuid = existing["uuid"]
  ```
  Then change WHERE clause from `WHERE type_id = ?` to `WHERE uuid = ?`, binding `uuid`.
  **Done:** `test_update_entity_with_uuid` passes.

### 2.6 `export_lineage_markdown` + `_export_tree` Updates

- [ ] **T2.6.1: Write export UUID internals test**
  Create `test_export_uses_uuid_internally`: register 3 entities with parent-child relationships (grandparent → parent → child), call `export_lineage_markdown()`, assert output contains type_id strings (e.g., `"feature:001-slug"`) and does NOT contain UUID patterns (no matches against `_UUID_V4_RE` in output text).
  **Done:** Test exists, runs red.

- [ ] **T2.6.2: Update export_lineage_markdown and _export_tree**
  1. Root-finding query (when `type_id` param is None): change from `SELECT type_id` to:
     ```sql
     SELECT uuid FROM entities WHERE parent_type_id IS NULL
     ORDER BY entity_type, name
     ```
     Pass each `row["uuid"]` to `_export_tree`.
  2. When `type_id` param provided: resolve via `_resolve_identifier` to get uuid, pass uuid to `_export_tree`.
  3. Update `_export_tree` CTE:
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
     Bind `(root_uuid, max_depth)`.
  4. Update truncation check. Locate it: `grep -n 'parent_type_id IN\|leaf_ids\|LIMIT 1' plugins/iflow/hooks/lib/entity_registry/database.py`. Find the `SELECT 1 FROM entities WHERE parent_type_id IN (...) LIMIT 1` query. Replace: build `leaf_ids` from `row["uuid"]` (not `row["type_id"]`) at deepest level, and change WHERE clause from `parent_type_id` to `parent_uuid`:
     ```sql
     SELECT 1 FROM entities WHERE parent_uuid IN ({placeholders}) LIMIT 1
     ```
     where `{placeholders}` is `",".join("?" * len(leaf_ids))`.
  **Done:** `test_export_uses_uuid_internally` passes.

## Phase 3: Server Helpers

**File:** `plugins/iflow/hooks/lib/entity_registry/server_helpers.py`
**Test file:** `plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py`

**Sequential:** T3.1.x must complete before T3.2.x (process handlers pass uuid values to render_tree).

### 3.1 `render_tree` Internal Updates

- [ ] **T3.1.1: Update _make_entity test helper**
  In `test_server_helpers.py`, add a hardcoded UUID mapping dict and update `_make_entity`:
  ```python
  ENTITY_UUIDS = {
      "project:P001": "550e8400-e29b-41d4-a716-446655440001",
      "feature:001-slug": "550e8400-e29b-41d4-a716-446655440002",
      "feature:002-slug": "550e8400-e29b-41d4-a716-446655440003",
      "brainstorm:20260101-test": "550e8400-e29b-41d4-a716-446655440004",
      "backlog:00001": "550e8400-e29b-41d4-a716-446655440005",
  }
  ```
  Update `_make_entity` to include `uuid` and `parent_uuid` fields:
  ```python
  entity["uuid"] = ENTITY_UUIDS.get(entity["type_id"], str(uuid.uuid4()))
  entity["parent_uuid"] = (
      ENTITY_UUIDS.get(entity["parent_type_id"])
      if entity.get("parent_type_id") else None
  )
  ```
  Run render_tree tests to verify they compile: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py -k "render_tree" -v`
  **Done:** Existing render_tree tests compile without KeyError and pass. Verify with: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py -k "render_tree" -v --tb=short`. **Known failing tests at this point** (NOT regressions — intentionally deferred to T5.1.4): `test_process_register_entity_new`, `test_process_register_entity_existing`, and any other tests asserting `"Registered entity: feature:..."` message format. These are fixed in T5.1.4 when the dual-identity format is applied.

- [ ] **T3.1.2: Update render_tree internals**
  Key `by_id` on `entity["uuid"]`, build `children` from `entity.get("parent_uuid")`, root lookup uses uuid. Update `_render_node` to traverse uuid keys. `_format_entity_label` unchanged.
  **Done:** All existing render_tree tests pass with uuid-keyed internals. Display unchanged (still shows type_id via `_format_entity_label`).

### 3.2 Process Handler Updates

- [ ] **T3.2.1: Update _process_register_entity**
  Capture UUID return from `db.register_entity(...)`. Construct type_id from inputs: `f"{entity_type}:{entity_id}"`. Format message: `f"Registered entity: {uuid} ({type_id})"`.
  **Done:** Register handler returns message like `"Registered entity: 550e8400-... (feature:001-slug)"`.

- [ ] **T3.2.2: Write test and update _process_get_lineage**
  **Pre-step:** Verify patch target by confirming how render_tree is referenced in server_helpers.py: `grep -n "import render_tree\|from.*import.*render_tree\|def render_tree" plugins/iflow/hooks/lib/entity_registry/server_helpers.py`. If render_tree is defined in this file (not imported), the patch target `'entity_registry.server_helpers.render_tree'` is correct. If imported from elsewhere, adjust the patch target to match the import path.
  Write `test_process_get_lineage_passes_uuid` in `test_server_helpers.py`. Import: `from entity_registry.server_helpers import render_tree` (needed for `wraps=` target). Create `db = EntityDatabase(":memory:")` inline (same pattern as other test_server_helpers.py tests). Register grandparent → parent → child chain via `db.register_entity(...)`. Call `_process_get_lineage(db, child_type_id)` with `unittest.mock.patch('entity_registry.server_helpers.render_tree', wraps=render_tree)` active (patch target is the reference in the calling module where _process_get_lineage looks up render_tree). Assert the **second** positional argument (`mock_render_tree.call_args.args[1]`) matches UUID v4 format — render_tree signature is `render_tree(entities, root_type_id, max_depth=50)`, so root identifier is args[1], not args[0]. This discriminates the fix — before the change, render_tree receives type_id at args[1] (fails UUID format check); after, it receives uuid (passes). Run: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py -k "process_get_lineage" -v --tb=short` — expect test to fail (render_tree receives type_id, not uuid).
  Then update `_process_get_lineage`: pass `entities[0]["uuid"]` to `render_tree` as root identifier (was `entities[0]["type_id"]`). Error message unchanged (echoes caller's identifier verbatim).
  **Done:** Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py -k "process_get_lineage" -v --tb=short`, test passes.

## Phase 4: MCP Server

**File:** `plugins/iflow/mcp/entity_server.py`
**Test file:** `plugins/iflow/hooks/lib/entity_registry/test_entity_server.py` (new file)

### 4.1 Tool Handler Message Updates

- [ ] **T4.1.1: Verify pytest-asyncio and write MCP handler tests**
  Verify pytest-asyncio: `plugins/iflow/.venv/bin/python -c "import pytest_asyncio; print(pytest_asyncio.__version__)"`. If import fails, install: `cd plugins/iflow && uv add pytest-asyncio`.
  `_db` is a module-level `None` initialized via lifespan (`_db: EntityDatabase | None = None`). Each handler has a `if _db is None` guard. Use `monkeypatch.setattr(entity_server, "_db", EntityDatabase(":memory:"))` in test setup — the guard is bypassed because `_db` is no longer `None`.
  Create new test file `plugins/iflow/hooks/lib/entity_registry/test_entity_server.py`. Write two tests using `@pytest.mark.asyncio`:
  - `test_set_parent_handler_dual_identity_message`: Set up `_db` via monkeypatch as above, register parent + child via `entity_server._db.register_entity(...)`, call `set_parent` handler, assert response text contains both UUID and type_id.
  - `test_update_entity_handler_dual_identity_message`: Same setup, register entity, call `update_entity` handler, assert response contains both UUID and type_id.
  **Done:** Tests exist, run red. pytest-asyncio installed.

- [ ] **T4.1.2: Update set_parent handler message**
  In `entity_server.py`, find the set_parent handler (`grep -n 'set_parent' plugins/iflow/mcp/entity_server.py`). Replace the try-block body (keep existing try/except wrapper intact):
  ```python
  try:
      child_uuid = _db.set_parent(type_id, parent_type_id)
      child = _db.get_entity(child_uuid)
      parent = _db.get_entity(child["parent_uuid"])
      return f"Set parent of {child_uuid} ({child['type_id']}) to {child['parent_uuid']} ({parent['type_id']})"
  except Exception as exc:
      return f"Error setting parent: {exc}"
  ```
  **Done:** `test_set_parent_handler_dual_identity_message` passes.

- [ ] **T4.1.3: Update update_entity handler message**
  In `entity_server.py`, find the update_entity handler (`grep -n 'update_entity' plugins/iflow/mcp/entity_server.py`). Replace the try-block body (keep existing try/except wrapper intact). The existing `_db.update_entity(...)` call stays — add a get_entity call after it and replace the return:
  ```python
  try:
      _db.update_entity(
          type_id, name=name, status=status,
          artifact_path=artifact_path, metadata=parse_metadata(metadata),
      )
      entity = _db.get_entity(type_id)
      return f"Updated entity: {entity['uuid']} ({entity['type_id']})"
  except Exception as exc:
      return f"Error updating entity: {exc}"
  ```
  **Done:** `test_update_entity_handler_dual_identity_message` passes.

## Phase 5: Test Finalization & Verification

**Files:** `test_database.py`, `test_server_helpers.py`

**Sequential:** T5.1.x must complete before T5.2.x.

### 5.1 Existing Test Assertion Updates

- [ ] **T5.1.1: Update schema assertion tests**
  Update and rename these tests in `test_database.py` (search from project root to confirm no other references: `grep -n "def test_entities_has_10\|def test_has_five_triggers\|def test_has_three_indexes\|def test_schema_version_is_1\|def test_type_id_is_primary" plugins/iflow/hooks/lib/entity_registry/test_database.py`):
  - `test_entities_has_10_columns` → rename to `test_entities_has_12_columns`, assert 12 columns
  - `test_entities_column_names` → add `uuid`, `parent_uuid` to expected list
  - `test_type_id_is_primary_key` → assert `uuid` is PK, `type_id` is NOT PK (rename to `test_uuid_is_primary_key`)
  - `test_schema_version_is_1` → rename to `test_schema_version_is_2`, assert `schema_version == "2"`
  - `test_has_five_triggers` → rename to `test_has_eight_triggers`, assert 8 triggers, sorted list: `enforce_immutable_created_at`, `enforce_immutable_entity_type`, `enforce_immutable_type_id`, `enforce_immutable_uuid`, `enforce_no_self_parent`, `enforce_no_self_parent_update`, `enforce_no_self_parent_uuid_insert`, `enforce_no_self_parent_uuid_update`
  - `test_has_three_indexes` → rename to `test_has_four_indexes`, assert 4 indexes, sorted list: `idx_entity_type`, `idx_parent_type_id`, `idx_parent_uuid`, `idx_status`
  **Done:** All schema assertion tests renamed and pass with new values.

- [ ] **T5.1.2: Update set_parent return value assertion tests**
  Update `TestSetParent.test_happy_path` to assert UUID v4 format return (match `_UUID_V4_RE`). Note: `register_entity` return value tests (`test_insert_or_ignore_idempotency`, `TestRegisterEntity.test_happy_path`, `TestRegisterEntity.test_type_id_auto_constructed`, `TestRegisterEntity.test_all_valid_types`) were already updated in T2.2.2 to keep the suite green.
  **Done:** Return value tests pass.

- [ ] **T5.1.3: Update raw SQL INSERT tests**
  Update `test_entity_type_check_constraint`, `test_valid_entity_types_accepted`, `test_self_parent_on_insert` to include `uuid` column via `str(uuid.uuid4())` in INSERT. Add second test case in `test_self_parent_on_insert` for the `parent_uuid` self-parent trigger (R12): INSERT with `parent_uuid = uuid` (same value), assert raises `"entity cannot be its own parent"`.
  **Done:** All raw SQL tests pass.

- [ ] **T5.1.4: Update server helper message assertions**
  Update test assertions in `test_server_helpers.py` for dual-identity message format: `"Registered entity: {uuid} ({type_id})"` in register handler tests.
  **Done:** Server helper tests pass.

### 5.2 Full Suite Verification

- [ ] **T5.2.1: Run full entity registry test suite**
  Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`. Verify 0 failures.
  **Done:** 0 failures.

- [ ] **T5.2.2: Verify test count and backfill compatibility**
  Verify 24 new test functions added by this feature. Breakdown: Phase 1 = 8 (test_migration_fresh_db, test_migration_populated_db_preserves_data, test_migration_populates_parent_uuid, test_uuid_immutability_trigger, test_self_parent_uuid_insert_trigger, test_self_parent_uuid_update_trigger, test_migration_rollback_on_failure, test_init_already_migrated_db), Phase 2 = 13 (test_resolve_identifier_with_uuid, test_resolve_identifier_with_type_id, test_resolve_identifier_not_found, test_register_returns_uuid_v4_format, test_register_duplicate_returns_existing_uuid, test_set_parent_mixed_identifiers, test_set_parent_updates_both_parent_columns, test_get_entity_by_uuid, test_get_entity_by_type_id, test_get_entity_not_found_returns_none, test_get_lineage_with_uuid, test_update_entity_with_uuid, test_export_uses_uuid_internally), Phase 3 = 1 (test_process_get_lineage_passes_uuid), Phase 4 = 2 (test_set_parent_handler_dual_identity_message, test_update_entity_handler_dual_identity_message). Hard minimum remains 10 per AC-27. First, verify the new test_entity_server.py is collected: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/test_entity_server.py --collect-only -q` — expect at least 2 tests listed (the two MCP handler tests). If collection fails, fix imports before proceeding. Then count new tests by matching new function names specifically (run from repo root for PYTHONPATH): `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ --collect-only -q | grep -cE 'test_migration_fresh|test_migration_populated|test_migration_populates|test_migration_rollback|test_uuid_immutability|test_self_parent_uuid|test_resolve_identifier|test_register_returns_uuid|test_register_duplicate|test_set_parent_mixed|test_set_parent_updates|test_get_entity_by_uuid|test_get_entity_by_type|test_get_entity_not_found|test_get_lineage_with_uuid|test_export_uses_uuid|test_init_already_migrated|test_update_entity_with_uuid|test_process_get_lineage_passes_uuid|test_set_parent_handler_dual|test_update_entity_handler_dual'` — expect at least 24 (tests span test_database.py, test_server_helpers.py, and test_entity_server.py). Verify backfill imports succeed (run from repo root so PYTHONPATH resolves):
  ```bash
  PYTHONPATH=plugins/iflow/hooks/lib plugins/iflow/.venv/bin/python -c "from entity_registry.backfill import scan_and_register; print(scan_and_register)"
  ```
  **Done:** Test count meets AC-27 minimum (10+). Backfill imports clean.

- [ ] **T5.2.3: Run entity server bootstrap test**
  Run `bash plugins/iflow/mcp/test_entity_server.sh`. Verify passes.
  **Done:** Bootstrap test passes.

## Dependency Summary

```
T1.1.1 → T1.1.2 → T1.1.3 → T1.1.4
T1.1.4 → T1.2.1 → T1.2.3 → T1.2.4 → T1.2.5
         T1.2.2 ──────────→ T1.2.4
T1.2.5 → T1.3.1 → T1.3.3 → T1.3.4
         T1.3.2 → T1.3.3
T1.3.4 → T1.4.1 → T1.4.2 → T1.4.3 → T1.4.4

T1.4.4 → T2.1.1 → T2.1.2 ──┐
         T2.2.1 → T2.2.2 ──┤ (parallel group A)
                            ├→ T2.3.1 → T2.3.2
                            │          ↓
                            ├→ T2.4.1 → T2.4.2 ──┐ (parallel group B)
                            │  T2.5.1 → T2.5.2 ──┤ (get_lineage — independent of T2.5.3)
                            │          T2.4.2 ──→ T2.5.3  (update_entity — needs get_entity from T2.4.2)
                            │                      ↓
                            └→ T2.6.1 → T2.6.2

T2.6.2 → T3.1.1 → T3.1.2 → T3.2.1
                             T3.2.2

T3.2.2 → T4.1.1 → T4.1.2 → T4.1.3

T4.1.3 → T5.1.1 → T5.1.2 → T5.1.3 → T5.1.4
T5.1.4 → T5.2.1 → T5.2.2 → T5.2.3
```

## Task Summary

- **Total tasks:** 40
- **Phases:** 5
- **Parallel groups:** 2 (Phase 2: group A = 2.1/2.2; group B = 2.4/2.5)
