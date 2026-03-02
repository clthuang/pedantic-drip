# Design: Bidirectional UUID Sync Between Files and DB

## Prior Art Research

### Codebase Patterns
- **frontmatter.py** (feature 002): `read_frontmatter` (never raises, returns None), `write_frontmatter` (atomic temp+rename, merge semantics, raises FrontmatterUUIDMismatch/ValueError), `build_header` (validates), `validate_header` (collects all errors)
- **frontmatter_inject.py** (feature 002): CLI injection template — `_parse_feature_type_id`, `_extract_project_id`, `ARTIFACT_BASENAME_MAP`, `ARTIFACT_PHASE_MAP` are importable helpers
- **database.py** (feature 001): `get_entity` returns dict|None, `update_entity` accepts UUID via `_resolve_identifier` (line 553). `metadata` column is JSON TEXT — requires `json.loads()` to parse
- **backfill.py**: `run_backfill` with `backfill_complete` guard at line 44. Glob-based directory scanning pattern
- **server_helpers.py**: Never-raises wrapper pattern — return error strings instead of propagating exceptions
- **Test pattern**: `tmp_path` fixture, `EntityDatabase(':memory:')`, class-grouped tests, `_write_file` helper

### External Research
- No existing bidirectional markdown↔SQLite tool exists. MarkdownDB and markdown-to-sqlite are one-directional (file→DB index only)
- Atomic write best practice: temp file in same directory + `os.rename` (already implemented in `write_frontmatter`)
- argparse subcommand pattern: `add_subparsers(required=True)` + `set_defaults(func=handler)` + `args.func(args)` dispatch
- Dataclass serialization: `dataclasses.asdict()` + `json.dumps()` for CLI JSON output

## Architecture Overview

```
frontmatter_sync.py (new)          frontmatter_sync_cli.py (new)
+---------------------------------+ +---------------------------+
| Dataclasses:                    | | argparse CLI              |
|   DriftReport, FieldMismatch,   | | 5 subcommands:            |
|   StampResult, IngestResult     | |   drift, stamp, ingest,   |
|                                 | |   backfill, scan          |
| Core functions:                 | |                           |
|   detect_drift()                | | JSON stdout, stderr logs  |
|   stamp_header()                | +---------------------------+
|   ingest_header()               |         |
|   backfill_headers()            |         | imports
|   scan_all()                    |<--------+
|                                 |
| Internal helpers:               |
|   _derive_optional_fields()     |
|   _derive_feature_directory()   |
|   _extract_project_id_from_*()  |
+---------------------------------+
      |               |
      | imports        | imports
      v               v
frontmatter.py    database.py       frontmatter_inject.py
(feature 002)     (feature 001)     (feature 002)
                                    - _parse_feature_type_id
                                    - ARTIFACT_BASENAME_MAP
                                    - ARTIFACT_PHASE_MAP

backfill.py (modified)
+-----------------------------------+
| run_backfill(db, root,            |
|   header_aware=False)             |
|   1. if header_aware:             |
|      backfill_headers(db, root)   |
|   2. if backfill_complete: return |
|   3. existing scan logic...       |
+-----------------------------------+
```

### Data Flow

```
DB→File (stamp):     DB.get_entity → build_header → write_frontmatter → file
File→DB (ingest):    read_frontmatter → DB.update_entity(artifact_path only)
Drift detection:     read_frontmatter + DB.get_entity → compare → DriftReport
Bulk backfill:       DB.list_entities("feature") → derive dirs → stamp each file
Scan all:            DB.list_entities("feature") → derive dirs → detect_drift each
```

## Components

### C1: Dataclasses (`frontmatter_sync.py`, lines 1-40)

Four stdlib `@dataclass` types defining the result contracts:

| Dataclass | Fields | Purpose |
|-----------|--------|---------|
| `FieldMismatch` | `field`, `file_value`, `db_value` | Single-field comparison result |
| `DriftReport` | `filepath`, `type_id`, `status`, `file_fields`, `db_fields`, `mismatches` | Full drift assessment |
| `StampResult` | `filepath`, `action`, `message` | DB→file stamp outcome |
| `IngestResult` | `filepath`, `action`, `message` | File→DB ingest outcome |

### C2: `detect_drift()` (~40 lines)

Stateless comparison function. No side effects — reads file and DB, returns report.

**Decision: Field mapping as constants.** Define `COMPARABLE_FIELD_MAP` as a module-level dict mapping file field names to DB column names:
```python
COMPARABLE_FIELD_MAP = {
    "entity_uuid": "uuid",
    "entity_type_id": "type_id",
}
```
This makes the comparison set explicit and extensible without changing function logic.

### C3: `stamp_header()` (~50 lines)

DB-authoritative write path. Follows the 7-step flow from spec R12.

**Decision: `_derive_optional_fields` internal helper.** Extract R13 derivation logic into a single internal function that takes the entity record dict and returns a dict of optional header fields. This isolates the `metadata` JSON parsing, `_parse_feature_type_id` import, and `project_id` dual-source logic in one testable unit.

### C4: `ingest_header()` (~25 lines)

File-authoritative path. Minimal: read frontmatter, look up entity by UUID, update `artifact_path`. The function uses `os.path.abspath(filepath)` to normalize the path before storing.

### C5: `backfill_headers()` (~40 lines)

Bulk stamp across all feature entities.

**Decision: `_derive_feature_directory` internal helper.** Encapsulates the 4-step fallback chain from spec R20 step 2 (isdir → isfile/dirname → construct → skip). Returns `str | None` — None means skip.

### C6: `scan_all()` (~25 lines)

Bulk drift detection. Mirrors `backfill_headers` structure but calls `detect_drift` instead of `stamp_header`.

### C7: `backfill.py` modification (~5 lines)

Add `header_aware: bool = False` parameter to `run_backfill`. Insert header stamping call BEFORE the `backfill_complete` guard.

### C8: `frontmatter_sync_cli.py` (~100 lines)

argparse CLI with 5 subcommands. Each handler instantiates `EntityDatabase`, calls the sync function, serializes result via `dataclasses.asdict()` + `json.dumps()`, and prints to stdout.

## Technical Decisions

### TD-1: Import helpers from `frontmatter_inject` rather than duplicating

**Decision:** Import `_parse_feature_type_id`, `ARTIFACT_BASENAME_MAP`, `ARTIFACT_PHASE_MAP` directly from `entity_registry.frontmatter_inject`.

**Rationale:** These are stable, tested functions. Duplicating creates drift risk. The underscore prefix is a convention, not an access barrier within the same package. No changes to `frontmatter_inject.py` required.

**Risk:** If `frontmatter_inject.py` is later refactored, imports break. Mitigated: both modules are in the same package and maintained together.

### TD-2: `metadata` field parsing for project_id

**Decision:** In `_derive_optional_fields`, parse entity `metadata` (JSON TEXT) via `json.loads()`. Handle None metadata and missing/empty `project_id` key gracefully.

**Implementation:**
```python
def _derive_optional_fields(entity: dict, artifact_type: str) -> dict:
    kwargs = {}
    entity_type, _, entity_id_part = entity["type_id"].partition(":")

    # feature_id + feature_slug (feature entities only)
    if entity_type == "feature":
        feat_id, feat_slug = _parse_feature_type_id(entity["type_id"])
        if feat_id:
            kwargs["feature_id"] = feat_id
        if feat_slug is not None:
            kwargs["feature_slug"] = feat_slug

    # project_id: metadata first, then parent_type_id fallback
    project_id = None
    if entity.get("metadata"):
        try:
            meta = json.loads(entity["metadata"])
            project_id = meta.get("project_id") or None
        except (json.JSONDecodeError, TypeError):
            pass
    if project_id is None and entity.get("parent_type_id"):
        p_type, _, p_id = entity["parent_type_id"].partition(":")
        if p_type == "project":
            project_id = p_id
    if project_id:
        kwargs["project_id"] = project_id

    # phase
    phase = ARTIFACT_PHASE_MAP.get(artifact_type)
    if phase:
        kwargs["phase"] = phase

    return kwargs
```

### TD-3: `_derive_feature_directory` 4-step fallback

**Decision:** Return `str | None` to allow callers to skip entities with no resolvable directory.

**Implementation:**
```python
def _derive_feature_directory(entity: dict, artifacts_root: str) -> str | None:
    ap = entity.get("artifact_path")
    if ap:
        if os.path.isdir(ap):
            return ap
        if os.path.isfile(ap):
            return os.path.dirname(ap)
    # Construct from entity_id (fallback step c)
    # Assumption: entity_id matches directory basename (e.g., "003-bidirectional-uuid-sync-betwee").
    # This holds for entities registered by backfill._scan_features, which derives entity_id
    # from .meta.json's id+slug fields matching the directory convention.
    # For entities registered via other means (MCP tools, manual), artifact_path (steps a/b)
    # is the primary resolution path; this construction is only a fallback.
    candidate = os.path.join(artifacts_root, "features", entity["entity_id"])
    if os.path.isdir(candidate):
        return candidate
    return None
```

### TD-4: Error handling strategy — never raise, always return

**Decision:** All public functions catch exceptions internally and return error-action results. `FrontmatterUUIDMismatch` and `ValueError` in `stamp_header` are caught explicitly (returns `action="error"`); other exceptions (sqlite3.Error) are caught with broad `except Exception` and returned as error results. Note: `write_frontmatter` raises `ValueError` (not `OSError`) for file-not-found — all frontmatter error paths produce `ValueError` or its subclass `FrontmatterUUIDMismatch`.

**Rationale:** Matches server_helpers.py never-raises pattern. Callers (CLI, backfill loop) process results uniformly without try/except.

### TD-5: CLI DB lifecycle

**Decision:** CLI handlers follow `frontmatter_inject.py` pattern: `ENTITY_DB_PATH` env var → fallback path. DB opened once per subcommand invocation, closed in `finally` block. Each subcommand handler wraps `_open_db()` in a try/except to catch `sqlite3.OperationalError` and other construction failures, printing a JSON error to stdout and exiting with code 1.

**Implementation:**
```python
def _open_db() -> EntityDatabase:
    db_path = os.environ.get(
        "ENTITY_DB_PATH",
        os.path.expanduser("~/.claude/iflow/entities/entities.db"),
    )
    return EntityDatabase(db_path)

def _run_handler(func):
    """Shared wrapper: opens DB, runs handler, closes DB, catches fatal errors.
    `func` is a closure over parsed argparse args, accepting only `db`."""
    db = None
    try:
        db = _open_db()
        func(db)
    except Exception as exc:
        print(json.dumps({"error": f"Fatal: {exc}"}, indent=2))
        sys.exit(1)
    finally:
        if db is not None:
            db.close()
```

### TD-6: CLI JSON serialization

**Decision:** Use `dataclasses.asdict()` + `json.dumps(indent=2)` for all output. For lists of results, serialize as JSON array.

**Rationale:** `dataclasses.asdict` handles nested dataclasses (e.g., `DriftReport.mismatches` contains `FieldMismatch` objects). No external serialization library needed.

### TD-7: `backfill.py` modification placement

**Decision:** Insert header stamping as the FIRST action in `run_backfill`, before the `backfill_complete` guard check.

**Modified structure:**
```python
def run_backfill(db, artifacts_root, header_aware=False):
    # Step 1: Header stamping (independent of backfill_complete)
    if header_aware:
        from entity_registry.frontmatter_sync import backfill_headers
        backfill_headers(db, artifacts_root)

    # Step 2: Existing entity registration (guarded by backfill_complete)
    if db.get_metadata("backfill_complete") == "1":
        return
    # ... existing scan logic ...
```

**Rationale:** Lazy import of `backfill_headers` avoids circular imports and keeps the dependency optional — `backfill.py` works without `frontmatter_sync.py` present.

## Interfaces

### Public API: `frontmatter_sync.py`

```python
@dataclass
class FieldMismatch:
    field: str
    file_value: str | None
    db_value: str | None

@dataclass
class DriftReport:
    filepath: str
    type_id: str | None
    status: str   # "in_sync" | "file_only" | "db_only" | "diverged" | "no_header" | "error"
    file_fields: dict | None
    db_fields: dict | None
    mismatches: list[FieldMismatch]

@dataclass
class StampResult:
    filepath: str
    action: str   # "created" | "updated" | "skipped" | "error"
    message: str

@dataclass
class IngestResult:
    filepath: str
    action: str   # "updated" | "skipped" | "error"
    message: str
```

#### `detect_drift(db, filepath, type_id=None) -> DriftReport`

```
Input:  db (EntityDatabase), filepath (str), type_id (str | None)
Output: DriftReport

Flow:
  1. header = read_frontmatter(filepath)
  2. Determine lookup_key:
     a. If type_id is provided → lookup_key = type_id
     b. Else if header is not None:
          uuid_key = header.get("entity_uuid")
          If uuid_key is None → return no_header (header has no entity_uuid, no type_id — untracked)
          lookup_key = uuid_key
     c. Else → return no_header (no header, no type_id)
  3. entity = db.get_entity(lookup_key)
  4. If header and not entity → return file_only
  5. If not header and entity → return db_only(type_id=entity["type_id"])
  6. If not header and not entity → return no_header (should not happen after step 2, but defensive)
  7. Compare COMPARABLE_FIELD_MAP fields:
     - entity_uuid: case-insensitive (.lower() on both sides, per UUID convention)
     - entity_type_id: case-sensitive (structured identifiers)
     Note: When type_id is provided and the file header contains a different
     entity_uuid than the DB entity's uuid, this naturally produces a
     FieldMismatch on entity_uuid → returned as "diverged". This correctly
     flags the file as stamped for a different entity than expected.
  8. If mismatches → return diverged with FieldMismatch list
  9. Else → return in_sync

Error: If db.get_entity raises (sqlite3.OperationalError for broken connection
       or locked DB) → catch, return DriftReport with status="error" (defensive)
```

#### `stamp_header(db, filepath, type_id, artifact_type) -> StampResult`

```
Input:  db (EntityDatabase), filepath (str), type_id (str), artifact_type (str)
Output: StampResult

Precondition: filepath must exist on disk. Caller is responsible for ensuring the
file exists before calling stamp_header (backfill_headers checks via os.path.isfile).

Flow (spec R12):
  1. entity = db.get_entity(type_id)
     If None → return error("Entity not found")
  2. Extract: uuid=entity["uuid"], type_id=entity["type_id"], created_at=entity["created_at"]
  3. optional = _derive_optional_fields(entity, artifact_type)
  4-7. Single try/except block covering build_header through write_frontmatter:
     try:
       4. header = build_header(uuid, type_id, artifact_type, created_at, **optional)
          (can raise ValueError on invalid fields)
       5. existing = read_frontmatter(filepath)
       6. If existing and existing.get("entity_uuid")
            and existing["entity_uuid"].lower() != uuid.lower()
          → return error("UUID mismatch")
          (If existing header has no entity_uuid, treat as create — merge will add it)
       7. write_frontmatter(filepath, header)
     except FrontmatterUUIDMismatch → return error("UUID mismatch: ...")
     except ValueError → return error("Stamp failed: {details}")
     Note: write_frontmatter raises ValueError (not OSError) for file-not-found.
     The precondition above prevents this, but the catch is defensive.
  8. Return created (if existing was None) or updated (if existing was not None)
```

#### `ingest_header(db, filepath) -> IngestResult`

```
Input:  db (EntityDatabase), filepath (str)
Output: IngestResult

Flow:
  1. header = read_frontmatter(filepath)
     If None → return skipped("No frontmatter")
  2. uuid = header.get("entity_uuid")
     If not uuid → return skipped("No entity_uuid in header")
  3. entity = db.get_entity(uuid)
     If None → return error("Entity not found in DB")
  4. abs_path = os.path.abspath(filepath)
  5. db.update_entity(uuid, artifact_path=abs_path)
     Catch ValueError → return error("Entity disappeared: {uuid}")
     Note: This catch is a defensive race-condition guard. Step 3 confirmed the
     entity exists, but a concurrent process could delete it between step 3 and
     step 5. The distinct error message distinguishes this from step 3's "not found".
  6. Return updated("artifact_path set to {abs_path}")
```

#### `backfill_headers(db, artifacts_root) -> list[StampResult]`

```
Input:  db (EntityDatabase), artifacts_root (str)
Output: list[StampResult]

Flow:
  1. results = []
  2. features = db.list_entities(entity_type="feature")
  3. For each feature entity:
     a. dir = _derive_feature_directory(entity, artifacts_root)
     b. If dir is None → results.append(StampResult(skipped, "No directory"))
        continue
     c. For each basename in ARTIFACT_BASENAME_MAP:
        filepath = os.path.join(dir, basename)
        If os.path.isfile(filepath):
          artifact_type = ARTIFACT_BASENAME_MAP[basename]
          result = stamp_header(db, filepath, entity["type_id"], artifact_type)
          results.append(result)
  4. Return results
```

#### `scan_all(db, artifacts_root) -> list[DriftReport]`

```
Input:  db (EntityDatabase), artifacts_root (str)
Output: list[DriftReport]

Flow: Same as backfill_headers but calls detect_drift(db, filepath, entity["type_id"])
     instead of stamp_header for each file.
     Note: Since scan_all always passes entity["type_id"] to detect_drift, the
     "no_header" status is not possible in results. Files without frontmatter
     return "db_only" instead.
```

### Modified API: `backfill.py`

```python
def run_backfill(db: EntityDatabase, artifacts_root: str, header_aware: bool = False) -> None:
    # NEW: header stamping before guard
    if header_aware:
        from entity_registry.frontmatter_sync import backfill_headers
        backfill_headers(db, artifacts_root)

    # EXISTING: guard + entity registration
    if db.get_metadata("backfill_complete") == "1":
        return
    # ... rest unchanged ...
```

### CLI API: `frontmatter_sync_cli.py`

```
Usage: python frontmatter_sync_cli.py <subcommand> [args]

Subcommands:
  drift <filepath> <type_id>                 → JSON DriftReport to stdout
  stamp <filepath> <type_id> <artifact_type> → JSON StampResult to stdout
  ingest <filepath>                          → JSON IngestResult to stdout
  backfill <artifacts_root>                  → JSON list[StampResult] to stdout
  scan <artifacts_root>                      → JSON list[DriftReport] to stdout

Environment:
  ENTITY_DB_PATH — override DB path (default: ~/.claude/iflow/entities/entities.db)

Exit codes:
  0 — success (including drift detected, errors in results)
  1 — fatal error (bad arguments, DB connection failure)
```

## Risks

### R1: Querying feature entities for bulk operations

The `EntityDatabase` class does not currently expose a `list_entities()` method. `backfill_headers` and `scan_all` need a way to query all feature entities.

**Resolution:** Add a `list_entities(entity_type=None)` method to `database.py`. This is a read-only query method — no schema changes, no behavioral changes to existing methods. The spec constraint C3 ("no raw SQL outside the database module") prohibits accessing `db._conn` from `frontmatter_sync.py`. Adding a public query method to the database module is the correct architectural boundary.

**Signature:**
```python
def list_entities(self, entity_type: str | None = None) -> list[dict]:
    """Return all entities, optionally filtered by entity_type."""
```

Returns dicts with the same keys as `get_entity`: `uuid`, `type_id`, `entity_id`, `entity_type`, `name`, `status`, `artifact_path`, `parent_type_id`, `metadata`, `created_at`, `updated_at`. This keeps all SQL within `database.py` and gives `frontmatter_sync.py` a clean public interface.

### R2: `_parse_feature_type_id` called with non-feature type_ids

If `stamp_header` receives a non-feature type_id (e.g., `"project:P001"`), the `_derive_optional_fields` helper guards on `entity_type == "feature"` before calling `_parse_feature_type_id`. No risk of misparse.

### R3: Concurrent DB + file access

Multiple CLI invocations or hooks running simultaneously could read stale state. SQLite's default serialized transactions prevent DB corruption but not logical races (e.g., stamp reads entity, entity gets deleted, stamp writes file with now-orphaned UUID).

**Mitigation:** Acceptable for CLI tooling. Drift detection exists precisely to catch such divergence after the fact. No locking mechanism needed.

### R4: Large artifact directories

With ~50 existing features and ~6 artifact types each, `backfill_headers` processes up to ~300 files. Each involves 1 DB read + 1 file read + potentially 1 file write. Expected runtime: <5 seconds. No pagination or progress reporting needed for this scale.

## File Impact Summary

| File | Action | Scope |
|------|--------|-------|
| `entity_registry/frontmatter_sync.py` | **Create** | ~200 lines: 4 dataclasses + 5 public functions + 2 internal helpers |
| `entity_registry/frontmatter_sync_cli.py` | **Create** | ~100 lines: argparse CLI with 5 subcommands |
| `entity_registry/test_frontmatter_sync.py` | **Create** | ~400 lines: unit + integration tests for all 24 ACs |
| `entity_registry/backfill.py` | **Modify** | ~5 lines: add `header_aware` parameter + conditional import |
| `entity_registry/database.py` | **Modify** | ~10 lines: add `list_entities(entity_type=None)` read-only query method |

No changes to: `frontmatter.py`, `frontmatter_inject.py`, or any DB schema.
