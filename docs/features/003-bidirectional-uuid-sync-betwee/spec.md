# Spec: Bidirectional UUID Sync Between Files and DB

## Problem Statement

Feature 002 established YAML frontmatter headers in markdown artifact files and a CLI injection script (`frontmatter_inject.py`) that stamps headers during the `commitAndComplete` workflow step. This provides **write-time** header injection for new artifacts. However, no mechanism exists to:

1. Sync header data back into the entity DB when a file header is the fresher source of truth (e.g., manual header edits, files created outside the workflow)
2. Retroactively stamp headers on the ~50+ existing artifact files that predate feature 002
3. Detect or resolve divergence between a file's frontmatter and the corresponding DB record

The result: the "UUID in MD file header = foreign key to DB record" invariant (roadmap.md line 125) holds only for artifacts created after feature 002 was deployed. Older artifacts remain unlinked, and any out-of-band edits can silently drift.

### Traceability

This feature implements PRD Section "M0: Identity and Taxonomy Foundations" — specifically the bidirectional sync invariant (roadmap.md line 125: "Bidirectional sync invariant: UUID in MD file header = foreign key to DB record; file renames don't break linkage"). Feature 001 established UUID as the canonical DB primary key. Feature 002 defined the frontmatter schema and write-time injection. Feature 003 closes the loop: DB→file backfill, file→DB sync, and drift detection. The downstream consumer is feature 011 (reconciliation MCP tool), which depends on this sync mechanism to detect and report drift.

Note: PRD FR-14 specifies reconciliation between `.meta.json` and DB state — that is a distinct comparison axis (workflow state vs DB) handled by feature 011. Feature 003's drift detection compares frontmatter headers vs DB entity records (identity metadata). Feature 011 will cover both `.meta.json`-vs-DB and frontmatter-vs-DB drift detection, building on top of feature 003's sync primitives.

## Goals

1. Provide a bulk migration tool that retroactively stamps frontmatter headers on all existing artifact files that have a registered entity in the DB
2. Provide a file→DB sync path that updates DB metadata from frontmatter headers when the file is the authoritative source
3. Provide a DB→file sync path that updates file frontmatter from DB records when the DB is the authoritative source
4. Provide a drift detection function that reports mismatches between file headers and DB records without modifying either
5. Integrate the sync mechanism into the backfill scanner so header-aware scanning is available for future backfill runs

## Non-Goals

- Full reconciliation UI or interactive resolution workflow (feature 011)
- Modifying the entity DB schema (no new tables or columns — feature 003 operates within the schema established by features 001-002)
- Changing the frontmatter schema (no new fields — uses the schema from feature 002)
- Automatic conflict resolution — drift detection reports mismatches; human decides resolution direction
- Real-time filesystem watching or inotify-based sync — sync is invoked explicitly
- Modifying the `commitAndComplete` workflow step — feature 002's `frontmatter_inject.py` continues to handle write-time injection

## Requirements

### Sync Module

- R1: Create module at `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync.py`
- R2: The module imports from `entity_registry.frontmatter` (read_frontmatter, write_frontmatter, build_header, validate_header) and `entity_registry.database` (EntityDatabase). No new external dependencies.

### Drift Detection

- R3: `detect_drift(db: EntityDatabase, filepath: str, type_id: str | None = None) -> DriftReport` — Compare frontmatter header in `filepath` against the DB record. `type_id` is optional: if provided, the DB record is looked up by `type_id`; if omitted, the DB record is looked up by `entity_uuid` from the file's frontmatter header (if present). Returns a `DriftReport` dataclass with:
  - `filepath: str` — the file path examined
  - `type_id: str | None` — the entity type_id (from DB lookup or parameter; None if neither available)
  - `status: str` — one of: `"in_sync"`, `"file_only"`, `"db_only"`, `"diverged"`, `"no_header"`
  - `file_fields: dict | None` — frontmatter fields from file (None if no header)
  - `db_fields: dict | None` — relevant fields from DB record (None if entity not found)
  - `mismatches: list[FieldMismatch]` — list of per-field differences (empty if in_sync or one side missing)
- R4: `FieldMismatch` is a dataclass with: `field: str`, `file_value: str | None`, `db_value: str | None`
- R5: Drift detection status logic:
  - `"in_sync"`: file has header AND DB has record AND all comparable fields match
  - `"file_only"`: file has header with `entity_uuid` but no matching DB record exists
  - `"db_only"`: DB record exists but file has no frontmatter header
  - `"diverged"`: both exist but one or more comparable fields differ
  - `"no_header"`: file has no frontmatter AND `type_id` parameter is None (cannot look up DB from either source)
- R6: Comparable fields for drift detection: `entity_uuid` and `entity_type_id`. The field mapping for cross-domain comparison: file field `entity_uuid` compares against DB column `uuid`; file field `entity_type_id` compares against DB column `type_id` (these are the same value — feature 002 R13 established the mapping). The field `artifact_type` is NOT compared against DB (it has no DB column — it is derived from the file basename per feature 002 R15). The fields `created_at`, `updated_at`, `feature_id`, `feature_slug`, `project_id`, `phase` are informational — included in `file_fields`/`db_fields` for reporting but not treated as mismatches (they may legitimately differ between file and DB). Additionally, `artifact_type` from the file header is included in `file_fields` for informational purposes but not compared against any DB value.

### DB→File Sync (Stamp)

- R7: `stamp_header(db: EntityDatabase, filepath: str, type_id: str, artifact_type: str) -> StampResult` — Read the entity from DB by `type_id`, construct a frontmatter header, and write it to the file using `write_frontmatter`. This is the "DB is authoritative" direction.
- R8: `StampResult` is a dataclass with: `filepath: str`, `action: str` (one of: `"created"`, `"updated"`, `"skipped"`, `"error"`), `message: str`
- R8a: Action value mapping for `stamp_header`:
  - `"created"`: file had no existing frontmatter — header was injected for the first time
  - `"updated"`: file had existing frontmatter with matching `entity_uuid` — optional fields were merged from DB
  - `"skipped"`: not used by stamp_header directly — used by `backfill_headers` (R20 step 2d) when a derived directory does not exist on disk
  - `"error"`: entity not found in DB (R11), or file has frontmatter with mismatched `entity_uuid` (R10), or other failure (DB connection error, file not found)
- R9: If the file already has frontmatter with a matching `entity_uuid`, merge new optional fields from the DB record (update direction: DB→file). The `write_frontmatter` merge semantics from feature 002 handle this. This returns `action="updated"`.
- R10: If the file already has frontmatter with a *different* `entity_uuid`, return `StampResult` with `action="error"` and descriptive message. Do not modify the file. Do not raise an exception — callers handle the error report.
- R11: If the entity is not found in the DB (`db.get_entity(type_id)` returns None), return `StampResult` with `action="error"`.
- R12: stamp_header flow: (1) call `db.get_entity(type_id)` — if None, return error per R11; (2) extract `entity_uuid` from result `["uuid"]`, `entity_type_id` from result `["type_id"]`, `created_at` from result `["created_at"]`; (3) derive optional fields per R13; (4) call `read_frontmatter(filepath)` to check existing state; (5) if existing header has mismatched UUID, return error per R10; (6) call `write_frontmatter(filepath, header)` — catch `FrontmatterUUIDMismatch` as error; (7) return `action="created"` if no prior header existed, `action="updated"` if prior header was present.
- R13: Optional field derivation rules. These follow the existing `_parse_feature_type_id` and `_extract_project_id` patterns from `frontmatter_inject.py` (lines 67-104):
  - `feature_id` and `feature_slug`: extracted from type_id using the same algorithm as `frontmatter_inject.py`'s `_parse_feature_type_id` (lines 67-85). Strip the `entity_type:` prefix (split on first `:`), then split the remaining entity_id on the first `-`. The portion before the hyphen is `feature_id`, the portion after is `feature_slug`. Only applies when `entity_type == "feature"`. If no hyphen in entity_id, `feature_slug` is omitted. Example: type_id `"feature:003-bidirectional-uuid-sync-betwee"` → `feature_id="003"`, `feature_slug="bidirectional-uuid-sync-betwee"`. Implementation should import `_parse_feature_type_id` directly from `frontmatter_inject` (no change to that file needed).
  - `project_id`: best-effort derivation with two sources checked in order: (1) parse entity's `metadata` JSON and look for key `"project_id"` — if present and non-empty, use it; (2) otherwise, check entity's `parent_type_id` field — if present and the parent entity's type starts with `"project:"`, extract the entity_id portion after the colon (e.g., `"project:P001"` → `"P001"`). This uses the entity record's `parent_type_id` field directly — no second DB lookup needed. If neither source yields a value, omit `project_id` from the header.
  - `phase`: from `artifact_type` parameter (maps 1:1: spec→specify, design→design, plan→create-plan, tasks→create-tasks, retro→finish, prd→brainstorm)

### File→DB Sync (Ingest)

- R14: `ingest_header(db: EntityDatabase, filepath: str) -> IngestResult` — Read frontmatter from `filepath` and update the corresponding DB record. This is the "file is authoritative" direction.
- R15: `IngestResult` is a dataclass with: `filepath: str`, `action: str` (one of: `"updated"`, `"skipped"`, `"error"`), `message: str`
- R16: The DB record is looked up by `entity_uuid` from the file header (via `db.get_entity(entity_uuid)`). If no record is found, return `action="error"` (we don't create DB records from file headers alone — registration is the DB's responsibility).
- R17: Updatable fields from file→DB: only `artifact_path` (set to the absolute filepath). The `entity_type`, `entity_id`, `type_id`, `uuid`, `name`, `status`, and `created_at` are immutable — never modified by ingest. The frontmatter fields `feature_id`, `feature_slug`, `project_id`, `phase` are informational decorations derived from the DB during stamp — they do NOT flow back into the DB during ingest (the DB is the canonical source for these values). The update is performed via `db.update_entity(entity_uuid, artifact_path=filepath)` — note: `update_entity`'s first parameter is named `type_id` but accepts UUIDs via the `_resolve_identifier` dual-read resolver (feature 001 R18; confirmed in `database.py` line 122). The designer should verify this call path against `database.py` to confirm UUID acceptance.
- R18: If the file has no frontmatter, return `action="skipped"`.

### Bulk Migration (Backfill Headers)

- R19: `backfill_headers(db: EntityDatabase, artifacts_root: str) -> list[StampResult]` — Scan all known artifact files across all registered feature entities and stamp headers on files that lack them.
- R20: Scan strategy:
  1. Query DB for all entities with `entity_type = "feature"`
  2. For each feature entity, derive the feature directory using this fallback chain: (a) if entity has `artifact_path` and `os.path.isdir(artifact_path)`, use it; (b) if entity has `artifact_path` and `os.path.isfile(artifact_path)`, use `os.path.dirname(artifact_path)`; (c) if entity has no `artifact_path` (None), construct from entity_id: `{artifacts_root}/features/{entity_id}/`; (d) if the derived directory does not exist on disk, skip this entity (include a `StampResult` with `action="skipped"` and message indicating missing directory)
  3. For each known artifact filename (`spec.md`, `design.md`, `plan.md`, `tasks.md`, `retro.md`, `prd.md`), check if the file exists in the feature directory
  4. For each existing file, call `stamp_header` to inject/update the header
  Note: after `ingest_header` (R17) runs, a feature entity's `artifact_path` may point to a specific file rather than the feature directory. Step 2b handles this case (`os.path.isfile` → `dirname`). Backfill tolerates both cases.
- R21: Files that already have valid frontmatter with matching `entity_uuid` are updated (optional fields merged) but not reported as errors. Files with mismatched `entity_uuid` are reported as errors and skipped.
- R22: `backfill_headers` returns a list of all `StampResult` outcomes for logging/auditing.
- R23: The function is idempotent — running it multiple times produces the same file state.

### Backfill Scanner Integration

- R24: Extend `backfill.py` with an optional `header_aware: bool = False` parameter on `run_backfill`. When `True`, call `backfill_headers(db, artifacts_root)` to stamp headers on all discovered artifact files.
- R25: The `header_aware` parameter defaults to `False` to maintain backward compatibility. Existing callers are not affected.
- R26: Header stamping runs BEFORE and INDEPENDENTLY of the `backfill_complete` early-return guard. The existing guard (line 44: `if db.get_metadata("backfill_complete") == "1": return`) prevents re-running entity registration on already-backfilled databases. Header stamping is independent of entity registration — it operates on entities that already exist in the DB. Therefore, the `run_backfill` function structure is: (1) if `header_aware`, call `backfill_headers` regardless of backfill_complete state; (2) then check `backfill_complete` guard for entity registration. This ensures `header_aware=True` works on production databases where entity backfill has already completed.

### CLI Interface

- R27: Create `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync_cli.py` — CLI entry point for manual invocation of sync operations.
- R28: CLI subcommands:
  - `drift <filepath> <type_id>` — Run drift detection, print JSON report
  - `stamp <filepath> <type_id> <artifact_type>` — Stamp DB record onto file header
  - `ingest <filepath>` — Ingest file header into DB
  - `backfill <artifacts_root>` — Run bulk header backfill
  - `scan <artifacts_root>` — Drift-scan all artifact files and print summary report
- R29: CLI uses `argparse` from stdlib. DB path resolved via `ENTITY_DB_PATH` env var (falling back to `~/.claude/iflow/entities/entities.db`), consistent with feature 002's `frontmatter_inject.py`.
- R30: All CLI output is JSON to stdout (machine-readable). Human-readable summaries go to stderr. Exit code 0 for success (even if drift detected), non-zero for fatal errors only.

### Scan All (Bulk Drift Detection)

- R31: `scan_all(db: EntityDatabase, artifacts_root: str) -> list[DriftReport]` — Scan all registered feature entities' artifact files and return drift reports.
- R32: Scan strategy mirrors `backfill_headers` (R20) but calls `detect_drift` instead of `stamp_header`.
- R33: Returns a flat list of `DriftReport` objects. Callers can filter by `status` to find drifted or unlinked files.

## Constraints

- C1: No external dependencies beyond Python stdlib and the existing `entity_registry` package
- C2: All file writes use the atomic write pattern from feature 002 (temp file + `os.rename`), inherited via `write_frontmatter`
- C3: DB access uses `EntityDatabase` from the existing `entity_registry` package — no raw SQL outside the database module
- C4: The sync module does not modify the DB schema. It operates within the entities table schema established by features 001-002
- C5: All functions are independently testable — no global state, no singletons. DB and file paths are explicit parameters
- C6: The module must handle the case where the DB is unavailable (file not found or connection error) — return error results, do not crash

## Design Constraints (Locked Decisions)

- **Module location**: `frontmatter_sync.py` in `plugins/iflow/hooks/lib/entity_registry/` — consistent with existing module layout
- **CLI location**: `frontmatter_sync_cli.py` in same directory
- **Dataclass return types**: `DriftReport`, `FieldMismatch`, `StampResult`, `IngestResult` are Python dataclasses (stdlib `dataclasses` module)
- **DB access method**: `EntityDatabase` instantiation from `entity_registry` package (same pattern as feature 002's `frontmatter_inject.py`)
- **Comparable fields for drift**: Only `entity_uuid` and `entity_type_id` (artifact_type is excluded per R6 — no DB column exists for it) — keeping the comparison set small to avoid false-positive drift on informational fields

Design decisions that remain open: internal helper decomposition, logging verbosity levels, batch size for bulk operations, progress reporting mechanism for bulk backfill.

## Acceptance Criteria

### Drift Detection

- AC-1: `detect_drift` on a file with matching frontmatter and DB record returns `status="in_sync"` with empty `mismatches`
- AC-2: `detect_drift` on a file with frontmatter but no matching DB record returns `status="file_only"`
- AC-3: `detect_drift` on a file without frontmatter where a DB record exists returns `status="db_only"`
- AC-4: `detect_drift` on a file where `entity_type_id` in the header differs from the DB `type_id` returns `status="diverged"` with a `FieldMismatch` entry where `field="entity_type_id"`
- AC-5: `detect_drift(db, filepath)` (no `type_id` argument) on a file without frontmatter returns `status="no_header"` (neither file nor parameter provides a DB lookup key)

### DB→File Sync (Stamp)

- AC-6: `stamp_header` on a file with no existing frontmatter creates a valid header with all required frontmatter fields (`entity_uuid`, `entity_type_id`, `artifact_type`, `created_at` — per feature 002 R3) from the DB record. Verified by `read_frontmatter` returning a dict with `entity_uuid` matching the DB record's UUID.
- AC-6a: `stamp_header` on a feature entity whose metadata JSON contains `{"project_id": "P001"}` and whose `parent_type_id` is not a project type includes `project_id="P001"` in the stamped header. Verifies metadata-based derivation takes priority over `parent_type_id` fallback.
- AC-7: `stamp_header` on a file with existing matching frontmatter updates optional fields from DB without changing `entity_uuid`. Verified by `read_frontmatter` before and after showing same `entity_uuid`.
- AC-8: `stamp_header` on a file with mismatched `entity_uuid` returns `action="error"` and does not modify the file
- AC-9: `stamp_header` with a nonexistent `type_id` returns `action="error"`
- AC-10: `stamp_header` preserves all markdown body content after the frontmatter block (verified by comparing body content before and after)

### File→DB Sync (Ingest)

- AC-11: `ingest_header` on a file with valid frontmatter updates the DB record's `artifact_path` to the file's path
- AC-12: `ingest_header` on a file without frontmatter returns `action="skipped"`
- AC-13: `ingest_header` on a file with frontmatter referencing a nonexistent DB entity returns `action="error"`

### Bulk Migration

- AC-14: `backfill_headers` on a directory with 3 feature entities (each having spec.md and design.md without frontmatter) stamps headers on all 6 files. Verified by `read_frontmatter` returning non-None for each.
- AC-15: `backfill_headers` is idempotent — running twice produces identical file content. First run returns `action="created"` for files without headers; second run returns `action="updated"` for the same files (headers now exist but are re-merged with identical data). File content is byte-identical after both runs.
- AC-16: `backfill_headers` skips files with mismatched `entity_uuid` and includes them as errors in the result list

### Scan All

- AC-17: `scan_all` on a directory with 2 features (one with headers, one without) returns appropriate drift statuses for each file

### Backfill Integration

- AC-18: `run_backfill(db, artifacts_root, header_aware=True)` stamps headers on artifact files regardless of `backfill_complete` state, and entity registration proceeds normally after (per R26 ordering)
- AC-19: `run_backfill(db, artifacts_root)` (default) does NOT stamp headers — backward compatible

### CLI

- AC-20: `frontmatter_sync_cli.py drift <filepath> <type_id>` outputs valid JSON to stdout with `status` field
- AC-21: `frontmatter_sync_cli.py backfill <artifacts_root>` stamps headers on all discovered artifact files and outputs JSON summary
- AC-22: `frontmatter_sync_cli.py scan <artifacts_root>` outputs JSON array of drift reports

### Error Handling

- AC-23: All sync functions handle DB unavailability (connection error) by returning error results, not raising exceptions
- AC-24: All sync functions handle missing files by returning error/skipped results, not raising exceptions

## Test Strategy

Unit tests for `frontmatter_sync.py` covering:
- Drift detection: all 5 status outcomes (AC-1 through AC-5)
- Stamp: create, update, mismatch error, missing entity (AC-6 through AC-10)
- Ingest: update, skip, missing entity (AC-11 through AC-13)
- Bulk backfill: multi-file, idempotency, mismatch handling (AC-14 through AC-16)
- Scan all: mixed drift statuses (AC-17)
- Error handling: DB unavailable, missing files (AC-23, AC-24)

Integration tests:
- Backfill integration with `run_backfill` (AC-18, AC-19)
- CLI subcommands via `subprocess.run` (AC-20 through AC-22)

All tests use in-memory SQLite DB and temp directories. Test file location: `plugins/iflow/hooks/lib/entity_registry/test_frontmatter_sync.py`

Manual verification (post-implementation, not automated):
- Run `frontmatter_sync_cli.py scan docs` against the actual `docs/features/` directory and verify all registered entities are discovered
- Run `frontmatter_sync_cli.py backfill docs` against the actual directory and verify headers are stamped on existing artifact files

## Dependencies

- **Depends on**: 002-markdown-entity-file-header-sc (frontmatter module, schema, write_frontmatter)
- **Depends on**: 001-entity-uuid-primary-key-migrat (UUID primary key, dual-read resolver, EntityDatabase API)
- **Required by**: 011-reconciliation-mcp-tool

## Scope Boundary

### In Scope

1. `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync.py` — sync module (detect_drift, stamp_header, ingest_header, backfill_headers, scan_all)
2. `plugins/iflow/hooks/lib/entity_registry/frontmatter_sync_cli.py` — CLI entry point
3. `plugins/iflow/hooks/lib/entity_registry/test_frontmatter_sync.py` — tests
4. Modification to `backfill.py` — add `header_aware` parameter to `run_backfill`

### Out of Scope

- Any DB schema changes (no new tables, columns, or migrations)
- Any changes to `frontmatter.py` or `frontmatter_inject.py`
- Any MCP server tool additions (feature 011 handles MCP exposure)
- Any UI components
- Interactive conflict resolution
- Any changes to the `commitAndComplete` workflow step
