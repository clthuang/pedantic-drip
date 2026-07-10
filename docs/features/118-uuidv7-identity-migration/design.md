# Design: UUIDv7 Identity Migration

## Overview

Three independent deliverables that together lay P004's identity foundation: (1) a dark-shipped v2 schema module with uuid7-keyed core tables and a DDL registry siblings extend; (2) a `generate_uuid7()` helper rewiring the 4 runtime uuid4 mints; (3) version-agnostic uuid validation (`_UUID_V4_RE` → `_UUID_RE`, nibble `[1-7]`) so uuid7 values flow through the three gated v17 paths. Plus the `requires-python >= 3.14` floor bump that unblocks all of it.

## Key Decisions

### D1: New module `schema_v2.py`, bootstrap takes an explicit path — no default
`plugins/pd/hooks/lib/entity_registry/schema_v2.py` owns everything v2: `V2_SCHEMA_VERSION = 1`, core DDL, registry, `bootstrap_v2(db_path)`. `db_path` is a REQUIRED argument with no production default — a default path constant would let a stray import/test create the real v2 DB before feature 132's cutover decides where it lives. Ships dark: no live code imports it except its tests.
*Rejected:* extending `EntityDatabase` with a v2 mode — couples the 10k-line v17 class to the rebuild and violates FR-12's clean-slate intent.

### D2: uuid7 helper in a new tiny module `uuid7.py` with import-time floor check
`plugins/pd/hooks/lib/entity_registry/uuid7.py` (~15 lines): `generate_uuid7() -> str` returning `str(uuid.uuid7())`, plus an import-time guard structured for testability — `def _require_uuid7(mod=uuid): if not hasattr(mod, "uuid7"): raise RuntimeError("pd requires Python >= 3.14 for uuid.uuid7 (stdlib); running <version>")`, called as `_require_uuid7()` at module top level — so a pre-3.14 interpreter fails at import with the floor named, never with a lazy `AttributeError` deep in a write path (spec boundary AC). The test injects a fake module lacking `uuid7` into `_require_uuid7(mod=...)` directly — no monkeypatching of the real `uuid` module or `sys.modules` re-import gymnastics needed to exercise the guard branch. No stdlib shadowing: imported as `entity_registry.uuid7`, distinct from stdlib `uuid`.
*Rejected:* placing the helper in `schema_v2.py` — the 4 rewired sites are v17 code (`database.py`, `project_identity.py`); importing the v2 module from v17 paths couples the live system to the dark module. *Rejected:* per-call `hasattr` check — pays the cost on every mint and reports late.

### D3: v2 core DDL — uuid7 PKs everywhere, no business-key uniqueness, state columns deliberately absent

```sql
CREATE TABLE IF NOT EXISTS _metadata (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
-- schema_version is written exactly once, by bootstrap_v2 (idempotent
-- insert-or-ignore) — the sole version write site [FR-12: ONE version location].
-- Deliberately NOT spelled as SQL here: test #5's source scan counts
-- executable write statements and must not match comment text.

CREATE TABLE IF NOT EXISTS workspaces (
  uuid         TEXT PRIMARY KEY,      -- uuid7
  project_root TEXT,                  -- resolution input (FR-9); project_id_legacy does NOT survive (FR-12)
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
  uuid            TEXT PRIMARY KEY,   -- uuid7
  workspace_uuid  TEXT NOT NULL REFERENCES workspaces(uuid),
  type            TEXT NOT NULL,      -- feature-109 polymorphic taxonomy carries over
  kind            TEXT NOT NULL,
  lifecycle_class TEXT NOT NULL,
  type_id         TEXT,               -- human-readable; NOT unique (FR-4)
  name            TEXT,               -- display; NOT unique
  artifact_path   TEXT,
  parent_uuid     TEXT REFERENCES entities(uuid),
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  metadata        TEXT                -- JSON
);
-- NO status / workflow_phase / pipeline_phase / execution_status columns:
-- state is events (119) projected via views (120) on the two axes (122).

CREATE TABLE IF NOT EXISTS entity_relations (
  uuid       TEXT PRIMARY KEY,        -- uuid7 (v17 used INTEGER id — FR-4 violation, fixed)
  from_uuid  TEXT NOT NULL REFERENCES entities(uuid) ON DELETE CASCADE,
  to_uuid    TEXT NOT NULL REFERENCES entities(uuid) ON DELETE CASCADE,
  kind       TEXT NOT NULL,           -- vocabulary CHECK deferred to 124 (owns `blocks` semantics)
  created_at TEXT NOT NULL
);
-- Carried over from v17 (database.py:4964-4967, :4971): ON DELETE CASCADE (dangling
-- relation rows serve nothing) and the structural dedup guard below — uuid+uuid+enum
-- is NOT a human-readable business key, so FR-4's no-uniqueness rule does not apply.
CREATE UNIQUE INDEX IF NOT EXISTS idx_relations_dedup
  ON entity_relations(from_uuid, to_uuid, kind);

CREATE TABLE IF NOT EXISTS sequences (
  uuid           TEXT PRIMARY KEY,    -- uuid7 (v17 PK was composite (workspace_uuid, entity_type) — business key, dropped)
  workspace_uuid TEXT NOT NULL REFERENCES workspaces(uuid),
  kind           TEXT NOT NULL,
  current_value  INTEGER NOT NULL DEFAULT 0
);

-- Non-unique lookup indexes (UNIQUE forbidden on human-readable fields; plain INDEX is not):
CREATE INDEX IF NOT EXISTS idx_entities_workspace ON entities(workspace_uuid);
CREATE INDEX IF NOT EXISTS idx_entities_type_id   ON entities(type_id);
CREATE INDEX IF NOT EXISTS idx_relations_from     ON entity_relations(from_uuid);
CREATE INDEX IF NOT EXISTS idx_relations_to       ON entity_relations(to_uuid);
CREATE INDEX IF NOT EXISTS idx_sequences_ws_kind  ON sequences(workspace_uuid, kind);
```

Decisions inside the DDL:
- **`parent_uuid` stays a column** (v17 shape; every lineage consumer reads it). FR-8 expands `entity_relations.kind` for `blocks` — it does not mandate parent-as-relation. Revisit only if 124 needs it.
- **`sequences` sheds its composite business-key PK** (v17: `PRIMARY KEY (workspace_uuid, entity_type)` with `next_val INTEGER NOT NULL DEFAULT 1`, `database.py:2140-2144`); allocation atomicity moves to 121's `BEGIN IMMEDIATE` (update-first-then-insert works serialized under SQLite's write lock; upsert-on-conflict is unavailable without a UNIQUE index, and that's fine). **Semantic contract for 121 — deliberately flipped from v17:** `current_value` holds the LAST ALLOCATED value (v17's `next_val` held the next-to-allocate); 121 allocates via `current_value + 1` under `BEGIN IMMEDIATE`; `DEFAULT 0` ⇒ first allocated id = 1. 121 must not port v17's pre-increment reading.
- **No `allowlist` table** — FR-9 removes cross-workspace allowlisting; links are ordinary uuid refs.
- **`workspaces` keeps `project_root`** (resolution precedence input, FR-9) and drops `project_id_legacy` (FR-12 shim cleanup).

### D4: Extension point = ordered module-level registry, executed by one bootstrap
```python
DDL_REGISTRY: list[tuple[str, str]] = [("core", _CORE_DDL)]  # (owner_name, sql_script)

def register_ddl(owner: str, sql_script: str) -> None:
    """Siblings (119 events, 120 views, 122 CHECK rewrites) append at import time,
    BEFORE bootstrap_v2 runs. Re-registration of the same owner is an error."""

def bootstrap_v2(db_path: str) -> sqlite3.Connection:
    """Idempotent: WAL + busy_timeout + foreign_keys=ON, executescript every
    registry entry in order (all DDL is IF NOT EXISTS), then the single
    INSERT OR IGNORE version write. Re-run: no error, version unchanged.
    RETURNS the open, PRAGMA-configured connection — caller closes. Rationale:
    foreign_keys/busy_timeout are per-connection; returning the configured
    connection lets tests assert the actual PRAGMA state (a fresh connection
    would test nothing) and gives future callers (119+) a ready connection."""
```
Idempotency is structural (IF NOT EXISTS everywhere + INSERT OR IGNORE for the version row), not stateful (no "already ran" flag to desync). Two SQLite footguns pinned:
- **PRAGMA ordering:** `journal_mode=WAL`, `busy_timeout`, and `foreign_keys=ON` are issued on a FRESH connection BEFORE any statement opens a transaction — `foreign_keys` is a silent no-op if set mid-transaction. Bootstrap uses `sqlite3.connect(db_path, autocommit=True)` (Python 3.12+ explicit autocommit) for the PRAGMA phase. `foreign_keys` AND `busy_timeout` are both per-connection (non-persistent); the docstring states the future v2 connection factory (later features) must re-issue both.
- **Multi-entry apply is convergent, not atomic:** `executescript` per registry entry commits as it goes — a failure at entry N leaves entries 1..N-1 applied. That partial state is safe BY the idempotency contract: re-running bootstrap converges (IF NOT EXISTS skips the applied prefix). Stated in the docstring as the recovery contract, not left implicit.
*Rejected:* migration-chain framework for v2 — FR-12 exists because the v17 chain (22 copy-rename rebuilds, ~127 version touch points) demonstrated the cost. v2 evolves by editing the DDL in place until cutover; after cutover, schema changes are a solved-later problem (the counter exists for that day).

### D5: Widen both PRODUCTION `_UUID_V4_RE` copies in place; rename to `_UUID_RE`; sweep EVERY reference
`database.py:25-27` and `frontmatter.py:57-59` each get version nibble `4` → `[1-7]` (variant `[89ab]` unchanged — uuid7 shares the IETF variant, venv-verified). The two-file duplication is deliberate v17 structure (frontmatter.py is import-light by design, R11 comment) — merging them into a shared module is v17 refactoring outside this feature's charter. Production call sites (`database.py:6054`, `:6283`, `frontmatter.py:118`) need only the rename; their `.match`/`.fullmatch` logic is version-agnostic once the regex is.

**Rename blast radius is ALL references, not just production** — the symbol is imported by name at module level in three test files (`test_database.py:17` + local re-imports `:178`/`:237`, `test_server_helpers.py:11`, `test_frontmatter.py:25`); a definition-only rename fails at test COLLECTION (ImportError), not assertion. The sweep is mechanical and separate from the behavioral re-scopes: rename every import and every usage, including the non-reversal usages the spec's categories don't cover — `test_server_helpers.py:501`/`:1018` (lineage root uuid-shape assertions) and the variant test `test_database.py:2113` (logic unchanged, symbol renamed). Acceptance: `grep -rn "_UUID_V4_RE" plugins/pd/hooks/lib/` returns ONLY the test-local private copy in `test_entity_server.py:19` (below).

A third, test-local `_UUID_V4_RE` copy exists at `test_entity_server.py:19`, used at `:84` as an error-message uuid-leak guard (`assert not ..._RE.search(result)`). It's a private definition, outside the production rename sweep — but its version nibble is ALSO widened to `[1-7]` (one character), because post-rewiring the uuids it most needs to catch leaking are v7; a v4-only leak guard would go blind exactly when it matters.
*Rejected:* full-UUID `uuid.UUID()` parse-based validation — changes error semantics and performance profile of hot lookup paths for zero requirement.

### D6: Rewiring = mechanical substitution at 4 sites
`str(uuid_mod.uuid4())` → `generate_uuid7()` at `database.py:6775` (entity mint), `:7801`, `:9736` (workspace mints), `project_identity.py:685` (workspace mint); `from entity_registry.uuid7 import generate_uuid7` (match each file's existing import idiom); `project_identity.py:563` docstring "generate uuid4" → "generate uuid7". Frozen sites `database.py:272`, `:1855` untouched (inside v17 migration functions; chain discarded at 132 replay).

## Data Flow (post-change, live v17)

`register_entity` → `generate_uuid7()` → uuid7 string into `entities.uuid` (TEXT, shape-compatible) → `get_entity`/`resolve_ref` route it via widened `_UUID_RE` → frontmatter `validate_header` accepts it. Workspace mints likewise; `_WORKSPACE_UUID_RE` already accepts `[1-7]` (`project_identity.py:30-34`, no change).

## Error Handling

- Pre-3.14 interpreter: `uuid7.py` import raises `RuntimeError` naming the floor (spec boundary AC; tested by calling `_require_uuid7(mod=fake)` with a fake module lacking `uuid7` — exercises the actual guard branch without touching the real `uuid` module).
- `bootstrap_v2` on an existing v2 DB: clean no-op (idempotency AC).
- `register_ddl` after bootstrap already ran on some path: the next `bootstrap_v2` call picks it up (registry is input to bootstrap, not a post-hoc migration); duplicate owner registration raises `ValueError` — catches double-import wiring mistakes loudly.

## Testing Strategy

New `test_schema_v2.py`:
1. Bootstrap shape: `PRAGMA table_info` per core table — uuid TEXT PK everywhere; `PRAGMA index_list`/`index_info` sweep inspecting each UNIQUE index's COVERED COLUMN SET — flag only unique indexes covering `type_id`/`slug`/`name`/display fields; the intended `idx_relations_dedup` (uuid+uuid+kind) is expected and excluded (loop over all tables, not per-table hardcode).
2. Same-business-key double insert (two entities, same `type_id`+workspace) succeeds.
3. Extension point: `register_ddl("dummy", "CREATE TABLE IF NOT EXISTS dummy_t (uuid TEXT PRIMARY KEY)")` → bootstrap → table exists; duplicate owner raises.
4. Idempotent re-bootstrap: second call no error, `schema_version` value unchanged, no duplicate rows.
5. One-version-location: source scan asserting exactly one SQL write statement targets `_metadata` in `schema_v2.py`.
6. WAL mode + foreign_keys + busy_timeout set on the bootstrap connection (FK-violating insert fails; `PRAGMA busy_timeout` returns the configured value) — asserted on the connection `bootstrap_v2` RETURNS (per D4's caller-closes contract; both PRAGMAs are per-connection, so a fresh connection would test nothing).

New `test_uuid7.py`:
7. 1000× mint: all version nibble 7, sorted == generation order (empirically holds: 10k venv demo at spec time).
8. Floor-failure: `_require_uuid7(mod=fake_module_without_uuid7)` raises `RuntimeError` containing "3.14" (direct guard-branch exercise, not sys.modules manipulation).

v17 integration (in `test_database.py` / `test_frontmatter.py` / `test_server_helpers.py`):
9. Round-trip: `register_entity` → minted uuid is v7 → fetch via `get_entity`-by-uuid routing → `resolve_ref` uuid branch → `validate_header` with that uuid: all positive (spec's non-vacuity requirement — these fail on v4-pinned regexes, pass after widening).
10. Re-scope the five version-boundary reversal tests (spec's enumerated set) to version-agnostic acceptance; minted-format assertions v4→`[1-7]` INCLUDING their failure-message text (`"Expected UUID v4"` → `"Expected a valid UUID"` — messages must not lie about v7 values, e.g. `test_database.py:671/:685/:803/:1910`); mechanical `_UUID_V4_RE`→`_UUID_RE` rename sweep across all three importing test files (D5 blast radius).
11. Full suite green under venv 3.14.6; same-session before/after doctor capture (procedure: run doctor, commit rewiring, run doctor, diff — no new issue classes).
12. Residual-uuid4 source scan (mirrors test #5's style): asserts `uuid4(` occurs in non-test `entity_registry/` code at EXACTLY the two frozen migration sites — pins spec SC4's grep durably against future stray uuid4 mints.

## Risks

- **Sibling import-order trap:** a sibling registering DDL after its own bootstrap call sees a stale DB on paths bootstrapped earlier in the same process. Mitigation: registry-is-input-to-bootstrap contract in docstring + duplicate-owner guard; real exposure starts at 119, not in this dark-shipped state.
- **uuid7 in live DB before cutover:** post-118 rows carry v7, old rows v4 — mixed versions are by-design valid (both match `_UUID_RE`; nothing orders by uuid string in v17). 132's replay decides re-mint vs preserve.

## File Change Inventory

| File | Change |
|------|--------|
| `plugins/pd/hooks/lib/entity_registry/schema_v2.py` | NEW — version constant, core DDL, registry, bootstrap |
| `plugins/pd/hooks/lib/entity_registry/uuid7.py` | NEW — `generate_uuid7()` + import-time floor check |
| `plugins/pd/hooks/lib/entity_registry/database.py` | `_UUID_V4_RE`→`_UUID_RE` widened (`:25-27`, call sites `:6054`, `:6283`); 3 mint sites rewired (`:6775`, `:7801`, `:9736`) |
| `plugins/pd/hooks/lib/entity_registry/project_identity.py` | mint site `:685` rewired; `:563` docstring |
| `plugins/pd/hooks/lib/entity_registry/frontmatter.py` | `_UUID_V4_RE`→`_UUID_RE` widened (`:57-59`, call site `:118`) |
| `plugins/pd/pyproject.toml` | `requires-python = ">=3.14"` (`:4`) |
| `plugins/pd/hooks/lib/entity_registry/test_schema_v2.py` | NEW |
| `plugins/pd/hooks/lib/entity_registry/test_uuid7.py` | NEW |
| `test_database.py`, `test_frontmatter.py`, `test_server_helpers.py` | mechanical `_UUID_V4_RE`→`_UUID_RE` rename sweep (imports + ALL usages) + reversal-set re-scope + minted-format assertions (incl. message text) + round-trip test |
| `test_entity_server.py` | test-local leak-guard regex nibble widened `4`→`[1-7]` (name kept local; one character) |
