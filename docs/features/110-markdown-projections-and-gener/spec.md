# Feature 110 — Markdown Projections and Generalized Guards

- **Project:** P003-entity-system-redesign — Milestone M3 (Phase 3 — Projections and Guards)
- **Depends on:** 109-polymorphic-taxonomy-and-event (post-migration-12 baseline)
- **Brainstorm source:** `docs/projects/P003-entity-system-redesign/prd.md`
- **Status:** revision 2 (4 blockers + 8 warnings + 2 suggestions resolved)

## §1 Background and SUT-Verified Baseline

This feature is decomposed from project P003 Phase 3. It bundles three sub-features under one feature directory:

- **F4 — Markdown-as-projection:** Make `.meta.json` and `docs/backlog.md` read-only projections of DB state. Gitignore both. Emit `pd-state.diff.md` for PR review.
- **F7 — Generalized data-file guard:** Replace the hardcoded `.meta.json` guard with a config-driven dispatch table covering N data-file patterns.
- **F8 — entity_display(uuid, seq, slug) table:** Separate identity (`uuid`) from display metadata (`seq`+`slug`).

### §1.1 Pre-spec codebase-explorer survey + empirical SUT pins

Per the feature-109 KB heuristic *Run codebase-explorer Before Spec Iter-1 for Schema-Migration Features*, the following table is grounded in `grep`/`sqlite3` results from 2026-05-14. Symbol references are used where line numbers might drift; line numbers are spot-verified for stability.

| Concern | Empirical SUT pin | Spec implication |
|---|---|---|
| `_project_meta_json` (projection function) | `workflow_state_server.py:373` (def). Callers at `:767, :992, :1309`. | Mature projection function; reuse as-is. |
| `_write_meta_json_fallback` (degraded-mode writer) | `engine.py:444` (def). | Residual non-projection writer #1 (retained, audit-commented). |
| `init_project_state` (project-type writer) | `feature_lifecycle.py:223` (def). | Residual non-projection writer #2 — see decision below. |
| `_fix_update_meta_json` (doctor autofix writer) | Function name searched in `plugins/pd/hooks/lib/doctor/fix_actions.py` — symbol present per SUT explorer. | Residual non-projection writer #3 — see decision below. |
| Backlog writers | Four sites: `add-to-backlog.md:51-59`, `finish-feature.md:414`, `cleanup_backlog.py:165`, `fix_actions.py:150-159`. | Port to `_project_backlog_md` OR retain with `# F4-AUDIT:` comment. |
| Existing `meta-json-guard.sh` | `plugins/pd/hooks/meta-json-guard.sh` — lone path-based data-file guard. Hardcodes `*.meta.json`. | FR-7 generalizes one current instance. |
| Config-routing patterns | None in `plugins/pd/hooks/`. Bash-from-shell Python dispatch precedent exists at `plugins/pd/hooks/lib/session-start-helpers.sh` (loads venv + invokes `python3 -m` with `PYTHONPATH`). | Reuse the session-start venv-invocation pattern for decision-module dispatch (FR-7 feasibility anchor). |
| Display-metadata storage today | NO `display_seq`/`display_slug` columns. `entities.entity_id` holds composite `{seq}-{slug}`. `entities.metadata` JSON ALSO carries `id` + `slug` (redundant copy). | FR-8 introduces `entity_display`. Backfill audits `entity_id` vs `metadata` for divergence (see FR-8.2-pre). |
| Callers parsing `entity_id` for seq/slug | Four sites: `database.py:899-906` (`scan_entity_ids`); `workflow_state_server.py:373,416-418` (`_project_meta_json`); `backfill.py` (slug extraction); `show-status.md:99,124` (skill prose). | FR-8.3 ports each. |
| `.gitignore` status | Contains neither `**/.meta.json` nor `docs/backlog.md`. `git ls-files \| grep "\\.meta\\.json$" \| wc -l` returns **132**. `docs/backlog.md` is tracked. | FR-4.5 gitignores both AND removes 132 `.meta.json` tracked copies + the single `docs/backlog.md`. |
| `entity_type` column post-migration-12 | **Source code schema:** Migration 12 includes a `DROP COLUMN entity_type` step (database.py:3195 "F11 DROP COLUMN entity_type (Group 7, Task 7.3)"). `MIGRATIONS_DOWN[12]` "restores entity_type column + backfill from kind" (database.py:3580). **Live DB (today):** `PRAGMA table_info(entities)` shows `entity_type` present (live DB is stale at pre-12; per feature-109 retro this is a flagged pre-existing condition, deferred for manual intervention). | Migration 13 must **verify schema_version ≥ 12 AND `entity_type` column absent** as a pre-flight check. If absent, proceed. If present (stale live DB), migration 13 ABORTS with explicit error pointing to feature-109 deferred remediation. Feature 110 does NOT attempt to fix the live-DB stale state — that is feature-109-leftover scope. |
| Post-migration-12 entities columns (source-of-truth) | `uuid, workspace_uuid, type_id, entity_id, name, status, parent_uuid, artifact_path, created_at, updated_at, metadata, type, kind, lifecycle_class` (14 columns). UNIQUE(workspace_uuid, type_id). | FR-8.1 entity_display joins on `entities.uuid`. |
| `schema_version` baseline | `12` per `database.py:3475-3479`. | Migration 13 sets `13`. |

**Decision recorded for R1 (init_project_state semantics):** `_project_meta_json` reconstructs feature-type `.meta.json` from entity row + engine state. The project-type schema in `init_project_state` writes a different shape (e.g., `id`, `name`, `description`, `features[]`, `created`). Per the project-row decision in P003 PRD §6 (out-of-scope for 110), **project-type `.meta.json` write semantics are NOT ported in feature 110**. `init_project_state` is annotated with `# F4-AUDIT: project-type schema differs; port deferred to feature 111` and the FR-7 guard table excludes `projects/*/.meta.json` from the guard pattern. FR-4.1 enumerates ONLY the two residual feature-type writers (`_write_meta_json_fallback`, `_fix_update_meta_json`).

**Decision recorded for R2 (doctor autofix surface):** `_fix_update_meta_json` is replaced. Doctor autofix invokes `complete_phase` / `transition_phase` MCP tools (which trigger projection); if the autofix surface cannot detect which MCP tool to invoke from the drift type, the autofix degrades to a non-autofix WARN-only finding (user sees the drift and must run MCP themselves). This is bounded scope — no semantic regress.

**Persistent decomposition warning (from parent PRD, acknowledged non-blocking):** Feature 110 bundles projection (read-path) and guard (write-path) responsibilities. Reassess at plan time if >800 LOC.

## §2 Goals

1. **Mathematical drift impossibility:** `.meta.json` and `docs/backlog.md` content is a deterministic function of DB state. Deleting either file does not change entity status; regenerating produces byte-identical output.
2. **Sealed write path for feature-type artifacts:** Only the projection functions (`_project_meta_json` for feature `.meta.json`, the new `_project_backlog_md` for backlog) write to these files. Project-type `.meta.json` writers are out-of-scope (feature 111).
3. **PR review diff artifact:** Pre-commit hook emits `pd-state.diff.md` summarizing entity-state changes between HEAD and base branch.
4. **Path-pattern guard:** Adding a new guarded file pattern requires only a config entry — no new shell script per pattern.
5. **Display/identity separation:** Renaming an entity's display slug or seq changes a side table, not `entities.uuid`.

## §3 Functional Requirements

### FR-4 — Markdown projection (sealed write path + diff artifact)

- **FR-4.1 — Audit + dispose of residual `.meta.json` writers.**
  - `engine.py:444 _write_meta_json_fallback` (degraded-mode): retain. Add inline `# F4-AUDIT: degraded-mode-only` comment. AST/grep test (AC-1.1) asserts it is the ONLY write site in `workflow_engine/`.
  - `feature_lifecycle.py:223 init_project_state`: retain WITH `# F4-AUDIT: project-type schema differs; ported to feature 111` comment. (Per §1.1 R1 decision.)
  - `fix_actions.py _fix_update_meta_json`: REMOVED. Replaced with a wrapper that invokes `complete_phase` / `transition_phase` MCP for drift modes the autofix understands. For undetectable drift modes, downgraded to WARN-only doctor finding. (Per §1.1 R2 decision.)
- **FR-4.2 — Add `_project_backlog_md(db)` projection function.** New function in `workflow_state_server.py` (sibling of `_project_meta_json`). Reconstructs `docs/backlog.md` from DB state. Output is byte-deterministic (sorted by ID ascending; category section ordering preserved as DB metadata).
- **FR-4.3 — Port backlog writers to projection or annotate.**
  - `add-to-backlog.md:51-59`: invokes a new write-helper that does `register_entity(entity_type='backlog', ...)` + calls `_project_backlog_md` to regenerate the file. The skill stops directly writing to backlog.md.
  - `finish-feature.md:414` (MED-finding auto-file): same pattern — register backlog entries via DB, then projection regenerates the file.
  - `cleanup_backlog.py:165`: REMOVED. The cleanup-archival behavior moves to a DB `status='archived'` flag; projection emits archived rows under a separate section.
  - `fix_actions.py:150-159 _fix_annotate_backlog`: retain WITH `# F4-AUDIT: annotation-only; not a state mutation` comment.
- **FR-4.4 — Determinism + idempotency.** Projection functions MUST source all timestamp fields from `entities.updated_at`/`entities.created_at` columns (read from DB row state, NEVER from `datetime.utcnow()` at projection time). Two consecutive invocations against unchanged DB state produce byte-identical output (sorted keys, fixed line endings, stable section ordering). Volatile fields enumerated: NONE (every field traces to a DB column).
- **FR-4.5 — Gitignore + tracked-copy removal.** Add `**/.meta.json` and `docs/backlog.md` to `.gitignore`. SAME commit runs `git rm --cached docs/features/*/.meta.json` (132 files per §1.1 SUT pin) and `git rm --cached docs/backlog.md`. Working-tree copies are untouched (regenerable via projection).
- **FR-4.6 — `pd-state.diff.md` generator (gitignored local artifact).** New script `plugins/pd/scripts/pd_state_diff.py` emits a markdown diff of (uuid, type_id, status, workflow_phase, parent_type_id) between HEAD and base branch. Wired into `pre-commit-guard.sh` which writes the file to repo root for local PR-prep. **`pd-state.diff.md` is added to `.gitignore` per AC-6.3 — it is NOT committed.** No `finish-feature.md` Step 5 integration (prior rev-1 wording removed).
- **FR-4.7 — Hand-editing safety.** Deleting `.meta.json` files does NOT change any row in `entities`, `workflow_phases`, or `phase_events`. AC-4.5 enforces.

### FR-7 — Generalized data-file guard

- **FR-7.1 — Config schema + module-lookup path env-overridability.** New file `plugins/pd/hooks/data_file_guards.json` with schema:
  ```json
  [
    {
      "pattern": "*.meta.json",
      "exclude_patterns": ["docs/projects/**/.meta.json"],
      "decision_module": "data_file_guards.meta_json_decision",
      "mcp_tool_hint": "complete_phase / transition_phase"
    },
    {
      "pattern": "docs/backlog.md",
      "decision_module": "data_file_guards.backlog_decision",
      "mcp_tool_hint": "/pd:add-to-backlog or update via DB then re-project"
    }
  ]
  ```
  Path resolution: config path defaults to `plugins/pd/hooks/data_file_guards.json`, overridable via env var `PD_DATA_FILE_GUARDS_CONFIG`. Decision module import root defaults to `plugins/pd/hooks/lib/`, overridable via `PD_DATA_FILE_GUARDS_LIB`. `exclude_patterns` (optional) excludes paths from the pattern (per §1.1 R1: `docs/projects/**/.meta.json` excluded so project-type writers continue working without trigger).
- **FR-7.2 — Dispatch loop.** New `plugins/pd/hooks/data-file-guard.sh` reads stdin once, sources `lib/session-start-helpers.sh` to load venv (per §1.1 FR-7 feasibility anchor), invokes `python3 -m data_file_guards.dispatcher <stdin>`. The Python dispatcher iterates config entries in declared order, runs `fnmatch.fnmatch(file_path, pattern)` AND none-of `exclude_patterns` match, and on first match invokes `decision_module.decide(file_path, tool_name, payload)`. Returns `hookSpecificOutput.permissionDecision=deny|allow` per the decision module.
- **FR-7.3 — Remove `meta-json-guard.sh`.** The file `plugins/pd/hooks/meta-json-guard.sh` is DELETED in the same commit. No shim retained. AC-7.6 enforces.
- **FR-7.4 — Hook registration.** `plugins/pd/.claude-plugin/hooks.json` registers `data-file-guard.sh` exactly once under `PreToolUse`. The `meta-json-guard.sh` registration entry is removed in the same commit.
- **FR-7.5 — Hot-add new pattern (config-driven, no script change).** Adding a new entry to `data_file_guards.json` and implementing its decision module under `plugins/pd/hooks/lib/data_file_guards/` requires NO change to `data-file-guard.sh` or the dispatcher. Integration test verifies this via `PD_DATA_FILE_GUARDS_CONFIG` + `PD_DATA_FILE_GUARDS_LIB` env overrides pointing at fixture files in `plugins/pd/hooks/tests/fixtures/`.

### FR-8 — entity_display(uuid, seq, slug)

- **FR-8.1 — Schema.** Migration 13 adds:
  ```sql
  CREATE TABLE entity_display (
    uuid TEXT PRIMARY KEY,
    seq INTEGER NOT NULL,
    slug TEXT NOT NULL,
    FOREIGN KEY (uuid) REFERENCES entities(uuid) ON DELETE CASCADE
  );
  CREATE INDEX idx_entity_display_seq ON entity_display(seq);
  ```
  Migration uses `PRAGMA table_info(entities)` runtime discovery (per FR-5.6) to confirm `entities.uuid` exists before adding the FK.
- **FR-8.2-pre — Pre-migration mismatch audit (mandatory).** Before any backfill INSERT, migration 13 runs:
  ```sql
  SELECT uuid, entity_id, json_extract(metadata, '$.id') AS meta_id,
         json_extract(metadata, '$.slug') AS meta_slug
  FROM entities
  WHERE json_extract(metadata, '$.slug') IS NOT NULL
    AND json_extract(metadata, '$.slug') != substr(entity_id, instr(entity_id, '-') + 1)
  ```
  Each mismatch row is logged to `migration_13_mismatch_log` (new table or `phase_events` row with `event_type='migration_audit'`). If `count > 0`, migration 13 ABORTS with error message listing UUIDs and instructions to manually reconcile, UNLESS the env var `PD_MIGRATION_13_ACCEPT_ENTITY_ID_WINS=1` is set (acknowledgement gate). AC-8.0 enforces.
- **FR-8.2 — Backfill at migration time.** Migration 13 populates `entity_display` for every row in `entities` by parsing `entities.entity_id` (format `{seq}-{slug}`). `seq` = numeric prefix; `slug` = suffix after first `-`. Pre-audit (FR-8.2-pre) guarantees `metadata['slug']` matches `entity_id` suffix, so the choice is unambiguous.
- **FR-8.3 — Port the four caller sites:**
  - `database.py:899-906 scan_entity_ids`: replace regex-on-`entity_id` with `SELECT COALESCE(MAX(seq), 0) FROM entity_display d JOIN entities e ON d.uuid = e.uuid WHERE e.workspace_uuid = ?`.
  - `workflow_state_server.py:373,416-418 _project_meta_json`: query `entity_display` instead of `metadata['id']`/`metadata['slug']`. If `entity_display` row missing (defense-in-depth), fall back to `metadata` with WARN log.
  - `backfill.py`: query `entity_display` instead of parsing `entity_id`.
  - `show-status.md:99,124`: skill prose update to reference `entity_display`.
- **FR-8.4 — Rename without rewrite.** AC-8.6 enforces: `UPDATE entity_display SET slug='renamed' WHERE uuid = ?` changes `.meta.json` projection output's `slug` field BUT leaves `entities` and `phase_events` tables byte-identical at the SQL dump level.
- **FR-8.5 — Identity stability under rename.** AC-8.7 enforces: after slug rename, `parent_uuid` references from child entities still resolve correctly.
- **FR-8.6 — Down-migration.** `MIGRATIONS_DOWN[13]` drops `entity_display` table + `idx_entity_display_seq` index. Drops the `migration_13_mismatch_log` table if present. Source-code restore is via git history (per feature-109 precedent).

### FR-5 — Migration 13 safety

- **FR-5.1 — Single-transaction discipline.** Migration 13 wraps all DDL + audit + backfill in `BEGIN IMMEDIATE` with `PRAGMA foreign_key_check` pre- and post-commit. On any check failure, rollback and surface the error.
- **FR-5.2 — Idempotency.** Re-running migration 13 against `schema_version=13` is a no-op (early return inside transaction).
- **FR-5.3 — Schema version stamp.** Migration 13 sets `PRAGMA user_version = 13` AND `INSERT INTO schema_version (version, applied_at) VALUES (13, ?)` inside the same transaction.
- **FR-5.4 — Reverse migration.** `MIGRATIONS_DOWN[13]` drops `entity_display`, `idx_entity_display_seq`, and `migration_13_mismatch_log` if present.
- **FR-5.5 — Pre-flight schema gate.** Migration 13 first asserts (a) `PRAGMA user_version` returns 12 (NOT 11 or less); (b) `PRAGMA table_info(entities)` returns the 14-column post-12 layout with `entity_type` ABSENT, `type`/`kind`/`lifecycle_class` PRESENT. If gate fails, migration ABORTS with explicit error pointing at feature-109's deferred live-DB remediation. No partial-state mutation.
- **FR-5.6 — Runtime schema introspection (no hardcoded column lists in backfill SELECT).** Migration 13's backfill SQL uses `PRAGMA table_info(entities)` to verify `uuid`, `entity_id`, `metadata` columns exist before issuing any SELECT. If expected columns absent, ABORT with error. No hardcoded column-list assumptions in backfill code.

## §4 Acceptance Criteria

### AC-1.x — Code-surface acceptance (AST-based, per feature-109 KB pattern)

- **AC-1.1** AST test `test_audit_writes.py::test_no_unaudited_meta_json_writes` walks `plugins/pd/hooks/lib/workflow_engine/`, `plugins/pd/mcp/`, `plugins/pd/hooks/lib/doctor/` (excludes `*/tests/*`). For every `Call` node targeting `.meta.json` writes (matches `open(...,'w')`, `Path(...).write_text(...)`, `json.dump(fp, ...)` with `fp` opened on a `.meta.json` path), assert the enclosing function name is one of the FR-4.1 allow-list: `_project_meta_json`, `_write_meta_json_fallback`, `init_project_state`. Any other match FAILS the test. Each allow-listed match must also have a `# F4-AUDIT:` comment within 5 lines (AC-1.1b).
- **AC-1.2** AST test `test_audit_writes.py::test_no_unaudited_backlog_md_writes` similarly walks for `backlog.md` writes; allow-list is `_project_backlog_md`, `_fix_annotate_backlog`. (Other writes must be replaced by FR-4.3 to call `_project_backlog_md`.)
- **AC-1.3** `python3 -c "from workflow_state_server import _project_backlog_md; print(callable(_project_backlog_md))"` prints `True` after install. (Module path matches actual import root.)
- **AC-1.4** `cat .gitignore | grep -E "^\*\*/\.meta\.json$"` returns 1 match AND `cat .gitignore | grep -E "^docs/backlog\.md$"` returns 1 match AND `cat .gitignore | grep -E "^pd-state\.diff\.md$"` returns 1 match.
- **AC-1.5** `git ls-files | grep -E "(\.meta\.json|^docs/backlog\.md|^pd-state\.diff\.md)$"` returns 0 lines post-commit. Pre-commit baseline (for visibility): 132 `.meta.json` + 1 `docs/backlog.md` = 133 files removed from index.

### AC-4.x — Projection determinism + idempotency

- **AC-4.1** Two consecutive `_project_meta_json(db, engine, type_id)` invocations against unchanged DB state produce byte-identical bytes. Test enforces by computing `hashlib.sha256` of both outputs. Implementation requirement: ALL timestamp fields source from `entities.updated_at` / `entities.created_at` columns; NO `datetime.utcnow()` call in the projection code path. Test verifies via static check: `grep -nE "datetime\.(utcnow|now)\b" plugins/pd/mcp/workflow_state_server.py` returns no matches inside the `_project_meta_json` body.
- **AC-4.2** Two consecutive `_project_backlog_md(db)` produce byte-identical output. Same hash-equality test. Same static-check for absent `datetime.utcnow()`.
- **AC-4.3** Delete a `.meta.json` file → re-invoke `_project_meta_json(...)` → file matches pre-delete bytes byte-for-byte.
- **AC-4.4** Delete `docs/backlog.md` → re-invoke `_project_backlog_md` → file matches pre-delete bytes byte-for-byte.
- **AC-4.5** Manually edit `.meta.json` (append `"tampered": true`) → `SELECT status FROM entities WHERE type_id = ?` returns the same value before and after. Re-invoking projection overwrites the tampered file with canonical content.

### AC-5.x — Migration 13 safety

- **AC-5.1** Migration 13 runs in a single `BEGIN IMMEDIATE` transaction. `PRAGMA foreign_key_check` returns zero rows both pre-COMMIT and post-COMMIT.
- **AC-5.2** Idempotency: running migration 13 twice yields identical schema_version=13 and identical `entity_display` row count; no duplicate-key errors.
- **AC-5.3** `PRAGMA user_version` returns 13 post-migration. `schema_version` table has row `(13, <iso ts>)`.
- **AC-5.4** `MIGRATIONS_DOWN[13]` drops the three artifacts (`entity_display`, `idx_entity_display_seq`, `migration_13_mismatch_log` if present). Post-down: `PRAGMA user_version` returns 12.
- **AC-5.5** Round-trip safety: up → down on a 100-row fixture DB leaves `entities`, `workflow_phases`, `phase_events` byte-identical (sqlite3 `.dump` compare).
- **AC-5.6** Pre-flight gate (FR-5.5): synthetic test using a stale-schema DB (entity_type column present, type/kind absent) asserts migration 13 ABORTS with error containing the phrase "feature 109" before any DDL is issued. DB state unchanged after the failed run.
- **AC-5.7** Runtime introspection (FR-5.6): backfill SQL uses `PRAGMA table_info` results to validate column presence. Synthetic test: drop `metadata` column from a fixture DB → migration aborts with column-missing error; entity_display table is NOT created.

### AC-6.x — `pd-state.diff.md` generator (gitignored)

- **AC-6.1** `python plugins/pd/scripts/pd_state_diff.py --base develop` against a clean checkout writes `pd-state.diff.md` containing zero entity-state-change rows OR the literal text `No entity state changes vs develop`.
- **AC-6.2** Same script run after a synthetic `register_entity` produces a row containing the new uuid, type_id, status=`active`, parent_type_id (or empty), and an `(added)` marker.
- **AC-6.3** `pre-commit-guard.sh` invokes `pd_state_diff.py` (via plugin venv) and writes `pd-state.diff.md` BEFORE the commit completes. The file is **gitignored** (FR-4.6 / AC-1.4 enforces). Not committed.
- **AC-6.4** Empty-tree branch run shows literal `No entity state changes vs {base}`.
- **AC-6.5** Performance: `time python plugins/pd/scripts/pd_state_diff.py --base develop` against a 500-row fixture DB completes in < 500 ms (measured wall-clock). Test fails if exceeded.
- **AC-6.6** Missing-base graceful degrade: if the base branch ref is absent (e.g., fresh clone with no `develop` ref), script emits `pd-state diff unavailable: base ref '{base}' not found` to `pd-state.diff.md` and exits 0. Does NOT block the commit.

### AC-7.x — Generalized guard

- **AC-7.1** `plugins/pd/hooks/data_file_guards.json` exists, parses as JSON, contains ≥ 2 entries matching FR-7.1 (with `exclude_patterns` field present on the `*.meta.json` entry).
- **AC-7.2** `data-file-guard.sh` exists, is executable, is registered exactly once in `plugins/pd/.claude-plugin/hooks.json` under `PreToolUse`. `meta-json-guard.sh` is NOT in `hooks.json`.
- **AC-7.3** Write/Edit of a `docs/features/*/.meta.json` outside the projection path is denied; reason text contains `complete_phase / transition_phase`.
- **AC-7.4** Write/Edit of `docs/backlog.md` outside the projection path is denied; reason text contains `/pd:add-to-backlog` OR `update via DB then re-project`.
- **AC-7.5** Hot-add (config-driven): integration test sets `PD_DATA_FILE_GUARDS_CONFIG=plugins/pd/hooks/tests/fixtures/test_data_file_guards.json` and `PD_DATA_FILE_GUARDS_LIB=plugins/pd/hooks/tests/fixtures/`, adds a `test_fixture.md` pattern with a fixture decision module, runs the dispatch hook with a Write tool input on `test_fixture.md`, asserts the deny path executes. `data-file-guard.sh` is NOT modified (git diff is empty for that file in the test setup).
- **AC-7.6** File `plugins/pd/hooks/meta-json-guard.sh` does NOT exist in tree post-feature (`test -f` returns nonzero).
- **AC-7.7** `docs/projects/**/.meta.json` paths are NOT denied (per `exclude_patterns`); regression test exercises project-type write and verifies the hook permits.

### AC-8.x — entity_display table

- **AC-8.0** Pre-migration mismatch audit (FR-8.2-pre): the audit query returns 0 rows on a clean fixture DB. On a DB with synthetic mismatch (manually edit `metadata` JSON to differ from `entity_id` suffix), migration ABORTS unless `PD_MIGRATION_13_ACCEPT_ENTITY_ID_WINS=1` is set. With the env set, migration proceeds and writes the mismatch to `migration_13_mismatch_log`.
- **AC-8.1** Post-migration: `PRAGMA table_info(entity_display)` returns columns `uuid`, `seq`, `slug`. Index `idx_entity_display_seq` exists per `sqlite_master`.
- **AC-8.2** Post-migration: every row in `entities` has a corresponding row in `entity_display` joined on `uuid` (`SELECT COUNT(*) FROM entities WHERE uuid NOT IN (SELECT uuid FROM entity_display)` returns 0).
- **AC-8.3** Backfill correctness: for each row, `entity_display.seq` = `CAST(substr(entities.entity_id, 1, instr(entities.entity_id, '-') - 1) AS INTEGER)` AND `entity_display.slug` = `substr(entities.entity_id, instr(entities.entity_id, '-') + 1)`. Test runs this SQL and asserts zero divergence rows.
- **AC-8.4** `scan_entity_ids` returns the same `max_seq` value pre- and post-migration when DB content is unchanged.
- **AC-8.5** `_project_meta_json` reads `id`/`slug` from `entity_display`. Test deletes the `id`/`slug` keys from `metadata` JSON post-migration, re-projects, and asserts `.meta.json` output is byte-identical to projection before the metadata edit.
- **AC-8.6** Slug rename: `UPDATE entity_display SET slug='renamed-slug' WHERE uuid = ?` followed by `_project_meta_json(type_id)` shows new slug in output. Full SQL `.dump` of `entities WHERE uuid = ?` AND full `.dump` of `phase_events` are byte-identical to pre-rename state (NO `entities.updated_at` change, NO `phase_events` row appended). This is enforced via sqlite3 dump comparison, not column-level grep.
- **AC-8.7** Identity stability under rename: child entities (where `parent_uuid = ?`) still resolve to the renamed parent. Test creates parent + child, renames parent slug, queries child's parent via uuid join, asserts parent uuid + entity_id + type_id unchanged.

## §5 Non-Functional Requirements

- **NFR-1 — Atomic commit discipline.** Each Group (sub-feature) is its own commit with passing tests at every boundary. No mixed F4/F7/F8 commits.
- **NFR-2 — No new third-party dependencies.** Stdlib + existing project deps (`sqlite3`, `pathlib`, `json`, `subprocess`, `fnmatch`, `ast`) only.
- **NFR-3 — Bash 3.2 / macOS BSD portability.** `data-file-guard.sh` runs under bash 3.2. Verified via `/bin/bash` harness test.
- **NFR-4 — Hook EPIPE safety.** `data-file-guard.sh` uses `safe_emit_hook_json` per feature 107 contract.
- **NFR-5 — Idempotent migrations.** Migration 13 is replay-safe per AC-5.2.

## §6 Out of Scope (Deferred)

- F6 `issue_spawn` MCP tool — feature 111 scope.
- F9 `complete_phase(closes=[...])` cascade closure — feature 111 scope.
- F10 free-text suffix parsing removal — feature 111 scope.
- Workspace-scoped slug uniqueness on `entity_display` — future enhancement.
- `pd-state.diff.md` rendering in CI / GitHub Actions integration — local pre-commit only.
- `init_project_state` port to `_project_meta_json` — deferred per §1.1 R1 decision (project-type schema differs).
- Live-DB stale-schema remediation (DB at pre-12 instead of expected 12) — deferred per feature-109 retro; migration 13 ABORTS rather than attempting to fix.

## §7 Open Risks

- **R3 — Backfill mismatch (FR-8.2-pre).** Addressed by mandatory pre-audit + abort-unless-acknowledged env var. Residual risk: env-var bypass on a busy DB hides drift. Plan phase to add post-migration verification log.
- **R4 — `pd-state.diff.md` performance.** Capped at 500ms per AC-6.5. If exceeded, design decides async-defer pattern (e.g., compute lazily during PR creation rather than every commit).
- **R5 — Doctor autofix regression (FR-4.1 _fix_update_meta_json).** Replacement may not handle all drift modes; degraded WARN-only fallback is documented. Plan must include explicit AC for each drift mode currently autofixed.
- **R6 — venv-from-bash bootstrap (FR-7.2).** Decision-module dispatch loads venv from `session-start-helpers.sh` precedent. If venv path discovery fails under hook context, dispatch must degrade to allow (fail-open) rather than block writes. Plan to add fallback AC.

## §8 Verification Mapping

| AC | Verification mechanism | Test file |
|---|---|---|
| AC-1.1, AC-1.2 | AST walk + comment proximity | `plugins/pd/hooks/lib/doctor/test_audit_writes.py` |
| AC-1.3 | import smoke test | `test_projection_helpers.py` |
| AC-1.4, AC-1.5 | `.gitignore` parse + `git ls-files` | `test_gitignore_drift.py` |
| AC-4.x | hashlib.sha256 byte-equality + static `datetime.utcnow` check | `test_projection_determinism.py` |
| AC-5.x | migration runner + `PRAGMA foreign_key_check` + pre-flight gate | `test_migration_13_safety.py` |
| AC-6.x | script invocation + `time` + parse | `test_pd_state_diff.py` |
| AC-7.x | hook integration test (shell harness with env overrides) | `plugins/pd/hooks/tests/test-data-file-guard.sh` + `tests/fixtures/` |
| AC-8.0, AC-8.x | DB introspection + integration test + `.dump` compare | `test_entity_display_table.py` |
