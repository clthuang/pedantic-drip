# Design: iflow Migration Tool

## Prior Art Research

### Codebase Patterns
- **EntityDatabase.export_entities_json()** (database.py:1160-1240) — structured JSON envelope with `schema_version`, `exported_at`, entity array. No import counterpart exists. Reusable as reference for manifest structure.
- **doctor.sh** — Bash conventions: colored output helpers (`RED/GREEN/YELLOW/NC`), `die()/warn()/ok()/info()` functions, step headers `[N/M]`, `set -euo pipefail`, path detection via symlink resolution and `.git` walk-up.
- **setup-memory.sh** — Python invocation pattern: `PYTHONPATH="$PLUGIN_DIR/hooks/lib" "$VENV_PYTHON" -m module`. Uses `sqlite3` CLI for row counts.
- **release.sh** — Reads plugin.json version via `sed`/inline Python.
- **MarkdownImporter.import_all()** (importer.py:42-76) — idempotent import via source_hash dedup + upsert.
- **ENTITY_DB_PATH** env var used consistently in entity_server.py, workflow_state_server.py, ui/__init__.py.
- **~/.claude/iflow/projects.txt** exists at the global state path — must be included in export.
- **No existing export/import/backup tooling** in the codebase.

### External Research
- **sqlite3.Connection.backup(pages=-1)** captures point-in-time snapshot without blocking concurrent access. Preferred over file copy for WAL-mode databases.
- **ATTACH DATABASE** for merge is significantly faster than row-by-row iteration — runs SQL across attached databases in-process with no file I/O overhead.
- **Embedding vectors from different providers are incompatible** — cosine similarity drops from ~0.85 to ~0.65 when mixing providers. Must warn on mismatch and recommend backfill.
- **tarfile** module in Python stdlib handles .tar.gz creation/extraction natively.

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│              migrate.sh (Bash)               │
│  CLI parsing, UX, file ops, progress output  │
├─────────────────────────────────────────────┤
│  export()        │  import()       │ help() │
│  - session check │  - session check│ - usage│
│  - staging dir   │  - extract tar  │        │
│  - invoke Python │  - invoke Python│        │
│  - tar + cleanup │  - copy files   │        │
│                  │  - doctor check │        │
└────────┬─────────┴────────┬────────┴────────┘
         │                  │
         ▼                  ▼
┌─────────────────────────────────────────────┐
│           migrate_db.py (Python)             │
│  SQLite operations, manifest, verification   │
├─────────────────────────────────────────────┤
│  Subcommands (argparse):                     │
│  backup   - .backup() API + checksums        │
│  manifest - generate manifest.json           │
│  validate - verify checksums                 │
│  merge    - import with dedup                │
│  verify   - PRAGMA integrity_check + counts  │
│  info     - read manifest metadata           │
└─────────────────────────────────────────────┘
```

### Design Decision: migrate_db.py as CLI with subcommands

**Decision:** migrate_db.py exposes argparse subcommands (`backup`, `manifest`, `validate`, `merge`, `verify`, `info`) rather than being a monolithic script called with the same export/import args as migrate.sh.

**Rationale:**
- Each SQLite operation is independently testable
- migrate.sh orchestrates the workflow; migrate_db.py provides atomic operations
- Enables future reuse (e.g., `migrate_db.py verify` standalone for health checks)
- Aligns with established pattern: Bash orchestrates, Python computes

**Alternative considered:** Single `migrate_db.py export/import` matching migrate.sh 1:1. Rejected because it duplicates orchestration logic and makes individual operations untestable.

### Design Decision: ATTACH DATABASE for merge

**Decision:** Use `ATTACH DATABASE` for merge operations instead of row-by-row SELECT + INSERT.

**Rationale:**
- Cleaner SQL — dedup via WHERE NOT IN subquery, no Python-side bookkeeping
- Handles all column mapping explicitly (no positional index fragility)
- Single statement per table = natural transaction boundary

**Trade-off acknowledged:** For typical scale (<500 entries), row-by-row would also be fast enough. ATTACH is chosen for SQL clarity and elimination of Python iteration bugs, not raw performance. Dry-run uses COUNT queries (no actual inserts).

**Spec pseudocode shows row-by-row approach** — design upgrades to ATTACH while preserving the same dedup semantics (source_hash for memory, type_id for entities).

### Design Decision: projects.txt inclusion

**Decision:** Include `~/.claude/iflow/projects.txt` in the export bundle.

**Rationale:** Codebase exploration revealed this file exists in the global state directory. It tracks registered projects. Omitting it would lose project registration state on import.

**Impact:** Add to Data Inventory as a fourth store. Bundle gains `projects.txt` at top level.

**Spec discrepancy:** The spec's Data Inventory and bundle format do not include projects.txt. Spec must be updated before implementation to add projects.txt as a fourth data store.

## Components

### C1: migrate.sh

**Responsibilities:** CLI parsing, UX shell, file operations, orchestration.

**Dependencies:** Bash 4+, tar, Python 3.8+ (via C2)

**Key behaviors:**
- Parses subcommand + flags using `case` statements
- Resolves Python path (dev workspace → plugin cache → system python3)
- Creates/cleans staging directory in `$TMPDIR`
- Delegates all SQLite ops to migrate_db.py
- Copies markdown files and projects.txt
- Creates/extracts tar.gz bundle
- Prints progress to stderr with optional color (respects `NO_COLOR`)
- Session detection via `pgrep -f` with `.db-wal` fallback

### C2: migrate_db.py

**Responsibilities:** All SQLite operations, manifest I/O, verification.

**Dependencies:** Python 3.8+ stdlib only (sqlite3, json, hashlib, argparse, platform, uuid, pathlib, sys)

**Key behaviors:**
- `backup`: sqlite3.Connection.backup(pages=-1) + SHA-256 + entry count
- `manifest`: generate/read manifest.json with checksums and metadata
- `validate`: verify bundle checksums against manifest
- `merge`: ATTACH-based merge with dedup (separate logic for memory vs entities)
- `verify`: PRAGMA integrity_check + count comparison
- `info`: read manifest for dry-run display and embedding mismatch detection

### C3: Bundle (data artifact)

**Structure:**
```
iflow-export-YYYYMMDD-HHMMSS/
  manifest.json
  projects.txt              # project registry (if exists)
  memory/
    memory.db               # SQLite backup
    *.md                    # category markdown files
  entities/
    entities.db             # SQLite backup
```

## Technical Decisions

### TD-1: Staging directory lifecycle

Export creates a temp staging dir (`mktemp -d`), writes all files there, generates manifest, creates tar.gz from it, then removes staging dir. This ensures atomic bundle creation — partial failures leave no artifacts.

### TD-2: Entity merge via ATTACH + Python UUID generation

The merge uses a two-phase approach: ATTACH for the SQL query, Python for UUID generation.

**Phase 1: Identify new entities (Python)**

```python
def merge_entities_db(src_path, dst_path, dry_run=False):
    dst = sqlite3.connect(dst_path)
    dst.execute(f"ATTACH DATABASE '{src_path}' AS src")

    # FK enforcement OFF during merge — we validate parent_type_id existence
    # via the WHERE clause instead. This avoids insertion-order issues where
    # a child entity might be inserted before its parent within the same batch.
    dst.execute("PRAGMA foreign_keys = OFF")

    # Count for dry-run
    new_type_ids = dst.execute("""
        SELECT src.type_id FROM src.entities src
        WHERE src.type_id NOT IN (SELECT type_id FROM main.entities)
    """).fetchall()
    skip_count = dst.execute("SELECT count(*) FROM src.entities").fetchone()[0] - len(new_type_ids)

    if dry_run:
        return {"added": len(new_type_ids), "skipped": skip_count}

    # Phase 2: Insert with Python-generated UUIDs
    for (type_id,) in new_type_ids:
        row = dst.execute("SELECT * FROM src.entities WHERE type_id = ?", (type_id,)).fetchone()
        cols = [desc[0] for desc in dst.execute("SELECT * FROM src.entities LIMIT 0").description]
        uuid_idx = cols.index("uuid")
        parent_uuid_idx = cols.index("parent_uuid")

        row = list(row)
        row[uuid_idx] = str(uuid.uuid4())   # New UUID (Python stdlib)
        row[parent_uuid_idx] = None          # Cleared — reconstructed below

        placeholders = ",".join("?" * len(row))
        col_names = ",".join(f'"{c}"' for c in cols)
        dst.execute(f"INSERT INTO main.entities ({col_names}) VALUES ({placeholders})", row)

    # Phase 3: Merge workflow_phases for newly inserted entities
    dst.execute("""
        INSERT OR IGNORE INTO main.workflow_phases (type_id, workflow_phase, kanban_column,
            last_completed_phase, mode, completed_phases, phase_iterations, phase_reviewer_notes)
        SELECT wp.type_id, wp.workflow_phase, wp.kanban_column,
            wp.last_completed_phase, wp.mode, wp.completed_phases,
            wp.phase_iterations, wp.phase_reviewer_notes
        FROM src.workflow_phases wp
        WHERE wp.type_id NOT IN (SELECT type_id FROM main.workflow_phases)
    """)

    # Phase 4: Reconstruct parent_uuid for imported entities
    # server_helpers.py uses parent_uuid for UI tree building, so we must populate it.
    dst.execute("""
        UPDATE main.entities
        SET parent_uuid = (
            SELECT uuid FROM main.entities AS parent
            WHERE parent.type_id = main.entities.parent_type_id
        )
        WHERE parent_uuid IS NULL
          AND parent_type_id IS NOT NULL
    """)

    # Phase 5: Rebuild FTS5 index for imported entities
    try:
        dst.execute("INSERT INTO entities_fts(entities_fts) VALUES('rebuild')")
    except sqlite3.OperationalError:
        pass  # FTS5 may not be configured; non-fatal

    dst.commit()
    dst.execute("DETACH DATABASE src")
    return {"added": len(new_type_ids), "skipped": skip_count}
```

**Key design choices:**
- **Python UUIDs** (not SQL randomblob): More reliable across SQLite versions, uses stdlib `uuid.uuid4()`
- **FK OFF during merge**: Avoids insertion-order issues when child entities appear before parents in the result set. Validity is enforced by the WHERE clause (only type_ids from source that don't exist in destination).
- **parent_uuid reconstruction**: Phase 4 UPDATE populates parent_uuid by looking up the new UUID via parent_type_id. This preserves UI tree hierarchy (server_helpers.py uses parent_uuid for tree building).
- **FTS5 rebuild**: Phase 5 rebuilds entities_fts so imported entities appear in search.

### TD-3: Memory merge via ATTACH + source_hash dedup

```python
def merge_memory_db(src_path, dst_path, dry_run=False):
    dst = sqlite3.connect(dst_path)
    dst.execute(f"ATTACH DATABASE '{src_path}' AS src")

    # Count for reporting
    add_count = dst.execute("""
        SELECT count(*) FROM src.entries
        WHERE source_hash NOT IN (SELECT source_hash FROM main.entries)
    """).fetchone()[0]
    skip_count = dst.execute("SELECT count(*) FROM src.entries").fetchone()[0] - add_count

    if dry_run:
        return {"added": add_count, "skipped": skip_count}

    # INSERT OR IGNORE: source_hash dedup is the primary filter (WHERE clause).
    # OR IGNORE handles the rare case where id (PK) collides but source_hash differs.
    dst.execute("""
        INSERT OR IGNORE INTO main.entries (id, name, description, reasoning, category,
            keywords, source, source_project, "references", observation_count, confidence,
            recall_count, last_recalled_at, embedding, created_at, updated_at,
            source_hash, created_timestamp_utc)
        SELECT src.id, src.name, src.description, src.reasoning, src.category,
            src.keywords, src.source, src.source_project, src."references",
            src.observation_count, src.confidence, src.recall_count,
            src.last_recalled_at, src.embedding, src.created_at, src.updated_at,
            src.source_hash, src.created_timestamp_utc
        FROM src.entries src
        WHERE src.source_hash NOT IN (SELECT source_hash FROM main.entries)
    """)

    # Rebuild FTS5 index for imported entries
    if add_count > 0:
        try:
            dst.execute("INSERT INTO entries_fts(entries_fts) VALUES('rebuild')")
        except sqlite3.OperationalError:
            pass  # FTS5 may not be configured; non-fatal

    dst.commit()
    dst.execute("DETACH DATABASE src")
    return {"added": add_count, "skipped": skip_count}
```

**Key design choices:**
- **INSERT OR IGNORE**: Handles rare PK collision (different content but same id) gracefully — skips the row instead of aborting the entire merge.
- **Dry-run via COUNT**: Uses the same WHERE clause in a SELECT count(*) to preview results without modifying data.
- **FTS5 rebuild**: Integrated into the merge function (not a separate post-step).

### TD-4: Manifest metadata sourcing

| Field | Source |
|-------|--------|
| `schema_version` | Hardcoded `SUPPORTED_SCHEMA_VERSION = 1` in migrate_db.py |
| `plugin_version` | Read from plugin.json via Glob: `~/.claude/plugins/cache/*/iflow*/*/plugin.json`, fallback `plugins/iflow/plugin.json` |
| `export_timestamp` | `datetime.utcnow().isoformat() + 'Z'` |
| `source_platform` | `f"{sys.platform}-{platform.machine()}"` → e.g. `darwin-arm64` |
| `python_version` | `platform.python_version()` |
| `embedding_provider` | `SELECT value FROM _metadata WHERE key='embedding_provider'` from memory.db |
| `embedding_model` | `SELECT value FROM _metadata WHERE key='embedding_model'` from memory.db |
| File checksums | `hashlib.sha256(file_bytes).hexdigest()` |
| Entry counts | `SELECT count(*) FROM entries/entities/workflow_phases` |

### TD-5: Session detection strategy

```bash
check_active_session() {
  # Primary: check for running MCP server processes
  if pgrep -f 'memory_server|entity_server|workflow_state_server' > /dev/null 2>&1; then
    return 0  # active
  fi
  # Fallback: check WAL file sizes (indicates uncommitted data)
  local wal_files=(
    "$MEMORY_DB_PATH-wal"
    "$ENTITY_DB_PATH-wal"
  )
  for wal in "${wal_files[@]}"; do
    if [ -f "$wal" ] && [ "$(stat -f%z "$wal" 2>/dev/null || stat -c%s "$wal" 2>/dev/null)" -gt 0 ]; then
      return 0  # active (WAL has uncommitted data)
    fi
  done
  return 1  # no active session
}
```

### TD-6: Doctor check resolution

```bash
run_doctor_check() {
  # Try dev workspace first
  local doctor="$(dirname "$0")/../plugins/iflow/scripts/doctor.sh"
  if [ ! -x "$doctor" ]; then
    # Try plugin cache
    doctor="$(ls ~/.claude/plugins/cache/*/iflow*/*/scripts/doctor.sh 2>/dev/null | head -1)"
  fi
  if [ -x "$doctor" ]; then
    "$doctor" --quiet || warn "doctor.sh reported issues (non-fatal)"
  else
    # Inline fallback
    verify_db_readable "$MEMORY_DB_PATH" "entries"
    verify_db_readable "$ENTITY_DB_PATH" "entities"
  fi
}
```

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| ATTACH merge SQL wrong column order | Silent data corruption | Use explicit column lists (not SELECT *); test with actual schemas |
| parent_uuid reconstruction misses orphans | Entity display issues in UI tree | Phase 4 UPDATE handles all NULL parent_uuid rows; verified server_helpers.py uses parent_uuid |
| FTS5 index inconsistency after merge | Search misses new entries | Both merge functions rebuild FTS5 (entries_fts and entities_fts) |
| Memory id PK collision | Row silently skipped | INSERT OR IGNORE; source_hash dedup catches most cases; PK collision = same or near-identical entry |
| Large embedding BLOBs slow merge | Export/import takes minutes | Acceptable for typical usage (<500 entries) |
| projects.txt format changes | Import breaks project list | Simple text file (one path per line); low risk |
| WAL checkpoint during export | Backup captures partial state | .backup() API handles this atomically |
| Spec does not include projects.txt | Implementation gap | Flagged for spec update before implementation |

## Interfaces

### C1 → C2: migrate_db.py CLI

```
# Backup a database
python migrate_db.py backup <src-db> <dst-db> --table <main-table>
  stdout: JSON {"sha256": "...", "size_bytes": N, "entry_count": N}
  exit: 0=success, 1=error

# Generate manifest
python migrate_db.py manifest <staging-dir> --plugin-version <ver>
  stdout: (writes manifest.json to staging-dir)
  exit: 0=success, 1=error

# Validate manifest checksums
python migrate_db.py validate <bundle-dir>
  stdout: JSON {"valid": true/false, "errors": [...]}
  exit: 0=valid, 1=invalid

# Merge databases (memory)
python migrate_db.py merge-memory <src-db> <dst-db> [--dry-run]
  stdout: JSON {"added": N, "skipped": N}
  exit: 0=success, 1=error

# Merge databases (entities + workflow_phases)
python migrate_db.py merge-entities <src-db> <dst-db> [--dry-run]
  stdout: JSON {"added": N, "skipped": N}
  exit: 0=success, 1=error

# Verify database integrity
python migrate_db.py verify <db-path> --expected-count N --table <name>
  stdout: JSON {"ok": true/false, "actual_count": N, "integrity": "ok/..."}
  exit: 0=pass, 1=fail

# Read manifest info (for dry-run and embedding check)
python migrate_db.py info <manifest-path>
  stdout: JSON (full manifest content)
  exit: 0=success, 1=error

# Detect embedding mismatch
python migrate_db.py check-embeddings <manifest-path> <dst-memory-db>
  stdout: JSON {"mismatch": true/false, "warning": "..." or null}
  exit: 0 always (informational)
```

All subcommands output JSON to stdout. Errors go to stderr. This enables migrate.sh to parse results with simple `jq`-free JSON extraction (`python3 -c "import json,sys; ..."` or grep for specific fields).

### C1 → C3: Bundle format

**Export produces:** `iflow-export-YYYYMMDD-HHMMSS.tar.gz`
- Created via `tar -czf` from staging directory
- Contains manifest.json as first entry for fast validation

**Import consumes:** Same format
- Extracted via `tar -xzf` to temp directory
- manifest.json read first for validation before any state changes

### migrate.sh internal flow: export

```bash
export_flow() {
  step 1/6 "Checking for active sessions"
  check_active_session  # exits 2 if active and no --force

  step 2/6 "Creating staging directory"
  STAGING=$(mktemp -d)
  mkdir -p "$STAGING/memory" "$STAGING/entities"

  step 3/6 "Backing up semantic memory database"
  MEMORY_RESULT=$("$PYTHON" "$MIGRATE_DB" backup "$MEMORY_DB" "$STAGING/memory/memory.db" --table entries)

  step 4/6 "Backing up entity registry database"
  ENTITY_RESULT=$("$PYTHON" "$MIGRATE_DB" backup "$ENTITY_DB" "$STAGING/entities/entities.db" --table entities)

  step 5/6 "Copying memory files"
  cp "$MEMORY_DIR"/*.md "$STAGING/memory/" 2>/dev/null || true
  [ -f "$IFLOW_DIR/projects.txt" ] && cp "$IFLOW_DIR/projects.txt" "$STAGING/"

  step 6/6 "Creating bundle"
  "$PYTHON" "$MIGRATE_DB" manifest "$STAGING" --plugin-version "$PLUGIN_VERSION"
  tar -czf "$OUTPUT_PATH" -C "$(dirname "$STAGING")" "$(basename "$STAGING")"
  rm -rf "$STAGING"

  # Print summary
  print_export_summary "$OUTPUT_PATH" "$MEMORY_RESULT" "$ENTITY_RESULT"
}
```

### migrate.sh internal flow: import

```bash
import_flow() {
  step 1/8 "Validating bundle"
  BUNDLE_DIR=$(mktemp -d)
  tar -xzf "$BUNDLE_PATH" -C "$BUNDLE_DIR"
  EXTRACTED="$BUNDLE_DIR/$(ls "$BUNDLE_DIR")"  # single top-level dir
  VALIDATE=$("$PYTHON" "$MIGRATE_DB" validate "$EXTRACTED")
  # Check valid field, exit 3 if invalid

  step 2/8 "Checking for active sessions"
  check_active_session  # exits 2 if active and no --force

  step 3/8 "Checking embedding compatibility"
  EMBED_CHECK=$("$PYTHON" "$MIGRATE_DB" check-embeddings "$EXTRACTED/manifest.json" "$MEMORY_DB")
  # Print warning if mismatch

  step 4/8 "Creating directory structure"
  mkdir -p "$MEMORY_DIR" "$ENTITY_DIR"

  step 5/8 "Restoring semantic memory"
  if [ -f "$MEMORY_DB" ]; then
    PRE_MEM_COUNT=$("$PYTHON" "$MIGRATE_DB" verify "$MEMORY_DB" --expected-count 0 --table entries | extract_actual_count)
    MEM_MERGE=$("$PYTHON" "$MIGRATE_DB" merge-memory "$EXTRACTED/memory/memory.db" "$MEMORY_DB" $DRY_RUN_FLAG)
    EXPECTED_MEMORY=$((PRE_MEM_COUNT + $(echo "$MEM_MERGE" | extract_added)))
  else
    cp "$EXTRACTED/memory/memory.db" "$MEMORY_DB"
    EXPECTED_MEMORY=$(manifest_entry_count "$EXTRACTED/manifest.json" "memory/memory.db")
  fi

  step 6/8 "Restoring entity registry"
  if [ -f "$ENTITY_DB" ]; then
    PRE_ENT_COUNT=$("$PYTHON" "$MIGRATE_DB" verify "$ENTITY_DB" --expected-count 0 --table entities | extract_actual_count)
    ENT_MERGE=$("$PYTHON" "$MIGRATE_DB" merge-entities "$EXTRACTED/entities/entities.db" "$ENTITY_DB" $DRY_RUN_FLAG)
    EXPECTED_ENTITIES=$((PRE_ENT_COUNT + $(echo "$ENT_MERGE" | extract_added)))
  else
    cp "$EXTRACTED/entities/entities.db" "$ENTITY_DB"
    EXPECTED_ENTITIES=$(manifest_entity_count "$EXTRACTED/manifest.json")
  fi

  step 7/8 "Copying files"
  copy_markdown_files "$EXTRACTED/memory/" "$MEMORY_DIR"
  [ -f "$EXTRACTED/projects.txt" ] && copy_file "$EXTRACTED/projects.txt" "$IFLOW_DIR/projects.txt"

  step 8/8 "Verifying integrity"
  "$PYTHON" "$MIGRATE_DB" verify "$MEMORY_DB" --expected-count "$EXPECTED_MEMORY" --table entries
  "$PYTHON" "$MIGRATE_DB" verify "$ENTITY_DB" --expected-count "$EXPECTED_ENTITIES" --table entities
  run_doctor_check

  rm -rf "$BUNDLE_DIR"
  print_import_summary
}
```

### Error handling contract

- migrate_db.py communicates errors via stderr + non-zero exit code
- migrate.sh captures exit codes and translates to user-facing messages (from Error Messages table in spec)
- All SQLite operations in migrate_db.py use explicit transactions (BEGIN/COMMIT with rollback on exception)
- File operations in migrate.sh track progress for partial-failure reporting

### Expected count computation for verification

After import, the verify step needs expected counts:
- **Fresh import** (no pre-existing DB): expected = manifest entry_count / entity_count
- **Merge import**: expected = pre_merge_count + merge_result["added"]

The import flow captures pre-merge count before calling merge, then adds the "added" value from the merge JSON output. Both values are passed to the verify subcommand.
