# Release C follow-ups: triage and design

- **Date:** 2026-09-25. **Base:** develop `84fc9376`.
- **Status:** rev 2.1.
  - Rev 1 went through an independent premortem and two prototype-based code verifications; rev 2 absorbs them.
  - Rev 2.1 absorbs what the implementation plan's review and calvin found in the design.
  - See "Review record".
- **Scope:** the 11 follow-ups recorded in `docs/plans/2026-09-22-structural-identity-completion-plan.md:883-902`, 12 more problems the investigation found (N1–N12), and one found at planning (N13).
- **Evidence:** `agent_sandbox/2026-09-25/release-c-followups/`.
  - `I1`–`I6`: one investigation per group of problems, each with a report and its probes.
  - `I1-verify`–`I6-verify`: an independent verdict on each report.
  - `design-review/`: the premortem and the two code verifications of rev 1, with their prototypes.
  - A figure below comes from a verdict unless it is marked "(report)".

## How it was investigated

1. **Six investigators**, one per group of related problems:
   - I1: problem 1;
   - I2: problems 2 and 4;
   - I3: problem 3;
   - I4: problems 5 and 7;
   - I5: problems 6 and 8;
   - I6: problems 9, 10 and 11.

   Each one:
   - read the code;
   - reproduced the problem on temp databases, temp repos and a temp HOME;
   - measured live exposure read-only.
2. **Six verifiers**, each independent of the report it checked, tried to refute every checkable claim by re-running the probes or writing smaller ones.
   - **Result:** 285 claims held, 42 were wrong and 10 could not be checked.
   - **Corrections:** every correction is folded in here.
3. **Nothing was changed.**
   - **Live registry:** read only through `immutable=1`. Its fingerprint is unchanged: `1790286038 4083712 2814bb4434e8faa0`.
   - **Stray file:** one probe that ran old commits' code wrote `.claude/pd/migrations/migration-11-workspace-mapping.json` (`{}`) into the main checkout. It was removed.

## Triage

**Severity scale:**
- **critical:** silent corruption triggered by routine use;
- **high:** corruption needing a plausible trigger, or a routine workflow broken;
- **medium:** a wrong answer in a real but uncommon case;
- **low:** latent, cosmetic or docs.

**Priority:**
- **P0:** must land before the pd plugin is re-enabled. It harms on first use.
- **P1:** fix in this round.
- **P2:** cheap cleanup in this round.
- **Deferred:** recorded, each with the event that should reopen it.

### The 11 recorded follow-ups

| # | Problem | Verdict | Severity | Priority | Workstream |
|---|---------|---------|----------|----------|------------|
| 1 | Shared type_ids across workspaces | Confirmed, with corrections | high by the scale (one silent cross-workspace row write); small live impact | P0 (writer API) and P1 (the rest) | W2, W3 |
| 2 | Namesake directories cross workspaces | Confirmed, broader | high as a class; live: one pending cross-workspace create | P0 | W1 |
| 3 | One-sided workspace failure | Confirmed; the premise was wrong, and a real trigger exists | low | P1 | W4 |
| 4 | `create_key_result` parent lookup | Confirmed | low (latent) | P1 (bundled with N4) | W3 |
| 5 | A fresh worktree archives every feature | Confirmed, and it has already fired | high | P0 | W1 |
| 6 | Writer and reader use different checkouts | Confirmed, far broader (N1, N2) | high | P0 | W2 |
| 7 | `detect_project_root` matches only a `.git` directory | Confirmed, wider | medium | P1, after W1 | W4 |
| 8 | `backfill_workflow_phases` reads the raw stored path | Confirmed | low | P0 (lands with W2) | W2 |
| 9 | `display.rename_entity` breaks the column invariant if wired up | Confirmed | low (latent) | P2 | W5 |
| 10 | Unguarded shell tests | Confirmed | low | P2 | W5 |
| 11 | README board sentence | Confirmed, plus two more inaccuracies | low (docs) | P2, needs the user | W5 |

### Found by the investigation (N1–N12)

| # | Problem | Severity | Priority | Workstream |
|---|---------|----------|----------|------------|
| N1 | **`/pd:create-feature` fails at its first phase step.** Since `bf860814` (feature 134, 2026-07-25), the feature is registered without `artifact_path` and activation projects nothing. So `transition_phase` answers "Feature not found" on both the deep and express lanes. No feature has been created since, which is why nobody noticed. | high | P0 | W2 |
| N2 | **Decomposed features cannot be activated.** Nothing creates their directory, and `activate_feature` requires it. | high | P0 | W2 |
| N3 | **The degraded-start recovery threads never recover.** Both servers open the DB on a worker thread. FastMCP runs tools on the loop thread, so every later call errors. Broken since `e2bda23a`. | low | P1 | W4 |
| N4 | **`set_parent` links across workspaces.** It resolves type_ids unscoped, and turns a uuid ref back into a type_id before writing. Several other entity tools share the pattern. | medium | P1 | W3 |
| N5 | **`reconcile_status` reports unhealthy in every workspace.** `workflow_state_server.py:2074` drops the workspace. In pedantic-drip, 131 rows with no `.meta.json` would keep it unhealthy even when scoped. | low | P0 (in W1) | W1 |
| N6 | **Cascade recovery misbehaves at every session start.** It fails on the shared `project:P001`: `rollup.py:373` and `dependencies.py:184` write by type_id, and the error is swallowed. It also rewrites pedantic-drip's `project:006-memory-flywheel` from every workspace's session. Task 3 (`dependency_freshness`) is unscoped in the same way. | low | P0 (in W1) | W1 |
| N7 | **Rows archived by problem 5 in the past.** | — | Decision D2 | — |
| N8 | **A stale `.meta.json` rolls DB status back** (reproduced: completed back to active). It is the same code as problem 5. | high | P0 (removed by W1) | W1 |
| N9 | **Five more hook shell tests** that nothing runs. | low | Deferred | — |
| N10 | **The C11 design's reason for leaving `rename_entity` alone is false** (`2026-09-25-c11-name-not-path-design.md:205`). The live registry has an `events` table and an `entity_id` column. The claim came from a fresh v1 database, which has no `events` table. | low (doc) | P2 | W5 |
| N11 | **`/pd:create-project`'s cross-workspace-parent refusal is labelled `invalid_transition`.** It also burns an allocated number. | low | P1 | W4 |
| N12 | **A new repo's first session cannot allocate ids.** With no `.claude/` and no workspaces row, the entity server resolves no workspace at startup, so `allocate_entity_id` refuses until a restart. This is the real trigger for problem 3's split. | medium | P1 | W4 |
| N13 | **16 repo-root script tests fail on develop, outside every gate.** Added at planning. <br>- `scripts/test_migrate_db.py::TestMigration6` (7) asserts a retired schema: `post_version == 8` against 25, and the columns `parent_type_id` and `entity_type`, and the table `entity_dependencies`. <br>- `scripts/test_migrate_e2e.py` (9) passes the caller's `ENTITY_DB_PATH` through to `migrate.sh`, which prefers it over the test's own HOME. So a temp-DB environment fails every test, and one pointed at the live registry would let the import tests write it. | medium (the isolation hole); low (the stale tests) | P2 | W5 |

### What the live data says

- **Problem 5 has already fired:**
  - 2026-05-17T04:34:01Z: 126 rows archived in 28 ms. 124 of today's 127 archived pedantic-drip features come from this batch.
  - 2026-06-20: 2 features (112, 113).
  - 2026-07-10: 15 planned P004 features, restored an hour later.
  - 2026-05-28: illium, 1 brainstorm.
  - It also re-stamps `updated_at` on 128 archived rows at every session start.
- **Problem 1:**
  - The 7 shared type_ids are permanent. Soft-deleted rows still count in `_resolve_identifier`, and v2 forbids hard deletes (the `events` foreign key plus `events_no_delete`).
  - Six live entities return 404 from their board card link today: pedantic-drip's features 002, 003 and 004, both brainstorms, and `P001`. The links carry the type_id; the detail route already answers by uuid.
  - No shared type_id has arisen naturally except the retired slugless `P001`.
- **Problem 6 / N1:** stored `artifact_path` shapes across the 271 feature rows:
  - 162 relative;
  - 67 absolute into pedantic-drip;
  - 42 absolute elsewhere;
  - 0 null.
- **The file→registry writers do no useful work.** Across all 9 local checkouts at their current HEADs, session-start Tasks 1 and 2 make 0 writes to their own workspace. Every write they would make is wrong: an archive, a status regression, or a cross-workspace row.
- **Brainstorms are registered only by session start.** `/pd:brainstorm` creates no entity (`commands/brainstorm.md:20`). The brainstorm helper's registration half is their only path into the registry.

## Root causes

1. **The checkout's files write the registry.**
   - **Where:**
     - session-start Task 1 (feature and project status and archive from `.meta.json`; brainstorm archive from a missing `.prd.md`);
     - Task 2 (`workflow_phases` from `.meta.json`);
     - the engine's lazy hydration;
     - the startup backfill's status and phase read.
   - **Why it's wrong:** the workflow-state skill says those files are projections, never to be trusted over the DB (`plugins/pd/skills/workflow-state/SKILL.md:10`).
   - **Problems:** 2, 5, 8, N5, N8.
2. **The stored `artifact_path` is used as a filesystem path.** C11 moved the engine to naming a feature's directory from its `entity_id`, but not the projection writer, the finish check, task promotion or the backfill. The value is also missing from every feature registered since feature 134.
   - **Problems:** 6, 8, N1, N2.
3. **Lookups by `type_id` ignore the workspace.**
   - **The key:** `workflow_phases` is keyed by `type_id` alone, a relic of migration 3.
   - **Three unscoped lookups settle ambiguity three different ways:**
     - `get_entity` answers None;
     - the autofill trigger takes the smallest `workspace_uuid`, because the insert APIs never pass one;
     - `create_workflow_phase`'s fallback takes the lowest rowid.
   - **Problems:** 1, 4, N4, N6.
4. **Workspace and root resolution fail without saying so.**
   - **Where:**
     - registering tools fall back to `__unknown__`;
     - the recovery threads never finish;
     - `detect_project_root` tests `-d .git`.
   - **Problems:** 3, 7, N3, N11, N12.

## Decisions for the user

Each has a recommended default. The plan follows the default unless the user rules otherwise.

- **D1. Delete the file→registry writers (recommended), or keep them scoped.**
  - **Delete:** W1 as designed. It strands nothing: 0 statuses change across 9 checkouts at HEAD.
  - **Brainstorm archiving:** it moves to `/pd:cleanup-brainstorms`, which archives explicitly.
  - **External repos:** repos whose committed `.meta.json` changes without pd lose the automatic import. A per-workspace import is recorded as deferred.
  - **Keep scoped:** a larger change. The workspace becomes required through the whole reconciliation path, and it still has to handle the archive and regression cases.
- **D2. Rows the bug archived in the past: leave them (recommended), or restore them.**
  - **The projects need nothing.** The two then-active projects it hid (`P002-memory-flywheel`, `P003-entity-system-redesign`) were superseded by C22's recreated `006-memory-flywheel` and `007-entity-system-redesign`, so un-archiving them would bring back duplicates.
  - **What's left is 125 completed features.** Archiving only hides a row from the board and two list filters (`board.py:74`, `workflow_state_server.py:678`).
  - **Restoring** puts them back in the board's Completed column. After W1, `update_entity(archived=false)` does it through MCP; it is a gated live write either way.
- **D3 ruling (2026-09-26): the re-key is in this round.** It goes through a survey, an inventory, a playbook and manual, and independent agent verification before execution, and it must be consistent with this design and future-proof.
  - **Where it's planned:** Phase R of the implementation plan.
  - **What it supersedes:** the "Deferred" rows for the re-key and for the read-scoping and type_id-only writers.
  - **What it absorbs:** W3.1–W3.3's contracts, restated by Phase R's playbook.
  - **The options offered, kept for the record:** the next bullet.
- **D3 (as offered). Shared type_ids: guard now, defer the re-key (recommended).**
  - **Now:** W2 and W3 stop the silent writes and fix the visible symptoms.
  - **Deferred (A):** re-keying `workflow_phases` by entity uuid (a migration plus about 45 call sites) waits until two workspaces must run live workflows on one type_id.
  - **Deferred (B):** refusing, at registration, a type_id another workspace holds would change feature 109's per-workspace identity design. It waits for a natural collision.
- **D4. README.md.** The one-line fix to `README.md:80` touches a file holding the user's uncommitted edits (they don't overlap line 80).
  - **Default:** the plan hands the user a one-hunk patch instead of committing it.
- **D5. Cross-workspace links: keep feature 129's rule (recommended), or adopt C22a's everywhere.**
  - **The two rules:**
    - feature 129 made cross-workspace links ordinary (commits `96df3398`, `d6b8eda3`; pinned by 4 tests);
    - C22a's `reparent_entity` refuses them, and says no new path may add more.
  - **What W3 does:** it adds no link path. A type_id resolves only in the caller's workspace, and an explicit uuid may still point anywhere.
  - **Adopting C22a's rule everywhere** would make `set_parent` and the dependency and alignment tools refuse cross-workspace uuids, and rewrite feature 129's 4 tests.

## Designs

### W1. The checkout's files stop writing the registry

**Problems:** 2, 5, N5, N6, N8. **Principle:** pd's own writers write the registry. Nothing reads a projection, or a file's absence, back into it.

**Changes:**
1. **Delete Task 1's archive and status passes.**
   - **Remove:**
     - `entity_status._sync_meta_json_entities` (`entity_status.py:24-93`);
     - its two entries in `sync_entity_statuses` (`:135-136`);
     - `STATUS_MAP` (`:15`);
     - Part 2 of `_sync_brainstorm_entities`, which archives a brainstorm whose `.prd.md` is missing (`:211-233`).
   - **Rewrite:** the module docstring, and the comment at `:170` that points at the deleted function.
   - **Keep:** Part 1 of the brainstorm helper (`:180-209`). It registers new `.prd.md` files and is the only path by which brainstorms reach the registry.
   - **Result keys:** only `test_orchestrator.py` reads them, so it follows whatever the remaining helper returns.
2. **Archive brainstorms explicitly.**
   - **The tool:** the `update_entity` MCP tool gains `archived: bool | None = None`, which calls `db.set_archived(<resolved uuid>, archived)`. The tool count is unchanged.
   - **The command:** `/pd:cleanup-brainstorms` step 4 calls `update_entity(type_id="brainstorm:{stem}", archived=true)` instead of writing the retired status `"archived"` (`commands/cleanup-brainstorms.md:25`).
   - **Sweep:** other markdown writing `status="archived"`.
   - **Docs that list `update_entity`'s parameters** gain `archived`: `docs/technical/api-reference.md:135-141`, `README_FOR_DEV.md:447`, `plugins/pd/README.md:130`.
3. **Delete Task 2's writers.**
   - **Remove:**
     - the orchestrator's Task 2 (`reconciliation_orchestrator/__main__.py:126-142`);
     - its `workflow_reconcile` result key (`:94`);
     - its mention in the module docstring (`:1-14`);
     - its display in `session-start.sh:523-539`.
   - **In `reconciliation.py`, remove:**
     - `_reconcile_single_feature` (`:398`);
     - `apply_workflow_reconciliation` (`:847`);
     - `_build_reconciliation_result` (`:941`);
     - `ReconcileAction` and `ReconciliationResult` (`:105`, `:127`);
     - `format_reconciliation_summary` (`:973`; only its tests use it).
   - **Keep:** `check_workflow_drift` and the read-only helpers it uses.
4. **Delete the `reconcile_apply` MCP tool.** No command, skill, agent, hook or script calls it.
   - **Code to remove:**
     - `workflow_state_server.py:2505-2519`;
     - `_process_reconcile_apply` (`:1852-1890`);
     - `_serialize_reconcile_action` (`:321-337`);
     - the imports at `:78` and `:80`.
   - **Counts to update:**
     - `plugins/pd/README.md:149` ("exposes 24 tools" becomes 23), which `validate.sh`'s `scripts/check-doc-drift.sh` checks;
     - `README_FOR_DEV.md:476`.
   - **Tool lists to update:**
     - `plugins/pd/README.md:163`;
     - `README_FOR_DEV.md:485`;
     - `docs/technical/api-reference.md:63-69`;
     - `docs/dev-guide/architecture-overview.md:120`, `:122` (drift "repaired by reconcile_check / reconcile_apply"), `:131` and `:133`.
   - **Done when:** `git grep -n reconcile_apply -- ':!CHANGELOG.md' ':!docs/plans' ':!docs/features'` prints nothing.
   - **Tests:**
     - three modules import the deleted names, so they fail collection: `test_reconciliation`, `test_c11_reconciliation_dir_name` and `test_workflow_state_server`;
     - two more reference them: `test_orchestrator` and `test_c11_mcp_dir_name`;
     - `test_feature_134_trustgate.py` imports from one of them.
5. **Delete the lazy hydration write.**
   - **What goes:** `engine._hydrate_from_meta_json` (`engine.py:592-654`).
   - **What `get_state` answers instead:** None when the DB has no row.
   - **Where rows come from:**
     - activation, for new and decomposed features (W2 change 5);
     - the startup backfill, for everything else (W2 change 6).
   - **What stays:** the degraded-mode read `_read_state_from_meta_json`, which only reads. It is reached from `get_state`'s other two branches (health failure, `sqlite3.Error`), which are unchanged.
   - **Sweep:** the docstrings that name `_hydrate_from_meta_json` (`engine.py:467`, `:514`).
6. **`reconcile_status`: scoped, and a missing projection isn't drift.**
   - **Scoped:** it passes the workspace to `check_workflow_drift` (`workflow_state_server.py:2074`).
   - **Health:** only features whose DB state and projection disagree (`db_ahead`, `meta_json_ahead`) make it unhealthy.
   - **Listed but not counted:** `db_only` (no projection) and `meta_json_only` (no row).
   - **Docs:** the docstring and the tool description say so.
7. **Cascade recovery becomes its own task, scoped and by uuid.**
   - **Its own task:** the orchestrator's new Task 2 calls `_recover_pending_cascades(db, workspace_uuid)` directly. Until now it ran inside `apply_workflow_reconciliation` (`reconciliation.py:908`).
     - **Unresolved workspace:** skipped, and recorded under `errors`.
   - **Scoped:** its scans (`reconciliation.py:618`, `:666`) cover only the session's workspace.
   - **Rollup stops at the workspace's edge:** a rollup stops at the first ancestor outside that workspace.
   - **Writes by uuid:**
     - the rollup writes (`rollup.py:196`, `:267`, `:373`; `reconciliation.py:690`) pass the uuid they already hold;
     - `DependencyManager._evaluate_and_flip` writes status and its phase event by the entity's uuid (`dependencies.py:184-185`), and drops its `"__unknown__"` project fallback.
8. **Task 3 is scoped.** `dependency_freshness.cleanup_stale_dependencies` takes the session's workspace, and lists only that workspace's blocked entities (`dependency_freshness.py:25`). With no workspace, it is skipped.

**Tests.** Each one fails on today's develop and passes after:
- **No archive:** a session start in a checkout with registered features and no `.meta.json` leaves every row's `is_archived` and `updated_at` unchanged. Today it archives.
- **No brainstorm archive:** a session start in a checkout that lacks a registered brainstorm's `.prd.md` leaves it unarchived. Today it archives.
- **Explicit brainstorm archive:** `update_entity(archived=true)` sets `is_archived`. Today the parameter doesn't exist.
- **No regression:** a session start with a stale `.meta.json` (`active`) for a completed feature leaves the DB status `completed`. Today it regresses.
- **No namesake row:** a session start with a namesake `.meta.json` of a feature only another workspace holds creates and changes no `workflow_phases` row. Today it creates one owned by that workspace.
- **No hydration write:** `get_phase` for a row-less feature whose `.meta.json` exists creates no row. Today it creates one. The shared-type_id form can't be tested: `get_entity` answers None there and hydration writes nothing.
- **Scoped, healthy status:**
  - `reconcile_status` in workspace A, with features only B holds, omits them;
  - a completed row with no `.meta.json` leaves it healthy.
  - Today it is unhealthy.
- **Rollup by uuid:** cascade recovery with `project:P001` held by two workspaces updates the session's parent by uuid. Today it raises `Ambiguous`.
- **Dependency flip by uuid:** a blocked dependent whose type_id another workspace also holds flips to `ready`. Today it raises `Ambiguous`.
- **Task 3 scoped:** another workspace's blocked entity is never flipped.

**Corrections absorbed:**
- **"The main checkout archives 0" is wrong.** Every session re-flags 128 rows (ver4).
- **"The DB is the sole truth everywhere" is wrong** outside pd. External repos commit projections that change without pd, and Task 1 once imported 17 illium statuses. Deleting still strands nothing: 0 statuses change across 9 checkouts at HEAD (ver2, ver4).
- **"Tracked brainstorm files are in every checkout" is wrong.** Branches and worktrees lack recent ones, and the brainstorm archive fires there (premortem story 1). So it is deleted here, not kept.

### W2. Name, not path: feature directories, activation, and the row writers

**Problems:** 1 (the writer API), 6, 8, N1, N2.

**Changes:**
1. **The row writers take the workspace, and never guess it.** Moved into Phase 1 from W3: without it, this workstream can't store the workspace it promises (premortem story 5; verify-p0).
   - **`create_workflow_phase(type_id, *, workspace_uuid=None, …)`** (`database.py:9951-10046`):
     - resolves the entity with `_resolve_identifier(type_id, workspace_uuid=workspace_uuid)`. That is scoped when a workspace is given, and must be globally unique otherwise, so ambiguity is refused;
     - inserts the resolved entity's `type_id`, `workspace_uuid` and `uuid` explicitly, so the autofill trigger never guesses.
   - **`upsert_workflow_phase`** (`:10181-10294`):
     - resolves the entity the same way;
     - inserts `workspace_uuid` and `uuid` (today's `INSERT OR IGNORE` omits both, `:10274-10278`);
     - refuses, rather than overwrites, a row that belongs to another workspace;
     - drops its `project_id="__unknown__"` default.
   - **Callers pass their workspace:**
     - `activate_feature` (change 5);
     - `init_feature_state` (`feature_lifecycle.py:305`);
     - `promote_task` (`task_promotion.py:403`);
     - the backfill (change 6).

     The other callers are deleted by W1 (`engine.py:633`, `reconciliation.py:495`).
2. **`_project_meta_json` names the directory.** With no `feature_dir` argument (`workflow_state_server.py:451-454`):
   - **Features:** `{artifacts_root}/features/{name}`. The name comes from `feature_dir_name(db, artifacts_root, type_id)`, plus the engine's containment check (`engine._feature_dir_name`).
   - **Projects:** `{artifacts_root}/projects/{last component of artifact_path}`, with a trailing `/` stripped first. 6 of 16 project entity_ids differ from their directory names, so the entity_id can't name them.
   - **Returns a warning and writes nothing when:** the name is refused, or the directory doesn't exist. The caller's write has already committed.
   - **`artifacts_root`** comes from the engine, or the server global when the engine is None.
3. **`_check_artifact_completeness` names the directory** the same way (`:1279-1315`), instead of `artifact_path`.
4. **`promote_task` names the directory** the same way (`task_promotion.py:317-322`). It gains an `artifacts_root` parameter, which its wrapper (`workflow_state_server.py:2716`) fills from `_artifacts_root`. It stays: it is `query_ready_tasks`'s only producer of task entities.
5. **`activate_feature` seeds the row, in one transaction** (`feature_lifecycle.py:548-584`).
   - **Inside one `db.transaction()`:**
     1. validate, as today;
     2. with no `workflow_phases` row, create it through change 1, with `kanban_column=_kanban_column_for("active", None)`, `workflow_phase` None and the caller's `workspace_uuid`;
     3. flip the status.
   - **Why one transaction:** a lock between the two writes can't strand the feature. `@_with_retry` re-runs the whole call, and the transaction is not re-entrant.
   - **Then:** the projection follows, through change 2.
   - **No directory creation.** A session and a server rooted in different checkouts keep today's loud `feature_not_found`, instead of passing against an empty directory (premortem story 2).
   - **Fixes N1:** `transition_phase` finds the row.
6. **The startup backfill reads no files, and stays in its workspace** (#8).
   - **No file reads:**
     - delete `_resolve_meta_path` (`backfill.py:127-152`) and every `.meta.json` read in `backfill_workflow_phases`;
     - status comes from the registry (today a `.meta.json` status wins, `:335-340`);
     - a feature's `workflow_phase` is `finish` when completed, otherwise None;
     - `last_completed_phase` and `mode` stay None.
   - **Scoped:**
     - iterate only the server's workspace (`:254`);
     - pass `workspace_uuid` to every write (`:317`, `:326`, `:395`);
     - an unresolved workspace skips the backfill.
   - **Why:** on a live copy, the unscoped run creates `feature:035`'s row for the wrong workspace (ver1, ver2, verify-p0).
7. **Decomposed features get their directory at activation.** The workflow-state skill's "Activating a planned feature" steps (`skills/workflow-state/SKILL.md:14-20`) run `mkdir -p {pd_artifacts_root}/features/{id}-{slug}/` before `activate_feature`, as `commands/create-feature.md:19` already does. This fixes N2.

**Tests.** Each one fails today:
- **Deep lane:** the create-feature sequence, through the real `_process_*` functions wired the way the servers wire them: allocate, mkdir, `register_entity` with no `artifact_path`, activate, then `transition_phase(specify)`. The transition succeeds, and the row's phase is `specify`.
  - **Why this test:** the only end-to-end test today (`test_workflow_state_server.py:5574`) starts from `init_feature_state`, which hides the break.
- **Express lane:** the same, then `record_mini_spec` and `transition_phase(implement, skipped_phases=…)`, which succeeds.
- **Decomposed, the skill:** the workflow-state skill's "Activating a planned feature" steps run `mkdir -p {pd_artifacts_root}/features/{id}-{slug}/` before `activate_feature`. Today the step is missing.
- **Decomposed, the transition:** register with no directory, mkdir as the skill says, then activate. The row exists right after activation, and `transition_phase(specify)` succeeds. Today the transition answers "Feature not found" (N1).
- **Every lane:** each lane test asserts the row, with its `workspace_uuid` and `uuid`, right after `activate_feature` and before any engine read. Otherwise hydration, which still exists until W1.5 lands, could create the row and hide a missing seed.
- **Activation retry:** inject "database is locked" on the status write. The retried activation succeeds, and one row exists.
- **Worktree projection:** a feature whose stored `artifact_path` is absolute into the main checkout, projected from a session rooted at a worktree, writes `.meta.json` in the worktree.
- **Explicit workspace:** `create_workflow_phase` for a type_id two workspaces hold, given workspace A, stores `workspace_uuid == A` and the entity's `uuid`. Today it has no parameter.
- **Upsert refuses:** `upsert_workflow_phase(workspace_uuid=A)` on B's row raises, and B's row is unchanged. Today it overwrites.
- **Backfill scope:**
  - B's NULL-phase brainstorm row is left alone by a server whose workspace is A (today it is rewritten through `:317`);
  - a shared type_id's missing row is seeded for the calling workspace (today, for the smallest uuid).
- **Backfill source:** a feature whose `.meta.json` says `active` while the registry says `completed` is seeded `finish` / `completed`. Today the file wins.

**Corrections absorbed:**
- **"C11 removed this blocker (R01/F1)" is wrong.** C11 never changed registration (ver5).
- **Rev 1's "explicit workspace" needed an API that didn't exist until Phase 2** (premortem story 5; verify-p0).
- **Rev 1's activation `mkdir` hid a wrong-checkout session** (premortem story 2).
- **Rev 1's backfill test passed on develop,** so it was vacuous. It is replaced (verify-p0).

### W3. Identity across workspaces: fix what users see, and scope the entity tools

**Problems:** 1, 4, N4.

**Changes:**
1. **The board query matches the workspace** (`database.py:10355-10390`).
   - **The join:** `LEFT JOIN entities e ON wp.type_id = e.type_id AND wp.workspace_uuid = e.workspace_uuid`, selecting `e.uuid AS entity_uuid`.
   - **The workspace filter:** it reads `wp.workspace_uuid`, not `e.workspace_uuid`.
   - **Orphans:** with a workspace given, it drops `OR e.uuid IS NULL`, so an orphan row shows only in the all-workspaces view.
   - **Measured:** on live data, 529 rows with 0 unmatched, against 534 today.
2. **Links by uuid.**
   - **The templates** link the entity uuid: `_card.html:1`, `_entities_content.html:73`, `entity_detail.html:83` and `:98`. The route `/entities/{identifier}` already accepts one.
   - **The lineage graph** links by uuid (`mermaid.py:67`).
   - **The Entities page** keys its workflow lookup by entity uuid (`ui/routes/entities.py:23-28`, `:103-106`).
   - **The detail page** picks its workflow row by `entity_uuid` (`:192-195`).
   - **An orphan card** (a row with no entity) keeps its type_id link.
3. **The remaining writer guards.**
   - **The `update_entity` re-attribution cascade** (`:8763-8777`) reads the old workspace before the entities UPDATE, and adds `AND workspace_uuid = <old>`.
   - **`append_phase_event`'s unscoped fallback** (`:9811-9815`) raises on ambiguity, the way `_resolve_identifier` does.
4. **Entity tools resolve type_id and ref parameters in the caller's workspace.**
   - **How:** `_resolve_ref_param` (`entity_server.py:316-360`) resolves a type_id or ref to a uuid inside `_require_workspace()`'s workspace (W4 change 1). An explicit uuid passes through unchanged. The tool then writes by uuid.
   - **The tools:**
     - `set_parent`, which calls `db.set_parent(child_uuid, parent_uuid)`, never re-resolving a type_id (`:974-1008`, `server_helpers.py:499`);
     - `add_dependency`, `remove_dependency` and `add_okr_alignment`;
     - `create_key_result`;
     - `update_entity`, `delete_entity`, `add_entity_tag` and `update_kr_score`.
   - **Confirmation texts:** still show type_ids.
   - **Unresolved workspace:** these tools call `_require_workspace()` (W4.1) themselves, as part of this change.
   - **What it keeps:** feature 129's four cross-workspace tests keep their assertions (D5):
     - `test_cross_workspace_matrix.py::test_t2b_5_cross_workspace_gate_matrix` (its `set_parent` case);
     - `test_cross_workspace_matrix.py::test_set_parent_cross_workspace_round_trip`;
     - `test_cross_workspace_mcp_regression.py::TestCrossWorkspaceMcpEnvelopeRegression::test_set_parent_cross_workspace_mcp_response_has_no_error_residue`;
     - `test_issue_spawn.py::TestAC95ParentValidation::test_cross_workspace_parent_spawn_succeeds`.

     The last one's fixture must set a workspace, since W4.1 removes the `__unknown__` fallback it relied on. The W3–W5 prototype failed it with `workspace_unresolved`.

**Named, and deferred with the re-key (D3):**
- **Writers keyed by type_id alone, when called without a workspace:**
  - `update_workflow_phase` (`:10164`);
  - `append_phase_event`'s step-5 projection (`:9780`);
  - `delete_workflow_phase` (`:10312`).

  Their production callers either pass a workspace or run on single-workspace ids.
- **`resolve_ref`'s exact-match branch** (`:7234-7236`) takes the first row.
- **`scripts/fix_kanban_columns.py:28`'s correlated subquery.**
- **The 39 unscoped `get_entity` reads.** They are scoped only after the re-key, or today's refusals become cross-workspace writes (ver1).

**Tests.** Each one fails today unless marked:
- **One card:** two workspaces hold `feature:X`, and one of them owns the row. The board query returns 1 row (today 2).
- **The card link works:** for a shared type_id, the rendered card link answers 200 with the owner's entity. Today it links the type_id, which answers 404.
- **Orphan scope:** a workflow row whose entity is in another workspace shows only in the all-workspaces view. Today it shows on every workspace's board.
- **Entities page:** two namesakes each show their own workflow status. Today both show the owner's.
- **Cascade:** re-attributing A's entity leaves B's row for the same type_id unchanged.
- **`set_parent` by type_id:** from workspace A, with a type_id only B holds, it answers not-found. Today it links B's entity.
- **`update_entity` by type_id:** from workspace A, with a type_id only B holds, it answers not-found. Today it updates B's entity.
- **`set_parent` by uuid (keep-green, passes today):** B's explicit uuid still links, per feature 129.
- **Unresolved:** with no resolvable workspace, `set_parent` given a type_id answers `workspace_unresolved`.

**Corrections absorbed:**
- **Guarding `register_entity` and `set_parent` with `refuse_deleted_or_cross_workspace_parent` is wrong.** It breaks 4 feature-129 tests (ver2).
- **Rev 1's detail-page test was vacuous:** the route already answers 200 by uuid. The broken thing is the link (verify-rest).
- **Rev 1 missed the display sites and the orphan filter** (verify-rest; premortem story 8).

### W4. Workspace and root resolution

**Problems:** 3, 7, N3, N11, N12.

**Changes:**
1. **Resolve on demand, then refuse.** Each server gets `_require_workspace()`.
   - **What it returns, in order:**
     1. `_workspace_uuid`, if set;
     2. otherwise, if `_project_root` is non-empty, `resolve_startup_workspace_uuid(_project_root)`, retried once;
     3. otherwise `db._resolve_optional_workspace_filter(None, _project_id)`, the existing lookup of the workspaces row whose `project_id_legacy` equals `_project_id` (`database.py:6896-6973`; the column is UNIQUE).
        - **Skipped** when `_project_id` is empty or `"__unknown__"`, which that method maps to the unknown workspace.
        - **Its `ValueError`** (no such row) means unresolved.
        - **Why it works:** the legacy id comes from the root commit, so it is the same from a subdirectory, a symlinked path, a worktree or a second clone.

     A success is cached.
   - **Still unresolved:** it raises the existing `workspace_unresolved` envelope. The hint names the server ("restart the pd entity-registry / workflow-engine MCP server from the repository root, or create `.claude/` there").
   - **Called by every tool that writes with a workspace:**
     - **entity server:**
       - `allocate_entity_id` (replacing its inline check, `entity_server.py:737-746`);
       - `register_entity`, when no `workspace_uuid` argument is given;
       - `issue_spawn`;
       - `create_key_result`;
       - the W3 change 4 tools, wired by W3.4 itself.
     - **workflow server:**
       - `activate_feature`, `transition_phase` and `complete_phase`;
       - `init_feature_state`, `init_project_state` and `init_entity_workflow`;
       - `transition_entity_phase`, `record_backward_event`, `record_mini_spec` and `promote_task`.
   - **Read tools** keep today's behaviour.
   - **What goes:** the `_project_id or "__unknown__"` fallbacks (`entity_server.py:633`, `:888`, `:1538`).
   - **Side effect:** a successful retry may write `.claude/pd/workspace.json`, the normal file of a pd project.
   - **What this fixes:**
     - problem 3's `__unknown__` writes, which become refusals;
     - N12, since by the first write the startup's `upsert_project` has bound the root commit's id to a workspace.
2. **Delete the recovery threads** (N3).
   - **What goes:** `_start_recovery_thread` in both servers (`entity_server.py:96-125`, `workflow_state_server.py:170-206`).
   - **After:** a degraded server stays degraded. `_check_db_available` answers "database unavailable (degraded start); restart the MCP server", no longer "temporarily".
   - **Why not fix them:** they have never worked, and a restart does the same job.
3. **Relabel the create-project refusal** (N11).
   - **The error:** the cross-workspace-parent refusal answers a `cross_workspace_parent` error type, instead of `invalid_transition`.
   - **The number:** its message names the allocated number that is now unused. Numbers are never reused.
   - **Where:** `feature_lifecycle.py` near `:487`, plus the envelope mapping.
4. **`detect_project_root` accepts a `.git` file** (#7).
   - **The test:** `-e` instead of `-d`, at `hooks/lib/common.sh:13`.
   - **One copy:** `scripts/doctor.sh` sources `common.sh` instead of keeping its own copy (`:48`), and uses `-e` at `:270`, `:310` and `:385`.
   - **Also:** `scripts/setup.sh:115`, and the repo-root finders in the hook test scripts: `test-hooks.sh:10`, `test-data-file-guard.sh:19`, `test-promptimize-content.sh:13`, `test-enriched-docs-content.sh:18`, `test-worktree-dispatch.sh:86` and `:132`.
   - **What changes for a session in a nested worktree:**
     - its hook state (`.claude/.yolo-hook-state`, `.claude/.plan-review-state`) and `pd-state.diff.md` live in the worktree;
     - a gitignored `.claude/pd.local.md` is absent there, so the defaults apply;
     - the workspace still resolves to the repository's.
5. **`sync-cache.sh` publishes only from the main checkout.**
   - **Detection:** when `git rev-parse --git-dir` and `--git-common-dir` differ, the session is in a linked worktree, and nothing is published.
   - **Why:** this stops a worktree publishing its branch's plugin, or the main checkout's half-edited one, over the shared cache (premortem story 9).
   - **Unchanged:** the main checkout, and a directory with no `.git` (a `git archive` export, as the gates and `test-hooks.sh` use), behave as today.
   - **The trade:** a developer editing the plugin in a worktree sees it in the cache only after it reaches the main checkout, as in Release C.
   - **`test-hooks.sh` Tests 13b and 13c** (`:341-413`) expect sync-cache to publish from wherever the suite runs. Run from a linked worktree, they skip with a note.

**Order:** change 4 lands only after Phase 1.
- **Why:** today problem 7 hides problems 5 and 6 in nested worktrees. A probe confirms that fixing 7 alone archives in every nested worktree (ver4, premortem story 1).
- **What Phase 1 removes:** every file-driven archive and status write.

**Tests.** Each one fails today:
- **Resolve on demand:** a first session in a new repo registers through both servers, with no restart, when started at:
  - the repository root;
  - a subdirectory;
  - a second clone.

  Today it refuses (entity server) or writes to `__unknown__` (workflow server).
- **`/pd:add-to-backlog` in a first session:** `init_entity_workflow` succeeds. Today it fails with "not found in project '__unknown__'".
- **Refuse:** a server with no resolvable workspace answers `workspace_unresolved` from `init_feature_state`, and writes no row.
- **Relabel:** create-project with another workspace's parent answers `cross_workspace_parent`.
- **Root detection:** in a nested linked worktree, `detect_project_root` answers the worktree's root. Today it answers the main checkout.
- **No archive from a worktree root:** after Phase 1, a session start in a nested worktree based on an older commit, rooted at the worktree, changes no row. This is premortem story 1's case. It passes only with Phase 1 in; red-first is shown on Phase 1's parent with the `-e` edit applied.
- **sync-cache:** run from a sibling worktree, it publishes nothing. Today it publishes the worktree's plugin.

**Corrections absorbed:**
- **"No routine case leaves only the workflow server unresolved" is wrong** (ver3).
- **Rev 1 wired the retry into two workflow tools, one of which nothing calls** (premortem story 4).
- **Rev 1's retry keyed on the path alone,** so it failed from a subdirectory, a symlink, a worktree or a second clone (verify-rest; premortem story 6).
- **Rev 1's sync-cache published the main checkout's working tree** from worktree sessions (premortem story 9).

### W5. Tooling and docs

**Problems:** 9, 10, 11, N10, N13.

**Changes:**
1. **Delete `entity_registry/display.py` and `test_display.py`** (22 tests).
   - **Also remove:**
     - its entries in `test_schema_v2.py`'s dark-module guard (`:524`, `:540-542`, and the three seeded self-tests);
     - the 8 stale comments that name it (`test_schema_v2.py`, `test_views.py:11`);
     - the docstring mentions (`events.py:33-37`, `database.py:8122-8124`, `axes.py:39-41`, `test_c22a_reparent_entity.py:7`).
   - **Measured:** the suite stays green at 4330 tests, the baseline 4355 less the 22 and the 3 self-tests.
2. **Delete `hooks/tests/test-workflow-regression.sh` and `test-sqlite-concurrency.sh`.**
   - **Why:**
     - pytest covers the first's four checks;
     - the second's question was answered by the April spike (`docs/features/078-cc-native-integration/spike-results.md`);
     - both sat red for 167 commits unnoticed.
   - **Sweep the references:** `docs/dev-guide/getting-started.md:109-116`, `hooks/tests/test-worktree-dispatch.sh:48-49`, `docs/knowledge-bank/heuristics.md:669`.
   - **The alias scan needs no change:** no `.sh` or `.md` caller passes a removed alias.
3. **Correct the board sentence** in `README.md:80` and `docs/user-guide/overview.md:42`.
   - **What it must not claim:**
     - a card for every item: 35 unarchived backlog and brainstorm items have none;
     - projects: none has a workflow row;
     - lineage on the board: it is on the detail page;
     - a per-project scope: the server is shared across projects, and its default workspace is the one it started in.
   - **Proposed second sentence of `README.md:80`:**
     > The board shows a card for each workflow item (features, brainstorms, backlog items and promoted tasks), refreshed every few seconds; archived entities get no card, though the Entities page still lists them. By default it shows the workspace the server was started in; open a card to see the entity's lineage.
   - **`overview.md:42`:** gets the same corrections.
   - **README.md (D4):** delivered as a one-hunk patch the user applies.
4. **Correct the C11 design's D7 note** (N10). Add a dated line saying the premise came from a fresh v1 database, and that `rename_entity` is now deleted.
5. **The repo-root script tests pass on develop** (N13).
   - **`scripts/test_migrate_e2e.py`:** `_run_migrate` removes `ENTITY_DB_PATH` from the environment it passes, so only the test's HOME names the database.
     - **Test:** a test that sets `ENTITY_DB_PATH` itself (monkeypatch) to a sentinel path under its tmp dir runs an export and an import. Both succeed, and the sentinel is never created. Today it fails. It sets the variable itself because the gate that runs it (G5) unsets it.
   - **`TestMigration6`:** rewritten against the current chain's version and columns, or deleted where it only pins a retired schema. The v1 chain is also covered under `plugins/pd/hooks/lib/entity_registry/`.
   - **Gate:** the repo-root script tests become a gate (G5), with 0 failures expected.

## Order and gates

1. **Phase 1 (P0): W1 and W2.**
   - **Why together:** both edit reconciliation, the backfill and the row writers.
   - **Why first:** it must land before the pd plugin is re-enabled.
   - **Order inside:** W2 change 1 (the row writers) first, because W2 changes 5–6 and W1 change 7 use it.
2. **Phase 2 (P1): W4 changes 1–3, then W3.**
   - **Why sequential:** W3 change 4 builds on W4 change 1's `_require_workspace()`, and both rewrite the same entity-server tools (premortem).
   - **What can run alongside:** W3 changes 1–3 (UI and database) run in parallel with W4.
3. **Phase 3 (P1): W4 changes 4–5.** After Phase 1.
4. **Phase 4 (P2): W5.**

**Landing order:** Phases 2, 3 and 4 may land in any order after Phase 1. One that finds develop has moved rebases onto it and re-runs its gates before landing (the plan's rebase rule).

**Process, per task:** implement, then an independent review, at most one fix round, then independent QA. Each phase gets an integration review and QA.

**The gates:** Release C's four, plus the repo-root script tests (W5.5). Their exact commands are the plan's G1–G5:
- the 3-path pytest suite;
- the scripts suite;
- `validate.sh` on a `git archive` export with `test-hooks.sh` removed, under a temp HOME;
- `test-hooks.sh` from a scratch clone, under a temp HOME whose `installed_plugins.json` points at a temp cache;
- the repo-root script tests.

**Test churn, measured by the prototypes:**
- **Phase 1:** about 196 existing tests pin deleted behaviour, 109 to delete and 87 to rewrite (42 of the rewrites are mechanical backfill-signature changes). The backfill's file reads and the brainstorm archive add more. Plus about 20 new tests.
- **Phases 2–3:** about 51 fail in the prototype. Most are fixtures and links to rewrite, and 4 are recovery-thread tests to delete. Plus about 16 new tests.
- **Phase 4:** 25 deleted from G1's suite, plus N13's migration-test fixes.

**Live effects:**
- **No change writes the live registry.**
- **D2's restore, if chosen,** is a separate gated run with a fingerprint check.

## Deferred

| Item | Reopen when |
|------|-------------|
| Re-key `workflow_phases` by entity uuid (D3) | **In scope since the D3 ruling (2026-09-26):** Phase R |
| Scope the 39 unscoped `get_entity` reads, and guard `update_workflow_phase`, the step-5 projection, `delete_workflow_phase`, `resolve_ref`'s exact match and `fix_kanban_columns.py` | Decided by Phase R's re-key design, from its inventory |
| Refuse cross-workspace duplicate type_ids at registration (D3) | The first natural collision |
| Per-workspace `.meta.json` import, which also covers `run_backfill`'s scanners that import a checkout's projections on a fresh DB or a version bump (`backfill.py:611-690`) (D1) | The user wants an external repo's committed projections in the registry |
| The library's `__unknown__` defaults in `feature_lifecycle.py:270` and `:484` (59 test edits); MCP callers always pass a workspace after W4 | Next cleanup of the library API |
| `/pd:create-project` resume from another checkout refuses: `_resumable_registration` compares the stored `artifact_path` (`feature_lifecycle.py:381`) | It is hit |
| `db.backfill_project_ids` claims `__unknown__` rows by `artifact_path` prefix (`entity_server.py:263`) | `__unknown__` rows reappear (0 live) |
| `frontmatter_sync` (for example `backfill_headers`) still reads `artifact_path` as a path | It runs outside the manual CLI |
| `update_entity` still accepts the retired status `"archived"` | Next status-vocabulary pass |
| The five unrun hook shell tests (N9): `test-cc-native-integration`, `test-worktree-dispatch`, `test-data-file-guard`, `test-enriched-docs-content`, `test-promptimize-content` | Next test-hygiene pass |
| Submodule sessions change root under `-e` (W4 change 4) | pd is used inside a submodule |

## Risks

- **A row-less legacy entity has no state until the next entity-server start backfills it.** This follows deleting hydration.
  - **Where it can happen:** 4 such features live, all archived.
  - **Mitigation:** the backfill runs at every start. Where the workspace doesn't resolve, W4's refusal names the fix.
- **External repos lose automatic status import.** They keep the committed files, and nothing reads them. D1 records the trade.
- **Brainstorms deleted outside `/pd:cleanup-brainstorms` stay on the board** until archived with `update_entity(archived=true)`.
- **A successful workspace retry writes `.claude/pd/workspace.json`.** That is the normal file of a pd project.
- **Worktree sessions no longer publish the plugin cache.**
- **Deleting `reconcile_apply` changes the MCP tool surface.** No markdown caller exists, and the counts `validate.sh` checks are swept in the same change.

## Review record

**Rev 1 → rev 2.** Three independent reviews, each reproducing or refuting against the code at `84fc9376`:

| Review | Result | What it changed |
|---|---|---|
| Premortem (9 stories, 13 unverified assumptions) | Story 1 blocked W4 change 4; stories 2, 3 and 5 needed amending before Phase 1 | Deleted the brainstorm archive and added an explicit archive (W1 changes 1–2); no mkdir in activation, and a mkdir in the skill (W2 changes 5, 7); one-transaction activation (W2 change 5); the row writers moved into Phase 1 (W2 change 1); the retry wired into every write, with a legacy-id fallback (W4 change 1); health excludes a missing projection (W1 change 6); orphan filter (W3 change 1); sync-cache skips worktrees (W4 change 5) |
| Code verification of W1/W2 (prototype, 52 claims: 44 hold, 7 wrong or incomplete, 1 not re-run) | No real breakage; about 196 tests pin deleted behaviour; 13 of 14 proposed tests pass, 14 with the writer API | The writer API into Phase 1; the dependency flip and Task 3 (W1 changes 7–8); the full tool-removal sweep, including the count `validate.sh` checks (W1 change 4); the backfill status from the registry (W2 change 6); corrected test wordings; a non-vacuous backfill test |
| Code verification of W3/W4/W5 (prototype, 43 claims: 31 hold, 6 wrong, 6 unverifiable) | No real breakage; 51 tests to rewrite; 12 of 15 proposed tests non-vacuous | The retry's key (W4 change 1); the create/upsert callers pass their workspace (W2 change 1); display sites (W3 change 2); named unguarded writers (W3, deferred); corrected figures (4330; 39 reads); `-e` side effects and the sync-cache trade stated; README wording without a per-project scope; three vacuous tests replaced |

**Rev 2 → rev 2.1.** Two independent reviews of the implementation plan found these in the design:

| Review | What it changed in the design |
|---|---|
| Plan review | <ul><li>The decomposed test was vacuous, so it was split into a skill-content test and a transition test, and every lane asserts the row right after activation (W2 tests).</li><li>`update_entity`'s docs, `architecture-overview.md:122`, a grep check, and five test modules, not three (W1.2, W1.4).</li><li>The hydration docstrings (W1.5).</li><li>Reusing `_resolve_optional_workspace_filter` (W4.1).</li><li>The W3.4 tools wire `_require_workspace()` themselves (W3.4, W4.1).</li><li>Tests 13b and 13c skip in a worktree (W4.5).</li><li>The sentinel test sets its own variable (W5.5).</li><li>The rebase rule (Order).</li></ul> |
| Calvin (report mode, 73 questions) | <ul><li>A no-archive test from a worktree root (W4 tests).</li><li>An unresolved-workspace test for a W3.4 tool (W3 tests).</li><li>Feature 129's four tests named, with the one fixture change (W3.4).</li><li>The rest is the plan's; answers are in its ledger.</li></ul> |

**Reviewer claims checked against source before absorption:**
- the upsert INSERT omits the workspace (`database.py:10274-10278`);
- `_evaluate_and_flip` writes by type_id (`dependencies.py:184-185`);
- Task 3 lists every workspace (`dependency_freshness.py:25`);
- `README.md:149`'s count is checked by `scripts/check-doc-drift.sh:28-46`;
- `/pd:brainstorm` registers nothing (`commands/brainstorm.md:20`);
- `/pd:cleanup-brainstorms` writes `status="archived"` (`commands/cleanup-brainstorms.md:25`);
- the legacy project id comes from the root commit (`project_identity.py:848-870`);
- Tests 13b and 13c run sync-cache from where the suite runs and compare the published file (`test-hooks.sh:341-413`);
- `_resolve_optional_workspace_filter` maps `"__unknown__"` and raises on no row (`database.py:6958-6972`);
- the create-feature steps are at `commands/create-feature.md:17-22`;
- the hydration docstrings are at `engine.py:467` and `:514`;
- the three docs list `update_entity`'s parameters;
- the W3–W5 prototype failed `test_cross_workspace_parent_spawn_succeeds` with `workspace_unresolved`, not on policy (`design-review/verify-rest/runs/proto/failed-tbline.txt:221`);
- the error mapping sends every unmatched `ValueError` to `invalid_transition` (`workflow_state_server.py:885-921`).
