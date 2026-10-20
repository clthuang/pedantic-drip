# Re-key `workflow_phases` per entity: playbook and operator manual (Phase R, step R2)

- **Status:** R2's playbook with R3's one revision applied (2026-09-26; plan:313: "At most one revision absorbs their findings; remaining blockers go to the user"). R3 ran a premortem, a code verification that built these changes on a scratch export and ran G1–G5, a blast-radius census of the strict rule, and a live-copy rehearsal with a rollback drill. Every finding's disposition is in the R3 revision record at the end, and no blocker remains for the user. Next: the user's first question batch (section 0.4), then R4.
- **Date:** 2026-09-26.
- **Home:** `docs/dev_artifacts/plans/2026-09-26-workflow-phases-rekey-playbook.md` (plan:298), copied there with the design and the inventory on 2026-09-29 from `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/workflow-phases-rekey-playbook.md`.
- **What it implements:** the re-key design, revised once for calvin's ledger (95 resolved, 0 open) and once for R3's findings (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/revision/dispositions.md`).
- **Inputs, and how they are cited:**
  - **the rekey design,** `docs/dev_artifacts/plans/2026-09-26-workflow-phases-rekey-design.md` (sandbox copy: `.../rekey/design/workflow-phases-rekey-design.md`), cited "rekey §N";
  - **the plan,** `docs/dev_artifacts/plans/2026-09-25-release-c-followups-implementation-plan.md`, cited "plan:line" at develop `c1bbfae0` (566 lines). `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/revision/plan-anchor-map.txt` maps R2's citations of the plan at `77f06efb` to it, each with its text unchanged;
  - **design rev 2.1,** `docs/dev_artifacts/plans/2026-09-25-release-c-followups-design.md`, cited "design:line";
  - **the inventory,** `docs/dev_artifacts/plans/2026-09-26-workflow-phases-rekey-inventory.md` (sandbox copy `.../rekey/inventory.md`, rows in `.../rekey/inventory.json`), cited by row id such as `schema-32`.
- **Code anchors:**
  - file:line citations were taken at `4a6373f0` (branch `followups-phase-1`, task 1A), which equals develop `77f06efb` outside 1A's files;
  - the ones that moved by develop `c1bbfae0` (code at `ddc299a0`) in the four files the table covers (`database.py`, `workflow_state_server.py`, `backfill.py`, `entity_server.py`) are listed in `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/proto/logs/anchors-moved.txt`, and R3's revision applied each row to the lines it names. Anchors R3 added are at `c1bbfae0`, and the moved ones in other files Phase 1 changed (for example `engine.py`) carry the design's `c1bbfae0` lines. So, as in the design, every file:line citation here is at `c1bbfae0`, except those that name their commit, such as code Phase 1 deleted (`4a6373f0`);
  - inventory rows carry lines at `77f06efb`;
  - **Phase 1, as read:** as landed on develop `c1bbfae0` (its code equals `ddc299a0`): 1A; 1B's W1 as executed, with its execution notes; 1C's brainstorm registration, scoped to the session's workspace, which skips a type_id another workspace holds and names it in the warnings. R4-C removes that skip (1.5);
  - every task re-anchors by symbol on its own branch before editing (plan:72).
- **Names used below:**
  - **R4-A … R4-I:** this playbook's tasks, with R3's R4-C0 and R4-F1 to R4-F4 (section 0.2, item 12). Section 1.1 maps them to the design's work units RK1–RK6.
  - **Q1–Q7:** the user's questions (section 0.4).
  - **the tripwire:** R4-C's refusal, inside the migration, to migrate the live file without the operator tool's flag (1.5, change 2; 2.2, step 1b).
  - **the naming rule:** rekey §6.1. **the row view:** rekey §6.2.
  - **the operator tool:** `scripts/rekey_live_registry.py`, which task R4-E adds.
  - **the live file:** `/Users/terry/.claude/pd/entities/entities.db`.
  - **the prescribed copy command:** plan:109-111, the only way any agent copies the live file:
    ```
    /Users/terry/projects/pedantic-drip/plugins/pd/.venv/bin/python -c "import sqlite3,sys; s=sqlite3.connect('file:/Users/terry/.claude/pd/entities/entities.db?immutable=1',uri=True); d=sqlite3.connect(sys.argv[1]); s.backup(d)" <dest>
    ```
  - **the two pinned workspaces:** pedantic-drip `69696982-0e18-46f1-acf2-18a3edc6bbb7` and terry_agent `f7b49c1d-6a72-4fe6-a4e7-14706161625a` (plan:414-415).
  - **fingerprint:** `stat -f '%m %z'` plus a sha256 prefix of the file (plan:42). **Per-table fingerprints:** for every table whose name is `NOT LIKE 'sqlite_%'` (FTS shadow tables included), its row count and a sha256 over its rows sorted (F1's method, plan:416-421). `sqlite_sequence` is compared on its own (1.7).
- **This playbook's own evidence** is under `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/r2/`:
  - `exp/rederive.py` → `exp/files/rederive.json`: every live figure of Part 2 re-derived on fresh copies with the design's prototype migration, plus a rollback drill through the backup API;
  - `exp/header_diff.txt`: which bytes differ between the live file, its backup and a restored file;
  - `rows/assign.py` → `rows/assign.out`: every one of the 369 inventory rows assigned to exactly one task or to the no-task list;
  - `rows/checklists2.py` → `rows/ck_R4-*.md`: the per-task checklists embedded below;
  - `docs_grep.txt`: the design's docs grep at `4a6373f0`;
  - `migrate_db_4a.py`: `scripts/migrate_db.py` at `4a6373f0`, read to decide the apply tool (section 0.2, item 2).
- **R3's evidence** is under `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/`:
  - `premortem/findings-all.md`: three independent lenses;
  - `proto/`: the core build (`build-report.md`), and `export/`, the working reference for the migration and the operator tool;
  - `blast/`: the strict rule's blast radius (`blast-report.md`, `work/`);
  - `rehearsal/`: the live-copy rehearsal (`rehearsal-report.md`);
  - `revision/`: the dispositions this revision applied, and its edit scripts.
- **Live registry:** fingerprint `1790286038 4083712`, sha256 prefix `2814bb4434e8faa0`, no `-wal` and no `-shm`, before and after this work; the fingerprint is unchanged after R3's revision. Opened only with `immutable=1`; every experiment ran on copies made with the prescribed copy command.

## 0. Reading guide

### 0.1 Who reads what

- **The orchestrator:** section 0, sections 1.1–1.2, 1.12 (Phase R integration) and 1.13 (row coverage), and Part 3. The R3 revision record at the end says what R3 changed, and where.
- **An implementer:** section 1.2 (the common brief) and its task's section; for R4-F1 to R4-F4, also 1.8's shared part (1.8.0). The orchestrator hands over both as they stand.
- **A reviewer:** the same, plus the task's "Reviewer focus".
- **QA:** the same, plus the task's "QA probes".
- **R3:** everything. Section 3.7 is the rehearsal procedure.

### 0.2 Where this playbook departs from the design, and why

Each item is a work-breakdown or evidence refinement. None changes a contract of the design.

1. **RK1 is two tasks, R4-A and R4-B.**
   - **What:** R4-A covers the library and the engine layer (`plugins/pd/hooks/lib`, `plugins/pd/scripts`); R4-B covers the two MCP servers (`plugins/pd/mcp`).
   - **Why:** RK1 touches 20 files and 151 inventory rows (148 after item 5 moves three to R4-F4). Background agents die of context overflow on briefs with that many files. The split keeps each implementer's and reviewer's reading bounded, and the change is additive, so each half keeps G1–G5 green on its own.
2. **A dedicated operator tool, task R4-E.** The task asked whether `scripts/migrate_db.py migrate` fits. It does not (`cmd_migrate`, migrate_db.py:355-507 at `4a6373f0`):
   - **It opens the file read-write for its pre-reads** (`sqlite3.connect(db_path)`, :409). The safety rules allow only `immutable=1` or `mode=ro` (plan:107).
   - **Its backup is `shutil.copy2`** (:448; its dry run copies the same way, :375), not the backup API. A byte copy of a WAL-mode file taken without its `-wal` can miss committed pages.
   - **It checks nothing the sitting needs:** no `-wal` check, no process check, no `schema_version` precondition, no expected figures, and no row-level verification.

   So R4-E adds `scripts/rekey_live_registry.py`, reviewed and tested like any task. Its subcommands are the manual's steps, so R3's rehearsal and the sitting run the same commands on different paths.
3. **The docs sweep is its own task, R4-H,** not part of RK2.
   - **Why:** the docs restate the final contract, which is complete only after R4-F4 (the strict flip).
   - **Why that is safe:** nothing lands on develop before the sitting (rekey §12), so docs that lag on the phase branch mislead nobody.
4. **`ENTITY_NAMING_METHODS` is declared in R4-A,** not in RK5.
   - **Why:** RK4's refusal test is parametrized over it (rekey §10), and RK4 runs before RK5.
   - **What RK5 still does:** R4-G adds the check that the declared list equals the AST scan (rekey §11, rule 5).
5. **Row ownership:**
   - **schema-50, -54 and -57 go to R4-F4.** Their own lines change only in the strict half. RK1's part is at their call sites.
   - **schema-55 (`resolve_entity_uuid`) goes to R4-B.** Its three production callers are in `workflow_state_server.py`, so its refusal of a missing workspace lands with them.
6. **In the sitting, the migration runs before develop moves.**
   - **The design's order before R3's revision:** land, migrate, verify, publish. The revised design runs this playbook's order (rekey §12, item 7; §13.3).
   - **This playbook's order:** apply from a scratch clone at the exact commit that will land, verify, then fast-forward develop, then publish.
   - **Why:** under the old order, a failed verification restores the file while develop already holds RK2's code. Any repo script or UI server started from the main checkout would then migrate the restored file again (the hazard of rekey §13.1). Migrating first makes that rollback a restore alone.
   - **The same code either way:** the scratch clone is checked out at the commit develop fast-forwards to.
7. **Rollback is confirmed by per-table fingerprints, not by sha256.**
   - **The claim that needs correcting:** rekey §13.4 cites the prototype's `rollback_sha256_matches_backup`, but the prototype restored with `shutil.copyfile` (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/proto/run_proto.py`, step 8), which proves nothing about a restore through the backup API.
   - **R2's drill:** it restored through the backup API, as rekey §13.4 prescribes (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/r2/exp/rederive.py`).
     - **What matched the backup:** schema_version 7, every per-table fingerprint, the full `sqlite_master` text, and `integrity_check` = ok.
     - **What did not:** the sha256 (`4f9b4b94ac502386` against `50b1ba011516f7a5`).
     - **Why:** the two files differ in 3 bytes, all inside the header fields at offsets 24-27 (file change counter), 40-43 (schema cookie) and 92-95 (version-valid-for) (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/r2/exp/header_diff.txt`).
8. **The rebuild's `phase_events` foreign-key check needs no new code.**
   - **The design's plan:** rekey §2.4 says R2 adds `PRAGMA foreign_key_check(phase_events)` to the rebuild's verification.
   - **Why no code is needed:** `run_backfill` already runs the full `PRAGMA foreign_key_check` after the import (rebuild_tool.py:1389 at `4a6373f0`), which covers `phase_events` once its column carries the foreign key.
   - **What R4-C adds instead:** a test showing that an unmapped event fails that check.
9. **Tests added beyond rekey §10,** each named in its task and marked "(playbook addition)":
   - the migration's remaining steps (4.4 steps 4, 5 and 8, and the event classes);
   - the engine contract and the CLIs' workspace resolution;
   - the servers' read tools;
   - the second workspace's activation, which is the user-visible bar of rekey §1.3.
10. **The pinned column count is 9, not 8.**
    - **The design's wording:** rekey §9 open question 21 says "the 8 columns become 7".
    - **What the test checks:** `test_workflow_phases_has_8_columns` asserts 9 columns (test_database.py:2870-2875 at `4a6373f0`), and the live table has 9. After the re-key it has 7.
11. **The guard's red-first evidence comes from an older commit.**
    - **Why:** R4-G lands after every site it detects is fixed, so on its own base it is green by construction.
    - **What stands in for red-first:** its run on R4-C's merge commit (the design's "on RK2's head", rekey §15), plus a mutation probe (section 1.9).
12. **R3's re-slicing: R4-C0 is new, and R4-F is four tasks** (2026-09-26).
    - **R4-C0** moves the tests' raw SQL on the two tables behind shape-aware helpers before the flip, so R4-C edits the helpers, not about 38 test files (PM-CODE-W11).
    - **R4-F1 to R4-F3** run the codemod tree by tree, additive under the fallback, and **R4-F4** makes the rule strict, last. Flipped first, the rule would fail R4-F's 961 tests at the flip's own gate (the blast census at `ddc299a0`; PM-CODE-W4).
    - **The design units stay RK1–RK6:** R4-C0 prepares RK2, and R4-F1 to R4-F4 are RK4. Design §15 records the same split.

### 0.3 Plan changes for the orchestrator: now, and in the sitting's commit (rekey §12)

R2 and R3 have no write access to tracked files, so each change is listed as old text → new text.
- **Anchors:** the plan at develop `c1bbfae0` (566 lines). R2's citations of the plan at `77f06efb` map to it with their text unchanged (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/revision/plan-anchor-map.txt`).
- **How the orchestrator applies them:** by each change's quoted old text, re-anchored against develop when it applies it.
- **When** (PM-CONS-W1):
  - **items 1–8:** in one commit on develop, before R4 starts;
  - **items 9 and 10:** in the sitting's commit, which step S8's fast-forward lands with Phase R (precondition 1), because they state facts true only once Phase R has landed. Under a recorded deferral of the sitting, they wait with Phase R.

**Apply now: one commit on develop, before R4 starts**
1. **Landing (plan:75):** after "land in whatever order they finish", add: "Phase R lands on develop only in the live-migration sitting, after the user's one yes (Phase R playbook, Part 3). Until then it waits on `followups-phase-r`, under the rebase rule below."
2. **Rebase rule (plan:76):** add: "A phase that rebases onto develop after Phase R has landed adopts Phase R's naming rule and row view (the re-key design, section 6). Strict-rule failures in its own new tests are its own to fix." (PM-CONS-S8.)
3. **Shared files (plan:77-79):**
   - **Old (plan:78):** "`database.py` (2B edits `list_workflow_phases` and the writers; 4A edits a docstring)".
   - **New:** "`database.py` (Phase R re-keys `workflow_phases` and `phase_events`; 4A edits a docstring)".
   - **Add** (PM-CONS-W4): "`hooks/lib/entity_registry/backfill.py` and `hooks/lib/workflow_engine/engine.py` (Phase R; 4A's W5.7 deletions)"; "`mcp/test_workflow_state_server.py` (Phase R; 4A deletes tests; 4C may edit fixtures)"; "`mcp/test_create_feature_lanes.py` (Phase R; 4C's fixtures)"; "`hooks/sync-cache.sh` (3A; Phase R's R4-E guard)".
4. **R4's order (plan:316):** "once Phase 1 and 2A have landed" becomes "once Phase 1, 2A and 2C have landed and the user has answered the playbook's first question batch (its section 0.4). R4-C also waits for 4C, and R4-F3 for 4A."
   - **Why 2C:** it edits `_resolve_ref_param` and the entity tools, which R4-B also edits.
   - **Why 4C** (BLAST-B1): its serialized, monotonic migration runner keeps migration 26 from bricking a file.
   - **Why 4A** (PM-CODE-S3): it deletes tests in `test_workflow_state_server.py`, R4-F3's largest file.
5. **F1, whenever the code under test holds Phase R:** at Phase R's integration (1.12), and at F2 after the sitting (F1 is plan:407-455):
   - **Setup step 2 (plan:411):** after making S, open one copy of S with the code under test, which migrates it (the tripwire is inert on copies). Fingerprint that copy as the baseline. Each step starts from a copy of the migrated S.
   - **Row fingerprint (plan:416-421):** `workflow_phases` sorts by its primary key, now `entity_uuid`.
   - **Step 4's "Before" (plan:444):**
     ```sql
     SELECT e.uuid FROM entities e
     LEFT JOIN workflow_phases wp ON wp.entity_uuid = e.uuid
     WHERE wp.entity_uuid IS NULL AND e.workspace_uuid = ? AND e.kind <> 'project'
       AND e.is_deleted = 0
     ```
     This is the backfill's own rule: it lists the workspace's entities (backfill.py:253), which leaves out soft-deleted ones by default (`list_entities`, database.py:8282), and skips projects (backfill.py:254). On today's data it selects pedantic-drip's 28 row-less entities (0 soft-deleted entities today; PM-LIVE-S5).
   - **Step 4's "Expected" (plan:446):** "exactly those entities gain rows, each keyed by its own `entity_uuid`".
   - **Steps 1–3 (amended 2026-09-26) hold unchanged under Phase R** (PM-CONS-S7). Step 1's registration clause (plan:427) covers a brainstorm whose type_id only another workspace holds, which registers here once R4-C removes 1C's skip. Step 3's `feature:035` check concerns a feature, which brainstorm registration never touches.
6. **F2 (plan:457):** "After all four phases land" becomes "After all four phases land, and Phase R has landed or the user has deferred it (recorded)".
7. **F3 (plan:464):**
   - **Old:** "**After Phase R's code lands,** it asks whether to migrate the live registry, per Phase R's manual."
   - **New:** "**When Phase R's branch is ready to land,** it asks one question: land Phase R, migrate the live registry and publish, in one sitting with pd disabled in every session (Phase R playbook, Part 3). The order is: migrate from the commit that will land, verify, land, publish. It asks at the same time about the five namesakes and the operator tool's fate (Phase R playbook, section 0.4, batch 2)."
8. **Done when (plan:474-484)** (PM-CONS-W1):
   - after #1, add: "Under a recorded deferral of Phase R's sitting, the type_id-only updates, W3.1–W3.3 and problem 1's read-scoping stay in the design's Deferred table, each marked to reopen when the sitting runs."
   - to #2 (plan:480), add: "Tests that live only on `followups-phase-r` under a recorded deferral are exempt."

**Apply in the sitting's commit** (step S8 lands it with Phase R)

9. **Problem 3 (plan:22-23):**
   - **Old:** "Every insert stores the resolved entity's `workspace_uuid` and `uuid`. Checks: W2.1's "Explicit workspace" and "Upsert refuses" tests, and F1 step 4." (plan:22, after its title) and "**Deferred by design (D3):** the type_id-only *updates*." (plan:23).
   - **New:** "Every insert is keyed by the resolved entity's uuid, and the row's workspace and type_id are the entity's, read by join. Checks: W2.1's "Explicit workspace" test as restated by Phase R, `test_upsert_writes_own_row_leaves_namesake_unchanged`, `test_rekey_schema.py::test_insert_for_unknown_entity_is_refused` (`wp_reject_unknown_entity`), and F1 step 4 as restated." The Deferred line (plan:23) goes: Phase R keys the updates by entity uuid.
10. **The fingerprint baseline after the sitting:** F1's "the live file's fingerprint matches kickoff's" (plan:452) and Done-when #4 (plan:482) compare against the fingerprint the sitting records (Part 3, step S9). That fingerprint replaces kickoff's from then on.

**The orchestrator's note, outside Phase R's documents:** plan:370 (4C's files) still says "migration 11 or its concurrency test". The amended 4C brief makes it the migration runner (`_migrate` and `_migrate_v2`). Align that line when the plan is next edited.

### 0.4 Questions for the user (rekey §9)

These are the design's section 9 items as R3 corrected them (PM-CONS-S1, PM-CONS-S2, PM-CONS-W6, PM-CONS-W7, PM-CONS-S4). The orchestrator asks them through AskUserQuestion, in two batches of at most four questions each. The first option of each is the recommendation, and the playbook follows it unless the user rules otherwise.
- **Batch 1 (Q1–Q4):** after this revision is applied, before R4 starts.
- **Batch 2 (Q5–Q7):** when Phase R's integration (1.12) has passed and R4-I is next.
- **Without an answer:** Q3 keeps today's fallback, since no ruling covers it. Every other question blocks what the table below says.

**What waits for which answer** (the prerequisites of 1.1):

| What waits | For |
|---|---|
| R4's start (R4-A and R4-C0, and so every R4 task) | Q1: hold the sitting this round |
| R4-B's change 2 (the three list tools) | Q3. A yes that arrives after R4-B merged moves the change to R4-F4 |
| R4-E's deletion part | Q4 |
| R4-F1 to R4-F4 | Q2: strict, answered before R4-F1 is cut |
| R4-G | Q4 (its declared-entry set) |
| R4-I (the sitting), and the sitting's plan changes (0.3, items 9 and 10) | Q5: yes |
| F2's cleanup commit | Q7 |
| Nothing in R4 | Q6. Its options 2 and 3 are scheduled after S12, as their own gated write |

**Batch 1: after this revision, before R4 starts**

1. **Q1. Phase R's code (13 tasks; about 1,800 test call sites and 115 production calls change) pays off only at the live sitting. Will you hold the sitting this round, and does pd stay disabled until it?**
   - **Hold it this round; pd stays off (Recommended).** Cost: no pd in any session until the sitting (as since 2026-09-24). Consequence: R4 starts once 2A and 2C land. No session can publish Phase R code or migrate the live file by accident.
   - **Hold it this round; re-enable pd now.** Cost: every agent command runs under the temp-HOME rule (1.2), and the migration tripwire is the only backstop. Consequence: a pd session started in a Phase R clone republishes that clone, and pd stops starting (the tripwire refuses) until develop is re-published.
   - **Not this round: stop after R3.** Cost: problem 1 (board and links) and the type_id-only updates stay open, and 1C's skip stays. Consequence: R4 does not start. The design and playbook are kept as the record, the deferral goes into the Deferred table, and the plan's Done-when deferral clause (0.3, item 8) applies.
2. **Q2. Strict naming rule (rekey §9, Q2): must every call that names an entity by type_id pass a workspace, for good?** If still open, it must be answered before R4-F1 is cut.
   - **Strict (Recommended).** Cost, measured at `ddc299a0`: under the full rule, 1451 tests fail before any task's edits (961 of them R4-F's). There are 1057 direct and 754 entry-point test call sites, 343 engine/helper and 250 MCP-handler sites among them beyond the codemod's list, and about 115 production calls. Lasting: every future test and caller passes a workspace or uuid; each rebase while the sitting waits re-runs the codemod; read tools answer `workspace_unresolved` in a session with no workspace. Consequence: R4-F1 to R4-F4 run, and criterion 4 is enforced by the API's shape.
   - **A default workspace per connection.** Cost: few call edits, but hidden state. A process serving several workspaces (the UI server, multi-workspace test fixtures) resolves in whatever workspace was bound last, so criterion 4 holds only by discipline. Consequence: R4-F is re-planned (a binding API in place of the four slices), and rekey §6.1 is revised and re-reviewed.
3. **Q3. The three list tools (`list_features_by_phase`, `list_features_by_status`, `query_ready_tasks`) with `project_id` omitted and no resolved workspace: refuse, or keep listing every workspace?** If still open, it must be answered before R4-B starts.
   - **Refuse with `workspace_unresolved` (Recommended).** Cost: a session with no resolved workspace gets an error instead of a cross-workspace list. `project_id='*'` still lists every workspace. Consequence: R4-B scopes them to `_require_workspace()` with two tests. This supersedes W4.1's "read tools keep today's behaviour" for these three.
   - **Keep today's fallback.** Cost: these three stay the one read path that answers across workspaces when unresolved. Consequence: R4-B leaves them, and W4.1's text stands.
4. **Q4. `scripts/migrate_db.py merge-entities`, broken since migration 11, which writes nothing: delete it, or keep it?** If still open, it must be answered before R4-E starts.
   - **Delete it (Recommended).** Cost: if a cross-machine import's entity merge is ever needed, it is rebuilt per entity. Consequence: R4-E deletes `cmd_merge_entities`, its subparser, `TestMergeEntities`, `test_migrate_deepened.py`'s merge tests and `migrate.sh import`'s merge step, which becomes a loud refusal counted in `import_failures`. The guard's declared entries fall to 0 once 4A lands. The repo's rule is the same: no backward compatibility, delete old code.
   - **Keep it as is.** Cost: a broken subcommand stays. Its declared guard entry is keyed by function plus a source hash, so any edit to it turns the guard red. Consequence: the guard's high-water mark stays 1 after 4A, and its Deferred row stays.

**Batch 1 answered (user, 2026-09-26):**
- **Q1:** the user asked, verbatim, "since pd is off, isn't it a good time to fully re-key with any side effect?". The orchestrator read it as option 1 (hold the sitting this round; pd stays off) and told the user so. The live migration itself still waits for Q5's yes.
- **Q2:** "Strict (Recommended)".
- **Q3:** "Refuse (Recommended)".
- **Q4:** "Delete it (Recommended)".

**Batch 2: when Phase R's integration (1.12) has passed and R4-I is next**

5. **Q5. Phase R is ready: migrate the live registry, verify, land Phase R on develop and publish, in one sitting with pd disabled in every session, the operator's included?**
   - **Yes, run the sitting (Recommended).** Cost: pd is off in every session for the sitting, while the operator runs Part 3's S1–S12. Consequence: the live file goes from v2/7 to v2/8, develop and the cache hold Phase R, and rollback follows 3.5. The fingerprint recorded at S9 becomes F1's baseline.
   - **Defer.** Cost: Phase R stays on its branch, rebasing and re-running its integration QA and per-rebase checklist at every develop landing. Problem 1 and W3.1–W3.3 wait, and brainstorm files whose type_id another workspace holds stay unregistered (1C's skip). Consequence: the Deferred rows stand, and the Done-when deferral clause applies.
   - **The order inside the sitting** puts the migration before develop moves (section 0.2, item 6). The one yes covers all of it.
   - **While deferred** (PM-CONS-W3), a brainstorm file whose type_id another workspace holds stays unregistered in the new workspace, and every session start's warnings name it.
6. **Q6. Pedantic-drip's five namesakes (not archived, shown on its board; terry_agent holds all five archived, and their artifacts exist only in `/Users/terry_agent/docs`): what should happen to them?**
   - **No change this round (Recommended).** Cost: pedantic-drip's board keeps the two promoted brainstorms and features 002–004, completed at finish. Consequence: the migration keeps today's attachment, and the Deferred row stays.
   - **Archive pedantic-drip's five copies.** Cost: a gated live write after the sitting (`set_archived` by uuid, reversible), with its own fingerprint check. Consequence: they leave pedantic-drip's default board, and terry_agent's copies are untouched.
   - **Merge into terry_agent's copies.** Cost: its own procedure after the sitting: copy the row state into terry_agent's backfill-seeded rows, optionally repair the 13 undecided events once, then archive or soft-delete pedantic-drip's copies. A gated live write. Consequence: one entity per type_id carries the history. Re-attributing them is impossible: `UNIQUE(workspace_uuid, type_id)`, and terry_agent already holds all five.
7. **Q7. After the sitting, what becomes of `scripts/rekey_live_registry.py` (`apply` and `restore --confirm-live` over the live file)?**
   - **Delete it after F2 (Recommended).** Cost: a restore after F2 follows 3.5's written steps with plain `sqlite3` instead of the tool. Consequence: F2's commit removes the tool and its tests, by the design's one-off rule (rekey §14).
   - **Keep it.** Cost: a permanent script that can write the live file, kept behind `--confirm-live` and the live-path guard, with its reason recorded in rekey §14. Consequence: the `restore` and `diff` subcommands stay available.

## Part 1. The playbook (R4's tasks)

### 1.1 Order and dependencies

**When R4 starts:** once Phase 1, 2A and 2C have landed on develop, and the user has answered batch 1's Q1 with "hold the sitting this round" (rekey §12; section 0.3, item 4; section 0.4). The orchestrator then cuts the phase branch `followups-phase-r` from develop. Each task branch is `followups-<task>` (for example `followups-r4-a`) in `.pd-worktrees/followups-<task>`, cut from the phase branch after the tasks it depends on have merged (plan:67-71).

| Task | Title | Design unit | Depends on (inside Phase R) | Outside prerequisites | Can run beside | Waits for a user answer |
|---|---|---|---|---|---|---|
| R4-A | The workspace reaches the library and engine layer | RK1, part 1 | nothing | Phase 1 (landed, `c1bbfae0`); 2A and 2C landed | R4-C0 | Q1 |
| R4-C0 | The tests' raw SQL behind shape-aware helpers (new in R3) | RK2, preparation | nothing | as R4-A | R4-A, R4-B | Q1 |
| R4-B | The two MCP servers pass the caller's workspace | RK1, part 2 | R4-A | none beyond R4-A's | R4-C0 | Q3, for change 2 only |
| R4-C | The schema flip | RK2 | R4-B, R4-C0 | 4C landed on develop; if it has not when R4-B merges, R4-C carries 4C's contract (1.5, change 0) | none | none |
| R4-D | The UI keyed by entity uuid | RK3 | R4-C | none | R4-E, R4-F1, R4-F2, R4-F3 | none |
| R4-E | The live-migration operator tool | new (section 0.2, item 2) | R4-C | 3A's `sync-cache.sh` edit stays a separate hunk | R4-D, R4-F1, R4-F2, R4-F3 | Q4, for its deletion part |
| R4-F1 | The codemod on the entity_registry tests and G2's three scripts tests (new in R3) | RK4 | R4-C | none | R4-D, R4-E, R4-F2, R4-F3 | Q2 (strict) |
| R4-F2 | The codemod on the workflow_engine and reconciliation_orchestrator tests (new in R3) | RK4 | R4-C | none | R4-D, R4-E, R4-F1, R4-F3 | Q2 (strict) |
| R4-F3 | The codemod on the mcp tests (new in R3) | RK4 | R4-C | 4A landed on develop | R4-D, R4-E, R4-F1, R4-F2 | Q2 (strict) |
| R4-F4 | The strict flip (new in R3) | RK4 | R4-D, R4-F1, R4-F2, R4-F3 | none | none | Q2 (strict) |
| R4-G | The criterion-4 guard | RK5 | R4-E, R4-F4 | none | R4-H | Q4, for its declared entries |
| R4-H | The docs that restate the key | split from RK2 (section 0.2, item 3) | R4-F4 | none | R4-G | none |
| R4-I | The live-migration sitting | RK6 | R4-G, R4-H, Phase R integration (1.12, with its per-rebase checklist), R3's rehearsal | none | none | Q5 (the one yes) |

```
R4-A ──▶ R4-B ──┐
                ├──▶ R4-C ──┬──▶ R4-D ───┐
R4-C0 ──────────┘           ├──▶ R4-F1 ──┤
                            ├──▶ R4-F2 ──┼──▶ R4-F4 ──┬──▶ R4-G ──┬──▶ integration (1.12) ──▶ R4-I (Part 3)
                            ├──▶ R4-F3 ──┘            └──▶ R4-H ──┘
                            └──▶ R4-E ──▶ (merged before R4-G is cut)
```

- **The order, edge by edge:**
  - R4-A → R4-B;
  - R4-B and R4-C0 → R4-C;
  - R4-C → R4-D, R4-E, R4-F1, R4-F2 and R4-F3, in parallel within the plan's cap of 6 agents at a time (plan:94);
  - R4-D, R4-F1, R4-F2 and R4-F3 → R4-F4;
  - R4-E and R4-F4 → R4-G; R4-F4 → R4-H;
  - R4-G and R4-H → integration (1.12) → R4-I.
- **Why this order:** expand, migrate, contract (rekey §15).
  - **R4-A and R4-B (expand):** they add the workspace to every call while the global-unique fallback still answers.
  - **R4-C0 (prepare):** it moves the tests' raw SQL on the two tables behind shape-aware helpers while the old shape is still live, so R4-C edits the helpers, not about 38 test files (PM-CODE-W11).
  - **R4-C:** it flips the schema and every statement on both tables at once.
  - **R4-D:** it moves the UI to the new key.
  - **R4-F1 to R4-F3 (expand, in the tests):** they run the codemod tree by tree, additive under the fallback, so each keeps G1–G5 unchanged.
  - **R4-F4 (contract):** it makes the rule strict, once R4-D has scoped `plugins/pd/ui` (3 production and 24 test calls, rekey §15) and the three slices have scoped the tests. Flipped first, it would fail R4-F's 961 tests at its own gate (the blast census at `ddc299a0`; PM-CODE-W4).
  - **R4-G:** it lands last among the code tasks, so the sites it detects equal its declared inventory.
- **Why R4-C waits for 4C** (BLAST-B1): the migration runner reads the version once, takes no lock, and stamps each step with an upsert that can lower it. Once migration 26 exists, that race bricks a file: two runners bricked a v10 file in 12 of 20 rounds (blast). 4C makes the runner serialized and its stamp monotonic. If 4C has not landed when R4-B merges, R4-C carries 4C's five-point contract (1.5, change 0), and the orchestrator tells 4C's owner.
- **Why R4-F3 waits for 4A** (PM-CODE-S3): 4A deletes tests in `test_workflow_state_server.py` (plan:371), the file with 418 of R4-F3's sites. R4-F1 and R4-F2 don't touch it, and don't wait.
- **Not prerequisites:** 4B (R4-C owns `TestMigration6`'s three row assertions either way; BUILD-W2) and 3A (its `sync-cache.sh` change is a separate hunk from R4-E's guard, and 1.12's per-rebase checklist re-checks S10 and 3.5's R5 once it lands).
- **Why R4-E runs beside R4-D and the codemod slices:** its files (`scripts/rekey_live_registry.py`, its test, and one hunk of `sync-cache.sh`) are disjoint from theirs, and its tests need R4-C's `make_pre_rekey_db`.
- **Why R4-E merges before R4-G is cut:** the guard scans the repo's `scripts/`, and the tool must pass it with no declared entry.
- **Sizing rule** (PM-CODE-W4): before a codemod slice's implementer starts, the orchestrator runs the codemod on the slice's base. If it leaves more than 150 hand edits, the slice is split by file.
- **The review protocol for every task** (plan:83-102): one implementer, an independent review, at most one fix round, then an independent QA that re-runs the task's red-first tests and all five gates. At most 6 agents at a time (plan:94).

### 1.2 The common brief (the orchestrator puts this in front of every task's brief)

**Where you work**
- **Your checkout:** the worktree `.pd-worktrees/followups-<task>`, on branch `followups-<task>`. Its **base** is the commit it was cut from. Red-first runs and gate comparisons use that base (plan:71).
- **The interpreter:** `/Users/terry/projects/pedantic-drip/plugins/pd/.venv/bin/python`, run from your worktree's root. Imports resolve from your worktree (plan:57-59).
- **Sandbox scripts** (PM-CODE-S2): every script this playbook cites under `agent_sandbox/` (the design's `work/`, R3's `r3/`) lives in the main checkout's sandbox, at the absolute path given. Run it from there, with your worktree as its argument: it does not exist inside your worktree.
- **The environment for every command** (PM-CONS-W5): every command you run (tests, probes, scripts, servers) runs with `HOME=$(mktemp -d)` and `ENTITY_DB_PATH` unset. The plan requires it for the gates (plan:380-381); Phase R extends it to every command, because opening `/Users/terry/.claude/pd/entities/entities.db` with Phase R's code migrates it. From R4-C on, the tripwire refuses that path without the operator tool's flag, but the tripwire is a backstop, not the rule.

**What binds**
- **The rekey design** (cited "rekey §N" below): its contracts bind. Where your brief and the design disagree, the design binds. Stop, record the conflict in your report, and tell the orchestrator (plan:7).
- **Design rev 2.1:** its contracts still bind where the rekey design does not supersede them (rekey §12 lists what it supersedes).

**Before you edit**
1. **Re-anchor.** The design's and this playbook's file:line citations are at develop `c1bbfae0` (its code equals `ddc299a0`), except those that name their commit (see the header); the inventory's rows carry lines at `77f06efb`.
   - **Find each row's symbol on your branch** (`codegraph explore "<symbol>"`, or grep), and record old → new in your report (plan:72).
   - **If a symbol is gone, or has changed in meaning:** stop and escalate.
2. **Check for Phase 1 drift** (rekey §9, open question 23). Phase 1 landed after the inventory was taken.
   - **List what changed:** `git -C <worktree> diff --name-status 77f06efb HEAD -- 'plugins/pd/**/test_*.py' 'scripts/test_*.py'`. It lists 1A's, 1B's and 1C's test files; handle 1B's and 1C's as 1.13 says (workspace or uuid arguments only, except 1C's skip tests, which R4-C rewrites).
   - **Grep those files** for `workflow_phases|phase_events` and for the methods your task changes.
   - **A hit inside your task's files** joins your checklist; record it.
3. **Run your task's "First checks"** and record each answer.

**How you work**
- **Keep your context small.** Never read `database.py` (~11k lines), `workflow_state_server.py` (~2.9k lines) or any file over ~1.5k lines whole. Use codegraph, grep and bounded reads, and redirect long output to files.
- **Red first** (plan:97). Write every new test your brief names before any production edit, and run it on your base. The saved output goes in your report.
  - **A test that passes on your base is vacuous,** unless your brief marks it keep-green.
  - **For a parametrized test,** record which cases are red and which are keep-green.
- **Deleting a test** (plan:98-102). Delete only a test that exercises a symbol or a behaviour a design change deletes. List each one with that change, for example "rekey §6.3: `delete_workflow_phase` deleted".
- **A test another task owns** that breaks in your task: fix it here, as a rewrite (a deletion only under the rule above), and list it in your report under "rewritten ahead of its owner".
- **Safety** (plan:104-121):
  - never open the live file except with `immutable=1`, and copy it only with the prescribed copy command;
  - **the live file's state, before and after** (PM-CONS-W5): your QA records the live file's `schema_version` (read with `immutable=1`) and its fingerprint (`stat -f '%m %z'`; `1790286038 4083712` at R3) before and after the task. A version other than 7, or a fingerprint change your task cannot explain, stops every task and goes to the user;
  - never start a Claude Code session in a Phase R clone or worktree while pd is enabled: `sync-cache.sh` is a SessionStart hook, and it would publish that tree's Phase R code;
  - never run `test-hooks.sh`, `validate.sh` or `sync-cache.sh` except as G3 and G4 prescribe;
  - no `git add -A`, and no bare `git stash`;
  - never commit `README.md` or any file the user has left untracked;
  - every commit ends with the co-author line.

**Gates** (plan:377-403). Run all five on your worktree. A gate passes when its failures are exactly its base's failures. **No test in any gate gets a re-run allowance:** a failure on one run is a failure. The migration runner's concurrency race is task 4C's to fix, not a flake to re-run: with migration 26 registered it bricks the file (BLAST-B1).
- **G1:** `python -m pytest plugins/pd/hooks/lib plugins/pd/mcp plugins/pd/ui/tests -q -p no:cacheprovider`.
- **G2:** `python -m pytest plugins/pd/scripts/tests -q -p no:cacheprovider`.
- **G3:** `./validate.sh` on a `git archive` export with `test-hooks.sh` removed, under a temp HOME whose `installed_plugins.json` points at a temp cache. Then `bash scripts/dev/check_fr_c_115_atomicity_postmerge.sh develop` from the worktree.
- **G4:** `test-hooks.sh` from a scratch clone of your branch, with the main checkout's `plugins/pd/.venv` symlinked in, under the same kind of temp HOME.
- **G5:** `python -m pytest scripts/test_*.py -q -p no:cacheprovider`.

Your brief names the count changes it expects in each gate.

**Your report:** `/Users/terry/projects/pedantic-drip/agent_sandbox/<date>/release-c-followups-execution/phase-r/<task>/report.md`. It holds:
- the red-first output, with keep-green cases marked;
- the anchor corrections (old → new);
- the Phase 1 drift check;
- every checklist row with its disposition (changed; verified unchanged, with the reason; deleted);
- the deleted tests, each with its design change, and the rewritten tests;
- tests rewritten ahead of their owner;
- gate counts on the base and on your head;
- anything left for a later task.

### 1.3 R4-A: the workspace reaches the library and engine layer (RK1, part 1)

- **Implements:**
  - rekey §6.1: the additive half of the naming rule;
  - rekey §6.3: the rows for `get_entity`, `get_workflow_phase`, `feature_entity_id`, `set_archived`, `set_deleted`, `delete_workflow_phase` and the feature-directory helpers;
  - rekey §8: the groups "Library resolvers" (additive), "Engines the servers call", "Dark engine paths", "server_helpers", and "CLIs and the session-start orchestrator";
  - rekey §15 RK1, except the MCP servers (R4-B).
- **Depends on:** nothing inside Phase R. Outside it: Phase 1 (landed, `c1bbfae0`), 2A and 2C landed, and Q1 answered (1.1).
- **Can run beside:** R4-C0.
- **Files:**
  - `plugins/pd/hooks/lib/entity_registry/database.py`;
  - `plugins/pd/hooks/lib/workflow_engine/`: `engine.py`, `entity_engine.py`, `feature_lifecycle.py`, `feature_paths.py`, `reconciliation.py`, `rollup.py`, `router.py`, `secretary_intelligence.py`, `task_promotion.py`;
  - `plugins/pd/hooks/lib/entity_registry/`: `backfill.py`, `dependencies.py`, `frontmatter_inject.py`, `frontmatter_sync.py`, `frontmatter_sync_cli.py` (PM-CODE-W9), `server_helpers.py`;
  - `plugins/pd/hooks/lib/reconciliation_orchestrator/`: `dependency_freshness.py`; and `entity_status.py`, read only (change 4);
  - `plugins/pd/scripts/cleanup_backlog.py`;
  - `plugins/pd/mcp/entity_server.py`: one line only, the call that passes `parent_type_id=None` (entity_server.py:703), because change 3 removes that parameter;
  - the new test files below, and the existing tests named below, among them `entity_registry/test_c11_feature_entity_id.py` and `workflow_engine/test_c11_feature_paths.py` (BLAST-B3).
- **Not this task's:** the rest of `plugins/pd/mcp` (R4-B); `plugins/pd/ui` (R4-D); the `phase_events` readers and every SQL statement on the two tables (R4-C); the global-unique fallback (R4-F4).

**Brief**

**Goal.** Every engine, helper and CLI in `plugins/pd/hooks/lib` and `plugins/pd/scripts` passes the workspace it holds to every library call that names an entity by type_id. The library methods that take no workspace today gain one.
- **What stays:** the global-unique fallback, so a type_id held by one workspace still resolves without a workspace, and every existing caller keeps working (rekey §15 RK1).
- **The one deliberate behaviour change:** `set_archived` and `set_deleted`, called with no workspace on a type_id two workspaces hold, raise instead of writing both namesakes.

**Read first:** rekey §6.1, §6.3 (the rows named above), §8 (the groups named above, and the engine contract in the "Engines the servers call" row), §5.3 (the backfill's row check) and §15 RK1.

**First checks** (record each answer in your report):
1. **How task 1B's landed code calls `set_archived`** from the `update_entity` tool (W1.2): with a uuid, or with a type_id and a workspace (rekey §9, open question 1). Both forms must work after this task. At `c1bbfae0`, `_process_update_entity` resolves the entity with `resolve_ref` (entity_server.py:399, which R4-B scopes), and `set_archived` has a by-uuid branch (database.py:8436).
2. **What W1 left** in `engine.py` (hydration: engines-7 to -9), `reconciliation.py` (engines-43 to -45) and `entity_status.py` (engines-84 to -86, -88). Those rows are not yours; the check confirms they are gone.
3. **Whether rollup's writes are already keyed by uuid** (engines-51 to -53, which W1.7 changes), and whether `_process_set_parent` (engines-79) already resolves in the caller's workspace (task 2C).
4. **What 1B and 1C already rewrote** (PM-CODE-W10): 1B rewrote engines-46 and -47 (cascade recovery, `_recover_pending_cascades`, now by uuid) and engines-71 and -72 (`DependencyManager._evaluate_and_flip`). Verify each by symbol, and record "verified by Phase 1, no change", with the commit. engines-87 is now 1C's code (entity_status.py:107-257; change 4).

**Changes**
1. **Library** (`database.py`, additive):
   1. **`ENTITY_NAMING_METHODS`:** a module-level tuple holding the 20 (method, parameter) pairs rekey §6.3 lists. At `4a6373f0` an AST scan finds 21; `delete_workflow_phase` is the 21st, and change 1.6 deletes it.
   2. **`get_entity(type_id, *, workspace_uuid=None, include_deleted=False)`:**
      - with a workspace, it resolves inside that workspace, and answers None when nothing matches;
      - with a uuid, it answers that entity, whatever the workspace;
      - with a type_id and no workspace, it behaves exactly as today (None for a type_id two workspaces hold) until R4-F4.
   3. **`get_workflow_phase(type_id, *, workspace_uuid=None)`:** it resolves the entity by the rule, then reads the row whose `(workspace_uuid, type_id)` equals the resolved entity's. It answers None when the entity is unknown or has no row. R4-C switches the read to `entity_uuid`.
   4. **`feature_entity_id(type_id, *, workspace_uuid=None)`:** it answers the resolved entity's `entity_id`, not a `SELECT DISTINCT` over every namesake.
   5. **`set_archived` and `set_deleted`:** they resolve through `_resolve_identifier` (a uuid, or a type_id with the workspace), then run `UPDATE entities … WHERE uuid = ?`.
      - **With no workspace, on a type_id two workspaces hold:** the existing "Ambiguous" `ValueError` (database.py:7051-7057), and nothing written.
      - **Today, for contrast:** `set_archived` already resolves a uuid (1B's by-uuid branch, database.py:8436), but a type_id still writes every namesake (:8470-8475). `set_deleted` (:8484) has no uuid path, and writes every namesake (`WHERE type_id = ?`, :8505).
   6. **`delete_workflow_phase` is deleted** (rekey §6.3: it has no production caller).
   7. **The feature-directory helpers** `feature_dir_name` and `feature_dir_path` (feature_paths.py:70, :113) and `engine._feature_dir_name` (engine.py:394) gain a keyword `workspace_uuid`, used only when they read the registry.
2. **Engines** (rekey §8, the engine contract): an engine method that takes a type_id also takes `workspace_uuid`, and passes it to every library call it makes.
   - **The read paths that gain it:**
     - `WorkflowStateEngine.get_state` and `validate_prerequisites`;
     - `feature_lifecycle`'s `get_entity` reads (:155, :258, :593);
     - `promote_task`, which already holds `task_workspace_uuid`;
     - `check_workflow_drift`, through `_read_single_meta_json` and `_single_feature_dir_name` (reconciliation.py:189, :210, :577, :580 at `c1bbfae0`). In the same change, restate its docstring (reconciliation.py:555-563: the per-feature comparison "reads the row by type_id alone") for the per-entity read (PM-CONS-W2);
     - `router.init_entity_workflow` and `router.transition_entity_phase`;
     - `secretary_intelligence.get_parent_context`.
   - **The feature-directory helper callers** named in rekey §6.3's `feature_entity_id` row pass the workspace they hold: engine.py:149 and :259, feature_lifecycle.py:133 (called at :591), task_promotion.py:327, and reconciliation.py's four sites above. `_artifact_dir` (workflow_state_server.py:422) is R4-B's.
   - **Unchanged:** the `use_db=False` calls (engine.py:256, :262, :531), which read no registry.
   - **The dark engine paths** (engines-13 to -16: `EntityWorkflowEngine.get_state`, `abandon_entity`, `_abandon_descendants`) hold the entity's uuid today and drop it for the type_id. They pass the uuid instead.
   - **The 5D and task paths** (engines-17 to -21) take the workspace like any engine path.
   - **How errors propagate:** the engines catch only `sqlite3.Error` for their `.meta.json` fallback (`get_state`, engine.py:93-120). A missing workspace must never be answered from a file.
3. **`server_helpers.py`:**
   - `_process_register_entity`'s reads (engines-73, -76) and `_process_get_lineage` (:484, engines-78) pass the workspace the function receives;
   - `_process_export_lineage_markdown` gains a `workspace_uuid` parameter and passes it to `db.export_lineage_markdown(type_id, workspace_uuid=...)` (server_helpers.py:369, today `project_id=` only), so no label-only call is left. R4-B's tool call (entity_server.py:1207) passes `_require_workspace()` (BLAST-W2);
   - the `parent_type_id` branch (engines-74, -75, -77) is deleted, with the parameter, because its only production caller passes None (entity_server.py:703). Update that call.
   - **Label-only calls** (PM-CODE-W8): a call with `project_id=` and no `workspace_uuid=` counts as unscoped (rekey §6.5). Each one in your files (for example backfill.py:424 and :763, and server_helpers.py:369, at `5cc2ab75`) passes the workspace or a uuid.
4. **CLIs and the orchestrator** (PM-CODE-W9):
   - `frontmatter_inject.py` (argv at :123-131), `frontmatter_sync`'s single-feature and backfill paths (engines-81, -82, run through `frontmatter_sync_cli.py`), and the `secretary_intelligence parent-context` CLI each resolve the workspace once, **read-only**, as `ui/__init__.py:126-150` does: `ENTITY_WORKSPACE_UUID`, then the project's `workspace.json`, then `_lookup_workspace_uuid_by_project_root` on a `mode=ro` connection with `_repository_root(cwd)`.
   - **Never** `resolve_startup_workspace_uuid` (project_identity.py:698) or `resolve_workspace_uuid`: the first falls back to the second (:739-740), which mints a workspace.
   - **With no workspace:** a warning on stderr, exit 0, and nothing written (rekey §8, the CLIs row).
   - **`backfill_headers`** lists only the resolved workspace's features (`list_entities(workspace_uuid=...)`); today it lists every workspace's (frontmatter_sync.py:518).
   - **`entity_status.py`** (engines-87) is 1C's code (PM-CODE-W10): `_sync_brainstorm_entities` (:107) registers in the session's workspace, and `_workspace_holds` (:228-241) is scoped. Verify it and record "verified by Phase 1". `_another_workspace_holds` (:244-257) is unscoped; R4-C deletes it with the skip (1.5, change 15). With no resolved workspace, the sync needs no change here: once R4-C removes the skip, it raises at the first file that needs registration, and the orchestrator records that (:169-170).
   - `dependency_freshness.py` (engines-89) passes its workspace.
5. **`backfill.py`:** `backfill_workflow_phases`' row checks (`get_workflow_phase(type_id)` at backfill.py:284 and :346) pass the workspace (rekey §5.3). `run_backfill`'s type_id comparisons stay until R4-C, which rekeys guard rule 3's maps.
6. **`cleanup_backlog.py` (SCR-3):** `apply_archival` resolves its workspace before the archive loop, archives each item with that workspace, and archives nothing when the lookup fails. Today the loop archives by bare type_id (:257-262) before the read-only workspace lookup (:275-286).
7. **The entry-point table** (PM-CODE-W4), in your report: for every engine and helper under `plugins/pd/hooks/lib` and `plugins/pd/scripts` that names an entity, whether its caller passes the workspace or the function derives it, and from what. The codemod's list (1.8.0) adds every entry point that takes it from its caller. At `ddc299a0` the blast census counts 343 engine and helper test sites outside the design's method list (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/blast/work/r4f-entry-by-home.txt`).

**Checklist** (inventory rows; paths under `plugins/pd/hooks/lib/` are shown relative to it):


- `entity_registry/backfill.py`: engines-63 to -64 (`run_backfill`); engines-65 to -70 (`backfill_workflow_phases`).
- `entity_registry/database.py`: schema-32 (`create_workflow_phase`); schema-34 (`get_workflow_phase`); schema-36 (`upsert_workflow_phase`); schema-38 (`delete_workflow_phase`); schema-44 (`delete_entity`); schema-45 (`set_archived`); schema-46 (`set_deleted`); schema-52 (`get_entity`); schema-56 (`feature_entity_id`); schema-58 (`set_parent / reparent_entity / get_lineage / export_lineage_`); schema-66 (`entities.metadata.depends_on_features`); synth-1 (`update_entity`).
- `entity_registry/dependencies.py`: engines-71 to -72 (`DependencyManager._evaluate_and_flip`; rewritten by 1B: first check 4).
- `entity_registry/frontmatter_inject.py`: engines-80 (`main`).
- `entity_registry/frontmatter_sync.py`: engines-81 (`detect_drift`); engines-82 (`stamp_header`).
- `entity_registry/server_helpers.py`: engines-73 to -77 (`_process_register_entity`); engines-78 (`_process_get_lineage`); engines-79 (`_process_set_parent`).
- `plugins/pd/scripts/cleanup_backlog.py`: SCR-3 (`apply_archival`).
- `reconciliation_orchestrator/dependency_freshness.py`: engines-89 (`cleanup_stale_dependencies`).
- `reconciliation_orchestrator/entity_status.py`: engines-87 (`_sync_brainstorm_entities`, :107; 1C's code: verify only, change 4). Its unscoped `_another_workspace_holds` (:244-257) is R4-C's to delete.
- `workflow_engine/engine.py`: engines-1 (`WorkflowStateEngine.get_state`); engines-2 (`WorkflowStateEngine.transition_phase`); engines-3 to -4 (`WorkflowStateEngine.complete_phase`); engines-5 (`WorkflowStateEngine.list_by_phase`); engines-6 (`WorkflowStateEngine.list_by_status`).
- `workflow_engine/entity_engine.py`: engines-11 (`EntityWorkflowEngine.complete_phase`); engines-12 (`EntityWorkflowEngine.transition_phase`); engines-13 to -14 (`EntityWorkflowEngine.get_state`); engines-15 (`EntityWorkflowEngine.abandon_entity`); engines-16 (`EntityWorkflowEngine._abandon_descendants`); engines-17 to -19 (`EntityWorkflowEngine._fived_complete`); engines-20 to -21 (`EntityWorkflowEngine._fived_transition`); engines-22 (`EntityWorkflowEngine._propagate_anomaly`); engines-23 (`EntityWorkflowEngine._get_weight`).
- `workflow_engine/feature_lifecycle.py`: engines-24 to -27 (`_promote_brainstorm`); engines-28 to -32 (`init_feature_state`); engines-33 to -34 (`activate_feature`).
- `workflow_engine/feature_paths.py`: engines-10 (`feature_dir_name`).
- `workflow_engine/reconciliation.py`: engines-40 to -42 (`_check_single_feature`); engines-46 to -47 (`_recover_pending_cascades`; rewritten by 1B: first check 4); engines-48 to -49 (`check_workflow_drift`).
- `workflow_engine/rollup.py`: engines-50 (`_get_workflow_phase / compute_progress`); engines-51 (`compute_okr_score`); engines-52 (`compute_objective_score`); engines-53 (`rollup_parent`).
- `workflow_engine/router.py`: engines-54 to -56 (`init_entity_workflow`); engines-57 to -60 (`transition_entity_phase`).
- `workflow_engine/secretary_intelligence.py`: engines-61 to -62 (`get_parent_context`).
- `workflow_engine/task_promotion.py`: engines-35 (`query_ready_tasks`); engines-36 to -39 (`promote_task`).

- **Rows owned elsewhere that you touch:**
  - the one `entity_server.py` call (change 3);
  - the call sites of schema-50, -54 and -57, which R4-F4 owns: pass the workspace where you hold one.

**Red-first tests (new)**
1. **`plugins/pd/hooks/lib/entity_registry/test_naming_rule.py`** (rekey §10 names the file; R4-B, R4-C and R4-F4 extend it). A table of per-pair call adapters, one minimal call per (method, parameter) pair, lives at the top of the file. R4-F4's refusal test reuses it. Its fixtures hold a third workspace, N, whose `project_id_legacy` is NULL and which holds a namesake: 7 of the 21 live workspaces have no legacy id. Each parametrized case also runs against N (PM-CODE-W8).
   - **`test_entity_naming_methods_lists_the_twenty_pairs`:**
     - *asserts:* the constant equals rekey §6.3's list;
     - *red on base:* the constant does not exist.
   - **`test_type_id_resolves_only_in_callers_workspace[<pair>]`**, for the 18 pairs other than `append_phase_event.type_id` and `query_phase_events.type_id`, which R4-C adds.
     - *the setup:* `feature:X` is registered in workspace A only.
     - *asserts, called with `workspace_uuid=B`:* the method does not act on A's entity. It raises its not-found `ValueError`, or answers None or empty, and A's entity and row are unchanged (per-table fingerprints before and after).
     - *asserts, called with A:* it acts on A's entity.
     - *red on base:* the `get_entity`, `get_workflow_phase` and `feature_entity_id` cases, whose keyword does not exist yet.
     - *expected keep-green:* the other 15 cases, whose methods already resolve inside a given workspace on the base (for example `resolve_ref`'s scoped exact match, then its scoped prefix search). Your report lists them. A case that turns out red on the base is recorded as red, with its reason.
   - **`test_uuid_resolves_its_entity_whatever_the_workspace[<pair>]`** (rekey §10), for the 15 pairs whose parameter is an identifier R4-A resolves (PM-CODE-B1): `resolve_ref.ref`, `set_parent.type_id`, `set_parent.parent_type_id`, `reparent_entity.type_id`, `get_entity.type_id`, `feature_entity_id.type_id`, `get_lineage.type_id`, `set_archived.type_id`, `set_deleted.type_id`, `update_entity.type_id`, `delete_entity.type_id`, `export_lineage_markdown.type_id`, `create_workflow_phase.type_id`, `get_workflow_phase.type_id`, `upsert_workflow_phase.type_id`.
     - *asserts:* A's uuid passed with `workspace_uuid=B` names A's entity;
     - *red on base:* five cases: `get_entity`, `get_workflow_phase` and `feature_entity_id` (the keyword is new: a `TypeError`), and `set_archived` and `set_deleted` (a uuid with another workspace raises);
     - *expected keep-green:* the other 10. Record each case's base outcome; a case the base run shows red is recorded red, with its reason;
     - *no case* for `resolve_entity_uuid.type_id` or `search_by_type_id_prefix.prefix`: they take type_id text by contract, not an identifier (rekey §6.1, §6.3). R4-C adds `update_workflow_phase.type_id`, `append_phase_event.type_id` and `query_phase_events.type_id`, whose rows and events it keys by entity uuid.
   - **`test_set_archived_without_workspace_on_shared_type_id_raises`** (rekey §15):
     - *the setup:* `feature:X` in A and B;
     - *asserts:* `set_archived("feature:X")` raises `ValueError`, and neither entity's `is_archived` changes;
     - *red on base:* both are archived.
   - **`test_set_deleted_without_workspace_on_shared_type_id_raises`** (playbook addition): the same for `set_deleted`. Red on base.
   - **`test_set_archived_by_uuid_archives_only_that_entity`** (playbook addition; W1.2's form): keep-green, because 1B added `set_archived`'s by-uuid branch (database.py:8436).
     - *asserts:* `set_archived(uuid_a)` archives A only.
   - **`test_set_deleted_by_uuid_deletes_only_that_entity`** (playbook addition, R3; PM-CODE-W6):
     - *asserts:* `set_deleted(uuid_a)` soft-deletes A only;
     - *red on base:* `set_deleted` has no uuid path (`WHERE type_id = ?`, database.py:8505), so it raises "no entity with type_id '<uuid>'".
2. **`plugins/pd/hooks/lib/workflow_engine/test_engine_reads_in_given_workspace.py`** (playbook addition):
   - **`test_engine_read_path_resolves_in_given_workspace[<entry>]`**, for: `WorkflowStateEngine.get_state`, `WorkflowStateEngine.validate_prerequisites`, `EntityWorkflowEngine.get_state`, `feature_lifecycle.activate_feature`, `router.init_entity_workflow`, `router.transition_entity_phase`, `task_promotion.promote_task`, `reconciliation.check_workflow_drift` and `secretary_intelligence.get_parent_context`.
     - *the setup:* the entity is in A only.
     - *asserts, called with `workspace_uuid=B`:* the entry's not-found answer, and A's rows unchanged.
     - *asserts, called with A:* it acts on A's entity.
     - *red on base:* the keyword is missing, or the unscoped read finds A's entity.
3. **`plugins/pd/hooks/lib/entity_registry/test_clis_resolve_their_workspace.py`** (playbook addition):
   - **`test_cli_reads_its_projects_namesake[frontmatter_inject|frontmatter_sync_single|frontmatter_sync_backfill|secretary_parent_context]`:**
     - *the setup:* `feature:X` in A and B, with different fields; the project root resolves to B (pin it with `ENTITY_WORKSPACE_UUID`, as the servers' tests do).
     - *asserts:* the CLI reads B's entity. For `frontmatter_sync_backfill`, also the scoped listing (PM-CODE-W9): only B's features are listed.
     - *red on base:* the unscoped `get_entity` answers None for a shared type_id, and `backfill_headers` lists every workspace's features (frontmatter_sync.py:518).
   - **`test_cli_skips_when_its_workspace_does_not_resolve[...]`:**
     - *the setup:* nothing resolves: no `ENTITY_WORKSPACE_UUID`, no `workspace.json`, and no `workspaces` row for the root.
     - *asserts:* exit 0, a warning on stderr, nothing written, and no workspace minted (no `workspace.json` created, no `workspaces` row added).
     - *red on base:* the base never resolves a workspace, so it writes.
4. **`plugins/pd/scripts/tests/test_cleanup_backlog_workspace.py`** (playbook addition; G2 collects it):
   - **`test_apply_archival_archives_only_its_workspaces_item`:**
     - *the setup:* `backlog:N` in A and B;
     - *asserts:* archival run for A archives only A's item;
     - *red on base:* the unscoped write archives both.
   - **`test_apply_archival_archives_nothing_when_the_workspace_does_not_resolve`** (R3; PM-CODE-W9):
     - *the setup:* the backlog's project root is no known workspace;
     - *asserts:* no item is archived, and the error names the root;
     - *red on base:* the loop archives before the lookup (cleanup_backlog.py:257-262, then :275-286).

**Existing tests**
- **Delete** (rekey §6.3: `delete_workflow_phase` deleted). The four tests in `test_database.py` that call it, at `4a6373f0`:
  - `test_delete_workflow_phase_existing_removes_row` (:3481);
  - `test_delete_workflow_phase_nonexistent_raises` (:3497);
  - `test_get_returns_none_after_delete` (:3504);
  - `test_delete_nonexistent_message_contains_type_id` (:4042).
- **Delete or rewrite** (rekey §8: the `parent_type_id` branch deleted). Tests that pass a non-None `parent_type_id` to `_process_register_entity`, at `4a6373f0` `test_server_helpers.py:125-177` and `test_entity_server.py:437`, `:452`:
  - **delete** the ones whose subject is the branch;
  - **rewrite with `parent_uuid`** the ones where it is setup.
- **Rewrite and delete** (rekey §6.3: `feature_entity_id` answers the resolved entity's value only; BLAST-B3):
  - **rewrite** `entity_registry/test_c11_feature_entity_id.py::test_a_type_id_held_in_two_workspaces_answers_once` (:84) to pass each workspace's `workspace_uuid`, and to assert that each answers its own `entity_id` (`003-shared`);
  - **delete** `entity_registry/test_c11_feature_entity_id.py::test_two_distinct_values_for_one_type_id_are_refused` (:111) and `workflow_engine/test_c11_feature_paths.py::test_disagreeing_rows_are_refused` (:115): their subject, reading every namesake's value at once, is gone.
- **Everything else stays green unchanged, apart from the tests listed above,** because the change is additive (rekey §15 RK1). A failure elsewhere is a breakage to fix, not a test to delete.

**Gates**
- **G1:** grows by the three new test files, and shrinks by the four `delete_workflow_phase` tests, the `parent_type_id`-branch tests you delete and the two test_c11 deletions. Your report lists each.
- **G2:** grows by `test_cleanup_backlog_workspace.py`.
- **G3–G5:** unchanged.

**QA probes**
1. **On a temp DB with `feature:X` in A and B:**
   - `get_entity("feature:X", workspace_uuid=B)` answers B's entity;
   - `get_entity("feature:X")` still answers None (until R4-F4);
   - `get_workflow_phase("feature:X", workspace_uuid=B)` answers None when only A has a row, and A's row for A.
2. **The archive flags:** `set_archived("feature:X")` raises and changes neither entity; `set_archived(uuid_a)` archives only A (as on the base, since 1B). Repeat both for `set_deleted`, whose by-uuid form is new.
3. **`git grep -n 'delete_workflow_phase' -- plugins scripts`** prints only docs and records. R4-H handles the docs.
4. **`git grep -n 'parent_type_id' plugins/pd/hooks/lib/entity_registry/server_helpers.py`** prints nothing.
5. **Every production call of `get_entity(`, `get_workflow_phase(`, `feature_entity_id(` and the directory helpers** under `plugins/pd/hooks/lib` and `plugins/pd/scripts` passes `workspace_uuid=` or a uuid. A label-only call (`project_id=` with no `workspace_uuid=`) counts as a straggler too (PM-CODE-W8). Expected: 0, or each listed with its reason; the `phase_events` readers are R4-C's.
6. **Run `frontmatter_inject.py`** in a temp repo pinned to B, for a shared type_id: B's fields are injected. In a temp repo that resolves no workspace, it exits 0 with a warning, and neither a `workspace.json` nor a `workspaces` row appears.

**Reviewer focus**
- **The engine contract** holds on every engine method that takes a type_id (rekey §8).
- **No single-workspace caller changes behaviour,** except `set_archived` and `set_deleted`.
- **The keep-green cases** really are green on the base for the reason given: the 15 of `test_type_id_resolves_only_in_callers_workspace`, and the 10 of `test_uuid_resolves_its_entity_whatever_the_workspace`.
- **No `.meta.json` fallback** answers a missing workspace.
- **No CLI mints a workspace,** and none reads the registry before its workspace resolves.
- **The entry-point table** names every engine and helper that names an entity (PM-CODE-W4).

### 1.4 R4-B: the two MCP servers pass the caller's workspace (RK1, part 2)

- **Implements:**
  - rekey §6.5: the MCP boundary;
  - rekey §8: the rows "Workflow server tools" and "Entity server tools";
  - rekey §6.3: the `resolve_entity_uuid` row;
  - rekey §12: W4.1's "Read tools keep today's behaviour" is superseded for read tools that name an entity.
- **Depends on:** R4-A.
- **Can run beside:** R4-C0.
- **Waits for:** Q3 (section 0.4), for the three list tools only. Without a ruling, those three keep today's fallback.
- **Files:**
  - `plugins/pd/mcp/workflow_state_server.py`;
  - `plugins/pd/mcp/entity_server.py`;
  - `plugins/pd/hooks/lib/entity_registry/database.py`: `resolve_entity_uuid` only;
  - `plugins/pd/hooks/lib/entity_registry/server_helpers.py`: the export-lineage path the entity server's tool reaches (BLAST-W2; R4-A adds its `workspace_uuid` parameter);
  - the new test file and the extended `test_naming_rule.py` below, and the existing tests named below.

**Brief**

**Goal.** Every MCP tool argument that names an entity resolves inside the caller's workspace, which `_require_workspace()` returns (W4.1). Parameters and replies do not change (rekey §6.5).

**Read first:** rekey §6.5, §8 (the two server rows), §12 (what W4.1 text this supersedes), and 2A's and 2C's landed changes: `_require_workspace()`, and `_resolve_ref_param` (W3.4).

**First checks:**
1. **The landed `_require_workspace()`** in both servers, and the write tools that already call it (task 2A).
2. **The landed `_resolve_ref_param`** and the entity tools that call it (task 2C). Compare it with `_process_update_entity`'s `resolve_ref(resolved_type_id, project_id=project_id)` (entity_server.py:399, MCPE-10, added by 1B) and with `_process_delete_entity`, and record how each resolves today (PM-CONS-W2).
3. **The user's ruling on Q3.** The orchestrator states it in your dispatch; without one, the list tools stay as they are.

**Changes**
1. **Workflow server.** Every tool argument that names an entity (`feature_type_id`, `type_id`, `ref` or `entity_ref`) resolves inside `_require_workspace()`. Each `get_entity`, `resolve_ref` or engine call in a handler passes `workspace_uuid=_require_workspace()`.
   - **The read tools this adds** (rekey §6.5):
     - `get_phase`, `get_mini_spec` (its entity resolution only; its event read is R4-C's), `validate_prerequisites` and `reproject_meta_json`;
     - `reconcile_check` and `reconcile_frontmatter`;
     - `get_progress_view`;
     - `query_phase_analytics`' `feature_type_id` filter (the resolution only; the event pairing is R4-C's);
     - `record_backward_event`'s reads.
   - **The write tools W4.1 covers** keep calling it.
   - **`_artifact_dir`** (workflow_state_server.py:422) passes the resolved feature's `workspace_uuid` to the directory helper (rekey §6.3).
2. **The three list tools** (`list_features_by_phase`, `list_features_by_status`, `query_ready_tasks`) change only if the user says yes to Q3 (rekey §6.5):
   - **`project_id` omitted:** they call `_require_workspace()`, which refuses when the workspace is unresolved;
   - **`'*'`:** lists every workspace;
   - **a legacy id:** lists its workspace, or answers `invalid_project_id`, as today (:2406-2448).

   Without a yes, they stay as they are (W4.1's text stands).
3. **Entity server:**
   - `_resolve_ref_param` (W3.4, entity_server.py:316-360) resolves in `_require_workspace()`'s workspace;
   - the read tools that name an entity do the same: `get_entity`, `get_lineage`, `export_lineage_markdown`'s `type_id`, `get_entity_tags` and `get_okr_alignments`;
   - after `_resolve_ref_param`, reads go by the resolved uuid;
   - direct `get_entity` reads (entity_server.py:424, :493, :1061, :1335) pass the workspace;
   - **`_process_update_entity`'s `resolve_ref`** (entity_server.py:399, MCPE-10, added by 1B): `resolve_ref(resolved_type_id, project_id=project_id)` passes `workspace_uuid=_require_workspace()` (PM-CONS-W2);
   - **`export_lineage_markdown`'s tool** (entity_server.py:1207) passes `_require_workspace()` to `_process_export_lineage_markdown` (server_helpers.py:369), whose parameter R4-A adds (BLAST-W2);
   - **label-only calls** (PM-CODE-W8): a call with `project_id=` and no `workspace_uuid=` is unscoped (rekey §6.5). Each one in the two servers passes the workspace or a uuid: at `5cc2ab75`, 20 in `entity_server.py` (for example :1026, :1057, :1370-1371) and 5 in `workflow_state_server.py` (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/premortem/probes/label_only_calls-5cc2ab75.out`);
   - `_effective_project_id()` survives only as the filter of list and export tools that accept `'*'`.
4. **The phase-event writers** (MCPE-5, -6, -10, -11, -13; MCPW-10, -18, -23, -35, -42): confirm that each passes a `workspace_uuid` to `append_phase_event`. rekey §3.1 found that all 10 production call sites do. No edit to those calls is expected; record each one in your report. MCPE-10's handler has one edit, its `resolve_ref` (change 3).
5. **`resolve_entity_uuid(workspace_uuid, type_id)`** raises `ValueError` when `workspace_uuid` is None; today `WHERE workspace_uuid = NULL` answers `(None, None)`. Its three production calls (workflow_state_server.py:1085, :1436, :1440) pass `_require_workspace()`.
6. **Errors** (rekey §6.5):
   - a type_id not found in the caller's workspace answers the tool's existing not-found envelope;
   - an unresolved workspace answers `workspace_unresolved`.
7. **The handler entry-point table** (PM-CODE-W4), in your report: for every MCP handler that names an entity, whether its caller passes the workspace or the handler derives it (from `_require_workspace()`, or from a resolved uuid). The codemod's list (1.8.0) adds every handler whose tests must pass the workspace; at `ddc299a0` the blast census counts 250 MCP-handler test sites in 13 files outside the design's method list.

**Checklist:**


- `entity_registry/database.py`: schema-55 (`resolve_entity_uuid`).
- `plugins/pd/mcp/entity_server.py`: MCPE-1 to -3 (`lifespan`); MCPE-4 (`_resolve_ref_param`); MCPE-5 (`register_entity`); MCPE-6 (`issue_spawn`); MCPE-7 (`set_parent / _process_set_parent`); MCPE-8 (`get_entity`); MCPE-9 (`get_lineage / _process_get_lineage`); MCPE-10 (`update_entity / _process_update_entity`; its `resolve_ref` at :399, change 3); MCPE-11 (`delete_entity / _process_delete_entity`); MCPE-12 (`add_entity_tag / get_entity_tags`); MCPE-13 (`remove_dependency / _process_remove_dependency`); MCPE-14 (`create_key_result / _process_create_key_result`); MCPE-15 (`update_kr_score / _process_update_kr_score`); MCPE-16 (`add_dependency / add_okr_alignment / get_okr_alignments`); synth-2 (`export_lineage_markdown MCP tool -> _process_export_lineage_`; the call is entity_server.py:1207 → server_helpers.py:369).
- `plugins/pd/mcp/workflow_state_server.py`: MCPW-1 (`_resolve_ref_to_feature_type_id`); MCPW-2 (`get_phase / _process_get_phase`); MCPW-3 (`validate_prerequisites / _process_validate_prerequisites`); MCPW-4 (`transition_phase / _process_transition_phase`); MCPW-5, -8 to -10 (`_process_transition_phase`); MCPW-6 (`_process_transition_phase -> engine.transition_phase / entit`); MCPW-7 (`_transitioned_entity_row`); MCPW-11 (`_process_transition_phase / _process_complete_phase / _proce`); MCPW-12 (`complete_phase / _process_complete_phase`); MCPW-13, -15 to -19 (`_process_complete_phase`); MCPW-14 (`_process_complete_phase -> engine.complete_phase / entity_en`); MCPW-20 (`_resolve_project_id`); MCPW-21 (`_project_meta_json`); MCPW-23 (`record_mini_spec`); MCPW-25 (`reproject_meta_json / _process_reproject_meta_json`); MCPW-26 (`list_features_by_phase / _process_list_features_by_phase`); MCPW-27 (`list_features_by_status / _process_list_features_by_status`); MCPW-28 (`_resolve_list_handler_workspace_filter`); MCPW-29 (`reconcile_check / _process_reconcile_check`); MCPW-32 (`reconcile_frontmatter / _process_reconcile_frontmatter`); MCPW-33 (`reconcile_status / _process_reconcile_status`); MCPW-34 (`init_feature_state / _process_init_feature_state`); MCPW-35 (`init_project_state / _process_init_project_state`); MCPW-36 (`activate_feature / _process_activate_feature`); MCPW-37 (`init_entity_workflow / _process_init_entity_workflow`); MCPW-38 (`transition_entity_phase / _process_transition_entity_phase`); MCPW-39 (`promote_task`); MCPW-40 (`query_ready_tasks`); MCPW-41 (`get_progress_view`); MCPW-42 (`record_backward_event`); MCPW-44 (`lifespan`).


**Red-first tests (new)**
1. **`plugins/pd/mcp/test_read_tools_resolve_in_workspace.py`** (playbook addition). Both servers start through their real lifespans, against a temp DB, a temp HOME and a temp repo, pinned with `ENTITY_WORKSPACE_UUID`. Follow the harness of 2A's `test_require_workspace.py`. The fixture also holds a workspace whose `project_id_legacy` is NULL and which holds a namesake, and each parametrized case runs against it too (PM-CODE-W8).
   - **`test_workflow_read_tool_answers_not_found_for_another_workspaces_type_id[get_phase|get_mini_spec|validate_prerequisites|reproject_meta_json|reconcile_check|reconcile_frontmatter|get_progress_view|record_backward_event]`:**
     - *the setup:* `feature:X` in A only; the server pinned to B.
     - *asserts:* the tool's existing not-found envelope, and A's rows and events unchanged.
     - *red on base:* the handler passes no workspace, so the fallback resolves A's feature and answers with A's data. `record_backward_event` would write an event for A's entity.
   - **`test_entity_read_tool_answers_not_found_for_another_workspaces_type_id[get_entity|get_lineage|export_lineage_markdown|get_entity_tags|get_okr_alignments]`:** the same. Red on base.
   - **`test_read_tool_answers_its_own_namesake[get_phase|get_entity|get_lineage|export_lineage_markdown]`:**
     - *the setup:* `feature:X` in A and B; the server pinned to B.
     - *asserts:* the tool answers B's entity. The export in B lists B's lineage only (BLAST-W2).
     - *red on base:* the unscoped `get_entity` answers None for a shared type_id, `resolve_ref`'s exact match takes the lowest rowid, and the export passes a label only (server_helpers.py:369).
   - **`test_read_tool_answers_workspace_unresolved`:**
     - *the setup:* the workspace does not resolve.
     - *asserts:* `get_phase` answers `workspace_unresolved`.
     - *red on base:* read tools fall back to a global read.
   - **`test_uuid_argument_reaches_its_entity_in_any_workspace[get_entity|get_lineage]`:** keep-green (D5).
   - **Only if the user says yes to Q3:**
     - `test_list_tool_scopes_to_callers_workspace_when_project_id_omitted[list_features_by_phase|list_features_by_status|query_ready_tasks]`. Red on base: it lists every workspace.
     - `test_list_tool_star_lists_every_workspace[...]`. Keep-green.
2. **In `test_naming_rule.py`: `test_resolve_entity_uuid_refuses_a_missing_workspace`.**
   - *asserts:* `resolve_entity_uuid(None, "feature:X")` raises `ValueError`.
   - *red on base:* it answers `(None, None)`.

**Existing tests**
- **Rewrite:** tests that call a read tool naming an entity, with no resolved workspace or from another workspace, and expect today's global answer.
  - **How:** pin the workspace in the fixture (`ENTITY_WORKSPACE_UUID`, or the server's `_workspace_uuid`), and leave the assertions unchanged.
  - **In 2A's and 2C's files** (`test_require_workspace.py`, `test_entity_tools_resolve_in_workspace.py`): an assertion of W4.1's "read tools keep today's behaviour" for a read tool that names an entity is rewritten to the new rule, citing rekey §12. The list-tool assertions stay unless Q3 is yes.
- **Unchanged:** feature 129's four cross-workspace tests (plan:257).
- **Delete:** none.

**Gates**
- **G1:** grows by the new file and the new `test_naming_rule.py` case.
- **G2–G5:** unchanged.

**QA probes**
1. **Start both servers against a temp DB** holding `feature:X` in A and B and `feature:Y` in A only, pinned to B:
   - `get_phase`, `get_entity` and `get_lineage` for X answer B's entity;
   - for Y they answer the not-found envelope;
   - unpinned, with no resolvable repo, they answer `workspace_unresolved`.
2. **A's uuid, passed from B,** still reaches A's entity (D5).
3. **`grep -n 'get_entity(\|resolve_ref(\|resolve_entity_uuid(' plugins/pd/mcp/*.py`** (production files): every call passes a workspace or a uuid. Label-only calls (`project_id=` with no `workspace_uuid=`) count as stragglers too (PM-CODE-W8). Expected: 0, or each listed with its reason.
4. **The list tools** behave as the user's ruling on Q3 says.

**Reviewer focus**
- **No read tool that names an entity** still falls back to every workspace.
- **Replies and parameters are unchanged,** so no command or skill markdown needs to change (rekey §6.5, open question 6).
- **Every refusal** uses the existing envelopes.

### 1.4a R4-C0: the tests' raw SQL behind shape-aware helpers (RK2, preparation; new in R3)

- **Implements:** the test half of rekey §15 RK2, prepared before the flip (PM-CODE-W11). R4-C's test changes then edit a few helpers, not about 38 test files.
- **Depends on:** nothing inside Phase R. Outside it: as R4-A (Phase 1, 2A and 2C landed; Q1 answered).
- **Can run beside:** R4-A and R4-B.
- **Files:**
  - `plugins/pd/hooks/lib/entity_registry/test_helpers.py`: the helpers;
  - every test file with raw SQL on `workflow_phases` or `phase_events`, except those under "Out". The measured list is below.
- **Out** (R4-C's, or history kept as written):
  - tests that stop the chain before version 26 or 8, or pin a historical schema: for example the migration-safety files of migrations 12, 13, 14 and 19, the `make_v10_db` family of builders, `test_search.py`'s migration-3 scaffolding, and the doctor tests' hand-rolled old DDL (`test_checks.py`, `test_fixer.py`);
  - the head-schema pins (`PRAGMA table_info`, trigger and index names), which R4-C restates in place: this task changes no assertion;
  - `scripts/test_migrate_db.py`: R4-C owns `TestMigration6`'s three row assertions;
  - the files R4-C deletes (`scripts/test_c22_recreate_live_remainder.py`, `scripts/test_fix_kanban_columns.py`);
  - any row or event with no entity behind it (the `_insert_orphan_workflow_row`, `_add_orphan_row` and `_seed_workflow_row` cases), whether the orphan is the test's subject or only setup: R4-C deletes those cases, or registers the entity;
  - the tests pinning the row key that R4-C restates: 1A's four files (`test_workflow_phase_writers.py`, `test_backfill_scoped.py`, `test_create_feature_lanes.py`, `test_projection_names_directory.py`) and 1C's skip tests.
- **Inventory rows:** none of its own. It touches R4-C's test rows that carry raw SQL, and R4-F1 to R4-F3's; their owners keep them (1.13).

**Brief**

**Goal.** Every raw-SQL statement on the two tables in a test file goes through a helper keyed by the entity's uuid, so the tests read and write rows the same way on the old shape and, once R4-C flips it, on the new. No production code changes, and no assertion changes.

**Read first:** rekey §4.2 (the target shape), §6.2 (the row view), §15 RK2, and R4-C's "Existing tests" (1.5), which this task prepares.

**First checks:**
1. **Re-count the raw SQL** on the two tables in test files on your base, per file. The lists below were measured at `4a6373f0`; the premortem counted 38 test files at `5cc2ab75`. Record old → new counts.
2. **The Phase 1 drift check** (1.2), with the two table names.

**Changes**
1. **The helpers** (`test_helpers.py`), each keyed by the entity's uuid. The names are this playbook's; if your base already has an equivalent helper, extend it and record the mapping.
   - `write_workflow_row(conn, entity_uuid, **state)`: inserts or replaces the entity's row, with the given state columns;
   - `read_workflow_row(conn, entity_uuid)`: the entity's row as a dict, or None;
   - `insert_phase_event(conn, entity_uuid, **fields)`: inserts one event, with the entity's `type_id` as its label unless a field gives another; `project_id` stays a label, as passed.
   - **Shape detection:** `PRAGMA table_info` on the table. The old shape has `type_id` and no `entity_uuid`.
   - **On the old shape,** a helper looks up the entity's `(workspace_uuid, type_id)` and writes those columns, and, for `workflow_phases`, `uuid` = the entity's uuid, as 1A's writers store it. **On the new,** it writes `entity_uuid`.
2. **Convert every statement in scope:** a raw `INSERT`, `UPDATE`, `DELETE` or `SELECT` of a row or an event becomes the helper call. A count or an existence check reads through `read_workflow_row` or the API.
3. **Record every converted statement** in your report: file, line, the old statement, and the helper call.

**The measured raw-SQL list** (moved here from R4-C; re-count on your base):
- **On `workflow_phases` at `4a6373f0`: 118 statements in 28 files** (from `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/scan/wp_sql_rows.json` and `sql_sites.json`):
  - `test_database.py` 50;
  - `scripts/test_migrate_db.py` 10 (out);
  - `test_workflow_state_server.py` 9;
  - `test_backfill.py` 5, and `scripts/test_fix_kanban_columns.py` 5 (out: R4-C deletes it);
  - `scripts/test_c22_recreate_live_remainder.py` 4 (out: R4-C deletes it);
  - 3 each: `test_checks.py` and `test_fixer.py` (out: hand-rolled old DDL), `test_migration_safety.py` (out: migration-12 history), `test_status_only_lifecycle.py`;
  - 2 each: `test_rebuild_tool.py`, `test_reconciliation.py`, `test_complete_phase_closes.py`, `test_issue_spawn.py`, `ui/tests/test_app.py`;
  - 1 each: `test_board_archived_query.py`, `test_entity_lifecycle.py`, `test_migration_13_safety.py` (out: history), `test_register_upsert_split.py`, `test_search.py` (out: migration-3 scaffolding), `test_c11_engine_dir_name.py`, `test_c11_reconciliation_dir_name.py` and `test_c8_kind_from_column.py` (their orphan helpers are out), `test_create_feature_lanes.py` (out: 1A's), and four UI test files (`test_board_archived.py`, `test_c8_card_kind.py`, `test_deepened_app.py`, `test_entities.py`).
- **On `phase_events`,** the files with raw INSERTs: `test_event_sourced_state.py`, `test_migration_13_safety.py` (out), `test_migration_19_safety.py` (out), `test_pd_state_diff.py` and `test_phase_events_adversarial.py`.
  - **Why they matter:** after R4-C, a raw `source='live'` INSERT with no `entity_uuid` aborts (`pe_reject_live_event_without_entity`), unless the file stops the chain before version 26 or 8. Through the helper, the INSERT names its entity.

**Red-first tests:** none. The helpers are exercised by every converted test, on the old shape here and on the new at R4-C. QA probe 2 shows that no converted statement bypasses them.

**Existing tests:** converted as above, with assertions unchanged. None is deleted.

**Gates**
- **G1–G5:** failures equal the base's. No assertion changes.
- **The report** lists every converted statement, against the re-count on base.

**QA probes**
1. **Re-count on the head:** no raw SQL on the two tables is left in a test file, outside "Out".
2. **The helpers carry every converted statement:** patch the three helpers to raise, and run the converted files. Every test that had a converted statement fails.
3. **`git diff <base> -- '*test_*.py' | grep -E '^[-+][[:space:]]*assert'`** prints nothing.

**Reviewer focus**
- **No assertion changed,** and nothing under "Out" was converted.
- **On the old shape,** the helpers write exactly the columns the old statements wrote (the stored `uuid` included), so every converted test passes for the same reason as before.

### 1.5 R4-C: the schema flip (RK2)

- **Implements:**
  - rekey §3 (`phase_events` gains the entity key), §4 (the target schema and the migration), §5 (the data rules);
  - rekey §6.2 (the row view), §6.3 (the row and event methods), §7 W3.3 (the cascade and the fallback deleted);
  - rekey §14 (`rebuild_tool`, the doctor, the scripts, the deletions) and §15 RK2.
  - The docs sweep moves to R4-H (section 0.2, item 3).
- **Depends on:** R4-B and R4-C0. Outside Phase R: task 4C landed on develop (BLAST-B1). If 4C has not landed when R4-B merges, this task carries 4C's contract (change 0), and the orchestrator tells 4C's owner.
- **Files:**
  - `plugins/pd/hooks/lib/entity_registry/`:
    - `database.py` (with the migration runners `_migrate` and `_migrate_v2`, only if you carry 4C's contract);
    - `schema_v2.py`;
    - `views.py` (read only: its text is the target);
    - `rebuild_tool.py`;
    - `backfill.py` (only `run_backfill`'s comparisons);
    - `test_helpers.py`: `make_pre_rekey_db`, `seed_rekey_classes`, and R4-C0's shape-aware helpers, which you check on the new shape;
  - `plugins/pd/hooks/lib/workflow_engine/`: `reconciliation.py` (`check_workflow_drift`'s map, and C8's orphan branch if W1 left it) and `engine.py` (`list_by_status`' map);
  - `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py`: 1C's skip, deleted (change 15; BLAST-B2);
  - `plugins/pd/hooks/lib/doctor/`: `checks.py`, `fix_actions/__init__.py`, `fixer.py`, `check_status_write_path.py`;
  - `plugins/pd/mcp/workflow_state_server.py`: the four `phase_events` readers, and `reconcile_status`' docstring (change 7);
  - `plugins/pd/scripts/pd_state_diff.py`;
  - `scripts/test_migrate_db.py`: `TestMigration6`'s three row assertions only (change 14; BUILD-W2);
  - **deleted:** `scripts/c22_recreate_live_remainder.py`, `scripts/test_c22_recreate_live_remainder.py`, `scripts/fix_kanban_columns.py`, `scripts/test_fix_kanban_columns.py`;
  - **test files:** the new ones below; the checklist's; 1A's four; the raw SQL R4-C0 left out (1.4a, "Out"); and the listed rewrites, among them `workflow_engine/test_engine.py` (BLAST-W1), `entity_registry/test_migration_14_safety.py` (BUILD-S6), and, for 1C's skip, `reconciliation_orchestrator/test_brainstorm_registration_scoped.py`, `test_c5b_brainstorm_workspace.py`, `test_entity_status.py` and `test_orchestrator.py` (BLAST-B2).

**Brief**

**Goal.** Both tables are keyed by the entity uuid, on both migration chains, through one resumable migration. Every statement on the two tables uses the new key, and every test passes on the new shape.

**Read first:** rekey §3, §4, §5, §6.2, §6.3, §7 (W3.3), §10 (criteria 1, 2, 3, 5 and 6), §14, §15 RK2, and Part 2 of this playbook, which is the exact migration.

**Work in this order, to keep your context bounded:**
1. First checks.
2. Only if 4C has not landed: change 0, with its own red-first tests.
3. The test helpers (`make_pre_rekey_db`, `seed_rekey_classes`).
4. The red-first tests: write them, run them on your base, save the output.
5. The migration, its registration and its tripwire.
6. The `database.py` statements.
7. Engine maps, server readers, `rebuild_tool`, doctor, `pd_state_diff`, 1C's skip, deletions.
8. Existing tests, file by file. R4-C0's helpers carry most of them; the rest are listed below.
9. The gates.

**First checks:**
1. **C8's orphan `db_only` branch** in `reconciliation.py`: did W1 leave it? If it did, delete it with its tests. Record which (rekey §9, open question 14).
2. **`TestMigration6`** (BUILD-W2): its three row assertions (`scripts/test_migrate_db.py`: `test_migration_no_orphaned_workflow_phases` :1080, `test_migration_no_null_uuids_in_workflow_phases` :1095, `test_migration_workflow_phases_uuid_backfill` :1222) reach the head chain through `cmd_migrate`'s `EntityDatabase` (migrate_db.py:355, which opens it at :391 and :488). So they break at this task whether or not 4B lands, and they are yours (change 14). Record G5's base: 7 `TestMigration6` tests already fail on it (the core build's G5 at `ddc299a0`). tests-67 to -69's other parts stay out (rekey §14).
3. **The Phase 1 drift check,** with the table and method names of this task.
4. **Task 4C** (BLAST-B1): has it landed on your base? If it has, confirm that the migration runner is serialized and its stamp monotonic (4C's contract), and run 4C's race tests once migration 26 is registered (Gates). If it has not, you carry 4C's contract (change 0), and the orchestrator tells 4C's owner.

**Changes**
0. **Only if 4C has not landed on your base** (BLAST-B1): 4C's five-point contract, as its brief's AMENDMENT states it (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/release-c-followups-execution/phase-2-4/briefs/4c.md`):
   1. **Serialized:** concurrent openers never run a migration step another process has already applied, on both chains (`_migrate`, database.py:11078; `_migrate_v2`, :11191). For example, re-read the version under a write lock before each step and skip what is done, or hold one cross-process lock around the whole pending run. Keep the migrations that manage their own transactions and `PRAGMA foreign_keys` working.
   2. **Monotonic:** the `schema_version` stamp never decreases; today `_upsert_metadata` (:5896, `ON CONFLICT DO UPDATE`) can lower it. A stored higher value is kept, and the loser stops.
   3. **Unchanged single-process behaviour:** resumable after a crash between steps, idempotent on re-open, and the C23 future-file guard (`_refuse_if_file_is_from_the_future`) still fires first.
   4. **Tests, red first:** a fresh-file race; an old-file race from a file stamped at 10, on the v1 chain; the v2 chain; the monotonic stamp; and `test_migration_11_concurrent_runners` passing 50 consecutive runs, its subject kept. The red run uses a probe that forks runners, as `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/blast/work/race_probe.py` does: record the brick rate on the base, and zero on the head.
   5. **Sweep:** `_migrate`'s and `_migrate_v2`'s docstrings, and any doc that says a migration runs once per file.
1. **The test helpers** (`test_helpers.py`; rekey §9, open question 22):
   - **`make_pre_rekey_db(path, generation, *, stale_axis_view=False)`** builds a file at the pre-re-key shape. It uses patched copies of `MIGRATIONS` and `V2_MIGRATIONS` with the re-key entries left out, and `V2_SCHEMA_VERSION` 7, and restores the module state afterwards.
     - `generation="v1"`: the fresh chain at 25.
     - `generation="v2"`: a staging build (`rebuild_tool.build_staging_database`) at 7.
     - `stale_axis_view=True` (BUILD-S4): installs the live file's stale view text (`... WHERE to_value IS NOT NULL AND event_type != 'skipped' ...`), so a test covers the `entity_axis_state_rebuilt` true branch the live file takes, not only the live-copy run.
     - **The model:** the prototype's `register()`/`unregister()` in `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/proto/run_proto.py`. R3's export rebinds the three module attributes instead (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/proto/export/plugins/pd/hooks/lib/entity_registry/test_helpers.py`).
   - **`seed_rekey_classes(path)`** adds, by raw SQL on the old shape, one row of every class in rekey §5.1 and one event of every class in §3.3:
     - rows: matched, null-uuid, stale-uuid, archived, soft-deleted, shared, re-attached, unmappable;
     - events: sole-holder, label-decided, undecided, no-holder;
     - it seeds the entities by raw SQL too (`test_helpers.seed_legacy_entity`), on a file opened under the pre-re-key build (the same patch `make_pre_rekey_db` uses), and writes exactly one event per class. It never calls `register_entity` or `append_phase_event` (BUILD-W3);
     - it returns the uuids and ids it seeded. The model is the export's `seed_rekey_classes`, in the same file, which adds the re-attached row the prototype lacked (rekey §5.1).
2. **The migration:** `_v2_migration_8_rekey_workflow_phases(conn)`, after `_v2_migration_7_immutable_is_legacy`, exactly as Part 2 gives it: the registration, the steps (step 1b, the tripwire, included), the SQL and the audit rows. R3's export is a working model (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/proto/export/plugins/pd/hooks/lib/entity_registry/database.py`, :6383-6652).
   - **Differences from the prototype** (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/proto/rekey_migration.py`) that the design requires:
     - raise `MigrationError` (database.py:4341);
     - write audit rows through `_append_migration_audit_log` (:4353);
     - when the re-probe under the lock finds nothing, `ROLLBACK` and write no audit row (rekey §4.4 step 4);
     - refuse a surprise dependent (step 5);
     - copy the re-attached class, audit it, and count it (steps 6.2, 6.6 and 6.7);
     - assert the table's index-name set (step 6.10);
     - use Part 2.3's payload keys;
     - no test-only parameters in the production signature (PM-CODE-W3). All the migration's SQL stays inside `_v2_migration_8_rekey_workflow_phases`. Tests inject failures by patching the SQL-free seam `_rekey_fault_point(stage)`, which the function calls between its stages (the export's model: database.py:6383, called at :6652). The guard's allow-list then needs no change.
   - **The live-path tripwire** (step 1b; PM-CONS-W5): when a pending part has rows to move (old-shape `workflow_phases` or `phase_events` rows), and the connection's main file (`PRAGMA database_list`) is the account's live registry, the function raises `MigrationError` naming `scripts/rekey_live_registry.py`, before it changes anything.
     - **The live test** is one helper in `entity_registry`, which the operator tool imports (1.7): `os.path.samefile` with `$HOME/.claude/pd/entities/entities.db`, or with the same path under the account's home (`pwd.getpwuid(os.getuid()).pw_dir`).
     - **Only `PD_REKEY_APPLY=1` in the environment lifts it,** and only the tool's `apply` sets it.
     - **It is inert** on fresh files, copies and re-keyed files. On any other machine with a pre-rekey registry, pd refuses to start until the tool runs there.
3. **The row view** (rekey §6.2): one module-level SELECT beside the DDL, `SELECT wp.*, e.type_id, e.workspace_uuid FROM workflow_phases wp JOIN entities e ON e.uuid = wp.entity_uuid`.
   - **Who uses it:** every method that returns a row.
   - **Keys:** `entity_uuid` is added, `uuid` goes, and `type_id` and `workspace_uuid` are read from the entity.
4. **Row methods** (rekey §6.3):
   - `create_workflow_phase`: `INSERT (entity_uuid, <state>)`;
   - `get_workflow_phase`: `WHERE entity_uuid = ?`;
   - `update_workflow_phase`: `WHERE entity_uuid = ?`. The stored-workspace assertion (:10169-10188) goes; the four tests that pin its "workspace_uuid mismatch" error are rewritten (Existing tests; BLAST-W1);
   - `upsert_workflow_phase`: `ON CONFLICT(entity_uuid) DO UPDATE SET <given columns>`. The branch that refuses another workspace's row goes;
   - `list_workflow_phases`: an inner join on `entity_uuid`, filtering on `e.workspace_uuid`, selecting `wp.entity_uuid`. The `OR e.uuid IS NULL` clauses (:10442, :10448) go.
5. **Event methods** (rekey §6.3):
   - **`append_phase_event`** gains `entity_uuid=None`; `type_id` becomes optional when `entity_uuid` is given. It resolves the entity once:
     - it stores `entity_uuid`, with the entity's `type_id` and the passed `project_id` as labels;
     - the status UPDATE (:9772) and the step-5 projection (:9790) are keyed by the entity uuid;
     - the dual-write's unscoped fallback SELECT (:9823) goes;
     - an unknown entity raises for any `source`;
     - an `entity_uuid` with a `type_id` that is not that entity's raises.
   - **`query_phase_events`** gains `entity_uuid` and `workspace_uuid`, and follows rekey §6.3's three cases. The label columns are never filtered on again.
   - **`query_phase_events_bulk(entity_uuids, event_types=None)`:** it refuses (`ValueError`) any element that is not a uuid, so a missed caller that still passes type_ids fails loudly, instead of reading nothing and reporting drift for every entity (BLAST-S4).
   - **`PHASE_EVENTS_COLS`,** `_VALID_PARAMS` and `_REQUIRED_PARAMS` gain `entity_uuid` (schema-49).
6. **`update_entity`:** the `workflow_phases` re-attribution cascade (:8773-8788) is deleted.
7. **Docstrings:**
   - **`delete_entity`'s** (:8984-8990): it no longer claims to delete `workflow_phases` rows.
   - **v2 migration 3's** (database.py:6173-6178; rekey §4.3): its view filters only `event_type != 'skipped'`, and NULL-`to_value` rows stay visible as the designed reset (views.py:65-71).
   - **`reconcile_status`'s** (workflow_state_server.py:2546-2553 at `c1bbfae0`): "Workflow rows are keyed by type_id", which this flip makes false (PM-CONS-W2).
8. **The readers:**
   - `_check_artifact_completeness` and `get_mini_spec` read the entity's events by `entity_uuid`;
   - `_detect_phase_events_drift` calls the bulk read with entity uuids;
   - `query_phase_analytics` and `_compute_durations` scope by the entity's workspace, and pair events by `entity_uuid` (MCPW-43, fill-2).
9. **Maps keyed by `entity_uuid`** (guard rule 3): `run_backfill` (backfill.py), `check_workflow_drift` (reconciliation.py) and `WorkflowStateEngine.list_by_status` (engine.py).
10. **`rebuild_tool`** (rekey §14):
    - its copy lists and `_preimport_vocab_diff` follow the new shape;
    - it refuses a source whose `workflow_phases` has no `entity_uuid`, with this message (PM-LIVE-W5): "this file is not re-keyed. Make a copy with the prescribed backup command and migrate the copy, or use scripts/rekey_live_registry.py. Never open the source itself." Opening the source with `EntityDatabase` would migrate it with no backup, or turn the only pre-rekey backup into version 8;
    - its re-mint maps both tables' `entity_uuid` through its old-to-new uuid map, and an unattributed event keeps its NULL;
    - the existing full `PRAGMA foreign_key_check` (rebuild_tool.py:1389) now covers `phase_events` (section 0.2, item 8).
11. **The doctor** (rekey §14):
    - `check_referential_integrity`'s `workflow_phases` part reports the rows `PRAGMA foreign_key_check(workflow_phases)` and `(phase_events)` return, and offers no fix;
    - `_fix_remove_orphan_workflow` is deleted, with its dispatch entry;
    - `_fix_self_referential_parent` writes by uuid;
    - `check_status_write_path`'s permitted list drops `delete_workflow_phase`.
12. **`pd_state_diff.py`** (SCR-1, SCR-2) joins and replays by `entity_uuid`. It stays read-only and fails soft.
13. **Deletions:**
    - the C22 script and its test, and `fix_kanban_columns.py` and its test (rekey §14);
    - the orphan-tolerance code, including C8's orphan branch if first check 1 found it;
    - 1C's skip (change 15).
14. **`TestMigration6`'s three row assertions** (`scripts/test_migrate_db.py`; BUILD-W2), rewritten to the new key: orphan rows: none by `entity_uuid`; null uuids: no `entity_uuid` is NULL; the uuid backfill: every row's `entity_uuid` names an entity. The file's other tests (tests-67) stay out.
15. **1C's skip is removed** (BLAST-B2). Its own condition is "until workflow rows are keyed per entity", which this flip meets, and it must be gone before R4-F4 makes the prefix search strict: `_another_workspace_holds` calls `search_by_type_id_prefix(type_id)` with no workspace (entity_status.py:256), the second production caller besides `resolve_ref` (database.py:7245).
    - **Delete** `_another_workspace_holds` (entity_status.py:244-257), the skip branch in `_sync_brainstorm_entities` (:160-167), and the module docstring's skip paragraph (around :21: "The skip stays until workflow rows are keyed per entity (Phase R)").
    - **Keep** `_workspace_holds` (:228-241, scoped).
    - **The effect:** a brainstorm file whose type_id only another workspace holds registers in the session's workspace, as its own namesake. With no resolved workspace, the sync raises at the first file that needs registration, and the orchestrator records it (:169-170).

**Checklist:**


- `(shared fixtures, several files)`: tests-73 (no `conftest.py` creates rows). The shapes reach the tests through:
  - `EntityDatabase.__init__`, through each file's own db fixtures (the fresh v1 chain);
  - `test_helpers.py`;
  - `rebuild_tool.build_staging_database` (v2);
  - `scripts/test_migrate_db.py`'s `create_entity_db` (tests-67), which stays out; `TestMigration6`'s three row assertions, in the same file, are yours (change 14).
- `doctor/check_status_write_path.py`: engines-94 (`check_status_write_path`).
- `doctor/checks.py`: engines-91 (`check_referential_integrity`).
- `doctor/fix_actions/__init__.py`: engines-92 (`_fix_remove_orphan_workflow`); engines-93 (`_fix_self_referential_parent`).
- `doctor/test_check_status_write_path.py`: tests-4 (`test_doctor_detects_status_violations`).
- `doctor/test_checks.py`: tests-1 (`_make_db`).
- `doctor/test_fixer.py`: tests-2 (`_make_db`).
- `entity_registry/database.py`: schema-11 (`workflow_phases`); schema-19 (`phase_events`); schema-20 (`MIGRATIONS`); schema-21 (`_migrate / _migrate_v2 / _refuse_if_file_is_from_the_future`); schema-22 (`MIGRATIONS_DOWN / _migrate_down`); schema-23 (`_v2_migration_3_state_only_axis_views`); schema-26 (`append_phase_event step 2`); schema-27 (`append_phase_event step 3`); schema-28 (`append_phase_event step 5`); schema-29 (`append_phase_event step 6`); schema-30 (`query_phase_events`); schema-31 (`query_phase_events_bulk`); schema-33 (`create_workflow_phase`); schema-35 (`update_workflow_phase`); schema-37 (`upsert_workflow_phase`); schema-39 (`list_workflow_phases`); schema-40 to -41 (`update_entity`); schema-42 (`register_entity`); schema-43 (`upsert_entity`); schema-49 (`PHASE_EVENTS_COLS`); schema-68 (`migration_audit_log`).
- `entity_registry/rebuild_tool.py`: schema-76 (`_replay_v1_chain / _seed_v2_schema / _apply_v2_chain / _stam`); schema-77 (`_preimport_vocab_diff`); schema-78 (`_import_workflow_phases`); schema-79 (`_emit_all_events`); schema-80 (`_insert_event / _emit_events_for_entity`).
- `entity_registry/schema_v2.py`: schema-74 (`_CORE_DDL / DDL_REGISTRY / bootstrap_v2`).
- `entity_registry/test_axes.py`: schema-102 (`test_axes.py`).
- `entity_registry/test_backfill.py`: tests-25 (`db fixture`).
- `entity_registry/test_backfill_parent_uuid.py`: tests-26 (`TestParentUuidPreference`).
- `entity_registry/test_board_archived_query.py`: tests-14 (`helpers _add_feature`).
- `entity_registry/test_c22a_reparent_entity.py`: schema-106 (`test_c22a_reparent_entity.py`).
- `entity_registry/test_c5b_alias_free_callers.py`: tests-15 (`_created_label`).
- `entity_registry/test_c5b_step2_aliases_removed.py`: tests-16 (`_registry_state`).
- `entity_registry/test_database.py`: tests-6 (`fixtures db`).
- `entity_registry/test_display.py`: schema-105 (`test_display.py`).
- `entity_registry/test_entity_display_table.py`: tests-24 (`_dump_table_for_uuid`).
- `entity_registry/test_event_sourced_state.py`: tests-9 (`_bootstrap_v12_workspace`).
- `entity_registry/test_events.py`: schema-103 (`test_events.py`).
- `entity_registry/test_helpers.py`: tests-5 (`make_v10_db`).
- `entity_registry/test_migration_13_safety.py`: tests-20 (`_seed_round_trip_fixture`).
- `entity_registry/test_migration_14_safety.py`: tests-21 (`module-level migration-14 tests`). Its `_make_v14_db` (:57) builds at `max(MIGRATIONS)`, so after the re-key `_migration_14_down` replays `idx_pe_entity`, and `test_ac_mr_7` (:251) fails with "no such column: entity_uuid" (BUILD-S6; Existing tests).
- `entity_registry/test_migration_19_safety.py`: tests-22 (`_seed_phase_event`).
- `entity_registry/test_migration_safety.py`: tests-19 (`module-level migration-12 tests`).
- `entity_registry/test_pd_state_diff.py`: tests-18 (`_insert_phase_event`).
- `entity_registry/test_phase_events.py`: tests-7 (`fixtures seeded_db`).
- `entity_registry/test_phase_events_adversarial.py`: tests-8 (`helper _reset_to_pre_migration_10`).
- `entity_registry/test_rebuild_tool.py`: tests-27 (`_seed_workflow_phase`).
- `entity_registry/test_register_upsert_split.py`: tests-10 (`module-level tests`).
- `entity_registry/test_search.py`: tests-13 (`_make_v3_db-style builder`).
- `entity_registry/test_status_only_lifecycle.py`: tests-11 (`module-level tests`).
- `entity_registry/test_v2_migrations.py`: tests-23 (`_make_v2_version1_file`).
- `entity_registry/test_views.py`: schema-104 (`test_views.py`).
- `plugins/pd/mcp/test_c5b_c17_allocate_register.py`: tests-58 (`_created_label`).
- `plugins/pd/mcp/workflow_state_server.py`: MCPW-22 (`_check_artifact_completeness`); MCPW-24 (`get_mini_spec`); MCPW-30 (`_detect_phase_events_drift`); MCPW-43 (`query_phase_analytics`); fill-2 (`_compute_durations`).
- `plugins/pd/scripts/pd_state_diff.py`: SCR-1 (`_fetch_current_state`); SCR-2 (`_phase_events_for`).
- `plugins/pd/scripts/tests/test_c5b_parse_backlog_workspace.py`: tests-59 (`module-level`).
- `plugins/pd/ui/tests/test_app.py`: tests-60 (`helpers _seed_workflow_row`).
- `plugins/pd/ui/tests/test_board_archived.py`: tests-61 (`helpers _add`).
- `plugins/pd/ui/tests/test_c8_card_kind.py`: tests-62 (`helper _insert_workflow_row`).
- `plugins/pd/ui/tests/test_deepened_app.py`: tests-63 (`helpers _seed_workflow_row`).
- `plugins/pd/ui/tests/test_entities.py`: tests-64 (`fixture integration_client`).
- `reconciliation_orchestrator/test_c5b_brainstorm_workspace.py`: tests-48 (`_created_label`); its skip-dependent tests follow change 15 (Existing tests).
- `scripts/c22_recreate_live_remainder.py`: SCR-9 (`_ensure_backlog_workflow`); SCR-10 (`verification`).
- `scripts/fix_kanban_columns.py`: SCR-5 (`_UPDATE_SQL / fix_kanban_columns`); SCR-6 (`_PREVIEW_SQL / _dry_run`).
- `scripts/test_c22_recreate_live_remainder.py`: tests-65 (`helpers summarize`).
- `scripts/test_fix_kanban_columns.py`: tests-66 (`helpers _make_db`).
- `workflow_engine/test_c11_engine_dir_name.py`: tests-39 (`helper _insert_orphan_workflow_row`).
- `workflow_engine/test_c11_reconciliation_dir_name.py`: tests-38 (`helper _insert_orphan_workflow_row`).
- `workflow_engine/test_c5b_workspace_callers.py`: tests-46 (`_created_label`).
- `workflow_engine/test_c8_kind_from_column.py`: tests-40 (`helpers _insert_orphan_workflow_row`).

- **Rows R4-F1 to R4-F3 own whose raw SQL breaks here:** R4-C0 moved their raw SQL behind its helpers. What it left out (1.4a, "Out"), you rewrite ahead of their owner:
  - `test_entity_lifecycle.py` (tests-12);
  - `test_reconciliation.py` (tests-37);
  - `test_complete_phase_closes.py` (tests-53);
  - `test_issue_spawn.py` (tests-54);
  - `test_workflow_state_server.py` (tests-51).
- **Test files with no inventory row:**
  - 1A's (added after the inventory's commit): `test_workflow_phase_writers.py`, `test_backfill_scoped.py`, `test_create_feature_lanes.py`, `test_projection_names_directory.py`;
  - 1C's `test_brainstorm_registration_scoped.py` (change 15), and 1B's four files, whose assertions stay (1.13);
  - any file the Phase 1 drift check adds.
- **The tests' raw SQL on the two tables:** R4-C0 moved it behind shape-aware helpers (1.4a, with the per-file list measured at `4a6373f0`). Your part:
  - **check that the helpers write the new shape** (`entity_uuid`) once the flip has run, and fix them if not;
  - **the statements R4-C0 left out** (1.4a, "Out"): tests that stop the chain before 26 or 8 keep their SQL; the head-schema pins are restated below; orphan rows are deleted, or their entity is registered; 1A's and 1C's row-key assertions are restated below;
  - **a raw `phase_events` INSERT left out** with `source='live'` and no `entity_uuid` now aborts (`pe_reject_live_event_without_entity`), unless the file stops the chain before version 26 or 8. Give it an `entity_uuid`, or `source='backfill'` where the test is about backfill.

**Red-first tests (new).** Each is red on your base for the reason given. The three criterion-2 tests marked keep-green are the exception (rekey §10).
1. **`plugins/pd/hooks/lib/entity_registry/test_rekey_schema.py`** (rekey §10: criteria 1 and 3). Red on base: the old shape.
   - **`test_primary_key_is_entity_uuid`:** the primary key is `entity_uuid` alone, with a foreign key to `entities(uuid)`.
   - **`test_no_identity_copy_columns`:** no `type_id`, `workspace_uuid` or `uuid` column.
   - **`test_insert_for_unknown_entity_is_refused`:** refused by `wp_reject_unknown_entity`, with `PRAGMA foreign_keys` on and off. This is W3.1's orphan-scope test, restated (rekey §7).
   - **`test_row_cannot_move_to_another_entity`:** an UPDATE of `entity_uuid` aborts.
   - **`test_hard_delete_of_entity_with_row_fails`:** refused on a foreign-keys-on connection.
   - **`test_live_event_without_entity_is_refused`.**
   - **`test_event_entity_is_set_once`:** NULL → value is allowed; value → another value aborts.
   - **`test_no_index_leads_with_type_id_or_project_id`.**
   - **`test_backfill_dedup_is_per_entity`** (playbook addition): two namesakes' backfill events with the same phase, type and timestamp both insert. On the base they collide on the type_id form of the index.
2. **`plugins/pd/hooks/lib/entity_registry/test_rekey_migration.py`** (rekey §10: criteria 5 and 6), on `make_pre_rekey_db` files.
   - **Non-vacuous by construction** (PM-CODE-W5): every test first asserts a fact only the migration makes true (version 26 on a v1 file or 8 on a v2 file, `entity_uuid` as the primary key, the `success` audit row), and only then that nothing else changed. Red on base: that first assertion, since the base has no migration and the file stays at 25 or 7.
   - **The fault-injection tests** patch `_rekey_fault_point` (change 2). On the base, where the seam does not exist, their red is structural (`AttributeError`): record it as such.
   - **`test_fresh_and_staging_shapes_identical`:** a fresh v1 file and a staging v2 file have identical `sqlite_master` text for both tables, and Part 2.6's 12 object names. Their CHECK lists carry the live DDL's allowed values, compared as sets (BUILD-S7). Both files reach the step through the v1 chain, so each `success` row records `migration_version` 26, and a fresh file's row carries every count 0 (BUILD-S2).
   - **`test_pre_rekey_v1_and_v2_files_reach_the_same_target`:** they reach versions 26 and 8, with the same text.
   - **`test_migrates_every_row_class`:** the class fixture ends as rekey §5.1 says: matched, re-attached and unmappable partition the rows, and state is preserved exactly.
   - **`test_audits_reattached_dropped_and_stale_rows`:** one audit row per seeded case, with Part 2.3's payloads.
   - **`test_event_classes_follow_the_attribution_rules`** (playbook addition): rekey §3.3's four classes, and no event is attributed to an entity with another type_id. Two more cases (PM-LIVE-W8): a label that is a holder's workspace uuid decides (1B writes one for a workspace with no legacy id, dependencies.py:193); an `'__unknown__'` label stays undecided, even when the unknown workspace holds the type_id.
   - **`test_success_audit_payload_names_the_migration_and_counts`** (playbook addition): exactly one `success` row; `migration_version` is the chain generation when the migration ran: 8 when `_metadata.schema_generation` was `v2`, 26 otherwise (BUILD-S2); Part 2.3's keys.
   - **`test_rolls_back_on_injected_failure`:** tables and schema unchanged, `foreign_keys` restored.
   - **`test_resumes_after_kill_inside_the_transaction`:** a subprocess `os._exit`s after the copy. Tables and schema are unchanged, and the next open migrates.
   - **`test_resumes_after_crash_before_stamp`:** the next open changes only `_metadata`.
   - **`test_reopen_is_a_no_op`:** after the first open's version and `success` row, a second open leaves the per-table fingerprints unchanged and writes no new audit row.
   - **`test_peer_finished_first_writes_nothing`** (playbook addition; rekey §4.4 step 4): pending before the lock, nothing pending under it. The migration rolls back, writes no audit row, and restores `foreign_keys`. It stays the in-process case (PM-CODE-S1).
   - **`test_two_runners_on_a_pre_rekey_v2_file_migrate_once`** (R3; BLAST-B1): on `make_pre_rekey_db(path, "v2")`, two forked runners, then a third open. Version 8, exactly one `success` audit row, and the third open succeeds. Red on base: the base has no migration.
   - **`test_live_path_refuses_without_the_operator_flag[refuses|flag-set-migrates|copy-migrates|fresh-file-migrates]`** (R3; PM-CONS-W5), with a temp HOME holding a pre-rekey file at `.claude/pd/entities/entities.db`: opening that path raises `MigrationError` naming `scripts/rekey_live_registry.py`, and the file stays byte-identical; with `PD_REKEY_APPLY=1`, it migrates; a copy elsewhere, and a fresh file, migrate. Red on base: the base has no migration.
   - **`test_refuses_a_surprise_dependent`** (playbook addition; step 5).
   - **`test_foreign_keys_restored`:** with the recorded value on, and off.
   - **`test_axis_view_recreated_from_views_ddl`** (playbook addition; rekey §4.3): a v2 file built with `make_pre_rekey_db(path, "v2", stale_axis_view=True)` (the live file's stale `to_value IS NOT NULL` text) ends with `_VIEWS_DDL`'s text, its `success` row records `entity_axis_state_rebuilt` true, and `entity_state` is untouched (BUILD-S4).
   - **`test_rows_join_entity_phase_status_one_to_one`:** on a seeded staging file, every row joins `entity_phase_status` on `entity_uuid`, at most once.
3. **`plugins/pd/hooks/lib/entity_registry/test_rekey_identity.py`** (rekey §10: criteria 1, 2 and 3; §7 W3.1 and W3.3):
   - **`test_two_namesakes_two_rows_and_no_cross_write`:** both workspaces create a row for `feature:X`, and an update through A leaves B's row byte-identical. Red: the second insert fails on the type_id key.
   - **`test_upsert_writes_own_row_leaves_namesake_unchanged`:** red, because W2.1 refuses.
   - **`test_row_and_events_survive_type_id_rename`** (rekey §9, open question 4):
     - *the setup:* a raw-SQL rename of `entities.type_id` (no trigger forbids it).
     - *asserts:* the row and the events are found by the new type_id and the workspace; the old type_id is not found; and no `workflow_phases` write happened.
     - *red:* the row is keyed by the old type_id.
   - **`test_row_survives_reattribution[update_entity|backfill_project_ids|claim_unknown_entities]`** (PM-CONS-S6):
     - *the setup:* the entity is re-attributed through `update_entity(new_project_id)`, `backfill_project_ids` (database.py:8818) or `claim_unknown_entities` (:9130). The last two never touched the row; the first cascaded until change 6.
     - *asserts:* the row view's workspace is the new one, and the raw row is unchanged.
     - *red:* the stored workspace copy stays stale, or the cascade rewrites the row.
   - **`test_update_entity_reattribution_writes_no_workflow_row`** (W3.3's "Cascade", rekey §7): A's row is unchanged (`updated_at` included), and so is B's. Red: the cascade rewrites the row.
   - **`test_shared_type_id_rows_are_independent`:** red, because B can hold no row.
   - **Keep-green** (today's type_id key already survives these): `test_row_survives_reparent`, `test_row_survives_archive_round_trip`, `test_row_survives_soft_delete_round_trip`.
   - **`test_row_view_reads_current_identity`:** after a raw rename and a re-attribution. Red.
   - **`test_list_workflow_phases_one_row_per_entity_with_entity_uuid`** (playbook addition; W3.1's "one card"): namesakes each with a row, plus an archived namesake. The rows come back unfanned, each with `entity_uuid`, and the workspace filter uses the entity's workspace. Red: no `entity_uuid`, and the type_id join fans out.
4. **`plugins/pd/mcp/test_rekey_event_streams.py`** (rekey §10: criterion 4). **The setup** (PM-CODE-W5): A's `feature:X`, and a namesake `feature:X` in workspace B, each with its own events, so the base fails by reading the other entity's events, not by finding none.
   - **`test_mini_spec_of_a_is_invisible_to_b`:** A's `feature:X` has a `mini_spec` event and B's has none; `get_mini_spec` pinned to B answers none. Red: the event read by type_id returns A's.
   - **`test_artifact_completeness_reads_only_own_events`** (playbook addition): red.
   - **`test_phase_events_drift_is_keyed_by_entity`** (playbook addition): red.
   - **`test_phase_analytics_pairs_events_per_entity`** (playbook addition): two namesakes' `started` and `completed` events never pair across entities. Red.
   - **`test_bulk_read_refuses_type_ids`** (R3; BLAST-S4): `query_phase_events_bulk(["feature:X"])` raises `ValueError`. Red on base: the method takes type_ids.
5. **`plugins/pd/hooks/lib/workflow_engine/test_second_workspace_namesake_activates.py`** (playbook addition; the bar of rekey §1.3):
   - **`test_activate_feature_in_second_workspace_seeds_its_own_row`:**
     - *the setup:* A's `feature:X` has a row; B registers a planned `feature:X`.
     - *asserts:* `activate_feature` in B succeeds and seeds B's own row, and A's row is unchanged.
     - *red:* B's insert fails on the type_id key.
6. **`test_naming_rule.py`, extended:**
   - **the cases R4-A left out** (PM-CODE-B1): `append_phase_event.type_id` and `query_phase_events.type_id` in both parametrized tests, and `update_workflow_phase.type_id` in `test_uuid_resolves_its_entity_whatever_the_workspace` (rows and events are keyed by entity uuid here). Red: no workspace keyword, the write lands on A's entity, or there is no uuid path.
   - **`test_append_phase_event_rejects_an_entity_uuid_type_id_mismatch`:** red, because there is no `entity_uuid` parameter.
   - **`test_append_phase_event_attributes_by_workspace_not_label`:**
     - *the setup:* the label names workspace C; the workspace passed is A.
     - *asserts:* the event's `entity_uuid` is A's entity, and the label is stored as passed.
     - *red:* there is no column to attribute.
7. **`plugins/pd/hooks/lib/entity_registry/test_rebuild_rekey.py`** (playbook addition; rekey §14):
   - **`test_rebuild_maps_entity_uuid_through_the_remint`:** both tables; an unattributed event stays NULL.
   - **`test_rebuild_refuses_an_old_shape_source`:** the message names `scripts/rekey_live_registry.py`, and the source stays byte-identical (PM-LIVE-W5).
   - **`test_rebuild_foreign_key_check_catches_an_unmapped_event`.**

   Red: the old shape.
8. **`plugins/pd/hooks/lib/doctor/test_rekey_doctor.py`** (playbook addition; rekey §14):
   - **`test_referential_integrity_reports_foreign_key_violations_without_fixing`:** a row whose entity was hard-deleted with foreign keys off is reported, and no fix is offered. Red: the check keys by type_id, and the fix exists.
   - **`test_fix_self_referential_parent_writes_by_uuid`:** only A's namesake is self-referential, and the fix leaves B unchanged. Red: the base writes by type_id.
9. **In `test_pd_state_diff.py` (tests-18): `test_state_diff_joins_rows_by_entity_uuid`.** Each namesake's own row is reported. Red.

**Existing tests**
- **Rewrite:**
  - **the checklist's test rows,** and the raw SQL R4-C0 left out (1.4a, "Out"): joins on `entity_uuid`, or the API;
  - **head-schema pins** (rekey §9, open question 21), updated in place:
    - `test_database.py`: `test_type_id_is_primary_key` becomes `test_entity_uuid_is_primary_key`; `test_workflow_phases_has_8_columns`, which asserts 9, asserts 7; `test_workflow_phases_column_names` lists the 7 names; `TestTriggers.test_has_nine_triggers` (:591) becomes `test_has_ten_triggers`: it drops `enforce_immutable_wp_type_id`, `wp_autofill_workspace_uuid` and `wp_reject_orphaned_insert`, and adds `enforce_immutable_pe_entity_uuid`, `enforce_immutable_wp_entity_uuid`, `pe_reject_live_event_without_entity` and `wp_reject_unknown_entity`; `TestIndexes.test_has_indexes` (:620) drops `idx_pe_lookup`, `idx_pe_project`, `idx_wp_uuid` and `idx_wp_workspace_uuid`, and adds `idx_pe_entity`;
    - `test_phase_events.py`: `test_ac2_schema_correct` (:133) appends `entity_uuid` and asserts 14 columns; `test_ac3_indexes_exist` (:150) asserts `idx_pe_entity` and `idx_pe_timestamp`, and that `idx_pe_lookup` and `idx_pe_project` are gone;
    - `test_v2_migrations.py::test_migration_3_noop_without_events_store`: "25" becomes "26";
    - `test_v2_migrations.py::TestV2Migration2MiniSpec::test_open_migrates_v2_file_to_version_2` (:85): the head's `phase_events` index list becomes `idx_pe_entity`, `idx_pe_timestamp`, `phase_events_backfill_dedup`;
    - `test_rebuild_tool.py`'s trigger-name assertions: `wp_reject_orphaned_insert` and `wp_autofill_workspace_uuid` become `wp_reject_unknown_entity` and `enforce_immutable_wp_entity_uuid`;
    - any other index-name pin on the head chain. The figures above were checked on the prototype's migrated files (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/proto/files/fresh-v1.db` and `live-copy.db`): 10 triggers on a fresh file, `phase_events` at 14 columns with `entity_uuid` last, and its indexes `idx_pe_entity`, `idx_pe_timestamp` and `phase_events_backfill_dedup`.
    - **A test that stops the chain at version N** keeps pinning N; for example, `test_migration_19_safety.py::test_indices_survive_widening` still asserts `idx_pe_lookup` and `idx_pe_project`.
  - **1A's `test_workflow_phase_writers.py`:** the `stored["uuid"]` and `stored["workspace_uuid"]` assertions become "`entity_uuid` is A's entity uuid, and the row view's `workspace_uuid` is A" (rekey §12, the W2 tests row). The same for `test_projection_names_directory.py:245`, the SELECT in `test_create_feature_lanes.py`, and the row assertions in `test_backfill_scoped.py`.
  - **The UI tests** (tests-60 to -64): register the entity first, and insert `(entity_uuid, …)`. The UI still links by type_id until R4-D; keep it green.
  - **The tests that pin `update_workflow_phase`'s stored-workspace assertion** (BLAST-W1; change 4 deletes it): `TestEngineWorkspaceUuidForwarding`'s three tests (test_engine.py:3526-3611, matching "workspace_uuid mismatch" at :3589, :3601 and :3611) and `TestUpdateWorkflowPhaseWorkspaceUuidAssertion` (test_database.py:4160-4203). They keep their subject, the engine forwarding the workspace, and now expect the not-found error ("Workflow phase not found"), with nothing written.
  - **`test_migration_14_safety.py`'s fixture** (tests-21; BUILD-S6): build it with `make_pre_rekey_db(path, "v1")`, or stop the chain at 14. The historical down migration is unchanged.
  - **`TestMigration6`'s three row assertions** (change 14).
  - **1C's skip tests** (BLAST-B2), red on your base, where the skip still runs:
    - `test_brainstorm_registration_scoped.py:327` `test_a_type_id_only_another_workspace_holds_is_skipped_and_named[none|archived|soft_deleted]` becomes `test_a_type_id_only_another_workspace_holds_registers_here[...]`: a new entity in the session's workspace; the other workspace's entity and row unchanged; no warning names it;
    - `:419` `test_a_second_session_start_after_the_skip_changes_nothing` becomes `test_a_second_session_start_after_the_registration_changes_nothing`;
    - `:443`'s parameter `[skipped-held-by-B]` becomes `[registered-beside-B]`;
    - the blast's 7 strict-rule failures in `test_c5b_brainstorm_workspace.py` (3), `test_entity_status.py` (3) and `test_orchestrator.py` (1) reach the skip's unscoped prefix search. They are expected green once the skip goes; any that pins the skip is rewritten the same way.
- **Delete,** each with its change:
  - **`test_workflow_phase_writers.py::test_upsert_from_a_refuses_bs_row_and_leaves_it_unchanged`:** rekey §6.3 and §12 delete upsert's other-workspace refusal, and `test_upsert_writes_own_row_leaves_namesake_unchanged` replaces it;
  - **orphan-tolerance cases** (rekey §4.2, §7; open question 14): the `_insert_orphan_workflow_row` cases of `test_c11_reconciliation_dir_name.py`, `test_c11_engine_dir_name.py` and `test_c8_kind_from_column.py`; the `_add_orphan_row` cases of `test_board_archived_query.py` and `ui/tests/test_board_archived.py`; and the orphan cases of `test_workflow_state_server.py` and `test_reconciliation.py`, wherever the orphan is the test's subject. Where an orphan row was only setup (a card to render), register its entity instead;
  - **the `_fix_remove_orphan_workflow` tests** in `test_fixer.py` (rekey §14);
  - **`scripts/test_c22_recreate_live_remainder.py` and `scripts/test_fix_kanban_columns.py`,** with their scripts (rekey §14);
  - **C8's orphan-branch tests,** if first check 1 found the branch.
- **Re-run, and edit only if they break:** the events tests (schema-102 to -106).

**Gates**
- **G1:** the new files, the rewrites and the deleted cases. Your report lists each deleted test with its change.
  - **Changed without an edit** (BLAST-S1): the 16 `test_c19_c20b_rebuild_structure.py` tests (an R4-F1 row, tests-28) are red between the flip and change 10 (rebuild_tool.py:337, "no such column: wp.type_id", in `_preimport_vocab_diff`), and green at your head.
  - **4C's race tests run with migration 26 registered** (BLAST-B1; PM-CODE-S1): the fresh-file race, the old-file race from v10, and `test_migration_11_concurrent_runners` 50 consecutive runs, all green, and `test_two_runners_on_a_pre_rekey_v2_file_migrate_once`.
  - **No re-run allowance:** no test in any gate is re-run to pass.
- **G2:** unchanged, unless a `plugins/pd/scripts/tests` file reads a changed column.
- **G5:** shrinks by the deleted scripts' tests: measure it (32 tests in `test_c22_recreate_live_remainder.py` at `ddc299a0`, plus `test_fix_kanban_columns.py`'s; the inventory at `77f06efb` counted 34 and 7 test functions). Its base keeps `TestMigration6`'s 7 failing tests, and the three row assertions you rewrite (change 14) pass (BUILD-W2).
- **G3, G4:** expected unchanged. Run both.

**QA probes**
1. **Migrate a same-minute copy of the live file** (the prescribed copy command, then `EntityDatabase(copy).close()` from the worktree root, with a temp HOME), and run Part 2.6's queries. Every expected value must match, or the figure the backup gives if the live file has changed since 2026-09-26 (Part 2.5).
2. **Re-open the migrated copy:** per-table fingerprints unchanged, and no new audit row.
3. **Build a fresh v1 file and a staging v2 file:** the two tables' `sqlite_master` text equals the migrated copy's, and the views equal the staging file's.
4. **Open a copy of the migrated file with your base's code** (a `git archive` of your base):
   - writes are denied (C23: "not authorized");
   - `get_workflow_phase` fails loudly ("no such column: type_id");
   - per-table fingerprints are unchanged.
5. **Against the migrated copy, with a temp HOME and `ENTITY_DB_PATH` set to the copy:** the doctor with `--fix`, `pd_state_diff.py`, and the session-start orchestrator as `session-start.sh` runs it. Each exits 0 with no traceback.
6. **Grep the scan roots** for `["uuid"]`, `.get("uuid")` and template `.uuid` reads on row-view results (rekey §6.2): none.
7. **Preview the guard** (BUILD-S5): copy the design's probe into your QA directory and run the copy there, so the design's evidence file beside the original is not overwritten: `cp /Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/guard/guard_probe.py <qa-dir>/ && <PY> <qa-dir>/guard_probe.py <worktree>`. No statement keys either table by type_id alone outside the migration function, except the R4-D and R4-F4 sites it lists.
8. **The skip's removal** (PM-CODE-W9): the record-only census (1.8.0's method) over G1 shows 0 would-be refusals from `entity_status.py`.
9. **The tripwire:** in a temp HOME holding a pre-rekey copy at `.claude/pd/entities/entities.db`, `EntityDatabase(<that path>)` raises `MigrationError` naming the tool, and the copy's sha256 is unchanged. With `PD_REKEY_APPLY=1`, it migrates.
10. **The race, with migration 26 registered** (BLAST-B1): 4C's race probe, or `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/blast/work/race_probe.py`, on a v10 file and on a pre-rekey v2 file: 0 bricked files in at least 20 rounds of each.

**Reviewer focus**
- **The migration matches Part 2 line by line:** the DDL text, the steps' order, no `executescript`, a table-scoped `foreign_key_check`, and the audit payloads.
- **Every deleted test cites its change,** and no orphan case was deleted where the orphan was only setup.
- **Re-run the two `uuid` greps** on the landed code (rekey §6.2).
- **4C's contract holds,** if you carried it: serialized, monotonic, and its tests red on the base.
- **The tripwire** fires only on the live path, with rows to move, before any change.

### 1.6 R4-D: the UI keyed by entity uuid (RK3; W3.1–W3.3 restated)

- **Implements:** rekey §7 (W3.1, the board, as it reaches the routes; W3.2, links by uuid), §8 (the UI row) and §15 RK3.
- **Depends on:** R4-C.
- **Can run beside:** R4-E, R4-F1, R4-F2 and R4-F3.
- **Files:**
  - `plugins/pd/ui/routes/entities.py`, `plugins/pd/ui/routes/board.py`, `plugins/pd/ui/routes/helpers.py`;
  - `plugins/pd/ui/mermaid.py`;
  - `plugins/pd/ui/templates/_card.html`, `_entities_content.html`, `entity_detail.html`;
  - `plugins/pd/ui/tests/*`.

**Brief**

**Goal.** Every UI link, lookup and graph node names an entity by its uuid. A type_id in a URL resolves only in the workspace an explicit uuid cookie selects. This task also owns every edit under `plugins/pd/ui` that the strict rule will need: 3 production and 24 test calls (rekey §15, `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/calvin/churn_ui_only.out`).

**Read first:** rekey §7 (W3.2 and W3's restated tests), §8 (the UI row) and §15 RK3.

**First check:** re-count the UI's production and test calls that name an entity by type_id with no workspace. Use the design's `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/calvin/churn_ui_only.py` on your worktree; record the list.

**Changes**
1. **Templates link by uuid:**
   - `_card.html:1` → `/entities/{{ item.entity_uuid }}`;
   - `_entities_content.html:73` → `/entities/{{ entity.uuid }}`;
   - `entity_detail.html:83` and `:98` → `{{ a.uuid }}` and `{{ c.uuid }}`.
2. **The detail route** (`ui/routes/entities.py:160-205`):
   - **The three cookie states** (PM-CODE-W7; ui/routes/helpers.py:51-65): no cookie → the startup workspace (`app.state.workspace_uuid`; all workspaces if it did not resolve); the `'*'` cookie → all workspaces; a uuid cookie → that workspace.
   - **The identifier:** a uuid resolves globally. A type_id resolves only in the workspace an explicit uuid cookie selects. With no cookie, or the `'*'` cookie, it answers the 404 page: every rendered link is a uuid, and the startup workspace is hidden state.
   - **The route decides that 404 by its own cookie check,** before any library call. It never answers it by swallowing a library refusal (R4-F4; PM-CODE-W1).
   - **Lineage:** `get_lineage(entity["uuid"], …)`, and `_strip_self_from_lineage` compares uuids.
   - **The workflow row:** `get_workflow_phase(entity["uuid"])`, one keyed read in place of the scan-and-match by type_id (:193-194).
3. **The Entities page:** `_build_workflow_lookup` (:23-28) keys on `wp["entity_uuid"]`, and the page looks up `e["uuid"]` (:103-106).
4. **The mermaid graph** (`ui/mermaid.py:38-85`): nodes are keyed and clicked by `uuid`, edges come from `parent_uuid`, and styles come from `kind`.
5. **The board** (`ui/routes/board.py:72-75`) reads R4-C's inner join. Confirm that it filters by `effective_workspace_uuid(request)` and has no orphan branch left.
6. **Scope the UI calls** from the first check: pass the workspace the request holds, or the uuid.

**Checklist:**


- `plugins/pd/ui/mermaid.py`: UI-10 (`build_mermaid_dag`).
- `plugins/pd/ui/routes/board.py`: UI-1 (`board`).
- `plugins/pd/ui/routes/entities.py`: UI-4 (`_build_workflow_lookup / entity_list`); UI-6 to -8 (`entity_detail`).
- `plugins/pd/ui/routes/helpers.py`: UI-2 (`effective_workspace_uuid`).
- `plugins/pd/ui/templates/_card.html`: UI-3 (`board card link`).
- `plugins/pd/ui/templates/_entities_content.html`: UI-5 (`entity list link`).
- `plugins/pd/ui/templates/entity_detail.html`: UI-9 (`ancestor and child links`).


**Red-first tests (new):** `plugins/pd/ui/tests/test_ui_keyed_by_entity_uuid.py`. The setup is two workspaces holding `feature:X`, each namesake with its own row and a different phase, plus a parent/child pair.
- **`test_card_link_uses_entity_uuid_and_answers_the_owner`:**
  - *asserts:* every card's href is `/entities/<uuid>`, and following it answers 200 with that card's own entity.
  - *red on base:* the hrefs are type_ids.
- **`test_board_shows_one_card_per_row_for_shared_type_id`:** keep-green. R4-C's inner join already makes it structural (rekey §7: "One card: unchanged").
- **`test_entities_page_shows_each_namesakes_own_status`:** red, because the lookup is keyed by type_id.
- **`test_detail_lineage_for_shared_type_id_is_not_empty`:** red, because `get_lineage(type_id)` answers `[]` for a shared type_id (rekey §9, open question 19).
- **`test_mermaid_draws_an_edge_per_parent`:** red, because lineage rows carry no `parent_type_id`.
- **`test_type_id_url_answers_404_without_a_selected_workspace[no-cookie|star-cookie]`** (PM-CODE-W7), with the file's shared-type_id fixture plus a type_id one workspace holds:
  - *asserts:* in both states, both type_ids answer the 404 page;
  - *red on base:* the type_id one workspace holds answers 200 with that workspace's entity, in either state. The shared type_id already answers 404 on the base, since the unscoped read answers None.
- **`test_type_id_url_resolves_in_the_cookie_workspace[uuid-cookie]`:** the shared type_id, with B's uuid cookie, answers B's entity. Red: a shared type_id answers None on the base, so the page is a 404.
- **`test_detail_workflow_is_the_entitys_own_row`:** red, because the scan-and-match by type_id can pick the namesake's row.

**Existing tests**
- **Rewrite:** tests that pin type_id hrefs, the type_id-keyed lookup, or mermaid nodes keyed by type_id; and the 24 test calls from the first check.
- **Delete:** any test pinning rev 2.1's "an orphan card keeps its type_id link". rekey §7 deletes that clause: pd can no longer create an orphan row.
- **Already done by R4-C:** the raw INSERTs of tests-60 to -64.

**Gates**
- **G1:** its `ui/tests` part changes, as above.
- **G2–G5:** unchanged.

**QA probes**
1. **Build `create_app(db_path=<a migrated live copy>)` from pedantic-drip's checkout,** so the startup workspace is pedantic-drip, and query it through a test client, with a temp HOME. The expected figures are measured in rekey §7, on today's data:
   - no cookie (the startup workspace): 240 cards, 397 with archived included;
   - the `'*'` cookie (all workspaces, archived hidden): 366 cards;
   - every card href is `/entities/<uuid>`, and each answers 200.
2. **`/entities/feature:002-assessed-mode-pipeline-fix`:**
   - with no cookie, and with the `'*'` cookie, it answers 404;
   - with pedantic-drip's uuid cookie, it answers pedantic-drip's entity at `finish`.
3. **The detail page of a feature with a parent** shows its lineage and a mermaid edge to the parent.

**Reviewer focus**
- **No template or route** builds an entity link from a type_id.
- **No route resolves a type_id** outside the workspace an explicit uuid cookie selects.

### 1.7 R4-E: the live-migration operator tool (new; section 0.2, item 2)

- **Implements:**
  - the tool Part 3 runs, for rekey §13.3 (the live migration), §13.4 (rollback) and §13.5 (the rehearsal);
  - the `sync-cache.sh` guard against publishing a build older than the live file (PM-LIVE-W4);
  - if Q4 = delete, the deletion of `migrate_db.py merge-entities` (PM-CONS-W7).
- **Depends on:** R4-C, for the migration, its tripwire and `make_pre_rekey_db`.
- **Can run beside:** R4-D, R4-F1, R4-F2 and R4-F3.
- **Must merge before:** R4-G is cut.
- **Waits for:** Q4, for the deletion only.
- **Files:**
  - `scripts/rekey_live_registry.py` (new) and `scripts/test_rekey_live_registry.py` (new; G5 collects it);
  - `plugins/pd/hooks/sync-cache.sh`: the guard, in one hunk. Task 3A also edits this file: keep separate hunks;
  - `plugins/pd/hooks/tests/test-hooks.sh`: the guard's test (G4 runs it);
  - **only if Q4 = delete:** `scripts/migrate_db.py` (`cmd_merge_entities` at :199, and its subparser at :618-627), `scripts/migrate.sh` (the import's merge step, about :391-402), `scripts/test_migrate_db.py` (`TestMergeEntities`, :325-573) and `scripts/test_migrate_deepened.py` (its merge tests).
- **Inventory rows:** none, unless Q4 = delete: then SCR-7 (`cmd_merge_entities`).
  - **The closest rows:** SCR-8 (`migrate_db.py`'s `cmd_manifest` and `cmd_migrate`), whose `cmd_migrate` this tool replaces for the live file.
  - **Why `migrate_db.py migrate` stays unchanged:** it is out of scope (rekey §14).
- **The working reference:** R3's export of this tool (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/proto/export/scripts/rekey_live_registry.py`, its tests beside it) and the core build's report (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/proto/build-report.md`, sections 4 and 5). The contract below pins what the export left open (BUILD-S8), and adds R3's findings.
- **Its fate after the sitting** is Q7 (section 0.4): deleted in F2's commit (recommended), or kept, with its reason recorded in rekey §14 (PM-CONS-S4).

**Brief**

**Goal.** One command-line tool whose subcommands are the operator manual's steps. The sitting (Part 3) and R3's rehearsal then run the same commands on different paths.

**Read first:** rekey §13 and this playbook's Part 2 (the SQL and the expected figures) and Part 3 (how the tool is used).

**The contract**
- **Invocation:** `python scripts/rekey_live_registry.py <subcommand> --db PATH [options]`, from the repository root, with the interpreter of plan:57.
  - **`--db` has no default.** A path is always named, and Part 3 gives every path absolute.
  - **The build it uses:** it imports `entity_registry` from `<the repository the script lives in>/plugins/pd/hooks/lib`, as `migrate_db.py` does.
- **Output:** one JSON object on stdout: `{"ok", "subcommand", "db", "checks": [{"name", "ok", "value", "expected", "required"}], "fingerprint_before", "fingerprint_after", ...}`.
  - **A fingerprint** (REH-S1) is `{"stat": "<mtime> <size>", "sha256_16", "wal", "shm", "schema_generation", "schema_version", "tables": {name: [rows, sha256_12]}}`. The generation and the version are read from `_metadata` in the same read-only connection.
  - **Per-table fingerprints** (PM-LIVE-W2) cover every table whose name is `NOT LIKE 'sqlite_%'`, FTS shadow tables included. `sqlite_sequence` is checked on its own (`verify`).
  - **Exit codes** (BUILD-S8): 0 when every required check passes; 1 when one fails, and the JSON names the failed check; 2 on a usage error.
- **Read-only opens** (PM-LIVE-S7): every check opens its own read-only connection (`file:PATH?immutable=1` when no `PATH-wal` exists, otherwise `file:PATH?mode=ro`; rekey §13.3 step 4) and closes it. No connection spans `apply` or `restore`. The tool never opens a path read-write except where a subcommand below says so.
- **The live-path test** (PM-LIVE-W1): PATH is live when `os.path.samefile(PATH, X)` for X in {`$HOME/.claude/pd/entities/entities.db`, `<pwd.getpwuid(os.getuid()).pw_dir>/.claude/pd/entities/entities.db`}. It is one helper, shared with R4-C's tripwire (1.5, change 2).
  - **For a live PATH:** `apply`, `restore` and `checkpoint` need `--confirm-live`, and preflight's P3 and P4 are required.
  - **The guard (check G0):** without `--confirm-live`, those three refuse a live PATH before opening anything.
  - **The swap guards** (REH-W1): `apply` and `restore` also refuse when `--backup` is a live path (either form), or when `--db` and `--backup` are the same file (`os.path.samefile`).
- **The one lift of the tripwire** (PM-CONS-W5): `apply` sets `PD_REKEY_APPLY=1` for its one `EntityDatabase` open, and nothing else sets it.
- **Backup-API connections** (REH-S9): `backup` and `restore` close both of their connections in a `finally` block.
- **The guard test:** the tool must pass R4-G's guard with no declared entry.
  - **Its SQL:** every `type_id` predicate carries a workspace predicate.
  - **Its event classification is Python:** it reads raw rows (`SELECT id, type_id, project_id FROM phase_events`, and the entities with their workspaces' legacy ids and uuids) and applies rekey §3.3's rules itself. The label-decided rule (PM-LIVE-W8): the label equals a holder's workspace's `project_id_legacy` or its uuid, and is not `'__unknown__'`.
  - **Why Python is the right choice here:** it is an implementation independent of the migration's UPDATE statements, so a fault in those predicates cannot hide in a verifier that shares them.
  - **2.5's and 2.6's SQL stays out of the tool,** since its type_id-only predicates would trip the guard. Its runnable form is the rehearsal's two scripts (Part 3; REH-S10).

**Subcommands**
1. **`fingerprint --db PATH`:** prints PATH's fingerprint, with its `schema_generation` and `schema_version`.
2. **`preflight --db PATH [--settings FILE] [--expect-generation v2] [--expect-version 7]`:**
   - P1: PATH exists, and no `PATH-wal` exists. A `-shm` is reported.
   - P2: `lsof PATH` (and `PATH-wal` or `PATH-shm` if present) prints nothing.
   - P3: no process whose command line matches `entity_server\.py|workflow_state_server\.py|ui/__main__\.py|run-(entity|workflow|ui)-server\.sh|reconciliation_orchestrator|pd_state_diff\.py`. The source is `ps -axww -o pid=,command=`, excluding the tool's own process.
   - P4 (PM-LIVE-S2): no settings file that applies enables pd: `enabledPlugins["pd@pedantic-drip-marketplace"]` is not `true` in any of
     - `.claude/settings.json` and `.claude/settings.local.json` under the home whose live path matched (the account's home for the live file, otherwise `$HOME`); `--settings` overrides the user-level `settings.json`;
     - every workspace root's `.claude/settings.json` and `.claude/settings.local.json`, the roots read from the registry's `workspaces` table (read-only).
   - P5: `_metadata.schema_generation` and `schema_version` equal the expected values (v2 and 7 for the live file).
   - P6: the old shape. `workflow_phases` has `type_id` and no `entity_uuid`; `phase_events` has no `entity_uuid`.
   - P7: no `migration_audit_log` row whose payload names `rekey_workflow_phases`.
   - P8: `PRAGMA integrity_check` is `ok`.
   - P9: no surprise dependent (Part 2.2, step 5's query).
   - **It also reports:** row counts for `entities`, `workspaces`, `workflow_phases`, `phase_events`, `events` and `migration_audit_log`, and the fingerprint.
   - **Where P3 and P4 apply:** they are required only when PATH is live (either form of the live-path test). For any other path, such as a rehearsal copy while the user has pd enabled, they are reported and not required. P1, P2 and P5–P9 are required for every path.
   - **For tests:** P2–P4's sources (the `lsof` runner, the `ps` runner, the settings paths and the account's home) are injectable.
3. **`backup --db PATH --dest DEST`:**
   - **B0 refuses** when DEST, `DEST-wal` or `DEST-shm` exists, or when `PATH-wal` exists.
   - **Then it runs exactly the prescribed copy command's code** with PATH, closing both connections in a `finally`:
     ```python
     s = sqlite3.connect(f"file:{PATH}?immutable=1", uri=True)
     try:
         d = sqlite3.connect(DEST)
         try:
             s.backup(d)
         finally:
             d.close()
     finally:
         s.close()
     ```
   - **Checks:**
     - B1: DEST's `integrity_check` is `ok`;
     - B2: DEST's per-table fingerprints and `sqlite_sequence` equal PATH's;
     - B3: DEST's full `sqlite_master` text equals PATH's;
     - B4: DEST is page-identical to PATH outside header bytes 24-27, 40-43 and 92-95 (section 0.2, item 7);
     - B5: PATH's fingerprint is unchanged.
4. **`expect --backup BACKUP --out FILE`:** computes, on the backup (old shape, read-only), every expected figure of Part 2.5, and writes them to FILE as JSON.
   - **FILE holds no file path** (REH-W4): paths go to stdout only, so two backups of one file give byte-identical FILEs.
   - **FILE's keys** (BUILD-S8): `rows` (counted, matched, reattached, dropped, null_uuid, stale_uuid, kept, archive_flags, shared, sql_cross_check); `events` (count, classes, attributed, unattributed, unattributed_by_holders); `attribution` (event id → entity uuid or null); `q_rows_kept_pre`; `null_uuid_pairs`; `stored_uuids`; `stored_uuids_that_are_keys`; `reattached_rows`; `dropped_rows`; `shared_rows`; `event_count_max_seq`; `entity_axis_state_rebuilt`; `audit_rows`; `success_payload`; `version_pre`; `version_post`; `generation`.
   - **Rows:**
     - counted and matched (the pair join);
     - re-attached (Part 2.2's re-attach SELECT);
     - dropped (unmatched and not re-attached: 2.2's dropped SELECT);
     - null-uuid (the matched rows only; BUILD-W1) and stale-uuid;
     - the counts by archive flags;
     - the shared rows;
     - the Q-rows-kept pre set: the matched rows plus the re-attached rows, each under its entity's current pair (PM-LIVE-W9).
   - **Events:** the expected entity uuid (or NULL) for every event id, and the four class counts, by the Python classification above.
   - **Checks:** E1: matched + re-attached + dropped = counted; E2: the four event classes sum to the `phase_events` count; E3: the row classes agree with a SQL count.
5. **`apply --db PATH --backup BACKUP [--confirm-live]`:**
   - G0 and the swap guards;
   - re-runs P1–P9 on PATH. P5 expects the generation and version read from BACKUP (v2 and 7 today; BUILD-S8);
   - A1: PATH's per-table fingerprints equal BACKUP's, so nothing has changed since the backup;
   - A2: the build: `schema_v2.V2_SCHEMA_VERSION == 8`, `database.V2_MIGRATIONS[8] is database.MIGRATIONS[26]`, and its name is `_v2_migration_8_rekey_workflow_phases`;
   - runs `EntityDatabase(PATH).close()`, with `PD_REKEY_APPLY=1` set for that open only: the one read-write open;
   - A3: the version after (read-only) is 8;
   - A4 (PM-LIVE-W10): no `-wal` remains after it closes. A remaining `-wal` fails the apply; 3.4's S6 rows say what to do.
6. **`verify --db PATH --backup BACKUP --expected FILE`:** runs every check of Part 2.6 against PATH, with both files read-only, including:
   - the per-event attribution against FILE;
   - the one-target check (BUILD-S8): the two tables' `sqlite_master` text against a fresh file and a staging file (`rebuild_tool.build_staging_database`) that the tool builds in a temp dir, and the views against the staging file's, so 3.7's T9 runs inside `verify`;
   - every other table unchanged, and `sqlite_sequence` changed only in `migration_audit_log`'s seq, by the number of audit rows written (1 → 2 on the live file; PM-LIVE-W2).
7. **`restore --db PATH --backup BACKUP --expected FILE [--confirm-live]`:**
   - G0 and the swap guards;
   - **BACKUP must be the old shape** (REH-W1): P5 and P6 run on BACKUP (version 7, no `entity_uuid`), so a migrated backup is refused;
   - re-runs P2–P4 on PATH, so nothing holds it;
   - runs the backup API from BACKUP (opened `immutable=1`) onto PATH, closing both connections in a `finally`;
   - if a `PATH-wal` remains after closing, runs `PRAGMA wal_checkpoint(TRUNCATE)` on one plain `sqlite3` connection, never `EntityDatabase`. The tool never deletes a `-wal` or `-shm` file (rekey §13.4);
   - **checks, named after 2.7's six points** (REH-S3):
     - 2.7-1: `schema_version` is 7, the value FILE's `version_pre` records, never read from BACKUP (REH-W1);
     - 2.7-2: every per-table fingerprint equals BACKUP's;
     - 2.7-3: the full `sqlite_master` text equals BACKUP's;
     - 2.7-4: `integrity_check` is `ok`;
     - 2.7-5: no `-wal` remains;
     - 2.7-6: PATH is page-identical to BACKUP outside the three header fields.
8. **`checkpoint --db PATH [--confirm-live]`** (PM-LIVE-W10): G0; one plain `sqlite3` connection, `PRAGMA wal_checkpoint(TRUNCATE)`, close. It reports the fingerprint, sha256 and version before and after. It never opens `EntityDatabase`, and never deletes a file.
9. **`diff --db PATH --ref COPY`** (PM-LIVE-W6): read-only. For each table in both files, the rows only in PATH and the rows only in COPY, as JSON. A table whose columns differ is reported by name.

**Red-first tests (new):** `scripts/test_rekey_live_registry.py`. The fixtures are `make_pre_rekey_db(tmp, "v2")` files, seeded with `seed_rekey_classes`. HOME is a temp dir, and the process sources and the account's home are injected. Red on base: the tool does not exist.
- **`test_preflight_passes_on_a_quiet_old_shape_file`.**
- **`test_preflight_fails_when_a_wal_file_exists`:** a second connection holds the file open in WAL mode.
- **`test_preflight_fails_when_a_pd_server_process_is_listed`:** on the live-path setup (HOME a temp dir holding the file at `.claude/pd/entities/entities.db`), the injected `ps` output has an `entity_server.py` line. The same output only reports, and does not fail, for any other path.
- **`test_preflight_fails_when_pd_is_enabled[user|user-local|project|project-local]`** (PM-LIVE-S2): on the live-path setup, the named settings file enables pd.
- **`test_preflight_fails_on_the_migrated_shape`:** version 8.
- **`test_backup_refuses_an_existing_destination`.**
- **`test_backup_equals_its_source_table_by_table`.**
- **`test_expect_counts_every_row_and_event_class`:** the seeded classes, one each, with the per-event attribution.
- **`test_expect_output_is_path_independent`** (R3; REH-W4): two backups of one file, at different paths, give byte-identical output files.
- **`test_classifier_label_decides_by_legacy_id_or_workspace_uuid[legacy-id|workspace-uuid|unknown-label]`** (R3; PM-LIVE-W8): a legacy-id label and a workspace-uuid label each decide; an `'__unknown__'` label stays undecided, even when the unknown workspace holds the type_id.
- **`test_expect_and_verify_report_the_stale_axis_view_rebuilt`** (R3; BUILD-S4): on `make_pre_rekey_db(tmp, "v2", stale_axis_view=True)`, `expect` and `verify` both report `entity_axis_state_rebuilt` true.
- **`test_apply_then_verify_passes`.**
- **`test_apply_fails_when_a_wal_remains_after_it_closes`** (R3; PM-LIVE-W10): check A4.
- **`test_verify_fails_when_a_row_state_differs`:** one row's `kanban_column` is changed after `apply`.
- **`test_verify_fails_when_another_table_changed`:** one `entity_tags` row is added after `apply`.
- **`test_apply_refuses_when_the_file_changed_since_the_backup`.**
- **`test_apply_and_restore_refuse_the_live_path_without_confirm_live`:** HOME is a temp dir holding a copy at `.claude/pd/entities/entities.db`, and the copy's fingerprint is unchanged afterwards. The same for `checkpoint`.
- **`test_swapped_apply_is_refused`** and **`test_swapped_restore_is_refused`** (R3; REH-W1): `--db` and `--backup` exchanged, or `--backup` on a live path: refused, and the backup's sha256 is unchanged.
- **`test_restore_refuses_a_migrated_backup`** (R3; REH-W1).
- **`test_restore_returns_version_7_and_the_backups_tables`.**
- **`test_checkpoint_after_a_killed_apply_removes_the_wal_and_keeps_the_file`** (R3; PM-LIVE-W10): after an apply killed inside its transaction, `checkpoint` leaves the main file byte-unchanged and removes the `-wal`.
- **`test_diff_lists_rows_changed_since_the_copy`** (R3; PM-LIVE-W6).
- **In `plugins/pd/hooks/tests/test-hooks.sh`: `test_sync_cache_refuses_an_older_schema_build`** (R3; PM-LIVE-W4): a temp HOME with a v8 registry, and a source at v7. The cache is unchanged, and the hook's JSON says why.

**The `sync-cache.sh` guard** (PM-LIVE-W4). The SessionStart hook runs the cache's own `sync-cache.sh`, which publishes the working tree of the checkout it detects (sync-cache.sh:12, :32). So a guard shipped with Phase R's publish runs before any later publish.
- **The check:** read the source's `V2_SCHEMA_VERSION` from `plugins/pd/hooks/lib/entity_registry/schema_v2.py`, and the live file's `schema_version` read-only (`immutable=1`, or `mode=ro` when a `-wal` exists).
- **If the source's value is lower:** skip the rsync, say why in the hook's `additionalContext` JSON, and exit 0. A hook never blocks a session.
- **It fails open** when the registry is absent or unreadable.

**Merge-entities, only if Q4 = delete** (PM-CONS-W7): delete `cmd_merge_entities` and its subparser; `migrate.sh import`'s merge step becomes a loud refusal, counted in `import_failures`; delete `TestMergeEntities` and the merge tests in `test_migrate_deepened.py`.

**Existing tests:** none change, unless Q4 = delete: then `TestMergeEntities` (scripts/test_migrate_db.py:325-573) and the merge tests in `scripts/test_migrate_deepened.py` go with `cmd_merge_entities` (rekey §14, as ruled).

**Gates**
- **G5:** grows by the new file. If merge-entities is deleted, it shrinks by `TestMergeEntities` and the merge tests in `test_migrate_deepened.py`: measure it.
- **G4:** runs, with the new `sync-cache.sh` test.
- **G1–G3:** unchanged.

**QA probes**
1. **Run the whole sequence on a same-minute live copy,** exactly as section 3.7 steps T2–T8 and T12 do: `preflight`, `backup`, `expect`, `apply`, `verify`, `restore`, then the restore checks. Compare with Part 2's figures. Then the new subcommands: `diff` against a copy taken right after `apply` lists exactly the one row a later write changed; `checkpoint` on a killed-apply copy removes the `-wal` and leaves the file byte-unchanged.
2. **The live-path guard:** set HOME to a temp dir holding a copy at `.claude/pd/entities/entities.db`, and run `apply` on that path without `--confirm-live`. It is refused, and the copy is unchanged. For the other form (PM-LIVE-W1), run the live-path helper alone on `/Users/terry/.claude/pd/entities/entities.db` with HOME a temp dir: it reports the file live, through the account's home. The helper only compares paths, and never opens the file.
   - **Never point the tool's subcommands at the real live file** during QA.
3. **Preflight with a fake server running,** on the live-path setup of probe 2: start a dummy process whose command line contains `entity_server.py` (for example, `python -c "import time; time.sleep(60)" entity_server.py`). `preflight` fails on P3. On any other path, it only reports P3.
4. **Run the design's guard preview on the tool** (BUILD-S5), from a copy, so the design's evidence file beside the original is not overwritten: `cp /Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/guard/guard_probe.py <qa-dir>/ && <PY> <qa-dir>/guard_probe.py <worktree>`. No hits in `scripts/rekey_live_registry.py`.
5. **The swap** (REH-W1): `apply` and `restore` with `--db` and `--backup` exchanged are refused, and the backup's sha256 is unchanged.
6. **The `sync-cache.sh` guard:** with a temp HOME holding a v8 registry, a v7 source's publish leaves the cache unchanged, and the JSON says why; with the registry absent, it publishes.

**Reviewer focus**
- **The only read-write opens** are the backup's destination, `apply`'s `EntityDatabase`, `restore`'s destination, and `checkpoint`'s connection.
- **Every read** of PATH or of the backup is `immutable=1`, or `mode=ro` when a `-wal` exists, on its own connection.
- **The event classification** implements rekey §3.3 independently of the migration's SQL, with the label rule above.
- **No subcommand deletes a file,** and none but `apply` sets `PD_REKEY_APPLY`.

### 1.8 R4-F1 to R4-F4: the strict naming rule and the test codemod (RK4; split in R3)

- **Implements:** rekey §6.1 (the strict half), §6.3 (`_resolve_identifier`, `get_entity`, `resolve_ref`, `search_by_type_id_prefix`), §6.4 (the codemod), §12 (feature 129's tests) and §15 RK4.
- **Why four tasks** (PM-CODE-W4). As one task, R4-F was too big for one implementer. The blast census measured it at `ddc299a0`, develop `c1bbfae0`'s code (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/blast/blast-report.md`, §3.2 and §7):
  - 1201 static test calls in 66 files, 804 of them in 10 files over 1500 lines;
  - 1057 direct test call sites in 63 files, plus 754 that reach a refusal through production code. Of those 754, 343 call engine and helper functions and 250 call MCP handlers, none of them on the codemod's old method list;
  - under the full rule, 961 of the 1451 tests G1 fails are R4-F's, in 54 files. 541 distinct call sites refuse first, and four fixtures account for 257 of those tests.
- **The split: expand, then contract** (rekey §15):
  - **R4-F1, R4-F2 and R4-F3** run the codemod, one test tree each. Each is additive under the global-unique fallback, so G1–G5 stay unchanged;
  - **R4-F4** makes the rule strict, once R4-D and the three slices have merged.
- **Per test tree** (direct + entry-point call sites, from the census):
  - entity_registry: 584 + 195 in 31 files (R4-F1);
  - workflow_engine: 179 + 287 in 15 files, and reconciliation_orchestrator: 17 + 9 in 5 files (R4-F2);
  - mcp: 252 + 263 in 13 files, 418 of them in `test_workflow_state_server.py` (R4-F3);
  - ui: 25 + 0 in 4 files (R4-D's).
- **Sizing rule** (1.1): before a slice's implementer starts, the orchestrator runs the codemod on the slice's base. If it leaves more than 150 hand edits, the slice is split by file.
- **Waits for:** Q2 (section 0.4). These briefs assume the recommended strict rule. If the user chooses the alternative (a default workspace bound to each connection), the orchestrator re-plans R4-F1 to R4-F4 before any of them starts.

#### 1.8.0 Shared by R4-F1, R4-F2 and R4-F3: the codemod

**Goal.** Every test call that names an entity by type_id passes the workspace that entity was registered in, or its uuid, while the fallback still answers. The strict flip (R4-F4) then breaks no test.

**Read first:** rekey §6.1, §6.4, §12 and §15 RK4; R4-A's and R4-B's entry-point tables (1.3 and 1.4, change 7), from their reports.

**The codemod** (rekey §6.4) works per test function.
- **Its method list:** `ENTITY_NAMING_METHODS`, plus every entry point that R4-A's and R4-B's entry-point tables say takes the workspace from its caller (PM-CODE-W4).
- **One workspace expression in scope** (the function and the fixtures it uses): it adds `workspace_uuid=<that expression>` to each call.
- **Two or more, or none it can read:** it leaves the calls and lists them. You then edit each by hand, taking the workspace from that entity's registration.
- **A call that names entities of two workspaces** passes their uuids instead. Feature 129's two calls are the known cases (1.8.1).
- **The script:** one script, kept in the phase's evidence directory under `agent_sandbox/` and never committed. It exists before the slices are cut, because the sizing rule runs it on each slice's base.

**First checks** (each slice, on its base, over its own tree):
1. **Re-run the design's churn count:** `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/scan/churn_totals.py`, plus `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/calvin/churn_gaps.py`. Record the test call counts, and list every production straggler for R4-F4.
2. **Re-run `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/calvin/codemod_workspace_scopes.py`:** which test files use more than one workspace expression. It found 30 of 81 at `5cc2ab75`; each slice re-measures on its base.
3. **Run the codemod,** and record its per-function classification (one workspace, several, or none) and its leftover list.

**Rules**
- **Arguments only:** a slice adds `workspace_uuid=` or uuid arguments, and changes no assertion unless its section says so.
- **No production edit:** a production straggler goes on R4-F4's list.
- **Phase 1's test files** (1.13): 1B's four and 1C's `test_brainstorm_registration_scoped.py` get workspace or uuid arguments only, and their assertions stay unchanged (PM-CONS-W8). 1C's skip tests are R4-C's.
- **`match=` on the 16 `pytest.raises` blocks that have none** (PM-CODE-W1): each slice adds `match=`, naming the error each block expects, in its own tree. The list is the premortem's `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/premortem/probes/raises_names.out` (at `5cc2ab75`: 12 in entity_registry, 4 in workflow_engine, none in mcp), less any that an earlier task deleted.

**Gates:** G1–G5 unchanged: each gate's failures equal the base's. An added argument that changes an outcome is a codemod error.

**QA probes** (each slice; they replace the old 20-edit sample, PM-CODE-W4)
1. **The record-only census** (the blast's method, blast-report.md §1.2):
   - on a copy of the slice's worktree, add the strict rule's four refusal points in record-only form: each constructs the refusal, records it and continues, as `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/blast/layers/record-only` does;
   - run G1 there (R4-F1 also G2) with the recorder `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/blast/work/blast_plugin.py` (`-p blast_plugin`), and summarize with `census_refusals.py` beside it;
   - expected: 0 would-be refusals from the slice's files.
2. **The closed leftover list:** every hand edit is listed, with its function and why.

**Reviewer focus**
- **No codemod edit** passes a workspace different from the one the entity was registered in.
- **Hand edits** take the workspace from the registration, not from a guess.
- **Phase 1's test files** gain only workspace or uuid arguments, with every assertion unchanged. Check it against the diff (PM-CONS-W8).

#### 1.8.1 R4-F1: the codemod on the entity_registry tests and G2's three scripts tests

- **Depends on:** R4-C.
- **Can run beside:** R4-D, R4-E, R4-F2 and R4-F3.
- **Waits for:** Q2 (strict).
- **Files:**
  - the test files under `plugins/pd/hooks/lib/entity_registry/` (31 with call sites at `ddc299a0`);
  - G2's three: `plugins/pd/scripts/tests/test_cleanup_backlog.py`, `test_parse_backlog_md.py`, and `test_c5b_parse_backlog_workspace.py`, whose `test_defensive_insert` calls `get_entity` with no workspace (:50; BLAST-S2);
  - repo `scripts/test_*.py` files (G5) that call a naming method with a type_id and no workspace.
- **Feature 129's two calls** (PM-CODE-B2; rekey §12, plan:257): in `test_cross_workspace_matrix.py`, the `HANDLERS` lambda at :230-236 and the call at :307 pass two workspaces' type_ids. Both pass the entities' uuids instead, and every assertion is unchanged.
- **Phase 1's files here:** 1A's `test_workflow_phase_writers.py` and `test_backfill_scoped.py` get arguments only. The fallback tests in `test_workflow_phase_writers.py` are R4-F4's.
- **`match=`:** the 12 entity_registry blocks.
- **Checklist:**
  - `(several test files)`: tests-72 (the implicit `phase_events` writers: `register_entity`, `upsert_entity`, `update_entity`, `_process_register_entity`). R4-F1 owns the row, and R4-F3 edits its mcp files. Its files here:
    - under `plugins/pd/hooks/lib/entity_registry/`: `test_c11_feature_entity_id.py`, `test_c12_display_width_from_renderer.py`, `test_c22a_reparent_entity.py`, `test_c3_completeness_guard.py`, `test_c9_c10_frontmatter_identity.py`, `test_census_and_issuance.py`, `test_cross_workspace_matrix.py`, `test_database_052.py`, `test_frontmatter.py`, `test_future_file_guard.py`, `test_migration_18_safety.py`, `test_project_identity.py`, `test_projection_determinism.py`, `test_ref_resolution.py`, `test_server_helpers.py`, `test_structured_registration.py`;
    - under `plugins/pd/scripts/tests/`: `test_cleanup_backlog.py`, `test_parse_backlog_md.py`;
    - `plugins/pd/hooks/tests/test-sqlite-concurrency.sh`, which task 4A deletes (W5.2) and no gate runs.
  - `entity_registry/test_c13_missing_parent_reported.py`: tests-29 (`module-level tests calling run_backfill`).
  - `entity_registry/test_c18_backfill_canonical_identity.py`: tests-30 (`module-level tests calling run_backfill`).
  - `entity_registry/test_c19_c20b_rebuild_structure.py`: tests-28 (`_OldFile`).
  - `entity_registry/test_c3_allocation_callers.py`: tests-70 (`test_promote_task_reports_the_refusal_not_invalid_input`).
  - `entity_registry/test_cleanup_suffix_parsers.py`: tests-31 (`TestACCL2BackfillNoMarkerDerivation`).
  - `entity_registry/test_dependencies.py`: tests-17 (`TestCascadeUnblock`).
  - `entity_registry/test_entity_lifecycle.py`: tests-12 (`db fixture`).
  - `entity_registry/test_entity_server.py`: tests-71 (`test at :176-199`).
  - `entity_registry/test_frontmatter_sync.py`: tests-32 (`TestBackfillHeaderAware`).
  - **Plus:** every test file in this tree that first check 1 lists.
- **QA probe 3** (beyond 1.8.0's): `git diff <base> -- plugins/pd/hooks/lib/entity_registry/test_cross_workspace_matrix.py` shows only the two calls changed (to uuids), and no assertion changed.

#### 1.8.2 R4-F2: the codemod on the workflow_engine and reconciliation_orchestrator tests

- **Depends on:** R4-C.
- **Can run beside:** R4-D, R4-E, R4-F1 and R4-F3.
- **Waits for:** Q2 (strict).
- **Files:** the test files under `plugins/pd/hooks/lib/workflow_engine/` (15 with call sites at `ddc299a0`) and `plugins/pd/hooks/lib/reconciliation_orchestrator/` (5).
- **Phase 1's files here** (arguments only, assertions unchanged): 1B's `reconciliation_orchestrator/test_session_start_reads_no_files.py` and `workflow_engine/test_get_state_without_hydration.py`; 1C's `reconciliation_orchestrator/test_brainstorm_registration_scoped.py`, except the skip tests R4-C rewrote.
- **`match=`:** the 4 workflow_engine blocks.
- **Checklist:**
  - `reconciliation_orchestrator/test_dependency_freshness.py`: tests-50 (`tests of cleanup_stale_dependencies`).
  - `reconciliation_orchestrator/test_entity_status.py`: tests-49 (`tests of sync_entity_statuses`).
  - `reconciliation_orchestrator/test_orchestrator.py`: tests-47 (`TestWorkflowReconcileAppliesDrift`).
  - `workflow_engine/test_c11_validator_and_init.py`: tests-36 (`helpers _activate`).
  - `workflow_engine/test_c15_c16_project_registration.py`: tests-45 (`_creation_events`).
  - `workflow_engine/test_engine.py`: tests-33 (`helpers _setup_engine`).
  - `workflow_engine/test_entity_engine.py`: tests-34 (`helper _with_phase`).
  - `workflow_engine/test_feature_lifecycle.py`: tests-35 (`TestInitFeatureState`).
  - `workflow_engine/test_reconciliation.py`: tests-37 (`helpers _setup_engine`).
  - `workflow_engine/test_rollup.py`: tests-41 (`helper _with_phase`).
  - `workflow_engine/test_router.py`: tests-42 (`db fixture`).
  - `workflow_engine/test_secretary_intelligence.py`: tests-43 (`TestGetParentContext`).
  - `workflow_engine/test_task_promotion.py`: tests-44 (`helpers _register_feature`).
  - **Plus:** every test file in these two trees that first check 1 lists.

#### 1.8.3 R4-F3: the codemod on the mcp tests

- **Depends on:** R4-C.
- **Outside prerequisite** (PM-CODE-S3): task 4A has landed on develop. It deletes tests in `test_workflow_state_server.py` (plan:371), the file with 418 of this slice's call sites.
- **Can run beside:** R4-D, R4-E, R4-F1 and R4-F2.
- **Waits for:** Q2 (strict).
- **Files:** the test files under `plugins/pd/mcp/` (13 with call sites at `ddc299a0`).
- **Phase 1's files here:** 1B's `test_reconcile_status_scoped.py` and `test_update_entity_archived.py` (arguments only, assertions unchanged); 1A's `test_create_feature_lanes.py` and `test_projection_names_directory.py` (arguments only).
- **`test_c8_workflow_state_kind.py` (tests-52):** the codemod's edits land here. Its assertion that `db.get_entity(type_id) is None` for a shared type_id stays, for R4-F4 to rewrite.
- **Checklist:**
  - tests-72's mcp files (the row is R4-F1's): `test_c9_c12_projection_identity.py`, `test_cross_workspace_mcp_regression.py`, `test_search_mcp.py`.
  - `plugins/pd/mcp/test_c11_mcp_dir_name.py`: tests-56 (`fixture column_directory_only`).
  - `plugins/pd/mcp/test_c15_c16_create_project_flow.py`: tests-57 (`module-level tests`).
  - `plugins/pd/mcp/test_c8_workflow_state_kind.py`: tests-52 (`helpers _seed_disagreeing_entity`).
  - `plugins/pd/mcp/test_complete_phase_closes.py`: tests-53 (`fixture seeded`).
  - `plugins/pd/mcp/test_feature_134_trustgate.py`: tests-55 (`fixture tool_env`).
  - `plugins/pd/mcp/test_issue_spawn.py`: tests-54 (`fixture parent_feature`).
  - `plugins/pd/mcp/test_workflow_state_server.py`: tests-51 (`fixtures seeded_engine`).
  - **Plus:** every test file in this tree that first check 1 lists.
- **QA probe 3** (beyond 1.8.0's): `git diff <base> -- plugins/pd/mcp/test_cross_workspace_mcp_regression.py` shows no assertion changed (rekey §12).

#### 1.8.4 R4-F4: the strict flip

- **Implements:** rekey §6.1 (the strict half), and §6.3's four rows named in 1.8.
- **Depends on:** R4-D, R4-F1, R4-F2 and R4-F3.
- **Can run beside:** none.
- **Waits for:** Q2 (strict).
- **Files:**
  - `plugins/pd/hooks/lib/entity_registry/database.py`;
  - the swallowing callers of change 7, in `workflow_engine/feature_lifecycle.py`, `workflow_engine/reconciliation.py`, `workflow_engine/router.py`, `workflow_engine/engine.py`, `entity_registry/server_helpers.py`, `entity_registry/frontmatter_sync.py`, `entity_registry/backfill.py`, `plugins/pd/mcp/workflow_state_server.py` and `plugins/pd/ui/routes/entities.py`, and the callers of `feature_dir_name` (`workflow_engine/feature_paths.py:87`);
  - the production stragglers the slices listed;
  - tests: `plugins/pd/hooks/lib/entity_registry/test_naming_rule.py` (R4-A created it), 1A's `test_workflow_phase_writers.py`, `plugins/pd/mcp/test_c8_workflow_state_kind.py`, and the existing tests of the converted callers.
- **Checklist:**
  - `entity_registry/database.py`: schema-50 (`_resolve_identifier`); schema-54 (`resolve_ref`); schema-57 (`search_by_type_id_prefix`).
  - **Plus:** the fallback tests of 1A's `test_workflow_phase_writers.py`, which have no inventory row.

**Brief**

**Goal.** A type_id names an entity only together with a workspace, for every method in `ENTITY_NAMING_METHODS`. The global-unique fallback goes, and the refusal reaches every caller: nothing turns it into None, `[]` or "not found".

**Read first:** rekey §6.1, §6.3 (the four rows), §8 (the engine contract), §10 (criterion 4) and §15 RK4; 1.8.0; the slices' straggler lists.

**Changes**
1. **`_resolve_identifier`** drops the "No scope: must be globally unique" branch (database.py:7041-7057). A type_id with no workspace raises `WorkspaceRequiredError`, a `ValueError` subclass, even when only one workspace holds it.
   - **The pinned message names the parameter** (PM-CODE-S4): `"<parameter> '<value>' needs a workspace_uuid: a type_id names an entity only inside one workspace"`. For example: `"type_id 'feature:X' needs a workspace_uuid: ..."`, and `"prefix 'feature:05' needs a workspace_uuid: ..."`.
2. **The deprecated `project_id` alias,** on the methods that already accept it, resolves exactly as `_resolve_optional_workspace_filter` does (database.py:6896-6977):
   - `'__unknown__'` names the unknown workspace;
   - another value names the workspace whose `project_id_legacy` it is, or raises;
   - given both, `workspace_uuid` wins, with a `DeprecationWarning`;
   - `'*'` is not a workspace;
   - `append_phase_event`'s `project_id` is its label, never an alias (rekey §6.1).
3. **`get_entity`:** a type_id with no workspace raises. A uuid, and a type_id with a workspace, are unchanged.
4. **`resolve_ref`:** its exact and prefix branches run only inside the workspace, and the unscoped exact match (:7236-7239) goes.
5. **`search_by_type_id_prefix`:** the workspace becomes required. After R4-C, its only production caller is `resolve_ref`: R4-C deleted 1C's `_another_workspace_holds` (BLAST-B2).
6. **Re-raised, never swallowed** (PM-CODE-W1): `get_entity`, `get_lineage` and every not-found handler in `database.py` (`feature_entity_id`, `get_workflow_phase`, `update_workflow_phase`, `set_archived`, `set_deleted`, `query_phase_events`) re-raise `WorkspaceRequiredError`. None turns it into None, `[]` or "not found".
7. **The swallowing callers let it propagate** (PM-CODE-W1; rekey §8):
   - `feature_lifecycle._promote_brainstorm` (:143-166) and `_validate_feature_type_id` (:103-134);
   - `reconciliation._read_single_meta_json` (:194-211), and the callers of `feature_dir_name` (feature_paths.py:87);
   - `server_helpers.py` :257, :369 and :484; `frontmatter_sync.py` :236 and :336;
   - `router.py` :358 and :437; `backfill.py` :346; `engine.py` :111;
   - `workflow_state_server.py` :2180, and `ui/routes/entities.py` :170.
   - **Each MCP handler** answers its workspace error. **The UI route** answers its 404 page by its own cookie check, before any library call (R4-D), and never by swallowing the refusal.
8. **Production stragglers** from the slices' first checks: each passes the workspace its caller holds.
9. **Only if Q3's yes arrived after R4-B merged:** make R4-B's change 2 (the three list tools), with its two list-tool tests. `plugins/pd/mcp/workflow_state_server.py` is already in this task's files.

**Red-first tests (in `test_naming_rule.py`)**
- **`test_type_id_without_workspace_raises[<each ENTITY_NAMING_METHODS pair>]`** (rekey §10: criterion 4):
  - *the setup:* a type_id that exactly one workspace holds.
  - *asserts:* called with no workspace, the method raises `WorkspaceRequiredError` matching `needs a workspace_uuid`, and nothing is written.
  - *special cases:* `set_parent` is checked once per parameter; `append_phase_event` is called with a `project_id` label and no `workspace_uuid` (rekey §11, rule 5); `search_by_type_id_prefix`'s message names `prefix`.
  - *red on base:* the fallback resolves the sole holder.
- **`test_resolve_ref_exact_match_needs_a_workspace`:** red, because the unscoped exact match answers the lowest rowid.
- **`test_project_id_alias_resolves_like_the_optional_filter`:**
  - *asserts:* `'__unknown__'`, a legacy id, an unheld label (raises), and both given (`workspace_uuid` wins, with a warning).
  - *red on base:* none expected, because the alias already exists. Mark the cases that pass on the base keep-green in your report.
- **`test_star_is_not_a_workspace`:** keep-green if the base already raises. Your report says which.
- **`test_refusal_reaches_the_caller[<site>]`** (PM-CODE-W1), one case per site of changes 6 and 7, on a real database:
  - *asserts:* a call with no workspace raises `WorkspaceRequiredError`, or answers the workspace error; it never answers None, `[]` or "not found";
  - *red on base:* the site swallows the error, or the fallback resolves.

**Existing tests**
- **Rewrite:**
  - `test_c8_workflow_state_kind.py` (tests-52), which asserts `db.get_entity(type_id) is None` for a shared type_id: it asserts the refusal instead;
  - in 1A's `test_workflow_phase_writers.py`, the two "refuses a type_id two workspaces hold" tests keep their subject and match the new message;
  - any test of a converted caller that pins None, `[]` or "not found" for a missing workspace: it asserts the refusal.
- **Unchanged assertions:** feature 129's four cross-workspace tests keep every assertion. R4-F1 changed their two calls (rekey §12, plan:257).
- **Delete** (rekey §6.1: the global-unique fallback is deleted), each replaced by a `test_type_id_without_workspace_raises` case:
  - 1A's `test_create_without_a_workspace_stores_the_sole_holders_identity`;
  - 1A's `test_upsert_without_a_workspace_resolves_a_globally_unique_type_id`;
  - any other test whose subject is the fallback.

**Gates**
- **G1:** failures equal the base's, apart from the listed additions, deletions and rewrites.
- **G2–G5:** unchanged. The slices already scoped G2's and G5's calls.

**QA probes**
1. **For each of the 20 pairs:** a type_id with no workspace raises the pinned message, naming its parameter.
2. **The record-only census over all of G1** (1.8.0's method, on a copy of this worktree): 0 refusals outside `test_naming_rule.py`, and 0 swallowed refusals.
3. **Re-run the churn count:** 0 production calls pass a type_id with no workspace; list any uuid-passing exceptions. Label-only stragglers (a `project_id=` with no `workspace_uuid=`; PM-CODE-W8): 0, by the premortem's `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/premortem/probes/label_only_calls.py`.

**Reviewer focus**
- **No caller** turns the refusal into None, `[]`, "not found" or a skipped step (rekey §8).
- **The message** names its parameter, exactly as pinned.
- **Each deleted test** is replaced by a `test_type_id_without_workspace_raises` case.

### 1.9 R4-G: the criterion-4 guard (RK5)

- **Implements:** rekey §11 and §15 RK5.
- **Depends on:** R4-E and R4-F4.
- **Can run beside:** R4-H.
- **Waits for:** Q4 (merge-entities; section 0.4). With the recommended delete, R4-E removes `cmd_merge_entities`, and nothing is declared for it (PM-CONS-W7).
- **Files:** `plugins/pd/hooks/lib/doctor/test_entity_keyed_access.py` (new).

**Brief**

**Goal.** A test that fails when new code keys either table by type_id alone, reaches an entity by a type_id without a workspace, or adds a method that names an entity without joining the naming rule.

**Read first:** rekey §11, and the model it follows: the identity-inference inventory in `doctor/test_audit_writes.py` (:498-650 at `4a6373f0`; `_INVENTORY_HIGH_WATER` at :628).

**First checks:**
1. **Does `plugins/pd/hooks/lib/entity_registry/display.py` exist on your base** (task 4A deletes it)? If it does, declare `display.py::_rename`; if not, don't.
2. **The user's ruling on Q4.** With the recommended delete, R4-E has removed `cmd_merge_entities`: declare nothing for it. If the user keeps it, declare `scripts/migrate_db.py::cmd_merge_entities`, keyed by its function name plus a sha256 of its source, so that any edit to it turns the guard red (PM-CONS-W7).
3. **Rule 5's widened pattern beyond the 20 pairs** (found while applying R3's revision). Run the pattern below on your base, and list every match outside `ENTITY_NAMING_METHODS`.
   - **Known on `c1bbfae0`:** `refuse_deleted_or_cross_workspace_parent.child_ref` (database.py:8054). It is a label used only in the refusal's message (:8079), beside a required `workspace_uuid`. (`query_phase_events_bulk.type_ids` also matches there; R4-C renames it `entity_uuids`.)
   - **A match that names no entity lookup:** the guard excludes it by name, with its reason in a comment.
   - **A match that resolves an entity by type_id:** stop and escalate.

**What the test holds** (rekey §11)
- **Scan roots:**
  - `plugins/pd/hooks/lib`, `plugins/pd/mcp`, all of `plugins/pd/ui` (routes, `mermaid.py`, templates) and `plugins/pd/scripts`;
  - the repository's `scripts/`.
- **Skipped:** `test_*.py`, `conftest.py`, any `tests/` directory, `.venv`, `__pycache__`, and docstrings.
- **Rules 1 to 5,** exactly as rekey §11 states them:
  1. SQL in one string;
  2. SQL split across literals in one function;
  3. Python maps and comparisons over workflow rows;
  4. template links;
  5. the API's shape and the schema. Rule 5's refusal half is `test_naming_rule.py::test_type_id_without_workspace_raises`, parametrized from the constant. The guard checks that `ENTITY_NAMING_METHODS` equals the AST scan of database.py (every parameter of a public `EntityDatabase` method whose name matches rule 5's pattern: 20 pairs, less first check 3's exclusions), and runs the schema checks on a temp `EntityDatabase`.
- **The widened matching** (R3; PM-CODE-W2):
  1. constant f-string, `%` and `.format` operands are resolved before matching;
  2. a workspace predicate counts only when it is unconditional: not under `? IS NULL OR`, and not appended under an `if`;
  3. the type_id predicate also matches `IS`, `>=`, `<`, `BETWEEN`, and a function call on the column (for example `instr(type_id, ?)`);
  4. rule 4 also covers Python string constants containing `/entities/` under `plugins/pd/ui` (for example `mermaid.py:67`);
  5. rule 5 matches parameter names by pattern: `(^|_)type_ids?$`, `_type_id$`, `(^|_)ref$` and `prefix`.
- **The event-label check** (R3; PM-CONS-S6): no production code compares the `type_id` key of `query_phase_events`' results with an entity's current type_id. That key is the event's write-time label (rekey §3.2).
- **The limits the test states:** SQL built at run time from data, and SQL outside Python strings.
- **Sites are keyed** `(relative path, enclosing function, rule)`.
- **The declared inventory:**
  - the functions that are values of `MIGRATIONS`, `MIGRATIONS_DOWN` and `V2_MIGRATIONS`, computed at test time;
  - plus the declared entries of the first checks.
- **The detected set must equal it.**
- **The high-water mark** is the count of declared entries (PM-CONS-W7):
  - with merge-entities deleted (Q4, recommended): 1 while `display.py` exists, and 0 once 4A lands;
  - if the user keeps it: 2, and 1.
- **What the test itself must not detect:** the operator tool, `scripts/rekey_live_registry.py`.

**Red-first evidence** (section 0.2, item 11). The review protocol's red run on the base cannot show red here: on your base every site is already fixed.
1. **Run the new test against a `git archive` of R4-C's merge commit** (rekey §15: "on RK2's head"). It must fail, listing the sites R4-D and R4-F4 removed:
   - rule 3's `_build_workflow_lookup` and `entity_detail`;
   - rule 4's four template links;
   - the strict-rule SQL that rule 1 flags in `_resolve_identifier`'s global-unique branch, `resolve_ref`'s unscoped exact match and `search_by_type_id_prefix`.
2. **On your base:** it passes.
3. **Scanner self-tests,** in the same file. They are red on the base because the scanner does not exist yet.
   - **`test_scanner_flags_a_synthetic_site[rule1_sql|rule1_label|rule2_split|rule3_map|rule4_link|rule4_python_link|event_label]`** feeds a synthetic source string per rule, and asserts it is flagged. The rule 1 case includes a join through `entities` filtered by type_id alone.
   - **`test_scanner_flags_a_premortem_evasion[fstring_column|percent_column|format_column|conditional_workspace|is_null_or_workspace|type_id_range|type_id_is|function_on_type_id]`** (R3; PM-CODE-W2): each evasion the premortem found passing rules 1 and 2 (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/premortem/probes/mut` and `probes/mutguard` beside it) is flagged.
   - **`test_scanner_passes_a_workspace_scoped_statement`** is their counterpart.

**Checklist:**


- `doctor/test_audit_writes.py`: tests-3 (`_KNOWN_INFERENCE_SITES`).
- **What this row means:** tests-3 is the model, read and not edited. The guard's own site set is rekey §11's 34 sites, which R4-A to R4-F4 fix or delete, less the declared entries.

**Existing tests:** none change.

**Gates**
- **G1:** grows by the new file.
- **G2–G5:** unchanged.

**QA probes**
1. **In a scratch copy of the worktree:** add to a scanned file a function with `SELECT workflow_phase FROM workflow_phases wp JOIN entities e ON e.uuid = wp.entity_uuid WHERE e.type_id = ?`. The guard fails.
2. **Add a public `EntityDatabase` method with a `type_id` parameter.** The guard fails until `ENTITY_NAMING_METHODS` lists it.
3. **Add `/entities/{{ x.type_id }}` to a template.** The guard fails.
4. **Raise the guard's high-water constant without adding a declared entry.** The guard fails.
5. **Add to a scanned file a comparison of an event's `type_id` key with an entity's current type_id** (for example, `ev["type_id"] == entity["type_id"]` over `query_phase_events`' results). The guard fails.

**Reviewer focus**
- **The inventory is computed,** not hand-listed, for the migration registries.
- **The high-water comment** keeps the model's rule: raising it is "a deliberate act with a line in that table, not a way to quiet a red test".

**Later changes to this guard**
- **If Phase R's rebase brings 4A:** `display.py` is gone. The rebase fix-up removes the entry and lowers the mark.
- **If 4A lands after Phase R:** 4A's own change does it (rekey §11).

### 1.10 R4-H: the docs that restate the key (split from RK2)

- **Implements:** rekey §14's docs sweep (section 0.2, item 3).
- **Depends on:** R4-F4.
- **Can run beside:** R4-G.
- **Files:** the `*.md` files the grep below finds, outside records; `CLAUDE.md` for one gotcha line; and the code comments and docstrings step 5's grep finds.
  - **Not `README.md`:** it holds the user's uncommitted edits (plan:60-62). If a `README.md` line needs a change, write a patch the way 4A does (plan:352-355) and hand it to the user; none needs one at `4a6373f0`.

**Brief**
1. **Run the design's grep** (rekey §14) on your base, and redirect it to a file:
   ```
   git grep -n -E 'workflow_phases|phase_events|append_phase_event|query_phase_events|get_workflow_phase|upsert_workflow_phase|create_workflow_phase|update_workflow_phase|delete_workflow_phase' -- '*.md' ':!docs/plans' ':!docs/features' ':!docs/brainstorms' ':!docs/projects' ':!docs/rca' ':!docs/knowledge-bank' ':!CHANGELOG.md' ':!agent_sandbox'
   ```
   - **At `4a6373f0`:** 39 lines in 8 files (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/r2/docs_grep.txt`):
     - `docs/technical/api-reference.md` 10;
     - `docs/dev_artifacts/backlog-manual.md` 9;
     - `docs/entity-archive-manifest.md` 7;
     - `docs/technical/architecture.md` 4;
     - `README_FOR_DEV.md` 4, including :451 (inventory 10.6, O3);
     - `docs/dev_guides/cutover-runbook.md` 3;
     - `CLAUDE.md` 1;
     - `docs/dev-guide/architecture-overview.md` 1.
2. **Also grep the same scope** for `_fix_remove_orphan_workflow`, `c22_recreate_live_remainder`, `fix_kanban_columns`, and "orphan" near `workflow_phases`.
3. **Give each line a disposition:** edited, or "states no key / is a record".
   - **The edits restate the new key and the naming rule:**
     - `entity_uuid` is the key of both tables;
     - a type_id names an entity only with a workspace;
     - the new keywords (`workspace_uuid` on `get_entity`, `get_workflow_phase`, `feature_entity_id` and `query_phase_events`; `entity_uuid` on `append_phase_event` and `query_phase_events`);
     - `query_phase_events_bulk(entity_uuids)`;
     - the row view's keys;
     - `delete_workflow_phase` removed.
4. **`CLAUDE.md`, "Entity Registry & Gotchas":** add one bullet stating the naming rule and the `entity_uuid` key of both tables, citing this playbook.
5. **Grep the code's comments and docstrings** (R3; PM-CONS-W2), and redirect it to a file:
   ```
   git grep -n -E 'keyed by type_id|type_id alone|until Phase R|\(Phase R\)|Known gap' -- '*.py' '*.sh'
   ```
   - **Expected after your edits:** no line, outside records and tests that name a removed behaviour.
   - **Each line it finds** is edited to state the new key, or given its disposition, as in step 3.

**Red-first tests:** none (docs only).

**Existing tests:** none.

**Gates**
- **G3:** it runs `validate.sh`, which checks docs.
- **All five** run as usual.

**QA probes**
1. **Re-run both greps** (steps 1 and 5): every line has a disposition in the report.
2. **Every signature the edited docs state** matches the code on the branch (codegraph).

**Reviewer focus:** the grep's scope matches rekey §14 exactly, and no record (plans, features, brainstorms, rca, knowledge bank, changelog) was edited.

### 1.11 R4-I: the live-migration sitting (RK6)

- **Implements:** rekey §13.3–§13.5, as Part 3 of this playbook.
- **Depends on:**
  - R4-G, R4-H;
  - Phase R's integration (1.12), with its per-rebase checklist;
  - R3's rehearsal (section 3.7);
  - the user's one yes (Q5, batch 2).
- **Files:** none in the repository. The phase report records the fingerprints, the backup, the expected and verified figures, and the two commits (develop before landing, and the landed commit).
- **Who runs it:** the orchestrator, as operator, in a Claude Code session with pd disabled (Part 3).

### 1.12 Phase R integration

After R4-G and R4-H merge into `followups-phase-r`:
1. **An integration review and QA** (plan:91): G1–G5 on the phase branch.
2. **F1,** with the adjustments of section 0.3, item 5:
   - **the baseline:** the migrated snapshot;
   - **step 4:** the `entity_uuid` query, with pedantic-drip's 28 row-less entities on today's data.
3. **A rebase each time develop moves** (plan:75-76). Phase R rebases onto develop and re-runs this integration QA. If the rebase brings 4A, the guard's `display._rename` entry is removed and its mark lowered (1.9).
4. **The per-rebase checklist** (R3; PM-CONS-W4). Each rebase runs it:
   1. re-run the codemod and the record-only census (1.8.0) on the test files that arrived since the last rebase: 0 would-be refusals;
   2. re-run rekey §6.2's uuid greps, and a grep for `row['type_id']` and `.get('uuid')`, on the code that arrived;
   3. if 3A landed: re-check step S10 and 3.5's R5 against the landed `sync-cache.sh`, and keep R4-E's guard hunk;
   4. if 4C landed: the migration runner is serialized, its race tests pass with migration 26 registered, and Phase R's tests patch no `PID_DIR` or watchdog by hand;
   5. if 4A's W5.7 landed: re-check the `backfill.py` and `engine.py` deletions against R4-A's and R4-F4's edits;
   6. record each item's result in the integration report.
5. **Then Phase R waits** for the user's one yes (Q5) and the sitting (Part 3). It never fast-forwards develop outside the sitting (rekey §13.1).

### 1.13 Row coverage

`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/r2/rows/assign.py` assigns all 369 inventory rows: 0 missing, 0 duplicated. R3's re-slicing moves R4-F's 33 rows to R4-F1 to R4-F4 by tree, and gives R4-C0 none.

| Owner | Rows |
|---|---|
| R4-A | 91 |
| R4-B | 57 |
| R4-C0 | 0 |
| R4-C | 87 |
| R4-D | 10 |
| R4-E | 0 (1, SCR-7, if Q4 = delete) |
| R4-F1 | 10 |
| R4-F2 | 13 |
| R4-F3 | 7 |
| R4-F4 | 3 |
| R4-G | 1 |
| No task | 90 (89 if Q4 = delete) |

- **Section 5.4** (the 277 surviving rows outside test files, the re-key's checklist): R4-A 91, R4-B 57, R4-C 43, R4-D 10, R4-F4 3; 73 left out, all in the table below.
- **Section 6** (the row ids its tables name; its text also names a few rows from other tables):
  - **6.1:** 34 ids. R4-A 18, R4-B 11, R4-C 2, R4-D 1; two, engines-7 and engines-85, are deleted by W1 and do not survive.
  - **6.2:** 41 ids. R4-A 23, R4-B 10, R4-D 6; MD-17 and MD-24 are left out.
  - **6.3:** 19 ids. R4-A 4, R4-B 10, R4-C 1, R4-F4 3; MD-17 is left out.
- **Section 7** (tests): 81 ids. R4-C 45, R4-F1 10, R4-F2 13, R4-F3 7, R4-G 1; 5 are left out.

**Rows left out, with the design's reason** (rekey §15, "Rows no task edits"):

| Reason | Rows | Count |
|---|---|---|
| Historical migrations, kept as written; the guard allows them | schema-1 to -10, -12 to -18, -24, -25; fill-1 | 20 |
| Already keyed by uuid, or holding no entity key | schema-47, -48, -51, -53, -59 to -65, -67, -69 to -71 | 15 |
| Read by the migration as its target (views.py's text) | schema-72 | 1 |
| Deferred (the `ready` gap in the `kanban_column` CHECK) | schema-73 | 1 |
| Deleted by W1 (Phase 1) | engines-7 to -9, -43 to -45, -84 to -86, -88, -90; MCPW-31 | 12 |
| Deleted by task 4A (W5.1, W5.2) | engines-83; fill-3 | 2 |
| Out of scope (rekey §14): merge-entities and the counts, the backlog parser, one-offs, the bash migrate tests. SCR-7 leaves this row for R4-E if Q4 = delete | SCR-4, -7, -8, -11, -12; TST-3; tests-67 to -69 | 9 |
| Reached only through the Python they launch; R4-C's QA probe 5 and section 3.7's step T13 run that Python | HOOK-1 to -5 | 5 |
| Tool parameters unchanged, so no markdown change (rekey §6.5) | MD-1 to -25 | 25 |

- **tests-67 to -69 stay out as rows,** since their hand-rolled old-shape helpers are unchanged. Inside their files, R4-C restates `TestMigration6`'s three row assertions (scripts/test_migrate_db.py:941) whether or not 4B lands (BUILD-W2). If Q4 = delete, R4-E deletes `TestMergeEntities` (tests-67's file) and the merge tests of `test_migrate_deepened.py` (tests-69's).

**Rows two tasks touch** (each has one owner):
- **schema-50, -54 and -57:** R4-A and R4-B pass the workspace at their call sites; R4-F4, the owner, changes the methods.
- **Test rows with raw SQL on the two tables:** R4-C0 moves their statements behind its helpers (the list in 1.4a), and R4-C re-keys the helpers. Their owners (R4-C, R4-F1 to R4-F3) keep them. R4-C0 owns no row.
- **tests-72:** R4-F1 owns it; R4-F3 edits its mcp files.
- **tests-52:** R4-F3 owns it; R4-F4 rewrites its `get_entity(type_id) is None` assertion.
- **synth-2:** R4-B owns it (the tool at entity_server.py:1207); R4-A gives `_process_export_lineage_markdown` (server_helpers.py:369) its workspace parameter (BLAST-W2).
- **1A's four test files:** they have no rows. R4-C restates their row-key assertions; R4-F1 and R4-F3 add arguments; R4-F4 rewrites or deletes their fallback tests.
- **1B's four test files and 1C's `test_brainstorm_registration_scoped.py`** (PM-CONS-W2): they have no rows. The R4-F slice for their tree adds workspace or uuid arguments only, with assertions unchanged (PM-CONS-W8); R4-C rewrites 1C's skip tests (BLAST-B2).
- **1C's `_another_workspace_holds`** (entity_status.py:244-257): no row. R4-C deletes it, before R4-F4 makes the prefix search strict (BLAST-B2).

## Part 2. The migration

Everything in this part is rekey §4 and §5, restated as code with the SQL as the design states it. Anything this playbook adds is marked "playbook". Where the two differ, the design binds.

### 2.1 One function, both chains

```python
# entity_registry/database.py, after _v2_migration_7_immutable_is_legacy (:6348 at 4a6373f0, unmoved at c1bbfae0)
def _v2_migration_8_rekey_workflow_phases(conn: sqlite3.Connection) -> None: ...

V2_MIGRATIONS[8] = _v2_migration_8_rekey_workflow_phases   # inside the V2_MIGRATIONS dict (:6481)
MIGRATIONS[26] = _v2_migration_8_rekey_workflow_phases     # beside MIGRATIONS[22..25] (:6496-6499)

# entity_registry/schema_v2.py:31
V2_SCHEMA_VERSION = 8     # the import-time assert (database.py:6506) fails if the two move apart
```

- **Which file takes which chain:**
  - a fresh or v1-generation file runs `_migrate` (database.py:11078): 25 → 26;
  - the live file (v2 generation) runs `_migrate_v2` (:11191): 7 → 8;
  - a staging file from `rebuild_tool.build_staging_database` reaches v2/8 through both.
- **Forward only:** there is no `MIGRATIONS_DOWN[26]`, so `_migrate_down` raises `NotImplementedError` for it. Rollback is a restore (2.7).
- **The runner stamps the version** after the function returns, as for every migration. The runner is serialized and its stamp monotonic (task 4C), so two processes opening a pre-rekey file run migration 26/8 once (BLAST-B1).

### 2.2 The steps, with their SQL (rekey §4.4)

**Step 1: probe, outside the lock.** Three parts can be pending. If none is, return: a re-run is a no-op, and a core-only `bootstrap_v2` file with neither table is left alone.
```sql
PRAGMA table_info(workflow_phases);  -- pending: the table exists and has no entity_uuid column
PRAGMA table_info(phase_events);     -- pending: the table exists and has no entity_uuid column
SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'events';            -- v2 files only
SELECT sql FROM sqlite_master WHERE type = 'view' AND name = 'entity_axis_state';
-- pending: the view is missing, or its whitespace-normalised text differs from _VIEWS_DDL's
-- first statement (views.py:86-91) with "IF NOT EXISTS" removed
```

**Step 1b: the live-path tripwire** (playbook, from rekey §13.1; PM-CONS-W5). If a pending part has rows to move (old-shape `workflow_phases` or `phase_events` rows), and the connection's main file (`PRAGMA database_list`) is the account's live registry (1.7's live-path test), raise `MigrationError` naming `scripts/rekey_live_registry.py`. Only `PD_REKEY_APPLY=1` lifts it, and only the tool's `apply` sets it. Nothing has changed yet.

**Step 2: foreign keys off.** If the read-back is still 1, a transaction is open: raise `MigrationError` (database.py:4341).
```sql
PRAGMA foreign_keys;          -- record the value, to restore it in step 11
PRAGMA foreign_keys = OFF;
PRAGMA foreign_keys;          -- must read 0
```

**Step 3:** `BEGIN IMMEDIATE`, as literal SQL. The function runs on both `EntityDatabase`'s connection and `rebuild_tool`'s autocommit connection (as v2 migration 2 does, database.py:5999-6007).

**Step 4: re-probe under the lock** with step 1's queries. A peer may have finished first.
- **If nothing is pending:** `ROLLBACK`, restore `foreign_keys`, and return None. No audit row is written.

**Step 5: refuse a surprise dependent,** only when the `workflow_phases` part is pending. Any row raises `MigrationError`.
```sql
-- playbook's rendering of rekey §4.4 step 5; 0 rows on the live file (read with immutable=1, 2026-09-26)
SELECT type, name FROM sqlite_master
WHERE (type = 'trigger' AND tbl_name <> 'workflow_phases' AND sql LIKE '%workflow_phases%')
   OR (type = 'view' AND sql LIKE '%workflow_phases%');
```

**Step 6: copy-rename `workflow_phases`,** when pending.
```sql
-- 6.1 count
SELECT count(*) FROM workflow_phases;

-- 6.2 rows no entity holds by (workspace_uuid, type_id), a NULL workspace included, split in two
--     (playbook's rendering of the rule; the conditions are rekey §5.1's re-attach copy):
--   re-attached: audit event 'rekey_row_reattached', one row each
SELECT wp.*, e.uuid AS entity_uuid, e.workspace_uuid AS entity_workspace_uuid
FROM workflow_phases wp JOIN entities e ON e.uuid = wp.uuid
WHERE NOT EXISTS (SELECT 1 FROM entities x
                  WHERE x.workspace_uuid = wp.workspace_uuid AND x.type_id = wp.type_id)
  AND NOT EXISTS (SELECT 1 FROM entities m JOIN workflow_phases w1
                    ON w1.workspace_uuid = m.workspace_uuid AND w1.type_id = m.type_id
                  WHERE m.uuid = e.uuid)
  AND (SELECT count(*) FROM workflow_phases w2 WHERE w2.uuid = wp.uuid) = 1;
--   dropped (the unmappable class): audit event 'rekey_row_dropped', one row each: unmatched, and not
--   re-attached. NOT EXISTS against the whole re-attach predicate, so a NULL type_id (the old TEXT
--   PRIMARY KEY admits one) is still classified (the form of R3's export).
SELECT wp.* FROM workflow_phases wp
WHERE NOT EXISTS (SELECT 1 FROM entities x
                  WHERE x.workspace_uuid = wp.workspace_uuid AND x.type_id = wp.type_id)
  AND NOT EXISTS (SELECT 1 FROM entities e WHERE e.uuid = wp.uuid
    AND NOT EXISTS (SELECT 1 FROM entities m JOIN workflow_phases w1
                      ON w1.workspace_uuid = m.workspace_uuid AND w1.type_id = m.type_id
                    WHERE m.uuid = e.uuid)
    AND (SELECT count(*) FROM workflow_phases w2 WHERE w2.uuid = wp.uuid) = 1);

-- 6.3 stale stored uuids: audit event 'rekey_stored_uuid_ignored', one row each
SELECT wp.type_id, wp.workspace_uuid, wp.uuid AS stored_uuid, e.uuid AS entity_uuid
FROM workflow_phases wp
JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id
WHERE wp.uuid IS NOT NULL AND wp.uuid <> e.uuid;

-- 6.4 the new table (rekey §4.2; CHECK lists with the same allowed values as the live DDL,
--     compared as sets by test_fresh_and_staging_shapes_identical)
DROP TABLE IF EXISTS workflow_phases_new;
CREATE TABLE workflow_phases_new (
    entity_uuid                TEXT NOT NULL PRIMARY KEY
                               REFERENCES entities(uuid),
    workflow_phase             TEXT CHECK(workflow_phase IN (
                                   'brainstorm','specify','design',
                                   'create-plan','implement','finish',
                                   'draft','reviewing','promoted','abandoned',
                                   'open','triaged','dropped',
                                   'discover','define','deliver','debrief'
                               ) OR workflow_phase IS NULL),
    kanban_column              TEXT NOT NULL DEFAULT 'backlog'
                               CHECK(kanban_column IN (
                                   'backlog','prioritised','wip',
                                   'agent_review','human_review',
                                   'blocked','documenting','completed'
                               )),
    last_completed_phase       TEXT CHECK(last_completed_phase IN (
                                   'brainstorm','specify','design',
                                   'create-plan','implement','finish',
                                   'draft','reviewing','promoted','abandoned',
                                   'open','triaged','dropped',
                                   'discover','define','deliver','debrief'
                               ) OR last_completed_phase IS NULL),
    mode                       TEXT CHECK(mode IN ('standard','full','light')
                                          OR mode IS NULL),
    backward_transition_reason TEXT,
    updated_at                 TEXT NOT NULL
);

-- 6.5 copy the matched rows
INSERT INTO workflow_phases_new
SELECT e.uuid, wp.workflow_phase, wp.kanban_column, wp.last_completed_phase,
       wp.mode, wp.backward_transition_reason, wp.updated_at
FROM workflow_phases wp
JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id;

-- 6.6 copy the re-attached rows (rekey §5.1, verbatim)
INSERT INTO workflow_phases_new
SELECT e.uuid, wp.workflow_phase, wp.kanban_column, wp.last_completed_phase,
       wp.mode, wp.backward_transition_reason, wp.updated_at
FROM workflow_phases wp JOIN entities e ON e.uuid = wp.uuid
WHERE NOT EXISTS (SELECT 1 FROM entities x
                  WHERE x.workspace_uuid = wp.workspace_uuid AND x.type_id = wp.type_id)
  AND NOT EXISTS (SELECT 1 FROM entities m JOIN workflow_phases w1
                    ON w1.workspace_uuid = m.workspace_uuid AND w1.type_id = m.type_id
                  WHERE m.uuid = e.uuid)
  AND (SELECT count(*) FROM workflow_phases w2 WHERE w2.uuid = wp.uuid) = 1;

-- 6.7 (Python) copied + re-attached + dropped = the count of 6.1, else MigrationError
-- 6.8 the old table; its 3 triggers and 4 indexes go with it
DROP TABLE workflow_phases;
-- 6.9
ALTER TABLE workflow_phases_new RENAME TO workflow_phases;
-- 6.10 the indexes and triggers
CREATE INDEX idx_wp_kanban_column ON workflow_phases(kanban_column);
CREATE INDEX idx_wp_workflow_phase ON workflow_phases(workflow_phase);
CREATE TRIGGER wp_reject_unknown_entity
BEFORE INSERT ON workflow_phases
WHEN NOT EXISTS (SELECT 1 FROM entities e WHERE e.uuid = NEW.entity_uuid)
BEGIN SELECT RAISE(ABORT, 'workflow_phases.entity_uuid names no entity; register the entity first'); END;
CREATE TRIGGER enforce_immutable_wp_entity_uuid
BEFORE UPDATE OF entity_uuid ON workflow_phases
WHEN NEW.entity_uuid IS NOT OLD.entity_uuid
BEGIN SELECT RAISE(ABORT, 'workflow_phases.entity_uuid is immutable: a row belongs to one entity for life'); END;
-- then assert the index-name set (playbook: the names the prototype produced on all four files):
SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'workflow_phases' ORDER BY name;
-- = idx_wp_kanban_column, idx_wp_workflow_phase, sqlite_autoindex_workflow_phases_1
```

**Step 7: alter `phase_events` in place,** when pending. There is no copy-rename, so `sqlite_sequence` and the AUTOINCREMENT ids are untouched.
```sql
ALTER TABLE phase_events ADD COLUMN entity_uuid TEXT REFERENCES entities(uuid);

-- sole-holder: the type_id's only holder (rekey §5.2, verbatim); its rowcount is the sole-holder count
UPDATE phase_events SET entity_uuid =
  (SELECT e.uuid FROM entities e WHERE e.type_id = phase_events.type_id)
WHERE entity_uuid IS NULL
  AND (SELECT count(*) FROM entities e WHERE e.type_id = phase_events.type_id) = 1;

-- label-decided: several holders; the label names one holder's workspace, by its legacy id or its uuid;
--   '__unknown__' never decides (verbatim); its rowcount is that count
UPDATE phase_events SET entity_uuid =
  (SELECT e.uuid FROM entities e JOIN workspaces w ON w.uuid = e.workspace_uuid
    WHERE e.type_id = phase_events.type_id
      AND (w.project_id_legacy = phase_events.project_id OR w.uuid = phase_events.project_id)
      AND phase_events.project_id <> '__unknown__')
WHERE entity_uuid IS NULL
  AND (SELECT count(*) FROM entities e WHERE e.type_id = phase_events.type_id) > 1
  AND (SELECT e.uuid FROM entities e JOIN workspaces w ON w.uuid = e.workspace_uuid
        WHERE e.type_id = phase_events.type_id
          AND (w.project_id_legacy = phase_events.project_id OR w.uuid = phase_events.project_id)
          AND phase_events.project_id <> '__unknown__') IS NOT NULL;
-- the lookup is unique: project_id_legacy is UNIQUE, a legacy id (12 hex characters) never equals
--   a workspace uuid, and entities are unique per (workspace, type_id)

-- undecided and no-holder: no statement; entity_uuid stays NULL

DROP INDEX IF EXISTS idx_pe_lookup;               -- (type_id, phase, event_type)
DROP INDEX IF EXISTS idx_pe_project;              -- (project_id, event_type)
DROP INDEX IF EXISTS phase_events_backfill_dedup; -- UNIQUE(type_id, phase, event_type, timestamp) WHERE source = 'backfill'
CREATE INDEX idx_pe_entity ON phase_events(entity_uuid, phase, event_type);
CREATE UNIQUE INDEX phase_events_backfill_dedup
    ON phase_events(entity_uuid, phase, event_type, timestamp) WHERE source = 'backfill';
CREATE TRIGGER pe_reject_live_event_without_entity
BEFORE INSERT ON phase_events
WHEN NEW.source = 'live' AND NEW.entity_uuid IS NULL
BEGIN SELECT RAISE(ABORT, 'phase_events: a live event must name its entity (entity_uuid)'); END;
CREATE TRIGGER enforce_immutable_pe_entity_uuid
BEFORE UPDATE OF entity_uuid ON phase_events
WHEN OLD.entity_uuid IS NOT NULL AND NEW.entity_uuid IS NOT OLD.entity_uuid
BEGIN SELECT RAISE(ABORT, 'phase_events.entity_uuid is immutable once set'); END;
-- idx_pe_timestamp stays
```

**Step 8: re-create the view,** on v2 files only, when pending (rekey §4.3). Run each statement with `conn.execute`. Never use `executescript`: it would COMMIT in the middle of the transaction.
```sql
DROP VIEW IF EXISTS entity_axis_state;
-- then each ';'-separated statement of views._VIEWS_DDL (views.py:86-105):
CREATE VIEW IF NOT EXISTS entity_axis_state AS
SELECT entity_uuid, axis, to_value, MAX(uuid) AS event_uuid, timestamp
FROM events
WHERE event_type != 'skipped'
GROUP BY entity_uuid, axis;
-- entity_state's own CREATE VIEW IF NOT EXISTS leaves the existing view in place
```

**Step 9: check foreign keys,** scoped to the two tables, and only for those that exist on this file. An unrelated violation elsewhere must not stop the file from opening. Any row returned raises `MigrationError`.
```sql
PRAGMA foreign_key_check(workflow_phases);
PRAGMA foreign_key_check(phase_events);
```

**Step 10:** write one `success` audit row (2.3).

**Step 11:** `COMMIT`. On any exception, `ROLLBACK` and re-raise. In a `finally`, restore `PRAGMA foreign_keys` to its recorded value.

**Resumability** (rekey §4.4, shown by the prototype on live copies):

| Interruption | Result |
|---|---|
| Process killed inside the transaction | Tables and schema unchanged; the next open migrates (529 rows) |
| Exception after the copy | `ROLLBACK`; tables and schema unchanged; `foreign_keys` back on |
| Crash between `COMMIT` and the version stamp | Version still 7; the next open finds nothing pending and changes only `_metadata` |
| Re-open of a migrated file | No table changes, and no audit row |

### 2.3 The audit rows (playbook: pins rekey §4.4's "counts" to key names)

- **How they are written:** all through `_append_migration_audit_log(conn, version=, event_type=, payload=)` (database.py:4353). It stores `json.dumps(payload)` with the default separators, so every payload contains the text `"migration": "rekey_workflow_phases"`.
- **`migration_version`:** the chain generation when the migration ran: 8 when `_metadata.schema_generation` was `'v2'`, and 26 otherwise. Staging-built and fresh files record 26; a fresh file carries one `success` row with every count 0.

| `event_type` | When | Payload keys |
|---|---|---|
| `success` | once, at step 10 | `migration`, `workflow_phases_pre`, `workflow_phases_copied`, `workflow_phases_reattached`, `workflow_phases_dropped`, `workflow_phases_stale_uuid`, `phase_events_sole_holder`, `phase_events_label_decided`, `phase_events_unattributed`, `entity_axis_state_rebuilt` (a part that was not pending records 0 or `false`) |
| `rekey_row_reattached` | once per re-attached row | `migration`, `row` (every old column by name), `entity_uuid`, `entity_workspace_uuid` |
| `rekey_row_dropped` | once per unmappable row | `migration`, `row` (every old column by name), `reason` |
| `rekey_stored_uuid_ignored` | once per stale stored uuid | `migration`, `type_id`, `workspace_uuid`, `stored_uuid`, `entity_uuid` |

- **Difference from the prototype's payload:** it named the event counts `phase_events_unique_holder` and `phase_events_shared_by_label`, and carried `v1_version` and `v2_version`. The shipped keys follow the design's class names above.

### 2.4 Pre-flight checks, with today's values

Read on 2026-09-26 with `immutable=1`. The operator tool's `preflight` runs checks P1–P9 (section 1.7).

| Check | How | Today |
|---|---|---|
| P1: no `-wal` | `ls /Users/terry/.claude/pd/entities/entities.db-wal` | absent; no `-shm` either |
| P2: no process holds the file | `lsof /Users/terry/.claude/pd/entities/entities.db` prints nothing | checked at the sitting |
| P3: no pd server process | `ps -axww -o pid=,command=`, filtered as in section 1.7 | none running (2026-09-26) |
| P4: pd enabled in no settings file that applies | `enabledPlugins["pd@pedantic-drip-marketplace"]` in `settings.json` and `settings.local.json` under the account's home (`/Users/terry/.claude/`), and in every workspace root's `.claude/settings.json` and `.claude/settings.local.json` (roots from the registry's `workspaces` table) | `false` in `/Users/terry/.claude/settings.json`; no other file of the 21 workspace roots names it |
| P5: generation and version | `SELECT key, value FROM _metadata WHERE key IN ('schema_generation','schema_version')` | `v2`, `7` |
| P6: the old shape | `PRAGMA table_info` | `workflow_phases`: 9 columns, `type_id, workflow_phase, kanban_column, last_completed_phase, mode, backward_transition_reason, updated_at, uuid, workspace_uuid`. `phase_events`: 13 columns, no `entity_uuid` |
| P7: no earlier run of this migration | `SELECT count(*) FROM migration_audit_log WHERE payload LIKE '%"migration": "rekey_workflow_phases"%'` | 0. The table's one row is migration 14's `success`, with payload `{"feature": "111-issue-lifecycle-closure"}` |
| P8: integrity | `PRAGMA integrity_check` | `ok` (on the copy) |
| P9: no surprise dependent | step 5's query | 0 rows |
| Row counts | `SELECT count(*)` | `entities` 589; `workspaces` 21; `workflow_phases` 529; `phase_events` 1469 (1372 `backfill`, 97 `live`); `events` 2244; `migration_audit_log` 1 |
| Fingerprint | `stat -f '%m %z'`; sha256 | `1790286038 4083712`; `2814bb4434e8faa0` |

### 2.5 Expected figures

**How they are derived:** on the backup (old shape), by the operator tool's `expect`, and independently by the SQL below. R2 re-derived both on fresh copies of today's file (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/r2/exp/files/rederive.json`); they agree with each other and with the design's prototype and `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/calvin/live_class_counts.out`.

| Figure | Today |
|---|---|
| `workflow_phases` rows counted | 529 |
| matched (by pair) | 529 |
| re-attached | 0 |
| unmappable (dropped) | 0 |
| null-uuid (facet of matched) | 8, all pedantic-drip: `backlog:278`–`284` and `feature:134-workflow-rebuild` |
| stale-uuid | 0 |
| by archive flags (`is_archived`, `is_deleted`) | (0, 0): 366; (1, 0): 163 |
| shared rows | 5, all pedantic-drip (the five type_ids in 2.6) |
| events: sole-holder / label-decided / undecided / no-holder | 1436 / 8 / 13 / 12 |
| attributed / unattributed | 1444 / 25 |

```sql
-- rows (rekey §5.1 "pre" queries, run on the backup; runnable form: the rehearsal's t6_crosscheck.py, 3.1's SCRIPTS)
SELECT count(*) FROM workflow_phases wp
JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id;          -- matched: 529
SELECT count(*) FROM workflow_phases wp
JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id
WHERE wp.uuid IS NULL;                                                                          -- null-uuid, matched rows only: 8
SELECT count(*) FROM workflow_phases wp
JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id
WHERE wp.uuid IS NOT NULL AND wp.uuid <> e.uuid;                                               -- stale: 0
SELECT count(*) FROM workflow_phases wp WHERE NOT EXISTS (
  SELECT 1 FROM entities e WHERE e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id); -- unmatched: 0
-- re-attached: the re-attached SELECT of 2.2 step 6.2, as count(*): 0
-- dropped: the dropped SELECT of 2.2 step 6.2, as count(*): 0

-- events: the four classes by the UPDATEs' own predicates (rekey §5.1) -> 1436, 8, 13, 12
SELECT sum(h = 1), sum(h > 1 AND lbl IS NOT NULL), sum(h > 1 AND lbl IS NULL), sum(h = 0) FROM (
  SELECT (SELECT count(*) FROM entities e WHERE e.type_id = pe.type_id) AS h,
         (SELECT e.uuid FROM entities e JOIN workspaces w ON w.uuid = e.workspace_uuid
           WHERE e.type_id = pe.type_id
             AND (w.project_id_legacy = pe.project_id OR w.uuid = pe.project_id)
             AND pe.project_id <> '__unknown__') AS lbl
  FROM phase_events pe);
```

**If the live file has changed since 2026-09-26** (the user used pd after Phase 1's publish), the table's figures change with it.
- **Then:** the figures the backup gives replace the table's, and the phase report records both, with the cause (rekey §13.3, precondition 5).
- **The stop rule** (PM-CONS-W9): any non-zero dropped (unmappable), stale-uuid or re-attached figure stops the sitting before S6 and goes to the user, with the rows listed from `expect`'s `dropped_rows` and `reattached_rows`.
- **What must stay true either way:**
  - matched + re-attached + unmappable = counted;
  - sole-holder + label-decided + undecided + no-holder = the `phase_events` count;
  - `expect`'s Python classification equals the SQL's four sums.

### 2.6 Verification queries, with their expected results on the live file

**"Pre"** runs on the backup; **"post"** runs on the migrated file; both are opened read-only. The expected values are today's (2.5), which the design's prototype and R2's re-derivation both produced; with a changed file, 2.5's backup figures replace them. The operator tool's `verify` runs all of these. Their runnable form outside the tool is the rehearsal's `q26.py` (3.1's SCRIPTS; REH-S10).

```sql
-- Q-version: post -> ('schema_generation','v2'), ('schema_version','8')
SELECT key, value FROM _metadata WHERE key IN ('schema_generation','schema_version') ORDER BY key;

-- Q-rows-kept: state preserved exactly. Compare the two sets in the verifier (Python):
--   |pre| = |post| = 529, pre - post = post - pre = {}.
-- pre: the matched rows plus the re-attached rows, each keyed by its entity's current
--   (workspace_uuid, type_id); the second SELECT's WHERE is the re-attach copy's (0 rows live):
SELECT e.workspace_uuid, e.type_id, wp.workflow_phase, wp.kanban_column,
       wp.last_completed_phase, wp.mode, wp.backward_transition_reason, wp.updated_at
FROM workflow_phases wp
JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id
UNION ALL
SELECT e.workspace_uuid, e.type_id, wp.workflow_phase, wp.kanban_column,
       wp.last_completed_phase, wp.mode, wp.backward_transition_reason, wp.updated_at
FROM workflow_phases wp JOIN entities e ON e.uuid = wp.uuid
WHERE NOT EXISTS (SELECT 1 FROM entities x
                  WHERE x.workspace_uuid = wp.workspace_uuid AND x.type_id = wp.type_id)
  AND NOT EXISTS (SELECT 1 FROM entities m JOIN workflow_phases w1
                    ON w1.workspace_uuid = m.workspace_uuid AND w1.type_id = m.type_id
                  WHERE m.uuid = e.uuid)
  AND (SELECT count(*) FROM workflow_phases w2 WHERE w2.uuid = wp.uuid) = 1;
-- post:
SELECT e.workspace_uuid, e.type_id, wp.workflow_phase, wp.kanban_column,
       wp.last_completed_phase, wp.mode, wp.backward_transition_reason, wp.updated_at
FROM workflow_phases wp JOIN entities e ON e.uuid = wp.entity_uuid;

-- Q-null-uuid: the matched NULL-uuid rows kept. pre lists 8 pairs, each joining an entity
--   (an orphan NULL-uuid pair, which the migration drops, is not listed); post: each listed pair has a row -> 8
SELECT wp.workspace_uuid, wp.type_id FROM workflow_phases wp
JOIN entities e ON e.workspace_uuid = wp.workspace_uuid AND e.type_id = wp.type_id
WHERE wp.uuid IS NULL;                                                                  -- pre
SELECT count(*) FROM workflow_phases wp JOIN entities e ON e.uuid = wp.entity_uuid
WHERE e.workspace_uuid = ? AND e.type_id = ?;                                           -- post, per pair: 1

-- Q-stale-uuid: pre -> 0 (2.5); post: every stored uuid is now a key -> 521
--   (q26.py binds the pre list in place of the placeholder)
SELECT count(*) FROM workflow_phases WHERE entity_uuid IN (<pre: SELECT uuid FROM workflow_phases WHERE uuid IS NOT NULL>);

-- Q-archive-flags: post -> (0,0,366), (1,0,163)
SELECT e.is_archived, e.is_deleted, count(*) FROM workflow_phases wp
JOIN entities e ON e.uuid = wp.entity_uuid GROUP BY 1, 2 ORDER BY 1, 2;

-- Q-shared: post -> 5 rows, all workspace 69696982-0e18-46f1-acf2-18a3edc6bbb7:
--   brainstorm:20260318-025248-three-claws-v2-protocol, brainstorm:20260326-030832-openclaw-gap-analysis,
--   feature:002-assessed-mode-pipeline-fix, feature:003-oc-config-optimizer,
--   feature:004-rca005-restart-loop-keychain-fix
SELECT e.type_id, e.workspace_uuid FROM workflow_phases wp JOIN entities e ON e.uuid = wp.entity_uuid
WHERE (SELECT count(*) FROM entities x WHERE x.type_id = e.type_id) > 1 ORDER BY 1;

-- Q-unmappable: pre -> 0 (2.5); post: re-attached plus dropped audit rows -> 0
SELECT count(*) FROM migration_audit_log WHERE event_type IN ('rekey_row_reattached', 'rekey_row_dropped');

-- Q-keys -> 529 rows; 0 without an entity; foreign_key_check empty
SELECT count(*) FROM workflow_phases;
SELECT count(*) FROM workflow_phases wp LEFT JOIN entities e ON e.uuid = wp.entity_uuid WHERE e.uuid IS NULL;
PRAGMA foreign_key_check(workflow_phases);

-- Q-attributed -> 1444
SELECT count(*) FROM phase_events WHERE entity_uuid IS NOT NULL;
-- Q-unattributed, by holder count -> {0: 12, 2: 13}
SELECT (SELECT count(*) FROM entities e WHERE e.type_id = pe.type_id) AS holders, count(*)
FROM phase_events pe WHERE entity_uuid IS NULL GROUP BY 1 ORDER BY 1;
-- Q-misattributed -> 0
SELECT count(*) FROM phase_events pe JOIN entities e ON e.uuid = pe.entity_uuid WHERE e.type_id <> pe.type_id;
-- Q-event-count: nothing added or lost -> (1469, 1469, 1469)
SELECT count(*), max(id), (SELECT seq FROM sqlite_sequence WHERE name = 'phase_events') FROM phase_events;
-- Q-event-fk -> empty
PRAGMA foreign_key_check(phase_events);

-- Q-audit: exactly one success row -> migration_version 8; payload: workflow_phases_pre 529, copied 529,
--   reattached 0, dropped 0, stale_uuid 0; phase_events_sole_holder 1436, label_decided 8, unattributed 25;
--   entity_axis_state_rebuilt true
SELECT migration_version, payload FROM migration_audit_log
WHERE event_type = 'success' AND payload LIKE '%"migration": "rekey_workflow_phases"%';
-- Q-audit-rows: the per-row audit rows -> none on the live file
SELECT event_type, count(*) FROM migration_audit_log
WHERE event_type IN ('rekey_row_reattached', 'rekey_row_dropped', 'rekey_stored_uuid_ignored')
  AND payload LIKE '%"migration": "rekey_workflow_phases"%' GROUP BY 1;
```

**Further checks, run by `verify`** (playbook; each has a measured result):

| Check | Expected on today's file | Measured by |
|---|---|---|
| Q-integrity: `PRAGMA integrity_check` | `ok` | R2's re-derivation |
| Q-full-fk: `PRAGMA foreign_key_check` (whole file) | 0 rows | re-derivation; prototype `full_fk_check_count` |
| Q-target: `SELECT type, name, sql FROM sqlite_master WHERE tbl_name IN ('workflow_phases','phase_events')`, whitespace-normalised | equals a fresh file's and a staging file's (`rebuild_tool.build_staging_database`), both built by the same code in a temp dir by `verify` (BUILD-S8), so section 3.7's T9 runs inside `verify`. 12 names: indexes `idx_pe_entity`, `idx_pe_timestamp`, `idx_wp_kanban_column`, `idx_wp_workflow_phase`, `phase_events_backfill_dedup`, `sqlite_autoindex_workflow_phases_1`; tables `phase_events`, `workflow_phases`; triggers `enforce_immutable_pe_entity_uuid`, `enforce_immutable_wp_entity_uuid`, `pe_reject_live_event_without_entity`, `wp_reject_unknown_entity` | prototype files `live-copy.db`, `fresh-v1.db`, `staging-v2.db` |
| Q-views: `entity_axis_state`'s text | `… FROM events WHERE event_type != 'skipped' GROUP BY entity_uuid, axis` (`_VIEWS_DDL`'s), equal to the staging file's | prototype `verify_live_copy.axis_view` |
| Q-others-unchanged: per-table fingerprints of every table whose name is `NOT LIKE 'sqlite_%'` (FTS shadow tables included), except `workflow_phases`, `phase_events`, `migration_audit_log` and `_metadata` | equal the backup's; the apply changed exactly those four, and `sqlite_sequence` as Q-sequence says | re-derivation `tables_changed_by_apply`, which left out the `sqlite_%` tables |
| Q-sequence (R3; PM-LIVE-W2): `sqlite_sequence` against the backup | only `migration_audit_log`'s seq changes, by the number of audit rows written: 1 → 2 | the premortem's `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/premortem/live-data-work/probes/apply_verify.json` (`tables_changed`); the live `sqlite_sequence`, read with `immutable=1` |
| Q-metadata: `_metadata` against the backup | only `schema_version` differs, 7 → 8 | re-derivation `meta` and `post_meta` |
| Q-per-event: every event id's `entity_uuid` against `expect`'s attribution | equal for all 1469 ids | the operator tool (new) |
| Q-v2-join (criterion 6): `SELECT count(*), count(DISTINCT wp.entity_uuid) FROM workflow_phases wp JOIN entity_phase_status s ON s.entity_uuid = wp.entity_uuid` | (529, 529), at most one match per row | measured on the prototype's migrated copy |

### 2.7 Rollback: restore from the backup, and how to confirm it

- **When:** Part 3, section 3.4 decides.
- **How:** the backup API, from the backup opened `immutable=1` onto the live path (rekey §13.4). The operator tool's `restore` runs it, after its refusals (G0, the swap guards, and a backup that is not the old shape; 1.7), closing both connections in a `finally`:
  ```python
  s = sqlite3.connect("file:<backup>?immutable=1", uri=True)
  try:
      d = sqlite3.connect("/Users/terry/.claude/pd/entities/entities.db")
      try:
          s.backup(d)
      finally:
          d.close()
  finally:
      s.close()
  ```
- **Never delete a `-wal` or `-shm` by hand;** use the tool's `checkpoint` (PM-LIVE-W10).
  - **Why that is safe:** the destination connection reads any `-wal` the migrated file left, and then the backup overwrites every page.
  - **If a `-wal` remains** after the connection closes, `restore` runs `PRAGMA wal_checkpoint(TRUNCATE)` on one plain `sqlite3` connection, never `EntityDatabase`, before any check. By hand, the same is `TOOL checkpoint --db LIVE --confirm-live`.
- **Every check opens its own read-only connection** after the restore, and closes it (PM-LIVE-S7). A connection held across the restore reads stale content.
- **Confirmed when all of these hold** (R2's drill, `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/r2/exp/files/rederive.json`, `rollback_*` keys). The tool names its checks after them (REH-S3):
  1. **2.7-1:** `schema_version` is 7, the value `expected.json`'s `version_pre` records, never read from the backup (REH-W1);
  2. **2.7-2:** every table's per-table fingerprint equals the backup's;
  3. **2.7-3:** the full `sqlite_master` text equals the backup's;
  4. **2.7-4:** `PRAGMA integrity_check` is `ok`;
  5. **2.7-5:** no `-wal` remains;
  6. **2.7-6:** the file is page-identical to the backup outside header bytes 24-27, 40-43 and 92-95 (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/design/work/r2/exp/header_diff.txt`: 3 bytes differ, all inside those fields).
- **Not a criterion: sha256 equality.** A backup-API copy never equals its source byte for byte:
  - the backup differs from the live file in 6 header bytes;
  - the restored file differs from the backup in 3 (section 0.2, item 7).
- **Then, on a copy of the restored file, the pre-Phase-R build works:** a read and a write succeed (section 3.7, step T12).

## Part 3. The operator manual (task R4-I)

**The orchestrator runs this only after the user's one yes** (Q5, section 0.4; F3 as amended in section 0.3, item 7). One sitting does all of it: migrate, verify, land and publish.

### 3.1 Names used in this part

- **`MAIN`:** `/Users/terry/projects/pedantic-drip`, the main checkout, on develop.
- **`LIVE`:** `/Users/terry/.claude/pd/entities/entities.db`.
- **`BACKUP`:** `/Users/terry/.claude/pd/entities/entities.db.pre-rekey-<YYYYMMDD>`, beside the earlier `pre-*` backups. Read-only (0444) from step S3 on.
- **`BACKUP_POST`:** `/Users/terry/.claude/pd/entities/entities.db.post-rekey-<YYYYMMDD>`, the copy step S7b takes right after the verification (PM-LIVE-W6). Read-only (0444).
- **`PY`:** `/Users/terry/projects/pedantic-drip/plugins/pd/.venv/bin/python`.
- **`REPORT`:** `/Users/terry/projects/pedantic-drip/agent_sandbox/<date>/release-c-followups-execution/phase-r/sitting/`. Every output below is saved there, by absolute path (REH-S7).
- **`SCRIPTS`:** `$REPORT/scripts/`, where step S1 copies the rehearsal's two scripts (REH-S10):
  - `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/rehearsal/t6_crosscheck.py`: 2.5's SQL. Usage: `t6_crosscheck.py BACKUP`;
  - `q26.py`, beside it: 2.6's SQL. Usage: `q26.py BACKUP MIGRATED`.
- **`SCRATCH`:** a fresh `mktemp -d`.
- **`P`:** the commit at the head of `followups-phase-r`, after its last rebase and integration QA.
- **`D0`:** the commit develop points at when the sitting starts. It is the rollback build.
- **`TOOL`:** `env -u ENTITY_DB_PATH $PY $SCRATCH/apply-clone/scripts/rekey_live_registry.py`, by absolute path. It imports the build of the clone it lives in (1.7).
- **`F0`, `F1`:** the live fingerprints before the apply and after it.

### 3.2 Preconditions (all hold before step S1)

1. **Phase R is ready:** rebased onto develop, it passed its integration QA, G1–G5, F1 as adjusted, and its per-rebase checklist (1.12). It is recorded as `P`.
2. **R3's rehearsal passed** (3.7), and its recorded live fingerprint is in R3's report.
3. **The user said yes** to Q5 (section 0.4): migrate, land and publish, in one sitting.
4. **pd is disabled in every Claude Code session,** the operator's included (rekey §13.3, precondition 4):
   - no settings file that applies enables `pd@pedantic-drip-marketplace` (PM-LIVE-S2): not `/Users/terry/.claude/settings.json` or `settings.local.json`, and not any workspace root's `.claude/settings.json` or `.claude/settings.local.json`. `preflight`'s P4 reads them all;
   - if the user re-enabled pd after Phase 1's publish, the user disables it and restarts every session first. pd's MCP servers hold the file open;
   - `lsof /Users/terry/.claude/pd/entities/entities.db` prints nothing;
   - no pd server process is running (`preflight`'s P3);
   - **the tripwire is a backstop, not the rule** (PM-CONS-W5): until S6, Phase R's build refuses to migrate `LIVE` except through `TOOL apply`. The rule is that nothing but `TOOL` and the prescribed copy command opens `LIVE`.
5. **The live fingerprint** (`stat -f '%m %z'`, and the sha256 prefix) is compared with R3's.
   - **A change since R3** is expected once the user has used pd. It does not stop the sitting: record both fingerprints and the cause, and step S4 re-derives every figure.
   - **A change during the sitting,** after step S3, stops it and goes to the user (rekey §13.3, precondition 5).
6. **The live `schema_version` is 7,** read with `immutable=1`. An 8 means something migrated the file outside this procedure (rekey §13.1): stop, and ask the user.
7. **Develop can fast-forward to `P`:** `git -C $MAIN merge-base --is-ancestor develop P` exits 0.
8. **Record `D0`** (`git -C $MAIN rev-parse develop`), `P`, and `git -C $MAIN status --short` (plan:63).
9. **`MAIN` is on develop** (PM-LIVE-W3): `git -C $MAIN symbolic-ref --short HEAD` prints `develop`. Steps S8 and R6 re-run this check first.
10. **Nothing uncommitted under `plugins/pd`** (PM-LIVE-W7): `git -C $MAIN status --porcelain -- plugins/pd` prints nothing, untracked files included.
11. **The rehearsal's two scripts stay as R3 ran them** (found while applying R3's revision): `t6_crosscheck.py` and `q26.py` in `r3/rehearsal/` keep the pre-revision text the rehearsal report cites. Step S1 copies them to `$SCRIPTS` first, and the orchestrator then brings the copies to 2.5's and 2.6's revised queries: the null-uuid count and pairs over matched rows only, the label predicate, and Q-rows-kept's pre with the re-attached rows.

### 3.3 Steps, with the live fingerprint after each

| Step | What | Command (every path absolute; outputs to `$REPORT`) | Pass when | Live fingerprint after |
|---|---|---|---|---|
| S1 | A scratch clone at `P`, with the main venv, and the two scripts | `git clone $MAIN $SCRATCH/apply-clone`; `git -C $SCRATCH/apply-clone checkout --detach P`; `ln -s $MAIN/plugins/pd/.venv $SCRATCH/apply-clone/plugins/pd/.venv`; `mkdir -p $SCRIPTS`, then copy the two scripts of 3.1 into it, and bring the copies to 2.5's and 2.6's queries (precondition 11) | `git -C $SCRATCH/apply-clone rev-parse HEAD` = `P`; both scripts in `$SCRIPTS` | unchanged |
| S2 | Pre-flight | `TOOL preflight --db LIVE > $REPORT/s2-preflight.json` | `ok`; version 7; row counts recorded | `F0` (equals precondition 5's) |
| S3 | Back up | `TOOL backup --db LIVE --dest BACKUP > $REPORT/s3-backup.json`; then `chmod 0444 BACKUP` (REH-W1) | `ok`: integrity, per-table fingerprints, schema text and page identity, as in 1.7; `BACKUP` is read-only | `F0` |
| S4 | Expected figures | `TOOL expect --backup BACKUP --out $REPORT/expected.json > $REPORT/s4-expect.json`; then `$PY $SCRIPTS/t6_crosscheck.py BACKUP > $REPORT/s4-crosscheck.json` | equal to 2.5's table, or the change is explained by precondition 5's recorded cause; the cross-check agrees. 2.5's stop rule: a non-zero dropped, stale-uuid or re-attached figure stops the sitting here (PM-CONS-W9) | `F0` |
| S5 | Same-minute rehearsal on a copy, with the code about to land (rekey §13.3 step 2) | the prescribed copy command → `$SCRATCH/rehearsal.db`; then `TOOL backup`, `expect`, `apply` and `verify` on it (as 3.7 steps T4–T8), with every output under `$REPORT/s5/`: `backup.db`, `expected.json`, `s5-*.json` (REH-W4); then 3.7 step T13 on it, from `$SCRATCH/apply-clone`; then stop every process S5 started (PM-LIVE-S1); then `TOOL fingerprint --db LIVE > $REPORT/s5-live-fingerprint.json` (REH-S8) | every check passes; `cmp $REPORT/expected.json $REPORT/s5/expected.json` exits 0; the live fingerprint equals `F0` | `F0` |
| S6 | Apply | first `TOOL preflight --db LIVE > $REPORT/s6-preflight.json`, for P2 and P3 again (PM-LIVE-S1); then `TOOL apply --db LIVE --backup BACKUP --confirm-live > $REPORT/s6-apply.json` | preflight `ok`; apply `ok`: version 8, and no `-wal` left (check A4) | `F1`, which is new: record it |
| S7 | Verify | `TOOL verify --db LIVE --backup BACKUP --expected $REPORT/expected.json > $REPORT/s7-verify.json` | `ok`: every check of 2.6 | `F1` |
| S7b | The post-sitting copy (PM-LIVE-W6) | `TOOL backup --db LIVE --dest BACKUP_POST > $REPORT/s7b-backup.json`; then `chmod 0444 BACKUP_POST`. No `-wal` exists then: S6 checked | `ok`, as in S3 | `F1` |
| S8 | Land | re-run precondition 9 first (PM-LIVE-W3); then `git -C $MAIN merge --ff-only P > $REPORT/s8-merge.txt` | develop = `P`; `git -C $MAIN status --short` identical to precondition 8's | `F1` |
| S9 | Record | the phase report, `$REPORT/s9-phase-report.md`: `F0`, `F1`, `BACKUP` and `BACKUP_POST` with their per-table fingerprints, `D0`, `P`, and the outputs of S2–S7b | written | `F1` |
| S10 | Publish | `cd $MAIN && bash plugins/pd/hooks/sync-cache.sh`, with the real HOME. It publishes `$MAIN/plugins/pd` to the `installPath` that `installed_plugins.json` names; today that is `/Users/terry/.claude/plugins/cache/pedantic-drip-marketplace/pd/6.0.0` | the cache's files equal `P`'s `plugins/pd` (PM-LIVE-W7): `mkdir $SCRATCH/p-tree && git -C $MAIN archive P plugins/pd \| tar -x -C $SCRATCH/p-tree`, then `diff -rq -x .venv -x __pycache__ $SCRATCH/p-tree/plugins/pd <installPath> > $REPORT/s10-diff.txt` prints nothing. The script's exit code proves nothing, because its `rsync` ends in `\|\| true` (sync-cache.sh:32) | `F1` (publishing never opens the registry) |
| S11 | Smoke, on a copy, with the published code | the prescribed copy command → `$SCRATCH/smoke.db`; then 3.7 step T13, run from `$MAIN` at `P` | every check passes | `F1` |
| S12 | Hand-off | tell the user the sitting is done. The user re-enables pd in settings, or restarts sessions. The orchestrator never re-enables pd (plan:463) | the user has the message | changes as sessions write. `F1` is the new baseline (section 0.3, item 10) |

**The order, and why** (rekey §13.1–§13.3; section 0.2, item 6):
1. **Migrate and verify before develop moves.** A failure in S6 or S7 then needs only a restore, and develop never holds RK2's code while the file is at version 7.
2. **Take the post-sitting copy (S7b) and land, right after the verification passes,** so develop's code matches the file.
3. **Publish after landing, in the same sitting.** Until the publish, any session's old build (maximum version 7) meets a version-8 file. C23 then denies its writes, and its type_id reads fail loudly (rekey §13.2).
4. **Re-enable pd last,** after the smoke check passes.

### 3.4 Rollback criteria

| Where | What failed | Action |
|---|---|---|
| Preconditions, S1–S5 | any check | Stop. Nothing has been written. Report, and the user decides |
| S4 | a non-zero dropped, stale-uuid or re-attached figure (2.5's stop rule; PM-CONS-W9) | Stop before S6, and go to the user, with the rows listed from `expect`'s `dropped_rows` and `reattached_rows` |
| S3 onward | the live fingerprint differs from `F0` before S6, S5's `s5-live-fingerprint.json` included (REH-S8) | Stop, and go to the user (rekey §13.3, precondition 5) |
| S6 | `apply` passed, but a `-wal` remains (check A4; PM-LIVE-W10) | Find the holder with `lsof LIVE` and stop it. Run `TOOL checkpoint --db LIVE --confirm-live > $REPORT/s6-checkpoint.json`, then go on to S7 |
| S6 | `apply` raised, was killed, or the version is not 8 (PM-LIVE-W10) | If a `-wal` or `-shm` remains and `lsof LIVE` lists nothing, run `TOOL checkpoint --db LIVE --confirm-live` first. Then run `TOOL fingerprint --db LIVE`, and compare its per-table fingerprints with the ones S3 recorded for `BACKUP`. If they are equal and its `schema_version` is 7 (REH-S1), stop with nothing to restore: a retry starts again at S2. Otherwise restore (3.5, steps R1–R4) |
| S7 | any verification | Restore (3.5, steps R1–R4). Develop has not moved, and nothing is published |
| S8 | `MAIN` is not on develop (PM-LIVE-W3) | Stop. Check out develop in `MAIN`, and re-run S8 |
| S8 | develop moved, so `--ff-only` refused | Default: restore (3.5, steps R1–R4). Or, on the user's explicit choice, keep the migrated file while Phase R rebases and re-runs its integration QA; pd stays disabled until S10 |
| S10–S11 | the publish, or the smoke check, failed, and no session has written the file | Stop, with pd still disabled. Offer the user two choices. **Roll forward:** fix, re-run the integration QA, publish; the file stays migrated and nothing is lost. **Roll back:** 3.5, steps R1–R6 |
| After S12 | a defect, found after sessions have written the migrated file | Roll forward: fix the code and publish, keeping the file. A restore would lose those writes, so it happens only on the user's explicit choice, with the changed rows listed for re-entry by 3.5's R2 (rekey §13.4) |

### 3.4a Resuming an interrupted sitting (PM-LIVE-S4)

Resume at the step after the last output `$REPORT` holds:

| The last output in `$REPORT` | Resume at |
|---|---|
| none, or `s2-preflight.json` | S2 |
| `s3-backup.json` | S4 (`BACKUP` exists, 0444) |
| `s4-expect.json` | S5 |
| `s5-live-fingerprint.json`, or `s6-preflight.json` | S6, starting with its preflight |
| `s6-apply.json`, and no `s7-verify.json` | S7, after 3.4's S6 rows if a `-wal` remains |
| `s7-verify.json` | S7b |
| `s7b-backup.json` | S8 |
| `s8-merge.txt` | S9 |
| `s9-phase-report.md` | S10 |
| `s10-diff.txt` | S11 |

- **Any live-fingerprint change** against the last one recorded, before S6, restarts the sitting at S2.

### 3.5 Rollback procedure

**The restore and any republish are one gated live write,** done on the user's yes (rekey §13.4). An S6 or S7 failure inside the sitting is covered by the sitting's yes.

1. **R1: stop every pd process.**
   - the user disables pd and restarts sessions, if any were started;
   - `lsof LIVE` prints nothing;
   - `restore` runs G0 and P2–P4 before it writes, and `r3-restore.json` records them (REH-S2).
2. **R2: record what would be lost.**
   - Fingerprint the migrated file.
   - If it differs from `F1`, sessions have written it. `TOOL diff --db LIVE --ref BACKUP_POST > $REPORT/r2-changed-rows.json` lists the rows changed since the sitting, for re-entry (PM-LIVE-W6).
3. **R3: restore.** `TOOL restore --db LIVE --backup BACKUP --expected $REPORT/expected.json --confirm-live > $REPORT/r3-restore.json`. It runs the backup API as in 2.7, never deletes a `-wal`, and refuses a swapped or migrated backup (REH-W1).
4. **R4: confirm:** `r3-restore.json` shows 2.7's checks 2.7-1 to 2.7-6 passed (REH-S3):
   - version 7, the value `expected.json` records;
   - per-table fingerprints and the `sqlite_master` text equal the backup's;
   - integrity `ok`;
   - no `-wal`;
   - page-identical outside the three header fields.

   Record the restored fingerprint. It is not expected to equal the backup's sha256.
5. **R5: the build must match the file** (rekey §13.4). Only if S10 ran:
   - make a scratch clone at `D0`, and symlink the main venv into it;
   - run `bash plugins/pd/hooks/sync-cache.sh` from that clone, with the real HOME. It publishes the checkout it runs in (sync-cache.sh:11-13);
   - check the cache against the clone's `plugins/pd` with S10's `diff -rq`.
6. **R6: develop must match the file.** Only if S8 ran:
   - re-run precondition 9: `MAIN` is on develop (PM-LIVE-W3);
   - `git -C $MAIN reset --keep D0`. `--keep` leaves the user's uncommitted `README.md` untouched, because no Phase R commit changes it;
   - compare `git -C $MAIN status --short` with precondition 8's;
   - the Phase R commits stay on `followups-phase-r`.
7. **Then:** report to the user. pd stays disabled until the user re-enables it.

### 3.6 After the sitting

- **The new baseline:** `F1` replaces kickoff's fingerprint for F1's and Done-when #4's comparisons (section 0.3, item 10).
- **The backups stay** at `BACKUP` and `BACKUP_POST`, like the earlier `pre-*` backups.
- **F2 runs next.** It was waiting for Phase R's landing (section 0.3, item 6).
- **A session that fails loudly on every workflow call** (rekey §13.2) runs a build older than the file:
  - **one started before the publish:** restart it;
  - **one whose checkout published an older plugin** (PM-LIVE-W4). Cause: `sync-cache.sh` published the checked-out branch's older plugin. Cure: check out develop in the main checkout, run `plugins/pd/hooks/sync-cache.sh`, and restart the sessions. Once Phase R's build is published, R4-E's guard in `sync-cache.sh` refuses such a publish.
- **The marketplace build** at `0b8a05b8` (v2 maximum 3, no C23 guard) is the one an auto-update installs (PM-LIVE-S6). If it is ever active, re-run `sync-cache.sh` from develop.
- **The terry_agent namesakes get their own rows** when terry_agent's entity server first starts: five, plus feature 035's (rekey §5.3). Pedantic-drip's five copies stay as they are unless the user rules otherwise on Q6 (batch 2).
- **The operator tool's fate** is Q7 (batch 2; PM-CONS-S4): deleted with F2's commit (recommended; a later restore then follows 3.5's written steps with plain `sqlite3`), or kept, with its reason recorded in rekey §14.

### 3.7 The R3 rehearsal procedure (the same steps, on copies, with a rollback drill)

**Which build:** R3's own, the playbook's changes (R4-A to R4-H) built on a scratch export of develop after Phase 1 (plan:310). No Phase R code has landed when R3 runs. R3 ran it on 2026-09-26 (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/rehearsal/rehearsal-report.md`), and this revision absorbs its findings. The sitting's step S5 repeats T4–T8 and T13 with the code about to land.

**Environment:**
- all paths are under R3's output directory, `OUT`, and every path below is written out absolutely (REH-S7);
- HOME is a temp dir for every command, except the prescribed copy command, which reads the live file with `immutable=1`. Under a temp HOME, the account's live file is still live to the tool and the tripwire, through the account's home (1.7's live-path test; PM-LIVE-W1);
- `ENTITY_DB_PATH` is unset, except where a step sets it to a copy;
- `TOOL` is R3's build of `scripts/rekey_live_registry.py`, by absolute path;
- `SCRIPTS` is `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/rehearsal/`, which holds the two scripts (3.1).

**What each figure is:** step T5's figures are the migration's own, taken before any server starts.

1. **T1: fingerprint the live file** (`stat`, sha256) and confirm no `-wal` exists. Record it.
2. **T2: copy the live file** with the prescribed copy command to `$OUT/L.db`. The live fingerprint is unchanged.
3. **T3: `TOOL preflight --db $OUT/L.db --settings /Users/terry/.claude/settings.json > $OUT/t3-preflight.json`:** `ok`, version 7. P2 requires that nothing holds `L.db`. P3 and P4 read the real machine and are only reported, since `L.db` is not the live path (1.7). `--settings` is written out absolutely, since `~` expands to the temp HOME (PM-LIVE-S2).
4. **T4: `TOOL backup --db $OUT/L.db --dest $OUT/B.db > $OUT/t4-backup.json`:** `ok`.
5. **T5: `TOOL expect --backup $OUT/B.db --out $OUT/expected.json > $OUT/t5-expect.json`:** the figures equal 2.5's table, or the recorded change.
6. **T6: the independent cross-check.** `$PY $SCRIPTS/t6_crosscheck.py $OUT/B.db > $OUT/t6-crosscheck.json` runs 2.5's SQL read-only: the same four event sums and row figures as T5.
7. **T7: `TOOL apply --db $OUT/L.db --backup $OUT/B.db > $OUT/t7-apply.json`** (no `--confirm-live`: `L.db` is not the live path): version 8.
8. **T8: `TOOL verify --db $OUT/L.db --backup $OUT/B.db --expected $OUT/expected.json > $OUT/t8-verify.json`:** `ok`. Also `$PY $SCRIPTS/q26.py $OUT/B.db $OUT/L.db > $OUT/t8-q26.json` runs 2.6's SQL directly: every expected value.
9. **T9: one target.** `verify` (T8) already checks it, against a fresh and a staging file it builds (2.6's Q-target and Q-views; BUILD-S8): record that result. The hand check, with R3's build: make a fresh v1 file (`EntityDatabase(fresh.db)`) and a staging v2 file (`rebuild_tool.build_staging_database(staging.db)`).
   - The two tables' `sqlite_master` text is identical across `L.db`, `fresh.db` and `staging.db`.
   - `L.db`'s views equal `staging.db`'s.
10. **T10: resumability, on further copies of `B.db`.** Inject the failures by patching the SQL-free seam `_rekey_fault_point(stage)` in a subprocess (PM-CODE-W3), as R3's `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/proto/runs/demo.py` does (its section 8):
    - (a) killed inside the transaction: tables and schema unchanged, and the next open migrates (529 rows);
    - (b) an exception after the copy: rolled back, and `foreign_keys` restored;
    - (c) a crash between `COMMIT` and the stamp: version 7, and the next open changes only `_metadata`;
    - (d) a re-open of a migrated file: no table change, and no new audit row.
11. **T11: an old build on the migrated copy.** From a `git archive` of develop after Phase 1 (the pre-Phase-R build), open a copy of `L.db`:
    - a write is denied (C23: "not authorized"): `add_tag`, or `register_entity` (REH-S5);
    - `get_workflow_phase` fails loudly ("no such column: type_id");
    - the per-table fingerprints are unchanged.
    - **Then the marketplace build** (`git archive 0b8a05b8`: v2 maximum 3, no C23 guard), the one an auto-update installs (PM-LIVE-S6), on another copy of `L.db`: it must fail loudly without writing. Record what it does.
12. **T12: the rollback drill.**
    - `TOOL restore --db $OUT/L.db --backup $OUT/B.db --expected $OUT/expected.json > $OUT/t12-restore.json`. Check every point of 2.7 (2.7-1 to 2.7-6). The sha256 is recorded, not compared.
    - Then the pre-Phase-R build opens a copy of the restored `L.db`. A read (`get_workflow_phase` of `feature:002-assessed-mode-pipeline-fix` in pedantic-drip → `finish`) and a write (an `update_workflow_phase` on a pedantic-drip backlog row) both succeed.
    - Then R3's build opens that copy again and migrates it. It reaches version 8 with the same counts (REH-S6): 529 rows; 1469 events, 1444 attributed and 25 unattributed; archive flags 366/163; one `success` audit row; and the old build's write is visible after the re-migration.
13. **T13: the build serves a migrated copy** (rekey §13.5, step 7). Make a fresh copy `L2.db`, and migrate it as in T7. Start both MCP servers and the UI against it, with a temp HOME and `ENTITY_DB_PATH=L2.db`. Do this twice: pinned to pedantic-drip, then to terry_agent, with `ENTITY_WORKSPACE_UUID` as F1 pins.
    - **The backfill runs first.** Each start's entity server seeds rows for its workspace's row-less entities (W2.6) and reports how many:
      - pedantic-drip: 28 (25 backlog items, and the archived features 035, 112 and 113);
      - terry_agent: 6 (the five namesakes and feature 035, all archived);
      - R2 re-measured both on a migrated copy: `rowless_69696982` and `rowless_f7b49c1d` in `rederive.json`.
    - **The board then shows** 366 + 25 = 391 cards in the `'*'` view, and 529 + 34 = 563 with archived ones (PM-CODE-W7). On a changed file, the backfill's reported counts replace these.
    - **Reads:** `get_phase` for each of the five shared type_ids answers from the pinned workspace's own entity:
      - pinned to pedantic-drip: its rows, for example `feature:002-assessed-mode-pipeline-fix` at `finish`;
      - pinned to terry_agent: its newly seeded rows.
    - **A write:** pinned to terry_agent, `transition_entity_phase` moves `brainstorm:20260318-025248-three-claws-v2-protocol` from `draft` to `reviewing` (router.py:203 allows it). Pedantic-drip's namesake row keeps its per-row fingerprint.
    - **The Python the hooks launch,** each against `L2.db`, pinned the same way. Each exits 0 with no traceback:
      - the session-start orchestrator, as `session-start.sh` runs it (HOOK-1);
      - the doctor with `--fix` (HOOK-2);
      - `pd_state_diff.py` (HOOK-4).
    - **Not run:** HOOK-5 is the UI above, and HOOK-3 reads no registry.
    - **Then stop every process T13 started:** both servers and the UI.
14. **T14: F1's adjusted queries.** On a migrated copy, section 0.3 item 5's step-4 query returns pedantic-drip's 28 row-less entities.
15. **T15: the live fingerprint is unchanged at the end.** If it has changed, find the cause, record it, and tell the orchestrator.

**R3 reports:** every step's output; the T5/T6 agreement; the T12 sha256s, with the header bytes that differ; and any figure that differs from this playbook, with its cause.

## Checklist: each future-proof criterion, and what shows it

The criteria are plan:279-290. Each row names the task that lands the evidence, then the test or the rehearsal step that shows it.

| Criterion | Task | Test (file::name) | Rehearsal or sitting step |
|---|---|---|---|
| **1. One row per entity, enforced by the schema** | R4-C | `test_rekey_schema.py::test_primary_key_is_entity_uuid`, `::test_insert_for_unknown_entity_is_refused`, `::test_row_cannot_move_to_another_entity`; `test_rekey_identity.py::test_two_namesakes_two_rows_and_no_cross_write`, `::test_upsert_writes_own_row_leaves_namesake_unchanged`, `::test_list_workflow_phases_one_row_per_entity_with_entity_uuid`; `test_second_workspace_namesake_activates.py::test_activate_feature_in_second_workspace_seeds_its_own_row` | 3.7 T8 (Q-keys), T13 (a terry_agent namesake gets its own row) |
| **2. Survives every identity change:** rename, re-attribution, reparent, archive, soft delete, shared type_id | R4-C; R4-A for the archive and delete flags | `test_rekey_identity.py::test_row_and_events_survive_type_id_rename`, `::test_row_survives_reattribution[update_entity\|backfill_project_ids\|claim_unknown_entities]`, `::test_update_entity_reattribution_writes_no_workflow_row`, `::test_shared_type_id_rows_are_independent`, keep-green `::test_row_survives_reparent`, `::test_row_survives_archive_round_trip`, `::test_row_survives_soft_delete_round_trip`; `test_rekey_schema.py::test_hard_delete_of_entity_with_row_fails`; `test_rebuild_rekey.py::test_rebuild_maps_entity_uuid_through_the_remint` (the re-mint path); `test_naming_rule.py::test_set_deleted_by_uuid_deletes_only_that_entity`, and keep-green `::test_set_archived_by_uuid_archives_only_that_entity` (1B added the by-uuid branch) | 3.7 T13 (pinned reads and writes on the shared type_ids) |
| **3. No identity copy can drift silently** | R4-C; R4-G | `test_rekey_schema.py::test_no_identity_copy_columns`, `::test_event_entity_is_set_once`; `test_rekey_identity.py::test_row_view_reads_current_identity`; the guard's rule 1 label clause and its event-label check (`test_entity_keyed_access.py`; PM-CONS-S6) | 3.7 T8 (Q-target: no copy column in the migrated schema) |
| **4. No path reaches another workspace's row by type_id** (the API's shape, and a guard) | R4-A, R4-B, R4-C, R4-D, R4-F1 to R4-F4, R4-G | `test_naming_rule.py::test_type_id_resolves_only_in_callers_workspace[...]`, `::test_type_id_without_workspace_raises[...]`, `::test_uuid_resolves_its_entity_whatever_the_workspace[...]`, `::test_refusal_reaches_the_caller[...]`, `::test_set_archived_without_workspace_on_shared_type_id_raises`; `test_engine_reads_in_given_workspace.py`; `test_read_tools_resolve_in_workspace.py`; `test_rekey_event_streams.py::test_mini_spec_of_a_is_invisible_to_b`, `::test_bulk_read_refuses_type_ids`; `test_ui_keyed_by_entity_uuid.py`; `doctor/test_entity_keyed_access.py` (detected sites = declared inventory; `ENTITY_NAMING_METHODS` = the AST scan) | 3.7 T13 (each pinned workspace reads its own namesake; the terry_agent write leaves pedantic-drip's row unchanged) |
| **5. One target schema** (fresh and live); resumable copy-rename with `foreign_key_check`; a live-copy rehearsal and a rollback | R4-C, R4-E, R4-I | `test_rekey_migration.py::test_fresh_and_staging_shapes_identical`, `::test_pre_rekey_v1_and_v2_files_reach_the_same_target`, `::test_migrates_every_row_class`, `::test_audits_reattached_dropped_and_stale_rows`, `::test_event_classes_follow_the_attribution_rules`, `::test_rolls_back_on_injected_failure`, `::test_resumes_after_kill_inside_the_transaction`, `::test_resumes_after_crash_before_stamp`, `::test_reopen_is_a_no_op`, `::test_peer_finished_first_writes_nothing`, `::test_two_runners_on_a_pre_rekey_v2_file_migrate_once`, `::test_live_path_refuses_without_the_operator_flag[...]`, `::test_foreign_keys_restored`, `::test_axis_view_recreated_from_views_ddl`; 4C's race tests with migration 26 registered, with no re-run allowance; `scripts/test_rekey_live_registry.py`, including `checkpoint`, `diff` and the swap refusals | 3.7 T3–T12 (T9 one target, T10 resumability, T12 the rollback drill); the sitting's S2–S7b, and 3.5 if needed |
| **6. Fits the v2 direction** (entity-uuid events and views) | R4-C | `test_rekey_migration.py::test_rows_join_entity_phase_status_one_to_one` | 3.7 T8 (Q-v2-join: 529 of 529 rows join `entity_phase_status` once) |
| **7. Consistent with rev 2.1:** W2.1's call-site contract, W3.4, D5, W1's deletions | R4-B, R4-C, R4-D, R4-F1 to R4-F3, R4-G | feature 129's four cross-workspace tests, with unchanged assertions: only two calls change, to uuids (`test_cross_workspace_matrix.py:230-236` and `:307`; R4-F1's QA probe 3); W2.1's "Explicit workspace" test restated (R4-C); 2C's `test_entity_tools_resolve_in_workspace.py`, unchanged; `test_read_tools_resolve_in_workspace.py::test_uuid_argument_reaches_its_entity_in_any_workspace` (D5); W3's restated tests (R4-C, R4-D); W1's evidence (PM-CONS-W8): 1B's `test_session_start_reads_no_files.py`, `test_get_state_without_hydration.py`, `test_reconcile_status_scoped.py` and `test_update_entity_archived.py`, and 1C's `test_brainstorm_registration_scoped.py` except the skip tests R4-C rewrites, each with unchanged assertions and only workspace or uuid arguments added; a secondary line: the guard's inventory holds no function W1 deletes | 1.12 (integration QA, and F1 as adjusted) |

## R3 revision record (2026-09-26)

- **What it records:** Phase R's step R3, part 3, the one revision. Every disposition in `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/revision/dispositions.json` whose targets include this playbook was applied here, in file order. The design was revised separately, by its own editor.
- **How:** exact-match edit blocks (`/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/revision/playbook-editor/edits-*.txt`), each checked to match the pre-revision text exactly once, then applied in one pass by `apply_playbook_edits.py`. The pre-revision text is `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/revision/playbook-before-r3.md` (1917 lines); the revised body is 2404 lines, before this section.
- **Counts:** 79 dispositions, from 114 findings. 78 target this playbook and are applied; 1 is not.
- **Lines:** this file's lines, as revised. A range is the whole edited block that carries the change; a block that carries several dispositions appears under each.

**Applied**

| Id | Verdict | Change | Lines |
|---|---|---|---|
| PM-CONS-W2 | accept | Phase 1 as landed (1A, 1B, 1C) in the header and 1.2's drift check; R4-A restates `check_workflow_drift`'s docstring; R4-B scopes MCPE-10's `resolve_ref`; R4-C restates `reconcile_status`'s docstring; R4-H's code-comment grep (step 5); 1.13 names 1B's and 1C's test files | 12-17, 277-283, 348-352, 373, 537-538, 556-570, 576, 702-718, 794-798, 887-900, 1610-1611, 1636-1642, 1653, 1726-1736 |
| PM-CODE-W10 | accept-modified | anchors re-derived at `ddc299a0` = `c1bbfae0`'s code; R4-A's first checks expect 1B's re-keyed rows and verify 1C's `entity_status.py` code | 12-17, 109-157, 277-283, 328-338, 348-352, 365, 373, 376, 381-395, 402, 408, 413, 549-570, 781-783, 787-788, 794-798, 1745, 1756-1760 |
| PM-CONS-W3 | already-handled | 0.4's Q5: while the sitting is deferred, brainstorms another workspace holds stay unregistered and named in the warnings | 159-208 |
| BUILD-S7 | accept | 2.2 step 6.4: the CHECK lists hold the live DDL's allowed values, compared as sets | 913-932, 1830-1831 |
| BUILD-S2 | accept | 2.3: `migration_version` is the chain generation when the migration ran; staging and fresh files record 26; R4-C's shape test asserts it | 913-932, 1981 |
| BUILD-S3 | accept | 2.2: step 5 only when the `workflow_phases` part is pending; step 9 only for tables that exist | 1788, 1959 |
| BLAST-B1 | already-handled | R4-C waits for 4C or carries its five-point contract (1.1, 1.5 change 0); no re-run allowance in any gate (1.2); the v2-chain race test; 2.1 notes the serialized runner (:11078, :11191) | 109-157, 214-262, 302, 702-718, 726-774, 913-932, 1007-1014, 1026-1029, 1034-1036, 1756-1760, 2402 |
| PM-LIVE-W9 | accept | Q-rows-kept's pre is the matched plus the re-attached rows under the entity's current pair (2.6; `expect` in 1.7) | 1187-1219, 2028-2049, 2068-2101 |
| BUILD-W1 | accept | the null-uuid count and Q-null-uuid cover matched rows only (2.5, 2.6; `expect` in 1.7) | 1187-1219, 2028-2049, 2068-2101 |
| PM-LIVE-W8 | accept-modified | the label-decided predicate also matches a workspace-uuid label and never `'__unknown__'` (2.2 step 7, 2.5, the tool's classifier); a test case for each | 913-932, 1149-1168, 1248-1271, 1912-1926, 2028-2049 |
| PM-CODE-B1 | accept | the uuid test covers 15 pairs (5 red, 10 keep-green) with its exclusions; R4-C adds three pairs; checklist row 4 drops "keep-green" | 434-438, 507-510, 960-961, 2401 |
| PM-CODE-W1 | accept-modified | `WorkspaceRequiredError`, re-raised everywhere; the swallowing callers converted, with `test_refusal_reaches_the_caller` (R4-F4); `match=` on the 16 `pytest.raises` blocks (the slices); R4-D answers its 404 by its own cookie check | 1063-1065, 1320-1514, 2401 |
| PM-CODE-S4 | accept-modified | the pinned refusal message names its parameter (1.8.4, change 1) | 1432-1514 |
| BLAST-S4 | accept | `query_phase_events_bulk` refuses a non-uuid element, with `test_bulk_read_refuses_type_ids` (R4-C); checklist row 4 | 792, 949-954, 2401 |
| PM-CODE-W8 | accept | label-only calls count as unscoped (R4-A and R4-B QA); NULL-legacy workspace fixtures; R4-F4's QA expects 0 label-only stragglers | 381-395, 424, 501-502, 556-570, 581, 620-621 |
| PM-CODE-W7 | accept | the UI's three cookie states; a type_id URL resolves only under a uuid cookie; R4-D's tests and QA figures (240/397, 366); T13's `'*'` view (391/563) | 1063-1065, 1093-1096, 1109-1115, 1120, 2376 |
| PM-CONS-S1 | accept | 0.4's Q2 carries the strict rule's lasting costs; every "user item" reference is now a Q-number | 159-208, 1302-1318, 1432-1500, 1519-1522, 1661-1665, 1671-1684, 2192, 2213-2230 |
| PM-CONS-S2 | accept | 0.4 asks in two batches; Q1 (hold the sitting this round) gates R4's start (1.1) | 159-208, 214-262, 328-338, 519-527, 537-538, 549-555, 596, 606-607, 620-621 |
| PM-CONS-W6 | accept | 0.4's Q6 (no change, archive, or merge the five namesakes) replaces item 3; 3.6 cites it | 109-208, 2323-2331 |
| PM-CONS-W7 | accept | merge-entities: delete recommended (Q4); R4-E deletes it on that answer; R4-G's declared entries and high-water mark follow; 1.13 moves SCR-7 | 159-208, 1122-1147, 1273-1285, 1519-1522, 1530-1565, 1688-1710, 1722, 1726-1736 |
| PM-LIVE-W5 | accept | R4-C's rebuild refusal message names the operator tool, and its test asserts it | 806, 969 |
| PM-CONS-W8 | accept | 1B's and 1C's test files get workspace or uuid arguments only, assertions unchanged (1.8.0, 1.13); checklist row 7's evidence | 1320-1430, 1726-1736, 2404 |
| PM-CODE-B2 | accept | feature 129's two calls (`test_cross_workspace_matrix.py:230-236` and `:307`) go to R4-F1, with QA probe 3; checklist row 7 | 1320-1500, 2404 |
| PM-CODE-W2 | accept | R4-G's widened matching (five rules), the premortem's evasions as scanner self-tests, and the guard's stated limits | 1530-1565, 1574-1576 |
| PM-CODE-W3 | accept | the migration's SQL stays inside its one function; tests and T10 inject failures through the SQL-free seam `_rekey_fault_point(stage)` (1.5 change 2, 3.7) | 743-774, 913-932, 2357 |
| PM-CONS-W5 | accept-modified | a temp HOME for every agent command, and the live file's state recorded before and after (1.2); the migration's live-path tripwire (1.5 change 2, 2.2 step 1b, tests); precondition 4's backstop line | 19-21, 159-208, 267-270, 291-300, 726-774, 913-932, 1026-1029, 1034-1036, 1149-1168, 1220-1246, 1774-1776, 2213-2230, 2402 |
| PM-LIVE-W4 | accept | R4-E adds the `sync-cache.sh` guard, its hook test and G4; 3.6 gives the republish cause and cure | 109-157, 214-262, 1122-1147, 1248-1300, 2323-2331 |
| PM-LIVE-W6 | accept-modified | step S7b takes `BACKUP_POST`; R4-E's `diff` subcommand and test; 3.5's R2 lists changed rows with `TOOL diff` | 1220-1271, 1287-1300, 2196-2209, 2234-2248, 2252, 2258-2269, 2294-2307, 2323-2331, 2402 |
| BUILD-W2 | accept | R4-C owns `TestMigration6`'s three row assertions whatever 4B does (first check, change 14, G5's base of 7 failures); 4B is no prerequisite (1.1, 1.12, 1.13) | 214-262, 702-718, 726-741, 815-823, 832, 990-998, 1007-1014, 1671-1684, 1722, 1726-1736 |
| PM-CONS-S4 | accept | Q7 decides the operator tool's fate after the sitting (0.4, 1.7, 3.6) | 109-208, 1122-1147, 2323-2331 |
| PM-CONS-W1 | accept | 0.3 split: items 1-8 on develop now, items 9-10 in the sitting's commit; the Done-when deferral clauses | 109-157, 2192, 2234-2248, 2323-2331 |
| PM-CONS-S7 | accept | every plan citation re-anchored to `c1bbfae0` (`plan-anchor-map.txt`); 0.3's F1 notes (steps 1-3 hold; plan:427) | 3-6, 9, 12-17, 25, 29-30, 37-44, 64, 109-157, 214-262, 267-270, 277-283, 288, 291-302, 606-607, 1149-1168, 1610-1611, 1671-1684, 2213-2230, 2234-2248, 2335-2342, 2394 |
| PM-CONS-S8 | accept-modified | 0.3 item 2: a phase rebasing after Phase R adopts its naming rule and row view | 109-157 |
| PM-LIVE-S5 | accept | 0.3 item 5's step-4 query adds `e.is_deleted = 0`, with the backfill's anchors | 109-157 |
| PM-CODE-W11 | accept-modified | new task R4-C0 (1.4a) moves the tests' raw SQL behind shape-aware helpers; R4-C's raw-SQL list moves there; 1.1 and 1.13 updated | 19-21, 103-107, 214-262, 302, 519-527, 626-693, 702-718, 726-741, 887-900, 980, 1007-1014, 1688-1710, 1726-1736 |
| PM-CODE-S3 | accept-modified | R4-F3 waits for 4A (1.1, 0.3 item 4, 1.8.3) | 109-157, 214-262, 1302-1318, 1358-1430 |
| PM-CODE-S2 | accept | every sandbox path is absolute; 1.2 says the scripts run from the main checkout's sandbox | 84-85, 88, 267-270, 743-774, 887-900, 987, 1026-1029, 1051, 1055, 1287-1300, 1320-1356, 1618, 1688-1710, 2012, 2162-2184, 2357 |
| PM-CODE-W6 | accept | `set_archived` by uuid is keep-green; a new red test for `set_deleted` by uuid; checklist row 2 | 348-352, 365, 444-448, 498, 2399 |
| BLAST-B3 | accept | R4-A rewrites one `test_c11` test and deletes two, and its files add both test files; "everything else stays green" qualified | 328-338, 483-486, 489 |
| PM-CODE-W9 | accept-modified | R4-A's CLI changes: `frontmatter_sync_cli.py`, the read-only resolver, `backfill_headers` scoped, `cleanup_backlog`'s lookup order, `entity_status.py` verify-only; their tests and QA | 328-338, 381-395, 455-472, 501-502, 507-510, 1026-1029 |
| BLAST-W2 | accept | `_process_export_lineage_markdown` gains a workspace parameter (R4-A); the export tool passes it and R4-B's files add `server_helpers.py`; synth-2's note (1.13) | 381-395, 519-527, 556-570, 576, 587-590, 1726-1736 |
| BLAST-B2 | accept | R4-C deletes 1C's skip (`_another_workspace_holds`) and rewrites its skip tests; R4-F4's change 5 names `resolve_ref` as the prefix search's only caller; 1.13 | 381-395, 408, 702-718, 726-741, 815-823, 877, 887-900, 990-998, 1432-1500, 1726-1736 |
| BLAST-W1 | accept | R4-C rewrites the four workspace-mismatch tests, and its anchors move to :10169-10188 | 702-718, 781-783, 990-998 |
| BUILD-W3 | accept | R4-C's class seeding writes raw SQL, not `register_entity` | 743-774 |
| BUILD-S4 | accept | `make_pre_rekey_db(..., stale_axis_view=True)`; R4-C's migration test and R4-E's tool test for `entity_axis_state_rebuilt` | 743-774, 913-932, 1248-1271 |
| BUILD-S6 | accept | R4-C rewrites `test_migration_14_safety.py`'s fixture, which builds at `max(MIGRATIONS)` | 702-718, 856, 990-998 |
| PM-CODE-W5 | accept | R4-C's migration tests first assert a fact only the migration makes true; the fault seam; the event-stream tests seed a namesake with its own events | 913-932, 949-954, 2401-2402 |
| PM-CODE-S1 | already-handled | R4-C adds the two-runner v2-chain test beside the in-process peer test; checklist row 5 | 913-932, 1007-1014, 2402 |
| BLAST-S1 | accept | R4-C's gates name the 16 rebuild-structure tests and the deleted scripts' tests | 1007-1014 |
| PM-LIVE-W1 | accept | the live-path test's two forms (HOME, and the account's home), shared by the tool and the tripwire; tests and QA; 3.7's environment | 1149-1186, 1248-1271, 1287-1300, 2335-2342 |
| PM-LIVE-W2 | accept | fingerprints cover tables `NOT LIKE 'sqlite_%'`; `sqlite_sequence` checked on its own (1 to 2); 2.6's Q-others-unchanged and new Q-sequence | 29-30, 1149-1168, 1220-1246, 2151-2155 |
| PM-LIVE-S2 | accept | P4 reads the user's and every workspace root's settings files (1.7, 2.4, precondition 4); T3 passes `--settings` absolutely | 1170-1186, 1248-1271, 2001, 2213-2230, 2346-2353 |
| PM-LIVE-S7 | accept | every check opens its own read-only connection, none spans `apply` or `restore`, and the checkpoint uses plain `sqlite3` (1.7, 2.7) | 1149-1168, 1220-1246, 2162-2184 |
| BUILD-S5 | accept | the guard preview runs from a copy (R4-C's and R4-E's QA probes) | 1026-1029, 1287-1300 |
| BUILD-S8 | accept | R4-E's contract pins P5 from the backup, the exit codes, the table set, `expect`'s keys, and `verify`'s staging comparison (T9 runs inside `verify`) | 1122-1168, 1187-1246, 2151-2155, 2354 |
| REH-W1 | accept | `chmod 0444` on the backups; `apply` and `restore` refuse a swapped or live backup; `restore` needs an old-shape backup and checks version 7 from `expected.json` | 1149-1168, 1220-1271, 1287-1300, 2162-2184, 2196-2209, 2234-2248, 2294-2307, 2368-2370, 2402 |
| REH-W4 | accept | `expect` writes no path; S5 writes under `$REPORT/s5/` and compares with `cmp` | 1187-1219, 1248-1271, 2234-2248 |
| REH-S1 | accept | `fingerprint` reports `schema_generation` and `schema_version`; 3.4's S6 row uses it | 1149-1186, 2258-2269 |
| REH-S3 | accept | `restore`'s checks are named 2.7-1 to 2.7-6 (1.7, 2.7, 3.5) | 1220-1246, 2162-2184, 2294-2307, 2368-2370 |
| REH-S9 | accept | `backup` and `restore` close both connections in a `finally` (1.7, 2.7) | 1149-1168, 1187-1219, 2162-2184 |
| PM-CODE-W4 | accept-modified | R4-F becomes R4-F1 to R4-F4 with a sizing rule; entry-point tables in R4-A and R4-B; the record-only census replaces the 20-edit sample; figures re-measured at `ddc299a0`; every task reference updated | 19-21, 50-51, 62, 70, 76, 103-107, 159-208, 214-262, 328-338, 360, 421, 424, 496, 507-510, 556-570, 1026-1029, 1042, 1122-1147, 1302-1514, 1519-1522, 1568, 1582, 1608, 1688-1710, 1726-1736, 2401, 2404 |
| BLAST-S2 | accept | R4-F1's files add `test_c5b_parse_backlog_workspace.py` (G2) | 1358-1430 |
| PM-CONS-W4 | accept-modified | 1.12's per-rebase checklist; 0.3 item 3's shared files; precondition 1 | 109-157, 214-262, 1661-1665, 1671-1684, 2213-2230 |
| PM-LIVE-S3 | accept | 2.2's dropped SELECT is a NOT EXISTS against the whole re-attach predicate (the export's form, see below); 2.5 counts it | 1812-1822, 2028-2049 |
| PM-LIVE-W3 | accept | precondition 9 (MAIN on develop), re-run at S8 and R6; 3.4's S8 row split in two | 2213-2230, 2234-2248, 2258-2269, 2314-2316 |
| PM-LIVE-W7 | accept | precondition 10 (nothing uncommitted under `plugins/pd`); S10 compares the cache with `git archive P` | 2213-2230, 2234-2248 |
| PM-CONS-W9 | accept-modified | 2.5's stop rule on any non-zero dropped, stale-uuid or re-attached figure; S4 and a 3.4 row | 2052-2055, 2234-2248, 2258-2269 |
| PM-LIVE-S1 | accept | S5 stops the processes it started; S6 re-runs `preflight` first; T13 ends by stopping its processes | 2234-2248, 2385-2386 |
| REH-S8 | accept | S5 ends with the live fingerprint, compared with `F0`; 3.4's row | 2234-2248, 2258-2269 |
| PM-LIVE-W10 | accept-modified | `apply` fails when a `-wal` remains (A4); the `checkpoint` subcommand and its test; 3.4's two S6 rows; 2.7 names `checkpoint` | 1220-1271, 1287-1300, 2162-2184, 2234-2248, 2258-2269, 2402 |
| PM-LIVE-S4 | accept | new section 3.4a: where to resume an interrupted sitting | 2271-2290 |
| REH-S2 | accept | 3.5's R1 relies on `restore`'s own G0 and P2-P4 results | 2294-2307 |
| PM-LIVE-S6 | accept | 3.6 names the marketplace build `0b8a05b8`; T11 runs it on a copy | 2323-2331, 2362-2366 |
| REH-S5 | accept | T11's write is `add_tag` or `register_entity` | 2362-2366 |
| REH-S6 | accept | T12 names the counts the re-migration must reach | 2368-2370 |
| REH-S7 | accept | every path in S2-S7b and T3-T8 is absolute, and every output is saved | 2196-2209, 2234-2248, 2335-2342, 2346-2353, 2368-2370 |
| REH-S10 | accept-modified | the rehearsal's two scripts, copied by S1 into `SCRIPTS` and run at S4, T6 and T8; 2.5 and 2.6 point to them; their SQL stays out of the tool | 1149-1168, 2028-2049, 2062, 2068-2101, 2196-2209, 2213-2230, 2234-2248, 2335-2342, 2346-2353 |
| PM-CONS-S6 | accept-modified | the re-attribution test covers three writers; checklist row 2 adds the rebuild re-mint test; R4-G's event-label check (self-test, QA probe 5, row 3) | 940-943, 1538-1565, 1574-1576, 1594-1595, 2399-2400 |

**Not applied**

| Id | Verdict | Reason |
|---|---|---|
| PM-CONS-S3 | accept | no playbook target: it aligns the design's §11 and §15 with this playbook's 1.9 "Later changes" and 1.12, which already say it |

**Found while applying**

1. **The dropped SELECT** (PM-LIVE-S3). The disposition's literal `NOT EXISTS (SELECT 1 FROM entities e WHERE e.uuid = wp.uuid)` leaves out two of the re-attach conditions, so a row whose stored uuid names an entity that fails them would fall in neither class. 2.2 uses R3's export's form, a NOT EXISTS against the whole re-attach predicate. The design's editor should check §5.1 against it.
2. **Rule 5's widened pattern meets `refuse_deleted_or_cross_workspace_parent.child_ref`** (database.py:8054; PM-CODE-W2). The parameter is a message label (:8079), so the AST scan finds 21 pairs where `ENTITY_NAMING_METHODS` has 20, and the guard would fail. R4-G's first check 3 excludes such a match by name, with its reason, or escalates. The design's §11 states the same pattern.
3. **The rehearsal's two scripts carry the pre-revision SQL** (REH-S10): `t6_crosscheck.py`'s null-uuid count and label predicate, and `q26.py`'s Q-rows-kept pre and null pairs. Precondition 11 has S1 copy them to `$SCRIPTS` first, and the orchestrator update the copies.
4. **R4-D's 404 test needs a second fixture** (PM-CODE-W7). With the shared type_id alone it is green on the base, where an unscoped read of a shared type_id already answers None. The test adds a type_id one workspace holds.
5. **`test_c11_feature_paths.py` lives in `workflow_engine`** (BLAST-B3 names no directory). R4-A cites the path.
6. **R4-F3 also takes 1B's `test_update_entity_archived.py`,** by tree (mcp). The re-slicing table names only `test_reconcile_status_scoped.py` there.
7. **The row fingerprint's anchor is plan:416-421,** from the anchor map, not PM-CONS-S7's :417-421.
8. **reconciliation.py's anchors** at `c1bbfae0`: :189, :210, :577 and :580, and `check_workflow_drift`'s docstring at :555-563.
9. **Relative evidence paths in section 0.2, item 7** are absolute too (PM-CODE-S2's sweep).
10. **Re-read on 2026-09-26** (read-only, `immutable=1`): P4's settings, where only `/Users/terry/.claude/settings.json` names pd (`false`) among the account's and the 21 workspace roots' files; `sqlite_sequence` (`migration_audit_log` 1, `phase_events` 1469); the live fingerprint, still `1790286038 4083712`.

**Checker gaps (applied after the completeness check)**

- **Source:** `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-26/rekey/r3/revision/check-report.md`: 0 blockers, 3 warnings (W1–W3) and 6 suggestions (S1–S6).
- **Method:** 22 exact-match replacements here (13 in the design), each checked to match exactly once (`/private/tmp/claude-501/-Users-terry-projects-pedantic-drip/27cf8870-ad10-4a78-9c82-03da65e2304a/scratchpad/r3-gaps/apply_gap_edits.py`). No edit changed a line count, so the line numbers above still hold.

| Gap | Change | Lines |
|---|---|---|
| W1 | The header's anchor rule is the design's: every file:line citation is at `c1bbfae0`, except those that name their commit; "Before you edit" step 1 says the same. R4-A's nine engine numbers take the design's `c1bbfae0` lines, each checked with `git show c1bbfae0:<path>`: feature_paths.py:70, :113; engine.py:394, :149, :259, :256, :262, :531 and :93-120. | 14, 277, 367, 376-377, 380 |
| W2 | None to Part 3: the design's 13.3 now runs apply, verify, land, publish, as S6 to S10 do. Swept: section 0.2, item 6 now gives the land-first order as the design's before R3's revision, and says the revised design runs this playbook's order. | 79, 81 |
| W3 | None here: the design's 404 test now takes R4-D's second fixture (found-while-applying note 4). | none |
| S1 | Question pointers follow the design's two lists: "(rekey §9, Q2)" for the strict rule, and "open question N" for the table of 27. Swept: the seven other "question N" pointers, for the same wording. | 185, 349, 625, 936; 99, 280, 738, 750, 981, 1001, 1091 |
| S2 | None here (the design's R4-F4 row). | none |
| S3 | None here (the design's R4-F3 row). | none |
| S4 | None here: 1.12 already greps `.get('uuid')`, and the design now does too. | none |
| S5 | None here (the design's code-comment grep hits). | none |
| S6 | Precondition 11 keeps R3's two scripts as the rehearsal report cites them: S1 copies them to `$SCRIPTS` first, and the orchestrator brings the copies to 2.5's and 2.6's queries. Swept: S1's row, and found-while-applying note 3. | 2230; 2236, 2506 |
