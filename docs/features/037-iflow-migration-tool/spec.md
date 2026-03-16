# Specification: iflow Migration Tool

## Overview

A `scripts/migrate.sh` script providing `export` and `import` subcommands for migrating all global iflow state between machines. Bash wrapper delegates to Python for SQLite operations.

## Scope

**In scope:** Global iflow state at `~/.claude/iflow/` — two SQLite databases and markdown memory files.

**Out of scope:** Project-level state (`docs/knowledge-bank/`, `.meta.json`), plugin files, venv, per-project configs (`iflow.local.md`), cloud sync, encryption, GUI.

## Data Inventory

| Store | Default Path | Type | Export Method |
|-------|-------------|------|---------------|
| Semantic memory DB | `~/.claude/iflow/memory/memory.db` | SQLite (WAL) | `sqlite3.Connection.backup()` — hardcoded path |
| Entity registry DB | `~/.claude/iflow/entities/entities.db` | SQLite (WAL) | `sqlite3.Connection.backup()` — respects `ENTITY_DB_PATH` env override |
| Memory markdown files | `~/.claude/iflow/memory/*.md` | Markdown | File copy |
| Project registry | `~/.claude/iflow/projects.txt` | Text | File copy (if exists) |

## File Structure

```
scripts/
  migrate.sh          # Bash entry point (CLI parsing, UX, file ops)
  migrate_db.py       # Python helper (SQLite backup, merge, verify)
```

## CLI Interface

### Export

```
scripts/migrate.sh export [output-path] [--force]

  output-path   Optional. Defaults to ~/iflow-export-YYYYMMDD-HHMMSS.tar.gz
  --force       Proceed even if active Claude session detected
```

**Exit codes:** 0 = success, 1 = error, 2 = active session detected (without --force)

### Import

```
scripts/migrate.sh import <bundle-path> [--dry-run] [--force]

  bundle-path   Required. Path to .tar.gz bundle from export
  --dry-run     Preview what would be restored, no changes made
  --force       Overwrite existing files instead of skipping
```

**Exit codes:** 0 = success, 1 = error, 3 = bundle validation failed

### Help

```
scripts/migrate.sh help
scripts/migrate.sh --help
scripts/migrate.sh            # (no args) prints help
```

## Bundle Format

```
iflow-export-YYYYMMDD-HHMMSS/
  manifest.json
  projects.txt                # Project registry (if exists)
  memory/
    memory.db                 # SQLite backup (WAL-safe)
    *.md                      # Category markdown files
  entities/
    entities.db               # SQLite backup (WAL-safe)
```

Compressed to `iflow-export-YYYYMMDD-HHMMSS.tar.gz`.

### manifest.json Schema

```json
{
  "schema_version": 1,
  "plugin_version": "4.12.4-dev",
  "export_timestamp": "2026-03-16T02:54:08Z",
  "source_platform": "darwin-arm64",
  "python_version": "3.11.6",
  "embedding_provider": "gemini",
  "embedding_model": "text-embedding-004",
  "files": {
    "memory/memory.db": {
      "sha256": "abc123...",
      "size_bytes": 1048576,
      "entry_count": 142
    },
    "entities/entities.db": {
      "sha256": "def456...",
      "size_bytes": 524288,
      "entity_count": 87,
      "workflow_phases_count": 45
    },
    "memory/patterns.md": {
      "sha256": "789abc...",
      "size_bytes": 4096
    }
  }
}
```

## Acceptance Criteria

### AC-1: Export produces valid bundle
- **Given** no active Claude session
- **When** `scripts/migrate.sh export` is run
- **Then** a `.tar.gz` file is created containing manifest.json and all data stores
- **And** all SHA-256 checksums in manifest match actual file contents
- **And** step-by-step progress is printed to stderr

### AC-2: SQLite databases use .backup API
- **Given** memory.db or entities.db exists with WAL-mode data
- **When** export runs
- **Then** databases are backed up via Python `sqlite3.Connection.backup()`
- **And** the exported .db files pass `PRAGMA integrity_check`
- **And** entry counts match source databases

### AC-3: Active session detection
- **Given** MCP server processes are running (`pgrep -f 'memory_server|entity_server|workflow_state_server'`)
- **When** `scripts/migrate.sh export` is run without `--force`
- **Then** script warns "Active Claude session detected" and exits with code 2
- **When** `--force` is provided
- **Then** export proceeds with a warning

### AC-4: Import on fresh machine (no existing state)
- **Given** `~/.claude/iflow/` does not exist or is empty, and no active Claude session (or `--force` provided)
- **When** `scripts/migrate.sh import bundle.tar.gz` is run
- **Then** directory structure is created
- **And** database files are copied directly (no merge needed)
- **And** markdown files are copied
- **And** post-import verification passes (entry counts match manifest, `PRAGMA integrity_check` OK)

### AC-5: Import with existing state (merge)
- **Given** destination already has memory.db and entities.db with data, and no active Claude session (or `--force` provided)
- **When** `scripts/migrate.sh import bundle.tar.gz` is run
- **Then** memory entries are merged using source_hash deduplication (skip rows where source_hash exists in destination)
- **And** entity records are merged using `INSERT OR IGNORE` on `type_id` UNIQUE constraint (destination-wins). New UUIDs are generated for inserted rows since `uuid` is the actual PK.
- **And** `PRAGMA foreign_keys = OFF` is set during merge to avoid insertion-order issues (child before parent); type_id validity is enforced by the WHERE clause filtering against destination
- **And** for each newly inserted entity, its `workflow_phases` row is also inserted
- **And** for skipped entities (type_id conflict), workflow_phases rows are also skipped
- **And** markdown files are skipped if they already exist (unless `--force`)
- **And** summary reports: N entries added, M skipped

### AC-6: Dry-run mode
- **Given** a valid bundle file
- **When** `scripts/migrate.sh import --dry-run bundle.tar.gz` is run
- **Then** output shows: files to add, files to skip, DB entries to merge vs skip
- **And** no filesystem changes are made
- **And** exit code is 0

### AC-7: Bundle validation
- **Given** a corrupt or tampered bundle
- **When** import is attempted
- **Then** SHA-256 checksum mismatch is detected before any files are touched
- **And** clear error message is printed
- **And** exit code is 3

### AC-8: Version compatibility
- **Given** a bundle with `schema_version` higher than `SUPPORTED_SCHEMA_VERSION` (constant in migrate_db.py, initially 1)
- **When** import is attempted
- **Then** error: "Bundle schema version {n} is not supported. This script supports up to version {max}. Update your iflow plugin."
- **Given** a bundle with `schema_version` equal to or lower than supported
- **When** import is attempted
- **Then** import proceeds (forward-compatible)

### AC-9: Embedding provider mismatch warning
- **Given** bundle's `embedding_provider` differs from destination's `_metadata.embedding_provider`
- **When** import runs
- **Then** warning: "Embeddings were generated with {provider}/{model}. Semantic search may degrade. Run backfill to regenerate."
- **And** import continues (embeddings are still imported)
- **Given** destination has no `_metadata` table (fresh machine)
- **When** import runs
- **Then** mismatch check is skipped (no baseline to compare against)

### AC-10: Force mode
- **Given** destination has existing markdown files
- **When** `scripts/migrate.sh import --force bundle.tar.gz` is run
- **Then** existing files are overwritten instead of skipped
- **And** database merge still uses INSERT OR IGNORE (force only affects files)

### AC-11: Post-import verification
- **Given** import completes
- **When** verification runs
- **Then** `PRAGMA integrity_check` passes on both databases
- **And** entry counts are compared: manifest vs actual
- **And** any discrepancy is reported with a warning (not a failure)

### AC-12: ENTITY_DB_PATH override
- **Given** `ENTITY_DB_PATH` env var is set to a custom path
- **When** export runs
- **Then** entities.db is read from the custom path (not default)
- **When** import runs
- **Then** entities.db is written to the custom path

### AC-13: Disk full / partial failure handling
- **Given** import is in progress and disk runs out of space
- **When** a write operation fails
- **Then** script aborts cleanly
- **And** reports what was and wasn't restored
- **And** does NOT leave partial database state — all DB merges are wrapped in a single `BEGIN`/`COMMIT` transaction per database; on failure, Python's `connection.rollback()` reverts all inserts
- **And** file copies that already completed remain on disk (no filesystem rollback); the error message lists which files were and weren't restored
- **And** exit code is 1

### AC-14: Progress output
- **Given** export or import is running
- **Then** step-by-step progress is printed to stderr: "Step N/M: {description}..."
- **And** completed steps show past tense: "Step N/M: {description}... done"
- **And** `NO_COLOR` env var suppresses ANSI color codes

### AC-15: Post-import doctor check
- **Given** import completes successfully
- **When** verification step runs
- **Then** if `scripts/doctor.sh` exists, invoke it and report pass/fail. If doctor.sh is unavailable (fresh machine, no dev workspace), fall back to inline health checks: both databases respond to `SELECT count(*) FROM {main_table}`, markdown files are readable.
- **And** if any check fails, warning is printed but import is not rolled back (data is already committed)
- **And** output suggests "Run your first Claude session to verify MCP servers can connect"
- **Note:** doctor.sh is the canonical health check (PRD SC-7). Inline checks are a subset approximation for environments where doctor.sh is not present. doctor.sh is resolved via the same plugin path discovery logic as VENV_PYTHON (dev workspace first, then plugin cache Glob).

## Technical Specifications

### migrate.sh (Bash)

**Responsibilities:**
- CLI argument parsing (subcommand, flags, paths)
- Active session detection (`pgrep -f`)
- Directory creation and file copy operations
- tar.gz compression/extraction
- Progress output to stderr
- Invoking `migrate_db.py` for all SQLite operations

**Session detection:**
```bash
if pgrep -f 'memory_server|entity_server|workflow_state_server' > /dev/null 2>&1; then
  # Active session detected
fi
```
Note: Pattern should be verified against actual MCP server launch commands during implementation. If `pgrep` pattern doesn't match, fall back to checking for `.db-wal` file size > 0 as a secondary indicator.

**Session detection also applies to import** (same logic, same exit code 2). Both export and import check for active sessions before proceeding.

**Python invocation:**
```bash
# Try dev workspace venv first, then plugin cache, then system Python
VENV_PYTHON="$(dirname "$0")/../plugins/iflow/.venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
  VENV_PYTHON="$(ls ~/.claude/plugins/cache/*/iflow*/*/.venv/bin/python 2>/dev/null | head -1)"
fi
if [ -z "$VENV_PYTHON" ] || [ ! -x "$VENV_PYTHON" ]; then
  VENV_PYTHON="python3"  # fallback — acceptable since migrate_db.py uses only stdlib
fi
"$VENV_PYTHON" "$(dirname "$0")/migrate_db.py" "$@"
```

### migrate_db.py (Python)

**Responsibilities:**
- SQLite `.backup` API calls
- Manifest generation (checksums, entry counts, metadata)
- Manifest validation on import
- Database merge logic (source_hash dedup for memory, INSERT OR IGNORE for entities)
- Post-import verification (PRAGMA integrity_check, count comparison)
- Embedding provider mismatch detection

**Key functions:**

```python
def backup_database(src_path: str, dst_path: str) -> dict:
    """Backup SQLite DB using .backup API. Returns {sha256, size_bytes, entry_count}."""

def generate_manifest(staging_dir: str, plugin_version: str) -> dict:
    """Generate manifest.json with checksums and metadata.

    Sources:
    - plugin_version: read from plugins/iflow/plugin.json "version" field
    - embedding_provider/model: read from memory.db _metadata table (keys: embedding_provider, embedding_model)
    - python_version: platform.python_version()
    - source_platform: f"{sys.platform}-{platform.machine()}" (e.g. 'darwin-arm64')
    - entry_count: SELECT count(*) FROM entries
    - entity_count: SELECT count(*) FROM entities
    - workflow_phases_count: SELECT count(*) FROM workflow_phases
    """

def validate_manifest(bundle_dir: str) -> tuple[bool, list[str]]:
    """Validate bundle checksums. Returns (valid, error_messages)."""

def merge_memory_db(src_path: str, dst_path: str, dry_run: bool = False) -> dict:
    """Merge memory entries using source_hash dedup. Returns {added, skipped}."""

def merge_entities_db(src_path: str, dst_path: str, dry_run: bool = False) -> dict:
    """Merge entities + workflow_phases using type_id dedup. Returns {added, skipped}."""

def verify_database(db_path: str, expected_count: int, table: str) -> dict:
    """Run PRAGMA integrity_check and count comparison. Returns {ok, actual_count, integrity}.
    If expected_count is 0, skip count validation and just return actual_count + integrity."""

def detect_embedding_mismatch(bundle_manifest: dict, dst_db_path: str) -> str | None:
    """Compare embedding_provider/model. Returns warning message or None.

    If dst_db_path does not exist or has no _metadata table, returns None (fresh machine — skip check).
    Reads destination provider from: SELECT value FROM _metadata WHERE key='embedding_provider'.
    """
```

**Merge strategy detail:**

```python
# memory.db merge
def merge_memory_db(src_path, dst_path, dry_run=False):
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)

    # Resolve column names (robust against schema evolution)
    src_cols = [desc[0] for desc in src.execute("SELECT * FROM entries LIMIT 0").description]
    source_hash_idx = src_cols.index("source_hash")

    src_entries = src.execute("SELECT * FROM entries").fetchall()
    dst_hashes = {row[0] for row in dst.execute("SELECT source_hash FROM entries")}

    added, skipped = 0, 0
    dst.execute("BEGIN")
    for entry in src_entries:
        source_hash = entry[source_hash_idx]
        if source_hash in dst_hashes:
            skipped += 1
        else:
            if not dry_run:
                dst.execute(f"INSERT INTO entries VALUES ({','.join('?' * len(entry))})", entry)
            added += 1

    if not dry_run:
        dst.commit()
    return {"added": added, "skipped": skipped}

# entities.db merge
# Schema: uuid TEXT NOT NULL PRIMARY KEY, type_id TEXT NOT NULL UNIQUE, ...
# Dedup key: type_id (UNIQUE constraint), NOT uuid (PK)
# Must generate new uuids for inserted rows to avoid PK collision
import uuid as uuid_mod

def merge_entities_db(src_path, dst_path, dry_run=False):
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    dst.execute("PRAGMA foreign_keys = OFF")  # OFF: avoids insertion-order FK violations; WHERE clause validates type_id

    # Get column names for proper mapping
    src_cols = [desc[0] for desc in src.execute("SELECT * FROM entities LIMIT 0").description]
    type_id_idx = src_cols.index("type_id")
    uuid_idx = src_cols.index("uuid")

    src_entities = src.execute("SELECT * FROM entities").fetchall()
    dst_type_ids = {row[0] for row in dst.execute("SELECT type_id FROM entities")}
    added, skipped = 0, 0

    dst.execute("BEGIN")
    for entity in src_entities:
        type_id = entity[type_id_idx]
        if type_id in dst_type_ids:
            skipped += 1
            continue

        if not dry_run:
            # Generate new uuid to avoid PK collision
            row = list(entity)
            row[uuid_idx] = str(uuid_mod.uuid4())
            dst.execute(f"INSERT INTO entities VALUES ({','.join('?' * len(row))})", row)
            # Also insert workflow_phases row (FK: type_id)
            wp = src.execute("SELECT * FROM workflow_phases WHERE type_id=?", (type_id,)).fetchone()
            if wp:
                dst.execute(f"INSERT OR IGNORE INTO workflow_phases VALUES ({','.join('?' * len(wp))})", wp)
        added += 1

    if not dry_run:
        dst.commit()
    return {"added": added, "skipped": skipped}
```

### Export Flow (Step-by-Step)

```
Step 1/6: Checking for active sessions...
Step 2/6: Creating staging directory...
Step 3/6: Backing up semantic memory database... done (142 entries)
Step 4/6: Backing up entity registry database... done (87 entities, 45 workflow phases)
Step 5/6: Copying memory files... done (3 files)
Step 6/6: Creating bundle... done

Export complete:
  Bundle: ~/iflow-export-20260316-025408.tar.gz
  Size: 2.1 MB
  SHA-256: abc123...

  Contents:
    memory.db: 142 entries
    entities.db: 87 entities, 45 workflow phases
    Markdown files: 3

  ⚠ This bundle contains private workflow history. Treat as sensitive.
```

### Import Flow (Step-by-Step)

```
Step 1/8: Validating bundle... done (schema v1, exported 2026-03-16)
Step 2/8: Checking for active sessions...
Step 3/8: Checking embedding compatibility...
Step 4/8: Creating directory structure...
Step 5/8: Restoring semantic memory... done (added 142, skipped 0)
Step 6/8: Restoring entity registry... done (added 80, skipped 7 conflicts)
Step 7/8: Copying memory files... done (added 2, skipped 1 existing)
Step 8/8: Verifying integrity... done

Import complete:
  Memory entries: 142 added, 0 skipped
  Entity records: 80 added, 7 skipped (destination-wins)
  Markdown files: 2 added, 1 skipped (already exists)
  Integrity: ✓ All databases passed PRAGMA integrity_check

  ⚠ Embeddings generated with gemini/text-embedding-004. Semantic search may degrade if you use a different provider.
```

### Dry-Run Output

```
Dry-run preview (no changes will be made):

  Bundle: iflow-export-20260316-025408.tar.gz (schema v1)

  Semantic memory:
    Would add: 120 entries
    Would skip: 22 entries (source_hash exists)

  Entity registry:
    Would add: 65 entities (+ workflow phases)
    Would skip: 22 entities (type_id exists, destination-wins)

  Markdown files:
    Would add: patterns.md, heuristics.md
    Would skip: anti-patterns.md (already exists)
```

## Constraints

- Must NOT copy raw .db files — always use `sqlite3.Connection.backup()`
- Must NOT overwrite existing state without `--force`
- Must NOT export project-level data (docs/knowledge-bank/, .meta.json)
- Must NOT require active Claude session
- Export < 30 seconds for typical state (≤500 memory entries, ≤200 entities, ≤10 markdown files)
- Bundle < 50MB for typical usage
- No dependencies beyond Python 3.8+ stdlib + iflow venv
- Respects `NO_COLOR` env var
- `plugin_version` in manifest sourced from `plugins/iflow/plugin.json` (Glob: `~/.claude/plugins/cache/*/iflow*/*/plugin.json`, fallback `plugins/iflow/plugin.json`)
- Tables enumerated for merge: `entries` (memory.db), `entities` + `workflow_phases` (entities.db). Future tables require migrate_db.py update.

## Error Messages

| Condition | Message | Exit Code |
|-----------|---------|-----------|
| No subcommand | `Usage: migrate.sh {export|import|help}` | 1 |
| Active session (no --force) | `Error: Active Claude session detected (MCP servers running). Close all Claude sessions or use --force.` | 2 |
| Bundle not found | `Error: Bundle not found: {path}` | 1 |
| Checksum mismatch | `Error: Bundle integrity check failed. File {name}: expected {expected}, got {actual}` | 3 |
| Schema version too new | `Error: Bundle requires migrate.sh schema version {n}, but this version supports up to {max}.` | 1 |
| No data to export | `Error: No iflow data found at ~/.claude/iflow/. Run setup.sh first.` | 1 |
| Python not available | `Error: Python 3 required for SQLite operations. Install Python or run: plugins/iflow/scripts/setup.sh` | 1 |
| Disk full | `Error: Disk full during import. Rolled back database changes. Files restored: {list}. Files NOT restored: {list}.` | 1 |

## Testing Strategy

Tests live in `scripts/test_migrate.py` using pytest + tmp_path fixtures:

1. **Export round-trip:** Create test DBs → export → extract → verify checksums match
2. **Import fresh:** Export → import into empty dir → verify all entries present
3. **Import merge:** Create overlapping state → import → verify no duplicates, no data loss
4. **Dry-run:** Import with --dry-run → verify zero filesystem changes
5. **Corrupt bundle:** Tamper with file after export → verify import rejects
6. **Session detection:** Mock pgrep → verify abort without --force
7. **ENTITY_DB_PATH:** Set override → verify export reads correct path
8. **Embedding mismatch:** Different provider in bundle vs dest → verify warning
9. **Post-import doctor:** Import → verify health checks run and report readable output
10. **Fresh machine embedding check:** Import into empty dir (no _metadata) → verify no mismatch warning
11. **UUID generation on merge:** Import with overlapping entities → verify new uuids generated, type_id dedup works
12. **Force overwrite:** Create existing markdown files → import with --force → verify files are overwritten with bundle contents
