# Tasks: Markdown Entity File Header Schema

## Phase 1: Core Infrastructure

### Task 1.1.1: Create module scaffolding and constants
- [ ] Create `plugins/iflow/hooks/lib/entity_registry/frontmatter.py`
- [ ] Add imports: `os`, `re`, `tempfile`, `logging`, `datetime`
- [ ] Add logger: `logging.getLogger("entity_registry.frontmatter")`
- [ ] Define `FIELD_ORDER` tuple per TD-2
- [ ] Define `REQUIRED_FIELDS` frozenset
- [ ] Define `OPTIONAL_FIELDS` frozenset
- [ ] Define `ALLOWED_FIELDS` frozenset (`REQUIRED_FIELDS | OPTIONAL_FIELDS`)
- [ ] Define `ALLOWED_ARTIFACT_TYPES` frozenset
- [ ] Define `_UUID_V4_RE` compiled regex (no `re.IGNORECASE`)

**Done when:** Module imports without error; all 6 constants accessible; `_UUID_V4_RE.match("a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d")` returns a match object.

### Task 1.1.2: Create test file scaffolding
- [ ] Create `plugins/iflow/hooks/lib/entity_registry/test_frontmatter.py`
- [ ] Add imports: `pytest`, `os`, `tempfile`
- [ ] Add `from entity_registry.frontmatter import` statement for all public functions and constants
- [ ] Verify test file is discoverable by pytest

**Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/test_frontmatter.py --collect-only` succeeds.

### Task 1.2.1: Write tests for `_parse_block`
- [ ] Test: empty lines list returns empty dict
- [ ] Test: single valid `key: value` line returns `{"key": "value"}`
- [ ] Test: line with colon in value (`entity_type_id: feature:002-foo`) parses correctly
- [ ] Test: line without `: ` separator is ignored
- [ ] Test: line with invalid key chars (uppercase, digits, hyphens) is ignored
- [ ] Test: blank lines and comment lines are ignored
- [ ] Test: multiple valid lines all captured

**Done when:** 7 test cases exist and all FAIL (RED phase — `_parse_block` not yet implemented).

### Task 1.2.2: Implement `_parse_block`
- [ ] Implement `_parse_block(lines: list[str]) -> dict` per I7
- [ ] Use `line.partition(': ')` for splitting
- [ ] Use `re.fullmatch(r'[a-z_]+', key)` for key validation
- [ ] Return dict of valid key-value pairs

**Done when:** All Task 1.2.1 tests pass (GREEN phase).

### Task 1.3.1: Write tests for `_serialize_header`
- [ ] Test: dict with all required fields produces string with `---\n` delimiters, fields in FIELD_ORDER
- [ ] Test: dict with required + optional fields has optional after required, in FIELD_ORDER
- [ ] Test: dict with unknown field has it after all FIELD_ORDER fields
- [ ] Test: round-trip — serialize then parse back equals original (non-empty dict)
- [ ] Test: round-trip — single-field dict
- [ ] Test: round-trip — empty dict `{}` serializes as `---\n---\n`, parses back to `{}`

**Done when:** 6 test cases exist and all FAIL (RED phase).

### Task 1.3.2: Implement `_serialize_header`
- [ ] Implement `_serialize_header(header: dict) -> str` per I8
- [ ] Iterate FIELD_ORDER, then remaining keys
- [ ] Wrap with `---\n` delimiters

**Done when:** All Task 1.3.1 tests pass (GREEN phase).

---

## Phase 2: Validation & Build Functions

> **Parallel group:** Tasks 2.1.x and 2.2.x are sequential within each group, but 2.1.x is a prerequisite for 2.2.x.

### Task 2.1.1: Write tests for `validate_header`
- [ ] Test AC-5: all required fields with valid values returns empty list
- [ ] Test AC-6: missing each required field individually returns error with field name
- [ ] Test AC-7: invalid UUID format returns validation error
- [ ] Test: valid UUID (lowercase) returns no error
- [ ] Test: header dict with `entity_uuid` containing uppercase hex (e.g., `"A1B2C3D4-E5F6-4A7B-8C9D-0E1F2A3B4C5D"`) returns empty errors list — lowercased before regex match
- [ ] Test: invalid `artifact_type` returns validation error
- [ ] Test: each valid `artifact_type` returns no error
- [ ] Test: invalid `created_at` (not ISO 8601) returns validation error
- [ ] Test: valid `created_at` with timezone returns no error
- [ ] Test: unknown field present returns validation error
- [ ] Test: multiple errors all returned (no short-circuit)

**Done when:** 11 test cases exist and all FAIL (RED phase).

### Task 2.1.2: Implement `validate_header`
- [ ] Implement `validate_header(header: dict) -> list[str]` per I4
- [ ] Check required fields presence
- [ ] UUID regex check (`.lower()` before matching `_UUID_V4_RE`)
- [ ] `artifact_type` set membership check
- [ ] `datetime.fromisoformat()` for `created_at`
- [ ] Unknown field check against `ALLOWED_FIELDS`

**Done when:** All Task 2.1.1 tests pass (GREEN phase).

### Task 2.2.1: Write tests for `build_header`
- [ ] Test AC-10: valid required args returns dict passing `validate_header`
- [ ] Test AC-11: invalid `artifact_type` raises `ValueError`
- [ ] Test: invalid UUID raises `ValueError`
- [ ] Test: invalid `created_at` raises `ValueError`
- [ ] Test: valid required + valid optional kwargs all present in output
- [ ] Test: unknown optional kwarg raises `ValueError`

**Done when:** 6 test cases exist and all FAIL (RED phase).

### Task 2.2.2: Implement `build_header`
- [ ] Implement `build_header(entity_uuid, entity_type_id, artifact_type, created_at, **optional_fields) -> dict` per I3
- [ ] Construct dict from positional + kwargs
- [ ] Call `validate_header`, raise `ValueError` if errors

**Done when:** All Task 2.2.1 tests pass (GREEN phase).

---

## Phase 3: Read Function

### Task 3.1.1: Write tests for `read_frontmatter`
- [ ] Test AC-2: file with valid frontmatter returns dict with all fields
- [ ] Test AC-3: legacy file (no `---` on line 1) returns `None`
- [ ] Test AC-4: malformed frontmatter (opening `---` but no closing `---`) returns `None` + warning logged
- [ ] Test: empty file returns `None`
- [ ] Test: `---` on line 1 and `---` on line 2 (empty block) returns `{}` (empty dict, NOT None)
- [ ] Test: frontmatter with values containing `: ` parses correctly
- [ ] Test: binary content (null bytes in first 8192 bytes) returns `None` + warning
- [ ] Test: file does not exist returns `None` + warning
- [ ] Test: body content after frontmatter preserved (only header parsed)
- [ ] Test: large file with frontmatter — only header portion parsed

**Done when:** 10 test cases exist and all FAIL (RED phase).

### Task 3.1.2: Implement `read_frontmatter`
- [ ] Implement `read_frontmatter(filepath: str) -> dict | None` per I1
- [ ] Binary content guard: open binary, read 8192 bytes, check for `\x00`
- [ ] Open text (`encoding='utf-8'`), read line-by-line
- [ ] First line must be `---` (stripped) — else return None
- [ ] Accumulate lines until closing `---` or EOF
- [ ] If EOF without closing delimiter: warn, return None
- [ ] Pass accumulated lines to `_parse_block()`
- [ ] Handle `FileNotFoundError`: catch → `logger.warning("File not found: %s", filepath)` → return `None`. Do NOT re-raise — `read_frontmatter` is always non-raising (unlike `write_frontmatter` which re-raises as `ValueError` per I2)

**Done when:** All Task 3.1.1 tests pass (GREEN phase).

---

## Phase 4: Write Function

### Task 4.1.1: Write tests for `write_frontmatter` — core behavior
- [ ] Test AC-1: new file (no frontmatter) gets header prepended, body preserved
- [ ] Test AC-8: file with existing frontmatter gets header replaced, body preserved
- [ ] Test AC-15: idempotent — write twice with same header produces identical content
- [ ] Test AC-16: UUID mismatch raises `ValueError`
- [ ] Test AC-16 variant: UUID case mismatch (uppercase vs lowercase same UUID) does NOT raise
- [ ] Test AC-17: existing optional field + `None` in new headers removes field
- [ ] Test AC-18: existing optional field + `""` in new headers removes field
- [ ] Test TD-9: existing `created_at` preserved when new headers differ
- [ ] Test: file does not exist raises `ValueError`
- [ ] Test: merge-preserve — pre-write file via `write_frontmatter` with full valid header `{"entity_uuid": uuid, "entity_type_id": tid, "artifact_type": at, "created_at": ts, "feature_id": fid}`. Then call `write_frontmatter` with partial dict `{"entity_uuid": same_uuid, "artifact_type": same_at}` (intentionally omits required fields — relies on merge to preserve from existing). Assert `feature_id` still present in output
- [ ] Test: merge-add — pre-write file via `write_frontmatter` with full valid header `{"entity_uuid": uuid, "entity_type_id": tid, "artifact_type": at, "created_at": ts}`. Then call `write_frontmatter` with `{"entity_uuid": same_uuid, "artifact_type": same_at, "feature_id": new_fid}`. Assert `feature_id` now present in output (added from new call)
- [ ] Test: validation failure after merge raises `ValueError`, file unchanged

**Done when:** 12 test cases exist and all FAIL (RED phase).

### Task 4.1.2: Write tests for `write_frontmatter` — atomic write and guards
- [ ] Test AC-9: atomic write verification — mock `os.rename` to verify temp file in same dir
- [ ] Test: temp file cleanup on error (write fails before rename)
- [ ] Test: binary content guard — file with null bytes raises `ValueError`, file unchanged
- [ ] Test: divergence guard — `read_frontmatter(path)` returns same header as write's internal read
- [ ] Test: body starting with `---` (markdown horizontal rule) — read logic stops at correct delimiter
- [ ] Test: structural independence — patch `read_frontmatter` to raise `AssertionError`; call `write_frontmatter`; confirm no `AssertionError` raised (verifies internal read logic is independent of `read_frontmatter`)

**Done when:** 6 test cases exist and all FAIL (RED phase).

### Task 4.1.3: Implement `write_frontmatter`
- [ ] Implement `write_frontmatter(filepath: str, headers: dict) -> None` per I2
- [ ] Binary content guard (first 8192 bytes)
- [ ] Read existing file, detect frontmatter (own line-by-line logic, NOT calling `read_frontmatter`)
- [ ] UUID match check (`.lower()` both sides)
- [ ] Merge logic: existing ← new (None/empty deletion, `created_at` preserved per TD-9)
- [ ] Validate merged header
- [ ] Serialize: `_serialize_header(merged) + body` (no extra blank line)
- [ ] Atomic write: `NamedTemporaryFile(delete=False, dir=same_dir, suffix='.tmp')` + `os.rename`
- [ ] `finally` cleanup of temp file if rename didn't happen

**Done when:** All Task 4.1.1 and 4.1.2 tests pass (GREEN phase).

### Task 4.2.1: Write and verify round-trip tests
- [ ] Test AC-14: `read_frontmatter(path)` after `write_frontmatter(path, h)` returns dict equal to `h`
- [ ] Test: round-trip with all required fields only
- [ ] Test: round-trip with required + all optional fields
- [ ] Test: round-trip with values containing `: ` characters

**Done when:** 4 test cases pass (GREEN — depends on both read and write being implemented).

### Task 4.3: Run Phase 4 verification checkpoint
- [ ] Run: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/test_frontmatter.py -v`
- [ ] Verify all tests through Phase 4 pass
- [ ] Run: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- [ ] Verify no regressions in pre-existing entity_registry tests

**Done when:** Both test runs pass with 0 failures.

---

## Phase 5: CLI Script

### Task 5.1.1: Create CLI script scaffolding
- [ ] Create `plugins/iflow/hooks/lib/entity_registry/frontmatter_inject.py`
- [ ] Add imports: `sys`, `os`, `logging`, `datetime`, `sqlite3`
- [ ] Add `from entity_registry.frontmatter import build_header, write_frontmatter`
- [ ] Add `from entity_registry.database import EntityDatabase`
- [ ] Add logging config: `StreamHandler(sys.stderr)` with format `"%(levelname)s: %(message)s"`
- [ ] Define `ARTIFACT_BASENAME_MAP` constant (TD-6)
- [ ] Define `ARTIFACT_PHASE_MAP` constant (I5 step 7)

**Done when:** Run: `PYTHONPATH=plugins/iflow/hooks/lib plugins/iflow/.venv/bin/python -c "import entity_registry.frontmatter_inject"` — exits code 0, no `ImportError` or traceback.

### Task 5.1.2: Implement helper function stubs
- [ ] Add `_parse_feature_type_id(type_id: str) -> tuple[str, str | None]` with `raise NotImplementedError`
- [ ] Add `_extract_project_id(parent_type_id: str | None) -> str | None` with `raise NotImplementedError`

**Done when:** Run: `PYTHONPATH=plugins/iflow/hooks/lib plugins/iflow/.venv/bin/python -c "from entity_registry.frontmatter_inject import _parse_feature_type_id, _extract_project_id"` — exits code 0, no `ImportError` or traceback.

### Task 5.2.1: Write tests for CLI helpers (RED)
- [ ] Test: `ARTIFACT_BASENAME_MAP` contains all 6 supported basenames
- [ ] Test: `ARTIFACT_PHASE_MAP` contains all 6 artifact types
- [ ] Test: `_parse_feature_type_id("feature:002-some-slug")` returns `("002", "some-slug")`
- [ ] Test: `_parse_feature_type_id("feature:noseparator")` returns `("noseparator", None)`
- [ ] Test: `_parse_feature_type_id("feature:")` returns `("", None)` — empty string entity_id, no slug
- [ ] Test: `_extract_project_id("project:P001")` returns `"P001"`
- [ ] Test: `_extract_project_id("brainstorm:abc")` returns `None`
- [ ] Test: `_extract_project_id(None)` returns `None`

**Done when:** 8 test cases exist. Constant tests pass; function tests FAIL (RED — stubs raise NotImplementedError).

### Task 5.2.2: Implement helper functions (GREEN)
- [ ] Replace `_parse_feature_type_id` stub with full implementation
- [ ] Replace `_extract_project_id` stub with full implementation

**Done when:** Run: `PYTHONPATH=plugins/iflow/hooks/lib plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/test_frontmatter.py -k "test_parse_feature_type_id or test_extract_project_id or test_artifact" -v` — all 8 tests pass.

### Task 5.3.1: Pre-verify EntityDatabase API
- [ ] Run: `grep -n "def get_entity" plugins/iflow/hooks/lib/entity_registry/database.py` — confirm method exists
- [ ] Run: `grep -A 10 "def get_entity" plugins/iflow/hooks/lib/entity_registry/database.py | grep "_resolve_identifier"` — confirm get_entity's body delegates to _resolve_identifier
- [ ] If `get_entity()` only accepts UUID (not type_id), add a comment at the top of Task 5.3.3 noting the alternative call path

**Done when:** First grep returns the method definition line; second grep returns a line showing `_resolve_identifier` is called within get_entity's body.

### Task 5.3.2: Pre-verify EntityDatabase teardown API
- [ ] Read `database.py` for `close()` method, `__exit__` support, or other teardown
- [ ] Add a standalone comment block near the bottom of `test_frontmatter.py` (after the last existing test class): `# DB teardown: EntityDatabase.<method>() confirmed available (database.py:<line>)` — this comment will be superseded by the `TestFrontmatterInjectCLI` class definition in Task 7.1.1

**Done when:** Comment exists near the bottom of `test_frontmatter.py` specifying the teardown method name and its line number in `database.py`.

### Task 5.3.3: Implement main function
- [ ] Parse `sys.argv` — expect 3 args, print usage + exit 1 if wrong
- [ ] Derive `artifact_type` from basename via `ARTIFACT_BASENAME_MAP` — skip if not found
- [ ] Resolve DB path from `ENTITY_DB_PATH` env var
- [ ] Instantiate `EntityDatabase(db_path)` — catch `(sqlite3.Error, OSError)`, warn, exit 0
- [ ] Call `db.get_entity(feature_type_id)` — if None, warn, exit 0
- [ ] Extract UUID: `entity_record['uuid']`
- [ ] Parse feature_id and feature_slug from type_id via `_parse_feature_type_id`
- [ ] Derive project_id via `_extract_project_id`
- [ ] Derive phase from `ARTIFACT_PHASE_MAP`
- [ ] Build header via `build_header()`
- [ ] Call `write_frontmatter()` — catch `ValueError` (UUID mismatch) exit 1, `OSError` exit 0
- [ ] Add `if __name__ == "__main__":` guard

**Done when:** Run: `PYTHONPATH=plugins/iflow/hooks/lib plugins/iflow/.venv/bin/python plugins/iflow/hooks/lib/entity_registry/frontmatter_inject.py` — exits code 1 with usage to stderr. Run: `ENTITY_DB_PATH=/tmp/nonexistent.db PYTHONPATH=plugins/iflow/hooks/lib plugins/iflow/.venv/bin/python plugins/iflow/hooks/lib/entity_registry/frontmatter_inject.py /tmp/spec.md feature:001-test` — exits code 0 with WARNING to stderr. Full AC verification deferred to Phase 7.

---

## Phase 6: SKILL.md Integration

### Task 6.1: Add frontmatter injection pseudocode to SKILL.md
- [ ] Read `plugins/iflow/skills/workflow-transitions/SKILL.md`
- [ ] Locate `commitAndComplete` Step 1, find insertion point before `git add`
- [ ] Insert I6 pseudocode block (plugin root resolution, for-each artifact loop, shell invocation with `2>/dev/null || true`)
- [ ] Verify insertion is syntactically consistent with surrounding pseudocode

**Done when:** SKILL.md contains the frontmatter injection pseudocode in the correct location.

### Task 6.2: Validate SKILL.md modification
- [ ] Run `./validate.sh`
- [ ] Confirm no plugin portability violations flagged for the modified SKILL.md

**Done when:** `validate.sh` passes with 0 violations.

---

## Phase 7: Integration Tests

### Task 7.1.1: Set up integration test infrastructure
- [ ] Create `TestFrontmatterInjectCLI` class in `test_frontmatter.py`
- [ ] Add fixture: create temp dir with file-based test DB (`EntityDatabase(str(tmp_path / "test.db"))`)
- [ ] Add fixture: create temp artifact file (`spec.md` with markdown content)
- [ ] Add DB teardown: use `db.close()` if available, otherwise `with`-block via `__exit__`, otherwise `del db` — use method confirmed in Task 5.3.2
- [ ] Add subprocess invocation helper: `subprocess.run([sys.executable, script_path, ...], env={PYTHONPATH, ENTITY_DB_PATH})` where `PYTHONPATH = str(Path(__file__).parent.parent)` (resolves to `hooks/lib/` — the test file is in `hooks/lib/entity_registry/`, so `parent.parent` is `hooks/lib/`)

**Done when:** Test class exists with fixtures; subprocess invocation runs without import errors.

### Task 7.2.1: Write AC-12 integration test
- [ ] Register entity in test DB with known UUID
- [ ] Create `spec.md` with plain markdown (no frontmatter)
- [ ] Invoke `frontmatter_inject.py` via subprocess
- [ ] Assert exit code 0
- [ ] Read artifact → `read_frontmatter()` returns dict with correct `entity_uuid`, `entity_type_id`, `artifact_type`, valid `created_at`

**Done when:** AC-12 test passes.

### Task 7.3.1: Write AC-13 integration test
- [ ] Set `ENTITY_DB_PATH` to nonexistent path
- [ ] Invoke `frontmatter_inject.py` via subprocess
- [ ] Assert exit code 0
- [ ] Assert stderr contains warning
- [ ] Assert artifact file unchanged

**Done when:** AC-13 test passes.

### Task 7.4.1: Write additional integration edge case tests
- [ ] Test: unsupported basename (`notes.md`) — exit 0, no header
- [ ] Test: entity not found in DB — exit 0, no header
- [ ] Test: idempotent — run CLI twice, second run succeeds, file identical
- [ ] Test: UUID mismatch — file has frontmatter with different UUID — exit 1

**Done when:** 4 edge case tests pass.

### Task 7.5: Run final verification
- [ ] Run full test suite: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/test_frontmatter.py -v`
- [ ] Run regression check: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- [ ] Run `./validate.sh`
- [ ] Verify AC coverage: `grep -c "AC-" plugins/iflow/hooks/lib/entity_registry/test_frontmatter.py` returns >= 18 (each test function has `# AC-N` comment)
- [ ] Verify no external dependencies added (stdlib + entity_registry only)
- [ ] Verify all `open()` calls use `encoding='utf-8'` (TD-10)
- [ ] Verify atomic writes use `NamedTemporaryFile(delete=False, dir=same_dir) + os.rename()` (C2)

**Done when:** All checks pass; feature is implementation-ready.

---

## Dependency Graph

```
Phase 1 (sequential):
  1.1.1 ──→ 1.1.2 ──→ 1.2.1 ──→ 1.2.2 ──→ 1.3.1 ──→ 1.3.2

Phase 2 (sequential, depends on Phase 1):
  2.1.1 ──→ 2.1.2 ──→ 2.2.1 ──→ 2.2.2

Phase 3 (depends on Phase 1):
  3.1.1 ──→ 3.1.2

Phase 4 (depends on Phases 1-3):
  4.1.1 ──→ 4.1.2 ──→ 4.1.3 ──→ 4.2.1 ──→ 4.3

Phase 5 (depends on Phases 1-4):
  5.1.1 ──→ 5.1.2 ──→ 5.2.1 ──→ 5.2.2
  5.3.1 (parallel with 5.1.x)
  5.3.2 (parallel with 5.1.x)
  5.3.3 (depends on 5.2.2, 5.3.1, 5.3.2)

Phase 6 (depends on Phase 5):
  6.1 ──→ 6.2

Phase 7 (depends on all prior phases):
  7.1.1 ──→ 7.2.1 ──→ 7.3.1 ──→ 7.4.1 ──→ 7.5
```

## Summary

- **Total tasks:** 36
- **Phases:** 7
- **Parallel groups:** 1 (Tasks 5.3.1/5.3.2 run parallel with 5.1.x)
