# Spec: Feature 108 — Workspace Identity Foundation

- **Project:** P003-entity-system-redesign
- **Feature:** 108-workspace-identity-foundation
- **Phase:** 0 (foundation, 1-shot, low risk)
- **Status:** Draft
- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **PRD reference:** `docs/projects/P003-entity-system-redesign/prd.md`
- **Roadmap reference:** `docs/projects/P003-entity-system-redesign/roadmap.md`
- **Fixes delivered (per PRD union-of-fixes):** F1 (workspace UUID identity), F5 (drop `parent_type_id`), F6 (UUIDv7 — conditional on Python 3.14+ stdlib `uuid.uuid7`)
- **Constraint:** No backward compatibility. All `project_id` reader call sites get rewritten — old code paths are deleted.

---

## 1. Overview

This feature replaces the implicit, git-derived workspace identity primitive (`project_id` = 12-char hex of root commit SHA, computed by `project_identity.py:detect_project_id` at lines 90-144) with an explicit, file-stamped UUID written to `.claude/pd/workspace.json` on first SessionStart. A new `workspaces` table is introduced as the FK target for a new `entities.workspace_uuid` column; the existing `UNIQUE(project_id, type_id)` constraint at `database.py:1024` is replaced by `UNIQUE(workspace_uuid, type_id)`.

In the same migration we drop the redundant `parent_type_id` column at `database.py:578` (the immutable-text parent FK) and delete its associated index `idx_parent_type_id` and three triggers (`enforce_no_self_parent`, `enforce_no_self_parent_update`). Live DB state already shows 0 rows depend on this column exclusively (verified: `SELECT COUNT(*) FROM entities WHERE parent_uuid IS NULL AND parent_type_id IS NOT NULL` returns 0; 22 rows have `parent_uuid` only, 88 have both).

Conditionally (gated by a documented EXPLAIN QUERY PLAN check) we replace `uuid_mod.uuid4()` at runtime register sites — `database.py:2145` (`register_entity`, approximate; verify at implement time) and `database.py:3846` (`register_entities_batch`, approximate; verify at implement time) — with `uuid_mod.uuid7()` for time-ordered identity. **Migration 1's UUID generation at `database.py:167` is explicitly EXCLUDED** from F6 substitution: Migration 1 must remain stable across re-runs to avoid changing UUIDs assigned to legacy data. Stdlib `uuid.uuid7` ships in **Python 3.14+** (CPython issue #102461; see https://docs.python.org/3/library/uuid.html). The current `pyproject.toml` `python_requires` floor is `>=3.12` (verified at `plugins/pd/pyproject.toml:4`). Because 3.12 is below 3.14, **F6 is deferred to backlog by default** for this feature; F6 ships only if the resolved venv is Python 3.14+ AND the EXPLAIN QUERY PLAN check passes. F6 is a **build-time decision frozen at implementation merge**, not a runtime fallback (see FR-15).

This feature is the foundation for 109/110/111: feature 109 needs `workspace_uuid` to scope its taxonomy migration; 110 needs stable identity for projection generation; 111 writes events into `phase_events` keyed on the same uuid surface. Without 108, those features cannot proceed.

---

## 2. Functional Requirements

Each FR has explicit acceptance criteria, cited file:line, and a verification mechanism.

### FR-1: Workspace UUID file format

The file `.claude/pd/workspace.json` (project-relative; lives under the same `.claude/` dir that owns settings) is the canonical workspace identity store.

JSON schema (strict, no extras):

```json
{
  "workspace_uuid": "<uuidv7-or-uuidv4>",
  "schema_version": 1,
  "created_at": "<ISO 8601 UTC>",
  "created_by": "session-start.sh",
  "project_id_legacy": "<12-char hex from previous detect_project_id, optional>"
}
```

- **AC:** Field `workspace_uuid` is a valid UUID (string form, lowercase, hyphenated, length 36).
- **AC:** Field `schema_version` is integer literal `1` for this feature.
- **AC:** `created_at` parses as ISO 8601 in UTC.
- **AC:** `project_id_legacy` is optional and present only on workspaces migrated from a pre-108 DB.
- **AC:** Any unknown top-level key is rejected (file is rewritten on read, with WARN log if extra keys observed).

### FR-2: Workspace UUID lifecycle

- **AC:** `session-start.sh` calls a new helper `ensure_workspace_uuid()` (added to `lib/session-start-helpers.sh`) before any DB read. The shell helper invokes the Python implementation via `plugins/pd/.venv/bin/python -c "from entity_registry.project_identity import resolve_workspace_uuid; print(resolve_workspace_uuid())"` — there is **no second shell-level write path** (see NFR-1).
- **AC:** If `.claude/pd/workspace.json` is missing, the Python helper writes it atomically: `tempfile.NamedTemporaryFile(dir='.claude/pd/', delete=False)` (same directory as destination, never `/tmp` — guarantees same-filesystem atomicity per NFR-7) followed by `os.replace(tempfile_path, workspace_json_path)`. The UUID generator is `uuid_mod.uuid7()` only if F6 lands and venv is Python 3.14+, else `uuid_mod.uuid4()`.
- **AC:** **fcntl.flock-based cross-process synchronization** (corrects the broken re-read-after-rename approach in earlier drafts). The helper uses `fcntl.flock(LOCK_EX)` on a sentinel `.claude/pd/workspace.json.lock` file in the same directory. Caller order: (1) acquire exclusive flock; (2) re-check existence — if file exists, read and return its UUID (loser case); (3) write tempfile + os.replace; (4) re-read file content for return value; (5) release flock. Under N parallel callers, all return the SAME UUID (either the writer's or the existing-file reader's). Re-read-after-rename WITHOUT flock is BROKEN because each racer's `os.replace` overwrites others' tempfiles and the loser reads back its own discarded UUID. AC verifies via `multiprocessing.Pool(2)` with explicit `os.fork` barrier (Event/Barrier sync) that forces both processes to hit the flock acquire within the same millisecond; asserts `race_results[0] == race_results[1]` (winner's tempfile content).
- **AC:** If the file exists and parses, the helper returns the stored `workspace_uuid` and does not rewrite the file.
- **AC:** If the file exists and is corrupted or has wrong `schema_version`, the helper aborts session-start with exit code 2 and a structured JSON error to stderr (suppressed via `safe_emit_hook_json` to preserve EPIPE safety).
- **AC:** The atomic-write path uses `os.makedirs('.claude/pd', exist_ok=True)` then `os.replace` from a same-directory tempfile; race tolerance verified by AC-15 (parallel race test using `multiprocessing.Pool(2)`, exercising actual concurrency, not a single-thread mock).

### FR-3: Lookup precedence for `workspace_uuid`

`detect_project_id` at `project_identity.py:90-144` is **renamed to `resolve_workspace_uuid` (no alias kept)**. Git-SHA computation moves into a private helper `_compute_legacy_project_id(working_dir)` used **ONLY** by Migration 11 step 0 to populate `workspaces.project_id_legacy`. After migration completes, `_compute_legacy_project_id` is unreferenced from runtime code paths.

Precedence chain:

1. `ENTITY_WORKSPACE_UUID` env var (test override; supersedes `ENTITY_PROJECT_ID`, which is removed entirely).
2. `.claude/pd/workspace.json` (the new SoT). **Project-level always wins** — see EC-8 for the user-level vs project-level resolution rule.
2.5. **DB recovery** — if the file is missing AND the `workspaces` table contains exactly one row whose `project_root` equals `abspath('.claude/..')` for the current `.claude/`-owner directory, regenerate `workspace.json` with that row's `workspace_uuid` (and its `project_id_legacy`, if non-NULL). **If `project_root` is NULL or no row matches**, fall through to step 3. **If multiple rows match (ambiguous)**, also fall through to step 3 and emit a WARN log naming the ambiguity. This step ONLY triggers when the file is missing; it never overrides a present file.
3. **Fallback** — derive a fresh UUID, write the file, and return it. When step 3 fires for a populated DB (i.e., entities exist but no `workspaces` row matched in step 2.5), emit a WARN log: `"No workspace_uuid match in workspaces table; generated fresh UUID — entities may be orphaned, run claim_unknown_entities to reattribute"`. (Git-SHA path and path-hash path become legacy-only and are used **only during migration** via `_compute_legacy_project_id` to compute `project_id_legacy` for the audit trail; they never populate `workspace_uuid` at runtime.)

- **AC:** `ENTITY_PROJECT_ID` env var is removed entirely from the codebase. Migration 11 does NOT read either env var — it derives the legacy `project_id` via `_compute_legacy_project_id()` (per design Decision 5). Post-merge, `grep -r ENTITY_PROJECT_ID plugins/pd/` returns 0 hits (per FR-14 AC).
- **AC:** Calling `resolve_workspace_uuid()` on a fresh, never-seen `.claude/` dir generates the file and returns its UUID.
- **AC:** Calling it again returns the same UUID without rewriting the file (verified by `stat -f %m` mtime preservation).
- **AC:** After implementation, `grep -rn 'detect_project_id' plugins/pd/ --include='*.py'` returns 0 hits (no alias kept).
- **AC:** **Step 2.5 recovery (single match):** Deleting `workspace.json` on a populated DB whose `workspaces` table has a single row matching `project_root = abspath('.claude/..')` regenerates the file with that row's `workspace_uuid`; no WARN log emitted.
- **AC:** **Step 2.5 fallthrough (no match / NULL):** Deleting `workspace.json` on a populated DB whose `workspaces.project_root` is NULL or doesn't match the current path generates a fresh UUID via step 3 and emits the documented WARN log.
- **AC:** **Step 2.5 fallthrough (ambiguous):** Deleting `workspace.json` on a populated DB with multiple `workspaces` rows whose `project_root` matches the current path generates a fresh UUID via step 3 and emits a WARN log naming the ambiguity.

### FR-4: New `workspaces` table

Schema (added by Migration 11):

```sql
CREATE TABLE workspaces (
    uuid               TEXT NOT NULL PRIMARY KEY,
    project_id_legacy  TEXT UNIQUE,           -- old 12-char hex, NULL for born-after workspaces
    project_root       TEXT,                  -- absolute path of .claude/ owner directory
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX idx_workspaces_legacy ON workspaces(project_id_legacy);
```

- **AC:** `PRAGMA table_info(workspaces)` returns these 5 columns in order with the listed types/nullability.
- **AC:** `project_id_legacy` is `UNIQUE` (a single legacy `project_id` cannot map to two workspace UUIDs).
- **AC:** Existing `projects` table is **rebuilt** in this migration (analogous to FR-5/step 5 entities rebuild) so that the new `projects.workspace_uuid TEXT NOT NULL REFERENCES workspaces(uuid)` column starts as `NOT NULL` rather than NULL-then-tightened. Steps: (a) `CREATE TABLE projects_new` mirroring the existing 13 columns plus `workspace_uuid TEXT NOT NULL REFERENCES workspaces(uuid)`; (b) `INSERT INTO projects_new SELECT p.*, w.uuid FROM projects p JOIN workspaces w ON p.project_id = w.project_id_legacy`; (c) `DROP TABLE projects`; (d) `ALTER TABLE projects_new RENAME TO projects`; (e) recreate any indexes/triggers on `projects`. Backfill JOIN guarantees no NULL `workspace_uuid` values can land in the new table.

#### Canonical `__unknown__` workspace seed

A single seed string `"pd-test-fixture-unknown-workspace"` is defined once in `database.py` as the constant `_UNKNOWN_WORKSPACE_UUID_SEED`. The derived UUID `_UNKNOWN_WORKSPACE_UUID` is computed via:

```
digest = hashlib.sha256(_UNKNOWN_WORKSPACE_UUID_SEED.encode()).hexdigest()  # 64 hex chars
hex32  = digest[:32]                                                         # 32 hex chars
# Format as 8-4-4-4-12, force version nibble (13th char) to '4' (RFC 4122 v4),
# force variant nibble (17th char) to one of {'8','9','a','b'} per RFC 4122.
formatted = f"{hex32[0:8]}-{hex32[8:12]}-4{hex32[13:16]}-{('8','9','a','b')[int(hex32[16],16) % 4]}{hex32[17:20]}-{hex32[20:32]}"
_UNKNOWN_WORKSPACE_UUID = formatted
```

**Pinned literal value:** `_UNKNOWN_WORKSPACE_UUID = "6250c8a6-5306-443f-b225-477a040016ea"`. Computed once: `sha256('pd-test-fixture-unknown-workspace').hexdigest()[:32]`, formatted per RFC 4122 v4 (variant nibble at idx 16 = `'b'` from `int('b',16)%4=3 → 'b'`; version nibble forced to `'4'`; idx 12 intentionally unused). Tests assert byte-equality against this literal, **NOT** "recompute and compare".

- **AC:** `_UNKNOWN_WORKSPACE_UUID == "6250c8a6-5306-443f-b225-477a040016ea"` (byte-equality against pinned literal).
- **AC:** `_UNKNOWN_WORKSPACE_UUID` is deterministic across machines and Python versions.
- **AC:** `uuid.UUID(_UNKNOWN_WORKSPACE_UUID).version == 4` and `uuid.UUID(_UNKNOWN_WORKSPACE_UUID).variant == uuid.RFC_4122`.

### FR-5: New `entities.workspace_uuid` column

Migration 11 rebuilds the `entities` table (10th rebuild — same pattern as Migrations 6 and 8 in `database.py`). New column position: after `uuid`, before `type_id`.

```sql
CREATE TABLE entities_new (
    uuid           TEXT NOT NULL PRIMARY KEY,
    workspace_uuid TEXT NOT NULL REFERENCES workspaces(uuid),
    type_id        TEXT NOT NULL,
    entity_type    TEXT NOT NULL,
    entity_id      TEXT NOT NULL,
    name           TEXT NOT NULL,
    status         TEXT,
    parent_uuid    TEXT REFERENCES entities_new(uuid),
    artifact_path  TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    metadata       TEXT,
    UNIQUE(workspace_uuid, type_id)
);
```

- **AC:** Column `project_id` is dropped from `entities` (it lives only on `workspaces.project_id_legacy` going forward).
- **AC:** Column `parent_type_id` is dropped from `entities`.
- **AC:** `UNIQUE(workspace_uuid, type_id)` enforced at schema layer (replaces `UNIQUE(project_id, type_id)` at line 1024).
- **AC:** Index `idx_workspace_uuid` created on `entities(workspace_uuid)`.
- **AC:** Composite index `idx_workspace_entity_type` on `entities(workspace_uuid, entity_type)` (replaces existing `idx_project_entity_type`).
- **AC:** `idx_project_id` and `idx_project_entity_type` are dropped.
- **AC:** `idx_parent_type_id` is dropped.

### FR-6: Trigger updates

The 9 existing triggers on `entities` are rebuilt as 7 (drop the 2 `parent_type_id` triggers); plus 1 new trigger guards `workspace_uuid` immutability.

Triggers after migration:
1. `enforce_immutable_uuid` (kept, line 1061-1064)
2. `enforce_immutable_type_id` (kept, line 1046-1049)
3. `enforce_immutable_entity_type` (kept, line 1051-1054)
4. `enforce_immutable_created_at` (kept, line 1056-1059)
5. `enforce_immutable_workspace_uuid` (NEW — supersedes `enforce_immutable_project_id` at line 1066-1069)
6. `enforce_no_self_parent_uuid_insert` (kept, line 1083-1087)
7. `enforce_no_self_parent_uuid_update` (kept, line 1088-1093)

Dropped triggers:
- `enforce_no_self_parent` (line 1071-1075) — referenced `parent_type_id`
- `enforce_no_self_parent_update` (line 1077-1081) — referenced `parent_type_id`
- `enforce_immutable_project_id` (line 1066-1069) — replaced by `enforce_immutable_workspace_uuid`

- **AC:** `SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='entities'` returns exactly the 7 names listed above (no `parent_type_id`, no `project_id` triggers).
- **AC:** Attempting `UPDATE entities SET workspace_uuid=...` raises `RAISE(ABORT, 'workspace_uuid is immutable — use re-attribution API')`.
- **AC:** Attempting `INSERT` with `parent_uuid = uuid` still raises `'entity cannot be its own parent (uuid)'`.

### FR-7: Forward migration logic (Migration 11 up)

Migration writes are wrapped in `BEGIN IMMEDIATE / COMMIT / ROLLBACK` with `PRAGMA foreign_keys = OFF` outside the transaction (matching existing pattern at `database.py:558-903`).

Steps:

0. **Workspace mapping audit (pre-transaction):** Run `SELECT DISTINCT project_id FROM entities` and emit `<workspace_root>/.claude/pd/migrations/migration-11-workspace-mapping.json` (workspace-relative; `<workspace_root>` is the dir containing `.claude/`; auto-gitignored since `.claude/pd/` is per-workspace state) mapping `{old_project_id_hex: new_workspace_uuid}` for every distinct `project_id`, **including `__unknown__`**. Production `__unknown__` rows are real (per `database.py:1013` `project_id TEXT NOT NULL DEFAULT '__unknown__'` and the production `claim_unknown_entities` reattribution path at `database.py:2580`); they are mapped to the canonical `_UNKNOWN_WORKSPACE_UUID` (deterministic UUID derived from the seed `"pd-test-fixture-unknown-workspace"` per FR-4) — **not aborted**. Migration emits a WARN-level log line per `__unknown__` row count: `"Migration 11: N entities with project_id='__unknown__' attributed to canonical unknown-workspace UUID; review with claim_unknown_entities post-migration."` Operators run `claim_unknown_entities` post-migration to reattribute as needed. There is no `--allow-unknown-project-id` CLI flag.
1. PRAGMA foreign_keys = OFF; verify it took effect.
2. BEGIN IMMEDIATE.
3. Pre-migration FK check (must be empty).
4. **Bootstrap workspaces table:** for each distinct `project_id` in `entities` (verified live: 3 distinct values — `48e4416a668f`, `b5127373568d`, `e99bb5601c36`), insert into `workspaces` with `project_id_legacy=<old project_id>`. The UUID assigned is `_UNKNOWN_WORKSPACE_UUID` (FR-4 deterministic) when `project_id='__unknown__'`, otherwise a freshly generated UUID. Pull `project_root` from `projects` table where matched; default to NULL otherwise.
5. **Build entities_new:** with new column layout, no `project_id`, no `parent_type_id`.
6. **Pre-migration assertion (must run before step 7 data copy):** Execute `SELECT COUNT(*) AS n, GROUP_CONCAT(uuid) AS offenders FROM entities WHERE parent_uuid IS NULL AND parent_type_id IS NOT NULL` and **abort migration with a clear error if `n > 0`**. The error message lists the offending UUIDs to allow operator review. Migration tooling does NOT silently resolve such rows; explicit operator decision is required. Live DB state confirms `n = 0` pre-migration, so the assertion passes; the former implicit `UPDATE` backfill is removed because (a) it is dead code in the current state and (b) silent resolution of cross-`project_id` parent_type_id pointers would risk attributing parents incorrectly.
7. **Data copy:** `INSERT INTO entities_new (uuid, workspace_uuid, type_id, entity_type, entity_id, name, status, parent_uuid, artifact_path, created_at, updated_at, metadata) SELECT e.uuid, w.uuid, e.type_id, e.entity_type, e.entity_id, e.name, e.status, e.parent_uuid, e.artifact_path, e.created_at, e.updated_at, e.metadata FROM entities e JOIN workspaces w ON e.project_id = w.project_id_legacy`.
8. DROP TABLE entities; ALTER TABLE entities_new RENAME TO entities.
9. **Recreate triggers** (7 listed in FR-6).
10. **Recreate indexes:** `idx_entity_type`, `idx_status`, `idx_parent_uuid`, `idx_workspace_uuid`, `idx_workspace_entity_type`. (Drop: `idx_project_id`, `idx_project_entity_type`, `idx_parent_type_id`.)
11. **Update `workflow_phases.workspace_uuid`:** add column `workspace_uuid TEXT REFERENCES workspaces(uuid)`; backfill from `entities`; add index `idx_wp_workspace_uuid`. **Add AFTER INSERT trigger `wp_autofill_workspace_uuid`** that auto-populates `workspace_uuid` from `entities.workspace_uuid` keyed by `type_id` whenever the inserted row's `workspace_uuid` is NULL — eliminates need to modify the existing INSERT sites at `database.py:3265` (`set_workflow_phase`) and `database.py:3442` (upsert path). See design Decision 8 for trigger choice rationale vs explicit INSERT modification. Add BEFORE INSERT trigger `wp_reject_orphaned_insert` that raises ABORT when `NEW.workspace_uuid IS NULL AND NOT EXISTS (SELECT 1 FROM entities e WHERE e.type_id = NEW.type_id)` — fail-fast on orphaned phase row insertion (matches design Decision 8). Both triggers form a complementary pair: autofill on entity-exists, reject on orphan.
12. **Rebuild `sequences` table** to key on `workspace_uuid` instead of `project_id`. Current schema: `CREATE TABLE sequences (project_id TEXT NOT NULL, entity_type TEXT NOT NULL, next_val INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (project_id, entity_type))`. Target schema:
    ```sql
    CREATE TABLE sequences_new (
      workspace_uuid TEXT NOT NULL,
      entity_type    TEXT NOT NULL,
      next_val       INTEGER NOT NULL DEFAULT 1,
      PRIMARY KEY (workspace_uuid, entity_type),
      FOREIGN KEY (workspace_uuid) REFERENCES workspaces(uuid)
    );
    INSERT INTO sequences_new (workspace_uuid, entity_type, next_val)
    SELECT w.uuid, s.entity_type, s.next_val
    FROM sequences s
    JOIN workspaces w ON s.project_id = w.project_id_legacy;
    DROP TABLE sequences;
    ALTER TABLE sequences_new RENAME TO sequences;
    ```
    Down-migration (FR-8 step 9 mirror): rebuild `sequences_old` with `(project_id, entity_type)` PK, INSERT...SELECT joining `workspaces.project_id_legacy`, DROP, RENAME.
13. **Rebuild `projects` table** with `workspace_uuid NOT NULL` from creation (per FR-4): `CREATE TABLE projects_new`, `INSERT INTO projects_new SELECT p.*, w.uuid FROM projects p JOIN workspaces w ON p.project_id = w.project_id_legacy`, `DROP TABLE projects`, `ALTER TABLE projects_new RENAME TO projects`, recreate indexes/triggers. Existing `project_id` PK kept on the new table for legacy projection display.
14. **Rebuild `entities_fts`:** drop, recreate, repopulate (matches Migration 7 at line 1024).
15. UPDATE _metadata SET schema_version=11.
16. COMMIT.
17. PRAGMA foreign_keys = ON. Post-migration FK check (must be empty).

- **AC:** After migration on a copy of the live `~/.claude/pd/entities/entities.db`, `SELECT COUNT(*) FROM entities WHERE workspace_uuid IS NULL` returns 0.
- **AC:** Distinct workspace UUIDs in `entities` after migration equals distinct `project_id` values pre-migration (live: 3).
- **AC:** `SELECT COUNT(*) FROM entities` is unchanged (live: 452 = 369+55+28).
- **AC:** `PRAGMA foreign_key_check` post-commit returns no rows.
- **AC:** `_metadata.schema_version` = `11`.
- **AC:** **Pre-migration assertion** (step 7) runs and emits `Pre-migration check passed (0 unresolved parent_type_id orphans)` when the DB is in expected state. A synthetic test injects a row matching the predicate (`parent_uuid IS NULL AND parent_type_id IS NOT NULL`) and confirms the migration aborts with the documented error listing the offending UUID(s).
- **AC:** **Workspace mapping audit** (step 0) writes `<workspace_root>/.claude/pd/migrations/migration-11-workspace-mapping.json` (workspace-relative; auto-gitignored). Test 7.6 (workspace mapping audit) asserts post-migration `workspaces.project_id_legacy` matches each `{old_project_id_hex → new_workspace_uuid}` mapping entry.
- **AC:** When the DB contains rows with `project_id='__unknown__'`, migration emits a WARN log per `__unknown__` count, includes the `__unknown__ → _UNKNOWN_WORKSPACE_UUID` mapping in `migration-11-workspace-mapping.json`, and completes successfully (does not abort). Verified by injecting `__unknown__` rows into a synthetic DB pre-migration and asserting (a) WARN log substring present in captured stderr, (b) mapping file contains the `__unknown__` key with `_UNKNOWN_WORKSPACE_UUID` value, (c) `_metadata.schema_version=11` post-migration.
- **AC (workflow_phases workspace_uuid invariant):** After Migration 11, every `workflow_phases` row has a non-NULL `workspace_uuid` matching its entity's `workspace_uuid` (verified via JOIN query: `SELECT COUNT(*) FROM workflow_phases wp LEFT JOIN entities e ON wp.type_id=e.type_id WHERE wp.workspace_uuid IS NULL OR wp.workspace_uuid != e.workspace_uuid` returns 0). New INSERTs without explicit `workspace_uuid` populate via the `wp_autofill_workspace_uuid` AFTER INSERT trigger created in Migration 11 step 11. Verified by inserting into `workflow_phases` via `database.py:3265` (`set_workflow_phase`) and `database.py:3442` (upsert path) without `workspace_uuid` and asserting trigger auto-fills from `entities.workspace_uuid`. Additionally, `wp_reject_orphaned_insert` blocks orphan insertion at runtime; tested via `test_workflow_phases_orphan_insert_rejected` (synthetic INSERT for `type_id` with no entity raises `sqlite3.IntegrityError`).

### FR-8: Reverse migration logic (Migration 11 down)

The down-script must restore the pre-Migration-11 schema **exactly** (column order, types, defaults, triggers, indexes match the Migration 8/10 final state).

**Pre-down assertion:** Before reversing, execute:

```sql
SELECT COUNT(*) FROM entities e
WHERE EXISTS (
  SELECT 1 FROM entities p
  WHERE p.uuid = e.parent_uuid
    AND p.workspace_uuid != e.workspace_uuid
)
```

and **abort with error if > 0**. Cross-workspace `parent_uuid` references cannot be reversed losslessly into the pre-11 `parent_type_id` text format (text references are workspace-scoped via the old `UNIQUE(project_id, type_id)`). Such rows require operator intervention — either prune the cross-workspace edges or refuse the down-migration.

Steps:

1. PRAGMA foreign_keys = OFF; BEGIN IMMEDIATE.
2. **Pre-down assertion** (above). Abort on `n > 0`.
3. Build `entities_old` with the pre-11 schema (with `project_id`, `parent_type_id`, `UNIQUE(project_id, type_id)`).
4. **Restore `project_id`:** `INSERT INTO entities_old SELECT uuid, type_id, w.project_id_legacy, entity_type, entity_id, name, status, NULL AS parent_type_id, parent_uuid, artifact_path, created_at, updated_at, metadata FROM entities e JOIN workspaces w ON e.workspace_uuid = w.uuid`.
5. **Restore `parent_type_id`:** `UPDATE entities_old SET parent_type_id = (SELECT type_id FROM entities_old AS p WHERE p.uuid = entities_old.parent_uuid) WHERE parent_uuid IS NOT NULL`.
6. DROP TABLE entities; RENAME entities_old TO entities.
7. Recreate the 9 pre-11 triggers (including the 2 `parent_type_id` triggers and `enforce_immutable_project_id`).
8. Recreate the 6 pre-11 indexes.
9. Reverse changes to `workflow_phases`, `sequences`, `projects`.
10. DROP TABLE workspaces.
11. UPDATE _metadata SET schema_version=10.
12. COMMIT; PRAGMA foreign_keys = ON.

- **AC:** Down-migration is deterministic: applying up + down + up returns DB to the same post-up state byte-for-byte (modulo `created_at` timestamps in `workspaces`, which are stable across the up→down→up sequence because `workspaces` is dropped and recreated with original UUIDs from `project_id_legacy` round-trip).
- **AC:** A test database constructed at schema_version=10, migrated to 11, then reverse-migrated back to 10, has identical row counts and identical `entities` row content (verified by `SELECT * FROM entities ORDER BY uuid` checksum). The round-trip is **lossless**: down-step-5 backfills `parent_type_id` from the `parent_uuid → uuid → type_id` JOIN, recovering the textual format from the UUID-keyed FK. The pre-up assertion (FR-7 step 7) already excludes the only lossy case `(parent_uuid IS NULL AND parent_type_id IS NOT NULL)` by aborting the migration. There is no carve-out.

### FR-9: Drop `parent_type_id` from all reader call sites

Call sites to rewrite (verified live by `grep -rln 'parent_type_id' plugins/pd/ --include='*.py'` — **29 files**, split 12 production + 17 test). Math: 12 + 17 = 29.

(Note: `project_identity.py` does NOT contain `parent_type_id` references and is therefore not listed in FR-9. Its rename from `detect_project_id` → `resolve_workspace_uuid` is covered by FR-3 / FR-18, not FR-9.)

#### Production files (12)

| File | Rewrite |
|---|---|
| `plugins/pd/hooks/lib/entity_registry/database.py` | Drop `parent_type_id` parameter from `register_entity`; signature becomes `(entity_type, entity_id, name, *, workspace_uuid, parent_uuid=None, ...)`. |
| `plugins/pd/hooks/lib/entity_registry/backfill.py` | All `project_id=` kwargs become `workspace_uuid=`; remove `parent_type_id` resolution code (already prefers `parent_uuid`). |
| `plugins/pd/hooks/lib/entity_registry/server_helpers.py` | Same as backfill.py. |
| `plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py` | Drop `parent_type_id` reads. |
| `plugins/pd/hooks/lib/entity_registry/frontmatter_inject.py` | Drop `parent_type_id` writes to frontmatter. |
| `plugins/pd/hooks/lib/workflow_engine/reconciliation.py` | Replace `parent_type_id` reads with `parent_uuid` joins. |
| `plugins/pd/hooks/lib/workflow_engine/secretary_intelligence.py` | Same. |
| `plugins/pd/hooks/lib/workflow_engine/task_promotion.py` | Same. |
| `plugins/pd/hooks/lib/doctor/checks.py` | Drop the `parent_type_id` consistency checks (5 distinct check types, approximate lines 1565-1670 — verify at implement time); keep only `parent_uuid` checks. |
| `plugins/pd/hooks/lib/doctor/fix_actions.py` | Drop the `parent_type_id` fixer (approximate line 36 — verify at implement time). |
| `plugins/pd/mcp/entity_server.py` | Drop `parent_type_id` parameter from `register_entity` MCP tool surface. **Also covers `_upsert_project` rewrite**: `mcp/entity_server.py:124` `db.upsert_project(project_id=info.project_id, ...)` becomes `db.upsert_project(project_id=info.project_id, workspace_uuid=_workspace_uuid, ...)` where `_workspace_uuid` is the lazy global resolved at MCP server startup post-Migration 11. Dependency: `_migrate` runs at MCP server import time before any tool dispatch, so Migration 11 has completed and `_workspace_uuid` is populated before `_upsert_project` is called. |
| `plugins/pd/ui/mermaid.py` | Generate edges from `parent_uuid` joined to `entities.type_id` for display labels only. |

(Also: `plugins/pd/commands/{secretary,create-project,create-feature}.md` and `plugins/pd/skills/{decomposing,brainstorming}/SKILL.md` — non-Python docs caught by FR-18 file list, not part of the 29 Python files.)

#### Test files (17)

| File | Rewrite |
|---|---|
| `plugins/pd/ui/tests/test_mermaid.py` | Update assertions to verify `parent_uuid`-only graph generation. |
| `plugins/pd/ui/tests/test_entities.py` | Drop `parent_type_id` fixture data; assert column absent post-migration. |
| `plugins/pd/mcp/test_search_mcp.py` | Drop `parent_type_id` fixture/assertion. |
| `plugins/pd/mcp/test_entity_server.py` | Update test callers at lines 318 and 373 to pass `workspace_uuid=get_test_workspace_uuid()` to `db.upsert_project()`. Drop `parent_type_id` kwargs. |
| `plugins/pd/hooks/lib/doctor/test_fixer.py` | Drop `parent_type_id` fixer test cases. |
| `plugins/pd/hooks/lib/doctor/test_checks.py` | Drop `parent_type_id` consistency check tests. |
| `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py` | Update fixtures to `workspace_uuid`+`parent_uuid` only. |
| `plugins/pd/hooks/lib/entity_registry/test_frontmatter_sync.py` | Drop `parent_type_id` frontmatter assertions. |
| `plugins/pd/hooks/lib/entity_registry/test_database.py` | Add Migration 11 schema-shape assertions: column absent, indexes/triggers gone. |
| `plugins/pd/hooks/lib/entity_registry/test_search.py` | Update fixtures. |
| `plugins/pd/hooks/lib/entity_registry/test_server_helpers.py` | Same. |
| `plugins/pd/hooks/lib/entity_registry/test_backfill_parent_uuid.py` | Assert post-migration backfill state preserved (22 only-uuid, 88 both, 0 only-text). |
| `plugins/pd/hooks/lib/entity_registry/test_backfill.py` | Update fixtures. |
| `plugins/pd/hooks/lib/workflow_engine/test_task_promotion.py` | Update fixtures. |
| `plugins/pd/hooks/lib/workflow_engine/test_rollup.py` | Update fixtures. |
| `plugins/pd/hooks/lib/workflow_engine/test_entity_engine.py` | Update fixtures. |
| `plugins/pd/hooks/lib/workflow_engine/test_secretary_intelligence.py` | Update fixtures. |
| `plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py` | Update fixtures. |

- **AC:** After implementation, `grep -rl 'parent_type_id' plugins/pd/ --include='*.py'` returns ONLY test files asserting the migration occurred (e.g., `test_database.py`, `test_backfill_parent_uuid.py`); zero hits in production code. The 12 production files above all have `parent_type_id` references removed.
- **AC:** `grep -rn "parent_type_id" plugins/pd/ --include="*.md"` returns 0 hits in non-historical-doc files (commands, skills updated; legacy migration history in CHANGELOG/README permitted).

### FR-10: Drop `project_id` from all reader call sites

The full file list will be **regenerated by `grep -rln '\bproject_id\b' plugins/pd/ --include='*.py' --include='*.sh'` at implementation start**; the count below is approximate and pinned to the day of spec authoring (verified live: **55 files**, 2026-05-10). Files get rewritten as follows:

- **Python:** all `project_id=` kwargs become `workspace_uuid=`; all `db.foo(project_id=...)` calls become `db.foo(workspace_uuid=...)`.
- **`backfill.py:117`**: `project_id: str = "__unknown__"` becomes `workspace_uuid: str` (no default — caller must supply).
- **`backfill.py:177`**: same.
- **`mcp/entity_server.py:140-145`**: `_resolve_project_id` becomes `_resolve_workspace_uuid`; `_project_id` global becomes `_workspace_uuid`.
- **`mcp/entity_server.py:202`**: `_project_id = detect_project_id(_project_root)` becomes `_workspace_uuid = resolve_workspace_uuid(_project_root)`.
- **`reconciliation_orchestrator/__main__.py:88`**: same.
- **`reconciliation_orchestrator/entity_status.py:80,87,110`**: `project_id` parameter renamed and default removed.
- **`session-start.sh:119`**: replaces `meta.get("project_id")` Python snippet with `meta.get("workspace_uuid")`.
- **`session-start.sh:453,461,474-475`**: substitute `workspace_uuid` for `project_id` in the slug-rendering block; the displayed token in injected context becomes `${workspace_uuid_short}-${project_slug}` where `workspace_uuid_short` = first 8 hex chars of UUID (no hyphen).

- **AC:** `grep -rn "\bproject_id\b" plugins/pd/ --include="*.py" --include="*.sh"` returns hits only inside the migration step (Migration 11 source) and the legacy `projects` table operations; no live read paths reference `project_id` after this feature.
- **AC:** `__unknown__` literal removed from all Python sources except inside the migration code that handles legacy `projects` rows for backwards display.

### FR-11: Workspace context injection into hooks

The `meta-json-guard.sh` hook (`plugins/pd/hooks/meta-json-guard.sh`) currently has zero workspace awareness. After this feature:

- **AC:** Hook reads `.claude/pd/workspace.json` at startup; sources `lib/session-start-helpers.sh::ensure_workspace_uuid` (or fail-soft equivalent for the guard context).
- **AC:** Hook exports `WORKSPACE_UUID` env var into any subprocess it dispatches.
- **AC:** Failure to read workspace.json produces a structured warning via `safe_emit_hook_json` but does NOT block the user's tool call (guard policy: warn-only on missing workspace context).

### FR-12: Reconciliation orchestrator reads `workspace_uuid`

`plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py:23,88,93` and `entity_status.py:21,29,47,72,80,87,110` get rewritten:

- **AC:** Module imports `from entity_registry.project_identity import resolve_workspace_uuid` (renamed function).
- **AC:** `args.project_root` lookup followed by `resolve_workspace_uuid(args.project_root)` produces a UUID, not a 12-char hex.
- **AC:** All downstream `update_entity(...)`, `query_entities(...)` calls accept `workspace_uuid=` instead of `project_id=`.

### FR-13: MCP `register_entity` accepts `workspace_uuid`

`plugins/pd/mcp/entity_server.py:_process_register_entity` and the public MCP tool `register_entity` are rewritten:

- **AC:** New signature: `register_entity(entity_type, entity_id, name, *, workspace_uuid: str | None = None, artifact_path=None, status=None, parent_uuid=None, metadata=None)`.
- **AC:** When `workspace_uuid=None`, the MCP server resolves it via the lazy global `_workspace_uuid`, which is populated at server startup from `.claude/pd/workspace.json`.
- **AC:** Old `parent_type_id` parameter removed from MCP signature; deprecation note in commit message only (no runtime warning — pd is private tooling).

### FR-14: Backwards-compat assertion (zero)

**Primary verification (runtime):** After Migration 11 (which DROPs the `project_id` column from `entities`), the full pytest suite runs without `sqlite3.OperationalError: no such column: project_id`. Any code path that dynamically references `project_id` will surface this error at runtime. Static `grep` is kept as **defense in depth — necessary but not sufficient** (it cannot catch dynamic SQL, ORM column references, f-string-built queries, or string-template column lists).

- **AC:** Full `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ plugins/pd/hooks/lib/workflow_engine/ plugins/pd/mcp/` exits 0 after Migration 11 with no `OperationalError` for `project_id` or `parent_type_id`.
- **AC:** No code path retains `project_id` reads at runtime (verified by `grep` as defense in depth).
- **AC:** No code path retains `parent_type_id` reads at runtime.
- **AC:** `ENTITY_PROJECT_ID` env var is **deleted** from the codebase. Tests that previously set this env var are updated to set `ENTITY_WORKSPACE_UUID`.
- **AC:** No "if column exists" runtime branches; the schema is one shape post-migration, and code asserts that shape.

### FR-15: UUIDv7 conditional deliverable (F6)

**F6 is a build-time decision frozen at implementation merge, NOT a runtime fallback.** The `_new_uuid()` helper either always-uses-v7 (if F6 lands) or always-uses-v4 (if F6 deferred). If F6 lands and the venv regresses below 3.14, code calling `_new_uuid()` raises `AttributeError: module 'uuid' has no attribute 'uuid7'` immediately — no silent fallback.

Decision gate runs at the start of implementation:

```bash
plugins/pd/.venv/bin/python -c "import sys, uuid; assert sys.version_info >= (3, 14) and hasattr(uuid, 'uuid7'), 'F6 requires Python 3.14+ stdlib uuid7'"
```

**Scope of substitution:** F6 substitution applies ONLY to runtime register sites — `database.py:2145` (`register_entity`, approximate line; verify at implement time using the symbolic reference) and `database.py:3846` (`register_entities_batch`, approximate line; verify at implement time). **EXCLUDED:** `database.py:167` (Migration 1 historical UUID generation) — Migration 1 must remain stable across re-runs to avoid changing UUIDs assigned to legacy data.

If the gate passes (Python 3.14+ AND `pyproject.toml` floor raised to `>=3.14`):

- **AC:** Replace `uuid_mod.uuid4()` at the symbolic call sites `register_entity` (~`database.py:2145`) and `register_entities_batch` (~`database.py:3846`) with `_new_uuid()`. **Do NOT modify `database.py:167`** (Migration 1).
- **AC:** Add a small helper `_new_uuid()` in `database.py` that **unconditionally calls `uuid_mod.uuid7()`** with comment `# F6: time-ordered identity (Python 3.14+ only)`. No try/except, no fallback. If venv regresses below 3.14, this raises `AttributeError` at runtime — surfacing the contract violation immediately.
- **AC:** Migration 1's UUID-generation behavior is unchanged. Re-applying schema_version 0→1 migration on a synthetic legacy DB yields the same UUIDs whether run before or after this feature's merge.
- **AC:** Existing v4 UUIDs in the DB remain valid (no rewrite); spec asserts that the `uuid` column accepts both forms (verified by mixed-population query post-migration).
- **AC:** EXPLAIN QUERY PLAN audit committed alongside change: run `EXPLAIN QUERY PLAN SELECT * FROM entities WHERE uuid = ?` and `EXPLAIN QUERY PLAN SELECT rowid, * FROM entities ORDER BY uuid` on a mixed v4/v7 dataset of ≥500 rows. Document fragmentation symptoms (or absence) in `docs/features/108-workspace-identity-foundation/uuid-explain-plan.md`. If F6 lands, this file MUST exist; if F6 deferred, this file is NOT required.

If the gate fails:

- **AC:** F6 is deferred to a backlog item (`/pd:add-to-backlog "Adopt uuid7 once Python 3.14+ is the venv default and pyproject.toml floor raised"`). The plan and implementation skip F6 changes entirely. Spec marks FR-15 as "deferred" in the implementation log. A backlog entry referencing F6 deferral rationale exists.

**Implementation log entry (2026-05-10):** F6 DEFERRED. Policy gate result captured at `agent_sandbox/2026-05-10/108-f6-gate/gate-result.txt`: `pyproject_requires_python = ">=3.12"` (floor below 3.14, gate FAILS). Backlog item `#00359` filed in `docs/backlog.md`. Negative grep verification: `grep -rn '\b_new_uuid\b' plugins/pd/` returns 0 hits. No `_new_uuid()` helper introduced. PASSES-path tasks (7.2-7.5) NOT executed.

### FR-16: `.claude/pd/workspace.json` gitignore

- **AC:** `.gitignore` (project-root) is updated to include `.claude/pd/workspace.json`. Workspace UUID is per-`.claude/`-dir, never checked in.
- **AC:** `.claude/pd/` parent directory is created during ensure step if missing.

### FR-17: Doctor health check for workspace.json

`plugins/pd/hooks/lib/doctor/checks.py` gets a new check:

- **AC:** New check function `check_workspace_uuid_consistency(db)` verifies (a) `.claude/pd/workspace.json` exists and parses, (b) the UUID inside it matches at least one row in `workspaces` table, (c) the legacy `project_id_legacy` (if present in workspace.json) matches `workspaces.project_id_legacy` for that UUID.
- **AC:** Check returns `Severity.ERROR` if file missing AND DB has rows for some workspace_uuid; returns `Severity.WARN` if file missing AND DB has zero rows (fresh checkout); returns `Severity.OK` otherwise.

### FR-18: List of changed files (anchor for the plan)

The implementation must touch at minimum these files (any additions are reviewer-flagged in plan stage):

- `plugins/pd/hooks/lib/entity_registry/database.py` (Migration 11 + register_entity rewrite + index/trigger drops + UUID generator)
- `plugins/pd/hooks/lib/entity_registry/project_identity.py` (rename + workspace.json read/write)
- `plugins/pd/hooks/lib/entity_registry/backfill.py` (workspace_uuid plumbing)
- `plugins/pd/hooks/lib/entity_registry/server_helpers.py`
- `plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py`
- `plugins/pd/hooks/lib/entity_registry/frontmatter_inject.py`
- `plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py`
- `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py`
- `plugins/pd/hooks/lib/doctor/checks.py`
- `plugins/pd/hooks/lib/doctor/fix_actions.py`
- `plugins/pd/hooks/lib/workflow_engine/reconciliation.py`
- `plugins/pd/hooks/lib/workflow_engine/secretary_intelligence.py`
- `plugins/pd/hooks/lib/workflow_engine/task_promotion.py`
- `plugins/pd/hooks/lib/session-start-helpers.sh` (new `ensure_workspace_uuid`)
- `plugins/pd/hooks/session-start.sh`
- `plugins/pd/hooks/meta-json-guard.sh`
- `plugins/pd/mcp/entity_server.py`
- `plugins/pd/ui/mermaid.py`
- `plugins/pd/commands/{secretary,create-project,create-feature}.md`
- `plugins/pd/skills/{decomposing,brainstorming}/SKILL.md`
- All `test_*.py` files listed in FR-9.
- `.gitignore`

---

## 3. Non-Functional Requirements

### NFR-1: Bash 3.2 / macOS BSD portability

All new shell in `session-start.sh`, `meta-json-guard.sh`, and `lib/session-start-helpers.sh` must:

- Use POSIX `[[:space:]]` (not `\s`) in any `grep -E` invocations.
- Use `${!varname:-default}` indirect expansion (not `eval`).
- Avoid GNU-only flags (`mktemp -p`, `cp --reflink`, `stat -c`, `readlink -f`).
- **Atomic write of `workspace.json` is delegated to FR-2's Python helper.** The shell `ensure_workspace_uuid` function in `lib/session-start-helpers.sh` shells out via `plugins/pd/.venv/bin/python -c "from entity_registry.project_identity import resolve_workspace_uuid; resolve_workspace_uuid()"`. **No shell-level tempfile manipulation, no `mktemp` invocation writes `workspace.json`** — same-directory tempfile + `os.replace()` lives in Python (`tempfile.NamedTemporaryFile(dir='.claude/pd/', delete=False)`), which guarantees same-filesystem atomicity per NFR-7.
- **Verification:** `bash --version` 3.2.57 (macOS default) and `zsh` both pass `bash plugins/pd/hooks/tests/test-hooks.sh`.
- **AC:** `ensure_workspace_uuid` in `lib/session-start-helpers.sh` shells out to the Python helper; no `mktemp` invocation in any pd shell script writes `workspace.json`. Verified by `grep -n 'mktemp.*workspace' plugins/pd/hooks/` returning 0 matches.

### NFR-2: SQLite WAL mode preserved

- `workspaces` table is created in the same DB file; WAL mode (set per-connection at `database.py:_open_connection`) covers all tables. No WAL config changes required.
- **AC:** `PRAGMA journal_mode` returns `wal` after migration.

### NFR-3: Migration reversibility

- Every up-migration step has an exact inverse in the down-migration script.
- Down-migration tested in CI (see Test Plan §7).
- Down-migration restores the **exact** pre-11 schema (column order, default values, trigger names, index names match).

### NFR-4: No hardcoded plugin paths

- All workspace.json bootstrap code uses the two-location glob pattern: primary `~/.claude/plugins/cache/*/pd*/*/...`, fallback `plugins/*/...` (dev workspace), per CLAUDE.md "Plugin portability".
- **AC:** `validate.sh` passes (no new violations).

### NFR-5: Hook EPIPE safety preserved

- All new hook output (workspace.json bootstrap log, error messages, MCP boot logs) routes through `safe_emit_hook_json` from `lib/session-start-helpers.sh`.
- Subprocess `stderr` suppressed via `2>/dev/null` in shell paths invoking Python (matches CLAUDE.md "Hook subprocess safety").
- **AC:** New `bench-session-start.sh` runs include the workspace.json bootstrap path and pass NFR2 (no broken-pipe failures).

### NFR-6: Migration runtime

- Migration 11 must complete in <2s on the live DB (~452 entity rows). This is a soft target; hard-fail at 30s.
- Migration is idempotent if interrupted between transactions (no half-migrated state because the entire migration is one BEGIN IMMEDIATE / COMMIT).

### NFR-7: Concurrent SessionStart safety

- workspace.json creation must tolerate two SessionStart processes racing on the same `.claude/` dir. The Python helper acquires `fcntl.flock(LOCK_EX)` on a sentinel `.claude/pd/workspace.json.lock` file before any tempfile or rename operation. Inside the critical section it uses `tempfile.NamedTemporaryFile(dir='.claude/pd/', delete=False)` + `os.replace()` for the rename, then re-reads the file before releasing the lock — guaranteeing both racers return the same UUID.
- **Both racers must return the SAME UUID** — guaranteed by **fcntl.flock-based cross-process synchronization** (per FR-2 AC). The helper acquires an exclusive flock on `.claude/pd/workspace.json.lock`, re-checks existence (loser reads existing file), writes tempfile + os.replace, re-reads file content, releases flock. Under N parallel callers, all return the same UUID (winner's or pre-existing). Re-read-after-rename WITHOUT flock is BROKEN — each racer's `os.replace` overwrites others' tempfiles and the loser reads back its own discarded UUID.
- Followup writes from the loser are no-op because the helper short-circuits when `.claude/pd/workspace.json` exists and parses.
- Cross-device tempfile (e.g., `/tmp` on a different filesystem) is forbidden because `os.replace` (and `mv`) would degrade to copy-then-unlink, breaking atomicity. NFR-1 enforces this by routing all writes through the Python helper with `dir='.claude/pd/'` — there is no shell-level `mktemp` path that could violate this constraint.

### NFR-8: No new Python dependencies

- F6 uses **stdlib `uuid.uuid7`** only (Python 3.14+; CPython issue #102461; documented at https://docs.python.org/3/library/uuid.html). No `pip install uuid7` shim, no third-party uuid7 backport.
- `pyproject.toml` is unchanged in this feature; the current floor `requires-python = ">=3.12"` (verified at `plugins/pd/pyproject.toml:4`) is below 3.14.
- **Therefore: F6 is deferred to backlog regardless of EXPLAIN QUERY PLAN result** unless the implementer explicitly raises `pyproject.toml`'s `python_requires` floor to `>=3.14` AS PART OF THIS FEATURE. If the floor is below 3.14 at merge time, F6 is deferred with no exceptions.

---

## 4. Acceptance Criteria (testable list)

Each item is programmatically verifiable. AC numbering is independent from FR numbering and exists for QA gate cross-reference. **Total: 41 ACs.**

| # | Acceptance Criterion | Verification |
|---|---|---|
| AC-1 | After migration, `SELECT COUNT(*) FROM entities WHERE workspace_uuid IS NULL` returns 0. | `sqlite3` |
| AC-2 | After migration, `PRAGMA table_info(entities)` does NOT list `parent_type_id`. | `sqlite3` |
| AC-3 | After migration, `PRAGMA table_info(entities)` does NOT list `project_id`. | `sqlite3` |
| AC-4 | After migration, `PRAGMA table_info(entities)` lists `workspace_uuid` at column index 1. | `sqlite3` |
| AC-5 | Inserting two entities with same `type_id` under different `workspace_uuid` values succeeds. | pytest |
| AC-6 | Inserting two entities with same `type_id` under same `workspace_uuid` raises `sqlite3.IntegrityError`. | pytest |
| AC-7 | Deleting `.claude/pd/workspace.json` and rerunning session-start regenerates a new file with a fresh UUID (because no DB row predates the deletion in this test scenario). | pytest+shell |
| AC-8 | Deleting `.claude/pd/workspace.json` on a populated DB regenerates the file via the FR-3 precedence chain — step 2.5 (DB recovery: single `workspaces` row matching `project_root = abspath('.claude/..')` reuses its UUID, no WARN); fallthrough to step 3 with WARN log when `project_root` is NULL, no match, or ambiguous. | pytest+shell |
| AC-9 | `SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='entities'` returns exactly the 7 names listed in FR-6. | `sqlite3` |
| AC-10 | `enforce_immutable_workspace_uuid` trigger blocks `UPDATE entities SET workspace_uuid=...`. | pytest |
| AC-11 | Down-migration restores `parent_type_id` column with values backfilled from `parent_uuid → uuid → type_id` join. | pytest |
| AC-12 | Down-migration restores `project_id` column with values from `workspaces.project_id_legacy`. | pytest |
| AC-13 | Up + down + up sequence yields byte-identical `entities` row content (verified by `SELECT * FROM entities ORDER BY uuid` and `PRAGMA table_info` equality). Round-trip is lossless because down-step-5 backfills `parent_type_id` from the `parent_uuid → uuid → type_id` JOIN, recovering the textual format from the UUID-keyed FK. The only lossy pre-up case `(parent_uuid IS NULL AND parent_type_id IS NOT NULL)` is excluded by the FR-7 step 7 pre-up assertion (migration aborts before reaching down→up). No carve-out. | pytest |
| AC-14 | `bash plugins/pd/hooks/tests/test-hooks.sh` passes with new schema. | shell |
| AC-15 | Two parallel `session-start.sh` processes racing on workspace.json creation both exit 0 and the file is well-formed. | pytest+shell |
| AC-16 | `bench-session-start.sh` reports no broken-pipe failures and total time within prior NFR2 bounds. | shell |
| AC-17 | `grep -rn "\bproject_id\b" plugins/pd/ --include="*.py" --include="*.sh"` returns 0 hits in non-migration, non-legacy-projects-table code paths. | grep |
| AC-18 | `grep -rn "parent_type_id" plugins/pd/ --include="*.py" --include="*.md"` returns 0 hits in production code. | grep |
| AC-19 | `register_entity(workspace_uuid=W1, type_id="feature:001-x")` returns the entity UUID. Calling again with the same args returns the **same UUID** (current INSERT OR IGNORE semantics preserved; the F12 split into raises/upsert is deferred to Feature 109). No contradictory either-or pass condition. | pytest |
| AC-20 | Doctor check `check_workspace_uuid_consistency` returns OK when `.claude/pd/workspace.json` matches a `workspaces` row. | pytest |
| AC-21 | Doctor check returns ERROR when `.claude/pd/workspace.json` is missing AND `entities` has rows. | pytest |
| AC-22 | Workspace.json with `schema_version=99` (unknown) causes `ensure_workspace_uuid` to abort session-start with structured stderr. | pytest |
| AC-23 | Workspace.json with extra unknown top-level key triggers a WARN log but does not abort. | pytest |
| AC-24 | (F6 conditional) On Python 3.14+ AND when F6 lands, new entity UUIDs are uuidv7 (verifiable: `uuid.UUID(uuid_str).version == 7`). | pytest |
| AC-25 | (F6 conditional) On Python 3.14+ AND when F6 lands, existing uuidv4 entries remain queryable; mixed v4/v7 dataset shows no FTS or index errors. | pytest |
| AC-26 | `validate.sh` passes (no plugin-portability violations). | shell |
| AC-27 | `.gitignore` contains the literal line `.claude/pd/workspace.json`. | grep |
| AC-28 | `_metadata.schema_version` after up-migration is `'11'` (string). | `sqlite3` |
| AC-29 | (FR-11) `meta-json-guard.sh` exports `WORKSPACE_UUID` env var; verified by spawning a test subprocess and checking the env (`bash -c 'echo $WORKSPACE_UUID'`). | shell+pytest |
| AC-30 | (FR-12) `reconciliation_orchestrator/__main__.py` imports `resolve_workspace_uuid` (not `detect_project_id`); verified by `grep -n 'from .* import .*resolve_workspace_uuid' plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py`. | grep |
| AC-31 | (FR-13) `register_entity` MCP tool accepts `workspace_uuid` kwarg; rejects `parent_type_id` kwarg with `TypeError` (unknown keyword argument). | pytest |
| AC-32 | (NFR-6) Migration timed via Python `time.perf_counter()` against a synthetic 500-row DB; logs warning if >2s, fails AC if >30s. | pytest |
| AC-33 | (FR-15) If F6 lands, `docs/features/108-workspace-identity-foundation/uuid-explain-plan.md` exists and contains the captured EXPLAIN QUERY PLAN output. If F6 deferred, this file is not required AND a backlog entry exists referencing F6 deferral rationale. | shell |
| AC-34 | (NFR-1) Hook test suite (`bash plugins/pd/hooks/tests/test-hooks.sh`) exits 0 under `bash` 3.2 (verified via `bash --version | grep -E 'version 3\.2'` precondition or skipped on bash 4+ hosts with explicit skip log). | shell |
| AC-35 | **Atomicity rollback under FK violation** (FR-7 step 3 / EC-3 reinforcement): Injecting an FK violation mid-migration causes `ROLLBACK`; post-rollback `_metadata.schema_version` = `10`, `entities` retains pre-up schema (`PRAGMA table_info` matches pre-up output byte-for-byte), all 9 pre-up triggers exist, all 8 pre-up indexes exist, `workspaces` table does NOT exist in `sqlite_master`. | pytest |
| AC-36 | **Workspace mapping audit file** (FR-7 step 0): `<workspace_root>/.claude/pd/migrations/migration-11-workspace-mapping.json` is emitted during migration and contains a JSON object mapping each pre-migration `project_id` (hex) to its assigned `workspace_uuid`. Verified via `test -f $(get_workspace_root)/.claude/pd/migrations/migration-11-workspace-mapping.json`. Entries match `SELECT project_id_legacy, uuid FROM workspaces` post-migration row-for-row. | pytest+json |
| AC-37 | **Race test (FR-2 / NFR-7)**: `test_workspace_resolve_concurrent` uses `multiprocessing.Pool(2)` with explicit `os.fork` barrier (Event/Barrier sync to force both processes to hit the flock acquire within the same millisecond). Asserts `race_results[0] == race_results[1]` (winner's tempfile content). Both processes' return values are **equal** AND **equal to the file contents**. Validates fcntl.flock-based cross-process synchronization (FR-2). | pytest |
| AC-38 | **FR-3 step 2.5 single match:** Deleting `workspace.json` on a populated DB whose `workspaces` table has exactly one row matching `project_root = abspath('.claude/..')` regenerates the file with that row's `workspace_uuid`; no WARN log emitted. | pytest+shell |
| AC-39 | **FR-3 step 2.5 fallthrough:** Deleting `workspace.json` on a populated DB whose `workspaces.project_root` is NULL, doesn't match, or matches multiple rows generates a fresh UUID via step 3 and emits the documented WARN log (`"No workspace_uuid match in workspaces table; generated fresh UUID — entities may be orphaned, run claim_unknown_entities to reattribute"` for the no-match case; ambiguity-named WARN for multiple matches). | pytest+shell |
| AC-40 | **NFR-1 no shell mktemp:** `grep -n 'mktemp.*workspace' plugins/pd/hooks/` returns 0 matches; `ensure_workspace_uuid` in `lib/session-start-helpers.sh` shells out to the Python helper (`plugins/pd/.venv/bin/python -c "from entity_registry.project_identity import resolve_workspace_uuid; resolve_workspace_uuid()"`). | grep+shell |
| AC-41 | **FR-7 step 0 __unknown__ handling:** Migration mapping a pre-migration `project_id='__unknown__'` row writes the entry `{"__unknown__": "<_UNKNOWN_WORKSPACE_UUID>"}` to `workspace-mapping.json`, emits a WARN log naming the row count, and completes with `_metadata.schema_version=11`. Migration does NOT abort on `__unknown__`. | pytest |

---

## 5. Out of Scope

Explicitly NOT in this feature; deferred to later features per roadmap and PRD §"Solution Approach":

- **Polymorphic taxonomy** (Feature 109 / F11): the 6-type ontology (`workspace`, `work`, `container`, `brainstorm`, `artifact`, `phase_event`) and `kind`/`lifecycle_class` discriminators are NOT introduced here. `entity_type` keeps its existing 8-value vocabulary.
- **Markdown-as-projection** (Feature 110 / F4): `.meta.json` and `docs/backlog.md` continue to be source-of-truth pairings of DB+file. Gitignoring those files is **not** in this feature.
- **Issue lifecycle MCPs** (Feature 111 / F9, F10): `issue_spawn`, `complete_phase(closes=...)` are not added here.
- **`INSERT OR IGNORE` audit and split** (Feature 109 / F12): `register_entity` keeps its current INSERT OR IGNORE semantics. The split into `register_entity` (raises) / `upsert_entity` (idempotent) is deferred.
- **Cross-workspace queries:** the schema **gates** cross-workspace queries by enforcing `workspace_uuid` as a required filter on every read API. Adding explicit cross-workspace join helpers is deferred.
- **`enforce_immutable_entity_type` trigger removal:** kept as-is in this feature; removed in Feature 109 alongside the polymorphic taxonomy migration.
- **`entity_display(uuid, seq, slug)` table** (Feature 110 / F8): UUIDs continue to be the only identity column; `entity_id` keeps its current `{seq}-{slug}` format embedded in the same row.
- **Pre-commit hook for `pd-state.diff.md`** (Feature 110): not in this feature.
- **Fixing the 6 duplicate project rows or 120 orphan backlog rows** (PRD §Success Criteria items 8 and 9): data hygiene cleanup is deferred to Feature 109 where the new taxonomy provides the structural reason to clean.

---

## 6. Edge Cases & Failure Modes

### EC-1: Concurrent SessionStart on workspace.json creation

Two shells start simultaneously in the same project. Both call `ensure_workspace_uuid`. Both detect `.claude/pd/workspace.json` is missing. Both attempt to acquire `fcntl.flock(LOCK_EX)` on `.claude/pd/workspace.json.lock`.

- **Behavior:** flock serializes the two processes. The first acquirer re-checks file existence (still missing), writes tempfile + os.replace, re-reads, releases lock. The second acquirer enters the critical section, re-checks file existence (now present), reads existing file, releases lock. **Both return the same UUID.** Neither process errors.
- **Resolution:** Acceptable and correct. The flock guarantees both racers converge on the winner's UUID — the loser's never-written UUID is discarded before any rename. Tests verify via `multiprocessing.Pool(2)` with explicit fork barrier (AC-15, AC-37).

### EC-2: Migration run twice (idempotency)

A user (or test) runs Migration 11 twice on the same DB.

- **Behavior:** Second invocation reads `_metadata.schema_version=11` and short-circuits. The migration registry pattern at `database.py:_migrate` skips already-applied versions.
- **Resolution:** Standard pattern; same as Migrations 1-10. Test asserts second call is a no-op.

### EC-3: Migration partial failure

PRAGMA foreign_key_check fails mid-migration; transaction rolls back.

- **Behavior:** ROLLBACK in the `except` block (matching pattern at `database.py:898-900`). DB returns to pre-11 state. Re-running the migration from clean state works.
- **Resolution:** Standard. Test simulates by injecting a row that violates an FK and asserts ROLLBACK fires.

### EC-4: workspace.json corrupted

User hand-edits the file and produces invalid JSON, or truncates it.

- **Behavior:** `ensure_workspace_uuid` aborts session-start with structured stderr (FR-2 AC). User sees an error and a fix hint: "rm .claude/pd/workspace.json and re-run".
- **Resolution:** Documented in error message. Auto-recovery is intentionally NOT done because the file may have been edited deliberately and silently overwriting it could lose a legitimate UUID.

### EC-5: workspace.json schema_version mismatch

User has `schema_version=99` (or `0`, or string instead of int).

- **Behavior:** Same as EC-4 — abort with structured error.

### EC-6: Existing DB with `project_id='__unknown__'`

Production AND test code can produce `__unknown__` as project_id: `database.py:1013` declares `project_id TEXT NOT NULL DEFAULT '__unknown__'` (real production default), `database.py:2580` defines the production `claim_unknown_entities` reattribution path, and `backfill.py:117,177` references the same literal.

- **Behavior:** `__unknown__` rows (production AND test) are mapped to the canonical `_UNKNOWN_WORKSPACE_UUID` (defined in FR-4, derived from the seed `"pd-test-fixture-unknown-workspace"` via the v4 formatting algorithm spelled out there). Migration does **not** abort. A WARN log line is emitted per `__unknown__` count (see FR-7 step 0). Live DB has 3 distinct project_ids — none currently `__unknown__` — but the migration must still handle the case because `claim_unknown_entities` is a production code path that can produce `__unknown__` rows mid-flight.
- **Resolution:** Operator runs `claim_unknown_entities` post-migration to reattribute orphan entities to specific workspaces as needed. The WARN log surfaces the count to remind the operator. There is no `--allow-unknown-project-id` flag.

### EC-7: UUIDv7 unavailable (Python <3.14)

Decision gate fails (FR-15). Stdlib `uuid.uuid7` ships in Python **3.14+** (CPython issue #102461). The current `pyproject.toml` floor is `>=3.12` (verified at `plugins/pd/pyproject.toml:4`), so this is the **expected default** outcome for this feature unless the implementer raises the floor.

- **Behavior:** F6 deferred. Implementation skips F6 changes. `_new_uuid()` helper is NOT introduced. `uuid_mod.uuid4()` continues to be used. A backlog entry is created via `/pd:add-to-backlog`.
- **Resolution:** Documented in implementation log; F6 reappears as a separate backlog item titled "Adopt uuid7 once Python 3.14+ is the venv default and pyproject.toml floor raised".

### EC-8: User has multiple `.claude/` dirs (e.g., user-level + project-level)

The user has `~/.claude/` (global) and `~/projects/foo/.claude/` (project). Each gets its own workspace.json.

- **Behavior:** **Project-level `.claude/pd/workspace.json` always wins.** User-level `~/.claude/pd/workspace.json` is a **separate workspace** if it exists (it has its own UUID for entities created at user-scope). Two project directories with no `.claude/pd/workspace.json` each generate their own fresh UUIDs; they do **NOT** inherit from `~/.claude/`.
- **Resolution:** This contradicts FR-3's earlier "fallback" framing — FR-3 has been clarified to indicate that the precedence chain stops at "fresh write a project-local workspace.json" rather than reading user-level. Add explicit test: "project with no workspace.json AND user-level present → fresh UUID, not user's UUID".

### EC-9: `.claude/pd/` does not exist

Brand-new project with no `.claude/pd/` directory.

- **Behavior:** Helper runs `mkdir -p .claude/pd 2>/dev/null` then writes the file. `mkdir -p` is universally available on macOS/Linux.
- **Resolution:** Tested in fresh-checkout integration test.

### EC-10: Workspace UUID collision

Astronomically unlikely (UUID4 collision probability ~5.3×10⁻³⁷). Not a real concern.

- **Behavior:** `INSERT INTO workspaces` would raise on PK conflict; user re-runs and gets a new UUID (or, more likely, the user files a bug report that wins them an obscure record).
- **Resolution:** No special handling. Note in spec only.

---

## 7. Test Plan

All tests live under `plugins/pd/hooks/lib/entity_registry/`, `plugins/pd/hooks/lib/doctor/`, `plugins/pd/hooks/lib/reconciliation_orchestrator/`, or `plugins/pd/hooks/tests/`. Run with `plugins/pd/.venv/bin/python -m pytest`.

### 7.1 Schema tests

| Test | Path | Asserts |
|---|---|---|
| `test_migration_11_table_shape` | `entity_registry/test_database.py` | After up, `entities` has 12 columns (no `project_id`, no `parent_type_id`, has `workspace_uuid`). |
| `test_migration_11_unique_constraint` | same | `INSERT` of duplicate `(workspace_uuid, type_id)` raises IntegrityError; different workspace UUIDs allowed. |
| `test_workspaces_table_ddl` | same | `workspaces` table has the 5 columns listed in FR-4. |
| `test_workspace_uuid_immutable_trigger` | same | UPDATE on `workspace_uuid` raises ABORT. |
| `test_no_parent_type_id_triggers` | same | `enforce_no_self_parent`, `enforce_no_self_parent_update`, `enforce_immutable_project_id` are gone. |
| `test_indexes_after_migration_11` | same | New: `idx_workspace_uuid`, `idx_workspace_entity_type`. Gone: `idx_project_id`, `idx_project_entity_type`, `idx_parent_type_id`. |

### 7.2 Migration tests

| Test | Path | Asserts |
|---|---|---|
| `test_migration_11_forward_idempotent` | `entity_registry/test_database.py` | Apply twice → second call is no-op. |
| `test_migration_11_data_preservation` | same | Entity row count and contents survive forward migration. |
| `test_migration_11_workspace_bootstrap` | same | One `workspaces` row per distinct pre-migration `project_id`. |
| `test_migration_11_reverse` | same | Down-script restores exact pre-11 schema; rebuild round-trip preserves rows. |
| `test_migration_11_round_trip_checksum` | same | `up→down→up` final state checksum equals `up` final state checksum (entities table only). |
| `test_migration_11_partial_failure_rollback` | same | Inject FK violation mid-migration; assert ROLLBACK + DB at version 10. |
| `test_migration_11_unknown_project_id` | same | Test fixtures with `project_id='__unknown__'` get a deterministic workspace UUID; tests remain stable. |
| `test_migration_11_parent_uuid_already_populated` | `entity_registry/test_backfill_parent_uuid.py` | Live state (22 only-uuid, 88 both, 0 only-text) preserved after migration; no `parent_uuid` regenerated incorrectly. |

### 7.3 Workspace.json tests

| Test | Path | Asserts |
|---|---|---|
| `test_ensure_workspace_uuid_creates_file` | `entity_registry/test_project_identity.py` (renamed module) | Fresh `.claude/` → file written, parses, contains valid UUID. |
| `test_ensure_workspace_uuid_idempotent` | same | Subsequent calls do not modify mtime. |
| `test_ensure_workspace_uuid_corrupted` | same | Truncated JSON → abort with exit code 2. |
| `test_ensure_workspace_uuid_wrong_schema_version` | same | `schema_version=99` → abort. |
| `test_ensure_workspace_uuid_extra_keys` | same | Unknown top-level key → warn but proceed. |
| `test_lookup_precedence` | same | ENV > file > fresh-write. |
| `test_workspace_json_atomic_write` | same | Tempfile + mv pattern; partial writes do not leave a half-file. |

### 7.4 Hook integration tests

| Test | Path | Asserts |
|---|---|---|
| `test_session_start_with_workspace_uuid` | `hooks/tests/test-hooks.sh` (added test case) | session-start.sh invokes `ensure_workspace_uuid`; `WORKSPACE_UUID` exported in injected context. |
| `test_meta_json_guard_workspace_aware` | same | meta-json-guard hook reads workspace.json; fails soft if missing. |
| `test_session_start_bench` | `hooks/tests/bench-session-start.sh` | NFR2 bounds preserved; no broken pipe. |

### 7.5 Concurrency tests

| Test | Path | Asserts |
|---|---|---|
| `test_parallel_session_start_race` | `entity_registry/test_project_identity.py` | Two subprocesses fork simultaneously; both exit 0; final file is well-formed. |
| `test_parallel_first_creation` | same | When file does NOT exist, parallel writes resolve to a single valid UUID (one of the two; deterministic only after `mv`). |

### 7.6 Reverse migration end-to-end

| Test | Path | Asserts |
|---|---|---|
| `test_full_round_trip_with_real_db` | `entity_registry/test_database.py` | Take the live `~/.claude/pd/entities/entities.db` (copied to tmp), apply Migration 11 up + down, assert entities row count and content match (modulo timestamps). |

### 7.7 Reader call site tests

For every Python module rewritten in FR-9 / FR-10, an existing test is updated to use `workspace_uuid=` instead of `project_id=`. Test pass criteria: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/ plugins/pd/mcp/` returns 0 failures.

### 7.8 Doctor health check

| Test | Path | Asserts |
|---|---|---|
| `test_check_workspace_uuid_consistency_ok` | `doctor/test_checks.py` | File matches DB → OK. |
| `test_check_workspace_uuid_consistency_missing_file` | same | Missing file + populated DB → ERROR. |
| `test_check_workspace_uuid_consistency_empty_db` | same | Missing file + empty DB → WARN. |
| `test_check_workspace_uuid_consistency_legacy_mismatch` | same | File's `project_id_legacy` ≠ DB's → ERROR. |

### 7.9 F6 conditional tests (only run if Python ≥3.14 AND F6 lands)

| Test | Path | Asserts |
|---|---|---|
| `test_uuid7_when_available` | `entity_registry/test_database.py` | If `uuid.uuid7` exists, new entities have `version == 7`. |
| `test_uuid_v4_v7_coexist` | same | Mixed v4/v7 dataset queries cleanly via `idx_uuid` (PK). |

### 7.10 Test runner orchestration

```bash
plugins/pd/.venv/bin/python -m pytest \
  plugins/pd/hooks/lib/entity_registry/ \
  plugins/pd/hooks/lib/doctor/ \
  plugins/pd/hooks/lib/reconciliation_orchestrator/ \
  plugins/pd/hooks/lib/workflow_engine/ \
  plugins/pd/mcp/ \
  plugins/pd/ui/

bash plugins/pd/hooks/tests/test-hooks.sh
bash plugins/pd/hooks/tests/bench-session-start.sh
./validate.sh
```

All four commands must exit 0 for the feature to be considered complete.

---

## 8. Dependencies

### Within feature

```
F1 (workspace UUID)
  ├── F5 (drop parent_type_id) — independent code path; can ship same migration
  └── F6 (uuidv7)              — independent generator change; can ship anytime
```

- **F1 must land before F5 in the migration script** because the entities table rebuild that drops `parent_type_id` is the same `CREATE TABLE entities_new` step that adds `workspace_uuid`. Doing them in one migration (Migration 11) is more efficient than two consecutive table rebuilds.
- **F6 is independent** of F1 and F5; it only changes the UUID generator. It can ship in the same PR or be deferred to a backlog item without affecting the migration.

### External

- **None.** This is a Phase-0 feature and explicitly designed to land before Features 109/110/111.
- **Implicit:** SQLite (already a dependency), Python 3.12+ (already required by `pyproject.toml`).

### Downstream features blocked

- Feature 109 (Polymorphic Taxonomy) depends on `entities.workspace_uuid` existing.
- Feature 110 (Markdown Projections) depends on stable identity in Feature 109's schema.
- Feature 111 (Issue Lifecycle Closure) depends on Feature 109's event log keyed on workspace.

---

## 9. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Migration 11 doesn't cleanly map old `project_id` to new `workspace_uuid` for edge-case rows. | Med | High | Pre-migration audit query (Migration 11 step 0) emits `workspace-mapping.json` programmatically; AC-36 asserts mapping integrity post-migration. Test 7.6 takes the live DB as input. No "human review" stage required — verification is fully automated via AC-36. |
| R2 | Removing `parent_type_id` breaks readers we missed. | Low | High | `grep -rln 'parent_type_id' plugins/pd/ --include='*.py'` enumerates all **29 files** (12 production + 17 test) — FR-9 lists each. Post-drop runtime assertion (FR-14): pytest suite would fail with `OperationalError: no such column: parent_type_id` if any dynamic SQL referenced the dropped column. Static `grep` AC ensures zero hits in production code. Live DB state confirms 0 rows have only `parent_type_id`. |
| R3 | UUIDv7 introduces a stdlib dep that's not in the resolved venv (Python 3.14+ required). | High (today; floor is 3.12) | Low | F6 is conditional. Decision gate at start of implementation. Default expectation: F6 **deferred** because `pyproject.toml` floor is below 3.14. If implementer raises floor and gate passes, F6 ships. No `uuid7` third-party shim added. |
| R4 | Hooks regress on EPIPE handling because of new structured output paths. | Med | Med | All new hook output routes through `safe_emit_hook_json`. NFR2 bench is part of the test suite (NFR-5 AC). |
| R5 | Two parallel SessionStart processes corrupt workspace.json or return divergent UUIDs. | Low | Med | **fcntl.flock-based cross-process synchronization** (FR-2 AC + design Decision 9). Exclusive flock on `.claude/pd/workspace.json.lock` serializes parallel callers; both return the same UUID (winner's or pre-existing). Test 7.5 + AC-37 simulate the race via `multiprocessing.Pool(2)` with explicit fork barrier. The earlier "re-read after rename" approach was BROKEN and has been replaced. |
| R6 | User has hand-edited `.claude/pd/workspace.json` to a custom value. | Low | Low | Helper validates JSON schema strictly; rejects unknown top-level keys with WARN; rejects bad `schema_version` with ERROR. User can `rm` and re-create. |
| R7 | Down-migration restores `parent_type_id` with NULL values where `parent_uuid` resolves to a row outside the workspace. | Low | Med | Down-script's `parent_type_id` UPDATE joins on `parent_uuid → uuid → type_id` within the same workspace; cross-workspace `parent_uuid` references would already be schema violations pre-migration so this case cannot occur from valid pre-11 state. |
| R8 | Live `~/.claude/pd/entities/entities.db` is large enough that migration time exceeds NFR-6 target. | Low | Low | Live DB is ~452 entity rows; even with table rebuild, sub-2s. NFR-6 hard cap is 30s for safety. |
| R9 | Feature 109 contract changes break this migration's assumptions. | Low | High | This feature ships first; 109 builds on top. Explicit roadmap dependency. |
| R10 | Operator forgets to run `claim_unknown_entities` post-migration → orphan entities visible only under the canonical unknown-workspace UUID. | Med | Med | Production `__unknown__` rows are real (created by `claim_unknown_entities` path at `database.py:2580` and the `database.py:1013` DEFAULT) and are **mapped, not blocked**. Migration emits a WARN-level log per `__unknown__` row count (FR-7 step 0) reminding the operator to reattribute via `claim_unknown_entities`. Test fixtures rely on the same deterministic `_UNKNOWN_WORKSPACE_UUID` (FR-4) so tests are stable. Documented in EC-6. |

---

## 10. Open Questions

These are flagged for the design phase and must be resolved before plan creation.

- **OQ-1:** Should `workspace.json` track the user identity (e.g., `created_by_user`) or remain process-only? **Resolution:** No — workspaces are per-`.claude/` dir, not per-user. User identity belongs in a different layer.
- **OQ-2:** Should we add a `workspace_url` (e.g., remote git URL) field to the `workspaces` table for human display? **Resolution:** No, that's already in the existing `projects` table. `workspaces` keeps minimal columns; rich display data lives in `projects`.
- **OQ-3:** Should the deterministic UUID for `__unknown__` legacy_id be derived from an explicit seed constant or computed at migration time? **Resolution:** **Resolved in FR-4.** Single canonical seed string `"pd-test-fixture-unknown-workspace"` (constant `_UNKNOWN_WORKSPACE_UUID_SEED`); derived UUID stored once as `_UNKNOWN_WORKSPACE_UUID`; v4 formatting algorithm spelled out in FR-4 (8-4-4-4-12 hex from sha256, version nibble forced to 4, variant nibble to {8,9,a,b} per RFC 4122). **Both production AND test** `__unknown__` rows map to this UUID — production rows arise legitimately via `claim_unknown_entities` (`database.py:2580`) and the `database.py:1013` DEFAULT. Migration WARN-logs the count (FR-7 step 0) and operator reattributes post-migration via `claim_unknown_entities`.

---

## 11. Provenance

This spec is derived from:

- **PRD:** `docs/projects/P003-entity-system-redesign/prd.md` (sections "Solution Approach" Feature 1, "User Story 1", "Inter-Feature Dependencies", "Constraints").
- **Roadmap:** `docs/projects/P003-entity-system-redesign/roadmap.md` (Execution Order item 1, M1 milestone).
- **Live DB verification (2026-05-10):**
  - `sqlite3 ~/.claude/pd/entities/entities.db "SELECT DISTINCT project_id, COUNT(*) FROM entities GROUP BY project_id"` → 3 workspaces, 452 entities.
  - `sqlite3 ... "SELECT 'only_uuid', COUNT(*) FROM entities WHERE parent_uuid IS NOT NULL AND parent_type_id IS NULL UNION ALL SELECT 'both', COUNT(*) FROM entities WHERE parent_uuid IS NOT NULL AND parent_type_id IS NOT NULL UNION ALL SELECT 'only_type_id', COUNT(*) FROM entities WHERE parent_uuid IS NULL AND parent_type_id IS NOT NULL"` → 22 / 88 / 0.
  - `sqlite3 ... "SELECT value FROM _metadata WHERE key='schema_version'"` → `10`.
- **Code state verified:** `database.py` Migration 6 (line 530), Migration 7 (line 913), Migration 8 (line 1000); `register_entity` (line 2083); UUID generator call sites (lines 167, 2145, 3846); 9 entity triggers; 8 entity indexes including `idx_project_id`, `idx_project_entity_type`, `idx_parent_type_id`.
- **`grep -rln` enumerations (verified live 2026-05-10):**
  - `grep -rln 'parent_type_id' plugins/pd/ --include='*.py'` → **29 files** (12 production + 17 test). Full list in FR-9.
  - `grep -rln '\bproject_id\b' plugins/pd/ --include='*.py' --include='*.sh'` → **55 files** (will be regenerated at implementation start per FR-10).

---

## 12. Document Conventions

- All file paths absolute when in code, relative when in docs (per repo convention).
- Schema changes show full DDL, not deltas.
- Tests cite the file path where they will live.
- Live DB queries are committed as scripts under `docs/features/108-workspace-identity-foundation/verify-queries.sh` (created during implementation, not part of this spec).
- `workspace_uuid` is always lowercase, hyphenated, 36 chars (`xxxxxxxx-xxxx-Mxxx-Nxxx-xxxxxxxxxxxx`).
