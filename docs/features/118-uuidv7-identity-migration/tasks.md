# Tasks: UUIDv7 Identity Migration

Execution: STRICTLY SERIAL, in order (tasks 2 and 3 edit `database.py`; the doctor capture brackets task 3). Concurrency: NONE — task 4 COULD run parallel to 1-2 (new files only, zero collisions); deliberately forgone: for a 5-task serial chain the dispatch overhead outweighs the slot, and serial keeps the doctor bracket unambiguous.

All bare `*.py` paths are relative to `plugins/pd/hooks/lib/entity_registry/` unless stated otherwise. All `pytest` invocations mean `plugins/pd/.venv/bin/python -m pytest` (the venv interpreter is the thing under test for the 3.14 floor — a wrong-interpreter pytest masks exactly the regression task 1 exists to catch).

## Task 1: Python 3.14 floor + uuid7 helper

**Files:** `plugins/pd/pyproject.toml`, `plugins/pd/uv.lock` (regenerated), NEW `plugins/pd/hooks/lib/entity_registry/uuid7.py`, NEW `.../test_uuid7.py`

**Do:**
1. `pyproject.toml:4` → `requires-python = ">=3.14"`; run `uv lock` from `plugins/pd/` (best-effort per plan — if index resolution unavailable, edit `uv.lock:3` directly and note it; not a greenness gate).
2. `uuid7.py`: `_require_uuid7(mod=uuid)` → `RuntimeError` naming the 3.14 floor if `uuid7` absent; called at module top; `generate_uuid7() -> str` = `str(uuid.uuid7())`.
3. `test_uuid7.py`: (a) 1000 mints — every version nibble `7`, list equals its sorted self; (b) `_require_uuid7(mod=types.SimpleNamespace())` raises `RuntimeError` with `"3.14"` in the message (design tests #7-8).

**Verify:** `pytest test_uuid7.py` green. `grep -n "requires-python" plugins/pd/pyproject.toml plugins/pd/uv.lock` → both `>=3.14`.

## Task 2: `_UUID_RE` widening + full rename sweep + reversal re-scope

**Files:** `database.py`, `frontmatter.py`, `test_database.py`, `test_server_helpers.py`, `test_frontmatter.py`, `test_entity_server.py`

**Do:**
1. `database.py:25-27`: rename `_UUID_V4_RE` → `_UUID_RE`, nibble `4` → `[1-7]`; update the comment above (no longer v4-only; R11 lowercase rule unchanged). Same at `frontmatter.py:57-59`.
2. Rename at `database.py:6054`, `:6283`, `frontmatter.py:118`.
3. Sweep EVERY `_UUID_V4_RE` reference in `test_database.py` (imports `:17/:178/:237`; all `.match(...)` usages incl. variant test `:2113`), `test_server_helpers.py` (`:11/:501/:1018`), `test_frontmatter.py` (`:25` + usages).
4. Re-scope the 5 reversal tests: `TestResolveIdentifierBoundary` v1/v3/v5 tests → assert `_UUID_RE.match(...)` SUCCEEDS (rename tests to `..._matched_as_uuid`, update docstrings: versions 1-7 accepted, uuid-vs-type_id routing now version-agnostic); `TestValidateHeaderUUIDBoundary` v3/v5 tests → assert `validate_header` returns NO uuid error (rename to `test_validate_header_uuid_version_digit_3_accepted` / `..._digit_5_accepted` + docstrings likewise). Variant-nibble tests in both files unchanged.
5. Sweep ALL lying v4 labels (plan step 2's full enumeration): failure messages `test_database.py:671/:685/:803/:1910`, the DIFFERENT template `:721`, message `:4099`; test name `test_register_returns_uuid_v4_format` `:1907` + docstrings `:800`/`:1908`; class docstring `test_frontmatter.py:1131`; comments `:220`/`:2179` — version-agnostic wording.
6. `test_entity_server.py:19`: widen local leak-guard nibble to `[1-7]` (name unchanged).

**Verify:** `grep -rn "_UUID_V4_RE" plugins/pd/hooks/lib/` → only the `test_entity_server.py` local def+use. Case-insensitive label sweep `grep -rniE "uuid[_ ]v4|valid v4|v4[_ ](format|pattern|regex)" plugins/pd/hooks/lib/entity_registry/*.py` → zero hits outside the `test_entity_server.py` leak-guard (catches skipped do-item-5 targets mechanically, INCLUDING the underscored test name `:1907` and the pluralized comment `:2179` that a literal `"UUID v4"` grep misses — messages never render on a green run). Full `pytest plugins/pd/hooks/lib/entity_registry/` green (mints still v4; widened regex accepts both — step independently green).

## Task 3: Rewire 4 mints + round-trip + residual scan (doctor-bracketed)

**Files:** `database.py`, `project_identity.py`, `test_database.py` (round-trip + scan tests), NEW `docs/features/118-uuidv7-identity-migration/.doctor-before.txt` / `.doctor-after.txt`

**Do:**
1. BEFORE any code change — the DB-aware doctor, NOT `scripts/doctor.sh` (environmental only, never reads the entities DB): `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m doctor --entities-db ~/.claude/pd/entities/entities.db --project-root "$PWD"` WITHOUT `--fix` → save `.doctor-before.txt`.
2. Rewire `str(uuid_mod.uuid4())` → `generate_uuid7()` at `database.py:6775`, `:7801`, `:9736` and `project_identity.py:685` (import `from entity_registry.uuid7 import generate_uuid7` matching each file's idiom); update `project_identity.py:563` docstring ("uuid4" → "uuid7"); DROP `project_identity.py:21` `import uuid as uuid_mod` (sole use was `:685`; database.py's stays for the frozen sites). Do NOT touch `database.py:272`, `:1855`.
3. Round-trip test, in `test_database.py` ONLY, calling `frontmatter.validate_header` inline (not duplicated into other test files; design inventory's three-file grouping refers to the rename/re-scope edits): register entity → assert `uuid[14] == "7"` (non-vacuous: impossible pre-rewiring) → `get_entity(uuid)` routes via the uuid branch → `resolve_ref(uuid)` resolves → `validate_header` returns no errors.
4. Residual-uuid4 scan test: COUNT-BASED — assert exactly 2 `uuid4(` occurrences in non-test `entity_registry/*.py`, both inside the frozen migration function bodies (content signature, NEVER line numbers — this task's own import insertion shifts them).
5. Mutation-check the scan test once: revert one rewired site in the working tree → scan test red → restore.
6. AFTER: run doctor → `.doctor-after.txt`; diff — no new issue classes, no check crashes.

**Verify:** full `entity_registry` suite green; doctor diff clean; step-5 mutation check observed red-then-green.

## Task 4: schema_v2 dark module

**Files:** NEW `plugins/pd/hooks/lib/entity_registry/schema_v2.py`, NEW `.../test_schema_v2.py`

**Do:**
1. `schema_v2.py` per design D1/D3/D4: `V2_SCHEMA_VERSION = 1`; `_CORE_DDL` exactly as design D3 (all `IF NOT EXISTS`; entities/relations/sequences/workspaces/`_metadata`; CASCADE FKs + `idx_relations_dedup` UNIQUE(from_uuid,to_uuid,kind); non-unique lookup indexes; NO state columns, NO allowlist); `DDL_REGISTRY = [("core", _CORE_DDL)]`; `register_ddl(owner, sql)` with duplicate-owner `ValueError`; `bootstrap_v2(db_path) -> sqlite3.Connection` — `sqlite3.connect(db_path, autocommit=True)`, PRAGMAs (journal_mode=WAL, busy_timeout, foreign_keys=ON) before any transaction, `executescript` per entry in order, then the module's ONLY `_metadata` write (`INSERT OR IGNORE` schema_version), RETURNS the open configured connection (caller closes — design D4). Docstrings: registry-is-input-to-bootstrap, convergent-not-atomic recovery, factory must re-issue foreign_keys AND busy_timeout.
2. `test_schema_v2.py` (design #1-6): uuid TEXT PK on the 4 CORE tables (workspaces, entities, entity_relations, sequences — `_metadata` excluded: key-value bookkeeping, PK is `key`, per this task's own DDL); UNIQUE-index sweep by covered column set (only `idx_relations_dedup` allowed); duplicate `(type_id, workspace)` entity insert succeeds twice; `register_ddl("dummy", ...)` → bootstrap creates it, duplicate owner raises; double bootstrap idempotent (version value unchanged, single `_metadata` row); one-version-write source scan over executable statements (strip `--` comments before counting); WAL + FK enforcement (violating insert raises `IntegrityError`) + `busy_timeout` value — all asserted on the connection `bootstrap_v2` RETURNS (per-connection PRAGMAs; a fresh connection would assert SQLite defaults, not bootstrap's work).

**Verify:** `pytest test_schema_v2.py` green; `grep -rn "schema_v2" plugins/pd/hooks/lib/ --include="*.py" | grep -v "test_\|schema_v2.py"` → empty (dark).

## Task 5: Integration QA

**Do:** full `pytest plugins/pd/hooks/lib/`; `./validate.sh`; `git diff develop...HEAD --stat` vs design File Change Inventory; doctor stability spot-check — re-run the Task-3 command verbatim (`PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m doctor --entities-db ~/.claude/pd/entities/entities.db --project-root "$PWD"`, no `--fix`).

**Verify:** suite green; validate.sh green; diff = inventory files + doctor captures + feature docs, no unsanctioned changes; doctor issue-class set matches `.doctor-after.txt` (no drift since Task 3).

## Summary

| Task | Depends on | Files collide with |
|------|-----------|--------------------|
| 1 | — | — |
| 2 | — | 3 (`database.py`, `test_database.py`) |
| 3 | 1, 2 | 2 |
| 4 | — (dark) | — |
| 5 | 1-4 | — |

Execution order: 1 → 2 → 3 → 4 → 5. Concurrency: NONE (serial; collision pairs + doctor bracket make parallel dispatch net-negative for 5 tasks).
