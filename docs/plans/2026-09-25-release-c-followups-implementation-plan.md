# Release C follow-ups: implementation plan (from design rev 2.1)

- **Status:** plan rev 2.
  - Rev 1 went through an independent plan review (not approved: 3 blockers, 12 warnings) and calvin in report mode (73 questions).
  - Rev 2 resolves both. Calvin's ledger, with the author's answers, closes this file.
- **Design:** `docs/plans/2026-09-25-release-c-followups-design.md`, rev 2.1.
  - **What binds:** the design's contracts (W1–W5, each change numbered) and this plan's steps. When the two disagree, the design binds. The implementer stops and records the conflict in the task report, and the orchestrator amends one of them before the task merges.
  - **How steps cite it:** by change, for example "W2.1" for W2 change 1. This plan does not restate a contract; where it adds something, it says why.
- **Names:**
  - tasks are 1A–4B, and phases are Phase 1–4;
  - P0, P1 and P2 are only the design's priorities.

## Problem, and how to tell it is solved

Each problem in the design's two triage tables is closed when the check named for it passes:
1. **No session start writes the registry from files**, except brainstorm registration from a tracked `.prd.md`, which W1.1 keeps. Checks:
   - fresh worktree or clone, or any checkout with no `.meta.json`: W1's "No archive" test, and F1 step 2;
   - an old checkout with stale `.meta.json`: W1's "No regression" test;
   - another workspace's namesake checkout: W1's "No namesake row" test, and F1 step 3.
2. **A new feature works from allocation through its first phase transition** (`specify` for deep, `implement` for express), on the deep, express and decomposed paths. That transition is where N1 broke. Checks: W2's lane tests, and F1 step 5.
3. **No `workflow_phases` insert guesses a workspace.** Every insert stores the resolved entity's `workspace_uuid` and `uuid`. Checks: W2.1's "Explicit workspace" and "Upsert refuses" tests, and F1 step 4.
   - **Deferred by design (D3):** the type_id-only *updates*.
4. **No MCP tool writes into `__unknown__`.** Every tool that writes with a workspace resolves one or refuses. Checks: W4.1's tests.
   - **Deferred by design:** the library's own `__unknown__` defaults.
5. **A nested worktree roots at itself, archives nothing, and publishes nothing.** Checks: W4's "Root detection", "No archive from a worktree root" and "sync-cache" tests, run after Phase 1.
6. **Every other change passes the test or grep check the design names for it.** That covers W3's board and links, W4.3's relabel, and W5's deletions and docs.

## Roles and locations

- **The orchestrator** runs the plan. It never implements a task, so every review and QA stays independent of the implementer. It:
  - cuts branches;
  - dispatches the implementer, reviewer and QA agents;
  - merges task branches into phase branches;
  - runs F1–F3;
  - fast-forwards develop.
- **Kickoff**, before Phase 1:
  1. Commit this plan and the design to develop, so every branch carries them.
  2. Ask the user, through AskUserQuestion, to rule on D1, D3 and D5. D1 decides Phase 1's task 1B, and D3 and D5 decide Phase 2's.
     - **A ruling that differs from a default:** the affected tasks are re-planned before they start.
     - **The concurrency cap:** confirm it in the same question.
  3. Take the live registry's first fingerprint (`stat -f '%m %z'` and a sha256 prefix). F1, F2 and Done-when #4 compare against it.
- **Evidence and reports** live in the main checkout's gitignored `agent_sandbox/`, by absolute path. A task worktree's own `agent_sandbox/` is deleted with the worktree.
  - **Evidence:** `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-25/release-c-followups/`.
  - **Reports:** `/Users/terry/projects/pedantic-drip/agent_sandbox/<date>/release-c-followups-execution/`, with one directory per phase and one per task. The task report holds:
    - the red-first output;
    - the deletion and rewrite lists;
    - anchor corrections;
    - gate counts.
- **The interpreter** is always the main checkout's `/Users/terry/projects/pedantic-drip/plugins/pd/.venv/bin/python`, run from the root of the checkout under test.
  - **Why:** `plugins/pd/.venv` is gitignored, so task worktrees don't have it.
  - **Imports:** they resolve from the checkout under test, because the venv holds no editable install.
- **Develop** is checked out in the main checkout, which holds the user's uncommitted `README.md` and untracked `docs/workflow-*` and `.codegraph/`.
  - **Fast-forwards:** `git merge --ff-only` there.
  - **Why that's safe:** no task commits `README.md` or any path the user has untracked (D4), so the fast-forward touches neither.
  - **Check:** the orchestrator compares `git status --short` before and after.

## Branches, merges and landing

- **Branches:**
  - one phase branch, `followups-phase-<n>`, cut from develop when the phases it depends on have landed;
  - one task branch per task, `followups-<task>`, in `.pd-worktrees/followups-<task>`, cut from its phase branch;
  - a task that depends on another in its phase (1B on 1A, 2C on 2A) is cut from the phase branch after that task merges.
- **A task's base** is the commit its branch is cut from. Red-first runs and gate comparisons use that base.
- **Anchors:** before editing, re-verify every file:line anchor on the task branch; the anchors here are from develop `84fc9376`.
  - **Moved:** find the symbol by name (codegraph), and record old → new in the task report.
  - **Gone or changed in meaning:** stop and escalate to the orchestrator.
- **Landing:** Phases 2, 3 and 4 run side by side after Phase 1, and land in whatever order they finish.
  - **Rebase rule:** a phase that finds develop has moved rebases onto develop, re-runs its integration QA (all gates), then fast-forwards.
  - **Shared files:** the phases share some files, in separate hunks:
    - `database.py` (2B edits `list_workflow_phases` and the writers; 4A edits a docstring);
    - `hooks/tests/test-worktree-dispatch.sh` (3A at `:86`, `:132`; 4A at `:48-49`).

    A rebase conflict goes back to the phase's implementer, then through the phase's QA.

## Review protocol

1. **Per task:**
   1. one implementer;
   2. an independent review;
   3. a fix round, only if the review has findings, and at most one;
   4. an independent QA that re-runs the task's red-first tests and all gates.
2. **QA findings:** at most one fix round, then QA re-runs once. No confirmatory re-run follows a clean pass.
3. **Per phase,** after its tasks merge: an independent integration review and QA, then at most one fix round and one QA re-run, as in step 2.
4. **Escalation:** a blocker still open after its fix round goes to the user.
   - **While it waits:** tasks that don't depend on it continue, and its phase does not land.
5. **Concurrency:** at most 6 agents at a time (implementers, reviewers and QA together).
   - **Where 6 comes from:** the user's setting for Release C's execution. For this orchestration it overrides `.claude/pd.local.md`'s `max_concurrent_agents: 5`, which governs pd's own skills.
   - **Confirmed** at kickoff.
6. **Red-first:** every new test the design names is written first and run on the task's base, and the red output goes in the task report. A test that passes there is vacuous unless the design marks it keep-green, and the reviewer rejects it.
7. **Deleting a test:**
   - **Allowed only when** it exercises a symbol or behaviour a design change deletes. The task report lists each deleted test with that change (for example "W1.3: `apply_workflow_reconciliation`").
   - **Any other failure is a breakage,** to fix, not delete.
   - **The checklist:** the prototypes' classifications (`design-review/verify-p0/verdict.md` "Failure classification", `design-review/verify-rest/verdict.md` "Failure classification"). A failure outside them is investigated before it is classified.
   - **The reviewer checks** every listed deletion against its cited change.

## Safety, for every agent

- **The live registry** is never written.
  - **Reading it:** only as `file:<path>?immutable=1` (uri=True), or `mode=ro` when a `-wal` exists.
  - **A copy** is made only this way:
    ```
    python -c "import sqlite3,sys; s=sqlite3.connect('file:/Users/terry/.claude/pd/entities/entities.db?immutable=1',uri=True); d=sqlite3.connect(sys.argv[1]); s.backup(d)" <dest>
    ```
    The `sqlite3` shell's `.backup` opens the live file read-write.
- **The real HOME:** no script runs with it that can publish or write `~/.claude`. `test-hooks.sh`, `validate.sh` and `sync-cache.sh` run only as G3 and G4 say.
- **The main checkout:** leave `README.md` and the untracked files alone.
- **Another project's checkout** (`/Users/terry_agent`, fractorg, cast-below, illium) is read, never written.
- **Git:**
  - no `git add -A`;
  - no bare `git stash`;
  - merges go to develop, never main;
  - commits end with the co-author line.

## Phase 1 (P0): the checkout's files stop writing the registry, and features work end to end

**Why it matters:** it must land before the pd plugin is re-enabled.
- The plugin has been disabled since 2026-09-24, so nothing breaks while it stays off.
- Re-enabled without Phase 1, session starts archive and regress features, and `/pd:create-feature` fails at its first phase step.

**Order:** 1A, then 1B cut from the phase branch after 1A merges.
- **Shared files:** both edit `workflow_state_server.py` and the engine. `backfill.py` is 1A's only.
- **What 1A's tests must not rely on:** anything 1B deletes: hydration, Task 2 or the reconcile tools.
  - **The lane tests** assert the seeded row right after `activate_feature`, before any engine read (design W2 tests).
  - **1A's QA** runs its new tests once more, with `WorkflowStateEngine._hydrate_from_meta_json` patched to raise.

**1A: row writers, name-not-path, activation and backfill** (W2.1–W2.7).
1. **Row writers** (W2.1): `create_workflow_phase` and `upsert_workflow_phase` in `database.py`, and the callers that survive Phase 1:
   - `feature_lifecycle.py:305`;
   - `task_promotion.py:403`;
   - activation;
   - the backfill.

   `engine.py:633` (hydration) and `reconciliation.py:495` are left for 1B to delete. Until then, they reach W2.1's new unscoped resolution, which refuses an ambiguous type_id instead of taking the lowest rowid.
2. **Name, not path** (W2.2–W2.4):
   - `_project_meta_json` and `_check_artifact_completeness` in `workflow_state_server.py`;
   - `promote_task` in `task_promotion.py`, and its wrapper at `workflow_state_server.py:2716`.
3. **Activation** (W2.5): `feature_lifecycle.activate_feature`, in one `db.transaction()`.
4. **The skill's mkdir** (W2.7): `plugins/pd/skills/workflow-state/SKILL.md:14-20`.
5. **Backfill** (W2.6): `backfill.py`, and the entity server's startup call (`entity_server.py:282-294`), which passes the resolved workspace.
6. **New tests,** red on 1A's base (W2's list in the design):
   - `plugins/pd/mcp/test_create_feature_lanes.py`: deep, express and decomposed, the skill-content test, and activation retry. The create-feature steps follow `commands/create-feature.md:17-22`, with express's `record_mini_spec` at `:22`.
   - `plugins/pd/hooks/lib/entity_registry/test_workflow_phase_writers.py`: explicit workspace, and upsert refuses.
   - `plugins/pd/mcp/test_projection_names_directory.py`: worktree projection, projects, completeness and promotion.
   - `plugins/pd/hooks/lib/entity_registry/test_backfill_scoped.py`: scope and source.

   Every lane test starts both servers through their real lifespans against a temp DB (`ENTITY_DB_PATH` set to a tmp path), with a temp HOME and a temp repo. It never reaches the live registry.
7. **Existing tests,** per verify-p0's classification:
   - **Rewrite about 67:**
     - 42 mechanical backfill-signature changes;
     - promotion fixtures in `test_task_promotion.py`, `test_c5b_workspace_callers.py` and `test_c3_allocation_callers.py`;
     - the projection and completeness tests, including `test_feature_134_trustgate.py`.
   - **Delete:** only the tests that pin the backfill's file reads (`_resolve_meta_path`, and `.meta.json` status winning over the DB, e.g. `test_backfill.py:1088`, `:1117`), each listed with its W2.6 reason.
   - **The rest:** tests that pin behaviour 1B deletes still pass at 1A. 1A's G1 has no failures.

**1B: delete the file→registry writers, scope cascade recovery** (W1.1–W1.8).
1. **Task 1** (W1.1): `entity_status.py`. Keep the brainstorm helper's Part 1.
2. **Explicit archive** (W1.2): the `update_entity` tool (`entity_server.py`), and `commands/cleanup-brainstorms.md:25`.
   - **Docs listing its parameters:** `docs/technical/api-reference.md:135-141`, `README_FOR_DEV.md:447`, `plugins/pd/README.md:130`.
   - **Sweep:** `git grep -nE 'status="archived"|status=.archived.' -- plugins/pd/commands plugins/pd/skills plugins/pd/agents plugins/pd/references` lists no call that passes the retired status to a tool.
3. **Task 2 and `reconcile_apply`** (W1.3–W1.4), with the design's full sweep. Done when W1.4's `git grep` prints nothing.
4. **Hydration** (W1.5):
   - **Delete:** `engine.py:592-654`, and `get_state`'s fall-through at `engine.py:105`, so `get_state` returns None with no row.
   - **Unchanged:** the degraded branches (`:93-99`, `:106-112`).
   - **Sweep:** the docstrings at `:467` and `:514`.
5. **`reconcile_status`** (W1.6): the scope at `workflow_state_server.py:2074`, and the health rule.
6. **Cascade recovery** (W1.7):
   - the orchestrator's new Task 2;
   - `_recover_pending_cascades(db, workspace_uuid)`;
   - `rollup.py`'s uuid writes and its stop at the workspace's edge;
   - `dependencies.py:184-185`.
7. **Task 3** (W1.8): `dependency_freshness.py`.
8. **New tests,** red on 1B's base (W1's list in the design):
   - `plugins/pd/hooks/lib/reconciliation_orchestrator/test_session_start_reads_no_files.py`: no archive, no brainstorm archive, no regression, no namesake row, rollup, dependency flip, and Task 3;
   - `plugins/pd/hooks/lib/workflow_engine/test_get_state_without_hydration.py`;
   - `plugins/pd/mcp/test_reconcile_status_scoped.py`;
   - `plugins/pd/mcp/test_update_entity_archived.py`.
9. **Existing tests,** per verify-p0's classification:
   - **Delete about 109**, each listed with the W1 change it pins.
   - **Rewrite about 20:**
     - `_recover_pending_cascades` gains a parameter;
     - the orchestrator's key set;
     - helper isolation;
     - the validator-caller lists in `test_c11_mcp_dir_name.py`;
     - two engine integration tests seed the row.

**Phase 1 integration:**
- integration review and QA, as in the review protocol;
- F1 on the phase branch;
- landing;
- F3's first hand-off.

## Phase 2 (P1): workspace resolution and identity

It starts when Phase 1 has landed.
- **Order:** 2A and 2B run side by side, since their files are disjoint. 2C is cut after 2A merges.

**2A: resolve or refuse, recovery threads, relabel** (W4.1–W4.3).
- **Files:**
  - `entity_server.py` and `workflow_state_server.py`: the `_require_workspace()` accessor and the write tools W4.1 lists, except W3.4's tools, which 2C wires; the recovery threads go;
  - `feature_lifecycle.py` near `:487`: the relabel;
  - `workflow_state_server.py`'s `_catch_value_error` (`:885-921`), whose mapping learns the `cross_workspace_parent:` prefix.
- **`database.py`:** not edited. The legacy-id lookup reuses `_resolve_optional_workspace_filter`, as W4.1 says.
- **New tests,** in `plugins/pd/mcp/test_require_workspace.py`:
  - the first-session tests: both servers started through their real lifespans, against a temp DB and a temp repo with no `.claude/` and no workspaces row, launched from the root, a subdirectory and a second clone;
  - add-to-backlog in a first session;
  - refuse, and the relabel.
- **Existing tests,** per verify-rest's classification:
  - rewrite about 24 fixtures that relied on `__unknown__`, including `test_issue_spawn.py::TestAC95ParentValidation::test_cross_workspace_parent_spawn_succeeds` (its fixture sets a workspace; its assertion is unchanged);
  - delete the 4 recovery-thread tests.

**2B: the board, links and the remaining guards** (W3.1–W3.3).
- **Files:**
  - `database.py`: `list_workflow_phases`, the re-attribution cascade, and `append_phase_event`'s fallback;
  - `plugins/pd/ui/`: routes, templates and `mermaid.py`.
- **New tests:**
  - `plugins/pd/ui/tests/test_board_workspace_join.py`: one card, a working card link, orphan scope, and the Entities page;
  - `plugins/pd/hooks/lib/entity_registry/test_cross_workspace_writer_guards.py`: the cascade.
- **Existing tests:** rewrite about 20 that pin type_id links or the old join.

**2C: entity tools resolve in the caller's workspace** (W3.4). Cut after 2A merges; it uses `_require_workspace()` and edits the same tools.
- **Files:** `entity_server.py` (`_resolve_ref_param`, and the tools W3.4 lists, each calling `_require_workspace()`) and `server_helpers.py:499`.
- **New tests,** in `plugins/pd/mcp/test_entity_tools_resolve_in_workspace.py`:
  - W3.4's tests;
  - the keep-green `set_parent`-by-uuid test;
  - one W3.4 tool answering `workspace_unresolved`.
- **Existing tests:** feature 129's four cross-workspace tests (named in W3.4) pass with their assertions unchanged.

## Phase 3 (P1): root detection and the plugin cache (W4.4–W4.5)

It starts when Phase 1 has landed, and runs beside Phase 2.
- **No dependency on Phase 2:** a nested worktree resolves its workspace through `resolve_startup_workspace_uuid`, which maps a linked worktree to its repository (`project_identity.py:715-723`). It doesn't need 2A's accessor.

**3A:**
- **Files:**
  - `hooks/lib/common.sh:13`;
  - `scripts/doctor.sh`, which sources `common.sh`, plus `:270`, `:310` and `:385`;
  - `scripts/setup.sh:115`;
  - the six hook-test repo-root finders W4.4 lists;
  - `hooks/sync-cache.sh`;
  - `test-hooks.sh`'s Tests 13b and 13c, which skip in a linked worktree (W4.5).
- **New tests,** in `plugins/pd/hooks/lib/test_project_root_and_sync_cache.py`, under G1's path:
  - root detection;
  - no archive from a worktree root;
  - sync-cache from a sibling worktree.

  They build temp repos with linked worktrees. HOME is a temp dir whose `.claude/plugins/installed_plugins.json` names a temp cache.
- **The four edited scripts no gate runs** (`test-data-file-guard`, `test-promptimize-content`, `test-enriched-docs-content`, `test-worktree-dispatch`; N9): 3A's QA runs each once under a temp HOME, after reading it to confirm it is isolated. One that isn't isolated is recorded as unverified with N9.
- **G4 runs twice:** from the scratch clone (13b and 13c run), and from a linked worktree added to that clone (13b and 13c skip).

## Phase 4 (P2): tooling and docs (W5)

It starts when Phase 1 has landed, and runs beside Phases 2 and 3.

**4A:**
- **Deletions:**
  - `display.py` and its tests, with the guard entries and stale comments (W5.1);
  - the two shell tests and their references (W5.2).
- **The C11 design's D7 note** (W5.4).
- **`docs/user-guide/overview.md:42`** (W5.3).
- **The README patch** (W5.3, D4), which is not committed:
  - written against the main checkout's `HEAD:README.md` at line 80;
  - saved to `/Users/terry/projects/pedantic-drip/agent_sandbox/2026-09-25/release-c-followups/readme-board.patch`;
  - checked with `git -C /Users/terry/projects/pedantic-drip apply --check`.
- **Measured:** G1 collects exactly 25 fewer tests than 4A's base, re-measured on the rebased base if 4A rebases.

**4B: the repo-root script tests** (W5.5, N13). Runs beside 4A; the files are disjoint.
- **`scripts/test_migrate_e2e.py`:**
  - `_run_migrate` stops passing `ENTITY_DB_PATH` through;
  - the sentinel test sets the variable itself (W5.5), so it runs under G5, which unsets it;
  - red on 4B's base.
- **`TestMigration6`:** rewrite against the current chain, or delete what only pins a retired schema. The task report names which.
- **Measured:** G5 has 0 failures.

## Gates

**Where they run:**
- **Every task's QA and every phase's integration QA** run all five gates on the checkout under test.
- **Every gate** uses the main checkout's interpreter, a temp HOME, and `ENTITY_DB_PATH` unset, unless its entry says otherwise.

**A gate passes when** its failures are exactly its base's failures:
- G1, G2 and G4: none at `84fc9376`;
- G5: its base's set, until 4B, then none.

A new failure that is explained but not fixed does not pass. It goes through the review protocol's fix round, then escalation.

**The gates:**
- **G1:** `python -m pytest plugins/pd/hooks/lib plugins/pd/mcp plugins/pd/ui/tests -q -p no:cacheprovider`. At `84fc9376`: 4355 passed, 2 skipped. It includes `doctor/test_audit_writes.py`.
- **G2:** `python -m pytest plugins/pd/scripts/tests -q -p no:cacheprovider`. At `84fc9376`: 49 passed, 1 skipped.
- **G3:** `./validate.sh` on a `git archive` export of the checkout under test, with `plugins/pd/hooks/tests/test-hooks.sh` removed.
  - It runs under a temp HOME, whose `installed_plugins.json` points at a temp cache.
  - It is followed by `bash scripts/dev/check_fr_c_115_atomicity_postmerge.sh develop`, run from the checkout under test. The script checks `merge-base(develop)..HEAD`, which is exactly the work under test.
- **G4:** `test-hooks.sh` from a scratch clone of the branch under test (`git clone <repo> <scratch>`, then check out the branch), with the main checkout's `plugins/pd/.venv` symlinked into the clone.
  - **HOME:** a temp dir whose `.claude/plugins/installed_plugins.json` points pd's `installPath` at a temp cache.
  - **Why a clone:** its `.git` is a directory, so the suite roots and publishes as a main checkout does.
  - **Expected at `84fc9376`:** 66/66.
- **G5:** `python -m pytest scripts/test_*.py -q -p no:cacheprovider`.
  - **Base:** the task's base, measured in the same environment. With `ENTITY_DB_PATH` set to a temp DB, `84fc9376` has 16 failures (N13); unset, the count is measured at kickoff.
  - **After 4B:** 0 failures.

## Final checks

**F1: live-copy check.** It runs at Phase 1's integration, on the phase branch, and again at F2, on develop.
- **Why it exists:** it replays the changed session start, backfill and create-feature against the real registry's shapes. Synthetic fixtures don't carry those shapes: 21 workspaces, 7 shared type_ids, mixed `artifact_path`s, 128 archived rows and legacy ids. It is Release C's live rehearsal, repeated.
- **Setup:**
  1. **The code:** a scratch clone of the branch under test, whose own orchestrator and entity server run every step.
  2. **The snapshot:** one copy, S, of the live registry, made as the safety section says. Each step starts from its own copy of S.
  3. **A timestamp file,** created before step 1.
- **Workspaces:** every step pins its workspace with `ENTITY_WORKSPACE_UUID`, plus `--workspace-uuid` for the orchestrator. The scratch directories carry no `workspace.json`.
  - **Steps 1, 2 and 4:** pedantic-drip is `69696982-0e18-46f1-acf2-18a3edc6bbb7`.
  - **Step 3:** terry_agent is `f7b49c1d-6a72-4fe6-a4e7-14706161625a`.
- **Row fingerprint:** a sha256 over each table's rows, sorted by primary key, for:
  - `entities`, all columns;
  - `workflow_phases`, all columns;
  - `phase_events` and `events`, with row count and max rowid.

  Any inserted, deleted or modified row counts as a change.
- **Steps:**
  1. **Main checkout:**
     - **Setup:** `rsync -a` the main checkout's `docs/`, including its `.meta.json` projections, into scratch.
     - **Run:** the orchestrator, as `session-start.sh` runs it, with `--project-root <scratch>`.
     - **Expected:** unchanged fingerprints, except inserted brainstorm entities, and their creation events, for tracked `.prd.md` files the copy lacks.
  2. **Fresh checkout:**
     - **Setup:** a second scratch clone, with no `.meta.json`.
     - **Expected:** the same as step 1.
  3. **terry_agent:**
     - **Setup:** `rsync -a /Users/terry_agent/docs/` into scratch. `/Users/terry_agent` is read, never written.
     - **Expected:**
       - no row outside terry_agent's workspace changes;
       - terry_agent's rows change only by brainstorm registration;
       - no row for `feature:035-slim-watchdog-self-mgmt` is created in either workspace.
  4. **Entity-server startup backfill:**
     - **Before:** list pedantic-drip's row-less entities with SQL on the copy (entities with no `workflow_phases` row for the same workspace and type_id, of kinds feature, brainstorm and backlog).
     - **Run:** the lifespan, with its working directory the scratch clone.
     - **Expected:** exactly those entities gain rows, each with its own `workspace_uuid` and `uuid`.
  5. **Create-feature, deep lane:**
     - **Setup:** a scratch repo with `.claude/` created first, so the resolver mints its own workspace. In Phase 1, W4.1 doesn't exist yet (N12).
     - **Expected:** the transition to `specify` succeeds.
- **After the steps:**
  - `find /Users/terry_agent /Users/terry/projects/pedantic-drip -newer <timestamp file> -not -path '*/agent_sandbox/*' -not -path '*/.pd-worktrees/*'` prints nothing;
  - the live file's fingerprint matches kickoff's;
  - the results go in the phase report.
- **A failure** is a phase integration QA failure. It gets one fix round and one F1 re-run, then escalation.
- **A changed live fingerprint** means something outside this plan wrote the file, for example the user's own session. The orchestrator stops and asks the user. The copy-based results still stand, and the change and its cause are recorded.

**F2: final gate.** After all four phases land:
- G1–G5 on develop;
- F1 on develop;
- the follow-ups section of `docs/plans/2026-09-22-structural-identity-completion-plan.md` updated. Each item is marked with the commit that closed it, or with its row in the design's "Deferred" table, which is on develop since kickoff.

**F3: hand-offs to the user.** Nothing is published, pushed or written live without a yes.
- **After Phase 1 lands,** the orchestrator asks whether to publish the plugin cache (`sync-cache.sh` from the main checkout) and push develop. With Phase 1 published, the user can re-enable pd in their settings; the plan never re-enables it.
- **After F2,** it asks about:
  - publishing and pushing again;
  - D2 (leave, or restore the archived features);
  - the README patch (D4).
- **On a yes:**
  - the orchestrator carries out the publish, the push or the restore, the restore as a gated live write with a fingerprint check;
  - the user applies the README patch, since the file holds their edits.

## Done when

1. **Problems covered:** every problem in the design's two triage tables is either:
   - closed by a merged change;
   - in the design's "Deferred" table;
   - or settled by a user decision (D2 for N7, D4 for the README half of W5.3).
2. **Tests:** every test the design names exists and passes on develop. Its red output on its base is in the task report, or the design marks it keep-green.
3. **Gates:** G1–G5 pass on develop at F2.
4. **Live copy:** F1 passes at Phase 1's integration and at F2, and the live registry's fingerprint matches kickoff's, or its change is recorded as F1 says.
5. **Status recorded:** the completion plan's follow-ups section records each item's resolution.
6. **Hand-offs:** F3's questions are answered by the user.

## Calvin ledger (report mode, 2026-09-25): author's answers

Calvin swept plan rev 1 (lines L1–L196 below are rev 1's) and asked 73 questions. The author answered each, and rev 2 carries the answers. The plan review's 3 blockers and 12 warnings overlap questions 1–18 and are absorbed with them. "Rev 2:" names the section that now says it.

| # | Line (rev 1) | Category | Question (short) | Status | Author's answer |
|---|---|---|---|---|---|
| 1 | L3+L23+L83+L99 | assumption · blocker | Are the design and verdicts on task branches? | RESOLVED | The plan and design are committed to develop at kickoff, so every branch has them; evidence is read by absolute main-checkout path. Rev 2: Roles and locations. |
| 2 | L6+L183 | completeness · blocker | When does the user rule on D1, D3, D5? | RESOLVED | At kickoff, through AskUserQuestion, before Phase 1; D1 shapes 1B, D3 and D5 shape Phase 2. Rev 2: Roles and locations. |
| 3 | L17+L90+L115+L129 | completeness · blocker | How does a later phase land on a moved develop? | RESOLVED | It rebases onto develop, re-runs its integration QA, then fast-forwards. Rev 2: Branches, merges and landing. |
| 4 | L37+L50+L108 | reasoning · blocker | Red on which base, for 1B and 2C? | RESOLVED | A task's base is the commit its branch is cut from; 1B and 2C are cut after their sibling merges, so red shows their own change. Rev 2: Branches, merges and landing. |
| 5 | L42+L17+L86 | assumption · blocker | How does a fast-forward leave README.md alone? | RESOLVED | `git merge --ff-only` in the main checkout; no task commits README.md or a user-untracked path, and `git status --short` is compared before and after. Rev 2: Roles and locations. |
| 6 | L83 | reasoning · blocker | How to tell a pinned-behaviour test from a breakage? | RESOLVED | A test may be deleted only when it exercises a symbol or behaviour a named design change deletes, cited per test; anything else is a breakage to fix; the reviewer checks each citation. Rev 2: Review protocol, item 7. |
| 7 | L86+L168 | ambiguity · blocker | Which branch's code runs F1? | RESOLVED | A scratch clone of the branch under test: the phase branch at Phase 1, develop at F2. Rev 2: F1 setup. |
| 8 | L98+L64 | assumption · blocker | Which DB do the lifespans open in tests? | RESOLVED | A temp DB via `ENTITY_DB_PATH`, with a temp HOME and temp repo; never the live registry. Rev 2: 1A item 6, 2A. |
| 9 | L124+L97+L110 | completeness · blocker | Where do 2A, 2C, 3A tests live; which gate runs them? | RESOLVED | Named files under G1's paths: `test_require_workspace.py`, `test_entity_tools_resolve_in_workspace.py`, `hooks/lib/test_project_root_and_sync_cache.py`. Rev 2: Phases 2 and 3. |
| 10 | L125+L157 | ambiguity · blocker | What are "the main checkout of a scratch worktree" and "a nested worktree of it"? | RESOLVED | G4 now runs from a scratch clone; 3A runs it again from a linked worktree added to that clone, where Tests 13b and 13c skip. Rev 2: G4, 3A. |
| 11 | L140+L142 | inconsistency · blocker | How does the sentinel test run red while ENTITY_DB_PATH is unset? | RESOLVED | The sentinel test sets the variable itself (monkeypatch) to a tmp path; the rest of the module runs with it unset. Rev 2: 4B; design W5.5. |
| 12 | L153+L23 | assumption · blocker | Do task worktrees have the venv? | RESOLVED | No; every gate uses the main checkout's interpreter by absolute path, run from the checkout under test. Rev 2: Roles and locations. |
| 13 | L155+L41 | completeness · blocker | What HOME does G3 use? | RESOLVED | A temp HOME whose `installed_plugins.json` points at a temp cache. Rev 2: G3. |
| 14 | L164+L193 | vagueness · blocker | What does "pass" mean; does an explained failure pass? | RESOLVED | Pass means failures exactly equal the base's; an explained but unfixed failure doesn't pass and goes through the fix round, then escalation. Rev 2: Gates. |
| 15 | L169+L171 | ambiguity · blocker | What does step 1's export carry? | RESOLVED | The main checkout's `docs/` via rsync, projections included; step 2 is a fresh clone without them. Rev 2: F1 steps 1–2. |
| 16 | L169+L171+L172 | assumption · blocker | What pins each F1 directory's workspace? | RESOLVED | `ENTITY_WORKSPACE_UUID` and `--workspace-uuid`, set to the named uuids; the scratch directories carry no `workspace.json`. Rev 2: F1 Workspaces. |
| 17 | L170 | completeness · blocker | Does the comparison see `workflow_phases`? | RESOLVED | Yes: the fingerprint covers `entities`, `workflow_phases`, `phase_events` and `events`. Rev 2: F1 row fingerprint. |
| 18 | L174 | assumption · blocker | Who registers step 5's scratch repo, before N12's fix? | RESOLVED | The step creates `.claude/` in the scratch repo first, so the resolver mints its workspace. Rev 2: F1 step 5. |
| 19 | L4 | completeness · minor | Which binds when plan and design disagree? | RESOLVED | The design; the implementer records the conflict, and the orchestrator amends before merging. Rev 2: header. |
| 20 | L8–L15 | completeness · minor | Which bar covers the 404 links, N11, W5? | RESOLVED | Bar 6: each passes the test or grep check the design names. Rev 2: Problem, bar 6. |
| 21 | L9+L68+L170 | inconsistency · minor | Does bar 1 exclude brainstorm registration? | RESOLVED | Yes, and bar 1 now says so. Rev 2: bar 1. |
| 22 | L10 | completeness · minor | Which test shows clone and old checkout change nothing? | RESOLVED | No archive (clone, fresh worktree), No regression (old checkout), and F1 step 2. Rev 2: bar 1. |
| 23 | L12 | vagueness · minor | Where is "end to end"'s end? | RESOLVED | Allocation through the first phase transition, where N1 broke. Rev 2: bar 2. |
| 24 | L13 | inconsistency · minor | Inserts or all writes; where do the deferred updates fall? | RESOLVED | Inserts only; the type_id-only updates are deferred with the re-key (D3), and bar 3 says so. Rev 2: bar 3. |
| 25 | L13 | reasoning · minor | Which W3 test shows an insert storing workspace and uuid? | RESOLVED | None; the proof is W2.1's tests and F1 step 4. Bar 3 no longer cites W3. Rev 2: bar 3. |
| 26 | L14 | vagueness · minor | How far does "Nothing lands in __unknown__" reach? | RESOLVED | MCP tools only; the library's defaults are deferred. Rev 2: bar 4. |
| 27 | L15 | reasoning · minor | Which test shows a nested worktree archives nothing? | RESOLVED | A new W4 test, "No archive from a worktree root", run after Phase 1. Rev 2: bar 5, 3A; design W4 tests. |
| 28 | L23 | completeness · minor | What if an anchor fails re-verification? | RESOLVED | Find the symbol by name and record old → new; stop and escalate if it's gone or changed in meaning. Rev 2: Branches. |
| 29 | L29+L152 | ambiguity · minor | Which gates does a task's QA run? | RESOLVED | All five. Rev 2: Review protocol, Gates. |
| 30 | L31+L28 | inconsistency · minor | Does the phase fix round run with no findings? | RESOLVED | No: at most one fix round, only with findings, and QA re-runs only after a fix. Rev 2: Review protocol. |
| 31 | L33 | completeness · minor | What happens while an escalation waits? | RESOLVED | Independent tasks continue; the blocked phase doesn't land. Rev 2: Review protocol. |
| 32 | L35 | vagueness · minor | Where does 6 come from; what counts? | RESOLVED | The user's Release C setting; it overrides pd.local.md's 5 for this orchestration, counts every agent, and is confirmed at kickoff. Rev 2: Review protocol. |
| 33 | L37+… | ambiguity · minor | Where do reports live? | RESOLVED | `agent_sandbox/<date>/release-c-followups-execution/` in the main checkout, by absolute path. Rev 2: Roles and locations. |
| 34 | L48 | assumption · minor | Why now; what if pd stays disabled? | RESOLVED | Disabled, nothing breaks; the round exists so re-enabling is safe, and Phase 1 is the part re-enabling needs. Rev 2: Phase 1 intro. |
| 35 | L48+L183 | completeness · minor | Who re-enables pd, and when? | RESOLVED | The user, in their settings, once Phase 1 is published at F3's first hand-off; the plan never does. Rev 2: F3. |
| 36 | L50 | inconsistency · minor | Which 1B step edits backfill.py? | RESOLVED | None; the rev 1 sentence was wrong. `backfill.py` is 1A's only. Rev 2: Phase 1 order. |
| 37 | L50 | ambiguity · minor | What counts as 1A depending on 1B's deletions; who checks? | RESOLVED | A 1A test that passes only through hydration or Task 2; the lane tests assert the row before any engine read, and 1A's QA re-runs them with hydration patched to raise. Rev 2: Phase 1 order. |
| 38 | L57 | ambiguity · minor | Which unscoped path refuses ambiguity? | RESOLVED | W2.1's new resolution in `create_workflow_phase`, which refuses instead of taking the lowest rowid; the rev 1 wording was loose. Rev 2: 1A item 1. |
| 39 | L57+L152 | completeness · minor | What must 1A's gates show for tests 1B will delete? | RESOLVED | They still pass; 1A's G1 has no failures. Rev 2: 1A item 7. |
| 40 | L63+L82+L105 | ambiguity · minor | What do `fu` and `w2` tell a reader? | RESOLVED | Nothing; the files are renamed by what they test. Rev 2: every task's new tests. |
| 41 | L65 | ambiguity · minor | Which tests does 1A delete? | RESOLVED | Only those pinning the backfill's file reads, each listed with its W2.6 reason. Rev 2: 1A item 7. |
| 42 | L65+… | vagueness · minor | What if a count strays from "about N"? | RESOLVED | Counts are guidance; every failure is classified individually, and one outside the verdicts' tables is investigated first. Rev 2: Review protocol, item 7. |
| 43 | L72 | vagueness · minor | Which markdown does the `status="archived"` sweep cover? | RESOLVED | commands, skills, agents and references, by the stated `git grep`. Rev 2: 1B item 2. |
| 44 | L74 | assumption · minor | What else lives in engine.py:105's branch? | RESOLVED | Only the fall-through to hydration; the degraded reads sit in the other two branches, which are unchanged. Rev 2: 1B item 4. |
| 45 | L84+L65 | inconsistency · minor | How do 61 and 45 add up to 87? | RESOLVED | They didn't; per verify-p0, 1A rewrites about 67 and 1B about 20, which is 87. Rev 2: 1A item 7, 1B item 9. |
| 46 | L86 | completeness · minor | What if F1 fails? | RESOLVED | A phase integration QA failure: one fix round, one re-run, then escalation. Rev 2: F1. |
| 47 | L88+… | ambiguity · minor | What does "P1" name? | RESOLVED | Only a priority; tasks are renamed 1A–4B. Rev 2: header. |
| 48 | L90+L96+L103 | inconsistency · minor | Where does the new helper live? | RESOLVED | Dropped: 2A reuses `_resolve_optional_workspace_filter`, and doesn't edit `database.py`. Rev 2: 2A; design W4.1. |
| 49 | L94+L109 | ambiguity · minor | Who wires W3.4's tools to `_require_workspace()`? | RESOLVED | 2C, with a test. Rev 2: 2A, 2C; design W3.4. |
| 50 | L95 | ambiguity · minor | Which file holds the envelope mapping? | RESOLVED | `workflow_state_server.py`'s `_catch_value_error` (`:885-921`). Rev 2: 2A. |
| 51 | L111 | ambiguity · minor | Which four 129 tests? | RESOLVED | Named in design W3.4, with the one fixture change. Rev 2: 2A, 2C. |
| 52 | L115 | reasoning · minor | How does a nested worktree resolve before Phase 2? | RESOLVED | `resolve_startup_workspace_uuid` maps a linked worktree to its repository, so no accessor is needed. Rev 2: Phase 3. |
| 53 | L122 | completeness · minor | What shows the unrun scripts' finders work? | RESOLVED | 3A's QA runs the four scripts once under a temp HOME, or records them unverified with N9. Rev 2: 3A. |
| 54 | L129 | inconsistency · minor | How are Phase 4's files disjoint? | RESOLVED | They aren't; the shared files and hunks are named, and the rebase rule handles landing. Rev 2: Branches. |
| 55 | L129 | reasoning · minor | Why must Phase 4 land last? | RESOLVED | It needn't; that line is gone. Rev 2: Branches. |
| 56 | L137 | ambiguity · minor | Which commit is 4A's base for the count? | RESOLVED | The commit 4A is cut from, re-measured after any rebase. Rev 2: 4A. |
| 57 | L146 | ambiguity · minor | Which task writes the README patch, against which HEAD? | RESOLVED | 4A, against the main checkout's `HEAD:README.md`, saved by absolute path. Rev 2: 4A. |
| 58 | L154+L153 | ambiguity · minor | Why does G2 repeat test_audit_writes? | RESOLVED | It needn't; G1 runs it, and G2 is `scripts/tests` only. Rev 2: G2. |
| 59 | L155+L152 | reasoning · minor | What does the atomicity script check before develop has the work? | RESOLVED | `merge-base(develop)..HEAD` of the checkout under test, which is exactly the work under test. Rev 2: G3. |
| 60 | L161+L37+L164 | ambiguity · minor | Is `84fc9376` the base for later phases? | RESOLVED | No; each gate compares with the task's own base. Rev 2: Gates, G5. |
| 61 | L168 | reasoning · minor | What does F1 catch that tests can't? | RESOLVED | The real registry's shapes: 21 workspaces, shared ids, mixed paths, archived rows and legacy ids. Rev 2: F1. |
| 62 | L168 | ambiguity · minor | Which copy does each step start from? | RESOLVED | Its own copy of one snapshot S. Rev 2: F1 setup. |
| 63 | L170+L171 | ambiguity · minor | Is an inserted row a change; does step 2 carve out brainstorms? | RESOLVED | Yes, and yes: steps 1 and 2 share the brainstorm carve-out. Rev 2: F1 steps. |
| 64 | L172+L10 | inconsistency · minor | May terry_agent's own rows change? | RESOLVED | Only by brainstorm registration. Step 3 is terry_agent's own checkout, not a namesake. Rev 2: F1 step 3. |
| 65 | L173 | completeness · minor | How is "row-less" known beforehand? | RESOLVED | By SQL on the copy before the run. Rev 2: F1 step 4. |
| 66 | L176 | vagueness · minor | What is a row fingerprint? | RESOLVED | Defined in F1: tables, columns and ordering. Rev 2: F1. |
| 67 | L176+L194 | ambiguity · minor | Unchanged since when? | RESOLVED | Since kickoff's fingerprint. Rev 2: Roles, F1, Done-when 4. |
| 68 | L181 | assumption · minor | Is the design on develop at F2? | RESOLVED | Yes, since kickoff. Rev 2: F2. |
| 69 | L183+L48 | reasoning · minor | Why wait for all four phases to publish? | RESOLVED | No reason; F3 now offers publish and push right after Phase 1. Rev 2: F3. |
| 70 | L191 | completeness · minor | How is N7 counted? | RESOLVED | Settled by the user's D2 decision; Done-when 1 names that route. Rev 2: Done when. |
| 71 | L194+L176 | assumption · minor | What else could change the live file? | RESOLVED | The user's own sessions or scripts; a change stops the run for the user, and is recorded. Rev 2: F1. |
| 72 | L196+L183 | ambiguity · minor | Who carries out a yes at F3? | RESOLVED | The orchestrator publishes, pushes or restores; the user applies the README patch. Rev 2: F3. |
| 73 | doc | assumption · minor | Who cuts, merges, fast-forwards and runs F1–F3? | RESOLVED | The orchestrator. Rev 2: Roles and locations. |

☑ 73 resolved · 0 open · 0 dismissed
