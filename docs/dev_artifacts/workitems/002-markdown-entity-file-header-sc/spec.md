# Spec: Markdown Entity File Header Schema

## Problem Statement

iflow markdown artifact files carry no embedded identity metadata, causing the link between file content and entity registry records to break when files are moved, copied, or viewed outside their parent directory.

### Traceability

This feature implements PRD Section "M0: Identity and Taxonomy Foundations" — specifically the bidirectional sync invariant prerequisite (PRD → roadmap.md decomposition → feature 002). The PRD defines high-level goals; the roadmap materializes them as features with dependency ordering. Feature 002 defines the schema; feature 003 implements the sync mechanism. The file-to-DB linkage invariant: "UUID in MD file header = foreign key to DB record; file renames don't break linkage" (roadmap.md line 125).

## Goals

1. Define a YAML frontmatter schema for iflow markdown artifact files that embeds entity identity metadata
2. Provide a Python utility module for reading, writing, and validating frontmatter headers
3. Integrate header injection into the workflow-transitions commit path so new artifacts are created with headers automatically
4. Support backward-compatible reading of legacy files (no header = no error)

## Non-Goals

- Bidirectional sync between file headers and DB (feature 003)
- Reconciliation or drift detection between headers and DB (feature 011)
- Retroactively adding headers to all existing artifacts (migration is out of scope — feature 003 handles sync)
- Modifying the entity registry DB schema (no new tables or columns)
- Changing how `.meta.json` works — headers supplement, not replace, `.meta.json`
- UI rendering of frontmatter (feature 020+)

## Requirements

### YAML Frontmatter Schema (Header Definition)

- R1: Frontmatter block uses standard YAML delimiters: opening `---` on first line, closing `---` after the last header field
- R2: The frontmatter block must appear at the very beginning of the file (byte offset 0). No leading whitespace or blank lines before the opening `---`
- R3: Required fields for all artifact files:
  - `entity_uuid`: The entity UUID from the entity registry (immutable once written)
  - `entity_type_id`: The entity type_id (e.g., `feature:002-markdown-entity-file-header-sc`)
  - `artifact_type`: The artifact kind — one of: `spec`, `design`, `plan`, `tasks`, `retro`, `prd`
  - `created_at`: ISO 8601 timestamp of when this file was first created
- R4: Optional fields (included when available):
  - `feature_id`: The feature ID (e.g., `002`)
  - `feature_slug`: The feature slug (e.g., `markdown-entity-file-header-sc`)
  - `project_id`: The project ID if the feature belongs to a project (e.g., `P001`)
  - `phase`: The workflow phase that produced this artifact (e.g., `specify`, `design`)
  - `updated_at`: ISO 8601 timestamp of last modification (caller-managed — `write_frontmatter` does not auto-populate this field; callers must include it in the `headers` dict if desired)
- R5: Field ordering in the YAML block follows the order listed in R3 and R4 (entity_uuid first, then entity_type_id, etc.). This is a write-time convention enforced by `write_frontmatter` and `build_header`. The `read_frontmatter` function accepts fields in any order.
- R6: `entity_uuid` is immutable once written — no process may modify this field after initial creation. This is enforced by the utility module (R11 validation), not by filesystem-level protection.

### Python Utility Module

- R7: Create module at `plugins/iflow/hooks/lib/entity_registry/frontmatter.py`
- R8: `read_frontmatter(filepath: str) -> dict | None` — Parse YAML frontmatter from a markdown file. Returns a dict of header fields, or `None` if no valid frontmatter block is found. Any block delimited by opening `---` and closing `---` is valid frontmatter; the parsed dict may be empty if no lines match the key-value pattern. An empty parsed dict (no key-value pairs found) is returned as-is, not coerced to `None`. Callers that need to distinguish "no header" from "header present but empty" should check the return value: `None` means no valid block was found; an empty dict means a block was found but contained no parseable key-value lines. Only a missing closing `---` constitutes malformed frontmatter (including when the opening `---` is present but no closing `---` exists anywhere in the file, i.e., the block extends to EOF) — returns `None` with a warning logged via Python stdlib `logging` module (logger name: `entity_registry.frontmatter`). Returns `None` without parsing if the file contains null bytes in the first 8192 bytes (binary content guard).
- R9: `write_frontmatter(filepath: str, headers: dict) -> None` — Prepend YAML frontmatter to an existing markdown file, or update existing frontmatter if already present. When updating existing frontmatter: if `entity_uuid` matches, optional fields in `headers` are merged into the existing header (new values override old values for the same key; existing keys not in `headers` are preserved; keys present in `headers` with a value of `None` or empty string are removed from the merged header — this is explicit deletion). If `entity_uuid` does not match, raises `ValueError` (immutability enforcement per R6). After merging, `write_frontmatter` calls `validate_header` on the resulting header dict. If validation fails, the write is aborted and `ValueError` is raised with the validation errors — the original file is not modified. Preserves all content after the closing `---` delimiter. File is written atomically (write to temp file, then rename).
- R10: `build_header(entity_uuid: str, entity_type_id: str, artifact_type: str, created_at: str, **optional_fields) -> dict` — Construct a valid header dict from required and optional fields. Validates field types and values. Raises `ValueError` for invalid inputs.
- R11: `validate_header(header: dict) -> list[str]` — Validate a header dict against the schema. Returns a list of validation error strings (empty list = valid). Checks:
  - All R3 required fields present
  - `entity_uuid` matches UUID v4 format: regex `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` (case-insensitive)
  - `artifact_type` is one of the allowed values
  - `created_at` is valid ISO 8601
  - No unknown fields outside R3 + R4

### Workflow Integration

- R12: Integration is via a Python CLI script (`frontmatter_inject.py`) invoked as a shell command within the `commitAndComplete` pseudocode in the workflow-transitions SKILL.md. The SKILL.md's commit step is extended with a pre-commit shell invocation. Plugin root resolution uses the two-location Glob pattern from CLAUDE.md: primary `~/.claude/plugins/cache/*/iflow*/*/hooks/lib/entity_registry/frontmatter_inject.py`, fallback `plugins/iflow/hooks/lib/entity_registry/frontmatter_inject.py`. The Python interpreter is `<plugin_root>/.venv/bin/python` to ensure entity_registry package availability. The invocation: `<plugin_root>/.venv/bin/python <plugin_root>/hooks/lib/entity_registry/frontmatter_inject.py <artifact_path> <feature_type_id>`. If the script exits non-zero (including when the Python interpreter at `<plugin_root>/.venv/bin/python` does not exist), the workflow logs a warning and proceeds without frontmatter (fail-open).
- R13: To obtain `entity_uuid`, the CLI script instantiates `EntityDatabase` from the existing `entity_registry` package (inheriting connection setup, migrations, and `_resolve_identifier`) and queries by `type_id`. The DB path is resolved by `ENTITY_DB_PATH` environment variable (falling back to `~/.claude/iflow/entities/entities.db`). The DB `type_id` column value is constructed as `feature:{id}-{slug}` from the `.meta.json` fields in the feature directory, or passed as a CLI argument. The frontmatter field `entity_type_id` maps directly to the DB column `type_id` — the `entity_` prefix disambiguates from generic type identifiers in the frontmatter context. If the entity is not registered (DB unavailable or entity missing), skip header injection and log a warning to stderr — do not block the workflow.
- R14: Header injection is idempotent — if the file already has valid frontmatter with the same `entity_uuid`, the existing header is preserved (optional fields may be updated per R9 merge semantics). Files without frontmatter get new headers injected. Files with frontmatter containing a different `entity_uuid` cause the script to raise `ValueError` and exit non-zero (the workflow then skips injection per R12 fail-open behavior).
- R15: The `artifact_type` is derived by exact basename match (case-sensitive): `spec.md` → `spec`, `design.md` → `design`, `plan.md` → `plan`, `tasks.md` → `tasks`, `retro.md` → `retro`, `prd.md` → `prd`. Files with any other basename (e.g., `spec-v2.md`, `notes.md`) are skipped — no header injection, warning logged to stderr.

### Backward Compatibility

- R16: All code that reads markdown artifacts must tolerate files without frontmatter. The `read_frontmatter` function returns `None` for legacy files — callers handle this as "no header, proceed normally."
- R17: The backfill scanner (`backfill.py`) is NOT modified by this feature. Backfill continues to use `.meta.json` as its data source. Feature 003 will add header-aware scanning.

## Constraints

- C1: No external YAML parsing library. The frontmatter schema uses only flat string key-value pairs (no nested structures, no lists, no multi-line values), so a minimal custom parser is sufficient and is the sole implementation. Parser rules: each line is split on the FIRST occurrence of `: ` (colon followed by a single space). The portion before the first `: ` must match `^[a-z_]+$` — this is the key. The entire remainder of the line after the first `: ` is the value (which may itself contain `: ` sequences, e.g., `entity_type_id: feature:002-foo`). Lines not matching this pattern (including blank lines, comments, lines without `: `) are silently ignored. This avoids any dependency on PyYAML (which is a third-party package, not in Python stdlib).
- C2: File write operations must be atomic — write to a temporary file in the same directory, then `os.rename()` to the target path. This prevents partial writes if the process is interrupted. This assumes POSIX semantics where `os.rename()` is atomic for files on the same filesystem. Windows is not a supported platform.
- C3: The utility module must have zero dependencies beyond Python stdlib and the existing `entity_registry` package.
- C4: Frontmatter round-trip fidelity — `read_frontmatter(path)` after `write_frontmatter(path, header)` must return a dict equal to `header` (no data loss or value transformation). Comparison is by dict equality (key-value pairs), not by field ordering in the file.

## Design Constraints (Locked Decisions)

The following implementation decisions are intentionally prescribed in this spec and are locked for the design phase. This is a small, well-scoped utility module where the spec author has pre-resolved these choices to ensure consistency with the existing `entity_registry` package conventions:

- **Function signatures and module location** (R7-R11): The four public functions, their parameters, return types, and module path are fixed. Design should organize internals around these contracts, not redesign them.
- **Custom YAML parser** (C1): The split-on-first-`: ` parser algorithm is locked. No external YAML library. Design may add internal helper functions but must not change the parsing rules.
- **UUID validation regex** (R11): The exact UUID v4 regex pattern is locked.
- **Atomic write mechanism** (C2): POSIX `os.rename()` from temp file in same directory is locked.
- **CLI invocation format** (R12): The `frontmatter_inject.py` CLI interface and plugin root resolution pattern are locked.
- **DB access method** (R13): `EntityDatabase` instantiation from `entity_registry` package is locked.

Design decisions that remain open: internal module structure, error message formatting, temp file naming strategy, logging verbosity levels, and any helper functions needed to implement the locked contracts.

## Acceptance Criteria

- AC-1: A new file created by `write_frontmatter` with a valid header dict starts with `---\n`, contains all required fields, and ends the header block with `---\n` followed by the original file content
- AC-2: `read_frontmatter` on a file with valid frontmatter returns a dict with all header fields
- AC-3: `read_frontmatter` on a legacy file (no frontmatter) returns `None`
- AC-4: `read_frontmatter` on a file with malformed frontmatter (missing closing `---`) returns `None`
- AC-5: `validate_header` with all R3 required fields and valid values returns empty list
- AC-6: `validate_header` missing a required field returns a list containing the field name
- AC-7: `validate_header` with an invalid UUID format returns a validation error
- AC-8: `write_frontmatter` on a file that already has frontmatter replaces only the frontmatter block, preserving the markdown body
- AC-9: `write_frontmatter` uses atomic file writes — verified by mocking `os.rename` to confirm it is called with a temp file path in the same directory as the target
- AC-10: `build_header` with valid required args returns a dict passing `validate_header`
- AC-11: `build_header` with invalid `artifact_type` raises `ValueError`
- AC-12: Integration test: given a temp directory with a feature `.meta.json` and a registered entity in a test DB, when `frontmatter_inject.py` is invoked with the artifact path and type_id, the artifact file contains valid YAML frontmatter with all R3 required fields: `entity_uuid` matching the DB record, `entity_type_id` matching the registered type_id, `artifact_type` derived from the filename, and a valid `created_at` timestamp. Test uses `subprocess.run` to invoke the CLI script with `ENTITY_DB_PATH` pointing to the test DB.
- AC-13: Integration test: given `ENTITY_DB_PATH` pointing to a nonexistent file, when `frontmatter_inject.py` is invoked, it exits with code 0 and logs a warning to stderr. The artifact file is unchanged — no crash, no partial write.
- AC-14: Frontmatter round-trip: `read_frontmatter(path)` after `write_frontmatter(path, h)` returns dict equal to `h`
- AC-15: Header injection is idempotent — running `write_frontmatter` twice with the same header produces identical file content
- AC-16: `entity_uuid` immutability — `write_frontmatter` on a file that already has frontmatter with a different `entity_uuid` raises `ValueError` (does not silently overwrite)
- AC-17: `write_frontmatter` on a file with an existing optional field, passing that field as `None` in `headers`, results in the field being absent from the written frontmatter block (explicit deletion per R9)
- AC-18: `write_frontmatter` on a file with an existing optional field, passing that field as an empty string in `headers`, results in the field being absent from the written frontmatter block (explicit deletion per R9)

## Test Strategy

Unit tests for the `frontmatter.py` module covering:
- Read/write/validate/build functions (AC-1 through AC-11, AC-14 through AC-18)
- Edge cases: empty files, binary content guard (R8 null-byte detection), very large files, Unicode content
- Atomic write verification

Integration tests:
- AC-12: End-to-end header injection during workflow commit
- AC-13: Graceful degradation when DB is unavailable

## Scope Boundary

This feature produces:
1. `plugins/iflow/hooks/lib/entity_registry/frontmatter.py` — utility module (read, write, validate, build)
2. `plugins/iflow/hooks/lib/entity_registry/frontmatter_inject.py` — CLI script for workflow integration
3. `plugins/iflow/hooks/lib/entity_registry/test_frontmatter.py` — unit and integration tests
4. A single-line addition to the `commitAndComplete` pseudocode in `plugins/iflow/skills/workflow-transitions/SKILL.md` — shell invocation of `frontmatter_inject.py`

This feature does NOT produce:
- Any DB schema changes
- Any changes to the backfill scanner
- Any changes to MCP server tools
- Any UI components
- Any retroactive migration of existing files
