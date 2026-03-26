# Spec: Cross-Project Entity Scoping

## Overview
Add project scoping to the global entity registry DB so that entities from different projects coexist without collisions and queries default to the current project.

**PRD:** `docs/features/065-cross-project-entity-scoping/prd.md`

## Scope

### In Scope
- Schema migration 8: `project_id` column, `projects` table, `sequences` table, composite UNIQUE
- `project_identity.py` module: `detect_project_id()`, `collect_git_info()`, `normalize_remote_url()`
- Project-scoped query filtering on all read methods
- Project-scoped sequential ID generation
- MCP tool parameter additions + new `list_projects` tool
- Startup auto-registration/upsert of project, artifact-path backfill
- Doctor check updates
- `add-to-backlog` migration to DB-based ID generation

### Out of Scope
- Per-project DB files
- Cross-project entity migration tool
- Project registry UI
- Namespace-prefixed human-readable IDs

## Functional Specifications

### FS-1: Project Identity Module

**Module:** `plugins/pd/hooks/lib/entity_registry/project_identity.py`

#### FS-1.1: `detect_project_id(working_dir: str | None = None) -> str`
- Returns 12-char hex string
- Fallback chain: (1) root commit SHA truncated, (2) HEAD SHA, (3) SHA-256 of absolute path
- Cached per-process via `lru_cache(maxsize=1)`
- `ENTITY_PROJECT_ID` env var override takes precedence over all fallbacks (for CI)
- Timeout: 5 seconds on all subprocess calls
- Must complete in <100ms under normal conditions

**Acceptance Criteria:**
- [ ] AC-1.1.1: Returns same value for same repo regardless of working directory depth within repo
- [ ] AC-1.1.2: Returns same value across clones of same repo (shared root commit)
- [ ] AC-1.1.3: Returns same value for SSH and HTTPS checkouts (root commit is protocol-agnostic)
- [ ] AC-1.1.4: Falls back to HEAD when root commit unavailable (shallow clone)
- [ ] AC-1.1.5: Falls back to path hash when no git at all
- [ ] AC-1.1.6: `ENTITY_PROJECT_ID` env var overrides all detection
- [ ] AC-1.1.7: Second call with same arguments does not spawn subprocess (cache hit). Note: `lru_cache(maxsize=1)` is intentional — MCP servers call once with the same project_root.

#### FS-1.2: `collect_git_info(working_dir: str | None = None) -> GitProjectInfo`

Returns frozen dataclass:
```python
@dataclasses.dataclass(frozen=True)
class GitProjectInfo:
    project_id: str          # from detect_project_id()
    root_commit_sha: str     # full 40-char or ""
    name: str                # from remote URL or dir basename
    remote_url: str          # raw origin URL or ""
    normalized_url: str      # canonical host/owner/repo or ""
    remote_host: str         # e.g. "github.com" or ""
    remote_owner: str        # e.g. "terry" or ""
    remote_repo: str         # e.g. "pedantic-drip" or ""
    default_branch: str      # e.g. "main" or ""
    project_root: str        # absolute path
    is_git_repo: bool
```

**Acceptance Criteria:**
- [ ] AC-1.2.1: Each field fails independently — partial git info does not block other fields
- [ ] AC-1.2.2: `name` derived from `remote_repo` when available, falls back to dir basename
- [ ] AC-1.2.3: Non-git directories produce `is_git_repo=False` with empty git fields

#### FS-1.3: `normalize_remote_url(raw_url: str) -> str`

Normalization rules (in order):
1. Strip scheme (`https://`, `ssh://`, `git://`)
2. Strip user@ prefix (`git@`, `ssh@`)
3. Replace `:` with `/` for SCP-style URLs (only the first `:` after host)
4. Strip trailing `.git`
5. Strip trailing `/`
6. Lowercase the host portion
7. Result: `host/owner/repo`

**Acceptance Criteria:**
- [ ] AC-1.3.1: `git@github.com:terry/pedantic-drip.git` → `github.com/terry/pedantic-drip`
- [ ] AC-1.3.2: `https://github.com/terry/pedantic-drip.git` → same
- [ ] AC-1.3.3: `ssh://git@github.com/terry/pedantic-drip` → same
- [ ] AC-1.3.4: Empty string input → empty string output
- [ ] AC-1.3.5: Local path URLs (e.g., `/path/to/repo.git`) handled gracefully

### FS-2: Schema Migration 8

**File:** `plugins/pd/hooks/lib/entity_registry/database.py`
**Function:** `_add_project_scoping(conn: sqlite3.Connection)`

Self-managed transaction following the established pattern in `_schema_expansion_v6`.

#### Migration Steps
1. `PRAGMA foreign_keys = OFF`
2. `BEGIN IMMEDIATE`
3. CREATE TABLE `projects` (FR-2 DDL from PRD)
4. CREATE TABLE `sequences` (FR-4 DDL from PRD)
5. CREATE TABLE `entities_new` (FR-3 target DDL from PRD — includes `project_id TEXT NOT NULL DEFAULT '__unknown__'`, `UNIQUE(project_id, type_id)`, `parent_type_id TEXT` without FK constraint)
6. INSERT INTO `entities_new` SELECT with `'__unknown__'` as project_id for ALL existing entities. **Deviation from PRD FR-1 (spec supersedes PRD migration row states table):** existing `metadata.project_id` values are project entity IDs (e.g., `"P001"`) — NOT the 12-char hex SHA format that `detect_project_id()` produces. Using `json_extract` would create format-mismatched project_ids that never match the detected ID. Instead, all existing entities start as `'__unknown__'` and the artifact-path backfill at MCP startup claims them with the correct 12-char SHA.
7. DROP TABLE `entities` / ALTER TABLE `entities_new` RENAME TO `entities`
8. Recreate 9 triggers (8 existing + `enforce_immutable_project_id`)
9. Recreate all indexes + `idx_project_id`, `idx_project_entity_type`
10. Migrate `_metadata` `next_seq_*` → `sequences` table with `project_id='__unknown__'`, DELETE old keys
11. DROP + CREATE `entities_fts`, backfill (migration 7 pattern)
12. Update schema_version to 8
13. COMMIT
14. `PRAGMA foreign_keys = ON`, post-commit FK check

**Acceptance Criteria:**
- [ ] AC-2.1: Fresh DB (no entities) creates all 3 new tables with correct schema
- [ ] AC-2.2: ALL existing entities get `project_id = '__unknown__'` regardless of metadata.project_id values (format mismatch: metadata stores project entity IDs like "P001", not 12-char SHA)
- [ ] AC-2.3: Artifact-path backfill at startup claims `__unknown__` entities with correct 12-char SHA project_id
- [ ] AC-2.4: Same type_id in different projects can coexist (composite UNIQUE)
- [ ] AC-2.5: Same type_id in same project is rejected (composite UNIQUE)
- [ ] AC-2.6: All 9 triggers exist and function post-migration
- [ ] AC-2.7: `project_id` column is immutable via trigger (UPDATE raises ABORT)
- [ ] AC-2.8: FTS search still works post-migration
- [ ] AC-2.9: `_metadata` `next_seq_*` keys are deleted, values migrated to `sequences`
- [ ] AC-2.10: Migration is idempotent (re-opening DB does not re-run)
- [ ] AC-2.11: Migration rolls back cleanly on failure (no partial state)
- [ ] AC-2.12: `parent_type_id` column retained as denormalized data (no FK constraint)
- [ ] AC-2.13: `parent_uuid REFERENCES entities(uuid)` FK is preserved and functional

### FS-3: Project-Scoped Queries

#### FS-3.1: `EntityDatabase` method changes

**Convention:** DB methods use `None` for all-projects queries. MCP tools use `"*"` string, converted to `None` at the MCP handler layer (see FS-4.2 sentinel mapping).

| Method | `project_id` param | Behavior |
|--------|-------------------|----------|
| `register_entity` | Required `str` | Stored in column; no default at DB layer. **Idempotency change:** `INSERT OR IGNORE` now deduplicates on `(project_id, type_id)` — same type_id in different project creates new entity. Post-insert UUID lookup: `WHERE type_id = ? AND project_id = ?`. **Parent resolution:** `parent_type_id` lookup at database.py:1388-1391 must add `AND project_id = ?` filter (parents assumed in same project). |
| `register_entities_batch` | Required `str` | Applied to all entities in batch. Same idempotency change as `register_entity`. |
| `list_entities` | Optional `str \| None` | `None` = all projects, string = filter |
| `search_entities` | Optional `str \| None` | `None` = all projects, string = filter; FTS query unchanged, project filter via WHERE on joined entities table |
| `export_entities_json` | Optional `str \| None` | `None` = all projects |
| `export_lineage_markdown` | Optional `str \| None` | `None` = all projects (filters root entities) |
| `scan_entity_ids` | Optional `str \| None` | `None` = all projects; used by sequence bootstrap |
| `_resolve_identifier` | Optional `str \| None` | See FS-3.2 |
| `next_sequence_value` | Required `str` | New method — always project-scoped |

| `resolve_ref` | Optional `str \| None` | Exact type_id lookup (database.py:1082-1086) and prefix search (`search_by_type_id_prefix`) both need project_id filtering. Pass through to `_resolve_identifier`. |
| `search_by_type_id_prefix` | Optional `str \| None` | Add `AND project_id = ?` to LIKE query; `None` = all projects |
| `set_parent` | Optional `str \| None` | Resolves both type_id args via `_resolve_identifier` with project context |
| `update_entity` | Optional `str \| None` | Resolves type_id via `_resolve_identifier`. See re-attribution note below. |
| `delete_entity` | Optional `str \| None` | Resolves type_id via `_resolve_identifier` to get UUID, then deletes by UUID. Internal queries at database.py:1743,1764,1769 must resolve to UUID first, not use raw `WHERE type_id = ?`. |

**Unchanged methods** (operate on UUID only, no type_id lookup): `get_entity_by_uuid`, `get_children_by_uuid`, tag methods (`add_tag`, `remove_tag`, `get_tags`, `query_by_tag`), dependency methods (`add_dependency`, `remove_dependency`, `query_dependencies`), OKR methods.

**Note on workflow phase methods:** `create_workflow_phase`, `get_workflow_phase`, `update_workflow_phase`, `upsert_workflow_phase`, `delete_workflow_phase`, `list_workflow_phases` all use `WHERE type_id = ?` on the `workflow_phases` table. Post-migration, type_id is no longer globally unique. **Design trade-off:** The `workflow_phases` table does not gain a `project_id` column. This is safe IF all callers resolve entities to a project-scoped type_id before calling workflow methods. **Critical safeguard:** Add `project_id` parameter to `upsert_workflow_phase` to scope the initial entity existence check — this is NOT optional, it is required to prevent cross-project type_id collisions in workflow_phases. **Known risk:** If any caller bypasses entity resolution and passes an ambiguous type_id, workflow phases could leak across projects. Mitigated by: all MCP tool handlers resolve via `_resolve_identifier(type_id, _project_id)` before calling workflow methods. **Method-by-method disposition:** `create_workflow_phase`, `get_workflow_phase`, `update_workflow_phase`, `delete_workflow_phase`, `list_workflow_phases` — no signature change needed. Callers must resolve type_id to a project-scoped value before calling. `upsert_workflow_phase` — add `project_id` parameter (required for entity existence check).

**Note on `update_entity` re-attribution:** For changing an entity's project_id, `update_entity` uses trigger-drop approach within `BEGIN IMMEDIATE`: (1) DROP TRIGGER enforce_immutable_project_id, (2) UPDATE entities SET project_id = ? WHERE uuid = ?, (3) FTS sync (DELETE + INSERT by rowid), (4) CREATE TRIGGER enforce_immutable_project_id. DDL within transactions is valid in SQLite. Add `new_project_id: str | None = None` parameter.

**Re-attribution Acceptance Criteria:**
- [ ] AC-3.3.1: `update_entity` with `new_project_id` preserves UUID, all tags, dependencies, workflow_phases, and OKR alignments (no data loss)
- [ ] AC-3.3.2: Re-attribution is atomic — failure at any step rolls back (trigger restored)
- [ ] AC-3.3.3: Re-attribution updates the entity's project_id in the composite UNIQUE constraint
- [ ] AC-3.3.4: FTS entry is updated after re-attribution (entity remains searchable)

#### FS-3.2: `_resolve_identifier` project-scoped resolution

```
_resolve_identifier(identifier: str, project_id: str | None = None) -> tuple[str, str]
```

- UUID input → unchanged (globally unique)
- type_id input + `project_id` provided → `WHERE type_id = ? AND project_id = ?`
- type_id input + `project_id` is None ��� query all projects:
  - Exactly 1 match → return it
  - 0 matches → raise `ValueError("Entity not found")`
  - 2+ matches → raise `ValueError("Ambiguous type_id '{x}' found in projects: {list}. Specify project_id.")`

**Acceptance Criteria:**
- [ ] AC-3.2.1: UUID resolution unchanged regardless of project_id
- [ ] AC-3.2.2: type_id with project_id returns correct project's entity
- [ ] AC-3.2.3: type_id without project_id returns entity if globally unique
- [ ] AC-3.2.4: type_id without project_id raises ambiguity error if exists in multiple projects

### FS-4: MCP Server Changes

#### FS-4.1: Entity Server Startup

**File:** `plugins/pd/mcp/entity_server.py`

In `lifespan()`, after DB initialization:
1. `_project_id = detect_project_id(_project_root)` — stored as module global
2. `_upsert_project(db, collect_git_info(_project_root))` — register/update in projects table
3. `_backfill_project_ids(db, _project_root, _project_id)` — claim `'__unknown__'` entities whose `artifact_path` starts with `project_root`

**Ordering requirement (from brainstorm-reviewer warning):** Steps 1-3 must complete synchronously before the server starts serving tool calls. This ensures the first project-scoped query returns correct results. These steps run in the existing `lifespan()` function before `yield {}`, which already gates tool availability.

**Concurrent claim safety (from brainstorm-reviewer warning):** The artifact-path backfill uses `UPDATE entities SET project_id = ? WHERE project_id = '__unknown__' AND artifact_path LIKE ? || '%'` inside a `BEGIN IMMEDIATE` transaction. If two MCP servers race to claim the same entity, the `WHERE project_id = '__unknown__'` clause ensures only the first writer succeeds — the second sees `project_id` already changed and updates 0 rows. This is correct: the entity belongs to whichever project's root contains its artifact_path.

**LIKE escaping:** The `project_root` value used in the LIKE pattern must have `%` and `_` characters escaped before concatenation (replace `%` with `\%`, `_` with `\_`, use `ESCAPE '\'`). While rare in filesystem paths, this prevents incorrect matching.

**Artifact path format:** `artifact_path` is stored as an absolute path in the current codebase (verified: `entity_server.py` constructs paths via `os.path.join(project_root, ...)` and `backfill.py` uses `os.path.abspath()`). The LIKE match on `project_root` prefix is therefore valid.

**Acceptance Criteria:**
- [ ] AC-4.1.1: `_project_id` is populated before first tool call
- [ ] AC-4.1.2: Project is registered in `projects` table at startup
- [ ] AC-4.1.3: `__unknown__` entities with matching artifact_path are claimed
- [ ] AC-4.1.4: Already-claimed entities are not re-claimed by other projects

#### FS-4.2: MCP Tool Parameter Additions

| Tool | New param | Default | Notes |
|------|-----------|---------|-------|
| `register_entity` | `project_id: str \| None`, `auto_id: bool` | `_project_id`, `false` | When `auto_id=true` and `entity_id` omitted: calls `generate_entity_id(db, entity_type, name, project_id)`. When `auto_id=true` and `entity_id` provided: error (conflict). |
| `update_entity` | `project_id: str \| None`, `new_project_id: str \| None` | `_project_id`, `None` | `project_id` for resolution context. `new_project_id` for re-attribution (DELETE+INSERT bypass). |
| `search_entities` | `project_id: str \| None` | `_project_id` | `"*"` for all projects |
| `export_entities` | `project_id: str \| None` | `_project_id` | `"*"` for all projects |
| `export_lineage_markdown` | `project_id: str \| None` | `_project_id` | `"*"` for all projects |
| `get_entity` | No new param | — | Uses `_project_id` internally via `_resolve_identifier` |
| `list_projects` | None | — | **NEW tool** — returns all rows from projects table |

**Sentinel mapping:** MCP tools receive `"*"` string for "all projects" → MCP handler converts to `None` before passing to DB methods (where `None` = all projects). This conversion happens in the MCP tool function, not at the DB layer.

#### FS-4.3: Workflow State Server

**File:** `plugins/pd/mcp/workflow_state_server.py`

- Add `_project_id` global, resolved at startup same as entity_server
- `list_features_by_phase`, `list_features_by_status` — add optional `project_id` param defaulting to `_project_id`

**Acceptance Criteria:**
- [ ] AC-4.3.1: `list_features_by_phase` with default project_id returns only current project's features
- [ ] AC-4.3.2: `list_features_by_status` with explicit project_id filters correctly

### FS-5: Sequential ID Generation

#### FS-5.1: `next_sequence_value(project_id: str, entity_type: str) -> int`

New method on `EntityDatabase`:
1. Check `sequences` table for existing row
2. If no row: bootstrap by scanning entities `WHERE project_id = ? AND entity_type = ?` for max sequential prefix, INSERT with `next_val = max + 1`
3. Read current `next_val` as the issued sequence number, UPDATE `next_val = next_val + 1` (so `next_val` always holds the NEXT value to be issued)
4. Return the issued value (pre-increment)
5. Entire operation within `BEGIN IMMEDIATE` transaction

#### FS-5.2: `id_generator.py` changes

- `generate_entity_id(db, entity_type, name, project_id)` — `project_id` required
- Calls `db.next_sequence_value(project_id, entity_type)` instead of `_metadata` counter
- `_scan_existing_max_seq` deleted (superseded by bootstrap in `next_sequence_value`)

**Acceptance Criteria:**
- [ ] AC-5.1: Different projects get independent sequence counters
- [ ] AC-5.2: Counter bootstraps correctly from existing entities
- [ ] AC-5.3: Concurrent callers don't get duplicate IDs (BEGIN IMMEDIATE serialization)
- [ ] AC-5.4: Old `_metadata` `next_seq_*` keys are not read post-migration

### FS-6: Consumer Updates

#### FS-6.1: `add-to-backlog` command
- Remove file-parsing ID generation logic
- Use `register_entity` MCP tool with `auto_id: true` parameter
- MCP tool calls `next_sequence_value(project_id, "backlog")` internally when `auto_id=true` and `entity_id` is omitted

#### FS-6.2: `backfill.py`
- `run_backfill` and `backfill_workflow_phases` must receive `project_id` parameter
- Pass to `register_entity` / `register_entities_batch` calls
- `project_id` from `detect_project_id(project_root)`

#### FS-6.3: Reconciliation Orchestrator
- `sync_entity_statuses` must pass `project_id` when registering entities
- `project_id` derived from `PROJECT_ROOT` env var via `detect_project_id()`

#### FS-6.4: `show-status` command
- **Traceability note:** `show-status` calls `export_entities` and `list_features_by_phase` MCP tools, which are already covered by FS-4.2 and FS-4.3 (both gain project_id filtering). No additional show-status-specific changes are needed — project scoping flows through automatically from the MCP tool defaults.

#### FS-6.5: Doctor Checks
- Bump `ENTITY_SCHEMA_VERSION` to 8
- `check_entity_orphans`: filter by `project_id` (DB column) instead of heuristic artifact_path matching
- New `check_project_attribution`: warn on `'__unknown__'` entities with determinable project
- Auto-fix capability: run artifact-path backfill for `'__unknown__'` entities via `--fix` flag

**Acceptance Criteria:**
- [ ] AC-6.1: `add-to-backlog` creates entities with correct project_id and sequential ID from DB
- [ ] AC-6.2: Backfill stamps all discovered entities with correct project_id
- [ ] AC-6.3: Reconciliation passes project_id through to entity operations
- [ ] AC-6.4: Doctor reports `__unknown__` entities as warnings
- [ ] AC-6.5: Doctor `--fix` claims `__unknown__` entities via artifact-path heuristic

## Error Handling

| Scenario | Behavior |
|----------|----------|
| `git rev-list` fails | Fall back to `git rev-parse HEAD`, then path hash |
| `git rev-list` times out (>5s) | Fall back to next in chain |
| No git binary | Path hash fallback, `is_git_repo=False` |
| Migration fails mid-transaction | ROLLBACK, DB unchanged |
| Concurrent MCP servers claim same entity | First writer wins (`WHERE project_id='__unknown__'` guard) |
| `_resolve_identifier` ambiguous type_id | Raise `ValueError` with project list |
| `register_entity` called without project_id at DB layer | Error — project_id is required |
| Entity with NULL `artifact_path` | Remains `'__unknown__'` — cannot be claimed by artifact-path backfill. Reported by doctor `check_project_attribution`. Manual re-attribution via `update_entity(new_project_id=...)`. |

## Testing Requirements

### Unit Tests
- `test_project_identity.py` (~12 tests): covers AC-1.1.1 through AC-1.3.5 — detect_project_id fallback chain, collect_git_info fields, normalize_remote_url formats, caching, env var override
- `test_database.py` migration (~15 tests): covers AC-2.1 through AC-2.13 — migration 8 DDL, backfill correctness, composite UNIQUE enforcement, trigger verification, FTS rebuild, sequence migration, rollback safety
- `test_database.py` sequences (~5 tests): covers AC-5.1 through AC-5.4 — next_sequence_value bootstrap, increment, project scoping
- `test_database.py` queries (~6 tests): covers AC-3.2.1 through AC-3.2.4 — _resolve_identifier project scoping, register_entity idempotency change, parent resolution
- `test_database.py` re-attribution (~4 tests): covers AC-3.3.1 through AC-3.3.3 — DELETE+INSERT bypass, related data preservation, rollback on failure
- Doctor tests (~5 tests): covers AC-6.4, AC-6.5 — schema version, project-scoped orphan checks, attribution warnings, auto-fix

### Existing Test Files Requiring Updates
- `test_database.py` — register_entity, delete_entity, set_parent, update_entity signatures gain project_id
- `test_backfill.py` — run_backfill calls gain project_id parameter
- `test_frontmatter_sync.py` — project_id derivation tests may need adjustment for new format
- `test_search_mcp.py` — search_entities gains project_id filtering
- `test_workflow_state_server.py` — list_features_by_phase/status gain project_id
- `test_export_entities.py` — export gains project_id filtering

### Integration Tests
- MCP tool tests (~8 tests): covers AC-4.1.1 through AC-4.3.2 — register with project_id, search filtering, export filtering, list_projects (returns all projects ordered by created_at, no filtering in v1), get_entity resolution
- Backfill tests (~3 tests): covers AC-6.2, AC-6.3 — project_id passed through, reconciliation integration

### Manual Verification
- Backup real DB, start entity_server, verify migration completes
- Run `search_entities` — only current project's entities returned
- Create backlog item — gets project-scoped sequential ID
- Run doctor — no unexpected warnings
