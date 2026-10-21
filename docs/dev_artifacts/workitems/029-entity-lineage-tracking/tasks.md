# Tasks: Entity Lineage Tracking

## Phase 1: Database Foundation (Step 1)

### Task 1.1: Create entity_registry package scaffold
- **Files:** `plugins/iflow/hooks/lib/entity_registry/__init__.py`
- **Action:** Create empty `__init__.py` for the `entity_registry` package
- **Done when:** `__init__.py` exists and is importable (`python -c "import entity_registry"` from `hooks/lib/`)
- **Depends on:** Nothing
- **Parallel group:** P1

### Task 1.2: Write tests for EntityDatabase.__init__ — schema and pragmas
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_database.py` (new)
- **Action:** Write tests verifying: schema creation (entities table with 10 columns: `type_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL CHECK(entity_type IN ('backlog','brainstorm','project','feature')), entity_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT, parent_type_id TEXT REFERENCES entities(type_id), artifact_path TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, metadata TEXT`; _metadata table with `key TEXT PRIMARY KEY, value TEXT NOT NULL`; 3 immutable triggers; 2 self-parent triggers; 3 indexes: `idx_parent`, `idx_entity_type`, `idx_status`), pragma verification (WAL mode, foreign_keys ON, busy_timeout=5000), migration versioning in _metadata table. Assert all 5 trigger names exist in sqlite_master: `enforce_immutable_type_id`, `enforce_immutable_entity_type`, `enforce_immutable_created_at`, `enforce_no_self_parent`, `enforce_no_self_parent_update`. Test entity_type CHECK constraint rejects invalid types (e.g., "invalid_type").
- **Done when:** Tests exist and FAIL (RED phase — no implementation yet)
- **Depends on:** Task 1.1
- **Parallel group:** P1

### Task 1.3: Implement EntityDatabase.__init__ — schema and pragmas
- **Files:** `plugins/iflow/hooks/lib/entity_registry/database.py` (new)
- **Action:** Implement `EntityDatabase.__init__` with full schema DDL. Entities table: `CREATE TABLE entities (type_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL CHECK(entity_type IN ('backlog','brainstorm','project','feature')), entity_id TEXT NOT NULL, name TEXT NOT NULL, status TEXT, parent_type_id TEXT REFERENCES entities(type_id), artifact_path TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, metadata TEXT)`. Metadata table: `CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)`. 3 immutable triggers (`BEFORE UPDATE OF type_id/entity_type/created_at → RAISE(ABORT)`), 2 self-parent triggers (`BEFORE INSERT/UPDATE WHEN NEW.parent_type_id = NEW.type_id → RAISE(ABORT)`), 3 indexes (`idx_parent`, `idx_entity_type`, `idx_status`). Pragma settings: WAL, foreign_keys=ON, busy_timeout=5000, cache_size=-8000. Migration versioning via _metadata key `schema_version`. Follow `MemoryDatabase` pattern. Also implement `get_metadata(self, key: str) -> str | None` (SELECT value FROM _metadata WHERE key = :key) and `set_metadata(self, key: str, value: str) -> None` (INSERT OR REPLACE INTO _metadata) as part of the initial implementation, matching the MemoryDatabase pattern.
- **Done when:** Task 1.2 tests pass (GREEN phase)
- **Depends on:** Task 1.2
- **Parallel group:** P1

### Task 1.4: Write tests for register_entity — happy path, idempotency, validation
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_database.py` (append)
- **Action:** Write tests for: happy path registration, INSERT OR IGNORE idempotency, entity_type CHECK constraint validation (only backlog/brainstorm/project/feature), type_id auto-construction as `f"{entity_type}:{entity_id}"` (type_id is NOT a caller parameter — it is derived internally from entity_type + entity_id). Example: `register_entity(entity_type="feature", entity_id="029-entity-lineage-tracking", name="Entity Lineage")` → stored type_id = `"feature:029-entity-lineage-tracking"`. Test parent_type_id validation (FK must exist). Method signature: `register_entity(self, entity_type: str, entity_id: str, name: str, artifact_path: str | None = None, status: str | None = None, parent_type_id: str | None = None, metadata: dict | None = None) -> str` — returns the constructed type_id string. Use pytest `@pytest.fixture` with `tmp_path` for DB isolation (pattern: `plugins/iflow/hooks/lib/semantic_memory/test_database.py`).
- **Done when:** New tests exist and FAIL (RED)
- **Depends on:** Task 1.3
- **Parallel group:** P1

### Task 1.5: Implement register_entity
- **Files:** `plugins/iflow/hooks/lib/entity_registry/database.py` (append)
- **Action:** Implement `register_entity(self, entity_type, entity_id, name, artifact_path=None, status=None, parent_type_id=None, metadata=None) -> str`. Construct type_id as `f"{entity_type}:{entity_id}"` internally. INSERT OR IGNORE semantics, entity_type validation via _validate_entity_type, parent existence validation if parent_type_id provided, metadata stored as JSON TEXT. Returns constructed type_id string.
- **Done when:** Task 1.4 tests pass (GREEN)
- **Depends on:** Task 1.4
- **Parallel group:** P1

### Task 1.6: Write tests for immutable field triggers
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_database.py` (append)
- **Action:** Write tests verifying RAISE(ABORT) on attempted mutation of type_id, entity_type, created_at columns
- **Done when:** New tests exist and PASS (GREEN — triggers already created in Task 1.3 schema DDL)
- **Depends on:** Task 1.5
- **Parallel group:** P1

### Task 1.7: Verify immutable triggers pass and fix if needed
- **Files:** `plugins/iflow/hooks/lib/entity_registry/database.py`, `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- **Action:** Run Task 1.6 tests. If any fail, fix the trigger definitions in database.py. Note: triggers are created in Task 1.3 schema (monolithic DDL), so this task verifies correctness rather than implementing new code. This intentionally breaks the strict RED-GREEN TDD pattern because triggers are part of the schema, not a separate method.
- **Done when:** `python -m pytest plugins/iflow/hooks/lib/entity_registry/test_database.py -k "immutable" -v` — all pass
- **Depends on:** Task 1.6
- **Parallel group:** P1

### Task 1.8: Write tests for set_parent — happy path, circular rejection, self-parent, non-existent
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_database.py` (append)
- **Action:** Write tests for: happy path set_parent, circular reference rejection (CTE walk-up check), self-parent rejection, non-existent entity rejection (both child and parent)
- **Done when:** New tests exist and FAIL (RED)
- **Depends on:** Task 1.7
- **Parallel group:** P1

### Task 1.9: Implement set_parent
- **Files:** `plugins/iflow/hooks/lib/entity_registry/database.py` (append)
- **Action:** Implement `set_parent(self, type_id: str, parent_type_id: str) -> str` with: (1) both-entity-exist validation, (2) circular reference detection via recursive CTE: `WITH RECURSIVE ancestors(type_id, depth) AS (SELECT parent_type_id, 1 FROM entities WHERE type_id = :proposed_parent AND parent_type_id IS NOT NULL UNION ALL SELECT e.parent_type_id, a.depth + 1 FROM entities e JOIN ancestors a ON e.type_id = a.type_id WHERE a.depth < 10 AND e.parent_type_id IS NOT NULL) SELECT 1 FROM ancestors WHERE type_id = :child`. Binds: `:proposed_parent` = parent_type_id arg, `:child` = type_id arg (the entity being reparented). If query returns a row → raise ValueError("circular reference"). If query returns no rows (walk reached root or depth 10 without finding child) → allow the assignment.
- **Done when:** Task 1.8 tests pass (GREEN)
- **Depends on:** Task 1.8
- **Parallel group:** P1

### Task 1.10: Write tests for get_entity — existing and non-existent
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_database.py` (append)
- **Action:** Write tests for: get_entity returns dict for existing entity, returns None for non-existent
- **Done when:** New tests exist and FAIL (RED)
- **Depends on:** Task 1.9
- **Parallel group:** P1

### Task 1.11: Implement get_entity
- **Files:** `plugins/iflow/hooks/lib/entity_registry/database.py` (append)
- **Action:** Implement `get_entity` — simple SELECT by type_id primary key, return dict or None
- **Done when:** Task 1.10 tests pass (GREEN)
- **Depends on:** Task 1.10
- **Parallel group:** P1

### Task 1.12: Write tests for get_lineage — upward, downward, depth limit, single entity
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_database.py` (append)
- **Action:** Write tests for: upward traversal (root first ordering), downward traversal (BFS order), depth limit enforcement (max 10), single entity with no parent
- **Done when:** New tests exist and FAIL (RED)
- **Depends on:** Task 1.11
- **Parallel group:** P1

### Task 1.13: Implement get_lineage with recursive CTEs
- **Files:** `plugins/iflow/hooks/lib/entity_registry/database.py` (append)
- **Action:** Implement `get_lineage(self, type_id: str, direction: str = "up", max_depth: int = 10) -> list[dict]`. Returns list of entity dicts (all columns as dict keys). Upward CTE (direction="up"): `WITH RECURSIVE ancestors(type_id, depth) AS (SELECT :start, 0 UNION ALL SELECT e.parent_type_id, a.depth + 1 FROM entities e JOIN ancestors a ON e.type_id = a.type_id WHERE a.depth < :max_depth AND e.parent_type_id IS NOT NULL) SELECT e.* FROM ancestors a JOIN entities e ON a.type_id = e.type_id ORDER BY a.depth DESC` — returns root-first ordering. Downward CTE (direction="down"): `WITH RECURSIVE descendants(type_id, depth) AS (SELECT :start, 0 UNION ALL SELECT e.type_id, d.depth + 1 FROM entities e JOIN descendants d ON e.parent_type_id = d.type_id WHERE d.depth < :max_depth) SELECT e.* FROM descendants d JOIN entities e ON d.type_id = e.type_id ORDER BY d.depth ASC` — returns BFS order from root.
- **Done when:** Task 1.12 tests pass (GREEN)
- **Depends on:** Task 1.12
- **Parallel group:** P1

### Task 1.14: Write tests for update_entity — name, status, metadata updates
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_database.py` (append)
- **Action:** Write tests for: name/status updates, shallow metadata merge, empty dict clears metadata, updated_at timestamp changes
- **Done when:** New tests exist and FAIL (RED)
- **Depends on:** Task 1.13
- **Parallel group:** P1

### Task 1.15: Implement update_entity
- **Files:** `plugins/iflow/hooks/lib/entity_registry/database.py` (append)
- **Action:** Implement `update_entity` with selective field updates, shallow metadata merge, updated_at auto-set
- **Done when:** Task 1.14 tests pass (GREEN)
- **Depends on:** Task 1.14
- **Parallel group:** P1

### Task 1.16: Write tests for export_lineage_markdown — single tree, all trees
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_database.py` (append)
- **Action:** Write tests for: single tree markdown export, all trees export, correct markdown format with entity details
- **Done when:** New tests exist and FAIL (RED)
- **Depends on:** Task 1.15
- **Parallel group:** P1

### Task 1.17: Implement export_lineage_markdown
- **Files:** `plugins/iflow/hooks/lib/entity_registry/database.py` (append)
- **Action:** Implement `export_lineage_markdown` — query all root entities, build trees, format as markdown
- **Done when:** Task 1.16 tests pass (GREEN)
- **Depends on:** Task 1.16
- **Parallel group:** P1

### Task 1.18: Refactor pass on EntityDatabase
- **Files:** `plugins/iflow/hooks/lib/entity_registry/database.py`
- **Action:** Extract shared helpers: (1) `_now_iso()` returning UTC ISO-8601 timestamp string (used by register_entity, update_entity), (2) `_validate_entity_type(entity_type)` raising ValueError for invalid types (used by register_entity). Remove duplication. Verify naming consistency: run `grep -n 'def ' database.py` and confirm all public methods match design C1 names exactly (`register_entity`, `set_parent`, `get_entity`, `get_lineage`, `update_entity`, `export_lineage_markdown`) and all private helpers start with `_`.
- **Done when:** `python -m pytest plugins/iflow/hooks/lib/entity_registry/test_database.py -v` — all pass AND `grep -q 'def _now_iso' plugins/iflow/hooks/lib/entity_registry/database.py` succeeds AND `grep -q 'def _validate_entity_type' plugins/iflow/hooks/lib/entity_registry/database.py` succeeds
- **Depends on:** Task 1.17
- **Parallel group:** P1

## Phase 2A: MCP Server Helpers (Step 2, sub-steps 1-5) — parallel with Phase 2B

### Task 2.1: Write tests for tree rendering helper
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py` (new)
- **Action:** Write tests for `render_tree(entities: list[dict], root_type_id: str) -> str`. Each entity dict has keys: `{'type_id': str, 'name': str, 'entity_type': str, 'status': str|None, 'parent_type_id': str|None, 'created_at': str}`. Expected output format for a 3-node linear chain (backlog→brainstorm→feature):
  ```
  backlog:00019 — "Item" (promoted, 2026-02-27)
    └─ brainstorm:20260227-lineage — "Entity Lineage" (2026-02-27)
         └─ feature:029-entity-lineage-tracking — "Entity Lineage" (active, 2026-02-27)
  ```
  Root line: `{type_id} — "{name}" ({status}, {created_at})` (status omitted if None). Children: `└─` for last child, `├─` for non-last child. Continuation indent: `│  ` (pipe + 2 spaces) for each depth level. Test fixtures: single node; linear chain (3 deep); branching tree (2 children, first uses `├─`, second uses `└─`).
- **Done when:** Tests exist and FAIL (RED)
- **Depends on:** Task 1.18
- **Parallel group:** P2A

### Task 2.2: Implement render_tree helper
- **Files:** `plugins/iflow/hooks/lib/entity_registry/server_helpers.py` (new)
- **Action:** Implement `render_tree(entities: list[dict], root_type_id: str) -> str` with Unicode box-drawing characters
- **Done when:** Task 2.1 tests pass (GREEN)
- **Depends on:** Task 2.1
- **Parallel group:** P2A

### Task 2.3: Write tests for metadata JSON parsing helper
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py` (append)
- **Action:** Write tests for `parse_metadata`: valid JSON returns dict, invalid JSON returns error dict, None passthrough returns None
- **Done when:** Tests exist and FAIL (RED)
- **Depends on:** Task 2.2
- **Parallel group:** P2A

### Task 2.4: Implement parse_metadata helper
- **Files:** `plugins/iflow/hooks/lib/entity_registry/server_helpers.py` (append)
- **Action:** Implement `parse_metadata(metadata_str: str | None) -> dict | None`
- **Done when:** Task 2.3 tests pass (GREEN)
- **Depends on:** Task 2.3
- **Parallel group:** P2A

### Task 2.5: Write tests for output_path resolution helper
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py` (append)
- **Action:** Write tests for `resolve_output_path`: relative resolved against artifacts_root, absolute used as-is, None returns None
- **Done when:** Tests exist and FAIL (RED)
- **Depends on:** Task 2.4
- **Parallel group:** P2A

### Task 2.6: Implement resolve_output_path helper
- **Files:** `plugins/iflow/hooks/lib/entity_registry/server_helpers.py` (append)
- **Action:** Implement `resolve_output_path(output_path: str | None, artifacts_root: str) -> str | None`
- **Done when:** Task 2.5 tests pass (GREEN)
- **Depends on:** Task 2.5
- **Parallel group:** P2A

### Task 2.7: Write tests for _process_register_entity and _process_get_lineage
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py` (append)
- **Action:** Write tests for: `_process_register_entity(db: EntityDatabase, entity_type: str, entity_id: str, name: str, artifact_path: str | None, status: str | None, parent_type_id: str | None, metadata: dict | None) -> str` — delegates to db.register_entity, formats success/error as string for MCP response. `_process_get_lineage(db: EntityDatabase, type_id: str, direction: str, max_depth: int) -> str` — delegates to db.get_lineage (returns `list[dict]`), passes result to render_tree, returns formatted string. Both take `db` as explicit parameter (not global) for testability. Test error paths: invalid entity_type returns formatted error string, non-existent type_id returns "not found" message.
- **Done when:** Tests exist and FAIL (RED)
- **Depends on:** Task 2.6
- **Parallel group:** P2A

### Task 2.8: Implement _process_register_entity and _process_get_lineage
- **Files:** `plugins/iflow/hooks/lib/entity_registry/server_helpers.py` (append)
- **Action:** Implement both extracted helper functions that wrap EntityDatabase calls with error handling
- **Done when:** Task 2.7 tests pass (GREEN)
- **Depends on:** Task 2.7
- **Parallel group:** P2A

## Phase 2B: Backfill Scanner (Step 3) — parallel with Phase 2A

### Task 3.1: Set up backfill test fixtures
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_backfill.py` (new)
- **Action:** Create pytest fixtures using `tmp_path` that build mock artifact directories: `features/029-entity-lineage-tracking/` with `.meta.json` containing `{"id": "029", "slug": "entity-lineage-tracking", "brainstorm_source": "docs/brainstorms/20260227-lineage.prd.md", "backlog_source": "00019"}`, `brainstorms/` with `20260227-lineage.prd.md` containing `*Source: Backlog #00019*`, `projects/` (empty dir), `backlog.md` with table header + row `| 00019 | 2026-02-27 | Entity lineage |`. Fixture returns `(tmp_path, db)` tuple where db is a fresh EntityDatabase at `tmp_path / "test.db"`. Include a smoke test `test_fixtures_smoke` asserting: `(tmp_path / "features/029-entity-lineage-tracking/.meta.json").exists()` is True, the JSON is parseable, and key `brainstorm_source` is present.
- **Done when:** `python -m pytest plugins/iflow/hooks/lib/entity_registry/test_backfill.py::test_fixtures_smoke -v` passes (1 test)
- **Depends on:** Task 1.18
- **Parallel group:** P2B

### Task 3.2: Write tests for topological ordering
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_backfill.py` (append)
- **Action:** Write tests verifying scan order: backlog → brainstorm → project → feature
- **Done when:** Tests exist and FAIL (RED)
- **Depends on:** Task 3.1
- **Parallel group:** P2B

### Task 3.3: Implement scan ordering logic
- **Files:** `plugins/iflow/hooks/lib/entity_registry/backfill.py` (new)
- **Action:** Implement `run_backfill(db: EntityDatabase, artifacts_root: str) -> None` with `ENTITY_SCAN_ORDER = ['backlog', 'brainstorm', 'project', 'feature']`. For each entity type, call the type-specific scanner: `_scan_backlog(db, artifacts_root)`, `_scan_brainstorms(db, artifacts_root)`, `_scan_projects(db, artifacts_root)`, `_scan_features(db, artifacts_root)`. Stub each scanner as `pass` — actual logic added in subsequent tasks. Import `EntityDatabase` from `entity_registry.database`.
- **Done when:** Task 3.2 tests pass (GREEN)
- **Depends on:** Task 3.2
- **Parallel group:** P2B

### Task 3.4: Write tests for parent derivation
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_backfill.py` (append)
- **Action:** Write tests for: feature→brainstorm (via `.meta.json` `brainstorm_source` field), feature→project (via `.meta.json` `project_id` field), brainstorm→backlog using both marker format regexes: (1) `r'\*Source:\s*Backlog\s*#(\d{5})\*'` matching `*Source: Backlog #00019*`, (2) `r'\*\*Backlog Item:\*\*\s*(\d{5})'` matching `**Backlog Item:** 00019`. Test that both formats produce parent_type_id = `backlog:{id}`.
- **Done when:** Tests exist and FAIL (RED)
- **Depends on:** Task 3.3
- **Parallel group:** P2B

### Task 3.5: Implement parent derivation
- **Files:** `plugins/iflow/hooks/lib/entity_registry/backfill.py` (append)
- **Action:** Implement `_derive_parent(entity_type: str, meta: dict, brainstorm_content: str | None) -> str | None`. Returns parent_type_id or None. Lookup priority by entity_type: for `feature` → check `meta.get("project_id")` first (returns `"project:{project_id}"`), then `meta.get("brainstorm_source")` (extract stem, returns `"brainstorm:{stem}"`); for `brainstorm` → scan `brainstorm_content` with regex patterns `BACKLOG_MARKER_PATTERN_1 = r'\*Source:\s*Backlog\s*#(\d{5})\*'` and `BACKLOG_MARKER_PATTERN_2 = r'\*\*Backlog Item:\*\*\s*(\d{5})'` (returns `"backlog:{id}"`); for `project` → check `meta.get("brainstorm_source")` (returns `"brainstorm:{stem}"`); for `backlog` → always returns None (root entities). Define regex patterns as module-level constants.
- **Done when:** Task 3.4 tests pass (GREEN)
- **Depends on:** Task 3.4
- **Parallel group:** P2B

### Task 3.6: Write tests for orphaned backlog and external brainstorm handling
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_backfill.py` (append)
- **Action:** Write tests for: orphaned backlog items get synthetic entity with status="orphaned", external brainstorm_source gets synthetic entity with status="external"
- **Done when:** Tests exist and FAIL (RED)
- **Depends on:** Task 3.5
- **Parallel group:** P2B

### Task 3.7: Implement orphaned and external entity handling
- **Files:** `plugins/iflow/hooks/lib/entity_registry/backfill.py` (append)
- **Action:** Implement `_register_synthetic(db: EntityDatabase, entity_type: str, entity_id: str, name: str, status: str) -> str`. Calls `db.register_entity(entity_type=entity_type, entity_id=entity_id, name=name, status=status)`. Used for two cases: (1) orphaned backlog — when a feature's `backlog_source` references a backlog ID not found in `backlog.md`, register with `status="orphaned"`, `name="Backlog #{id} (orphaned)"`; (2) external brainstorm — when `brainstorm_source` points outside `artifacts_root` (detected via `not os.path.isabs(path) or not path.startswith(artifacts_root)`), register with `status="external"`, `name="External: {path}"`.
- **Done when:** Task 3.6 tests pass (GREEN)
- **Depends on:** Task 3.6
- **Parallel group:** P2B

### Task 3.8: Write tests for idempotency and .prd.md/.md priority
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_backfill.py` (append)
- **Action:** Write tests for: running backfill twice produces same result (INSERT OR IGNORE), `.prd.md` files scanned first with `.md` only for unregistered stems
- **Done when:** Tests exist and FAIL (RED)
- **Depends on:** Task 3.7
- **Parallel group:** P2B

### Task 3.9: Implement idempotency and file priority
- **Files:** `plugins/iflow/hooks/lib/entity_registry/backfill.py` (append)
- **Action:** In `_scan_brainstorms`, glob `{artifacts_root}/brainstorms/*.prd.md` first, collect registered stems in a `set`. Then glob `{artifacts_root}/brainstorms/*.md`, filter to exclude stems already in the set. This ensures `.prd.md` files take priority over `.md` files for the same stem. Idempotency is guaranteed by EntityDatabase's INSERT OR IGNORE semantics (Task 1.5) — no additional logic needed in backfill.
- **Done when:** Task 3.8 tests pass (GREEN)
- **Depends on:** Task 3.8
- **Parallel group:** P2B

### Task 3.10: Write tests for backfill_complete marker and partial recovery
- **Files:** `plugins/iflow/hooks/lib/entity_registry/test_backfill.py` (append)
- **Action:** Write tests for: `backfill_complete` marker in `_metadata` table set after full run, not set → re-runs, set → skips, partial failure recovery (INSERT OR IGNORE on re-run)
- **Done when:** Tests exist and FAIL (RED)
- **Depends on:** Task 3.9
- **Parallel group:** P2B

### Task 3.11: Implement backfill_complete marker
- **Files:** `plugins/iflow/hooks/lib/entity_registry/backfill.py` (append)
- **Action:** At the top of `run_backfill`, add guard: `if db.get_metadata("backfill_complete") == "1": return` (skip if already done). At the bottom of `run_backfill` (after all scanners complete), add: `db.set_metadata("backfill_complete", "1")`. The `get_metadata`/`set_metadata` methods are implemented as part of EntityDatabase in Task 1.3 (matching MemoryDatabase pattern).
- **Done when:** Task 3.10 tests pass (GREEN)
- **Depends on:** Task 3.10
- **Parallel group:** P2B

### Task 3.12: Refactor pass on backfill module
- **Files:** `plugins/iflow/hooks/lib/entity_registry/backfill.py`
- **Action:** Consolidate regex patterns, review scan functions, verify topological ordering correctness, ensure all tests pass. Note: `_scan_features`, `_scan_projects`, `_scan_backlog`, and `_scan_brainstorms` full implementations (glob directory, read metadata, call `db.register_entity` for each entity, call `_derive_parent` for parent linkage) are built incrementally across Tasks 3.3–3.11 as each helper is implemented. This refactor pass ensures all four scanner functions have non-stub bodies and work end-to-end.
- **Done when:** `python -m pytest plugins/iflow/hooks/lib/entity_registry/test_backfill.py -v` — all pass AND `grep -cE '^[A-Z_]+PATTERN\s*=' plugins/iflow/hooks/lib/entity_registry/backfill.py` returns 2 or more (regex patterns defined as module-level constants) AND `grep -c 'register_entity' plugins/iflow/hooks/lib/entity_registry/backfill.py` returns 4 or more (each scanner calls register_entity)
- **Depends on:** Task 3.11
- **Parallel group:** P2B

## Phase 3: MCP Server Assembly (Step 2, sub-step 6 + Step 4)

### Task 4.1: Create entity_server.py with FastMCP server
- **Files:** `plugins/iflow/mcp/entity_server.py` (new)
- **Action:** Create FastMCP server following `memory_server.py` pattern. Directory setup: `os.makedirs(os.path.dirname(db_path), exist_ok=True)` where `db_path = os.path.expanduser("~/.claude/iflow/entities/entities.db")`. Implement lifespan: read project root from env (`PROJECT_ROOT = os.environ.get("PROJECT_ROOT", os.getcwd())`), read artifacts_root from config (via `from semantic_memory.config import read_config`), open EntityDatabase at `db_path`, import backfill (`from entity_registry.backfill import run_backfill`) and call `run_backfill(db, artifacts_root)` unconditionally — the idempotency guard inside `run_backfill` (Task 3.11) handles skip-if-complete logic. Define 6 MCP tools: `register_entity`, `set_parent`, `get_entity`, `get_lineage`, `update_entity`, `export_lineage_markdown`. Tools with complex logic (`register_entity`, `get_lineage`) wrap extracted helper functions from `server_helpers.py` (`from entity_registry.server_helpers import _process_register_entity, _process_get_lineage`). Remaining tools (`set_parent`, `get_entity`, `update_entity`, `export_lineage_markdown`) delegate directly to `db.*` methods — their logic is simple enough that a dedicated helper adds no value (≤5 lines each, per Task 4.2 verification).
- **Done when:** Server file exists at `plugins/iflow/mcp/entity_server.py`, all 6 tools are decorated with `@mcp.tool()` with correct signatures matching design I2/I3/I4, and `python -c "import entity_server"` succeeds from `mcp/` directory with PYTHONPATH=../hooks/lib
- **Depends on:** Task 2.8, Task 3.12
- **Parallel group:** P3

### Task 4.2: Refactor pass on MCP server
- **Files:** `plugins/iflow/mcp/entity_server.py`
- **Action:** Review helper function interfaces, remove duplication between process helpers, verify error message consistency, ensure tool docstrings match design interface specs (I2, I3, I4). Verification: confirm each `@mcp.tool()` function body is ≤5 lines (delegation only, no inline DB logic). Cross-check tool parameter names against design I2/I3/I4 interface definitions.
- **Done when:** `python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v` passes (all previously green tests still pass) AND each of the 6 MCP tool implementations delegates to a `_process_*` helper or direct DB call (no inline DB logic — verify with `grep -A 5 '@mcp.tool' plugins/iflow/mcp/entity_server.py` showing ≤5 lines per tool body) AND `register_entity` tool accepts parameters: entity_type, entity_id, name, artifact_path, status, parent_type_id, metadata (I2) AND `get_lineage` accepts: type_id, direction, max_depth (I3)
- **Depends on:** Task 4.1
- **Parallel group:** P3

### Task 4.3: Create run-entity-server.sh bootstrap wrapper
- **Files:** `plugins/iflow/mcp/run-entity-server.sh` (new)
- **Action:** Create shell wrapper that extends `run-memory-server.sh`'s 3-path pattern with a uv bootstrap step inserted as step 3; the existing wrapper's pip-only bootstrap becomes step 4 (fallback). Use `set -euo pipefail`. Resolution flow:
  1. **Existing venv:** If `[[ -x "$VENV_DIR/bin/python" ]]` → `exec "$VENV_DIR/bin/python" "$SERVER_SCRIPT"`
  2. **System python3 fast path:** If `python3 -c "import mcp.server.fastmcp" 2>/dev/null` succeeds → `exec python3 "$SERVER_SCRIPT"` (deps already available, skip bootstrap)
  3. **Bootstrap with uv (preferred):** If `command -v uv >/dev/null 2>&1` succeeds → `uv venv "$VENV_DIR"` + `uv pip install --python "$VENV_DIR/bin/python" "mcp>=1.0,<2"` (all output to stderr via `>&2`)
  4. **Bootstrap with pip (fallback):** If `uv` unavailable → `python3 -m venv "$VENV_DIR"` + `"$VENV_DIR/bin/pip" install -q "mcp>=1.0,<2"` (output to stderr via `>&2`)
  After bootstrap: `exec "$VENV_DIR/bin/python" "$SERVER_SCRIPT"`. Set `export PYTHONUNBUFFERED=1` (required for MCP stdio protocol), `PYTHONPATH="$PLUGIN_DIR/hooks/lib${PYTHONPATH:+:$PYTHONPATH}"`, `VENV_DIR="$PLUGIN_DIR/.venv"`. Add header comment: `# Shared venv with memory server — each server's bootstrap handles its own deps`. Deps: `mcp>=1.0,<2` only. All diagnostics to stderr (stdout is MCP stdio protocol).
- **Done when:** Script is executable (`chmod +x` verified), `bash -n plugins/iflow/mcp/run-entity-server.sh` passes (syntax check), `grep -q 'PYTHONUNBUFFERED' plugins/iflow/mcp/run-entity-server.sh` passes, script handles all 4 paths in the resolution flow above
- **Depends on:** Task 4.1
- **Parallel group:** P3

### Task 4.4: Register entity-registry MCP server in plugin.json
- **Files:** `plugins/iflow/.claude-plugin/plugin.json` (modified)
- **Action:** Add `entity-registry` entry to `mcpServers` object. Exact JSON to add after the `memory-server` entry:
  ```json
  "entity-registry": {
    "command": "${CLAUDE_PLUGIN_ROOT}/mcp/run-entity-server.sh",
    "args": []
  }
  ```
- **Done when:** `plugin.json` contains valid `entity-registry` MCP server entry and `python -m json.tool plugins/iflow/.claude-plugin/plugin.json` succeeds (valid JSON)
- **Depends on:** Task 4.3
- **Parallel group:** P3

### Task 4.5: Write integration test script
- **Files:** `plugins/iflow/mcp/test_entity_server.sh` (new)
- **Action:** Write bash integration test following `test_run_memory_server.sh` pattern. Scope is limited to wrapper bootstrap mechanics (NOT full JSON-RPC protocol testing — that's covered by Python unit tests in Tasks 2.x). DB isolation: set `ENTITY_DB_PATH=$(mktemp /tmp/test-entity-XXXXXX.db)` and export as env var. Tests: (1) `bash -n run-entity-server.sh` passes (syntax check), (2) script file is executable (`[[ -x run-entity-server.sh ]]`), (3) PYTHONPATH is set correctly (source script vars section, verify `$PYTHONPATH` contains `hooks/lib`), (4) server process starts without immediate crash — use pattern: `timeout 5 bash run-entity-server.sh >/dev/null 2>&1 & PID=$!; sleep 2; if kill -0 $PID 2>/dev/null; then echo "PASS: server started"; kill $PID; else wait $PID; if [[ $? -eq 124 ]]; then echo "PASS: server ran until timeout"; else echo "FAIL: server crashed"; exit 1; fi; fi`. Script must `set -euo pipefail`, clean up on exit via `trap 'kill $PID 2>/dev/null; rm -f "$ENTITY_DB_PATH"' EXIT`. Note: if entity_server.py does not support `ENTITY_DB_PATH` env var override, add it to entity_server.py as `db_path = os.environ.get("ENTITY_DB_PATH", os.path.expanduser("~/.claude/iflow/entities/entities.db"))`.
- **Done when:** Test script exists, is executable (`chmod +x`), `bash -n` syntax check passes, tests pass when run
- **Depends on:** Task 4.4
- **Parallel group:** P3

## Phase 4: Command and Skill Integrations (Steps 5-8) — all parallel after Phase 3

### Task 5.1: Create /show-lineage command
- **Files:** `plugins/iflow/commands/show-lineage.md` (new)
- **Action:** Create command markdown with frontmatter. Must include all 7 sections: (1) frontmatter with description and argument-hint per design I5, (2) argument parsing for all 5 flags (`--feature`, `--project`, `--backlog`, `--brainstorm`, `--descendants`), (3) branch auto-detection regex `^feature/(.+)$`, (4) type_id construction table:
  | Flag | type_id format |
  |------|---------------|
  | `--feature={id}-{slug}` | `feature:{id}-{slug}` (direct) |
  | `--feature={id}` (bare 3-digit) | Call `get_entity` MCP tool with `type_id="feature:{id}"` — if not found, glob features dir for `{id}-*` pattern and use first match slug to construct `feature:{id}-{slug}` |
  | `--project={id}` | `project:{id}` |
  | `--backlog={5-digit-id}` | `backlog:{id}` |
  | `--brainstorm={filename-stem}` | `brainstorm:{stem}` |
  | (no flag, on feature branch) | `feature:{branch-suffix}` from regex |
  (5) `get_lineage` MCP tool call with direction parameter (`"up"` default, `"down"` if `--descendants`), (6) tree output display section, (7) 3 error cases: entity not found → `"Entity {type:id} not found in registry"`, no arg + no feature branch → `"No entity specified. Use --feature, --project, --backlog, or --brainstorm, or run from a feature branch."`, depth limit → `"Traversal depth limit reached (>10 hops)..."`
- **Done when:** `ls plugins/iflow/commands/show-lineage.md` succeeds AND `grep -c '##' plugins/iflow/commands/show-lineage.md` returns 7 or more AND `grep -q 'get_lineage' plugins/iflow/commands/show-lineage.md` passes AND `grep -q 'argument-hint' plugins/iflow/commands/show-lineage.md` passes (frontmatter present)
- **Depends on:** Task 4.5
- **Parallel group:** P4

### Task 6.1: Modify create-feature.md — entity registration
- **Files:** `plugins/iflow/commands/create-feature.md` (modified)
- **Action:** Insert entity registration block after the "Create `.meta.json`" step (after the existing `Write to {iflow_artifacts_root}/features/{id}-{slug}/.meta.json:` section) and before "Handle PRD Source". Add MCP tool calls: register backlog entity (idempotent) if backlog_source, update backlog status to "promoted", register brainstorm entity (idempotent) if brainstorm_source, register feature entity with parent_type_id. MCP failure handling: wrap in `try/catch` style — `If MCP call fails: warn "Entity registration failed: {error}" but do NOT block feature creation`.
- **Done when:** create-feature.md contains `register_entity` MCP calls (for backlog, brainstorm, and feature entities) with `parent_type_id` parameter and error handling (`If MCP call fails: warn ... but do NOT block`)
- **Depends on:** Task 4.5
- **Parallel group:** P4

### Task 6.2: Modify create-feature.md — backlog mark-as-promoted
- **Files:** `plugins/iflow/commands/create-feature.md` (modified)
- **Action:** Change backlog handling from row deletion to appending promotion annotation to Description column. Exact transformation:
  - **Before:** `| 00019 | 2026-02-27T05:00:00Z | Entity lineage tracking |`
  - **After:** `| 00019 | 2026-02-27T05:00:00Z | Entity lineage tracking (promoted → feature:029-entity-lineage-tracking) |`
  - **Multi-promotion (if Description already contains `(promoted → ...)`):** Replace closing `)` with `, feature:{id}-{slug})`. E.g., `(promoted → project:P001)` becomes `(promoted → project:P001, feature:029-entity-lineage-tracking)`.
  Write ordering: DB registration/update first (`register_entity` + `update_entity` MCP calls), then backlog.md annotation. If annotation fails, warn but do not rollback DB — DB is source of truth. Replace display message from `"Linked from backlog item #{id} (removed from backlog)"` to `"Linked from backlog item #{id} (promoted)"`.
- **Done when:** create-feature.md uses mark-as-promoted instead of row deletion, handles multi-promotion format, preserves the row in backlog.md
- **Depends on:** Task 6.1
- **Parallel group:** P4

### Task 7.1: Modify create-project.md — entity registration
- **Files:** `plugins/iflow/commands/create-project.md` (modified)
- **Action:** After project directory + .meta.json creation, add MCP tool calls: register brainstorm entity (idempotent), parse brainstorm for backlog source marker, if found register backlog entity and call `set_parent` on the brainstorm to link it to the backlog (brainstorm→backlog), register project entity with `parent_type_id` parameter set to brainstorm type_id (project→brainstorm link via register_entity, NOT via set_parent). MCP failure: warn but don't block.
- **Done when:** create-project.md contains `register_entity` MCP calls (for brainstorm and project entities) with `parent_type_id` parameter for the project, AND contains `set_parent` call for the brainstorm→backlog link when backlog source is found
- **Depends on:** Task 4.5
- **Parallel group:** P4

### Task 7.2: Modify decomposing SKILL.md — entity registration with I7
- **Files:** `plugins/iflow/skills/decomposing/SKILL.md` (modified)
- **Action:** When creating planned features, add `register_entity` call with `parent_type_id="project:{project_id}"`. Store `depends_on_features` in entity metadata JSON as `{"depends_on_features": ["feature:{id}-{slug}", ...]}` where each element is a type_id string referencing sibling features (NOT as parent-child relationships). MCP failure: warn but don't block.
- **Done when:** decomposing SKILL.md contains register_entity calls with correct parent and metadata
- **Depends on:** Task 4.5
- **Parallel group:** P4

### Task 8.1: Modify brainstorming SKILL.md — entity registration
- **Files:** `plugins/iflow/skills/brainstorming/SKILL.md` (modified)
- **Action:** After creating brainstorm PRD file (end of Stage 3), call `register_entity` to register the brainstorm entity. If brainstorm originated from backlog (`*Source: Backlog #ID*`), set parent to `backlog:{id}`. MCP failure: warn but don't block.
- **Done when:** brainstorming SKILL.md contains register_entity call at end of Stage 3
- **Depends on:** Task 4.5
- **Parallel group:** P4

## Phase 5: Gap Log and Documentation (Steps 9-10)

### Task 9.1: Create gap-log.md template
- **Files:** `docs/dev_artifacts/workitems/029-entity-lineage-tracking/gap-log.md` (new)
- **Action:** Create gap-log.md with Summary table (invocation count, entity types queried, gaps observed) and Invocation Log table (date, entity, query type, result, gap noted) per design I8 template. Initial values: 0 invocations, no entity types, no gaps.
- **Done when:** `docs/dev_artifacts/workitems/029-entity-lineage-tracking/gap-log.md` exists with Summary table and Invocation Log table
- **Depends on:** Nothing
- **Parallel group:** P4 (can run anytime)

### Task 10.1: Update README.md
- **Files:** `README.md` (modified)
- **Action:** Add `/show-lineage` to command table, update component counts for new MCP server and command
- **Done when:** README.md lists show-lineage command and has correct component counts
- **Depends on:** Task 5.1, Task 6.2, Task 7.2, Task 8.1
- **Parallel group:** P5

### Task 10.2: Update README_FOR_DEV.md
- **Files:** `README_FOR_DEV.md` (modified)
- **Action:** Update component counts to reflect new MCP server, command, and modified files
- **Done when:** README_FOR_DEV.md has correct component counts
- **Depends on:** Tasks 5.1, 6.2, 7.2, 8.1
- **Parallel group:** P5

### Task 10.3: Update plugins/iflow/README.md
- **Files:** `plugins/iflow/README.md` (modified)
- **Action:** Add show-lineage command to command table, add entity-registry to MCP server listing, update component counts
- **Done when:** Plugin README lists both the new command and MCP server
- **Depends on:** Tasks 5.1, 6.2, 7.2, 8.1
- **Parallel group:** P5

## Summary

- **Total tasks:** 43
- **Phases:** 5 (P1: Database → P2A+P2B: Server Helpers + Backfill parallel → P3: Assembly → P4: Integrations parallel → P5: Docs)
- **Parallel groups:**
  - P1: Tasks 1.1–1.18 (sequential, TDD pairs)
  - P2A: Tasks 2.1–2.8 (sequential, TDD pairs) — parallel with P2B
  - P2B: Tasks 3.1–3.12 (sequential, TDD pairs) — parallel with P2A
  - P3: Tasks 4.1–4.5 (sequential, assembly)
  - P4: Tasks 5.1, 6.1–6.2, 7.1–7.2, 8.1, 9.1 (all parallel after P3)
  - P5: Tasks 10.1–10.3 (all parallel, after P4)
