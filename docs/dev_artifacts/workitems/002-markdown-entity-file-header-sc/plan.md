# Plan: Markdown Entity File Header Schema

## Implementation Order

TDD approach: write tests first for each function, then implement, then verify. The dependency graph is linear — each phase builds on the previous.

```
Phase 1: Core Infrastructure
  └── Constants, helpers (_parse_block, _serialize_header)
       │
Phase 2: Validation & Build
  └── validate_header, build_header
       │
Phase 3: Read
  └── read_frontmatter
       │
Phase 4: Write
  └── write_frontmatter (depends on read, validate, serialize)
       │
Phase 5: CLI Script
  └── frontmatter_inject.py (depends on all of Phase 1-4 + EntityDatabase)
       │
Phase 6: SKILL.md Integration
  └── Pseudocode addition to commitAndComplete
       │
Phase 7: Integration Tests
  └── AC-12, AC-13 (end-to-end CLI + DB)
```

---

## Phase 1: Core Infrastructure

**Goal:** Establish the foundational constants and internal helpers that all public functions depend on.

**Files:** `frontmatter.py`, `test_frontmatter.py`

### Step 1.1: Module scaffolding and constants

Create `frontmatter.py` with:
- Imports: `os`, `re`, `tempfile`, `logging`, `datetime`
- Logger: `logging.getLogger("entity_registry.frontmatter")`
- `FIELD_ORDER` tuple (TD-2): `("entity_uuid", "entity_type_id", "artifact_type", "created_at", "feature_id", "feature_slug", "project_id", "phase", "updated_at")`
- `REQUIRED_FIELDS` frozenset: `{"entity_uuid", "entity_type_id", "artifact_type", "created_at"}`
- `OPTIONAL_FIELDS` frozenset: `{"feature_id", "feature_slug", "project_id", "phase", "updated_at"}`
- `ALLOWED_FIELDS` frozenset: `REQUIRED_FIELDS | OPTIONAL_FIELDS`
- `ALLOWED_ARTIFACT_TYPES` frozenset: `{"spec", "design", "plan", "tasks", "retro", "prd"}`
- `_UUID_V4_RE` compiled regex (R11): `re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')` — NO `re.IGNORECASE`, matching the existing `database.py:11-13` convention. Callers must `.lower()` UUIDs before regex validation. The spec says "case-insensitive" (R11), which is achieved by normalizing input to lowercase before matching, not by making the regex case-insensitive. This ensures consistency with the DB layer which also `.lower()`s before matching.

Create `test_frontmatter.py` with:
- Imports: `pytest`, `os`, `tempfile`
- `from entity_registry.frontmatter import ...` (all public functions + constants for white-box testing of helpers)
- `tmp_path` fixture usage (pytest built-in)

### Step 1.2: `_parse_block` helper

**TDD tests first** (in a helper test class or inline):
- Empty lines list → empty dict
- Single valid `key: value` line → `{"key": "value"}`
- Line with colon in value (`entity_type_id: feature:002-foo`) → key is `entity_type_id`, value is `feature:002-foo`
- Line without `: ` separator → ignored
- Line with invalid key chars (uppercase, digits, hyphens) → ignored
- Blank lines and comment lines → ignored
- Multiple valid lines → all captured

**Implement:** Per I7 — `line.partition(': ')`, `re.fullmatch(r'[a-z_]+', key)`, return dict.

### Step 1.3: `_serialize_header` helper

**TDD tests first:**
- Dict with all required fields → string starting with `---\n`, ending with `---\n`, fields in FIELD_ORDER
- Dict with required + optional fields → optional fields appear after required, in FIELD_ORDER
- Dict with unknown field → appears after all FIELD_ORDER fields
- Round-trip: serialize then parse back. Split `_serialize_header(h)` by `\n`, extract lines between the opening `---` and closing `---` delimiters (skip first line which is `---`, stop before the line that is `---`), pass to `_parse_block()`, verify result equals `h`. Test with: non-empty dict, single-field dict, and empty dict `{}` (edge case — serialized as `---\n---\n`, parsed back to `{}`).

**Implement:** Per I8 — iterate FIELD_ORDER, then remaining keys, wrap with `---\n` delimiters.

**Dependency:** `_parse_block` (for internal round-trip test only, not functional dependency).

---

## Phase 2: Validation & Build Functions

**Goal:** Implement the two functions that don't do file I/O.

**Files:** `frontmatter.py`, `test_frontmatter.py`

### Step 2.1: `validate_header`

**TDD tests first** (class `TestValidateHeader`):
- AC-5: All required fields with valid values → empty list
- AC-6: Missing each required field individually → error mentioning field name
- AC-7: Invalid UUID format → validation error
- Valid UUID (lowercase) → no error
- Valid UUID (uppercase) → no error (UUID is `.lower()`'d before regex matching per DB convention)
- Invalid `artifact_type` → validation error
- Each valid `artifact_type` → no error
- Invalid `created_at` (not ISO 8601) → validation error
- Valid `created_at` with timezone → no error
- Unknown field present → validation error
- Multiple errors → all returned (no short-circuit)

**Implement:** Per I4 — check required fields, UUID regex (`.lower()` UUID before matching `_UUID_V4_RE`), artifact_type set membership, `datetime.fromisoformat()` for created_at, unknown field check.

### Step 2.2: `build_header`

**TDD tests first** (class `TestBuildHeader`):
- AC-10: Valid required args → dict passing `validate_header`
- AC-11: Invalid `artifact_type` → `ValueError`
- Invalid UUID → `ValueError`
- Invalid `created_at` → `ValueError`
- Valid required + valid optional kwargs → all present in output dict
- Unknown optional kwarg → `ValueError`

**Implement:** Per I3 — construct dict from positional + kwargs, call `validate_header`, raise `ValueError` if errors.

**Dependency:** `validate_header`.

---

## Phase 3: Read Function

**Goal:** Implement `read_frontmatter` — the read-only file operation.

**Files:** `frontmatter.py`, `test_frontmatter.py`

### Step 3.1: `read_frontmatter`

**TDD tests first** (class `TestReadFrontmatter`):
- AC-2: File with valid frontmatter → dict with all fields
- AC-3: Legacy file (no `---` on line 1) → `None`
- AC-4: Malformed frontmatter (opening `---` but no closing `---`) → `None` + warning logged
- Empty file → `None`
- File with `---` on line 1 and `---` on line 2 (empty block) → `{}` (empty dict, NOT None)
- File with frontmatter containing values with `: ` in them → correct parsing
- Binary content (null bytes in first 8192 bytes) → `None` + warning
- File does not exist → `None` + warning
- Body content after frontmatter preserved (not part of return value, but ensures only header is parsed)
- Large file with frontmatter → only header portion parsed (no full read)

**Implement:** Per I1 —
1. Open binary, read 8192 bytes, check for `\x00`
2. Open text (`encoding='utf-8'`), read line-by-line
3. First line must be `---` (stripped) — else return None
4. Accumulate lines until closing `---` or EOF
5. If EOF without closing → warn, return None
6. Pass accumulated lines to `_parse_block()`

**Dependency:** `_parse_block`.

---

## Phase 4: Write Function

**Goal:** Implement `write_frontmatter` — the most complex function with merge, validation, and atomic write.

**Files:** `frontmatter.py`, `test_frontmatter.py`

### Step 4.1: `write_frontmatter`

**TDD tests first** (class `TestWriteFrontmatter`):
- AC-1: New file (no frontmatter) → prepend header block, body preserved
- AC-8: File with existing frontmatter → replace only header, body preserved
- AC-9: Atomic write verification (mock-only test, separate from content tests) → mock `os.rename` to verify it is called with a `.tmp` file in the same directory as the target. Note: content correctness after real atomic writes is verified by AC-1 and AC-8 tests (non-mocked).
- AC-14: Round-trip fidelity (also in `TestRoundTrip`)
- AC-15: Idempotent — write twice with same header → identical file content
- AC-16: UUID mismatch → `ValueError`
- AC-17: Existing optional field + `None` in new headers → field removed
- AC-18: Existing optional field + `""` in new headers → field removed
- TD-9: Existing `created_at` preserved when new headers have different `created_at`
- File does not exist → `ValueError`
- Merge: existing key not in new headers → preserved
- Merge: new key not in existing → added
- Validation failure after merge → `ValueError`, file unchanged
- Temp file cleanup on error (write fails before rename)

**Implement:** Per I2 —
1. Open file (catch `FileNotFoundError` → `ValueError`)
2. Read content, check for existing frontmatter via same line-by-line logic as `read_frontmatter`
3. If existing: extract header dict, check UUID match using `.lower()` on both existing and new UUID values (raise `ValueError` if mismatch after lowercasing). Add test case: file has UUID in uppercase, new header has same UUID in lowercase → should NOT raise ValueError.
4. Merge: start with existing, apply new headers (None/empty → delete, else overwrite), preserve `created_at` per TD-9
5. If no existing: use new headers directly
6. Validate merged header → abort on failure
7. Serialize: `_serialize_header(merged) + body` — `_serialize_header` ends with `---\n`. Body is concatenated directly with NO extra blank line inserted. For files with existing frontmatter, body is everything after the closing `---\n` (preserving any leading blank lines the original body had). For new files (no existing frontmatter), the entire original file content becomes the body. This ensures round-trip fidelity (C4) — no content is added or removed between header and body.
8. Atomic write: `NamedTemporaryFile(delete=False, dir=same_dir, suffix='.tmp')` → write → `os.rename`
9. `finally`: cleanup temp file if rename didn't happen

**Binary content guard:** `write_frontmatter` includes the same binary content guard as `read_frontmatter`: read first 8192 bytes, check for `\x00`. If binary content detected, raise `ValueError("Cannot write frontmatter to binary file")`. Although the CLI script filters by basename, `write_frontmatter` is a public API and must be defensive. Add a test: `write_frontmatter` on a file with null bytes raises `ValueError`, file unchanged. **Implementation note:** The guard runs before any file modification logic — early return on binary content prevents unnecessary parsing or merge attempts.

**Dependency:** `read_frontmatter` (for detecting existing headers — but note: `write_frontmatter` implements its own read logic internally rather than calling `read_frontmatter`, because it needs both the parsed header AND the body content. The read logic is duplicated but keeps the two functions decoupled), `validate_header`, `_serialize_header`.

**Design note:** `write_frontmatter` does NOT call `read_frontmatter` — it implements its own read-and-split logic because it needs both the header dict AND the remaining body content. `read_frontmatter` only returns the header dict. Extracting a shared internal helper for delimiter detection + line accumulation would be premature abstraction for this scope.

**Divergence guard test:** Add a test in `TestWriteFrontmatter` that verifies: for a file with existing frontmatter, `read_frontmatter(path)` returns the same header dict that `write_frontmatter`'s internal read logic parses. This catches accidental divergence between the two read paths. Test body content starting with `---` (a markdown horizontal rule) to ensure the read logic correctly stops at the closing delimiter, not a body `---` line.

### Step 4.2: Round-trip test (class `TestRoundTrip`)

- AC-14: `read_frontmatter(path)` after `write_frontmatter(path, h)` returns dict equal to `h`
- Test with all required fields only
- Test with required + all optional fields
- Test with values containing `: ` characters

**Dependency:** Both `read_frontmatter` and `write_frontmatter` implemented.

---

## Phase 5: CLI Script

**Goal:** Build the workflow integration entry point.

**Files:** `frontmatter_inject.py`

### Step 5.1: `frontmatter_inject.py` scaffolding

Create CLI script with:
- Imports: `sys`, `os`, `logging`, `datetime`, `sqlite3`
- `from entity_registry.frontmatter import build_header, write_frontmatter`
- `from entity_registry.database import EntityDatabase`
- Logging config: `StreamHandler(sys.stderr)` with format `"%(levelname)s: %(message)s"`
- `ARTIFACT_BASENAME_MAP` constant (TD-6)
- `ARTIFACT_PHASE_MAP` constant (I5 step 7)
- **Extract testable helper functions:**
  - `_parse_feature_type_id(type_id: str) -> tuple[str, str | None]` — splits `feature:002-slug` into `("002", "slug")`. If entity_id contains no `-`, returns `(entity_id, None)`.
  - `_extract_project_id(parent_type_id: str | None) -> str | None` — extracts `"P001"` from `"project:P001"`. Returns `None` if parent is not a project or is None.

### Step 5.2: Unit tests for CLI logic

**TDD tests first** (class `TestFrontmatterInjectHelpers` in `test_frontmatter.py`):
- `ARTIFACT_BASENAME_MAP` contains all 6 supported basenames
- `ARTIFACT_PHASE_MAP` contains all 6 artifact types
- Feature_id/slug parsing: `feature:002-some-slug` → `("002", "some-slug")`
- Feature_id/slug parsing: `feature:noseparator` → `("noseparator", None)` — no `-` in entity_id
- Feature_id/slug parsing: `feature:` → edge case, empty entity_id
- project_id extraction from `parent_type_id`: `project:P001` → `"P001"`
- project_id extraction when parent is not project: `brainstorm:abc` → `None`
- project_id extraction when no parent: `None` → `None`

**Note:** These test the parsing/derivation logic extracted as testable helpers. The full end-to-end CLI tests are in Phase 7 (integration tests).

### Step 5.3: Main function

**API pre-verification (before writing code):** Read `database.py` — specifically the `get_entity()` method and `_resolve_identifier()` helper. Confirm that `get_entity()` accepts a `type_id` string (e.g., `feature:002-slug`), not only a UUID. The `_resolve_identifier()` method handles both UUID and type_id lookup, and `get_entity()` delegates to it. If this assumption is incorrect (i.e., `get_entity()` only accepts UUID), the CLI must call `_resolve_identifier()` directly or use a different query path — document the finding and adjust step 5 below accordingly.

**Implement** per I5:
1. Parse `sys.argv` — expect `len(sys.argv) == 3` (script name + artifact_path + feature_type_id). If wrong count, print usage to stderr and exit 1.
2. Derive `artifact_type` from basename via `ARTIFACT_BASENAME_MAP` — skip if not found
3. Resolve DB path from `ENTITY_DB_PATH` env var
4. Instantiate `EntityDatabase(db_path)` — catch `(sqlite3.Error, OSError)` specifically, warn to stderr, exit 0. Do NOT catch bare `Exception` — let programming bugs (TypeError, AttributeError, NameError) propagate as unhandled exceptions. `sqlite3.Error` is the base class for the entire `sqlite3` exception hierarchy: `OperationalError` (corrupt DB, locked), `DatabaseError` (invalid file), `InterfaceError`, `ProgrammingError`, `IntegrityError`, and `DataError` are all subclasses. Catching `sqlite3.Error` therefore covers all database-layer failures without needing to enumerate individual subclasses. `OSError` covers permission errors and path issues. `EntityDatabase.__init__` runs migrations to the latest schema (currently v2 which includes the `uuid` column), so by the time `get_entity` is called the schema is guaranteed current.
5. Call `db.get_entity(feature_type_id)` — if None, warn, exit 0
6. Extract UUID from entity record: `entity_uuid = entity_record['uuid']` — note the DB column is `uuid` (via `dict(row)` from `get_entity()`), mapped to frontmatter field `entity_uuid`. The `entity_` prefix disambiguates in the frontmatter context per spec R13.
7. Parse `feature_id` and `feature_slug` from `feature_type_id`: split on first `:` to get entity_id (e.g., `002-markdown-entity-file-header-sc`), then split entity_id on first `-` to get feature_id (`002`) and feature_slug (`markdown-entity-file-header-sc`). **Defensive guard:** If entity_id contains no `-`, set `feature_id = entity_id` and omit `feature_slug` from the header (don't pass it to `build_header`). This handles edge cases like entity_ids without slugs.
8. Derive `project_id` from entity's `parent_type_id` (if `project:*` pattern). **Scope note:** Only checks immediate parent — does not traverse ancestor chain. This is intentional: feature entities are registered with `parent_type_id` pointing directly to their project (e.g., `project:P001`) in `create-feature` command. No ancestor traversal needed.
9. Derive `phase` from `ARTIFACT_PHASE_MAP[artifact_type]`
10. Build header via `build_header()` with required + optional fields
11. Call `write_frontmatter(artifact_path, header)`

**Error boundary (governs steps 4, 5, 11):** Targeted exception handling, NOT a blanket `try/except Exception`. Each operation catches specific exceptions:
- **Step 4** — `EntityDatabase(db_path)`: catches `(sqlite3.Error, OSError)` → warn, exit 0
- **Step 5** — `db.get_entity(type_id)`: catches `(sqlite3.Error,)` → warn, exit 0
- **Step 11** — `write_frontmatter(path, header)`: catches `ValueError` (UUID mismatch) → exit 1; catches `OSError` → warn, exit 0
- **All other steps** — unexpected exceptions (TypeError, AttributeError, NameError, etc.) propagate as unhandled — the `|| true` in SKILL.md already provides the fail-open safety net at the workflow level. This makes programming bugs visible in stderr instead of being silently swallowed.

---

## Phase 6: SKILL.md Integration

**Goal:** Add frontmatter injection pseudocode to the workflow-transitions skill.

**Files:** `plugins/iflow/skills/workflow-transitions/SKILL.md`

### Step 6.1: Add pseudocode block

Insert the frontmatter injection pseudocode (I6) into the `commitAndComplete` function, between the step heading and the existing `git add` bash code block. The new block is a separate pseudocode section, NOT inserted inside the existing bash block. The addition is LLM-interpreted pseudocode matching the existing SKILL.md style, including:
- Plugin root resolution (two-location Glob pattern)
- For-each loop over artifact files
- Shell invocation with stderr suppression and `|| true`
- `entity_type_id` construction from `.meta.json` fields

**Verification:** Read the modified SKILL.md to confirm the pseudocode is in the correct location and syntactically consistent with surrounding pseudocode.

### Step 6.2: Validate SKILL.md modification

Run `./validate.sh` and confirm no plugin portability violations (hardcoded `plugins/iflow/` paths) are flagged in the modified SKILL.md. The pseudocode uses the two-location Glob pattern per CLAUDE.md convention — `validate.sh` catches violations.

---

## Phase 7: Integration Tests

**Note:** AC-12 tests the CLI subprocess directly (not via the SKILL.md pseudocode path). The SKILL.md integration is verified manually in Phase 6 Step 6.1/6.2. The SKILL.md pseudocode is LLM-interpreted at runtime — automated testing of that path requires an end-to-end workflow execution which is outside this feature's scope.

**Goal:** End-to-end tests for the CLI script with a real (test) database.

**Files:** `test_frontmatter.py`

### Step 7.1: Integration test infrastructure

Set up test helpers:
- Create temp directory with `.meta.json` fixture
- Create **file-based** test DB using `EntityDatabase(str(tmp_path / "test.db"))` — NOT `:memory:` — because the CLI subprocess needs to access it via `ENTITY_DB_PATH` env var. Before subprocess invocation, flush the DB: if `EntityDatabase` exposes a `close()` method, call it; if it supports context manager (`__exit__`), use `with` block; otherwise, delete the `db` reference and call `gc.collect()` to trigger SQLite's WAL checkpoint via garbage collection. **Pre-verification:** Read `database.py` to confirm which teardown method is available before writing the test infrastructure.
- Create temp artifact file (`spec.md` with markdown content)
- Subprocess invocation uses `subprocess.run([sys.executable, script_path, artifact_path, type_id], env={...})` where `sys.executable` is the test runner's Python, and `env` includes `PYTHONPATH` pointing to the `hooks/lib` directory and `ENTITY_DB_PATH` pointing to the test DB file path. **Common pitfall:** `PYTHONPATH` must resolve to the absolute `hooks/lib` directory so `from entity_registry.frontmatter import ...` works in the subprocess. Integration tests should verify this explicitly by checking exit code and stderr for import errors.

### Step 7.2: AC-12 — Happy path integration test

**Class `TestFrontmatterInjectCLI`:**
- Register entity in test DB with known UUID
- Create `spec.md` in temp dir with plain markdown (no frontmatter)
- Invoke `frontmatter_inject.py` via `subprocess.run` with `ENTITY_DB_PATH` pointing to test DB
- Assert exit code 0
- Read artifact file → `read_frontmatter()` returns dict with:
  - `entity_uuid` matching DB record
  - `entity_type_id` matching registered type_id
  - `artifact_type` == `"spec"`
  - `created_at` is valid ISO 8601

### Step 7.3: AC-13 — DB unavailable graceful degradation

- Set `ENTITY_DB_PATH` to a nonexistent path
- Invoke `frontmatter_inject.py` via `subprocess.run`
- Assert exit code 0
- Assert stderr contains warning
- Assert artifact file unchanged (no frontmatter added, no crash)

### Step 7.4: Additional integration edge cases

- Unsupported basename (e.g., `notes.md`) → exit 0, no header injected
- Entity not found in DB → exit 0, no header
- Idempotent: run CLI twice on same file → second run succeeds, file content identical
- UUID mismatch: file has frontmatter with different UUID → exit 1

---

## Verification Checklist

**Gate condition:** Each item below MUST be confirmed before the implementation is considered complete. Items marked with a phase number should be verified at the end of that phase (not deferred to the end). Items without a phase number are final checks after Phase 7.

After all phases complete, verify:

- [ ] (Phase 4) All tests written through Phase 4 pass: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/test_frontmatter.py -v`
- [ ] (Phase 4) No regressions in pre-existing entity_registry tests (database, backfill, server helpers): `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- [ ] (Phase 4) TD-9 `created_at` immutability on merge is covered by a test in `TestWriteFrontmatter`
- [ ] (Phase 4) Divergence guard test (write path vs read path consistency) exists in `TestWriteFrontmatter`
- [ ] (Phase 6) SKILL.md modification is syntactically consistent with surrounding pseudocode
- [ ] (Phase 6) `./validate.sh` passes — no plugin portability violations
- [ ] (Phase 7) All 18 acceptance criteria (AC-1 through AC-18) have corresponding tests
- [ ] (Phase 7) `frontmatter_inject.py` is executable and handles all error cases with fail-open behavior
- [ ] (Final) No external dependencies added (stdlib + entity_registry only)
- [ ] (Final) All file I/O uses `encoding='utf-8'` (TD-10)
- [ ] (Final) Atomic writes use `tempfile.NamedTemporaryFile(delete=False, dir=same_dir)` + `os.rename()` (C2)
- [ ] (Final) Any new dependencies managed via `uv add` (not `pip install`). This feature requires no new external deps (C3), but if any tooling changes are needed, use `uv`.
