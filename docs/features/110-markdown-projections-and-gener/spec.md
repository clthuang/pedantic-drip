# Feature 110 — Markdown Projections and Generalized Guards

- **Project:** P003-entity-system-redesign — Milestone M3 (Phase 3 — Projections and Guards)
- **Depends on:** 109-polymorphic-taxonomy-and-event (schema_version 12 baseline)
- **Brainstorm source:** `docs/projects/P003-entity-system-redesign/prd.md` (parent PRD covers F4 + F7 + F8 scope)
- **Status:** revision 1

## §1 Background and SUT-Verified Baseline

This feature is decomposed from project P003 Phase 3. It bundles three sub-features under one feature directory:

- **F4 — Markdown-as-projection:** Make `.meta.json` and `docs/backlog.md` read-only projections of DB state. Gitignore both. Emit `pd-state.diff.md` for PR review.
- **F7 — Generalized data-file guard:** Replace the hardcoded `.meta.json` guard with a config-driven dispatch table covering N data-file patterns.
- **F8 — entity_display(uuid, seq, slug) table:** Separate identity (`uuid`) from display metadata (`seq`+`slug`). Removes the composite-id rename impossibility described in the parent PRD.

**Pre-spec codebase-explorer survey (pinned for traceability, per SUT-verification heuristic from feature 109 KB):**

| Concern | Empirical SUT state | Spec implication |
|---|---|---|
| F4 — `_project_meta_json()` projection function | Already exists at `workflow_state_server.py:373`. Called post-`transition_phase`, `complete_phase`, `init_feature_state`, `activate_feature`. Reconstructs `.meta.json` from DB+engine state with fail-open semantics. | Projection function is mature; F4 work is sealing the write path (kill non-projection writers) + adding `project_backlog_md()` analog + gitignore entries + `pd-state.diff.md` generator. |
| F4 — non-projection writers of `.meta.json` | Three residual sites: (a) `engine.py:450-477` `_write_meta_json_fallback` (degraded-mode only); (b) `feature_lifecycle.py:285-298` `init_project_state` (project type writes directly via `open()`); (c) `fix_actions.py:53-95` `_fix_update_meta_json` (doctor autofix). | FR-4.1/FR-4.2 must enumerate ALL THREE residual write sites and dispose of each (kill, port to `_project_meta_json`, or document why retained). |
| F4 — backlog writers | Four sites: `add-to-backlog.md:51-59`, `finish-feature.md:414`, `cleanup_backlog.py:165`, `fix_actions.py:150-159`. | FR-4.3/FR-4.4 must port these to a new `project_backlog_md()` analog OR migrate them to `issue_spawn` MCP (per parent PRD F6) — feature-110 scope adopts the projection path; MCP migration is feature 111 (F6/F9). |
| F4 — gitignore status | `.gitignore` contains neither `**/.meta.json` nor `docs/backlog.md`. Both currently tracked. | FR-4.5 adds both to `.gitignore`; existing tracked copies removed in same commit. |
| F7 — existing guards | `meta-json-guard.sh` (the lone path-based data-file guard) hardcodes `*.meta.json`. Other guards (`pre-commit-guard.sh`, `yolo-guard.sh`, `pre-exit-plan-review.sh`) are not path-based. | FR-7 generalizes ONLY the data-file guard surface (one current instance: meta-json-guard). It adds a `data_file_guards.json` config table and routes `meta-json-guard.sh` + future `backlog-guard.sh` through it. |
| F7 — config-routing patterns | None exist. No JSON/YAML map drives guard behavior anywhere in `plugins/pd/hooks/`. | FR-7 introduces a new convention; AC must pin schema and call ordering. |
| F8 — current seq/slug storage | NO `display_seq`/`display_slug` columns. Both live in `entities.entity_id` as composite `{seq}-{slug}` AND redundantly in `metadata` JSON (`id` numeric, `slug` string). | FR-8.1 must dual-state: read from new `entity_display` table; backfill from existing `entity_id` + `metadata` JSON. |
| F8 — callers relying on entity_id parsing | Four sites: (a) `database.py:899-906` `scan_entity_ids` extracts max numeric prefix; (b) `workflow_state_server.py:373,416-418` `_project_meta_json` reads `metadata['id']`/`metadata['slug']`; (c) `backfill.py` parses `entity_id`; (d) `show-status.md:99,124` parses dir name. | FR-8.2 enumerates these explicitly; each is ported to query `entity_display` post-migration. |
| F8 — existing separation | None. No `entity_display` or related table. | FR-8.3 introduces table; migration is in scope. |
| Schema baseline | `schema_version=12` post-feature-109 (`database.py:3475-3479`). Entities columns: `uuid, workspace_uuid, type_id, entity_type, entity_id, name, status, parent_uuid, artifact_path, created_at, updated_at, metadata, type, kind, lifecycle_class`. | Migration 13 lands on top of 12; entity_display joins on `entities.uuid`. |

**Note:** `entity_type` column is listed in the post-12 schema above per the SUT-explorer report, but the feature-109 retro states it was dropped. Spec drafting treats the column as **absent** post-migration-12 (per the feature 109 implementation, not the spec text). Migration 13 must verify column absence before joining.

**Persistent decomposition warning (from parent PRD, acknowledged non-blocking):** Feature 110 bundles projection (read-path) and guard (write-path) responsibilities. These have different change axes. Per parent PRD persistence warning, this remains acceptable unless feature grows >800 LOC during create-plan; reassess at plan time.

## §2 Goals

1. **Mathematical drift impossibility:** `.meta.json` and `docs/backlog.md` content is a deterministic function of DB state. Deleting either file does not change entity status; regenerating produces byte-identical output.
2. **Sealed write path:** Only the projection functions (`_project_meta_json`, the new `_project_backlog_md`) write to these files. All ad-hoc writers from F4's audit are removed, ported, or explicitly documented as retained-with-rationale.
3. **PR review diff artifact:** Pre-commit hook emits `pd-state.diff.md` summarizing entity-state changes (uuid, status, phase, parent) between HEAD and base branch, so PR review has a human-readable state diff.
4. **Path-pattern guard:** Adding a new guarded file pattern requires only a config entry in `data_file_guards.json` — no new shell script per pattern.
5. **Display/identity separation:** Renaming an entity's display slug or sequence number changes a side table, not the canonical `entities.uuid` — survives without cascading rewrites.

## §3 Functional Requirements

### FR-4 — Markdown projection (sealed write path + diff artifact)

- **FR-4.1 — Audit + dispose of residual `.meta.json` writers.** All three residual non-projection write sites enumerated in §1 must be addressed in this feature:
  - `engine.py:450-477` `_write_meta_json_fallback`: retain (justified — degraded-mode lifeline) BUT add inline `# F4-AUDIT: degraded-mode-only` comment AND a static-grep test asserting it is the ONLY direct-write site in `workflow_engine/`.
  - `feature_lifecycle.py:285-298` `init_project_state`: port to use `_project_meta_json` for projects (or document why projects retain direct-write semantics; the migration may be deferred to feature 111 if project-type semantics differ — decision recorded in design phase).
  - `fix_actions.py:53-95` `_fix_update_meta_json`: replace with a doctor autofix that calls `complete_phase` / `transition_phase` MCP tools (which trigger projection) instead of writing directly. If the autofix surface can't be cleanly ported, document why and add inline `# F4-AUDIT:` comment.
- **FR-4.2 — Add `_project_backlog_md(db)` projection function.** New function in `workflow_state_server.py` (sibling of `_project_meta_json`) that reconstructs `docs/backlog.md` from DB state. Output is byte-deterministic (sorted by ID ascending; keep-a-changelog category sections preserved as DB metadata).
- **FR-4.3 — Port backlog writers to projection or MCP.** Each of the four backlog write sites is routed to one of: (a) call `_project_backlog_md` after a DB mutation, (b) call a new `issue_spawn` MCP (deferred to feature 111), or (c) explicitly retained with `# F4-AUDIT:` comment.
- **FR-4.4 — Determinism + idempotency.** Running `_project_meta_json` or `_project_backlog_md` on unchanged DB state produces byte-identical output (sorted keys, fixed line endings, stable ordering). Test asserts second invocation matches first byte-for-byte.
- **FR-4.5 — Gitignore + tracked-copy removal.** Add `**/.meta.json` and `docs/backlog.md` to `.gitignore`. Same commit runs `git rm --cached` for currently-tracked copies of both file types. (`docs/backlog.md` is currently tracked; the per-feature `.meta.json` files are also tracked.)
- **FR-4.6 — `pd-state.diff.md` generator.** New script `plugins/pd/scripts/pd_state_diff.py` that emits a markdown diff comparing entity state on HEAD vs base branch. Columns: `uuid`, `type_id`, `status`, `workflow_phase`, `parent_type_id`. Wired into `pre-commit-guard.sh` (writes `pd-state.diff.md` to repo root) AND `finish-feature.md` Step 5 (commits the artifact alongside `.meta.json`).
- **FR-4.7 — Hand-editing safety.** Deleting `.meta.json` files does NOT change any row in `entities`, `workflow_phases`, or `phase_events`. Test asserts: delete-then-regenerate cycle leaves DB content unchanged AND regenerated file byte-identical to pre-delete file.

### FR-7 — Generalized data-file guard

- **FR-7.1 — Config schema.** New file `plugins/pd/hooks/data_file_guards.json` with schema:
  ```json
  [
    {
      "pattern": "*.meta.json",
      "guard_module": "meta_json_guard",
      "decision_module": "meta_json_sentinel_decision",
      "mcp_tool_hint": "complete_phase / transition_phase"
    },
    {
      "pattern": "docs/backlog.md",
      "guard_module": "backlog_guard",
      "decision_module": "backlog_projection_decision",
      "mcp_tool_hint": "/pd:add-to-backlog or issue_spawn"
    }
  ]
  ```
  `pattern` uses shell glob semantics. `guard_module` and `decision_module` are dotted Python module names (resolved relative to `plugins/pd/hooks/lib/`). `mcp_tool_hint` is the user-facing remediation message.
- **FR-7.2 — Dispatch loop.** A new `plugins/pd/hooks/data-file-guard.sh` reads stdin once, iterates config entries in declared order, runs `fnmatch`-style pattern match on `file_path`, and on first match invokes the configured decision module. Returns `hookSpecificOutput.permissionDecision=deny|allow` per the decision module's output.
- **FR-7.3 — Backwards-compat retire.** Existing `meta-json-guard.sh` becomes a thin shim that delegates to `data-file-guard.sh` OR is removed in the same commit that registers the unified hook. Spec defers the choice to design — implementation must keep the user-facing behavior unchanged (deny still fires on Write/Edit of `.meta.json` outside the projection write path).
- **FR-7.4 — Hook registration.** `plugins/pd/.claude-plugin/hooks.json` registers `data-file-guard.sh` once (PreToolUse) and unregisters the per-file guard scripts that have been retired.
- **FR-7.5 — Hot-add new pattern.** Adding a new entry to `data_file_guards.json` and implementing its decision module requires NO change to the dispatch script. Test demonstrates this by adding a third pattern under a fixture path and verifying the dispatch routes correctly without touching `data-file-guard.sh`.

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
  No UNIQUE on `slug` alone (parent project PRD allows duplicate slugs across workspaces); UNIQUE may be added in a future feature once workspace-scoping is confirmed.
- **FR-8.2 — Backfill at migration time.** Migration 13 populates `entity_display` for every existing entity by parsing `entities.entity_id` (format: `{seq}-{slug}`) and reading `metadata['id']`/`metadata['slug']` as a cross-check. Mismatches between the two sources are logged but do not block migration; the `entity_id`-parsed values win (since `entity_id` is the FK-constrained truth).
- **FR-8.3 — Port the four caller sites enumerated in §1:**
  - `database.py:899-906` `scan_entity_ids`: replace regex-on-`entity_id` with `SELECT MAX(seq) FROM entity_display WHERE entities.workspace_uuid = ?`.
  - `workflow_state_server.py:373,416-418` `_project_meta_json`: query `entity_display` instead of `metadata['id']`/`metadata['slug']`.
  - `backfill.py`: query `entity_display` instead of parsing `entity_id`.
  - `show-status.md:99,124`: documentation/skill change — show how to derive seq+slug from the new table.
- **FR-8.4 — Rename without rewrite.** Test asserts: updating `entity_display.slug` for a given `uuid` changes `_project_meta_json` output's `slug` field BUT does NOT touch `entities.entity_id`, `entities.type_id`, `entities.uuid`, OR any `phase_events` row.
- **FR-8.5 — Identity stability under rename.** Test asserts: after a slug rename via `entity_display`, `parent_uuid` references from child entities still resolve correctly (no orphans introduced).
- **FR-8.6 — Down-migration.** `MIGRATIONS_DOWN[13]` drops the `entity_display` table and index. Source-code restore is via git history (per feature-109 precedent — down-migration is runtime-only).

### FR-5 — Migration 13 safety

- **FR-5.1 — Single-transaction discipline.** Migration 13 wraps all DDL + backfill in `BEGIN IMMEDIATE` with `PRAGMA foreign_key_check` pre- and post-commit. On any check failure, rollback and surface the error.
- **FR-5.2 — Idempotency.** Re-running migration 13 against a `schema_version=13` DB is a no-op (returns early after table-existence check inside the transaction; defense-in-depth against WAL read-snapshot races, per feature-109 pattern).
- **FR-5.3 — Schema version stamp.** Migration 13 sets `PRAGMA user_version = 13` AND `INSERT INTO schema_version (version, applied_at) VALUES (13, ?)` inside the same transaction.
- **FR-5.4 — Reverse migration.** `MIGRATIONS_DOWN[13]` drops `entity_display` and `idx_entity_display_seq`. Per feature-109 retro: down-migration is runtime-only restore; source-code state pre-13 is reachable via git history alone.

## §4 Acceptance Criteria

### AC-1.x — Code-surface acceptance (verifiable via grep / pytest)

- **AC-1.1** `grep -nE "open\\(.+\\.meta\\.json.*['\"]w['\"]" plugins/pd/hooks/lib/ plugins/pd/mcp/` returns ≤ 3 matches (the FR-4.1 enumerated residuals) AND each match has a sibling `# F4-AUDIT:` comment within 5 lines.
- **AC-1.2** `grep -nE "(write_text|open\\(.*['\"]w['\"]).*backlog\\.md" plugins/pd/` returns ≤ 4 matches (the FR-4.3 enumerated residuals) AND each match has `# F4-AUDIT:` comment within 5 lines OR is replaced with a `_project_backlog_md` call.
- **AC-1.3** `python3 -c "from workflow_engine.mcp.workflow_state_server import _project_backlog_md; print(callable(_project_backlog_md))"` prints `True` after install.
- **AC-1.4** `cat .gitignore | grep -E "^(\\*\\*/)?\\.meta\\.json$"` returns a match AND `cat .gitignore | grep "docs/backlog.md"` returns a match.
- **AC-1.5** `git ls-files | grep -E "(\\.meta\\.json|docs/backlog\\.md)$"` returns 0 lines after the migration commit (all tracked copies removed via `git rm --cached`).

### AC-4.x — Projection determinism + idempotency

- **AC-4.1** Two consecutive invocations of `_project_meta_json(db, engine, type_id)` against unchanged DB state produce byte-identical output (sorted keys, ISO timestamps preserved, no whitespace drift).
- **AC-4.2** Two consecutive invocations of `_project_backlog_md(db)` produce byte-identical output.
- **AC-4.3** Deleting a `.meta.json` file then calling `_project_meta_json` for that feature regenerates byte-identical content.
- **AC-4.4** Deleting `docs/backlog.md` then calling `_project_backlog_md` regenerates byte-identical content.
- **AC-4.5** Tampering with `.meta.json` (manual edit: append `"tampered": true`) does NOT change `entities.status` for any row. Verified via `SELECT status FROM entities WHERE type_id = ?` before and after.

### AC-6.x — `pd-state.diff.md` generator

- **AC-6.1** Running `python plugins/pd/scripts/pd_state_diff.py --base develop` against a clean checkout writes `pd-state.diff.md` containing zero entity-state-change rows.
- **AC-6.2** Same script run after a synthetic `register_entity` produces a diff row containing the new uuid, type_id, status=`active`, parent_type_id (or empty), and a `(added)` marker.
- **AC-6.3** `pre-commit-guard.sh` runs `pd_state_diff.py` (or invokes it via the bundled Python venv) and writes `pd-state.diff.md` BEFORE the commit completes. The file is gitignored (consistent with `.meta.json`/`backlog.md` projection treatment) — its purpose is local PR-prep, not version-controlled.
- **AC-6.4** `pd-state.diff.md` for an empty-tree branch run shows `No entity state changes vs {base}`.

### AC-7.x — Generalized guard

- **AC-7.1** `plugins/pd/hooks/data_file_guards.json` exists with at least the two FR-7.1 entries.
- **AC-7.2** `data-file-guard.sh` exists, is executable, and is registered exactly once in `plugins/pd/.claude-plugin/hooks.json` under `PreToolUse`.
- **AC-7.3** Write/Edit of `.meta.json` outside the projection write path is denied with reason text mentioning `complete_phase / transition_phase`.
- **AC-7.4** Write/Edit of `docs/backlog.md` outside the projection write path is denied with reason text mentioning `/pd:add-to-backlog or issue_spawn`.
- **AC-7.5** Hot-add: writing a third config entry `{"pattern": "test_fixture.md", "guard_module": "fixture_guard", "decision_module": "fixture_decision", "mcp_tool_hint": "..."}` and providing the decision module causes the dispatch script to route Write/Edit of `test_fixture.md` to the new module WITHOUT modifying `data-file-guard.sh`. Verified via integration test.

### AC-8.x — entity_display table

- **AC-8.1** Post-migration-13, `PRAGMA table_info(entity_display)` returns the four columns: `uuid`, `seq`, `slug`, plus the table-info preamble. Index `idx_entity_display_seq` exists per `sqlite_master`.
- **AC-8.2** Post-migration, every row in `entities` has a corresponding row in `entity_display` joined on `uuid` (assert via `SELECT COUNT(*) FROM entities WHERE uuid NOT IN (SELECT uuid FROM entity_display)` returns 0).
- **AC-8.3** Backfill correctness: for each row, `entity_display.seq` matches the numeric prefix of `entities.entity_id` AND `entity_display.slug` matches the suffix (after the first `-`).
- **AC-8.4** `scan_entity_ids` returns the same `max_seq` value pre- and post-migration when the DB content is otherwise unchanged.
- **AC-8.5** `_project_meta_json` after migration reads `id` and `slug` fields from `entity_display`, NOT from `metadata` JSON. Verified by deleting the JSON `id`/`slug` keys post-migration and re-projecting — `.meta.json` output is unchanged.
- **AC-8.6** Slug rename test: `UPDATE entity_display SET slug='renamed-slug' WHERE uuid = ?` followed by `_project_meta_json(type_id)` shows new slug in `.meta.json` output AND `entities.uuid`, `entities.entity_id`, `entities.type_id`, all `phase_events.entity_uuid` references are byte-identical to pre-rename state.

### AC-5.x — Migration 13 safety

- **AC-5.1** Migration 13 runs in a single `BEGIN IMMEDIATE` transaction with `PRAGMA foreign_key_check` returning zero rows both before COMMIT and after.
- **AC-5.2** Migration 13 is idempotent: running it twice on the same DB yields identical schema_version (13) and identical entity_display contents (no duplicate-key error, no behavior change).
- **AC-5.3** Migration 13 sets `PRAGMA user_version = 13` AND inserts `(13, applied_at)` into `schema_version` table.
- **AC-5.4** `MIGRATIONS_DOWN[13]` exists, drops `entity_display` + `idx_entity_display_seq`, decrements `user_version` to 12, removes the schema_version row.
- **AC-5.5** Down-migration round-trip: up → down on a 100-row fixture DB leaves `entities`, `workflow_phases`, `phase_events` rows byte-identical.

## §5 Non-Functional Requirements

- **NFR-1 — Atomic commit discipline.** Each Group (sub-feature) is its own commit with passing tests at every boundary. No mixed F4/F7/F8 commits.
- **NFR-2 — No new third-party dependencies.** Stdlib + existing project deps (`sqlite3`, `pathlib`, `json`, `subprocess`) only.
- **NFR-3 — Bash 3.2 / macOS BSD portability.** `data-file-guard.sh` must run under bash 3.2 (POSIX `[[:space:]]` regex; no GNU extensions). Verified via `/bin/bash` harness test.
- **NFR-4 — Hook EPIPE safety.** `data-file-guard.sh` uses `safe_emit_hook_json` per feature 107 contract.
- **NFR-5 — Idempotent migrations.** Migration 13 is replay-safe per AC-5.2.

## §6 Out of Scope (Deferred)

- F6 `issue_spawn` MCP tool — feature 111 scope.
- F9 `complete_phase(closes=[...])` cascade closure — feature 111 scope.
- F10 free-text suffix parsing removal — feature 111 scope.
- Workspace-scoped slug uniqueness on `entity_display` — future enhancement once `workspace_uuid` joining patterns are bedded in.
- `pd-state.diff.md` rendering in CI / GitHub Actions integration — local pre-commit only in this feature.

## §7 Open Risks

- **R1 — `init_project_state` semantic divergence (FR-4.1).** Project-type entities may have schema differences from feature-type entities that prevent direct port to `_project_meta_json`. Design phase decides: port or document-with-rationale.
- **R2 — Doctor autofix surface (FR-4.1).** `_fix_update_meta_json` is a "make the DB and file agree" operation. Replacing direct-write with `complete_phase` may not handle every drift mode (e.g., DB has stale `lastCompletedPhase`, file has correct). Design phase decides recovery path.
- **R3 — Backfill mismatch (FR-8.2).** Pre-migration `entities.entity_id` parsing may produce different values than `metadata['id']`/`metadata['slug']` for legacy rows. AC-8.3 enforces post-migration `entity_id` parse wins; pre-migration audit step in design ensures this is safe (no DB rows have inconsistent values).
- **R4 — `pd-state.diff.md` performance (FR-4.6).** Diff generator runs on every pre-commit. Design must ensure it terminates in <500ms for a 500-row entity DB; otherwise it gets disabled or async-deferred.

## §8 Verification Mapping

| AC | Verification mechanism | Location |
|---|---|---|
| AC-1.1, AC-1.2 | static grep | new pytest in `test_audit_writes.py` |
| AC-1.3 | import smoke test | `test_projection_helpers.py` |
| AC-1.4, AC-1.5 | git command + `.gitignore` parse | `test_gitignore_drift.py` |
| AC-4.x | byte-equality assertion on projection output | `test_projection_determinism.py` |
| AC-6.x | script invocation + output parse | `test_pd_state_diff.py` |
| AC-7.x | hook integration test (shell harness) | `plugins/pd/hooks/tests/test-data-file-guard.sh` |
| AC-8.x | DB introspection + integration test | `test_entity_display_table.py` |
| AC-5.x | migration runner + foreign_key_check | `test_migration_13_safety.py` |
