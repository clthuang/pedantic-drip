# Design: Markdown Entity File Header Schema

## Prior Art Research

### Codebase Findings

1. **No existing YAML parser** — zero `import yaml` occurrences in production code. The only frontmatter-like parsing is `read_local_md_field` in `common.sh:88-103` (shell, uses `grep "^${field}:" | sed`). The custom parser approach (spec C1) is consistent with this convention.

2. **Atomic write pattern** — `write_hook_state` in `common.sh:122-135` writes to `${file}.tmp` then `mv`. Same pattern prescribed by spec C2 for Python.

3. **EntityDatabase conventions** — SQLite WAL-mode, `INSERT OR IGNORE` idempotency, JSON metadata blob, `row_factory = sqlite3.Row`. Connection setup: FK enforcement, 5s busy_timeout, 8MB cache. UUID v4 regex already defined at `database.py:11-13`.

4. **`_resolve_identifier` method** — `database.py:273-303`. Accepts both UUID and type_id, returns `(uuid, type_id)` tuple. Despite being prefixed with `_` (private), it's the only path to resolve a type_id to a UUID. The CLI script needs this for R13.

5. **Error handling** — `_read_file`/`_read_json` in `backfill.py` return `None` on failure (silent-skip pattern). Logging uses `print(..., file=sys.stderr)` with prefixes throughout the codebase.

6. **Test conventions** — `tmp_path` fixture, `EntityDatabase(":memory:")`, class-based grouping with `Test*` prefixes. Tests import from `entity_registry.database`.

7. **Import convention** — `from entity_registry.database import EntityDatabase` (see `backfill.py:15`). Module is on `PYTHONPATH` via plugin venv.

8. **type_id format** — `"{entity_type}:{entity_id}"` (see `database.py:344`). Maps to frontmatter `entity_type_id` field per spec R3/R13.

### External Findings

1. **Frontmatter delimiters** — Jekyll, Hugo, and python-frontmatter all use `---` as opening/closing delimiter. File must start with `---` at byte offset 0. Standard practice.

2. **stdlib-only parsing** — `line.partition(': ')` is the idiomatic stdlib approach for splitting on first occurrence. More readable than `line.split(': ', 1)` and handles edge cases (returns `('line', '', '')` when delimiter not found).

3. **Atomic writes** — `tempfile.NamedTemporaryFile(delete=False, dir=same_dir)` + `os.replace()` is preferred over `os.rename()` on Python 3.3+ because `os.replace()` handles the case where the target already exists (replaces it atomically). However, spec C2 locks `os.rename()` — POSIX-only assumption means this is fine.

4. **Prepending content** — read-modify-write pattern is the only correct way to prepend to files. Never use `r+` mode with seek. Read entire file, write new header + body to temp file, rename.

### Design Decision: `os.rename()` vs `os.replace()`

The spec locks `os.rename()` (C2). On POSIX, `os.rename()` atomically replaces an existing file. Since POSIX is the only supported platform (C2 explicit), `os.rename()` is sufficient. No deviation needed.

### Design Decision: Logging

Spec R8 locks Python stdlib `logging` module with logger name `entity_registry.frontmatter`. This diverges from the codebase convention (`print(stderr)`). The design follows the spec — the `logging` module is the correct choice for a library module that may be imported by multiple callers. The CLI script (`frontmatter_inject.py`) can configure a stderr handler at its entry point.

---

## Architecture Overview

### Component Diagram

```
┌─────────────────────────────────────────────────┐
│ Workflow Integration Layer                       │
│                                                  │
│  SKILL.md commitAndComplete                      │
│    └── shell invocation ──┐                      │
│                           ▼                      │
│  ┌────────────────────────────────────────────┐  │
│  │ frontmatter_inject.py  (CLI entry point)   │  │
│  │  - Arg parsing (artifact_path, type_id)    │  │
│  │  - DB lookup via EntityDatabase            │  │
│  │  - Artifact type derivation from basename  │  │
│  │  - Delegates to frontmatter.py             │  │
│  │  - Exit 0 always (fail-open)               │  │
│  └──────────────┬─────────────────────────────┘  │
│                 │ imports                         │
│                 ▼                                 │
│  ┌────────────────────────────────────────────┐  │
│  │ frontmatter.py  (utility library)          │  │
│  │                                            │  │
│  │  read_frontmatter(filepath) → dict | None  │  │
│  │  write_frontmatter(filepath, headers)      │  │
│  │  build_header(...) → dict                  │  │
│  │  validate_header(header) → list[str]       │  │
│  │                                            │  │
│  │  Internal: _parse_block, _serialize_header │  │
│  └────────────────────────────────────────────┘  │
│                 │ imports                         │
│                 ▼                                 │
│  ┌────────────────────────────────────────────┐  │
│  │ entity_registry.database.EntityDatabase    │  │
│  │  (existing — no modifications)             │  │
│  └────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### Data Flow

```
1. commitAndComplete step in SKILL.md
   │
   ├── Resolves plugin root (two-location Glob)
   ├── Invokes: <plugin_root>/.venv/bin/python frontmatter_inject.py <path> <type_id>
   │
   ▼
2. frontmatter_inject.py (CLI)
   │
   ├── Parse sys.argv: artifact_path, feature_type_id
   ├── Derive artifact_type from basename (spec R15)
   │   └── Skip if basename not in {spec.md, design.md, plan.md, tasks.md, retro.md, prd.md}
   ├── Connect to EntityDatabase (ENTITY_DB_PATH env var, fallback path)
   ├── Query entity by type_id → get entity_uuid
   │   └── If not found: warn + exit 0
   ├── Build header dict via build_header()
   ├── Call write_frontmatter(artifact_path, header)
   │   └── If ValueError (UUID mismatch): warn + exit 1 → workflow fail-open
   └── Exit 0

3. frontmatter.py (library)
   │
   ├── read_frontmatter: parse existing block (if any)
   ├── write_frontmatter: merge → validate → atomic write
   └── validate_header: schema validation
```

### File Locations

| File | Path | Purpose |
|------|------|---------|
| frontmatter.py | `plugins/iflow/hooks/lib/entity_registry/frontmatter.py` | Utility library |
| frontmatter_inject.py | `plugins/iflow/hooks/lib/entity_registry/frontmatter_inject.py` | CLI script |
| test_frontmatter.py | `plugins/iflow/hooks/lib/entity_registry/test_frontmatter.py` | Tests |
| SKILL.md | `plugins/iflow/skills/workflow-transitions/SKILL.md` | Pseudocode block addition |

---

## Components

### C1: frontmatter.py — Utility Library

**Responsibility:** Read, write, validate, and build YAML frontmatter headers for markdown files.

**Dependencies:** Python stdlib only (`os`, `re`, `tempfile`, `logging`, `datetime`).

**Internal helpers:**

- `_parse_block(lines: list[str]) -> dict` — Parse the already-extracted lines between frontmatter delimiters. Returns dict of key-value pairs (may be empty). The caller (`read_frontmatter` / `write_frontmatter`) handles delimiter detection and line-by-line I/O.
- `_serialize_header(header: dict) -> str` — Serialize a header dict to a YAML frontmatter string (with `---` delimiters), respecting field ordering per R5.

**Logger:** `logging.getLogger("entity_registry.frontmatter")` per spec R8.

### C2: frontmatter_inject.py — CLI Script

**Responsibility:** CLI entry point for workflow integration. Bridges the SKILL.md shell invocation to the frontmatter library and entity database.

**Dependencies:** `frontmatter.py` (sibling module), `entity_registry.database.EntityDatabase`.

**Constants (owned by this module, not by frontmatter.py):**

- `ARTIFACT_BASENAME_MAP` — maps basename to artifact_type (TD-6): `{"spec.md": "spec", "design.md": "design", ...}`
- `ARTIFACT_PHASE_MAP` — maps artifact_type to workflow phase (I5 step 7): `{"spec": "specify", "design": "design", ...}`

**Error handling:** All exceptions caught at top level — log warning to stderr, exit 0 (fail-open per R12). Only exception: UUID mismatch from `write_frontmatter` causes exit 1 (workflow fail-open behavior still applies because the SKILL.md checks for non-zero exit).

### C3: test_frontmatter.py — Test Suite

**Responsibility:** Unit tests (AC-1 through AC-11, AC-14 through AC-18) and integration tests (AC-12, AC-13).

**Test organization:** Class-based grouping matching codebase convention:
- `TestReadFrontmatter` — AC-2, AC-3, AC-4, edge cases
- `TestWriteFrontmatter` — AC-1, AC-8, AC-9, AC-15, AC-16, AC-17, AC-18, plus TD-9 (`created_at` preserved from existing header when new headers dict contains a different `created_at` — no AC number assigned but critical for merge correctness)
- `TestBuildHeader` — AC-10, AC-11
- `TestValidateHeader` — AC-5, AC-6, AC-7
- `TestRoundTrip` — AC-14
- `TestFrontmatterInjectCLI` — AC-12, AC-13

### C4: SKILL.md Modification

**Responsibility:** Pseudocode block addition to `commitAndComplete` that invokes `frontmatter_inject.py` before the `git add` step. The addition is LLM-interpreted pseudocode (matching the existing SKILL.md style), not literal bash.

---

## Technical Decisions

### TD-1: Custom YAML Parser Algorithm

**Decision:** Split on first `: ` (colon-space) per spec C1. Use `line.partition(': ')` for clarity.

**Rationale:** `str.partition()` returns a 3-tuple `(before, sep, after)`. When separator is not found, `sep` is `''`, making the "not found" check trivial (`if sep`). This is more explicit than `str.split(': ', 1)` which returns a 1-element list when not found.

**Key validation:** Key portion must match `^[a-z_]+$`. This is checked with `re.fullmatch()` (avoids needing `^` and `$` anchors explicitly — `fullmatch` implies both).

### TD-2: Field Ordering Strategy

**Decision:** Define `FIELD_ORDER` as a tuple constant listing all fields in R3+R4 order. `_serialize_header` iterates this tuple and includes each field present in the header dict. Unknown fields (if any survive validation) are appended at the end.

```python
FIELD_ORDER = (
    "entity_uuid", "entity_type_id", "artifact_type", "created_at",
    "feature_id", "feature_slug", "project_id", "phase", "updated_at",
)
```

### TD-3: Atomic Write Implementation

**Decision:** Use `tempfile.NamedTemporaryFile(mode='w', dir=target_dir, delete=False, suffix='.tmp')` for the temp file, then `os.rename(tmp.name, target_path)`.

**Rationale:**
- `dir=target_dir` ensures same filesystem (required for atomic `os.rename`)
- `delete=False` keeps the file after close so `os.rename` can move it
- `suffix='.tmp'` makes temp files identifiable if cleanup is needed
- Cleanup in `finally` block: if rename hasn't happened, `os.unlink(tmp.name)`

### TD-4: Binary Content Guard

**Decision:** Read first 8192 bytes, check for `\x00` (null byte). If found, return `None` without parsing.

**Rationale:** Simple, fast, no external dependencies. 8192 bytes is enough to detect binary files (most binary formats have null bytes in their magic numbers/headers).

### TD-5: DB Path Resolution

**Decision:** `os.environ.get("ENTITY_DB_PATH", os.path.expanduser("~/.claude/iflow/entities/entities.db"))`.

**Rationale:** Consistent with how the entity server resolves the DB path. `ENTITY_DB_PATH` env var is documented in CLAUDE.md.

### TD-6: Artifact Type Derivation

**Decision:** Dict lookup on `os.path.basename(filepath)`:

```python
ARTIFACT_BASENAME_MAP = {
    "spec.md": "spec",
    "design.md": "design",
    "plan.md": "plan",
    "tasks.md": "tasks",
    "retro.md": "retro",
    "prd.md": "prd",
}
```

Exact, case-sensitive basename match per R15. Files not in the map are skipped with a warning.

### TD-7: Logging Configuration

**Decision:** The library module (`frontmatter.py`) uses `logging.getLogger("entity_registry.frontmatter")` and does NOT configure handlers (follows Python logging best practice — library modules should never call `basicConfig` or add handlers).

The CLI script (`frontmatter_inject.py`) configures a `StreamHandler(sys.stderr)` at its entry point with format `"%(levelname)s: %(message)s"` — minimal, stderr-only, matching the codebase convention for CLI output.

### TD-8: Merge Semantics for write_frontmatter

**Decision:** When updating existing frontmatter with matching UUID:
1. Start with existing header dict
2. For each key in new `headers` dict:
   - If value is `None` or `""` → remove key from merged dict (explicit deletion per R9)
   - Otherwise → overwrite value
3. Existing keys not in `headers` → preserved
4. Run `validate_header` on merged result → abort if invalid

This ensures R9 merge behavior, R6 immutability enforcement, and R11 validation gate.

### TD-9: `created_at` Immutability on Merge

**Decision:** When merging headers in `write_frontmatter` (UUID matches), `created_at` is preserved from the existing header. If the new `headers` dict contains a different `created_at`, the existing value takes precedence silently (no error). This prevents accidental timestamp drift.

**Rationale:** `created_at` records when the file was first created. Like `entity_uuid`, it should never change after initial write. Unlike `entity_uuid` (which raises `ValueError` on mismatch per R6), `created_at` mismatch is a silent keep-existing because callers commonly pass `datetime.now()` without checking if the file already has a `created_at`.

### TD-10: File Encoding

**Decision:** All `open()` calls use `encoding='utf-8'` explicitly.

**Rationale:** Markdown files are UTF-8 by convention. Python's default encoding depends on the locale, which varies across environments. Explicit UTF-8 avoids locale-dependent behavior for files containing Unicode characters (e.g., feature names with accented characters).

---

## Risks

### Risk 1: `_resolve_identifier` Coupling

**Risk:** The CLI script relies on `EntityDatabase._resolve_identifier` (a private method) via `get_entity(type_id)` to look up entities by type_id. The spec phase-reviewer flagged this (phaseReview concern 1).

**Mitigation:** The CLI does NOT call `_resolve_identifier` directly. It calls `get_entity(type_id)` which is a public method that internally uses `_resolve_identifier`. This is the intended public API surface. No fragile coupling.

**Verification note:** Implementer must confirm `get_entity(type_id)` accepts a non-UUID string and internally delegates to `_resolve_identifier`. If the method signature only accepts UUID, the CLI will need to call `_resolve_identifier` directly or a thin wrapper will be needed.

### Risk 2: SKILL.md Integration Ambiguity

**Risk:** The exact insertion point within `commitAndComplete` is ambiguous (phaseReview concern 2). The pseudocode has Step 1 (git add/commit/push) and Step 2 (update state).

**Mitigation:** The frontmatter injection must run BEFORE `git add` — it modifies artifact files that need to be included in the commit. The shell invocation is inserted as the first operation in Step 1, before the `git add` line.

### Risk 3: Race Condition on Concurrent Writes

**Risk:** If two processes write frontmatter to the same file simultaneously, one write could be lost.

**Mitigation:** This is a non-issue in practice — iflow workflows are single-agent-at-a-time per feature branch. The atomic write (temp file + rename) prevents partial writes but does not prevent lost updates from concurrent full writes. Acceptable for the intended use case.

### Risk 4: Large File Performance

**Risk:** `read_frontmatter` reads the entire file content to find the frontmatter block.

**Mitigation:** Read only enough to find the frontmatter block. Read line-by-line: if first line is not `---`, return None immediately. Otherwise, read lines until closing `---` is found or EOF. For `write_frontmatter`, the full file must be read anyway (to preserve body content), so no optimization is possible there. For `read_frontmatter`, line-by-line reading avoids loading multi-megabyte files into memory.

---

## Interfaces

### I1: `read_frontmatter(filepath: str) -> dict | None`

**Contract:**
- Input: absolute or relative path to a markdown file
- Output: dict of header fields, or `None`
- Raises: no exceptions (all errors → `None` + log warning)

**Behavior matrix:**

| Scenario | Return | Log |
|----------|--------|-----|
| File has valid frontmatter with fields | `{"entity_uuid": "...", ...}` | — |
| File has valid frontmatter, empty block | `{}` | — |
| File has no `---` on line 1 | `None` | — |
| File has opening `---` but no closing `---` | `None` | warning: malformed |
| File does not exist | `None` | warning: file not found |
| File has null bytes in first 8192 bytes | `None` | warning: binary content |
| File is empty | `None` | — |

**Implementation detail:** Open file with `encoding='utf-8'`. Binary content guard: read first 8192 bytes in binary mode, check for `\x00`. If binary, return None + warning. File is opened twice — once in binary mode for the null-byte guard, once in text mode for line-by-line parsing. TOCTOU between the two opens is acceptable given single-agent-per-branch execution model (Risk 3). Otherwise, read line-by-line: first line must be exactly `---\n` (or `---` at EOF). Accumulate lines (stripping trailing newlines via `line.rstrip('\n')`) until another `---` line or EOF. If EOF reached without closing delimiter → malformed, return None + warning. An empty file (zero bytes) has no first line, so it returns None immediately (same codepath as "first line is not `---`"). Pass accumulated lines (between delimiters, newline-stripped) to `_parse_block()` for key-value parsing.

### I2: `write_frontmatter(filepath: str, headers: dict) -> None`

**Contract:**
- Input: file path and header dict
- Output: None (file is modified in-place atomically)
- Raises: `ValueError` if UUID mismatch, validation failure, or file not found (`FileNotFoundError` is caught and re-raised as `ValueError` for a uniform exception interface)

**Behavior matrix:**

| Scenario | Behavior |
|----------|----------|
| File has no frontmatter | Prepend header block, preserve body |
| File has frontmatter, same UUID | Merge headers (preserving `created_at` per TD-9), validate, write |
| File has frontmatter, different UUID | Raise `ValueError` |
| Headers fail validation after merge | Raise `ValueError`, file unchanged |
| Header value is `None` or `""` | Remove field from merged result |
| File does not exist | Raise `ValueError('File not found: {path}')` |

**Write sequence:**
1. Open file with `encoding='utf-8'` — catch `FileNotFoundError`, raise `ValueError`
2. Read existing file content
3. If frontmatter exists: extract existing header, check UUID match
4. Merge: existing ← new headers (with None/empty deletion, `created_at` preserved from existing per TD-9)
5. Validate merged header → abort on failure
6. Serialize: `_serialize_header(merged)` + body content
7. Write to temp file in same directory (with `encoding='utf-8'`)
8. `os.rename(temp, target)`
9. Cleanup temp file in `finally` block if rename didn't happen

### I3: `build_header(entity_uuid: str, entity_type_id: str, artifact_type: str, created_at: str, **optional_fields) -> dict`

**Contract:**
- Input: required fields as positional args, optional fields as kwargs
- Output: validated header dict
- Raises: `ValueError` if any input is invalid

**Validation:**
- `entity_uuid` must match UUID v4 regex
- `artifact_type` must be in `{"spec", "design", "plan", "tasks", "retro", "prd"}`
- `created_at` must be valid ISO 8601 (checked via `datetime.fromisoformat()`)
- `optional_fields` keys must be in the R4 set
- Calls `validate_header` on the result → raises on failure

### I4: `validate_header(header: dict) -> list[str]`

**Contract:**
- Input: header dict
- Output: list of error strings (empty = valid)
- Raises: no exceptions

**Checks (ordered):**
1. Required fields present: `entity_uuid`, `entity_type_id`, `artifact_type`, `created_at`
2. `entity_uuid` matches UUID v4 regex (case-insensitive)
3. `artifact_type` in allowed set
4. `created_at` parseable by `datetime.fromisoformat()`
5. No unknown fields (not in R3 + R4 union)

**Returns:** All errors found (does not short-circuit on first error).

### I5: `frontmatter_inject.py` CLI Interface

**Usage:** `python frontmatter_inject.py <artifact_path> <feature_type_id>`

**Arguments:**
- `artifact_path`: Path to the markdown artifact file
- `feature_type_id`: The entity type_id (e.g., `feature:002-markdown-entity-file-header-sc`)

**Exit codes:**
- `0`: Success (header injected) or graceful skip (entity not found, unsupported basename, DB unavailable)
- `1`: UUID mismatch (file has frontmatter with different UUID)

**Stderr output:** Warnings and errors via logging (StreamHandler on stderr).

**Sequence:**
1. Parse `sys.argv` — if wrong arg count, print usage, exit 1
2. Derive `artifact_type` from `os.path.basename(artifact_path)` using `ARTIFACT_BASENAME_MAP`
   - If not in map: warn "Unsupported artifact basename", exit 0
3. Resolve DB path from `ENTITY_DB_PATH` env var (fallback `~/.claude/iflow/entities/entities.db`)
4. Instantiate `EntityDatabase(db_path)` — if fails, warn, exit 0
5. Call `db.get_entity(feature_type_id)` — if None, warn "Entity not found", exit 0
6. Extract `entity_uuid` from entity dict
7. Build header via `build_header(entity_uuid, feature_type_id, artifact_type, now_iso, **optional_fields)`
   - `created_at`: `datetime.now(timezone.utc).isoformat()` (only used for new headers; existing `created_at` preserved on merge per TD-9)
   - `feature_id`: parsed from `feature_type_id` — split on `:` to get `feature:{id}-{slug}`, then extract `{id}` (digits before first `-`)
   - `feature_slug`: parsed from `feature_type_id` — remainder after `{id}-`
   - `project_id`: parse entity DB record's `parent_type_id` string — split on `:` to get `(entity_type, entity_id)`. If `entity_type` is `project`, use `entity_id` as `project_id` (e.g., `project:P001` → `P001`). No second DB query needed — `type_id` format is `entity_type:entity_id` by construction. Omitted if no project parent
   - `phase`: derived from `artifact_type` using `ARTIFACT_PHASE_MAP` constant: `{'spec': 'specify', 'design': 'design', 'plan': 'create-plan', 'tasks': 'create-tasks', 'retro': 'finish', 'prd': 'brainstorm'}`
   - No `.meta.json` reading needed — all data sourced from entity DB record and CLI arguments
8. Call `write_frontmatter(artifact_path, header)`
   - If `ValueError` (UUID mismatch): log error, exit 1
9. Exit 0

### I6: SKILL.md Integration Point

**Location:** `plugins/iflow/skills/workflow-transitions/SKILL.md`, within `commitAndComplete` Step 1, before the `git add` line.

**entity_type_id derivation:** The SKILL.md pseudocode already has access to the feature's `.meta.json` (read during `validateAndSetup`). The `entity_type_id` is constructed as `feature:{id}-{slug}` from the `.meta.json` `id` and `slug` fields. This matches the `type_id` format in `database.py:344`.

**Addition (LLM-interpreted pseudocode, matching existing SKILL.md style):**
```
# Frontmatter injection (before git add):
# For each artifact file being committed, invoke frontmatter_inject.py
# to embed entity identity headers. Resolve plugin root using the
# two-location pattern (primary: ~/.claude/plugins/cache, fallback: plugins/iflow).
# Construct entity_type_id as "feature:{id}-{slug}" from .meta.json.
# Suppress stderr (2>/dev/null) and ignore non-zero exit (|| true) — fail-open.
#
# Shell equivalent:
#   PLUGIN_ROOT=$(ls -d ~/.claude/plugins/cache/*/iflow*/*/hooks 2>/dev/null | head -1 | xargs dirname)
#   if [ -z "$PLUGIN_ROOT" ]; then PLUGIN_ROOT="plugins/iflow"; fi  # Fallback (dev workspace)
#   for artifact in {artifacts}; do
#     "$PLUGIN_ROOT/.venv/bin/python" "$PLUGIN_ROOT/hooks/lib/entity_registry/frontmatter_inject.py" \
#       "$artifact" "feature:{id}-{slug}" 2>/dev/null || true
#   done
```

**Key behaviors:**
- This is pseudocode that the LLM agent executing `commitAndComplete` interprets and translates to shell commands
- `2>/dev/null` suppresses stderr to prevent corrupting JSON hook output
- `|| true` ensures non-zero exit doesn't abort the commit step (fail-open)
- Iterates over all artifacts being committed (e.g., `spec.md`, `design.md`)
- Plugin root resolution uses two-location pattern per CLAUDE.md convention
- `entity_type_id` is derived from `.meta.json` fields already available in the workflow context

### I7: Internal Helper — `_parse_block(lines: list[str]) -> dict`

**Contract:**
- Input: list of lines extracted between frontmatter `---` delimiters (excluding the delimiters themselves)
- Output: dict of key-value pairs (may be empty if no lines match the key-value pattern)
- Does NOT handle delimiter detection — that is the caller's responsibility (`read_frontmatter` and `write_frontmatter` handle line-by-line I/O and delimiter detection)

**Parsing algorithm:**
1. Initialize empty dict
2. For each line: `key, sep, value = line.partition(': ')`
   - If `sep` and `re.fullmatch(r'[a-z_]+', key)`: add `key: value` to dict
   - Else: silently ignore
3. Return dict

**Caller contract:** Lines passed to `_parse_block` must have trailing newlines already stripped (e.g., via `line.rstrip('\n')` during accumulation in `read_frontmatter`). This keeps `_parse_block` pure (no I/O concerns) and preserves round-trip fidelity (spec C4) — values are stored exactly as written.

### I8: Internal Helper — `_serialize_header(header: dict) -> str`

**Encoding note:** All file I/O uses `encoding='utf-8'` per TD-10.

**Contract:**
- Input: header dict (assumed valid)
- Output: string with `---\n{fields}\n---\n` format

**Serialization:**
1. Start with `---\n`
2. For each field in `FIELD_ORDER`: if present in header, append `{key}: {value}\n`
3. For any remaining keys not in `FIELD_ORDER`: append `{key}: {value}\n`
4. End with `---\n`
