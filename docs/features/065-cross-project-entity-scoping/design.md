# Design: Cross-Project Entity Scoping

## Prior Art Research

### Codebase Patterns
- **Table-rebuild migration:** Migration 6 (`_schema_expansion_v6`, database.py:529-910) is the canonical template — 14-step DDL with self-managed transaction, PRAGMA FK off/on outside transaction, FTS rebuild via Python loop INSERT
- **delete_entity cascade gap:** Current `delete_entity` (database.py:1723-1775) does NOT clean up `entity_tags`, `entity_dependencies`, or `entity_okr_alignment` rows — only `entities_fts` and `workflow_phases`. Design must fix this in migration or note it as pre-existing
- **_resolve_identifier:** database.py:1002-1032 dispatches on UUID regex vs bare `WHERE type_id = ?` — needs project_id WHERE clause
- **register_entity → MCP chain:** entity_server.py:352-398 → server_helpers._process_register_entity (with @with_retry) → db.register_entity(). project_id must flow through this entire chain
- **Backfill versioning:** `_BACKFILL_VERSION = "2"` — must bump to "3" to trigger re-scan with project_id

### External Research
- **PRAGMA foreign_keys:** Must be set OUTSIDE any transaction; silently ignored if set mid-transaction (sqlite.org/foreignkeys.html)
- **Shallow clone:** `git rev-list --max-parents=0 HEAD` returns grafted boundary commit, NOT true root. SHA differs between shallow/full clones. Spec addresses via fallback chain + ENTITY_PROJECT_ID env var override
- **FTS5 rowids:** Restart from 1 on table rebuild — must rebuild FTS after entities table rebuild
- **Multiple roots:** `rev-list --max-parents=0 HEAD` can return multiple lines (orphan branches, merged histories) — take first (sorted by traversal order)
- **URL normalization:** npm/normalize-git-url canonical pattern: SCP colon→slash, strip scheme, strip user@, strip .git, lowercase host

## Architecture Overview

### Components

```
┌─────────────────────────────────────┐
│        project_identity.py          │  NEW
│  detect_project_id()                │
│  collect_git_info() → GitProjectInfo│
│  normalize_remote_url()             │
└──────────────┬──────────────────────┘
               │ called at startup
┌──────────────▼──────────────────────┐
│        entity_server.py             │  MODIFIED
│  _project_id global                 │
│  _upsert_project()                  │
│  _backfill_project_ids()            │
│  MCP tools + project_id params      │
└──────────────┬──────────────────────┘
               │ delegates to
┌──────────────▼──────────────────────┐
│        server_helpers.py            │  MODIFIED
│  _process_register_entity()         │
│  _process_export_entities()         │
│  project_id pass-through            │
└──────────────┬──────────────────────┘
               │ calls
┌──────────────▼──────────────────────┐
│        database.py                  │  MODIFIED
│  Migration 8: _add_project_scoping  │
│  register_entity(project_id)        │
│  _resolve_identifier(project_id)    │
│  next_sequence_value()              │
│  All query methods + project_id     │
└──────────────┬──────────────────────┘
               │ uses
┌──────────────▼──────────────────────┐
│        id_generator.py              │  MODIFIED
│  generate_entity_id(project_id)     │
│  Uses sequences table               │
└─────────────────────────────────────┘
```

### Data Flow

**Entity Registration (post-migration):**
```
MCP register_entity(entity_type, entity_id, name, ..., project_id=None)
  → project_id ||= _project_id (server global)
  → server_helpers._process_register_entity(db, ..., project_id)
    → db.register_entity(entity_type, entity_id, name, ..., project_id)
      → INSERT OR IGNORE INTO entities (..., project_id, ...)
      → UNIQUE(project_id, type_id) deduplication
      → FTS INSERT
```

**Entity Query (post-migration):**
```
MCP search_entities(query, entity_type, project_id=None)
  → project_id ||= _project_id; if project_id == "*": project_id = None
  → db.search_entities(query, entity_type, limit, project_id)
    → FTS MATCH query
    → JOIN entities WHERE project_id = ? (if not None)
```

**Startup Sequence:**
```
lifespan():
  1. _db = init_db(path)           # triggers migration 8 if needed
  2. _project_id = detect_project_id(_project_root)
  3. _upsert_project(_db, collect_git_info(_project_root))
  4. _backfill_project_ids(_db, _project_root, _project_id)
  5. run_backfill(_db, _artifacts_root, _project_id)  # existing backfill, now with project_id
  6. yield {}  # server ready
```

## Technical Decisions

### TD-1: All existing entities get `'__unknown__'` during migration
**Decision:** Do NOT use `json_extract(metadata, '$.project_id')` during migration.
**Rationale:** Existing metadata.project_id values are project entity IDs (e.g., `"P001"`) — a different format from the 12-char hex SHA that `detect_project_id()` produces. Using them would create format-mismatched project_ids that never match.
**Consequence:** All entities start as `'__unknown__'`. Artifact-path backfill at each MCP startup progressively claims them with correct SHA-based project_id.
**PRD Update Required:** PRD FR-1 and Migration Row States table still reference json_extract. PRD must be updated to match this decision (spec supersedes).

### TD-2: parent_type_id FK dropped, parent_uuid FK retained
**Decision:** Remove `REFERENCES entities(type_id)` on parent_type_id column.
**Rationale:** type_id is no longer globally UNIQUE after composite constraint change. parent_uuid remains the real FK (uuid is PK, globally unique). parent_type_id kept as denormalized data for human readability.

### TD-3: project_id is immutable via trigger
**Decision:** Add `enforce_immutable_project_id` trigger. Re-attribution requires DELETE+re-INSERT bypass.
**Rationale:** Prevents accidental project_id corruption from casual UPDATEs. Intentional re-attribution is rare and should be explicit.

### TD-4: Workflow phases table does NOT gain project_id column
**Decision:** workflow_phases queries use type_id but are always preceded by project-scoped entity resolution.
**Rationale:** Adding project_id to workflow_phases would require another table rebuild with minimal benefit since all callers already resolve entities within project context first.
**Safeguard:** `upsert_workflow_phase` gains project_id parameter (required, not optional) for entity existence check.

### TD-5: Sequences table replaces _metadata counters atomically
**Decision:** Migration moves `next_seq_*` keys to `sequences` table AND deletes old keys in the same transaction.
**Rationale:** Prevents dual-read scenarios where old code reads _metadata and new code reads sequences.

### TD-6: delete_entity cascade extended
**Decision:** Fix pre-existing cascade gap: delete_entity must also clean up entity_tags, entity_dependencies, entity_okr_alignment rows by UUID before deleting the entity.
**Rationale:** Discovered during codebase research — junction table rows are orphaned by current delete_entity. This is a bug fix bundled with the feature.

### TD-8: Re-attribution uses trigger-drop, not DELETE+re-INSERT
**Decision:** Re-attribution (`update_entity` with `new_project_id`) temporarily drops and recreates the `enforce_immutable_project_id` trigger within a `BEGIN IMMEDIATE` transaction:
```sql
BEGIN IMMEDIATE;
DROP TRIGGER enforce_immutable_project_id;
UPDATE entities SET project_id = ? WHERE uuid = ?;
-- FTS sync: DELETE + INSERT by rowid (standard pattern from update_entity)
CREATE TRIGGER enforce_immutable_project_id
    BEFORE UPDATE OF project_id ON entities
    BEGIN SELECT RAISE(ABORT, 'project_id is immutable — use re-attribution API'); END;
COMMIT;
```
**Rationale:** 3 statements vs ~12 for DELETE+re-INSERT cascade. No risk of losing related data (tags, deps, OKR, workflow_phases). DDL within transactions is valid in SQLite and already used by the migration itself. FTS sync uses the same DELETE+INSERT-by-rowid pattern as regular `update_entity`.

### TD-7: Shallow clone detection
**Decision:** Add `git rev-parse --is-shallow-repository` check before `rev-list`. If shallow, skip directly to HEAD SHA fallback.
**Rationale:** Shallow clone's `rev-list --max-parents=0 HEAD` returns grafted boundary commit (wrong SHA). Detecting shallow state avoids silently returning the wrong project_id.

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Migration 8 fails on real DB | Data loss | Low | Transactional rollback; pre-migration backup recommended |
| FTS rowid desync after rebuild | Search broken | Medium | Explicit FTS rebuild step; verified by AC-2.8 |
| `__unknown__` entities accumulate | Incorrect queries | Medium | Progressive artifact-path backfill; doctor check warns |
| Concurrent MCP servers race on backfill | Double-claim | Low | `WHERE project_id='__unknown__'` guard ensures first-writer-wins |
| Workflow phases leak across projects | Wrong phase data | Low | upsert_workflow_phase project_id check (TD-4) |
| FTS queries scan all projects then filter | Slow search | Low | At current scale (<1000 entities, <10 projects) negligible. If scale grows, project_id can be added to FTS content for direct filtering. |
| lru_cache(maxsize=1) thrash on mixed args | Cache miss | Low | Contract: detect_project_id MUST be called with same working_dir per-process. MCP servers call once at startup. |

## Interfaces

### I-1: `project_identity.py` Public API

```python
# --- Types ---
@dataclasses.dataclass(frozen=True)
class GitProjectInfo:
    project_id: str          # 12-char hex
    root_commit_sha: str     # full 40-char or ""
    name: str                # human-readable
    remote_url: str          # raw origin URL or ""
    normalized_url: str      # canonical host/owner/repo or ""
    remote_host: str         # e.g. "github.com" or ""
    remote_owner: str        # e.g. "terry" or ""
    remote_repo: str         # e.g. "pedantic-drip" or ""
    default_branch: str      # e.g. "main" or ""
    project_root: str        # absolute path
    is_git_repo: bool

# --- Functions ---
@functools.lru_cache(maxsize=1)
def detect_project_id(working_dir: str | None = None) -> str:
    """12-char hex project identifier. Env var ENTITY_PROJECT_ID overrides.
    Fallback: root commit SHA → HEAD SHA (skip if shallow) → abs path hash."""

def collect_git_info(working_dir: str | None = None) -> GitProjectInfo:
    """All git metadata for projects table. Each field fails independently."""

def normalize_remote_url(raw_url: str) -> str:
    """Canonical 'host/owner/repo' form. Empty string → empty string."""
```

### I-2: `database.py` New/Changed Methods

```python
# --- Migration ---
def _add_project_scoping(conn: sqlite3.Connection) -> None:
    """Migration 8. Self-managed transaction (BEGIN IMMEDIATE / COMMIT / ROLLBACK)."""

# --- New method ---
def next_sequence_value(self, project_id: str, entity_type: str) -> int:
    """Atomic: read next_val, return it, increment. Bootstraps from entities scan."""

# --- Changed signatures ---
def register_entity(self, entity_type, entity_id, name, artifact_path=None,
                    status=None, parent_type_id=None, metadata=None,
                    project_id: str) -> str:  # project_id REQUIRED, returns uuid

def register_entities_batch(self, entities: list[dict],
                            project_id: str) -> dict:  # project_id REQUIRED

def _resolve_identifier(self, identifier: str,
                        project_id: str | None = None) -> tuple[str, str]:
    """UUID → unchanged. type_id → filter by project_id if provided,
    else return if globally unique, raise ambiguity error if not."""

def resolve_ref(self, ref: str,
                project_id: str | None = None) -> str:
    """Returns UUID (str). Three resolution paths: UUID lookup, exact type_id,
    prefix search — all gain project_id filtering. Return type unchanged from current."""

def search_by_type_id_prefix(self, prefix: str,
                              project_id: str | None = None) -> list[dict]:

def list_entities(self, entity_type: str | None = None,
                  project_id: str | None = None) -> list[dict]:

def search_entities(self, query: str, entity_type: str | None = None,
                    limit: int = 20,
                    project_id: str | None = None) -> list[dict]:

def export_entities_json(self, entity_type=None, status=None,
                         include_lineage=True,
                         project_id: str | None = None) -> dict:

def export_lineage_markdown(self, type_id=None,
                            project_id: str | None = None) -> str:

def scan_entity_ids(self, entity_type: str,
                    project_id: str | None = None) -> list[str]:

def set_parent(self, type_id: str, parent_type_id: str,
               project_id: str | None = None) -> dict:

def update_entity(self, type_id: str,
                  name: str | None = None, status: str | None = None,
                  artifact_path: str | None = None, metadata: dict | None = None,
                  project_id: str | None = None,
                  new_project_id: str | None = None) -> None:
    """Signature matches current source (None defaults, None return).
    Only project_id and new_project_id are new parameters.
    new_project_id triggers re-attribution via trigger-drop approach (TD-8)."""

def delete_entity(self, type_id: str,
                  project_id: str | None = None) -> None:
    """Return type unchanged (None). Extended cascade: entity_tags,
    entity_dependencies, entity_okr_alignment, workflow_phases,
    entities_fts, entities."""

def upsert_workflow_phase(self, type_id: str, project_id: str, **kwargs):
    """project_id REQUIRED for entity existence check."""
```

### I-3: `id_generator.py` Changed Signature

```python
def generate_entity_id(db: EntityDatabase, entity_type: str, name: str,
                       project_id: str) -> str:
    """project_id REQUIRED. Uses db.next_sequence_value()."""
```

### I-4: `entity_server.py` New/Changed MCP Tools

```python
# Module globals (added)
_project_id: str = ""
_git_info: GitProjectInfo | None = None

# Changed tools
@server.tool()
async def register_entity(entity_type, entity_id=None, name, ...,
                          project_id=None, auto_id=False):
    """project_id defaults to _project_id. auto_id=True generates entity_id
    via generate_entity_id(). Conflict: auto_id=True + entity_id → error."""

@server.tool()
async def update_entity(type_id, ..., project_id=None, new_project_id=None):
    """project_id for resolution. new_project_id for re-attribution."""

@server.tool()
async def search_entities(query, entity_type=None, limit=20, project_id=None):
    """Defaults to _project_id. "*" → None (all projects)."""

@server.tool()
async def export_entities(entity_type=None, ..., project_id=None):
    """Defaults to _project_id. "*" → None (all projects)."""

@server.tool()
async def export_lineage_markdown(type_id=None, ..., project_id=None):
    """Defaults to _project_id. "*" → None (all projects)."""

# New tools
@server.tool()
async def list_projects() -> list[dict]:
    """Returns all projects ordered by created_at. No filters in v1."""

# Startup functions (added to lifespan)
def _upsert_project(db, info: GitProjectInfo) -> None:
    """INSERT OR REPLACE into projects table."""

def _upsert_project(db, info: GitProjectInfo) -> None:
    """INSERT INTO projects (...) VALUES (...) ON CONFLICT(project_id) DO UPDATE SET
    name=excluded.name, remote_url=excluded.remote_url, ...
    (omits created_at from UPDATE SET to preserve original creation time)."""

def _backfill_project_ids(db, project_root: str, project_id: str) -> int:
    """UPDATE entities SET project_id=? WHERE project_id='__unknown__'
    AND artifact_path LIKE escaped_root || '%' ESCAPE '\\'.
    Returns count of claimed entities.
    Note: entities with NULL artifact_path cannot be claimed — they remain
    '__unknown__' and are reported by doctor check_project_attribution."""
```

### I-5: `server_helpers.py` Changed Functions

```python
def _process_register_entity(db, entity_type, entity_id, name, ...,
                             project_id: str, auto_id: bool = False) -> str:
    """Passes project_id to db.register_entity(). Handles auto_id."""

def _process_export_entities(db, entity_type, status, ...,
                             project_id: str | None = None, ...) -> dict:
    """Passes project_id to db.export_entities_json()."""
```

### I-6: Migration 8 DDL (Exact SQL)

```sql
-- Step 3: projects table
CREATE TABLE projects (
    project_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    root_commit_sha TEXT,
    remote_url      TEXT,
    normalized_url  TEXT,
    remote_host     TEXT,
    remote_owner    TEXT,
    remote_repo     TEXT,
    default_branch  TEXT,
    project_root    TEXT,
    is_git_repo     INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- Step 4: sequences table
CREATE TABLE sequences (
    project_id  TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    next_val    INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (project_id, entity_type)
);

-- Step 5: entities_new (target schema)
CREATE TABLE entities_new (
    uuid           TEXT NOT NULL PRIMARY KEY,
    type_id        TEXT NOT NULL,
    project_id     TEXT NOT NULL DEFAULT '__unknown__',
    entity_type    TEXT NOT NULL,
    entity_id      TEXT NOT NULL,
    name           TEXT NOT NULL,
    status         TEXT,
    parent_type_id TEXT,
    parent_uuid    TEXT REFERENCES entities_new(uuid),
    artifact_path  TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    metadata       TEXT,
    UNIQUE(project_id, type_id)
);

-- Step 6: data copy
INSERT INTO entities_new (uuid, type_id, project_id, entity_type, entity_id,
    name, status, parent_type_id, parent_uuid, artifact_path,
    created_at, updated_at, metadata)
SELECT uuid, type_id, '__unknown__', entity_type, entity_id,
    name, status, parent_type_id, parent_uuid, artifact_path,
    created_at, updated_at, metadata
FROM entities;

-- Step 7: swap
DROP TABLE entities;
ALTER TABLE entities_new RENAME TO entities;

-- Step 8: triggers (9 total)
CREATE TRIGGER IF NOT EXISTS enforce_immutable_type_id
    BEFORE UPDATE OF type_id ON entities
    BEGIN SELECT RAISE(ABORT, 'type_id is immutable'); END;
CREATE TRIGGER IF NOT EXISTS enforce_immutable_entity_type
    BEFORE UPDATE OF entity_type ON entities
    BEGIN SELECT RAISE(ABORT, 'entity_type is immutable'); END;
CREATE TRIGGER IF NOT EXISTS enforce_immutable_created_at
    BEFORE UPDATE OF created_at ON entities
    BEGIN SELECT RAISE(ABORT, 'created_at is immutable'); END;
CREATE TRIGGER IF NOT EXISTS enforce_immutable_uuid
    BEFORE UPDATE OF uuid ON entities
    BEGIN SELECT RAISE(ABORT, 'uuid is immutable'); END;
CREATE TRIGGER IF NOT EXISTS enforce_immutable_project_id
    BEFORE UPDATE OF project_id ON entities
    BEGIN SELECT RAISE(ABORT, 'project_id is immutable — use re-attribution API'); END;
CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent
    BEFORE INSERT ON entities WHEN NEW.parent_type_id = NEW.type_id
    BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END;
CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_update
    BEFORE UPDATE OF parent_type_id ON entities WHEN NEW.parent_type_id = NEW.type_id
    BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent'); END;
CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_uuid_insert
    BEFORE INSERT ON entities WHEN NEW.parent_uuid = NEW.uuid
    BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent (uuid)'); END;
CREATE TRIGGER IF NOT EXISTS enforce_no_self_parent_uuid_update
    BEFORE UPDATE OF parent_uuid ON entities WHEN NEW.parent_uuid = NEW.uuid
    BEGIN SELECT RAISE(ABORT, 'entity cannot be its own parent (uuid)'); END;

-- Step 9: indexes (6 total)
CREATE INDEX IF NOT EXISTS idx_entity_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_status ON entities(status);
CREATE INDEX IF NOT EXISTS idx_parent_type_id ON entities(parent_type_id);
CREATE INDEX IF NOT EXISTS idx_parent_uuid ON entities(parent_uuid);
CREATE INDEX IF NOT EXISTS idx_project_id ON entities(project_id);
CREATE INDEX IF NOT EXISTS idx_project_entity_type ON entities(project_id, entity_type);

-- Step 10: migrate _metadata counters
-- (Python loop: for each row WHERE key LIKE 'next_seq_%':
--   parse entity_type, INSERT INTO sequences('__unknown__', entity_type, int(value))
--   DELETE FROM _metadata WHERE key = ?)

-- Step 11: FTS rebuild
DROP TABLE IF EXISTS entities_fts;
CREATE VIRTUAL TABLE entities_fts USING fts5(
    name, entity_id, entity_type, status, metadata_text
);
-- (Python loop: INSERT INTO entities_fts for each entity row)

-- Step 12: version
INSERT INTO _metadata (key, value) VALUES ('schema_version', '8')
    ON CONFLICT(key) DO UPDATE SET value = '8';
```

### I-7: `backfill.py` Changes

```python
# Bump version
_BACKFILL_VERSION = "3"  # v3: project_id scoping

# Changed signature
def run_backfill(db: EntityDatabase, artifacts_root: str,
                 project_id: str) -> None:
    """project_id passed to all register_entity calls.
    Existing backfill guard: backfill_complete='1' AND backfill_version >= _BACKFILL_VERSION.
    Bumping to '3' triggers re-backfill because '2' < '3' (string comparison).
    Confirmed: backfill.py:144-146 checks both flags together."""

def backfill_workflow_phases(db: EntityDatabase, artifacts_root: str) -> dict:
    """Unchanged signature — workflow_phases don't need project_id."""
```

### I-8: `workflow_state_server.py` Startup

```python
# workflow_state_server resolves _project_id via detect_project_id() at startup
# but does NOT run _upsert_project or _backfill_project_ids.
# Entity_server owns project registration and backfill.
# Query results may include '__unknown__' entities until entity_server's backfill runs.
_project_id: str = ""  # resolved in lifespan, same pattern as entity_server
```

### I-9: `doctor/checks.py` Changes

```python
ENTITY_SCHEMA_VERSION = 8  # bumped from 7

def check_project_attribution(entities_conn, project_root=None, **kwargs):
    """Warn on entities with project_id='__unknown__' that have
    artifact_path under a known project root."""
    # --fix: run artifact-path backfill for __unknown__ entities
```
