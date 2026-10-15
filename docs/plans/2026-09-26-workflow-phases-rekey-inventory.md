# Inventory for the `workflow_phases` re-key (Phase R, step R0)

Merged from four read-only surveys of `develop` at `77f06efb`, 2026-09-26. Facts only; no design choices.

- **Rows:** `inventory.json`, 369 rows (366 from the merge, 3 added by the completeness round, section 10). Each row has the survey fields plus the synthesizer's fields (section 1.3). Cells in the tables below are cut to a fixed width (marked …); `inventory.json` holds every field in full, by id.
- **Citations:** `design:NNN` is `docs/plans/2026-09-25-release-c-followups-design.md` (rev 2.1) and `plan:NNN` is `docs/plans/2026-09-25-release-c-followups-implementation-plan.md`, both at `77f06efb`. File paths in tables drop the `plugins/pd/hooks/lib/` or `plugins/pd/` prefix.

## 1. Scope and method

- **Repository:** `/Users/terry/projects/pedantic-drip`, branch `develop` at commit `77f06efb`, main checkout.
  - Read-only: no tracked file was edited, staged or committed; `.pd-worktrees/followups-1a` was not touched.
  - `git diff --stat 84fc9376 77f06efb` touches only plan documents, so the design's line citations hold (engines survey).
- **Live registry:** `~/.claude/pd/entities/entities.db` (schema_generation `v2`, schema_version `7`, no `-wal` file).
  - Read only as `sqlite3.connect('file:/Users/terry/.claude/pd/entities/entities.db?immutable=1', uri=True)`.
  - Experiments ran only on copies made with the prescribed `s.backup(d)` command, inside this directory.
  - Fingerprint before and after the tests-and-live survey: `1790286038 4083712`, sha256 prefix `2814bb4434e8faa0` (section 8).

### 1.1 Areas and inputs

| Area | What it covered | Rows file | Rows | Report |
|---|---|---|---|---|
| schema | `entity_registry/{database,schema_v2,events,axes,views,rebuild_tool}.py`: DDL, both migration chains, identity resolution, other entity-referencing tables, v2 events and views, rebuild tool | `survey-schema.json` | 106 | `survey-schema.md` |
| engines | `workflow_engine/` (14 modules), the other 15 `entity_registry/` modules, `reconciliation_orchestrator/` (4), `doctor/` (11) | `survey-engines.json` | 94 | `survey-engines.md` |
| surfaces | both MCP servers (44 tools), UI, `plugins/pd/scripts/` and `scripts/`, hooks, commands and skills | `survey-surfaces.json` | 119 | `survey-surfaces.md` |
| tests-and-live | 144 `test_*.py` and `conftest.py` files; live census and a dry run on a copy | `survey-tests.json` | 73 | `live-census.md` |

### 1.2 Commands used

**By the surveyors** (scripts and outputs in this directory):
- **schema:** bounded reads of the schema modules; `EntityDatabase(path)` to build `fresh.db`; `rebuild_tool.build_staging_database` to build `staging-rebuild.db`; `sqlite_master` dumps (`fresh-schema-master.txt`, `live-schema-master.txt`, `fresh-vs-live-diff.txt`); probes `probe_shared_type_id.py` and `probe_reattribution.py` on copies (outputs `*.out`); `git log -S` for the view text; `build_survey_schema.py` writes the rows.
- **engines:** `engines-work/scan.py` (candidate-site scan of 44 modules), `reach.py` (AST reachability from MCP tools), `pygrep.py` (path:line grep), codegraph caller lists (`cg_*.txt`), `live_context.py` (read-only live counts); `build_rows.py` asserts each row's anchor text at its line before writing.
- **surfaces:** grep lists (`surfaces-work/grep_*_tables.txt`, `md_*.txt`, `tools.txt`), `ui_probe.py` and the phase_events probe on a live copy; `rows/*.py` and `build.py` write the rows.
- **tests-and-live:** AST census (`tests-work/autofacts.py`, `manual.py`, `build_rows.py`), `census.py` (live, SELECT only), `dryrun.py` (on `tests-work/live-copy.db`), `guard_probe.py`, `write_census_md.py`.

**By the synthesizer** (`synth-work/`):
- `merge.py`: merges the rows, adds the synthesizer fields and the two synthesizer rows, writes `inventory.json` and `synth-work/conflicts.json`.
- `build_md.py`: writes this file; section 8 is copied from `live-census.md`.
- `count_tests.py`: an independent AST count of SQL literals and API calls per test file (`overlap_counts.json`, `all_test_counts.json`), used for conflicts C05 and C12; C06–C08 used targeted scans of the lines they name.
- `git grep -n -E '\.get_entity\(' -- '*.py'` over production files: 39 lines (`get_entity_grep.txt`, mapped in section 6.1).
- Completeness greps over production code (results in `uncovered_calls.txt`, `uncovered_sql.txt`):
  - calls of `update_entity`, `set_archived`, `get_lineage`, `set_parent`, `feature_entity_id`, `resolve_ref`, `set_deleted`, `delete_entity`, `search_by_type_id_prefix`, `_resolve_identifier`, `export_lineage_markdown`, `reparent_entity`: 72 lines, 19 outside every row's range (section 1.4);
  - SQL of the form `type_id = ?`, `type_id = x.type_id`, `type_id IN (`: 49 lines, 4 outside every row's range (section 1.4);
  - files naming either table or the row APIs: 43; all are recorded except `CHANGELOG.md`, `CLAUDE.md`, `README_FOR_DEV.md`, `doctor/__init__.py`, `doctor/fixer.py`, `scripts/dev/check_fr_c_115_atomicity*.sh` (2) and `scripts/gen_archive_manifest.py` (section 1.4).
- Live re-checks, immutable, listed with their results in section 8.4.

### 1.3 Merge rules

- **Deduplicated by file and line.** 28 survey rows describe a site another area also recorded:
  - `display.py` rename: schema-75 merged into engines-83 (conflict C01);
  - 21 `entity_registry` test files: each schema row merged into the tests row for the same file;
  - 6 script test files: surfaces TST-1, 2, 4, 5, 6, 7 merged into tests-67, 68, 66, 65, 59, 69.
  - The primary row keeps its id; `merged_from` lists every source id; the merged row's fate, evidence, notes and any differing `rekey_needs` are appended to `notes`.
- **Nested ranges kept apart.** Rows in one file whose ranges nest (a migration and the trigger it creates; an MCP handler and the statements inside it) name different symbols or statements, so they stay separate rows.
- **Two rows added** for sites no survey recorded: synth-1 (`update_entity`'s own resolution, database.py:8557) and synth-2 (the `export_lineage_markdown` MCP path).
- **Three rows added by the completeness round** (section 10): fill-1 (v2 migration 5's phase_events read), fill-2 (`_compute_durations`) and fill-3 (`hooks/tests/test-workflow-regression.sh`).
- **Fields added to every row:**
  - `area`, `merged_from`, `conflicts`;
  - `object_class`: the surveyors' object labels normalised (for example `entities (write by type_id)` becomes `entity write by type_id`, and the surfaces label `join` becomes `workflow_phases`);
  - `phase1_class` (`deleted`, `changed`, `unchanged`) and `phase1_class_detail`, from the fate's leading decision;
  - `phase1_changes`: the W ids that delete or change the site; `phase1_related`: W ids an unchanged row's fate mentions (a caller or callee changes); `survives_phase1`; `is_test_file_row`.
  - `completeness`: the critic items that added or corrected the row (section 10); `workspace_scoped_after_phase1`, only where Phase 1 changes a surviving unscoped read's scope (schema-32).
- **Classification rules for `phase1_class`:**
  - a test file "deleted in part" counts as changed (the file survives);
  - one rule since the completeness round (section 10.3): `changed` only when Phase 1 edits a line in the row's own range, or the body of a function the design deletes or restructures that the row lies in; a change that reaches the row only through a callee goes in `phase1_related`. The merge had counted engines-56 as changed, as the engines survey did; it is now unchanged, with nine MCP rows;
  - for a test-file row, `changed` means Phase 1 requires an edit to the file: the aggregate tests-73 counts as changed (two call sites need a workspace), and tests-72 is unchanged (section 10.3);
  - the merge's rules reproduced the engines survey's own counts (11 deleted, 20 changed, 63 unchanged); under the one rule they are 11, 19 and 64.
- **Result:** 366 rows = 392 survey rows − 28 merged + 2 added; the completeness round added 3, so 369 (section 10).
- **Recording conventions the surveys shared, checked here:**
  - The implicit phase_events writes inside `EntityDatabase` are recorded once, at the method: schema-41 (`update_entity` status change, database.py:8680-8709), schema-42 (`register_entity`), schema-43 (`upsert_entity`). Callers are recorded as entity-by-type_id rows, not as separate phase_events rows (engines open question 5).
  - The design's "39 unscoped `get_entity` reads" is reconciled line by line in section 6.1 (engines open question 2).

### 1.4 Completeness checks that added no row

- `doctor/fixer.py:28` registers `_fix_remove_orphan_workflow` (recorded as an engines fix-action row); it is a dispatch table entry.
- `doctor/__init__.py:43` is a comment.
- Scoped resolution that the engines survey listed under "Considered and not recorded": `backfill.py:468`, `:666`, `:807`, `:899`, `:944`; `feature_lifecycle.py:375`.
- uuid-keyed: `frontmatter_sync.py:463`; `scripts/c22_recreate_live_remainder.py:1001` (update by uuid), `:1076` (`reparent_entity` by uuid).
- Scoped writes in the one-off C22 script: `c22_recreate_live_remainder.py:1082`, `:1087` (`set_archived(type_id, workspace_uuid=...)`).
- Docstrings or text: `router.py:417`, `cleanup_backlog.py:200`, `parse_backlog_md.py:14`, `c22_recreate_live_remainder.py:58`, `append_phase_event`'s docstring at database.py:9654 and :9663; `scripts/gen_archive_manifest.py:80-82` writes instruction text into a manifest.
- `database.py:297`: migration 2 (`_migrate_to_uuid_pk`) resolves parents by type_id; it predates workspaces and touches only `entities`. `database.py:5682`: migration 18, scoped by workspace.
- `scripts/dev/check_fr_c_115_atomicity*.sh`: git-diff greps (surfaces survey).

### 1.5 Conflicts between surveyors, and their resolution

| Id | Rows | Field | One survey says | The other says | What the synthesizer checked | Resolution |
|---|---|---|---|---|---|---|
| C01 | engines-83, schema-75 | line | schema-75: `123-232 (UPDATE 205-216)` | engines-83: `190-233` | display.py: `def rename_entity(` at :123, `def _rename(` at :190, file ends at :233; `set_parts.append("type_id = ?")` at :207; `UPDATE entities SET ... WHERE uuid = ?` at :216-218. | One site, merged into engines-83 with line `123-233 (rename_entity 123-189; _rename 190-233; UPDATE entities 216-218)`. The other fields agree (uuid key, test-only, unchanged in Phase 1, deleted by W5.1 in Phase 4). |
| C02 | tests-6, schema-81 | phase1_fate | schema-81 (test_database.py): unchanged (quotes the Deferred re-key row) | tests-6: changed by W2.1 | test_database.py:3745-3760 `test_scoped_type_id_collision_dedupes_to_target_workspace` registers `feature:002-collide` in two workspaces, then calls `db.create_workflow_phase("feature:002-collide", kanban_column="wip")` with no workspace. W2.1 (design:263-265): the lookup "must be globally unique otherwise, so ambiguity is refused". | changed by W2.1 (tests-6 stands): that test must pass a workspace. The migration classes in the file are unchanged. |
| C03 | tests-17, schema-99 | phase1_fate | schema-99 (test_dependencies.py): unchanged | tests-17: changed by W1.7 | test_dependencies.py:427-435 builds `flaky_update_entity(type_id, ...)` that raises only when `type_id == b2_type_id`; dependencies.py:184 calls `db.update_entity(entity["type_id"], status="ready")`, which W1.7 (design:234) moves to the entity uuid. | changed by W1.7 (tests-17 stands): once the call passes a uuid the injected fault never fires and `pytest.raises(RuntimeError)` fails. |
| C04 | tests-26, schema-100 | phase1_fate | schema-100 (test_backfill_parent_uuid.py): unchanged | tests-26: changed by W2.6 | The file writes `.meta.json` files (:71, :125, :155, :198) and calls `backfill_workflow_phases(db, artifacts_root, project_id="__unknown__")` (:75, :128, :158, :201). W2.6 (design:295-303) deletes the backfill's `.meta.json` reads and scopes it to the server's workspace; plan 1A item 7 (plan:156) counts "42 mechanical backfill-signature changes". | changed by W2.6 (tests-26 stands). |
| C05 | tests-14, tests-6, tests-9, tests-22, tests-19, tests-7, tests-8, tests-23, schema-94, schema-81, schema-84, schema-86, schema-90, schema-82, schema-83, schema-88 | evidence (raw-SQL count) | schema rows count source lines: test_board_archived_query 1, test_database 49, test_event_sourced_state 13, test_migration_19_safety 9, test_migration_safety 4, test_phase_events 21, test_phase_events_adversarial 12, test_v2_migrations 6 | tests rows count SQL statements: 2, 59 (57 wp + 2 pe), 10, 10, 7, 28, 13, 10 | Independent AST count of SQL string literals naming either table (synth-work/count_tests.py, results in synth-work/overlap_counts.json) reproduces the tests figures in all 21 shared files. | The tests figures are statement counts and stand; the schema figures count matching source lines, a different unit. The other 13 shared files agree. |
| C06 | tests-14, schema-94 | evidence (API-call count) | schema-94 (test_board_archived_query.py): 9 wp/pe EntityDatabase calls | tests-14: 8 (list_workflow_phases x7, create_workflow_phase x1) | Calls at :79, :129, :144, :145, :146, :163, :170, :183; the module docstring at :4 also contains `list_workflow_phases(`. | 8 calls (tests-14 stands). |
| C07 | tests-6, schema-81 | notes (INSERTs naming workspace_uuid) | schema-81: 26 raw INSERTs, 6 name workspace_uuid | tests-6: 26 INSERTs, 21 type_id only, 5 +workspace_uuid | AST scan: INSERT column lists name workspace_uuid at :3187, :3619, :3656, :3732, :3786; the only other text naming both `INSERT` and `workspace_uuid` is the docstring at :3170. | 5 (tests-6 stands); 0 name uuid (both agree). |
| C08 | tests-67, TST-1 | line / evidence (SQL count) | TST-1 (scripts/test_migrate_db.py): wp SQL at 10 lines (237, 291, 765, 921, 1087, 1102, 1180, 1183, 1192, 1229) | tests-67: 13 statements at the same 10 lines | The DDL script string at :765 holds 4 statements naming workflow_phases (CREATE TABLE, CREATE TRIGGER enforce_immutable_wp_type_id, 2 CREATE INDEX); the other 9 strings hold one each. | Both are right: 10 string literals, 13 statements. |
| C09 | tests-59, TST-6 | line | TST-6 (test_c5b_parse_backlog_workspace.py): `24-60` | tests-59: `1-57 (whole file)` | `wc -l` = 57; the one test function starts at :24; the phase_events SELECT is at :53. | The test spans 24-57; line 60 does not exist. Merged row keeps tests-59's whole-file range. |
| C10 | schema-19, survey-schema.md, live-census.md | live figure: phase_events rows whose (label -> workspace, type_id) finds no entity | schema: 368 of 1469 | tests (live census): 381 of 1469 | Live, immutable: counting every row gives 381; counting only rows whose project_id names some workspace gives 368. The 13-row difference is project_id `e8bdba5f147b`, which names no workspace. | Both are right under their definitions; section 8 uses 381 (all rows). |
| C11 | schema-19, live-census.md | live figure: workspaces with NULL project_id_legacy | schema: 7 of 21 workspaces | tests: two workspaces (d373a5ad, fe180347) | Live: 21 workspaces, 7 with NULL project_id_legacy; 7 workspaces hold entities, 2 of them (d373a5ad, fe180347) with NULL. | Both are right: 7 of all 21 workspaces; 2 of the 7 that hold entities. |
| C12 | survey-engines.md, tests-73 | test totals | engines lead: 37 test files, 158 raw-SQL statements, 427 API calls (workflow_engine, entity_registry, reconciliation_orchestrator, doctor) | tests: 144 files scanned, 41 with raw SQL, 130 wp + 111 pe statements; API totals per method | Synthesizer AST count over the same four directories: 38 files with any contact, 27 with raw SQL, 187 SQL literals (88 wp + 99 pe), 426 API calls. Over all 144 files: 41 files with raw SQL, 127 wp literals (130 statements, see C08) and 111 pe; per-method API totals equal tests-73's. | The engines figure is a line grep (engines-work/test_leads.txt) over a narrower scope; section 7 uses the tests figures. |
| C13 | survey-surfaces.md, live-census.md | live fact: feature:035-slim-watchdog-self-mgmt | surfaces: "active in both pedantic-drip and terry_agent" | tests: "both archived, no row in either" | Live entities: 69696982/feature/active/arch=1 and f7b49c1d/feature/active/arch=1; no workflow_phases row. | Both are right: status `active`, `is_archived=1`, in both workspaces. |
| C14 | survey-schema.json, schema summary | row count | schema summary: "1 row for each of 25 test files" | survey-schema.json: 26 test-file rows (schema-81 .. schema-106) | Counted rows whose file name starts with `test_`. | 26. |
| C15 | tests-73, schema-102, schema-103, schema-104, schema-105, schema-106, tests-72 | coverage of five test files | schema: rows for test_axes, test_events, test_views, test_display (v2 events/views, rename) and test_c22a_reparent_entity | tests-73 lists the first four under "files with no contact at all"; tests-72 aggregates test_c22a | The four files touch only `events` and the v2 views (0 statements and 0 API calls on workflow_phases/phase_events, by both surveys); test_c22a has 3 implicit phase_events writes through register_entity and no direct wp/pe call. | No disagreement of fact: the tests survey scoped "contact" to workflow_phases and phase_events. The schema rows stay as rows; tests-72 keeps test_c22a in its aggregate. |

## 2. Schema objects

Everything below is `database.py` unless another file is named. Verified by the synthesizer: a whitespace-normalised comparison of `sqlite_master` for every object on or naming `workflow_phases`, `phase_events` and `entities` finds the same 30 objects with the same text in `fresh.db` and the live file (section 8.4).

### 2.1 The two chains, and how each file reaches its version

| Item | Fact | Row |
|---|---|---|
| v1 chain (`MIGRATIONS`) | versions 1–19, plus the v2 steps 2–7 registered again as 20–25: `MIGRATIONS[20] = _v2_migration_2_mini_spec`, `[21] = _v2_migration_3_state_only_axis_views`, `[22..25]` = v2 steps 4–7 (:6496-6517) | schema-20 |
| v2 chain (`V2_MIGRATIONS`) | `{2: mini_spec, 3: state_only_axis_views, 4: explicit_legacy_flag, 5: explicit_archived_flag, 6: soft_delete, 7: immutable_is_legacy}` (:6481-6488); `assert max(V2_MIGRATIONS) == V2_SCHEMA_VERSION` (:6506) | schema-20 |
| A file created now | `EntityDatabase(path)` runs the v1 chain to schema_version 25, with no `schema_generation` key; `_metadata`: audit_emit_failed_count, migration_5_statuses_restored, schema_version | schema-20 |
| The live file | schema_generation `v2`, schema_version 7 = `max(V2_MIGRATIONS)`; `_metadata` adds backfill_complete=1, backfill_version=4 | schema-20 |
| Rebuild tool | `build_staging_database`: v1 chain (now 1..25), then events/views/axes DDL, every `V2_MIGRATIONS` entry, stamp v2/7 (rebuild_tool.py:76-167); a staging file built now matches live except the `entity_axis_state` text | schema-76 |
| Runner | `_migrate` stamps each version as it commits, so an interrupted chain resumes (:11001-11066); `_migrate_v2` (:11114-11142) | schema-21 |
| C23 guard | `_refuse_if_file_is_from_the_future` (:11068-11112): a file stamped past the build's max gets a write-denying authorizer, so old-build processes lose write access after a live version bump | schema-21 |
| Down migrations | `MIGRATIONS_DOWN` holds 11–17 only (:5943-5956; m11, m12 and m14 downs touch wp/pe); `_migrate_down` raises for version 25 or 7 (:6565) | schema-22 |
| Copy-rename template | `_v2_migration_2_mini_spec` (:5973-6169): probe, `BEGIN IMMEDIATE`, capture and replay indexes, assert the index-name set and row count, `foreign_key_check` before COMMIT, literal COMMIT/ROLLBACK, registered in both chains | schema-17 |

### 2.2 `workflow_phases`: every step that created or changed it

| Step | Where | What it did | Row |
|---|---|---|---|
| m3 `_create_workflow_phases_table` | :378-470 (CREATE :405-428) | `type_id TEXT PRIMARY KEY REFERENCES entities(type_id)`; sound then, because m2 made `entities.type_id` UNIQUE (:254); creates `enforce_immutable_wp_type_id` (:433-438), `idx_wp_kanban_column`, `idx_wp_workflow_phase` (:441-448) | schema-1, schema-2, schema-10 |
| m5 `_expand_workflow_phase_check` | :514-629 (CREATE :544-573) | copy-rename to widen the phase CHECK; re-creates the trigger (:592) and indexes (:600-607) | schema-3 |
| m6 `_schema_expansion_v6` | :750-829 (step 4), :957-980 (step 12) | copy-rename adding `uuid TEXT` (no FK, not unique), filled by an unscoped type_id backfill (:797); trigger (:812); `idx_wp_uuid` (:829) | schema-4 |
| m8 `_add_project_scoping` step 9b | :1200-1270 (CREATE :1204-1235) | copy-rename that **drops the FK to entities**, because entities became `UNIQUE(project_id, type_id)` (:1116); type_id stays the key; trigger (:1251) | schema-5 |
| m9 `_migration_9_remove_create_tasks` | :1328-1459 (CREATE :1368-1398) | copy-rename (phase remap :1357-1364); trigger (:1418); this CREATE plus m11's ADD COLUMN (:2043-2045) is the final body | schema-6, schema-11 |
| m11 `_migration_11_workspace_identity` | :2039-2090 | `ALTER TABLE workflow_phases ADD COLUMN workspace_uuid TEXT REFERENCES workspaces(uuid)` (:2042-2045) with an unscoped type_id backfill (:2047); `idx_wp_workspace_uuid` (:2053); triggers `wp_autofill_workspace_uuid` (:2061-2076) and `wp_reject_orphaned_insert` (:2077-2090) | schema-7, schema-8, schema-9 |
| m12 | :2776-2791; :2972-2990 | deletes the `'feature:'` row (:2791); the entities copy-rename captures, drops and replays the two m11 triggers verbatim (:2972-2990) | schema-12 |
| m14, m14-down | :4492-4506, :4582-4589, :5048-5059 | the same trigger replay around entities copy-renames | schema-12 |

**Final shape (fresh v1/25 and live v2/7, identical text):**

| Part | Definition | Notes |
|---|---|---|
| `type_id` | `TEXT PRIMARY KEY` | the key; nullable (no NOT NULL); `sqlite_autoindex_workflow_phases_1` is the only uniqueness on the table |
| `workflow_phase`, `last_completed_phase` | `TEXT CHECK(IN 17 phase names) OR NULL` | |
| `kanban_column` | `TEXT NOT NULL DEFAULT 'backlog' CHECK(IN 8 columns)` | the v2 execution vocabulary includes `ready`, which this CHECK lacks (schema-73) |
| `mode` | `TEXT CHECK(IN ('standard','full','light')) OR NULL` | |
| `backward_transition_reason` | `TEXT` | |
| `updated_at` | `TEXT NOT NULL` | |
| `uuid` | `TEXT` | no FK, not unique, nullable; live: 521 set, 8 NULL (all written after the cutover); no SQL reader joins on it |
| `workspace_uuid` | `TEXT REFERENCES workspaces(uuid)` | nullable; the table's only FK; not part of any key |
| Storage | rowid table | |
| `enforce_immutable_wp_type_id` | `BEFORE UPDATE OF type_id` → `RAISE(ABORT, 'workflow_phases.type_id is immutable')` | `entities.type_id` has been mutable since m12 dropped `enforce_immutable_type_id` (:3114-3116) |
| `wp_autofill_workspace_uuid` | `AFTER INSERT WHEN NEW.workspace_uuid IS NULL AND EXISTS(entity with NEW.type_id)` → `UPDATE ... SET workspace_uuid = (SELECT e.workspace_uuid FROM entities e WHERE e.type_id = NEW.type_id)` | unscoped subquery; with two holders it takes the smallest workspace_uuid (covering scan of `sqlite_autoindex_entities_2`); never sets `uuid` |
| `wp_reject_orphaned_insert` | `BEFORE INSERT WHEN NEW.workspace_uuid IS NULL AND NOT EXISTS(entity with NEW.type_id)` → abort | an insert that names a workspace is never checked against entities |
| Indexes | `idx_wp_kanban_column(kanban_column)`, `idx_wp_workflow_phase(workflow_phase)`, `idx_wp_uuid(uuid)`, `idx_wp_workspace_uuid(workspace_uuid)` | all non-unique |

### 2.3 `phase_events`: every step that created or changed it

| Step | Where | What it did | Row |
|---|---|---|---|
| m10 `_migration_10_phase_events` | :1460-1728 (CREATE :1506-1523) | `type_id` and `project_id` (legacy workspace label), no FK; indexes `idx_pe_lookup(type_id, phase, event_type)`, `idx_pe_project(project_id, event_type)`, `idx_pe_timestamp(timestamp)` (:1525-1533); `phase_events_backfill_dedup` UNIQUE(type_id, phase, event_type, timestamp) WHERE source='backfill' (:1550-1554) | schema-13, schema-18 |
| m12 step 5i | :3363-3481 (CREATE :3431-3453) | copy-rename: 7 event types, nullable `phase`, `metadata` | schema-14 |
| m14 `_copy_rename_phase_events_for_v14` | :4590-4719 (CREATE :4657-4679) | copy-rename adding `spawned_child` | schema-15 |
| m19 `_migration_19_widen_phase_events_cascade_ready` | :5758-5895 (CREATE :5832-5845) | copy-rename adding `cascade_ready` | schema-16 |
| v2 m2 = v1 m20 `_v2_migration_2_mini_spec` | :5973-6169 (CREATE :6078-6100) | copy-rename adding `mini_spec`; the final body | schema-17, schema-19 |
| Index replay | every copy-rename | indexes replayed from `sqlite_master` | schema-18 |

**Final shape (fresh and live, identical text):** `id INTEGER PRIMARY KEY AUTOINCREMENT, type_id TEXT NOT NULL, project_id TEXT NOT NULL, phase TEXT, event_type TEXT NOT NULL CHECK(IN 10 values: started, completed, skipped, backward, entity_created, entity_status_changed, entity_promoted, spawned_child, cascade_ready, mini_spec), timestamp TEXT NOT NULL, iterations INTEGER, reviewer_notes, backward_reason, backward_target, source TEXT NOT NULL DEFAULT 'live' CHECK(IN ('live','backfill')), created_at TEXT NOT NULL, metadata TEXT`.
- No FK, no entity uuid, no workspace column; the entity is named by `type_id`, the workspace only by `project_id`, which equals `workspaces.project_id_legacy` when it names a workspace (schema-19).
- `append_phase_event` takes `workspace_uuid`, but its INSERT stores only `type_id` and `project_id` (:9734-9746, schema-26).
- AUTOINCREMENT keeps a `sqlite_sequence` row (live: 1469).

### 2.4 `entities` identity, as it bears on both tables

| Step | Identity | Row |
|---|---|---|
| m1 | `type_id` PRIMARY KEY | schema-25 |
| m2 | `uuid` PRIMARY KEY + UNIQUE(`type_id`) (:254) | schema-25 |
| m8 | UNIQUE(`project_id`, `type_id`) (:1116) | schema-25 |
| m11 | UNIQUE(`workspace_uuid`, `type_id`) (:1949); later copy-renames keep it (m12 :3018/:3330, m14 :4528) | schema-25 |
| m12 | drops `enforce_immutable_type_id` (:3114-3116): `entities.type_id` is mutable | schema-25 |
| Final | uuid PK; UNIQUE(workspace_uuid, type_id) = `sqlite_autoindex_entities_2`; no index on type_id alone; triggers `enforce_immutable_uuid` and `enforce_immutable_workspace_uuid` ('use re-attribution API'); `update_entity(new_project_id=...)` drops and re-creates the latter around its UPDATE (:8737-8790) | schema-25, schema-40 |

### 2.5 v2 events and views (live file only)

| Object | Source | Key | Row |
|---|---|---|---|
| `events` table: `uuid TEXT PRIMARY KEY, entity_uuid TEXT NOT NULL REFERENCES entities(uuid)` (no ON DELETE), event_type, axis (pipeline/execution/lifecycle), from_value, to_value, actor, timestamp, payload | events.py:76-99 | entity uuid | schema-69 |
| `events_no_update`, `events_no_delete`, `events_no_replace` triggers; `idx_events_entity_axis(entity_uuid, axis)`, `idx_events_timestamp` | events.py:76-99 | | schema-69 |
| `events_vocab_pipeline`, `events_vocab_execution` triggers (to_value vocabularies; execution includes `ready`) | axes.py:125-136 | | schema-73 |
| `entity_axis_state`, `entity_state` views | views.py:86-105; v2 m3 = v1 m21 (:6170-6204) rebuilds them | `entity_uuid, axis`; one row per `entities.uuid` | schema-23, schema-72 |
| `entity_phase_status` view | axes.py:141-149 | one row per entity | schema-73 |
| Writers of `events` | `_emit_v2_event` (:11144-11189; called from append_phase_event, create_workflow_phase, delete_entity, reparent_entity), `display.rename_entity` (test-only), rebuild_tool, `scripts/seed-census-db.py` | | schema-71, engines-83, SCR-12 |
| Readers | none in production: `read_events` has no non-test caller; the only non-test SQL on the views is `plugins/pd/hooks/tests/bench-db-direct-read.sh` | | schema-70 |

- **No view reads `workflow_phases` or `phase_events`.** On both files the three wp triggers are the only schema objects that name them.
- **`entity_axis_state` text differs:** live `WHERE to_value IS NOT NULL AND event_type != 'skipped'`; views.py:90 and a rebuild today `WHERE event_type != 'skipped'`; v2 m3's probe accepts both (schema open question 1; verified by the synthesizer).
- **Dark v2 core:** `schema_v2._CORE_DDL` declares `type_id TEXT, -- human-readable; NOT unique (FR-4)` (schema_v2.py:64) and has no `workflow_phases` or `phase_events`; `V2_SCHEMA_VERSION = 7` (schema-74).

### 2.6 Final shape, fresh file versus live file

| Object | Fresh (`EntityDatabase`, v1 chain, schema_version 25) | Live (v2, schema_version 7) |
|---|---|---|
| `workflow_phases` table, its PK autoindex, 4 indexes, 3 triggers | present, text identical to live | present |
| `phase_events` table, 4 indexes (one partial UNIQUE) | present, text identical to live | present |
| `entities` table and its triggers and indexes | present, text identical to live | present |
| `events`, its 2 indexes and 5 triggers | absent (`MIGRATIONS[21]` is a no-op without `events`) | present |
| `entity_axis_state`, `entity_state`, `entity_phase_status` views | absent | present |
| `_metadata` | schema_version 25; no schema_generation | schema_generation v2, schema_version 7 |
| Rebuild staging file built now | v2/7; same as live except the `entity_axis_state` text | |

Source: `fresh-vs-live-diff.txt` (ONLY IN LIVE: the 12 events/view objects; ONLY IN FRESH: none), `live-schema-master.txt`, tests-73.

## 3. Other tables that reference entities by type_id text

Live counts are immutable reads by the synthesizer (section 8.4).

| Column | Refers to the entity by | FK | Workspace-aware | Live | Row |
|---|---|---|---|---|---|
| `workflow_phases.type_id` | type_id text, PRIMARY KEY | none since m8 | only through the nullable `workspace_uuid`, which is not in the key | 529 rows | schema-11 |
| `workflow_phases.uuid` | a copy of the entity uuid | none; not unique; nullable | n/a | 521 set, all agreeing with the (workspace_uuid, type_id) entity; 8 NULL | schema-4, schema-11 |
| `phase_events.type_id` + `project_id` | type_id text + legacy workspace label | none | only through `workspaces.project_id_legacy`: NULL for 7 of 21 workspaces (2 of the 7 that hold entities); never rewritten by re-attribution | 1469 rows; 381 whose (label → workspace, type_id) finds no entity | schema-19 |
| `entities.metadata.depends_on_features` | type_id text inside JSON (some entries are bare entity ids) | none | resolved once, at registration, in the registering workspace (:7792-7805), and materialised as `entity_relations` `blocks` rows | 84 entities, 106 entries: 72 `feature:` type_ids, all held in the entity's own workspace, none shared; 34 bare ids | schema-66 |

No other table stores a type_id. For contrast, the tables that reference entities by uuid:

| Table | Column(s) | FK | Live rows | Row |
|---|---|---|---|---|
| `events` | `entity_uuid` | `entities(uuid)`, no ON DELETE | 2244 | schema-69 |
| `entity_relations` | `from_uuid`, `to_uuid`, `kind` (`blocks` only) | CASCADE | 33 | schema-61 |
| `entity_display` | `uuid` (one row per entity) | CASCADE | 409 | schema-62 |
| `cross_workspace_allowlist` | `parent_uuid`, `child_uuid` | CASCADE | 0 | schema-63 |
| `entity_tags` | `entity_uuid` | none | 9 | schema-59 |
| `entity_okr_alignment` | `entity_uuid`, `key_result_uuid` | none | 0 | schema-60 |
| `entities` | `parent_uuid` | `entities(uuid)` | 589 entities | schema-25 |
| `entities_fts` | rowid = `entities.rowid` | none | 589 | schema-65 |
| `sequences` | (`workspace_uuid`, `entity_type`) counter, not an entity reference | workspaces | 19 | schema-64 |
| `projects` | legacy `project_id` + `workspace_uuid` (repo metadata) | workspaces | 0 | schema-67 |
| `migration_audit_log` | none | none | 1 | schema-68 |

- **`entities.parent_type_id` no longer exists** (live columns: uuid, workspace_uuid, type_id, entity_id, name, status, parent_uuid, artifact_path, created_at, updated_at, metadata, type, kind, lifecycle_class, is_legacy, is_archived, is_deleted); `scripts/migrate_db.py` and `ui/mermaid.py` still read that key (SCR-7, UI-10).

## 4. Sites, grouped by file

All rows except test files, which section 7 tabulates (one row per file). Within a file, rows are ordered by their first line. The `phase1_fate` column shows the class and change ids first; the design quote each surveyor cited is in `inventory.json`.

### `plugins/pd/hooks/lib/entity_registry/database.py` (71)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| schema-1 | 378-470 (CREATE 405-428) | _create_workflow_phases_table (MIGRATIONS[3]) | migration | DDL | type_id | never | EntityDatabase._migrate() v1 chain: every fresh file (fresh files are v1-generation) and rebuild_tool._replay_v1_chain;… | unchanged — unchanged. Design "Deferred" table: "Re-key `workflow_phases` by entity uuid (D3) \| In… | Birth of the key. Any change of key is a new chain entry: fresh files replay MIGRATIONS 1..25 (database.py:11056-11063) and the live v2 file only runs V2_MIGRATIONS above its stamp (:11114-11142). |
| schema-2 | 433-438 (m3); re-created 592-597 (m5), 812-8… | enforce_immutable_wp_type_id | trigger | trigger | type_id | n/a | fires on any UPDATE OF type_id ON workflow_phases; no production code issues one | unchanged — unchanged. Design "Deferred" table: "Re-key `workflow_phases` by entity uuid (D3) \| In… | Pins wp.type_id while entities.type_id is mutable: migration 12 dropped entities' enforce_immutable_type_id (database.py:3114-3116) and display.rename_entity UPDATEs entities.type_id by uuid (display.py:205-216). A renamed entity's wp row stays under the old type_id and this trigger aborts any UPDA… |
| schema-10 | 441-448, 600-607, 820-829, 1257-1269, 1426-1… | idx_wp_kanban_column, idx_wp_workflow_phase, idx_wp_uuid (m… | index | index | type_id (PK autoindex); uuid; workspace_uuid | n/a | every workflow_phases read/write | unchanged — unchanged. Design "Deferred" table: "Re-key `workflow_phases` by entity uuid (D3) \| In… | The only unique index is the PK autoindex on (type_id). idx_wp_uuid and idx_wp_workspace_uuid are non-unique; nothing enforces one row per entity. Each copy-rename so far re-created these indexes by hand. |
| schema-65 | 480, 836, 1015, 1291, 2152, 3193, 3775 (FTS… | entities_fts | entities_fts | DDL | none (rowid = entities.rowid) | n/a | search_entities; every entity write syncs it by rowid | unchanged — unchanged. No W1/W2 change names it. | Standalone FTS5 coupled to entities by rowid, not uuid or type_id: an entities copy-rename must preserve rowids (each rebuild re-populates FTS). Not in wp/pe scope, but any migration touching entities inherits this coupling. |
| schema-3 | 514-629 (CREATE 544-573, DROP 585, RENAME 58… | _expand_workflow_phase_check (MIGRATIONS[5]) | migration | migration | type_id | never | EntityDatabase._migrate() v1 chain: every fresh file (fresh files are v1-generation) and rebuild_tool._replay_v1_chain;… | unchanged — unchanged. Design "Deferred" table: "Re-key `workflow_phases` by entity uuid (D3) \| In… | Copy-rename precedent on this table: explicit column-list INSERT-SELECT, trigger and 2 indexes re-created by hand. |
| schema-4 | 750-829 (step 4); 957-980 (step 12) | _schema_expansion_v6 (MIGRATIONS[6]) | migration | migration | type_id | never | EntityDatabase._migrate() v1 chain: every fresh file (fresh files are v1-generation) and rebuild_tool._replay_v1_chain;… | unchanged — unchanged. Design "Deferred" table: "Re-key `workflow_phases` by entity uuid (D3) \| In… | Added the `uuid TEXT` column (nullable, no FK, no UNIQUE) and idx_wp_uuid; backfilled it with an unscoped type_id subquery (exact at the time: entities.type_id was UNIQUE). Step 12 deletes orphans by type_id and re-runs the same backfill for NULL uuids. |
| schema-59 | 862-870 (m6); live DDL | entity_tags | entity_tags | DDL | uuid | n/a | add_tag/remove_tag/get_tags/query_by_tag (database.py:7398-7465) | unchanged — unchanged. No W1/W2 change names it. | uuid-keyed (entity_uuid, tag) UNIQUE; no FK to entities, so orphans are possible (live: 9 rows, 0 orphans). Not a type_id reference. |
| schema-60 | 894-900 (m6); live DDL | entity_okr_alignment | entity_okr_alignment | DDL | uuid | n/a | add/remove/get_okr_alignment (database.py:7466-7532) | unchanged — unchanged. No W1/W2 change names it. | uuid-keyed, no FK (live: 0 rows). Not a type_id reference. |
| schema-67 | 1073 (m8 CREATE TABLE projects), 2114 (m11 p… | projects | projects | DDL | project_id(legacy) + workspace_uuid | always | upsert_project / list_projects (entity_server startup) | unchanged — unchanged. No W1/W2 change names it. | Repo metadata keyed by the legacy project_id; not an entity reference. It and workspaces.project_id_legacy are the only mapping from phase_events.project_id to a workspace. |
| schema-64 | 1092 (m8), 2093 (m11 sequences_new); live DDL | sequences | sequences | DDL | none (workspace_uuid + entity_type counter) | always | next_sequence_value (database.py:10687); display.next_display_seq is test-only | unchanged — unchanged. No W1/W2 change names it. | Per-(workspace, kind) counter, not an entity reference. |
| schema-5 | 1200-1270 (CREATE 1204-1235, DROP 1244, RENA… | _add_project_scoping (MIGRATIONS[8]) step 9b | migration | migration | type_id | never | EntityDatabase._migrate() v1 chain: every fresh file (fresh files are v1-generation) and rebuild_tool._replay_v1_chain;… | unchanged — unchanged. Design "Deferred" table: "Re-key `workflow_phases` by entity uuid (D3) \| In… | The point where the key stopped matching entity identity: entities became UNIQUE(project_id, type_id) (database.py:1116) and this step DROPPED the FK instead of widening the wp key. |
| schema-6 | 1328-1459 (remap 1357-1364, CREATE 1368-1398… | _migration_9_remove_create_tasks (MIGRATIONS[9]) | migration | migration | type_id | never | EntityDatabase._migrate() v1 chain: every fresh file (fresh files are v1-generation) and rebuild_tool._replay_v1_chain;… | unchanged — unchanged. Design "Deferred" table: "Re-key `workflow_phases` by entity uuid (D3) \| In… | Last CREATE of the table body in the v1 chain; the current column list and CHECKs (minus workspace_uuid) are this DDL. |
| schema-11 | 1368-1398 + 2043-2045 (final body); live sql… | workflow_phases (final shape, fresh v25 = live v2/7) | workflow_phases | DDL | type_id | optional (workspace_uuid column, nullable, never part of the key) | all readers/writers below | unchanged — unchanged. Design "Deferred" table: "Re-key `workflow_phases` by entity uuid (D3) \| In… | Final columns: type_id TEXT PRIMARY KEY (no NOT NULL: SQLite allows NULL in a non-INTEGER PK of a rowid table), workflow_phase CHECK(17 values) OR NULL, kanban_column NOT NULL DEFAULT 'backlog' CHECK(8), last_completed_phase CHECK(17) OR NULL, mode CHECK('standard','full','light') OR NULL, backward… |
| schema-13 | 1460-1728 (CREATE 1506-1523, idx 1525-1533,… | _migration_10_phase_events (MIGRATIONS[10]) | phase_events | migration | type_id+project_id(legacy) | never (project_id legacy label only) | EntityDatabase._migrate() v1 chain: every fresh file (fresh files are v1-generation) and rebuild_tool._replay_v1_chain;… | unchanged — unchanged. No W1/W2 change names it; plan Phase R: "The design also decides ... whether… | Created with `type_id TEXT NOT NULL, project_id TEXT NOT NULL` and no FK, no entity uuid, no workspace_uuid. The metadata backfill (:1555-1700) derives project_id from entities.project_id or, post-m11, workspaces.project_id_legacy (:1565-1575). |
| schema-18 | 1525-1533, 1550-1554 (re-created verbatim by… | idx_pe_lookup, idx_pe_project, idx_pe_timestamp, phase_even… | index | index | type_id (+phase,event_type); project_id(legacy) | never | every phase_events read; the dedup index constrains source='backfill' rows | unchanged — unchanged. No W1/W2 change names it; plan Phase R: "The design also decides ... whether… | phase_events_backfill_dedup is UNIQUE(type_id, phase, event_type, timestamp) WHERE source='backfill': two workspaces' backfill rows for one shared type_id with equal phase/event/timestamp collide (rebuild_tool catches this per row, rebuild_tool.py:1048-1068). Lookup indexes lead with type_id or pro… |
| schema-25 | 1949 (m11), 3018/3330 (m12), 4528 (m14); 311… | entities UNIQUE(workspace_uuid, type_id); entities.type_id… | entity read by type_id | DDL | type_id+workspace_uuid | always | every entity write | unchanged — unchanged. Design "Deferred" table: "Re-key `workflow_phases` by entity uuid (D3) \| In… | The entity identity a wp row must follow: uuid PK, (workspace_uuid, type_id) unique, type_id NOT immutable (no trigger), workspace_uuid immutable except under the re-attribution APIs that drop enforce_immutable_workspace_uuid temporarily. There is no index on type_id alone (unscoped type_id lookups… |
| schema-7 | 2039-2055 (ALTER 2042-2045, backfill 2046-20… | _migration_11_workspace_identity (MIGRATIONS[11]) step 11 | migration | migration | type_id | never | EntityDatabase._migrate() v1 chain: every fresh file (fresh files are v1-generation) and rebuild_tool._replay_v1_chain;… | unchanged — unchanged. Design "Deferred" table: "Re-key `workflow_phases` by entity uuid (D3) \| In… | Added `workspace_uuid TEXT REFERENCES workspaces(uuid)` (nullable) by ALTER, backfilled by an UNSCOPED scalar subquery on type_id while entities were already per-project unique; the PK stayed type_id. |
| schema-8 | 2061-2076 | wp_autofill_workspace_uuid (created by MIGRATIONS[11]) | trigger | trigger | type_id | never | fires on every INSERT with NULL workspace_uuid: create_workflow_phase (database.py:10018) and upsert_workflow_phase's I… | unchanged; related W2.1 — unchanged as DDL; W2.1 stops its writers relying on it: "inserts the reso… | Guesses the workspace from type_id alone and never fills uuid. On a shared type_id its scalar subquery returns the smallest workspace_uuid (query plan: SCAN e USING COVERING INDEX sqlite_autoindex_entities_2, i.e. (workspace_uuid, type_id) order) - plan-dependent, not a contract. Any per-entity key… |
| schema-9 | 2077-2090 | wp_reject_orphaned_insert (created by MIGRATIONS[11]) | trigger | trigger | type_id | never | fires on INSERT with NULL workspace_uuid | unchanged — unchanged. Design "Deferred" table: "Re-key `workflow_phases` by entity uuid (D3) \| In… | Existence test is by type_id in ANY workspace: an insert naming a type_id that only another workspace holds passes and is then autofilled to that workspace. With workspace_uuid given it does not fire at all (no entity check). A per-entity key would make the orphan test a FK or a uuid lookup. |
| schema-12 | 2776-2791; 2972-2990 (+ recreate after RENAM… | _migration_12_polymorphic_taxonomy_and_events, _copy_rename… | migration | migration | type_id | never | EntityDatabase._migrate() v1 chain: every fresh file (fresh files are v1-generation) and rebuild_tool._replay_v1_chain;… | unchanged — unchanged. Design "Deferred" table: "Re-key `workflow_phases` by entity uuid (D3) \| In… | Every entities copy-rename captures triggers on OTHER tables whose SQL mentions `entities` (the two wp triggers), drops them, and replays the captured SQL verbatim after the RENAME. A future entities rebuild replays whatever wp trigger text exists at that time. |
| schema-14 | 3363-3481 (CREATE 3431-3453, DROP 3475, RENA… | _migration_12_... step 5i (phase_events copy-rename) | phase_events | migration | type_id+project_id(legacy) | never | EntityDatabase._migrate() v1 chain: every fresh file (fresh files are v1-generation) and rebuild_tool._replay_v1_chain;… | unchanged — unchanged. No W1/W2 change names it; plan Phase R: "The design also decides ... whether… | Widened event_type to 7, made phase nullable, added `metadata TEXT`; identity columns unchanged. |
| schema-62 | 4130-4144 (m13); live DDL | entity_display | entity_display | DDL | uuid | n/a | _insert_display_row (database.py:7567), get_entity_display (:10817) | unchanged — unchanged. No W1/W2 change names it. | `uuid TEXT PRIMARY KEY` FK entities(uuid) ON DELETE CASCADE, the model of a one-row-per-entity table enforced by schema. |
| schema-68 | 4146-4155 (m13) | migration_audit_log | migration_audit_log | DDL | none | n/a | _append_migration_audit_log (database.py:4353) | unchanged — unchanged. No W1/W2 change names it. | Free-form JSON payload; no entity key column. A re-key migration could log here. |
| schema-15 | 4590-4719 (CREATE 4657-4679, DROP 4699, RENA… | _copy_rename_phase_events_for_v14 (MIGRATIONS[14]) | phase_events | migration | type_id+project_id(legacy) | never | EntityDatabase._migrate() v1 chain: every fresh file (fresh files are v1-generation) and rebuild_tool._replay_v1_chain;… | unchanged — unchanged. No W1/W2 change names it; plan Phase R: "The design also decides ... whether… | Adds 'spawned_child'; identity columns unchanged. |
| schema-63 | 5435-5468 (m17); live DDL | cross_workspace_allowlist | cross_workspace_allowlist | DDL | uuid | n/a | set_parent cross-workspace allow-list | unchanged — unchanged. No W1/W2 change names it. | uuid FKs, CASCADE. Not a type_id reference. |
| schema-61 | 5592-5605 (m18 copy-rename); live DDL | entity_relations | entity_relations | DDL | uuid | n/a | dependencies / fixes edges (DependencyManager, register_entity depends_on_features) | unchanged — unchanged. No W1/W2 change names it. | uuid FKs with ON DELETE CASCADE. m18 folded entity_dependencies into it (forward-only). Not a type_id reference. |
| schema-16 | 5758-5895 (CREATE 5832-5845, DROP 5874, RENA… | _migration_19_widen_phase_events_cascade_ready (MIGRATIONS[… | phase_events | migration | type_id+project_id(legacy) | never | EntityDatabase._migrate() v1 chain: every fresh file (fresh files are v1-generation) and rebuild_tool._replay_v1_chain;… | unchanged — unchanged. No W1/W2 change names it; plan Phase R: "The design also decides ... whether… | Adds 'cascade_ready'; identity columns unchanged. |
| schema-20 | 5915-5935, 5962-5970, 6481-6517 | MIGRATIONS (1-19 + aliases 20-25), V2_MIGRATIONS (2-7), imp… | migration | migration | none | n/a | import of entity_registry.database; EntityDatabase.__init__ | unchanged — unchanged. Design "Deferred" table: "Re-key `workflow_phases` by entity uuid (D3) \| In… | Two lineages: a fresh file ends at v1 schema_version 25 with no schema_generation key (measured on fresh.db); the live file is schema_generation v2, schema_version 7. V2 steps 2-7 are also registered as v1 MIGRATIONS[20..25]. `assert max(V2_MIGRATIONS) == schema_v2.V2_SCHEMA_VERSION` (:6506) ties a… |
| schema-22 | 5943-5956 (MIGRATIONS_DOWN 11-17), 6520-6580… | MIGRATIONS_DOWN / _migrate_down (m11-down, m12-down, m14-do… | migration | migration | type_id | never | test-only: no production caller; doctor/check_status_write_path.py:83-87 only enumerates the functions | unchanged — unchanged. No W1/W2 change names it. | Unreachable on both real shapes: _migrate_down raises when the current version has no MIGRATIONS_DOWN entry (:6565), and fresh (25) and live (7) have none. The downs drop the wp triggers and workspace_uuid column (m11-down) and reverse the phase_events copy-renames, including `DELETE ... phase_even… |
| schema-17 | 5973-6169 (CREATE 6078-6100, INSERT-SELECT 6… | _v2_migration_2_mini_spec (V2_MIGRATIONS[2] and MIGRATIONS[… | phase_events | migration | type_id+project_id(legacy) | never | both chains: V2_MIGRATIONS[2] (live, already applied) and MIGRATIONS[20] (fresh files); rebuild_tool._apply_v2_chain | unchanged — unchanged. No W1/W2 change names it; plan Phase R: "The design also decides ... whether… | The repo's newest copy-rename template for these tables, generation-agnostic: probes sqlite_master first (replay-safe), BEGIN IMMEDIATE, captured-index replay with a name-set assertion, row-count assertion, foreign_key_check before COMMIT, literal COMMIT/ROLLBACK so it works on both EntityDatabase'… |
| schema-19 | 6078-6100 (last CREATE); live sqlite_master | phase_events (final shape, fresh v25 = live v2/7) | phase_events | DDL | type_id+project_id(legacy) | never | append_phase_event (writer), query_phase_events / query_phase_events_bulk (readers), rebuild_tool | unchanged — unchanged. No W1/W2 change names it; plan Phase R: "The design also decides ... whether… | No FK, no entity uuid, no workspace_uuid. Workspace is recoverable only through project_id = workspaces.project_id_legacy, which is NULL for 7 of 21 live workspaces (those append '__unknown__'), is not rewritten by re-attribution, and for 13 live rows names no workspace ('e8bdba5f147b'). |
| schema-23 | 6170-6204 | _v2_migration_3_state_only_axis_views (V2_MIGRATIONS[3] and… | view | migration | uuid | n/a | both chains; returns immediately on files without an events table (all fresh v1 files) | unchanged — unchanged. No W1/W2 change names it; plan R1 criterion 6: "It fits the v2 direction (en… | Probe accepts any entity_axis_state SQL containing "event_type != 'skipped'" and then replays views.py's _VIEWS_DDL. Live view text differs from what this code produces (see views row). |
| schema-24 | 6206-6380 | _v2_migration_4..7 (is_legacy, is_archived, is_deleted, imm… | entity read by type_id | migration | none for the flag DDL and the `status = 'archived'` UPDATE (:6276-6279); uuid f… | n/a for the entities flag columns; the phase_events read in this range is never… | both chains | unchanged — unchanged. No W1/W2 change names it. | Soft delete and archive are flag columns on entities (is_deleted, is_archived); nothing cascades to workflow_phases or phase_events, so a wp row outlives its entity's deletion and archive. The range also holds v2/5's phase_events read by type_id (fill-1). |
| fill-1 | 6293-6315 (archived-entity scan 6293-6295; p… | _v2_migration_5_explicit_archived_flag, status-restore loop… | phase_events | read (inside a migration) | type_id (the archived entity's type_id, row[1]; no project_id or workspace pred… | never | Both chains, and only while entities.is_archived is missing (the column probe returns first, :6272-6274): the v1 chain'… | unchanged — unchanged. No W1/W2 change names it; design:509 '1. **Phase 1 (P0): W1 and W2.**', and… | Reads phase_events by type_id alone, newest first, and keeps the first entity_status_changed event whose new_status is 'archived' and which has an old_status. Where two workspaces hold the type_id, that newest event among all holders decides each archived holder's restored status; the restore then… |
| schema-49 | 6593-6597, 6609-6660 | PHASE_EVENTS_COLS, _VALID_PARAMS / _REQUIRED_PARAMS | phase_events | read | none | n/a | query_phase_events, query_phase_events_bulk, append_phase_event validation | unchanged — unchanged. No W1/W2 change names it; plan Phase R: "The design also decides ... whether… | Explicit column list: a new phase_events column is invisible to both readers until added here; _VALID_PARAMS keys must equal the event_type CHECK list (10 values). |
| schema-51 | 6896-6975 | EntityDatabase._resolve_optional_workspace_filter | entity read by type_id | resolve | project_id(legacy) -> workspace_uuid | n/a (it produces the scope) | read paths in this class; write paths upsert_workflow_phase and update_entity re-attribution; entity_server.py:477/644/… | unchanged — unchanged; plan 2A: "The legacy-id lookup reuses `_resolve_optional_workspace_filter`,… | Rules: workspace_uuid wins (DeprecationWarning when both given); '__unknown__' -> canonical unknown uuid; other legacy id -> workspaces.project_id_legacy or ValueError; both None -> None, meaning 'no scoping'. The None result is what lets every optional-scope reader fall through to an unscoped quer… |
| schema-50 | 6980-7056 | EntityDatabase._resolve_identifier | entity read by type_id | resolve | uuid \| type_id+workspace_uuid \| type_id | optional (scoped when workspace_uuid or project_id is given) | get_entity, update_entity, delete_entity, set_parent, reparent_entity, get_lineage, export_lineage_markdown; backfill.p… | unchanged; related W2.1 — unchanged as code; W2.1 routes create/upsert_workflow_phase through it | Behaviour: uuid input -> that row, soft-deleted included; type_id + scope -> that workspace's row or 'Entity not found'; unscoped type_id -> the row if exactly one holds it, else ValueError 'Ambiguous type_id ... exists in multiple workspaces'. No is_deleted filter anywhere, so a soft-deleted names… |
| schema-53 | 7060-7094 | EntityDatabase.get_entity_by_uuid | entity read by type_id | read | uuid | n/a (uuid is global) | entity_server, workflow_state_server, dependencies.py, rollup.py, feature_lifecycle.py, backfill.py, frontmatter_inject… | unchanged — unchanged. No W1/W2 change names it. | The only per-entity read; hides soft-deleted rows unless include_deleted. |
| schema-55 | 7156-7175 | EntityDatabase.resolve_entity_uuid | entity read by type_id | resolve | type_id+workspace_uuid | always | workflow_state_server.py:1048, 1389, 1393 (complete_phase closes=) | unchanged — unchanged. No W1/W2 change names it. | Already the per-workspace resolver shape a re-key needs (returns (uuid, workspace_uuid) or (None, None)); no is_deleted filter. |
| schema-54 | 7177-7253 (exact match 7225-7237, prefix 723… | EntityDatabase.resolve_ref | entity read by type_id | resolve | uuid \| type_id(+workspace_uuid) \| type_id prefix | optional | entity_server.py:338/356/1022/1339/1340/1377/1378/1464/1465/1486, workflow_state_server.py:2157/2783, database.py:7797… | unchanged — unchanged. Design "Deferred": "Scope the 39 unscoped `get_entity` reads, and guard `upd… | Unscoped exact match takes the first row (SCAN entities, lowest rowid) with no ambiguity check and no is_deleted filter; the uuid branch hides soft-deleted rows. Prefix branch raises on multiple matches. |
| schema-57 | 7280-7322 | EntityDatabase.search_by_type_id_prefix | entity read by type_id | read | type_id prefix (+workspace_uuid) | optional | resolve_ref prefix branch; entity tools (other areas) | unchanged — unchanged. No W1/W2 change names it. | Unscoped call returns every workspace's matches. |
| schema-42 | 7686-7697, 7765-7776 | EntityDatabase.register_entity (entity_created event) | phase_events | write | type_id+project_id(legacy) | always (resolved workspace) | every registration (entity_server / workflow_state_server tools, backfill, batch) | unchanged — unchanged. No W1/W2 change names it; plan Phase R: "The design also decides ... whether… | Same label derivation: `project_id_legacy` of the workspace, else '__unknown__'; no entity uuid stored in the row. |
| schema-66 | 7792-7805 | entities.metadata.depends_on_features (JSON) | entity read by type_id | resolve | type_id text inside JSON | always at registration (resolve_ref(ref, workspace_uuid=ws_uuid)) | register_entity | unchanged — unchanged. No W1/W2 change names it. | A type_id-text reference stored in entities.metadata; resolved once at registration into entity_relations rows (uuid). The stored text is not re-keyed by a rename. |
| schema-43 | 7895-7937 | EntityDatabase.upsert_entity (status-change branch) | phase_events | write | type_id+workspace_uuid (entity row); type_id+project_id(legacy) (event) | always | register_entities_batch (database.py:10946), server_helpers, backfill | unchanged — unchanged. No W1/W2 change names it; plan Phase R: "The design also decides ... whether… | Scoped read `WHERE workspace_uuid = ? AND type_id = ?` (:7898), then an event row keyed by type_id + label. |
| schema-58 | 7981-7990, 8160-8162, 8377-8381, 9392-9396 | set_parent / reparent_entity / get_lineage / export_lineage… | entity read by type_id | resolve | type_id (+workspace_uuid optional) | optional | MCP set_parent / reparent / lineage / export tools (other areas) | unchanged; related W3.4 — unchanged as a method. W3.4 (plan 2C) changes its MCP callers: "Entity to… | Unscoped callers get Ambiguous on shared type_ids (never a silent pick). |
| schema-52 | 8212-8245 | EntityDatabase.get_entity | entity read by type_id | resolve | uuid \| type_id | never (no workspace parameter) | 39 production call lines (workflow_state_server.py 12, frontmatter_sync.py 5, entity_server.py 4, server_helpers.py 4,… | unchanged — unchanged. Design "Deferred": "Scope the 39 unscoped `get_entity` reads, and guard `upd… | Unscoped by signature: a type_id held by one workspace -> that entity; by two -> None (the Ambiguous ValueError is swallowed); single holder soft-deleted -> None unless include_deleted. Any reader that needs one workspace's entity must pass through a scoped resolver instead. |
| schema-56 | 8247-8277 | EntityDatabase.feature_entity_id | entity read by type_id | read | type_id | never (by design) | workflow_engine/feature_paths.py:85 (feature_dir_name) | unchanged; related W2.2,W2.4 — unchanged; W2.2-W2.4 reuse it: "The name comes from `feature_dir_nam… | Deliberately unscoped: namesakes that agree on entity_id answer once; disagreeing namesakes raise feature_not_found. |
| schema-45 | 8433-8472 (SQL 8459-8465) | EntityDatabase.set_archived | entity read by type_id | write | type_id (+workspace_uuid optional) | optional (without workspace_uuid it flags EVERY workspace's entity with that ty… | entity_status.py:58 and :230 (W1.1 deletes both), scripts/cleanup_backlog.py:200/260, scripts/c22_recreate_live_remaind… | unchanged; related W1.1,W1.2 — method unchanged; W1.1 deletes its two session-start callers; W1.2 a… | Not a wp/pe writer. Keyed by type_id: passing a uuid as the first argument matches no row and raises ValueError, so W1.2's call as written needs either type_id + workspace or a uuid-keyed method. |
| schema-46 | 8474-8505 | EntityDatabase.set_deleted | entity read by type_id | write | type_id (+workspace_uuid optional) | optional (unscoped call flags every namesake) | test-only (no production caller found) | unchanged — unchanged. No W1/W2 change names it. | Not a wp/pe writer; same type_id keying as set_archived. |
| synth-1 | 8506-8560 (resolution 8557-8559) | EntityDatabase.update_entity (identifier resolution) | entity read by type_id | resolve | uuid \| type_id+workspace_uuid (workspace_uuid, or legacy project_id) \| type_id | optional: scoped when workspace_uuid or project_id is passed; without either, _… | every update_entity caller in this inventory (engines rows whose object is 'entities (write by type_id)', MCP update_en… | unchanged; related W1.2,W1.7 — unchanged. No W1/W2 change edits EntityDatabase.update_entity; W1.2… | The uuid this line returns (entity_uuid) is the key the status write, the entity_status_changed phase event (schema-41, 8680-8709) and the re-attribution cascade (schema-40, 8763-8777) act on; the cascade re-reads the entity's type_id and updates workflow_phases WHERE type_id = ?. |
| schema-41 | 8680-8709 | EntityDatabase.update_entity (status change -> append_phase… | phase_events | write | type_id+project_id(legacy) (+workspace_uuid for the entities UPDATE) | always | MCP update_entity tool; dependencies.py cascade flips; engines' status writes | unchanged — unchanged. No W1/W2 change names it; plan Phase R: "The design also decides ... whether… | The resolved uuid is in hand (entity_uuid) but is converted back to (type_id, project_id label) for the event row; a label-less workspace becomes '__unknown__'. |
| schema-40 | 8737-8807 (cascade 8763-8777) | EntityDatabase.update_entity (re-attribution cascade, new_p… | workflow_phases | write | type_id | never | MCP update_entity tool with new_project_id (entity_server.py:1085 -> :380-384) | unchanged — unchanged in Phase 1. Plan 2B: "re-planned into Phase R (D3 ruling) ... Phase R's playb… | Entity moves by uuid, but its wp row is found by type_id alone, so the cascade moves ANY workspace's row for that type_id. Probe: moving B's entity to C moved A's row to C. |
| schema-47 | 8808-8966 (UPDATE 8927-8933) | EntityDatabase.backfill_project_ids | entity read by type_id | write | uuid (workspace_uuid + artifact_path prefix) | always (claims only from the __unknown__ workspace) | entity_server startup (entity_server.py:263 -> :191) | unchanged — unchanged. Design Deferred: "`db.backfill_project_ids` claims `__unknown__` rows by `ar… | Re-attributes entities to a workspace WITHOUT cascading to workflow_phases.workspace_uuid or phase_events.project_id. A kept workspace copy on the wp row drifts silently on this path. |
| schema-44 | 8967-9119 (soft delete 9083-9086; stale docs… | EntityDatabase.delete_entity | entity read by type_id | resolve | type_id+workspace_uuid (optional), or uuid | optional (unscoped type_id must be globally unique) | MCP delete_entity tool (entity_server.py _process_delete_entity) | unchanged; related W3.4 — unchanged as a method. W3.4 (plan 2C) changes its MCP callers: "Entity to… | Soft-deletes by uuid and touches no wp/pe row; the wp row of a deleted entity stays live under its type_id and still blocks another workspace's row for that type_id. Docstring still says it deletes workflow_phases (stale). |
| schema-48 | 9120-9239 (UPDATE 9216-9221) | EntityDatabase.claim_unknown_entities | entity read by type_id | write | uuid | always | test-only (no production caller found) | unchanged — unchanged. No W1/W2 change names it. | Same as backfill_project_ids: moves entities by uuid, no wp/pe cascade. |
| schema-26 | 9734-9746 | EntityDatabase.append_phase_event step 2 | phase_events | write | type_id+project_id(legacy) | never (project_id label is supplied by the caller) | workflow_state_server.py:1201/1210/1497/2293/2841, entity_server.py:957 (spawned_child), register_entity (database.py:7… | unchanged — unchanged. No W1/W2 change names it; plan Phase R: "The design also decides ... whether… | The event row carries no entity key: it is re-attributable only by (type_id, project_id). The workspace_uuid argument is accepted but not stored. |
| schema-27 | 9751-9766 | EntityDatabase.append_phase_event step 3 | entity read by type_id | write | type_id+workspace_uuid | always (workspace_uuid required for these event types) | entity_status_changed from update_entity/upsert_entity/cascade_ready | unchanged — unchanged. No W1/W2 change names it. | Already scoped; the status UPDATE could take the entity uuid directly. |
| schema-28 | 9776-9784 | EntityDatabase.append_phase_event step 5 (started/completed… | workflow_phases | write | type_id | never | phase transitions: workflow_state_server.py transition/complete callers (other areas) | unchanged — unchanged. Design "Deferred": "Scope the 39 unscoped `get_entity` reads, and guard `upd… | UPDATE keyed by type_id alone; the method has no entity uuid in hand at this point. A per-entity key needs the entity (uuid) resolved before step 5, scoped by the caller's workspace. |
| schema-29 | 9786-9827 (fallback 9811-9815) | EntityDatabase.append_phase_event step 6 (v2 dual-write) | entity read by type_id | resolve | type_id+workspace_uuid, else type_id | optional (scoped when workspace_uuid is passed; unscoped .fetchone() otherwise) | every append on a v2 file except mini_spec | unchanged — unchanged in Phase 1. Plan 2B: "re-planned into Phase R (D3 ruling) ... Phase R's playb… | Unscoped fallback returns the lowest-rowid entity (plan: SCAN entities) with no ambiguity check, so the v2 event can land on another workspace's entity. Its comment (:9794-9799) claims exactness because step 5 is type_id-keyed; probe step 2 shows the wp row (autofilled to A) moved while the v2 'sta… |
| schema-30 | 9831-9867 | EntityDatabase.query_phase_events | phase_events | read | type_id and/or project_id(legacy) | optional (project_id label only; no workspace_uuid parameter) | workflow_state_server.py:1301, 2324, 2915, 2920, 2938, 2961, 2979 (5 of 7 pass project_id) | unchanged — unchanged. No W1/W2 change names it; plan Phase R: "The design also decides ... whether… | Filters by type_id alone mix two workspaces' histories of a shared type_id; the only scope is the legacy label, which is '__unknown__' for label-less workspaces and stale after re-attribution. |
| schema-31 | 9869-9946 | EntityDatabase.query_phase_events_bulk | phase_events | read | type_id | never | workflow_state_server.py:1768 (drift detector, reconcile_status) | unchanged — unchanged. No W1/W2 change names it; plan Phase R: "The design also decides ... whether… | type_id IN (...) with no scope at all; a per-entity key would need entity keys (or type_id + workspace) as input. |
| schema-32 | 9992-9996 | EntityDatabase.create_workflow_phase (entity lookup) | entity read by type_id | resolve | type_id | never | feature_lifecycle.py:305 (init_feature_state), task_promotion.py:403 (promote_task), engine.py:633 (hydration; W1.5 del… | changed (W2.1) — changed by W2.1: "resolves the entity with `_resolve_identifier(type_id, workspace… | Unscoped `.fetchone()` = lowest-rowid entity (plan: SCAN entities); its uuid feeds the v2 emit. W2.1 replaces it with _resolve_identifier (scoped, or refuses ambiguity). |
| schema-33 | 10016-10046 | EntityDatabase.create_workflow_phase (INSERT, v2 emit, re-r… | workflow_phases | write | type_id | never | same as the lookup row | changed (W2.1) — changed by W2.1: "resolves the entity with `_resolve_identifier(type_id, workspace… | INSERT omits workspace_uuid and uuid (trigger fills workspace, uuid stays NULL); PK collision on a second workspace's row raises 'Workflow phase already exists'; the re-read is by type_id. W2.1 adds workspace_uuid and uuid to the INSERT but the PK is still type_id, so the second workspace still can… |
| schema-34 | 10048-10056 | EntityDatabase.get_workflow_phase | workflow_phases | read | type_id | never | 19 production call lines: engine.py, entity_engine.py, router.py, feature_lifecycle.py, reconciliation.py, rollup.py, b… | unchanged — unchanged. No W1/W2 change names it. | Signature has no workspace or entity key; SELECT * by type_id returns whichever workspace owns the single row. |
| schema-35 | 10058-10179 (SELECT 10123-10127, UPDATE 1016… | EntityDatabase.update_workflow_phase | workflow_phases | write | type_id | optional (workspace_uuid is a read-side assertion only, never part of the WHERE) | 13 production call lines, 4 pass the workspace_uuid keyword: backfill.py:216/317 (W2.6 adds workspace to :317), engine.… | unchanged — unchanged. Design "Deferred": "Scope the 39 unscoped `get_entity` reads, and guard `upd… | With the assertion it refuses another workspace's row; without it it updates whoever owns the type_id. Its docstring calls wp.workspace_uuid immutable post-m11, but no trigger enforces that and the update_entity cascade rewrites it. |
| schema-36 | 10181-10266 (default 10235-10236, resolve 10… | EntityDatabase.upsert_workflow_phase (scope + entity check) | entity read by type_id | resolve | type_id+workspace_uuid | always (defaults to the __unknown__ workspace when both workspace_uuid and proj… | backfill.py:326/395 (pass project_id), router.py:393 (passes workspace_uuid) | changed (W2.1) — changed by W2.1: "resolves the entity the same way; inserts `workspace_uuid` and `… | The entity check is scoped, but its uuid is discarded; the write that follows is type_id-keyed. |
| schema-37 | 10268-10294 (INSERT OR IGNORE 10274-10279, U… | EntityDatabase.upsert_workflow_phase (write) | workflow_phases | upsert | type_id | never | same as the scope row | changed (W2.1) — changed by W2.1: "resolves the entity the same way; inserts `workspace_uuid` and `… | INSERT OR IGNORE omits workspace_uuid/uuid; when another workspace owns the type_id the insert is ignored and the UPDATE overwrites that workspace's row. W2.1 makes it refuse instead; under a type_id PK the calling workspace still cannot get its own row. |
| schema-38 | 10296-10314 | EntityDatabase.delete_workflow_phase | workflow_phases | delete | type_id | never | test-only (no production caller found by grep) | unchanged — unchanged. Design "Deferred": "Scope the 39 unscoped `get_entity` reads, and guard `upd… | Deletes by type_id alone. |
| schema-39 | 10316-10390 (filter 10364-10366, join 10379-… | EntityDatabase.list_workflow_phases | workflow_phases | join | type_id | optional (filters e.workspace_uuid, the JOINED entity's workspace, plus orphans) | ui/routes/board.py:72, ui/routes/entities.py:24/27/193, backfill.py:213, reconciliation.py:821, engine.py:285/328 (6 of… | unchanged — unchanged in Phase 1. Plan 2B: "re-planned into Phase R (D3 ruling) ... Phase R's playb… | Join by type_id alone: a wp row joins every namesake entity. Measured on a live copy: unscoped 534 rows for 529 wp rows; list_workflow_phases(workspace_uuid=f7b49c1d...) returns 5 rows owned by workspace 69696982. |
| schema-21 | 11001-11066 (_migrate), 11068-11112 (_refuse… | EntityDatabase._migrate / _migrate_v2 / _refuse_if_file_is_… | migration | migration | none | n/a | every EntityDatabase open (MCP servers, hooks, doctor, UI, scripts) | unchanged — unchanged. No W1/W2 change names it. | Per-version loop stamps schema_version after each function and commits, so an interrupted chain resumes at the next version. C23 guard: a file stamped above this build's max gets a write-denying authorizer - after a version bump on the live file, already-running old-build processes can still read b… |
| schema-71 | 11144-11189; call sites 8202, 9091, 9820, 10… | EntityDatabase._emit_v2_event | events | write | uuid | n/a | reparent_entity, delete_entity, append_phase_event step 6, create_workflow_phase (v2 files only) | unchanged — unchanged. No W1/W2 change names it; plan R1 criterion 6: "It fits the v2 direction (en… | The v2 writes are keyed by an entity uuid the caller resolved; two of the four callers resolve it unscoped by type_id (append_phase_event fallback, create_workflow_phase lookup), so v2 attribution inherits their first-row pick. |

### `plugins/pd/hooks/lib/entity_registry/axes.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| schema-73 | 125-149, 155-194 | entity_phase_status view; events_vocab_pipeline / events_vo… | view | view | uuid | n/a | no production reader; triggers fire on every v2 events INSERT | unchanged — unchanged. No W1/W2 change names it; plan R1 criterion 6: "It fits the v2 direction (en… | entity_phase_status renames entity_state columns (pipeline_phase, execution_status). Vocab triggers constrain to_value on pipeline (6 phases) and execution (7 statuses incl 'ready', which workflow_phases.kanban_column's CHECK lacks). |

### `plugins/pd/hooks/lib/entity_registry/backfill.py` (8)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-63 | 210-214 | run_backfill | workflow_phases | join | type_id (Python set membership) | always: workspace resolved at :202 from project_id; list_workflow_phases(worksp… | entity-server startup (entity_server.py:277) — but run_backfill returns at :191 when backfill_complete == '1' and backf… | unchanged — unchanged: W2.6 names backfill_workflow_phases' lines (`:254`, `:317`, `:326`, `:395`,… | `done = {e["type_id"] ...}` and `row["type_id"] in done` pair entity and row by type_id; a namesake's row passes the join filter whenever any holder is in this workspace |
| engines-64 | 216-217 | run_backfill | workflow_phases | write | type_id (workspace asserted) | always: workspace_uuid=workspace_uuid (ValueError on a stored-workspace mismatc… | entity-server startup (entity_server.py:277) — but run_backfill returns at :191 when backfill_complete == '1' and backf… | unchanged — unchanged (see the :210-214 row) | writes workflow_phase='finish' by row['type_id']; the row's own workspace_uuid is not used as key |
| engines-65 | 254 | backfill_workflow_phases | entities (unscoped list feedi… | read | none (whole table) | never: db.list_entities() with no workspace | entity-server startup, every server start (entity_server.py:285-287: backfill_workflow_phases(_db, _artifacts_root, pro… | changed (W2.6) — changed by W2.6: design:301 'iterate only the server's workspace (`:254`)', design… | not a workflow_phases access; it decides which type_ids reach the writes at :317/:326/:395 (every workspace's entities, written with the server's project_id) |
| engines-66 | 297 | backfill_workflow_phases | workflow_phases | read | type_id | never | entity-server startup, every server start (entity_server.py:285-287: backfill_workflow_phases(_db, _artifacts_root, pro… | changed (W2.6) — changed by W2.6: design:301 'iterate only the server's workspace (`:254`)', design… | existence read by entity['type_id']; entity dict (uuid, workspace_uuid) in hand |
| engines-67 | 317-321 | backfill_workflow_phases | workflow_phases | write | type_id | never today (no workspace argument) | entity-server startup, every server start (entity_server.py:285-287: backfill_workflow_phases(_db, _artifacts_root, pro… | changed (W2.6) — changed by W2.6: design:301 'iterate only the server's workspace (`:254`)', design… | writes by entity['type_id']; entity uuid/workspace in the loop's entity dict |
| engines-68 | 326-331 | backfill_workflow_phases | workflow_phases | upsert | type_id (+ server project_id for the existence check) | always, but with the SERVER's workspace: project_id=project_id resolves the ser… | entity-server startup, every server start (entity_server.py:285-287: backfill_workflow_phases(_db, _artifacts_root, pro… | changed (W2.6) — changed by W2.6: design:301 'iterate only the server's workspace (`:254`)', design… | writes by entity['type_id']; the entity's own uuid and workspace_uuid are in the loop dict but not passed |
| engines-69 | 390 | backfill_workflow_phases | workflow_phases | read | type_id | never | entity-server startup, every server start (entity_server.py:285-287: backfill_workflow_phases(_db, _artifacts_root, pro… | changed (W2.6) — changed by W2.6: design:301 'iterate only the server's workspace (`:254`)', design… | skip-if-exists by type_id; entity dict in hand |
| engines-70 | 395-402 | backfill_workflow_phases | workflow_phases | upsert | type_id (+ server project_id) | always, with the SERVER's workspace (as the :326 row) | entity-server startup, every server start (entity_server.py:285-287: backfill_workflow_phases(_db, _artifacts_root, pro… | changed (W2.6) — changed by W2.6: design:301 'iterate only the server's workspace (`:254`)', design… | writes by entity['type_id']; entity uuid and workspace_uuid in the loop dict but not passed |

### `plugins/pd/hooks/lib/entity_registry/dependencies.py` (2)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-71 | 184 | DependencyManager._evaluate_and_flip | entities (write by type_id) | write | type_id (uuid in hand) | never | DependencyManager.cascade_unblock (dependencies.py:118-132) <- EntityDatabase.update_entity on a resolving status (data… | changed (W1.7) — changed by W1.7: design:234 '`DependencyManager._evaluate_and_flip` writes status… | uid (the loop variable) is the entity uuid; the write uses entity['type_id'], so a shared type_id raises 'Ambiguous' inside the flip transaction; the status change also appends an entity_status_changed phase_events row for the resolved entity (database.py:8680-8710) |
| engines-72 | 185-196 | DependencyManager._evaluate_and_flip | phase_events | write | type_id+project_id(legacy) | optional: workspace_uuid=entity.get('workspace_uuid') feeds the v2 entity looku… | DependencyManager.cascade_unblock (dependencies.py:118-132) <- EntityDatabase.update_entity on a resolving status (data… | changed (W1.7) — changed by W1.7: design:234 '`DependencyManager._evaluate_and_flip` writes status… | the row written carries (type_id, project_id) with project_id falling back to '__unknown__' (:187); the entity uuid (uid) is in hand; event_type 'cascade_ready' is not among step 5's workflow_phases-projecting types ('started', 'completed', 'backward', database.py:9776-9784) |

### `plugins/pd/hooks/lib/entity_registry/display.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-83 | 123-233 (rename_entity 123-189; _rename 190-… | _rename (rename_entity) | entities (type_id rename) + e… | write | uuid | n/a (uuid) | test-only: module docstring 'Ships dark (design D1): no live code path imports this module, only its own tests do' | unchanged; related W5.1 — unchanged in Phase 1; W5.1 (Phase 4) deletes it: design:477 'Delete `enti… | renames entities.type_id by uuid and appends a 'renamed' events row by entity uuid; it does not touch workflow_phases (PK type_id; live trigger enforce_immutable_wp_type_id aborts UPDATE OF type_id) or phase_events (type_id column), so both would keep the old type_id (problem 9) |

### `plugins/pd/hooks/lib/entity_registry/events.py` (2)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| schema-69 | 76-99 | _EVENTS_DDL (events table, events_no_update/delete/replace) | events | DDL | uuid | n/a | created on v2 files only (rebuild_tool._seed_v2_schema, schema_v2.bootstrap_v2); absent on every fresh v1 file | unchanged — unchanged. No W1/W2 change names it; plan R1 criterion 6: "It fits the v2 direction (en… | Already keyed per entity: entity_uuid NOT NULL REFERENCES entities(uuid) (no ON DELETE) + immutability triggers, so entities can only be soft-deleted on v2 files. Indexed (entity_uuid, axis). |
| schema-70 | 102-118, 151-256, 257-276 | connect_v2 / append_event / read_events | events | write | uuid | n/a | append_event: EntityDatabase._emit_v2_event (database.py:11183), display.rename_entity (display.py:220, test-only), scr… | unchanged — unchanged. No W1/W2 change names it; plan R1 criterion 6: "It fits the v2 direction (en… | No production code READS the events table: read_events has no non-test caller. |

### `plugins/pd/hooks/lib/entity_registry/frontmatter_inject.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-80 | 160 | main | entity read by type_id | read | type_id | never | skills/workflow-transitions/SKILL.md:28 (frontmatter_inject.py CLI at every phase-exit commit) | unchanged — unchanged: no W1/W2 change names it; design:374 'The 39 unscoped `get_entity` reads. Th… | the CLI takes <artifact_path> <feature_type_id> only; the matched entity's uuid is stamped into the artifact's frontmatter (:166), so a foreign-only type_id stamps another workspace's uuid (I2 S-44) |

### `plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py` (2)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-81 | 236 | detect_drift | entity read by type_id | read | type_id when given, else the header's entity_uuid | never | MCP reconcile_frontmatter single-feature (workflow_state_server.py:1920), scan_all (:586) <- MCP reconcile_frontmatter… | unchanged — unchanged: no W1/W2 change names it; design:374 'The 39 unscoped `get_entity` reads. Th… | with a type_id argument the read is unscoped; the uuid path (header entity_uuid) is exact |
| engines-82 | 336 | stamp_header | entity read by type_id | read | type_id | never | backfill_headers (:534, which lists every workspace's features unscoped at :518) <- frontmatter_sync_cli backfill; fron… | unchanged — unchanged: no W1/W2 change names it; design:374 'The 39 unscoped `get_entity` reads. Th… | writes the matched row's uuid into the file; the caller at :534 holds the entity dict (uuid) but passes entity['type_id'] |

### `plugins/pd/hooks/lib/entity_registry/rebuild_tool.py` (5)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| schema-76 | 76-167 | _replay_v1_chain / _seed_v2_schema / _apply_v2_chain / _sta… | migration | migration | none | n/a | rebuild_tool CLI main() (manual v1->v2 cutover; live cutover 2026-07-25T02:48:24Z per ~/.claude/pd/migrations/v2-cutove… | unchanged — unchanged. No W1/W2 change names it. | A staging file = full v1 chain (now 1..25) + events/views/axes DDL + all V2_MIGRATIONS + stamp v2/7. Built now it matches live except the entity_axis_state view. Any new V2_MIGRATIONS entry also runs here (all entries must be replay-safe). |
| schema-77 | 303-387 (type_id joins 325-340; event_type s… | _preimport_vocab_diff | phase_events | join | type_id | never | rebuild_tool run (reads the OLD v1 file) | unchanged — unchanged. No W1/W2 change names it. | Two type_id-only joins against the old file (phase_events JOIN entities; entities LEFT JOIN workflow_phases); vocabulary check only. |
| schema-78 | 786-857 (INSERT 838-846) | _import_workflow_phases | workflow_phases | write | type_id+workspace_uuid (old row) -> uuid | always | rebuild_tool run | unchanged — unchanged. No W1/W2 change names it. | Keys each old row by (old wp.workspace_uuid, type_id) through secondary_map (rebuild_tool.py:270-274) and writes uuid and workspace_uuid explicitly - the only writer outside the migrations (m6 backfill) that sets wp.uuid. Its INSERT names 9 columns; a wp shape change must keep them insertable. The… |
| schema-80 | 906-976 | _insert_event / _emit_events_for_entity | events | write | uuid | n/a | rebuild_tool run | unchanged — unchanged. No W1/W2 change names it. | Backfilled v2 events per surviving entity uuid (actor 'backfill:132'). |
| schema-79 | 977-1110 (INSERT 1036-1047, grouping 1069-10… | _emit_all_events (phase_events copy) | phase_events | write | type_id+project_id(legacy) | never (workspace recovered via workspaces.project_id_legacy) | rebuild_tool run | unchanged — unchanged. No W1/W2 change names it. | Copies every phase_events row (source re-stamped 'backfill'); groups rows per entity by (workspace from the project_id label, type_id). Unresolvable labels become orphan_phase_event anomalies (row still copied). |

### `plugins/pd/hooks/lib/entity_registry/schema_v2.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| schema-74 | 41-104, 145-208 | _CORE_DDL / DDL_REGISTRY / bootstrap_v2 | migration | DDL | uuid | n/a | bootstrap_v2: scripts/seed-census-db.py:173 and tests only; rebuild_tool seeds every owner EXCEPT 'core' | unchanged — unchanged. No W1/W2 change names it; plan R1 criterion 6: "It fits the v2 direction (en… | The dark v2 core: entities.type_id `NOT unique (FR-4)` with a plain idx_entities_type_id; relations and sequences keyed by uuid7; no workflow_phases or phase_events at all. V2_SCHEMA_VERSION = 7 (:31). |

### `plugins/pd/hooks/lib/entity_registry/server_helpers.py` (7)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-73 | 257 | _process_register_entity | entity read by type_id | read | type_id | never | MCP register_entity (entity_server.py:542 -> :677; /pd:add-to-backlog, /pd:create-feature, /pd:create-project, decompos… | unchanged — unchanged: no W1/W2 change names it; design:374 'The 39 unscoped `get_entity` reads. Th… | existence check before registering into registration_workspace_uuid (:285-287); a type_id held only by another workspace makes a successful new registration answer 'Already existed' (I2 S-31) |
| engines-74 | 265 | _process_register_entity | entity read by type_id | read | type_id | never | unreachable from MCP: the only production call passes parent_type_id=None (entity_server.py:679 'parent_type_id removed… | unchanged — unchanged: no W1/W2 change names it; design:374 'The 39 unscoped `get_entity` reads. Th… | parent resolution by type_id with no workspace |
| engines-75 | 311 | _process_register_entity | entities (write by type_id: p… | write | type_id | never | unreachable from MCP: the only production call passes parent_type_id=None (entity_server.py:679 'parent_type_id removed… | unchanged — unchanged in Phase 1: no W1/W2 change names it | set_parent resolves child and parent type_ids unscoped (database.py:7981-7990) |
| engines-76 | 317 | _process_register_entity | entity read by type_id | read | type_id | never | MCP register_entity (entity_server.py:542 -> :677; /pd:add-to-backlog, /pd:create-feature, /pd:create-project, decompos… | unchanged — unchanged: no W1/W2 change names it; design:374 'The 39 unscoped `get_entity` reads. Th… | re-read after a conflict in registration_workspace_uuid, by type_id with no workspace |
| engines-77 | 329 | _process_register_entity | entity read by type_id | read | type_id | never | unreachable from MCP: the only production call passes parent_type_id=None (entity_server.py:679 'parent_type_id removed… | unchanged — unchanged: no W1/W2 change names it; design:374 'The 39 unscoped `get_entity` reads. Th… | re-read by type_id with no workspace |
| engines-78 | 484 | _process_get_lineage | entity read by type_id (linea… | read | type_id | never | MCP get_lineage (entity_server.py:1046 -> :1079, after _resolve_ref_param turns a ref into a type_id); /pd:show-lineage… | unchanged — unchanged in Phase 1: no W1/W2 change names it (get_lineage is not in W3.4's tool list,… | get_lineage resolves the start type_id unscoped (database.py:8377) |
| engines-79 | 517 | _process_set_parent | entities (write by type_id: p… | write | type_id | never | MCP set_parent (entity_server.py:974 -> :1009; child ref resolved with the project id, parent ref without, then both pa… | unchanged; related W3.4 — unchanged in Phase 1; W3.4 (Phase 2C) names it: design:351 '`set_parent`,… | set_parent re-resolves both type_ids unscoped (database.py:7981-7990); design N4 |

### `plugins/pd/hooks/lib/entity_registry/views.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| schema-72 | 86-105 | entity_axis_state, entity_state (views) | view | view | uuid | n/a | no production reader (only tests and the bench script); created on v2 files only | unchanged — unchanged. No W1/W2 change names it; plan R1 criterion 6: "It fits the v2 direction (en… | Per-entity by construction (GROUP BY entity_uuid, axis; entity_state FROM entities ent). The live view text is `WHERE to_value IS NOT NULL AND event_type != 'skipped'`, but views.py:90 and a rebuild-staging file built now have only `WHERE event_type != 'skipped'`; no committed code produces the liv… |

### `plugins/pd/hooks/lib/workflow_engine/engine.py` (9)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-1 | 102-105 (read 102; no-row fall-through 105) | WorkflowStateEngine.get_state | workflow_phases | read | type_id | never | MCP get_phase (workflow_state_server.py:2178 -> _process_get_phase :1005; /pd:show-status, /pd:wrap-up, /pd:secretary,… | changed (W1.5) — changed by W1.5: design:216 'What `get_state` answers instead: None when the DB ha… | signature get_state(self, feature_type_id) carries only a type_id; no uuid or workspace parameter exists anywhere in WorkflowStateEngine's read path, and FeatureWorkflowState (models.py:11-19) has feature_type_id but no uuid/workspace field; a per-entity key needs the entity uuid (or type_id + work… |
| engines-2 | 156-160 | WorkflowStateEngine.transition_phase | workflow_phases | write | type_id (workspace_uuid only asserted against the stored row) | optional: workspace_uuid=workspace_uuid; update_workflow_phase selects `WHERE t… | MCP transition_phase (workflow_state_server.py:2193; workflow-transitions skill step 2, i.e. every phase command): via… | unchanged — unchanged: design:366-367 'Writers keyed by type_id alone, when called without a worksp… | writes the row by feature_type_id; the only identity in scope is the type_id argument plus an optional workspace; a per-entity key needs the entity uuid here (EntityWorkflowEngine holds it but passes entity['type_id'], entity_engine.py:241/:280) |
| engines-3 | 214-219 | WorkflowStateEngine.complete_phase | workflow_phases | write | type_id (workspace_uuid only asserted) | optional: same as transition_phase (assertion-only workspace; MCP passes `_work… | MCP complete_phase (workflow_state_server.py:2226; workflow-transitions skill, every phase exit): via EntityWorkflowEng… | unchanged — unchanged: design:366-367 'Writers keyed by type_id alone, when called without a worksp… | writes last_completed_phase/workflow_phase by feature_type_id; needs the entity uuid, which only the EntityWorkflowEngine caller holds (entity_engine.py:155/:169) |
| engines-4 | 222 | WorkflowStateEngine.complete_phase | entities (write by type_id) | write | type_id+workspace_uuid (workspace optional) | optional: update_entity resolves `_resolve_identifier(type_id, project_id, work… | MCP complete_phase (workflow_state_server.py:2226; workflow-transitions skill, every phase exit): via EntityWorkflowEng… | unchanged — unchanged: no W1/W2 change names engine.py:222 | status write by type_id; the status change also appends an entity_status_changed phase_events row keyed by the RESOLVED entity (database.py:8680-8710) and runs cascade_unblock (database.py:8722-8735); passing the entity uuid would make the write exact (update_entity accepts a uuid, database.py:7014… |
| engines-5 | 285-287 | WorkflowStateEngine.list_by_phase | workflow_phases | read | none (filter workflow_phase); DB API joins wp.type_id = e.type_id (database.py:… | optional: MCP list_features_by_phase passes ws_filter (current workspace by def… | MCP list_features_by_phase (workflow_state_server.py:2429 -> :1706); /pd:list-features --phase | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | consumes rows the type_id join builds; _row_to_state keys the result by row['type_id'] (engine.py:375); a shared type_id with a workspace filter admits the row whenever ANY namesake entity is in the workspace |
| engines-6 | 322-334 | WorkflowStateEngine.list_by_status | workflow_phases | join | type_id (Python dict join) | optional: both list_entities(entity_type='feature', workspace_uuid) and list_wo… | MCP list_features_by_status (workflow_state_server.py:2460 -> :1714); /pd:list-features --status, /pd:create-feature in… | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | pairs entity and row in Python: `wp_map = {r["type_id"]: r for r in wp_rows}` then `wp_map.get(type_id)`; the entity dicts carry 'uuid' but the pairing uses type_id, so with no workspace filter two namesake entities both map to the single row |
| engines-7 | 599 | WorkflowStateEngine._hydrate_from_meta_json | entity read by type_id | read | type_id | never | get_state's fall-through when no row exists (engine.py:105), so every get_state caller: MCP get_phase (workflow_state_s… | deleted (W1.5) — deleted by W1.5: design:215 'What goes: `engine._hydrate_from_meta_json` (`engine.… | none after W1.5 (deleted). Today: an ambiguous type_id answers None, so hydration writes nothing |
| engines-8 | 633-639 | WorkflowStateEngine._hydrate_from_meta_json | workflow_phases | write | type_id | never: create_workflow_phase has no workspace parameter; it resolves the entity… | get_state's fall-through (engine.py:105): MCP get_phase (workflow_state_server.py:2178 -> _process_get_phase :1005; /pd… | deleted (W1.5); related W2.1 — deleted by W1.5 (design:215); until 1B lands it reaches W2.1's new r… | none after W1.5 (deleted) |
| engines-9 | 649 | WorkflowStateEngine._hydrate_from_meta_json | workflow_phases | read | type_id | never | the ValueError branch after create_workflow_phase (:640-652), inside hydration | deleted (W1.5) — deleted by W1.5 (design:215) | none after W1.5 (deleted) |

### `plugins/pd/hooks/lib/workflow_engine/entity_engine.py` (13)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-11 | 169-171 | EntityWorkflowEngine.complete_phase | workflow_phases (via Workflow… | write | type_id (entity uuid in hand, dropped) | optional: forwards workspace_uuid (MCP passes `_workspace_uuid or None`) | EntityWorkflowEngine.complete_phase (entity_engine.py:127) <- MCP complete_phase (workflow_state_server.py:1411-1417) f… | unchanged — unchanged: no W1/W2 change names it (the frozen get_state it reaches loses hydration by… | method parameter is entity_uuid and it loads the entity by uuid (:155), but hands only entity['type_id'] (:164) to the type_id-only WorkflowStateEngine API |
| engines-12 | 280-283 | EntityWorkflowEngine.transition_phase | workflow_phases (via Workflow… | write | type_id (entity uuid in hand, dropped) | optional: forwards workspace_uuid | MCP transition_phase (workflow_state_server.py:2193; workflow-transitions skill step 2, i.e. every phase command): via… | unchanged — unchanged: no W1/W2 change names it | entity loaded by uuid (:233); passes entity['type_id'] (:241) to the type_id-only frozen engine |
| engines-13 | 309 | EntityWorkflowEngine.get_state | workflow_phases (via Workflow… | read | type_id (entity uuid in hand, dropped) | never | test-only: no production caller of EntityWorkflowEngine.get_state (pygrep of plugins/pd/mcp, ui, hooks and scripts, tes… | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | entity loaded by uuid (:301); passes entity['type_id'] |
| engines-14 | 312 | EntityWorkflowEngine.get_state | workflow_phases | read | type_id (entity uuid in hand) | never | test-only (see the :309 row) | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | reads the non-feature row by entity['type_id'] although the entity uuid was the lookup key (:301) |
| engines-15 | 388 | EntityWorkflowEngine.abandon_entity | entities (write by type_id) | write | type_id (entity uuid in hand) | never | test-only: abandon_entity has no production caller (only test_entity_engine.py) | unchanged — unchanged: no W1/W2 change names it (W1.7's by-uuid writes list only rollup.py, reconci… | status write by entity['type_id']; unscoped, so a shared type_id raises 'Ambiguous'; the uuid (entity_uuid) is the method parameter; the status change also appends a phase_events row for the resolved entity (database.py:8680-8710) |
| engines-16 | 415 | EntityWorkflowEngine._abandon_descendants | entities (write by type_id) | write | type_id (child uuid in hand) | never | test-only (abandon_entity cascade=True) | unchanged — unchanged: no W1/W2 change names it | children come from get_children_by_uuid (:407) and carry 'uuid' (used at :416); the write uses child['type_id'] |
| engines-17 | 448 | EntityWorkflowEngine._fived_complete | workflow_phases | read | type_id (entity dict in hand) | never | EntityWorkflowEngine.complete_phase (entity_engine.py:127) <- MCP complete_phase (workflow_state_server.py:1411-1417) f… | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | the entity dict (with 'uuid') is the method argument; the read uses entity['type_id'] (:427) |
| engines-18 | 469-473 | EntityWorkflowEngine._fived_complete | workflow_phases | write | type_id | never (no workspace argument) | EntityWorkflowEngine.complete_phase (entity_engine.py:127) <- MCP complete_phase (workflow_state_server.py:1411-1417) f… | unchanged — unchanged: design:366-367 'Writers keyed by type_id alone, when called without a worksp… | writes by entity['type_id'] with no workspace; entity uuid available in the entity dict |
| engines-19 | 475 | EntityWorkflowEngine._fived_complete | entities (write by type_id) | write | type_id | never | EntityWorkflowEngine.complete_phase (entity_engine.py:127) <- MCP complete_phase (workflow_state_server.py:1411-1417) f… | unchanged — unchanged: no W1/W2 change names it | status write by type_id although the entity dict (uuid) is in hand |
| engines-20 | 503 | EntityWorkflowEngine._fived_transition | workflow_phases | read | type_id | never | EntityWorkflowEngine.transition_phase (:289) <- MCP transition_phase, 5D kinds only; 0 live | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | entity dict (uuid) in hand; reads by entity['type_id'] (:499) |
| engines-21 | 512-514 | EntityWorkflowEngine._fived_transition | workflow_phases | write | type_id | never (no workspace argument) | as the :503 row; 5D kinds only; 0 live | unchanged — unchanged: design:366-367 'Writers keyed by type_id alone, when called without a worksp… | writes by type_id with no workspace; entity uuid available |
| engines-22 | 711-714 | EntityWorkflowEngine._propagate_anomaly | entities (write by type_id) | write | type_id (parent uuid in hand) | never | EntityWorkflowEngine.complete_phase (entity_engine.py:127) <- MCP complete_phase (workflow_state_server.py:1411-1417) f… | unchanged — unchanged: no W1/W2 change names it | metadata write by parent['type_id'] with no workspace; parent was loaded by uuid (get_entity_by_uuid(parent_uuid)); parents may sit in another workspace (20 live cross-workspace parent links) |
| engines-23 | 722 | EntityWorkflowEngine._get_weight | workflow_phases | read | type_id | never | _fived_complete (:429), _fived_transition (:501) and _propagate_anomaly (:658), the last on every MCP complete_phase ro… | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | signature _get_weight(self, type_id); all three callers hold the entity dict/uuid but pass entity['type_id'] |

### `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py` (11)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-24 | 155 | _promote_brainstorm | entity read by type_id | read | type_id (composed 'brainstorm:{stem}' from a path) | never | init_feature_state (:249, only when brainstorm_source is given) <- MCP init_feature_state (workflow_state_server.py:255… | unchanged — unchanged: no W1/W2 change names it; design:374 'The 39 unscoped `get_entity` reads. Th… | the type_id is composed from the brainstorm_source file name; no uuid or workspace is in scope (the function takes only db and the path); init_feature_state has workspace_uuid but does not pass it |
| engines-25 | 157 | _promote_brainstorm | entities (write by type_id) | write | type_id | never | init_feature_state (:249, only when brainstorm_source is given) <- MCP init_feature_state (workflow_state_server.py:255… | unchanged — unchanged: no W1/W2 change names it | status write by type_id; the entity dict from :155 (with uuid) is in hand |
| engines-26 | 158 | _promote_brainstorm | workflow_phases | read | type_id | never | init_feature_state (:249, only when brainstorm_source is given) <- MCP init_feature_state (workflow_state_server.py:255… | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | reads by type_id; entity uuid from :155 in hand |
| engines-27 | 160-164 | _promote_brainstorm | workflow_phases | write | type_id | never (no workspace argument) | init_feature_state (:249, only when brainstorm_source is given) <- MCP init_feature_state (workflow_state_server.py:255… | unchanged — unchanged: design:366-367 'Writers keyed by type_id alone, when called without a worksp… | writes workflow_phase='promoted', kanban_column='completed' by type_id with no workspace |
| engines-28 | 258 | init_feature_state | entity read by type_id | read | type_id | never | MCP init_feature_state (workflow_state_server.py:2554 -> _process_init_feature_state :1949); no command/skill/agent nam… | unchanged — unchanged: no W1/W2 change names it; design:374 'The 39 unscoped `get_entity` reads. Th… | existence check decides register-vs-update; with a type_id only another workspace holds it returns that entity and the else-branch runs update_entity(..., workspace_uuid=caller) (:294); with two holders it returns None and register_entity runs; the caller's workspace_uuid is a parameter of the func… |
| engines-29 | 294 | init_feature_state | entities (write by type_id) | write | type_id+workspace_uuid (workspace optional) | optional: workspace_uuid=workspace_uuid (MCP passes `_workspace_uuid or None`,… | MCP init_feature_state (workflow_state_server.py:2554 -> _process_init_feature_state :1949); no command/skill/agent nam… | unchanged — unchanged: no W1/W2 change names it | status+metadata write by type_id; the entity dict from :258 (with uuid) is in hand |
| engines-30 | 297 | init_feature_state | workflow_phases | read | type_id | never | MCP init_feature_state (workflow_state_server.py:2554 -> _process_init_feature_state :1949); no command/skill/agent nam… | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | reads by feature_type_id; neither the registered uuid (register_entity's return is discarded, :262) nor the workspace is used |
| engines-31 | 301 | init_feature_state | workflow_phases | write | type_id | never: the function has workspace_uuid but this call passes none | MCP init_feature_state (workflow_state_server.py:2554 -> _process_init_feature_state :1949); no command/skill/agent nam… | unchanged — unchanged: design:366-367 'Writers keyed by type_id alone, when called without a worksp… | kanban write by type_id with no workspace; a ValueError (no row) falls through to :305 |
| engines-32 | 305 | init_feature_state | workflow_phases | write | type_id | never today: create_workflow_phase has no workspace parameter (resolves the ent… | MCP init_feature_state (workflow_state_server.py:2554 -> _process_init_feature_state :1949); no command/skill/agent nam… | changed (W2.1) — changed by W2.1: design:271-273 'Callers pass their workspace: ... `init_feature_s… | after W2.1 the call carries (type_id, workspace); the resolved entity uuid is computed inside the DB API, not held by this caller |
| engines-33 | 566 | activate_feature | entity read by type_id | read | type_id | never | MCP activate_feature (workflow_state_server.py:2612 -> :2014); /pd:create-feature step 5 and the workflow-state skill's… | changed (W2.5) — changed by W2.5 (function restructured into one db.transaction(), design:285-289)… | status precondition read by type_id; activate_feature has workspace_uuid but not here; W2.5's seeding (step 2) creates the row 'through change 1 ... and the caller's `workspace_uuid`' |
| engines-34 | 577 | activate_feature | entities (write by type_id) | write | type_id+workspace_uuid (workspace optional) | optional: workspace_uuid=workspace_uuid (MCP passes `_workspace_uuid or None`,… | MCP activate_feature (workflow_state_server.py:2612 -> :2014); /pd:create-feature step 5 and the workflow-state skill's… | changed (W2.5) — changed by W2.5: design:289 '3. flip the status', inside one `db.transaction()` af… | status write by type_id; entity dict (uuid) from :566 in hand |

### `plugins/pd/hooks/lib/workflow_engine/feature_paths.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-10 | 85 | feature_dir_name | entity read by type_id | read | type_id | never, by design: EntityDatabase.feature_entity_id runs `SELECT DISTINCT entity… | engine._feature_dir_name (engine.py:403; from transition_phase :140, validate_prerequisites :250), engine._hydrate_from… | unchanged; related W2.2,W2.4 — unchanged; W2.2-W2.4 add callers ('The name comes from `feature_dir_… | none for the key: the answer is one entity_id for every row holding the type_id (docstring database.py:8255-8257 'a type_id held in two workspaces answers once'); it never touches workflow_phases |

### `plugins/pd/hooks/lib/workflow_engine/reconciliation.py` (10)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-40 | 306 | _check_single_feature | workflow_phases | read | type_id (composed from a directory name) | never | check_workflow_drift (reconciliation.py:752 single, :800 bulk) <- MCP reconcile_check (workflow_state_server.py:2491 ->… | unchanged — unchanged: W1.3 design:194 'Keep: `check_workflow_drift` and the read-only helpers it u… | pairs one .meta.json with one row by a type_id composed from the listed directory name (engine._iter_meta_jsons yields f'feature:{dirname}'); no workspace or uuid is in scope for this pairing |
| engines-41 | 375 | _check_single_feature | entity read by type_id | read | type_id | never | check_workflow_drift (reconciliation.py:752 single, :800 bulk) <- MCP reconcile_check (workflow_state_server.py:2491 ->… | unchanged — unchanged: W1.3 design:194 'Keep: `check_workflow_drift` and the read-only helpers it u… | depth-context read by type_id; no uuid in scope |
| engines-42 | 379 | _check_single_feature | entity read by type_id (linea… | read | type_id | never | check_workflow_drift (reconciliation.py:752 single, :800 bulk) <- MCP reconcile_check (workflow_state_server.py:2491 ->… | unchanged — unchanged: W1.3 design:194 'Keep: `check_workflow_drift` and the read-only helpers it u… | get_lineage resolves the start by type_id unscoped (database.py:8377); the entity from :375 (uuid) is in hand |
| engines-43 | 445 | _reconcile_single_feature | workflow_phases | write | type_id (workspace asserted when given) | optional: kwargs['workspace_uuid'] = workspace_uuid; Task 2 passes none (__main… | session start: session-start.sh run_reconciliation (:496-512) -> reconciliation_orchestrator/__main__.py Task 2 (:126-1… | deleted (W1.3) — deleted by W1.3: design:188-189 'In `reconciliation.py`, remove: `_reconcile_singl… | none after W1.3 (deleted) |
| engines-44 | 495-500 | _reconcile_single_feature | workflow_phases | write | type_id | never (create_workflow_phase has no parameter) | session start: session-start.sh run_reconciliation (:496-512) -> reconciliation_orchestrator/__main__.py Task 2 (:126-1… | deleted (W1.3) — deleted by W1.3: design:188-189 'In `reconciliation.py`, remove: `_reconcile_singl… | none after W1.3 (deleted) |
| engines-45 | 534-537 | _reconcile_single_feature | workflow_phases | write | type_id (workspace asserted when given) | optional: workspace_uuid=workspace_uuid (assertion only); Task 2 passes none | session start: session-start.sh run_reconciliation (:496-512) -> reconciliation_orchestrator/__main__.py Task 2 (:126-1… | deleted (W1.3) — deleted by W1.3: design:188-189 'In `reconciliation.py`, remove: `_reconcile_singl… | none after W1.3 (deleted) |
| engines-46 | 618; 666 | _recover_pending_cascades | entities (unscoped list feedi… | read | none (whole table) | never: db.list_entities() with no workspace | session start: session-start.sh run_reconciliation (:496-512) -> reconciliation_orchestrator/__main__.py Task 2 (:126-1… | changed (W1.7) — changed by W1.7: design:228 'the orchestrator's new Task 2 calls `_recover_pending… | not a workflow_phases access; it chooses which parents/objectives get the type_id writes at rollup.py:373 and reconciliation.py:690 |
| engines-47 | 690 | _recover_pending_cascades | entities (write by type_id) | write | type_id (uuid in hand) | never | session start: session-start.sh run_reconciliation (:496-512) -> reconciliation_orchestrator/__main__.py Task 2 (:126-1… | changed (W1.7) — changed by W1.7: design:233 'the rollup writes (`rollup.py:196`, `:267`, `:373`; `… | obj['uuid'] (:672) is in hand; the write uses obj['type_id'] |
| engines-48 | 765 | check_workflow_drift | workflow_phases | read | type_id | never (the function's workspace_uuid is not used on the single-feature path) | single-feature path only (feature_type_id given, no .meta.json): MCP reconcile_check / reconcile_apply with feature_typ… | unchanged — unchanged: W1.3 design:194 'Keep: `check_workflow_drift` and the read-only helpers it u… | reads by the caller's type_id argument; reports status db_only when a row exists |
| engines-49 | 821-826 | check_workflow_drift | workflow_phases | join | type_id (Python dict join against .meta.json type_ids) | optional: list_workflow_phases(workspace_uuid=workspace_uuid); reconcile_check… | check_workflow_drift (reconciliation.py:752 single, :800 bulk) <- MCP reconcile_check (workflow_state_server.py:2491 ->… | unchanged; related W1.6 — unchanged body; W1.6 changes its reconcile_status caller: design:223 'Sco… | `db_rows_by_id = {row["type_id"]: row ...}` assumes at most one row per type_id, and `db_only_ids = db_rows_by_id.keys() - meta_type_ids` is a type_id set difference; rows keyed per entity with no workspace filter would collide in this dict |

### `plugins/pd/hooks/lib/workflow_engine/rollup.py` (4)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-50 | 49 (called at 99) | _get_workflow_phase / compute_progress | workflow_phases | read | type_id (child uuid in hand) | never | compute_progress <- rollup_parent (:371), EntityWorkflowEngine._run_cascade (entity_engine.py:587), reconciliation._rec… | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | children come from get_children_by_uuid(entity_uuid) (:74) and carry 'uuid'; the lookup passes child['type_id']; children can be in another workspace (20 live cross-workspace parent links) |
| engines-51 | 196 | compute_okr_score | entities (write by type_id) | write | type_id (uuid in hand) | never | compute_objective_score (:257) <- reconciliation._recover_pending_cascades (:677, session-start Task 2); 0 live objecti… | changed (W1.7) — changed by W1.7: design:233 'the rollup writes (`rollup.py:196`, `:267`, `:373`; `… | kr_uuid is the function parameter; the write uses entity['type_id'] |
| engines-52 | 267-270 | compute_objective_score | entities (write by type_id) | write | type_id (uuid in hand) | never | reconciliation._recover_pending_cascades (:677, session-start Task 2); 0 live objectives | changed (W1.7) — changed by W1.7: design:233 'the rollup writes (`rollup.py:196`, `:267`, `:373`; `… | objective_uuid is the function parameter; the write uses entity['type_id'] |
| engines-53 | 373-376 | rollup_parent | entities (write by type_id) | write | type_id (parent uuid in hand) | never | rollup_parent <- EntityWorkflowEngine._run_cascade (entity_engine.py:576, after every MCP complete_phase routed through… | changed (W1.7) — changed by W1.7: design:233 'the rollup writes (`rollup.py:196`, `:267`, `:373`; `… | parent_uuid is the loop variable (parent loaded by uuid, :367); the write uses parent['type_id']; live: 41 children point at a parent whose type_id is project:P001 (held by 3 workspaces), so the write raises 'Ambiguous' (I2 probe2d) |

### `plugins/pd/hooks/lib/workflow_engine/router.py` (7)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-54 | 358 | init_entity_workflow | entity read by type_id | read | type_id (a uuid is also accepted) | never | MCP init_entity_workflow (workflow_state_server.py:2627 -> :2037); /pd:add-to-backlog step 4 (commands/add-to-backlog.m… | unchanged — unchanged: no W1/W2 change names it; design:374 'The 39 unscoped `get_entity` reads. Th… | validation read by the type_id argument; the docstring says the kind checks run 'including one passed by uuid', and no ':' check guards the later row lookups (unlike transition_entity_phase :434) |
| engines-55 | 382 | init_entity_workflow | workflow_phases | read | type_id (the argument string) | never | MCP init_entity_workflow (workflow_state_server.py:2627 -> :2037); /pd:add-to-backlog step 4 (commands/add-to-backlog.m… | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | idempotency check by the argument string; the entity dict from :358 (with uuid) is in hand |
| engines-56 | 393-396 | init_entity_workflow | workflow_phases | upsert | type_id (+ workspace for the entity existence check) | optional: workspace_uuid=workspace_uuid (MCP passes `_workspace_uuid or None`,… | MCP init_entity_workflow (workflow_state_server.py:2627 -> :2037); /pd:add-to-backlog step 4 (commands/add-to-backlog.m… | unchanged; related W2.1; own lines unchanged; behaviour changes through a callee (W2.1) — unchanged… | insert and update are by type_id; the entity dict (uuid) from :358 is in hand but not passed |
| engines-57 | 437 | transition_entity_phase | entity read by type_id | read | type_id (':' required at :434) | never | MCP transition_entity_phase (workflow_state_server.py:2647 -> :2050); no command/skill/agent names the tool | unchanged — unchanged: no W1/W2 change names it; design:374 'The 39 unscoped `get_entity` reads. Th… | validation read by type_id; transition_entity_phase takes workspace_uuid but not here |
| engines-58 | 452 | transition_entity_phase | workflow_phases | read | type_id | never | MCP transition_entity_phase (workflow_state_server.py:2647 -> :2050); no command/skill/agent names the tool | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | current-phase read by type_id; entity (uuid) from :437 in hand |
| engines-59 | 480 | transition_entity_phase | entities (write by type_id) | write | type_id+workspace_uuid (workspace optional) | optional: workspace_uuid=workspace_uuid (MCP `_workspace_uuid or None`, :2052) | MCP transition_entity_phase (workflow_state_server.py:2647 -> :2050); no command/skill/agent names the tool | unchanged — unchanged: no W1/W2 change names it | status write by type_id; entity uuid from :437 in hand |
| engines-60 | 492 | transition_entity_phase | workflow_phases | write | type_id (workspace asserted when given) | optional: 'workspace_uuid is unconditional; None is a no-op in update_workflow_… | MCP transition_entity_phase (workflow_state_server.py:2647 -> :2050); no command/skill/agent names the tool | unchanged — unchanged: design:366-367 'Writers keyed by type_id alone, when called without a worksp… | writes by type_id; entity uuid from :437 in hand |

### `plugins/pd/hooks/lib/workflow_engine/secretary_intelligence.py` (2)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-61 | 501 | get_parent_context | entity read by type_id | read | type_id | never | CLI `python -m workflow_engine.secretary_intelligence parent-context` (:683, :728); no command, skill, agent or hook in… | unchanged — unchanged: no W1/W2 change names it; design:374 'The 39 unscoped `get_entity` reads. Th… | reads the parent by the caller-supplied type_id; no workspace in the CLI or function |
| engines-62 | 507 | get_parent_context | workflow_phases | read | type_id | never | CLI `python -m workflow_engine.secretary_intelligence parent-context` (:683, :728); no command, skill, agent or hook in… | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | reads by parent_type_id; the entity dict (uuid) from :501 is in hand |

### `plugins/pd/hooks/lib/workflow_engine/task_promotion.py` (5)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-35 | 86 | query_ready_tasks | workflow_phases | read | type_id (parent_type_id) | never | MCP query_ready_tasks (workflow_state_server.py:2732 -> :2764); no command/skill/agent names the tool; 0 live task enti… | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | reads the PARENT's row by task['parent_type_id']; the task dict from list_entities carries 'parent_uuid' (used by the same module at :348), so the parent's uuid is available |
| engines-36 | 309 | promote_task | entity read by type_id | read | type_id or uuid (feature_ref) | never | MCP promote_task (workflow_state_server.py:2702 -> :2716); no command/skill/agent names the tool; 0 live task entities | unchanged — unchanged: W2.4 changes only how the directory is named (`task_promotion.py:317-322`, d… | resolves the feature by feature_ref with no workspace although promote_task takes workspace_uuid; yields feature_uuid (:313) |
| engines-37 | 359 | promote_task | workflow_phases | read | type_id | never | MCP promote_task (workflow_state_server.py:2702 -> :2716); no command/skill/agent names the tool; 0 live task entities | unchanged — unchanged: no W1/W2 change names it; the key is Phase R's (design:543 'Re-key `workflow… | reads the feature's mode by feature_type_id; feature_uuid (:313) is in hand |
| engines-38 | 383 | promote_task | entity read by type_id | read | type_id | never | MCP promote_task (workflow_state_server.py:2702 -> :2716); no command/skill/agent names the tool; 0 live task entities | unchanged — unchanged: no W1/W2 change names it; design:374 'The 39 unscoped `get_entity` reads. Th… | re-reads the same feature by type_id to get parent_uuid, which :313 already holds as feature_uuid |
| engines-39 | 403 | promote_task | workflow_phases | write | type_id | never today (no parameter); the task was registered in task_workspace_uuid (:36… | MCP promote_task (workflow_state_server.py:2702 -> :2716); no command/skill/agent names the tool; 0 live task entities | changed (W2.1) — changed by W2.1: design:274 '`promote_task` (`task_promotion.py:403`)' among 'Call… | the new task's uuid (task_uuid, :387) and workspace (task_workspace_uuid) are both in hand at this call |

### `plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-90 | 126-142 | main (Task 2) | workflow_phases (via apply_wo… | write | none passed (no workspace_uuid argument) | never: apply_workflow_reconciliation(engine=engine, db=entity_db, artifacts_roo… | session start: session-start.sh run_reconciliation (:496-512, `python -m reconciliation_orchestrator`) | deleted (W1.3) — deleted by W1.3: design:184 'the orchestrator's Task 2 (`reconciliation_orchestrat… | none after W1.3 (deleted) |

### `plugins/pd/hooks/lib/reconciliation_orchestrator/dependency_freshness.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-89 | 25 | cleanup_stale_dependencies | entities (unscoped list feedi… | read | none (whole table) | never: db.list_entities(); the function takes no workspace | session start: reconciliation_orchestrator/__main__.py Task 3 (:144-147) | changed (W1.8) — changed by W1.8: design:235 '`dependency_freshness.cleanup_stale_dependencies` tak… | not a workflow_phases access; feeds uuids to _evaluate_and_flip, whose writes are the dependencies.py:184-185 rows |

### `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py` (5)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-84 | 58 | _sync_meta_json_entities | entities (archive flag by typ… | write | type_id (+ workspace when resolved) | optional: workspace_uuid is None when the orchestrator could not resolve one (e… | session start: session-start.sh run_reconciliation -> reconciliation_orchestrator/__main__.py Task 1 (:116-122) -> enti… | deleted (W1.1) — deleted by W1.1: design:170 'Remove: `entity_status._sync_meta_json_entities` (`en… | none after W1.1 (deleted) |
| engines-85 | 77 | _sync_meta_json_entities | entity read by type_id | read | type_id (composed from a folder name) | never | session start: session-start.sh run_reconciliation -> reconciliation_orchestrator/__main__.py Task 1 (:116-122) -> enti… | deleted (W1.1) — deleted by W1.1: design:170 'Remove: `entity_status._sync_meta_json_entities` (`en… | none after W1.1 (deleted) |
| engines-86 | 83-88 | _sync_meta_json_entities | entities (write by type_id) | write | type_id+workspace_uuid, else project_id(legacy) | always (workspace_uuid, or the legacy project_id when none resolved) | session start: session-start.sh run_reconciliation -> reconciliation_orchestrator/__main__.py Task 1 (:116-122) -> enti… | deleted (W1.1) — deleted by W1.1: design:170 'Remove: `entity_status._sync_meta_json_entities` (`en… | none after W1.1 (deleted) |
| engines-87 | 190 | _sync_brainstorm_entities (Part 1) | entity read by type_id | read | type_id (composed 'brainstorm:{stem}') | never | session start: session-start.sh run_reconciliation -> reconciliation_orchestrator/__main__.py Task 1 (:116-122) -> enti… | unchanged — unchanged: W1.1 design:175 'Keep: Part 1 of the brainstorm helper (`:180-209`). It regi… | a stem registered only in another workspace is skipped, never registered here; I1-verify note 7: scoping it naively would start minting shared brainstorm ids in every worktree or clone workspace |
| engines-88 | 230 | _sync_brainstorm_entities (Part 2) | entities (archive flag by typ… | write | type_id (+ workspace when resolved) | optional: None when unresolved; set_archived then archives the type_id in every… | session start: session-start.sh run_reconciliation -> reconciliation_orchestrator/__main__.py Task 1 (:116-122) -> enti… | deleted (W1.1) — deleted by W1.1: design:173 'Part 2 of `_sync_brainstorm_entities`, which archives… | none after W1.1 (deleted) |

### `plugins/pd/hooks/lib/doctor/check_status_write_path.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-94 | 28-44; 222-237 | check_status_write_path (_PERMITTED_ENCLOSING_DEFS) | workflow_phases (static sourc… | read | n/a (greps source text 'UPDATE workflow_phases') | n/a | doctor at every session start (session-start.sh:545-565 run_doctor_autofix, `python -m doctor ... --fix`) and /pd:docto… | unchanged — unchanged: no W1/W2 change names the doctor | any function containing 'UPDATE workflow_phases' in hooks/lib or mcp is reported unless its name is in _PERMITTED_ENCLOSING_DEFS (append_phase_event, upsert_workflow_phase, update_workflow_phase, create_workflow_phase, update_entity, _v2_migration_5_explicit_archived_flag, check_status_write_path)… |

### `plugins/pd/hooks/lib/doctor/checks.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-91 | 367-389 | check_referential_integrity (workflow_phases FK part) | workflow_phases | read | type_id (set membership against every workspace's entity type_ids) | n/a: whole-table raw SQL `SELECT type_id FROM workflow_phases` on the doctor's… | doctor at every session start (session-start.sh:545-565 run_doctor_autofix, `python -m doctor ... --fix`) and /pd:docto… | unchanged — unchanged: no W1/W2 change names the doctor | orphan test is `wp_type_id not in type_ids_in_use` where type_ids_in_use spans all workspaces; a row whose workspace_uuid/uuid match no entity is invisible to it (I1 report L153); its Issue carries entity=<type_id> and fix_hint 'Remove orphaned workflow_phases row' |

### `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py` (2)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| engines-93 | 51 | _fix_self_referential_parent | entities (write by type_id) | write | type_id (Issue.entity) | never: raw `UPDATE entities SET parent_uuid = NULL WHERE type_id = ?` hits ever… | doctor --fix (session start and /pd:doctor --fix) when check_referential_integrity reports 'is its own parent' (checks.… | unchanged — unchanged: no W1/W2 change names the doctor | not a workflow_phases access; the check has the offending uuid (uuid_val) but the Issue carries only the type_id |
| engines-92 | 92-95 | _fix_remove_orphan_workflow | workflow_phases | delete | type_id (Issue.entity, else parsed from the message) | never: raw `DELETE FROM workflow_phases WHERE type_id = ?` | fixer.apply_fixes via the dispatch entry ('Remove orphaned workflow_phases', fixer.py:28) at session start (doctor --fi… | unchanged — unchanged: no W1/W2 change names the doctor | deletes by type_id; the issue carries only the type_id; a per-entity table would need the row's own key in the Issue |

### `plugins/pd/mcp/entity_server.py` (17)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MCPE-3 | 258-273 (helper 175-196) | lifespan (_backfill_project_ids) | entity read by type_id | write | none (claims '__unknown__' entities by artifact_path prefix) | always (claims into the server's workspace) | entity-registry MCP server start | unchanged — unchanged — deferred: "`db.backfill_project_ids` claims `__unknown__` rows by `artifact… | db.backfill_project_ids UPDATEs entities.workspace_uuid (database.py:8928) with no matching workflow_phases update, unlike update_entity's re-attribution cascade (database.py:8768-8777); a workflow_phases copy of workspace_uuid would drift here, a uuid key would not. |
| MCPE-2 | 275-279 | lifespan (run_backfill call) | workflow_phases | write | type_id (+workspace_uuid) | always (run_backfill resolves _workspace(db, project_id) and passes workspace_u… | entity-registry MCP server start, guarded by metadata backfill_complete/_BACKFILL_VERSION='4' | unchanged — unchanged — deferred: "Per-workspace `.meta.json` import, which also covers `run_backfi… | run_backfill's version-gated fix-up updates NULL workflow_phase rows by type_id with the workspace asserted (backfill.py:210-216); its scanners upsert entities (upsert_entity emits phase_events, database.py:7928). A per-entity key needs the uuid of the row it already lists. |
| MCPE-1 | 281-294 | lifespan (backfill_workflow_phases call) | workflow_phases | upsert | type_id | never (backfill_workflow_phases iterates db.list_entities() of every workspace… | entity-registry MCP server start (every start, outside the backfill_complete guard) | changed (W2.6) — changed by W2.6: "The startup backfill reads no files, and stays in its workspace… | Call passes project_id=_project_id only; the backfill writes update_workflow_phase/upsert_workflow_phase by type_id (backfill.py:317, :326, :395). After W2.6 it passes a workspace; a per-entity key needs the entity uuid it iterates (list_entities rows carry uuid) passed to the row writer. |
| MCPE-4 | 316-360 | _resolve_ref_param | entity read by type_id | resolve | type_id (explicit type_id returned unchanged); ref -> db.resolve_ref(ref, proje… | optional: a ref is resolved in the server's legacy project (project_id=_effecti… | entity tools set_parent, get_entity, get_lineage, update_entity, delete_entity, add_entity_tag, get_entity_tags, create… | unchanged; related W3.4 — unchanged in Phase 1 — W3.4 rewrites it in Phase 2 ("`_resolve_ref_param`… | Returns entity['type_id'] after a scoped ref resolution, so the handlers re-resolve that text unscoped (MCPE-8, -9, -12, -14, -15). A per-entity key needs it to return the uuid. |
| MCPE-5 | 541-684 | register_entity | phase_events | write | type_id (entity_type + seq/slug or display_id) + workspace_uuid | always (workspace_uuid argument, else _workspace_uuid, else legacy _project_id… | MCP tool register_entity; markdown: add-to-backlog.md:13, create-feature.md:20, create-project.md:19, decomposing/SKILL… | unchanged; related W4.1 — unchanged in Phase 1 (W4.1 removes the `__unknown__` fallback in Phase 2:… | db.register_entity appends phase_events 'entity_created' keyed by type_id/project_id (database.py:7765-7775). server_helpers._process_register_entity also reads get_entity(type_id) and get_entity(parent_type_id) unscoped and calls db.set_parent(type_id, parent_type_id) on a duplicate (server_helper… |
| MCPE-6 | 812-970 (event 957-968) | issue_spawn | phase_events | write | parent by uuid; event keyed by parent's type_id + the caller's legacy project_id | optional (event workspace_uuid from the parent row; project_id from the caller:… | MCP tool issue_spawn(parent_uuid, ...) (no markdown caller found) | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | The parent is addressed by uuid, but the spawned_child event is written under parent_row['type_id'] with the caller's project_id, which differs from the parent's when the parent sits in another workspace (feature 129 allows it). An entity key on phase_events would carry the uuid already in hand. |
| MCPE-7 | 973-1009 (server_helpers.py:499-520) | set_parent / _process_set_parent | entity read by type_id | resolve | type_id (child: type_id\|ref; parent: parent_type_id\|parent_ref) | optional (child ref resolved in the server's legacy project; parent ref and bot… | MCP tool set_parent; markdown: create-project.md:19 (brainstorm under its backlog entity) | unchanged; related W3.4 — unchanged in Phase 1 — W3.4 (Phase 2): "`set_parent`, which calls `db.set… | db.set_parent(type_id, parent_type_id) with no workspace (server_helpers.py:517) -> _resolve_identifier unscoped for both (database.py:7981-7990). No workflow_phases/phase_events write. |
| MCPE-8 | 1012-1042 | get_entity | entity read by type_id | read | type_id | never for the final read (a ref is resolved in the server's project first, then… | MCP tool get_entity; markdown: show-lineage.md:12 (ref="feature:{id}"), show-status.md:12 | unchanged — unchanged — deferred read (W3: "The 39 unscoped `get_entity` reads. They are scoped onl… | _db.get_entity(resolved_type_id) answers None for a shared type_id even when the ref resolved in scope. The reply drops uuid, entity_id and parent_uuid, so no markdown caller can obtain a uuid from this tool (export_entities is the MCP read that returns uuid). |
| MCPE-9 | 1045-1079 (server_helpers.py:458-497) | get_lineage / _process_get_lineage | entity read by type_id | read | type_id | never (db.get_lineage called with no project_id/workspace) | MCP tool get_lineage; markdown: show-lineage.md:13 | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | db.get_lineage(type_id) returns [] when _resolve_identifier is ambiguous (database.py:8376-8383), so show-lineage answers "Entity not found" for a shared type_id. Walks by uuid after resolution; only the entry needs the entity key. |
| MCPE-10 | 1082-1143 (handler 369-386) | update_entity / _process_update_entity | phase_events | write | type_id\|ref + legacy project_id (server's, or the caller's project_id argument) | optional (scoped by _effective_project_id(project_id); unscoped when the server… | MCP tool update_entity; markdown: abandon-feature.md:18, cleanup-brainstorms.md:25 | changed (W1.2) — changed by W1.2: "the `update_entity` MCP tool gains `archived: bool \| None = None… | db.update_entity(type_id, project_id=) resolves with _resolve_identifier(type_id, project_id=) (database.py:8557); a status change appends a phase_events row keyed by type_id (database.py:8699); new_project_id re-attribution cascades "UPDATE workflow_phases SET workspace_uuid = ?, updated_at = ? WH… |
| synth-2 | 1147-1180 (project_id at 1174); helper serve… | export_lineage_markdown MCP tool -> _process_export_lineage… | entity read by type_id | resolve | type_id (or uuid) + legacy project_id when given | optional: `resolved_project_id = None if project_id == "*" else _effective_proj… | MCP export_lineage_markdown (entity server); /pd:show-lineage is recorded as MD-17 | unchanged — unchanged. No W1/W2 change names it; design:544 leaves unscoped type_id reads to Phase… | Resolves the root with _resolve_identifier(type_id, project_id=..., workspace_uuid=...) (database.py:9391-9397, part of schema-58); an unscoped call raises "Ambiguous" for a shared type_id. No workflow_phases or phase_events access. |
| MCPE-11 | 1226-1250 (handler 389-395) | delete_entity / _process_delete_entity | phase_events | write | type_id\|ref + legacy project_id | optional (project_id=_effective_project_id()) | MCP tool delete_entity (no markdown caller found) | unchanged; related W1.7; own lines unchanged; behaviour changes through a callee (W1.7) — unchanged… | db.delete_entity soft-deletes (UPDATE entities SET is_deleted = 1 ... WHERE uuid = ?, database.py:9084-9087) and deliberately keeps the workflow_phases row (comment 9071-9076); it emits a v2 'entity_deleted' event by uuid (9091-9097); then _evaluate_and_flip updates dependents by entity['type_id']… |
| MCPE-12 | 1253-1312 (handler 398-405) | add_entity_tag / get_entity_tags | entity read by type_id | read | type_id | never for the final read | MCP tools add_entity_tag, get_entity_tags (no markdown caller found) | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | get_entity(resolved_type_id) unscoped (400, 1304) then tags by entity['uuid']: a shared type_id answers not-found. Needs the uuid from resolution. |
| MCPE-16 | 1315-1350, 1447-1491 (scope helper 165-172) | add_dependency / add_okr_alignment / get_okr_alignments | entity read by type_id | resolve | ref -> uuid (db.resolve_ref(ref, project_id=_effective_project_id())) | optional: scoped to the server's legacy project; _effective_project_id returns… | MCP tools add_dependency, add_okr_alignment, get_okr_alignments (no markdown caller found) | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Contrast pattern: these tools resolve a ref once, in scope, and then write by uuid (entity_dependencies, entity_okr_alignment). No workflow_phases/phase_events access. resolve_ref's scoped exact match is unique per (workspace_uuid, type_id). |
| MCPE-13 | 1353-1386 (handler 424-437) | remove_dependency / _process_remove_dependency | phase_events | write | entity_ref/blocked_by_ref -> uuid (resolve_ref scoped by legacy project); flip… | optional (refs scoped; the flip's writes unscoped) | MCP tool remove_dependency (no markdown caller found) | unchanged; related W1.7; own lines unchanged; behaviour changes through a callee (W1.7) — unchanged… | DependencyManager.remove_dependency -> _evaluate_and_flip(db, affected) (dependencies.py:132) -> db.update_entity(entity["type_id"], status="ready") with no workspace and append_phase_event(type_id=entity["type_id"], project_id=entity.get("project_id") or "__unknown__", event_type="cascade_ready")… |
| MCPE-14 | 1499-1541 (handler 453-509) | create_key_result / _process_create_key_result | entity read by type_id | read | parent_ref -> type_id (scoped ref) -> get_entity(parent_type_id) unscoped | optional (ref scoped; parent re-read unscoped; registration workspace from the… | MCP tool create_key_result (no markdown caller found) | unchanged; related W3.4 — unchanged in Phase 1 — W3.4 (Phase 2) lists `create_key_result` | Parent read by type_id (469) answers None for a shared type_id ("Parent entity not found"); register_entity then appends phase_events 'entity_created' for the new key_result. Needs the parent uuid from resolution. |
| MCPE-15 | 1544-1572 (handler 511-517) | update_kr_score / _process_update_kr_score | entity read by type_id | write | kr_ref -> type_id (scoped ref) -> update_entity(type_id) with no scope | never for the write | MCP tool update_kr_score (no markdown caller found) | unchanged; related W3.4 — unchanged in Phase 1 — W3.4 (Phase 2) lists `update_kr_score` | db.update_entity(resolved_type_id, metadata=) with no project_id/workspace: global-unique or Ambiguous refusal. Metadata only, so no phase event. Needs the uuid. |

### `plugins/pd/mcp/workflow_state_server.py` (45)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MCPW-44 | 217-280 (engine construction 257-261) | lifespan | workflow_phases | resolve | none (engine objects hold no workspace) | n/a | workflow-engine MCP server start | unchanged; related W4.1 — unchanged by Phase 1 (W4.1 adds _require_workspace() in Phase 2: "Each se… | WorkflowStateEngine(_db, _artifacts_root) and EntityWorkflowEngine(_db, _artifacts_root, ...) take no workspace; _workspace_uuid is a module global passed per call as `_workspace_uuid or None`. A per-entity key needs either the engine or each engine method to receive the entity/workspace. |
| MCPW-21 | 412-596 (reads at 436, 507; dir naming 451-4… | _project_meta_json | entity read by type_id | read | type_id | never | MCPW-11's five callers (transition_phase, complete_phase, init_feature_state, activate_feature, reproject_meta_json) | changed (W2.2) — changed by W2.2 (directory naming at 451-454): "**Features:** `{artifacts_root}/fe… | get_entity(type_id) (436) is None for a shared type_id, so the projection returns "entity not found" and writes nothing; engine.get_state(type_id) (507) reads workflow_phases by type_id for last_completed_phase/current_phase. W2.2's feature_dir_name reads entities.entity_id by type_id with no works… |
| MCPW-20 | 838-862 | _resolve_project_id | phase_events | resolve | project_id(legacy) | n/a | every workflow-server append_phase_event: transition_phase 1200, complete_phase 1499, record_mini_spec 2292, record_bac… | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Supplies phase_events.project_id from entity['project_id'] (workspaces.project_id_legacy), '__unknown__' when missing; callers pass '__unknown__' when their unscoped read was None. phase_events has no workspace/entity column (live columns: id,type_id,project_id,phase,event_type,...,metadata), so th… |
| MCPW-7 | 1015-1052 (fed by the unscoped get_entity at… | _transitioned_entity_row | entity read by type_id | resolve | type_id+workspace_uuid when _workspace_uuid is set (db.resolve_entity_uuid), el… | optional (scoped only when the server resolved a workspace) | MCP tool transition_phase (phase_timing merge, kind, started_at) | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Already re-resolves in the server's workspace; returns a row dict but callers keep using feature_type_id for the writes that follow. A per-entity key would let the writes use the uuid this helper already finds. |
| MCPW-5 | 1124 | _process_transition_phase | entity read by type_id | read | type_id | never | MCP tool transition_phase | unchanged — unchanged — not named by W1/W2; the design defers these reads ("The 39 unscoped `get_en… | db.get_entity(type_id) answers None when two workspaces hold the type_id (it swallows _resolve_identifier's Ambiguous error, database.py:8226-8229). A per-entity key would need this lookup to be the single resolution of the target entity (uuid) that the rest of the handler reuses. |
| MCPW-6 | 1129-1152, 1219-1223 | _process_transition_phase -> engine.transition_phase / enti… | workflow_phases | write | type_id | optional: update_workflow_phase(type_id, workflow_phase=, workspace_uuid=) asse… | MCP tool transition_phase | unchanged; related W1.5 — unchanged in these lines; W1.5 removes the hydration inside the get_state… | engine.py:156-160 UPDATE ... WHERE type_id = ? (database.py:10164 region). The workspace check compares the row's workspace to the server's, so a namesake's row in another workspace makes the transition raise rather than write the caller's own (missing) row. A per-entity key needs the engine write… |
| MCPW-8 | 1182-1185 | _process_transition_phase | entity read by type_id | write | type_id (+workspace_uuid when set) | optional (_workspace_uuid or None) | MCP tool transition_phase | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | update_entity(type_id, metadata=, workspace_uuid=) resolves via _resolve_identifier (database.py:8557); scoped when workspace given, else global-unique or Ambiguous error. A per-entity key would pass the uuid. |
| MCPW-9 | 1190-1192 | _process_transition_phase | workflow_phases | write | type_id | never (no workspace argument passed) | MCP tool transition_phase (feature kind only) | unchanged — unchanged — the design names the writer, not this call, and defers it: "Writers keyed b… | update_workflow_phase(type_id, kanban_column=...) with no workspace_uuid: UPDATE workflow_phases ... WHERE type_id = ? (database.py:10164). A per-entity key needs the entity uuid here. |
| MCPW-10 | 1200-1217 | _process_transition_phase | phase_events | write | type_id + legacy project_id; v2 events by entity uuid resolved from (workspace_… | optional (workspace_uuid=_workspace_uuid or None; project_id comes from the uns… | MCP tool transition_phase (event 'started' plus one 'skipped' per skipped phase) | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | append_phase_event INSERTs phase_events(type_id, project_id, ...) (database.py:9735-9745), and for 'started' also runs step 5 "UPDATE workflow_phases SET workflow_phase = ?, updated_at = ? WHERE type_id = ?" (database.py:9779-9784). A per-entity key needs an entity column on phase_events (or the uu… |
| MCPW-11 | 1236, 1617, 1966, 2022, 1694 | _process_transition_phase / _process_complete_phase / _proc… | entity read by type_id | read | type_id | never | MCP tools transition_phase, complete_phase, init_feature_state, activate_feature, reproject_meta_json (post-commit proj… | unchanged; related W2.2; own lines unchanged; behaviour changes through a callee (W2.2) — unchanged… | Call sites pass only the type_id; see MCPW-21 for the reads inside. |
| MCPW-22 | 1279-1315 (reads 1284, 1293, 1301) | _check_artifact_completeness | workflow_phases | read | type_id | never | MCP tool complete_phase when phase == 'finish' (1639-1644) | changed (W2.3) — changed by W2.3: "`_check_artifact_completeness` names the directory the same way… | get_entity(type_id) (1284), get_workflow_phase(type_id) for mode (1293), query_phase_events(type_id=) with no project_id for mini_spec (1301): a namesake's mini_spec event in another workspace would switch the expected artifacts to retro.md only. A per-entity key needs the uuid for all three. |
| MCPW-13 | 1381-1405 | _process_complete_phase (closes resolution) | entity read by type_id | resolve | type_id+workspace_uuid (server workspace, then the unknown workspace as legacy… | always (scoped to _workspace_uuid or _UNKNOWN_WORKSPACE_UUID) | MCP tool complete_phase with closes=[...] | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Scoped resolution of the caller entity to from_uuid already exists here; the uuid is used for entity_relations only, not for the workflow_phases/phase_events writes of the same call. |
| MCPW-14 | 1413-1437 | _process_complete_phase -> engine.complete_phase / entity_e… | workflow_phases | write | type_id | optional: update_workflow_phase(..., workspace_uuid=) asserts stored workspace… | MCP tool complete_phase | unchanged; related W1.5 — unchanged in these lines; W1.5 removes hydration in the get_state they ca… | engine.complete_phase -> get_state(type_id) (engine.py:174), update_workflow_phase(type_id, workflow_phase=, last_completed_phase=, workspace_uuid=) (engine.py:214-219), update_entity(type_id, status="completed", workspace_uuid=) (engine.py:222). A per-entity key needs the uuid threaded into engine… |
| MCPW-15 | 1441-1448, 1624 | _process_complete_phase | entity read by type_id | read | type_id | never | MCP tool complete_phase | unchanged — unchanged — deferred read (W3: "The 39 unscoped `get_entity` reads. They are scoped onl… | Unscoped get_entity; None for a shared type_id raises feature_not_found inside the transaction. A per-entity key needs this read to use the resolved entity. |
| MCPW-16 | 1470-1473 | _process_complete_phase | entity read by type_id | write | type_id (+workspace_uuid when set) | optional | MCP tool complete_phase | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | update_entity(type_id, metadata=, workspace_uuid=) — same as MCPW-8. |
| MCPW-17 | 1479-1481 | _process_complete_phase | workflow_phases | write | type_id | never | MCP tool complete_phase (feature kind only) | unchanged — unchanged — deferred writer (W3: "`update_workflow_phase` (`:10164`)" under "Named, and… | update_workflow_phase(type_id, kanban_column=) with no workspace. Needs the entity uuid. |
| MCPW-18 | 1497-1508 | _process_complete_phase | phase_events | write | type_id + legacy project_id (from the entity read at 1441); v2 events by (works… | optional (_workspace_uuid or None) | MCP tool complete_phase (event 'completed') | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Same as MCPW-10: phase_events row keyed by type_id/project_id; step 5 UPDATE workflow_phases ... WHERE type_id = ? for 'completed'. Reviewer notes and iterations that retrospect/analytics read live on this row. |
| MCPW-19 | 1576-1590 | _process_complete_phase (closes targets) | entity read by type_id | write | uuid | always (caller_workspace_uuid) | MCP tool complete_phase with closes=[...] | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Already writes by uuid (update_entity(to_uuid, ...), insert_entity_relation(from_uuid, to_uuid)); the status change inside update_entity still appends a phase_events row keyed by the target's type_id (database.py:8699 region). |
| MCPW-30 | 1724-1815 (reads 1752, 1755, 1768) | _detect_phase_events_drift | phase_events | read | type_id | never (list_entities(entity_type="feature") with no workspace; bulk query by ty… | MCP tools reconcile_check (1844) and reconcile_apply (1879) | unchanged; related W1.4 — unchanged for reconcile_check; its reconcile_apply caller is deleted by W… | Lists active features of every workspace and compares entities.metadata.phase_timing with phase_events rows matched on (type_id, phase, event_type): a namesake's events can satisfy or pollute another workspace's check. Needs phase_events rows attributable to one entity. |
| MCPW-1 | 2126-2161 | _resolve_ref_to_feature_type_id | entity read by type_id | resolve | type_id (an explicit feature_type_id is returned with no lookup); ref -> db.res… | never | every workflow tool with a feature_type_id/type_id/ref parameter: get_phase, transition_phase, complete_phase, record_m… | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | It resolves a uuid and then throws it away, returning only entity['type_id']; every downstream call is keyed by that text. A per-entity key needs this helper to return the entity uuid (or type_id plus the resolved workspace) and the _process_* handlers to accept it. db.resolve_ref is called with no… |
| MCPW-2 | 2177-2189 (handler 1004-1012) | get_phase / _process_get_phase | workflow_phases | read | type_id | never | MCP tool get_phase(feature_type_id\|ref); markdown: show-status.md:11, wrap-up.md:12, retrospect.md:10, secretary.md:15,… | unchanged; related W1.5; own lines unchanged; behaviour changes through a callee (W1.5) — unchanged… | engine.get_state(feature_type_id) -> db.get_workflow_phase(type_id) (engine.py:102). get_state's signature takes only the type_id and the engine is built with no workspace (WorkflowStateEngine(_db, _artifacts_root), 257); a per-entity key needs the entity uuid (or type_id plus workspace) carried fr… |
| MCPW-4 | 2192-2222 (handler 1058-1276) | transition_phase / _process_transition_phase | workflow_phases | write | type_id (feature_type_id\|ref reduced to type_id by MCPW-1) | optional: engine write and update_entity/append_phase_event pass workspace_uuid… | MCP tool transition_phase; markdown: workflow-transitions/SKILL.md:16 (phase entry for specify/design/create-plan/imple… | unchanged; related W1.5 — unchanged in its own lines; its engine read loses hydration (W1.5: "What… | Tool-level summary of sites MCPW-5..MCPW-11: every write and read is keyed by the type_id text; the entity uuid is available only on the entity_engine branch (entity['uuid'] at 1130) and is converted back to a type_id there (entity_engine.py:233-241, delegated at :281). A per-entity key needs the h… |
| MCPW-12 | 2225-2261 (handler 1322-1653) | complete_phase / _process_complete_phase | workflow_phases | write | type_id (feature_type_id\|ref reduced by MCPW-1); closes=[uuid,...] by uuid | optional: engine/update_entity/append pass _workspace_uuid or None; update_work… | MCP tool complete_phase; markdown: workflow-transitions/SKILL.md:33 (phase exit for every phase command; finish-feature… | unchanged; related W1.5,W2.2,W2.3 — unchanged in its own lines; reached engine.get_state loses hydr… | Tool-level summary of MCPW-13..MCPW-19. Same shape as transition_phase: the uuid is known only inside entity_engine and is converted back to type_id (entity_engine.py:155-164, delegated at :170). |
| MCPW-23 | 2264-2301 | record_mini_spec | phase_events | write | type_id + legacy project_id | optional (_workspace_uuid or None); the entity read at 2291 is unscoped | MCP tool record_mini_spec(feature_type_id\|ref); markdown: create-feature.md:22 | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | get_entity(resolved) unscoped for project_id ('__unknown__' when None), then append_phase_event(event_type='mini_spec') keyed by type_id/project_id; no step-5 projection for mini_spec. Needs an entity key on the event. |
| MCPW-24 | 2304-2339 | get_mini_spec | phase_events | read | type_id | never (no project_id or workspace filter) | MCP tool get_mini_spec; markdown: implement.md:12, :15, :16 (express detection: "`get_mini_spec` resolves") | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | query_phase_events(type_id=resolved) with no project_id returns every workspace's events for the type_id and picks the highest id; a namesake's mini_spec in another workspace would make this feature look express. Needs an entity key on phase_events. |
| MCPW-3 | 2342-2358 (handler 1656-1666) | validate_prerequisites / _process_validate_prerequisites | workflow_phases | read | type_id | never | MCP tool validate_prerequisites(feature_type_id\|ref); listed as a read tool in workflow-state/SKILL.md:10; no markdown… | unchanged; related W1.5; own lines unchanged; behaviour changes through a callee (W1.5) — unchanged… | engine.validate_prerequisites(type_id, target) -> self.get_state(type_id) (engine.py:241) -> get_workflow_phase(type_id); same threading need as MCPW-2. |
| MCPW-25 | 2361-2380 (handler 1669-1700) | reproject_meta_json / _process_reproject_meta_json | entity read by type_id | read | type_id (ref resolved unscoped by MCPW-1) | never | MCP tool reproject_meta_json; markdown: abandon-feature.md:18 (ref="feature:{id}-{slug}") | unchanged; related W2.2; own lines unchanged; behaviour changes through a callee (W2.2) — unchanged… | Pure projection call: reads entity and workflow_phases by type_id (MCPW-21). Needs the uuid. |
| MCPW-28 | 2383-2425 | _resolve_list_handler_workspace_filter | workflow_phases | resolve | type_id+workspace_uuid (filter value) | optional: default is `_workspace_uuid or None`; with the server workspace unres… | list_features_by_phase, list_features_by_status, query_ready_tasks | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Scope source for the list tools; returns None (cross-workspace) both for project_id='*' and when _workspace_uuid is empty, although the docstring says "else the canonical unknown UUID". A re-key keeps needing a workspace scope for lists. |
| MCPW-26 | 2428-2456 (handler 1703-1708) | list_features_by_phase / _process_list_features_by_phase | join | join | type_id (wp.type_id = e.type_id) | optional (default server workspace via MCPW-28; project_id='*' -> all) | MCP tool list_features_by_phase; markdown: list-features.md:11, workflow-state/SKILL.md:10 | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | engine.list_by_phase -> db.list_workflow_phases(workflow_phase=, workspace_uuid=) (engine.py:284-286), whose join is "LEFT JOIN entities e ON wp.type_id = e.type_id" and whose filter is "(e.workspace_uuid = ? OR e.uuid IS NULL)" (database.py:10362-10386). A row joins every namesake, so a shared typ… |
| MCPW-27 | 2459-2487 (handler 1711-1716) | list_features_by_status / _process_list_features_by_status | join | join | type_id (Python dict wp_map keyed by type_id) | optional (default server workspace; '*' -> all) | MCP tool list_features_by_status; markdown: create-feature.md:12 ("list_features_by_status(status=\"active\")"), list-f… | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | engine.list_by_status builds wp_map = {r["type_id"]: r} from list_workflow_phases and looks each entity up by entity['type_id'] (engine.py:322-345): terry_agent's namesakes get pedantic-drip's row. Needs a map keyed by entity uuid. |
| MCPW-29 | 2490-2502 (handler 1817-1849) | reconcile_check / _process_reconcile_check | workflow_phases | read | type_id | optional: bulk scan scoped by workspace_uuid; the single-feature read and _vali… | MCP tool reconcile_check; listed as a read tool in workflow-state/SKILL.md:10 | unchanged; related W1.3 — unchanged — W1.3: "**Keep:** `check_workflow_drift` and the read-only hel… | _validate_feature_type_id -> feature_dir_name -> db.feature_entity_id(type_id) (unscoped SELECT DISTINCT entity_id ... WHERE type_id = ?, database.py:8264-8267); check_workflow_drift reads get_workflow_phase(type_id) (reconciliation.py:765) or list_workflow_phases(workspace_uuid) (:821); then MCPW-… |
| MCPW-31 | 2505-2520; 1852-1890; 321-337; 78, 80 | reconcile_apply / _process_reconcile_apply / _serialize_rec… | workflow_phases | write | type_id | optional (workspace_uuid=_workspace_uuid or None) | MCP tool reconcile_apply — no command, skill, agent, hook or script calls it (design W1.4) | deleted (W1.4) — deleted by W1.4: "Delete the `reconcile_apply` MCP tool. ... `workflow_state_serve… | None after Phase 1 (deleted). Today: apply_workflow_reconciliation writes workflow_phases from .meta.json by type_id. |
| MCPW-32 | 2523-2535 (handler 1896-1931) | reconcile_frontmatter / _process_reconcile_frontmatter | entity read by type_id | read | type_id | optional: scan_all(workspace_uuid=) scoped; the single-feature path is unscoped | MCP tool reconcile_frontmatter (no markdown caller found) | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Single-feature path: _validate_feature_type_id (feature_entity_id by type_id) then frontmatter_sync.detect_drift(db, filepath, type_id=) -> db.get_entity(lookup_key) (frontmatter_sync.py:236). No workflow_phases/phase_events access. Needs uuid only if entity reads are re-keyed. |
| MCPW-33 | 2538-2550 (handler 2057-2123; call at 2074) | reconcile_status / _process_reconcile_status | workflow_phases | read | type_id | never (check_workflow_drift called without workspace_uuid); the frontmatter sca… | MCP tool reconcile_status (no markdown caller found) | changed (W1.6) — changed by W1.6: "**Scoped:** it passes the workspace to `check_workflow_drift` (`… | check_workflow_drift(engine, db, artifacts_root) with no workspace reads list_workflow_phases(workspace_uuid=None) (reconciliation.py:821) — all workspaces joined on type_id. After W1.6 the scope is the workspace filter of that join, still keyed by type_id. |
| MCPW-34 | 2553-2574 (handler 1934-1974) | init_feature_state / _process_init_feature_state | workflow_phases | write | type_id composed as feature:{feature_id}-{slug} | optional (workspace_uuid=_workspace_uuid or None for register/update_entity; no… | MCP tool init_feature_state (no markdown caller; the create-feature sequence uses register_entity + activate_feature) | unchanged; related W2.1; own lines unchanged; behaviour changes through a callee (W2.1) — unchanged… | Library init_feature_state: get_entity(type_id) unscoped (feature_lifecycle.py:258), register_entity (:262), update_entity(..., workspace_uuid=) (:294), get_workflow_phase(type_id) (:297), update_workflow_phase(type_id, kanban_column=) (:301, no workspace), create_workflow_phase(type_id, kanban_col… |
| MCPW-35 | 2578-2608 (handler 1977-2004) | init_project_state / _process_init_project_state | phase_events | write | type_id (project:{id}-{slug}) + workspace_uuid | optional (workspace_uuid=_workspace_uuid or None) | MCP tool init_project_state; markdown: create-project.md:20, decomposing/SKILL.md:8 | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Registers the project (feature_lifecycle.py:498) -> db.register_entity -> append_phase_event('entity_created') keyed by type_id/project_id (database.py:7765-7775). No workflow_phases row for projects (live: 0 project rows). Needs the event's entity key only. |
| MCPW-36 | 2611-2623 (handler 2007-2030) | activate_feature / _process_activate_feature | workflow_phases | write | type_id (feature_type_id\|ref via MCPW-1) | optional (update_entity gets workspace_uuid; the reads are unscoped) | MCP tool activate_feature; markdown: workflow-state/SKILL.md:18, create-feature.md:21 (via that skill), workflow-transi… | unchanged; related W2.5; own lines unchanged; behaviour changes through a callee (W2.5) — unchanged… | Library activate_feature: _validate_feature_type_id (feature_entity_id by type_id), get_entity(type_id) unscoped (feature_lifecycle.py:566), update_entity(type_id, status="active", workspace_uuid=) (:577); then _project_meta_json. W2.5 adds create_workflow_phase with the caller's workspace; a per-e… |
| MCPW-37 | 2626-2643 (handler 2033-2043) | init_entity_workflow / _process_init_entity_workflow | workflow_phases | upsert | type_id (type_id\|ref via MCPW-1) | optional (workspace_uuid=_workspace_uuid or None passed to upsert_workflow_phas… | MCP tool init_entity_workflow; markdown: add-to-backlog.md:14; scripts/c22_recreate_live_remainder.py:993 | unchanged; related W2.1; own lines unchanged; behaviour changes through a callee (W2.1) — unchanged… | router.init_entity_workflow: get_entity(type_id) unscoped (router.py:358), get_workflow_phase(type_id) (:382), upsert_workflow_phase(type_id, workspace_uuid=) (:393). Needs the entity uuid for the row. |
| MCPW-38 | 2646-2662 (handler 2046-2054) | transition_entity_phase / _process_transition_entity_phase | workflow_phases | write | type_id (type_id\|ref via MCPW-1) | optional (update_entity/update_workflow_phase get workspace_uuid; reads unscope… | MCP tool transition_entity_phase (no markdown caller found) | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | router.transition_entity_phase: get_entity(type_id) (router.py:437), get_workflow_phase(type_id) (:452), update_entity(type_id, status=, workspace_uuid=) (:480), update_workflow_phase(type_id, ..., workspace_uuid=) (:492). Needs uuid. |
| MCPW-39 | 2701-2728 | promote_task | workflow_phases | write | feature_ref (type_id; unscoped get_entity) -> task type_id | optional (task registered with workspace_uuid; create_workflow_phase gets none… | MCP tool promote_task (no markdown caller found; query_ready_tasks's only producer) | changed (W2.1) — changed by W2.1 ("`promote_task` (`task_promotion.py:403`)" passes its workspace)… | task_promotion.promote_task: get_entity(feature_ref) unscoped (task_promotion.py:309), get_workflow_phase(feature_type_id) (:359), get_entity (:383), register_entity (:387-395, returns task_uuid), create_workflow_phase(task_type_id, mode=) (:403). Needs the task uuid it already has for the row. |
| MCPW-40 | 2731-2767 | query_ready_tasks | workflow_phases | read | type_id (parent's) | optional (tasks listed per workspace; parent phase read unscoped) | MCP tool query_ready_tasks (no markdown caller found) | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | task_promotion.query_ready_tasks: list_entities(entity_type="task", workspace_uuid=) (task_promotion.py:57), then parent_wp = db.get_workflow_phase(parent_type_id) (:86) by the parent's type_id although the task holds parent_uuid. Needs a lookup by parent uuid. |
| MCPW-41 | 2770-2789 | get_progress_view | entity read by type_id | resolve | ref -> uuid (db.resolve_ref, unscoped) | never | MCP tool get_progress_view (no markdown caller found) | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | resolve_ref(entity_ref) unscoped exact-match takes the first row; rollup.get_ancestor_progress then walks by uuid (rollup.py:299-308) and reads no workflow_phases. Only the resolution would need a workspace. |
| MCPW-42 | 2797-2868 | record_backward_event | phase_events | write | type_id + legacy project_id | optional (_workspace_uuid or None); entity read unscoped | MCP tool record_backward_event(type_id); markdown: workflow-transitions/SKILL.md:18, secretary.md:29 | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | get_entity(type_id) unscoped (2821) answers entity_not_found for a shared type_id; append_phase_event(event_type='backward', phase=source_phase) also runs step 5, UPDATE workflow_phases SET workflow_phase = source_phase WHERE type_id = ? (database.py:9776-9784). Needs the entity key for both. |
| MCPW-43 | 2871-2989 (queries 2915, 2920, 2938, 2961, 2… | query_phase_analytics | phase_events | read | type_id (optional feature_type_id) + project_id(legacy) | optional: default project_id=_project_id; '*' -> all; unfiltered when _project_… | MCP tool query_phase_analytics; retrospecting/SKILL.md:13 reads "Engine phase events (MCP read tools)" (the tool is not… | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Filters phase_events by type_id and legacy project_id only; rows written with project_id='__unknown__' (285 live) are outside any project scope. A per-entity key needs an entity column on phase_events to scope by entity or workspace. |
| fill-2 | 2992-3057 (grouping key 3017; called at 2926) | _compute_durations (query_phase_analytics' phase_duration b… | phase_events | join | type_id + phase (Python dict key (e["type_id"], e["phase"]) pairing started and… | optional: it inherits query_phase_analytics' filter (MCPW-43), the legacy proje… | MCP tool query_phase_analytics(query_type='phase_duration') (:2926); retrospecting/SKILL.md:13 reads "Engine phase even… | unchanged — unchanged. No W1/W2 change names it; design:509 '1. **Phase 1 (P0): W1 and W2.**', and… | Pairs events in memory by (type_id, phase), so the events of two holders of one type_id that pass the label filter share one group, and zip_longest pairs them by timestamp. Live: feature:002-assessed-mode-pipeline-fix (4 started, 1 completed) and feature:004-rca005-restart-loop-keychain-fix (2 star… |

### `plugins/pd/ui/mermaid.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| UI-10 | 38-85 (nodes 43-54, edges 57-60, click 63-67) | build_mermaid_dag | entity read by type_id | read | type_id (node dict keyed by type_id, node ids hashed from type_id, edges from e… | never | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), detail page lineage graph | unchanged — unchanged in Phase 1 — W3 is Phase 2 ("2. **Phase 2 (P1): W4 changes 1–3, then W3.**")… | Two lineage members with one type_id (possible across workspaces, feature 129) collapse into one node. Edges read e.get("parent_type_id") and styling reads e.get("entity_type"), keys that only get_entity's enriched row carries: lineage rows are plain e.* (database.py:8405-8406, 8425-8426). Needs no… |

### `plugins/pd/ui/routes/board.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| UI-1 | 72-75 | board | join | join | type_id (list_workflow_phases: LEFT JOIN entities e ON wp.type_id = e.type_id) | optional (effective_workspace_uuid: cookie uuid, else startup default; cookie '… | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), route GET / (HTMX refresh every… | unchanged — unchanged in Phase 1 — W3 is Phase 2 ("2. **Phase 2 (P1): W4 changes 1–3, then W3.**")… | db.list_workflow_phases(workspace_uuid=, include_archived=False) selects wp.*, e.name, e.kind, e.artifact_path but no entity uuid (database.py:10379-10384), so a card cannot link by uuid; a row joins every namesake and passes the filter for each namesake's workspace. A per-entity key needs the join… |

### `plugins/pd/ui/routes/entities.py` (4)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| UI-4 | 23-28, 103-107 | _build_workflow_lookup / entity_list | workflow_phases | join | type_id (dict {wp['type_id']: wp}) | optional (list_workflow_phases(workspace_uuid=effective)) | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), route GET /entities | unchanged — unchanged in Phase 1 — W3 is Phase 2 ("2. **Phase 2 (P1): W4 changes 1–3, then W3.**")… | Each listed entity looks up its execution_status by e['type_id'], so namesakes show the row owner's status. Needs the lookup keyed by entity uuid, which list_workflow_phases does not select today. |
| UI-6 | 170 | entity_detail | entity read by type_id | read | uuid or type_id (the path identifier) | never (db.get_entity has no workspace parameter) | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), route GET /entities/{identifier} | unchanged — unchanged in Phase 1 — W3 is Phase 2 ("2. **Phase 2 (P1): W4 changes 1–3, then W3.**")… | Accepts a uuid already; with a type_id identifier it answers 404 for a shared type_id. |
| UI-7 | 182-188 | entity_detail (lineage) | entity read by type_id | read | type_id (entity['type_id'] re-used after the entity was found) | never | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), route GET /entities/{identifier} | unchanged; related W3.2 — unchanged — not named by W1/W2 or by W3.2's detail-page change ("**The de… | db.get_lineage(type_id, ...) returns [] when the type_id is ambiguous (database.py:8376-8383): even when the page is opened by uuid, a shared type_id's detail page shows no ancestors or children. _strip_self_from_lineage also filters by type_id (31-33). Needs get_lineage called with the entity uuid… |
| UI-8 | 193-196 (display entity_detail.html:44-64) | entity_detail (workflow row) | workflow_phases | join | type_id (first row of an unscoped list_workflow_phases() whose type_id matches) | never | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), route GET /entities/{identifier} | unchanged — unchanged in Phase 1 — W3 is Phase 2 ("2. **Phase 2 (P1): W4 changes 1–3, then W3.**")… | Scans every workspace's rows and takes the first with the type_id: a namesake's page shows the owner's phase, mode, last_completed_phase and backward reason. Needs a row lookup by the entity uuid. |

### `plugins/pd/ui/routes/helpers.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| UI-2 | 51-65 (default: ui/__init__.py:125-151) | effective_workspace_uuid | workflow_phases | resolve | workspace_uuid (filter value) | optional: '*' cookie -> None (unscoped); uuid-shaped cookie; else app.state.wor… | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start); used by board (UI-1) and the En… | unchanged — unchanged in Phase 1 — W3 is Phase 2 ("2. **Phase 2 (P1): W4 changes 1–3, then W3.**")… | Scope source only. A re-key does not remove the need for a workspace filter on lists; the filter would need to apply to the row's own entity rather than to any namesake. |

### `plugins/pd/ui/templates/_card.html` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| UI-3 | 1 | board card link | entity read by type_id | read | type_id (href /entities/{{ item.type_id }}) | never | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), board cards -> GET /entities/{i… | unchanged — unchanged in Phase 1 — W3 is Phase 2 ("2. **Phase 2 (P1): W4 changes 1–3, then W3.**")… | The card has only workflow_phases/joined columns; it needs the entity uuid in the row (UI-1) to link by uuid. |

### `plugins/pd/ui/templates/_entities_content.html` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| UI-5 | 73 | entity list link | entity read by type_id | read | type_id (href /entities/{{ entity.type_id }}) | never | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), Entities page rows -> GET /enti… | unchanged — unchanged in Phase 1 — W3 is Phase 2 ("2. **Phase 2 (P1): W4 changes 1–3, then W3.**")… | The entity dict here comes from list_entities/search_entities and carries uuid; the link uses type_id. |

### `plugins/pd/ui/templates/entity_detail.html` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| UI-9 | 83, 98 | ancestor and child links | entity read by type_id | read | type_id (href /entities/{{ a.type_id }} and {{ c.type_id }}) | never | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), detail page lineage lists | unchanged — unchanged in Phase 1 — W3 is Phase 2 ("2. **Phase 2 (P1): W4 changes 1–3, then W3.**")… | Lineage rows are entities rows (e.*) and carry uuid; the links use type_id. |

### `plugins/pd/scripts/cleanup_backlog.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| SCR-3 | 253-263 | apply_archival | entity read by type_id | write | type_id (backlog:{ID}) | never (set_archived called with no workspace_uuid; the re-projection that follo… | command /pd:cleanup-backlog --apply (commands/cleanup-backlog.md:11-26) | unchanged; related W1.2 — unchanged — not named by W1/W2 (W1.2 routes brainstorm archiving through… | db.set_archived(type_id) runs "UPDATE entities SET is_archived = ?, updated_at = ? WHERE type_id = ?" with no workspace clause (database.py:8458-8465): it archives every workspace's entity holding the backlog id. Not a workflow_phases write, but the board drops those rows via include_archived=False… |

### `plugins/pd/scripts/parse_backlog_md.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| SCR-4 | 229-315 | main loop (backlog.md -> registry) | entity read by type_id | write | entity_id match across all workspaces; update by uuid; register into _UNKNOWN_W… | never (list_entities(entity_type="backlog") with no workspace; "Look up existin… | manual CLI only (no command, hook or script invokes it) | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Updates metadata on every workspace's backlog entity whose entity_id matches (by uuid, 304-307), and registers missing ones into the unknown workspace (register_entity appends phase_events 'entity_created'). No workflow_phases write. |

### `plugins/pd/scripts/pd_state_diff.py` (2)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| SCR-1 | 119-139 (called at 334) | _fetch_current_state | join | join | type_id (LEFT JOIN workflow_phases wp ON wp.type_id = e.type_id) | never (every workspace's entities) | hook pre-commit-guard.sh emit_pd_state_diff (PreToolUse on git commit) -> writes pd-state.diff.md | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Raw SQL join on type_id: both namesakes get the owner's workflow_phase. Needs the join on the entity key (wp.uuid = e.uuid, or type_id+workspace); read-only connection (mode=ro, 97-116). |
| SCR-2 | 142-161 (called at 350) | _phase_events_for | phase_events | read | type_id | never | hook pre-commit-guard.sh emit_pd_state_diff | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Replays phase_events by type_id to reconstruct base-time state per entity uuid: a namesake's events (entity_created, status changes, entity_promoted) replay onto both entity rows. Needs an entity key on phase_events. |

### `scripts/c22_recreate_live_remainder.py` (2)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| SCR-9 | 988-996 | _ensure_backlog_workflow | workflow_phases | read | type_id | never (existence check); then init_entity_workflow(type_id=) through the workfl… | one-time C22 remediation script (applied to the live registry 2026-09-25 per I1-verify); its tests | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | "SELECT 1 FROM workflow_phases WHERE type_id = ?" treats any namesake's row as the replacement's row. Needs the replacement's uuid (Row carries it). |
| SCR-10 | 1157-1161 | verification (backlog workflow row) | workflow_phases | read | type_id | never | one-time C22 remediation script, verify step | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Verification read by type_id; needs the replacement's uuid under a per-entity key. |

### `scripts/dev/cutover-prepass.sql` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| SCR-11 | 14-44 | cutover pre-pass (backlog #085) | phase_events | write | none (rows chosen by phase value; id/type_id/project_id copied into cutover_pre… | n/a | manual, with the v1->v2 rebuild tool per docs/dev_guides/cutover-runbook.md | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | UPDATE phase_events SET phase='create-plan' WHERE phase='create-tasks'; DELETE single-character skipped rows; the record table and INSERT ... SELECT list name phase_events' columns explicitly, so an added entity column would not be recorded. |

### `scripts/fix_kanban_columns.py` (2)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| SCR-5 | 27-38 (run 59-83) | _UPDATE_SQL / fix_kanban_columns | workflow_phases | write | type_id (correlated subquery entities.type_id = workflow_phases.type_id) | never | manual one-time CLI (no command, hook or script invokes it; only scripts/test_fix_kanban_columns.py) | unchanged — unchanged — named and deferred in W3: "**`scripts/fix_kanban_columns.py:28`'s correlate… | The scalar subquery takes the first entities row holding the type_id, so a shared id's kanban column follows an arbitrary namesake's status. Needs the subquery keyed by the row's entity (uuid). |
| SCR-6 | 41-56 (dry run 86-105) | _PREVIEW_SQL / _dry_run | join | join | type_id (LEFT JOIN entities e ON e.type_id = wp.type_id) | never | manual CLI --dry-run | unchanged — unchanged — deferred with SCR-5 (W3 "Named, and deferred with the re-key (D3)") | Preview join duplicates a shared id's row once per namesake. Needs the join on the entity key. |

### `scripts/migrate_db.py` (2)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| SCR-8 | 117-121, 426-430 | cmd_manifest / cmd_migrate | workflow_phases | read | none (row count) | n/a | scripts/migrate.sh export (manifest) and migrate subcommand | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | SELECT count(*) only; unaffected by the key unless the table is renamed. |
| SCR-7 | 199-273 | cmd_merge_entities | workflow_phases | write | type_id (new ids = src type_ids absent from main; rows copied by type_id) | never | scripts/migrate.sh import (merge-entities at migrate.sh:393); manual cross-machine migration | unchanged; related W5.5 — unchanged — not named by W1/W2 (W5.5 in Phase 4 touches only its tests: "… | Merges by bare type_id (208-211, 236-238), inserts workflow_phases with an explicit column list that omits uuid and workspace_uuid (249-258), so wp_autofill_workspace_uuid picks the workspace; reconstructs parents through entities.parent_type_id (262-273), a column the live schema no longer has (li… |

### `scripts/seed-census-db.py` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| SCR-12 | 116-160, 161-225 | _append_event_stream / seed_census_db | events | write | uuid (events.append_event(conn, entity_uuid=...)) | n/a (synthetic v2 DB in --target-dir) | manual bench seeding (feature 126 D8); test plugins/pd/hooks/lib/entity_registry/test_census_seeder.py | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | None: the v2 events stream is already keyed by entity uuid, and the script never touches workflow_phases or phase_events. Evidence for the v2 direction (Phase R criterion 6). |

### `plugins/pd/hooks/pre-commit-guard.sh` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| HOOK-4 | 204-247 (called at 262) | emit_pd_state_diff | join | join | type_id (via pd_state_diff.py, SCR-1/SCR-2) | never | PreToolUse hook on Bash `git commit` (hooks.json:74) | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Launch site for pd_state_diff.py (SCR-1, SCR-2), which joins workflow_phases and reads phase_events by type_id across all workspaces; fail-open. |

### `plugins/pd/hooks/session-start.sh` (3)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| HOOK-3 | 62-113, 116-135, 380-404 | find_active_feature / parse_feature_meta / context build | entity read by type_id | read | none in the DB (reads .meta.json files); emits the feature id-slug that later b… | n/a | SessionStart hook -> additionalContext "You're working on feature {id}-{slug}" | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Source of the `feature:{id}-{slug}` text that commands pass to workflow tools: it is the checkout's own projection, so the id is local but not unique across workspaces (a namesake's registry row answers). No DB access; nothing to re-key here, but callers keep only a type_id. |
| HOOK-1 | 496-539 (called at 628) | run_reconciliation | workflow_phases | write | type_id (Task 2 reconciles workflow_phases from .meta.json; Task 1 writes entit… | optional (orchestrator resolves workspace_uuid via resolve_workspace_uuid(proje… | SessionStart hook (hooks.json:27) -> python -m reconciliation_orchestrator --project-root --artifacts-root --entity-db | changed (W1.3,W1.1,W1.7,W1.8) — changed: the display block (523-539) is deleted by W1.3 ("its displ… | The shell only launches the orchestrator and prints workflow_reconcile counts; after Phase 1 the remaining writers are the brainstorm registration (entity_status Part 1), cascade recovery and dependency freshness, surveyed in the library area. |
| HOOK-2 | 545-584 (called at 631) | run_doctor_autofix | workflow_phases | read | type_id (doctor checks such as the workflow_phases orphan check, doctor/checks.… | optional (per check) | SessionStart hook -> python -m doctor --entities-db --project-root --artifacts-root --fix; also /pd:doctor (commands/do… | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Launch site only; the checks and fix actions (library area) read/write workflow_phases and phase_events by type_id. The --fix run writes the live registry at every session start. |

### `plugins/pd/hooks/start-ui-server.sh` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| HOOK-5 | 63 | UI server launch | workflow_phases | read | type_id (UI rows UI-1..UI-10) | optional (UI-2) | SessionStart hook (hooks.json:45) | unchanged — unchanged in Phase 1 (UI changes are W3, Phase 2) | Launch site only; see UI rows. |

### `plugins/pd/commands/abandon-feature.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-1 | 12, 18 | /pd:abandon-feature step 2 | phase_events | write | type_id ("feature:{id}-{slug}" to update_entity; ref="feature:{id}-{slug}" to r… | optional (update_entity scoped by the entity server's legacy project id); repro… | command /pd:abandon-feature | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Passes type_ids only. update_entity(status="abandoned") appends a phase_events status event by type_id (MCPE-10); the projection (MCPW-25) answers "entity not found" for a shared id. No workflow_phases write, so the board card keeps its column. Could name another workspace's type_id: yes — the id c… |

### `plugins/pd/commands/add-to-backlog.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-2 | 13-14 | /pd:add-to-backlog steps 3-4 | workflow_phases | upsert | type_id ("backlog:{entity_id}" built from register_entity's reply) | optional (register_entity in the resolved workspace; init_entity_workflow via M… | command /pd:add-to-backlog | unchanged; related W2.1 — unchanged in its own text; the init_entity_workflow it calls changes by W… | register_entity replies with the type_id only (no uuid), so step 4 re-addresses the new entity by the type_id text. Could name another workspace's type_id: yes, if the allocated seq+slug matches a backlog item another workspace already holds (I1-verify: allocation has no cross-workspace check; 0 su… |

### `plugins/pd/commands/cleanup-backlog.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-4 | 8, 11-28 | /pd:cleanup-backlog | entity read by type_id | write | type_id (backlog:{ID} inside cleanup_backlog.py) | never for the archive write (SCR-3) | command /pd:cleanup-backlog --apply -> plugins/pd/scripts/cleanup_backlog.py | unchanged; related W1.2 — unchanged — not named by W1/W2 (W1.2's sweep covers "other markdown writi… | Runs SCR-3: set_archived(type_id) with no workspace archives every workspace's namesake. Could name another workspace's type_id: yes if two workspaces hold the same backlog id (0 live). |

### `plugins/pd/commands/cleanup-brainstorms.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-3 | 25 | /pd:cleanup-brainstorms step 4 | phase_events | write | type_id ("brainstorm:{stem}" from the deleted file name) | optional (update_entity scoped by the entity server's legacy project id) | command /pd:cleanup-brainstorms | changed (W1.2) — changed by W1.2: "`/pd:cleanup-brainstorms` step 4 calls `update_entity(type_id=\"… | Today writes status="archived" (a phase_events status event by type_id); after W1.2 calls set_archived for the resolved entity. Could name another workspace's type_id: yes — live has 2 shared brainstorm ids (brainstorm:20260318-025248-three-claws-v2-protocol, brainstorm:20260326-030832-openclaw-gap… |

### `plugins/pd/commands/create-feature.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-5 | 12, 18-22 | /pd:create-feature steps 2-6 | workflow_phases | write | type_id ("feature:{id}-{slug}" from allocate_entity_id; parent_uuid for promoti… | optional (allocate/register in the resolved workspace; later tools per MCPW row… | command /pd:create-feature | unchanged — unchanged in its own text (W2 tests exercise this sequence: "allocate, mkdir, `register… | Sequence: list_features_by_status (scoped), allocate_entity_id (per workspace), mkdir, register_entity (entity_created phase event; reply has no uuid), activate_feature via workflow-state (MCPW-36), record_mini_spec(feature_type_id=) (MCPW-23), then implement's transition_phase(skipped_phases). Eve… |

### `plugins/pd/commands/create-plan.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-11 | 17, 21 | /pd:create-plan engine entry/exit | workflow_phases | write | type_id (resolved per workflow-transitions) | optional (per MCPW-4/MCPW-12) | command /pd:create-plan | unchanged — unchanged in its own text | Same as MD-9 with target_phase="create-plan". Could name another workspace's type_id: yes — the id comes from `--feature=<id>-<slug>` or the single active feature (session context from .meta.json, HOOK-3, or list_features_by_status); feature ids are per-workspace sequences, and live feature:035-sli… |

### `plugins/pd/commands/create-project.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-6 | 17-20 | /pd:create-project steps 3-6 | phase_events | write | type_id for set_parent (brainstorm and backlog type_ids); parent_uuid for init_… | optional | command /pd:create-project | unchanged; related W4.3 — unchanged — not named by W1/W2 (W4.3 relabels init_project_state's cross-… | register (brainstorm with display_id) and init_project_state append entity_created phase events by type_id (MCPE-5, MCPW-35); set_parent passes type_ids that db.set_parent resolves unscoped (MCPE-7). The step names a "{brainstorm uuid}" for parent_uuid, but register_entity and get_entity return no… |

### `plugins/pd/commands/create-specialist-team.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-7 | 106-114, 206-207 | /pd:create-specialist-team step 3 | workflow_phases | read | type_id ("feature:{id}-{slug}" from the checkout's .meta.json files) | never (MCPW-2) | command /pd:create-specialist-team | unchanged; related W1.5 — unchanged in its own text; the get_phase it calls changes by W1.5 (MCPW-2) | get_phase(type_id) reads workflow_phases by type_id. Could name another workspace's type_id: yes — the id comes from `--feature=<id>-<slug>` or the single active feature (session context from .meta.json, HOOK-3, or list_features_by_status); feature ids are per-workspace sequences, and live feature:… |

### `plugins/pd/commands/design.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-10 | 17, 22 | /pd:design engine entry/exit | workflow_phases | write | type_id (resolved per workflow-transitions) | optional (per MCPW-4/MCPW-12) | command /pd:design | unchanged — unchanged in its own text | Same as MD-9 with target_phase="design". Could name another workspace's type_id: yes — the id comes from `--feature=<id>-<slug>` or the single active feature (session context from .meta.json, HOOK-3, or list_features_by_status); feature ids are per-workspace sequences, and live feature:035-slim-wat… |

### `plugins/pd/commands/doctor.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-20 | 15-21 | /pd:doctor step 1 | workflow_phases | read | type_id (doctor checks) | optional (per check) | command /pd:doctor (python -m doctor, same module as HOOK-2) | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Launch site only; no type_id passed. The doctor module's checks/fixes are in the library area. |

### `plugins/pd/commands/finish-feature.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-12 | 17, 32 | /pd:finish-feature engine entry/exit | workflow_phases | write | type_id (resolved per workflow-transitions) | optional (per MCPW-4/MCPW-12) | command /pd:finish-feature | unchanged; related W2.3 — unchanged in its own text; the finish completion reaches _check_artifact_… | complete_phase(phase="finish") is "what marks the entity terminal" (engine update_entity(status="completed") by type_id, MCPW-14) and triggers the artifact check (MCPW-22). Could name another workspace's type_id: yes — the id comes from `--feature=<id>-<slug>` or the single active feature (session… |

### `plugins/pd/commands/implement.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-8 | 12, 15-16, 21 | /pd:implement steps 1-2, 7 | phase_events | read | type_id (resolved feature) | never (get_mini_spec reads every workspace's events, MCPW-24) | command /pd:implement | unchanged — unchanged in its own text; engine entry/exit tools change as MCPW-4/MCPW-12 say | Express detection is `get_mini_spec` resolving (MCPW-24: unscoped phase_events read), then entry transition_phase(target_phase="implement", skipped_phases=...) and exit complete_phase via workflow-transitions. Could name another workspace's type_id: yes — the id comes from `--feature=<id>-<slug>` o… |

### `plugins/pd/commands/list-features.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-13 | 11-12 | /pd:list-features | join | read | none passed (status/phase filters); results keyed by feature_type_id | optional (list tools default to the server's workspace, MCPW-28) | command /pd:list-features | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | No type_id is passed in. list_features_by_status/phase join workflow_phases on type_id (MCPW-26, MCPW-27), so a namesake's row can appear under this workspace's entity; export_entities is scoped and returns uuid. |

### `plugins/pd/commands/retrospect.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-14 | 8, 10 | /pd:retrospect | workflow_phases | read | type_id (resolved feature) | never (get_phase, MCPW-2) | command /pd:retrospect (and finish-feature step 5 via the retrospecting skill) | unchanged; related W1.5 — unchanged in its own text; the get_phase it calls changes by W1.5 (MCPW-2) | Reads engine phase state with get_phase(type_id). Could name another workspace's type_id: yes — the id comes from `--feature=<id>-<slug>` or the single active feature (session context from .meta.json, HOOK-3, or list_features_by_status); feature ids are per-workspace sequences, and live feature:035… |

### `plugins/pd/commands/secretary.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-16 | 15, 29 | /pd:secretary routing | phase_events | write | type_id (named feature) | never for reads (get_phase); record_backward_event per MCPW-42 | command /pd:secretary | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | get_phase(type_id) to route; mid-express escalation calls record_backward_event(feature_type_id, source_phase="implement", target_phase="specify", ...), which also sets workflow_phases.workflow_phase by type_id (MCPW-42). Could name another workspace's type_id: yes — the id comes from `--feature=<i… |

### `plugins/pd/commands/show-lineage.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-17 | 11-13 | /pd:show-lineage steps 1-3 | entity read by type_id | read | type_id ("feature:{id}-{slug}", "project:{id}", "backlog:{id}", "brainstorm:{st… | never for the final reads (MCPE-8, MCPE-9) | command /pd:show-lineage | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | get_entity(ref="feature:{id}") resolves the prefix in scope but re-reads by type_id unscoped; get_lineage(type_id=) resolves unscoped and returns "Entity not found" for a shared id. Could name another workspace's type_id: yes — `--project=P001` names live project:P001 (3 workspaces), and shared fea… |

### `plugins/pd/commands/show-status.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-18 | 10-13 | /pd:show-status | workflow_phases | read | type_id (from export_entities' type_id field) | optional (export_entities scoped to the server's project; get_phase/get_entity… | command /pd:show-status | unchanged; related W1.5 — unchanged in its own text; the get_phase it calls changes by W1.5 (MCPW-2) | Takes this workspace's active features from export_entities (which does return uuid) and calls get_phase(feature_type_id=...) by type_id. Could name another workspace's type_id: yes, when one of this workspace's features shares its type_id (live: feature:035-slim-watchdog-self-mgmt is active in two… |

### `plugins/pd/commands/specify.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-9 | 17, 21 | /pd:specify engine entry/exit | workflow_phases | write | type_id (resolved per workflow-transitions) | optional (per MCPW-4/MCPW-12) | command /pd:specify | unchanged — unchanged in its own text (tools per MCPW-4/MCPW-12) | transition_phase(target_phase="specify") and complete_phase via workflow-transitions/SKILL.md:16, :33 with the feature type_id. Could name another workspace's type_id: yes — the id comes from `--feature=<id>-<slug>` or the single active feature (session context from .meta.json, HOOK-3, or list_feat… |

### `plugins/pd/commands/wrap-up.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-19 | 12, 15 | /pd:wrap-up step 3 | workflow_phases | read | type_id (active feature) | never (MCPW-2) | command /pd:wrap-up | unchanged; related W1.5 — unchanged in its own text; the get_phase it calls changes by W1.5 (MCPW-2) | Read-only get_phase(type_id); explicitly no transition/complete. Could name another workspace's type_id: yes — the id comes from `--feature=<id>-<slug>` or the single active feature (session context from .meta.json, HOOK-3, or list_features_by_status); feature ids are per-workspace sequences, and l… |

### `plugins/pd/skills/decomposing/SKILL.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-21 | 8, 15, 23 | decomposing steps 3 and 7 | phase_events | write | parent by uuid (project_uuid from init_project_state); features by allocated se… | optional (allocate/register in the resolved workspace) | skill decomposing (from /pd:create-project step 8) | unchanged; related W2.5 — unchanged in its own text; the planned features it registers get their wo… | The one markdown path that carries a uuid (project_uuid) into a tool. register_entity(status="planned") appends entity_created events and creates no workflow_phases row. Could name another workspace's type_id: only on a seq+slug collision at allocation. |

### `plugins/pd/skills/retrospecting/SKILL.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-15 | 13 | retrospecting bundle (engine phase events) | phase_events | read | type_id (+ legacy project_id default) — the tool is not named; query_phase_anal… | optional (query_phase_analytics defaults to the server's legacy project id, MCP… | skill retrospecting (from /pd:retrospect, /pd:finish-feature) | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | Retro figures (timings, iterations, reviewer notes, backward transitions) come from phase_events rows keyed by type_id/project_id; rows written with project_id='__unknown__' fall outside the default scope. Could name another workspace's type_id: yes — the id comes from `--feature=<id>-<slug>` or th… |

### `plugins/pd/skills/workflow-state/SKILL.md` (1)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-22 | 10, 14-20 | Activating a planned feature | workflow_phases | write | type_id ("feature:{id}-{slug}" from `--feature=<id>-<slug>`) | optional (MCPW-36) | skill workflow-state (from /pd:create-feature step 5 and any planned-feature start) | changed (W2.7) — changed by W2.7: "The workflow-state skill's \"Activating a planned feature\" step… | activate_feature(feature_type_id=) by type_id (MCPW-36; W2.5 makes it seed the workflow_phases row). Line 10 lists the read tools (get_phase, list_features_by_status, list_features_by_phase, validate_prerequisites, reconcile_check, get_mini_spec), all type_id-keyed. Could name another workspace's t… |

### `plugins/pd/skills/workflow-transitions/SKILL.md` (3)

| id | line | symbol | object | op | key_used | workspace_scoped | reached_from | phase1_fate | rekey_needs |
|---|---|---|---|---|---|---|---|---|---|
| MD-23 | 15-18 | Phase entry | workflow_phases | write | type_id ("Resolve the feature: `--feature=<id>-<slug>` argument, else the singl… | optional (MCPW-4, MCPW-42) | skill workflow-transitions (phase entry for specify, design, create-plan, implement, finish-feature) | unchanged — unchanged in its own text; the tools change as MCPW-4 says | transition_phase(feature_type_id, target_phase, yolo_active, skipped_phases=[...]) and record_backward_event(type_id, source_phase, target_phase, reason) — both by the type_id text; the skill never obtains a uuid. Could name another workspace's type_id: yes — the id comes from `--feature=<id>-<slug… |
| MD-24 | 21-30 | Phase exit step 1 (frontmatter injection) | entity read by type_id | read | type_id ("feature:{id}-{slug}" argv to frontmatter_inject.py) | never (frontmatter_inject.py:160 db.get_entity(feature_type_id)) | skill workflow-transitions phase exit, per artifact | unchanged — unchanged — not named by W1 or W2 (design "Order and gates": "1. **Phase 1 (P0): W1 and… | A Python CLI reached from markdown: frontmatter_inject.py opens the registry and reads get_entity(feature_type_id) unscoped (None for a shared id, so no header is injected; errors are swallowed by `\|\| true`). Needs the uuid or a workspace to address the entity. |
| MD-25 | 33, 46 | Phase exit step 2; MCP degradation | workflow_phases | write | type_id | optional (MCPW-12) | skill workflow-transitions phase exit (every phase command) | unchanged — unchanged in its own text; the tool changes as MCPW-12 says | complete_phase(feature_type_id, phase, iterations, reviewer_notes=[...]) by type_id; for a shared id it fails with feature_not_found (MCPW-15) and, per :46, the command stops and runs /pd:doctor. Could name another workspace's type_id: yes — the id comes from `--feature=<id>-<slug>` or the single a… |

## 5. Phase-1 fates

Phase 1 is W1 and W2 of the design (design:509). A site is `changed` only when Phase 1 edits its own lines; a change that reaches it through a callee is listed in `phase1_related` (sections 1.3 and 10.3).

### 5.1 Counts

| Area | Rows | deleted | changed | unchanged | of which test-file rows (deleted / changed / unchanged) |
|---|---|---|---|---|---|
| schema | 84 | 0 | 4 | 80 | 0 / 0 / 5 |
| engines | 94 | 11 | 19 | 64 | 0 / 0 / 0 |
| surfaces | 113 | 1 | 9 | 103 | 0 / 0 / 1 |
| tests | 73 | 0 | 20 | 53 | 0 / 20 / 53 |
| synth | 2 | 0 | 0 | 2 | 0 / 0 / 0 |
| fill | 3 | 0 | 1 | 2 | 0 / 1 / 0 |
| **all** | **369** | **12** | **53** | **304** | **0 / 21 / 59** |

- **Sites other than test files:** 289: 12 deleted, 32 changed, 245 unchanged. **277 survive Phase 1.**
- **By object (sites other than test files):**

| object_class | deleted | changed | unchanged |
|---|---|---|---|
| workflow_phases | 7 | 16 | 87 |
| entity read by type_id | 2 | 4 | 73 |
| phase_events | 0 | 3 | 38 |
| entity write by type_id | 3 | 6 | 12 |
| migration | 0 | 0 | 12 |
| events | 0 | 0 | 5 |
| entity list feeding a type_id write | 0 | 3 | 0 |
| trigger | 0 | 0 | 3 |
| view | 0 | 0 | 3 |
| index | 0 | 0 | 2 |
| cross_workspace_allowlist | 0 | 0 | 1 |
| entity_display | 0 | 0 | 1 |
| guard (no table access) | 0 | 0 | 1 |
| entities_fts | 0 | 0 | 1 |
| entity_tags | 0 | 0 | 1 |
| projects | 0 | 0 | 1 |
| sequences | 0 | 0 | 1 |
| entity_okr_alignment | 0 | 0 | 1 |
| migration_audit_log | 0 | 0 | 1 |
| entity_relations | 0 | 0 | 1 |

### 5.2 Sites Phase 1 deletes

| id | file:line | symbol | object | by |
|---|---|---|---|---|
| engines-90 | reconciliation_orchestrator/__main__.py:126-142 | main (Task 2) | workflow_phases (via apply_workflow_rec… | W1.3 |
| engines-84 | reconciliation_orchestrator/entity_status.py:58 | _sync_meta_json_entities | entities (archive flag by type_id) | W1.1 |
| engines-85 | reconciliation_orchestrator/entity_status.py:77 | _sync_meta_json_entities | entity read by type_id | W1.1 |
| engines-86 | reconciliation_orchestrator/entity_status.py:83-88 | _sync_meta_json_entities | entities (write by type_id) | W1.1 |
| engines-88 | reconciliation_orchestrator/entity_status.py:230 | _sync_brainstorm_entities (Part 2) | entities (archive flag by type_id) | W1.1 |
| engines-7 | workflow_engine/engine.py:599 | WorkflowStateEngine._hydrate_from_meta_json | entity read by type_id | W1.5 |
| engines-8 | workflow_engine/engine.py:633-639 | WorkflowStateEngine._hydrate_from_meta_json | workflow_phases | W1.5 |
| engines-9 | workflow_engine/engine.py:649 | WorkflowStateEngine._hydrate_from_meta_json | workflow_phases | W1.5 |
| engines-43 | workflow_engine/reconciliation.py:445 | _reconcile_single_feature | workflow_phases | W1.3 |
| engines-44 | workflow_engine/reconciliation.py:495-500 | _reconcile_single_feature | workflow_phases | W1.3 |
| engines-45 | workflow_engine/reconciliation.py:534-537 | _reconcile_single_feature | workflow_phases | W1.3 |
| MCPW-31 | mcp/workflow_state_server.py:2505-2520; 1852-1890; 321-337; 78, 80 | reconcile_apply / _process_reconcile_apply / _serialize_reconcile_act… | workflow_phases | W1.4 |

### 5.3 Sites Phase 1 changes, by change

| Change | Sites (id: file:line) |
|---|---|
| W1.1 | tests-49: reconciliation_orchestrator/test_entity_status.py; tests-47: reconciliation_orchestrator/test_orchestrator.py; HOOK-1: hooks/session-start.sh:496-539 (called at 628) |
| W1.2 | MD-3: commands/cleanup-brainstorms.md:25; MCPE-10: mcp/entity_server.py:1082-1143 (handler 369-386) |
| W1.3 | tests-47: reconciliation_orchestrator/test_orchestrator.py; tests-38: workflow_engine/test_c11_reconciliation_dir_name.py; tests-37: workflow_engine/test_reconciliation.py; HOOK-1: hooks/session-start.sh:496-539 (called at 628) |
| W1.4 | tests-56: mcp/test_c11_mcp_dir_name.py; tests-55: mcp/test_feature_134_trustgate.py; tests-51: mcp/test_workflow_state_server.py |
| W1.5 | engines-1: workflow_engine/engine.py:102-105 (read 102; no-row fal…; tests-39: workflow_engine/test_c11_engine_dir_name.py; tests-33: workflow_engine/test_engine.py |
| W1.6 | tests-51: mcp/test_workflow_state_server.py; MCPW-33: mcp/workflow_state_server.py:2538-2550 (handler 2057-2123;… |
| W1.7 | engines-71: entity_registry/dependencies.py:184; engines-72: entity_registry/dependencies.py:185-196; tests-17: entity_registry/test_dependencies.py; engines-46: workflow_engine/reconciliation.py:618; 666; engines-47: workflow_engine/reconciliation.py:690; engines-51: workflow_engine/rollup.py:196; engines-52: workflow_engine/rollup.py:267-270; engines-53: workflow_engine/rollup.py:373-376; tests-37: workflow_engine/test_reconciliation.py; HOOK-1: hooks/session-start.sh:496-539 (called at 628) |
| W1.8 | engines-89: reconciliation_orchestrator/dependency_freshness.py:25; tests-50: reconciliation_orchestrator/test_dependency_freshness.py; HOOK-1: hooks/session-start.sh:496-539 (called at 628) |
| W2.1 | tests-73: (shared test fixtures); schema-32: entity_registry/database.py:9992-9996; schema-33: entity_registry/database.py:10016-10046; schema-36: entity_registry/database.py:10181-10266 (default 10235-10…; schema-37: entity_registry/database.py:10268-10294 (INSERT OR IGNORE…; tests-6: entity_registry/test_database.py; engines-32: workflow_engine/feature_lifecycle.py:305; engines-39: workflow_engine/task_promotion.py:403; tests-36: workflow_engine/test_c11_validator_and_init.py; tests-35: workflow_engine/test_feature_lifecycle.py; tests-44: workflow_engine/test_task_promotion.py; tests-52: mcp/test_c8_workflow_state_kind.py; MCPW-39: mcp/workflow_state_server.py:2701-2728 |
| W2.2 | fill-3: hooks/tests/test-workflow-regression.sh; tests-51: mcp/test_workflow_state_server.py; MCPW-21: mcp/workflow_state_server.py:412-596 (reads at 436, 507; d… |
| W2.3 | tests-55: mcp/test_feature_134_trustgate.py; tests-51: mcp/test_workflow_state_server.py; MCPW-22: mcp/workflow_state_server.py:1279-1315 (reads 1284, 1293,… |
| W2.4 | tests-70: entity_registry/test_c3_allocation_callers.py; tests-44: workflow_engine/test_task_promotion.py |
| W2.5 | engines-33: workflow_engine/feature_lifecycle.py:566; engines-34: workflow_engine/feature_lifecycle.py:577; tests-36: workflow_engine/test_c11_validator_and_init.py; tests-35: workflow_engine/test_feature_lifecycle.py; tests-56: mcp/test_c11_mcp_dir_name.py; tests-51: mcp/test_workflow_state_server.py |
| W2.6 | engines-65: entity_registry/backfill.py:254; engines-66: entity_registry/backfill.py:297; engines-67: entity_registry/backfill.py:317-321; engines-68: entity_registry/backfill.py:326-331; engines-69: entity_registry/backfill.py:390; engines-70: entity_registry/backfill.py:395-402; tests-25: entity_registry/test_backfill.py; tests-26: entity_registry/test_backfill_parent_uuid.py; MCPE-1: mcp/entity_server.py:281-294 |
| W2.7 | MD-22: skills/workflow-state/SKILL.md:10, 14-20 |

A site named by several changes appears once per change.

### 5.4 Sites that survive Phase 1: the re-key's checklist

Every row that Phase 1 changes or leaves unchanged, test files excluded (section 7 lists those), grouped by object and file. Each entry is `id @ first line`; a `*` marks a site Phase 1 changes. Section 4 has each row's fields.

| object_class | file | surviving sites |
|---|---|---|
| workflow_phases (103) | entity_registry/database.py | schema-11 @ 1368, schema-40 @ 8737, schema-28 @ 9776, schema-33* @ 10016, schema-34 @ 10048, schema-35 @ 10058, schema-37* @ 10268, schema-38 @ 10296, schema-39 @ 10316 |
|  | entity_registry/backfill.py | engines-63 @ 210, engines-64 @ 216, engines-66* @ 297, engines-67* @ 317, engines-68* @ 326, engines-69* @ 390, engines-70* @ 395 |
|  | entity_registry/rebuild_tool.py | schema-78 @ 786 |
|  | workflow_engine/engine.py | engines-1* @ 102, engines-2 @ 156, engines-3 @ 214, engines-5 @ 285, engines-6 @ 322 |
|  | workflow_engine/entity_engine.py | engines-11 @ 169, engines-12 @ 280, engines-13 @ 309, engines-14 @ 312, engines-17 @ 448, engines-18 @ 469, engines-20 @ 503, engines-21 @ 512, engines-23 @ 722 |
|  | workflow_engine/feature_lifecycle.py | engines-26 @ 158, engines-27 @ 160, engines-30 @ 297, engines-31 @ 301, engines-32* @ 305 |
|  | workflow_engine/reconciliation.py | engines-40 @ 306, engines-48 @ 765, engines-49 @ 821 |
|  | workflow_engine/rollup.py | engines-50 @ 49 |
|  | workflow_engine/router.py | engines-55 @ 382, engines-56 @ 393, engines-58 @ 452, engines-60 @ 492 |
|  | workflow_engine/secretary_intelligence.py | engines-62 @ 507 |
|  | workflow_engine/task_promotion.py | engines-35 @ 86, engines-37 @ 359, engines-39* @ 403 |
|  | doctor/checks.py | engines-91 @ 367 |
|  | doctor/fix_actions/__init__.py | engines-92 @ 92 |
|  | mcp/entity_server.py | MCPE-2 @ 275, MCPE-1* @ 281 |
|  | mcp/workflow_state_server.py | MCPW-44 @ 217, MCPW-6 @ 1129, MCPW-9 @ 1190, MCPW-22* @ 1279, MCPW-14 @ 1413, MCPW-17 @ 1479, MCPW-2 @ 2177, MCPW-4 @ 2192, MCPW-12 @ 2225, MCPW-3 @ 2342, MCPW-28 @ 2383, MCPW-26 @ 2428, MCPW-27 @ 2459, MCPW-29 @ 2490, MCPW-33* @ 2538, MCPW-34 @ 2553, MCPW-36 @ 2611, MCPW-37 @ 2626, MCPW-38 @ 2646, MCPW-39* @ 2701, MCPW-40 @ 2731 |
|  | ui/routes/board.py | UI-1 @ 72 |
|  | ui/routes/entities.py | UI-4 @ 23, UI-8 @ 193 |
|  | ui/routes/helpers.py | UI-2 @ 51 |
|  | scripts/pd_state_diff.py | SCR-1 @ 119 |
|  | scripts/c22_recreate_live_remainder.py | SCR-9 @ 988, SCR-10 @ 1157 |
|  | scripts/fix_kanban_columns.py | SCR-5 @ 27, SCR-6 @ 41 |
|  | scripts/migrate_db.py | SCR-8 @ 117, SCR-7 @ 199 |
|  | hooks/pre-commit-guard.sh | HOOK-4 @ 204 |
|  | hooks/session-start.sh | HOOK-1* @ 496, HOOK-2 @ 545 |
|  | hooks/start-ui-server.sh | HOOK-5 @ 63 |
|  | commands/add-to-backlog.md | MD-2 @ 13 |
|  | commands/create-feature.md | MD-5 @ 12 |
|  | commands/create-plan.md | MD-11 @ 17 |
|  | commands/create-specialist-team.md | MD-7 @ 106 |
|  | commands/design.md | MD-10 @ 17 |
|  | commands/doctor.md | MD-20 @ 15 |
|  | commands/finish-feature.md | MD-12 @ 17 |
|  | commands/list-features.md | MD-13 @ 11 |
|  | commands/retrospect.md | MD-14 @ 8 |
|  | commands/show-status.md | MD-18 @ 10 |
|  | commands/specify.md | MD-9 @ 17 |
|  | commands/wrap-up.md | MD-19 @ 12 |
|  | skills/workflow-state/SKILL.md | MD-22* @ 10 |
|  | skills/workflow-transitions/SKILL.md | MD-23 @ 15, MD-25 @ 33 |
| entity read by type_id (77) | entity_registry/database.py | schema-25 @ 1949, schema-24 @ 6206, schema-51 @ 6896, schema-50 @ 6980, schema-53 @ 7060, schema-55 @ 7156, schema-54 @ 7177, schema-57 @ 7280, schema-66 @ 7792, schema-58 @ 7981, schema-52 @ 8212, schema-56 @ 8247, schema-45 @ 8433, schema-46 @ 8474, synth-1 @ 8506, schema-47 @ 8808, schema-44 @ 8967, schema-48 @ 9120, schema-27 @ 9751, schema-29 @ 9786, schema-32* @ 9992, schema-36* @ 10181 |
|  | entity_registry/frontmatter_inject.py | engines-80 @ 160 |
|  | entity_registry/frontmatter_sync.py | engines-81 @ 236, engines-82 @ 336 |
|  | entity_registry/server_helpers.py | engines-73 @ 257, engines-74 @ 265, engines-76 @ 317, engines-77 @ 329, engines-78 @ 484 |
|  | workflow_engine/feature_lifecycle.py | engines-24 @ 155, engines-28 @ 258, engines-33* @ 566 |
|  | workflow_engine/feature_paths.py | engines-10 @ 85 |
|  | workflow_engine/reconciliation.py | engines-41 @ 375, engines-42 @ 379 |
|  | workflow_engine/router.py | engines-54 @ 358, engines-57 @ 437 |
|  | workflow_engine/secretary_intelligence.py | engines-61 @ 501 |
|  | workflow_engine/task_promotion.py | engines-36 @ 309, engines-38 @ 383 |
|  | reconciliation_orchestrator/entity_status.py | engines-87 @ 190 |
|  | mcp/entity_server.py | MCPE-3 @ 258, MCPE-4 @ 316, MCPE-7 @ 973, MCPE-8 @ 1012, MCPE-9 @ 1045, synth-2 @ 1147, MCPE-12 @ 1253, MCPE-16 @ 1315, MCPE-14 @ 1499, MCPE-15 @ 1544 |
|  | mcp/workflow_state_server.py | MCPW-21* @ 412, MCPW-7 @ 1015, MCPW-5 @ 1124, MCPW-8 @ 1182, MCPW-11 @ 1236, MCPW-13 @ 1381, MCPW-15 @ 1441, MCPW-16 @ 1470, MCPW-19 @ 1576, MCPW-1 @ 2126, MCPW-25 @ 2361, MCPW-32 @ 2523, MCPW-41 @ 2770 |
|  | ui/mermaid.py | UI-10 @ 38 |
|  | ui/routes/entities.py | UI-6 @ 170, UI-7 @ 182 |
|  | ui/templates/_card.html | UI-3 @ 1 |
|  | ui/templates/_entities_content.html | UI-5 @ 73 |
|  | ui/templates/entity_detail.html | UI-9 @ 83 |
|  | scripts/cleanup_backlog.py | SCR-3 @ 253 |
|  | scripts/parse_backlog_md.py | SCR-4 @ 229 |
|  | hooks/session-start.sh | HOOK-3 @ 62 |
|  | commands/cleanup-backlog.md | MD-4 @ 8 |
|  | commands/show-lineage.md | MD-17 @ 11 |
|  | skills/workflow-transitions/SKILL.md | MD-24 @ 21 |
| phase_events (41) | entity_registry/database.py | schema-13 @ 1460, schema-14 @ 3363, schema-15 @ 4590, schema-16 @ 5758, schema-17 @ 5973, schema-19 @ 6078, fill-1 @ 6293, schema-49 @ 6593, schema-42 @ 7686, schema-43 @ 7895, schema-41 @ 8680, schema-26 @ 9734, schema-30 @ 9831, schema-31 @ 9869 |
|  | entity_registry/dependencies.py | engines-72* @ 185 |
|  | entity_registry/rebuild_tool.py | schema-77 @ 303, schema-79 @ 977 |
|  | mcp/entity_server.py | MCPE-5 @ 541, MCPE-6 @ 812, MCPE-10* @ 1082, MCPE-11 @ 1226, MCPE-13 @ 1353 |
|  | mcp/workflow_state_server.py | MCPW-20 @ 838, MCPW-10 @ 1200, MCPW-18 @ 1497, MCPW-30 @ 1724, MCPW-23 @ 2264, MCPW-24 @ 2304, MCPW-35 @ 2578, MCPW-42 @ 2797, MCPW-43 @ 2871, fill-2 @ 2992 |
|  | scripts/pd_state_diff.py | SCR-2 @ 142 |
|  | scripts/dev/cutover-prepass.sql | SCR-11 @ 14 |
|  | commands/abandon-feature.md | MD-1 @ 12 |
|  | commands/cleanup-brainstorms.md | MD-3* @ 25 |
|  | commands/create-project.md | MD-6 @ 17 |
|  | commands/implement.md | MD-8 @ 12 |
|  | commands/secretary.md | MD-16 @ 15 |
|  | skills/decomposing/SKILL.md | MD-21 @ 8 |
|  | skills/retrospecting/SKILL.md | MD-15 @ 13 |
| entity write by type_id (18) | entity_registry/dependencies.py | engines-71* @ 184 |
|  | entity_registry/display.py | engines-83 @ 123 |
|  | entity_registry/server_helpers.py | engines-75 @ 311, engines-79 @ 517 |
|  | workflow_engine/engine.py | engines-4 @ 222 |
|  | workflow_engine/entity_engine.py | engines-15 @ 388, engines-16 @ 415, engines-19 @ 475, engines-22 @ 711 |
|  | workflow_engine/feature_lifecycle.py | engines-25 @ 157, engines-29 @ 294, engines-34* @ 577 |
|  | workflow_engine/reconciliation.py | engines-47* @ 690 |
|  | workflow_engine/rollup.py | engines-51* @ 196, engines-52* @ 267, engines-53* @ 373 |
|  | workflow_engine/router.py | engines-59 @ 480 |
|  | doctor/fix_actions/__init__.py | engines-93 @ 51 |
| migration (12) | entity_registry/database.py | schema-1 @ 378, schema-3 @ 514, schema-4 @ 750, schema-5 @ 1200, schema-6 @ 1328, schema-7 @ 2039, schema-12 @ 2776, schema-20 @ 5915, schema-22 @ 5943, schema-21 @ 11001 |
|  | entity_registry/rebuild_tool.py | schema-76 @ 76 |
|  | entity_registry/schema_v2.py | schema-74 @ 41 |
| events (5) | entity_registry/database.py | schema-71 @ 11144 |
|  | entity_registry/events.py | schema-69 @ 76, schema-70 @ 102 |
|  | entity_registry/rebuild_tool.py | schema-80 @ 906 |
|  | scripts/seed-census-db.py | SCR-12 @ 116 |
| trigger (3) | entity_registry/database.py | schema-2 @ 433, schema-8 @ 2061, schema-9 @ 2077 |
| view (3) | entity_registry/database.py | schema-23 @ 6170 |
|  | entity_registry/axes.py | schema-73 @ 125 |
|  | entity_registry/views.py | schema-72 @ 86 |
| entity list feeding a type_id write (3) | entity_registry/backfill.py | engines-65* @ 254 |
|  | workflow_engine/reconciliation.py | engines-46* @ 618 |
|  | reconciliation_orchestrator/dependency_freshness.py | engines-89* @ 25 |
| index (2) | entity_registry/database.py | schema-10 @ 441, schema-18 @ 1525 |
| entity_tags (1) | entity_registry/database.py | schema-59 @ 862 |
| entity_okr_alignment (1) | entity_registry/database.py | schema-60 @ 894 |
| entity_relations (1) | entity_registry/database.py | schema-61 @ 5592 |
| entity_display (1) | entity_registry/database.py | schema-62 @ 4130 |
| cross_workspace_allowlist (1) | entity_registry/database.py | schema-63 @ 5435 |
| sequences (1) | entity_registry/database.py | schema-64 @ 1092 |
| entities_fts (1) | entity_registry/database.py | schema-65 @ 480 |
| projects (1) | entity_registry/database.py | schema-67 @ 1073 |
| migration_audit_log (1) | entity_registry/database.py | schema-68 @ 4146 |
| guard (no table access) (1) | doctor/check_status_write_path.py | engines-94 @ 28 |

### 5.5 Sites Phase 1 adds (not in the inventory: they do not exist at `77f06efb`)

- **`create_workflow_phase(type_id, *, workspace_uuid=None, ...)`** resolves with `_resolve_identifier(type_id, workspace_uuid=...)` and inserts `type_id`, `workspace_uuid` and `uuid` explicitly; `upsert_workflow_phase` does the same and refuses another workspace's row (W2.1, design:263-270).
- **`activate_feature` seeds the row** inside one `db.transaction()` through W2.1, with the caller's workspace (W2.5, design:285-291). The engines survey notes this is a new `create_workflow_phase` caller.
- **The orchestrator's new Task 2** calls `_recover_pending_cascades(db, workspace_uuid)` directly; rollup writes and `_evaluate_and_flip` write by uuid (W1.7, design:227-234).
- **The `update_entity` MCP tool gains `archived`** and calls `db.set_archived(<resolved uuid>, archived)` (W1.2, design:178; see open question 1).
- **New test files** named by plan 1A item 6 (plan:147-151): `mcp/test_create_feature_lanes.py`, `entity_registry/test_workflow_phase_writers.py`, `mcp/test_projection_names_directory.py`, `entity_registry/test_backfill_scoped.py`.

## 6. Unscoped entity reads by type_id that survive Phase 1

### 6.1 The design's "39 unscoped `get_entity` reads", line by line

`git grep -n -E '\.get_entity\(' -- '*.py'`, production files only, gives 39 lines. The row column names the row that records the call (an exact line match first, else the row whose range contains it).

| # | file:line | kind | row | Phase 1 | reached from (row's `reached_from`, cut) |
|---|---|---|---|---|---|
| 1 | entity_registry/frontmatter_inject.py:160 | type_id | engines-80 | unchanged | skills/workflow-transitions/SKILL.md:28 (frontmatter_inject.py CLI at every phase-exit commit) |
| 2 | entity_registry/frontmatter_sync.py:104 | docstring | none | n/a | n/a |
| 3 | entity_registry/frontmatter_sync.py:149 | docstring | none | n/a | n/a |
| 4 | entity_registry/frontmatter_sync.py:236 | type_id | engines-81 | unchanged | MCP reconcile_frontmatter single-feature (workflow_state_server.py:1920), scan_all (:586) <- MCP reconcile_fr… |
| 5 | entity_registry/frontmatter_sync.py:336 | type_id | engines-82 | unchanged | backfill_headers (:534, which lists every workspace's features unscoped at :518) <- frontmatter_sync_cli back… |
| 6 | entity_registry/frontmatter_sync.py:452 | uuid argument | none (engines: "uuid-keyed") | n/a | n/a |
| 7 | entity_registry/server_helpers.py:257 | type_id | engines-73 | unchanged | MCP register_entity (entity_server.py:542 -> :677; /pd:add-to-backlog, /pd:create-feature, /pd:create-project… |
| 8 | entity_registry/server_helpers.py:265 | type_id | engines-74 | unchanged | unreachable from MCP: the only production call passes parent_type_id=None (entity_server.py:679 'parent_type_… |
| 9 | entity_registry/server_helpers.py:317 | type_id | engines-76 | unchanged | MCP register_entity (entity_server.py:542 -> :677; /pd:add-to-backlog, /pd:create-feature, /pd:create-project… |
| 10 | entity_registry/server_helpers.py:329 | type_id | engines-77 | unchanged | unreachable from MCP: the only production call passes parent_type_id=None (entity_server.py:679 'parent_type_… |
| 11 | reconciliation_orchestrator/entity_status.py:77 | type_id | engines-85 | deleted (W1.1) | session start: session-start.sh run_reconciliation -> reconciliation_orchestrator/__main__.py Task 1 (:116-12… |
| 12 | reconciliation_orchestrator/entity_status.py:190 | type_id | engines-87 | unchanged | session start: session-start.sh run_reconciliation -> reconciliation_orchestrator/__main__.py Task 1 (:116-12… |
| 13 | workflow_engine/engine.py:599 | type_id | engines-7 | deleted (W1.5) | get_state's fall-through when no row exists (engine.py:105), so every get_state caller: MCP get_phase (workfl… |
| 14 | workflow_engine/feature_lifecycle.py:155 | type_id | engines-24 | unchanged | init_feature_state (:249, only when brainstorm_source is given) <- MCP init_feature_state (workflow_state_ser… |
| 15 | workflow_engine/feature_lifecycle.py:258 | type_id | engines-28 | unchanged | MCP init_feature_state (workflow_state_server.py:2554 -> _process_init_feature_state :1949); no command/skill… |
| 16 | workflow_engine/feature_lifecycle.py:566 | type_id | engines-33 | changed (W2.5) | MCP activate_feature (workflow_state_server.py:2612 -> :2014); /pd:create-feature step 5 and the workflow-sta… |
| 17 | workflow_engine/reconciliation.py:375 | type_id | engines-41 | unchanged | check_workflow_drift (reconciliation.py:752 single, :800 bulk) <- MCP reconcile_check (workflow_state_server.… |
| 18 | workflow_engine/router.py:358 | type_id | engines-54 | unchanged | MCP init_entity_workflow (workflow_state_server.py:2627 -> :2037); /pd:add-to-backlog step 4 (commands/add-to… |
| 19 | workflow_engine/router.py:437 | type_id | engines-57 | unchanged | MCP transition_entity_phase (workflow_state_server.py:2647 -> :2050); no command/skill/agent names the tool |
| 20 | workflow_engine/secretary_intelligence.py:501 | type_id | engines-61 | unchanged | CLI `python -m workflow_engine.secretary_intelligence parent-context` (:683, :728); no command, skill, agent… |
| 21 | workflow_engine/task_promotion.py:309 | type_id | engines-36 | unchanged | MCP promote_task (workflow_state_server.py:2702 -> :2716); no command/skill/agent names the tool; 0 live task… |
| 22 | workflow_engine/task_promotion.py:383 | type_id | engines-38 | unchanged | MCP promote_task (workflow_state_server.py:2702 -> :2716); no command/skill/agent names the tool; 0 live task… |
| 23 | mcp/entity_server.py:400 | type_id | MCPE-12 | unchanged | MCP tools add_entity_tag, get_entity_tags (no markdown caller found) |
| 24 | mcp/entity_server.py:469 | type_id | MCPE-14 | unchanged; related W3.4 | MCP tool create_key_result (no markdown caller found) |
| 25 | mcp/entity_server.py:1037 | type_id | MCPE-8 | unchanged | MCP tool get_entity; markdown: show-lineage.md:12 (ref="feature:{id}"), show-status.md:12 |
| 26 | mcp/entity_server.py:1304 | type_id | MCPE-12 | unchanged | MCP tools add_entity_tag, get_entity_tags (no markdown caller found) |
| 27 | mcp/workflow_state_server.py:436 | type_id | MCPW-21 | changed (W2.2) | MCPW-11's five callers (transition_phase, complete_phase, init_feature_state, activate_feature, reproject_met… |
| 28 | mcp/workflow_state_server.py:1052 | type_id | MCPW-7 | unchanged | MCP tool transition_phase (phase_timing merge, kind, started_at) |
| 29 | mcp/workflow_state_server.py:1124 | type_id | MCPW-5 | unchanged | MCP tool transition_phase |
| 30 | mcp/workflow_state_server.py:1162 | type_id | MCPW-7 | unchanged | MCP tool transition_phase (phase_timing merge, kind, started_at) |
| 31 | mcp/workflow_state_server.py:1245 | type_id | MCPW-7 | unchanged | MCP tool transition_phase (phase_timing merge, kind, started_at) |
| 32 | mcp/workflow_state_server.py:1284 | type_id | MCPW-22 | changed (W2.3) | MCP tool complete_phase when phase == 'finish' (1639-1644) |
| 33 | mcp/workflow_state_server.py:1413 | type_id | MCPW-14 | unchanged; related W1.5 | MCP tool complete_phase |
| 34 | mcp/workflow_state_server.py:1441 | type_id | MCPW-15 | unchanged | MCP tool complete_phase |
| 35 | mcp/workflow_state_server.py:1624 | type_id | MCPW-15 | unchanged | MCP tool complete_phase |
| 36 | mcp/workflow_state_server.py:1752 | type_id | MCPW-30 | unchanged; related W1.4 | MCP tools reconcile_check (1844) and reconcile_apply (1879) |
| 37 | mcp/workflow_state_server.py:2291 | type_id | MCPW-23 | unchanged | MCP tool record_mini_spec(feature_type_id\|ref); markdown: create-feature.md:22 |
| 38 | mcp/workflow_state_server.py:2821 | type_id | MCPW-42 | unchanged | MCP tool record_backward_event(type_id); markdown: workflow-transitions/SKILL.md:18, secretary.md:29 |
| 39 | ui/routes/entities.py:170 | type_id | UI-6 | unchanged | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), route GET /entities/{… |

- **Totals:** 36 call lines take a type_id (a few take a value that may also be a uuid: `task_promotion.py:309` `feature_ref`, `ui/routes/entities.py:170` `identifier`, `frontmatter_sync.py:236` `lookup_key`); 1 passes a uuid; 2 are docstring lines. So "39" counts 3 lines that are not type_id reads.
- **After Phase 1:** 34 of the 36 type_id call lines survive; 2 are deleted (engine.py:599 by W1.5, entity_status.py:77 by W1.1).
- `get_entity` has no workspace parameter (database.py:8212-8245, schema-52): it returns None when two workspaces hold the type_id, and None for a soft-deleted entity unless `include_deleted`.

### 6.2 Always unscoped after Phase 1 (`never`)

Scope is the row's `workspace_scoped` at `77f06efb`, except where Phase 1 changes a surviving read's scope: then `workspace_scoped_after_phase1` decides. Only schema-32 has it; W2.1 moves it from 6.2 to 6.3 (section 10.3).

| id | file:line | symbol | key_used | scope | reached_from | Phase 1 |
|---|---|---|---|---|---|---|
| schema-52 | entity_registry/database.py:8212-8245 | EntityDatabase.get_entity | uuid \| type_id | never (no workspace parameter) | 39 production call lines (workflow_state_server.py 12, frontmatter_sync.py 5, entity_server.py 4, server_helpers.py 4, feature_lifecycle.py 3, others) | unchanged |
| schema-56 | entity_registry/database.py:8247-8277 | EntityDatabase.feature_entity_id | type_id | never (by design) | workflow_engine/feature_paths.py:85 (feature_dir_name) | unchanged; related W2.2,W2.4 |
| engines-80 | entity_registry/frontmatter_inject.py:160 | main | type_id | never | skills/workflow-transitions/SKILL.md:28 (frontmatter_inject.py CLI at every phase-exit commit) | unchanged |
| engines-81 | entity_registry/frontmatter_sync.py:236 | detect_drift | type_id when given, else the header's entity_uuid | never | MCP reconcile_frontmatter single-feature (workflow_state_server.py:1920), scan_all (:586) <- MCP reconcile_frontmatter bulk and reconcile_status (their listing is worksp… | unchanged |
| engines-82 | entity_registry/frontmatter_sync.py:336 | stamp_header | type_id | never | backfill_headers (:534, which lists every workspace's features unscoped at :518) <- frontmatter_sync_cli backfill; frontmatter_sync_cli stamp; run_backfill(header_aware=… | unchanged |
| engines-73 | entity_registry/server_helpers.py:257 | _process_register_entity | type_id | never | MCP register_entity (entity_server.py:542 -> :677; /pd:add-to-backlog, /pd:create-feature, /pd:create-project, decomposing skill), and issue_spawn (:814) / create_key_re… | unchanged |
| engines-74 | entity_registry/server_helpers.py:265 | _process_register_entity | type_id | never | unreachable from MCP: the only production call passes parent_type_id=None (entity_server.py:679 'parent_type_id removed (FR-13 AC)'); test-only | unchanged |
| engines-76 | entity_registry/server_helpers.py:317 | _process_register_entity | type_id | never | MCP register_entity (entity_server.py:542 -> :677; /pd:add-to-backlog, /pd:create-feature, /pd:create-project, decomposing skill), and issue_spawn (:814) / create_key_re… | unchanged |
| engines-77 | entity_registry/server_helpers.py:329 | _process_register_entity | type_id | never | unreachable from MCP: the only production call passes parent_type_id=None (entity_server.py:679 'parent_type_id removed (FR-13 AC)'); test-only | unchanged |
| engines-78 | entity_registry/server_helpers.py:484 | _process_get_lineage | type_id | never | MCP get_lineage (entity_server.py:1046 -> :1079, after _resolve_ref_param turns a ref into a type_id); /pd:show-lineage (commands/show-lineage.md:13) | unchanged |
| engines-24 | workflow_engine/feature_lifecycle.py:155 | _promote_brainstorm | type_id (composed 'brainstorm:{stem}' from a path) | never | init_feature_state (:249, only when brainstorm_source is given) <- MCP init_feature_state (workflow_state_server.py:2554 -> _process_init_feature_state :1949); no comman… | unchanged |
| engines-28 | workflow_engine/feature_lifecycle.py:258 | init_feature_state | type_id | never | MCP init_feature_state (workflow_state_server.py:2554 -> _process_init_feature_state :1949); no command/skill/agent names the tool (pygrep over plugins/pd/commands, skil… | unchanged |
| engines-33 | workflow_engine/feature_lifecycle.py:566 | activate_feature | type_id | never | MCP activate_feature (workflow_state_server.py:2612 -> :2014); /pd:create-feature step 5 and the workflow-state skill's 'Activating a planned feature' (SKILL.md:18) | changed (W2.5) |
| engines-10 | workflow_engine/feature_paths.py:85 | feature_dir_name | type_id | never, by design: EntityDatabase.feature_entity_id runs `SELECT DISTINCT entity_id FROM e… | engine._feature_dir_name (engine.py:403; from transition_phase :140, validate_prerequisites :250), engine._hydrate_from_meta_json (:608), feature_lifecycle._validate_fea… | unchanged; related W2.2,W2.4 |
| engines-41 | workflow_engine/reconciliation.py:375 | _check_single_feature | type_id | never | check_workflow_drift (reconciliation.py:752 single, :800 bulk) <- MCP reconcile_check (workflow_state_server.py:2491 -> :1837, passes workspace), MCP reconcile_status (:… | unchanged |
| engines-42 | workflow_engine/reconciliation.py:379 | _check_single_feature | type_id | never | check_workflow_drift (reconciliation.py:752 single, :800 bulk) <- MCP reconcile_check (workflow_state_server.py:2491 -> :1837, passes workspace), MCP reconcile_status (:… | unchanged |
| engines-54 | workflow_engine/router.py:358 | init_entity_workflow | type_id (a uuid is also accepted) | never | MCP init_entity_workflow (workflow_state_server.py:2627 -> :2037); /pd:add-to-backlog step 4 (commands/add-to-backlog.md:14); one-off scripts/c22_recreate_live_remainder… | unchanged |
| engines-57 | workflow_engine/router.py:437 | transition_entity_phase | type_id (':' required at :434) | never | MCP transition_entity_phase (workflow_state_server.py:2647 -> :2050); no command/skill/agent names the tool | unchanged |
| engines-61 | workflow_engine/secretary_intelligence.py:501 | get_parent_context | type_id | never | CLI `python -m workflow_engine.secretary_intelligence parent-context` (:683, :728); no command, skill, agent or hook in plugins/ invokes it (pygrep finds only the module… | unchanged |
| engines-36 | workflow_engine/task_promotion.py:309 | promote_task | type_id or uuid (feature_ref) | never | MCP promote_task (workflow_state_server.py:2702 -> :2716); no command/skill/agent names the tool; 0 live task entities | unchanged |
| engines-38 | workflow_engine/task_promotion.py:383 | promote_task | type_id | never | MCP promote_task (workflow_state_server.py:2702 -> :2716); no command/skill/agent names the tool; 0 live task entities | unchanged |
| engines-87 | reconciliation_orchestrator/entity_status.py:190 | _sync_brainstorm_entities (Part 1) | type_id (composed 'brainstorm:{stem}') | never | session start: session-start.sh run_reconciliation -> reconciliation_orchestrator/__main__.py Task 1 (:116-122) -> entity_status.sync_entity_statuses (workspace_uuid is… | unchanged |
| MCPE-8 | mcp/entity_server.py:1012-1042 | get_entity | type_id | never for the final read (a ref is resolved in the server's project first, then reduced t… | MCP tool get_entity; markdown: show-lineage.md:12 (ref="feature:{id}"), show-status.md:12 | unchanged |
| MCPE-9 | mcp/entity_server.py:1045-1079 (server_helpers.py:458-497) | get_lineage / _process_get_lineage | type_id | never (db.get_lineage called with no project_id/workspace) | MCP tool get_lineage; markdown: show-lineage.md:13 | unchanged |
| MCPE-12 | mcp/entity_server.py:1253-1312 (handler 398-405) | add_entity_tag / get_entity_tags | type_id | never for the final read | MCP tools add_entity_tag, get_entity_tags (no markdown caller found) | unchanged |
| MCPW-21 | mcp/workflow_state_server.py:412-596 (reads at 436, 507; di… | _project_meta_json | type_id | never | MCPW-11's five callers (transition_phase, complete_phase, init_feature_state, activate_feature, reproject_meta_json) | changed (W2.2) |
| MCPW-5 | mcp/workflow_state_server.py:1124 | _process_transition_phase | type_id | never | MCP tool transition_phase | unchanged |
| MCPW-11 | mcp/workflow_state_server.py:1236, 1617, 1966, 2022, 1694 | _process_transition_phase / _process_complete_phase / _proc… | type_id | never | MCP tools transition_phase, complete_phase, init_feature_state, activate_feature, reproject_meta_json (post-commit projection) | unchanged; related W2.2; own lines unch… |
| MCPW-15 | mcp/workflow_state_server.py:1441-1448, 1624 | _process_complete_phase | type_id | never | MCP tool complete_phase | unchanged |
| MCPW-1 | mcp/workflow_state_server.py:2126-2161 | _resolve_ref_to_feature_type_id | type_id (an explicit feature_type_id is returned with no lookup); ref… | never | every workflow tool with a feature_type_id/type_id/ref parameter: get_phase, transition_phase, complete_phase, record_mini_spec, get_mini_spec, validate_prerequisites, r… | unchanged |
| MCPW-25 | mcp/workflow_state_server.py:2361-2380 (handler 1669-1700) | reproject_meta_json / _process_reproject_meta_json | type_id (ref resolved unscoped by MCPW-1) | never | MCP tool reproject_meta_json; markdown: abandon-feature.md:18 (ref="feature:{id}-{slug}") | unchanged; related W2.2; own lines unch… |
| MCPW-41 | mcp/workflow_state_server.py:2770-2789 | get_progress_view | ref -> uuid (db.resolve_ref, unscoped) | never | MCP tool get_progress_view (no markdown caller found) | unchanged |
| UI-10 | ui/mermaid.py:38-85 (nodes 43-54, edges 57-60, click 63-67) | build_mermaid_dag | type_id (node dict keyed by type_id, node ids hashed from type_id, ed… | never | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), detail page lineage graph | unchanged |
| UI-6 | ui/routes/entities.py:170 | entity_detail | uuid or type_id (the path identifier) | never (db.get_entity has no workspace parameter) | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), route GET /entities/{identifier} | unchanged |
| UI-7 | ui/routes/entities.py:182-188 | entity_detail (lineage) | type_id (entity['type_id'] re-used after the entity was found) | never | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), route GET /entities/{identifier} | unchanged; related W3.2 |
| UI-3 | ui/templates/_card.html:1 | board card link | type_id (href /entities/{{ item.type_id }}) | never | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), board cards -> GET /entities/{identifier} (UI-6) | unchanged |
| UI-5 | ui/templates/_entities_content.html:73 | entity list link | type_id (href /entities/{{ entity.type_id }}) | never | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), Entities page rows -> GET /entities/{identifier} | unchanged |
| UI-9 | ui/templates/entity_detail.html:83, 98 | ancestor and child links | type_id (href /entities/{{ a.type_id }} and {{ c.type_id }}) | never | UI server (hooks/start-ui-server.sh:63 launches mcp/run-ui-server.sh at session start), detail page lineage lists | unchanged |
| MD-17 | commands/show-lineage.md:11-13 | /pd:show-lineage steps 1-3 | type_id ("feature:{id}-{slug}", "project:{id}", "backlog:{id}", "brai… | never for the final reads (MCPE-8, MCPE-9) | command /pd:show-lineage | unchanged |
| MD-24 | skills/workflow-transitions/SKILL.md:21-30 | Phase exit step 1 (frontmatter injection) | type_id ("feature:{id}-{slug}" argv to frontmatter_inject.py) | never (frontmatter_inject.py:160 db.get_entity(feature_type_id)) | skill workflow-transitions phase exit, per artifact | unchanged |

40 rows.

### 6.3 Unscoped on some paths after Phase 1 (`optional`)

| id | file:line | symbol | key_used | scope | reached_from | Phase 1 |
|---|---|---|---|---|---|---|
| schema-50 | entity_registry/database.py:6980-7056 | EntityDatabase._resolve_identifier | uuid \| type_id+workspace_uuid \| type_id | optional (scoped when workspace_uuid or project_id is given) | get_entity, update_entity, delete_entity, set_parent, reparent_entity, get_lineage, export_lineage_markdown; backfill.py:899 | unchanged; related W2.1 |
| schema-54 | entity_registry/database.py:7177-7253 (exact match 7225-723… | EntityDatabase.resolve_ref | uuid \| type_id(+workspace_uuid) \| type_id prefix | optional | entity_server.py:338/356/1022/1339/1340/1377/1378/1464/1465/1486, workflow_state_server.py:2157/2783, database.py:7797 (register_entity depends_on_features, scoped), fea… | unchanged |
| schema-57 | entity_registry/database.py:7280-7322 | EntityDatabase.search_by_type_id_prefix | type_id prefix (+workspace_uuid) | optional | resolve_ref prefix branch; entity tools (other areas) | unchanged |
| schema-58 | entity_registry/database.py:7981-7990, 8160-8162, 8377-8381… | set_parent / reparent_entity / get_lineage / export_lineage… | type_id (+workspace_uuid optional) | optional | MCP set_parent / reparent / lineage / export tools (other areas) | unchanged; related W3.4 |
| synth-1 | entity_registry/database.py:8506-8560 (resolution 8557-8559) | EntityDatabase.update_entity (identifier resolution) | uuid \| type_id+workspace_uuid (workspace_uuid, or legacy project_id)… | optional: scoped when workspace_uuid or project_id is passed; without either, _resolve_id… | every update_entity caller in this inventory (engines rows whose object is 'entities (write by type_id)', MCP update_entity MCPE-10, workflow handlers MCPW-8 and MCPW-16… | unchanged; related W1.2,W1.7 |
| schema-44 | entity_registry/database.py:8967-9119 (soft delete 9083-908… | EntityDatabase.delete_entity | type_id+workspace_uuid (optional), or uuid | optional (unscoped type_id must be globally unique) | MCP delete_entity tool (entity_server.py _process_delete_entity) | unchanged; related W3.4 |
| schema-29 | entity_registry/database.py:9786-9827 (fallback 9811-9815) | EntityDatabase.append_phase_event step 6 (v2 dual-write) | type_id+workspace_uuid, else type_id | optional (scoped when workspace_uuid is passed; unscoped .fetchone() otherwise) | every append on a v2 file except mini_spec | unchanged |
| schema-32 | entity_registry/database.py:9992-9996 | EntityDatabase.create_workflow_phase (entity lookup) | type_id | after Phase 1: optional: W2.1 resolves with _resolve_identifier(type_id, workspace_uuid=w… | feature_lifecycle.py:305 (init_feature_state), task_promotion.py:403 (promote_task), engine.py:633 (hydration; W1.5 deletes), reconciliation.py:495 (W1.3 deletes) | changed (W2.1) |
| MCPE-4 | mcp/entity_server.py:316-360 | _resolve_ref_param | type_id (explicit type_id returned unchanged); ref -> db.resolve_ref(… | optional: a ref is resolved in the server's legacy project (project_id=_effective_project… | entity tools set_parent, get_entity, get_lineage, update_entity, delete_entity, add_entity_tag, get_entity_tags, create_key_result, update_kr_score | unchanged; related W3.4 |
| MCPE-7 | mcp/entity_server.py:973-1009 (server_helpers.py:499-520) | set_parent / _process_set_parent | type_id (child: type_id\|ref; parent: parent_type_id\|parent_ref) | optional (child ref resolved in the server's legacy project; parent ref and both explicit… | MCP tool set_parent; markdown: create-project.md:19 (brainstorm under its backlog entity) | unchanged; related W3.4 |
| synth-2 | mcp/entity_server.py:1147-1180 (project_id at 1174); helper… | export_lineage_markdown MCP tool -> _process_export_lineage… | type_id (or uuid) + legacy project_id when given | optional: `resolved_project_id = None if project_id == "*" else _effective_project_id(pro… | MCP export_lineage_markdown (entity server); /pd:show-lineage is recorded as MD-17 | unchanged |
| MCPE-16 | mcp/entity_server.py:1315-1350, 1447-1491 (scope helper 165… | add_dependency / add_okr_alignment / get_okr_alignments | ref -> uuid (db.resolve_ref(ref, project_id=_effective_project_id())) | optional: scoped to the server's legacy project; _effective_project_id returns None (all… | MCP tools add_dependency, add_okr_alignment, get_okr_alignments (no markdown caller found) | unchanged |
| MCPE-14 | mcp/entity_server.py:1499-1541 (handler 453-509) | create_key_result / _process_create_key_result | parent_ref -> type_id (scoped ref) -> get_entity(parent_type_id) unsc… | optional (ref scoped; parent re-read unscoped; registration workspace from the server's l… | MCP tool create_key_result (no markdown caller found) | unchanged; related W3.4 |
| MCPW-7 | mcp/workflow_state_server.py:1015-1052 (fed by the unscoped… | _transitioned_entity_row | type_id+workspace_uuid when _workspace_uuid is set (db.resolve_entity… | optional (scoped only when the server resolved a workspace) | MCP tool transition_phase (phase_timing merge, kind, started_at) | unchanged |
| MCPW-32 | mcp/workflow_state_server.py:2523-2535 (handler 1896-1931) | reconcile_frontmatter / _process_reconcile_frontmatter | type_id | optional: scan_all(workspace_uuid=) scoped; the single-feature path is unscoped | MCP tool reconcile_frontmatter (no markdown caller found) | unchanged |

15 rows.

### 6.4 How the unscoped lookups settle a type_id two workspaces hold

From the schema survey's identity table and probes on copies (`probe_shared_type_id.out`):

| Lookup | Row | Two holders | Soft-deleted namesake |
|---|---|---|---|
| `_resolve_identifier` (:6980) | schema-50 | scoped: that workspace's entity; unscoped: `ValueError` "Ambiguous" | still counted, so an unscoped lookup stays ambiguous |
| `get_entity` (:8212) | schema-52 | None (swallows "Ambiguous") | None unless `include_deleted` |
| `resolve_ref` (:7177) | schema-54 | unscoped exact match: the first row (lowest rowid), no error | the type_id branch returns deleted rows |
| `feature_entity_id` (:8247) | schema-56 | one answer if the namesakes agree, else `feature_not_found` | not filtered |
| `create_workflow_phase` lookup (:9993) | schema-32 | lowest rowid (SCAN entities) | |
| `append_phase_event` step 6 fallback (:9813) | schema-29 | lowest rowid (SCAN entities) | |
| `wp_autofill_workspace_uuid` | schema-8 | smallest `workspace_uuid` | |

These picks depend on the query plan; no contract guarantees them. Unscoped entity **writes** by type_id that survive are the `entity write by type_id` rows in section 5.4; `set_archived` with no workspace and the doctor's `UPDATE entities SET parent_uuid = NULL WHERE type_id = ?` reach every namesake at once (engines-84, 88, 93, SCR-3), while `update_entity(type_id)` without scope raises "Ambiguous".

## 7. Tests

### 7.1 Scope and totals

- **Scanned:** 144 `test_*.py` and `conftest.py` files (tests survey, AST). The synthesizer's AST count (`synth-work/count_tests.py`) reproduces every total below.
- **Shell tests (completeness round):** every `.sh` under `plugins/pd` and `scripts/` that names either table or a registry API: `hooks/tests/test-workflow-regression.sh` is fill-3, `hooks/tests/test-sqlite-concurrency.sh:158` joins tests-72, `scripts/test_migrate_bash.sh` is TST-3, and `scripts/dev/check_fr_c_115_atomicity*.sh` only grep git diffs. The totals below cover the `.py` files only.
- **Raw SQL:** 41 files run raw SQL on the two tables.
  - `workflow_phases`: 130 statements (127 string literals; the DDL script at `scripts/test_migrate_db.py:765` holds 4).
  - Its 57 INSERTs: 38 name only `type_id` (the autofill trigger fills `workspace_uuid`, `uuid` stays NULL), 17 add `workspace_uuid`, 2 add `uuid` (`test_migration_13_safety.py:432`, `test_rebuild_tool.py:204`).
  - `phase_events`: 111 statements, all naming `type_id` and the legacy `project_id`.
- **API calls (calls, files):** `create_workflow_phase` 277 in 25 (0 pass a workspace), `get_workflow_phase` 147 in 14, `list_workflow_phases` 31 in 5 (10 scoped), `upsert_workflow_phase` 23 in 4 (5 pass a workspace), `update_workflow_phase` 22 in 7 (2 pass a workspace), `delete_workflow_phase` 4 in 1, `append_phase_event` 63 in 6 (8 pass `workspace_uuid`, 61 `project_id`), `query_phase_events` 48 in 9, `query_phase_events_bulk` 3 in 1; `register_entity` 1206 in 72 (each appends an `entity_created` phase event).
- **Where schemas come from:**
  - `EntityDatabase(path)`, the fresh v1 chain: `EntityDatabase(` appears 461 times in 83 files; 44 files define their own `db` fixture;
  - `rebuild_tool.build_staging_database`, the v2 generation: 28 calls in 8 files (the `v2_db` fixture in 4);
  - `test_helpers.make_v10_db` / `make_v11_db` / `make_v12_db` (historic): 11 files, 104 references; `make_v12_db` is the newest;
  - hand-written DDL: doctor `_make_db` x2, `scripts/test_migrate_db.py` `create_entity_db`, fix_kanban_columns `_make_db`, `test_database.py` `_build_v7_conn`, `test_search.py:944`.
  - A fresh `EntityDatabase` and the live file have the same 14 DDL objects for the two tables (tests-73; section 2.6).
- **No conftest creates rows.** `hooks/lib/conftest.py` only points `ENTITY_DB_PATH` at a temp file (session autouse); `workflow_engine/conftest.py` and `ui/tests/conftest.py` only edit `sys.path`. Only `hooks/lib` has the conftest that keeps tests off the live registry.

### 7.2 Shared fixtures and helpers

Per-file helpers that funnel most row creation (references, tests-73): `seeded_engine` (test_workflow_state_server.py, 166), `_with_phase` (test_entity_engine.py 97, test_rollup.py 20), `seeded` (test_complete_phase_closes.py 76), `_setup_engine` (test_engine.py 68, test_reconciliation.py 35), `integration_client` (ui test_entities.py 53), `parent_feature` (test_issue_spawn.py 17), `_seed_workflow_row` (test_deepened_app.py 17, test_app.py 12), `_register_feature` (test_task_promotion.py 14), `tool_env` (test_feature_134_trustgate.py 12); `_seed_shared_type_id` (test_c8_workflow_state_kind.py:121) seeds one row for a type_id two workspaces hold.

### 7.3 Tests that pin today's shape

- **Head-schema pins** (they use the `db` fixture, i.e. the HEAD schema, not a migration snapshot):
  - `test_database.py` `TestMigration3.test_type_id_is_primary_key` (:2895-2899, `assert col_map["type_id"][5] == 1`), `test_workflow_phases_has_8_columns`, `TestTriggers` (:590, exact trigger list including the three wp triggers), `TestIndexes` (:619, exact index list), the `enforce_immutable_wp_type_id` test (:2990);
  - `test_v2_migrations.py:284` `assert version == "25"`.
- **Rows no entity holds:** 10 files insert them with an explicit `workspace_uuid` to pass `wp_reject_orphaned_insert` (4 in `test_database.py`: :3619, :3656, :3732, :3786; the doctor tests in hand-written schemas). Readers are pinned to tolerate them (the board query, `list_workflow_phases`' `OR e.uuid IS NULL`, the doctor checks). Live has 0 such rows.
- **One row joined to two entities:** `test_database.py:3745` pins the scoped board query's dedupe for a shared type_id.
- **Guards:**
  - `doctor/test_audit_writes.py` `_KNOWN_INFERENCE_SITES` and `_INVENTORY_HIGH_WATER = 8` (:628) guard reading meaning out of id text;
  - `test_event_sourced_state.py:717` and `doctor/check_status_write_path.py` (:224-231, engines-94) guard which functions write `UPDATE workflow_phases`; neither checks the key a statement uses;
  - a naive probe of production code (tests-work `guard_probe.py`) flags 23 SQL statements and 42 API calls keyed by type_id alone, a floor: f-string SQL splits across constants (database.py:10164, :10289), the scan roots miss `ui/routes` and repo `scripts/`, and `ui/routes/entities.py:24-27`, `:193-194` match rows by `type_id` in Python.
- **Phase-1 effects on tests that the design does not name:**
  - W2.1 refuses the unscoped `create_workflow_phase` for a shared type_id: `test_database.py:3745` (C02) and `test_c8_workflow_state_kind.py` `_seed_shared_type_id` (tests-52);
  - W1.7 disarms `test_dependencies.py:430-435`, whose fault injection matches `update_entity`'s type_id argument (C03);
  - W2.2 breaks the complete_phase case of `hooks/tests/test-workflow-regression.sh` (fill-3): its `artifacts_root` is `{TMPDIR}/features`, so the named directory would be `{TMPDIR}/features/features/999-mock-feature` (inferred, not run). The merge also listed `test_projection_determinism.py` and `test_c9_c12_projection_identity.py:69` here; W2.2 keeps the `feature_dir` parameter and both pass it, so they do not change (section 10.3).

### 7.4 Test files

One row per file. Counts for tests-area rows are parsed from the row (statements on `workflow_phases` / `phase_events`, and wp/pe API calls); schema-only rows count source lines on `events` and the views.

| id | file | tests | wp SQL | pe SQL | wp/pe API | Phase 1 | rekey_needs |
|---|---|---|---|---|---|---|---|
| tests-3 | doctor/test_audit_writes.py |  | 0 | 0 | 0 | unchanged | What it guards: identity-TEXT inference only. scan_roots flags regex/split/slice/startswith on id receivers (names ending entity_id/type_id, eid, tid) and SQL constants matching substr(type_id\|entity_id / instr(... / type_id LIKE '...:' (identity_inference.py… |
| tests-4 | doctor/test_check_status_write_path.py | 5 | 0 | 0 | 0 | unchanged | The audited check greps 'UPDATE workflow_phases' in hooks/lib and mcp and allows only enclosing defs in _PERMITTED_ENCLOSING_DEFS (append_phase_event, upsert/update/create_workflow_phase, update_entity, _v2_migration_5_explicit_archived_flag, check_status_wri… |
| tests-1 | doctor/test_checks.py | 89 | 3 | 0 | 0 | unchanged | The fixture DDL is a hand copy of an old shape, not the migrated schema, so a re-key leaves it green unless doctor check 9's SQL changes; if check 9 starts reading uuid/workspace_uuid, this DDL and the two INSERTs (feature:001, feature:ghost) must gain those… |
| tests-2 | doctor/test_fixer.py | 32 | 3 | 0 | 0 | unchanged | Pins a delete-by-type_id fix. Under a key that allows one row per entity, a type_id can name several rows, so the fix and this test would need the row's own key (uuid) rather than the Issue's type_id text; the fixture's workflow_phase 'ideate' is outside the… |
| schema-102 | entity_registry/test_axes.py |  | 0 lines (wp+pe) | events/views: 14 lines | 0 | unchanged | Raw SQL and fixture calls that name the current key/columns/objects must follow any re-key; counts are the checklist size. |
| tests-25 | entity_registry/test_backfill.py | 128 | 5 | 0 | 43 | changed (W2.6) | Backfill writes rows by type_id and reads them back by type_id (40x); the 'shared type_id's missing row is seeded for the calling workspace' W2 test becomes two rows under a per-entity key. The 4 raw INSERTs pre-create rows by type_id only. |
| tests-26 | entity_registry/test_backfill_parent_uuid.py | 4 | 0 | 0 | 2 | changed (W2.6) | Reads rows by type_id after backfill; one-workspace DB, so unambiguous. |
| tests-14 | entity_registry/test_board_archived_query.py | 4 | 2 | 0 | 8 | unchanged | _add_orphan_row inserts an orphan workflow_phases row (a type_id no entity holds) with an explicit workspace_uuid to pass wp_reject_orphaned_insert; a key that references the entity would make that row unrepresentable, so these tests pin behaviour a per-entit… |
| tests-29 | entity_registry/test_c13_missing_parent_reported.py | 7 | 0 | 0 | 0 | unchanged | run_backfill registers entities (phase_events entity_created rows) and, per workspace, sets workflow_phase='finish' on NULL-phase rows of done entities through update_workflow_phase(type_id, workspace_uuid=...) (backfill.py:206-219); the repair loop keys upda… |
| tests-30 | entity_registry/test_c18_backfill_canonical_identity.py | 5 | 0 | 0 | 0 | unchanged | run_backfill registers entities (phase_events entity_created rows) and, per workspace, sets workflow_phase='finish' on NULL-phase rows of done entities through update_workflow_phase(type_id, workspace_uuid=...) (backfill.py:206-219); the repair loop keys upda… |
| tests-28 | entity_registry/test_c19_c20b_rebuild_structure.py | 17 | 0 | 0 | 0 | unchanged | Goes through rebuild_tool.rebuild/run_backfill; follows whatever the rebuild's workflow_phases import does. |
| schema-106 | entity_registry/test_c22a_reparent_entity.py |  | 0 lines (wp+pe) | events/views: 4 lines | 0 | unchanged | Raw SQL and fixture calls that name the current key/columns/objects must follow any re-key; counts are the checklist size. |
| tests-70 | entity_registry/test_c3_allocation_callers.py | 5 | 0 | 0 | 1 | changed (W2.4) | One row created by type_id as setup; the test's subject is the allocation refusal, not the row. |
| tests-15 | entity_registry/test_c5b_alias_free_callers.py | 7 | 0 | 1 | 0 | unchanged | Asserts phase_events.project_id per registration; if phase_events gains an entity or workspace key, the natural assertion moves to it; the SELECT by type_id is unambiguous in its one-workspace DB. |
| tests-16 | entity_registry/test_c5b_step2_aliases_removed.py | 10 | 0 | 2 | 0 | unchanged | The dump compares whole tables before/after, so a new phase_events column appears in both snapshots; the two project_id SELECTs pin the legacy column. |
| tests-31 | entity_registry/test_cleanup_suffix_parsers.py | 7 | 0 | 0 | 0 | unchanged | run_backfill registers entities (phase_events entity_created rows) and, per workspace, sets workflow_phase='finish' on NULL-phase rows of done entities through update_workflow_phase(type_id, workspace_uuid=...) (backfill.py:206-219); the repair loop keys upda… |
| tests-6 | entity_registry/test_database.py | 476 | 57 | 2 | 153 | changed (W2.1) | Head-schema pins fail by design: TestMigration3.test_type_id_is_primary_key (:2895, asserts table_info pk flag on type_id), test_workflow_phases_has_8_columns (exact column list ending uuid, workspace_uuid), TestTriggers.test_has_nine_triggers (:591, exact li… |
| tests-17 | entity_registry/test_dependencies.py | 33 | 0 | 0 | 5 | changed (W1.7) | Reads cascade events by type_id; for a type_id two workspaces hold, a type_id filter returns both workspaces' events unless phase_events can name the entity or workspace. Its fault-injection test monkeypatches db.update_entity and matches on the first argumen… |
| schema-105 | entity_registry/test_display.py |  | 0 lines (wp+pe) | events/views: 5 lines | 0 | unchanged; related W5.1 | Raw SQL and fixture calls that name the current key/columns/objects must follow any re-key; counts are the checklist size. |
| tests-24 | entity_registry/test_entity_display_table.py | 9 | 0 | 0 | 0 | unchanged | Behaviour flips with the schema: if phase_events gains a column literally named 'uuid', the helper's branch switches from a whole-table dump to 'WHERE uuid = ?' with an entity uuid (:374-377); a column named otherwise (e.g. entity_uuid) keeps the whole-table… |
| tests-12 | entity_registry/test_entity_lifecycle.py | 29 | 1 | 0 | 13 | unchanged | Reads the row by type_id after router calls; the :318 check reads workspace_uuid off the row, which a per-entity key keeps or derives. init_entity_workflow's upsert path is where a key change lands (router.py, other area). |
| tests-71 | entity_registry/test_entity_server.py | 49 | 0 | 0 | 0 | unchanged | Pins that a missing row surfaces as entity_not_found through the MCP error chain; a per-entity key keeps the case (no row for the entity). |
| tests-9 | entity_registry/test_event_sourced_state.py | 10 | 1 | 9 | 5 | unchanged | Guard facts: test_no_direct_workflow_phases_updates greps 'UPDATE workflow_phases' in plugins/pd/hooks/lib and plugins/pd/mcp only (not ui/, not repo scripts/) and allows append_phase_event, upsert/update/create_workflow_phase, update_entity, check_status_wri… |
| schema-103 | entity_registry/test_events.py |  | 0 lines (wp+pe) | events/views: 22 lines | 0 | unchanged | Raw SQL and fixture calls that name the current key/columns/objects must follow any re-key; counts are the checklist size. |
| tests-32 | entity_registry/test_frontmatter_sync.py | 85 | 0 | 0 | 0 | unchanged | run_backfill registers entities (phase_events entity_created rows) and, per workspace, sets workflow_phase='finish' on NULL-phase rows of done entities through update_workflow_phase(type_id, workspace_uuid=...) (backfill.py:206-219); the repair loop keys upda… |
| tests-5 | entity_registry/test_helpers.py | 0 | 0 | 0 | 0 | unchanged | None for the builders themselves: they replay MIGRATIONS up to a fixed N, so a new migration does not change them. A re-key migration's own tests would need a 'head minus one' builder of the same kind (none exists for 24 or 25; make_v12_db is the newest). |
| tests-20 | entity_registry/test_migration_13_safety.py | 11 | 1 | 1 | 0 | unchanged | History (migration 13 up/down). The only seed in the suite that fills workflow_phases.uuid besides test_rebuild_tool.py's. Its down-migration dump compares the three tables byte-for-byte. |
| tests-21 | entity_registry/test_migration_14_safety.py | 14 | 0 | 1 | 0 | unchanged | History; pins v_before/v_after == max(MIGRATIONS) (adapts to a new migration automatically). |
| tests-22 | entity_registry/test_migration_19_safety.py | 5 | 0 | 10 | 0 | unchanged | History, and the closest precedent for a phase_events copy-rename: it checks row ids, indexes (idx_pe_*) and the CHECK after the rebuild. A phase_events re-key migration would need an equivalent test. |
| tests-19 | entity_registry/test_migration_safety.py | 7 | 3 | 4 | 0 | unchanged | History: migration 12 removes the malformed row 'feature:' (:250). A new migration does not change these; a re-key's own safety tests would follow this file's pattern (build head-1, seed, migrate, check foreign_key_check). |
| tests-18 | entity_registry/test_pd_state_diff.py | 7 | 0 | 1 | 0 | unchanged | The helper names type_id and project_id only; it has 0 references, so an entity-key column would only matter if it were used. |
| tests-7 | entity_registry/test_phase_events.py | 33 | 0 | 28 | 23 | unchanged | If phase_events gains an entity key: the migration-10 tests (DDL, idx_pe_lookup/idx_pe_project/idx_pe_timestamp, phase_events_backfill_dedup) pin the table's current columns and indexes; seeded_db registers 3 entities, drops phase_events and re-runs migration… |
| tests-8 | entity_registry/test_phase_events_adversarial.py | 26 | 0 | 13 | 19 | unchanged | Same as test_phase_events.py: raw INSERT INTO phase_events (3) name no entity, and TestBackfillEdgeCases replays migration 10's backfill; an entity-key column that is NOT NULL would need values in these INSERTs. |
| tests-27 | entity_registry/test_rebuild_tool.py | 59 | 2 | 6 | 0 | unchanged | rebuild re-mints entity uuids (uuid7, D2), so a stored workflow_phases.uuid must be remapped on copy (rebuild_tool.py _import_workflow_phases :786-860). Tests compare phase_events rows before/after by table name (dynamic, :1463-1486) and assert the fresh buil… |
| tests-10 | entity_registry/test_register_upsert_split.py | 19 | 1 | 9 | 2 | unchanged | The duplicate-init assertion ('Expected 1 workflow_phases row after duplicate init', :509) counts rows by type_id; under a per-entity key it stays 1 in a one-workspace DB. The raw INSERT INTO phase_events names type_id+project_id only. |
| tests-13 | entity_registry/test_search.py | 72 | 1 | 0 | 0 | unchanged | Scaffolding only: migration 3's table and one hand-written copy exist so later FTS migrations run; no row is read or written. Unaffected unless a new migration step touches workflow_phases on the v3/v7 path it replays. |
| tests-11 | entity_registry/test_status_only_lifecycle.py | 8 | 3 | 0 | 0 | unchanged | Asserts absence of a row by type_id; under an entity key the same absence check would read by the entity's uuid or (workspace, type_id). No inserts. |
| tests-23 | entity_registry/test_v2_migrations.py | 9 | 0 | 10 | 5 | unchanged | Pins the fresh v1-generation schema_version as a literal: test_migration_3_noop_without_events_store asserts version == "25" (:284); a migration added to MIGRATIONS changes it. Other version checks use schema_v2.V2_SCHEMA_VERSION (7) and adapt. |
| schema-104 | entity_registry/test_views.py |  | 0 lines (wp+pe) | events/views: 18 lines | 0 | unchanged | Raw SQL and fixture calls that name the current key/columns/objects must follow any re-key; counts are the checklist size. |
| tests-48 | reconciliation_orchestrator/test_c5b_brainstorm_workspace.py | 3 | 0 | 1 | 0 | unchanged | Pins the legacy project_id on entity_created for session-start brainstorm registration. |
| tests-50 | reconciliation_orchestrator/test_dependency_freshness.py | 1 | 0 | 0 | 0 | changed (W1.8) | Status flips go through append_phase_event; no direct contact with the two tables. |
| tests-49 | reconciliation_orchestrator/test_entity_status.py | 23 | 0 | 0 | 0 | changed (W1.1); deleted in part | Only implicit phase_events writes remain after W1.1 (brainstorm registration). |
| tests-47 | reconciliation_orchestrator/test_orchestrator.py | 16 | 0 | 0 | 1 | changed (W1.1,W1.3) | After Phase 1 its workflow_phases contact (Task 2) is gone; W1.7 adds a Task 2 for cascade recovery by uuid. |
| tests-39 | workflow_engine/test_c11_engine_dir_name.py | 21 | 1 | 0 | 16 | changed (W1.5) | _insert_orphan_workflow_row inserts an orphan workflow_phases row (a type_id no entity holds) with an explicit workspace_uuid to pass wp_reject_orphaned_insert; a key that references the entity would make that row unrepresentable, so these tests pin behaviour… |
| tests-38 | workflow_engine/test_c11_reconciliation_dir_name.py | 17 | 1 | 0 | 3 | changed (W1.3); deleted in part | _insert_orphan_workflow_row inserts an orphan workflow_phases row (a type_id no entity holds) with an explicit workspace_uuid to pass wp_reject_orphaned_insert; a key that references the entity would make that row unrepresentable, so these tests pin behaviour… |
| tests-36 | workflow_engine/test_c11_validator_and_init.py | 13 | 0 | 0 | 0 | changed (W2.5,W2.1) | Two helpers; a signature change lands in them once. |
| tests-45 | workflow_engine/test_c15_c16_project_registration.py | 19 | 0 | 0 | 1 | unchanged | Reads entity_created events by type_id; unambiguous in its one-workspace DB. |
| tests-46 | workflow_engine/test_c5b_workspace_callers.py | 6 | 0 | 1 | 0 | unchanged | Same as test_c5b_alias_free_callers.py: pins the legacy project_id stored on entity_created. |
| tests-40 | workflow_engine/test_c8_kind_from_column.py | 13 | 1 | 0 | 10 | unchanged | Pins that an orphan row (no entity, so kind None) stays a db_only candidate whatever its type_id spells (test_audit_writes.py comment at :531-535); inserts an orphan workflow_phases row (a type_id no entity holds) with an explicit workspace_uuid to pass wp_re… |
| tests-33 | workflow_engine/test_engine.py | 187 | 0 | 0 | 36 | changed (W1.5) | _setup_two_workspaces pins today's contract: a row owned by ws_a, engine call with ws_b, update_workflow_phase raises ValueError (FR-4.1). Under a per-entity key ws_b would have no row for that entity (not found) unless it holds the entity; all other rows are… |
| tests-34 | workflow_engine/test_entity_engine.py | 100 | 0 | 0 | 11 | unchanged | _with_phase creates rows by type_id; 97 references flow through it, so a key change touches one helper. Fault-injection tests assert the row is unchanged (:2178, :2199). |
| tests-35 | workflow_engine/test_feature_lifecycle.py | 30 | 0 | 0 | 0 | changed (W2.5,W2.1) | After Phase 1 these calls carry the caller's workspace; a per-entity key would resolve (workspace, type_id) to the entity once inside the writer, which these tests reach only through the public functions. |
| tests-37 | workflow_engine/test_reconciliation.py | 151 | 2 | 0 | 48 | changed (W1.3,W1.7); deleted in part | The surviving check_workflow_drift tests read rows by type_id and include an orphan row (inserts an orphan workflow_phases row (a type_id no entity holds) with an explicit workspace_uuid to pass wp_reject_orphaned_insert; a key that references the entity woul… |
| tests-41 | workflow_engine/test_rollup.py | 90 | 0 | 0 | 1 | unchanged | Rollup reads the parent's row via rollup._get_workflow_phase (by type_id); one helper (_with_phase) creates all rows. |
| tests-42 | workflow_engine/test_router.py | 22 | 0 | 0 | 1 | unchanged | Goes through router.init_entity_workflow/transition_entity_phase; follows their key. |
| tests-43 | workflow_engine/test_secretary_intelligence.py | 128 | 0 | 0 | 2 | unchanged | Two row creations by type_id; the reader secretary_intelligence.get_parent_context uses get_workflow_phase(type_id) (other area). |
| tests-44 | workflow_engine/test_task_promotion.py | 29 | 0 | 0 | 17 | changed (W2.4,W2.1) | Three helpers create every row by type_id. |
| fill-3 | hooks/tests/test-workflow-regression.sh | 4 | 0 | 0 | 3 | changed (W2.2); related W2.1; W2.2 breaks th… | Reaches workflow_phases only through create_workflow_phase(type_id, ...), update_workflow_phase(type_id, ...) and the _process_* handlers, all by type_id with no workspace; it has no raw SQL, so it follows the API's signatures. |
| tests-56 | mcp/test_c11_mcp_dir_name.py | 5 | 0 | 0 | 1 | changed (W1.4,W2.5) | One fixture creates the row by type_id. |
| tests-57 | mcp/test_c15_c16_create_project_flow.py | 9 | 0 | 0 | 2 | unchanged | Reads entity_created events by type_id. |
| tests-58 | mcp/test_c5b_c17_allocate_register.py | 6 | 0 | 1 | 0 | unchanged | Pins the legacy project_id on entity_created. |
| tests-52 | mcp/test_c8_workflow_state_kind.py | 10 | 1 | 0 | 13 | changed (W2.1) | The only suite fixture that builds the live shared-type_id shape and runs transitions through it; under a per-entity key the other workspace could hold its own row, and get_workflow_phase(type_id) (9 reads) would be ambiguous. It asserts db.get_entity(type_id… |
| tests-53 | mcp/test_complete_phase_closes.py | 13 | 2 | 3 | 3 | unchanged | One fixture creates the rows; raw reads by type_id are unambiguous in its DB except where TestAc10_6 adds a second workspace (distinct type_ids). |
| tests-55 | mcp/test_feature_134_trustgate.py | 7 | 0 | 0 | 6 | changed (W1.4,W2.3) | mini_spec events are read by type_id from phase_events (workflow_state_server get_mini_spec, :2324). |
| tests-54 | mcp/test_issue_spawn.py | 13 | 2 | 5 | 1 | unchanged | Asserts phase_events row counts unchanged (:288) and a spawned_child event by type_id; follows any phase_events key change in append_phase_event. |
| tests-51 | mcp/test_workflow_state_server.py | 414 | 9 | 2 | 142 | changed (W1.4,W1.6,W2.2,W2.3,W2.5); deleted… | seeded_engine is the single row creator for most MCP tests (166 references), so a create_workflow_phase signature change lands there once; the two orphan INSERTs (inserts an orphan workflow_phases row (a type_id no entity holds) with an explicit workspace_uui… |
| tests-59 | scripts/tests/test_c5b_parse_backlog_workspace.py | 1 | 0 | 1 | 0 | unchanged | Pins the legacy project_id on entity_created. |
| tests-60 | ui/tests/test_app.py | 60 | 2 | 0 | 11 | unchanged | _seed_workflow_row inserts rows with no entity for board rendering (inserts an orphan workflow_phases row (a type_id no entity holds) with an explicit workspace_uuid to pass wp_reject_orphaned_insert; a key that references the entity would make that row unrep… |
| tests-61 | ui/tests/test_board_archived.py | 9 | 1 | 0 | 1 | unchanged | _add_orphan_row inserts an orphan workflow_phases row (a type_id no entity holds) with an explicit workspace_uuid to pass wp_reject_orphaned_insert; a key that references the entity would make that row unrepresentable, so these tests pin behaviour a per-entit… |
| tests-62 | ui/tests/test_c8_card_kind.py | 4 | 1 | 0 | 4 | unchanged | _insert_workflow_row's docstring: 'With no entities row behind it, it is an orphan'; inserts an orphan workflow_phases row (a type_id no entity holds) with an explicit workspace_uuid to pass wp_reject_orphaned_insert; a key that references the entity would ma… |
| tests-63 | ui/tests/test_deepened_app.py | 38 | 1 | 0 | 0 | unchanged | _seed_workflow_row inserts rows with no entity (inserts an orphan workflow_phases row (a type_id no entity holds) with an explicit workspace_uuid to pass wp_reject_orphaned_insert; a key that references the entity would make that row unrepresentable, so these… |
| tests-64 | ui/tests/test_entities.py | 91 | 1 | 0 | 8 | unchanged | One fixture inserts the row by type_id only (trigger fills workspace, uuid NULL); the route's lookup dict is keyed by type_id (ui/routes/entities.py:24-27, other area). |
| tests-65 | scripts/test_c22_recreate_live_remainder.py | 34 | 4 | 0 | 0 | unchanged | Pins a one-off script's before/after state by type_id; the script ran already (C22), so a re-key affects it only if kept runnable. |
| tests-66 | scripts/test_fix_kanban_columns.py | 7 | 5 | 0 | 0 | unchanged | Hand-rolled schema with workflow_phases keyed by type_id; follows only if fix_kanban_columns.py changes. |
| TST-3 | scripts/test_migrate_bash.sh |  | 4 (CREATE TABLE :309, :656; INSERT :319, :670) | 0 | 0 | unchanged | 4 raw-SQL statements on workflow_phases (2 CREATE TABLE, 2 INSERT) in heredocs; hand schema with no uuid/workspace columns. |
| tests-67 | scripts/test_migrate_db.py | 45 | 13 | 0 | 0 | unchanged | scripts/migrate_db.py:248-257 merges 'INSERT OR IGNORE INTO main.workflow_phases ... WHERE wp.type_id NOT IN (SELECT type_id FROM main.workflow_phases)'; the fixtures are pre-workspace shapes, so a re-key reaches these tests only if migrate_db.py is kept and… |
| tests-69 | scripts/test_migrate_deepened.py | 25 | 0 | 0 | 0 | unchanged | Same as test_migrate_db.py. |
| tests-68 | scripts/test_migrate_e2e.py | 10 | 0 | 0 | 0 | unchanged | Same as test_migrate_db.py. |
| tests-72 | (aggregate) plugins/pd/hooks/lib/entity_registry/test_c11_feature_entity_id.py,… |  | 0 | 0 | 0 (184 implicit pe writes via registration/status calls) | unchanged; related W2.2; no file needs an ed… | Nothing per file if phase_events keeps its columns or a new key is filled inside append_phase_event, which register_entity (:7765), upsert_entity (:7928) and update_entity (:8699) already call with workspace_uuid; these files change only if append_phase_event… |
| tests-73 | (shared fixtures) plugins/pd/hooks/lib/entity_registry/database.py EntityDataba… |  | see 7.1 | see 7.1 | see 7.1 | changed (W2.1); W2.1 adds an optional parame… | A key change reaches most tests through a handful of per-file helpers, not per test; the schema reaches them through EntityDatabase(path) (fresh v1 chain) and build_staging_database (v2), which a migration must bring to one target. Measured on a scratch file:… |

80 test-file rows (tests-72 aggregates 22 files, 21 `test_*.py` and `hooks/tests/test-sqlite-concurrency.sh`, whose only contact is implicit phase_events writes through registration and status updates; tests-73 covers the shared fixtures).

## 8. Live census

Copied verbatim from `live-census.md` (tests-and-live survey); only its headings are renumbered 8.1–8.3 and moved down one level. Section 8.4 adds the synthesizer's re-checks.


- **Surveyor:** tests-and-live agent, 2026-09-26. Repo `develop` at 77f06efb.
- **Live file:** `~/.claude/pd/entities/entities.db`, schema_generation `v2`, schema_version `7`, no `-wal` file.
- **How it was read:** every live figure below came from `sqlite3.connect('file:/Users/terry/.claude/pd/entities/entities.db?immutable=1', uri=True)`, SELECT only.
- **Dry run:** on a copy made with the prescribed backup command into `agent_sandbox/2026-09-26/rekey/tests-work/live-copy.db`. The dry run added scratch objects (`dryrun_wp_by_entity`, `dryrun_pe_map`, column `phase_events.dryrun_entity_uuid`) to that copy only.
- **Scripts:** `tests-work/census.py` (live, read-only), `tests-work/dryrun.py` (copy), `tests-work/write_census_md.py` (this file). Raw results: `tests-work/census-results.json`, `tests-work/dryrun-results.json`.

### 8.1 Fingerprint of the live file

| When | `stat -f '%m %z'` | sha256 prefix |
|---|---|---|
| Before any work | `1790286038 4083712` | `2814bb4434e8faa0` |
| After all work (measured when this file was written) | `1790286038 4083712` | `2814bb4434e8faa0` |
| Expected (task brief) | `1790286038 4083712` | `2814bb4434e8faa0` |

**Match:** yes, before = after = expected.

### 8.2 Headline figures

#### workflow_phases (529 rows)
- **Key today:** `type_id TEXT PRIMARY KEY`; `uuid` is nullable with no constraint, and `workspace_uuid` is nullable with `REFERENCES workspaces(uuid)` (indexes `idx_wp_uuid`, `idx_wp_workspace_uuid`; triggers `wp_autofill_workspace_uuid`, `wp_reject_orphaned_insert`, `enforce_immutable_wp_type_id`).
- **NULL uuid:** 8 rows, all in pedantic-drip (`69696982`): `backlog:278` to `backlog:284` (7 rows, updated 2026-09-18 and 2026-09-24) and `feature:134-workflow-rebuild` (2026-09-16).
- **NULL workspace_uuid:** 0.
- **uuid disagrees with the (workspace_uuid, type_id) entity:** 0. The other 521 uuids all agree. No uuid names a missing entity or an entity with another type_id or workspace. No uuid repeats.
- **No entity for (workspace_uuid, type_id):** 0. **type_id no entity holds at all:** 0.
- **type_id held by more than one workspace:** 5 rows, every one owned by pedantic-drip (`69696982`), and the other holder is terry_agent (`f7b49c1d`) each time: `feature:002-assessed-mode-pipeline-fix`, `feature:003-oc-config-optimizer`, `feature:004-rca005-restart-loop-keychain-fix`, `brainstorm:20260318-025248-three-claws-v2-protocol`, `brainstorm:20260326-030832-openclaw-gap-analysis`. The terry_agent entities are all `is_archived=1`. Those 5 terry_agent entities have no row, because the type_id primary key already holds pedantic-drip's.
- **Rows per kind:** backlog 177, brainstorm 88, feature 264, project 0.
- **Rows per workspace:** 69696982 (pedantic-drip) 397, f7b49c1d (terry_agent) 49, 7e788234 (project_illium) 29, 35d9b5f9 (cast-below) 27, 6f113c48 (fractorg) 23, d373a5ad 3, fe180347 1.
- **Entities with no row, by (workspace_uuid, type_id):** backlog 25, brainstorm 12, feature 7, project 16 (60 of 589 entities).
- **Registry-wide shared type_ids:** 7. The 5 above, plus `feature:035-slim-watchdog-self-mgmt` (pedantic-drip and terry_agent, both archived, no row in either) and `project:P001` (terry_agent, cast-below, pedantic-drip; projects never get a row).

- **Fresh versus live DDL:** a fresh `EntityDatabase` on a scratch file (`tests-work/fresh-v1.db`, v1 chain, schema_version 25) has the same 14 `sqlite_master` objects for `workflow_phases` and `phase_events` (tables, triggers, indexes) as the live v2 file. Live `workflow_phases` has one foreign key (`workspace_uuid REFERENCES workspaces(uuid)`); `phase_events` has none.

#### phase_events (1469 rows)
- **Columns:** `id INTEGER PRIMARY KEY AUTOINCREMENT, type_id TEXT NOT NULL, project_id TEXT NOT NULL, phase, event_type NOT NULL, timestamp NOT NULL, iterations, reviewer_notes, backward_reason, backward_target, source NOT NULL DEFAULT 'live', created_at NOT NULL, metadata`.
- **How it names the entity:** by `type_id` only. There is no entity `uuid` column and no `workspace_uuid` column.
- **How it names the workspace:** by the legacy `project_id` text, the value `workspaces.project_id_legacy` holds. `append_phase_event` takes `workspace_uuid` but its INSERT stores only `type_id` and `project_id` (`database.py:9736-9746`).
- **project_id values (8):** `48e4416a668f` 770 (pedantic-drip), `__unknown__` 285 (the `__unknown__` workspace `6250c8a6`, which holds 0 entities), `b5127373568d` 243 (terry_agent), `721cb90c8607` 71 (workspace `0dcd2558` `projects`, which holds 0 entities), `c894a0cc8ade` 52 (project_illium), `b3835982ffa0` 34 (fractorg), `e8bdba5f147b` 13 (no workspace has this legacy id), `e99bb5601c36` 1 (cast-below).
- **Workspaces project_id cannot name:** d373a5ad and fe180347 have `project_id_legacy` NULL. Their entities' 3 and 9 events carry `__unknown__`.
- **Rows whose (project_id -> workspace, type_id) finds an entity:** 1088. The other 381: `__unknown__` 285, `721cb90c8607` 71, `e8bdba5f147b` 13, and the 12 rows whose type_id no entity holds.
- **Rows whose type_id is held by one workspace:** 1436; **by two:** 20; **by three:** 1 (`project:P001`); **by none:** 12.
- **Shared type_id rows (21), can their workspace be told apart by project_id?**
  - **Yes, 8 rows:** each carries terry_agent's or pedantic-drip's own project_id, and that workspace holds the type_id (`entity_status_changed` rows for the two brainstorms, features 002, 003, 004, 035 and `project:P001`; feature 035 has one row per workspace).
  - **No, 13 rows:** `feature:002-assessed-mode-pipeline-fix` (5) and `feature:004-rca005-restart-loop-keychain-fix` (8), all `started`/`completed`, `source='backfill'`, `project_id='__unknown__'`. Their timestamps (002: 2026-03-20T04:28:02 to 04:57:10; 004: 2026-03-25T16:45:34 to 18:44:59) precede the terry_agent entities' `created_at` (2026-03-27T01:01:05.597), and follow the pedantic-drip entities' `created_at` (002: 2026-03-20T04:28:02.435512, 44 microseconds after its first event at 04:28:02.435468; 004: 2026-03-25T16:45:19.955). The `workflow_phases` rows for both type_ids are pedantic-drip's.
- **Rows that map to no entity:** 12, all `entity_created`, `source='backfill'`, one per type_id: `backlog:001` to `backlog:004` (project_id `c894a0cc8ade`, project_illium) and `backlog:052` to `backlog:059` (project_id `48e4416a668f`, pedantic-drip). No entity holds these type_ids today.
- **Rows per event_type:** completed 653, started 393, entity_status_changed 278, entity_created 144, backward 1. **Per source:** backfill 1372, live 97. Last write 2026-09-24T21:40:38.

#### events, v2 (2244 rows)
- **Key:** `uuid TEXT PRIMARY KEY`; the entity is `entity_uuid TEXT NOT NULL REFERENCES entities(uuid)`. Triggers `events_no_delete`, `events_no_update`, `events_no_replace`, `events_vocab_pipeline`, `events_vocab_execution`.
- **Coverage:** 589 distinct `entity_uuid`, which is every entity. 0 events name a missing entity. 0 entities have no events.
- **Every workflow_phases row's entity has events:** yes, 0 of 529 lack them. Only 97 of those 529 entities have `pipeline`-axis events.
- **Per axis/event_type:** lifecycle entity_created 680, lifecycle entity_status_changed 278, lifecycle reparented 25, execution status_backfilled 553, pipeline completed 477, pipeline started 229, pipeline workflow_established 1, pipeline backward 1.

#### Dry run on the copy: one key per entity (the entity's uuid)
- **workflow_phases, mapped by (workspace_uuid, type_id):** exactly one entity 529, none 0, several 0.
  - The same rows mapped by `type_id` alone: exactly one 524, several 5 (the shared type_ids above), none 0.
  - Mapped by the stored `uuid`: 521 name an entity (all agree with the (workspace_uuid, type_id) entity), 8 are NULL.
  - A scratch table keyed `entity_uuid TEXT NOT NULL PRIMARY KEY REFERENCES entities(uuid)` took all 529 rows with no conflict, and `pragma_foreign_key_check` on it returned 0 rows.
  - **Unmappable workflow_phases rows:** none.
- **phase_events:** exactly one entity 1444 (1436 by a type_id one workspace holds, 8 shared type_ids decided by project_id), none 12, several 13.
  - 356 of the 1436 rows mapped by type_id alone carry a project_id that does not name their entity's workspace (`__unknown__` 272, `721cb90c8607` 71, `e8bdba5f147b` 13).
  - Mapped strictly by (project_id -> workspace, type_id): 1088 exactly one, 381 none, 0 several.
  - **Unmappable phase_events rows, by type_id:**
    - none: `backlog:001-feature-054-multi-lp-type`, `backlog:002-re-open-univ4-signal-a`, `backlog:003-ilb-partial-exit-executor`, `backlog:004-f052-f056-follow-up-mark`, `backlog:052-low-security-defense-in-depth`, `backlog:053-low-security-replace-abs`, `backlog:054-132-cutover-verify-no`, `backlog:055-bug-workflow-state-mcp-phase`, `backlog:056-ergonomics-complete-phase`, `backlog:057-reviewer-severity-rubric`, `backlog:058-phase-gate-rerun-compression`, `backlog:059-migration11-race-test-flake` (1 row each);
    - several: `feature:002-assessed-mode-pipeline-fix` (5 rows), `feature:004-rca005-restart-loop-keychain-fix` (8 rows).
  - Mapped phase_events rows whose entity has no workflow_phases row: backlog 32, brainstorm 12, feature 20, project 12.

### 8.3 Every query, with its SQL and result

#### workflow_phases (live, immutable)

- **row count; rows with uuid; rows with workspace_uuid; distinct type_ids:** `[[529, 521, 529, 529]]`
  ```sql
  SELECT count(*), count(uuid), count(workspace_uuid), count(DISTINCT type_id) FROM workflow_phases
  ```
- **rows with NULL uuid (listed):** `[["backlog:278-entity-rename-tooling-or", "69696982", "2026-09-18T03:35:02.849481+00:00", "backlog"], ["backlog:279-pre-review-lint-for-curly", "69696982", "2026-09-24T21:40:38.467616+00:00", "backlog"], ["backlog:280-structured-git-operations", "69696982", "2026-09-24T21:40:38.469367+00:00", "backlog"], ["backlog:281-low-security-resolve-project", "69696982", "2026-09-24T21:40:38.470829+00:00", "backlog"], ["backlog:282-low-correctness-detect-phase", "69696982", "2026-09-24T21:40:38.472274+00:00", "backlog"], ["backlog:283-low-implementation-ac-5", "69696982", "2026-09-24T21:40:38.473760+00:00", "backlog"], ["backlog:284-low-test-gap-ac-5-rejection", "69696982", "2026-09-24T21:40:38.475181+00:00", "backlog"], ["feature:134-workflow-rebuild", "69696982", "2026-09-16T14:26:26.735204+00:00", "feature"]]`
  ```sql
  SELECT wp.type_id, substr(wp.workspace_uuid,1,8), wp.updated_at, e.kind FROM workflow_phases wp LEFT JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id WHERE wp.uuid IS NULL ORDER BY wp.type_id
  ```
- **rows with NULL workspace_uuid:** `[[0]]`
  ```sql
  SELECT count(*) FROM workflow_phases WHERE workspace_uuid IS NULL
  ```
- **rows whose non-NULL uuid disagrees with the entity found by (workspace_uuid, type_id):** `[[0]]`
  ```sql
  SELECT count(*) FROM workflow_phases wp JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id WHERE wp.uuid IS NOT NULL AND wp.uuid <> e.uuid
  ```
- **rows whose non-NULL uuid names no entity at all:** `[[0]]`
  ```sql
  SELECT count(*) FROM workflow_phases wp WHERE wp.uuid IS NOT NULL AND NOT EXISTS (SELECT 1 FROM entities e WHERE e.uuid = wp.uuid)
  ```
- **rows whose uuid names an entity with a different type_id or workspace_uuid:** `[[0]]`
  ```sql
  SELECT count(*) FROM workflow_phases wp JOIN entities e ON e.uuid = wp.uuid WHERE e.type_id <> wp.type_id OR e.workspace_uuid <> wp.workspace_uuid
  ```
- **uuid values shared by more than one row:** `[[0]]`
  ```sql
  SELECT count(*) FROM (SELECT uuid FROM workflow_phases WHERE uuid IS NOT NULL GROUP BY uuid HAVING count(*) > 1)
  ```
- **rows with no entity for (workspace_uuid, type_id):** `[[0]]`
  ```sql
  SELECT count(*) FROM workflow_phases wp WHERE NOT EXISTS (SELECT 1 FROM entities e WHERE e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id)
  ```
- **rows whose type_id no entity holds at all:** `[[0]]`
  ```sql
  SELECT count(*) FROM workflow_phases wp WHERE NOT EXISTS (SELECT 1 FROM entities e WHERE e.type_id = wp.type_id)
  ```
- **rows whose type_id is held by more than one workspace (row owner, holders):** `[["brainstorm:20260318-025248-three-claws-v2-protocol", "69696982", 2, "f7b49c1d/active/arch=1/del=0 ; 69696982/promoted/arch=0/del=0"], ["brainstorm:20260326-030832-openclaw-gap-analysis", "69696982", 2, "f7b49c1d/active/arch=1/del=0 ; 69696982/promoted/arch=0/del=0"], ["feature:002-assessed-mode-pipeline-fix", "69696982", 2, "69696982/completed/arch=0/del=0 ; f7b49c1d/archived/arch=1/del=0"], ["feature:003-oc-config-optimizer", "69696982", 2, "f7b49c1d/archived/arch=1/del=0 ; 69696982/completed/arch=0/del=0"], ["feature:004-rca005-restart-loop-keychain-fix", "69696982", 2, "69696982/completed/arch=0/del=0 ; f7b49c1d/archived/arch=1/del=0"]]`
  ```sql
  SELECT wp.type_id, substr(wp.workspace_uuid,1,8) AS row_ws, count(DISTINCT e.workspace_uuid) AS holders, group_concat(substr(e.workspace_uuid,1,8) || '/' || e.status || '/arch=' || e.is_archived || '/del=' || e.is_deleted, ' ; ') FROM workflow_phases wp JOIN entities e ON e.type_id = wp.type_id GROUP BY wp.type_id HAVING count(DISTINCT e.workspace_uuid) > 1 ORDER BY wp.type_id
  ```
- **rows per kind (kind of the entity found by (workspace_uuid, type_id)):** `[["backlog", 177], ["brainstorm", 88], ["feature", 264]]`
  ```sql
  SELECT coalesce(e.kind, '<no entity>'), count(*) FROM workflow_phases wp LEFT JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id GROUP BY 1 ORDER BY 1
  ```
- **rows per workspace:** `[["69696982", 397], ["f7b49c1d", 49], ["7e788234", 29], ["35d9b5f9", 27], ["6f113c48", 23], ["d373a5ad", 3], ["fe180347", 1]]`
  ```sql
  SELECT substr(wp.workspace_uuid,1,8), count(*) FROM workflow_phases wp GROUP BY wp.workspace_uuid ORDER BY 2 DESC
  ```
- **entity flags of the rows' entities (archived, deleted, legacy):** `[[163, 0, 170]]`
  ```sql
  SELECT sum(e.is_archived), sum(e.is_deleted), sum(e.is_legacy) FROM workflow_phases wp JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id
  ```
- **entities with no workflow_phases row for (workspace_uuid, type_id), per kind:** `[["backlog", 25], ["brainstorm", 12], ["feature", 7], ["project", 16]]`
  ```sql
  SELECT e.kind, count(*) FROM entities e WHERE NOT EXISTS (SELECT 1 FROM workflow_phases wp WHERE wp.workspace_uuid = e.workspace_uuid AND wp.type_id = e.type_id) GROUP BY e.kind ORDER BY 1
  ```
- **entities with no row whose type_id has a row in ANOTHER workspace (blocked by the type_id PRIMARY KEY):** `[["brainstorm:20260318-025248-three-claws-v2-protocol", "f7b49c1d", "brainstorm", "active", 1], ["brainstorm:20260326-030832-openclaw-gap-analysis", "f7b49c1d", "brainstorm", "active", 1], ["feature:002-assessed-mode-pipeline-fix", "f7b49c1d", "feature", "archived", 1], ["feature:003-oc-config-optimizer", "f7b49c1d", "feature", "archived", 1], ["feature:004-rca005-restart-loop-keychain-fix", "f7b49c1d", "feature", "archived", 1]]`
  ```sql
  SELECT e.type_id, substr(e.workspace_uuid,1,8), e.kind, e.status, e.is_archived FROM entities e WHERE NOT EXISTS (SELECT 1 FROM workflow_phases wp WHERE wp.workspace_uuid = e.workspace_uuid AND wp.type_id = e.type_id) AND EXISTS (SELECT 1 FROM workflow_phases wp WHERE wp.type_id = e.type_id) ORDER BY e.type_id
  ```

#### entities (live, immutable)

- **type_ids held by more than one workspace (all kinds):** `[["brainstorm:20260318-025248-three-claws-v2-protocol", 2, "f7b49c1d/brainstorm/active/arch=1/del=0 ; 69696982/brainstorm/promoted/arch=0/del=0"], ["brainstorm:20260326-030832-openclaw-gap-analysis", 2, "f7b49c1d/brainstorm/active/arch=1/del=0 ; 69696982/brainstorm/promoted/arch=0/del=0"], ["feature:002-assessed-mode-pipeline-fix", 2, "69696982/feature/completed/arch=0/del=0 ; f7b49c1d/feature/archived/arch=1/del=0"], ["feature:003-oc-config-optimizer", 2, "f7b49c1d/feature/archived/arch=1/del=0 ; 69696982/feature/completed/arch=0/del=0"], ["feature:004-rca005-restart-loop-keychain-fix", 2, "69696982/feature/completed/arch=0/del=0 ; f7b49c1d/feature/archived/arch=1/del=0"], ["feature:035-slim-watchdog-self-mgmt", 2, "69696982/feature/active/arch=1/del=0 ; f7b49c1d/feature/active/arch=1/del=0"], ["project:P001", 3, "f7b49c1d/project/active/arch=1/del=0 ; 35d9b5f9/project/completed/arch=0/del=0 ; 69696982/project/-/arch=1/del=0"]]`
  ```sql
  SELECT type_id, count(*), group_concat(substr(workspace_uuid,1,8) || '/' || kind || '/' || coalesce(status,'-') || '/arch=' || is_archived || '/del=' || is_deleted, ' ; ') FROM entities GROUP BY type_id HAVING count(DISTINCT workspace_uuid) > 1 ORDER BY type_id
  ```
- **entity count; distinct type_ids; workspaces:** `[[589, 581, 7]]`
  ```sql
  SELECT count(*), count(DISTINCT type_id), count(DISTINCT workspace_uuid) FROM entities
  ```

#### phase_events (live, immutable)

- **row count; distinct type_ids; distinct project_ids:** `[[1469, 376, 8]]`
  ```sql
  SELECT count(*), count(DISTINCT type_id), count(DISTINCT project_id) FROM phase_events
  ```
- **rows per project_id, and the workspace whose project_id_legacy equals it:** `[["48e4416a668f", 770, "69696982", 1], ["__unknown__", 285, "6250c8a6", 1], ["b5127373568d", 243, "f7b49c1d", 1], ["721cb90c8607", 71, "0dcd2558", 1], ["c894a0cc8ade", 52, "7e788234", 1], ["b3835982ffa0", 34, "6f113c48", 1], ["e8bdba5f147b", 13, null, 0], ["e99bb5601c36", 1, "35d9b5f9", 1]]`
  ```sql
  SELECT pe.project_id, count(*), (SELECT group_concat(substr(w.uuid,1,8)) FROM workspaces w WHERE w.project_id_legacy = pe.project_id), (SELECT count(*) FROM workspaces w WHERE w.project_id_legacy = pe.project_id) FROM phase_events pe GROUP BY pe.project_id ORDER BY 2 DESC
  ```
- **rows per event_type:** `[["completed", 653], ["started", 393], ["entity_status_changed", 278], ["entity_created", 144], ["backward", 1]]`
  ```sql
  SELECT event_type, count(*) FROM phase_events GROUP BY 1 ORDER BY 2 DESC
  ```
- **rows per source:** `[["backfill", 1372], ["live", 97]]`
  ```sql
  SELECT source, count(*) FROM phase_events GROUP BY 1
  ```
- **rows whose type_id no entity holds at all (count, distinct type_ids):** `[[12, 12]]`
  ```sql
  SELECT count(*), count(DISTINCT type_id) FROM phase_events pe WHERE NOT EXISTS (SELECT 1 FROM entities e WHERE e.type_id = pe.type_id)
  ```
- **rows whose type_id no entity holds, by type_id:** `[["backlog:001-feature-054-multi-lp-type", 1, "c894a0cc8ade", "2026-06-14T07:13:24.384596+00:00", "2026-06-14T07:13:24.384596+00:00"], ["backlog:002-re-open-univ4-signal-a", 1, "c894a0cc8ade", "2026-06-15T04:45:38.546910+00:00", "2026-06-15T04:45:38.546910+00:00"], ["backlog:003-ilb-partial-exit-executor", 1, "c894a0cc8ade", "2026-06-15T05:36:21.375892+00:00", "2026-06-15T05:36:21.375892+00:00"], ["backlog:004-f052-f056-follow-up-mark", 1, "c894a0cc8ade", "2026-06-15T18:51:27.204988+00:00", "2026-06-15T18:51:27.204988+00:00"], ["backlog:052-low-security-defense-in-depth", 1, "48e4416a668f", "2026-07-10T15:44:17.654558+00:00", "2026-07-10T15:44:17.654558+00:00"], ["backlog:053-low-security-replace-abs", 1, "48e4416a668f", "2026-07-10T15:44:19.710960+00:00", "2026-07-10T15:44:19.710960+00:00"], ["backlog:054-132-cutover-verify-no", 1, "48e4416a668f", "2026-07-10T19:49:29.543951+00:00", "2026-07-10T19:49:29.543951+00:00"], ["backlog:055-bug-workflow-state-mcp-phase", 1, "48e4416a668f", "2026-07-10T19:49:34.619387+00:00", "2026-07-10T19:49:34.619387+00:00"], ["backlog:056-ergonomics-complete-phase", 1, "48e4416a668f", "2026-07-10T19:49:34.983592+00:00", "2026-07-10T19:49:34.983592+00:00"], ["backlog:057-reviewer-severity-rubric", 1, "48e4416a668f", "2026-07-11T02:06:57.635467+00:00", "2026-07-11T02:06:57.635467+00:00"], ["backlog:058-phase-gate-rerun-compression", 1, "48e4416a668f", "2026-07-11T02:07:05.815625+00:00", "2026-07-11T02:07:05.815625+00:00"], ["backlog:059-migration11-race-test-flake", 1, "48e4416a668f", "2026-07-11T02:30:28.877283+00:00", "2026-07-11T02:30:28.877283+00:00"]]`
  ```sql
  SELECT type_id, count(*), group_concat(DISTINCT project_id), min(timestamp), max(timestamp) FROM phase_events pe WHERE NOT EXISTS (SELECT 1 FROM entities e WHERE e.type_id = pe.type_id) GROUP BY type_id ORDER BY type_id
  ```
- **rows whose type_id is held by exactly one / more than one workspace:** `[[1, 1436], [2, 20], [3, 1]]`
  ```sql
  SELECT h.holders, count(*) FROM phase_events pe JOIN (SELECT type_id, count(DISTINCT workspace_uuid) AS holders FROM entities GROUP BY type_id) h ON h.type_id = pe.type_id GROUP BY h.holders
  ```
- **rows whose type_id is held by more than one workspace: per type_id and project_id, with the workspace project_id names and whether that workspace holds the type_id:** `[["brainstorm:20260318-025248-three-claws-v2-protocol", "b5127373568d", 1, "f7b49c1d", 1, "entity_status_changed"], ["brainstorm:20260326-030832-openclaw-gap-analysis", "b5127373568d", 1, "f7b49c1d", 1, "entity_status_changed"], ["feature:002-assessed-mode-pipeline-fix", "__unknown__", 5, "6250c8a6", 0, "started,completed"], ["feature:002-assessed-mode-pipeline-fix", "b5127373568d", 1, "f7b49c1d", 1, "entity_status_changed"], ["feature:003-oc-config-optimizer", "b5127373568d", 1, "f7b49c1d", 1, "entity_status_changed"], ["feature:004-rca005-restart-loop-keychain-fix", "__unknown__", 8, "6250c8a6", 0, "started,completed"], ["feature:004-rca005-restart-loop-keychain-fix", "b5127373568d", 1, "f7b49c1d", 1, "entity_status_changed"], ["feature:035-slim-watchdog-self-mgmt", "48e4416a668f", 1, "69696982", 1, "entity_status_changed"], ["feature:035-slim-watchdog-self-mgmt", "b5127373568d", 1, "f7b49c1d", 1, "entity_status_changed"], ["project:P001", "b5127373568d", 1, "f7b49c1d", 1, "entity_status_changed"]]`
  ```sql
  SELECT pe.type_id, pe.project_id, count(*), (SELECT group_concat(substr(w.uuid,1,8)) FROM workspaces w WHERE w.project_id_legacy = pe.project_id) AS pid_ws, (SELECT count(*) FROM entities e JOIN workspaces w ON w.uuid = e.workspace_uuid WHERE e.type_id = pe.type_id AND w.project_id_legacy = pe.project_id) AS pid_ws_holds, group_concat(DISTINCT pe.event_type) FROM phase_events pe WHERE pe.type_id IN (SELECT type_id FROM entities GROUP BY type_id HAVING count(DISTINCT workspace_uuid) > 1) GROUP BY pe.type_id, pe.project_id ORDER BY pe.type_id, pe.project_id
  ```
- **rows whose project_id names a workspace that holds their type_id (i.e. the pair (project_id -> workspace, type_id) finds an entity):** `[[1088]]`
  ```sql
  SELECT count(*) FROM phase_events pe WHERE EXISTS (SELECT 1 FROM entities e JOIN workspaces w ON w.uuid = e.workspace_uuid WHERE e.type_id = pe.type_id AND w.project_id_legacy = pe.project_id)
  ```
- **rows whose type_id exists but whose project_id does not name a holder of it (project_id -> workspace mismatch), by project_id:** `[["__unknown__", 285, 64], ["721cb90c8607", 71, 10], ["e8bdba5f147b", 13, 2]]`
  ```sql
  SELECT pe.project_id, count(*), count(DISTINCT pe.type_id) FROM phase_events pe WHERE EXISTS (SELECT 1 FROM entities e WHERE e.type_id = pe.type_id) AND NOT EXISTS (SELECT 1 FROM entities e JOIN workspaces w ON w.uuid = e.workspace_uuid WHERE e.type_id = pe.type_id AND w.project_id_legacy = pe.project_id) GROUP BY pe.project_id ORDER BY 2 DESC
  ```
- **rows per kind of the entity holding the type_id (type_ids held by one workspace only):** `[["backlog", 81], ["brainstorm", 32], ["feature", 1312], ["project", 11]]`
  ```sql
  SELECT e.kind, count(*) FROM phase_events pe JOIN entities e ON e.type_id = pe.type_id WHERE pe.type_id IN (SELECT type_id FROM entities GROUP BY type_id HAVING count(*) = 1) GROUP BY e.kind ORDER BY 1
  ```

#### events (live, immutable)

- **row count; distinct entity_uuid; entity_uuid naming no entity:** `[[2244, 589, 0]]`
  ```sql
  SELECT count(*), count(DISTINCT entity_uuid), sum(NOT EXISTS (SELECT 1 FROM entities e WHERE e.uuid = ev.entity_uuid)) FROM events ev
  ```
- **rows per axis and event_type:** `[["execution", "status_backfilled", 553], ["lifecycle", "entity_created", 680], ["lifecycle", "entity_status_changed", 278], ["lifecycle", "reparented", 25], ["pipeline", "completed", 477], ["pipeline", "started", 229], ["pipeline", "workflow_established", 1], ["pipeline", "backward", 1]]`
  ```sql
  SELECT axis, event_type, count(*) FROM events GROUP BY 1, 2 ORDER BY 1, 3 DESC
  ```
- **entities with no events:** `[[0]]`
  ```sql
  SELECT count(*) FROM entities e WHERE NOT EXISTS (SELECT 1 FROM events ev WHERE ev.entity_uuid = e.uuid)
  ```
- **workflow_phases rows whose entity (by workspace_uuid, type_id) has no events:** `[[0]]`
  ```sql
  SELECT count(*) FROM workflow_phases wp JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id WHERE NOT EXISTS (SELECT 1 FROM events ev WHERE ev.entity_uuid = e.uuid)
  ```
- **workflow_phases rows whose entity has pipeline-axis events:** `[[97]]`
  ```sql
  SELECT count(*) FROM workflow_phases wp JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id WHERE EXISTS (SELECT 1 FROM events ev WHERE ev.entity_uuid = e.uuid AND ev.axis = 'pipeline')
  ```

#### Dry run (copy)

- **copy sanity: workflow_phases, phase_events, events, entities counts:** `[[529, 1469, 2244, 589]]`
  ```sql
  SELECT (SELECT count(*) FROM workflow_phases), (SELECT count(*) FROM phase_events), (SELECT count(*) FROM events), (SELECT count(*) FROM entities)
  ```
- **wp: entities matching (workspace_uuid, type_id) per row -> rows with 0 / 1 / >1 matches:** `[[1, 529]]`
  ```sql
  SELECT n, count(*) FROM (SELECT wp.type_id, (SELECT count(*) FROM entities e WHERE e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id) AS n FROM workflow_phases wp) GROUP BY n ORDER BY n
  ```
- **wp: entities matching type_id alone per row -> rows with 0 / 1 / >1 matches:** `[[1, 524], [2, 5]]`
  ```sql
  SELECT n, count(*) FROM (SELECT wp.type_id, (SELECT count(*) FROM entities e WHERE e.type_id = wp.type_id) AS n FROM workflow_phases wp) GROUP BY n ORDER BY n
  ```
- **wp: stored uuid -> NULL / names an entity / names nothing:** `[["NULL", 8], ["names an entity", 521]]`
  ```sql
  SELECT CASE WHEN wp.uuid IS NULL THEN 'NULL' WHEN EXISTS (SELECT 1 FROM entities e WHERE e.uuid = wp.uuid) THEN 'names an entity' ELSE 'names nothing' END, count(*) FROM workflow_phases wp GROUP BY 1
  ```
- **wp: stored uuid agrees with the (workspace_uuid, type_id) entity / NULL / disagrees:** `[["NULL", 8], ["agrees", 521]]`
  ```sql
  SELECT CASE WHEN wp.uuid IS NULL THEN 'NULL' WHEN wp.uuid = e.uuid THEN 'agrees' ELSE 'disagrees' END, count(*) FROM workflow_phases wp LEFT JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id GROUP BY 1
  ```
- **wp: INSERT every row into a scratch table keyed by the entity uuid found by (workspace_uuid, type_id):** `[["rowcount", 529]]`
  ```sql
  INSERT INTO dryrun_wp_by_entity SELECT e.uuid, wp.type_id, wp.workspace_uuid, wp.workflow_phase, wp.kanban_column, wp.last_completed_phase, wp.mode, wp.backward_transition_reason, wp.updated_at FROM workflow_phases wp JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id
  ```
- **wp: scratch table row count, and PRAGMA foreign_key_check rows for it:** `[[529, 0]]`
  ```sql
  SELECT (SELECT count(*) FROM dryrun_wp_by_entity), (SELECT count(*) FROM pragma_foreign_key_check('dryrun_wp_by_entity'))
  ```
- **wp: entities that would hold no row under the entity key, per kind (same as today's no-row set, by uuid):** `[["backlog", 25], ["brainstorm", 12], ["feature", 7], ["project", 16]]`
  ```sql
  SELECT e.kind, count(*) FROM entities e WHERE NOT EXISTS (SELECT 1 FROM dryrun_wp_by_entity d WHERE d.entity_uuid = e.uuid) GROUP BY e.kind ORDER BY 1
  ```
- **pe: map rows whose type_id one entity holds (type_id alone decides):** `[["rowcount", 1436]]`
  ```sql
  UPDATE dryrun_pe_map SET entity_uuid = (SELECT e.uuid FROM entities e WHERE e.type_id = dryrun_pe_map.type_id), how = 'type_id unique' WHERE n_by_type_id = 1
  ```
- **pe: map rows whose type_id several workspaces hold, when project_id names exactly one holder (project_id -> workspaces.project_id_legacy):** `[["rowcount", 8]]`
  ```sql
  UPDATE dryrun_pe_map SET entity_uuid = (SELECT e.uuid FROM entities e JOIN workspaces w ON w.uuid = e.workspace_uuid WHERE e.type_id = dryrun_pe_map.type_id AND w.project_id_legacy = dryrun_pe_map.project_id), how = 'shared; project_id decides' WHERE n_by_type_id > 1 AND n_by_pid_type_id = 1
  ```
- **pe: outcome per row -> exactly one entity / none / several:** `[["exactly one (shared; project_id decides)", 8], ["exactly one (type_id unique)", 1436], ["none (no entity holds the type_id)", 12], ["several (shared type_id; project_id names no holder)", 13]]`
  ```sql
  SELECT CASE WHEN entity_uuid IS NOT NULL THEN 'exactly one (' || how || ')' WHEN n_by_type_id = 0 THEN 'none (no entity holds the type_id)' ELSE 'several (shared type_id; project_id names no holder)' END, count(*) FROM dryrun_pe_map GROUP BY 1 ORDER BY 1
  ```
- **pe: rows mapped by type_id alone whose project_id does NOT name the entity's workspace, by project_id:** `[["__unknown__", 272], ["721cb90c8607", 71], ["e8bdba5f147b", 13]]`
  ```sql
  SELECT m.project_id, count(*) FROM dryrun_pe_map m JOIN entities e ON e.uuid = m.entity_uuid WHERE m.how = 'type_id unique' AND NOT EXISTS (SELECT 1 FROM workspaces w WHERE w.uuid = e.workspace_uuid AND w.project_id_legacy = m.project_id) GROUP BY m.project_id ORDER BY 2 DESC
  ```
- **pe: stricter mapping by (project_id -> workspace, type_id) only -> 0 / 1 / >1 matches:** `[[0, 381], [1, 1088]]`
  ```sql
  SELECT n_by_pid_type_id, count(*) FROM dryrun_pe_map GROUP BY 1 ORDER BY 1
  ```
- **pe: unmappable rows (none or several), by type_id:** `[["backlog:001-feature-054-multi-lp-type", "none", 1, "c894a0cc8ade", "entity_created", "backfill", "2026-06-14T07:13:24.384596+00:00", "2026-06-14T07:13:24.384596+00:00"], ["backlog:002-re-open-univ4-signal-a", "none", 1, "c894a0cc8ade", "entity_created", "backfill", "2026-06-15T04:45:38.546910+00:00", "2026-06-15T04:45:38.546910+00:00"], ["backlog:003-ilb-partial-exit-executor", "none", 1, "c894a0cc8ade", "entity_created", "backfill", "2026-06-15T05:36:21.375892+00:00", "2026-06-15T05:36:21.375892+00:00"], ["backlog:004-f052-f056-follow-up-mark", "none", 1, "c894a0cc8ade", "entity_created", "backfill", "2026-06-15T18:51:27.204988+00:00", "2026-06-15T18:51:27.204988+00:00"], ["backlog:052-low-security-defense-in-depth", "none", 1, "48e4416a668f", "entity_created", "backfill", "2026-07-10T15:44:17.654558+00:00", "2026-07-10T15:44:17.654558+00:00"], ["backlog:053-low-security-replace-abs", "none", 1, "48e4416a668f", "entity_created", "backfill", "2026-07-10T15:44:19.710960+00:00", "2026-07-10T15:44:19.710960+00:00"], ["backlog:054-132-cutover-verify-no", "none", 1, "48e4416a668f", "entity_created", "backfill", "2026-07-10T19:49:29.543951+00:00", "2026-07-10T19:49:29.543951+00:00"], ["backlog:055-bug-workflow-state-mcp-phase", "none", 1, "48e4416a668f", "entity_created", "backfill", "2026-07-10T19:49:34.619387+00:00", "2026-07-10T19:49:34.619387+00:00"], ["backlog:056-ergonomics-complete-phase", "none", 1, "48e4416a668f", "entity_created", "backfill", "2026-07-10T19:49:34.983592+00:00", "2026-07-10T19:49:34.983592+00:00"], ["backlog:057-reviewer-severity-rubric", "none", 1, "48e4416a668f", "entity_created", "backfill", "2026-07-11T02:06:57.635467+00:00", "2026-07-11T02:06:57.635467+00:00"], ["backlog:058-phase-gate-rerun-compression", "none", 1, "48e4416a668f", "entity_created", "backfill", "2026-07-11T02:07:05.815625+00:00", "2026-07-11T02:07:05.815625+00:00"], ["backlog:059-migration11-race-test-flake", "none", 1, "48e4416a668f", "entity_created", "backfill", "2026-07-11T02:30:28.877283+00:00", "2026-07-11T02:30:28.877283+00:00"], ["feature:002-assessed-mode-pipeline-fix", "several", 5, "__unknown__", "started,completed", "backfill", "2026-03-20T04:28:02.435468+00:00", "2026-03-20T04:57:10.651269+00:00"], ["feature:004-rca005-restart-loop-keychain-fix", "several", 8, "__unknown__", "started,completed", "backfill", "2026-03-25T16:45:34.745309+00:00", "2026-03-25T18:44:59.479466+00:00"]]`
  ```sql
  SELECT m.type_id, CASE WHEN m.n_by_type_id = 0 THEN 'none' ELSE 'several' END, count(*), group_concat(DISTINCT m.project_id), group_concat(DISTINCT pe.event_type), group_concat(DISTINCT pe.source), min(pe.timestamp), max(pe.timestamp) FROM dryrun_pe_map m JOIN phase_events pe ON pe.id = m.pe_id WHERE m.entity_uuid IS NULL GROUP BY m.type_id ORDER BY m.type_id
  ```
- **pe: the 'several' rows' candidate entities (type_id, workspace, status, created_at) and the workflow_phases row owner:** `[["feature:002-assessed-mode-pipeline-fix", "69696982", "completed", 0, "2026-03-20T04:28:02.435512+00:00", "69696982"], ["feature:002-assessed-mode-pipeline-fix", "f7b49c1d", "archived", 1, "2026-03-27T01:01:05.597175+00:00", "69696982"], ["feature:004-rca005-restart-loop-keychain-fix", "69696982", "completed", 0, "2026-03-25T16:45:19.955371+00:00", "69696982"], ["feature:004-rca005-restart-loop-keychain-fix", "f7b49c1d", "archived", 1, "2026-03-27T01:01:05.597485+00:00", "69696982"]]`
  ```sql
  SELECT e.type_id, substr(e.workspace_uuid,1,8), e.status, e.is_archived, e.created_at, (SELECT substr(wp.workspace_uuid,1,8) FROM workflow_phases wp WHERE wp.type_id = e.type_id) FROM entities e WHERE e.type_id IN (SELECT type_id FROM dryrun_pe_map WHERE entity_uuid IS NULL AND n_by_type_id > 1) ORDER BY e.type_id, e.workspace_uuid
  ```
- **pe: copy the mapping into a scratch column on the COPY's phase_events:** `[["rowcount", 1469]]`
  ```sql
  UPDATE phase_events SET dryrun_entity_uuid = (SELECT m.entity_uuid FROM dryrun_pe_map m WHERE m.pe_id = phase_events.id)
  ```
- **pe: scratch column filled / NULL:** `[[1444, 25]]`
  ```sql
  SELECT count(dryrun_entity_uuid), sum(dryrun_entity_uuid IS NULL) FROM phase_events
  ```
- **pe: mapped rows whose entity has no workflow_phases row under the entity key (by kind):** `[["backlog", 32], ["brainstorm", 12], ["feature", 20], ["project", 12]]`
  ```sql
  SELECT e.kind, count(*) FROM phase_events pe JOIN entities e ON e.uuid = pe.dryrun_entity_uuid WHERE NOT EXISTS (SELECT 1 FROM dryrun_wp_by_entity d WHERE d.entity_uuid = e.uuid) GROUP BY e.kind ORDER BY 1
  ```

Note: `dryrun.py` also ran `CREATE TABLE dryrun_wp_by_entity (entity_uuid TEXT NOT NULL PRIMARY KEY REFERENCES entities(uuid), type_id TEXT NOT NULL, workspace_uuid TEXT NOT NULL, workflow_phase, kanban_column NOT NULL, last_completed_phase, mode, backward_transition_reason, updated_at NOT NULL)`, `CREATE TABLE dryrun_pe_map AS SELECT ...` and `ALTER TABLE phase_events ADD COLUMN dryrun_entity_uuid TEXT`, on the copy only. They are counting scaffolds, not a proposed schema.

### 8.4 Synthesizer's re-checks (live, `immutable=1`, 2026-09-26)

| Query | Result |
|---|---|
| `SELECT count(*), sum(project_id_legacy IS NULL) FROM workspaces` | 21, 7 |
| workspaces holding entities, and those with NULL `project_id_legacy` | 7, 2 (d373a5ad, fe180347) |
| phase_events rows with no entity for (label → workspace, type_id) | 381 (all rows); 368 when rows whose label names no workspace are left out; that label is `e8bdba5f147b` (13 rows) |
| children of any `project:P001` (`parent_uuid` join) | 41 |
| parent links that cross a workspace | 20 |
| `_metadata` backfill keys | backfill_complete=1, backfill_version=4 |
| entities per kind | backlog 202, brainstorm 100, feature 271, project 16 |
| workflow_phases rows whose (workspace_uuid, type_id) entity is archived | 163 |
| `list_workflow_phases()` equivalent: `workflow_phases LEFT JOIN entities ON wp.type_id = e.type_id` | 534 rows for 529 stored |
| the same with the board's unarchived filter | 366 |
| the same scoped to f7b49c1d (`e.workspace_uuid = ? OR e.uuid IS NULL`), rows owned by another workspace | 5, all owned by 69696982 |
| `entities.metadata.depends_on_features` | 84 entities, 106 entries: 72 `feature:` type_ids (all in the entity's own workspace, 0 shared), 34 bare ids |
| `entity_relations` kinds | `blocks` 33 |
| `sqlite_sequence` | migration_audit_log 1, entity_relations 33, phase_events 1469 |
| whitespace-normalised `sqlite_master` for objects on or naming workflow_phases, phase_events, entities: fresh.db vs live | 30 objects each, none only in one file, no text difference |
| `_metadata` schema keys | fresh.db: schema_version 25; live: schema_generation v2, schema_version 7 |

## 9. Open questions for the re-key design

Collected from the four surveys and deduplicated; the source is in brackets. Facts only; each needs a ruling.

**A. Contracts the design restates**

1. **W1.2's archive call passes a uuid to a type_id-keyed method.** design:178 has `update_entity(archived=)` call `db.set_archived(<resolved uuid>, archived)`; `set_archived(type_id, archived=True, *, workspace_uuid=None, actor=...)` runs `UPDATE entities SET is_archived = ? ... WHERE type_id = ?` (database.py:8433-8464), so a uuid matches no row and raises `ValueError`. Which contract does Phase R restate? [schema 2, surfaces 1]
2. **Is `workflow_phases.workspace_uuid` meant to be immutable?** `update_workflow_phase`'s docstring says so after m11; no trigger enforces it, and `update_entity`'s re-attribution cascade rewrites it by type_id (database.py:8763-8777). [schema 3]
3. **Which identity does criterion 6 ("fits the v2 direction") mean?** The dark `schema_v2._CORE_DDL` declares `entities.type_id` not unique (schema_v2.py:64); live entities keep UNIQUE(workspace_uuid, type_id). [schema 7]
4. **How is criterion 2's "type_id rename" to be shown?** After W5.1 deletes `display.rename_entity` (engines-83), no code path renames `entities.type_id`; only raw SQL can, and the wp immutability trigger aborts a follow-up `UPDATE OF type_id`. [schema 6]
5. **Which key does the re-keyed MCP boundary take?** The entity server scopes by the legacy `_project_id` through `_effective_project_id()`; the workflow server by `_workspace_uuid`; W4.1 gives both `_require_workspace()`. [surfaces 6]
6. **Where do markdown callers get a uuid?** The only MCP read returning one is `export_entities`; `register_entity` replies `Registered: {type_id}` and `get_entity` strips uuid; decomposing's `parent_uuid=<project_uuid>` is the one uuid path in commands and skills. [surfaces 5]
7. **Should the list tools' all-workspaces fallback survive?** With the workflow server's workspace unresolved, `list_features_by_phase`, `list_features_by_status` and `query_ready_tasks` fall back to all workspaces (`return _workspace_uuid or None`, workflow_state_server.py:2425), although the docstring promises the unknown workspace. [surfaces 7]

**B. `phase_events`**

8. **Does `phase_events` gain the entity key this round?** (plan:271) It has no entity or workspace column; `get_mini_spec` (express detection), `_check_artifact_completeness`, `_detect_phase_events_drift` and `pd_state_diff` read every workspace's rows for a type_id; `query_phase_analytics`' default project scope misses the 285 `'__unknown__'` rows; the workflow server writes `'__unknown__'` whenever its unscoped `get_entity` is None, which is always the case for a shared type_id. [surfaces 4, schema 4]
9. **If it does, how are old rows mapped?** Dry run: 1444 rows map to exactly one entity (1436 by a type_id one workspace holds, 8 decided by project_id); 13 rows (`feature:002` x5, `feature:004` x8, all `'__unknown__'`, `source='backfill'`) have two candidates, with only timestamps (before the terry_agent entities' `created_at`) and the pedantic-drip ownership of the wp rows as evidence; 12 `entity_created` backfill rows name type_ids no entity holds. Backfill, leave as they are, or mark? [tests 2, 3; schema 4]
10. **Will the design avoid `project_id` as a workspace key?** 356 of the 1436 rows mapped by type_id alone carry a project_id that does not name the holder's workspace (`'__unknown__'` 272, `721cb90c8607` 71, `e8bdba5f147b` 13); 7 of 21 workspaces (2 of the 7 that hold entities) have no `project_id_legacy`; re-attribution never rewrites the label. [tests 4, schema]

**C. Schema, migration and operation**

11. **Which `entity_axis_state` text is the target?** Live has `WHERE to_value IS NOT NULL AND event_type != 'skipped'`; views.py:90 and a rebuild today produce `WHERE event_type != 'skipped'`; no commit ever had the live text in code; v2 m3's probe accepts both. [schema 1]
12. **Is `rebuild_tool` still a supported v1→v2 path?** Fresh files stay v1-generation. Outside m6's backfill it is the only writer that sets `workflow_phases.uuid`; its INSERT column lists (wp 9, pe 12) and `_apply_v2_chain` would run any new `V2_MIGRATIONS` entry. [schema 5]
13. **Old processes lose write access after a live bump.** `V2_MIGRATIONS[8]` / `V2_SCHEMA_VERSION` 8 makes every running old-build MCP process read-only through the C23 guard (database.py:11068-11112); the operator manual's apply step has to plan for it. [schema 8]
14. **Should rows no entity holds stay representable?** Live has 0; 10 test files insert them, and the board query, `list_workflow_phases`' `OR e.uuid IS NULL` and the doctor checks tolerate them. Keep representable, or rewrite or delete those tests? [tests 1]
15. **Archived and soft-deleted entities keep live wp rows under their type_id** (163 live rows belong to archived entities); `delete_entity`'s docstring says it deletes `workflow_phases` rows, but it only soft-deletes. [schema 9]

**D. Scope of the round**

16. **Dark and test-only sites: re-key, delete, or out of scope?** `EntityWorkflowEngine.get_state` (engines-13, 14), `abandon_entity` and `_abandon_descendants` (engines-15, 16), server_helpers' `parent_type_id` branch (engines-74, 75, 77; the only production caller passes None), `display.rename_entity` (engines-83), the `secretary_intelligence` parent-context CLI (engines-61, 62). The 5D and task paths (engines-17 to 21) have callers but 0 live entities. [engines 3]
17. **Two script writers no design section names:** `cleanup_backlog.py`'s `set_archived(type_id)` with no workspace (SCR-3), and `pd_state_diff.py`'s type_id join and replay (SCR-1, SCR-2), run on every commit through `pre-commit-guard.sh` (HOOK-4). Are they in Phase R's task list? [surfaces 9]
18. **`scripts/migrate_db.py` merge-entities and the one-off C22 script:** migrate_db reads `entities.parent_type_id` (gone) and inserts wp rows without uuid or workspace (SCR-7; reached through `migrate.sh import`); is it inside criterion 5's "one target schema", or retired? Is `scripts/c22_recreate_live_remainder.py` still supported (SCR-9, SCR-10)? [surfaces 8, tests 8]
19. **The UI's lineage stays type_id-keyed after W3.2:** the detail page's `get_lineage(type_id)` calls (ui/routes/entities.py:184, :187, UI-7) return [] for a shared type_id even when the page is opened by uuid; `mermaid.py` draws edges from `parent_type_id` and styles nodes from `entity_type`, keys lineage rows don't carry (UI-10). Does W3.2's re-link at mermaid.py:67 cover node identity and edges? [surfaces 2, 3]
20. **What must the criterion-4 guard cover?** The existing scan roots (hooks/lib, mcp, ui/templates, plugins/pd/scripts) miss `plugins/pd/ui/routes/*.py` and repo `scripts/` (`migrate_db.py`, `fix_kanban_columns.py`, `c22_recreate_live_remainder.py`); `ui/routes/entities.py` matches list results by `row['type_id']` in Python; f-string SQL splits across constants. [tests 8]

**E. Tests**

21. **Pinned-schema tests:** update in place, or turn into historic snapshots? (`test_database.py` TestMigration3.test_type_id_is_primary_key, test_workflow_phases_has_8_columns, TestTriggers, TestIndexes; `test_v2_migrations.py:284`.) [tests 5]
22. **No "head minus one" builder:** `make_v12_db` is the newest in `test_helpers.py`; the migration's safety tests need a pre-migration fixture for the fresh v1 chain and for the v2 generation (`build_staging_database`). Which builder does the playbook add? [tests 6]
23. **Phase-1 effects the design does not name** (section 7.3): does the Phase 1 plan absorb them? [tests 7]
24. **Test breakage was determined statically.** No pytest ran, to protect the live registry (only `hooks/lib/conftest.py` sets `ENTITY_DB_PATH`); a code-verification pass (R3) would run the suites in a scratch export. [tests 9]

**F. Process**

25. **Line drift after Phase 1.** Rows are pinned at `77f06efb`; task 1A (in progress in `.pd-worktrees/followups-1a`) moves lines in feature_lifecycle.py, task_promotion.py, backfill.py and database.py, and W2.5 adds a `create_workflow_phase` call inside `activate_feature`. Re-anchor these rows after Phase 1 merges, or re-run R0? [engines 1]
26. **Inclusion boundary.** Kept as rows: three feeder `list_entities()` scans (engines-46, 65, 89), the engine delegations (engines-11, 12, 13), the orchestrator's Task 2 entry (engines-90) and the doctor's static guard (engines-94); plus synth-1 and synth-2. Keep, or fold into the rows they feed? [engines 4]
27. **"Deciding line" for unchanged rows.** Where no W1/W2 change edits a site, its `phase1_fate` quotes the deferral lines (design:543-544, :374, :365-367). Is that acceptable to the completeness critic? [engines 6]

Answered by this inventory (not open): the "39 `get_entity` reads" count (section 6.1) [engines 2]; how the implicit phase_events writes of `update_entity` and registration are recorded (section 1.3) [engines 5].

## 10. Completeness check

- **The critic:** `critic.md`, written by an agent independent of the four surveyors and the synthesizer, reviewed the 366-row inventory. Its verdict was "gaps": three missing sites, one row with the wrong key, and two summary figures misstated or classified inconsistently.
- **This round:** each item was checked against the source at `77f06efb` and the live registry (`immutable=1`) before any edit. `fill-work/fill.py` applied the confirmed items to `inventory.json`, and `fill-work/build_md_fill.py` rebuilt this file.
- **Result:** 369 rows (366 + 3 added). All six items were confirmed; M1 carries one wrong line citation, and one aside in the critic's section 3.3 is rejected. Applying X2's single rule also moved tests-72 and corrected two line fields.
- **Rows this round added or changed (20):** schema-24, schema-32, schema-35, schema-36, engines-1, engines-56, MCPW-2, MCPW-3, MCPW-11, MCPW-25, MCPW-29, MCPW-34, MCPW-36, MCPW-37, MCPE-11, MCPE-13, tests-72, fill-1, fill-2, fill-3. Each carries the critic item in `completeness` and a note starting "Completeness round:".

### 10.1 What the critic found, and the verdict

| Item | Critic's claim | Verdict | What was checked |
|---|---|---|---|
| M1 | `database.py:6297-6300` reads phase_events by type_id alone, and no row records it. | Confirmed: added fill-1. The critic cites the doctor's allow-list entry at `doctor/check_status_write_path.py:41`; the name is at :42. | `database.py:6293-6315` at `77f06efb`; `grep -c -E 'old_status\|629[6-9]' inventory.json` gave 0; the chain entries at :6485 and :6497; the column probe at :6272-6274. |
| M2 | `workflow_state_server.py:3017` pairs phase_events by `(type_id, phase)`. It is unscoped with `project_id='*'` or an empty `_project_id`. | Confirmed: added fill-2. | `:2909`, `:2926`, `:2992-3057`; `query_phase_events` adds the label only when it is truthy (`database.py:9846-9848`); the other branches group by phase or not at all. Live: feature:002 has 4 started and 1 completed, feature:004 has 2 and 6. Both are held by 69696982 and f7b49c1d, and every event is `'__unknown__'`. |
| M3 | `hooks/tests/test-workflow-regression.sh` has no row. | Confirmed: added fill-3, which Phase 1 changes (W2.2; see 10.3). | 604 lines; the API calls at :173, :202, :296, :322, :333, :493, :497, :502, :509, :512 match the critic's list; the file has no `execute(`; only `docs/dev-guide/getting-started.md:113` names it. |
| M3, minor | `test-sqlite-concurrency.sh:158` belongs with the tests-72 aggregate. | Confirmed: tests-72 now has 22 files and 184 calls. | :158-164 passes `workspace_uuid`; `register_entity` appends `entity_created` through `append_phase_event` (`database.py:7765`). |
| X1 | schema-24's `key_used` is `uuid`, but its range holds a phase_events read by type_id. | Confirmed: `key_used` and `workspace_scoped` now cover only the entity side, and fill-1 carries the read. | `database.py:6276-6279` (no key), `:6297-6300` (type_id), `:6311-6313` (uuid). |
| X2 | `phase1_class` follows two opposite rules for the same situation. | Confirmed: one rule now applies to every row (10.3). | `fill-work/fate_rule_check.py` checks every row that is not a test file against the design's cited lines. It found 12 mismatches on the merged inventory and 0 after this round. |
| X3 | "41 always-unscoped" counts schema-32, which W2.1 scopes. | Confirmed: 6.2 now has 40 rows and 6.3 has 15. | design:263-265. engines-33, MCPW-11, MCPW-21 and MCPW-25 keep their `get_entity` reads (`feature_lifecycle.py:566`, `workflow_state_server.py:436`). |
| Aside (critic 3.3) | The inventory does not mention the 34 un-prefixed values in `depends_on_features`. | Rejected. | Section 3's `depends_on_features` row and section 8.4 both read "106 entries: 72 `feature:` type_ids ..., 34 bare ids". |

### 10.2 Rows added

| id | Site | Why no survey had it |
|---|---|---|
| fill-1 | `database.py:6293-6315`: v2 migration 5's restore loop reads phase_events by type_id alone, newest first, then writes the restored status by uuid | The schema survey recorded migrations v2/4 to v2/7 as one range row, schema-24 |
| fill-2 | `workflow_state_server.py:2992-3057`: `_compute_durations` pairs events in memory by `(type_id, phase)` | MCPW-43 covers the tool, `:2871-2989`, and stops before the helper |
| fill-3 | `hooks/tests/test-workflow-regression.sh`, a test-file row: `create_workflow_phase` x2 and `update_workflow_phase` x1 with no workspace, `get_entity` x1, `register_entity` x3, three `_process_*` calls, no raw SQL | The tests survey scanned only `test_*.py` and `conftest.py`, and the surfaces survey scanned hook scripts but not `hooks/tests/*.sh` |

- **Also added:** `hooks/tests/test-sqlite-concurrency.sh` joins the tests-72 aggregate (same cause).
- **The sweep for that cause found nothing else:**
  - **Shell scripts:** five `.sh` files under `plugins/pd` and `scripts/` name either table or a registry API. Two are listed above, `scripts/test_migrate_bash.sh` is TST-3, and `scripts/dev/check_fr_c_115_atomicity*.sh` only grep git diffs.
  - **Python files with no row:** seven `.py` files that are not tests name the tables or the APIs, and none reads or writes either table or looks an entity up by type_id:
    - `doctor/__init__.py` (a comment) and `doctor/fixer.py` (a dispatch-table entry), as section 1.4 says;
    - `entity_registry/id_generator.py` and `entity_registry/metadata.py`: docstrings and comments;
    - `scripts/census_register_sites.py` and `scripts/rewrite_test_ids.py`: they read or rewrite source text, not the database;
    - `scripts/gen_archive_manifest.py`: it reads `entities` by uuid, and names phase_events only in prose (section 1.4; `critic.md` section 3.1).
  - **Other file types:** `ui/templates/_card.html` is UI-3 and `scripts/dev/cutover-prepass.sql` is SCR-11.

### 10.3 Fields corrected

**X1: schema-24**
- **`key_used`:** was `uuid`. It now reads: none for the flag DDL and the `status = 'archived'` UPDATE (`:6276-6279`); uuid for v2/5's restore UPDATE (`:6311-6313`); the phase_events read is fill-1.
- **`workspace_scoped`:** was `n/a`. It now reads: n/a for the flag columns; the phase_events read is never scoped (fill-1).

**X2: one rule for `phase1_class`**
- **The rule:** a row is `changed` only when Phase 1 edits a line inside the row's own range. That is either a line the design names, or the body of a function the design deletes or restructures that the row lies in:
  - `activate_feature`, `backfill_workflow_phases`, `_project_meta_json` and `_check_artifact_completeness`;
  - `_recover_pending_cascades`, `rollup_parent` and `cleanup_stale_dependencies`;
  - `create_workflow_phase` and `upsert_workflow_phase`.
- **A change through a callee:** when Phase 1 reaches the row only through a function it calls, the change goes in `phase1_related` and the class stays `unchanged`.
- **Test-file rows:** `changed` means Phase 1 requires an edit to the file.
- **Why this rule:** most rows already followed it, including the critic's Case B (MCPW-4, -6, -12, -14; MD-2, -7, -18, -19). It can also be checked by machine against the lines the design cites (`fill-work/fate_rule_check.py`).
- **Moved from `changed` to `unchanged` (10 rows):** engines-56, MCPW-2, MCPW-3, MCPW-11, MCPW-25, MCPW-34, MCPW-36, MCPW-37, MCPE-11, MCPE-13.
  - **What each row keeps:** its W id moves to `phase1_related`, and its fate keeps the surveyor's text after the new decision.
  - **The critic's six:** engines-56, MCPW-2, MCPW-3, MCPW-11, MCPW-25 and MCPW-37 (Case A).
  - **Four more of the same kind:** MCPW-34 and MCPW-36 already pass the workspace (`:1963`, `:2019`). MCPE-11 and MCPE-13 reach `_evaluate_and_flip` only through a callee.
  - **Why MCPW-11 moves:** the calls at `:1236`, `:1617`, `:1694` and `:2022` pass no `feature_dir`, and `:1966` passes one. W2.2 keeps the parameter.
  - **One caveat, MCPW-25:** `verify-p0/verdict.md:159` lists its handler's docstring (`:1686-1692`) as text W2.2 leaves stale. The design names no sweep for it, so the row stays `unchanged`; if Phase 1 sweeps that docstring, the row's lines change.
- **Still `changed`, with its line corrected:** engines-1 read `102`. Its fate cites the fall-through at `engine.py:105`, which W1.5 edits, so its line is now `102-105`.
- **Range corrected:** MCPW-29's handler ended at `:1852`, the first decorator of `_process_reconcile_apply`, which W1.4 deletes. `_process_reconcile_check` ends at `:1849`.
- **tests-72 moved from `changed` to `unchanged`:**
  - **The merged claim:** two files' `_project_meta_json(db, None, type_id, <dir>)` calls "lose the feature_dir argument under W2.2".
  - **What the design says:** design:278 describes only the branch with no `feature_dir` (`:451-454`). `verify-p0/verdict.md:159` says init_feature_state's call at `:1966` "passes `feature_dir` and is unchanged".
  - **What the files do:** both pass the directory (`test_c9_c12_projection_identity.py:69`; `test_projection_determinism.py:127-308`, 8 calls), so no file in the aggregate needs an edit.
  - **Also corrected:** section 7.3's bullet.
- **fill-3 is `changed`:** its complete_phase case builds the engine with `artifacts_root = {TMPDIR}/features` (`:286`, `:330`) and seeds `artifact_path = {TMPDIR}/features/999-mock-feature` (`:303`).
  - **What W2.2 does there:** it names `{artifacts_root}/features/{name}` and writes nothing when that directory is missing (design:279, :281).
  - **The effect:** the check at `:345-361` would fail. This is inferred from the design and the test's paths; the test was not run.
- **The checks:**
  - `fate_rule_check.py` found 12 mismatches on the merged inventory (the 10 rows, engines-1 and MCPW-29) and 0 after this round;
  - the critic's `critic-work/fatecheck.py` still reports 0 exceptions.
- **The engines counts:** the merge reproduced the engines survey's own 11/20/63 by counting engines-56 as changed. Under the one rule they are 11/19/64.

**X3: schema-32 after Phase 1**
- **New field:** `workspace_scoped_after_phase1`, on schema-32 only. It reads `optional`: the lookup is scoped when a workspace is given, and with none an ambiguous type_id is refused (design:263-265).
- **Sections 6.2 and 6.3** now use it: 6.2 has 40 rows and 6.3 has 15.
- **The other four 6.2 rows Phase 1 changes** keep their unscoped reads, as the critic says:
  - engines-33: `feature_lifecycle.py:566`, a `db.get_entity` that design:287 keeps ("validate, as today");
  - MCPW-21: `workflow_state_server.py:436`, a `db.get_entity`;
  - MCPW-11 and MCPW-25: they reach that same read.

**Observation O1 (critic section 4), recorded as notes**
- **The asymmetry:** schema-35 (`update_workflow_phase`) and schema-36 (`upsert_workflow_phase`) emit no v2 event. Their docstrings say "deliberately EXCLUDED from v2 dual-write duty" (`database.py:10075`, `:10195`).
- **The contrast:** `create_workflow_phase` emits `workflow_established` (`:10026`, schema-33).
- **Why it matters:** it bears on criterion 6.

### 10.4 Rejected, and why

- **"34 un-prefixed values ... which the inventory does not mention"** (critic 3.3): section 3's `depends_on_features` row and section 8.4 both give "106 entries: 72 `feature:` type_ids ..., 34 bare ids".
- **M1's doctor citation:** the critic gives `doctor/check_status_write_path.py:41`, but the name is at `:42` (`:41` is the comment line above it). M1 stands, and fill-1's notes give the right line.
- **Everything else stands:** nothing else in M1–M3 or X1–X3 was wrong. The Case B rows in X2 were already `unchanged` under the one rule, so they needed no change.

### 10.5 Counts after this round

| Scope | Rows | Phase-1 classes | Survive Phase 1 |
|---|---|---|---|
| all rows | 369 | 12 deleted, 53 changed, 304 unchanged | 357 |
| sites other than test files | 289 | 12 deleted, 32 changed, 245 unchanged | 277 |
| test-file rows | 80 | 0 deleted, 21 changed, 59 unchanged | 80 |

- **Before this round:** 366 rows; 12 deleted, 63 changed, 291 unchanged. Sites other than test files: 287, of which 12 were deleted, 42 changed and 233 unchanged, so 275 survived. Test-file rows: 79 (0/21/58).
- **Why the figures moved:**
  - three rows were added: fill-1 and fill-2 are unchanged, and fill-3 is changed;
  - ten rows moved from changed to unchanged, and so did tests-72.
- **Section 6:** 6.1 is unchanged (36 `get_entity` call lines take a type_id; 34 survive). 6.2 has 40 rows (was 41) and 6.3 has 15 (was 14).

### 10.6 Critic observations outside R0, checked and not made into rows

- **O2, recovery threads:** confirmed.
  - **What they set:** `_start_recovery_thread` sets `_db`, and in the workflow server also its engines and roots.
  - **What they leave:** `_project_id` and `_workspace_uuid` stay `""` (`workflow_state_server.py:137-144`, `:170-206`; `entity_server.py:63-70`, `:98-126`).
  - **Where it is recorded:** in fill-2's notes. W4.2 deletes these threads in Phase 2.
- **O3, docs that restate the key:** `README_FOR_DEV.md:451` still says `delete_entity` deletes workflow_phases rows; schema-44 records that the delete is soft. Docs belong to W5's sweep, not to R0's rows.
- **O4, test-hooks.sh:** it drives session-start.sh's reconciliation against a throwaway DB and makes no API or SQL call itself, so by the inventory's rule it gets no row.

### 10.7 How this file was made

- **Rebuild order:** `synth-work/merge.py`, then `fill-work/fill.py`, then `fill-work/build_md_fill.py`.
  - `fill.py` starts from `fill-work/inventory.pre-fill.json`, the merge's output, so re-running it is idempotent.
  - After a new merge, delete that file first.
- **`build_md_fill.py`:** it runs the synthesizer's `build_md.py` with these text changes, then adds this section:
  - area `fill` in 5.1;
  - the one-rule text in 1.3 and 5;
  - 6.2 and 6.3 by scope after Phase 1;
  - tests-72's counts, the 7.3 W2.2 bullet and a shell-test line in 7.1.
- **Checks:** `fill-work/fate_rule_check.py`, with its outputs `fate_rule_check.out` (after) and `fate_rule_check.pre-fill.out` (before).
- **Read-only:**
  - no tracked file was edited, staged or committed;
  - `.pd-worktrees/followups-1a` was not touched;
  - the live registry was opened only with `immutable=1`.
- **Live fingerprint after this round:** `1790286038 4083712`, sha256 prefix `2814bb4434e8faa0`, no `-wal` or `-shm` file. This is unchanged.
